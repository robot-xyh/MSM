# D2 多目标跟踪与数据关联实现差距审计

**审计对象**：`subagent_reviews/D2_DATA_ASSOCIATION_REVIEW_AND_PLAN.md`、`subagent_reviews/MAIN_IMPLEMENTATION_GAP_AUDIT.md`、`C_UAS_MAINSTREAM_SOLUTIONS_AND_DIFFICULTIES.md`、`research_modules/d2_data_association/` 代码与测试，并抽查 `research_modules/integration_contracts.py`、`research_modules/integrated_simulation/`、`research_modules/airsim_runtime/` 中的 D2 调用边界。

**审计边界**：仅评估 D2 离线科研仿真与数据关联模块，不涉及真实飞控、硬件、火控、毁伤或自动处置逻辑。

**本轮状态同步来源**：截至 2026-07-23 的 D2 代码与测试、main 尾部合并后的 seed1005
回归、200v200 单 seed development 制品、20/50/100/200 各 5 seed 快速治理制品，并保留
既有 AirSim/EVAL 审计结论；本次新增 clean 基线与候选的 200v200 五 seed 热路径对照，
`8f86192` 对 `f80b5bd` 的 10.0 s 三 seed clean 集成逐条语义审计，以及 clean
`4ac3bb2` nominal 200v200、seed 1000、10.0 s 冻结总线的 profiler 和旧/新等价比较；
同时纳入 clean 提交 `909669b` 的身份承诺 v2 首轮 A/B，以及发布新鲜度修复并绑定配置
谱系后的 clean 提交 `ff881316243ff5a2991a4659ab78637ed625d123`、nominal 200v200、
2.2 s、`recon_count=2`、seed 1100 的复核 A/B。

**结论摘要**：截至 2026-07-23，D2 无运行算法 P0 blocker。既有二维默认
GNN/Hungarian 与历史 AirSim replay 证据保持不变；显式六维路径已闭合 D2-owned
`[pN,pE,pD,vN,vE,vD]`、3D 马氏门控、KD-tree 候选图、分量 Hungarian、中心 ID、在线
truth 隔离、完整 D1 source-posterior covariance、固定权重 CI、速度创新 NIS 门控和
有限速度代价。50 条 seed 17 修复后速度 P50/P90/max 为
`5.082/6.401/7.218 m/s`、Pvv trace `101.181`，位置 RMSE `48.364 m`、IDSW 0、
continuity 1.0；200 条 seed 41 保持 `200/40,000` 候选/全对、IDSW 0、continuity 1.0。
历史完整回归 `139 passed, 1 warning`。当前 main 尾部合并使 seed1005 replay 合法变为 0；
D2 v3 复现和测试验收已同步。五 seed 200v200 候选在 45/45 周期保持完整发布语义，D2
总墙钟均值 `9.8299 -> 2.7679 s`。最终集成候选三 seed 的 D2 association 均值为
`8.317513 -> 7.671266 s`，终态航迹数 `205/204/203` 相同，逐条在线语义和 topic counts
均通过。P0 验证 blocker 已关闭，关联算法未修改。固定 CI weight `0.5` 尚未多 seed 标定；
六维 NIS/NEES coverage、高机动、实时/超线性、完整 JPDA/MHT 和外部框架 tracker 仍开放。
最新 seed 1000 profiler 在 48/48 周期严格等价下将 D2 core 中位数
`2.928830 -> 2.204672 s`，但早/晚窗口比 `1.119661x -> 1.123036x`，因此只关闭三个
可证明的常数成本热点，长窗口 P1 不关闭。身份承诺 v2 的 main/D6 接线和 fail-closed
行为已由 seed 1100 验证。发布新鲜度修复后的 clean A/B 已使 candidate strict 指标恢复
可用，三条超龄恢复保持未提交；未提交绑定违规和在线 truth use 均为 0。candidate
IDSW `9 -> 3`，但 D2/D3 数量 `203/200 -> 201/197`、track/coverage continuity
`0.865/0.870 -> 0.8266667/0.8283333`。合同修复通过，算法候选继续拒绝。

## 2026-07-31 正式 R0 半程 GAP 判定

本轮新增证据来自 clean producer `80e55eb` 的正式 R0 shard 0-9，共 `450/900`
episode。D6 v12 evaluator `b6289c5` 已按哈希校验后的离线 truth-isolated 身份制品
重聚合：严格 `id_switch_count` 为 `414/450 available`，可用项合计 893，169 个
episode 非零。在线 producer 保持 `0/450 available`；这符合在线 truth 隔离合同，
不列为 GAP。

- **P0 状态不变**：没有新增运行安全 blocker。36 个异常 episode 均失败关闭，未补零、
  未让 truth 进入在线 D2，也没有证据表明下游可把不可用值当作硬风险零值。
- **P1-A 高规模规范身份合并**：27 个 episode 因一条 `global_track_id` 对应多个真值
  目标而不可用；其中 23 个位于 200 规模、4 个位于 100 规模、50 及以下为 0。需要
  对候选边、连通分量、source claim、身份承诺与生命周期接续做逐帧因果审计。不能用
  truth 直接拆轨，也不能仅收紧门限后宣称修复。
- **P1-B 谱系时间链**：9 个 episode 因来源观测超出冻结的 `0.9 s` lineage window
  而不可用。4 个是 5v5 delayed-noisy 的不同 seed，5 个是 seed 1004 在五个 100v100
  场景中的重复表现。该分布不是规模单调退化，需先核对 measurement/arrival/
  state-valid/published/consume 时刻、调度和 sidecar 匹配。
- **P1-C 可评分身份稳定性**：100/200 规模贡献 821/893 次严格 ID Switch；
  delayed-noisy 场景族贡献 486 次，dense-crossing 贡献 95 次。前者没有一轨多真值
  失败，说明“严格可用但切换多”和“证据不可用”是两个独立问题，后续准入必须分别
  报告。
- **指标边界**：36 个失败项中的部分下界只覆盖局部可评分转移。严格不可用不等于 0，
  下界不能并入严格总数、不能替代 episode 指标，也不能参与算法排名或置信区间。

### 后续代码任务与验收口径

1. 固定 36 个失败项及同规模、同场景相邻通过项，生成逐帧 association-edge、component、
   claim、commitment、lifecycle 和五时刻因果包；在线包继续禁止 truth。
2. 一轨多真值候选应把真实歧义表示为 uncommitted/coverage 损失，禁止一个已承诺
   canonical track 同时吸收多个物理目标。谱系任务先修生产/调度/证据合同，不扩大窗口。
3. 任一代码、门限、状态机或窗口改变均冻结新 source 与新 execution plan，从 shard 0
   重跑。旧 `80e55eb` 的 450-cell 不重标签、不重解释、不与新结果拼接。
4. 定向回归要求 36 个历史失败原因均被正确消除或转化为可审计的未承诺覆盖损失，在线
   truth use、规范 ID 非法改写、重复谱系消费均为 0。
5. 完整晋级要求 9 场景、5 规模、20 unseen seeds 的严格证据完整；配对比较 ID Switch、
   identity/coverage continuity、track count、RMSE 和 D2 wall time。严格指标不可用或
   任一业务指标明显退化时继续失败关闭。

该证据只完成正式矩阵半程诊断。不能把 seed 1000-1009 写成 20-seed 完整结论，也不能
将 450-cell 的 893 次 ID Switch 外推为 900-cell 总量。

## 2026-07-23 D1 歧义侧车与 D2 保持租约增量

- **问题来源**：D1 v1/v2 在 clean 200v200 A/B 中把整歧义分量 suppression 作为硬
  身份处理后，D2 tracks `203 -> 199`、D3 targets `200 -> 196`、continuity
  `.865 -> .830`，候选被拒绝。下一候选把“歧义期不做硬身份承诺”下移到 D2
  canonical 生命周期，不再要求 D1 产生可消费的重复 posterior hit。
- **接口阻断已关闭**：D2 公开合同严格镜像冻结的 D1
  `d1.structural-ambiguity-evidence.v1`。默认发布节点为 `D1_FUSION`，默认兼容 epoch
  为 `d1-default-epoch-v1`；成员令牌、三段式 `source_key` 和不可逆
  `d1-observation-sha256:<digest>` 均有固定合同向量测试。D2 不 import D1 私有类，
  不要求原始 observation ID/source namespace。
- **A/B 隔离已关闭**：D1 本地 ID 到不透明来源键的转换只有显式
  `use_opaque_d1_source_tokens=True` 才启用；默认 adapter 调用和 Detection 序列化
  保持等价。随机上游字符串只进入 SHA-256，D2 canonical ID 仍由 `GT3D-*` 产生。
  缺 publisher epoch 时显式记录兼容默认值和 restart rotation 要求，不能宣称 D2
  已自动发现外部重启。
- **P1 模块实现已完成**：`AmbiguityHoldLeaseConfig` 默认关闭；开启后提供 soft/hard
  deadline、`max_component_age_seconds`、容量上限、generation/evidence replay
  拒绝、epoch 回退拒绝、观测 reservation 和 prediction-only hold。D1
  measurement/state-valid 时刻允许早于 D2 tracker epoch；未来分量和超过年龄上限的
  分量 fail-closed。保持轨不 update、不 hit、不 miss、不 birth、不 rebind、不
  coalesce，身份置信度不增加，协方差不因 posterior 收缩。未绑定成员和分量观测禁止
  birth。
- **P0 正常路径硬化已完成**：六维 source binding 在关联候选边生成时硬掩码，已绑定
  source 只能连原 canonical track。原边几何不通过时隔离并禁止 shadow birth，不再
  先调用 `_update_track()` 再记录 conflict；合法已有 binding 保持可更新。
- **诊断已完成**：逐帧/累计输出 component accepted/rejected/expired、hold track、
  reserved evidence、prevented hit/miss/birth/rebind、pre-update binding rejection、
  deadline/reason、原 measurement/arrival/state-valid/published 时刻、D2 消费时刻、
  `component_age_seconds/time_decision`、schema/policy 和
  `online_truth_used=false`。活动分量显式提高
  `AssociationRiskSummary.association_ambiguity`，在线 IDSW 仍为 unavailable。
- **模块证据**：2026-07-23 D2 完整回归为
  `271 passed, 1 warning in 28.82s`。专项覆盖 `0.40 -> 0.65 s` 合法延迟接受、
  future/stale 拒绝、原双时间戳不变和 replay 不刷新租约。warning 为环境 Matplotlib `Axes3D`，不影响
  合同和数值验收。该结果只关闭代码、合同和单元/模块不变式。
- **单 seed 集成候选已拒绝**：main 在固定提交 `9cd2a79` 运行 nominal 200v200、
  seed 1100、2.2 s、`recon_count=2` 对照。候选 D1 evidence received/consumed
  `46/46`，7 次 D2 消费产生 33 个 accepted component event，prevented
  hit/miss/birth 为 `69/69/4`；在线 truth use 为 0。D2 航迹 `203 -> 201`、D3 分配
  `200 -> 197`、available/unavailable mapping
  `1566/230 -> 1492/294`、RTF `0.2245 -> 0.2112`。候选身份评分因
  `source_observation_outside_lineage_window` unavailable，不能与 baseline IDSW
  `9`、track/identity continuity `0.865`、coverage continuity `0.870` 数值比较。
- **仍开放 P1**：候选未达到业务可用性不退化和身份指标 available 门槛，seeds
  1101/1102 已停止，默认关闭。下一步先定义歧义保活帧的可评分谱系合同：
  `identity_uncommitted/ambiguity_hold` 与普通 `lineage_missing` 分离，候选观测在
  身份未承诺期间不得硬分给 `global_track_id`。合同冻结后再联合校准 lineage window
  与 lease，并定位保持对航迹数、mapping 和 D3 分配的退化。禁止仅放宽当前 `0.9 s`
  window 作为准入修复；同 seed 1100 复核通过后才允许多 seed。首版只有 lease expiry
  release；连续双向唯一自动 resolution、component-level JPDA、bounded MHT 和跨进程
  epoch 协商未实现。

### 2026-07-23 身份承诺 v2 修复判定

- **D2-owned 合同缺口已关闭**：新增
  `d2.identity-evidence-commitment.v2` 和
  `d2.scalable3d_identity_evidence.v2`。每条 `GT3D-*` 航迹跨 lease expiry 保存
  `identity_uncommitted_after_hold`；soft/hard release 不再自动恢复身份承诺。
- **旧 reservation 重入缺口已关闭**：每条受 hold 影响航迹保存私有候选 key 集合和
  最大 component measurement timestamp。lease 到期释放 claim reservation 不清理该
  状态。同一旧 key 即使再次被 freshness 接纳，也在量测更新前撤回，不能增加 hit、
  更新状态、绑定 claim 或进入 `detection_to_track`。
- **恢复门控已关闭**：恢复同时要求 key 不在阻断集合、source timestamp 严格晚于水位线、
  claim 是本扫描首次 accepted original evidence 且 replay count 为 0、活动 lease 为 0、
  disposition 为 truth-free `target_candidate`，并且当前 tracker frame 减 source
  measurement timestamp 不超过版本化发布新鲜度预算。重复、同扫描 duplicate、超龄、
  future/stale component、旧/重复 generation、仅预测和显式
  `known_false_alarm/unknown` 均不能恢复。后两类处置来自不读取离线 truth sidecar 的
  上游传感器治理。
- **容量边界已关闭**：`IdentityCommitmentRecoveryConfig` 默认每航迹 2048 个阻断 key、
  全局 250000 个；未溢出状态在成功恢复后清理，溢出持续 fail-closed 并只在永久 drop
  清理。恢复配置 schema 已升级为 v2，默认发布年龄预算为 `0.9 s`；显式关闭只提供旧
  水位线/replay 兼容。重复航迹合并取集合并集与最大水位线。公开 DTO 只给出 blocker
  count、水位线和 overflow，不公开 key。
- **候选绑定缺口已关闭**：未提交 DTO 与 v2 evidence record 都禁止携带 source
  observation binding。离线 evaluator 不为未提交帧生成 truth candidate；coverage
  继续受罚，IDSW 跨未提交空窗比较 committed 锚点。普通 lineage 缺失和完整性错误
  继续 fail-closed。
- **兼容与规模已验证**：v1 默认构造、round-trip 和评分不变；v1 拒绝 v2 字段。
  专项覆盖 37 目标动态输入，无 2/5/200 固定规模。2026-07-23 完整 D2 回归为
  `291 passed, 1 warning in 29.05s`，验收阈值为零失败。新增回归覆盖旧 key 释放后重入、
  同水位线不同 key、未来来源时刻、发布超龄阻断、后续合格证据恢复、Detection/tracker
  frame 不一致拒绝、兼容关闭和容量溢出。
- **系统接线已关闭**：clean 提交 `909669b` 已原子持久化
  `identity_commitment_by_track`，D6 已聚合 commitment coverage、uncommitted
  counts、恢复原因、水位线、overflow 和 binding violation。clean 提交 `ff88131` 已
  按发布新鲜度修复后的 v2 再次重测 seed 1100，并将逐发布恢复配置快照、规范化哈希、
  offline identity manifest 和原始 D2 JSONL 绑定。
- **合同通过、算法准入仍开放**：baseline 的 D2 航迹/D3 分配为 `203/200`，strict
  IDSW、track continuity、coverage continuity 为 `9/0.865/0.870`，承诺覆盖率 `1.0`。
  candidate 为 `201/197`，strict 三项为 `3/0.8266667/0.8283333`，all-record
  commitment coverage `0.9574706212`，1711 条 committed、76 条 uncommitted，其中
  69 条 active hold、7 条 after hold。未提交 source/candidate binding violation 均为
  0，online truth use 为 0，说明 v2 fail-closed 合同通过。
- **当前 P1 阻断**：`GT3D-000185/000186/000202` 的超龄恢复已由同一 `0.9 s` 发布
  新鲜度门控阻断，strict 可用性缺口关闭。算法候选仍因 D2/D3 数量及两项 continuity
  退化未达到联合非退化门槛。默认仍为 disabled，seeds 1101/1102、10 s 和 20-seed
  矩阵停止；禁止扩大 `0.9 s` window。

## 0. 2026-07-15 M5N2 20-case GAP 判定

- **新增已闭合证据**：SimpleFlight M5N2 baseline/candidate 各 10 seed，20/20 case
  完整；D2 association main-bus 3805/3805 样本可用，mean/P95/max 为
  `2.521/3.147/98.942 ms`。此前缺少的同一真实 M5N2 多 seed D2 阶段时延证据已补齐。
- **P0 保持通过**：在线 truth identity/state use 为 0，`global_track_id` 仍由中心
  D2 主线维护，D5/D7 没有本地重绑证据。无 truth assignment 时在线 IDSW、continuity
  和依赖真值的身份指标必须保持 `None/unavailable`，不得写成 0。
- **不能归因的失败**：第二 primary 5 米成功为 0/20，最终均为 `collision_stop`；
  artifact 缺少 collision object、碰撞法向和碰撞瞬间成员/环境距离。该现象不能列为
  D2 算法失败，也不能据此调整 gate、生命周期或切换 JPDA/MHT。
- **仍开放 P1**：对这类真实 M5N2 运行冻结独立 offline truth sidecar，并逐 seed 生成
  IDSW/continuity availability 和置信区间；显式覆盖 duplicate source、teleport、
  clutter、dropout、合法新目标和 owner/epoch failover。98.942 ms 的 D2 单次时延长尾
  也需记录触发帧与输入规模后再判断是否要优化。
- **范围控制**：M5N2 完成后多 seed 批次已停止。`TERM` 前额外完成的单个
  `png_ttc_2v2_seed001` 不纳入本审计，dropout case 完成数为 0。默认
  GNN/Hungarian 和 P2 optional 边界不变。

## 1. 总体判断

D2 当前实现符合“先用规则 GNN/Hungarian 做工程主线，密集交叉再用 JPDA/MHT 做研究对照”的共识。二维兼容路径与六维稀疏路径均坚持 GNN=Global Nearest Neighbor；D2 未实现图神经网络。有界 whole-scan OOSM adapter 已实现，后续 backlog 是 main scalable bus 接入、真实 OOSM/遮挡/杂波参数、极端密度、生命周期和统计一致性标定；完整 JPDA/MHT、外部框架 tracker 和高阶运动模型保持 optional，不影响既有默认路径。

### 1.1 本轮 P0/P1 复核结论

