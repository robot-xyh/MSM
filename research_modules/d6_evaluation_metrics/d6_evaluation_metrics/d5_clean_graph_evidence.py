"""Strict read-only admission layers for D5 clean cross-view graph data."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence


D5_CLEAN_GRAPH_LEGACY_INPUT_SCHEMA_VERSION = "d6.d5-clean-graph-inputs.v1"
D5_CLEAN_GRAPH_INPUT_SCHEMA_VERSION = "d6.d5-clean-graph-inputs.v2"
D5_CLEAN_GRAPH_EVIDENCE_SCHEMA_VERSION = "d6.d5-clean-graph-evidence.v1"
D5_CLEAN_GRAPH_EVIDENCE_DATE = "2026-07-21"
D5_GRAPH_MODEL_REPORT_SCHEMA_VERSION = "d5.tracklet-graph-model-evaluation.v1"
D5_HELDOUT_CORPUS_SCHEMA_VERSION = "d5.tracklet-heldout-corpus.v1"
D5_HELDOUT_EPISODE_SCHEMA_VERSION = "d5.tracklet-heldout-episode.v1"
D5_HELDOUT_EVALUATION_SCHEMA_VERSION = (
    "d5.tracklet-heldout-model-evaluation.v1"
)
D5_TRACKLET_MODEL_BUNDLE_SCHEMA_VERSION = "d5.tracklet-model-bundle.v3"

D5_CLEAN_GRAPH_CRITERIA: Mapping[str, Any] = {
    "maximum_edge_free_ratio": 0.9,
    "maximum_p95_inference_latency_ms": 100.0,
    "maximum_test_ece": 0.05,
    "maximum_test_false_merge_rate": 0.01,
    "minimum_candidate_recall_availability_ratio": 1.0,
    "minimum_candidate_recall_pairs_per_split": 100,
    "minimum_scenario_scale_both_class_fraction": 0.8,
    "minimum_test_candidate_recall": 0.95,
    "minimum_test_f1": 0.92,
    "minimum_test_negative_edges": 30,
    "minimum_test_positive_edges": 50,
    "minimum_test_precision": 0.95,
    "minimum_test_recall": 0.9,
    "minimum_test_seed_count": 20,
    "minimum_train_negative_edges": 100,
    "minimum_train_positive_edges": 100,
    "minimum_validation_negative_edges": 30,
    "minimum_validation_positive_edges": 50,
    "reserved_evaluation_seed_start": 1000,
    "reserved_evaluation_seed_stop": 1020,
    "reserved_evaluation_seeds": list(range(1000, 1020)),
}

_REQUIRED_ARTIFACT_NAMES = (
    "supplemental_summary",
    "composite_admission",
    "composite_view",
    "formal_canonical_view",
    "supplemental_canonical_view",
    "supplemental_manifest",
    "supplemental_dataset_manifest",
    "formal_source_manifest",
)
_MODEL_ARTIFACT_NAMES = ("model_report", "model_weights", "model_config")
_HELDOUT_ARTIFACT_NAMES = (
    "heldout_evaluation_report",
    "heldout_manifest",
)
_SHA_RE = re.compile(r"^(?:sha256:)?([0-9a-fA-F]{64})$")
_EXPECTED_SEED_COUNTS = {"train": 60, "validation": 20, "test": 20}
_RESERVED_SEEDS = frozenset(range(1000, 1020))
_SPLITS = ("train", "validation", "test")
_HELDOUT_ROLE = "held_out_evaluation"
_HELDOUT_PROFILE_VERSION = "d5-tracklet-heldout-1000-1019-full-v1"
_HELDOUT_SCENARIOS = (
    "nominal",
    "dense_crossing",
    "formation_split",
    "evasive_multilevel",
    "delayed_noisy",
    "communication_degraded",
    "center_failure",
    "secondary_failure",
    "high_threat_m_to_n",
)
_HELDOUT_SCALES = (5, 20, 50, 100, 200)
_HELDOUT_CELLS = tuple(
    (scenario, scale)
    for scenario in _HELDOUT_SCENARIOS
    for scale in _HELDOUT_SCALES
)
_HELDOUT_EPISODE_COUNT = len(_RESERVED_SEEDS) * len(_HELDOUT_CELLS)
_HELDOUT_IMPLEMENTATION_FILES = (
    "sparse_tracklet_graph.py",
    "tracklet_dataset.py",
    "tracklet_gnn.py",
    "tracklet_model_bundle.py",
    "tracklet_training.py",
    "tracklet_training_audit.py",
    "tracklet_supplemental_curriculum.py",
    "tracklet_heldout_evaluation.py",
)
_MODEL_IMPLEMENTATION_FILES = (
    "tracklet_gnn.py",
    "tracklet_model_bundle.py",
    "tracklet_training.py",
    "tracklet_training_audit.py",
)
_MODEL_NODE_FEATURE_NAMES = (
    "center_x_normalized",
    "center_y_normalized",
    "log_bbox_area_ratio",
    "log_bbox_aspect_ratio",
    "angular_velocity_x_rad_s",
    "angular_velocity_y_rad_s",
    "bbox_scale_rate_s",
    "confidence",
    "pixel_covariance_trace_normalized",
    "tracklet_age_s",
)
_MODEL_EDGE_FEATURE_NAMES = (
    "time_delta_s",
    "pixel_mahalanobis",
    "reprojection_error_px",
    "ray_closest_distance_m",
    "bbox_log_scale_delta",
    "bbox_scale_rate_delta_s",
    "angular_velocity_delta_rad_s",
    "baseline_m",
    "extrinsics_covariance_trace",
    "epipolar_error_px",
    "triangulation_angle_rad",
    "global_projection_mahalanobis",
    "confidence_product",
    "shared_global_track_count",
)
_HELDOUT_DEFAULT_GATE_CONFIG: Mapping[str, Any] = {
    "max_time_delta_s": 0.35,
    "max_arrival_time_delta_s": 1.0,
    "max_camera_geometry_age_s": 0.35,
    "fov_margin_px": 2.0,
    "max_epipolar_error_px": 8.0,
    "epipolar_covariance_sigma": 2.0,
    "max_ray_closest_distance_m": 25.0,
    "ray_covariance_sigma": 2.0,
    "min_triangulation_angle_deg": 0.2,
    "max_reprojection_error_px": 10.0,
    "reprojection_covariance_sigma": 2.0,
    "max_pixel_mahalanobis": 6.0,
    "max_global_projection_mahalanobis": 6.0,
    "global_process_noise_m2_s4": 1.0,
    "max_tracklet_covariance_trace_px2": 10_000.0,
    "max_extrinsics_covariance_trace": 1_000.0,
    "camera_overlap_near_m": 1.0,
    "camera_overlap_far_m": 3_000.0,
    "camera_index_cell_size_m": 1_000.0,
    "camera_pair_time_window_s": 0.35,
    "camera_pair_budget": 4_096,
    "camera_index_max_search_radius_cells": 8,
    "max_tracklet_candidate_edges_per_node": 24,
    "max_neighbors_per_node": 24,
    "covariance_regularization": 1.0e-6,
}


class D5CleanGraphEvidenceError(RuntimeError):
    """Stable fail-closed error at the D5-to-D6 evidence boundary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code)


@dataclass(frozen=True, slots=True)
class D5CleanGraphArtifact:
    """One explicit artifact and its caller-supplied file digest."""

    path: Path
    sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", Path(self.path))
        object.__setattr__(self, "sha256", _normalise_sha256(self.sha256))

    def resolved(self) -> "D5CleanGraphArtifact":
        return D5CleanGraphArtifact(self.path.expanduser().resolve(), self.sha256)

    def to_dict(self) -> dict[str, str]:
        return {"path": str(self.path), "sha256": self.sha256}


@dataclass(frozen=True, slots=True)
class D5CleanGraphEvidenceInputs:
    """Explicit D5 data, model, and optional paired held-out artifacts."""

    supplemental_summary: D5CleanGraphArtifact
    composite_admission: D5CleanGraphArtifact
    composite_view: D5CleanGraphArtifact
    formal_canonical_view: D5CleanGraphArtifact
    supplemental_canonical_view: D5CleanGraphArtifact
    supplemental_manifest: D5CleanGraphArtifact
    supplemental_dataset_manifest: D5CleanGraphArtifact
    formal_source_manifest: D5CleanGraphArtifact
    model_report: D5CleanGraphArtifact | None = None
    model_weights: D5CleanGraphArtifact | None = None
    model_config: D5CleanGraphArtifact | None = None
    heldout_evaluation_report: D5CleanGraphArtifact | None = None
    heldout_manifest: D5CleanGraphArtifact | None = None
    schema_version: str = D5_CLEAN_GRAPH_INPUT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version not in {
            D5_CLEAN_GRAPH_LEGACY_INPUT_SCHEMA_VERSION,
            D5_CLEAN_GRAPH_INPUT_SCHEMA_VERSION,
        }:
            raise ValueError("unsupported D5 clean graph input schema")
        for name in _REQUIRED_ARTIFACT_NAMES:
            if not isinstance(getattr(self, name), D5CleanGraphArtifact):
                raise TypeError(f"{name} must be a D5CleanGraphArtifact")
        present = tuple(getattr(self, name) is not None for name in _MODEL_ARTIFACT_NAMES)
        if any(present) and not all(present):
            raise ValueError(
                "model_report, model_weights, and model_config must be supplied together"
            )
        for name in _MODEL_ARTIFACT_NAMES:
            value = getattr(self, name)
            if value is not None and not isinstance(value, D5CleanGraphArtifact):
                raise TypeError(f"{name} must be a D5CleanGraphArtifact or None")
        heldout_present = tuple(
            getattr(self, name) is not None for name in _HELDOUT_ARTIFACT_NAMES
        )
        if any(heldout_present) and not all(heldout_present):
            raise ValueError(
                "heldout_evaluation_report and heldout_manifest must be supplied together"
            )
        for name in _HELDOUT_ARTIFACT_NAMES:
            value = getattr(self, name)
            if value is not None and not isinstance(value, D5CleanGraphArtifact):
                raise TypeError(f"{name} must be a D5CleanGraphArtifact or None")
        if self.has_heldout_evidence and not self.has_model_bundle:
            raise ValueError("held-out evidence requires the complete internal model bundle")
        if (
            self.schema_version == D5_CLEAN_GRAPH_LEGACY_INPUT_SCHEMA_VERSION
            and self.has_heldout_evidence
        ):
            raise ValueError("v1 D5 clean graph inputs cannot carry held-out evidence")

    @property
    def has_model_bundle(self) -> bool:
        return self.model_report is not None

    @property
    def has_heldout_evidence(self) -> bool:
        return self.heldout_evaluation_report is not None

    def resolved(self) -> "D5CleanGraphEvidenceInputs":
        values: dict[str, Any] = {
            name: getattr(self, name).resolved() for name in _REQUIRED_ARTIFACT_NAMES
        }
        values.update(
            {
                name: (
                    None
                    if getattr(self, name) is None
                    else getattr(self, name).resolved()
                )
                for name in _MODEL_ARTIFACT_NAMES
            }
        )
        values.update(
            {
                name: (
                    None
                    if getattr(self, name) is None
                    else getattr(self, name).resolved()
                )
                for name in _HELDOUT_ARTIFACT_NAMES
            }
        )
        return D5CleanGraphEvidenceInputs(
            **values,
            schema_version=self.schema_version,
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema_version": self.schema_version,
            "artifacts": {
                name: getattr(self, name).to_dict()
                for name in _REQUIRED_ARTIFACT_NAMES
            },
            "model_evidence": (
                None
                if not self.has_model_bundle
                else {
                    name: getattr(self, name).to_dict()
                    for name in _MODEL_ARTIFACT_NAMES
                }
            ),
        }
        if self.schema_version == D5_CLEAN_GRAPH_INPUT_SCHEMA_VERSION:
            result["heldout_evidence"] = (
                None
                if not self.has_heldout_evidence
                else {
                    name: getattr(self, name).to_dict()
                    for name in _HELDOUT_ARTIFACT_NAMES
                }
            )
        return result

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
        *,
        base_dir: str | Path | None = None,
    ) -> "D5CleanGraphEvidenceInputs":
        schema_version = payload.get("schema_version")
        _expect(
            schema_version
            in {
                D5_CLEAN_GRAPH_LEGACY_INPUT_SCHEMA_VERSION,
                D5_CLEAN_GRAPH_INPUT_SCHEMA_VERSION,
            },
            "input_schema_mismatch",
            "D5 clean graph input specification schema is unsupported",
        )
        expected_top_level = {"schema_version", "artifacts", "model_evidence"}
        if schema_version == D5_CLEAN_GRAPH_INPUT_SCHEMA_VERSION:
            expected_top_level.add("heldout_evidence")
        _require_exact_keys(
            payload,
            expected_top_level,
            "D5 clean graph input specification",
        )
        root = None if base_dir is None else Path(base_dir).expanduser().resolve()
        artifacts = _mapping(payload.get("artifacts"), "input artifacts")
        _require_exact_keys(
            artifacts,
            set(_REQUIRED_ARTIFACT_NAMES),
            "input artifacts",
        )
        values = {
            name: _artifact_from_mapping(artifacts[name], name=name, base_dir=root)
            for name in _REQUIRED_ARTIFACT_NAMES
        }
        model = payload.get("model_evidence")
        if model is None:
            values.update({name: None for name in _MODEL_ARTIFACT_NAMES})
        else:
            model_mapping = _mapping(model, "model evidence")
            _require_exact_keys(
                model_mapping,
                set(_MODEL_ARTIFACT_NAMES),
                "model evidence",
            )
            values.update(
                {
                    name: _artifact_from_mapping(
                        model_mapping[name], name=name, base_dir=root
                    )
                    for name in _MODEL_ARTIFACT_NAMES
                }
            )
        if schema_version == D5_CLEAN_GRAPH_INPUT_SCHEMA_VERSION:
            heldout = payload.get("heldout_evidence")
            if heldout is None:
                values.update({name: None for name in _HELDOUT_ARTIFACT_NAMES})
            else:
                heldout_mapping = _mapping(heldout, "held-out evidence")
                _require_exact_keys(
                    heldout_mapping,
                    set(_HELDOUT_ARTIFACT_NAMES),
                    "held-out evidence",
                )
                values.update(
                    {
                        name: _artifact_from_mapping(
                            heldout_mapping[name], name=name, base_dir=root
                        )
                        for name in _HELDOUT_ARTIFACT_NAMES
                    }
                )
        else:
            values.update({name: None for name in _HELDOUT_ARTIFACT_NAMES})
        return cls(**values, schema_version=str(schema_version))


