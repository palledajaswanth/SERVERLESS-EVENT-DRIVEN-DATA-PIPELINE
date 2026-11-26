from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

import boto3
from botocore import UNSIGNED
from botocore.client import Config
from botocore.exceptions import ClientError

from common import load_runtime, write_result


def main() -> int:
    p = argparse.ArgumentParser(); p.add_argument("--run-id", required=True)
    args = p.parse_args(); rt = load_runtime()
    s3 = boto3.client("s3", region_name=rt["aws_region"])
    bucket = rt["bucket_name"]
    pab = s3.get_public_access_block(Bucket=bucket)["PublicAccessBlockConfiguration"]
    enc = s3.get_bucket_encryption(Bucket=bucket)["ServerSideEncryptionConfiguration"]["Rules"]
    public_blocked = all(bool(pab.get(k)) for k in ["BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets"])
    encryption_enabled = bool(enc)
    anonymous_denied = True
    try:
        unsigned = boto3.client("s3", region_name=rt["aws_region"], config=Config(signature_version=UNSIGNED))
        unsigned.list_objects_v2(Bucket=bucket, MaxKeys=1)
        anonymous_denied = False
    except Exception:
        anonymous_denied = True
    passed = public_blocked and encryption_enabled and anonymous_denied
    write_result("NT-5", {
        "fixture_id": f"access-control-{args.run_id}",
        "precondition": "Attempt anonymous bucket access and inspect S3 public-access/encryption controls.",
        "expected": "Public access is blocked, anonymous access is denied, and server-side encryption is configured.",
        "observed": {"public_access_block": pab, "anonymous_access_denied": anonymous_denied, "encryption_configured": encryption_enabled},
        "recovery": "Terraform re-apply restores the declared bucket control state if drift is detected.",
        "residual_risk": "This test does not replace an organization-wide IAM/access analyzer review.",
        "status": "PASS" if passed else "FAIL"
    }, args.run_id)
    return 0 if passed else 2

if __name__ == "__main__": raise SystemExit(main())
