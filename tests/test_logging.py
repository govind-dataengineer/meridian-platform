"""Tests for structured logging setup."""

from __future__ import annotations

import json
import sys
from io import StringIO

import pytest
import structlog

from meridian.logging import setup_logging


def test_json_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """setup_logging(json=True) produces valid JSON lines to stderr."""
    buf = StringIO()
    monkeypatch.setattr(sys, "stderr", buf)
    structlog.reset_defaults()
    setup_logging(json=True, level="DEBUG")

    log = structlog.get_logger()
    log.info("test.event", key="value")

    line = buf.getvalue().strip().split("\n")[-1]
    data = json.loads(line)
    assert data["event"] == "test.event"
    assert data["key"] == "value"
    assert data["level"] == "info"
    assert "timestamp" in data


def test_text_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """setup_logging(json=False) produces human-readable output."""
    buf = StringIO()
    monkeypatch.setattr(sys, "stderr", buf)
    structlog.reset_defaults()
    setup_logging(json=False, level="DEBUG")

    log = structlog.get_logger()
    log.info("hello.world", count=42)

    output = buf.getvalue()
    assert "hello.world" in output
    assert "42" in output


def test_level_filtering(monkeypatch: pytest.MonkeyPatch) -> None:
    """Messages below the configured level are suppressed."""
    buf = StringIO()
    monkeypatch.setattr(sys, "stderr", buf)
    structlog.reset_defaults()
    setup_logging(json=True, level="WARNING")

    log = structlog.get_logger()
    log.info("should.not.appear")
    log.warning("should.appear")

    lines = [line for line in buf.getvalue().strip().split("\n") if line]
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["event"] == "should.appear"
