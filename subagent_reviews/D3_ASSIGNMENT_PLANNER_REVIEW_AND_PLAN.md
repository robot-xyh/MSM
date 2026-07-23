# D3 中心化资源-目标分配综述及子方案

**定位**: 在由 main runtime `--drone-count` 决定的 N 对 N 或非等量资源/目标场景中，由中心节点生成滚动 `AssignmentPlan`，并通过迟滞逻辑避免频繁重分配；5v5 只作为示例和基准场景。
**边界**: 本文只讨论抽象资源-目标匹配、离线评估和人工授权前的候选计划，不包含真实火控参数、毁伤模型或自动处置流程。
**D3 复核状态 2026-07-14**: active-plan 连续性、execution-signature identity、candidate/published 分离、forced replan ack/applied、solve 前 switch penalty、secondary activation/current-binding、same-owner continuation、M-to-N demand-slot、保守增量规划、feedback soft/hard 分级、transient feedback dwell、role-aware primary 保持和 canonical planning-tick history schema/export 均已关闭。普通 ambiguous/hold/reacquire 不再升级为资源 `operator_hold`，且 transient 窗口不能绕过 `min_dwell`。M5N2 采用 `2 primary + 1 standby reserve`，不要求两个 primary 同时到达。真实 SimpleFlight 已完成 baseline 与三个候选各 10 seeds、共 40 个 episode；coalition completion 依次为 `0/10`、`5/10`、`2/10`、`1/10`，最佳 `20 m / 3 s / 40 deg` profile 未达到 `8/10`。版本/stale/role 合同及 reserve 安全保持；P1 开放项转为 main history 写盘与 D6 churn 消费、D5 feedback 权重/迟滞和动态 N/M 标定。P2 仅为隔离 optional benchmark。

**保留 seed 证据状态 2026-07-22**: nominal 5v5、duration 2.2、seeds 1000-1019 的 D3 control 精确重放阻塞已关闭，v2 正式产物已落盘并通过 D3 独立复核。D6 profile-bound v2 sidecar 状态为 `pass_offline_assignment_comparison_only`，现已把 same-frame offline assignment comparison 标为 available，关闭 D3 assignment 层可用性和独立消费缺口。runtime ACK、post-intervention physical outcome、paired physical effect/non-degradation、反事实、因果和生产晋级仍为 unavailable；PPO、assist、authority 保持 false，规则回退保持 true。

**隔离消费状态 2026-07-22**: D3 已提供独立 schema 的 plan-consumption 构造、校验与去重
账本，绑定 experiment/seed/arm、source snapshot、receipt 和 plan payload。该记录固定
`production_runtime_ack=false`，不能提供 physical outcome 或 reward。main 多周期世界、D7
命令应用 lineage 和 D6 paired physical effect 仍待跨模块闭合。

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
- P1 formal reserved-seed evidence done：v2 正式产物已独立复核；treatment applied=`20/20`、fallback=`0`，cost-matrix changed=`20/20`，final-binding changed=`0/20`。安全计数和规则评分未退化，但未形成 runtime/physical/causal/promotion 证据。
- P1 D6 independent consumption done：profile-bound v2 availability sidecar 已存在，same-frame offline assignment comparison 为 available；runtime ACK、physical outcome、paired non-degradation、counterfactual 和 causal 仍明确 unavailable。
- P1 isolated plan consumption contract done：D3 构造/校验 API 和 replay/stale ledger 已
  通过 8 项专项；main 克隆世界推进、D7 command lineage 和 D6 物理窗口仍开放。
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

## 23. 可复现学习研究管线复核（2026-07-20）

本轮补齐的不是新 assignment backend，而是围绕规则 Hungarian 的研究外环。默认
`AssignmentPlanner` 仍没有模型；模型只对 deterministic candidate mask 中的边输出
bounded residual，最终 plan 仍由 Hungarian/demand-slot、all-or-none、迟滞和版本链
产生。PPO 与 BC 均没有 assignment head，也没有修改 D7。

| 复核项 | 状态 | 判断 |
|---|---|---|
| scenario/seed/episode 数据合同 | legacy v1 superseded | 原合同只隔离 scenario+seed，跨 scenario 同数值 seed 风险由 section 26 的 v2 关闭 |
| 匿名特征 | implemented/tested | ordinal token + allow-list 派生字段；禁止 truth actor 和原 entity ID |
| BC | synthetic pipeline done | 多 episode frame mini-batch，train/validation loss 和 whole-seed metric 可用 |
| PPO | native pipeline done, outcome unvalidated | clipped actor-critic、变长 edge、pooled value、低频 advice；只做 synthetic/offline rollout |
| bundle | implemented/tested | manifest/state_dict/SHA、weights-only strict load、版本/特征/SHA 回退 |
| shadow paired report | implemented/tested | 成本、high-threat unmet、churn、安全违规、P50/P95 和 fallback 均可聚合 |
| promotion | unavailable | synthetic test 仅 6 unseen seed 且 cost non-degradation=false；false/unavailable 正确 |
| online hold/replan | not integrated | advice head 只进入离线 BC/PPO；在线 assistant 当前仅消费 residual |

以下 30-seed/60-frame smoke 属于 legacy v1：BC loss `1.1001 -> 0.5014`、validation `0.3768`；PPO 46
transitions 的一次更新有限。12-frame test shadow inference P50/P95=`0.281/0.350 ms`，
fallback、duplicate、hard violation 均为 0。该规模和时延不构成实时或收益结论。

后续顺序保持：先由 main 生成 truth-isolated 真实 sequential records，再按完整 seed
训练和标定；至少保留 20 个完全未见 test seed，完成动态 3v5/5v3、资源失效、目标增删、
M-to-N demand、stale/timeout/OOD paired shadow。安全、成本、高威胁 unmet 和 churn 全部
非退化后才能生成 recommended manifest。正式权重、AirSim 接线和 D6 系统报告均未完成。

该 v1 批次新增 16 个专项测试后 D3 共收集 215 项，结果为 `214 passed, 1 skipped`（6.95 s），
零失败满足门限；唯一 skip 是既有 optional OR-Tools installed-only case。

## 24. 最近单帧规划证据接口复核（2026-07-20）

本次补齐 planner 与既有 `LearningFrameRecord` 之间的所有权断点。rule matrix 在 switch
penalty 后、learning assistant 前冻结；effective matrix 是实际送入 Hungarian/demand-slot
solver 的结果。shadow proposal 单列且不改变 effective，assist effective 单列，任意
fallback 都必须逐元素返回 rule。计划选择来源另分 `central_solver`、
`incremental_solver` 和 `regional_authority`，避免把区域授权选边误写成中心 solver 决策。

`PlanningFrameEvidence` 只保留一帧，值对象 frozen，数组使用不可写独立 buffer。快照
不是输入对象引用：所有实体和 assignment 先映射为 ordinal token，再只保留 frame
builder 必需字段；上游 metadata、node、actor、object、truth alias 不进入证据。它也
不附加到 `AssignmentPlan.metadata`，因此不改变在线发布合同或默认 Hungarian 行为。

