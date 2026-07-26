# D3 集中式 Assignment Planner 计划

## 2026-07-26 A1/C1/F1 学习准入复核

状态为“legacy assist 绕过已关闭，实际模型仍未准入”。

1. [x] 对照 main `d59352b` 检查 A1、C1、F1 的 bundle 需求、文件树哈希绑定、
   运行前预检和禁止规则回退合同。
2. [x] 关闭旧 `d3_learning_model_bundle_v2` 仅凭旧 promotion manifest 进入 assist 的
   缺口。v2 继续可用于 development shadow；assist 固定返回
   `bundle_assist_admission_missing`。`require_promotion_for_assist=False` 仍返回
   `promotion_bypass_forbidden`。
3. [x] 保持 v3 正向准入：只有 `stage=qualified`、允许 assist、外部保留评估通过且
   promotion 的数据、切分和权重 SHA-256 一致时，loader 才可能返回 assist。硬禁边、
   Hungarian/需求槽 Hungarian、计划版本和规则回退均未放宽。
4. [x] 只读复核实际 bundle，未修改旧 manifest 或权重。路径为
   `outputs/formal_bc_development_20260720/bundle/`；manifest/state SHA-256 分别为
   `a9213d65606a9e2f921040e153488c0f4cdebb10882fa16013fce5b59f9314c0` 和
   `e3da9fd5b54451da83358405b6051991e0c78bcf9f538b350d459b05faf8e0b2`。
   main 口径的 tree/binding SHA-256 分别为
   `3c08e58171c0474de9596fd3285d17bb50614a88cd7bbf3bf9af5345c7fee085` 和
   `70aa1b0f0f2869cdae0f9ba32b18499b003c88ebfcdb9e9dce0bc950b13542a8`。
5. [x] 当前实际 bundle 的 admission 为 development/shadow-only，promotion 为
   unavailable。模块 assist 返回 `bundle_shadow_only`；main 解析为
   `effective_mode=rule_fallback`、`bundle_loaded=false`。A1 在 episode 写盘前拒绝；
   C1/F1 同样拒绝 D3，并另受 D4/D5 准入约束。
6. [x] 核对 D6 现有 sidecar。文件 SHA-256 为
   `f3852251daf02ec87fe878e7fb80aad6f381d8c0756a5c956a32e737a3871c3b`，状态仅为
   `pass_offline_assignment_comparison_only`。runtime ACK、干预后物理结果和 paired
   non-degradation 均为 unavailable，不能生成新 admitted bundle。
7. [ ] main/D7 先生成模型实际采用的版本化 runtime ACK 和成对物理状态窗口；D6 再对
   至少 20 个未见 seed 输出可用的模型采用、物理结果和规则基线非退化结论。不可用指标
   不补零。
8. [ ] D3 只在上述外部证据可验证后生成一个新的 v3 qualified bundle，并绑定当前源码、
   数据、切分、权重和 D6 证据。不得修改现有 development bundle 自我晋级。
9. [ ] 新 bundle 首先由 main 执行：

   ```bash
   python3 -m research_modules.scalable_3d_simulation.run_experiment_matrix_shard \
     init-scope --scope-variants A1 --formal \
     --d3-model-bundle "$D3_ADMITTED_BUNDLE" \
     --output "$A1_EXECUTION_ROOT"
   ```

   只有 A1 预检和正式成对验收通过后，才评审 C1/F1；后两者还要求其他模块独立准入。
10. [x] 2026-07-26 定向 bundle 测试 `20 passed`；D3 全量收集 465 项，结果为
    `464 passed, 1 skipped`。唯一跳过是可选 OR-Tools，另有一条既有 Matplotlib
    `Axes3D` 导入告警。

## 2026-07-25 正式 R0 滚动需求 P0

状态为“代码已修复、开发复验通过、正式重跑待完成”。

1. clean commit `32b3b40` 的 `high_threat_m_to_n`、200v200、seed 1000、
   2.0 秒正式单元在 `t=1.0` 失败。`GT3D-000021` 的旧库存是无成员的
   `k=1` incomplete coalition，本周期需求升为 `k=3`，候选 coalition 已完整。
2. 同一周期另有多个 coalition 处于成员驻留期。全局成员迟滞试图保持旧计划，而旧计划
   可行性评分在“无 executable assignment”分支提前返回，漏掉上述需求合同变化。
   最终库存规范化因此抛出未治理异常。
3. 当前实现先比较旧/新 coalition 的需求合同，再判断旧目标是否有 executable
   assignment。需求数量、主资源数量、协同模式、时间合同或 assignment demand 不一致时，
   旧计划立即标为不可保留，采用当前求解器重新生成的版本化候选。
4. 该安全释放不放宽资源容量、资源唯一性、all-or-none、primary/reserve、stale plan、
   计划版本和需求一致性检查。最终库存规范化仍承担失败关闭校验。
5. 新增回归覆盖需求升高、需求降低、同需求成员迟滞保持、过分配拒绝和 200 输入规模。
   2026-07-25 D3 全量结果为 `464 passed, 1 skipped`，唯一跳过为可选 OR-Tools。
6. 同一配置的当前工作树开发复验完成 2.0 秒，有限状态为真、在线真值使用为 0。
   `t=1.0` 对 `GT3D-000021` 记录需求重建，最终 197 个 assignment 使用 197 个唯一资源，
   过分配和需求摘要失配均为 0。
7. 当前结果不是新的 formal R0 证据。旧失败制品仍绑定 `32b3b40`；main 需要在新 clean
   commit 下重建正式执行来源并重跑该单元及分片，才能关闭正式验收边界。

## 2026-07-25 多周期可辨识影子评估

本阶段已完成，范围限定为 D3 离线研究臂。

1. 新增规则组与行为克隆残差组的多周期成对评估器。每个周期共享匿名输入快照和外生事件，
   两组分别沿自己的上一计划连续推进，记录规范计划 token、版本、输入前序和声明前序。
2. 场景覆盖匈牙利切换边界、5资源3目标、3资源5目标、资源失效与恢复、目标增删和
   M-to-N 需求变化。规模由输入数组决定，没有写死 2v2 或 5v5。
3. 处理组只能执行
   `C_effective = C_rule + alpha * tanh(delta_C)`，并继续经过可达性、容量、友方冲突、
   身份承诺、需求槽完整性和版本门。异常、超时和分布外输入逐元素恢复规则矩阵。
4. 固定保留种子影子评估使用 1000-1019，训练种子为 0-99，交集为 0。620 个周期中有
   580 个周期实际改变代价矩阵，120 个周期最终绑定不同；受控切换边界 20/20 seed 均可辨识。
5. 重复资源、硬约束或谱系违规、旧版本采用和在线真值使用均为 0。40 个 M-to-N 周期因
   分布外输入回退，回退矩阵与规则矩阵完全相同。
6. 处理组抖动总数为 200，规则组为 520；处理组按规则矩阵重评分的周期平均代价高
   0.000707。该结果只说明当前冻结残差对切换稳定性和规则代价存在取舍，不构成收益判断。
7. PPO 未启动，线上 assist、authority 和计划发布均未开放。下一阶段仍需 main 提供真实
   运行 ACK、后续状态和物理结果，再由 D6 做成对非退化复核；在此之前不修改默认 Hungarian。
8. 当前结果绑定了训练种子注册表、模型清单、权重、数据帧和切分摘要，但生成时源码仍未
   形成 clean commit。该目录是开发证据；后续需在 clean worktree 复跑并记录源码提交和
   配置摘要，才能进入正式准入审计。
9. 收尾复核修复了 `cost_weights` 被接收但未传入规划器的问题。规则组和处理组现在分别
   构造独立 `CostModel`，共享同一冻结权重配置；专项测试验证零权重矩阵在两组完全一致。
10. CSV writer 显式使用 LF 行结束符。已从原结果重新生成逐周期和逐 seed CSV；规范化内容
    摘要不变，JSON、中文报告和核心计数无需改写。

验证日期为 2026-07-25。新增专项 9 项通过；D3 全量收集 460 项，结果为
`459 passed, 1 skipped`。唯一跳过仍为未安装的可选 OR-Tools。

## 2026-07-23 身份承诺准入

已完成最小实现：

1. `TargetTrack.identity_commitment_state` 支持 committed、两类 uncommitted，以及 D3
   内部的 missing/unknown 失败关闭状态。只有 committed 可以进入新计划。
2. 所有非 committed 状态在代价矩阵中形成硬拒绝。普通分配、M-to-N、增量规划和区域规划
   不能通过权重、学习残差或迟滞恢复该边。
3. main 负责根据 D2 状态触发 hold/replan。上一计划已绑定目标转为非 committed 后，D3 在
   被调用时去除全部普通及联盟绑定，严格升版并记录原因；不修改 `global_track_id`。
4. AirSim dry-run 适配器读取顶层、嵌套或 metadata 字段。字段缺失和未知值均拒绝，不使用
   真值 ID、actor ID 或目标数量推断承诺。
5. 专项测试 12 项通过；D3 全量 `450 passed, 1 skipped`，跳过项为既有可选 OR-Tools。
6. clean seed 1100 已完成运行时接线复核。固定提交
   `7e15dac9cdaf6743999dfe045a70676fd31a17d6`、`repository_dirty=false`、
   200 资源/200 目标、2.2 秒条件下，`hold_only` 与 `hold_plus_centroid` 两臂结果一致：
   `t=0.75` 发布 v1/193，`t=1.0` 对 11 个原 v1 目标执行身份未提交撤回，绕过迟滞并发布
   v2/186，`t=2.0` 发布 v3/186。
7. v2 明确记录 `identity_commitment_forced_replan=true`、
   `identity_commitment_replan_reason=previous_target_identity_uncommitted` 和
   `identity_commitment_hysteresis_bypassed=true`。11 个拒绝目标在 v2 中全部不存在；
   从 `t>=1.0` 起，D3、D5 主动视觉、D5 终端绑定和 D7 导引的违规继续执行均为 0。

main 按 `global_track_id` 接入 D2 commitment map、撤销旧绑定和采用严格新版本计划的
运行时链路已由上述 episode 验证。main 终态诊断中的 binding hold count 为 13、event count
为 1；13 是跨运行时绑定保持计数，不能写成 D3 拒绝目标数，D3 本次拒绝目标数是 11。

下一步保留三项工作：在多 seed 和动态非等量场景复核相同安全不变量；用独立的
AirSim/module regression 持续验证 stale plan 主动注入；评估 D1/D2 算法本身是否改善身份
连续性。本 episode 没有伪造 stale 输入，且两臂一致只证明 D3 安全撤回，不证明 D1
质心修正或 D2 关联收益。

## 1. 模块边界

D3 负责中心节点可用时的抽象资源-目标分配。输入是 D2/main 提供的 `TargetTrack[]`、`ResourceState[]` 和滚动时间戳；输出是版本化 `AssignmentPlan`、D7 可消费的 `AssignmentGuidanceBinding`、D4/D6 可消费的计划有效性摘要和 D6 assignment record。

D3 不负责：

- 末端视觉重绑。D5 可以报告 `ambiguous`、`hold`、`reacquire`、`mismatch`、`cross_view_conflict` 等状态，但 D3 不允许本地资源或末端视觉直接替换 `global_track_id`。
- 改写或重新命名 `global_track_id`。全局航迹 ID 由 D2/中心数据总线维护；D3 只在计划中引用它。
- D4 二级节点选择、CBBA/拍卖式分布式接管、中心恢复仲裁或主动/被动降级执行。
- AirSim Blocks 启停、episode 顺序、真实 runtime 日志采集、D6 存储、真实飞控/硬件/火控/毁伤或绕过人工授权的逻辑。

2v2、5v5 只是 baseline 场景名。运行规模由 main/runtime 的 `--drone-count N` 和输入数组长度决定，D3 不能写死 5v5，也不能假设目标数等于资源数。

## 2. 当前已实现状态

### 2.1 Hungarian / SciPy 主线

当前默认求解器是 `HungarianAssignmentSolver`：

- 优先调用 `scipy.optimize.linear_sum_assignment`。
- 在每个目标后拼接 dummy unassignment 列，支持资源少于目标、目标暂不分配或不可行边过滤。
- 当 SciPy 不可用或测试强制 `allow_scipy=False` 时，使用 `FallbackAssignmentSolver` 的位掩码 DP fallback。
- 代价矩阵尺寸来自 `len(tracks) x len(resources)`，并在计划 metadata 中记录 `assignment_matrix_shape`。
- 当前 plan metadata 同时记录 D4/D6 可回放的 current cost matrix、target/resource ids、per-edge cost breakdown、hard rejected edges 和 reject reasons；`assignment_evidence_from_plan(...)` 可导出结构化 evidence bundle。

测试覆盖：

- SciPy/fallback 行为：`tests/test_solver.py`。
- 非 5v5 动态规模：`tests/test_planner.py` 中 3 targets / 2 resources，验证 `resource_count=2`、`target_count=3`、`assignment_matrix_shape=[3, 2]`。

### 2.2 版本化 AssignmentPlan

`AssignmentPlan` 当前包含：

- `plan_id`、`version`、`window_id`。
- `resource_count`、`target_count`。
- `assignments`、`unassigned_target_ids`。
- `total_cost`、`candidate_total_cost`、`previous_total_cost_current`。
- `decision_state`、`changed`、`last_changed_at`。
- `source_node_id`、`target_node_id`、`link_type`、`stale_after_s`。

`AssignmentPlanner` 内部只记录已发布的最新 `plan_id/version`。首次调用允许 `previous_plan=None` 并生成 version 1；`plan(..., publish=False)` 生成的候选不推进 latest，审核或 owner/activation 盖章后由 `publish_plan(...)` 显式发布。已发布 active plan 后，后续调用必须显式传入该 active identity；缺失、旧版本、旧 id 或 `expected_previous_version` 不匹配均按既有 reason 拒绝。

计划 identity 由 `AssignmentPlan.execution_signature()` 和 lineage policy 共同约束。无论 `k=1` 还是 `k>1`，成员、角色、目标、owner、授权和执行状态均未变化时属于 evaluation refresh：保留 `plan_id/version/created_at`、assignment version、成员驻留时钟和 coalition `version/epoch`，仅设置 `evaluation_refresh_only=True` 并刷新成本诊断与 `last_evaluated_at_s`。真实 assignment/owner/activation/coalition 变化才推进执行版本；二级 owner takeover 等明确转换创建新 plan lineage。

M5N2 逐 pair 诊断合同已补齐但不改变上述 identity 规则。`AssignmentRecord` 和 D7 binding metadata 统一携带 plan owner/version、coalition id/version/epoch、member role、wave、activation、validity、`terminal_authorization_scope=per_primary`、授权资格、plan churn、rollback 和 stale reject。两个 primary 分别为 active/current/eligible；未显式激活的 reserve 始终为 standby、不可执行且不具终端授权资格。普通 current evaluation refresh 的 churn 为 0、rollback 为 false，且不重置 plan identity 或 coalition epoch。

`PlannerConfig.human_authorization_state` 当前会直接写入 `AssignmentPlan.human_authorization_state`，并同步记录到 `metadata["configured_human_authorization_state"]` 和 `metadata["effective_human_authorization_state"]`。这允许 main runtime 在仿真中使用 `"recorded"` 等记录态授权，而不是让 D3 固定输出 `"required"`。

### 2.3 滚动重分配与迟滞

每个 planning tick 的处理顺序是：

1. `CostModel.build_matrix()` 构建目标-资源基础代价矩阵和未分配代价。
2. 若存在 `previous_plan`，对已有 target 改配到不同 resource 的可行候选边加入 `reassignment_switch_penalty`；同 resource 边和 unassigned cost 不变。
3. Hungarian/fallback 使用加过 switch penalty 的矩阵求解候选计划。
4. 从当前 tick 矩阵派生 `d3_hysteresis_current_objective_v1` 比较口径：candidate 与
   previous 均按基础 target-resource cost、硬可行性和当前 demand/unassigned 规则
   重评分；switch penalty、soft-feedback FOV shaping、slot priority 和 role pin 仅
   作为候选搜索项，不进入单边 `delta` 比较。
5. 若候选计划与旧计划不同，只有满足收益、驻留时间和同 `window_id` 累计变更预算
   才接受；hold/refresh 不消耗预算，新 window 从零开始。

接受新换配的核心条件：

```text
J_new < (1 - delta) * J_old_current
and dwell_time > min_dwell
and changes_used_in_window + change_count <= max_changes_per_window
```

已实现的决策状态包括：

- `accepted`：首次计划或无迟滞情况下接受。
- `accepted_no_hysteresis`：关闭迟滞后接受候选。
- `unchanged`：候选 assignment 与旧 assignment 一致。
- `held_by_hysteresis`：旧计划仍可行，但收益或驻留时间不足。
- `held_by_change_limit`：收益和驻留时间满足，但本候选加入后将超过同窗口累计预算。
- `accepted_gain_and_dwell`：收益、驻留时间和变更限制均满足。
- `accepted_previous_infeasible`：旧计划在当前矩阵中不可行，允许绕过迟滞接受候选。
- `accepted_high_threat_release`：候选计划减少高威胁未分配目标时，允许带原因记录地释放迟滞。
- `held_by_transient_feedback_dwell`：版本匹配的短暂稳定性不足/reacquire 尚未达到 effective feedback window，旧 primary 可行时保持当前执行签名与 plan version。
- `accepted_transient_feedback_dwell_complete`：连续 transient feedback 达到 effective window，允许绕过普通 cost min dwell 发布候选。
- `accepted_hard_feedback_release`：硬反馈风险已确认但旧边尚未在成本矩阵中标为不可行，允许立即发布候选；若旧边已 hard reject，沿用 `accepted_previous_infeasible`。
- `accepted_execution_control_change`：plan-level owner、activation 或 authorization
  语义改变，立即发布新 identity，使旧 binding fail closed；联盟成员角色候选仍受
  成员迟滞，不按该状态绕过。
- `replan_ack_no_change`：forced replan 已处理，但执行签名未变化，计划 identity 不推进。
- `replan_applied`：forced replan 改变执行签名，计划 identity 推进一次。

迟滞结果会写入 plan metadata 和 D6 `AssignmentRecord`：`hysteresis_state`、`hysteresis_reason`、`hysteresis_reasons`、`hysteresis_release_reason`、`hysteresis_dwell_time_s`、`hysteresis_min_dwell_s`、`hysteresis_delta`、收益/驻留/变更限制布尔值、candidate change count，以及高威胁 release 前后的未分配计数。这样 D6 可以解释一次 hold 或 release 是由收益不足、min dwell、change limit、旧边不可行还是高威胁保护触发。

