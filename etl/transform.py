"""TRANSFORM: validate, conform to dimensions, reconstruct model runs, stage lab logs."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import TMS_FAMILY, STAGING
from .reconstruct import build as build_reconstructed


class DQ:
    """Collects data-quality results; FAIL stops the pipeline before load."""
    def __init__(self):
        self.rows = []

    def check(self, name, table, bad: pd.DataFrame | int, detail="", severity="FAIL"):
        n = bad if isinstance(bad, int) else len(bad)
        self.rows.append({"check_name": name, "target_table": table,
                          "status": "PASS" if n == 0 else severity, "failed_rows": n, "detail": detail})

    @property
    def failed(self):
        return [r for r in self.rows if r["status"] == "FAIL"]


def _pack_scale(n):
    return "single_cell" if n == 1 else ("module" if n <= 16 else "pack")


def transform(f: dict):
    dq = DQ()
    src, packs, mats, meas, rel, thr = (f[k].copy() for k in
                                        ("sources", "packs", "materials", "measurements", "relative", "thresholds"))

    # ---------- validation ----------
    for name, df, key in [("sources", src, "source_id"), ("packs", packs, "pack_id"),
                          ("materials", mats, "material_id"), ("measurements", meas, "meas_id"),
                          ("relative", rel, "rel_id")]:
        dq.check(f"unique_{key}", name, df[df[key].duplicated()], f"duplicate {key}")
    dq.check("fk_meas_source", "measurements", meas[~meas.source_id.isin(src.source_id)])
    dq.check("fk_meas_pack", "measurements", meas[~meas.pack_id.isin(packs.pack_id)])
    dq.check("fk_meas_material", "measurements", meas[~meas.material_id.isin(mats.material_id)])
    dq.check("fk_rel_material", "relative",
             rel[~rel.material_id.isin(mats.material_id) | ~rel.baseline_material_id.isin(mats.material_id)])
    temp_metrics = meas.metric.str.startswith("T_MAX")
    dq.check("range_t_max_0_120C", "measurements", meas[temp_metrics & ~meas.value.between(0, 120)])
    dq.check("range_dt_0_30C", "measurements", meas[(meas.metric == "DT_MAX") & ~meas.value.between(0, 30)])
    dq.check("range_c_rate", "measurements", meas[meas.c_rate.notna() & ~meas.c_rate.between(0.1, 10)])
    dq.check("doi_or_url_present", "sources", src[src.doi.isna() & src.open_url.isna()])
    # physical sanity: foam/PCM peak should not exceed no-PCM peak for same pack+condition
    t = meas[meas.metric == "T_MAX"].merge(mats[["material_id", "tms_code"]], on="material_id")
    t = t.assign(amb=t.ambient_c.fillna(-999))
    base = t[t.tms_code == "NC"][["pack_id", "c_rate", "amb", "value"]].rename(columns={"value": "nc"})
    foam = t[t.tms_code.str.startswith(("CF", "NF"))].merge(base, on=["pack_id", "c_rate", "amb"])
    dq.check("foam_peak_le_baseline", "measurements", foam[foam.value > foam.nc],
             "metal-foam peak above no-PCM peak", severity="WARN")

    # ---------- conform dimensions ----------
    packs["n_cells"] = packs.n_cells.astype(int)
    packs["pack_scale"] = packs.n_cells.map(_pack_scale)
    packs["layout"] = packs.rows.astype(int).astype(str) + "x" + packs.cols.astype(int).astype(str)
    mats["tms_family"] = mats.tms_code.map(TMS_FAMILY).fillna("METAL_FOAM_PCM")
    mats = mats.rename(columns={"foam_mass_g_per_cell": "foam_mass_g_per_cell"})

    # ---------- reconstructed time-series runs (S1) ----------
    runs, logs = build_reconstructed(meas, f["packs"], f["materials"])
    err = (runs.sim_peak - runs.target_value).abs()
    dq.check("reconstruction_peak_within_0.05C", "fact_run", runs[err > 0.05])
    anchors = meas.set_index("meas_id").value
    dt_runs = runs[runs.anchor_meas_id.str.contains(r"\+", na=False)]
    dt_err = [abs(r.sim_dt_max - anchors[r.anchor_meas_id.split("+")[1]]) for r in dt_runs.itertuples()]
    dq.check("reconstruction_dt_within_0.05C", "fact_run", int(sum(e > 0.05 for e in dt_err)))

    # ---------- lab logs (if any were dropped into data/raw/lab_logs) ----------
    lab = f["lab_logs"]
    if len(lab):
        dq.check("lab_fk_pack", "lab_logs", lab[~lab.pack_id.isin(packs.pack_id)])
        dq.check("lab_fk_material", "lab_logs", lab[~lab.material_id.isin(mats.material_id)])
        dq.check("lab_temp_range", "lab_logs", lab[~lab.temp_c.between(-40, 150)], severity="WARN")
        dq.check("lab_dup_samples", "lab_logs", lab[lab.duplicated(["run_id", "cell_id", "t_s"])])
        lab = lab.drop_duplicates(["run_id", "cell_id", "t_s"])
        lab = lab[lab.temp_c.between(-40, 150)]
        lab_runs = (lab.groupby("run_id").agg(pack_id=("pack_id", "first"), material_id=("material_id", "first"),
                                              c_rate=("c_rate", "first"), ambient_c=("ambient_c", "first"))
                    .reset_index())
        lab_runs["dod_pct"] = lab.groupby("run_id")["dod_pct"].first().values if "dod_pct" in lab else 100
        lab_runs = lab_runs.assign(source_id=None, environment="lab", data_origin="lab_measured",
                                   anchor_meas_id=None, calib_param=None, calib_value=np.nan,
                                   fixed_params=None, target_value=np.nan, sim_peak=np.nan, sim_dt_max=np.nan)
        for col, default in [("phase", None), ("pcm_liquid_frac", np.nan), ("heat_w", np.nan)]:
            if col not in lab:
                lab[col] = default
        runs = pd.concat([runs, lab_runs], ignore_index=True)
        logs = pd.concat([logs, lab[["run_id", "cell_id", "t_s", "temp_c", "pcm_liquid_frac", "heat_w", "phase"]]],
                         ignore_index=True)

    dq.check("log_no_null_temp", "fact_thermal_log", logs[logs.temp_c.isna()])
    dq.check("log_unique_grain", "fact_thermal_log", logs[logs.duplicated(["run_id", "cell_id", "t_s"])])

    # cells dimension = every (pack, cell) seen in logs
    cells = logs.merge(runs[["run_id", "pack_id"]], on="run_id")[["pack_id", "cell_id"]].drop_duplicates()
    rc = cells.cell_id.str.extract(r"R(\d+)C(\d+)")
    cells["row_idx"] = pd.to_numeric(rc[0]); cells["col_idx"] = pd.to_numeric(rc[1])
    cells.loc[cells.cell_id == "C1", ["row_idx", "col_idx"]] = 1

    # conditions dimension = union of measurement + run conditions
    cond = pd.concat([meas[["c_rate", "ambient_c", "dod_pct", "environment"]],
                      runs[["c_rate", "ambient_c", "dod_pct", "environment"]]]).drop_duplicates()

    STAGING.mkdir(parents=True, exist_ok=True)
    runs.to_csv(STAGING / "stg_runs.csv", index=False)
    logs.to_csv(STAGING / "stg_thermal_log.csv", index=False)

    return dict(sources=src, packs=packs, materials=mats, measurements=meas, relative=rel,
                thresholds=thr, runs=runs, logs=logs, cells=cells, conditions=cond), dq
