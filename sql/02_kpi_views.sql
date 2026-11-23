-- =====================================================================
-- Thermal-health KPI layer (views). Thresholds come from dim_threshold,
-- so changing a limit there re-scores everything.
-- =====================================================================
DROP VIEW IF EXISTS vw_thresholds;
CREATE VIEW vw_thresholds AS
SELECT
    (SELECT value FROM dim_threshold WHERE threshold_id = 'TH_OPT_HIGH') AS t_opt,
    (SELECT value FROM dim_threshold WHERE threshold_id = 'TH_WARN')     AS t_warn,
    (SELECT value FROM dim_threshold WHERE threshold_id = 'TH_CRIT')     AS t_crit,
    (SELECT value FROM dim_threshold WHERE threshold_id = 'TH_DT_LIMIT') AS dt_limit;

-- ---------- Per cell, per run (time-series KPIs) ----------
DROP VIEW IF EXISTS vw_cell_run_kpi;
CREATE VIEW vw_cell_run_kpi AS
WITH s AS (
    SELECT l.*,
           COALESCE(LEAD(t_s) OVER w - t_s, 0)                         AS dt_next,
           (LEAD(temp_c) OVER w - temp_c) * 60.0 /
               NULLIF(LEAD(t_s) OVER w - t_s, 0)                        AS rate_c_per_min
    FROM fact_thermal_log l
    WINDOW w AS (PARTITION BY run_key, cell_key ORDER BY t_s)
)
SELECT s.run_key, s.cell_key,
       MAX(temp_c)                                                   AS t_max_c,
       MIN(temp_c)                                                   AS t_min_c,
       ROUND(AVG(temp_c), 3)                                         AS t_mean_c,
       SUM(CASE WHEN temp_c > th.t_opt  THEN dt_next ELSE 0 END)     AS s_above_opt,
       SUM(CASE WHEN temp_c > th.t_warn THEN dt_next ELSE 0 END)     AS s_above_warn,
       SUM(CASE WHEN temp_c > th.t_crit THEN dt_next ELSE 0 END)     AS s_above_crit,
       SUM(dt_next)                                                  AS s_total,
       ROUND(MAX(rate_c_per_min), 3)                                 AS max_rise_c_per_min,
       MAX(pcm_liquid_frac)                                          AS max_liquid_frac,
       ROUND(SUM(heat_w * dt_next), 1)                               AS heat_generated_j
FROM s CROSS JOIN vw_thresholds th
GROUP BY s.run_key, s.cell_key;

-- time to peak (first time the cell reaches its maximum)
DROP VIEW IF EXISTS vw_cell_time_to_peak;
CREATE VIEW vw_cell_time_to_peak AS
SELECT l.run_key, l.cell_key, MIN(l.t_s) AS t_peak_s
FROM fact_thermal_log l
JOIN vw_cell_run_kpi k ON k.run_key = l.run_key AND k.cell_key = l.cell_key AND l.temp_c = k.t_max_c
GROUP BY l.run_key, l.cell_key;

-- instantaneous module spread
DROP VIEW IF EXISTS vw_run_spread_ts;
CREATE VIEW vw_run_spread_ts AS
SELECT run_key, t_s,
       MAX(temp_c) AS t_hot_c, MIN(temp_c) AS t_cold_c, AVG(temp_c) AS t_avg_c,
       MAX(temp_c) - MIN(temp_c) AS spread_c
FROM fact_thermal_log
GROUP BY run_key, t_s;

