# D3 集中式资源-目标分配实验报告

## 1. 实验边界

本报告仅覆盖离线抽象资源-目标候选分配。规划器输出是候选 `AssignmentPlan`，必须经过人工或外部授权层确认。模块不包含真实火控参数、毁伤逻辑、飞控接口、硬件驱动、自动处置或绕过人工授权的流程。

## 2. 实验目的

D3 研究多目标、多资源条件下的滚动分配稳定性。重点验证：

- Hungarian 是否能作为 5v5 及更大规模的一对一分配基线。
- 迟滞逻辑是否能减少频繁重分配。
- 代价函数是否显式包含接近窗口、航迹不确定性、威胁权重、资源状态、视场难度和冲突风险。
- 分配计划是否版本化，并验证默认 `human_authorization_state="required"` 与 `PlannerConfig` 配置化授权状态透传。

完整算法原理、接口契约和调参建议见 [ALGORITHM_AND_IMPLEMENTATION.md](ALGORITHM_AND_IMPLEMENTATION.md)。

## 3. 分配模型

分配变量：

```text
x_ij in {0, 1}
```

总代价：

```text
J = sum_i sum_j x_ij C_ij
```

重分配条件：

```text
J_new < (1 - delta) * J_old
and dwell_time > min_dwell
and changes_used_in_window + change_count <= max_changes_per_window
```

## 4. 场景配置

| 项目 | 设置 |
|---|---:|
| 随机种子 | 20260630 |
| 目标数 | 8 |
| 资源数 | 8 |
| 仿真时长 | 100.0 s |
| 决策频率 | 2.0 Hz |
| 步数 | 200 |
| 迟滞参数 | `delta=0.2`, `min_dwell=2.0` |

运行命令：

```bash
cd research_modules/d3_assignment_planner
python3 simulations/run_rolling_assignment.py
```

## 5. 结果表

| 工况 | 重分配事件 | 变更边数 | 总成本 | 平均成本 | 高威胁未分配比例 | 平均耗时 ms |
|---|---:|---:|---:|---:|---:|---:|
| 无迟滞 | 33 | 96 | 3261.348 | 16.307 | 0.0000 | 0.162 |
| 迟滞 `delta=0.2` | 12 | 46 | 3380.071 | 16.900 | 0.0000 | 0.171 |

## 6. 图表与曲线

### 6.1 分配成本与重分配曲线

![D3 分配成本与重分配曲线](../results/cost_reassignment.png)

该图展示无迟滞与迟滞策略下的滚动成本和重分配事件。迟滞策略牺牲少量成本，换取更少的任务抖动。

### 6.2 权重敏感性分析

![D3 权重敏感性曲线](../results/weight_sensitivity.png)

该图用于判断代价项权重变化对平均成本、重分配次数和高威胁未分配比例的影响。后续扩展到不同目标密度时，应优先扫描 `threat`、`covariance` 和 `conflict` 权重。

## 7. 结论

Hungarian 仍是中心节点存在时的默认主线。迟滞逻辑显著减少重分配事件，但会带来可解释的成本上升。当前版本已加入 stale plan 拒绝、版本递增、强制人工授权状态、换配上限和 `reassignment_switch_penalty` 分项，适合作为 D4 降级协商和 D5 终端锁定的候选计划来源。

## 8. 2026-07-14 Feedback 分级回归

本轮不重跑 AirSim，也不改变上表随机实验。feedback 分级确定性合同继续检查：普通 ambiguous/legacy pair hold 不产生资源 `operator_hold`；verified friend、friend overlap、duplicate assignment/lock 和显式 feasibility reject 保持 fail-closed；transient 窗口完成后的 soft candidate 仍受 `min_dwell`/联盟成员迟滞。

现有 40-case M5N2 aggregate 缺逐 planning tick 的计划、feedback 分类和迟滞历史。因此“普通 pair hold 被扩大为整资源不可行”只能列为 churn 根因线索，不能写成已证明导致某次成员抖动、版本抖动或物理失败。验收阈值仍是最佳 profile 至少 `8/10` coalition completion；现有最佳 `5/10`，P1 物理性能与逐时刻权重/迟滞标定继续开放。

## 9. 2026-07-14 Canonical History Schema 验收

本轮新增 `PlanningTickHistoryRecord`、`d3_plan_history_record_v1` 和 `plan_history_record_from_plan(...)`，不修改 main、D6、AirSim runtime 或既有实验输出。单 tick payload 由 main 提供的 `[sequence_index, timestamp]` 排序，包含 plan/count/owner/epoch/lease、ordered assignment/coalition members、迟滞/成员变化、soft/hard feedback、成本及 stale/rollback/replan 审计；`to_dict()` 可用 `json.dumps(..., allow_nan=False)` 严格序列化，且不输出 truth 字段。

2026-07-14 的 D3 全量结果现为 `157 passed, 1 skipped`。最新 5 个测试函数覆盖 soft-feedback/往返稳定性、同窗口累计预算、跨窗口恢复、资源硬失效、missing + membership hold、owner fail-closed 和 history 预算导出；既有 history 与 held-scope/lifecycle case 继续通过。唯一 skip 是未安装 OR-Tools 的 optional installed-only benchmark。

## 10. AirSim M5N2 Baseline Seed 001 计划历史专项（2026-07-14）

### 10.1 数据范围

- 输入：`p1_terminal_closure_truthisolated_preflight_v2_20260714_m5n2_baseline_seed001/episode_006_full_flow`；
- 样本：1 个真实 AirSim seed，仿真时间 35 秒，349 个 planning tick；
- 在线 truth：本专项只读取 main 已保存的在线 D2/D3 历史，不用离线 actor truth 修正分配；
- 本次没有重跑 Blocks，因此结论属于日志审计和确定性合同修复，不是多 seed 性能结论。

### 10.2 现象

初始 v1 为 T001 的 2 primary + 1 standby reserve、T002 的 1 primary，共 4 个
assignment 记录。0.2 至 30.5 秒间计划从 v1 变到 v31，基本每 1.0 至 1.1 秒切换一次
成员；每次记录均满足该 episode 的 `delta=0.2` 和 `min_dwell=1.0 s`，所以没有违反
现有数学门限，但形成了明显周期性 churn。

