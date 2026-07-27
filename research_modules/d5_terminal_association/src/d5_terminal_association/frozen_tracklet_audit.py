"""Reproducible audit entrypoint for one frozen D5 tracklet GNN bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from typing import Any, Mapping, Sequence

from .tracklet_dataset import sha256_file, sha256_json
from .tracklet_heldout_evaluation import (
    HELDOUT_CONFIG_FILENAME,
    HELDOUT_EVALUATION_FILENAME,
    HELDOUT_EVALUATION_SCHEMA_VERSION,
    HELDOUT_MANIFEST_FILENAME,
    HeldoutEvaluationPolicy,
    evaluate_heldout_development_bundle,
)
from .tracklet_model_bundle import (
    CHECKSUMS_FILENAME,
    MANIFEST_FILENAME,
    WEIGHTS_FILENAME,
    load_tracklet_model_bundle,
)
from .tracklet_paired_shadow import (
    PAIRED_SHADOW_LINEAGE_FILENAME,
    PAIRED_SHADOW_LINEAGE_SCHEMA_VERSION,
    PAIRED_SHADOW_MARKDOWN_FILENAME,
    PAIRED_SHADOW_REPORT_FILENAME,
    PAIRED_SHADOW_SCHEMA_VERSION,
    PairedShadowInputSpec,
    run_tracklet_paired_shadow,
)


FROZEN_AUDIT_REFERENCE_SCHEMA_VERSION = "d5.frozen-tracklet-audit-reference.v1"
FROZEN_AUDIT_SUMMARY_SCHEMA_VERSION = "d5.frozen-tracklet-audit-summary.v1"
FROZEN_AUDIT_EVIDENCE_SCHEMA_VERSION = "d5.frozen-tracklet-audit-evidence.v1"
SUMMARY_FILENAME = "frozen_audit_summary.json"
SUMMARY_MARKDOWN_FILENAME = "FROZEN_GNN_AUDIT_REPORT_CN.md"
SUMMARY_CHECKSUMS_FILENAME = "SHA256SUMS"
AUDIT_EVIDENCE_FILENAME = "audit_evidence.json"
REGISTRY_REFERENCE_FILENAME = "frozen_bundle_reference.json"
SYNTHETIC_SHORTCUT_AUC_THRESHOLD = 0.995
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class FrozenTrackletAuditError(ValueError):
    """Stable validation error for the frozen audit entrypoint."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code)


def validate_frozen_reference(
    reference_path: str | Path,
    *,
    repository_root: str | Path,
) -> Mapping[str, Any]:
    """Validate one tracked reference against the ignored local bundle."""

    reference_file = Path(reference_path).resolve()
    root = Path(repository_root).resolve()
    reference = _read_json(reference_file)
    if reference.get("schema_version") != FROZEN_AUDIT_REFERENCE_SCHEMA_VERSION:
        _fail("reference_schema_mismatch", str(reference.get("schema_version")))
    relative = Path(str(reference.get("bundle_relative_path", "")))
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        _fail("bundle_relative_path_invalid", str(relative))
    bundle = (root / relative).resolve()
    try:
        bundle.relative_to(root)
    except ValueError:
        _fail("bundle_path_escape", str(bundle))
    expected = reference.get("expected_hashes")
    if not isinstance(expected, Mapping):
        _fail("expected_hashes_missing", str(reference_file))
    files = {
        "manifest_sha256": bundle / MANIFEST_FILENAME,
        "weights_sha256": bundle / WEIGHTS_FILENAME,
        "checksums_sha256": bundle / CHECKSUMS_FILENAME,
    }
    actual = {name: sha256_file(path) for name, path in files.items()}
    for name, digest in actual.items():
        expected_digest = str(expected.get(name, "")).strip().lower()
        if not _SHA256_PATTERN.fullmatch(expected_digest):
            _fail("reference_hash_invalid", name)
        if digest != expected_digest:
            _fail(f"{name}_mismatch", f"expected={expected_digest};actual={digest}")
    scorer = load_tracklet_model_bundle(bundle)
    admission = dict(scorer.manifest["admission"])
    if (
        admission.get("status") != "development_only_fail_closed"
        or admission.get("default_model") is not False
        or admission.get("g1_assist_eligible") is not False
    ):
        _fail("frozen_bundle_authority_invalid", str(admission))
    return {
        "reference_path": str(reference_file),
        "reference_sha256": sha256_file(reference_file),
        "bundle_dir": str(bundle),
        "model_id": str(reference.get("model_id", "")),
        "manifest_sha256": scorer.bundle_manifest_sha256,
        "weights_sha256": scorer.bundle_weights_sha256,
        "checksums_sha256": actual["checksums_sha256"],
        "admission": admission,
        "strict_load_passed": True,
    }


def run_frozen_tracklet_audit(
    reference_path: str | Path,
    heldout_corpus_dir: str | Path,
    output_dir: str | Path,
    *,
    repository_root: str | Path,
    evaluated_at_utc: str,
    device: str = "cpu",
    latency_repeats: int = 3,
    require_full_profile: bool = True,
) -> Mapping[str, Any]:
    """Run held-out inference and paired shadow against exactly one bundle."""

    destination = Path(output_dir).resolve()
    if destination.exists():
        _fail("audit_destination_exists", str(destination))
    timestamp = str(evaluated_at_utc).strip()
    if not timestamp:
        _fail("evaluated_at_missing", "evaluated_at_utc must be non-empty")
    frozen = validate_frozen_reference(
        reference_path,
        repository_root=repository_root,
    )
    corpus_root = Path(heldout_corpus_dir).resolve()
    corpus_manifest_path = corpus_root / HELDOUT_MANIFEST_FILENAME
    corpus_config_path = (
        corpus_root / "heldout_dataset" / HELDOUT_CONFIG_FILENAME
    )
    corpus_manifest = _read_json(corpus_manifest_path)
    destination.mkdir(parents=True)
    heldout_output = destination / "heldout_evaluation"
    paired_output = destination / "paired_shadow"
    try:
        heldout = evaluate_heldout_development_bundle(
            corpus_root,
            frozen["bundle_dir"],
            heldout_output,
            evaluated_at_utc=timestamp,
            policy=HeldoutEvaluationPolicy(
                device=device,
                latency_repeats=latency_repeats,
            ),
            require_full_profile=require_full_profile,
        )
        heldout_report_path = heldout_output / HELDOUT_EVALUATION_FILENAME
        paired = run_tracklet_paired_shadow(
            PairedShadowInputSpec(
                heldout_corpus_dir=corpus_root,
                bundle_dir=frozen["bundle_dir"],
                heldout_report_path=heldout_report_path,
                output_dir=paired_output,
                expected_corpus_manifest_sha256=sha256_file(
                    corpus_manifest_path
                ),
                expected_corpus_content_sha256=str(
                    corpus_manifest["content_sha256"]
                ),
                expected_corpus_config_sha256=sha256_file(corpus_config_path),
                expected_bundle_manifest_sha256=str(
                    frozen["manifest_sha256"]
                ),
                expected_bundle_weights_sha256=str(frozen["weights_sha256"]),
                expected_bundle_checksums_sha256=str(
                    frozen["checksums_sha256"]
                ),
                expected_heldout_report_sha256=sha256_file(
                    heldout_report_path
                ),
                expected_heldout_report_content_sha256=str(
                    heldout["content_sha256"]
                ),
                evaluated_at_utc=timestamp,
                device=device,
                require_full_profile=require_full_profile,
            )
        )
        summary = _summary(
            frozen,
            heldout,
            paired,
            evaluated_at_utc=timestamp,
            heldout_report_path=heldout_report_path,
            paired_output=paired_output,
        )
        _write_json(destination / SUMMARY_FILENAME, summary)
        (destination / SUMMARY_MARKDOWN_FILENAME).write_text(
            _render_summary(summary),
            encoding="utf-8",
        )
        _write_summary_checksums(destination)
        return summary
    except Exception:
        # Preserve evidence already written by fail-closed child evaluators.
        raise


