#!/usr/bin/env python3
"""Summarize D1 EO association-risk shadow evidence from completed episodes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_modules.scalable_3d_simulation.d1_association_risk_calibration import (
    AssociationRiskCalibrationCase,
    run_d1_association_risk_calibration,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--case",
        action="append",
        metavar="CASE_ID=EPISODE_DIR",
    )
    source.add_argument("--episode-root", type=Path)
    parser.add_argument("--episode-glob", default="*/*")
    parser.add_argument(
        "--diagnostics-root",
        type=Path,
        help=(
            "D2 read-only identity diagnostics output; required with "
            "--episode-root"
        ),
    )
    parser.add_argument(
        "--failure-event",
        action="append",
        default=[],
        metavar="CASE_ID=SENSOR_ID@MEASUREMENT_TIMESTAMP",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--validation-role",
        choices=("development", "held_out"),
        default="development",
    )
    parser.add_argument(
        "--require-online-classifications",
        action="store_true",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.episode_root is None:
        paths_by_case = _parse_cases(args.case)
        events_by_case = _parse_events(
            args.failure_event,
            case_ids=set(paths_by_case),
        )
    else:
        if args.diagnostics_root is None:
            raise ValueError(
                "--diagnostics-root is required with --episode-root"
            )
        paths_by_case, events_by_case, skipped = (
            _discover_diagnostic_cases(
                args.episode_root,
                episode_glob=args.episode_glob,
                diagnostics_root=args.diagnostics_root,
            )
        )
        manual_events = _parse_events(
            args.failure_event,
            case_ids=set(paths_by_case),
        )
        for case_id, values in manual_events.items():
            events_by_case.setdefault(case_id, []).extend(values)
        print(f"diagnostic_cases={len(paths_by_case)}")
        print(f"diagnostic_cases_skipped={skipped}")
    paths = run_d1_association_risk_calibration(
        args.output,
        cases=(
            AssociationRiskCalibrationCase(
                case_id=case_id,
                episode_dir=episode_dir,
                expected_failure_events=tuple(events_by_case.get(case_id, ())),
            )
            for case_id, episode_dir in paths_by_case.items()
        ),
        validation_role=args.validation_role,
        require_online_classifications=(
            args.require_online_classifications
        ),
    )
    print(f"summary={paths['summary']}")
    print(f"rows={paths['rows']}")
    print(f"report={paths['report']}")
    return 0


def _parse_cases(values: list[str]) -> dict[str, Path]:
    cases: dict[str, Path] = {}
    for value in values:
        case_id, separator, raw_path = value.partition("=")
        case_id = case_id.strip()
        if not separator or not case_id or not raw_path.strip():
            raise ValueError("--case must use CASE_ID=EPISODE_DIR")
        if case_id in cases:
            raise ValueError(f"duplicate case: {case_id}")
        cases[case_id] = Path(raw_path.strip())
    return cases


def _parse_events(
    values: list[str],
    *,
    case_ids: set[str],
) -> dict[str, list[tuple[str, float]]]:
    events: dict[str, list[tuple[str, float]]] = {}
    for value in values:
        case_id, separator, raw_event = value.partition("=")
        sensor_id, event_separator, raw_timestamp = raw_event.rpartition("@")
        case_id = case_id.strip()
        sensor_id = sensor_id.strip()
        if (
            not separator
            or not event_separator
            or case_id not in case_ids
            or not sensor_id
        ):
            raise ValueError(
                "--failure-event must use CASE_ID=SENSOR_ID@MEASUREMENT_TIMESTAMP"
            )
        events.setdefault(case_id, []).append((sensor_id, float(raw_timestamp)))
    return events


def _discover_diagnostic_cases(
    episode_root: Path,
    *,
    episode_glob: str,
    diagnostics_root: Path,
) -> tuple[dict[str, Path], dict[str, list[tuple[str, float]]], int]:
    root = episode_root.expanduser().resolve()
    diagnostic_dir = diagnostics_root.expanduser().resolve() / "episodes"
    episode_dirs = sorted(
        path for path in root.glob(episode_glob) if path.is_dir()
    )
    if not episode_dirs:
        raise ValueError("no episode directories matched")
    paths: dict[str, Path] = {}
    events: dict[str, list[tuple[str, float]]] = {}
    skipped = 0
    for episode_dir in episode_dirs:
        manifest = _load_json(episode_dir / "manifest.json")
        episode_id = str(manifest.get("episode_id", "")).strip()
        if not episode_id:
            raise ValueError(f"episode manifest lacks episode_id: {episode_dir}")
        diagnostics = _load_json(
            diagnostic_dir / f"{episode_id}_identity_blockers.json"
        )
        if diagnostics.get("episode_id") != episode_id:
            raise ValueError(f"diagnostic episode identity mismatch: {episode_id}")
        identity_boundary = diagnostics.get("identity_boundary")
        if (
            not isinstance(identity_boundary, Mapping)
            or identity_boundary.get("online_truth_isolation_verified")
            is not True
            or identity_boundary.get("usage") != "offline_evaluation_only"
            or identity_boundary.get("identity_heuristics_used") is not False
        ):
            raise ValueError(
                f"diagnostics did not verify online truth isolation: {episode_id}"
            )
        failure_events = _camera_caused_multi_truth_events(diagnostics)
        identity = _load_json(
            episode_dir / "offline_identity" / "identity_evaluation.json"
        )
        metrics = identity.get("metrics")
        if not isinstance(metrics, Mapping):
            raise ValueError(f"identity metrics are missing: {episode_id}")
        strict_available = bool(metrics.get("truth_metrics_available"))
        if not failure_events and not strict_available:
            skipped += 1
            continue
        relative = episode_dir.relative_to(root)
        case_id = "__".join(relative.parts)
        if case_id in paths:
            raise ValueError(f"duplicate discovered case_id: {case_id}")
        paths[case_id] = episode_dir
        events[case_id] = list(failure_events)
    if not paths:
        raise ValueError("no eligible camera-failure or passing-control cases")
    return paths, events, skipped


def _camera_caused_multi_truth_events(
    diagnostics: Mapping[str, Any],
) -> tuple[tuple[str, float], ...]:
    events: set[tuple[str, float]] = set()
    for event in diagnostics.get("causal_mapping_events", ()):
        if not isinstance(event, Mapping):
            raise ValueError("causal mapping event must be a mapping")
        if event.get("reason") != "multiple_truth_targets_for_global_track":
            continue
        transition = event.get("sensor_transition")
        if not isinstance(transition, Mapping):
            continue
        newest_modalities = {
            str(value).strip().lower()
            for value in transition.get("newest_modalities", ())
        }
        if "camera" not in newest_modalities:
            continue
        for observation in event.get("source_observations", ()):
            if not isinstance(observation, Mapping):
                continue
            if (
                observation.get("is_newest_measurement") is not True
                or str(observation.get("sensor_modality", "")).lower()
                != "camera"
            ):
                continue
            sensor_id = str(observation.get("sensor_id", "")).strip()
            timestamp = float(observation.get("measurement_timestamp"))
            if not sensor_id or timestamp < 0.0:
                raise ValueError("camera causal event lacks sensor or timestamp")
            events.add((sensor_id, timestamp))
    return tuple(sorted(events))


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON payload must be an object: {path}")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