31.3 秒后 D2 依次产生 T003 至 T008。T008 在 34.4 秒创建，34.5 秒 confirmed 并被
当前计划接纳，34.6 秒才进入 engageable。最终 v45 有 T001 三成员、T002 一成员和
T008 一成员，对应 `intercept_summary.json` 的 5 个 pair。T008 无离线 truth 映射，
其物理证据不可用。

另有 8 个 hold tick 因当前新目标进入 `unassigned_target_ids` 而推进版本。该行为与
“hold 不改变 current execution identity”冲突，是 D3-owned P1 缺陷。修复后 held
计划保留上一执行范围，候选目标只进入审计字段。

### 10.3 Reserve 复核

D3 v44/v45 中 INT-01 的角色是 reserve，计划记录为 standby，D3 guidance binding
按合同应为 hold。最终拦截摘要把该 pair 标为 active，是 runtime 在资源此前作为
primary 激活后没有随新 binding 降级，并非 D3 发布了 reserve activation。该问题需
由 main/runtime owner 修复，D3 不跨模块改写。

### 10.4 确定性验收

新增两个 case：普通迟滞 + 新目标、M-to-N 联盟成员迟滞 + 新目标。验收阈值均为：

- held plan ID/version 不变；
- execution signature 与上一 current plan 完全一致；
- candidate/pending target 可审计；
- 不使用 truth，不限制目标数量，不降低 stale/version/coalition 门控。

结果为 `157 passed, 1 skipped`。同时验证上一已分配目标从当前输入消失时，D3
跳过 same-assignment hold，按 `accepted_previous_infeasible` 发布新版本并记录缺失
目标。下一阶段需要 main 修复生命周期准入和 reserve
demotion 后按同几何至少运行 10 seeds；D6 再判断 churn、错误准入和物理结果是否收敛。

## 11. 最新 M5N2 347-Record 抖动专项与确定性验收（2026-07-14）

### 11.1 输入与现象

- 数据：最新 truth-isolated M5N2 baseline seed 001；
- 样本：347 条 planning records，执行版本 v1..v35；
- 现象：稳定目标/资源/需求阶段约每秒往返换员；
- 在线 truth：0；本次只读取计划/history，不用 truth 修正输入；
- 本批未重跑 Blocks。

一个代表性 membership record 为 candidate coalition cost `0.8868`、previous
coalition cost `2.8520`。previous 的当前成员边含 `2.2` soft-feedback FOV shaping；
在两侧统一排除 search-only shaping 后，previous base 约 `0.6520`，candidate 不满足
`0.8 * previous`。原日志中的 20% improvement 因而不是同一 objective 下的收益。

### 11.2 修复与门限

- `d3_hysteresis_current_objective_v1`：双侧包含当前 base edge、hard feasibility、
  当前 demand/unassigned；排除 switch、soft-feedback FOV、slot priority/role pin；
- `d3_cumulative_window_change_budget_v1`：同 `window_id` 累计已接受 change count；
  hold/refresh 不计费，新 window 清零；
- 普通验收：`J_candidate < 0.8 * J_previous`、dwell 满足且
  `used + candidate_changes <= max_changes_per_window`；
- 安全优先：missing execution target、资源 hard unavailable、plan-level owner/
  activation/authorization 变化立即新版本；预算超限时记录 bypass；
- missing + 另一联盟 hold：消失目标不得进入 assignment/coalition/membership audit。

### 11.3 结果与限制

新增 5 个确定性测试函数，D3 全量 `157 passed, 1 skipped`，接受阈值为零失败；
唯一 skip 是 optional OR-Tools 未安装。该结果关闭 D3-owned 周期性换员实现 P1，
不是 AirSim 多 seed 物理证据。剩余验收为至少 10 个同几何 seeds，比较 churn、
high-threat unassigned、stale reject 和 reserve unauthorized activation；物理 coalition
completion 仍需从最佳 `5/10` 达到 `8/10`。

## 12. Actual-v2 真实 AirSim 证据（2026-07-14）

本节只同步已写盘结果，不重跑 AirSim、不改代码。接受条件为两个 required case 均有
有效 actual metrics，且 command、actual、history 的唯一 plan ID/version 一致。

| 场景 | command/actual/history | History | Feedback churn | 物理层级 |
|---|---|---:|---:|---|
| tuned 2v2 seed 1 | `d3-plan-c3cc6d28c365/1` | 24 | 3 | pair `2/2`，target `2/2` |
| M5N2 seed 1 | `d3-plan-cfdd088a10e1/1` | 214 | 50 | pair `2/3`，target `2/2`，coalition `0/1` |

D6 actual required/available/unavailable=`2/2/0`，history available/unavailable=
`2/0` 且无 validation reason，P0 证据链通过。M5N2 第二 primary 最近约 11.02 m，
目标级 `2/2` 不能写成联盟完成；第二 primary 与多 seed 仍为 P1。

## 13. M5N2 20-Case 计划与成员稳定性复核（2026-07-15）

### 13.1 样本范围

- baseline：10 seeds，`1869` 个 planning tick；
- `candidate_soft_prediction_trend_coast`：10 seeds，`1856` 个 planning tick；
- 合计：20 case、`3725` 个 tick；
- 排除：TERM 生效前额外完成的 `png_ttc_2v2_seed001`；
- 未执行：其余 tuned case 与全部 dropout case，结果保持 `unavailable`。

### 13.2 D3 history 结果

| 指标 | Baseline + Candidate | 可用性/解释 |
|---|---:|---|
| history case | 20/20 | `record_count` 与数组长度全部一致 |
| history record | 3725/3725 | `d3_plan_history_record_v1` |
| 规模记录 | 3725 个 5-resource/2-target | 无 N=N 假设 |
| T001 角色结构 | 每 tick 2 primary + 1 reserve | reserve 为 standby |
| T002 角色结构 | 每 tick 1 primary | active/current |
| plan/version transition | 0 | 每 case 只有一个 plan/version=1 |
| member roster transition | 0 | 单 case 内没有实际换员 |
| owner transition | 0 | center 所有权保持 |
| stale reject / rollback | 0 / 0 | 本批未触发 |
| membership candidate audit | 3555 | 不是实际 churn |
| member hold / outer hold | 3524 / 31 | 31 个候选通过成员层后被全局迟滞保持 |
| transient feedback dwell hold | 150 | 不推进 current identity |

