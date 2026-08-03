"""Non-formal quota audit helpers for the frozen A1 v3 source schedule."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
import json
from math import isfinite
import os
from pathlib import Path
import tempfile
from typing import Any


A1_V3_QUOTA_PROBE_SCHEMA_V1 = "d3-a1-v3-cross-seed-quota-probe-v1"
A1_V3_QUOTA_KEYS = ("observable", "positive", "negative", "hard_negative")
A1_V3_FORBIDDEN_FORMAL_SEEDS = frozenset(range(1000, 1020))
A1_V3_FORBIDDEN_R0_SHARDS = frozenset(range(10, 20))
A1_V3_QUOTA_PROBE_SOURCE_ONLY_CONTRACT = {
    "counterfactual_mode": "coverage_degrading",
    "post_projection_reference_policy": "exact_safe_reference",
    "candidate_reference_access_allowed": False,
    "safe_reference_enters_after_candidate_freeze": True,
    "effective_safe_reference_exact_match_required": True,
    "online_truth_read_allowed": False,
    "global_track_id_write_allowed": False,
}


class A1V3QuotaProbeError(ValueError):
    """A non-formal quota probe record violates an audit invariant."""


def canonical_frame_key(value: Any) -> tuple[int, str, int]:
    """Normalize the JSON list/Python tuple frame-key representation."""

    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise A1V3QuotaProbeError("probe_frame_key_invalid")
    seed, episode_id, frame_index = value
    if type(seed) is not int or seed < 0:
        raise A1V3QuotaProbeError("probe_frame_key_seed_invalid")
    if not isinstance(episode_id, str) or not episode_id:
        raise A1V3QuotaProbeError("probe_frame_key_episode_invalid")
    if type(frame_index) is not int or frame_index < 0:
        raise A1V3QuotaProbeError("probe_frame_key_index_invalid")
    return seed, episode_id, frame_index


@dataclass(frozen=True)
class A1V3QuotaCounts:
    observable: int
    positive: int
    negative: int
    hard_negative: int

    def __post_init__(self) -> None:
        for name in A1_V3_QUOTA_KEYS:
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise A1V3QuotaProbeError(f"quota_count_invalid:{name}")

    def to_dict(self) -> dict[str, int]:
        return {name: getattr(self, name) for name in A1_V3_QUOTA_KEYS}

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "A1V3QuotaCounts":
        if set(value) != set(A1_V3_QUOTA_KEYS):
            raise A1V3QuotaProbeError("quota_count_fields_mismatch")
        return cls(**{name: value[name] for name in A1_V3_QUOTA_KEYS})


def missing_a1_v3_quota(
    counts: A1V3QuotaCounts,
    required: A1V3QuotaCounts,
) -> A1V3QuotaCounts:
    """Return the exact non-negative deficit without changing frozen quotas."""

    return A1V3QuotaCounts(
        observable=max(0, required.observable - counts.observable),
        positive=max(0, required.positive - counts.positive),
        negative=max(0, required.negative - counts.negative),
        hard_negative=max(0, required.hard_negative - counts.hard_negative),
    )


def quota_met(missing: A1V3QuotaCounts) -> bool:
    return not any(missing.to_dict().values())


def validate_probe_episode_record(record: Mapping[str, Any]) -> None:
    """Validate one completed record before it is accepted into a checkpoint."""

    required_fields = {
        "entry_index",
        "episode_id",
        "cell_id",
        "scenario_family",
        "seed",
        "split",
        "source_only_counterfactual_mode",
        "source_only_contract",
        "status",
        "required",
        "counts",
        "missing",
        "online_truth_use_count",
        "global_track_id_created_count",
        "global_track_id_rewritten_count",
        "finite_state",
        "frames",
        "probe_error_code",
    }
    if set(record) != required_fields:
        raise A1V3QuotaProbeError("probe_episode_fields_mismatch")
    for name in ("entry_index", "seed", "online_truth_use_count"):
        if type(record[name]) is not int or record[name] < 0:
            raise A1V3QuotaProbeError(f"probe_episode_{name}_invalid")
    for name in (
        "global_track_id_created_count",
        "global_track_id_rewritten_count",
    ):
        if type(record[name]) is not int or record[name] < 0:
            raise A1V3QuotaProbeError(f"probe_episode_{name}_invalid")
    if record["seed"] in A1_V3_FORBIDDEN_FORMAL_SEEDS:
        raise A1V3QuotaProbeError("forbidden_formal_seed_read")
    if record["split"] not in {"train", "validation", "test"}:
        raise A1V3QuotaProbeError("probe_episode_split_invalid")
    if record["source_only_counterfactual_mode"] != "coverage_degrading":
        raise A1V3QuotaProbeError("probe_counterfactual_mode_invalid")
    if record["source_only_contract"] != A1_V3_QUOTA_PROBE_SOURCE_ONLY_CONTRACT:
        raise A1V3QuotaProbeError("probe_source_only_contract_invalid")
    if record["status"] not in {"pass", "quota_failed", "probe_error"}:
        raise A1V3QuotaProbeError("probe_episode_status_invalid")
    required = A1V3QuotaCounts.from_mapping(record["required"])
    counts = A1V3QuotaCounts.from_mapping(record["counts"])
    missing = A1V3QuotaCounts.from_mapping(record["missing"])
    if counts.positive + counts.negative != counts.observable:
        raise A1V3QuotaProbeError("probe_episode_class_inventory_mismatch")
    if counts.hard_negative > counts.negative:
        raise A1V3QuotaProbeError("probe_episode_hard_negative_inventory_mismatch")
    if required.positive + required.negative > required.observable:
        raise A1V3QuotaProbeError("probe_required_class_inventory_impossible")
    if required.hard_negative > required.negative:
        raise A1V3QuotaProbeError("probe_required_hard_negative_impossible")
    if missing != missing_a1_v3_quota(counts, required):
        raise A1V3QuotaProbeError("probe_episode_missing_quota_mismatch")
    expected_status = "pass" if quota_met(missing) else "quota_failed"
    if record["status"] != "probe_error" and record["status"] != expected_status:
        raise A1V3QuotaProbeError("probe_episode_status_count_mismatch")
    if record["status"] != "probe_error" and len(record["frames"]) != counts.observable:
        raise A1V3QuotaProbeError("probe_episode_frame_inventory_mismatch")
    if record["status"] != "probe_error" and any(
        record[name] != 0
        for name in (
            "online_truth_use_count",
            "global_track_id_created_count",
            "global_track_id_rewritten_count",
        )
    ):
        raise A1V3QuotaProbeError("probe_episode_online_identity_write_nonzero")
    if not isinstance(record["finite_state"], bool):
        raise A1V3QuotaProbeError("probe_episode_finite_state_invalid")
    error_code = record["probe_error_code"]
    if record["status"] == "probe_error":
        if not isinstance(error_code, str) or not error_code:
            raise A1V3QuotaProbeError("probe_error_code_missing")
    elif error_code is not None:
        raise A1V3QuotaProbeError("probe_error_code_unexpected")
    for frame in record["frames"]:
        frame_key = canonical_frame_key(frame.get("frame_key"))
        if frame_key[:2] != (record["seed"], record["episode_id"]):
            raise A1V3QuotaProbeError("probe_frame_key_episode_binding_mismatch")
        if "frame_index" in frame and frame["frame_index"] != frame_key[2]:
            raise A1V3QuotaProbeError("probe_frame_key_index_binding_mismatch")
        if record["status"] != "probe_error":
            if (
                frame.get("source_only_counterfactual_mode")
                != record["source_only_counterfactual_mode"]
            ):
                raise A1V3QuotaProbeError(
                    "probe_frame_counterfactual_mode_binding_mismatch"
                )
            if (
                frame.get("post_projection_reference_policy")
                != record["source_only_contract"][
                    "post_projection_reference_policy"
                ]
            ):
                raise A1V3QuotaProbeError(
                    "probe_frame_reference_policy_binding_mismatch"
                )
            _validate_source_only_probe_frame(frame)


def _validate_source_only_probe_frame(frame: Mapping[str, Any]) -> None:
    if frame.get("source_only_counterfactual_mode") != "coverage_degrading":
        raise A1V3QuotaProbeError("probe_frame_counterfactual_mode_invalid")
    if frame.get("post_projection_reference_policy") != "exact_safe_reference":
        raise A1V3QuotaProbeError("probe_frame_reference_policy_invalid")
    measurement = frame.get("measurement_timestamp_s")
    arrival = frame.get("arrival_timestamp_s")
    if (
        isinstance(measurement, bool)
        or isinstance(arrival, bool)
        or not isinstance(measurement, (int, float))
        or not isinstance(arrival, (int, float))
        or not isfinite(float(measurement))
        or not isfinite(float(arrival))
        or float(arrival) <= float(measurement)
    ):
        raise A1V3QuotaProbeError("probe_frame_dual_timestamp_invalid")
    for name in (
        "online_truth_use_count",
        "global_track_id_created_count",
        "global_track_id_rewritten_count",
    ):
        if frame.get(name) != 0:
            raise A1V3QuotaProbeError(f"probe_frame_{name}_nonzero")
    if frame.get("effective_matches_teacher") is not True:
        raise A1V3QuotaProbeError("probe_frame_effective_safety_fallback_invalid")
    if not isinstance(frame.get("candidate_differs_from_teacher"), bool):
        raise A1V3QuotaProbeError("probe_frame_candidate_difference_invalid")
    transition_counts = {
        name: frame.get(name)
        for name in (
            "candidate_edge_count_before",
            "candidate_edge_count_after",
            "candidate_edge_count_delta",
            "candidate_edge_added_count",
            "candidate_edge_removed_count",
            "teacher_edge_count_delta",
            "coverage_deficit_delta",
        )
    }
    if any(type(value) is not int for value in transition_counts.values()):
        raise A1V3QuotaProbeError("probe_frame_transition_count_invalid")
    if any(
        transition_counts[name] < 0
        for name in (
            "candidate_edge_count_before",
            "candidate_edge_count_after",
            "candidate_edge_added_count",
            "candidate_edge_removed_count",
        )
    ):
        raise A1V3QuotaProbeError("probe_frame_transition_count_invalid")
    candidate_delta = transition_counts["candidate_edge_count_delta"]
    if (
        transition_counts["candidate_edge_count_after"]
        - transition_counts["candidate_edge_count_before"]
        != candidate_delta
        or transition_counts["candidate_edge_added_count"]
        - transition_counts["candidate_edge_removed_count"]
        != candidate_delta
    ):
        raise A1V3QuotaProbeError(
            "probe_frame_candidate_feasibility_inventory_inconsistent"
        )
    transition_axes = frame.get("transition_axes")
    if (
        not isinstance(transition_axes, list)
        or any(not isinstance(axis, str) for axis in transition_axes)
        or len(transition_axes) != len(set(transition_axes))
    ):
        raise A1V3QuotaProbeError("probe_frame_transition_axes_invalid")
    action_change_type = frame.get("action_change_type")
    if action_change_type == "assignment_coverage_contraction" and not (
        candidate_delta < 0
        and transition_counts["teacher_edge_count_delta"] < 0
        and transition_counts["coverage_deficit_delta"]
        == -transition_counts["teacher_edge_count_delta"]
        and "candidate_feasibility" in transition_axes
        and "teacher_edges" in transition_axes
    ):
        raise A1V3QuotaProbeError(
            "probe_frame_coverage_contraction_evidence_invalid"
        )
    if action_change_type == "assignment_coverage_recovery" and not (
        candidate_delta > 0
        and transition_counts["teacher_edge_count_delta"] > 0
        and transition_counts["coverage_deficit_delta"]
        == -transition_counts["teacher_edge_count_delta"]
        and "candidate_feasibility" in transition_axes
        and "teacher_edges" in transition_axes
    ):
        raise A1V3QuotaProbeError(
            "probe_frame_coverage_recovery_evidence_invalid"
        )
    pre_reasons = frame.get("pre_projection_reason_codes")
    post_reasons = frame.get("post_projection_reason_codes")
    if not isinstance(pre_reasons, list) or not any(
        reason
        in {
            "candidate_coverage_degradation_generated_v1",
            "candidate_coverage_degradation_unavailable_v1",
        }
        for reason in pre_reasons
    ):
        raise A1V3QuotaProbeError("probe_frame_source_only_reason_missing")
    if not isinstance(post_reasons, list) or not any(
        reason
        in {
            "effective_reference_plan_stability_fallback_v1",
            "effective_reference_plan_stability_match_v1",
        }
        for reason in post_reasons
    ):
        raise A1V3QuotaProbeError("probe_frame_effective_reason_missing")


def build_a1_v3_quota_probe_report(
    records: Sequence[Mapping[str, Any]],
    *,
    schedule_path: str,
    schedule_sha256: str,
    base_config_path: str,
    base_config_sha256: str,
    source_git_commit: str,
    generated_at_utc: str,
    elapsed_s: float,
    expected_episode_count: int = 300,
    repository_dirty: bool = False,
    source_bindings: Mapping[str, Mapping[str, str]] | None = None,
) -> dict[str, Any]:
    """Build an audit report that cannot be mistaken for a source dataset."""

    ordered = tuple(sorted((dict(item) for item in records), key=lambda item: item["entry_index"]))
    if len(ordered) != expected_episode_count:
        raise A1V3QuotaProbeError("probe_episode_coverage_incomplete")
    for item in ordered:
        validate_probe_episode_record(item)
    if tuple(item["entry_index"] for item in ordered) != tuple(range(expected_episode_count)):
        raise A1V3QuotaProbeError("probe_entry_index_not_contiguous")
    episode_ids = [item["episode_id"] for item in ordered]
    seeds = [item["seed"] for item in ordered]
    if len(set(episode_ids)) != len(episode_ids):
        raise A1V3QuotaProbeError("probe_duplicate_episode_id")
    if len(set(seeds)) != len(seeds):
        raise A1V3QuotaProbeError("probe_duplicate_seed")
    if set(seeds) & A1_V3_FORBIDDEN_FORMAL_SEEDS:
        raise A1V3QuotaProbeError("forbidden_formal_seed_read")

    frame_keys: list[tuple[int, str, int]] = []
    for item in ordered:
        for frame in item["frames"]:
            frame_keys.append(canonical_frame_key(frame.get("frame_key")))
    duplicate_frame_count = len(frame_keys) - len(set(frame_keys))
    status_counts = Counter(item["status"] for item in ordered)
    failures = [
        {key: value for key, value in item.items() if key != "frames"}
        for item in ordered
        if item["status"] != "pass"
    ]
    cells = sorted({item["cell_id"] for item in ordered})
    cell_summary = []
    for cell_id in cells:
        cell_records = [item for item in ordered if item["cell_id"] == cell_id]
        cell_summary.append(
            {
                "cell_id": cell_id,
                "episode_count": len(cell_records),
                "pass_count": sum(item["status"] == "pass" for item in cell_records),
                "failure_count": sum(item["status"] != "pass" for item in cell_records),
                "minimum_counts": {
                    name: min(item["counts"][name] for item in cell_records)
                    for name in A1_V3_QUOTA_KEYS
                },
                "maximum_missing": {
                    name: max(item["missing"][name] for item in cell_records)
                    for name in A1_V3_QUOTA_KEYS
                },
            }
        )
    truth_use = sum(item["online_truth_use_count"] for item in ordered)
    created = sum(item["global_track_id_created_count"] for item in ordered)
    rewritten = sum(item["global_track_id_rewritten_count"] for item in ordered)
    clean_quota_pass = (
        not failures
        and truth_use == 0
        and created == 0
        and rewritten == 0
        and duplicate_frame_count == 0
    )
    formal_coverage = expected_episode_count == 300
    if repository_dirty:
        status = "exploratory_dirty_pass" if clean_quota_pass else "exploratory_dirty_quota_gap"
    elif not formal_coverage:
        status = "exploratory_incomplete_pass" if clean_quota_pass else "exploratory_incomplete_quota_gap"
    else:
        status = "pass_300_of_300" if clean_quota_pass else "quota_gap_confirmed"
    return {
        "schema_version": A1_V3_QUOTA_PROBE_SCHEMA_V1,
        "status": status,
        "generated_at_utc": generated_at_utc,
        "source_git_commit": source_git_commit,
        "repository_dirty": repository_dirty,
        "exploratory_only": repository_dirty or not formal_coverage,
        "readiness_eligible": clean_quota_pass and not repository_dirty and formal_coverage,
        "source_bindings": dict(source_bindings or {}),
        "formal_source_generation": False,
        "dataset_finalized": False,
        "training_started": False,
        "runtime_authority_granted": False,
        "control_authority_granted": False,
        "schedule_path": schedule_path,
        "schedule_sha256": schedule_sha256,
        "base_config_path": base_config_path,
        "base_config_sha256": base_config_sha256,
        "episode_count": len(ordered),
        "pass_count": status_counts["pass"],
        "failure_count": len(failures),
        "probe_error_count": status_counts["probe_error"],
        "online_truth_use_count": truth_use,
        "global_track_id_created_count": created,
        "global_track_id_rewritten_count": rewritten,
        "duplicate_frame_count": duplicate_frame_count,
        "forbidden_formal_seed_read_count": 0,
        "r0_shard_10_19_read_count": 0,
        "elapsed_s": float(elapsed_s),
        "cell_summary": cell_summary,
        "failures": failures,
        "episodes": list(ordered),
    }


def canonical_json_sha256(value: Any) -> str:
    return sha256(
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    ).hexdigest()


def write_json_atomic(path: str | Path, payload: Mapping[str, Any]) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    content = (
        json.dumps(
            payload,
            ensure_ascii=True,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("ascii")
    with tempfile.NamedTemporaryFile(
        mode="wb",
        dir=destination.parent,
        prefix=f".{destination.name}.",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, destination)
    return destination


__all__ = [
    "A1V3QuotaCounts",
    "A1V3QuotaProbeError",
    "A1_V3_FORBIDDEN_FORMAL_SEEDS",
    "A1_V3_FORBIDDEN_R0_SHARDS",
    "A1_V3_QUOTA_KEYS",
    "A1_V3_QUOTA_PROBE_SCHEMA_V1",
    "build_a1_v3_quota_probe_report",
    "canonical_frame_key",
    "canonical_json_sha256",
    "missing_a1_v3_quota",
    "quota_met",
    "validate_probe_episode_record",
    "write_json_atomic",
]
