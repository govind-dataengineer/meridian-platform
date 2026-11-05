"""Persistence and idempotency (VR-009), using in-memory SQLite."""

import pytest
from sqlalchemy import create_engine, func, select

from meridian.ingest import pipeline, store
from meridian.ingest.models import RunStatus


@pytest.fixture
def engine():
    eng = create_engine("sqlite://")
    store.create_tables(eng)
    return eng


def count(engine, table):
    with engine.connect() as conn:
        return conn.execute(select(func.count()).select_from(table)).scalar_one()


def test_publish_then_rerun_is_a_no_op(engine, batch, run_at):
    _, first = store.persist(engine, batch, pipeline.evaluate(batch, run_at), run_at)
    assert first.status is RunStatus.PUBLISHED
    assert count(engine, store.stg_orders) == 8
    assert count(engine, store.stg_support_cases) == 5
    assert count(engine, store.stg_issue_records) == 5
    assert count(engine, store.review_queue) == 2
    assert count(engine, store.rejected_records) == 11

    _, second = store.persist(engine, batch, pipeline.evaluate(batch, run_at), run_at)
    assert second.status is RunStatus.DUPLICATE
    assert count(engine, store.stg_orders) == 8  # nothing duplicated
    assert count(engine, store.review_queue) == 2
    assert count(engine, store.ingest_runs) == 2  # but the rerun is still audited


def test_paused_run_publishes_nothing(engine, batch, run_at):
    batch.files.pop("orders.csv")
    batch.columns.pop("orders.csv")
    _, result = store.persist(engine, batch, pipeline.evaluate(batch, run_at), run_at)
    assert result.status is RunStatus.PAUSED
    assert count(engine, store.stg_support_cases) == 0
    assert count(engine, store.ingest_findings) == 1
