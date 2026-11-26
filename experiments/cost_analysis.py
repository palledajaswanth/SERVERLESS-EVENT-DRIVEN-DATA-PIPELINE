from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = json.loads((ROOT / "config" / "runtime.json").read_text(encoding="utf-8"))

REPORT_RE = re.compile(r"Billed Duration:\s*([0-9.]+)\s*ms.*?Memory Size:\s*([0-9.]+)\s*MB", re.I)


def parse_dt(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def load_price(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"pricing snapshot missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def price(snapshot: dict, key: str) -> float | None:
    item = snapshot.get("selected_price_dimensions", {}).get(key)
    if not item:
        return None
    try:
        return float(item["price_usd"])
    except Exception:
        return None


def lambda_usage(logs, group: str, start: datetime, end: datetime) -> dict:
    token = None
    reports = []
    while True:
        kwargs = {
            "logGroupName": group,
            "startTime": int(start.timestamp() * 1000),
            "endTime": int(end.timestamp() * 1000),
            "filterPattern": '"REPORT RequestId:"',
            "limit": 10000,
        }
        if token:
            kwargs["nextToken"] = token
        resp = logs.filter_log_events(**kwargs)
        for event in resp.get("events", []):
            m = REPORT_RE.search(event.get("message", ""))
            if m:
                billed_ms = float(m.group(1))
                memory_mb = float(m.group(2))
                reports.append({"billed_ms": billed_ms, "memory_mb": memory_mb})
        new_token = resp.get("nextToken")
        if not new_token or new_token == token:
            break
        token = new_token
    gb_seconds = sum((r["billed_ms"] / 1000.0) * (r["memory_mb"] / 1024.0) for r in reports)
    return {
        "invocations_from_report_lines": len(reports),
        "billed_ms_sum": round(sum(r["billed_ms"] for r in reports), 3),
        "gb_seconds": round(gb_seconds, 9),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", required=True)
    p.add_argument("--pricing", default=str(ROOT / "config" / "pricing_snapshot.json"))
    args = p.parse_args()

    run_dir = ROOT / "evidence" / "runs" / args.run_id
    baseline_path = run_dir / "baseline_summary.json"
    aws_path = run_dir / "aws_summary.json"
    out_path = run_dir / "cost_analysis.json"

    if not baseline_path.exists() or not aws_path.exists():
        raise SystemExit("Baseline/AWS summaries are required before cost analysis.")

    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    aws = json.loads(aws_path.read_text(encoding="utf-8"))
    try:
        snap = load_price(Path(args.pricing))
    except Exception as exc:
        out_path.write_text(json.dumps({"status": "HOLD", "reason": str(exc)}, indent=2), encoding="utf-8")
        print(out_path)
        return 3

    required = {
        "lambda_request": price(snap, "lambda_request"),
        "lambda_gb_second": price(snap, "lambda_gb_second"),
        "api_gateway_request": price(snap, "api_gateway_request"),
        "sqs_request": price(snap, "sqs_request"),
        "s3_put_request": price(snap, "s3_put_request"),
        "dynamodb_write": price(snap, "dynamodb_write"),
        "ec2_hour": price(snap, "ec2_t3_micro_linux_hour"),
    }
    missing = [k for k, v in required.items() if v is None]
    if missing:
        out_path.write_text(json.dumps({"status": "HOLD", "reason": "missing normalized pricing", "missing": missing}, indent=2), encoding="utf-8")
        print(out_path)
        return 3

    start = parse_dt(aws["started_at"]) - timedelta(seconds=5)
    # Transformer can finish after the API workload completes.
    end = parse_dt(aws["ended_at"]) + timedelta(seconds=90)
    logs = boto3.client("logs", region_name=RUNTIME["aws_region"])
    ingest_usage = lambda_usage(logs, f"/aws/lambda/{RUNTIME['ingestion_function']}", start, end)
    transform_usage = lambda_usage(logs, f"/aws/lambda/{RUNTIME['transformer_function']}", start, end)

    lambda_invocations = ingest_usage["invocations_from_report_lines"] + transform_usage["invocations_from_report_lines"]
    lambda_gb_seconds = ingest_usage["gb_seconds"] + transform_usage["gb_seconds"]
    accepted = int(aws.get("success_count", 0))
    attempted = int(aws.get("count", accepted))

    # SQS billing includes API actions. The exact receive/delete batch mix is not exposed as one immediate per-run billing metric,
    # so this is a declared conservative bound of two billable SQS requests per accepted event.
    sqs_request_upper_bound = accepted * 2
    s3_puts = accepted
    ddb_writes = accepted

    component_costs = {
        "api_gateway": attempted * required["api_gateway_request"],
        "lambda_requests": lambda_invocations * required["lambda_request"],
        "lambda_compute": lambda_gb_seconds * required["lambda_gb_second"],
        "sqs_upper_bound": sqs_request_upper_bound * required["sqs_request"],
        "s3_put_upper_bound": s3_puts * required["s3_put_request"],
        "dynamodb_write_upper_bound": ddb_writes * required["dynamodb_write"],
    }
    serverless_total = sum(component_costs.values())
    baseline_elapsed = float(baseline.get("elapsed_seconds", 0.0))
    baseline_modeled_cost = (baseline_elapsed / 3600.0) * required["ec2_hour"]

    result = {
        "status": "OK",
        "run_id": args.run_id,
        "pricing_snapshot": str(Path(args.pricing).relative_to(ROOT)),
        "serverless": {
            "attempted_events": attempted,
            "accepted_events": accepted,
            "lambda_ingestion_usage": ingest_usage,
            "lambda_transformer_usage": transform_usage,
            "component_cost_usd": {k: round(v, 10) for k, v in component_costs.items()},
            "estimated_total_usd": round(serverless_total, 10),
            "estimated_cost_per_accepted_event_usd": round(serverless_total / accepted, 12) if accepted else None,
            "measurement_note": "Lambda request count and billed GB-seconds are parsed from CloudWatch REPORT lines in the run window. SQS/S3/DynamoDB request counts are conservative declared bounds based on accepted events."
        },
        "always_on_baseline": {
            "measured_elapsed_seconds": baseline_elapsed,
            "modeled_instance": "t3.micro Linux on-demand",
            "captured_hourly_rate_usd": required["ec2_hour"],
            "modeled_cost_for_measured_run_usd": round(baseline_modeled_cost, 10),
            "modeled_cost_per_successful_event_usd": round(baseline_modeled_cost / int(baseline.get("success_count", 0)), 12) if int(baseline.get("success_count", 0)) else None,
            "measurement_note": "Performance is measured locally; cost is modeled using the captured EC2 on-demand hourly price. Do not label this baseline cost as an AWS-billed measurement."
        },
        "limitations": [
            "AWS billing tiers/free tier/taxes and data-transfer charges can differ from this per-run estimate.",
            "CloudWatch log window must not overlap unrelated project traffic for clean attribution.",
            "The baseline cost is modeled, not an observed AWS invoice."
        ]
    }
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"COST_ANALYSIS={out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