失败语义是本次复核重点。每次 planning attempt 先替换上一帧；stale、区域 authority
拒绝、证据形状/roster 不一致和没有匹配成本帧的发布均留下 unavailable reason 和空
payload。authority-generation fence 只有版本隔离，没有当前成本输入，因此明确不可
转成学习帧。有效 held、unchanged、forced-replan ack 和 regional plan 仍可记录当前
输入，而不是复用旧矩阵。

公开 `build_latest_learning_frame_record()` 已替换 synthetic generator 对
`_build_search_matrix()` 的私有调用。main 后续只提供 scenario version、seed、episode
和 frame index 即可写既有匿名 schema。11 个新增专项测试和 226 项全量回归结果为
`225 passed, 1 skipped`；零失败门限通过，skip 仅 optional OR-Tools。尚未完成的是
main/runtime 的真实 episode 接线、连续整 seed 数据、D6 可用性统计和真实 shadow
promotion 证据。

## 25. 区域资源提示候选图入口复核（2026-07-20）

本轮新增能力与既有 `plan_regional_authority()` 分工明确：后者物化 D4 已裁决的 owner 和
成员；新 `plan(..., regional_planning_hint=...)` 只把上一轮聚合区域资源建议转换成下一
轮 D3 candidate graph 约束。DTO、schema、严格 mapping 解析和错误 reason 全部由 D3
拥有，不导入 D4 控制类，也不接受 target/resource/truth/actor/object 身份字段。

应用顺序为 rule cost/switch penalty -> regional mask -> optional learning residual ->
Hungarian/demand-slot -> feedback/hysteresis/version。每条 transfer allowance 对应一个固定
大小、与其他 route 互斥的未承诺资源池；资源唯一性使实际跨区数不超过许可。上一计划的
所有 assignment/coalition member 和按 post-quota 计算的 reserve floor 不进入该池。D5
hard reject、能力、三维可达性和稀疏 mask 仍优先。非法/过期/不可满足提示记录 reason 后
调用同帧无提示 `_plan_candidate()`，不把非法值解释为零建议。

14 个新增 fixture case 与 240 项全量回归结果为 `239 passed, 1 skipped`，零失败门限
通过；skip 是 optional OR-Tools。覆盖 1-to-1、M-to-N、learning assist、D5 hard edge、
source/lease/region/conservation/transfer 错误和 commit/reserve 保护，seed 不适用。复核
结论为 D3-owned 合同已实现并测试；main 尚未映射 D4 recommendation，D6 尚未形成正式
多 seed 指标，AirSim 和物理拦截本轮均未运行。

## 26. 数值 Seed 原子切分与 v2 Bundle 复核（2026-07-20）

本次改动只修学习研究数据边界，不修改 Hungarian、demand-slot、BC/PPO reward 公式、
动作空间、安全外壳、迟滞、版本或 D7 binding。旧 split 将 `(scenario_version, seed)` 作为
身份；同一数值 seed 在不同 scenario/scale 下可能进入不同 split，导致所谓 test seed 已
参与 train/validation。该风险不能靠 episode 哈希补丁解决，必须在完整 catalog 层处理。

当前采集 record 显式为 `unassigned`。finalize 对全部唯一数值 seed 做稳定排序并按数量
分配三个 split；scenario、规模和 episode 不参与身份。少于 3 个唯一 seed、test 少于声明
unseen 数、冲突预分配、跨 split seed、重复 frame 或篡改均 fail closed。正序和逆序输入
产生相同 canonical JSONL、manifest、split hash 与 frame SHA。dataset/split/bundle/shadow
分别升级到 v2，旧 dataset/bundle v1 明确拒绝，不静默解释。

训练 whole-seed metric 与 shadow unseen/per-seed report 均按数值 seed 跨 scenario 聚合。
promotion manifest 同时绑定 dataset v2、split policy v2 和
`numeric_seed_global_across_scenarios`，手写旧语义 recommended 不能授权 assist。规则矩阵、
求解器和计划发布链未改变。

writer 通过 iterator、临时 SQLite 和增量 SHA 保持审计质量并避免 D3 内部全量常驻。
200v200 fixture 单帧 JSON 约 5.85 MB，NumPy payload 加 edge tuple 浅层约 5.16 MB；main
现有 40-frame 全量读取的保守下界超过约 440 MB。D3-owned API 缺口关闭，main 改用
`iter_learning_frame_records()` 仍是 cross-module P1。

全量收集 244 项，结果 `243 passed, 1 skipped`，零失败门限通过；唯一 skip 是 optional
OR-Tools。本批没有模型训练、AirSim 运行或性能比较，不能据此宣称模型或物理效果改善。

## 27. Learning Bundle、训练与 Shadow 复核补正（2026-07-20）

复核结论是规则主线与授权边界保持不变，但原 learning 外环需要五项 fail-closed 补正，
当前均已在 D3 owned code/test 中完成：

1. BC 仅使用 train/validation，PPO 仅使用 train；test frame 在训练 API 边界被拒绝，
   BC whole-seed metric 不再出现 test seed。CLI 的完整 dataset load 仅验证内容与切分合同。
2. frame v2 采用精确字段集合并递归拒绝 truth/actor/identity/entity-ID 类未知字段；保留
   ordinal token、已声明强类型匿名字段和语义 hard-reject reason 的显式兼容范围。
3. candidate mask/hint 在候选索引、assistant 返回和 solver 消费三层都与 hard reject
   reasons 求交，因此人为不一致也不能恢复 D5、容量、冲突或可达性禁边。
4. assist promotion 不能绕过，且必须证明 eligible 正式 test paired shadow；evidence
   schema/kind、`rule_cost_matrix_v1`、split/frame/state 三摘要、严格布尔/计数、至少 20
   unseen seed、零 fallback 和安全/成本非退化全部满足。
5. rule/proposal 可以用不同矩阵选边，但二者最终成本必须在相同 `C_rule` 与 unassigned
   costs 上重算。学习仍只输出 `C_rule+alpha*tanh(delta_C)` 的受约束 residual proposal，
   不能输出或授权 AssignmentPlan、coalition member、version 或 D7 action。

全量收集 252 项，结果 `251 passed, 1 skipped`；接受门限零失败通过，skip 仅 optional
OR-Tools。可提交状态不等于模型可晋级：当前没有正式权重、真实 D2/D3 训练、>=20 未见
真实/高保真 test seed、eligible promotion、AirSim 收益或 200v200 学习闭环结论。SHA
提供完整性与错配保护，不是签名式来源认证；同步 timeout 也仍是返回后拒绝。

## 28. 200×200 Learning Export 性能复核（2026-07-20）

本轮修改的是 planner evidence 之后的数据工程路径，不是 assignment backend。旧
finalization 将每个已验证 record 转字典并编码进 SQLite，排序后再完整解码、递归检查、
重建 record、替换 split、转字典和重编码。cProfile 中重复 `from_dict()` 和 identity
递归占主要累计时间；这部分不会提高 Hungarian 质量，也不增加安全证据。

