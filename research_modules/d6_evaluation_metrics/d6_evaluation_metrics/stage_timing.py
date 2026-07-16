"""Strict offline validation and reporting for AirSim stage timing logs.

D6 consumes the persisted JSONL records only.  The two timing scopes are
validated and summarized independently because the control-tick scope wraps
the main-bus scope and therefore cannot be added to it.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence


STAGE_TIMING_REPORT_SCHEMA_VERSION = "d6-stage-timing-report-v2"
STAGE_TIMING_SCOPE_SUMMARY_SCHEMA_VERSION = "d6-stage-timing-scope-summary-v2"
SINGLE_EPISODE_TIMING_MODE = "single_episode"
CASE_AWARE_SUITE_TIMING_MODE = "case_aware_suite"
STAGE_TIMING_INPUT_MODES = (
    SINGLE_EPISODE_TIMING_MODE,
    CASE_AWARE_SUITE_TIMING_MODE,
)
CASE_AWARE_TIMING_METADATA_FIELDS = (
    "case_id",
    "family",
    "profile",
    "seed",
)


@dataclass(frozen=True)
class _TimingScopeSpec:
    layer: str
    schema_version: str
    scope: str
    total_stage_name: str
    stage_names: tuple[str, ...]


_MAIN_BUS_SPEC = _TimingScopeSpec(
    layer="main_bus",
    schema_version="main-stage-timing-v1",
    scope="main_episode_bus",
    total_stage_name="bus_total",
    stage_names=(
        "communication",
        "d1_fusion",
        "d2_association",
        "d6_track_recording",
        "d3_assignment",
        "coalition_commit",
        "d5_terminal_association",
        "d4_arbitration",
        "d7_guidance_contract",
        "link_and_cross_view_recording",
    ),
)

_CONTROL_TICK_SPEC = _TimingScopeSpec(
    layer="control_tick",
    schema_version="control-tick-stage-timing-v1",
    scope="simpleflight_control_tick",
    total_stage_name="control_tick_total",
    stage_names=(
        "airsim_frame_sample",
        "bus_processing",
        "control_evidence_and_pair_sync",
        "guidance_and_control_rpc",
    ),
)

_SCOPE_SPECS = {
    _MAIN_BUS_SPEC.layer: _MAIN_BUS_SPEC,
    _CONTROL_TICK_SPEC.layer: _CONTROL_TICK_SPEC,
}

_REQUIRED_RECORD_FIELDS = {
    "schema_version",
    "scope",
    "frame_index",
    "timestamp_s",
    "budget_ms",
    "total_stage_name",
    "stages_ms",
    "stage_status",
    "measured_stage_sum_ms",
    "unattributed_ms",
    "total_ms",
    "budget_exceeded",
    "error_type",
    "error_message",
}

_MEASURED_STATUSES = {"available", "error"}
_ALLOWED_STATUSES = {*_MEASURED_STATUSES, "not_applicable"}


class StageTimingValidationError(ValueError):
    """Raised when persisted stage timing evidence violates its contract."""


@dataclass(frozen=True)
class StageTimingInputs:
    """Optional paths for the two independent timing layers."""

    main_bus: str | Path | None = None
    control_tick: str | Path | None = None
    input_mode: str = SINGLE_EPISODE_TIMING_MODE


def _normalize_stage_timing_input_mode(value: Any) -> str:
    """Return one supported timing mode before any loader/evaluator dispatch."""

    if not isinstance(value, str) or value not in STAGE_TIMING_INPUT_MODES:
        raise StageTimingValidationError(
            f"input_mode must be one of {list(STAGE_TIMING_INPUT_MODES)}, got {value!r}"
        )
    return value


class StageTimingReportGenerator:
    """Write an offline, availability-aware timing report bundle."""

    def write_report_bundle(
        self,
        output_dir: str | Path,
        *,
        inputs: StageTimingInputs,
        title: str = "AirSim 分阶段延迟离线评估报告",
    ) -> dict[str, Path]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        summary = evaluate_stage_timing_inputs(inputs)

        json_path = output_dir / "stage_timing_summary.json"
        json_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        csv_path = output_dir / "stage_timing_summary.csv"
        rows = stage_timing_csv_rows(summary)
        with csv_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=_CSV_FIELDS)
            writer.writeheader()
            writer.writerows(rows)

        plot_path = output_dir / "stage_timing_overview.png"
        _write_stage_timing_plot(summary, plot_path)

        markdown_path = output_dir / "STAGE_TIMING_REPORT_CN.md"
        markdown_path.write_text(
            render_stage_timing_markdown(
                summary,
                title=title,
                plot_name=plot_path.name,
            ),
            encoding="utf-8",
        )
        return {
            "csv": csv_path,
            "json": json_path,
            "markdown": markdown_path,
            "plot": plot_path,
        }


def load_stage_timing_jsonl(
    path: str | Path,
    *,
    expected_layer: str,
    input_mode: str = SINGLE_EPISODE_TIMING_MODE,
) -> list[dict[str, Any]]:
    """Load and strictly validate one timing JSONL stream.

    A malformed record raises :class:`StageTimingValidationError`; it is never
    converted to a zero-valued latency observation.
    """

    spec = _scope_spec(expected_layer)
    mode = _normalize_stage_timing_input_mode(input_mode)
    source_path = Path(path)
    records: list[dict[str, Any]] = []
    try:
        stream = source_path.open("r", encoding="utf-8")
    except OSError as exc:
        raise StageTimingValidationError(
            f"{expected_layer}: cannot read timing JSONL {source_path}: {exc}"
        ) from exc
    with stream:
        for line_number, line in enumerate(stream, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                raw = json.loads(stripped)
            except (json.JSONDecodeError, ValueError) as exc:
                raise StageTimingValidationError(
                    f"{expected_layer} line {line_number}: invalid JSON: {exc}"
                ) from exc
            validator = (
                validate_stage_timing_record
                if mode == SINGLE_EPISODE_TIMING_MODE
                else validate_case_aware_stage_timing_record
            )
            records.append(
                validator(
                    raw,
                    expected_layer=spec.layer,
                    line_number=line_number,
                )
            )
    _validate_timing_record_order(records, layer=spec.layer, input_mode=mode)
    return records


def validate_stage_timing_record(
    raw: Any,
    *,
    expected_layer: str,
    line_number: int | None = None,
) -> dict[str, Any]:
    """Validate and normalize one current-version timing record."""

    spec = _scope_spec(expected_layer)
    prefix = f"{spec.layer}"
    if line_number is not None:
        prefix += f" line {line_number}"
    if not isinstance(raw, Mapping):
        raise StageTimingValidationError(f"{prefix}: record must be a JSON object")
    fields = set(raw)
    missing = sorted(_REQUIRED_RECORD_FIELDS - fields)
    extra = sorted(fields - _REQUIRED_RECORD_FIELDS)
    if missing or extra:
        raise StageTimingValidationError(
            f"{prefix}: record fields mismatch; missing={missing}, extra={extra}"
        )
    if raw["schema_version"] != spec.schema_version:
        raise StageTimingValidationError(
            f"{prefix}: expected schema {spec.schema_version!r}, "
            f"got {raw['schema_version']!r}"
        )
    if raw["scope"] != spec.scope:
        raise StageTimingValidationError(
            f"{prefix}: expected scope {spec.scope!r}, got {raw['scope']!r}"
        )
    if raw["total_stage_name"] != spec.total_stage_name:
        raise StageTimingValidationError(
            f"{prefix}: expected total stage {spec.total_stage_name!r}, "
            f"got {raw['total_stage_name']!r}"
        )

    frame_index = _integer(raw["frame_index"], name="frame_index", prefix=prefix)
    if frame_index < 0:
        raise StageTimingValidationError(f"{prefix}: frame_index must be nonnegative")
    timestamp_s = _finite_number(
        raw["timestamp_s"], name="timestamp_s", prefix=prefix
    )
    if timestamp_s < 0.0:
        raise StageTimingValidationError(f"{prefix}: timestamp_s must be nonnegative")
    budget_ms = _finite_number(raw["budget_ms"], name="budget_ms", prefix=prefix)
    if budget_ms <= 0.0:
        raise StageTimingValidationError(f"{prefix}: budget_ms must be positive")

    stages_raw = raw["stages_ms"]
    statuses_raw = raw["stage_status"]
    if not isinstance(stages_raw, Mapping) or not isinstance(statuses_raw, Mapping):
        raise StageTimingValidationError(
            f"{prefix}: stages_ms and stage_status must be objects"
        )
    expected_names = set(spec.stage_names)
    if set(stages_raw) != expected_names:
        raise StageTimingValidationError(
            f"{prefix}: stages_ms keys must exactly match {list(spec.stage_names)}"
        )
    if set(statuses_raw) != expected_names:
        raise StageTimingValidationError(
            f"{prefix}: stage_status keys must exactly match {list(spec.stage_names)}"
        )

    stages_ms: dict[str, float | None] = {}
    stage_status: dict[str, str] = {}
    for stage_name in spec.stage_names:
        status = statuses_raw[stage_name]
        if not isinstance(status, str) or status not in _ALLOWED_STATUSES:
            raise StageTimingValidationError(
                f"{prefix}: invalid status for {stage_name!r}: {status!r}"
            )
        value = stages_raw[stage_name]
        if status == "not_applicable":
            if value is not None:
                raise StageTimingValidationError(
                    f"{prefix}: not_applicable stage {stage_name!r} must have null duration"
                )
            normalized_value = None
        else:
            normalized_value = _finite_number(
                value,
                name=f"stages_ms.{stage_name}",
                prefix=prefix,
            )
            if normalized_value < 0.0:
                raise StageTimingValidationError(
                    f"{prefix}: stage {stage_name!r} duration must be nonnegative"
                )
        stages_ms[stage_name] = normalized_value
        stage_status[stage_name] = status

    measured_sum_ms = _finite_nonnegative(
        raw["measured_stage_sum_ms"],
        name="measured_stage_sum_ms",
        prefix=prefix,
    )
    unattributed_ms = _finite_nonnegative(
        raw["unattributed_ms"], name="unattributed_ms", prefix=prefix
    )
    total_ms = _finite_nonnegative(raw["total_ms"], name="total_ms", prefix=prefix)
    computed_sum_ms = sum(value for value in stages_ms.values() if value is not None)
    if not _same_float(measured_sum_ms, computed_sum_ms):
        raise StageTimingValidationError(
            f"{prefix}: measured_stage_sum_ms conflicts with stage durations"
        )
    if total_ms < measured_sum_ms:
        raise StageTimingValidationError(
            f"{prefix}: total_ms must be >= measured_stage_sum_ms"
        )
    computed_unattributed_ms = total_ms - measured_sum_ms
    if not _same_float(unattributed_ms, computed_unattributed_ms):
        raise StageTimingValidationError(
            f"{prefix}: unattributed_ms conflicts with total minus measured sum"
        )

    budget_exceeded = raw["budget_exceeded"]
    if not isinstance(budget_exceeded, bool):
        raise StageTimingValidationError(f"{prefix}: budget_exceeded must be boolean")
    if budget_exceeded is not (total_ms > budget_ms):
        raise StageTimingValidationError(
            f"{prefix}: budget_exceeded conflicts with total_ms and budget_ms"
        )

    error_type = raw["error_type"]
    error_message = raw["error_message"]
    if not isinstance(error_type, str) or not isinstance(error_message, str):
        raise StageTimingValidationError(
            f"{prefix}: error_type and error_message must be strings"
        )
    has_stage_error = any(status == "error" for status in stage_status.values())
    if has_stage_error != bool(error_type.strip()):
        raise StageTimingValidationError(
            f"{prefix}: error stage status conflicts with error_type"
        )
    if not error_type.strip() and error_message:
        raise StageTimingValidationError(
            f"{prefix}: error_message requires a non-empty error_type"
        )

    return {
        "schema_version": spec.schema_version,
        "scope": spec.scope,
        "frame_index": frame_index,
        "timestamp_s": timestamp_s,
        "budget_ms": budget_ms,
        "total_stage_name": spec.total_stage_name,
        "stages_ms": stages_ms,
        "stage_status": stage_status,
        "measured_stage_sum_ms": measured_sum_ms,
        "unattributed_ms": unattributed_ms,
        "total_ms": total_ms,
        "budget_exceeded": budget_exceeded,
        "error_type": error_type,
        "error_message": error_message,
    }


def validate_case_aware_stage_timing_record(
    raw: Any,
    *,
    expected_layer: str,
    line_number: int | None = None,
) -> dict[str, Any]:
    """Validate one suite-envelope record without relaxing episode records."""

    spec = _scope_spec(expected_layer)
    prefix = spec.layer
    if line_number is not None:
        prefix += f" line {line_number}"
    if not isinstance(raw, Mapping):
        raise StageTimingValidationError(f"{prefix}: record must be a JSON object")
    expected_fields = _REQUIRED_RECORD_FIELDS | set(CASE_AWARE_TIMING_METADATA_FIELDS)
    fields = set(raw)
    missing = sorted(expected_fields - fields)
    extra = sorted(fields - expected_fields)
    if missing or extra:
        raise StageTimingValidationError(
            f"{prefix}: case-aware record fields mismatch; "
            f"missing={missing}, extra={extra}"
        )

    metadata: dict[str, Any] = {}
    for field in ("case_id", "family", "profile"):
        value = raw[field]
        if not isinstance(value, str) or not value.strip():
            raise StageTimingValidationError(
                f"{prefix}: case metadata {field} must be a non-empty string"
            )
        metadata[field] = value
    seed = raw["seed"]
    if isinstance(seed, bool) or not isinstance(seed, int) or seed <= 0:
        raise StageTimingValidationError(
            f"{prefix}: case metadata seed must be a positive integer"
        )
    metadata["seed"] = seed

    episode_record = {
        field: raw[field] for field in _REQUIRED_RECORD_FIELDS
    }
    normalized = validate_stage_timing_record(
        episode_record,
        expected_layer=expected_layer,
        line_number=line_number,
    )
    return {**normalized, **metadata}


def summarize_stage_timing_records(
    records: Sequence[Mapping[str, Any]],
    *,
    expected_layer: str,
    evidence_path: str | Path | None = None,
    input_mode: str = SINGLE_EPISODE_TIMING_MODE,
) -> dict[str, Any]:
    """Validate and summarize one layer without combining nested durations."""

    spec = _scope_spec(expected_layer)
    mode = _normalize_stage_timing_input_mode(input_mode)
    validator = (
        validate_stage_timing_record
        if mode == SINGLE_EPISODE_TIMING_MODE
        else validate_case_aware_stage_timing_record
    )
    normalized = [
        validator(
            record,
            expected_layer=spec.layer,
            line_number=index,
        )
        for index, record in enumerate(records, start=1)
    ]
    _validate_timing_record_order(normalized, layer=spec.layer, input_mode=mode)
    if not normalized:
        return _unavailable_layer_summary(
            spec,
            reason="stage_timing_records_empty",
            evidence_path=evidence_path,
            input_mode=mode,
        )

    stages: dict[str, dict[str, Any]] = {}
    for stage_name in spec.stage_names:
        statuses = [record["stage_status"][stage_name] for record in normalized]
        values = [
            float(record["stages_ms"][stage_name])
            for record, status in zip(normalized, statuses)
            if status in _MEASURED_STATUSES
        ]
        stages[stage_name] = {
            **_distribution(values),
            "available_count": statuses.count("available"),
            "not_applicable_count": statuses.count("not_applicable"),
            "error_count": statuses.count("error"),
            "status_counts": {
                "available": statuses.count("available"),
                "not_applicable": statuses.count("not_applicable"),
                "error": statuses.count("error"),
            },
        }

    dominant_candidates = [
        (stage_name, stages[stage_name]["mean_ms"])
        for stage_name in spec.stage_names
        if stages[stage_name]["mean_ms"] is not None
    ]
    dominant_stage = (
        max(dominant_candidates, key=lambda item: float(item[1]))[0]
        if dominant_candidates
        else None
    )
    violation_count = sum(record["budget_exceeded"] for record in normalized)
    case_summaries = (
        _case_timing_summaries(normalized, spec=spec)
        if mode == CASE_AWARE_SUITE_TIMING_MODE
        else []
    )
    case_order = [item["case"] for item in case_summaries]
    return {
        "schema_version": STAGE_TIMING_SCOPE_SUMMARY_SCHEMA_VERSION,
        "availability": "available",
        "unavailable_reason": "",
        "layer": spec.layer,
        "input_mode": mode,
        "case_aware": mode == CASE_AWARE_SUITE_TIMING_MODE,
        "episode_continuity_assumed": mode == SINGLE_EPISODE_TIMING_MODE,
        "case_metadata_fields": (
            list(CASE_AWARE_TIMING_METADATA_FIELDS)
            if mode == CASE_AWARE_SUITE_TIMING_MODE
            else []
        ),
        "case_count": len(case_summaries) if case_summaries else None,
        "case_order": case_order,
        "case_summaries": case_summaries,
        "source_schema_version": spec.schema_version,
        "scope": spec.scope,
        "total_stage_name": spec.total_stage_name,
        "evidence_path": str(evidence_path) if evidence_path is not None else None,
        "record_count": len(normalized),
        "frame_index_first": (
            normalized[0]["frame_index"]
            if mode == SINGLE_EPISODE_TIMING_MODE
            else None
        ),
        "frame_index_last": (
            normalized[-1]["frame_index"]
            if mode == SINGLE_EPISODE_TIMING_MODE
            else None
        ),
        "timestamp_first_s": (
            normalized[0]["timestamp_s"]
            if mode == SINGLE_EPISODE_TIMING_MODE
            else None
        ),
        "timestamp_last_s": (
            normalized[-1]["timestamp_s"]
            if mode == SINGLE_EPISODE_TIMING_MODE
            else None
        ),
        "pooled_across_cases": mode == CASE_AWARE_SUITE_TIMING_MODE,
        "cross_case_total_ms": None,
        "total": _distribution([record["total_ms"] for record in normalized]),
        "unattributed": _distribution(
            [record["unattributed_ms"] for record in normalized]
        ),
        "budget": _distribution([record["budget_ms"] for record in normalized]),
        "budget_violation_count": violation_count,
        "budget_violation_rate": violation_count / len(normalized),
        "error_record_count": sum(bool(record["error_type"]) for record in normalized),
        "dominant_stage": dominant_stage,
        "dominant_stage_mean_ms": (
            stages[dominant_stage]["mean_ms"] if dominant_stage is not None else None
        ),
        "stages": stages,
    }


def evaluate_stage_timing_inputs(inputs: StageTimingInputs) -> dict[str, Any]:
    """Evaluate both timing paths while preserving their nested scope boundary."""

    mode = _normalize_stage_timing_input_mode(inputs.input_mode)
    layers = {
        "main_bus": _evaluate_path(
            inputs.main_bus, spec=_MAIN_BUS_SPEC, input_mode=mode
        ),
        "control_tick": _evaluate_path(
            inputs.control_tick, spec=_CONTROL_TICK_SPEC, input_mode=mode
        ),
    }
    case_manifest_match: bool | None = None
    if mode == CASE_AWARE_SUITE_TIMING_MODE:
        available_layers = [
            layer
            for layer in layers.values()
            if layer["availability"] == "available"
        ]
        if len(available_layers) == 2:
            manifests = [
                [_case_key(item) for item in layer["case_order"]]
                for layer in available_layers
            ]
            case_manifest_match = manifests[0] == manifests[1]
            if not case_manifest_match:
                raise StageTimingValidationError(
                    "case-aware timing layer manifests differ between main_bus "
                    "and control_tick"
                )
    available_count = sum(
        layer["availability"] == "available" for layer in layers.values()
    )
    reasons = {
        name: layer["unavailable_reason"]
        for name, layer in layers.items()
        if layer["availability"] != "available"
    }
    return {
        "schema_version": STAGE_TIMING_REPORT_SCHEMA_VERSION,
        "availability": "available" if available_count else "unavailable",
        "unavailable_reason": (
            "" if available_count else "stage_timing_artifacts_unavailable"
        ),
        "offline_only": True,
        "input_mode": mode,
        "case_aware": mode == CASE_AWARE_SUITE_TIMING_MODE,
        "case_manifest_match": case_manifest_match,
        "cross_case_continuity_prohibited": mode == CASE_AWARE_SUITE_TIMING_MODE,
        "cross_case_total_ms": None,
        "cross_layer_aggregation_prohibited": True,
        "cross_layer_total_ms": None,
        "available_layer_count": available_count,
        "unavailable_layer_count": len(layers) - available_count,
        "unavailable_layer_reasons": reasons,
        "layers": layers,
    }


def stage_timing_csv_rows(summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Flatten a two-layer summary without creating a cross-layer total."""

    rows: list[dict[str, Any]] = []
    layers = summary.get("layers", {})
    if not isinstance(layers, Mapping):
        return rows
    for layer_name in ("main_bus", "control_tick"):
        layer = layers.get(layer_name, {})
        if not isinstance(layer, Mapping):
            continue
        common = {
            "layer": layer_name,
            "scope": layer.get("scope"),
            "source_schema_version": layer.get("source_schema_version"),
            "input_mode": layer.get("input_mode"),
            "case_count": layer.get("case_count"),
            "evidence_path": layer.get("evidence_path"),
            "unavailable_reason": layer.get("unavailable_reason"),
        }
        total = layer.get("total", {})
        rows.append(
            {
                **common,
                "row_type": "total",
                "stage_name": layer.get("total_stage_name"),
                **_distribution_csv_fields(total),
                "budget_violation_count": layer.get("budget_violation_count"),
                "budget_violation_rate": layer.get("budget_violation_rate"),
                "dominant_stage": layer.get("dominant_stage"),
            }
        )
        stages = layer.get("stages", {})
        if not isinstance(stages, Mapping):
            continue
        for stage_name, stage in stages.items():
            if not isinstance(stage, Mapping):
                continue
            rows.append(
                {
                    **common,
                    "row_type": "stage",
                    "stage_name": stage_name,
                    **_distribution_csv_fields(stage),
                    "available_count": stage.get("available_count"),
                    "not_applicable_count": stage.get("not_applicable_count"),
                    "error_count": stage.get("error_count"),
                    "dominant_stage": layer.get("dominant_stage"),
                }
            )
    return [{field: row.get(field) for field in _CSV_FIELDS} for row in rows]


