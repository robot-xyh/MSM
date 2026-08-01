# D3 中心化资源-目标分配综述及子方案

## 2026-07-31 来源独立评价 v2 结果复核

D3 按冻结合同完成唯一一次 v2 来源独立评价。输入为 `20000-20099` 共 100 个 seed、
100 个 episode 和 292 帧，来源 train/validation/test 分组为 178/57/57 帧。模型、
归一化、教师、阈值和安全投影未修改，正式 seed `1000-1019` 未读取。

机器门整体通过。正类安全换绑为 `13/110=11.82%`，正类教师完全匹配为
`8/110=7.27%`，负类 exact-R0 为 `182/182=100%`，均超过预注册门限。94 个失败关闭帧
的矩阵和绑定均恢复 R0；重复资源、硬禁边、M-to-N 原子性、版本和规则矩阵突变违规均为
0。在线真值使用为 0，固定五文件及校验和通过。

结果状态为 `source_independent_evaluation_v2_gate_passed_not_admitted`。这项证据只关闭
D3 的“来源独立评价未执行”缺口。D6 独立复核、正式保留集、运行采用、版本化 ACK、物理
窗口、同键 R0 非退化和 production admission 仍开放。所有运行、分配、计划、控制、物理
和正式权限保持 false。2026-07-31 D3 全量回归为
`668 passed, 1 skipped, 1 warning`；跳过项仍是可选 OR-Tools。

## 2026-07-30 来源独立评价 v2 复核（评价前历史状态）

v1 官方命令只运行一次。预检通过，逐帧读取因 `source_scenario_scale_mismatch` 失败，
没有结果目录和模型指标。main 的纯结构统计确认，配置目标数描述场景规模，在线
`anonymous_targets` 描述 D1/D2 航迹集合。两者基数不具备逐帧相等关系。

D3 已新增 v2 合同和评价入口。v2 将 cell 目标数字段定义为
`configured_scenario_target_count`，允许匿名航迹数随漏检、虚警和航迹起落变化。匿名
资源数仍须与配置资源数相同，成本矩阵、动作掩码、候选边、需求槽、有限值和匿名身份检查
保持不变。失败上下文只携带场景、seed、帧序号、匿名数量和矩阵形状。

v2 没有改变冻结 bundle、归一化、教师、安全投影、性能门或权限。合同 SHA 为
`f47ec9d0...a8497e7`，源码树 SHA 为 `b31d0b86...de2438`。新增测试 `9 passed`，
v1/v2 专项 `26 passed`，D3 全量 `649 passed, 1 skipped`。

当前状态是 `evaluator_v2_ready_evaluation_not_run`。下一步由 main 使用新的唯一输出身份
授权一次 v2 评价，随后由 D6 独立复核。正式 seed `1000-1019` 仍未读取。

## 2026-07-30 A1 来源独立只读评价复核（评价前历史状态）

D3 已完成 assignment-aware 开发候选的来源独立评价器和预注册合同。合同锁定
`20000-20099`、10 个场景规模单元、冻结 bundle manifest/state/tree 三摘要、冻结源码
清单和固定性能门。train、validation、test 不再具有训练或选模语义，只作为同一次
`source_independent_evaluation` 的来源子组。

评价器逐帧记录规则基线、模型候选、安全投影后的有效结果、正负类分母、OOD 和拒绝原因。
输入或摘要不一致直接停止；性能门不通过时仍生成未准入报告，便于 D6 独立审计。任何失败
关闭帧必须恢复原始规则矩阵和 R0 绑定。输出没有 assignment、plan、runtime、control、
physical 或 formal-admission 权限。

2026-07-30 的验证仅覆盖软件合同，专项 `17 passed`，D3 全量
`640 passed, 1 skipped`。未运行新来源评价，未生成聚合结果，未读取正式 seed
`1000-1019`。下一步由 main 指定唯一输出位置并执行一次；D6 复核完成前，不能进入正式
holdout。

## 2026-07-27 提交前复核

当前 A1、隔离批量和区域提示实现可进入独立 D3 提交。新增复核确保序列化候选不能通过
重算摘要伪造计划连续版本，复合真值/Actor/Object 身份字段不能进入在线候选选择。区域
提示仍坚持来源版本、统一权属、租约、资源守恒、hold 原边硬安全和严格后继条件；无动作
提示不机械升版。

全量测试共 563 项，`562 passed, 1 skipped`。开放项仍是跨模块证据闭环：A1 的实际
publication/runtime ACK/物理窗口与同键 R0，A2 的持久化非零安全动作、owner ACK 和物理
非退化。当前实现不授予生产 assist、分配或控制权限。

## 2026-07-26 A1/C1/F1 证据装配复核

main `d59352b` 要求学习 scope 在 episode 写盘前证明模型实际进入 assist。D3 此前关闭了
legacy v2 绕过，但 v3 仍只有清单内部校验。调用方可以直接向 production writer 传入
qualified admission，也可以手工填写正向布尔和格式正确的占位 SHA，让 loader 接受。
这条链不等价于“D6 外部审计 -> D3 evidence assembler -> 新 bundle”。

本轮关闭该 P0。`save_model_bundle()` 只生成 development/research bundle，调用方提供
qualified admission 时在创建文件前拒绝。手工 v3 清单即使通过字段和 promotion 校验，
production assist 也返回 `bundle_assist_evidence_assembler_unavailable`。v2/v3 shadow、
`promotion_bypass_forbidden`、规则回退、硬禁边、Hungarian、版本和 stale 逻辑保持不变。

实际 bundle 未修改，路径为
`research_modules/d3_assignment_planner/outputs/formal_bc_development_20260720/bundle/`。
manifest/state/tree/binding SHA-256 分别为：

- `a9213d65606a9e2f921040e153488c0f4cdebb10882fa16013fce5b59f9314c0`
- `e3da9fd5b54451da83358405b6051991e0c78bcf9f538b350d459b05faf8e0b2`
- `3c08e58171c0474de9596fd3285d17bb50614a88cd7bbf3bf9af5345c7fee085`
- `70aa1b0f0f2869cdae0f9ba32b18499b003c88ebfcdb9e9dce0bc950b13542a8`

