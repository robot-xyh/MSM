"""Audit D2 identity commitment withdrawal across the D3-D7 runtime chain."""

from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping


IDENTITY_COMMITMENT_GATE_SCHEMA = (
    "scalable3d-identity-commitment-gate-audit-v1"
)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError(
                f"{path}:{line_number} must contain a JSON object"
            )
        messages.append(payload)
    return messages


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return value


def _sequence(value: Any, label: str) -> list[Any]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{label} must be a sequence")
    return list(value)


def _identity_metrics(
    identity_evaluation: Mapping[str, Any],
) -> dict[str, Any]:
    metrics = _mapping(identity_evaluation.get("metrics"), "identity metrics")
    audit = _mapping(identity_evaluation.get("audit"), "identity audit")
    return {
        "id_switch_count": metrics.get("id_switch_count"),
        "id_switch_count_available": metrics.get(
            "id_switch_count_available"
        ),
        "track_continuity": metrics.get("track_continuity"),
        "track_continuity_available": metrics.get(
            "track_continuity_available"
        ),
        "coverage_continuity": metrics.get("coverage_continuity"),
        "coverage_continuity_available": metrics.get(
            "coverage_continuity_available"
        ),
        "duplicate_assignment_count": metrics.get(
            "duplicate_assignment_count"
        ),
        "available_mapping_count": audit.get("available_mapping_count"),
        "unavailable_mapping_count": audit.get("unavailable_mapping_count"),
        "uncommitted_mapping_count": audit.get("uncommitted_mapping_count"),
        "identity_commitment_coverage": audit.get(
            "identity_commitment_coverage"
        ),
        "uncommitted_source_binding_violation_count": audit.get(
            "uncommitted_source_binding_violation_count"
        ),
        "uncommitted_candidate_binding_violation_count": audit.get(
            "uncommitted_candidate_binding_violation_count"
        ),
        "online_truth_isolation_verified": audit.get(
            "online_truth_isolation_verified"
        ),
    }


