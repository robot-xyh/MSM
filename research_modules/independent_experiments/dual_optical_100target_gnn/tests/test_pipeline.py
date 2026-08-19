from __future__ import annotations

import json
import math

import pytest
import torch

from dual_optical_100target_gnn.dataset import (
    canonical_json_sha256,
    dataset_fingerprint,
    load_dataset_manifest,
    load_entry,
    prepare_dataset,
    sample_entries,
)
from dual_optical_100target_gnn.evaluation import (
    _promotion_decision,
    evaluate_frozen,
)
from dual_optical_100target_gnn.reporting import _result_section, generate_report
from dual_optical_100target_gnn.training import (
    TrainingConfig,
    train_and_freeze,
    verify_freeze_manifest,
)


def test_dataset_separates_online_graphs_and_offline_labels(episode_factory, tmp_path):
    inputs = {seed: episode_factory(seed, version=2 + seed % 2) for seed in (301, 302, 303)}
    manifest_path = prepare_dataset(
        inputs,
        tmp_path / "dataset",
        splits={"train": (301,), "val": (302,), "test": (303,)},
        expected_target_count=4,
    )
    manifest, root = load_dataset_manifest(manifest_path)
    assert all(
        "positive_candidate_edge_count" not in entry["online_diagnostics"]
        for entry in manifest["samples"]
    )
    entry = sample_entries(manifest, "train")[0]
    graph, labels = load_entry(root, entry, include_labels=False)
    assert labels is None
    online_keys = set(__import__("numpy").load(root / entry["online_path"], allow_pickle=False).files)
    assert not any("truth" in key or "actor" in key or "identity" in key for key in online_keys)
    assert graph.seed == 301


def test_dataset_hash_rejects_modified_online_graph(episode_factory, tmp_path):
    inputs = {seed: episode_factory(seed) for seed in (311, 312, 313)}
    manifest_path = prepare_dataset(
        inputs,
        tmp_path / "dataset_hash",
        splits={"train": (311,), "val": (312,), "test": (313,)},
        expected_target_count=4,
    )
    manifest, root = load_dataset_manifest(manifest_path)
    entry = sample_entries(manifest, "train")[0]
    online_path = root / entry["online_path"]
    with online_path.open("ab") as handle:
        handle.write(b"tamper")
    with pytest.raises(ValueError, match="hash mismatch"):
        load_entry(root, entry, include_labels=False)


def test_dataset_manifest_requires_all_corruptions_per_seed(episode_factory, tmp_path):
    inputs = {seed: episode_factory(seed) for seed in (314, 315, 316)}
    manifest_path = prepare_dataset(
        inputs,
        tmp_path / "dataset_levels",
        splits={"train": (314,), "val": (315,), "test": (316,)},
        expected_target_count=4,
    )
    manifest, _ = load_dataset_manifest(manifest_path)
    manifest["samples"] = [
        entry
        for entry in manifest["samples"]
        if not (entry["seed"] == 314 and entry["corruption_level"] == "heavy")
    ]
    with pytest.raises(ValueError, match="incomplete corruption set"):
        sample_entries(manifest, "train")


def test_dataset_fingerprint_is_reproducible_and_detects_manifest_tamper(
    episode_factory, tmp_path
):
    inputs = {seed: episode_factory(seed) for seed in (317, 318, 319)}
    split = {"train": (317,), "val": (318,), "test": (319,)}
    first_path = prepare_dataset(
        inputs,
        tmp_path / "dataset_repeat_a",
        splits=split,
        expected_target_count=4,
    )
    second_path = prepare_dataset(
        inputs,
        tmp_path / "dataset_repeat_b",
        splits=split,
        expected_target_count=4,
    )
    first, _ = load_dataset_manifest(first_path)
    second, _ = load_dataset_manifest(second_path)
    assert first["dataset_fingerprint_sha256"] == second["dataset_fingerprint_sha256"]
    assert dataset_fingerprint(first) == dataset_fingerprint(second)

    first["expected_target_count"] = 5
    first_path.write_text(json.dumps(first, indent=2), encoding="utf-8")
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        load_dataset_manifest(first_path)


def test_formal_dataset_rejects_non_100_target_episode(episode_factory, tmp_path):
    inputs = {seed: episode_factory(seed) for seed in (321, 322, 323)}
    with pytest.raises(ValueError, match="configures 4 targets"):
        prepare_dataset(
            inputs,
            tmp_path / "wrong_scale",
            splits={"train": (321,), "val": (322,), "test": (323,)},
        )


