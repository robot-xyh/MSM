# D2 数据关联模块原理与当前实现说明

**状态日期**：2026-07-23

**适用范围**：科研仿真、受治理日志回放、离线评估与跨节点航迹注册基础

**能力口径**：本文只描述当前仓库已经实现并有代码或验证证据支撑的能力。优先级零、优先级一和优先级二（Priority 0 / Priority 1 / Priority 2，P0 / P1 / P2）用于区分工程优先级，不表示算法自动进入主线。

本文中的 D1-D7 是仓库内模块代号。D2 的默认工程主线是全局最近邻（Global Nearest Neighbor，GNN）与匈牙利算法（Hungarian algorithm）的组合；联合概率数据关联（Joint Probabilistic Data Association，JPDA）和多假设跟踪（Multiple Hypothesis Tracking，MHT）仅处于显式选择的研究对照状态。标识符（Identifier，ID）及其连续性是本模块的核心对象。

## 0. 2026-07-15 M5N2 真实运行证据边界

本轮 SimpleFlight 运行完成 baseline 10 seed 和 candidate 10 seed，共 20 个 M5N2
case。在线 D2 仍只接收受治理状态、协方差和时间戳，truth identity/state use 均为 0；
仿真真值只允许在写盘后由独立评估器使用。因此，本批在线身份切换次数和航迹连续性没有
真值分配时是“不可用”，不是数值零。

D2 association main-bus 在 3805 个 control tick 上全部有计时，平均值、第 95 百分位和
最大值分别为 `2.521 ms`、`3.147 ms` 和 `98.942 ms`。这说明 D2 常态计算不是本轮
约 1.07 秒外层控制周期的主要耗时，但单次接近 100 ms 的尾部值仍需继续追踪。第二
primary 的 5 米成功率为 0/20，且最终均为 `collision_stop`；由于碰撞对象没有写盘，
该现象不能归因于 D2，也不能用来调整关联门限或身份规则。

默认 GNN/匈牙利硬关联、中心节点对 `global_track_id` 的唯一所有权以及“末端节点不得
本地重绑规范 ID”的原则均未改变。M5N2 完成后批次已终止；终止前额外完成的单个
`png_ttc_2v2_seed001` 被排除，dropout case 未执行。

## 1. 模块定位、问题与边界

### 1.1 模块定位

D2 是反无人机系统（Counter-Unmanned Aircraft System，C-UAS）多目标流程中的数据关联与身份连续性模块。它接收 D1 已治理的观测或粗航迹，把每帧观测与已有航迹对应起来，维护中心拥有的 `global_track_id`（全局航迹标识符），并输出关联结果、航迹生命周期、质量风险和离线身份指标。

D2 解决的不是单纯的“位置误差是否足够小”，而是以下连续性问题：

- 同一物理目标在交叉、近距并行、短时遮挡或漏检后，是否仍由同一个 `global_track_id` 表示；
- 新观测应更新已有航迹、形成新航迹，还是作为门外候选被拒绝；
- 同一观测或同一真实目标是否被重复解释；
- 多个节点发布的局部航迹是否属于同一规范全局目标；
- 无真值在线路径如何发布可解释风险，而不把风险分数冒充真实身份错误。

### 1.2 工程问题

当前实现直接面对以下工程约束：

1. **输入数量动态变化**：每帧活动航迹数和观测数可能不相等，且会随漏检、虚警、建轨和删轨变化。代价矩阵按实际输入构造，不从 `2v2`、`5v5` 或场景名称推断规模。
2. **时间语义不可混淆**：`measurement_timestamp`（量测时间戳）描述信息对应的物理时刻，`arrival_timestamp`（到达时间戳）描述信息到达处理链路的时刻。D2 保留二者，但当前主跟踪器按已治理的量测时间顺序处理。
3. **不确定性必须随数据流动**：观测和航迹都携带协方差；门控、更新和跨节点匹配不能退化为仅比较欧氏距离。
4. **身份权威必须唯一**：源观测 ID、节点本地航迹 ID、仿真对象（actor）名称和离线真值标签都不能覆盖中心生成的 `global_track_id`。
5. **在线与离线证据必须隔离**：在线关联不能读取仿真真值；依赖真值的身份切换、连续性和统计一致性指标只能在关联结束后的离线评估层计算。
6. **结果必须可审计**：匹配、未匹配、门控拒绝、候选数量、代价矩阵、风险摘要、状态转移和指标可用性都需要显式输出。

### 1.3 科学问题

D2 当前研究围绕三个相互关联但不能混为一谈的问题：

1. **单帧组合优化**：在马氏门控后，如何用一对一全局分配最小化本帧总代价。
2. **多帧身份连续性**：如何通过运动预测、航迹状态机、短时历史和质量风险，减少一次硬判决错误向后续帧传播。
3. **评估可辨识性**：如何在在线路径不接触真值的前提下，用隔离真值计算标识符切换计数（Identifier Switch Count，IDSW）、身份连续性、覆盖连续性和重复解释，并判断候选参数是否真的优于默认配置。

跨节点扩展另有一个独立科学问题：先判断不同节点的局部航迹是否对应同一目标，再决定相关信息是否可融合。身份对应和数值状态融合是两个步骤，不能先融合再用融合结果反证身份对应。

### 1.4 明确边界

D2 当前边界如下：

- 只用于科研仿真、离线回放和接口验证；
- 不包含真实飞控、硬件驱动、真实火控、毁伤评估、自动授权或绕过人工审核的流程；
- `engageable`（可供下游研究使用）只是航迹质量状态，不表示任何处置许可；
- 不启动、重置或编排微软 AirSim 无人系统仿真器；
- 不直接调用 AirSim 软件开发工具包（Software Development Kit，SDK）；
- 不采集图像，不负责目标检测器，也不负责 D5 末端视觉局部跟踪；
- 不生成 D3 的 `AssignmentPlan`（分配计划），不维护其版本，也不判断旧版本是否可执行；
- 不决定 D4 的中心、二级或分布式模式切换，只发布关联风险证据；
- 不实现原始乱序量测（Out-of-Sequence Measurement，OOSM）的回溯、重放或平滑；
- 不把旧二维 `Tracker` 与独立六维 `Scalable3DTracker` 混成同一个默认入口；
- 不把可选库对象适配器表述为端到端多目标跟踪系统。

## 2. 当前能力状态总览

### 2.1 默认工程主线

当前默认主线由以下组件组成：

```text
D1 受治理观测或二维 Detection
  -> 二维常速度预测
  -> 协方差治理
  -> 马氏门控与质量感知门限
  -> GNN / 匈牙利一对一硬关联
  -> 卡尔曼更新、漏检处理与动态建轨
  -> tentative / confirmed / engageable / lost / dropped 状态机
  -> association logs、风险摘要与在线可用指标
  -> 关联结束后的隔离真值评估
```

默认关联器类 `GNNHungarianAssociator`（GNN 与匈牙利关联器）使用 Python 科学计算库 SciPy 的 `linear_sum_assignment`（线性和分配求解函数）。矩阵运算使用 Python 数值计算库 NumPy。默认主线不依赖 AirSim、Stone Soup 或 FilterPy。

需要区分两个默认值层次：

- `GNNHungarianAssociator` 类构造默认值为门限 `9.21`、特征权重 `1.0`、运动权重 `1.0`、质量感知门控开启；
- `build_default_dry_run_tracker()`（默认干运行跟踪器构造函数）显式把特征权重设为 `6.0`；若观测没有特征向量，特征代价仍为零；
- 2026-07-13 固定矩阵中的受治理基线是门限 `9.21`、质量感知门控开启、丢失/删除阈值 `2/5`、运动权重倍数 `1.0`。该标定没有改变默认在线主线。

### 2.2 已实现但不等于默认主线

以下能力已有可执行代码和测试，但不替换默认关联路径：

- JPDA 小规模联合假设枚举、假设归一化和边缘概率输出；
- MHT 有界分支、短历史、漏检/虚警惩罚和分支截断；
- 离线真值合同、在线真值剥离、精确时间对齐和离线身份评分；
- N 次扫描中至少 M 次命中的初始化评估（M-of-N），默认离线口径为 `2-of-3`；
- 密集交叉、连续漏检、虚警和延迟到达的确定性回放与多种子校准工具；
- 固定 54 组 GNN 参数筛选、20 种子确认和同输入轻量 JPDA 对照；
- 跨节点局部航迹到规范航迹的中心注册基础；
- 可选第三方库的对象转换与延时冒烟测试。
- 六维 NED 常速度航迹、3D 马氏门控、KD-tree 稀疏候选图和分量级 Hungarian；
- 六维在线 truth-free 合同、中心 `GT3D-*` 所有权、有界历史和独立离线身份评分。
- D1 六维 source posterior 的完整 6x6 covariance、固定权重 CI 更新、速度创新 NIS 门控
  和有限速度 tie-break cost。
- 默认关闭的结构歧义保持租约、D1 不透明来源令牌适配和关联前来源绑定硬约束。

### 2.3 结构歧义保持候选

D1 在最大匹配允许边图不能给出唯一身份时，可以发布
`d1.structural-ambiguity-evidence.v1` 侧车。D2 复制公开常量和摘要算法，不 import
D1 私有实现。成员令牌按
`SHA-256(canonical JSON [publisher_node_id,publisher_epoch,d1_local_track_id])`
生成，前缀固定为 `d1-track-sha256:`；来源键固定为
`publisher_node_id::publisher_epoch::opaque_member_track_token`。该来源键只用于
binding 和 ambiguity membership，D2 canonical ID 仍由 `GT3D-*` 序列分配。

侧车中的观测只携带 `d1-observation-sha256:<digest>`、NED 位置和协方差。D2 不要求
原始 observation ID 或 source namespace，也不尝试反解谱系。claim ledger 将证据状态
显式分为 `unseen`、`reserved_ambiguous` 和 `consumed`。同一不可逆证据不能被不兼容
分量重复预留。

开启租约后，D2 把歧义成员经已有 source binding 映射到 canonical track。租约期间这些
航迹只执行常速度预测：

```text
D1 完整歧义分量
  -> schema / bounded age / covariance / generation / epoch 校验
  -> opaque member source_key 查询已有 D2 binding
  -> observation evidence reservation
  -> 已绑定航迹 prediction-only hold
  -> 新原始 evidence 延长 soft deadline
  -> soft/hard deadline 到期释放
```

保持期间不做量测更新，不增加 hit 或 miss，不生成新航迹，不改绑来源，不提高身份置信度。
协方差只按预测传播，不能因重复 posterior 收缩。未绑定成员和分量观测禁止 birth。重复
evidence、同代或旧代 generation、坏 schema、缺时间戳/协方差、
`posterior_update_applied=true` 和已退休 publisher epoch 均拒绝，且不刷新截止时间。

侧车时间不按等时刻匹配。D1 的 `measurement_timestamp` 和
`state_valid_timestamp` 保持相等并代表原量测物理时刻；D2 tracker epoch 代表延迟补偿
后的当前消费时刻。D2 使用

\[
\Delta t_{\mathrm{age}}
=t_{\mathrm{D2,consume}}-t_{\mathrm{D1,state-valid}}
\]

做有界准入。容差外的负值表示未来证据，超过 `max_component_age_seconds` 表示过旧
证据，两者均拒绝且不建立或刷新租约。年龄窗内的延迟证据可接受，soft/hard deadline
仍从 D2 首次消费时刻和后续新原始证据消费时刻起算。默认年龄上限 `1.0 s` 用于覆盖
当前 main 常见 `0.5 s` D1 scan lateness 与传输余量，后续必须按实测时延标定。
原 measurement/arrival/state-valid/published 时刻不被改写，并与 D2 消费时刻、分量
年龄和时间判定一起写入诊断。

默认配置为关闭。`detections3d_from_d1_global_tracks()` 也只有在显式设置
`use_opaque_d1_source_tokens=True` 时生成 D1 三段式来源键。缺 publisher epoch 时使用
兼容默认 `d1-default-epoch-v1` 并记录 defaulted；发布者重启必须由集成层显式轮换
epoch，D2 无法从默认值自行判断重启。首版消歧方式是到期释放，没有连续双向唯一自动
解除、component-level JPDA 或 bounded MHT。

来源绑定的正常路径同时改为关联前硬约束。已绑定来源只允许连接原 canonical track；
若原边不满足几何门控，该观测被隔离，原航迹按预测继续，禁止错误航迹先更新后报冲突和
同源 shadow birth。

