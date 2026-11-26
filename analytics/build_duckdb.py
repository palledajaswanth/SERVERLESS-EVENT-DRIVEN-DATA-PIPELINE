from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "analytics" / "data" / "events"
DB_PATH = ROOT / "analytics" / "pipeline.duckdb"
SUMMARY_PATH = ROOT / "analytics" / "analytics_summary.json"


def _create_empty_events_table(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        """
        CREATE TABLE events(
          schema_version VARCHAR, event_id VARCHAR, event_type VARCHAR,
          event_timestamp VARCHAR, value DOUBLE, source VARCHAR,
          received_at VARCHAR, processed_at VARCHAR, processor_request_id VARCHAR
        )
        """
    )


def create_events_table(
    con: duckdb.DuckDBPyConnection,
    files: Iterable[Path] | None = None,
) -> None:
    file_paths = [Path(path) for path in (files or sorted(DATA_DIR.glob("*.json")))]
    con.execute("DROP TABLE IF EXISTS events")

    loaded = False
    for path in file_paths:
        if not path.is_file():
            continue
        try:
            if not loaded:
                con.execute(
                    "CREATE TABLE events AS SELECT * FROM read_json_auto(?, union_by_name=true)",
                    [str(path)],
                )
                loaded = True
            else:
                con.execute(
                    "INSERT INTO events SELECT * FROM read_json_auto(?, union_by_name=true)",
                    [str(path)],
                )
        except duckdb.Error as exc:
            print(f"Skipping unreadable events file {path}: {exc}")

    if not loaded:
        _create_empty_events_table(con)


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH))
    try:
        create_events_table(con, sorted(DATA_DIR.glob("*.json")))

        total = con.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        types = con.execute("SELECT event_type, COUNT(*) AS n, AVG(value) AS avg_value FROM events GROUP BY event_type ORDER BY n DESC").fetchall()
        summary = {
            "total_events": total,
            "by_type": [{"event_type": r[0], "count": r[1], "avg_value": r[2]} for r in types],
            "database": str(DB_PATH),
        }
        SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2))
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
