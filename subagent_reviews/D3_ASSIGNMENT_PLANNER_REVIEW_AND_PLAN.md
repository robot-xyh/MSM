# D3 中心化资源-目标分配综述及子方案

**定位**: 在由 main runtime `--drone-count` 决定的 N 对 N 或非等量资源/目标场景中，由中心节点生成滚动 `AssignmentPlan`，并通过迟滞逻辑避免频繁重分配；5v5 只作为示例和基准场景。
**边界**: 本文只讨论抽象资源-目标匹配、离线评估和人工授权前的候选计划，不包含真实火控参数、毁伤模型或自动处置流程。
**D3 复核状态 2026-07-14**: active-plan 连续性、execution-signature identity、candidate/published 分离、forced replan ack/applied、solve 前 switch penalty、secondary activation/current-binding、same-owner continuation、M-to-N demand-slot、保守增量规划、feedback soft/hard 分级、transient feedback dwell、role-aware primary 保持和 canonical planning-tick history schema/export 均已关闭。普通 ambiguous/hold/reacquire 不再升级为资源 `operator_hold`，且 transient 窗口不能绕过 `min_dwell`。M5N2 采用 `2 primary + 1 standby reserve`，不要求两个 primary 同时到达。真实 SimpleFlight 已完成 baseline 与三个候选各 10 seeds、共 40 个 episode；coalition completion 依次为 `0/10`、`5/10`、`2/10`、`1/10`，最佳 `20 m / 3 s / 40 deg` profile 未达到 `8/10`。版本/stale/role 合同及 reserve 安全保持；P1 开放项转为 main history 写盘与 D6 churn 消费、D5 feedback 权重/迟滞和动态 N/M 标定。P2 仅为隔离 optional benchmark。

**P1 switch-penalty 状态 2026-07-10**: done。`reassignment_switch_penalty` 已从 solve 后追加改为 solve 前进入可行改配边；同 resource、不可行边、无历史 assignment 的 target 和 unassigned cost 不变。solver matrix、breakdown total、objective、Assignment 和 evidence 使用同一成本且无双重计费。新 current plan binding 即使发生改配仍为 `active/current`，旧 plan 由 current plan id/version gate 失效。

当前 D3 P0/P1 缺口清单：

- P0 done：旧“无 P0 blocker”结论已撤销；active plan 后缺失 `previous_plan` 的版本回退入口已关闭，拒绝 reason 固定为 `previous_plan_required` 并返回 latest plan id/version。首次调用仍允许 `None`，新 episode 使用新 planner 实例。
- P1 done：switch penalty 已在 Hungarian/fallback solve 前加入可行改配边，matrix/breakdown/objective/evidence 单次计费一致；unassigned/release 和 current binding 语义不变。
- P1 合同层 done：5-resource/2-target ComputerVision 10 seeds 中，T001 双 primary 视觉共识与当前计划授权达到 8/10；seeds 7/27 保留回归。
- P1 下游合同证据 done：二级接管和完全分布式 commit 正例通过；缺 ACK 时 coalition aborted、D7 许可为 0，fail-closed 通过。该结果不等于物理拦截。
- P1 transient feedback dwell done：`primary_lock_stability_incomplete`/短暂 reacquire 只在 source plan version 匹配、旧 primary 仍可行且无硬冲突时保护 coalition primary；effective window 为 D3 配置和上游 required stable frames 的最大值，窗口完成后 soft candidate 仍受 coalition/global `min_dwell` 约束，硬风险可立即换员。
- P1 reserve role protection done：若所有旧 primary 都是同版本 `consistent/continue`，且旧 reserve 仅为普通 `hold/hold` 或 `reacquire/replan`，D3 从 previous assignment role 推导 primary pins，只重解 reserve candidate；实际替换仍需迟滞放行，不要求 main 提供 reason/required/member_role。
- P1 feedback 分级 root-cause fix done：ordinary ambiguous/hold/reacquire、几何/FOV/检测不稳定为 edge-soft；friend overlap/verified friend、身份安全冲突、duplicate 和显式 feasibility reject 保持 fail-closed。分类审计兼容旧 metadata。
- P1 canonical history schema/export done：`PlanningTickHistoryRecord` / `plan_history_record_from_plan(...)` 输出 `d3_plan_history_record_v1`，以 main 提供的 `[sequence_index, timestamp]` 排序，聚合 ordered assignment/coalition、owner/epoch/lease、迟滞/成员变化、soft/hard feedback、成本和 stale/rollback/replan 审计；严格 JSON 且排除 truth 字段。
- P1 evidence update：历史 40-case 保留为旧预筛；最新 M5N2 baseline/candidate 各 10 seeds 已由 main 写盘 canonical history。20/20 case、3725/3725 record 可用，plan-version/member-roster/owner transition 均为 0；membership audit 数量不得直接当成 churn。物理第二 primary/coalition 仍开放。
- P1：D5 feedback 权重与 dwell/迟滞阈值仍需用逐时刻 D6 records 配对标定。
- P1 增量接口 done：输入快照、changed-set 完整性、独立连通分量局部求解、全量 fallback reason、全局迟滞、M-to-N all-or-none 和增量/全量 comparison summary 已测试；仍缺真实非等量 3v5/5v3、目标新增、资源失效和 crossing/dense 动态 N/M 多 seed 校准。
- P1 deterministic calibration support done：versioned 8-scenario matrix 新增高威胁需求变化、D5 reserve feedback 和 hard-window；paired runner 统一比较 full/incremental latency、churn、unassigned high-threat、coalition shortfall 和 fallback/reject，8/8 转换 assignment/cost 等价。
- P1：D3 secondary activation/current-binding 合同已闭合，并已由二级/分布式 commit 正例与缺 ACK fail-closed 覆盖下游消费；D4 协商与恢复策略仍属 D4/main 边界。
- Optional benchmark done：OR-Tools 同输入 Min-Cost Flow 接口已实现，不是待关闭 P1；CP-SAT/MILP、复杂 flow 和大规模扫描保留为 P2 optional。

