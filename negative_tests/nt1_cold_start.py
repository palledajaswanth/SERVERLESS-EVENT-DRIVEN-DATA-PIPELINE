from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path

from common import ROOT, load_project, write_result


def main() -> int:
    p = argparse.ArgumentParser(); p.add_argument("--run-id", required=True); p.add_argument("--trials", type=int)
    args = p.parse_args()
    trials = args.trials or load_project()["cold_start_trials"]
    script = ROOT / "experiments" / "cold_start.py"
    proc = subprocess.run([sys.executable, str(script), "--trials", str(trials), "--run-id", args.run_id], cwd=ROOT)
    csv_path = ROOT / "evidence" / "runs" / args.run_id / "cold_start_trials.csv"
    latencies = []
    failures = 0
    if csv_path.exists():
        with csv_path.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                latencies.append(float(row["latency_ms"]))
                failures += 0 if row["ok"].lower() == "true" else 1
    passed = proc.returncode == 0 and len(latencies) == trials and failures == 0
    write_result("NT-1", {
        "fixture_id": f"cold-start-{args.run_id}",
        "precondition": "Ingestion Lambda configuration is changed before each request to force a fresh execution environment.",
        "expected": f"All {trials} requests are accepted; latency evidence is retained; no silent state loss or duplicate object is introduced.",
        "observed": {"trials": len(latencies), "request_failures": failures, "min_ms": min(latencies) if latencies else None, "max_ms": max(latencies) if latencies else None},
        "recovery": "Restore normal Lambda configuration nonce and continue queue processing; SQS provides durable buffering.",
        "residual_risk": "API latency includes network/API Gateway overhead; CloudWatch Init Duration should be correlated for publication.",
        "status": "PASS" if passed else "FAIL",
    }, args.run_id)
    return 0 if passed else 2

if __name__ == "__main__": raise SystemExit(main())
