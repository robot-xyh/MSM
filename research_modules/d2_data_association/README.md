# D2 Data Association Research Module

D2 是 C-UAS 多目标数据关联研究模块，目标是在离线仿真和日志回放中维护稳定的 `global_track_id`，降低多目标交叉、密集编队、漏检、短时遮挡和虚警条件下的 ID Switch 风险。

安全边界：本模块只用于科研仿真、dry-run 和离线评估，不包含真实飞控、硬件驱动、火控参数、毁伤逻辑、自动处置或绕过人工授权的流程。

规模边界：D2 消费每帧传入的 `tracks`、`detections` 和当前 `active_tracks` 集合，不从场景名推断目标数量，不写死 2v2 或 5v5。`crossing_dense_5v5` 等名称只是可重复 baseline fixture；main runtime 的 `--drone-count N` 只应体现为传入 D2 的输入集合长度。

### 2026-07-23 身份证据承诺 v2

- 新增 truth-free `d2.identity-evidence-commitment.v2` DTO 和
  `d2.scalable3d_identity_evidence.v2` 外层证据合同。v1 常量、默认构造、序列化和
  评分行为保持兼容；v2 必须显式携带 `identity_commitment`。
- 每条六维规范航迹现在独立保存
  `committed -> identity_uncommitted_ambiguity_hold ->
  identity_uncommitted_after_hold -> committed` 状态。租约到期或硬上限释放只改变
  hold 状态，不恢复身份承诺。每条受 hold 影响的航迹另保存有界的歧义候选 key 集合和
  最大分量量测时间水位线；reservation 从 claim ledger 删除后，该集合仍存在。恢复要求
  key 不在阻断集合、source measurement timestamp 严格晚于水位线、claim 是本扫描首次
  接纳且 replay count 为 0、活动租约为 0，并且 truth-free disposition 为
  `target_candidate`。
- 恢复门控在量测更新之前执行。旧 hold 候选即使在 reservation 释放后再次通过 freshness，
  也不会 update、增加 hit、写入 `detection_to_track` 或绑定 observation claim。阻断集合
  默认每航迹最多 2048 个 key、全局最多 250000 个；未溢出状态在真正的新证据恢复后
  清理。溢出后保持 fail-closed，只在航迹永久 dropped 时释放。
- 每帧 `AssociationResult.metadata.identity_commitment_by_track` 稳定输出
  `association_state`、承诺状态和原因、状态时刻、量测/到达双时间戳、commitment/
  component/evidence generation、publisher epoch、active lease、soft/hard deadline
  和 expiry 信息，并公开 blocker count、recovery watermark 和 overflow，不公开阻断
  key。未提交 payload 不含 source observation evidence key，main 不得再通过当前
  `hold_track_ids` 推断历史承诺状态。
- `known_false_alarm/unknown` 是传感器、杂波分类器或人工规则给出的 truth-free 上游
  disposition。在线 D2 不读取仿真 truth sidecar，也禁止生产者用离线 truth label 回填
  这两个字段；两类证据不能更新航迹、建轨或恢复身份承诺。
- 离线 v2 evaluator 将显式未提交帧排除在
  `global_track_id -> truth candidate` 身份赋值之外，但保留在 truth-presence 覆盖分母
  中；IDSW 继续比较未提交空窗前后的 committed 锚点。普通
  `source_lineage_missing`、未来/超窗观测、未知标签和冲突谱系仍 fail-closed。
  audit 新增 commitment coverage、状态计数、未提交 mapping 数和候选绑定违规数。
- 2026-07-23 模块回归为 `281 passed, 1 warning in 29.46s`，验收阈值为零失败。专项覆盖活动
  hold、租约释放后旧候选 key 重入仍阻断、不同 key 但时间未越过水位线仍阻断、更晚新
  key 恢复、容量溢出 fail-closed、未来来源时刻/重复/超龄/已知假警/未知处置不恢复、无
  hold 正常路径、37 目标动态规模、v1 round-trip 和跨未提交空窗 IDSW/coverage。warning 是本机
  Matplotlib `Axes3D` 环境问题。
- 已实现和已测试仅指 D2-owned 合同与状态机。main 尚未把 v2 payload 写入 scalable
  episode，D6 尚未聚合 commitment coverage，clean seed 1100 A/B 也尚未复跑。
  候选继续默认关闭，不能据此宣称 lineage blocker、D3 分配退化或系统晋级已经关闭。

### 2026-07-23 D1 结构歧义保持租约候选

- 六维稀疏路径新增 `AmbiguityComponent3D.from_mapping()`，只接受冻结的
  `d1.structural-ambiguity-evidence.v1` 公开侧车。合同严格校验分量代次、双时间戳、
  NED 状态和协方差、完整成员/观测/候选边、`posterior_update_applied=false`、
  prediction-only 更新方式及 deferred birth。观测预留键直接使用不可逆
  `d1-observation-sha256:<digest>`，不要求或恢复原始 observation ID 和来源命名空间。
- D1 成员来源合同与上游规则逐字节一致：默认发布者为 `D1_FUSION`，兼容默认 epoch
  为 `d1-default-epoch-v1`，成员令牌为
  `d1-track-sha256:` 加规范 JSON
  `[publisher_node_id,publisher_epoch,d1_local_track_id]` 的 SHA-256。D2
  `source_key` 固定为
  `publisher_node_id::publisher_epoch::opaque_member_track_token`。原始 D1 本地 ID
  只进入不可逆摘要，不复制为 D2 `global_track_id`。
- `detections3d_from_d1_global_tracks(..., use_opaque_d1_source_tokens=True)`
  才启用上述来源适配。默认值为关闭，默认调用的 Detection 序列化与原行为保持相同。
  未显式提供 publisher epoch 时，元数据记录使用兼容默认 epoch，并标明发布者重启时
  必须轮换；D2 不能自行感知外部进程重启。
- `Scalable3DTracker.step(..., ambiguity_components=())` 保持旧调用兼容。
  `AmbiguityHoldLeaseConfig` 默认 `enabled=False`；开启后使用 2 个等效扫描周期的软
  间隔和 5 个周期的硬上限，也可显式配置秒值。只有新的原始不可逆观测证据可延长软
  截止，重复 evidence、重复或回退 generation、回放 posterior 和坏合同均不能刷新
  租约。硬截止保存在有界历史中，同一分量不能通过递增 generation 重置硬上限。
- 侧车的 `state_valid_timestamp` 按 D1 合同保持为原
  `measurement_timestamp`，不再要求与延迟补偿后的 D2 扫描时刻相等。D2 计算
  `component_age_seconds = d2_consumption_timestamp - state_valid_timestamp`：
  未来证据拒绝，超过 `max_component_age_seconds` 的过旧证据拒绝，年龄窗内的延迟
  证据按当前 D2 扫描时刻建租约。开发默认年龄上限为 `1.0 s`，用于覆盖当前 main
  常见的 `0.5 s` D1 scan lateness 和传输余量；正式运行应按实测时延显式配置。
  事件同时保留原 measurement/arrival/state-valid/published 时刻、D2 消费时刻、
  分量年龄和时间判定。
- 活动租约内，已绑定 canonical track 只做预测，不 update、不增 hit、不增 miss、
  不 birth、不 rebind，身份置信度不增加，协方差不收缩。未绑定成员和分量观测被预留，
  不得建轨。首版只支持租约到期释放，没有实现连续双向唯一证据自动消歧，也没有接入
  JPDA/MHT。
- 正常六维路径的来源绑定约束已前移到候选边生成阶段。已绑定 source 只能连接原
  `GT3D-*`；若原绑定边不满足几何门限，则该输入被隔离并只让原航迹预测，不允许错误
  航迹先更新后记录冲突，也不允许另建影子航迹。
- 逐帧和累计诊断包括 accepted/rejected/expired component、活动保持航迹、预留证据、
  阻止的 hit/miss/birth/rebind、关联前 binding rejection、软硬截止及原因。活动分量
  将 `AssociationRiskSummary` 标为高歧义，但在线 `id_switch_count` 仍保持
  unavailable，不伪造改善。
- main 已在固定提交 `9cd2a79` 对 nominal 200v200、seed 1100、2.2 s、
  `recon_count=2` 运行 baseline/candidate 单 seed 门槛。候选收到并消费 D1 evidence
  `46/46`，在 7 个 D2 周期产生 33 个 accepted component event，阻止
  hit/miss/birth `69/69/4`，证明侧车和保持状态机在集成路径实际生效。候选 D2 航迹
  `203 -> 201`、D3 分配 `200 -> 197`、available/unavailable mapping
  `1566/230 -> 1492/294`、RTF `0.2245 -> 0.2112`。候选离线身份指标因
  `source_observation_outside_lineage_window` 不可用，不能与 baseline 的 IDSW `9`、
  track/identity continuity `0.865` 和 coverage continuity `0.870` 作数值比较。
  在线 truth use 为 0。
- 2026-07-23 D2 完整模块结果为 `271 passed, 1 warning in 28.82s`，验收阈值为零
  失败；warning 是环境 Matplotlib `Axes3D` 导入问题。该结果只证明模块合同和不变式，
  不证明系统级 IDSW、continuity 或航迹数改善。seed 1100 候选未达到晋级门槛，
  seeds 1101/1102 已停止，默认 `enabled=False` 保持。下一轮先定义歧义保活帧的
  可评分谱系合同：用 `identity_uncommitted/ambiguity_hold` 区分普通
  `lineage_missing`，保留分量和证据审计，但不把候选观测硬分给
  `global_track_id`。该合同冻结后再联合校准 lineage window 与 lease，并排查映射和
  分配退化。禁止仅放宽当前 `0.9 s` window 作为准入修复或晋级依据；通过同 seed 门槛
  后才恢复多 seed。

### 2026-07-23 clean `4ac3bb2` seed 1000 profiler 与等价优化

- 本轮针对 nominal 200v200、seed 1000、10.0 s 的 clean `4ac3bb2` 冻结在线总线做
  D2-owned 归因。原完整阶段有 47 次 regular association，P50/P95/max 为
  `121.972/137.335/145.966 ms`，10.0 s 相对 2.2 s 的单次成本约为 `1.579x`。
  profiler 从 48 条 D2 输出恢复最新前置 D1 输入，允许 MAIN/D5/D7 记录交错，不读取
  truth sidecar。输入 SHA-256 为
  `c1dda8523e48c255bbeef48d9516b05863eb1bbb3a3ae2e09733259e6a66f77a`。
- `cProfile` 将明确的重复成本定位为：相同 `dt` 下逐轨重建 CV transition/process
  matrix、可信 D1 适配器已经从同一完整 6x6 covariance 切出的 marginal 再做两次
  `np.allclose`，以及 claim ledger 每帧重复汇总和线性扫描。本轮只复用每个唯一 `dt`
  的 CV 矩阵、在同一可信构造边界跳过两次冗余 marginal 比较，并以精确增量计数生成
  ledger summary；普通构造、regularized covariance 和未知输入仍走完整验证。
- 同输入旧/新比较的 48/48 周期公开输出与 tracker 状态完全相等，重复语义哈希均为
  `b2334c619b9d2f7c467387ad27b62614d028af83f0b7842b867cab1c4aa9824b`。
  input/fresh/replay/candidate/matched 分别保持
  `9626/9038/588/8862/8823`，在线 truth use 为 0；`global_track_id`、
  `id_switch_count` availability、门控、版本、逐条发布、claim 与真值隔离均未改变。
