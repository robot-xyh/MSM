# D4 分布式降级与接管实验报告

## 1. 实验边界

本报告覆盖两类离线降级逻辑：中心节点失效后的被动降级连续性仿真，以及中心节点未失效但局部不确定性升高时的主动降级仲裁规则测试。节点通过内存网络交换粗粒度摘要，不涉及真实无线通信、火控参数、毁伤逻辑、实机飞控、硬件驱动、自动处置或绕过人工授权的流程。

2026-07-15 AirSim 证据严格限定为已完成的 20 个真实 M5N2 case。2026-07-20 D4-owned 证据包括 23 个区域 authority 合同测试、原 32 个区域资源建议/学习管线测试和新增 15 个 next-cycle advisory 消费合同 case；main-owned scalable 3D 定向接口测试为 8/8。新增 15 项是确定性纯 Python 合同/接口测试，无随机 seed，不是正式多 seed、AirSim、真实网络、硬件或长时运行证据。本轮没有启动新 AirSim episode。终止命令生效前额外完成的 `png_ttc_2v2_seed001` 不纳入 M5N2 聚合；其余 tuned case 未执行，dropout case 完成数为 0，缺失项保持 unavailable。

## 2. 实验目的

D4 验证中心节点异常时的保底策略：

- 使用 `C2Health` 状态机判断 `normal/degraded/suspect/failed`。
- 正常状态由中心节点统一融合、分配和发布计划。
- 中心节点失效后，优先降级到高空系留侦察无人机等二级节点，由二级节点作为区域协调者。
- 二级节点失效或不可用时，才进入完全无中心的 CBBA 风格协商。
- 优先考虑备份节点、二级侦察节点、lease 优先级和覆盖小区。
- 中心恢复后不允许靠单次心跳直接回到 normal，必须经过双轨合并和人工确认。
- CBBA 未收敛时只输出审计信息，不发布有效 assignment。
- 中心节点未失效但 D1/D2/D3/D5 风险升高时，由 `ActiveDegradationArbiter` 判断继续中心计划、请求中心重分配、请求二级节点辅助或安全保持；不转移 plan owner。

## 3. 二级节点降级层级

本阶段假设存在若干高空系留侦察无人机，作为区域二级节点。二级节点具备更稳定的视场和更大的通信覆盖，但在本模块中只作为离线协调与观测摘要源，不代表真实通信、控制或执行链路。

降级顺序为：

```text
中心 C2 正常
  -> 中心失效：二级侦察节点接管局部区域协调
  -> 二级节点失效或不可用：集群代表 / CBBA 完全无中心协商
  -> CBBA 不收敛：保持/继续观测/安全回退的离线状态
```

`ResourceSummary.node_role` 用于区分 `ground_backup`、`secondary_recon`、`cluster_representative` 和 `interceptor`。`coordinator_only=True` 表示该节点只做协调/观测摘要，不作为执行资源参与任务所有权分配。

## 4. 主动降级仲裁

主动降级不是中心被摧毁后的接管，而是中心仍在运行时的保守仲裁。D4 汇总四类输入：

- D1：`TrackUncertaintySummary`，表示定位协方差、位置标准差和量测年龄。
- D2：`AssociationRiskSummary`，表示关联 ambiguity、ID switch、重复航迹和连续性。
- D3：`AssignmentValiditySummary`，表示分配版本、是否 current、计划年龄、cost margin 和资源可行性。
- D5：`TerminalAssociationSummary`，表示末端视觉是否来自被指派 `resource_id`、是否 `locked`、是否多帧 `ambiguous/hold/reacquire`、是否与 assigned `global_track_id` 一致。

仲裁结论：

| 场景 | D4 输出 |
|---|---|
| D5 与分配目标一致，且 D1/D2/D3 风险低 | `continue_center` |
| D1/D2 风险上升但 D5 一致 | `request_secondary_assist`，请求二级节点辅助观测/cue |
| D3 分配 stale/not current 或资源不可行 | `request_center_replan` |
| 仅 cost margin 过低且 D5 一致 | `continue_center` 或请求二级 cue，继续观察 |
| D5 多帧非锁定但无观测 ID mismatch、资源错配、重复锁定或友方冲突 | `continue_center` 或 `request_secondary_assist` |
| D5 持续 global-track mismatch、资源错配或重复锁定 | 中心可用时 `request_center_replan` |
| 中心 failed，二级节点持续 ready | `degrade_to_secondary` |
| 中心 failed 且二级节点不可用/不覆盖 | `degrade_to_distributed` |
| 友方身份冲突 | `hold_for_review` |