当前实现按 target 缓存需求对象，frame builder 复用 action-mask reject count。writer
写盘前重新校验 record，随后 canonical 编码一次；SQLite 仅维护稳定键、offset 和 size，
payload 保存在临时 JSONL。排序输出读取单帧字节并替换唯一受控 split 占位符。该设计没有
绕开 truth/actor/identity 拒绝，也没有信任外部原始 JSON。

确定性测试用旧语义直接构造 expected bytes，正序、逆序和优化结果完全相同；另有构造后
mask 篡改和 hard-reject truth key 注入负例。200×200 top-32 六帧微基准显示 frame build
2.10×、JSON decode/validate 1.71×、finalize 3.74×，匹配峰值下降 12.69%。测试不使用
墙钟阈值；全量结果为 `254 passed, 1 skipped`。

复核结论为 D3-owned 重复对象/JSON 转换 GAP 已关闭。标准库 `tolist/json.dumps` 是剩余
热点，九场景 27.86 MB 内容按 schema 要求保留。模块微基准本身不能解释联合 staging；
main 后续 clean-tree 复测已补齐分项 wall fields。没有运行 AirSim、训练模型或改变
Hungarian、残差公式、硬掩码、计划版本、联盟和 D7 授权。

## 29. Clean-tree 200v200 集成复核（2026-07-20）

main 对相同 nominal 200v200 三 seed 生成链执行优化前后对照。基线位于
`capacity_probe_v2/nominal_timed`，优化后位于
`capacity_probe_v2/nominal_timed_postopt`。优化后 producer commit 为
`4052d9411363c39d52100c0e3a4f60ee88443cab`，`repository_dirty=false`。

| 阶段 | 基线 | 优化后 |
|---|---:|---:|
| episode run | 125.2205 s | 127.9871 s |
| artifact staging | 225.9243 s | 126.4682 s |
| D3/D4/D5 联合 finalization | 116.5624 s | 7.7377 s |
| 总生成 | 467.8007 s | 262.2866 s |

D3 stage 在 seed 930/931/932 上分别为 0.0917/0.1129/0.0999 s；D3 输出 6 帧并正常
finalize，train/validation/test 各 2 帧，在线真值使用为 0。该结果将 D3-owned 重复编码
与 finalization 热点状态确认为什么“已关闭”，也证明此前联合 staging 不能归因于 D3。
联合 finalization 的 7.7377 s 是三个模块的汇总，不得全部记为 D3 改善。

本节形成时只完成三 seed 生成复测。其后正式 900 episode 数据和 BC 开发模型已按第 30 节
补齐；AirSim、外部 seed 1000-1019、paired 非退化和 assist promotion 仍开放。

## 30. 正式 900 Episode 与 BC Shadow 复核（2026-07-20）

### 数据与训练

正式 D3 数据清单通过完整只读审计：900 episode、1604 帧、100 个数值 seed，三分为
60/20/20 seed 和 962/320/322 帧。五档规模均覆盖，1000-1019 与训练体系数据零交集。
frame SHA 为 `6761d35d...fdb59a2`，split hash 为 `679a9051...70a2`。

BC 使用固定 seed `20260720`、12 epoch、hidden size 64、Adam 0.001、mini-batch 8 和
正类权重上限 16。训练 loss `1.083713 -> 0.468781`，validation loss `0.469243`。
训练 23.81 s，开发评估 8.42 s，进程总 wall 73.43 s，峰值 RSS 约 1.58 GB。PPO 未启动。

### 开发结果

internal-test 有 322 帧、708188 条候选边。边排序一致性 0.8031，计划完全一致率 0.6770，
计划边 Jaccard 0.5914。BC shadow 与 rule-only 需求满足率同为 0.975689，高威胁满足率同为
0.887165，duplicate 与 hard violation 均为 0，平均 churn 同为 70.1149。共同规则成本
均值由 246.682813 增至 246.705159，平均差 +0.022345，相对 +0.0091%。

推理 P95 在 5/20/50/100/200 档为 0.247/0.433/0.860/1.434/2.793 ms。当前帧级 OOD
策略只要任一候选边任一特征超过 6σ 就回退，internal-test 有 163/322 帧触发。这个门控
保证了规则回退，但也说明现有阈值没有完成准入标定。

### 结论与下一步

bundle v3 同时绑定数据、split、feature、配置、state-dict、Git 基线提交/角色、工作树状态
和训练源码摘要。`39b097e...` 是数据生成与训练基线；未提交 D3 源码以独立 SHA256 固化。
admission 为 `development/shadow-only`，外部保留状态 `not_evaluated`；assist 加载稳定
返回 `bundle_shadow_only`。权重 SHA 为
`e3da9fd5b54451da83358405b6051991e0c78bcf9f538b350d459b05faf8e0b2`。

该模型没有通过性能晋级：成本略有退化，OOD 回退比例高，内部 test 也不等价于 seed
1000-1019。main 下一阶段应冻结同一权重，由 D6 对 20 个外部 seed 做 rule-only/BC
shadow 配对，并单独审计 OOD 特征、confidence、P99/timeout。通过前不接 assist，不改变
Hungarian、计划版本或 D7 binding。

模型权重位于 ignored `research_modules/d3_assignment_planner/outputs/`，普通 Git 仅保留
审计、配置、指标和 SHA。当前环境无 Git LFS，长期权重归档由 main 处理。

D3 全量回归收集 258 项，结果 `257 passed, 1 skipped`；唯一 skip 为 optional OR-Tools。
AirSim 集成计划和 M-to-N 专项 review 均已检查，本次离线 BC 开发任务未改变其合同。

## 31. Detached 共享 Seed 切分复核（2026-07-21）

### 复核结论

D3 正式数据原有 `d3_numeric_seed_atomic_split_v2` 映射与 main 的 detached
`scalable3d-shared-seed-split-registry-v1` 完全一致。100 个训练 seed 按 60/20/20 分配，
1000-1019 未进入。该结论来自 registry 哈希重算、D3 policy 重放、manifest 比对和全部
1604 帧检查，不是按配置值推断。

### 实施判断

- 共享 registry 保持 main-owned。D3 只读取和验证，不复制一份可独立漂移的映射，也不
  修改正式 dataset/manifest。
- loader 的默认路径继续使用模块 v2 合同。C1 调用必须同时提供共享 registry 和其冻结
  source registry；缺一项或任一哈希、seed、split 不一致立即停止。
- 新训练产物将 binding 写入 bundle `training_results` 或正式 sidecar。旧 bundle 可用于
  非联合开发回放，不可在没有 shared binding 的情况下冒充 C1 产物。
- 这次改动只提供数据分割证明。当前 BC 仍轻微成本退化且内部 test 有较多 OOD 回退，
  因此 `assist_authorized=false` 保持不变；PPO 不启动。

正式验证的 registry file/content/assignment/source SHA 为
`68608d29...032f`、`29eb6895...f146`、`31c6a3fc...6ab5`、`2ab928a4...15f`。输入文件
前后哈希相同。D3 全量回归 `269 passed, 1 skipped`。C1 下一步由 main 核对 D4、D5 的
同 registry binding、跨模块 join 和 label availability，再决定是否建立联合训练视图。

## 32. 正式全样本准入复核（2026-07-21）

