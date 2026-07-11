# M 对 N 多无人机协同拦截调研总报告

**日期**：2026-07-11

**范围**：高威胁目标需要多架资源协同处置时的定位、关联、联盟分配、降级接管、末端多视角配准、到达时序和评估方法。本文先汇总 D1-D7 专项调研，并记录 2026-07-11 完成的中心化闭环实现；D7 已验证 PN/PNG 核心公式未修改。

## 1. 总体结论

当前 MSM 已支持动态资源/目标数量以及中心化 M 对 N 联盟任务。目标数量与资源数量可以不相等仍不自动等同于联盟；只有显式 `TargetDemand` 才启用多资源需求。

后续应显式定义目标需求：

\[
k_j = \text{目标 }j\text{ 最少需要的有效资源数}
\]

高威胁研究基线可取 \(k_j=3\)。只有一个版本化联盟同时满足成员数量、能力、身份、时间窗和安全约束，才能认为该目标需求被满足。

跨模块一致结论如下：

1. 现有 \(k_j=1\) Hungarian、PN/PNG 和一对一视觉门控继续兼容；中心化 \(k_j>1\) 的 schema v2、原子需求槽、合法多成员锁和成员级导引门控已实现。
2. 二级/完全分布式原子联盟仍是 P1：中心失效时当前实现 fail-closed，不把单赢家 CBBA 冒充协同联盟。
3. 严格三机同时到达不是普适共识。默认研究策略采用混合 2+1：两架主资源形成安全分离的首批窗口，第三架担任 reserve/observer，根据首批结果继续、替换或退出。
4. 当逃逸窗口极短、共同到达时间可达、通信和时钟可靠、终端扇区已分离时，才考虑 simultaneous 3。
5. 当身份或航迹不确定、首批结果可及时反馈、成员机动差异大或通信退化时，优先 sequential 1+1+1 或预先计划的分波次策略。
6. 多无人机协同定位可行，但第三个视角只提供冗余，不自动提高精度。时间、位姿、外参、协方差、观测谱系和非退化交会几何必须同时成立。
7. 中心化基数需求可用 b-matching/最小费用流表达；复杂联盟、能力、同步和波次适合 CP-SAT/MILP 参考模型。普通 Hungarian 与单 winner CBBA 都不能直接表达原子 \(k_j=3\) 联盟。
8. 没有发现一个许可证清晰、维护活跃、带测试且能直接覆盖 MSM 全合同的端到端开源库。成熟开源工具应作为算法构件或隔离 benchmark，不应被描述为已经解决完整协同拦截问题。

## 2. 问题模型

设资源集合为 \(R=\{r_i\}_{i=1}^{M}\)，目标集合为 \(T=\{t_j\}_{j=1}^{N}\)，分配变量为：

\[
x_{ij}\in\{0,1\}
\]

基础需求约束为：

\[
\sum_i x_{ij}\ge k_j,\qquad \sum_j x_{ij}\le 1
\]

这只表达资源数量，不足以描述协同任务。可执行联盟还需满足：

\[
C_j=\{r_i\mid x_{ij}=1\}
\]

\[
|C_j|\ge k_j,\quad
\text{capability}(C_j)\ge q_j,\quad
\text{timing}(C_j)\in W_j,\quad
\text{safety}(C_j)=true
\]

联盟不是三个彼此独立的 assignment。它至少需要以下语义：

| 类别 | 必要字段 |
| --- | --- |
| 目标需求 | required_resource_count、required_capabilities、threat、policy |
| 联盟身份 | coalition_id、coalition_version、epoch、state |
| 成员关系 | member_resource_ids、member_role、member_ack、lease |
| 时序 | simultaneous/sequential/hybrid、arrival window、wave、reserve deadline |
| 安全 | terminal sector、minimum separation、FOV/机动可达性 |
| 计划 | plan_id、plan_version、owner、validity、superseded plan |
| 目标身份 | center-owned global_track_id、binding history、association confidence |

## 3. 三种协同策略

### 3.1 同时到达

所有主成员进入同一容差窗口：

\[
\max_i t_i^{arrival}-\min_i t_i^{arrival}\le \Delta t_{sim}
\]

适用于目标逃逸窗口短、资源机动能力接近、共同时间可达、通信和时钟可靠的场景。必须同时为成员分配不同终端扇区或进入角，并检查最小间距。

主要风险是最慢成员拖累全组、为赶时引起命令饱和或 FOV 丢失，以及多机同点进入导致碰撞和遮挡。同步时间不能替代空间安全约束。

### 3.2 序贯波次

成员按计划波次到达：

\[
t_i^{arrival}=t_0+w_i\Delta t
\]

适用于首批结果具有信息价值、目标身份仍不确定、成员性能差异较大或在线通信不可靠的场景。波次由 D3/D4 规划，D7 只执行当前有效时间窗，不能自行决定后续成员继续。