#### 身份承诺状态

活动租约集合只说明“当前是否还在 hold”，不能说明一条航迹在此前歧义后是否重新获得了
可用的身份观测。D2 因此新增独立的身份证据承诺状态：

```text
committed
  -> identity_uncommitted_ambiguity_hold
  -> identity_uncommitted_after_hold
  -> committed
```

`identity_uncommitted_ambiguity_hold` 表示结构歧义租约仍有效，航迹只预测。
`identity_uncommitted_after_hold` 表示软截止、硬上限或 publisher epoch 轮换已经释放
租约，但 D2 尚未实际接受新的原始观测。释放租约只允许恢复普通关联计算，不自动恢复身份
承诺。该状态跨帧保存，不通过当前 `hold_track_ids` 临时推导。

活动 hold 首次影响航迹时，D2 把该分量的 observation evidence key 保存到航迹私有阻断
集合，并把恢复水位线更新为相关分量 measurement timestamp 的最大值。claim ledger 在
租约释放时删除 reservation，阻断集合不随之删除。因此同一个旧 key 再次入场时仍能被
识别，不能依靠 ledger 生命周期绕过 hold。

恢复 `committed` 同时满足五项条件：候选 key 不在阻断集合；source measurement
timestamp 严格晚于恢复水位线和容差；claim 为本扫描首次接纳的 original evidence，
状态仍为 `unseen` 且 replay count 为 0；活动 lease 为 0；上游 disposition 为
`target_candidate`。判断在航迹量测更新之前完成。失败观测不增加 hit、不更新状态、不
形成 `detection_to_track` 或 observation claim binding。

阻断集合由 `IdentityCommitmentRecoveryConfig` 限制容量。默认每航迹 2048 个、全局
250000 个；溢出后该航迹保持 fail-closed，不能因丢弃了部分 key 而恢复。真正的新证据
只清理未溢出的集合；溢出集合在永久 dropped 时释放。`target_candidate`、`known_false_alarm`
和 `unknown` 都是 truth-free 上游处置。在线 D2 不读取离线 truth sidecar；生产者也不得
用仿真真值反向生成这些处置。

`d2.identity-evidence-commitment.v2` 为每条航迹输出关联状态、承诺状态和原因、D2 状态
时刻、量测/到达双时间戳、commitment/component/evidence generation、发布节点与
epoch、活动租约键、软硬截止和释放信息。未提交状态不输出 source observation evidence
key，并只公开 blocker count、恢复水位线和 overflow，不公开阻断 key，避免 main 或离线
评估器把歧义候选绑定到 `global_track_id`。

离线 `d2.scalable3d_identity_evidence.v2` 显式携带上述承诺 DTO。未提交帧不形成
`global_track_id` 到候选真值的映射，但仍进入真值存在帧的覆盖分母。评估器比较空窗前后
两个 committed 锚点，因此换成新 `global_track_id` 时仍计一次身份切换。普通 v1 谱系
合同、缺失谱系、未来/超窗观测和冲突标签的 fail-closed 行为不变。

2026-07-23 D2 模块回归为 `281 passed, 1 warning in 29.46s`。测试覆盖 37 目标动态规模以及
hold、到期、reservation 释放后的旧 key 重入、同水位线新 key、更晚新 key、容量溢出、
未来来源时刻、重复、超龄、已知假警、未知处置和正常恢复。本结果尚未包含 main 持久化、D6 汇总或
clean seed 1100 重测，结构歧义候选仍默认关闭。

### 2.4 部分实现

1. **JPDA**：能输出边缘概率和非冲突匹配，但 `Tracker` 仍对选出的单个匹配做普通卡尔曼更新；没有完整概率混合状态更新、协方差混合、航迹合并抑制和生产级分簇。
2. **MHT**：能保留有限分支和有限历史，但没有 N 扫描剪枝、长期假设树、分簇、确认逻辑和中心算力调度。
3. **双路径维度**：D1 的六维北-东-地状态仍可投影到旧二维 `GlobalTrack`；显式选择的
   `GlobalTrack3D` 已维护六维状态，main-owned scalable point-mass bus 已有只读运行
   诊断，但修复后跨模块 schema、多 seed 和端到端验收仍未冻结。
4. **跨节点注册**：中心规范注册、相关性决策和融合请求已实现；数值状态融合结果没有在 D2 内计算或回写。
5. **质量感知门控**：已实现轻量、带上下界的门限调整；它不是经过完整多场景标定的通用自适应门控框架。
6. **结构歧义保持**：有界 prediction-only 租约和到期释放已实现；自动消歧、JPDA/MHT
   状态融合和跨进程 epoch 协商尚未实现。clean 200v200 单 seed 系统 A/B 已执行，
   但候选因离线 lineage 指标 unavailable、映射和分配退化被拒绝；修复后的同 seed
   复核与多 seed 验收尚未完成。

### 2.5 明确未实现

- 完整 JPDA 滤波器和完整 MHT；
- 根据在线风险自动切换 GNN、JPDA 或 MHT，以及该切换所需的迟滞；
- 六维路径修复后的跨模块版本化输出、真实多 seed 标定和极端密度预算；基础 point-mass
  episode-bus 编排已有 main 只读证据，不再列为完全未接入。
- 扩展卡尔曼滤波（Extended Kalman Filter，EKF）、无迹卡尔曼滤波（Unscented Kalman Filter，UKF）和交互多模型（Interacting Multiple Model，IMM）预测；
- Stone Soup 多目标跟踪研究框架的端到端 JPDA/MHT 跟踪器；
- FilterPy 滤波算法库的端到端数据关联跟踪器；
- 原始 OOSM 回溯和平滑；
- 跨节点高歧义多帧 JPDA/MHT；
- D2 owner/epoch（身份所有者/纪元）故障切换与完全分布式临时 ID 合并；
- D1 拥有的精确相关数值融合或协方差交集（Covariance Intersection，CI）后验计算；
- 平均归一化估计误差平方（Average Normalized Estimation Error Squared，ANEES）和通信字节统计闭环。

## 3. 上游输入与核心数据结构

### 3.1 D1 受治理输入

D2 有三类 D1 输入适配路径。

第一类是 D1 `GlobalTrack`（D1 全局航迹对象）投影：

- D1 状态顺序为 `[north, east, down, vn, ve, vd]`，即北、东、地位置和对应速度；
- D1 协方差为 `6 x 6`；
- D2 取状态前两维作为二维北-东位置，取协方差左上 `2 x 2` 子矩阵；
- `measurement_timestamp`、`arrival_timestamp`、来源 `global_track_id` 和 metadata（元数据）被保留；
- 该路径是旧兼容入口的二维投影，不改变其四维状态。

第二类是 D1 受治理回放清单：

- 清单版本为 `d1.governed_replay_manifest.v1`（D1 受治理回放清单第一版）；
- 观测版本为 `d1.sensor_observation.v1`（D1 传感器观测第一版）；
- 当前只接受工作坐标系为 NED 的雷达记录；
- 雷达球坐标 `[rho, azimuth, elevation]`（距离、方位角、俯仰角）通过雅可比矩阵投影到水平北-东位置和协方差；
- 一维声学方位和光电（Electro-Optical，EO）像素观测因量测空间不同而显式跳过，不会错误混入北-东平面；
- 输出按 `(measurement_timestamp, frame_index)`（量测时间与帧号）聚合，并生成匿名在线观测 ID；
- `arrival_timestamp` 取本帧已接受观测的最大到达时间，仍保留每条观测自己的到达时间元数据。

第三类是显式六维稀疏入口：`Detection3D` 使用 NED 三维位置、3x3 covariance、双
时间戳和可选速度提示；`GlobalTrack3D` 使用
`[pN,pE,pD,vN,vE,vD]` 与 6x6 covariance。D1 对象中的上游 `global_track_id` 不被
复制为规范身份，`GT3D-*` 只由 D2 创建。adapter 以 D1 state-valid timestamp 对齐
关联 epoch，并把原始 sensor measurement/arrival timestamp 保留在 source metadata；
原始雷达球坐标和视觉像素仍必须先经 D1。

雷达水平投影为：

\[
\begin{aligned}
n &= n_s + \rho\cos(e)\cos(a),\\
e_N &= e_s + \rho\cos(e)\sin(a),\\
R_{ne} &= J R_{rae} J^T.
\end{aligned}
\]

其中，`rho` 是距离，`a` 是方位角，`e` 是俯仰角，`(n_s,e_s)` 是传感器水平 NED 位置，`R_rae` 是雷达球坐标量测协方差，`J` 是从球坐标到北-东平面的雅可比矩阵，`R_ne` 是投影后的二维量测协方差。

### 3.2 `Detection`：单帧二维观测

`Detection`（观测）是默认关联器的核心输入：

| 字段 | 中文含义 | 当前约束 |
| --- | --- | --- |
| `detection_id` | 单帧观测标识符 | 在线治理后使用匿名 ID，不是全局身份权威 |
| `timestamp` | 该观测的量测时刻 | 转为有限浮点数 |
| `position` | 二维位置 `[x,y]` 或 `[north,east]` | 固定两维 |
| `covariance` | 二维量测协方差 | 固定 `2 x 2`，执行一致性治理 |
| `confidence` | 观测置信度 | 当前存储并透传，不直接进入默认代价公式 |
| `feature` | 可选特征向量 | 维度与航迹特征相同时参与平方差代价 |
| `metadata` | 来源、时间、投影和诊断元数据 | 在线路径递归移除真值身份字段 |
| `truth_id` | 离线真实目标标识 | 在线受治理路径必须为空，只供离线评估 |

### 3.3 `GlobalTrack`：中心航迹状态

默认 D2 `GlobalTrack` 的状态为：

\[
\mathbf{x}=[p_x,p_y,v_x,v_y]^T,
\]

协方差为 `4 x 4`。主要字段包括：

| 字段 | 中文含义 |
| --- | --- |
| `global_track_id` | 中心生成的规范全局航迹 ID |
| `state` | 二维位置与二维速度状态 |
| `covariance` | 状态协方差 |
| `timestamp` | 当前状态有效时刻 |
| `lifecycle_state` | 航迹生命周期状态 |
| `hits` / `consecutive_hits` | 累计命中数 / 连续命中数 |
| `misses` | 连续漏检数 |
| `age` | 预测年龄计数 |
| `last_detection_id` | 最近一次更新使用的观测 ID |
| `identity_confidence` | 基于连续命中的轻量身份置信度 |
| `track_quality` | 当前航迹质量，范围 `[0,1]` |
| `association_risk` | 当前关联风险，范围 `[0,1]` |
| `quality_metadata` | 质量和风险组成的解释字段 |
| `history` | 创建、预测、更新和漏检历史 |
| `transition_log` | 状态转移及原因 |

新航迹 ID 以 `T001`、`T002` 等顺序由中心 `Tracker`（跟踪器）创建。源观测 ID 和离线真值 ID 不参与该编号。

### 3.4 每帧关联结构

`AssociationResult`（关联结果）包含：

- `matched_pairs`（已匹配对）：`track_id`（航迹 ID）、`detection_id`（观测 ID）、`cost`（代价）和 `probability`（概率）；
- `unmatched_track_ids`（未匹配航迹 ID）；
- `unmatched_detection_ids`（未匹配观测 ID）；
- `ambiguity_score`（歧义分数）；
- `associator_type`（关联器类型）；
- `rejected_pairs`（拒绝候选对）及 `mahalanobis_gate`（马氏门控拒绝）或 `assignment_above_gate`（分配后仍超门限）原因；
- `cost_matrix`（总代价矩阵）和 `distance_matrix`（马氏平方距离矩阵）；
- `metadata`（求解器、候选数、门限、协方差、运动一致性和质量风险诊断）；
- 可选 `risk_summary`（风险摘要）。

`AssociationLogEntry`（关联日志条目）在上述信息之外记录 `runtime_seconds`（本帧运行秒数），供回放和 D6 评估。

### 3.5 离线真值结构

离线标签使用 `d2-offline-truth-label/v1`（D2 离线真值标签第一版），每条至少包含：

- `episode_id`（回合 ID）；
- `frame_index`（帧号）；
- `timestamp`（真值时刻）；
- `truth_id`（真实目标 ID）；
- `position`（二维离线真值位置）；
- 可选 `match_annotation`（离线匹配审计注释）。