D3 owner 已对正式分配数据完成独立流式全样本复核。输入是 7 个冻结源文件，核心帧文件
约 883 MiB；审计按行处理 1604 个决策帧，没有重新生成或修改正式数据。源文件审计前后
SHA256 一致，报告和 JSON 写入 D3 自有目录。

复核计数为 900 个实际 episode、3658815 条候选边和 117304 条规则选中动作。规范数值
seed 身份为 60/20/20；实际 episode 为 540/180/180，决策帧为 962/320/322，候选边为
2229182/721445/708188。全部 43905780 个候选特征值有限。容量、需求槽、动作索引、
切分、前序版本、在线 truth、脏 episode 和非法 `global_track_id` 字段违规均为 0。
`feedback_result` 与 `hysteresis_result` 按字符串统计。194 个不可导出原因保留，没有以上一
有效帧替代。

数据结构准入为 `complete`，总体为 `partial`。frame 不携带 current owner/current
version、真实 applied ACK、outcome 或 stale runtime record。规则教师
`reward_components` 不能解释为可归因 runtime reward；同 seed paired shadow 和外部
保留 seed 非退化也未闭合。审计没有训练模型或写入 `.pt`，PPO、assist 和在线权限保持
关闭，默认规则代价与需求槽匈牙利未改变。

新增 10 个审计负例和正常路径测试。D3 全量收集 280 项，结果为
`279 passed, 1 skipped`，唯一 skip 为 optional OR-Tools。下一步由 main/D6 使用审计
JSON 文件 SHA `62a47df8...17fb` 和内容 SHA `954f3e96...1867` 做跨模块复核；运行时
owner/version/ACK/outcome 和 paired shadow 应作为新证据生产，不得回填本批正式数据。

## 33. Runtime ACK 消费复核（2026-07-21）

D3 已增加版本化、只读的运行计划 ACK 验证器。接口不依赖 main 包，要求提供 ACK、
D3 来源 envelope、可选 D7 来源 envelope 和预期 `AssignmentPlan`。它复算规范
payload SHA-256，核对正整数 bus sequence、当前 plan id/version/schema、assignment
inventory、资源与中心航迹 binding、coalition/version/role，并从 D7 来源独立重算
fully-bound、control-applied 和 held。

原始实现用单一 `isinstance` 检查预期计划，无法接受同一 D3 源码经顶层与 namespaced
包路径载入后形成的另一类对象。本轮改为受约束身份验证：模块名、类名、精确数据类字段
集合和计划 schema 必须全部匹配。普通外观相同对象仍以稳定错误码失败关闭。consumer
源码不导入 main，跨包集成仅由测试导入 main，运行时依赖方向不变。

24 项专项测试覆盖全部要求的正负例和两种合法跨包组合。自动化真实 main 集成测试运行
3v3、seed 7、1.2 秒，产生 2 条 ACK；公开 consumer 验证最后一条 ACK，最终 3 条 binding
全部通过，在线 truth use=0。缺失 learning mode 时结果保持 unavailable。冻结 900-episode
数据不含新 ACK，当前 D3 consumer 完成不等于正式 applied/outcome/reward join 完成。

评审结论：D3-owned runtime ACK 消费接口为 implemented/tested；D6 离线 join、独立
outcome/reward sidecar 和同 seed paired shadow 仍开放。规则教师 `reward_components`
不再能被误写为运行 reward，shadow 或 accepted plan 不再能被误写为学习 applied ACK。
PPO、assist、authority 保持 false。D3 全量结果为 `303 passed, 1 skipped`。

## 34. 运行结果归因复核（2026-07-21）

D6 已提供只读 `runtime-plan-outcome-join.v1`，D3 本轮补齐自身消费边界。新适配器要求
verified ACK 和完整 D6 结果摘要，按一个资源-`global_track_id` binding 建立来源计划、
D7 消费、main ACK 和结果窗口的引用。输出保留 owner、版本、三个序号、时间窗、执行
签名和全部摘要，不复制 D6 的离线真值身份。

复核确认以下行为失败关闭：缺 ACK/owner/字段/摘要、错误资源或航迹、序号倒置、窗口
重叠、旧版本、刷新类型错误、同 identity 执行签名变化、在线真值使用、自报 reward、
反事实或因果结果。顶层与 namespaced D3 包路径继续采用受约束类身份兼容，不接受任意
鸭子类型。

现有六项 `OfflineRewardComponents` 是规则教师值，不能作为运行结果。新输出对六项分别
写 null 和 reason；D6 的五米事件及距离进展只进入 observed outcome。当前 paired、
counterfactual、causal、formal reward 全部 unavailable，PPO/assist/authority 保持关闭。

专项 16 项和真实 main 3v3、seed 41、1.2 秒集成样本通过；D3 全量为
`319 passed, 1 skipped`。下一步由 main/D6 生成规则/候选同 seed 配对 episode 和计划级
结果 sidecar，再由 D3 定义后续 reward schema 版本；不得在 v1 上放宽门限。

## 35. 保留 Seed 配对干预复核（2026-07-21）

D3 已补齐规则基线与学习代价修正的保留 seed 实验合同。固定目录为 `1000-1019`，每个
seed 必须有一条 control 和一条 treatment，且使用不同 isolation id。两条 arm 共享相同
场景、初始世界状态、观测输入、D1/D2 lineage、规则代价配置、D3 bundle、阈值、安全外壳
和 source/current plan 版本。任一字段或 SHA 不同都不再被解释为同 seed 配对。

control 的求解路径固定为现有规则代价和 Hungarian。treatment 只在离线仿真 arm 内允许
`C_final=C_rule+alpha*tanh(delta_C)` 影响求解输入。执行收据要求确定性动作掩码、可达性、
容量、版本、迟滞和安全门全部生效，模型异常时仍可回退规则路径。该语义不改变线上权限：
PPO、assist 和 authority 均为 false，规则回退为 true。

manifest 复用现有 paired evaluator、runtime ACK 和 runtime reward 证据 schema。输入
等价性可由 D3 specification 独立确认；treatment 是否实际应用必须有完整 40 条 arm 收据；
runtime ACK 只引用经过现有验证器确认的 ACK。outcome、counterfactual 和 causal 仍由 D6
sidecar 独立提供，没有 sidecar 时保持 unavailable。

本轮完成的是接口、JSON 往返和失败关闭测试，没有执行正式 20-seed 配对实验，也没有
生成性能或因果结论。main 后续负责隔离 episode 和运行时记录，D6 负责 outcome join 与
统计；D3 不扩展为跨模块 runner。专项为 `36 passed`，D3 全量为
`355 passed, 1 skipped`；唯一 skip 为可选 OR-Tools。

## 36. 保留 Seed 隔离执行复核（2026-07-21）

D3 已将配对 specification 转为可执行 typed API。main 提供 seed `1000-1019` 的 20 个
匿名 `PlanningFrameEvidence` 和冻结 development bundle 后，D3 在两个独立 planner 中
复放 control 与 treatment。control 使用原规则矩阵；treatment 只在
`offline_simulation_intervention_arm` 内施加有界代价残差。两条路径共享输入快照、规则
矩阵、硬安全动作掩码、前序计划和时间戳。

