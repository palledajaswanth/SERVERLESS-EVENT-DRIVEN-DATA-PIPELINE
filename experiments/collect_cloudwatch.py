from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = json.loads((ROOT / "config" / "runtime.json").read_text(encoding="utf-8"))


def metric(cw, fn: str, name: str, statistic: str, start, end):
    resp = cw.get_metric_statistics(
        Namespace="AWS/Lambda", MetricName=name,
        Dimensions=[{"Name": "FunctionName", "Value": fn}],
        StartTime=start, EndTime=end, Period=60,
        Statistics=[statistic],
    )
    return sorted(resp.get("Datapoints", []), key=lambda x: x["Timestamp"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--minutes", type=int, default=30)
    parser.add_argument("--run-id", default=datetime.now(timezone.utc).strftime("cw-%Y%m%dT%H%M%SZ"))
    args = parser.parse_args()
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=args.minutes)
    cw = boto3.client("cloudwatch", region_name=RUNTIME["aws_region"])
    result = {"start": start.isoformat(), "end": end.isoformat(), "functions": {}}
    for fn in [RUNTIME["ingestion_function"], RUNTIME["transformer_function"]]:
        result["functions"][fn] = {
            "invocations": metric(cw, fn, "Invocations", "Sum", start, end),
            "errors": metric(cw, fn, "Errors", "Sum", start, end),
            "duration_sum_ms": metric(cw, fn, "Duration", "Sum", start, end),
            "duration_average_ms": metric(cw, fn, "Duration", "Average", start, end),
        }
    out = ROOT / "evidence" / "runs" / args.run_id
    out.mkdir(parents=True, exist_ok=True)
    path = out / "cloudwatch_metrics.json"
    path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"CLOUDWATCH={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
