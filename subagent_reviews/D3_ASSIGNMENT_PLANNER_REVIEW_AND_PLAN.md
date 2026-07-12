# D3 中心化资源-目标分配综述及子方案

**定位**: 在由 main runtime `--drone-count` 决定的 N 对 N 或非等量资源/目标场景中，由中心节点生成滚动 `AssignmentPlan`，并通过迟滞逻辑避免频繁重分配；5v5 只作为示例和基准场景。
**边界**: 本文只讨论抽象资源-目标匹配、离线评估和人工授权前的候选计划，不包含真实火控参数、毁伤模型或自动处置流程。
**D3 复核状态 2026-07-11**: active-plan 连续性、execution-signature identity、candidate/published 分离、forced replan ack/applied、solve 前 switch penalty、secondary activation/current-binding、same-owner continuation、M-to-N demand-slot、保守增量规划、transient feedback dwell 和 role-aware primary 保持均已关闭。历史第一次 M=5/N=2 复验曾暴露 soft reserve hold 导致 healthy primary 旋转，现已按 previous-plan member role 固定健康 primary、只重解 reserve。当前 ComputerVision 10-seed 中 T001 双 primary 视觉共识与当前计划授权为 8/10；二级/分布式 commit 正例和缺 ACK fail-closed 已通过，因此 D3 P1 合同层闭合。15 s SimpleFlight 仍是 0 物理命中的诊断，物理闭环开放；P2 仅为隔离 optional benchmark。

**P1 switch-penalty 状态 2026-07-10**: done。`reassignment_switch_penalty` 已从 solve 后追加改为 solve 前进入可行改配边；同 resource、不可行边、无历史 assignment 的 target 和 unassigned cost 不变。solver matrix、breakdown total、objective、Assignment 和 evidence 使用同一成本且无双重计费。新 current plan binding 即使发生改配仍为 `active/current`，旧 plan 由 current plan id/version gate 失效。

当前 D3 P0/P1 缺口清单：

- P0 done：旧“无 P0 blocker”结论已撤销；active plan 后缺失 `previous_plan` 的版本回退入口已关闭，拒绝 reason 固定为 `previous_plan_required` 并返回 latest plan id/version。首次调用仍允许 `None`，新 episode 使用新 planner 实例。
- P1 done：switch penalty 已在 Hungarian/fallback solve 前加入可行改配边，matrix/breakdown/objective/evidence 单次计费一致；unassigned/release 和 current binding 语义不变。
- P1 合同层 done：5-resource/2-target ComputerVision 10 seeds 中，T001 双 primary 视觉共识与当前计划授权达到 8/10；seeds 7/27 保留回归。
- P1 下游合同证据 done：二级接管和完全分布式 commit 正例通过；缺 ACK 时 coalition aborted、D7 许可为 0，fail-closed 通过。该结果不等于物理拦截。
- P1 transient feedback dwell done：`primary_lock_stability_incomplete`/短暂 reacquire 只在 source plan version 匹配、旧 primary 仍可行且无硬冲突时保护 coalition primary；effective window 为 D3 配置和上游 required stable frames 的最大值，持续到阈值或硬风险可立即换员。
- P1 reserve role protection done：若所有旧 primary 都是同版本 `consistent/continue`，且旧 reserve 仅为普通 `hold/hold` 或 `reacquire/replan`，D3 从 previous assignment role 推导 primary pins，只替换 reserve；不要求 main 提供 reason/required/member_role。
- P1：D5 feedback 权重与 dwell/迟滞阈值仍需用真实 D6 records 配对标定。
- P1 增量接口 done：输入快照、changed-set 完整性、独立连通分量局部求解、全量 fallback reason、全局迟滞、M-to-N all-or-none 和增量/全量 comparison summary 已测试；仍缺真实非等量 3v5/5v3、目标新增、资源失效和 crossing/dense 多 seed 校准。
- P1：D3 secondary activation/current-binding 合同已闭合，并已由二级/分布式 commit 正例与缺 ACK fail-closed 覆盖下游消费；D4 协商与恢复策略仍属 D4/main 边界。
- Optional benchmark done：OR-Tools 同输入 Min-Cost Flow 接口已实现，不是待关闭 P1；CP-SAT/MILP、复杂 flow 和大规模扫描保留为 P2 optional。