模型加载没有复用生产 assist 权限。新入口先调用生产 shadow loader，再核对 manifest
文件 SHA、权重 SHA、policy version、development/shadow-only admission、保留 seed 清单
和权重有限性。通过后仅在离线 planner 内构造有效残差；分布外、低置信度、超时、非有限
值或任何 bundle 不一致均回退规则矩阵。生产 `load_model_bundle(..., mode="assist")` 对
同一 bundle 继续返回 `bundle_shadow_only`。

一次批执行生成一个覆盖 20 seed 的配对报告和 40 条共享报告哈希的真实 receipt。输出
计划带离线、不可发布和无授权标记。manifest 的 runtime ACK、outcome、counterfactual、
causal 层继续 unavailable，不从规则成本或五米事件推断。D3 没有伪造 main ACK、D6 结果
或因果收益。

专项 7 项使用临时冻结 v3 development bundle 和 20 个匿名规划帧，覆盖成功路径、
manifest/version 失配、分布外门控、deadline、非有限权重、快照篡改和 JSON 产物，全部
通过。D3 全量为 `362 passed, 1 skipped`，唯一 skip 为可选 OR-Tools。

当前判断：D3 模块执行接口缺口已关闭；main 的正式 1000-1019 三维 episode 调度、D6
非退化侧车和 applied ACK 仍开放。完成这些外部证据前不修改 production admission，不启动
PPO，不开放 online assist 或 authority。

## 37. 保留 Seed 精确重放复核（2026-07-21）

失败帧集中在 `t=1.0`。原计划是 `held_by_hysteresis` 或
`replan_ack_no_change`，离线重放却生成 `accepted_execution_control_change`。代码复核
确认规则矩阵和动作掩码没有变化；差异来自匿名前序计划清空 owner/activation metadata，
以及规划帧未记录 `forced_replan`。因此严格 `control_plan_replay_mismatch` 是正确拒绝，
不能删除或放宽。

D3 修复限定在证据和离线执行边界。计划 owner/activation、授权、节点/链路、迟滞窗口累计
数和联盟执行字段按白名单保存，身份值匿名化；前序独有 roster 使用 `previous_*` token。
离线 planner 恢复匿名配置并传入原 `forced_replan`。control gate 现在比较完整执行签名和
状态，不只比较 pair 集合。生产 `load_model_bundle()` 的 assist 准入未改，离线输出仍不可
发布。

新增 20-seed 真实形态回归覆盖 5v5 迟滞、4→5 强制重规划、5→4 生命周期和篡改 binding
负例。专项 `9 passed`；D3 全量 `364 passed, 1 skipped`。随后读取 main 当前 20 个源帧与
冻结 development bundle 做不写盘复验，40 个 arm 完成，control 状态分布为 15 个
unchanged、3 个 held、2 个 replan ACK，binding/状态失配为 0。

第 37 节阶段的 D3 P1 runner 阻塞已关闭；当时 main 尚未写出完整 D3/D4 产物，D6 也尚未
完成独立结果消费。runtime ACK、物理结果、反事实、因果和正式 reward 当时不可用。该结果不支持 PPO、
online assist 或 authority 晋级。

## 38. 二元特征分布门复核（2026-07-21）

首轮正式保留 seed 证据中的 20/20 OOD 不是连续特征越界。11 个连续项最大 z 为
`1.6229`；旧门把伯努利 `previous_binding=1` 与训练均值做对称高斯比较，得到
`z=8.4669`。训练集中已包含该端点，拒绝结果与特征定义不一致。

D3 现固定二元特征清单和 `1e-6` 端点容差。合法 0/1 绕过连续 z 门，非法中间值、越界和
非有限值仍失败关闭。连续 6σ、绝对上限、deadline、confidence、动作掩码、版本、安全门
和规则回退均保持原值。loader 只绑定 manifest 已验证的特征顺序，没有修改冻结 bundle。

诊断 schema 记录原因、特征名、索引、边偏移和最大连续 z，不携带目标、资源、真值或
全局航迹身份。回归覆盖合法/非法二元输入和连续超限；D3 全量为
`372 passed, 1 skipped`。

同一正式 bundle 与当前 nominal 5v5、2.2 秒、seed `1000-1019` 的不写盘复验得到
applied=20、fallback=0，推理均值/P95/最大为 `0.340/0.692/0.899 ms`。重复分配、硬约束
违规和高威胁未满足均为 0，最终 binding 未变化。该不写盘结果已由第 39 节的
v2 正式证据取代；PPO、online assist 和 authority 仍未开放。

## 39. v2 正式保留 Seed 证据复核（2026-07-21）

本轮只读复核了 nominal 5v5、2.2 秒、seed `1000-1019` 的 v2 正式产物。
源提交为 `78912963b67fe86ee9a8d29186b18a9dd60c460c`。`SHA256SUMS`、
`manifest.json` 和 D3 产物的 SHA-256 分别为
`821f15035e628d8db86f13c22d93f8e05142c5f00aae9118974a74bdc98b72bc`、
`d6ef23b28add92e9a24a185ea72a7275e341bd796a2e11930c4d5f46b19a883c` 和
`e878cd97f2a0f1c84fbd68b5ee996d0dc6d4e550cce42eab53558a33a120270b`。五个受管
文件的 `sha256sum -c` 全部通过，D3 JSON 没有非有限数。

来源 lineage 中有 20 个唯一源样本，对应 seed `1000-1019`。20 个样本全部
clean/finite，online truth 使用为 0。control 和 treatment 各 20 条。treatment
applied=`20/20`、fallback=`0`；隔离模型修改了 `20/20` 组有效代价矩阵，
最终 Hungarian binding 变化为 `0/20`。规则与 treatment 的 assignment cost mean 均为
`17.0560260319065`；高威胁未满足、duplicate、hard violation 和 churn 均为 0。
推理时延 P50/P95 为 `0.246385/0.310801 ms`，最小/最大为
`0.234524/0.792214 ms`。

结论限定在规划层隔离应用。学习修正已实际进入求解输入，但没有改变最终分配，
也没有产生可声明的任务收益。runtime ACK、physical outcome、counterfactual、causal 和
formal reward 均为 unavailable，promotion 仍为 unavailable。PPO、assist、authority 保持
false，rule fallback 保持 true，runtime publication 保持 false。本结论取代第 35-38 节中
“正式产物待 main 重跑”的历史状态，不改变其他安全门控和开放缺口。

## 40. D6 Profile-Bound v2 可用性复核（2026-07-22）

D6 已在提交 `d4e8562` 中完成独立只读消费，目录为
`research_modules/d6_evaluation_metrics/outputs/reserved_seed_interventions_nominal_5v5_1000_1019_formal_7891296_d6_profile_bound_v2_audit_20260722/`。
`outcome_availability_sidecar.json` 状态为
`pass_offline_assignment_comparison_only`；文件 SHA-256 为
`f3852251daf02ec87fe878e7fb80aad6f381d8c0756a5c956a32e737a3871c3b`，规范内容
SHA-256 为 `c02a345c46ddc642dea7fb6bfcfb24184e7dc2a9f35b754c90324d074b445d2d`。

