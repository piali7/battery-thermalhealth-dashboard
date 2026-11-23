"""EXTRACT: read raw literature tables and any lab logs, record a file manifest."""
from __future__ import annotations

import hashlib
import pandas as pd

from .config import RAW_LIT, RAW_LAB, LITERATURE_FILES, LAB_LOG_COLUMNS


def _sha(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract():
    frames, manifest = {}, []
    for key, fname in LITERATURE_FILES.items():
        p = RAW_LIT / fname
        df = pd.read_csv(p)
        frames[key] = df
        manifest.append({"file_path": str(p.relative_to(RAW_LIT.parents[2])), "sha256": _sha(p), "n_rows": len(df)})

    lab = []
    for p in sorted(RAW_LAB.glob("*.csv")):
        if p.name.startswith("_"):          # templates / examples are skipped
            continue
        df = pd.read_csv(p)
        missing = [c for c in LAB_LOG_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(f"{p.name}: missing required columns {missing}")
        df["source_file"] = p.name
        lab.append(df)
        manifest.append({"file_path": str(p.relative_to(RAW_LAB.parents[2])), "sha256": _sha(p), "n_rows": len(df)})
    frames["lab_logs"] = pd.concat(lab, ignore_index=True) if lab else pd.DataFrame(columns=LAB_LOG_COLUMNS)
    return frames, pd.DataFrame(manifest)
