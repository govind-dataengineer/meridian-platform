"""Pure evaluation of one landing batch. Same input -> same output, no I/O."""

from __future__ import annotations

from datetime import datetime

import structlog

from meridian.ingest import contracts as c
from meridian.ingest import rules
from meridian.ingest.models import LandingBatch, Record, Route, RunResult, RunStatus

log = structlog.get_logger()


def _records(batch: LandingBatch, file: str) -> list[Record]:
    return [
        Record(file=file, row_number=i, data=row, key_field=c.KEY_FIELD[file])
        for i, row in enumerate(batch.files[file], start=1)
    ]


def evaluate(batch: LandingBatch, run_at: datetime, freshness_hours: int = 24) -> RunResult:
    log.info("pipeline.evaluate.start", files=list(batch.files.keys()))

    schema_problems = rules.check_schema(batch)
    if schema_problems:
        log.warning("pipeline.schema_fail", problems=len(schema_problems))
        return RunResult(RunStatus.PAUSED, records=[], file_findings=schema_problems)

    orders = _records(batch, c.ORDERS)
    cases = _records(batch, c.CASES)
    issues = _records(batch, c.ISSUES)
    log.info(
        "pipeline.rows_parsed",
        orders=len(orders),
        cases=len(cases),
        issues=len(issues),
    )

    rules.check_delivery_date_format(orders)
    rules.check_case_id_present(cases)
    rules.check_case_id_unique(cases)
    rules.check_order_required(cases)
    rules.check_review_status(cases)
    rules.block_cases_of_failed_orders(orders, cases)
    rules.check_delivery_dates_agree(orders, cases, issues)
    rules.block_issues_of_failed_cases(cases, issues)

    warnings = rules.check_freshness(batch, run_at, freshness_hours)
    all_records = orders + cases + issues
    summary = {r.name: sum(1 for rec in all_records if rec.route is r) for r in Route}
    log.info("pipeline.evaluate.done", **summary)
    return RunResult(RunStatus.PUBLISHED, records=all_records, file_findings=warnings)
