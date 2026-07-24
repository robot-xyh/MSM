from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .fusion import CHI2_3_999, FusionAdapter
from .motion import cv_process_noise, cv_transition
from .observations import radar_covariance_from_range
from .replay import (
    ReplayProvenance,
    sensor_observation_from_jsonl_record,
    serialize_governed_replay,
)
from .scan_input import (
    ScanInputConfig,
    ScanInputOrganizer,
    SensorScanFrame,
)
from .types import GlobalTrack, SensorObservation, StructuralAmbiguityEvidence


STRUCTURAL_AMBIGUITY_REPLAY_DIAGNOSTIC_SCHEMA_VERSION = (
    "d1.structural_ambiguity_replay_diagnostic.v2"
)
STRUCTURAL_AMBIGUITY_REPLAY_SCENARIO_VERSION = (
    "d1.structural_ambiguity_replay_scenarios.v1"
)

_INVALID_COST = 1_000.0
_MAX_TRANSLATION_M = 30.0
_SENSOR_POSITION_NED = np.zeros(3, dtype=float)
_FLOAT_TOLERANCE = 1.0e-8
_CANDIDATE_NOT_PROMOTED = "candidate_not_promoted"
_PROMOTION_INELIGIBILITY_REASON = "controlled_boundary_diagnostic_only"
_REJECTED_REPLAY_REPLACEMENT_ROOT_CAUSE = (
    "candidate_rejection_publication_base_replacement_with_"
    "non_semigroup_discrete_process_noise_segmentation"
)
_REJECTED_REPLAY_REPLACEMENT_INTERPRETATION = (
    "centroid_correction_not_applied_but_publication_base_replay_"
    "replacement_produces_finite_diagnostic_only_difference"
)


@dataclass(frozen=True)
class _DiagnosticScenario:
    scenario_id: str
    scenario_kind: str
    frames: tuple[SensorScanFrame, ...]
    target_scan_id: str
    preset_costs: dict[int, np.ndarray]
    expected_rejection_reason: str | None


@dataclass(frozen=True)
class _TrackCapture:
    global_track_id: str
    state: np.ndarray
    covariance: np.ndarray
    hits: int
    lineage: tuple[tuple[Any, ...], ...]
    source_support: tuple[tuple[str, int], ...]
    identity_likelihood: tuple[tuple[str, float], ...]
    track_level: str


@dataclass(frozen=True)
class _StateCapture:
    state: np.ndarray
    covariance: np.ndarray
    timestamp: float


@dataclass(frozen=True)
class _CandidateBuildCapture:
    scan_id: str
    scan_index: int
    track_ids: tuple[str, ...]
    previous_fusion_time: float
    current_fusion_time: float
    process_noise_spectral_density: float
    latest_measurement_timestamps: dict[str, float]
    states_before_build: dict[str, _StateCapture]
    publication_base_states: dict[str, _StateCapture]
    correction_produced: bool
    rejection_reason: str | None
    translation_ned: np.ndarray | None
    position_covariance_inflation: np.ndarray | None


@dataclass(frozen=True)
class _PublicationBaseReplacementCapture:
    scan_id: str
    scan_index: int
    states_before_replacement: dict[str, _StateCapture]
    publication_base_states: dict[str, _StateCapture]
    states_after_replacement: dict[str, _StateCapture]


@dataclass(frozen=True)
class _ArmReplay:
    target_tracks_before: dict[str, _TrackCapture]
    target_tracks_after: dict[str, _TrackCapture]
    target_component_track_ids: tuple[str, ...]
    target_evidence: tuple[StructuralAmbiguityEvidence, ...]
    target_diagnostic: dict[str, Any]
    fusion_processing_order: tuple[dict[str, Any], ...]
    final_association_audit: dict[str, Any]
    candidate_build_events: tuple[_CandidateBuildCapture, ...]
    publication_base_replacement_events: tuple[
        _PublicationBaseReplacementCapture, ...
    ]


class _PresetRadarCostDiagnosticAdapter(FusionAdapter):
    """Inject a small deterministic ambiguity graph into the existing adapter."""

    def __init__(
        self,
        *,
        preset_costs: dict[int, np.ndarray],
        centroid_enabled: bool,
    ) -> None:
        super().__init__(
            association_gate=40.0,
            radar_assignment_ambiguity_hold_evidence=True,
            radar_assignment_ambiguity_neutral_centroid_correction=(
                centroid_enabled
            ),
            publisher_node_id="D1_REPLAY_DIAGNOSTIC",
            publisher_epoch="d1-frozen-centroid-diagnostic-v1",
            neutral_centroid_gate_chi2=1.0e9,
            neutral_centroid_shape_gate_m2=1.0e9,
            neutral_centroid_max_translation_m=_MAX_TRANSLATION_M,
        )
        self._preset_costs = {
            int(scan_index): np.asarray(costs, dtype=float).copy()
            for scan_index, costs in preset_costs.items()
        }
        self._diagnostic_scan_id = ""
        self._diagnostic_fusion_time_before = 0.0
        self.candidate_build_events: list[_CandidateBuildCapture] = []
        self.publication_base_replacement_events: list[
            _PublicationBaseReplacementCapture
        ] = []
        self._pending_rejected_build: _CandidateBuildCapture | None = None

    def set_diagnostic_frame_context(
        self,
        *,
        scan_id: str,
        fusion_time_before: float,
    ) -> None:
        self._diagnostic_scan_id = str(scan_id)
        self._diagnostic_fusion_time_before = float(fusion_time_before)

    def _radar_scan_cost_matrix(
        self,
        track_items: list[tuple[str, Any]],
        observations: list[SensorObservation],
    ) -> np.ndarray:
        scan_index = int(observations[0].metadata["diagnostic_scan_index"])
        preset = self._preset_costs.get(scan_index)
        if preset is None:
            return super()._radar_scan_cost_matrix(track_items, observations)
        if preset.shape != (len(track_items), len(observations)):
            raise ValueError(
                "diagnostic preset cost shape does not match the current scan"
            )
        return preset.copy()

    def _build_neutral_centroid_correction(
        self,
        observations: list[SensorObservation],
        ambiguity: Any,
        evidence: StructuralAmbiguityEvidence,
        *,
        publication_base_states: Mapping[str, Any],
        scan_has_oosm: bool,
        scan_has_stale_observation: bool,
    ) -> tuple[Any | None, str | None]:
        track_ids = tuple(str(item) for item in ambiguity.track_ids)
        states_before_build = {
            track_id: _capture_state(self.tracks[track_id].current_state)
            for track_id in track_ids
        }
        publication_bases = {
            track_id: _capture_state(publication_base_states[track_id])
            for track_id in track_ids
        }
        latest_measurement_timestamps = {
            track_id: max(
                [
                    float(self.tracks[track_id].initial_state.timestamp),
                    *[
                        float(item.measurement_timestamp)
                        for item in self.tracks[track_id].observations
                    ],
                ]
            )
            for track_id in track_ids
        }
        correction, rejection_reason = super()._build_neutral_centroid_correction(
            observations,
            ambiguity,
            evidence,
            publication_base_states=publication_base_states,
            scan_has_oosm=scan_has_oosm,
            scan_has_stale_observation=scan_has_stale_observation,
        )
        event = _CandidateBuildCapture(
            scan_id=self._diagnostic_scan_id,
            scan_index=int(observations[0].metadata["diagnostic_scan_index"]),
            track_ids=track_ids,
            previous_fusion_time=self._diagnostic_fusion_time_before,
            current_fusion_time=float(self.current_time),
            process_noise_spectral_density=float(self.process_noise),
            latest_measurement_timestamps=latest_measurement_timestamps,
            states_before_build=states_before_build,
            publication_base_states=publication_bases,
            correction_produced=correction is not None,
            rejection_reason=rejection_reason,
            translation_ned=(
                None
                if correction is None
                else np.asarray(correction.translation_ned, dtype=float).copy()
            ),
            position_covariance_inflation=(
                None
                if correction is None
                else np.asarray(
                    correction.position_covariance_inflation,
                    dtype=float,
                ).copy()
            ),
        )
        self.candidate_build_events.append(event)
        self._pending_rejected_build = event if correction is None else None
        return correction, rejection_reason

    def _replace_neutral_centroid_publication_states(
        self,
        publication_bases: Mapping[str, Any],
    ) -> None:
        states_before = {
            track_id: _capture_state(self.tracks[track_id].current_state)
            for track_id in publication_bases
        }
        captured_bases = {
            track_id: _capture_state(state)
            for track_id, state in publication_bases.items()
        }
        super()._replace_neutral_centroid_publication_states(
            publication_bases
        )
        states_after = {
            track_id: _capture_state(self.tracks[track_id].current_state)
            for track_id in publication_bases
        }
        pending = self._pending_rejected_build
        self.publication_base_replacement_events.append(
            _PublicationBaseReplacementCapture(
                scan_id=(
                    pending.scan_id
                    if pending is not None
                    else self._diagnostic_scan_id
                ),
                scan_index=(
                    pending.scan_index
                    if pending is not None
                    else -1
                ),
                states_before_replacement=states_before,
                publication_base_states=captured_bases,
                states_after_replacement=states_after,
            )
        )
        self._pending_rejected_build = None