---

## 0. 当前代码状态摘要

截至 2026-07-13，D3 代码已经实现：

- SciPy Hungarian / `linear_sum_assignment` 主线，带 dummy unassignment 列。
- 无 SciPy 时的小规模 `FallbackAssignmentSolver` 位掩码 DP fallback。
- `AssignmentPlan(plan_id, version, window_id, resource_count, target_count)` 和 `assignment_matrix_shape` 规模 metadata。
- `StalePlanError`，拒绝 active plan 后缺失的 `previous_plan`、旧 `previous_plan`、旧 `plan_id` 或不匹配的 `expected_previous_version`。
- 迟滞重分配：`delta`、`min_dwell`、`max_changes_per_window`；`reassignment_switch_penalty` 在 solver 前进入候选 matrix，不再 solve 后补账。
- D5 terminal feedback helper，始终 `allow_local_rebind=False`。
- D7 `AssignmentGuidanceBinding`，携带 `assigned_global_track_id`、`plan_version`、binding state、source/target/link 和 `allow_local_rebind=False`。
- `AssignmentValiditySummary` 和 D6-compatible `AssignmentRecord` 导出；assignment records 携带 multi-seed 分组所需的 owner/source/schema、replan/takeover reason、previous/supersede、secondary owner/version/epoch/lease/readiness/activation、迟滞决策、矩阵规模、cost gap 和 N/M mismatch replay 字段。
- M5N2 逐 pair 诊断已统一：record/binding 同时输出 plan owner/version、coalition id/version/epoch、role/wave/activation/validity、per-primary 授权资格及 churn/rollback/stale reject；两个 primary 独立 active，reserve 固定 standby/hold。纯 current evaluation refresh 输出零 churn、无 rollback，并保持 plan identity 与 coalition epoch。
- `AssignmentEvidenceExport` 导出 current plan id/version/owner/source、完整 current cost matrix、per-edge cost breakdown、hard rejected edges/reasons、stale rejection reason，以及 secondary readiness/activation/owner/version/epoch/lease/supersede 字段。
- `PlanningTickHistoryRecord` 把每 tick 的 plan/count/owner/lineage/cost 字段集中记录一次，稳定排序 assignment 和可恢复 coalition members，并附迟滞、成员变化、feedback classification/count、stale/rollback/replan reason；`to_dict()` 为 JSON-native 且无在线 truth 字段。旧 `assignment_records_from_plan()` 保持兼容。
- 轻量 hard time-window baseline：显式 closed/expired/not-yet-open 的边会被 hard rejected，不进入最终 assignment，`window_cost` 继续作为 open edge 软排序项。
- synthetic AirSim dry-run adapter，不 import AirSim，不控制 Blocks runtime。
- `PlannerConfig.human_authorization_state` 透传到 `AssignmentPlan.human_authorization_state`，并写入 `configured_human_authorization_state` / `effective_human_authorization_state` metadata。
- `apply_terminal_feedback_to_planner_inputs()` 将 D5 metadata 分为 edge-soft/edge-hard/resource-hard/target-hard，并写回下一轮 `TargetTrack[]/ResourceState[]`；保留 source plan version、coalition reason/conflict、stable counts、required window 和 classification audit。普通 pair hold 不再扩大为 resource hold；full/incremental planner 共用不绕过标准迟滞的 transient primary dwell。
- `prepare_secondary_takeover_plan()` 在 D4/main 已选定具体二级节点且持续 `takeover_ready` 后，校验精确 supersede、严格 version/epoch 和 live lease，再生成 active `secondary_plan_v2`；D7 secondary binding 还必须显式匹配 current plan，过期或历史计划不可执行。
- `summarize_terminal_feedback_calibration()` 和 `summarize_assignment_mismatch_replay()` 已支持多 seed feedback/assignment replay 汇总，只输出调参建议和 replay 计数，不修改默认权重或迟滞参数。