def assemble_frozen_tracklet_registry(
    reference_path: str | Path,
    frozen_audit_summary_path: str | Path,
    heldout_report_path: str | Path,
    paired_shadow_report_path: str | Path,
    paired_lineage_path: str | Path,
    output_dir: str | Path,
    *,
    expected_reference_sha256: str,
    expected_frozen_audit_summary_sha256: str,
    expected_heldout_report_sha256: str,
    expected_paired_shadow_report_sha256: str,
    expected_paired_lineage_sha256: str,
) -> Mapping[str, Any]:
    """Assemble one hash-bound, shadow-only frozen registry atomically.

    The caller supplies an out-of-band digest for every producer artifact.
    Report status fields are recorded but never used as a substitute for
    schema, content-hash, lineage, authority, or input-immutability checks.
    """

    destination = Path(output_dir).expanduser().resolve()
    paths = {
        "reference": Path(reference_path).expanduser().resolve(),
        "summary": Path(frozen_audit_summary_path).expanduser().resolve(),
        "heldout": Path(heldout_report_path).expanduser().resolve(),
        "paired": Path(paired_shadow_report_path).expanduser().resolve(),
        "lineage": Path(paired_lineage_path).expanduser().resolve(),
    }
    expected_hashes = {
        "reference": _registry_sha256(
            expected_reference_sha256,
            "expected_reference_sha256",
        ),
        "summary": _registry_sha256(
            expected_frozen_audit_summary_sha256,
            "expected_frozen_audit_summary_sha256",
        ),
        "heldout": _registry_sha256(
            expected_heldout_report_sha256,
            "expected_heldout_report_sha256",
        ),
        "paired": _registry_sha256(
            expected_paired_shadow_report_sha256,
            "expected_paired_shadow_report_sha256",
        ),
        "lineage": _registry_sha256(
            expected_paired_lineage_sha256,
            "expected_paired_lineage_sha256",
        ),
    }
    _validate_registry_destination(destination)
    _validate_registry_output_separation(destination, tuple(paths.values()))

    reference = _load_registry_json_input(
        paths["reference"],
        expected_hashes["reference"],
        artifact_id="reference",
        require_content_sha256=False,
    )
    summary = _load_registry_json_input(
        paths["summary"],
        expected_hashes["summary"],
        artifact_id="summary",
        require_content_sha256=False,
    )
    heldout = _load_registry_json_input(
        paths["heldout"],
        expected_hashes["heldout"],
        artifact_id="heldout",
        require_content_sha256=True,
    )
    paired = _load_registry_json_input(
        paths["paired"],
        expected_hashes["paired"],
        artifact_id="paired",
        require_content_sha256=True,
    )
    lineage = _load_registry_lineage_input(
        paths["lineage"],
        expected_hashes["lineage"],
    )
    snapshots = {
        artifact["path"]: artifact["file_sha256"]
        for artifact in (reference, summary, heldout, paired, lineage)
    }
    normalized = _validate_frozen_registry_chain(
        reference,
        summary,
        heldout,
        paired,
        lineage,
    )
    evidence = _build_frozen_registry_evidence(
        reference,
        summary,
        heldout,
        paired,
        lineage,
        normalized,
    )
    report = _render_registry_report(evidence)
    _recheck_registry_inputs(snapshots)

    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.staging-",
            dir=destination.parent,
        )
    )
    published = False
    try:
        (staging / REGISTRY_REFERENCE_FILENAME).write_bytes(reference["raw"])
        _write_json(staging / AUDIT_EVIDENCE_FILENAME, evidence)
        (staging / SUMMARY_MARKDOWN_FILENAME).write_text(
            report,
            encoding="utf-8",
        )
        _write_registry_checksums(staging)
        _verify_registry_output(staging, reference["file_sha256"])
        _recheck_registry_inputs(snapshots)
        if destination.exists():
            _fail("registry_destination_exists", str(destination))
        os.rename(staging, destination)
        published = True
    finally:
        if not published:
            shutil.rmtree(staging, ignore_errors=True)
    return evidence