def run_structural_ambiguity_centroid_replay_diagnostic() -> dict[str, Any]:
    """Run three frozen, identity-free boundary cases through the online core.

    The candidate is enabled only inside this diagnostic. The function neither
    changes the production default nor relaxes any timestamp, cardinality,
    covariance, lineage, or identity gate.
    """

    scenario_results = [
        _run_scenario(scenario) for scenario in _build_scenarios()
    ]
    by_kind = {
        str(item["scenario_kind"]): item for item in scenario_results
    }
    synchronous = by_kind["synchronous_balanced_cycle"]
    oosm = by_kind["reordered_balanced_cycle"]
    unbalanced = by_kind["unbalanced_component"]
    rejected_scenario_diagnostics = {
        str(item["scenario_kind"]): {
            "rejection_reason": item["target_outcome"]["rejection_reason"],
            "applied_component_count": item["target_outcome"][
                "applied_component_count"
            ],
            "centroid_correction_applied": item["invariant_checks"][
                "target_centroid_state_or_covariance_correction_applied"
            ],
            "publication_base_replay_replacement_count": item[
                "invariant_checks"
            ]["target_publication_base_replacement_count"],
            "candidate_minus_control_covariance_delta_min_eigenvalue": item[
                "invariant_checks"
            ]["rejected_target_covariance_delta_min_eigenvalue"],
            "candidate_minus_control_covariance_delta_max_abs": item[
                "invariant_checks"
            ]["rejected_target_covariance_delta_max_abs"],
            "root_cause": item["invariant_checks"][
                "rejected_target_delta_root_cause"
            ],
            "interpretation": item["invariant_checks"][
                "rejected_target_finite_difference_interpretation"
            ],
            "diagnostic_only": item["invariant_checks"][
                "rejected_scenario_covariance_delta_diagnostic_only"
            ],
            "promotion_boundary": item["promotion_boundary"],
        }
        for item in scenario_results
        if item["expected_rejection_reason"] is not None
    }
    acceptance = {
        "synchronous_nonzero_bounded_translation": bool(
            synchronous["target_outcome"]["applied_component_count"] == 1
            and synchronous["invariant_checks"]["translation_nonzero"]
            and synchronous["invariant_checks"]["translation_bounded"]
            and synchronous["invariant_checks"]["covariance_not_contracted"]
        ),
        "oosm_fail_closed": bool(
            oosm["target_outcome"]["applied_component_count"] == 0
            and oosm["target_outcome"]["rejection_reason"] == "oosm_scan"
            and oosm["invariant_checks"][
                "rejected_target_path_strictly_attributed"
            ]
        ),
        "unbalanced_fail_closed": bool(
            unbalanced["target_outcome"]["applied_component_count"] == 0
            and unbalanced["target_outcome"]["rejection_reason"]
            == "unbalanced_component"
            and unbalanced["invariant_checks"][
                "rejected_target_path_strictly_attributed"
            ]
        ),
        "rejected_targets_have_no_centroid_formula_output": bool(
            oosm["invariant_checks"][
                "rejected_target_no_centroid_formula_output"
            ]
            and unbalanced["invariant_checks"][
                "rejected_target_no_centroid_formula_output"
            ]
        ),
        "rejected_target_covariance_delta_root_cause_resolved": bool(
            oosm["invariant_checks"][
                "rejected_target_path_strictly_attributed"
            ]
            and unbalanced["invariant_checks"][
                "rejected_target_path_strictly_attributed"
            ]
        ),
        "control_and_candidate_used_same_frozen_frames": all(
            item["control_and_candidate_consumed_same_frozen_frames"]
            for item in scenario_results
        ),
        "online_default_changed": False,
        "online_safety_gate_relaxed": False,
        "candidate_promoted": False,
        "candidate_not_promoted": all(
            item["promotion_boundary"] == _CANDIDATE_NOT_PROMOTED
            and not item["candidate_promoted"]
            for item in scenario_results
        ),
    }
    acceptance["passed"] = bool(
        acceptance["synchronous_nonzero_bounded_translation"]
        and acceptance["oosm_fail_closed"]
        and acceptance["unbalanced_fail_closed"]
        and acceptance["rejected_targets_have_no_centroid_formula_output"]
        and acceptance[
            "rejected_target_covariance_delta_root_cause_resolved"
        ]
        and acceptance["control_and_candidate_used_same_frozen_frames"]
        and not acceptance["online_default_changed"]
        and not acceptance["online_safety_gate_relaxed"]
        and not acceptance["candidate_promoted"]
        and acceptance["candidate_not_promoted"]
    )
    return {
        "schema_version": (
            STRUCTURAL_AMBIGUITY_REPLAY_DIAGNOSTIC_SCHEMA_VERSION
        ),
        "scenario_version": STRUCTURAL_AMBIGUITY_REPLAY_SCENARIO_VERSION,
        "evidence_date": "2026-07-23",
        "scope": "d1_frozen_scan_boundary_diagnostic",
        "candidate_default": False,
        "candidate_status": "experimental_default_off_not_promoted",
        "promotion_boundary": _CANDIDATE_NOT_PROMOTED,
        "promotion_evidence_eligible": False,
        "promotion_ineligibility_reason": _PROMOTION_INELIGIBILITY_REASON,
        "online_truth_used": False,
        "acceptance": acceptance,
        "rejected_scenario_diagnostics": rejected_scenario_diagnostics,
        "scenarios": scenario_results,
    }


