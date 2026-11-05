from datetime import datetime
from pathlib import Path

import pytest

from meridian.ingest import sources
from meridian.ingest.models import LandingBatch

LANDING = Path(__file__).resolve().parents[1] / "data" / "landing"
RUN_AT = datetime.fromisoformat("2026-09-18T10:30:00+00:00")


@pytest.fixture
def batch() -> LandingBatch:
    """The Class 5 delivery: deliberately messy, so every rule has something to catch."""
    return sources.from_directory(LANDING)


@pytest.fixture
def run_at() -> datetime:
    return RUN_AT