### 2.4 代价函数与输入规模

当前 `CostModel.edge_cost()` 输出可解释 `cost_breakdown`：

- `window`
- `covariance`
- `threat`
- `resource_state`
- `resource_energy`
- `resource_availability`
- `resource_current_load`
- `resource_history_failure`
- `fov`
- `conflict`
- `reassignment_switch_penalty`
- `intercept_feasibility`
- `infeasible`
- `total`

`TargetTrack` 支持 `fov_difficulty_by_resource`、`conflict_risk_by_resource`、`feasibility_by_resource`，可由 main 把 D5/D4/D2 的反馈映射进下一轮 D3 输入。`ResourceState` 支持 `status`、`health_score`、`busy_until`、`operator_hold`、`load_penalty`、`capability_class`，并补齐 P0-B 字段：`energy_fraction`、`availability_score`、`current_load`、`history_failure_rate`、`intercept_feasibility_by_target`、`intercept_feasibility_score_by_target`。`CostModel` 将能量、可用性、当前负载、历史失败率纳入 `resource_state`，并把能量耗尽、availability 为零、pair infeasible 和 intercept infeasible 标成硬不可行原因 flag。这些字段按输入数组长度运行，不依赖 2v2 或 5v5 常量。

P1 switch-penalty 矩阵接入已完成：penalty 在 solve 前写入 `CostMatrixResult.matrix` 和对应 edge breakdown，`breakdown["total"]` 与 matrix cell 相等。solver objective、候选 `Assignment.cost`、`candidate_total_cost/total_cost` 和 `AssignmentEvidenceExport` 共用该矩阵，不再在 solve 后追加 penalty，因此不会双重计费。不可行边、同 resource 边、无历史 assignment 的 target 和 `unassigned_costs` 保持原语义。

P0-C threat baseline 由 `compose_threat_score_baseline(...)` 提供：输入关键区接近、TTC、速度、协方差和目标状态，输出 normalized `ThreatScoreBaseline(threat_score, components, weights, reasons, metadata)`。`AirSimDryRunAssignmentAdapter` 在输入没有显式 `threat_score` 时会使用该 helper 生成 baseline，并把 components/reasons 写入 track metadata。完整动态威胁评估、资源状态耦合和 outcome-aware 标定仍是 P1。

`apply_terminal_feedback_to_planner_inputs()` 已把 D5 feedback metadata 分级映射为下一轮 D3 DTO：普通 ambiguous/hold/reacquire、几何/FOV/检测不稳定只提高当前边 `fov_difficulty_by_resource` 并保持 D7；friend overlap/verified friend 分别形成 resource-hard/target-hard；身份冲突、duplicate 和显式 feasibility reject 形成 hard reject。writeback 保留 target/resource/source plan version、coalition reason/conflict、stable count、required window 与 classification audit，始终 `allow_local_rebind=False`。`plan()` 与 `plan_incremental()` 在普通 cost hysteresis 前统一执行版本化 transient feedback dwell：`PlannerConfig.transient_feedback_dwell_frames` 默认 2，effective window 取该值与上游 `required_stable_frames` 的最大值；窗口未满且旧 primary 仍可行时保持原成员，窗口完成后的 soft candidate 仍进入成员/全局 `min_dwell` 迟滞。duplicate/friend conflict、wrong binding、失联、资源不可用、显式禁配或任何旧计划不可行立即绕过 dwell；不匹配 current plan version 的反馈只审计，不参与保护。该策略不降低 D5/D7 视觉门控，也不修改 PNG 核心。

真实 M=5/N=2 复验进一步确认，main event 没有 coalition reason/required stable fields：两个旧 primary 分别为 `consistent/continue`，旧 reserve 为单帧 `hold/hold`。旧逻辑将 reserve 的 `operator_hold` 提升为 whole-coalition infeasibility，因此求解器在替换 reserve 时同时重排 primary。D3 现按 `previous_plan` 的 target/resource/member_role 关联版本匹配事件；当所有旧 primary 均 `consistent/continue`、至少一个旧 reserve 为普通 `hold/hold` 或 `reacquire/replan`、旧 primary 边及能力仍可行且无硬冲突时，在 demand-slot matrix 固定旧 primary 集合，只生成 reserve 约束/替换 candidate，再由成员和全局迟滞决定是否发布。该规则不依赖 main 新增 reason、required window 或 member_role 字段；primary 自身 failure、duplicate/friend/wrong-binding conflict、primary 不可用、需求变化或 stale feedback 均禁用固定并沿用既定释放策略。

轻量 hard time-window baseline 已接入 Hungarian 主线，不引入 OR-Tools。`TargetTrack` 可用显式字段或 metadata 描述 `hard_time_window`、`time_window_open_at_s`、`time_window_close_at_s`、`time_window_state` 和按资源的 `time_window_by_resource`；窗口明确 closed/expired/not-yet-open 时，`CostModel` 把对应边标为 hard infeasible，输出 `hard_time_window_reject` 和 `reason_time_window_*` breakdown flag，planner 不会分配该边，并在 evidence metadata 中记录可解释 `reject_reason`。`window_cost` 仍作为 open edge 的软排序项。

### 2.5 D7 guidance binding

D3 已实现 `guidance_bindings_from_assignment_plan()`：

- 输出 `AssignmentGuidanceBinding`。
- 保留 `plan_id`、`plan_version`、`resource_id`、`assigned_global_track_id`、`target_id`、`authorization_state`、`guidance_phase`。
- 提供 D7 兼容别名：`assignment_id`、`id`、`version`、`track_version`、`owner`、`assigned_resource_id`、`global_track_id`、`human_authorization_state`、`source`、`target`、`link`。
- 支持 `active`、`stale`、`revoked`、`reassigned`、`hold` 状态。
- 在 metadata 中固定 `allow_local_rebind=False`。
- 新 plan 的 binding 即使发生资源-目标改配仍为 `active/current`；旧 plan 由当前 `plan_id/version` gate 判 stale/revoked，不把新 binding 标为 `superseded`。

D7 PN/PNG gating 的含义是：D7 只能消费当前版本且未被 D4/D5 gate 阻断的 binding；D7 不分配目标、不授权、不改写 `global_track_id`。当 D4 输出 `request_center_replan`、`degrade_to_secondary`、`degrade_to_distributed`，或 D5 未达到 terminal `locked`，D7 应保持/阻断视觉 PNG，而不是自行切换目标。

### 2.6 D4/D5/D6 辅助导出

D3 已实现以下 helper：

- `evaluate_terminal_feedback(...)`：把 D5 反馈映射为 `hold`、`replan` 或 `secondary_arbitration`，始终 `allow_local_rebind=False`。
- `apply_terminal_feedback_to_planner_inputs(...)`：兼容 D5 旧 metadata，分级写回 edge-soft/edge-hard/resource-hard/target-hard，并让成本矩阵、禁配边和 D7 gate 实际生效。
- `compose_threat_score_baseline(...)`：从关键区接近、TTC、速度、协方差和目标状态组合可解释 threat baseline；不替代 P1 完整动态威胁评估。
- `prepare_secondary_takeover_plan(...)`：在 D4/main 已选定真实二级节点且持续满足 `takeover_ready` 后，要求 candidate 的 `previous_plan_id` 精确指向当前计划、version 严格递增、leader epoch 单调且 lease 在激活时有效；成功后写入 active `secondary_plan_v2`、owner/source、readiness、activation、supersede、epoch/lease 和 `allow_local_rebind=False`。
- `continue_active_secondary_plan(...)`：active owner 已是 secondary 时，把下一普通 rolling candidate 继续盖章为同一 owner；要求 version/supersede 连续、concrete owner/source、readiness sustained、epoch 不倒退以及 previous/new lease 均有效且不回退。这不是新 takeover，不要求 owner 改变。
- `build_p1_assignment_fixtures()`：输出带 schema/profile/version 和 changed-id 合同的 5v5、3v5、5v3、新目标、资源失效、高威胁需求变化、D5 reserve feedback 和 hard-window fixture；标签明确采用 `resources x targets`。
- `run_p1_assignment_calibration_matrix()`：用独立 full/incremental planner 执行同一事件转换，汇总 latency、churn、unassigned high-threat、coalition shortfall、hard-window reject、fallback reason、assignment/cost equivalence 和 role-aware primary 保持；CLI 支持可选 `--output` 持久化同一份 `summary.as_dict()` JSON，并始终保留 stdout；只生成校准证据，不根据单次计时改默认路径。
- `assignment_validity_summary_from_plan(...)`：导出 `AssignmentValiditySummary(plan_age_s, assignment_latency_s, cost_margin, stale_plan_version, duplicate_assignment_count, unassigned_high_threat_count, resource_count, target_count, assigned_count, hysteresis_reject_count, stale_reject_count, reassign_count)`。
- `assignment_records_from_plan(...)` / `assignment_evidence_from_plan(...)`：除 current plan、N/M、成本、reject、迟滞和 secondary 字段外，输出 `assignment_profile_schema`、cost/feedback profile id/version、实际 `cost_weights` 和 `planner_thresholds`，供 main/D6 做同 profile 配对标定。
- `plan_history_record_from_plan(plan, sequence_index=..., timestamp=..., previous_plan=..., feedback_metadata=...)`：生成单 planning-tick 的 `PlanningTickHistoryRecord`；schema 固定为 `d3_plan_history_record_v1`，`to_dict()` 输出严格 JSON-native 白名单字段。main 提供的 `sequence_index` 与 `timestamp` 共同形成字典序 ordering key；assignment/coalition member/feedback/membership records 均稳定排序，任何 truth 命名字段不进入在线 history。
- `summarize_assignment_mismatch_replay(...)`：从 D6 assignment records 或 summary dict 聚合 N/M replay 字段：`resource_count`、`target_count`、`assigned_count`、`unassigned_high_threat_count`、`hysteresis_reject_count`、`stale_reject_count`、`reassign_count`。
- `summarize_terminal_feedback_calibration(...)`：输入多 seed assignment records/feedback records，输出 duplicate/friend/fov/geometry reject 计数，以及 cost/hysteresis 调参建议；该 helper 只给建议，不自动替换默认 `CostWeights`、`PlannerConfig.delta/min_dwell/max_changes_per_window/reassignment_switch_penalty`。
- `AirSimDryRunAssignmentAdapter`：接收 synthetic AirSim-style dict/object，不 import AirSim，不控制 Blocks runtime。

## 3. P2 Optional Benchmark：Min-Cost Flow / OR-Tools

当前容量约束对照是隔离 benchmark，不是默认 planner 后端：

- `p2_benchmark.py` 定义一份共享 `CapacityBenchmarkProblem`，同时送入 SciPy Hungarian 和 OR-Tools Min Cost Flow；fixture 为 4 resources / 3 targets / 5 demand slots，HIGH target 使用 `primary+primary+reserve`，资源容量为 `(2,1,1,1)`。
- Hungarian 通过按容量展开资源列求解，当前环境得到 objective `5.6`；Min Cost Flow 直接在 resource-to-sink arc 使用相同容量，不再局限于容量 1。
- `run_p2_capacity_benchmark()` 统一回映原始 resource/target/role，并输出目标值、耗时、assignment、容量和 `objective_delta/objectives_match`。当前环境未安装 OR-Tools，因此 flow outcome 为 `status="unavailable"` 且包含 `unavailable_reason`，不会抛出到 benchmark 调用者。
- `simulations/run_p2_capacity_benchmark.py` 输出结构化 JSON；low-level `MinCostFlowAssignmentSolver` 仍在直接调用且依赖缺失时抛 `OrToolsUnavailableError`。
- `ortools` 不进入默认 requirements，`AssignmentPlanner` 不自动选择该 benchmark。

仍不把 OR-Tools 作为默认路径的原因：

- `k_j=1` 和 demand-slot 高频 baseline 已由 SciPy Hungarian/fallback 覆盖。
- flow adapter 仅比较 demand-slot 容量和成本；role 随 slot 记录，但不表达 coalition 原子启用、committed prefix、波次同步或 reserve 激活逻辑。当前环境尚未产出 installed solver 结果。
- 更强约束应由 CP-SAT/MILP 小规模参考模型验证，不应把 flow benchmark 误称为完整 coalition solver。

计划策略：

- P2 capacity benchmark contract done：同一非等量 N/M、hybrid role 和容量输入可由 SciPy 求解，并可选调用 OR-Tools；缺依赖状态可机读。
- installed OR-Tools 的 objective/assignment 实证仍待隔离环境补跑；无 OR-Tools 环境保持默认全量回归通过。
- CP-SAT/MILP coalition 参考尚未实现；原子 admission、备份资源配额、多窗口、区域配额和预测性滚动仍属于 P2/P3 复杂约束。
- 默认在线路径仍是 SciPy Hungarian/fallback 与显式 demand 的 demand-slot 主线，未被 optional adapter 替换。

## 4. 已接入闭环与待校准项

### 4.1 Secondary takeover owner/version 状态

当前 D3 已闭合模块内 secondary activation 与 same-owner rolling 合同。首次接管使用 `prepare_secondary_takeover_plan()`；后续每次普通 `AssignmentPlanner.plan(previous_plan=active_secondary)` 的 candidate 必须经过 `continue_active_secondary_plan()`，否则 candidate 中的 center 默认 metadata 不代表可执行 owner。continuation helper 从 previous plan 派生 concrete owner/source，校验严格 version/supersede、持续 readiness、epoch 不倒退和 lease 有效/续期。D7 仍只接受显式 current identity，旧版本为 stale。

历史基线（2026-07-10）：main runtime 已接入 secondary owner/version/source 记录，但当时 20 个 `degrade_to_secondary` case 均保守转为 `degrade_to_distributed`，`secondary_plan_active=0`。2026-07-11 P1 验证已进一步通过二级接管和完全分布式的 commit 正例；缺 ACK 时 coalition 中止、D7 许可为 0，fail-closed 通过。该结果证明 D3 版本化 current plan/binding 可被下游 commit gate 正确消费，不把二级节点选择、ACK 协议或恢复仲裁归入 D3。

D3 边界保持不变：

- D3 不选择 `selected_secondary_node_id`。
- D3 校验激活快照中的 lease/epoch 并在 binding 导出时拒绝过期 lease，但不维护 lease 续期、leader 选举或中心恢复合并状态。
- 二级计划发布后，哪些 runtime 版本有效、中心恢复后如何拒绝旧二级计划或合并状态，仍属 main/D4 的 runtime policy，不列为 D3 DTO 缺口。

已验证并保持回归的跨模块合同序列为：

```text
pending_secondary_plan
-> takeover_ready (持续满足)
-> prepare_secondary_takeover_plan(exact supersede, version/epoch monotonic, live lease)
-> secondary_plan_active(owner=concrete secondary node)
-> planner.plan(previous_plan=current secondary)
-> continue_active_secondary_plan(same owner, renewed lease, non-regressing epoch)
-> old center plan rejected as stale
-> D7 consumes only the explicitly current, lease-valid secondary binding
```

### 4.2 D4 request_center_replan 中心重规划闭环

D3 的 terminal feedback helper 可以返回 `main_action="replan"` 或 `main_action="secondary_arbitration"`，并在 metadata 中给出 `d4_request`、`d7_gate_action`、禁配边或 `operator_hold` 建议。但当前没有 D3 内部自动调用 D4：

- `request_center_replan` 是否触发，由 main/D4 根据 D3 summary、D5 状态、D2 不确定性和 C2Health 综合决定。
- D3 不直接发 D4 action，不执行 `degrade_to_secondary` 或 `degrade_to_distributed`。
- D3 只能提供版本、成本、stale、重复分配、高威胁未分配和 D5 feedback 证据。
- 当 D4/main 触发 `request_center_replan` 并再次调用 D3 时，D3 会生成新的版本化 `AssignmentPlan`。
- 当前 main runtime 已把该中心重规划接入 AirSim episode bus：触发重规划后，新计划 metadata/log 记录 `replan_reason`、`supersedes_plan_id`、`supersedes_plan_version` 和 `active_plan_owner="center"`。
- D3 侧验收重点变为保持版本递增、stale `previous_plan` 拒绝、`human_authorization_state` 配置透传和 D7 binding 当前版本约束不退化。

### 4.3 真实 AirSim runtime 接线与校准

D3 有 synthetic dry-run adapter，不直接导入 AirSim。真实 AirSim Blocks 的 tick-to-plan-to-gate 闭环由 main/runtime 接线，当前已覆盖 D3 plan/binding/summary/record/evidence、D5 feedback writeback、中心重规划和 secondary owner/version 记录。2026-07-11 的 5-resource/2-target ComputerVision 10-seed 验证中，T001 双 primary 视觉共识与当前计划授权达到 8/10，seeds 7/27 保留回归；结合保守增量规划和 role-aware primary 保持实现，D3 的 P1 合同层已闭合。二级/分布式 commit 正例和缺 ACK fail-closed 也已通过下游验证。

2026-07-13 已按同一验收口径完成 M5N2 hybrid `2 primary + 1 standby reserve` 的真实 SimpleFlight paired 运行：baseline 与三个候选各 10 seeds，共 40 个 episode；本阶段不要求两个 primary 同时到达。baseline coalition completion 为 `0/10`，`20 m / 3 s / 40 deg` 为 `5/10`，其余两个候选分别为 `2/10` 和 `1/10`，最佳结果未达到 `8/10` 验收门限。该结果证明候选排序与逐 pair 合同能够进入真实 runtime，但不能宣称协同物理闭环已完成。计划版本/stale 拒绝、primary/reserve 角色和 reserve standby 安全合同保持，未发现 reserve 越权执行。