def load_d5_clean_graph_evidence_inputs(
    path: str | Path,
    *,
    expected_sha256: str,
) -> D5CleanGraphEvidenceInputs:
    """Load an explicit input specification after verifying its own digest."""

    source = Path(path).expanduser().resolve()
    _verify_file(source, expected_sha256, "input_specification")
    payload = _load_json(source, "D5 clean graph input specification")
    return D5CleanGraphEvidenceInputs.from_mapping(payload, base_dir=source.parent)


def audit_d5_clean_graph_evidence(
    inputs: D5CleanGraphEvidenceInputs,
    *,
    evaluation_date: str = D5_CLEAN_GRAPH_EVIDENCE_DATE,
) -> dict[str, Any]:
    """Verify clean D5 data without promoting a model or changing control."""

    _expect(
        evaluation_date == D5_CLEAN_GRAPH_EVIDENCE_DATE,
        "evaluation_date_mismatch",
        f"evaluation_date must be {D5_CLEAN_GRAPH_EVIDENCE_DATE}",
    )
    source = inputs.resolved()
    artifact_hashes = _verify_input_artifacts(source)
    summary = _load_and_verify_content(
        source.supplemental_summary.path,
        "supplemental summary",
    )
    admission = _load_and_verify_content(
        source.composite_admission.path,
        "composite admission",
    )
    view = _load_and_verify_content(source.composite_view.path, "composite view")
    formal_view = _load_and_verify_content(
        source.formal_canonical_view.path,
        "formal canonical view",
    )
    supplemental_view = _load_and_verify_content(
        source.supplemental_canonical_view.path,
        "supplemental canonical view",
    )
    supplemental_manifest = _load_and_verify_content(
        source.supplemental_manifest.path,
        "supplemental manifest",
    )
    supplemental_dataset = _load_json(
        source.supplemental_dataset_manifest.path,
        "supplemental dataset manifest",
    )
    formal_manifest = _load_json(
        source.formal_source_manifest.path,
        "formal source manifest",
    )

    _validate_summary(summary, artifact_hashes)
    supplemental_data = _validate_supplemental_manifest(
        supplemental_manifest,
        artifact_hashes,
    )
    dataset_data = _validate_dataset_manifest(
        supplemental_dataset,
        context="supplemental dataset manifest",
    )
    formal_data = _validate_dataset_manifest(
        formal_manifest,
        context="formal source manifest",
        require_complete_labels=False,
    )
    _expect_equal(
        dataset_data["episode_count"],
        supplemental_data["episode_count"],
        "supplemental_episode_count_mismatch",
        "supplemental manifest and dataset disagree on episode count",
    )
    _expect_equal(
        dataset_data["class_balance"],
        supplemental_data["class_balance"],
        "supplemental_class_balance_mismatch",
        "supplemental manifest and dataset disagree on class balance",
    )
    formal_partition = _validate_canonical_view(
        formal_view,
        expected_source_sha256=artifact_hashes["formal_source_manifest"],
        context="formal canonical view",
    )
    supplemental_partition = _validate_canonical_view(
        supplemental_view,
        expected_source_sha256=artifact_hashes[
            "supplemental_dataset_manifest"
        ],
        context="supplemental canonical view",
    )
    _expect_equal(
        formal_partition,
        supplemental_partition,
        "canonical_seed_partition_mismatch",
        "formal and supplemental canonical views use different seed partitions",
    )
    selection = _validate_composite_view(
        view,
        formal_view=formal_view,
        supplemental_view=supplemental_view,
        formal_view_path=source.formal_canonical_view.path,
        supplemental_view_path=source.supplemental_canonical_view.path,
        artifact_hashes=artifact_hashes,
        seed_partition=formal_partition,
    )
    _validate_composite_admission(
        admission,
        view=view,
        selection=selection,
        artifact_hashes=artifact_hashes,
    )
    _validate_cross_source_counts(
        summary=summary,
        supplemental_data=supplemental_data,
        dataset_data=dataset_data,
        formal_data=formal_data,
        selection=selection,
    )

    model_layer = _audit_model_bundle(
        source,
        artifact_hashes=artifact_hashes,
        training_source_sha256=str(selection["training_set_sha256"]),
        test_seed_values=tuple(formal_partition["test"]),
    )
    heldout_layer = _audit_heldout_evidence(
        source,
        artifact_hashes=artifact_hashes,
        training_source_sha256=str(selection["training_set_sha256"]),
    )
    layers = {
        "data_support": {
            "available": True,
            "status": "complete",
            "reason": "clean_labeled_cross_view_graph_support_verified",
        },
        "training_source": {
            "available": True,
            "status": "complete",
            "reason": "immutable_clean_composite_training_source_verified",
            "training_source_sha256": selection["training_set_sha256"],
        },
        "internal_model_test": model_layer,
        "held_out_seed": heldout_layer,
        "paired_shadow": _unavailable_layer(
            "same_seed_paired_shadow_not_supplied"
        ),
    }
    promotion_blockers = []
    if not model_layer["available"]:
        promotion_blockers.append("internal_model_test_unavailable")
    elif model_layer["status"] != "complete":
        promotion_blockers.append("internal_model_test_thresholds_failed")
    if not heldout_layer["available"]:
        promotion_blockers.append("held_out_seed_evaluation_unavailable")
    elif heldout_layer["status"] != "complete":
        promotion_blockers.append("held_out_seed_evaluation_failed")
    promotion_blockers.extend(
        [
            "same_seed_paired_shadow_unavailable",
            "g1_assist_authority_not_admitted",
        ]
    )
    return {
        "schema_version": D5_CLEAN_GRAPH_EVIDENCE_SCHEMA_VERSION,
        "evaluation_date": evaluation_date,
        "evaluation_mode": "offline_read_only_fail_closed",
        "source_artifacts": {
            name: {"sha256": artifact_hashes[name], "verified": True}
            for name in (*_REQUIRED_ARTIFACT_NAMES, *_MODEL_ARTIFACT_NAMES)
            if name in artifact_hashes
        },
        "data_summary": {
            "episode_count": selection["episode_count"],
            "candidate_edge_count": selection["candidate_edge_count"],
            "positive_candidate_edge_count": selection["positive_edge_count"],
            "negative_candidate_edge_count": selection["negative_edge_count"],
            "unlabeled_candidate_edge_count": 0,
            "scenario_scale_cell_count": int(summary["scenario_scale_cell_count"]),
            "seed_counts": dict(_EXPECTED_SEED_COUNTS),
            "reserved_seed_overlap": [],
            "source_repository_dirty": False,
            "source_modified": False,
        },
        "evidence_layers": layers,
        "admission": {
            "clean_data_supported": True,
            "training_source_supported": True,
            "model_promotion_allowed": False,
            "g1_allowed": False,
            "assist_allowed": False,
            "authority_allowed": False,
            "rule_fallback_required": True,
            "formal_ppo_reward_available": False,
            "causal_claim_available": False,
            "counterfactual_available": False,
            "status": "data_ready_model_admission_closed",
            "promotion_blockers": promotion_blockers,
        },
        "audit": {
            "passed": True,
            "fail_closed": True,
            "implicit_d5_output_path_discovery_used": False,
            "source_mutation_performed": False,
            "runtime_outcome_diagnostic_modified": False,
            "formal_ppo_reward_generated": False,
            "causal_claim_generated": False,
        },
    }


def write_d5_clean_graph_evidence_report(
    inputs: D5CleanGraphEvidenceInputs,
    output_dir: str | Path,
) -> dict[str, Path]:
    """Write deterministic JSON and Chinese Markdown evidence reports."""

    payload = audit_d5_clean_graph_evidence(inputs)
    root = Path(output_dir).expanduser().resolve()
    input_paths = {
        getattr(inputs.resolved(), name).path
        for name in (
            *_REQUIRED_ARTIFACT_NAMES,
            *_MODEL_ARTIFACT_NAMES,
            *_HELDOUT_ARTIFACT_NAMES,
        )
        if getattr(inputs.resolved(), name) is not None
    }
    _expect(
        all(path != root and root not in path.parents for path in input_paths),
        "output_overlaps_input",
        "output directory must not contain or replace an input artifact",
    )
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / "d5_clean_graph_evidence.json"
    markdown_path = root / "D5_CLEAN_GRAPH_EVIDENCE_CN.md"
    _write_json_atomic(json_path, payload)
    _write_text_atomic(markdown_path, render_d5_clean_graph_evidence_markdown(payload))
    return {"json": json_path, "markdown": markdown_path}


def render_d5_clean_graph_evidence_markdown(payload: Mapping[str, Any]) -> str:
    """Render the five-layer boundary without treating data as model evidence."""

    summary = _mapping(payload.get("data_summary"), "data summary")
    layers = _mapping(payload.get("evidence_layers"), "evidence layers")
    admission = _mapping(payload.get("admission"), "admission")
    lines = [
        "# D5 跨视角图数据分层评估",
        "",
        "## 结论",
        "",
        (
            f"已核验 {int(summary['episode_count'])} 个图帧、"
            f"{int(summary['candidate_edge_count'])} 条候选边。"
            f"正边 {int(summary['positive_candidate_edge_count'])} 条，"
            f"负边 {int(summary['negative_candidate_edge_count'])} 条，未标注边为 0。"
        ),
        (
            "数据支持和训练来源为 complete。"
            f"模型内部测试为 {layers['internal_model_test']['status']}，"
            f"保留 seed 为 {layers['held_out_seed']['status']}，"
            f"同 seed 配对影子为 {layers['paired_shadow']['status']}。"
        ),
        "G1、辅助模式和控制权限保持关闭，确定性几何规则继续作为默认回退。",
        "",
        "## 证据分层",
        "",
        "| 层级 | 状态 | 原因 |",
        "| --- | --- | --- |",
    ]
    labels = {
        "data_support": "数据支持",
        "training_source": "训练数据来源",
        "internal_model_test": "模型内部测试",
        "held_out_seed": "保留 seed",
        "paired_shadow": "配对影子",
    }
    for name in labels:
        item = _mapping(layers.get(name), name)
        lines.append(f"| {labels[name]} | {item['status']} | {item['reason']} |")
    lines.extend(
        [
            "",
            "## 准入边界",
            "",
            f"当前状态为 `{admission['status']}`。模型 promotion、G1、assist 和 authority 均为 false。",
            "本报告不生成正式 PPO 奖励，不给出因果或反事实结论。",
            "",
        ]
    )
    return "\n".join(lines)


def _verify_input_artifacts(
    inputs: D5CleanGraphEvidenceInputs,
) -> dict[str, str]:
    names = list(_REQUIRED_ARTIFACT_NAMES)
    if inputs.has_model_bundle:
        names.extend(_MODEL_ARTIFACT_NAMES)
    if inputs.has_heldout_evidence:
        names.extend(_HELDOUT_ARTIFACT_NAMES)
    paths: set[Path] = set()
    hashes: dict[str, str] = {}
    for name in names:
        artifact = getattr(inputs, name)
        assert artifact is not None
        _expect(
            artifact.path not in paths,
            "duplicate_input_path",
            f"multiple logical inputs use {artifact.path}",
        )
        paths.add(artifact.path)
        hashes[name] = _verify_file(artifact.path, artifact.sha256, name)
    return hashes


def _validate_summary(
    summary: Mapping[str, Any],
    hashes: Mapping[str, str],
) -> None:
    _expect_equal(
        summary.get("schema_version"),
        "d5.tracklet-supplemental-summary.v1",
        "supplemental_summary_schema_mismatch",
        "supplemental summary schema changed",
    )
    _expect(
        summary.get("source_repository_dirty") is False,
        "dirty_training_source",
        "supplemental summary was generated from a dirty repository",
    )
    _expect_equal(
        summary.get("canonical_seed_counts"),
        _EXPECTED_SEED_COUNTS,
        "supplemental_seed_counts_mismatch",
        "supplemental summary is not split 60/20/20",
    )
    _expect_equal(
        _nonnegative_int(summary.get("unique_seed_count"), "unique_seed_count"),
        100,
        "supplemental_seed_count_mismatch",
        "supplemental summary must contain 100 training-registry seeds",
    )
    _expect_equal(
        _normalise_sha256(summary.get("manifest_sha256")),
        hashes["supplemental_manifest"],
        "summary_supplemental_manifest_hash_mismatch",
        "summary references another supplemental manifest",
    )
    _expect_equal(
        _normalise_sha256(summary.get("dataset_manifest_sha256")),
        hashes["supplemental_dataset_manifest"],
        "summary_dataset_manifest_hash_mismatch",
        "summary references another supplemental dataset",
    )
    _expect_equal(
        _normalise_sha256(summary.get("formal_manifest_sha256")),
        hashes["formal_source_manifest"],
        "summary_formal_manifest_hash_mismatch",
        "summary references another formal source",
    )
    _expect_equal(
        _nonnegative_int(summary.get("scenario_scale_cell_count"), "cell count"),
        45,
        "scenario_scale_cell_count_mismatch",
        "clean supplemental evidence must cover 45 scenario-scale cells",
    )
    _validate_admission_flags(summary.get("admission"), "supplemental summary")
    balance = _class_balance(
        summary.get("class_balance"),
        "summary class balance",
        candidate_edges=_positive_int(
            summary.get("candidate_edge_count"), "summary candidate edge count"
        ),
    )
    _expect_clean_balance(balance, "supplemental summary")
    _expect(
        _ratio(summary.get("label_availability_ratio"), "label availability")
        == 1.0,
        "incomplete_label_availability",
        "supplemental summary label availability is not 100 percent",
    )


