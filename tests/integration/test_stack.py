"""End-to-end against the real stack: Floci S3 -> pipeline -> MySQL.

Run with:  make up && make test-integration
"""

import uuid

import pytest
from sqlalchemy import create_engine, func, select, text

from meridian.aws import ensure_bucket, s3_client, upload_directory
from meridian.config import get_settings
from meridian.ingest import pipeline, sources, store
from tests.conftest import LANDING

pytestmark = pytest.mark.integration


def test_trusted_database_is_seeded():
    engine = create_engine(get_settings().trusted_db_url)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM orders")).scalar_one() == 20_000
        assert conn.execute(text("SELECT COUNT(*) FROM support_cases")).scalar_one() == 25_000


def test_floci_to_mysql():
    s = get_settings()
    client = s3_client(s)
    ensure_bucket(client, s.landing_bucket)
    prefix = f"it-{uuid.uuid4().hex[:8]}"
    upload_directory(client, s.landing_bucket, prefix, LANDING)

    batch = sources.from_s3(client, s.landing_bucket, prefix)
    engine = create_engine(s.db_url)
    store.create_tables(engine)
    run_id, _ = store.persist(engine, batch, pipeline.evaluate(batch, s.run_at), s.run_at)

    with engine.connect() as conn:
        n = conn.execute(
            select(func.count())
            .select_from(store.ingest_runs)
            .where(store.ingest_runs.c.run_id == run_id)
        ).scalar_one()
        assert n == 1
        assert conn.execute(select(func.count()).select_from(store.stg_orders)).scalar_one() >= 8