D6 复算得到 treatment applied=`20/20`、fallback=`0`、effective matrix changed=`20/20`、
final binding changed=`0/20`。rule/treatment 同帧 cost mean 均为
`17.0560260319065`；high-threat unmet、duplicate、hard violation 和 churn 均为 0。
`same_frame_offline_assignment_comparison` 因而为 available，D3 assignment 层可用性和
独立消费缺口关闭。

该 sidecar 没有 runtime ACK 和干预后的物理状态窗口。post-intervention physical outcome、
paired physical effect/non-degradation、counterfactual、causal 和 promotion 仍为
unavailable；`PPO=false`、`assist=false`、`authority=false`、`rule_fallback=true`。本批
binding 未变化不能解释为候选策略有效，也不能解释为物理无退化。

## 41. 隔离计划消费合同复核（2026-07-22）

D3 已增加与生产 runtime ACK 分离的计划消费合同。构造器首先调用 runtime ACK 路径共享的
计划结构检查，确认计划 schema、N/M 规模、binding 唯一性和 metadata 可规范编码，再核对
paired arm、execution receipt、输入快照和输出计划载荷 SHA。共享检查不共享证据身份；新
输出采用 `d3.isolated-plan-consumption-evidence.v1`，状态固定为隔离 consumer 接受。

证据携带 experiment/version、pair/seed/arm/isolation、场景配置、初始世界、匿名观测快照、
D1/D2 lineage、plan id/version/schema、payload SHA、消费周期和时刻、assignment/binding
计数及 binding inventory SHA。有状态 validator 按 arm 维护已消费版本。重复计划、版本
回退、相同版本换计划、非单调周期/时间以及任一 lineage 或摘要不一致均失败关闭，失败项
不会污染账本。

权限边界为强制字段，不由调用方选择。`production_runtime_ack=false`、
`isolated_simulation_only=true`、生产世界控制为 false；physical outcome、reward、causal
均 unavailable，PPO、online assist、online authority 保持关闭。由此，原 offline
execution receipt 仍是离线执行声明，新记录也只是在克隆世界入口处的消费确认，两者都
不能转换为线上 ACK。

专项 8 项及 D3 全量回归通过，全量为 `380 passed, 1 skipped`。当前 D3-owned 接口可以
交给 main 集成。仍需 main 建立两套多周期世界并保存 D7 command lineage 和状态窗口，D6
再完成 paired physical effect 的 availability-aware 联接。nominal 5v5 的 final binding
仍为 0/20 变化，因此还需边界场景；D4 degraded effectiveness 需单独实验。

## 42. 离线目标库存兼容复核（2026-07-21）

兼容阻塞来自特定迟滞路径，不是 dataclass 类身份或跨 arm mutation。main 实际产物使用
`research_modules.d3_assignment_planner.src.d3_assignment_planner.models.AssignmentPlan`，
该身份在严格白名单内；冻结 dataclass 由 `replace` 生成新计划。`seed=1000/control` 的
5 个 binding 和 5 个需求摘要始终完整。首个异常位于 `index=22, seed=1011, control`：
当前 roster 为 5，旧执行绑定为 4，`target_0004` 只在候选审计范围中。

修复限定在 D3 offline intervention 生成边界。离线计划先按当前匿名 track roster 重建
未分配、不完整和需求摘要，再生成不可发布 plan id 与 receipt SHA。生产 runtime ACK
验证器未修改。缺失 bundle 条件下逐 seed/arm 严格扫描为 `40/40`，`seed=1011/1019` 的
control/treatment 均保留 4 个绑定并显式登记 `target_0004`。删除该库存项后严格校验仍以
`expected_plan_target_count_invalid` 失败关闭。

D3 专项 `19 passed`，全量 `382 passed, 1 skipped`。本项关闭 main 隔离 rollout 的计划
消费兼容阻塞；多周期控制、物理结果、reward、causal evidence 和生产 ACK 仍不属于该证据。

## 43. 在线故障代际库存复核（2026-07-22）

故障接管断点来自计划身份与当前目标库存不同步。seed 1011/1019 在故障前保留 4 个旧绑定，
故障时当前规划帧已经有 5 个目标。原 fence 只复制已发布计划，无法为第 5 个目标生成库存
条目，二级 owner 转换后也没有匹配的新规划证据。

D3 现把当前目标 roster 纳入执行身份。中心、增量和区域授权计划均在身份最终化前规范库存。
`advance_authority_generation()` 只在最近规划上下文与当前已发布计划身份匹配时使用该上下文，
保留原绑定并补齐零绑定目标；否则不推测目标。库存变化形成新计划编号和严格递增版本，
previous-only 可执行绑定仍失败关闭。发布前调用既有严格载荷摘要校验，未修改生产 ACK 的
接受条件。

M-to-N 的两个计数已经分开。不完整联盟的 `assigned_resource_count` 表示已找到的候选成员，
需求摘要据此计算 shortfall；`AssignmentPlan.assignments` 只保存可执行绑定。联盟未完整时
assignment 必须为 0，成员必须标记不可执行，目标保持未分配且不完整。联盟完整时，候选
成员数必须与可执行绑定数一致。

定向 5 项和 D3 全量通过。全量共 386 项，结果为 `385 passed, 1 skipped`。只读三维质点
`center_failure` 复核使用 5v5、3.2 秒、seed 1011/1019。两组最终计划均为二级 owner、
v3/epoch 3，保留 4 个绑定，第 5 个目标未分配且不完整，需求摘要 5 条；各有 2 个故障后
可用规划帧，严格计划摘要通过，在线真值使用为 0。

该结果关闭 D3-owned 在线 roster 和故障代际规划证据缺口。后续由 main 扩大 seed、规模及
二级再次失效场景，并运行 AirSim。D4 接管许可、D7 控制许可、生产 runtime ACK 和物理结果
仍是独立证据，不能由 D3 计划库存推导。

## 44. 故障代际离线重放复核（2026-07-22）

新增断点位于离线 replay 的 owner 时序。记录帧已经完成 center 到 secondary 的身份转换，
但原 replay 直接用记录计划的 secondary source/link 配置规划器。在线实际先由中心配置求解
候选，再由 D3 helper 写入 secondary owner、lease 和 epoch。提前带入新 owner 会使相同
5/5 binding 被判为执行签名变化，control 因而得到 `replan_applied/changed=true`。

修复后，authority frame 先从 `previous_plan` 恢复求解阶段配置。冻结矩阵、版本 fence、
迟滞和普通 planner 决策保持原样。候选形成后，再依据 recorded plan 的二级合同调用
`prepare_secondary_takeover_plan()` 或 `continue_active_secondary_plan()`。二级状态、owner、
激活时刻、lease、epoch 和 link 均为硬条件。重放计划通过严格 payload 校验后，继续由原
control matcher 比较完整执行签名和决策身份。

真实 `center_failure` 运行覆盖 seed 1000-1019。40 个 arm 全部完成；20 个 control 均重现
`replan_ack_no_change`，40 个 arm 均有严格回执。seed 1011/1019 的 control/treatment 各保留
4 个 binding，并登记 `target_0004` 未分配且不完整。在线真值使用为 0，输出清单 5/5 通过。
D3 全量 387 项，结果为 `386 passed, 1 skipped`。