- **P0 复核**：无开放 blocker。GNN/Hungarian、马氏门控、`DataAssociator`、`Track` 状态机、`id_switch_count`、`track_continuity`、`duplicate_assignment_count`、D1 adapter、AirSim dry-run adapter 和按输入集合长度运行的要求已在文档/GAP 中准确覆盖。seed1005 v3 测试合同已允许 main 尾部合并产生 `replay=0`，同时继续验证不新增航迹、hit 或真值使用。
- **P1 合同复核**：D1 governed adapter、offline truth evaluator、逐帧 schema/profile、匿名在线 detection ID、`d2-offline-truth-label/v1`、N-target dense/crossing fixture、至少 10-seed runner、M-of-N/false-track 和 NIS/NEES availability 已闭合。在线 Detection/Track/log 不含 actor 身份或 truth；无 truth replay 仍可计算 NIS。
- **2026-07-12 变更复核**：`33e6fa0` 没有 D2-owned 变更；后续 D2-owned P1 任务新增 long governed replay runner/schema、OOSM exposure 和动态 N/M 测试，默认在线 GNN/Hungarian 路径未替换。
- **2026-07-12 历史模块回归**：`PYTHONPATH=research_modules/d2_data_association pytest -q research_modules/d2_data_association/tests` 当时得到 `69 passed, 1 warning`。该数字仅是历史阶段测试规模；warning 来自 Matplotlib `Axes3D` 多版本导入，不影响 D2 关联、身份或指标测试。
- **2026-07-13 历史权威模块回归**：当时完整回归为 `93 passed`；后续历史结果见下一条，当前权威结果见 2026-07-22 条目。
- **2026-07-14 历史模块回归**：Post-batch 审计后完整 D2 suite 当时为 `99 passed, 1 warning`，专项 source-lineage teleport 测试为 `1 passed, 1 warning`。
- **2026-07-15 strict v2 完整重算**：六档真实 D1 replay 的 screening/confirmation 均 available，阶段内 digest 唯一，全部在线 truth leakage 为 0。总体候选五项 gate 全部通过并形成 promotion review recommendation；轻量 JPDA 的 IDSW/continuity gate 失败。默认 GNN/Hungarian 不变。
- **2026-07-20 历史模块回归**：原六维专项 13 个和新增速度稳定性专项 3 个通过，
  完整结果为 `139 passed, 1 warning`；warning 是环境 Matplotlib `Axes3D`，不影响
  六维数值状态。
- **2026-07-22 历史模块回归**：三 seed clean 集成证据同步后为
  `219 passed, 1 warning in 49.75s`；warning 仍为环境 `Axes3D`。
- **2026-07-23 当前权威模块回归**：身份承诺 v2、恢复水位线、发布新鲜度门控和独立
  audit 重算后的完整结果为 `291 passed, 1 warning in 29.05s`，验收阈值为零失败；warning 仍为
  环境 `Axes3D`。此前 `271 passed` 是保持租约阶段，`234 passed` 是 profiler
  等价优化阶段的历史结果。
- **2026-07-12 AirSim 证据**：PNG delivery candidate 的 2v2 10 seeds 为 20/20 pair、在线 truth 使用为 0；锁定后两帧 dropout 沿原 global/local track 和原计划上下文预测，没有 truth ID 或本地 ID 重写。M5N2 8 s 短窗口为 0/9，报告明确其几何与时间窗不足且不可与长时高净空基线直接比较。这些是 D2 下游合同的非退化证据，不是 D2 新算法或长期标定完成证据。
- **P0/P1 开放项**：P0 无开放项。P1 synthetic long replay、独立 offline truth、至少 10-seed 的 IDSW/continuity/false-track/RMSE/NIS/NEES availability、版本治理和 strict 4 m/2 m 各 20-seed 首轮真实标定已闭合；结构歧义保持租约、身份承诺 v2、发布新鲜度门控、main 持久化和 D6 聚合也已完成。当前仍开放新门控的 clean seed 1100 指标可用性与 D2/D3 业务非退化复核；通过前不得启动 1101/1102。更长 OOSM/遮挡/杂波 replay 下的 gate/risk/M-of-N 生命周期参数冻结、跨节点 D1 exact/CI posterior 回写、高歧义 replay 和 owner/epoch failover 验证仍开放；扩大 `0.9 s` window 不关闭该 GAP。
- **下一验收条件**：沿 2026-07-13 冻结 replay/truth/profile/预算合同扩展困难度和时间窗；逐 seed 及聚合报告 IDSW、identity/coverage continuity、duplicate、false-track、初始化延迟、NIS/NEES availability/coverage、runtime 和在线 truth 泄漏数。任何候选必须同时满足全部门限，不能只凭 IDSW 改善晋级。跨节点验收还必须证明 canonical ID 连续、duplicate payload 拒绝、owner/epoch 切换可恢复，并由 D1/D6 给出融合 posterior 与 NEES/ANEES。
- **历史基线**：2026-07-10 的 5v5/2v2 批次和 2026-07-11 早期的 seeds 7/17/27 当时不足以关闭 D2 P1，且 T001 双 primary 为 0。本条仅保留实施前/过渡证据边界，不代表当前状态。
- **2026-07-11 合同验收证据**：M=5、N=2 ComputerVision 的 T001 双 primary 共识/计划授权为 8/10；D2 `id_switch_count=0`、错误 duplicate=0、`global_track_id` 改写/重绑=0 均为 10/10。
- **commit/fail-closed 边界**：二级和完全分布式 commit 正例通过，缺 ACK 时 `aborted`/`hold_for_review` 且导引许可为 0。这只证明下游能沿用 D2 中心 `global_track_id` 完成 commit/fail-closed，不表示 D2 owner failover 或分布式临时 ID 合并已实现。
- **物理边界**：物理命中率属于 main/D7/D6 系统验收，不替代 D2 的身份连续性与隔离 offline truth 评分。2026-07-12 的 2v2 20/20 和 M5N2 短窗 0/9 都不改变 D2 synthetic dense calibration runner 已闭合、真实长 replay 标定仍开放的结论。
- **在线/离线指标边界**：没有 offline truth label 时，truth-based `id_switch_count`、`track_continuity`/`identity_continuity` 和 NEES 必须标记 unavailable；在线可继续计算 NIS、ambiguity、candidate overlap、cost margin、duplicate 和 track-quality risk。IDSW/continuity 结论必须由隔离的 offline evaluator 评分。
- **P1 闭合与后续研究边界**：D2 已形成覆盖 dense crossing、连续漏检/遮挡和虚警的动态 N replay，并冻结独立 truth JSONL；同 seed 复现、truth 隔离和 availability 已有测试。strict 4 m/2 m 真实 AirSim dense crossing 首轮标定已完成；更长 OOSM/遮挡/杂波以及 gate/risk/NIS/NEES 深度标定仍是 P1 性能研究，不是合同断链。
- **M 对 N P1 状态**：D2 已实现跨节点 local-track namespace、公共时刻传播、track-to-track Mahalanobis/Hungarian、公共信息谱系防重、canonical multi-source binding/history 和 exact/unknown/duplicate 决策基础。多个节点观测同一目标不会增加目标基数，也不会被误记为合法协同资源的 duplicate assignment。数值 CI/相关融合仍由 D1 owner 实现；高歧义多帧关联、owner failover 和融合一致性标定尚未闭合。专项证据见 `D2_M_TO_N_TRACK_FUSION_REVIEW.md`。
- **D4 P1 仲裁语义复核**：2026-07-07 main runtime bus / D4 P1 修复后，D4 已区分 D2 软风险和硬风险。`association_ambiguity`、cost margin risk、candidate overlap 和短时 D5 disagreement 是观察/二级 cue 证据；`id_switch_count` 增量、`duplicate_assignment_count`/`duplicate_track_risk` 和可用的 `track_continuity` 低于阈值才是 D4 主动仲裁的硬风险证据。2026-07-10 D2 P1 修复后，无 offline truth label 时 `truth_metrics_available=false`、`continuity_available=false`，兼容数值 `0.0` 不再触发 `duplicate_track_risk`、`continuity_collapse` 或 hard risk；旧 replay 未携带 availability 字段时同样保守按不可用处理。
- **P2 边界复核**：P2 v2 的第三方/高阶 benchmark 状态不变。模块内轻量 JPDA/MHT 仍是研究近似；完整外部 JPDA/MHT/UKF/IMM 和 optional 端到端 tracking 未实现。六维规则基线已在 D2 内实现，但没有替换二维默认入口，也没有进入第三方 benchmark 或 main 总线。

## 2. 明确状态分区

### 2.1 已实现

- **GNN/Hungarian 主线**：`GNNHungarianAssociator` 调用 SciPy `linear_sum_assignment`，每帧由实际 `tracks` 与 `detections` 构造代价矩阵，输出匹配、未匹配、拒配原因、代价矩阵、歧义分数和候选计数。
- **可插拔关联器接口**：`DataAssociator` 已作为统一插件边界，`Tracker` 消费 `AssociationResult`，因此 GNN、JPDA、MHT 可共享状态机、metrics 和风险摘要。
- **马氏门控与二维 Kalman 航迹管理**：`build_gated_cost_matrix()`、`Tracker` 和 `[x,y,vx,vy]` 常速度预测/更新已可运行，生命周期覆盖 `tentative/confirmed/engageable/lost/dropped`。
- **P0-B track quality / association risk**：`GlobalTrack.to_dict()`、`AssociationResult.metadata`、association logs、risk summary metadata 和 `MetricsRecorder.summary()` 已输出 `track_quality_by_track`、`association_risk_by_track`、mean/min/max 质量风险摘要和每条 track 的 `quality_metadata`。
- **P0-B 运动一致性约束**：`GNNHungarianAssociator` 在保留马氏门控和 `linear_sum_assignment` 的基础上，把速度方向、短时历史和加速度异常形成的 `motion_consistency_cost_matrix` 加入代价，并输出 per-pair/per-track diagnostics。
- **P0-B quality-aware gate baseline**：`build_gated_cost_matrix()` 已按 track quality、局部目标密度、位置协方差和上一帧 association risk 生成 `gate_thresholds_by_track`，在低质量/高协方差时保守放宽、在高密度/高歧义时收紧；完整自适应门控仍保留为 P1。
- **核心指标**：`MetricsRecorder.summary()` 已输出 `id_switch_count`、`track_continuity`/`identity_continuity`、`coverage_continuity`、`truth_metrics_available`、`continuity_available`、`duplicate_assignment_count`、RMSE、confusion matrix 和 runtime；无 truth 时 continuity 数值只保留报告兼容性。
- **拒配日志闭环**：`AssociationLogEntry.rejected_pairs` 默认空列表，`to_dict()` 和 `MetricsRecorder` 日志构造完整保留 `mahalanobis_gate`/`assignment_above_gate`；replay gate summary 分原因计数，旧 JSON 缺字段按空处理。
- **covariance 输入与统计治理**：Detection/GlobalTrack 及门控边界拒绝非有限、明显非对称、明显非 PSD covariance；replay governance 已输出 NIS 和 offline-only NEES 的 95% 卡方覆盖。剩余项是用真实多 seed 数据按距离、传感器和场景校准，而非接口缺失。
- **crossing/dense fixture**：`crossing_dense_5v5` 已作为确定性 baseline fixture 加入，可同场比较 GNN、JPDA、MHT；该 fixture 不改变关联器按输入集合长度运行的边界。
- **D1 adapter 基线**：`detections_from_d1_global_tracks()` 可把 D1 六维 NED `GlobalTrack` 投影为 D2 二维 `Detection`，保留 `measurement_timestamp`、`arrival_timestamp`、`covariance`、`global_track_id` 和 metadata。
- **AirSim dry-run/replay 输入基线**：`detections_from_airsim_frame()` 与 `run_airsim_dry_run_association()` 支持 synthetic AirSim-style `detections/tracks/objects`，接受 `x/y`、`x_val/y_val`、2x2/3x3 covariance，且明确不 import 或调用 `airsim`。
- **AirSim-style replay/report helper**：`load_airsim_replay_frames()`、`run_airsim_replay_association()`、`write_replay_association_report()` 和 `write_association_logs_jsonl()` 已能读取离线 JSON/JSONL replay，保留 main/D6-style row 中的 seed/scenario/frame/offline truth label，并输出 association logs、summary、当前 `global_track_ids`、`replay_metadata`、`association_risk_threshold_version`、gate pass/reject count、motion/quality risk summary 和风险摘要。
- **阈值敏感性与多 seed helper**：`run_threshold_sensitivity()` 可按 gate threshold 与 risk threshold profile 输出 `id_switch_count`、`track_continuity`、`duplicate_assignment_count`、`risk_profile_version`/`association_risk_threshold_version`、seed/episode/scenario/frame metadata、gate/motion/quality diagnostics 和 soft/hard risk summary；`summarize_multi_seed_risk_calibration()` 可按 gate/risk profile/version 汇总 IDSW、continuity、duplicate、soft/hard risk 分布、dense/crossing sensitivity summary 并给出推荐阈值摘要。
- **冻结 truth 与 calibration runner**：`OfflineTruthLabel` JSONL 合同固定 episode/frame/timestamp/truth ID/position/可选注释；读写器校验 schema、重复键和数值。通用 N-target fixture 和至少 10-seed runner 分离在线帧/离线评分，输出每 seed 和聚合 IDSW、continuity、NIS/NEES availability、gate/risk version、runtime 与确定性签名，unavailable 不转换为零。
- **弱证据风险摘要**：`AssociationRiskSummary`、`AssociationRiskSummaryWindowGenerator`、`RiskThresholds` 和 `classify_risk_summary()` 已把 cost margin、candidate overlap、ID switch delta、duplicate delta、continuity、D5 disagreement、source node/link type 汇总为 D4/D6 可消费的风险证据。
- **M 对 N canonical registry 基础**：`SourceTrackSummary` 固化 source/local/epoch namespace、measurement/arrival timestamp、6D NED state/covariance、quality、lineage/correlation status 和 canonical hints；`CrossNodeTrackAssociator`/`CrossNodeTrackRegistry` 完成公共时刻传播、covariance-aware gate、按 source Hungarian、one canonical-to-many source binding/history 与 duplicate/stale governance。source hints 不具备 canonical 身份权威。
- **M 对 N 指标与 truth 隔离**：在线 `CrossNodeRegistryMetrics` 输出 operational cross-node rebind、duplicate payload rejection 和 transport/queue/fusion latency，且不接受 truth；独立 `OfflineCrossNodeMetricsEvaluator` 通过 source-key truth mapping 计算 cross-node IDSW、`canonical_duplicate_count` 和 association precision/recall。
- **六维稀疏 detection-to-track 基线**：`Detection3D`/`GlobalTrack3D`、`Sparse3DGNNHungarianAssociator`、`Scalable3DTracker` 和 `Sparse3DOfflineEvaluator` 已实现；在线无 truth 字段，`GT3D-*` 只由 D2 分配，候选/分量/耗时/risk 和 unavailable identity metrics 显式输出。

### 2.2 部分实现

- **JPDA**：`JPDAAssociator` 已能枚举小规模联合假设、计算边缘概率并输出接口兼容结果；但它不是完整 JPDA 滤波器，没有概率混合状态更新、完整协方差融合或生产级参数标定。
- **MHT**：`MHTAssociator` 已有 bounded branch、短历史和 pruning 参数，能作为 MHT-compatible research placeholder；但不是完整 MHT，没有 N-scan pruning、分簇、长期假设树管理和中心算力策略。
- **EKF 表述**：D2 当前只有二维线性 Kalman fallback。主审计中“EKF/滤波主线 P0 可用”在 D2 侧应理解为轻量 Kalman 航迹预测可用，不代表 D2 已实现非线性 EKF。
- **3D NED 支持**：旧 `Tracker` 仍固定 `[x,y,vx,vy]`；显式 `Scalable3DTracker` 已固定
  `[pN,pE,pD,vN,vE,vD]`。main point-mass 总线已有只读诊断；部分实现项是修复后
  端到端复跑、版本化跨模块输出、真实多 seed 和统计一致性标定，不再是 D2 状态/门控
  代码缺失。
- **D6/集成输出**：D2 summary 与 association logs 已具备 IDSW、continuity、duplicate、risk/profile version、gate pass/reject、motion/quality 和 dense/crossing sensitivity 字段，且有 D2/D6 `id_switch_count` 口径测试。2026-07-11 P1 CV 批次已由 main/runtime/D6 生产和评分；2026-07-12 PNG delivery 报告没有新增 D2 offline IDSW/continuity。
- **D6 bundle 对齐**：D6 标准 AirSim calibration bundle 已由 main runtime 自动调用；D2 只保证 report/log/profile 字段可被分组读取，不在模块内重复生成 D6 report。

### 2.3 未实现

- **UKF 与 IMM-EKF/UKF**：代码中无 sigma-point UKF、IMMEstimator、CV/CA/CT 模型集或模型转移概率。
- **完整非线性 EKF**：代码中无雷达球坐标、相机投影或三维非线性量测雅可比。
- **完整外部框架 tracker**：`compat.py` 已返回 Stone Soup Detection 与 FilterPy KalmanFilter，`p2_benchmark.py` 已建立可运行 smoke comparison；但没有 Stone Soup Track/JPDA/MHT 或 FilterPy 端到端关联器。
- **JPDA/MHT 自动升级触发**：当前由调用方或仿真 CLI 显式选择 associator，未在 `Tracker` 内按风险阈值自动切换。
- **六维跨模块验收**：D2-owned 规则 tracker 已实现，main scalable point-mass bus 已有
  D1/D2/D3 只读运行证据；修复后 50v50/200v200、D3 reachability、版本化 D5/D6 输出
  和多 seed 端到端验收尚未完成。
- **AirSim runtime 职责边界**：D2 消费 main/runtime 导出的 governed JSON/JSONL replay 与隔离 truth，不连接 AirSim SDK，不采集 `simGetDetections`/CV 图像 metadata，也不编排 episode。
- **后续研究增强**：JPDA/MHT/BP 选型对照、SORT/ByteTrack-style fallback、完整自适应门控、N/M 初始化参数网格和 NEES/NIS 深度标定仍未完成；这些不是 P1 合同 blocker。

### 2.4 未实现原因

- **轻依赖优先**：当前默认测试要求只依赖 NumPy/SciPy/pytest，避免 Stone Soup、FilterPy、AirSim SDK、ROS 或 GPU 依赖进入基础回归。
- **接口先于高阶算法**：D2 先固化 `DataAssociator`、`AssociationResult`、ID 指标、风险摘要和 D1/D6 合同，避免在总线未稳定时引入重型框架对象。
- **场景证据不足**：UKF/IMM、完整 JPDA/MHT 和六维路径的高机动/密集场景升级需要强机动、遮挡、密集交叉、真实 replay 等证据证明收益，否则会增加参数和复杂度但不一定降低 IDSW。
- **职责边界**：真实 AirSim 启停、episode JSONL、CV detector metadata 和跨模块 runtime bus 由 main/runtime 负责；D2 只维护模块内 adapter 和离线关联能力。

### 2.5 缺少条件

- **数据条件**：若继续后续性能研究，需要专用多 seed 真实 AirSim dense/crossing replay、隔离 truth position、漏检/虚警/遮挡 sweep，以及 false track、init latency 和软/硬风险误报漏报统计。
- **模型条件**：JPDA/MHT/BP 选型对照、SORT/ByteTrack-style fallback、完整自适应门控策略、N/M 初始化标定和 NEES/NIS 统计一致性判定；三维 NED 状态合同、三维 covariance 门控、雷达/相机非线性量测模型、CV/CA/CT 机动模型和 IMM 转移概率。
- **依赖条件**：隔离 venv 已具备 Stone Soup 1.9.1/FilterPy 1.4.5 并完成 adapter smoke；完整算法仍需 framework tracker 配置、版本化参数、测试标记和同预算验收门限。
- **系统条件**：main/runtime/D6 已完成 2026-07-11 P1 CV 批次及离线评分。后续自动算法切换仍需阈值配置来源、迟滞和专用 replay 证据。

### 2.6 下一步优先级

