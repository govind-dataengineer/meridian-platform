"""The Class 5 validation rules as small, testable functions.

Python decides; nothing here guesses. Each rule adds a Finding to a Record and
the worst finding decides the route (REJECT > HUMAN_REVIEW > PUBLISH).
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import date, datetime, timedelta

from meridian.ingest import contracts as c
from meridian.ingest.models import Finding, LandingBatch, Record, Route

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_iso_date(text: str) -> date | None:
    """Strict YYYY-MM-DD. Returns None for anything else (e.g. 17-09-2026)."""
    text = text.strip()
    if not _ISO_DATE.match(text):
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:  # e.g. 2026-02-30
        return None


def check_schema(batch: LandingBatch) -> list[Finding]:
    """VR-007: every required file and column exists, otherwise PAUSE_LOAD."""
    problems: list[Finding] = []
    for file, required in c.REQUIRED_COLUMNS.items():
        if file not in batch.files:
            problems.append(Finding("VR-007", "PAUSE_LOAD", file, f"missing file {file}"))
            continue
        missing = [col for col in required if col not in batch.columns[file]]
        if missing:
            problems.append(
                Finding("VR-007", "PAUSE_LOAD", file, f"{file} missing columns {missing}")
            )
    return problems


def check_case_id_present(cases: list[Record]) -> None:
    """VR-001."""
    for r in cases:
        if not r.key:
            r.flag("VR-001", Route.REJECT, "case_id is blank")


def check_case_id_unique(cases: list[Record]) -> None:
    """VR-002: both occurrences of a duplicate fail."""
    counts = Counter(r.key for r in cases if r.key)
    for r in cases:
        if r.key and counts[r.key] > 1:
            r.flag("VR-002", Route.REJECT, f"case_id {r.key} appears {counts[r.key]} times")


def check_order_required(cases: list[Record]) -> None:
    """VR-003: RETURN and DAMAGE cases must reference an order."""
    for r in cases:
        if (
            r.data["case_type"].strip() in c.ORDER_REQUIRED_CASE_TYPES
            and not r.data["order_id"].strip()
        ):
            r.flag("VR-003", Route.REJECT, f"{r.data['case_type']} case has no order_id")


def check_review_status(cases: list[Record]) -> None:
    """VR-004."""
    for r in cases:
        status = r.data["review_status"].strip()
        if status not in c.REVIEW_STATUSES:
            r.flag("VR-004", Route.REJECT, f"unknown review_status {status!r}")


def check_delivery_date_format(orders: list[Record]) -> None:
    """VR-005: a present delivery_date must be a real YYYY-MM-DD date."""
    for r in orders:
        text = r.data["delivery_date"].strip()
        if text and parse_iso_date(text) is None:
            r.flag("VR-005", Route.REJECT, f"delivery_date {text!r} is not YYYY-MM-DD")


def block_cases_of_failed_orders(orders: list[Record], cases: list[Record]) -> None:
    """VR-005 (bundle part): a failed order blocks the cases linked to it."""
    failed = {o.key for o in orders if o.route is Route.REJECT}
    for r in cases:
        oid = r.data["order_id"].strip()
        if oid in failed:
            r.flag("VR-005", Route.REJECT, f"blocked: linked order {oid} failed validation")


def check_delivery_dates_agree(
    orders: list[Record], cases: list[Record], issues: list[Record]
) -> None:
    """VR-006: if order and issue both give a delivery date, they must agree.

    A disagreement is readable, so a person decides: the issue AND its case go
    to HUMAN_REVIEW (the pipeline cannot decide which source owns the truth).
    """
    order_by_id = {o.key: o for o in orders if o.key}
    case_by_id = {r.key: r for r in cases if r.key}
    for issue in issues:
        case = case_by_id.get(issue.key)
        if case is None:
            continue
        order = order_by_id.get(case.data["order_id"].strip())
        if order is None:
            continue
        reported = parse_iso_date(issue.data["reported_delivery_date"])
        recorded = parse_iso_date(order.data["delivery_date"])
        if reported and recorded and reported != recorded:
            msg = f"order {order.key} says {recorded}, issue says {reported}"
            issue.flag("VR-006", Route.HUMAN_REVIEW, msg)
            case.flag("VR-006", Route.HUMAN_REVIEW, msg)


def block_issues_of_failed_cases(cases: list[Record], issues: list[Record]) -> None:
    """An issue cannot publish without a publishable case (keeps the bundle whole)."""
    case_routes: dict[str, Route] = {}
    for r in cases:
        if r.key:
            case_routes[r.key] = max(case_routes.get(r.key, Route.PUBLISH), r.route)
    for issue in issues:
        route = case_routes.get(issue.key)
        if route is None:
            issue.flag("BUNDLE", Route.REJECT, f"no support case {issue.key!r} in this delivery")
        elif route is Route.REJECT:
            issue.flag("BUNDLE", Route.REJECT, f"blocked: case {issue.key} was rejected")


def check_freshness(batch: LandingBatch, run_at: datetime, max_age_hours: int) -> list[Finding]:
    """VR-008: warn (do not block) when a file's extract is older than the window."""
    warnings: list[Finding] = []
    limit = run_at - timedelta(hours=max_age_hours)
    for file, rows in batch.files.items():
        stamps = [
            datetime.fromisoformat(v)
            for row in rows
            if (v := row.get("extract_generated_at", "").strip())
        ]
        if stamps and min(stamps) < limit:
            warnings.append(
                Finding(
                    "VR-008",
                    "LOAD_WARNING",
                    file,
                    f"{file} extract from {min(stamps).isoformat()} is older than "
                    f"{max_age_hours}h before run time {run_at.isoformat()}",
                )
            )
    return warnings
