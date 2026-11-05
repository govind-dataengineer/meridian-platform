"""Write a RunResult into the landing database in ONE transaction.

Tables:
  ingest_runs, ingest_findings      -> audit trail of every run
  stg_orders / stg_support_cases /  -> rows that passed every rule
  stg_issue_records
  review_queue                      -> rows a person must decide (HUMAN_REVIEW)
  rejected_records                  -> rows that failed, kept with their reasons

Idempotency (VR-009): the same content hash is never published twice, and a
re-delivered key replaces its earlier staged row instead of duplicating it.
SQLAlchemy Core keeps this portable (MySQL in the stack, SQLite in unit tests).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import (
    JSON,
    Column,
    Date,
    DateTime,
    Engine,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    delete,
    insert,
    select,
)
from sqlalchemy.engine import Connection

from meridian.ingest import contracts as c
from meridian.ingest.models import LandingBatch, Record, Route, RunResult, RunStatus
from meridian.ingest.rules import parse_iso_date

metadata = MetaData()

ingest_runs = Table(
    "ingest_runs",
    metadata,
    Column("run_id", String(36), primary_key=True),
    Column("source", String(500), nullable=False),
    Column("content_hash", String(64), nullable=False, index=True),
    Column("status", String(20), nullable=False),
    Column("run_at", DateTime, nullable=False),
    Column("finished_at", DateTime, nullable=False),
    Column("summary", JSON, nullable=False),
)

ingest_findings = Table(
    "ingest_findings",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("run_id", String(36), nullable=False, index=True),
    Column("file", String(50), nullable=False),
    Column("row_number", Integer),
    Column("record_key", String(50)),
    Column("rule_id", String(10), nullable=False),
    Column("route", String(20), nullable=False),
    Column("message", Text, nullable=False),
)

stg_orders = Table(
    "stg_orders",
    metadata,
    Column("order_id", String(12), primary_key=True),
    Column("product", String(100), nullable=False),
    Column("order_date", Date, nullable=False),
    Column("delivery_date", Date),
    Column("payment_status", String(20), nullable=False),
    Column("extract_generated_at", DateTime, nullable=False),
    Column("run_id", String(36), nullable=False),
)

stg_support_cases = Table(
    "stg_support_cases",
    metadata,
    Column("case_id", String(12), primary_key=True),
    Column("order_id", String(12)),
    Column("received_at", DateTime, nullable=False),
    Column("customer_question", Text, nullable=False),
    Column("case_type", String(20), nullable=False),
    Column("review_status", String(20), nullable=False),
    Column("extract_generated_at", DateTime, nullable=False),
    Column("run_id", String(36), nullable=False),
)

stg_issue_records = Table(
    "stg_issue_records",
    metadata,
    Column("case_id", String(12), primary_key=True),
    Column("issue_type", String(30), nullable=False),
    Column("issue_details", Text, nullable=False),
    Column("reported_delivery_date", Date),
    Column("evidence_status", String(20), nullable=False),
    Column("extract_generated_at", DateTime, nullable=False),
    Column("run_id", String(36), nullable=False),
)

review_queue = Table(
    "review_queue",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("run_id", String(36), nullable=False, index=True),
    Column("file", String(50), nullable=False),
    Column("record_key", String(50)),
    Column("payload", JSON, nullable=False),
    Column("reasons", JSON, nullable=False),
    Column("status", String(20), nullable=False, default="OPEN"),
)

rejected_records = Table(
    "rejected_records",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("run_id", String(36), nullable=False, index=True),
    Column("file", String(50), nullable=False),
    Column("row_number", Integer, nullable=False),
    Column("record_key", String(50)),
    Column("payload", JSON, nullable=False),
    Column("reasons", JSON, nullable=False),
)

STAGING = {c.ORDERS: stg_orders, c.CASES: stg_support_cases, c.ISSUES: stg_issue_records}


def create_tables(engine: Engine) -> None:
    metadata.create_all(engine)


def _utc_naive(text: str) -> datetime:
    """MySQL DATETIME has no time zone, so store everything as naive UTC."""
    dt = datetime.fromisoformat(text.strip())
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC).replace(tzinfo=None)
    return dt


def _staged_row(record: Record, run_id: str) -> dict[str, Any]:
    d = {k: v.strip() for k, v in record.data.items()}
    row: dict[str, Any] = dict(
        d, run_id=run_id, extract_generated_at=_utc_naive(d["extract_generated_at"])
    )
    if record.file == c.ORDERS:
        row["order_date"] = parse_iso_date(d["order_date"])
        row["delivery_date"] = parse_iso_date(d["delivery_date"]) if d["delivery_date"] else None
    elif record.file == c.CASES:
        row["order_id"] = d["order_id"] or None
        row["received_at"] = _utc_naive(d["received_at"])
    else:
        rdd = d["reported_delivery_date"]
        row["reported_delivery_date"] = parse_iso_date(rdd) if rdd else None
    allowed = set(STAGING[record.file].c.keys())
    return {k: v for k, v in row.items() if k in allowed}


def _reasons(record: Record) -> list[dict[str, str]]:
    return [{"rule_id": f.rule_id, "route": f.route, "message": f.message} for f in record.findings]


def already_published(conn: Connection, content_hash: str) -> str | None:
    q = select(ingest_runs.c.run_id).where(
        ingest_runs.c.content_hash == content_hash,
        ingest_runs.c.status == RunStatus.PUBLISHED.value,
    )
    return conn.execute(q).scalar_one_or_none()


def persist(
    engine: Engine, batch: LandingBatch, result: RunResult, run_at: datetime
) -> tuple[str, RunResult]:
    """Store the run. Returns (run_id, result) — result.status may become DUPLICATE."""
    log = structlog.get_logger()
    run_id = str(uuid.uuid4())
    log.info("db.persist_start", run_id=run_id, status=result.status.value)
    with engine.begin() as conn:  # one transaction: all of it lands, or none of it
        if result.status is RunStatus.PUBLISHED and already_published(conn, batch.content_hash):
            result = RunResult(RunStatus.DUPLICATE, result.records, result.file_findings)

        conn.execute(
            insert(ingest_runs).values(
                run_id=run_id,
                source=batch.source,
                content_hash=batch.content_hash,
                status=result.status.value,
                run_at=run_at.astimezone(UTC).replace(tzinfo=None),
                finished_at=datetime.now(UTC).replace(tzinfo=None),
                summary=result.summary(),
            )
        )

        findings = list(result.file_findings) + [f for r in result.records for f in r.findings]
        if findings:
            conn.execute(
                insert(ingest_findings),
                [
                    dict(
                        run_id=run_id,
                        file=f.file,
                        row_number=f.row_number,
                        record_key=f.record_key,
                        rule_id=f.rule_id,
                        route=f.route,
                        message=f.message,
                    )
                    for f in findings
                ],
            )

        if result.status is not RunStatus.PUBLISHED:
            log.info("db.persist_skip", status=result.status.value)
            return run_id, result

        for file, table in STAGING.items():
            good = [r for r in result.records if r.file == file and r.route is Route.PUBLISH]
            if not good:
                continue
            key_col = table.c[c.KEY_FIELD[file]]
            conn.execute(delete(table).where(key_col.in_([r.key for r in good])))
            conn.execute(insert(table), [_staged_row(r, run_id) for r in good])
            log.info("db.staged", table=table.name, rows=len(good))

        review = [r for r in result.records if r.route is Route.HUMAN_REVIEW]
        if review:
            conn.execute(
                insert(review_queue),
                [
                    dict(
                        run_id=run_id,
                        file=r.file,
                        record_key=r.key or None,
                        payload=r.data,
                        reasons=_reasons(r),
                        status="OPEN",
                    )
                    for r in review
                ],
            )

        rejected = [r for r in result.records if r.route is Route.REJECT]
        if rejected:
            conn.execute(
                insert(rejected_records),
                [
                    dict(
                        run_id=run_id,
                        file=r.file,
                        row_number=r.row_number,
                        record_key=r.key or None,
                        payload=r.data,
                        reasons=_reasons(r),
                    )
                    for r in rejected
                ],
            )
    log.info("db.persist_ok", run_id=run_id)
    return run_id, result