- **P0 维护**：保持 GNN/Hungarian、门控、指标、D1 adapter、dry-run adapter、5v5 fixture、航迹质量评分、运动一致性约束和 quality-aware gate baseline 测试稳定；严禁把 2v2/5v5 写成算法常量。
- **P0 工程化硬化**：已新增每条 track 的 `track_quality`/`association_risk`，已把速度方向、加速度异常和短时历史一致性作为 GNN/Hungarian 代价项与 score 输出，并已实现 quality-aware gate baseline；继续维护这些字段的 D3/D5/D6 可消费性。当前无 D2 运行级 P0 blocker。
- **P1 闭合维护**：持续回归 replay/report、D1 governed adapter、冻结 truth JSONL、动态 N fixture、至少 10-seed runner、availability、threshold/risk split、covariance 治理和 IDSW/continuity 评分边界。完整 adaptive gate、JPDA 对照和真实 dense/NIS/NEES 标定作为后续性能研究。
- **P2**：维护已实现的六维规则路径并完成 main bus/多 seed/极端密度标定；EKF/UKF/IMM 只有在规则 CV 瓶颈有证据时再考虑。
- **P2 benchmark 已收敛**：dependency version/reason probe、对象 adapter、frozen replay digest、GNN/JPDA/MHT 同 Tracker 对照、五行 JSON、统一 `unavailable_reason`、truth-free 在线输入和隔离 venv smoke 已覆盖；默认 requirements/在线路径不变。
- **D1 governed schema 支持**：这是已闭合的 P1 输入合同。D2 loader 识别 `d1.governed_replay_manifest.v1`/`d1.sensor_observation.v1`，匿名 observation identity，按 frame/time 聚合 radar 球坐标并传播 covariance 到水平 N/E；声学 bearing 与 EO pixel 按原因跳过。
- **P2/P3 剩余**：完整 Stone Soup JPDA/MHT、FilterPy EKF/UKF/IMM、端到端身份指标与真实 replay 对照。
- **P3**：在多 seed replay 证明收益后，再做 JPDA/MHT 自动升级策略和切换迟滞。

实施顺序为：维护已闭合的 P1 replay/truth/D1-governed 合同和 synthetic runner；如需要，再扩展真实 dense/crossing 性能标定。P2 继续隔离运行，adapter 不得写入默认总线对象或默认依赖。

### 2.7 `global_track_id` 下游消费合同

- **D3**：D3 以 D2 输出的 `global_track_id`、状态、协方差和 `lifecycle_state` 构造资源-目标分配代价。D2 应提供当前活动航迹集合；D3 应优先消费 `confirmed/engageable`，对 `tentative`、长期 `lost` 或高风险航迹提高代价或延迟分配。D2 不生成 `AssignmentPlan`，也不修改 D3 的 plan version。
- **D4**：D4 消费 D2 `AssociationRiskSummary`、`id_switch_count` delta、continuity、duplicate risk、D5 disagreement、`source_node_id` 和 `link_type` 作为主动降级证据。D2 只发布关联风险，不决定 `continue_center`、`request_center_replan`、`degrade_to_secondary` 或 `degrade_to_distributed`。
- **D4 软/硬风险分层**：D2 的 ambiguity、low margin 和候选重叠是软风险，支持观察、提高 D3 迟滞、请求二级 cue 或离线 JPDA/MHT 对照；ID switch、duplicate 和 continuity 崩塌是硬风险，可作为 D4 主动重规划/降级仲裁证据。D2 不直接输出降级动作。
- **D5**：D5 使用 `global_track_id` 做终端视觉投影和候选配准，可回传 `TerminalAssociation`、`IdentityClaim`、候选 ID 与不一致事件作为弱证据。D5 不得改写、重绑或本地覆盖 D2 的规范 `global_track_id`。
- **D6**：D6 消费 association logs、TrackTransition、summary 和 confusion matrix。D2/D6 必须显式保留 `id_switch_count`：同一 truth 的代表 `global_track_id` 变化就是 ID Switch，不能用 RMSE、覆盖率或命中数替代。

## 3. 实现差距表

| 预期项 | 当前状态 | 证据文件 | 未实现原因 | 缺失条件 | 建议优先级 |
|---|---|---|---|---|---|
| GNN/Hungarian 默认关联主线 | 已实现。`GNNHungarianAssociator` 使用 SciPy `linear_sum_assignment`，支持马氏门控、运动一致性代价、quality-aware gate diagnostics、代价矩阵、拒配原因、候选数元数据，并按实际 `len(tracks)`/`len(detections)` 运行 | `research_modules/d2_data_association/d2_data_association/associators.py`；`research_modules/d2_data_association/d2_data_association/gating.py`；`tests/test_gating_and_associators.py` | 不适用 | 继续保留 5v5 高密交叉基准作为 fixture，不把规模写成运行假设；完整自适应门控仍需多 seed 标定 | P0 已满足，持续维护 |
| 可插拔 `DataAssociator` 接口 | 已实现。GNN、JPDA、MHT 均返回统一 `AssociationResult`，可复用 `Tracker`、metrics、risk summary 和 dry-run 输出 | `associators.py`；`tracker.py`；`tests/test_gating_and_associators.py` | 不适用 | 后续外部库 adapter 必须继续返回 `AssociationResult`，不得把外部对象泄漏到系统总线 | P0 已满足 |
| 马氏距离门控 | 已实现。`mahalanobis_squared()`、`build_gated_cost_matrix()` 输出候选数和拒配对 | `research_modules/d2_data_association/d2_data_association/gating.py`；`tests/test_gating_and_associators.py` | 不适用 | 可增加协方差交叠率自动计算 | P0 已满足 |
| 二维常速度 Kalman 航迹管理 | 已实现。`Tracker` 使用 `[x,y,vx,vy]`、线性预测和 Joseph 更新，含 tentative/confirmed/engageable/lost/dropped 状态机 | `research_modules/d2_data_association/d2_data_association/tracker.py`；`tests/test_tracker_metrics.py` | 不适用 | 若接 D1 3D NED，需要三维状态或投影适配策略固定 | P0 已满足 |
| EKF | D2 未实现完整非线性 EKF。当前是二维线性 Kalman fallback；主审计中“EKF/滤波主线 P0 可用”对 D2 的含义是轻量 Kalman 跟踪可用，不是 D2 EKF 已实现 | `tracker.py`；`docs/ALGORITHM_AND_IMPLEMENTATION.md`；`MAIN_IMPLEMENTATION_GAP_AUDIT.md` | Phase-1 使用二维质点/线性观测，暂不需要雅可比和非线性量测 | 需要三维 NED、雷达球坐标/相机投影量测、非线性观测模型 | P2 |
| UKF | 未实现 | `compat.py` 仅实现线性 CV FilterPy object adapter；没有 sigma points | 当前运行路径避免引入高阶模型；未定义 UKF 三维状态/量测接口 | 需要机动/非线性场景和模型合同 | P2 |
| IMM-EKF/UKF | 未实现 | `D2_DATA_ASSOCIATION_REVIEW_AND_PLAN.md` 仅列为目标；代码中无 IMMEstimator | 当前机动压力测试不足，D2 重点先解决关联接口与指标 | 需要 CV/CA/CT 模型集、模型转移概率、机动目标场景和评估门限 | P2 |
| JPDA | 部分实现。`JPDAAssociator` 可枚举小规模联合假设、计算边缘概率并输出接口兼容结果；不是完整 JPDA 滤波器 | `associators.py`；`tests/test_gating_and_associators.py`；`docs/ALGORITHM_AND_IMPLEMENTATION.md` | 为保持轻量可运行，只实现小规模离线对照；没有概率混合状态更新和完整航迹协方差融合 | 需要真实 5v5 replay、多 seed risk calibration、Stone Soup/完整 JPDA 对照和参数标定 | P1 已有可执行对照；完整 JPDA benchmark 为 P2 |
| MHT | 部分实现。`MHTAssociator` 保留有界分支和短历史，是 MHT-compatible research placeholder；非完整 MHT | `associators.py`；`tests/test_gating_and_associators.py` | 完整 MHT 复杂度高，当前只做中心/离线对照接口 | 需要 N-scan pruning、分簇、假设管理策略、中心节点算力假设和多 seed replay 证据 | P2 optional benchmark |
| Stone Soup | 部分实现。Detection/StateVector adapter、版本探测、frozen replay conversion smoke 已实现；1.9.1 实测成功 | `compat.py`；`p2_benchmark.py`；`tests/test_p2_benchmark.py` | 刻意不把 Stone Soup 对象暴露到总线；尚未配置 Track/predictor/updater | 完整 JPDA/MHT、状态更新、假设管理和同预算 IDSW/continuity | P2 adapter 已完成；tracker 未完成 |
| FilterPy | 部分实现。CV KalmanFilter 可由 D2 track/detection 初始化并执行 predict/update；1.4.5 实测成功 | `compat.py`；`p2_benchmark.py`；`tests/test_p2_benchmark.py` | adapter 不替换默认 Tracker，也不维护跨帧身份 | EKF/UKF/IMM、端到端关联生命周期和同输入身份指标 | P2 CV adapter 已完成；高阶/端到端未完成 |
| `id_switch_count` | 已实现。`MetricsRecorder` 根据 truth-to-track 代表 ID 变化计数，且测试验证 D2 与 D6 episode 计数口径一致 | `metrics.py`；`tests/test_tracker_metrics.py`；`simulation.py` | 不适用 | 集成场景必须提供离线 `truth_id`，否则只能输出风险摘要，不能评估真实 IDSW | P0 已满足，D2/D6 强制保留 |
| `track_continuity` / `identity_continuity` | 已实现。`track_continuity` 是 `identity_continuity` 别名，同时有 `coverage_continuity`；`truth_metrics_available`/`continuity_available` 区分无 truth 的 unavailable 与真实数值 0 | `metrics.py`；`tests/test_tracker_metrics.py`；`tests/test_replay.py` | 不适用 | D6 消费时必须先检查 availability，不能把兼容 `0.0` 当作连续性崩塌 | P0 指标已满足；P1 unavailable 语义已闭合 |
| `duplicate_assignment_count` | 已实现。统计同帧重复 detection/track 和同 truth 多 track | `metrics.py`；`tests/test_tracker_metrics.py` | 不适用 | 后续可扩展为滑窗 duplicate-track risk 自动评分 | P0 已满足 |
| 跨视角弱证据风险字段 | 已实现最小数据合同。`AssociationRiskSummary` 支持 `source_node_id`、`link_type`、`d5_disagreement_count`、`duplicate_track_risk`、`association_ambiguity`、`covariance_overlap_rate` | `models.py`；`metrics.py`；`tests/test_tracker_metrics.py` | 不适用 | 尚缺真实 D5/二级节点消息流和跨节点回放样本 | P1 已完成基线 |
| `AssociationRiskSummary` 自动派生 | 已实现 P1 基线。`AssociationRiskSummaryWindowGenerator` 可从 `AssociationResult.cost_matrix`、candidate count metadata、cost margin、ID switch delta、duplicate delta、track continuity 和 D5 disagreement 生成滑窗风险摘要，并进入 `MetricsRecorder.summary()` | `metrics.py`；`tests/test_tracker_metrics.py`；`docs/ALGORITHM_AND_IMPLEMENTATION.md` | 不适用；当前仍是轻量窗口规则，不是学习式风险模型 | 后续需用真实 5v5 AirSim replay 校准窗口长度、阈值和 D4 主动降级触发边界 | P1 已完成基线 |
| D4 软/硬风险消费合同 | 已实现代码和文档。D2 ambiguity/cost margin/candidate overlap 作为软风险；IDSW、duplicate 和可用 continuity 低于阈值作为硬风险。`continuity_available=false` 时 classifier 显式忽略 continuity，D2 不直接发起 `request_center_replan` | `metrics.py`；`tests/test_replay.py`；`README.md`；`PLAN.md`；`subagent_reviews/D2_DATA_ASSOCIATION_REVIEW_AND_PLAN.md` | D4 的主动降级动作由 D4/main runtime bus 负责，D2 只能维护证据字段 | 需要真实 5v5 AirSim replay 校准软风险误触发率和硬风险漏报率 | P1 unavailable 语义已闭合，阈值校准保留 |
| AirSim dry-run 适配 | 已实现。接收 synthetic AirSim-style dict/object，不 import `airsim`，支持 `detections/tracks/objects`、`x/y`、`x_val/y_val`、2x2/3x3 协方差，并在 bus message 中按活动航迹集合导出全部 `global_track_id` | `dry_run_adapter.py`；`tests/test_dry_run_adapter.py` | 不适用 | 尚未接真实 AirSim runtime；当前按要求只做 dry-run/replay | P0 已满足 |
| AirSim-like replay、冻结 truth JSONL 与 multi-seed summary | 已实现 D2 P1 合同。`d2-offline-truth-label/v1` 固定 episode/frame/timestamp/truth ID/position 和可选匹配注释；在线帧与 track/log 不携带 truth。通用 N-target fixture 和至少 10-seed runner 输出每 seed/聚合 IDSW、continuity、NIS/NEES availability、gate/risk version、runtime 和确定性签名 | `offline_truth.py`；`calibration.py`；`replay.py`；`tests/test_calibration.py`；`tests/test_replay.py` | D2 不连接 AirSim SDK | 可选扩展专用真实 dense/crossing 性能标定 | P1 合同/runner 已闭合 |
| D1 governed frozen replay loader | 已实现。manifest/records 转为 timestamp-grouped radar N/E detections，使用球坐标 Jacobian 传播 covariance；源 observation ID/lineage 不进入在线帧，声学/EO 有 skip diagnostics，旧 AirSim frames 保持兼容 | `d1_governed_adapter.py`；`replay.py`；`tests/test_p2_benchmark.py` | D2 当前关联平面是水平 N/E，不能直接混合 bearing-only 或 pixel measurements | 非 radar 模态需先由 D1 融合成 GlobalTrack，不能在 D2 loader 中伪转换 | P1 governed input 合同已闭合 |
| D1 `GlobalTrack` 到 D2 `Detection` | 已实现 P1 基线。D2 dry-run adapter 支持 `tracks` 字段和 3D covariance 投影到 2D；模块内提供 D1 `GlobalTrack` -> D2 `Detection` 转换入口，集成层仍保留 `CanonicalTrack`/`d2_detection_kwargs()` 合同测试 | `dry_run_adapter.py`；`tests/test_dry_run_adapter.py`；`integration_contracts.py`；`integration_tests/test_cross_module_contracts.py`；`integrated_simulation/adapters.py` | 不适用；当前转换仍保持 duck typing，避免 D2 强依赖 D1 包 | 后续需冻结真实 replay schema、坐标轴投影规则、timestamp 透传字段和阈值版本记录 | P1 已完成基线 |
| 原生 3D NED D2 跟踪 | D2-owned 规则基线已实现：六维 CV、完整 source covariance、相关 posterior CI、速度 NIS 门控、3D 位置创新/马氏门控、KD-tree 候选、分量 Hungarian、中心 ID、在线风险与离线身份评分 | `scalable_3d_models.py`；`sparse_3d.py`；`scalable_3d_offline.py`；`tests/test_sparse_3d_association.py`；`tests/test_scalable_3d_velocity_stability.py` | 为兼容旧 replay，未替换二维 `Tracker`；不消费原始 radar/pixel；CI weight 0.5 未标定为最优 | main 修复后端到端复跑、真实多 seed、六维 NIS/NEES、高机动、极端大分量预算和跨模块 schema | D2 P2 局部基线闭合；集成/标定开放 |
| 5v5 crossing/dense 专用测试 | 已实现 P1 基线。D2 自模块新增 deterministic `crossing_dense_5v5` fixture，并可同场比较 GNN、JPDA、MHT 的 IDSW、continuity 和 runtime；该场景是 baseline fixture，不是关联器固定数量假设 | `simulation.py`；`tests/test_simulation.py`；`docs/benchmark_results.json` | 不适用；当前是二维质点观测压力测试，不是 AirSim 图像回放 | 后续应补真实 AirSim CV replay 输入和更多遮挡/漏检/虚警 sweep | P1 已完成基线 |
| JPDA/MHT 自动升级触发 | 未实现。文档定义触发条件，代码需调用方手动选择 associator | `simulation.py` 的 `make_associator()`；`docs/ALGORITHM_AND_IMPLEMENTATION.md` | 自动切换会影响可比性和测试稳定，先保留显式对照 | 需要 D4/D6 认可风险阈值、切换迟滞和实验矩阵 | P2 |
| Stone Soup 对照测试 | adapter smoke 已实现。缺依赖明确 unavailable；available 分支转换 frozen replay Detection 并记录 latency，IDSW/continuity unavailable | `p2_benchmark.py`；`tests/test_p2_benchmark.py` | 未实现完整 tracker，禁止宣称 JPDA/MHT 成功 | 需要 Stone Soup tracker pipeline 才能产生身份指标 | P2 基础完成 |
| FilterPy 对照测试 | CV object smoke 已实现。缺依赖明确 unavailable；available 分支执行 predict/update 并记录 latency，IDSW/continuity unavailable | `compat.py`；`p2_benchmark.py`；`tests/test_p2_benchmark.py` | 无跨帧关联和生命周期 | 需要端到端 tracker 才能比较身份指标 | P2 基础完成 |
| D6 指标输出接口 | 已实现 D2-owned 输出。`MetricsRecorder.summary()` 输出 IDSW、continuity、duplicate、RMSE、runtime、risk、track quality 和 association risk 字段；`integrated_simulation` 已把 D2 tracks/summary 写入系统级记录；main runtime/D6 负责 episode 汇总 | `metrics.py`；`tests/test_tracker_metrics.py`；`integrated_simulation/runner.py`；`integrated_simulation/adapters.py` | D6 统一日志格式独立维护，D2 避免直接耦合 D6 类 | 可选扩展专用 dense/crossing 分组标定 | P1 D2/D6 指标合同已闭合 |
| `track_quality` / `association_risk` 航迹质量评分 | 已实现 EVAL P0-B。每条 `GlobalTrack` 输出 `track_quality`、`association_risk`、`quality_metadata`；`AssociationResult.metadata`、association logs、risk summary metadata 和 `MetricsRecorder.summary()` 输出 track-level 质量/风险字典与 mean/min/max 摘要 | `models.py`；`tracker.py`；`metrics.py`；`tests/test_tracker_metrics.py` | 不适用；当前是可解释规则评分，不是学习式质量模型 | 后续 D3/D5/D6 只消费该字段，不改写 D1/D3/D5 合同字段；多 seed replay 可继续标定阈值 | P0 已闭合，保持回归 |
| 运动一致性约束 | 已实现 EVAL P0-B。GNN/Hungarian 代价在马氏距离和可选 feature cost 外加入速度方向、短时历史和加速度异常形成的 motion consistency cost，并输出 pair/track diagnostics | `associators.py`；`gating.py`；`tracker.py`；`tests/test_gating_and_associators.py` | 不适用；仍保留原马氏门控和 Hungarian 求解器 | 后续用 dense/crossing replay 持续验证 motion weight 是否需要按场景校准 | P0 已闭合，保持回归 |
| quality-aware gate baseline | 已实现 EVAL P0-B。`build_gated_cost_matrix()` 按 track quality、局部目标密度、位置协方差和上一帧 association risk 生成 per-track gate threshold，低质量/高协方差保守放宽，高密度/高歧义收紧；不是完整 adaptive gating framework | `gating.py`；`associators.py`；`metrics.py`；`tests/test_gating_and_associators.py`；`tests/test_replay.py` | 轻量、可解释 baseline，不替换默认关联器 | 完整自适应门控作为后续研究 | P0 已闭合，保持回归 |
| 完整自适应门控策略 | 未实现。当前只有 quality-aware gate baseline | `gating.py`；`replay.py`；`metrics.py` | 阈值敏感性 helper 已完成，但不是在线自适应策略 | 需要专用 replay、隔离 truth、版本治理和多 seed calibration | 后续研究增强 |
| JPDA/MHT/BP 选型对照 | 模块内轻量研究近似已进入 frozen replay benchmark。`JPDAAssociator` 小规模枚举、`MHTAssociator` 有界分支均复用 Tracker/offline evaluator，并与 GNN 同输入输出 IDSW、continuity 和 latency；BP 未实现 | `associators.py`；`p2_benchmark.py`；`tests/test_p2_benchmark.py`；`simulation.py` | 当前 JPDA/MHT 未做概率混合状态更新、生产级假设管理、同预算标定或 coalescence 指标；BP 不进入当前依赖 | 需要真实 dense/crossing 多 seed 与同预算验收，且保留 GNN/Hungarian 默认主线 | P2 轻量对照已闭合；完整算法未实现 |
| SORT/ByteTrack-style fallback | 未实现 EVAL P1。当前 GNN/Hungarian 已具备 SORT-like 的运动预测 + Hungarian 核心，但没有独立 SORT fallback 模式，也没有 ByteTrack-style 低置信检测二阶段关联或视觉 MOT handoff adapter | `associators.py`；`tracker.py`；`EVAL/FRAMEWORK_EVAL_PATCH_ENGINEERING_PRACTICES.md`；`EVAL/FRAMEWORK_EVAL_PATCH_2026_VERIFIED.md` | 当前 P0 主线已足够运行；SORT/ByteTrack 应作为轻量 fallback 或视觉 MOT 场景对照，不能替代稳定 `global_track_id` 合同 | 需要定义 fallback 触发条件、输入置信度字段、IDSW/continuity 对照、异常回退路径和 D5 视觉 MOT replay 样本 | P1 对照/增强，不是 P0 |
| N/M 初始化优化 | D2-owned 接口已实现。`InitializationGovernanceProfile` 默认 2-of-3，并可由 replay/sensitivity 入口注入其他版本；输出 init/confirmation latency、success rate、false-track count/rate、miss/false-alarm 和逐帧 measurement/truth count | `replay_governance.py`；`replay.py`；`tests/test_replay_governance.py` | 在线 Tracker 状态机保持不变，truth 只用于离线标定 | 需要 main/D6 在真实多 seed replay 中标定 M/N 和生命周期参数 | P1 接口闭合；真实标定保留 |
| 协方差一致性检查 | 输入治理和统计接口已实现：NIS 用在线 innovation，NEES 仅用独立 offline truth state，输出二维/四维 95% 卡方区间及覆盖率 | `gating.py`；`replay_governance.py`；`tests/test_replay_governance.py` | online path 不接触 truth，缺 truth 时 NEES 为 unavailable | 需要真实 replay 和 D6 做分传感器/距离/场景多 seed 标定 | P1 接口闭合；真实标定保留 |
| M 对 N 跨平台 track-to-track association 与保守融合决策 | D2 注册基础已实现。`SourceTrackSummary`、公共时刻 CV 传播、完整 6D covariance-aware Mahalanobis gate、按 source Hungarian、lineage/payload/stale 防重和 exact/unknown/duplicate 决策均有测试；unknown 只输出 CI request，不在 D2 复制数值 CI | `cross_node_models.py`；`cross_node_registry.py`；`tests/test_cross_node_registry.py` | 数值 CI/已知相关融合属于 D1；D2 当前只完成关联、身份和融合策略请求 | 需要 D1 消费 fusion directives 并返回融合 posterior；需要高歧义多帧 replay 和 NEES/ANEES | P1 D2 基础闭合；跨模块数值融合/标定保留 |
| canonical global identity 多源注册 | 已实现中心 registry 基础。维护 `global_track_id -> [(source_node_id, local_track_id, epoch)]`、binding history、连续 ID 分配和 authoritative rebind；source candidate/current ID 只作非权威 hint | `cross_node_models.py`；`cross_node_registry.py`；`cross_node_metrics.py`；`tests/test_cross_node_registry.py` | 中心单 owner 已闭合；二级 owner 切换和完全分布式临时 ID 合并不在本轮基础范围 | 需要 D4 owner/epoch failover 合同和跨 owner replay | P1 中心注册闭合；failover 保留 |

