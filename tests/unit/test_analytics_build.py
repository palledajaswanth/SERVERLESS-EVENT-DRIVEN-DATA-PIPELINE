import json
from pathlib import Path

import duckdb

from analytics.build_duckdb import create_events_table


def test_create_events_table_handles_small_batch(tmp_path: Path):
    files = []
    for idx, payload in enumerate([
        {"event_id": "a", "event_type": "telemetry", "value": 1.5, "schema_version": "1.0"},
        {"event_id": "b", "event_type": "transaction", "value": 2.5, "schema_version": "1.0"},
    ]):
        path = tmp_path / f"event-{idx}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        files.append(path)

    con = duckdb.connect(database=":memory:")
    try:
        create_events_table(con, files)
        row_count = con.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        assert row_count == 2
        value_sum = con.execute("SELECT SUM(value) FROM events").fetchone()[0]
        assert value_sum == 4.0
    finally:
        con.close()