当前只是部分实现或未实现：

- `MinCostFlowAssignmentSolver` 支持 optional OR-Tools 资源容量；隔离 runner 用同一非等量 N/M、hybrid demand-slot 输入比较 SciPy 与 flow，未安装时输出结构化 `unavailable_reason`，不进入默认依赖或 planner。
- `secondary_plan_v2` 的 D3 activation/current-binding 合同已实现；main runtime 仍需传入 sustained readiness、activation time、leader epoch、live lease 和 current plan identity。二级节点选择、lease 续期、中心恢复合并和 active owner runtime 仲裁仍属 D4/main policy。
- D4 `request_center_replan`、`degrade_to_secondary`、`degrade_to_distributed` 仍由 main/D4 消费 D3 证据后触发，D3 不自动调用；其中中心 `request_center_replan` 的 owner/version/supersede runtime 记录已由 main 接线，D3 只需保持版本化计划和 stale 拒绝合同。
- 剩余 D3 P1 是基于已写盘 history 的真实动态 N/M 标定、D5 feedback/迟滞权重、hard-window 多场景和完整动态威胁；最新 M5N2 的 history/churn availability 不再是缺口。secondary 只剩跨模块 runtime 验证，不再是 D3 DTO 缺口。
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

当前实现只以已发布计划执行 stale 校验；`publish=False` 候选不推进 latest，`publish_plan()` 才提交 identity。纯成本/诊断重评不属于可执行计划变化：`k=1` 与 `k>1` 均保留 `plan_id/version/created_at`、assignment version 和 coalition epoch，写入 `evaluation_refresh_only=True`，仅更新当前成本证据与 `last_evaluated_at_s`。资源、角色、目标、owner、授权或 activation 变化才推进执行版本；secondary takeover 明确建立新 lineage。record/evidence/binding 始终透传稳定 current identity。

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
4. 若旧计划仍可行，只有满足 `J_new < (1-delta) * J_old`、`dwell_time > min_dwell`、`changes_used_in_window + change_count <= max_changes_per_window` 才接受换配。
5. 若旧计划不可行，例如资源失效、目标 dropped、禁配边出现，则允许绕过收益门限，标记 `accepted_previous_infeasible`。
6. 若 D5 多视角关联与中心/二级计划连续不一致，D3 请求 D4 `secondary_arbitration`，而不是在本地资源之间直接重写 `global_track_id`。
7. 若二级节点也无法提供一致计划，D4 才进入完全分布式协同；D3 只保留最新中心计划作为回滚和审计基线。二级 takeover 的 D3 规则要求 concrete owner、持续 readiness、精确 supersede、严格 version/epoch 和 live lease；secondary binding 只有显式匹配 current plan 且 lease 有效时才是 `active/current`。节点选择、租约续期和中心恢复仍由 D4/main 定义。