def _validate_supplemental_manifest(
    manifest: Mapping[str, Any],
    hashes: Mapping[str, str],
) -> dict[str, Any]:
    _expect_equal(
        manifest.get("schema_version"),
        "d5.tracklet-supplemental-manifest.v1",
        "supplemental_manifest_schema_mismatch",
        "supplemental manifest schema changed",
    )
    source = _mapping(manifest.get("source"), "supplemental source")
    _expect(
        source.get("repository_dirty") is False,
        "dirty_training_source",
        "supplemental manifest was generated from a dirty repository",
    )
    _expect_sha(source.get("git_commit"), 40, "supplemental source git commit")
    formal = _mapping(manifest.get("formal_source"), "formal source binding")
    _expect(
        formal.get("modified") is False,
        "source_rewrite_detected",
        "formal source was modified while constructing supplemental data",
    )
    _expect_equal(
        _normalise_sha256(formal.get("manifest_sha256")),
        hashes["formal_source_manifest"],
        "supplemental_formal_hash_mismatch",
        "supplemental manifest references another formal source",
    )
    dataset = _mapping(manifest.get("dataset"), "supplemental dataset binding")
    _expect_equal(
        _normalise_sha256(dataset.get("manifest_sha256")),
        hashes["supplemental_dataset_manifest"],
        "supplemental_dataset_hash_mismatch",
        "supplemental manifest references another dataset manifest",
    )
    _validate_admission_flags(manifest.get("admission"), "supplemental manifest")
    seeds = _mapping(manifest.get("seed_registries"), "seed registries")
    _expect_equal(
        seeds.get("canonical_seed_counts"),
        _EXPECTED_SEED_COUNTS,
        "supplemental_seed_counts_mismatch",
        "supplemental manifest is not split 60/20/20",
    )
    _expect_equal(
        seeds.get("reserved_evaluation_seeds"),
        list(range(1000, 1020)),
        "reserved_seed_contract_mismatch",
        "reserved seed inventory changed",
    )
    _expect_equal(
        seeds.get("reserved_seed_overlap"),
        [],
        "reserved_seed_leakage",
        "supplemental manifest overlaps reserved seeds",
    )
    balance = _class_balance(
        dataset.get("class_balance"),
        "manifest class balance",
        candidate_edges=_positive_int(
            dataset.get("candidate_edge_count"), "candidate edge count"
        ),
    )
    _expect_clean_balance(balance, "supplemental manifest")
    return {
        "episode_count": _positive_int(dataset.get("episode_count"), "episode count"),
        "candidate_edge_count": _positive_int(
            dataset.get("candidate_edge_count"), "candidate edge count"
        ),
        "class_balance": balance,
    }


def _validate_dataset_manifest(
    manifest: Mapping[str, Any],
    *,
    context: str,
    require_complete_labels: bool = True,
) -> dict[str, Any]:
    expected_schemas = {
        "schema_version": "d5.tracklet-dataset.v2",
        "graph_schema_version": "d5.sparse-tracklet-graph.v1",
        "node_feature_version": "d5.tracklet-node-features.v1",
        "edge_feature_version": "d5.tracklet-edge-features.v1",
        "evaluator_label_schema_version": "d5.tracklet-evaluator-labels.v1",
    }
    for key, expected in expected_schemas.items():
        _expect_equal(
            manifest.get(key),
            expected,
            "dataset_schema_mismatch",
            f"{context} field {key} changed",
        )
    split_policy = _mapping(manifest.get("split_policy"), f"{context} split policy")
    _expect(
        split_policy.get("edge_level_random_split") is False
        and split_policy.get("shared_seed_values_atomic_across_scenarios") is True
        and split_policy.get("unit")
        == "whole_episode_grouped_by_scenario_version_and_seed"
        and _nonnegative_int(split_policy.get("split_seed"), "split seed")
        == 20260720
        and math.isclose(
            _ratio(split_policy.get("validation_fraction"), "validation fraction"),
            0.2,
        )
        and math.isclose(
            _ratio(split_policy.get("test_fraction"), "test fraction"),
            0.2,
        ),
        "dataset_split_policy_mismatch",
        f"{context} does not use the frozen whole-seed split policy",
    )
    episodes = _sequence(manifest.get("episodes"), f"{context} episodes")
    _expect(bool(episodes), "dataset_empty", f"{context} contains no episodes")
    partition: dict[int, str] = {}
    totals = {
        "candidate_edges": 0,
        "positive_candidate_edges": 0,
        "negative_candidate_edges": 0,
        "unlabeled_candidate_edges": 0,
    }
    seen_uids: set[str] = set()
    for raw in episodes:
        item = _mapping(raw, f"{context} episode")
        uid = _required_string(item, "episode_uid")
        _expect(uid not in seen_uids, "duplicate_episode_uid", f"duplicate {uid}")
        seen_uids.add(uid)
        seed = _nonnegative_int(item.get("seed"), "episode seed")
        split = _required_string(item, "split")
        _expect(split in _SPLITS, "invalid_episode_split", f"invalid split {split}")
        _expect(
            seed not in partition or partition[seed] == split,
            "non_atomic_seed_split",
            f"seed {seed} occurs in multiple splits",
        )
        partition[seed] = split
        if require_complete_labels:
            _expect(
                item.get("labels_complete") is True
                and item.get("candidate_recall_available") is True,
                "incomplete_supplemental_episode_labels",
                "supplemental episode lacks complete labels or recall evidence",
            )
        balance = _class_balance(item.get("class_balance"), "episode class balance")
        _expect_equal(
            _nonnegative_int(item.get("edge_count"), "episode edge count"),
            balance["candidate_edges"],
            "episode_edge_count_mismatch",
            "episode edge count differs from class balance",
        )
        for key in totals:
            totals[key] += balance[key]
    _expect_equal(
        {split: sum(value == split for value in partition.values()) for split in _SPLITS},
        _EXPECTED_SEED_COUNTS,
        "dataset_seed_counts_mismatch",
        f"{context} does not contain 60/20/20 unique seeds",
    )
    _expect(
        not (_RESERVED_SEEDS & set(partition)),
        "reserved_seed_leakage",
        f"{context} contains reserved seed values",
    )
    reported_by_split = _mapping(
        manifest.get("class_balance_by_split"),
        f"{context} class balance by split",
    )
    reported_totals = {key: 0 for key in totals}
    for split in _SPLITS:
        balance = _class_balance(reported_by_split.get(split), f"{split} class balance")
        for key in reported_totals:
            reported_totals[key] += balance[key]
    _expect_equal(
        reported_totals,
        totals,
        "dataset_class_balance_mismatch",
        f"{context} class balance does not match episode descriptors",
    )
    if require_complete_labels:
        _expect_clean_balance(totals, context)
        availability = _mapping(
            manifest.get("candidate_recall_availability"),
            "candidate recall availability",
        )
        _expect(
            availability.get("status") == "available"
            and _nonnegative_int(
                availability.get("available_episode_count"),
                "available episode count",
            )
            == len(episodes)
            and _nonnegative_int(
                availability.get("episode_count"), "availability episode count"
            )
            == len(episodes),
            "candidate_recall_availability_incomplete",
            "supplemental candidate recall evidence is incomplete",
        )
    return {
        "episode_count": len(episodes),
        "unique_seed_count": len(partition),
        "class_balance": totals,
    }


def _validate_canonical_view(
    view: Mapping[str, Any],
    *,
    expected_source_sha256: str,
    context: str,
) -> dict[str, tuple[int, ...]]:
    _expect_equal(
        view.get("schema_version"),
        "d5.canonical-seed-split-view.v1",
        "canonical_view_schema_mismatch",
        f"{context} schema changed",
    )
    _expect_equal(
        view.get("consumer"),
        "tracklet_graph",
        "canonical_view_consumer_mismatch",
        f"{context} belongs to another consumer",
    )
    source = _mapping(view.get("source"), f"{context} source")
    _expect_equal(
        _normalise_sha256(source.get("manifest_sha256")),
        expected_source_sha256,
        "canonical_view_source_hash_mismatch",
        f"{context} references another source manifest",
    )
    contract = _mapping(view.get("view_contract"), f"{context} contract")
    _expect(
        contract.get("source_manifest_modified") is False
        and contract.get("source_artifacts_modified") is False
        and contract.get("complete_episode_rebucket_only") is True
        and contract.get("sample_copy_allowed") is False
        and contract.get("online_offline_content_rewrite_allowed") is False
        and contract.get("default_legacy_loader_unchanged") is True,
        "source_rewrite_detected",
        f"{context} does not preserve its source artifacts",
    )
    canonical = _mapping(view.get("canonical_split"), f"{context} split")
    return _validate_seed_partition(canonical, context=context)


def _validate_composite_view(
    view: Mapping[str, Any],
    *,
    formal_view: Mapping[str, Any],
    supplemental_view: Mapping[str, Any],
    formal_view_path: Path,
    supplemental_view_path: Path,
    artifact_hashes: Mapping[str, str],
    seed_partition: Mapping[str, tuple[int, ...]],
) -> dict[str, Any]:
    _expect_equal(
        view.get("schema_version"),
        "d5.tracklet-composite-admission-view.v1",
        "composite_view_schema_mismatch",
        "composite admission view schema changed",
    )
    _expect_equal(
        view.get("selection_policy_version"),
        "d5-tracklet-complete-label-source-selection-v1",
        "selection_policy_mismatch",
        "composite source-selection policy changed",
    )
    source_contract = _mapping(view.get("source_contract"), "source contract")
    _expect(
        source_contract.get("complete_seed_atomic_split_required") is True
        and source_contract.get("reserved_seed_allowed") is False
        and source_contract.get("sample_copy_allowed") is False
        and source_contract.get("source_artifact_modified") is False
        and source_contract.get("source_label_backfill_allowed") is False
        and source_contract.get("source_manifest_modified") is False,
        "source_rewrite_detected",
        "composite view does not preserve formal and supplemental sources",
    )
    sources = _mapping(view.get("sources"), "composite sources")
    _expect(
        sources.get("formal_source_modified") is False
        and sources.get("supplemental_source_modified") is False
        and sources.get("supplemental_source_repository_dirty") is False,
        "dirty_or_rewritten_source",
        "composite view reports a dirty or rewritten source",
    )
    _expect_equal(
        _normalise_sha256(sources.get("formal_manifest_sha256")),
        artifact_hashes["formal_source_manifest"],
        "composite_formal_hash_mismatch",
        "composite view references another formal source",
    )
    _expect_equal(
        _normalise_sha256(sources.get("supplemental_manifest_sha256")),
        artifact_hashes["supplemental_manifest"],
        "composite_supplemental_hash_mismatch",
        "composite view references another supplemental source",
    )
    subviews = _mapping(view.get("canonical_subviews"), "canonical subviews")
    for name, logical_name, payload, explicit_path in (
        ("formal", "formal_canonical_view", formal_view, formal_view_path),
        (
            "supplemental",
            "supplemental_canonical_view",
            supplemental_view,
            supplemental_view_path,
        ),
    ):
        binding = _mapping(subviews.get(name), f"{name} subview binding")
        _expect_equal(
            binding.get("file"),
            explicit_path.name,
            "canonical_subview_filename_mismatch",
            f"{name} subview filename binding changed",
        )
        _expect_equal(
            _normalise_sha256(binding.get("file_sha256")),
            artifact_hashes[logical_name],
            "canonical_subview_file_hash_mismatch",
            f"{name} subview file hash differs",
        )
        _expect_equal(
            _normalise_sha256(binding.get("content_sha256")),
            _normalise_sha256(payload.get("content_sha256")),
            "canonical_subview_content_hash_mismatch",
            f"{name} subview content hash differs",
        )
    selection = _mapping(view.get("selection"), "composite selection")
    _expect_equal(
        selection.get("seed_counts"),
        _EXPECTED_SEED_COUNTS,
        "composite_seed_counts_mismatch",
        "composite selection is not split 60/20/20",
    )
    _expect_equal(
        selection.get("reserved_evaluation_seed_overlap"),
        [],
        "reserved_seed_leakage",
        "composite selection contains reserved seeds",
    )
    _expect(
        _ratio(selection.get("label_availability_ratio"), "label availability")
        == 1.0
        and _nonnegative_int(
            selection.get("unlabeled_candidate_edge_count"),
            "unlabeled candidate edge count",
        )
        == 0,
        "composite_unlabeled_edges_present",
        "composite selected corpus is not fully labeled",
    )
    readiness = _mapping(view.get("readiness"), "composite readiness")
    _validate_readiness(readiness)
    selected = _mapping(readiness.get("selected_corpus"), "selected corpus")
    for key in (
        "episode_count",
        "candidate_edge_count",
        "unlabeled_candidate_edge_count",
        "label_availability_ratio",
        "seed_counts",
        "reserved_evaluation_seed_overlap",
        "training_set_sha256",
    ):
        if key in selection and key in selected:
            _expect_equal(
                selection[key],
                selected[key],
                "selection_readiness_mismatch",
                f"selection and readiness disagree on {key}",
            )
    positive = 0
    negative = 0
    split_summaries = _mapping(readiness.get("split_summaries"), "split summaries")
    for split in _SPLITS:
        item = _mapping(split_summaries.get(split), f"{split} summary")
        _expect(
            _positive_int(item.get("positive_candidate_edges"), "positive edges")
            > 0
            and _positive_int(item.get("negative_candidate_edges"), "negative edges")
            > 0
            and _nonnegative_int(item.get("unlabeled_candidate_edges"), "unlabeled")
            == 0,
            "composite_class_support_incomplete",
            f"{split} lacks positive/negative clean edge support",
        )
        positive += int(item["positive_candidate_edges"])
        negative += int(item["negative_candidate_edges"])
    candidate_count = _positive_int(
        selection.get("candidate_edge_count"), "selected candidate edge count"
    )
    _expect_equal(
        positive + negative,
        candidate_count,
        "composite_candidate_count_mismatch",
        "composite positive and negative edge counts do not sum to total",
    )
    _expect_sha(selection.get("training_set_sha256"), 64, "training source SHA")
    return {
        "episode_count": _positive_int(selection.get("episode_count"), "episode count"),
        "candidate_edge_count": candidate_count,
        "positive_edge_count": positive,
        "negative_edge_count": negative,
        "training_set_sha256": _normalise_sha256(
            selection.get("training_set_sha256")
        ),
        "seed_partition": seed_partition,
    }