def test_promotion_requires_duplicate_identity_non_increase():
    aggregate = {
        "geometry": {
            "macro_f1": 0.80,
            "false_association_count": 20,
            "duplicate_identity_match_count": 5,
        },
        "hybrid": {
            "macro_f1": 0.95,
            "false_association_count": 10,
            "duplicate_identity_match_count": 5,
        },
    }
    latency = {"gpu": {"available": 1, "p95_ms": 0.8}}
    passed = _promotion_decision(aggregate, latency, {})
    assert passed["duplicate_identity_non_increase"] is True
    assert passed["geometry_duplicate_identity_match_count"] == 5
    assert passed["hybrid_duplicate_identity_match_count"] == 5
    assert passed["recommend_continue_toward_mainline"] is True

    aggregate["hybrid"]["duplicate_identity_match_count"] = 6
    failed = _promotion_decision(aggregate, latency, {})
    assert failed["duplicate_identity_non_increase"] is False
    assert failed["recommend_continue_toward_mainline"] is False


def test_formal_result_section_contains_per_corruption_table_and_limits(tmp_path):
    history_path = tmp_path / "training_history.csv"
    history_path.write_text(
        "epoch,train_loss,val_loss\n"
        + "".join(
            f"{epoch},{1.0 / epoch:.6f},{0.08 + abs(epoch - 19) * 0.01:.6f}\n"
            for epoch in range(1, 30)
        ),
        encoding="utf-8",
    )

    def summary(precision, recall, f1, false_count, duplicate_count, samples=2):
        return {
            "sample_count": samples,
            "macro_precision": precision,
            "macro_recall": recall,
            "macro_f1": f1,
            "false_association_count": false_count,
            "duplicate_track_assignment_count": 0,
            "duplicate_identity_match_count": duplicate_count,
        }

    assignment = {
        "geometry": summary(0.8078, 0.8317, 0.8196, 120, 5, samples=6),
        "learned": summary(0.9877, 0.9133, 0.9490, 7, 8, samples=6),
        "hybrid": summary(0.9823, 0.9133, 0.9465, 10, 5, samples=6),
    }
    by_corruption = {
        level: {
            "geometry": summary(0.81, 0.83, 0.82, 40, 2),
            "learned": summary(0.99, 0.91, 0.95, 2, 2),
            "hybrid": summary(0.98, 0.91, 0.94, 3, 1),
        }
        for level in ("light", "medium", "heavy")
    }
    metrics = {
        "evidence_status": "formal_reserved_test",
        "test_seeds": [20260830, 20260831],
        "test_sample_count": 6,
        "candidate_edge_auprc_macro": 0.9967139,
        "assignment": assignment,
        "assignment_by_corruption": by_corruption,
        "latency": {
            "cpu": {"available": 1, "p95_ms": 1.2706},
            "gpu": {"available": 1, "p95_ms": 0.7776},
        },
        "promotion": {
            "macro_f1_delta": 0.1269,
            "f1_improvement_at_least_0_02": True,
            "false_association_non_increase": True,
            "duplicate_identity_non_increase": True,
            "gpu_p95_at_most_100_ms": True,
            "recommend_continue_toward_mainline": True,
        },
        "artifacts": {"training_history": history_path.name},
    }
    section = _result_section(metrics, tmp_path / "evaluation_metrics.json")
    assert "仅包含2个独立AirSim种子" in section
    assert "轻、中、重三档分别形成2个样本" in section
    assert "| 轻度 | 2 | 确定性几何 |" in section
    assert "| 中度 | 2 | 学习代价 |" in section
    assert "| 重度 | 2 | 混合代价 |" in section
    assert "0.8196" in section and "0.9490" in section and "0.9465" in section
    assert "120" in section and "| 7 |" in section and "| 10 |" in section
    assert "中央处理器1.27毫秒" in section
    assert "图形处理器0.78毫秒" in section
    assert "共训练29轮" in section and "第19轮" in section
    assert "约为0.992" in section
    assert "不足以证明必须采用图神经网络" in section
    assert "满足进入下一轮隔离工程验证条件" in section
    assert "不表示图网络已经可以替换确定性主线" in section


