"""Versioned offline scenario catalogue for reproducible D6 batch reports."""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


VALID_DIFFICULTIES = {"smoke", "nominal", "challenging", "stress"}


@dataclass(frozen=True)
class ScenarioDefinition:
    """Stable scenario identity plus versioned experiment metadata."""

    scenario_group: str
    scenario_version: str
    tags: tuple[str, ...]
    difficulty: str
    expected_failure_modes: tuple[str, ...]
    seeds: tuple[int, ...]
    parameters: Mapping[str, Any] = field(default_factory=dict)
    online_truth_policy: str = "forbidden"

    def __post_init__(self) -> None:
        if not self.scenario_group.strip():
            raise ValueError("scenario_group must be non-empty and stable across seeds")
        if not self.scenario_version.strip():
            raise ValueError("scenario_version must be non-empty")
        if self.difficulty not in VALID_DIFFICULTIES:
            raise ValueError(
                f"difficulty must be one of {sorted(VALID_DIFFICULTIES)}"
            )
        if not self.tags:
            raise ValueError("at least one scenario tag is required")
        if any(not tag.strip() for tag in self.tags) or len(set(self.tags)) != len(self.tags):
            raise ValueError("tags must be unique non-empty strings")
        if len(set(self.expected_failure_modes)) != len(self.expected_failure_modes):
            raise ValueError("expected_failure_modes must be unique")
        if not self.seeds:
            raise ValueError("at least one seed is required")
        if len(set(self.seeds)) != len(self.seeds) or any(seed < 0 for seed in self.seeds):
            raise ValueError("seeds must be unique non-negative integers")
        if self.online_truth_policy != "forbidden":
            raise ValueError("online_truth_policy must remain 'forbidden'")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["tags"] = list(self.tags)
        payload["expected_failure_modes"] = list(self.expected_failure_modes)
        payload["seeds"] = list(self.seeds)
        payload["parameters"] = dict(self.parameters)
        return payload


