from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
import matplotlib.pyplot as plt

from dual_optical_online_benchmark import gate_confirmation_reporting as reporting
from dual_optical_online_benchmark.gate_confirmation_reporting import (
    evaluate_variants,
    generate_gate_confirmation_report,
    main,
    summarize_rows,
)


VARIANTS = {
    "baseline": {
        "variant_id": "baseline",
        "label_cn": "严格基线",
        "selection_rule": "none",
        "diagnostic_only": False,
    },
    "gate_wide": {
        "variant_id": "gate_wide",
        "label_cn": "放宽初筛",
        "selection_rule": "candidate",
        "diagnostic_only": False,
    },
    "confirm_early": {
        "variant_id": "confirm_early",
        "label_cn": "提前确认",
        "selection_rule": "confirmation",
        "diagnostic_only": False,
    },
    "direct_1of1": {
        "variant_id": "direct_1of1",
        "label_cn": "单圈直接确认",
        "selection_rule": "confirmation",
        "diagnostic_only": True,
    },
}


def _row(
    *,
    variant: str = "baseline",
    split: str = "validation",
    level: str = "clean",
    seed: int = 1,
    revolution: int = 1,
    target_count: int = 20,
    matches: int = 10,
    correct: int = 9,
    unique: int = 9,
    opportunities: int = 20,
    retained: int = 18,
    edges: int = 100,
    first_confirmation: float | None = 2.0,
    switches: int = 0,
    violations: int = 0,
    latency: float = 50.0,
    gpu_peak_memory_mb: float = 256.0,
    gpu_peak_memory_available: bool = True,
) -> dict[str, object]:
    return {
        "variant_id": variant,
        "target_count": target_count,
        "seed": seed,
        "split": split,
        "level": level,
        "revolution": revolution,
        "match_count": matches,
        "correct_count": correct,
        "false_count": matches - correct,
        "unique_correct_targets": unique,
        "candidate_opportunities": opportunities,
        "candidate_true_retained": retained,
        "candidate_edge_count": edges,
        "candidate_build_ms": 10.0,
        "inference_ms": 20.0,
        "assignment_ms": 5.0,
        "end_to_end_ms": latency,
        "first_confirmation_s": first_confirmation,
        "relation_switch_count": switches,
        "one_to_one_violations": violations,
        "gpu_peak_memory_mb": gpu_peak_memory_mb,
        "gpu_peak_memory_available": gpu_peak_memory_available,
        "gpu_peak_memory_source": (
            "cuda_peak" if gpu_peak_memory_available else "not_recorded"
        ),
    }


def test_weighted_and_macro_averages_are_kept_separate() -> None:
    rows = [
        _row(seed=1, matches=10, correct=5, unique=5, opportunities=20, retained=10),
        _row(seed=2, matches=2, correct=2, unique=2, opportunities=4, retained=4),
    ]

    per_seed, summary = summarize_rows(rows, VARIANTS)

    assert len(per_seed) == 2
    result = summary[0]
    assert result["association_precision"] == pytest.approx(7 / 12)
    assert result["macro_association_precision"] == pytest.approx((0.5 + 1.0) / 2)
    assert result["coverage"] == pytest.approx(7 / 40)
    assert result["macro_coverage"] == pytest.approx((5 / 20 + 2 / 20) / 2)
    assert result["candidate_true_retention_rate"] == pytest.approx(14 / 24)
    assert result["macro_candidate_true_retention_rate"] == pytest.approx(0.75)


def test_empty_output_is_counted_without_division_error() -> None:
    rows = [
        _row(
            matches=0,
            correct=0,
            unique=0,
            first_confirmation=None,
            retained=0,
            opportunities=0,
        )
    ]

    per_seed, summary = summarize_rows(rows, VARIANTS)

    assert per_seed[0]["association_precision"] == 0.0
    assert summary[0]["coverage"] == 0.0
    assert summary[0]["candidate_true_retention_rate"] == 0.0
    assert summary[0]["first_confirmation_s"] is None
    assert summary[0]["no_output_revolutions"] == 1
    assert summary[0]["no_output_rate"] == 1.0


def test_explicit_unrecorded_gpu_peak_is_not_inferred_as_zero() -> None:
    rows = [_row(gpu_peak_memory_mb=0.0, gpu_peak_memory_available=False)]

    per_seed, summary = summarize_rows(rows, VARIANTS)

    assert per_seed[0]["gpu_peak_memory_available"] is False
    assert per_seed[0]["gpu_peak_memory_mb"] is None
    assert summary[0]["gpu_peak_memory_available"] is False
    assert summary[0]["gpu_peak_memory_mb"] is None


