"""
Build reconstructed time-series runs from the S1 study (He et al. 2025) — the one
source that reports matched natural-convection AND metal-foam/PCM peaks for both a
single cell and a 2x2 module, at 1C/2C/3C in a 25 C chamber.

Calibration chain (one fitted parameter per run, all logged in fact_run):
  1. single cell, no PCM      -> fit heat_w (W/cell) so peak = reported NC peak, h = 10 W/m2K (assumed)
  2. single cell, foam/PCM    -> reuse heat_w from step 1, fit G (cell->composite conductance)
  3. module, no PCM           -> reuse heat_w, fit effective h_conv, then cell heat spread s to match dT_max
  4. module, foam/PCM (F1)    -> reuse heat_w, fit G, then spread s to match dT_max
Other studies are loaded as reported values only (not enough parameters published).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .thermal_model import CellThermal, PCMThermal, RunSpec, simulate, peak, max_spread, calibrate

AMBIENT = 25.0
H_NAT = 10.0                       # assumed natural-convection coefficient, W/m2K
MOD_W, MOD_H = 0.052, 0.065        # S1 module block 52 x 52 x 65 mm
CELL_VOL = np.pi * 0.009 ** 2 * 0.065
SLEEVE_VOL = MOD_W * MOD_W * MOD_H / 4 - CELL_VOL          # composite volume per cell
SLEEVE_OUTER_AREA = (4 * MOD_W * MOD_H + 2 * MOD_W ** 2) / 4  # outer area per cell
PARAFFIN_RHO, CU_RHO = 800.0, 8960.0
MODULE_WEIGHTS = np.array([1.0, 1 / 3, -1 / 3, -1.0])     # 2x2 cell heat-spread pattern
MODULE_CELLS = ["C1_R1C1", "C2_R1C2", "C3_R2C1", "C4_R2C2"]


def _pcm_for(mat: pd.Series) -> PCMThermal:
    eps = float(mat.foam_porosity)
    eta = float(mat.composite_latent_j_per_g) / float(mat.pcm_latent_j_per_g)
    return PCMThermal(
        pcm_mass_kg=SLEEVE_VOL * eps * PARAFFIN_RHO * eta,
        latent_j_per_kg=float(mat.pcm_latent_j_per_g) * 1000,
        melt_c=float(mat.pcm_melt_c),
        melt_halfwidth_c=float(mat.pcm_melt_range_c) / 2,
        foam_mass_kg=SLEEVE_VOL * (1 - eps) * CU_RHO,
        outer_area_m2=SLEEVE_OUTER_AREA,
    )


R_CELL, R_SLEEVE = 0.009, np.sqrt(MOD_W * MOD_W / 4 / np.pi)   # equivalent cylindrical sleeve


def _g_conduction(mat: pd.Series) -> tuple[float, str]:
    """Cell->composite conductance from measured k_eff, cylindrical shell:
    G = 2 pi k L / ln(r2/r1). 20 PPI k is not stated in S1 text -> interpolated by PPI."""
    if pd.notna(mat.k_eff_w_per_mk):
        k, basis = float(mat.k_eff_w_per_mk), "k reported"
    else:
        k, basis = 4.42 + (2.89 - 4.42) * (float(mat.foam_ppi) - 10) / 20, "k interpolated 10/30 PPI"
    return 2 * np.pi * k * MOD_H / np.log(R_SLEEVE / R_CELL), f"{basis} ({k:.2f} W/mK)"


def _cell(pack: pd.Series) -> CellThermal:
    return CellThermal(float(pack.cell_mass_kg), float(pack.cell_cp_j_per_kgk), float(pack.cell_area_m2))


def _frames(run_id, spec, cell_ids):
    t, T, f, q = simulate(spec)
    disch = spec.discharge_s
    rows = []
    for j, cid in enumerate(cell_ids):
        rows.append(pd.DataFrame({
            "run_id": run_id, "cell_id": cid, "t_s": t.astype(int),
            "temp_c": np.round(T[:, j], 3), "pcm_liquid_frac": np.round(f[:, j], 4),
            "heat_w": np.round(q[:, j], 4),
            "phase": np.where(t < disch, "discharge", "rest"),
        }))
    return pd.concat(rows, ignore_index=True)


def build(meas: pd.DataFrame, packs: pd.DataFrame, mats: pd.DataFrame):
    packs = packs.set_index("pack_id"); mats = mats.set_index("material_id")
    m = meas[meas.source_id == "S1"]
    get = lambda pack, mat, c, metric: m[(m.pack_id == pack) & (m.material_id == mat) &
                                         (m.c_rate == c) & (m.metric == metric)]
    runs, logs = [], []
    cell_pack, mod_pack = packs.loc["CELL18650_S1"], packs.loc["MOD18650_2x2_S1"]

    for c in (1, 2, 3):
        # ---- 1. single cell NC: fit heat
        r = get("CELL18650_S1", "M_S1_NC", c, "T_MAX").iloc[0]
        spec = RunSpec(cell=_cell(cell_pack), c_rate=c, ambient_c=AMBIENT, t_start_c=AMBIENT, h_conv=H_NAT)
        q = calibrate(spec, "heat_w", r.value, 0.01, 50, increasing=True)
        rid = f"S1_CELL_NC_{c}C"
        runs.append(dict(run_id=rid, anchor_meas_id=r.meas_id, pack_id="CELL18650_S1", material_id="M_S1_NC",
                         c_rate=c, calib_param="heat_w_per_cell", calib_value=q, fixed_params=f"h_conv={H_NAT}",
                         target_value=r.value, sim_peak=peak(spec), sim_dt_max=0.0))
        logs.append(_frames(rid, spec, ["C1"]))

        # ---- 2. single cell foam/PCM: fit G
        for mat_id in ("M_S1_F1", "M_S1_F2", "M_S1_F3"):
            r = get("CELL18650_S1", mat_id, c, "T_MAX").iloc[0]
            G, gb = _g_conduction(mats.loc[mat_id])
            spec = RunSpec(cell=_cell(cell_pack), c_rate=c, ambient_c=AMBIENT, t_start_c=AMBIENT,
                           heat_w=q, pcm=_pcm_for(mats.loc[mat_id]), G_w_per_k=G, h_out=H_NAT)
            lam = calibrate(spec, "path_scale", r.value, 0.01, 100, increasing=False)
            rid = f"S1_CELL_{mats.loc[mat_id].tms_code}_{c}C"
            runs.append(dict(run_id=rid, anchor_meas_id=r.meas_id, pack_id="CELL18650_S1", material_id=mat_id,
                             c_rate=c, calib_param="thermal_path_scale_lambda", calib_value=lam,
                             fixed_params=f"heat_w={q:.4f};G0={G:.3f} W/K from {gb};h_out0={H_NAT}", target_value=r.value,
                             sim_peak=peak(spec), sim_dt_max=0.0))
            logs.append(_frames(rid, spec, ["C1"]))

        # ---- 3/4. module runs
        for mat_id in ("M_S1_NC", "M_S1_F1"):
            r = get("MOD18650_2x2_S1", mat_id, c, "T_MAX").iloc[0]
            d = get("MOD18650_2x2_S1", mat_id, c, "DT_MAX").iloc[0]
            pcm = None if mat_id == "M_S1_NC" else _pcm_for(mats.loc[mat_id])
            G, gb = (None, "") if pcm is None else _g_conduction(mats.loc[mat_id])
            spec = RunSpec(cell=_cell(mod_pack), c_rate=c, ambient_c=AMBIENT, t_start_c=AMBIENT,
                           heat_w=q, pcm=pcm, G_w_per_k=G or 0.0, h_out=H_NAT, cell_factors=np.ones(4))
            attr, lo, hi, inc = (("h_conv", 0.05, 200, False) if pcm is None else ("path_scale", 0.01, 100, False))
            s = 0.0
            for _ in range(4):                       # alternate peak and spread fits
                spec.cell_factors = 1 + s * MODULE_WEIGHTS
                val = calibrate(spec, attr, r.value, lo, hi, increasing=inc)
                def spread_err(x):
                    spec.cell_factors = 1 + x * MODULE_WEIGHTS
                    return max_spread(spec) - d.value
                a, b = 0.0, 0.6
                for _ in range(40):
                    mid = 0.5 * (a + b)
                    if spread_err(mid) > 0: b = mid
                    else: a = mid
                s = 0.5 * (a + b)
            spec.cell_factors = 1 + s * MODULE_WEIGHTS
            val = calibrate(spec, attr, r.value, lo, hi, increasing=inc)
            code = mats.loc[mat_id].tms_code
            rid = f"S1_MOD_{code}_{c}C"
            runs.append(dict(run_id=rid, anchor_meas_id=f"{r.meas_id}+{d.meas_id}", pack_id="MOD18650_2x2_S1",
                             material_id=mat_id, c_rate=c,
                             calib_param=("h_eff_module_w_per_m2k" if pcm is None else "thermal_path_scale_lambda"),
                             calib_value=val, fixed_params=f"heat_w={q:.4f};cell_heat_spread={s:.4f}" + (f";G0={G:.3f} W/K from {gb};h_out0={H_NAT}" if G else ""),
                             target_value=r.value, sim_peak=peak(spec), sim_dt_max=max_spread(spec)))
            logs.append(_frames(rid, spec, MODULE_CELLS))

    runs = pd.DataFrame(runs)
    runs["source_id"] = "S1"; runs["ambient_c"] = AMBIENT; runs["dod_pct"] = 100
    runs["environment"] = "chamber"; runs["data_origin"] = "model_reconstructed"
    return runs, pd.concat(logs, ignore_index=True)
