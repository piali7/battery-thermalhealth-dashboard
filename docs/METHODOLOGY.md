# Methodology, data provenance and limits

## 1. Sources

| ID | Study | What was used |
|---|---|---|
| S1 | He S. et al. 2025, *Materials* 18(19):4604, doi:10.3390/ma18194604 (open access, PMC12526344) | Sanyo 18650 (3.2 Ah) single cell and 2S2P 2×2 module, 25 °C chamber, 1C/2C/3C. Natural convection vs LMA-encapsulated copper foam/paraffin at 10/20/30 PPI. Peak temperatures (cell and module), module ΔT, foam porosity, impregnation, conductivity, paraffin melting point & latent heat. |
| S2 | Wang Z. et al. 2017, *RSC Advances* 7:27441, doi:10.1039/c7ra03963h | 26650 / 42110 / prismatic LFP cells; natural-convection peaks for 26650; upper-bound peaks with copper foam/paraffin at 5C (insulated). |
| S3 | Sun Z. et al. 2023, *Int. J. Thermofluids* 17:100255, doi:10.1016/j.ijft.2022.100255 | 4×4 module of 21700 thermal dummy cells; pure PCM vs copper foam/PCM at 3C, 60% DoD; uniformity bounds (abstract values). |
| S4 | Wang X. et al. 2018, *Energy* 156:154-168 (White Rose eprint 141655) | 12-cell LTO pouch pack; copper foam/n-eicosane composite vs natural convection at 28/35/42 °C; cycle peaks (simulation, flagged). |
| S5 | Hussain A. et al. 2016, *Energy* 115:209-218 | Nickel foam/paraffin, relative reductions only. |
| S6 | *Energy Sources Part A* 2023, doi:10.1080/15567036.2023.2171515 | Nickel and copper foam/paraffin on NCR18650B, relative reductions only. |

Each row in `reported_measurements.csv` stores the value, unit, qualifier (`=` or `<=` for an upper
bound), basis (`reported`, `derived_from_reported`, `simulation_reported`) and a note on where in the
paper it came from. Two S1 module baselines (1C, 2C) are **derived** = F1 value + the reduction the
paper states; the 3C baseline (75.9 °C) is stated directly.

## 2. Why some curves are reconstructed

Papers publish figures, not raw logs, and figure digitising was not possible here. So the project
separates **what was measured** (published numbers) from **what is modelled** (time series between
them), and records the link in `fact_run.anchor_meas_id`.

### Model
Per cell, two nodes:

* cell: `m·c·dTc/dt = Q − G·(Tc − Tp)` (no PCM: `Q − h·A·(Tc − Ta)`)
* composite: `dH/dt = G·(Tc − Tp) − h_out·A_out·(Tp − Ta)`, temperature from enthalpy with a linear
  melt over the paraffin's melting range (42 ± 1 °C for S1).

Exchange between nodes uses an exact two-node relaxation, so the solver is stable for any conductance.

### Calibration chain (one fitted parameter per run)
1. Single cell, no PCM → fit heat generation `Q` (h = 10 W/m²K assumed, typical natural convection).
2. Single cell, foam/PCM → reuse `Q`; `G0 = 2πkL/ln(r2/r1)` from the **measured** foam conductivity
   (4.42 W/m·K at 10 PPI, 2.89 at 30 PPI, 20 PPI interpolated); fit one scale λ applied to both G0 and h_out.
3. Module, no PCM → reuse `Q`; fit effective h, then a cell-to-cell heat spread to match the published ΔT.
4. Module, 10 PPI foam/PCM → reuse `Q`; fit λ and spread.

Result: all 18 runs match their published peaks within 0.05 °C and all 6 module runs match published
ΔT within 0.05 °C (enforced as blocking DQ checks and unit tests).

### Assumptions (stated, not hidden)
* 18650 mass 46 g and cp 1000 J/kg·K (typical values; the paper does not give them).
* Composite volume per cell = module block (52×52×65 mm) / 4 minus cell volume; paraffin density 800 kg/m³.
* Fitted λ varies with C-rate (≈1 at 1C, ≈0.1–0.2 at 3C). It absorbs everything the lumped model
  doesn't capture (true sleeve geometry, contact resistance, encapsulation layer), so read it as a
  fitting factor, not a material property. Curve *shapes* are therefore indicative; *peaks and ΔT are exact.*

## 3. Data-quality gate (sample of checks)
Primary-key uniqueness for every table · foreign keys measurement→source/pack/material · temperature
0–120 °C, ΔT 0–30 °C, C-rate 0.1–10 · every source has a DOI or URL · metal-foam peak ≤ baseline peak
(same pack, rate, ambient; WARN) · reconstruction peak and ΔT within 0.05 °C (FAIL) · no null
temperatures, unique log grain · post-load SQLite foreign_key_check · every run scored by the KPI view.
For lab logs: unknown pack/material (FAIL), duplicate samples (FAIL, deduplicated), out-of-range temps (WARN, dropped).

## 4. Known limits
* No open study gave a complete data set for a 3×2 or 4×2 module; the 2×2 (S1) and 4×4 (S3) are the closest.
  Your lab 4×2 data is the intended way to fill this.
* S1 module tests reported only the 10 PPI composite; 20/30 PPI exist for the single cell only.
* S2: ambient not stated; foam case insulated while baseline was open air, so its comparison is conservative.
* S3: values from the abstract; the abstract's wording calls 57.4 → 51.4 °C the "maximum temperature rise".
* S4 cycle peaks are simulations in that paper and are flagged `simulation_reported`.
