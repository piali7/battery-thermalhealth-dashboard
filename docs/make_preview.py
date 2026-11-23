"""Render docs/dashboard_preview.png from the warehouse (run after run_pipeline.py).

    python docs/make_preview.py
"""
import sqlite3
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "warehouse" / "battery_thermal_dw.sqlite"
OUT = ROOT / "docs" / "dashboard_preview.png"

SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
FOAM, NOPCM = "#2a78d6", "#eb6834"                      # categorical slots 1, 2
BAND = {"Healthy": "#0ca30c", "Watch": "#fab219", "Critical": "#d03b3b"}

con = sqlite3.connect(DB)
k = pd.read_sql("SELECT * FROM vw_run_kpi", con).set_index("run_id")
ts = pd.read_sql("""SELECT r.run_id, s.t_s/60.0 AS t_min, s.t_hot_c
                    FROM vw_run_spread_ts s JOIN fact_run r USING(run_key)
                    WHERE r.run_id IN ('S1_MOD_NC_3C','S1_MOD_CF_PA_10PPI_3C')""", con)
con.close()

plt.rcParams.update({"font.family": "DejaVu Sans", "text.color": INK, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "axes.edgecolor": GRID})
fig = plt.figure(figsize=(16, 9.6), dpi=110, facecolor=SURFACE)
fig.text(0.04, 0.95, "Battery Thermal Health Monitor — Metal Foam / PCM", fontsize=22, weight="bold")
fig.text(0.04, 0.915, "2×2 module of 18650 cells, 3C discharge, 25 °C. Peaks and spreads from He et al. 2025 (Materials); "
         "curves from a thermal model calibrated to them.", fontsize=11.5, color=INK2)

# ---- KPI tiles: 10 PPI copper foam vs no PCM
f, b = k.loc["S1_MOD_CF_PA_10PPI_3C"], k.loc["S1_MOD_NC_3C"]
tiles = [("Peak cell temperature", f"{f.peak_c:.1f} °C", f"vs {b.peak_c:.1f} °C no PCM"),
         ("Cell-to-cell spread", f"{f.dt_max_c:.1f} °C", f"vs {b.dt_max_c:.1f} °C no PCM"),
         ("Time above 45 °C", f"{f.s_above_warn/60:.1f} min", f"vs {b.s_above_warn/60:.1f} min no PCM"),
         ("Thermal Health Index", f"{f.thermal_health_index:.1f}", f"vs {b.thermal_health_index:.1f} no PCM")]
for i, (lab, big, cmp_) in enumerate(tiles):
    ax = fig.add_axes([0.04 + i * 0.235, 0.72, 0.215, 0.15])
    ax.set_facecolor("white"); ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color(GRID)
    ax.text(0.06, 0.78, lab, fontsize=12, color=INK2, transform=ax.transAxes)
    ax.text(0.06, 0.38, big, fontsize=28, transform=ax.transAxes)
    ax.text(0.06, 0.12, cmp_, fontsize=11, color=INK2, transform=ax.transAxes)

# ---- Trace chart
ax = fig.add_axes([0.06, 0.08, 0.50, 0.54])
ax.set_facecolor(SURFACE)
for rid, col, lab in [("S1_MOD_NC_3C", NOPCM, "No PCM"), ("S1_MOD_CF_PA_10PPI_3C", FOAM, "Cu foam 10 PPI + paraffin")]:
    d = ts[ts.run_id == rid]
    ax.plot(d.t_min, d.t_hot_c, color=col, lw=2.2, label=lab)
    ax.text(d.t_min.iloc[-1] + 0.3, d.t_hot_c.iloc[-1], lab, color=INK2, fontsize=10, va="center")
ax.axvspan(20, 30, color=GRID, alpha=0.5, lw=0)
ax.text(25, 21.5, "rest", ha="center", fontsize=10, color=INK2)
for v, lab, col in [(45, "45 °C warning", "#8a8984"), (60, "60 °C limit", BAND["Critical"])]:
    ax.axhline(v, ls="--", lw=1, color=col)
    ax.text(0.3, v + 0.8, lab, fontsize=10, color=INK2)
ax.set_xlim(0, 36); ax.set_ylim(20, 80)
ax.set_xlabel("Time (min)"); ax.set_ylabel("Hottest-cell temperature (°C)")
ax.grid(axis="y", color=GRID, lw=0.8); ax.set_axisbelow(True)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
ax.legend(frameon=False, loc="upper left", bbox_to_anchor=(0, 1.08), ncol=2, fontsize=10.5)
ax.set_title("Hottest cell through 3C discharge and rest", loc="left", fontsize=13, pad=26)

# ---- THI board
ax = fig.add_axes([0.70, 0.08, 0.27, 0.54])
ax.set_facecolor(SURFACE)
order = k.sort_values("thermal_health_index")
names = [("Module" if r.pack_scale == "module" else "Cell") + f" · {int(r.c_rate)}C · "
         + ("No PCM" if r.tms_family == "NO_PCM" else f"{int(r.foam_ppi)} PPI foam") for r in order.itertuples()]
ax.barh(names, order.thermal_health_index, color=[BAND[b] for b in order.health_band], height=0.7)
for y, v in enumerate(order.thermal_health_index):
    ax.text(v + 1.5, y, f"{v:.0f}", va="center", fontsize=9, color=INK2)
ax.set_xlim(0, 112); ax.tick_params(axis="y", labelsize=9, length=0)
ax.set_xlabel("Thermal Health Index (0–100)")
for s in ("top", "right", "left"):
    ax.spines[s].set_visible(False)
handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in BAND.values()]
ax.legend(handles, ["Healthy ≥ 75", "Watch 50–75", "Critical < 50"], frameon=False,
          loc="upper left", bbox_to_anchor=(-0.45, 1.08), ncol=3, fontsize=10)
ax.set_title("Health score, all 18 runs", loc="left", fontsize=13, pad=26, x=-0.45)

fig.savefig(OUT, facecolor=SURFACE)
print("wrote", OUT)
