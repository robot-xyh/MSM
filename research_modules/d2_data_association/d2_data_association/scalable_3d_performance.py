"""Reproducible semantic and timing comparison for scalable D2 episodes."""

from __future__ import annotations

import csv
from hashlib import sha256
import json
from pathlib import Path
from statistics import mean
from typing import Any, Iterable


SCALABLE_3D_D2_PERFORMANCE_COMPARISON_SCHEMA_VERSION = (
    "d2-scalable3d-performance-comparison-v1"
)
_D2_TOPIC = "modules.d2.associated_tracks"
_ASSOCIATION_STAGE = "module.d2_association"
_FINALIZE_STAGE = "module.d2_association_finalize"


def compare_scalable_3d_d2_performance(
    baseline_root: str | Path,
    candidate_root: str | Path,
    *,
    relative_scenario_dir: str | Path = "nominal/200v200",
    seeds: Iterable[int] | None = None,
) -> dict[str, Any]:
    """Compare frozen baseline episodes with optimized reruns.

    Runtime fields live outside D2 publications. Therefore an exact canonical
    hash of each D2 envelope covers association decisions, center-owned IDs,
    lifecycle states, observation claims, replay decisions and risk audit
    fields without masking a semantic difference as a timing difference.
    """

    baseline_parent = Path(baseline_root) / Path(relative_scenario_dir)
    candidate_parent = Path(candidate_root) / Path(relative_scenario_dir)
    seed_values = (
        tuple(sorted(set(int(seed) for seed in seeds)))
        if seeds is not None
        else _common_seed_values(baseline_parent, candidate_parent)
    )
    if not seed_values:
        raise ValueError("no common seed directories were found")

    episodes = [
        compare_scalable_3d_d2_episode(
            baseline_parent / f"seed_{seed}",
            candidate_parent / f"seed_{seed}",
        )
        for seed in seed_values
    ]
    regular_baseline = [item["timing"]["baseline_association_seconds"] for item in episodes]
    regular_candidate = [item["timing"]["candidate_association_seconds"] for item in episodes]
    finalize_baseline = [item["timing"]["baseline_finalize_seconds"] for item in episodes]
    finalize_candidate = [item["timing"]["candidate_finalize_seconds"] for item in episodes]
    total_baseline = [left + right for left, right in zip(regular_baseline, finalize_baseline, strict=True)]
    total_candidate = [left + right for left, right in zip(regular_candidate, finalize_candidate, strict=True)]

    return {
        "schema_version": SCALABLE_3D_D2_PERFORMANCE_COMPARISON_SCHEMA_VERSION,
        "baseline_root": str(Path(baseline_root).resolve()),
        "candidate_root": str(Path(candidate_root).resolve()),
        "relative_scenario_dir": str(Path(relative_scenario_dir)),
        "seed_count": len(seed_values),
        "seeds": list(seed_values),
        "all_semantics_equal": all(item["semantics_equal"] for item in episodes),
        "all_online_truth_free": all(item["online_truth_free"] for item in episodes),
        "aggregate_timing": {
            "baseline_association_mean_seconds": mean(regular_baseline),
            "candidate_association_mean_seconds": mean(regular_candidate),
            "association_speedup": _speedup(regular_baseline, regular_candidate),
            "baseline_finalize_mean_seconds": mean(finalize_baseline),
            "candidate_finalize_mean_seconds": mean(finalize_candidate),
            "finalize_speedup": _speedup(finalize_baseline, finalize_candidate),
            "baseline_total_mean_seconds": mean(total_baseline),
            "candidate_total_mean_seconds": mean(total_candidate),
            "total_speedup": _speedup(total_baseline, total_candidate),
        },
        "episodes": episodes,
    }


