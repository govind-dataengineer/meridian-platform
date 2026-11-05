"""The expected outcome of the Class 5 delivery, rule by rule."""

from datetime import timedelta

from meridian.ingest import contracts as c
from meridian.ingest import pipeline
from meridian.ingest.models import Route, RunStatus
from meridian.ingest.rules import parse_iso_date


def routes(result, file):
    return {(r.row_number, r.key): r.route for r in result.by_file(file)}


def rules_for(result, file, key):
    return {f.rule_id for r in result.by_file(file) if r.key == key for f in r.findings}


def test_parse_iso_date_is_strict():
    assert parse_iso_date("2026-09-10") is not None
    assert parse_iso_date("17-09-2026") is None
    assert parse_iso_date("2026-02-30") is None


def test_summary_counts(batch, run_at):
    result = pipeline.evaluate(batch, run_at)
    assert result.status is RunStatus.PUBLISHED
    files = result.summary()["files"]
    assert files[c.ORDERS] == {"PUBLISH": 8, "HUMAN_REVIEW": 0, "REJECT": 1}
    assert files[c.CASES] == {"PUBLISH": 5, "HUMAN_REVIEW": 1, "REJECT": 6}
    assert files[c.ISSUES] == {"PUBLISH": 5, "HUMAN_REVIEW": 1, "REJECT": 4}


def test_bad_delivery_date_blocks_its_bundle(batch, run_at):
    result = pipeline.evaluate(batch, run_at)
    assert rules_for(result, c.ORDERS, "MR-503") == {"VR-005"}
    assert rules_for(result, c.CASES, "MCS-503") == {"VR-005"}
    assert rules_for(result, c.ISSUES, "MCS-503") == {"BUNDLE"}


def test_case_rules(batch, run_at):
    result = pipeline.evaluate(batch, run_at)
    assert rules_for(result, c.CASES, "") == {"VR-001"}
    assert rules_for(result, c.CASES, "MCS-510") == {"VR-002"}
    assert sum(1 for r in result.by_file(c.CASES) if r.key == "MCS-510") == 2
    assert rules_for(result, c.CASES, "MCS-504") == {"VR-003"}
    assert rules_for(result, c.CASES, "MCS-505") == {"VR-004"}
    # GENERAL enquiry with no order is allowed
    assert rules_for(result, c.CASES, "MCS-508") == set()


def test_conflicting_dates_go_to_a_person(batch, run_at):
    result = pipeline.evaluate(batch, run_at)
    case = next(r for r in result.by_file(c.CASES) if r.key == "MCS-502")
    issue = next(r for r in result.by_file(c.ISSUES) if r.key == "MCS-502")
    assert case.route is Route.HUMAN_REVIEW and issue.route is Route.HUMAN_REVIEW
    assert "2026-09-15" in issue.findings[0].message


def test_missing_column_pauses_the_whole_load(batch, run_at):
    batch.columns[c.ORDERS].remove("delivery_date")
    result = pipeline.evaluate(batch, run_at)
    assert result.status is RunStatus.PAUSED
    assert result.records == []
    assert result.file_findings[0].rule_id == "VR-007"


def test_stale_extract_warns_but_still_publishes(batch, run_at):
    result = pipeline.evaluate(batch, run_at + timedelta(days=3))
    assert result.status is RunStatus.PUBLISHED
    assert {f.rule_id for f in result.file_findings} == {"VR-008"}


def test_same_input_same_output(batch, run_at):
    a = pipeline.evaluate(batch, run_at).summary()
    b = pipeline.evaluate(batch, run_at).summary()
    assert a == b