def render_stage_timing_markdown(
    summary: Mapping[str, Any],
    *,
    title: str,
    plot_name: str,
) -> str:
    """Render the timing summary as a Chinese engineering report."""

    lines = [
        f"# {title}",
        "",
        "D6 只离线消费已经落盘的分阶段计时 JSONL，不连接 AirSim，也不参与关联、分配、降级、末端锁定或导引控制。旧产物缺少计时文件时显示为 `unavailable`，不补零。",
        "",
        f"![分阶段延迟]({plot_name})",
        "",
        "main bus 是 control tick 的内部组成部分，两层同名或嵌套耗时禁止相加；本报告不发布跨层总延迟。",
        f"输入模式：`{_format_value(summary.get('input_mode'))}`。case-aware suite 仅按 case 池化耗时分布，不把多个 episode 拼成连续时间轴，`cross_case_total_ms` 固定为 `null`。",
        "",
    ]
    layers = summary.get("layers", {})
    for layer_name, heading in (
        ("main_bus", "Main Episode Bus 内层"),
        ("control_tick", "SimpleFlight Control Tick 外层"),
    ):
        layer = layers.get(layer_name, {}) if isinstance(layers, Mapping) else {}
        if not isinstance(layer, Mapping):
            layer = {}
        lines.extend([f"## {heading}", ""])
        if layer.get("availability") != "available":
            lines.extend(
                [
                    f"- 状态：`unavailable`；原因：`{_format_value(layer.get('unavailable_reason'))}`。",
                    f"- 证据路径：`{_format_value(layer.get('evidence_path'))}`。",
                    "",
                ]
            )
            continue
        total = layer.get("total", {})
        budget = layer.get("budget", {})
        lines.extend(
            [
                f"- schema/scope：`{layer.get('source_schema_version')}` / `{layer.get('scope')}`。",
                f"- 输入模式：`{layer.get('input_mode')}`；case count：`{_format_value(layer.get('case_count'))}`；跨 case 连续性：`{str(bool(layer.get('episode_continuity_assumed'))).lower()}`。",
                f"- 帧数：`{layer.get('record_count')}`；总延迟 mean/P95/max：`{_format_value(_mapping_get(total, 'mean_ms'))}/{_format_value(_mapping_get(total, 'p95_ms'))}/{_format_value(_mapping_get(total, 'max_ms'))}` ms。",
                f"- 预算 mean：`{_format_value(_mapping_get(budget, 'mean_ms'))}` ms；违例：`{layer.get('budget_violation_count')}/{layer.get('record_count')}`，比例 `{_format_value(layer.get('budget_violation_rate'))}`。",
                f"- 主导阶段：`{_format_value(layer.get('dominant_stage'))}`，mean `{_format_value(layer.get('dominant_stage_mean_ms'))}` ms；error records：`{layer.get('error_record_count')}`。",
                "",
                "| 阶段 | Samples | Mean ms | P95 ms | Max ms | Available | N/A | Error |",
                "|---|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        stages = layer.get("stages", {})
        if isinstance(stages, Mapping):
            for stage_name, stage in stages.items():
                if not isinstance(stage, Mapping):
                    continue
                lines.append(
                    f"| `{stage_name}` | {_format_value(stage.get('sample_count'))} | {_format_value(stage.get('mean_ms'))} | {_format_value(stage.get('p95_ms'))} | {_format_value(stage.get('max_ms'))} | {_format_value(stage.get('available_count'))} | {_format_value(stage.get('not_applicable_count'))} | {_format_value(stage.get('error_count'))} |"
                )
        lines.append("")
    lines.extend(
        [
            "## 结论边界",
            "",
            "- 本报告关闭的是阶段延迟可观测性与离线校验能力，不证明任何阶段已经满足性能预算。",
            "- 非法 schema、负数、非有限值、状态冲突、总和冲突、预算标志冲突以及重复/倒序帧会直接校验失败，不进入统计。",
            "- 真实 AirSim 同配置多 seed 的 100 ms 预算达标与跨提交性能趋势仍需后续实测。",
            "",
        ]
    )
    return "\n".join(lines)


def _evaluate_path(
    path: str | Path | None,
    *,
    spec: _TimingScopeSpec,
    input_mode: str,
) -> dict[str, Any]:
    if path is None:
        return _unavailable_layer_summary(
            spec,
            reason="stage_timing_artifact_not_provided",
            evidence_path=None,
            input_mode=input_mode,
        )
    source_path = Path(path)
    if not source_path.exists():
        return _unavailable_layer_summary(
            spec,
            reason="stage_timing_artifact_missing",
            evidence_path=source_path,
            input_mode=input_mode,
        )
    records = load_stage_timing_jsonl(
        source_path,
        expected_layer=spec.layer,
        input_mode=input_mode,
    )
    return summarize_stage_timing_records(
        records,
        expected_layer=spec.layer,
        evidence_path=source_path,
        input_mode=input_mode,
    )


def _unavailable_layer_summary(
    spec: _TimingScopeSpec,
    *,
    reason: str,
    evidence_path: str | Path | None,
    input_mode: str = SINGLE_EPISODE_TIMING_MODE,
) -> dict[str, Any]:
    return {
        "schema_version": STAGE_TIMING_SCOPE_SUMMARY_SCHEMA_VERSION,
        "availability": "unavailable",
        "unavailable_reason": reason,
        "layer": spec.layer,
        "input_mode": input_mode,
        "case_aware": input_mode == CASE_AWARE_SUITE_TIMING_MODE,
        "episode_continuity_assumed": input_mode == SINGLE_EPISODE_TIMING_MODE,
        "case_metadata_fields": (
            list(CASE_AWARE_TIMING_METADATA_FIELDS)
            if input_mode == CASE_AWARE_SUITE_TIMING_MODE
            else []
        ),
        "case_count": None,
        "case_order": [],
        "case_summaries": [],
        "source_schema_version": spec.schema_version,
        "scope": spec.scope,
        "total_stage_name": spec.total_stage_name,
        "evidence_path": str(evidence_path) if evidence_path is not None else None,
        "record_count": 0,
        "frame_index_first": None,
        "frame_index_last": None,
        "timestamp_first_s": None,
        "timestamp_last_s": None,
        "pooled_across_cases": input_mode == CASE_AWARE_SUITE_TIMING_MODE,
        "cross_case_total_ms": None,
        "total": _distribution([]),
        "unattributed": _distribution([]),
        "budget": _distribution([]),
        "budget_violation_count": None,
        "budget_violation_rate": None,
        "error_record_count": None,
        "dominant_stage": None,
        "dominant_stage_mean_ms": None,
        "stages": {},
    }


def _validate_record_order(records: Sequence[Mapping[str, Any]], *, layer: str) -> None:
    previous_frame: int | None = None
    previous_timestamp: float | None = None
    for position, record in enumerate(records, start=1):
        frame_index = int(record["frame_index"])
        timestamp_s = float(record["timestamp_s"])
        if previous_frame is not None and frame_index <= previous_frame:
            raise StageTimingValidationError(
                f"{layer} record {position}: duplicate or out-of-order frame_index"
            )
        if previous_timestamp is not None and timestamp_s <= previous_timestamp:
            raise StageTimingValidationError(
                f"{layer} record {position}: duplicate or out-of-order timestamp_s"
            )
        previous_frame = frame_index
        previous_timestamp = timestamp_s


def _validate_timing_record_order(
    records: Sequence[Mapping[str, Any]],
    *,
    layer: str,
    input_mode: str,
) -> None:
    if input_mode == SINGLE_EPISODE_TIMING_MODE:
        _validate_record_order(records, layer=layer)
        return

    completed_cases: set[tuple[str, str, str, int]] = set()
    metadata_by_case_id: dict[str, tuple[str, str, str, int]] = {}
    current_case: tuple[str, str, str, int] | None = None
    previous_frame: int | None = None
    previous_timestamp: float | None = None
    for position, record in enumerate(records, start=1):
        case_key = _case_key(record)
        case_id = case_key[0]
        previous_metadata = metadata_by_case_id.setdefault(case_id, case_key)
        if previous_metadata != case_key:
            raise StageTimingValidationError(
                f"{layer} record {position}: conflicting metadata for case_id "
                f"{case_id!r}"
            )
        if case_key != current_case:
            if current_case is not None:
                completed_cases.add(current_case)
            if case_key in completed_cases:
                raise StageTimingValidationError(
                    f"{layer} record {position}: case metadata reappeared after case switch"
                )
            current_case = case_key
            previous_frame = None
            previous_timestamp = None

        frame_index = int(record["frame_index"])
        timestamp_s = float(record["timestamp_s"])
        if previous_frame is not None and frame_index <= previous_frame:
            raise StageTimingValidationError(
                f"{layer} record {position}: duplicate or out-of-order frame_index "
                "within case"
            )
        if previous_timestamp is not None and timestamp_s <= previous_timestamp:
            raise StageTimingValidationError(
                f"{layer} record {position}: duplicate or out-of-order timestamp_s "
                "within case"
            )
        previous_frame = frame_index
        previous_timestamp = timestamp_s


def _case_key(record: Mapping[str, Any]) -> tuple[str, str, str, int]:
    return (
        str(record["case_id"]),
        str(record["family"]),
        str(record["profile"]),
        int(record["seed"]),
    )


def _case_metadata(record: Mapping[str, Any]) -> dict[str, Any]:
    return {field: record[field] for field in CASE_AWARE_TIMING_METADATA_FIELDS}


def _case_timing_summaries(
    records: Sequence[Mapping[str, Any]],
    *,
    spec: _TimingScopeSpec,
) -> list[dict[str, Any]]:
    groups: list[list[Mapping[str, Any]]] = []
    current_key: tuple[str, str, str, int] | None = None
    for record in records:
        key = _case_key(record)
        if key != current_key:
            groups.append([])
            current_key = key
        groups[-1].append(record)

    result: list[dict[str, Any]] = []
    for group in groups:
        episode_records = [
            {field: record[field] for field in _REQUIRED_RECORD_FIELDS}
            for record in group
        ]
        episode = summarize_stage_timing_records(
            episode_records,
            expected_layer=spec.layer,
            input_mode=SINGLE_EPISODE_TIMING_MODE,
        )
        result.append(
            {
                "case": _case_metadata(group[0]),
                "record_count": episode["record_count"],
                "frame_index_first": episode["frame_index_first"],
                "frame_index_last": episode["frame_index_last"],
                "timestamp_first_s": episode["timestamp_first_s"],
                "timestamp_last_s": episode["timestamp_last_s"],
                "total": episode["total"],
                "budget_violation_count": episode["budget_violation_count"],
                "budget_violation_rate": episode["budget_violation_rate"],
                "error_record_count": episode["error_record_count"],
                "dominant_stage": episode["dominant_stage"],
            }
        )
    return result


def _scope_spec(layer: str) -> _TimingScopeSpec:
    try:
        return _SCOPE_SPECS[layer]
    except KeyError as exc:
        raise ValueError(
            f"expected_layer must be one of {sorted(_SCOPE_SPECS)}, got {layer!r}"
        ) from exc


def _finite_number(value: Any, *, name: str, prefix: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StageTimingValidationError(f"{prefix}: {name} must be numeric")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise StageTimingValidationError(f"{prefix}: {name} must be finite")
    return normalized


def _finite_nonnegative(value: Any, *, name: str, prefix: str) -> float:
    normalized = _finite_number(value, name=name, prefix=prefix)
    if normalized < 0.0:
        raise StageTimingValidationError(f"{prefix}: {name} must be nonnegative")
    return normalized


def _integer(value: Any, *, name: str, prefix: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise StageTimingValidationError(f"{prefix}: {name} must be an integer")
    return int(value)


def _same_float(left: float, right: float) -> bool:
    return math.isclose(float(left), float(right), rel_tol=1e-9, abs_tol=1e-6)


def _distribution(values: Sequence[float]) -> dict[str, Any]:
    clean = sorted(float(value) for value in values)
    if not clean:
        return {
            "availability": "unavailable",
            "sample_count": 0,
            "mean_ms": None,
            "p95_ms": None,
            "max_ms": None,
        }
    return {
        "availability": "available",
        "sample_count": len(clean),
        "mean_ms": sum(clean) / len(clean),
        "p95_ms": _percentile(clean, 0.95),
        "max_ms": clean[-1],
    }


def _percentile(values: Sequence[float], quantile: float) -> float:
    if len(values) == 1:
        return float(values[0])
    position = (len(values) - 1) * quantile
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return float(values[lower])
    weight = position - lower
    return float(values[lower] * (1.0 - weight) + values[upper] * weight)


def _distribution_csv_fields(value: Any) -> dict[str, Any]:
    distribution = value if isinstance(value, Mapping) else {}
    return {
        "availability": distribution.get("availability", "unavailable"),
        "sample_count": distribution.get("sample_count", 0),
        "mean_ms": distribution.get("mean_ms"),
        "p95_ms": distribution.get("p95_ms"),
        "max_ms": distribution.get("max_ms"),
    }


def _mapping_get(value: Any, key: str) -> Any:
    return value.get(key) if isinstance(value, Mapping) else None


def _format_value(value: Any) -> str:
    if value is None or value == "":
        return "NA"
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value)


def _write_stage_timing_plot(summary: Mapping[str, Any], path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    cjk_font_path = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
    if cjk_font_path.exists():
        font_manager.fontManager.addfont(str(cjk_font_path))
        family = font_manager.FontProperties(fname=str(cjk_font_path)).get_name()
    else:
        family = "DejaVu Sans"
    plt.rcParams["font.sans-serif"] = [family, "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    fig, axes = plt.subplots(2, 1, figsize=(13.0, 9.0))
    layers = summary.get("layers", {})
    for axis, (layer_name, title) in zip(
        axes,
        (
            ("main_bus", "Main Episode Bus 内层阶段延迟"),
            ("control_tick", "SimpleFlight Control Tick 外层阶段延迟"),
        ),
    ):
        layer = layers.get(layer_name, {}) if isinstance(layers, Mapping) else {}
        if not isinstance(layer, Mapping) or layer.get("availability") != "available":
            axis.text(0.5, 0.5, "计时证据不可用", ha="center", va="center")
            axis.set_xticks([])
            axis.set_yticks([])
            axis.set_title(title)
            continue
        stages = layer.get("stages", {})
        stage_names = list(stages) if isinstance(stages, Mapping) else []
        means = [float(stages[name]["mean_ms"]) for name in stage_names]
        p95s = [float(stages[name]["p95_ms"]) for name in stage_names]
        positions = list(range(len(stage_names)))
        axis.bar(
            [position - 0.2 for position in positions],
            means,
            width=0.4,
            label="平均值",
            color="#356859",
        )
        axis.bar(
            [position + 0.2 for position in positions],
            p95s,
            width=0.4,
            label="第95百分位",
            color="#d97706",
        )
        budget_mean = _mapping_get(layer.get("budget"), "mean_ms")
        if budget_mean is not None:
            axis.axhline(
                float(budget_mean),
                color="#b91c1c",
                linestyle="--",
                linewidth=1.2,
                label="平均预算",
            )
        axis.set_xticks(positions, stage_names, rotation=20, ha="right")
        axis.set_ylabel("耗时（毫秒）")
        axis.set_title(title)
        axis.grid(axis="y", alpha=0.25)
        axis.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


_CSV_FIELDS = (
    "layer",
    "scope",
    "source_schema_version",
    "input_mode",
    "case_count",
    "row_type",
    "stage_name",
    "availability",
    "sample_count",
    "mean_ms",
    "p95_ms",
    "max_ms",
    "available_count",
    "not_applicable_count",
    "error_count",
    "budget_violation_count",
    "budget_violation_rate",
    "dominant_stage",
    "evidence_path",
    "unavailable_reason",
)
