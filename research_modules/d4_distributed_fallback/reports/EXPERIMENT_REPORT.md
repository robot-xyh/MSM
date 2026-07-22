# D4 分布式降级与接管实验报告

## 1. 实验边界

本报告覆盖两类离线降级逻辑：中心节点失效后的被动降级连续性仿真，以及中心节点未失效但局部不确定性升高时的主动降级仲裁规则测试。节点通过内存网络交换粗粒度摘要，不涉及真实无线通信、火控参数、毁伤逻辑、实机飞控、硬件驱动、自动处置或绕过人工授权的流程。

2026-07-15 AirSim 证据严格限定为已完成的 20 个真实 M5N2 case。2026-07-20 D4-owned 证据包括区域 authority、区域资源建议和 next-cycle advisory 消费合同测试；main-owned scalable 3D 定向接口测试为 8/8。2026-07-21 增加正式数据审计、共享切分、区域动作覆盖课程和区域建议运行时确认接口。新增证据均为确定性纯 Python 合同验证，不是 AirSim、真实网络、硬件或长时运行结果。本轮没有启动新 AirSim episode。终止命令生效前额外完成的 `png_ttc_2v2_seed001` 不纳入 M5N2 聚合；其余 tuned case 未执行，dropout case 完成数为 0，缺失项保持 unavailable。

2026-07-21 又增加区域结果/奖励证据合同测试。19 个新增用例覆盖新执行计划、同代评估刷新、分项缺测不补零、ACK 缺失、旧 generation、租约过期、窗口重叠、执行与联盟绑定变化、快照/来源哈希篡改、在线真值字段和 D6 目标级诊断误用。新增专项 19/19，ACK 与奖励证据专项 52/52，D4 全量 449/449。测试使用单区域确定性 fixture，不是多 seed 性能试验。它证明 schema、公式和失败关闭逻辑可运行，没有提供正式 episode 的实际区域 reward、策略收益、物理执行或因果证据。

同日增加保留 seed 配对干预合同、冻结候选只读加载和候选门诊断。arm evidence 升级为 v2，保存 candidate confidence、冻结最小置信门、OOD、latency/limit、finite 和逐项 gate；v1 reader 在验证旧 manifest content ID 后迁移，未知诊断保持 unavailable。专项现为 33/33，D4 全量 482/482。当前权威 `formal_7891296` 已生成 nominal 5v5 seed 1000-1019 的正式 v2 execution receipts；D4 仅做只读复核，不改写该输出。2026-07-22，D6 在 `research_modules/d6_evaluation_metrics/outputs/reserved_seed_interventions_nominal_5v5_1000_1019_formal_7891296_d6_profile_bound_v2_audit_20260722/` 生成 profile-bound v2 outcome-availability sidecar，状态为 `pass_offline_assignment_comparison_only`；sidecar 文件 SHA256 为 `f3852251daf02ec87fe878e7fb80aad6f381d8c0756a5c956a32e737a3871c3b`，规范内容 SHA256 为 `c02a345c46ddc642dea7fb6bfcfb24184e7dc2a9f35b754c90324d074b445d2d`。该 sidecar 只使同帧离线分配比较可用；`formal_twenty_seed_performance_completed=false`，runtime ACK、物理结果、paired effect/non-degradation、counterfactual 和 causal 均保持 unavailable。

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

paired evaluator 的合成 19-seed case 按门槛拒绝 assist；合成 20-seed case 报告 backlog、transfer time、plan churn、communication load、fail-closed、安全违规和 candidate latency P50/P95。该 20-seed fixture 只测试 evaluator 逻辑，不是已训练模型的未见 seed 实验，不能作为 assist 推荐证据。后续虽已生成开发 checkpoint，但实际至少 20 个未见 seed paired suite、AirSim 或真实网络收益仍未形成，默认保持 disabled/shadow。

