# Building the dashboard in Tableau

## Connect
1. Tableau Desktop → **Connect → More… → Tableau Extract (.hyper)** (or "To a File → More…") →
   `data/exports/tableau/battery_thermal_health.hyper`.
2. The extract holds these tables (schema `Extract`): `run_kpi`, `foam_effectiveness_runs`,
   `thermal_log`, `spread_ts`, `reported_kpi`, `reported_foam_vs_baseline`, `reported_relative`,
   `sources`, `dq_check_result`. The same tables are in the folder as CSVs if you prefer Text File connections.
3. Relationships (drag onto canvas): `thermal_log.run_id = run_kpi.run_id`, `spread_ts.run_id = run_kpi.run_id`.

## Suggested sheets
| Sheet | Build |
|---|---|
| KPI tiles | `run_kpi`; filter `tms_family = METAL_FOAM_PCM`, `foam_ppi = 10`; text marks: `peak_c`, `dt_max_c`, `thermal_health_index` |
| Temperature trace | `thermal_log`: Columns `t_min`, Rows `MAX(temp_c)`, Color `tms_label`, Filter `c_rate`, `pack_scale`; reference lines at 45 and 60 |
| Spread trace | `spread_ts`: `t_min` vs `spread_c`, reference line 5 |
| THI scorecard | `run_kpi`: bar `thermal_health_index` by `run_id`, Color `health_band` |
| Published evidence (dumbbell) | `reported_foam_vs_baseline`: Measure Values `baseline_t_max_c`, `foam_t_max_c` on Columns (dual axis circle + line), Rows `short_cite`, `pack_label`, `c_rate` |
| PPI effect | `run_kpi` or `reported_kpi`: `foam_ppi` × `c_rate`, measure `t_max_c` |
| Data quality | `dq_check_result`: count by `status` |

## Useful calculated fields
```
// Health band colour order
CASE [health_band] WHEN 'Healthy' THEN 1 WHEN 'Watch' THEN 2 ELSE 3 END

// Minutes above warning
[s_above_warn] / 60

// Peak status vs thresholds
IF [peak_c] >= 60 THEN 'Critical' ELSEIF [peak_c] >= 45 THEN 'Warning'
ELSEIF [peak_c] > 35 THEN 'Elevated' ELSE 'Optimal' END
```

Add the **C-rate** and **pack_scale** filters to all sheets ("Apply to worksheets → All using this data source")
to reproduce the web dashboard's selectors. When your lab logs are loaded, add `data_origin` as a filter
or colour to compare lab-measured vs literature runs.
