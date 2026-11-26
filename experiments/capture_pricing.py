from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError

ROOT = Path(__file__).resolve().parents[1]
PROJECT = json.loads((ROOT / "config" / "project.json").read_text(encoding="utf-8"))
RUNTIME_PATH = ROOT / "config" / "runtime.json"
REGION = (json.loads(RUNTIME_PATH.read_text(encoding="utf-8"))["aws_region"] if RUNTIME_PATH.exists() else PROJECT["aws_region"])

REGION_LOCATIONS = {
    "ap-south-1": "Asia Pacific (Mumbai)",
    "us-east-1": "US East (N. Virginia)",
    "us-east-2": "US East (Ohio)",
    "us-west-2": "US West (Oregon)",
    "eu-west-1": "EU (Ireland)",
    "ap-southeast-1": "Asia Pacific (Singapore)",
}


def products(pricing, service_code: str) -> list[dict]:
    filters = [{"Type": "TERM_MATCH", "Field": "regionCode", "Value": REGION}]
    out = []
    token = None
    for _ in range(8):
        kwargs = {"ServiceCode": service_code, "Filters": filters, "MaxResults": 100}
        if token: kwargs["NextToken"] = token
        resp = pricing.get_products(**kwargs)
        for raw in resp.get("PriceList", []):
            out.append(json.loads(raw))
        token = resp.get("NextToken")
        if not token: break
    return out


def dimensions(items: list[dict]) -> list[dict]:
    rows = []
    for item in items:
        attrs = item.get("product", {}).get("attributes", {})
        for term in item.get("terms", {}).get("OnDemand", {}).values():
            for dim in term.get("priceDimensions", {}).values():
                usd = dim.get("pricePerUnit", {}).get("USD")
                if usd is None: continue
                try: price = float(usd)
                except ValueError: continue
                rows.append({
                    "price_usd": price,
                    "unit": dim.get("unit"),
                    "description": dim.get("description", ""),
                    "begin_range": dim.get("beginRange"),
                    "end_range": dim.get("endRange"),
                    "group": attrs.get("group"),
                    "group_description": attrs.get("groupDescription"),
                    "usage_type": attrs.get("usagetype"),
                    "instance_type": attrs.get("instanceType"),
                    "operating_system": attrs.get("operatingSystem"),
                    "tenancy": attrs.get("tenancy"),
                    "preinstalled_software": attrs.get("preInstalledSw"),
                    "capacitystatus": attrs.get("capacitystatus"),
                })
    return rows


def select(rows: list[dict], *, unit_contains: str | None = None, text_contains: list[str] | None = None) -> dict | None:
    candidates = []
    for r in rows:
        unit = (r.get("unit") or "").lower()
        text = " ".join(str(r.get(k) or "") for k in ["description", "group", "group_description", "usage_type"]).lower()
        if unit_contains and unit_contains.lower() not in unit: continue
        if text_contains and not all(t.lower() in text for t in text_contains): continue
        if r["price_usd"] < 0: continue
        candidates.append(r)
    positive = [c for c in candidates if c["price_usd"] > 0]
    if not positive:
        return candidates[0] if candidates else None
    # For the pre-spend guardrail prefer the highest matching positive tier, which is conservative.
    return max(positive, key=lambda x: x["price_usd"])


def main() -> int:
    pricing = boto3.client("pricing", region_name="us-east-1")
    services = {
        "lambda": "AWSLambda",
        "apigateway": "AmazonApiGateway",
        "sqs": "AWSQueueService",
        "s3": "AmazonS3",
        "dynamodb": "AmazonDynamoDB",
        "ec2": "AmazonEC2",
    }
    raw = {}
    try:
        for name, code in services.items():
            raw[name] = dimensions(products(pricing, code))
    except (BotoCoreError, ClientError) as exc:
        print(f"Pricing API failed: {exc}")
        return 2
    selected = {
        "lambda_request": select(
            [r for r in raw["lambda"] if r.get("usage_type") == "APS3-Request"],
            unit_contains="request",
            text_contains=["request"]
        ),
        "lambda_gb_second": select(
            [r for r in raw["lambda"] if "edge" not in str(r.get("usage_type") or "").lower()
             and "edge" not in str(r.get("group") or "").lower()],
            unit_contains="gb-second",
            text_contains=["compute"]
        ),
        "api_gateway_request": select(
            raw["apigateway"], unit_contains="request", text_contains=["request"]
        ),
        "sqs_request": select(
            [r for r in raw["sqs"] if "fifo" not in str(r.get("usage_type") or "").lower()],
            unit_contains="request", text_contains=["request"]
        ),
        "s3_put_request": select(
            [r for r in raw["s3"] if r.get("usage_type") == "APS3-Requests-Tier1"],
            unit_contains="request", text_contains=["put"]
        ),
        "dynamodb_write": select(
            [r for r in raw["dynamodb"] if "ia" not in str(r.get("usage_type") or "").lower()
             and "infrequent" not in str(r.get("description") or "").lower()],
            unit_contains="request", text_contains=["write"]
        ),
    }
    ec2_candidates = [r for r in raw["ec2"] if r.get("instance_type") == PROJECT["baseline_instance_type_for_cost_model"]
                      and (r.get("operating_system") or "").lower() == "linux"
                      and (r.get("tenancy") or "").lower() == "shared"
                      and (r.get("preinstalled_software") or "").lower() in {"na", "none", ""}
                      and (r.get("capacitystatus") or "").lower() in {"used", ""}
                      and (r.get("unit") or "").lower() in {"hrs", "hours", "hour"}]
    selected["ec2_t3_micro_linux_hour"] = max([r for r in ec2_candidates if r["price_usd"] > 0], key=lambda x: x["price_usd"], default=None)

    # A declared conservative projection used only for NT-3 pre-spend guardrail.
    # Publication cost analysis should use measured invocation/duration evidence.
    def p(name: str) -> float:
        item = selected.get(name)
        return float(item["price_usd"]) if item else 0.0

    per_event = 0.0
    per_event += p("api_gateway_request")
    per_event += p("lambda_request") * 1.1  # 1 ingress + about 0.1 batched transform invocation
    per_event += p("lambda_gb_second") * (0.25 * 0.20 + 0.25 * 0.20 / 10.0)  # declared 200 ms upper-bound assumption
    per_event += p("sqs_request") * 2.0
    per_event += p("s3_put_request")
    per_event += p("dynamodb_write")

    snapshot = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "region": REGION,
        "location": REGION_LOCATIONS.get(REGION),
        "source": "AWS Price List Query API via pricing:GetProducts",
        "selected_price_dimensions": selected,
        "projection_assumptions": {
            "lambda_memory_gb": 0.25,
            "declared_duration_seconds_per_invocation": 0.20,
            "transform_batch_size": 10,
            "sqs_billable_requests_per_event_upper_bound": 2.0,
            "purpose": "NT-3 pre-spend guardrail only; not a substitute for measured cost-per-event."
        },
        "estimated_serverless_usd_per_million_events": round(per_event * 1_000_000, 6) if all(selected.get(k) for k in ["lambda_request", "lambda_gb_second", "api_gateway_request", "sqs_request", "s3_put_request", "dynamodb_write"]) else None,
        "raw_dimensions": raw,
    }
    path = ROOT / "config" / "pricing_snapshot.json"
    path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    print(f"PRICING={path}")
    print(json.dumps({k: v for k, v in snapshot.items() if k != "raw_dimensions"}, indent=2))
    return 0

if __name__ == "__main__": raise SystemExit(main())