同日只读运行 main-owned `scalable_3d_simulation/tests/test_module_stack.py` 为 8/8 passed。已有测试验证：单一二级接管后 D3 plan version 提升且 owner 为 `RECON-001`；两个二级节点发布多 owner 区域 plan；中心和二级连续失效后发布 distributed 区域 plan；D7 仅在当前 owner、epoch、lease、commit 和 fault fence 下继续质点导引。该结果是接口/质点证据，不写成 AirSim、真实网络或实飞结果。

### 4.5 2026-07-20 下一周期 advisory 消费合同验证

在原 32 项基础上新增 15 个 pytest case，该消费合同阶段 `test_region_resource_advisor.py` 为 **47/47 passed**，D4 全量为 **350/350 passed**，验收阈值均为零失败；当前结果见 4.6。测试覆盖：`d4-region-resource-advisory-v1` 内容寻址 ID 与 JSON 回读、`projected=true`、scenario/snapshot/authority/创建时间/source plan/policy/model identity、默认 1.0 s 且受最早 lease 限制的有效期、逐区域 owner/epoch/lease 与 reserve/committed proof、逐 transfer endpoint generation 与 edge capacity proof、下一周期首次消费及同 ID 重放拒绝、严格过期边界、旧 snapshot/plan/epoch、ACK 不完整、fault fence、非 projected、总资源不守恒、未知/非邻接 transfer、partition/edge unavailable，以及 `k>1` formal committed member 不被转出。

规则 fallback 与学习候选共用同一 `DeterministicResourceProjector` 实例；学习测试替身只生成 raw proposal，advisor 输出才为 projected recommendation/advisory contract。序列化断言确认合同不含 `global_track_id`、actor truth ID 或 target ID，也不输出目标级分配。`RegionResourceAdvisoryGate` 当前重放记录是进程内状态，main 跨进程持久化 ledger 和真实 D3 planning-loop 消费尚未实现。

这 15 个 case 没有随机 seed、AirSim episode、训练后 checkpoint、物理运动或真实网络输入，只证明 D4 合同构造和 fail-closed 消费门。它不改变上一节 main 质点接口 8/8，也不增加 2026-07-15 AirSim 20-case 结果；正式至少 20 个未见 seed paired shadow、AirSim secondary/distributed 扰动和物理连续性仍开放。

### 4.6 2026-07-20 区域学习 episode 数据合同验证

`tests/test_region_resource_dataset.py` 当前 15 个 pytest case，结果 **15/15 passed**；`test_region_resource_advisor.py` 当前 **51/51 passed**，二者合计 **66/66**。共享切分、动作覆盖课程、全样本准入和运行时确认阶段分别达到 381/381、387/387、397/397 和 430/430。加入 19 项区域 reward 合同和候选门诊断回归后，2026-07-21 当前全量为 **482/482 passed**。版本固定为 `d4-region-learning-dataset-v1`、`d4-region-resource-model-bundle-v2` 和 `d4-region-resource-observational-reward-v1`。

高基数正例仍为 96 episode/192 frame，正序和逆序输入得到相同 manifest，同数值 seed 不跨 split。复核新增：训练 target 重新验证 projector、owner/plan/version/epoch/lease、备用和 edge/quota 证明；中心、二级、distributed owner 序列化回读；manifest availability 与可重放 split 对 episode inventory 的一致性；truth/object/global-track key 变体拒绝；区域图规模增加到 200。BC/PPO 缺值仍失败关闭。

该结果只证明数据合同、确定性 split 和 fail-closed loader。96 episode 是程序生成的测试 fixture，不是正式导出，不含 AirSim 动力学或真实网络样本。正式数据、开发 checkpoint 和训练指标见 4.7；两类证据不能合并。main 后续 writer 仍需使用公开 source/frame DTO 和 D4 stage/finalize/load API，不应解析 D4 私有 JSON 结构。

### 4.7 正式数据审计与行为克隆开发训练