def _validate_composite_admission(
    admission: Mapping[str, Any],
    *,
    view: Mapping[str, Any],
    selection: Mapping[str, Any],
    artifact_hashes: Mapping[str, str],
) -> None:
    _expect_equal(
        admission.get("schema_version"),
        "d5.tracklet-composite-admission-readiness.v1",
        "composite_admission_schema_mismatch",
        "composite admission schema changed",
    )
    _expect_equal(
        admission.get("criteria"),
        D5_CLEAN_GRAPH_CRITERIA,
        "admission_threshold_contract_mismatch",
        "D5 data/model admission thresholds were lowered or changed",
    )
    _expect_equal(
        _normalise_sha256(admission.get("view_manifest_sha256")),
        artifact_hashes["composite_view"],
        "admission_view_file_hash_mismatch",
        "composite admission references another view file",
    )
    _expect_equal(
        _normalise_sha256(admission.get("view_content_sha256")),
        _normalise_sha256(view.get("content_sha256")),
        "admission_view_content_hash_mismatch",
        "composite admission references another view content",
    )
    _validate_readiness(admission)
    selected = _mapping(admission.get("selected_corpus"), "admission selected corpus")
    _expect_equal(
        _nonnegative_int(selected.get("candidate_edge_count"), "candidate edge count"),
        selection["candidate_edge_count"],
        "admission_selection_mismatch",
        "composite admission and view disagree on candidate edges",
    )
    sources = _mapping(admission.get("sources"), "admission sources")
    _expect_equal(
        _normalise_sha256(sources.get("formal_manifest_sha256")),
        artifact_hashes["formal_source_manifest"],
        "admission_formal_hash_mismatch",
        "composite admission references another formal manifest",
    )
    _expect_equal(
        _normalise_sha256(sources.get("supplemental_manifest_sha256")),
        artifact_hashes["supplemental_manifest"],
        "admission_supplemental_hash_mismatch",
        "composite admission references another supplemental manifest",
    )


def _validate_readiness(readiness: Mapping[str, Any]) -> None:
    _expect_equal(
        readiness.get("schema_version"),
        "d5.tracklet-composite-admission-readiness.v1",
        "readiness_schema_mismatch",
        "composite readiness schema changed",
    )
    _expect_equal(
        readiness.get("criteria"),
        D5_CLEAN_GRAPH_CRITERIA,
        "admission_threshold_contract_mismatch",
        "D5 data/model admission thresholds were lowered or changed",
    )
    data_support = _mapping(readiness.get("data_support_readiness"), "data support")
    gates = _sequence(data_support.get("existing_gate_results"), "data gates")
    _expect(
        bool(gates)
        and all(_mapping(item, "data gate").get("passed") is True for item in gates)
        and data_support.get("passed") is True
        and data_support.get("status") == "pass"
        and data_support.get("label_availability_100_percent") is True,
        "data_support_gate_failed",
        "D5 clean graph data support gates are incomplete",
    )
    training = _mapping(readiness.get("training_readiness"), "training readiness")
    _expect(
        training.get("passed") is True
        and training.get("status") == "pass"
        and training.get("failure_reasons") == [],
        "training_source_gate_failed",
        "D5 clean graph training-source gate did not pass",
    )
    promotion = _mapping(readiness.get("promotion_readiness"), "promotion readiness")
    _expect(
        promotion.get("g1_assist_eligible") is False
        and promotion.get("model_training_performed") is False
        and promotion.get("pt_generated") is False
        and promotion.get("passed") is False
        and promotion.get("status") == "awaiting_new_model_evidence",
        "clean_data_overstated_as_model_promotion",
        "D5 clean data report overstates model promotion readiness",
    )
    safety = _mapping(readiness.get("identity_safety"), "identity safety")
    _expect(
        safety.get("deterministic_rule_fallback_preserved") is True
        and safety.get("geometry_gate_preserved") is True
        and safety.get("global_track_id_rewrite_allowed") is False
        and safety.get("same_camera_mutual_exclusion_preserved") is True
        and safety.get("model_output")
        == "same_target_probability_on_existing_candidate_edges_only",
        "identity_safety_contract_mismatch",
        "D5 clean graph evidence changes identity or fallback authority",
    )


def _validate_cross_source_counts(
    *,
    summary: Mapping[str, Any],
    supplemental_data: Mapping[str, Any],
    dataset_data: Mapping[str, Any],
    formal_data: Mapping[str, Any],
    selection: Mapping[str, Any],
) -> None:
    _expect_equal(
        _nonnegative_int(summary.get("episode_count"), "summary episode count"),
        supplemental_data["episode_count"],
        "summary_episode_count_mismatch",
        "summary and supplemental manifest disagree on episode count",
    )
    _expect_equal(
        _nonnegative_int(
            summary.get("candidate_edge_count"), "summary candidate edge count"
        ),
        supplemental_data["candidate_edge_count"],
        "summary_candidate_count_mismatch",
        "summary and supplemental manifest disagree on candidate edges",
    )
    _expect_equal(
        dataset_data["unique_seed_count"],
        100,
        "supplemental_unique_seed_count_mismatch",
        "supplemental dataset must contain 100 unique seeds",
    )
    _expect_equal(
        formal_data["unique_seed_count"],
        100,
        "formal_unique_seed_count_mismatch",
        "formal source must contain 100 unique seeds",
    )
    _expect(
        int(selection["episode_count"]) >= int(supplemental_data["episode_count"]),
        "composite_episode_count_too_small",
        "composite selection omits the admitted supplemental corpus",
    )


def _audit_model_bundle(
    inputs: D5CleanGraphEvidenceInputs,
    *,
    artifact_hashes: Mapping[str, str],
    training_source_sha256: str,
    test_seed_values: tuple[int, ...],
) -> dict[str, Any]:
    if not inputs.has_model_bundle:
        return _unavailable_layer("complete_model_evidence_bundle_not_supplied")
    assert inputs.model_report is not None
    report = _load_and_verify_content(inputs.model_report.path, "model report")
    expected_keys = {
        "schema_version",
        "content_sha256",
        "evaluation_date",
        "model_id",
        "weights_sha256",
        "config_sha256",
        "training_source_sha256",
        "test_seed_values",
        "test_metrics",
        "cell_metrics",
        "latency",
    }
    _require_exact_keys(report, expected_keys, "model report")
    _expect_equal(
        report.get("schema_version"),
        D5_GRAPH_MODEL_REPORT_SCHEMA_VERSION,
        "model_report_schema_mismatch",
        "D5 model report schema is unsupported",
    )
    _required_string(report, "evaluation_date")
    _required_string(report, "model_id")
    _expect_equal(
        _normalise_sha256(report.get("weights_sha256")),
        artifact_hashes["model_weights"],
        "model_weight_hash_mismatch",
        "model report weight SHA does not match the supplied weight file",
    )
    _expect_equal(
        _normalise_sha256(report.get("config_sha256")),
        artifact_hashes["model_config"],
        "model_config_hash_mismatch",
        "model report config SHA does not match the supplied config file",
    )
    _expect_equal(
        _normalise_sha256(report.get("training_source_sha256")),
        _normalise_sha256(training_source_sha256),
        "model_training_source_hash_mismatch",
        "model report was trained from another source view",
    )
    report_test_seeds = tuple(
        _nonnegative_int(value, "model test seed")
        for value in _sequence(report.get("test_seed_values"), "model test seeds")
    )
    _expect_equal(
        report_test_seeds,
        test_seed_values,
        "model_test_seed_partition_mismatch",
        "model internal test does not use the frozen test split",
    )
    metrics = _validate_metric_set(report.get("test_metrics"), "model test metrics")
    cells = _sequence(report.get("cell_metrics"), "model cell metrics")
    _expect_equal(
        len(cells),
        45,
        "model_cell_count_mismatch",
        "model report must contain exactly 45 scenario-scale cells",
    )
    cell_ids: set[str] = set()
    cell_sample_count = 0
    for raw in cells:
        item = _mapping(raw, "model cell metric")
        _require_exact_keys(
            item,
            {
                "cell_id",
                "scenario",
                "scale",
                "sample_count",
                "precision",
                "recall",
                "f1",
                "candidate_recall",
                "false_merge_rate",
                "ece",
            },
            "model cell metric",
        )
        cell_id = _required_string(item, "cell_id")
        _expect(
            cell_id not in cell_ids,
            "duplicate_model_cell",
            f"duplicate model cell {cell_id}",
        )
        cell_ids.add(cell_id)
        _required_string(item, "scenario")
        _positive_int(item.get("scale"), "cell scale")
        cell_sample_count += _positive_int(
            item.get("sample_count"), "cell sample count"
        )
        _validate_metric_set(item, "model cell metric", allow_extra_identity=True)
    latency = _mapping(report.get("latency"), "model latency")
    _require_exact_keys(
        latency,
        {"device", "sample_count", "p50_ms", "p95_ms", "max_ms"},
        "model latency",
    )
    device = _required_string(latency, "device")
    latency_samples = _positive_int(latency.get("sample_count"), "latency samples")
    p50 = _nonnegative_float(latency.get("p50_ms"), "p50 latency")
    p95 = _nonnegative_float(latency.get("p95_ms"), "p95 latency")
    maximum = _nonnegative_float(latency.get("max_ms"), "max latency")
    _expect(
        p50 <= p95 <= maximum,
        "model_latency_order_invalid",
        "model latency quantiles are not ordered",
    )
    passed = (
        metrics["precision"] >= D5_CLEAN_GRAPH_CRITERIA["minimum_test_precision"]
        and metrics["recall"] >= D5_CLEAN_GRAPH_CRITERIA["minimum_test_recall"]
        and metrics["f1"] >= D5_CLEAN_GRAPH_CRITERIA["minimum_test_f1"]
        and metrics["candidate_recall"]
        >= D5_CLEAN_GRAPH_CRITERIA["minimum_test_candidate_recall"]
        and metrics["false_merge_rate"]
        <= D5_CLEAN_GRAPH_CRITERIA["maximum_test_false_merge_rate"]
        and metrics["ece"] <= D5_CLEAN_GRAPH_CRITERIA["maximum_test_ece"]
        and p95
        <= D5_CLEAN_GRAPH_CRITERIA["maximum_p95_inference_latency_ms"]
    )
    return {
        "available": True,
        "status": "complete" if passed else "failed",
        "reason": (
            "complete_internal_model_test_thresholds_passed"
            if passed
            else "internal_model_test_thresholds_failed"
        ),
        "thresholds_passed": passed,
        "test_metrics": metrics,
        "cell_count": len(cells),
        "cell_sample_count": cell_sample_count,
        "latency": {
            "device": device,
            "sample_count": latency_samples,
            "p50_ms": p50,
            "p95_ms": p95,
            "max_ms": maximum,
        },
    }


def _audit_heldout_evidence(
    inputs: D5CleanGraphEvidenceInputs,
    *,
    artifact_hashes: Mapping[str, str],
    training_source_sha256: str,
) -> dict[str, Any]:
    if not inputs.has_heldout_evidence:
        return _unavailable_layer("held_out_seed_evaluation_not_supplied")
    assert inputs.heldout_evaluation_report is not None
    assert inputs.heldout_manifest is not None
    assert inputs.model_config is not None
    assert inputs.model_weights is not None

    manifest = _load_and_verify_d5_content(
        inputs.heldout_manifest.path,
        "held-out manifest",
    )
    manifest_summary = _validate_heldout_manifest(manifest)
    model_bundle = _validate_heldout_model_bundle_config(
        inputs.model_config.path,
        model_weights_path=inputs.model_weights.path,
        artifact_hashes=artifact_hashes,
        training_source_sha256=training_source_sha256,
    )
    report = _load_and_verify_d5_content(
        inputs.heldout_evaluation_report.path,
        "held-out evaluation report",
    )
    return _validate_heldout_report(
        report,
        manifest=manifest,
        manifest_summary=manifest_summary,
        model_bundle=model_bundle,
        artifact_hashes=artifact_hashes,
    )


def _validate_heldout_model_bundle_config(
    path: Path,
    *,
    model_weights_path: Path,
    artifact_hashes: Mapping[str, str],
    training_source_sha256: str,
) -> dict[str, Any]:
    payload = _load_json(path, "held-out model bundle manifest")
    _require_exact_keys(
        payload,
        {
            "schema_version",
            "model_semantic_version",
            "dataset_schema_version",
            "graph_schema_version",
            "node_feature_version",
            "edge_feature_version",
            "node_feature_names",
            "edge_feature_names",
            "architecture",
            "training_dataset",
            "code_provenance",
            "calibration",
            "validation_results",
            "weights",
            "admission",
        },
        "held-out model bundle manifest",
    )
    _expect_equal(
        payload.get("schema_version"),
        D5_TRACKLET_MODEL_BUNDLE_SCHEMA_VERSION,
        "heldout_model_bundle_schema_mismatch",
        "held-out evaluation must bind a D5 v3 tracklet model bundle",
    )
    _expect_equal(
        payload.get("model_semantic_version"),
        "1.0.0",
        "heldout_model_semantic_version_mismatch",
        "held-out model semantic version changed",
    )
    for name, expected in (
        ("dataset_schema_version", "d5.tracklet-dataset.v2"),
        ("graph_schema_version", "d5.sparse-tracklet-graph.v1"),
        ("node_feature_version", "d5.tracklet-node-features.v1"),
        ("edge_feature_version", "d5.tracklet-edge-features.v1"),
    ):
        _expect_equal(
            payload.get(name),
            expected,
            "heldout_model_feature_contract_mismatch",
            f"held-out model {name} changed",
        )
    _expect_equal(
        tuple(_sequence(payload.get("node_feature_names"), "model node features")),
        _MODEL_NODE_FEATURE_NAMES,
        "heldout_model_feature_contract_mismatch",
        "held-out model node feature order changed",
    )
    _expect_equal(
        tuple(_sequence(payload.get("edge_feature_names"), "model edge features")),
        _MODEL_EDGE_FEATURE_NAMES,
        "heldout_model_feature_contract_mismatch",
        "held-out model edge feature order changed",
    )

    architecture = _mapping(payload.get("architecture"), "model architecture")
    _require_exact_keys(
        architecture,
        {
            "class_name",
            "node_feature_dim",
            "edge_feature_dim",
            "hidden_dim",
            "message_passing_steps",
            "dropout",
        },
        "model architecture",
    )
    _expect_equal(
        architecture.get("class_name"),
        "NativeTrackletEdgeClassifier",
        "heldout_model_architecture_mismatch",
        "held-out model class changed",
    )
    _expect_equal(
        _positive_int(architecture.get("node_feature_dim"), "node feature dim"),
        len(_MODEL_NODE_FEATURE_NAMES),
        "heldout_model_architecture_mismatch",
        "held-out model node feature dimension changed",
    )
    _expect_equal(
        _positive_int(architecture.get("edge_feature_dim"), "edge feature dim"),
        len(_MODEL_EDGE_FEATURE_NAMES),
        "heldout_model_architecture_mismatch",
        "held-out model edge feature dimension changed",
    )
    _positive_int(architecture.get("hidden_dim"), "hidden dimension")
    _positive_int(
        architecture.get("message_passing_steps"),
        "message passing steps",
    )
    _ratio(architecture.get("dropout"), "model dropout")

    training = _normalised_sha_mapping(
        payload.get("training_dataset"),
        {
            "dataset_manifest_sha256",
            "split_sha256",
            "training_set_sha256",
            "training_config_sha256",
        },
        "model training dataset",
    )
    _expect_equal(
        training["training_set_sha256"],
        _normalise_sha256(training_source_sha256),
        "heldout_model_training_source_hash_mismatch",
        "held-out model bundle was trained from another clean composite view",
    )
    provenance = _mapping(payload.get("code_provenance"), "model code provenance")
    _require_exact_keys(
        provenance,
        {"implementation_sha256", "source_files"},
        "model code provenance",
    )
    source_files = _normalised_sha_mapping(
        provenance.get("source_files"),
        set(_MODEL_IMPLEMENTATION_FILES),
        "model source files",
    )
    _expect_equal(
        _normalise_sha256(provenance.get("implementation_sha256")),
        _d5_canonical_sha256(
            {
                name: source_files[name].removeprefix("sha256:")
                for name in sorted(source_files)
            }
        ),
        "heldout_model_implementation_hash_mismatch",
        "model implementation hash does not match its source inventory",
    )

    calibration = _mapping(payload.get("calibration"), "model calibration")
    _require_exact_keys(
        calibration,
        {
            "method",
            "source_split",
            "temperature",
            "decision_threshold",
            "threshold_objective",
        },
        "model calibration",
    )
    _expect(
        calibration.get("method") == "validation_only_scalar_temperature"
        and calibration.get("source_split") == "validation"
        and calibration.get("threshold_objective") == "validation_f1",
        "heldout_model_calibration_source_mismatch",
        "held-out temperature and threshold must be frozen on validation",
    )
    temperature = _nonnegative_float(
        calibration.get("temperature"),
        "model calibration temperature",
    )
    _expect(
        temperature > 0.0,
        "heldout_model_temperature_invalid",
        "model calibration temperature must be positive",
    )
    threshold = _ratio(
        calibration.get("decision_threshold"),
        "model decision threshold",
    )
    _mapping(payload.get("validation_results"), "model validation results")

    weights = _mapping(payload.get("weights"), "model weights metadata")
    _require_exact_keys(
        weights,
        {"filename", "format", "sha256", "size_bytes"},
        "model weights metadata",
    )
    _expect(
        weights.get("filename") == "weights.pt"
        and weights.get("format") == "pytorch_state_dict_weights_only",
        "heldout_model_weights_contract_mismatch",
        "held-out model weights metadata changed",
    )
    _expect_equal(
        _normalise_sha256(weights.get("sha256")),
        artifact_hashes["model_weights"],
        "heldout_model_weight_hash_mismatch",
        "model bundle manifest references other weights",
    )
    _expect_equal(
        _positive_int(weights.get("size_bytes"), "model weights size"),
        model_weights_path.stat().st_size,
        "heldout_model_weight_size_mismatch",
        "model bundle weights size differs from the supplied file",
    )

    admission = _mapping(payload.get("admission"), "model admission")
    _require_exact_keys(
        admission,
        {
            "status",
            "default_model",
            "g1_assist_eligible",
            "readiness_audit_sha256",
        },
        "model admission",
    )
    _expect(
        admission.get("status") == "development_only_fail_closed"
        and admission.get("default_model") is False
        and admission.get("g1_assist_eligible") is False,
        "heldout_model_authority_invalid",
        "held-out evaluation requires a fail-closed development bundle",
    )
    _normalise_sha256(admission.get("readiness_audit_sha256"))
    return {
        "temperature": temperature,
        "decision_threshold": threshold,
        "training_dataset": training,
        "admission_status": str(admission["status"]),
    }


