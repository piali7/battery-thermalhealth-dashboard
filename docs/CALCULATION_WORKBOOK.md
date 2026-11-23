# Calculation Workbook

Every calculation behind the dashboard, with inputs, formulas and worked numbers, so each figure can be checked by hand or in Excel.

| Kind of number | What it is | How to verify |
| --- | --- | --- |
| Published | Values copied from papers (Section 2) | Compare with the paper |
| Derived by arithmetic | Geometry, masses, KPIs, reductions (Sections 3, 6, 7) | Re-do the arithmetic shown |
| Model-calibrated | Fitted parameters and time curves (Sections 4, 5) | Each simulated peak equals its published target within 0.05 °C; re-run `python run_pipeline.py` |

## 1. Input data (published values)

All 18 model runs are anchored to [He et al. 2025, *Materials* 18(19):4604](https://pmc.ncbi.nlm.nih.gov/articles/PMC12526344/): Sanyo 18650 (3.2 Ah), 25 °C chamber, 2S2P module of four cells (52 × 52 × 65 mm). F1/F2/F3 = copper foam at 10/20/30 PPI filled with paraffin, sealed with a low-melting alloy.

**Peak temperature, °C**

| Configuration | Cooling | 1C | 2C | 3C |
| --- | --- | --- | --- | --- |
| Single cell | No PCM | 36.1 | 46.2 | 59.3 |
| Single cell | F3, 30 PPI | 34.3 | 44.3 | 50.3 |
| Single cell | F2, 20 PPI | 33.9 | 42.9 | 48.5 |
| Single cell | F1, 10 PPI | 33.5 | 42.7 | 47.9 |
| 2×2 module | No PCM | 38.9* | 59.6* | 75.9 |
| 2×2 module | F1, 10 PPI | 35.5 | 41.0 | 44.6 |

\*Derived: F1 value + the drop the paper states (3.4, 18.6 °C). The 3C value is stated directly (44.6 + 31.3 = 75.9 checks).

**Module max cell-to-cell difference ΔT, °C:** no PCM 2.9 / 6.3 / 10.2; F1 0.3 / 1.1 / 1.2 (1C / 2C / 3C).

**Materials:** porosity 0.935 / 0.955 / 0.965; impregnation 98.658% / 93.670% / 88.731%; paraffin melts at 42 °C, latent heat 220 J/g; conductivity 4.42 / 3.66 / 2.89 W/m·K (F2 interpolated: 4.42 + (2.89 − 4.42) × 10/20 = 3.655).

## 2. Geometry and materials

Assumed (not in the paper): cell mass 46 g, cell cp 1000 J/kg·K, paraffin 800 kg/m³ and 2000 J/kg·K, copper 8960 kg/m³ and 385 J/kg·K, h = 10 W/m²·K.

$$A_{cell} = \pi d L + 2\pi r^2 = \pi(0.018)(0.065) + 2\pi(0.009)^2 = 0.004185\ \text{m}^2$$

$$V_{sleeve} = \frac{0.052 \times 0.052 \times 0.065}{4} - \pi(0.009)^2(0.065) = 4.394\times10^{-5} - 1.654\times10^{-5} = 2.740\times10^{-5}\ \text{m}^3$$

$$m_{paraffin} = V_{sleeve}\,\varepsilon\,\rho_{paraffin}\,\eta \qquad m_{Cu} = V_{sleeve}(1-\varepsilon)\,\rho_{Cu}$$

$$S = m_{paraffin} c_{paraffin} + m_{Cu} c_{Cu} \qquad L = m_{paraffin} \times 220\ \text{J/g} \qquad G_0 = \frac{2\pi k L_{cell}}{\ln(r_2/r_1)} = \frac{2\pi k (0.065)}{\ln(14.67/9)}$$

Worked F1: paraffin 2.740×10⁻⁵ × 0.935 × 800 × 0.98658 = 20.22 g; copper 2.740×10⁻⁵ × 0.065 × 8960 = 15.96 g; G₀ = 2π × 4.42 × 0.065 / 0.4885 = 3.695 W/K.

| Quantity | F1 | F2 | F3 |
| --- | --- | --- | --- |
| Paraffin mass, g | 20.22 | 19.61 | 18.77 |
| Copper mass, g | 15.96 | 11.05 | 8.59 |
| Sensible capacity S, J/K | 46.57 | 43.47 | 40.84 |
| Latent capacity L, J | 4,447 | 4,314 | 4,129 |
| Conductance G₀, W/K | 3.695 | 3.056 | 2.416 |

## 3. Thermal model

$$m c \frac{dT_c}{dt} = Q - h A_{cell}(T_c - T_a) \quad \text{(no PCM)}$$

$$m c \frac{dT_c}{dt} = Q - \lambda G_0 (T_c - T_p) \qquad \frac{dH}{dt} = \lambda G_0 (T_c - T_p) - \lambda h_{out} A_{out} (T_p - T_a) \quad \text{(foam/PCM)}$$

Composite temperature comes from enthalpy with the melt spread over 41–43 °C; liquid fraction = (T_p − 41)/2, clipped to 0–1. Discharge lasts 3600/C s, followed by a 600 s rest. In modules each cell's heat is Q(1 + s·wᵢ) with w = (1, ⅓, −⅓, −1), and s is fitted to the published ΔT.

## 4. Calibration (one fitted parameter per run)

1. Single cell, no PCM: fit Q (h = 10 W/m²·K).
2. Single cell, foam: reuse Q, fit λ.
3. Module, no PCM: reuse Q, fit effective h, then spread s.
4. Module, F1: reuse Q, fit λ, then spread s.

**Hand check of step 1** (exact solution, τ = 46 / (10 × 0.004185) = 1099.3 s):

$$T_c(t) = T_a + \frac{Q}{hA}\left(1 - e^{-t/\tau}\right)$$

| C-rate | Fitted Q, W | Q/(hA), °C | 1 − e^(−t/τ) | Peak, °C | Published, °C |
| --- | --- | --- | --- | --- | --- |
| 1C | 0.4823 | 11.526 | 0.9622 | 36.09 | 36.1 |
| 2C | 1.1011 | 26.313 | 0.8055 | 46.20 | 46.2 |
| 3C | 2.1599 | 51.615 | 0.6643 | 59.29 | 59.3 |

| Run | Fitted | Value | Spread s | Target °C | Simulated °C | Target ΔT | Simulated ΔT |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Cell F1/F2/F3, 1C | λ | 1.037 / 0.982 / 0.939 | — | 33.5 / 33.9 / 34.3 | 33.485 / 33.917 / 34.312 | — | — |
| Module no PCM, 1C | h | 8.739 | 0.1165 | 38.9 | 38.897 | 2.9 | 2.900 |
| Module F1, 1C | λ | 0.743 | 0.0145 | 35.5 | 35.507 | 0.3 | 0.300 |
| Cell F1/F2/F3, 2C | λ | 0.184 / 0.202 / 0.140 | — | 42.7 / 42.9 / 44.3 | 42.716 / 42.897 / 44.297 | — | — |
| Module no PCM, 2C | h | 4.081 | 0.1002 | 59.6 | 59.590 | 6.3 | 6.300 |
| Module F1, 2C | λ | 0.788 | 0.0356 | 41.0 | 41.002 | 1.1 | 1.100 |
| Cell F1/F2/F3, 3C | λ | 0.085 / 0.094 / 0.093 | — | 47.9 / 48.5 / 50.3 | 47.901 / 48.506 / 50.295 | — | — |
| Module no PCM, 3C | h | 3.943 | 0.1113 | 75.9 | 75.900 | 10.2 | 10.196 |
| Module F1, 3C | λ | 0.188 | 0.0350 | 44.6 | 44.591 | 1.2 | 1.200 |

λ is a fitting factor that absorbs what the lumped model leaves out. Peaks and spreads are exact; curve shapes are indicative.

## 5. KPIs and Thermal Health Index

Thresholds: optimal ≤ 35 °C, warning 45 °C, critical 60 °C, ΔT limit 5 °C.

$$P = \text{clip}\left(100 \cdot \frac{60 - T_{peak}}{25}\right) \qquad U = \text{clip}\left(100 \cdot \left(1 - \frac{\Delta T}{10}\right)\right) \qquad E = 100 \cdot \left(1 - \frac{t_{>45}}{t_{total}}\right)$$

$$THI = 0.5P + 0.2E + 0.3U \ \ \text{(module)} \qquad THI = \frac{0.5P + 0.2E}{0.7} \ \ \text{(single cell)}$$

Bands: Healthy ≥ 75, Watch 50–75, Critical < 50.

- **Module, F1, 3C:** P = 100 × (60 − 44.591)/25 = 61.64; U = 100 × (1 − 1.2/10) = 88.0; E = 100 → THI = 30.82 + 20.00 + 26.40 = **77.2**
- **Module, no PCM, 3C:** P → 0; U → 0; E = 100 × (1 − 1380/1800) = 23.33 → THI = **4.7**
- **Cell, F1, 3C:** P = 48.40; E = 100 × (1 − 490/1800) = 72.78 → THI = (24.20 + 14.56)/0.7 = **55.4**

## 6. Foam effectiveness

$$\text{Reduction} = T_{base} - T_{foam} \qquad \text{Rise suppression} = \frac{T_{base} - T_{foam}}{T_{base} - 25}$$

Module, 3C: 75.9 − 44.6 = 31.3 °C (41.2%); rise suppression 31.3/50.9 = 61.5%.

| Other studies | Condition | Baseline °C | Foam °C | Reduction |
| --- | --- | --- | --- | --- |
| [Wang Z. et al. 2017](https://pubs.rsc.org/en/content/articlehtml/2017/ra/c7ra03963h), 26650 cell | 5C | 62.77 (no PCM) | ≤ 44.37 | ≥ 18.4 °C |
| [Sun et al. 2023](https://pureportal.coventry.ac.uk/en/publications/experimental-study-of-battery-passive-thermal-management-system-u/), 4×4 module | 3C, 60% DoD | 57.4 (pure PCM) | 51.4 | 6.0 °C (10.5%) |
| [Wang X. et al. 2018](https://eprints.whiterose.ac.uk/141655/), LTO pack | 4C, 35 °C | 51.3 (no PCM) | 43.0 | 8.3 °C |

The full per-run tables are in the warehouse views `vw_run_kpi` and `vw_foam_effectiveness_runs`.
