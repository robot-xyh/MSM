from __future__ import annotations

from copy import deepcopy
import json

import pytest

from dual_optical_100target_gnn.comparison import (
    COMPARISON_RESULT_SCHEMA_VERSION,
    compare_exports,
    validate_comparison_export,
)
from dual_optical_100target_gnn.dataset import (
    candidate_graph_fingerprint,
    canonical_json_sha256,
    load_dataset_manifest,
    load_entry,
    sample_entries,
)
from dual_optical_100target_lightweight.evaluation import evaluate_frozen
from dual_optical_100target_lightweight.pipeline import train_validate_and_freeze


def _refingerprint(payload):
    payload.pop("payload_fingerprint_sha256", None)
    payload["payload_fingerprint_sha256"] = canonical_json_sha256(payload)
    return payload


def test_shared_candidate_fingerprint_and_comparison_export(dataset_manifest, tmp_path):
    freeze_path = train_validate_and_freeze(dataset_manifest, tmp_path / "model")
    metrics_path = evaluate_frozen(
        freeze_path,
        tmp_path / "evaluation",
        latency_repeats=1,
        bootstrap_resamples=20,
    )
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    candidate_manifest = json.loads(
        (metrics_path.parent / metrics["artifacts"]["candidate_manifest"]).read_text(
            encoding="utf-8"
        )
    )
    manifest, dataset_root = load_dataset_manifest(dataset_manifest)
    test_entry = sample_entries(manifest, "test")[0]
    graph, _ = load_entry(dataset_root, test_entry, include_labels=False)
    matching_entry = next(
        entry
        for entry in candidate_manifest["entries"]
        if int(entry["seed"]) == graph.seed
        and entry["corruption_level"] == graph.corruption_level
    )
    assert matching_entry["candidate_fingerprint_sha256"] == candidate_graph_fingerprint(
        graph
    )
    assert set(matching_entry) == {
        "seed",
        "corruption_level",
        "candidate_fingerprint_sha256",
        "online_sha256",
    }
    assert candidate_manifest["entries"] == sorted(
        candidate_manifest["entries"],
        key=lambda item: (int(item["seed"]), str(item["corruption_level"])),
    )
    assert candidate_manifest["candidate_fingerprint_sha256"] == canonical_json_sha256(
        candidate_manifest["entries"]
    )
    assert (
        metrics["reproducibility"]["candidate_fingerprint_sha256"]
        == candidate_manifest["candidate_fingerprint_sha256"]
    )

    export_path = metrics_path.parent / metrics["artifacts"]["comparison_export"]
    lightweight = json.loads(export_path.read_text(encoding="utf-8"))
    validated = validate_comparison_export(lightweight)
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    assert validated["method_family"] == "lightweight"
    assert validated["method_id"] == freeze["selected_model_id"]
    assert validated["selected_route"] == "selected_lightweight"
    assert validated["dataset_fingerprint_sha256"] == metrics["reproducibility"][
        "dataset_fingerprint_sha256"
    ]
    assert validated["candidate_fingerprint_sha256"] == candidate_manifest[
        "candidate_fingerprint_sha256"
    ]
    assert set(validated["latency"]) == {"cpu", "gpu"}

    gnn = deepcopy(lightweight)
    gnn["method_family"] = "gnn"
    gnn["method_id"] = "fixture-gnn"
    gnn["selected_route"] = "hybrid"
    for row in gnn["per_seed"]:
        row["mode"] = "hybrid"
    _refingerprint(gnn)
    comparison = compare_exports(gnn, lightweight, repeats=100, random_seed=19)
    assert comparison["schema_version"] == COMPARISON_RESULT_SCHEMA_VERSION

    invalid_payload = deepcopy(lightweight)
    invalid_payload["candidate_fingerprint_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        validate_comparison_export(invalid_payload)

    tampered_candidate = _refingerprint(deepcopy(invalid_payload))
    with pytest.raises(ValueError, match="candidate_fingerprint_sha256"):
        compare_exports(gnn, tampered_candidate, repeats=100, random_seed=19)