文件采用 JavaScript 对象表示法（JavaScript Object Notation，JSON）的逐行格式（JSON Lines，JSONL）。读写器拒绝重复 `(episode_id, frame_index, truth_id)`（回合、帧、真值 ID）键和非法坐标。D1 三维真值旁路文件只把北、东位置送入 D2 离线评估；Down（向下）分量仅保留为审计注释。

### 3.6 跨节点局部航迹结构

跨节点路径与默认 `Detection -> GlobalTrack` 路径分离。`SourceTrackSummary`（来源航迹摘要）包含：

- `(source_node_id, local_track_id, local_epoch)`（来源节点、本地航迹 ID、本地纪元）命名空间；
- 独立的 `measurement_timestamp` 和 `arrival_timestamp`；
- 六维 NED 状态 `[north,east,down,vn,ve,vd]`；
- `6 x 6` NED 协方差；
- `quality`（质量）、`lineage`（信息谱系）和 `payload_id`（载荷消息 ID）；
- `correlation_status`（相关性状态）；
- `candidate_canonical_ids`（候选规范 ID）和 `current_canonical_id`（当前规范 ID）提示。

候选或当前规范 ID 只是非权威提示。只有中心 `CrossNodeTrackRegistry`（跨节点航迹注册表）能创建和更新规范绑定。

## 4. 数学模型与默认算法

### 4.1 二维常速度模型

默认模型是常速度模型（Constant Velocity，CV）。设相邻帧量测时间差为 `dt`，状态转移矩阵为：

\[
F(dt)=
\begin{bmatrix}
1&0&dt&0\\
0&1&0&dt\\
0&0&1&0\\
0&0&0&1
\end{bmatrix}.
\]

预测方程为：

\[
\hat{\mathbf{x}}^-_k=F\hat{\mathbf{x}}^+_{k-1},
\qquad
P^-_k=F P^+_{k-1} F^T+Q(dt).
\]

其中，`x^-` 和 `P^-` 是关联前预测状态与协方差，`x^+` 和 `P^+` 是上一帧更新后状态与协方差。过程噪声强度默认 `q=0.20`，实现中的离散过程噪声为：

\[
Q=q
\begin{bmatrix}
dt^4/4&0&dt^3/2&0\\
0&dt^4/4&0&dt^3/2\\
dt^3/2&0&dt^2&0\\
0&dt^3/2&0&dt^2
\end{bmatrix}.
\]

`Tracker` 使用 `dt=max(timestamp-track.timestamp,0)`。因此负时间差不会反向传播；这只是保护，不是 OOSM 回溯实现。

### 4.2 观测模型与创新

二维位置观测矩阵为：

\[
H=
\begin{bmatrix}
1&0&0&0\\
0&1&0&0
\end{bmatrix}.
\]

对航迹 `i` 与观测 `j`：

\[
\hat{\mathbf{z}}_i=H\hat{\mathbf{x}}^-_i,
\quad
\mathbf{r}_{ij}=\mathbf{z}_j-\hat{\mathbf{z}}_i,
\quad
S_{ij}=H P^-_i H^T+R_j.
\]

其中，`r_ij` 是创新，`S_ij` 是创新协方差，`R_j` 是观测协方差。

### 4.3 马氏门控

门控使用马氏平方距离：

\[
d^2_{ij}=\mathbf{r}_{ij}^T S_{ij}^{-1}\mathbf{r}_{ij}.
\]

矩阵不可逆时实现使用广义逆。类默认基础门限 `g_0=9.21`，接近二维卡方分布的 99% 分位。若 `d^2_ij` 超过该航迹实际门限，该候选被置为大代价 `10^9` 并记录拒绝原因。

### 4.4 质量感知门限

质量感知门控默认开启。每条航迹先计算质量：

\[
q_t=0.28q_P+0.18q_H+0.12q_A+0.18q_M+0.16q_L+0.08q_I,
\]

其中：

- `q_P` 是由位置协方差迹得到的不确定性分数；
- `q_H` 是累计命中分数；
- `q_A` 是航迹年龄分数；
- `q_M` 是漏检惩罚后的分数；
- `q_L` 是生命周期分数；
- `q_I` 是身份置信度。

实际门限按以下结构调整：

\[
g_i=\operatorname{clip}
\left(
g_0(1+r_q+r_P-t_d-t_a),g_{min},g_{max}
\right).
\]

`r_q` 在质量低于 `0.65` 时保守放宽，`r_P` 在位置协方差迹较大时放宽，`t_d` 在局部密度高时收紧，`t_a` 在上一帧关联风险高且目标密集时收紧。默认上下界是 `4.0` 和 `16.0`。该规则的目的不是追求门越大越好，而是在漏配与错误吸附之间做可解释折中。

### 4.5 代价函数

门内候选总代价为：

\[
C_{ij}=d^2_{ij}+w_f C^{feature}_{ij}+w_m C^{motion}_{ij}.
\]

特征维度一致时：

\[
C^{feature}_{ij}=\|\mathbf{f}_i-\mathbf{f}_j\|^2.
\]

没有特征或维度不一致时，该项为零。运动一致性代价由三部分组成：

\[
C^{motion}_{ij}=\min
\left(3,
C_{dir}+0.75C_{hist}+0.50C_{acc}
\right).
\]

其中，`C_dir` 比较当前速度方向与候选残差方向，`C_hist` 比较最近量测历史速度与候选速度方向，`C_acc` 惩罚相对当前速度异常大的候选加速度。方向代价采用 `(1-cos(theta))/2`，所以同向接近零，反向接近一。它是轻量运动约束，不是新的运动滤波模型。

### 4.6 匈牙利一对一分配

设当前有 `N_t` 条活动航迹和 `N_z` 个观测，求解：

\[
\min_{a_{ij}}\sum_{i=1}^{N_t}\sum_{j=1}^{N_z}a_{ij}C_{ij},
\]

满足：

\[
a_{ij}\in\{0,1\},\quad
\sum_j a_{ij}\leq 1,\quad
\sum_i a_{ij}\leq 1.
\]

即每条航迹最多匹配一个观测，每个观测最多匹配一条航迹。求解后仍检查大代价和实际门限，防止门外项因矩阵形状进入结果。匈牙利求解复杂度约为 `O(max(N_t,N_z)^3)`，因此算法不写死规模，但计算量仍随输入增长。

### 4.7 歧义分数

对每条航迹，将门内代价从小到大排列。若最优与次优代价差为 `Delta_i`，则行歧义分数为：

\[
A_i=\exp(-0.5\Delta_i).
\]

总体 `ambiguity_score`（歧义分数）是所有行分数平均值。只有一个合法候选时该行记零。代价越接近，分数越接近一，表示硬关联越不确定。

### 4.8 卡尔曼更新

匹配后使用线性卡尔曼更新：

\[
K=P^- H^T(H P^- H^T+R)^{-1},
\qquad
\hat{\mathbf{x}}^+=\hat{\mathbf{x}}^-+K\mathbf{r}.
\]

协方差使用 Joseph 形式：

\[
P^+=(I - K H)P^-(I - K H)^T+K R K^T.
\]

Joseph 形式比简化的 `(I - K H)P` 更能保持数值对称性和半正定性。更新后累计命中、清零漏检、更新最近观测 ID，并以默认平滑系数 `0.85` 更新可选特征。

### 4.9 动态建轨

未匹配观测默认生成新航迹：

\[
\mathbf{x}_0=[z_x,z_y,0,0]^T,
\]

初始位置方差为 `4.0`，初始速度方差为 `25.0`。新航迹从 `tentative`（暂定）开始，ID 由中心顺序生成。未匹配观测数没有固定上限，也不会按目标场景名补齐或截断。

## 5. 生命周期、迟滞与身份安全

### 5.1 在线状态机

当前状态集合固定为：

```text
tentative -> confirmed -> engageable
     |           |             |
     +-----------+------miss--> lost --more miss--> dropped
                              |
                              +--hit--> confirmed 或 engageable
```

代码中没有 `engaged`（已执行）状态。默认转移规则为：

| 条件 | 转移 | 默认阈值 |
| --- | --- | ---: |
| 连续命中达到确认数 | `tentative -> confirmed` | `confirmation_hits=2` |
| 累计命中足够且协方差迹较小 | `confirmed -> engageable` | `hits>=4` 且总协方差迹 `<=20` |
| 连续漏检达到丢失阈值 | 非删除状态 `-> lost` | `lost_miss_threshold=2` |
| 连续漏检达到删除阈值 | 非删除状态 `-> dropped` | `drop_miss_threshold=5` |
| `lost` 后重新命中 | `lost -> confirmed` | 普通质量 |
| `lost` 后高质量重获 | `lost -> engageable` | 命中和协方差条件同时满足 |

这种“命中确认、漏检丢失、更多漏检删除、重获后再确认”的不同阈值构成生命周期迟滞。它减少单帧漏检导致的立即删轨，也避免一次重获直接无条件恢复高质量状态。

每次转移写入 `TrackTransition`（航迹状态转移），包括时间、航迹 ID、前后状态和原因。下游不能通过修改状态来重命名 `global_track_id`。

### 5.2 在线状态机与离线 M-of-N 的区别

默认在线状态机按连续命中数确认航迹。`InitializationGovernanceProfile`（初始化治理配置）实现的默认 `2-of-3` 只用于离线评估：从某真值首次出现的帧开始，在三个扫描中检查是否至少两帧被分配。它不会把真值反馈给在线 `Tracker`，也不会改变在线确认逻辑。

因此，“M-of-N 接口已实现”表示评估与标定合同已实现，不表示在线跟踪器已经改成通用滑窗 M-of-N 建轨器。

### 5.3 协方差治理

观测和航迹协方差都必须满足：

1. 形状正确；
2. 所有元素有限；
3. 在数值容差内对称；
4. 在数值容差内为半正定（Positive Semidefinite，PSD）。

明显非对称、非有限或明显负特征值输入直接拒绝。仅对浮点误差尺度内的缺陷执行：

- `0.5(P+P^T)` 对称化；
- 将极小或轻微负特征值抬升到机器精度相关下限。

`covariance_consistency`（协方差一致性诊断）表示最新一次检查；`covariance_regularized`（协方差曾正则化）和 `regularization_ever_applied`（历史上曾正则化）保留历史事实；`last_regularization`（最近一次正则化）保留具体证据。输入合法性不等于滤波统计一致性，后者还需归一化创新平方（Normalized Innovation Squared，NIS）和归一化估计误差平方（Normalized Estimation Error Squared，NEES）评估。

### 5.4 中心 ID 权威

身份安全规则如下：

- `global_track_id` 只由 D2 中心 `Tracker` 或中心跨节点注册表创建和维护；
- `detection_id`（观测 ID）只在单帧关联和日志中使用；
- D1 来源 `global_track_id` 在投影适配中作为元数据保留，不自动成为 D2 规范 ID；
- 仿真 actor 名称、源 detection ID、本地航迹 ID、候选规范 ID 和离线 `truth_id` 都没有重命名权限；
- D5 和 D7 可以消费或引用 `global_track_id`，不能改写、重绑或本地覆盖；
- D5 不一致只作为弱风险证据，不作为真值重命名命令；
- 目标数或资源数变化不能触发固定长度 ID 补齐；
- 同一规范目标绑定多个合法来源航迹，不表示出现多个目标。

### 5.5 在线真值隔离

受治理回放默认执行以下隔离：

1. 源观测 ID 改为按帧匿名 ID；
2. 在线 `Detection.truth_id`（观测真值 ID）为空；
3. actor、truth、ground-truth 等嵌套元数据递归移除；
4. 在线 `GlobalTrack.truth_id`（航迹真值 ID）为空；
5. 在线关联日志不携带真值标签、真值目标数或 NEES；
6. 关联全部结束后，独立 evaluator（评估器）才读取离线标签。

D1 AirSim 真值旁路文件只允许在冻结的 `1e-9` 秒容差内做精确时间匹配。找不到对应受治理帧的合法样本记为 `partial/unmatched`（部分可用/未匹配），不采用最近邻补配。同一时间映射到多个帧且无法唯一消歧时直接拒绝，防止错误标签制造虚假的 IDSW 改善。

## 6. 风险、质量和指标

### 6.1 航迹关联风险

每条航迹的 `association_risk` 由以下可解释分量相加后截断到 `[0,1]`：

