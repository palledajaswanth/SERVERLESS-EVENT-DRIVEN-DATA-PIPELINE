from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    p = argparse.ArgumentParser(); p.add_argument("--baseline", required=True); p.add_argument("--aws", required=True); p.add_argument("--output", default=str(ROOT / "evidence" / "comparison.json"))
    args = p.parse_args()
    b = json.loads(Path(args.baseline).read_text(encoding="utf-8")); a = json.loads(Path(args.aws).read_text(encoding="utf-8"))
    fields = ["throughput_events_per_second", "error_rate_percent", "p50_ms", "p95_ms", "p99_ms"]
    comparison = {"baseline": b, "aws": a, "delta": {}}
    for f in fields:
        bv, av = b.get(f), a.get(f)
        if isinstance(bv, (int, float)) and isinstance(av, (int, float)):
            comparison["delta"][f] = {"absolute": av - bv, "percent_vs_baseline": ((av - bv) / bv * 100) if bv else None}
    out = Path(args.output); out.parent.mkdir(parents=True, exist_ok=True); out.write_text(json.dumps(comparison, indent=2), encoding="utf-8")
    print(f"COMPARISON={out}")
    return 0

if __name__ == "__main__": raise SystemExit(main())