def _validate_frozen_registry_chain(
    reference: Mapping[str, Any],
    summary: Mapping[str, Any],
    heldout: Mapping[str, Any],
    paired: Mapping[str, Any],
    lineage: Mapping[str, Any],
) -> dict[str, Any]:
    reference_payload = reference["payload"]
    summary_payload = summary["payload"]
    heldout_payload = heldout["payload"]
    paired_payload = paired["payload"]

    _registry_schema(
        reference_payload,
        FROZEN_AUDIT_REFERENCE_SCHEMA_VERSION,
        "reference",
    )
    _registry_schema(
        summary_payload,
        FROZEN_AUDIT_SUMMARY_SCHEMA_VERSION,
        "summary",
    )
    _registry_schema(
        heldout_payload,
        HELDOUT_EVALUATION_SCHEMA_VERSION,
        "heldout",
    )
    _registry_schema(
        paired_payload,
        PAIRED_SHADOW_SCHEMA_VERSION,
        "paired",
    )

    reference_hashes = _registry_mapping(
        reference_payload.get("expected_hashes"),
        "reference.expected_hashes",
    )
    bundle_hashes = {
        name: _registry_sha256(
            reference_hashes.get(name),
            f"reference.expected_hashes.{name}",
        )
        for name in (
            "manifest_sha256",
            "weights_sha256",
            "checksums_sha256",
        )
    }
    _registry_all_false(
        _registry_mapping(
            reference_payload.get("admission_policy"),
            "reference.admission_policy",
        ),
        "reference.admission_policy",
    )

    summary_model = _registry_mapping(
        summary_payload.get("model"),
        "summary.model",
    )
    _registry_equal(
        summary_model.get("reference_sha256"),
        reference["file_sha256"],
        "summary_reference_sha256_mismatch",
    )
    _registry_equal(
        summary_model.get("model_id"),
        reference_payload.get("model_id"),
        "summary_model_id_mismatch",
    )
    for name, digest in bundle_hashes.items():
        _registry_equal(
            summary_model.get(name),
            digest,
            f"summary_bundle_{name}_mismatch",
        )
    if summary_model.get("strict_load_passed") is not True:
        _fail(
            "summary_strict_load_not_passed",
            str(summary_model.get("strict_load_passed")),
        )
    summary_admission = _registry_mapping(
        summary_model.get("admission"),
        "summary.model.admission",
    )
    if summary_admission.get("status") != "development_only_fail_closed":
        _fail(
            "summary_admission_status_invalid",
            str(summary_admission.get("status")),
        )
    _registry_false(
        summary_admission.get("default_model"),
        "summary.model.admission.default_model",
    )
    _registry_false(
        summary_admission.get("g1_assist_eligible"),
        "summary.model.admission.g1_assist_eligible",
    )
    _registry_all_false(
        _registry_mapping(
            summary_payload.get("authority"),
            "summary.authority",
        ),
        "summary.authority",
    )

    heldout_model = _registry_mapping(
        heldout_payload.get("development_model"),
        "heldout.development_model",
    )
    if heldout_model.get("admission_status") != "development_only_fail_closed":
        _fail(
            "heldout_admission_status_invalid",
            str(heldout_model.get("admission_status")),
        )
    _registry_equal(
        heldout_model.get("bundle_manifest_sha256"),
        bundle_hashes["manifest_sha256"],
        "heldout_bundle_manifest_mismatch",
    )
    _registry_equal(
        heldout_model.get("weights_sha256"),
        bundle_hashes["weights_sha256"],
        "heldout_bundle_weights_mismatch",
    )
    heldout_assessment = _registry_mapping(
        heldout_payload.get("heldout_assessment"),
        "heldout.heldout_assessment",
    )
    _registry_false(
        heldout_assessment.get("authority_enabled"),
        "heldout.heldout_assessment.authority_enabled",
    )
    _registry_false(
        heldout_assessment.get("g1_assist_eligible"),
        "heldout.heldout_assessment.g1_assist_eligible",
    )
    heldout_safety = _registry_mapping(
        heldout_payload.get("identity_and_truth_safety"),
        "heldout.identity_and_truth_safety",
    )
    _registry_false(
        heldout_safety.get("global_track_id_created_or_rebound"),
        "heldout.identity_and_truth_safety.global_track_id_created_or_rebound",
    )
    _registry_zero(
        heldout_safety.get("online_truth_feature_count"),
        "heldout.identity_and_truth_safety.online_truth_feature_count",
    )

    paired_authority = _registry_mapping(
        paired_payload.get("authority"),
        "paired.authority",
    )
    for field in ("g1", "assist", "authority", "runtime_default_changed"):
        _registry_false(
            paired_authority.get(field),
            f"paired.authority.{field}",
        )
    paired_assessment = _registry_mapping(
        paired_payload.get("paired_shadow_assessment"),
        "paired.paired_shadow_assessment",
    )
    for field in ("g1", "assist", "authority"):
        _registry_false(
            paired_assessment.get(field),
            f"paired.paired_shadow_assessment.{field}",
        )
    paired_safety = _registry_mapping(
        paired_payload.get("identity_and_truth_safety"),
        "paired.identity_and_truth_safety",
    )
    for field in (
        "g1",
        "assist",
        "authority",
        "global_track_id_created_or_rebound",
    ):
        _registry_false(
            paired_safety.get(field),
            f"paired.identity_and_truth_safety.{field}",
        )
    for field in (
        "global_track_id_rewrite_count",
        "online_truth_feature_count",
        "same_camera_mutual_exclusion_violation_count",
    ):
        _registry_zero(
            paired_safety.get(field),
            f"paired.identity_and_truth_safety.{field}",
        )
    frozen_decision = _registry_mapping(
        paired_payload.get("frozen_decision"),
        "paired.frozen_decision",
    )
    for field in (
        "candidate_gate_changed",
        "temperature_reestimated",
        "threshold_reselected",
        "weights_updated",
    ):
        _registry_false(
            frozen_decision.get(field),
            f"paired.frozen_decision.{field}",
        )
    if paired_payload.get("input_artifacts_unchanged") is not True:
        _fail(
            "paired_inputs_not_unchanged",
            str(paired_payload.get("input_artifacts_unchanged")),
        )

    before = _registry_mapping(
        paired_payload.get("input_hashes_before"),
        "paired.input_hashes_before",
    )
    after = _registry_mapping(
        paired_payload.get("input_hashes_after"),
        "paired.input_hashes_after",
    )
    if dict(before) != dict(after):
        _fail("paired_input_hashes_changed", "before != after")
    input_spec = _registry_mapping(
        paired_payload.get("input_spec"),
        "paired.input_spec",
    )
    input_spec_hashes = _registry_mapping(
        input_spec.get("expected_hashes"),
        "paired.input_spec.expected_hashes",
    )
    if dict(before) != dict(input_spec_hashes):
        _fail("paired_input_spec_hashes_mismatch", "expected_hashes != before")

    heldout_corpus = _registry_mapping(
        heldout_payload.get("heldout_corpus"),
        "heldout.heldout_corpus",
    )
    chain_hashes = {
        "bundle_manifest_sha256": bundle_hashes["manifest_sha256"],
        "bundle_weights_sha256": bundle_hashes["weights_sha256"],
        "bundle_checksums_sha256": bundle_hashes["checksums_sha256"],
        "corpus_manifest_sha256": _registry_sha256(
            heldout_corpus.get("manifest_sha256"),
            "heldout.heldout_corpus.manifest_sha256",
        ),
        "corpus_content_sha256": _registry_sha256(
            heldout_corpus.get("manifest_content_sha256"),
            "heldout.heldout_corpus.manifest_content_sha256",
        ),
        "corpus_config_sha256": _registry_sha256(
            before.get("corpus_config_sha256"),
            "paired.input_hashes_before.corpus_config_sha256",
        ),
        "heldout_report_sha256": heldout["file_sha256"],
        "heldout_report_content_sha256": heldout["content_sha256"],
    }
    for name, expected in chain_hashes.items():
        _registry_equal(
            before.get(name),
            expected,
            f"paired_input_{name}_mismatch",
        )

    heldout_binding = _registry_mapping(
        paired_payload.get("heldout_lineage_binding"),
        "paired.heldout_lineage_binding",
    )
    for name in (
        "bundle_manifest_sha256",
        "bundle_weights_sha256",
        "corpus_manifest_sha256",
        "corpus_content_sha256",
    ):
        _registry_equal(
            heldout_binding.get(name),
            chain_hashes[name],
            f"paired_lineage_{name}_mismatch",
        )
    if heldout_binding.get("report_used_for_predictions") is not False:
        _fail(
            "heldout_report_prediction_reuse_invalid",
            str(heldout_binding.get("report_used_for_predictions")),
        )

    summary_heldout = _registry_mapping(
        summary_payload.get("heldout"),
        "summary.heldout",
    )
    _registry_equal(
        summary_heldout.get("report_file_sha256"),
        heldout["file_sha256"],
        "summary_heldout_file_sha256_mismatch",
    )
    _registry_equal(
        summary_heldout.get("content_sha256"),
        heldout["content_sha256"],
        "summary_heldout_content_sha256_mismatch",
    )
    _registry_equal(
        summary_heldout.get("status"),
        heldout_assessment.get("status"),
        "summary_heldout_status_mismatch",
    )

    paired_lineage = _registry_mapping(
        paired_payload.get("paired_lineage"),
        "paired.paired_lineage",
    )
    _registry_equal(
        paired_lineage.get("schema_version"),
        PAIRED_SHADOW_LINEAGE_SCHEMA_VERSION,
        "paired_lineage_schema_mismatch",
    )
    _registry_equal(
        paired_lineage.get("sha256"),
        lineage["file_sha256"],
        "paired_lineage_sha256_mismatch",
    )
    _registry_equal(
        paired_lineage.get("record_count"),
        lineage["record_count"],
        "paired_lineage_record_count_mismatch",
    )
    _registry_equal(
        paired_lineage.get("filename"),
        _path_name(lineage["path"]),
        "paired_lineage_filename_mismatch",
    )

    summary_paired = _registry_mapping(
        summary_payload.get("paired_shadow"),
        "summary.paired_shadow",
    )
    _registry_equal(
        summary_paired.get("report_file_sha256"),
        paired["file_sha256"],
        "summary_paired_file_sha256_mismatch",
    )
    _registry_equal(
        summary_paired.get("content_sha256"),
        paired["content_sha256"],
        "summary_paired_content_sha256_mismatch",
    )
    _registry_equal(
        summary_paired.get("lineage_sha256"),
        lineage["file_sha256"],
        "summary_paired_lineage_sha256_mismatch",
    )
    _registry_equal(
        summary_paired.get("status"),
        paired_assessment.get("status"),
        "summary_paired_status_mismatch",
    )
    _registry_equal(
        summary_payload.get("status"),
        paired_payload.get("status"),
        "summary_paired_overall_status_mismatch",
    )
    for payload in (summary_payload, heldout_payload, paired_payload):
        evaluated = payload.get("evaluated_at_utc")
        if not isinstance(evaluated, str) or not evaluated.strip():
            _fail("evaluated_at_invalid", str(evaluated))
        _registry_equal(
            evaluated,
            summary_payload.get("evaluated_at_utc"),
            "evaluation_timestamp_mismatch",
        )

    totals = _registry_mapping(paired_payload.get("totals"), "paired.totals")
    catalog = _registry_mapping(
        summary_payload.get("catalog"),
        "summary.catalog",
    )
    for name in (
        "candidate_edge_count",
        "episode_count",
        "labeled_candidate_edge_count",
        "node_count",
        "scenario_scale_cell_count",
        "seed_count",
    ):
        value = _registry_nonnegative_int(totals.get(name), f"paired.totals.{name}")
        _registry_equal(
            catalog.get(name),
            value,
            f"summary_catalog_{name}_mismatch",
        )
    seeds = heldout_corpus.get("seed_values")
    if (
        not isinstance(seeds, list)
        or any(isinstance(seed, bool) or not isinstance(seed, int) for seed in seeds)
        or len(set(seeds)) != len(seeds)
    ):
        _fail("heldout_seed_values_invalid", str(seeds))
    _registry_equal(
        len(seeds),
        totals.get("seed_count"),
        "heldout_seed_count_mismatch",
    )
    _registry_equal(
        heldout_corpus.get("episode_count"),
        totals.get("episode_count"),
        "heldout_episode_count_mismatch",
    )
    _registry_equal(
        heldout_corpus.get("scenario_scale_cell_count"),
        totals.get("scenario_scale_cell_count"),
        "heldout_cell_count_mismatch",
    )
    _registry_equal(
        lineage["record_count"],
        totals.get("episode_count"),
        "lineage_episode_count_mismatch",
    )

    normalized_metrics = _normalized_registry_metrics(paired_payload)
    for name, value in normalized_metrics["summary_metrics"].items():
        _registry_equal(
            summary_paired.get(name),
            value,
            f"summary_metric_{name}_mismatch",
        )
    _registry_equal(
        summary_paired.get("robustness_profiles"),
        normalized_metrics["robustness_profiles"],
        "summary_robustness_profiles_mismatch",
    )
    _registry_equal(
        summary_paired.get("maximum_single_feature_auc"),
        normalized_metrics["summary_metrics"][
            "maximum_single_feature_auc"
        ],
        "summary_single_feature_auc_mismatch",
    )
    return {
        "bundle_hashes": bundle_hashes,
        "chain_hashes": chain_hashes,
        "catalog": totals,
        "seeds": list(seeds),
        "profile_version": str(heldout_corpus.get("profile_version", "")),
        **normalized_metrics,
    }