- CPU 0 绑定、BLAS/OMP 单线程、1 次 warmup 和 7 次计时下，D2 core 回放总中位数为
  `2.928830 -> 2.204672 s`，描述性加速 `1.328465x`。CV model build
  `9246 -> 46`，marginal `allclose` `19252 -> 0`，ledger summary
  `96 -> 48` 次且 cProfile 累计 `63.184 -> 0.405 ms`。早/晚 regular 窗口比却为
  `1.119661x -> 1.123036x`，没有改善长窗口增长，因此性能 P1 保持开放。
- 机器报告为 `docs/d2_clean_4ac3bb2_seed1000_hotpath_20260723.json`，SHA-256 为
  `2256d6fdd29223ed5dd75351cd6bb208a4d67c55925eeba047620ac865b6c7da`。墙钟只作诊断，
  不设脆弱硬断言；该单 seed 冻结质点回放不是 AirSim、完整 D1-D7、多 seed 身份标定
  或实时 SLA。完整 D2 回归为 `234 passed, 1 warning in 34.83s`，验收阈值为零失败。

### 2026-07-20 六维稀疏关联路径

- 新增显式选择的 `Scalable3DTracker`：航迹状态和协方差采用
  `[pN,pE,pD,vN,vE,vD]` / `6x6`。独立六维量测使用 Joseph 更新，只有位置时仍使用
  3D NED Joseph 更新；D1 source posterior 保留完整 6x6 covariance 并使用保守 CI，
  不再把相关 posterior 重复当作独立位置量测。旧二维 `Tracker`、replay、JPDA/MHT
  与默认 `GNNHungarianAssociator` 均未改变。
- `Sparse3DGNNHungarianAssociator` 先用 `scipy.spatial.cKDTree` 生成保守空间候选，
  再计算 3D 位置创新马氏距离，并对稀疏二部图的每个连通分量运行 Hungarian。这里及
  旧类名中的 GNN 都表示 Global Nearest Neighbor，不是图神经网络；D5 的跨视角图网络
  不在 D2 实现。
- 在线 `Detection3D` 合同没有 truth 字段，并递归拒绝 truth/actor/object/entity、上游
  `global_track_id` 等身份元数据。D1 六维对象适配器忽略上游 canonical 值，只有 D2
  `Scalable3DTracker` 分配 `GT3D-*`；adapter 以 D1 state-valid timestamp 作为关联
  epoch，并另存原始 measurement/arrival timestamp 供延迟审计。在线结果显式输出
  `id_switch_count=None`、continuity unavailable 和 `AssociationRiskSummary`；独立
  `Sparse3DOfflineEvaluator` 只在关联结束后读取 truth sidecar。
- D1 adapter 不再丢弃位置-速度交叉 covariance。相关 posterior 的当前 CI track weight
  固定为 `0.5`；速度创新 NIS 超过三自由度 99% 卡方门限时，通过 covariance inflation
  降低该速度 posterior 的影响。关联中的速度项也只在有限代价内作 tie-break，位置候选
  仍由三维马氏门控决定。这里没有按速度模长、4.7 m/s 或场景名硬裁剪。
- 2026-07-20 单元验收覆盖 5/20/50/100/200、D 轴门控、两目标三维交叉、连续漏检、
  15 个匿名虚警、truth 拒绝、有界历史和六维速度稳定性。完整 D2 回归为
  `139 passed, 1 warning`，
  验收阈值为零失败；warning 是环境 Matplotlib `Axes3D` 导入问题。
- 同日 200 目标确定性规则网格做 3 个独立 trial，每个 trial 预热 1 帧后测量 30 帧；
  90 个测量帧的候选边均为 `200`，潜在全对 `40,000`，分量矩阵元素 `200`，最大单
  分量元素 `1`，候选裁剪率 `99.5%`。聚合关联 mean/P95/max 为
  `6.683/7.056/22.471 ms`，含预测与更新的 tracker step 为
  `25.491/26.797/41.613 ms`。这是当前主机单进程合成样本，包含系统调度尾值，不是
  实时 SLA、真实 AirSim 或多 seed 统计；极端全重叠场景仍可能形成大连通分量。

### 2026-07-20 六维速度状态稳定性修复

- main 只读诊断的 50v50、seed 17、2.2 s、radar-only 输入中，D1 速度 P50/P90/max 为
  `6.28/12.16/21.03 m/s`，速度 covariance trace 为 `101.24/110.31/112.32`；旧 D2
  输出反而升至 `8.89/17.43/27.49 m/s`，trace 缩至 `62.95/69.37/70.86`。根因是
  adapter 丢弃 6x6 交叉 covariance，tracker 又只消费位置 marginal；CV 预测产生的
  position-velocity cross covariance 令位置 residual 持续注入速度，同时错误收缩 Pvv。
- D2-owned 匿名合成复现使用 seed 17、50 条、12 帧、0.2 s 周期（0.0--2.2 s）。输入
  速度 P50/P90/max 为 `5.415/7.960/12.274 m/s`；旧路径复现为
  `9.41/14.31/21.88 m/s`、Pvv trace `62.76`。修复后为
  `5.082/6.401/7.218 m/s`、Pvv trace `101.181`，最终位置 RMSE 从输入 posterior 的
  `52.634 m` 改善到 `48.364 m`，离线 IDSW 为 0、continuity 为 1.0。
- 200 条批量回归使用 seed 41、10 帧、0.2 s 周期。每个更新帧候选/潜在全对为
  `200/40,000`，活动航迹始终 200；输入/输出速度 P90 为 `8.097/5.980 m/s`，输出
  Pvv trace 中位数 `69.685`，输入 trace 为 `75`，离线 IDSW 为 0、continuity 为 1.0。
  seed 29 的 21 帧双目标交叉另注入一次速度离群值，交叉帧保持 4 条位置门内候选，
  NIS update gate 与有限速度代价均触发，IDSW 仍为 0、continuity 为 1.0。
- 验收比较使用输入/输出分位数、covariance trace、位置 RMSE 和隔离离线身份标签；在线
  DTO 不含 truth/actor/object identity，也没有速度硬上限。CI 权重 `0.5` 只是当前保守
  baseline，未证明最优；至少 20 个未见 seed、六维 NIS/离线 NEES coverage、不同
  covariance 相关结构和高机动/模型失配标定仍开放。main 的 50v50/200v200 场景也需
  owner 在修复后复跑，本文不把模块合成结果替代为端到端结论。

### 2026-07-15 M5N2 真实 AirSim 20-case 证据同步

- 本批为 SimpleFlight M5N2：baseline 10 seed、candidate 10 seed，共 20 case；M5N2 达到
  20/20 后终止多 seed 批次。`TERM` 生效前仅额外完成一个被排除的
  `png_ttc_2v2_seed001`，其结果不进入 M5N2 聚合；dropout case 完成数为 0。
- 20 case 共记录 3805 个可用 D2 association main-bus 样本，mean/P95/max 分别为
  `2.521/3.147/98.942 ms`。均值和 P95 明显低于整个 main bus，但 98.942 ms 的单次
  尾部值仍需在后续性能审计中保留，不能只报告均值。
- 在线 truth identity/state 使用均为 0。由于在线 D2 没有 truth assignment，本批在线
  `id_switch_count`、`track_continuity` 和其他依赖真值的身份指标必须保持
  `None + unavailable`，不得写成 0；如需身份结论，必须另用隔离 sidecar 在写盘后评分。
- 本批第二 primary 进入 5 m 为 0/20，且其最终停止原因均记录为 `collision_stop`；但
  artifact 没有持久化碰撞对象，当前证据不能把该失败归因于 D2 关联。默认
  GNN/Hungarian、中心拥有 `global_track_id`、D5/D7 禁止本地重绑的合同均保持不变。

## 当前能力

已实现：

- GNN/Hungarian 默认关联器，底层使用 SciPy `linear_sum_assignment`。
- `DataAssociator` 可插拔接口，当前有 GNN、JPDA、MHT 三条接口兼容路径。
- 兼容基线保留马氏门控、二维 `[x,y,vx,vy]` 常速度 Kalman fallback 和 4x4 covariance；Detection/GlobalTrack covariance 在输入和门控边界拒绝非有限、明显非对称或明显非 PSD 矩阵，仅对数值容差内缺陷做对称化/特征值 floor。`covariance_consistency` 表示最新检查，`covariance_regularized`/`regularization_ever_applied` 与 `last_regularization` 保留历史正则化证据。
- 六维稀疏路径使用 `Detection3D`、`GlobalTrack3D`、完整 source 6x6 covariance、相关
  posterior CI、独立量测 Joseph update、速度创新 NIS 门控、3D 马氏门控、KD-tree
  候选图和分量级 Hungarian；航迹事件历史与逐帧审计均有配置上限，不保存无条件全密集代价/距离历史。
- 六维路径提供默认关闭的 D1 结构歧义保持租约。公开 DTO 不 import D1 私有实现；
  observation claim 明确区分 `unseen/reserved_ambiguous/consumed`，source binding
  在状态更新前执行权威硬掩码。