20 个 case 的成员并非完全相同：19 个 case 为 T001 primary
`INT-02/INT-03`、reserve `INT-01`；candidate seed 002 为 primary
`INT-01/INT-02`、reserve `INT-03`。因此分析第二 primary 必须从每 case 的 current
plan/role 读取，不能写死资源编号。

### 13.3 物理结果与 D3 归因边界

| 层级 | 结果 | 结论 |
|---|---:|---|
| active pair | 12/60 | 系统物理结果，不等价于计划稳定性 |
| canonical target | 12/40 | 标准目标级统计，不等价于协同联盟完成 |
| T001 coalition | 0/20 | required-primary 协同物理闭环未完成 |
| 第二 primary 5 m | 0/20 | 仍为 P1 |
| 第二 primary stop reason | 20/20 `collision_stop` | 缺 collision object，原因不可判定 |

candidate 与 baseline 的系统成功总数相同，但 paired non-degradation 判据失败，因此
candidate 不晋级默认路径。该结论不应写成“D3 退化”：两组均保持单一 current plan、
零实际成员 churn 和零 owner churn。当前证据只说明下游 candidate 没有形成稳定物理
收益，并且第二 primary/coalition 仍未闭合。

后续报告统一使用两个术语：`canonical target success` 保留 D6 标准目标分母 40；
`cooperative target diagnosis` 单独报告 T001 的 primary pair、第二 primary 和
coalition 分母 20。缺失 case 不补零，也不把 canonical target 成功数用于关闭联盟 P1。

证据完整性验收要求 20/20 case 可读、3725/3725 record 可解析且 churn 字段可计算，
本批满足；物理验收要求 active primary 进入 5 m，第二 primary 和 coalition 不满足。
文档同步后 D3 回归为 `157 passed, 1 skipped`，唯一 skip 是未安装 optional OR-Tools
的 installed-only 对照，接受门限为零测试失败。

## 2026-07-20 可扩展三维与学习辅助确定性验收

本批没有运行 AirSim，也没有使用 truth label 或 PPO。新增测试样本为：1 个 3v5、
1 个 5v3、1 个 200v200、1 个 2-target/5-resource 高威胁 M-to-N、三维规则成本、
mask/fallback/version cases，以及 1 个 32-edge synthetic behavior-cloning batch。

| 指标 | 接受阈值 | 结果 |
|---|---:|---:|
| 新增测试 | 零失败 | 13/13 通过 |
| D3 全量 | 零失败 | 170 passed、1 optional skip |
| 200v200 executable assignment | 200/200 | 200/200 |
| 200v200 策略候选动作 | `< 40000` | 800 |
| 候选密度 | 记录实际值 | 2% |
| fallback cost | 与 `C_rule` 逐元素相同 | timeout/低置信/OOD 均通过 |
| stale previous plan | 必须拒绝 | `StalePlanError` 通过 |
| BC 最小接口 | final loss 小于 initial | 32-edge synthetic batch 通过 |

200v200 单次本地调用耗时 0.621 s。该数字没有 warm-up 分布、重复样本、置信区间或
阶段归因，只作为本机功能样本，不设实时通过结论。完整分配也只证明该确定性几何中
top-4 候选保留了 perfect matching，不证明所有密集/交叉/资源失效场景都能用相同 k。

学习侧只证明共享候选边网络、严格残差公式、shadow/assist 和 fail-safe fallback
可执行。当前无真实轨迹训练集、checkpoint、未见 seed、收益对照、PPO 或大规模训练
验收；gymnasium/stable_baselines3 未安装。后续必须由 main 接入 scalable simulation
总线并由 D6 做多 seed 非退化、时延和物理结果统计后，才能更新能力等级。

## 2026-07-20 200×200 性能与区域合同验收

### 实验设置

性能样本固定为 200 个资源、200 个目标和每目标最多 32 条候选边。旧参考路径与向量化
路径在同一 Python 进程、同一输入上各运行 5 次，以中位耗时比较。验收要求两条路径
均完成 200 个分配，规则语义对照一致，新路径不再逐个调用全部 40,000 条 Python 边
规则。原始结果记录在 `results/scalable_3d_assignment_benchmark_20260720.json`。

| 路径 | 中位耗时 | Python 全边规则调用 | 完整解释物化 | 候选边 | 分配数 |
|---|---:|---:|---:|---:|---:|
| 旧参考路径 | 1904.261 ms | 40,000 | 40,000 | 6,400 | 200 |
| 向量化稀疏路径 | 85.367 ms | 0 | 6,400 | 6,400 | 200 |

中位加速为 22.307 倍。另用 20 个目标、23 个资源逐边比较矩阵、候选掩码、拒绝原因和
候选解释，浮点容差设为 `1e-11`，结果通过。该基准没有包含 D1、D2、D4-D7、网络、
AirSim 或控制循环，因此不作为系统实时指标。

区域合同专项现有 18 个测试，覆盖同一计划中的两个 secondary owner、secondary 和
distributed k=1、D4 `single_member_authorized` summary、单成员无授权、证据过期、
owner/epoch/member 不一致、错误 atomic/commit-required 标记、grant 禁止执行、重复
资源，以及 distributed k=3 committed、缺 ACK、旧 epoch、grant 过期和 stale source。
稀疏求解专项同时覆盖两个
不连通候选分量和无候选目标。D3 全量共收集 194 项，结果为
`193 passed, 1 skipped`，接受阈值为零失败；唯一跳过项为未安装的可选 OR-Tools 对照。

k=1 正例的 assignment metadata 为 `commit_required=False`、模式
`single_member_authority`。无 summary 时 state 为 `single_member_authority`；D4 提供
有效 summary 时 state 为 `single_member_authorized`，且 evidence-present 为真。k=3
正例仍为 `commit_required=True`、模式 `atomic_coalition_commit`、state committed。
该结果验证了合同分类，没有降低多成员全 ACK 和原子提交门限。

本批没有运行 AirSim 或多 seed。区域接口尚未由 main 接入 D4 运行时裁决，因而没有
center failure、multiple secondary owner、secondary failure 或网络分区的全栈结果。
后续验收应记录 plan version 单调性、stale 拒绝、lease 过期执行数、缺 ACK 执行数和
每阶段耗时，再由 D6 汇总。

