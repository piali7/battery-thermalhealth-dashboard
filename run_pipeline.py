"""
Battery Thermal Health — ETL orchestrator.

    python run_pipeline.py            # extract -> transform -> load -> export

Re-run any time you add lab logs to data/raw/lab_logs/ (see data/raw/lab_logs/README.md).
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone

from etl.extract import extract
from etl.transform import transform
from etl.load import load
from etl.export import export
from etl.export_dashboard import export_dashboard


def main() -> int:
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    batch_id = "B" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    print(f"[{batch_id}] EXTRACT ...")
    frames, manifest = extract()
    print(f"  {len(manifest)} files, lab-log rows: {len(frames['lab_logs'])}")

    print(f"[{batch_id}] TRANSFORM + VALIDATE (includes model reconstruction, ~1 min) ...")
    t, dq = transform(frames)
    for r in dq.rows:
        if r["status"] != "PASS":
            print(f"  {r['status']}: {r['check_name']} ({r['failed_rows']} rows) {r['detail']}")
    if dq.failed:
        print("  Blocking DQ failures - warehouse not loaded."); return 1

    print(f"[{batch_id}] LOAD ...")
    counts, status = load(t, dq, manifest, batch_id, started)
    for k, v in counts.items():
        print(f"  {k:<28}{v:>8}")
    print(f"  DQ checks: {sum(r['status']=='PASS' for r in dq.rows)}/{len(dq.rows)} PASS  -> {status}")

    print(f"[{batch_id}] EXPORT (Tableau) ...")
    ex, hyper = export()
    for k, v in ex.items():
        print(f"  {k:<28}{v:>8} rows")
    print(f"  hyper: {hyper or 'skipped (pip install tableauhyperapi)'}")
    print(f"[{batch_id}] EXPORT (web dashboard) ...")
    for k, v in export_dashboard().items():
        print(f"  {k:<28}{v:>8} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
