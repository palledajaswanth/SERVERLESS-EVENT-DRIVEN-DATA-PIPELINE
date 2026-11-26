import json
import math
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import boto3
from botocore.exceptions import ClientError

s3 = boto3.client("s3")
sqs = boto3.client("sqs")
dynamodb = boto3.resource("dynamodb")

BUCKET = os.environ["OUTPUT_BUCKET"]
TABLE_NAME = os.environ["IDEMPOTENCY_TABLE"]
DLQ_URL = os.environ["DLQ_URL"]
table = dynamodb.Table(TABLE_NAME)


def _quality_validate(event: dict[str, Any]) -> None:
    value = event.get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("value_must_be_numeric")
    value_float = float(value)
    if not math.isfinite(value_float):
        raise ValueError("value_must_be_finite")
    if value_float < -1_000_000 or value_float > 1_000_000:
        raise ValueError("value_out_of_range")


def _object_key(event: dict[str, Any]) -> str:
    timestamp = str(event["timestamp"]).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(timestamp)
    except ValueError:
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    safe_type = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(event["event_type"]))[:64]
    return f"events/year={dt:%Y}/month={dt:%m}/day={dt:%d}/type={safe_type}/{event['event_id']}.json"


def _put_idempotent_s3(key: str, body: bytes, metadata: dict[str, str]) -> str:
    try:
        response = s3.put_object(
            Bucket=BUCKET,
            Key=key,
            Body=body,
            ContentType="application/json",
            Metadata=metadata,
            ServerSideEncryption="AES256",
            IfNoneMatch="*",
        )
        return response.get("ETag", "").strip('"')
    except ClientError as exc:
        code = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        err = exc.response.get("Error", {}).get("Code", "")
        if code == 412 or err in {"PreconditionFailed", "ConditionalRequestConflict"}:
            head = s3.head_object(Bucket=BUCKET, Key=key)
            return head.get("ETag", "").strip('"')
        raise


def _record_status(event: dict[str, Any], key: str, etag: str, sqs_message_id: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    table.put_item(Item={
        "event_id": event["event_id"],
        "event_type": event["event_type"],
        "s3_key": key,
        "etag": etag,
        "status": "STORED",
        "stored_at": now,
        "source_message_id": sqs_message_id,
        "value": Decimal(str(event["value"])),
    })


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    failures: list[dict[str, str]] = []
    for record in event.get("Records", []):
        message_id = record.get("messageId", "unknown")
        try:
            envelope = json.loads(record["body"])
            payload = envelope["event"]
            _quality_validate(payload)

            transformed = {
                "schema_version": "1.0",
                "event_id": payload["event_id"],
                "event_type": payload["event_type"],
                "event_timestamp": payload["timestamp"],
                "value": float(payload["value"]),
                "source": payload.get("source", "simulator"),
                "received_at": envelope.get("received_at"),
                "processed_at": datetime.now(timezone.utc).isoformat(),
                "processor_request_id": getattr(context, "aws_request_id", "local"),
            }

            key = _object_key(payload)
            body = json.dumps(transformed, separators=(",", ":"), sort_keys=True).encode("utf-8")
            etag = _put_idempotent_s3(
                key,
                body,
                {"event-id": payload["event_id"], "event-type": payload["event_type"][:128]},
            )
            _record_status(payload, key, etag, message_id)
            print(json.dumps({"kind": "event_stored", "event_id": payload["event_id"], "s3_key": key, "etag": etag}))
        except ValueError as exc:
            # Deterministic schema/quality failures are dead-lettered immediately; retrying the payload cannot repair it.
            # If the DLQ write itself fails transiently, retry only this source record through partial batch failure.
            try:
                sqs.send_message(
                    QueueUrl=DLQ_URL,
                    MessageBody=record.get("body", "{}"),
                    MessageAttributes={
                        "failure_reason": {"DataType": "String", "StringValue": str(exc)[:256]},
                        "source_message_id": {"DataType": "String", "StringValue": message_id[:256]},
                    },
                )
                print(json.dumps({"kind": "quality_dead_letter", "message_id": message_id, "error": str(exc)}))
            except Exception as dlq_exc:
                print(json.dumps({"kind": "dlq_write_failure", "message_id": message_id, "error": repr(dlq_exc)}))
                failures.append({"itemIdentifier": message_id})
        except Exception as exc:
            # Transient/infrastructure failures remain retryable through Lambda's partial batch failure contract.
            print(json.dumps({"kind": "transform_failure", "message_id": message_id, "error": repr(exc)}))
            failures.append({"itemIdentifier": message_id})

    return {"batchItemFailures": failures}
