#!/usr/bin/env python3
"""Run the frozen A1 v3 schedule as a non-formal, resumable quota probe."""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Mapping


MODULE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = MODULE_ROOT.parents[1]
SRC_ROOT = MODULE_ROOT / "src"
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from d3_assignment_planner.a1_v3_quota_probe import (  # noqa: E402
    A1V3QuotaCounts,
    A1V3QuotaProbeError,
    A1_V3_FORBIDDEN_FORMAL_SEEDS,
    A1_V3_QUOTA_PROBE_SOURCE_ONLY_CONTRACT,
    build_a1_v3_quota_probe_report,
    canonical_json_sha256,
    missing_a1_v3_quota,
    quota_met,
    validate_probe_episode_record,
    write_json_atomic,
)


DEFAULT_SCHEDULE = (
    MODULE_ROOT / "configs/a1_source_independent_v3_generation_schedule_v1.json"
)
DEFAULT_BASE_CONFIG = (
    REPOSITORY_ROOT
    / "research_modules/scalable_3d_simulation/configs/nominal_200v200.json"
)
DEFAULT_OUTPUT = (
    MODULE_ROOT
    / "results/a1_v3_cross_seed_quota_probe_20260802/"
    "a1_v3_300_recipe_quota_probe.json"
)
CHECKPOINT_SCHEMA = "d3-a1-v3-cross-seed-quota-probe-checkpoint-v4"
PROBE_COUNTERFACTUAL_MODE = "coverage_degrading"
PROBE_REFERENCE_POLICY = "exact_safe_reference"
PROBE_MINIMUM_POSITIVE_FRAMES = 3
PROBE_MINIMUM_NEGATIVE_FRAMES = 3
PROBE_MINIMUM_HARD_NEGATIVE_FRAMES = 2

PROBE_SOURCE_BINDINGS = {
    "probe_runner": Path(__file__).resolve(),
    "probe_source": (
        MODULE_ROOT / "src/d3_assignment_planner/a1_v3_quota_probe.py"
    ),
    "sidecar_classifier": (
        MODULE_ROOT
        / "src/d3_assignment_planner/a1_v3_sidecar_classification.py"
    ),
    "sidecar_classification_policy": (
        MODULE_ROOT
        / "configs/a1_source_independent_v3_sidecar_classification_policy_v1.json"
    ),
    "frozen_request": (
        MODULE_ROOT
        / "configs/a1_source_independent_v3_development_data_request_v1.json"
    ),
    "dataset_writer": (
        MODULE_ROOT / "src/d3_assignment_planner/a1_v3_dataset_writer.py"
    ),
    "data_contract": (
        MODULE_ROOT / "src/d3_assignment_planner/a1_v3_data_contract.py"
    ),
    "source_generation_request_validation": (
        MODULE_ROOT
        / "src/d3_assignment_planner/a1_v3_source_generation_request.py"
    ),
    "source_only_projection": (
        MODULE_ROOT
        / "src/d3_assignment_planner/a1_v3_source_only_projection.py"
    ),
    "assignment_safety_projection": (
        MODULE_ROOT
        / "src/d3_assignment_planner/a1_assignment_aware_development.py"
    ),
    "learning_source_adapter": (
        REPOSITORY_ROOT
        / "research_modules/scalable_3d_simulation/learning_source_adapters.py"
    ),
    "learning_source_recipes": (
        REPOSITORY_ROOT
        / "research_modules/scalable_3d_simulation/learning_source_recipes.py"
    ),
    "episode_treatments": (
        REPOSITORY_ROOT
        / "research_modules/scalable_3d_simulation/episode_treatments.py"
    ),
    "orchestrator": (
        REPOSITORY_ROOT
        / "research_modules/scalable_3d_simulation/orchestrator.py"
    ),
    "generation_schedule": DEFAULT_SCHEDULE,
    "base_config": DEFAULT_BASE_CONFIG,
}

_WORKER_CONTEXT: dict[str, Any] = {}


