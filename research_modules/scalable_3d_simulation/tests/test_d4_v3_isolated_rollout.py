from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from research_modules.scalable_3d_simulation.d4_v3_isolated_rollout import (
    D4_V3_ISOLATED_ROLLOUT_SCHEMA_VERSION,
    D4V3IsolatedRolloutExecution,
    D4V3IsolatedRolloutOptions,
    _V3TreatmentProvider,
    _v3_decision_rejection_reasons,
    normalized_region_snapshot_lineage_sha256,
    write_d4_v3_isolated_rollout_execution,
)
from research_modules.scalable_3d_simulation.run_d4_v3_isolated_rollout import (
    parse_args,
)


class _Snapshot:
    seed = 2003
    scenario_id = "nominal"
    scenario_version = "scenario-v1"

    def __init__(self, *, plan_id: str, plan_version: int = 7) -> None:
        self.plan_id = plan_id
        self.plan_version = plan_version

    def to_dict(self) -> dict[str, object]:
        return {
            "seed": self.seed,
            "scenario_id": self.scenario_id,
            "scenario_version": self.scenario_version,
            "authority_digest": f"authority-{self.plan_id}",
            "regions": [
                {
                    "region_id": "R0",
                    "plan_id": self.plan_id,
                    "plan_version": self.plan_version,
                }
            ],
        }


class _UnexpectedAdvisor:
    executor = SimpleNamespace(projector=object())

    def advise_pair(self, **_: object) -> None:
        raise AssertionError("lineage mismatch must fail before inference")


class _FakePair:
    seed = 2003
    _manifest = SimpleNamespace(
        to_dict=lambda: {
            "git_commit": "c" * 40,
            "repository_dirty": True,
            "config_sha256": "d" * 64,
        }
    )
    control = SimpleNamespace(
        summary={"online_truth_use_count": 0, "finite_state": True},
        manifest=_manifest,
    )
    treatment = SimpleNamespace(
        summary={"online_truth_use_count": 0, "finite_state": True},
        manifest=_manifest,
    )
    runtime_records: tuple[dict[str, object], ...] = ()

    def summary_payload(self) -> dict[str, object]:
        return {
            "seed": self.seed,
            "same_initial_state": True,
            "same_exogenous_config": True,
            "raw_inference_count": 1,
            "runtime_gate_pass_count": 1,
            "isolated_adoption_count": 1,
            "d3_successor_count": 0,
            "accepted_runtime_ack_count": 0,
            "physical_execution_window_count": 0,
            "control_intercept_count": 0,
            "treatment_intercept_count": 0,
        }


@pytest.mark.parametrize("seeds", [(), (2003, 2003), (1000,)])
def test_options_reject_invalid_development_seed_inventory(
    seeds: tuple[int, ...],
) -> None:
    with pytest.raises(ValueError):
        D4V3IsolatedRolloutOptions(seeds=seeds)


def test_normalized_lineage_ignores_random_plan_identity() -> None:
    left = normalized_region_snapshot_lineage_sha256(
        _Snapshot(plan_id="PLAN-random-left")
    )
    right = normalized_region_snapshot_lineage_sha256(
        _Snapshot(plan_id="PLAN-random-right")
    )

    assert left == right


def test_provider_fails_closed_on_snapshot_lineage_mismatch() -> None:
    expected = normalized_region_snapshot_lineage_sha256(
        _Snapshot(plan_id="PLAN-expected")
    )
    provider = _V3TreatmentProvider(
        advisor=_UnexpectedAdvisor(),
        binding=SimpleNamespace(
            seed=2003,
            scenario_id="nominal",
            scenario_version="scenario-v1",
        ),
        expected_timestamp_s=0.0,
        expected_snapshot_lineage_sha256=expected,
    )

    assert (
        provider.evaluate_if_due(
            snapshot=_Snapshot(plan_id="PLAN-observed", plan_version=8),
            formal_decision=object(),
            evaluated_at_s=0.0,
        )
        is None
    )
    assert provider.attempted is True
    assert provider.events[0]["trigger_passed"] is False
    assert provider.events[0]["trigger_rejection_reasons"] == [
        "normalized_snapshot_lineage_mismatch"
    ]


def test_production_permission_true_rejects_isolated_decision() -> None:
    evidence = SimpleNamespace(
        pair_input_match=True,
        candidate_bundle_match=True,
        candidate_thresholds_passed=True,
        candidate_safety_projection_passed=True,
        next_cycle_consumption_passed=True,
        isolated_treatment_safe_adopted=True,
    )
    treatment = SimpleNamespace(
        candidate_scope_compatible=True,
        raw_inference_completed=True,
        runtime_gate_applied=True,
        runtime_gate_passed=True,
        projection_passed=True,
        next_cycle_isolated_adoption=True,
        isolated_treatment_influence_allowed=True,
        isolated_treatment_influence_adopted=True,
        deterministic_rule_selected=False,
        arm_evidence=evidence,
        production_runtime_ack_emitted=False,
        assist_authority_granted=False,
        assignment_authority_granted=False,
        degradation_authority_granted=False,
        takeover_authority_granted=False,
        coalition_commit_authority_granted=False,
        control_authority_granted=False,
    )
    decision = SimpleNamespace(
        treatment=treatment,
        formal_evaluation_authorized=False,
        production_runtime_ack_emitted=False,
        assist_authority_granted=False,
        assignment_authority_granted=False,
        degradation_authority_granted=False,
        takeover_authority_granted=False,
        coalition_commit_authority_granted=False,
        control_authority_granted=True,
    )

    assert _v3_decision_rejection_reasons(decision) == [
        "paired_decision_permission_true:control_authority_granted"
    ]


def test_writer_is_atomic_hash_bound_and_does_not_overwrite(
    tmp_path: Path,
) -> None:
    execution = D4V3IsolatedRolloutExecution(
        options=D4V3IsolatedRolloutOptions(seeds=(2003,)),
        specification_id="specification-v3",
        specification_sha256="a" * 64,
        candidate_identity_sha256="b" * 64,
        pairs=(_FakePair(),),
    )
    output = tmp_path / "rollout"
    paths = write_d4_v3_isolated_rollout_execution(
        output,
        execution,
        persist_episode_outputs=False,
    )
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))

    assert manifest["schema_version"] == D4_V3_ISOLATED_ROLLOUT_SCHEMA_VERSION
    assert manifest["pair_count"] == 1
    assert manifest["d3_successor_seed_count"] == 0
    assert manifest["d3_successor_rejection_reason_counts"] == {}
    assert manifest["isolated_consumption_rejection_reason_counts"] == {}
    assert manifest["production_permissions"]["control"] is False
    assert manifest["source_provenance"]["git_commit"] == "c" * 40
    assert manifest["source_provenance"]["repository_dirty"] is True
    assert len(
        manifest["source_provenance"]["implementation_file_sha256"]
    ) == 11
    assert paths["sha256sums"].read_text(encoding="utf-8").strip()
    assert not tuple(tmp_path.glob(".rollout.tmp-*"))
    with pytest.raises(FileExistsError):
        write_d4_v3_isolated_rollout_execution(
            output,
            execution,
            persist_episode_outputs=False,
        )


def test_cli_requires_explicit_candidate_and_output_paths() -> None:
    args = parse_args(
        [
            "--candidate-root",
            "candidate",
            "--output",
            "output",
            "--seeds",
            "2003",
            "2004",
            "--no-episode-outputs",
        ]
    )

    assert args.candidate_root == Path("candidate")
    assert args.output == Path("output")
    assert args.seeds == [2003, 2004]
    assert args.no_episode_outputs is True
