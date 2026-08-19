"""Fixture loading for main-owned shared campaign inputs."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Iterable

from center_terminal_cv_campaign.common.contracts import SourceCueRecord, SourceCueTruthLabel
from center_terminal_cv_campaign.common.scenario import (
    CampaignScenario,
    TargetTruth,
    build_source_fixture,
    generate_targets,
)


@dataclass(frozen=True)
class SearchFixture:
    scenario: CampaignScenario
    targets: tuple[TargetTruth, ...]
    source_cues: tuple[SourceCueRecord, ...]
    source_truth_labels: tuple[SourceCueTruthLabel, ...]
    source: str


def build_default_fixture(*, target_count: int, seed: int) -> SearchFixture:
    scenario = CampaignScenario(target_count=target_count, seed=seed)
    targets = generate_targets(scenario)
    cues, labels = build_source_fixture(scenario, targets)
    return SearchFixture(scenario, targets, cues, labels, "generated_common_fixture")


def _read_rows(directory: Path, candidates: Iterable[str]) -> list[dict[str, Any]]:
    for relative in candidates:
        path = directory / relative
        if not path.exists():
            continue
        if path.suffix == ".jsonl":
            return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return payload
        for key in ("records", "rows", "targets", "source_cues", "labels"):
            if isinstance(payload.get(key), list):
                return payload[key]
        raise ValueError(f"fixture file does not contain a row list: {path}")
    raise FileNotFoundError(
        f"fixture directory {directory} lacks any of: {', '.join(candidates)}"
    )


def load_fixture(
    directory: Path,
    *,
    target_count: int | None = None,
    seed: int | None = None,
) -> SearchFixture:
    """Load the shared JSON/JSONL fixture without changing common files.

    Canonical names match ``prepare_campaign.prepare_fixture``. Explicit
    target count or seed values must agree with ``scenario.json``; omitted
    values are inferred from that file.
    """

    directory = Path(directory)
    cue_rows = _read_rows(
        directory,
        ("online/source_cues.jsonl", "source_cues.jsonl", "source_cues.json"),
    )
    label_rows = _read_rows(
        directory,
        (
            "truth/source_cue_labels.jsonl",
            "truth/source_truth_labels.jsonl",
            "source_truth_labels.json",
        ),
    )
    target_rows = _read_rows(
        directory,
        (
            "truth/targets.jsonl",
            "truth/targets.json",
            "targets.json",
            "truth/target_specs.json",
        ),
    )
    scenario_path = directory / "scenario.json"
    scenario_values: dict[str, Any] = {}
    if scenario_path.exists():
        raw = json.loads(scenario_path.read_text(encoding="utf-8"))
        nested = raw.get("scenario", raw)
        allowed = set(CampaignScenario.__dataclass_fields__)
        scenario_values.update({key: value for key, value in nested.items() if key in allowed})
    declared_target_count = scenario_values.get("target_count")
    if (
        target_count is not None
        and declared_target_count is not None
        and int(target_count) != int(declared_target_count)
    ):
        raise ValueError(
            "requested target_count "
            f"{target_count} conflicts with scenario target_count {declared_target_count}"
        )
    resolved_target_count = int(
        target_count
        if target_count is not None
        else (declared_target_count if declared_target_count is not None else len(target_rows))
    )
    declared_seed = scenario_values.get("seed")
    if seed is not None and declared_seed is not None and int(seed) != int(declared_seed):
        raise ValueError(f"requested seed {seed} conflicts with scenario seed {declared_seed}")
    resolved_seed = int(
        seed if seed is not None else (declared_seed if declared_seed is not None else 20260816)
    )
    scenario_values["target_count"] = resolved_target_count
    scenario_values["seed"] = resolved_seed
    scenario = CampaignScenario(**scenario_values)
    targets = tuple(TargetTruth(**row) for row in target_rows)
    cues = tuple(SourceCueRecord(**row) for row in cue_rows)
    labels = tuple(SourceCueTruthLabel(**row) for row in label_rows)
    if len(targets) != scenario.target_count:
        raise ValueError(
            f"fixture has {len(targets)} targets, scenario declares {scenario.target_count}"
        )
    return SearchFixture(scenario, targets, cues, labels, str(directory.resolve()))
