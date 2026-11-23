"""Run a .sql file (or a single statement) against the warehouse and print results.

    python -m etl.query sql/03_analysis_queries.sql
    python -m etl.query "SELECT * FROM vw_run_kpi LIMIT 5"
"""
import sqlite3
import sys
from pathlib import Path

import pandas as pd

from .config import WAREHOUSE_DB


def main(arg: str):
    sql = Path(arg).read_text() if arg.endswith(".sql") else arg
    con = sqlite3.connect(WAREHOUSE_DB)
    pd.set_option("display.width", 220); pd.set_option("display.max_columns", 20)
    for stmt in [s.strip() for s in sql.split(";")]:
        body = "\n".join(l for l in stmt.splitlines() if not l.strip().startswith("--")).strip()
        if not body:
            continue
        print("\n" + body.splitlines()[0][:100])
        print(pd.read_sql_query(body, con).to_string(index=False))


if __name__ == "__main__":
    main(sys.argv[1])