def _required_probe_quota(recipe: Any) -> A1V3QuotaCounts:
    """Apply the non-negotiable 3/3/2 floor to every probe recipe."""

    return A1V3QuotaCounts(
        observable=recipe.minimum_observable_frames,
        positive=max(
            PROBE_MINIMUM_POSITIVE_FRAMES,
            recipe.minimum_positive_frames,
        ),
        negative=max(
            PROBE_MINIMUM_NEGATIVE_FRAMES,
            recipe.minimum_negative_frames,
        ),
        hard_negative=max(
            PROBE_MINIMUM_HARD_NEGATIVE_FRAMES,
            recipe.minimum_hard_negative_frames,
        ),
    )


def _initialize_worker(
    repository_root: str,
    schedule_path: str,
    base_config_path: str,
) -> None:
    from research_modules.d3_assignment_planner.src.d3_assignment_planner.a1_v3_dataset_writer import (
        load_a1_v3_writer_contract,
    )
    from research_modules.scalable_3d_simulation.learning_source_recipes import (
        load_d3_a1_v3_episode_recipes,
    )
    from research_modules.scalable_3d_simulation.models import ScenarioConfig

    root = Path(repository_root)
    schedule = Path(schedule_path)
    base_path = Path(base_config_path)
    recipes = load_d3_a1_v3_episode_recipes(schedule)
    if any(item.seed in A1_V3_FORBIDDEN_FORMAL_SEEDS for item in recipes):
        raise A1V3QuotaProbeError("forbidden_formal_seed_read")
    _WORKER_CONTEXT.update(
        {
            "root": root,
            "recipes": recipes,
            "base": ScenarioConfig.from_dict(
                json.loads(base_path.read_text(encoding="ascii"))
            ),
            "contract": load_a1_v3_writer_contract(),
        }
    )