- 低航迹质量风险，最高主要权重 `0.55`；
- 多候选风险，超过一个候选后逐步增加，最高 `0.30`；
- 运动不一致风险，最高 `0.25`；
- 漏检风险，最高 `0.35`；
- 本帧未匹配风险 `0.18`；
- `lost` 状态风险 `0.28`，`tentative` 状态风险 `0.08`；
- 新建航迹风险 `0.05`。

这些权重是当前轻量风险模型，不是概率意义上的身份错误后验。

### 6.2 滑窗风险摘要

`AssociationRiskSummaryWindowGenerator`（关联风险滑窗生成器）默认窗口为五帧，汇总：

- 歧义分数；
- 候选重叠率；
- 最优与次优代价间隔风险；
- IDSW 窗口增量；
- 重复分配窗口增量；
- 可用时的连续性风险；
- D5 不一致次数；
- 航迹质量和最大关联风险；
- 来源节点和链路类型。

不可用的连续性不参与 `duplicate_track_risk`（重复航迹风险）或硬风险计算。旧回放缺少可用性字段时也按不可用处理，不能从兼容值 `0.0` 推断连续性崩溃。

### 6.3 软风险和硬风险

默认 `RiskThresholds`（风险门限配置）把证据分为：

| 类型 | 当前证据 | 默认阈值 |
| --- | --- | ---: |
| 软风险 | 关联歧义 | `>=0.45` |
| 软风险 | 候选重叠率 | `>=0.30` |
| 软风险 | 代价间隔风险 | `>=0.45` |
| 软风险 | D5 不一致 | `>=1` |
| 硬风险 | IDSW 窗口增量 | `>=1` |
| 硬风险 | 重复分配窗口增量 | `>=1` |
| 硬风险 | 重复航迹风险 | `>=0.65` |
| 硬风险 | 可用的身份连续性 | `<0.75` |

软风险表示硬关联不确定，适合继续观察、提高 D3 迟滞或请求额外证据；硬风险表示身份连续性或重复解释已经受损。D2 只分类和发布证据，不直接要求系统重规划或降级。

### 6.4 身份与几何指标

离线评估对每个真实目标 `u` 统计其存在帧数 `T_u`、被任意航迹覆盖帧数 `C_u` 和由同一代表航迹稳定覆盖帧数 `S_u`：

\[
\text{coverage continuity}
=\frac{1}{|U|}\sum_{u\in U}\frac{C_u}{T_u},
\]

\[
\text{identity continuity}
=\frac{1}{|U|}\sum_{u\in U}\frac{S_u}{T_u}.
\]

当前 `track_continuity`（航迹连续性）是 `identity_continuity`（身份连续性）的兼容别名。若同一真实目标本帧代表航迹与上一已分配帧不同，`id_switch_count`（ID 切换计数）增加一。

`duplicate_assignment_count`（重复分配计数）显式统计：

- 同一帧同一观测被重复使用；
- 同一帧同一航迹被重复使用；
- 同一真实目标被多条航迹同时覆盖。

均方根误差（Root Mean Square Error，RMSE）为：

\[
\mathrm{RMSE}=\sqrt{\frac{1}{K}\sum_{k=1}^{K}\|\hat{\mathbf{p}}_k-\mathbf{p}^{truth}_k\|^2}.
\]

RMSE 只反映几何误差，不能替代 IDSW 或身份连续性。混淆矩阵记录每个真实目标被各全局航迹解释的次数，用于定位身份分裂和交换。

### 6.5 NIS 与 NEES

NIS 就是匹配前的马氏平方距离：

\[
\mathrm{NIS}=\mathbf{r}^T S^{-1}\mathbf{r}.
\]

它只依赖在线创新和协方差，因此无真值时仍可计算。当前二维量测按自由度二的 95% 卡方区间统计样本数、均值、中位数和区间覆盖率。

NEES 为：

\[
\mathrm{NEES}=(\hat{\mathbf{x}}-\mathbf{x}^{truth})^T P^{-1}
(\hat{\mathbf{x}}-\mathbf{x}^{truth}).
\]

它要求独立四维离线真值状态，只在离线评估层计算，并按自由度四的 95% 卡方区间统计。缺少真值状态时 `available=false`（不可用），不会填成零。

## 7. 可选和离线算法

### 7.1 当前轻量 JPDA

JPDA 对每条航迹保留最多四个门内候选，最多枚举 `4096` 个联合假设。对假设 `h`，当前对数似然为：

\[
\log L(h)=
\sum_{(i,j)\in h}
\left[\log P_D-\frac{1}{2}C_{ij}\right]
+n_{miss}\log(1-P_D)
+n_{fa}\log\lambda_c.
\]

其中，默认探测概率 `P_D=0.90`，杂波密度 `lambda_c=10^{-3}`，`n_miss` 是未匹配航迹数，`n_fa` 是未匹配观测数。归一化所有假设后，候选边缘概率为包含该匹配的假设概率之和。当前只选择边缘概率不低于 `0.35` 的非冲突对，再交给普通 `Tracker` 更新。

因此它是“联合假设与边缘概率关联器”，不是“完整 JPDA 滤波器”。2026-07-13 同输入真实回放中轻量 JPDA 结果退化，没有晋级。

### 7.2 当前有界 MHT

MHT 每帧枚举有限分配并扩展历史分支。分支累计分数为：

\[
J_{new}=J_{old}+\sum C_{ij}
+6.0\,n_{miss}+4.0\,n_{fa}.
\]

默认每条航迹最多三个候选，每帧最多生成 `512` 个分配，保留最优 `16` 个分支和最近五帧历史。当前帧使用最优分支的匹配结果。该实现用于接口和复杂度研究，不是完整 MHT。

### 7.3 第三方对象适配器

P2 可选基准在同一冻结回放摘要下输出五类结果：默认 GNN、模块内 JPDA、模块内 MHT、Stone Soup 和 FilterPy。

- Stone Soup 多目标跟踪研究框架当前仅把 D2 `Detection` 转换成其 Detection 对象并测量对象转换路径；
- FilterPy 滤波算法库当前仅构造二维常速度卡尔曼对象并执行对象级预测/更新；
- 两条外部库路径都没有跨帧端到端数据关联和航迹生命周期，因此 IDSW 和连续性必须标记不可用；
- 可选依赖缺失时输出 `dependency_available=false`（依赖不可用）、`executed=false`（未执行）和明确原因，不静默回退；
- 隔离环境曾验证 Stone Soup 1.9.1 和 FilterPy 1.4.5，但二者不进入默认依赖。

## 8. 跨节点规范航迹注册

### 8.1 公共时刻传播

跨节点来源航迹先按量测时间传播到公共 `fusion_timestamp`（融合时刻）。六维常速度状态转移为：

\[
F_6(dt)=
\begin{bmatrix}
I_3&dtI_3\\
0&I_3
\end{bmatrix},
\]

并加入三维白噪声加速度过程协方差。融合时刻不能早于量测时刻或消息到达时刻，注册表融合时间必须单调。

### 8.2 航迹到航迹门控

来源航迹与规范航迹的状态残差为：

\[
\mathbf{e}=\mathbf{x}_{source}-\mathbf{x}_{canonical}.
\]

若已知交叉协方差 `P_sc`：

\[
P_\Delta=P_c+P_s-P_{sc}-P_{sc}^T.
\]

若相关性未知，当前门控使用保守膨胀：

\[
P_\Delta=2(P_c+P_s).
\]

随后计算：

\[
d^2=\mathbf{e}^TP_\Delta^{\dagger}\mathbf{e},
\]

其中上标 `dagger` 表示广义逆。默认六维门限为 `16.812`。已有权威绑定匹配同一规范 ID 时，分配代价减去最多 `4.0` 的连续性偏置，但不会把门外候选拉回门内。

### 8.3 按来源分组的一对一约束

注册表按 `source_node_id`（来源节点 ID）分组，对每个来源分别执行匈牙利匹配。这样同一来源内部保持一对一，同时允许不同观察节点各有一条来源航迹绑定同一个规范 ID。合法多源观察不会增加目标基数。

未找到门内规范航迹时创建 `GT-000001` 等新规范 ID。注册表拒绝：

- 同批次重复来源键；
- 重复 `payload_id`；
- 重复信息谱系；
- 明确声明的重复信息；
- 同一来源键量测时间不递增的陈旧或重放消息。

### 8.4 相关性决策与职责边界

注册表只输出融合指令：

| 条件 | D2 指令 | 含义 |
| --- | --- | --- |
| 单一来源 | `NO_FUSION_SINGLE_SOURCE` | 不需要融合 |
| 已知交叉协方差 | `REQUEST_EXACT_CORRELATED_FUSION` | 请求 D1 做精确相关数值融合 |
| 相关性未知 | `REQUEST_COVARIANCE_INTERSECTION` | 请求 D1 做保守 CI 数值融合 |
| 重复信息 | `REJECT_DUPLICATE_INFORMATION` | 拒绝重复使用 |

D2 已实现“对应关系、相关性分类、规范绑定和请求”，没有实现数值 CI。在线跨节点指标只统计规范重绑、重复消息拒绝和传输/排队/融合延迟；真值相关的规范重复、跨节点 IDSW、关联精确率和召回率由独立离线评估器计算。

## 9. 与其他模块和主运行时的接口

### 9.1 D1 到 D2

D1 负责原始或近原始多传感器观测治理、时间与坐标处理、观测级融合和协方差。D2 消费：

- 量测时间与到达时间；
- NED 位置或可投影观测；
- 协方差；
- 置信度、来源和谱系；
- 可选特征。

D2 不把声学方位或 EO 像素直接当作北-东位置。跨节点路径请求 D1 计算精确相关融合或 CI 后验，D2 不复制该数值能力。

### 9.2 D2 到 D3

D3 使用 `global_track_id`、状态、协方差、生命周期、`track_quality`（航迹质量）和 `association_risk`（关联风险）构造资源-目标分配输入。D3 可对暂定、丢失或高风险航迹提高代价或延迟分配，但不得重命名目标。

D2 不生成 `AssignmentPlan`，不增加计划版本，不接受旧计划，也不判断 stale plan（过时计划）。这些属于 D3。

### 9.3 D2 到 D4

D4 消费 D2 的软/硬风险、IDSW 增量、重复解释、可用连续性、来源节点和链路信息，再与 D1、D3、D5 和通信状态共同仲裁。D2 不直接返回 `request_center_replan`（请求中心重规划）或任何模式切换命令。

### 9.4 D2 与 D5

D5 使用 `global_track_id` 做中心航迹与终端视觉候选的关联。D5 可回传置信度、不一致和候选集合；D2 可把这些作为弱证据纳入风险摘要。D5 的本地目标 ID、AirSim actor ID 或视觉跟踪 ID 都不能成为 D2 规范 ID。

### 9.5 D2 与 D6

D6 消费：

- `AssociationLogEntry`（关联日志条目）；
- `TrackTransition`（状态转移）；
- 指标摘要和混淆矩阵；
- 回放、门限、风险和场景版本；
- 离线真值评分及可用性；
- 多种子和按难度分组结果。

D2 与 D6 必须显式保留 `id_switch_count`。在线无真值时，D6 不能把兼容数值零解释为“没有身份切换”或“连续性正常”。

### 9.6 D2 与 D7

D7 可沿用 D2/D3 传递的 `global_track_id` 和计划上下文，但不得本地改写身份。D2 不提供制导许可，也不以物理接近或命中结果反向修改关联真值。

### 9.7 main runtime

main runtime（主运行时）负责：

- AirSim Blocks 示例环境启动、重置和回合顺序；
- `--drone-count N`（无人机数量参数）及场景资源生成；
- AirSim `simGetDetections`（仿真检测元数据接口）或其他检测输入采集；
- 在线受治理回放和独立离线真值文件生产；
- D1-D7 总线编排、日志收集与 D6 总报告。

D2 只消费 main/runtime 写出的受治理输入。`DryRunAssociationResult.to_bus_message()`（干运行关联结果转总线消息）输出活动航迹、动态 `global_track_ids`（全局航迹 ID 列表）、关联日志、指标和可用性字段，不对列表补齐到固定规模。

## 10. 回放、校准与证据治理

### 10.1 已实现回放能力

当前回放入口支持 JSON 和 JSONL，兼容旧 AirSim 风格帧和 D1 受治理清单。可输出：

