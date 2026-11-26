from __future__ import annotations

import argparse
import csv
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import boto3
import httpx

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT / "config" / "project.json").read_text(encoding="utf-8"))
RUNTIME = json.loads((ROOT / "config" / "runtime.json").read_text(encoding="utf-8"))


def event_for(i: int, run_id: str) -> dict:
    return {
        "event_id": f"{run_id}-{i:04d}-{uuid.uuid4().hex[:10]}",
        "event_type": "cold-start",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "value": float(i),
        "source": "cold-start-experiment",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=CFG["cold_start_trials"])
    parser.add_argument("--run-id", default=datetime.now(timezone.utc).strftime("cold-%Y%m%dT%H%M%SZ"))
    args = parser.parse_args()

    region = RUNTIME["aws_region"]
    function_name = RUNTIME["ingestion_function"]
    api_url = RUNTIME["api_url"]
    client = boto3.client("lambda", region_name=region)

    rows = []
    with httpx.Client(timeout=30.0) as http:
        for i in range(args.trials):
            cfg = client.get_function_configuration(FunctionName=function_name)
            env = dict(cfg.get("Environment", {}).get("Variables", {}))
            env["COLD_START_NONCE"] = f"{args.run_id}-{i}-{uuid.uuid4().hex}"
            client.update_function_configuration(FunctionName=function_name, Environment={"Variables": env})
            client.get_waiter("function_updated_v2").wait(FunctionName=function_name)
            t0 = time.perf_counter_ns()
            r = http.post(api_url, json=event_for(i, args.run_id))
            latency_ms = (time.perf_counter_ns() - t0) / 1_000_000
            rows.append({"trial": i + 1, "status_code": r.status_code, "latency_ms": round(latency_ms, 3), "ok": 200 <= r.status_code < 300})
            print(rows[-1])

    out_dir = ROOT / "evidence" / "runs" / args.run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "cold_start_trials.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader(); writer.writerows(rows)
    print(f"COLD_START={path}")
    return 0 if all(r["ok"] for r in rows) else 2


if __name__ == "__main__":
    raise SystemExit(main())