- D3 已提供 8 类 deterministic fixture、统一 paired runner 和 canonical `d3_plan_history_record_v1` exporter。fixture 覆盖 5v5、3v5、5v3、目标新增、资源失效、高威胁 `2 primary + 1 reserve` 需求变化、D5 reserve hold 与 hard-window；本地 8/8 转换的 full/incremental assignment/cost 等价。下一步由 main 在真实 AirSim episode 每 tick 调用 exporter 并写盘，而不是只保存最终 aggregate。
- D6 已能展开 40 个 M5N2 case 和逐 pair 结果；D3 schema/export 已完成，但正式 aggregate 尚无 main 写盘的逐 tick history，D6 也未据此计算 churn，因此 membership/version churn 当前仍必须报告为 `unavailable`，不得推断或补零。
- D3 已验证分级 feedback 对矩阵、reject、assignment 和迟滞的直接影响：普通 ambiguous/hold/reacquire 与几何/FOV/检测不稳定只形成当前边 soft cost 和 D7 hold，不设置资源 `operator_hold`；friend/verified friend、安全身份冲突、duplicate 和显式 feasibility reject 继续 fail-closed。下一步使用逐时刻 D5 feedback、计划版本和 outcome 做权重/迟滞配对扫描，并补真实 3v5、5v3、目标新增、资源失效和需求变化标定。
- 二级/分布式 commit 正例和缺 ACK fail-closed 已覆盖下游 current binding 消费；后续仅继续校准长时 lease、epoch 负例和中心恢复，不重开 D3 P1 合同。
- 校准完整动态威胁模型、增量/全量选择结果和 hard time-window 到达时间/多窗口输入；所有 fallback/reject reason 必须可由 D6 聚合。
- P2 同输入容量 benchmark 合同已完成；installed OR-Tools 求解实证、备份资源配额、分组配额和 CP-SAT/MILP 只进入隔离 benchmark。任何结果都不替换默认在线路径。

## 5. 跨模块接口影响

### 5.1 D4 主动/被动降级

被动降级由 D4/C2Health 判断，D3 只提供最新中心计划作为接管基线。主动降级中，D3 应提供：

- `stale_plan_version`：旧版本不得继续驱动 D5/D7。
- `cost_margin`：中心重分配是否有明显收益。
- `duplicate_assignment_count`：非零时优先 hold 或仲裁。
- `unassigned_high_threat_count`：持续非零时需要中心重分配或 D4 仲裁。
- D5 feedback 映射后的 `main_action` 和 `d4_request`。

推荐顺序是：中心仍可用且 Hungarian 能改善时先 `request_center_replan`；中心计划连续 stale、D5 多帧不一致或 D2/D1 不确定性升高时进入 `degrade_to_secondary`/二级仲裁；二级不可用后再由 D4 进入分布式 fallback。

`request_center_replan` 完成后，main/runtime 已把新中心计划登记为 active owner/version，并记录它 supersede 的旧计划版本；D3 只保证新计划版本化和旧计划拒绝。二级 takeover 完成后，D3 通过 `prepare_secondary_takeover_plan()` 强制登记 concrete secondary owner、精确 supersede、持续 readiness、激活时刻和必填 epoch/lease；main/runtime 仍负责 secondary node 选择、lease 续期、当前 owner 仲裁和中心恢复策略，并在导出 D7 binding 时传入当前 plan id/version。

### 5.2 D5 terminal association

D5 是末端视觉配准模块，不是分配模块。D3 文档和 DTO 必须保持以下约束：

- D5 不重新分配目标。
- D5 不创建、不改写、不换绑 `global_track_id`。
- D3 对 D5 的输入只发布“资源当前应关注哪个全局目标”的版本化 assignment。
- D5 反馈只能通过 main/D3 DTO 映射为下一轮 D3 的边级 soft cost、显式 hard reject、资源/目标 hard hold 或 D4/D7 gate，不允许本地视觉直接改写 assignment。普通 pair hold 不得写成资源 `operator_hold`；只有 friend overlap 等明确资源级风险可设置该字段。D3 侧 `apply_terminal_feedback_to_planner_inputs()` 已兼容旧 metadata 并输出分类审计；后续工作是长期标定 `fov_difficulty`、禁配边、hold/replan/secondary_arbitration 阈值和迟滞参数的相互影响。

### 5.3 D7 PN/PNG gating

D7 中段 PN 和末端视觉 PNG 应满足：

- D3 plan/binding version 当前有效。
- D4 action 允许继续中心计划；若 D4 要求 `request_center_replan`、`degrade_to_secondary` 或 `degrade_to_distributed`，D7 阻断视觉 PNG。
- D5 terminal association 为 `locked` 且与 `assigned_global_track_id` 一致。
- binding 未 stale、未 revoked、未 hold。

D3 提供 binding 和 gate 证据，但不产生导引律、不执行控制、不授权目标处置。

## 6. N 规模输入策略

D3 所有核心路径按输入列表长度运行：

- `target_count = len(tracks)`。
- `resource_count = len(resources)`。
- `assignment_matrix_shape = [target_count, resource_count]`。
- 当 `target_count > resource_count` 时，dummy unassignment 支持部分目标未分配。
- 当资源不可用、忙碌或 operator hold 时，该资源对应边被判为不可行或高成本。

P1 集成时，main 应保证：

- `--drone-count N` 只决定资源/actor 数量，不进入 D3 算法常量。
- 目标数可大于、小于或等于资源数。
- 2v2、5v5、8v8、非等量 M/N 都使用同一接口。

## 7. 当前 P0/P1 缺口与下一步优先级

### P0

- 2026-07-25 正式 R0 新暴露的滚动需求库存 P0 已完成 D3 代码修复和同配置开发复验。
  clean-source formal 单元/分片尚未在新提交上重跑，因此状态是“实现关闭、正式证据待补”，
  不能写成完整 R0 已通过。
- 旧“无 P0 blocker”结论已撤销。P0 `previous_plan` 连续性缺口已于 2026-07-10 修复并标记 done：首次调用仍允许 `None`；active plan 存在后省略 `previous_plan` 会以 `previous_plan_required` 拒绝并返回 latest plan id/version，版本不会回退到 1；新 episode 使用新 planner 实例。
- 其余 Hungarian/DP fallback、版本化 `AssignmentPlan`、迟滞与 stale 拒绝、D5 feedback helper/writeback、secondary takeover owner/version DTO、D7 binding、D6 export、`AssignmentEvidenceExport` 和轻量 hard time-window closed-edge rejection baseline 当前均已实现并保持回归。
- P0-B 已补齐：`ResourceState` 标准化 energy、availability、intercept feasibility、current load、history failure 字段，`CostModel` 消费这些字段并导出可解释资源状态/不可行原因。
- P0-B 增强迟滞已补齐：保留 switch penalty、min dwell、change limit、旧边不可行 bypass 和 stale 拒绝；新增高威胁 release condition 与 D6 可解释 metadata/export。
- P0-C 已补齐：`compose_threat_score_baseline(...)` 提供关键区接近、TTC、速度、协方差和目标状态的可解释 baseline helper；完整动态威胁评估不并入 P0。

### P1

- D5 feedback 分级治理 done（2026-07-14）：普通 ambiguous/hold/reacquire、几何/FOV/检测不稳定为 edge-soft，不能制造资源级不可行；friend overlap、verified friend、安全身份冲突、duplicate assignment/lock 和显式 feasibility reject 为 hard。transient 窗口完成后仍必须通过 `min_dwell`/成员迟滞。确定性验收为 5 个 feedback case；剩余是真实 D6 records 权重扫描。
- P1 canonical plan-history schema/export done（2026-07-14）：`PlanningTickHistoryRecord` 聚合 plan/count/owner/epoch/lease、ordered assignment/coalition members、迟滞/成员变化、soft/hard feedback、成本和 stale/rollback/replan 审计，`to_dict()` 可严格 JSON 序列化且排除 truth 字段。D3 不写盘；main 接线与 D6 churn 计算仍开放。
- P1 合同层 done：真实 AirSim ComputerVision 的 5-resource/2-target 10 seeds 中，T001 双 primary 视觉共识与当前计划授权达到 8/10；seeds 7/27 保留回归。demand-slot、计划 identity/no-change ACK、增量规划和 role-aware primary 保持已闭合。
- 下游合同证据 done：二级接管和完全分布式 commit 正例通过，缺 ACK 时 aborted 且 D7 许可为 0。该证据不把 D4 联盟协议归入 D3，也不等于物理拦截。
- 增量接口 done：`plan_incremental(...)` 用输入指纹验证 changed IDs，在可行二部图的独立连通分量上局部求解，保留未受影响且仍可行的 assignment/coalition member；漏报变更、目标/资源集合变化、需求变化、计划过期、时间相关约束或全局分量均带原因回退标准全量 `plan()`。expected/current version 不一致继续抛带 metadata 的 `StalePlanError`。
- N/M deterministic evidence done：8 类矩阵已覆盖 5v5、3v5、5v3、新目标、资源失效、高威胁需求变化、D5 feedback 和 hard-window；统一 summary 输出增量/全量 latency、churn、unassigned high-threat、coalition shortfall、reject/fallback 和 role-aware primary，8/8 转换 assignment/cost 等价。真实 AirSim 3v5/5v3 和动态事件仍需多 seed 校准。
- P1 物理/长期标定 open：2026-07-13 已完成 40 个真实 SimpleFlight M5N2 episode，最佳 `20 m / 3 s / 40 deg` profile coalition completion 为 `5/10`，其余候选为 `2/10`、`1/10`，baseline 为 `0/10`，未达到 `8/10`。D3 history schema/export 不再是缺口；下一步由 main 写盘逐 tick record，再由 D6 计算 churn，并继续 D5 feedback 权重/迟滞和真实动态 N/M 标定。
- 完整动态威胁评估：在现有可解释 baseline 上加入保护区、目标类别、资源状态和 mission outcome 标定，保留 baseline 对照。
- 时间窗口硬约束校准：覆盖到达时间、多窗口、closed/not-yet-open edge 和 reject reason 聚合，不重复实现已有单窗口拒绝 baseline。
- 二级 active plan runtime 验证：D3 takeover、same-owner continuation 和 current-binding 合同已完成；main/D4 需在 episode bus 调用两个 helper并验证 lease 续期、中心恢复与多 seed。
- 合同保持回归：维持 active-plan `previous_plan` 必填、solve 前 switch penalty、D5/D7 禁止本地 rebind、secondary current/lease/owner gate 和 D6 profile schema；schema v2/M-to-N 回归由 `test_m_to_n_demand_slots.py` 覆盖。

### P2

- OR-Tools Min-Cost Flow：同输入容量 runner、SciPy objective 和结构化 unavailable 已完成；当前环境 installed-only test skip，因此尚不能称为完成了已安装 flow 求解器实证。
- CP-SAT/MILP 小规模参考模型：尚未实现；仅规划为 optional benchmark，用于表达 coalition 原子启用、能力、同步和波次约束，不进入默认 requirements 或在线 planner。
- OR-Tools Min-Cost Flow 扩展研究：共享输入已覆盖单层资源容量；备份资源、分组配额或多窗口只在离线对照中评估，并保持 Hungarian/demand-slot 为默认轻量路径。
- 大规模参数扫描：扩展到 10x10、20x20 和更高密度混叠场景，形成 D5 feedback 权重、迟滞参数和 assignment quality 的长期对照表。

### 后续实施顺序

1. 保持 P0 和已完成 P1 接口回归，不重复实现 demand-slot、execution signature、forced replan ACK 或 optional Min-Cost Flow 接口。
2. done：事件驱动 `plan_incremental(...)`、输入快照、连通子图、安全全量回退和增量/全量 summary 已实现并完成 deterministic 测试。
3. next：用真实 3v5、5v3、目标新增、资源失效和高威胁需求变化多 seed 数据校准增量/全量延迟、迟滞、fallback 分布和未分配率；不得用单次延迟自动选择路径。
4. next：用 D6 records 配对标定 D5 feedback、完整动态威胁和 hard-window 输入，同时由 main/D4 验证 secondary active-plan 正负例。
5. P2 容量约束同输入 benchmark 合同已完成；后续补 installed OR-Tools 实证、CP-SAT/MILP coalition 参考、复杂 flow 和大规模参数扫描。任何 optional 结果不得替换默认 Hungarian/demand-slot 主线。

## 8. 验收命令

```bash
python3 -m pytest -q research_modules/d3_assignment_planner/tests
git diff --check -- research_modules/d3_assignment_planner subagent_reviews/D3_*
```

## 9. M 对 N 联盟分配研究计划补充（2026-07-11）

文献与开源审计见 `subagent_reviews/D3_M_TO_N_ASSIGNMENT_AND_SCHEDULING_REVIEW.md`。schema v2 与 demand-slot baseline 已于 2026-07-11 实现；本节同步实现状态，不改变既有 P2/P3 范围。

### 9.1 问题定义修正

既有“非等量 N/M”仍是一对一 optional assignment，只说明目标数和资源数可以不相等。新增 M 对 N 能力指目标 `j` 有资源需求 `k_j`；高威胁基准为 `k_j=3`。后续方案必须区分：

- `k_j=1`: 继续使用当前 Hungarian 默认主线。
- `k_j>1`: 形成版本化 coalition，并显式记录 required/assigned/shortfall，禁止把部分联盟记为任务完成。
- 合法 coalition multiplicity 不得计入 `duplicate_assignment_count`；异常超额、同一资源跨联盟冲突仍需记录。

### 9.2 P1 实现状态与后续顺序

1. done：`TargetDemand`、`CoalitionPlan`、成员 role/wave/window、demand summary 和 `AssignmentPlan schema v2` 合同已冻结并实现；`primary_resource_count` 接收 main `--cooperative-primary-count`，校验范围为 `1..k_j`。
2. done：`hungarian_demand_slots` 展开 target slots，按 threat penalty 优先 admission；不足或能力不匹配时整目标剔除并重解，不发布部分 executable assignment。
3. done：迟滞、change count、switch penalty 和 reassign export 使用稳定 set/signature；成员/角色变化才递增 coalition version/epoch，可执行窗口变化递增 plan version，纯成本/诊断重评不递增执行版本。
4. done：D7 multi-binding 与 coalition-aware duplicate 语义已实现；只有 committed/current coalition 可 active，合法 `<=k_j` multiplicity 不计异常。
5. P2 benchmark contract done / installed evidence pending：4-resource/3-target、5-slot hybrid primary+reserve 容量输入已在 SciPy 得到 objective `5.6`；OR-Tools 缺失时输出结构化 `unavailable_reason`，不进入默认 requirements 或默认 planner。当前环境未执行 installed flow 求解。
6. evidence updated：2026-07-13 已完成 baseline 与三个 profile 各 10 seeds、合计 40 个真实 SimpleFlight M5N2 episode；默认保持 `2 primary + 1 standby reserve` 且无同时到达要求。最佳 `20 m / 3 s / 40 deg` 为 `5/10`，其余为 `2/10`、`1/10`，baseline 为 `0/10`，未达 `8/10`。版本/stale/role 合同和 reserve 安全保持。
7. calibration pending：D3 canonical history schema/export 已补齐；下一步由 main 每 tick 写盘并由 D6 计算 membership/version churn，随后按真实 D5 feedback 校准代价权重与迟滞，并完成 3v5、5v3、目标新增、资源失效和需求变化等动态 N/M 多 seed 标定。本阶段不新增同时到达要求。
8. P2 optional：用 OR-Tools CP-SAT/Pyomo/PuLP 建小规模全局参考模型，对比 demand-slot admission 的最优差距；复杂同步动力学、committed prefix 和 reserve feedback policy 不进入默认在线主线。

### 9.3 跨模块输入与输出边界

- D1/D2 提供航迹状态、协方差和可达时间相关的不确定度，不由 D3 实施协同定位。
- D5 提供多视角一致性和观测几何证据，不允许改写 `global_track_id`。
- D7 提供成员 ETA/可达性并执行具体同步或波次导引；D3 只发布角色和目标时间窗。
- D4 在中心失效时负责 coalition 协商和成员退出后的重构；D3 提供最新中心 coalition plan 作为基线。
- D6 区分合法多资源 coalition 和 duplicate assignment，并评估 demand satisfaction、arrival dispersion、wave interval 和 coalition churn。

### 9.4 P0/P1 状态

- **P0**: 2026-07-25 的滚动需求库存异常已在 D3 代码和同配置开发复验中修复；新 clean
  commit 的 formal R0 重跑待 main 完成。现有 `k_j=1` Hungarian、plan version、
  stale rejection、迟滞和 `global_track_id` 约束保持回归。
- **P1 done**: `target_demand=k_j`、可配置 `primary_resource_count`、全有或全无 admission、成员角色、simultaneous/sequential/hybrid 波次、coalition version、coalition-aware duplicate、D7 multi-binding 和 demand summary 已实现并单测。
- **P1 evidence done**: 5-resource/2-target ComputerVision 10-seed 运行中 T001 双 primary 视觉共识与当前计划授权达到 8/10；二级/分布式 commit 正例及缺 ACK fail-closed 通过。D3 P1 合同层闭合。
- **P1 interface done**: `plan_incremental`、changed-set 完整性检查、独立连通分量求解、全量回退原因、M-to-N all-or-none、全局迟滞、分级 feedback、版本化 transient feedback dwell、reserve-soft-feedback primary role protection、canonical planning-tick history export 和增量/全量 comparison summary 已实现；帧级 transient 窗口不替代 `min_dwell`。
- **P2 capacity benchmark contract done**: 共享 4-resource/3-target、5-slot hybrid 输入已由 SciPy 求解；optional flow 缺依赖时输出 `unavailable_reason`，installed 实证待补。
- **Regression**: 2026-07-14 当前为 `157 passed, 1 skipped`；既有 canonical history、held-scope/lifecycle 和新增累计预算/统一成本测试均通过，唯一 skip 为当前环境缺少 optional OR-Tools 的 installed-only 求解测试。

## 11. 独立 Primary 合同与成员级迟滞（2026-07-12）

- 高威胁默认保持 `2 primary + 1 reserve`。合同显式输出 `terminal_authorization_scope=per_primary`、`arrival_coordination_required=false`；本阶段不要求 primary 同时到达。
- reserve 分配用于容量保留，但 D7 binding 为 `hold/reserve_standby_not_activated`，只有后续新版本改变角色后才能执行。
- `k>1` 成员迟滞按目标维护 `membership_changed_at_s`。当前成员可执行时，未满 2 s 或候选成本改善不超过 20%均保持原成员；资源失效、硬边不可行或 gain+dwell 同时通过才替换。
- 每轮输出 `membership_change_reason`、前后成员集合、成员成本、dwell/gain 判据和 `membership_hold_basis`。普通 evaluation refresh 保持 plan ID/version 与 coalition epoch，只更新非执行诊断。
- 默认 Hungarian/demand-slot solver、威胁 admission 和 all-or-none demand satisfaction 不变。
- **Physical loop evidenced / coalition still open**: 2026-07-13 已完成 40 个真实 SimpleFlight M5N2 episode；最佳 profile 为 `5/10`，未达 `8/10`。下一验收是 main 使用 canonical exporter 逐时刻写盘、D6 membership/version churn 可用性、D5 feedback/dwell 和真实动态 N/M 多 seed 校准，而不是增加同时到达约束。
- **P2 isolated benchmark only**: CP-SAT/MILP 全局参考、复杂 flow、复杂同步动力学和大规模参数扫描不得进入默认 requirements，也不替换 Hungarian/demand-slot 主线。