def _selection_summary(
    variant: str,
    level: str,
    *,
    precision: float,
    coverage: float,
    retention: float,
    switches: float = 0.0,
    violations: int = 0,
    latency: float = 50.0,
) -> dict[str, object]:
    return {
        "variant_id": variant,
        "target_count": 20,
        "split": "validation",
        "level": level,
        "association_precision": precision,
        "coverage": coverage,
        "candidate_true_retention_rate": retention,
        "relation_switch_rate": switches,
        "one_to_one_violations": violations,
        "end_to_end_p95_ms": latency,
    }


def test_selection_fails_closed_and_excludes_direct_confirmation() -> None:
    summary = []
    for level in ("clean", "light"):
        summary.extend(
            [
                _selection_summary(
                    "baseline", level, precision=0.90, coverage=0.50, retention=0.95
                ),
                _selection_summary(
                    "gate_wide", level, precision=0.87, coverage=0.54, retention=0.98
                ),
                _selection_summary(
                    "confirm_early",
                    level,
                    precision=0.89,
                    coverage=0.54,
                    retention=0.95,
                ),
                _selection_summary(
                    "direct_1of1",
                    level,
                    precision=0.99,
                    coverage=0.99,
                    retention=1.0,
                ),
            ]
        )

    selection = evaluate_variants(summary, VARIANTS, "baseline")

    assert selection["candidate_strategy"]["baseline_retained"] is True
    assert selection["candidate_strategy"]["selected_variant_id"] == "baseline"
    assert selection["confirmation_strategy"]["baseline_retained"] is True
    assert selection["confirmation_strategy"]["selected_variant_id"] == "baseline"
    direct = next(
        item
        for item in selection["confirmation_strategy"]["decisions"]
        if item["variant_id"] == "direct_1of1"
    )
    assert direct["eligible"] is False
    assert direct["reason_codes"] == ["diagnostic_only_direct_1of1"]
    assert selection["test_used_for_selection"] is False


def test_validation_rules_select_passing_candidate_and_confirmation() -> None:
    summary = []
    for level in ("clean", "light"):
        summary.extend(
            [
                _selection_summary(
                    "baseline", level, precision=0.90, coverage=0.50, retention=0.94
                ),
                _selection_summary(
                    "gate_wide",
                    level,
                    precision=0.89,
                    coverage=0.52 if level == "clean" else 0.53,
                    retention=0.96,
                ),
                _selection_summary(
                    "confirm_early",
                    level,
                    precision=0.89,
                    coverage=0.56,
                    retention=0.94,
                    switches=0.005,
                    latency=900.0,
                ),
            ]
        )
    # A strong test-only row must not change the validation decision.
    summary.append(
        {
            **_selection_summary(
                "baseline", "clean", precision=0.0, coverage=0.0, retention=0.0
            ),
            "split": "test",
        }
    )

    selection = evaluate_variants(summary, VARIANTS, "baseline")

    assert selection["candidate_strategy"]["selected_variant_id"] == "gate_wide"
    assert selection["candidate_strategy"]["baseline_retained"] is False
    assert selection["confirmation_strategy"]["selected_variant_id"] == "confirm_early"
    assert selection["confirmation_strategy"]["baseline_retained"] is False


def test_per_level_precision_gate_rejects_mean_masked_drop() -> None:
    summary = []
    for level in ("clean", "light"):
        baseline_precision = 0.80
        masked_precision = 0.913 if level == "clean" else 0.704
        summary.extend(
            [
                _selection_summary(
                    "baseline",
                    level,
                    precision=baseline_precision,
                    coverage=0.50,
                    retention=0.95,
                ),
                _selection_summary(
                    "gate_wide",
                    level,
                    precision=masked_precision,
                    coverage=0.55,
                    retention=0.97,
                ),
                _selection_summary(
                    "confirm_early",
                    level,
                    precision=masked_precision,
                    coverage=0.56,
                    retention=0.95,
                    switches=0.005,
                ),
            ]
        )

    selection = evaluate_variants(summary, VARIANTS, "baseline")

    for family_name, variant_id in (
        ("candidate_strategy", "gate_wide"),
        ("confirmation_strategy", "confirm_early"),
    ):
        family = selection[family_name]
        assert family["baseline_retained"] is True
        decision = next(
            item for item in family["decisions"] if item["variant_id"] == variant_id
        )
        assert decision["eligible"] is False
        assert decision["deltas"]["clean_precision_delta"] == pytest.approx(0.113)
        assert decision["deltas"]["light_precision_delta"] == pytest.approx(-0.096)
        assert decision["deltas"]["mean_precision_delta"] == pytest.approx(0.0085)
        assert decision["reason_codes"] == ["light_precision_drop_exceeds_2pp"]


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _experiment_rows() -> list[dict[str, object]]:
    rows = []
    for split in ("validation", "test"):
        for target_count in (20, 40, 60):
            for variant in VARIANTS:
                for level in ("clean", "light"):
                    for seed in (1, 2):
                        for revolution in (1, 2):
                            coverage = 9
                            if variant in {"confirm_early", "direct_1of1"}:
                                coverage = 11
                            rows.append(
                                _row(
                                    variant=variant,
                                    split=split if target_count == 20 else "offline",
                                    level=level,
                                    seed=seed,
                                    revolution=revolution,
                                    target_count=target_count,
                                    matches=12,
                                    correct=11,
                                    unique=min(coverage, target_count),
                                    retained=20,
                                    opportunities=20,
                                    edges=120 if variant == "baseline" else 180,
                                    first_confirmation=2.0 if variant == "baseline" else 1.0,
                                    gpu_peak_memory_mb=0.0,
                                    gpu_peak_memory_available=False,
                                )
                            )
    # The loop emits duplicate offline rows once for each requested split.
    unique = {}
    for row in rows:
        key = (
            row["variant_id"],
            row["target_count"],
            row["split"],
            row["level"],
            row["seed"],
            row["revolution"],
        )
        unique[key] = row
    return list(unique.values())