该 bundle 为 development/shadow-only，promotion unavailable。模块 shadow 加载成功，
assist 返回 `bundle_shadow_only`；main 解析为规则回退。A1、C1、F1 均在 D3 条件上失败
关闭。C1/F1 还需要 D4、D5 各自独立准入，不能由 D3 状态替代。

D6 sidecar 文件 SHA-256 为
`f3852251daf02ec87fe878e7fb80aad6f381d8c0756a5c956a32e737a3871c3b`，状态仅为
`pass_offline_assignment_comparison_only`。runtime ACK、post-intervention physical
outcome 和 paired non-degradation 均不可用。当前不能合法生成新 admitted bundle。

D6 当前有三类可复用能力：

1. 跨模块数据审计已提供 D3 数据 manifest/frames SHA、60/20/20 seed、保留 seed 零泄漏
   和全样本审计。
2. 旧 reserved-seed sidecar 已绑定 D3 manifest/state SHA，并验证 20 个处理臂同帧应用；
   它明确没有 runtime ACK、物理结果和 paired non-degradation。
3. 新 formal-scope auditor 能复核 bundle 文件树、实际 assist 采用、物理结果和同键 R0
   非退化，但当前没有实际 A1 输出。该 auditor 明确
   `model_promotion.allowed=false`，也不替 D3 强制至少 20 个未见 seed。

因此 D3 不新建第二套通用审计 schema。下一验收顺序为：main/D7 生成 1000-1019 的模型
采用 ACK 和成对物理窗口；D6 输出实际 A1 审计及校验和；D3 再实现模块专用装配器，绑定
数据、切分、源码、模型、bundle tree 和 D6 报告并生成新 immutable bundle。不得修改旧
bundle，也不得把 unavailable 补零。

2026-07-26 定向 `21 passed`；D3 全量为
`465 passed, 1 skipped`。唯一跳过为可选 OR-Tools。

## 2026-07-25 正式 R0 滚动需求复核

clean commit `32b3b40` 的 `high_threat_m_to_n` 200v200、seed 1000、2.0 秒正式单元
在 `t=1.0` 暴露运行级 P0。一个无 executable assignment 的旧 `k=1` incomplete
coalition 本周期升为完整 `k=3` 候选；其他 coalition 的成员迟滞触发全局 hold，旧需求
库存被错误保留，最终规范化抛出需求不一致异常。

D3 已把需求合同检查前移到旧计划可行性评分。需求数量、主资源数量、协同模式、时间模板
或 assignment demand 变化时，上一计划不能被迟滞保留。当前求解器重建版本化候选，最终
规范化仍严格执行容量、资源唯一性、all-or-none、主备角色和需求一致性检查。需求未变化
的成员换位仍执行原驻留和收益迟滞。

同一配置的当前工作树开发复验完成 2.0 秒。`GT3D-000021` 在 `t=1.0` 重建为完整
`k=3` coalition；有限状态为真、在线真值使用为 0，197 个 assignment 使用 197 个唯一
资源，过分配和需求摘要失配为 0。新增回归覆盖需求升高、降低、同需求保持、过分配拒绝
和 200 输入规模。D3 全量为 `464 passed, 1 skipped`。

owner 结论：P0 代码路径已修复并完成开发复验，正式证据尚未闭合。原分片和 marker 仍
绑定 `32b3b40`；main 需在新 clean commit 下重跑正式单元和分片，不能把当前结果标为
formal complete。

## 2026-07-25 多周期行为克隆影子复核

D3 已把原单帧处理臂扩展为多周期成对评估。规则组和处理组接收相同匿名输入、时间戳和
外生事件，各自连续使用自己的上一计划。处理组只修改硬安全候选边代价，最终仍由原
Hungarian 或需求槽 Hungarian 求解。默认在线规划器、PPO、assist 和 authority 均未改变。
收尾复核同时修复了多周期接口未应用自定义 `cost_weights` 的问题；两组现在使用独立但同
配置的 `CostModel`，默认权重落盘结果不变。

本次固定保留种子影子评估使用 1000-1019 共 20 个保留种子，与 0-99 训练种子零重叠。
六类场景共 620 个周期，处理组实际改变 580 个代价矩阵；120 个周期产生不同绑定，受控
匈牙利切换边界在
20/20 seed 中可辨识。资源失效场景也出现绑定差异。其余非等量与目标增删场景虽然改变
代价，没有改变最终绑定。

规则组累计抖动 520，处理组 200；处理组按规则矩阵重评分的周期平均代价高 0.000707。
40 个 M-to-N 需求变化周期触发分布外回退，矩阵逐元素恢复规则值。重复资源、硬约束或
谱系违规、旧版本采用和在线真值使用均为 0。该结果证明模型有决策影响，也显示稳定性与
规则代价之间存在取舍，不能解释为任务收益。

D3 owner 判断：多周期“可辨识性”P1 已关闭；运行采用和物理非退化 P1 保持开放。下一步由
main 在隔离世界中绑定 runtime ACK、后续状态与 D7 物理结果，再交 D6 独立复核。当前不
启动 PPO，不调整 OOD、置信度或硬门限，不开放线上辅助。新增专项 9 项通过，D3 全量为
`459 passed, 1 skipped`。

生成结果绑定了训练种子注册表、模型清单、权重、数据帧和切分摘要，但对应源码尚未形成
clean commit。该目录仍是开发证据，不能作为正式准入制品。
两份 CSV 已由 D3 writer 以显式 LF 重生成，规范化内容摘要保持不变。

## 2026-07-23 身份承诺准入评审

D2 已能发布每轨 `identity_commitment_state`。D3 当前把该状态作为求解前硬准入条件：
`committed` 可进入候选矩阵，两类 uncommitted、缺失和未知状态对全部资源边直接拒绝。
学习残差、Hungarian、需求槽和迟滞都不能恢复被拒绝边。

main 负责触发已有绑定的 hold/replan。D3 收到当前非 committed 状态后采用无该目标绑定的
候选并严格升版，审计状态为 `accepted_identity_commitment_replan`。该安全撤销只绕过保留
旧绑定的迟滞，不绕过 stale、授权、owner、epoch、lease 或版本检查，也不修改
`global_track_id`。M-to-N 中 primary 与 reserve 整体阻断。