def test_train_freeze_then_evaluate_and_report(episode_factory, tmp_path, monkeypatch):
    inputs = {seed: episode_factory(seed) for seed in (401, 402, 403)}
    dataset_manifest = prepare_dataset(
        inputs,
        tmp_path / "dataset",
        splits={"train": (401,), "val": (402,), "test": (403,)},
        expected_target_count=4,
    )
    import dual_optical_100target_gnn.training as training_module

    opened_during_training = []
    original_load_entry = training_module.load_entry

    def recording_load_entry(root, entry, *, include_labels):
        opened_during_training.append(int(entry["seed"]))
        return original_load_entry(root, entry, include_labels=include_labels)

    monkeypatch.setattr(training_module, "load_entry", recording_load_entry)
    freeze_path = train_and_freeze(
        dataset_manifest,
        tmp_path / "frozen",
        config=TrainingConfig(max_epochs=2, patience=1, device="cpu", random_seed=7),
    )
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    assert 403 not in opened_during_training
    assert freeze["test_graph_files_opened_before_freeze"] is False
    assert freeze["checkpoint_payload"] == "state_dict_only"
    assert len(freeze["model_fingerprint_sha256"]) == 64
    assert len(freeze["dataset_fingerprint_sha256"]) == 64
    assert freeze["selected_route"] in {"learned", "hybrid"}
    assert freeze["selected_probability_threshold"] in [
        0.3,
        0.4,
        0.5,
        0.6,
        0.7,
        0.8,
        0.9,
    ]
    assert freeze["selected_unmatched_cost"] == pytest.approx(
        -math.log(freeze["selected_probability_threshold"])
    )
    assert (freeze_path.parent / freeze["validation_selection"]).is_file()
    selection = json.loads(
        (freeze_path.parent / freeze["validation_selection"]).read_text(encoding="utf-8")
    )
    assert len(selection["candidates"]) == 14
    assert selection["fixed_probability_threshold_candidates"] == [
        0.3,
        0.4,
        0.5,
        0.6,
        0.7,
        0.8,
        0.9,
    ]
    assert selection["hybrid_weights"] == {"geometry": 0.4, "learned": 0.6}
    assert selection["selected_probability_threshold"] == freeze[
        "selected_probability_threshold"
    ]
    assert selection["selected_unmatched_cost"] == pytest.approx(
        -math.log(selection["selected_probability_threshold"])
    )
    verify_freeze_manifest(freeze_path)

    tampered = dict(freeze)
    tampered["selected_unmatched_cost"] += 0.01
    tampered_path = freeze_path.parent / "tampered_freeze_manifest.json"
    tampered_path.write_text(json.dumps(tampered, indent=2), encoding="utf-8")
    with pytest.raises(ValueError, match="unmatched cost"):
        verify_freeze_manifest(tampered_path)

    legacy = dict(freeze)
    legacy["schema_version"] = "dual-optical-edge-gnn-freeze-v2"
    for key in (
        "validation_selection",
        "validation_selection_sha256",
        "expanded_formal_protocol",
        "protocol_profile",
        "selected_route",
        "selected_probability_threshold",
        "selected_unmatched_cost",
        "route_probability_thresholds",
        "route_unmatched_costs",
    ):
        legacy.pop(key, None)
    legacy_artifacts = {
        key: legacy[key]
        for key in (
            "weights_sha256",
            "normalizer_sha256",
            "model_config_sha256",
            "training_history_sha256",
        )
    }
    legacy["model_fingerprint_sha256"] = canonical_json_sha256(
        {
            "dataset_fingerprint_sha256": legacy["dataset_fingerprint_sha256"],
            "artifact_hashes": legacy_artifacts,
            "train_seeds": legacy["train_seeds"],
            "validation_seeds": legacy["validation_seeds"],
            "reserved_test_seeds": legacy["reserved_test_seeds"],
            "corruption_levels": legacy["corruption_levels"],
        }
    )
    legacy_path = freeze_path.parent / "legacy_v2_freeze_manifest.json"
    legacy_path.write_text(json.dumps(legacy, indent=2), encoding="utf-8")
    verified_legacy, _ = verify_freeze_manifest(legacy_path)
    assert verified_legacy["schema_version"] == "dual-optical-edge-gnn-freeze-v2"
    state = torch.load(freeze_path.parent / freeze["weights"], weights_only=True)
    assert state and all(hasattr(value, "shape") for value in state.values())
    metrics_path = evaluate_frozen(
        freeze_path,
        tmp_path / "evaluation",
        latency_repeats=1,
        bootstrap_repeats=200,
    )
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    assert metrics["test_seeds"] == [403]
    assert metrics["truth_isolation"]["truth_fields_in_model_features"] is False
    assert set(metrics["assignment"]) == {"geometry", "learned", "hybrid"}
    assert set(metrics["assignment_by_corruption"]) == {"light", "medium", "heavy"}
    assert metrics["test_sample_count"] == 3
    assert metrics["evidence_status"] == "nonformal_test_split"
    assert "duplicate_identity_non_increase" in metrics["promotion"]
    assert metrics["seed_grouped_bootstrap_95ci"]["seed_count"] == 1
    assert len(metrics["reproducibility"]["candidate_fingerprint_sha256"]) == 64
    assert (metrics_path.parent / metrics["artifacts"]["comparison_export"]).is_file()
    assert metrics["promotion"]["recommendation_scope"] == (
        "next_isolated_engineering_validation_only"
    )
    assert metrics["reproducibility"]["model_weights_sha256"] == freeze["weights_sha256"]
    assert all(
        values["duplicate_track_assignment_count"] == 0
        for level in metrics["assignment_by_corruption"].values()
        for values in level.values()
    )
    report = generate_report(tmp_path / "report", metrics_path=metrics_path)
    assert report.is_file()
    assert len(list((report.parent / "figures").glob("*.png"))) == 8
    report_text = report.read_text(encoding="utf-8")
    assert "本地轨迹样本离线生成" in report_text
    assert "低纯度轨迹采用多数身份作为监督标签" in report_text
    assert "不能判断图网络的消息传递是否带来独立收益" in report_text