该逻辑已由 `tests/test_active_degradation.py` 的规则测试覆盖。当前报告图表仍是被动降级/CBBA 通信退化曲线；主动降级的批量统计曲线应在后续 D6 集成后生成。

### 4.1 2026-07-15 secondary readiness/lease P0 边界验证

本次只运行 D4 Python 模块测试，未启动 AirSim。此前 278/278 验收覆盖 coordinator election、episode readiness DTO、secondary coalition proposal、resource lease 和 D6 metadata，但没有覆盖两个公开 secondary plan helper 对 sustained/source/epoch 的 `None`；此前“所有公开入口都已闭锁”的结论过度，现不再作为证据。新增矩阵对 `build_d7_secondary_handoff()` 与 `build_secondary_takeover_plan_metadata()` 逐项删除 readiness、expected/actual source、plan/required lease epoch、expiry/current time，并覆盖完整 evidence 与同一 active plan 维持正例。统一判定为仅 exact-true readiness、匹配 source、有效 epoch 且 `current_time < expiry` 的二级 plan 可 execute；interceptor peer distributed fallback 不使用二级视觉门。

验收命令为 `PYTHONPATH=research_modules/d4_distributed_fallback python3 -m pytest -q research_modules/d4_distributed_fallback/tests`，阈值为 100% 测试通过且任何不完整 readiness/source/epoch/time evidence 都不得产生 executable secondary owner。结果为 280/280 passed，满足阈值；本次样本为确定性单元测试，无 AirSim seed/episode 样本。剩余限制是未生成新的 AirSim、真实网络或物理任务证据；P1 自主成员形成、reserve 激活、补位/缩编/整盟重组也未实现。

### 4.2 2026-07-15 M5N2 中心负对照

| 项目 | 结果 | D4 解释 |
|---|---:|---|
| 完整 case | 20/20 | baseline/candidate 各 10 seeds |
| active degradation | 0 | 中心 owner 继续执行，无 secondary/distributed 动作 |
| coalition completion | 0/20 | M-to-N 联盟物理闭环未完成 |
| 第二 primary 进入 5 m | 0/20 | 第二 primary 仍是主要物理断点 |
| 第二 primary `collision_stop` | 20/20 | collision object 未记录，不能判定碰撞类型 |
| D4 main-bus mean/P95/max | 5.59/6.70/94.10 ms | 不是当前 control tick 的主要瓶颈 |

该批是负对照，不评价二级接管或完全分布式联盟性能。`collision_stop` 和 5 m 未闭合只进入诊断记录，不自动触发主动降级。D4 动作仍需 D1/D2/D3/D5 的可审计组合证据；本批没有这些降级条件，因此 `active degradation=0` 是预期行为。

验收阈值按证据域分开：中心负对照要求 `active degradation=0` 且 center owner 持续 current，本批满足；M-to-N 物理闭环要求第二 primary 进入 5 m 且 coalition completion 成立，本批 `0/20`，未满足；secondary/distributed 性能因本批未执行而标记 unavailable，不以零值替代。

### 4.3 2026-07-20 区域化 200v200 元数据与故障合同

新增 `test_regional_failover.py` 共 23 个确定性 test case。规模参数化用例分别构造 5、20、50、100、200 个 region，并为每个 region 构造一个 active task 和对应 resource metadata；这验证输入数组长度、region ownership 和 bus summary，不运行 200v200 动力学。其余 case 覆盖 scenario 声明 resource/recon 数量上限、中心健康时 D1/D2 风险只请求机动高空侦察辅助且 owner 保持 center、D3/D5 硬风险 fail closed、中心失效后二级 coverage/readiness 接管、二级失效后 distributed candidate、双区域 coverage 隔离、中心/二级/distributed `k>1` 完整/缺失 ACK、旧 ACK epoch、中心健康与 fallback 分区、旧 authority epoch/plan version、最早 task/authority lease、旧 secondary lease epoch、D5 member hold、单成员多能力与跨区域 capacity。

| 验收项 | 门限 | 结果 |
|---|---:|---:|
| 新增区域合同测试 | 23/23 | 23/23 passed |
| D4 全量测试（区域合同阶段） | 零失败 | 303/303 passed |
| 五档 metadata region/task 完整性 | 5/20/50/100/200 全部匹配 | 5/5 scales passed |
| 中心正常时 owner 转移 | 0 | 0 |
| `k>1` 缺 ACK 部分提交 | 0 | 0 |
| 旧 epoch/version、过期 lease、分区后执行 | 0 | 0 |