- GNN/Hungarian 主线在保留马氏门控和 `linear_sum_assignment` 的基础上，加入速度方向、短时历史和加速度异常组成的轻量运动一致性代价，并输出 motion consistency diagnostics。
- 在线 D1 track-to-track 输入增加非真值 `source_global_track_id` 连续性代价和来源谱系治理：已落入现有门限但未被一对一分配的上游影子航迹不立即 birth，仍绑定活动 D2 航迹但发生统计大跳的同源输入先隔离并记录原因；该保护不读取 actor/truth ID，不替代马氏门控或 GNN/Hungarian。
- quality-aware gate baseline：按 track quality、局部目标密度、位置协方差和上一帧 association risk 对每条 track 的 gate 做保守放宽或收紧；这不是完整自适应门控框架。
- `tentative/confirmed/engageable/lost/dropped` Track 状态机；summary 另导出不依赖 truth 的 `birth_count/lost_count/drop_count/rebirth_count` 和完整 lifecycle transitions。`rebirth` 仅指同一 `global_track_id` 从 `lost` 重获，不把 dropped 后新建航迹猜成同一真实目标。
- 每条 `GlobalTrack` 输出 `track_quality`、`association_risk` 和 `quality_metadata`；`AssociationResult.metadata`、association logs、risk summary metadata 与 metrics summary 同步输出 track-level 质量和风险字典，供 D3/D5/D6 消费。
- `id_switch_count`、`track_continuity`、`identity_continuity`、`coverage_continuity`、`duplicate_assignment_count`、RMSE、confusion matrix 和 runtime 指标；无 truth assignment 时 IDSW、continuity 和 RMSE 字段仍存在，但值为 `None`，并分别输出一致的 `available=false` 与 `reason=truth_assignment_unavailable`。truth 可用且 IDSW 确实为零时输出可用的整数 `0`，不再用伪零表示 unavailable。
- `AssociationRiskSummaryWindowGenerator` 滑窗风险摘要，汇总代价 margin、候选重叠、IDSW delta、duplicate delta、可用 continuity、D5 disagreement、source node 和 link type；不可用 continuity 不参与 `duplicate_track_risk`、`continuity_collapse` 或 hard risk 计算。
- `RiskThresholds` / `classify_risk_summary()` 软/硬风险分层，按 D4 口径区分 ambiguity/cost margin/candidate overlap 与 IDSW/duplicate/continuity collapse。
- D1 6D NED `GlobalTrack` 到 D2 2D `Detection` 的旧投影 adapter，保留 `measurement_timestamp`、`arrival_timestamp`、covariance 和 metadata；新 `detections3d_from_d1_global_tracks()` 保留 NED 六维 source posterior 及完整 covariance，以 state-valid timestamp 对齐关联 epoch，把原始双时间戳留在 source metadata，并忽略上游 canonical ID。
- AirSim-style dry-run/replay adapter，不 import 或调用 `airsim`，并在 bus message 中导出当前活动 `global_track_ids`。
- `load_airsim_replay_frames()`、`run_airsim_replay_association()`、`run_threshold_sensitivity()` 和 `summarize_multi_seed_risk_calibration()` 支持离线 JSON/JSONL replay 读取、association log/report 输出、seed/episode/scenario/frame/offline truth label 校准元数据透传、`RiskThresholds.profile_version` 与 `association_risk_threshold_version` 记录、gate pass/reject count、motion/quality risk summary、dense/crossing threshold sensitivity summary 和多 seed 推荐阈值摘要；无 truth label 的 N-v-N replay 会用输入观测数或显式 count 字段给出 `target_count` fallback。
- `OfflineTruthLabel` 冻结 `d2-offline-truth-label/v1` JSONL 合同，每条记录包含 `episode_id/frame_index/timestamp/truth_id/position` 和可选离线匹配注释；读写器拒绝重复键和非法坐标。`strip_offline_truth_from_frames()` 生成不含 truth 的在线帧，`run_airsim_replay_association(..., offline_truth_labels=...)` 只在在线关联结束后构造 evaluator-only 评分视图。
- `build_dense_crossing_replay_fixture(target_count=N)` 按输入 N 生成 dense crossing、遮挡式连续漏检和虚警压力场景；`build_5v5_replay_fixture()` 只是兼容包装器。`run_dense_crossing_calibration()` 强制至少 10 个唯一 seed，输出每 seed IDSW、continuity、NIS/NEES availability、gate/risk profile/version、runtime、确定性签名和保留 unavailable 的聚合摘要。
- `load_airsim_replay_frames()` 同时接受旧 AirSim `frames` schema 和 D1 `d1.governed_replay_manifest.v1 + records`。D1 adapter 按 frame/timestamp 聚合 radar records，用球坐标雅可比投影到水平 N/E，并匿名化 observation ID/lineage；一维声学和 pixel EO 不混入 N/E，按原因显式跳过。
- P1 replay 治理默认将 simulator truth 从在线 `Detection`、track 和 association log 中移除，并将源 detection/actor ID 改为按帧匿名 ID；嵌套 actor/truth metadata 同样递归清除。GNN/Hungarian 仅看到量测、协方差、时间戳、置信度和可用特征。`OfflineTruthEvaluation` 在关联完成后按同帧输入顺序独立对齐标签，计算 IDSW、continuity、confusion matrix 和 RMSE；报告同时保留 `online_metrics` 与 `offline_truth_evaluation`，避免把在线 unavailable 误写成零。
- `InitializationGovernanceProfile` 提供版本化 M-of-N 初始化口径，默认 `2-of-3`，也可由 replay 和 gate sensitivity 入口显式传入其他 profile；离线治理输出初始化/确认延迟、成功率、虚假航迹数与比例、漏检数、虚警数、逐帧 measurement count / truth-target count 以及 mismatch frame count。
- NIS 由关联前 innovation covariance 和马氏距离计算，不依赖 truth，因此无 truth replay 仍可输出；NEES 只在独立 offline truth state 可用时计算。两者输出样本数、均值、中位数、二维/四维 95% 卡方区间及区间覆盖率，不把缺失样本解释为零。
- `build_5v5_replay_fixture()` 构造动态 5 目标 crossing/dense/漏检/虚警组合 fixture；它只用于回归和标定，不把 5 写入关联器或 Tracker。
- `AssociationLogEntry.rejected_pairs` 默认空列表并完整序列化 `mahalanobis_gate`/`assignment_above_gate` 原因；replay gate summary 按原因统计，旧 JSON 缺该字段时按空列表兼容。
- 跨节点注册基础：`SourceTrackSummary` 使用 `(source_node_id, local_track_id, local_epoch)` 命名空间、独立 measurement/arrival timestamp、6D NED state/covariance、quality、lineage/correlation status 及 candidate/current canonical hint，在线合同不含 truth。
- `CrossNodeTrackAssociator` 将 source tracks 传播到公共时刻，按完整 6D 状态和差分协方差做 Mahalanobis gate，并按 source 节点分组使用 Hungarian；`CrossNodeTrackRegistry` 因而支持一个 canonical `global_track_id` 绑定多个观察节点的 source tracklets，同时保持同一 source 内一对一。
- registry 对 `exact_known_correlation` 输出 D1 数值相关融合请求，对 `unknown_correlation` 只输出 CI/保守融合请求，对显式 duplicate、重复 payload、重复 lineage 和 stale/replay source track 在关联前拒绝；D2 不复制数值 CI。
- cross-node 在线指标输出 source binding rebind ID switch、duplicate payload rejection 和 transport/queue/fusion latency；`OfflineCrossNodeMetricsEvaluator` 在独立 truth mapping 下计算 canonical duplicate 与 track-to-track association precision/recall，不向在线 registry 暴露 truth。

### 2026-07-15 Ceiling-aware 身份连续性准入

- P1 报告 schema 已升级为 `d2-p1-identity-calibration/v2`，准入策略版本为
  `d2-p1-identity-admission/ceiling-aware-error-reduction-v1`。基线连续性为
  `C_b` 时，剩余误差空间 `H=max(0, 1-C_b)`；候选实际提升
  `Delta=C_c-C_b`；v2 所需提升为 `Delta_req=min(0.10, 0.10*H)`。当 `H>0`
  时同时输出 `Delta/H`，即候选消除基线剩余身份错误的比例；当 `H=0` 时只接受合法、
  不退化的 `C_c=1`。
- 每个候选输出 baseline headroom、实际/所需提升、headroom/error reduction fraction、
  policy version，以及 IDSW、continuity、false-track、P95 latency、truth leakage 五项
  gate 的 `passed/reason/actual/required`。缺指标、非有限值、越界连续性、零 IDSW
  基线、continuity 退化、false-track 超限、延时超预算或任一在线 truth leakage 均
  fail-closed；不能只凭 IDSW 改善晋级。
- v1 的固定 `+0.10` 仍在报告中以 `legacy/deprecated` 字段保留，仅供历史审计，明确
  `used_for_admission=false`，不改变旧字段曾表示“绝对提升”的语义。任何通过结果仍
  只是 promotion review 建议，`default_online_path_changed=false`，默认在线
  GNN/Hungarian 不变。
- 2026-07-15 已使用冻结的六档真实 AirSim replay/truth manifest 离线重算完整 v2
  报告，本批没有重新启动 AirSim。candidate `gnn-g5.99-qa1-ld3_7-mw0.5x` 的总体
  IDSW `1.358333 -> 0.616667`，continuity `0.981046 -> 0.983954`；headroom
  `0.018954`、所需提升 `0.001895`、实际提升 `0.002908`、error reduction
  `15.3448%`。false-track 0、P95 `15.470 ms`、baseline/candidate truth leakage 0，
  五项联合 gate 全部通过，因此 `promotion_recommended=true`。该字段只表示评审建议；
  `selected_online_path=baseline_gnn_hungarian` 且
  `default_online_path_changed=false`。
- 分档只有 `clutter` 和 `combined` 通过完整联合 gate；其余四档 baseline IDSW=0，
  按 `baseline_zero_no_measurable_reduction_evidence` fail-closed。dropout 的 offline
  truth alignment 为 partial，未做最近邻补齐，也没有在线 truth 泄漏。
- 2026-07-15 模块回归：`113 passed, 1 warning`；warning 仍是本机 Matplotlib
  `Axes3D` 多版本导入问题，不影响准入判据。

### 2026-07-14 Online Truth Policy 与 Truthless 指标收口

- `TrackerTruthPolicy` 显式区分 `online` 与 `offline`，默认 `online`。在线 `step()` 在状态预测和关联前 fail-closed：拒绝 `Detection.truth_id`、任何显式 `truth_ids_present`，以及 Detection/frame metadata 中递归出现的 truth、actor 或 object identity。`online_truth_isolated`、`online_truth_hints_used`、`truth_metrics_available`、`continuity_available` 仅作为布尔治理状态允许通过；非布尔值仍拒绝。拒绝发生时不建轨、不计帧。
- replay 的在线路径显式使用 `online` tracker；synthetic simulation 和允许 truth 的 evaluator/dry-run 路径显式使用 `offline`。offline evaluator 继续允许 truth，并保持“真实零 IDSW = available `0`”。
- 验证日期为 2026-07-14：8 类拒绝用例、main owner 四布尔状态正例、3 帧和 5 帧 truthless replay、7 帧 birth/lost/rebirth/drop 状态序列及完整 D2 回归均通过；验收阈值为零失败、在线拒绝发生于状态变更前、truthless 三个身份/误差字段均为 `None`。完整结果为 `98 passed, 1 warning`，warning 是环境中的 Matplotlib `Axes3D` 多版本导入问题。
- 本批没有修改 `confirmation_hits`、`lost_miss_threshold`、`drop_miss_threshold` 或 gate。真实 replay 中 `T001 -> T005` 航迹序列对应的 birth/lost/drop/rebirth 参数标定仍为 P1。

### 2026-07-12 状态同步

- commit `33e6fa0` 本身没有修改 D2；其后的 D2-owned P1 任务新增长 governed replay 校准入口、OOSM exposure 审计和动态 N/M 回归。该阶段 D2 回归当时为 `69 passed, 1 warning`，warning 是本机 Matplotlib `Axes3D` 多版本导入问题。
- main GAP 与 PNG delivery AirSim 报告给出的 D2 相关新证据仅是合同保持：2v2 candidate 10 seeds 为 20/20 pair、在线 truth 使用为 0；锁定后两帧 dropout 仍沿原 global/local track 与计划上下文预测，没有 truth ID 或本地 ID 重写。
- M5N2 8 s 短窗口为 0/9，且不是同几何、同时间窗的长期对照；该 AirSim 报告没有 D2 专项 offline IDSW/continuity 或真实 dense/crossing 长回放。当前已闭合 D2 synthetic 长 replay runner/schema，但真实 replay、gate/risk、M-of-N/false-track、NIS/NEES 和跨节点 failover 标定仍开放。

### 2026-07-11 main runtime 合同验收证据（历史）