## 10. P1 M5N2 协同候选预筛（2026-07-12）

### 10.1 D3 已实现

- 新增通用 `CooperativePrescreenCandidate` 和固定 3x3x3 参数网格：末端交接距离 `20/30/40 m`、primary 到达窗口宽度 `3/5/8 s`、接近扇区间隔 `20/40/60 deg`。`candidate_id` 稳定，不包含固定 M/N 数量。
- `demand_for_cooperative_candidate()` 在调用方提供的 `TargetDemand` 上设置 primary 窗口宽度和候选审计字段，保留 required/primary 数、coordination mode、能力、wave interval 和 minimum separation。因此高威胁 `2 primary + 1 reserve` 保持现有合同，其他动态 k 值也走同一接口。
- `export_cooperative_candidate_plan_metadata()` 只导出当前 plan 的 candidate、arrival window、sector separation、member role/wave、plan/coalition version 和 minimum separation。primary 标为 active，reserve/retry 标为 standby；旧 plan、assignment version 或 coalition version 被拒绝。
- `rank_cooperative_candidates()` 只对 main/D6 提供的完整实测数据排序，固定优先级为：零安全违规、coalition completion 最大、pair success 最大、arrival spread 最小、candidate ID 稳定破同分。默认输出前三名，不预测或补齐缺失物理结果。
- Hungarian、demand-slot all-or-none admission、迟滞、版本推进、D5 feedback 和 D7 binding 主线均未修改。

### 10.2 Main/D6 执行结果与后续

1. 真实 AirSim 已完成 baseline 与前三候选各 10 seeds，共 40 个 SimpleFlight episode；两个 primary 独立按 5 m 结果计分，不要求同时到达。
2. coalition completion 分别为：baseline `0/10`、`20 m / 3 s / 40 deg` `5/10`、其余候选 `2/10` 和 `1/10`。最佳 profile 未达到 `8/10`，默认 Hungarian/demand-slot 与当前安全门控不变。
3. 计划版本/stale/role 合同保持；reserve 始终为 standby，未出现 reserve 越权执行。D3 已提供 canonical history schema/export，但正式 aggregate 没有 main 写盘的逐 tick records，membership/version churn 必须标记为 `unavailable`，不能补零。
4. 下一轮由 main 每个 planning tick 调用 `plan_history_record_from_plan(...).to_dict()` 写盘；D6 按 `[sequence_index, timestamp]` 排序后计算 churn，D3 再用这些证据标定 feedback 权重、`delta/min_dwell/reassignment_switch_penalty` 与动态 N/M 事件。
5. OR-Tools Min-Cost Flow、CP-SAT/MILP 和复杂容量约束保持 P2 optional，只做隔离 benchmark，不进入默认在线路径。

## 12. P1 Feedback 分级与抖动根因修复（2026-07-14）

- D3 内部将 feedback 分为 `resource_target_edge_soft`、`resource_target_edge_hard`、`resource_hard`、`target_hard` 和 `none`，并记录 scope、classification reason 与 hard-reject 标志。
- 普通 `ambiguous/hold/reacquire` 及几何、FOV、检测稳定性问题只提高当前 resource-target 边代价并保持 D7 gate；旧 `operator_hold_suggested/resource_update` pair metadata 继续可读，但不会扩大为整资源 hold。
- `friend_overlap_hold` 保持 resource-hard，verified friend 保持 target-hard；身份安全冲突、duplicate assignment/lock 与显式 feasibility reject 保持 hard reject。资源 DTO 已为 unavailable 时仍由 `CostModel` 对全部资源边硬拒绝。
- transient feedback 帧窗口仅提供前置保护。窗口完成后的 soft candidate 仍进入 coalition/global `delta/min_dwell/change-limit` 迟滞；硬冲突和旧边真实不可行仍可立即释放。
- 2026-07-14 确定性验收新增 5 个 feedback case，验收标准是 ordinary hold 不产生 resource hold、hard 类仍拒绝、soft candidate 在 dwell 未满时保持旧计划。
- 40-case SimpleFlight aggregate 缺逐 planning tick history。普通 hold 扩大为资源不可行是 churn 根因线索，但现有 40-case 证据不能证明它导致了特定 membership/version churn 或物理失败；因果验证仍需逐 tick 配对日志。

## 13. P1 Canonical Planning-Tick History（2026-07-14）

- schema 为 `d3_plan_history_record_v1`，公开类型/API 为 `PlanningTickHistoryRecord`、`plan_history_record_from_plan(...)` 和 `to_dict()`；`assignment_records_from_plan(...)` 保持兼容。
- main 必须提供非负 `sequence_index` 和有限 `timestamp`。history 顺序由 `[sequence_index, timestamp]` 字典序建立，不从可能保持不变的 plan version 推断 tick 顺序。
- plan 级字段每 tick 只出现一次：plan schema/id/version/window、changed/decision、N/M/assigned count、owner/source、secondary version/leader epoch/lease、lineage、成本、stale/rollback/replan reason。
- assignment 按 target/coalition/wave/role/resource 排序并记录 primary/reserve activation、active、coalition id/version/epoch/completeness、validity/feasibility 和 cost；coalition 输出稳定排序的可恢复成员集合。
- 迟滞 state/reason/dwell/delta、membership change records、feedback class/scope/reason 与 soft/hard count 均进入审计。`feedback_metadata` 可传 `TerminalFeedbackWriteback.metadata`；缺省兼容读取 plan metadata 与旧 `terminal_feedback_events` 命名。
- `to_dict()` 只返回 JSON-native 值并递归排除 truth 命名字段；该在线 schema 不接受 truth label，不改写 `global_track_id`。
- 2026-07-14 新增 5 个 history case，随后补充 3 个 held-scope/lifecycle case；当前全回归为 `157 passed, 1 skipped`。这关闭 D3 schema/export 与 hold identity P1，不代表跨模块多 seed 已闭合。

## 14. AirSim Seed 001 计划身份复核与 P1 修复（2026-07-14）

### 已完成

- 读取 main 已写盘的 349 条 `d3_plan_history_record_v1`，复原初始 4 个 assignment
  记录、后段 D2 新生航迹、最终 5 个 pair 和 v1 至 v45 的变化链。
- 修复 hold 分支把当前新目标写入上一 current plan 执行范围的问题。普通 hysteresis、
  coalition membership hysteresis 和 transient feedback dwell 都保留上一计划的
  `unassigned_target_ids`、`incomplete_target_ids`、coalition 和 assignment。
- 新增候选范围审计：candidate target/unassigned/incomplete、held execution target、
  pending new target、missing previous target 和明确的 audit-only policy。
- 新增普通一对一迟滞与 M-to-N 联盟成员迟滞回归。验收要求 plan ID/version 和
  execution signature 不推进，动态 `target_count` 仍反映本 tick 输入。
- 上一 current plan 的已分配目标若从当前输入消失，立即标记 previous infeasible，
  输出 `previous_missing_execution_target_ids` 并发布新版本，不能被 same-assignment
  快路径或 dwell 持续保留。
- D3 当前全量 `157 passed, 1 skipped`，语法和 diff 检查通过。

### 不在 D3 内绕过的根因

- T008 等后段航迹由 D2 生命周期产生；main adapter 当前将 tentative/confirmed 也
  视为 assignable。下一步应在 main/D2 输入合同中只提交 engageable 或显式批准航迹，
  而不是在 D3 内用 truth、固定目标数或隐式年龄阈值过滤。
- 初始稳定双目标阶段每约 1 秒发生一次成员切换，均满足该 episode 的
  `delta=0.2`、`min_dwell=1.0 s`，因此不是 stale/version 规则违规，但属于 P1 参数
  治理不足。main 多 seed 应扫描 `min_dwell`、`max_changes_per_window` 和
  `reassignment_switch_penalty`，并约束高威胁未分配率不得恶化。
- D3 reserve binding 仍为 standby/hold。runtime 必须在 current binding 把资源从
  primary 改成 reserve 时撤销旧 active pair；该修复由 main/runtime owner 完成。

### 下一验收

使用同一几何至少 10 seeds 重跑并比较修复前后：held-version advance count 必须为
0；每次执行版本变化必须对应 assignment/coalition/owner/activation 的真实变化；
在线 truth 使用为 0；上游未准入航迹不得形成 assignment。该批次由 main 调度，D6
聚合，D3 不直接控制 AirSim。

## 15. P1 同窗口计划抖动关闭批次（2026-07-14，已完成）

本批针对 truth-isolated M5N2 seed-1 的 347 条 planning records、plan v1..v35 和
约每秒往返换员现象，限定在 D3 planner 与 D3 文档内完成以下工作：

1. 将 `max_changes_per_window` 从“单次 candidate 的 `change_count` 上限”改为同一
   `window_id` 内已发布执行变更的累计预算；hold/refresh 不消耗预算，新 window
   从零恢复，硬失效与执行语义强制变化不受普通抖动预算阻塞但必须留审计原因。
2. 为 candidate 与 previous 建立同一 objective cost basis：两者都按当前 tick 的
   target-resource 基础成本与相同 unassigned/demand 口径重评分；switch penalty、
   feedback pin 和 demand-slot 展开只用于候选搜索/可行性，不得只落在一侧后参与
   `delta=20%` 改善判断。
3. 在目标、资源、需求和 owner/activation 稳定且只有小幅成本噪声时保持 execution
   signature 与 plan identity；确定性往返候选不得周期性推进版本。
4. execution target 消失、资源硬失效、owner/activation 执行语义改变时立即生成
   fail-closed 新版本；missing target 与另一 coalition membership hold 同时出现时，
   输出不得保留消失目标的 coalition、assignment 或 membership audit。
5. 新增确定性回归，覆盖往返候选、同窗口累计预算、跨窗口预算恢复、真实资源硬
   失效，以及 missing-target + membership-hold 组合；算法继续按输入规模运行，
   不消费 truth，不改写 `global_track_id`。

验收条件：上述回归全部通过；metadata 明确记录 cost-basis schema、窗口预算已用/
剩余/候选/是否绕过及原因；执行 `python3 -m pytest -q
research_modules/d3_assignment_planner/tests` 与 `git diff --check --
research_modules/d3_assignment_planner subagent_reviews/D3_*` 均通过；完成后同步本
`PLAN.md`、模块 `README.md`、D3 GAP audit 与 D3 review，并记录实际日期、场景、
样本数、结果、阈值和剩余限制。

完成结果：新增 `tests/test_p1_plan_churn_budget.py` 的 5 个确定性测试函数，覆盖 soft
feedback/小幅往返噪声、同窗口累计预算、跨窗口恢复、预算耗尽后的资源硬失效、
missing-target + 另一联盟 hold，以及 plan-level owner 切换。全量验收为
`157 passed, 1 skipped`，接受阈值为零失败；skip 仅为当前环境未安装 optional
OR-Tools。最新真实日志仍是 1 个 M5N2 seed、347 records、v1..v35，只作为修复动因：
本批未重跑 Blocks，至少 10 个同几何 seeds 的 churn/高威胁未分配/物理结果仍由
main+D6 验收。D3-owned 周期性换员实现缺口已关闭；main/D2 lifecycle admission、
runtime reserve demotion 和 M5N2 `8/10` 物理门限仍是剩余 P1。

## 16. Actual-v2 真实证据同步（2026-07-14）

- tuned 2v2 seed 1：command/actual/history 均为
  `d3-plan-c3cc6d28c365/1`，history 24 条。
- M5N2 seed 1：command/actual/history 均为
  `d3-plan-cfdd088a10e1/1`，history 214 条。
- D6 history available/unavailable=`2/0` 且无 validation reason；actual required
  cases `2/2` available，因此计划身份可追溯 P0 关闭。
- M5N2 feedback churn=50，但 plan version/membership/owner churn 均为 0；该单
  seed 仍需 P1 参数标定。
- M5N2 pair/target/coalition=`2/3`、`2/2`、`0/1`，第二 primary 最近约
  11.02 m。目标级 `2/2` 不是联盟完成；第二 primary 与多 seed 继续为 P1。

## 17. M5N2 20-Case 证据同步与后续计划（2026-07-15）

### 已完成

- 只读复核 baseline 10 seeds 和 candidate 10 seeds 的 20 个
  `d3_plan_history.json`，共 `3725` 个 planning tick；M5N2 聚合只包含这 20 个 case。
- canonical history 的 case/record 可用率为 `20/20`、`3725/3725`。所有记录均带
  plan identity、owner、5-resource/2-target 规模、primary/reserve assignment、
  coalition、迟滞、membership audit、stale 和 rollback 字段。
- 每个 case 的 current plan 始终为单一 `plan_id/version=1`，实际 plan-version、
  owner 和 member-roster transition 都为 0。20 个初始 accepted tick 之后，`3524`
  个候选由 coalition membership hysteresis 保持、`150` 个由 transient feedback
  dwell 保持、`31` 个由全局 hysteresis 保持。
- `3555` 条 membership audit 中，`3524` 条为 `coalition_membership_hold`，`31` 条
  为 member gain/dwell 通过后由更外层迟滞阻断；它们不能计为 actual churn。
- T001 始终满足 D3 计划合同 `2 primary + 1 standby reserve`，T002 始终为
  `1 primary`。资源成员跨 case 可变化，因此不固定第二 primary 资源编号。

### 结果边界

系统物理聚合为 pair `12/60`、canonical target `12/40`、coalition `0/20`；T001
第二 primary `0/20` 进入 5 m，且 20 个 stop reason 都是 `collision_stop`。D3 history
没有碰撞对象字段，因此只确认计划身份和成员稳定，不能判断是成员间冲突、环境碰撞
还是 AirSim 状态问题。candidate 的系统级 paired non-degradation 失败不构成 D3
算法退化证据；该 candidate 改变的是下游软预测/趋势 coast 试验，而 D3 两组均保持
稳定 current plan。

### 后续 P1

1. main/D6 统一 `canonical target success` 和 `cooperative target diagnosis`：前者
   继续按 40 个目标样本统计，后者单独报告 T001 两个 primary、第二 primary 和
   coalition，禁止以 target `12/40` 代替 coalition `0/20`。
2. main/D7/AirSim runtime 补充 `collision_stop` 的碰撞对象与触发来源；D3 只消费
   结果，不在缺证据时修改 Hungarian、demand-slot 或迟滞默认值。
3. D3 后续真实标定转向 3v5、5v3、目标新增、资源失效和需求变化；继续复用已写盘
   canonical history，报告 actual roster/version churn、高威胁未分配和 shortfall。
4. `png_ttc_2v2_seed001` 明确排除在本批 M5N2 聚合之外；未运行的 tuned/dropout
   case 保持 `unavailable`，不得补零。

本次文档同步验收：20/20 history 可读且无 record 缺失，计划/成员/owner churn 可
计算；`python3 -m pytest -q research_modules/d3_assignment_planner/tests` 为
`157 passed, 1 skipped`，零失败达到门限。物理 5 m 和 coalition 门限未达到，继续
按上述 P1 执行。

## 18. 可扩展三维规则与学习辅助计划（2026-07-20）

### 已实现范围

1. `PlannerConfig.scalable_3d()` 显式开启三维规则 profile；旧 profile 和无三维字段
   输入保持原代价语义。
2. 规则边增加解析三维截获时间/距离、NED 位置协方差和区域项。不可达、容量为零、
   友方冲突、区域不兼容继续作为硬约束，不允许学习残差覆盖。
3. 候选图按区域/可达性过滤，再按每目标规则成本 top-k 稀疏化。每目标保留数不低于
   `required_resource_count`，并额外保留上一 current plan 中仍可行的成员边。
4. 最终求解器仍为 Hungarian 或 `hungarian_demand_slots`；高威胁 M-to-N 继续通过
   显式 `TargetDemand`、角色/波次和 all-or-none admission 表达。
5. 学习只在稀疏边上输出共享 `delta_C`，assist 公式固定为
   `C_final=C_rule+alpha*tanh(delta_C)`。动作掩码覆盖规则不可达、容量、友方冲突和
   plan version；timeout、低置信、OOD、非有限/错误形状和模型异常均回退 `C_rule`。
6. `shadow` 只记录候选修正，不改变 solver 输入；`assist` 也无权直接输出 assignment。
   `AssignmentPlan` 的 execution identity、递增版本和 stale rejection 沿用现有合同。
7. 原生 PyTorch `SharedCandidateEdgeResidualPolicy` 使用共享 MLP 处理 `E x 12` 特征，
   `E` 为稀疏边数；`behavior_clone_warmup` 提供最小监督预热。没有 40,000 维自由
   动作头，也没有引入 gymnasium/stable_baselines3。

### 确定性验收

验证日期为 2026-07-20。新增 13 个测试，样本包括 1 个 3-target/5-resource、1 个
5-target/3-resource、1 个 200v200、1 个 2-target/5-resource M-to-N、规则成本与
mask/fallback/version cases，以及 1 个 32-edge synthetic BC batch。接受阈值为测试
零失败、200v200 完整分配、候选动作严格少于 40,000、stale 不得接受、所有 fallback
与规则矩阵逐元素相同。

实际结果为 200/200 分配、800 条候选边/动作、候选密度 2%；单次本地调用 0.621 s，
仅作为功能时延样本，不据此宣称实时。D3 全量为 `170 passed, 1 skipped`，唯一 skip
为当前环境未安装 optional OR-Tools。

### 开放训练与系统缺口

- 尚无真实轨迹上的 BC 数据集、checkpoint、train/validation/未见 seed 划分和收益
  指标；32-edge synthetic batch 只证明接口可训练。
- 尚未完成 shadow 多 seed 非退化、置信/OOD 标定、GPU/CPU deadline 分布和可抢占
  timeout。当前 timeout 是调用返回后的 deadline 检查，超时结果不进入 solver。