## 4. 关键缺口说明

### 4.1 已满足的 P0 主线

- GNN/Hungarian 作为默认关联器已可运行，且使用成熟 SciPy 求解器。
- 马氏门控、候选计数、歧义分数、拒配原因已输出。
- Tracker 具备基本航迹生命周期管理和 ID 评估闭环。
- 关联器、Tracker 和 metrics 均按输入集合长度运行；2v2/5v5 只作为可重复测试场景。
- `id_switch_count`、`track_continuity`、`duplicate_assignment_count` 已进入 summary，且 D2/D6 对 `id_switch_count` 的计数规则已有合同测试。
- AirSim dry-run/replay-style 适配满足“无 AirSim SDK import、无真实 simulator call”的约束。
- D2-owned JSON/JSONL replay reader/report、association logs JSONL、threshold profile version、`association_risk_threshold_version`、gate pass/reject count、motion/quality risk summary、dense/crossing sensitivity summary、replay metadata、main/D6 row metadata、offline truth label、N-v-N target_count fallback、threshold sensitivity helper 和 multi-seed summary helper 已补齐，并通过 5 目标 AirSim-like replay、main/D6-style row、无 truth label N-v-N 与多 seed summary 测试覆盖。
- 集成层已能把 D1/D2/D3/D4/D5/D6 串入 `nominal_5v5` replay，D2 P0 主线已进入系统级离线闭环。

### 4.2 P1 已闭合接口与后续研究项

- D2-owned `crossing_dense_5v5` 确定性压力测试已经加入，用于 GNN/JPDA/MHT 同场对照。
- `AssociationRiskSummaryWindowGenerator` 已能从 cost margin、candidate overlap、ID switch delta、duplicate delta、continuity 和 D5 disagreement 自动生成滑窗风险。
- `RiskThresholds`/`classify_risk_summary()` 已把 D2 风险证据分为软风险和硬风险。
- `run_airsim_replay_association()`、`run_threshold_sensitivity()` 与 `summarize_multi_seed_risk_calibration()` 已能输出 5 目标 AirSim-like replay 的 association logs、metrics、risk summary、replay metadata、risk profile version、`association_risk_threshold_version`、gate pass/reject count、motion/quality risk summary、dense/crossing 阈值敏感性行和多 seed 推荐阈值摘要。
- D1 `GlobalTrack` 到旧 D2 `Detection` 的二维 adapter 保持兼容；新增 adapter 可产生 truth-free `Detection3D`，保留 NED 位置/速度提示并忽略上游 canonical ID。
- 2026-07-11 P1 CV 批次已沿隔离 truth 边界完成评分；2026-07-12 PNG delivery 报告没有新增 D2 offline IDSW/continuity。如扩展专用真实 dense/crossing 数据集，main/runtime/D6 应继续沿用 `d2-offline-truth-label/v1` 与已冻结 profile。
- EVAL 同步后的航迹质量评分、运动一致性约束和 quality-aware gate baseline 已作为 P0 工程化硬化闭合并保持回归；这些项增强 GNN/Hungarian 主线，不替换默认关联器，也不得改写 D1/D3/D5 合同字段。
- JPDA/MHT/BP 选型对照、SORT/ByteTrack-style fallback、完整自适应门控、N/M 参数优化和 NEES/NIS 深度标定保留为后续研究增强，不再写成 P1 合同未闭合。
- M 对 N D2-owned 注册基础已闭合：1/2/3/N source、异步公共时刻、交叉、duplicate payload/lineage、source local ID 冲突、canonical continuity、exact/unknown/duplicate 决策和 online truth isolation 均有专项回归。剩余是 D1 数值融合、D6 NEES/ANEES、多 seed 高歧义 replay 和 owner failover。

### 4.3 多目标交叉、密集编队与 ID Switch 剩余风险

- **多目标交叉**：GNN/Hungarian 是单帧硬判决。交叉窗口内最优/次优代价 margin 过小时，硬关联可能任意打破平局，并在后续 Kalman update 中吸收错误观测。JPDA/MHT 可用于对照和风险暴露，但当前 JPDA 没有概率混合状态更新，MHT 没有完整 N-scan 和长期假设管理，不能宣称已消除交叉 ID Switch。
- **密集编队**：多条航迹共享门内候选时，`candidate_counts_by_track`、`candidate_counts_by_detection` 和协方差重叠会升高。当前 feature cost 是简单向量差异；若外观、类别或声纹特征不稳定，仍可能发生 ID 交换或重复航迹解释。
- **ID Switch 可观测性**：`id_switch_count` 依赖离线 `truth_id`。真实在线路径没有 truth label 时，D2 只能发布风险摘要和弱证据，不能把在线风险摘要当成真实 IDSW ground truth。D6 应在带 truth 的仿真或 replay 中计算最终 IDSW。
- **规模风险**：D2 不写死 2v2/5v5。六维路径通常只对稀疏连通分量运行 Hungarian，但极端全重叠仍可能退化为大分量；JPDA/MHT 仍会随候选数增长。更大 N 需要候选预算、分区和召回率联合标定。

### 4.4 暂不实现的合理项

- Stone Soup/FilterPy object adapter 已隔离实现，但不得进入核心运行路径；完整 tracker 仍只能作为未来研究对照。
- 完整 MHT 不适合资源节点，当前有界 MHT placeholder 满足离线接口验证；生产级 MHT 需要中心算力、剪枝策略和更完整的场景基准。
- EKF/UKF/IMM 需要更复杂的机动/非线性量测证据；当前二维兼容和六维线性 CV 两条规则路径不构成这些高阶滤波器已实现。

## 5. 下一步建议

1. **维护 P1 governed replay/truth 合同**：继续回归 D1 adapter、在线匿名化、`d2-offline-truth-label/v1`、profile version 和 evaluator-only 评分。若新增专用真实 dense/crossing 数据，沿用同一合同。

2. **N/M 初始化与 false-track 标定**：使用已实现的版本化 M-of-N/false-track 输出，对建轨确认、漏检容忍和删除参数做真实多 seed 网格实验，并覆盖非 2/5 数量输入。

3. **NIS/NEES 真实标定**：复用现有 NIS/NEES 和卡方覆盖接口，补按传感器、距离和场景的多 seed 分组偏差及 D6 趋势。

4. **完整 adaptive gate / JPDA 对照**：固定 replay、seed、输入和预算，对比固定门限、quality-aware baseline、完整 adaptive gate 及 GNN/JPDA，报告 IDSW、continuity、false track、漏关联、延迟和 JPDA 截断率；默认主线仍保持 GNN/Hungarian。

**M 对 N 后续：数值融合与高歧义治理**：D2 已闭合“公共时刻预测 -> track-to-track association -> 相关性/公共信息判定 -> canonical binding -> fusion request”基础。后续由 D1 接续 exact/CI 数值融合，并用多 seed crossing/dense replay 验证跨节点 JPDA/MHT、D2 owner failover 和融合一致性。D4 commit 正例通过不等于这些 D2 能力已实现。

**M 对 N 评估状态**：已实现 `canonical_duplicate_count`、cross-node IDSW、track-to-track association precision/recall、重复消息拒绝数和 fusion latency；online registry 不读取 simulator truth。fusion NEES/ANEES 和通信字节仍需 D1/D6 离线评分与 replay schema。

5. **P2：接入已实现六维路径**
   由 main 冻结 D1 -> D2 -> D3/D5/D6 的 scalable bus schema、模型版本和性能预算；D2 继续保证中心 ID、三维门控与 truth isolation。

6. **P2/P3：外部库增强**
   对象 adapter/frozen replay smoke 已完成。后续只有在真实 replay 和计算预算冻结后才实现 Stone Soup JPDA/MHT 或 FilterPy EKF/UKF/IMM 端到端对照；否则保持 unavailable，不以 adapter latency 代替 IDSW/continuity。

## 6. 审计结论

D2 已具备既有 P1 合同和六维稀疏 D2-owned 基线：在线 identity 匿名、中心 `global_track_id`、3D innovation、稀疏候选、风险摘要和隔离 evaluator 均有代码/测试。默认二维 GNN/Hungarian 不变；六维规则路径是 scalable 场景的显式入口。进一步开放项是 main 总线、真实多 seed/极端密度、高阶关联/运动对照和 D2 owner failover；P2 第三方 adapter 继续隔离。

## 7. 2026-07-12 P1 长 Replay 增量复核

### 已闭合的 D2-owned 缺口

- 新增 `d2-governed-long-replay/v1` synthetic governed replay 和至少 10-seed
  runner，覆盖重复 dense crossing、交叉窗口遮挡、周期漏检、近场虚警和延迟到达。
- gate profile、risk profile、association threshold 和 scenario 均带版本；报告固定
  默认在线关联器为 `GNNHungarianAssociator`，JPDA/MHT 不进入主线。
- 每 seed 和聚合层新增 false-track、RMSE、identity/coverage continuity、
  NIS/NEES availability、OOSM exposure、online truth leakage 和中心
  `global_track_id` owner 证据。
- 新增动态 N/M 回归：3 个目标场景中每帧 measurement count 同时覆盖小于和大于
  target count，算法和报告不依赖 2v2/5v5 常量。
- OOSM 边界已明确：该 replay runner 消费按 measurement time 治理后的序列；D2 后续
  新增 whole-scan adapter 可对有界 arrival inversion 排序。原始量测回溯/重放仍属于
  D1/main 或后续研究，不在 D2 中伪实现。
- 默认 5 目标、120 帧、10-seed smoke 得到平均 IDSW `139.6`、identity continuity
  `0.691`、false-track `5.3`、RMSE `0.306 m`，NIS/NEES 10/10 seeds available，
  arrival inversion 70 次且 online truth leakage 为 0；当前 profile 未通过治理阈值。

### 仍开放的 P1

- 真实 AirSim/Blocks 长时间 dense crossing、遮挡和 OOSM governed replay 尚未由
  main 冻结；当前新增的是确定性 synthetic 校准入口和 schema。
- gate/risk、M-of-N 生命周期、false-track 和 NIS/NEES 的工程阈值仍需真实多 seed
  数据标定。长 replay 中暴露出的 IDSW/continuity 退化属于待校准结果，不应改写为
  “默认 GNN 已解决”。
- cross-node owner/epoch failover、高歧义多帧 canonical registration、D1 exact/CI
  posterior 回写和 D6 fusion NEES/ANEES 仍按原 P1 backlog 保留。

P0 仍无 blocker；P2 的完整 JPDA/MHT、Stone Soup/FilterPy 端到端 tracker 和原生
3D/IMM 不因本轮入口增加而升级状态。

## 8. 2026-07-12 P1 固定矩阵补充

### 已实现

- 新增固定 54 组 GNN/Hungarian 标定矩阵：gate `5.99/9.21/13.82`、
  quality-aware off/on、lost/drop `1/3, 2/5, 3/7`、motion consistency 当前权重
  的 `0.5/1/2` 倍；默认 baseline 固定为 `9.21/on/2-5/1.0x`。
- 新增 10-seed 筛选和 20-seed 确认合同。全部配置记录同一 frozen replay/truth
  suite digest；seed 重复或数量不足时显式 unavailable。
- 每 seed 和聚合输出 IDSW、identity/coverage continuity、false-track、RMSE、
  NIS/NEES availability、初始化延迟、p95 loop latency 和 truth leakage。
- 当前轻量 JPDA 仅对最佳 GNN 的同一输入、gate 和 lifecycle 做离线对照；完整 JPDA
  状态概率混合仍未实现，默认 GNN/Hungarian 未替换。
- 固化候选门限并保持 fail-safe：只有 20-seed 确认满足 IDSW `>=30%` 改善、
  continuity 消除至少 10% 基线剩余错误且不退化、false-track 增幅 `<=10%`、p95
  在冻结预算内且 baseline/candidate truth leakage 均为 0 才生成 promotion review
  建议；任一指标 unavailable 均拒绝，代码不自动切换主线。

### 2026-07-13 真实确认结果与开放 P1

- main 已提供 nominal 4 m 与 tight 2 m 各 20-seed 的真实 AirSim/D1 governed replay，
  frozen screening/confirmation 与 P95 预算合同可用。
- 最佳 GNN 候选 IDSW `1.358333 -> 0.616667`（下降 `54.6012%`），continuity
  `0.981046 -> 0.983954`，P95 `15.470 ms`；v2 continuity 所需提升为 `0.001895`，
  实际 `0.002908`，error reduction `15.3448%`。false-track 与 truth leakage 均为 0，
  完整总体 admission 通过并生成评审建议，但没有自动改默认路径。
- 轻量 JPDA 在同输入下退化，继续标为 research adapter。默认 GNN/Hungarian 保持
  不变；完整 JPDA/MHT 和 Stone Soup tracker 继续属于 P2 optional。
- P1 仍需扩展更长时窗、OOSM、遮挡、杂波、M-of-N/false-track 和 NIS/NEES 分档标定，
  并验证 continuity 改善是否可复现。

模块回归新增矩阵、digest、指标 availability、缺 20-seed fail-closed、manifest
加载和默认主线不变测试。P0 仍无 blocker。

### D1 Sidecar 集成补充

- **已闭合**：D2 manifest loader 现可按 suffix/schema 区分 D2 JSONL truth label 与
  D1 `d1.airsim_offline_truth.v1` JSON sidecar；不再把 D1 JSON 误交给 JSONL loader。
- **已闭合**：D1 adapter 强制验证 evaluator-only、NED、有限 timestamp、非空
  `truth_id`、三维有限 `position_ned`、sample/target count 和 replay frame 唯一映射。
- **已闭合**：三维 NED 只投影为 evaluator-only N/E `OfflineTruthLabel`，Down 和来源
  payload index 保留在 annotation；在线 frame、track 和 association log 不注入 truth。
- **测试证据**：D1 governed replay + D1 sidecar 经 manifest loader、D2 association 和
  offline evaluator 端到端通过，并验证在线 truth leakage 为 0；错误 frame/time/ID/
  position 和无匹配 frame 均 fail closed。
- **当前状态**：2026-07-13 strict 4 m/2 m 各 20-seed 数据已冻结并完成首轮标定；
  sidecar adapter 和首轮结果不表示更长 OOSM/遮挡/杂波参数已完成标定。

### Real AirSim evidence 分类修复

- **已闭合**：历史分类器只识别严格等于 `airsim` 的来源，导致 main 已冻结的
  `real_airsim_blocks_d1_governed_replay` 在 screening、confirmation 和 JPDA 对照中
  被错误标为 `airsim_evidence=false`。
- **当前规则**：legacy `airsim` 与受治理的 `real_airsim_*` 标识为真实 AirSim 证据；
  普通 synthetic 标签不能仅凭包含 `airsim` 子串获得真实证据状态。
- **影响边界**：只修复来源元数据分类，不改变 GNN/Hungarian 主线、54 组配置、固定
  门限、promotion review 策略、指标值或 online truth 隔离。

## 9. P1 六档高难度 replay 支持

### 已实现

- frozen case/manifest 增加六档受控 `scenario_difficulty` 和实际注入参数元数据；未知
  档位、同档重复 seed、同档元数据不一致均 fail closed。
- 混合 suite 的治理键改为 `(scenario_difficulty, seed)`，每档独立满足 10-seed
  screening；`combined` 支持独立 20-seed confirmation。
- 每个 GNN/JPDA 结果输出 `aggregate_by_difficulty`，包含 IDSW、continuity、
  false-track、RMSE、latency 与 truth leakage；最终报告给出分档 admission。
- 增加“场景仍无区分度”判定：所有受评算法均为零 IDSW 且 identity continuity 为
  1.0 时，不生成该档 promotion 建议。
- 保留默认 GNN/Hungarian、既有 54 组矩阵、轻量 JPDA research-only 状态、固定准入
  门限和 evaluator-only truth sidecar 隔离。