def _validate_heldout_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    _require_exact_keys(
        manifest,
        {
            "schema_version",
            "evaluation_role",
            "created_at_utc",
            "profile",
            "training_split_registry_used",
            "source",
            "read_only_training_sources",
            "config",
            "candidate_gate",
            "evaluator_lineage",
            "episodes",
            "counts",
            "identity_and_truth_safety",
            "artifact_inventory",
            "artifact_inventory_sha256",
            "content_sha256",
        },
        "held-out manifest",
    )
    _expect_equal(
        manifest.get("schema_version"),
        D5_HELDOUT_CORPUS_SCHEMA_VERSION,
        "heldout_manifest_schema_mismatch",
        "D5 held-out corpus schema is unsupported",
    )
    _expect(
        manifest.get("evaluation_role") == _HELDOUT_ROLE
        and manifest.get("training_split_registry_used") is False,
        "heldout_manifest_role_mismatch",
        "held-out corpus entered a training split role",
    )
    _required_string(manifest, "created_at_utc")

    profile = _mapping(manifest.get("profile"), "held-out profile")
    _require_exact_keys(
        profile,
        {
            "profile_version",
            "evaluation_role",
            "seeds",
            "scenario_cells",
            "frames_per_seed_cell",
            "expected_frame_count",
            "training_split_registry_used",
        },
        "held-out profile",
    )
    _expect(
        profile.get("profile_version") == _HELDOUT_PROFILE_VERSION
        and profile.get("evaluation_role") == _HELDOUT_ROLE
        and profile.get("training_split_registry_used") is False,
        "heldout_profile_mismatch",
        "held-out corpus does not use the frozen full profile",
    )
    seeds = tuple(
        _nonnegative_int(value, "held-out seed")
        for value in _sequence(profile.get("seeds"), "held-out seeds")
    )
    _expect_equal(
        seeds,
        tuple(sorted(_RESERVED_SEEDS)),
        "heldout_seed_catalog_mismatch",
        "held-out corpus must use exactly seeds 1000-1019",
    )
    raw_cells = _sequence(profile.get("scenario_cells"), "held-out cells")
    cells: list[tuple[str, int]] = []
    for raw in raw_cells:
        item = _mapping(raw, "held-out cell")
        _require_exact_keys(item, {"scenario", "scale"}, "held-out cell")
        cells.append(
            (
                _required_string(item, "scenario"),
                _positive_int(item.get("scale"), "held-out cell scale"),
            )
        )
    _expect_equal(
        tuple(cells),
        _HELDOUT_CELLS,
        "heldout_cell_catalog_mismatch",
        "held-out corpus must use the frozen 45-cell catalog",
    )
    _expect(
        profile.get("frames_per_seed_cell") == 1
        and profile.get("expected_frame_count") == _HELDOUT_EPISODE_COUNT,
        "heldout_frame_profile_mismatch",
        "held-out corpus must contain one frame per seed/cell",
    )

    source = _mapping(manifest.get("source"), "held-out source")
    _require_exact_keys(
        source,
        {"git_commit", "repository_dirty", "implementation_sha256"},
        "held-out source",
    )
    _expect_sha(source.get("git_commit"), 40, "held-out source commit")
    _expect(
        source.get("repository_dirty") is False,
        "dirty_heldout_source",
        "formal held-out evidence must come from a clean repository",
    )
    _normalised_sha_mapping(
        source.get("implementation_sha256"),
        set(_HELDOUT_IMPLEMENTATION_FILES),
        "held-out source implementation",
    )
    _validate_heldout_training_source_bindings(
        manifest.get("read_only_training_sources")
    )

    config = _mapping(manifest.get("config"), "held-out config binding")
    _require_exact_keys(
        config,
        {"file", "sha256", "generation_config_sha256"},
        "held-out config binding",
    )
    _expect_equal(
        config.get("file"),
        "heldout_dataset/heldout_config.json",
        "heldout_config_path_mismatch",
        "held-out config path changed",
    )
    config_sha = _normalise_sha256(config.get("sha256"))
    generation_config_sha = _normalise_sha256(
        config.get("generation_config_sha256")
    )

    gate = _mapping(manifest.get("candidate_gate"), "held-out candidate gate")
    _require_exact_keys(
        gate,
        {"policy", "config", "config_sha256", "aggregate_counts"},
        "held-out candidate gate",
    )
    _expect(
        gate.get("policy") == "unchanged_sparse_tracklet_default"
        and gate.get("config") == _HELDOUT_DEFAULT_GATE_CONFIG,
        "heldout_candidate_gate_changed",
        "held-out corpus changed the frozen geometry gate",
    )
    gate_sha = _normalise_sha256(gate.get("config_sha256"))
    _expect_equal(
        gate_sha,
        _d5_canonical_sha256(_HELDOUT_DEFAULT_GATE_CONFIG),
        "heldout_candidate_gate_hash_mismatch",
        "held-out candidate gate hash is invalid",
    )
    _validate_nonnegative_counter(
        gate.get("aggregate_counts"),
        "held-out candidate gate counts",
    )

    lineage = _mapping(manifest.get("evaluator_lineage"), "held-out lineage")
    _require_exact_keys(
        lineage,
        {"file", "sha256", "record_count", "physically_separate_from_online_graph"},
        "held-out lineage",
    )
    _expect(
        lineage.get("file") == "evaluator/observation_lineage.json.gz"
        and lineage.get("physically_separate_from_online_graph") is True,
        "heldout_lineage_contract_mismatch",
        "held-out evaluator lineage is not physically separate",
    )
    lineage_sha = _normalise_sha256(lineage.get("sha256"))
    _positive_int(lineage.get("record_count"), "held-out lineage record count")

    raw_episodes = _sequence(manifest.get("episodes"), "held-out episodes")
    _expect_equal(
        len(raw_episodes),
        _HELDOUT_EPISODE_COUNT,
        "heldout_episode_count_mismatch",
        "held-out manifest must contain exactly 900 episodes",
    )
    episodes: list[Mapping[str, Any]] = []
    seen_uids: set[str] = set()
    seen_seed_cells: set[tuple[int, str, int]] = set()
    cell_edge_counts: dict[tuple[str, int], int] = {
        cell: 0 for cell in _HELDOUT_CELLS
    }
    aggregate_balance = {
        "candidate_edges": 0,
        "positive_candidate_edges": 0,
        "negative_candidate_edges": 0,
        "unlabeled_candidate_edges": 0,
    }
    node_count = 0
    edge_count = 0
    for raw in raw_episodes:
        item = _mapping(raw, "held-out episode")
        descriptor = _validate_heldout_episode_descriptor(
            item,
            expected_config_sha256=generation_config_sha,
            expected_gate_sha256=gate_sha,
        )
        uid = str(descriptor["episode_uid"])
        key = (
            int(descriptor["seed"]),
            str(descriptor["scenario"]),
            int(descriptor["scale"]),
        )
        _expect(
            uid not in seen_uids,
            "heldout_episode_duplicate",
            f"duplicate held-out episode {uid}",
        )
        _expect(
            key not in seen_seed_cells,
            "heldout_seed_cell_duplicate",
            f"duplicate held-out seed/cell {key}",
        )
        seen_uids.add(uid)
        seen_seed_cells.add(key)
        episodes.append(item)
        cell = (str(descriptor["scenario"]), int(descriptor["scale"]))
        cell_edge_counts[cell] += int(descriptor["edge_count"])
        node_count += int(descriptor["node_count"])
        edge_count += int(descriptor["edge_count"])
        for name in aggregate_balance:
            aggregate_balance[name] += int(descriptor["class_balance"][name])
    expected_seed_cells = {
        (seed, scenario, scale)
        for seed in _RESERVED_SEEDS
        for scenario, scale in _HELDOUT_CELLS
    }
    _expect_equal(
        seen_seed_cells,
        expected_seed_cells,
        "heldout_seed_cell_catalog_mismatch",
        "held-out episode directory is missing or adding a seed/cell",
    )
    _expect(
        all(value > 0 for value in cell_edge_counts.values()),
        "heldout_cell_edge_support_missing",
        "each held-out cell must contain labeled candidate edges",
    )

    counts = _mapping(manifest.get("counts"), "held-out counts")
    _require_exact_keys(
        counts,
        {
            "episode_count",
            "seed_count",
            "scenario_scale_cell_count",
            "node_count",
            "candidate_edge_count",
            "class_balance",
            "factor_counts",
        },
        "held-out counts",
    )
    _expect(
        counts.get("episode_count") == _HELDOUT_EPISODE_COUNT
        and counts.get("seed_count") == len(_RESERVED_SEEDS)
        and counts.get("scenario_scale_cell_count") == len(_HELDOUT_CELLS),
        "heldout_count_mismatch",
        "held-out count catalog differs from 900/20/45",
    )
    _expect_equal(
        _positive_int(counts.get("node_count"), "held-out node count"),
        node_count,
        "heldout_count_mismatch",
        "held-out node count differs from episode descriptors",
    )
    _expect_equal(
        _positive_int(
            counts.get("candidate_edge_count"),
            "held-out candidate edge count",
        ),
        edge_count,
        "heldout_count_mismatch",
        "held-out edge count differs from episode descriptors",
    )
    count_balance_payload = _mapping(
        counts.get("class_balance"),
        "held-out aggregate class balance",
    )
    _require_exact_keys(
        count_balance_payload,
        set(aggregate_balance),
        "held-out aggregate class balance",
    )
    count_balance = _class_balance(
        count_balance_payload,
        "held-out aggregate class balance",
        candidate_edges=edge_count,
    )
    _expect_equal(
        count_balance,
        aggregate_balance,
        "heldout_class_balance_mismatch",
        "held-out aggregate class balance differs from episodes",
    )
    _expect_clean_balance(count_balance, "held-out manifest")
    _validate_nonnegative_counter(counts.get("factor_counts"), "held-out factors")
    _validate_heldout_manifest_safety(manifest.get("identity_and_truth_safety"))
    _validate_heldout_artifact_inventory(
        manifest,
        episodes=episodes,
        config_sha256=config_sha,
        lineage_sha256=lineage_sha,
    )
    return {
        "episode_count": _HELDOUT_EPISODE_COUNT,
        "seed_count": len(_RESERVED_SEEDS),
        "cell_count": len(_HELDOUT_CELLS),
        "candidate_edge_count": edge_count,
        "cell_edge_counts": cell_edge_counts,
    }


