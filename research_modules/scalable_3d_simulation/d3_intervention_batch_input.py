"""Build a clean, truth-free D3 reserved-seed replay input bundle.

This main-owned producer runs the integrated rule stack, captures anonymous
planning frames, and writes the strict manifest consumed by D3's isolated
intervention batch runner.  It does not load a learning policy into the online
stack, publish a treatment plan, create a runtime acknowledgement, or evaluate
physical outcomes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime
from hashlib import sha256
import json
from math import isfinite
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any

from research_modules.d3_assignment_planner.src.d3_assignment_planner import (
    ISOLATED_INTERVENTION_BATCH_MANIFEST_SCHEMA_V1,
    ISOLATED_INTERVENTION_BATCH_SEEDS_V1,
    CostWeights,
    ModelBundleManifest,
    PlannerConfig,
    PlanningFrameEvidence,
    write_anonymous_planning_frame_evidence,
)

from .episode_bus import jsonable
from .learning_runtime import LearningRuntimeOptions, resolve_learning_runtime
from .module_stack import IntegratedStackConfig
from .orchestrator import Scalable3DEpisodeRunner
from .scenarios import make_curriculum_scenario


D3_INTERVENTION_BATCH_INPUT_SUMMARY_SCHEMA_V1 = (
    "scalable3d.d3-intervention-batch-input-summary.v1"
)
D3_INTERVENTION_BATCH_INPUT_SCOPE = (
    "clean-rule-stack-anonymous-planning-frames-no-authority"
)
D3_INTERVENTION_BATCH_INPUT_MANIFEST = "manifest.json"
D3_INTERVENTION_BATCH_INPUT_SUMMARY = "source_summary.json"
D3_INTERVENTION_BATCH_INPUT_CHECKSUMS = "SHA256SUMS"

_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_UTC_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_BATCH_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


@dataclass(frozen=True, slots=True)
class D3InterventionBatchInputOptions:
    """Fixed scenario controls for one reserved-seed input capture."""

    scenario: str = "nominal"
    scale: int = 5
    target_count: int | None = None
    resource_count: int | None = None
    duration_s: float = 6.0
    batch_id: str = "d3-isolated-intervention-nominal-5v5-v1"
    evaluated_at_utc: str = "2026-07-26T00:00:00Z"
    reserved_seeds: tuple[int, ...] = ISOLATED_INTERVENTION_BATCH_SEEDS_V1

    def __post_init__(self) -> None:
        scenario = str(self.scenario).strip().lower()
        if not scenario:
            raise ValueError("scenario must be non-empty")
        object.__setattr__(self, "scenario", scenario)
        if int(self.scale) <= 0:
            raise ValueError("scale must be positive")
        for name in ("target_count", "resource_count"):
            value = getattr(self, name)
            if value is not None and int(value) <= 0:
                raise ValueError(f"{name} must be positive when provided")
        duration = float(self.duration_s)
        if not isfinite(duration) or duration <= 0.0:
            raise ValueError("duration_s must be positive and finite")
        object.__setattr__(self, "duration_s", duration)
        batch_id = str(self.batch_id).strip()
        if _BATCH_ID_PATTERN.fullmatch(batch_id) is None:
            raise ValueError("batch_id is invalid")
        object.__setattr__(self, "batch_id", batch_id)
        evaluated_at = str(self.evaluated_at_utc).strip()
        if _UTC_PATTERN.fullmatch(evaluated_at) is None:
            raise ValueError("evaluated_at_utc must use YYYY-MM-DDTHH:MM:SSZ")
        try:
            datetime.strptime(evaluated_at, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError as exc:
            raise ValueError("evaluated_at_utc is invalid") from exc
        object.__setattr__(self, "evaluated_at_utc", evaluated_at)
        seeds = tuple(int(seed) for seed in self.reserved_seeds)
        if seeds != ISOLATED_INTERVENTION_BATCH_SEEDS_V1:
            raise ValueError("reserved_seeds must be exactly 1000-1019")
        object.__setattr__(self, "reserved_seeds", seeds)


@dataclass(frozen=True, slots=True)
class D3InterventionSeedCapture:
    """Anonymous D3 frame sequence and source lineage for one seed."""

    seed: int
    source_episode_id: str
    source_manifest_sha256: str
    scenario_version: str
    frames: tuple[PlanningFrameEvidence, ...]

    def __post_init__(self) -> None:
        if int(self.seed) not in ISOLATED_INTERVENTION_BATCH_SEEDS_V1:
            raise ValueError("seed is outside the reserved inventory")
        if not str(self.source_episode_id).strip():
            raise ValueError("source_episode_id must be non-empty")
        _require_sha256(self.source_manifest_sha256, "source_manifest_sha256")
        if not str(self.scenario_version).strip():
            raise ValueError("scenario_version must be non-empty")
        frames = tuple(self.frames)
        if not frames:
            raise ValueError("each seed must provide at least one replayable frame")
        previous_timestamp = -1.0
        for frame in frames:
            _validate_replayable_rule_frame(frame)
            if float(frame.timestamp_s) <= previous_timestamp:
                raise ValueError("planning frame timestamps must be strictly increasing")
            previous_timestamp = float(frame.timestamp_s)
        object.__setattr__(self, "frames", frames)


@dataclass(frozen=True, slots=True)
class D3InterventionBatchCapture:
    """In-memory clean source capture ready for atomic serialization."""

    options: D3InterventionBatchInputOptions
    repository_git_commit: str
    planner_config: PlannerConfig
    cost_weights: CostWeights
    seeds: tuple[D3InterventionSeedCapture, ...]
    online_truth_use_count: int = 0

    def __post_init__(self) -> None:
        if _COMMIT_PATTERN.fullmatch(str(self.repository_git_commit)) is None:
            raise ValueError("repository_git_commit must be a full SHA-1")
        if not isinstance(self.planner_config, PlannerConfig):
            raise TypeError("planner_config must be PlannerConfig")
        if not isinstance(self.cost_weights, CostWeights):
            raise TypeError("cost_weights must be CostWeights")
        seeds = tuple(self.seeds)
        if tuple(item.seed for item in seeds) != (
            ISOLATED_INTERVENTION_BATCH_SEEDS_V1
        ):
            raise ValueError("capture must contain ordered seeds 1000-1019")
        if int(self.online_truth_use_count) != 0:
            raise ValueError("online truth use must remain zero")
        object.__setattr__(self, "seeds", seeds)


def collect_d3_intervention_batch_input(
    options: D3InterventionBatchInputOptions,
) -> D3InterventionBatchCapture:
    """Run clean rule episodes and retain every replayable D3 frame."""

    if not isinstance(options, D3InterventionBatchInputOptions):
        raise TypeError("options must be D3InterventionBatchInputOptions")
    captures: list[D3InterventionSeedCapture] = []
    repository_commit: str | None = None
    planner_config: PlannerConfig | None = None
    cost_weights: CostWeights | None = None
    planner_config_sha256: str | None = None
    cost_weights_sha256: str | None = None

    for seed in options.reserved_seeds:
        config = make_curriculum_scenario(
            options.scenario,
            scale=options.scale,
            seed=seed,
            duration_s=options.duration_s,
            target_count=options.target_count,
            resource_count=options.resource_count,
        )
        config = replace(
            config,
            sensor_random_schedule_version="entity_fixed_v1",
        )
        resolved = resolve_learning_runtime(
            config,
            LearningRuntimeOptions(),
            stack_config=IntegratedStackConfig(
                capture_learning_artifacts=True,
            ),
        )
        result = Scalable3DEpisodeRunner(
            resolved.config,
            module_stack=resolved.stack,
        ).run()
        if bool(result.manifest.repository_dirty):
            raise RuntimeError(
                "D3 intervention input requires a clean source worktree"
            )
        if not bool(result.summary.get("finite_state")):
            raise RuntimeError("D3 intervention source episode is non-finite")
        online_truth = int(result.summary.get("online_truth_use_count", -1))
        if online_truth != 0:
            raise RuntimeError("D3 intervention source used online truth")
        commit = str(result.manifest.git_commit)
        if _COMMIT_PATTERN.fullmatch(commit) is None:
            raise RuntimeError("source episode did not report a full Git commit")
        if repository_commit is None:
            repository_commit = commit
        elif commit != repository_commit:
            raise RuntimeError("source Git commit changed across reserved seeds")

        current_config = resolved.stack.d3.config
        current_weights = resolved.stack.d3.cost_model.weights
        current_config_sha = _canonical_sha256(asdict(current_config))
        current_weights_sha = _canonical_sha256(asdict(current_weights))
        if planner_config is None:
            planner_config = current_config
            cost_weights = current_weights
            planner_config_sha256 = current_config_sha
            cost_weights_sha256 = current_weights_sha
        elif (
            current_config_sha != planner_config_sha256
            or current_weights_sha != cost_weights_sha256
        ):
            raise RuntimeError("D3 configuration changed across reserved seeds")

        frames = tuple(
            frame
            for frame in resolved.stack.learning_artifacts().d3_planning_frames
            if _is_replayable_rule_frame(frame)
        )
        if not frames:
            raise RuntimeError(
                f"reserved seed {seed} produced no replayable D3 frame"
            )
        captures.append(
            D3InterventionSeedCapture(
                seed=seed,
                source_episode_id=result.manifest.episode_id,
                source_manifest_sha256=_canonical_sha256(
                    jsonable(result.manifest)
                ),
                scenario_version=resolved.config.scenario_version,
                frames=frames,
            )
        )

    if repository_commit is None or planner_config is None or cost_weights is None:
        raise RuntimeError("reserved-seed capture is empty")
    return D3InterventionBatchCapture(
        options=options,
        repository_git_commit=repository_commit,
        planner_config=planner_config,
        cost_weights=cost_weights,
        seeds=tuple(captures),
    )


def write_d3_intervention_batch_input(
    output_dir: str | Path,
    capture: D3InterventionBatchCapture,
    *,
    bundle_dir: str | Path,
    expected_bundle_manifest_sha256: str | None = None,
    expected_policy_version: str | None = None,
) -> dict[str, Path]:
    """Atomically write one self-contained D3 replay input directory."""

    if not isinstance(capture, D3InterventionBatchCapture):
        raise TypeError("capture must be D3InterventionBatchCapture")
    source_bundle = Path(bundle_dir).resolve(strict=True)
    manifest_path = source_bundle / "manifest.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise FileNotFoundError("D3 bundle manifest is unavailable")
    bundle_manifest_sha256 = _file_sha256(manifest_path)
    if (
        expected_bundle_manifest_sha256 is not None
        and bundle_manifest_sha256 != expected_bundle_manifest_sha256
    ):
        raise ValueError("D3 bundle manifest SHA-256 mismatch")
    try:
        bundle_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        bundle_manifest = ModelBundleManifest.from_dict(bundle_payload)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ValueError("D3 bundle manifest is invalid") from exc
    if (
        expected_policy_version is not None
        and bundle_manifest.policy_version != expected_policy_version
    ):
        raise ValueError("D3 bundle policy version mismatch")
    state_path = source_bundle / bundle_manifest.state_dict_file
    if not state_path.is_file() or state_path.is_symlink():
        raise FileNotFoundError("D3 bundle state dictionary is unavailable")
    if _file_sha256(state_path) != bundle_manifest.state_dict_sha256:
        raise ValueError("D3 bundle state dictionary SHA-256 mismatch")

    output = Path(output_dir)
    _assert_empty_output(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{output.name}.staging-",
            dir=output.parent,
        )
    )
    try:
        staged_bundle = staging / "bundle"
        staged_bundle.mkdir()
        shutil.copyfile(manifest_path, staged_bundle / manifest_path.name)
        shutil.copyfile(state_path, staged_bundle / state_path.name)

        seed_entries: list[dict[str, Any]] = []
        source_rows: list[dict[str, Any]] = []
        for seed_capture in capture.seeds:
            frame_entries: list[dict[str, Any]] = []
            for sequence_index, frame in enumerate(seed_capture.frames):
                relative_path = (
                    Path("frames")
                    / f"seed_{seed_capture.seed}"
                    / f"frame_{sequence_index:04d}.json"
                )
                hashes = write_anonymous_planning_frame_evidence(
                    staging / relative_path,
                    frame,
                )
                frame_entries.append(
                    {
                        "sequence_index": sequence_index,
                        "timestamp_s": float(frame.timestamp_s),
                        "path": relative_path.as_posix(),
                        "file_sha256": hashes["file_sha256"],
                        "content_sha256": hashes["content_sha256"],
                    }
                )
            seed_entries.append(
                {
                    "seed": seed_capture.seed,
                    "frames": frame_entries,
                }
            )
            source_rows.append(
                {
                    "seed": seed_capture.seed,
                    "source_episode_id": seed_capture.source_episode_id,
                    "source_manifest_sha256": (
                        seed_capture.source_manifest_sha256
                    ),
                    "scenario_version": seed_capture.scenario_version,
                    "frame_count": len(frame_entries),
                    "first_timestamp_s": frame_entries[0]["timestamp_s"],
                    "last_timestamp_s": frame_entries[-1]["timestamp_s"],
                }
            )

        batch_manifest = {
            "schema_version": (
                ISOLATED_INTERVENTION_BATCH_MANIFEST_SCHEMA_V1
            ),
            "batch_id": capture.options.batch_id,
            "evaluated_at": capture.options.evaluated_at_utc,
            "split": "test",
            "source": {
                "repository_git_commit": capture.repository_git_commit,
                "worktree_state": "clean",
            },
            "bundle": {
                "directory": "bundle",
                "manifest_sha256": bundle_manifest_sha256,
                "policy_version": bundle_manifest.policy_version,
            },
            "planner_config": jsonable(asdict(capture.planner_config)),
            "cost_weights": jsonable(asdict(capture.cost_weights)),
            "seeds": seed_entries,
        }
        _write_json(staging / D3_INTERVENTION_BATCH_INPUT_MANIFEST, batch_manifest)
        source_summary = {
            "schema_version": (
                D3_INTERVENTION_BATCH_INPUT_SUMMARY_SCHEMA_V1
            ),
            "scope": D3_INTERVENTION_BATCH_INPUT_SCOPE,
            "batch_id": capture.options.batch_id,
            "evaluated_at_utc": capture.options.evaluated_at_utc,
            "repository_git_commit": capture.repository_git_commit,
            "source_worktree_state": "clean",
            "scenario": capture.options.scenario,
            "scale": capture.options.scale,
            "target_count": capture.options.target_count,
            "resource_count": capture.options.resource_count,
            "duration_s": capture.options.duration_s,
            "seed_count": len(source_rows),
            "frame_count": sum(row["frame_count"] for row in source_rows),
            "online_truth_use_count": capture.online_truth_use_count,
            "bundle_manifest_sha256": bundle_manifest_sha256,
            "bundle_state_dict_sha256": bundle_manifest.state_dict_sha256,
            "planner_config_sha256": _canonical_sha256(
                asdict(capture.planner_config)
            ),
            "cost_weights_sha256": _canonical_sha256(
                asdict(capture.cost_weights)
            ),
            "execution_boundary": {
                "learning_bundle_loaded_online": False,
                "treatment_plan_published": False,
                "runtime_ack_created": False,
                "production_assignment_authority": False,
                "production_control_authority": False,
                "physical_outcome_available": False,
                "reward_available": False,
            },
            "seeds": source_rows,
        }
        _write_json(staging / D3_INTERVENTION_BATCH_INPUT_SUMMARY, source_summary)
        _write_tree_checksums(staging)
        _assert_staged_bundle_unchanged(
            staged_bundle,
            bundle_manifest_sha256=bundle_manifest_sha256,
            state_dict_name=bundle_manifest.state_dict_file,
            state_dict_sha256=bundle_manifest.state_dict_sha256,
        )
        _assert_empty_output(output)
        if output.exists():
            output.rmdir()
        os.replace(staging, output)
    finally:
        if staging.exists():
            shutil.rmtree(staging)

    return {
        "manifest": output / D3_INTERVENTION_BATCH_INPUT_MANIFEST,
        "source_summary": output / D3_INTERVENTION_BATCH_INPUT_SUMMARY,
        "checksums": output / D3_INTERVENTION_BATCH_INPUT_CHECKSUMS,
    }


def _is_replayable_rule_frame(value: Any) -> bool:
    if not isinstance(value, PlanningFrameEvidence):
        return False
    return bool(
        value.available
        and value.learning_state == "rule_only"
        and value.previous_plan is not None
        and value.plan is not None
        and value.rule_matrix_result is not None
        and value.effective_matrix_result is not None
    )


def _validate_replayable_rule_frame(frame: PlanningFrameEvidence) -> None:
    if not _is_replayable_rule_frame(frame):
        raise ValueError("capture contains a non-replayable D3 planning frame")
    timestamp = float(frame.timestamp_s)
    if not isfinite(timestamp) or timestamp < 0.0:
        raise ValueError("planning frame timestamp must be finite and nonnegative")


def _assert_empty_output(path: Path) -> None:
    if not path.exists():
        return
    if not path.is_dir() or path.is_symlink():
        raise FileExistsError("output exists and is not a regular directory")
    try:
        next(path.iterdir())
    except StopIteration:
        return
    raise FileExistsError("output directory is not empty")


def _assert_staged_bundle_unchanged(
    bundle: Path,
    *,
    bundle_manifest_sha256: str,
    state_dict_name: str,
    state_dict_sha256: str,
) -> None:
    if _file_sha256(bundle / "manifest.json") != bundle_manifest_sha256:
        raise RuntimeError("staged D3 bundle manifest changed")
    if _file_sha256(bundle / state_dict_name) != state_dict_sha256:
        raise RuntimeError("staged D3 bundle state dictionary changed")


def _write_tree_checksums(root: Path) -> None:
    checksum_path = root / D3_INTERVENTION_BATCH_INPUT_CHECKSUMS
    files = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path != checksum_path
    )
    checksum_path.write_text(
        "".join(
            f"{_file_sha256(path)}  {path.relative_to(root).as_posix()}\n"
            for path in files
        ),
        encoding="ascii",
        newline="\n",
    )


def _canonical_sha256(value: Any) -> str:
    payload = (
        json.dumps(
            jsonable(value),
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _require_sha256(value: str, name: str) -> None:
    text = str(value)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise ValueError(f"{name} must be a lowercase SHA-256")


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(
            jsonable(payload),
            ensure_ascii=True,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="ascii",
        newline="\n",
    )


__all__ = [
    "D3_INTERVENTION_BATCH_INPUT_CHECKSUMS",
    "D3_INTERVENTION_BATCH_INPUT_MANIFEST",
    "D3_INTERVENTION_BATCH_INPUT_SCOPE",
    "D3_INTERVENTION_BATCH_INPUT_SUMMARY",
    "D3_INTERVENTION_BATCH_INPUT_SUMMARY_SCHEMA_V1",
    "D3InterventionBatchCapture",
    "D3InterventionBatchInputOptions",
    "D3InterventionSeedCapture",
    "collect_d3_intervention_batch_input",
    "write_d3_intervention_batch_input",
]