集中测试文件 `12 passed`；D3 全量 `450 passed, 1 skipped`，唯一跳过为可选 OR-Tools。
固定 clean 提交 `7e15dac9cdaf6743999dfe045a70676fd31a17d6` 的 200v200、2.2 秒、
seed 1100 运行已完成 D2 commitment map 到 D3 的接线验证。`hold_only` 与
`hold_plus_centroid` 两臂结果一致：`t=0.75` 发布 v1/193；`t=1.0` 有 11 个原 v1
目标进入 `identity_uncommitted_ambiguity_hold`，D3 强制重规划、绕过迟滞并严格发布
v2/186；`t=2.0` 发布 v3/186。

v2 明确记录 `identity_commitment_forced_replan=true`、
`identity_commitment_replan_reason=previous_target_identity_uncommitted` 和
`identity_commitment_hysteresis_bypassed=true`。11 个目标全部从 v2 assignment 删除。
从 `t>=1.0` 起，D3、D5 主动视觉、D5 终端绑定和 D7 导引的违规继续执行均为 0。

main 终态 binding hold count 为 13、event count 为 1；13 是运行时绑定处置计数，D3
rejected target 数为 11。本 episode 未主动注入 stale plan，过时计划拒绝继续由
AirSim/module unit regression 证明。该结果验证运行时安全撤回，不构成 D1 质心修正、D2
关联算法或 seed 1100 物理性能晋级证据。

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

- P0 implementation done / formal rerun open：`32b3b40` 正式 R0 暴露的空 coalition
  需求升高与全局成员迟滞冲突已修复；同配置开发复验通过。新 clean commit 下的正式单元
  和分片尚未重跑，当前不能标记 formal closed。
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
- P1 跨模块运行时撤回 done：main 已将 D2 commitment map 接入 D3 输入；clean seed
  1100 两臂均对 11 个已分配目标完成 v1 到 v2 的严格撤回，D3/D5/D7 后续违规执行为 0。
  多 seed、动态非等量和主动 stale 注入仍作为证据校准项保留。
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

## 54. 学习干预可辨识帧复核（2026-07-26）

20 个保留 seed 的既有 D3/D7 续跑已证明两组计划均被消费并进入物理窗口，但最终绑定
0/20 变化，因而轨迹和指标相同。该结果说明原共同检查点选择过早或没有越过 Hungarian
切换边界，不能用于判断学习处理对后续控制的影响。运行又来自脏工作树，不具备准入效力。

D3 本轮增加真值无关资格层。规则帧和处理帧必须来自同一匿名输入、同一前序计划和同一
时间；处理模型必须实际修改 hard-safe 成本并产生不同绑定。两份计划分别经过资源唯一、
成本一致、硬候选、版本、有效期、需求槽和 M-to-N 原子性检查。fallback、OOD、timeout、
nonfinite、模型未应用和任何合同缺失都返回稳定拒绝原因。

公开 selector 验证 main 历史的 `sequence_index` 与 `timestamp_s` 分别严格递增，再返回按
规划时间首个 eligibility 为真的记录。重复或逆序时间戳失败关闭；当前不允许同一规划时刻
存在多个候选记录。它不读取 seed 的物理结果，不跨 D7 选择检查点，也不产生 admission 或
authority。证据 schema、规范摘要和内容 SHA-256 可供 main 后续预注册共同帧；SHA 不是
来源签名。

专项 `19 passed`，D3 全量为 `484 passed, 1 skipped`（485 项）。默认规则/Hungarian、
需求槽、代价、迟滞、OOD 阈值、production writer/loader 和 assist 权限未改。D3 模块内
资格合同已完成；main 仍需接入真实逐帧历史并重跑 clean 多 seed。

## 55. 单帧隔离重放生产者复核（2026-07-26）

main 不能只凭一份规则规划帧构造处理帧，也不能把手工“模型已采用”布尔传给资格接口。
D3 现提供公开单帧重放生产者。它从同一冻结规则输入新建两个隔离规划器，规则组不加载
学习助手，处理组只加载 manifest SHA-256、policy version 和 development/shadow-only
边界均通过的冻结 bundle。两个候选均以 `publish=False` 计算。

接口先校验前序版本、计划升版链、有效期、完整规则输入摘要、航迹和资源标识顺序以及有限
数值。输出 DTO 保存两份完整 `PlanningFrameEvidence`、资格证据、bundle 实际身份、回退
原因、输入谱系和内容摘要。truth、reward、物理 outcome、旧版本、矩阵差异、标识变化和
摘要篡改均失败关闭。运行发布、运行 ACK 和 authority 始终不可用。

17 项新专项全部通过。原离线执行器 23 项回归继续通过，证明共享 arm 重构没有改变既有
批量执行；与资格选择测试合计 `59 passed`。D3 全量为 `501 passed, 1 skipped`（502 项）。
默认 Hungarian、需求槽、规则代价、阈值、生产 loader/writer 和 assist 权限均未改变。

该接口只提供 single-frame checkpoint-selection evidence。匿名帧没有 seed，seed
`1000-1019`、split 和清单完整性由 main/D6 外层校验。该接口形成时尚未完成的 20-seed
clean 正式运行现已由下一节闭合；D7 共同检查点、runtime ACK、outcome、reward 和
admission 仍未完成，不能从模块单元测试或批量合同推导。

## 56. 20-seed 外层 runner 复核（2026-07-26）

D3 新增的外层 runner 没有把 seed 写回 `PlanningFrameEvidence`。seed 与匿名帧的关系由
显式 manifest 保存，且 seed 清单固定为 `1000-1019`。每个文件同时使用文件 SHA、完整
内容 SHA 和输入快照 SHA；bundle 使用 manifest 与 state-dict 双摘要。runner 不枚举目录，
也不接收调用方 eligibility、物理结果或真值。

跨运行确定性没有沿用单帧 DTO 的随机 plan id 和墙钟推理耗时。batch 重新生成语义摘要，
只比较输入、矩阵、动作掩码、绑定、bundle、回退、安全状态和选择结果。单元夹具两次运行
的四个输出逐字节一致。该处理不会改变单帧完整 DTO，也不改变在线计划身份合同。