主要风险是总任务时间增加、目标在波次间机动，以及首批反馈到下一版计划的延迟。

### 3.3 混合 2+1

推荐作为下一阶段默认研究假设：

- 两架 primary 在共同但有容差的窗口进入不同终端扇区。
- 第三架 reserve/observer 保持安全时间和空间间隔，并继续提供观测。
- 首批成功时 reserve 释放；首批失败、失联或视觉关联不一致时，由 D3/D4 新版本激活 reserve。
- reserve 未实际完成需求角色时，不得被统计为已满足的第三个资源槽。

这一策略兼顾高威胁覆盖、协同观测和终端安全，但仍需通过质点模型和 AirSim 多 seed 验证，不能写成行业唯一默认。

## 4. 端到端协同链路

### 4.1 D1：多平台观测与协同定位

每个平台在量测时刻提供 NED 位姿、传感器外参、观测、协方差、measurement timestamp、arrival timestamp 和 source lineage。观测先传播到共同估计时刻，再进行联合滤波或保守航迹融合。

两条不平行视线理论上可三角定位，第三条视线用于提高冗余和抗遮挡。系统必须检查联合雅可比/Fisher 信息矩阵秩与条件数、交会角、基线距离比、重投影误差以及位姿和时间误差传播。几何退化时应增大协方差或拒绝融合。

中心获得原始观测时，优先使用观测级 EKF/UKF/信息滤波。只能交换局部航迹且交叉相关未知时，使用 Covariance Intersection 作为保守对照，并防止共享先验和 relay 消息被重复计数。

### 4.2 D2：跨平台航迹对应和规范身份

多架无人机看到同一目标，应表示为一个 canonical global track 对多个 source tracklet，而不是生成多个目标。

处理顺序为：

1. 各局部航迹传播到公共时刻。
2. 使用带协方差的 track-to-track 马氏门控和 GNN/Hungarian 做低歧义对应。
3. 密集交叉时以 JPDA/MHT 作为可插拔歧义管理。
4. 已知交叉协方差时做相关融合；未知相关时使用 CI；发现重复谱系时拒绝再次融合。
5. 中心 registry 维护 source-local ID 到 global_track_id 的绑定历史。

D1 负责数值融合和不确定性传播，D2 负责身份对应、canonical registry、公共信息治理和 id_switch_count。两者不能互相替代。

### 4.3 D3：中心化联盟分配和时序调度

当前 Hungarian 继续处理 \(k_j=1\)。对只有基数需求、边代价可加的问题，首选 b-matching 或最小费用流：

\[
\min \sum_{i,j} C_{ij}x_{ij}
\]

并显式输出 required、assigned、shortfall 和 coalition complete。

若问题包含能力互补、联盟原子启用、主备角色、同步窗口、波次、碰撞和滚动冻结，应使用 CP-SAT/MILP 参考模型。近期应同时比较：

- simultaneous 3
- sequential 1+1+1
- hybrid 2+1
- independent PN baseline

联盟变更必须递增 plan/coalition version，冻结已执行波次，只重排未提交后缀。合法多资源绑定不得计入 duplicate assignment。

### 4.4 D4：中心、二级节点与无中心联盟维护

中心正常时，D3 生成联盟，D4 维护健康、lease、epoch 和执行证据。中心失效但二级侦察节点可用时，二级节点根据缓存态势发布新的 coalition version，并在区域 reserve pool 中补位。

中心和二级节点均不可用时，基础 CBBA 只能继续作为单 winner 或候选成员选择基线。把同一目标复制成三条 CBBA task 不能保证原子联盟。完全分布式路径需要对 coalition id、成员、需求、能力、时序、ACK、lease 和 state 达成一致。

成员退出时按以下顺序处理：

- 剩余成员仍满足最低需求和能力：新版本缩编继续。
- 有满足时间窗的 reserve：补位并要求全体重新 ACK。
- 需求或共同窗口不再满足：释放旧 coalition lease，进入新 epoch 重组。
- 网络分区无法唯一裁决：hold/observe，不允许并行发布两个联盟。

### 4.5 D5：末端多视角配准和合法协同锁定

ByteTrack/BoT-SORT 只维护单相机 local track。跨相机仍需把 GlobalTrack 按量测时刻和相机位姿投影到各图像平面，结合像素马氏距离、时间、角速度、类别、外观和计划绑定进行匹配。

多机协同定位不能直接平均 bbox 中心。至少需要相机内参、畸变、量测时刻外参和协方差，以及具有足够交会角的多条视线。序贯帧必须做目标和相机运动补偿。

当以下条件同时成立时，多架资源锁定同一 global_track_id 属于 planned cooperative lock：