-- ---------- Per run KPIs + Thermal Health Index ----------
DROP VIEW IF EXISTS vw_run_kpi;
CREATE VIEW vw_run_kpi AS
WITH agg AS (
    SELECT run_key,
           MAX(t_max_c)              AS peak_c,
           MAX(s_above_opt)          AS s_above_opt,
           MAX(s_above_warn)         AS s_above_warn,
           MAX(s_above_crit)         AS s_above_crit,
           MAX(s_total)              AS s_total,
           MAX(max_rise_c_per_min)   AS max_rise_c_per_min,
           MAX(max_liquid_frac)      AS max_liquid_frac,
           COUNT(*)                  AS n_cells_logged
    FROM vw_cell_run_kpi GROUP BY run_key
), spr AS (
    SELECT run_key, MAX(spread_c) AS dt_max_c FROM vw_run_spread_ts GROUP BY run_key
), ttp AS (
    SELECT run_key, MIN(t_peak_s) AS t_peak_s FROM vw_cell_time_to_peak GROUP BY run_key
), scored AS (
    SELECT r.run_key, r.run_id, r.data_origin, r.anchor_meas_id, r.calib_param, r.calib_value,
           s.short_cite, p.pack_id, p.pack_label, p.pack_scale, p.layout, p.n_cells,
           t.material_id, t.tms_code, t.tms_label, t.tms_family, t.foam_metal, t.foam_ppi,
           c.c_rate, c.ambient_c, c.dod_pct,
           a.peak_c, ROUND(spr.dt_max_c, 3) AS dt_max_c, ttp.t_peak_s,
           a.s_above_opt, a.s_above_warn, a.s_above_crit, a.s_total,
           ROUND(100.0 * a.s_above_warn / a.s_total, 2) AS pct_time_above_warn,
           a.max_rise_c_per_min, a.max_liquid_frac, a.n_cells_logged,
           -- component scores 0-100
           MAX(0, MIN(100, 100.0 * (th.t_crit - a.peak_c) / (th.t_crit - th.t_opt)))            AS score_peak,
           CASE WHEN a.n_cells_logged > 1
                THEN MAX(0, MIN(100, 100.0 * (1 - spr.dt_max_c / (2 * th.dt_limit)))) END       AS score_uniformity,
           100.0 * (1 - 1.0 * a.s_above_warn / a.s_total)                                       AS score_exposure
    FROM fact_run r
    JOIN agg a        ON a.run_key = r.run_key
    JOIN spr          ON spr.run_key = r.run_key
    JOIN ttp          ON ttp.run_key = r.run_key
    JOIN dim_pack p   ON p.pack_key = r.pack_key
    JOIN dim_tms t    ON t.tms_key = r.tms_key
    JOIN dim_condition c ON c.condition_key = r.condition_key
    LEFT JOIN dim_source s ON s.source_key = r.source_key
    CROSS JOIN vw_thresholds th
)
SELECT scored.*,
       ROUND((0.5 * score_peak + 0.2 * score_exposure + COALESCE(0.3 * score_uniformity, 0))
             / (0.7 + CASE WHEN score_uniformity IS NULL THEN 0 ELSE 0.3 END), 1)   AS thermal_health_index,
       CASE
         WHEN (0.5 * score_peak + 0.2 * score_exposure + COALESCE(0.3 * score_uniformity, 0))
              / (0.7 + CASE WHEN score_uniformity IS NULL THEN 0 ELSE 0.3 END) >= 75 THEN 'Healthy'
         WHEN (0.5 * score_peak + 0.2 * score_exposure + COALESCE(0.3 * score_uniformity, 0))
              / (0.7 + CASE WHEN score_uniformity IS NULL THEN 0 ELSE 0.3 END) >= 50 THEN 'Watch'
         ELSE 'Critical' END                                                        AS health_band
FROM scored;

-- ---------- Metal-foam effectiveness vs no-PCM baseline (same pack, same condition) ----------
DROP VIEW IF EXISTS vw_foam_effectiveness_runs;
CREATE VIEW vw_foam_effectiveness_runs AS
SELECT f.run_id, f.pack_label, f.tms_label, f.foam_ppi, f.c_rate,
       b.peak_c AS baseline_peak_c, f.peak_c AS foam_peak_c,
       ROUND(b.peak_c - f.peak_c, 2)                                   AS peak_reduction_c,
       ROUND(100.0 * (b.peak_c - f.peak_c) / (b.peak_c - f.ambient_c), 1) AS rise_suppression_pct,
       b.dt_max_c AS baseline_dt_c, f.dt_max_c AS foam_dt_c,
       b.s_above_warn AS baseline_s_above_warn, f.s_above_warn AS foam_s_above_warn,
       b.thermal_health_index AS baseline_thi, f.thermal_health_index AS foam_thi,
       ROUND(f.thermal_health_index - b.thermal_health_index, 1)        AS thi_gain