2026-07-20 正式数据包含 900 episode、1798 frame 和 14384 个区域动作。900 个 episode SHA256 全部通过，数据集 SHA256 为 `b06d741bd22a0cd84ef1e47a48a0b8cd81ceb7e4ea294eeeb38b892e69d36158`，split SHA256 为 `18a2c60097fefe05cb70ed811d28faf90c51bbbba0bbe984e07f23fb12f8d7f0`。训练、验证和内部测试按数值 seed 原子划分为 70/15/15，外部保留 seed 1000-1019 未进入数据。

固定随机 seed `20260720` 的复跑完成 66 epoch，最佳 epoch 54，训练耗时 66.02 秒。内部测试损失为 `0.071545`，保留比例平均绝对误差为 `0.000317`，侦察优先级平均绝对误差为 `0.000100`，端到端建议和确定性投影推理 P95 为 `0.7774 ms`。权重 SHA256 为 `3da0360be8788f3ffeb8e9f9eba3e0d5369ec0bdf9e05729dfb1db07d71d5f62`，与首次正式训练一致。

动作标签审计给出明确限制：14384 个动作中的非零配额、跨区域转移、保持和请求重规划数量均为 0。保持与重规划表面准确率为 `0.992593`，但两类都没有正样本；配额和转移的零误差同样只反映零动作基线。D6 审计中 898/1798 帧只有无归因相邻状态转移，reward、causal 和 counterfactual 可用数均为 0。训练器没有把这些相邻状态变化改写成回报。

当前结论为“管线可用但动作多样性不足，shadow-only”。bundle admission 保存动作计数，并固定 `action_diversity_sufficient=false`、`strategy_capability_claim_allowed=false`、`reward_evidence_available=false`。内部测试低损失不能用于宣称调度策略能力。没有 D6 可验证回报和外部 20-seed paired shadow 结果前，PPO 与 assist 均不可用。权重只保存在 ignored `outputs/`，文本结果仅记录配置、命令、指标、SHA256 和本地定位。

### 4.8 共享 seed 切分只读审计

2026-07-21，D4 使用独立消费者读取正式 shared registry，没有导入 main runtime。校验项包括 schema/policy、D3 兼容排序、consumer contract、content/assignment SHA256、源 training-seed-registry SHA、100 个 dataset seed 的完整覆盖、无额外 seed 和保留 seed 1000-1019 隔离。正式视图结果如下。

| 项目 | 原 D4 split | canonical view |
|---|---:|---:|
| 训练 seed | 70 | 60 |
| 验证 seed | 15 | 20 |
| 测试 seed | 15 | 20 |
| 训练 episode | 630 | 540 |
| 验证 episode | 135 | 180 |
| 测试 episode | 135 | 180 |
| 训练 frame | 1258 | 1079 |
| 验证 frame | 270 | 359 |
| 测试 frame | 270 | 360 |

数据集 SHA256 为 `b06d741bd22a0cd84ef1e47a48a0b8cd81ceb7e4ea294eeeb38b892e69d36158`；原 split SHA256 为 `18a2c60097fefe05cb70ed811d28faf90c51bbbba0bbe984e07f23fb12f8d7f0`；源 registry SHA256 为 `2ab928a476a4430b99326f245222f058bc5be5025158134ba89b01b3dec7815f`；共享 registry content SHA256 为 `29eb6895c4aa570b068f15141cbbbfede3041519117852d1ad48e848a25af146`，assignment SHA256 为 `31c6a3fc265d088d9958f44d579d8098e2aeab06b0daa60c68452ae4c6d46ab5`。

审计前后正式 D4 dataset 目录树 SHA256 均为 `8cde5cace4bd8106e35801f6179775ae39298592f3b556f712ea857b9c496bc1`。原 manifest 和 900 个 episode 文件未改写。新增 12 项测试覆盖成功映射、BC 显式选择、哈希篡改、漏/多 seed、保留 seed 和源 SHA 不匹配；该共享切分阶段 D4 全量为 381/381。该结果只证明跨模块数据切分治理可用。PPO 仍不可用，assist 仍关闭，行为克隆性能不因重新分桶自动更新；当前全量为 482/482。

