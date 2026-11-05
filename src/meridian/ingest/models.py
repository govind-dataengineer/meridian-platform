"""Plain data types shared by the pipeline. No I/O here."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum, StrEnum
from typing import Any

Row = dict[str, str]


class Route(IntEnum):
    """Where a record goes. Higher value wins when several rules fire."""

    PUBLISH = 0
    HUMAN_REVIEW = 1
    REJECT = 2


class RunStatus(StrEnum):
    PUBLISHED = "PUBLISHED"
    PAUSED = "PAUSED"  # VR-007: schema contract broken, nothing published
    DUPLICATE = "DUPLICATE"  # VR-009: same content already published


@dataclass(frozen=True)
class Finding:
    rule_id: str
    route: str  # REJECT | HUMAN_REVIEW | LOAD_WARNING | PAUSE_LOAD
    file: str
    message: str
    row_number: int | None = None
    record_key: str | None = None


@dataclass
class Record:
    file: str
    row_number: int  # 1-based data row (header excluded), stable even when keys are blank
    data: Row
    key_field: str
    findings: list[Finding] = field(default_factory=list)

    @property
    def key(self) -> str:
        return self.data.get(self.key_field, "").strip()

    @property
    def route(self) -> Route:
        worst = Route.PUBLISH
        for f in self.findings:
            if f.route in Route.__members__:
                worst = max(worst, Route[f.route])
        return worst

    def flag(self, rule_id: str, route: Route, message: str) -> None:
        self.findings.append(
            Finding(rule_id, route.name, self.file, message, self.row_number, self.key or None)
        )


@dataclass
class LandingBatch:
    """The files of one delivery, already parsed, plus a hash of their exact bytes."""

    source: str
    content_hash: str
    files: dict[str, list[Row]]
    columns: dict[str, list[str]]


@dataclass
class RunResult:
    status: RunStatus
    records: list[Record]
    file_findings: list[Finding]

    def by_file(self, file: str) -> list[Record]:
        return [r for r in self.records if r.file == file]

    def summary(self) -> dict[str, Any]:
        out: dict[str, Any] = {"status": self.status.value, "files": {}}
        for r in self.records:
            counts = out["files"].setdefault(r.file, {k.name: 0 for k in Route})
            counts[r.route.name] += 1
        out["warnings"] = [f.message for f in self.file_findings if f.route == "LOAD_WARNING"]
        return out