N 对 N 基准迟滞建议可从 5v5 参数开始扫描：`delta=0.2`，`min_dwell=2.0s`，`max_changes_per_window=2`，连续 3 次 `held_by_hysteresis` 且 D5 不一致时请求 D4 主动降级仲裁。后续 P1 校准应跨真实多 seed 统计 `resource_count`、`target_count`、`reassignment_count`、`duplicate_assignment_count`、`unassigned_high_threat_count`、`stale_plan_version_count`、`secondary_arbitration_count`、center/secondary owner/version/source 变更，并用 P1 calibration sweep 的 D6 assignment records 和标准报告 bundle 反向标定 D5 feedback 权重阈值。

---

## 10. 离线验证

当前已实现的离线验证覆盖 Hungarian/fallback、demand-slot M-to-N、execution identity/publish semantics、forced replan、solve 前 switch penalty、matrix/breakdown/objective/evidence 一致性、迟滞/stale、coalition binding/duplicate、保守增量规划与全量回退、feedback soft/hard 分级、版本化 transient feedback dwell、reserve-soft-feedback primary role protection、secondary takeover/continuation、D6 export、canonical planning-tick history、synthetic AirSim dry-run adapter，以及同输入容量约束 SciPy/optional flow benchmark。8-scenario P1 runner 对 full/incremental 路径给出 8/8 assignment/cost 等价；2026-07-14 另有 5 个 canonical history、3 个 held-scope/lifecycle case 和 5 个累计预算/统一成本/硬失效测试函数。当前全量基线为 `157 passed, 1 skipped`，唯一 skip 是未安装 optional OR-Tools 的 installed-only 测试。真实 SimpleFlight M5N2 物理性能结果仍沿用既有报告，尚待本次跨模块修复后重跑。

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

迟滞、change count、switch penalty 与 reassign export 已转为 stable signature/set 语义。当前 `k>1` 成员至少保持 2 s；只有成员硬不可行，或候选联盟成本改善超过 20%且 dwell 满足时才替换。普通成本/诊断刷新不推进 plan identity；成员或角色变化才推进 coalition version/epoch。只有真实可执行版本变化才使旧 binding stale。OR-Tools flow 是 optional benchmark，不进入默认依赖或默认 planner。

当前合同缺口已关闭；40 个真实 SimpleFlight M5N2 episode 已完成，但最佳 coalition completion 仅 `5/10`。本轮 feedback 修复只证明一个可导致 churn 的合同根因已消除；D3 虽已提供 canonical history schema/export，既有 40-case 仍没有 main 写盘记录，不能声明该根因已被证实造成既有结果。剩余 P1 是 main 写盘/D6 churn、D5 feedback 权重/迟滞和动态 N/M 标定。CP-SAT/MILP 小规模参考、复杂 flow 与大规模扫描仅为 P2 隔离 benchmark。

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

---

## 14. M5N2 协同候选预筛接口（2026-07-12）

D3 已补充独立的 `cooperative_prescreen` 层，但没有改变 Hungarian 或 demand-slot 求解。该层把下一阶段实验拆成三个明确边界：

1. **候选定义**：固定形成 `20/30/40 m x 3/5/8 s x 20/40/60 deg` 共 27 组稳定 candidate；候选不携带固定资源数或目标数。
2. **计划元数据**：在调用方的 `TargetDemand` 和当前 `AssignmentPlan` 上保留 required/primary 数、arrival window、wave、minimum separation、member role、plan/coalition version。hybrid reserve 导出为 standby，不因候选入选而激活。
3. **实测排序**：main/D6 必须提供每组实际 safety violation、coalition completion、pair success 和 arrival spread。D3 不补齐缺失观测，不用规划代价冒充物理命中；固定排序后只返回前三候选。

版本安全采用 fail-closed：导出时必须显式给出 current plan id/version，且 assignment/coalition version 与 committed coalition 一致。该接口可供 main runtime 和 D6 序列化消费，但不控制 AirSim、不决定物理可达，也不修改 D7 PN/PNG。

真实 AirSim 验收已于 2026-07-13 运行：baseline 与前三候选各 10 seeds，共 40 个 SimpleFlight episode。高威胁目标保持 `2 primary + 1 standby reserve`，两个 active primary 分别统计合同许可与 5 m 结果，不把同时到达作为成功前提。coalition completion 为 baseline `0/10`、最佳 `20 m / 3 s / 40 deg` `5/10`、其余 `2/10` 和 `1/10`，未达到 `8/10`；reserve 越权、stale/role 合同和身份改写安全约束保持。

