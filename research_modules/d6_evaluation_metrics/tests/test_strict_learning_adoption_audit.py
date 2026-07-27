from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from functools import lru_cache
from hashlib import sha256
import importlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
for module_path in (
    REPOSITORY_ROOT / "research_modules" / "d3_assignment_planner" / "src",
    REPOSITORY_ROOT / "research_modules" / "d3_assignment_planner" / "tests",
    REPOSITORY_ROOT / "research_modules" / "d4_distributed_fallback",
    REPOSITORY_ROOT / "research_modules" / "d5_terminal_association" / "src",
):
    if str(module_path) not in sys.path:
        sys.path.insert(0, str(module_path))

from d6_evaluation_metrics import (  # noqa: E402
    StrictLearningAdoptionAuditError,
    audit_learning_adoption_evidence,
    build_learning_adoption_audit_input,
    build_learning_adoption_audit_input_from_episode_files,
    load_learning_adoption_audit_input,
    load_learning_adoption_audit_output,
    load_learning_adoption_episode_evidence,
    validate_learning_adoption_audit_input,
    validate_learning_adoption_audit_output,
)
import d6_evaluation_metrics.strict_learning_adoption_audit as strict_audit  # noqa: E402


def test_strict_output_validator_runs_in_clean_subprocess() -> None:
    pythonpath = os.pathsep.join(
        str(path)
        for path in (
            REPOSITORY_ROOT
            / "research_modules"
            / "d3_assignment_planner"
            / "src",
            REPOSITORY_ROOT
            / "research_modules"
            / "d4_distributed_fallback",
            REPOSITORY_ROOT
            / "research_modules"
            / "d5_terminal_association"
            / "src",
            REPOSITORY_ROOT / "research_modules" / "d6_evaluation_metrics",
        )
    )
    script = """
from d6_evaluation_metrics.strict_learning_adoption_audit import (
    _validate_a3_pairing_inventory_output,
    audit_learning_adoption_evidence,
    build_learning_adoption_audit_input,
    validate_learning_adoption_audit_output,
)

assert callable(_validate_a3_pairing_inventory_output)
request = build_learning_adoption_audit_input(
    a3_pairing_dispositions=(),
)
output = audit_learning_adoption_evidence(request)
validate_learning_adoption_audit_output(output)
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPOSITORY_ROOT,
        env={**os.environ, "PYTHONPATH": pythonpath},
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def _canonical_sha256(value: object) -> str:
    return sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _a2_pair_records(
    *,
    include_candidate_window: bool = True,
) -> tuple[dict[str, object], dict[str, object]]:
    support = _support("d4")
    evidence, context, candidate, r0_window = (
        support._a2_benefit_audit_case()
    )
    module = importlib.import_module(
        "d4_distributed_fallback.region_resource_a2_benefit_audit"
    )
    pair = module.assemble_region_resource_a2_benefit_audit_input(
        safe_adoption_evidence=evidence,
        context=context,
        candidate_window=(
            candidate if include_candidate_window else None
        ),
        same_key_r0_window=r0_window,
    )
    return evidence.to_dict(), pair.to_dict()


@lru_cache(maxsize=None)
def _support(name: str):
    paths = {
        "d3": (
            REPOSITORY_ROOT
            / "research_modules"
            / "d3_assignment_planner"
            / "tests"
            / "test_a1_intervention_selection.py"
        ),
        "d4": (
            REPOSITORY_ROOT
            / "research_modules"
            / "d4_distributed_fallback"
            / "tests"
            / "test_region_resource_safe_adoption.py"
        ),
        "d5": (
            REPOSITORY_ROOT
            / "research_modules"
            / "d5_terminal_association"
            / "tests"
            / "test_active_vision_a3_evidence_assembler.py"
        ),
    }
    module_name = f"_d6_learning_adoption_{name}_fixture_support"
    spec = importlib.util.spec_from_file_location(module_name, paths[name])
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _a1_complete_records() -> list[dict[str, object]]:
    support = _support("d3")
    candidate, _, treatment = support._candidate()
    assert treatment.plan is not None
    selection = support.select_a1_intervention_candidate(
        preregistration=support._registration(),
        seed=1000,
        candidates=(candidate,),
    )
    publication = support._publication(treatment.plan)
    runtime_ack = support._runtime_ack(treatment.plan, publication)
    lifecycle = support.assemble_a1_intervention_lifecycle(
        selection=selection,
        selected_candidate=candidate,
        expected_plan=treatment.plan,
        publication_evidence=publication,
        runtime_ack_evidence=runtime_ack,
        physical_window_evidence=support._physical_windows(
            treatment.plan,
            publication,
            runtime_ack,
            paired=True,
        ),
    )
    return [
        candidate.to_dict(),
        selection.to_dict(),
        publication.to_dict(),
        lifecycle.to_dict(),
    ]


def _a1_rejected_records() -> list[dict[str, object]]:
    support = _support("d3")
    candidate, _, _ = support._candidate(
        predictor=support._NonSelectedEdgePredictor()
    )
    selection = support.select_a1_intervention_candidate(
        preregistration=support._registration(),
        seed=1000,
        candidates=(candidate,),
    )
    assert not candidate.selected_for_paired_evaluation
    assert not selection.selected
    return [candidate.to_dict(), selection.to_dict()]


def _a2_complete_record() -> dict[str, object]:
    case = _a2_case()
    return case["assembler"].assemble(
        preparation=case["preparation"],
        context=case["context"],
        evaluated_at_s=case["evaluated_at_s"],
        d3_successor_plan=case["plan"],
        runtime_ack=case["runtime_ack"],
        owner_ack_delivery=case["owner_delivery"],
        physical_window=case["physical_window"],
    ).to_dict()


def _a2_case() -> dict[str, object]:
    support = _support("d4")
    snapshot = support._snapshot()
    context = support._context(snapshot)
    assembler = support.RegionResourceSafeAdoptionAssembler()
    preparation = assembler.prepare(
        snapshot=snapshot,
        candidate=support._candidate(snapshot),
        context=context,
        formal_decision=support._formal_decision(snapshot),
    )
    assert preparation.available
    applied = preparation.applied_recommendation
    assert applied is not None
    plan = support.RegionResourceD3PlanReference(
        plan_id="successor-plan",
        plan_version=4,
        previous_plan_id=applied.source_plan_id,
        previous_plan_version=applied.source_plan_version,
        owner_node_id=applied.owner_node_id,
        owner_layer=applied.owner_layer,
        epoch=applied.epoch,
        created_at_s=1.6,
        valid_until_s=9.5,
        source_advisory_id=applied.advisory.advisory_id,
        source_advisory_version=applied.advisory_version,
        source_advisory_payload_sha256=applied.advisory_payload_sha256,
        plan_payload_sha256=support._sha("successor-plan-payload"),
        plan_bus_sequence=100,
        accepted_by_main_runtime=True,
        regional_hint_applied=True,
        stale_version_rejected=True,
    )
    assignment_ack_sha256 = support._sha("runtime-assignment-ack")
    runtime_ack = support.RegionResourceRuntimeAckEvidence(
        code=support.RegionResourceRuntimeAckCode.APPLIED.value,
        reason="new execution plan applied",
        runtime_advisory_applied_ack_available=True,
        adoption_kind=(
            support.RegionResourceRuntimeAdoptionKind
            .NEW_EXECUTION_PLAN_APPLIED.value
        ),
        advisory_id=applied.advisory.advisory_id,
        advisory_version=applied.advisory_version,
        source_plan_id=applied.source_plan_id,
        source_plan_version=applied.source_plan_version,
        applied_plan_id=plan.plan_id,
        applied_plan_version=plan.plan_version,
        consumed_at_s=context.consumption_timestamp_s,
        acknowledged_at_s=1.7,
        owner_layer=applied.owner_layer.value,
        owner_node_id=applied.owner_node_id,
        authority_epoch=applied.epoch,
        lease_expires_at_s=applied.lease_expires_at_s,
        source_plan_bus_sequence=plan.plan_bus_sequence,
        advisory_source_plan_bus_sequence=99,
        source_guidance_bus_sequence=101,
        ack_bus_sequence=102,
        assignment_plan_ack_payload_sha256=assignment_ack_sha256,
        advisory_payload_sha256=applied.advisory_payload_sha256,
        source_plan_payload_sha256=plan.plan_payload_sha256,
        source_guidance_payload_sha256=support._sha("guidance-payload"),
    )
    owner_ack = support.RegionResourceOwnerPlanAck(
        message_id="owner-ack-001",
        owner_node_id=applied.owner_node_id,
        owner_layer=applied.owner_layer,
        region_ids=applied.region_ids,
        advisory_id=applied.advisory.advisory_id,
        advisory_version=applied.advisory_version,
        advisory_payload_sha256=applied.advisory_payload_sha256,
        source_plan_id=applied.source_plan_id,
        source_plan_version=applied.source_plan_version,
        applied_plan_id=plan.plan_id,
        applied_plan_version=plan.plan_version,
        applied_plan_payload_sha256=plan.plan_payload_sha256,
        applied_plan_bus_sequence=plan.plan_bus_sequence,
        runtime_assignment_ack_payload_sha256=assignment_ack_sha256,
        runtime_assignment_ack_bus_sequence=runtime_ack.ack_bus_sequence,
        epoch=applied.epoch,
        lease_expires_at_s=applied.lease_expires_at_s,
        partition_generation=context.partition_generation,
        acknowledged_at_s=1.8,
        accepted=True,
    )
    owner_receipt = support._receipt(
        payload=owner_ack.to_transport_payload(),
        source=applied.owner_node_id,
        destination=context.runtime_node_id,
        topic=support.REGION_RESOURCE_OWNER_ACK_TOPIC,
        sequence=200,
        sent_at_s=owner_ack.acknowledged_at_s,
        arrival_at_s=1.82,
    )
    owner_delivery = support.RegionResourceOwnerAckDelivery(
        ack=owner_ack,
        receipt=owner_receipt,
    )
    physical_window = support.RegionResourcePhysicalWindowEvidence(
        window_id="physical-window-001",
        available=True,
        window_start_s=2.05,
        window_end_s=2.2,
        advisory_id=applied.advisory.advisory_id,
        advisory_version=applied.advisory_version,
        advisory_payload_sha256=applied.advisory_payload_sha256,
        applied_plan_id=plan.plan_id,
        applied_plan_version=plan.plan_version,
        runtime_ack_sha256=_canonical_sha256(runtime_ack.to_dict()),
        owner_ack_receipt_id=owner_receipt.receipt_id,
        coalition_commit_sha256=(),
        source_state_payload_sha256=support._sha(
            "physical-source-state"
        ),
        post_state_payload_sha256=support._sha("physical-post-state"),
        physical_execution_observed=True,
        hard_constraint_violation_count=0,
    )
    return {
        "assembler": assembler,
        "context": context,
        "preparation": preparation,
        "plan": plan,
        "runtime_ack": runtime_ack,
        "owner_delivery": owner_delivery,
        "physical_window": physical_window,
        "evaluated_at_s": 2.3,
    }


def _a3_complete_record(
    *,
    comparison_key: str = "nominal-scale5-seed1000-window0",
    seed: int = 1000,
    source_event_log_sha256: str | None = None,
) -> dict[str, object]:
    support = _support("d5")
    trace = _a3_trace(
        comparison_key=comparison_key,
        seed=seed,
        source_event_log_sha256=source_event_log_sha256,
    )
    return support.assemble_active_vision_a3_evidence(
        trace,
        candidate_window=support._candidate_window(trace),
        same_key_r0_window=support._r0_window(trace),
    ).to_dict()


def _a3_zero_detection_complete_record() -> dict[str, object]:
    support = _support("d5")
    trace = _a3_trace()
    frame = support._zero_detection_frame(
        measurement_timestamp=1.15,
        arrival_timestamp=1.16,
    )
    candidate_window = (
        support.assemble_active_vision_a3_physical_observation_window(
            trace,
            arm=support.ActiveVisionA3WindowArm.A3,
            observation_frames=(frame,),
            window_start_timestamp=1.10,
            window_end_timestamp=2.10,
        )
    )
    assert candidate_window is not None
    assert candidate_window.outcome.benefit_outcome_available
    assert candidate_window.outcome.association_locked_count == 0
    assert candidate_window.outcome.association_ambiguous_count == 0
    assert candidate_window.outcome.association_reacquire_count == 1
    assert candidate_window.outcome.coverage_fraction == 0.0
    return support.assemble_active_vision_a3_evidence(
        trace,
        candidate_window=candidate_window,
        same_key_r0_window=support._r0_window(trace),
    ).to_dict()


def _a3_pairing_inventory_case(
    *,
    detailed_unpairable: bool = False,
) -> tuple[
    tuple[dict[str, object], ...],
    tuple[dict[str, object], ...],
]:
    support = _support("d5")
    pairable_trace = _a3_trace()
    pairable = support.attempt_active_vision_a3_pairing(
        pairable_trace,
        candidate_window=support._candidate_window(pairable_trace),
        same_key_r0_windows=(support._r0_window(pairable_trace),),
    )
    assert pairable.pairable
    assert pairable.paired_evidence is not None

    unpairable_trace = _a3_trace(
        comparison_key="nominal-scale5-seed1001-window1",
        seed=1001,
        window_index=1,
        sample_key="episode-002:active-vision:000002:CAM-01",
        source_event_log_sha256=support._digest("7"),
    )
    unpairable = support.attempt_active_vision_a3_pairing(
        unpairable_trace,
        candidate_window=None,
        same_key_r0_windows=(support._r0_window(unpairable_trace),),
        candidate_stage_evidence=(
            support._candidate_stage_evidence(unpairable_trace)
            if detailed_unpairable
            else None
        ),
    )
    assert not unpairable.pairable
    return (
        (pairable.paired_evidence.to_dict(),),
        (pairable.to_dict(), unpairable.to_dict()),
    )


def _legacy_a3_disposition(
    disposition: dict[str, object],
) -> dict[str, object]:
    support = _support("d5")
    payload = deepcopy(disposition)
    payload["schema_version"] = (
        support.ACTIVE_VISION_A3_PAIRING_DISPOSITION_LEGACY_SCHEMA_VERSION
    )
    payload.pop("candidate_stage_reason_codes", None)
    payload.pop("candidate_stage_evidence", None)
    payload.pop("content_sha256")
    payload["content_sha256"] = _canonical_sha256(payload)
    return payload


def _a3_trace(
    *,
    decision=None,
    runtime_ack=...,
    camera_feedback=...,
    ack_kind: str | None = None,
    feedback_kind: str | None = None,
    synthetic_fixture: bool = False,
    online_truth_use_count: int = 0,
    command_issued: bool = True,
    comparison_key: str = "nominal-scale5-seed1000-window0",
    seed: int = 1000,
    window_index: int = 0,
    sample_key: str = "episode-001:active-vision:000001:CAM-01",
    source_event_log_sha256: str | None = None,
):
    support = _support("d5")
    assembler = importlib.import_module(
        "d5_terminal_association.active_vision_a3_evidence_assembler"
    )
    selected = decision or support._decision()
    issued = selected.effective_action.issued_timestamp
    ack = (
        support._ack(sample_key=sample_key, issued=issued)
        if runtime_ack is ...
        else runtime_ack
    )
    feedback = (
        support._feedback(
            timestamp=issued + 0.05,
            yaw_deg=(
                12.0
                if selected.effective_mode
                is support.ActiveVisionRuntimeMode.ASSIST
                else 11.0
            ),
            pitch_deg=(
                -6.0
                if selected.effective_mode
                is support.ActiveVisionRuntimeMode.ASSIST
                else -5.0
            ),
            fov_mode=selected.effective_action.fov_mode,
        )
        if camera_feedback is ...
        else camera_feedback
    )
    ack_kind = ack_kind or support.RUNTIME_OBSERVED_EVIDENCE_KIND
    feedback_kind = (
        feedback_kind or support.RUNTIME_OBSERVED_EVIDENCE_KIND
    )
    pose_lineage = None
    if not command_issued:
        ack = None
        feedback = None
        ack_kind = support.UNAVAILABLE_EVIDENCE_KIND
        feedback_kind = support.UNAVAILABLE_EVIDENCE_KIND
    elif feedback is not None:
        state = feedback.camera_state
        horizontal_fov = (
            state.wide_horizontal_fov_deg
            if state.current_fov_mode is support.ActiveVisionFovMode.WIDE
            else state.zoom_horizontal_fov_deg
        )
        pose_lineage = assembler.ActiveVisionA3CameraPoseLineage(
            camera_id=state.camera_id,
            resource_id=state.resource_id,
            state_timestamp=state.state_timestamp,
            yaw_deg=state.yaw_deg,
            pitch_deg=state.pitch_deg,
            horizontal_fov_deg=horizontal_fov,
            fov_mode=state.current_fov_mode.value,
            last_plan_version=selected.plan_version,
            last_coalition_version=selected.coalition_version,
            last_communication_version=selected.communication_version,
            evidence_kind=feedback_kind,
            source_sequence=12,
        )
    return assembler.ActiveVisionA3AdoptionTrace(
        comparison_key=comparison_key,
        scenario_id="nominal",
        scale=5,
        seed=seed,
        window_index=window_index,
        sample_key=sample_key,
        camera_id="CAM-01",
        resource_id="INT-01",
        pairing_context_sha256=support._digest("9"),
        source_event_log_sha256=(
            source_event_log_sha256 or support._digest("8")
        ),
        policy_evaluated=True,
        policy_evaluated_timestamp=issued - 0.01,
        model_fingerprint="active-vision-model-v1",
        bundle_manifest_sha256=support._digest("a"),
        bundle_weights_sha256=support._digest("b"),
        implementation_sha256=support._digest("c"),
        source_git_commit="d" * 40,
        decision=selected,
        pre_command_camera_state=support._camera_state(
            timestamp=issued - 0.05,
            yaw_deg=10.0,
            pitch_deg=-5.0,
            fov_mode=support.ActiveVisionFovMode.WIDE,
        ),
        issued_command_payload=(
            support._command_payload(
                selected.effective_action,
                requested_mode=selected.requested_mode.value,
                effective_mode=selected.effective_mode.value,
            )
            if command_issued
            else None
        ),
        runtime_ack=ack,
        camera_feedback=feedback,
        camera_pose_lineage=pose_lineage,
        runtime_ack_evidence_kind=ack_kind,
        camera_feedback_evidence_kind=feedback_kind,
        synthetic_fixture=synthetic_fixture,
        pose_tolerance_deg=0.25,
        online_truth_use_count=online_truth_use_count,
    )


def _a2_rejected_record() -> dict[str, object]:
    support = _support("d4")
    snapshot = support._snapshot()
    context = support._context(snapshot)
    assembler = support.RegionResourceSafeAdoptionAssembler()
    preparation = assembler.prepare(
        snapshot=snapshot,
        candidate=support._candidate(
            snapshot,
            source=support.RecommendationSource.RULE,
            fallback_reason="deterministic_rule_fallback",
        ),
        context=context,
        formal_decision=support._formal_decision(snapshot),
    )
    assert not preparation.available
    return assembler.assemble(
        preparation=preparation,
        context=context,
        evaluated_at_s=2.3,
    ).to_dict()


def _a2_post_projection_rejected_record() -> dict[str, object]:
    case = _a2_case()
    stale_plan = replace(
        case["plan"],
        plan_version=case["plan"].previous_plan_version,
    )
    evidence = case["assembler"].assemble(
        preparation=case["preparation"],
        context=case["context"],
        evaluated_at_s=case["evaluated_at_s"],
        d3_successor_plan=stale_plan,
    )
    assert evidence.stage.value == "safe_adoption_rejected"
    assert evidence.reason_codes == (
        "successor_plan_version_not_strictly_new",
    )
    assert evidence.d3_successor_plan is None
    return evidence.to_dict()


def _a2_incomplete_record() -> dict[str, object]:
    case = _a2_case()
    return case["assembler"].assemble(
        preparation=case["preparation"],
        context=case["context"],
        evaluated_at_s=case["evaluated_at_s"],
        d3_successor_plan=None,
    ).to_dict()


def _a2_missing_runtime_ack_record() -> dict[str, object]:
    case = _a2_case()
    return case["assembler"].assemble(
        preparation=case["preparation"],
        context=case["context"],
        evaluated_at_s=case["evaluated_at_s"],
        d3_successor_plan=case["plan"],
        runtime_ack=None,
    ).to_dict()


def _a2_missing_physical_window_record() -> dict[str, object]:
    case = _a2_case()
    return case["assembler"].assemble(
        preparation=case["preparation"],
        context=case["context"],
        evaluated_at_s=case["evaluated_at_s"],
        d3_successor_plan=case["plan"],
        runtime_ack=case["runtime_ack"],
        owner_ack_delivery=case["owner_delivery"],
        physical_window=None,
    ).to_dict()


@pytest.mark.parametrize("layout", ("pythonpath", "repository_root"))
def test_public_validators_resolve_in_both_supported_layouts(
    tmp_path: Path,
    layout: str,
) -> None:
    safe, pair = _a2_pair_records()
    request_path = tmp_path / "audit-input.json"
    request_path.write_text(
        json.dumps(
            build_learning_adoption_audit_input(
                a1=_a1_complete_records(),
                a2=(safe, pair),
                a3=(_a3_complete_record(),),
            ),
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    if layout == "pythonpath":
        import_statement = (
            "from d6_evaluation_metrics.strict_learning_adoption_audit "
            "import audit_learning_adoption_evidence"
        )
        expected_modules = (
            "d3_assignment_planner.a1_intervention_selection",
            "d4_distributed_fallback.region_resource_safe_adoption",
            (
                "d4_distributed_fallback."
                "region_resource_a2_benefit_audit"
            ),
            "d5_terminal_association.active_vision_a3_evidence_assembler",
        )
        block_top_level = ""
    else:
        import_statement = (
            "from research_modules.d6_evaluation_metrics."
            "d6_evaluation_metrics.strict_learning_adoption_audit "
            "import audit_learning_adoption_evidence"
        )
        expected_modules = (
            "research_modules.d3_assignment_planner.src."
            "d3_assignment_planner.a1_intervention_selection",
            "research_modules.d4_distributed_fallback."
            "d4_distributed_fallback.region_resource_safe_adoption",
            "research_modules.d4_distributed_fallback."
            "d4_distributed_fallback.region_resource_a2_benefit_audit",
            "research_modules.d5_terminal_association.src."
            "d5_terminal_association.active_vision_a3_evidence_assembler",
        )
        block_top_level = """