---

## 0. 当前代码状态摘要

截至 2026-07-10，D3 代码已经实现：

- SciPy Hungarian / `linear_sum_assignment` 主线，带 dummy unassignment 列。
- 无 SciPy 时的小规模 `FallbackAssignmentSolver` 位掩码 DP fallback。
- `AssignmentPlan(plan_id, version, window_id, resource_count, target_count)` 和 `assignment_matrix_shape` 规模 metadata。
- `StalePlanError`，拒绝 active plan 后缺失的 `previous_plan`、旧 `previous_plan`、旧 `plan_id` 或不匹配的 `expected_previous_version`。
- 迟滞重分配：`delta`、`min_dwell`、`max_changes_per_window`；`reassignment_switch_penalty` 在 solver 前进入候选 matrix，不再 solve 后补账。
- D5 terminal feedback helper，始终 `allow_local_rebind=False`。
- D7 `AssignmentGuidanceBinding`，携带 `assigned_global_track_id`、`plan_version`、binding state、source/target/link 和 `allow_local_rebind=False`。
- `AssignmentValiditySummary` 和 D6-compatible `AssignmentRecord` 导出；assignment records 携带 multi-seed 分组所需的 owner/source/schema、replan/takeover reason、previous/supersede、secondary owner/version/epoch/lease/readiness/activation、迟滞决策、矩阵规模、cost gap 和 N/M mismatch replay 字段。
- `AssignmentEvidenceExport` 导出 current plan id/version/owner/source、完整 current cost matrix、per-edge cost breakdown、hard rejected edges/reasons、stale rejection reason，以及 secondary readiness/activation/owner/version/epoch/lease/supersede 字段。
- 轻量 hard time-window baseline：显式 closed/expired/not-yet-open 的边会被 hard rejected，不进入最终 assignment，`window_cost` 继续作为 open edge 软排序项。
- synthetic AirSim dry-run adapter，不 import AirSim，不控制 Blocks runtime。
- `PlannerConfig.human_authorization_state` 透传到 `AssignmentPlan.human_authorization_state`，并写入 `configured_human_authorization_state` / `effective_human_authorization_state` metadata。
- `apply_terminal_feedback_to_planner_inputs()` 将 D5 duplicate/friend/fov/feasibility metadata 写回下一轮 `TargetTrack[]/ResourceState[]`，并保留 source plan version、coalition reason/conflict、stable counts 和 required window；full/incremental planner 共用 transient primary dwell。
- `prepare_secondary_takeover_plan()` 在 D4/main 已选定具体二级节点且持续 `takeover_ready` 后，校验精确 supersede、严格 version/epoch 和 live lease，再生成 active `secondary_plan_v2`；D7 secondary binding 还必须显式匹配 current plan，过期或历史计划不可执行。
- `summarize_terminal_feedback_calibration()` 和 `summarize_assignment_mismatch_replay()` 已支持多 seed feedback/assignment replay 汇总，只输出调参建议和 replay 计数，不修改默认权重或迟滞参数。

当前只是部分实现或未实现：

- `MinCostFlowAssignmentSolver` 支持 optional OR-Tools 资源容量；隔离 runner 用同一非等量 N/M、hybrid demand-slot 输入比较 SciPy 与 flow，未安装时输出结构化 `unavailable_reason`，不进入默认依赖或 planner。
- `secondary_plan_v2` 的 D3 activation/current-binding 合同已实现；main runtime 仍需传入 sustained readiness、activation time、leader epoch、live lease 和 current plan identity。二级节点选择、lease 续期、中心恢复合并和 active owner runtime 仲裁仍属 D4/main policy。
- D4 `request_center_replan`、`degrade_to_secondary`、`degrade_to_distributed` 仍由 main/D4 消费 D3 证据后触发，D3 不自动调用；其中中心 `request_center_replan` 的 owner/version/supersede runtime 记录已由 main 接线，D3 只需保持版本化计划和 stale 拒绝合同。
- 剩余 D3 P1 是增量/全量真实多 seed 标定、真实非等量 N/M 与动态事件、D5 feedback/迟滞权重、hard-window 多场景和完整动态威胁；secondary 只剩跨模块 runtime 验证，不再是 D3 DTO 缺口。增量接口和 optional OR-Tools 同输入接口已经完成。
- D3 不负责末端视觉重绑，不改写 `global_track_id`。

