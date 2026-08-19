"""Aggregate candidate-gate and confirmation-policy ablation results.

The reporter consumes per-revolution JSON/CSV records and a variant manifest.
Validation records are the only records used for strategy selection.  Test
records are reported as diagnostic confirmation because the held-out seeds in
this experiment have already been inspected.

Minimal manifest example::

    {
      "baseline_variant_id": "baseline",
      "variants": [
        {"variant_id": "baseline", "label_cn": "基线", "selection_rule": "none"},
        {"variant_id": "gate_10s", "label_cn": "放宽初筛", "selection_rule": "candidate"},
        {
          "variant_id": "early_2of2",
          "label_cn": "提前重复确认",
          "selection_rule": "confirmation"
        }
      ],
      "inputs": [
        {"path": "validation.csv", "split": "validation"},
        {"path": "test.json", "split": "test"}
      ]
    }

Rows may carry their own ``split`` field.  When they do not, the manifest input
entry supplies it.  JSON inputs may be a row list, a single row, or an object
with a ``rows``/``records``/``data`` list.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
from statistics import fmean
from typing import Any, Iterable, Mapping, Sequence

import matplotlib

matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
from matplotlib import font_manager


def _configure_plot_font() -> None:
    candidates = (
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Medium.ttc"),
        Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
        Path("/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf"),
    )
    for path in candidates:
        if not path.is_file():
            continue
        family = font_manager.FontProperties(fname=str(path)).get_name()
        matplotlib.rcParams["font.family"] = [family, "DejaVu Sans"]
        matplotlib.rcParams["axes.unicode_minus"] = False
        return


_configure_plot_font()


SCHEMA_VERSION = "dual-optical-gate-confirmation-report-v1"
LEVELS = ("clean", "light")
MAIN_TARGET_COUNT = 20
OFFLINE_REVIEW_COUNTS = (40, 60)
SELECTION_RULES = {"none", "candidate", "confirmation"}
SCALE_PREFERRED_VARIANTS = (
    "baseline_strict",
    "baseline_early",
    "baseline_graded_p08_m01",
)

REQUIRED_ROW_FIELDS = (
    "variant_id",
    "target_count",
    "seed",
    "level",
    "revolution",
    "match_count",
    "correct_count",
    "false_count",
    "unique_correct_targets",
    "candidate_opportunities",
    "candidate_true_retained",
    "candidate_edge_count",
    "candidate_build_ms",
    "inference_ms",
    "assignment_ms",
    "end_to_end_ms",
    "first_confirmation_s",
    "relation_switch_count",
    "one_to_one_violations",
    "gpu_peak_memory_mb",
)

ROW_ALIASES = {
    "level": ("corruption_level",),
    "revolution": ("revolution_index",),
    "correct_count": ("correct_match_count",),
    "false_count": ("false_association_count",),
    "candidate_opportunities": ("candidate_true_opportunity_count",),
    "candidate_true_retained": ("candidate_true_retained_count",),
    "split": ("dataset_split", "phase"),
}

PER_SEED_FIELDS = (
    "variant_id",
    "variant_label_cn",
    "selection_rule",
    "diagnostic_only",
    "target_count",
    "split",
    "level",
    "seed",
    "revolution_count",
    "match_count",
    "correct_count",
    "false_count",
    "association_precision",
    "macro_association_precision",
    "unique_correct_targets",
    "target_opportunities",
    "coverage",
    "macro_coverage",
    "candidate_opportunities",
    "candidate_true_retained",
    "candidate_true_retention_rate",
    "macro_candidate_true_retention_rate",
    "candidate_edge_count",
    "mean_candidate_edge_count",
    "first_confirmation_s",
    "no_output_revolutions",
    "no_output_rate",
    "relation_switch_count",
    "relation_switch_opportunities",
    "relation_switch_rate",
    "one_to_one_violations",
    "candidate_build_p95_ms",
    "inference_p95_ms",
    "assignment_p95_ms",
    "end_to_end_p95_ms",
    "gpu_peak_memory_mb",
    "gpu_peak_memory_available",
)

SUMMARY_FIELDS = tuple(field for field in PER_SEED_FIELDS if field != "seed") + (
    "seed_count",
)


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read valid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _write_csv(
    path: Path, rows: Sequence[Mapping[str, Any]], fields: Sequence[str]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(fields), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {name: "" if row.get(name) is None else row.get(name) for name in fields}
            )


def _percentile(values: Iterable[float], percentile: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile / 100.0
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _ratio(numerator: float, denominator: float) -> float:
    return float(numerator) / float(denominator) if denominator > 0 else 0.0


def _value(row: Mapping[str, Any], name: str) -> Any:
    if name in row:
        return row[name]
    for alias in ROW_ALIASES.get(name, ()):
        if alias in row:
            return row[alias]
    return None


def _as_int(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not math.isfinite(number) or not number.is_integer():
        raise ValueError(f"{name} must be an integer")
    return int(number)


def _as_float(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def _as_bool(value: Any, name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    raise ValueError(f"{name} must be boolean")


def _optional_nonnegative_float(value: Any, name: str) -> float | None:
    if value is None or (isinstance(value, str) and value.strip().lower() in {"", "na", "none", "null"}):
        return None
    number = _as_float(value, name)
    return None if number < 0.0 else number


def _normalize_row(
    raw: Mapping[str, Any], *, default_split: str | None = None
) -> dict[str, Any]:
    missing = [
        name
        for name in REQUIRED_ROW_FIELDS
        if _value(raw, name) is None and name != "first_confirmation_s"
    ]
    if missing:
        raise ValueError(f"score row is missing required fields: {', '.join(missing)}")

    split_value = _value(raw, "split") or default_split
    if split_value is None:
        raise ValueError("score row has no split and its input has no manifest split")
    split = str(split_value).strip().lower()
    if split not in {"validation", "test", "offline"}:
        raise ValueError(f"unsupported score split: {split}")
    level = str(_value(raw, "level")).strip().lower()
    if level not in LEVELS:
        raise ValueError(f"unsupported interference level: {level}")

    row: dict[str, Any] = {
        "variant_id": str(_value(raw, "variant_id")).strip(),
        "target_count": _as_int(_value(raw, "target_count"), "target_count"),
        "seed": str(_value(raw, "seed")),
        "level": level,
        "split": split,
        "revolution": _as_int(_value(raw, "revolution"), "revolution"),
    }
    integer_fields = (
        "match_count",
        "correct_count",
        "false_count",
        "unique_correct_targets",
        "candidate_opportunities",
        "candidate_true_retained",
        "candidate_edge_count",
        "relation_switch_count",
        "one_to_one_violations",
    )
    float_fields = (
        "candidate_build_ms",
        "inference_ms",
        "assignment_ms",
        "end_to_end_ms",
        "gpu_peak_memory_mb",
    )
    for name in integer_fields:
        row[name] = _as_int(_value(raw, name), name)
    for name in float_fields:
        row[name] = _as_float(_value(raw, name), name)
    availability = raw.get("gpu_peak_memory_available")
    source = str(raw.get("gpu_peak_memory_source") or "").strip().lower()
    if availability is not None:
        row["gpu_peak_memory_available"] = _as_bool(
            availability, "gpu_peak_memory_available"
        )
    elif source in {"not_recorded", "unavailable", "unknown"}:
        row["gpu_peak_memory_available"] = False
    else:
        # Historical rows only carried a numeric measurement.
        row["gpu_peak_memory_available"] = True
    row["first_confirmation_s"] = _optional_nonnegative_float(
        _value(raw, "first_confirmation_s"), "first_confirmation_s"
    )

    if not row["variant_id"]:
        raise ValueError("variant_id must not be empty")
    if row["target_count"] <= 0 or row["revolution"] < 0:
        raise ValueError("target_count must be positive and revolution nonnegative")
    for name in integer_fields + float_fields:
        if row[name] < 0:
            raise ValueError(f"{name} must be nonnegative")
    if row["match_count"] != row["correct_count"] + row["false_count"]:
        raise ValueError("match_count must equal correct_count plus false_count")
    if row["unique_correct_targets"] > row["target_count"]:
        raise ValueError("unique_correct_targets exceeds target_count")
    if row["candidate_true_retained"] > row["candidate_opportunities"]:
        raise ValueError("candidate_true_retained exceeds candidate_opportunities")
    return row


def _manifest_variants(manifest: Mapping[str, Any]) -> tuple[str, dict[str, dict[str, Any]]]:
    raw_variants = manifest.get("variants")
    variants: dict[str, dict[str, Any]] = {}
    if isinstance(raw_variants, Mapping):
        iterable = []
        for variant_id, config in raw_variants.items():
            if not isinstance(config, Mapping):
                raise ValueError("variant configuration must be an object")
            iterable.append({"variant_id": str(variant_id), **dict(config)})
    elif isinstance(raw_variants, Sequence) and not isinstance(raw_variants, (str, bytes)):
        iterable = list(raw_variants)
    else:
        raise ValueError("manifest variants must be an array or object")
    for raw in iterable:
        if not isinstance(raw, Mapping):
            raise ValueError("variant configuration must be an object")
        variant_id = str(raw.get("variant_id") or "").strip()
        if not variant_id or variant_id in variants:
            raise ValueError("manifest contains an empty or duplicate variant_id")
        config = dict(raw)
        config["variant_id"] = variant_id
        config["label_cn"] = str(raw.get("label_cn") or variant_id)
        direct = (
            raw.get("diagnostic_only") is True
            or str(raw.get("confirmation_strategy") or "") == "direct_1of1"
            or "direct_1of1" in variant_id.lower()
        )
        rule = str(
            raw.get("selection_rule")
            or raw.get("variant_type")
            or raw.get("category")
            or "none"
        ).lower()
        if rule == "baseline":
            rule = "none"
        if rule not in SELECTION_RULES:
            raise ValueError(f"unsupported selection_rule for {variant_id}: {rule}")
        config["selection_rule"] = rule
        config["diagnostic_only"] = direct
        variants[variant_id] = config
    baseline_id = str(manifest.get("baseline_variant_id") or "baseline")
    if baseline_id not in variants:
        raise ValueError("baseline_variant_id is absent from manifest variants")
    variants[baseline_id]["selection_rule"] = "none"
    return baseline_id, variants


def _manifest_input_entries(manifest: Mapping[str, Any], base: Path) -> list[dict[str, Any]]:
    raw_inputs = manifest.get("inputs", manifest.get("score_files", ()))
    entries: list[dict[str, Any]] = []
    if isinstance(raw_inputs, Mapping):
        for split, paths in raw_inputs.items():
            values = paths if isinstance(paths, list) else [paths]
            entries.extend({"path": value, "split": split} for value in values)
    elif isinstance(raw_inputs, Sequence) and not isinstance(raw_inputs, (str, bytes)):
        for item in raw_inputs:
            entries.append(dict(item) if isinstance(item, Mapping) else {"path": item})
    elif raw_inputs:
        raise ValueError("manifest inputs must be an array or object")
    normalized: list[dict[str, Any]] = []
    for entry in entries:
        path_value = entry.get("path")
        if not path_value:
            raise ValueError("manifest input entry has no path")
        path = Path(str(path_value))
        if not path.is_absolute():
            path = (base / path).resolve()
        normalized.append({"path": path, "split": entry.get("split")})
    return normalized


def _input_specs(
    manifest: Mapping[str, Any],
    manifest_path: Path,
    score_paths: Sequence[Path] | None,
) -> list[dict[str, Any]]:
    configured = _manifest_input_entries(manifest, manifest_path.parent)
    if not score_paths:
        if not configured:
            raise ValueError("no score files were supplied")
        return configured
    split_by_path = {entry["path"]: entry.get("split") for entry in configured}
    split_by_name = {
        entry["path"].name: entry.get("split")
        for entry in configured
        if sum(other["path"].name == entry["path"].name for other in configured) == 1
    }
    result = []
    for raw_path in score_paths:
        path = raw_path.resolve()
        result.append(
            {
                "path": path,
                "split": split_by_path.get(path, split_by_name.get(path.name)),
            }
        )
    return result


def _read_score_file(path: Path, default_split: str | None) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(path)
    file_split = default_split
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            raw_rows: Any = list(csv.DictReader(stream))
    elif path.suffix.lower() == ".json":
        raw_value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw_value, list):
            raw_rows = raw_value
        elif isinstance(raw_value, Mapping):
            file_split = str(raw_value.get("split") or file_split or "") or None
            raw_rows = next(
                (
                    raw_value[name]
                    for name in ("rows", "records", "data")
                    if isinstance(raw_value.get(name), list)
                ),
                [raw_value],
            )
        else:
            raise ValueError(f"unsupported JSON score payload: {path}")
    else:
        raise ValueError(f"score file must be JSON or CSV: {path}")
    rows = []
    for raw in raw_rows:
        if not isinstance(raw, Mapping):
            raise ValueError(f"score row must be an object: {path}")
        rows.append(_normalize_row(raw, default_split=file_split))
    return rows


def load_score_rows(
    manifest_path: str | Path,
    score_paths: Sequence[str | Path] | None = None,
) -> tuple[dict[str, Any], str, dict[str, dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Load and validate a manifest plus all per-revolution score records."""

    manifest_path = Path(manifest_path).resolve()
    manifest = _read_json_object(manifest_path)
    baseline_id, variants = _manifest_variants(manifest)
    normalized_paths = None if score_paths is None else [Path(path) for path in score_paths]
    specs = _input_specs(manifest, manifest_path, normalized_paths)
    rows: list[dict[str, Any]] = []
    input_metadata: list[dict[str, Any]] = []
    for spec in specs:
        path = spec["path"]
        loaded = _read_score_file(path, spec.get("split"))
        rows.extend(loaded)
        input_metadata.append(
            {
                "path": str(path),
                "sha256": _sha256(path),
                "split": spec.get("split"),
                "row_count": len(loaded),
            }
        )
    if not rows:
        raise ValueError("score inputs contain no rows")
    unknown = sorted({row["variant_id"] for row in rows} - variants.keys())
    if unknown:
        raise ValueError(f"score rows reference unknown variants: {', '.join(unknown)}")
    keys = [
        (
            row["variant_id"],
            row["target_count"],
            row["split"],
            row["seed"],
            row["level"],
            row["revolution"],
        )
        for row in rows
    ]
    if len(keys) != len(set(keys)):
        raise ValueError("score inputs contain duplicate per-revolution records")
    return manifest, baseline_id, variants, rows, input_metadata


