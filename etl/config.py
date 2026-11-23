from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_LIT = ROOT / "data" / "raw" / "literature"
RAW_LAB = ROOT / "data" / "raw" / "lab_logs"
STAGING = ROOT / "data" / "staging"
WAREHOUSE_DB = ROOT / "data" / "warehouse" / "battery_thermal_dw.sqlite"
EXPORTS = ROOT / "data" / "exports" / "tableau"
SQL_DIR = ROOT / "sql"

LITERATURE_FILES = {
    "sources": "sources.csv",
    "packs": "packs.csv",
    "materials": "tms_materials.csv",
    "measurements": "reported_measurements.csv",
    "relative": "reported_relative.csv",
    "heat": "heat_generation.csv",
    "thresholds": "thresholds.csv",
}

# Required columns for lab logs dropped into data/raw/lab_logs/*.csv
LAB_LOG_COLUMNS = ["run_id", "pack_id", "material_id", "c_rate", "ambient_c",
                   "cell_id", "t_s", "temp_c"]
LAB_LOG_OPTIONAL = ["dod_pct", "phase", "pcm_liquid_frac", "heat_w", "row_idx", "col_idx"]

METRICS = {
    "T_MAX": ("Peak cell surface temperature", "C"),
    "DT_MAX": ("Maximum cell-to-cell temperature difference", "C"),
    "T_RISE": ("Temperature rise above start", "C"),
    "T_MAX_CYCLE1": ("Peak temperature, cycle 1 (simulation)", "C"),
    "T_MAX_CYCLE2": ("Peak temperature, cycle 2 (simulation)", "C"),
    "T_MAX_CYCLE3": ("Peak temperature, cycle 3 (simulation)", "C"),
    "T_MAX_CYCLE4": ("Peak temperature, cycle 4 (simulation)", "C"),
}

TMS_FAMILY = {"NC": "NO_PCM", "PCM_PA": "PURE_PCM"}   # anything with foam -> METAL_FOAM_PCM