- 资源属于同一有效 coalition；
- plan/version、member role 和 arrival slot 一致；
- 每个资源只提交唯一 local track 支持；
- 支持均指向同一中心拥有的 global_track_id；
- 时间、几何、稳定窗口和友方身份门控均通过。

计划外资源加入、一个资源多 local lock、一个 local track 支持多个 global ID、过期计划或几何冲突仍属于 duplicate/conflict。支持数超过需求时应报告 over support，由 D3/D4 仲裁，D5 不自行解绑或改写 global_track_id。

### 4.6 D7：协同到达和成员级导引

多个成员各自运行 PN/PNG，只是独立 pair，并非协同导引。真正的同步协同至少需要共享或协调 time-to-go、共同到达窗口、终端进入方向或最小安全间距。

现有位置 PN 和 TTC 捷联视觉 PNG 公式保持不变。后续研究应在其上层增加：

- coalition-level arrival window 或 wave schedule；
- 每个成员独立的 D3/D4/D5 gate；
- 不同 terminal sector/impact angle；
- 最小成员距离和命令饱和检查；
- 成员失联、未锁定或窗口不可达时的重规划请求。

任何一个成员 locked 不能让全联盟自动切换视觉 PNG。同步模式应要求所有 primary 在同一有效 epoch 内 ready；混合模式允许未 ready 成员转 reserve，但必须由新版本计划授权。

### 4.7 D6：评估

评估不能只统计命中率。统计单位扩展为 episode、target、coalition/version、wave、member/link/frame，并始终区分 unavailable、zero 和 not applicable。

| 维度 | 核心指标 |
| --- | --- |
| 需求 | target demand satisfaction、unmet slots、over support |
| 联盟 | formation/reconfiguration time、member loss、replacement、digest conflict |
| 时序 | simultaneous dispersion、common-window success、wave interval/order、reserve activation |
| 定位 | RMSE、NIS/NEES、covariance consistency、geometry rejection |
| 身份 | canonical duplicate、cross-node ID switch、common-information duplicate rejection |
| 末端 | planned cooperative lock、erroneous duplicate lock、friend/geometry conflict |
| 通信 | messages、bytes、rounds、end-to-end latency、measurement age |
| 安全 | minimum member separation、collision-risk exposure、constraint violation |

需求满足率只计算处于当前 plan/version、lease 有效且能力/角色合格的成员。reserve 永久等待不能计入已满足槽位。没有 target demand、arrival、truth、covariance 或 lineage 证据时，相应指标必须是 unavailable，不能用零代替。

四种路线必须使用相同 scenario version、初始几何和 paired seeds，并分别覆盖中心正常、二级接管和完全无中心，以及良好/退化几何、同步/异步、正常/退化通信和成员失效。详细公式、输入事件和十二组合实验矩阵见 D6 专项报告。

## 5. 开源算法与实现成熟度

| 能力 | 成熟构件/基线 | 可插拔或研究候选 | 结论 |
| --- | --- | --- | --- |
| 滤波与保守融合 | Stone Soup、FilterPy | GTSAM 动态因子图、GCI/RFS | 有成熟构件，无完整协同定位系统 |
| 几何与标定 | OpenCV、GTSAM | 主动几何优化 | 几何原语成熟，时间/位姿协方差需 MSM 补合同 |
| 跨平台航迹关联 | Stone Soup GNN/JPDA/MHT benchmark | labeled RFS、GCI/AA | 无现成 canonical registry 和公共谱系 |
| 基数需求分配 | OR-Tools Min Cost Flow、NetworkX | b-matching 网络变换 | 能表达 \(k_j\)，但不原生表达复杂联盟原子性 |
| 联盟和时序 | OR-Tools CP-SAT、Pyomo/PuLP | MRTA/coalition research repositories | 建模工具成熟，端到端联盟算法无统一默认 |
| 分布式协商 | MIT CBBA MATLAB、zehuilu/CBBA-Python | CCBBA、CBBA-PR、grouping/CNP | 基础 CBBA 不支持原子 \(k_j>1\) |
| 本地 MOT | ByteTrack | BoT-SORT、Deep SORT | 只提供 local ID，不负责 global identity |
| 多视角关联 | OpenCV 投影门控 | ReST、3D-Visual-MOT、MVDet | 研究实现可用，空中机动目标域仍需验证 |
| 协同导引 | 单机 PN/PNG、单机 ITCG 对照 | impact-time consensus、prescribed-time guidance | 未发现成熟多旋翼开源 cooperative guidance 库 |

特别纠正：

- github.com/mit-acl/cbba-python 不存在，不能再称为 MIT 官方实现。
- mit-acl/CACBBA 当前只有 README，没有可运行源码或许可证，不能列为可接入依赖。
- 多个 cooperative guidance 仓库未声明许可证，只能用于证据核对，不能复制进 MSM。
- 开源优化器、滤波器和 MOT 只能解决子问题，不能据此宣称 M 对 N 全链路已经实现。