### 4.9 区域动作覆盖补充课程

2026-07-21 使用正式训练 seed 注册表和共享切分注册表生成独立课程。main 在 detached clean worktree commit `9445ed6` 上完成当前证据生成。配置为 4 个区域、17 份聚合资源、100 个数值 seed，每 seed 生成保持、请求重规划和跨区转移三帧，共 100 episode/300 frame。正式 900 episode 目录及两个 registry 文件哈希在生成前后保持不变。

| 指标 | 结果 | 验收门限 |
|---|---:|---:|
| hold 正类 | 100 | > 0 |
| request-replan 正类 | 200 | > 0 |
| 非零 quota action | 200 | > 0 |
| transfer | 100 | > 0 |
| 硬约束违规 | 0 | 0 |
| 在线真值字段 | 0 | 0 |
| 保留 seed 泄漏 | 0 | 0 |
| reward available | 0/300 | 必须为 0 |
| PPO available | 否 | 必须为否 |
| online assist available | 否 | 必须为否 |

canonical 视图为 60/20/20 seed，对应 180/60/60 frame。训练桶含 hold 60、request-replan 120、非零 quota 120、transfer 60；验证和测试桶各含 20、40、40、20。clean 数据集 SHA256 为 `7e17aba7911602c1b9e9f5b917aea97f1eeec478f03963b119fbcfc8de299e72`，view SHA256 为 `9aa28765bc6e09fd912b2899716e8f0b046d538a0cb96da610519963784cc8de`。

专项测试 6/6、该阶段 D4 全量 387/387 通过。clean 课程的 dirty episode 数为 0，180 个 canonical 训练样本可由 BC 只读 view 消费，`behavior_cloning_manifest_available=true`；PPO loader 因 reward unavailable 拒绝，assist 和 authority 仍关闭。首次 dirty 课程只保留为开发期结构审计历史。该课程只补规则 teacher 动作覆盖，不构成模型收益或 AirSim 策略证据。

### 4.10 区域调度全样本准入审计

2026-07-21 使用 `d4-region-resource-full-sample-admission-audit-v1` 对两类冻结数据执行只读、失败关闭审计。正式数据位于 `research_modules/scalable_3d_simulation/outputs/learning_generation_v1_multibatchfix/learning_dataset/d4_region`；clean supplemental 课程位于 `research_modules/d4_distributed_fallback/outputs/region_action_coverage_curriculum_20260721_clean_9445ed6/dataset`。审计不修改两类数据，不训练模型，不生成权重，也不开放 online assist 或 authority。

| 数据 | episode | frame/sample | action | train/validation/test episode | train/validation/test sample | train/validation/test action |
|---|---:|---:|---:|---:|---:|---:|
| 正式数据 | 900 | 1798 | 14384 | 540/180/180 | 1079/359/360 | 8632/2872/2880 |
| clean supplemental | 100 | 300 | 1200 | 60/20/20 | 180/60/60 | 720/240/240 |

正式数据 900/900 episode 哈希通过，1798/1798 样本数值有限且安全合同有效。补充课程 100/100 episode 哈希通过，300/300 样本数值有限且安全合同有效。两类数据的 manifest/source/schema、规范 60/20/20 切分、资源配额守恒、transfer 邻接和容量、owner/plan/epoch/lease/version 单调与有效性、保留 seed、dirty 状态和真值隔离均通过，违规数为 0。补充课程动作覆盖为 hold 100、request-replan 200、非零 quota 200、transfer 100；正式数据四类正动作仍均为 0。

