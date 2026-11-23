"""LOAD: (re)build the SQLite warehouse, populate dimensions then facts, store DQ + audit."""
from __future__ import annotations

import sqlite3
import pandas as pd

from .config import WAREHOUSE_DB, SQL_DIR, METRICS


def _keymap(con, table, natural, key):
    return dict(con.execute(f"SELECT {natural}, {key} FROM {table}").fetchall())


def _insert(con, table, df: pd.DataFrame):
    df = df.astype(object).where(pd.notna(df), None)
    cols = ",".join(df.columns); qs = ",".join("?" * len(df.columns))
    con.executemany(f"INSERT INTO {table} ({cols}) VALUES ({qs})", df.itertuples(index=False, name=None))
    return len(df)


def load(t: dict, dq, manifest: pd.DataFrame, batch_id: str, started: str):
    WAREHOUSE_DB.parent.mkdir(parents=True, exist_ok=True)
    if WAREHOUSE_DB.exists():
        WAREHOUSE_DB.unlink()                      # full refresh (small warehouse)
    con = sqlite3.connect(WAREHOUSE_DB)
    con.executescript((SQL_DIR / "01_schema.sql").read_text())
    n = {}

    n["dim_source"] = _insert(con, "dim_source", t["sources"][[
        "source_id", "short_cite", "title", "journal", "year", "volume_pages", "doi", "open_url", "study_type", "notes"]])
    sk = _keymap(con, "dim_source", "source_id", "source_key")

    p = t["packs"].assign(source_key=lambda d: d.source_id.map(sk))
    n["dim_pack"] = _insert(con, "dim_pack", p[[
        "pack_id", "source_key", "pack_label", "pack_scale", "cell_format", "chemistry", "cell_capacity_ah",
        "n_cells", "layout", "electrical_config", "cell_mass_kg", "cell_cp_j_per_kgk", "cell_area_m2",
        "cell_resistance_mohm"]])
    pk = _keymap(con, "dim_pack", "pack_id", "pack_key")

    c = t["cells"].assign(pack_key=lambda d: d.pack_id.map(pk))
    n["dim_cell"] = _insert(con, "dim_cell", c[["pack_key", "cell_id", "row_idx", "col_idx"]])
    ck = {(pid, cid): key for pid, cid, key in con.execute(
        "SELECT p.pack_id, c.cell_id, c.cell_key FROM dim_cell c JOIN dim_pack p USING(pack_key)")}

    m = t["materials"].assign(source_key=lambda d: d.source_id.map(sk))
    n["dim_tms"] = _insert(con, "dim_tms", m[[
        "material_id", "source_key", "tms_code", "tms_label", "tms_family", "foam_metal", "foam_ppi",
        "foam_porosity", "pcm_name", "pcm_melt_c", "pcm_latent_j_per_g", "composite_latent_j_per_g",
        "k_eff_w_per_mk", "pcm_mass_g_per_cell", "foam_mass_g_per_cell", "encapsulation", "basis_note"]])
    tk = _keymap(con, "dim_tms", "material_id", "tms_key")

    cond = t["conditions"].copy()
    cond["condition_label"] = cond.apply(lambda r: " | ".join(filter(None, [
        f"{r.c_rate:g}C" if pd.notna(r.c_rate) else None,
        f"{r.ambient_c:g} °C amb" if pd.notna(r.ambient_c) else "amb n/a",
        f"{r.dod_pct:g}% DoD" if pd.notna(r.dod_pct) else None, r.environment])), axis=1)
    n["dim_condition"] = _insert(con, "dim_condition", cond)

    def cond_key(df):
        keys = []
        for r in df.itertuples():
            row = con.execute(
                "SELECT condition_key FROM dim_condition WHERE c_rate IS ? AND ambient_c IS ? "
                "AND dod_pct IS ? AND environment IS ?",
                [None if pd.isna(v) else float(v) if not isinstance(v, str) else v
                 for v in (r.c_rate, r.ambient_c, r.dod_pct, r.environment)]).fetchone()
            keys.append(row[0])
        return keys

    met = pd.DataFrame([(k, d, u) for k, (d, u) in METRICS.items()], columns=["metric_code", "description", "unit"])
    n["dim_metric"] = _insert(con, "dim_metric", met)
    mk = _keymap(con, "dim_metric", "metric_code", "metric_key")
    n["dim_threshold"] = _insert(con, "dim_threshold", t["thresholds"])

    me = t["measurements"].copy()
    me["source_key"] = me.source_id.map(sk); me["pack_key"] = me.pack_id.map(pk)
    me["tms_key"] = me.material_id.map(tk); me["metric_key"] = me.metric.map(mk)
    me["condition_key"] = cond_key(me); me["batch_id"] = batch_id
    n["fact_reported_measurement"] = _insert(con, "fact_reported_measurement", me[[
        "meas_id", "source_key", "pack_key", "tms_key", "condition_key", "metric_key", "value", "qualifier",
        "value_basis", "location_note", "batch_id"]])

    rl = t["relative"].copy()
    rl = rl.assign(source_key=rl.source_id.map(sk), pack_key=rl.pack_id.map(pk), tms_key=rl.material_id.map(tk),
                   baseline_tms_key=rl.baseline_material_id.map(tk), metric_code=rl.metric, batch_id=batch_id)
    n["fact_reported_relative"] = _insert(con, "fact_reported_relative", rl[[
        "rel_id", "source_key", "pack_key", "tms_key", "baseline_tms_key", "c_rate", "metric_code",
        "reduction_pct", "value_basis", "note", "batch_id"]])

    ru = t["runs"].copy()
    ru = ru.assign(source_key=ru.source_id.map(sk), pack_key=ru.pack_id.map(pk), tms_key=ru.material_id.map(tk),
                   condition_key=cond_key(ru), batch_id=batch_id)
    n["fact_run"] = _insert(con, "fact_run", ru[[
        "run_id", "source_key", "pack_key", "tms_key", "condition_key", "data_origin", "anchor_meas_id",
        "calib_param", "calib_value", "fixed_params", "target_value", "sim_peak", "sim_dt_max", "batch_id"]])
    rk = _keymap(con, "fact_run", "run_id", "run_key")

    lg = t["logs"].merge(t["runs"][["run_id", "pack_id"]], on="run_id")
    lg["run_key"] = lg.run_id.map(rk)
    lg["cell_key"] = [ck[(a, b)] for a, b in zip(lg.pack_id, lg.cell_id)]
    n["fact_thermal_log"] = _insert(con, "fact_thermal_log", lg[[
        "run_key", "cell_key", "t_s", "temp_c", "pcm_liquid_frac", "heat_w", "phase"]])

    con.executescript((SQL_DIR / "02_kpi_views.sql").read_text())

    # post-load DQ: referential integrity enforced by FKs; check view health
    fk = con.execute("PRAGMA foreign_key_check").fetchall()
    dq.check("post_load_foreign_keys", "warehouse", len(fk))
    nk = con.execute("SELECT COUNT(*) FROM vw_run_kpi").fetchone()[0]
    dq.check("post_load_every_run_scored", "vw_run_kpi", abs(nk - n["fact_run"]))

    _insert(con, "dq_check_result", pd.DataFrame(dq.rows).assign(batch_id=batch_id)[
        ["batch_id", "check_name", "target_table", "status", "failed_rows", "detail"]])
    _insert(con, "etl_file_manifest", manifest.assign(batch_id=batch_id)[["batch_id", "file_path", "sha256", "n_rows"]])
    status = "FAILED_DQ" if dq.failed else "SUCCESS"
    con.execute("INSERT INTO etl_batch VALUES (?,?,datetime('now'),?,?)",
                (batch_id, started, status, str(n)))
    con.commit(); con.close()
    return n, status
