"""Main-owned wiring from scalable episode artifacts to D6 public adapters."""

from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence


D6_TRUTH_ISOLATED_MANIFEST_SCHEMA_VERSION = (
    "scalable3d-d6-truth-isolated-manifest-v1"
)
D6_RUNTIME_PLAN_OUTCOME_MANIFEST_SCHEMA_VERSION = (
    "scalable3d-d6-runtime-plan-outcome-manifest-v1"
)

_RUNTIME_PLAN_OUTCOME_SOURCE_PATHS = {
    "online_observations": "online_observations",
    "d2_identity_evaluation": "offline_identity_evaluation",
    "d2_identity_manifest": "offline_identity_manifest",
    "d2_online_d1_records": "offline_identity_d1_records",
    "d2_online_d2_records": "offline_identity_d2_records",
    "d2_observation_truth_labels": "offline_identity_truth_labels",
    "d2_identity_evidence": "offline_identity_evidence",
    "offline_truth_state": "offline_truth_state",
    "offline_proximity_intercepts": "offline_intercepts",
    "episode_manifest": "manifest",
    "scenario_config": "scenario_config",
}


def build_truth_isolated_episode_record(
    result: Any,
    artifact_paths: Mapping[str, Path] | None = None,
) -> Any:
    """Build one D6 record from independently hash-verified D1/D2 artifacts."""

    _prepare_matplotlib_3d()
    from research_modules.d6_evaluation_metrics.d6_evaluation_metrics import (
        TruthIsolatedEpisodeContext,
        build_truth_isolated_episode_record as build_d6_record,
    )

    paths = dict(result.output_paths or {})
    if artifact_paths is not None:
        paths.update(artifact_paths)
    context = TruthIsolatedEpisodeContext(
        episode_id=str(result.manifest.episode_id),
        scenario_id=str(result.config.scenario_name),
        scenario_version=str(result.config.scenario_version),
        run_id=str(result.manifest.episode_id),
        seed=int(result.config.seed),
        target_count=int(result.config.target_count),
        resource_count=int(result.config.resource_count),
        recon_count=int(result.config.recon_count),
        camera_count=int(result.config.resource_count + result.config.recon_count),
    )

    d1_path, d1_sha = _d1_result_source(paths)
    d2_path, d2_sha, d2_source_hashes = _d2_identity_source(paths)
    return build_d6_record(
        context,
        d1_result=d1_path,
        d2_evaluation=d2_path,
        d1_expected_sha256=d1_sha,
        d2_expected_sha256=d2_sha,
        d2_expected_source_hashes=d2_source_hashes,
    )


def write_episode_truth_isolated_outputs(
    result: Any,
    output_dir: str | Path,
    *,
    artifact_paths: Mapping[str, Path],
) -> dict[str, Path]:
    """Write a single-episode D6 bundle and its main provenance manifest."""

    _prepare_matplotlib_3d()
    from research_modules.d6_evaluation_metrics.d6_evaluation_metrics import (
        TruthIsolatedOfflineReportGenerator,
    )

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    record = build_truth_isolated_episode_record(result, artifact_paths)
    report_paths = TruthIsolatedOfflineReportGenerator().write_report_bundle(
        root,
        records=(record,),
    )
    record_path = _write_json(root / "episode_record.json", record.to_dict())
    source_hashes = _source_hash_summary(artifact_paths)
    output_hashes = {
        "episode_record": _sha256_file(record_path),
        **{
            name: _sha256_file(path) for name, path in report_paths.items()
        },
    }
    manifest_path = _write_json(
        root / "manifest.json",
        {
            "schema_version": D6_TRUTH_ISOLATED_MANIFEST_SCHEMA_VERSION,
            "episode_id": str(result.manifest.episode_id),
            "scenario_version": str(result.config.scenario_version),
            "seed": int(result.config.seed),
            "target_count": int(result.config.target_count),
            "resource_count": int(result.config.resource_count),
            "source_hashes": source_hashes,
            "output_hashes": dict(sorted(output_hashes.items())),
        },
    )
    return {
        "d6_truth_isolated_manifest": manifest_path,
        "d6_truth_isolated_episode_record": record_path,
        **{
            f"d6_truth_isolated_{name}": path
            for name, path in report_paths.items()
        },
    }


