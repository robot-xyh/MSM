"""Fail-closed reporting for the 20/40/60/100 target scale funnel.

This module only reads sealed benchmark artifacts.  It never opens route-specific
validation evidence, reruns an association route, or changes a promotion decision.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from statistics import fmean
from typing import Any, Mapping, Sequence

import matplotlib

matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt


SUPPORTED_TARGET_COUNTS = (20, 40, 60, 100)
ROUTE_ORDER = ("epipolar_mht", "lightweight", "gnn", "track_superglue")
ROUTE_LABELS_CN = {
    "epipolar_mht": "增强几何/多假设/匈牙利",
    "lightweight": "轻量几何/匈牙利",
    "gnn": "图网络/匈牙利",
    "track_superglue": "航迹级注意力/最优传输",
}
ROUTE_LABELS_EN = {
    "epipolar_mht": "Enhanced geometry",
    "lightweight": "Lightweight geometry",
    "gnn": "Graph network",
    "track_superglue": "Track SuperGlue",
}
ROUTE_COLORS = {
    "epipolar_mht": "#4f6272",
    "lightweight": "#2e7d32",
    "gnn": "#1565c0",
    "track_superglue": "#8e5a2b",
}
STATUS_LABELS_CN = {
    "eliminated_on_validation": "验证淘汰",
    "eliminated_on_heldout": "保留集淘汰",
    "promoted": "晋级",
    "final_tier_passed": "最终档通过",
    "final_tier_failed": "最终档未通过",
    "tracker_calibration_failed": "共享跟踪器正式标定失败",
}
REASON_LABELS_CN = {
    "conditional_precision_floor_not_met": "条件精确率未达到验证门槛",
    "route_validation_failed_closed": "路线验证失败关闭",
    "zero_validation_association_skill": "验证阶段未形成有效关联",
    "tiny_validation_association_output": "验证阶段有效输出过少",
    "validation_rejected": "未通过验证门槛",
    "latency_p95_exceeded_1000ms": "P95时延超过1000毫秒",
    "conditional_precision_below_0_70": "条件精确率低于0.70",
    "medium_heavy_on_time_recall_decreased_2pp": "中重干扰按时召回率下降超过2个百分点",
    "paired_recall_delta_ci95_below_zero": "配对召回率差值的95%置信区间低于零",
    "false_opportunity_rate_increased_without_5pp_recall": "错配率上升且召回率增益不足5个百分点",
    "deadline_rate_decreased_10pp": "按时完成率下降超过10个百分点",
    "compute_increased_without_2pp_recall": "计算量增加且召回率增益不足2个百分点",
    "identity_or_one_to_one_contract_violation": "发生身份或一对一约束违规",
    "false_reactivation_rate_absolute": "错误重激活率超过0.005",
    "false_reactivation_rate_not_above_baseline": "错误重激活率高于基线",
    "fragmentation_not_above_baseline": "航迹碎片数高于基线",
    "sweep_runtime_p95_ms": "单圈跟踪95%分位时延超过250毫秒",
    "absolute_on_time_recall_below_0_25": "按时召回率低于0.25",
    "superglue_recall_gain_below_2pp": "航迹级注意力路线召回率增益不足2个百分点",
    "superglue_paired_ci95_lower_below_zero": "航迹级注意力路线配对置信区间下界低于零",
    "superglue_false_opportunity_rate_increased_over_0_005": "航迹级注意力路线错配机会率增量超过0.005",
    "median_track_purity": "航迹纯度未达到正式标定门槛",
    "light_common_confirmed_rate": "轻干扰共同成轨率未达到正式标定门槛",
    "medium_common_confirmed_rate": "中干扰共同成轨率未达到正式标定门槛",
    "heavy_common_confirmed_rate": "重干扰共同成轨率未达到正式标定门槛",
}
ARTIFACT_RELATIVE_PATHS = {
    "comparison_metrics": Path("results/comparison_metrics.json"),
    "promotion_manifest": Path("results/promotion_manifest.json"),
    "preflight_summary": Path("preflight/preflight_summary.json"),
    "shared_tracker": Path("dataset/freezes/shared_tracker.json"),
    "all_routes_frozen": Path("dataset/freezes/all_routes_frozen.json"),
    "raw_calibration_manifest": Path("dataset/raw_calibration_manifest.json"),
    "shared_tracker_calibration": Path(
        "dataset/freezes/shared_tracker_calibration.json"
    ),
}
FINALIZATION_ARTIFACTS = (
    "comparison_metrics",
    "promotion_manifest",
    "shared_tracker",
    "all_routes_frozen",
)
CSV_FIELDS = (
    "target_count",
    "route_name",
    "route_label_cn",
    "status",
    "status_cn",
    "validation_f1",
    "precision",
    "recall",
    "f1",
    "latency_p95_ms",
    "conditional_precision",
    "candidate_true_retention_rate",
    "common_confirmed_rate_mean",
    "common_confirmed_rate_worst",
    "preflight_ideal_common_confirmed_rate",
    "preflight_pose_error_common_confirmed_rate",
    "preflight_full_interference_common_confirmed_rate",
    "identity_contract_violations",
    "false_association_count",
    "tracker_candidate_count",
    "tracker_accepted_candidate_count",
    "failure_reason_codes",
    "failure_reasons_cn",
)
TRACKER_CANDIDATE_CSV_FIELDS = (
    "target_count",
    "candidate_index",
    "selected",
    "tracker_fingerprint",
    "accepted",
    "median_track_purity",
    "clean_common_confirmed_rate",
    "light_common_confirmed_rate",
    "medium_common_confirmed_rate",
    "heavy_common_confirmed_rate",
    "mean_fragmentation",
    "false_reactivation_rate",
    "baseline_false_reactivation_rate",
    "sweep_runtime_p95_ms",
    "failed_check_codes",
    "failed_checks_cn",
)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read valid JSON object: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


def _sequence(value: Any, name: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{name} must be an array")
    return value


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    return float(value)


def _integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return int(value)


def _routes(value: Any, name: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    routes = tuple(str(item) for item in _sequence(value, name))
    if (
        (not routes and not allow_empty)
        or len(routes) != len(set(routes))
        or any(route not in ROUTE_ORDER for route in routes)
    ):
        raise ValueError(f"{name} contains an invalid route set")
    return routes


def _artifact_paths(funnel_root: Path, target_count: int) -> dict[str, Path]:
    tier_root = funnel_root / f"targets_{target_count:03d}"
    return {
        name: tier_root / relative
        for name, relative in ARTIFACT_RELATIVE_PATHS.items()
    }


def _discover_tiers(
    funnel_root: Path,
) -> tuple[
    tuple[int, ...],
    tuple[int, ...],
    tuple[int, ...],
    dict[int, dict[str, Path]],
]:
    paths_by_tier: dict[int, dict[str, Path]] = {}
    completed: list[int] = []
    preflight_only: list[int] = []
    tracker_calibration_failed: list[int] = []
    for target_count in SUPPORTED_TARGET_COUNTS:
        paths = _artifact_paths(funnel_root, target_count)
        paths_by_tier[target_count] = paths
        present = {name for name, path in paths.items() if path.is_file()}
        finalization_started = bool(present.intersection(FINALIZATION_ARTIFACTS))
        if finalization_started:
            required = (
                "comparison_metrics",
                "promotion_manifest",
                "preflight_summary",
                "shared_tracker",
                "all_routes_frozen",
            )
            missing = [name for name in required if name not in present]
            if missing:
                joined = ", ".join(missing)
                raise FileNotFoundError(
                    f"targets_{target_count:03d} is partially sealed; missing: {joined}"
                )
            completed.append(target_count)
        elif present.intersection(
            {"raw_calibration_manifest", "shared_tracker_calibration"}
        ):
            required = (
                "preflight_summary",
                "raw_calibration_manifest",
                "shared_tracker_calibration",
            )
            missing = [name for name in required if name not in present]
            if missing:
                joined = ", ".join(missing)
                raise FileNotFoundError(
                    f"targets_{target_count:03d} has partial tracker calibration; "
                    f"missing: {joined}"
                )
            calibration = _read_json(paths["shared_tracker_calibration"])
            acceptance = _mapping(
                calibration.get("acceptance"), "tracker calibration acceptance"
            )
            if acceptance.get("accepted") is not False:
                raise ValueError(
                    f"targets_{target_count:03d} tracker calibration did not fail "
                    "but freeze/test artifacts are absent"
                )
            tracker_calibration_failed.append(target_count)
        elif "preflight_summary" in present:
            preflight_only.append(target_count)

    if not completed:
        raise ValueError("no completed scale tier was found")
    expected = list(SUPPORTED_TARGET_COUNTS[: len(completed)])
    if completed != expected:
        raise ValueError(
            f"completed scale tiers are not a contiguous prefix: {completed}"
        )
    allowed_terminal = (
        []
        if len(completed) == len(SUPPORTED_TARGET_COUNTS)
        else [SUPPORTED_TARGET_COUNTS[len(completed)]]
    )
    if preflight_only and tracker_calibration_failed:
        raise ValueError("a scale cannot be both preflight-only and calibration-failed")
    if preflight_only not in ([], allowed_terminal):
        raise ValueError(
            "preflight-only tiers must contain only the immediate next scale"
        )
    if tracker_calibration_failed not in ([], allowed_terminal):
        raise ValueError(
            "tracker-calibration failure must be the immediate next scale"
        )
    return (
        tuple(completed),
        tuple(preflight_only),
        tuple(tracker_calibration_failed),
        paths_by_tier,
    )


def _check_optional_hash(
    source: Mapping[str, Any], field: str, artifact: Path, description: str
) -> None:
    expected = source.get(field)
    if expected is not None and str(expected) != _sha256(artifact):
        raise ValueError(f"{description} hash mismatch")


def _reason_cn(reason: str) -> str:
    return REASON_LABELS_CN.get(reason, reason)


def _mean_common_tracking(
    tracker: Mapping[str, Any],
) -> tuple[dict[str, float], float, float]:
    validation = _mapping(tracker.get("validation_metrics"), "tracker validation")
    levels = _mapping(
        validation.get("by_corruption_level"), "tracker corruption levels"
    )
    if not levels:
        raise ValueError("tracker corruption levels are empty")
    values: dict[str, float] = {}
    for level, raw in levels.items():
        item = _mapping(raw, f"tracker level {level}")
        values[str(level)] = _number(
            item.get("mean_common_confirmed_rate"),
            f"tracker level {level} common-confirmed rate",
        )
    return values, fmean(values.values()), min(values.values())


def _preflight_rates(preflight: Mapping[str, Any]) -> dict[str, float]:
    acceptance = _mapping(preflight.get("acceptance"), "preflight acceptance")
    scenarios = _mapping(acceptance.get("by_scenario"), "preflight scenarios")
    expected = ("ideal", "pose_error", "full_interference")
    missing = [name for name in expected if name not in scenarios]
    if missing:
        raise ValueError(f"preflight scenarios are incomplete: {missing}")
    return {
        name: _number(
            _mapping(scenarios[name], f"preflight {name}").get(
                "mean_common_confirmed_rate"
            ),
            f"preflight {name} common-confirmed rate",
        )
        for name in expected
    }


def _validation_tracking_summary(
    validation: Mapping[str, Any], name: str
) -> tuple[dict[str, float], float, float]:
    levels = _mapping(validation.get("by_corruption_level"), f"{name} levels")
    expected = ("clean", "light", "medium", "heavy")
    missing = [level for level in expected if level not in levels]
    if missing:
        raise ValueError(f"{name} levels are incomplete: {missing}")
    values = {
        level: _number(
            _mapping(levels[level], f"{name} {level}").get(
                "mean_common_confirmed_rate"
            ),
            f"{name} {level} common-confirmed rate",
        )
        for level in expected
    }
    purity = _number(validation.get("median_track_purity"), f"{name} purity")
    fragmentation = fmean(
        _number(
            _mapping(levels[level], f"{name} {level}").get(
                "mean_fragments_per_real_identity"
            ),
            f"{name} {level} fragmentation",
        )
        for level in expected
    )
    return values, purity, fragmentation


def _load_tracker_calibration_failure(
    target_count: int, paths: Mapping[str, Path]
) -> dict[str, Any]:
    preflight = _read_json(paths["preflight_summary"])
    manifest = _read_json(paths["raw_calibration_manifest"])
    calibration = _read_json(paths["shared_tracker_calibration"])
    expected_schemas = {
        "preflight": (preflight, "dual-optical-online-preflight-v1"),
        "raw calibration manifest": (
            manifest,
            "dual-optical-raw-calibration-manifest-v1",
        ),
    }
    for source_name, (source, schema) in expected_schemas.items():
        if source.get("schema_version") != schema:
            raise ValueError(f"unsupported {source_name} schema")
    calibration_schema = calibration.get("schema_version")
    if calibration_schema not in {
        "dual-optical-shared-tracker-calibration-v2",
        "dual-optical-shared-tracker-calibration-v3",
    }:
        raise ValueError("unsupported shared tracker calibration schema")
    protocol_fingerprint = str(preflight.get("protocol_fingerprint") or "")
    if not protocol_fingerprint:
        raise ValueError("preflight omits protocol fingerprint")
    for source_name, source in (
        ("raw calibration manifest", manifest),
        ("shared tracker calibration", calibration),
    ):
        if str(source.get("protocol_fingerprint") or "") != protocol_fingerprint:
            raise ValueError(f"{source_name} protocol fingerprint mismatch")
        if source.get("test_data_accessed") is not False:
            raise ValueError(f"{source_name} does not prove test-data isolation")
    if preflight.get("test_data_accessed") is not False:
        raise ValueError("preflight does not prove test-data isolation")
    _check_optional_hash(
        calibration,
        "calibration_manifest_sha256",
        paths["raw_calibration_manifest"],
        "raw calibration manifest",
    )
    manifest_reference = Path(
        str(calibration.get("calibration_manifest") or "")
    ).resolve()
    if manifest_reference != paths["raw_calibration_manifest"].resolve():
        raise ValueError("tracker calibration references a foreign raw manifest")

    acceptance = _mapping(
        calibration.get("acceptance"), "tracker calibration acceptance"
    )
    if acceptance.get("accepted") is not False:
        raise ValueError("tracker calibration failure evidence is not rejected")
    failure_reasons = tuple(
        str(value)
        for value in _sequence(
            acceptance.get("failure_reasons"),
            "tracker calibration failure reasons",
        )
    )
    thresholds_raw = _mapping(
        acceptance.get("thresholds"), "tracker calibration thresholds"
    )
    checks_raw = _mapping(
        acceptance.get("checks"), "tracker calibration checks"
    )
    base_checks = (
        "median_track_purity",
        "light_common_confirmed_rate",
        "medium_common_confirmed_rate",
        "heavy_common_confirmed_rate",
    )
    v3_checks = (
        "false_reactivation_rate_absolute",
        "false_reactivation_rate_not_above_baseline",
        "fragmentation_not_above_baseline",
        "sweep_runtime_p95_ms",
    )
    expected_checks = (
        (*base_checks, *v3_checks)
        if calibration_schema.endswith("v3")
        else base_checks
    )
    required_thresholds = set(base_checks)
    if calibration_schema.endswith("v3"):
        required_thresholds.update(
            {"maximum_false_reactivation_rate", "maximum_sweep_runtime_p95_ms"}
        )
    if set(thresholds_raw) != required_thresholds or set(checks_raw) != set(expected_checks):
        raise ValueError("tracker calibration acceptance checks are incomplete")
    failed_checks = tuple(name for name in expected_checks if checks_raw[name] is False)
    if (
        not failed_checks
        or set(failure_reasons) != set(failed_checks)
        or any(not isinstance(checks_raw[name], bool) for name in expected_checks)
    ):
        raise ValueError("tracker calibration failure reasons disagree with checks")
    thresholds = {
        name: _number(value, f"tracker threshold {name}")
        for name, value in thresholds_raw.items()
    }

    candidates_raw = _sequence(
        calibration.get("candidates"), "tracker calibration candidates"
    )
    candidate_count = _integer(
        calibration.get("candidate_count"), "tracker candidate_count"
    )
    accepted_candidate_count = _integer(
        calibration.get("accepted_candidate_count"),
        "tracker accepted_candidate_count",
    )
    if candidate_count != len(candidates_raw) or candidate_count <= 0:
        raise ValueError("tracker calibration candidate grid is incomplete")
    if accepted_candidate_count != 0:
        raise ValueError("rejected tracker calibration has accepted candidates")
    selected_fingerprint = str(calibration.get("selected_tracker_fingerprint") or "")
    if not selected_fingerprint:
        raise ValueError("tracker calibration omits selected candidate fingerprint")

    candidates: list[dict[str, Any]] = []
    seen_fingerprints: set[str] = set()
    calculated_accepted = 0
    for index, raw in enumerate(candidates_raw):
        candidate = _mapping(raw, f"tracker candidate {index}")
        fingerprint = str(candidate.get("tracker_fingerprint") or "")
        if not fingerprint or fingerprint in seen_fingerprints:
            raise ValueError("tracker calibration repeats or omits a candidate fingerprint")
        seen_fingerprints.add(fingerprint)
        candidate_validation = _mapping(
            candidate.get("validation"), f"tracker candidate {index} validation"
        )
        rates, purity, fragmentation = _validation_tracking_summary(
            candidate_validation,
            f"tracker candidate {index} validation",
        )
        checks = {
            "median_track_purity": purity >= thresholds["median_track_purity"],
            "light_common_confirmed_rate": rates["light"]
            >= thresholds["light_common_confirmed_rate"],
            "medium_common_confirmed_rate": rates["medium"]
            >= thresholds["medium_common_confirmed_rate"],
            "heavy_common_confirmed_rate": rates["heavy"]
            >= thresholds["heavy_common_confirmed_rate"],
        }
        false_reactivation_rate = _number(
            candidate_validation.get("false_reactivation_rate", 0.0),
            f"tracker candidate {index} false reactivation rate",
        )
        baseline_false_reactivation_rate = _number(
            candidate_validation.get(
                "baseline_false_reactivation_rate", false_reactivation_rate
            ),
            f"tracker candidate {index} baseline false reactivation rate",
        )
        baseline_fragmentation = _number(
            candidate_validation.get(
                "baseline_mean_fragments_per_real_identity", fragmentation
            ),
            f"tracker candidate {index} baseline fragmentation",
        )
        sweep_runtime_p95_ms = _number(
            candidate_validation.get("sweep_runtime_p95_ms", 0.0),
            f"tracker candidate {index} sweep runtime P95",
        )
        if calibration_schema.endswith("v3"):
            checks.update(
                {
                    "false_reactivation_rate_absolute": false_reactivation_rate
                    <= thresholds["maximum_false_reactivation_rate"],
                    "false_reactivation_rate_not_above_baseline": false_reactivation_rate
                    <= baseline_false_reactivation_rate + 1.0e-12,
                    "fragmentation_not_above_baseline": fragmentation
                    <= baseline_fragmentation + 1.0e-12,
                    "sweep_runtime_p95_ms": sweep_runtime_p95_ms
                    <= thresholds["maximum_sweep_runtime_p95_ms"],
                }
            )
        candidate_failed = [name for name, passed in checks.items() if not passed]
        accepted = not candidate_failed
        calculated_accepted += int(accepted)
        candidates.append(
            {
                "candidate_index": index,
                "selected": fingerprint == selected_fingerprint,
                "tracker_fingerprint": fingerprint,
                "accepted": accepted,
                "median_track_purity": purity,
                "mean_fragmentation": fragmentation,
                "false_reactivation_rate": false_reactivation_rate,
                "baseline_false_reactivation_rate": baseline_false_reactivation_rate,
                "baseline_mean_fragmentation": baseline_fragmentation,
                "sweep_runtime_p95_ms": sweep_runtime_p95_ms,
                "common_confirmed_rate_by_level": rates,
                "failed_check_codes": candidate_failed,
                "failed_checks_cn": [_reason_cn(name) for name in candidate_failed],
            }
        )
    if calculated_accepted != accepted_candidate_count:
        raise ValueError("tracker accepted_candidate_count disagrees with candidates")
    if sum(candidate["selected"] for candidate in candidates) != 1:
        raise ValueError("tracker calibration selected candidate is not unique")

    selected_validation = _mapping(
        calibration.get("selected_validation_metrics"),
        "selected tracker validation metrics",
    )
    selected_rates, selected_purity, selected_fragmentation = (
        _validation_tracking_summary(
            selected_validation, "selected tracker validation"
        )
    )
    selected_candidate = next(
        candidate for candidate in candidates if candidate["selected"]
    )
    if (
        selected_candidate["common_confirmed_rate_by_level"] != selected_rates
        or selected_candidate["median_track_purity"] != selected_purity
        or selected_candidate["mean_fragmentation"] != selected_fragmentation
    ):
        raise ValueError("selected tracker summary disagrees with candidate grid")
    metric_accessors = {
        "median_track_purity": lambda item: float(item["median_track_purity"]),
        "light_common_confirmed_rate": lambda item: float(
            item["common_confirmed_rate_by_level"]["light"]
        ),
        "medium_common_confirmed_rate": lambda item: float(
            item["common_confirmed_rate_by_level"]["medium"]
        ),
        "heavy_common_confirmed_rate": lambda item: float(
            item["common_confirmed_rate_by_level"]["heavy"]
        ),
    }
    best_by_metric: dict[str, dict[str, Any]] = {}
    for metric_name, metric_value in metric_accessors.items():
        best_candidate = max(candidates, key=metric_value)
        best_by_metric[metric_name] = {
            "value": metric_value(best_candidate),
            "candidate_index": best_candidate["candidate_index"],
            "tracker_fingerprint": best_candidate["tracker_fingerprint"],
            "candidate_median_track_purity": best_candidate[
                "median_track_purity"
            ],
        }

    episodes = _sequence(manifest.get("episodes"), "raw calibration episodes")
    if not episodes:
        raise ValueError("raw calibration manifest contains no episodes")
    unique_evidence: set[tuple[int, str]] = set()
    for item in episodes:
        episode = _mapping(item, "calibration episode")
        seed = _integer(episode.get("seed"), "calibration episode seed")
        split = str(episode.get("split") or "")
        if split not in {"train", "validation"}:
            raise ValueError("raw calibration manifest contains an invalid split")
        unique_evidence.add((seed, split))
    if len(unique_evidence) != len(episodes):
        raise ValueError("raw calibration manifest repeats an episode")

    return {
        "target_count": target_count,
        "status": "tracker_calibration_failed",
        "status_cn": STATUS_LABELS_CN["tracker_calibration_failed"],
        "protocol_fingerprint": protocol_fingerprint,
        "preflight_common_tracking": _preflight_rates(preflight),
        "calibration_episode_count": len(episodes),
        "candidate_count": candidate_count,
        "accepted_candidate_count": accepted_candidate_count,
        "failure_reason_codes": list(failure_reasons),
        "failure_reasons_cn": [_reason_cn(reason) for reason in failure_reasons],
        "thresholds": thresholds,
        "checks": {name: bool(checks_raw[name]) for name in expected_checks},
        "selected_tracker_fingerprint": selected_fingerprint,
        "selected_validation": {
            "median_track_purity": selected_purity,
            "mean_fragmentation": selected_fragmentation,
            "false_reactivation_rate": selected_candidate[
                "false_reactivation_rate"
            ],
            "sweep_runtime_p95_ms": selected_candidate["sweep_runtime_p95_ms"],
            "common_confirmed_rate_by_level": selected_rates,
        },
        "best_by_metric": best_by_metric,
        "candidates": candidates,
        "truth_boundary": {
            "online_truth_used": False,
            "test_data_accessed_during_calibration": False,
            "heldout_test_started": False,
        },
    }


def _empty_metrics() -> dict[str, None]:
    return {
        "precision": None,
        "recall": None,
        "f1": None,
        "latency_p95_ms": None,
        "conditional_precision": None,
        "candidate_true_retention_rate": None,
        "identity_contract_violations": None,
        "false_association_count": None,
    }


def _load_tier(target_count: int, paths: Mapping[str, Path]) -> dict[str, Any]:
    metrics = _read_json(paths["comparison_metrics"])
    promotion = _read_json(paths["promotion_manifest"])
    preflight = _read_json(paths["preflight_summary"])
    tracker = _read_json(paths["shared_tracker"])
    frozen = _read_json(paths["all_routes_frozen"])

    protocol = _mapping(metrics.get("protocol"), "comparison protocol")
    if _integer(protocol.get("target_count"), "protocol target_count") != target_count:
        raise ValueError(f"targets_{target_count:03d} protocol target_count mismatch")
    protocol_fingerprint = str(metrics.get("protocol_fingerprint") or "")
    if not protocol_fingerprint:
        raise ValueError("comparison metrics omit protocol fingerprint")
    for source_name, source, field in (
        ("preflight", preflight, "protocol_fingerprint"),
        ("freeze marker", frozen, "protocol_fingerprint"),
        ("promotion", promotion, "source_protocol_fingerprint"),
    ):
        if str(source.get(field) or "") != protocol_fingerprint:
            raise ValueError(f"{source_name} protocol fingerprint mismatch")

    if metrics.get("truth_used_online") is not False:
        raise ValueError("comparison metrics do not prove online truth isolation")
    for source_name, source in (
        ("preflight", preflight),
        ("shared tracker", tracker),
        ("freeze marker", frozen),
    ):
        if source.get("test_data_accessed") is not False:
            raise ValueError(f"{source_name} does not prove test-data isolation")

    _check_optional_hash(
        metrics,
        "freeze_marker_sha256",
        paths["all_routes_frozen"],
        "comparison freeze marker",
    )
    _check_optional_hash(
        frozen,
        "tracker_freeze_sha256",
        paths["shared_tracker"],
        "shared tracker freeze",
    )
    _check_optional_hash(
        promotion,
        "metrics_sha256",
        paths["comparison_metrics"],
        "promotion metrics",
    )

    active_routes = _routes(metrics.get("active_routes"), "metrics active_routes")
    if active_routes != _routes(frozen.get("active_routes"), "freeze active_routes"):
        raise ValueError("metrics and freeze marker active routes differ")
    if active_routes != _routes(
        promotion.get("active_routes"), "promotion active_routes"
    ):
        raise ValueError("metrics and promotion active routes differ")

    validation_eliminated_raw = _mapping(
        frozen.get("eliminated_routes", {}), "validation eliminated routes"
    )
    validation_eliminated: dict[str, Mapping[str, Any]] = {}
    for route, raw in validation_eliminated_raw.items():
        if route not in ROUTE_ORDER or route in active_routes:
            raise ValueError("freeze marker contains an invalid validation elimination")
        item = _mapping(raw, f"validation elimination {route}")
        if item.get("status") not in {
            "eliminated_on_validation",
            "eliminated_on_main_validation_gate",
        }:
            raise ValueError("validation elimination has an invalid status")
        validation_eliminated[route] = item

    requested_routes = _routes(frozen.get("requested_routes"), "requested_routes")
    if set(requested_routes) != set(active_routes).union(validation_eliminated):
        raise ValueError("requested routes are not partitioned by freeze outcome")

    frozen_routes = _mapping(frozen.get("routes"), "frozen active routes")
    if any(route not in frozen_routes for route in active_routes):
        raise ValueError("active route lacks validation acceptance")

    aggregate = _mapping(
        _mapping(metrics.get("aggregate"), "comparison aggregate").get("routes"),
        "route aggregate",
    )
    rows = _sequence(metrics.get("rows"), "comparison rows")
    if not rows:
        raise ValueError("comparison metrics contain no held-out rows")
    shared_checks = metrics.get("shared_input_checks")
    if shared_checks is not None and any(
        _mapping(item, "shared input check").get("all_equal") is not True
        for item in _sequence(shared_checks, "shared input checks")
    ):
        raise ValueError("routes did not consume identical held-out inputs")

    promoted_routes = _routes(
        promotion.get("eligible_routes", promotion.get("promoted_routes")),
        "eligible_routes",
        allow_empty=True,
    )
    compatibility_routes = _routes(
        promotion.get("promoted_routes"), "promoted_routes", allow_empty=True
    )
    if promoted_routes != compatibility_routes:
        raise ValueError("eligible and promoted route aliases differ")
    preferred_route = promotion.get("preferred_route")
    if preferred_route is not None and str(preferred_route) not in promoted_routes:
        raise ValueError("preferred route is not eligible")
    if any(route not in active_routes for route in promoted_routes):
        raise ValueError("promotion resurrects a non-active route")
    heldout_eliminated = _mapping(
        promotion.get("eliminated_routes", {}), "held-out eliminated routes"
    )
    if set(promoted_routes).intersection(heldout_eliminated):
        raise ValueError("route is both promoted and eliminated on held-out data")
    if set(active_routes) != set(promoted_routes).union(heldout_eliminated):
        raise ValueError("held-out decisions do not partition active routes")
    if bool(promotion.get("promotion_allowed")) != bool(promoted_routes):
        raise ValueError("promotion_allowed disagrees with promoted routes")
    if _integer(promotion.get("source_target_count"), "promotion source target") != target_count:
        raise ValueError("promotion source target_count mismatch")
    expected_next = (
        None
        if target_count == SUPPORTED_TARGET_COUNTS[-1]
        else SUPPORTED_TARGET_COUNTS[SUPPORTED_TARGET_COUNTS.index(target_count) + 1]
    )
    if promotion.get("next_target_count") != expected_next:
        raise ValueError("promotion next target_count mismatch")

    decisions = _mapping(promotion.get("decisions"), "promotion decisions")
    if set(decisions) != set(active_routes):
        raise ValueError("promotion decisions do not match active routes")
    if promotion.get("reserved_test_used_for_parameter_selection") is not False:
        raise ValueError("held-out data may not be used for parameter selection")
    if promotion.get("reserved_test_used_for_single_promotion_decision") is not True:
        raise ValueError("promotion does not identify the one-shot held-out decision")

    tracker_rates, tracker_mean, tracker_worst = _mean_common_tracking(tracker)
    preflight_rates = _preflight_rates(preflight)
    route_records: list[dict[str, Any]] = []

    # Validation eliminations are represented only by the top-level marker facts.
    # Their failure_evidence path is deliberately never opened.
    for route in requested_routes:
        if route in validation_eliminated:
            reason = str(
                validation_eliminated[route].get("reason_code")
                or "validation_rejected"
            )
            route_records.append(
                {
                    "route_name": route,
                    "route_label_cn": ROUTE_LABELS_CN[route],
                    "status": "eliminated_on_validation",
                    "status_cn": STATUS_LABELS_CN["eliminated_on_validation"],
                    "is_preferred": False,
                    "validation_f1": None,
                    **_empty_metrics(),
                    "failure_reason_codes": [reason],
                    "failure_reasons_cn": [_reason_cn(reason)],
                }
            )
            continue

        if route not in aggregate:
            raise ValueError(f"active route {route} lacks aggregate metrics")
        route_rows = [
            _mapping(row, "comparison row")
            for row in rows
            if _mapping(row, "comparison row").get("route_name") == route
        ]
        if not route_rows:
            raise ValueError(f"active route {route} lacks held-out rows")
        item = _mapping(aggregate[route], f"aggregate {route}")
        decision = _mapping(decisions[route], f"promotion decision {route}")
        decision_promoted = decision.get(
            "eligible", decision.get("promoted")
        ) is True
        if decision_promoted != (route in promoted_routes):
            raise ValueError(f"promotion decision disagrees for {route}")
        if route in heldout_eliminated:
            heldout_reasons = tuple(
                str(value)
                for value in _sequence(
                    heldout_eliminated[route], f"held-out reasons {route}"
                )
            )
            decision_reasons = tuple(
                str(value)
                for value in _sequence(
                    decision.get("reasons", ()), f"decision reasons {route}"
                )
            )
            if heldout_reasons != decision_reasons or not heldout_reasons:
                raise ValueError(f"held-out failure reasons disagree for {route}")
            status = "final_tier_failed" if target_count == 100 else "eliminated_on_heldout"
            reasons = list(heldout_reasons)
        else:
            status = "final_tier_passed" if target_count == 100 else "promoted"
            reasons = []

        validation = _mapping(
            _mapping(frozen_routes[route], f"freeze route {route}").get(
                "validation_acceptance"
            ),
            f"validation acceptance {route}",
        )
        if validation.get("accepted") is not True:
            raise ValueError(f"active route {route} was not accepted on validation")
        route_records.append(
            {
                "route_name": route,
                "route_label_cn": ROUTE_LABELS_CN[route],
                "status": status,
                "status_cn": STATUS_LABELS_CN[status],
                "is_preferred": route == preferred_route,
                "validation_f1": _number(
                    validation.get("validation_f1"), f"validation F1 {route}"
                ),
                "precision": _number(item.get("macro_precision"), f"precision {route}"),
                "recall": _number(item.get("macro_recall"), f"recall {route}"),
                "f1": _number(item.get("macro_f1"), f"F1 {route}"),
                "latency_p95_ms": _number(
                    item.get("latency_p95_ms"), f"P95 latency {route}"
                ),
                "conditional_precision": _number(
                    decision.get("conditional_precision"),
                    f"conditional precision {route}",
                ),
                "candidate_true_retention_rate": _number(
                    item.get("mean_candidate_true_retention_rate"),
                    f"candidate retention {route}",
                ),
                "identity_contract_violations": _integer(
                    decision.get("identity_contract_violations"),
                    f"identity violations {route}",
                ),
                "false_association_count": _integer(
                    item.get("false_association_count"),
                    f"false associations {route}",
                ),
                "failure_reason_codes": reasons,
                "failure_reasons_cn": [_reason_cn(reason) for reason in reasons],
            }
        )

    return {
        "target_count": target_count,
        "protocol_fingerprint": protocol_fingerprint,
        "requested_routes": list(requested_routes),
        "active_routes": list(active_routes),
        "promoted_routes": list(promoted_routes),
        "eligible_routes": list(promoted_routes),
        "preferred_route": preferred_route,
        "next_target_count": expected_next,
        "promotion_allowed": bool(promoted_routes),
        "common_tracking": {
            "by_corruption_level": tracker_rates,
            "mean": tracker_mean,
            "worst": tracker_worst,
        },
        "preflight_common_tracking": preflight_rates,
        "routes": route_records,
        "truth_boundary": {
            "online_truth_used": False,
            "test_data_accessed_during_freeze": False,
            "heldout_used_for_parameter_selection": False,
        },
    }


def collect_scale_funnel(funnel_root: str | Path) -> dict[str, Any]:
    """Load and validate a contiguous prefix of sealed scale tiers."""

    root = Path(funnel_root).resolve()
    (
        completed,
        preflight_only,
        tracker_calibration_failed,
        paths_by_tier,
    ) = _discover_tiers(root)
    scales = [_load_tier(count, paths_by_tier[count]) for count in completed]
    calibration_failure = (
        None
        if not tracker_calibration_failed
        else _load_tracker_calibration_failure(
            tracker_calibration_failed[0],
            paths_by_tier[tracker_calibration_failed[0]],
        )
    )

    for previous, current in zip(scales, scales[1:]):
        if set(previous["promoted_routes"]) != set(current["requested_routes"]):
            raise ValueError(
                "next tier requested routes differ from prior promotion manifest"
            )
    highest = scales[-1]
    if (preflight_only or calibration_failure) and not highest["promoted_routes"]:
        raise ValueError("next tier started after all routes were eliminated")
    if calibration_failure is not None:
        expected_count = highest["next_target_count"]
        if calibration_failure["target_count"] != expected_count:
            raise ValueError("tracker calibration failure is not the promoted next tier")

    if calibration_failure is not None:
        funnel_state = "tracker_calibration_failed"
    elif completed[-1] == SUPPORTED_TARGET_COUNTS[-1]:
        funnel_state = "final_tier_completed"
    elif not highest["promoted_routes"]:
        funnel_state = "stopped_no_survivor"
    elif preflight_only:
        funnel_state = "next_tier_preflight_only"
    else:
        funnel_state = "next_tier_not_started"

    return {
        "schema_version": "dual-optical-scale-funnel-summary-v1",
        "source_root": str(root),
        "completed_target_counts": list(completed),
        "preflight_only_target_counts": list(preflight_only),
        "tracker_calibration_failed_target_counts": list(
            tracker_calibration_failed
        ),
        "highest_completed_target_count": completed[-1],
        "final_tier_reached": completed[-1] == SUPPORTED_TARGET_COUNTS[-1],
        "funnel_state": funnel_state,
        "scales": scales,
        "tracker_calibration_failure": calibration_failure,
        "evidence_boundary": {
            "online_input": "AirSim simGetDetections metadata",
            "offline_truth": "used only after online publication for scoring",
            "fielded_system_claim": False,
        },
    }


def _csv_row(scale: Mapping[str, Any], route: Mapping[str, Any]) -> dict[str, Any]:
    common = _mapping(scale["common_tracking"], "common tracking")
    preflight = _mapping(scale["preflight_common_tracking"], "preflight tracking")
    row = {
        "target_count": scale["target_count"],
        **{field: route.get(field) for field in CSV_FIELDS if field in route},
        "common_confirmed_rate_mean": common["mean"],
        "common_confirmed_rate_worst": common["worst"],
        "preflight_ideal_common_confirmed_rate": preflight["ideal"],
        "preflight_pose_error_common_confirmed_rate": preflight["pose_error"],
        "preflight_full_interference_common_confirmed_rate": preflight[
            "full_interference"
        ],
        "failure_reason_codes": ";".join(route["failure_reason_codes"]),
        "failure_reasons_cn": "；".join(route["failure_reasons_cn"]),
    }
    return {field: "" if row.get(field) is None else row.get(field) for field in CSV_FIELDS}


def _tracker_failure_csv_row(failure: Mapping[str, Any]) -> dict[str, Any]:
    preflight = _mapping(failure["preflight_common_tracking"], "preflight tracking")
    selected = _mapping(failure["selected_validation"], "selected validation")
    levels = _mapping(
        selected["common_confirmed_rate_by_level"], "selected validation levels"
    )
    row = {
        "target_count": failure["target_count"],
        "route_name": "shared_tracker",
        "route_label_cn": "共享跟踪器",
        "status": failure["status"],
        "status_cn": failure["status_cn"],
        "validation_f1": None,
        "precision": None,
        "recall": None,
        "f1": None,
        "latency_p95_ms": None,
        "conditional_precision": None,
        "candidate_true_retention_rate": None,
        "common_confirmed_rate_mean": fmean(float(value) for value in levels.values()),
        "common_confirmed_rate_worst": min(float(value) for value in levels.values()),
        "preflight_ideal_common_confirmed_rate": preflight["ideal"],
        "preflight_pose_error_common_confirmed_rate": preflight["pose_error"],
        "preflight_full_interference_common_confirmed_rate": preflight[
            "full_interference"
        ],
        "identity_contract_violations": None,
        "false_association_count": None,
        "tracker_candidate_count": failure["candidate_count"],
        "tracker_accepted_candidate_count": failure["accepted_candidate_count"],
        "failure_reason_codes": ";".join(failure["failure_reason_codes"]),
        "failure_reasons_cn": "；".join(failure["failure_reasons_cn"]),
    }
    return {field: "" if row.get(field) is None else row.get(field) for field in CSV_FIELDS}


def _tracker_candidate_csv_rows(
    failure: Mapping[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for candidate in failure["candidates"]:
        levels = candidate["common_confirmed_rate_by_level"]
        rows.append(
            {
                "target_count": failure["target_count"],
                "candidate_index": candidate["candidate_index"],
                "selected": candidate["selected"],
                "tracker_fingerprint": candidate["tracker_fingerprint"],
                "accepted": candidate["accepted"],
                "median_track_purity": candidate["median_track_purity"],
                "clean_common_confirmed_rate": levels["clean"],
                "light_common_confirmed_rate": levels["light"],
                "medium_common_confirmed_rate": levels["medium"],
                "heavy_common_confirmed_rate": levels["heavy"],
                "mean_fragmentation": candidate["mean_fragmentation"],
                "false_reactivation_rate": candidate["false_reactivation_rate"],
                "baseline_false_reactivation_rate": candidate[
                    "baseline_false_reactivation_rate"
                ],
                "sweep_runtime_p95_ms": candidate["sweep_runtime_p95_ms"],
                "failed_check_codes": ";".join(candidate["failed_check_codes"]),
                "failed_checks_cn": "；".join(candidate["failed_checks_cn"]),
            }
        )
    return rows


def _write_csv(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    fields: Sequence[str] = CSV_FIELDS,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _metric_points(
    summary: Mapping[str, Any], route_name: str, metric: str
) -> tuple[list[int], list[float]]:
    x: list[int] = []
    y: list[float] = []
    for scale in summary["scales"]:
        for route in scale["routes"]:
            value = route.get(metric)
            if route["route_name"] == route_name and value is not None:
                x.append(int(scale["target_count"]))
                y.append(float(value))
    return x, y


def _write_performance_figure(summary: Mapping[str, Any], path: Path) -> None:
    figure, axes = plt.subplots(1, 2, figsize=(13.2, 4.8))
    metric_styles = {
        "precision": ("Precision", "-"),
        "recall": ("Recall", "--"),
        "f1": ("F1", ":"),
    }
    for route in ROUTE_ORDER:
        for metric, (label, style) in metric_styles.items():
            x, y = _metric_points(summary, route, metric)
            if x:
                axes[0].plot(
                    x,
                    y,
                    marker="o",
                    linestyle=style,
                    color=ROUTE_COLORS[route],
                    label=f"{ROUTE_LABELS_EN[route]} {label}",
                )
        x, y = _metric_points(summary, route, "latency_p95_ms")
        if x:
            axes[1].plot(
                x,
                y,
                marker="o",
                color=ROUTE_COLORS[route],
                label=ROUTE_LABELS_EN[route],
            )
    ticks = summary["completed_target_counts"]
    axes[0].set(
        title="Held-out association performance",
        xlabel="Target count",
        ylabel="Rate",
        xticks=ticks,
        ylim=(0.0, 1.0),
    )
    axes[1].axhline(1000.0, color="#c62828", linestyle="--", linewidth=1.2)
    axes[1].set(
        title="Held-out P95 latency",
        xlabel="Target count",
        ylabel="Milliseconds",
        xticks=ticks,
    )
    for axis in axes:
        axis.grid(alpha=0.25)
        axis.legend(fontsize=7)
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180)
    plt.close(figure)


def _write_tracking_figure(summary: Mapping[str, Any], path: Path) -> None:
    figure, axes = plt.subplots(1, 2, figsize=(13.2, 4.8))
    tracking_records = [
        {
            "target_count": int(scale["target_count"]),
            "preflight_common_tracking": scale["preflight_common_tracking"],
        }
        for scale in summary["scales"]
    ]
    calibration_failure = summary.get("tracker_calibration_failure")
    if calibration_failure is not None:
        tracking_records.append(
            {
                "target_count": int(calibration_failure["target_count"]),
                "preflight_common_tracking": calibration_failure[
                    "preflight_common_tracking"
                ],
            }
        )
    x = [record["target_count"] for record in tracking_records]
    scenario_labels = {
        "ideal": "Ideal",
        "pose_error": "Pose error",
        "full_interference": "Full interference",
    }
    scenario_styles = {
        "ideal": "-",
        "pose_error": "--",
        "full_interference": ":",
    }
    for scenario, label in scenario_labels.items():
        axes[0].plot(
            x,
            [
                float(record["preflight_common_tracking"][scenario])
                for record in tracking_records
            ],
            marker="o",
            linestyle=scenario_styles[scenario],
            label=label,
        )
    for route in ROUTE_ORDER:
        route_x, route_y = _metric_points(
            summary, route, "candidate_true_retention_rate"
        )
        if route_x:
            axes[1].plot(
                route_x,
                route_y,
                marker="o",
                color=ROUTE_COLORS[route],
                label=ROUTE_LABELS_EN[route],
            )
    axes[0].set(
        title="Shared confirmed-track rate",
        xlabel="Target count",
        ylabel="Rate",
        xticks=x,
        ylim=(0.0, 1.0),
    )
    axes[1].set(
        title="True-edge retention in candidate graph",
        xlabel="Target count",
        ylabel="Rate",
        xticks=x,
        ylim=(0.0, 1.0),
    )
    for axis in axes:
        axis.grid(alpha=0.25)
        axis.legend(fontsize=8)
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180)
    plt.close(figure)


def _fmt(value: Any, digits: int = 4) -> str:
    return "无数据" if value is None else f"{float(value):.{digits}f}"


def _state_conclusion(summary: Mapping[str, Any]) -> str:
    state = summary["funnel_state"]
    highest = summary["highest_completed_target_count"]
    if state == "tracker_calibration_failed":
        failure = summary["tracker_calibration_failure"]
        return (
            f"{failure['target_count']}目标已完成正式标定，但共享跟踪器没有通过"
            "验证门槛，漏斗在生成冻结配置和保留集测试前终止。"
        )
    if state == "final_tier_completed":
        return "100目标最终档已经完成，路线结果按最终档通过或未通过列示。"
    if state == "stopped_no_survivor":
        return f"漏斗在{highest}目标停止，保留集判定后没有路线可以继续晋级。"
    if state == "next_tier_preflight_only":
        next_count = summary["preflight_only_target_counts"][0]
        return (
            f"{highest}目标保留集判定已经完成；{next_count}目标只有预检证据，"
            "尚未形成冻结、保留集结果和最终结论。"
        )
    return f"{highest}目标保留集判定已经完成，下一规模尚未开始。"


def _write_markdown(summary: Mapping[str, Any], path: Path) -> None:
    route_rows: list[str] = []
    tracking_rows: list[str] = []
    decision_rows: list[str] = []
    for scale in summary["scales"]:
        target_count = scale["target_count"]
        common = scale["common_tracking"]
        preflight = scale["preflight_common_tracking"]
        tracking_rows.append(
            "| {count} | {ideal} | {pose} | {full} | {mean} | {worst} |".format(
                count=target_count,
                ideal=_fmt(preflight["ideal"]),
                pose=_fmt(preflight["pose_error"]),
                full=_fmt(preflight["full_interference"]),
                mean=_fmt(common["mean"]),
                worst=_fmt(common["worst"]),
            )
        )
        for route in scale["routes"]:
            reasons = "；".join(route["failure_reasons_cn"]) or "无"
            route_rows.append(
                "| {count} | {route} | {status} | {precision} | {recall} | {f1} | "
                "{latency} | {conditional} | {retention} | {identity} | {failures} |".format(
                    count=target_count,
                    route=route["route_label_cn"],
                    status=route["status_cn"],
                    precision=_fmt(route["precision"]),
                    recall=_fmt(route["recall"]),
                    f1=_fmt(route["f1"]),
                    latency=_fmt(route["latency_p95_ms"], 2),
                    conditional=_fmt(route["conditional_precision"]),
                    retention=_fmt(route["candidate_true_retention_rate"]),
                    identity=(
                        "无数据"
                        if route["identity_contract_violations"] is None
                        else str(route["identity_contract_violations"])
                    ),
                    failures=route["false_association_count"]
                    if route["false_association_count"] is not None
                    else "无数据",
                )
            )
            decision_rows.append(
                f"| {target_count} | {route['route_label_cn']} | "
                f"{route['status_cn']} | {reasons} |"
            )

    calibration_failure = summary.get("tracker_calibration_failure")
    calibration_section = ""
    if calibration_failure is not None:
        failure = calibration_failure
        selected = failure["selected_validation"]
        levels = selected["common_confirmed_rate_by_level"]
        best_by_metric = failure["best_by_metric"]
        thresholds = failure["thresholds"]
        checks = failure["checks"]
        tracking_rows.append(
            "| {count} | {ideal} | {pose} | {full} | {mean} | {worst} |".format(
                count=failure["target_count"],
                ideal=_fmt(failure["preflight_common_tracking"]["ideal"]),
                pose=_fmt(failure["preflight_common_tracking"]["pose_error"]),
                full=_fmt(
                    failure["preflight_common_tracking"]["full_interference"]
                ),
                mean=_fmt(fmean(float(value) for value in levels.values())),
                worst=_fmt(min(float(value) for value in levels.values())),
            )
        )
        failure_reasons = "；".join(failure["failure_reasons_cn"])
        decision_rows.append(
            f"| {failure['target_count']} | 共享跟踪器 | "
            f"{failure['status_cn']} | {failure_reasons} |"
        )
        threshold_rows = []
        metric_labels = {
            "median_track_purity": "航迹纯度中位数",
            "light_common_confirmed_rate": "轻干扰共同成轨率",
            "medium_common_confirmed_rate": "中干扰共同成轨率",
            "heavy_common_confirmed_rate": "重干扰共同成轨率",
        }
        actual_values = {
            "median_track_purity": selected["median_track_purity"],
            "light_common_confirmed_rate": levels["light"],
            "medium_common_confirmed_rate": levels["medium"],
            "heavy_common_confirmed_rate": levels["heavy"],
        }
        for name, label in metric_labels.items():
            threshold_rows.append(
                f"| {label} | {_fmt(actual_values[name])} | "
                f"{_fmt(best_by_metric[name]['value'])} | "
                f"{_fmt(thresholds[name])} | "
                f"{'通过' if checks[name] else '未通过'} |"
            )
        medium_best = best_by_metric["medium_common_confirmed_rate"]
        continuity_gate_text = ""
        if "false_reactivation_rate_absolute" in checks:
            continuity_gate_text = (
                f"选定候选的错误重激活率为"
                f"{_fmt(selected['false_reactivation_rate'])}，单圈跟踪95%分位"
                f"时延为{_fmt(selected['sweep_runtime_p95_ms'], 2)}毫秒。"
                "同时检查错误重激活不高于基线、航迹碎片不增加和单圈时延"
                "不超过250毫秒。"
            )
        calibration_section = f"""
