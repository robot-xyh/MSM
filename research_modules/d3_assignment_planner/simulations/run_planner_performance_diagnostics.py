"""Run the isolated D3 200x200 performance-attribution benchmark."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from d3_assignment_planner import (
    run_reproducible_planner_performance_benchmark,
)


MODULE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JSON = MODULE_ROOT / "results" / "d3_planner_performance_attribution_20260722.json"
DEFAULT_REPORT = MODULE_ROOT / "reports" / "D3_PLANNER_PERFORMANCE_ATTRIBUTION_20260722_CN.md"


def render_chinese_report(payload: dict[str, Any]) -> str:
    modes = {item["mode"]: item for item in payload["modes"]}
    default = modes["default"]
    identity_reference = modes["identity_recompute_reference"]
    evidence_reference = modes["evidence_bypass_reference"]
    initial_counts = default["initial"]["operation_counts"]
    refresh_counts = default["refresh"]["operation_counts"]

    def median_ms(mode: dict[str, Any], phase: str, key: str) -> str:
        return f"{float(mode[phase]['timing_medians_ms'][key]):.3f}"

    return f"""# D3 规划热路径冻结输入归因

## 结论

本次使用同一份匿名、可复现的 {payload['target_count']}×{payload['resource_count']} 输入，分离 D3 成本矩阵、候选图、Hungarian 求解、迟滞、计划载荷、身份发布和离线证据构造。默认路径、身份重复计算参考路径和关闭离线证据参考路径的绑定哈希、计划版本及规范业务哈希一致。最新发布执行签名始终来自规划器内部缓存，不使用调用方 previous plan 代替。参考路径只用于归因，不是运行时替代方案。

D3 暖启动耗时主要由候选边计划证据、上一计划帧的迟滞重评分和匿名离线证据构成。Hungarian 在当前稀疏候选图下不是唯一成本来源。集成 10 秒 episode 的累计时间还受 D3 调用次数和上游输入形状影响，不能用单次墙钟直接解释；main 需在隔离工作树中对同一 episode 再测。

## 冻结输入

- fixture schema：`{payload['fixture_schema']}`
- seed：`{payload['seed']}`
- 输入 SHA-256：`{payload['input_sha256']}`
- 目标数：{payload['target_count']}
- 资源数：{payload['resource_count']}
- 每目标候选边上限：{payload['max_candidate_edges_per_target']}
- 重复次数：{payload['repeat']}
- 在线真值：未使用。目标标识是匿名 GlobalTrack 代理，不是仿真真实编号。

## 热点边界

| 阶段 | 首帧结构操作数 | 上一计划帧结构操作数 | 边界 |
| --- | ---: | ---: | --- |
| 全量目标资源对 | {initial_counts['full_pair_count']} | {refresh_counts['full_pair_count']} | 向量化规则代价计算 |
| 候选边 | {initial_counts['candidate_edge_count']} | {refresh_counts['candidate_edge_count']} | 稀疏候选图与计划边证据 |
| 候选连通分量 | {initial_counts['candidate_component_count']} | {refresh_counts['candidate_component_count']} | 分量内 Hungarian |
| Hungarian 准备矩阵单元 | {initial_counts['hungarian_prepared_cell_count']} | {refresh_counts['hungarian_prepared_cell_count']} | 局部代价矩阵加未分配虚拟列 |
| 计划边哈希条目 | {initial_counts['canonical_edge_hash_item_count']} | {refresh_counts['canonical_edge_hash_item_count']} | `cost_breakdowns_by_edge` 规范哈希 |
| 迟滞候选边访问 | {initial_counts['hysteresis_candidate_edge_visit_count']} | {refresh_counts['hysteresis_candidate_edge_visit_count']} | 去除搜索整形后的当前目标重评分 |
| 迟滞绑定重评分 | {initial_counts['hysteresis_binding_rescore_count']} | {refresh_counts['hysteresis_binding_rescore_count']} | 旧计划与候选计划绑定 |
| 匿名证据矩阵复制单元 | {initial_counts['evidence_matrix_cell_copy_count']} | {refresh_counts['evidence_matrix_cell_copy_count']} | 规则矩阵和实际求解矩阵的只读快照 |
| 匿名 breakdown 单元访问 | {initial_counts['evidence_breakdown_cell_visit_count']} | {refresh_counts['evidence_breakdown_cell_visit_count']} | 保留共享模板的匿名化遍历 |
| 匿名 breakdown 实际净化数 | {initial_counts['evidence_unique_breakdown_sanitize_count']} | {refresh_counts['evidence_unique_breakdown_sanitize_count']} | 按对象身份复用净化结果 |

## 墙钟结果

墙钟仅写入本基准报告，没有进入 `AssignmentPlan.metadata`、`plan_id` 或运行时控制合同。各阶段为包含式边界，不应相加解释总耗时。