def test_scale_plot_uses_shared_variants_and_chinese_labels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    preferred = {
        "baseline_strict": "8σ初筛和三圈两次确认",
        "baseline_early": "第二圈即可重复确认",
        "baseline_graded_p08_m01": "分级确认0.8和0.10",
    }
    rows = []
    for count in (20, 40, 60):
        for variant_id, label in preferred.items():
            for level in ("clean", "light"):
                rows.append(
                    {
                        "variant_id": variant_id,
                        "variant_label_cn": label,
                        "target_count": count,
                        "split": "test" if count == 20 else "offline",
                        "level": level,
                        "association_precision": 0.8,
                        "coverage": 0.4,
                    }
                )
    for level in ("clean", "light"):
        rows.append(
            {
                "variant_id": "moderate_strict",
                "variant_label_cn": "仅20目标候选策略",
                "target_count": 20,
                "split": "test",
                "level": level,
                "association_precision": 0.9,
                "coverage": 0.5,
            }
        )

    captured: dict[str, object] = {}

    def capture(_path: Path, figure: plt.Figure) -> None:
        captured["figure"] = figure

    monkeypatch.setattr(reporting, "_save_figure", capture)
    reporting._plot_scale(rows, tmp_path / "scale.png")

    figure = captured["figure"]
    assert isinstance(figure, plt.Figure)
    axes = figure.axes
    assert [axis.get_xlabel() for axis in axes] == ["目标数量", "目标数量"]
    assert axes[0].get_title() == "不同目标规模的关联精度"
    assert axes[1].get_title() == "不同目标规模的覆盖度"
    assert {line.get_label() for line in axes[0].lines} == set(preferred.values())
    assert "仅20目标候选策略" not in {
        line.get_label() for line in axes[0].lines
    }
    plt.close(figure)


def test_cli_generates_csv_json_chinese_report_and_four_pngs(tmp_path: Path) -> None:
    rows = _experiment_rows()
    json_rows = [row for index, row in enumerate(rows) if index % 2 == 0]
    csv_rows = [row for index, row in enumerate(rows) if index % 2 == 1]
    json_path = tmp_path / "scores.json"
    csv_path = tmp_path / "scores.csv"
    _write_json(json_path, {"rows": json_rows})
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(csv_rows[0]))
        writer.writeheader()
        writer.writerows(csv_rows)
    manifest_path = tmp_path / "manifest.json"
    _write_json(
        manifest_path,
        {
            "baseline_variant_id": "baseline",
            "variants": list(VARIANTS.values()),
            "inputs": [{"path": json_path.name}, {"path": csv_path.name}],
        },
    )
    output_dir = tmp_path / "report"

    assert main(
        [
            "--manifest",
            str(manifest_path),
            "--output-dir",
            str(output_dir),
        ]
    ) == 0

    expected = {
        "per_seed.csv",
        "summary.csv",
        "metrics.json",
        "GATE_CONFIRMATION_ABLATION_REPORT_CN.md",
        "candidate_retention_edges.png",
        "precision_coverage.png",
        "confirmation_timing_no_output.png",
        "scale_20_40_60.png",
    }
    assert expected == {path.name for path in output_dir.iterdir()}
    for filename in expected:
        assert (output_dir / filename).stat().st_size > 0
    metrics = json.loads((output_dir / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["test_used_for_selection"] is False
    assert metrics["selection"]["test_used_for_selection"] is False
    assert metrics["offline_review_target_counts"] == [40, 60]
    report = (output_dir / "GATE_CONFIRMATION_ABLATION_REPORT_CN.md").read_text(
        encoding="utf-8"
    )
    assert "单圈直接确认" in report
    assert "只用于诊断" in report
    assert "测试集此前已经" in report
    assert "正式定型或正式采用" in report
    assert "40目标离线复核" in report
    assert "60目标离线复核" in report
    assert "未记录" in report
    assert "0MB" not in report
    assert all(
        row["gpu_peak_memory_available"] is False
        and row["gpu_peak_memory_mb"] is None
        for row in metrics["summary"]
    )
