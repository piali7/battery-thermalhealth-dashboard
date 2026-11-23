-- =====================================================================
-- Battery Thermal Health Data Warehouse — star schema (SQLite dialect,
-- portable to PostgreSQL / SQL Server with minor type changes)
-- =====================================================================
PRAGMA foreign_keys = ON;

-- ---------- Dimensions ----------
CREATE TABLE IF NOT EXISTS dim_source (
    source_key      INTEGER PRIMARY KEY,
    source_id       TEXT NOT NULL UNIQUE,
    short_cite      TEXT NOT NULL,
    title           TEXT,
    journal         TEXT,
    year            INTEGER,
    volume_pages    TEXT,
    doi             TEXT,
    open_url        TEXT,
    study_type      TEXT,
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS dim_pack (
    pack_key            INTEGER PRIMARY KEY,
    pack_id             TEXT NOT NULL UNIQUE,
    source_key          INTEGER REFERENCES dim_source(source_key),
    pack_label          TEXT NOT NULL,
    pack_scale          TEXT CHECK (pack_scale IN ('single_cell','module','pack')),
    cell_format         TEXT,
    chemistry           TEXT,
    cell_capacity_ah    REAL,
    n_cells             INTEGER CHECK (n_cells >= 1),
    layout              TEXT,               -- e.g. '2x2'
    electrical_config   TEXT,
    cell_mass_kg        REAL,
    cell_cp_j_per_kgk   REAL,
    cell_area_m2        REAL,
    cell_resistance_mohm REAL
);

CREATE TABLE IF NOT EXISTS dim_cell (
    cell_key        INTEGER PRIMARY KEY,
    pack_key        INTEGER NOT NULL REFERENCES dim_pack(pack_key),
    cell_id         TEXT NOT NULL,
    row_idx         INTEGER,
    col_idx         INTEGER,
    UNIQUE (pack_key, cell_id)
);

CREATE TABLE IF NOT EXISTS dim_tms (                 -- thermal management system / material
    tms_key                 INTEGER PRIMARY KEY,
    material_id             TEXT NOT NULL UNIQUE,
    source_key              INTEGER REFERENCES dim_source(source_key),
    tms_code                TEXT NOT NULL,
    tms_label               TEXT NOT NULL,
    tms_family              TEXT CHECK (tms_family IN ('NO_PCM','PURE_PCM','METAL_FOAM_PCM')),
    foam_metal              TEXT,
    foam_ppi                INTEGER,
    foam_porosity           REAL CHECK (foam_porosity IS NULL OR (foam_porosity > 0 AND foam_porosity < 1)),
    pcm_name                TEXT,
    pcm_melt_c              REAL,
    pcm_latent_j_per_g      REAL,
    composite_latent_j_per_g REAL,
    k_eff_w_per_mk          REAL,
    pcm_mass_g_per_cell     REAL,
    foam_mass_g_per_cell    REAL,
    encapsulation           TEXT,
    basis_note              TEXT
);

CREATE TABLE IF NOT EXISTS dim_condition (
    condition_key   INTEGER PRIMARY KEY,
    c_rate          REAL,
    ambient_c       REAL,
    dod_pct         REAL,
    environment     TEXT,
    condition_label TEXT,
    UNIQUE (c_rate, ambient_c, dod_pct, environment)
);

CREATE TABLE IF NOT EXISTS dim_metric (
    metric_key      INTEGER PRIMARY KEY,
    metric_code     TEXT NOT NULL UNIQUE,
    description     TEXT,
    unit            TEXT
);

CREATE TABLE IF NOT EXISTS dim_threshold (
    threshold_id    TEXT PRIMARY KEY,
    metric          TEXT,
    value           REAL NOT NULL,
    unit            TEXT,
    band            TEXT,
    basis           TEXT
);

-- ---------- Facts ----------
-- Grain: one published number (one metric, one test condition, one TMS, one pack)
CREATE TABLE IF NOT EXISTS fact_reported_measurement (
    meas_key        INTEGER PRIMARY KEY,
    meas_id         TEXT NOT NULL UNIQUE,
    source_key      INTEGER NOT NULL REFERENCES dim_source(source_key),
    pack_key        INTEGER NOT NULL REFERENCES dim_pack(pack_key),
    tms_key         INTEGER NOT NULL REFERENCES dim_tms(tms_key),
    condition_key   INTEGER NOT NULL REFERENCES dim_condition(condition_key),
    metric_key      INTEGER NOT NULL REFERENCES dim_metric(metric_key),
    value           REAL NOT NULL,
    qualifier       TEXT CHECK (qualifier IN ('=','<=','>=')),
    value_basis     TEXT CHECK (value_basis IN ('reported','derived_from_reported','simulation_reported')),
    location_note   TEXT,
    batch_id        TEXT
);

-- Grain: one published relative reduction (no absolute values given in source)
CREATE TABLE IF NOT EXISTS fact_reported_relative (
    rel_key             INTEGER PRIMARY KEY,
    rel_id              TEXT NOT NULL UNIQUE,
    source_key          INTEGER NOT NULL REFERENCES dim_source(source_key),
    pack_key            INTEGER NOT NULL REFERENCES dim_pack(pack_key),
    tms_key             INTEGER NOT NULL REFERENCES dim_tms(tms_key),
    baseline_tms_key    INTEGER NOT NULL REFERENCES dim_tms(tms_key),
    c_rate              REAL,
    metric_code         TEXT,
    reduction_pct       REAL,
    value_basis         TEXT,
    note                TEXT,
    batch_id            TEXT
);

-- Grain: one test run (one pack x TMS x condition), header for the time-series
CREATE TABLE IF NOT EXISTS fact_run (
    run_key         INTEGER PRIMARY KEY,
    run_id          TEXT NOT NULL UNIQUE,
    source_key      INTEGER REFERENCES dim_source(source_key),
    pack_key        INTEGER NOT NULL REFERENCES dim_pack(pack_key),
    tms_key         INTEGER NOT NULL REFERENCES dim_tms(tms_key),
    condition_key   INTEGER NOT NULL REFERENCES dim_condition(condition_key),
    data_origin     TEXT NOT NULL CHECK (data_origin IN ('model_reconstructed','lab_measured')),
    anchor_meas_id  TEXT,          -- published value(s) the run is calibrated to
    calib_param     TEXT,
    calib_value     REAL,
    fixed_params    TEXT,
    target_value    REAL,
    sim_peak        REAL,
    sim_dt_max      REAL,
    batch_id        TEXT
);

-- Grain: one temperature sample of one cell at one time in one run
CREATE TABLE IF NOT EXISTS fact_thermal_log (
    run_key         INTEGER NOT NULL REFERENCES fact_run(run_key),
    cell_key        INTEGER NOT NULL REFERENCES dim_cell(cell_key),
    t_s             INTEGER NOT NULL CHECK (t_s >= 0),
    temp_c          REAL NOT NULL,
    pcm_liquid_frac REAL CHECK (pcm_liquid_frac IS NULL OR pcm_liquid_frac BETWEEN 0 AND 1),
    heat_w          REAL,
    phase           TEXT CHECK (phase IN ('discharge','rest','charge')),
    PRIMARY KEY (run_key, cell_key, t_s)
);
CREATE INDEX IF NOT EXISTS ix_log_run_t ON fact_thermal_log(run_key, t_s);

-- ---------- ETL audit ----------
CREATE TABLE IF NOT EXISTS etl_batch (
    batch_id        TEXT PRIMARY KEY,
    started_at      TEXT,
    finished_at     TEXT,
    status          TEXT,
    rows_loaded     TEXT
);
CREATE TABLE IF NOT EXISTS etl_file_manifest (
    batch_id        TEXT,
    file_path       TEXT,
    sha256          TEXT,
    n_rows          INTEGER,
    PRIMARY KEY (batch_id, file_path)
);
CREATE TABLE IF NOT EXISTS dq_check_result (
    batch_id        TEXT,
    check_name      TEXT,
    target_table    TEXT,
    status          TEXT CHECK (status IN ('PASS','WARN','FAIL')),
    failed_rows     INTEGER,
    detail          TEXT,
    PRIMARY KEY (batch_id, check_name)
);