---

## 1. 研究问题

初始分配不是一次性决策。目标会丢失、航迹质量会变化、资源状态会变化，末端配准也可能返回 `ambiguous` 或 `hold`。如果每一帧都重新求最优，系统会频繁抖动；如果完全不重分配，则会漏掉更合理的计划。

本子系统目标：

- 中心节点正常时默认使用 Hungarian。
- 复杂约束时升级为最小费用流或 CP-SAT/MILP。
- 分配代价包含航迹不确定性、抽象威胁权重、资源状态、视场确认难度和资源间冲突风险。
- 重分配必须带版本号、迟滞和最小保持时间。

---

## 2. 文献综述要点

2015-2026 年动态资源分配主线包括 Hungarian、最小费用流、MILP、滚动窗口优化和多智能体任务分配。Hungarian 适合一对一匹配，延迟低、实现成熟。最小费用流能表达容量、禁配边、任务需求量和多阶段约束。MILP/CP-SAT 表达能力更强，但求解时间和建模复杂度更高。

滚动窗口优化是动态场景常见方法：每个周期只提交近期计划，远期计划保持可调整。为了避免抖动，常用策略包括切换惩罚、最小保持时间、双阈值、版本锁和收益门限。例如只有新方案总代价相对旧方案改善超过阈值，才允许切换。

本文推荐：N 对 N 或非等量 M/N 一对一基线优先使用 SciPy Hungarian，5v5 仅作为默认示例/基准；当出现容量、禁配、备份资源或多轮窗口约束时，再把当前预留的 OR-Tools Min Cost Flow 后端实现为可运行求解器；更复杂逻辑再进入 CP-SAT/MILP 离线研究。

---

## 3. 开源代码选型

| 工具 | 适用场景 | 优点 | 限制 |
|------|----------|------|------|
| SciPy `linear_sum_assignment` | 一对一矩阵分配 | 简洁、快、稳定 | 难表达复杂约束 |
| OR-Tools Min Cost Flow | 容量、禁配、分组、时间窗 | 约束强，适合后续复杂约束 | 当前仅预留接口；需要 optional dependency、建图和整数代价缩放 |
| OR-Tools CP-SAT | 复杂逻辑约束 | 表达能力强 | 当前未实现，不适合高频滚动主线 |

当前已落地 Hungarian/fallback 主线和 `MinCostFlowAssignmentSolver` 保留边界。后续接入 OR-Tools 时，应保持 `AssignmentPlan`、D7 binding 和 D6 export 的外部合同不变。

---

## 4. 子系统架构

### 4.1 数据结构

```text
ResourceState
- resource_id
- status: available | busy | degraded | unavailable
- capability_class
- health_score
- busy_until
- operator_hold
- load_penalty
- fov_difficulty / conflict_risk
- metadata

Assignment
- resource_id
- target_id  # 等价引用 D2/中心维护的 global_track_id
- cost
- cost_breakdown
- feasibility_state
- source_node_id / target_node_id / link_type
- plan_version
- stale_after_s

AssignmentPlan
- plan_id
- version
- window_id
- resource_count
- target_count
- assignments
- total_cost
- created_at
- human_authorization_state
- decision_state
- source_node_id / target_node_id / link_type
- stale_after_s

TerminalFeedbackWriteback
- tracks/resources  # 下一轮 D3 输入
- prohibited_edges
- hold_resource_ids
- updated_target_ids / updated_resource_ids
- d7_gate_action
- d4_requests
- allow_local_rebind=False
```