- 每帧关联日志和活动 `global_track_ids`；
- 门控通过/拒绝数及拒绝原因；
- 运动一致性与质量风险摘要；
- IDSW、身份/覆盖连续性、重复解释和 RMSE；
- NIS/NEES 可用性和分布；
- M-of-N 初始化、确认延迟和虚假航迹；
- 种子、回合、场景、帧号、目标数、门限和版本；
- 在线真值泄漏审计；
- 多种子汇总和确定性摘要。

`build_dense_crossing_replay_fixture(target_count=N)`（构造 N 目标密集交叉回放）按传入 N 生成场景；`build_5v5_replay_fixture()`（构造 5 对 5 兼容回放）只是兼容包装器。回放生成器已覆盖观测数少于目标数和多于目标数的帧。

### 10.2 固定矩阵和准入规则

P1 身份校准固定 54 个 GNN 配置：

- 马氏门限 `5.99 / 9.21 / 13.82`；
- 质量感知门控关闭/开启；
- 丢失/删除阈值 `1/3`、`2/5`、`3/7`；
- 运动权重倍数 `0.5 / 1.0 / 2.0`。

十个唯一种子用于筛选；二十个唯一种子用于确认默认基线、最佳 GNN 和同输入轻量 JPDA。缺少要求数量时对应阶段为不可用，不用合成基准场景（fixture）冒充真实 AirSim 结论。

当前 v2 版本化联合准入同时要求：

- IDSW 至少下降 30%；
- 身份连续性按剩余误差空间判定：`H=max(0,1-C_b)`，所需提升为
  `min(0.10,0.10H)`，且候选不得退化；
- 虚假航迹增幅不超过 10%；
- 第 95 百分位（95th Percentile，P95）循环延迟不超过冻结预算；
- 在线真值泄漏为零。

即使全部通过，runner（运行器）也只输出晋级评审建议，不会自动替换默认 GNN。

### 10.3 六档难度状态

代码已支持 `nominal`（标称）、`tight_crossing`（紧密交叉）、`dropout`（漏检）、`clutter`（杂波）、`delayed_noisy`（延迟噪声）和 `combined`（组合压力）六档治理、分档汇总和输入一致性检查。

该支持表示消费、压力变换、版本和汇总接口已实现；不表示六档长期真实 AirSim 数据已全部完成。观测压力变换器不读取真值旁路文件，不移动目标几何，只对雷达记录施加漏检、匿名杂波、到达延迟和协方差放大。

## 11. 2026-07-13 验证结果

### 11.1 严格 4 米 / 2 米真实 AirSim 标定

根据 `subagent_reviews/MAIN_P1_CONVERGENCE_VALIDATION_REPORT_20260713.md`（主收敛验证报告），D1/D2 严格密集交叉验证使用：

- AirSim ComputerVision（计算机视觉）模式；
- 五个目标；
- 标称相邻目标三维距离严格为 4 米；
- 紧密相邻目标三维距离严格为 2 米；
- 每组 20 个种子，共 40 个真实 AirSim 回合；
- 每回合 51 帧；
- evaluator-only truth（仅评估器可见真值）样本共 10200 条；
- 在线真值泄漏为零。

结果为：

| 指标 | 默认基线 | 最佳 GNN 候选 | 结论 |
| --- | ---: | ---: | --- |
| 平均 IDSW | `1.3583` | `0.6167` | 下降 `54.6%` |
| 身份连续性 | `0.9810` | `0.9840` | 仅提高 `0.0030` |
| P95 循环延迟 | 未在基线行报告 | `24` 毫秒 | 满足冻结实时筛选预算 |

2026-07-15 已按 v2 在六档冻结真实 replay/truth 上完整重算。`0.981046 -> 0.983954`
对应 headroom `0.018954`、所需提升 `0.001895`、实际提升 `0.002908`，消除
`15.3448%` 的剩余错误；IDSW、false-track、P95 和 truth isolation gate 也同时通过，
因此生成总体 promotion review recommendation。轻量 JPDA 在同输入下退化。
**推荐评审不等于自动晋级，默认仍是 GNN/匈牙利基线参数，不是候选参数，也不是
JPDA。**

### 11.3 2026-07-15 准入实现状态

- 报告 schema：`d2-p1-identity-calibration/v2`。
- 策略版本：`d2-p1-identity-admission/ceiling-aware-error-reduction-v1`。
- 报告显式携带 baseline headroom、实际/所需提升、error reduction fraction、每项
  gate reason 和弃用的 v1 `+0.10` 审计字段。
- IDSW 至少改善 30%、false-track 最多增长 10%、P95 冻结预算、baseline/candidate
  truth leakage 为 0 等门限保持；任一 unavailable 均拒绝，IDSW 单项不能触发晋级。
- 通过只生成评审建议，`default_online_path_changed=false`。
- 2026-07-15 证据重算为 6x10 screening 和 6x20 confirmation，实际耗时
  `2501.32 s`；未重新启动 AirSim。总体联合 gate 通过，分档仅 clutter/combined
  通过，其余四档 baseline IDSW=0 fail-closed；dropout truth alignment 为 partial。

### 11.2 模块回归状态

2026-07-13 main 报告记录的历史回归为 `93 passed`。2026-07-14 Post-batch 审计后
当时完整 D2 suite 为 `99 passed, 1 warning`；2026-07-22 当前权威结果为
`183 passed, 1 warning in 29.08s`。warning 来自本机 Matplotlib `Axes3D` 环境，
不影响 D2 结论。当前模块使用 Python pytest 测试框架，
并通过环境变量 `PYTHONPATH`（Python 模块搜索路径）指向 D2 模块目录：

```bash
PYTHONPATH=research_modules/d2_data_association pytest -q research_modules/d2_data_association/tests
```

### 11.3 已解决问题

截至当前日期，以下问题已有实现和验证证据：

1. 默认 GNN/匈牙利、马氏门控、动态矩阵和状态机可执行；
2. 观测与航迹协方差输入治理、Joseph 更新和诊断证据闭合；
3. `track_quality`、`association_risk`、运动一致性和质量感知门控已进入默认主线；
4. `id_switch_count`、身份/覆盖连续性、重复解释、RMSE 和混淆矩阵显式输出；
5. 无真值时的指标可用性不会再被兼容数值零掩盖；
6. D1 受治理雷达输入、双时间戳、NED 投影和不支持模态跳过已实现；
7. 在线身份匿名化、真值递归剥离、离线标签合同和严格时间对齐已实现；
8. 动态 N 目标、至少十种子、长期合成回放、M-of-N、虚假航迹和 NIS/NEES 接口已实现；
9. 严格 4 米/2 米各二十种子的首轮真实标定已完成；
10. 候选没有满足完整门限时保持默认主线的保守准入规则已生效；
11. 跨节点命名空间、公共时刻传播、按来源匈牙利注册、重复信息拒绝和规范绑定基础已实现。

### 11.4 剩余局限

1. **身份性能未完全收敛**：真实严格场景中候选 IDSW 改善明显，但连续性增益不足；不能宣称密集交叉身份问题已经解决。
2. **长时真实数据仍不足**：更长 OOSM、遮挡、连续漏检、杂波和延迟噪声组合的真实回放尚需扩展。
3. **生命周期参数未冻结**：M-of-N、虚假航迹、丢失/删除阈值及确认延迟仍需按密度和漏检率分层标定。
4. **统计一致性未完成真实分层标定**：NIS/NEES 接口存在，但尚需按传感器、距离、场景和种子汇总。
5. **默认模型仅二维常速度**：强机动和三维垂直运动可能增加预测误差与候选重叠。
6. **高阶关联不完整**：轻量 JPDA/MHT 不能代表完整算法，且当前真实对照没有证明替换收益。
7. **无在线真值时不能直接知道 IDSW**：在线只能发布歧义、候选重叠、代价间隔和质量风险；真实 IDSW 必须离线评分。
8. **跨节点数值融合未闭合**：D2 只发精确相关融合或 CI 请求，D1 后验回写与 D6 ANEES 仍缺失。
9. **owner/epoch 故障切换未实现**：D4 的二级或分布式提交成功不等于 D2 规范 ID owner 切换已实现。
10. **物理闭环不能替代 D2 验证**：main 报告中的协同物理结果、视觉获取或制导结果属于其他模块和系统层，不可反推 D2 身份连续性已闭合。

## 12. 选型理由

### 12.1 为什么默认使用 GNN/匈牙利

- SciPy 提供成熟、确定性的一对一求解器；
- 复杂度和运行延迟可控，适合作为默认工程基线；
- 匹配、未匹配、门控、候选数和代价都容易审计；
- 可直接复用同一 `Tracker` 生命周期和指标；
- 2026-07-13 真实验证没有证据支持 JPDA 替换默认路径；
- 参数候选未达到全部冻结门限，维持默认配置符合证据治理规则。

### 12.2 为什么保留 JPDA/MHT 对照

- GNN 是单帧硬判决，无法表达多个候选同时合理；
- JPDA 可暴露边缘概率分散和候选不确定性；
- MHT 可研究多帧延迟决策是否减少交叉期错误；
- 二者能在同一接口和离线真值评估下做受控对照。

保留对照不等于自动切换，也不等于完整算法已经实现。

### 12.3 为什么不把第三方库放入默认路径

- 默认回归需要保持轻依赖和可复现；
- Stone Soup/FilterPy 当前只完成对象适配，不具备 D2 总线合同、中心 ID 权威和完整生命周期；
- 没有端到端 IDSW/连续性结果时，对象转换延迟不能证明跟踪收益；
- 外部对象不应泄漏到跨模块总线。

### 12.4 为什么在线和离线必须分层

使用 AirSim actor ID 或真值标签在线关联会把评估答案泄漏给算法，使 IDSW、连续性和准入结论失真。当前采用“在线匿名关联、写盘后独立评分”，既保留可重复评估，又确保主线只依赖现实中可获得的量测、协方差、时间和特征。

## 13. 中文术语表

| 术语 | 含义 |
| --- | --- |
| D2 | 仓库中的数据关联模块代号 |
| 全局航迹 ID | 中心维护的规范身份键，对应代码字段 `global_track_id` |
| 观测 ID | 单帧观测键，对应 `detection_id`，不具备全局身份权威 |
| IDSW | 同一真实目标的代表全局航迹 ID 发生变化的计数 |
| GNN | 全局最近邻；对整帧候选做一对一硬分配 |
| 匈牙利算法 | 求解线性和分配问题的组合优化算法 |
| JPDA | 联合概率数据关联；对合法联合假设求边缘关联概率 |
| MHT | 多假设跟踪；跨帧保留并剪枝多个关联假设 |
| NED | 北-东-地坐标系，Down 轴向下 |
| CV | 常速度运动模型，不是本文中的计算机视觉模式简称 |
| 马氏平方距离 | 用创新协方差归一化位置残差的距离 |
| 门控 | 在全局分配前排除统计上不相容的航迹-观测候选 |
| 质量感知门控 | 按航迹质量、密度、协方差和前帧风险调整门限的当前轻量基线 |
| 暂定航迹 | `tentative`，尚未达到确认命中条件的航迹 |
| 确认航迹 | `confirmed`，达到确认条件但未必达到更高质量门槛的航迹 |
| 可供下游研究使用 | `engageable`，仅表示航迹质量状态，不表示处置授权 |
| 丢失航迹 | `lost`，连续漏检达到丢失阈值但尚未删除 |
| 删除航迹 | `dropped`，连续漏检达到删除阈值，不再作为活动航迹 |
| 身份连续性 | 真实目标存在期间由同一代表航迹稳定覆盖的平均比例 |
| 覆盖连续性 | 真实目标存在期间由任意航迹覆盖的平均比例 |
| 重复分配 | 同帧观测、航迹或真实目标被重复解释的异常 |
| RMSE | 位置估计均方根误差，不能替代身份指标 |
| NIS | 用创新协方差归一化的匹配前残差平方 |
| NEES | 用状态协方差归一化的估计状态与离线真值状态误差平方 |
| M-of-N 初始化 | N 次扫描内至少 M 次命中的初始化评估口径；当前只用于离线治理 |
| OOSM | 到达或处理顺序与量测时间顺序不一致的乱序量测 |
| CI | 未知交叉相关时的保守协方差融合方法；跨节点多 source 数值融合仍由 D2 请求、D1 执行，D2 六维 tracker 内另用固定权重 CI 处理同一 source posterior 的未知时序相关性 |
| 规范航迹 | 跨节点注册表维护的中心全局目标表示 |
| 来源航迹 | 某个节点本地跟踪器产生、带节点和纪元命名空间的航迹摘要 |
| 信息谱系 | 描述观测或航迹由哪些来源信息产生的 lineage，用于防止重复使用 |
| 在线真值隔离 | 在线关联输入、航迹和日志不含仿真真实身份，真值只供事后评估 |
| 软风险 | 歧义、候选重叠、代价间隔或短时 D5 不一致等不确定性证据 |
| 硬风险 | 已发生的 IDSW、重复解释或可用连续性崩溃证据 |