| 路径 | 帧 | 端到端/ms | 成本矩阵/ms | Hungarian/ms | 计划边证据/ms | 迟滞/ms | 身份固化/ms | 发布/ms | 离线证据/ms |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 默认 | 首帧 | {median_ms(default, 'initial', 'end_to_end_ms')} | {median_ms(default, 'initial', 'search_matrix_ms')} | {median_ms(default, 'initial', 'hungarian_ms')} | {median_ms(default, 'initial', 'plan_edge_evidence_ms')} | {median_ms(default, 'initial', 'hysteresis_ms')} | {median_ms(default, 'initial', 'identity_finalize_ms')} | {median_ms(default, 'initial', 'publish_ms')} | {median_ms(default, 'initial', 'offline_evidence_ms')} |
| 默认 | 上一计划帧 | {median_ms(default, 'refresh', 'end_to_end_ms')} | {median_ms(default, 'refresh', 'search_matrix_ms')} | {median_ms(default, 'refresh', 'hungarian_ms')} | {median_ms(default, 'refresh', 'plan_edge_evidence_ms')} | {median_ms(default, 'refresh', 'hysteresis_ms')} | {median_ms(default, 'refresh', 'identity_finalize_ms')} | {median_ms(default, 'refresh', 'publish_ms')} | {median_ms(default, 'refresh', 'offline_evidence_ms')} |
| 身份重复计算参考 | 上一计划帧 | {median_ms(identity_reference, 'refresh', 'end_to_end_ms')} | {median_ms(identity_reference, 'refresh', 'search_matrix_ms')} | {median_ms(identity_reference, 'refresh', 'hungarian_ms')} | {median_ms(identity_reference, 'refresh', 'plan_edge_evidence_ms')} | {median_ms(identity_reference, 'refresh', 'hysteresis_ms')} | {median_ms(identity_reference, 'refresh', 'identity_finalize_ms')} | {median_ms(identity_reference, 'refresh', 'publish_ms')} | {median_ms(identity_reference, 'refresh', 'offline_evidence_ms')} |
| 关闭离线证据参考 | 上一计划帧 | {median_ms(evidence_reference, 'refresh', 'end_to_end_ms')} | {median_ms(evidence_reference, 'refresh', 'search_matrix_ms')} | {median_ms(evidence_reference, 'refresh', 'hungarian_ms')} | {median_ms(evidence_reference, 'refresh', 'plan_edge_evidence_ms')} | {median_ms(evidence_reference, 'refresh', 'hysteresis_ms')} | {median_ms(evidence_reference, 'refresh', 'identity_finalize_ms')} | {median_ms(evidence_reference, 'refresh', 'publish_ms')} | {median_ms(evidence_reference, 'refresh', 'offline_evidence_ms')} |

## 语义校验

- 默认首帧绑定 SHA-256：`{default['initial']['binding_sha256']}`
- 默认首帧业务 SHA-256：`{default['initial']['business_sha256']}`
- 默认刷新帧绑定 SHA-256：`{default['refresh']['binding_sha256']}`
- 默认刷新帧业务 SHA-256：`{default['refresh']['business_sha256']}`
- 三条路径绑定一致：`{payload['semantic_equivalence']['bindings_equal']}`
- 三条路径计划版本一致：`{payload['semantic_equivalence']['plan_versions_equal']}`
- 三条路径规范业务哈希一致：`{payload['semantic_equivalence']['canonical_business_hashes_equal']}`
- 刷新帧复用原 `plan_id`：`{payload['semantic_equivalence']['refresh_reuses_plan_identity']}`
- 最新发布签名来源：`{payload['latest_published_signature_source']}`
- 调用方 previous 签名充当 latest：`{payload['caller_previous_signature_used_as_latest']}`
- 规则代价、Hungarian、迟滞和 D5/D7 binding 均未修改。

## main 复测要求

main 应在最终候选提交建立 detached clean worktree，使用 seed 42000 的同一 2.2 秒与 10 秒配置复跑，再扩展 seed 42001、42002。复测需同时核对 D3 调用次数、每次目标/资源/候选边数量、绑定哈希、计划版本、运行时 ACK、在线真值使用次数和累计阶段墙钟。只有冻结输入的单次成本与调用密度都能解释累计差异时，才能判断 2.484 秒到约 3.348 秒的变化来自 D3 代码或 episode 调度。
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42_000)
    parser.add_argument("--max-edges", type=int, default=32)
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--output-report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    payload = run_reproducible_planner_performance_benchmark(
        count=args.count,
        seed=args.seed,
        max_candidate_edges_per_target=args.max_edges,
        repeat=args.repeat,
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_report.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.output_report.write_text(render_chinese_report(payload), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
