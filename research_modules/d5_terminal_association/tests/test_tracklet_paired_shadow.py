from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import torch

import d5_terminal_association.tracklet_paired_shadow as paired_shadow_module
from d5_terminal_association.scalable_3d_adapter import Scalable3DAdapterConfig
from d5_terminal_association.tracklet_gnn import NativeTrackletEdgeClassifier
from d5_terminal_association.tracklet_heldout_evaluation import (
    HELDOUT_SMOKE_PROFILE_VERSION,
    HeldoutEvaluationPolicy,
    HeldoutGenerationConfig,
    evaluate_heldout_development_bundle,
    generate_tracklet_heldout_corpus,
    load_tracklet_heldout_corpus,
)
from d5_terminal_association.tracklet_model_bundle import (
    load_tracklet_model_bundle,
    write_tracklet_model_bundle,
)
from d5_terminal_association.tracklet_paired_shadow import (
    PAIRED_SHADOW_LINEAGE_FILENAME,
    PAIRED_SHADOW_REPORT_FILENAME,
    PairedShadowInputSpec,
    TrackletPairedShadowError,
    run_tracklet_paired_shadow,
)
from d5_terminal_association.tracklet_supplemental_curriculum import (
    FORMAL_SCENARIO_CELLS,
)


@pytest.fixture(scope="module")
def paired_shadow_fixture(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("tracklet-paired-shadow")
    formal = root / "formal"
    supplemental = root / "supplemental"
    formal.mkdir()
    supplemental.mkdir()
    _write_json(formal / "manifest.json", {"schema_version": "formal-test-source.v1"})
    _write_json(
        supplemental / "supplemental_manifest.json",
        {"schema_version": "supplemental-test-source.v1"},
    )
    corpus = root / "heldout"
    generate_tracklet_heldout_corpus(
        corpus,
        formal_dataset_dir=formal,
        supplemental_root=supplemental,
        created_at_utc="2026-07-21T12:00:00Z",
        source_git_commit="a" * 40,
        source_repository_dirty=True,
        config=HeldoutGenerationConfig(
            profile_version=HELDOUT_SMOKE_PROFILE_VERSION,
            seeds=(1000,),
            scenario_cells=(FORMAL_SCENARIO_CELLS[0], FORMAL_SCENARIO_CELLS[1]),
        ),
    )
    bundle = root / "bundle"
    torch.manual_seed(7)
    write_tracklet_model_bundle(
        bundle,
        NativeTrackletEdgeClassifier(hidden_dim=8, message_passing_steps=1),
        dataset_manifest_sha256="a" * 64,
        split_sha256="b" * 64,
        training_set_sha256="c" * 64,
        training_config_sha256="d" * 64,
        calibration_temperature=1.0,
        decision_threshold=0.6,
        validation_results={"f1": {"available": True, "value": 0.8}},
        admission_status="development_only_fail_closed",
        readiness_audit_sha256="e" * 64,
    )
    heldout_evaluation = root / "heldout-evaluation"
    evaluate_heldout_development_bundle(
        corpus,
        bundle,
        heldout_evaluation,
        evaluated_at_utc="2026-07-21T12:10:00Z",
        policy=HeldoutEvaluationPolicy(latency_repeats=1),
        require_full_profile=False,
    )
    return {
        "root": root,
        "corpus": corpus,
        "bundle": bundle,
        "heldout_report": heldout_evaluation / "heldout_evaluation.json",
    }


def test_paired_shadow_uses_identical_graphs_and_keeps_authority_closed(
    paired_shadow_fixture: dict[str, Path], tmp_path: Path
) -> None:
    output = tmp_path / "paired-output"
    report = run_tracklet_paired_shadow(
        _spec(paired_shadow_fixture, output)
    )

    assert report["execution_completed"] is True
    assert report["totals"]["episode_count"] == 2
    assert report["totals"]["seed_count"] == 1
    assert report["totals"]["scenario_scale_cell_count"] == 2
    assert report["catalog_integrity"]["complete"] is True
    assert report["catalog_integrity"]["actual_frame_count"] == 2
    assert report["graph_identity"]["graph_identity_ratio"] == 1.0
    assert report["graph_identity"]["candidate_identity_ratio"] == 1.0
    assert report["graph_identity"]["label_identity_ratio"] == 1.0
    assert report["graph_identity"]["model_candidate_edges_added_or_removed"] == 0
    assert report["overall"]["control"]["candidate_coverage"] == report["overall"][
        "model"
    ]["candidate_coverage"]
    assert report["identity_and_truth_safety"]["online_truth_feature_count"] == 0
    assert report["identity_and_truth_safety"]["same_camera_candidate_edge_count"] == 0
    assert report["identity_and_truth_safety"][
        "truth_scoring_after_both_arm_predictions_count"
    ] == 2
    assert report["identity_and_truth_safety"]["unlabeled_candidate_edge_count"] == 0
    assert report["identity_and_truth_safety"]["global_track_id_rewrite_count"] == 0
    assert report["authority"] == {
        "status": "pending_d6_external_audit",
        "paired_shadow_passed": report["paired_shadow_assessment"]["passed"],
        "g1": False,
        "assist": False,
        "authority": False,
        "rule_fallback": True,
        "runtime_default_changed": False,
    }
    diagnostics = report["feature_label_diagnostics"]
    assert diagnostics["scope"] == "post_prediction_evaluator_only"
    assert diagnostics["interpretation_scope"] == (
        "dataset_separability_not_model_feature_attribution"
    )
    assert diagnostics["changes_to_frozen_evaluation"] == {
        "candidate_gate_changed": False,
        "threshold_reselected": False,
        "temperature_reestimated": False,
        "weights_updated": False,
        "predictions_recomputed_for_diagnostics": False,
    }
    for arm in ("control", "model"):
        strata = report["overall"][arm]["edge_by_shared_global_track_count"]
        assert strata["0"]["edge_count"] + strata["1"]["edge_count"] + strata[
            "other"
        ]["edge_count"] == report["totals"]["candidate_edge_count"]
    lineage = (output / PAIRED_SHADOW_LINEAGE_FILENAME).read_text().splitlines()
    assert len(lineage) == 2
    for raw in lineage:
        item = json.loads(raw)
        assert item["loaded_graph_instance_count"] == 1
        assert item["control_graph_sha256"] == item["model_graph_sha256"]
        assert item["control_candidate_edge_sha256"] == item[
            "model_candidate_edge_sha256"
        ]
        assert item["control_labels_sha256"] == item["model_labels_sha256"]
        assert item["source_arrays_sha256"] == item["graph_after_control_sha256"]
        assert item["source_arrays_sha256"] == item["graph_after_model_sha256"]
        assert item["source_arrays_sha256"] == item[
            "graph_after_clustering_sha256"
        ]
        assert item["truth_scoring_started_after_both_arm_predictions"] is True
        assert item["same_camera_candidate_edge_count"] == 0


def test_evaluator_truth_scoring_waits_for_both_arms_and_reuses_graph_instance(
    paired_shadow_fixture: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    corpus = load_tracklet_heldout_corpus(
        paired_shadow_fixture["corpus"], require_full_profile=False
    )
    base_episode = corpus.episodes[0]
    scorer = load_tracklet_model_bundle(paired_shadow_fixture["bundle"])
    state: dict[str, object] = {
        "rule_completed": False,
        "model_completed": False,
        "label_access_count": 0,
    }
    original_rule = paired_shadow_module._deterministic_edge_probabilities

    def observed_rule(graph, config):
        state["rule_graph_id"] = id(graph)
        result = original_rule(graph, config)
        state["rule_completed"] = True
        return result

    class ObservedScorer:
        device = scorer.device
        decision_threshold = scorer.decision_threshold

        def forward_graph(self, graph):
            state["model_graph_id"] = id(graph)
            result = scorer.forward_graph(graph)
            state["model_completed"] = True
            return result

    class GuardedEpisode:
        graph = base_episode.graph
        graph_sha256 = base_episode.graph_sha256
        labels_sha256 = base_episode.labels_sha256
        scenario = base_episode.scenario
        scale = base_episode.scale

        @property
        def evaluator_labels(self):
            assert state["rule_completed"] is True
            assert state["model_completed"] is True
            state["label_access_count"] = int(state["label_access_count"]) + 1
            return base_episode.evaluator_labels

    monkeypatch.setattr(
        paired_shadow_module,
        "_deterministic_edge_probabilities",
        observed_rule,
    )
    record = paired_shadow_module._evaluate_episode(
        GuardedEpisode(),
        scorer=ObservedScorer(),
        rule_config=Scalable3DAdapterConfig(),
    )

    assert state["label_access_count"] == 1
    assert state["rule_graph_id"] == state["model_graph_id"]
    assert record["loaded_graph_instance_count"] == 1
    assert record["truth_scoring_started_after_both_arm_predictions"] is True


def test_wrong_out_of_band_hash_atomically_reports_fail_closed(
    paired_shadow_fixture: dict[str, Path], tmp_path: Path
) -> None:
    output = tmp_path / "hash-failure"
    spec = _spec(paired_shadow_fixture, output)
    bad = PairedShadowInputSpec(
        **{
            **spec.__dict__,
            "expected_bundle_weights_sha256": "0" * 64,
        }
    )

    report = run_tracklet_paired_shadow(bad)

    assert report["execution_completed"] is False
    assert report["status"] == "fail_closed"
    assert report["paired_shadow_assessment"]["failure_reasons"] == [
        "bundle_weights_sha256_mismatch"
    ]
    assert (output / PAIRED_SHADOW_REPORT_FILENAME).is_file()
    assert (output / PAIRED_SHADOW_LINEAGE_FILENAME).read_bytes() == b""
    assert report["authority"]["g1"] is False
    assert report["authority"]["assist"] is False
    assert report["authority"]["authority"] is False
    assert report["authority"]["rule_fallback"] is True


def test_authoritative_output_preserves_and_hash_binds_superseded_evidence(
    paired_shadow_fixture: dict[str, Path], tmp_path: Path
) -> None:
    superseded = tmp_path / "superseded"
    superseded.mkdir()
    old_report = superseded / PAIRED_SHADOW_REPORT_FILENAME
    old_lineage = superseded / PAIRED_SHADOW_LINEAGE_FILENAME
    old_report.write_text('{"old":true}\n', encoding="utf-8")
    old_lineage.write_text('{"old_record":true}\n', encoding="utf-8")
    output = tmp_path / "authoritative"
    base = _spec(paired_shadow_fixture, output)
    spec = PairedShadowInputSpec(
        **{
            **base.__dict__,
            "superseded_output_dir": superseded,
            "expected_superseded_report_sha256": _sha256_file(old_report),
            "expected_superseded_lineage_sha256": _sha256_file(old_lineage),
        }
    )

    report = run_tracklet_paired_shadow(spec)

    assert report["evidence_status"]["status"] == "authoritative"
    assert report["evidence_status"]["supersedes"] == [
        {
            "directory": str(superseded.resolve()),
            "status": "superseded_preserved",
            "report_sha256": _sha256_file(old_report),
            "lineage_sha256": _sha256_file(old_lineage),
            "files_modified": False,
            "files_deleted": False,
        }
    ]
    assert old_report.read_text(encoding="utf-8") == '{"old":true}\n'
    assert old_lineage.read_text(encoding="utf-8") == '{"old_record":true}\n'


def test_existing_destination_is_never_overwritten(
    paired_shadow_fixture: dict[str, Path], tmp_path: Path
) -> None:
    output = tmp_path / "existing"
    output.mkdir()
    sentinel = output / "sentinel.txt"
    sentinel.write_text("keep", encoding="utf-8")

    with pytest.raises(TrackletPairedShadowError) as error:
        run_tracklet_paired_shadow(_spec(paired_shadow_fixture, output))

    assert error.value.code == "paired_shadow_destination_exists"
    assert sentinel.read_text(encoding="utf-8") == "keep"


def _spec(paths: dict[str, Path], output: Path) -> PairedShadowInputSpec:
    corpus_manifest = _read_json(paths["corpus"] / "heldout_manifest.json")
    heldout_report = _read_json(paths["heldout_report"])
    return PairedShadowInputSpec(
        heldout_corpus_dir=paths["corpus"],
        bundle_dir=paths["bundle"],
        heldout_report_path=paths["heldout_report"],
        output_dir=output,
        expected_corpus_manifest_sha256=_sha256_file(
            paths["corpus"] / "heldout_manifest.json"
        ),
        expected_corpus_content_sha256=corpus_manifest["content_sha256"],
        expected_corpus_config_sha256=_sha256_file(
            paths["corpus"] / "heldout_dataset" / "heldout_config.json"
        ),
        expected_bundle_manifest_sha256=_sha256_file(paths["bundle"] / "manifest.json"),
        expected_bundle_weights_sha256=_sha256_file(paths["bundle"] / "weights.pt"),
        expected_bundle_checksums_sha256=_sha256_file(paths["bundle"] / "SHA256SUMS"),
        expected_heldout_report_sha256=_sha256_file(paths["heldout_report"]),
        expected_heldout_report_content_sha256=heldout_report["content_sha256"],
        evaluated_at_utc="2026-07-21T12:20:00Z",
        require_full_profile=False,
    )


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