旧 `active_risk_clean_*` 和 `checkpoint_paired_physical_20seed_*` 输出仍未改名或补写。
main 已在 clean source commit `0ed7ca2730f5354be1e6021f9882f1ae26bc42df`
重新生成 20 seed、每 seed 5 帧、共 100 帧的匿名输入。manifest SHA-256 为
`e5367d2651955f809b482d78ef3205cbdf44d57eae576c80f64cbd38eac59a44`，输入
`SHA256SUMS` 全部通过。首次运行在 seed 1011 序号 3 因新增目标联盟 token 与隔离规划器
本地命名不同而失败。该帧除联盟标识外，binding、成本、迟滞、版本、窗口、决策和规模均
一致。

D3 增加严格记录联盟身份恢复。它只允许前序计划中尚无联盟的目标采用记录帧已哈希绑定的
匿名标识；前序已有联盟必须保持连续。assignment、需求摘要、成员、metadata 和最终控制
执行签名继续校验。重复联盟标识、前序标识重写及引用篡改均失败关闭。

修复后的正式 clean evaluator 使用代码提交
`bdb665eb8e63a17f5f15dbf3fe472af10e5e5b5c`。正式输出 `SHA256SUMS` 全部通过，内容
SHA-256 为 `c01b13fb5925d99078a3bb9505dc0f9511ec5ab700a432399d3ebe0fcfb55592`；
输入与输出外部归档 SHA-256 为
`127ad91d864b136ab10cde7111bf6241a7a765ad4467aa449ef29cbb5557ef5e`。
20/20 seed 均为 `unavailable/no_eligible_frame`；100 帧中 80 帧应用学习代价，20 帧
分布外回退，每个 seed 的 binding change、硬违规和 `global_track_id` 改写均为 0。
`publish=false`，生产分配/控制权限均为 false。两个空目录逐文件一致属于开发确定性复核；
正式输出由独立校验清单和内容摘要约束。

最终回归结果为单帧专项 `23 passed`、相关合同组合 `79 passed`、D3 全量
`521 passed, 1 skipped`（522 项）。隔离批量重放合同正式闭合，但当前 development
policy 没有跨过 Hungarian 离散边界。D3/D7 共同检查点不存在，A1、默认路径、PPO、
assist、生产权限和物理结果仍未准入。

## 57. A1 选择后证据复核（2026-07-26）

现有 `learning_intervention_eligibility.py` 和 `isolated_intervention_batch.py` 已经负责
匿名输入、真值隔离、安全资格和首个 eligible 帧选择。D3 本轮没有重写这些条件。新增
`a1_intervention_selection.py` 消费既有资格证据，只处理预注册后的近似竞争选择、严格
版本变化和后续运行事实装配。

模块接口把七个状态分开：策略已评估、代价修正已接受、离散分配已变化、计划已发布、运行
确认已取得、完整物理窗口可用、同 seed R0 配对可用。候选和选择对象不能携带发布、ACK
或物理真值。发布对象必须由 main D3 总线实物构造；运行确认复用现有
`AssignmentPlanRuntimeAckEvidence`；物理与配对状态复用现有
`RuntimePlanWindowRewardEvidence`。每一级都绑定计划号、版本、来源总线序号和 payload
摘要。

近似竞争选择仍受确定性安全外壳约束。处理计划不得增加总需求缺口或高威胁目标需求缺口，
不得越过 hard-safe candidate mask，不得重复资源或破坏 M-to-N 原子性。计划必须相对前序
严格升版。规则成本基准下的绝对差、相对差、最大代价修正和最大绑定变化数均在评估前
预注册。seed、序号、时间超出预注册范围时失败关闭。

专项 `13 passed`。正例仅是三资源、两目标、一个双 primary 的模块夹具，用于证明有竞争帧
可以形成安全离散变化以及后续阶段可独立装配。正式 20-seed/100-frame 输入没有重跑，既有
结果仍为 20/20 `no_eligible_frame` 和逐 seed binding change 0。D3 全量收集 535 项，
结果为 `534 passed, 1 skipped`，skip 为可选 OR-Tools。正式结果不能通过新 selector
事后改写。

main 尚需完成四项接线：在运行前持久化预注册；把选中处理计划按严格新版本发布到真实总线；
将 D7/运行时 ACK 对回该发布；把 D6 为全部 binding 生成的物理窗口及同 seed R0 配对交给
生命周期装配器。当前 policy 无选中帧时，这些阶段应全部保持 unavailable。production
admission bundle 仍需另外绑定训练数据、切分、模型树和 D6 正式审计，不能用本次 DTO
合同替代。

`docs/AIRSIM_INTEGRATION_PLAN.md`、`docs/EXPERIMENT_REPORT.md` 和
`D3_M_TO_N_ASSIGNMENT_AND_SCHEDULING_REVIEW.md` 已检查。本次未改变 AirSim 输入输出、
未产生新实验结果，也未修改 M-to-N 求解或调度算法，因此不更新这三个文件。

## 58. A1 隔离 batch 接线复核（2026-07-27）

复核确认上一阶段的核心 A1 API 尚未被旧 batch 调用。main 虽可得到 eligibility 首帧，
但无法在不复制 bundle、匿名帧和 replay 内部逻辑的条件下生成 A1 candidate 与 selection。
D3 现扩展原 runner，以一个可选预注册文件打开 A1 模式。旧模式不带新参数，输出和 schema
保持不变。

新入口只执行一轮 replay。每帧使用 replay 已产生的规则帧和处理帧调用核心 candidate
评估器，并核对 eligibility 内容摘要。每 seed 的候选序列继续由核心 selector 决策。batch
没有引入调用方 eligibility、candidate accepted 或 selected 布尔。

预注册文件与实际模型强绑定。seed 必须精确为 `1000-1019`，序号和时间必须覆盖 manifest
全部帧，policy artifact SHA 必须等于 bundle state-dict。输入在输出前后复核，任一摘要
变化时不发布 staging 目录。