def compare_scalable_3d_d2_episode(
    baseline_episode_dir: str | Path,
    candidate_episode_dir: str | Path,
) -> dict[str, Any]:
    """Compare one seed while keeping timing separate from online semantics."""

    baseline_dir = Path(baseline_episode_dir)
    candidate_dir = Path(candidate_episode_dir)
    baseline_records = _d2_records(baseline_dir / "online_observations.jsonl")
    candidate_records = _d2_records(candidate_dir / "online_observations.jsonl")
    if not baseline_records or not candidate_records:
        raise ValueError("both episodes must contain D2 associated-track records")

    baseline_domains = _semantic_domains(baseline_records)
    candidate_domains = _semantic_domains(candidate_records)
    baseline_summary = _load_json(baseline_dir / "summary.json")
    candidate_summary = _load_json(candidate_dir / "summary.json")
    baseline_timing = _stage_timings(baseline_dir / "stage_timings.csv")
    candidate_timing = _stage_timings(candidate_dir / "stage_timings.csv")
    baseline_config_hash = _sha256_file(baseline_dir / "scenario_config.json")
    candidate_config_hash = _sha256_file(candidate_dir / "scenario_config.json")
    baseline_truth_hash = _sha256_file(baseline_dir / "offline_truth_labels.jsonl")
    candidate_truth_hash = _sha256_file(candidate_dir / "offline_truth_labels.jsonl")

    domain_equality = {
        name: baseline_domains[name] == candidate_domains[name]
        for name in baseline_domains
    }
    cycle_hashes_equal = (
        baseline_domains["cycle_sha256"] == candidate_domains["cycle_sha256"]
    )
    config_equal = baseline_config_hash == candidate_config_hash
    truth_equal = baseline_truth_hash == candidate_truth_hash
    online_truth_free = (
        int(baseline_summary.get("online_truth_use_count", -1)) == 0
        and int(candidate_summary.get("online_truth_use_count", -1)) == 0
    )
    semantics_equal = bool(
        all(domain_equality.values())
        and cycle_hashes_equal
        and config_equal
        and truth_equal
    )
    seed = int(candidate_summary.get("seed", baseline_summary.get("seed", -1)))

    return {
        "seed": seed,
        "baseline_episode_dir": str(baseline_dir.resolve()),
        "candidate_episode_dir": str(candidate_dir.resolve()),
        "d2_cycle_count": len(baseline_records),
        "candidate_d2_cycle_count": len(candidate_records),
        "semantics_equal": semantics_equal,
        "domain_equality": domain_equality,
        "cycle_hashes_equal": cycle_hashes_equal,
        "scenario_config_equal": config_equal,
        "offline_truth_sidecar_equal": truth_equal,
        "online_truth_free": online_truth_free,
        "baseline_hashes": baseline_domains,
        "candidate_hashes": candidate_domains,
        "scenario_config_sha256": baseline_config_hash,
        "offline_truth_labels_sha256": baseline_truth_hash,
        "timing": {
            "baseline_association_seconds": _required_stage(
                baseline_timing, _ASSOCIATION_STAGE
            ),
            "candidate_association_seconds": _required_stage(
                candidate_timing, _ASSOCIATION_STAGE
            ),
            "baseline_finalize_seconds": _required_stage(
                baseline_timing, _FINALIZE_STAGE
            ),
            "candidate_finalize_seconds": _required_stage(
                candidate_timing, _FINALIZE_STAGE
            ),
        },
    }


def write_scalable_3d_d2_performance_comparison(
    output_path: str | Path,
    report: dict[str, Any],
) -> str:
    """Write a stable JSON report and return its SHA-256 digest."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(report, indent=2, sort_keys=True) + "\n"
    path.write_text(content, encoding="utf-8")
    return sha256(content.encode("utf-8")).hexdigest()


def _d2_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number} must contain a JSON object")
            if value.get("topic") == _D2_TOPIC:
                records.append(value)
    return records


def _semantic_domains(records: list[dict[str, Any]]) -> dict[str, Any]:
    payloads = [record["payload"] for record in records]
    associations = [payload["association"] for payload in payloads]
    identity_lifecycle = [
        {
            "timestamp": payload["timestamp"],
            "track_count": payload["track_count"],
            "tracks": payload["tracks"],
            "id_switch_count": payload["id_switch_count"],
            "id_switch_count_available": payload["id_switch_count_available"],
            "identity_lineage_policy": payload["identity_lineage_policy"],
            "identity_lineage": payload["identity_lineage"],
        }
        for payload in payloads
    ]
    claims = [
        association["observation_evidence_governance"]
        for association in associations
    ]
    return {
        "full_d2_records_sha256": _canonical_sha256(records),
        "association_sha256": _canonical_sha256(associations),
        "identity_lifecycle_sha256": _canonical_sha256(identity_lifecycle),
        "claim_and_audit_sha256": _canonical_sha256(claims),
        "cycle_sha256": [_canonical_sha256(record) for record in records],
    }


def _stage_timings(path: Path) -> dict[str, float]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = csv.DictReader(handle)
        return {
            str(row["stage"]): float(row["wall_time_s"])
            for row in rows
        }


def _required_stage(values: dict[str, float], name: str) -> float:
    if name not in values:
        raise ValueError(f"required timing stage is missing: {name}")
    return values[name]


def _common_seed_values(left: Path, right: Path) -> tuple[int, ...]:
    def values(parent: Path) -> set[int]:
        result: set[int] = set()
        for path in parent.glob("seed_*"):
            if not path.is_dir():
                continue
            try:
                result.add(int(path.name.removeprefix("seed_")))
            except ValueError:
                continue
        return result

    return tuple(sorted(values(left) & values(right)))


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _speedup(baseline: list[float], candidate: list[float]) -> float | None:
    candidate_mean = mean(candidate)
    return mean(baseline) / candidate_mean if candidate_mean > 0.0 else None