def _normalized_registry_metrics(
    paired: Mapping[str, Any],
) -> dict[str, Any]:
    overall = _registry_mapping(paired.get("overall"), "paired.overall")
    control = _registry_mapping(overall.get("control"), "paired.overall.control")
    model = _registry_mapping(overall.get("model"), "paired.overall.model")
    control_edge = _registry_mapping(
        control.get("edge"),
        "paired.overall.control.edge",
    )
    model_edge = _registry_mapping(
        model.get("edge"),
        "paired.overall.model.edge",
    )
    control_cluster = _registry_mapping(
        control.get("cluster_pairwise"),
        "paired.overall.control.cluster_pairwise",
    )
    model_cluster = _registry_mapping(
        model.get("cluster_pairwise"),
        "paired.overall.model.cluster_pairwise",
    )
    model_latency = _registry_mapping(
        model.get("latency_ms"),
        "paired.overall.model.latency_ms",
    )
    runtime = _registry_mapping(paired.get("runtime"), "paired.runtime")
    fallback = _registry_mapping(
        paired.get("runtime_fallback_probe"),
        "paired.runtime_fallback_probe",
    )
    diagnostics = _registry_mapping(
        paired.get("feature_label_diagnostics"),
        "paired.feature_label_diagnostics",
    )
    shortcut = _registry_mapping(
        diagnostics.get("maximum_single_feature_auc"),
        "paired.feature_label_diagnostics.maximum_single_feature_auc",
    )
    if shortcut.get("available") is not True:
        _fail(
            "single_feature_auc_unavailable",
            str(shortcut.get("available")),
        )
    shortcut_value = {
        "best_direction_auc": _registry_probability(
            shortcut.get("best_direction_auc"),
            "paired.maximum_single_feature_auc.best_direction_auc",
        ),
        "feature": _registry_nonempty_string(
            shortcut.get("feature"),
            "paired.maximum_single_feature_auc.feature",
        ),
    }

    robustness_payload = paired.get("robustness_profiles")
    if not isinstance(robustness_payload, list) or not robustness_payload:
        _fail("robustness_profiles_invalid", str(type(robustness_payload)))
    robustness: list[dict[str, Any]] = []
    for index, item in enumerate(robustness_payload):
        record = _registry_mapping(item, f"paired.robustness_profiles[{index}]")
        profile = _registry_mapping(
            record.get("profile"),
            f"paired.robustness_profiles[{index}].profile",
        )
        profile_model = _registry_mapping(
            record.get("model"),
            f"paired.robustness_profiles[{index}].model",
        )
        profile_edge = _registry_mapping(
            profile_model.get("edge"),
            f"paired.robustness_profiles[{index}].model.edge",
        )
        profile_cluster = _registry_mapping(
            profile_model.get("cluster_pairwise"),
            f"paired.robustness_profiles[{index}].model.cluster_pairwise",
        )
        robustness.append(
            {
                "profile_id": _registry_nonempty_string(
                    profile.get("profile_id"),
                    f"paired.robustness_profiles[{index}].profile.profile_id",
                ),
                "model_edge_f1": _registry_probability(
                    profile_edge.get("f1"),
                    f"paired.robustness_profiles[{index}].model.edge.f1",
                ),
                "model_cluster_f1": _registry_probability(
                    profile_cluster.get("f1"),
                    f"paired.robustness_profiles[{index}].model.cluster.f1",
                ),
                "model_cluster_false_merge_rate": _registry_probability(
                    profile_cluster.get("false_merge_rate"),
                    (
                        "paired.robustness_profiles"
                        f"[{index}].model.cluster.false_merge_rate"
                    ),
                ),
            }
        )

    shared = _registry_mapping(
        diagnostics.get("shared_global_track_count"),
        "paired.feature_label_diagnostics.shared_global_track_count",
    )
    near_deterministic = shared.get("near_deterministic")
    if not isinstance(near_deterministic, bool):
        _fail(
            "shared_global_track_near_deterministic_invalid",
            str(near_deterministic),
        )
    strata = _registry_mapping(
        shared.get("strata"),
        "paired.feature_label_diagnostics.shared_global_track_count.strata",
    )
    nonzero_shared_count = 0
    for stratum in ("1", "other"):
        record = _registry_mapping(
            strata.get(stratum),
            f"paired.shared_global_track_count.strata.{stratum}",
        )
        nonzero_shared_count += _registry_nonnegative_int(
            record.get("edge_count"),
            f"paired.shared_global_track_count.strata.{stratum}.edge_count",
        )

    summary_metrics = {
        "candidate_recall": _registry_probability(
            overall.get("candidate_recall"),
            "paired.overall.candidate_recall",
        ),
        "rule_edge_f1": _registry_probability(
            control_edge.get("f1"),
            "paired.overall.control.edge.f1",
        ),
        "model_edge_f1": _registry_probability(
            model_edge.get("f1"),
            "paired.overall.model.edge.f1",
        ),
        "rule_cluster_f1": _registry_probability(
            control_cluster.get("f1"),
            "paired.overall.control.cluster_pairwise.f1",
        ),
        "model_cluster_f1": _registry_probability(
            model_cluster.get("f1"),
            "paired.overall.model.cluster_pairwise.f1",
        ),
        "model_cluster_false_merge_rate": _registry_probability(
            model_cluster.get("false_merge_rate"),
            "paired.overall.model.cluster_pairwise.false_merge_rate",
        ),
        "model_latency_p50_ms": _registry_nonnegative_number(
            model_latency.get("scoring_p50"),
            "paired.overall.model.latency_ms.scoring_p50",
        ),
        "model_latency_p95_ms": _registry_nonnegative_number(
            model_latency.get("scoring_p95"),
            "paired.overall.model.latency_ms.scoring_p95",
        ),
        "peak_rss_mib": _registry_nonnegative_number(
            runtime.get("max_rss_mib"),
            "paired.runtime.max_rss_mib",
        ),
        "runtime_fallback_rate": _registry_probability(
            fallback.get("fallback_rate"),
            "paired.runtime_fallback_probe.fallback_rate",
        ),
        "maximum_single_feature_auc": dict(shortcut),
    }
    return {
        "summary_metrics": summary_metrics,
        "nominal_metrics": {
            name: value
            for name, value in summary_metrics.items()
            if name != "maximum_single_feature_auc"
        },
        "robustness_profiles": robustness,
        "single_feature_shortcut": shortcut_value,
        "shared_global_track_nonzero_edge_count": nonzero_shared_count,
        "shared_global_track_near_deterministic": near_deterministic,
    }


