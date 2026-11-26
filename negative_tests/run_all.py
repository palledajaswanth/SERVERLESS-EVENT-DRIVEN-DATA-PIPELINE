from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = [
    "nt1_cold_start.py",
    "nt2_vendor_portability.py",
    "nt3_cost_guardrail.py",
    "nt4_partition_quality.py",
    "nt5_access_control.py",
]


def main() -> int:
    p = argparse.ArgumentParser(); p.add_argument("--run-id", default=datetime.now(timezone.utc).strftime("accept-%Y%m%dT%H%M%SZ"))
    args = p.parse_args(); statuses = []
    for test in TESTS:
        proc = subprocess.run([sys.executable, str(ROOT / "negative_tests" / test), "--run-id", args.run_id], cwd=ROOT / "negative_tests")
        statuses.append((test, proc.returncode))
    print("Negative-test return codes:", statuses)
    # HOLD (3) is not silently treated as PASS.
    return 0 if all(code == 0 for _, code in statuses) else 2

if __name__ == "__main__": raise SystemExit(main())
