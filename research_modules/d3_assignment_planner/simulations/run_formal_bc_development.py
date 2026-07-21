#!/usr/bin/env python3
"""Train and audit the formal D3 behavior-cloning development bundle."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys
from time import perf_counter
from typing import Any, Sequence

from d3_assignment_planner.development_evaluation import (
    audit_formal_learning_dataset,
    evaluate_behavior_cloning_development,
)
from d3_assignment_planner.learning_bundle import (
    development_shadow_admission,
    save_model_bundle,
)
from d3_assignment_planner.learning_data import load_learning_dataset
from d3_assignment_planner.learning_training import train_behavior_cloning
from d3_assignment_planner.native_ppo import SharedEdgeActorCriticPolicy, torch


DEFAULT_HOLDOUT_SEEDS = tuple(range(1000, 1020))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit formal D3 data and train a shadow-only BC bundle"
    )
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--bundle-output",
        type=Path,
        required=True,
        help="ignored local output directory; must be outside the tracked report directory",
    )
    parser.add_argument("--repository-git-commit", required=True)
    parser.add_argument("--training-date", default="2026-07-20")
    parser.add_argument("--epochs", type=int, default=12)
    parser.add_argument("--mini-batch-frames", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=1.0e-3)
    parser.add_argument("--hidden-size", type=int, default=64)
    parser.add_argument("--positive-class-weight-cap", type=float, default=16.0)
    parser.add_argument("--seed", type=int, default=20260720)
    parser.add_argument("--torch-num-threads", type=int, default=4)
    parser.add_argument("--alpha", type=float, default=0.25)
    parser.add_argument("--min-confidence", type=float, default=0.0)
    parser.add_argument("--ood-z-threshold", type=float, default=6.0)
    parser.add_argument("--deadline-s", type=float, default=0.05)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if torch is None:  # pragma: no cover
        raise SystemExit("PyTorch is required for the D3 formal BC run")
    dataset = args.dataset.resolve()
    output = args.output.resolve()
    bundle_dir = args.bundle_output.resolve()
    if dataset == output or dataset in output.parents:
        raise SystemExit("output must not be inside the read-only formal dataset")
    if (
        output == bundle_dir
        or output in bundle_dir.parents
        or bundle_dir in output.parents
    ):
        raise SystemExit("bundle-output must be outside the tracked report directory")
    if output.exists():
        if not args.overwrite:
            raise SystemExit(f"output already exists: {output}")
        shutil.rmtree(output)
    output.mkdir(parents=True)
    if bundle_dir.exists():
        if not args.overwrite:
            raise SystemExit(f"bundle output already exists: {bundle_dir}")
        shutil.rmtree(bundle_dir)
    bundle_dir.parent.mkdir(parents=True, exist_ok=True)
    started = perf_counter()

    manifest, records = load_learning_dataset(dataset)
    audit = audit_formal_learning_dataset(
        dataset,
        manifest,
        records,
        external_holdout_seed_values=DEFAULT_HOLDOUT_SEEDS,
    )
    if not audit["all_checks_passed"]:
        raise SystemExit("formal dataset audit failed")
    _write_json(output / "dataset_audit.json", audit)

    torch.set_num_threads(int(args.torch_num_threads))
    torch.manual_seed(int(args.seed))
    torch.use_deterministic_algorithms(True)
    policy = SharedEdgeActorCriticPolicy(hidden_size=int(args.hidden_size))
    training_records = tuple(
        record for record in records if record.split in {"train", "validation"}
    )
    training_started = perf_counter()
    policy, training_result = train_behavior_cloning(
        training_records,
        policy=policy,
        epochs=int(args.epochs),
        mini_batch_frames=int(args.mini_batch_frames),
        learning_rate=float(args.learning_rate),
        seed=int(args.seed),
        positive_class_weight_cap=float(args.positive_class_weight_cap),
    )
    training_elapsed_s = perf_counter() - training_started

    evaluation_started = perf_counter()
    evaluation = evaluate_behavior_cloning_development(
        records,
        policy,
        normalization_mean=training_result.normalization_mean,
        normalization_scale=training_result.normalization_scale,
        alpha=float(args.alpha),
        min_confidence=float(args.min_confidence),
        ood_z_threshold=float(args.ood_z_threshold),
        deadline_s=float(args.deadline_s),
    )
    evaluation_elapsed_s = perf_counter() - evaluation_started
    training_source_sha256 = _source_digest()
    configuration = {
        "epochs": int(args.epochs),
        "mini_batch_frames": int(args.mini_batch_frames),
        "learning_rate": float(args.learning_rate),
        "hidden_size": int(args.hidden_size),
        "positive_class_weight_cap": float(args.positive_class_weight_cap),
        "seed": int(args.seed),
        "torch_num_threads": int(args.torch_num_threads),
        "alpha": float(args.alpha),
        "min_confidence": float(args.min_confidence),
        "ood_z_threshold": float(args.ood_z_threshold),
        "deadline_s": float(args.deadline_s),
        "deterministic_algorithms": True,
        "optimizer": "Adam",
        "training_kind": "behavior_cloning",
        "ppo_started": False,
    }
    training_results = {
        "behavior_cloning": training_result.to_dict(),
        "development_evaluation": evaluation,
        "configuration": configuration,
        "timing_s": {
            "training": training_elapsed_s,
            "evaluation": evaluation_elapsed_s,
        },
        "admission_statement": (
            "development_shadow_only_external_holdout_1000_1019_not_evaluated"
        ),
    }
    bundle = save_model_bundle(
        bundle_dir,
        policy,
        split_hash=manifest.split_hash,
        dataset_frames_sha256=manifest.frames_sha256,
        normalization_mean=training_result.normalization_mean,
        normalization_scale=training_result.normalization_scale,
        training_results=training_results,
        alpha=float(args.alpha),
        min_confidence=float(args.min_confidence),
        ood_z_threshold=float(args.ood_z_threshold),
        deadline_s=float(args.deadline_s),
        provenance={
            "repository_git_commit": str(args.repository_git_commit),
            "repository_git_commit_role": "dataset_and_training_base_commit",
            "training_worktree_state": "module_changes_present_source_sha256_bound",
            "training_date": str(args.training_date),
            "dataset_manifest_sha256": str(audit["dataset_manifest_sha256"]),
            "training_source_sha256": training_source_sha256,
            "training_entrypoint": "run_formal_bc_development.py",
        },
        admission=development_shadow_admission(DEFAULT_HOLDOUT_SEEDS),
        promotion_unavailable_reason="external_holdout_1000_1019_not_evaluated",
    )
    total_elapsed_s = perf_counter() - started
    report = {
        "schema_version": "d3_formal_bc_development_run_v1",
        "training_date": str(args.training_date),
        "dataset_audit": audit,
        "configuration": configuration,
        "training_result": training_result.to_dict(),
        "development_evaluation": evaluation,
        "bundle": {
            "path": _portable_path(bundle_dir),
            "storage_class": "local_ignored_output",
            "schema_version": bundle.bundle_schema_version,
            "state_dict_sha256": bundle.state_dict_sha256,
            "dataset_frames_sha256": bundle.dataset_frames_sha256,
            "split_hash": bundle.split_hash,
            "provenance": dict(bundle.provenance),
            "admission": dict(bundle.admission),
            "promotion_manifest": dict(bundle.promotion_manifest),
        },
        "timing_s": {
            "training": training_elapsed_s,
            "evaluation": evaluation_elapsed_s,
            "total": total_elapsed_s,
        },
        "limitations": [
            "internal test seeds are development evidence only",
            "external holdout seeds 1000-1019 have not been evaluated",
            "assist mode is not authorized",
            "PPO was not started",
            "AirSim and physical interception effects were not evaluated",
        ],
    }
    report_path = output / "development_evaluation.json"
    _write_json(report_path, report)
    markdown_path = output / "TRAINING_REPORT_CN.md"
    markdown_path.write_text(_render_markdown(report), encoding="utf-8")
    command_path = output / "training_command.txt"
    command_path.write_text(" ".join(sys.argv) + "\n", encoding="utf-8")
    location_path = output / "MODEL_ARTIFACT_LOCATION.md"
    location_path.write_text(
        _render_model_location(bundle_dir, bundle.state_dict_sha256),
        encoding="utf-8",
    )
    tracked_artifact_hashes = {
        relative: _file_sha256(output / relative)
        for relative in (
            "dataset_audit.json",
            "development_evaluation.json",
            "TRAINING_REPORT_CN.md",
            "training_command.txt",
            "MODEL_ARTIFACT_LOCATION.md",
        )
    }
    artifact_hashes = {
        "tracked_artifacts": tracked_artifact_hashes,
        "local_ignored_model": {
            "path": _portable_path(bundle_dir),
            "manifest_sha256": _file_sha256(bundle_dir / "manifest.json"),
            "state_dict_sha256": _file_sha256(bundle_dir / "state_dict.pt"),
        },
    }
    _write_json(output / "artifact_hashes.json", artifact_hashes)
    print(
        json.dumps(
            {
                "output": str(output),
                "bundle_state_dict_sha256": bundle.state_dict_sha256,
                "artifact_hashes": artifact_hashes,
                "timing_s": report["timing_s"],
                "admission": bundle.admission,
            },
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _source_digest() -> str:
    root = Path(__file__).resolve().parents[1]
    paths = (
        Path(__file__).resolve(),
        root / "src/d3_assignment_planner/development_evaluation.py",
        root / "src/d3_assignment_planner/learning.py",
        root / "src/d3_assignment_planner/learning_bundle.py",
        root / "src/d3_assignment_planner/learning_data.py",
        root / "src/d3_assignment_planner/learning_training.py",
        root / "src/d3_assignment_planner/native_ppo.py",
        root / "src/d3_assignment_planner/solver.py",
    )
    digest = sha256()
    for path in sorted(paths, key=lambda value: str(value)):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _render_markdown(report: dict[str, Any]) -> str:
    audit = report["dataset_audit"]
    evaluation = report["development_evaluation"]
    bundle = report["bundle"]
    training = report["training_result"]
    lines = [
        "# D3 正式数据行为克隆开发报告",
        "",
        "## 结论",
        "",
        "本轮完成正式 900 episode 数据审计和行为克隆开发训练。模型只产生有界代价修正，匈牙利求解、需求槽、硬门控、迟滞和计划版本语义未改变。",
        "",
        "当前 bundle 状态为 `development/shadow-only`。内部测试集用于开发诊断，外部保留种子 1000-1019 尚未运行，因此禁止进入 assist。",
        "",
        "## 数据审计",
        "",
        f"- 数据 schema：`{audit['manifest']['schema_version']}`",
        f"- episode：{audit['actual']['episode_count']}；帧：{audit['actual']['frame_count']}；数值 seed：{audit['actual']['unique_seed_count']}",
        f"- train/validation/internal-test 帧：{audit['actual']['split_frame_counts']['train']}/{audit['actual']['split_frame_counts']['validation']}/{audit['actual']['split_frame_counts']['test']}",
        f"- frames SHA256：`{audit['frames_sha256']}`",
        f"- split hash：`{audit['split_hash']}`",
        f"- 1000-1019 与当前数据交集：{audit['external_holdout']['overlap']}",
        "",
        "## 训练配置",
        "",
        f"固定随机 seed {report['configuration']['seed']}，训练 {report['configuration']['epochs']} 个 epoch，隐藏层宽度 {report['configuration']['hidden_size']}，正类权重上限 {report['configuration']['positive_class_weight_cap']}。训练使用 train，validation 用于开发损失；internal-test 未参与归一化和梯度更新。",
        "",
        f"初始训练损失 {training['initial_train_loss']:.6f}，最终训练损失 {training['final_train_loss']:.6f}，验证损失 {training['validation_loss']:.6f}。训练耗时 {report['timing_s']['training']:.2f} 秒，开发评估耗时 {report['timing_s']['evaluation']:.2f} 秒。",
        "",
        "## 分割结果",
        "",
        "| 分割 | 残差平滑损失 | 边排序一致性 | 计划完全一致率 | 计划成本差 | 需求满足率 | 重复分配 | 推理 P95 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for split in ("train", "validation", "test"):
        metrics = evaluation["split_metrics"][split]
        lines.append(
            "| {split} | {loss:.6f} | {rank:.4f} | {exact:.4f} | {gap:.6f} | {demand:.4f} | {duplicate} | {p95:.3f} ms |".format(
                split=("internal-test" if split == "test" else split),
                loss=metrics["regression"]["residual_smooth_l1_mean"],
                rank=metrics["edge_action_consistency"]["ranking_auc"],
                exact=metrics["edge_action_consistency"]["plan_exact_match_rate"],
                gap=metrics["plan_cost"]["mean_gap"],
                demand=metrics["demand_satisfaction"]["bc_shadow_rate"],
                duplicate=metrics["safety"]["bc_shadow_duplicate_count"],
                p95=metrics["latency_ms"]["model_inference_p95"],
            )
        )
    lines.extend(
        [
            "",
            "## 规模覆盖",
            "",
            "| 名义规模 | 帧数 | 推理 P50 | 推理 P95 | BC 需求满足率 | 计划成本差 |",
            "|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for scale in (5, 20, 50, 100, 200):
        metrics = evaluation["scale_metrics"][str(scale)]
        lines.append(
            f"| {scale} | {metrics['frame_count']} | {metrics['latency_ms']['model_inference_p50']:.3f} ms | {metrics['latency_ms']['model_inference_p95']:.3f} ms | {metrics['demand_satisfaction']['bc_shadow_rate']:.4f} | {metrics['plan_cost']['mean_gap']:.6f} |"
        )
    lines.extend(
        [
            "",
            "## 准入状态",
            "",
            f"- bundle schema：`{bundle['schema_version']}`",
            f"- 权重 SHA256：`{bundle['state_dict_sha256']}`",
            f"- 本地 ignored bundle：`{bundle['path']}`",
            f"- Git 提交：`{bundle['provenance']['repository_git_commit']}`",
            f"- 训练源码 SHA256：`{bundle['provenance']['training_source_sha256']}`",
            "- 允许模式：shadow",
            "- assist：未授权",
            "- PPO：未启动",
            "",
            "main 后续必须使用同一冻结 bundle 在种子 1000-1019 上运行独立评估，核对安全非退化、计划成本、需求满足、抖动、分布外回退和时延。该证据通过前，内部测试结果不得写成最终准入结论。",
            "",
        ]
    )
    return "\n".join(lines)


def _write_json(path: Path, value: Any) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")


def _render_model_location(bundle_dir: Path, state_dict_sha256: str) -> str:
    manifest_sha256 = _file_sha256(bundle_dir / "manifest.json")
    return (
        "# D3 行为克隆权重定位\n\n"
        "开发权重不进入普通 Git 提交。当前本地 bundle 位于：\n\n"
        f"`{_portable_path(bundle_dir)}`\n\n"
        "权重文件 `state_dict.pt` 的 SHA256 为：\n\n"
        f"`{state_dict_sha256}`\n\n"
        "bundle manifest 的 SHA256 为：\n\n"
        f"`{manifest_sha256}`\n\n"
        "该 bundle 为 `development/shadow-only`，外部保留种子 1000-1019 尚未验收。"
        "长期保留权重需使用 Git LFS 或独立制品存储；当前环境未配置 Git LFS，因此本地 "
        "ignored output 是唯一权重副本。删除本地 `outputs/` 前应先完成制品归档。\n"
    )


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _portable_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