def _aggregate_group(
    rows: Sequence[Mapping[str, Any]],
    *,
    variants: Mapping[str, Mapping[str, Any]],
    seed: str | None,
) -> dict[str, Any]:
    first = rows[0]
    config = variants[str(first["variant_id"])]
    target_count = int(first["target_count"])
    matches = sum(int(row["match_count"]) for row in rows)
    correct = sum(int(row["correct_count"]) for row in rows)
    false = sum(int(row["false_count"]) for row in rows)
    unique = sum(int(row["unique_correct_targets"]) for row in rows)
    target_opportunities = target_count * len(rows)
    candidate_opportunities = sum(int(row["candidate_opportunities"]) for row in rows)
    retained = sum(int(row["candidate_true_retained"]) for row in rows)
    edges = sum(int(row["candidate_edge_count"]) for row in rows)
    first_times = [
        float(row["first_confirmation_s"])
        for row in rows
        if row["first_confirmation_s"] is not None
    ]
    no_output = sum(int(row["match_count"]) == 0 for row in rows)
    switches = sum(int(row["relation_switch_count"]) for row in rows)
    if seed is None:
        seed_groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for row in rows:
            seed_groups[str(row["seed"])].append(row)
        switch_opportunities = sum(
            target_count * max(len(seed_rows) - 1, 0)
            for seed_rows in seed_groups.values()
        )
    else:
        switch_opportunities = target_count * max(len(rows) - 1, 0)
    row_precisions = [
        _ratio(int(row["correct_count"]), int(row["match_count"])) for row in rows
    ]
    row_coverages = [
        _ratio(int(row["unique_correct_targets"]), target_count) for row in rows
    ]
    row_retentions = [
        _ratio(int(row["candidate_true_retained"]), int(row["candidate_opportunities"]))
        for row in rows
    ]
    result: dict[str, Any] = {
        "variant_id": first["variant_id"],
        "variant_label_cn": config["label_cn"],
        "selection_rule": config["selection_rule"],
        "diagnostic_only": bool(config["diagnostic_only"]),
        "target_count": target_count,
        "split": first["split"],
        "level": first["level"],
        "revolution_count": len(rows),
        "match_count": matches,
        "correct_count": correct,
        "false_count": false,
        "association_precision": _ratio(correct, matches),
        "macro_association_precision": fmean(row_precisions),
        "unique_correct_targets": unique,
        "target_opportunities": target_opportunities,
        "coverage": _ratio(unique, target_opportunities),
        "macro_coverage": fmean(row_coverages),
        "candidate_opportunities": candidate_opportunities,
        "candidate_true_retained": retained,
        "candidate_true_retention_rate": _ratio(retained, candidate_opportunities),
        "macro_candidate_true_retention_rate": fmean(row_retentions),
        "candidate_edge_count": edges,
        "mean_candidate_edge_count": _ratio(edges, len(rows)),
        "first_confirmation_s": min(first_times) if first_times else None,
        "no_output_revolutions": no_output,
        "no_output_rate": _ratio(no_output, len(rows)),
        "relation_switch_count": switches,
        "relation_switch_opportunities": switch_opportunities,
        "relation_switch_rate": _ratio(switches, switch_opportunities),
        "one_to_one_violations": sum(int(row["one_to_one_violations"]) for row in rows),
        "candidate_build_p95_ms": _percentile(
            (float(row["candidate_build_ms"]) for row in rows), 95
        ),
        "inference_p95_ms": _percentile(
            (float(row["inference_ms"]) for row in rows), 95
        ),
        "assignment_p95_ms": _percentile(
            (float(row["assignment_ms"]) for row in rows), 95
        ),
        "end_to_end_p95_ms": _percentile(
            (float(row["end_to_end_ms"]) for row in rows), 95
        ),
        "gpu_peak_memory_mb": (
            max(float(row["gpu_peak_memory_mb"]) for row in rows)
            if all(bool(row["gpu_peak_memory_available"]) for row in rows)
            else None
        ),
        "gpu_peak_memory_available": all(
            bool(row["gpu_peak_memory_available"]) for row in rows
        ),
    }
    if seed is not None:
        result["seed"] = seed
    return result