D6 已能展开全部 40 case，D3 也已提供 canonical `d3_plan_history_record_v1` exporter；但正式 aggregate 没有 main 写盘的逐 tick records，因而 membership/version churn 仍为 `unavailable`，不能补零。下一阶段 main 调用 `plan_history_record_from_plan(...).to_dict()` 写盘，D6 按 `[sequence_index, timestamp]` 消费，D3 再据此标定 D5 feedback 权重、`delta/min_dwell/reassignment_switch_penalty` 和动态 N/M 场景。

---

## 15. Per-primary 授权与成员迟滞复核（2026-07-12）

本阶段明确不把“同时到达”作为 D3 授权条件。高威胁目标仍分配两个 primary 和一个 reserve，但每个 primary 由自己的 D5 lock、当前 plan binding、D4 permission 和 D7 机动门控独立授权。D3 通过 `terminal_authorization_scope=per_primary` 与 `arrival_coordination_required=false` 明示该合同；reserve 只占用计划容量，其 guidance binding 保持 standby/hold。

成员稳定性采用目标级迟滞，不再用频繁 evaluation refresh 重置驻留时间。每个 coalition 保存 `membership_changed_at_s`，并审计前后成员、成员成本、改善比例、dwell 和保持依据。普通成本刷新沿用同一 `plan_id/version`，coalition epoch 保持；资源或角色真正改变时才增加 epoch。真实 M5N2 连续三 tick 回归固定为同一 A/v1，而不是 `{v1,v2}`。该实现不改变 Hungarian/demand-slot 求解器。

逐 pair 审计不改变执行策略：`AssignmentRecord.active` 只对可行 active primary 为 true，reserve 即使占用 demand slot 也保持 false；D7 binding 对 reserve 输出 `hold/revoke_reason=reserve_standby_not_activated`。main/D6 可据 `plan_churn_count`、`plan_rollback_detected`、`stale_reject_count` 区分成员实质变化、非法 identity 回退和旧计划拒绝。

---

## 16. 真实 Seed 001 分配链复核（2026-07-14）

main 已保存的 349 条计划历史证明 canonical exporter 已接入实际 episode。最终 5 个
pair 不是 D3 写死 M5N2：T001 需求为 3、T002 需求为 1，D2 后段又提交 T008，D3
因此形成第 5 个 assignment。T008 在 confirmed 时即进入 adapter 的 assignable
输入，早于 engageable 一帧；其根因是 D2/main 生命周期准入，而不是 Hungarian
demand-slot 重复分配。

D3 本轮修复 held plan scope 泄漏。保持状态现在不改变 plan identity，候选新目标
只作为 audit evidence；释放仍必须通过原有 hard infeasible、gain+dwell 或高威胁
条件。没有修改高威胁需求、M-to-N 槽位、stale 检查、coalition 完整性或授权门控。
若上一已分配目标从当前输入消失，则 previous plan 明确不可行，不能继续 hold；D3
发布新版本并记录 `previous_missing_execution_target_ids`。

该 episode 的 v1-v31 周期性成员切换均满足 `min_dwell=1 s` 和 `delta=0.2`，形式上
合法但工程上抖动过大。下一步不是再加 D3 隐式目标过滤，而是 main 先修 lifecycle
admission，再以 10 seeds 扫描 `min_dwell >= 2 s`、change budget 和 switch penalty；
验收时高威胁未分配率不能恶化。reserve active 的异常也必须在 runtime binding
同步处修复，因为 D3 v45 仍明确输出 standby reserve。

---

## 17. 最新 347-record 计划抖动关闭结论（2026-07-14）

最新 truth-isolated M5N2 seed 1 有 347 条 planning records、执行版本 v1..v35，
仍显示约每秒往返换员。直接根因不是 Hungarian 规模或 stale identity，而是两层
治理同时缺失：`max_changes_per_window` 只比较单次 candidate；membership/global
gain 又把 candidate demand-slot/search objective 与 previous current-edge objective
混比。soft feedback 会只抬高当前成员边，下一成员因没有同一 shaping 而看似每次都
改善超过 20%。