- 未实现或验收大规模 PPO；不得把本批写成 PPO、强化学习收益或 20-seed 验收完成。
- 区域划分/邻区许可由上游提供；D3 未实现跨区域配额 RL。解析可达性也不代替 D7
  动力学、障碍/航路规划、友方轨迹解冲和 AirSim 物理闭环。
- 200v200 当前仍构造确定性 dense solver matrix，并以 infeasible penalty 表示稀疏
  图外边；策略和 evidence 已稀疏，但更大规模的 sparse flow/auction 仍是后续研究。

## 19. 200×200 性能收敛与区域计划合同（2026-07-20）

### 本轮目标

1. 复现 200 resource × 200 target、top-32 时约 1.97 s 的 D3 耗时，区分成本构造、
   求解和证据输出。
2. 保持规则代价、不可达约束、M-to-N demand slot、迟滞、学习有界修正和规则回退，
   去除全 `N×M` Python 边对象计算。
3. 保留 SciPy Hungarian 默认路径，在稀疏候选图上按连通分量构造局部求解矩阵。
4. 为 D4 已裁决的多 secondary owner 和 distributed peer coalition 提供 D3-owned
   区域计划发布合同。D3 只验证并发布，不自行决定降级。

### 已完成

- `CostModel` 增加可开关的向量化稀疏路径。可扩展 profile 默认启用；复杂资源目标
  字典覆盖和时间窗输入自动回退旧参考实现。
- NumPy 批量计算三维截获、协方差、区域和资源状态；top-k 排序保持成本和资源编号
  的确定性顺序。候选 breakdown 物化数由 40,000 降到 6,400。
- Hungarian 支持候选二部图连通分量的局部矩阵；SciPy 仍为默认，未增加强制依赖。
- 新增区域 authority/commit DTO 和 `plan_regional_authority()`。来源计划不匹配、
  旧 epoch、过期 lease、重复资源、非候选边和需求不足均 fail closed。`k=1` 依赖
  D4 已裁决的单成员区域授权；`k>1` 的缺 ACK、未 committed 或非 atomic coalition
  继续 fail closed。
- 多 owner 只记录在同一版本化 `AssignmentPlan` 及每条 assignment 上，不创建本地
  `global_track_id`，也不改变 D7 的 current binding 规则。

### 验证证据

验证日期为 2026-07-20。D3 独立 200×200、top-32、5 次同输入基准中，旧路径中位
`1904.261 ms`，新路径中位 `85.367 ms`，加速 `22.307×`；两条路径均完成 200 个
assignment。结构检查证明新路径 Python 全边成本调用为 0。20×23 逐边对照验证规则
矩阵、候选掩码、拒绝原因和 breakdown 一致。

区域专项覆盖 2 个 secondary owner、secondary/distributed k=1、D4
`single_member_authorized` summary，以及 distributed k=3 committed、缺 ACK、无授权、
owner/epoch/member 不一致、错误 atomic/commit-required 标记、重复资源、旧 epoch、
过期 lease 和 stale source。求解专项覆盖不连通局部矩阵和无候选目标。D3 全量结果为
`193 passed, 1 skipped`，接受阈值
为零失败；skip 仅为 optional OR-Tools。

### 后续集成

1. main 将 D4 `RegionalFailoverDecision.region_decisions` 映射为 D3
   `RegionalAuthorityInput`，不得把 D4 truth 或本地身份写入 D3。
2. main 在 center failure、多 secondary owner 和 secondary failure 场景中验证
   `plan_version` 严格单调、stale=0、过期 lease 执行数=0、缺 ACK 执行数=0。
3. D6 消费区域 owner/epoch/lease/commit 和 D3 阶段耗时，完成 5/20/50/100/200
   多 seed 报告。当前模块基准不等于全栈实时验收。
4. AirSim adapter、actor、控制或话题接口本轮未改变；相关集成计划检查后无需修改。

## 20. D4-D3 单成员区域授权合同对齐（2026-07-20）

### 对齐原则

- `required_resource_count == 1` 表示区域 owner 对一个资源成员的授权，不建立多成员
  原子联盟。secondary 和 distributed 层级使用同一规则。
- D4 未提供 commit summary 时，D3 依赖 grant 的 current source plan、epoch、lease、
  `execution_allowed`、唯一资源和规则可行性发布。
- D4 提供 k=1 summary 时，D3 只接受 `commit_required=False`、状态
  `single_member_authorized`、`atomic_committed=False`、执行授权有效、成员完整和
  当前租约。
- `required_resource_count > 1` 继续要求 `commit_required=True`、committed、atomic
  committed 和全 ACK。该安全门没有放宽。

### 审计和待集成

计划、区域记录、联盟和每条 assignment 现在区分 `single_member_authority` 与
`atomic_coalition_commit`，并记录 commit 是否必需、是否提供 evidence 和实际 state。
main 应直接映射 D4 `CoalitionCommitSummary.commit_required`，D6 应按该模式分别统计
单成员授权和原子联盟提交。本轮仅完成 D3 模块合同；main 的 DTO 映射和故障场景集成
回归仍待执行。

## 21. 故障代际 Fence（2026-07-20）

### 已实现

1. 新增 `advance_authority_generation()`，输入当前已发布计划、timestamp、精确前序
   version 和 fence reason；接口始终通过 D3 `publish_plan()` 登记。
2. 新计划只更新 `plan_id/version/created_at` 和 assignment 的计划上下文版本。
   assignment 成员、目标身份、coalition identity/version、owner、授权状态、总代价和
   `last_changed_at` 保持不变。
3. metadata 明确记录 fence schema、reason、source plan、generation、non-reassignment、
   non-execution-authorization 和 D4 gate requirement。
4. `publish_plan()` 对同执行签名新身份只开放严格 fence 例外。普通 evaluation refresh
   仍不得推进 identity；错误来源、重复版本和任何执行语义变化均拒绝。
5. 连续 fence 按 v1 -> v2 -> v3 单调推进。每次发布后，上一代立即进入 stale 状态。

### 安全边界

Fence 只解决 D4 要求“owner 变化前必须先提升 D3 generation”的前置条件。它不选择
owner、不改变授权、不执行重分配，也不表示 D4 已允许继续任务。D7 必须继续消费 D4
hold/continue；任何直接把 fence 当成执行许可的 main 适配都属于合同错误。

### 验证与后续

新增 5 个测试覆盖正例、expected version 错误、成员/coalition 身份不变、连续 fence、
重复发布和 coalition 篡改。D3 全量 199 项，`198 passed, 1 skipped`，零失败达到门限。
main 后续在 50v50、`recon_count=2`、中心故障路径中调用接口，并复验 D4
`authority_generation_not_advanced=0`。本轮未修改 AirSim adapter、actor、settings 或
控制接口，AirSim 集成文档检查后无需修改。

## 22. 可复现学习研究管线（2026-07-20）

### 已完成的 D3-owned 能力

1. 数据集合同已升级到 `d3_learning_dataset_v2` 和
   `d3_numeric_seed_atomic_split_v2`。采集帧先标记 `unassigned`，finalize 使用完整唯一
   数值 seed catalog 按数量分配；同一 seed 跨 scenario、规模和 episode 原子进入同一
   split。少于 3 个唯一 seed、任一 split 为空或 test 少于声明 unseen 数均失败关闭。
   manifest 固化逐 split seed/episode/frame 数、split hash 与 frame-file SHA256。
2. bundle 已升级到 `d3_learning_model_bundle_v2`，显式绑定 dataset/split policy v2。
   `manifest.json + state_dict.pt + SHA256` 继续包含 feature/policy、split hash、归一化、
   guardrail、结构、训练和 promotion。v1 dataset/bundle 不兼容并稳定拒绝；只允许
   weights-only load，其他缺失、损坏或合同不匹配均构造 rule fallback assistant。
3. 多 episode BC 已实现。训练先验证三个全局数值 seed 集合两两不交，再按 frame
   mini-batch 训练，不把 edge 随机拆到不同 split；同时
   学习规则选边、规则 residual teacher 和低频 hold/replan，输出 train/validation loss
   及 whole-seed accuracy。
4. 原生 PyTorch clipped PPO 已实现。共享边 actor 支持变长 `E`，value 使用 masked
   pooled context；动作仅为 bounded residual 和低频建议。counterfactual rollout 必须
   先经 deterministic mask/Hungarian demand-slot solver，再用高威胁覆盖、规则成本、
   unmet slot、churn、计划过期和安全拒绝形成 reward。PPO 不输出 assignment。
5. paired shadow evaluator 和 CLI 已实现。unseen 与 whole-seed 指标按数值 seed 跨
   scenario 聚合，报告同 seed 的 rule/proposal 成本、高威胁
   unmet、churn、duplicate/hard violation、P50/P95 与 fallback。promotion 必须使用
   test split、至少 20 个未见 seed、零 fallback，并同时满足安全和成本非退化。
6. 默认 planner 不变。`learning_assistant=None` 仍是构造默认；shadow/assist 都需显式
   注入。bundle assist loader 只有通过完整 promotion manifest 才返回可用 assistant。
7. writer 流式边界已下沉到 D3 API：`iter_learning_frame_records()` 逐行解析 staging，
   `write_learning_dataset()` 通过临时 SQLite 和可配置批次完成确定性排序、split finalize、
   split hash 与完整 frame SHA，不再把全量 record 保存在 D3 进程内存。

### 2026-07-20 合成 smoke

原 30-seed、60-frame smoke 的 `23/1/6` split、BC/PPO 数值和 shadow 时延由 v1
scenario/seed policy 生成，现仅作为历史开发记录。v2 loader/bundle 不接受这些产物，
本次未重训或生成新的模型性能数据，不据此声明 v2 模型 loss、成本或时延表现。

本地阶段耗时样本为数据生成 `0.375 s`、BC `0.920 s`、PPO `0.132 s`、12-frame
shadow `0.006 s`。这些是单机 smoke，不是吞吐、实时、收益或系统验收。专项测试另用
人为偏移 old log probability 覆盖 PPO clipped-ratio 分支；smoke 的实际 clip fraction
为 0，不据此声明策略收敛。

### 仍开放的真实数据与准入条件

1. main 提供 truth-isolated 的真实 D2/D3 sequential frames，并给出稳定
   `scenario_version`、seed、episode 和 frame 时钟；不得把 AirSim actor/truth ID 写入
   online feature 或训练记录。
2. 至少 20 个从未参与 normalization、BC、PPO 或 threshold 调整的 test 数值 seed；
   train、validation、test 数值 seed 集合必须两两不相交，同一值在任何 scenario/scale
   都沿用同一 split，split hash 和 policy version 随 bundle 固化。
3. 在目标新增/消失、3v5、5v3、资源失效、M-to-N demand 变化和 stale/timeout/OOD
   故障注入下完成 paired shadow；duplicate、hard violation、未授权执行和 stale 接受
   必须为 0，高威胁 unmet 与 assignment cost 不退化。
4. 标定 CPU/GPU inference P50/P95/P99、confidence、OOD 和 deadline，并实现或证明
   可抢占 timeout；当前仍是同步返回后的 deadline 拒绝。
5. 只有上述证据写入 promotion manifest 后才允许 assist。任何正式权重、长期训练、
   AirSim runtime 接线和 D6 系统报告均不属于本次 synthetic smoke。

当前 v2 验证门限为 D3 全量零失败、逆序输入同 hash/同文件、三 split 数值 seed 零交集、
少于 3 个唯一 seed 或声明 unseen 不足失败、dataset/bundle v1 和篡改稳定拒绝。全量共
收集 244 项，结果为 `243 passed, 1 skipped`；唯一 skip 是 optional OR-Tools。

200v200 fixture 的单帧 canonical JSON 为 5,854,691 bytes，NumPy payload 加 edge tuple
浅层约 5,161,640 bytes。D3 writer 的全量内存缺口已关闭。当时 main 尚未采用 iterator；
当前 scalable finalize 已直接传入 `iter_learning_frame_records()`，该调用侧 P1 已关闭。
正式 900-episode 最坏容量仍由 main 的 clean-tree gate 验收。

## 23. 单帧规划证据与真实 Episode Recorder 接口（2026-07-20）

### 已完成

1. `AssignmentPlanner` 公开最近一帧 `latest_planning_evidence`，不保留历史列表。regular、
   incremental 和 D4 裁决后的 regional path 均在调用开始时清除旧 payload，成功后才
   发布当前输入快照；失败保留 unavailable reason。
2. 成本链拆分为精确 `C_rule` 和 solver 实际消费的 `C_effective`。shadow proposal、
   assist effective、rule fallback 和无 learning 的 rule-only 状态使用不同字段/枚举，
   不从 plan metadata 反推矩阵。
3. 快照内 target/resource/assignment ID 全部 ordinal 化，metadata 与 node/actor/object/
   truth alias 被剥离；矩阵使用独立不可写 buffer，mapping 使用只读视图。证据不进入
   `AssignmentPlan` 或在线消息合同。
4. `build_latest_learning_frame_record(...)` 只要求 main 提供
   `scenario_version/seed/episode/frame_index`，直接复用当前证据生成既有
   `LearningFrameRecord`。synthetic dataset generator 已改用该公开 helper，不再调用
   planner 私有矩阵构造函数。
5. held、unchanged、forced replan ack 和有效 regional authority 可形成一致帧；stale、
   invalid authority、authority-generation fence、unmatched external publish 或快照一致性
   失败显式 unavailable，禁止返回上一帧。

### 验证与下一步

2026-07-20 新增 11 个专项测试，样本覆盖 1x3、3x2、7x4 roster 及 regular/regional、
shadow/assist/fallback。全量收集 226 项，结果 `225 passed, 1 skipped`，接受门限为零
失败；唯一 skip 为 optional OR-Tools。默认 Hungarian、需求槽、迟滞、版本和 stale
行为由既有全量回归保护。

下一步由 main 在 `IntegratedScalableModuleStack` 每个真实 planning tick 后调用公开
helper，按完整 scenario/seed/episode 保存 `unassigned` 连续 frame，在完整数值 seed
catalog 结束后用 D3 iterator 一次 finalize，并由 D6 检查帧数、split/frame hash、
缺帧/不可用 reason 和 truth-isolation。D3 本轮没有修改 main/runtime，也没有生成真实
AirSim seed；真实数据训练、>=20 未见 seed、paired shadow 非退化和 assist promotion
继续开放。

## 24. D4 区域资源建议到 D3 候选图合同（2026-07-20）

### 已完成的 D3-owned 能力

1. 新增冻结、版本化的 `RegionalPlanningHint`、`RegionalPlanningConstraint` 和
   `RegionalTransferAllowance`，公共 schema 为 `d3_regional_planning_hint_v1`。严格
   mapping 工厂不依赖 D4 包，并拒绝未知字段及 truth/actor/object/target/resource ID。
2. `AssignmentPlanner.plan(..., regional_planning_hint=...)` 只接受精确引用
   `previous_plan.plan_id/version`、未过期且已 projected 的提示。逐区域 source、owner、
   epoch、lease、当前区域集合、quota 守恒和 transfer 净额均显式验证。
3. 前一计划 assignment 和 coalition 成员全部计入 committed protection；源区按
   post-quota 的 `ceil(reserve_ratio * resource_count)` 保护 reserve。许可资源不足、
   hold 区域被 transfer、或候选物理/反馈边不足均给稳定 reason，并重跑无提示规则规划。
4. 合法提示在 learning assistant 前约束 candidate mask。同区候选保留原规则结果；每条
   跨区 route 预选固定大小、互斥且未承诺的资源池，Hungarian 资源唯一性保证实际使用数
   不超过 allowance。M-to-N demand slot、D5 hard feedback、学习 residual、迟滞和版本
   发布继续复用既有实现。
5. plan metadata 输出 hint available/considered/applied/rejected、advisory/source identity、
   projected、fallback/rejection reason、hold/request-replan region、route allowed/actual 和
   actual cross-region resource count。非法提示不会静默折算为零建议。

### 验证与剩余集成

验证日期为 2026-07-20。新增 14 个模块 fixture case，覆盖无提示等价、1-to-1、M-to-N、
8 类拒绝回退、commit/reserve、D5 hard edge 和 learning assist；seed 不适用。全量收集
240 项，结果为 `239 passed, 1 skipped`，门限为零失败，skip 是 optional OR-Tools。

该状态是 D3 模块合同已实现并测试，不是 D4-main-D3 运行闭环或多 seed 性能结论。后续：

1. main 将上一轮 D4 `RegionResourceRecommendation` 的 projected actions/transfers 映射
   为 D3 DTO，同时明确生成 `expires_at_s` 和 advisory version；禁止透传 D4 控制对象。
2. main 保证调用顺序为 D3 plan N -> D4 advice N -> D3 plan N+1，并使用同一 episode
   单调时钟；stale source、过期 lease 和 reset 后旧 advisory 必须被审计拒绝。
3. D6 统计 considered/applied/rejected、reason、allowed/actual transfer、跨区资源数、
   unmet demand、churn 和求解时延，并在动态 N/M 的正式多 seed/AirSim 批次做非退化比较。
4. `plan_regional_authority()` 继续承担 D4 已裁决 owner/成员的执行计划物化；新 hint 入口
   不选择 owner、不授权 D7，也不替代 D4 failover/coalition commit。

## 25. Learning 数据、训练与 Promotion 安全补正（2026-07-20）

### 已完成

1. 训练入口按用途收窄 split：BC 仅使用 train/validation，PPO 仅使用 train；test frame
   进入任一训练 API 都报错。完整 dataset loader 仍校验三分、canonical 内容和摘要，但
   test 不进入 normalization、梯度更新或训练期 whole-seed metric，只能由独立
   shadow/evaluation 入口使用。
2. frame v2 改为严格字段集合并在构造前递归检查未知嵌套内容；truth、actor、identity、
   `*_id`/`*_ids`、UUID 和 vehicle-name 类字段失败关闭。兼容范围只包括已声明匿名
   ordinal、强类型数值/布尔字段和 hard-reject 语义计数，新增普通字段必须升级 schema。
3. `CostMatrixResult.candidate_edge_indices`、assistant 返回值和最终 solver mask 都把
   candidate hint 与 hard reject reasons 求交；mask/reason shape 不一致拒绝。学习残差
   不能重新开放物理、D5、容量或冲突禁边。