- main 在线链路已强制令 D2 输入和航迹的 `truth_id=None`；D1 -> D2 -> D3 仍按 D2 状态、协方差、质量和中心维护的 `global_track_id` 运行，不再依赖 simulator truth/actor identity 构造 D3 目标。
- `d2_governance_summary` 已进入 main episode bus 并由 D6 消费。D1 governed replay adapter 保留 timestamp/covariance 并匿名化来源身份；D2 在线关联不读取 simulator truth，truth 只通过 `d2-offline-truth-label/v1` 在 episode 后评分。
- P1 合同层已闭合。M=5、N=2 的 ComputerVision 10-seed 批次中，T001 双 primary 视觉共识与当前计划授权为 8/10；D2 相关指标为 `id_switch_count=0` (10/10)、错误 duplicate 为 0 (10/10)、`global_track_id` 改写/重绑为 0 (10/10)。
- 二级接管和完全分布式的 coalition commit 正例均进入 `executing`，缺 ACK 时为 `aborted`/`hold_for_review` 且导引许可为 0。这是下游消费 D2 中心管理 `global_track_id` 的 commit/fail-closed 合同证据，不是 D2 重绑 ID 或实现分布式临时 ID 合并的证据。
- SimpleFlight 15 s 仅用于诊断。30 个 active pair 的物理命中为 0，因此不能宣称物理拦截闭合；该结果也不改写 D2 已通过的身份与 truth-isolation 合同结论。
- D2-owned N-target dense/crossing fixture、至少 10-seed runner、offline truth 和 availability-aware 汇总已闭合。专用真实 AirSim dense/crossing 的参数标定是后续性能研究，不再作为 P1 合同 blocker。
- P2 benchmark 在同一 frozen replay digest 下固定输出 GNN/Hungarian、FilterPy、Stone Soup、模块内 JPDA 和模块内 MHT 五行。GNN/JPDA/MHT 复用同一 `Tracker` 生命周期并在在线运行结束后由隔离 truth evaluator 计算 IDSW/continuity；Stone Soup 1.9.1 和 FilterPy 1.4.5 仍仅是对象 adapter smoke，不是端到端 tracker，也不进入默认依赖/在线路径。

部分实现：

- `JPDAAssociator` 可执行小规模联合假设枚举和 marginal probability 对照，但不是完整 JPDA filter。
- `MHTAssociator` 可执行有界 branch 和短历史对照，但不是完整 MHT。
- 旧 `Tracker` 继续投影 D1 3D/NED 输入；独立 `Scalable3DTracker` 已实现原生六维状态，
  main-owned scalable point-mass 总线已有只读运行证据，但修复后端到端复跑、版本化输出
  验收与多 seed 标定尚未完成。
- cross-node registry 已完成低歧义 GNN/Hungarian 注册基础，但尚无多帧 JPDA/MHT 歧义保持、owner/epoch failover 或数值融合回写。
- 结构歧义保持租约只实现 prediction-only 有界保持与到期释放。连续双向唯一自动消歧、
  component-level JPDA、bounded MHT 和跨进程 publisher epoch 协商尚未完成。main
  clean 200v200 单 seed A/B 已执行，但候选因 lineage 指标 unavailable 及映射/分配
  退化被拒绝；修复与重测尚未完成。
- Stone Soup `Detection` adapter 与 FilterPy CV `KalmanFilter` adapter 已可选执行并记录对象转换/更新 latency；它们是 adapter smoke，不是端到端 tracker，IDSW/continuity 必须标记 unavailable。

未实现：

- Stone Soup 完整 JPDA/MHT tracker benchmark。
- FilterPy EKF/UKF/IMM 或端到端数据关联 tracker。
- `scalable_3d_simulation` 六维路径修复后的版本化输出 schema 和端到端多 seed 验收；
  episode-bus 基础编排已有 main 只读运行证据，不再列为完全未接入。
- JPDA/MHT 自动升级触发。
- D2 不直连 AirSim SDK，不负责 ComputerVision 图像/metadata 采集或 episode 编排；它只消费 main/runtime 导出的 governed replay 与隔离 offline truth。
- 跨节点多 source 的 D1-owned 数值 CI、已知交叉协方差融合、fusion NEES/ANEES 和
  通信字节统计；D2 当前只发布跨节点相关性决策与融合请求。D2 内部针对同一 source
  posterior 时序相关性的固定权重 CI 不等同于该跨节点数值融合能力。

## 目录

- `d2_data_association/models.py`：`Detection`、`GlobalTrack`、`AssociationResult`、风险摘要和生命周期数据结构。
- `d2_data_association/gating.py`：马氏距离、门控代价矩阵和歧义分数。
- `d2_data_association/associators.py`：`DataAssociator`、`GNNHungarianAssociator`、`JPDAAssociator`、`MHTAssociator`。
- `d2_data_association/tracker.py`：常速度 Kalman fallback、状态机、建轨、漏检和删除。
- `d2_data_association/metrics.py`：IDSW、continuity、duplicate、RMSE、confusion matrix、风险摘要和软/硬风险分层。
- `d2_data_association/cross_node_models.py`：source-track、canonical binding/history、相关性和融合请求合同。
- `d2_data_association/cross_node_registry.py`：公共时刻传播、track-to-track Hungarian 和中心 canonical registry。
- `d2_data_association/cross_node_metrics.py`：truth-free registry 指标和隔离的 offline cross-node evaluator。
- `d2_data_association/scalable_3d_models.py`：truth-free `Detection3D`、六维 `GlobalTrack3D` 和松耦合 D1/scalable 量测适配器。
- `d2_data_association/ambiguity_hold.py`：冻结 D1 结构歧义 DTO、不可逆来源令牌合同和
  默认关闭的租约配置。
- `d2_data_association/sparse_3d.py`：KD-tree 稀疏 GNN/Hungarian、六维 CV Tracker、风险摘要和有界审计。
- `d2_data_association/scalable_3d_offline.py`：关联完成后才可调用的 3D truth sidecar IDSW/continuity evaluator。
- `d2_data_association/scalable_3d_performance.py`：冻结 episode 的 D2 发布语义哈希和阶段墙钟比较器。
- `d2_data_association/dry_run_adapter.py`：D1/AirSim-style dry-run 输入适配和 bus message 输出。
- `d2_data_association/d1_governed_adapter.py`：D1 frozen manifest/records 到在线安全 D2 radar/N-E frames 的转换和跳过诊断。
- `d2_data_association/replay.py`：离线 JSON/JSONL replay 读取、association report/log 输出和阈值敏感性 helper。
- `d2_data_association/replay_governance.py`：在线 truth 隔离、offline label evaluator、M-of-N 初始化、false-track、NIS/NEES 和 5v5 压力 fixture。
- `d2_data_association/offline_truth.py`：版本化 offline truth JSONL 合同、truth stripping 和 evaluator-only 评分视图。
- `d2_data_association/calibration.py`：N-target dense/crossing 至少 10-seed runner、每 seed 结果和 availability-aware 聚合。
- `d2_data_association/compat.py`：optional dependency 版本/原因探测、Stone Soup Detection 和 FilterPy CV filter 对象 adapter。
- `d2_data_association/p2_benchmark.py`：同一 frozen replay 下默认 GNN/Hungarian、模块内 JPDA/MHT 研究 adapter 与外部对象 adapter 的隔离比较合同。
- `d2_data_association/simulation.py`：crossing、dense 5v5、formation、occlusion、missed、false alarm 场景。
- `scripts/run_simulation.py`：CLI benchmark runner。
- `scripts/run_dense_crossing_calibration.py`：P1 多 seed 校准 CLI，单独输出 truth JSONL 和聚合 JSON。
- `scripts/run_p2_optional_benchmark.py`：读取 frozen replay/truth 文件并输出 P2 adapter comparison JSON。
- `scripts/run_scalable_3d_performance_comparison.py`：生成 200 规模 current-default-vs-optimized JSON 和中文曲线。
- `docs/ALGORITHM_AND_IMPLEMENTATION.md`：中文算法和实现说明。
- `docs/EXPERIMENT_REPORT.md`：离线仿真结果和解释。
- `docs/AIRSIM_INTEGRATION_PLAN.md`：AirSim 离线回放接入计划。

## 跨模块合同

- D2 输出的 `global_track_id` 是 D3 分配、D4 主动降级证据、D5 末端配准和 D6 指标评估的共同键。
- source 的 local ID、candidate/current canonical hint 不具备身份权威；只有 `CrossNodeTrackRegistry` 能创建或更新 canonical binding。多个合法观察者绑定同一 canonical ID 不增加目标基数，也不计为 D3 duplicate assignment。
- `REQUEST_COVARIANCE_INTERSECTION` 和 `REQUEST_EXACT_CORRELATED_FUSION` 是 D2 关联/相关性决策，不是已融合状态；数值融合及一致性统计由 D1/D6 owner 接续。
- D2 track-level `track_quality` 和 `association_risk` 是下游可消费的质量/风险证据；下游可以提高代价、延迟分配或标记复核，但不得用这些字段改写 `global_track_id`。
- D5 和 D7 不得改写、重绑或本地覆盖 D2 的 `global_track_id`。
- D2/D6 必须显式保留 `id_switch_count`；它不能被 RMSE、覆盖率或命中率替代。
- D2 输出的 `global_track_ids` 来自当前活动航迹集合，不截断或补齐到固定 2 或 5。
- D4 当前把 D2 风险分为软/硬两类：`association_ambiguity`、低 cost margin、candidate overlap 属于观察/二级 cue 证据；`id_switch_count` 增量、`duplicate_assignment_count`/`duplicate_track_risk` 和可用的 `track_continuity` 低于阈值属于硬风险证据。`continuity_available=false` 时不得把兼容数值 `0.0` 当作 continuity collapse。D2 只发布证据，不直接触发 `request_center_replan` 或降级。
- 多 seed 风险校准的 replay/report 应保留 `seed`、`episode_id`、`scenario_name`/`scenario`、`frame_index`、`drone_count`/`target_count`、gate threshold、`risk_profile`、`risk_profile_version`、`association_risk_threshold_version`、association logs、gate pass/reject count、motion/quality risk summary、dense/crossing sensitivity summary、M-of-N profile、false-track、NIS/NEES、`id_switch_count`、`track_continuity`、`duplicate_assignment_count` 和 soft/hard risk summary。在线 association log 只记录 schema/profile、measurement/active-track count 和 innovation 诊断，不携带 truth label、truth target count 或 NEES；标签、真值目标数和 NEES 只存在于 `offline_truth_evaluation`。
- 2026-07-11 P1 CV 批次、episode 证据和隔离 truth 由 main/runtime/D6 生产/评分；2026-07-12 PNG delivery 报告没有新增 D2 offline IDSW/continuity。D2 不连接 AirSim SDK。若继续做专用真实 dense/crossing 标定，应沿用已冻结 schema/profile，但它是后续性能研究而非 P1 合同缺口。
- main runtime 已具备 P1 D4/D5 calibration sweep，D6 已具备标准 AirSim calibration report bundle 自动生成。D2 的对齐目标是让自身 replay/report/log 字段能进入该 bundle 做分组统计；D2 不重复实现 sweep 编排、AirSim reset 或 D6 报告生成。
- 在线 D6 治理摘要可以记录 soft/hard risk frame rate，但不得在缺少 offline truth labels 时把它解释成 IDSW=0 或 continuity 正常；truth-based 指标必须保留 unavailable 状态，待离线评分后再进入多 seed 结论。

## 运行测试

从仓库根目录：

```bash
PYTHONPATH=research_modules/d2_data_association pytest -q research_modules/d2_data_association/tests
```

从模块目录：

```bash
pytest -q
```

## 运行仿真

```bash
python3 scripts/run_simulation.py --steps 24 --seed 7
```

可选输出：

```bash
python3 scripts/run_simulation.py \
  --steps 36 \
  --seed 7 \
  --json-out artifacts/d2_results.json \
  --markdown-out artifacts/d2_results.md
```

P1 N-target、至少 10-seed 校准：

```bash
PYTHONPATH=research_modules/d2_data_association \
python3 research_modules/d2_data_association/scripts/run_dense_crossing_calibration.py \
  --target-count 5 \
  --steps 12 \
  --output /tmp/msm-d2-calibration
```

输出目录包含 `calibration_summary.json` 和按 episode 分开的 `offline_truth/*.jsonl`；这些 truth 文件只供离线评分使用。

