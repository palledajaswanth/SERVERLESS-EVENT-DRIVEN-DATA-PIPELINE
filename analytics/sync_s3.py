from __future__ import annotations

import argparse
import json
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = json.loads((ROOT / "config" / "runtime.json").read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(ROOT / "analytics" / "data" / "events"))
    parser.add_argument("--prefix", default="events/")
    args = parser.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    for stale in out.glob("*.json"):
        stale.unlink()

    s3 = boto3.client("s3", region_name=RUNTIME["aws_region"])
    bucket = RUNTIME["bucket_name"]
    paginator = s3.get_paginator("list_objects_v2")
    count = 0
    for page in paginator.paginate(Bucket=bucket, Prefix=args.prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if not key.endswith(".json"):
                continue
            dest = out / key.replace("/", "__")
            s3.download_file(bucket, key, str(dest))
            count += 1
    print(f"Downloaded {count} event objects from s3://{bucket}/{args.prefix} to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