本轮实现将求解和迟滞比较分层：求解继续保留 switch penalty、soft-feedback FOV、
slot priority 和 role pin；迟滞 comparison 同时把 candidate/previous 投影到当前
base execution objective，只保留基础边成本、硬可行性和当前 demand/unassigned。
同一 `window_id` 的已接受 change count 通过 plan metadata 累计，普通 hold/refresh
不计费，跨 window 恢复。硬目标消失、资源 unavailable 和 plan-level
owner/activation/authorization 变化仍优先发布新 identity；联盟角色候选不作为外部
activation 绕过成员迟滞。

确定性验收新增 5 个测试函数，覆盖往返噪声/soft feedback、累计预算、跨窗口恢复、
资源硬失效、missing + membership hold、owner fail-closed 和 history 导出。全量
`157 passed, 1 skipped`，零失败达到阈值；optional OR-Tools 是唯一 skip。未重跑
Blocks，所以 D3-owned 实现 P1 已关闭，但真实至少 10 seeds 的 churn/high-threat
unassigned/物理完成率、D2/main lifecycle admission 和 runtime reserve demotion 仍
开放。

## 18. Actual-v2 真实 AirSim 复核（2026-07-14）

2v2 seed 1 的 command、actual、24 条 history 均为
`d3-plan-c3cc6d28c365/1`；M5N2 seed 1 的 command、actual、214 条 history 均为
`d3-plan-cfdd088a10e1/1`。D6 history available/unavailable=`2/0` 且无
validation reason，actual required cases `2/2` available，因此运行级计划身份 P0
证据链关闭。

M5N2 feedback churn=50，plan version/membership/owner churn=0。物理层
pair/target/coalition=`2/3`、`2/2`、`0/1`，第二 primary 最近约 11.02 m。
目标级 `2/2` 不得改写为联盟完成；第二 primary 和同配置多 seed 仍为 P1。

## 19. M5N2 20-Case 计划稳定性复核（2026-07-15）

本次只读分析 baseline 10 seeds 与 `candidate_soft_prediction_trend_coast` 10 seeds，
没有把额外 `png_ttc_2v2_seed001` 或未执行的 dropout case 混入聚合。20 个
`d3_plan_history.json` 共 `3725` 条记录，所有 case 的 schema、record count、计划身份、
成员、迟滞、stale 和 rollback 字段均可用。

| 观察项 | 结果 | 评审判断 |
|---|---:|---|
| 每 case current plan | 1 个，version 1 | 计划身份稳定 |
| plan/member/owner transition | 0/0/0 | actual churn 为 0 |
| membership audit | 3555 | 候选评估，不是实际换员 |
| member hold | 3524 | 未达到成员收益条件或被成员迟滞保持 |
| member pass 后 global hold | 31 | 外层迟滞继续阻断发布 |
| T001/T002 assignment | 3/1 | 2 primary+1 reserve / 1 primary |
| physical pair/target/coalition | 12/60、12/40、0/20 | 计划稳定不等于物理联盟完成 |
| 第二 primary | 0/20 | P1 open |

19 个 case 的 T001 primary 为 `INT-02/INT-03`，candidate seed 002 为
`INT-01/INT-02`，因此任何后续代码或报告都必须从 current plan 的 target/role 识别
第二 primary，不能固定为 `INT-03`。20 个第二 primary 均以 `collision_stop` 结束，
但产物没有 collision object；D3 不据此修改成本或成员选择。

candidate 未通过系统级 paired non-degradation，只能说明该候选不晋级默认路径。
baseline 与 candidate 的 D3 plan/member churn 同为 0，不能写成 D3 算法退化。后续
评估统一区分 D6 `canonical target success` 和 T001 `cooperative target diagnosis`，
后者必须单列两个 primary、第二 primary 与 coalition。

本次只改 D3 文档。模块全量测试为 `157 passed, 1 skipped`，零失败达到门限；
optional OR-Tools installed-only case 是唯一 skip，owned-path diff 检查通过。

## 20. Scalable-3D 与学习辅助复核（2026-07-20）

