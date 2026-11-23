# Drop your lab logs here

Any `*.csv` file in this folder (not starting with `_`) is picked up by `python run_pipeline.py`
and loaded into the warehouse as `data_origin = 'lab_measured'`, side by side with the
literature data. All KPIs, the Thermal Health Index and the Tableau extracts update automatically.

## Required columns (long format: one row = one thermocouple reading)

| column | example | meaning |
|---|---|---|
| run_id | LAB_4x2_CFPCM_3C_R1 | unique id of one test run |
| pack_id | MOD18650_4x2_LAB | must exist in `data/raw/literature/packs.csv` (add a row for your pack) |
| material_id | M_LAB_CF_PA | must exist in `data/raw/literature/tms_materials.csv` (add a row) |
| c_rate | 3 | discharge C-rate |
| ambient_c | 25 | chamber / room temperature, °C |
| cell_id | C3_R1C3 | sensor/cell name; use `R<row>C<col>` so position is parsed |
| t_s | 120 | seconds since start of the run |
| temp_c | 41.7 | measured temperature, °C |

Optional: `dod_pct`, `phase` (discharge/rest/charge), `pcm_liquid_frac`, `heat_w`.

## If your logger exports wide format (one column per thermocouple)

```python
import pandas as pd
w = pd.read_csv("logger_export.csv")             # columns: time_s, T1, T2, ... T8
long = w.melt(id_vars="time_s", var_name="cell_id", value_name="temp_c").rename(columns={"time_s": "t_s"})
long = long.assign(run_id="LAB_4x2_CFPCM_3C_R1", pack_id="MOD18650_4x2_LAB",
                   material_id="M_LAB_CF_PA", c_rate=3, ambient_c=25)
long.to_csv("data/raw/lab_logs/LAB_4x2_CFPCM_3C_R1.csv", index=False)
```

See `_TEMPLATE_lab_log.csv` for the exact header. Files beginning with `_` are ignored.
