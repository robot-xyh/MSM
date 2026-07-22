from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_modules.scalable_3d_simulation.isolated_paired_rollout import (
    ISOLATED_PAIRED_ROLLOUT_SCHEMA_VERSION,
    IsolatedPairedRolloutOptions,
    execute_isolated_paired_rollouts,
    write_isolated_paired_rollout_execution,
)
from research_modules.scalable_3d_simulation.reserved_seed_interventions import (
    D3DevelopmentBundleBinding,
)


def _missing_bundle(tmp_path: Path) -> D3DevelopmentBundleBinding:
    return D3DevelopmentBundleBinding(
        bundle_dir=tmp_path / "missing-d3-bundle",
        manifest_sha256="a" * 64,
        policy_version="missing-development-policy",
    )


def test_isolated_pair_uses_separate_worlds_and_shared_exogenous_schedule(
    tmp_path: Path,
) -> None:
    execution = execute_isolated_paired_rollouts(
        IsolatedPairedRolloutOptions(
            scale=2,
            duration_s=1.2,
            seeds=(1000,),
        ),
        d3_bundle=_missing_bundle(tmp_path),
    )

    assert execution.d3_bundle_loaded is False
    assert len(execution.pairs) == 1
    pair = execution.pairs[0]
    assert pair.same_initial_state is True
    assert pair.same_exogenous_schedule is True
    assert pair.worlds_isolated is True
    assert pair.buses_isolated is True
    assert pair.control.initial_state_sha256 == pair.treatment.initial_state_sha256
    assert pair.control.result.manifest.episode_id != pair.treatment.result.manifest.episode_id
    assert pair.control.result.summary["online_truth_use_count"] == 0
    assert pair.treatment.result.summary["online_truth_use_count"] == 0
    assert pair.control.summary_payload()["production_runtime_ack"] is False
    assert pair.treatment.summary_payload()["isolated_simulation_only"] is True
    assert pair.summary_payload()["paired_physical_effect_available"] is False
    assert pair.summary_payload()["causal_available"] is False


def test_isolated_pair_writer_is_hash_bound_and_immutable(tmp_path: Path) -> None:
    execution = execute_isolated_paired_rollouts(
        IsolatedPairedRolloutOptions(
            scale=1,
            duration_s=0.2,
            seeds=(1000,),
        ),
        d3_bundle=_missing_bundle(tmp_path),
    )
    output = tmp_path / "paired-output"
    paths = write_isolated_paired_rollout_execution(output, execution)
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))

    assert manifest["schema_version"] == ISOLATED_PAIRED_ROLLOUT_SCHEMA_VERSION
    assert manifest["pair_count"] == 1
    assert manifest["same_initial_state_count"] == 1
    assert manifest["same_exogenous_schedule_count"] == 1
    assert manifest["evidence_availability"]["production_runtime_ack"] is False
    assert manifest["evidence_availability"]["d6_paired_physical_effect"] is False
    assert paths["sha256sums"].read_text(encoding="utf-8").strip()
    with pytest.raises(FileExistsError):
        write_isolated_paired_rollout_execution(output, execution)


@pytest.mark.parametrize(
    "seeds",
    [(), (1000, 1000)],
)
def test_isolated_pair_options_reject_invalid_seed_inventory(
    seeds: tuple[int, ...],
) -> None:
    with pytest.raises(ValueError, match="non-empty and unique"):
        IsolatedPairedRolloutOptions(seeds=seeds)
