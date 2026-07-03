# D3 实现差距审计

**模块**: D3 集中式资源-目标分配  
**审计范围**: `subagent_reviews/D3_ASSIGNMENT_PLANNER_REVIEW_AND_PLAN.md`、`C_UAS_MAINSTREAM_SOLUTIONS_AND_DIFFICULTIES.md`、`research_modules/d3_assignment_planner/` 代码与测试。  
**边界**: 本审计只覆盖离线科研仿真中的抽象资源-目标分配、计划版本、终端反馈合同和 AirSim dry-run 适配；不涉及真实飞控、硬件、火控、毁伤或自动处置。

## 1. 总体结论

D3 已实现中心化 1 对 1 分配主线：`SciPy linear_sum_assignment`/Hungarian、fallback 动态规划、可解释代价矩阵、滚动重分配、迟滞、版本化 `AssignmentPlan`、stale plan 拒绝、D5 terminal feedback 保守决策 helper，以及 synthetic AirSim dry-run 输入适配。

仍未实现的主要是复杂约束和跨模块闭环：OR-Tools 最小费用流仅保留接口；`AssignmentValiditySummary` 尚未代码化；D5 terminal feedback 目前只通过 helper 给出建议，没有自动写回 planner 成本矩阵；AirSim dry-run 只接收合成 dict/object，不接入 AirSim/Blocks runtime；二级节点仲裁和 CBBA 属于 D4，不在 D3 当前实现内。

## 2. 实现差距表

