from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import ROOT, load_project, write_result


def main() -> int:
    p = argparse.ArgumentParser(); p.add_argument("--run-id", required=True); p.add_argument("--events", type=int); p.add_argument("--budget-usd", type=float)
    args = p.parse_args()
    cfg = load_project()
    events = args.events or cfg["cost_projection_events"]
    budget = args.budget_usd or cfg["cost_guardrail_usd"]
    pricing_path = ROOT / "config" / "pricing_snapshot.json"
    if not pricing_path.exists():
        write_result("NT-3", {
            "fixture_id": f"cost-scale-{args.run_id}", "expected": "Projected spend is checked before scale-up.",
            "observed": "No captured pricing snapshot is available.", "recovery": "Run python experiments/capture_pricing.py with AWS credentials that allow pricing:GetProducts.",
            "residual_risk": "No cost claim should be published until pricing is captured.", "status": "HOLD"
        }, args.run_id)
        return 3
    pricing = json.loads(pricing_path.read_text(encoding="utf-8"))
    per_million = pricing.get("estimated_serverless_usd_per_million_events")
    if per_million is None:
        write_result("NT-3", {
            "fixture_id": f"cost-scale-{args.run_id}", "expected": "Projected spend is checked before scale-up.",
            "observed": "Pricing snapshot exists but automatic normalized rate extraction was incomplete.",
            "recovery": "Review raw pricing entries and set estimated_serverless_usd_per_million_events in config/pricing_snapshot.json.",
            "residual_risk": "Cost guardrail cannot pass without a normalized price rate.", "status": "HOLD"
        }, args.run_id)
        return 3
    per_million = float(per_million)
    # When no explicit --events value is supplied, increase the fixture until it definitely crosses the declared budget.
    if args.events is None and per_million > 0:
        minimum_millions_to_exceed = int(budget // per_million) + 1
        events = max(events, minimum_millions_to_exceed * 1_000_000)
    projected = events / 1_000_000 * per_million
    action = "BLOCK" if projected > budget else "ALLOW"
    passed = projected > budget and action == "BLOCK"
    write_result("NT-3", {
        "fixture_id": f"cost-scale-{args.run_id}", "precondition": {"events": events, "budget_usd": budget, "pricing_snapshot": str(pricing_path.relative_to(ROOT))},
        "expected": "A deliberately over-budget scale fixture is detected and blocked before execution.",
        "observed": {"projected_usd": round(projected, 6), "guardrail_action": action, "normalized_usd_per_million_events": per_million},
        "recovery": "Reduce volume/concurrency, revise architecture or explicitly approve a higher budget before rerun.",
        "residual_risk": "AWS tiering, free tier, data transfer and taxes may differ from the normalized pre-spend estimate.",
        "status": "PASS" if passed else "FAIL"
    }, args.run_id)
    return 0 if passed else 2

if __name__ == "__main__": raise SystemExit(main())