该结果关闭 center-to-secondary 离线 replay 的 D3-owned 缺口。secondary-to-distributed、
通信退化、大规模和 AirSim 尚未验证。离线 authority identity 仍是仿真重放事实，不是
生产 runtime ACK、控制许可或物理结果。

## 45. 区域授权待分配库存复核（2026-07-22）

main 的区域 adapter 现只为上一计划已有可执行绑定的目标生成 D4 grant。seed 1011/1019
在二级再次失效时有 5 个当前目标，其中 4 个保留执行绑定，`target_0004` 已在上一计划中
明确为零绑定、未分配且不完整。旧 D3 校验要求 grant 覆盖全部 5 个目标，因此把正确的
4 目标授权误判为 `regional_authority_target_set_mismatch`。

D3 现将未授权差集限制为“前序显式待分配库存”。校验同时核对 assignment、未分配清单、
不完整清单、需求摘要和可选联盟成员；任何一项不一致都失败关闭。通过后只为 4 个 grant
目标构造区域 assignment 和 coalition。第 5 个目标保留 `0/1` 短缺，并明确记录
`authority_granted=false`，不获得 owner、lease、commit 或执行许可。

正例、漏授权、未证明新增目标、库存篡改和 previous-only 可执行绑定测试均通过。模块区域
专项及规划证据为 `34 passed`；三维质点 `secondary_failure`、规模 5、4.2 秒、seed
1011/1019 的 main 集成测试文件为 `10 passed`。D3 全量为 `390 passed, 1 skipped`。

该结果关闭区域目标集合的 D3-owned P1 断点。生产 runtime ACK 校验没有放宽。本轮不包含
AirSim、D7 控制采用或物理结果；更多 seed、规模和通信退化由 main 后续验证。

## 46. 非生产隔离执行计划升版复核（2026-07-22）

原离线 arm receipt 绑定的是求解候选。候选虽然使用新 `plan_id`，version 仍可能等于正式
源计划，不能直接作为 D4 接受的新执行代际。由 main 临时修改 version 会破坏 receipt、
候选载荷和后续消费者之间的哈希关系，也会把调用方变成计划身份所有者。

D3 现以 `build_isolated_execution_plan(...)` 统一完成该转换。构造器验证同一
`PlanningFrameEvidence` 中的两个角色：`previous_plan` 是离线求解源，继续约束 arm、receipt
和候选哈希；`plan` 是当前正式权威，决定新计划应超越的版本、前序计划和降级权威。完整帧
转换摘要同时绑定两个计划载荷，调用方不能以同 ID/version 的其他载荷替换任一来源。

输出版本固定为正式权威版本加一，`previous_plan_id` 固定为正式权威计划号。创建时刻严格
晚于正式权威和干预时刻，有效期由 arm 与 authority lease/stale 的最早截止约束。正式权威
的 owner/source/link/epoch/lease 被保留；候选的资源目标绑定和完整目标库存被保留。计划中
的生产发布、生产执行和在线 authority 均显式关闭。

`validate_isolated_execution_plan_conversion(...)` 可重建预期计划并核对计划和证据摘要。
隔离消费接口仅在同时提供规划帧、求解源、正式权威、原候选和转换证据时接受升版计划；
缺任一项即失败关闭。原直接消费路径保留兼容。专项 18 项、全量
`408 passed, 1 skipped`。普通 5v5 和 `center_failure` 均完成 20 seed、40 arm 扫描；中心
失效链路验证版本 `1 -> 2 -> 3`。下一步由 main 按新签名完成真实 rollout 接线和 D4/D7/D6
联合验证。本轮没有运行 AirSim，不据离线合同结果声明 adoption、控制采用或物理效果。

## 47. 区域权威离线重放复核（2026-07-22）

`secondary_failure` 的记录规划帧已经由 D4 裁决为区域 owner，但旧离线执行仍调用普通
中心求解，再保留原中心或二级 authority。绑定集合、版本和决策状态相同，assignment 的
owner、区域、epoch、lease 和 commit 不同，因此原完整执行签名正确拒绝。

D3 现把匿名记录区域计划作为该类离线帧的固定安全输入。规划证据保存前序计划与记录计划
的转换摘要。执行器从记录 assignment 恢复区域授权 DTO，再调用线上
`plan_regional_authority()`。重放计划必须复现同一 binding、库存、联盟执行语义、版本、
前序计划、窗口和决策身份。最终 control matcher 保持原实现。

处理臂不能借学习残差改变 D4 已裁决成员。显式待分配目标不进入 grant；seed 1011/1019
因此保持 4 个授权 binding 加 1 个无授权待分配目标。真实 20-seed、40-arm 运行全部生成，
在线真值使用为 0。离线干预专项 `23 passed`，D3 全量 `419 passed, 1 skipped`。

该修复位于既有离线执行接口内部，main 无需更改调用签名。main 后续仍需验证升版计划进入
D4 adoption、D7 控制和 D6 结果侧车后的同一 lineage。当前没有 AirSim、生产 ACK 或物理
拦截证据；M-to-N 区域原子联盟仍需单独多 seed 验收。

## 48. 200×200 规划证据性能复核（2026-07-22）

main 基线表明三次 D3 规划随 20/50/100/200 规模近似平方增长，200 规模累计
`7.329949 s`。D3 cProfile 将确定性主因定位到 planning evidence：相同 rule/effective
breakdown 被按完整 40,000 单元重复深度匿名化，单次约调用 80,200 次
`_safe_cost_breakdown()`。向量化代价构造和 Hungarian 不是本轮主热点。

D3 已在证据层完成最小范围修复。相同源 breakdown 按对象身份缓存，rule/effective 共享
只读匿名 breakdown/reject 结构，数值矩阵保持独立不可写；结构不同的学习有效矩阵继续单独
清洗。previous-plan 迟滞比较只复制 hard-safe candidate breakdown。规划公式、求解器、
M-to-N、迟滞、版本、stale、联盟和 D7 binding 均未改。

独立基准由 `2651.953 ms` 降至 `189.111 ms`，加速 `14.023x`；完整 seed 42000、2.2 秒
质点链路三次 D3 规划降至 `1.013593 s`，加速 `7.232x`。完整边、候选边和 assignment
保持 `40000/6400/200`，在线真值使用为 0。新增非等量、200x200、M-to-N 和多周期语义/
操作计数测试，定向 `62 passed`；D3 全量选定集为
`422 passed, 1 skipped, 2 deselected`。

结论：D3-owned P1 规划证据确定性热点已关闭。墙钟仍是 development benchmark，后续由
main 运行完整 200v200 多 seed 和 AirSim 系统验收。该阶段两项 `global_track_stale` 后续
分别由 main 修复未消费后验调度、D3 修复 ACK 取样口径；当前全量零失败，D3 未放宽 stale
门。更大规模求解器替换不纳入本轮工作。

## 49. AssignmentPlan 成本证据单副本复核（2026-07-22）