完整核心 A1 DTO 含运行内随机计划号及实测推理时间，不能直接形成确定性批量制品。新写盘
schema 使用稳定投影。它保留 candidate 阶段、成本、需求缺口、版本、规则/处理 binding、
拒绝原因和预注册谱系，排除随机计划身份及其 payload 摘要。核心选择发生在投影之前。
稳定投影只能作为 paired runtime 的检查点证据，不能声称计划已发布。

输出文件为 legacy result/CSV/中文报告、A1 result/candidates/selections 和统一校验清单。
main 的公开调用为：

```text
run_a1_isolated_intervention_batch(
    manifest_path,
    preregistration_path,
    output_dir,
)
```

新增 6 项通过：双帧合成正例两次独立输出一致，20/20 选择首帧；零残差 20/20 失败关闭；
truth、预注册篡改、seed 和帧作用域均拒绝。batch 共 `20 passed`，A1 相关合计
`33 passed`，D3 全量 `540 passed, 1 skipped`（541 项）。

本项只关闭模块内 batch-to-selector 接线。main 仍须把未来选中业务 binding 转成实际严格
升版计划并提供真实总线 envelope；D7 ACK、D6 physical window/R0 pair 和 production
admission 仍开放。当前正式 20-seed/100-frame 为 `0/20 eligible`，没有可发布处理计划。
AirSim 集成计划、实验报告和 M-to-N 专项已检查，本次无需更新。

## 59. A2 权属传播复核（2026-07-27）

main 的正向探针定位到 D3 与 D4 之间的明确合同缺口：D3 已采用有效区域提示并生成严格新
计划，但计划 metadata 没有 authority epoch 和 lease，D4 无法证明该计划仍处于提示来源
权属范围内。D4 的失败关闭结论正确，不能在 D4 侧用默认值补齐。

D3 已把权属统一性加入区域提示严格 context。全部区域约束必须共享 owner layer、owner id、
epoch 和 lease。任一差异都拒绝整份提示；D3 不从多个地区任取一个值。成功采用时，
`plan_owner`、`active_plan_owner`、`current_plan_owner`、owner node、epoch 和 lease
来自同一已验证四元组。D3 发布节点字段保持原值。

测试用目标新增触发真实执行签名变化和严格升版，验证新 metadata 完整。owner、epoch、
lease 三类不一致均回退规则规划。相同 owner 的无动作提示不被 epoch/lease 审计字段强制
升版，并明确返回无后继；无提示刷新不获得新权属字段。

复核结论限于 D3 合同。当前没有新的真实总线 ACK、owner ACK、coalition member ACK、
租约内物理窗口或配对规则基线，A2 不能标记为实际采用完成。main/D4/D6 应在下一次集成
探针中消费该新计划，不应从本次单元测试推断物理结果。

该段记录 successor 重跑前的接口状态。新批次没有可消费的严格后继，当前证据和后续动作
以第 60 节为准。

`docs/AIRSIM_INTEGRATION_PLAN.md`、`docs/EXPERIMENT_REPORT.md` 和 M-to-N 专项已检查。
本次未改变 AirSim 接口、分配算法或 M-to-N 调度，也未运行新实验，因此无需更新。

## 60. A2 后继身份复核（2026-07-27）

早期开发批次只在 seed 1002、1007 识别出无动作建议。main 按修正后的 successor 合同
重跑后确认：全部 20 个策略候选都没有配额变化、hold、跨区转移或重规划请求。原 18/20
采用表象来自并行普通 D3 滚动重规划的错误归因。D3 求解结果与来源计划具有相同执行签名，
保留同一身份是正确行为。

D3 已把内部约束应用和可执行后继发布拆开。严格后继必须使用不同计划号、递增版本和正确
来源引用。无执行变化时返回 `no_successor`、`successor_plan_available=false`，并保留
来源计划的控制权属和租约。无效提示返回 `hint_rejected`。重复零动作提示继续幂等，不
推进版本。

区域提示专项 `21 passed`；相关身份、规划证据和运行回执组合
`65 passed, 1 warning`；D3 全量 `547 passed, 1 skipped`（548 项）。

main 重跑的正式开发证据为：候选评估 20/20，可识别区域干预 0/20，实际 A2 采用 0/20，
A2/R0 收益审计 0/20。20 条记录均以
`identifiable_regional_intervention_missing` 失败关闭。输出 SHA-256 为
`ff3c10a089b6a94582451ae05d8a884af3a2bd7485acd4df0496442ea7e0ec55`。

后续应修改 A2 策略候选，使其在确定性安全投影后产生可识别的非零配额、hold、
`request_replan` 或 transfer，再建立严格后继和物理配对。D3 不修改版本合同，不机械升版，
也不把同期普通规划变化归因给 A2。

本次检查了 AirSim 集成计划、实验报告和 M-to-N 专项。代码没有改变 AirSim 消息、仿真
场景、分配代价或多机需求槽，因此这些文档不更新。

## 61. A2 非零区域干预消费复核（2026-07-27）

D3 发现 `hold` 先前只阻止 transfer 触及区域，没有冻结该区域的来源绑定。当前实现已把
hold 收紧为严格候选图约束：只保留来源计划中触及该区域且仍硬安全的边；新增、换绑和
空闲资源重新使用均被阻断。来源边硬失效时返回
`regional_hint_held_assignment_infeasible`，不恢复失效边。

`request_replan` 保持触发语义。单独请求且执行签名不变时返回 `no_successor`，不推进版本。
无来源承诺区域可以合法 hold 新进入目标并形成严格后继；守恒跨区 transfer 可以直接改变
资源绑定。严格后继新增显式 advisory、source plan、owner、epoch 和 lease 字段。

main 的不落盘 20-seed 探针为 15/20 safe/auditable。seed
1000/1002/1007/1009/1013 的 `d3_successor_plan_missing` 保留。seed 1000 的
`regional_hint_no_executable_successor` 和
`regional_hint_held_assignment_infeasible` 均符合合同。D3 不通过放宽 hold 硬安全门
追求 20/20。