## 6. 正式标定终止

{failure['target_count']}目标共使用{failure['calibration_episode_count']}个训练和验证回合，评估{failure['candidate_count']}组共享跟踪器候选。全部候选均未通过全部门槛，通过候选为{failure['accepted_candidate_count']}组，因此状态记为“{failure['status_cn']}”。中干扰共同成轨率的单项最高值为{_fmt(medium_best['value'])}，对应候选的航迹纯度为{_fmt(medium_best['candidate_median_track_purity'])}，门槛为{_fmt(thresholds['medium_common_confirmed_rate'])}。{continuity_gate_text}本阶段没有生成共享跟踪器冻结文件、路线冻结文件或保留集指标。

| 正式验证指标 | 标定选定候选值 | 全部候选按该指标最高值 | 门槛 | 选定候选结果 |
| --- | ---: | ---: | ---: | --- |
{chr(10).join(threshold_rows)}

失败项为{failure_reasons}。“全部候选按该指标最高值”逐项独立计算，可能来自不同候选，不能拼成一套通过方案。{failure['candidate_count']}组候选的逐项汇总写入 `tracker_calibration_candidates.csv`，没有读取或要求不存在的路线测试指标。
"""

    pending_text = "无"
    if calibration_failure is not None:
        pending_text = (
            f"{calibration_failure['target_count']}目标（共享跟踪器正式标定失败）"
        )
    elif summary["preflight_only_target_counts"]:
        pending_text = "、".join(
            f"{count}目标（仅预检）"
            for count in summary["preflight_only_target_counts"]
        )
    text = f"""# 双光电目标规模漏斗汇总

