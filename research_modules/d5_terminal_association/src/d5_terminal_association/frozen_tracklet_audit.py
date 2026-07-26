"""Reproducible audit entrypoint for one frozen D5 tracklet GNN bundle."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from .tracklet_dataset import sha256_file
from .tracklet_heldout_evaluation import (
    HELDOUT_CONFIG_FILENAME,
    HELDOUT_EVALUATION_FILENAME,
    HELDOUT_MANIFEST_FILENAME,
    HeldoutEvaluationPolicy,
    evaluate_heldout_development_bundle,
)
from .tracklet_model_bundle import (
    CHECKSUMS_FILENAME,
    MANIFEST_FILENAME,
    WEIGHTS_FILENAME,
    load_tracklet_model_bundle,
)
from .tracklet_paired_shadow import (
    PAIRED_SHADOW_LINEAGE_FILENAME,
    PAIRED_SHADOW_MARKDOWN_FILENAME,
    PAIRED_SHADOW_REPORT_FILENAME,
    PairedShadowInputSpec,
    run_tracklet_paired_shadow,
)


FROZEN_AUDIT_REFERENCE_SCHEMA_VERSION = "d5.frozen-tracklet-audit-reference.v1"
FROZEN_AUDIT_SUMMARY_SCHEMA_VERSION = "d5.frozen-tracklet-audit-summary.v1"
SUMMARY_FILENAME = "frozen_audit_summary.json"
SUMMARY_MARKDOWN_FILENAME = "FROZEN_GNN_AUDIT_REPORT_CN.md"
SUMMARY_CHECKSUMS_FILENAME = "SHA256SUMS"
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class FrozenTrackletAuditError(ValueError):
    """Stable validation error for the frozen audit entrypoint."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code)


def validate_frozen_reference(
    reference_path: str | Path,
    *,
    repository_root: str | Path,
) -> Mapping[str, Any]:
    """Validate one tracked reference against the ignored local bundle."""

    reference_file = Path(reference_path).resolve()
    root = Path(repository_root).resolve()
    reference = _read_json(reference_file)
    if reference.get("schema_version") != FROZEN_AUDIT_REFERENCE_SCHEMA_VERSION:
        _fail("reference_schema_mismatch", str(reference.get("schema_version")))
    relative = Path(str(reference.get("bundle_relative_path", "")))
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        _fail("bundle_relative_path_invalid", str(relative))
    bundle = (root / relative).resolve()
    try:
        bundle.relative_to(root)
    except ValueError:
        _fail("bundle_path_escape", str(bundle))
    expected = reference.get("expected_hashes")
    if not isinstance(expected, Mapping):
        _fail("expected_hashes_missing", str(reference_file))
    files = {
        "manifest_sha256": bundle / MANIFEST_FILENAME,
        "weights_sha256": bundle / WEIGHTS_FILENAME,
        "checksums_sha256": bundle / CHECKSUMS_FILENAME,
    }
    actual = {name: sha256_file(path) for name, path in files.items()}
    for name, digest in actual.items():
        expected_digest = str(expected.get(name, "")).strip().lower()
        if not _SHA256_PATTERN.fullmatch(expected_digest):
            _fail("reference_hash_invalid", name)
        if digest != expected_digest:
            _fail(f"{name}_mismatch", f"expected={expected_digest};actual={digest}")
    scorer = load_tracklet_model_bundle(bundle)
    admission = dict(scorer.manifest["admission"])
    if (
        admission.get("status") != "development_only_fail_closed"
        or admission.get("default_model") is not False
        or admission.get("g1_assist_eligible") is not False
    ):
        _fail("frozen_bundle_authority_invalid", str(admission))
    return {
        "reference_path": str(reference_file),
        "reference_sha256": sha256_file(reference_file),
        "bundle_dir": str(bundle),
        "model_id": str(reference.get("model_id", "")),
        "manifest_sha256": scorer.bundle_manifest_sha256,
        "weights_sha256": scorer.bundle_weights_sha256,
        "checksums_sha256": actual["checksums_sha256"],
        "admission": admission,
        "strict_load_passed": True,
    }


