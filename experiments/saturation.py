from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKLOAD = ROOT / "workload" / "load_test.py"
CONFIG = json.loads((ROOT / "config" / "project.json").read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=["aws", "baseline"], required=True)
    parser.add_argument("--count", type=int, default=500)
    parser.add_argument("--run-id", default=datetime.now(timezone.utc).strftime("sat-%Y%m%dT%H%M%SZ"))
    args = parser.parse_args()

    results = []
    for concurrency in CONFIG["saturation_concurrency"]:
        child_run = f"{args.run_id}-{args.target}-c{concurrency}"
        cmd = [sys.executable, str(WORKLOAD), "--target", args.target, "--count", str(args.count), "--concurrency", str(concurrency), "--run-id", child_run]
        completed = subprocess.run(cmd, cwd=ROOT / "workload", text=True, capture_output=True)
        print(completed.stdout)
        if completed.stderr:
            print(completed.stderr, file=sys.stderr)
        summary = ROOT / "evidence" / "runs" / child_run / f"{args.target}_summary.json"
        if summary.exists():
            results.append(json.loads(summary.read_text(encoding="utf-8")))

    out_dir = ROOT / "evidence" / "runs" / args.run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{args.target}_saturation.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"SATURATION={out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