## 2026-07-20 故障代际 Fence 确定性验收

本批针对 50v50 中心故障时 `authority_generation_not_advanced` 阻塞增加 D3 模块级
测试。测试使用一个显式 k=3 混合联盟，以同时检查 assignment 成员和 coalition
identity/version。没有运行 scalable 3D 全栈、AirSim 或多 seed。

| 验收项 | 门限 | 结果 |
|---|---|---|
| 单次 fence | version 严格 +1，正常 publish | 通过 |
| assignment/目标身份 | 成员和 target 不变 | 通过 |
| coalition | identity/version/成员不变 | 通过 |
| owner/授权 | 不改变 | 通过 |
| expected version 错误 | fail closed | `expected_previous_version_mismatch` |
| 连续 fence | v1 -> v2 -> v3 | 通过 |
| 重复 fence 版本 | fail closed | `authority_fence_duplicate_version` |
| 伪造 coalition | fail closed | 通过 |

新增专项测试 5 个。D3 全量共收集 199 项，结果为 `198 passed, 1 skipped`，接受门限
为零失败；唯一 skip 是未安装的 optional OR-Tools。该结果证明 D3 fence 接口和发布
门控可执行，不证明 main 已修复 50v50 故障流程。下一项系统验收是 main 在 D4 裁决前
调用 fence，并确认所有区域不再出现 `authority_generation_not_advanced`。

## 2026-07-20 可复现学习管线 Synthetic Smoke（Legacy v1）

### 设置与门限

本节记录旧 `d3_learning_dataset_v1` / `d3_scenario_seed_group_split_v1` 的历史开发
smoke，不是当前 v2 证据。该批未运行 AirSim、未使用 truth actor ID、未提交正式权重。
固定 30 个 seed、每 seed 1 episode/2 frame；旧 split 按 `scenario_version + seed` 哈希，
实际 train/validation/test seed 为 `23/1/6`，frame 为 `46/2/12`。

接受门限如下：

| 项目 | 门限 |
|---|---|
| split | legacy v1 同一 scenario/seed 不得跨 split |
| BC | final train loss < initial，validation loss 有限 |
| PPO | policy/value/entropy/KL/clip/gradient 指标均有限 |
| mask/solver | duplicate=0、hard violation=0、mask 外动作不可生效 |
| bundle | SHA/feature/policy/version 错误必须回退规则；weights-only load |
| promotion | 至少 20 未见 test seed，且零 fallback、安全/成本非退化 |

### 结果

| 阶段 | 样本/配置 | 结果 | 本地耗时 |
|---|---|---|---:|
| dataset | 30 seed、30 episode、60 frame | split hash 可复算，无 seed 泄漏 | 0.375 s |
| BC | 5 epoch、8-frame mini-batch | train `1.1001 -> 0.5014`；validation `0.3768` | 0.920 s |
| PPO | 46 transitions、1 update、2 optimization epoch | 所有更新指标有限；smoke clip fraction=0 | 0.132 s |
| shadow | 6 test seed、12 frame | fallback=0、duplicate=0、hard violation=0 | 0.006 s |

legacy shadow inference P50/P95 为 `0.281/0.350 ms`。安全非退化为 true，但 assignment-cost
非退化为 false；同时 test 只有 6 个未见 seed，且数据源是 synthetic。因此 promotion
manifest 为 `promotion_recommended=false`、`promotion_status=unavailable`、reason
`evidence_source_not_promotion_eligible`。v2 loader/bundle 会稳定拒绝该产物；这不是当前
模型收益证据。

专项测试共新增 16 项：dataset/bundle 8 项、PPO/shadow 7 项、四命令 CLI 1 项。覆盖
3v5、5v3、200 candidate edge shape、整 seed 泄漏拒绝、BC loss、PPO clipped-ratio、
mask 外动作拒绝、bundle missing/SHA/feature/policy mismatch、version fallback、shadow
规则矩阵不变、少于 20 seed 拒绝和 20-seed gate 正例。最终全量测试结果在本轮复验后
为 `214 passed, 1 skipped`，共收集 215 项、耗时 6.95 s；接受门限为零失败，唯一
skip 是 optional OR-Tools installed-only case。

### 尚缺正式证据

- truth-isolated 真实 D2/D3 连续轨迹和反馈标签；
- 至少 20 个完全未参与训练、归一化、阈值选择的真实或高保真 test seed；
- 目标增删、资源失效、3v5/5v3、M-to-N demand 变化及 stale/timeout/OOD 故障注入；
- CPU/GPU P50/P95/P99、可抢占 timeout、confidence/OOD calibration；
- paired assignment cost、高威胁 unmet、churn 和系统物理结果全部非退化。

在这些条件满足前，assist 不得晋级；默认继续使用规则 Hungarian/demand-slot。

## 2026-07-20 数值 Seed 隔离 v2 软件合同验收

### 设置与门限

本批只运行 D3 单元和全量回归，不运行 AirSim、不训练新模型、不比较拦截或 assignment
性能。dataset fixture 使用 8 个唯一数值 seed；每个 seed 同时出现在 2v2/5v5 风格的两个
scenario/scale 中，每个 scenario 含两个 episode、每 episode 两帧。相同记录分别按正序、
逆序和逐行 iterator 输入 finalize。

| 验收项 | 门限 |
|---|---|
| seed 原子性 | 同一数值 seed 的全部 scenario/scale/episode/frame 只有一个 split |
| split 隔离 | train/validation/test 数值 seed 集合两两零交集且均非空 |
| 数量门 | 少于 3 个唯一 seed 或 test 少于声明 unseen 数必须失败 |
| 确定性 | 正序/逆序的 canonical frames、split hash、frame SHA 和 manifest 完全一致 |
| 篡改/版本 | 修改 frame/split/hash、冲突预分配、dataset v1、bundle v1 均稳定拒绝 |
| 下游 | BC/PPO/shadow 先验证完整三分；whole-seed/unseen 按数值 seed 跨 scenario 计数 |

### 结果