区域提示专项 `25 passed`；D3 全量收集 552 项，结果为
`551 passed, 1 skipped`，另有 1 条既有 Matplotlib 警告。仍需 main/D4 提供持久化
advisory/plan/binding envelope、owner ACK、运行租约确认和同键物理窗口。本轮未运行
AirSim，AirSim 集成计划与实验报告检查后无需更新。

补跑 D4-D3 runtime ACK 集成专项时，6 个用例均在 fixture 初始化阶段被 D6
`strict_learning_adoption_audit.py` 的
`NameError: _validate_a3_pairing_inventory_output is not defined` 阻断，尚未进入 D3-D4
断言。该问题不在 D3 owned path，本轮未越权修改；需由 D6 owner 修复后再复跑。

## 62. A1 冻结帧动作裕量复核（2026-07-27）

正式 20-seed A1 结果仍是处理矩阵全部变化、最终绑定全部不变。冻结 bundle 仍为
development/shadow，清单 `alpha=0.25`、`min_confidence=0.0`，没有 assist 或 authority。
D3 本轮没有训练新模型，也没有启动正式多 seed 写盘。

新增校准接口只消费既有匿名单帧隔离重放。它先计算每个目标硬安全候选边的局部规则间隔，
再用记录 `learning_delta_c` 判断方向优势和临界 `alpha`，最后通过原 Hungarian 或需求槽
Hungarian 验证候选网格是否真正改变绑定。局部间隔判断与实际分配结果分开记录，避免把
理论可跨越误写成全局换绑。

开发夹具证明该接口能区分：

- 零残差和幅度不足导致的 no-op；
- 候选 `alpha=0.25` 产生的 3 条可辨识绑定差异；
- `min_confidence=1.0` 的低置信规则回退；
- 超过绝对修正上限的不求解拒绝；
- 可辨识但仍无发布、分配和控制权限的候选。

D3 复核后补充了消费时内容摘要重算、矩阵/清单/非有限值检查、空矩阵与无可行动作拒绝，
并阻断已经发生换绑的源帧进入 no-op 裕量校准。候选新增规则/处理绑定摘要、求解器和计划
版本证据。两目标、三资源的非等量夹具继续通过；全动作硬拒绝和构造后篡改均失败关闭。

D3 全量 `571 passed, 1 skipped`。当前关闭的是 D3 对“为什么没有换绑”的模块内诊断缺口，
不是正式 A1 采用或收益缺口。main/D6 后续需要在 clean commit 上消费实际冻结帧；任何
候选参数都必须重新冻结、预注册和完成独立 20-seed 成对验收，不能由校准接口自授权。

AirSim 集成计划、实验报告和 M-to-N 专项已检查。本轮没有 AirSim DTO、运行时计划、物理
窗口或实验结果变化，因此这些文件不更新。

## 63. A1 隔离批次公共读取复核（2026-07-28）

D6 指出的模块级断点成立。现有 writer 能生成稳定 A1 summary、candidate inventory、
selection inventory 和统一校验和，但消费方没有公共 API 复核整套目录。只读取 JSON 或
只运行 `sha256sum -c` 都不足以验证跨文件候选谱系。

D3 新增公共严格读取器。它固定七文件目录和六文件校验和覆盖，拒绝缺失、额外、符号链接
和路径逃逸。四个 JSON 的精确字段、schema、有限值、内容摘要和在线身份隔离重新执行。
预注册继续由核心 A1 validator 处理，未复制 seed、帧范围、安全外壳和权限规则。

旧批次帧与 candidate 按 seed 和序号一一连接。输入文件、内容、重放和资格摘要必须一致。
selection 的阶段计数、候选历史和首个安全候选由读取器重算。顶层 candidate/selection
contract 再与全部记录核对。计划版本关系和 binding change 也重新计算，攻击者同步更新
文件 SHA 和 JSON 内容 SHA 后仍不能绕过语义检查。

返回对象明确固定 publication、runtime ACK、physical window、R0 pair、production
admission、assignment authority 和 control authority 为 false。D6 可以把读取成功作为
“A1 隔离批次软件完整性可用”，不能把 candidate 或 selection 解释为运行采用和物理证据。

合成 20-seed/40-candidate/20-selection 主夹具和 20-seed 零选择夹具专项
`46 passed`，D3 全量 `593 passed, 1 skipped`。正式 A1 `0/20 eligible` 没有变化，
后续发布、ACK、完整物理
窗口、同键 R0 和正式准入仍开放。AirSim 集成计划已检查；本项没有运行时接口变化。实验
报告仅新增软件合同验证，不改写既有正式 100-frame 结果。M-to-N 专项无变化。

## 64. A2 当前谱系后继证据复核（2026-07-28）

区域提示主线已经能生成安全后继，缺口位于后继的外部归因。旧记录只凭
`regional_hint_applied`、计划版本和 advisory 身份判断 A2 采用，不能证明该计划来自当前
候选，也不能排除同周期普通重规划。只有 runtime-compatible 的 current-lineage 候选在
非正式预检中产生非回退安全输出后，该缺口才进入正式 20-seed A2/R0 影子评价。

D3 新增 `a2_successor_evidence`，没有修改规划器。候选 loader 对 D4 manifest 文件摘要、
内部内容摘要、权重、source identity、开发阶段和权限执行独立校验。当前实物读取结果与
D4 记录一致。单帧 verifier 再连接以下五层：

1. D4 实际模型诊断中的 scenario、seed、frame 和 snapshot SHA；
2. candidate id、model state 和 current source identity；
3. 安全投影后的配额、备用资源、hold、request-replan 和 transfer；
4. D3 前序 owner/version/epoch/lease 与严格 successor；
5. 同输入、无 A2 提示的 R0 计划。

当 R0 自身因周期输入变化形成新计划时，证据保留
`ordinary_periodic_replan_changed=true`。A2 只记录 successor 与 R0 的执行签名差异。
successor 与 R0 相同即拒绝，不能把整个新计划归给 A2。候选/R0 混用、旧版本、资源不可
行、投影动作不一致和 no-op 均有独立负例。

