# D4 分布式降级与接管实验报告

## 1. 实验边界

本报告覆盖两类离线降级逻辑：中心节点失效后的被动降级连续性仿真，以及中心节点未失效但局部不确定性升高时的主动降级仲裁规则测试。节点通过内存网络交换粗粒度摘要，不涉及真实无线通信、火控参数、毁伤逻辑、实机飞控、硬件驱动、自动处置或绕过人工授权的流程。

2026-07-15 AirSim 证据严格限定为已完成的 20 个真实 M5N2 case。2026-07-20 D4-owned 证据包括区域 authority、区域资源建议和 next-cycle advisory 消费合同测试；main-owned scalable 3D 定向接口测试为 8/8。2026-07-21 增加正式数据审计、共享切分和区域动作覆盖课程。新增课程是确定性纯 Python 离线证据，不是 AirSim、真实网络、硬件或长时运行结果。本轮没有启动新 AirSim episode。终止命令生效前额外完成的 `png_ttc_2v2_seed001` 不纳入 M5N2 聚合；其余 tuned case 未执行，dropout case 完成数为 0，缺失项保持 unavailable。

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

`tests/test_region_resource_dataset.py` 当前 15 个 pytest case，结果 **15/15 passed**；`test_region_resource_advisor.py` 当前 **51/51 passed**，二者合计 **66/66**。增加 4.8 的共享切分 12 项后，该历史阶段 D4 全量为 **381/381 passed**，验收门限均为零失败。加入 4.9 的动作覆盖课程 6 项后为 **387/387 passed**；再加入 4.10 的全样本准入专项 10 项后，2026-07-21 当前全量为 **397/397 passed**。版本固定为 `d4-region-learning-dataset-v1` 和 `d4-region-resource-model-bundle-v2`。

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

审计前后正式 D4 dataset 目录树 SHA256 均为 `8cde5cace4bd8106e35801f6179775ae39298592f3b556f712ea857b9c496bc1`。原 manifest 和 900 个 episode 文件未改写。新增 12 项测试覆盖成功映射、BC 显式选择、哈希篡改、漏/多 seed、保留 seed 和源 SHA 不匹配；该共享切分阶段 D4 全量为 381/381。该结果只证明跨模块数据切分治理可用。PPO 仍不可用，assist 仍关闭，行为克隆性能不因重新分桶自动更新；加入课程专项后为 387/387，加入全样本审计专项后当前为 397/397。

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

审计专项 10/10、D4 全量 397/397 通过。审计内容 SHA256 为 `94f4f4bf914dde9fee0ce1d92ac491902019dd7388502fbee5f96c4edfac3e7f`，tracked JSON 文件带外 SHA256 为 `4245f1db36f1af47259554f0770e75a3fe97fcc5e9b75c1b04c83d5bfb5c9e46`。D6 需按显式 JSON 路径和该带外哈希独立复核。复核完成、真实 ACK/outcome/reward 与 paired shadow 形成前，确定性规则、lease/epoch 和安全投影仍是唯一可执行路径。

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
