from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

import pytest

from d4_distributed_fallback.region_resource_v5_external_evaluation import (
    REGION_RESOURCE_V5_EXTERNAL_ARTIFACT_FILENAME,
    REGION_RESOURCE_V5_EXTERNAL_ARTIFACT_SCHEMA,
    REGION_RESOURCE_V5_EXTERNAL_INTEGRITY_FILENAME,
    REGION_RESOURCE_V5_EXTERNAL_OVERLAP_FILENAME,
    REGION_RESOURCE_V5_EXTERNAL_RECORD_SCHEMA,
    REGION_RESOURCE_V5_EXTERNAL_RECORDS_FILENAME,
    REGION_RESOURCE_V5_EXTERNAL_REPORT_FILENAME,
    REGION_RESOURCE_V5_EXTERNAL_SUMMARY_FILENAME,
    RegionResourceV5ExternalEvaluationConfig,
    RegionResourceV5ExternalEvaluationError,
    _summarize_records,
    _validate_paths,
    _with_content_sha256,
    review_region_resource_v5_external_evaluation,
)


def _record(
    *,
    split: str,
    score: float,
    rule_safe_positive: bool,
    actor_derived_positive: bool,
) -> dict[str, object]:
    return {
        "schema": REGION_RESOURCE_V5_EXTERNAL_RECORD_SCHEMA,
        "split": split,
        "score": score,
        "rule_safe_positive_action": rule_safe_positive,
        "actor_executable_difference": actor_derived_positive,
        "actor_target_signature_match": actor_derived_positive,
        "actor_derived_positive": actor_derived_positive,
        "confidence_threshold_passed": score >= 0.60,
        "candidate_gate_passed": (
            actor_derived_positive and score >= 0.60
        ),
        "rule_fallback_used": True,
    }


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _input_roots(tmp_path: Path) -> dict[str, Path]:
    roots = {
        name: tmp_path / name
        for name in ("source", "labeled", "v4", "v5")
    }
    for root in roots.values():
        root.mkdir()
    return roots


@pytest.fixture
def persisted_evaluation(tmp_path: Path) -> Path:
    root = tmp_path / "d4-v5-external-evaluation"
    root.mkdir()
    integrity = _with_content_sha256({"fixture": "integrity"})
    overlap = _with_content_sha256(
        {
            "exact_observable_key_intersection_count": 0,
        }
    )
    summary = _with_content_sha256(
        {
            "input_integrity_content_sha256": integrity[
                "content_sha256"
            ],
            "observable_overlap_content_sha256": overlap[
                "content_sha256"
            ],
            "metrics": {
                "sample_count": 63,
                "rule_safe_positive_action_count": 2,
                "actor_derived_positive_count": 0,
                "confidence_threshold_pass_count": 0,
                "negative_false_accept_count": 0,
                "rule_fallback_count": 63,
                "positive_denominator_available": False,
            },
            "data_usage": {
                "formal_holdout_payload_read_count": 0,
            },
            "candidate_status": {
                "registered": False,
                "admission_closed": True,
                "rule_fallback_required": True,
            },
        }
    )
    _write_json(
        root / REGION_RESOURCE_V5_EXTERNAL_INTEGRITY_FILENAME,
        integrity,
    )
    _write_json(
        root / REGION_RESOURCE_V5_EXTERNAL_OVERLAP_FILENAME,
        overlap,
    )
    _write_json(
        root / REGION_RESOURCE_V5_EXTERNAL_SUMMARY_FILENAME,
        summary,
    )
    (
        root / REGION_RESOURCE_V5_EXTERNAL_RECORDS_FILENAME
    ).write_text("{}\n", encoding="utf-8")
    (
        root / REGION_RESOURCE_V5_EXTERNAL_REPORT_FILENAME
    ).write_text("# fixture\n", encoding="utf-8")
    artifact_names = (
        REGION_RESOURCE_V5_EXTERNAL_RECORDS_FILENAME,
        REGION_RESOURCE_V5_EXTERNAL_INTEGRITY_FILENAME,
        REGION_RESOURCE_V5_EXTERNAL_OVERLAP_FILENAME,
        REGION_RESOURCE_V5_EXTERNAL_SUMMARY_FILENAME,
        REGION_RESOURCE_V5_EXTERNAL_REPORT_FILENAME,
    )
    artifact_manifest = _with_content_sha256(
        {
            "schema": REGION_RESOURCE_V5_EXTERNAL_ARTIFACT_SCHEMA,
            "report_date": "2026-07-29",
            "artifact_files": {
                name: _file_sha256(root / name)
                for name in artifact_names
            },
            "candidate_mutation_count": 0,
            "formal_holdout_payload_read_count": 0,
            "production_permission_available": False,
        }
    )
    _write_json(
        root / REGION_RESOURCE_V5_EXTERNAL_ARTIFACT_FILENAME,
        artifact_manifest,
    )
    return root