def render_structural_ambiguity_replay_diagnostic_cn(
    report: dict[str, Any],
) -> str:
    """Render a compact Chinese report from the machine-readable result."""

    scenarios = {
        item["scenario_kind"]: item for item in report["scenarios"]
    }
    rows = []
    for kind in (
        "synchronous_balanced_cycle",
        "reordered_balanced_cycle",
        "unbalanced_component",
    ):
        item = scenarios[kind]
        outcome = item["target_outcome"]
        component = outcome["components"][0]
        covariance_delta_min_eigenvalue = item["invariant_checks"][
            "minimum_covariance_delta_eigenvalue"
        ]
        rows.append(
            "| "
            + " | ".join(
                (
                    item["scenario_name_cn"],
                    f"{component['member_count']}/{component['observation_count']}",
                    f"{component['free_row_count']}/{component['free_column_count']}",
                    str(outcome["applied_component_count"]),
                    str(outcome["rejection_reason"] or "无"),
                    f"{item['invariant_checks']['translation_norm_m']:.6f}",
                    f"{covariance_delta_min_eigenvalue:.12f}",
                )
            )
            + " |"
        )

    synchronous = scenarios["synchronous_balanced_cycle"]
    oosm = scenarios["reordered_balanced_cycle"]
    unbalanced = scenarios["unbalanced_component"]
    oosm_target = oosm["target_outcome"]
    oosm_order = " -> ".join(
        item["scan_id"] for item in oosm["fusion_processing_order"]
    )
    input_order = " -> ".join(
        item["scan_id"] for item in oosm["input_order"]
    )
    unbalanced_component = unbalanced["target_outcome"]["components"][0]
    oosm_rejected = report["rejected_scenario_diagnostics"][
        "reordered_balanced_cycle"
    ]
    unbalanced_rejected = report["rejected_scenario_diagnostics"][
        "unbalanced_component"
    ]
    acceptance = report["acceptance"]
    lines = [
        "# D1 结构歧义共同质心冻结扫描诊断",
        "",
        "## 结论",
        "",
        "三类冻结输入均按现有时间、数量和身份安全合同运行。同步平衡分量形成一次非零有界共同"
        "平移；乱序平衡分量以 `oosm_scan` 拒绝；数量不平衡分量以 "
        "`unbalanced_component` 拒绝。候选仍为默认关闭的边界诊断能力，不构成算法晋级证据。",
        "",
        "## 结果",
        "",
        "| 场景 | 成员/观测 | free row/column | 实际施加 | 拒绝原因 | 共同平移模长/m | 候选-控制协方差差最小特征值 |",
        "| --- | ---: | ---: | ---: | --- | ---: | ---: |",
        *rows,
        "",
        "同步平衡场景的速度、成员相对位置、命中数、来源谱系、身份似然、规范航迹编号均保持"
        "不变，协方差没有收缩。共同平移为 "
        f"`{synchronous['invariant_checks']['translation_ned_m']}` m，模长 "
        f"`{synchronous['invariant_checks']['translation_norm_m']:.6f}` m，未超过 "
        f"`{_MAX_TRANSLATION_M:.1f}` m 上限。",
        "",
        "## 乱序时序",
        "",
        f"输入到达顺序为 `{input_order}`。扫描组织器保留双时间戳和重排事件；实际融合处理顺序为 "
        f"`{oosm_order}`。目标扫描量测时刻为 "
        f"`{oosm_target['measurement_timestamp']:.3f}` s，到达时刻为 "
        f"`{oosm_target['arrival_timestamp']:.3f}` s，进入融合前的当前时刻为 "
        f"`{oosm_target['fusion_time_before']:.3f}` s。量测时刻早于已有融合时刻，现有资格门"
        "据此返回 `oosm_scan`。诊断没有删除时间戳、重排输入或绕过该门。",
        "",
        "## 数量边界",
        "",
        "数量不平衡目标分量记录成员数 "
        f"`{unbalanced_component['member_count']}`、观测数 "
        f"`{unbalanced_component['observation_count']}`、free row "
        f"`{unbalanced_component['free_row_count']}`、free column "
        f"`{unbalanced_component['free_column_count']}`。该分量的共同质心 correction "
        "未施加。",
        "",
        "## 拒绝路径数值归因",
        "",
        "两个拒绝场景的 `applied_component_count=0`，共同质心公式均未产生平移或协方差"
        "膨胀输出，因此共同质心 correction 未施加。但候选臂在登记拒绝前仍各执行 1 次"
        " publication-base replay + replace，用重建的发布基准清除旧临时修正；所以不能把"
        "拒绝路径描述为对状态和协方差严格无副作用。",
        "",
        "乱序平衡场景的候选臂减控制臂协方差差最小特征值为 "
        f"`{oosm_rejected['candidate_minus_control_covariance_delta_min_eigenvalue']:.15f}`；"
        "数量不平衡场景为 "
        f"`{unbalanced_rejected['candidate_minus_control_covariance_delta_min_eigenvalue']:.15f}`。"
        "控制臂保留分段预测发布态，候选臂替换为从观测历史重放到发布时间的发布基准；当前"
        "离散 CV 过程噪声在单段与分段传播下不满足半群等价，因而产生上述有限协方差差异。"
        "诊断已逐元素确认候选-控制差值与 replacement 前后差值 bitwise 一致，模型解释残差"
        "低于 `1e-12`。",
        "",
        "这些差异只用于定位拒绝后的发布态重放替换，不是共同质心 correction，也不是门控"
        f"放宽或收益证据。两项拒绝结果的晋级边界均为 `{_CANDIDATE_NOT_PROMOTED}`。",
        "",
        "## 证据边界",
        "",
        "输入先经过既有 governed replay 序列化和回读，再由 `SensorScanFrame`、"
        "`ScanInputOrganizer` 释放，控制臂和候选臂消费同一冻结扫描序列。测试未读取在线真值，"
        "未改变共同质心公式、默认开关或固定滞后策略。",
        "",
        "协方差不收缩只对实际施加共同平移的同步平衡场景作验收。两个拒绝场景仍输出候选臂"
        "相对控制臂的协方差差值，供后续解释重放发布基准的数值差异；该差值不作为放宽 "
        "OOSM 或数量门的依据。",
        "",
        "专项验收结果："
        f"{'通过' if acceptance['passed'] else '未通过'}。剩余工作是验证该受控窗口能否在"
        "真实匿名冻结扫描中自然出现，并开展未见种子、状态误差、一致性、吞吐和内存验收。",
        "",
    ]
    return "\n".join(lines)


def write_structural_ambiguity_replay_diagnostic(
    output_dir: str | Path,
    report: dict[str, Any] | None = None,
) -> dict[str, Path]:
    """Write deterministic JSON and Chinese Markdown diagnostic artifacts."""

    payload = (
        run_structural_ambiguity_centroid_replay_diagnostic()
        if report is None
        else report
    )
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "structural_ambiguity_centroid_replay_diagnostic.json"
    markdown_path = output / "STRUCTURAL_AMBIGUITY_CENTROID_REPLAY_DIAGNOSTIC_CN.md"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(
        render_structural_ambiguity_replay_diagnostic_cn(payload),
        encoding="utf-8",
    )
    return {"json": json_path, "markdown": markdown_path}