def run_frozen_tracklet_audit(
    reference_path: str | Path,
    heldout_corpus_dir: str | Path,
    output_dir: str | Path,
    *,
    repository_root: str | Path,
    evaluated_at_utc: str,
    device: str = "cpu",
    latency_repeats: int = 3,
    require_full_profile: bool = True,
) -> Mapping[str, Any]:
    """Run held-out inference and paired shadow against exactly one bundle."""

    destination = Path(output_dir).resolve()
    if destination.exists():
        _fail("audit_destination_exists", str(destination))
    timestamp = str(evaluated_at_utc).strip()
    if not timestamp:
        _fail("evaluated_at_missing", "evaluated_at_utc must be non-empty")
    frozen = validate_frozen_reference(
        reference_path,
        repository_root=repository_root,
    )
    corpus_root = Path(heldout_corpus_dir).resolve()
    corpus_manifest_path = corpus_root / HELDOUT_MANIFEST_FILENAME
    corpus_config_path = (
        corpus_root / "heldout_dataset" / HELDOUT_CONFIG_FILENAME
    )
    corpus_manifest = _read_json(corpus_manifest_path)
    destination.mkdir(parents=True)
    heldout_output = destination / "heldout_evaluation"
    paired_output = destination / "paired_shadow"
    try:
        heldout = evaluate_heldout_development_bundle(
            corpus_root,
            frozen["bundle_dir"],
            heldout_output,
            evaluated_at_utc=timestamp,
            policy=HeldoutEvaluationPolicy(
                device=device,
                latency_repeats=latency_repeats,
            ),
            require_full_profile=require_full_profile,
        )
        heldout_report_path = heldout_output / HELDOUT_EVALUATION_FILENAME
        paired = run_tracklet_paired_shadow(
            PairedShadowInputSpec(
                heldout_corpus_dir=corpus_root,
                bundle_dir=frozen["bundle_dir"],
                heldout_report_path=heldout_report_path,
                output_dir=paired_output,
                expected_corpus_manifest_sha256=sha256_file(
                    corpus_manifest_path
                ),
                expected_corpus_content_sha256=str(
                    corpus_manifest["content_sha256"]
                ),
                expected_corpus_config_sha256=sha256_file(corpus_config_path),
                expected_bundle_manifest_sha256=str(
                    frozen["manifest_sha256"]
                ),
                expected_bundle_weights_sha256=str(frozen["weights_sha256"]),
                expected_bundle_checksums_sha256=str(
                    frozen["checksums_sha256"]
                ),
                expected_heldout_report_sha256=sha256_file(
                    heldout_report_path
                ),
                expected_heldout_report_content_sha256=str(
                    heldout["content_sha256"]
                ),
                evaluated_at_utc=timestamp,
                device=device,
                require_full_profile=require_full_profile,
            )
        )
        summary = _summary(
            frozen,
            heldout,
            paired,
            evaluated_at_utc=timestamp,
            heldout_report_path=heldout_report_path,
            paired_output=paired_output,
        )
        _write_json(destination / SUMMARY_FILENAME, summary)
        (destination / SUMMARY_MARKDOWN_FILENAME).write_text(
            _render_summary(summary),
            encoding="utf-8",
        )
        _write_summary_checksums(destination)
        return summary
    except Exception:
        # Preserve evidence already written by fail-closed child evaluators.
        raise