`target.kind=rule` 仅表示规则教师标签，`target` 字段名不属于真值泄漏。`recommendation.projected=true` 仅说明建议通过离线确定性安全投影，不能解释为 runtime applied ACK。当前数据没有显式投影前 action mask、被拒旧 plan/epoch/lease 候选、真实 `CoalitionMemberAck`、observed outcome、可归因 reward 或同 seed paired shadow；这些证据均标为 unavailable/pending。模块内正式、补充和联合全样本状态为 complete，D6 外部准入仍 pending。

审计专项 10/10、当时 D4 全量 397/397 通过。审计内容 SHA256 为 `94f4f4bf914dde9fee0ce1d92ac491902019dd7388502fbee5f96c4edfac3e7f`，tracked JSON 文件带外 SHA256 为 `4245f1db36f1af47259554f0770e75a3fe97fcc5e9b75c1b04c83d5bfb5c9e46`。D6 需按显式 JSON 路径和该带外哈希独立复核。复核完成、真实 ACK/outcome/reward 与 paired shadow 形成前，确定性规则、lease/epoch 和安全投影仍是唯一可执行路径。

### 4.11 区域建议运行时确认接口

2026-07-21，运行时确认输出升级为 `d4-region-resource-runtime-ack-evidence-v2`。原合同专项 28/28；新增真实 main 质点集成 5/5，运行时专项合计 33/33。集成正例直接运行 5v5、seed 41、duration 1.2 s、assist `RegionResourceAdvisor`：source D3 seq=10，current D3 seq=94，consumption seq=96，D7 seq=99，ACK seq=100。初次计划在 0.25 s 发布，同 plan ID/version v1 在 1.0 s 以 `evaluation_refresh_only=true`、`execution_signature_changed=false` 完成区域建议评估刷新；payload SHA 和 binding 完整，验证器输出 `available=true`、`adoption_kind=evaluation_refresh_applied`。加入区域 reward 合同和候选门诊断回归后当前 D4 全量为 482/482。

四项集成负例分别篡改 refresh flags、在同版本中改变 coalition version、声明 `execution_signature_changed=true` 却不提升 plan generation，以及移除前序 source-plan envelope，均按稳定 code 失败关闭。手工 fixture 仍覆盖严格更新的新执行计划路径。该质点正例只证明建议在同执行方案下被重新评估和采纳；不证明新执行计划、物理结果或 reward。冻结 900 episode 没有这些 runtime 字段，`CoalitionMemberAck`、物理 outcome、可归因 reward、paired shadow、PPO、assist 和 authority 状态未改变。

### 4.12 冻结候选隔离加载与门诊断

2026-07-21，D4 对 `region_resource_bc_900_20260720/bundle` 增加只读、内容寻址的隔离加载验证。冻结 manifest SHA256 为 `dad2adbe9c36dd9ff8ee8bb3c11b1e07e66743c6f80dd8e956799208a10c05c9`，权重为 `3da0360be8788f3ffeb8e9f9eba3e0d5369ec0bdf9e05729dfb1db07d71d5f62`，训练清单为 `ff3081c8e320d9c8e1b032fb6234cd24159f0feedb1c6a706633cea6c1030dc6`。加载器同时复核 development 生命周期、shadow-only 最高模式、正式数据集和切分摘要，并在每次 raw inference 前后重新计算三文件指纹。

专项测试由 26 项增至 33 项。新增用例分别覆盖 low-confidence、OOD、timeout、nonfinite、四门组合、原 `0.6/50 ms` 边界和 v1 40-arm manifest 迁移；既有 bundle identity、pair input、authority/projection、next-cycle safety 和规则回退回归保持通过。明确拒绝码与旧 generic 汇总码可同时存在，但任何已评估单门失败都不能只留下 generic。