def _run_scenario(scenario: _DiagnosticScenario) -> dict[str, Any]:
    frozen_frames, frozen_summary = _freeze_and_roundtrip_frames(scenario)
    released_frames, organizer_summary = _organize_frames(frozen_frames)
    control = _run_arm(scenario, released_frames, centroid_enabled=False)
    candidate = _run_arm(scenario, released_frames, centroid_enabled=True)
    checks = _compare_target_component(control, candidate)
    target = candidate.target_diagnostic
    covariance_non_contraction_required = bool(
        target["applied_component_count"] > 0
    )
    checks["covariance_non_contraction_required"] = (
        covariance_non_contraction_required
    )
    checks["covariance_non_contraction_acceptance"] = bool(
        checks["covariance_not_contracted"]
    ) if covariance_non_contraction_required else None
    rejected_scenario = bool(
        target["applied_component_count"] == 0
        and target["rejection_reason"] is not None
    )
    checks["rejected_scenario_covariance_delta_diagnostic_only"] = bool(
        rejected_scenario
        and checks["rejected_target_no_centroid_formula_output"]
        and checks["target_publication_base_replacement_count"] == 1
        and checks[
            "rejected_target_publication_base_replacement_side_effect_present"
        ]
        and checks["rejected_target_path_strictly_attributed"]
    )
    checks["applied_scenario_covariance_gate_passed"] = bool(
        covariance_non_contraction_required
        and checks["covariance_not_contracted"]
    )
    checks["candidate_promotion_evidence_eligible"] = False
    checks["candidate_promotion_ineligibility_reason"] = (
        _PROMOTION_INELIGIBILITY_REASON
    )
    components = [
        _component_summary(item) for item in candidate.target_evidence
    ]
    if not components:
        raise RuntimeError(
            f"{scenario.scenario_id} did not produce structural ambiguity evidence"
        )
    result = {
        "scenario_id": scenario.scenario_id,
        "scenario_kind": scenario.scenario_kind,
        "scenario_name_cn": _scenario_name_cn(scenario.scenario_kind),
        "target_scan_id": scenario.target_scan_id,
        "expected_rejection_reason": scenario.expected_rejection_reason,
        "input_order": [_frame_order_item(item) for item in frozen_frames],
        "fusion_processing_order": list(candidate.fusion_processing_order),
        "frozen_replay": frozen_summary,
        "scan_organizer": organizer_summary,
        "target_outcome": {
            **target,
            "components": components,
        },
        "invariant_checks": checks,
        "control_and_candidate_consumed_same_frozen_frames": (
            _frozen_frame_processing_signature(
                control.fusion_processing_order
            )
            == _frozen_frame_processing_signature(
                candidate.fusion_processing_order
            )
        ),
        "candidate_default_changed": False,
        "online_safety_gate_relaxed": False,
        "candidate_promoted": False,
        "promotion_boundary": _CANDIDATE_NOT_PROMOTED,
    }
    _validate_scenario_result(result)
    return result


def _run_arm(
    scenario: _DiagnosticScenario,
    frames: tuple[SensorScanFrame, ...],
    *,
    centroid_enabled: bool,
) -> _ArmReplay:
    adapter = _PresetRadarCostDiagnosticAdapter(
        preset_costs=scenario.preset_costs,
        centroid_enabled=centroid_enabled,
    )
    processing_order: list[dict[str, Any]] = []
    target_before: dict[str, _TrackCapture] | None = None
    target_after: dict[str, _TrackCapture] | None = None
    target_component_ids: tuple[str, ...] = ()
    target_evidence: tuple[StructuralAmbiguityEvidence, ...] = ()
    target_diagnostic: dict[str, Any] | None = None

    for processing_index, frame in enumerate(frames):
        audit_before = adapter.association_audit_summary()
        fusion_time_before = float(adapter.current_time)
        internal_before_materialization = _capture_internal_states(adapter)
        captures_before = _capture_adapter_tracks(adapter)
        internal_after_materialization = _capture_internal_states(adapter)
        adapter.set_diagnostic_frame_context(
            scan_id=frame.scan_id,
            fusion_time_before=fusion_time_before,
        )
        result = adapter.process_scan_batch(frame.observations)
        audit_after = adapter.association_audit_summary()
        frame_diagnostic = {
            **_frame_order_item(frame),
            "processing_index": processing_index,
            "fusion_time_before": fusion_time_before,
            "fusion_time_after": float(adapter.current_time),
            "measurement_precedes_fusion_time": bool(
                frame.measurement_timestamp
                < fusion_time_before - _FLOAT_TOLERANCE
            ),
            "pre_scan_materialization_state_covariance_unchanged_bitwise": (
                _state_capture_maps_equal_bitwise(
                    internal_before_materialization,
                    internal_after_materialization,
                )
            ),
            "candidate_component_count": _audit_delta(
                audit_before,
                audit_after,
                "neutral_centroid_candidate_component_count",
            ),
            "applied_component_count": _audit_delta(
                audit_before,
                audit_after,
                "neutral_centroid_applied_component_count",
            ),
            "rejected_component_count": _audit_delta(
                audit_before,
                audit_after,
                "neutral_centroid_rejected_component_count",
            ),
            "rejection_reason": (
                audit_after.get("latest_neutral_centroid_rejection_reason")
                if _audit_delta(
                    audit_before,
                    audit_after,
                    "neutral_centroid_rejected_component_count",
                )
                else None
            ),
        }
        processing_order.append(frame_diagnostic)
        if frame.scan_id != scenario.target_scan_id:
            continue
        target_evidence = tuple(result.structural_ambiguity_evidence)
        target_component_ids = _component_global_track_ids(
            result.tracks,
            target_evidence,
        )
        target_before = {
            track_id: captures_before[track_id]
            for track_id in target_component_ids
        }
        captures_after = _capture_adapter_tracks(adapter, result.tracks)
        target_after = {
            track_id: captures_after[track_id]
            for track_id in target_component_ids
        }
        target_diagnostic = frame_diagnostic

    if (
        target_before is None
        or target_after is None
        or target_diagnostic is None
        or not target_component_ids
    ):
        raise RuntimeError(
            f"{scenario.scenario_id} target scan was not processed"
        )
    return _ArmReplay(
        target_tracks_before=target_before,
        target_tracks_after=target_after,
        target_component_track_ids=target_component_ids,
        target_evidence=target_evidence,
        target_diagnostic=target_diagnostic,
        fusion_processing_order=tuple(processing_order),
        final_association_audit=adapter.association_audit_summary(),
        candidate_build_events=tuple(adapter.candidate_build_events),
        publication_base_replacement_events=tuple(
            adapter.publication_base_replacement_events
        ),
    )


