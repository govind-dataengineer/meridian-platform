"""Read a delivery from a local folder or an S3 prefix (Floci locally, AWS later)."""

from __future__ import annotations

import csv
import hashlib
import io
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from meridian.ingest.contracts import REQUIRED_COLUMNS
from meridian.ingest.models import LandingBatch, Row

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


def _parse(raw: bytes) -> tuple[list[str], list[Row]]:
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    rows = [{k: (v or "") for k, v in row.items() if k is not None} for row in reader]
    return list(reader.fieldnames or []), rows


def _build(source: str, blobs: dict[str, bytes]) -> LandingBatch:
    log = structlog.get_logger()
    digest = hashlib.sha256()
    files: dict[str, list[Row]] = {}
    columns: dict[str, list[str]] = {}
    for name in sorted(blobs):
        digest.update(name.encode() + b"\0" + blobs[name] + b"\0")
        columns[name], files[name] = _parse(blobs[name])
    batch = LandingBatch(source, digest.hexdigest(), files, columns)
    log.info(
        "source.read",
        source=source,
        files=list(files.keys()),
        content_hash=batch.content_hash[:12],
    )
    return batch


def from_directory(path: Path) -> LandingBatch:
    blobs = {
        name: (path / name).read_bytes() for name in REQUIRED_COLUMNS if (path / name).exists()
    }
    return _build(str(path), blobs)


def from_s3(client: S3Client, bucket: str, prefix: str) -> LandingBatch:
    prefix = prefix.strip("/")
    blobs: dict[str, bytes] = {}
    for name in REQUIRED_COLUMNS:
        key = f"{prefix}/{name}" if prefix else name
        try:
            blobs[name] = client.get_object(Bucket=bucket, Key=key)["Body"].read()
        except client.exceptions.NoSuchKey:
            continue  # VR-007 will report the missing file
    return _build(f"s3://{bucket}/{prefix}", blobs)