def _validate_heldout_episode_descriptor(
    item: Mapping[str, Any],
    *,
    expected_config_sha256: str,
    expected_gate_sha256: str,
) -> dict[str, Any]:
    expected_keys = {
        "episode_uid",
        "scenario_version",
        "seed",
        "episode_id",
        "graph_file",
        "graph_sha256",
        "labels_file",
        "labels_sha256",
        "config_sha256",
        "node_count",
        "edge_count",
        "class_balance",
        "labels_complete",
        "candidate_recall_available",
        "hard_negative_provenance",
        "schema_version",
        "evaluation_role",
        "split",
        "scenario",
        "scale",
    }
    _require_exact_keys(item, expected_keys, "held-out episode")
    _expect(
        item.get("schema_version") == D5_HELDOUT_EPISODE_SCHEMA_VERSION
        and item.get("evaluation_role") == _HELDOUT_ROLE
        and item.get("split") == _HELDOUT_ROLE,
        "heldout_episode_role_mismatch",
        "held-out episode entered a training role or changed schema",
    )
    seed = _nonnegative_int(item.get("seed"), "held-out episode seed")
    scenario = _required_string(item, "scenario")
    scale = _positive_int(item.get("scale"), "held-out episode scale")
    _expect(
        seed in _RESERVED_SEEDS,
        "heldout_seed_catalog_mismatch",
        f"episode seed {seed} is outside 1000-1019",
    )
    _expect(
        (scenario, scale) in _HELDOUT_CELLS,
        "heldout_cell_catalog_mismatch",
        f"unknown held-out cell {scenario}:{scale}",
    )
    _expect_equal(
        item.get("scenario_version"),
        f"{scenario}-{scale}v{scale}-v1",
        "heldout_scenario_version_mismatch",
        "held-out scenario version differs from its cell",
    )
    uid = _required_string(item, "episode_uid")
    _expect(
        _required_string(item, "episode_id").startswith("d5-heldout-"),
        "heldout_episode_id_invalid",
        f"held-out episode id is invalid for {uid}",
    )
    _validate_relative_artifact_path(item.get("graph_file"), "held-out graph")
    _validate_relative_artifact_path(item.get("labels_file"), "held-out labels")
    graph_sha = _normalise_sha256(item.get("graph_sha256"))
    labels_sha = _normalise_sha256(item.get("labels_sha256"))
    _expect_equal(
        _normalise_sha256(item.get("config_sha256")),
        expected_config_sha256,
        "heldout_episode_config_hash_mismatch",
        "held-out episode was generated with another config",
    )
    node_count = _positive_int(item.get("node_count"), "held-out node count")
    edge_count = _positive_int(item.get("edge_count"), "held-out edge count")
    balance_payload = _mapping(item.get("class_balance"), "held-out class balance")
    _require_exact_keys(
        balance_payload,
        {
            "candidate_edges",
            "positive_candidate_edges",
            "negative_candidate_edges",
            "unlabeled_candidate_edges",
        },
        "held-out class balance",
    )
    balance = _class_balance(
        balance_payload,
        "held-out class balance",
        candidate_edges=edge_count,
    )
    _expect_clean_balance(balance, "held-out episode")
    _expect(
        item.get("labels_complete") is True
        and item.get("candidate_recall_available") is True,
        "heldout_labels_incomplete",
        f"held-out labels are incomplete for {uid}",
    )
    provenance = _mapping(
        item.get("hard_negative_provenance"),
        "held-out hard-negative provenance",
    )
    _require_exact_keys(
        provenance,
        {"source", "truth_use", "candidate_gate_config_sha256", "evaluation_role"},
        "held-out hard-negative provenance",
    )
    _expect(
        provenance.get("source")
        == "heldout_physical_projection_after_default_geometry_gates"
        and provenance.get("truth_use")
        == "offline_exact_observation_lineage_only"
        and provenance.get("evaluation_role") == _HELDOUT_ROLE,
        "heldout_truth_provenance_mismatch",
        "held-out hard-negative truth provenance changed",
    )
    _expect_equal(
        _normalise_sha256(provenance.get("candidate_gate_config_sha256")),
        expected_gate_sha256,
        "heldout_candidate_gate_hash_mismatch",
        "held-out episode references another candidate gate",
    )
    return {
        "episode_uid": uid,
        "seed": seed,
        "scenario": scenario,
        "scale": scale,
        "node_count": node_count,
        "edge_count": edge_count,
        "class_balance": balance,
        "graph_sha256": graph_sha,
        "labels_sha256": labels_sha,
    }


def _validate_heldout_training_source_bindings(value: Any) -> None:
    bindings = _mapping(value, "held-out read-only training sources")
    _require_exact_keys(
        bindings,
        {"formal", "supplemental", "samples_copied_or_rewritten"},
        "held-out read-only training sources",
    )
    _expect(
        bindings.get("samples_copied_or_rewritten") is False,
        "heldout_training_source_rewrite_detected",
        "held-out generation copied or rewrote training samples",
    )
    for name, expected_file in (
        ("formal", "manifest.json"),
        ("supplemental", "supplemental_manifest.json"),
    ):
        item = _mapping(bindings.get(name), f"held-out {name} source")
        _require_exact_keys(
            item,
            {"manifest_file", "manifest_sha256", "modified"},
            f"held-out {name} source",
        )
        _expect(
            item.get("manifest_file") == expected_file
            and item.get("modified") is False,
            "heldout_training_source_rewrite_detected",
            f"held-out {name} source was modified",
        )
        _normalise_sha256(item.get("manifest_sha256"))


def _validate_heldout_manifest_safety(value: Any) -> None:
    safety = _mapping(value, "held-out manifest safety")
    _require_exact_keys(
        safety,
        {
            "anonymous_online_tracklets",
            "online_truth_feature_count",
            "same_camera_candidate_edge_count",
            "global_track_id_created_or_rebound",
            "all_episodes_held_out_evaluation",
            "train_validation_test_assignment_count",
        },
        "held-out manifest safety",
    )
    _expect(
        safety.get("anonymous_online_tracklets") is True
        and safety.get("all_episodes_held_out_evaluation") is True,
        "heldout_online_identity_contract_mismatch",
        "held-out online tracklets are not anonymous held-out-only records",
    )
    _expect_equal(
        _nonnegative_int(
            safety.get("online_truth_feature_count"),
            "held-out online truth count",
        ),
        0,
        "heldout_online_truth_leakage",
        "held-out online graph contains truth features",
    )
    _expect_equal(
        _nonnegative_int(
            safety.get("same_camera_candidate_edge_count"),
            "held-out same-camera edge count",
        ),
        0,
        "heldout_same_camera_edge_leakage",
        "held-out graph contains same-camera candidate edges",
    )
    _expect(
        safety.get("global_track_id_created_or_rebound") is False,
        "heldout_global_track_id_rewrite",
        "held-out evaluation created or rebound global_track_id",
    )
    _expect_equal(
        _nonnegative_int(
            safety.get("train_validation_test_assignment_count"),
            "held-out training split assignment count",
        ),
        0,
        "heldout_training_split_assignment_detected",
        "held-out episodes were assigned to train/validation/test",
    )


def _validate_heldout_artifact_inventory(
    manifest: Mapping[str, Any],
    *,
    episodes: Sequence[Mapping[str, Any]],
    config_sha256: str,
    lineage_sha256: str,
) -> None:
    inventory = _sequence(
        manifest.get("artifact_inventory"),
        "held-out artifact inventory",
    )
    records: dict[str, dict[str, Any]] = {}
    canonical: list[dict[str, Any]] = []
    for raw in inventory:
        item = _mapping(raw, "held-out artifact inventory item")
        _require_exact_keys(
            item,
            {"path", "sha256", "size_bytes"},
            "held-out artifact inventory item",
        )
        relative = _validate_relative_artifact_path(
            item.get("path"),
            "held-out inventory artifact",
        )
        _expect(
            relative not in records,
            "heldout_artifact_inventory_duplicate",
            f"duplicate held-out inventory path {relative}",
        )
        raw_sha = _normalise_sha256(item.get("sha256")).removeprefix("sha256:")
        size = _positive_int(item.get("size_bytes"), "held-out artifact size")
        canonical_item = {
            "path": relative,
            "sha256": raw_sha,
            "size_bytes": size,
        }
        records[relative] = canonical_item
        canonical.append(canonical_item)

    expected_paths = {
        "heldout_dataset/heldout_config.json",
        "evaluator/observation_lineage.json.gz",
    }
    for descriptor in episodes:
        uid = str(descriptor["episode_uid"])
        expected_paths.update(
            {
                f"heldout_dataset/{descriptor['graph_file']}",
                f"heldout_dataset/{descriptor['labels_file']}",
                f"heldout_dataset/episodes/{uid}.episode.json",
            }
        )
    _expect_equal(
        set(records),
        expected_paths,
        "heldout_artifact_inventory_set_mismatch",
        "held-out artifact inventory does not exactly cover the 900-frame corpus",
    )
    _expect_equal(
        _normalise_sha256(
            records["heldout_dataset/heldout_config.json"]["sha256"]
        ),
        config_sha256,
        "heldout_config_hash_mismatch",
        "held-out config inventory hash differs from its binding",
    )
    _expect_equal(
        _normalise_sha256(
            records["evaluator/observation_lineage.json.gz"]["sha256"]
        ),
        lineage_sha256,
        "heldout_lineage_hash_mismatch",
        "held-out lineage inventory hash differs from its binding",
    )
    for descriptor in episodes:
        uid = str(descriptor["episode_uid"])
        graph_record = records[f"heldout_dataset/{descriptor['graph_file']}"]
        label_record = records[f"heldout_dataset/{descriptor['labels_file']}"]
        descriptor_record = records[
            f"heldout_dataset/episodes/{uid}.episode.json"
        ]
        _expect_equal(
            _normalise_sha256(graph_record["sha256"]),
            _normalise_sha256(descriptor.get("graph_sha256")),
            "heldout_graph_hash_binding_mismatch",
            f"held-out graph inventory differs for {uid}",
        )
        _expect_equal(
            _normalise_sha256(label_record["sha256"]),
            _normalise_sha256(descriptor.get("labels_sha256")),
            "heldout_label_hash_binding_mismatch",
            f"held-out label inventory differs for {uid}",
        )
        _expect_equal(
            _normalise_sha256(descriptor_record["sha256"]),
            _d5_canonical_sha256(descriptor),
            "heldout_descriptor_hash_binding_mismatch",
            f"held-out descriptor inventory differs for {uid}",
        )
    _expect_equal(
        _normalise_sha256(manifest.get("artifact_inventory_sha256")),
        _d5_canonical_sha256({"artifacts": canonical}),
        "heldout_artifact_inventory_hash_mismatch",
        "held-out artifact inventory digest is invalid",
    )