## 14. 当前结论

截至 2026-07-20，D2 保留可运行、可审计、按动态输入规模工作的二维默认主线，并已实现显式选择的六维稀疏规则路径。两条路径都坚持 GNN 表示 Global Nearest Neighbor、中心拥有 `global_track_id`、在线不读取真值。六维路径的 D2-owned 状态/门控/稀疏求解/风险/离线评分和 source-posterior 速度稳定性基线已闭合；main 修复后端到端复跑、多 seed 高密度证据、CI 权重与 NIS/NEES 标定、JPDA/MHT 高阶版本、自动切换和跨节点数值融合仍处于明确的待验证或未实现边界。

### 14.1 2026-07-14 truth 与 lifecycle 原则补充

在线 Tracker 默认采用显式 `online` truth policy，并在状态变更前拒绝 truth、AirSim actor 和 simulator object identity；只有显式 `offline` evaluator 可消费 truth。布尔型 truth governance/availability 状态不是身份：已知的四个状态键只在值为布尔型时允许通过，非布尔值和 offline truth payload 仍拒绝。无 truth assignment 时 IDSW、track continuity 和 RMSE 必须输出 `None + available=false + reason`，不能用零代替不可用；有 truth 且确实无 ID switch 时零值仍然有效。

birth/lost/drop/rebirth 计数和状态转移是 truth-free 航迹事件。rebirth 只表示同一 `global_track_id` 从 lost 重获，不能据此宣称 dropped 后新建航迹属于同一真实目标。2026-07-14 完整回归为 `98 passed, 1 warning`；本批未调整 gate/lost/drop，`T001 -> T005` 生命周期参数冻结仍为 P1。

### 14.2 来源航迹 ID 与规范航迹 ID 不同

`source_global_track_id` 是 D1 上游航迹谱系，不是 AirSim 真值，也不是 D2 规范身份。
D2 可以用它在马氏门内保持同源连续性，并把多个重复上游来源保守归并到同一个
`global_track_id`；D2 不能把来源 ID 直接复制成规范 ID，也不能仅凭来源名称越过
几何门限。

当同帧新来源与既有规范航迹重叠时，D2 延迟其 birth，避免把跨模态影子立即解释为
新目标；当已绑定来源发生统计大跳时，D2 fail-closed 隔离该输入，避免连续 mint 新
ID。2026-07-14 匿名四帧回归验证了这两条原则，完整测试为 `99 passed`。真实 AirSim
同 seed 复跑已不再出现 `T008`；2026-07-15 的 20-case 普通 M5N2 已补齐多 seed
运行时延证据，但没有显式上游重复/跳变扰动和该批离线身份评分，二者仍是独立开放项。

### 14.3 Post-batch 单 seed 原则结论

真实 M5N2 baseline/candidate seed 1 分别运行 142/141 帧。前 2 帧为 D1/D2 启动期，
之后均只存在两条 D1 来源航迹和两条 D2 规范航迹；生命周期均为
`birth=2, lost=0, drop=0, rebirth=0`，没有 `T008`。在线不读取 truth，因此在线
IDSW/continuity 必须保持 unavailable；独立离线评分才可报告 IDSW 0 和 continuity。

该证据关闭的是“同 seed 修复后仍膨胀”的疑问，不是完整 P1。两个 episode 没有触发
shadow suppression 或 teleport quarantine，只能说明正常数据未被误拦。后续普通
M5N2 已达到 20 case，但没有专门构造重复来源、teleport、漏检、杂波与合法新目标，
也没有为该批冻结离线身份评分；这些受治理专项完成前，不能冻结来源连续性权重、抑制
窗口或 lifecycle 参数，也不能用 seed 数量替换既有严格 admission。

### 14.4 来源身份治理的计数原则

来源治理必须可累计审计，但计数本身不获得身份权威。D2 从每帧关联结果中分别累计
`source_binding_conflicts` 和 `quarantined_sources`，形成
`source_binding_conflict_count` 与 `source_lineage_quarantine_count`。上游在像素/局部
tracker 支线中已经拒绝的身份塌缩，只能通过 frame metadata 的
`upstream_local_identity_rejection_count` 作为审计数进入 D2；字段缺失为 0，且只有
非布尔的非负整数合法。非法值必须在预测、关联和建轨前 fail closed。

这三项不生成观测或航迹，不把 local/source ID 提升为 `global_track_id`，不替代
`id_switch_count`，也不自动构成软/硬风险阈值命中。D2 不消费原始像素、不复制 D5
`bright_hungarian`，而是继续复用 GNN/Hungarian、马氏门控与来源谱系治理。

2026-07-16 的连续同源、binding conflict、Mahalanobis discontinuity、零检测 upstream
audit、非法 metadata 和 legacy 回归均通过；两个 3-frame synthetic seed 输出
conflict=`1/1`、quarantine=`1/1`、upstream rejection=`2/4`，全量结果为
`123 passed, 1 warning`，验收阈值零失败。该证据是模块合同/回放证据，不是实际
AirSim 受扰运行证据；真实至少 10 个来源扰动 case 仍待标定。

## 15. 六维稀疏关联原则

1. **坐标和状态唯一**：工作坐标固定 NED，状态顺序固定
   `[pN,pE,pD,vN,vE,vD]`；高度解释为 `-pD`，D2 不在内部切换 WGS84 或 ENU。
2. **门控只用三维创新**：候选是否可行由位置 residual 和 3x3 innovation covariance
   的马氏距离决定。速度只以封顶代价打破交叉平局，不能改变 gate 自由度或把速度
   离群值变成位置拒配。
3. **先稀疏后求解**：KD-tree 只生成保守候选；精确门控后按二部图连通分量做 Hungarian。
   分量解合并仍是候选图上的全局最近邻，不是贪心局部最近邻。
4. **GNN 不改含义**：`GNNHungarianAssociator` 和
   `Sparse3DGNNHungarianAssociator` 中 GNN 均为 Global Nearest Neighbor。D2 不实现、
   不命名伪装、也不训练 D5 所属的跨视角 Graph Neural Network。
5. **中心身份不可借用**：上游 observation/local track ID 只能作 namespaced source
   evidence；D1 对象的 `global_track_id` 不进入六维 canonical namespace。只有 D2
   tracker 创建 `GT3D-*`。
6. **在线不猜 truth 指标**：在线风险摘要只基于候选重叠、cost margin、漏配和 lifecycle；
   `id_switch_count`、continuity 保留显式字段但为 unavailable。truth sidecar 只能在
   `Sparse3DOfflineEvaluator` 中事后评分。
7. **历史和矩阵有预算**：不保存全密集 cost/distance history；每条 track history 和
   frame log 有硬上限。极端大连通分量必须通过统计字段暴露，不能声称空间索引使最坏
   情况天然线性。
8. **相关 posterior 不重复计数**：D1 六维 posterior 必须携带完整 6x6 covariance。
   同一 source 的时序交叉相关未知时使用 CI，不得再作为独立位置量测重复收缩 Pvv；
   速度创新 NIS 超门只通过 covariance inflation 降权，不按速度模长或场景名硬裁剪。
   当前 CI track weight `0.5` 仅是待标定 baseline，不是最优性结论，也不等同于跨节点
   多 source 的 D1-owned 数值融合。

2026-07-20 验收覆盖 5/20/50/100/200、交叉、漏检、虚警、truth 拒绝、历史上限和
六维速度稳定性；全量为 `139 passed, 1 warning`。200 目标 3 个 trial、共 90 个测量帧的候选均为
`200/40,000`，裁剪 `99.5%`，聚合关联/tracker-step P95 为
`7.056/26.797 ms`，max 为 `22.471/41.613 ms`。证据来自单一确定性合成布局，尾值
包含系统调度抖动，不能外推为真实多 seed、AirSim 或端到端实时保证。

同日速度专项的 50 条 seed 17、12 帧输入速度 P50/P90/max 为
`5.415/7.960/12.274 m/s`，修复后为 `5.082/6.401/7.218 m/s`，Pvv trace 为
`101.181`，位置 RMSE `52.634 -> 48.364 m`，离线 IDSW 0、continuity 1.0。200 条
seed 41、10 帧更新中，候选/全对保持 `200/40,000`，输入/输出速度 P90
`8.097/5.980 m/s`，IDSW 0、continuity 1.0。在线 tracker 未读取离线标签；固定 CI
权重的至少 20 未见 seed、六维 NIS/NEES coverage、高机动和 main 修复后端到端复跑
仍是必需的后续验收。

## 十八、scalable 3D 离线身份映射原则（2026-07-20）

1. **真值只在 evaluator join**：在线 D1/D2 records 和 association evidence 只能保留
   observation/source lineage、时间戳、lifecycle 与 D2 canonical ID；不得新增
   `truth_target_id`、actor/object identity 或在线 truth map。
2. **唯一允许的身份连接是 observation lineage**：truth sidecar 只提供
   `observation_id -> truth_target_id`。名称、actor ID、终态邻近、最近距离、位置
   Hungarian 均不是本合同的身份来源。
3. **来源先验完整性优先于部分数值**：evidence bundle、D1 records、D2 records 和 truth
   sidecar 必须经过 schema、SHA-256、record sequence 和在线 truth-isolation 校验。
   sequence 必须进一步绑定 D1 lineage 与 D2-owned canonical ID、六维 state、6x6
   covariance、frame/lifecycle/association，并覆盖完整 D2 track-frame；校验失败不产出
   指标，校验通过但 lineage 不足时输出带原因的 unavailable/ambiguous。
4. **重复和重放必须区分**：同 lineage 跨帧重用必须显式递增 `replay_generation`；同帧
   重复、未标记跨帧重复、跨 global track 重绑、同 observation 的不同 lineage 均不能
   被静默去重为有效身份。
5. **多重关系不强制一一化**：一个 truth 对多条由不同 observation 支持的 track 是可
   审计 duplicate；一条 track 的完整证据指向多个 truth 则 ambiguous。D2 evaluator
   不用全局 Hungarian 强制选一个 truth。
6. **availability 是指标合同组成部分**：IDSW、track/identity/coverage continuity、
   duplicate 和 confusion matrix 只在全部相关 mapping 可验证时可用。不可验证时值为
   `None`，不能写 0。可用时口径与 `MetricsRecorder` 一致。
7. **生命周期不能被 truth 修补**：dropped 后同 canonical ID 复用、非法 lifecycle
   回退、inactive track 带当前关联 lineage 都会阻断身份指标；truth sidecar 不允许改写
   `global_track_id` 或在线状态机。

上述原则由五个 `v1` schema 和 23 个专项测试约束；2026-07-20 完整 D2 回归为
`162 passed, 1 warning in 30.63s`。本轮不改变默认 GNN/Hungarian、JPDA/MHT、门限、
owner 或控制链路，也不构成 AirSim/point-mass 多 seed 性能证据。

## 十九、在线观测新鲜度与重复航迹治理（2026-07-22）

### 19.1 观测时间和状态时间

D1 可以把旧量测形成的后验预测到新的状态时刻。对 D2 而言，新状态时间说明该后验
可以与当前航迹比较，不说明出现了新的传感器信息。若 `latest_observation_id` 和源量测
时间未变化，同一后验跨帧进入滤波会重复降低协方差、增加命中数并绕过确认门。

D2 同时使用三类时间：`Detection3D.measurement_timestamp` 表示后验状态有效时刻，
`arrival_timestamp` 表示到达 D2 的时刻，metadata 中的
`source_measurement_timestamp` 表示后验最新底层观测的量测时刻。关联仍在统一状态
时刻进行；是否允许形成 hit 由 opaque observation key、最大迟到和声明水位线共同决定。
不同 observation ID 只有在源量测时间未超过配置的 max-lateness 时才可接纳；同一 ID
重放或同一 ID 对应冲突源时间直接隔离。

