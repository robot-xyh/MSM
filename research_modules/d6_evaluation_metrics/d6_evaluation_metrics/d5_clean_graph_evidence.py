"""Strict read-only admission layers for D5 clean cross-view graph data."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence


D5_CLEAN_GRAPH_INPUT_SCHEMA_VERSION = "d6.d5-clean-graph-inputs.v1"
D5_CLEAN_GRAPH_EVIDENCE_SCHEMA_VERSION = "d6.d5-clean-graph-evidence.v1"
D5_CLEAN_GRAPH_EVIDENCE_DATE = "2026-07-21"
D5_GRAPH_MODEL_REPORT_SCHEMA_VERSION = "d5.tracklet-graph-model-evaluation.v1"

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
_SHA_RE = re.compile(r"^(?:sha256:)?([0-9a-fA-F]{64})$")
_EXPECTED_SEED_COUNTS = {"train": 60, "validation": 20, "test": 20}
_RESERVED_SEEDS = frozenset(range(1000, 1020))
_SPLITS = ("train", "validation", "test")


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
    """Explicit D5 data artifacts and an optional complete model bundle."""

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
    schema_version: str = D5_CLEAN_GRAPH_INPUT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != D5_CLEAN_GRAPH_INPUT_SCHEMA_VERSION:
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

    @property
    def has_model_bundle(self) -> bool:
        return self.model_report is not None

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
        return D5CleanGraphEvidenceInputs(**values)

    def to_dict(self) -> dict[str, Any]:
        return {
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

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
        *,
        base_dir: str | Path | None = None,
    ) -> "D5CleanGraphEvidenceInputs":
        _require_exact_keys(
            payload,
            {"schema_version", "artifacts", "model_evidence"},
            "D5 clean graph input specification",
        )
        _expect(
            payload.get("schema_version") == D5_CLEAN_GRAPH_INPUT_SCHEMA_VERSION,
            "input_schema_mismatch",
            "D5 clean graph input specification schema is unsupported",
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
        return cls(**values)


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
        "held_out_seed": _unavailable_layer(
            "held_out_seed_evaluation_not_supplied"
        ),
        "paired_shadow": _unavailable_layer(
            "same_seed_paired_shadow_not_supplied"
        ),
    }
    promotion_blockers = []
    if not model_layer["available"]:
        promotion_blockers.append("internal_model_test_unavailable")
    elif model_layer["status"] != "complete":
        promotion_blockers.append("internal_model_test_thresholds_failed")
    promotion_blockers.extend(
        [
            "held_out_seed_evaluation_unavailable",
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
        for name in (*_REQUIRED_ARTIFACT_NAMES, *_MODEL_ARTIFACT_NAMES)
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
    """Render the six-layer boundary without treating data as model evidence."""

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
        "数据支持和训练来源为 complete。当前没有完整模型内部测试、保留 seed 或同 seed 配对影子证据。",
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