import importlib.abc
class _BlockTopLevelModuleLayout(importlib.abc.MetaPathFinder):
    _roots = {
        "d3_assignment_planner",
        "d4_distributed_fallback",
        "d5_terminal_association",
    }
    def find_spec(self, fullname, path=None, target=None):
        root = fullname.split(".", 1)[0]
        if root in self._roots:
            raise ModuleNotFoundError(
                f"No module named {root!r}",
                name=root,
            )
        return None
sys.meta_path.insert(0, _BlockTopLevelModuleLayout())
"""
    script = f"""
import json
from pathlib import Path
import sys
{block_top_level}
{import_statement}
request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
result = audit_learning_adoption_evidence(request)
print(json.dumps({{
    "result": result,
    "resolved_modules": [
        name for name in {expected_modules!r} if name in sys.modules
    ],
}}, sort_keys=True))
"""
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    if layout == "pythonpath":
        env["PYTHONPATH"] = os.pathsep.join(
            str(path)
            for path in (
                REPOSITORY_ROOT
                / "research_modules"
                / "d6_evaluation_metrics",
                REPOSITORY_ROOT
                / "research_modules"
                / "d3_assignment_planner"
                / "src",
                REPOSITORY_ROOT
                / "research_modules"
                / "d4_distributed_fallback",
                REPOSITORY_ROOT
                / "research_modules"
                / "d5_terminal_association"
                / "src",
            )
        )
    completed = subprocess.run(
        [sys.executable, "-c", script, str(request_path)],
        cwd=REPOSITORY_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)
    result = payload["result"]

    assert payload["resolved_modules"] == list(expected_modules)
    for variant in ("A1", "A2", "A3"):
        assert result["variants"][variant]["validated_record_count"] > 0
        assert not any(
            "public_validator_unavailable" in code
            or "public_contract_unavailable" in code
            or "public_advisory_loader_unavailable" in code
            or "public_runtime_ack_contract_unavailable" in code
            or "public_communication_contract_unavailable" in code
            for code in result["variants"][variant]["blocker_codes"]
        )


def test_public_module_internal_dependency_error_is_not_misclassified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_import = strict_audit.importlib.import_module

    def import_with_broken_dependency(name: str):
        if name == "d3_assignment_planner.a1_intervention_selection":
            raise ModuleNotFoundError(
                "No module named 'contract_internal_dependency'",
                name="contract_internal_dependency",
            )
        return real_import(name)

    monkeypatch.setattr(
        strict_audit.importlib,
        "import_module",
        import_with_broken_dependency,
    )

    with pytest.raises(
        ModuleNotFoundError,
        match="contract_internal_dependency",
    ):
        audit_learning_adoption_evidence(
            build_learning_adoption_audit_input(
                a1=(_a1_complete_records()[0],)
            )
        )


def test_a3_positive_runtime_fixture_produces_complete_counts() -> None:
    request = build_learning_adoption_audit_input(
        a3=(_a3_complete_record(),)
    )

    result = audit_learning_adoption_evidence(request)
    a3 = result["variants"]["A3"]

    assert a3["availability"] == "available"
    assert a3["highest_evidence_stage"] == "auditable_benefit_input"
    assert a3["actual_adoption_count"]["value"] == 1
    assert a3["physical_window_count"]["value"] == 1
    assert a3["same_key_r0_pair_count"]["value"] == 1
    assert a3["benefit_auditable_count"]["value"] == 1
    assert a3["auditable_benefit_count"]["value"] == 1
    assert all(value is False for value in a3["permissions"].values())


def test_a3_zero_detection_is_auditable_zero_coverage_not_positive_state() -> None:
    request = build_learning_adoption_audit_input(
        a3=(_a3_zero_detection_complete_record(),)
    )

    result = audit_learning_adoption_evidence(request)
    a3 = result["variants"]["A3"]
    inventory = a3["observation_outcome_inventory"]

    assert a3["availability"] == "available"
    assert a3["benefit_auditable_count"]["value"] == 1
    assert a3["positive_benefit_claimed"] is False
    assert a3["non_degradation_claimed"] is False
    assert inventory["availability"] == "available"
    assert inventory["candidate_window_count"] == 1
    assert inventory["observation_frame_count"] == 1
    assert inventory["tracklets_observed_frame_count"] == 0
    assert inventory["processed_zero_detection_frame_count"] == 1
    assert inventory["association_outcome_available"] is True
    assert inventory["association_evaluable_frame_count"] == 1
    assert inventory["association_locked_count"] == 0
    assert inventory["association_ambiguous_count"] == 0
    assert inventory["association_hold_count"] == 0
    assert inventory["association_reacquire_count"] == 1
    assert inventory["coverage_outcome_available"] is True
    assert inventory["assigned_reference_count"] == 1
    assert inventory["visible_assigned_reference_count"] == 0
    assert inventory["coverage_fraction"] == 0.0
    assert inventory["zero_detection_locked_or_ambiguous_count"] == 0
    assert all(value is False for value in a3["permissions"].values())
    assert all(value is False for value in result["permissions"].values())


@pytest.mark.parametrize(
    ("field", "value", "error_code"),
    (
        (
            "association_locked_count",
            1,
            "audit_output_a3_association_count_conservation_invalid",
        ),
        (
            "zero_detection_locked_or_ambiguous_count",
            1,
            "audit_output_a3_zero_detection_positive_state_forbidden",
        ),
        (
            "coverage_fraction",
            1.0,
            "audit_output_a3_coverage_fraction_invalid",
        ),
    ),
)
def test_a3_zero_detection_output_tamper_is_rejected(
    field: str,
    value: object,
    error_code: str,
) -> None:
    result = audit_learning_adoption_evidence(
        build_learning_adoption_audit_input(
            a3=(_a3_zero_detection_complete_record(),)
        )
    )
    tampered = deepcopy(result)
    tampered["variants"]["A3"]["observation_outcome_inventory"][
        field
    ] = value
    tampered.pop("content_sha256")
    tampered["content_sha256"] = _canonical_sha256(tampered)

    with pytest.raises(StrictLearningAdoptionAuditError) as exc:
        validate_learning_adoption_audit_output(tampered)

    assert exc.value.code == error_code


def test_a3_zero_detection_rebalanced_locked_tamper_is_rejected() -> None:
    result = audit_learning_adoption_evidence(
        build_learning_adoption_audit_input(
            a3=(_a3_zero_detection_complete_record(),)
        )
    )
    tampered = deepcopy(result)
    inventory = tampered["variants"]["A3"][
        "observation_outcome_inventory"
    ]
    inventory["association_locked_count"] = 1
    inventory["association_reacquire_count"] = 0
    tampered.pop("content_sha256")
    tampered["content_sha256"] = _canonical_sha256(tampered)

    with pytest.raises(StrictLearningAdoptionAuditError) as exc:
        validate_learning_adoption_audit_output(tampered)

    assert (
        exc.value.code
        == "audit_output_a3_zero_detection_positive_state_forbidden"
    )


def test_a3_disposition_inventory_reports_full_denominator() -> None:
    records, dispositions = _a3_pairing_inventory_case()
    request = build_learning_adoption_audit_input(
        a3=records,
        a3_pairing_dispositions=dispositions,
    )

    result = audit_learning_adoption_evidence(request)
    a3 = result["variants"]["A3"]
    inventory = a3["pairing_disposition_inventory"]

    assert request["schema_version"] == (
        strict_audit.LEARNING_ADOPTION_AUDIT_INPUT_SCHEMA_VERSION_V2
    )
    assert inventory["availability"] == "available"
    assert inventory["candidate_count"]["value"] == 2
    assert inventory["pairable_count"]["value"] == 1
    assert inventory["unpairable_count"]["value"] == 1
    assert inventory["pairing_coverage"]["value"] == pytest.approx(0.5)
    assert inventory["inventory_completeness"]["value"] is True
    assert inventory["paired_evidence_completeness"]["value"] is False
    assert inventory["complete_model_evidence_claimed"] is False
    assert inventory["reason_code_counts"]["value"]["pairable"] == 1
    assert (
        inventory["reason_code_counts"]["value"][
            "candidate_physical_window_missing"
        ]
        == 1
    )
    assert a3["actual_adoption_count"]["value"] is None
    assert a3["same_key_r0_pair_count"]["value"] is None
    assert a3["benefit_auditable_count"]["value"] is None
    assert (
        "a3_pairing_inventory_contains_unpairable"
        in a3["blocker_codes"]
    )
    assert all(value is False for value in a3["permissions"].values())
    assert all(value is False for value in result["permissions"].values())


def test_a3_candidate_stage_details_are_hierarchical_and_fail_closed() -> None:
    records, dispositions = _a3_pairing_inventory_case(
        detailed_unpairable=True
    )
    result = audit_learning_adoption_evidence(
        build_learning_adoption_audit_input(
            a3=records,
            a3_pairing_dispositions=dispositions,
        )
    )
    a3 = result["variants"]["A3"]
    inventory = a3["pairing_disposition_inventory"]

    assert inventory["candidate_count"]["value"] == 2
    assert inventory["candidate_stage_evidence_count"]["value"] == 1
    assert (
        inventory["candidate_stage_evidence_missing_count"]["value"] == 1
    )
    assert inventory["detail_reason_record_count"]["value"] == 1
    assert inventory["detail_reasonless_record_count"]["value"] == 1
    assert inventory["detail_reason_assignment_count"]["value"] == 2
    details = inventory["detail_reason_code_counts"]["value"]
    assert details["candidate_anonymous_observation_missing"] == 1
    assert details["candidate_physical_window_confirmed_missing"] == 1
    hierarchy = inventory["top_level_detail_reason_counts"]["value"]
    missing_row = hierarchy["candidate_physical_window_missing"]
    assert missing_row["record_count"] == 1
    assert missing_row["records_with_detail_reason_count"] == 1
    assert missing_row["records_without_detail_reason_count"] == 0
    assert missing_row["detail_reason_assignment_count"] == 2
    assert (
        inventory["physical_window_missing_detail_scope_count"]["value"]
        == 1
    )
    assert (
        inventory[
            "physical_window_missing_detail_evidenced_count"
        ]["value"]
        == 1
    )
    assert (
        inventory[
            "physical_window_missing_detail_unresolved_count"
        ]["value"]
        == 0
    )
    assert (
        inventory[
            "physical_window_missing_detail_completeness"
        ]["value"]
        is True
    )

    assert inventory["complete_model_evidence_claimed"] is False
    assert inventory["paired_evidence_completeness"]["value"] is False
    assert a3["actual_adoption_count"]["value"] is None
    assert a3["physical_window_count"]["value"] is None
    assert a3["same_key_r0_pair_count"]["value"] is None
    assert a3["benefit_auditable_count"]["value"] is None
    assert all(value is False for value in a3["permissions"].values())


def test_a3_legacy_dispositions_preserve_top_level_and_leave_detail_open() -> None:
    records, dispositions = _a3_pairing_inventory_case(
        detailed_unpairable=True
    )
    legacy = tuple(_legacy_a3_disposition(item) for item in dispositions)

    a3 = audit_learning_adoption_evidence(
        build_learning_adoption_audit_input(
            a3=records,
            a3_pairing_dispositions=legacy,
        )
    )["variants"]["A3"]
    inventory = a3["pairing_disposition_inventory"]

    assert inventory["availability"] == "available"
    assert inventory["candidate_count"]["value"] == 2
    assert (
        inventory["top_level_reason_code_counts"]["value"][
            "candidate_physical_window_missing"
        ]
        == 1
    )
    assert inventory["candidate_stage_evidence_count"]["value"] == 0
    assert inventory["detail_reason_record_count"]["value"] == 0
    assert (
        inventory[
            "physical_window_missing_detail_unresolved_count"
        ]["value"]
        == 1
    )
    assert (
        inventory[
            "physical_window_missing_detail_completeness"
        ]["value"]
        is False
    )
    assert a3["actual_adoption_count"]["value"] is None
    assert all(value is False for value in a3["permissions"].values())


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    (
        (
            "unknown",
            "pairing_disposition_stage_reason_unsupported",
        ),
        (
            "duplicate",
            "pairing_disposition_stage_reasons_invalid",
        ),
        (
            "evidence_mismatch",
            "pairing_disposition_stage_reason_mismatch",
        ),
    ),
)
def test_a3_candidate_stage_detail_contract_violations_fail_closed(
    mutation: str,
    expected_code: str,
) -> None:
    records, dispositions = _a3_pairing_inventory_case(
        detailed_unpairable=True
    )
    tampered = deepcopy(dispositions[1])
    stage_reasons = tampered["candidate_stage_reason_codes"]
    assert isinstance(stage_reasons, list) and len(stage_reasons) == 2
    if mutation == "unknown":
        stage_reasons.append("candidate_unknown_stage")
    elif mutation == "duplicate":
        stage_reasons.append(stage_reasons[0])
    else:
        stage_reasons.pop()
    tampered.pop("content_sha256")
    tampered["content_sha256"] = _canonical_sha256(tampered)

    a3 = audit_learning_adoption_evidence(
        build_learning_adoption_audit_input(
            a3=records,
            a3_pairing_dispositions=(dispositions[0], tampered),
        )
    )["variants"]["A3"]

    assert (
        a3["pairing_disposition_inventory"]["availability"]
        == "unavailable"
    )
    assert any(
        code.startswith(
            "a3_pairing_disposition_contract_validation_failed."
            f"{expected_code}"
        )
        for code in a3["blocker_codes"]
    )
    assert a3["actual_adoption_count"]["value"] is None
    assert all(value is False for value in a3["permissions"].values())


def test_strict_audit_input_and_output_round_trip(
    tmp_path: Path,
) -> None:
    records, dispositions = _a3_pairing_inventory_case(
        detailed_unpairable=True
    )
    request = build_learning_adoption_audit_input(
        a3=records,
        a3_pairing_dispositions=dispositions,
    )
    input_path = tmp_path / "strict-audit-input.json"
    input_path.write_text(
        json.dumps(request, sort_keys=True),
        encoding="utf-8",
    )

    reloaded_input = load_learning_adoption_audit_input(input_path)
    result = audit_learning_adoption_evidence(reloaded_input)
    output_path = tmp_path / "strict-audit-output.json"
    output_path.write_text(
        json.dumps(result, sort_keys=True),
        encoding="utf-8",
    )

    assert reloaded_input == request
    assert validate_learning_adoption_audit_output(result) == result
    assert load_learning_adoption_audit_output(output_path) == result


def test_strict_audit_output_detail_count_tamper_fails_closed() -> None:
    records, dispositions = _a3_pairing_inventory_case(
        detailed_unpairable=True
    )
    result = audit_learning_adoption_evidence(
        build_learning_adoption_audit_input(
            a3=records,
            a3_pairing_dispositions=dispositions,
        )
    )
    tampered = deepcopy(result)
    inventory = tampered["variants"]["A3"][
        "pairing_disposition_inventory"
    ]
    inventory["detail_reason_assignment_count"]["value"] += 1
    tampered.pop("content_sha256")
    tampered["content_sha256"] = _canonical_sha256(tampered)

    with pytest.raises(
        StrictLearningAdoptionAuditError,
        match=(
            "audit_output_a3_pairing_detail_assignment_count_"
            "conservation_invalid"
        ),
    ):
        validate_learning_adoption_audit_output(tampered)


def test_a3_all_pairable_disposition_inventory_preserves_paired_metrics() -> None:
    records, dispositions = _a3_pairing_inventory_case()
    a3 = audit_learning_adoption_evidence(
        build_learning_adoption_audit_input(
            a3=records,
            a3_pairing_dispositions=(dispositions[0],),
        )
    )["variants"]["A3"]
    inventory = a3["pairing_disposition_inventory"]

    assert inventory["candidate_count"]["value"] == 1
    assert inventory["pairable_count"]["value"] == 1
    assert inventory["unpairable_count"]["value"] == 0
    assert inventory["pairing_coverage"]["value"] == pytest.approx(1.0)
    assert inventory["paired_evidence_completeness"]["value"] is True
    assert inventory["complete_model_evidence_claimed"] is False
    assert a3["availability"] == "available"
    assert a3["same_key_r0_pair_count"]["value"] == 1
    assert a3["benefit_auditable_count"]["value"] == 1
    assert all(value is False for value in a3["permissions"].values())


def test_a3_v1_input_marks_disposition_inventory_unavailable() -> None:
    request = build_learning_adoption_audit_input(
        a3=(_a3_complete_record(),)
    )

    result = audit_learning_adoption_evidence(request)
    inventory = result["variants"]["A3"][
        "pairing_disposition_inventory"
    ]

    assert request["schema_version"] == (
        strict_audit.LEARNING_ADOPTION_AUDIT_INPUT_SCHEMA_VERSION
    )
    assert result["schema_version"] == (
        strict_audit.LEARNING_ADOPTION_AUDIT_SCHEMA_VERSION
    )
    assert inventory["declared"] is False
    assert inventory["availability"] == "unavailable"
    assert inventory["candidate_count"]["value"] is None
    assert (
        "a3_pairing_disposition_inventory_not_declared_v1"
        in inventory["inventory_completeness"]["reason_codes"]
    )


def test_a3_v2_missing_dispositions_fail_closed() -> None:
    request = build_learning_adoption_audit_input(
        a3=(_a3_complete_record(),),
        a3_pairing_dispositions=(),
    )

    a3 = audit_learning_adoption_evidence(request)["variants"]["A3"]
    inventory = a3["pairing_disposition_inventory"]

    assert inventory["declared"] is True
    assert inventory["availability"] == "unavailable"
    assert inventory["inventory_completeness"]["value"] is None
    assert (
        "a3_pairing_disposition_top_level_evidence_unmatched"
        in a3["blocker_codes"]
    )
    assert a3["actual_adoption_count"]["value"] is None


def test_a3_disposition_duplicate_trace_fails_closed() -> None:
    records, dispositions = _a3_pairing_inventory_case()
    duplicated = (*dispositions, deepcopy(dispositions[0]))

    a3 = audit_learning_adoption_evidence(
        build_learning_adoption_audit_input(
            a3=records,
            a3_pairing_dispositions=duplicated,
        )
    )["variants"]["A3"]

    assert (
        "a3_pairing_disposition_duplicate_adoption_trace"
        in a3["blocker_codes"]
    )
    assert (
        a3["pairing_disposition_inventory"]["availability"]
        == "unavailable"
    )
    assert a3["benefit_auditable_count"]["value"] is None


def test_a3_disposition_hash_tamper_fails_closed() -> None:
    records, dispositions = _a3_pairing_inventory_case()
    tampered = deepcopy(dispositions[0])
    tampered["content_sha256"] = "f" * 64

    a3 = audit_learning_adoption_evidence(
        build_learning_adoption_audit_input(
            a3=records,
            a3_pairing_dispositions=(tampered, dispositions[1]),
        )
    )["variants"]["A3"]

    assert any(
        code.startswith(
            "a3_pairing_disposition_contract_validation_failed."
            "pairing_disposition_hash_mismatch"
        )
        for code in a3["blocker_codes"]
    )
    assert a3["actual_adoption_count"]["value"] is None
    assert all(value is False for value in a3["permissions"].values())


def test_a3_disposition_field_tamper_fails_closed() -> None:
    records, dispositions = _a3_pairing_inventory_case()
    tampered = deepcopy(dispositions[0])
    tampered["assignment_authority"] = True
    body = dict(tampered)
    body.pop("content_sha256")
    tampered["content_sha256"] = _canonical_sha256(body)

    a3 = audit_learning_adoption_evidence(
        build_learning_adoption_audit_input(
            a3=records,
            a3_pairing_dispositions=(tampered, dispositions[1]),
        )
    )["variants"]["A3"]

    assert any(
        code.startswith(
            "a3_pairing_disposition_contract_validation_failed."
        )
        for code in a3["blocker_codes"]
    )
    assert (
        a3["pairing_disposition_inventory"]["availability"]
        == "unavailable"
    )
    assert all(value is False for value in a3["permissions"].values())


def test_a3_pairable_disposition_must_match_top_level_evidence() -> None:
    _, dispositions = _a3_pairing_inventory_case()
    mismatched_top_level = _a3_complete_record(
        comparison_key="nominal-scale5-seed1002-window0",
        seed=1002,
        source_event_log_sha256=_canonical_sha256(
            {"event_log": "candidate-seed-1002"}
        ),
    )

    a3 = audit_learning_adoption_evidence(
        build_learning_adoption_audit_input(
            a3=(mismatched_top_level,),
            a3_pairing_dispositions=(dispositions[0],),
        )
    )["variants"]["A3"]

    assert (
        "a3_pairing_disposition_pairable_evidence_missing"
        in a3["blocker_codes"]
    )
    assert (
        "a3_pairing_disposition_top_level_evidence_unmatched"
        in a3["blocker_codes"]
    )
    assert a3["same_key_r0_pair_count"]["value"] is None


def test_a3_disposition_reason_counts_conserve_candidate_total() -> None:
    records, dispositions = _a3_pairing_inventory_case()
    inventory = audit_learning_adoption_evidence(
        build_learning_adoption_audit_input(
            a3=records,
            a3_pairing_dispositions=dispositions,
        )
    )["variants"]["A3"]["pairing_disposition_inventory"]

    candidate_count = inventory["candidate_count"]["value"]
    pairable_count = inventory["pairable_count"]["value"]
    unpairable_count = inventory["unpairable_count"]["value"]
    reason_total = sum(inventory["reason_code_counts"]["value"].values())

    assert candidate_count == pairable_count + unpairable_count
    assert candidate_count == reason_total


def test_a3_same_episode_windows_share_one_event_log_identity() -> None:
    support = _support("d5")
    shared_log = _canonical_sha256(
        {"episode_id": "episode-001", "stream": "active-vision"}
    )
    first_trace = _a3_trace(source_event_log_sha256=shared_log)
    second_trace = _a3_trace(
        comparison_key="nominal-scale5-seed1000-window1",
        window_index=1,
        sample_key="episode-001:active-vision:000002:CAM-01",
        source_event_log_sha256=shared_log,
    )
    records = (
        support.assemble_active_vision_a3_evidence(
            first_trace,
            candidate_window=support._candidate_window(first_trace),
            same_key_r0_window=None,
        ).to_dict(),
        support.assemble_active_vision_a3_evidence(
            second_trace,
            candidate_window=support._candidate_window(second_trace),
            same_key_r0_window=None,
        ).to_dict(),
    )

    a3 = audit_learning_adoption_evidence(
        build_learning_adoption_audit_input(a3=records)
    )["variants"]["A3"]

    assert a3["actual_adoption_count"]["value"] == 2
    assert not any(
        code.startswith("a3_event_log_episode_binding_mismatch")
        for code in a3["blocker_codes"]
    )


def test_a1_positive_module_fixture_stops_at_serialized_claim_boundary() -> None:
    request = build_learning_adoption_audit_input(
        a1=_a1_complete_records()
    )

    result = audit_learning_adoption_evidence(request)
    a1 = result["variants"]["A1"]

    assert a1["validated_record_count"] == 4
    assert a1["highest_evidence_stage"] == "r0_pair_claim_validated"
    assert a1["actual_adoption_count"]["value"] is None
    assert "a1_runtime_provenance_not_serialized" in a1["blocker_codes"]
    assert "a1_physical_window_payload_not_serialized" in a1["blocker_codes"]
    assert "a1_same_key_r0_identity_not_serialized" in a1["blocker_codes"]


def test_a2_positive_module_fixture_exposes_only_proved_counts() -> None:
    request = build_learning_adoption_audit_input(
        a2=(_a2_complete_record(),)
    )

    result = audit_learning_adoption_evidence(request)
    a2 = result["variants"]["A2"]

    assert a2["availability"] == "unavailable"
    assert a2["validated_record_count"] == 1
    assert a2["highest_evidence_stage"] == "physical_window_available"
    assert a2["actual_adoption_count"]["value"] == 1
    assert a2["physical_window_count"]["value"] == 1
    assert a2["same_key_r0_pair_count"]["value"] is None
    assert a2["auditable_benefit_count"]["value"] is None
    assert "a2_same_key_r0_contract_unavailable" in a2["blocker_codes"]


def test_a2_public_pair_wrapper_exposes_four_audit_levels() -> None:
    safe, pair = _a2_pair_records()
    result = audit_learning_adoption_evidence(
        build_learning_adoption_audit_input(a2=(safe, pair))
    )

    a2 = result["variants"]["A2"]
    assert a2["availability"] == "available"
    assert a2["validated_record_count"] == 2
    assert a2["highest_evidence_stage"] == "auditable_benefit_input"
    assert a2["actual_adoption_count"]["value"] == 1
    assert a2["physical_window_count"]["value"] == 1
    assert a2["same_key_r0_pair_count"]["value"] == 1
    assert a2["benefit_auditable_count"]["value"] == 1
    assert a2["auditable_benefit_count"]["value"] == 1
    assert a2["benefit_audit_status"] == "audit_input_available"
    assert a2["positive_benefit_claimed"] is False
    assert a2["non_degradation_claimed"] is False
    assert all(value is False for value in a2["permissions"].values())


def test_a2_pair_missing_candidate_window_preserves_only_adoption() -> None:
    safe, pair = _a2_pair_records(include_candidate_window=False)
    result = audit_learning_adoption_evidence(
        build_learning_adoption_audit_input(a2=(safe, pair))
    )

    a2 = result["variants"]["A2"]
    assert a2["actual_adoption_count"]["value"] == 1
    assert a2["physical_window_count"]["value"] is None
    assert a2["same_key_r0_pair_count"]["value"] is None
    assert a2["benefit_auditable_count"]["value"] is None
    assert (
        "a2_candidate_physical_window_incomplete"
        in a2["blocker_codes"]
    )


def test_a2_pair_identity_and_summary_are_independently_recomputed() -> None:
    safe, pair = _a2_pair_records()
    identity_mismatch = deepcopy(pair)
    identity_mismatch["same_key_r0_window"][
        "paired_exogenous_config_sha256"
    ] = "f" * 64
    r0_body = dict(identity_mismatch["same_key_r0_window"])
    r0_body.pop("content_sha256")
    identity_mismatch["same_key_r0_window"]["content_sha256"] = (
        _canonical_sha256(r0_body)
    )

    summary_tamper = deepcopy(pair)
    summary_tamper["d6_benefit_audit_eligible"] = False
    summary_tamper["permissions"][
        "d6_benefit_audit_input_allowed"
    ] = False
    summary_body = dict(summary_tamper)
    summary_body.pop("content_sha256")
    summary_tamper["content_sha256"] = _canonical_sha256(summary_body)

    identity_result = audit_learning_adoption_evidence(
        build_learning_adoption_audit_input(
            a2=(safe, identity_mismatch)
        )
    )["variants"]["A2"]
    summary_result = audit_learning_adoption_evidence(
        build_learning_adoption_audit_input(a2=(safe, summary_tamper))
    )["variants"]["A2"]

    assert any(
        "a2_pair_public_validation_failed" in code
        for code in identity_result["blocker_codes"]
    )
    assert any(
        "a2_pair_public_validation_failed" in code
        for code in summary_result["blocker_codes"]
    )
    assert identity_result["actual_adoption_count"]["value"] is None
    assert summary_result["actual_adoption_count"]["value"] is None


def test_a2_pair_rejects_reused_r0() -> None:
    safe, valid_pair = _a2_pair_records()
    reused_result = audit_learning_adoption_evidence(
        build_learning_adoption_audit_input(
            a2=(safe, valid_pair, valid_pair)
        )
    )["variants"]["A2"]

    assert "a2_r0_multi_pair_reuse" in reused_result["blocker_codes"]
    assert reused_result["same_key_r0_pair_count"]["value"] is None


def test_a1_explicit_rejection_is_audited_zero_not_missing_evidence() -> None:
    result = audit_learning_adoption_evidence(
        build_learning_adoption_audit_input(a1=_a1_rejected_records())
    )
    a1 = result["variants"]["A1"]

    assert a1["actual_adoption_count"] == {
        "availability": "available",
        "value": 0,
        "reason_codes": [],
    }
    assert a1["physical_window_count"]["value"] is None
    assert "a1_lifecycle_evidence_missing" not in a1["blocker_codes"]
    assert "a1_actual_adoption_absent" in a1["blocker_codes"]


def test_a1_selected_candidate_without_lifecycle_remains_unavailable() -> None:
    result = audit_learning_adoption_evidence(
        build_learning_adoption_audit_input(a1=_a1_complete_records()[:2])
    )
    a1 = result["variants"]["A1"]

    assert a1["actual_adoption_count"]["value"] is None
    assert "a1_lifecycle_evidence_missing" in a1["blocker_codes"]


def test_a1_nested_digest_tamper_fails_closed() -> None:
    records = _a1_complete_records()
    records[0]["content_sha256"] = "f" * 64

    result = audit_learning_adoption_evidence(
        build_learning_adoption_audit_input(a1=records)
    )
    a1 = result["variants"]["A1"]

    assert a1["actual_adoption_count"]["value"] is None
    assert any(
        code.startswith("a1_contract_validation_failed.")
        for code in a1["blocker_codes"]
    )


def test_a1_duplicate_comparison_key_rejects_counts() -> None:
    records = _a1_complete_records()
    records.append(deepcopy(records[-1]))

    result = audit_learning_adoption_evidence(
        build_learning_adoption_audit_input(a1=records)
    )
    a1 = result["variants"]["A1"]

    assert "a1_duplicate_comparison_key" in a1["blocker_codes"]
    assert a1["actual_adoption_count"]["value"] is None


def test_a1_synthetic_or_authority_fields_fail_closed() -> None:
    synthetic = _a1_complete_records()[0]
    synthetic["synthetic_fixture"] = True
    authority = _a1_complete_records()[0]
    authority["permissions"] = {"assignment_authority": True}

    synthetic_result = audit_learning_adoption_evidence(
        build_learning_adoption_audit_input(a1=(synthetic,))
    )["variants"]["A1"]
    authority_result = audit_learning_adoption_evidence(
        build_learning_adoption_audit_input(a1=(authority,))
    )["variants"]["A1"]

    assert (
        "a1_synthetic_runtime_rejected.record_0"
        in synthetic_result["blocker_codes"]
    )
    assert synthetic_result["actual_adoption_count"]["value"] is None
    assert (
        "a1_authority_escalation_attempt.record_0"
        in authority_result["blocker_codes"]
    )
    assert authority_result["actual_adoption_count"]["value"] is None


def test_a2_candidate_rejection_is_audited_zero() -> None:
    result = audit_learning_adoption_evidence(
        build_learning_adoption_audit_input(a2=(_a2_rejected_record(),))
    )
    a2 = result["variants"]["A2"]

    assert a2["highest_evidence_stage"] == "candidate_rejected"
    assert a2["actual_adoption_count"] == {
        "availability": "available",
        "value": 0,
        "reason_codes": [],
    }
    assert a2["physical_window_count"]["value"] is None
    assert "a2_actual_adoption_absent" in a2["blocker_codes"]


def test_a2_post_projection_rejection_is_audited_zero() -> None:
    result = audit_learning_adoption_evidence(
        build_learning_adoption_audit_input(
            a2=(_a2_post_projection_rejected_record(),)
        )
    )
    a2 = result["variants"]["A2"]

    assert a2["highest_evidence_stage"] == "safe_adoption_rejected"
    assert a2["validated_record_count"] == 1
    assert a2["actual_adoption_count"] == {
        "availability": "available",
        "value": 0,
        "reason_codes": [],
    }
    assert a2["physical_window_count"]["value"] is None
    assert a2["same_key_r0_pair_count"]["value"] is None
    assert a2["benefit_auditable_count"]["value"] is None
    assert "a2_actual_adoption_absent" in a2["blocker_codes"]
    assert not any(
        "a2_d3_plan_stage_contradiction" in code
        for code in a2["blocker_codes"]
    )
    assert a2["positive_benefit_claimed"] is False
    assert a2["non_degradation_claimed"] is False
    assert all(value is False for value in a2["permissions"].values())


def test_a2_post_projection_rejection_tamper_fails_closed() -> None:
    record = _a2_post_projection_rejected_record()
    record["projection_available"] = False
    payload = dict(record)
    payload.pop("content_sha256")
    record["content_sha256"] = _canonical_sha256(payload)

    a2 = audit_learning_adoption_evidence(
        build_learning_adoption_audit_input(a2=(record,))
    )["variants"]["A2"]

    assert a2["actual_adoption_count"]["value"] is None
    assert any(
        "a2_projection_contract_incomplete" in code
        for code in a2["blocker_codes"]
    )
    assert all(value is False for value in a2["permissions"].values())


def test_a2_post_projection_rejection_requires_reason() -> None:
    record = _a2_post_projection_rejected_record()
    record["reason_codes"] = []
    payload = dict(record)
    payload.pop("content_sha256")
    record["content_sha256"] = _canonical_sha256(payload)

    a2 = audit_learning_adoption_evidence(
        build_learning_adoption_audit_input(a2=(record,))
    )["variants"]["A2"]

    assert a2["actual_adoption_count"]["value"] is None
    assert any(
        code.startswith("a2_contract_validation_failed.")
        for code in a2["blocker_codes"]
    )
    assert all(value is False for value in a2["permissions"].values())


def test_a2_post_projection_rejection_rejects_execution_evidence() -> None:
    record = _a2_post_projection_rejected_record()
    complete = _a2_complete_record()
    for name in (
        "d3_successor_plan",
        "runtime_ack",
        "owner_ack_delivery",
        "coalition_commits",
        "physical_window",
        "d3_successor_plan_available",
        "runtime_ack_available",
        "owner_ack_available",
        "coalition_commit_required",
        "coalition_commit_available",
        "physical_window_available",
    ):
        record[name] = deepcopy(complete[name])
    payload = dict(record)
    payload.pop("content_sha256")
    record["content_sha256"] = _canonical_sha256(payload)

    a2 = audit_learning_adoption_evidence(
        build_learning_adoption_audit_input(a2=(record,))
    )["variants"]["A2"]

    assert a2["actual_adoption_count"]["value"] is None
    assert any(
        "a2_post_projection_rejection_contract_invalid" in code
        for code in a2["blocker_codes"]
    )
    assert all(value is False for value in a2["permissions"].values())


def test_a2_incomplete_runtime_chain_is_unavailable_not_zero() -> None:
    result = audit_learning_adoption_evidence(
        build_learning_adoption_audit_input(a2=(_a2_incomplete_record(),))
    )
    a2 = result["variants"]["A2"]

    assert a2["highest_evidence_stage"] == "awaiting_d3_plan"
    assert a2["actual_adoption_count"]["value"] is None
    assert a2["physical_window_count"]["value"] is None
    assert "a2.d3_successor_plan_missing" in a2["blocker_codes"]


@pytest.mark.parametrize(
    ("record_factory", "stage", "reason"),
    (
        (
            _a2_missing_runtime_ack_record,
            "awaiting_runtime_ack",
            "a2.runtime_ack_missing",
        ),
        (
            _a2_missing_physical_window_record,
            "awaiting_physical_window",
            "a2.physical_window_missing",
        ),
    ),
)
def test_a2_missing_ack_or_physical_window_remains_unavailable(
    record_factory,
    stage: str,
    reason: str,
) -> None:
    result = audit_learning_adoption_evidence(
        build_learning_adoption_audit_input(a2=(record_factory(),))
    )
    a2 = result["variants"]["A2"]

    assert a2["highest_evidence_stage"] == stage
    assert a2["actual_adoption_count"]["value"] is None
    assert a2["physical_window_count"]["value"] is None
    assert reason in a2["blocker_codes"]


def test_a2_nested_tamper_with_recomputed_outer_hash_fails_closed() -> None:
    record = _a2_complete_record()
    record["runtime_ack"]["assignment_plan_ack_payload_sha256"] = "f" * 64
    payload = dict(record)
    payload.pop("content_sha256")
    record["content_sha256"] = _canonical_sha256(payload)

    result = audit_learning_adoption_evidence(
        build_learning_adoption_audit_input(a2=(record,))
    )
    a2 = result["variants"]["A2"]

    assert a2["actual_adoption_count"]["value"] is None
    assert any(
        code.startswith("a2_contract_validation_failed.")
        for code in a2["blocker_codes"]
    )


def test_a2_duplicate_comparison_key_rejects_counts() -> None:
    record = _a2_complete_record()
    result = audit_learning_adoption_evidence(
        build_learning_adoption_audit_input(a2=(record, record))
    )

    a2 = result["variants"]["A2"]
    assert "a2_duplicate_comparison_key" in a2["blocker_codes"]
    assert a2["actual_adoption_count"]["value"] is None


def test_a2_synthetic_or_authority_fields_fail_closed() -> None:
    synthetic = _a2_complete_record()
    synthetic["synthetic_fixture"] = True
    synthetic_payload = dict(synthetic)
    synthetic_payload.pop("content_sha256")
    synthetic["content_sha256"] = _canonical_sha256(synthetic_payload)
    authority = _a2_complete_record()
    authority["permissions"] = {"failover_authority": True}
    authority_payload = dict(authority)
    authority_payload.pop("content_sha256")
    authority["content_sha256"] = _canonical_sha256(authority_payload)

    synthetic_result = audit_learning_adoption_evidence(
        build_learning_adoption_audit_input(a2=(synthetic,))
    )["variants"]["A2"]
    authority_result = audit_learning_adoption_evidence(
        build_learning_adoption_audit_input(a2=(authority,))
    )["variants"]["A2"]

    assert synthetic_result["actual_adoption_count"]["value"] is None
    assert (
        "a2_synthetic_runtime_rejected.record_0"
        in synthetic_result["blocker_codes"]
    )
    assert (
        "a2_authority_escalation_attempt.record_0"
        in authority_result["blocker_codes"]
    )
    assert authority_result["actual_adoption_count"]["value"] is None


def test_missing_variants_remain_unavailable_without_zero_filling() -> None:
    result = audit_learning_adoption_evidence(
        build_learning_adoption_audit_input()
    )

    for variant in ("A1", "A2", "A3"):
        row = result["variants"][variant]
        assert row["availability"] == "unavailable"
        for name in (
            "actual_adoption_count",
            "physical_window_count",
            "same_key_r0_pair_count",
            "auditable_benefit_count",
        ):
            assert row[name]["availability"] == "unavailable"
            assert row[name]["value"] is None


def test_input_unknown_field_and_content_tamper_are_rejected() -> None:
    request = build_learning_adoption_audit_input()
    unknown = {**request, "assignment_authority": True}
    with pytest.raises(
        StrictLearningAdoptionAuditError,
        match="audit_input_fields_mismatch",
    ):
        validate_learning_adoption_audit_input(unknown)

    tampered = deepcopy(request)
    tampered["schema_version"] = "d6.strict-learning-adoption-audit-input.v3"
    with pytest.raises(
        StrictLearningAdoptionAuditError,
        match="audit_input_schema_unsupported",
    ):
        validate_learning_adoption_audit_input(tampered)

    tampered = deepcopy(request)
    tampered["a1"] = [{"schema_version": "unknown"}]
    with pytest.raises(
        StrictLearningAdoptionAuditError,
        match="audit_input_content_sha256_mismatch",
    ):
        validate_learning_adoption_audit_input(tampered)


def test_input_v2_requires_pairing_disposition_field() -> None:
    request = build_learning_adoption_audit_input(
        a3_pairing_dispositions=()
    )
    request.pop("a3_pairing_dispositions")
    body = dict(request)
    body.pop("content_sha256")
    request["content_sha256"] = _canonical_sha256(body)

    with pytest.raises(
        StrictLearningAdoptionAuditError,
        match="audit_input_fields_mismatch",
    ):
        validate_learning_adoption_audit_input(request)


def test_explicit_episode_evidence_files_are_verified_and_combined(
    tmp_path: Path,
) -> None:
    paths: list[Path] = []
    for index, records in enumerate(
        (
            {"a1": [], "a2": [_a2_complete_record()], "a3": []},
            {"a1": [], "a2": [], "a3": [_a3_complete_record()]},
            {"a1": [], "a2": [], "a3": []},
        ),
        start=1,
    ):
        episode_id = (
            "episode-r0" if index == 3 else f"episode-{index:03d}"
        )
        payload: dict[str, object] = {
            "schema_version": (
                "scalable3d-learning-adoption-evidence-records-v1"
            ),
            "episode_id": episode_id,
            "records": records,
        }
        payload["content_sha256"] = _canonical_sha256(payload)
        path = tmp_path / f"{episode_id}.json"
        path.write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )
        paths.append(path)

    first = load_learning_adoption_episode_evidence(paths[0])
    combined = build_learning_adoption_audit_input_from_episode_files(
        paths
    )

    assert first["episode_id"] == "episode-001"
    assert len(combined["a2"]) == 1
    assert len(combined["a3"]) == 1
    assert (
        validate_learning_adoption_audit_input(combined)
        == combined
    )
    assert (
        audit_learning_adoption_evidence(combined)["variants"]["A3"][
            "benefit_auditable_count"
        ]["value"]
        == 1
    )

    duplicate = tmp_path / "episode-duplicate.json"
    duplicate.write_text(paths[0].read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(
        StrictLearningAdoptionAuditError,
        match="episode_evidence_duplicate_episode_id",
    ):
        build_learning_adoption_audit_input_from_episode_files(
            (paths[0], duplicate)
        )


def test_d4_pair_wrapper_resolves_safe_source_across_episode_files(
    tmp_path: Path,
) -> None:
    safe, pair = _a2_pair_records()
    candidate_episode = pair["candidate_window"]["execution_arm_id"]
    r0_episode = pair["same_key_r0_window"]["execution_arm_id"]

    def write_episode(
        episode_id: str,
        records: dict[str, list[dict[str, object]]],
    ) -> Path:
        payload: dict[str, object] = {
            "schema_version": (
                "scalable3d-learning-adoption-evidence-records-v1"
            ),
            "episode_id": episode_id,
            "records": records,
        }
        payload["content_sha256"] = _canonical_sha256(payload)
        path = tmp_path / f"{episode_id}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    candidate_path = write_episode(
        candidate_episode,
        {"a1": [], "a2": [safe], "a3": []},
    )
    r0_path = write_episode(
        r0_episode,
        {"a1": [], "a2": [], "a3": []},
    )
    pair_path = write_episode(
        "episode-a2-pair-assembly",
        {"a1": [], "a2": [pair], "a3": []},
    )

    request = build_learning_adoption_audit_input_from_episode_files(
        (candidate_path, r0_path, pair_path)
    )
    a2 = audit_learning_adoption_evidence(request)["variants"]["A2"]

    assert a2["availability"] == "available"
    assert a2["actual_adoption_count"]["value"] == 1
    assert a2["physical_window_count"]["value"] == 1
    assert a2["same_key_r0_pair_count"]["value"] == 1
    assert a2["benefit_auditable_count"]["value"] == 1

    with pytest.raises(
        StrictLearningAdoptionAuditError,
        match="episode_a2_source_episode_missing",
    ):
        build_learning_adoption_audit_input_from_episode_files(
            (candidate_path, pair_path)
        )

    wrong_candidate_path = write_episode(
        "episode-a2-wrong-source",
        {"a1": [], "a2": [safe], "a3": []},
    )
    with pytest.raises(
        StrictLearningAdoptionAuditError,
        match="episode_a2_candidate_source_episode_mismatch",
    ):
        build_learning_adoption_audit_input_from_episode_files(
            (wrong_candidate_path, r0_path, pair_path)
        )


def test_a3_nested_hash_tamper_fails_closed() -> None:
    record = _a3_complete_record()
    record["adoption_trace"]["issued_command_payload"]["aim_point_ned"][0] = 999.0
    result = audit_learning_adoption_evidence(
        build_learning_adoption_audit_input(a3=(record,))
    )

    a3 = result["variants"]["A3"]
    assert a3["availability"] == "unavailable"
    assert a3["actual_adoption_count"]["value"] is None
    assert any(
        code.startswith("a3_contract_validation_failed.")
        for code in a3["blocker_codes"]
    )


def test_a3_synthetic_runtime_cannot_masquerade_as_adoption() -> None:
    support = _support("d5")
    trace = _a3_trace(
        ack_kind=support.SYNTHETIC_FIXTURE_EVIDENCE_KIND,
        feedback_kind=support.SYNTHETIC_FIXTURE_EVIDENCE_KIND,
        synthetic_fixture=True,
    )
    record = support.assemble_active_vision_a3_evidence(
        trace,
        candidate_window=support._candidate_window(
            trace,
            observation_kind=support.SYNTHETIC_FIXTURE_EVIDENCE_KIND,
        ),
        same_key_r0_window=support._r0_window(trace),
    ).to_dict()

    result = audit_learning_adoption_evidence(
        build_learning_adoption_audit_input(a3=(record,))
    )

    a3 = result["variants"]["A3"]
    assert a3["actual_adoption_count"]["value"] is None
    assert "a3_synthetic_runtime_rejected" in a3["blocker_codes"]


def test_a3_duplicate_comparison_key_rejects_aggregate_counts() -> None:
    record = _a3_complete_record()
    result = audit_learning_adoption_evidence(
        build_learning_adoption_audit_input(a3=(record, record))
    )

    a3 = result["variants"]["A3"]
    assert "a3_duplicate_comparison_key" in a3["blocker_codes"]
    assert "a3_r0_multi_pair_reuse" in a3["blocker_codes"]
    assert a3["actual_adoption_count"]["value"] is None


def test_a3_event_log_digest_is_bound_to_episode_id() -> None:
    first = _a3_complete_record()
    second = _a3_complete_record(
        comparison_key="nominal-scale5-seed1001-window0",
        seed=1001,
        source_event_log_sha256=_canonical_sha256(
            {"event_log": "candidate-seed-1001"}
        ),
    )

    result = audit_learning_adoption_evidence(
        build_learning_adoption_audit_input(a3=(first, second))
    )

    a3 = result["variants"]["A3"]
    assert (
        "a3_event_log_episode_binding_mismatch"
        in a3["blocker_codes"]
    )
    assert a3["actual_adoption_count"]["value"] is None
    assert a3["same_key_r0_pair_count"]["value"] is None


def test_a3_cross_key_r0_pair_is_rejected_by_public_validator() -> None:
    record = _a3_complete_record()
    r0 = record["same_key_r0_window"]
    r0["comparison_key"] = "different-comparison-key"
    r0_without_hash = dict(r0)
    r0_without_hash.pop("window_sha256")
    r0["window_sha256"] = _canonical_sha256(r0_without_hash)
    record_without_hash = dict(record)
    record_without_hash.pop("content_sha256")
    record["content_sha256"] = _canonical_sha256(record_without_hash)

    result = audit_learning_adoption_evidence(
        build_learning_adoption_audit_input(a3=(record,))
    )

    assert any(
        "same_key_r0_identity_mismatch" in code
        for code in result["variants"]["A3"]["blocker_codes"]
    )


def test_a3_authority_escalation_is_rejected_before_counting() -> None:
    record = _a3_complete_record()
    record["permissions"]["camera_command_authority"] = True
    result = audit_learning_adoption_evidence(
        build_learning_adoption_audit_input(a3=(record,))
    )

    a3 = result["variants"]["A3"]
    assert "a3_authority_escalation_attempt.record_0" in a3["blocker_codes"]
    assert a3["actual_adoption_count"]["value"] is None
    assert all(value is False for value in result["permissions"].values())


def test_rule_fallback_is_explicit_zero_adoption_not_a_physical_success() -> None:
    support = _support("d5")
    trace = _a3_trace(
        decision=support._decision(assist=False, projection_rejected=True)
    )
    record = support.assemble_active_vision_a3_evidence(
        trace,
        candidate_window=None,
        same_key_r0_window=support._r0_window(trace),
    ).to_dict()

    result = audit_learning_adoption_evidence(
        build_learning_adoption_audit_input(a3=(record,))
    )
    a3 = result["variants"]["A3"]

    assert a3["actual_adoption_count"] == {
        "availability": "available",
        "value": 0,
        "reason_codes": [],
    }
    assert a3["physical_window_count"]["value"] is None
    assert a3["auditable_benefit_count"]["value"] is None


def test_a1_batch_inventory_without_public_loader_fails_closed() -> None:
    batch_inventory = {
        "schema_version": (
            "d3.a1-isolated-intervention-candidate-inventory.v1"
        ),
        "batch_id": "batch-001",
        "records": [],
        "content_sha256": "0" * 64,
    }
    result = audit_learning_adoption_evidence(
        build_learning_adoption_audit_input(a1=(batch_inventory,))
    )

    assert (
        "a1_batch_public_strict_loader_unavailable"
        in result["variants"]["A1"]["blocker_codes"]
    )
    assert result["variants"]["A1"]["actual_adoption_count"]["value"] is None


def test_truth_leakage_fails_closed_for_each_variant() -> None:
    a1 = _a1_complete_records()[0]
    a1["truth_id"] = "T-001"
    a2 = _a2_complete_record()
    a2["outcome"] = {"reward": 1.0}
    a3 = _a3_complete_record()
    a3["actor_id"] = "Intruder-1"
    result = audit_learning_adoption_evidence(
        build_learning_adoption_audit_input(a1=(a1,), a2=(a2,), a3=(a3,))
    )

    assert "a1_truth_or_outcome_leakage.record_0" in (
        result["variants"]["A1"]["blocker_codes"]
    )
    assert "a2_truth_or_outcome_leakage.record_0" in (
        result["variants"]["A2"]["blocker_codes"]
    )
    assert "a3_truth_leakage.record_0" in (
        result["variants"]["A3"]["blocker_codes"]
    )


def test_mixed_a1_a2_a3_aggregate_does_not_hide_unavailable_variants() -> None:
    result = audit_learning_adoption_evidence(
        build_learning_adoption_audit_input(
            a1=_a1_complete_records(),
            a2=(_a2_complete_record(),),
            a3=(_a3_complete_record(),),
        )
    )

    assert result["variants"]["A3"]["availability"] == "available"
    assert result["variants"]["A1"]["availability"] == "unavailable"
    assert result["variants"]["A2"]["availability"] == "unavailable"
    assert result["availability"] == "unavailable"
    for name in (
        "actual_adoption_count",
        "physical_window_count",
        "same_key_r0_pair_count",
        "auditable_benefit_count",
    ):
        assert result["aggregate"][name]["availability"] == "unavailable"
        assert result["aggregate"][name]["value"] is None