@pytest.mark.parametrize(
    ("protected_name", "destination_suffix", "expected_name"),
    (
        ("v4", ("evaluation-output",), "v4_candidate"),
        ("source", ("nested", "evaluation-output"), "source"),
    ),
)
def test_v5_external_output_within_protected_input_is_rejected(
    tmp_path: Path,
    protected_name: str,
    destination_suffix: tuple[str, ...],
    expected_name: str,
) -> None:
    roots = _input_roots(tmp_path)
    destination = roots[protected_name].joinpath(*destination_suffix)

    with pytest.raises(
        RegionResourceV5ExternalEvaluationError,
        match=(
            "v5_external_output_within_protected_input:"
            f"{expected_name}"
        ),
    ):
        _validate_paths(
            source=roots["source"],
            labeled=roots["labeled"],
            v4_root=roots["v4"],
            v5_root=roots["v5"],
            destination=destination,
            replace_output=False,
        )


def test_v5_external_output_outside_protected_inputs_is_accepted(
    tmp_path: Path,
) -> None:
    roots = _input_roots(tmp_path)

    _validate_paths(
        source=roots["source"],
        labeled=roots["labeled"],
        v4_root=roots["v4"],
        v5_root=roots["v5"],
        destination=tmp_path / "external-output",
        replace_output=False,
    )


def test_v5_external_contract_cannot_read_holdout_or_lower_gate() -> None:
    config = RegionResourceV5ExternalEvaluationConfig()
    assert config.fixed_minimum_confidence == 0.60
    assert config.formal_holdout_read_allowed is False
    assert config.model_fit_allowed is False
    assert not (
        set(config.training_seeds)
        & set(config.formal_holdout_seeds)
    )
    assert not (
        set(config.design_pilot_seeds)
        & set(config.independent_evaluation_seeds)
    )
    with pytest.raises(
        ValueError,
        match="external evaluation contract changed",
    ):
        replace(config, fixed_minimum_confidence=0.59)
    with pytest.raises(
        ValueError,
        match="external evaluation must remain read-only",
    ):
        replace(config, formal_holdout_read_allowed=True)


def test_rule_positive_is_not_actor_positive_denominator() -> None:
    records = (
        _record(
            split="train",
            score=0.0,
            rule_safe_positive=True,
            actor_derived_positive=False,
        ),
        _record(
            split="validation",
            score=0.0,
            rule_safe_positive=False,
            actor_derived_positive=False,
        ),
        _record(
            split="test",
            score=0.0,
            rule_safe_positive=False,
            actor_derived_positive=False,
        ),
    )
    metrics = _summarize_records(records, threshold=0.60)
    assert metrics["rule_safe_positive_action_count"] == 1
    assert metrics["actor_derived_positive_count"] == 0
    assert metrics["positive_denominator_available"] is False
    assert metrics["positive_recall"] is None
    assert (
        metrics["positive_recall_status"]
        == "positive_denominator_unavailable"
    )
    assert metrics["negative_specificity"] == 1.0
    assert metrics["rule_fallback_count"] == 3


def test_actor_positive_recall_uses_actor_derived_denominator() -> None:
    records = (
        _record(
            split="train",
            score=0.75,
            rule_safe_positive=True,
            actor_derived_positive=True,
        ),
        _record(
            split="validation",
            score=0.10,
            rule_safe_positive=False,
            actor_derived_positive=False,
        ),
        _record(
            split="test",
            score=0.0,
            rule_safe_positive=False,
            actor_derived_positive=False,
        ),
    )
    metrics = _summarize_records(records, threshold=0.60)
    assert metrics["actor_derived_positive_count"] == 1
    assert metrics["positive_denominator_available"] is True
    assert metrics["positive_recall"] == 1.0
    assert metrics["negative_false_accept_count"] == 0


def test_persisted_v5_external_evaluation_is_closed_and_reviewable(
    persisted_evaluation: Path,
) -> None:
    reviewed = review_region_resource_v5_external_evaluation(
        persisted_evaluation
    )
    summary = reviewed["summary"]
    metrics = summary["metrics"]
    assert metrics["sample_count"] == 63
    assert metrics["rule_safe_positive_action_count"] == 2
    assert metrics["actor_derived_positive_count"] == 0
    assert metrics["confidence_threshold_pass_count"] == 0
    assert metrics["negative_false_accept_count"] == 0
    assert metrics["rule_fallback_count"] == 63
    assert metrics["positive_denominator_available"] is False
    assert summary["data_usage"]["formal_holdout_payload_read_count"] == 0
    assert summary["candidate_status"]["registered"] is False
    assert summary["candidate_status"]["admission_closed"] is True
    assert summary["candidate_status"]["rule_fallback_required"] is True
    assert reviewed["overlap"][
        "exact_observable_key_intersection_count"
    ] == 0


def test_persisted_v5_external_evaluation_tamper_is_rejected(
    persisted_evaluation: Path,
) -> None:
    summary_path = (
        persisted_evaluation / REGION_RESOURCE_V5_EXTERNAL_SUMMARY_FILENAME
    )
    summary_path.write_bytes(summary_path.read_bytes() + b" ")
    with pytest.raises(
        RegionResourceV5ExternalEvaluationError,
        match="artifact_sha256_mismatch",
    ):
        review_region_resource_v5_external_evaluation(
            persisted_evaluation
        )