class ScenarioLibrary:
    """Validate and serialize a deterministic seed matrix without running AirSim."""

    def __init__(self, scenarios: Iterable[ScenarioDefinition]) -> None:
        self.scenarios = tuple(scenarios)
        keys = [
            (scenario.scenario_group, scenario.scenario_version)
            for scenario in self.scenarios
        ]
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate scenario_group/scenario_version")

    def seed_matrix(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for scenario in sorted(
            self.scenarios,
            key=lambda item: (item.scenario_group, item.scenario_version),
        ):
            for seed in sorted(scenario.seeds):
                rows.append(
                    {
                        "scenario_group": scenario.scenario_group,
                        "scenario_version": scenario.scenario_version,
                        "seed": seed,
                        "tags": list(scenario.tags),
                        "difficulty": scenario.difficulty,
                        "expected_failure_modes": list(
                            scenario.expected_failure_modes
                        ),
                        "parameters": dict(scenario.parameters),
                        "online_truth_policy": scenario.online_truth_policy,
                    }
                )
        return rows

    def write_bundle(self, output_dir: str | Path) -> dict[str, Path]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        rows = self.seed_matrix()
        json_path = output_dir / "scenario_library.json"
        csv_path = output_dir / "scenario_seed_matrix.csv"
        markdown_path = output_dir / "scenario_library.md"

        json_path.write_text(
            json.dumps(
                {
                    "schema_version": "d6-scenario-library-v1",
                    "scenario_count": len(self.scenarios),
                    "seed_matrix_row_count": len(rows),
                    "scenarios": [scenario.to_dict() for scenario in self.scenarios],
                    "seed_matrix": rows,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        with csv_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=[
                    "scenario_group",
                    "scenario_version",
                    "seed",
                    "tags",
                    "difficulty",
                    "expected_failure_modes",
                    "parameters",
                    "online_truth_policy",
                ],
            )
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        **row,
                        "tags": ";".join(row["tags"]),
                        "expected_failure_modes": ";".join(
                            row["expected_failure_modes"]
                        ),
                        "parameters": json.dumps(
                            row["parameters"], ensure_ascii=False, sort_keys=True
                        ),
                    }
                )

        lines = [
            "# D6 标准场景库与 Seed Matrix",
            "",
            "场景标识使用稳定 `scenario_group`；版本、难度、预期失败模式和 seed 单独记录。在线链路禁止读取离线真值字段。",
            "",
            "## 场景定义",
            "",
            "| 场景组 | 版本 | 标签 | 难度 | 预期失败模式 (Expected failure modes) | Seeds | 参数 |",
            "|---|---|---|---|---|---|---|",
        ]
        for scenario in sorted(
            self.scenarios,
            key=lambda item: (item.scenario_group, item.scenario_version),
        ):
            lines.append(
                "| {group} | {version} | {tags} | {difficulty} | {failures} | {seeds} | {parameters} |".format(
                    group=scenario.scenario_group,
                    version=scenario.scenario_version,
                    tags=", ".join(scenario.tags),
                    difficulty=scenario.difficulty,
                    failures=", ".join(scenario.expected_failure_modes) or "none",
                    seeds=", ".join(str(seed) for seed in sorted(scenario.seeds)),
                    parameters=json.dumps(
                        dict(scenario.parameters), ensure_ascii=False, sort_keys=True
                    ).replace("|", "\\|"),
                )
            )
        lines.extend(
            [
                "",
                "## Seed 矩阵摘要",
                "",
                f"- 场景数量：{len(self.scenarios)}",
                f"- Episode 计划数量：{len(rows)}",
                "- 所有场景的在线真值策略：`forbidden`",
                "- D6 只使用这些定义进行离线分组与报告，不负责启动 AirSim 或改变模块配置。",
            ]
        )
        markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return {"json": json_path, "csv": csv_path, "markdown": markdown_path}

    @classmethod
    def from_mappings(
        cls,
        payloads: Sequence[Mapping[str, Any]],
    ) -> "ScenarioLibrary":
        return cls(
            ScenarioDefinition(
                scenario_group=str(payload["scenario_group"]),
                scenario_version=str(payload["scenario_version"]),
                tags=tuple(str(value) for value in payload.get("tags", ())),
                difficulty=str(payload["difficulty"]),
                expected_failure_modes=tuple(
                    str(value)
                    for value in payload.get("expected_failure_modes", ())
                ),
                seeds=tuple(int(value) for value in payload.get("seeds", ())),
                parameters=dict(payload.get("parameters", {})),
                online_truth_policy=str(
                    payload.get("online_truth_policy", "forbidden")
                ),
            )
            for payload in payloads
        )


def default_p1_governance_scenario_library(
    seeds: Sequence[int] = tuple(range(1, 11)),
) -> ScenarioLibrary:
    """Return the versioned D1-D3 AirSim governance matrix owned by D6."""

    seed_tuple = tuple(int(seed) for seed in seeds)
    shared = {
        "airsim_mode": "ComputerVision",
        "requires_real_airsim_outputs": True,
        "camera_count": 5,
    }
    return ScenarioLibrary(
        [
            ScenarioDefinition(
                scenario_group="blocks_cv_5v5_d1_governance",
                scenario_version="d1-governance-v1",
                tags=("airsim", "5v5", "d1", "oosm", "region_quality"),
                difficulty="challenging",
                expected_failure_modes=(
                    "schema_provenance_missing",
                    "oosm_rate_high",
                    "region_quality_degraded",
                ),
                seeds=seed_tuple,
                parameters={
                    **shared,
                    "drone_count": 5,
                    "resource_count": 5,
                    "target_count": 5,
                    "governance_profile": "d1-schema-oosm-region-v1",
                },
            ),
            ScenarioDefinition(
                scenario_group="blocks_cv_5v5_d2_governance",
                scenario_version="d2-governance-v1",
                tags=("airsim", "5v5", "d2", "dense_crossing", "false_tracks"),
                difficulty="stress",
                expected_failure_modes=(
                    "association_risk_high",
                    "nis_nees_inconsistent",
                    "false_track_rate_high",
                ),
                seeds=seed_tuple,
                parameters={
                    **shared,
                    "drone_count": 5,
                    "resource_count": 5,
                    "target_count": 5,
                    "risk_profile": "d2-default",
                    "risk_profile_version": "unversioned_until_runtime_writes",
                },
            ),
            ScenarioDefinition(
                scenario_group="blocks_cv_5v5_d3_governance",
                scenario_version="d3-governance-v1",
                tags=("airsim", "5v5", "d3", "balanced_nm", "d5_feedback"),
                difficulty="challenging",
                expected_failure_modes=(
                    "assignment_coverage_low",
                    "hysteresis_reject_high",
                    "feedback_profile_missing",
                ),
                seeds=seed_tuple,
                parameters={
                    **shared,
                    "drone_count": 5,
                    "resource_count": 5,
                    "target_count": 5,
                    "feedback_profile": "d3-terminal-feedback-v1",
                },
            ),
            ScenarioDefinition(
                scenario_group="blocks_cv_3r5t_d3_nm_governance",
                scenario_version="d3-nm-governance-v1",
                tags=("airsim", "d3", "resource_limited", "nm_mismatch"),
                difficulty="stress",
                expected_failure_modes=(
                    "unassigned_target_rate_high",
                    "high_threat_unassigned",
                ),
                seeds=seed_tuple,
                parameters={
                    **shared,
                    "drone_count": 3,
                    "resource_count": 3,
                    "target_count": 5,
                    "feedback_profile": "d3-terminal-feedback-v1",
                },
            ),
            ScenarioDefinition(
                scenario_group="blocks_cv_5r3t_d3_nm_governance",
                scenario_version="d3-nm-governance-v1",
                tags=("airsim", "d3", "resource_surplus", "nm_mismatch"),
                difficulty="challenging",
                expected_failure_modes=(
                    "duplicate_assignment",
                    "hysteresis_churn",
                ),
                seeds=seed_tuple,
                parameters={
                    **shared,
                    "drone_count": 5,
                    "resource_count": 5,
                    "target_count": 3,
                    "feedback_profile": "d3-terminal-feedback-v1",
                },
            ),
        ]
    )
