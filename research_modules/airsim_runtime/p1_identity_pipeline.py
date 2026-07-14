"""Main-owned assembly of AirSim evidence for D1/D2/D6 identity calibration."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from d1_sensor_fusion import (
    ReplayProvenance,
    freeze_airsim_replay_file,
    write_frozen_airsim_replay,
)
from d2_data_association import transform_d1_governed_replay


PIPELINE_SCHEMA_VERSION = "main-p1-identity-pipeline-v1"
D2_INPUT_SCHEMA_VERSION = "d2-p1-identity-calibration-input/v1"
CAPTURE_PROVENANCE_SCHEMA_VERSION = "main.airsim.capture_provenance.v1"


@dataclass(frozen=True)
class IdentityEpisodeEvidence:
    seed: int
    episode_dir: Path
    scenario_id: str
    scenario_version: str
    scenario_difficulty: str = "nominal"
    declared_target_spacing_m: float = 4.0
    difficulty_metadata: dict[str, Any] | None = None


def freeze_identity_episode(
    evidence: IdentityEpisodeEvidence,
    output_dir: str | Path,
) -> dict[str, Path]:
    """Merge one persisted episode and freeze it through D1's public adapter."""

    episode_dir = Path(evidence.episode_dir)
    frames_path = episode_dir / "blocks_frames.jsonl"
    observations_path = episode_dir / "blocks_sensor_observations.jsonl"
    if not frames_path.exists() or not observations_path.exists():
        raise FileNotFoundError(
            f"episode evidence missing frames/observations: {episode_dir}"
        )
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    combined_path = output / "main_airsim_frames_with_observations.jsonl"
    evidence_path = str(episode_dir.resolve())
    capture_provenance = {
        "schema_version": CAPTURE_PROVENANCE_SCHEMA_VERSION,
        "scenario_id": evidence.scenario_id,
        "scenario_version": evidence.scenario_version,
        "scenario_config_version": "1",
        "seed": evidence.seed,
        "target_spacing_m": float(evidence.declared_target_spacing_m),
        "evidence_path": evidence_path,
    }
    _write_combined_frames(
        frames_path,
        observations_path,
        combined_path,
        capture_provenance=capture_provenance,
    )
    input_digest = _file_sha256(combined_path)
    scenario_digest = _stable_digest(
        {
            "scenario_id": evidence.scenario_id,
            "scenario_version": evidence.scenario_version,
            "seed": evidence.seed,
            "input_digest": input_digest,
        }
    )
    provenance = ReplayProvenance(
        scenario_id=evidence.scenario_id,
        scenario_version=evidence.scenario_version,
        config_id="main-p1-dense-crossing",
        config_digest=input_digest,
        config_version="1",
        scenario_digest=scenario_digest,
        run_id=f"seed-{evidence.seed:06d}",
        seed=evidence.seed,
        source_format="main_airsim_frame_plus_anonymous_observation_jsonl",
        producer="main-p1-identity-pipeline",
        metadata={
            "episode_dir": str(episode_dir),
            "online_truth_policy": "truth_sidecar_only",
            "target_spacing_m": float(evidence.declared_target_spacing_m),
            "scenario_difficulty": evidence.scenario_difficulty,
            "scenario_config_version": "1",
            "evidence_path": evidence_path,
        },
    )
    result = freeze_airsim_replay_file(combined_path, provenance)
    paths = write_frozen_airsim_replay(output / "d1_frozen", result)
    bundle_path = output / "d1_governed_bundle.json"
    bundle_path.write_text(
        json.dumps(
            {"manifest": result.manifest, "records": result.records},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    index_path = output / "identity_episode_evidence.json"
    index_path.write_text(
        json.dumps(
            {
                "schema_version": PIPELINE_SCHEMA_VERSION,
                "seed": evidence.seed,
                "scenario_id": evidence.scenario_id,
                "scenario_version": evidence.scenario_version,
                "scenario_difficulty": evidence.scenario_difficulty,
                "declared_target_spacing_m": evidence.declared_target_spacing_m,
                "input_digest": input_digest,
                "governed_bundle": str(bundle_path),
                "offline_truth": str(paths["offline_truth"]),
                "d1_summary": str(paths["summary"]),
                "online_truth_leak_count": result.summary["online_truth_leak_count"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return {
        **paths,
        "combined": combined_path,
        "governed_bundle": bundle_path,
        "index": index_path,
    }


def build_identity_calibration_manifest(
    evidence_rows: Iterable[tuple[IdentityEpisodeEvidence, dict[str, Path]]],
    output_path: str | Path,
    *,
    frozen_p95_loop_latency_budget_s: float,
) -> Path:
    """Write the D2 screening/confirmation input contract from frozen D1 outputs."""

    if frozen_p95_loop_latency_budget_s <= 0.0:
        raise ValueError("frozen_p95_loop_latency_budget_s must be positive")
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    cases = []
    for evidence, paths in evidence_rows:
        cases.append(
            {
                "seed": evidence.seed,
                "replay_name": f"{evidence.scenario_id}_seed{evidence.seed:03d}",
                "replay_path": _relative_or_absolute(paths["governed_bundle"], output.parent),
                "truth_path": _relative_or_absolute(paths["offline_truth"], output.parent),
                "scenario_difficulty": evidence.scenario_difficulty,
                "difficulty_metadata": dict(evidence.difficulty_metadata or {}),
            }
        )
    payload = {
        "schema_version": D2_INPUT_SCHEMA_VERSION,
        "evidence_source": "real_airsim_blocks_d1_governed_replay",
        "frozen_p95_loop_latency_budget_s": float(frozen_p95_loop_latency_budget_s),
        "cases": sorted(cases, key=lambda row: int(row["seed"])),
    }
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return output


def materialize_identity_difficulty_profiles(
    evidence: IdentityEpisodeEvidence,
    frozen_paths: dict[str, Path],
    output_dir: str | Path,
    *,
    profiles: tuple[str, ...],
) -> tuple[tuple[IdentityEpisodeEvidence, dict[str, Path]], ...]:
    """Create deterministic D2 stress bundles from one D1-governed replay."""

    governed = json.loads(frozen_paths["governed_bundle"].read_text(encoding="utf-8"))
    output = Path(output_dir)
    rows: list[tuple[IdentityEpisodeEvidence, dict[str, Path]]] = []
    for profile in profiles:
        result = transform_d1_governed_replay(
            governed,
            scenario_difficulty=profile,
            seed=evidence.seed,
            declared_target_spacing_m=evidence.declared_target_spacing_m,
        )
        profile_dir = output / profile / f"seed{evidence.seed:03d}"
        profile_dir.mkdir(parents=True, exist_ok=True)
        replay_path = profile_dir / "d1_governed_bundle.json"
        audit_path = profile_dir / "d2_stress_audit.json"
        replay_path.write_text(
            json.dumps(result.payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        audit_path.write_text(
            json.dumps(result.to_dict(include_payload=False), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        profile_evidence = IdentityEpisodeEvidence(
            seed=evidence.seed,
            episode_dir=evidence.episode_dir,
            scenario_id=evidence.scenario_id,
            scenario_version=evidence.scenario_version,
            scenario_difficulty=profile,
            declared_target_spacing_m=evidence.declared_target_spacing_m,
            difficulty_metadata=result.profile_metadata,
        )
        rows.append(
            (
                profile_evidence,
                {
                    **frozen_paths,
                    "governed_bundle": replay_path,
                    "stress_audit": audit_path,
                },
            )
        )
    return tuple(rows)


def _write_combined_frames(
    frames_path: Path,
    observations_path: Path,
    output_path: Path,
    *,
    capture_provenance: dict[str, Any],
) -> None:
    observations_by_timestamp: dict[float, list[dict[str, Any]]] = {}
    with observations_path.open("r", encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            observation = json.loads(line)
            timestamp = float(
                observation.get("measurement_timestamp", observation.get("arrival_timestamp", 0.0))
            )
            observations_by_timestamp.setdefault(round(timestamp, 6), []).append(observation)
    with frames_path.open("r", encoding="utf-8") as source, output_path.open(
        "w", encoding="utf-8"
    ) as target:
        for line in source:
            if not line.strip():
                continue
            frame = json.loads(line)
            timestamp = round(float(frame.get("timestamp", 0.0)), 6)
            frame_observations = [
                _with_observation_coverage_cell(item)
                for item in observations_by_timestamp.get(timestamp, [])
            ]
            payload = {
                **frame,
                "capture_provenance": dict(capture_provenance),
                "sensor_observations": frame_observations,
                "processing_timestamp": frame.get("metadata", {}).get(
                    "processing_timestamp"
                ),
                "publish_timestamp": frame.get("metadata", {}).get("publish_timestamp"),
            }
            target.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _with_observation_coverage_cell(observation: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(observation.get("metadata") or {})
    if metadata.get("coverage_cell"):
        return observation
    measurement = observation.get("measurement")
    modality = str(observation.get("modality") or "").lower()
    bearing = None
    if isinstance(measurement, (list, tuple)):
        if modality == "radar" and len(measurement) > 1:
            bearing = measurement[1]
        elif modality == "acoustic" and measurement:
            bearing = measurement[0]
    try:
        bearing_value = float(bearing) if bearing is not None else None
    except (TypeError, ValueError):
        bearing_value = None
    metadata["coverage_cell"] = (
        "cell-unresolved"
        if bearing_value is None
        else "cell-north"
        if bearing_value <= 0.0
        else "cell-south"
    )
    metadata["coverage_cell_source"] = "measurement_bearing_sign"
    return {**observation, "metadata": metadata}


def _relative_or_absolute(path: Path, base: Path) -> str:
    try:
        return str(path.resolve().relative_to(base.resolve()))
    except ValueError:
        return str(path.resolve())


def _file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _stable_digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()
