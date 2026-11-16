"""Load UC4 cases, logs, metrics and changes once, and look things up in them.

Everything is read on first use and cached (lru_cache), so repeated calls are cheap.
Rows keep the data's own field names; we only add parsed timestamps next to them.
"""
import csv
import json
from bisect import bisect_left, bisect_right
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from typing import Any

from app.uc4.models import Case
from app.uc4.settings import data_path


def parse_ts(value: str) -> datetime:
    """Parse '2026-10-15T05:17:22.435Z' into a timezone-aware datetime."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@dataclass
class _TimeIndex:
    """Rows sorted by time, so a time range is two binary searches."""

    times: list[datetime] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)

    def between(self, start: datetime, end: datetime, end_inclusive: bool) -> list[dict[str, Any]]:
        lo = bisect_left(self.times, start)
        hi = bisect_right(self.times, end) if end_inclusive else bisect_left(self.times, end)
        return self.rows[lo:hi]


def _build_index(rows: list[dict[str, Any]], key) -> dict[Any, _TimeIndex]:
    groups: dict[Any, list[tuple[datetime, dict[str, Any]]]] = defaultdict(list)
    for row in rows:
        groups[key(row)].append((parse_ts(row["ts"]), row))
    index = {}
    for k, pairs in groups.items():
        pairs.sort(key=lambda p: p[0])
        index[k] = _TimeIndex([p[0] for p in pairs], [p[1] for p in pairs])
    return index


def _read_jsonl(name: str) -> list[dict[str, Any]]:
    with open(data_path(name), encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# ---------- cases ----------

@lru_cache(maxsize=1)
def load_cases() -> dict[str, Case]:
    """All cases by case_id, in file order."""
    return {row["case_id"]: Case.model_validate(row) for row in _read_jsonl("cases")}


def get_case(case_id: str) -> Case:
    """One case by case_id. Raises KeyError if unknown."""
    cases = load_cases()
    if case_id not in cases:
        raise KeyError(f"unknown case_id: {case_id}")
    return cases[case_id]


# ---------- request logs ----------

@lru_cache(maxsize=1)
def _logs() -> tuple[dict[str, _TimeIndex], dict[str, list[dict[str, Any]]]]:
    rows = _read_jsonl("logs")
    by_route = _build_index(rows, key=lambda r: r["route"])
    by_cid: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_cid[row["correlation_id"]].append(row)
    return by_route, dict(by_cid)


def logs_for_route(route: str, start: datetime, end: datetime, end_inclusive: bool = True) -> list[dict[str, Any]]:
    """Request log rows for one route with start <= ts <= end (or < end), sorted by ts."""
    index = _logs()[0].get(route)
    return index.between(start, end, end_inclusive) if index else []


def logs_by_correlation_id(correlation_id: str) -> list[dict[str, Any]]:
    """Request log rows with this correlation_id (usually one)."""
    return list(_logs()[1].get(correlation_id, []))


# ---------- metrics ----------

_METRIC_NUMBERS = ("rps", "error_rate", "p50_ms", "p95_ms")


@lru_cache(maxsize=1)
def _metrics() -> dict[tuple[str, str], _TimeIndex]:
    with open(data_path("metrics"), encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        for col in _METRIC_NUMBERS:
            row[col] = float(row[col]) if row[col] not in ("", None) else None
    return _build_index(rows, key=lambda r: (r["kind"], r["target"]))


def metrics_for(kind: str, target: str, start: datetime, end: datetime, end_inclusive: bool = True) -> list[dict[str, Any]]:
    """Per-minute metric rows for one kind ('endpoint' or 'service') and target, in a time range."""
    index = _metrics().get((kind, target))
    return index.between(start, end, end_inclusive) if index else []


# ---------- changes ----------

@lru_cache(maxsize=1)
def _changes() -> _TimeIndex:
    return _build_index(_read_jsonl("changes"), key=lambda r: "all").get("all", _TimeIndex())


def changes_between(start: datetime, end: datetime) -> list[dict[str, Any]]:
    """Deploy and config change events with start <= ts <= end, sorted by ts."""
    return _changes().between(start, end, end_inclusive=True)