P1 长 governed replay 校准：

```bash
PYTHONPATH=research_modules/d2_data_association \
python3 research_modules/d2_data_association/scripts/run_long_replay_calibration.py \
  --target-count 5 \
  --steps 120 \
  --sample-period-s 0.2 \
  --output /tmp/msm-d2-long-replay
```

该入口固定使用默认 `GNNHungarianAssociator`，场景版本为
`d2-governed-long-replay/v1`，覆盖重复 dense crossing、交叉窗口遮挡、
周期漏检、近场虚警和延迟到达。输入帧由 D1/main 治理后按
`measurement_timestamp` 排序；D2 保留 `arrival_timestamp` 并报告 arrival
inversion/late measurement 暴露，但不宣称实现原始量测 OOSM 回溯。每 seed
输出 IDSW、identity/coverage continuity、false-track、RMSE、NIS/NEES
availability、版本化 gate/risk profile、中心 ID owner 和 online truth leakage。
量测数可以小于或大于目标数，目标数和代价矩阵均来自当前输入，不依赖场景名。

P1 dense/crossing 固定矩阵标定：

```bash
PYTHONPATH=research_modules/d2_data_association \
python3 research_modules/d2_data_association/scripts/run_p1_identity_calibration.py \
  --screening-manifest /path/to/screening-10seed-manifest.json \
  --confirmation-manifest /path/to/confirmation-20seed-manifest.json \
  --output /tmp/d2-p1-identity-calibration.json
```

manifest schema 为 `d2-p1-identity-calibration-input/v1`，每个 seed 显式给出
`replay_path` 和 evaluator-only `truth_path`，并冻结
`frozen_p95_loop_latency_budget_s`。runner 对全部 54 组 GNN 配置使用同一个
replay/truth digest，覆盖 gate `5.99/9.21/13.82`、quality-aware off/on、
lost/drop `1/3, 2/5, 3/7` 和 motion weight `0.5/1/2` 倍。轻量 JPDA 只在最佳
GNN 的输入、gate 和 lifecycle 上做离线同预算对照。缺少 10 或 20 个唯一 seed 时
对应阶段显式 `unavailable`，不会用 synthetic fixture 补齐或冒充 AirSim 结论。
准入报告使用 `d2-p1-identity-calibration/v2` 和版本化 ceiling-aware 联合门限，
只给出评审建议，不会替换默认 GNN/Hungarian。

`truth_path` 按 suffix 和 schema 显式选择：`.jsonl` 读取
`d2-offline-truth-label/v1`；`.json` 只接受 D1 freeze 生成的
`d1.airsim_offline_truth.v1`。D1 JSON adapter 校验 `evaluator_only=true`、NED
frame、有限 timestamp、非空 `truth_id` 和有限三维 `position_ned`，再按量测时间
映射到 governed replay frame，并投影为 D2 水平 N/E label。Down 分量只进入离线审计
annotation。无法唯一匹配 replay frame、位置不可用或 schema 不支持时直接拒绝，绝不
把 sidecar 内容写入在线 frame。

证据分类兼容 legacy `airsim` 和受治理的 `real_airsim_*` 来源标识，因此 main 生成的
`real_airsim_blocks_d1_governed_replay` 会在 screening、confirmation 和 JPDA 对照中
正确标为 `airsim_evidence=true`。包含 `airsim` 字样但不以 `real_airsim_` 开头的
synthetic 来源不会被误分类。该字段只描述证据来源，不参与参数排序或算法准入。

P1 高难度 replay 使用六个固定 `scenario_difficulty`：`nominal`、
`tight_crossing`、`dropout`、`clutter`、`delayed_noisy`、`combined`。manifest 可在
顶层设置统一难度，也可在 case 中覆盖；可选 `difficulty_metadata` 记录 main 实际注入
参数。D2 只校验和消费元数据，不在模块内生成 AirSim 数据。混合 manifest 的 case
唯一键为 `(scenario_difficulty, seed)`，每个出现的难度档都必须满足 screening 10 个
seed；confirmation 通常只提供 `combined` 的 20 个 seed。

每个 GNN/JPDA 结果新增 `aggregate_by_difficulty`，报告的 `difficulty_results` 直接给出
每档 baseline、最佳 GNN、JPDA 的 IDSW、identity continuity、false-track、RMSE 和
p95 latency，以及分档 admission。若所有受评算法在某档均为 `IDSW=0` 且
`identity_continuity=1.0`，该档显式标记
`scenario_still_non_discriminative=true`，禁止把理想但无区分度的 fixture 解释为候选
算法优于默认 GNN/Hungarian。在线 truth 隔离和 v2 版本化联合准入保持不变。

真实 governed replay 的观测压力使用纯离线 API：

```python
from d2_data_association import transform_d1_governed_replay

result = transform_d1_governed_replay(
    d1_governed_bundle,
    scenario_difficulty="combined",
    seed=7,
    declared_target_spacing_m=2.0,
)
# main 写 result.payload，并把 result.profile_metadata 放入校准 manifest。
```

transformer 不接收 truth sidecar：`dropout` 在量测时间中段删除 0.6-1.2 s 雷达记录，
`clutter` 每帧注入 1-3 条匿名雷达虚警，`delayed_noisy` 增加 0.2-0.5 s 到达延迟并将
协方差放大 3 倍，`combined` 组合三者。保留的记录维持 measurement timestamp、
arrival timestamp、covariance 和原 source lineage；延迟/噪声 profile 在保留原值
来源的同时生成受治理新值和追加 lineage。虚警仅使用 opaque ID，并带
`injected_evaluator_scenario`。

几何不能由该 API 伪造：`nominal/dropout/clutter/delayed_noisy` 只接受 main 声明的
约 4 m 捕获，`tight_crossing/combined` 只接受约 2 m 捕获。若 D1 provenance 已携带
`target_spacing_m`，声明必须一致；没有该字段时，报告明确标记为
`capture_declaration_only_no_truth_geometry`。输出包含 profile metadata、输入/输出
digest、实际注入参数、计数和 online truth leak 审计。

进入真实 AirSim P1 标定 manifest 时规则更严格：D1 adapter 会把
`target_spacing_m` 和 `d2_offline_stress_profile` 透传到每个 D2 frame；
`airsim`/`real_airsim_*` case 缺少 spacing、4 m/2 m 档位不符、frame 与 profile
数值冲突或 difficulty 冲突时直接拒绝。六档治理仍以 `(difficulty, seed)` 为唯一键，
允许不同 seed 保留不同的实际 dropout/delay/clutter 参数，仅 profile/schema/version
等不变量要求同档一致。分档摘要同时报告 NIS/NEES available seed count。

D1 offline truth 允许比 governed replay 更稠密。adapter 只在量测时间戳位于冻结
`1e-9 s` 容差且 frame 可唯一确定时生成 evaluator label；没有匿名传感器观测而缺失的
replay frame 记为 unmatched，不做最近邻补配。输出 `complete/partial/unavailable`、
matched/unmatched sample count、原因和不含身份的样本索引/时间审计。非法 sidecar、
重复样本或同时间多 frame 无法消歧仍 fail closed；truth 不进入在线 frame。

## 可选集成

`filterpy` 和 `stonesoup` 不是运行时依赖。默认环境缺依赖时，对应行输出 `dependency_available=false`、`executed=false` 和明确的 `unavailable_reason`；不会静默回退。隔离环境已验证 FilterPy 1.4.5 与 Stone Soup 1.9.1 的对象 adapter，但完整外部框架 JPDA/MHT、EKF/UKF/IMM 和 optional 端到端 IDSW/continuity 仍未实现。模块内 `JPDAAssociator`/`MHTAssociator` 不需要外部依赖，只作为显式 research adapter 运行，不能解释为完整算法已经实现。

```bash
PYTHONPATH=research_modules/d2_data_association \
/home/linux/.cache/msm-p2-venv/bin/python \
  research_modules/d2_data_association/scripts/run_p2_optional_benchmark.py \
  --replay /path/to/frozen_replay.jsonl \
  --offline-truth /path/to/offline_truth_labels.jsonl \
  --output /tmp/d2-p2-benchmark.json
```

输出 schema 为 `d2-optional-framework-benchmark/v2`。每行统一包含 `id_switch_count`、`track_continuity`、`latency_seconds` 和 `unavailable_reason`：GNN/JPDA/MHT 行在离线标签有效时提供身份指标；FilterPy/Stone Soup 对象行的身份指标保持 unavailable，并用 `adapter_only_no_end_to_end_association` 说明原因。所有行继续声明完整 JPDA/MHT 的真实实现状态。输入若为 D1 governed replay，报告 `input_metadata.d1_governed_adapter` 会给出接受的 radar 数量、跳过模态及投影方法。

## 2026-07-14 AirSim `T008` 来源谱系膨胀 P1 修复

- 修复前审计对象为真实 Blocks episode
  `p1_terminal_closure_truthisolated_preflight_v2_20260714_m5n2_baseline_seed001`，
  seed 1、351 帧、在线目标数 2。D1 在 31.3 秒由 2 条航迹增至 3 条：新增
  `global_track_003` 只有单次雷达支持，却与原 `global_track_002` 同时落入 D2
  `T002` 门限；之后 `global_track_002` 又从约 `[77,-19] m` 跳至
  `[13.5,-24.9] m`。D2 未使用上游航迹谱系，因而累计 birth 8、drop 4，并在
  34.4 秒生成 `T008`；D3 随后把它纳入新计划，放大为 plan/pair churn。
- D2 修复由 `GlobalTrack.source_track_ids`、GNN 来源连续性代价、门内影子 birth
  抑制和已绑定来源的马氏大跳隔离组成。来源 ID 只是 D1 航迹谱系，不是目标真值；
  新来源在几何允许时可并入既有 D2 航迹，D2 规范 `global_track_id` 不被重写。
- 修复后验证为 4 帧匿名在线回归：2 条目标轨迹、1 条近邻重复来源和 1 次同源
  teleport；验收阈值为活动 D2 航迹始终恰为 2、影子 birth 抑制 1 次、大跳隔离
  1 次、truth 输入 0。专项与完整回归通过，最新结果为 `99 passed, 1 warning`；
  warning 仍是本机 Matplotlib `Axes3D` 环境问题。
- 修复后的同 seed 真实复跑已经完成，详见下一节。2026-07-15 后续 M5N2 已完成
  baseline/candidate 各 10 seed，但未注入显式 teleport/影子扰动，也未形成该批 D2
  offline identity 评分，因此仍不能把 seed 数量达标外推为 P1 参数冻结结论。

## 2026-07-14 Post-batch M5N2 同 seed 复验

审计对象为以下两组真实 Blocks、M5N2、seed 1 episode，均不保存在线真值：

- `p1_terminal_closure_postbatch_seed1_20260714_m5n2_baseline_seed001`；
- `p1_terminal_closure_postbatch_seed1_20260714_m5n2_candidate_soft_prediction_trend_coast_seed001`。

baseline 共 142 帧，candidate 共 141 帧。两组 D1 均在前 2 帧后稳定输出
`global_track_001/global_track_002`；D2 分别在后续 140/139 帧只维护
`T001/T002`，最大活动规范航迹数为 2，未再出现 `T008`。两组 truth-free 生命周期
均为 `birth=2, lost=0, drop=0, rebirth=0`，状态只发生
`tentative -> confirmed -> engageable` 各两次。来源绑定最终均为
`global_track_001 -> T001`、`global_track_002 -> T002`。