### 4.2 类图

```text
AssignmentPlanner
  + plan(tracks, resources, timestamp, previous_plan=None, expected_previous_version=None)
  - _apply_switch_penalty_to_matrix()
  - _apply_hysteresis()
  - _validate_previous_plan()
  - _remember_plan()

CostModel
  + build_matrix(tracks, resources, timestamp)
  + edge_cost(track, resource, timestamp)

HungarianAssignmentSolver
  + solve(cost_matrix, unassigned_costs)

FallbackAssignmentSolver
  + solve(cost_matrix, unassigned_costs)

MinCostFlowAssignmentSolver
  + solve(...)  # optional OR-Tools same-input benchmark
```

---

## 5. 代价函数

保持抽象、可解释、可记录：

```text
assignment_cost =
    approach_window_cost
  + track_uncertainty_penalty
  + target_priority_weight
  + resource_state_penalty
  + fov_confirmation_difficulty
  + inter_resource_conflict_risk
  + reassignment_switch_penalty
```

每项都必须写入 `cost_breakdown`，便于解释为何分配或拒配。对 `previous_plan` 中已有 target，切换到不同 resource 的可行边在 Hungarian/fallback 前加入 `reassignment_switch_penalty`；同 resource、不可行边、无历史 assignment 的 target 和 unassigned cost 不变。matrix cell、breakdown `total`、solver objective、Assignment 和 evidence 必须同值，禁止 solve 后再次追加。

---

## 6. 迟滞逻辑伪代码

```python
class AssignmentPlanner:
    def plan(self, tracks, resources, timestamp, previous_plan=None, expected_previous_version=None):
        validate_previous_plan(previous_plan, expected_previous_version)
        matrix = CostModel.build_matrix(tracks, resources, timestamp)
        matrix = apply_switch_penalty_to_feasible_reassignment_edges(matrix, previous_plan)
        candidate = HungarianAssignmentSolver.solve(matrix, unassigned_costs)
        candidate = build_assignment_plan(candidate, resource_count=len(resources), target_count=len(tracks))
        candidate.human_authorization_state = self.config.human_authorization_state
        if previous_plan is None:  # 仅首次调用允许
            remember_latest_plan(candidate)
            return candidate
        candidate = apply_hysteresis(candidate, previous_plan, matrix, timestamp)
        remember_latest_plan(candidate)
        return candidate

class HysteresisManager:
    def apply(self, candidate, previous):
        old_cost = rescore_previous_assignment_on_current_matrix(previous)
        if previous_infeasible:
            return accept(candidate, "accepted_previous_infeasible")
        if not enough_gain_or_dwell_or_change_budget(candidate, old_cost):
            return keep_previous_assignments_with_new_version("held_by_hysteresis")
        return accept(candidate, "accepted_gain_and_dwell")
```

当前实现只以已发布计划执行 stale 校验；`publish=False` 候选不推进 latest，`publish_plan()` 才提交 identity。同执行签名刷新保留 `plan_id/version/created_at`、`identity_created_at_s` 和 assignment `plan_version`，但 plan/assignment metadata 的 `last_evaluated_at_s` 始终更新为本轮 `plan()` timestamp；forced no-change 同样只刷新该活性时间，真实身份变化时两者更新。record/evidence/binding 发布快照均可读取两个时间。forced replan 分别输出 `replan_ack_no_change` 或 `replan_applied`。switch penalty 仍在 solve 前进入 `CostMatrixResult`，每轮 N/M 规模和 evidence 字段保持输出。

---

## 7. 重分配触发条件

| 触发 | 说明 |
|------|------|
| 新目标确认 | `tentative -> confirmed/engageable` |
| 航迹质量变化 | 协方差发散或重新稳定 |
| 资源状态变化 | 资源失效、忙碌、通信降级 |
| 末端配准失败 | D5返回 `ambiguous/hold/reacquire` |
| 被动中心降级 | D4进入 `suspect/failed` |
| 主动降级风险 | 中心仍在线，但计划年龄、延迟、成本或末端一致性已不满足有效性要求 |
| 计划收益足够 | 新方案改善超过迟滞阈值 |