def _compare_target_component(
    control: _ArmReplay,
    candidate: _ArmReplay,
) -> dict[str, Any]:
    control_ids = control.target_component_track_ids
    candidate_ids = candidate.target_component_track_ids
    shared_ids = tuple(sorted(set(control_ids) & set(candidate_ids)))
    if not shared_ids:
        raise RuntimeError("control and candidate have no common component members")

    translations = [
        candidate.target_tracks_after[track_id].state[:3]
        - control.target_tracks_after[track_id].state[:3]
        for track_id in shared_ids
    ]
    translation = translations[0]
    translation_norm = float(np.linalg.norm(translation))
    common_translation = all(
        np.allclose(item, translation, atol=_FLOAT_TOLERANCE, rtol=0.0)
        for item in translations
    )
    relative_position_unchanged = True
    for left_index, left_id in enumerate(shared_ids):
        for right_id in shared_ids[left_index + 1 :]:
            control_relative = (
                control.target_tracks_after[left_id].state[:3]
                - control.target_tracks_after[right_id].state[:3]
            )
            candidate_relative = (
                candidate.target_tracks_after[left_id].state[:3]
                - candidate.target_tracks_after[right_id].state[:3]
            )
            relative_position_unchanged = (
                relative_position_unchanged
                and bool(
                    np.allclose(
                        control_relative,
                        candidate_relative,
                        atol=_FLOAT_TOLERANCE,
                        rtol=0.0,
                    )
                )
            )

    minimum_covariance_delta_eigenvalue = math.inf
    covariance_not_contracted = True
    for track_id in shared_ids:
        covariance_delta = (
            candidate.target_tracks_after[track_id].covariance
            - control.target_tracks_after[track_id].covariance
        )
        covariance_delta = 0.5 * (
            covariance_delta + covariance_delta.T
        )
        minimum = float(np.linalg.eigvalsh(covariance_delta)[0])
        minimum_covariance_delta_eigenvalue = min(
            minimum_covariance_delta_eigenvalue,
            minimum,
        )
        covariance_not_contracted = (
            covariance_not_contracted and minimum >= -_FLOAT_TOLERANCE
        )

    before = candidate.target_tracks_before
    after = candidate.target_tracks_after
    checks = {
        "component_global_track_ids": list(shared_ids),
        "global_track_id_unchanged": bool(
            control_ids == candidate_ids
            and set(shared_ids) == set(before)
            and set(shared_ids) == set(after)
        ),
        "velocity_unchanged": all(
            np.allclose(
                after[track_id].state[3:],
                control.target_tracks_after[track_id].state[3:],
                atol=_FLOAT_TOLERANCE,
                rtol=0.0,
            )
            for track_id in shared_ids
        ),
        "relative_position_unchanged": relative_position_unchanged,
        "hits_unchanged": all(
            before[track_id].hits == after[track_id].hits
            for track_id in shared_ids
        ),
        "lineage_unchanged": all(
            before[track_id].lineage == after[track_id].lineage
            for track_id in shared_ids
        ),
        "lineage_equal_to_control": all(
            after[track_id].lineage
            == control.target_tracks_after[track_id].lineage
            for track_id in shared_ids
        ),
        "identity_unchanged": all(
            before[track_id].identity_likelihood
            == after[track_id].identity_likelihood
            and before[track_id].source_support
            == after[track_id].source_support
            and before[track_id].track_level
            == after[track_id].track_level
            for track_id in shared_ids
        ),
        "identity_equal_to_control": all(
            after[track_id].identity_likelihood
            == control.target_tracks_after[track_id].identity_likelihood
            and after[track_id].source_support
            == control.target_tracks_after[track_id].source_support
            and after[track_id].track_level
            == control.target_tracks_after[track_id].track_level
            for track_id in shared_ids
        ),
        "hits_equal_to_control": all(
            after[track_id].hits
            == control.target_tracks_after[track_id].hits
            for track_id in shared_ids
        ),
        "common_translation": common_translation,
        "translation_ned_m": [float(value) for value in translation],
        "translation_norm_m": translation_norm,
        "translation_nonzero": translation_norm > _FLOAT_TOLERANCE,
        "translation_bounded": (
            translation_norm <= _MAX_TRANSLATION_M + _FLOAT_TOLERANCE
        ),
        "covariance_not_contracted": covariance_not_contracted,
        "minimum_covariance_delta_eigenvalue": (
            minimum_covariance_delta_eigenvalue
        ),
    }
    checks.update(
        _target_candidate_path_attribution(
            control,
            candidate,
            shared_ids,
        )
    )
    return checks


def _target_candidate_path_attribution(
    control: _ArmReplay,
    candidate: _ArmReplay,
    shared_ids: tuple[str, ...],
) -> dict[str, Any]:
    target_scan_id = str(candidate.target_diagnostic["scan_id"])
    build_events = tuple(
        item
        for item in candidate.candidate_build_events
        if item.scan_id == target_scan_id
    )
    replacement_events = tuple(
        item
        for item in candidate.publication_base_replacement_events
        if item.scan_id == target_scan_id
    )
    materialization_unchanged = bool(
        control.target_diagnostic[
            "pre_scan_materialization_state_covariance_unchanged_bitwise"
        ]
        and candidate.target_diagnostic[
            "pre_scan_materialization_state_covariance_unchanged_bitwise"
        ]
    )
    base = {
        "target_candidate_build_event_count": len(build_events),
        "target_publication_base_replacement_count": len(
            replacement_events
        ),
        "target_pre_scan_materialization_state_covariance_unchanged_bitwise": (
            materialization_unchanged
        ),
        "target_centroid_formula_correction_produced": False,
        "target_centroid_formula_rejection_reason": None,
        "target_centroid_formula_translation_ned_m": None,
        "target_centroid_formula_position_covariance_inflation": None,
        "target_centroid_state_or_covariance_correction_applied": False,
        "rejected_target_no_centroid_formula_output": False,
        "rejected_target_pre_replacement_matches_control_bitwise": False,
        "rejected_target_post_replacement_matches_publication_base_bitwise": (
            False
        ),
        "rejected_target_published_matches_post_replacement_bitwise": False,
        "rejected_target_control_candidate_delta_explained_by_replacement_bitwise": (
            False
        ),
        "rejected_target_prediction_segmentation_residual_max_abs": None,
        "rejected_target_state_delta_norm_m": None,
        "rejected_target_covariance_delta_min_eigenvalue": None,
        "rejected_target_covariance_delta_max_eigenvalue": None,
        "rejected_target_covariance_delta_max_abs": None,
        "rejected_target_publication_base_replacement_side_effect_present": (
            False
        ),
        "rejected_target_path_strictly_attributed": False,
        "rejected_target_delta_root_cause": None,
        "rejected_target_finite_difference_interpretation": None,
        "rejected_target_promotion_boundary": _CANDIDATE_NOT_PROMOTED,
    }
    if len(build_events) != 1:
        return base

    build = build_events[0]
    base.update(
        {
            "target_centroid_formula_correction_produced": bool(
                build.correction_produced
            ),
            "target_centroid_formula_rejection_reason": (
                build.rejection_reason
            ),
            "target_centroid_formula_translation_ned_m": (
                None
                if build.translation_ned is None
                else [
                    float(value)
                    for value in build.translation_ned
                ]
            ),
            "target_centroid_formula_position_covariance_inflation": (
                None
                if build.position_covariance_inflation is None
                else build.position_covariance_inflation.tolist()
            ),
            "target_centroid_state_or_covariance_correction_applied": bool(
                build.correction_produced
            ),
        }
    )
    if build.correction_produced or len(replacement_events) != 1:
        return base

    replacement = replacement_events[0]
    member_ids = tuple(
        track_id
        for track_id in shared_ids
        if track_id in build.states_before_build
        and track_id in replacement.states_before_replacement
        and track_id in replacement.publication_base_states
        and track_id in replacement.states_after_replacement
    )
    if member_ids != shared_ids:
        return base

    pre_matches_control = True
    post_matches_base = True
    published_matches_post = True
    delta_explained = True
    segmentation_residual_max_abs = 0.0
    state_delta_norm_m = 0.0
    covariance_delta_min_eigenvalue = math.inf
    covariance_delta_max_eigenvalue = -math.inf
    covariance_delta_max_abs = 0.0

    for track_id in member_ids:
        build_pre = build.states_before_build[track_id]
        replacement_pre = replacement.states_before_replacement[track_id]
        publication_base = replacement.publication_base_states[track_id]
        replacement_after = replacement.states_after_replacement[track_id]
        control_after = control.target_tracks_after[track_id]
        candidate_after = candidate.target_tracks_after[track_id]

        pre_matches_control = (
            pre_matches_control
            and _state_capture_equal_bitwise(build_pre, replacement_pre)
            and np.array_equal(
                replacement_pre.state,
                control_after.state,
            )
            and np.array_equal(
                replacement_pre.covariance,
                control_after.covariance,
            )
        )
        post_matches_base = (
            post_matches_base
            and _state_capture_equal_bitwise(
                replacement_after,
                publication_base,
            )
            and _state_capture_equal_bitwise(
                publication_base,
                build.publication_base_states[track_id],
            )
        )
        published_matches_post = (
            published_matches_post
            and np.array_equal(
                candidate_after.state,
                replacement_after.state,
            )
            and np.array_equal(
                candidate_after.covariance,
                replacement_after.covariance,
            )
        )

        observed_state_delta = (
            candidate_after.state - control_after.state
        )
        replacement_state_delta = (
            replacement_after.state - replacement_pre.state
        )
        observed_covariance_delta = (
            candidate_after.covariance - control_after.covariance
        )
        replacement_covariance_delta = (
            replacement_after.covariance
            - replacement_pre.covariance
        )
        delta_explained = (
            delta_explained
            and np.array_equal(
                observed_state_delta,
                replacement_state_delta,
            )
            and np.array_equal(
                observed_covariance_delta,
                replacement_covariance_delta,
            )
        )

        latest_measurement_timestamp = (
            build.latest_measurement_timestamps[track_id]
        )
        first_dt = max(
            build.previous_fusion_time - latest_measurement_timestamp,
            0.0,
        )
        second_dt = max(
            build.current_fusion_time - build.previous_fusion_time,
            0.0,
        )
        full_dt = first_dt + second_dt
        transition_second = cv_transition(second_dt)
        spectral_density = build.process_noise_spectral_density
        split_process_noise = (
            transition_second
            @ cv_process_noise(first_dt, spectral_density)
            @ transition_second.T
            + cv_process_noise(second_dt, spectral_density)
        )
        single_process_noise = cv_process_noise(
            full_dt,
            spectral_density,
        )
        expected_covariance_delta = (
            single_process_noise - split_process_noise
        )
        segmentation_residual_max_abs = max(
            segmentation_residual_max_abs,
            float(
                np.max(
                    np.abs(
                        replacement_covariance_delta
                        - expected_covariance_delta
                    )
                )
            ),
        )
        state_delta_norm_m = max(
            state_delta_norm_m,
            float(np.linalg.norm(observed_state_delta[:3])),
        )
        symmetric_covariance_delta = 0.5 * (
            observed_covariance_delta + observed_covariance_delta.T
        )
        eigenvalues = np.linalg.eigvalsh(symmetric_covariance_delta)
        covariance_delta_min_eigenvalue = min(
            covariance_delta_min_eigenvalue,
            float(eigenvalues[0]),
        )
        covariance_delta_max_eigenvalue = max(
            covariance_delta_max_eigenvalue,
            float(eigenvalues[-1]),
        )
        covariance_delta_max_abs = max(
            covariance_delta_max_abs,
            float(np.max(np.abs(observed_covariance_delta))),
        )

    no_formula_output = bool(
        not build.correction_produced
        and build.translation_ned is None
        and build.position_covariance_inflation is None
    )
    prediction_segmentation_explained = bool(
        segmentation_residual_max_abs <= 1.0e-12
    )
    strictly_attributed = bool(
        no_formula_output
        and materialization_unchanged
        and pre_matches_control
        and post_matches_base
        and published_matches_post
        and delta_explained
        and prediction_segmentation_explained
    )
    base.update(
        {
            "rejected_target_no_centroid_formula_output": (
                no_formula_output
            ),
            "rejected_target_pre_replacement_matches_control_bitwise": (
                pre_matches_control
            ),
            "rejected_target_post_replacement_matches_publication_base_bitwise": (
                post_matches_base
            ),
            "rejected_target_published_matches_post_replacement_bitwise": (
                published_matches_post
            ),
            "rejected_target_control_candidate_delta_explained_by_replacement_bitwise": (
                delta_explained
            ),
            "rejected_target_prediction_segmentation_residual_max_abs": (
                segmentation_residual_max_abs
            ),
            "rejected_target_state_delta_norm_m": state_delta_norm_m,
            "rejected_target_covariance_delta_min_eigenvalue": (
                covariance_delta_min_eigenvalue
            ),
            "rejected_target_covariance_delta_max_eigenvalue": (
                covariance_delta_max_eigenvalue
            ),
            "rejected_target_covariance_delta_max_abs": (
                covariance_delta_max_abs
            ),
            "rejected_target_publication_base_replacement_side_effect_present": (
                state_delta_norm_m > 0.0
                or covariance_delta_max_abs > 0.0
            ),
            "rejected_target_path_strictly_attributed": strictly_attributed,
            "rejected_target_delta_root_cause": (
                _REJECTED_REPLAY_REPLACEMENT_ROOT_CAUSE
                if strictly_attributed
                else "unresolved"
            ),
            "rejected_target_finite_difference_interpretation": (
                _REJECTED_REPLAY_REPLACEMENT_INTERPRETATION
                if strictly_attributed
                else "unresolved"
            ),
        }
    )
    return base