在线摘要按设计保持 `id_switch_count=None`、`track_continuity=None` 和
`truth_assignment_unavailable`；这不是零 IDSW 的在线声明。独立 sidecar 只在写盘后
进入 evaluator：对 D1 governed replay 运行现有 `run_airsim_replay_association()`，
两组均得到 IDSW 0、identity/coverage continuity 1.0、false track 0、online truth
isolation violation 0。对 main 实际发布的 track records 做独立位置匈牙利裁决时，
baseline/candidate 分别得到 IDSW 0、continuity 0.985915/0.985816；差异仅来自 D1/D2
启动前 2 帧尚无规范航迹，混淆关系始终为 `TGT-001 -> T001`、
`TGT-002 -> T002`。

本次平稳 episode 中 `suppressed_births=0`、quarantine 0、source conflict 0，说明
来源治理没有误触发，但没有真实激发 teleport 抑制。teleport/影子能力仍由匿名专项
回归证明。当前判断是：`T008` 同 seed 复发缺口已关闭；2026-07-15 的 20-case 已满足
普通 M5N2 运行数量并补齐 D2 阶段时延，但没有覆盖重复来源、teleport、漏检、杂波、
合法新目标 birth 延迟或独立离线身份评分，相关 P1 仍开放。默认 GNN/Hungarian、中心
`global_track_id` 所有权和在线 truth 隔离均不变。

## 2026-07-16 来源身份治理显式指标

- `MetricsRecorder.summary()`、逐帧 `AssociationRiskSummary`、replay risk summary、
  threshold sensitivity 逐 seed 行及多 seed/校准聚合现在显式保留
  `source_binding_conflict_count`、`source_lineage_quarantine_count` 和
  `upstream_local_identity_rejection_count`；`id_switch_count` 仍是独立且显式的
  truth-based 指标，未被三项在线治理诊断替代。
- 前两项分别只累计每帧 `AssociationResult.metadata.source_binding_conflicts` 和
  `quarantined_sources` 的条目数。第三项只接受经 `Tracker.step(frame_metadata=...)`
  验证的同名非负整数；字段缺失为 0，布尔、浮点、字符串、`None` 和负数均在预测、
  关联或建轨前 fail closed。该上游计数只记录 D1/main 已拒绝的本地身份塌缩候选，
  不合成 Detection、不创建 Track，也不把 local/source ID 升级为 `global_track_id`。
- 2026-07-16 专项验证包含连续同源、同源跨两个规范航迹冲突、绑定来源马氏不连续隔离、
  零观测上游审计、5 类非法 metadata 和旧帧无 metadata 兼容。两条 3-frame replay
  seed 7/8 各得到 conflict=1、quarantine=1，上游拒绝分别为 2/4；多 seed 均值为
  1/1/3。验收阈值为精确计数、非法输入零状态副作用和完整回归零失败，结果为
  `123 passed, 1 warning`；warning 仍是本机 Matplotlib `Axes3D` 环境问题。
- 本批没有启动 AirSim、没有读取像素或 actor/truth ID、没有复制 D5
  `bright_hungarian`，也没有改变默认 GNN/Hungarian、马氏门限、来源连续性权重、
  lifecycle 门限或风险阈值。三项计数当前是审计证据，不自动新增 soft/hard risk 原因；
  至少 10 个真实 duplicate-source/teleport/合法新目标受治理 case 的统计标定仍开放。

## 2026-07-20 scalable 3D 离线身份映射合同

D2 新增 `scalable_3d_identity.py`，只用于在线关联结束后的 evaluator。公开版本为：

- evidence bundle：`d2.scalable3d_identity_evidence.v1/v2`；
- observation truth adapter：`d2.scalable3d_observation_truth.v2`，并严格适配现有
  v1 和
  `scalable3d-offline-truth-v1` 的 `observation_id -> truth_entity_id` sidecar；
- frame mapping：`d2.scalable3d_global_track_truth_mapping.v1`；
- metrics：`d2.scalable3d_identity_metrics.v1`；
- evaluation artifact：legacy `d2.scalable3d_identity_evaluation.v1` 和带承诺审计的
  `d2.scalable3d_identity_evaluation.v2`。

公开入口包括 `ObservationLineageRef`、`GlobalTrackLineageEvidence`、
`create_scalable_3d_identity_evidence_bundle()`、
`evaluate_scalable_3d_identity[_files]()` 以及 evidence/truth/evaluation 的确定性
writer/loader。文件入口要求 evidence bundle 的外部 SHA-256，同时校验其绑定的 D1
records、D2 records、truth sidecar 三个 SHA-256、在线 schema、truth-isolation audit
和 record sequence。sequence 不是仅做存在性检查：每条 mapping 还必须逐项绑定被哈希
D2 record 中同一 frame 的 D2-owned canonical ID、六维 `state_ned`、`6x6 covariance`、
lifecycle/association/source lineage，并回查对应 D1 observation lineage；任一不一致直接
拒绝。逐帧输出 mapping status、候选 truth、证据/replay/重复计数、冲突原因和 source
hashes。

身份只沿 `source_lineage` 最终的 `observation_id` 连接独立 truth label。一个 truth 对应
多条有效 global track 会计入 `duplicate_truth_to_track_count`；一条 track 的证据指向
多个 truth、同 lineage 被多 track 声明、标签冲突、缺标签、未标记重放、时间窗冲突或
lifecycle 冲突时为 `ambiguous/unavailable`，不会按名称、actor ID、终态邻近或最近距离
选 truth。IDSW、identity/coverage continuity 和 duplicate 采用 `MetricsRecorder` 的
逐帧 first-assignment 口径；只要身份完整性不足，值就是 `None + availability=false`，
不以 0 填补。

2026-07-20 新增 23 个专项，覆盖稳定身份、真实 ID switch、一对多/多对一、缺失/重复/
冲突 lineage、显式 replay generation、标签冲突与篡改、时间窗、dropped 后复用、无
truth、37 目标动态规模、schema/hash/在线 truth 隔离、六维 source binding、D2 ID owner、
在线 IDSW null/unavailable 和 public artifact availability round-trip。完整 D2 回归为
`162 passed, 1 warning in 30.63s`；warning 仍为环境 Matplotlib
`Axes3D`。本轮未修改在线 association、`global_track_id` owner、门限、JPDA/MHT、控制
路径或默认 GNN/Hungarian。当前只关闭 D2-owned 离线合同；main 持久化 evidence 与 D6
接线、AirSim/point-mass 正式多 seed 身份性能仍开放。当前 main producer 会跳过无
source lineage 的 D2 track/frame；在其按完整 D2 frame 集合持久化 available/unavailable
evidence 前，不能把现有接线写成端到端 identity metrics 已可用。

## 2026-07-22 陈旧后验重放治理

active-risk 5v5、seed 1005 暴露出一条独立于空间近邻的重复航迹路径。D1 的一条预测型
后验在没有新传感器观测时仍按当前状态时刻发布，但 `latest_observation_id` 长时间保持
为 `radar-s000002-d0003`。旧 D2 只看每帧重新生成的 detection ID，把同一底层观测
重复计为新命中，最终令 `GT3D-000004` 和 `GT3D-000006` 同时 confirmed。两条航迹
相距约 1.5--1.6 km，不能用宽距离门强行合并。

`Scalable3DTracker` 现已在 GNN/Hungarian 前增加在线观测新鲜度治理：

- 以 `latest_sensor_id + latest_observation_id` 形成不解析内容的 opaque evidence key；
- 同一 key 跨帧再次出现时从关联输入中隔离，不参与状态更新、命中计数或确认；
- 同一 key 携带冲突的源量测时间时 fail closed，并输出时间冲突审计；
- tentative 航迹连续两帧没有新证据后删除，第一次漏配只重置连续命中，保留短时重获；
- 航迹合并只允许共享 observation/source 证据、六维位置和速度统计门均通过、且双方
  没有在同帧同时获得新证据。survivor 依次按生命周期成熟度、创建时间、命中数和
  `global_track_id` 选择；状态使用协方差交叉融合，不累加重复命中。

真实复现命令：

```bash
PYTHONPATH=research_modules/d2_data_association \
python3 research_modules/d2_data_association/scripts/reproduce_active_risk_seed_1005.py
```

2026-07-22 的 2.2 s 单 seed 结果为：10 个 D2 发布帧，航迹数
`5,6,6,5,5,5,5,5,5,5`；隔离陈旧后验 9 次、tentative 陈旧删除 1 次、统计合并 0 次，
最终保留 `GT3D-000001` 至 `GT3D-000005`，`GT3D-000006` 被删除，在线真值使用为 0。
5 个合成专项覆盖重复确认、seed 1005 等价短时重生、近邻独立目标、协方差合并边界和
异步新证据；真实 seed 专项 1 个。完整 D2 回归为 `168 passed, 1 warning in 26.15s`，
warning 仍为本机 Matplotlib `Axes3D` 环境问题。

main 于 2026-07-22 先完成 development 复跑，随后以提交 `0fa7c00` 生成 clean-tree
active-risk seeds 1000--1019 结果。clean manifest 记录 `repository_dirty=false`、源提交
统一、20/20 物理窗与配对比较可用、D4 adoption 188/188、两臂各 1960 条命令、100 条
离线唯一身份映射。seed 1005 保持 GT1-GT5 五条唯一映射，在线 truth use 0。两臂在
1 s 计划有效窗内均为 0 次 5 m 拦截；counterfactual、causal 和 production runtime ACK
仍 unavailable，因此该 clean 结果只关闭可复现集成运行，不证明降级收益或拦截效果。

## 2026-07-22 长 episode 声明治理

`Scalable3DTracker` 新增 `ObservationClaimLedgerConfig`。默认配置版本为
`d2-observation-claim-policy-v2`，包含 retention、max-count 和 max-lateness。新观测先按
`current_state_time - max_lateness` 检查是否过旧；claim 只有在
`current_state_time - max(retention, max_lateness)` 之后才可淘汰。淘汰索引使用最小堆，
旧量测即使 key 已从字典移除，也会被 admission watermark 拒绝，不能重新形成 hit 或
birth。无源量测时间的 claim 不淘汰；达到 max-count 后新证据 fail closed，内存不再增长。

逐帧 metadata 和 summary 现区分 `observation_measurement_too_old`、
`observation_identity_timestamp_conflict`、`repeated_latest_observation_id`、
`duplicate_observation_within_scan` 和 `observation_claim_ledger_overflow`。公开 ledger
summary 包含配置/schema 版本、current/peak/evicted、overflow/too-old/replay、两个水位线、
undated、eviction index、track observation reverse-index、`tombstone_count=0` 和
anti-replay mode。

乱序整帧由可选 `Scalable3DOOSMScanAdapter` 在 Tracker 前处理。它按到达顺序接收完整
common-epoch scan，在 max-lateness 水位线后按量测时间释放；超窗、早于已释放状态或缓冲
溢出的 scan 整帧拒绝。`flush()` 只用于 episode 结束后的有序排空，不做状态回溯、固定
滞后平滑或重放。

