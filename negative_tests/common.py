from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_runtime() -> dict:
    return json.loads((ROOT / "config" / "runtime.json").read_text(encoding="utf-8"))


def load_project() -> dict:
    return json.loads((ROOT / "config" / "project.json").read_text(encoding="utf-8"))


def write_result(test_id: str, result: dict, run_id: str | None = None) -> Path:
    rid = run_id or datetime.now(timezone.utc).strftime("neg-%Y%m%dT%H%M%SZ")
    out = ROOT / "evidence" / "runs" / rid / "negative_tests"
    out.mkdir(parents=True, exist_ok=True)
    payload = {
        "test_id": test_id,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        **result,
    }
    path = out / f"{test_id.lower()}.json"
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(json.dumps(payload, indent=2, default=str))
    print(f"EVIDENCE={path}")
    return path
