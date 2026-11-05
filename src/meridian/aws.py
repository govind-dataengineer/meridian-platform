"""boto3 clients pointed at Floci locally, or real AWS when the endpoint is unset."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import boto3
from botocore.config import Config

from meridian.config import Settings

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


def s3_client(settings: Settings) -> S3Client:
    if settings.aws_endpoint_url:  # local emulator (Floci)
        return boto3.client(
            "s3",
            endpoint_url=settings.aws_endpoint_url,
            region_name=settings.aws_region,
            aws_access_key_id=settings.local_aws_key,
            aws_secret_access_key=settings.local_aws_secret,
            # path-style (http://floci:4566/bucket) works for any hostname, incl. compose names
            config=Config(s3={"addressing_style": "path"}),
        )
    return boto3.client("s3", region_name=settings.aws_region)  # real AWS


def ensure_bucket(client: S3Client, bucket: str) -> None:
    existing = {b["Name"] for b in client.list_buckets().get("Buckets", [])}
    if bucket not in existing:
        client.create_bucket(Bucket=bucket)


def upload_directory(client: S3Client, bucket: str, prefix: str, folder: Path) -> list[str]:
    keys = []
    for path in sorted(folder.glob("*.csv")):
        key = f"{prefix.strip('/')}/{path.name}"
        client.upload_file(str(path), bucket, key)
        keys.append(key)
    return keys