### 仍开放的 P1

- 六档真实 AirSim replay、注入参数和 10/20-seed manifest 仍由 main 生成；D2 本轮只
  闭合消费、分档统计和治理接口。
- 若 `combined` 真实数据仍被判定无区分度，需要 main 增强遮挡、异步量测或杂波，
  不能在 D2 内利用 truth 人为制造区分度。
- 候选通过分档 admission 仍只表示可进入评审，默认在线路径不会自动切换。

P0 仍无 blocker；完整 JPDA/MHT 和 Stone Soup 端到端后端仍为 P2。

## 10. P1 真实 governed replay 压力生成补充

### 已实现

- 新增 public、纯离线、确定性 D1 governed replay transformer；输入仅为在线-safe
  bundle、profile、seed 和 spacing 声明，不存在 truth sidecar 参数。
- dropout、clutter、delayed/noisy、combined 在 observation record 层执行，保留双
  时间戳、协方差和 lineage 合同；匿名虚警带 evaluator scenario 标记。
- nominal/单压力档验证约 4 m 捕获声明，tight/combined 验证约 2 m；已有 D1
  provenance spacing 与调用声明不一致时 fail closed。transformer 不改目标几何。
- 输出 profile metadata/digest、input/output digest、实际随机参数、记录统计和 online
  truth leak；同 seed 对同输入逐字节可复现。
- 真实 Blocks governed bundle 专项验证中，radar 记录统计为 nominal `255`、dropout
  `240`、clutter `355`、delayed/noisy `255`、combined `340`，各档 digest 不同且均可
  由现有 D2 adapter 读取，truth leak 为 0。

### 仍开放的 P1

- **接口已闭合、数据仍待 main 提供**：D1 loader 已透传 `target_spacing_m` 与 stress
  profile，真实 AirSim P1 manifest 缺 spacing、4 m/2 m 档位冲突或多来源数值冲突会
  fail closed；main 仍需在每次真实捕获时写入该 provenance。
- **稀疏 truth 对齐 blocker 已闭合**：D1 sidecar 中没有对应 governed frame 的合法
  truth 样本现在进入 unmatched 审计，不再中止真实 pipeline；只生成严格时间对齐的
  evaluator labels，并输出 `complete/partial/unavailable`。最近邻、伪造标签和在线
  truth 注入均禁止，重复/歧义/非法 sidecar 仍 fail closed。
- transformer 只制造观测压力，不保证一定产生 IDSW；是否达到算法区分度必须由真实
  10/20-seed 校准结果判断。
- main 需把 result profile metadata/digest 写入六档 manifest，D6 再审计每档实际
  注入统计与 admission。

## 11. 2026-07-13 Strict 4 m/2 m GAP 复核

### 已闭合

- nominal 4 m 与 tight 2 m 各 `20` 个真实 D1 replay seeds 已进入同一受治理校准链路。
- 最佳 GNN 候选的 IDSW 从 `1.3583` 降至 `0.6167`，下降 `54.6%`；continuity 从
  `0.9810` 提高至 `0.9840`；P95 loop latency 为 `24 ms`。
- truth 只在 `1e-9 s` 容差内 exact matching；未找到严格对应 frame 的合法样本计入
  `partial/unmatched`，不做 nearest-neighbor 补齐，不伪造 evaluator label。
- online truth leakage 为 `0`，在线 detection、track 和 association log 不含 truth ID。

### 仍开放 P1

- v1 的 `+0.10` 不可达门限及完整 v2 冻结报告均已闭合；当前开放项改为跨模块评审
  promotion recommendation、分档 baseline IDSW=0 的证据解释和 dropout partial truth
  alignment，不再是“缺少完整联合报告”。
- 需要更长 OOSM/遮挡/漏检/杂波组合回放，继续标定 gate/risk、M-of-N、false-track、
  NIS/NEES，并判断 IDSW 改善与 continuity 改善能否同时稳定成立。
- 高歧义跨节点 canonical registration、owner/epoch failover，以及 D1/D6 exact/CI
  posterior 和 NEES/ANEES 仍未闭合。

### P2 Optional 边界

轻量 JPDA 本轮退化；完整 JPDA/MHT、Stone Soup 端到端 tracker 和 FilterPy
EKF/UKF/IMM 仍只允许隔离 benchmark。当时尚未实现的六维规则路径已在 2026-07-20
作为独立入口补齐，但没有替换默认 GNN/Hungarian，
也不得写入默认 requirements、在线自动切换或跨模块运行合同。

### 权威回归状态

2026-07-13 当时 D2 模块完整回归为 `93 passed`。`69 passed, 1 warning` 仅对应
2026-07-12 历史阶段；本机 Matplotlib `Axes3D` warning 不影响 D2 功能与本轮结论。

## 12. 2026-07-14 Online Truth 与 Lifecycle GAP 收口

### P0 已闭合边界

- `TrackerTruthPolicy` 已把在线和离线 truth 权限变为显式合同。online 默认 fail-closed，且在任何预测、关联、建轨或指标计数前拒绝 `Detection.truth_id`、显式 `truth_ids_present` 和递归 metadata 中的 truth/actor/object identity；offline evaluator 继续允许 truth。owner 集成复核后，四个已知 governance/availability 键只在值为布尔型时允许通过，非布尔身份值与 offline truth payload 仍 fail-closed。
- `MetricsRecorder.summary()` 在 truth assignment 不可用时保留 IDSW、track continuity 和 RMSE 键，但值为 `None`，同时输出一致的逐指标 availability/reason。truth 可用且零 IDSW 的回归继续输出 available `0`。
- truth-free lifecycle evidence 已输出 birth/lost/drop/rebirth 显式计数和 `TrackTransition` 列表。rebirth 只表示同一中心航迹从 `lost` 重获，不越权推断 dropped 后的新航迹真实身份。

### 验证与剩余 P1

2026-07-14 验证覆盖 8 类拒绝输入、main owner 四布尔状态正例、3/5 帧 truthless replay、7 帧 lifecycle 状态序列和完整模块回归；验收要求为零失败、fail-closed 无状态副作用、truthless 字段不返回伪零，结果为 `98 passed, 1 warning`。warning 仅来自环境中的 Matplotlib `Axes3D` 导入。

本批没有修改 `confirmation_hits`、lost/drop 或 gate 参数。真实 replay 的 `T001 -> T005` birth/lost/drop/rebirth 生命周期调参、按密度/漏检率冻结 M-of-N 与 false-track 阈值仍是 P1；跨节点 owner/epoch failover 和 D1/D6 exact/CI posterior 闭环也保持原 P1 状态。P0 无新增 blocker。

## 13. 2026-07-14 `T008` 航迹膨胀专项

### P1 已闭合的 D2 局部缺口

- **根因证据**：真实 seed 1、351 帧 episode 在 31.3 秒出现第三条 D1 航迹；
  `global_track_002` 与新建雷达 `global_track_003` 同时成为 `T002` 的合法候选。
  D2 旧逻辑只按运动代价选择一个，并对另一条立即 birth；随后上游同一来源发生
  数十米级单帧跳变，旧逻辑继续产生 `T003...T008`。修复前统计为 birth 8、drop 4，
  真实目标数仅为 2。
- **D2 修复**：来源谱系连续性进入 GNN 代价；门内影子 observation 不 birth；已
  绑定来源超门限跳变 fail-closed 隔离。诊断显式记录来源 ID、规范 ID、马氏距离、
  门限和抑制原因。所有逻辑在线匿名、动态规模，不使用 truth，不本地重绑规范 ID。
- **验收证据**：4 帧匿名 fixture 中 2 条目标、1 条近邻影子和 1 次 teleport 后仍为
  `T001/T002`，抑制和隔离各 1 次；D2 全量 `99 passed`。`git diff --check` 在任务
  结束统一确认。

### 仍开放的 P1 与 owner

- **D1 owner**：修复 D1 在 31.3 秒把一个真实目标拆成两个 GlobalTrack，以及后续
  `global_track_002` 状态 teleport；D2 的保护只能阻止其继续膨胀，不能恢复被 D1
  丢失的正确状态。
- **main/D3 owner**：复核修复前 `T008` 在 `confirmed` 状态即被分配的问题；建议
  分配输入按 `engageable`/质量合同治理，而不是消费全部 non-dropped active tracks。
- **main owner**：同配置真实 AirSim seed 1 baseline/candidate 已复跑；两组都只维护
  `T001/T002`，`birth=2`、`lost/drop/rebirth=0`，未再出现 `T008`。2026-07-15 的
  后续普通 M5N2 已完成 20 case，但显式 teleport/影子扰动和该批 offline identity
  仍未执行，针对性系统级 P1 因而保持开放。
- **历史 P2 状态**：本专项当时 JPDA/MHT、Stone Soup/FilterPy 和原生三维均未进入
  主线；原生六维规则基线随后于 2026-07-20 以独立入口实现，旧结论不再代表当前代码。

## 14. 2026-07-14 Post-batch M5N2 D2 证据复核

### 权威输入与在线结果

| 项目 | baseline | candidate |
| --- | ---: | ---: |
| 真实 episode | `...m5n2_baseline_seed001` | `...m5n2_candidate_soft_prediction_trend_coast_seed001` |
| 帧数 | 142 | 141 |
| D1 为 2 条航迹的帧数 | 140 | 139 |
| D2 为 2 条规范航迹的帧数 | 140 | 139 |
| 最大活动规范航迹数 | 2 | 2 |
| 唯一规范 ID | `T001,T002` | `T001,T002` |
| birth/lost/drop/rebirth | `2/0/0/0` | `2/0/0/0` |
| `T008` 记录 | 0 | 0 |
| source binding | `001->T001, 002->T002` | `001->T001, 002->T002` |
| suppression/quarantine/conflict | `0/0/0` | `0/0/0` |

每组仅有 2 个 unmatched detection，对应初始 birth；之后 baseline/candidate 分别形成
278/276 个 matched pairs，未出现 unmatched active track。在线 GNN/Hungarian 日志中
IDSW 和 continuity 均为 `None + unavailable`，原因是 `truth_assignment_unavailable`，
符合 P0 truth isolation，不应改成伪零。

### Evaluator-only 复核

独立 `offline_truth_labels.jsonl` 分别包含 284/282 条标签，在线关联结束后才进入评分。
现有 D2 governed replay 入口对两组均输出 IDSW 0、identity/coverage continuity 1.0、
false track 0、online truth isolation violation 0。对 main 实际 track records 做写盘后
位置匈牙利裁决，baseline/candidate 的 IDSW 均为 0，continuity 分别为
0.985915/0.985816，混淆矩阵始终是一对一；不足 1.0 只来自启动前 2 帧无 D2 航迹。

### GAP 判定

- **已关闭**：修复后同 seed 的 `T008`/额外 birth 复发；单 seed 活动 canonical
  track 数和生命周期异常；在线 truth 泄漏。
- **仍开放 P1**：普通 M5N2 数量已达到 20 case；剩余验收改为至少 10 个显式包含
  重复 D1 source、teleport、dropout、clutter 和合法新目标的受治理 case，统计
  suppression recall/false suppression，并按 seed 输出 offline IDSW/continuity
  availability 与置信区间。
- **证据限制**：本批平稳 episode 的 suppression/quarantine 均为 0，只证明没有
  误触发，不能替代已通过的匿名 teleport fixture，也不能证明真实扰动下召回率。
- **代码决定**：未发现 D2-owned 断点，不修改默认 GNN/Hungarian、gate、生命周期
  参数或 `global_track_id` 合同；P2 optional 状态不变。

## 15. 2026-07-15 Continuity Admission P1 收口

### 已关闭

- v1 固定 `+0.10` continuity 绝对提升在高基线下不可达的问题已关闭。v2 使用
  `H=max(0,1-C_b)` 和 `Delta_req=min(0.10,0.10H)`，保证
  `C_b+Delta_req<=1.0`。
- 每个候选显式输出 baseline/candidate、headroom、实际/所需提升、error reduction
  fraction、policy version、逐 gate `passed/reason/actual/required`。
- 缺指标、非有限/越界、continuity 退化、baseline IDSW=0、false-track 超限、P95
  超预算和 truth leakage 均有 fail-safe 回归；IDSW 单项通过不能形成 promotion review。
- v1 `+0.10` 仅作为 `legacy/deprecated` 审计字段，`used_for_admission=false`；v2
  通过仍只推荐人工/主流程评审，`default_online_path_changed=false`。

### 验证与证据限制

- 2026-07-15 D2 完整回归：`113 passed, 1 warning`；验收阈值为零失败。warning 是
  Matplotlib `Axes3D` 环境问题。
- 本批未运行 AirSim，使用已冻结的真实 replay/truth 离线重算。总体五项 gate 的完整
  v2 证据已可用，promotion review recommendation 为 true；仍不得把 recommendation
  解释为默认路径已改变。
- dropout 档有 20 个 partial truth alignment case 和 440 个 unmatched evaluator
  sample；没有最近邻补齐，在线 truth leakage 仍为 0。

### 后续 P1

- main/D6 复核总体 recommendation 与分档 fail-closed 差异；任何正式默认参数变更都应
  另建版本化决策，不由本 runner 自动执行。
- 更长 OOSM/遮挡/杂波、M-of-N/lifecycle 和跨节点 owner/epoch 标定状态不变。

## 16. 2026-07-16 来源身份治理审计指标 GAP 收口

### GAP 变化

- **已关闭 D2-owned P1 接口缺口**：来源绑定冲突和来源不连续隔离此前只有逐帧明细，
  现已分别形成 `source_binding_conflict_count` 与
  `source_lineage_quarantine_count`；上游本地身份塌缩拒绝形成独立的
  `upstream_local_identity_rejection_count`，三项进入 metrics、risk 和 replay
  逐 seed/聚合输出。
- **fail-closed 边界已关闭**：上游拒绝计数只接受验证后的 frame metadata 非负整数；
  缺失为 0，负数、布尔、浮点、字符串和 `None` 在 tracker 状态变化前拒绝。
- **身份权威未变化**：source/local ID 仍仅是 namespaced lineage。D2 不消费原始像素，
  不复制 `bright_hungarian`，不从审计计数创建 Detection/Track，也不把 local ID
  复制或重绑为中心 `global_track_id`。`id_switch_count` 仍显式保留并仅由可用离线真值
  解释。

### 验证证据

- 日期：2026-07-16；专项样本：连续同源、binding conflict、Mahalanobis discontinuity、
  零检测 upstream audit、5 类非法 metadata 和 legacy 无 metadata。
- replay：synthetic seed 7/8，各 3 帧；conflict=`1/1`、quarantine=`1/1`、upstream
  rejection=`2/4`，聚合均值=`1/1/3`。阈值为精确一致且旧流程三项为 0。
- 全量 D2：`123 passed, 1 warning`，验收阈值零失败；warning 是环境 Matplotlib
  `Axes3D` 导入，不影响结果。未启动 AirSim，未产生新的真实飞行证据。

### 仍开放

- 真实 AirSim 至少 10 个 duplicate-source、teleport、dropout、clutter 和合法新目标
  受治理 case 的 false-suppression/recall、offline IDSW/continuity 与置信区间仍为 P1。
- main/D1 的 namespaced `source_track_ids` 与可信 upstream rejection metadata 生产、
  D6 跨模块总报告接入由各 owner/main 后续完成；本轮未修改默认关联器、门限或风险分类。

## 17. 2026-07-20 六维稀疏关联 GAP 判定

### 已关闭的 D2-owned GAP

- 六维 NED state/covariance、三维位置 innovation/Mahalanobis gate；
- 面向 200 目标的 KD-tree 空间索引、稀疏候选边和分量级 Hungarian；
- 不分配/保存无条件全密集 cost/distance history，有界 track/frame 审计；
- D2/中心创建 `GT3D-*`，上游 canonical ID、truth/actor/object identity 不具备权威；
- D1 fused-track adapter 对齐 state-valid association epoch，并保留原始 source
  measurement/arrival timestamp 供延迟审计；
- D1 fused-track adapter 保留完整 6x6 covariance 和 position-velocity cross block；
  相关 source posterior 不再被重复当作独立位置量测，固定权重 CI 与速度创新 NIS
  covariance inflation 已实现；
- 在线显式 unavailable 的 IDSW/continuity、identity-free risk summary，以及隔离 offline
  evaluator 的可用 IDSW/identity/coverage continuity；
- 5/20/50/100/200、crossing、连续漏检、虚警和无固定 2v2/5v5 测试。

### 证据

- 2026-07-20 原六维专项 `13 passed`，新增速度专项 `3 passed`；完整 D2
  `139 passed, 1 warning`，验收阈值零失败。
- 200 目标规则网格：3 个独立 trial，每个预热 1 帧后测量 30 帧；90 个测量帧的
  候选/全对均为 `200/40,000`，分量矩阵 `200`，peak component `1`，裁剪 `99.5%`。
- 聚合关联 mean/P50/P95/max `6.683/6.306/7.056/22.471 ms`；tracker step
  `25.491/25.016/26.797/41.613 ms`。
- crossing、漏检和虚警专项离线 IDSW 均 0；在线层未读取 truth，在线身份指标为
  `None + unavailable`。

### 未关闭

- main-owned `scalable_3d_simulation` 修复后 50v50/200v200、D3 reachability 和
  D1/D3/D5/D6 版本化 schema 验收；
- 至少 20 个未见 seed、密集交叉/编队分裂/多高度/协方差膨胀下的候选召回与置信区间；
- 极端大连通分量的候选预算/区域分解及其 identity recall 损失控制；
- 六维 JPDA/MHT、OOSM 回溯/平滑、EKF/UKF/IMM、真实 AirSim 子场景和端到端
  200v200 证据。

本轮只关闭 D2-owned 规则基线，不把单布局性能写成实时 SLA，也不重分类跨模块 owner 的
集成 GAP。

## 18. 2026-07-20 六维速度稳定性 GAP 判定

### 已关闭的 D2-owned 缺口

- **完整 covariance 丢失**：`Detection3D.state_estimate_covariance` 现在显式携带 D1
  source posterior 的 6x6 covariance；position/velocity marginal 必须匹配，交叉块不再
  在 adapter 边界丢失。
- **相关 posterior 重复消费**：旧路径出生后只做位置 Joseph update，把 D1 历史 posterior
  当作新独立位置量测，导致 Ppv 把位置 random-walk residual 注入速度并伪收缩 Pvv。
  相关 source posterior 现走 6D covariance intersection；独立六维量测和 position-only
  量测分别保留 6D/3D Joseph update。
- **速度离群影响无界**：velocity NIS 超三自由度 99% 门限时按 `NIS/gate` 做 covariance
  inflation；关联速度 cost 在门限处封顶。位置可行性仍只由 3D Mahalanobis gate 决定。
- **合同保持**：没有 truth/actor/object ID、速度模长上限、4.7 m/s 常量或场景特判；
  `GT3D-*` 仍由 D2 创建，稀疏候选、IDSW/continuity availability 和 offline evaluator
  边界保持。

### 定量证据与门限

- main 只读 50v50、seed 17、2.2 s、radar-only 触发证据：D1 速度
  `6.28/12.16/21.03 m/s`、Pvv trace `101.24/110.31/112.32`；旧 D2 为
  `8.89/17.43/27.49 m/s`、trace `62.95/69.37/70.86`。该批尚未在修复后由 main 复跑。
- D2 synthetic seed 17、50 条、12 帧：输入速度 `5.415/7.960/12.274 m/s`，旧 D2
  复现 `9.41/14.31/21.88 m/s`、trace `62.76`；修复后
  `5.082/6.401/7.218 m/s`、trace `101.181`。位置 RMSE
  `52.634 -> 48.364 m`，IDSW 0、continuity 1.0。