---

## 8. 主动降级与末端反馈下的分配约束

D4 现在区分被动降级和主动降级。被动降级来自中心节点心跳、通信或进程失效；主动降级发生在中心节点仍工作，但 D3 发现当前 `AssignmentPlan` 在态势上已经不可靠，例如定位误差增大、关联不确定性升高、计划版本过期、assignment 成本快速恶化，或 D5 末端视觉连续反馈不一致。

D3 在该场景下的职责不是直接选择二级节点或完全分布式方案，也不是自动调用 D4 action，而是输出可审计的计划有效性证据，并约束下游不得本地改绑：

```text
D5 末端反馈 -> D3 计划有效性评估 -> keep / hold / replan / secondary_arbitration
```

### 8.1 D5 不一致时的处理原则

当 D5 发现末端视觉关联与中心或二级节点分配不一致时，D3 应按保守顺序处理：

1. `hold`: 若只是单帧模糊、短时遮挡、局部 MOT 未稳定，D3 保持原 `assigned_global_track_id`，把对应资源置为暂缓确认，不允许本地无人机自行改绑 `global_track_id`。
2. `replan`: 若 D5 连续反馈目标不可见、视场代价显著升高，但 D2 航迹仍稳定，D3 重新计算中心 `AssignmentPlan`，提高该资源-目标边的 `fov_confirmation_difficulty` 或设置临时禁配边。
3. `secondary_arbitration`: 若 D5 多帧不一致，且 D2 关联不确定性或 D1 定位协方差同时升高，D3 请求 D4 进入主动降级仲裁，优先交给覆盖该区域的二级侦察节点复核。
4. `distributed_arbitration`: 若中心和二级节点都无法形成一致计划，D3 只输出失效证据，由 D4 降级到完全分布式协同；D3 不直接发布分布式任务结果。

核心约束：D5 可以报告 `ambiguous`、`hold`、`reacquire`、`friend_overlap_hold` 和候选视觉证据，但不能把本地视觉最近目标直接替换为新的 `global_track_id`。D3 只能接受来自 D2/D4 统一数据总线的全局 ID 和版本化计划。

### 8.2 D3 给 D4 的主动降级触发量

D3 应向 D4 发布或记录以下 `AssignmentValiditySummary` 字段，用于主动降级仲裁：

| 触发量 | 含义 | 建议用途 |
|---|---|---|
| `plan_age` | 当前计划从 `created_at` 到评估时刻的年龄 | 超过 2-3 个规划周期时触发中心重分配检查 |
| `assignment_latency` | 从 D2 航迹时间戳到 D3 计划发布时间的端到端延迟 | 延迟持续升高时降低计划置信度 |
| `cost_margin` | 当前候选计划与旧计划的成本差或比值 | 判断是否值得中心重分配 |
| `reassignment_hysteresis` | 迟滞保持次数、最小保持时间和收益门限状态 | 区分正常防抖与持续无法切换 |
| `stale_plan_version` | 调用方或下游使用的版本是否落后于 D3 最新版本 | stale 计划必须被拒绝，不得覆盖新计划 |
| `duplicate_assignment_count` | 同一目标或同一资源被重复分配的异常计数 | 非零时请求 D4 仲裁或进入 hold |
| `unassigned_high_threat_count` | 高优先级目标未分配数量 | 持续非零时触发重分配或主动降级 |

建议 D4 解释这些字段时采用分层判断：

```text
valid -> central_replan -> secondary_arbitration -> distributed_arbitration -> hold_for_observation
```