| 复核项 | 状态 | 结论 |
|---|---|---|
| 三维规则成本 | implemented/tested | 解析截获时间/距离、NED 协方差和区域项进入 breakdown |
| 稀疏候选图 | implemented/tested | 区域/可达性 hard gate + per-target top-k；保留 current 可行成员 |
| 3v5 / 5v3 | deterministic done | 同一 planner path，分别 3/3 和 3/5 target 获得 assignment |
| 200v200 | deterministic single sample | 200/200，800 candidates/actions，2% density；非实时验收 |
| 高威胁 M-to-N | regression done | top-k 不低于 demand，仍走 `hungarian_demand_slots` 和 all-or-none |
| 学习残差 | interface done | 仅 `C_rule+alpha*tanh(delta_C)`；shared edge MLP，不直接分配 |
| mask/fallback | deterministic done | reachability/capacity/friend/version；timeout/low confidence/OOD 回规则 |
| 版本/stale | regression done | 执行变化递增；旧 published plan 继续抛 `StalePlanError` |
| BC | minimal interface only | 32-edge synthetic warm-up；没有真实数据或 checkpoint |
| PPO | unavailable/unvalidated | 无 gymnasium/SB3，不得写成大规模 PPO 完成 |

规则主线未替换。学习 assistant 默认为可选，shadow 不改变 solver matrix；assist 也只
修正候选边成本，最终计划仍由 Hungarian/demand-slot、迟滞和版本发布链产生。硬约束
先于模型，模型不能解除不可达、容量、友方冲突、区域或 stale gate。

验证样本共新增 13 个确定性测试；全量 `170 passed, 1 skipped`，接受阈值为零失败，
skip 仅 optional OR-Tools。200v200 单次本地调用 0.621 s 只记录为单样本功能时延。
开放 P1/P2 是真实轨迹 BC 数据、checkpoint、confidence/OOD/deadline 标定、多 seed
shadow paired non-degradation、scalable simulation/AirSim 物理闭环和任何 PPO 研究。

## 21. 大规模性能和区域所有权复核（2026-07-20）

此前 200×200、top-32 的主要耗时不在 Hungarian 本身，而在求解前的 Python 全边
规则计算和解释字典构造。当前实现将核心三维规则改为 NumPy 批量计算，在候选选择后
只为 6,400 条边生成完整解释；候选图按连通分量进入局部 Hungarian。默认求解器、
M-to-N demand slot、迟滞、硬门控和学习有界残差保持不变。

同进程 5 次基准中，旧路径中位 1904.261 ms，新路径 85.367 ms，分配结果均为
200/200。20×23 语义对照通过。该数据足以关闭 D3-owned 的 Python 全边性能缺口，
不能替代 main 的 module-stack、多 seed、通信和 AirSim 时延验收。

区域计划接口遵循“D4 裁决、D3 验证和发布”。一个版本化计划可承载多个 secondary
owner 或 distributed peer owner。来源计划、epoch、lease、成员候选和 M-to-N 完整性
均为硬条件。k=1 使用 D4 单成员区域授权；提供 summary 时只接受
`single_member_authorized` 且非 atomic。k>1 继续强制 committed、atomic committed 和
全 ACK。失败时直接拒绝，不由 D3 改变降级层级。模块测试覆盖两种层级的 k=1 和
distributed k=3 正负例；main/D4 运行时映射尚未完成。

本轮 D3 全量共 194 项，结果为 `193 passed, 1 skipped`。下一步仅需 main 接入 D4
区域裁决、复跑四个 module-stack 场景并由 D6记录 owner/epoch/lease/commit 指标；D3
不继续扩展新的求解器或区域决策策略。

## 22. 故障代际 Fence 复核（2026-07-20）

50v50 中心故障暴露了重规划与故障隔离的语义差异。普通 `forced_replan=True` 在
assignment 未变时保留原版本，符合 evaluation refresh 合同；D4 owner 切换则需要
先建立严格更高的 generation。D3 现用独立 `advance_authority_generation()` 处理后者，
避免通过伪造 assignment、owner 或授权变化强制升版。

Fence 复制当前已发布计划的 assignment 和 coalition，只推进 D3 identity/version，
并记录 source lineage、原因和 D4 gate requirement。`publish_plan()` 仍拒绝普通同执行
签名新身份；fence 只有安全 metadata 和内容不变量全部通过时才获准发布。重复版本、
错误 expected version 和 coalition 篡改均被拒绝。

新增 5 个测试后 D3 全量为 `198 passed, 1 skipped`。D3-owned 阻塞已关闭。main 尚需
在 D4 `RegionalFailoverCoordinator` 重新裁决前调用 fence，并在 50v50 中验证 owner
变化、plan version/epoch 和 D7 hold/continue 的完整链路。
