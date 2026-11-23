"""Run with:  python -m pytest -q   (after python run_pipeline.py)"""
import sqlite3
import pandas as pd
import pytest

from etl.config import WAREHOUSE_DB, RAW_LIT


@pytest.fixture(scope="module")
def con():
    c = sqlite3.connect(WAREHOUSE_DB)
    yield c
    c.close()


def q(con, sql):
    return pd.read_sql_query(sql, con)


def test_every_published_value_loaded(con):
    raw = pd.read_csv(RAW_LIT / "reported_measurements.csv")
    db = q(con, "SELECT meas_id, value FROM fact_reported_measurement")
    m = raw.merge(db, on="meas_id", suffixes=("_raw", "_db"))
    assert len(m) == len(raw)
    assert (m.value_raw - m.value_db).abs().max() < 1e-9


def test_reconstructed_runs_match_published_peaks(con):
    d = q(con, """SELECT k.run_id, k.peak_c, m.value FROM vw_run_kpi k
                  JOIN fact_reported_measurement m ON m.meas_id = substr(k.anchor_meas_id,1,4)""")
    assert len(d) == 18
    assert (d.peak_c - d.value).abs().max() <= 0.05


def test_module_spread_matches_published_dt(con):
    d = q(con, """SELECT k.run_id, k.dt_max_c, m.value FROM vw_run_kpi k
                  JOIN fact_reported_measurement m ON m.meas_id = substr(k.anchor_meas_id,6,4)
                  WHERE k.pack_scale = 'module'""")
    assert len(d) == 6
    assert (d.dt_max_c - d.value).abs().max() <= 0.05


def test_foam_always_beats_baseline(con):
    d = q(con, "SELECT * FROM vw_foam_effectiveness_runs")
    assert (d.peak_reduction_c > 0).all()


def test_sun_2023_reduction_matches_paper(con):
    d = q(con, "SELECT peak_reduction_pct FROM vw_reported_foam_vs_baseline WHERE short_cite LIKE 'Sun%'")
    assert abs(d.peak_reduction_pct.iloc[0] - 10.4) < 0.2


def test_no_blocking_dq_failures(con):
    d = q(con, "SELECT * FROM dq_check_result WHERE status = 'FAIL'")
    assert d.empty


def test_thi_bounds(con):
    d = q(con, "SELECT thermal_health_index FROM vw_run_kpi")
    assert d.thermal_health_index.between(0, 100).all()
