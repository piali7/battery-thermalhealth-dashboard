"""EXPORT for the web dashboard: compact, display-ready datasets computed in SQL.
Model-derived sets are JSON {rows, meta} carrying the code that made them (lineage)."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd

from .config import WAREHOUSE_DB, ROOT

OUT = ROOT / "data" / "exports" / "dashboard"

SCORECARD = """
SELECT k.run_id, k.pack_scale, k.pack_label, k.layout, k.tms_family,
       CASE WHEN k.tms_family = 'NO_PCM' THEN 'No PCM (natural convection)'
            ELSE 'Cu foam ' || k.foam_ppi || ' PPI + paraffin' END            AS tms_short,
       k.foam_ppi, CAST(k.c_rate AS INTEGER) AS c_rate,
       ROUND(k.peak_c, 1)               AS peak_c,
       ROUND(k.dt_max_c, 1)             AS dt_max_c,
       ROUND(k.s_above_warn / 60.0, 1)  AS min_above_45,
       ROUND(k.s_above_crit / 60.0, 1)  AS min_above_60,
       ROUND(k.max_liquid_frac * 100)   AS pct_pcm_melted,
       ROUND(k.max_rise_c_per_min, 2)   AS max_rise_c_per_min,
       k.thermal_health_index           AS thi,
       k.health_band,
       ROUND(e.baseline_peak_c, 1)      AS baseline_peak_c,
       ROUND(e.peak_reduction_c, 1)     AS peak_reduction_c,
       ROUND(e.baseline_dt_c, 1)        AS baseline_dt_c,
       ROUND(e.baseline_s_above_warn / 60.0, 1) AS baseline_min_above_45,
       e.baseline_thi, e.thi_gain,
       k.anchor_meas_id, m.value        AS published_peak_c,
       k.calib_param, ROUND(k.calib_value, 4) AS calib_value, k.data_origin
FROM vw_run_kpi k
LEFT JOIN vw_foam_effectiveness_runs e ON e.run_id = k.run_id
LEFT JOIN fact_reported_measurement m ON m.meas_id = substr(k.anchor_meas_id, 1, 4)
ORDER BY k.pack_scale DESC, k.c_rate, k.tms_family DESC, k.foam_ppi
"""

TIMESERIES = """
SELECT r.run_id, ROUND(s.t_s / 60.0, 2) AS t_min,
       ROUND(s.t_hot_c, 2) AS hot_c, ROUND(s.spread_c, 2) AS spread_c,
       ROUND(MAX(l.pcm_liquid_frac) * 100, 1) AS pct_pcm_melted
FROM vw_run_spread_ts s
JOIN fact_run r USING(run_key)
JOIN fact_thermal_log l ON l.run_key = s.run_key AND l.t_s = s.t_s
WHERE s.t_s % 30 = 0
GROUP BY r.run_id, s.t_s
ORDER BY r.run_id, s.t_s
"""

EVIDENCE = """
SELECT v.short_cite, v.pack_label, v.foam_tms,
       v.baseline_tms, CAST(v.c_rate AS INTEGER) AS c_rate, v.ambient_c,
       v.baseline_env, v.foam_env, v.baseline_t_max_c, v.foam_t_max_c, v.t_max_qualifier,
       v.peak_reduction_c, v.peak_reduction_pct, v.baseline_dt_c, v.foam_dt_c, v.evidence,
       v.short_cite || ' | ' || v.pack_label || ' | ' || v.foam_tms || ' | ' || CAST(v.c_rate AS INTEGER) || 'C'
           || COALESCE(' | ' || CAST(v.ambient_c AS INTEGER) || ' °C', '')  AS row_label
FROM vw_reported_foam_vs_baseline v
ORDER BY v.peak_reduction_c DESC
"""

RELATIVE = """
SELECT s.short_cite, p.pack_label, t.tms_label AS foam_tms, b.tms_label AS baseline_tms,
       CAST(r.c_rate AS INTEGER) AS c_rate, r.reduction_pct, r.note,
       r.rel_id
FROM fact_reported_relative r JOIN dim_source s USING(source_key) JOIN dim_pack p USING(pack_key)
JOIN dim_tms t ON t.tms_key = r.tms_key JOIN dim_tms b ON b.tms_key = r.baseline_tms_key
ORDER BY r.rel_id
"""

SOURCES = "SELECT source_id, short_cite, title, journal, year, doi, open_url, study_type, notes FROM dim_source"
DQ = """SELECT check_name, target_table, status, failed_rows FROM dq_check_result
        WHERE batch_id = (SELECT MAX(batch_id) FROM etl_batch) ORDER BY status DESC, check_name"""


def export_dashboard() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(WAREHOUSE_DB)
    batch = con.execute("SELECT batch_id FROM etl_batch ORDER BY started_at DESC LIMIT 1").fetchone()[0]
    code = lambda p: (ROOT / p).read_text()
    lineage = [
        {"label": "Pipeline batch", "value": batch},
        {"label": "Warehouse", "value": "data/warehouse/battery_thermal_dw.sqlite (views vw_run_kpi, vw_foam_effectiveness_runs)"},
        {"label": "Anchored to", "value": "He et al. 2025, Materials 18(19):4604, doi 10.3390/ma18194604 — every run's peak (and module dT) equals the published value"},
        {"label": "thermal_model.py", "value": code("etl/thermal_model.py"), "type": "code", "lang": "python"},
        {"label": "reconstruct.py", "value": code("etl/reconstruct.py"), "type": "code", "lang": "python"},
    ]
    sizes = {}
    for name, sql, as_json in [("scorecard", SCORECARD, True), ("timeseries", TIMESERIES, True),
                               ("evidence", EVIDENCE, False), ("relative", RELATIVE, False),
                               ("sources", SOURCES, False), ("dq", DQ, False)]:
        df = pd.read_sql_query(sql, con)
        if as_json:
            meta = lineage + [{"label": "Query", "value": sql.strip(), "type": "code", "lang": "sql"}]
            rows = json.loads(df.to_json(orient="records"))      # NaN -> null
            (OUT / f"{name}.json").write_text(json.dumps({"rows": rows, "meta": meta}))
        else:
            df.to_csv(OUT / f"{name}.csv", index=False)
        sizes[name] = len(df)
    con.close()
    return sizes
