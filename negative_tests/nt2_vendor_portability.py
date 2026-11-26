from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import boto3
import httpx

from common import ROOT, load_runtime, write_result


def main() -> int:
    p = argparse.ArgumentParser(); p.add_argument("--run-id", required=True)
    args = p.parse_args()
    runtime = load_runtime()
    outbox = ROOT / "evidence" / "runs" / args.run_id / "portable_outbox.jsonl"
    outbox.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "event_id": f"{args.run_id}-portable-0001", "event_type": "portability",
        "timestamp": datetime.now(timezone.utc).isoformat(), "value": 42.0, "source": "nt2"
    }
    started = time.perf_counter()
    degraded_ok = False
    try:
        httpx.post("http://127.0.0.1:1/events", json=event, timeout=1.0).raise_for_status()
    except Exception:
        outbox.write_text(json.dumps(event) + "\n", encoding="utf-8")
        degraded_ok = outbox.exists()

    replay_status = None
    stored = False
    version_count = None
    try:
        with outbox.open(encoding="utf-8") as f:
            replay_event = json.loads(next(iter(f)).strip())
        r = httpx.post(runtime["api_url"], json=replay_event, timeout=30.0)
        replay_status = r.status_code
        r.raise_for_status()

        ddb = boto3.resource("dynamodb", region_name=runtime["aws_region"]).Table(runtime["dynamodb_table"])
        deadline = time.time() + 60
        item = None
        while time.time() < deadline:
            item = ddb.get_item(Key={"event_id": replay_event["event_id"]}).get("Item")
            if item and item.get("status") == "STORED":
                stored = True
                break
            time.sleep(2)

        # Replay the same event again. Conditional S3 writes must prevent a second object version.
        r2 = httpx.post(runtime["api_url"], json=replay_event, timeout=30.0)
        r2.raise_for_status()
        time.sleep(5)
        if stored and item and item.get("s3_key"):
            s3 = boto3.client("s3", region_name=runtime["aws_region"])
            versions = s3.list_object_versions(Bucket=runtime["bucket_name"], Prefix=str(item["s3_key"]))
            version_count = len([v for v in versions.get("Versions", []) if v.get("Key") == str(item["s3_key"])])
        replay_ok = stored and version_count == 1
    except Exception:
        replay_ok = False
    recovery_s = round(time.perf_counter() - started, 3)
    passed = degraded_ok and replay_ok
    write_result("NT-2", {
        "fixture_id": f"vendor-portability-{args.run_id}",
        "precondition": "Primary endpoint is deliberately unreachable; event schema remains vendor-neutral JSON.",
        "expected": "Client fails closed into a durable local outbox, replays the exact event after recovery, and a duplicate replay does not create a second S3 object version.",
        "observed": {"outbox_created": degraded_ok, "replay_http_status": replay_status, "stored": stored, "s3_object_versions_after_duplicate_replay": version_count},
        "recovery_time_seconds": recovery_s,
        "recovery": "Replay JSONL outbox to the restored AWS API endpoint (or the protocol-compatible local baseline).",
        "residual_risk": "Infrastructure remains AWS-specific; portability demonstrated here is at the event contract/client replay boundary, not zero-effort cloud migration.",
        "status": "PASS" if passed else "FAIL",
    }, args.run_id)
    return 0 if passed else 2

if __name__ == "__main__": raise SystemExit(main())