专项 `16 passed`，区域提示组合 `41 passed`，D3 全量
`609 passed, 1 skipped`。当前只完成模块软件边界和候选身份读取。D4/main 运行兼容性
预检显示：5v5、2 区域为 3/3 `feature_ood`，200v200、8 区域为 2/2
`feature_ood`，非回退模型执行均为 0。当前候选不得直接启动正式 20-seed。

D4 应先基于实际运行特征和动作课程生成 clean-lineage、runtime-compatible 的新
development/shadow 候选。D3 核验身份和关闭权限后，main 先做非正式预检；出现非回退
模型执行且安全投影通过后，才允许冻结候选并生成正式 successor 证据。20 个未见 seed、
计划运行确认、owner/coalition ACK、物理窗口、D7 执行和收益仍未生成；所有对应权限和
可用性字段保持 false。AirSim 集成接口和 M-to-N 调度未变化。

## 65. readiness-v3 跨区来源承诺复核（2026-07-29）

main 提供的修改前固定基线覆盖 seeds 2003-2012、20v20、8-region。D4 候选 10/10
通过原始推理、运行门、投影和隔离采用，D3 严格后继仍为 0/10。拒绝中 7/10 是
`regional_hint_previous_cross_region_commit_exceeds_allowance`，3/10 是
`regional_hint_no_executable_successor`。

D3 复核确认 transfer allowance 应约束来源计划之外的新增跨区动作。来源计划已发布的
跨区 assignment 已由 plan id/version、owner 和 lease 绑定，不应再次消耗本轮增量额度。
修复没有把它变成开放 route：受保护资源只可保留原 target-resource edge；其他目标即使
位于同一区域也不能使用该资源的跨区资格。原边硬不可行时，提示整体拒绝并回退原规则。
新增资源仍要求显式 allowance、守恒配额、备用余量、硬安全和 Hungarian 唯一性。

侦察优先级没有加入 D3 AssignmentPlan。当前接口无法说明“哪个侦察资源执行哪个区域搜索
任务”，也没有量化死区和成本作用。约 `1e-4` 的模型输出差异不构成可辨识分配干预。
reserve ratio 单独变化同样只影响增量转移容量检查，不生成备用成员名单。

新增 5 个专项场景后，区域提示文件 `30 passed`；D3 全量
`614 passed, 1 skipped`。main 尚未重跑上述 10 个 seed，因此当前结论是合同错误已修复，
不是 successor 或收益已经形成。下一步必须保留同输入双臂和全部拒绝分母，重新确认
7 个旧拒绝是形成真实后继，还是转为无执行变化。

## 66. 区域后继权限刷新复核（2026-07-29）

seed 2007 暴露的缺口成立。D3 在 t=1 形成带 owner/epoch/lease 的严格后继，t=2 无提示
重建候选时丢失权限 metadata，却沿用原身份。D6 将 authority 纳入规范执行签名，因此拒绝
该伪 evaluation refresh 是正确行为。

D3 修复在身份定稿前恢复原计划权限，要求租约有效且规范化后的完整执行签名与前序逐项
一致。租约到期、owner 失活、epoch 篡改和 fault generation fence 均失败关闭。A2 负例
同步同输入 R0 的 authority 后再比较，证明 authority 不同的计划不能称为不可区分。

main 复跑结果为完整 episode 写盘成功，D6 接受 4 ACK、77 bindings 和 1 次合法同身份
evaluation refresh，online truth=0。A2 专项 `16 passed`，区域提示/身份/围栏组合
`51 passed`，D3 全量 `618 passed, 1 skipped`。该证据关闭 D3 同身份权限丢失 P1，不
扩展为策略收益或物理结果。

README、PLAN、原则、算法和实验报告已同步。AirSim 集成计划已检查，无接口变化；M-to-N
调度文档也已检查，本项没有需求槽、联盟规模或到达调度变化，因此不修改。

## 67. 规划专用区域转移因果复核（2026-07-29）

本轮复核没有发现 D3 求解或发布实现缺陷。现有三区域夹具已具备 source、无提示 R0 和
区域提示 treatment 三个候选，本次补齐同一测试内的规范执行签名和业务集合断言。

source 绑定为 `{T-A->R-A0, T-B->R-B0, T-C->R-C0}`。同输入未发布 R0 在 B 区原资源
不可用后变为 `{T-A->R-A0, T-C->R-C1}`，并将 `T-B` 放入未分配清单。treatment 在合法
A 到 B 单资源许可和 C 区 hold 下形成
`{T-A->R-A0, T-B->R-A1, T-C->R-C0}`。三者 assignment 数为 `3/2/3`，未分配集合为
`空/{T-B}/空`。

treatment 的执行签名同时区别于 source 和 R0。相对 source 的新增绑定是
`T-B->R-A1`，相对 R0 新增覆盖目标是 `T-B`。R0 与 treatment 均为 source 的下一版本
候选，R0 不发布，treatment 严格发布并精确引用 source。owner、epoch、lease、reserve、
可达性、hold、来源承诺和 stale plan 门限未放宽。

main 已把 20v20、8 区域、seed 29 固化为永久 module-stack 正例：17 条绑定增加到
18 条、未分配 3 降到 2、版本 1 递增到 2、在线真值 0，D4 全部 execution authority
为 false。配套负例在 `t=2.0` 注入中心 fault generation 变化并阻断规划专用转移。
main 两项专项测试通过；scalable world 与 module stack 全量 `100 passed`，D4 全量
`794 passed`。跨模块正向接线和故障代际失败关闭已完成，不代表 v4 学习收益。D6 同输入
R0 和多 seed 非退化审计仍开放。

区域提示专项 `34 passed`，D3 全量 `618 passed, 1 skipped`。README、PLAN、原则、算法、
实验报告和 GAP 已同步。AirSim 集成计划与 M-to-N 专项已检查，本项没有对应接口或算法
变化，因此不修改。

## 68. A1 分配感知开发候选复核（2026-07-30）

新候选没有替换默认分配器。模型只产生有界代价修正，最终离散结果仍由需求槽 Hungarian
和确定性安全投影生成。规则矩阵、硬禁边、M-to-N、迟滞、版本和 stale rejection 保持
原合同。模型不输出计划、版本、全局航迹标识或控制。