4. bundle/promotion 证据链同时绑定 split SHA、完整 dataset frame SHA 和 model-state
   SHA。assist 必须使用 eligible 的正式 test paired shadow，证据 schema/kind、
   `rule_cost_matrix_v1` 口径、三摘要、至少 20 未见 seed、零 fallback、安全与成本非退化
   全部匹配；promotion bypass、类型伪装和摘要错配均失败关闭。
5. shadow 对 rule/proposal 分别求解后，使用同一原始 `C_rule` 和 unassigned costs 重算
   两个 assignment 的最终 objective。proposal 矩阵只影响候选选边，不能用不同矩阵的
   solver objective 直接宣称非退化，也不能直接形成执行授权。

### 验证与开放项

2026-07-20 D3 全量收集 252 项，结果 `251 passed, 1 skipped`；接受门限零失败达到，
唯一 skip 是 optional OR-Tools installed-only benchmark。负例覆盖上述五项合同及
validation/non-eligible/bypass/hash/type mismatch。

本项只把 software safety/data contract 从部分闭合更新为 D3-owned implemented/tested。
仍无正式权重、真实 D2/D3 训练集、至少 20 个未见真实/高保真 test seed、正式 assist
promotion、可抢占 timeout、AirSim 模型收益或 200v200 全栈学习性能结论。后续证据必须
由 main 的 truth-isolated recorder 与独立 test shadow 批次产生，学习输出继续不得被
下游解释为授权。

## 26. 学习帧构造与数据集收口性能（2026-07-20）

### 已完成

1. `build_candidate_edge_batch()` 将 `effective_demand` 从每条候选边重复构造改为每个目标
   构造一次；frame builder 复用 demand 和 action-mask reject count，不改变任何特征值。
2. `LearningFrameRecord` 增加 compact canonical JSONL 编解码入口。identity 扫描采用迭代
   容器遍历，递归真值字段拒绝范围和 v2 完整字段 allow-list 保持不变。
3. dataset writer 在写盘前重新运行 dataclass 结构校验，构造后篡改 NumPy mask 或匿名
   mapping 仍失败关闭。SQLite 只保存排序键和 payload offset/size；单次编码 payload
   使用临时 JSONL sidecar，排序输出时不再完整解码和重建对象。
4. split 只在 writer 自己生成的 canonical 顶层占位符上替换。确定性测试证明最终字节与
   `replace(record, split=...).to_dict()` 旧语义完全一致，schema、字段、排序、frame SHA、
   split hash 和 manifest 不变。
5. 新增无墙钟阈值的 CLI 微基准和测试。200×200、top-32、6 帧结果为 frame build
   `48.19 -> 22.99 ms`，JSON decode/validate `95.92 -> 56.09 ms`，finalize
   `910.20 -> 243.65 ms`；匹配 cProfile/Tracemalloc 峰值下降 12.69%。

### 下一步与边界

- 当前 main 已逐行调用 `iter_learning_frame_records()`；D3 调用侧全量 materialization
  缺口不再开放。clean-tree 复测也已写出 D3、D4、D5 分项计时，D3 stage 为
  0.0917/0.1129/0.0999 s。D3-owned 重复编码/最终化及跨模块归因缺口均已关闭。
- top-32 canonical 帧约 2.20 MB，九场景 D3 数据约 27.86 MB。无 schema/content 变化条件
  下不删除 dense rule matrix、mask 或候选特征；正式 900-episode 容量由 main gate 决定。
- 标准库 `tolist()` 与 `json.dumps()` 已成为剩余主要 CPU 路径。后续若研究更快编码器，
  必须作为可选 adapter 做逐字节或逐字段兼容验证，不在当前默认依赖中加入。
- 正式 D2/D3 数据、模型训练、至少 20 个未见 seed、shadow 非退化和 assist promotion
  仍为原 P1，不因导出提速而关闭。

本批 D3 全量收集 255 项，结果 `254 passed, 1 skipped`；唯一 skip 为 optional
OR-Tools，零失败满足门限。

## 27. Clean-tree 200v200 复测状态（2026-07-20）

### 已完成

1. main 使用 nominal 200v200、seed 930/931/932、每 seed 2 s，在干净工作树复跑三
   episode。优化后 producer commit 为
   `4052d9411363c39d52100c0e3a4f60ee88443cab`，manifest 记录
   `repository_dirty=false`。
2. 基线到优化后，总耗时为 `467.8007 -> 262.2866 s`，artifact stage 为
   `225.9243 -> 126.4682 s`，联合 finalization 为 `116.5624 -> 7.7377 s`，episode run
   为 `125.2205 -> 127.9871 s`。
3. D3 分项 stage 为 `0.0917/0.1129/0.0999 s`。6 帧数据正常最终化，三个 split 各 2 帧，
   `online_truth_use_count=0`。这组结果证明 D3 导出优化进入 main 真实三维质点生成链路，
   不再只依赖模块微基准。

### 下一步

- 联合 finalization 同时收口 D3、D4、D5，7.7377 s 的改善不能全部计入 D3。
- 不再继续改 D3 默认 JSON schema 或 Hungarian 主线来追逐联合阶段耗时。标准库
  `tolist/json.dumps` 只保留为 P2 optional adapter 研究项。
- 本节形成时，900 episode schedule 与模型训练尚未完成；其后正式数据生成和 BC 开发
  训练已由第 28 节补齐。PPO、外部保留 seed 1000-1019 配对验收和 assist promotion
  继续作为开放项。

## 28. 正式 BC 开发训练状态（2026-07-20）

### 已完成

1. 只读加载并复核正式 900 episode D3 数据。1604 帧按 100 个数值 seed 原子切分为
   962/320/322 帧，5/20/50/100/200 五档均有覆盖。frames SHA、split hash、episode/seed
   原子性和 manifest 统计全部重算通过；外部保留 seed 1000-1019 未进入当前数据。
2. 使用既有共享候选边网络完成行为克隆开发训练。固定 seed `20260720`，12 epoch，
   hidden size 64，Adam 0.001，mini-batch 8；对约 3.2% 的正边使用最大 16 倍权重。模型只
   学习有界代价 residual，不替换 Hungarian，也不修改需求槽、版本、迟滞、硬门控和 D7
   binding。
3. 新增 train/validation/internal-test 开发 evaluator，报告残差损失、边排序、计划一致、
   共同规则成本差、需求满足、重复/硬违规、churn、fallback 及 5 档时延。internal-test
   排序一致性 0.8031，计划完全一致 0.6770，成本差 +0.022345，重复和硬违规为 0。
4. bundle 升级为 v3 provenance/admission 合同。开发权重明确 `shadow-only`，外部保留
   seed 状态为 `not_evaluated`；assist loader 在 promotion 检查前先拒绝开发 bundle。
   Git 字段标明基线提交角色，未提交 D3 训练源码另由 SHA256 精确绑定。
5. 权重迁入模块 ignored `outputs/`。tracked `results/` 只保留数据审计、训练配置与命令、
   指标、模型定位和 SHA256。当前环境无 Git LFS，不把 `.pt` 放入普通提交。
6. D3 全量回归收集 258 项，结果 `257 passed, 1 skipped`；唯一 skip 为 optional
   OR-Tools installed-only case。语法检查通过。

### 下一步

1. main 冻结本地权重 SHA256
   `e3da9fd5b54451da83358405b6051991e0c78bcf9f538b350d459b05faf8e0b2`，在 seed
   1000-1019 上运行独立 R0/BC-shadow 配对验收。内部 test 结果不得复用为最终准入。
2. D6 对每个保留 seed 汇总共同规则成本、需求满足、high-threat unmet、duplicate、hard
   violation、churn、fallback 和分档 P50/P95/P99。当前 internal-test 有 163/322 OOD
   回退，必须先定位“任一边超阈值”的帧级 OOD 规则是否过于保守。
3. 只有外部保留集达到零安全退化、成本非退化、时延预算和已批准 fallback 门限，才允许
   生成 qualified admission。当前轻微成本退化已使 assist 保持关闭。
4. PPO 不在本阶段启动。现有 rule demonstration/reward components 尚不能替代可验证的
   在线或反事实回报，后续需由 D6 明确 reward availability 与因果口径后另行评审。
5. 长期保留权重使用 Git LFS 或独立制品存储。main 需在全局 `VERSIONING.md` 中记录本机
   `git-lfs` 不可用状态；D3 不跨模块修改该文件。

## 29. C1 共享 Seed 切分绑定（2026-07-21）

### 已完成

1. 增加 `d3_shared_seed_split_binding_v1` 只读验证器。验证器固定接受
   `scalable3d-shared-seed-split-registry-v1` 和
   `scalable3d-numeric-seed-atomic-split-v1`，并要求 ordering compatibility 为
   `d3_numeric_seed_atomic_split_v2`。
2. 同时验证 registry 文件 SHA、去除自哈希字段后的 content SHA、assignment SHA 和
   source training registry 文件 SHA。source schema、Git 提交、工作树状态和 schedule
   SHA 必须与 detached registry 的 provenance 相同。
3. 以 source registry 为全集，核对 dataset manifest 和全部 records 的 seed 完整覆盖、
   60/20/20 映射、逐数值 seed 原子性及 1000-1019 排除。映射还必须由 D3 v2 算法使用
   registry 参数独立重算得到。
4. `load_learning_dataset()` 新增成对可选参数。默认不启用共享验证，保留旧开发数据和旧
   bundle 兼容；启用时任何差异失败关闭。验证过程不写 dataset、manifest、registry 或
   bundle。
5. 通用 BC/PPO/shadow CLI 和正式 BC 入口接入同一验证器。启用共享 registry 后，新 bundle
   将 binding 写入 `training_results`；正式报告另写 sidecar 并纳入 artifact hash。PPO
   入口只获得验证能力，本任务没有启动 PPO。
6. 正式 900 episode/1604 frame/100-seed 数据验证通过，文件前后 SHA 相同。D3 全量回归
   `269 passed, 1 skipped`，skip 仍为 optional OR-Tools。

### 开放条件

1. D3 的 split ambiguity 已关闭，但 C1 联合训练仍需 main 让 D4、D5 使用同一 registry，
   并冻结跨模块样本 join、label availability 和 sidecar provenance。
2. 当前 BC bundle 保持 `development/shadow-only`。共享映射一致不等于模型非退化，也不
   允许 assist；外部 seed 1000-1019 仍需独立验收。
3. D4/D5 的动作多样性、奖励/运行时确认和图候选负样本不足未由 D3 解决。条件闭合前不
   启动 C1 或 PPO，也不修改 Hungarian、代价残差公式、安全外壳、计划版本和 D7 binding。

## 30. 正式分配数据全样本准入审计（2026-07-21）

### 已完成

1. 对正式 900-episode D3 数据建立独立流式审计入口。输入绑定
   `dataset_manifest.json`、`frames.jsonl`、训练 seed 注册表、共享切分注册表、生成摘要、
   episode 进度和批量导出摘要。7 个源文件均有冻结 SHA256，审计前后再次复算；输出
   写入 D3 自有 `results/` 和 `reports/`，禁止写回正式数据根目录。
2. 逐行解析 883 MiB 帧文件，不把 1604 帧物化成完整 tuple。每帧重新执行 v2 字段白名单、
   匿名实体和有限数值检查，并复核候选边、动作标签、成本矩阵、动作索引、资源容量、
   目标需求槽、seed/episode 原子切分、规范排序、连续帧号、时间递增和前序版本不回退。
3. 计数口径分层保存。规范 episode 身份按 100 个数值 seed 为 60/20/20；900 个实际场景
   episode 为 540/180/180；1604 个决策帧为 962/320/322。候选边和动作标签均为
   3658815，规则选中动作 117304。任何报告不得把 seed、episode、frame 或 edge 比例混写。
4. episode 进度与帧集合逐项绑定。900 个 episode 全部为有限状态，脏 episode 和在线
   truth 使用均为 0。194 个未导出帧原因保留为权威代次围栏或计划-成本帧不匹配，禁止
   使用旧帧填充。
5. 正式审计为 0 违规，数据结构状态 `complete`。专项 10 项和 D3 全量 280 项通过，结果
   为 `279 passed, 1 skipped`；skip 仅可选 OR-Tools。

### 保持关闭的条件

1. 数据只携带匿名 token 和 `previous_plan_version`。当前计划 owner、当前 plan version、
   运行时 stale 接受/拒绝不在 schema 中，状态为 `unavailable`，不能从帧序号推断。
2. `reward_components` 只用于规则教师诊断。真实 applied ACK、outcome 归因、因果或反事实
   reward、同 seed 规则/学习 shadow 非退化均未闭合。
3. 总体准入保持 `partial`。本项不训练 BC 或 PPO，不生成 `.pt`，不开放 assist/authority，
   不改变规则代价、需求槽匈牙利、迟滞、计划发布或 D7 binding。
4. 下一步由 main 将本审计 JSON 及文件 SHA 交给 D6 复核。未来 producer 需另外生成运行时
   owner/version/applied-ACK/outcome 记录和同 seed paired shadow；这些记录不得回填到本批
   已冻结的正式数据。

## 31. 运行计划 ACK 只读验证（2026-07-21）

### 已完成

1. 新增 D3-owned `d3_assignment_plan_runtime_ack_evidence_v1` 消费合同。输入为 main
   ACK schema、ACK mapping、D3 来源 envelope、可选 D7 来源 envelope 和预期
   `AssignmentPlan`；实现不依赖 main 包。
2. 规范哈希算法与 main 对齐：UTF-8、`sort_keys=true`、紧凑分隔符、
   `allow_nan=false`。来源 sequence 必须为正整数，D7 sequence 必须位于同 tick 的
   D3 sequence 之后。
3. 精确验证 plan id/version/schema、decision id、计划创建和确认时间、计数、solver、
   metadata、assignment inventory、未分配清单、资源/中心航迹 binding、
   coalition/version/role 和区域 owner 字段。
4. 根据 D7 来源命令独立计算 command-present、fully-bound、control-applied 和 held。
   重复、缺失、额外绑定，旧版本，来源哈希/序号错误，非有限时间和
   `global_track_id` 不一致均使用稳定 reason/code 失败关闭。
5. 学习证据缺字段保持 unavailable。只有 assist、applied 和 bundle-loaded 三条件同时
   明确为真，且整个来源链验证通过，才形成 runtime learning applied ACK。shadow、规则
   教师诊断或 accepted plan 均不形成该证据。
6. 物理 outcome 和 reward 在 v1 ACK 中必须为 false。D6 profile-bound availability
   sidecar 已独立存在，但不是该 ACK 接口的输入，因此任何自报 true 都被拒绝。返回值为
   frozen dataclass 和 tuple，只支持新建
   序列化对象，不修改或重新发布 `AssignmentPlan`。

### 验证

- 专项测试 24 项，覆盖正常路径，以及 schema、D3/D7 hash、旧版本、非正序号、重复、
  缺失、额外、中心航迹重绑、统计错误、非有限时间、自报 outcome/reward、shadow
  冒充 applied、两种合法 D3 包导入身份组合和非约束鸭子类型拒绝。
- 自动化真实 main 集成测试运行三维集成栈 3v3、seed 7、1.2 秒并产生 2 条 ACK；公开
  consumer 验证最后一条 ACK，最终 3 条 binding 全部进入 D7，control-applied=3、
  held=0、online truth use=0。consumer 源码不导入 main，main 仅由 D3 测试导入。
  学习、物理 outcome 和 reward 均保持 unavailable。
- D3 全量 304 项，结果 `303 passed, 1 skipped`；接受门限为零失败，skip 仅 optional
  OR-Tools。

### 保持关闭的条件

1. 冻结的正式 900 episode 不含新 ACK，不能把当前 3v3 自动化集成测试回填或外推为
   正式逐样本 applied evidence。
2. D6 已实现同帧离线分配比较的 profile-bound 消费；仍需按 source sequence/hash、plan
   id/version 和时间窗连接 runtime ACK 与干预后物理 outcome/reward。D3 验证器只证明
   来源与绑定一致。
3. 同 seed paired shadow、可归因 reward、外部保留 seed 和 promotion gate 未闭合。
   PPO、assist、authority 保持 false；默认规划和安全外壳不变。

## 已采用计划窗口归因计划更新（2026-07-21）

### 本轮完成

1. 增加版本化 `d3_runtime_plan_window_reward_evidence_v1`。适配器只接受已通过 D3
   `runtime_plan_ack` 验证的不可变 ACK，并用调用方提供的 SHA-256 校验完整 D6 v1 结果。
2. 将来源计划发布、D7 同 tick 消费、main ACK、D6 观测窗口拆成独立层。输出绑定
   source/consumption/ACK sequence、plan id/version、owner、resource-target binding、
   occurrence、执行签名、时间窗和全部来源摘要。
3. 对整个 D6 窗口集合复核不重叠、ACK 顺序、计划版本单调、同 identity 刷新序号连续、
   刷新类型和执行签名一致。缺字段、旧版本、错误刷新、窗口重叠和在线真值使用失败关闭。
4. 固定原始分项可用性清单：`high_threat_coverage`、`rule_total_cost`、
   `unmet_demand_slots`、`reassignment_churn`、`plan_expired`、`safety_rejections`。当前
   D6 binding-window 证据不足以给出这些计划级运行分项，因此每项使用 null value 和明确
   reason，不用 0 代替缺失。
5. 将五米接近和有界最优距离进展保留为 `observed_outcome`，同时强制
   `formal_reward_eligible=false`。paired、counterfactual、causal 和 formal reward 当前
   均 unavailable。
6. 真实 main 3v3、seed 41、1.2 秒集成样本验证 producer、D6 join 和 D3 consumer 可以
   对接，且在线真值使用为 0。consumer 验证全部 ACK 与各自发布时计划快照，按总线顺序
   选择首个非保持 ACK 的 binding 建立 D6 窗口。当前末条 ACK 因
   `global_track_stale` 全部保持，保留为安全证据，不进入 `ack_applied` 取样。专项 16 项和
   历史 D3 全量 320 项通过零失败门限；2026-07-22 当前全量 439 项结果为
   `438 passed, 1 skipped, 0 failed`。

### 后续证据

1. main/D6 需产生同场景、同 seed、同初始状态和同传感器随机数的规则/候选配对运行，
   明确 intervention、factual/counterfactual 计划和完整 outcome hash。
2. D6 需补充计划级需求满足、抖动、过期和安全结果的版本化 sidecar。单 binding 距离变化
   和同 episode 五米事件不能替代这些分项。
