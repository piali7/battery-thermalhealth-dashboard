"""
Lumped-capacitance thermal model of a cell (optionally wrapped in a PCM / metal-foam
composite) used to RECONSTRUCT time-series logs from published peak values.

Every reconstructed run is calibrated so that its simulated peak equals the value
reported in the source paper. Only ONE parameter is fitted per run; everything
else comes from the paper or from documented assumptions (see docs/METHODOLOGY.md).

Nodes per cell
  cell :  m_c c_c dTc/dt = Q(t) - G (Tc - Tp)              [with PCM]
          m_c c_c dTc/dt = Q(t) - h A_c (Tc - Ta)           [no PCM]
  pcm  :  dH/dt          = G (Tc - Tp) - h_out A_out (Tp - Ta)
          Tp = f(H)  (enthalpy method, linear melt over [Tm - w, Tm + w])
"""
from __future__ import annotations

from dataclasses import dataclass, field
import numpy as np


@dataclass
class CellThermal:
    mass_kg: float
    cp: float
    area_m2: float


@dataclass
class PCMThermal:
    pcm_mass_kg: float
    latent_j_per_kg: float
    melt_c: float
    melt_halfwidth_c: float = 1.0
    cp_solid_liquid: float = 2000.0       # paraffin, J/kgK (typical)
    foam_mass_kg: float = 0.0
    foam_cp: float = 385.0                 # copper
    outer_area_m2: float = 0.005

    @property
    def sensible_cap(self) -> float:
        return self.pcm_mass_kg * self.cp_solid_liquid + self.foam_mass_kg * self.foam_cp

    @property
    def latent_cap(self) -> float:
        return self.pcm_mass_kg * self.latent_j_per_kg


@dataclass
class RunSpec:
    cell: CellThermal
    c_rate: float
    ambient_c: float
    t_start_c: float
    dod: float = 1.0
    rest_s: float = 600.0
    dt_s: float = 1.0
    log_every_s: float = 10.0
    heat_w: float = 1.0                  # per-cell mean heat generation during discharge
    h_conv: float = 10.0                 # W/m2K cell (no-PCM) convection
    pcm: PCMThermal | None = None
    G_w_per_k: float = 3.0               # cell->composite conductance
    h_out: float = 10.0                  # composite outer surface convection
    cell_factors: np.ndarray = field(default_factory=lambda: np.ones(1))  # per-cell heat multipliers
    h_factors: np.ndarray | None = None  # per-cell cooling multipliers
    path_scale: float = 1.0              # lambda: multiplies G and h_out together (fitted for PCM runs)

    @property
    def discharge_s(self) -> float:
        return self.dod * 3600.0 / self.c_rate


def _pcm_temp(H, pcm: PCMThermal, Tref):
    """Invert enthalpy (J, relative to Tref, all solid) -> temperature."""
    S, L = pcm.sensible_cap, pcm.latent_cap
    T1 = pcm.melt_c - pcm.melt_halfwidth_c
    T2 = pcm.melt_c + pcm.melt_halfwidth_c
    H1 = S * (T1 - Tref)
    H2 = S * (T2 - Tref) + L
    T = np.where(
        H <= H1, Tref + H / S,
        np.where(H >= H2, T2 + (H - H2) / S,
                 T1 + (H - H1) / (S + L / (T2 - T1))))
    frac = np.clip((T - T1) / (T2 - T1), 0.0, 1.0)
    return T, frac


def simulate(spec: RunSpec):
    n = len(spec.cell_factors)
    hf = spec.h_factors if spec.h_factors is not None else np.ones(n)
    C_c = spec.cell.mass_kg * spec.cell.cp
    Ta, Tref = spec.ambient_c, spec.t_start_c
    Tc = np.full(n, spec.t_start_c, dtype=float)
    H = np.zeros(n)
    total = spec.discharge_s + spec.rest_s
    steps = int(round(total / spec.dt_s))
    every = max(1, int(round(spec.log_every_s / spec.dt_s)))
    out_t, out_T, out_f, out_q = [], [], [], []
    for k in range(steps + 1):
        t = k * spec.dt_s
        discharging = t < spec.discharge_s
        Q = spec.heat_w * spec.cell_factors if discharging else np.zeros(n)
        if spec.pcm is not None:
            Tp, frac = _pcm_temp(H, spec.pcm, Tref)
        else:
            Tp, frac = None, np.zeros(n)
        if k % every == 0:
            out_t.append(t); out_T.append(Tc.copy()); out_f.append(frac.copy()); out_q.append(Q.copy())
        if k == steps:
            break
        if spec.pcm is None:
            dTc = (Q - spec.h_conv * hf * spec.cell.area_m2 * (Tc - Ta)) / C_c
        else:
            # exact two-node relaxation for cell<->composite exchange (stable for any G)
            p = spec.pcm
            in_melt = (frac > 0) & (frac < 1)
            C_p = np.where(in_melt, p.sensible_cap + p.latent_cap / (2 * p.melt_halfwidth_c), p.sensible_cap)
            inv = 1.0 / C_c + 1.0 / C_p
            lam = spec.path_scale
            E = (Tc - Tp) * (1 - np.exp(-lam * spec.G_w_per_k * spec.dt_s * inv)) / inv
            H = H + E - spec.dt_s * lam * spec.h_out * hf * p.outer_area_m2 * (Tp - Ta)
            dTc = (Q * spec.dt_s - E) / C_c / spec.dt_s
        Tc = Tc + spec.dt_s * dTc
    return (np.array(out_t), np.array(out_T), np.array(out_f), np.array(out_q))


def peak(spec: RunSpec) -> float:
    _, T, _, _ = simulate(spec)
    return float(T.max())


def max_spread(spec: RunSpec) -> float:
    _, T, _, _ = simulate(spec)
    return float((T.max(axis=1) - T.min(axis=1)).max())


def calibrate(spec: RunSpec, attr: str, target: float, lo: float, hi: float,
              increasing: bool, tol: float = 0.02, it: int = 60) -> float:
    """Bisection on one RunSpec attribute so that the simulated peak == target."""
    def f(x):
        setattr(spec, attr, x)
        return peak(spec) - target
    flo, fhi = f(lo), f(hi)
    if np.sign(flo) == np.sign(fhi):
        raise ValueError(f"target {target} not bracketed for {attr} in [{lo},{hi}] -> {flo+target:.2f},{fhi+target:.2f}")
    for _ in range(it):
        mid = np.sqrt(lo * hi) if lo > 0 else 0.5 * (lo + hi)
        fm = f(mid)
        if abs(fm) < tol:
            break
        if (fm > 0) == increasing:
            hi = mid
        else:
            lo = mid
    setattr(spec, attr, mid)
    return mid