## 1. 结论

本报告纳入的完整规模为{('、'.join(str(value) for value in summary['completed_target_counts']))}目标。{_state_conclusion(summary)}

完整结果按“验证筛选、保留集判定、逐级晋级、100目标最终档”解释。验证淘汰路线没有保留集指标；报告只引用冻结标记中的状态和原因。当前待完成档为{pending_text}。

## 2. 证据范围

在线输入来自AirSim `simGetDetections` 检测元数据。在线跟踪和配准不读取Actor名称或真实身份。目标真实身份只在结果发布后用于离线计算精确率、召回率、错配数和候选真边保留率。

这些结果属于AirSim仿真证据，用于比较算法在统一输入下的性能和计算时延。结果不能直接代表实装光电设备的探测距离、识别率或现场配准能力。

## 3. 成轨条件

| 目标数 | 理想预检 | 姿态误差预检 | 完整干扰预检 | 冻结数据平均共同成轨率 | 冻结数据最差共同成轨率 |
| ---: | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(tracking_rows)}

预检共同成轨率反映两部光电在同一场景中形成可比较局部航迹的比例。候选真边保留率反映候选筛选后仍保留正确跨站关系的比例，两项指标用途不同。

## 4. 路线结果

| 目标数 | 路线 | 状态 | 精确率 | 召回率 | F1 | P95时延/毫秒 | 条件精确率 | 候选真边保留率 | 身份违规 | 错配数 |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(route_rows)}