def _summary(
    frozen: Mapping[str, Any],
    heldout: Mapping[str, Any],
    paired: Mapping[str, Any],
    *,
    evaluated_at_utc: str,
    heldout_report_path: Path,
    paired_output: Path,
) -> dict[str, Any]:
    if (
        paired["heldout_lineage_binding"]["bundle_manifest_sha256"]
        != frozen["manifest_sha256"]
        or paired["heldout_lineage_binding"]["bundle_weights_sha256"]
        != frozen["weights_sha256"]
    ):
        _fail("paired_bundle_lineage_mismatch", str(frozen["model_id"]))
    overall = paired["overall"]
    return {
        "schema_version": FROZEN_AUDIT_SUMMARY_SCHEMA_VERSION,
        "evaluated_at_utc": evaluated_at_utc,
        "status": paired["status"],
        "model": dict(frozen),
        "catalog": dict(paired["totals"]),
        "heldout": {
            "status": heldout["heldout_assessment"]["status"],
            "content_sha256": heldout["content_sha256"],
            "report_file_sha256": sha256_file(heldout_report_path),
        },
        "paired_shadow": {
            "status": paired["paired_shadow_assessment"]["status"],
            "content_sha256": paired["content_sha256"],
            "report_file_sha256": sha256_file(
                paired_output / PAIRED_SHADOW_REPORT_FILENAME
            ),
            "markdown_sha256": sha256_file(
                paired_output / PAIRED_SHADOW_MARKDOWN_FILENAME
            ),
            "lineage_sha256": sha256_file(
                paired_output / PAIRED_SHADOW_LINEAGE_FILENAME
            ),
            "candidate_recall": overall["candidate_recall"],
            "rule_edge_f1": overall["control"]["edge"]["f1"],
            "model_edge_f1": overall["model"]["edge"]["f1"],
            "rule_cluster_f1": overall["control"]["cluster_pairwise"]["f1"],
            "model_cluster_f1": overall["model"]["cluster_pairwise"]["f1"],
            "model_cluster_false_merge_rate": overall["model"][
                "cluster_pairwise"
            ]["false_merge_rate"],
            "model_latency_p50_ms": overall["model"]["latency_ms"][
                "scoring_p50"
            ],
            "model_latency_p95_ms": overall["model"]["latency_ms"][
                "scoring_p95"
            ],
            "peak_rss_mib": paired["runtime"]["max_rss_mib"],
            "runtime_fallback_rate": paired["runtime_fallback_probe"][
                "fallback_rate"
            ],
            "maximum_single_feature_auc": paired[
                "feature_label_diagnostics"
            ]["maximum_single_feature_auc"],
            "robustness_profiles": [
                {
                    "profile_id": item["profile"]["profile_id"],
                    "model_edge_f1": item["model"]["edge"]["f1"],
                    "model_cluster_f1": item["model"]["cluster_pairwise"]["f1"],
                    "model_cluster_false_merge_rate": item["model"][
                        "cluster_pairwise"
                    ]["false_merge_rate"],
                }
                for item in paired["robustness_profiles"]
            ],
        },
        "authority": {
            "g1": False,
            "assist": False,
            "authority": False,
            "default_model_changed": False,
            "active_visual_ppo_started": False,
        },
        "limitations": [
            "synthetic_heldout_single_feature_shortcut",
            "counterfactual_profiles_hold_candidate_graph_fixed",
            "d6_external_audit_required",
            "no_online_authority",
        ],
    }