完整 `k=2` ACK 用例在中心、二级与 distributed 三层都只在两成员 ACK 均匹配 plan/coalition version、epoch 且最早 lease 有效后进入 `committed`；缺一 ACK 为 `aborted`，任一层级分区闭锁，已提交 coalition 遇分区转为 `reconfiguring`。该结果关闭 D4 模块内区域 authority 和安全合同；main 后续已经完成质点模块栈接口接线，但完整 CBBA/CCBBA 共识、全局组合最优性、reserve/补位/缩编/重构、AirSim、真实网络和物理拦截仍未关闭。

### 4.4 2026-07-20 区域资源建议与质点接口验证

原 `test_region_resource_advisor.py` 32 个 test case，验收阈值零失败，结果 32/32；当时 D4 全量为 335/335。参数化规模为 3、5、8、32 个区域，不固定 8 区或 200 架资源。安全用例覆盖资源守恒、最低备用、断边/网络分区、中心 owner、两个二级 owner、完全 distributed owner、旧 epoch、过期 lease、缺 ACK、fault fence 和 formal committed member 保护。研究管线用例覆盖 BC loss/update、原生 clipped PPO 有限更新、manifest/state_dict/SHA256、版本/SHA/OOD/timeout/低置信/非有限回退和 shadow formal verdict 不变。旧 split 用例只保证单个 `(scenario, seed)` group 不拆分，未证明相同数值 seed 跨场景/规模不泄漏；该缺口由 4.6 的 dataset-v1 回归关闭。

paired evaluator 的合成 19-seed case 按门槛拒绝 assist；合成 20-seed case 报告 backlog、transfer time、plan churn、communication load、fail-closed、安全违规和 candidate latency P50/P95。该 20-seed fixture 只测试 evaluator 逻辑，不是已训练模型的未见 seed 实验，不能作为 assist 推荐证据。当前仍无训练后独立 checkpoint、实际至少 20 个未见 seed paired suite、AirSim 或真实网络收益，默认保持 disabled/shadow。

同日只读运行 main-owned `scalable_3d_simulation/tests/test_module_stack.py` 为 8/8 passed。已有测试验证：单一二级接管后 D3 plan version 提升且 owner 为 `RECON-001`；两个二级节点发布多 owner 区域 plan；中心和二级连续失效后发布 distributed 区域 plan；D7 仅在当前 owner、epoch、lease、commit 和 fault fence 下继续质点导引。该结果是接口/质点证据，不写成 AirSim、真实网络或实飞结果。

### 4.5 2026-07-20 下一周期 advisory 消费合同验证

在原 32 项基础上新增 15 个 pytest case，该消费合同阶段 `test_region_resource_advisor.py` 为 **47/47 passed**，D4 全量为 **350/350 passed**，验收阈值均为零失败；当前结果见 4.6。测试覆盖：`d4-region-resource-advisory-v1` 内容寻址 ID 与 JSON 回读、`projected=true`、scenario/snapshot/authority/创建时间/source plan/policy/model identity、默认 1.0 s 且受最早 lease 限制的有效期、逐区域 owner/epoch/lease 与 reserve/committed proof、逐 transfer endpoint generation 与 edge capacity proof、下一周期首次消费及同 ID 重放拒绝、严格过期边界、旧 snapshot/plan/epoch、ACK 不完整、fault fence、非 projected、总资源不守恒、未知/非邻接 transfer、partition/edge unavailable，以及 `k>1` formal committed member 不被转出。

规则 fallback 与学习候选共用同一 `DeterministicResourceProjector` 实例；学习测试替身只生成 raw proposal，advisor 输出才为 projected recommendation/advisory contract。序列化断言确认合同不含 `global_track_id`、actor truth ID 或 target ID，也不输出目标级分配。`RegionResourceAdvisoryGate` 当前重放记录是进程内状态，main 跨进程持久化 ledger 和真实 D3 planning-loop 消费尚未实现。

这 15 个 case 没有随机 seed、AirSim episode、训练后 checkpoint、物理运动或真实网络输入，只证明 D4 合同构造和 fail-closed 消费门。它不改变上一节 main 质点接口 8/8，也不增加 2026-07-15 AirSim 20-case 结果；正式至少 20 个未见 seed paired shadow、AirSim secondary/distributed 扰动和物理连续性仍开放。

### 4.6 2026-07-20 区域学习 episode 数据合同验证

`tests/test_region_resource_dataset.py` 当前 13 个 pytest case，结果 **13/13 passed**；`test_region_resource_advisor.py` 当前 **49/49 passed**，二者合计 **62/62**，D4 全量 **365/365 passed**，验收门限均为零失败。版本固定为 `d4-region-learning-dataset-v1` 和 `d4-region-resource-model-bundle-v2`。