如果 `cost_margin` 显示中心 Hungarian 可以显著改善，且 `stale_plan_version=False`，应由 main/D4 优先触发 `request_center_replan`。当前 main runtime 已在触发后再次调用 D3，并记录新的 `active_plan_owner=center`、`plan_id/version`、`replan_reason`、superseded previous plan 和 stale/rejected plan 归因。如果 `assignment_latency`、`stale_plan_version`、`duplicate_assignment_count` 或 D5 多帧不一致同时出现，应请求 D4 主动降级仲裁。D3 当前只给出 summary、metadata、feedback writeback 和 secondary takeover DTO，不直接执行 `request_center_replan`、`degrade_to_secondary` 或 `degrade_to_distributed`。

### 8.3 D3 与 D7 比例导引的接口

D7 比例导引只应消费 D3/D4 确认过的版本化分配，不应自行选择目标。D3 当前输出给 D7 的接口是 `AssignmentGuidanceBinding`：

```text
AssignmentGuidanceBinding
- assigned_global_track_id
- resource_id
- plan_id
- plan_version
- guidance_phase: midcourse | terminal_visual
- assignment_validity_state
- human_authorization_state
```

中段 PN 使用 `assigned_global_track_id` 对应的 D2/D1 航迹预测作为导引目标；进入末端视觉 PNG 后，D7 必须继承同一个 `global_track_id`。如果 D5 在末端发现视觉目标与该 `global_track_id` 不一致，D7 不得切换目标，而应进入 `hold/reacquire`，并把不一致事件回传 D5/D3/D4。

因此 D3 到 D7 的约束是：

- `plan_version` 必须与当前数据总线版本一致。
- 新 current plan binding 即使资源-目标发生变化仍为 `active/current`；旧 plan 通过 latest `plan_id/version` gate 失效，不把新 binding 标记为 `superseded`。
- `assigned_global_track_id` 在中段和末端保持一致。
- `guidance_phase` 只描述仿真阶段，不代表真实控制或处置命令。
- `human_authorization_state` 来自 `PlannerConfig`，默认 `required`，也可由外部授权/仿真记录层显式设置；D3 不提供绕过授权字段。
- D4 action 为 `request_center_replan`、`degrade_to_secondary` 或 `degrade_to_distributed` 时，D7 应阻断视觉 PNG。
- D5 terminal association 未达到 `locked` 或 binding 为 `stale/revoked/hold/reassigned` 时，D7 不得进入目标重绑。

---

## 9. N 配置滚动重分配执行顺序与迟滞原则

### 9.1 2v2 场景

2v2 适合做最小闭环测试，重点验证 ID 稳定、版本号、迟滞和 D5 末端反馈；它和 5v5 一样都不是算法常量：

1. D2 输出两个稳定 `global_track_id`，D3 构建 2x2 成本矩阵。
2. D3 使用 Hungarian 生成初始 `AssignmentPlan(version=1)`。
3. 若 D5 两个资源均返回一致锁定，D3 保持计划，除非新计划收益超过 `delta` 且满足 `min_dwell`。
4. 若一个资源末端模糊，D3 对该边提高 `fov_confirmation_difficulty`，先进入 `hold` 或中心重分配。
5. 若两个目标交叉导致 D5 与 D2 同时不稳定，D3 不允许本地换绑，输出主动降级证据给 D4。

2v2 默认迟滞建议：`delta=0.2`，`min_dwell=2` 个规划周期，单窗口最多允许 1 条 assignment 变化。这样可以清楚观察每一次换配的原因。

### 9.2 N 对 N 场景

运行时 N 由 main `--drone-count` 统一设置，5v5 是基准示例。重点是避免频繁抖动、重复分配和高优先级目标长期未分配：