本轮新增 15 个模块测试。5 目标 x 500 帧和 40 目标 x 200 帧长期循环均满足 claim
peak 不超过配置上限、overflow=0 且发生安全淘汰。离线 benchmark 的 3/12 目标、16 帧、
0.75 m 间距分别有 43/187 条合法检测，误抑制 0、近邻召回 1.0、错误 coalescence 0、
确认延迟均值/P95 0.25/0.25 s、离线 IDSW 0；truth 只在 `step()` 后进入 evaluator。
完整 D2 回归为 `183 passed, 1 warning in 29.08s`。真实 AirSim 的 observation ID 稳定性、
时钟误差、距离/遮挡/杂波门限，以及 20/50/100/200 多规模多 seed 性能证据仍开放。
在线 `id_switch_count` 继续显式为 `None/unavailable`。

### main-owned 接入建议

main 构造 Tracker 时应显式传入并写入 manifest：

```python
tracker = Scalable3DTracker(
    observation_claim_config=ObservationClaimLedgerConfig(
        config_version="d2-observation-claim-policy-v2",
        retention_seconds=30.0,
        max_count=100_000,
        max_lateness_seconds=5.0,
    ),
    replay_coast_config=ReplayCoastConfig(
        config_version="d2-replay-coast-policy-v1",
        grace_seconds=0.5,
    ),
)
```

若 main 已保证 scan 的 state-valid `measurement_timestamp` 单调，可直接调用
`tracker.step()`。若 transport 按 arrival 顺序交付且完整 scan 可能乱序，应使用
`Scalable3DOOSMScanAdapter`。每个 `submit_scan()` 传入一个完整共同量测时刻的 scan；空
scan 必须显式传 measurement/arrival time。一次 submit 可能释放 0 到多条 result，main
应按 result 自带时间逐条发布。`flush()` 只在确认该 episode 不再有输入时调用，reset 后
重新构造 adapter/tracker，不能把 flush 当作周期性回溯更新。

在线持久化建议包括 result 的 `observation_rejection_reason_counts`、累计 reason、
`observation_claim_ledger`、eviction count/events，以及 adapter summary 的
submitted/admitted/released/rejected、current/peak scan 与 detection buffer、measurement inversion、拒绝
原因、水位线和 last released time。离线 D6 可消费 governance benchmark 的 false
suppression、nearby recall、erroneous coalescence、confirmation latency 和 offline
identity metrics；这些 truth 指标不得写回在线总线。

## 2026-07-22 重复后验短时 coast

D1 全量发布后验时，无新量测的航迹仍可能携带上一条 `latest_observation_id`。D2 继续把
这类 detection 按 `repeated_latest_observation_id` 隔离，不进入候选图、状态量测更新、
hit 或 birth。若该 claim 已绑定现存中心航迹，且当前状态时刻距航迹
`last_update_time` 不超过版本化 `ReplayCoastConfig.grace_seconds`，该航迹本帧只做常
速度预测，不增加 miss。`last_update_time` 和宽限起点不因 replay 刷新，超过宽限后立即
恢复原 miss/lost/drop 逻辑。时间冲突、过旧量测、账本溢出和未绑定 claim 均不 coast。

逐帧结果公开 `replay_coast_count/events/track_ids/reason_counts/config` 和
`missed_track_ids`；Tracker summary 公开累计 coast count、reason 和配置。coast 不增加
常驻 ledger，额外持久状态只有定长整数计数。12 目标、200 帧、雷达每 0.5 s 更新的全量
后验循环中，1920 次相邻 replay coast，所有航迹 misses 为 0，claim 仍受 max-count
约束。合并前 main 接线中的 active-risk seed 1005 曾从旧基线的 `5,6,6,5` 改为前四帧
持续 5 条航迹，9 次 replay 均未形成额外 birth 或 tentative stale drop；当前尾部合并后
该 seed 的集成 replay 为 0，见下一节。两种路径在线 truth 使用均为 0。
完整 D2 回归为 `188 passed, 1 warning in 31.03s`；warning 为既有 Matplotlib
`Axes3D` 环境提示。

## 2026-07-22 scalable 尾部合并后证据复核

main 当前在 episode 结束时仍按量测时刻逐条融合并发布 D1 尾部扫描，但只把最终融合后验
送入 D2 一次；该次更新只用于状态和审计收口，不生成相机或运动控制命令。active-risk
5v5、seed 1005、1.1 s 当前运行产生 2 个 D2 发布帧，均为 GT1-GT5 五条规范航迹。累计
birth 5、claim 10、replay quarantine/coast 0、tentative stale drop 0、coalescence 0；
D2 finalize 调用 1 次，`coalesced_release_count=5`，在线真值使用为 0。旧文档中的
`claim=26、replay=9` 属于尾部逐次调用 D2 的上一版 main 接线，不再代表当前集成行为。

D2 的 bounded replay/coast 能力没有删除。12 目标、200 帧模块 fixture 仍以 1920 次
重复后验验证宽限、超时和冲突边界。seed1005 复现报告现为
`d2.active-risk-seed1005-reproduction.v3`，接受 replay=0 或有界 replay；两种分支均要求
全部发布为 GT1-GT5、owner 为 `D2_center`、birth 5、coast 与 quarantine 一致、无 stale
drop/错误合并且在线真值使用为 0。当前 2.2 s 复跑得到 6 个五航迹帧、replay 0，
`acceptance_passed=true`。完整 D2 回归为 `189 passed, 1 warning`，未修改 D2 算法。

200v200、seed 42000、2.2 s 的最新持久化 development 制品将尾部 31 次 D2 调用合并为
1 次并记录 `coalesced_release_count=30`。常规 D2 关联 8 次共 6.135 s，尾部关联 1 次为
2.033 s；claim current/peak 为 `1583/1583`，容量 60000，overflow/too-old 0，在线真值
使用 0。`1976/1976` 来自合并前的上一份 development 制品，不能与合并后的调用次数和
时延拼接成同一结果。以上均来自脏工作树质点运行，不是 AirSim、实时性或完整 200v200
验收。

快速治理初跑为脏工作树 development 证据。随后在提交
`e4d66db02a0b8f1b867a0e81b4a73de84588426b` 上完成 20/50/100/200 四个规模、
每档 5 个 seed 的 formal/clean 复跑。20 个 manifest 全部记录
`evidence_tier=formal`、`repository_dirty=false` 和同一源提交；输入清单绑定的
20 个 manifest、20 个 online audit 和 20 个 evaluator sidecar 共 60 个 SHA-256
全部匹配。

四档 claim peak/capacity 依次为 `2390/4800`、`6020/12000`、
`12070/24000`、`24170/48000`，安全淘汰依次为 285、735、1485、2985，
overflow/too-old 均为 0。离线评估侧近邻召回率均为 1.0，误抑制率和错误
合并率均为 0，确认延迟均值/P95 均为 0.25/0.25 s；20 个 episode 在线
真值使用总数为 0，sidecar 全部为 evaluator-only 且未被在线路径消费。
该证据只关闭 clean 提交上的多规模观测治理复跑，不关闭完整 D1-D7 融合、
真实 AirSim、多场景身份连续性、实时服务等级或物理拦截闭环。

保留 seed 1011 和 1019 在 1.0 s 干预帧只有 4 条在线航迹，后续新鲜观测到达后终态恢复
5 条 confirmed。scalable 验收仍应以实际 D2 库存连接 D3，并单独报告相对场景目标数的
可见性缺口；不得用离线 truth 补轨或硬编码目标数。

## 2026-07-22 200 规模关联热路径收敛

clean 基线目录的 `nominal/200v200` seeds 42000--42004 与候选重跑形成 5 组冻结输入
对照，每组 8 个常规关联周期和 1 个尾部收束周期。候选只优化在线身份 metadata 审计：
有界缓存键归一化和禁用键分类，使用原生前后缀判断，并删除 D1 adapter 的一次冗余
预扫描。`Detection3D.__post_init__` 与 `Scalable3DTracker.step()` 的双边界审计仍保留，
构造后篡改继续 fail closed。

常规关联平均累计墙钟从 `7.5552 s` 降至 `2.2033 s`，尾部收束从 `2.2747 s` 降至
`0.5646 s`；单 episode D2 合计从 `9.8299 s` 降至 `2.7679 s`。五组总墙钟为
`49.1497 -> 13.8397 s`，总体加速 `3.551x`。45/45 周期的完整发布、关联、规范 ID/
生命周期、claim/审计哈希一致，在线 truth use 为 0。默认 GNN/Hungarian、3D 门控、
中心 `global_track_id`、claim ledger、生命周期和显式 IDSW/continuity unavailable 语义
均未改变。

专项报告见 `docs/D2_SCALABLE_3D_PERFORMANCE_BENCHMARK_CN.md`，机器可读比较 schema 为
`d2-scalable3d-performance-comparison-v1`。候选运行仍是未提交开发态，不构成实时 SLA、
AirSim 或完整 200v200 闭环验收。

### 2026-07-22 长时元数据审计收口

10 秒、48 周期的 200v200 profile 进一步确认，随时长增长的主要成本来自 D1 在每条
`GlobalTrack` 上重复携带 `sensor_health`、`association_audit` 和 `latency_audit`，D2
逐轨递归审计同内容诊断树。D1 批输入现在先完整审计身份安全；批内内容相同的共享诊断
只审计一个代表，任一不同值仍完整审计。通过后只把双时间戳、观测谱系、来源和帧等 D2
实际消费字段带入 `Detection3D`。

最终审查加固代码的可复现 200 航迹、48 周期基准为
`16.858297 -> 6.472896 s`，加速 `2.604444x`，48/48 周期语义一致。既有 10 秒对照
`35.8121 -> 5.5057 s` 和五 seed 对照是在自定义 Mapping 等价审查加固前运行；其
48/48、45/45 周期语义哈希和在线 truth use 为 0 的证据仍有效，最终加固性能需 main
复跑。审查加固后的专项为 `25 passed`，加固前全量为 `214 passed, 1 warning`。默认
GNN/Hungarian、三维门控、中心 ID、claim/replay/stale、生命周期和显式 IDSW 语义未改。
详见 `docs/D2_SCALABLE_3D_LONG_DURATION_PERFORMANCE_CN.md`。

## 2026-07-22 关联内核操作数归因与严格等价优化

针对 clean 代码基线 `8f86192` 的 200v200、seed 42000 长短增长信号，冻结比较文件中
10 秒常规 D2 association 为 `8.062584 s`，finalize 为 `0.208472 s`；常规阶段相对
2.2 秒 episode 的归一化增长为 `1.993045x`。本轮不重新运行场景，只读取同一 10 秒
episode 的 `online_observations.jsonl`，文件 SHA-256 为
`3d2b4ae9f8036ae036d877a9f0e48fc7b7b1d9555bc9662b909cc9df2206924e`；未读取 truth
sidecar，在线 truth use 为 0。

48 周期固定操作数为：输入 9644、fresh 9233、replay quarantine 411、dense pair
1,820,766、空间候选/位置马氏求解 9215、合法边 9017、匹配 9012。9012 个候选连通
分量的峰值矩阵只有 2 个单元，说明该输入的主要重复成本是 covariance/innovation，
不是大型 Hungarian。候选批量计算检测/航迹最大特征值和 KD-tree 查询半径，复用关联边
已计算的 velocity NIS，跳过 1x1 Hungarian，并只复用刚由 D1 adapter 完整治理且
`covariance_regularized=false` 的 6x6 covariance 结果。regularized 输入继续完整回退。

预验证状态不是 `Detection3D` 构造参数；普通构造无法传入。负例使用位置和速度边缘各自
正定、但交叉项使整体最小特征值为负的 6x6 矩阵，并伪造 consistency 字典，仍由完整
6x6 governance 拒绝。公开 DTO、`to_dict()`、门控、合法候选、关联频率、中心
`global_track_id`、`id_switch_count` 和生命周期语义均未改变。