### 19.2 生命周期抑制

确认采用连续新证据，而非连续发布帧。tentative 第一次没有新证据时只清零连续命中；
第二次仍无新证据则删除。已确认航迹继续使用原 lost/drop 门限。该取舍允许一次短时
漏配后由新观测恢复旧中心 ID，同时阻止单个离群观测衍生的航迹靠 D1 预测重放确认。

### 19.3 合并安全条件

空间接近只能说明统计重叠，不能证明同一目标。当前合并必须先具备共享 observation
key 或 namespaced source-track key，再同时满足位置和速度马氏距离门。两个航迹在同帧
各自获得不同新观测时禁止合并。survivor 选择顺序为生命周期成熟度、创建时间、命中
数、漏配数和中心 ID；状态用协方差交叉融合，hits 取最大值而不求和。这样保留一个
已有中心 ID，也不把相关重复信息当作独立量测增加确定性。

active-risk 5v5 seed 1005 验证中，两条问题航迹相距约 1.5--1.6 km，没有执行空间
合并。D2 隔离 9 次同 observation 重放，错误 tentative 航迹连续两次无新证据后删除，
原 `GT3D-000004` 由新观测恢复。10 个发布帧从 `5,6,6` 收敛为后续 7 帧均为 5 条，
online truth use 0。5 个合成专项和 1 个真实 seed 专项通过；完整回归
`168 passed, 1 warning in 26.15s`。该结果是模块级单 seed point-mass 证据，不能代替
AirSim 标定。

### 19.4 多 seed 证据边界

main 随后在同日脏工作树运行 active-risk seeds 1000--1019 的 control/treatment 隔离
对照。总线已将 observation evidence governance 以版本化 `v1` 结构持久化。D6 七类
非因果证据可用性均为 20/20；D4 adoption 合计 188/188，两臂各应用 1960 条命令。
seed 1005 的离线谱系只恢复 GT1-GT5 五条唯一映射，在线真值使用为 0。

同日提交 `0fa7c00` 的 clean-tree 运行记录源提交统一、`repository_dirty=false`、20 个
pair、D4 adoption 188/188、两臂各 1960 条命令和 100 条离线唯一映射。control 和
treatment 在 1 s 有效窗内均无 5 m 拦截；counterfactual、causal、production runtime
ACK 均不可用。clean 复跑已完成，但不构成策略收益、AirSim 或 200v200 验收。

## 二十、长时声明和乱序整帧原则（2026-07-22）

### 20.1 有界声明

声明策略同时配置 retention、max-count 和 max-lateness，并携带独立版本。max-lateness
形成观测接纳水位线；`max(retention, max-lateness)` 形成更保守的淘汰水位线。claim 只有
越过淘汰水位线后才能删除。原量测再次到达时仍早于接纳水位线，因而不能形成命中或出生。
该方法用受信源量测时间代替无限 tombstone。源量测时间缺失时不做不安全淘汰；容量满后
新证据拒绝，并显式报告 overflow。

声明字典、航迹反向 key 和淘汰最小堆的常驻规模均为 `O(C_max)`。逐帧与累计审计区分
too-old、同 key 时间冲突、replay、同帧重复和 overflow，并报告 current、peak、evicted、
undated、两个水位线和配置版本。中心 `global_track_id` ownership、GNN/Hungarian 和在线
`id_switch_count=None/unavailable` 不变。

### 20.2 整帧乱序

Tracker 本体保持单调 state time。乱序 scan 只能先进入
`Scalable3DOOSMScanAdapter`，按 arrival time 建立事件时间水位线，再按 measurement time
释放完整 scan。超 max-lateness、早于已释放 state、arrival 回退或缓冲溢出均整帧拒绝。
`flush()` 只用于 episode 结束后的有序排空；该适配器不进行回溯、重放或固定滞后平滑。

### 20.3 验证边界

2026-07-22 的 5 x 500 帧和 40 x 200 帧循环均满足 claim peak/current 不超过 `6N`、
overflow 0、安全淘汰大于 0。3/12 目标、16 帧、0.75 m 间距离线 benchmark 的合法检测
为 43/187，误抑制 0、召回 1.0、错误合并 0、确认延迟 0.25 s、IDSW 0；truth 仅在关联
完成后进入 evaluator。完整 D2 回归为 `183 passed, 1 warning in 29.08s`。

这些数据是确定性模块 fixture。2026-07-22 后续完成的 formal/clean 质点治理
批次已覆盖 20/50/100/200 各 5 个 seed，见第二十三节。真实 AirSim observation ID、
时钟漂移、迟到分布、遮挡/杂波以及身份连续性标定仍需单独完成。

## 二十一、重复后验短时续航原则（2026-07-22）

D1 的状态发布频率可以高于雷达新量测频率。相邻发布帧携带同一 observation ID 时，D2
仍把它视为重放，不重复融合。若该证据已经绑定活动中心航迹，且距最后一次新鲜更新不
超过版本化宽限，航迹只按运动模型预测，本帧不增加漏配。这样避免正常传感器更新间隔把
航迹误判为 lost。

宽限时钟只从新鲜量测更新。重放不增加命中、不重置漏配、不建立航迹，也不刷新宽限。
时间冲突、过旧、溢出、未绑定和超时继续保守拒绝并计 miss。该策略只处理发布节拍差，
不替代传感器失联检测。真实 AirSim 需要按雷达周期和抖动分布标定默认 0.5 s。

## 二十二、在线航迹库存原则（2026-07-22）

在线航迹数量由已到达且通过治理的观测、关联结果和生命周期共同决定。场景目标总数只在
仿真配置和离线评估中可知，不能用来补齐 D2 航迹。雷达漏检或量测尚未到达时，冻结的
干预快照可以少于目标总数；这应记录为检测/初始化可用性，而不是伪造一条无观测航迹。

active-risk seed 1005 当前保持 5 条规范航迹且不再经历第 6 条错误出生。main 在尾部只把
最终 D1 后验送 D2 一次，因此该集成路径 replay=0 合法；D2 模块仍用独立 fixture 验证
正数 bounded replay。保留 seed 1011 和 1019 在 1.0 s 干预时刻各只有 4 条航迹，后续
新鲜观测到达后恢复到 5 条 confirmed。两类结果共同要求验收按实际在线库存检查身份
唯一性、谱系、生命周期和覆盖率，不能固定发布次数或强制航迹数等于离线真值目标数。

## 二十三、formal/clean 治理证据原则（2026-07-22）

1. **正式性按 episode 判定**：20 个 manifest 均必须同时满足
   `evidence_tier=formal`、`repository_dirty=false` 和绑定提交
   `e4d66db02a0b8f1b867a0e81b4a73de84588426b`。`runner_summary.json` 顶层没有
   `formal_episode_count` 不能被解读为 0；分档 aggregate 中每档 5 个 formal episode
   与每个 manifest 的 provenance 是验收依据。
2. **真值隔离优先于分数**：在线路径真值使用总数必须为 0。召回率、误抑制、错误合并和
   确认延迟只来自 `evaluator_only=true`、`online_consumed=false` 的 sidecar。本批次四档
   近邻召回率为 1.0，两类错误率为 0，确认延迟为 0.25 s。
3. **容量验收不等于全系统验收**：20/50/100/200 规模的 claim peak 都低于对应
   capacity，安全淘汰已发生且 overflow/too-old 为 0。这关闭 clean 治理复跑，不代表完整
   D1-D7 融合、真实 AirSim、多场景身份连续性、实时服务等级或物理拦截已通过。

## 二十四、性能优化的语义等价原则（2026-07-22）

1. **先定位热点**：阶段墙钟与函数 profile 分开记录。嵌套函数累计时间不能相加成总
   墙钟；优化对象必须由同一冻结输入上的 profile 确认。本批热点是 metadata 身份审计，
   不是稀疏 Hungarian。
2. **身份审计不能旁路**：可以缓存纯字符串的归一化和禁用键分类，但缓存必须有界；
   `Detection3D` 构造和 Tracker step 两道审计都保留。删除 adapter 预扫描不等于删除
   输入审计，构造后篡改仍应 fail closed。
3. **算法语义逐域比较**：性能对照分别哈希完整发布、关联、中心 ID/生命周期、claim/
   审计和逐周期记录。只比较航迹数或终态 ID 不足以证明等价。
4. **真值只校验输入**：比较器可校验两侧 offline truth sidecar 的文件哈希，确认输入
   相同；在线关联不得读取 sidecar。在线无真值时 IDSW 和 continuity 继续 unavailable。
5. **墙钟不等于 SLA**：五 seed 墙钟只描述当前主机和 nominal 200v200 输入。候选未在
   clean-tree 固定环境晋级前，不能写成实时保证，也不能外推到 AirSim 或极端全重叠图。

本批 45/45 周期语义哈希一致，在线 truth use 为 0。单 episode D2 总墙钟均值
`9.8299 -> 2.7679 s`，五 seed 合计 `49.1497 -> 13.8397 s`。GNN/Hungarian、三维
门控、中心 `global_track_id`、claim ledger 和生命周期没有改变。

## 二十五、批内共享诊断审计原则（2026-07-22）

D1 同一发布批次的航迹可以携带相同的传感器健康和融合审计信息。D2 必须在接收边界检查
其中是否含真值或外部身份，但不需要对内容相等的大型诊断树按航迹重复递归。首个值通过
完整审计后，后续值只有在内容相等时才复用结果；任一变化都会重新执行完整检查。

审计与运行时合同分开处理。审计覆盖全部输入 metadata，随后只将双时间戳、观测标识、
来源谱系、模态和坐标帧等 D2 消费字段带入关联对象。`Detection3D` 构造和 tracker step
继续执行身份审计。该顺序同时保持 fail-closed 边界，并阻止 D1-owned 诊断规模进入 D2
逐轨热路径。

最终审查加固代码的 200 航迹、48 周期基准从 `16.858297 s` 降至 `6.472896 s`，加速
`2.604444x`。未知或自定义 Mapping 必须完整递归审计，不可依赖其 `__eq__` 复用结果。
既有实际 10 秒隔离回放计时属于该审查加固前候选；48/48 周期语义域哈希仍有效，最终
加固性能需 main 复跑。该原则不改变门控、Hungarian、中心 ID、claim、replay/stale、
生命周期或 IDSW availability。

## 二十六、协方差与创新复用的可信边界（2026-07-22）

1. **先固定操作数**：性能候选必须保持输入、fresh/replay 分类、空间候选、三维马氏门控、
   合法边、连通分量和匹配数量不变。当前 48 周期对照的 1,820,766 个 dense pair、9215
   个空间候选、9017 条合法边和 9012 个匹配逐项相同。
2. **只复用同一周期的已验证量**：关联边计算的 velocity NIS 可由紧随其后的同一匹配
   更新消费；不得跨周期、跨航迹或跨候选复用。该值是私有瞬态数据，不进入公开
   `AssociationResult` 序列化。
3. **预验证不是外部声明**：普通 `Detection3D(...)` 不接受 covariance 预验证参数。
   只有 D1 adapter 刚调用 `govern_covariance()` 得到的同一 ndarray 且结果为 consistent
   时，才在内部构造期间复用；regularized 输入继续执行原 full covariance 校验。
4. **边缘正定不代表整体正定**：位置和速度 3x3 marginal 各自合法，不能替代含交叉项的
   6x6 PSD 检查。伪造 `covariance_regularized=false` 诊断不具可信性，普通构造必须拒绝
   交叉项导致整体非 PSD 的矩阵。
5. **批处理不改变边界**：批量 `eigvalsh` 和 KD-tree query 只能合并函数调用，查询半径、
   候选排序、门控和合法候选集合必须逐周期等价；1x1 连通分量可省略求解器调用，因为图中
   唯一边已经通过全部门控。

冻结在线回放的 48/48 周期完整语义哈希一致，合计中位墙钟
`4.859477 -> 4.018963 s`。该原则不授权减少输入、降低频率、截断候选、放宽门控、读取
truth 或改变中心 ID/IDSW 语义。

## 二十七、跨构建集成等价原则（2026-07-22）

1. **先比较 D2 自身语义**：跨提交验证必须逐条比较 D2 发布、中心航迹标识、状态、
   covariance、生命周期、claim 和审计字段，并核对 topic counts。只比较终态航迹数量
   不能证明身份链路等价。