1. D2 输出 N 个或更多 `GlobalTrack`，D3 过滤 `confirmed/engageable` 航迹。
2. D3 将资源状态、D5 视场难度、D1/D2 协方差和冲突风险合成成本矩阵。
3. 中心节点正常时，每个规划周期先计算候选 Hungarian 计划，但不立即替换旧计划。
4. 若旧计划仍可行，只有满足 `J_new < (1-delta) * J_old`、`dwell_time > min_dwell`、`change_count <= max_changes_per_window` 才接受换配。
5. 若旧计划不可行，例如资源失效、目标 dropped、禁配边出现，则允许绕过收益门限，标记 `accepted_previous_infeasible`。
6. 若 D5 多视角关联与中心/二级计划连续不一致，D3 请求 D4 `secondary_arbitration`，而不是在本地资源之间直接重写 `global_track_id`。
7. 若二级节点也无法提供一致计划，D4 才进入完全分布式协同；D3 只保留最新中心计划作为回滚和审计基线。二级 takeover 的 D3 规则要求 concrete owner、持续 readiness、精确 supersede、严格 version/epoch 和 live lease；secondary binding 只有显式匹配 current plan 且 lease 有效时才是 `active/current`。节点选择、租约续期和中心恢复仍由 D4/main 定义。

N 对 N 基准迟滞建议可从 5v5 参数开始扫描：`delta=0.2`，`min_dwell=2.0s`，`max_changes_per_window=2`，连续 3 次 `held_by_hysteresis` 且 D5 不一致时请求 D4 主动降级仲裁。后续 P1 校准应跨真实多 seed 统计 `resource_count`、`target_count`、`reassignment_count`、`duplicate_assignment_count`、`unassigned_high_threat_count`、`stale_plan_version_count`、`secondary_arbitration_count`、center/secondary owner/version/source 变更，并用 P1 calibration sweep 的 D6 assignment records 和标准报告 bundle 反向标定 D5 feedback 权重阈值。

---

## 10. 离线验证

当前已实现的离线验证覆盖 Hungarian/fallback、demand-slot M-to-N、execution identity/publish semantics、forced replan、solve 前 switch penalty、matrix/breakdown/objective/evidence 一致性、迟滞/stale、coalition binding/duplicate、保守增量规划与全量回退、版本化 transient feedback dwell、reserve-soft-feedback primary role protection、D5 feedback、secondary takeover/continuation、D6 export、synthetic AirSim dry-run adapter，以及同输入容量约束 SciPy/optional flow benchmark。当前全量基线为 `123 passed, 1 skipped`，唯一 skip 是未安装 optional OR-Tools 的 installed-only 测试。真实 10-seed CV 已将 role-aware 结果推进到 8/10，并完成二级/分布式 commit 正例和缺 ACK fail-closed，P1 合同层闭合。下一阶段聚焦 15 s 诊断所暴露的物理断点、3v5/5v3 与动态事件参数标定；P2 只运行隔离 benchmark：

```text
Hungarian without hysteresis
Hungarian with hysteresis
MinCostFlow same-input capacity comparator # P2 optional，对照后端
```

指标：

```text
total_assignment_cost
reassignment_count
average_assignment_hold_time
duplicate_assignment_count
unassigned_high_threat_count
version_conflict_count
single_window_runtime_ms
secondary_arbitration_count
stale_plan_version_count
secondary_plan_activation_count
```

---

## 11. 交付物

1. 动态分配策略综述。
2. SciPy 与 OR-Tools 选型对比。
3. `AssignmentPlanner`、`AssignmentPlan`、`ResourceState` 数据结构。
4. 迟滞重分配算法设计。
5. 离线批量验证脚本方案和报告模板。
6. 面向 D4 主动降级的 `AssignmentValiditySummary` 字段建议。
7. 面向 D7 PN 的 `AssignmentGuidanceBinding` 接口建议。

---

## 12. 参考资料

- SciPy `linear_sum_assignment`: <https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.linear_sum_assignment.html>
- OR-Tools Min Cost Flow: <https://developers.google.com/optimization/flow/mincostflow>
- OR-Tools assignment as min-cost flow: <https://developers.google.com/optimization/flow/assignment_min_cost_flow>
- Dynamic WTA rolling horizon example: <https://www.mdpi.com/2079-9292/9/9/1511>
- TAPF dynamic assignment discussion: <https://arxiv.org/html/2307.00663v1>

---

## 13. M 对 N 联盟分配与时序调度复核（2026-07-11）