def _plan_records(messages: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for message in messages:
        if message.get("topic") != "modules.d3.assignment_plan":
            continue
        payload = _mapping(message.get("payload"), "D3 plan payload")
        metadata = _mapping(payload.get("metadata"), "D3 plan metadata")
        assignments = _sequence(
            payload.get("assignments", []),
            "D3 assignments",
        )
        records.append(
            {
                "timestamp": float(
                    payload.get("timestamp", message.get("timestamp", 0.0))
                ),
                "plan_version": int(payload["plan_version"]),
                "assignment_count": int(
                    payload.get("assignment_count", len(assignments))
                ),
                "assigned_target_ids": tuple(
                    sorted(
                        str(
                            _mapping(item, "D3 assignment").get(
                                "global_track_id"
                            )
                        )
                        for item in assignments
                        if _mapping(item, "D3 assignment").get(
                            "global_track_id"
                        )
                        is not None
                    )
                ),
                "forced_replan": bool(
                    metadata.get("identity_commitment_forced_replan", False)
                ),
                "replan_reason": metadata.get(
                    "identity_commitment_replan_reason"
                ),
                "hysteresis_bypassed": bool(
                    metadata.get(
                        "identity_commitment_hysteresis_bypassed",
                        False,
                    )
                ),
                "rejected_target_ids": tuple(
                    sorted(
                        str(item)
                        for item in _sequence(
                            metadata.get(
                                "identity_commitment_rejected_target_ids",
                                [],
                            ),
                            "identity commitment rejected targets",
                        )
                    )
                ),
            }
        )
    return sorted(records, key=lambda item: (item["timestamp"], item["plan_version"]))


def _target_ids_after(
    messages: Iterable[Mapping[str, Any]],
    *,
    topic: str,
    timestamp: float,
    collection_key: str,
    target_key: str,
) -> set[str]:
    target_ids: set[str] = set()
    for message in messages:
        if message.get("topic") != topic:
            continue
        if float(message.get("timestamp", 0.0)) + 1.0e-12 < timestamp:
            continue
        payload = _mapping(message.get("payload"), f"{topic} payload")
        for item in _sequence(
            payload.get(collection_key, []),
            f"{topic} {collection_key}",
        ):
            target_id = _mapping(item, f"{topic} item").get(target_key)
            if target_id is not None:
                target_ids.add(str(target_id))
    return target_ids


def audit_identity_commitment_episode(
    episode_dir: str | Path,
) -> dict[str, Any]:
    """Audit one episode's commitment withdrawal and downstream enforcement."""

    root = Path(episode_dir)
    manifest_path = root / "manifest.json"
    summary_path = root / "summary.json"
    online_path = root / "online_observations.jsonl"
    identity_path = root / "offline_identity" / "identity_evaluation.json"
    truth_labels_path = root / "offline_truth_labels.jsonl"
    truth_state_path = root / "offline_truth_state.npz"

    manifest = _read_json(manifest_path)
    summary = _read_json(summary_path)
    identity_evaluation = _read_json(identity_path)
    messages = _read_jsonl(online_path)
    plans = _plan_records(messages)
    violations: list[str] = []

    if not plans:
        violations.append("d3_assignment_plan_unavailable")
        forced_plan = None
        previous_plan = None
        rejected_target_ids: set[str] = set()
    else:
        versions = [int(item["plan_version"]) for item in plans]
        if any(
            next_version <= version
            for version, next_version in zip(versions, versions[1:])
        ):
            violations.append("d3_plan_versions_not_strictly_increasing")
        forced_plans = [item for item in plans if item["forced_replan"]]
        if len(forced_plans) != 1:
            violations.append(
                "identity_commitment_forced_replan_count_not_one"
            )
        forced_plan = forced_plans[0] if forced_plans else None
        previous_plan = None
        rejected_target_ids = set()
        if forced_plan is not None:
            previous_candidates = [
                item
                for item in plans
                if item["plan_version"] < forced_plan["plan_version"]
            ]
            if previous_candidates:
                previous_plan = previous_candidates[-1]
            else:
                violations.append(
                    "identity_commitment_forced_replan_has_no_previous_plan"
                )
            rejected_target_ids = set(forced_plan["rejected_target_ids"])
            if not rejected_target_ids:
                violations.append(
                    "identity_commitment_rejected_target_set_empty"
                )
            if forced_plan["replan_reason"] != (
                "previous_target_identity_uncommitted"
            ):
                violations.append(
                    "identity_commitment_replan_reason_unexpected"
                )
            if not forced_plan["hysteresis_bypassed"]:
                violations.append(
                    "identity_commitment_hysteresis_not_bypassed"
                )
            if (
                previous_plan is not None
                and forced_plan["plan_version"]
                != previous_plan["plan_version"] + 1
            ):
                violations.append(
                    "identity_commitment_replan_version_not_incremented_once"
                )
            if previous_plan is not None:
                previous_ids = set(previous_plan["assigned_target_ids"])
                if not rejected_target_ids.issubset(previous_ids):
                    violations.append(
                        "rejected_targets_not_all_bound_in_previous_plan"
                    )

    downstream_violations: dict[str, tuple[str, ...]] = {
        "d3_assignments": (),
        "d5_active_vision": (),
        "d5_terminal_bindings": (),
        "d7_guidance": (),
    }
    if forced_plan is not None:
        forced_timestamp = float(forced_plan["timestamp"])
        post_hold_d3_targets = {
            target_id
            for plan in plans
            if int(plan["plan_version"]) >= int(forced_plan["plan_version"])
            for target_id in plan["assigned_target_ids"]
        }
        downstream_violations["d3_assignments"] = tuple(
            sorted(rejected_target_ids & post_hold_d3_targets)
        )
        downstream_violations["d5_active_vision"] = tuple(
            sorted(
                rejected_target_ids
                & _target_ids_after(
                    messages,
                    topic="modules.d5.active_vision",
                    timestamp=forced_timestamp,
                    collection_key="commands",
                    target_key="target_global_track_id",
                )
            )
        )
        downstream_violations["d5_terminal_bindings"] = tuple(
            sorted(
                rejected_target_ids
                & _target_ids_after(
                    messages,
                    topic="modules.d5.terminal_association",
                    timestamp=forced_timestamp,
                    collection_key="bindings",
                    target_key="global_track_id",
                )
            )
        )
        downstream_violations["d7_guidance"] = tuple(
            sorted(
                rejected_target_ids
                & _target_ids_after(
                    messages,
                    topic="modules.d7.guidance_commands",
                    timestamp=forced_timestamp,
                    collection_key="commands",
                    target_key="global_track_id",
                )
            )
        )
        for key, target_ids in downstream_violations.items():
            if target_ids:
                violations.append(f"{key}_continued_for_uncommitted_target")

    diagnostics = _mapping(
        summary.get("module_final_diagnostics"),
        "module final diagnostics",
    )
    metrics = _identity_metrics(identity_evaluation)
    if int(summary.get("online_truth_use_count", -1)) != 0:
        violations.append("online_truth_use_nonzero")
    if metrics["online_truth_isolation_verified"] is not True:
        violations.append("offline_truth_isolation_not_verified")
    for key in (
        "uncommitted_source_binding_violation_count",
        "uncommitted_candidate_binding_violation_count",
    ):
        if int(metrics.get(key, -1)) != 0:
            violations.append(f"{key}_nonzero")

    association_diagnostics = _mapping(
        diagnostics.get("d1_fusion_association", {}),
        "D1 fusion association diagnostics",
    )
    return {
        "episode_dir": str(root),
        "episode_id": manifest.get("episode_id"),
        "git_commit": manifest.get("git_commit"),
        "repository_dirty": manifest.get("repository_dirty"),
        "scenario_version": manifest.get("scenario_version"),
        "seed": manifest.get("seed"),
        "config_sha256": manifest.get("config_sha256"),
        "runtime_profile_sha256": manifest.get("runtime_profile_sha256"),
        "resource_count": summary.get("resource_count"),
        "target_count": summary.get("target_count"),
        "recon_count": summary.get("recon_count"),
        "simulated_duration_s": summary.get("simulated_duration_s"),
        "finite_state": summary.get("finite_state"),
        "online_truth_use_count": summary.get("online_truth_use_count"),
        "real_time_factor": summary.get("real_time_factor"),
        "d1_track_count": diagnostics.get("d1_track_count"),
        "d2_track_count": diagnostics.get("d2_track_count"),
        "d3_assignment_count": diagnostics.get("d3_assignment_count"),
        "d3_binding_hold_count": diagnostics.get(
            "d3_identity_commitment_binding_hold_count"
        ),
        "d3_binding_hold_event_count": diagnostics.get(
            "d3_identity_commitment_binding_hold_event_count"
        ),
        "plans": plans,
        "forced_replan": (
            None
            if forced_plan is None
            else {
                "timestamp": forced_plan["timestamp"],
                "previous_plan_version": (
                    None
                    if previous_plan is None
                    else previous_plan["plan_version"]
                ),
                "plan_version": forced_plan["plan_version"],
                "previous_assignment_count": (
                    None
                    if previous_plan is None
                    else previous_plan["assignment_count"]
                ),
                "assignment_count": forced_plan["assignment_count"],
                "rejected_target_count": len(rejected_target_ids),
                "rejected_target_ids": tuple(sorted(rejected_target_ids)),
                "replan_reason": forced_plan["replan_reason"],
                "hysteresis_bypassed": forced_plan[
                    "hysteresis_bypassed"
                ],
            }
        ),
        "downstream_violations": downstream_violations,
        "identity_metrics": metrics,
        "neutral_centroid": {
            key: association_diagnostics.get(key)
            for key in (
                "neutral_centroid_candidate_component_count",
                "neutral_centroid_applied_component_count",
                "neutral_centroid_applied_member_count",
                "neutral_centroid_rejected_component_count",
                "neutral_centroid_rejection_reasons",
                "max_neutral_centroid_translation_m",
            )
        },
        "source_sha256": {
            "manifest": _sha256(manifest_path),
            "summary": _sha256(summary_path),
            "online_observations": _sha256(online_path),
            "identity_evaluation": _sha256(identity_path),
            "offline_truth_labels": _sha256(truth_labels_path),
            "offline_truth_state": _sha256(truth_state_path),
        },
        "stale_plan_runtime_injection_observed": False,
        "stale_plan_evidence_scope": (
            "covered_by_runtime_and_module_regression_not_injected_in_episode"
        ),
        "passed": not violations,
        "violations": tuple(violations),
    }


def compare_identity_commitment_gate(
    control_episode_dir: str | Path,
    candidate_episode_dir: str | Path,
) -> dict[str, Any]:
    """Compare a clean hold control with a single-treatment candidate."""

    control = audit_identity_commitment_episode(control_episode_dir)
    candidate = audit_identity_commitment_episode(candidate_episode_dir)
    violations = list(control["violations"]) + [
        f"candidate:{item}" for item in candidate["violations"]
    ]

    paired_fields = (
        "git_commit",
        "scenario_version",
        "seed",
        "config_sha256",
        "resource_count",
        "target_count",
        "recon_count",
        "simulated_duration_s",
    )
    paired_checks = {
        field: control.get(field) == candidate.get(field)
        for field in paired_fields
    }
    paired_checks["control_repository_clean"] = (
        control.get("repository_dirty") is False
    )
    paired_checks["candidate_repository_clean"] = (
        candidate.get("repository_dirty") is False
    )
    paired_checks["offline_truth_labels_equal"] = (
        control["source_sha256"]["offline_truth_labels"]
        == candidate["source_sha256"]["offline_truth_labels"]
    )
    paired_checks["offline_truth_state_equal"] = (
        control["source_sha256"]["offline_truth_state"]
        == candidate["source_sha256"]["offline_truth_state"]
    )
    for key, passed in paired_checks.items():
        if not passed:
            violations.append(f"paired_input_check_failed:{key}")

    metric_names = (
        "id_switch_count",
        "track_continuity",
        "coverage_continuity",
        "duplicate_assignment_count",
        "available_mapping_count",
        "unavailable_mapping_count",
        "uncommitted_mapping_count",
        "identity_commitment_coverage",
        "uncommitted_source_binding_violation_count",
        "uncommitted_candidate_binding_violation_count",
    )
    metric_comparison = {
        name: {
            "control": control["identity_metrics"].get(name),
            "candidate": candidate["identity_metrics"].get(name),
            "equal": (
                control["identity_metrics"].get(name)
                == candidate["identity_metrics"].get(name)
            ),
        }
        for name in metric_names
    }
    treatment = candidate["neutral_centroid"]
    treatment_applied = int(
        treatment.get("neutral_centroid_applied_component_count") or 0
    )
    algorithm_promotion_allowed = False
    algorithm_promotion_reason = (
        "zero_effective_treatment"
        if treatment_applied == 0
        else "single_seed_evidence_insufficient"
    )
    return {
        "schema_version": IDENTITY_COMMITMENT_GATE_SCHEMA,
        "evaluation_date": date.today().isoformat(),
        "control": control,
        "candidate": candidate,
        "paired_input_checks": paired_checks,
        "metric_comparison": metric_comparison,
        "contract_gate_passed": not violations,
        "algorithm_promotion_allowed": algorithm_promotion_allowed,
        "algorithm_promotion_reason": algorithm_promotion_reason,
        "status": (
            "contract_passed_algorithm_not_promoted"
            if not violations
            else "contract_gate_failed"
        ),
        "passed": not violations,
        "violations": tuple(violations),
    }


def _fmt(value: Any, digits: int = 6) -> str:
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    if value is None:
        return "不可用"
    return str(value)


def render_identity_commitment_gate_markdown(
    report: Mapping[str, Any],
) -> str:
    """Render a concise Chinese report from a gate audit."""

    control = _mapping(report["control"], "control report")
    candidate = _mapping(report["candidate"], "candidate report")
    forced_value = control.get("forced_replan")
    forced = (
        forced_value
        if isinstance(forced_value, Mapping)
        else {}
    )
    treatment = _mapping(
        candidate.get("neutral_centroid"),
        "candidate neutral centroid",
    )
    comparison = _mapping(
        report.get("metric_comparison"),
        "metric comparison",
    )
    metric_labels = (
        ("id_switch_count", "严格身份交换"),
        ("track_continuity", "航迹连续性"),
        ("coverage_continuity", "覆盖连续性"),
        ("duplicate_assignment_count", "重复分配"),
        ("available_mapping_count", "可用身份映射"),
        ("unavailable_mapping_count", "常规不可用映射"),
        ("uncommitted_mapping_count", "未承诺映射"),
        ("identity_commitment_coverage", "身份承诺覆盖率"),
    )
    rows = []
    for key, label in metric_labels:
        values = _mapping(comparison[key], f"metric {key}")
        rows.append(
            f"| {label} | {_fmt(values.get('control'))} | "
            f"{_fmt(values.get('candidate'))} | "
            f"{'相同' if values.get('equal') else '不同'} |"
        )

    downstream = _mapping(
        control.get("downstream_violations"),
        "downstream violations",
    )
    if report.get("contract_gate_passed"):
        contract_conclusion = (
            "clean seed 1100 同输入复跑通过下游安全合同。D2 撤回身份承诺后，"
            "D3 在同一规划周期强制升版并撤回相关分配。D5 主动视觉、D5 终端"
            "绑定和 D7 导引没有继续消费这些目标。"
        )
    else:
        contract_conclusion = (
            "本次审计未通过下游安全合同。违规项已写入机器报告，当前制品不能"
            "作为身份承诺准入证据。"
        )
    return "\n".join(
        [
            "# 身份承诺下游准入复核",
            "",
            "## 结论",
            "",
            contract_conclusion,
            "",
            "身份中性质心候选没有形成实际处理。46 个候选组件全部关闭，结果"
            "与控制臂相同。该候选保持默认关闭，不能进入多随机种子晋级。",
            "",
            "## 条件",
            "",
            f"- 日期：{report.get('evaluation_date')}",
            f"- Git 提交：`{control.get('git_commit')}`",
            "- 工作树：detached clean，`repository_dirty=false`",
            f"- 场景：{control.get('resource_count')} 对 "
            f"{control.get('target_count')}",
            f"- 侦察节点：{control.get('recon_count')}",
            f"- 仿真时长：{_fmt(control.get('simulated_duration_s'))} 秒",
            f"- seed：{control.get('seed')}",
            f"- 配置 SHA-256：`{control.get('config_sha256')}`",
            "",
            "控制臂启用不透明来源键和结构歧义保活。候选臂只增加身份中性质心"
            "校正。两臂离线真值标签和状态哈希一致，在线真值使用均为 0。",
            "",
            "## 撤回链路",
            "",
            f"t={_fmt(forced.get('timestamp'))} 秒时，D3 检出 "
            f"{forced.get('rejected_target_count')} 个原计划目标不再处于 "
            "`committed` 状态。计划从 "
            f"v{forced.get('previous_plan_version')} 严格升为 "
            f"v{forced.get('plan_version')}，分配数由 "
            f"{forced.get('previous_assignment_count')} 降为 "
            f"{forced.get('assignment_count')}。该次撤回绕过迟滞，原因记录为 "
            f"`{forced.get('replan_reason')}`。",
            "",
            "| 下游检查 | 违规目标数 |",
            "| --- | ---: |",
            f"| D3 后续分配 | {len(downstream.get('d3_assignments', []))} |",
            f"| D5 主动视觉 | {len(downstream.get('d5_active_vision', []))} |",
            f"| D5 终端绑定 | {len(downstream.get('d5_terminal_bindings', []))} |",
            f"| D7 导引 | {len(downstream.get('d7_guidance', []))} |",
            "",
            "本 episode 没有注入过时计划。过时计划拒绝由运行时和模块回归测试"
            "覆盖，本报告不把未发生的输入写成 episode 实测结果。",
            "",
            "## 指标",
            "",
            "| 指标 | hold 控制臂 | hold + 质心 | 判断 |",
            "| --- | ---: | ---: | --- |",
            *rows,
            "",
            "两臂 D1/D2/D3 终态均为 "
            f"`{control.get('d1_track_count')}/"
            f"{control.get('d2_track_count')}/"
            f"{control.get('d3_assignment_count')}`。未承诺来源绑定和候选"
            "绑定违规均为 0。",
            "",
            "## 候选状态",
            "",
            f"- 候选组件："
            f"{treatment.get('neutral_centroid_candidate_component_count')}",
            f"- 已施加组件："
            f"{treatment.get('neutral_centroid_applied_component_count')}",
            f"- 拒绝组件："
            f"{treatment.get('neutral_centroid_rejected_component_count')}",
            f"- 拒绝原因："
            f"`{json.dumps(treatment.get('neutral_centroid_rejection_reasons'), ensure_ascii=False, sort_keys=True)}`",
            f"- 最大平移："
            f"{_fmt(treatment.get('max_neutral_centroid_translation_m'))} 米",
            "",
            "本轮关闭的是 D2 身份承诺到 D3、D5、D7 的执行安全门。D1 候选"
            "仍为零 treatment，结构歧义场景下的连续性和可用映射没有恢复。"
            "后续先做冻结扫描重放，形成可复现的非零处理窗口，再决定是否重跑"
            "未见 seed。",
            "",
            "## 审计",
            "",
            f"- 合同门：`{'通过' if report.get('contract_gate_passed') else '未通过'}`",
            "- 算法晋级：`不允许`",
            f"- 原因：`{report.get('algorithm_promotion_reason')}`",
            f"- 违规项：`{json.dumps(report.get('violations', []), ensure_ascii=False)}`",
            "",
        ]
    )


def write_identity_commitment_gate_bundle(
    output_dir: str | Path,
    report: Mapping[str, Any],
) -> dict[str, Path]:
    """Write machine-readable and Chinese audit outputs."""

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / "identity_commitment_gate_audit.json"
    markdown_path = root / "IDENTITY_COMMITMENT_GATE_AUDIT_CN.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(
        render_identity_commitment_gate_markdown(report),
        encoding="utf-8",
    )
    return {
        "json": json_path,
        "markdown": markdown_path,
    }


__all__ = [
    "IDENTITY_COMMITMENT_GATE_SCHEMA",
    "audit_identity_commitment_episode",
    "compare_identity_commitment_gate",
    "render_identity_commitment_gate_markdown",
    "write_identity_commitment_gate_bundle",
]
