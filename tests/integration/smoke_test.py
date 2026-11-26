from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import boto3
import httpx

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = json.loads((ROOT / "config" / "runtime.json").read_text(encoding="utf-8"))


def main() -> int:
    event_id = f"smoke-{int(time.time())}"
    event = {"event_id": event_id, "event_type": "smoke", "timestamp": datetime.now(timezone.utc).isoformat(), "value": 1.0, "source": "smoke-test"}
    r = None
    for attempt in range(5):
        try:
            r = httpx.post(RUNTIME["api_url"], json=event, timeout=30.0)
            if 200 <= r.status_code < 300:
                break
        except Exception:
            pass
        time.sleep(2 + attempt)
    assert r is not None and 200 <= r.status_code < 300, (r.text if r is not None else "API request failed")
    ddb = boto3.resource("dynamodb", region_name=RUNTIME["aws_region"]).Table(RUNTIME["dynamodb_table"])
    deadline = time.time() + 60
    item = None
    while time.time() < deadline:
        item = ddb.get_item(Key={"event_id": event_id}).get("Item")
        if item and item.get("status") == "STORED": break
        time.sleep(2)
    assert item and item.get("status") == "STORED", "event did not reach STORED state"
    print(json.dumps({"ok": True, "event_id": event_id, "s3_key": item.get("s3_key")}, default=str))
    return 0

if __name__ == "__main__": raise SystemExit(main())