正式输入为 `research_modules/scalable_3d_simulation/outputs/reserved_seed_interventions_nominal_5v5_1000_1019_formal_7891296`，源验证日期 2026-07-21，D6 独立审计日期 2026-07-22，场景 nominal 5v5，源提交 `78912963b67fe86ee9a8d29186b18a9dd60c460c`。D4 对 `SHA256SUMS`、manifest、20 条 source lineage 和 40 条 arm evidence v2 做了只读复核，D6 随后按 profile-bound v2 合同独立重算。执行时延与门控汇总使用不同 P95 方法，必须分列。旧 v1 latency 只属于历史运行，不进入下表。

| 验收项 | 门限 | 结果 |
|---|---:|---:|
| 配对专项 | 33/33 | 33/33 passed |
| D4 全量 | 零失败 | 482/482 passed |
| `SHA256SUMS` 文件 SHA256 | `821f1503...72bc` | 匹配 |
| manifest SHA256 | `d6ef23b2...883c` | 匹配 |
| source lineage | 20 clean/finite，truth=0 | 20/20，20/20，0 |
| arm evidence schema | 全部 v2 | 40/40 |
| 冻结 bundle 读取前后 SHA 变化 | 0 | 0 |
| candidate considered | 20/20 | 20/20 |
| confidence min/mean/max | 诊断统计 | 0.508892953/0.563426384/0.569492280 |
| confidence 通过数 | `>=0.6` | 0/20 |
| OOD 通过数 | 全部通过 | 20/20 |
| latency 通过数 | `<=50 ms` | 20/20 |
| finite 通过数 | 全部通过 | 20/20 |
| failure gate 通过数 | 全部通过 | 20/20 |
| 执行时延 P95 | `treatment_candidate_latency_ms`，nearest-rank | 2.241315 ms |
| 门控汇总时延 P95 | `candidate_gate_summary.candidate_latency_ms`，线性插值 | 2.264415 ms |
| aggregate gate 通过数 | 全部门通过 | 0/20 |
| safe adopted | 必须由 aggregate gate 决定 | 0/20 |
| 明确阈值拒绝 | 分解到具体门 | `candidate_low_confidence`: 20 |
| generic 兼容理由 | 允许与明确理由并存 | `candidate_threshold_or_finite_gate_rejected`: 20 |
| 候选失败后规则回退 | 20/20 | 20/20 |
| PPO/assist/online authority | 全部 false | 全部 false |
| runtime ACK/outcome/causal 伪造 | 0 | 0 |

默认 `minimum_confidence=0.6` 未下调，正式 20 个 treatment 均继续规则回退，候选有效数仍为 0。bundle manifest 明确包含 `confidence_head_uncalibrated`；后续应在与训练和保留 seed 隔离的 calibration split 上报告 reliability/ECE/Brier，校准或重训 confidence head 后仍按同一 0.6 门复验。本轮没有修改 bundle、权重、manifest、当前 v2 正式输出或历史 v1 artifact，也没有开放 PPO/assist/authority。D6 availability sidecar 已形成，但 runtime ACK、post-intervention physical outcome、paired effect/non-degradation、counterfactual、causal 和故障场景降级策略效果仍不可用。nominal 5v5 只证明门控分解和失败回退，不能说明候选策略有效、优于规则或具有降级策略效果。

### 4.13 隔离 degraded rollout 合同验证

2026-07-21 本地运行 `test_region_resource_isolated_rollout.py`。测试使用单区域确定性合同 fixture，source seed 字段为 1000，但没有运行保留 seed 批次、AirSim、真实网络或质点多周期状态积分。验收目标是验证错误证据不能形成隔离候选采用。