专项正负例全部通过。D3 全量收集 244 项，结果为 `243 passed, 1 skipped`，接受门限为
零失败；唯一 skip 是环境未安装 optional OR-Tools 的 installed-only benchmark。schema
结果为 `d3_learning_dataset_v2`、`d3_numeric_seed_atomic_split_v2`、
`d3_learning_model_bundle_v2` 和 `d3_shadow_paired_evaluation_v2`。这是软件合同结果，
不表示模型 loss、成本、时延或物理拦截性能改善。

写出边界另用一个 dense 200v200 fixture 量化：40,000 candidate edge，单帧 canonical
JSON 5,854,691 bytes，NumPy payload 加 edge tuple 浅层约 5,161,640 bytes。D3 writer
已改为 iterator + 磁盘 payload + SQLite 索引 + 增量 SHA；当前 scalable main 已直接传入
iterator，不再执行全量 `read_text().splitlines()`。正式批量最坏容量仍待 main 验收。

## 2026-07-20 单帧规划证据确定性验收

### 设置与门限

本批只运行 D3 单元/回归测试，不运行 AirSim，不导出真实 seed。新增测试直接调用
`AssignmentPlanner.plan()` 和 `plan_regional_authority()`，构造包含 truth/actor/object
metadata 的输入，检查 retained evidence 不出现原 ID；同时覆盖 mutable input、只读
matrix/mapping、失败调用替换旧帧和公开 frame helper。

接受门限为：默认 Hungarian assignment/版本结果不变；rule/effective 与实际 learning
模式一致；shadow proposal 不进入 solver；fallback effective 逐元素等于 rule；所有
失败路径不返回陈旧 payload；动态 roster shape 不固定；全量零失败。

### 结果

| 验收项 | 样本 | 结果 |
|---|---|---|
| regular lifecycle | initial、held、unchanged、forced-replan ack、stale | 通过；timestamp/previous version 对应当前 tick |
| learning matrix state | shadow、assist、low-confidence fallback | 通过；三类矩阵/状态明确分离 |
| solver fallback | SciPy disabled | `fallback_dp` 可审计，规则矩阵不变 |
| regional authority | 1 个有效、1 个 target-set mismatch | 有效帧可记录；拒绝后 unavailable 且无旧 payload |
| 隔离 | 原输入 metadata、plan/record 外部修改 | retained snapshot 不受影响；无原 truth/actor/object ID |
| 动态规模 | 1x3、3x2、7x4 | matrix 和 snapshot shape 均跟随输入 |
| 公开 helper | scenario/seed/episode/frame index | 生成既有匿名 `LearningFrameRecord` |

专项测试 11 项全部通过。D3 全量共收集 226 项，结果为
`225 passed, 1 skipped`；接受门限零失败达到，唯一 skip 是环境未安装 optional
OR-Tools 的 installed-only benchmark。该结果只证明 D3 recorder API 与 fail-closed
生命周期，尚无 main 集成、真实 episode frame 数、真实 seed split、AirSim outcome 或
shadow non-degradation 数据。

## 2026-07-20 区域资源提示候选约束确定性验收

### 设置与门限

本批使用 D3 本地 pytest fixture，不启动 AirSim，不运行性能 benchmark。输入覆盖普通
1-to-1 和 `required_resource_count=2` 的 M-to-N；构造 A/B 两区域、上一计划已承诺成员、
空闲源区资源、目标区资源失效、reserve ratio、D5 hard edge 和 learning assist。seed
不适用。接受门限为：无提示求解同解；合法提示真实改变 candidate edge；每 route actual
不超过 allowance；committed/coalition/reserve 不被 transfer；非法提示 reason 非空且
结果等于同帧无提示基线；全量零失败。

### 结果

| 验收项 | 样本 | 结果 |
|---|---|---|
| DTO/mapping | frozen、未知字段、truth/actor/object identity | 严格解析和拒绝 reason 通过 |
| 无提示 | 隐式缺省与显式 `None` | assignment、成本、solver 和候选数一致 |
| 1-to-1 transfer | A -> B allowance=1 | 原 region-incompatible 资源成为候选并被 Hungarian 选择；actual=1 |
| 非法/过时提示 | source、expiry、region、conservation、transfer net、projected、lease、truth | 8 类均回退原规则且 reason 明确 |
| commit/reserve | previous assignment + post-quota reserve | 超额 transfer 整体拒绝 |
| M-to-N | simultaneous k=2、allowance=2 | 两个跨区成员组成 complete coalition；actual=2 |
| D5 + learning | 1 条 hard edge、assist residual | hard edge 未恢复，另一许可边进入 Hungarian，learning 正常执行 |

新增 14 个 case 全部通过。D3 全量收集 240 项，结果为
`239 passed, 1 skipped`，接受门限为零失败；skip 是 optional OR-Tools installed-only
case。该结果证明 D3 DTO、候选约束、fallback 和审计合同，不证明 main 已接入 D4，也
没有正式多 seed、AirSim 时延/非退化或物理拦截结果。

## 2026-07-20 Learning 数据与 Promotion 安全负例验收

### 设置与门限

本批只运行 D3 pytest，不启动 AirSim，也不训练或发布模型。接受门限为：训练入口对
test frame 零消费；BC 训练期指标不含 test seed；递归 identity/未知 frame 字段全部拒绝；
candidate hint 不能恢复 hard reject；assist 只接受 eligible 正式 test paired evidence，
dataset split/frame/model 三摘要完全匹配；rule/proposal 非退化在同一
`rule_cost_matrix_v1 + unassigned_costs` 基准计算；全量零失败。

### 结果

| 验收项 | 负例/样本 | 结果 |
|---|---|---|
| seed 隔离 | BC 输入 train/validation/test；PPO 输入 train/test | 训练 API 拒绝 test，BC whole-seed metric 仅含 train/validation |
| frame 真值隔离 | 顶层/嵌套 truth、actor、identity、未知扩展、数值字段 actor 字符串 | 全部 fail closed；v2 兼容字段保持显式 allow-list |
| action mask | 人为设置 `candidate_mask=True` 重开 D5/容量/冲突禁边 | 候选索引、assistant 返回和 solver mask 都继续拒绝 hard edge |
| bundle/evidence | frame SHA 错配、validation、non-eligible、promotion bypass、证据摘要/类型伪装 | assist 均回退规则 |
| cost non-degradation | residual 诱导选择较贵的规则边 | 共同 `C_rule` 重评分识别成本退化并拒绝 promotion |