def _capture_state(state: Any) -> _StateCapture:
    return _StateCapture(
        state=np.asarray(state.state, dtype=float).copy(),
        covariance=np.asarray(state.covariance, dtype=float).copy(),
        timestamp=float(state.timestamp),
    )


def _capture_internal_states(
    adapter: FusionAdapter,
) -> dict[str, _StateCapture]:
    return {
        track_id: _capture_state(record.current_state)
        for track_id, record in adapter.tracks.items()
    }


def _state_capture_equal_bitwise(
    left: _StateCapture,
    right: _StateCapture,
) -> bool:
    return bool(
        left.timestamp == right.timestamp
        and np.array_equal(left.state, right.state)
        and np.array_equal(left.covariance, right.covariance)
    )


def _state_capture_maps_equal_bitwise(
    left: Mapping[str, _StateCapture],
    right: Mapping[str, _StateCapture],
) -> bool:
    return bool(
        tuple(sorted(left)) == tuple(sorted(right))
        and all(
            _state_capture_equal_bitwise(left[key], right[key])
            for key in left
        )
    )


def _capture_adapter_tracks(
    adapter: FusionAdapter,
    tracks: tuple[GlobalTrack, ...] | None = None,
) -> dict[str, _TrackCapture]:
    snapshots = (
        adapter.materialize_global_tracks().tracks
        if tracks is None
        else tuple(tracks)
    )
    captures: dict[str, _TrackCapture] = {}
    for track in snapshots:
        record = adapter.tracks[track.global_track_id]
        captures[track.global_track_id] = _TrackCapture(
            global_track_id=track.global_track_id,
            state=track.state.copy(),
            covariance=track.covariance.copy(),
            hits=int(record.hits),
            lineage=tuple(
                tuple(item.source_lineage_key)
                for item in record.observations
            ),
            source_support=tuple(sorted(track.source_support.items())),
            identity_likelihood=tuple(
                sorted(track.identity_likelihood.items())
            ),
            track_level=track.track_level.value,
        )
    return captures


def _frozen_frame_processing_signature(
    processing_order: tuple[dict[str, Any], ...],
) -> tuple[tuple[str, float, float, int], ...]:
    """Return only immutable scan identity fields shared by both arms."""

    return tuple(
        (
            str(item["scan_id"]),
            float(item["measurement_timestamp"]),
            float(item["arrival_timestamp"]),
            int(item["observation_count"]),
        )
        for item in processing_order
    )


def _component_global_track_ids(
    tracks: tuple[GlobalTrack, ...],
    evidence: tuple[StructuralAmbiguityEvidence, ...],
) -> tuple[str, ...]:
    tokens = {
        member.opaque_member_track_token
        for item in evidence
        for member in item.member_states
    }
    return tuple(
        sorted(
            track.global_track_id
            for track in tracks
            if track.metadata.get("opaque_member_track_token") in tokens
        )
    )


