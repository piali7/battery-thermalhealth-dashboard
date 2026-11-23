-- =====================================================================
-- Example analytical queries against the warehouse (run in DB Browser
-- for SQLite, DBeaver, or `python -m etl.query sql/03_analysis_queries.sql`)
-- =====================================================================

-- Q1. Thermal-health scorecard: every reconstructed / lab run, worst first
SELECT run_id, pack_label, tms_label, c_rate, peak_c, dt_max_c,
       pct_time_above_warn, thermal_health_index, health_band
FROM vw_run_kpi
ORDER BY thermal_health_index;

-- Q2. Does foam pore density matter? Peak reduction by PPI and C-rate (single cell, published values)
SELECT c.c_rate, t.foam_ppi, m.value AS foam_t_max_c,
       b.value AS nc_t_max_c, ROUND(b.value - m.value, 2) AS reduction_c
FROM fact_reported_measurement m
JOIN dim_tms t        ON t.tms_key = m.tms_key AND t.tms_family = 'METAL_FOAM_PCM'
JOIN dim_metric d     ON d.metric_key = m.metric_key AND d.metric_code = 'T_MAX'
JOIN dim_pack p       ON p.pack_key = m.pack_key AND p.pack_id = 'CELL18650_S1'
JOIN dim_condition c  ON c.condition_key = m.condition_key
JOIN fact_reported_measurement b ON b.pack_key = m.pack_key AND b.condition_key = m.condition_key
                                AND b.metric_key = m.metric_key
JOIN dim_tms bt       ON bt.tms_key = b.tms_key AND bt.tms_family = 'NO_PCM'
ORDER BY c.c_rate, t.foam_ppi;

-- Q3. Module vs single cell: how much worse does packing make no-PCM cooling, and how much does foam recover?
SELECT f.c_rate,
       MAX(CASE WHEN f.pack_scale = 'single_cell' AND f.tms_family = 'NO_PCM' THEN f.peak_c END) AS cell_nc_peak,
       MAX(CASE WHEN f.pack_scale = 'module'      AND f.tms_family = 'NO_PCM' THEN f.peak_c END) AS module_nc_peak,
       MAX(CASE WHEN f.pack_scale = 'module'      AND f.tms_family = 'METAL_FOAM_PCM' THEN f.peak_c END) AS module_foam_peak
FROM vw_run_kpi f GROUP BY f.c_rate ORDER BY f.c_rate;

-- Q4. Time above 45 °C warning threshold, minutes, per run
SELECT run_id, ROUND(s_above_warn / 60.0, 1) AS min_above_45c, ROUND(s_above_crit / 60.0, 1) AS min_above_60c
FROM vw_run_kpi ORDER BY s_above_warn DESC;

-- Q5. PCM latent-heat utilisation: how much of the paraffin melted at peak load?
SELECT run_id, c_rate, ROUND(max_liquid_frac * 100, 1) AS pct_pcm_melted
FROM vw_run_kpi WHERE tms_family = 'METAL_FOAM_PCM' ORDER BY c_rate, run_id;

-- Q6. Module hot-spot: which cell runs hottest, and when does the spread peak?
SELECT r.run_id, ce.cell_id, k.t_max_c
FROM vw_cell_run_kpi k JOIN fact_run r USING(run_key) JOIN dim_cell ce USING(cell_key)
WHERE r.run_id LIKE 'S1_MOD_%_3C' ORDER BY r.run_id, k.t_max_c DESC;

-- Q7. Data lineage: every KPI traced back to the published value that anchors it
SELECT r.run_id, r.data_origin, r.anchor_meas_id, m.value AS published_value, m.location_note,
       s.short_cite, s.doi, r.calib_param, ROUND(r.calib_value, 4) AS calib_value
FROM fact_run r
LEFT JOIN fact_reported_measurement m ON m.meas_id = substr(r.anchor_meas_id, 1, 4)
LEFT JOIN dim_source s ON s.source_key = r.source_key;

-- Q8. ETL audit
SELECT * FROM etl_batch ORDER BY started_at DESC;
SELECT * FROM dq_check_result WHERE batch_id = (SELECT MAX(batch_id) FROM etl_batch);