长时输出的主要 D3 载荷问题来自字段别名。6,304 条边在
`cost_breakdowns_by_edge/current_cost_breakdowns_by_edge` 中各写一次，单份为
4,757,920 字节。仓库检索只有生产者写旧别名，没有跨模块 Python 消费者；规范字段已被
`assignment_evidence_from_plan()` 使用。

D3 将内部证据升级到 `d3_assignment_evidence_v2`。完整列表、拒绝信息和成本分解保留，
并增加内容 schema、count、SHA-256、单副本存储标记和旧字段引用。公共导出接口可读取旧
v1；新 v2 的内容或审计元数据不一致时失败关闭。外层计划 schema、assignment、执行签名、
版本、owner、迟滞和 stale 均未改变。

合成 200x200 计划缩减 46.28%，只读长时样本字段投影缩减 48.03%。新增 5 项通过。全量
430 项中 427 passed、1 skipped、2 个既有 `global_track_stale` failed。下一步由 main 在
clean worktree 重跑长时 episode，并由 D6 验证新 payload；D3 不把旧样本投影写成正式新
schema 运行证据。

## 50. 冻结输入性能归因与身份签名复用复核（2026-07-22）

本轮没有根据三次集成累计墙钟直接调整规则代价或迟滞。D3 先建立匿名冻结输入，把规划链路
拆为成本矩阵、候选图、Hungarian、计划边证据、迟滞、身份固化、发布校验和离线证据八个
边界。定长操作计数用于解释算法工作量，墙钟只由 benchmark 包装器采集。在线计划对象不
携带任何性能字段。

200×200、top-32 输入产生 40,000 个完整对、6,400 条候选边和一个 200×200 连通分量。
Hungarian 的局部实边和未分配虚拟列共准备 80,000 个单元。规划证据复制 80,000 个数值
单元并访问 40,000 个 breakdown 单元，按共享对象实际净化 6,401 次。上一计划帧另外访问
6,400 条迟滞边，并对旧计划和候选计划共 400 个绑定进行重评分。

局部代码复核发现执行签名在身份固化和发布校验边界重复生成。当前实现只在一次规划调用内
复用 candidate signature。latest published execution signature 由 planner-owned cache
跨帧保存并作为唯一发布权威；caller previous 仍计算自身签名，但只用于与可信 latest 做
一致性校验。公共 `publish_plan()` 从待发布对象计算 candidate signature，不接受外部 latest
签名。优化前后的 assignment、计划版本、计划号复用行为和规范业务哈希完全一致。

区域路径采用分阶段校验。plan id/version 首先失败关闭，pending inventory 随后由区域规则
检查，以保留 `RegionalPlanAuthorityError`；通过区域检查后再执行通用 execution signature
校验。其他同 identity 执行语义篡改仍返回 `StalePlanError`。直接发布和 authority fence
继续使用 planner-owned latest cache。

三条基准路径用于区分成本来源。默认上一计划帧中位为 `334.735 ms`，恢复身份重复计算后
为 `389.673 ms`，关闭离线证据的离线参考为 `223.147 ms`。后一个参考不满足生产审计要求，
没有运行时入口。各阶段计时为包含式边界，不能相加解释端到端时间。

身份、区域、直接发布、authority fence 和性能诊断定向组合 `46 passed`。D3 全量 439 项
初次有 436 项通过、1 项可选 OR-Tools 跳过和 2 项 `global_track_stale` 失败。后续 seed 7
由 main 的未消费后验锁存恢复；seed 41 保留正确 stale 结果，并由 D3 改为选择首个非保持
ACK。当前结果为 `438 passed, 1 skipped, 0 failed`，未调整 stale 门。main 应在隔离环境用
同一提交复测 seed 42000-42002，只有单次输入操作数、调用密度和累计耗时能够相互解释后，
才可形成集成性能结论。

## 51. clean 三种子集成证据复核（2026-07-22）

main 已在 clean commit `8f86192` 完成 200v200、10 秒、seed 42000-42002 复跑。三组均为
finite，在线 truth 使用为 0；每组 D3 调用、计划发布和计划 ACK 均为 10。binding ACK、
control applied 和 hold 摘要与旧 clean commit `3bac3ff` 逐 seed 一致，说明 D1 快照优化
没有改变 D3 执行语义。

D3 assignment 累计墙钟为 `3.437/3.319/3.110 s`，均值 `3.289 s`。旧提交均值为
`3.348 s`，变化约 `-1.8%`。seed 间变化方向不完全一致，结论限定为基本持平和调度噪声，
不用于代码归因或晋级。

冻结 200x200 benchmark 与本次集成复核分别保留。前者的默认上一计划帧 `334.735 ms` 等
数字用于固定输入热点归因；后者用于累计阶段时间和业务一致性。clean 三种子复测项已关闭，
AirSim、物理拦截、长期资源峰值和生产实时预算继续保持开放。

## 52. 独立运行计划身份审计（2026-07-22）

代码和既有测试确认，D3 的新执行谱系由 `uuid4` 生成。两个独立 planner 对相同输入产生
不同 `plan_id` 是当前有意合同；`test_planner_performance_diagnostics.py` 已显式断言原始
计划号不同而 binding/business 哈希相同。同一 planner 内的 refresh、执行变化、secondary
takeover、authority fence 和 stale publish 规则由 identity/authority 专项测试覆盖。

原文档只说明了运行内 identity 保持，没有定义跨独立 episode 的比较口径。本次补充的口径
要求 main 先验证各自版本链，再按计划号首次出现顺序生成规范 token，并保留 parent、version、
owner、coalition 和 stale 语义。原始 plan-derived binding/decision ID 与 payload SHA 需在
规范化后重建；resource、target、global track、node、region、advisory 和 coalition ID 不得
删除或映射。

当前 main-owned scalable publication 未直接包含 `previous_plan_id`。8f86192 与 f80b5bd 的
现有线性长时产物只有在发布序列完整、版本连续且无并行 owner 时，才能以前一发布推导父关系，
并应在报告中标为 derived。该简化 publication 也不能完整重建 execution signature。D3 已有
`PlanningTickHistoryRecord` 能提供完整关系；后续由 main 决定是否接入规范计划载荷。该限制
不要求改写 D3 随机身份合同，也没有形成新的 D3 P0。

## 53. seed 41 运行 ACK 取样复核（2026-07-22）

复核确认旧失败来自测试取样，不是 D3 规划或 D7 安全门退化。当前 3v3、seed 41、1.2 秒
episode 有两条可完整验证的 ACK。首条有 3 个非保持 binding；末条在没有新 D1 后验的条件下，
以约 `0.770941 s` 航迹年龄触发 D7 的 `0.75 s` stale 门并全部保持。

D3 用例现把每条来源计划与其发布时快照绑定，逐条验证来源序号、载荷摘要、计划内容和 D7
命令，再选首个非保持 binding 验证 D6 observed-only join。末条保持 ACK 继续作为失败关闭
证据，不作为 `ack_applied` 样本。修复只涉及 D3 测试和文档，没有放宽 stale 门、改写时间戳
或修改比例导引。定向测试通过；D3 全量 439 项为 `438 passed, 1 skipped, 0 failed`，唯一
跳过为可选 OR-Tools。