FROM vw_run_kpi f
JOIN vw_run_kpi b
  ON b.pack_id = f.pack_id AND b.c_rate = f.c_rate
 AND b.ambient_c = f.ambient_c AND b.tms_family = 'NO_PCM'
WHERE f.tms_family = 'METAL_FOAM_PCM';

-- ---------- KPIs straight from published numbers (all sources) ----------
DROP VIEW IF EXISTS vw_reported_kpi;
CREATE VIEW vw_reported_kpi AS
WITH piv AS (
    SELECT m.source_key, m.pack_key, m.tms_key, m.condition_key,
           MAX(CASE WHEN d.metric_code = 'T_MAX'  THEN m.value END)     AS t_max_c,
           MAX(CASE WHEN d.metric_code = 'T_MAX'  THEN m.qualifier END) AS t_max_qualifier,
           MAX(CASE WHEN d.metric_code = 'T_MAX'  THEN m.value_basis END) AS t_max_basis,
           MAX(CASE WHEN d.metric_code = 'DT_MAX' THEN m.value END)     AS dt_max_c,
           MAX(CASE WHEN d.metric_code = 'T_RISE' THEN m.value END)     AS t_rise_c,
           GROUP_CONCAT(m.meas_id, ',')                                 AS meas_ids
    FROM fact_reported_measurement m JOIN dim_metric d ON d.metric_key = m.metric_key
    WHERE d.metric_code IN ('T_MAX','DT_MAX','T_RISE')
    GROUP BY m.source_key, m.pack_key, m.tms_key, m.condition_key
)
SELECT s.source_id, s.short_cite, p.pack_id, p.pack_label, p.pack_scale, p.layout,
       t.material_id, t.tms_code, t.tms_label, t.tms_family, t.foam_metal, t.foam_ppi,
       c.c_rate, c.ambient_c, c.dod_pct, c.environment,
       piv.t_max_c, piv.t_max_qualifier, piv.t_max_basis, piv.dt_max_c, piv.t_rise_c, piv.meas_ids,
       CASE WHEN piv.t_max_c IS NULL THEN NULL
            WHEN piv.t_max_c >= th.t_crit THEN 'Critical'
            WHEN piv.t_max_c >= th.t_warn THEN 'Warning'
            WHEN piv.t_max_c >  th.t_opt  THEN 'Elevated'
            ELSE 'Optimal' END                                                   AS peak_band,
       CASE WHEN piv.dt_max_c IS NULL THEN NULL
            WHEN piv.dt_max_c > th.dt_limit THEN 'Non-uniform' ELSE 'Uniform' END AS uniformity_band
FROM piv
JOIN dim_source s    ON s.source_key = piv.source_key
JOIN dim_pack p      ON p.pack_key = piv.pack_key
JOIN dim_tms t       ON t.tms_key = piv.tms_key
JOIN dim_condition c ON c.condition_key = piv.condition_key
CROSS JOIN vw_thresholds th;

DROP VIEW IF EXISTS vw_reported_foam_vs_baseline;
CREATE VIEW vw_reported_foam_vs_baseline AS
SELECT f.short_cite, f.pack_label, f.tms_label AS foam_tms, b.tms_label AS baseline_tms,
       b.tms_family AS baseline_family, f.c_rate, f.ambient_c,
       b.environment AS baseline_env, f.environment AS foam_env,
       b.t_max_c AS baseline_t_max_c, f.t_max_c AS foam_t_max_c, f.t_max_qualifier,
       ROUND(b.t_max_c - f.t_max_c, 2)                                AS peak_reduction_c,
       ROUND(100.0 * (b.t_max_c - f.t_max_c) / b.t_max_c, 1)          AS peak_reduction_pct,
       b.dt_max_c AS baseline_dt_c, f.dt_max_c AS foam_dt_c,
       f.meas_ids || ' vs ' || b.meas_ids                              AS evidence
FROM vw_reported_kpi f
JOIN vw_reported_kpi b
  ON b.pack_id = f.pack_id AND b.c_rate = f.c_rate
 AND COALESCE(b.ambient_c, -1) = COALESCE(f.ambient_c, -1)
 AND b.tms_family IN ('NO_PCM','PURE_PCM')
WHERE f.tms_family = 'METAL_FOAM_PCM' AND f.t_max_c IS NOT NULL AND b.t_max_c IS NOT NULL;