- D2 synthetic seed 41、200 条、10 帧：每更新帧 candidate/dense pair
  `200/40,000`，活动航迹 200，输入/输出速度 P90 `8.097/5.980 m/s`，输入/输出 Pvv
  trace 中位数 `75/69.685`，IDSW 0、continuity 1.0。
- seed 29、21 帧双目标 crossing 注入一次速度离群值，update NIS gate 与有限速度 cost
  均触发；交叉帧候选 4，活动航迹 2、IDSW 0、continuity 1.0。
- 验收门限为输出速度 P50/P90/max 不超过相应输入的 `1.05/1.05/1.00` 倍，Pvv trace
  中位数不少于输入的 90%，位置 RMSE 不退化，50/200 活动航迹数准确且 IDSW 0、
  continuity 1.0；全部通过。

### 仍开放的 P1/集成风险

- `correlated_state_ci_track_weight=0.5` 只是固定 baseline，未证明最优。至少 20 个未见
  seed 的权重 sweep、置信区间和不同 covariance correlation 结构仍需完成。
- 当前有逐更新 velocity NIS 和门控诊断，但没有按距离、频率、模态和场景分组的六维
  NIS coverage；离线 identity/position 标签没有形成六维 NEES coverage。
- CV 模型下的持续加速度、协调转弯、长漏检和 OOSM 未标定；高机动中 NIS inflation
  可能保守滞后，不能据当前规则样本冻结 process noise 或 CI weight。
- main owner 需复跑修复后的 50v50/200v200，报告 D1/D2 速度与 covariance 分位数、
  D3 reachable count 和端到端时延；模块合成证据不能替代该验收。
- 本内部 CI 处理同一 source posterior 的未知时序相关性，不改变跨节点 exact/CI 数值
  融合仍由 D1 owner 执行的职责边界。

## 2026-07-20 Scalable 3D evaluator identity GAP 重分类

### D2-owned 缺口关闭

此前 scalable 3D online publication 只能正确声明 IDSW/continuity unavailable，缺少
可审计 `global_track_id -> truth_target_id` 事后映射。D2 现新增五个 `v1` schema、
truth-free lineage evidence bundle、严格 observation truth adapter、逐帧 mapping、
MetricsRecorder-compatible identity metrics 和 public evaluation writer/loader。

映射只允许 observation lineage join，不使用名称、actor ID、终态邻近或最近距离；处理
one-to-many/many-to-one、label/lineage 冲突、缺标签、显式 replay、重复 lineage、时间窗
和 lifecycle。任何歧义不强选 truth，任何身份指标不可验证时值为 `None`。文件入口对
evidence bundle、D1、D2、truth 四类 SHA-256、在线 schema、truth isolation 和 record
sequence fail closed；sequence 还必须语义绑定 D1 lineage 与同 frame 的 D2-owned
canonical ID、六维 state/6x6 covariance、lifecycle、association/source observations，
并覆盖完整 D2 track-frame 集合。

2026-07-20 验证为 23 个专项和完整 `162 passed, 1 warning in 30.63s`，验收阈值零失败；
warning 仅为环境 Matplotlib `Axes3D`。覆盖稳定身份、真实 IDSW、一对多/多对一、缺失/
重复/冲突 lineage、replay、标签篡改、时间/lifecycle、无 truth、37 目标动态规模和
artifact round-trip，并增加非六维 source、非 D2-owned ID、在线 IDSW 伪零和矛盾
availability 拒绝。没有 AirSim 或正式多 seed 运行。

### 仍开放且不得混写为已完成

- main 需按 public DTO 持久化 source observation lineage、record sequence 和 evidence
  bundle hash；当前 producer 会跳过无 lineage 的 D2 track/frame，必须保留其
  unavailable/unassigned evidence 才满足完整性合同。D2 不跨模块代改 producer。
- D6 需只消费 public evaluation artifact；legacy 路径为
  `d2.scalable3d_identity_evaluation.v1`，identity commitment 路径为 v2。不得解析 D2
  tracker 私有状态。
- 正式 scalable 3D episode 的多 seed IDSW/continuity/duplicate 性能、阈值对照和置信区间
  未完成。
- 在线 GNN/Hungarian、门限、`global_track_id` owner、JPDA/MHT、控制路径和 online truth
  isolation 均未改变。

因此本项状态为“D2-owned 离线映射与指标合同关闭；main/D6 集成和性能证据开放”。

## 2026-07-22 active-risk seed 1005 重复航迹 GAP 收口

### 已关闭的 D2-owned 缺口

- **陈旧 posterior 重复计 hit**：D2 不再按外层 detection ID 判断证据新鲜度。关联前以
  sensor namespace 和不透明 `latest_observation_id` 建立 observation claim；重复键不
  进入候选图、Hungarian、状态更新或命中计数。同键量测时间冲突按 fail-closed
  quarantine 处理。
- **tentative 短时重生**：tentative 首次无新证据时保留，连续第二次无新证据时删除。
  seed 1005 中 GT4 可由后续新雷达观测重获，只靠同一旧观测维持的 GT6 被删除。
- **重复航迹治理边界**：coalescence 必须同时具备共享 observation/source-track 谱系及
  位置、速度三维马氏门；同帧双方都有新证据时禁止合并。survivor 按成熟度、创建时间、
  hits、misses 和 ID 确定，原 `global_track_id` 保持不变。
- **审计与身份边界**：逐帧和 summary 显式输出 quarantine、timestamp conflict、claim、
  tentative stale drop、coalescence 和 survivor policy；`id_switch_count` 仍是显式
  `None + unavailable`。在线逻辑不读取 truth、actor ID、object ID 或目标名称。

### 验证证据

- 真实集成输入通过 `_make_intervention_scenario(active_risk, seed=1005)` 与
  `Scalable3DEpisodeRunner` 复现。10 个 D2 帧的活动航迹数为
  `5,6,6,5,5,5,5,5,5,5`，最终保留 GT1-GT5，GT4 保留、GT6 删除。
- replay quarantine 9 次、tentative stale drop 1 次、coalescence 0 次、在线 truth 使用
  0 次。该结果说明本例由 freshness/lifecycle 治理关闭，没有通过 1.5--1.6 km 的宽门
  强行合并。
- 5 个合成专项覆盖重复 replay、seed 1005 等价分支、近邻独立目标、共享来源统计门和
  异步时间边界；另有 1 个真实 seed 1005 集成回归。D2 全量结果为
  `168 passed, 1 warning in 26.15s`，验收阈值零失败。

### 当前 GAP 状态

P0 无新增 blocker。stale observation duplicate-confirmation 已关闭。main 先在脏工作树
完成 development 运行，随后以提交 `0fa7c00` 完成 clean-tree 20-seed 复跑：

- main runtime 以 `d2-observation-evidence-governance-v1` 持久化 fresh/replay、claim、
  timestamp conflict、coalescence、suppressed births 和 tentative stale drop 证据；
- active-risk seeds 1000--1019 的 clean manifest 为 `repository_dirty=false`、统一源提交，
  20/20 物理窗和配对比较可用，D4 adoption 188/188，control/treatment 各 1960 条命令，
  100 条离线唯一身份映射；seed 1005 为 GT1-GT5，在线 truth 使用 0。

该 clean 运行 1 s 有效窗内两臂均无 5 m 拦截，counterfactual、causal 和 production
runtime ACK unavailable。它关闭 clean 来源复跑，不证明策略收益、AirSim 或 200v200
性能。

## 2026-07-22 长 episode observation claim P1 收口

### 已关闭的 D2-owned 缺口

- `ObservationClaimLedgerConfig` 以 `d2-observation-claim-ledger-v2` 公开 retention、
  max-count、max-lateness 和 config version。admission watermark 拒绝过旧源量测；claim
  仅在更保守的 safe watermark 后淘汰。
- claim、track 反向 key 和淘汰 heap 常驻内存为 `O(C_max)`。无时间戳 claim 不做不安全
  淘汰，容量满后新 key 按 overflow fail closed。已淘汰旧证据由量测时间水位线阻断，
  不依赖无限 tombstone。
- too-old、同 key 时间冲突、replay、同帧重复、ledger overflow 均有逐帧/累计 reason；
  summary 含 current/peak/evicted、undated、两个 watermark、eviction index、配置版本和
  `tombstone_count=0`。
- `Scalable3DOOSMScanAdapter` 在 Tracker 前对完整 scan 有界缓冲、排序、释放。超窗、早于
  已释放 state、arrival 回退和 buffer overflow 整帧拒绝。Tracker 状态时间不回退；接口
  不声称 fixed-lag rewind/replay。
- 离线 benchmark 在 online step 后接 truth sidecar，输出合法量测误抑制、近邻独立目标
  recall、错误 coalescence、确认延迟和 IDSW；在线 truth use 为 0。

### 验证证据

- 2026-07-22 新增 15 个专项，完整 D2 为 `183 passed, 1 warning in 29.08s`。
- 5 x 500 帧、40 x 200 帧长期循环的 peak/current 不超过 `6N`、overflow 0、evicted >0。
- 3/12 目标、16 帧、0.75 m 间距 benchmark 的合法检测 43/187，false suppression 0、
  recall 1.0、错误 coalescence 0、确认延迟 mean/P95 0.25/0.25 s、离线 IDSW 0。
- OOSM 测试确认有界 inversion 释放顺序为 0.0/1.5/2.0/3.0 s，三个 fail-closed 边界不
  倒序更新 Tracker。

### 仍开放的 P1/集成证据

- main-owned scalable bus 已按公开 DTO/config 接入 ledger/OOSM summary、动态容量、版本化
  replay coast 和 episode-finalize 审计；当前证据没有读取 `_observation_claims` 私有状态。
- 真实 AirSim observation ID 唯一性、源时钟误差、迟到长尾、buffer/ledger 参数、距离/
  遮挡/杂波门限和 false suppression 尚未标定。
- 20/50/100/200 各 5 个 seed 的快速治理已在提交
  `e4d66db02a0b8f1b867a0e81b4a73de84588426b` 上完成
  20/20 formal/clean 复跑，clean 来源缺口已关闭。更多未见 seed、完整闭环
  IDSW/continuity、代表性 OOSM/遮挡/杂波分布和正式循环时延仍缺证据。
- `tentative_drop_miss_threshold=2`、两个 99% coalescence gate 和默认 ledger 参数仍是
  baseline；模块 fixture 不构成 200v200、实时 SLA 或 AirSim promotion。

## 2026-07-22 重复后验 coast P1 修复

### 已关闭的 D2-owned 缺口

- `ReplayCoastConfig` 以 `d2-replay-coast-policy-v1` 固化 grace。只有 reason 为
  `repeated_latest_observation_id`、claim 已绑定现存航迹且距最后一次新鲜更新不超过 grace
  时，才跳过该航迹一次 miss。
- replay 仍不进入关联、量测更新、hit 或 birth，且不刷新 `last_update_time`。超过 grace、
  timestamp conflict、too-old、overflow、未绑定和 dropped 情况继续 fail closed。
- 逐帧和累计 coast count/reason/config/events 已公开；没有新增无界 tombstone 或 coast
  ledger，在线 truth 使用和中心 `global_track_id` owner 不变。

### 模块证据与开放项

- 12 目标 x 200 帧全量后验循环产生 1920 次有界 coast，所有航迹 misses=0，claim
  peak/current 未超过 max-count。超时和冲突专项均恢复 miss。
- main-owned bus 已接入 `ReplayCoastConfig` 和 coast 审计字段。上游在调用 D2 前合并尾部
  后验时，单 episode replay 可以为 0；该结果不削弱上述 bounded replay 模块证据。
- 真实 AirSim 的合理 grace、不同雷达周期、抖动和失联长尾仍是 P1 标定项。

## 2026-07-22 scalable 尾部合并后 GAP 复核

### 当前已闭合

- main 在 episode 结束时逐条融合 D1 尾部扫描，只把最终后验送 D2 一次，并禁止该路径
  产生控制命令。seed 1005、1.1 s 当前有 2 个 D2 帧、每帧 5 条航迹，birth 5、claim 10、
  replay quarantine/coast 0、stale drop 0、coalescence 0、online truth use 0。
- D2 finalize 调用 1 次，`coalesced_release_count=5`。旧的 7 帧、claim 26、replay 9 已被
  当前 main 行为取代，不能作为现行验收口径。
- seed 1011/1019 在 1.0 s 干预帧只有 4 条在线航迹，来源是检测概率 0.98 下首扫漏检和
  后续量测到达时延。D2 在 1.05/1.10 s 接纳第 5 条新鲜证据，终态 5 confirmed，拒绝、
  coalescence 和 drop 均未损失合法目标。

### P0 验证口径收口

seed1005 复现报告升级为 v3，接受 replay=0 或正数 bounded replay。两种分支都强制全部
发布帧为五条规范中心航迹、owner 为 `D2_center`、birth 5、quarantine 与 coast 一致、
无 stale drop/错误合并且 online truth 0；正数 replay 只允许
`repeated_latest_observation_id` 原因。当前 1.1 s 和 2.2 s main 路径 replay 均为 0，
专项 2 个测试和完整 `189 passed, 1 warning` 均通过。该项 P0 验证 blocker 已关闭，
D2 算法未修改。

### P1 仍开放

- 真实 AirSim observation ID、时钟偏差、雷达周期和 replay grace 尚未标定。
- 干预帧在线航迹覆盖率、初始化延迟和离线 IDSW/continuity 仍需多 seed 统计。
- target inventory 必须按实际 D2 快照连接 D3；离线 `target_count` 差额只作 availability，
  不得用 truth 补轨。

## 2026-07-22 多规模治理 formal/clean 证据

### 已获得证据

- 200v200、seed 42000、2.2 s 持久化制品将尾部 31 次 D2 调用合并为 1 次，记录
  `coalesced_release_count=30`。常规/尾部 D2 时延为 6.135/2.033 s，claim
  current/peak/capacity 为 1583/1583/60000，overflow、too-old、coalescence 和 online
  truth use 均为 0。
- 合并前 development 制品的 claim 为 1976/1976。它与单次 finalize 制品不是同一运行，
  不能混合报告。
- 快速治理的 development 数值已在提交
  `e4d66db02a0b8f1b867a0e81b4a73de84588426b` 上完成 formal/clean 复跑。
  20/50/100/200 各 5 seed，共 20/20 formal episode；20 个 manifest 均为 clean 且绑定该提交。
- 四档 claim peak/capacity 为 2390/4800、6020/12000、12070/24000、24170/48000，
  safe evicted 为 285/735/1485/2985，overflow/too-old 均为 0。near-neighbor recall 均为
  1.0，false suppression 和 erroneous coalescence 均为 0，confirmation latency
  mean/P95 均为 0.25/0.25 s。
- 20 个 sidecar 均为 evaluator-only 且未被在线消费，online truth use 为 0。输入清单
  登记的 20 个 manifest、20 个 online audit 和 20 个 sidecar 共 60 个 SHA-256 已全部重算通过。

### GAP 判定

初次 development 批次的 `formal_episode_count=0` 仅作历史记录。新批次以每个 manifest
的 formal/clean provenance 和 aggregate 每档 `formal_episode_count=5` 为验收依据；
`runner_summary.json` 顶层不提供该分档计数，不将其缺失值解读为 0。该结果关闭
clean 提交上的四规模观测治理复跑，但不关闭以下项目：

- 每档更多未见 seed 及代表性漏检、遮挡、杂波和 OOSM 难度分布；
- 完整 200v200 感知、关联、分配、降级、视觉、制导闭环；
- 真实 AirSim 和多场景离线 IDSW/continuity 身份指标；
- 最坏大连通分量、循环时延预算和实时服务等级。

本次没有改变 GNN/Hungarian、门限、claim/coast 算法、中心 ID ownership 或控制接口。

## 2026-07-22 200v200 关联热路径 GAP 收口

### 已关闭

- 以 clean 基线 `nominal/200v200` seeds 42000--42004 建立冻结输入和阶段 profile，确认
  主要热点位于在线 metadata 身份递归审计及 adapter 重复扫描；稀疏 GNN/Hungarian
  不是本批主要开销。
- 优化限于等价身份审计：容量 1024 的字符串分类缓存、原生前后缀判断和删除 adapter
  冗余预扫描。`Detection3D` 构造审计与 Tracker step 审计都保留，构造后篡改仍拒绝。
- 新增 `d2-scalable3d-performance-comparison-v1` 对照合同。45/45 周期的完整发布、关联、
  中心 ID/生命周期、claim/审计和逐周期哈希一致；场景配置及 offline truth sidecar 哈希
  一致，在线 truth use 为 0。
- 常规关联、finalize 和合计平均墙钟分别为
  `7.5552 -> 2.2033 s`、`2.2747 -> 0.5646 s`、`9.8299 -> 2.7679 s`；五 seed
  D2 总墙钟 `49.1497 -> 13.8397 s`。

### GAP 判定

第二阶段 D2-owned 热路径性能 GAP 已在开发态候选上收敛。默认 GNN/Hungarian、三维门控、
中心 `global_track_id`、claim ledger、生命周期和显式 ID switch/continuity availability
语义均未改变。候选尚未形成 clean-tree promotion，因而不把本结果写成正式实时 SLA。

仍开放的 P1 证据是固定环境 clean 复跑、真实 AirSim observation ID/时钟分布、代表性
遮挡/杂波/OOSM、极端全重叠大连通分量和完整离线 IDSW/continuity。以上开放项不得通过
放宽在线身份审计、claim 或门控来换取时延。

## 2026-07-22 长时重复元数据审计 GAP 收口

### 已关闭

- 10 秒、48 周期 profile 将增长源定位到 D1 批内共享诊断树的逐轨重复递归审计；
  GNN/Hungarian、claim summary 和 duplicate coalescence 不是本批主要热点。
- D1 批输入先完整执行禁用身份键审计。内容相等的 `sensor_health`、
  `association_audit`、`latency_audit` 只递归审计一个代表，任一不同值仍完整审计。
- 审计后只携带 D2 消费的时间、谱系、来源、模态和帧字段。构造与 tracker step 的二次
  审计保留，单轨 truth 注入和构造后篡改继续 fail closed。
- 最终审查加固代码的可复现 200 航迹、48 周期基准为
  `16.858297 -> 6.472896 s`，加速 `2.604444x`，48/48 周期语义一致。未知或自定义
  Mapping 始终完整审计，恶意恒真 `__eq__` 且第二项含 `truth_id` 的测试 fail closed。
- 五 seed 45/45 周期及 10 秒 48/48 周期的完整发布、关联、中心 ID/生命周期、claim/审计
  哈希一致，在线 truth use 为 0。对应 `13.3842 -> 4.9606 s` 和
  `37.0072 -> 5.6582 s` 计时属于审查加固前候选，最终加固性能需 main 复跑。

### GAP 判定

D2-owned 长 episode 重复元数据审计 P1 缺口关闭。默认三维门控、GNN/Hungarian、关联
频率、中心 `global_track_id`、claim/replay/stale、生命周期和显式 IDSW availability
未改变。真实 AirSim 时钟/observation ID、遮挡/杂波/OOSM、极端大连通分量和固定硬件
循环分位数仍保持原 P1 状态，不由本批质点回放代替。

## 2026-07-22 关联内核重复计算 GAP 收口

### 已关闭的 D2-owned 缺口