D3 全量收集 252 项，结果 `251 passed, 1 skipped`；零失败达到门限，唯一 skip 是环境
未安装 optional OR-Tools。本批没有正式权重、真实 D2/D3 训练、至少 20 个未见真实/高
保真 test seed、eligible promotion 或 assist 准入结论。没有运行 AirSim，因此也不形成
模型时延、物理收益、拦截率或 200v200 全栈实验结论。

## 2026-07-20 学习帧导出微基准

### 目的与设置

本实验只测 D3 在 planner evidence 已存在之后的学习帧构造、JSONL 编解码和 dataset
finalization。输入为 200 targets、200 resources、top-32 稀疏候选；每帧 6,400 条候选
边，canonical JSONL 约 2.20 MB。finalization 使用 3 个数值 seed、每 seed 2 帧，共 6 帧。
同一进程预热后重复测量中位数；cProfile 与 Tracemalloc 另以相同 fixture 比较函数调用和
峰值。墙钟不进入 pytest 验收门限。

基线 revision 为 `98edde32fa96b4d4c618dcdaf71f004bd17d66f8`。复现实验命令：

```bash
python3 research_modules/d3_assignment_planner/simulations/run_learning_export_profile.py \
  --count 200 --max-candidate-edges 32 --frame-count 6 --repeat 5 \
  --output research_modules/d3_assignment_planner/results/scalable_3d_learning_export_profile_20260720.json
```

### 结果

| 指标 | 修改前 | 修改后 | 改善 |
|---|---:|---:|---:|
| frame build 中位数 | 0.048187 s | 0.022992 s | 2.10× |
| `to_dict + canonical json.dumps` | 0.025082 s | 0.025794 s | 无实质变化 |
| JSON decode + v2 validate | 0.095920 s | 0.056090 s | 1.71× |
| 6-frame finalize 中位数 | 0.910200 s | 0.243647 s | 3.74× |
| cProfile 函数调用 | 11,848,558 | 51,612 | -99.56% |
| 匹配 Tracemalloc 峰值 | 14,575,699 B | 12,725,690 B | -12.69% |

函数调用下降主要来自删除 finalization 内的第二轮完整 JSON 解析、递归 identity 扫描、
record 重建和重编码。frame build 收益主要来自按目标缓存 demand，以及取消重复 reject
reason 扫描。修改后 cProfile 的主要累计项为 canonical `json.dumps()`、NumPy
`tolist()` 和写盘前 record revalidation。

### 等价与边界

确定性测试证明优化结果与旧语义逐字节相同，逆序输入仍生成相同 canonical order、frame
SHA 和 manifest。构造后篡改 mask 或注入真值键仍在写正式文件前拒绝。schema、candidate
数量、规则矩阵、学习特征、split 和存储字节没有删减；九场景 D3 数据约 27.86 MB。

按本微基准估算，6 帧的 D3 frame build、首次 encode、逐行 decode/validate 和 finalize
合计约 0.87 s。该范围不含 planner 求解、D4/D5 数据构造、世界传播和 main 编排，因此
不能把 74-76 s 的总 staging 时间归因于 D3。后续总线优化应使用 main 的分模块 stage
计时。本批没有运行 AirSim、训练模型或生成物理收益证据。

新增确定性和微基准结构测试后，D3 全量收集 255 项，结果为
`254 passed, 1 skipped`；唯一 skip 是 optional OR-Tools，零失败满足门限。

## 2026-07-20 Clean-tree 200v200 三 seed 复测

### 设置

main 使用 nominal 200v200 配置运行 seed 930、931、932，每个 episode 时长 2 s。基线产物
为 `capacity_probe_v2/nominal_timed`，优化后产物为
`capacity_probe_v2/nominal_timed_postopt`。优化后 producer commit 为
`4052d9411363c39d52100c0e3a4f60ee88443cab`，生成计划与汇总均记录
`repository_dirty=false`。该批 `formal=false`，用于容量与耗时复核。

### 总体结果

| 指标 | 基线 | 优化后 | 变化 |
|---|---:|---:|---:|
| episode run | 125.2205 s | 127.9871 s | +2.7666 s |
| artifact staging | 225.9243 s | 126.4682 s | -99.4561 s |
| D3/D4/D5 联合 finalization | 116.5624 s | 7.7377 s | -108.8247 s |
| 总生成 | 467.8007 s | 262.2866 s | -205.5141 s |

episode run 基本保持，时间下降集中在 staging 和联合 finalization。联合 finalization 是
D3、D4、D5 的汇总字段，不能全部归因于 D3。

### D3 分项

| seed | D3 stage | 导出帧数 | 在线真值使用 |
|---:|---:|---:|---:|
| 930 | 0.0917 s | 2 | 0 |
| 931 | 0.1129 s | 2 | 0 |
| 932 | 0.0999 s | 2 | 0 |

D3 最终数据集共 6 帧，train、validation、test 各 2 帧，manifest 正常生成。该结果证明
D3-owned 重复编码和最终化热点已经关闭，并已在 main 的三维质点生成链中生效。它没有
证明模型收益、AirSim 性能或物理拦截效果。

### 剩余工作

本节形成时正式 schedule 尚未执行。其后 900 episode 与 BC 开发训练已完成，见第 16 节。
PPO、外部保留 seed 1000-1019、AirSim 收益和 assist promotion 仍未完成。后续报告继续
分别列出 D3 stage 与联合 finalization，避免跨模块误归因。

## 16. 正式 900 Episode 行为克隆开发实验

### 16.1 输入与审计

实验使用三维规模化仿真的正式 D3 数据。文件只读，未原地修改。

| 指标 | 结果 |
|---|---:|
| episode | 900 |
| frame | 1604 |
| 数值 seed | 100 |
| train/validation/internal-test frame | 962/320/322 |
| train/validation/internal-test seed | 60/20/20 |
| 候选边 | 3658815 |
| 规则已选边 | 117304 |
| 外部 seed 1000-1019 重叠 | 0 |

frames SHA256 为 `6761d35d...fdb59a2`，split hash 为 `679a9051...70a2`。schema、完整
文件哈希、分割重算、episode/seed 原子性和 5/20/50/100/200 覆盖全部通过。

