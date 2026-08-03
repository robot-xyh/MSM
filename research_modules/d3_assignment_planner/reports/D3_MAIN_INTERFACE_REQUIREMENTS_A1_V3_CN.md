# D3 主接口要求：匿名 roster 事件与困难负类

日期：2026-08-02。本文是 D3-owned interface requirement，不是 source generation
授权或正式数据结果。

当前状态：main 已按本接口完成 15-cell、300-episode dirty 开发探针，
结果为 `300/300 exploratory_dirty_pass`。该结果关闭 request-level
`cross_seed_quota_viability_not_proven`，但 `readiness_eligible=false`。正式生成、训练、运行和
控制仍未授权。下文的 20-frame 结果保留为接口开发早期证据。

## 已证明的最小能力

Main 必须能在不暴露 truth ID、`global_track_id`、teacher label 或 effective
override 的条件下，按预注册 frame schedule 产生匿名 roster events。roster 的目标、
需求槽和资源集合变化应能让 D3 确定性分类器产生正类或负类 transition。已有 main
实验在匿名 roster events 上得到 positive/negative `20/20`；这只证明事件可被观察，
不证明 source quota 已满足。已有困难负类配额只有 `12/20`，所以跨 seed quota viability
仍未证明。

## Main 输入合同

- truth-free frame：匿名目标/资源数量、候选 mask、规则 cost matrix、匿名 demand
  slots、`measurement_timestamp`、`arrival_timestamp`、上一帧匿名 roster/plan 摘要；
  保留两个时间戳，不得复制。
- frame schedule：使用冻结 schedule 的 episode/seed/split/cell 顺序和每帧真实事件；
  每 episode 最低 `positive=3`、`negative=3`、`hard_negative=2`，不能用复制帧补齐。
- 状态边界：D3 只消费匿名观测和已有 safety projection 输入；在线不得读取 truth
  actor/object ID、离线标签或中心 `global_track_id`。

## 输出合同

每帧输出匿名可审计的 candidate proposal、规则成本、candidate/pre-projection
edges、effective/post-projection edges、projection reason codes、双时间戳、规模字段和
稳定 frame key。正/负类由现有 D3 classifier 从连续匿名 transition 推导；困难负类必须
记录确定性 counterfactual candidate proposal 及其通过现有 safety projection 后的结果。

## 硬禁止

- 不得用 teacher edges 直接制造 candidate 或 hard-negative 标签。
- 不得把 effective plan 当作 candidate proposal，也不得用 caller label、teacher
  override 或阈值改写 quota 分类。
- 困难负类不得停留在未投影的危险 candidate；必须经过既有 safety projection，失败则
  fail-closed 并保留稳定 error/reason code。
- 不得读取 formal seeds `1000-1019` 或 R0 shards `10-19`，不得复制 frame，不得
  创建/改写 `global_track_id`。

当前结论：接口要求已明确并在 dirty 开发探针中完成 300/300 验证。
source request readiness 为 true，实际 source generation 及后续权限仍为 false。

## 现有 safety API 核验与接口缺口

D3 当前最接近的可调用函数是：

```python
from d3_assignment_planner.a1_assignment_aware_development import (
    solve_a1_safe_assignment,
)
outcome = solve_a1_safe_assignment(record: LearningFrameRecord, matrix: np.ndarray)
```

它要求 `LearningFrameRecord` 的完整输入：`action_mask`、有限且同形状的 `rule_cost_matrix`
或 proposal matrix、`target_demand_slots`、`target_threat_scores`、`unassigned_costs`、
`previous_selected_edges` 以及匿名 targets/resources 等学习记录字段。输出是
`A1SafeAssignmentOutcome`，包括 `selected_edges`、rule/proposal objective、assigned slot
count、high-threat coverage、duplicate resource、hard-edge、M-to-N atomicity、churn 和
removed-incomplete-target 计数。它执行 Hungarian demand-slot 求解并把不完整需求投影为
未激活目标。

但这个 API 不接受 `A1V3OnlineFrame`，也不接收 v3 的双时间戳、candidate/pre-projection
edges、post-projection edges 和 v3 reason-code 合同。另一个现有入口
`evaluate_learning_intervention_candidate_frame(sequence_index, rule_frame, treatment_frame)`
要求两个 `PlanningFrameEvidence` 同输入 frame，且是 rule/treatment eligibility 评估，
不是 v3 source-only counterfactual proposal API；`evaluate_a1_assignment_aware_candidate`
还要求 teacher frames 和 policy。它们都不能被主流程直接当作 v3 safety adapter。

## Source-only safety-projection API（接口 gap 已关闭）

D3 已提供稳定入口 `project_a1_v3_source_only_counterfactual`。其 typed 输入
`A1V3SourceOnlyProjectionInput` 只包含稳定 frame key、双时间戳、有限 rule cost matrix、
hard-safe action mask、匿名 demand/threat/unassigned 数据、上一帧匿名 selected edges 和
预注册 mode。严格 mapping parser 会拒绝 truth、teacher、reference、effective 和
`global_track_id` 字段；陈旧时间顺序和与当前 hard-safe mask 不一致的 previous edges 也会
以稳定错误码 fail closed。

最小调用示例：

