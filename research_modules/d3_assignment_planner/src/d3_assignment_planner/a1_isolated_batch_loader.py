"""Strict public loader for D3 A1 isolated-intervention batch artifacts.

The loader validates the immutable offline batch layout and its internal
lineage.  Loading these artifacts never proves publication, runtime adoption,
a physical window, an R0 pair, production admission, or control authority.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .a1_intervention_selection import (
    A1_INTERVENTION_CANDIDATE_REASON_CODES,
    A1InterventionContractError,
    A1InterventionPreRegistration,
    validate_a1_intervention_preregistration,
)
from .isolated_intervention_batch import (
    A1_BATCH_CANDIDATES_FILENAME,
    A1_BATCH_RESULT_FILENAME,
    A1_BATCH_SELECTIONS_FILENAME,
    A1_ISOLATED_INTERVENTION_BATCH_RESULT_SCHEMA_V1,
    A1_ISOLATED_INTERVENTION_BATCH_SCOPE,
    A1_ISOLATED_INTERVENTION_CANDIDATE_INVENTORY_SCHEMA_V1,
    A1_ISOLATED_INTERVENTION_CANDIDATE_SCHEMA_V1,
    A1_ISOLATED_INTERVENTION_SELECTION_INVENTORY_SCHEMA_V1,
    A1_ISOLATED_INTERVENTION_SELECTION_SCHEMA_V1,
    BATCH_CHECKSUMS_FILENAME,
    BATCH_PER_SEED_FILENAME,
    BATCH_REPORT_FILENAME,
    BATCH_RESULT_FILENAME,
    ISOLATED_INTERVENTION_BATCH_FRAME_SUMMARY_SCHEMA_V1,
    ISOLATED_INTERVENTION_BATCH_RESULT_SCHEMA_V1,
    ISOLATED_INTERVENTION_BATCH_SCOPE,
    ISOLATED_INTERVENTION_BATCH_SEEDS_V1,
    _a1_execution_boundary,
    _assert_all_finite,
    _assert_truth_free,
    _execution_boundary,
    _file_sha256,
    _finite_nonnegative,
    _finite_number,
    _load_json_file,
    _mapping,
    _nonnegative_int,
    _required_text,
    _sha256_text,
    _strict_mapping,
    _strict_sequence,
    _validated_utc_timestamp,
    _fail,
)
from .runtime_plan_ack import canonical_runtime_payload_sha256


A1_ISOLATED_INTERVENTION_BATCH_LOADER_SCHEMA_V1 = (
    "d3.a1-isolated-intervention-batch-loader.v1"
)

_CHECKSUMMED_FILENAMES = (
    BATCH_RESULT_FILENAME,
    BATCH_PER_SEED_FILENAME,
    BATCH_REPORT_FILENAME,
    A1_BATCH_RESULT_FILENAME,
    A1_BATCH_CANDIDATES_FILENAME,
    A1_BATCH_SELECTIONS_FILENAME,
)
_DIRECTORY_FILENAMES = frozenset(
    (*_CHECKSUMMED_FILENAMES, BATCH_CHECKSUMS_FILENAME)
)

_A1_RESULT_FIELDS = frozenset(
    {
        "schema_version",
        "batch_scope",
        "batch_id",
        "evaluated_at",
        "input_manifest_sha256",
        "legacy_batch_result_schema_version",
        "legacy_batch_result_content_sha256",
        "preregistration",
        "preregistration_file_sha256",
        "bundle",
        "output_files",
        "candidate_contract",
        "selection_contract",
        "execution_boundary",
        "content_sha256",
    }
)
_A1_BUNDLE_FIELDS = frozenset(
    {"manifest_sha256", "policy_version", "state_dict_sha256"}
)
_A1_OUTPUT_FILE_FIELDS = frozenset(
    {
        "legacy_result",
        "legacy_per_seed",
        "legacy_report",
        "a1_result",
        "a1_candidates",
        "a1_selections",
        "checksums",
    }
)
_A1_CANDIDATE_CONTRACT_FIELDS = frozenset(
    {
        "candidate_count",
        "policy_evaluated_count",
        "cost_correction_accepted_count",
        "assignment_changed_count",
        "near_competitive_count",
        "selected_candidate_count",
        "inventory_content_sha256",
    }
)
_A1_SELECTION_CONTRACT_FIELDS = frozenset(
    {
        "seed_count",
        "selected_seed_count",
        "no_safe_discrete_intervention_seed_count",
        "inventory_content_sha256",
    }
)
_INVENTORY_FIELDS = frozenset(
    {
        "schema_version",
        "batch_id",
        "registration_id",
        "preregistration_sha256",
        "record_count",
        "records",
        "content_sha256",
    }
)
_CANDIDATE_FIELDS = frozenset(
    {
        "schema_version",
        "evidence_kind",
        "batch_id",
        "registration_id",
        "preregistration_sha256",
        "seed",
        "sequence_index",
        "timestamp_s",
        "input_path",
        "input_file_sha256",
        "input_content_sha256",
        "stable_replay_sha256",
        "stable_eligibility_sha256",
        "rule_binding_sha256",
        "treatment_binding_sha256",
        "policy_evaluated",
        "policy_evaluation_semantics_sha256",
        "cost_correction_accepted",
        "assignment_changed",
        "near_competitive",
        "selected_for_paired_evaluation",
        "version_contract_valid",
        "max_abs_cost_correction",
        "rule_basis_score",
        "treatment_rule_basis_score",
        "absolute_rule_cost_difference",
        "relative_rule_cost_difference",
        "rule_unmet_demand_slots",
        "treatment_unmet_demand_slots",
        "rule_unmet_high_threat_slots",
        "treatment_unmet_high_threat_slots",
        "rule_plan_version",
        "treatment_plan_version",
        "previous_plan_version",
        "reason_codes",
        "plan_published",
        "runtime_ack",
        "physical_window_available",
        "r0_pair_available",
        "normalization",
        "execution_boundary",
        "content_sha256",
    }
)
_CANDIDATE_NORMALIZATION_FIELDS = frozenset(
    {
        "schema_version",
        "excluded_run_local_fields",
        "binding_identity_preserved",
        "runtime_publication_evidence",
    }
)
_SELECTION_FIELDS = frozenset(
    {
        "schema_version",
        "evidence_kind",
        "batch_id",
        "registration_id",
        "preregistration_sha256",
        "seed",
        "candidate_count",
        "policy_evaluated_count",
        "cost_correction_accepted_count",
        "assignment_changed_count",
        "near_competitive_count",
        "candidate_content_sha256s",
        "candidate_history_sha256",
        "selected",
        "reason",
        "selected_candidate_content_sha256",
        "selected_sequence_index",
        "selected_timestamp_s",
        "selected_treatment_binding_sha256",
        "plan_published",
        "runtime_ack",
        "physical_window_available",
        "r0_pair_available",
        "normalization",
        "execution_boundary",
        "content_sha256",
    }
)
_SELECTION_NORMALIZATION_FIELDS = frozenset(
    {
        "schema_version",
        "selection_uses_core_a1_decision",
        "stable_candidate_hashes_replace_runtime_candidate_hashes",
        "runtime_publication_evidence",
    }
)
_LEGACY_RESULT_FIELDS = frozenset(
    {
        "schema_version",
        "batch_scope",
        "batch_id",
        "evaluated_at",
        "input_manifest_sha256",
        "split",
        "source",
        "bundle",
        "configuration",
        "seed_contract",
        "execution_boundary",
        "seeds",
        "content_sha256",
    }
)
_LEGACY_SOURCE_FIELDS = frozenset(
    {"repository_git_commit", "worktree_state"}
)
_LEGACY_CONFIGURATION_FIELDS = frozenset(
    {"planner_config_sha256", "cost_weights_sha256"}
)
_LEGACY_SEED_CONTRACT_FIELDS = frozenset(
    {
        "expected_seeds",
        "seed_count",
        "eligible_seed_count",
        "unavailable_seed_count",
    }
)
_LEGACY_SEED_FIELDS = frozenset(
    {
        "seed",
        "status",
        "unavailable_reason",
        "frame_count",
        "eligible_frame_count",
        "first_eligible",
        "bundle",
        "binding_difference_count",
        "safety",
        "execution_boundary",
        "frames",
    }
)
_LEGACY_FIRST_ELIGIBLE_FIELDS = frozenset(
    {"sequence_index", "timestamp_s", "replay_sha256", "evidence_sha256"}
)
_LEGACY_SEED_BUNDLE_FIELDS = frozenset(
    {
        "all_frames_loaded",
        "applied_frame_count",
        "fallback_frame_count",
        "fallback_reasons",
    }
)
_LEGACY_SAFETY_FIELDS = frozenset(
    {
        "rule_hard_violation_count",
        "treatment_hard_violation_count",
        "global_track_id_rewrite_count",
    }
)
_LEGACY_FRAME_FIELDS = frozenset(
    {
        "schema_version",
        "sequence_index",
        "timestamp_s",
        "input_path",
        "input_file_sha256",
        "input_content_sha256",
        "replay_sha256",
        "evidence_sha256",
        "eligible",
        "reason_codes",
        "bundle_loaded",
        "learning_cost_applied",
        "rule_fallback_applied",
        "fallback_reason",
        "binding_change_count",
        "rule_hard_violation_count",
        "treatment_hard_violation_count",
        "execution_boundary",
    }
)


@dataclass(frozen=True, slots=True)
class A1IsolatedInterventionBatchLoadResult:
    """Validated, non-authoritative A1 isolated batch artifacts."""

    output_directory: Path
    batch_result: Mapping[str, Any]
    legacy_result: Mapping[str, Any]
    candidate_inventory: Mapping[str, Any]
    selection_inventory: Mapping[str, Any]
    candidates: tuple[Mapping[str, Any], ...]
    selections: tuple[Mapping[str, Any], ...]
    file_sha256s: Mapping[str, str]
    schema_version: str = A1_ISOLATED_INTERVENTION_BATCH_LOADER_SCHEMA_V1

    @property
    def plan_published(self) -> bool:
        return False

    @property
    def runtime_ack(self) -> bool:
        return False

    @property
    def physical_window_available(self) -> bool:
        return False

    @property
    def r0_pair_available(self) -> bool:
        return False

    @property
    def production_admission_granted(self) -> bool:
        return False

    @property
    def production_assignment_authority(self) -> bool:
        return False

    @property
    def production_control_authority(self) -> bool:
        return False


def load_a1_isolated_intervention_batch(
    output_directory: str | Path,
) -> A1IsolatedInterventionBatchLoadResult:
    """Load and fully validate one fixed-layout A1 isolated batch directory."""

    root = _resolve_batch_directory(output_directory)
    file_sha256s = _load_checksum_inventory(root)
    legacy_result = _load_output_json(root, BATCH_RESULT_FILENAME)
    batch_result = _load_output_json(root, A1_BATCH_RESULT_FILENAME)
    candidate_inventory = _load_output_json(
        root, A1_BATCH_CANDIDATES_FILENAME
    )
    selection_inventory = _load_output_json(
        root, A1_BATCH_SELECTIONS_FILENAME
    )
    return _validate_loaded_artifacts(
        output_directory=root,
        file_sha256s=file_sha256s,
        legacy_result=legacy_result,
        batch_result=batch_result,
        candidate_inventory=candidate_inventory,
        selection_inventory=selection_inventory,
    )


def validate_a1_isolated_intervention_batch(
    output_directory: str | Path,
) -> A1IsolatedInterventionBatchLoadResult:
    """Public validator alias that always re-reads files and SHA-256 values."""

    return load_a1_isolated_intervention_batch(output_directory)


def _resolve_batch_directory(value: str | Path) -> Path:
    try:
        root = Path(value).resolve(strict=True)
    except OSError as exc:
        _fail("a1_batch_loader_directory_missing", str(exc))
    if not root.is_dir():
        _fail("a1_batch_loader_directory_invalid")
    try:
        children = tuple(root.iterdir())
    except OSError as exc:
        _fail("a1_batch_loader_directory_read_failed", str(exc))
    names = frozenset(path.name for path in children)
    if (
        names != _DIRECTORY_FILENAMES
        or len(children) != len(_DIRECTORY_FILENAMES)
    ):
        _fail("a1_batch_loader_directory_layout_invalid")
    for path in children:
        if path.is_symlink() or not path.is_file() or path.parent != root:
            _fail("a1_batch_loader_artifact_path_invalid", path.name)
    return root


def _load_checksum_inventory(root: Path) -> dict[str, str]:
    checksum_path = root / BATCH_CHECKSUMS_FILENAME
    try:
        text = checksum_path.read_text(encoding="ascii")
    except (OSError, UnicodeError) as exc:
        _fail("a1_batch_loader_checksums_load_failed", str(exc))
    if "\r" in text:
        _fail("a1_batch_loader_checksums_format_invalid")
    lines = text.splitlines()
    if len(lines) != len(_CHECKSUMMED_FILENAMES) or any(
        not line for line in lines
    ):
        _fail("a1_batch_loader_checksums_coverage_invalid")
    values: dict[str, str] = {}
    for line in lines:
        parts = line.split("  ")
        if len(parts) != 2:
            _fail("a1_batch_loader_checksums_format_invalid")
        raw_digest, filename = parts
        if (
            filename not in _CHECKSUMMED_FILENAMES
            or Path(filename).name != filename
            or "/" in filename
            or "\\" in filename
            or filename in values
        ):
            _fail("a1_batch_loader_checksum_path_invalid")
        digest = _sha256_text(raw_digest, "a1_batch_output_file_sha256")
        path = root / filename
        if path.is_symlink() or not path.is_file() or path.parent != root:
            _fail("a1_batch_loader_artifact_path_invalid", filename)
        if _file_sha256(path) != digest:
            _fail("a1_batch_loader_checksum_mismatch", filename)
        values[filename] = digest
    if frozenset(values) != frozenset(_CHECKSUMMED_FILENAMES):
        _fail("a1_batch_loader_checksums_coverage_invalid")
    return values


def _load_output_json(root: Path, filename: str) -> Mapping[str, Any]:
    payload = _load_json_file(
        root / filename,
        "a1_batch_loader_json_load_failed",
    )
    _assert_truth_free(payload)
    _assert_all_finite(payload)
    return _mapping(payload, filename)


def _validate_loaded_artifacts(
    *,
    output_directory: Path,
    file_sha256s: Mapping[str, str],
    legacy_result: Mapping[str, Any],
    batch_result: Mapping[str, Any],
    candidate_inventory: Mapping[str, Any],
    selection_inventory: Mapping[str, Any],
) -> A1IsolatedInterventionBatchLoadResult:
    a1 = _content_addressed_mapping(
        batch_result,
        _A1_RESULT_FIELDS,
        "a1_batch_loader_result_fields_mismatch",
        "a1_batch_loader_result_content_sha256_mismatch",
    )
    if (
        a1["schema_version"]
        != A1_ISOLATED_INTERVENTION_BATCH_RESULT_SCHEMA_V1
    ):
        _fail("a1_batch_loader_result_schema_unsupported")
    if a1["batch_scope"] != A1_ISOLATED_INTERVENTION_BATCH_SCOPE:
        _fail("a1_batch_loader_scope_invalid")
    batch_id = _required_text(a1["batch_id"], "a1_batch_id")
    evaluated_at = _validated_utc_timestamp(a1["evaluated_at"])
    input_manifest_sha256 = _sha256_text(
        a1["input_manifest_sha256"],
        "a1_input_manifest_sha256",
    )
    preregistration_file_sha256 = _sha256_text(
        a1["preregistration_file_sha256"],
        "a1_preregistration_file_sha256",
    )
    del preregistration_file_sha256
    try:
        preregistration = validate_a1_intervention_preregistration(
            _mapping(a1["preregistration"], "a1_preregistration")
        )
    except A1InterventionContractError as exc:
        _fail("a1_batch_loader_preregistration_invalid", exc.code)
    if preregistration.evaluation_seeds != ISOLATED_INTERVENTION_BATCH_SEEDS_V1:
        _fail("a1_batch_loader_preregistration_seed_scope_mismatch")

    bundle = _strict_mapping(
        a1["bundle"],
        _A1_BUNDLE_FIELDS,
        "a1_batch_loader_bundle_fields_mismatch",
    )
    bundle_manifest_sha256 = _sha256_text(
        bundle["manifest_sha256"],
        "a1_bundle_manifest_sha256",
    )
    policy_version = _required_text(
        bundle["policy_version"],
        "a1_policy_version",
    )
    state_dict_sha256 = _sha256_text(
        bundle["state_dict_sha256"],
        "a1_state_dict_sha256",
    )
    if preregistration.policy_artifact_sha256 != state_dict_sha256:
        _fail("a1_batch_loader_policy_artifact_sha256_mismatch")
    _validate_output_file_map(a1["output_files"])
    _validate_execution_boundary(
        a1["execution_boundary"],
        a1=True,
        context="$.a1_result.execution_boundary",
    )

    legacy_frames = _validate_legacy_result(
        legacy_result,
        batch_id=batch_id,
        evaluated_at=evaluated_at,
        input_manifest_sha256=input_manifest_sha256,
        bundle_manifest_sha256=bundle_manifest_sha256,
        policy_version=policy_version,
        state_dict_sha256=state_dict_sha256,
        preregistration=preregistration,
    )
    legacy_content_sha256 = _sha256_text(
        legacy_result["content_sha256"],
        "legacy_batch_result_content_sha256",
    )
    if (
        a1["legacy_batch_result_schema_version"]
        != ISOLATED_INTERVENTION_BATCH_RESULT_SCHEMA_V1
        or a1["legacy_batch_result_schema_version"]
        != legacy_result["schema_version"]
        or _sha256_text(
            a1["legacy_batch_result_content_sha256"],
            "a1_legacy_batch_result_content_sha256",
        )
        != legacy_content_sha256
    ):
        _fail("a1_batch_loader_legacy_result_summary_mismatch")

    candidate_records = _validate_candidate_inventory(
        candidate_inventory,
        batch_id=batch_id,
        preregistration=preregistration,
        legacy_frames=legacy_frames,
    )
    candidates_by_seed: dict[int, tuple[Mapping[str, Any], ...]] = {}
    for seed in ISOLATED_INTERVENTION_BATCH_SEEDS_V1:
        candidates_by_seed[seed] = tuple(
            item for item in candidate_records if item["seed"] == seed
        )

    selection_records = _validate_selection_inventory(
        selection_inventory,
        batch_id=batch_id,
        preregistration=preregistration,
        candidates_by_seed=candidates_by_seed,
    )
    _validate_batch_contracts(
        a1,
        candidate_inventory=candidate_inventory,
        selection_inventory=selection_inventory,
        candidates=candidate_records,
        selections=selection_records,
    )
    return A1IsolatedInterventionBatchLoadResult(
        output_directory=output_directory,
        batch_result=a1,
        legacy_result=legacy_result,
        candidate_inventory=candidate_inventory,
        selection_inventory=selection_inventory,
        candidates=candidate_records,
        selections=selection_records,
        file_sha256s=dict(file_sha256s),
    )


def _validate_output_file_map(value: Any) -> None:
    item = _strict_mapping(
        value,
        _A1_OUTPUT_FILE_FIELDS,
        "a1_batch_loader_output_file_fields_mismatch",
    )
    expected = {
        "legacy_result": BATCH_RESULT_FILENAME,
        "legacy_per_seed": BATCH_PER_SEED_FILENAME,
        "legacy_report": BATCH_REPORT_FILENAME,
        "a1_result": A1_BATCH_RESULT_FILENAME,
        "a1_candidates": A1_BATCH_CANDIDATES_FILENAME,
        "a1_selections": A1_BATCH_SELECTIONS_FILENAME,
        "checksums": BATCH_CHECKSUMS_FILENAME,
    }
    if dict(item) != expected:
        _fail("a1_batch_loader_output_layout_invalid")


def _validate_legacy_result(
    value: Mapping[str, Any],
    *,
    batch_id: str,
    evaluated_at: str,
    input_manifest_sha256: str,
    bundle_manifest_sha256: str,
    policy_version: str,
    state_dict_sha256: str,
    preregistration: A1InterventionPreRegistration,
) -> dict[tuple[int, int], Mapping[str, Any]]:
    item = _content_addressed_mapping(
        value,
        _LEGACY_RESULT_FIELDS,
        "a1_batch_loader_legacy_fields_mismatch",
        "a1_batch_loader_legacy_content_sha256_mismatch",
    )
    if item["schema_version"] != ISOLATED_INTERVENTION_BATCH_RESULT_SCHEMA_V1:
        _fail("a1_batch_loader_legacy_schema_unsupported")
    if (
        item["batch_scope"] != ISOLATED_INTERVENTION_BATCH_SCOPE
        or item["batch_id"] != batch_id
        or _validated_utc_timestamp(item["evaluated_at"]) != evaluated_at
        or _sha256_text(
            item["input_manifest_sha256"],
            "legacy_input_manifest_sha256",
        )
        != input_manifest_sha256
        or item["split"] != "test"
    ):
        _fail("a1_batch_loader_legacy_lineage_mismatch")

    source = _strict_mapping(
        item["source"],
        _LEGACY_SOURCE_FIELDS,
        "a1_batch_loader_legacy_source_fields_mismatch",
    )
    commit = _required_text(
        source["repository_git_commit"],
        "legacy_repository_git_commit",
    )
    if (
        len(commit) != 40
        or any(character not in "0123456789abcdef" for character in commit)
        or source["worktree_state"] != "clean"
    ):
        _fail("a1_batch_loader_legacy_source_invalid")

    bundle = _strict_mapping(
        item["bundle"],
        _A1_BUNDLE_FIELDS,
        "a1_batch_loader_legacy_bundle_fields_mismatch",
    )
    if (
        _sha256_text(
            bundle["manifest_sha256"],
            "legacy_bundle_manifest_sha256",
        )
        != bundle_manifest_sha256
        or _required_text(
            bundle["policy_version"],
            "legacy_policy_version",
        )
        != policy_version
        or _sha256_text(
            bundle["state_dict_sha256"],
            "legacy_state_dict_sha256",
        )
        != state_dict_sha256
    ):
        _fail("a1_batch_loader_bundle_summary_mismatch")

    configuration = _strict_mapping(
        item["configuration"],
        _LEGACY_CONFIGURATION_FIELDS,
        "a1_batch_loader_configuration_fields_mismatch",
    )
    _sha256_text(
        configuration["planner_config_sha256"],
        "legacy_planner_config_sha256",
    )
    _sha256_text(
        configuration["cost_weights_sha256"],
        "legacy_cost_weights_sha256",
    )
    _validate_execution_boundary(
        item["execution_boundary"],
        a1=False,
        context="$.legacy_result.execution_boundary",
    )

    raw_seeds = _strict_sequence(item["seeds"], "legacy_seeds")
    if len(raw_seeds) != len(ISOLATED_INTERVENTION_BATCH_SEEDS_V1):
        _fail("a1_batch_loader_legacy_seed_inventory_invalid")
    frames_by_key: dict[tuple[int, int], Mapping[str, Any]] = {}
    eligible_seed_count = 0
    for expected_seed, raw_seed in zip(
        ISOLATED_INTERVENTION_BATCH_SEEDS_V1,
        raw_seeds,
        strict=True,
    ):
        seed_item = _validate_legacy_seed(
            raw_seed,
            expected_seed=expected_seed,
            preregistration=preregistration,
        )
        if seed_item["status"] == "eligible_selected":
            eligible_seed_count += 1
        for frame in seed_item["frames"]:
            key = (expected_seed, frame["sequence_index"])
            if key in frames_by_key:
                _fail("a1_batch_loader_legacy_frame_duplicate")
            frames_by_key[key] = frame

    seed_contract = _strict_mapping(
        item["seed_contract"],
        _LEGACY_SEED_CONTRACT_FIELDS,
        "a1_batch_loader_seed_contract_fields_mismatch",
    )
    expected_seed_values = tuple(
        _nonnegative_int(value, "legacy_expected_seed")
        for value in _strict_sequence(
            seed_contract["expected_seeds"],
            "legacy_expected_seeds",
        )
    )
    seed_count = _nonnegative_int(
        seed_contract["seed_count"],
        "legacy_seed_count",
    )
    declared_eligible = _nonnegative_int(
        seed_contract["eligible_seed_count"],
        "legacy_eligible_seed_count",
    )
    declared_unavailable = _nonnegative_int(
        seed_contract["unavailable_seed_count"],
        "legacy_unavailable_seed_count",
    )
    if (
        expected_seed_values != ISOLATED_INTERVENTION_BATCH_SEEDS_V1
        or seed_count != len(raw_seeds)
        or declared_eligible != eligible_seed_count
        or declared_unavailable != len(raw_seeds) - eligible_seed_count
        or declared_eligible + declared_unavailable != seed_count
    ):
        _fail("a1_batch_loader_seed_contract_mismatch")
    return frames_by_key


def _validate_legacy_seed(
    value: Any,
    *,
    expected_seed: int,
    preregistration: A1InterventionPreRegistration,
) -> Mapping[str, Any]:
    item = _strict_mapping(
        value,
        _LEGACY_SEED_FIELDS,
        "a1_batch_loader_legacy_seed_fields_mismatch",
    )
    if _nonnegative_int(item["seed"], "legacy_seed") != expected_seed:
        _fail("a1_batch_loader_legacy_seed_order_invalid")
    raw_frames = _strict_sequence(item["frames"], "legacy_seed_frames")
    if not raw_frames:
        _fail("a1_batch_loader_legacy_frame_inventory_empty")
    frames: list[Mapping[str, Any]] = []
    previous_sequence = -1
    previous_timestamp = -1.0
    for raw_frame in raw_frames:
        frame = _validate_legacy_frame(
            raw_frame,
            preregistration=preregistration,
        )
        sequence_index = frame["sequence_index"]
        timestamp_s = frame["timestamp_s"]
        if (
            sequence_index <= previous_sequence
            or timestamp_s <= previous_timestamp
        ):
            _fail("a1_batch_loader_legacy_frame_order_invalid")
        previous_sequence = sequence_index
        previous_timestamp = timestamp_s
        frames.append(frame)

    frame_count = _nonnegative_int(item["frame_count"], "legacy_frame_count")
    eligible_count = sum(frame["eligible"] for frame in frames)
    if (
        frame_count != len(frames)
        or _nonnegative_int(
            item["eligible_frame_count"],
            "legacy_eligible_frame_count",
        )
        != eligible_count
        or _nonnegative_int(
            item["binding_difference_count"],
            "legacy_binding_difference_count",
        )
        != sum(frame["binding_change_count"] for frame in frames)
    ):
        _fail("a1_batch_loader_legacy_frame_count_mismatch")

    bundle = _strict_mapping(
        item["bundle"],
        _LEGACY_SEED_BUNDLE_FIELDS,
        "a1_batch_loader_seed_bundle_fields_mismatch",
    )
    fallback_reasons = tuple(
        _required_text(value, "legacy_fallback_reason")
        for value in _strict_sequence(
            bundle["fallback_reasons"],
            "legacy_fallback_reasons",
        )
    )
    expected_fallback_reasons = tuple(
        sorted(
            {
                frame["fallback_reason"]
                for frame in frames
                if frame["fallback_reason"] is not None
            }
        )
    )
    if (
        _strict_bool(
            bundle["all_frames_loaded"],
            "legacy_all_frames_loaded",
        )
        != all(frame["bundle_loaded"] for frame in frames)
        or _nonnegative_int(
            bundle["applied_frame_count"],
            "legacy_applied_frame_count",
        )
        != sum(frame["learning_cost_applied"] for frame in frames)
        or _nonnegative_int(
            bundle["fallback_frame_count"],
            "legacy_fallback_frame_count",
        )
        != sum(frame["rule_fallback_applied"] for frame in frames)
        or fallback_reasons != expected_fallback_reasons
    ):
        _fail("a1_batch_loader_seed_bundle_summary_mismatch")

    safety = _strict_mapping(
        item["safety"],
        _LEGACY_SAFETY_FIELDS,
        "a1_batch_loader_seed_safety_fields_mismatch",
    )
    if (
        _nonnegative_int(
            safety["rule_hard_violation_count"],
            "legacy_rule_hard_violation_count",
        )
        != sum(frame["rule_hard_violation_count"] for frame in frames)
        or _nonnegative_int(
            safety["treatment_hard_violation_count"],
            "legacy_treatment_hard_violation_count",
        )
        != sum(frame["treatment_hard_violation_count"] for frame in frames)
        or _nonnegative_int(
            safety["global_track_id_rewrite_count"],
            "legacy_global_track_id_rewrite_count",
        )
        != 0
    ):
        _fail("a1_batch_loader_seed_safety_summary_mismatch")
    _validate_execution_boundary(
        item["execution_boundary"],
        a1=False,
        context=f"$.legacy_result.seeds[{expected_seed}].execution_boundary",
    )

    first_eligible = next(
        (frame for frame in frames if frame["eligible"]),
        None,
    )
    status = _required_text(item["status"], "legacy_seed_status")
    unavailable_reason = item["unavailable_reason"]
    if first_eligible is None:
        if status != "unavailable" or unavailable_reason != "no_eligible_frame":
            _fail("a1_batch_loader_legacy_seed_status_mismatch")
        if item["first_eligible"] is not None:
            _fail("a1_batch_loader_legacy_first_eligible_invalid")
    else:
        if status != "eligible_selected" or unavailable_reason is not None:
            _fail("a1_batch_loader_legacy_seed_status_mismatch")
        first = _strict_mapping(
            item["first_eligible"],
            _LEGACY_FIRST_ELIGIBLE_FIELDS,
            "a1_batch_loader_first_eligible_fields_mismatch",
        )
        if (
            _nonnegative_int(
                first["sequence_index"],
                "legacy_first_eligible_sequence_index",
            )
            != first_eligible["sequence_index"]
            or _finite_nonnegative(
                first["timestamp_s"],
                "legacy_first_eligible_timestamp_s",
            )
            != first_eligible["timestamp_s"]
            or _sha256_text(
                first["replay_sha256"],
                "legacy_first_eligible_replay_sha256",
            )
            != first_eligible["replay_sha256"]
            or _sha256_text(
                first["evidence_sha256"],
                "legacy_first_eligible_evidence_sha256",
            )
            != first_eligible["evidence_sha256"]
        ):
            _fail("a1_batch_loader_legacy_first_eligible_mismatch")
    return {**item, "frames": tuple(frames)}


def _validate_legacy_frame(
    value: Any,
    *,
    preregistration: A1InterventionPreRegistration,
) -> Mapping[str, Any]:
    item = _strict_mapping(
        value,
        _LEGACY_FRAME_FIELDS,
        "a1_batch_loader_legacy_frame_fields_mismatch",
    )
    if (
        item["schema_version"]
        != ISOLATED_INTERVENTION_BATCH_FRAME_SUMMARY_SCHEMA_V1
    ):
        _fail("a1_batch_loader_legacy_frame_schema_unsupported")
    sequence_index = _nonnegative_int(
        item["sequence_index"],
        "legacy_frame_sequence_index",
    )
    timestamp_s = _finite_nonnegative(
        item["timestamp_s"],
        "legacy_frame_timestamp_s",
    )
    if not (
        preregistration.sequence_index_min
        <= sequence_index
        <= preregistration.sequence_index_max
        and preregistration.timestamp_s_min
        <= timestamp_s
        <= preregistration.timestamp_s_max
    ):
        _fail("a1_batch_loader_frame_outside_preregistration")
    _required_text(item["input_path"], "legacy_frame_input_path")
    for field in (
        "input_file_sha256",
        "input_content_sha256",
        "replay_sha256",
        "evidence_sha256",
    ):
        _sha256_text(item[field], f"legacy_frame_{field}")
    for field in (
        "eligible",
        "bundle_loaded",
        "learning_cost_applied",
        "rule_fallback_applied",
    ):
        _strict_bool(item[field], f"legacy_frame_{field}")
    _text_sequence(item["reason_codes"], "legacy_frame_reason_codes")
    if item["fallback_reason"] is not None:
        _required_text(item["fallback_reason"], "legacy_frame_fallback_reason")
    for field in (
        "binding_change_count",
        "rule_hard_violation_count",
        "treatment_hard_violation_count",
    ):
        _nonnegative_int(item[field], f"legacy_frame_{field}")
    _validate_execution_boundary(
        item["execution_boundary"],
        a1=False,
        context="$.legacy_result.frame.execution_boundary",
    )
    return item


def _validate_candidate_inventory(
    value: Mapping[str, Any],
    *,
    batch_id: str,
    preregistration: A1InterventionPreRegistration,
    legacy_frames: Mapping[tuple[int, int], Mapping[str, Any]],
) -> tuple[Mapping[str, Any], ...]:
    item = _content_addressed_mapping(
        value,
        _INVENTORY_FIELDS,
        "a1_batch_loader_candidate_inventory_fields_mismatch",
        "a1_batch_loader_candidate_inventory_sha256_mismatch",
    )
    if (
        item["schema_version"]
        != A1_ISOLATED_INTERVENTION_CANDIDATE_INVENTORY_SCHEMA_V1
    ):
        _fail("a1_batch_loader_candidate_inventory_schema_unsupported")
    _validate_inventory_lineage(
        item,
        batch_id=batch_id,
        preregistration=preregistration,
    )
    raw_records = _strict_sequence(
        item["records"],
        "a1_candidate_records",
    )
    if _nonnegative_int(
        item["record_count"],
        "a1_candidate_record_count",
    ) != len(raw_records):
        _fail("a1_batch_loader_candidate_record_count_mismatch")

    records: list[Mapping[str, Any]] = []
    record_keys: list[tuple[int, int]] = []
    seen_keys: set[tuple[int, int]] = set()
    seen_digests: set[str] = set()
    previous_by_seed: dict[int, tuple[int, float]] = {}
    for raw_record in raw_records:
        record = _validate_candidate_record(
            raw_record,
            batch_id=batch_id,
            preregistration=preregistration,
        )
        seed = record["seed"]
        key = (seed, record["sequence_index"])
        if key in seen_keys or record["content_sha256"] in seen_digests:
            _fail("a1_batch_loader_candidate_inventory_duplicate")
        seen_keys.add(key)
        record_keys.append(key)
        seen_digests.add(record["content_sha256"])
        previous = previous_by_seed.get(seed)
        if previous is not None and (
            record["sequence_index"] <= previous[0]
            or record["timestamp_s"] <= previous[1]
        ):
            _fail("a1_batch_loader_candidate_history_not_ordered")
        previous_by_seed[seed] = (
            record["sequence_index"],
            record["timestamp_s"],
        )
        legacy = legacy_frames.get(key)
        if legacy is None:
            _fail("a1_batch_loader_candidate_frame_missing")
        if (
            record["timestamp_s"] != legacy["timestamp_s"]
            or record["input_path"] != legacy["input_path"]
            or record["input_file_sha256"] != legacy["input_file_sha256"]
            or record["input_content_sha256"]
            != legacy["input_content_sha256"]
            or record["stable_replay_sha256"] != legacy["replay_sha256"]
            or record["stable_eligibility_sha256"]
            != legacy["evidence_sha256"]
        ):
            _fail("a1_batch_loader_candidate_frame_summary_mismatch")
        records.append(record)
    if (
        seen_keys != set(legacy_frames)
        or tuple(record_keys) != tuple(legacy_frames)
    ):
        _fail("a1_batch_loader_candidate_frame_inventory_mismatch")
    return tuple(records)


def _validate_candidate_record(
    value: Any,
    *,
    batch_id: str,
    preregistration: A1InterventionPreRegistration,
) -> Mapping[str, Any]:
    item = _content_addressed_mapping(
        value,
        _CANDIDATE_FIELDS,
        "a1_batch_loader_candidate_fields_mismatch",
        "a1_batch_loader_candidate_content_sha256_mismatch",
    )
    if (
        item["schema_version"]
        != A1_ISOLATED_INTERVENTION_CANDIDATE_SCHEMA_V1
        or item["evidence_kind"] != "a1-isolated-intervention-candidate"
    ):
        _fail("a1_batch_loader_candidate_schema_or_kind_invalid")
    if (
        item["batch_id"] != batch_id
        or item["registration_id"] != preregistration.registration_id
        or _sha256_text(
            item["preregistration_sha256"],
            "a1_candidate_preregistration_sha256",
        )
        != preregistration.content_sha256
    ):
        _fail("a1_batch_loader_candidate_lineage_mismatch")
    seed = _nonnegative_int(item["seed"], "a1_candidate_seed")
    if seed not in ISOLATED_INTERVENTION_BATCH_SEEDS_V1:
        _fail("a1_batch_loader_candidate_seed_outside_scope")
    sequence_index = _nonnegative_int(
        item["sequence_index"],
        "a1_candidate_sequence_index",
    )
    timestamp_s = _finite_nonnegative(
        item["timestamp_s"],
        "a1_candidate_timestamp_s",
    )
    if not (
        preregistration.sequence_index_min
        <= sequence_index
        <= preregistration.sequence_index_max
        and preregistration.timestamp_s_min
        <= timestamp_s
        <= preregistration.timestamp_s_max
    ):
        _fail("a1_batch_loader_candidate_outside_preregistration")
    _required_text(item["input_path"], "a1_candidate_input_path")
    for field in (
        "input_file_sha256",
        "input_content_sha256",
        "stable_replay_sha256",
        "stable_eligibility_sha256",
        "rule_binding_sha256",
        "treatment_binding_sha256",
        "policy_evaluation_semantics_sha256",
    ):
        _sha256_text(item[field], f"a1_candidate_{field}")
    for field in (
        "policy_evaluated",
        "cost_correction_accepted",
        "assignment_changed",
        "near_competitive",
        "selected_for_paired_evaluation",
        "version_contract_valid",
        "plan_published",
        "runtime_ack",
        "physical_window_available",
        "r0_pair_available",
    ):
        _strict_bool(item[field], f"a1_candidate_{field}")
    if (
        item["plan_published"]
        or item["runtime_ack"]
        or item["physical_window_available"]
        or item["r0_pair_available"]
    ):
        _fail("a1_batch_loader_candidate_runtime_stage_forbidden")

    correction = _finite_nonnegative(
        item["max_abs_cost_correction"],
        "a1_candidate_max_abs_cost_correction",
    )
    if correction > preregistration.max_abs_cost_correction:
        _fail("a1_batch_loader_candidate_cost_correction_outside_scope")
    scores = (
        _optional_finite(item["rule_basis_score"], "rule_basis_score"),
        _optional_finite(
            item["treatment_rule_basis_score"],
            "treatment_rule_basis_score",
        ),
        _optional_nonnegative_finite(
            item["absolute_rule_cost_difference"],
            "absolute_rule_cost_difference",
        ),
        _optional_nonnegative_finite(
            item["relative_rule_cost_difference"],
            "relative_rule_cost_difference",
        ),
    )
    if any(value is None for value in scores) and any(
        value is not None for value in scores
    ):
        _fail("a1_batch_loader_candidate_rule_cost_basis_partial")
    for field in (
        "rule_unmet_demand_slots",
        "treatment_unmet_demand_slots",
        "rule_unmet_high_threat_slots",
        "treatment_unmet_high_threat_slots",
    ):
        _nonnegative_int(item[field], f"a1_candidate_{field}")
    previous_version = _nonnegative_int(
        item["previous_plan_version"],
        "a1_candidate_previous_plan_version",
    )
    rule_version = _nonnegative_int(
        item["rule_plan_version"],
        "a1_candidate_rule_plan_version",
    )
    treatment_version = _nonnegative_int(
        item["treatment_plan_version"],
        "a1_candidate_treatment_plan_version",
    )
    if (
        rule_version not in {previous_version, previous_version + 1}
        or treatment_version not in {previous_version, previous_version + 1}
        or (
            item["version_contract_valid"]
            and item["assignment_changed"]
            and treatment_version != previous_version + 1
        )
    ):
        _fail("a1_batch_loader_candidate_plan_version_lineage_invalid")
    if item["assignment_changed"] != (
        item["rule_binding_sha256"] != item["treatment_binding_sha256"]
    ):
        _fail("a1_batch_loader_candidate_binding_change_mismatch")
    reasons = _text_sequence(
        item["reason_codes"],
        "a1_candidate_reason_codes",
        require_nonempty=True,
        require_unique=True,
    )
    if any(
        reason not in A1_INTERVENTION_CANDIDATE_REASON_CODES
        for reason in reasons
    ):
        _fail("a1_batch_loader_candidate_reason_code_unsupported")
    if item["selected_for_paired_evaluation"]:
        if (
            not item["policy_evaluated"]
            or not item["cost_correction_accepted"]
            or not item["assignment_changed"]
            or not item["near_competitive"]
            or not item["version_contract_valid"]
            or reasons != ("selected",)
            or scores[2] is None
            or scores[2] > preregistration.max_rule_cost_difference
            or scores[3] is None
            or scores[3]
            > preregistration.max_relative_rule_cost_difference
            or item["treatment_unmet_demand_slots"]
            > item["rule_unmet_demand_slots"]
            or item["treatment_unmet_high_threat_slots"]
            > item["rule_unmet_high_threat_slots"]
        ):
            _fail("a1_batch_loader_candidate_selection_stage_invalid")
    _validate_candidate_normalization(item["normalization"])
    _validate_execution_boundary(
        item["execution_boundary"],
        a1=True,
        context="$.candidate.execution_boundary",
    )
    return item


def _validate_candidate_normalization(value: Any) -> None:
    item = _strict_mapping(
        value,
        _CANDIDATE_NORMALIZATION_FIELDS,
        "a1_batch_loader_candidate_normalization_fields_mismatch",
    )
    excluded = tuple(
        _required_text(value, "a1_candidate_excluded_field")
        for value in _strict_sequence(
            item["excluded_run_local_fields"],
            "a1_candidate_excluded_run_local_fields",
        )
    )
    if (
        item["schema_version"]
        != "d3.a1-isolated-identity-normalization.v1"
        or excluded
        != (
            "plan_id",
            "plan_payload_sha256",
            "candidate_runtime_content_sha256",
            "learning_inference_elapsed_s",
        )
        or _strict_bool(
            item["binding_identity_preserved"],
            "a1_candidate_binding_identity_preserved",
        )
        is not True
        or _strict_bool(
            item["runtime_publication_evidence"],
            "a1_candidate_runtime_publication_evidence",
        )
        is not False
    ):
        _fail("a1_batch_loader_candidate_normalization_invalid")


def _validate_selection_inventory(
    value: Mapping[str, Any],
    *,
    batch_id: str,
    preregistration: A1InterventionPreRegistration,
    candidates_by_seed: Mapping[int, tuple[Mapping[str, Any], ...]],
) -> tuple[Mapping[str, Any], ...]:
    item = _content_addressed_mapping(
        value,
        _INVENTORY_FIELDS,
        "a1_batch_loader_selection_inventory_fields_mismatch",
        "a1_batch_loader_selection_inventory_sha256_mismatch",
    )
    if (
        item["schema_version"]
        != A1_ISOLATED_INTERVENTION_SELECTION_INVENTORY_SCHEMA_V1
    ):
        _fail("a1_batch_loader_selection_inventory_schema_unsupported")
    _validate_inventory_lineage(
        item,
        batch_id=batch_id,
        preregistration=preregistration,
    )
    raw_records = _strict_sequence(
        item["records"],
        "a1_selection_records",
    )
    if (
        _nonnegative_int(
            item["record_count"],
            "a1_selection_record_count",
        )
        != len(raw_records)
        or len(raw_records) != len(ISOLATED_INTERVENTION_BATCH_SEEDS_V1)
    ):
        _fail("a1_batch_loader_selection_record_count_mismatch")
    records: list[Mapping[str, Any]] = []
    for expected_seed, raw_record in zip(
        ISOLATED_INTERVENTION_BATCH_SEEDS_V1,
        raw_records,
        strict=True,
    ):
        records.append(
            _validate_selection_record(
                raw_record,
                batch_id=batch_id,
                preregistration=preregistration,
                expected_seed=expected_seed,
                candidates=candidates_by_seed[expected_seed],
            )
        )
    return tuple(records)


def _validate_selection_record(
    value: Any,
    *,
    batch_id: str,
    preregistration: A1InterventionPreRegistration,
    expected_seed: int,
    candidates: tuple[Mapping[str, Any], ...],
) -> Mapping[str, Any]:
    item = _content_addressed_mapping(
        value,
        _SELECTION_FIELDS,
        "a1_batch_loader_selection_fields_mismatch",
        "a1_batch_loader_selection_content_sha256_mismatch",
    )
    if (
        item["schema_version"]
        != A1_ISOLATED_INTERVENTION_SELECTION_SCHEMA_V1
        or item["evidence_kind"] != "a1-isolated-intervention-selection"
    ):
        _fail("a1_batch_loader_selection_schema_or_kind_invalid")
    if (
        item["batch_id"] != batch_id
        or item["registration_id"] != preregistration.registration_id
        or _sha256_text(
            item["preregistration_sha256"],
            "a1_selection_preregistration_sha256",
        )
        != preregistration.content_sha256
        or _nonnegative_int(item["seed"], "a1_selection_seed")
        != expected_seed
    ):
        _fail("a1_batch_loader_selection_lineage_mismatch")

    candidate_digests = tuple(
        _sha256_text(
            value,
            "a1_selection_candidate_content_sha256",
        )
        for value in _strict_sequence(
            item["candidate_content_sha256s"],
            "a1_selection_candidate_content_sha256s",
        )
    )
    expected_digests = tuple(
        candidate["content_sha256"] for candidate in candidates
    )
    count = _nonnegative_int(
        item["candidate_count"],
        "a1_selection_candidate_count",
    )
    stage_fields = (
        ("policy_evaluated_count", "policy_evaluated"),
        ("cost_correction_accepted_count", "cost_correction_accepted"),
        ("assignment_changed_count", "assignment_changed"),
        ("near_competitive_count", "near_competitive"),
    )
    if (
        count != len(candidates)
        or candidate_digests != expected_digests
        or len(candidate_digests) != len(set(candidate_digests))
    ):
        _fail("a1_batch_loader_selection_candidate_inventory_mismatch")
    for count_field, candidate_field in stage_fields:
        if _nonnegative_int(
            item[count_field],
            f"a1_selection_{count_field}",
        ) != sum(candidate[candidate_field] for candidate in candidates):
            _fail("a1_batch_loader_selection_stage_count_mismatch")
    history_sha256 = _sha256_text(
        item["candidate_history_sha256"],
        "a1_selection_candidate_history_sha256",
    )
    if history_sha256 != canonical_runtime_payload_sha256(
        {
            "registration_id": preregistration.registration_id,
            "seed": expected_seed,
            "candidate_content_sha256s": candidate_digests,
        }
    ):
        _fail("a1_batch_loader_selection_history_sha256_mismatch")

    selected = _strict_bool(item["selected"], "a1_selection_selected")
    expected_selected = next(
        (
            candidate
            for candidate in candidates
            if candidate["selected_for_paired_evaluation"]
        ),
        None,
    )
    reason = _required_text(item["reason"], "a1_selection_reason")
    if selected:
        if expected_selected is None or reason != "selected":
            _fail("a1_batch_loader_selected_decision_invalid")
        if (
            _sha256_text(
                item["selected_candidate_content_sha256"],
                "a1_selected_candidate_content_sha256",
            )
            != expected_selected["content_sha256"]
            or _nonnegative_int(
                item["selected_sequence_index"],
                "a1_selected_sequence_index",
            )
            != expected_selected["sequence_index"]
            or _finite_nonnegative(
                item["selected_timestamp_s"],
                "a1_selected_timestamp_s",
            )
            != expected_selected["timestamp_s"]
            or _sha256_text(
                item["selected_treatment_binding_sha256"],
                "a1_selected_treatment_binding_sha256",
            )
            != expected_selected["treatment_binding_sha256"]
        ):
            _fail("a1_batch_loader_selected_candidate_summary_mismatch")
    elif (
        expected_selected is not None
        or reason != "no_safe_discrete_intervention"
        or any(
            item[field] is not None
            for field in (
                "selected_candidate_content_sha256",
                "selected_sequence_index",
                "selected_timestamp_s",
                "selected_treatment_binding_sha256",
            )
        )
    ):
        _fail("a1_batch_loader_unselected_decision_invalid")

    for field in (
        "plan_published",
        "runtime_ack",
        "physical_window_available",
        "r0_pair_available",
    ):
        if _strict_bool(item[field], f"a1_selection_{field}"):
            _fail("a1_batch_loader_selection_runtime_stage_forbidden")
    _validate_selection_normalization(item["normalization"])
    _validate_execution_boundary(
        item["execution_boundary"],
        a1=True,
        context="$.selection.execution_boundary",
    )
    return item


def _validate_selection_normalization(value: Any) -> None:
    item = _strict_mapping(
        value,
        _SELECTION_NORMALIZATION_FIELDS,
        "a1_batch_loader_selection_normalization_fields_mismatch",
    )
    if (
        item["schema_version"]
        != "d3.a1-isolated-identity-normalization.v1"
        or _strict_bool(
            item["selection_uses_core_a1_decision"],
            "a1_selection_uses_core_a1_decision",
        )
        is not True
        or _strict_bool(
            item["stable_candidate_hashes_replace_runtime_candidate_hashes"],
            "a1_stable_candidate_hashes_replace_runtime_candidate_hashes",
        )
        is not True
        or _strict_bool(
            item["runtime_publication_evidence"],
            "a1_selection_runtime_publication_evidence",
        )
        is not False
    ):
        _fail("a1_batch_loader_selection_normalization_invalid")


def _validate_inventory_lineage(
    item: Mapping[str, Any],
    *,
    batch_id: str,
    preregistration: A1InterventionPreRegistration,
) -> None:
    if (
        item["batch_id"] != batch_id
        or item["registration_id"] != preregistration.registration_id
        or _sha256_text(
            item["preregistration_sha256"],
            "a1_inventory_preregistration_sha256",
        )
        != preregistration.content_sha256
    ):
        _fail("a1_batch_loader_inventory_lineage_mismatch")


def _validate_batch_contracts(
    a1: Mapping[str, Any],
    *,
    candidate_inventory: Mapping[str, Any],
    selection_inventory: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
    selections: Sequence[Mapping[str, Any]],
) -> None:
    candidate_contract = _strict_mapping(
        a1["candidate_contract"],
        _A1_CANDIDATE_CONTRACT_FIELDS,
        "a1_batch_loader_candidate_contract_fields_mismatch",
    )
    candidate_counts = {
        "candidate_count": len(candidates),
        "policy_evaluated_count": sum(
            item["policy_evaluated"] for item in candidates
        ),
        "cost_correction_accepted_count": sum(
            item["cost_correction_accepted"] for item in candidates
        ),
        "assignment_changed_count": sum(
            item["assignment_changed"] for item in candidates
        ),
        "near_competitive_count": sum(
            item["near_competitive"] for item in candidates
        ),
        "selected_candidate_count": sum(
            item["selected_for_paired_evaluation"] for item in candidates
        ),
    }
    if any(
        _nonnegative_int(
            candidate_contract[field],
            f"a1_candidate_contract_{field}",
        )
        != expected
        for field, expected in candidate_counts.items()
    ) or _sha256_text(
        candidate_contract["inventory_content_sha256"],
        "a1_candidate_inventory_content_sha256",
    ) != _sha256_text(
        candidate_inventory["content_sha256"],
        "candidate_inventory_content_sha256",
    ):
        _fail("a1_batch_loader_candidate_contract_mismatch")

    selection_contract = _strict_mapping(
        a1["selection_contract"],
        _A1_SELECTION_CONTRACT_FIELDS,
        "a1_batch_loader_selection_contract_fields_mismatch",
    )
    selected_count = sum(item["selected"] for item in selections)
    seed_count = len(selections)
    if (
        _nonnegative_int(
            selection_contract["seed_count"],
            "a1_selection_contract_seed_count",
        )
        != seed_count
        or _nonnegative_int(
            selection_contract["selected_seed_count"],
            "a1_selection_contract_selected_seed_count",
        )
        != selected_count
        or _nonnegative_int(
            selection_contract[
                "no_safe_discrete_intervention_seed_count"
            ],
            "a1_selection_contract_unselected_seed_count",
        )
        != seed_count - selected_count
        or _sha256_text(
            selection_contract["inventory_content_sha256"],
            "a1_selection_inventory_content_sha256",
        )
        != _sha256_text(
            selection_inventory["content_sha256"],
            "selection_inventory_content_sha256",
        )
    ):
        _fail("a1_batch_loader_selection_contract_mismatch")


def _validate_execution_boundary(
    value: Any,
    *,
    a1: bool,
    context: str,
) -> None:
    expected = _a1_execution_boundary() if a1 else _execution_boundary()
    item = _strict_mapping(
        value,
        frozenset(expected),
        "a1_batch_loader_execution_boundary_fields_mismatch",
    )
    for key, expected_value in expected.items():
        actual = item[key]
        if type(expected_value) is bool:
            actual = _strict_bool(actual, f"{context}.{key}")
        else:
            actual = _nonnegative_int(actual, f"{context}.{key}")
        if actual != expected_value:
            _fail("a1_batch_loader_authority_boundary_invalid", f"{context}.{key}")


def _content_addressed_mapping(
    value: Any,
    expected_fields: frozenset[str],
    fields_code: str,
    digest_code: str,
) -> Mapping[str, Any]:
    _assert_truth_free(value)
    _assert_all_finite(value)
    item = _strict_mapping(value, expected_fields, fields_code)
    claimed = _sha256_text(item["content_sha256"], "content_sha256")
    payload = dict(item)
    del payload["content_sha256"]
    if canonical_runtime_payload_sha256(payload) != claimed:
        _fail(digest_code)
    return item


def _strict_bool(value: Any, context: str) -> bool:
    if type(value) is not bool:
        _fail("a1_batch_loader_boolean_invalid", context)
    return value


def _optional_finite(value: Any, context: str) -> float | None:
    if value is None:
        return None
    return _finite_number(value, context)


def _optional_nonnegative_finite(
    value: Any,
    context: str,
) -> float | None:
    if value is None:
        return None
    return _finite_nonnegative(value, context)


def _text_sequence(
    value: Any,
    context: str,
    *,
    require_nonempty: bool = False,
    require_unique: bool = False,
) -> tuple[str, ...]:
    values = tuple(
        _required_text(item, context)
        for item in _strict_sequence(value, context)
    )
    if (require_nonempty and not values) or (
        require_unique and len(values) != len(set(values))
    ):
        _fail("a1_batch_loader_text_sequence_invalid", context)
    return values


__all__ = [
    "A1_ISOLATED_INTERVENTION_BATCH_LOADER_SCHEMA_V1",
    "A1IsolatedInterventionBatchLoadResult",
    "load_a1_isolated_intervention_batch",
    "validate_a1_isolated_intervention_batch",
]