### 16.2 配置

训练日期记录为 2026-07-20。随机 seed `20260720`，12 epoch，mini-batch 8，hidden size
64，Adam 学习率 0.001，正类权重上限 16，PyTorch CPU 线程 4。残差 `alpha=0.25`，开发
shadow 的 confidence 下限设为 0，OOD 阈值 6σ，deadline 50 ms。confidence 下限为 0 只
用于观察原始模型提案；v3 admission 禁止 assist。

训练 loss `1.083713 -> 0.468781`，validation loss `0.469243`。训练 23.81 s，开发评估
8.42 s，总 wall 73.43 s，峰值 RSS 1577868 KiB。

### 16.3 三分结果

| 分割 | 残差平滑 L1 | 排序 AUC | 计划一致率 | 成本均值差 | 需求满足率 | duplicate | 硬违规 | 推理 P95 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| train | 0.321209 | 0.7999 | 0.6705 | +0.021641 | 0.969966 | 0 | 0 | 2.516 ms |
| validation | 0.320446 | 0.8097 | 0.6750 | +0.020823 | 0.973180 | 0 | 0 | 2.500 ms |
| internal-test | 0.315898 | 0.8031 | 0.6770 | +0.022345 | 0.975689 | 0 | 0 | 2.554 ms |

internal-test 的 rule-only 与 BC shadow 高威胁需求满足率均为 0.887165，平均 churn 均为
70.1149。相同指标说明学习提案没有破坏需求和抖动口径；共同规则成本轻微增加，不能写成
收益。计划一致率低于边排序 AUC，说明局部边排序变化在 Hungarian 全局竞争中会改变一部分
完整计划。

### 16.4 规模时延

| 名义规模 | frame | 模型推理 P50 | 模型推理 P95 | BC shadow 总路径 P95 | 成本均值差 |
|---:|---:|---:|---:|---:|---:|
| 5 | 320 | 0.226 ms | 0.247 ms | 0.331 ms | +0.000000 |
| 20 | 324 | 0.338 ms | 0.433 ms | 0.694 ms | +0.005758 |
| 50 | 320 | 0.707 ms | 0.860 ms | 1.531 ms | +0.015900 |
| 100 | 320 | 1.134 ms | 1.434 ms | 3.889 ms | +0.034839 |
| 200 | 320 | 2.064 ms | 2.793 ms | 10.857 ms | +0.051798 |

模型推理在当前 CPU 上低于 50 ms deadline。该值不含跨模块通信、D1-D2 更新或 D7 控制，
也不构成目标硬件时延保证。

### 16.5 回退与准入

内部 test 有 163/322 帧触发 `out_of_distribution`。原因是当前 guard 对整帧采用最大值：
任一候选边任一特征超过训练均值 6σ，整帧回退规则。大候选图和稀有离散特征会放大该
触发概率。规则回退确保 duplicate 和 hard violation 维持 0，但当前门限不适合直接用于
assist。

开发权重 SHA256 为
`e3da9fd5b54451da83358405b6051991e0c78bcf9f538b350d459b05faf8e0b2`。bundle admission 为
`development/shadow-only`，外部 1000-1019 状态为 `not_evaluated`，promotion 为
`unavailable`。`39b097e...` 记录数据生成和训练基线，训练时 D3 模块改动由独立源码
SHA256 绑定。权重保存在 ignored `outputs/`，tracked results 不含 `.pt`。PPO 未启动。

结论是正式数据和 BC 开发闭环已经跑通，模型尚未达到 assist 准入。main 后续需要使用
同一冻结 SHA 在外部 20 seed 上复核，并由 D6 独立判断成本、安全、需求、抖动、OOD 和
时延。没有这组证据时，规则 Hungarian 保持唯一默认执行路径。

代码验收执行 D3 全量测试，收集 258 项，结果 `257 passed, 1 skipped`。唯一 skip 为未
安装 optional OR-Tools 的 installed-only benchmark；正式训练入口和修改文件语法检查通过。

## 17. 共享 Seed 注册表只读验证（2026-07-21）

### 输入

本次复用第 16 节的正式 900-episode D3 数据，不重新生成样本、不训练模型，也不运行
AirSim。额外输入为 main detached shared split registry 及其 source training seed
registry。验证前记录 dataset manifest、frames 和两个 registry 文件的 SHA256。

### 结果

| 检查项 | 结果 |
|---|---:|
| episode/frame | 900/1604 |
| 训练 seed | 100 |
| train/validation/internal-test seed | 60/20/20 |
| 保留 seed 1000-1019 重叠 | 0 |
| schema/policy | 通过 |
| content/assignment/source SHA | 通过 |
| D3 v2 policy 独立重放 | 逐 seed 完全一致 |
| 输入文件前后 SHA | 完全一致 |

registry file SHA 为 `68608d29...032f`，content SHA 为 `29eb6895...f146`，assignment SHA
为 `31c6a3fc...6ab5`，source registry SHA 为 `2ab928a4...15f`。dataset frame SHA 和
split hash 仍为 `6761d35d...fdb59a2` 与 `679a9051...70a2`。

新增 12 个测试覆盖正确 fixture、schema/policy 篡改、content/assignment 篡改、有效自哈希
但映射变化、source SHA 不同、缺 seed、多 seed、保留 seed、跨 split、路径参数成对、原
文件零修改和新 bundle binding。D3 全量为 `269 passed, 1 skipped`。

该结果关闭 D3 对 C1 shared split 的验证缺口，不改变第 16 节的模型结论。现有权重未重训、
未改写，仍是 `development/shadow-only`。外部保留 seed 没有参与模型评估，PPO 未启动。

## 18. 正式分配数据全样本审计（2026-07-21）

### 实验对象

审计对象为正式三维质点生成批次中的 D3 分配数据。源数据包括 900 个场景 episode 和
1604 个决策帧，帧文件约 883 MiB。审计器按行读取全部帧，并绑定数据清单、两个 seed
注册表、生成摘要、episode 进度和批量导出摘要。审计过程中没有训练模型、运行 PPO、
生成权重或启动 AirSim。

### 计数结果

