"""Read-only audit for D4 terminal consistency in persisted AirSim outputs."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AirSimTerminalConsistencyAudit:
    control_row_count: int
    control_d4_terminal_inconsistent_count: int
    d4_event_count: int
    terminal_inconsistent_count: int
    terminal_inconsistent_without_hard_risk_count: int
    center_current_coalition_safe_false_count: int
    hard_fail_closed_count: int

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


def audit_airsim_terminal_consistency(
    control_commands_csv: str | Path,
    main_episode_bus_jsonl: str | Path,
) -> AirSimTerminalConsistencyAudit:
    """Summarize persisted D4 evidence without changing or reindexing it."""

    control_rows = 0
    control_rejects = 0
    with Path(control_commands_csv).open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            control_rows += 1
            if row.get("terminal_contract_reject_reason") == "d4_terminal_inconsistent":
                control_rejects += 1

    d4_events = 0
    inconsistent = 0
    inconsistent_without_hard = 0
    center_current_safe_false = 0
    hard_fail_closed = 0
    with Path(main_episode_bus_jsonl).open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("record_type") != "event":
                continue
            payload = _mapping(record.get("payload"))
            metadata = _mapping(payload.get("metadata"))
            if metadata.get("arbitration_source") != "d4_arbitration_adapter":
                continue
            d4_events += 1
            hard_risks = tuple(metadata.get("hard_risk_factors") or ())
            terminal_consistent = metadata.get("terminal_consistent") is True
            if not terminal_consistent:
                inconsistent += 1
                if not hard_risks:
                    inconsistent_without_hard += 1
                    if (
                        metadata.get("active_plan_owner") == "center"
                        and metadata.get("coalition_safe_to_execute") is True
                    ):
                        center_current_safe_false += 1
                else:
                    hard_fail_closed += 1

    return AirSimTerminalConsistencyAudit(
        control_row_count=control_rows,
        control_d4_terminal_inconsistent_count=control_rejects,
        d4_event_count=d4_events,
        terminal_inconsistent_count=inconsistent,
        terminal_inconsistent_without_hard_risk_count=inconsistent_without_hard,
        center_current_coalition_safe_false_count=center_current_safe_false,
        hard_fail_closed_count=hard_fail_closed,
    )


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}