def _build_frozen_registry_evidence(
    reference: Mapping[str, Any],
    summary: Mapping[str, Any],
    heldout: Mapping[str, Any],
    paired: Mapping[str, Any],
    lineage: Mapping[str, Any],
    normalized: Mapping[str, Any],
) -> dict[str, Any]:
    reference_payload = reference["payload"]
    summary_payload = summary["payload"]
    heldout_payload = heldout["payload"]
    summary_paired = _registry_mapping(
        summary_payload.get("paired_shadow"),
        "summary.paired_shadow",
    )
    limitations = _derived_registry_limitations(normalized)
    catalog = {
        name: normalized["catalog"][name]
        for name in (
            "candidate_edge_count",
            "episode_count",
            "node_count",
            "scenario_scale_cell_count",
            "seed_count",
        )
    }
    catalog["seeds"] = list(normalized["seeds"])
    heldout_corpus = _registry_mapping(
        heldout_payload.get("heldout_corpus"),
        "heldout.heldout_corpus",
    )
    return {
        "schema_version": FROZEN_AUDIT_EVIDENCE_SCHEMA_VERSION,
        "evaluated_at_utc": summary_payload["evaluated_at_utc"],
        "status": "evidence_chain_closed_shadow_only",
        "frozen_model": {
            "admission_status": "development_only_fail_closed",
            "manifest_sha256": normalized["bundle_hashes"]["manifest_sha256"],
            "weights_sha256": normalized["bundle_hashes"]["weights_sha256"],
        },
        "heldout_input": {
            "config_sha256": normalized["chain_hashes"][
                "corpus_config_sha256"
            ],
            "manifest_content_sha256": heldout_corpus[
                "manifest_content_sha256"
            ],
            "manifest_sha256": heldout_corpus["manifest_sha256"],
            "profile_version": normalized["profile_version"],
        },
        "catalog": catalog,
        "nominal_metrics": dict(normalized["nominal_metrics"]),
        "robustness_profiles": list(normalized["robustness_profiles"]),
        "single_feature_shortcut": dict(
            normalized["single_feature_shortcut"]
        ),
        "output_hashes": {
            "heldout_evaluation_content_sha256": heldout["content_sha256"],
            "heldout_evaluation_file_sha256": heldout["file_sha256"],
            "paired_lineage_sha256": lineage["file_sha256"],
            "paired_markdown_sha256": _registry_sha256(
                summary_paired.get("markdown_sha256"),
                "summary.paired_shadow.markdown_sha256",
            ),
            "paired_report_content_sha256": paired["content_sha256"],
            "paired_report_file_sha256": paired["file_sha256"],
        },
        "authority": {
            "g1": False,
            "assist": False,
            "authority": False,
            "default_model_changed": False,
            "active_visual_ppo_started": False,
        },
        "limitations": limitations,
    }


def _derived_registry_limitations(
    normalized: Mapping[str, Any],
) -> list[str]:
    limitations = [
        "counterfactual_profiles_hold_candidate_graph_fixed",
        "d6_external_audit_required",
        "no_online_authority",
    ]
    auc = normalized["single_feature_shortcut"]["best_direction_auc"]
    if auc >= SYNTHETIC_SHORTCUT_AUC_THRESHOLD:
        limitations.insert(0, "synthetic_heldout_single_feature_shortcut")
    if (
        normalized["shared_global_track_nonzero_edge_count"] > 0
        and normalized["shared_global_track_near_deterministic"] is True
    ):
        limitations.append(
            "shared_global_track_count_near_deterministic_shortcut"
        )
    return limitations


def _summary_limitations(paired: Mapping[str, Any]) -> list[str]:
    limitations = [
        "counterfactual_profiles_hold_candidate_graph_fixed",
        "d6_external_audit_required",
        "no_online_authority",
    ]
    diagnostics = paired.get("feature_label_diagnostics")
    if not isinstance(diagnostics, Mapping):
        return limitations
    maximum = diagnostics.get("maximum_single_feature_auc")
    if isinstance(maximum, Mapping):
        auc = maximum.get("best_direction_auc")
        if (
            maximum.get("available") is True
            and isinstance(auc, (int, float))
            and not isinstance(auc, bool)
            and math.isfinite(float(auc))
            and float(auc) >= SYNTHETIC_SHORTCUT_AUC_THRESHOLD
        ):
            limitations.insert(
                0,
                "synthetic_heldout_single_feature_shortcut",
            )
    shared = diagnostics.get("shared_global_track_count")
    if isinstance(shared, Mapping) and shared.get("near_deterministic") is True:
        strata = shared.get("strata")
        if isinstance(strata, Mapping):
            nonzero_count = 0
            for stratum in ("1", "other"):
                record = strata.get(stratum)
                if isinstance(record, Mapping):
                    count = record.get("edge_count")
                    if isinstance(count, int) and not isinstance(count, bool):
                        nonzero_count += max(count, 0)
            if nonzero_count > 0:
                limitations.append(
                    "shared_global_track_count_near_deterministic_shortcut"
                )
    return limitations