## 6. 当前实现状态与缺口分级

### 6.1 已实现并保持回归

- 动态资源/目标数组，不把 2v2 或 5v5 写死为算法上限。
- D1 协同方位定位、共同时间传播、协方差膨胀、CI 和 source lineage 去重。
- D2 跨节点 `SourceTrackSummary`、马氏/Hungarian 注册、canonical registry 和 ID 指标。
- D3 schema v2、`TargetDemand`、all-or-none demand-slot Hungarian、hybrid 2+1、联盟版本和迟滞。
- D4 中心联盟校验和中心失效 fail-closed；\(k_j=1\) 的三级降级保持兼容。
- D5 联盟只读合同、planned cooperative lock、over-support/version 冲突和 reserve 门控。
- D6 demand/coalition/arrival 记录及 M 对 N 指标可用性语义。
- D7 任意 resource-target pair 的 role/wave/window/version 门控；PN/PNG 核心公式未改。
- main 支持独立 `--resource-count/--target-count`、协同需求参数、5v2 总线和 3v1/5v2 质点场景。

### 6.2 P0 判断

中心化 \(k_j>1\) 的原 P0 合同已闭合，\(k_j=1\) 回归保持通过。二级或完全分布式节点当前不能原子形成联盟，但已通过 `coalition_fallback_unsupported` fail-closed，因此属于明确的能力边界而不是静默安全断链。

### 6.3 P1 研究与合同缺口

1. D1/D2 能力接入真实 AirSim 多节点观测，并标定共同时间、几何退化、CI 请求和跨节点 ID 阈值。
2. D3 增加 CP-SAT/MILP 复杂约束参考；OR-Tools Min Cost Flow 继续作为可选 benchmark。
3. D4 实现二级/完全分布式 coalition commit、ACK、lease、成员缩编/补位/重组和恢复 digest。
4. D5 标定真实多视角三角定位、跨视角 MOT/投影门和协同身份；保持 truth ID 在线隔离。
5. D7 增加同步到达可达性、终端扇区、最小成员距离和成员失效重规划证据。
6. D6 在真实多 seed episode 中积累 arrival、成员损失/替换、通信和安全指标证据。

## 7. 推荐验证顺序

中心化合同和质点/接口基线已完成，后续验证顺序为：

1. 质点模型中固定一个 \(k_j=3\) 目标，比较 independent PN、simultaneous 3、sequential 1+1+1、hybrid 2+1。
2. 加入良好/退化观测几何、同步/异步量测、不同目标机动和公共先验，验证 RMSE/NEES 与拒绝逻辑。
3. 加入成员失联、reserve 补位、中心失效、二级接管和网络分区，验证 coalition epoch/lease。
4. 加入终端扇区、最小间距、视觉锁定和计划外第四资源，验证安全与 duplicate 语义。
5. 先以 OR-Tools/NetworkX/Stone Soup/OpenCV 做隔离 benchmark，再决定是否进入主线依赖。
6. 运行 AirSim ComputerVision 5v2 接口多 seed，再进入 SimpleFlight 3v1/5v2 长时飞行；分布式联盟在 D4 原子协议完成前只验证 fail-closed。

## 8. 子模块报告索引

- D1：subagent_reviews/D1_M_TO_N_COOPERATIVE_LOCALIZATION_REVIEW.md
- D2：subagent_reviews/D2_M_TO_N_TRACK_FUSION_REVIEW.md
- D3：subagent_reviews/D3_M_TO_N_ASSIGNMENT_AND_SCHEDULING_REVIEW.md
- D4：subagent_reviews/D4_M_TO_N_DISTRIBUTED_COALITION_REVIEW.md
- D5：subagent_reviews/D5_M_TO_N_TERMINAL_MULTIVIEW_REVIEW.md
- D6：subagent_reviews/D6_M_TO_N_EVALUATION_FRAMEWORK_REVIEW.md
- D7：subagent_reviews/D7_M_TO_N_COOPERATIVE_GUIDANCE_REVIEW.md

## 9. 证据边界

本轮各模块合计核验了同行评审论文、arXiv 原稿、官方仓库和项目页面。Google Scholar 只作为发现入口，最终结论回到 DOI、arXiv、出版社或官方仓库。当前环境没有 Web of Science 机构订阅或导出文件，因此没有声称完成 WOS 引文网络或分区核验。

“未发现成熟开源实现”表示在本轮检索范围内没有找到同时满足许可证、维护、测试、任务模型和 MSM 合同要求的实现，不表示相关算法没有学术价值，也不表示作者不存在私有代码。