def write_batch_truth_isolated_outputs(
    results: Sequence[Any],
    output_dir: str | Path,
) -> dict[str, Path]:
    """Aggregate already-persisted episodes without weakening missing-data semantics."""

    _prepare_matplotlib_3d()
    from research_modules.d6_evaluation_metrics.d6_evaluation_metrics import (
        TruthIsolatedOfflineReportGenerator,
    )

    episodes = tuple(results)
    if not episodes:
        return {}
    records = tuple(build_truth_isolated_episode_record(result) for result in episodes)
    paths = TruthIsolatedOfflineReportGenerator().write_report_bundle(
        output_dir,
        records=records,
    )
    return {
        f"d6_truth_isolated_batch_{name}": path for name, path in paths.items()
    }


def write_episode_runtime_plan_outcome_outputs(
    result: Any,
    output_dir: str | Path,
    *,
    artifact_paths: Mapping[str, Path],
) -> dict[str, Path]:
    """Join runtime plan ACKs to offline outcomes using a replayable hash manifest."""

    if int(result.summary.get("assignment_plan_ack_count", 0)) <= 0:
        raise ValueError("runtime plan outcome join requires at least one plan ACK")

    _prepare_matplotlib_3d()
    from research_modules.d6_evaluation_metrics.d6_evaluation_metrics import (
        HashedArtifact,
        RUNTIME_PLAN_OUTCOME_INPUT_SCHEMA_VERSION,
        RuntimePlanOutcomeJoinInputs,
        load_runtime_plan_outcome_join_inputs,
        write_runtime_plan_outcome_join_report,
    )

    root = Path(output_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    missing = tuple(
        sorted(
            path_key
            for path_key in _RUNTIME_PLAN_OUTCOME_SOURCE_PATHS.values()
            if artifact_paths.get(path_key) is None
        )
    )
    if missing:
        raise ValueError(
            "runtime plan outcome join source paths missing: " + ", ".join(missing)
        )

    hashed_sources = {
        logical_name: HashedArtifact(
            Path(artifact_paths[path_key]).resolve(),
            _sha256_file(artifact_paths[path_key]),
        )
        for logical_name, path_key in _RUNTIME_PLAN_OUTCOME_SOURCE_PATHS.items()
    }
    inputs = RuntimePlanOutcomeJoinInputs(**hashed_sources)
    input_specification = {
        "schema_version": RUNTIME_PLAN_OUTCOME_INPUT_SCHEMA_VERSION,
        "artifacts": {
            name: {
                "path": os.path.relpath(artifact.path, start=root),
                "sha256": artifact.sha256,
            }
            for name, artifact in sorted(hashed_sources.items())
        },
    }
    input_path = _write_json(root / "input_specification.json", input_specification)
    input_sha = _sha256_file(input_path)
    verified_inputs = load_runtime_plan_outcome_join_inputs(
        input_path,
        expected_sha256=input_sha,
    )
    if (
        verified_inputs.resolved().to_dict()["artifacts"]
        != inputs.resolved().to_dict()["artifacts"]
    ):
        raise ValueError("runtime plan outcome input specification round-trip mismatch")

    report_paths = write_runtime_plan_outcome_join_report(
        verified_inputs,
        root,
    )
    evaluation = _load_json(report_paths["json"], "D6 runtime plan outcome report")
    admission = evaluation.get("admission")
    if not isinstance(admission, Mapping):
        raise TypeError("D6 runtime plan outcome report admission must be a mapping")
    output_hashes = {
        "input_specification": input_sha,
        **{
            name: _sha256_file(path) for name, path in sorted(report_paths.items())
        },
    }
    manifest_path = _write_json(
        root / "manifest.json",
        {
            "schema_version": D6_RUNTIME_PLAN_OUTCOME_MANIFEST_SCHEMA_VERSION,
            "episode_id": str(result.manifest.episode_id),
            "scenario_version": str(result.config.scenario_version),
            "seed": int(result.config.seed),
            "target_count": int(result.config.target_count),
            "resource_count": int(result.config.resource_count),
            "runtime_assignment_plan_ack_count": int(
                result.summary.get("assignment_plan_ack_count", 0)
            ),
            "source_hashes": {
                name: artifact.sha256
                for name, artifact in sorted(hashed_sources.items())
            },
            "output_hashes": dict(sorted(output_hashes.items())),
            "admission": {
                "status": admission.get("status"),
                "ppo_allowed": bool(admission.get("ppo_allowed", False)),
                "assist_allowed": bool(admission.get("assist_allowed", False)),
                "authority_allowed": bool(admission.get("authority_allowed", False)),
                "rule_fallback_required": bool(
                    admission.get("rule_fallback_required", True)
                ),
            },
        },
    )
    return {
        "d6_runtime_plan_outcome_manifest": manifest_path,
        "d6_runtime_plan_outcome_input_specification": input_path,
        **{
            f"d6_runtime_plan_outcome_{name}": path
            for name, path in report_paths.items()
        },
    }


def _d1_result_source(
    paths: Mapping[str, Path],
) -> tuple[Path | None, str | None]:
    result_path = paths.get("offline_consistency_result")
    manifest_path = paths.get("offline_consistency_manifest")
    if result_path is None or manifest_path is None:
        return None, None
    manifest = _load_json(manifest_path, "D1 consistency manifest")
    expected = _manifest_hash(manifest, "offline_result")
    _verify_file_hash(result_path, expected, "D1 offline consistency result")
    return Path(result_path), expected


def _prepare_matplotlib_3d() -> None:
    """Register mplot3d before D6's broad package exports load plotting modules."""

    import matplotlib

    from .animation import ensure_mplot3d

    ensure_mplot3d(matplotlib)


def _d2_identity_source(
    paths: Mapping[str, Path],
) -> tuple[Path | None, str | None, Mapping[str, str] | None]:
    evaluation_path = paths.get("offline_identity_evaluation")
    manifest_path = paths.get("offline_identity_manifest")
    if evaluation_path is None or manifest_path is None:
        return None, None, None
    manifest = _load_json(manifest_path, "D2 identity manifest")
    evaluation_sha = _manifest_hash(manifest, "identity_evaluation")
    _verify_file_hash(
        evaluation_path,
        evaluation_sha,
        "D2 identity evaluation",
    )
    source_specs = {
        "online_d1_records": (
            "online_d1_records",
            "offline_identity_d1_records",
        ),
        "online_d2_records": (
            "online_d2_records",
            "offline_identity_d2_records",
        ),
        "observation_truth_labels": (
            "observation_truth_labels",
            "offline_identity_truth_labels",
        ),
        "identity_evidence_bundle": (
            "identity_evidence",
            "offline_identity_evidence",
        ),
    }
    expected_source_hashes: dict[str, str] = {}
    for public_name, (manifest_name, path_name) in source_specs.items():
        expected = _manifest_hash(manifest, manifest_name)
        source_path = paths.get(path_name)
        if source_path is None:
            raise ValueError(f"D2 identity source path missing: {path_name}")
        _verify_file_hash(source_path, expected, public_name)
        expected_source_hashes[public_name] = expected
    return Path(evaluation_path), evaluation_sha, expected_source_hashes


def _source_hash_summary(paths: Mapping[str, Path]) -> dict[str, str | None]:
    summary: dict[str, str | None] = {}
    for name in (
        "offline_consistency_manifest",
        "offline_consistency_result",
        "offline_identity_manifest",
        "offline_identity_evaluation",
    ):
        path = paths.get(name)
        summary[name] = None if path is None else _sha256_file(path)
    return summary


def _manifest_hash(manifest: Mapping[str, Any], name: str) -> str:
    source_hashes = manifest.get("source_hashes")
    if not isinstance(source_hashes, Mapping):
        raise ValueError("evaluation manifest source_hashes must be a mapping")
    value = source_hashes.get(name)
    return _normalized_sha256(value, f"manifest hash {name}")


def _verify_file_hash(path: str | Path, expected: str, name: str) -> None:
    actual = _sha256_file(path)
    if actual != expected:
        raise ValueError(f"{name} SHA-256 mismatch: expected {expected}, got {actual}")


def _sha256_file(path: str | Path) -> str:
    digest = sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _normalized_sha256(value: Any, name: str) -> str:
    text = str(value).strip().lower()
    if not text.startswith("sha256:"):
        raise ValueError(f"{name} must use a sha256: prefix")
    hexadecimal = text[7:]
    if len(hexadecimal) != 64 or any(
        char not in "0123456789abcdef" for char in hexadecimal
    ):
        raise ValueError(f"{name} is not a valid SHA-256 digest")
    return text


def _load_json(path: str | Path, name: str) -> Mapping[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise TypeError(f"{name} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: Mapping[str, Any]) -> Path:
    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


__all__ = [
    "D6_RUNTIME_PLAN_OUTCOME_MANIFEST_SCHEMA_VERSION",
    "D6_TRUTH_ISOLATED_MANIFEST_SCHEMA_VERSION",
    "build_truth_isolated_episode_record",
    "write_batch_truth_isolated_outputs",
    "write_episode_runtime_plan_outcome_outputs",
    "write_episode_truth_isolated_outputs",
]