TRAIN 用于权重更新，VALIDATION 用于检查点选择。内部 TEST 未解析，正式留出
`1000-1019` 未读取。新 bundle 与旧 bundle 并存；策略、schema 和 loader 均使用独立版本。

第 7 轮检查点在 320 个 VALIDATION 帧中产生 104 个非零修正和 14 个安全换绑。其中正类
安全换绑 13/95，教师精确匹配 9/95，负类 exact-R0 224/225。79 帧失败关闭。有效结果未
出现重复资源、硬边、M-to-N 或版本违规，R0 原规则矩阵未改写。

模型、manifest 和 tree SHA-256 分别为：

```text
c185823bd9a4cf5363d17854385aeb74c340c8ac384327281d224a1097eb8206
ec9f93d668e1aa319f65fcda0d73adb0527f316a2d1880e93e88697b6468ad3d
de7b627df9782d7d2577687f30d02d4faeeaf577ecc557c2b8d91dd6e7115dd9
```

同输入独立训练两次摘要一致。loader 只允许 `shadow` 和
`source_independent_evaluation`，全部运行和生产权限为 false。专项 5 项通过，D3 全量
为 `623 passed, 1 skipped`。

复核结论是候选已在开发验证集上形成可辨识安全离散变化，尚未证明新来源泛化或任务收益。
main 下一步应冻结上述摘要，提供全新来源和布局进行只读评价，并保留正类、负类和失败
关闭分母。只有独立评价仍有安全换绑，才考虑预注册正式留出集。

AirSim 集成计划已检查；本项不改变 DTO、settings、episode 或控制接口，无需修改。
M-to-N 专项也已检查；联盟需求、成员角色、波次和到达调度均未改变。

## 69. 权威计划载荷复核（2026-07-30）

100-cell 复现与 main 独立统计一致，共有 48 个同身份组。执行 assignment、成员角色、
联盟、owner、lease、未分配集合和 N/M 规模变化均为 0。完整载荷全部变化，主要差异为
本轮时间、迟滞与成本诊断、输入指纹和成本边证据；33 组还出现相同 assignment 集合的
序列顺序变化。

因此原 stale-demand exception 不是本轮根因，D3 也没有漏升执行版本。v3 运行故障来自
main 把同身份 evaluation refresh 当作新权威消息重发。D3 接口本身存在容易误用的边界，
本轮以 `authority_signature()` 和 `requires_authoritative_publication()` 明确：

1. 新身份表示新权威载荷；
2. 同身份、同权威签名只形成独立评估记录；
3. 同身份、不同权威签名失败关闭；
4. 完整权威摘要不缩减，传输重试必须复用首次载荷。

200v200 seed1017 的 198 条绑定集合不变，0.95/1.00 秒两份载荷有 990 个叶级差异，
造成 37 次摘要错配和 37 次交叉绑定拒绝。专项审计保存在
`research_modules/d3_assignment_planner/reports/D3_PLAN_IDENTITY_PAYLOAD_AUDIT_20260730_CN.md`。

main 已按 D3 判定完成开发态集成。D3 只读审查确认：

1. 每个 `(plan_id, version)` 的首次计划进入权威缓存，同身份评估刷新不再产生权威 topic；
2. 传输摘要首次引用不可覆盖，同身份权威字段变化在发布前失败关闭；
3. v4 100-cell 中 151 个权威身份对应 151 次发布和 151 次计划 ACK；
4. 48 次同身份刷新被抑制，权威摘要冲突和重复传输引用计数均为 0；
5. finite、D3-D4 对齐和当前联盟闭合均为 100/100，在线真值使用为 0；
6. 100v100 seed1010、200v200 seed1013 和 seed1017 均恢复。

因此该项状态改为“开发态验证关闭、正式 R0 待执行”。v4 是 `/dev/shm` 下的 2 秒三维
质点预检，未绑定 clean commit 和冻结正式结果清单，也不是 AirSim 或物理拦截证据。
正式 R0 仍须保持摘要、版本、owner、epoch、lease 和 ACK 门限不变后重跑。

main 接线使两条旧 D3 集成测试假设失效。测试现按首次权威对象校验源载荷，并断言同身份
评估刷新不生成第二个 ACK；未修改规划算法。专项 2 项通过，D3 全量为
`654 passed, 1 skipped`，跳过项为可选 OR-Tools。

## 70. Opt-in 权威代际绑定复核（2026-07-31）

D3 新增 plan 级不可变绑定和 planner 级后置绑定入口。plan 级入口严格验证非负整数 epoch、
有限且晚于 `created_at` 的 lease，保持 `plan_id/version` 并写入 generic/regional
四键。同值调用幂等；同身份改值失败。四键继续属于权威签名，不能借 evaluation
diagnostics 改写。

只绑定 `plan()` 返回副本存在真实兼容风险：planner 内部仍保存未绑定 execution
signature，下一轮若直接使用该副本会被 stale semantics 校验拒绝。现有安全顺序为：

1. main 调用默认 `plan()`；
2. main 在外部发布前调用
   `planner.bind_published_authority_generation(plan, epoch, lease)`；
3. planner 原子更新内部已发布对象和可信签名；
4. main 发布返回的绑定对象，并在下一轮把它作为 `previous_plan`。

同身份 refresh 只在其余执行签名完全相同时继承旧四键，测试已覆盖评估时刻晚于 lease，
结果仍保留原 lease。执行变化后的新身份不继承旧绑定。默认 planner、Hungarian、需求槽、
迟滞和版本规则没有变化。

复核已覆盖 authority fence、普通执行变化、regional successor、multi-owner regional
authority、secondary takeover 和 secondary continuation。fence/secondary 不携带旧
四键；regional max/min 来自新身份合同而非旧绑定；secondary 后置绑定必须等于新
`secondary_*`。helper 的接线顺序固定为 helper、`publish_plan()`、planner 级绑定。

2026-07-31 身份专项 `28 passed`；D3 全量收集 669 项，结果为
`668 passed, 1 skipped`。唯一 skip 是可选 OR-Tools，既有 Matplotlib 警告不影响结果。
AirSim 集成、实验报告和 M-to-N 专项已检查；本项没有对应 DTO、样本或调度变化，不修改。