```python
import numpy as np

from d3_assignment_planner import (
    A1V3CounterfactualMode,
    A1V3PostProjectionReferencePolicy,
    A1V3SourceOnlyProjectionInput,
    project_a1_v3_source_only_counterfactual,
)

frame = A1V3SourceOnlyProjectionInput(
    frame_key=(23001, "a1-v3-episode-0001", 7),
    measurement_timestamp_s=12.50,
    arrival_timestamp_s=12.52,
    rule_cost_matrix=np.asarray([[1.0, 1.001]], dtype=float),
    hard_safe_action_mask=np.asarray([[True, True]], dtype=bool),
    target_demand_slots=(1,),
    target_threat_scores=(0.8,),
    unassigned_costs=np.asarray([10.0], dtype=float),
    previous_selected_edges=((0, 0),),
    preregistered_mode=A1V3CounterfactualMode.NEAR_TIE_ALTERNATIVE,
)
outcome = project_a1_v3_source_only_counterfactual(
    frame,
    # 只在 candidate/pre reasons 冻结后进入 post-projection。
    reference_effective_edges=((0, 0),),
    reference_policy=A1V3PostProjectionReferencePolicy.EXACT_SAFE_REFERENCE,
)
```

`coverage_degrading` 从 source-only rule projection 中确定性选择匿名低威胁已覆盖目标并生成
覆盖退化 candidate；`near_tie_alternative` 仅在原始 rule costs 同时满足冻结 absolute/relative
near-tie 边界且存在可执行替代边时生成 candidate，否则返回
`candidate_near_tie_alternative_unavailable_v1` 并回退。两种 mode 均复用 D3 的 Hungarian
demand-slot 和 all-or-none projection。

post policy 默认为 `coverage_floor`，保持原兼容行为。显式 `exact_safe_reference` 要求提供
通过索引、hard-safe mask、资源唯一性和 M-to-N all-or-none 检查的 reference；candidate
post edges 与 reference 不同即返回 reference，并记录
`effective_reference_plan_stability_fallback_v1`。缺失、非法或不安全 reference 使用稳定
错误码失败关闭。输出保留 policy、candidate/pre-projection edges、effective/post-projection
edges、稳定 pre/post reason codes、coverage/safety diagnostics、frame key 和双时间戳。
reference effective edges 不进入候选生成；不同 reference 的回归测试证明 candidate edges
与 pre reason codes 不变。输出的 `runtime`、`assignment`、`plan`、`control`、
`global_track_id` 权限固定为 false。

本接口关闭的是 D3-owned safety adapter gap，不改变本文前述 source request readiness；
`cross_seed_quota_viability_not_proven` 仍是独立 blocker。

## Main adapter 与 quota probe 接线核验

Main adapter 已提供显式 `source_only_counterfactual_mode` 和 `source_episode_key` 参数；还需
增加 typed `source_only_reference_policy` 并原样转发到 D3 projection。D3 quota probe v4
已固定调用 `A1V3CounterfactualMode.COVERAGE_DEGRADING`、
`A1V3PostProjectionReferencePolicy.EXACT_SAFE_REFERENCE`，并绑定
`source_episode_key=(recipe.seed, recipe.episode_id)`；全部 frame 完成 adaptation 和 online
frame 构建后才运行 sidecar classifier，因此不存在按实际 class、teacher 或 reference 结果
事后挑选 candidate frame 的路径。checkpoint、episode/frame record 与 source bindings 均
记录 policy；source bindings 同时覆盖 main adapter、D3 projection、
`a1_assignment_aware_development.py` all-or-none 依赖、冻结 request/policy 和 classifier。

此前 2026-08-02 聚焦核验只运行代表性 recipe
`a1-v3-cell-00-train-00`（seed `23000`）：10 个实际 runtime frame 全部生成覆盖退化
candidate，10 个 effective 结果全部经 reference coverage floor 安全回退；观测/正类/负类/
困难负类为 `10/4/6/6`，验收下限为 `9/3/3/2`。frame key 从
`(23000, "a1-v3-cell-00-train-00", 0)` 稳定递增至 index 9，arrival timestamp 全部晚于
measurement timestamp；online truth use、`global_track_id` create/rewrite 均为 0。不同
reference 下 candidate 不变而 effective 可按 coverage floor 改变的合同测试已通过。

该历史结果使用 coverage-floor 合同，不能替代 exact-policy 的新 probe。以上仅证明单
recipe 接线和合同行为，不证明跨 seed quota viability。probe 对全部 recipe
强制执行不低于 `positive=3`、`negative=3`、`hard_negative=2` 的统一下限，不采用旧条目中
更低的声明。readiness 继续保持 false，blocker 继续为
`cross_seed_quota_viability_not_proven`；只有 main 完成且通过 300/300 后才能重新评估。

## 匿名 assignment coverage taxonomy

稳定 target roster、demand 和 active-resource inventory 下，teacher coverage 数变化本身
不足以产生正类。transition 必须同时记录 candidate edge inventory 的 before/after、
added/removed 和净变化。candidate inventory 净收缩、teacher edge 净收缩且 coverage
deficit 等量增加时为 `assignment_coverage_contraction`；三者反向闭合时为
`assignment_coverage_recovery`。固定 candidate mask 的多边 teacher 丢失仍
`sidecar_teacher_change_unclassifiable`，不能误套 resource failure/recovery；teacher edge
数不变、资源 multiset 守恒的多目标 cycle 继续为 `multi_target_cycle`。

等基数单槽覆盖转移另行约束：一个已覆盖匿名目标必须从候选容量可行降为不可行，一个原未覆盖
目标接管，teacher 总边数和 deficit 不变，teacher 资源集合恰好一出一入。满足时复用
`single_target_rebind_with_resource_release`；任一条件缺失均失败关闭。

seed `23191` 的匿名 blocker 证据已冻结为 probe 回归期待：frame 3 candidate inventory
`1600 -> 1521`（added `174`、removed `253`），teacher `50 -> 48`；frame 8 candidate
inventory `1590 -> 1600`（added `72`、removed `62`），teacher `49 -> 50`。checkpoint
逐帧记录并校验 `after-before == added-removed == delta`。main 全局哈希绑定及 D3 下游
哈希链现已刷新，但在 300/300 复跑前，这些诊断与回归期待不得表述为 probe pass。