- 以 clean 基线 `8f86192` 的 10 秒、200v200、seed 42000 frozen online observations
  重建 48 周期。只读取 online bus，不读取 truth sidecar，online truth use 为 0。
- baseline/candidate 的 1,820,766 个 dense pair、9215 个空间候选/位置马氏求解、9017
  条合法边、9012 个匹配及全部 fresh/replay/分量诊断相等；峰值 component matrix size 2。
- 实施批量 covariance eigenvalue/KD-tree query、匹配 velocity NIS 复用、consistent D1
  covariance governance 复用和 1x1 assignment 快路。regularized covariance 仍走完整
  fallback，不减少输入、频率或合法候选，不放宽门控。
- 修复初版预验证构造参数绕过：最终 dataclass field 为 `init=False`，普通构造不能声明
  trusted covariance。边缘正定但整体非 PSD 的 6x6 交叉 covariance 及伪造 consistency
  负例仍被 full governance 拒绝；公开 DTO/序列化不变。
- 48/48 周期完整语义 SHA-256 同为
  `dd3f65f01fd5e0941fe5c37def42650edd7107213f7ae97c528c64688a8721ab`。7 次计时中位数
  `4.859477 -> 4.018963 s`，加速 `1.209137x`；完整测试
  `219 passed, 1 warning in 41.91s`。

### GAP 判定与剩余 P1

nominal frozen point-mass replay 上的 D2 association 内部重复计算缺口关闭，不提升为
AirSim、实时 SLA 或完整闭环结论。以下 P1 不变：真实 observation ID/时钟/雷达周期，
遮挡、杂波、漏检和 OOSM 多 seed 分布，最坏全重叠大连通分量，固定硬件逐周期
P50/P95/P99，多场景 offline IDSW/continuity，以及完整 200v200 D1-D7 闭环。不得通过
减少输入、降低频率、截断合法候选、放宽门控或使用 truth 关闭这些项目。

## 2026-07-22 三 seed clean 集成 GAP 重分类

### 新增证据

- reference `8f86192` 与 candidate `f80b5bd` 均使用独立 clean 输出；场景为 nominal
  200v200、10.0 s、seeds 42000/42001/42002。三个 episode 均有限，online truth use 为 0。
- 每 seed 的 D2 association 调用数均为 47；累计耗时三 seed 均值
  `8.317513 -> 7.671266 s`，约下降 `7.77%`。
- 终态 D2 航迹数按 seed 为 `205/204/203`，reference/candidate 逐组相同。在线逐条语义
  和 topic counts 三组全部通过。
- 跨模块审计只规范化独立 D3 planner 的 opaque `plan_id`，按 plan occurrence/version
  映射，并在映射前验证 ACK 原始载荷 SHA。owner、version、coalition、
  `global_track_id` 和 command 业务字段没有被忽略；D2 记录本身未做该规范化。
- 当前工作区完整 D2 回归 `219 passed, 1 warning in 49.75s`，验收阈值零失败；warning
  为环境 Matplotlib `Axes3D` 导入提示。

### GAP 判定

“最终加固代码尚缺 nominal 200v200 clean 集成复跑”已关闭。批量 KD-tree/eigenvalue、
同周期 velocity innovation、可信 covariance governance 和完整门控后的 1x1 component
bypass 获得三 seed 非退化证据。以下 P1 继续开放：

- 短长对照中的 D2 association 超线性增长和固定硬件逐周期 P50/P95/P99；
- 真实 AirSim observation ID、源时钟、雷达周期及迟到分布；
- 遮挡、杂波、漏检、OOSM 和极端大连通分量的多 seed identity/runtime 联合标定；
- 隔离 offline IDSW/continuity 置信区间、六维 NIS/NEES 和 CI 权重；
- 完整任务效果及物理拦截验收。三 seed nominal 语义相等不能替代这些证据。

## 2026-07-22 部分离线身份证据 GAP 收口

### 已关闭

- evaluation v1 新增可选 `d2.scalable3d_partial_identity_diagnostics.v1`。严格
  `id_switch_count`、continuity、duplicate、confusion matrix 的字段和值及全局
  fail-closed 语义未修改。
- 新诊断明确区分全部 mapping、`created/matched` 受评分 mapping、可评估 mapping、
  ambiguous、unavailable、mapped-truth-not-present 和 missing identity evidence。
- mapping、完整帧、相邻真值转移三个 coverage 都带分母、availability 和 reason。
  零分母保持 unavailable。
- 只发布可证明 IDSW lower bound。每个真值帧必须恰好有一个唯一可评估全局航迹才能成为
  锚点；多航迹重复映射被排除并带 reason count，不能复用严格指标的代表顺序。没有唯一
  锚点转移时下界 unavailable；缺失/歧义证据下不发布 upper bound。
- loader 从逐帧 mapping 复算诊断并拒绝矛盾制品。在线 DTO/log 不含 truth 或部分诊断。
  相关身份测试共 32 项；完整 D2 为 `228 passed, 1 warning in 29.26s`。

### 单 seed 证据

clean source commit `0d2da25` 的 nominal 200v200、10.0 s、seed 1000 只读复算保持
9644 条 mapping 的 `8906/13/725` 状态计数。受评分 9038、非评分状态审计 606、
可评估 8906，coverage `0.985395`；missing 119，完整帧 3/48，相邻转移 0/9400，
1 个真值帧因多条可评估航迹被排除。该帧原本也不完整，因此仍由 385 个唯一锚点区间证明
lower bound 7。严格 IDSW 仍因 `multiple_truth_targets_for_global_track` 为 unavailable。
本节没有验证其余 19 个 seed。

### 仍开放

1. main 重新生成正式多 seed evaluation 和 manifest hash。
2. D6 接入部分诊断并与 strict IDSW 分栏汇总；不能以下界填充严格指标。
3. 真实 AirSim、遮挡/杂波/漏检/OOSM 和不同目标密度下的 coverage/blocker/下界分布。
4. 完整 sidecar 条件下的严格 IDSW/continuity 置信区间。upper bound 当前明确不可用。

## 2026-07-23 clean `4ac3bb2` seed 1000 性能 P1 归因与重分类

### 新增证据与实现

- 原完整阶段在 nominal 200v200、seed 1000、10.0 s 有 47 次 regular association，
  P50/P95/max 为 `121.972/137.335/145.966 ms`；10.0 s 相对 2.2 s 的单次成本约
  `1.579x`。本轮未改 main-owned lineage/publication，也未重跑完整阶段。
- v2 profiler 正确处理 D1 与 MAIN/D5/D7 交错记录，从冻结在线总线恢复 48 个 D2 周期。
  输入 SHA-256 为
  `c1dda8523e48c255bbeef48d9516b05863eb1bbb3a3ae2e09733259e6a66f77a`，
  truth sidecar 未读，online truth use 为 0。
- profile 定位到三个低风险热点：相同 `dt` 的 CV matrix 重建、可信 D1 covariance
  marginal 的两次冗余 `allclose`、claim ledger summary 的重复扫描/生成。候选分别采用
  单周期唯一 `dt` 复用、仅限同一已治理 ndarray 原生 marginal 的可信跳过、增量精确
  ledger 计数和每帧一次 summary。普通/regularized covariance 仍完整验证。
- 同输入旧/新 48/48 周期公开输出与 tracker 状态严格相等，语义 SHA-256 均为
  `b2334c619b9d2f7c467387ad27b62614d028af83f0b7842b867cab1c4aa9824b`。
  input/fresh/replay/candidate/matched 为 `9626/9038/588/8862/8823`，两侧相同。
  逐条发布、中心 `global_track_id`、显式 IDSW availability、门控、版本、claim ledger
  和 truth isolation 未改变。
- CPU 0、BLAS/OMP 单线程、1 次 warmup、7 次计时下，D2 core 中位数
  `2.928830 -> 2.204672 s`，描述性加速 `1.328465x`。报告 SHA-256 为
  `2256d6fdd29223ed5dd75351cd6bb208a4d67c55925eeba047620ac865b6c7da`；测试策略不以
  墙钟作硬断言。完整 D2 为 `234 passed, 1 warning in 34.83s`。

### GAP 判定

“缺少可复现 clean seed 1000 profiler”以及上述三个固定操作数热点已关闭。性能增长 P1
保持开放：基线/候选早晚 regular 窗口比分别为 `1.119661x/1.123036x`，候选没有改善
窗口增长；完整阶段的 `1.579x` 也未由本轮 D2 core 回放替代。后续仍需固定硬件完整阶段
P50/P95/P99、多 seed 长短窗口、main-owned lineage/publication 分离，以及真实 AirSim
时钟、困难观测分布、极端大连通分量和 offline IDSW/continuity 联合验收。不得通过
降采样、减少合法候选、放宽门限、降低关联频率、修改 ID/claim/version 语义或在线 truth
关闭该 P1。

## 2026-07-23 20-seed 严格身份阻断 GAP 重分类

### 已关闭

- 新增 `d2.scalable3d_identity_blocker_diagnostics.v1`，按 reason、航迹和连续时间段
  固化 observation ID、量测时刻、谱系哈希和独立 truth label 状态。
- 新增 D1 `d2_lineage_mapping` 完整性审计。只有全量 estimate observations 都具有唯一
  label 和唯一 D2 track claim 时才输出 D1-compatible records；不完整时 records 为空。
- clean `5263e2b` nominal 200v200、10 秒、20 seed 的 source SHA、producer replay 和
  online truth isolation 均为 `20/20` 通过。strict unavailable 原因已从单 seed 推断
  提升为正式多 seed 可复核证据。

### 证据分型

1. **真实混轨**：118 个多真值航迹帧、107 个连续区间。不同真值由同帧独立 observation
   lineage 支撑，不能通过放宽 evaluator 分母修复。
2. **sidecar 信息不足**：2464 个受评分映射缺显式 label；D1 可用估计侧为 2474 条。
   现有 schema 没有覆盖已知虚警和未知标签的 disposition，D2 不从名称推断。
3. **D1 consumer coverage**：188951/191425 条可形成唯一候选，完整 episode 为
   `0/20`。没有发现独立于标签缺失之外的 D2 lineage claim 缺口。
4. **部分诊断**：mapping/frame/transition 为
   `178531/181110`、`103/959`、`1149/187800`；IDSW lower bound 合计
   `199/15215` anchor intervals。strict 未回填，upper bound 未生成。

### 仍开放的 P1

- D1 雷达/视觉跨模态门控和混轨航迹分裂；D2 只提供精确失败区间，不跨模块修改。
- 传感器/main producer 对 observation 全集的 truth target、known false alarm 和
  unknown label 显式处置与完整性摘要。
- D1/main 对已知虚警存在时的部分 RMSE/NEES coverage 合同，以及新制品上的
  `d2_lineage_mapping` 全覆盖验收。
- strict IDSW/continuity 在修复后 producer 上的多 seed 可用性和困难场景置信区间。
- 原有固定硬件时延、AirSim 时钟、遮挡/杂波/OOSM 和极端候选图 P1 状态不变。

本轮完整 D2 为 `238 passed, 1 warning in 32.88s`；warning 为既有 Matplotlib
`Axes3D` 环境提示。`AIRSIM_INTEGRATION_PLAN.md` 已检查，本次未改变 AirSim 输入、话题
或运行接口，因此不更新。

## 2026-07-23 observation truth v2 GAP 收口

### D2-owned 已关闭

- `d2.scalable3d_observation_truth.v2` 已定义 target、known false alarm 和 unknown
  三种显式处置；旧 D2/producer v1 target-only 输入兼容。
- load/write/hash、文件来源校验、严格 evaluator、partial diagnostics、blocker
  diagnostics 和 D1 mapping audit 已接入。禁止名称、距离、actor 或在线状态推断。
- 纯虚警不进入身份分母；target 与虚警混合保留 target 并审计；unknown、冲突、重复和
  时间戳不一致继续 fail closed。该改动未触碰在线关联路径。
- 新增 11 项专项测试；完整 D2 `249 passed, 1 warning in 32.08s`。冻结
  `5263e2b` seed 1000 的旧 v1 producer evaluation 重放一致。

### 仍开放的 P1

- main/传感器 producer 尚未实际为 `_append_false_alarms` 等虚警生成 v2
  `known_false_alarm` 记录，也未提供 observation 全集完整性摘要。
- 旧 20-seed strict 仍为 `0/20` 可用。v2 只能消除真实虚警造成的缺标签，不能跳过
  118 个多目标混轨帧；D1 跨模态门控和航迹分裂仍开放。
- main 生成新 v2 制品后，需重跑 seed 1000--1019，校验 missing/unknown/conflict、
  disposition audit、D1 mapping coverage 和 strict availability。
- 固定硬件时延、真实 AirSim 时钟、遮挡/杂波/OOSM 和极端候选图 P1 保持不变。

本次接口变化已同步 `AIRSIM_INTEGRATION_PLAN.md`。D1 partial RMSE/NEES 如何排除已知
虚警仍由 D1/main 定义，D2 只发布 target mapping 与 exclusion audit。

## 2026-07-23 identity commitment evaluator audit GAP 收口

### D2-owned 已关闭

- 新增 `d2.scalable3d_identity_evaluation.v2` 和
  `d2.scalable3d_identity_commitment_audit.v2`。v2 evaluation 嵌入受 evidence bundle
  SHA-256 约束的 truth-free `identity_evidence_records`；v1 保持原 schema。
- audit 明确输出 all-record 与 created/matched observed-record 两套 denominator、
  committed/uncommitted count 和 coverage，并输出 commitment reason counts、
  `identity_recovery_blocked_*` counts、blocker count summary、水位线年龄 summary、
  overflow record/track count。
- 未提交 candidate/source binding violation count 必须为 0。loader 从 v2 records 和
  frame mappings 重算审计，拒绝缺字段、篡改值和负水位线年龄。私有 blocked keys 不
  进入公开制品，跨未提交空档的 committed anchor 规则未变。
- 新增 5 项 evaluator 专项测试；完整 D2 为
  `286 passed, 1 warning in 29.22s`。验收阈值为零失败，warning 为既有 Matplotlib
  `Axes3D` 环境提示。

### 系统接线证据

- main 已将真实 scalable episode 的 `identity_commitment_by_track` 原子持久化为 v2
  evidence/evaluation；D6 已消费两类 denominator、恢复原因、水位线年龄、overflow 和
  violation 字段。发布新鲜度配置已升级为
  `d2.identity-commitment-recovery-config.v2`，默认使用固定 `0.9 s` 预算。
- clean 提交 `ff881316243ff5a2991a4659ab78637ed625d123` 已复跑 nominal 200v200、
  2.2 s、`recon_count=2`、seed 1100。D2 离线评估与 D6 episode record 均确认 strict
  指标 available，且没有回填 strict IDSW。
- baseline/candidate 的 9 条 D2 发布均使用
  `d2.identity-evidence-commitment.v2` /
  `d2-structural-ambiguity-commitment-v2`。实际集成配置
  `main-scalable3d-identity-recovery-publication-freshness-v1` 的规范化 SHA-256 为
  `sha256:bd8e362ec4ca128ed902826750b26d862286770d3c0c4d0b75960a50911a201a`；
  manifest v2 已确认逐发布一致性并绑定原始 D2 JSONL。配置谱系 P1 已关闭。
- nominal 200v200、2.2 s、`recon_count=2`、seed 1100（首个预留的未见 gate seed）
  的 baseline 为 D2 航迹 203、D3 分配 200、strict IDSW 9、track continuity
  `0.865`、coverage continuity
  `0.870`、commitment coverage `1.0`。
- candidate 为 D2 航迹 201、D3 分配 197，strict IDSW 3、track continuity
  `0.8266667`、coverage continuity `0.8283333`；all-record commitment coverage
  `0.9574706212`，1711 条 committed、76 条 uncommitted。未提交状态为 69 条 active
  hold 和 7 条 after hold；source/candidate binding violation 均为 0，online truth
  use 为 0，duplicate assignment 为 0。
- 三条恢复航迹 `GT3D-000185/000186/000202` 被
  `source_observation_outside_recovery_publication_freshness_window` 阻断，保持
  `identity_uncommitted_after_hold`。该结果关闭发布超龄证据导致 strict-unavailable
  的合同缺口。

### 仍开放的 P1

- v2 合同、发布新鲜度门控、strict 指标可用性和 fail-closed 行为通过。算法候选仍未
  通过准入：D2 航迹 `203 -> 201`、D3 分配 `200 -> 197`、track continuity
  `0.865 -> 0.8266667`、coverage continuity `0.870 -> 0.8283333`。
- IDSW 单项由 9 降至 3 不能覆盖数量、连续性和覆盖退化。后续结构歧义候选必须先解释
  hold 对航迹维持、建轨和下游分配的影响，并满足联合非退化门槛。
- 固定 `0.9 s` window 不扩大。候选保持默认关闭，seeds 1101/1102、10 s 和 20-seed
  矩阵停止。本候选真实 AirSim 尚未执行；当前不以更多 seed 掩盖首个 gate seed 的明确
  退化。

## 2026-07-23 结构歧义租约因果审计

### 已关闭的审计缺口

- 已定位 `201` 条终态航迹：候选累计创建 203 条，
  `GT3D-000133/000164` 在前两帧后退出；其后继碎片形成 candidate 全部 3 次 strict
  IDSW。
- 已定位 9 条终态未提交航迹：4 条释放后无新证据、3 条发布年龄
  `0.9308153039 s > 0.9 s`、2 条活动租约。三条超龄恢复拒绝正确。
- 五组 detached clean 参数扫描均完成。所有组合 D2 终态均为 197，没有一组关闭
  baseline-relative 航迹、分配和连续性退化。
- 已联接 D3 计划：第 2/3 版计划分别使用 11/8 条未提交航迹，证明 197 不能作为
  committed 可分配数解释。

### 仍开放的 P1

- 当前 prediction-only hold 不保留歧义期间的运动学信息。下一候选需定义
  identity-uncommitted 的保守运动学更新，并保持协方差不虚假收缩。
- 旧冻结 seed-1100 制品尚未以 `identity_commitment_state` 过滤新计划或撤回旧计划；
  该历史缺口已由固定提交 `7e15dac9` 的同输入 clean 集成复验关闭。未提交航迹进入
  D3 assignment、D5 active vision 和 D7 guidance 的计数均为 0。
- D1 deferred birth 和结构歧义成员变化仍需 D1 独立判断真假重复；D2 不跨模块归因。
- 候选继续默认关闭，不改 `(2,5)` 和 `0.9 s`，不启动新增 seed、长时或 AirSim 扩展。

完整审计见
`D2_STRUCTURAL_AMBIGUITY_HOLD_LEASE_CAUSAL_AUDIT_CN.md`。

本次复核没有发现新的 D2 代码 P0。2026-07-23 完整 D2 回归为
`291 passed, 1 warning in 31.00s`；warning 为既有 Matplotlib `Axes3D` 环境提示。

## 2026-07-23 clean seed 1100 承诺准入 GAP 更新

### 已关闭的 P1 合同缺口

- 固定提交 `7e15dac9cdaf6743999dfe045a70676fd31a17d6` 在
  `/tmp/MSM-identity-gate-results-7e15dac/{hold_only,hold_plus_centroid}` 完成同输入
  clean A/B。两臂均为 nominal 200v200、`recon_count=2`、`2.2 s`、seed 1100，
  `repository_dirty=false`，场景配置 SHA-256 相同。
- D2 在 `t=1.0 s` 发布 11 条未承诺航迹后，D3 第 2 版计划将其全部拒绝，旧绑定不再
  出现在 assignment，强制重规划绕过迟滞，计划版本严格由 1 增至 2。第 3 版继续按显式
  承诺状态失败关闭。
