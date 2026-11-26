from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "analytics" / "pipeline.duckdb"
RUNS_DIR = ROOT / "evidence" / "runs"
PRICING_PATH = ROOT / "config" / "pricing_snapshot.json"
ANALYTICS_SUMMARY_PATH = ROOT / "analytics" / "analytics_summary.json"
ANALYTICS_REJECTED_PATH = ROOT / "analytics" / "analytics_rejected.json"

SCENARIO_NAMES = {
    "NT-1": "Cold start",
    "NT-2": "Vendor/degraded endpoint portability",
    "NT-3": "Cost surprise guardrail",
    "NT-4": "Defective data partition",
    "NT-5": "Access control / evidence exposure",
}


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def available_runs() -> list[str]:
    """Return experiment run IDs, preferring complete/top-level runs over saturation children."""
    if not RUNS_DIR.exists():
        return []
    dirs = [p for p in RUNS_DIR.iterdir() if p.is_dir()]
    if not dirs:
        return []

    preferred: list[Path] = []
    fallback: list[Path] = []
    for p in dirs:
        has_core = (p / "baseline_summary.json").exists() or (p / "aws_summary.json").exists()
        has_acceptance = (
            (p / "comparison.json").exists()
            or (p / "cost_analysis.json").exists()
            or (p / "cold_start_trials.csv").exists()
            or (p / "negative_tests").exists()
        )
        if has_core and has_acceptance:
            preferred.append(p)
        elif has_core and "-c" not in p.name and not p.name.endswith("-saturation"):
            fallback.append(p)

    chosen = preferred or fallback or dirs
    return [p.name for p in sorted(chosen, key=lambda x: x.stat().st_mtime, reverse=True)]


def run_dir(run_id: str | None) -> Path | None:
    if not run_id:
        return None
    path = RUNS_DIR / run_id
    return path if path.exists() else None


def load_summary(run_id: str | None, target: str) -> dict[str, Any] | None:
    rd = run_dir(run_id)
    if not rd:
        return None
    data = read_json(rd / f"{target}_summary.json")
    return data if isinstance(data, dict) else None


def load_comparison(run_id: str | None) -> dict[str, Any] | None:
    rd = run_dir(run_id)
    if not rd:
        return None
    data = read_json(rd / "comparison.json")
    return data if isinstance(data, dict) else None


def load_saturation(run_id: str | None, target: str) -> list[dict[str, Any]]:
    if not run_id:
        return []
    candidates = [
        RUNS_DIR / f"{run_id}-saturation" / f"{target}_saturation.json",
        RUNS_DIR / run_id / f"{target}_saturation.json",
    ]
    for path in candidates:
        data = read_json(path)
        if isinstance(data, list):
            return [r for r in data if isinstance(r, dict)]
    return []


def load_trace(run_id: str | None, target: str) -> pd.DataFrame:
    rd = run_dir(run_id)
    if not rd:
        return pd.DataFrame()
    path = rd / f"{target}_trace.csv"
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def load_cold_start(run_id: str | None) -> pd.DataFrame:
    rd = run_dir(run_id)
    if not rd:
        return pd.DataFrame()
    path = rd / "cold_start_trials.csv"
    if not path.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(path)
        if "ok" in df.columns:
            df["ok"] = df["ok"].astype(str).str.lower().eq("true")
        return df
    except Exception:
        return pd.DataFrame()


def load_cost(run_id: str | None) -> dict[str, Any] | None:
    rd = run_dir(run_id)
    if not rd:
        return None
    data = read_json(rd / "cost_analysis.json")
    return data if isinstance(data, dict) else None


def load_cloudwatch(run_id: str | None) -> dict[str, Any] | None:
    rd = run_dir(run_id)
    if not rd:
        return None
    data = read_json(rd / "cloudwatch_metrics.json")
    return data if isinstance(data, dict) else None


def load_negative_tests(run_id: str | None) -> list[dict[str, Any]]:
    rd = run_dir(run_id)
    if not rd:
        return []
    folder = rd / "negative_tests"
    if not folder.exists():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(folder.glob("nt-*.json")):
        data = read_json(path)
        if isinstance(data, dict):
            data = dict(data)
            data["evidence_file"] = str(path.relative_to(ROOT))
            rows.append(data)
    return rows


def load_pricing() -> dict[str, Any] | None:
    data = read_json(PRICING_PATH)
    return data if isinstance(data, dict) else None


def load_analytics_summary() -> dict[str, Any] | None:
    data = read_json(ANALYTICS_SUMMARY_PATH)
    return data if isinstance(data, dict) else None


def load_rejected_events() -> list[dict[str, Any]]:
    data = read_json(ANALYTICS_REJECTED_PATH, [])
    return data if isinstance(data, list) else []


def load_events() -> pd.DataFrame:
    if not DB_PATH.exists():
        return pd.DataFrame()
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        df = con.execute(
            """
            SELECT schema_version, event_id, event_type, event_timestamp, value,
                   source, received_at, processed_at, processor_request_id
            FROM events
            """
        ).df()
    finally:
        con.close()

    for col in ["event_timestamp", "received_at", "processed_at"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], utc=True, errors="coerce")
    if {"received_at", "processed_at"}.issubset(df.columns):
        df["processing_ms"] = (df["processed_at"] - df["received_at"]).dt.total_seconds() * 1000.0
    return df


def latest_timestamp(events: pd.DataFrame) -> pd.Timestamp | None:
    if events.empty or "processed_at" not in events.columns:
        return None
    values = events["processed_at"].dropna()
    return values.max() if not values.empty else None
