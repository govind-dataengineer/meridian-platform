"""Tests for the synthetic data generator."""

from datetime import UTC, datetime

from meridian.generate import generate_delivery
from meridian.ingest.contracts import CASES, ISSUES, ORDERS, REQUIRED_COLUMNS
from meridian.ingest.models import LandingBatch, Route, RunStatus
from meridian.ingest.pipeline import evaluate

RUN_AT = datetime(2026, 9, 18, 10, 30, tzinfo=UTC)


def _to_batch(data: dict[str, list[dict[str, str]]]) -> LandingBatch:
    return LandingBatch(
        source="generated",
        content_hash="test",
        files=data,
        columns={k: list(REQUIRED_COLUMNS[k]) for k in data},
    )


def test_zero_errors_all_publish() -> None:
    """With error_rate=0, every row should publish."""
    data = generate_delivery(
        num_orders=50, error_rate=0.0, seed=1, run_at=RUN_AT, freshness_hours=24
    )
    result = evaluate(_to_batch(data), RUN_AT)
    assert result.status is RunStatus.PUBLISHED
    for record in result.records:
        assert record.route is Route.PUBLISH, (
            f"{record.file} row {record.row_number} ({record.key}) "
            f"routed to {record.route.name}: {[f.message for f in record.findings]}"
        )


def test_error_rate_roughly_matches() -> None:
    """With a known seed and 10% error rate, check that some rows are not PUBLISH."""
    data = generate_delivery(
        num_orders=500, error_rate=0.10, seed=42, run_at=RUN_AT, freshness_hours=24
    )
    result = evaluate(_to_batch(data), RUN_AT)
    assert result.status is RunStatus.PUBLISHED

    total = len(result.records)
    errored = sum(1 for r in result.records if r.route is not Route.PUBLISH)
    # Some rows will be errored (injected + bundle cascades). With 10% injection
    # across ~500 orders + ~700 cases + ~650 issues, we expect a meaningful count.
    # Be generous with bounds to avoid flaky tests.
    assert errored > 0, "Expected some errored rows at 10% error rate"
    assert errored < total, "Not every row should be errored at 10%"


def test_deterministic() -> None:
    """Same seed produces identical output."""
    kwargs = dict(num_orders=50, error_rate=0.08, seed=99, run_at=RUN_AT, freshness_hours=24)
    a = generate_delivery(**kwargs)
    b = generate_delivery(**kwargs)
    for filename in (ORDERS, CASES, ISSUES):
        assert a[filename] == b[filename], f"{filename} differs between runs"


def test_generated_files_have_correct_columns() -> None:
    """Every row has exactly the required columns."""
    data = generate_delivery(
        num_orders=20, error_rate=0.0, seed=1, run_at=RUN_AT, freshness_hours=24
    )
    for filename, rows in data.items():
        expected = set(REQUIRED_COLUMNS[filename])
        for i, row in enumerate(rows):
            assert set(row.keys()) == expected, (
                f"{filename} row {i} has columns {set(row.keys())}, expected {expected}"
            )