def _freeze_and_roundtrip_frames(
    scenario: _DiagnosticScenario,
) -> tuple[tuple[SensorScanFrame, ...], dict[str, Any]]:
    source_timestamp_signature = _observation_timestamp_signature(
        scenario.frames
    )
    observations = tuple(
        observation
        for frame in scenario.frames
        for observation in frame.observations
    )
    schedule_payload = [
        _frame_order_item(frame) for frame in scenario.frames
    ]
    config_payload = {
        "scenario_id": scenario.scenario_id,
        "scenario_version": (
            STRUCTURAL_AMBIGUITY_REPLAY_SCENARIO_VERSION
        ),
        "preset_costs": {
            str(key): value.tolist()
            for key, value in sorted(scenario.preset_costs.items())
        },
        "max_lateness_s": 0.15,
    }
    provenance = ReplayProvenance(
        scenario_id=scenario.scenario_id,
        scenario_version=STRUCTURAL_AMBIGUITY_REPLAY_SCENARIO_VERSION,
        config_id="d1-neutral-centroid-boundary-diagnostic",
        config_digest=_canonical_sha256(config_payload),
        config_version="d1-neutral-centroid-boundary-config-v1",
        scenario_digest=_canonical_sha256(schedule_payload),
        run_id=f"{scenario.scenario_id}-frozen-v1",
        seed=1100,
        source_format="d1_frozen_structural_ambiguity_diagnostic",
        producer="D1",
        metadata={
            "boundary_diagnostic_only": True,
        },
    )
    bundle = serialize_governed_replay(observations, provenance)
    records = list(bundle["records"])
    roundtrip_frames: list[SensorScanFrame] = []
    cursor = 0
    for source_frame in scenario.frames:
        count = len(source_frame.observations)
        restored = tuple(
            sensor_observation_from_jsonl_record(record)
            for record in records[cursor : cursor + count]
        )
        cursor += count
        roundtrip_frames.append(
            SensorScanFrame.from_observations(
                restored,
                scan_id=source_frame.scan_id,
            )
        )
    if cursor != len(records):
        raise RuntimeError("frozen replay frame reconstruction was incomplete")
    roundtrip_timestamp_signature = _observation_timestamp_signature(
        tuple(roundtrip_frames)
    )
    if source_timestamp_signature != roundtrip_timestamp_signature:
        raise RuntimeError(
            "frozen replay did not preserve observation dual timestamps"
        )
    return tuple(roundtrip_frames), {
        "bundle_schema_version": bundle["manifest"]["schema_version"],
        "bundle_sha256": _canonical_sha256(bundle),
        "observation_count": bundle["manifest"]["observation_count"],
        "frame_count": len(roundtrip_frames),
        "measurement_timestamp_range": bundle["manifest"][
            "measurement_timestamp_range"
        ],
        "arrival_timestamp_range": bundle["manifest"][
            "arrival_timestamp_range"
        ],
        "working_frame": bundle["manifest"]["working_frame"],
        "truth_policy": bundle["manifest"]["truth_policy"],
        "roundtrip_complete": True,
        "dual_timestamps_preserved": True,
        "observation_timestamp_signature_sha256": _canonical_sha256(
            roundtrip_timestamp_signature
        ),
    }


def _organize_frames(
    frames: tuple[SensorScanFrame, ...],
) -> tuple[tuple[SensorScanFrame, ...], dict[str, Any]]:
    organizer = ScanInputOrganizer(
        ScanInputConfig(
            max_lateness_s=0.15,
            max_buffer_residence_s=5.0,
        )
    )
    released: list[SensorScanFrame] = []
    events: list[dict[str, Any]] = []
    for frame in frames:
        result = organizer.ingest(frame)
        released.extend(result.released_scans)
        events.extend(_compact_scan_events(result.events))
    tail = organizer.close()
    released.extend(tail.released_scans)
    events.extend(_compact_scan_events(tail.events))
    return tuple(released), {
        "config": organizer.config.to_dict(),
        "audit": organizer.audit_summary().to_dict(),
        "events": events,
        "released_scan_ids": [item.scan_id for item in released],
    }


def _compact_scan_events(events: tuple[Any, ...]) -> list[dict[str, Any]]:
    return [
        {
            "event_sequence": item.event_sequence,
            "received_sequence": item.received_sequence,
            "scan_id": item.scan_id,
            "measurement_timestamp": item.measurement_timestamp,
            "arrival_timestamp": item.arrival_timestamp,
            "outcome": item.outcome,
            "reason": item.reason,
            "buffered": item.buffered,
            "reordered": item.reordered,
            "released": item.released,
            "too_late": item.too_late,
        }
        for item in events
    ]


def _build_scenarios() -> tuple[_DiagnosticScenario, ...]:
    balanced_positions = (
        np.array([1_000.0, -120.0, -100.0]),
        np.array([1_000.0, 120.0, -100.0]),
    )
    cycle_costs = np.array([[1.0, 2.0], [2.0, 1.0]])
    synchronous_frames = (
        _frame(0, balanced_positions, 0.0, 0.2, "sync-seed-000"),
        _frame(
            1,
            _shift(balanced_positions, 10.0),
            0.2,
            0.4,
            "sync-seed-001",
        ),
        _frame(
            2,
            _shift(balanced_positions, 35.0),
            0.4,
            0.6,
            "sync-target-002",
        ),
    )

    reordered_frames = (
        _frame(0, balanced_positions, 0.0, 0.2, "oosm-seed-000"),
        _frame(
            1,
            _shift(balanced_positions, 10.0),
            0.2,
            0.4,
            "oosm-seed-001",
        ),
        _frame(
            2,
            _shift(balanced_positions, 20.0),
            0.4,
            0.6,
            "oosm-watermark-002",
        ),
        _frame(
            3,
            _shift(balanced_positions, 25.0),
            0.3,
            0.65,
            "oosm-target-003",
        ),
    )

    unbalanced_positions = (
        np.array([1_000.0, -250.0, -100.0]),
        np.array([1_000.0, 0.0, -100.0]),
        np.array([1_000.0, 250.0, -100.0]),
    )
    unbalanced_scan_positions = (
        np.array([1_020.0, 0.0, -100.0]),
        np.array([1_020.0, 250.0, -100.0]),
    )
    unbalanced_frames = (
        _frame(0, unbalanced_positions, 0.0, 0.2, "unbalanced-seed-000"),
        _frame(
            1,
            _shift(unbalanced_positions, 10.0),
            0.2,
            0.4,
            "unbalanced-seed-001",
        ),
        _frame(
            2,
            unbalanced_scan_positions,
            0.4,
            0.6,
            "unbalanced-target-002",
        ),
    )
    return (
        _DiagnosticScenario(
            scenario_id="d1-centroid-sync-balanced-cycle",
            scenario_kind="synchronous_balanced_cycle",
            frames=synchronous_frames,
            target_scan_id="sync-target-002",
            preset_costs={2: cycle_costs},
            expected_rejection_reason=None,
        ),
        _DiagnosticScenario(
            scenario_id="d1-centroid-reordered-balanced-cycle",
            scenario_kind="reordered_balanced_cycle",
            frames=reordered_frames,
            target_scan_id="oosm-target-003",
            preset_costs={3: cycle_costs},
            expected_rejection_reason="oosm_scan",
        ),
        _DiagnosticScenario(
            scenario_id="d1-centroid-unbalanced-component",
            scenario_kind="unbalanced_component",
            frames=unbalanced_frames,
            target_scan_id="unbalanced-target-002",
            preset_costs={
                2: np.array(
                    [
                        [1.58, _INVALID_COST],
                        [0.80, _INVALID_COST],
                        [_INVALID_COST, 0.50],
                    ]
                )
            },
            expected_rejection_reason="unbalanced_component",
        ),
    )