def _render_registry_report(evidence: Mapping[str, Any]) -> str:
    model = evidence["frozen_model"]
    metrics = evidence["nominal_metrics"]
    shortcut = evidence["single_feature_shortcut"]
    catalog = evidence["catalog"]
    limitations = set(evidence["limitations"])
    lines = [
        "# D5 冻结图模型审计",
        "",
        "## 结论",
        "",
        (
            "冻结引用、保留集报告、成对影子报告和逐帧谱系已完成"
            "哈希与内容交叉校验。"
        ),
        (
            "该目录只构成外部审计输入。默认模型、图模型辅助、"
            "全局航迹标识和控制权限均保持关闭。"
        ),
        "",
        "## 数据与模型",
        "",
        f"- manifest SHA-256：`{model['manifest_sha256']}`。",
        f"- weights SHA-256：`{model['weights_sha256']}`。",
        f"- 未见种子：`{catalog['seed_count']}`；episode："
        f"`{catalog['episode_count']}`；场景规模单元："
        f"`{catalog['scenario_scale_cell_count']}`。",
        f"- 节点：`{catalog['node_count']}`；候选边："
        f"`{catalog['candidate_edge_count']}`。",
        "",
        "## 名义结果",
        "",
        "| 指标 | 结果 |",
        "| --- | ---: |",
        f"| 候选边召回率 | {_format_metric(metrics['candidate_recall'])} |",
        f"| 模型边 F1 | {_format_metric(metrics['model_edge_f1'])} |",
        f"| 模型聚类 F1 | {_format_metric(metrics['model_cluster_f1'])} |",
        (
            "| 模型聚类错误合并率 | "
            f"{_format_metric(metrics['model_cluster_false_merge_rate'])} |"
        ),
        (
            "| 模型推理 P50/P95 | "
            f"{_format_metric(metrics['model_latency_p50_ms'])}/"
            f"{_format_metric(metrics['model_latency_p95_ms'])} 毫秒 |"
        ),
        "",
        "## 扰动结果",
        "",
        "| 扰动 | 模型边 F1 | 模型簇 F1 | 错误合并率 |",
        "| --- | ---: | ---: | ---: |",
    ]
    for item in evidence["robustness_profiles"]:
        lines.append(
            f"| `{item['profile_id']}` | "
            f"{_format_metric(item['model_edge_f1'])} | "
            f"{_format_metric(item['model_cluster_f1'])} | "
            f"{_format_metric(item['model_cluster_false_merge_rate'])} |"
        )
    auc = shortcut["best_direction_auc"]
    if "synthetic_heldout_single_feature_shortcut" in limitations:
        auc_text = (
            f"最高单特征 AUC 为 `{_format_metric(auc)}`，达到 "
            f"`{SYNTHETIC_SHORTCUT_AUC_THRESHOLD:.3f}` 阈值，"
            "保留合成保留集单特征捷径阻断项。"
        )
    else:
        auc_text = (
            f"最高单特征 AUC 为 `{_format_metric(auc)}`，低于 "
            f"`{SYNTHETIC_SHORTCUT_AUC_THRESHOLD:.3f}` 阈值，"
            "不保留合成保留集单特征捷径阻断项。"
        )
    shared_text = (
        "非零共享全局航迹计数与标签呈近确定性关系，保留对应捷径阻断项。"
        if "shared_global_track_count_near_deterministic_shortcut"
        in limitations
        else "未发现非零共享全局航迹计数形成近确定性标签捷径。"
    )
    lines.extend(
        [
            "",
            "## 限制",
            "",
            auc_text,
            shared_text,
            (
                "扰动剖面固定候选图，只验证评分器稳定性。"
                "D6 外部审计完成前，模型继续保持影子状态。"
            ),
            "",
        ]
    )
    return "\n".join(lines)


def _load_registry_json_input(
    path: Path,
    expected_sha256: str,
    *,
    artifact_id: str,
    require_content_sha256: bool,
) -> dict[str, Any]:
    raw = _read_registry_bytes(path, artifact_id)
    actual_sha = hashlib.sha256(raw).hexdigest()
    if actual_sha != expected_sha256:
        _fail(
            f"input_sha256_mismatch.{artifact_id}",
            f"expected={expected_sha256};actual={actual_sha}",
        )
    try:
        payload = json.loads(
            raw.decode("utf-8"),
            parse_constant=lambda token: _reject_json_constant(token),
        )
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        _fail(f"input_json_invalid.{artifact_id}", str(path))
        raise AssertionError from exc
    if not isinstance(payload, dict):
        _fail(f"input_json_object_required.{artifact_id}", str(path))
    content_sha256 = None
    if require_content_sha256:
        content_sha256 = _registry_sha256(
            payload.get("content_sha256"),
            f"{artifact_id}.content_sha256",
        )
        unhashed = dict(payload)
        unhashed.pop("content_sha256", None)
        actual_content = sha256_json(unhashed)
        if content_sha256 != actual_content:
            _fail(
                f"input_content_sha256_mismatch.{artifact_id}",
                f"expected={content_sha256};actual={actual_content}",
            )
    return {
        "path": path,
        "raw": raw,
        "payload": payload,
        "file_sha256": actual_sha,
        "content_sha256": content_sha256,
    }


def _load_registry_lineage_input(
    path: Path,
    expected_sha256: str,
) -> dict[str, Any]:
    raw = _read_registry_bytes(path, "lineage")
    actual_sha = hashlib.sha256(raw).hexdigest()
    if actual_sha != expected_sha256:
        _fail(
            "input_sha256_mismatch.lineage",
            f"expected={expected_sha256};actual={actual_sha}",
        )
    records: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(raw.splitlines(), start=1):
        if not raw_line.strip():
            _fail("lineage_blank_line", str(line_number))
        try:
            value = json.loads(
                raw_line.decode("utf-8"),
                parse_constant=lambda token: _reject_json_constant(token),
            )
        except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
            _fail("lineage_json_invalid", str(line_number))
            raise AssertionError from exc
        if not isinstance(value, dict):
            _fail("lineage_json_object_required", str(line_number))
        _registry_schema(
            value,
            PAIRED_SHADOW_LINEAGE_SCHEMA_VERSION,
            f"lineage[{line_number}]",
        )
        records.append(value)
    if not records:
        _fail("lineage_empty", str(path))
    return {
        "path": path,
        "raw": raw,
        "file_sha256": actual_sha,
        "record_count": len(records),
    }


def _read_registry_bytes(path: Path, artifact_id: str) -> bytes:
    if not path.is_file():
        _fail(f"input_missing.{artifact_id}", str(path))
    try:
        return path.read_bytes()
    except OSError as exc:
        _fail(f"input_read_failed.{artifact_id}", str(path))
        raise AssertionError from exc


def _validate_registry_destination(destination: Path) -> None:
    if destination.exists():
        _fail("registry_destination_exists", str(destination))


def _validate_registry_output_separation(
    destination: Path,
    source_paths: Sequence[Path],
) -> None:
    for source in source_paths:
        if (
            destination == source
            or destination.is_relative_to(source)
            or source.is_relative_to(destination)
        ):
            _fail("registry_output_overlaps_input", str(source))


