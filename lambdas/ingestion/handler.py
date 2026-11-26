import json
import os
import time
from datetime import datetime, timezone
from typing import Any

import boto3

sqs = boto3.client("sqs")
QUEUE_URL = os.environ["QUEUE_URL"]

REQUIRED_FIELDS = ("event_id", "event_type", "timestamp", "value")


def _response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body, separators=(",", ":")),
    }


def _parse_body(event: dict[str, Any]) -> dict[str, Any]:
    body = event.get("body", event)
    if isinstance(body, str):
        body = json.loads(body)
    if not isinstance(body, dict):
        raise ValueError("JSON object expected")
    return body


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        payload = _parse_body(event)
    except Exception as exc:
        return _response(400, {"ok": False, "error": f"invalid_json: {exc}"})

    missing = [key for key in REQUIRED_FIELDS if key not in payload]
    if missing:
        return _response(400, {"ok": False, "error": "missing_fields", "fields": missing})

    if not isinstance(payload["event_id"], str) or not payload["event_id"].strip():
        return _response(400, {"ok": False, "error": "invalid_event_id"})
    if not isinstance(payload["event_type"], str) or not payload["event_type"].strip():
        return _response(400, {"ok": False, "error": "invalid_event_type"})

    envelope = {
        "schema_version": "1.0",
        "received_at": datetime.now(timezone.utc).isoformat(),
        "request_id": getattr(context, "aws_request_id", "local"),
        "event": payload,
    }

    result = sqs.send_message(
        QueueUrl=QUEUE_URL,
        MessageBody=json.dumps(envelope, separators=(",", ":")),
        MessageAttributes={
            "event_type": {"DataType": "String", "StringValue": payload["event_type"][:256]},
        },
    )

    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    print(json.dumps({
        "kind": "ingestion_accept",
        "event_id": payload["event_id"],
        "sqs_message_id": result.get("MessageId"),
        "latency_ms": elapsed_ms,
    }))

    return _response(202, {
        "ok": True,
        "status": "accepted",
        "event_id": payload["event_id"],
        "message_id": result.get("MessageId"),
    })