def _render_summary(summary: Mapping[str, Any]) -> str:
    paired = summary["paired_shadow"]
    model = summary["model"]
    lines = [
        "# D5 冻结图模型审计",
        "",
        "## 结论",
        "",
        f"同一权重完成保留集和成对影子评估，状态为 `{summary['status']}`。",
        "本次只关闭权重谱系断点。G1、辅助模式和控制权限保持关闭。",
        "",
        "## 模型谱系",
        "",
        f"- manifest SHA-256：`{model['manifest_sha256']}`。",
        f"- weights SHA-256：`{model['weights_sha256']}`。",
        f"- admission：`{model['admission']['status']}`。",
        "",
        "## 名义指标",
        "",
        f"- 帧数：`{summary['catalog']['episode_count']}`；seed："
        f"`{summary['catalog']['seed_count']}`。",
        f"- 候选边召回：`{_format_metric(paired['candidate_recall'])}`。",
        f"- 模型边 F1：`{_format_metric(paired['model_edge_f1'])}`；模型簇 F1："
        f"`{_format_metric(paired['model_cluster_f1'])}`。",
        f"- 模型簇错误合并率："
        f"`{_format_metric(paired['model_cluster_false_merge_rate'])}`。",
        f"- 推理 P50/P95：`{_format_metric(paired['model_latency_p50_ms'])}/"
        f"{_format_metric(paired['model_latency_p95_ms'])}` 毫秒。",
        f"- 峰值常驻内存：`{_format_metric(paired['peak_rss_mib'], digits=3)}` MiB。",
        f"- 模型异常规则回退率："
        f"`{_format_metric(paired['runtime_fallback_rate'])}`。",
        "",
        "## 扰动结果",
        "",
        "| 扰动 | 模型边 F1 | 模型簇 F1 | 错误合并率 |",
        "| --- | ---: | ---: | ---: |",
    ]
    for item in paired["robustness_profiles"]:
        lines.append(
            f"| `{item['profile_id']}` | {_format_metric(item['model_edge_f1'])} | "
            f"{_format_metric(item['model_cluster_f1'])} | "
            f"{_format_metric(item['model_cluster_false_merge_rate'])} |"
        )
    auc = paired["maximum_single_feature_auc"]
    lines.extend(
        [
            "",
            "## 限制",
            "",
            f"最高单特征 AUC 为 "
            f"`{_format_metric(auc['best_direction_auc'])}`，特征为 "
            f"`{auc['feature']}`。合成保留集仍存在明显捷径。",
            "扰动评估固定候选图，只检查评分器稳定性，不能替代物理投影和候选门重建实验。",
            "",
        ]
    )
    return "\n".join(lines)


def _format_metric(value: Any, *, digits: int = 6) -> str:
    if value is None:
        return "不可用"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def _write_summary_checksums(root: Path) -> None:
    names = (SUMMARY_FILENAME, SUMMARY_MARKDOWN_FILENAME)
    text = "".join(
        f"{sha256_file(root / name)}  {name}\n" for name in names
    )
    (root / SUMMARY_CHECKSUMS_FILENAME).write_text(text, encoding="ascii")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        _fail("json_invalid", str(path))
        raise AssertionError from exc
    if not isinstance(value, dict):
        _fail("json_object_required", str(path))
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    payload = (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    os.replace(temporary, path)


def _fail(code: str, message: str) -> None:
    raise FrozenTrackletAuditError(code, message)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one hash-bound D5 frozen GNN audit."
    )
    parser.add_argument("--reference", required=True)
    parser.add_argument("--repository-root", required=True)
    parser.add_argument("--heldout-corpus", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--evaluated-at-utc", required=True)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--latency-repeats", type=int, default=3)
    parser.add_argument("--smoke-profile", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    summary = run_frozen_tracklet_audit(
        args.reference,
        args.heldout_corpus,
        args.output_dir,
        repository_root=args.repository_root,
        evaluated_at_utc=args.evaluated_at_utc,
        device=args.device,
        latency_repeats=args.latency_repeats,
        require_full_profile=not args.smoke_profile,
    )
    print(
        json.dumps(
            {
                "status": summary["status"],
                "model_id": summary["model"]["model_id"],
                "weights_sha256": summary["model"]["weights_sha256"],
                "g1": False,
                "assist": False,
                "authority": False,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


__all__ = [
    "FROZEN_AUDIT_REFERENCE_SCHEMA_VERSION",
    "FROZEN_AUDIT_SUMMARY_SCHEMA_VERSION",
    "FrozenTrackletAuditError",
    "main",
    "run_frozen_tracklet_audit",
    "validate_frozen_reference",
]