同一输入各 1 次 warmup、7 次计时中，adapter 中位数 `2.127001 -> 1.913712 s`，tracker
`2.747088 -> 2.118685 s`，合计 `4.859477 -> 4.018963 s`，加速 `1.209137x`、墙钟降低
17.3%，7/7 对应样本更快。baseline/candidate 固定诊断逐项相等，48/48 周期完整公开结果
及 tracker 状态严格相等，双方语义 SHA-256 均为
`dd3f65f01fd5e0941fe5c37def42650edd7107213f7ae97c528c64688a8721ab`。机器报告见
`docs/d2_association_hotpath_benchmark_20260722.json`；完整 D2 回归为
`219 passed, 1 warning in 41.91s`。

该结果仅是当前主机上的冻结质点在线回放，不是 AirSim、实时 SLA 或完整 200v200 闭环
证据。真实 observation ID/时钟、代表性遮挡/杂波/OOSM、极端大连通分量、固定硬件周期
分位数、多 seed 离线 IDSW/continuity 和完整闭环仍为 P1。

## 2026-07-22 三 seed 集成候选复核

main 在独立 clean worktree 中比较 reference `8f86192` 与 candidate `f80b5bd`。场景固定为
nominal 200v200、10.0 s，随机种子为 42000、42001、42002。三个 seed 均为有限状态，
`online_truth_use_count=0`；每个 seed 的 D2 association 调用数均为 47。D2 association
累计耗时的三 seed 均值从 `8.317513 s` 降至 `7.671266 s`，减少 `0.646247 s`，相对下降
约 `7.77%`。三组终态 D2 航迹数分别为 `205/204/203`，reference 与 candidate 完全相同。

main 的跨提交逐条审计确认 D2 在线发布语义和 topic counts 三组均一致。下游比较只按
D3 plan occurrence/version 规范化独立运行产生的不透明 `plan_id`；规范化前先验证 ACK
原始载荷 SHA。审计没有忽略 owner、version、coalition、`global_track_id`、command 等
业务字段，D2 发布记录本身不依赖该计划号规范化。

候选仍采用批量 KD-tree 查询和 covariance 特征值计算，复用同周期匹配边的 velocity
innovation 与已由 D1 adapter 完成的 consistent covariance governance；只有通过全部
门控的 1x1 连通分量绕过 Hungarian。regularized、非对称、非 PSD 或其他不能证明可信的
covariance 继续走完整治理路径，候选集合、门限、关联频率和中心身份权威均未放宽。

这批数据把 D2 单 seed 冻结回放优化提升为三 seed clean 集成非退化证据，但不构成系统
实时性结论。短长对照仍把 `module.d2_association` 列为超线性阶段；真实 AirSim 时钟与
observation ID、遮挡/杂波/OOSM、多 seed 离线 IDSW/continuity、极端大连通分量和固定
硬件周期分位数继续作为 P1。2026-07-22 当前工作区完整 D2 回归为
`219 passed, 1 warning in 49.75s`，验收阈值为零失败；warning 仍是环境中的 Matplotlib
`Axes3D` 导入提示。

## 2026-07-22 scalable 3D 部分身份诊断

`d2.scalable3d_identity_evaluation.v1/v2` 均可附带
`d2.scalable3d_partial_identity_diagnostics.v1`。原 `metrics` 合同没有变化：只要存在
歧义、缺标签或完整性阻断，`id_switch_count`、continuity、duplicate 和 confusion
matrix 仍为 `None + unavailable`。新增块只描述可证明的离线证据，不参与在线关联、
门控、生命周期或 `global_track_id` 绑定。

映射覆盖率的分母只包含 `created/matched` 映射；lost、dropped 和 unmatched 记录保留在
总状态计数中，但不进入身份评分。完整可评估帧要求本帧真值存在集合非空，且每条受评分
映射都唯一对应本帧存在的真值。部分下界锚点另有更严格条件：同一真值在该帧必须恰好
对应一个唯一可评估 `global_track_id`。同一真值对应多条航迹时，严格指标仍按既有持久化
顺序保留 duplicate 和代表航迹语义；部分诊断不从中选代表，而是排除该真值帧并记录
`multiple_evaluable_global_tracks_for_truth_frame`。转移覆盖率使用相邻真值存在帧；
IDSW 下界比较每个真值连续的唯一锚点。锚点区间互不重叠，唯一航迹变化至少证明一次
切换。没有唯一锚点转移时下界保持 unavailable，不写 0。缺失或歧义证据不能确定完整
转移全集，因此不发布上界。

本次只读复算 clean source commit `0d2da25` 的 nominal 200v200、10.0 s、seed 1000，
共 48 帧和 9644 条 track/frame 映射。原状态计数保持
available/ambiguous/unavailable=`8906/13/725`。其中 9038 条属于受评分映射，606 条
lost/dropped/unmatched 审计映射不评分；8906 条可评估，映射覆盖率为 `98.5395%`；
119 条受评分映射缺 truth label。完整可评估帧为
`3/48`，相邻真值转移覆盖为 `0/9400`；1 个真值帧因对应两条可评估航迹被明确排除。
该帧原本也不是完整可评估帧，因此修正后仍有 385 个唯一锚点区间，证明 IDSW 下界为 7。
严格 IDSW 仍因 `multiple_truth_targets_for_global_track` 为 unavailable，7 不能写成
完整 IDSW。该复算是单 seed producer 合同检查，不是 20-seed 结果。

专项测试覆盖全可用、部分缺失、歧义、双目标交叉、一真值多航迹、零转移分母、在线真值
隔离、诊断篡改和旧 v1 制品兼容，相关身份测试共 32 项；完整 D2 回归为
`228 passed, 1 warning in 29.26s`。重复映射专项保留严格 `IDSW=1` 和 duplicate=2，
同时验证部分下界 unavailable。main 后续需重新生成正式批次制品；D6 需显式接入
`partial_identity_diagnostics` 后才能汇总覆盖率和下界。当前变更不关闭真实 AirSim、
困难场景多 seed IDSW/continuity 或固定硬件时延 P1。

## 2026-07-23 20-seed 严格身份阻断复核

新增 `d2.scalable3d_identity_blocker_diagnostics.v1` 离线诊断合同和
`run_scalable_3d_identity_blocker_audit.py`。诊断器重新校验 D1/D2 在线记录、独立
观测真值 sidecar、身份 evidence 和 evaluation 的 SHA-256，并重放 producer。它只使用
`observation_id`、量测时刻、D1/D2 来源谱系和独立离线标签；位置、距离、目标名称、
actor ID、末端接近和后验最近邻均被排除。在线 Tracker、中心 `global_track_id` 和严格
指标公式未修改。

clean `5263e2b` nominal 200v200、10 秒、seed 1000--1019 的 20 组制品均通过来源哈希、
在线真值隔离和 producer 重建一致性检查。严格 IDSW 为 `0/20` 可用。逐条谱系确认
118 个受评分航迹帧确实把多个真实目标混入同一全局航迹，形成 107 个连续时间段；另有
2464 个受评分映射缺少显式真值或非目标标签，形成 2451 个时间段。该结果不是分母定义
造成的伪阻断。严格指标继续 fail closed，部分下界不回填 strict，也不生成上界。

部分证据汇总为 mapping `178531/181110`、完整帧 `103/959`、相邻转换
`1149/187800`。19 个 episode 的保守 IDSW 下界合计为 `199/15215` 个唯一锚点区间。
D1 一致性证据有 191425 条可用估计，其中 188951 条可通过精确谱系形成唯一候选；
剩余 2474 条全部缺显式 truth/non-target 标签。由于 D1 v1 consumer 要求全部可用估计
都有映射，完整 `d2_lineage_mapping` 为 `0/20` 可发布。诊断器在不完整时输出空
`mapping_records` 和原因，不发布会被误用的部分 sidecar。

提交内中文报告和聚合 JSON 为
`docs/D2_SCALABLE_3D_IDENTITY_BLOCKER_AUDIT_CN.md` 与
`docs/d2_scalable_3d_identity_blocker_audit_20260723.json`；本机逐 episode 明细位于
`outputs/scalable_3d_identity_blocker_audit_20260723/`。新增 4 项专项测试覆盖多真值
连续时间段、D1 完整映射正例、缺标签和缺谱系 fail-closed；完整 D2 回归为
`238 passed, 1 warning in 32.88s`，warning 为既有 Matplotlib `Axes3D` 环境提示。
剩余修复属于上游边界：D1 跨模态门控/航迹分裂、离线标签对每条观测的显式处置，以及
main/D1 对带覆盖率部分误差指标的单独合同。D2 不用多数投票或最近邻伪造严格身份值。

## 2026-07-23 observation truth v2 处置合同

离线 sidecar 当前规范版本为 `d2.scalable3d_observation_truth.v2`。每条记录必须携带
`observation_id`、`measurement_timestamp` 和 `disposition`：

- `target` 必须且只能携带一个 `truth_target_id`；
- `known_false_alarm` 不携带 `truth_target_id`；
- `unknown` 不携带 `truth_target_id`，并继续阻断严格身份指标。

旧 `d2.scalable3d_observation_truth.v1` 和 `scalable3d-offline-truth-v1` 仍可读取，
其 target-only 记录按 `target` 规范化；writer 统一写出 v2。producer 必须显式提供
处置，D2 不读取 observation ID 中的 `fa` 文本，也不使用位置、距离、actor 名称或在线
状态推断。

目标观测与已知虚警出现在同一谱系时，唯一目标候选继续有效，虚警数量进入离线审计。
只有已知虚警的航迹帧标为 `excluded/known_false_alarm_only`，不进入严格 IDSW 或
partial lower-bound 分母。`unknown`、标签冲突、重复标签和时间戳不一致仍 fail closed。
D1 lineage mapping 只输出 target 记录；已知虚警作为显式排除项计数，不生成
`truth_id`，unknown 使全部 consumer records 保持空。

`Scalable3DObservationTruthLabel.target()`、`known_false_alarm()` 和 `unknown()` 是
main 可调用的构造 API。2026-07-23 新增 11 项专项测试，完整 D2 回归为
`249 passed, 1 warning in 32.08s`。冻结 `5263e2b` seed 1000 的 v1 producer 制品也完成
重放一致性检查。当前尚未取得 main 写出 v2 虚警处置后的 20-seed 新制品，因此旧报告中
strict IDSW `0/20` 可用的结论保持不变。

## 2026-07-23 身份承诺评估审计

身份承诺 evidence 现在生成 `d2.scalable3d_identity_evaluation.v2`。评估产物保留经
evidence bundle SHA-256 约束的 v2 evidence records，`audit` 分开统计全部记录和
`created/matched` 观测记录的 committed/uncommitted 分母与覆盖率，同时输出承诺原因、
恢复拒绝原因、blocker count、水位线年龄及 overflow 的记录数和航迹数。

loader 会从 `IdentityEvidenceCommitment` 和逐帧 mapping 重算上述字段。持久化聚合值
不一致、水位线年龄为负、未提交 mapping 携带候选或来源绑定时直接拒绝。旧 evaluation
v1 不嵌入 v2 evidence，新增审计项保持 unavailable/`None`。2026-07-23 D2 全量测试为
`286 passed, 1 warning in 29.22s`；该结果是模块合同验证，main/D6 接线和 clean seed
1100 A/B 尚未执行。