def _recheck_registry_inputs(snapshots: Mapping[Path, str]) -> None:
    for path, expected in snapshots.items():
        try:
            actual = sha256_file(path)
        except OSError:
            _fail("input_changed_during_assembly", str(path))
        if actual != expected:
            _fail("input_changed_during_assembly", str(path))


def _write_registry_checksums(root: Path) -> None:
    names = (
        SUMMARY_MARKDOWN_FILENAME,
        AUDIT_EVIDENCE_FILENAME,
        REGISTRY_REFERENCE_FILENAME,
    )
    (root / SUMMARY_CHECKSUMS_FILENAME).write_text(
        "".join(f"{sha256_file(root / name)}  {name}\n" for name in names),
        encoding="ascii",
    )


def _verify_registry_output(root: Path, reference_sha256: str) -> None:
    expected_names = {
        SUMMARY_MARKDOWN_FILENAME,
        AUDIT_EVIDENCE_FILENAME,
        REGISTRY_REFERENCE_FILENAME,
    }
    values: dict[str, str] = {}
    try:
        lines = (root / SUMMARY_CHECKSUMS_FILENAME).read_text(
            encoding="ascii"
        ).splitlines()
    except (OSError, UnicodeError) as exc:
        _fail("registry_checksums_invalid", str(root))
        raise AssertionError from exc
    for line in lines:
        parts = line.split("  ")
        if len(parts) != 2:
            _fail("registry_checksums_invalid", line)
        digest, name = parts
        _registry_sha256(digest, f"registry.checksums.{name}")
        if name in values:
            _fail("registry_checksums_duplicate", name)
        values[name] = digest
    if set(values) != expected_names:
        _fail("registry_checksums_incomplete", str(sorted(values)))
    for name, digest in values.items():
        if sha256_file(root / name) != digest:
            _fail("registry_output_sha256_mismatch", name)
    if values[REGISTRY_REFERENCE_FILENAME] != reference_sha256:
        _fail(
            "registry_reference_copy_mismatch",
            values[REGISTRY_REFERENCE_FILENAME],
        )
    evidence = _read_json(root / AUDIT_EVIDENCE_FILENAME)
    _registry_schema(
        evidence,
        FROZEN_AUDIT_EVIDENCE_SCHEMA_VERSION,
        "registry.audit_evidence",
    )


def _registry_schema(
    payload: Mapping[str, Any],
    expected: str,
    artifact_id: str,
) -> None:
    if payload.get("schema_version") != expected:
        _fail(
            f"schema_mismatch.{artifact_id}",
            f"expected={expected};actual={payload.get('schema_version')}",
        )


def _registry_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(f"type_invalid.{name}", "object required")
    return value


def _registry_all_false(value: Mapping[str, Any], name: str) -> None:
    if not value:
        _fail(f"authority_invalid.{name}", "empty")
    for field, enabled in value.items():
        _registry_false(enabled, f"{name}.{field}")


def _registry_false(value: Any, name: str) -> None:
    if value is not False:
        _fail(f"authority_not_closed.{name}", str(value))