def _frame(
    scan_index: int,
    positions: tuple[np.ndarray, ...],
    measurement_timestamp: float,
    arrival_timestamp: float,
    scan_id: str,
) -> SensorScanFrame:
    observations = tuple(
        _radar_observation(
            scan_index,
            observation_index,
            position,
            measurement_timestamp,
            arrival_timestamp,
            scan_id,
        )
        for observation_index, position in enumerate(positions)
    )
    return SensorScanFrame.from_observations(
        observations,
        scan_id=scan_id,
    )


def _radar_observation(
    scan_index: int,
    observation_index: int,
    position_ned: np.ndarray,
    measurement_timestamp: float,
    arrival_timestamp: float,
    scan_id: str,
) -> SensorObservation:
    position = np.asarray(position_ned, dtype=float)
    range_m = float(np.linalg.norm(position))
    horizontal_m = float(np.linalg.norm(position[:2]))
    observation_id = f"d1diag-s{scan_index:03d}-o{observation_index:03d}"
    return SensorObservation(
        observation_id=observation_id,
        sensor_id="D1-DIAGNOSTIC-RADAR",
        modality="radar",
        measurement_timestamp=measurement_timestamp,
        arrival_timestamp=arrival_timestamp,
        frame_id="ned",
        measurement=np.array(
            [
                range_m,
                math.atan2(float(position[1]), float(position[0])),
                math.atan2(
                    float(-position[2]),
                    max(horizontal_m, 1.0e-9),
                ),
                0.0,
            ],
            dtype=float,
        ),
        covariance=radar_covariance_from_range(range_m),
        metadata={
            "sensor_position_ned": _SENSOR_POSITION_NED,
            "scan_id": scan_id,
            "sequence_id": scan_index,
            "diagnostic_scan_index": scan_index,
            "coverage_cell": "d1-centroid-boundary-cell",
            "working_frame": "ned",
            "source_lineage_key": (
                "d1-centroid-boundary-v1",
                scan_id,
                observation_id,
            ),
            "radial_velocity_observed": False,
            "filter_measurement_dimension": 3,
            "filter_innovation_gate_chi2": CHI2_3_999,
            "radial_velocity_placeholder_ignored": True,
            "unobserved_velocity_variance_m2ps2": 25.0,
            "spherical_covariance_to_ned": "analytic_jacobian",
        },
    )


def _shift(
    positions: tuple[np.ndarray, ...],
    north_m: float,
) -> tuple[np.ndarray, ...]:
    delta = np.array([north_m, 0.0, 0.0])
    return tuple(position + delta for position in positions)


def _frame_order_item(frame: SensorScanFrame) -> dict[str, Any]:
    return {
        "scan_id": frame.scan_id,
        "measurement_timestamp": frame.measurement_timestamp,
        "arrival_timestamp": frame.arrival_timestamp,
        "observation_count": len(frame.observations),
    }


def _observation_timestamp_signature(
    frames: tuple[SensorScanFrame, ...],
) -> tuple[tuple[str, str, float, float], ...]:
    return tuple(
        (
            frame.scan_id,
            observation.observation_id,
            float(observation.measurement_timestamp),
            float(observation.arrival_timestamp),
        )
        for frame in frames
        for observation in frame.observations
    )


def _component_summary(
    evidence: StructuralAmbiguityEvidence,
) -> dict[str, Any]:
    return {
        "evidence_id": evidence.evidence_id,
        "measurement_timestamp": evidence.measurement_timestamp,
        "arrival_timestamp": evidence.arrival_timestamp,
        "member_count": evidence.member_count,
        "observation_count": evidence.observation_count,
        "candidate_edge_count": evidence.candidate_edge_count,
        "maximum_matching_cardinality": (
            evidence.maximum_matching_cardinality
        ),
        "free_row_count": evidence.free_row_count,
        "free_column_count": evidence.free_column_count,
        "component_kinds": list(evidence.component_kinds),
        "posterior_update_applied": evidence.posterior_update_applied,
        "update_mode": evidence.update_mode,
        "cross_covariance_available": (
            evidence.cross_covariance_available
        ),
    }


def _audit_delta(
    before: dict[str, Any],
    after: dict[str, Any],
    key: str,
) -> int:
    return int(after.get(key, 0)) - int(before.get(key, 0))


def _scenario_name_cn(kind: str) -> str:
    return {
        "synchronous_balanced_cycle": "同步平衡交替环",
        "reordered_balanced_cycle": "乱序平衡交替环",
        "unbalanced_component": "数量不平衡分量",
    }[kind]


def _canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _validate_scenario_result(result: dict[str, Any]) -> None:
    outcome = result["target_outcome"]
    expected = result["expected_rejection_reason"]
    if not result["frozen_replay"]["dual_timestamps_preserved"]:
        raise RuntimeError("frozen replay did not preserve dual timestamps")
    if not result["control_and_candidate_consumed_same_frozen_frames"]:
        raise RuntimeError("control and candidate did not consume one frozen input")
    if expected is None:
        if outcome["applied_component_count"] != 1:
            raise RuntimeError("synchronous component did not apply once")
        required_checks = (
            "global_track_id_unchanged",
            "velocity_unchanged",
            "relative_position_unchanged",
            "hits_unchanged",
            "lineage_unchanged",
            "identity_unchanged",
            "common_translation",
            "translation_nonzero",
            "translation_bounded",
            "covariance_not_contracted",
        )
        if not all(result["invariant_checks"][key] for key in required_checks):
            raise RuntimeError("synchronous component invariant failed")
    else:
        if outcome["applied_component_count"] != 0:
            raise RuntimeError("fail-closed scenario unexpectedly applied")
        if outcome["rejection_reason"] != expected:
            raise RuntimeError(
                f"expected {expected!r}, got {outcome['rejection_reason']!r}"
            )
        required_checks = (
            "global_track_id_unchanged",
            "hits_unchanged",
            "hits_equal_to_control",
            "lineage_unchanged",
            "lineage_equal_to_control",
            "identity_unchanged",
            "identity_equal_to_control",
            "rejected_target_no_centroid_formula_output",
            "rejected_target_pre_replacement_matches_control_bitwise",
            "rejected_target_post_replacement_matches_publication_base_bitwise",
            "rejected_target_published_matches_post_replacement_bitwise",
            "rejected_target_control_candidate_delta_explained_by_replacement_bitwise",
            "rejected_target_publication_base_replacement_side_effect_present",
            "rejected_target_path_strictly_attributed",
            "rejected_scenario_covariance_delta_diagnostic_only",
        )
        if not all(result["invariant_checks"][key] for key in required_checks):
            raise RuntimeError(
                "fail-closed scenario path attribution was incomplete"
            )
        covariance_delta = result["invariant_checks"][
            "rejected_target_covariance_delta_min_eigenvalue"
        ]
        if (
            covariance_delta is None
            or not math.isfinite(covariance_delta)
            or covariance_delta >= 0.0
        ):
            raise RuntimeError(
                "rejected scenario did not retain its finite covariance delta"
            )
        if result["promotion_boundary"] != _CANDIDATE_NOT_PROMOTED:
            raise RuntimeError(
                "rejected scenario crossed the candidate-not-promoted boundary"
            )
    if result["invariant_checks"]["candidate_promotion_evidence_eligible"]:
        raise RuntimeError(
            "controlled boundary scenario cannot be candidate promotion evidence"
        )
    if (
        result["invariant_checks"]["candidate_promotion_ineligibility_reason"]
        != _PROMOTION_INELIGIBILITY_REASON
    ):
        raise RuntimeError(
            "controlled boundary promotion ineligibility reason changed"
        )