def _probe_recipe(entry_index: int) -> dict[str, Any]:
    from research_modules.d3_assignment_planner.src.d3_assignment_planner.a1_v3_dataset_writer import (
        build_a1_v3_online_frame,
    )
    from research_modules.d3_assignment_planner.src.d3_assignment_planner.a1_v3_sidecar_classification import (
        analyze_a1_v3_anonymous_transition,
        derive_a1_v3_frame_classifications,
    )
    from research_modules.d3_assignment_planner.src.d3_assignment_planner.a1_v3_source_only_projection import (
        A1V3CounterfactualMode,
        A1V3PostProjectionReferencePolicy,
    )
    from research_modules.scalable_3d_simulation.learning_source_adapters import (
        adapt_d3_a1_runtime_frame,
    )
    from research_modules.scalable_3d_simulation.module_stack import (
        IntegratedScalableModuleStack,
        IntegratedStackConfig,
    )
    from research_modules.scalable_3d_simulation.orchestrator import run_episode

    recipe = _WORKER_CONTEXT["recipes"][entry_index]
    contract = _WORKER_CONTEXT["contract"]
    scheduled = contract.schedule.episodes[entry_index]
    required = _required_probe_quota(recipe)
    common = {
        "entry_index": entry_index,
        "episode_id": recipe.episode_id,
        "cell_id": recipe.cell_id,
        "scenario_family": recipe.scenario_family,
        "seed": recipe.seed,
        "split": recipe.split,
        "source_only_counterfactual_mode": PROBE_COUNTERFACTUAL_MODE,
        "source_only_contract": dict(A1_V3_QUOTA_PROBE_SOURCE_ONLY_CONTRACT),
        "required": required.to_dict(),
    }
    try:
        stack = IntegratedScalableModuleStack(
            IntegratedStackConfig(capture_learning_artifacts=True)
        )
        result = run_episode(recipe.build_config(_WORKER_CONTEXT["base"]), module_stack=stack)
        runtime_frames = tuple(
            stack.learning_artifacts().d3_a1_source_frames
        )
        adapted = tuple(
            adapt_d3_a1_runtime_frame(
                frame,
                source_only_counterfactual_mode=(
                    A1V3CounterfactualMode.COVERAGE_DEGRADING
                ),
                source_episode_key=(recipe.seed, recipe.episode_id),
                source_only_reference_policy=(
                    A1V3PostProjectionReferencePolicy.EXACT_SAFE_REFERENCE
                ),
            )
            for frame in runtime_frames
        )
        online = tuple(
            build_a1_v3_online_frame(scheduled, frame) for frame in adapted
        )
        if len(runtime_frames) != len(adapted) or len(adapted) != len(online):
            raise A1V3QuotaProbeError("source_only_frame_inventory_mismatch")
        online_payloads = tuple(frame.to_dict() for frame in online)
        if int(result.summary.get("online_truth_use_count", -1)) != 0:
            raise A1V3QuotaProbeError("probe_online_truth_use_nonzero")
        for evidence, frame, payload in zip(adapted, online, online_payloads, strict=True):
            if (
                frame.frame_key
                != (recipe.seed, recipe.episode_id, evidence.frame_index)
                or frame.source.measurement_timestamp_s
                != evidence.measurement_timestamp_s
                or frame.source.arrival_timestamp_s
                != evidence.arrival_timestamp_s
                or frame.source.arrival_timestamp_s
                <= frame.source.measurement_timestamp_s
            ):
                raise A1V3QuotaProbeError(
                    "source_only_frame_time_key_binding_mismatch"
                )
            ownership = payload["center_identity_ownership"]
            if (
                payload["online_truth_use_count"] != 0
                or ownership["learning_create_allowed"] is not False
                or ownership["learning_rewrite_allowed"] is not False
                or any(payload["permissions"].values())
            ):
                raise A1V3QuotaProbeError(
                    "source_only_online_authority_nonzero"
                )
        classified = derive_a1_v3_frame_classifications(
            scheduled,
            online,
            request=contract.request,
            policy=contract.sidecar_classification_policy,
        )
        classes = Counter(item.frame_class for item in classified)
        counts = A1V3QuotaCounts(
            observable=len(online),
            positive=classes["positive"],
            negative=classes["negative"],
            hard_negative=sum(item.hard_negative for item in classified),
        )
        missing = missing_a1_v3_quota(counts, required)
        frames = []
        previous = None
        for frame, label, payload in zip(
            online, classified, online_payloads, strict=True
        ):
            transition = analyze_a1_v3_anonymous_transition(previous, frame)
            reason = (
                label.action_change_type
                if label.frame_class == "positive"
                else label.hard_negative_type
                or "keep_exact_r0_no_derived_hard_negative"
            )
            frames.append(
                {
                    "frame_index": label.frame_index,
                    "measurement_timestamp_s": frame.source.measurement_timestamp_s,
                    "arrival_timestamp_s": frame.source.arrival_timestamp_s,
                    "frame_key": frame.frame_key,
                    "source_only_counterfactual_mode": (
                        PROBE_COUNTERFACTUAL_MODE
                    ),
                    "post_projection_reference_policy": (
                        PROBE_REFERENCE_POLICY
                    ),
                    "frame_class": label.frame_class,
                    "hard_negative": label.hard_negative,
                    "reason": reason,
                    "action_change_type": label.action_change_type,
                    "hard_negative_type": label.hard_negative_type,
                    "transition_axes": list(transition.changed_axes),
                    "candidate_edge_count_before": (
                        transition.candidate_edge_count_before
                    ),
                    "candidate_edge_count_after": (
                        transition.candidate_edge_count_after
                    ),
                    "candidate_edge_count_delta": (
                        transition.candidate_edge_count_delta
                    ),
                    "candidate_edge_added_count": (
                        transition.candidate_edge_added_count
                    ),
                    "candidate_edge_removed_count": (
                        transition.candidate_edge_removed_count
                    ),
                    "teacher_edge_count_delta": (
                        transition.teacher_edge_count_delta
                    ),
                    "coverage_deficit_delta": (
                        transition.coverage_deficit_delta
                    ),
                    "near_tie_qualifying_target_count": (
                        frame.near_tie_qualifying_target_count
                    ),
                    "teacher_edge_count": len(frame.teacher_edges),
                    "candidate_selected_edge_count": len(
                        frame.candidate_selected_edges
                    ),
                    "effective_selected_edge_count": len(
                        frame.effective_selected_edges
                    ),
                    "candidate_differs_from_teacher": (
                        frame.candidate_selected_edges != frame.teacher_edges
                    ),
                    "effective_matches_teacher": (
                        frame.effective_selected_edges == frame.teacher_edges
                    ),
                    "online_truth_use_count": payload["online_truth_use_count"],
                    "global_track_id_created_count": 0,
                    "global_track_id_rewritten_count": 0,
                    "pre_projection_reason_codes": list(
                        frame.pre_projection_reason_codes
                    ),
                    "post_projection_reason_codes": list(
                        frame.post_projection_reason_codes
                    ),
                }
            )
            previous = frame
        record = {
            **common,
            "status": "pass" if quota_met(missing) else "quota_failed",
            "counts": counts.to_dict(),
            "missing": missing.to_dict(),
            "online_truth_use_count": sum(
                int(payload["online_truth_use_count"])
                for payload in online_payloads
            ),
            "global_track_id_created_count": 0,
            "global_track_id_rewritten_count": 0,
            "finite_state": bool(result.summary.get("finite_state")),
            "frames": frames,
            "probe_error_code": None,
        }
    except Exception as exc:
        zero = A1V3QuotaCounts(0, 0, 0, 0)
        record = {
            **common,
            "status": "probe_error",
            "counts": zero.to_dict(),
            "missing": missing_a1_v3_quota(zero, required).to_dict(),
            "online_truth_use_count": 0,
            "global_track_id_created_count": 0,
            "global_track_id_rewritten_count": 0,
            "finite_state": False,
            "frames": [],
            "probe_error_code": (
                str(exc)
                if isinstance(exc, A1V3QuotaProbeError)
                else "worker_exception"
            ).split(":", 1)[0],
        }
        # Keep the checkpoint schema strict while surfacing the error through stderr.
        print(
            json.dumps(
                {
                    "episode_id": recipe.episode_id,
                    "probe_error_type": type(exc).__name__,
                    "probe_error": str(exc),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
            flush=True,
        )
    validate_probe_episode_record(record)
    return record


def _checkpoint_paths(output: Path) -> tuple[Path, Path]:
    return (
        output.with_suffix(output.suffix + ".checkpoint.json"),
        output.with_suffix(output.suffix + ".episodes.jsonl"),
    )


def _checkpoint_binding(
    *,
    schedule_sha256: str,
    base_config_sha256: str,
    source_git_commit: str,
    repository_dirty: bool,
    source_bindings: Mapping[str, Mapping[str, str]],
) -> dict[str, Any]:
    return {
        "schema_version": CHECKPOINT_SCHEMA,
        "schedule_sha256": schedule_sha256,
        "base_config_sha256": base_config_sha256,
        "source_git_commit": source_git_commit,
        "repository_dirty": repository_dirty,
        "source_bindings": dict(source_bindings),
        "source_only_contract": dict(A1_V3_QUOTA_PROBE_SOURCE_ONLY_CONTRACT),
        "formal_source_generation": False,
        "dataset_finalized": False,
        "training_started": False,
    }


def _load_checkpoint(
    output: Path,
    *,
    expected_binding: Mapping[str, Any],
) -> dict[int, dict[str, Any]]:
    manifest_path, rows_path = _checkpoint_paths(output)
    if not manifest_path.exists() and not rows_path.exists():
        write_json_atomic(manifest_path, expected_binding)
        rows_path.parent.mkdir(parents=True, exist_ok=True)
        rows_path.touch(exist_ok=False)
        return {}
    if not manifest_path.is_file() or not rows_path.is_file():
        raise A1V3QuotaProbeError("probe_checkpoint_inventory_incomplete")
    actual = json.loads(manifest_path.read_text(encoding="ascii"))
    if actual != expected_binding:
        raise A1V3QuotaProbeError("probe_checkpoint_binding_mismatch")
    records: dict[int, dict[str, Any]] = {}
    for line_number, line in enumerate(
        rows_path.read_text(encoding="ascii").splitlines(), start=1
    ):
        if not line:
            raise A1V3QuotaProbeError(
                f"probe_checkpoint_blank_line:{line_number}"
            )
        record = json.loads(line)
        validate_probe_episode_record(record)
        index = record["entry_index"]
        if index in records:
            raise A1V3QuotaProbeError("probe_checkpoint_duplicate_entry")
        records[index] = record
    return records


def _append_checkpoint(path: Path, record: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (
        json.dumps(
            record,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("ascii")
    with path.open("ab") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())


def _git_commit() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _repository_dirty() -> bool:
    completed = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return bool(completed.stdout.strip())


def _source_bindings() -> dict[str, dict[str, str]]:
    bindings: dict[str, dict[str, str]] = {}
    for name, path in PROBE_SOURCE_BINDINGS.items():
        resolved = path.expanduser().resolve()
        bindings[name] = {
            "path": str(resolved.relative_to(REPOSITORY_ROOT)),
            "sha256": sha256(resolved.read_bytes()).hexdigest(),
        }
    bindings["source_only_projection"]["selected_counterfactual_mode"] = (
        PROBE_COUNTERFACTUAL_MODE
    )
    bindings["source_only_projection"][
        "selected_post_projection_reference_policy"
    ] = PROBE_REFERENCE_POLICY
    return bindings


def run_probe(
    *,
    schedule_path: Path,
    base_config_path: Path,
    output: Path,
    workers: int,
) -> dict[str, Any]:
    from research_modules.scalable_3d_simulation.learning_source_recipes import (
        load_d3_a1_v3_episode_recipes,
    )

    schedule = schedule_path.expanduser().resolve()
    base_config = base_config_path.expanduser().resolve()
    destination = output.expanduser().resolve()
    recipes = load_d3_a1_v3_episode_recipes(schedule)
    if len(recipes) != 300:
        raise A1V3QuotaProbeError("probe_frozen_schedule_count_mismatch")
    if {item.seed for item in recipes} & A1_V3_FORBIDDEN_FORMAL_SEEDS:
        raise A1V3QuotaProbeError("forbidden_formal_seed_read")
    schedule_sha = sha256(schedule.read_bytes()).hexdigest()
    base_sha = sha256(base_config.read_bytes()).hexdigest()
    git_commit = _git_commit()
    repository_dirty = _repository_dirty()
    source_bindings = _source_bindings()
    binding = _checkpoint_binding(
        schedule_sha256=schedule_sha,
        base_config_sha256=base_sha,
        source_git_commit=git_commit,
        repository_dirty=repository_dirty,
        source_bindings=source_bindings,
    )
    records = _load_checkpoint(destination, expected_binding=binding)
    _, rows_path = _checkpoint_paths(destination)
    pending = [index for index in range(len(recipes)) if index not in records]
    started = time.perf_counter()
    if pending:
        with ProcessPoolExecutor(
            max_workers=workers,
            initializer=_initialize_worker,
            initargs=(str(REPOSITORY_ROOT), str(schedule), str(base_config)),
        ) as executor:
            futures = {executor.submit(_probe_recipe, index): index for index in pending}
            for completed_count, future in enumerate(as_completed(futures), start=1):
                record = future.result()
                records[record["entry_index"]] = record
                _append_checkpoint(rows_path, record)
                total = len(records)
                if completed_count % 5 == 0 or record["status"] != "pass":
                    passed = sum(item["status"] == "pass" for item in records.values())
                    print(
                        f"PROGRESS {total}/300 pass={passed} "
                        f"fail={total - passed} elapsed_s={time.perf_counter() - started:.1f}",
                        flush=True,
                    )
    report = build_a1_v3_quota_probe_report(
        tuple(records.values()),
        schedule_path=str(schedule.relative_to(REPOSITORY_ROOT)),
        schedule_sha256=schedule_sha,
        base_config_path=str(base_config.relative_to(REPOSITORY_ROOT)),
        base_config_sha256=base_sha,
        source_git_commit=git_commit,
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        elapsed_s=time.perf_counter() - started,
        repository_dirty=repository_dirty,
        source_bindings=source_bindings,
    )
    report["content_sha256"] = canonical_json_sha256(report)
    write_json_atomic(destination, report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schedule", type=Path, default=DEFAULT_SCHEDULE)
    parser.add_argument("--base-config", type=Path, default=DEFAULT_BASE_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--workers", type=int, default=2)
    arguments = parser.parse_args(argv)
    if arguments.workers < 1 or arguments.workers > 8:
        parser.error("--workers must be between 1 and 8")
    result = run_probe(
        schedule_path=arguments.schedule,
        base_config_path=arguments.base_config,
        output=arguments.output,
        workers=arguments.workers,
    )
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "status",
                    "episode_count",
                    "pass_count",
                    "failure_count",
                    "probe_error_count",
                    "online_truth_use_count",
                    "duplicate_frame_count",
                    "content_sha256",
                )
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if result["status"] == "pass_300_of_300" else 2


if __name__ == "__main__":
    raise SystemExit(main())