def _validate_heldout_report(
    report: Mapping[str, Any],
    *,
    manifest: Mapping[str, Any],
    manifest_summary: Mapping[str, Any],
    model_bundle: Mapping[str, Any],
    artifact_hashes: Mapping[str, str],
) -> dict[str, Any]:
    _require_exact_keys(
        report,
        {
            "schema_version",
            "evaluated_at_utc",
            "evaluation_role",
            "heldout_corpus",
            "development_model",
            "frozen_decision",
            "overall",
            "cell_metrics",
            "heldout_assessment",
            "identity_and_truth_safety",
            "layers",
            "implementation_sha256",
            "content_sha256",
        },
        "held-out evaluation report",
    )
    _expect_equal(
        report.get("schema_version"),
        D5_HELDOUT_EVALUATION_SCHEMA_VERSION,
        "heldout_report_schema_mismatch",
        "D5 held-out evaluation report schema is unsupported",
    )
    _required_string(report, "evaluated_at_utc")
    _expect_equal(
        report.get("evaluation_role"),
        _HELDOUT_ROLE,
        "heldout_report_role_mismatch",
        "D5 held-out report entered another evaluation role",
    )

    corpus = _mapping(report.get("heldout_corpus"), "held-out report corpus")
    _require_exact_keys(
        corpus,
        {
            "manifest_sha256",
            "manifest_content_sha256",
            "profile_version",
            "episode_count",
            "seed_values",
            "scenario_scale_cell_count",
        },
        "held-out report corpus",
    )
    _expect_equal(
        _normalise_sha256(corpus.get("manifest_sha256")),
        artifact_hashes["heldout_manifest"],
        "heldout_manifest_hash_mismatch",
        "held-out report references another manifest file",
    )
    _expect_equal(
        _normalise_sha256(corpus.get("manifest_content_sha256")),
        _normalise_sha256(manifest.get("content_sha256")),
        "heldout_manifest_content_hash_mismatch",
        "held-out report references another manifest content digest",
    )
    _expect(
        corpus.get("profile_version") == _HELDOUT_PROFILE_VERSION
        and corpus.get("episode_count") == _HELDOUT_EPISODE_COUNT
        and corpus.get("scenario_scale_cell_count") == len(_HELDOUT_CELLS),
        "heldout_report_corpus_count_mismatch",
        "held-out report corpus is not the frozen 900-frame profile",
    )
    report_seeds = tuple(
        _nonnegative_int(value, "held-out report seed")
        for value in _sequence(corpus.get("seed_values"), "held-out report seeds")
    )
    _expect_equal(
        report_seeds,
        tuple(sorted(_RESERVED_SEEDS)),
        "heldout_seed_catalog_mismatch",
        "held-out report must cover exactly seeds 1000-1019",
    )

    development = _mapping(
        report.get("development_model"),
        "held-out development model",
    )
    _require_exact_keys(
        development,
        {
            "model_id",
            "bundle_manifest_sha256",
            "weights_sha256",
            "training_dataset",
            "admission_status",
        },
        "held-out development model",
    )
    expected_model_id = (
        "d5-tracklet-development-"
        + artifact_hashes["model_weights"].removeprefix("sha256:")[:16]
    )
    _expect_equal(
        development.get("model_id"),
        expected_model_id,
        "heldout_model_id_mismatch",
        "held-out model id does not derive from the supplied weights",
    )
    _expect_equal(
        _normalise_sha256(development.get("bundle_manifest_sha256")),
        artifact_hashes["model_config"],
        "heldout_model_config_hash_mismatch",
        "held-out report references another model bundle manifest",
    )
    _expect_equal(
        _normalise_sha256(development.get("weights_sha256")),
        artifact_hashes["model_weights"],
        "heldout_model_weight_hash_mismatch",
        "held-out report references another model weight file",
    )
    report_training = _normalised_sha_mapping(
        development.get("training_dataset"),
        {
            "dataset_manifest_sha256",
            "split_sha256",
            "training_set_sha256",
            "training_config_sha256",
        },
        "held-out report training dataset",
    )
    _expect_equal(
        report_training,
        model_bundle["training_dataset"],
        "heldout_model_training_binding_mismatch",
        "held-out report and supplied model bundle use different training data",
    )
    _expect_equal(
        development.get("admission_status"),
        model_bundle["admission_status"],
        "heldout_model_admission_mismatch",
        "held-out report changed model admission status",
    )

    frozen = _mapping(report.get("frozen_decision"), "held-out frozen decision")
    _require_exact_keys(
        frozen,
        {
            "temperature",
            "decision_threshold",
            "source",
            "temperature_or_threshold_selection_performed",
            "weight_update_performed",
        },
        "held-out frozen decision",
    )
    _expect_equal(
        _nonnegative_float(frozen.get("temperature"), "held-out temperature"),
        model_bundle["temperature"],
        "heldout_temperature_reselection_detected",
        "held-out report did not use the frozen validation temperature",
    )
    _expect_equal(
        _ratio(frozen.get("decision_threshold"), "held-out threshold"),
        model_bundle["decision_threshold"],
        "heldout_threshold_reselection_detected",
        "held-out report did not use the frozen validation threshold",
    )
    _expect(
        frozen.get("source") == "development_bundle_validation_calibration"
        and frozen.get("temperature_or_threshold_selection_performed") is False,
        "heldout_threshold_reselection_detected",
        "held-out data selected a temperature or threshold",
    )
    _expect(
        frozen.get("weight_update_performed") is False,
        "heldout_weight_update_detected",
        "held-out evaluation updated model weights",
    )

    overall = _validate_heldout_metric_group(
        report.get("overall"),
        context="held-out overall metrics",
        expected_episode_count=_HELDOUT_EPISODE_COUNT,
        expected_labeled_edge_count=int(manifest_summary["candidate_edge_count"]),
        temperature=float(model_bundle["temperature"]),
        threshold=float(model_bundle["decision_threshold"]),
    )
    raw_cells = _sequence(report.get("cell_metrics"), "held-out cell metrics")
    _expect_equal(
        len(raw_cells),
        len(_HELDOUT_CELLS),
        "heldout_report_cell_count_mismatch",
        "held-out report must contain exactly 45 cell metrics",
    )
    cell_groups: list[dict[str, Any]] = []
    for index, expected_cell in enumerate(_HELDOUT_CELLS):
        raw = _mapping(raw_cells[index], "held-out cell metric")
        _require_exact_keys(
            raw,
            {
                "cell_id",
                "scenario",
                "scale",
                "episode_count",
                "complete_truth",
                "truth_scope",
                "labeled_candidate_edge_count",
                "decision_threshold",
                "temperature",
                "metrics",
                "latency",
            },
            "held-out cell metric",
        )
        scenario, scale = expected_cell
        _expect(
            raw.get("cell_id") == f"{scenario}-{scale}v{scale}"
            and raw.get("scenario") == scenario
            and raw.get("scale") == scale,
            "heldout_report_cell_catalog_mismatch",
            f"held-out cell metric {index} does not match the frozen catalog",
        )
        cell_groups.append(
            _validate_heldout_metric_group(
                {
                    key: value
                    for key, value in raw.items()
                    if key not in {"cell_id", "scenario", "scale"}
                },
                context=f"held-out cell {scenario}:{scale}",
                expected_episode_count=len(_RESERVED_SEEDS),
                expected_labeled_edge_count=int(
                    manifest_summary["cell_edge_counts"][expected_cell]
                ),
                temperature=float(model_bundle["temperature"]),
                threshold=float(model_bundle["decision_threshold"]),
            )
        )
    _expect_equal(
        sum(item["episode_count"] for item in cell_groups),
        overall["episode_count"],
        "heldout_report_episode_aggregate_mismatch",
        "held-out cell episode counts do not sum to the overall count",
    )
    _expect_equal(
        sum(item["labeled_candidate_edge_count"] for item in cell_groups),
        overall["labeled_candidate_edge_count"],
        "heldout_report_edge_aggregate_mismatch",
        "held-out cell edge counts do not sum to the overall count",
    )

    expected_assessment = _heldout_expected_assessment(
        overall["metrics"],
        tuple(
            (f"{scenario}-{scale}v{scale}", group["metrics"])
            for (scenario, scale), group in zip(
                _HELDOUT_CELLS,
                cell_groups,
                strict=True,
            )
        ),
    )
    assessment = _mapping(
        report.get("heldout_assessment"),
        "held-out assessment",
    )
    _require_exact_keys(
        assessment,
        set(expected_assessment),
        "held-out assessment",
    )
    _expect_equal(
        dict(assessment),
        expected_assessment,
        "heldout_assessment_mismatch",
        "held-out assessment does not match independently recomputed gates",
    )
    _validate_heldout_report_safety(report.get("identity_and_truth_safety"))
    _validate_heldout_report_layers(
        report.get("layers"),
        assessment=assessment,
    )
    _normalised_sha_mapping(
        report.get("implementation_sha256"),
        set(_HELDOUT_IMPLEMENTATION_FILES),
        "held-out evaluator implementation",
    )

    passed = bool(expected_assessment["passed"])
    return {
        "available": True,
        "status": "complete" if passed else "failed",
        "reason": (
            "held_out_seed_thresholds_passed"
            if passed
            else "held_out_seed_thresholds_failed"
        ),
        "producer_status": expected_assessment["status"],
        "thresholds_passed": passed,
        "episode_count": int(manifest_summary["episode_count"]),
        "seed_count": int(manifest_summary["seed_count"]),
        "cell_count": int(manifest_summary["cell_count"]),
        "overall_metrics": overall["metrics"],
        "frozen_decision": {
            "temperature": float(model_bundle["temperature"]),
            "decision_threshold": float(model_bundle["decision_threshold"]),
            "selection_performed": False,
            "weight_update_performed": False,
        },
        "paired_shadow_satisfied": False,
        "g1_assist_eligible": False,
        "authority_enabled": False,
    }


def _validate_heldout_metric_group(
    value: Any,
    *,
    context: str,
    expected_episode_count: int,
    expected_labeled_edge_count: int,
    temperature: float,
    threshold: float,
) -> dict[str, Any]:
    group = _mapping(value, context)
    _require_exact_keys(
        group,
        {
            "episode_count",
            "complete_truth",
            "truth_scope",
            "labeled_candidate_edge_count",
            "decision_threshold",
            "temperature",
            "metrics",
            "latency",
        },
        context,
    )
    episode_count = _positive_int(group.get("episode_count"), f"{context} episodes")
    edge_count = _positive_int(
        group.get("labeled_candidate_edge_count"),
        f"{context} labeled edges",
    )
    _expect_equal(
        episode_count,
        expected_episode_count,
        "heldout_report_episode_count_mismatch",
        f"{context} episode count differs from the manifest",
    )
    _expect_equal(
        edge_count,
        expected_labeled_edge_count,
        "heldout_report_edge_count_mismatch",
        f"{context} labeled edge count differs from the manifest",
    )
    _expect(
        group.get("complete_truth") is True
        and group.get("truth_scope") == "complete_graph_truth_evaluator_only",
        "heldout_truth_scope_mismatch",
        f"{context} does not use complete evaluator-only truth",
    )
    _expect_equal(
        _ratio(group.get("decision_threshold"), f"{context} threshold"),
        threshold,
        "heldout_threshold_reselection_detected",
        f"{context} changed the frozen validation threshold",
    )
    _expect_equal(
        _nonnegative_float(group.get("temperature"), f"{context} temperature"),
        temperature,
        "heldout_temperature_reselection_detected",
        f"{context} changed the frozen validation temperature",
    )
    metrics = _validate_heldout_metrics(group.get("metrics"), context)
    latency = _mapping(group.get("latency"), f"{context} latency")
    _require_exact_keys(
        latency,
        {"device", "sample_count", "p50_ms", "p95_ms", "max_ms"},
        f"{context} latency",
    )
    _required_string(latency, "device")
    _positive_int(latency.get("sample_count"), f"{context} latency samples")
    p50 = _nonnegative_float(latency.get("p50_ms"), f"{context} p50 latency")
    p95 = _nonnegative_float(latency.get("p95_ms"), f"{context} p95 latency")
    maximum = _nonnegative_float(latency.get("max_ms"), f"{context} max latency")
    _expect(
        p50 <= p95 <= maximum,
        "heldout_latency_order_invalid",
        f"{context} latency quantiles are not ordered",
    )
    _expect_equal(
        metrics["p50_inference_latency_ms"],
        {"available": True, "value": p50},
        "heldout_latency_metric_mismatch",
        f"{context} p50 latency metric differs from latency evidence",
    )
    _expect_equal(
        metrics["p95_inference_latency_ms"],
        {"available": True, "value": p95},
        "heldout_latency_metric_mismatch",
        f"{context} p95 latency metric differs from latency evidence",
    )
    return {
        "episode_count": episode_count,
        "labeled_candidate_edge_count": edge_count,
        "metrics": metrics,
    }


def _validate_heldout_metrics(value: Any, context: str) -> dict[str, Any]:
    metrics = _mapping(value, f"{context} metrics")
    expected_names = {
        "precision",
        "recall",
        "f1",
        "false_merge_rate",
        "candidate_recall",
        "brier_score",
        "ece",
        "p50_inference_latency_ms",
        "p95_inference_latency_ms",
    }
    _require_exact_keys(metrics, expected_names, f"{context} metrics")
    result: dict[str, Any] = {}
    for name in sorted(expected_names):
        item = _mapping(metrics.get(name), f"{context} metric {name}")
        available = item.get("available")
        _expect(
            type(available) is bool,
            "heldout_metric_availability_invalid",
            f"{context} metric {name} availability must be boolean",
        )
        if available:
            _require_exact_keys(
                item,
                {"available", "value"},
                f"{context} metric {name}",
            )
            if name.endswith("_latency_ms"):
                metric_value = _nonnegative_float(
                    item.get("value"),
                    f"{context} metric {name}",
                )
            else:
                metric_value = _ratio(
                    item.get("value"),
                    f"{context} metric {name}",
                )
            result[name] = {"available": True, "value": metric_value}
        else:
            _require_exact_keys(
                item,
                {"available", "value", "reason"},
                f"{context} metric {name}",
            )
            _expect(
                item.get("value") is None,
                "heldout_unavailable_metric_has_value",
                f"{context} unavailable metric {name} has a value",
            )
            result[name] = {
                "available": False,
                "value": None,
                "reason": _required_string(item, "reason"),
            }
    for required_available in (
        "brier_score",
        "ece",
        "p50_inference_latency_ms",
        "p95_inference_latency_ms",
    ):
        _expect(
            result[required_available]["available"] is True,
            "heldout_required_metric_unavailable",
            f"{context} metric {required_available} must be available",
        )
    return result


def _heldout_expected_assessment(
    overall_metrics: Mapping[str, Any],
    cells: Sequence[tuple[str, Mapping[str, Any]]],
) -> dict[str, Any]:
    limits = (
        (
            "precision",
            ">=",
            float(D5_CLEAN_GRAPH_CRITERIA["minimum_test_precision"]),
        ),
        (
            "recall",
            ">=",
            float(D5_CLEAN_GRAPH_CRITERIA["minimum_test_recall"]),
        ),
        ("f1", ">=", float(D5_CLEAN_GRAPH_CRITERIA["minimum_test_f1"])),
        (
            "false_merge_rate",
            "<=",
            float(D5_CLEAN_GRAPH_CRITERIA["maximum_test_false_merge_rate"]),
        ),
        (
            "candidate_recall",
            ">=",
            float(D5_CLEAN_GRAPH_CRITERIA["minimum_test_candidate_recall"]),
        ),
        ("ece", "<=", float(D5_CLEAN_GRAPH_CRITERIA["maximum_test_ece"])),
        (
            "p95_inference_latency_ms",
            "<=",
            float(
                D5_CLEAN_GRAPH_CRITERIA[
                    "maximum_p95_inference_latency_ms"
                ]
            ),
        ),
    )
    overall_gates = _heldout_metric_gates(overall_metrics, limits)
    cell_assessments: list[dict[str, Any]] = []
    for cell_id, metrics in cells:
        gates = _heldout_metric_gates(metrics, limits)
        cell_assessments.append(
            {
                "cell_id": cell_id,
                "gates": gates,
                "passed": all(bool(gate["passed"]) for gate in gates),
            }
        )
    passed = all(bool(gate["passed"]) for gate in overall_gates) and all(
        bool(item["passed"]) for item in cell_assessments
    )
    reasons = [
        f"overall:{gate['name']}"
        for gate in overall_gates
        if not bool(gate["passed"])
    ]
    reasons.extend(
        f"cell:{item['cell_id']}"
        for item in cell_assessments
        if not bool(item["passed"])
    )
    return {
        "status": "pass" if passed else "fail_closed",
        "passed": passed,
        "overall_gates": overall_gates,
        "cell_catalog_gate": {
            "actual": len(cells),
            "expected": len(_HELDOUT_CELLS),
            "passed": len(cells) == len(_HELDOUT_CELLS),
        },
        "cell_assessments": cell_assessments,
        "failure_reasons": reasons,
        "paired_shadow_satisfied": False,
        "g1_assist_eligible": False,
        "authority_enabled": False,
    }


def _heldout_metric_gates(
    metrics: Mapping[str, Any],
    limits: Sequence[tuple[str, str, float]],
) -> list[dict[str, Any]]:
    gates: list[dict[str, Any]] = []
    for name, operator, threshold in limits:
        metric = _mapping(metrics.get(name), f"held-out gate metric {name}")
        available = metric.get("available") is True
        raw_value = metric.get("value") if available else None
        passed = bool(
            available
            and raw_value is not None
            and (
                float(raw_value) >= threshold
                if operator == ">="
                else float(raw_value) <= threshold
            )
        )
        gates.append(
            {
                "name": name,
                "available": available,
                "value": raw_value,
                "operator": operator,
                "threshold": threshold,
                "passed": passed,
            }
        )
    return gates


def _validate_heldout_report_safety(value: Any) -> None:
    safety = _mapping(value, "held-out report safety")
    _require_exact_keys(
        safety,
        {
            "online_truth_feature_count",
            "same_camera_candidate_edge_count",
            "unlabeled_candidate_edge_count",
            "global_track_id_created_or_rebound",
            "truth_scope",
            "model_weights_unchanged",
            "model_config_unchanged",
            "heldout_corpus_unchanged",
        },
        "held-out report safety",
    )
    _expect_equal(
        _nonnegative_int(
            safety.get("online_truth_feature_count"),
            "held-out online truth count",
        ),
        0,
        "heldout_online_truth_leakage",
        "held-out report declares online truth use",
    )
    _expect_equal(
        _nonnegative_int(
            safety.get("same_camera_candidate_edge_count"),
            "held-out same-camera edge count",
        ),
        0,
        "heldout_same_camera_edge_leakage",
        "held-out report declares same-camera candidate edges",
    )
    _expect_equal(
        _nonnegative_int(
            safety.get("unlabeled_candidate_edge_count"),
            "held-out unlabeled edge count",
        ),
        0,
        "heldout_unlabeled_edge_leakage",
        "held-out report declares unlabeled candidate edges",
    )
    _expect(
        safety.get("global_track_id_created_or_rebound") is False,
        "heldout_global_track_id_rewrite",
        "held-out report declares global_track_id creation or rebinding",
    )
    _expect(
        safety.get("truth_scope") == "physically_separate_evaluator_only",
        "heldout_truth_scope_mismatch",
        "held-out report truth is not evaluator-only",
    )
    _expect(
        safety.get("model_weights_unchanged") is True
        and safety.get("model_config_unchanged") is True,
        "heldout_weight_update_detected",
        "held-out report declares model weights or config changed",
    )
    _expect(
        safety.get("heldout_corpus_unchanged") is True,
        "heldout_corpus_mutation_detected",
        "held-out report declares corpus mutation",
    )