高基数正例仍为 96 episode/192 frame，正序和逆序输入得到相同 manifest，同数值 seed 不跨 split。复核新增：训练 target 重新验证 projector、owner/plan/version/epoch/lease、备用和 edge/quota 证明；中心、二级、distributed owner 序列化回读；manifest availability 与可重放 split 对 episode inventory 的一致性；truth/object/global-track key 变体拒绝；区域图规模增加到 200。BC/PPO 缺值仍失败关闭。

该结果只证明数据合同、确定性 split 和 fail-closed loader。96 episode 是程序生成的测试 fixture，不是 main episode writer 的正式导出，不含 AirSim 动力学或真实网络样本；本轮没有训练 checkpoint、训练/验证损失、模型优于规则、至少 20 个真实未见 seed 或性能收益结论。main 后续需把现有 frame_index/timestamp/snapshot/recommendation 流补为公开 source/frame DTO，并调用 D4 stage/finalize/load API；D4 不要求 main 解析私有 JSON 结构。

## 5. 默认被动降级场景

运行命令：

```bash
python3 research_modules/d4_distributed_fallback/scripts/run_failover_simulation.py --nodes 5 --tasks 4 --packet-loss 0.10 --seed 7
```

| 项目 | 设置 |
|---|---:|
| 节点数 | 5 |
| 连续性任务数 | 4 |
| 中心故障时间 | 30.0 s |
| heartbeat warning | 1.0 s |
| suspect 阈值 | 2.0 s |
| failed 阈值 | 4.0 s |
| 网络延迟 | 0.1-0.5 s |
| 默认丢包率 | 10% |
| CBBA round period | 0.5 s |

## 6. 样例结果

| 指标 | 数值 |
|---|---:|
| 接管开始时间 | 34.0 s |
| 接管完成时间 | 36.0 s |
| 接管耗时 | 6.0 s |
| 共识轮数 | 5 |
| 任务完成率 | 1.0 |
| transient conflict count | 5 |
| messages sent | 80 |
| messages delivered | 73 |
| messages dropped | 7 |
| estimated bytes | 22404 |

## 7. 图表与曲线

### 7.1 丢包率对降级接管的影响

![D4 丢包率与接管性能曲线](failover_packet_loss_curve.png)

图中横轴为丢包率，曲线同时展示接管耗时、共识轮数和任务完成率。它用于判断分布式降级是否在通信质量下降时仍能保守运行。若 CBBA 不收敛，当前实现会输出空的安全保持结果，而不是把不一致分配当成成功。

## 8. 结果解读

- 中心故障后，状态机先进入 `failed`，再启动降级规划。
- 当存在可用二级侦察节点时，`coordination_mode=secondary_node`，二级节点承担局部协调者角色。
- 当二级节点不可用时，系统才切换到 `coordination_mode=distributed_cbba`。
- 备份/二级节点/lease 优先级先于普通资源质量排序，可避免“能力强但不是协调节点”的资源抢占接管权。
- 非收敛 CBBA 结果不再写入有效分配，这可以防止 D6 将失败降级错误统计为完成。
- 中心恢复必须通过 `merge_recovery()` 的双轨校验和人工接受，不允许由一次 heartbeat 自动恢复 normal。
- 主动降级中，D5 与中心/二级分配一致时不会直接切到完全分布式；只有多帧末端不一致或二级节点不可用时才进入更强降级。

## 9. 结论

D4 当前适合作为“中心节点、机动高空二级侦察节点、完全分布式”三级被动降级链路，以及“中心未失效但局部证据冲突”的主动降级仲裁框架。区域 authority、secondary resource、plan、owner、epoch/version/lease 和 `k>1` 原子 ACK 已执行 fail-closed，但 bounded bid selection 不是完整 CCBBA，该模块结果也不是 AirSim/scalable3d 物理闭环或自主成员补位证明。系统应继续通过 D3/D5/D6 的统一合同传递 `plan_id/version/authorization_state`、`global_track_id`、`risk_factors` 和 `terminal_consistent`。

区域学习 dataset-v1 已补齐正式数据格式和 seed 隔离机制，但当前结论仍是“合同可用、正式数据与模型证据不可用”。bundle-v2 的 manifest/SHA 溯源不能替代 checkpoint 验收或 paired 性能报告，也不改变 D4 主动/被动降级控制逻辑。

M5N2 中心负对照已完成 20/20，但 coalition 和第二 primary 5 m 均为 0/20；这说明物理协同闭环仍开放，不说明 D4 fallback 失败。本批未执行二级或完全分布式接管，真实 secondary/distributed 多 seed 继续列为 P1。后续必须补 collision object，并运行同 seeds 的中心失效、中心与二级连续失效和可审计主动风险 paired case。
