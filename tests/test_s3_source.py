"""S3 landing path, faked in-process with moto (no Floci needed for unit tests)."""

import boto3
import pytest
from moto import mock_aws

from meridian.aws import ensure_bucket, upload_directory
from meridian.ingest import sources
from tests.conftest import LANDING


@pytest.fixture
def s3(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    with mock_aws():
        yield boto3.client("s3", region_name="us-east-1")


def test_s3_round_trip_matches_local_hash(s3, batch):
    ensure_bucket(s3, "meridian-landing")
    ensure_bucket(s3, "meridian-landing")  # idempotent
    upload_directory(s3, "meridian-landing", "2026-09-18", LANDING)
    from_s3 = sources.from_s3(s3, "meridian-landing", "2026-09-18")
    assert from_s3.content_hash == batch.content_hash
    assert from_s3.files == batch.files


def test_missing_s3_file_is_reported_not_crashed(s3):
    ensure_bucket(s3, "meridian-landing")
    from_s3 = sources.from_s3(s3, "meridian-landing", "empty-day")
    assert from_s3.files == {}