| 计数单位 | 训练 | 验证 | 测试 | 合计 |
|---|---:|---:|---:|---:|
| 规范数值 seed/episode 身份 | 60 | 20 | 20 | 100 |
| 实际场景 episode | 540 | 180 | 180 | 900 |
| 决策帧 | 962 | 320 | 322 | 1604 |
| 候选边/动作标签 | 2229182 | 721445 | 708188 | 3658815 |
| 规则选中动作 | 71425 | 23147 | 22732 | 117304 |

全部 43905780 个候选特征值通过有限性检查。匿名目标记录 118109 条，匿名资源记录
120080 条。容量违规、需求槽违规、动作索引违规、seed/episode 泄漏、前序版本回退、
非法 `global_track_id` 字段、在线真值使用和脏 episode 均为 0。900 个 episode 的有限状态
记录齐全。进度文件保留 194 个未导出帧原因，其中权威代次围栏无成本帧 120 次、已发布
计划无匹配成本帧 74 次；审计没有补入旧帧。

### 完整性与结论

7 个源文件审计前后 SHA256 一致。正式 manifest SHA256 为
`816fe6e965d4f8d790e89a00a7c90e28bb8cd08a257fe685790669ab774a9089`，frame SHA256 为
`6761d35d6b48639a5eb4f3306f7b3f12ca72352a1028296a0c39a4b90fdb59a2`。审计 JSON 文件
SHA256 为 `62a47df8058c0238498f2181229a5f6d45f6d958799eda354f03e25ea24b17fb`，规范内容
SHA256 为 `954f3e96d563412644ec88d1b621e2a58c781af8af99de79b859d22079fc1867`。

数据结构状态为 `complete`，总体状态为 `partial`。当前计划 owner/current version、真实
applied ACK、outcome 归因、因果/反事实 reward 和同 seed paired shadow 都未携带。
`reward_components` 仅是规则教师诊断，不能作为运行时 reward。默认规则代价和需求槽
匈牙利不变，PPO、assist 和在线权限继续关闭。

专项测试覆盖正常数据、非有限值、split 错误、truth 泄漏、版本/索引/容量错误、文件篡改、
描述文件哈希变化和输出路径保护。D3 全量收集 280 项，结果 `279 passed, 1 skipped`；
唯一 skip 为可选 OR-Tools 安装检查。

## 30. 运行计划 ACK 验证试验（2026-07-21）

本次试验验证 D3 能否在不依赖 main Python 包的条件下，复核 main 发布的运行计划确认。
专项用例构造两资源协同指向同一中心航迹的 M-to-N 计划，覆盖 primary、reserve、联盟
版本、一个中段导引命令和一个 hold 命令。验收门限为所有正例通过、所有篡改负例失败
关闭、`AssignmentPlan` 与输入 mapping 前后不变。

专项共 24 项，全部通过。负例覆盖错误 ACK schema、D3/D7 来源 SHA、旧 plan version、
非正来源 sequence、重复/缺失/额外 binding、ACK 和来源计划的中心航迹替换、错误
fully-bound、自报物理 outcome、自报 reward、非有限时间、shadow 冒充 applied，以及
非约束鸭子类型。另以正例覆盖顶层 consumer 对 namespaced plan、namespaced consumer
对顶层 plan 两种导入组合。序列化结果通过 `json.dumps(..., allow_nan=False)`。

自动化真实 main 集成测试使用当前三维集成栈运行 3v3、seed 7、1.2 秒。总线产生 2 条
`runtime.assignment_plan_ack`；测试通过公开 consumer 验证最后一条 ACK。最终计划版本
1，assignment=3、binding ACK=3、control-applied=3、held=0、fully-bound=true，在线
真值使用为 0。最终 ACK 的学习 mode 为空，验证器输出 runtime learning applied ACK
unavailable；物理 outcome 和 reward 也为 unavailable。consumer 源码不导入 main，
main 集成栈只在 D3 测试中导入。该场景是三维质点软件测试，不是 AirSim 或实飞试验。

D3 全量收集 304 项，结果 `303 passed, 1 skipped`，唯一 skip 为 optional OR-Tools。
冻结正式数据仍是 900 episode、1604 决策帧，生成时间早于 ACK producer，因此正式逐样本
ACK 覆盖率仍为 0。当前结论只证明验证接口和新 producer 的小规模对接可用，不证明学习
动作收益、物理拦截结果或 reward 归因。

## 运行窗口归因合同验证（2026-07-21）

### 目的

本次验证检查 D3 是否能把一个已验证的计划 ACK 与 D6 的离线观测窗口严格连接，同时避免
把命令、相邻状态变化或五米事件误写成因果奖励。没有启动 PPO，没有加载 assist，也没有
改变 Hungarian、代价残差公式和安全外壳。

### 样本与门限

| 项目 | 设置或门限 |
|---|---|
| 专项单元测试 | 16 项，要求零失败 |
| 集成样本 | 三维质点 3v3，seed 41，1.2 秒 |
| 在线真值使用 | 必须为 0 |
| 来源关系 | D3 source sequence < D7 consumption sequence < ACK sequence |
| 窗口 | 同资源不重叠，版本和刷新语义一致 |
| 正式奖励 | 配对、反事实、因果证据缺失时必须 unavailable |
| 学习权限 | PPO/assist/authority 必须 false，规则回退必须 true |

### 结果

专项结果为 `16 passed`。真实 main 集成样本由当前 runtime 自动生成 D3 计划、D7 命令、
ACK 和 D6 `runtime_plan_outcome_join.json`。D3 对最后一条 ACK 的一个 active binding
完成来源、消费、ACK、owner、资源-航迹、执行签名和时间窗联接，在线真值使用为 0。
输出中 command 和 ACK applied 可用；观测诊断按 D6 实际状态保留；paired、
counterfactual、causal 和 formal reward 均不可用。

D3 全量收集 320 项，结果 `319 passed, 1 skipped`。唯一 skip 是当前环境未安装的可选
OR-Tools 对照。冻结 900 episode/1604 帧正式数据没有新 ACK，本次没有修改或回填这些
文件。

### 判断

ACK 到 observed outcome 的合同断点已关闭。正式 reward 仍缺计划级运行分项、同 seed
配对结果、反事实和因果证据，因此尚不能启动 PPO。五米事件和距离改善可用于诊断窗口
是否有结果，不用于宣称分配策略收益。