def _validate_heldout_report_layers(
    value: Any,
    *,
    assessment: Mapping[str, Any],
) -> None:
    layers = _mapping(value, "held-out report layers")
    _require_exact_keys(
        layers,
        {
            "data_support",
            "internal_model_test",
            "held_out_1000_1019",
            "paired_shadow",
            "g1_assist_authority",
        },
        "held-out report layers",
    )
    expected_data = {"status": "pass", "passed": True}
    expected_internal = {
        "status": "source_bundle_development_only",
        "passed": False,
        "authority": False,
    }
    expected_shadow = {"status": "not_run", "passed": False}
    _expect_equal(
        layers.get("data_support"),
        expected_data,
        "heldout_layer_contract_mismatch",
        "held-out data support layer changed",
    )
    _expect_equal(
        layers.get("internal_model_test"),
        expected_internal,
        "heldout_layer_contract_mismatch",
        "held-out report overstated its internal test binding",
    )
    _expect_equal(
        layers.get("held_out_1000_1019"),
        assessment,
        "heldout_layer_contract_mismatch",
        "held-out layer does not reproduce the assessment",
    )
    _expect_equal(
        layers.get("paired_shadow"),
        expected_shadow,
        "heldout_paired_shadow_overstated",
        "held-out report falsely claims paired shadow evidence",
    )
    authority = _mapping(
        layers.get("g1_assist_authority"),
        "held-out authority layer",
    )
    _require_exact_keys(
        authority,
        {
            "status",
            "passed",
            "g1_assist_eligible",
            "assist_enabled",
            "authority_enabled",
            "blockers",
        },
        "held-out authority layer",
    )
    expected_blockers = [
        "paired_shadow_not_run",
        "internal_model_test_report_not_bound",
    ]
    if assessment.get("passed") is not True:
        expected_blockers.insert(0, "held_out_1000_1019_not_passed")
    _expect(
        authority.get("status") == "fail_closed"
        and authority.get("passed") is False
        and authority.get("g1_assist_eligible") is False
        and authority.get("assist_enabled") is False
        and authority.get("authority_enabled") is False
        and authority.get("blockers") == expected_blockers,
        "heldout_authority_overstated",
        "held-out report forged G1, assist, or authority admission",
    )


def _normalised_sha_mapping(
    value: Any,
    expected_keys: set[str],
    context: str,
) -> dict[str, str]:
    payload = _mapping(value, context)
    _require_exact_keys(payload, expected_keys, context)
    return {
        name: _normalise_sha256(payload[name])
        for name in sorted(expected_keys)
    }


def _validate_nonnegative_counter(value: Any, context: str) -> None:
    payload = _mapping(value, context)
    _expect(bool(payload), "counter_required", f"{context} must not be empty")
    for name, raw in payload.items():
        _expect(
            isinstance(name, str) and bool(name),
            "counter_key_invalid",
            f"{context} contains an invalid key",
        )
        _nonnegative_int(raw, f"{context} {name}")


def _validate_relative_artifact_path(value: Any, context: str) -> str:
    text = str(value)
    path = Path(text)
    _expect(
        bool(text)
        and not path.is_absolute()
        and ".." not in path.parts
        and path.as_posix() == text,
        "heldout_artifact_path_invalid",
        f"{context} path is not a safe relative POSIX path: {text!r}",
    )
    return text


def _validate_metric_set(
    value: Any,
    context: str,
    *,
    allow_extra_identity: bool = False,
) -> dict[str, float]:
    payload = _mapping(value, context)
    metric_names = {
        "precision",
        "recall",
        "f1",
        "candidate_recall",
        "false_merge_rate",
        "ece",
    }
    if not allow_extra_identity:
        _require_exact_keys(payload, metric_names, context)
    result = {name: _ratio(payload.get(name), f"{context} {name}") for name in metric_names}
    return dict(sorted(result.items()))


def _validate_seed_partition(
    canonical: Mapping[str, Any],
    *,
    context: str,
) -> dict[str, tuple[int, ...]]:
    _expect_equal(
        canonical.get("seed_counts"),
        _EXPECTED_SEED_COUNTS,
        "canonical_seed_counts_mismatch",
        f"{context} is not split 60/20/20",
    )
    values = _mapping(canonical.get("seed_values"), f"{context} seed values")
    result: dict[str, tuple[int, ...]] = {}
    union: set[int] = set()
    for split in _SPLITS:
        seeds = tuple(
            _nonnegative_int(value, f"{split} seed")
            for value in _sequence(values.get(split), f"{split} seeds")
        )
        _expect_equal(
            len(seeds),
            _EXPECTED_SEED_COUNTS[split],
            "canonical_seed_counts_mismatch",
            f"{context} {split} seed count differs",
        )
        _expect_equal(
            len(set(seeds)),
            len(seeds),
            "duplicate_seed_in_split",
            f"{context} {split} contains duplicate seeds",
        )
        _expect(
            not (union & set(seeds)),
            "seed_split_overlap",
            f"{context} seed occurs in multiple splits",
        )
        union.update(seeds)
        result[split] = seeds
    _expect_equal(
        len(union),
        100,
        "canonical_unique_seed_count_mismatch",
        f"{context} must contain 100 unique seeds",
    )
    _expect(
        not (_RESERVED_SEEDS & union),
        "reserved_seed_leakage",
        f"{context} contains reserved seed values",
    )
    _expect_equal(
        canonical.get("reserved_evaluation_seed_overlap"),
        [],
        "reserved_seed_leakage",
        f"{context} declares reserved seed overlap",
    )
    return result


def _validate_admission_flags(value: Any, context: str) -> None:
    admission = _mapping(value, f"{context} admission")
    _expect(
        admission.get("full_sample_audit_required") is True
        and admission.get("g1_assist_allowed") is False
        and admission.get("global_track_id_created_or_rebound") is False
        and admission.get("model_training_performed") is False
        and admission.get("producer_complete") is True
        and admission.get("pt_generated") is False,
        "producer_admission_overstated",
        f"{context} overstates model or identity authority",
    )


def _class_balance(
    value: Any,
    context: str,
    *,
    candidate_edges: int | None = None,
) -> dict[str, int]:
    payload = _mapping(value, context)
    result: dict[str, int] = {
        key: _nonnegative_int(payload.get(key), f"{context} {key}")
        for key in (
            "positive_candidate_edges",
            "negative_candidate_edges",
            "unlabeled_candidate_edges",
        )
    }
    class_total = sum(result.values())
    reported_candidate_edges = payload.get("candidate_edges")
    if reported_candidate_edges is None:
        _expect(
            candidate_edges is not None,
            "candidate_edge_count_missing",
            f"{context} has no candidate edge total",
        )
        result["candidate_edges"] = int(candidate_edges)
    else:
        result["candidate_edges"] = _nonnegative_int(
            reported_candidate_edges, f"{context} candidate_edges"
        )
        if candidate_edges is not None:
            _expect_equal(
                result["candidate_edges"],
                candidate_edges,
                "class_balance_candidate_count_mismatch",
                f"{context} candidate edge total differs from its parent",
            )
    _expect_equal(
        result["candidate_edges"],
        class_total,
        "class_balance_sum_mismatch",
        f"{context} does not sum to candidate edges",
    )
    return result


def _expect_clean_balance(balance: Mapping[str, int], context: str) -> None:
    _expect(
        int(balance["positive_candidate_edges"]) > 0
        and int(balance["negative_candidate_edges"]) > 0
        and int(balance["unlabeled_candidate_edges"]) == 0,
        "clean_edge_support_incomplete",
        f"{context} lacks positive/negative support or contains unlabeled edges",
    )


def _unavailable_layer(reason: str) -> dict[str, Any]:
    return {"available": False, "status": "unavailable", "reason": reason}


def _artifact_from_mapping(
    value: Any,
    *,
    name: str,
    base_dir: Path | None,
) -> D5CleanGraphArtifact:
    payload = _mapping(value, f"artifact {name}")
    _require_exact_keys(payload, {"path", "sha256"}, f"artifact {name}")
    path = Path(_required_string(payload, "path"))
    if not path.is_absolute() and base_dir is not None:
        path = base_dir / path
    return D5CleanGraphArtifact(path, str(payload.get("sha256", "")))


def _load_and_verify_content(path: Path, context: str) -> Mapping[str, Any]:
    payload = _load_json(path, context)
    claimed = _normalise_sha256(payload.get("content_sha256"))
    unsigned = dict(payload)
    unsigned.pop("content_sha256", None)
    actual = _canonical_sha256(unsigned)
    _expect_equal(
        claimed,
        actual,
        "content_sha256_mismatch",
        f"{context} internal content SHA-256 is invalid",
    )
    return payload


def _load_and_verify_d5_content(path: Path, context: str) -> Mapping[str, Any]:
    """Verify D5 canonical JSON, whose digest includes its final newline."""

    payload = _load_json(path, context)
    claimed = _normalise_sha256(payload.get("content_sha256"))
    unsigned = dict(payload)
    unsigned.pop("content_sha256", None)
    _expect_equal(
        claimed,
        _d5_canonical_sha256(unsigned),
        "content_sha256_mismatch",
        f"{context} internal D5 content SHA-256 is invalid",
    )
    return payload


def _verify_file(path: Path, expected: Any, name: str) -> str:
    _expect(path.is_file(), "input_file_missing", f"missing {name}: {path}")
    expected_sha = _normalise_sha256(expected)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    actual = f"sha256:{digest}"
    _expect_equal(
        actual,
        expected_sha,
        f"{name}_sha256_mismatch",
        f"{name} file SHA-256 differs from the caller-supplied digest",
    )
    return actual


def _canonical_sha256(value: Any) -> str:
    try:
        encoded = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        _fail("canonical_json_failed", str(exc))
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _d5_canonical_sha256(value: Any) -> str:
    try:
        encoded = (
            json.dumps(
                value,
                allow_nan=False,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        _fail("canonical_json_failed", str(exc))
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _normalise_sha256(value: Any) -> str:
    match = _SHA_RE.fullmatch(str(value).strip())
    if match is None:
        _fail("invalid_sha256", f"invalid SHA-256 value: {value!r}")
    return f"sha256:{match.group(1).lower()}"


def _expect_sha(value: Any, length: int, context: str) -> None:
    text = str(value).strip().lower()
    _expect(
        len(text) == length and all(char in "0123456789abcdef" for char in text),
        "invalid_source_identity",
        f"{context} is not a {length}-character hexadecimal identity",
    )


def _load_json(path: Path, context: str) -> Mapping[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except D5CleanGraphEvidenceError:
        raise
    except Exception as exc:
        _fail("json_load_failed", f"cannot load {context}: {exc}")
    return _mapping(value, context)


def _unique_object(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _expect(
            key not in result,
            "duplicate_json_key",
            f"duplicate JSON key {key}",
        )
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    _fail("nonfinite_json_number", f"non-finite JSON number {value}")


def _mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("mapping_required", f"{context} must be an object")
    return value


def _sequence(value: Any, context: str) -> Sequence[Any]:
    if not isinstance(value, list):
        _fail("list_required", f"{context} must be a list")
    return value


def _required_string(payload: Mapping[str, Any], name: str) -> str:
    value = payload.get(name)
    _expect(
        isinstance(value, str) and bool(value.strip()),
        "string_required",
        f"{name} must be a non-empty string",
    )
    return str(value).strip()


def _nonnegative_int(value: Any, context: str) -> int:
    _expect(
        isinstance(value, int) and not isinstance(value, bool) and value >= 0,
        "nonnegative_integer_required",
        f"{context} must be a non-negative integer",
    )
    return int(value)


def _positive_int(value: Any, context: str) -> int:
    result = _nonnegative_int(value, context)
    _expect(result > 0, "positive_integer_required", f"{context} must be positive")
    return result


def _nonnegative_float(value: Any, context: str) -> float:
    _expect(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) >= 0.0,
        "nonnegative_number_required",
        f"{context} must be finite and non-negative",
    )
    return float(value)


def _ratio(value: Any, context: str) -> float:
    result = _nonnegative_float(value, context)
    _expect(result <= 1.0, "ratio_out_of_range", f"{context} must be <= 1")
    return result


def _require_exact_keys(
    payload: Mapping[str, Any],
    expected: set[str],
    context: str,
) -> None:
    actual = set(payload)
    _expect(
        actual == expected,
        "object_keys_mismatch",
        f"{context} keys differ; missing={sorted(expected-actual)}, extra={sorted(actual-expected)}",
    )


def _expect_equal(
    actual: Any,
    expected: Any,
    code: str,
    message: str,
) -> None:
    _expect(actual == expected, code, message)


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    _write_text_atomic(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def _write_text_atomic(path: Path, text: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _expect(condition: bool, code: str, message: str) -> None:
    if not condition:
        _fail(code, message)


def _fail(code: str, message: str) -> None:
    raise D5CleanGraphEvidenceError(code, message)


__all__ = [
    "D5_CLEAN_GRAPH_CRITERIA",
    "D5_CLEAN_GRAPH_EVIDENCE_DATE",
    "D5_CLEAN_GRAPH_EVIDENCE_SCHEMA_VERSION",
    "D5_CLEAN_GRAPH_INPUT_SCHEMA_VERSION",
    "D5_GRAPH_MODEL_REPORT_SCHEMA_VERSION",
    "D5CleanGraphArtifact",
    "D5CleanGraphEvidenceError",
    "D5CleanGraphEvidenceInputs",
    "audit_d5_clean_graph_evidence",
    "load_d5_clean_graph_evidence_inputs",
    "render_d5_clean_graph_evidence_markdown",
    "write_d5_clean_graph_evidence_report",
]
