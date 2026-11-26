from __future__ import annotations

import json
import math
import random
import statistics
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
EVIDENCE_DIR = ROOT / "evidence"


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def project_config() -> dict:
    return load_json(CONFIG_DIR / "project.json")


def runtime_config() -> dict:
    path = CONFIG_DIR / "runtime.json"
    if not path.exists():
        raise FileNotFoundError("config/runtime.json not found. Run scripts/deploy.ps1 first.")
    return load_json(path)


def make_event(index: int, seed: int, run_id: str, event_type: str | None = None) -> dict:
    rng = random.Random(seed + index)
    base = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=index)
    etype = event_type or rng.choice(["telemetry", "transaction", "audit", "sensor"])
    return {
        "event_id": f"{run_id}-{index:08d}-{uuid.uuid5(uuid.NAMESPACE_DNS, f'{seed}:{run_id}:{index}').hex[:12]}",
        "event_type": etype,
        "timestamp": base.isoformat().replace("+00:00", "Z"),
        "value": round(rng.uniform(0.0, 1000.0), 6),
        "source": "deterministic-simulator",
    }


def percentile(values: Iterable[float], p: float) -> float:
    xs = sorted(float(v) for v in values)
    if not xs:
        return math.nan
    if len(xs) == 1:
        return xs[0]
    k = (len(xs) - 1) * p
    lo = math.floor(k)
    hi = math.ceil(k)
    if lo == hi:
        return xs[lo]
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def summarize_latencies(latencies_ms: list[float]) -> dict:
    if not latencies_ms:
        return {"p50_ms": None, "p95_ms": None, "p99_ms": None, "mean_ms": None}
    return {
        "p50_ms": round(percentile(latencies_ms, 0.50), 3),
        "p95_ms": round(percentile(latencies_ms, 0.95), 3),
        "p99_ms": round(percentile(latencies_ms, 0.99), 3),
        "mean_ms": round(statistics.mean(latencies_ms), 3),
    }
