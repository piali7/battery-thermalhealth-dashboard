"""EXPORT: Tableau-ready extracts (CSV + optional .hyper) from the warehouse views."""
from __future__ import annotations

import sqlite3
import pandas as pd

from .config import WAREHOUSE_DB, EXPORTS

EXTRACTS = {
    "run_kpi": "SELECT * FROM vw_run_kpi ORDER BY pack_scale, c_rate, tms_family, foam_ppi",
    "foam_effectiveness_runs": "SELECT * FROM vw_foam_effectiveness_runs ORDER BY pack_label, c_rate, foam_ppi",
    "reported_kpi": "SELECT * FROM vw_reported_kpi ORDER BY source_id, pack_id, c_rate",
    "reported_foam_vs_baseline": "SELECT * FROM vw_reported_foam_vs_baseline",
    "reported_relative": """
        SELECT s.short_cite, p.pack_label, t.tms_label, b.tms_label AS baseline_tms, r.c_rate,
               r.metric_code, r.reduction_pct, r.value_basis, r.note
        FROM fact_reported_relative r JOIN dim_source s USING(source_key) JOIN dim_pack p USING(pack_key)
        JOIN dim_tms t ON t.tms_key = r.tms_key JOIN dim_tms b ON b.tms_key = r.baseline_tms_key""",
    "thermal_log": """
        SELECT r.run_id, r.data_origin, p.pack_label, p.pack_scale, t.tms_code, t.tms_label, t.tms_family,
               t.foam_ppi, c.c_rate, c.ambient_c, ce.cell_id, l.t_s, ROUND(l.t_s / 60.0, 2) AS t_min,
               l.temp_c, l.pcm_liquid_frac, l.heat_w, l.phase
        FROM fact_thermal_log l JOIN fact_run r USING(run_key) JOIN dim_pack p ON p.pack_key = r.pack_key
        JOIN dim_tms t ON t.tms_key = r.tms_key JOIN dim_condition c ON c.condition_key = r.condition_key
        JOIN dim_cell ce ON ce.cell_key = l.cell_key""",
    "spread_ts": """
        SELECT r.run_id, s.t_s, ROUND(s.t_s/60.0,2) AS t_min, s.t_hot_c, s.t_cold_c,
               ROUND(s.t_avg_c,3) AS t_avg_c, ROUND(s.spread_c,3) AS spread_c
        FROM vw_run_spread_ts s JOIN fact_run r USING(run_key)""",
    "sources": "SELECT * FROM dim_source",
    "dq_check_result": "SELECT * FROM dq_check_result",
}


def export():
    EXPORTS.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(WAREHOUSE_DB)
    frames = {k: pd.read_sql_query(q, con) for k, q in EXTRACTS.items()}
    con.close()
    for k, df in frames.items():
        df.to_csv(EXPORTS / f"{k}.csv", index=False)
    hyper = _write_hyper(frames)
    return {k: len(v) for k, v in frames.items()}, hyper


def _write_hyper(frames):
    try:
        from tableauhyperapi import (HyperProcess, Telemetry, Connection, CreateMode,
                                     TableDefinition, SqlType, Inserter, TableName)
    except ImportError:
        return None
    path = EXPORTS / "battery_thermal_health.hyper"
    if path.exists():
        path.unlink()

    def sqltype(s):
        if pd.api.types.is_integer_dtype(s): return SqlType.big_int()
        if pd.api.types.is_float_dtype(s): return SqlType.double()
        return SqlType.text()

    with HyperProcess(Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU) as hp:
        with Connection(hp.endpoint, str(path), CreateMode.CREATE_AND_REPLACE) as conn:
            conn.catalog.create_schema("Extract")
            for name, df in frames.items():
                td = TableDefinition(TableName("Extract", name),
                                     [TableDefinition.Column(c, sqltype(df[c])) for c in df.columns])
                conn.catalog.create_table(td)
                rows = df.astype(object).where(pd.notna(df), None).itertuples(index=False, name=None)
                with Inserter(conn, td) as ins:
                    ins.add_rows(rows); ins.execute()
    return path