def _registry_zero(value: Any, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value != 0:
        _fail(f"safety_count_nonzero.{name}", str(value))


def _registry_equal(actual: Any, expected: Any, code: str) -> None:
    if actual != expected:
        _fail(code, f"expected={expected!r};actual={actual!r}")


def _registry_sha256(value: Any, name: str) -> str:
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        _fail(f"sha256_invalid.{name}", str(value))
    return value


def _registry_nonnegative_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail(f"integer_invalid.{name}", str(value))
    return value


def _registry_nonnegative_number(value: Any, name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0.0
    ):
        _fail(f"number_invalid.{name}", str(value))
    return float(value)


def _registry_probability(value: Any, name: str) -> float:
    result = _registry_nonnegative_number(value, name)
    if result > 1.0:
        _fail(f"probability_invalid.{name}", str(value))
    return result


def _registry_nonempty_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(f"string_invalid.{name}", str(value))
    return value


def _reject_json_constant(token: str) -> None:
    raise ValueError(f"non-finite JSON constant: {token}")


def _path_name(value: Any) -> str:
    if not isinstance(value, Path) or not value.name:
        _fail("lineage_filename_invalid", str(value))
    return value.name


def _summary(
    frozen: Mapping[str, Any],
    heldout: Mapping[str, Any],
    paired: Mapping[str, Any],
    *,
    evaluated_at_utc: str,
    heldout_report_path: Path,
    paired_output: Path,
) -> dict[str, Any]:
    if (
        paired["heldout_lineage_binding"]["bundle_manifest_sha256"]
        != frozen["manifest_sha256"]
        or paired["heldout_lineage_binding"]["bundle_weights_sha256"]
        != frozen["weights_sha256"]
    ):
        _fail("paired_bundle_lineage_mismatch", str(frozen["model_id"]))
    overall = paired["overall"]
    return {
        "schema_version": FROZEN_AUDIT_SUMMARY_SCHEMA_VERSION,
        "evaluated_at_utc": evaluated_at_utc,
        "status": paired["status"],
        "model": dict(frozen),
        "catalog": dict(paired["totals"]),
        "heldout": {
            "status": heldout["heldout_assessment"]["status"],
            "content_sha256": heldout["content_sha256"],
            "report_file_sha256": sha256_file(heldout_report_path),
        },
        "paired_shadow": {
            "status": paired["paired_shadow_assessment"]["status"],
            "content_sha256": paired["content_sha256"],
            "report_file_sha256": sha256_file(
                paired_output / PAIRED_SHADOW_REPORT_FILENAME
            ),
            "markdown_sha256": sha256_file(
                paired_output / PAIRED_SHADOW_MARKDOWN_FILENAME
            ),
            "lineage_sha256": sha256_file(
                paired_output / PAIRED_SHADOW_LINEAGE_FILENAME
            ),
            "candidate_recall": overall["candidate_recall"],
            "rule_edge_f1": overall["control"]["edge"]["f1"],
            "model_edge_f1": overall["model"]["edge"]["f1"],
            "rule_cluster_f1": overall["control"]["cluster_pairwise"]["f1"],
            "model_cluster_f1": overall["model"]["cluster_pairwise"]["f1"],
            "model_cluster_false_merge_rate": overall["model"][
                "cluster_pairwise"
            ]["false_merge_rate"],
            "model_latency_p50_ms": overall["model"]["latency_ms"][
                "scoring_p50"
            ],
            "model_latency_p95_ms": overall["model"]["latency_ms"][
                "scoring_p95"
            ],
            "peak_rss_mib": paired["runtime"]["max_rss_mib"],
            "runtime_fallback_rate": paired["runtime_fallback_probe"][
                "fallback_rate"
            ],
            "maximum_single_feature_auc": paired[
                "feature_label_diagnostics"
            ]["maximum_single_feature_auc"],
            "robustness_profiles": [
                {
                    "profile_id": item["profile"]["profile_id"],
                    "model_edge_f1": item["model"]["edge"]["f1"],
                    "model_cluster_f1": item["model"]["cluster_pairwise"]["f1"],
                    "model_cluster_false_merge_rate": item["model"][
                        "cluster_pairwise"
                    ]["false_merge_rate"],
                }
                for item in paired["robustness_profiles"]
            ],
        },
        "authority": {
            "g1": False,
            "assist": False,
            "authority": False,
            "default_model_changed": False,
            "active_visual_ppo_started": False,
        },
        "limitations": _summary_limitations(paired),
    }


def _render_summary(summary: Mapping[str, Any]) -> str:
    paired = summary["paired_shadow"]
    model = summary["model"]
    lines = [
        "# D5 冻结图模型审计",
        "",
        "## 结论",
        "",
        f"同一权重完成保留集和成对影子评估，状态为 `{summary['status']}`。",
        "本次只关闭权重谱系断点。G1、辅助模式和控制权限保持关闭。",
        "",
        "## 模型谱系",
        "",
        f"- manifest SHA-256：`{model['manifest_sha256']}`。",
        f"- weights SHA-256：`{model['weights_sha256']}`。",
        f"- admission：`{model['admission']['status']}`。",
        "",
        "## 名义指标",
        "",
        f"- 帧数：`{summary['catalog']['episode_count']}`；seed："
        f"`{summary['catalog']['seed_count']}`。",
        f"- 候选边召回：`{_format_metric(paired['candidate_recall'])}`。",
        f"- 模型边 F1：`{_format_metric(paired['model_edge_f1'])}`；模型簇 F1："
        f"`{_format_metric(paired['model_cluster_f1'])}`。",
        f"- 模型簇错误合并率："
        f"`{_format_metric(paired['model_cluster_false_merge_rate'])}`。",
        f"- 推理 P50/P95：`{_format_metric(paired['model_latency_p50_ms'])}/"
        f"{_format_metric(paired['model_latency_p95_ms'])}` 毫秒。",
        f"- 峰值常驻内存：`{_format_metric(paired['peak_rss_mib'], digits=3)}` MiB。",
        f"- 模型异常规则回退率："
        f"`{_format_metric(paired['runtime_fallback_rate'])}`。",
        "",
        "## 扰动结果",
        "",
        "| 扰动 | 模型边 F1 | 模型簇 F1 | 错误合并率 |",
        "| --- | ---: | ---: | ---: |",
    ]
    for item in paired["robustness_profiles"]:
        lines.append(
            f"| `{item['profile_id']}` | {_format_metric(item['model_edge_f1'])} | "
            f"{_format_metric(item['model_cluster_f1'])} | "
            f"{_format_metric(item['model_cluster_false_merge_rate'])} |"
        )
    auc = paired["maximum_single_feature_auc"]
    auc_value = auc["best_direction_auc"]
    if (
        "synthetic_heldout_single_feature_shortcut"
        in summary["limitations"]
    ):
        shortcut_text = (
            f"最高单特征 AUC 为 `{_format_metric(auc_value)}`，特征为 "
            f"`{auc['feature']}`，达到 "
            f"`{SYNTHETIC_SHORTCUT_AUC_THRESHOLD:.3f}` 阈值，"
            "保留单特征捷径阻断项。"
        )
    else:
        shortcut_text = (
            f"最高单特征 AUC 为 `{_format_metric(auc_value)}`，特征为 "
            f"`{auc['feature']}`，低于 "
            f"`{SYNTHETIC_SHORTCUT_AUC_THRESHOLD:.3f}` 阈值，"
            "不保留单特征捷径阻断项。"
        )
    lines.extend(
        [
            "",
            "## 限制",
            "",
            shortcut_text,
            "扰动评估固定候选图，只检查评分器稳定性，不能替代物理投影和候选门重建实验。",
            "",
        ]
    )
    return "\n".join(lines)


def _format_metric(value: Any, *, digits: int = 6) -> str:
    if value is None:
        return "不可用"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def _write_summary_checksums(root: Path) -> None:
    names = (SUMMARY_FILENAME, SUMMARY_MARKDOWN_FILENAME)
    text = "".join(
        f"{sha256_file(root / name)}  {name}\n" for name in names
    )
    (root / SUMMARY_CHECKSUMS_FILENAME).write_text(text, encoding="ascii")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        _fail("json_invalid", str(path))
        raise AssertionError from exc
    if not isinstance(value, dict):
        _fail("json_object_required", str(path))
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    payload = (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    os.replace(temporary, path)


def _fail(code: str, message: str) -> None:
    raise FrozenTrackletAuditError(code, message)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one hash-bound D5 frozen GNN audit."
    )
    parser.add_argument("--reference", required=True)
    parser.add_argument("--repository-root", required=True)
    parser.add_argument("--heldout-corpus", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--evaluated-at-utc", required=True)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--latency-repeats", type=int, default=3)
    parser.add_argument("--smoke-profile", action="store_true")
    return parser


def _registry_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Assemble one hash-bound D5 frozen registry for external audit."
        )
    )
    parser.add_argument("--reference", required=True)
    parser.add_argument("--reference-sha256", required=True)
    parser.add_argument("--frozen-audit-summary", required=True)
    parser.add_argument("--frozen-audit-summary-sha256", required=True)
    parser.add_argument("--heldout-report", required=True)
    parser.add_argument("--heldout-report-sha256", required=True)
    parser.add_argument("--paired-shadow-report", required=True)
    parser.add_argument("--paired-shadow-report-sha256", required=True)
    parser.add_argument("--paired-lineage", required=True)
    parser.add_argument("--paired-lineage-sha256", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == "assemble-registry":
        args = _registry_parser().parse_args(arguments[1:])
        evidence = assemble_frozen_tracklet_registry(
            args.reference,
            args.frozen_audit_summary,
            args.heldout_report,
            args.paired_shadow_report,
            args.paired_lineage,
            args.output_dir,
            expected_reference_sha256=args.reference_sha256,
            expected_frozen_audit_summary_sha256=(
                args.frozen_audit_summary_sha256
            ),
            expected_heldout_report_sha256=args.heldout_report_sha256,
            expected_paired_shadow_report_sha256=(
                args.paired_shadow_report_sha256
            ),
            expected_paired_lineage_sha256=args.paired_lineage_sha256,
        )
        print(
            json.dumps(
                {
                    "status": evidence["status"],
                    "weights_sha256": evidence["frozen_model"][
                        "weights_sha256"
                    ],
                    "limitations": evidence["limitations"],
                    "g1": False,
                    "assist": False,
                    "authority": False,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    args = _parser().parse_args(arguments)
    summary = run_frozen_tracklet_audit(
        args.reference,
        args.heldout_corpus,
        args.output_dir,
        repository_root=args.repository_root,
        evaluated_at_utc=args.evaluated_at_utc,
        device=args.device,
        latency_repeats=args.latency_repeats,
        require_full_profile=not args.smoke_profile,
    )
    print(
        json.dumps(
            {
                "status": summary["status"],
                "model_id": summary["model"]["model_id"],
                "weights_sha256": summary["model"]["weights_sha256"],
                "g1": False,
                "assist": False,
                "authority": False,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


__all__ = [
    "AUDIT_EVIDENCE_FILENAME",
    "FROZEN_AUDIT_EVIDENCE_SCHEMA_VERSION",
    "FROZEN_AUDIT_REFERENCE_SCHEMA_VERSION",
    "FROZEN_AUDIT_SUMMARY_SCHEMA_VERSION",
    "FrozenTrackletAuditError",
    "REGISTRY_REFERENCE_FILENAME",
    "SYNTHETIC_SHORTCUT_AUC_THRESHOLD",
    "assemble_frozen_tracklet_registry",
    "main",
    "run_frozen_tracklet_audit",
    "validate_frozen_reference",
]