3. 只有 paired、counterfactual、causal、外部保留 seed 和非退化门全部可用后，才讨论
   正式标量 reward 与 PPO。当前保持 `PPO=false`、`assist=false`、`authority=false`、
   `rule_fallback=true`。
4. 冻结 900-episode 数据生成于 ACK producer 之前，保持原样；新证据必须来自新 episode，
   不得回填旧数据。

## 32. 保留 Seed 配对干预合同（2026-07-21）

### 已完成

1. 冻结 `d3.paired-intervention-specification.v1` 和
   `d3.paired-intervention-manifest.v1`。seed 目录严格为 `1000-1019`；每个 seed 只有一组
   control/treatment，缺失、重复或额外 seed 均失败关闭。
2. 每条 arm 显式绑定 scenario version、scenario config SHA、initial world state SHA、
   observation/input snapshot SHA、D1/D2 lineage、规则代价配置、D3 bundle、阈值、安全
   外壳和 source/current plan version。配对字段不等价时不允许生成有效 manifest。
3. control 固定为规则代价加 Hungarian。treatment 仅标记为离线仿真干预，不改变在线
   assist/authority 状态；执行收据必须证明现有动作掩码、可达性、容量、版本、迟滞和安全
   门均被执行，并保留规则回退。
4. 复用现有 paired evaluator schema、runtime ACK evidence schema 和 runtime reward
   evidence schema。ACK 引用只能从已验证的不可变 ACK 对象建立；D3 不在该合同内读取
   truth、计算 observed-window reward 或接管 D6 sidecar。
5. 可用性分层为 paired input equivalence、isolated treatment applied、runtime ACK、
   outcome、counterfactual 和 causal。没有执行收据或 D6 sidecar 时对应层保持
   unavailable，不补零、不推断。
6. 增加严格 JSON round-trip CLI 和失败关闭单元测试。本阶段没有运行 PPO，没有执行
   正式 20-seed 配对 episode，也没有改动冻结的 900-episode 数据。2026-07-21 专项
   `36 passed`，D3 全量 `355 passed, 1 skipped`，唯一 skip 为可选 OR-Tools。

### 后续接口

1. main 负责按 specification 建立两套隔离世界、冻结输入快照并产生完整执行收据和运行
   ACK。该工作不属于本轮 D3 收敛任务。
2. D6 负责按 pair/seed/arm 和全部 SHA 连接 outcome sidecar，计算结果差、反事实和因果
   统计。D3 manifest 本身不能将这些层改为 available。
3. 在真实 20-seed 结果和 D6 非退化判定完成前，继续保持 `PPO=false`、
   `assist=false`、`authority=false`、`rule_fallback=true`。

## 36. 保留 Seed 配对干预执行入口（2026-07-21）

### 已完成

1. 新增 typed API `execute_offline_paired_intervention(...)`。输入固定为完整配对规范、
   seed `1000-1019` 的 20 个 `PlanningFrameEvidence`、冻结 bundle 目录和 D3 planner
   配置；输出包含 40 个隔离 plan、40 份真实执行收据、共享配对报告和可直接序列化的
   `PairedInterventionManifest`。
2. control/treatment 从同一匿名输入快照复放。执行器复算输入、规则矩阵和动作掩码哈希，
   校验前序 plan id/version、干预时间和帧清单。control 复放结果必须与原规划帧的资源-
   目标 binding 一致，否则失败关闭。
3. 冻结 development bundle 先走生产 shadow loader，再由离线入口核对 manifest 文件
   SHA、state dict SHA、policy version、v3 development/shadow-only admission、
   1000-1019 holdout inventory 和有限权重。生产 assist 准入函数未改，绕过 promotion 的
   路径仍不存在。
4. treatment 的残差只作用于 `offline_simulation_intervention_arm`。动作仍由硬安全掩码
   和 Hungarian 决定；分布外输入、超时、低置信度、非有限值、模型异常或 bundle 不匹配
   时，treatment 使用原规则矩阵并在 receipt 中保存稳定回退原因。
5. 20 个 seed 聚合为一个 `d3_shadow_paired_evaluation_v2` 报告。40 份 receipt 共享报告
   SHA，输出同时固定 `PPO=false`、`online_assist=false`、`online_authority=false`、
   `runtime_publication_allowed=false` 和 `rule_fallback=true`。不生成 runtime ACK、物理
   outcome、反事实或因果字段。

### 验证

- 专项 7 项，使用临时冻结 v3 development bundle 和 20 个匿名保留-seed 规划帧，覆盖
  成功执行、manifest/version 失配、分布外输入、deadline、非有限权重和输入哈希篡改，
  结果 `7 passed`。
- D3 全量收集 363 项，结果 `362 passed, 1 skipped`；skip 仅可选 OR-Tools。
- 生产 `load_model_bundle(..., mode="assist")` 对同一 development bundle 继续返回
  `bundle_shadow_only`。

### 下一步

1. main 在 `scalable_3d_simulation` 为 seed 1000-1019 生成实际同源规划帧，并用本 API
   写出正式 40 臂执行产物。D3 不跨模块实现该调度。
2. D6 独立校验共享输入、收据、计划结果和 episode outcome，补充 non-degradation、
   counterfactual/causal availability；当前 D3 报告不得代替 D6 结果侧车。
3. 只有正式 20-seed 配对、运行时 applied ACK、成本和安全非退化、分布外/deadline 门限
   同时通过后，才讨论 qualified bundle。PPO、online assist 和 authority 继续关闭。

## 37. 保留 Seed 精确重放修复（2026-07-21）

### 已完成

1. 将 `forced_replan` 纳入 `PlanningFrameEvidence` 和输入快照哈希，中心规划与增量规划均在
   捕获帧时保存调用状态；区域授权路径保持默认 false，不引入不存在的重规划权限。
2. 匿名前序计划保留迟滞重放实际读取的窗口编号和累计变化数，并保留执行所有权、激活、
   人工授权、节点/链路及联盟执行语义。所有节点和前序独有目标/资源使用稳定匿名 token，
   不保留 truth、actor、object 或 mesh 身份。
3. 离线执行器依据记录计划恢复 planner 的人工作业状态和匿名链路端点。control 除比较
   资源-目标 binding 外，还严格比较执行签名、版本、窗口、决策状态、changed 和 N/M 规模；
   任一差异继续返回 `control_plan_replay_mismatch`。
4. 新增 20-seed 5v5 真实形态回归，覆盖 `held_by_hysteresis`、4→5 目标
   `replan_ack_no_change`、5→4 生命周期移除及篡改 binding 负例。专项 9 项通过，D3 全量
   `364 passed, 1 skipped`。
5. 使用 main 当前 nominal 5v5、duration 2.2、seed 1000-1019 源帧和冻结 development
   bundle 完成不写盘内存复验。20 个 control 均精确复现，状态分布为 15/3/2，40 个 arm
   完成，未产生在线权限或结果证据。

### 下一步

1. main 重新运行并写出完整 D3/D4 保留-seed 产物；D3 不修改 main runner 或输出目录。
2. D6 基于正式产物补充逐 seed 非退化、回退、分布外和时延统计。当前 D3 内存复验不能
   代替 D6 sidecar，也不能形成学习策略收益结论。
3. runtime ACK、物理 outcome、counterfactual 和 causal 继续保持 unavailable。冻结 bundle
   仍为 development/shadow-only；PPO、online assist、authority 不开放，规则回退保持启用。

## 38. 二元特征分布门修复（2026-07-21）

### 已完成

1. 将 `previous_binding` 固定为伯努利二元特征。有限 `0/1` 及 `1e-6` 容差内端点合法，
   不再进入连续特征对称 z 分数；`0.5`、越界和非有限值继续失败关闭。
2. 其余 11 个连续特征仍使用冻结 normalization 和 `ood_z_threshold=6.0`。未调整 bundle、
   权重、alpha、deadline、confidence、生产准入或规则回退。
3. 新增版本化、真值安全的分布评估结果，并以增量 metadata 记录触发特征、边偏移、最大
   连续 z 和原因。旧 `is_ood()` 返回类型和调用方式保持兼容。
4. 正式 bundle 与 nominal 5v5、2.2 秒、seed `1000-1019` 不写盘复验完成：20 个 treatment
   全部进入模型，applied=20、fallback=0，最大连续 z=`1.6229`，P95=`0.692 ms`，最大
   `0.899 ms`；重复、硬违规和高威胁未满足均为 0。
5. D3 全量 `372 passed, 1 skipped`。bundle manifest 和 state dict SHA256 分别保持
   `a9213d65...14c0` 与 `e3da9fd5...0b2`。

### 后续

1. main 需用修复后的代码重新生成正式落盘 D3/D4 产物；旧落盘文件仍记录 20 次错误 OOD，
   不得覆盖解释为修复后结果。
2. D6 需基于新产物完成逐 seed 成本、安全、回退和时延非退化复核。当前不写盘验证只证明
   D3 隔离推理入口可达。
3. runtime ACK、物理 outcome、counterfactual、causal 和生产晋级继续 unavailable。
   PPO、online assist、authority 保持 false，规则回退保持 true。

## 39. v2 正式保留 Seed 证据同步（2026-07-21）

### 已完成

1. main 已按第 38 节后续项生成 v2 正式产物，目录绑定源提交 `78912963...c460c`。D3 owner
   独立验证 `SHA256SUMS`、manifest 及清单内 5 个文件，未修改 main 输出。
2. 20 个 source episode 均 clean、finite，online truth use=0；20 control 和 20 treatment
   清单完整。D3 产物没有非有限数值。
3. 20/20 treatment 在隔离 arm 内 applied，fallback=0。20/20 有效代价矩阵发生变化，最终
   binding 变化为 0/20；规则与 treatment 的规则评分均值均为 `17.0560260319065`。
4. 高威胁未满足、duplicate、hard violation 和 churn 的 control/treatment 总数均为 0。
   推理时延 P50/P95 为 `0.246385/0.310801 ms`。
5. v2 证据关闭“修复后正式落盘产物缺失”和“隔离 treatment 是否实际应用未知”两项 P1
   缺口。它没有关闭运行采用、物理结果和因果归因缺口。

### 后续

1. D6 profile-bound v2 availability sidecar 已独立消费同帧规划结果；当前正式 artifact
   set 仍不含 runtime ACK、干预后 physical outcome 或 paired physical effect。
2. 如需讨论 production admission，必须另行获得运行确认、物理结果非退化、反事实和因果
   证据。
   当前 `PPO=false`、`assist=false`、`authority=false`、`rule_fallback=true` 不变。
3. 后续正式证据必须新建版本化目录并保留旧产物；不得回写本次 v2 文件或冻结 bundle。

## 40. D6 Profile-Bound v2 可用性同步（2026-07-22）

### 已完成

1. D6 已在提交 `d4e8562` 中生成独立 profile-bound v2 availability sidecar，目录为
   `research_modules/d6_evaluation_metrics/outputs/reserved_seed_interventions_nominal_5v5_1000_1019_formal_7891296_d6_profile_bound_v2_audit_20260722/`。
   sidecar 状态为 `pass_offline_assignment_comparison_only`，文件 SHA-256 为
   `f3852251daf02ec87fe878e7fb80aad6f381d8c0756a5c956a32e737a3871c3b`，规范内容 SHA-256
   为 `c02a345c46ddc642dea7fb6bfcfb24184e7dc2a9f35b754c90324d074b445d2d`。
2. D6 确认 20/20 isolated treatment applied、0 fallback、20/20 effective matrix changed、
   0/20 final binding changed。rule/treatment 同帧 assignment cost mean 均为
   `17.0560260319065`，high-threat unmet、duplicate、hard violation 和 churn 均为 0。
3. `same_frame_offline_assignment_comparison` 现为 available。这关闭 D3 assignment 层的
   可用性和独立消费 P1 缺口，但不构成策略有效性或物理非退化结论。

### 仍开放

1. 当前正式 artifact set 的 runtime ACK、post-intervention physical outcome、paired
   physical effect/non-degradation、counterfactual 和 causal 仍为 unavailable。
2. promotion 仍为 unavailable；`PPO=false`、`assist=false`、`authority=false`、
   `rule_fallback=true`。D3 不因 sidecar 可用而改变默认 Hungarian、在线准入或发布权限。

## 41. 隔离计划消费合同（2026-07-22）

### 已完成

1. 新增 `d3.isolated-plan-consumption-evidence.v1` 和版本化 source lineage。证据绑定
   experiment/version、pair/seed/arm/isolation、场景与初始世界摘要、匿名观测输入摘要、
   D1/D2 lineage、执行 receipt、plan id/version/schema/payload SHA，以及消费周期和时刻。
2. 计划载荷摘要复用 runtime ACK 的计划结构验证：资源和目标清单、重复 binding、计划
   schema、规模和 metadata 先通过同一 fail-closed 检查，再计算规范 SHA-256。该复用只
   共享安全检查，不生成 runtime ACK。
3. 构造器要求计划带 `isolated_simulation=true`、`runtime_execution_allowed=false`，且
   PPO、online assist、online authority 均为 false。accepted consumption 必须覆盖全部
   assignment binding；不完整计数直接拒绝。
4. `IsolatedPlanConsumptionValidator` 维护每个 experiment/seed/arm/isolation 的消费账本。
   重复计划、旧 plan version、相同版本二次消费、周期回退和时间回退均失败关闭。错 arm、
   source snapshot、receipt、plan identity 或 payload SHA 也不会进入账本。
5. 输出采用独立状态 `accepted_by_isolated_simulation_consumer`，并固定
   `production_runtime_ack=false`、`control_applied_to_production_world=false`、
   `physical_outcome_available=false`、`reward_available=false`、
   `causal_evidence_available=false`。离线 receipt 不会被提升为生产 ACK。
6. 2026-07-22 新增 8 项专项，覆盖正常 JSON 往返、payload 篡改、重复、错 arm、错版本、
   版本回退、source snapshot 篡改和生产 ACK 越权声明；专项全部通过。D3 全量结果为
   `380 passed, 1 skipped`，skip 仅为可选 OR-Tools。

### main 后续接线

1. main 为 control/treatment 分别创建独立世界和独立 validator，在一次性计划消费确认
   通过后，才允许该 arm 进入后续多周期质点推进。两个 arm 不能共享可变状态或消费账本。
2. main 需另行记录 D7 命令 lineage、隔离世界执行确认和干预后状态窗口。隔离消费证据
   不能命名为 production runtime ACK，也不能直接填充 physical outcome 或 reward。
3. D6 只有在 source lineage、消费确认、命令 lineage 和完整结果窗口均可验证时，才可
   计算 availability-aware paired physical effect。counterfactual、causal 和 promotion
   在证据不足时继续 unavailable。
4. 需增加能改变最终 binding 的边界场景，并分别运行正常中心与 D4 degraded 场景。当前
   nominal 5v5 的 0/20 binding change 不足以评估多周期策略效果。

## 42. 离线计划库存规范化（2026-07-21）

### 已完成

1. 离线 arm 在计划编号和 receipt 哈希生成前，以当前匿名目标快照作为唯一 roster，补齐
   迟滞保持期间未进入旧执行计划的新目标。
2. 无绑定目标标为未分配且不完整；部分 M-to-N 需求只标为不完整。需求摘要按当前
   `TargetDemand` 与实际 binding 数重建，目标只按唯一编号计数。
3. previous-only 诊断项从当前库存移除；previous-only 可执行 binding、目标计数不符、联盟
   需求不符和摘要不符均失败关闭。
4. 离线执行器在生成 receipt 时直接调用严格计划载荷校验。生产 runtime ACK 校验规则和
   API 未改，离线消费仍不产生线上 ACK、物理结果或奖励。
5. 缺失 bundle 的 20 seed、40 arm 扫描通过；`seed=1011/1019` 的第五个目标均显式进入
   未分配和不完整清单。D3 全量为 `382 passed, 1 skipped`。

### 仍开放

main 的多周期隔离世界推进、D7 命令 lineage 和 D6 物理结果连接仍按第 41 节执行。本项只
关闭 offline plan-consumption 兼容阻塞，不改变生产准入或控制权限。生产 planner 的保持
计划若包含仅供审计的新候选目标，仍由严格 runtime ACK 失败关闭；在线 roster 语义需另行
形成版本化合同后再修改。

## 43. 在线故障代际目标库存（2026-07-22）

### 已完成

1. 中心、增量和区域授权规划在身份最终化前，统一以当前 `TargetTrack` 集合规范化
   `target_count`、未分配清单、不完整清单和需求摘要。
2. 迟滞保持只保留合法执行绑定。新增目标进入当前库存时，计划严格升版并生成新计划编号；
   不再以旧计划身份携带新的 `target_count`。
3. `advance_authority_generation()` 复用与当前已发布计划匹配的最近规划上下文，在故障 fence
   前补齐新增目标，再执行严格载荷校验和发布。previous-only 执行绑定仍直接拒绝。
4. 不完整 M-to-N 联盟区分候选成员数和可执行绑定数。候选成员用于需求摘要和 shortfall；
   可执行绑定保持为 0，目标同时标记为未分配和不完整。完整联盟仍要求两类计数一致。
5. 匹配成本帧的二级 owner 身份转换可重建 planning evidence；绑定、成本、联盟或库存任一
   变化时不允许重绑定证据。

### 验收

定向 5 项通过。D3 全量共 386 项，结果为 `385 passed, 1 skipped`，skip 为可选 OR-Tools。
只读运行 `center_failure`、5v5、3.2 秒、seed 1011/1019，两组均形成二级 v3 计划和 2 个
故障后可用规划帧。最终均为 4 个保留绑定、1 个未分配且不完整目标、5 条需求摘要，严格
载荷摘要通过，在线真值使用为 0。

### 后续

当前闭合的是 D3 目标库存和规划证据合同。若故障 fence 前没有与已发布计划匹配的规划
上下文，D3 不推测未知目标；调用方必须先提供当前规划帧或进入区域授权规划。仍需 main
扩大故障 seed 和规模，并另行完成 AirSim 运行验证。生产 ACK、D4 执行许可和 D7 控制
许可保持独立。

## 44. 故障代际离线重放（2026-07-22）

### 已完成

1. authority planning frame 的离线 replay 使用 `previous_plan` 还原规划器求解阶段的 owner、
   source、target 和 link，再应用冻结规则矩阵及 control/treatment 代价。