- D3 拒绝集合与 assignment 的交集为 0；按计划版本联接的 D5 active-vision 和 D7
  guidance 对拒绝集合的命令数也为 0。原“未承诺航迹仍进入下游执行链”和“同输入 main
  集成复验待完成”关闭，后续作为回归合同维护。
- 两臂 online truth use、duplicate assignment、未承诺 source/candidate binding
  violation 均为 0，中心 `global_track_id` 权威未变化。

### 仍开放的 P1 算法缺口

- D2 终态 201、available mapping 1491、uncommitted mapping 76、track continuity
  `0.8266666667`、coverage continuity `0.8283333333`。显式准入没有修复相对早期
  hold-disabled baseline 的航迹连续性和映射可用性退化。
- prediction-only hold 仍会丢失歧义期间的运动学支持。下一候选必须保持身份未承诺，
  不产生硬 observation binding、hit、birth、rebind 或虚假协方差收缩，同时提供可复核
  的保守运动学更新。
- `hold_plus_centroid` 的 46 个候选全部被拒绝，应用分量/成员为 0。该零 treatment
  不能关闭质心候选的有效性、协方差一致性或退化风险 GAP。
- strict IDSW 为 3 只能说明可评分身份切换次数，不能覆盖 track/coverage continuity、
  可用映射和终态航迹退化。结构歧义 hold 与质心候选均不晋级。
- seeds 1101/1102、10 s 和 20-seed 扩展继续停止。真实 AirSim 承诺准入、时钟、遮挡、
  漏检、杂波和固定硬件时延标定仍未执行。

### 优先级

P0 无新增项。P1 下一步仍是 seed 1100 上的 D2 算法候选，而不是放宽 `0.9 s`、调整租约
参数或直接扩展 seed。候选只有在形成非零 treatment 且航迹数、映射可用性、连续性和
安全违规联合非退化后，才可进入 seeds 1101/1102。

2026-07-23 本轮完整 D2 回归为 `291 passed, 1 warning in 29.29s`。warning 是本机
Matplotlib `Axes3D` 环境提示。

## 2026-07-23 结构歧义有界身份假设 C0 GAP 重分类

### 已关闭的规划缺口

- D2 已形成正式 C0 设计
  `research_modules/d2_data_association/docs/STRUCTURAL_AMBIGUITY_BOUNDED_HYPOTHESIS_PLAN_CN.md`。
  文档冻结 D1 双时间戳、allowed-edge、opaque member/source lineage、NIS、
  generation 和 `cross_covariance_available=false` 输入边界，在线 truth 继续禁止。
- 首版推荐 component-local identity-only bounded MHT，并从保留的联合假设导出 JPDA
  风格边缘概率、熵和似然比。原因是 bounded MHT 能保留跨代排他路径，JPDA 边缘概率
  更适合作为承诺门和诊断；该结论不代表现有轻量 `MHTAssociator` 已满足新设计。
- C0 已预注册 200 规模稀疏分量、5-generation/1.0 s 窗口、full/k-best 生成、
  log-domain 归一化、确定性剪枝、birth/death/coast 占位语义、OOSM/generation 幂等、
  commitment 门、fail-closed 矩阵及 IDSW/continuity/可用性/P95/RSS/绑定验收。

### 仍开放的 P1 实现与效果缺口

- 本轮只有 C0 文档，没有 Python、开关、配置类、公开 schema、测试、回放、AirSim、
  P95/RSS 或算法收益证据。C1-C3 全部未开始。
- 首阶段只管理关联/身份假设，不做相关状态融合；因此既有 prediction-only hold 的
  运动学支持、航迹数和 continuity 退化没有被本设计关闭。相关状态处理需在有交叉相关
  模型和独立验收后另行评审。
- 未收敛、溢出、非有限权重、缺代、跨窗冲突和网络超窗均继续
  `uncommitted + hold`；不得创建、改写或局部重绑 `global_track_id`，source token
  不能冒充 canonical ID。D3 继续只消费 committed。
- 默认 GNN/Hungarian、现有 hold 和默认关闭状态均不变。seeds 1101/1102 不恢复。

本轮只关闭“缺少 D2-owned C0 正式计划”的文档 GAP，不关闭结构歧义算法 P1，也不新增
P0 blocker。

## 2026-07-24 已知虚警排除计数合同 GAP 收口

### 已关闭的 P1 评估合同缺口

- D6 严格消费 long seed 1102 reference 时发现
  `known_false_alarm_only_mapping_count=14`，但最终 frame mappings 中只有 11 条
  `excluded/known_false_alarm_only`。D2 producer 原实现按来源 disposition 组计数，
  没有服从最终持久化 mapping 的 status/reason。
- 独立根因复核确认，多出的 3 个组并非排除映射。它们处于 observed `created` 状态，
  但来源超出 lineage window，最终为
  `unavailable/source_observation_outside_lineage_window`。非 observed 且仍带仅虚警
  谱系时也存在同类口径风险。
- producer 已改为直接遍历最终 frame mappings，只统计
  `status="excluded"` 且 `reason="known_false_alarm_only"`。D6 严格校验保持不变，
  truth 隔离和 fail-closed 规则未放宽。
- 真实 200v200、10 秒、seed 1102 制品只读重放得到 `14 -> 11`；除该字段外 evaluation
  payload 完全相同。`target_with_known_false_alarm_mapping_count=133` 和
  `unknown_disposition_mapping_count=0` 保持来源证据组成语义和数值不变。
- 新增非 observed 仅虚警回归；处置专项 `12 passed`，完整 D2
  `292 passed, 1 warning in 28.81s`。验收阈值为零失败和 audit/persisted mapping
  严格相等。

### 仍开放的 P1

- 本修复只恢复 D2 producer 与 D6 consumer 的离线合同一致性，不证明 D2 关联性能、
  strict IDSW、continuity 或系统实时性改善。
- 结构歧义运动学支持、C1-C3 有界身份假设、真实 AirSim、困难场景多 seed 和固定硬件
  延迟仍开放。

P0 无新增项。该问题不要求修改在线 GNN/Hungarian、中心 `global_track_id` 或
AssignmentPlan 合同。

## 2026-07-24 D1 发布审计 v2 消费 GAP 更新

### 已关闭的 D2-owned P1

- D6 的 v1 13 对正式矩阵确认：D1 fusion wall 改善
  `16.29%/31.05%`，但 D2 association 增加 `53.44%/169.89%`，核心墙钟只改善
  `1.65%/1.21%`，未达到 `5%` 门。D2 重复递归扫描共享只读诊断树是明确根因。
- D2 现只信任 D1 公开的精确 v2 根类型、精确递归验证函数和固定
  `d1.publication_audit_tree.v2`。结构验证不能替代 forbidden-key 内容审计；两步均
  通过后才缓存。
- 缓存保存对象强引用，先按 `id` 定位再用 `is` 确认。等值不同身份对象分别验证和审计，
  不调用任意 `Mapping.__eq__` 作为 v2 信任依据。
- 畸形精确构造、v2 子类、truth/actor/object/target/global-track 禁止键失败关闭。
  marker、自定义恒等映射和可变后端只走非 v2 完整审计，不能获得同身份复用。原精确
  内建容器等值代表复用保持。
- 新 typed adapter 返回 `OnlineMetadataBatchAuditSummary`；函数与
  `D1GlobalTrackDetectionBatch` 均通过包 API 和 `__all__` 导出，旧二元入口保持兼容。
  200 航迹三共享根得到 3 次合同验证、3 次内容审计、597 次同身份复用，上游
  `global_track_id` 复制数为 0。
- 2026-07-24 完整 D2 回归为 `305 passed, 1 warning in 29.40s`。warning 是既有
  Matplotlib `Axes3D` 环境提示，不影响合同测试。

### 已关闭的跨模块 P1

- main 已调用带审计入口，并把 `d2_publication_metadata_audit` 持久化到 governance、
  final diagnostics 和 summary。promotion commit `f5b350b` 已默认使用
  `immutable_shared_v2`，`per_track_copy_v1` 保留为显式 reference。
- 2026-07-24 在 clean source commit
  `be399e138762f5e660f553c8caa812d52ab38c61` 上完成 short 10 pair、long 3 pair，
  共 13 pair/26 arm。场景固定为 200 目标、200 资源和 2 侦察节点；26 个 arm 均重新
  运行，`reused=0`、`failed=0`。
- 13/13 pair 的业务语义、有限状态、在线真值隔离、实现身份和 D2 发布元数据审计通过。
  候选累计 702 次精确 v2 合同验证、702 次完整内容审计、139920 次同对象身份复用，
  合同拒绝和内建等价复用均为 0。参考累计 139920 次内建等价复用，所有 v2 计数为 0。
- D2 association short 从 `0.657417 s` 降至 `0.548699 s`，下降 `16.1939%`；
  long 从 `5.869413 s` 降至 `3.774282 s`，下降 `35.6213%`。两档均满足相对参考
  均值增幅 `<=5%` 的门。D1 fusion 和核心墙钟门也通过，D6 判定
  `d1_optimization_admitted=true`。

### 仍开放的 P1

- 最低实时因子为 `0.1730801`，`system_realtime_gap_closed=false`。该结果关闭的是
  发布元数据审计路径回退，不是 200v200 系统实时容量。
- 当前 `latest/totals` 只能证明固定矩阵的累计计数关系；逐批合同验证、内容审计、身份
  复用和拒绝原因明细尚未持久化。
- 本矩阵没有验收 IDSW、track/identity/coverage continuity、RMSE、NEES 或 NIS，
  也不是 AirSim、固定硬件或实飞精度证据。
- 结构歧义运动学支持、C1-C3 有界身份假设、真实 AirSim 困难场景多 seed 和固定硬件
  延迟仍按既有 P1 管理。

本轮无新增 P0。`global_track_id` 继续由中心 D2 所有，发布元数据优化不改变身份、
状态机或下游分配合同。

## 2026-07-25 正式 R0 generation 守恒

### P0 状态

**main runtime 修复已进入正式 source
`1e5ed8ddcf27f375e922a447decfbd875d21bfdf`；3/5 原失败项已正式闭合，完整证据仍
开放。D2-owned 算法无缺陷。**

source commit `2c7b425` 的正式 R0 完成 900 个 episode。5 个 delayed-noisy episode
未通过 generation integrity：5v5 seeds 1000/1005/1008/1018 和 20v20 seed 1009。

900 个 summary 的 finalize skip 分布为 `{0: 895, 1: 5}`。旧守恒式恰好失败 5 项，
包含 skip 的扩展式在 900/900 上成立。该结果只证明 runtime disposition 计数没有漏项，
不证明五个 skip 合法。

### 根因

五例最终 D1 后验相对 D2 最后实际消费后验的全部航迹均发生状态和协方差变化。main
finalize 使用的签名不含状态有效时刻、六维均值、六维协方差和 posterior generation，
在调用 D2 前错误跳过，并无条件清空 pending。

D1 已发布完整且严格递增的 generation。D2 Tracker 没有收到调用，timestamp conflict
为 0。当前没有证据要求修改 D1 发布器或 D2 关联器。

### D2 处置

- 不改 GNN/Hungarian、claim ledger、replay-coast、生命周期或 IDSW。
- 不把未调用记为消费，不增加虚假 merge，不丢弃 late batch。
- 已形成
  `research_modules/d2_data_association/docs/D2_FORMAL_R0_GENERATION_CONSERVATION_AUDIT_CN.md`。
- 已复核 main hotfix：最终 pending 实际进入 `Scalable3DTracker.step()`，未消费时
  失败关闭。
- 已在 D2 replay-coast 单元测试中显式锁定累计 hit、birth count、track key 和规范
  `global_track_id` 集合不变。
- D2 复核提交为 `dc5821f`，D6 准入修复提交为 `8e955f3`，完整修复链已形成 clean
  source commit `98d01bf`。

### 开发态证据

五个原失败 cell 均达到 D1 final generation 等于 D2 consumed generation、skip 为 0、
pending 为空和在线真值使用为 0。最终调用的 `fresh_detection_count=0`，birth map 为空，
duplicate coalescence 为 0。四个 5v5 cell 全部在 replay-coast 宽限期内；20v20 seed
1009 有一条航迹超宽限而增加 miss，但未增加 hit、建轨或改写 ID。

五个 manifest 均为 dirty working tree。D6 generation integrity 为 5/5，formal
admission 为 0/5。

### 正式关闭条件

正式 source 和 plan 已冻结，shards 0、5、9 已完成，共 135/900。D6 v10 已正式关闭
原失败 5v5 seeds 1000/1005 和 20v20 seed 1009；seeds 1008/1018 尚未运行。当前可用
空间只比 20 GiB 运行下限多约 65 MB，main 已停止新单元。存储解阻后需按同一 plan
继续其余 765 个单元，最终由 D6 确认 900/900 generation integrity、clean repository
和 formal admission。若未来恢复 no-op，必须使用 D2 可见完整输入的强内容摘要，并把
resolved watermark 与 actual consumption 分开；不能仅把 finalize skip 加入正式
守恒式。

口径固定为：代码和 5-cell 开发态定向回归已通过；正式 source
`1e5ed8ddcf27f375e922a447decfbd875d21bfdf` 已运行 135/900；3/5 原失败正式闭合；
完整 900-cell R0 仍开放，存储仍阻塞。

2026-07-25 验证结果：D2 replay-coast 专项 `5 passed`，D2 全量
`305 passed, 1 warning`，main hotfix 五 seed 定向测试 `5 passed`；`py_compile` 和
scoped `git diff --check` 通过。未启动 AirSim。

## 2026-07-29 seed 2007 物理窗口身份 GAP

### P0 状态

无新增 D2 P0。`GT3D-000004` 在线航迹、规范 ID、协方差、D3 计划绑定、D7 指令和运行
确认均存在，在线 truth 使用为 0。D2 不需要补 ID、改写 `global_track_id` 或放宽逐帧
identity mapping。

### 已核实事实

- readiness-v3 treatment 的 `d3-plan-3529e5a66440:v2` 有 19 条非 hold 指令；
- `INT-0004/GT3D-000004` 是唯一 `identity_mapping_unavailable`；
- D2 evaluation v2 中，GT4 的 12 个 available frame 全部唯一映射到 `TGT-0004`；
- 唯一 unavailable frame 为 `1.035192721089 s` 的 confirmed/unmatched coast，原因仅
  `track_not_assigned_in_frame`；
- 前后锚点为 `0.833472220197 s` 和 `1.236148794089 s`，均映射 `TGT-0004`；
- GT4 ambiguous、uncommitted、竞争 truth claim 和在线 truth 使用均为 0；
- 目标在 truth state 中持续 active，不属于目标失活或未分配的合理 unavailable。

### 根因和 owner

D2 unmatched 帧不携带本帧 source observation 是正确合同。复制历史谱系会把 coast
伪装成新量测，破坏 claim/replay 审计。D2 evaluation 已保留逐帧 mapping、
identity commitment、前后锚点和冻结的 `0.9 s` lineage window。

直接断点是 D6 `runtime_plan_outcome_join` 的窗口策略：窗口内任一 unavailable mapping
都会阻断整个 truth mapping，尚未实现 evaluator-only 的 bounded committed coast
bridge。该项为 **D6-owned P1**，不是 D2 数据合同遗漏，也不是 main 在线 producer
缺字段。main/scalable3d 无需重新生成在线 ID；只需在 D6 修复后对原制品重放。

### 精确关闭条件

main 应下发 D6 专项，在不读取在线 truth 的前提下：

1. 从 D2 evaluation v2 读取前后 available 锚和嵌入的 identity evidence records；
2. 只桥接同一 global track、同一 truth、confirmed/unmatched、
   `track_not_assigned_in_frame` 的 gap；
3. 要求 gap 内 commitment 持续 committed，无 ambiguity lease、recovery blocker、
   ambiguous/uncommitted 或竞争 truth claim；
4. 要求锚点间隔不超过 evaluation 的 lineage window；
5. 输出 bridge policy、锚点、gap 帧、谱系哈希和
   `online_exposure_allowed=false`；
6. 任一条件不满足继续 unavailable；
7. 对 seed 2007 原输入重放后，19 条窗口应全部可审计，同时 online truth use、
   global ID rewrite 和 production authority 保持 0/false。

D2 本轮不改代码。该 P1 只有在 D6 测试和同输入重放通过后才能关闭。2026-07-29
D2 loader、`py_compile`、scoped `git diff --check` 均通过，D2 全量为
`305 passed, 1 warning in 29.38s`。

## 2026-07-31 正式严格身份阻断诊断缺口复核

### 状态

**无新增 P0。** 正式 execution-root 只读发现、严格不可用筛选、v3 逐 mapping 因果分类、
CLI、公共 API、逐案例制品和哈希清单已经实现。该能力不接触在线关联器，不修改既有
450 个 episode，不重标注，也不把 unavailable 解释为 0。

原 D2 P1“36 个严格身份不可用案例缺少可审计因果包生成能力”已在代码和小型 fixture
层关闭。发现器支持 `shards/*/cells/*/episode`，并验证 execution plan、shard 状态、
episode/D6/offline-identity 身份与来源哈希；哈希或布局不一致时失败关闭。旧
`--episode-root` 仍兼容，archive 不自动解包。

### 正式证据口径

main 独立只读核对结果为 36 个 episode、556 个 blocker mapping event：

- 27 个 multi-truth episode，38 个 mapping event；
- 9 个 lineage-window episode，518 个 mapping event；
- 517/518 为 `historical_lineage_only_stale`，1/518 为
  `active_commitment_source_stale`；
- 36/38 个 multi-truth event 由最新观测引入新真值，2/38 历史已含两个真值；
- 最新观测传感器模态为 camera 17 个、radar 21 个；完整来源模态转换为
  `radar->camera` 17 个、`radar->radar` 19 个、`camera+radar->radar` 2 个；
  38/38 的承诺 reason 均为
  `fresh_original_observation_accepted`；
- multi-truth 分布为 100v100 的 4 episode/4 event、200v200 的 23 episode/34 event，
  5/20/50 规模未出现该原因。证据显示它与密度和规模相关，不能据此断言单一算法根因。

这些统计绑定 producer commit `80e55eb43bc4a5feeac9c9af0d718d461a46401f` 和
execution-plan hash
`b922ff5f95864345efa583da7256935694e5c675529989a659716522a0d7590e`。本轮 D2 未运行
正式 450 episode，正式 36-case causal pack 仍待 main 调度生成。

### 保留 P1

1. main 在不删除原目录/归档、不中断 20 GiB 保护底线的条件下运行只读 CLI，保存并
   审核正式 36-case pack；这属于正式制品生成，不是算法修复。
2. 在线根因缓解仍开放。未来候选只能使用几何、协方差、运动和来源一致性等 truth-free
   信号；诊断 truth 不得进入在线输入。候选必须绑定新的 clean producer/execution plan
   并重新跑正式多 seed，不能回写当前 450 episode。
3. 固定 `0.9 s` 是身份承诺新鲜度预算。正式 delayed-noisy evaluator 中可能存在
   `1.05 s` lineage 配置，二者必须分别报告，不能通过放宽预算消除阻断。

2026-07-31 验收：37-entry 小 fixture 精确筛出 36 个严格不可用 episode，专项
`8 passed in 0.60s`；D2 全量 `309 passed, 1 warning in 29.68s`；CLI help、全部变更
Python 文件 `py_compile` 和 scoped `git diff --check` 通过。唯一 warning 为本机
Matplotlib `Axes3D` 多版本导入问题，与本次功能无关。
