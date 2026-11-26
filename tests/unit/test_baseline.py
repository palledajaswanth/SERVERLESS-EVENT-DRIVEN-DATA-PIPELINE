from pathlib import Path
import os
import sys
import tempfile

os.environ["BASELINE_DB"] = str(Path(tempfile.gettempdir()) / "serverless_pipeline_test.db")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "baseline"))
from fastapi.testclient import TestClient
from app import app


def test_baseline_health_and_idempotency():
    c = TestClient(app)
    assert c.get("/health").status_code == 200
    event = {"event_id": "unit-1", "event_type": "test", "timestamp": "2026-01-01T00:00:00Z", "value": 1.0, "source": "unit"}
    r1 = c.post("/events", json=event); r2 = c.post("/events", json=event)
    assert r1.status_code == 202 and r2.status_code == 202
    assert r2.json()["status"] in {"duplicate", "stored"}