| 预期项 | 当前状态 | 证据文件 | 未实现原因 | 缺失条件 | 建议优先级 |
|---|---|---|---|---|---|
| SciPy `linear_sum_assignment` / Hungarian 作为中心化 5v5 默认分配 | 已实现。`HungarianAssignmentSolver` 优先调用 SciPy；无 SciPy 时走 fallback DP。支持 dummy unassignment 列，允许目标未分配。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/solver.py`; `research_modules/d3_assignment_planner/tests/test_solver.py`; `subagent_reviews/D3_ASSIGNMENT_PLANNER_REVIEW_AND_PLAN.md`; `C_UAS_MAINSTREAM_SOLUTIONS_AND_DIFFICULTIES.md` | 不适用 | 仅需集成层提供归一化 `TargetTrack[]` 与 `ResourceState[]` | 已完成 |
| 小规模无 SciPy fallback | 已实现。`FallbackAssignmentSolver` 用位掩码 DP 求解小规模 optional assignment。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/solver.py`; `research_modules/d3_assignment_planner/tests/test_solver.py` | 不适用 | 大规模问题仍建议安装 SciPy，fallback 有列数上限 | 低 |
| OR-Tools Min Cost Flow / 最小费用流 | 未实现求解器，仅保留接口并显式抛出 `NotImplementedError`。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/min_cost_flow.py`; `research_modules/d3_assignment_planner/tests/test_min_cost_flow.py`; `research_modules/d3_assignment_planner/docs/ALGORITHM_AND_IMPLEMENTATION.md` | 当前 5v5 主线只需要一对一 Hungarian；OR-Tools 依赖未加入；容量、备份资源、时间窗等约束尚未进入主仿真。 | 需要确定 OR-Tools 依赖策略、整数代价缩放、容量/需求/禁配边数据结构、测试 fixture。 | 中 |
| CP-SAT / MILP 复杂逻辑约束 | 未实现。文档只列为更复杂离线研究方向。 | `subagent_reviews/D3_ASSIGNMENT_PLANNER_REVIEW_AND_PLAN.md`; `research_modules/d3_assignment_planner/docs/ALGORITHM_AND_IMPLEMENTATION.md` | 高频滚动主线不适合直接上 CP-SAT/MILP；当前缺少必须使用 MILP 的约束。 | 需要明确多阶段窗口、组合约束、求解时间预算和可接受降级策略。 | 低 |
| 滚动重分配 | 已实现。`AssignmentPlanner.plan()` 每个 tick 构建新候选计划，并与 `previous_plan` 比较。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`; `research_modules/d3_assignment_planner/tests/test_planner.py`; `research_modules/d3_assignment_planner/simulations/run_rolling_assignment.py` | 不适用 | 集成层需要持续传入 `previous_plan`、timestamp、window_id。 | 已完成 |
| 迟滞逻辑：`delta`、`min_dwell`、`max_changes_per_window` | 已实现。旧计划仍可行时，需满足收益、保持时间和变更上限才接受换配；否则输出 `held_by_hysteresis` 或 `held_by_change_limit`。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`; `research_modules/d3_assignment_planner/tests/test_planner.py`; `research_modules/d3_assignment_planner/docs/EXPERIMENT_REPORT.md` | 不适用 | 参数还需在 integrated 2v2/5v5 场景中继续扫描。 | 已完成 |
| 旧计划不可行时绕过迟滞 | 已实现。资源不可用、禁配边或旧边不可行时输出 `accepted_previous_infeasible`。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`; `research_modules/d3_assignment_planner/tests/test_planner.py` | 不适用 | 集成层需要把失效资源、不可分配目标和禁配边映射到 D3 输入。 | 已完成 |
| `AssignmentPlan` 版本、`plan_id`、stale plan 拒绝 | 已实现。版本单调递增；planner 记录最新 `plan_id/version`；旧版本继续滚动会抛出 `StalePlanError`。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`; `research_modules/d3_assignment_planner/tests/test_planner.py`; `research_modules/d3_assignment_planner/tests/test_airsim_dry_run_adapter.py` | 不适用 | 分布式/二级节点接入时需要统一传播 `plan_version` 和 stale 拒绝策略。 | 已完成 |
| 跨节点通信字段：`source_node_id`、`target_node_id`、`link_type`、`stale_after_s` | 已实现为兼容扩展字段，并写入 `AssignmentPlan`、`Assignment` 和 metadata。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`; `research_modules/d3_assignment_planner/tests/test_planner.py` | 不适用 | 需要主数据总线统一节点 ID、链路类型枚举和时效策略。 | 已完成 |
| 代价函数分解：窗口、协方差、威胁、资源状态、视场、冲突、不可行惩罚 | 已实现。`CostModel.edge_cost()` 输出 `cost_breakdown`。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/costs.py`; `research_modules/d3_assignment_planner/tests/test_costs.py`; `research_modules/d3_assignment_planner/docs/ALGORITHM_AND_IMPLEMENTATION.md` | 不适用 | 当前各项依赖外部归一化；尚未由 D1/D2/D5 自动派生完整真实几何代价。 | 中 |
| `reassignment_switch_penalty` | 已实现。换配时可在 assignment cost 和 breakdown 中暴露惩罚项。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`; `research_modules/d3_assignment_planner/tests/test_planner.py` | 不适用 | 集成场景需要确定是否启用，以及与 `delta/min_dwell` 的组合效果。 | 中 |
| D5 terminal feedback 合同：`ambiguous/hold/reacquire/mismatch` | 部分实现。`evaluate_terminal_feedback()` 可将 D5 状态映射为 `hold/replan/secondary_arbitration`，并保证 `allow_local_rebind=False`。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/tests/test_terminal_feedback_contract.py`; `research_modules/d3_assignment_planner/README.md` | 尚未和 `AssignmentPlanner.plan()` 自动联动；helper 只给建议，不直接修改成本矩阵或资源状态。 | 需要 integrated main 把 D5 反馈转成 `fov_difficulty`、`feasibility_by_resource`、`operator_hold` 或 D4 仲裁请求。 | 高 |
| 重复末端锁定风险 `duplicate_terminal_lock_risk` | 部分实现。模型字段和 helper 支持该风险，返回 `secondary_arbitration`。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/tests/test_terminal_feedback_contract.py` | D3 内部尚不统计多资源终端锁定冲突；只消费外部传入风险。 | 需要 D5/D6 或 main 提供同一 `global_track_id` 被多个资源 terminal lock 的聚合事件。 | 高 |
| `AssignmentValiditySummary` 主动降级摘要 | 未实现为代码数据类。文档中已有字段建议。 | `research_modules/d3_assignment_planner/docs/ALGORITHM_AND_IMPLEMENTATION.md`; `subagent_reviews/D3_ASSIGNMENT_PLANNER_REVIEW_AND_PLAN.md` | 当前只需 planner 基线和 helper；主动降级仲裁由 D4/main 统筹，D3 尚未形成统一 summary 对象。 | 需要 main 确定字段名、D4 接口、触发阈值、日志格式。 | 高 |
| D4 二级节点优先于 CBBA | 文档已明确，D3 代码仅返回 `secondary_arbitration` 建议，不运行 D4 接管或 CBBA。 | `research_modules/d3_assignment_planner/README.md`; `research_modules/d3_assignment_planner/PLAN.md`; `research_modules/d3_assignment_planner/docs/ALGORITHM_AND_IMPLEMENTATION.md`; `subagent_reviews/D3_ASSIGNMENT_PLANNER_REVIEW_AND_PLAN.md` | D4 负责降级接管，D3 不应内置 CBBA 或二级节点调度。 | 需要 D4 消费 D3 的 `recommended_action`/summary，并产生降级 `AssignmentPlan`。 | 中 |
| AirSim dry-run 适配 | 已实现 synthetic adapter。支持 dict/object 风格 `GlobalTrack`/`ResourceState`，无 AirSim import 或 runtime 调用。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/airsim_dry_run_adapter.py`; `research_modules/d3_assignment_planner/tests/test_airsim_dry_run_adapter.py`; `research_modules/d3_assignment_planner/docs/AIRSIM_INTEGRATION_PLAN.md` | 不适用 | 仍需要 main/AirSim 层提供 actor 到 synthetic dict 的抽取器；D3 不直接读 AirSim Blocks。 | 中 |
| AirSim / Blocks runtime 直接接入 | 未实现，且当前不建议在 D3 内实现。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/airsim_dry_run_adapter.py`; `research_modules/d3_assignment_planner/docs/AIRSIM_INTEGRATION_PLAN.md` | D3 边界是抽象分配，不应导入 AirSim 或调用仿真/控制 API。 | 需要 orchestrator 或 AirSim adapter 层把 runtime 数据转换为 D3 synthetic records。 | 低 |
| 5v5/8v8 离线滚动仿真与图表 | 已实现。默认仿真为 8 target / 8 resource、100 s、2 Hz，生成 CSV/JSON/图表。 | `research_modules/d3_assignment_planner/simulations/run_rolling_assignment.py`; `research_modules/d3_assignment_planner/results/EXPERIMENT_REPORT_GENERATED.md`; `research_modules/d3_assignment_planner/results/*.png` | 不适用 | 后续需补 integrated 5v5 AirSim ComputerVision actor 场景。 | 中 |
| D6 指标消费字段 | 部分实现。D3 输出成本、版本、decision_state、unassigned、changed 等字段；D6 指标表中需要的部分字段可从现有 plan 派生。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/docs/ALGORITHM_AND_IMPLEMENTATION.md` | 没有统一 `AssignmentRecord`/`AssignmentValiditySummary` 导出对象。 | 需要 main/D6 定义统一日志 schema，并决定由 D3 生成还是 orchestrator 派生。 | 中 |
| D7 PN 绑定接口 | 文档已有建议，D3 代码没有单独 `AssignmentGuidanceBinding`。 | `subagent_reviews/D3_ASSIGNMENT_PLANNER_REVIEW_AND_PLAN.md` | D7 属于导引模块；D3 当前 `AssignmentPlan.assignments` 已提供 `target_id/resource_id/plan_version`，但未封装 D7 专用结构。 | 需要 D7/main 明确 `guidance_phase` 与计划版本同步字段是否必须由 D3 直接生成。 | 低 |
| 分布式 CBBA / 拍卖 | 未在 D3 实现，符合边界。 | `C_UAS_MAINSTREAM_SOLUTIONS_AND_DIFFICULTIES.md`; `subagent_reviews/D3_ASSIGNMENT_PLANNER_REVIEW_AND_PLAN.md` | D4 是降级协同模块；D3 主线保持中心化。 | 需要 D4 在中心/二级不可用时消费 D3 最新计划作为基线。 | 不建议 D3 实现 |

## 3. 关键缺口按优先级排序

1. **高优先级**: 将 D5 terminal feedback 与 D3 planner 输入闭环打通。当前 helper 已能输出 `hold/replan/secondary_arbitration`，但需要 main 把反馈映射为 `fov_difficulty`、禁配边、`operator_hold` 或 D4 仲裁请求。
2. **高优先级**: 实现或由 main 派生 `AssignmentValiditySummary`，包含 `plan_age`、`assignment_latency`、`cost_margin`、`stale_plan_version`、`duplicate_assignment_count`、`unassigned_high_threat_count`。
3. **中优先级**: 增加 OR-Tools Min Cost Flow 可选后端。只有当 5v5 扩展到容量、备份资源、多窗口或分组约束时才需要。
4. **中优先级**: 为 AirSim ComputerVision 5v5 建立 orchestrator 侧数据抽取器，把 actor/camera 状态转成 D3 dry-run records。
5. **中优先级**: 定义 D3 到 D6 的统一 `AssignmentRecord` 日志格式，避免 D6 从多个 plan 字段临时拼装指标。
6. **低优先级**: D7 专用 `AssignmentGuidanceBinding` 可先由 main 从 `AssignmentPlan` 派生，除非 D7 需要 D3 直接输出 `guidance_phase`。

## 4. 风险说明

- D3 当前核心 Hungarian 分配和迟滞逻辑已经可用于 5v5 离线仿真，但如果 integrated main 只提供原始位姿而不提供归一化 `covariance/window_cost/fov/conflict/feasibility`，分配仍会运行，但代价缺乏真实判别力。
- OR-Tools 未实现不是当前主线阻塞项；它只阻塞复杂容量/备份/多窗口约束实验。
- D5 terminal feedback helper 不会自动阻止 planner 输出旧计划；需要 main 或 D4 根据 helper 的 `recommended_action` 执行 hold/replan/arbitration。
- AirSim dry-run adapter 不导入 AirSim，这是符合边界的；真正的 AirSim/Blocks runtime 接入应在 orchestrator 或独立 adapter 层完成。