详细中文调研见 `subagent_reviews/D3_M_TO_N_ASSIGNMENT_AND_SCHEDULING_REVIEW.md`，共核验 12 篇主要论文、1 篇补充综述、4 个成熟优化工具和 6 个 MRTA/联盟研究仓库。Google Scholar 仅用于发现；引用回到 DOI/论文原始页。当前无 WOS 订阅或导出数据，因此没有把 WOS 覆盖作为完成条件。

复核后的关键修正是：原 D3 “非等量 N/M”只是矩阵规模非方阵，仍是一对一分配；高威胁目标需要三架资源属于 `k_j>1` coalition allocation。该合同和 demand-slot baseline 已于 2026-07-11 实现，复杂 CP-SAT/MILP 全局参考仍未实现。

### 13.1 算法选型结论

- `k_j=1`: 继续使用 SciPy Hungarian 默认主线。
- 只有基数/容量/禁配边且成本可加：b-matching 或 Min-Cost Flow 是成熟升级基线。
- 要求“完整三机联盟才激活”、异构能力、同步窗口、波次、主备和冲突约束：使用 CP-SAT/MILP 参考模型。
- coalition formation 启发式和时序逻辑联合规划保留为研究方案；没有成熟开源库能直接覆盖 MSM 的版本、迟滞、D4/D5/D7 合同。
- 初始仿真默认建议 `hybrid 2+1`，但 primary 数由 `TargetDemand.primary_resource_count` 显式配置并接收 main `--cooperative-primary-count`；并与 `simultaneous 3`、`sequential 1+1+1` 同条件比较。该建议不是固定工程共识。

### 13.2 当前缺口与模块边界

已实现 `required_resource_count`、`primary_resource_count`、coalition identity/version/state、成员 role/wave/window、demand satisfaction、能力槽、simultaneous/sequential/hybrid baseline、coalition-aware duplicate 语义和 D7 多成员 current binding。显式 `TargetDemand()` 才启用默认 `k=3 hybrid 2+1`；缺省仍为 `k=1 independent primary=1`。hybrid 使用显式 primary 数，且该值进入 demand template、coalition signature/version 和 binding metadata。不完整 coalition 不发布 executable assignment，合法 `<=k_j` multiplicity 不计 duplicate。

迟滞、change count、switch penalty 与 reassign export 已转为 stable signature/set 语义；成员/角色/window/demand 模板变化递增 coalition version，旧 binding 由 current identity gate stale。OR-Tools flow 是 optional benchmark，不进入默认依赖或默认 planner。

当前合同缺口已关闭；剩余研究项是物理闭环所需的真实 ETA/同步动力学、长时多 seed 参数标定和 D6 coalition 指标长期分析。CP-SAT/MILP 小规模参考、复杂 flow 与大规模扫描仅为 P2 隔离 benchmark。D3 不执行协同定位；D1/D2/D5 负责多源/多视角定位与身份连续性，D3 仅调度角色并消费协方差和几何收益。

### 13.3 新增主要证据

- One-to-many coalition matching: <https://doi.org/10.1109/ICRA.2019.8793855>
- Coalition deadlines/interference: <https://doi.org/10.1371/journal.pone.0170659>
- Communication-aware distributed coalition: <https://doi.org/10.1109/ACCESS.2021.3061149>
- Team/coalition MRTA survey: <https://doi.org/10.1007/s43154-022-00087-4>
- Coalition formation survey: <https://doi.org/10.3390/robotics14070093>
- Simultaneous allocation/planning: <https://doi.org/10.1177/0278364918774135>
- Temporal/ordering taxonomy: <https://doi.org/10.1016/j.robot.2016.10.008>
- Temporospatial team scheduling: <https://doi.org/10.1109/TRO.2018.2795034>
- Group-based distributed auctions: <https://doi.org/10.1109/TASE.2022.3175040>
- Distributed multi-task assignment: <https://doi.org/10.1109/TCYB.2015.2418052>
- CBBA foundation: <https://doi.org/10.1109/TRO.2009.2022423>
- Synchronization modeling: <https://doi.org/10.1287/trsc.1110.0400>