2. **不透明计划号只在下游规范化**：独立 D3 planner 会生成新的 `plan_id`。main 只能按
   plan occurrence/version 映射该不透明谱系，并在映射前验证 ACK 原始载荷 SHA。owner、
   version、coalition、`global_track_id` 和 command 业务字段不得归一化或忽略。D2 记录
   本身不需要计划号归一化。
3. **阶段耗时与系统实时性分开**：nominal 200v200、10.0 s 的三个 clean seed 中，每组
   D2 association 均调用 47 次，累计耗时均值 `8.317513 -> 7.671266 s`，约下降
   `7.77%`。该数值证明候选在本批集成输入上降低阶段墙钟，不等价于实时服务等级。
4. **数量相同只是必要条件**：seeds 42000/42001/42002 的终态 D2 航迹数
   `205/204/203` 两侧相同，且逐条在线语义、topic counts、有限状态和 truth isolation
   同时通过，才构成当前 clean 非退化证据。
5. **增长问题继续开放**：短长归一化对照仍将 `module.d2_association` 判为超线性。
   因此不得把三 seed 平均耗时下降写成性能 P1 已关闭；真实时钟、困难候选图、离线身份
   指标和固定硬件周期分位数仍需验证。

## 二十八、部分身份指标原则（2026-07-22）

严格指标和部分诊断承担不同用途。严格 IDSW、身份连续性、覆盖连续性和重复解释要求所有
参与评分的映射完整且无歧义；任一阻断都会使整组严格指标 unavailable。部分诊断只回答
“现有侧车中有多少证据可审计”和“至少能证明多少次切换”，不能替代严格指标。

映射覆盖率以 `created/matched` 航迹帧映射为分母。完整帧覆盖要求本帧真值存在集合已知，
且所有受评分映射都能唯一落到本帧真值。部分下界还要求同一真值帧恰好对应一个唯一可评估
全局航迹。存在多条航迹时，严格指标保留既有代表顺序和重复计数，部分下界排除该真值帧，
不得用顺序第一条制造锚点。相邻转移覆盖只统计连续真值存在帧两端都有唯一锚点的情况。
IDSW 下界可跨过中间不完整帧，但只比较同一真值连续的唯一锚点；各锚点区间互不重叠，
唯一航迹不同才能计一次。零锚点转移时，下界不可用。

缺标签和歧义可能掩盖未知数量的身份转移，当前合同不发布 IDSW 上界。下界 0 只有在至少
一个锚点转移已经评估且未发现切换时才成立。单帧或零转移场景即使严格 IDSW 因定义为 0，
部分下界仍保持 unavailable，防止把“没有样本”解释成“没有切换”。

clean source commit `0d2da25` 的 seed 1000 只读复算中，严格 IDSW 保持 unavailable；
8906/9038 条受评分映射可评估，完整帧 3/48。1 个真值帧因多条可评估航迹被排除；该帧
本来就不完整，因此仍由 385 个唯一锚点区间证明下界 7。该证据用于验证 producer 合同，
不代表 20-seed 性能，也不允许进入在线风险或身份绑定。

## 二十九、冻结回放 profiler 与长窗口判定原则（2026-07-23）

1. **先证明输入恢复正确**：在线总线允许 D1 与 MAIN/D5/D7 记录交错。D2 profiler 必须
   使用每条 D2 输出之前最新的 D1 发布，不能假定两者物理相邻。clean `4ac3bb2`、
   nominal 200v200、seed 1000、10.0 s 冻结输入恢复出 48 个周期，输入 SHA-256 为
   `c1dda8523e48c255bbeef48d9516b05863eb1bbb3a3ae2e09733259e6a66f77a`。
2. **优化必须有可数热点**：本轮只处理 cProfile 能直接归因的三项重复工作，即相同
   `dt` 的 CV 矩阵重建、可信 adapter 内同源 covariance marginal 的重复 `allclose`，
   以及 claim ledger summary 的重复生成和容器扫描。优化后调用数分别由
   `9246 -> 46`、`19252 -> 0`、`96 -> 48`；候选、匹配、门控和发布频率不变。
3. **可信复用只存在于同一构造边界**：D1 adapter 先治理完整 6x6 covariance，再从该
   同一 ndarray 直接取得位置和速度 marginal。只有三个对象引用都与本次构造参数一致时
   才可跳过边缘相等检查；普通构造不能声明该状态，regularized covariance 仍执行完整
   fallback。CV 矩阵只在同一 `predict_all()` 调用内按精确 `dt` 复用。
4. **账本摘要必须精确而非近似**：undated claim 数和 track-observation key 总数随插入、
   绑定、淘汰及 duplicate coalescence 精确更新；每帧生成一次 summary 后复制到两个
   既有发布位置。字段、版本、淘汰语义、上限和逐条声明均不改变。
5. **语义验收优先于墙钟**：同输入旧/新 48/48 周期完整公开结果和 tracker 状态必须严格
   相等，固定诊断也必须相等。本轮语义 SHA-256 为
   `b2334c619b9d2f7c467387ad27b62614d028af83f0b7842b867cab1c4aa9824b`，
   `online_truth_used=false`。`global_track_id`、`id_switch_count` availability、门控、
   版本、claim 和真值隔离不能为了性能调整。
6. **墙钟只作可复现诊断**：CPU 0、BLAS/OMP 单线程、1 次 warmup、7 次重复下，D2 core
   总中位数 `2.928830 -> 2.204672 s`，只表示本机该冻结输入的 `1.328465x` 描述性
   加速。测试不得设置脆弱墙钟阈值。机器报告 SHA-256 为
   `2256d6fdd29223ed5dd75351cd6bb208a4d67c55925eeba047620ac865b6c7da`。
7. **绝对下降不等于增长闭合**：候选早/晚 regular 窗口比 `1.123036x`，基线
   `1.119661x`，长窗口趋势未改善。原完整阶段 10.0 s 相对 2.2 s 单次成本约
   `1.579x` 的 P1 继续开放；单 seed 质点回放不能替代 AirSim、完整 D1-D7、多 seed
   身份评估、极端候选图或固定硬件实时预算。

## 三十、严格身份阻断诊断原则（2026-07-23）

1. **阻断原因必须回到持久化观测谱系**：诊断只连接 D2 航迹帧、D1 来源观测、量测时刻
   和独立离线标签。每个多真值结论必须至少由两个不同 observation ID 的唯一标签证明。
   位置、距离、名称、actor ID、终端接近和后验最近邻不能作为身份补全证据。
2. **当前多真值是数据混轨，不是分母误差**：clean `5263e2b` 的 20 个 nominal
   200v200 episode 中有 118 个航迹帧同时携带多个真值，形成 107 个连续时间段。典型
   情况是同一 D1/D2 航迹帧同时携带雷达目标 A 和视觉目标 B；也存在相邻雷达观测在同一
   航迹内交换真值。改变评分窗口、选最新观测或多数投票都会掩盖该证据。
3. **标签缺失和虚警必须显式区分**：2464 个受评分映射缺 sidecar 标签；D1 可用估计侧
   为 2474 条。虽然 producer 中这批观测来自视觉虚警生成路径，冻结 sidecar 没有写出
   `known_false_alarm` 状态，离线 evaluator 不能依赖 observation ID 的文本形式推断。
4. **严格指标保持全时序唯一性**：任一受评分映射歧义、缺标签或违反完整性时，strict
   IDSW、continuity、duplicate 和 confusion matrix 继续为 unavailable。部分 mapping、
   frame、transition coverage 和保守下界只用于诊断；下界不回填 strict，不计算上界。
5. **D1 映射采用全覆盖发布**：D2 可为每条观测形成
   `(observation_id, measurement_timestamp, global_track_id, truth_id)` 候选。只有全部
   estimate-available D1 观测都唯一映射时才输出 consumer records。本批
   `188951/191425` 可形成候选，完整 episode 为 `0/20`，因此未发布 sidecar。
6. **上游修复分开验收**：D1 负责跨模态门控和混轨分裂；传感器/main 负责观测全集的
   显式 truth/non-target/unknown 处置；D1 负责定义带覆盖率的部分 RMSE/NEES。D2 只在
   新证据满足唯一、完整、可审计条件后改变 strict availability。

## 三十一、离线标签处置原则（2026-07-23）

1. **处置必须由 producer 明示**：v2 sidecar 只接受 `target`、
   `known_false_alarm` 和 `unknown`。D2 不从 `vision-...-fa...` 等 observation ID、
   位置、距离、actor 名称或在线航迹状态推断虚警。
2. **身份候选只来自 target**：target 必须对应唯一 `truth_target_id`。已知虚警没有
   目标身份，不能制造 IDSW、不能进入混淆矩阵，也不能生成 D1 truth mapping。
3. **混合谱系保留可证明目标**：一个航迹帧同时包含唯一 target 和已知虚警时，target
   候选保持有效，虚警另行计数。该规则不能消除同帧两个不同 target 形成的真实混轨。
4. **纯虚警不构成身份帧**：只有已知虚警的航迹帧保留为
   `known_false_alarm_only` 审计记录，从 strict 和 partial lower-bound 分母中排除。
5. **unknown 继续失败关闭**：unknown、标签处置冲突、重复记录和时间戳不一致均阻断
   strict。partial 只报告其可证明覆盖和下界，不把未知区间补成零或上界。
6. **D1 映射单独解释**：target 记录满足唯一标签、时间和 D2 claim 后才可输出；
   known false alarm 只进入 exclusion 计数。任一 unknown 或完整性错误都会清空全部
   consumer records，防止部分 sidecar 被误当成完整误差真值。

## 三十二、身份承诺审计原则（2026-07-23）

1. **分母必须分层**：全部 v2 evidence records 用于描述状态持续性；
   `created/matched` 子集用于描述实际观测更新。两者各自公开 denominator、
   committed/uncommitted count 和 coverage，禁止混用。
2. **恢复诊断来自公开承诺 DTO**：reason、recovery blocker count、水位线和 overflow
   只从 `IdentityEvidenceCommitment` 计算。私有 blocked evidence keys 不进入评估产物。
3. **水位线年龄不可为负**：年龄固定为 frame timestamp 减
   recovery-not-before measurement timestamp。超出时间容差的负值视为合同错误。
4. **未提交状态不绑定身份候选**：未提交 evidence 和 mapping 均不得携带 source
   observation、truth candidate 或 truth target。审计中的两类 violation count 必须为 0。
5. **聚合值必须可重算**：evaluation v2 嵌入经来源哈希约束的 evidence records。loader
   从记录和帧 mapping 重算审计，拒绝缺字段或篡改值。
6. **跨空档锚点口径不变**：IDSW 继续比较未提交空档前后相邻的 committed truth
   anchors。未提交帧降低覆盖率，不成为正确身份锚点，也不切断可证明的前后比较。

## 三十三、身份承诺准入原则（2026-07-23）

1. **合同通过不等于算法准入**：clean seed 1100 已证明未提交帧不携带 source 或 truth
   candidate binding，两个违规计数均为 0，在线 truth use 为 0。这些结果只确认身份承诺
   v2 的 fail-closed 行为。
2. **准入同时检查身份和业务可用性**：baseline 的 D2 航迹、D3 分配、strict IDSW、
   track continuity 和 coverage continuity 分别为 `203/200/9/0.865/0.870`；
   candidate 的 D2 航迹和 D3 分配为 `201/197`，strict 指标 unavailable。即使承诺审计
   完整，候选也不能晋级。
3. **承诺覆盖率必须带分母解释**：candidate 全部 1787 条记录中 1714 条 committed、
   73 条 uncommitted，coverage 为 `0.9591494124`。73 条未提交记录由 69 条 active hold
   和 4 条 after hold 组成；不能只报告覆盖率而省略状态分布。
4. **固定谱系窗口不能为单个候选放宽**：三个恢复航迹的新原始雷达量测时刻为 `1.2 s`，
   评分帧为 `2.130815 s`，谱系年龄约 `0.930815 s`。它超过固定 `0.9 s` window
   `0.030815 s`，strict 指标按合同不可用。后续应修复调度、发布或评分边界，不能扩大
   window 来制造可用指标。
5. **后续未见 seed 由首个 gate seed 控制**：seed 1100 是首个预留的未见 gate seed；
   它未同时满足 strict 指标可用、D2/D3 非退化和绑定违规为 0，因此扩展 seeds
   1101/1102 停止。候选继续默认关闭。