def summarize_rows(
    rows: Sequence[Mapping[str, Any]], variants: Mapping[str, Mapping[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return per-seed and cross-seed summaries with weighted and macro metrics."""

    per_seed_groups: dict[tuple[Any, ...], list[Mapping[str, Any]]] = defaultdict(list)
    summary_groups: dict[tuple[Any, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        common = (
            row["variant_id"],
            row["target_count"],
            row["split"],
            row["level"],
        )
        per_seed_groups[common + (row["seed"],)].append(row)
        summary_groups[common].append(row)
    per_seed = [
        _aggregate_group(group, variants=variants, seed=str(key[-1]))
        for key, group in sorted(per_seed_groups.items(), key=lambda item: tuple(map(str, item[0])))
    ]
    summary: list[dict[str, Any]] = []
    per_seed_index: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in per_seed:
        per_seed_index[
            (row["variant_id"], row["target_count"], row["split"], row["level"])
        ].append(row)
    for key, group in sorted(summary_groups.items(), key=lambda item: tuple(map(str, item[0]))):
        item = _aggregate_group(group, variants=variants, seed=None)
        seed_items = per_seed_index[key]
        item["macro_association_precision"] = fmean(
            float(seed_row["association_precision"]) for seed_row in seed_items
        )
        item["macro_coverage"] = fmean(float(seed_row["coverage"]) for seed_row in seed_items)
        item["macro_candidate_true_retention_rate"] = fmean(
            float(seed_row["candidate_true_retention_rate"]) for seed_row in seed_items
        )
        confirmation_times = [
            float(seed_row["first_confirmation_s"])
            for seed_row in seed_items
            if seed_row["first_confirmation_s"] is not None
        ]
        item["first_confirmation_s"] = (
            fmean(confirmation_times) if confirmation_times else None
        )
        item["seed_count"] = len(seed_items)
        summary.append(item)
    return per_seed, summary


def _summary_by_variant_level(
    summary: Sequence[Mapping[str, Any]], *, split: str, target_count: int
) -> dict[str, dict[str, Mapping[str, Any]]]:
    result: dict[str, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for row in summary:
        if row["split"] == split and int(row["target_count"]) == target_count:
            result[str(row["variant_id"])][str(row["level"])] = row
    return result


def _mean_levels(rows: Mapping[str, Mapping[str, Any]], metric: str) -> float:
    return fmean(float(rows[level][metric]) for level in LEVELS)


def _decision(
    variant_id: str,
    rule: str,
    baseline: Mapping[str, Mapping[str, Any]],
    candidate: Mapping[str, Mapping[str, Any]],
    diagnostic_only: bool,
) -> dict[str, Any]:
    reasons: list[str] = []
    if diagnostic_only:
        return {
            "variant_id": variant_id,
            "selection_rule": rule,
            "eligible": False,
            "reason_codes": ["diagnostic_only_direct_1of1"],
            "deltas": {},
        }
    if any(level not in baseline or level not in candidate for level in LEVELS):
        return {
            "variant_id": variant_id,
            "selection_rule": rule,
            "eligible": False,
            "reason_codes": ["validation_clean_light_incomplete"],
            "deltas": {},
        }
    precision_deltas = {
        level: float(candidate[level]["association_precision"])
        - float(baseline[level]["association_precision"])
        for level in LEVELS
    }
    precision_delta = fmean(precision_deltas.values())
    light_retention_delta = float(candidate["light"]["candidate_true_retention_rate"]) - float(
        baseline["light"]["candidate_true_retention_rate"]
    )
    clean_coverage_delta = float(candidate["clean"]["coverage"]) - float(
        baseline["clean"]["coverage"]
    )
    light_coverage_delta = float(candidate["light"]["coverage"]) - float(
        baseline["light"]["coverage"]
    )
    average_coverage_delta = (clean_coverage_delta + light_coverage_delta) / 2.0
    switch_delta = _mean_levels(candidate, "relation_switch_rate") - _mean_levels(
        baseline, "relation_switch_rate"
    )
    one_to_one = sum(int(candidate[level]["one_to_one_violations"]) for level in LEVELS)
    latency_p95 = max(float(candidate[level]["end_to_end_p95_ms"]) for level in LEVELS)
    deltas = {
        "mean_precision_delta": precision_delta,
        "clean_precision_delta": precision_deltas["clean"],
        "light_precision_delta": precision_deltas["light"],
        "light_candidate_retention_delta": light_retention_delta,
        "clean_coverage_delta": clean_coverage_delta,
        "light_coverage_delta": light_coverage_delta,
        "mean_coverage_delta": average_coverage_delta,
        "mean_relation_switch_rate_delta": switch_delta,
        "one_to_one_violations": one_to_one,
        "max_end_to_end_p95_ms": latency_p95,
    }
    tolerance = 1e-12
    for level in LEVELS:
        if precision_deltas[level] < -0.02 - tolerance:
            reasons.append(f"{level}_precision_drop_exceeds_2pp")
    if rule == "candidate":
        if max(light_retention_delta, light_coverage_delta) < 0.01 - tolerance:
            reasons.append("light_retention_or_coverage_gain_below_1pp")
    elif rule == "confirmation":
        if average_coverage_delta < 0.05 - tolerance:
            reasons.append("mean_coverage_gain_below_5pp")
        if clean_coverage_delta < -tolerance or light_coverage_delta < -tolerance:
            reasons.append("coverage_decreased_in_a_level")
        if switch_delta > 0.01 + tolerance:
            reasons.append("relation_switch_rate_increase_exceeds_1pp")
        if one_to_one != 0:
            reasons.append("one_to_one_violation")
        if latency_p95 > 1000.0 + tolerance:
            reasons.append("latency_p95_exceeds_1000ms")
    else:
        reasons.append("not_a_selectable_variant")
    return {
        "variant_id": variant_id,
        "selection_rule": rule,
        "eligible": not reasons,
        "reason_codes": reasons,
        "deltas": deltas,
    }


def evaluate_variants(
    summary: Sequence[Mapping[str, Any]],
    variants: Mapping[str, Mapping[str, Any]],
    baseline_variant_id: str,
) -> dict[str, Any]:
    """Apply fail-closed validation rules; test rows never influence selection."""

    by_variant = _summary_by_variant_level(
        summary, split="validation", target_count=MAIN_TARGET_COUNT
    )
    baseline = by_variant.get(baseline_variant_id, {})
    families: dict[str, Any] = {}
    for rule in ("candidate", "confirmation"):
        decisions = []
        for variant_id, config in variants.items():
            if config["selection_rule"] != rule:
                continue
            decisions.append(
                _decision(
                    variant_id,
                    rule,
                    baseline,
                    by_variant.get(variant_id, {}),
                    bool(config["diagnostic_only"]),
                )
            )
        eligible = [decision for decision in decisions if decision["eligible"]]
        if rule == "candidate":
            eligible.sort(
                key=lambda item: (
                    item["deltas"]["light_coverage_delta"],
                    item["deltas"]["light_candidate_retention_delta"],
                    -item["deltas"]["max_end_to_end_p95_ms"],
                ),
                reverse=True,
            )
        else:
            eligible.sort(
                key=lambda item: (
                    item["deltas"]["mean_coverage_delta"],
                    -item["deltas"]["mean_relation_switch_rate_delta"],
                    -item["deltas"]["max_end_to_end_p95_ms"],
                ),
                reverse=True,
            )
        selected = eligible[0]["variant_id"] if eligible else baseline_variant_id
        families[rule] = {
            "selected_variant_id": selected,
            "baseline_retained": not eligible,
            "decisions": decisions,
        }
    direct_variants = [
        variant_id
        for variant_id, config in variants.items()
        if bool(config["diagnostic_only"])
    ]
    return {
        "selection_basis": "validation_target_20_clean_light_per_level_precision_gate",
        "test_used_for_selection": False,
        "test_previously_inspected": True,
        "baseline_variant_id": baseline_variant_id,
        "candidate_strategy": families["candidate"],
        "confirmation_strategy": families["confirmation"],
        "diagnostic_variants_excluded": direct_variants,
    }


def _preferred_split(summary: Sequence[Mapping[str, Any]], target_count: int) -> str | None:
    present = {
        str(row["split"])
        for row in summary
        if int(row["target_count"]) == target_count
    }
    for split in ("test", "offline", "validation"):
        if split in present:
            return split
    return None


def _plot_rows(
    summary: Sequence[Mapping[str, Any]], target_count: int
) -> list[Mapping[str, Any]]:
    split = _preferred_split(summary, target_count)
    return [
        row
        for row in summary
        if int(row["target_count"]) == target_count and row["split"] == split
    ] if split else []


def _variant_order(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    return list(dict.fromkeys(str(row["variant_id"]) for row in rows))


def _label_map(rows: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    return {
        str(row["variant_id"]): str(row["variant_label_cn"])
        for row in rows
    }


def _save_figure(path: Path, figure: plt.Figure) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.tight_layout()
    figure.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(figure)


def _plot_candidate(summary: Sequence[Mapping[str, Any]], path: Path) -> None:
    rows = _plot_rows(summary, MAIN_TARGET_COUNT)
    variants = _variant_order(rows)
    labels = _label_map(rows)
    figure, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    width = 0.36
    for level_index, level in enumerate(LEVELS):
        selected = {(row["variant_id"], row["level"]): row for row in rows}
        x = [index + (level_index - 0.5) * width for index in range(len(variants))]
        retention = [
            100.0 * float(selected.get((variant, level), {}).get("candidate_true_retention_rate", 0.0))
            for variant in variants
        ]
        edges = [
            float(selected.get((variant, level), {}).get("mean_candidate_edge_count", 0.0))
            for variant in variants
        ]
        axes[0].bar(x, retention, width, label=level)
        axes[1].bar(x, edges, width, label=level)
    for axis in axes:
        axis.set_xticks(range(len(variants)), [labels.get(item, item) for item in variants], rotation=20, ha="right")
        axis.grid(axis="y", alpha=0.25)
        axis.legend()
    axes[0].set_ylabel("True candidate retention (%)")
    axes[0].set_title("Candidate retention")
    axes[1].set_ylabel("Mean candidate edges / revolution")
    axes[1].set_title("Candidate graph size")
    _save_figure(path, figure)


def _plot_precision_coverage(summary: Sequence[Mapping[str, Any]], path: Path) -> None:
    rows = _plot_rows(summary, MAIN_TARGET_COUNT)
    figure, axis = plt.subplots(figsize=(7.2, 5.2))
    markers = {"clean": "o", "light": "s"}
    for row in rows:
        axis.scatter(
            100.0 * float(row["coverage"]),
            100.0 * float(row["association_precision"]),
            marker=markers[str(row["level"])],
            s=64,
        )
        axis.annotate(
            f"{row['variant_label_cn']} / {row['level']}",
            (100.0 * float(row["coverage"]), 100.0 * float(row["association_precision"])),
            xytext=(4, 4),
            textcoords="offset points",
            fontsize=8,
        )
    axis.set_xlabel("Coverage (%)")
    axis.set_ylabel("Association precision (%)")
    axis.set_title("20-target precision and coverage")
    axis.grid(alpha=0.25)
    _save_figure(path, figure)


def _plot_confirmation(summary: Sequence[Mapping[str, Any]], path: Path) -> None:
    rows = _plot_rows(summary, MAIN_TARGET_COUNT)
    variants = _variant_order(rows)
    labels = _label_map(rows)
    by_variant: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        by_variant[str(row["variant_id"])].append(row)
    times = []
    no_output = []
    for variant in variants:
        available = [
            float(row["first_confirmation_s"])
            for row in by_variant[variant]
            if row["first_confirmation_s"] is not None
        ]
        times.append(fmean(available) if available else 0.0)
        no_output.append(100.0 * fmean(float(row["no_output_rate"]) for row in by_variant[variant]))
    figure, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    axes[0].bar(range(len(variants)), times, color="#4472c4")
    axes[1].bar(range(len(variants)), no_output, color="#c55a11")
    for axis in axes:
        axis.set_xticks(range(len(variants)), [labels.get(item, item) for item in variants], rotation=20, ha="right")
        axis.grid(axis="y", alpha=0.25)
    axes[0].set_ylabel("Seconds")
    axes[0].set_title("First confirmation")
    axes[1].set_ylabel("No-output revolutions (%)")
    axes[1].set_title("No-output rate")
    _save_figure(path, figure)


def _plot_scale(summary: Sequence[Mapping[str, Any]], path: Path) -> None:
    counts = [count for count in (20, 40, 60) if _plot_rows(summary, count)]
    all_rows = [row for count in counts for row in _plot_rows(summary, count)]
    present_by_count = [
        {str(row["variant_id"]) for row in _plot_rows(summary, count)}
        for count in counts
    ]
    common = set.intersection(*present_by_count) if present_by_count else set()
    variants = [variant for variant in SCALE_PREFERRED_VARIANTS if variant in common]
    if not variants:
        variants = [variant for variant in _variant_order(all_rows) if variant in common]
    labels = _label_map(all_rows)
    figure, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    for variant in variants:
        precision = []
        coverage = []
        available_counts = []
        for count in counts:
            selected = [
                row for row in _plot_rows(summary, count) if row["variant_id"] == variant
            ]
            if not selected:
                continue
            available_counts.append(count)
            precision.append(100.0 * fmean(float(row["association_precision"]) for row in selected))
            coverage.append(100.0 * fmean(float(row["coverage"]) for row in selected))
        if available_counts:
            axes[0].plot(available_counts, precision, marker="o", label=labels.get(variant, variant))
            axes[1].plot(available_counts, coverage, marker="o", label=labels.get(variant, variant))
    for axis in axes:
        axis.set_xticks(counts)
        axis.set_xlabel("目标数量")
        axis.grid(alpha=0.25)
        axis.legend(title="策略", fontsize=8)
    axes[0].set_ylabel("无干扰与轻干扰平均关联精度（%）")
    axes[0].set_title("不同目标规模的关联精度")
    axes[1].set_ylabel("无干扰与轻干扰平均覆盖度（%）")
    axes[1].set_title("不同目标规模的覆盖度")
    _save_figure(path, figure)


def generate_figures(summary: Sequence[Mapping[str, Any]], output_dir: Path) -> list[str]:
    figures = [
        ("candidate_retention_edges.png", _plot_candidate),
        ("precision_coverage.png", _plot_precision_coverage),
        ("confirmation_timing_no_output.png", _plot_confirmation),
        ("scale_20_40_60.png", _plot_scale),
    ]
    for filename, function in figures:
        function(summary, output_dir / filename)
    return [filename for filename, _ in figures]


_REASON_CN = {
    "diagnostic_only_direct_1of1": "单圈直接确认只用于诊断，不参与策略选择",
    "validation_clean_light_incomplete": "验证集缺少无干扰或轻干扰结果",
    "clean_precision_drop_exceeds_2pp": "无干扰档关联精度下降超过2个百分点",
    "light_precision_drop_exceeds_2pp": "轻干扰档关联精度下降超过2个百分点",
    "light_retention_or_coverage_gain_below_1pp": "轻干扰候选保留率和覆盖度增益均不足1个百分点",
    "mean_coverage_gain_below_5pp": "无干扰和轻干扰平均覆盖增益不足5个百分点",
    "coverage_decreased_in_a_level": "至少一个干扰档的覆盖度下降",
    "relation_switch_rate_increase_exceeds_1pp": "关系切换率增加超过1个百分点",
    "one_to_one_violation": "发生一对一约束违规",
    "latency_p95_exceeds_1000ms": "端到端95%分位时延超过1000毫秒",
    "not_a_selectable_variant": "该配置未声明选择规则",
}


def _result_table(
    lines: list[str], rows: Sequence[Mapping[str, Any]], *, target_count: int, heading: str
) -> None:
    selected = _plot_rows(rows, target_count)
    lines.extend(
        [
            f"## {heading}",
            "",
            "| 配置 | 条件 | 关联精度 | 覆盖度 | 候选保留率 | 首次确认 | 无输出圈 | 切换率 | P95时延 | GPU峰值 |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    if not selected:
        lines.extend(["| 无数据 | - | - | - | - | - | - | - | - | - |", ""])
        return
    for row in selected:
        first = "未确认" if row["first_confirmation_s"] is None else f"{float(row['first_confirmation_s']):.2f}秒"
        gpu = (
            f"{float(row['gpu_peak_memory_mb']):.0f}MB"
            if row.get("gpu_peak_memory_available")
            and row.get("gpu_peak_memory_mb") is not None
            else "未记录"
        )
        lines.append(
            "| {label} | {level} | {precision:.1%} | {coverage:.1%} | {retention:.1%} | "
            "{first} | {empty}/{rounds} | {switch:.2%} | {latency:.1f}毫秒 | {gpu} |".format(
                label=row["variant_label_cn"],
                level="无干扰" if row["level"] == "clean" else "轻干扰",
                precision=float(row["association_precision"]),
                coverage=float(row["coverage"]),
                retention=float(row["candidate_true_retention_rate"]),
                first=first,
                empty=int(row["no_output_revolutions"]),
                rounds=int(row["revolution_count"]),
                switch=float(row["relation_switch_rate"]),
                latency=float(row["end_to_end_p95_ms"]),
                gpu=gpu,
            )
        )
    lines.append("")


def _selection_section(
    lines: list[str], selection: Mapping[str, Any], variants: Mapping[str, Mapping[str, Any]]
) -> None:
    lines.extend(["## 验证集判断", ""])
    for key, title in (("candidate_strategy", "候选初筛"), ("confirmation_strategy", "确认策略")):
        family = selection[key]
        selected = str(family["selected_variant_id"])
        if family["baseline_retained"]:
            lines.append(f"{title}没有配置满足全部约束，继续保留基线。")
        else:
            lines.append(f"{title}验证规则选中的配置为“{variants[selected]['label_cn']}”。")
        for decision in family["decisions"]:
            label = variants[decision["variant_id"]]["label_cn"]
            if decision["eligible"]:
                lines.append(f"- {label}：满足本轮验证规则。")
            else:
                reasons = "；".join(_REASON_CN.get(code, code) for code in decision["reason_codes"])
                lines.append(f"- {label}：{reasons}。")
        lines.append("")
    lines.append(
        "上述判断只使用20目标验证数据。测试数据没有参与门限或配置选择。"
        "本批测试随机种子此前已经使用，因此结果只用于复核现象，不能表述为正式定型或正式采用。"
    )
    lines.append("")


def _write_markdown(
    path: Path,
    *,
    summary: Sequence[Mapping[str, Any]],
    selection: Mapping[str, Any],
    variants: Mapping[str, Mapping[str, Any]],
    input_count: int,
) -> None:
    lines = [
        "# 双光电初筛与确认策略离线评估",
        "",
        "## 统计口径",
        "",
        f"报告汇总{input_count}个逐圈评分文件。无干扰和轻干扰分别统计，20目标作为主结果，40和60目标只作离线复核。",
        "",
        "关联精度按全部已发布关系加权计算。覆盖度按每圈正确关联的唯一目标数除以目标数计算。候选真关系保留率按保留真关系数除以候选机会数计算。关系切换率以同一随机种子相邻扫描之间的目标数作为机会总数。空输出圈进入覆盖度和空输出统计，但不会虚构正确或错误关系。",
        "",
        "单圈直接确认（direct_1of1）只用于观察覆盖上限及误配代价，不进入候选或确认策略选择。",
        "",
    ]
    _selection_section(lines, selection, variants)
    _result_table(lines, summary, target_count=20, heading="20目标主结果")
    _result_table(lines, summary, target_count=40, heading="40目标离线复核")
    _result_table(lines, summary, target_count=60, heading="60目标离线复核")
    lines.extend(
        [
            "## 结果图",
            "",
            "![候选保留率与候选边数](candidate_retention_edges.png)",
            "",
            "![关联精度与覆盖度](precision_coverage.png)",
            "",
            "![首次确认与无输出圈](confirmation_timing_no_output.png)",
            "",
            "![20、40、60目标离线对比](scale_20_40_60.png)",
            "",
            "## 使用限制",
            "",
            "本报告只比较候选放宽和确认策略对既有评分数据的影响。40和60目标结果标记为离线复核。测试集此前已经查看过，不能作为新的独立验收证据。若需修改正式默认配置，应重新封存未使用的随机种子并重复同一统计流程。",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def generate_gate_confirmation_report(
    manifest_path: str | Path,
    output_dir: str | Path,
    score_paths: Sequence[str | Path] | None = None,
) -> Path:
    """Generate fixed-name CSV, JSON, Markdown, and PNG report artifacts."""

    manifest_path = Path(manifest_path).resolve()
    output_dir = Path(output_dir).resolve()
    manifest, baseline_id, variants, rows, input_metadata = load_score_rows(
        manifest_path, score_paths
    )
    per_seed, summary = summarize_rows(rows, variants)
    selection = evaluate_variants(summary, variants, baseline_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    figures = generate_figures(summary, output_dir)
    _write_csv(output_dir / "per_seed.csv", per_seed, PER_SEED_FIELDS)
    _write_csv(output_dir / "summary.csv", summary, SUMMARY_FIELDS)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "manifest_path": str(manifest_path),
        "manifest_sha256": _sha256(manifest_path),
        "baseline_variant_id": baseline_id,
        "levels": list(LEVELS),
        "main_target_count": MAIN_TARGET_COUNT,
        "offline_review_target_counts": list(OFFLINE_REVIEW_COUNTS),
        "truth_used_for_offline_scoring_only": True,
        "test_previously_inspected": True,
        "test_used_for_selection": False,
        "inputs": input_metadata,
        "variants": list(variants.values()),
        "per_seed": per_seed,
        "summary": summary,
        "selection": selection,
        "figures": figures,
    }
    metrics_path = output_dir / "metrics.json"
    _write_json(metrics_path, payload)
    _write_markdown(
        output_dir / "GATE_CONFIRMATION_ABLATION_REPORT_CN.md",
        summary=summary,
        selection=selection,
        variants=variants,
        input_count=len(input_metadata),
    )
    return metrics_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--input",
        "--scores",
        dest="score_files",
        type=Path,
        nargs="+",
        action="extend",
        help="JSON/CSV score files; defaults to manifest inputs",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    path = generate_gate_confirmation_report(
        args.manifest, args.output_dir, args.score_files
    )
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