| 验收项 | 结果 | 判据 |
|---|---:|---|
| `center_failed` 正例 | 通过 | secondary formal authority、严格新计划和隔离 receipt 一致 |
| `center_and_secondary_failed` 正例 | 通过 | distributed formal authority、严格新计划和隔离 receipt 一致 |
| `active_risk` 正例 | 通过 | 中心未失效、风险 action、严格新计划和隔离 receipt 一致 |
| 三类同代 evaluation refresh | 通过 | refresh 可记录，candidate adoption 必须为 false |
| 同版本、不同 plan ID | 拒绝 | 既非同身份 refresh，也不是严格更高版本 |
| 被动降级故障前 authority 作为 source | 拒绝 | source 必须匹配 formal secondary/distributed ownership |
| 低置信候选 | 通过 | `0.59 < 0.6`，仅规则 fallback 计划可继续 |
| 缺 ACK / receipt replay | 通过 | applied 和 candidate adoption 均为 false |
| 旧 epoch / 到期 lease / owner 篡改 | 通过 | authority gate 拒绝 |
| plan 或 ACK binding 篡改 | 通过 | binding SHA gate 拒绝 |
| same-generation binding 变化 | 通过 | refresh gate 拒绝 |
| 网络分区 / 缺联盟 ACK | 通过 | formal degraded execution 拒绝 |
| nominal 场景重标记 | 通过 | degraded evidence 不可用 |
| production ACK 伪标记 | 通过 | isolated ACK schema 拒绝 |
| 隔离专项 | 26/26 | 零失败 |
| D4 全量 | 508/508 | 零失败 |

三类正例输出 `isolated_simulation_only=true`、`production_runtime_ack=false`。它们只证明 D4 能验证来源、候选门、计划代次、authority 和隔离消费回执。physical outcome、paired non-degradation、counterfactual、causal、degradation effectiveness、PPO、assist 和 authority 均保持 false。main 尚未生成 arm-complete 多周期 rollout，D6 尚未接入干预后物理窗口，因此本节没有降级策略性能结果。

### 4.14 中心失效物理续跑适配审计

2026-07-22 审查 main 的中心失效 20-seed 物理续跑。20 个 pair 共生成 196 条区域采用记录。D7 世界命令已经写入隔离世界，D6 对 196 条记录的拒绝原因均为 `isolated_execution_plan_not_strictly_new`。

在线 D3 帧同时保存故障前 `previous_plan` 和故障后 `plan`。formal D4 decision 绑定故障后的当前 plan。现有物理 arm 从 `previous_plan` 重新求解，得到与 formal source 版本相同、计划标识不同的结果。D4 将该转换判为执行变化，但版本没有严格提高，因此拒绝。把 `previous_plan` 直接改作 source 也不成立：中心失效场景的 previous owner 是 center，中心与二级连续失效场景的 previous owner 是 secondary，均与当前 formal ownership 不符。

修正工作位于 main/D3 producer：以 formal current plan 为 source，再产生严格更高版本 applied plan；若实际世界只继续执行 formal current plan，则输出同身份、同 binding 的 evaluation refresh。D4 本轮只增加回归和说明，没有调整安全门。该 20-seed 结果证明错误代际被一致拒绝，不证明降级计划已采用，也不能用于 paired non-degradation 或策略效果结论。

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

区域学习 dataset-v1 已形成正式 900 episode 数据和可复现的 development checkpoint。独立补充课程已提供四类规则教师正样本，两类数据的 D4 全样本准入均为 complete，但仍没有 runtime applied ACK、动作执行结果或 reward。证据只支持数据结构、有限值、动作覆盖和确定性安全合同；D6 外部复核、回报归因、外部保留种子和成对收益不足以支持策略能力结论。bundle-v2 继续强制 shadow-only，其 manifest/SHA 溯源不能替代 paired 性能报告，也不改变 D4 主动/被动降级控制逻辑。

M5N2 中心负对照已完成 20/20，但 coalition 和第二 primary 5 m 均为 0/20；这说明物理协同闭环仍开放，不说明 D4 fallback 失败。本批未执行二级或完全分布式接管，真实 secondary/distributed 多 seed 继续列为 P1。后续必须补 collision object，并运行同 seeds 的中心失效、中心与二级连续失效和可审计主动风险 paired case。