2. 求解完成后按记录 evidence 重放二级首次接管或活动二级延续。owner、激活时刻、lease、
   epoch 和 link 缺失、非法或不支持时失败关闭。
3. 重放 authority 后先执行严格计划载荷校验，再调用未放宽的 control 精确匹配器。离线
   authority replay 不生成生产 ACK，不开启 PPO、assist 或 authority。
4. 新增 20-reserved-seed 模块回归，覆盖稳定 5v5 二级接管的决策身份；原 4→5 库存和篡改
   负例继续保留。

### 验收

用户指定的 main 命令以 `center_failure`、5v5、3.2 秒运行 seed 1000-1019，执行成功。
40/40 arm 有 authority replay 和严格回执，20/20 control 重现
`replan_ack_no_change/changed=false`。seed 1011/1019 的 control/treatment 均为 4 个绑定、
1 个未分配且不完整目标和 5 条需求摘要。在线真值使用为 0，5 个输出文件校验通过。
D3 全量为 `386 passed, 1 skipped`，共 387 项。

### 后续

当前只验证中心失效到二级接管。二级再次失效、distributed 区域计划、通信退化和 AirSim
重放仍由 main 后续覆盖。离线重放只证明计划身份可复现，不证明控制采用或物理效果。

## 45. 区域授权显式待分配库存（2026-07-22）

### 已完成

1. `plan_regional_authority()` 将当前目标分成 D4 已授权目标和未授权差集。差集只接受上一
   计划已证明的零绑定、未分配、不完整目标；需求摘要和可选联盟库存必须相互一致。
2. 区域计划只为授权目标构造 assignment 和 coalition。显式待分配目标进入当前
   `target_count`、未分配清单、不完整清单及 `0/required` 需求摘要，不生成 owner、lease、
   commit 或执行许可。
3. 漏掉上一计划已分配目标、新增但未证明目标、篡改待分配诊断、未知授权目标和
   previous-only 可执行绑定均失败关闭。旧版本、旧 epoch、过期 lease、缺 commit/ACK 的
   既有门控保持不变。
4. 元数据增加实际授权目标、无授权待分配目标和逐目标 `authority_granted` 状态，供 main
   和 D6 区分“区域执行目标”与“仅库存保留目标”。生产 runtime ACK 验证器没有修改。

### 验收

区域计划专项覆盖 4 个授权绑定加 1 个显式待分配目标、漏授权、未证明新增目标、库存篡改
和 previous-only 可执行绑定。输出通过 `validated_assignment_plan_payload_sha256()`。
三维质点 `secondary_failure` 集成测试使用 5 目标、4 绑定、4.2 秒、seed 1011/1019，完整
测试文件为 `10 passed`。D3 全量收集 391 项，结果为 `390 passed, 1 skipped`。

### 后续

本项关闭 D3 区域计划目标集合不匹配缺口。main 仍需扩大 secondary-to-distributed 的 seed、
规模、通信退化和目标生命周期组合，并在 AirSim 中验证同一合同。D4 的区域裁决、生产
runtime ACK、D7 控制采用和物理结果继续作为独立证据。

## 46. 非生产隔离执行计划严格升版（2026-07-22）

### 已完成

1. 保留 `d3.isolated-execution-plan.v1`，将转换证据升级为
   `d3.isolated-execution-plan-conversion.v2`。接口明确区分规划帧 `previous_plan` 对应的
   `offline_solve_source_plan` 和规划帧 `plan` 对应的 `formal_authority_plan`，并保存输入
   快照摘要、完整帧转换摘要及两个源计划摘要。
2. 新执行计划严格采用 `formal_authority_plan.version + 1`、新 `plan_id`、
   `previous_plan_id=formal_authority_plan.plan_id`。`created_at` 严格晚于正式权威创建时刻和
   干预时刻；有效期受 arm、lease、stale 和已有权威有效期的最早截止约束。
3. 转换完整保留候选 binding、显式未分配/不完整库存、coalition、demand summary、
   `resource_count` 和 `target_count`。计划身份字段和正式源 authority 字段按新代际重签，
   不创建候选之外的资源目标绑定。
4. 隔离消费构造器的转换上下文包含规划帧、求解源、正式权威、原候选和转换证据。原
   receipt 仍只证明离线候选；转换证据证明候选如何形成新执行计划；消费证据最后绑定新
   计划 SHA-256。三类证据不互相冒充。
5. 生产 runtime ACK、在线 planner、stale/previous-plan/version/authority 门均保持原状。
   新路径固定关闭生产发布、生产执行、在线 authority、物理结果、reward 和 causal claim。
6. 专项 18 项、普通 5v5 与 `center_failure` 各 20-seed/40-arm 扫描和 D3 全量回归通过；
   全量为 `408 passed, 1 skipped`，skip 为可选 OR-Tools。该证据是 D3 单元和离线合同
   回归，不是 AirSim 或物理效果。

### main 后续接线

1. main 必须把同一 planning frame 的 `previous_plan` 作为求解源、`plan` 作为正式权威，
   再与 `OfflineInterventionArmExecution.plan/receipt` 一起调用 D3 转换 API，不再自行改写
   plan id/version。
2. D7、D4 和 D6 应使用返回计划的同一 `plan_id/version/payload SHA-256`。D4 场景 lineage
   应作为外层证据，不得静默修改 D3 计划后继续复用原 SHA-256。
3. 本项只完成模块合同和单元回归。真实隔离多周期 rollout、D4 adoption、D7 控制应用及
   D6 物理结果仍由 main 后续集成验收。

## 47. 区域权威离线重放（2026-07-22）

### 已完成

1. 区域规划证据新增记录权威转换摘要，绑定同一匿名帧的前序计划、记录计划、路径和时刻。
   载荷替换、跨帧或摘要篡改在离线求解前拒绝。
2. `regional_authority` 离线路径从记录 assignment 严格重建 D3 区域授权 DTO，并复用线上
   `plan_regional_authority()` 的 source/version、epoch、lease、commit、成员和库存门控。
3. 区域重放只能采用记录的授权 binding。处理臂仍计算冻结规则矩阵上的代价修正，但不能
   更换 D4 已裁决的区域成员，也不能越过 action mask。
4. 显式零绑定目标只保留在未分配、不完整和需求摘要库存中。它不会获得区域 owner、lease、
   commit 或执行权限。
5. 生成计划继续通过严格载荷校验和未放宽的 control 精确匹配。离线标记不构成生产 ACK、
   线上 authority、物理结果、奖励或因果证据。

### 验收

真实 `secondary_failure`、规模 5、3.2 秒、seed 1000-1019 已完成，40/40 control/treatment
arm 均生成。seed 1011/1019 均为 4 个绑定加 `target_0004` 显式未分配且不完整，待分配
目标无区域 assignment。在线真值使用为 0。离线干预专项 `23 passed`，D3 全量
`419 passed, 1 skipped`，skip 为可选 OR-Tools。

### 后续

D3 本地 secondary-failure 区域回放断点已关闭。仍需 main 把同一结果接入隔离物理 rollout，
核对 D4 adoption、D7 命令 lineage 和 D6 结果侧车。当前真实 reserved-seed 数据为单成员
区域授权；M-to-N 原子联盟的区域离线重放仍需独立多 seed 场景验证。AirSim 未运行。

## 48. 200×200 规划证据确定性热点（2026-07-22）

### 问题定位

1. `PlannerConfig.scalable_3d(max_candidate_edges_per_target=32)` 已把 Python 代价明细物化
   控制在 6,400 条候选边，但规划证据仍对规则和有效两个 40,000 单元矩阵分别递归匿名化。
2. cProfile 基线中单次 planner 累计 `10.436 s`，其中 planning evidence 为 `9.697 s`；
   `_safe_cost_breakdown` 调用约 80,200 次。向量化代价构造约 `0.085 s`，Hungarian 两臂
   合计约 `0.53 s`，因此本轮不重写代价模型或求解器。
3. previous-plan 周期还会为迟滞比较复制全部 breakdown，进一步放大完整矩阵成本。

### 已完成

1. 同一源 breakdown 结构按对象身份只清洗一次，匿名结果为只读映射；缓存同时保存源对象
   引用，避免对象编号复用导致误命中。
2. 规则和有效结果共享源 breakdown/reject 结构时复用匿名 tuple。两个数值矩阵仍是相互
   独立的不可写快照；学习 assist 形成不同结构时仍分别匿名化。
3. `_readonly_array()` 从源数组直接生成一个只读字节快照，移除额外中间数组复制。
4. 迟滞比较只复制 `hard_safe_candidate_mask` 内的 breakdown。previous-plan 边由既有
   preserved-candidate 合同纳入候选；被裁剪或硬拒绝单元继续保留 sentinel，不参与旧计划
   或候选解评分。
5. 未修改规则代价、不可达边、容量、M-to-N demand slot、Hungarian、迟滞、版本、stale、
   联盟或 D7 binding 语义。

### 验证

1. 新增 3x5、5x3、200x200、M-to-N 和 previous-plan 多周期测试。测试同时检查分配规模、
   角色/容量、稳定签名、版本保持、只读证据和 breakdown 清洗上界，不以墙钟作为脆弱门限。
2. 独立 200x200、32 候选边、3 次重复的向量化中位数由 `2651.953 ms` 降至
   `189.111 ms`，加速 `14.023x`；当前复跑为 `195.716 ms`。结构保持 40,000 条完整边、
   6,400 条候选边和 200 条 assignment。
3. 优化后预热求解器的 cProfile 中 planning evidence 为 `0.210072 s`，breakdown 清洗
   为 6,601 次。完整 seed 42000、2.2 秒、200v200 集成运行的三次 D3 规划由
   `7.329949 s` 降至 `1.013593 s`，在线真值使用为 0，计划 ACK 为 3。
4. 语法检查和定向 `62 passed` 已通过。D3 全量选定集为
   `422 passed, 1 skipped, 2 deselected`；两项 `global_track_stale` 可在未修改 HEAD
   复现，作为 main/D7 跨模块既有失败保留，禁止放宽 stale 合同。

### 开放项

上述墙钟数据只用于开发归因。完整 200v200 多 seed、不同候选边上限、previous-plan 长周期、
AirSim 和物理拦截仍需 main 统一运行并由 D6 汇总。更大规模的稀疏流或区域分解仍是后续
研究，不进入本轮 P1 修复。

## 49. AssignmentPlan 在线成本证据单副本（2026-07-22）

### 问题

1. clean 10 秒、seed 42000 输出的一条 `modules.d3.assignment_plan` 为 9,905,419 字节。
   其中 `cost_breakdowns_by_edge` 与 `current_cost_breakdowns_by_edge` 各含 6,304 条记录，
   单份为 4,757,920 字节，内容完全相同。
2. 全仓库 Python 消费者只读取规范字段 `cost_breakdowns_by_edge`。旧 `current_` 字段仅在
   planner 生产处出现。两个 tuple 在内存中可共享边字典，但进入总线 `to_dict/JSON` 后会
   写出两份完整列表。
3. 成本明细不能改成摘要或采样。D6 审计、回放和问题定位仍需完整候选边证据。

### 实施

1. 内部证据升级为 `d3_assignment_evidence_v2`，计划外层继续使用
   `assignment_plan_v2`。规范列表仍是 `cost_breakdowns_by_edge`。
2. 元数据新增 `d3_cost_breakdowns_by_edge_v1`、条目数、规范 SHA-256、
   `inline_canonical_single_copy` 和 `current_cost_breakdowns_by_edge_ref`。旧字段本体不再
   写入 v2。
3. `assignment_evidence_from_plan()` 支持 v1 规范字段、v1 双字段和仅旧别名三种输入。
   双字段内容冲突时拒绝；v2 缺规范字段、计数、摘要、存储方式或引用时拒绝。
4. 执行签名不包含本项审计元数据。assignment、候选集、Hungarian、迟滞、owner、版本、
   stale、联盟和 D7 binding 保持原语义。完整计划 payload SHA 会随 schema 变化，消费者应
   对实际收到的 v2 payload 重算，不得复用 v1 摘要。

### 验证

1. 合成 200x200、6,400 候选边计划从 10,466,292 字节降至 5,622,366 字节，减少
   4,843,926 字节和 46.28%。assignment、稳定签名、执行签名、plan id/version 和完整边
   证据均等价。
2. 只读长时样本按相同字段投影后为 5,147,795 字节，较 9,905,419 字节减少 48.03%。该
   结果是旧产物的确定性投影，不替代 main 新 schema 长时复跑。
3. 新增 5 项专项测试，覆盖单副本、v1 旧别名、计数/摘要篡改和 stale/version。D3 全量
   430 项中 427 passed、1 skipped、2 个既有跨模块 `global_track_stale` failed。

### 后续

main 应在 clean worktree 重跑 10 秒以上 200v200，确认总线文件、D6 读取、runtime ACK 和
内存峰值。旧归档仍按 v1 读取；外部直接索引 `current_cost_breakdowns_by_edge` 的消费者需
改用规范字段或 D3 导出函数。AirSim 接口没有变化。

## 50. 冻结输入性能归因与身份签名复用（2026-07-22）

### 已完成

1. 增加定长、计划外的 `D3PlannerOperationCounts`，覆盖全量对、候选边、连通分量、
   Hungarian 准备矩阵、计划边哈希、迟滞重评分、匿名证据复制、`plan_id` 生成和发布校验。
   墙钟只由 benchmark 记录，不进入计划元数据或控制合同。
2. 固定 200×200、seed 42000、top-32 匿名输入，并记录输入 SHA-256。基准同时执行默认、
   身份重复计算参考和关闭离线证据参考；参考路径不进入运行时配置。
3. `_finalize_and_publish()` 在调用内复用候选执行签名；latest published execution signature
   由 planner-owned cache 跨帧保存并作为发布权威。caller previous 只做一致性校验，不能
   充当 latest；公共 `publish_plan()` 仍从待发布对象计算 candidate signature。
4. 三条路径的 binding、计划版本和规范业务哈希一致。默认上一计划帧中位为 334.735 ms；
   身份重复计算参考为 389.673 ms；关闭离线证据参考为 223.147 ms。墙钟只作本机归因。
5. 区域接管先校验 plan id/version，再保留 pending inventory 的
   `RegionalPlanAuthorityError`，最后执行通用执行语义校验。直接发布和 authority fence
   继续使用可信 latest 签名失败关闭。规则代价、需求槽、Hungarian、迟滞、版本和 D5/D7
   binding 不变。

### 验收与后续

身份、区域、authority fence 和性能诊断定向组合 `46 passed`。该阶段初次收集 439 项，结果
为 `436 passed, 1 skipped, 2 failed`；两项失败表现为 main/D7 `global_track_stale`，skip
是可选 OR-Tools。后续 main 修复 seed 7 的未消费后验调度，D3 修复 seed 41 的 ACK 取样；
当前全量为 `438 passed, 1 skipped, 0 failed`。D3 未放宽 stale 门控。

## 51. clean 10 秒三种子集成复核（2026-07-22）

### 已完成

1. main 在 clean commit `8f86192` 上运行 200v200、10 秒、seed 42000-42002。三组均为
   clean、finite，在线 truth 使用为 0。
2. 每个 seed 均调用并发布 D3 计划 10 次，计划 ACK 为 10。binding ACK、control applied
   和 hold 摘要与旧 clean commit `3bac3ff` 逐 seed 一致。
3. D3 assignment 累计墙钟为 `3.437/3.319/3.110 s`，均值由旧提交的 `3.348 s` 变为
   `3.289 s`，约 `-1.8%`。该幅度按基本持平和调度噪声处理，不形成性能晋级或代码归因。
4. 本次结果确认 D1 快照优化没有改变 D3 调用次数、计划业务摘要或执行语义。规则代价、
   Hungarian、需求槽、迟滞、版本及 D5/D7 binding 未改变。

### 证据边界与后续

冻结 200x200 benchmark 继续用于固定输入归因，默认上一计划帧保持 `334.735 ms`；clean
三种子结果用于完整 episode 的累计墙钟和业务一致性。两组证据不得互相替代。后续由 main
继续验证 AirSim、物理拦截、长期内存峰值和系统实时预算；D3 不基于本次 1.8% 差异调整规则
代价、迟滞或发布合同。

## 52. 独立运行计划谱系等价规则（2026-07-22）

### 合同结论

1. 新 planner 实例的首份计划使用独立 `uuid4` 身份。同 seed、同输入的两个独立实例产生
   不同原始 `plan_id` 是有意合同；版本、执行签名和业务决策仍应一致。
2. 同一实例内，evaluation refresh 保留原身份；执行语义变化建立新身份并严格升一版。
   authority generation fence 可在执行签名不变时升版，但必须保留专用 fence schema、原因
   和父计划引用，不能与普通 refresh 合并。
3. `execution_signature()` 不包含随机 `plan_id`，但包含 assignment、coalition、未分配和
   不完整集合、人工授权，以及 owner、activation、regional commit、epoch/lease 等执行
   元数据。跨运行应直接比较该签名或其等价规范载荷。

### main 比较流程

1. 先核对 episode、seed、输入摘要、场景版本、时间轴和 D3 事件数，再按权威总线序号排序。
2. 分别验证两个运行自身的 identity/version/parent 链。链不合法时直接判失败，禁止先删 ID
   再比较。
3. 对每个运行按计划号首次出现顺序建立 `raw_plan_id -> Pxxxx` 映射。刷新沿用原 token；
   新身份同时记录 `(token, version, parent_token, owner, transition_reason, published)`。
4. 只替换已声明的计划引用字段和由计划号确定性派生的 binding/decision 标识。资源、目标、
   全局航迹、节点、区域、advisory 和 coalition 标识保持原值。
5. 对替换后的载荷重算规范摘要，再逐事件比较业务字段、版本、父关系、stale/owner/coalition
   语义。原始 payload/ACK 摘要只用于各自运行内部完整性校验。

### 证据边界

D3 的 `AssignmentPlan`、`AssignmentRecord`、`AssignmentEvidenceExport` 和
`PlanningTickHistoryRecord` 已携带前序、supersede、latest 和版本字段。当前 main-owned
scalable publication 是简化投影，未直接输出顶层 `previous_plan_id`。现有产物仅在线性版本
连续、无丢失发布记录时允许由相邻发布推导父关系，并必须标注为推导证据；正式长期对比应
改用 planning-tick history。该接线属于 main 集成范围，不通过修改 D3 身份生成器解决。