条件精确率按已发布关系计算。身份违规汇总身份重复、一对一约束破坏和在线真值泄漏；数值为0表示本轮记录中未发生这些违规，不表示实装条件下风险已经消失。

## 5. 淘汰与晋级

| 目标数 | 路线 | 判定 | 原因 |
| ---: | --- | --- | --- |
{chr(10).join(decision_rows)}

验证淘汰发生在参数冻结前。保留集淘汰发生在冻结参数的一次性测试后。晋级只表示该路线可以进入下一目标规模；只有完成100目标测试后才记为最终档结果。

{calibration_section}

## 7. 趋势图

![性能与时延](figures/01_performance_latency_trend.png)

图1给出保留集精确率、召回率、F1和P95时延。被淘汰路线在后续规模没有数据点。

![成轨与候选保留](figures/02_tracking_candidate_trend.png)

图2给出三类预检条件下的共同成轨率，以及各存活路线的候选真边保留率。

## 8. 输出文件

- `scale_funnel_summary.json`：全部规模、路线状态和证据边界。
- `scale_route_metrics.csv`：所有已完成规模的逐路线结果。
- `targets_NNN_metrics.csv`：对应规模的独立结果表。
- `tracker_calibration_candidates.csv`：正式标定失败时的13组候选汇总。
- `figures/01_performance_latency_trend.png`：性能与时延趋势。
- `figures/02_tracking_candidate_trend.png`：成轨与候选保留趋势。
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def generate_scale_funnel_report(
    funnel_root: str | Path, output_dir: str | Path
) -> dict[str, Any]:
    """Generate CSV, JSON, PNG, and Chinese Markdown artifacts."""

    summary = collect_scale_funnel(funnel_root)
    destination = Path(output_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    all_rows: list[dict[str, Any]] = []
    tier_csv_paths: list[Path] = []
    for scale in summary["scales"]:
        rows = [_csv_row(scale, route) for route in scale["routes"]]
        all_rows.extend(rows)
        path = destination / f"targets_{int(scale['target_count']):03d}_metrics.csv"
        _write_csv(path, rows)
        tier_csv_paths.append(path)
    tracker_candidate_csv: Path | None = None
    calibration_failure = summary.get("tracker_calibration_failure")
    if calibration_failure is not None:
        failure_row = _tracker_failure_csv_row(calibration_failure)
        all_rows.append(failure_row)
        path = destination / (
            f"targets_{int(calibration_failure['target_count']):03d}_metrics.csv"
        )
        _write_csv(path, [failure_row])
        tier_csv_paths.append(path)
        tracker_candidate_csv = destination / "tracker_calibration_candidates.csv"
        _write_csv(
            tracker_candidate_csv,
            _tracker_candidate_csv_rows(calibration_failure),
            TRACKER_CANDIDATE_CSV_FIELDS,
        )

    combined_csv = destination / "scale_route_metrics.csv"
    summary_json = destination / "scale_funnel_summary.json"
    performance_figure = destination / "figures/01_performance_latency_trend.png"
    tracking_figure = destination / "figures/02_tracking_candidate_trend.png"
    report = destination / "DUAL_OPTICAL_SCALE_FUNNEL_SUMMARY_CN.md"
    _write_csv(combined_csv, all_rows)
    _write_json(summary_json, summary)
    _write_performance_figure(summary, performance_figure)
    _write_tracking_figure(summary, tracking_figure)
    _write_markdown(summary, report)
    return {
        "summary_json": summary_json,
        "combined_csv": combined_csv,
        "tier_csvs": tuple(tier_csv_paths),
        "tracker_candidate_csv": tracker_candidate_csv,
        "performance_figure": performance_figure,
        "tracking_figure": tracking_figure,
        "report": report,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate the dual-optical target-scale funnel report."
    )
    default_root = Path(__file__).resolve().parent / "outputs/scale_funnel_v4"
    parser.add_argument(
        "--funnel-root",
        type=Path,
        default=default_root,
        help="Root containing targets_020/040/060/100.",
    )
    parser.add_argument(
        "--output-dir", type=Path, required=True, help="Report output directory."
    )
    args = parser.parse_args(argv)
    artifacts = generate_scale_funnel_report(args.funnel_root, args.output_dir)
    printable = {
        key: [str(item) for item in value] if isinstance(value, tuple) else str(value)
        for key, value in artifacts.items()
    }
    print(json.dumps(printable, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "collect_scale_funnel",
    "generate_scale_funnel_report",
    "main",
]
