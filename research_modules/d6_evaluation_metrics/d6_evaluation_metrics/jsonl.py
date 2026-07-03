"""Dry-run JSONL loader for offline D6 evaluation records."""

from __future__ import annotations

from dataclasses import fields
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from .metrics import (
    AssignmentRecord,
    EventRecord,
    LinkRecord,
    MetricsCollector,
    TerminalRecord,
    TrackRecord,
)


def load_episode_log_jsonl(path: str | Path) -> tuple[MetricsCollector, dict[str, Any]]:
    """Load a dry-run episode JSONL file into a passive metrics collector.

    The supported schema is intentionally small and simulator-agnostic:
    each line is a JSON object with ``record_type`` and ``payload`` keys.
    ``record_type`` may be ``truth_summary``, ``track``, ``assignment``,
    ``event``, ``link``, or ``terminal``. Unknown record types are rejected so interface
    tests catch schema drift early.
    """

    collector = MetricsCollector()
    truth_summary: dict[str, Any] = {}
    with Path(path).open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            raw = json.loads(stripped)
            if not isinstance(raw, Mapping):
                raise ValueError(f"line {line_number}: JSONL record must be an object")
            record_type = str(raw.get("record_type", "")).strip().lower()
            payload = raw.get("payload", {})
            if not isinstance(payload, Mapping):
                raise ValueError(f"line {line_number}: payload must be an object")

            if record_type == "truth_summary":
                truth_summary.update(dict(payload))
            elif record_type == "track":
                collector.add_track(TrackRecord(**_filter_payload(TrackRecord, payload)))
            elif record_type == "assignment":
                collector.add_assignment(
                    AssignmentRecord(**_filter_payload(AssignmentRecord, payload))
                )
            elif record_type == "event":
                collector.add_event(EventRecord(**_filter_payload(EventRecord, payload)))
            elif record_type == "link":
                collector.add_link(LinkRecord(**_filter_payload(LinkRecord, payload)))
            elif record_type == "terminal":
                collector.add_terminal(TerminalRecord(**_filter_payload(TerminalRecord, payload)))
            else:
                raise ValueError(f"line {line_number}: unsupported record_type {record_type!r}")
    return collector, truth_summary


def dump_episode_log_jsonl(
    records: Iterable[Mapping[str, Any]],
    path: str | Path,
) -> Path:
    """Write already-normalized dry-run records to JSONL for interface tests."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(dict(record), sort_keys=True) + "\n")
    return path


def _filter_payload(record_cls: type[Any], payload: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {field.name for field in fields(record_cls)}
    return {key: value for key, value in payload.items() if key in allowed}
