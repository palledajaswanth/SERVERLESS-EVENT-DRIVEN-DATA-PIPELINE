
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone

import boto3

from common import load_runtime, write_result


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", required=True)
    p.add_argument("--wait", type=int, default=90)
    args = p.parse_args()
    rt = load_runtime()

    sqs = boto3.client("sqs", region_name=rt["aws_region"])

    before_attrs = sqs.get_queue_attributes(
        QueueUrl=rt["dlq_url"],
        AttributeNames=["ApproximateNumberOfMessages"]
    )["Attributes"]
    before_dlq = int(before_attrs.get("ApproximateNumberOfMessages", "0"))

    good = 20
    bad = 3

    for i in range(good):
        e = {
            "event": {
                "event_id": f"{args.run_id}-good-{i}",
                "event_type": "healthy",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "value": float(i),
                "source": "nt4"
            },
            "received_at": datetime.now(timezone.utc).isoformat()
        }
        sqs.send_message(
            QueueUrl=rt["queue_url"],
            MessageBody=json.dumps(e)
        )

    for i in range(bad):
        e = {
            "event": {
                "event_id": f"{args.run_id}-bad-{i}",
                "event_type": "defective-partition",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "value": "NOT_NUMERIC",
                "source": "nt4"
            },
            "received_at": datetime.now(timezone.utc).isoformat()
        }
        sqs.send_message(
            QueueUrl=rt["queue_url"],
            MessageBody=json.dumps(e)
        )

    deadline = time.time() + args.wait
    while time.time() < deadline:
        attrs = sqs.get_queue_attributes(
            QueueUrl=rt["dlq_url"],
            AttributeNames=["ApproximateNumberOfMessages"]
        )["Attributes"]
        dlq_count = int(attrs.get("ApproximateNumberOfMessages", "0"))

        if dlq_count - before_dlq >= bad:
            break

        time.sleep(3)

    attrs = sqs.get_queue_attributes(
        QueueUrl=rt["dlq_url"],
        AttributeNames=["ApproximateNumberOfMessages"]
    )["Attributes"]
    dlq_count = int(attrs.get("ApproximateNumberOfMessages", "0"))
    new_dlq = max(0, dlq_count - before_dlq)
    detected = new_dlq >= bad

    write_result("NT-4", {
        "fixture_id": f"partition-quality-{args.run_id}",
        "precondition": {
            "healthy_events": good,
            "defective_partition_events": bad
        },
        "expected": (
            "Invalid partition records are not silently committed; "
            "deterministic quality failures are sent directly to the DLQ "
            "while transient failures remain retryable."
        ),
        "observed": {
            "dlq_before": before_dlq,
            "dlq_after": dlq_count,
            "new_dlq_messages": new_dlq,
            "defective_partition_detected": detected
        },
        "recovery": (
            "Inspect DLQ fixture IDs, correct data, then replay only "
            "remediated records."
        ),
        "residual_risk": (
            "Approximate SQS counts are eventually consistent; publication "
            "runs should retain CloudWatch/log evidence as well."
        ),
        "status": "PASS" if detected else "FAIL"
    }, args.run_id)

    return 0 if detected else 2


if __name__ == "__main__":
    raise SystemExit(main())
