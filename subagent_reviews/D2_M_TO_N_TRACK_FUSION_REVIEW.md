# D2 M 对 N 协同拦截中的跨平台航迹关联与航迹级融合调研

**调研范围**：面向“一个高威胁目标由多架拦截无人机共同承担”的 M 对 N 协同拦截场景，研究同一物理目标被中心节点、二级侦察节点和多个拦截节点重复观测时，D2 如何识别同目标航迹、抑制重复建轨和公共信息双重计数，并保持中心拥有的 `global_track_id` 连续性。

**调研性质**：第 1-8.4 节保留文献与开源实现审计结论；第 8.5、11-13 节同步截至 2026-07-20 的 D2 后续实现与验证状态，不把论文能力、detection-to-track 能力和 cross-node track fusion 能力混淆。

**检索日期**：2026-07-11。

## 1. 结论摘要

1. **多个无人机观测同一目标，不等于出现多个目标。** 每个平台产生的是带命名空间的局部航迹或 tracklet；D2 必须先做跨平台航迹关联，再决定这些局部航迹是否共同指向一个中心 `global_track_id`。D3 的目标需求 `k_j=3` 表示三架资源承担同一个目标任务，不能据此复制三条全局目标航迹。
2. **航迹关联和航迹融合是两个不同步骤。** 先根据时间对齐后的状态、协方差、运动一致性、来源和可用的类别/外观证据建立对应关系；只有关联置信度足够，才融合状态。关联不确定时应保留候选或延迟决策，不能先融合再用融合结果证明关联。
3. **已知互相关时，使用带交叉协方差的最优航迹融合；互相关未知时，Covariance Intersection（CI）是成熟保守基线。** CI/GCI 可以避免未知公共信息被重复计数，但通常比掌握真实交叉协方差的最优融合更保守。
4. **CI 不能解决身份对应问题。** 两条航迹是否属于同一物理目标仍需 track-to-track association。对多个相邻高威胁目标，错误对应会把不同目标融合成一条；漏对应则会让同一目标形成重复全局航迹。
5. **带标签 RFS/GCI 是有价值的研究升级路线，但标签空间不一致是已知难点。** 不同节点独立生成的本地 label 数值相同也不代表同一目标，数值不同也不代表不同目标。文献表明直接融合不一致标签可能造成严重性能退化。
6. **D1 与 D2 的边界应保持稳定。** D1 负责原始/观测级异构传感器融合和单一融合工作空间中的 `GlobalTrack` 生成；D2 在存在多个独立本地跟踪器输出时，负责航迹到航迹对应、公共信息治理、全局身份连续性和保守航迹融合。不能让 D2 再次无条件融合已经由 D1 融合过的同源信息。
7. **时间组织推荐混合模式。** 各节点连续本地跟踪，按周期或事件向中心/二级节点发布航迹摘要；融合端按 `measurement_timestamp` 预测到公共融合时刻后批处理关联和融合。全同步批融合适合基准实验；纯序贯逐条融合对网络顺序和重复消息更敏感。
8. **当前项目已实现跨平台注册基础，但未实现数值 track fusion。** D2 后续新增 source-track DTO、公共时刻 track-to-track Hungarian、canonical multi-source registry、相关性谱系防重与融合请求；unknown correlation 只请求 D1 执行 CI，D2 不计算 CI posterior。

## 2. 问题定义

### 2.1 M 对 N 中的“多资源”和“多目标”必须分开

设物理目标集合为

\[
\mathcal{X}=\{X_1,\ldots,X_N\},
\]

拦截资源集合为

\[
\mathcal{R}=\{R_1,\ldots,R_M\}.
\]

目标需求 `k_j` 表示目标 `X_j` 需要多少资源协同承担。若 `k_j=3`，D3 可以把三架资源分给同一个 `global_track_id`，但 D2 的全局目标基数仍是一个。每个节点 `s` 对该目标产生的本地航迹应写作：

\[
T^{(s)}_a = (s,\ell_a,\hat{x}^{(s)}_a,P^{(s)}_a,t_m,t_a,\mathcal{L}^{(s)}_a),
\]

其中 `s` 是来源节点，`\ell_a` 是只在该节点命名空间内有效的 local track ID，`P` 是协方差，`t_m/t_a` 分别是量测时间和到达时间，`\mathcal{L}` 是信息来源谱系。D2 的任务是估计：

\[
T^{(s_1)}_a \sim T^{(s_2)}_b \Longleftrightarrow
\text{两条本地航迹代表同一物理目标}。
\]

只有这个对应关系成立，才允许把它们登记到同一个中心 `global_track_id` 下。

### 2.2 两阶段处理链

```text
local tracks from center / secondary / interceptors
  -> schema and provenance validation
  -> predict all tracks to a common fusion epoch
  -> cross-node track-to-track gating
  -> assignment or multi-hypothesis association
  -> common-information/correlation policy selection
  -> conservative state fusion
  -> canonical global_track_id registry update
  -> duplicate-track and ambiguity evidence
```

第一阶段解决“是不是同一目标”；第二阶段解决“若是同一目标，如何组合状态而不虚假变得过度确定”。

## 3. D1 观测融合与 D2 航迹融合边界

| 项目 | D1 观测级融合 | D2 航迹级融合 |
| --- | --- | --- |
| 输入 | 雷达点迹、声学方位、EO 像素框、LiDAR 等原始或近原始观测 | 不同节点独立滤波后发布的 local track/tracklet summary |
| 主要问题 | 异步时间、坐标变换、非线性量测、距离/遮挡相关协方差 | 同目标跨节点对应、公共信息、未知互相关、全局身份连续性 |
| 默认方法 | EKF/UKF 原型、统一 NED、延迟/OOSM 治理 | track-to-track GNN/Hungarian + 已知相关融合或 CI 保守融合 |
| 身份权威 | 提供候选全局航迹状态，不允许传感器局部 ID 成为全局真值 | 中心维护 canonical `global_track_id`；local ID 仅作来源键 |
| 主要失败 | 坐标/时间错误、协方差失配、重复使用同一原始观测 | 错误合并、重复全局航迹、公共信息双重计数、跨节点 ID switch |

边界规则：

- 如果多个传感器的原始观测已经由同一个 D1 实例联合更新了同一航迹，D2 不应把该融合航迹再与其原始分支航迹无谱系地融合。
- 如果中心、二级节点和拦截机运行相互独立的本地 tracker，D2 才执行跨平台 track-to-track association/fusion。
- `source_node_id + local_track_id` 是本地航迹键；`global_track_id` 是中心规范键。任何节点不得把本地 label 直接声明为规范 ID。
- D5 跨视角视觉证据可以增加或降低关联置信度，但不能越过 D2 的规范身份注册表直接重绑 `global_track_id`。

## 4. 算法原理和实施思路

### 4.1 时间对齐与跨节点航迹门控

不同节点航迹到达时间不同，不能直接比较到达时的状态。应根据每条航迹的 `measurement_timestamp` 将状态和协方差预测到公共融合时刻 `t_f`：

\[
\hat{x}^{(s)}(t_f)=F(t_f-t_m)\hat{x}^{(s)}(t_m),
\]

\[
P^{(s)}(t_f)=F P^{(s)}(t_m)F^T+Q(t_f-t_m).
\]

对来自不同节点的候选航迹计算创新：

\[
r_{ab}=H_a\hat{x}_a-H_b\hat{x}_b,
\]

再按已知或保守近似的差分协方差构造门控距离。若未知两条航迹的交叉协方差，门控不能假装两者独立；工程上可先采用膨胀协方差或 CI 一致的保守距离，并把未知相关性写入证据字段。

跨节点代价至少包含：

- 公共时刻位置/速度的马氏距离；
- 航向、速度和加速度历史一致性；
- 时间新鲜度和预测跨度；
- 来源节点、坐标变换和协方差健康状态；
- 可用的类别、声纹、视觉 embedding 或 Remote ID 正向证据；
- 已有 canonical binding 的连续性代价，防止每帧重新编号。

低歧义场景可使用 GNN/Hungarian 做节点间一对一对应；交叉或多个候选共享门限时，JPDA 可保留边缘关联概率，MHT 可延迟多帧裁决。此处的 JPDA/MHT 解决的是跨节点局部航迹对应，不是把多个资源分配给多个目标。

### 4.2 已知互相关的航迹融合

若系统保存了完整信息来源谱系、滤波增益和交叉协方差 `P_12`，可以使用考虑交叉相关的 track-to-track fusion。该路线信息利用率高，但要求严格维护公共过程噪声、重复消息和历史融合关系；在多跳网络和中心/二级切换中通常难以完整获得。

因此，本项目不能仅凭“两个节点不同”就假设估计独立。它们可能共同使用中心雷达 cue、相同 D1 航迹、相同过程模型，或相互转发过历史融合结果。

### 4.3 未知互相关的 Covariance Intersection

对两个高斯航迹 `(x_1,P_1)`、`(x_2,P_2)`，CI 使用：

\[
P_{CI}^{-1}=\omega P_1^{-1}+(1-\omega)P_2^{-1},
\]

\[
\hat{x}_{CI}=P_{CI}\left[\omega P_1^{-1}\hat{x}_1+(1-\omega)P_2^{-1}\hat{x}_2\right],
\quad \omega\in[0,1].
\]

`omega` 通常通过最小化 `trace(P_CI)`、`det(P_CI)` 或其他一致性目标选择。CI 的优势是不需要知道交叉相关即可保持保守一致；代价是可能丢失一部分可用信息。CI 只应在航迹已被判定为同一目标后执行。

### 4.4 公共信息去重和融合谱系

公共信息可能来自：

- 多节点使用同一中心雷达航迹初始化；
- 二级节点把融合结果广播给拦截机，拦截机再次回传；
- 同一视频/雷达观测被多个节点处理后回流；
- 中心与二级节点曾互相融合，恢复后又重新交换完整 posterior。

成熟处理思路分三层：

1. **相关性已知**：维护交叉协方差或信息增量，做精确/近精确融合。
2. **相关性未知**：CI/GCI 等保守融合，避免协方差虚假收缩。
3. **公共信息可追踪**：维护 lineage、message UUID、source epoch、parent fusion IDs，先剔除重复信息增量，再融合新增信息。

CI 可以降低未知相关导致的不一致，但不能替代消息去重和谱系。若同一融合结果无限循环，系统仍会浪费带宽和计算，并可能产生身份层面的重复解释。

### 4.5 标签不一致与全局身份连续性

2017 年 Robust Distributed Fusion with Labeled RFS 指出，GCI 对不同节点的 label consistency 高度敏感。工程上应采用：

- local ID 始终命名空间化，例如 `(node_id, local_track_id, local_epoch)`；
- canonical registry 维护 `global_track_id -> source_track_bindings[]`；
- 先按无标签运动/类别证据确认同目标，再更新全局 binding；
- 对不一致 label 不做数值相等判断；
- 关联模糊时保留候选图或延迟确认，不把多个局部航迹立即折叠；
- 全局 ID 只由中心或当前合法二级 owner 更新，完全分布式时使用带 epoch/owner 的临时共识 ID，中心恢复后保守合并。

多个节点合法观测同一 `global_track_id` 不应增加 `duplicate_assignment_count`。应新增或派生另一类指标：同一物理目标被错误维护为多个 canonical IDs 的 `duplicate_global_track_count`。前者描述资源/观测分配冲突，后者描述航迹注册错误，不能混用。

## 5. 同时、序贯和混合融合方式

| 方式 | 定义 | 优点 | 主要风险 | D2 建议 |
| --- | --- | --- | --- | --- |
| 同时批融合 | 将多个节点航迹预测到同一 `fusion_epoch`，统一关联后批量融合 | 顺序影响小，便于一致门控和全局冲突消解 | 需要等待窗口，慢节点会增加延迟 | 作为离线基准和中心节点高质量窗口 |
| 序贯融合 | 航迹一到达就逐条关联、融合 | 延迟低、实现简单 | 对到达顺序、重复消息和未知相关更敏感；pairwise CI 权重治理复杂 | 只用于低歧义、来源谱系完备的快速更新 |
| 混合模式 | 本地 tracker 连续运行，按周期/事件发布摘要；融合端按短窗口批关联并滚动更新 | 兼顾实时性、通信和全局一致性 | 需要窗口、epoch、stale message 和 replay 治理 | **推荐默认研究路线** |

这里的同时/序贯是信息融合时序，不是 D7 的多机同时到达拦截。D2 只给 D3/D7 提供带时间和协方差的一致目标状态；是否同时到达或分批拦截由 D3/D7 决定。

## 6. 主要论文证据

### 6.1 核心论文对比

| 年份 | 论文与原始来源 | 问题和方法 | 架构 | 融合时序 | 验证方式 | 官方代码 |
| --- | --- | --- | --- | --- | --- | --- |
| 1997 | Julier, Uhlmann, [A non-divergent estimation algorithm in the presence of unknown correlations](https://doi.org/10.1109/ACC.1997.609105) | 未知互相关下的一致状态估计，奠定 CI 基线 | 分布式/去中心 | 成对或批式均可 | 理论与数值示例 | 未发现官方仓库 |
| 2015 | Kamal et al., [Distributed Multi-Target Tracking and Data Association in Vision Networks](https://doi.org/10.1109/TPAMI.2015.2484339) | 视觉网络中的分布式多目标跟踪、跨相机关联与身份维护 | 分布式视觉网络 | 混合：本地连续跟踪、跨节点协作 | 多摄像机数据/实验 | 未发现论文官方仓库；[开放稿](https://escholarship.org/uc/item/6cq1w8t4) |
| 2016 | Wang et al., [Distributed Fusion With Multi-Bernoulli Filter Based on GCI](https://doi.org/10.1109/TSP.2016.2617825) | 未知相关下融合 MB posterior；GMB 近似后回投 MB | 分布式多传感器 | 迭代/序贯多节点融合 | SMC 数值仿真 | 未发现官方仓库；[arXiv](https://arxiv.org/abs/1603.08340) |
| 2017/2018 | Li et al., [Robust Distributed Fusion With Labeled Random Finite Sets](https://doi.org/10.1109/TSP.2017.2760286) | 揭示 label inconsistency 导致 GCI 退化；先无标签融合，再重建标签 | 分布式 | 共识/混合 | 挑战场景数值实验 | 未发现官方仓库；[arXiv](https://arxiv.org/abs/1710.00501) |
| 2018/2019 | Li, Corchado, Sun, [Partial Consensus and Conservative Fusion of Gaussian Mixtures for Distributed PHD Fusion](https://doi.org/10.1109/TAES.2018.2882960) | 只交换高权重 GM 分量；Hungarian 对应后做保守算术融合/合并 | P2P 分布式 | 共识迭代 | 单/多目标传感器网络仿真 | 未发现官方仓库；[arXiv](https://arxiv.org/abs/1711.10783) |
| 2018/2019 | Li et al., [Computationally Efficient Multi-Agent Multi-Object Tracking With Labeled RFS](https://doi.org/10.1109/TSP.2018.2880704) | 降低多智能体 labeled-RFS 融合的通信和计算成本 | 多智能体分布式 | 混合/迭代 | 数值多目标实验 | 未发现官方仓库 |
| 2019/2020 | G. Li et al., [Distributed Multi-sensor Multi-view Fusion Based on GCI](https://doi.org/10.1016/j.sigpro.2019.107246) | 不同 FoV 下先聚类；共同目标并行 GCI，非共同目标做补偿 | 分布式多视角 | 批式+滚动 | GM-PHD 数值实验、L1 误差分析 | 未发现官方仓库；[arXiv](https://arxiv.org/abs/1903.06985) |
| 2019 | T. Li et al., [Second-order Statistics Analysis and Comparison Between Arithmetic and Geometric Average Fusion](https://doi.org/10.1016/j.inffus.2019.02.009) | 比较 AA/GA 在变量、PDF 和多目标 GM 下的方差/MSE，不宣称单一融合规则普遍最优 | 通用分布式 | 批式/共识 | 理论推导与示例 | 未发现官方仓库；[arXiv](https://arxiv.org/abs/1901.08015) |
| 2020 | T. Li et al., [On Arithmetic Average Fusion and Its Application for Distributed Multi-Bernoulli Multitarget Tracking](https://doi.org/10.1109/TSP.2020.2985643) | Bernoulli-to-Bernoulli 对应后做 AA；比较 consensus/flooding 和通信成本 | 分布式 | 共识或 flooding 混合 | 两个仿真场景 | 未发现官方仓库 |
| 2020 | Gao, Battistelli, Chisci, [Fusion of Labeled RFS Densities With Minimum Information Loss](https://doi.org/10.1109/TSP.2020.3028496) | 处理 labeled density 融合的信息损失与标签空间问题 | 分布式/多智能体 | 批式或共识 | 理论与数值多目标实验 | 未发现官方仓库；[arXiv](https://arxiv.org/abs/1911.01083) |
| 2023 | W. Li, Yang, [Information Fusion over Network Dynamics with Unknown Correlations: An Overview](https://doi.org/10.53941/ijndi0201003) | 综述完全/部分未知相关、CI 类方法、consensus/diffusion 和多目标融合 | 中心/分布式综述 | 同时、序贯、混合均覆盖 | 综述 | 无配套代码；[开放 PDF](https://www.sciltp.com/journals/ijndi/article/download/184/105) |

### 6.2 证据解释

- CI/GCI 是“相关性未知时保持一致性”的成熟方法族，不是跨平台身份关联的完整解法。
- 2016-2020 年 RFS 文献证明，多目标 posterior 可以在分布式网络中做保守融合，但实际应用需处理 label mismatch、FoV 不重叠、漏检和通信预算。
- AA、GA/GCI 和 minimum-information-loss 路线各有适用条件；目前没有证据支持所有 C-UAS 场景只采用一个融合规则。
- JPDA/MHT 仍适合关联歧义管理；CI/GCI 负责融合相关性，两者解决的问题不同，可以串联而不是二选一。

## 7. 开源实现候选

| 项目 | 可复用能力 | 许可证与维护状态 | 成熟度判断 | MSM 适配难点 |
| --- | --- | --- | --- | --- |
| [dstl/Stone-Soup](https://github.com/dstl/Stone-Soup) | `TrackToTrackCounting`、一对一航迹关联、JPDA/MHT 示例、`Tracks2GaussianDetectionFeeder`、`ChernoffUpdater` CI 航迹融合示例、OSPA/SIAP 指标 | MIT；官方仓库截至 2026-07-07 仍有提交 | **成熟研究框架，首选离线 benchmark** | Stone Soup 对象不能泄漏到总线；需映射 MSM timestamp/covariance/source lineage/global ID；示例不直接提供 canonical registry 或公共信息谱系 |
| [jonassagild/Track-to-Track-Fusion](https://github.com/jonassagild/Track-to-Track-Fusion) | Python/Stone Soup 航迹融合；比较独立误差、考虑相关性和“track as measurement”；含 250 次 Monte Carlo ANEES 输出 | MIT；最后提交 2021-05-03；依赖 Stone Soup `0.1b1`、NumPy 1.19、SciPy 1.5 | **可读研究样例，不是生产库** | 依赖老旧；单项目论文原型；需要重写数据合同、动态节点数、身份注册和现代测试 |
| [KIT-ISAS/data-fusion](https://github.com/KIT-ISAS/data-fusion) | Python CI、Ellipsoidal Intersection、Inverse CI 和双节点 Kalman 网络仿真 | 仓库未发现明确 LICENSE；最后提交 2018-06-29 | **算法参考，不建议直接复用** | 缺许可证、缺多目标身份和航迹关联、维护停止 |
| [linh-gist/labeledRFS](https://github.com/linh-gist/labeledRFS) | Python GLMB/LMB、多传感器 Gibbs 采样、视觉 RFS 相关实现 | MIT；最后提交 2024-10-18 | **研究型 labeled-RFS 对照** | 不是现成分布式 track-to-track CI；状态/量测模型和计算预算与 MSM 差异大 |

Stone Soup 是唯一同时覆盖航迹关联、CI 航迹融合、多目标 tracker 和评估工具的成熟候选。第二个直接候选 `Track-to-Track-Fusion` 更适合用于核对公式和 ANEES 实验，不应作为默认运行依赖。FilterPy 没有现成的跨平台航迹对应、公共信息治理或 CI 全链路，因此不列为本专项的直接开源实现。

## 8. 方案分级与本项目状态

### 8.1 成熟默认方案

- 所有 local track 先预测到公共融合时刻。
- 使用带协方差的 track-to-track gating + GNN/Hungarian 做低歧义对应。
- 已知交叉协方差时使用相关 track fusion；未知相关时使用 CI。
- local ID 命名空间化，中心注册并维护 canonical `global_track_id`。
- 记录来源谱系、消息 UUID、fusion epoch 和 parent fusion IDs，拒绝重复信息循环。

### 8.2 可插拔升级

- 交叉/密集阶段用 JPDA 保留关联概率，或用 MHT 延迟裁决。
- 多节点 posterior 融合可对照 GCI、AA、partial consensus。
- 不同 FoV 使用聚类、共同 FoV 融合和非共同目标补偿。

### 8.3 研究型方案

- GLMB/LMB 等 labeled-RFS 分布式融合。
- minimum-information-loss 标签融合。
- 自动在精确相关融合、CI、AA/GCI 间选择。
- 完全分布式 canonical identity consensus。

### 8.4 尚无成熟开源完整实现

未发现一个许可证清晰、持续维护、可直接提供以下完整组合的仓库：

```text
MSM DTO
+ asynchronous timestamp alignment
+ cross-node track association
+ common-information lineage
+ CI/exact correlated fusion
+ center-owned global identity registry
+ JPDA/MHT ambiguity handling
+ D6 IDSW/duplicate-global-track evaluation
```

因此应把 Stone Soup 用作隔离 benchmark，而不是直接替换 D2 默认 GNN/Hungarian 主线。

### 8.5 本项目当前状态

**已实现基础（2026-07-11 同步）**：

- detection-to-track GNN/Hungarian、马氏门控、motion consistency、quality-aware gate；
- `source_node_id`、`link_type`、association risk 等基础字段；
- 在线 truth 隔离和中心生成的 `global_track_id`；
- JPDA/MHT 轻量研究对照。
- 6D NED `SourceTrackSummary`，含 source/local/epoch namespace、measurement/arrival timestamp、covariance、quality、lineage/correlation status 和 canonical hints；在线合同无 truth；
- `CrossNodeTrackAssociator` 公共时刻 CV 传播、covariance-aware Mahalanobis gate 和按 source Hungarian；
- `CrossNodeTrackRegistry` 中心连续 ID 分配、one canonical-to-many source binding/history、payload/lineage/stale 防重；
- exact-known correlation 请求相关融合，unknown correlation 只请求 CI，duplicate information 拒绝；
- truth-free cross-node rebind/duplicate/latency 指标与隔离 offline canonical duplicate、association precision/recall、truth-based cross-node IDSW。

**当前 P1 合同证据（2026-07-11 最终验证）**：

- D1 governed input、D2 online truth isolation/offline evaluator、中心 `global_track_id` 和 N-target/10-seed runner 的 D2-owned 合同已闭合；
- M=5、N=2 ComputerVision 10-seed 中，T001 双 primary 共识/当前计划授权为 8/10，D2 `id_switch_count=0`、错误 duplicate=0、`global_track_id` 改写/重绑=0 均为 10/10；
- 二级和完全分布式 coalition commit 正例通过，缺 ACK 时 fail-closed。这证明 D4-D7 能沿用 D2 中心 ID 执行合同，不等于 D2 已实现二级 owner/epoch failover 或分布式临时 ID 合并；
- SimpleFlight 15 s 只是诊断，30 个 active pair 无命中，物理拦截未闭合。

**后续研究仍未实现**：

- D1-owned 数值 CI 或已知交叉协方差融合 posterior 回写；
- 高歧义跨节点 JPDA/MHT 和延迟决策；
- 二级 owner/epoch failover 与完全分布式临时 ID 合并；
- fusion NEES/ANEES、通信字节和 D1/D6 多 seed 一致性标定；
- 同时/序贯/混合 replay 的多 seed 对照。

这些缺口不影响现有单中心 D1->D2 detection-to-track 主线或当前 P1 合同闭合结论。

## 9. 推荐给后续系统拆解的 D2 子任务

1. **合同研究（已闭合基础）**：`SourceTrackSummary` 已包含 source/local ID、epoch、两个 timestamp、6D NED 状态/协方差、frame、quality、lineage、correlation status 和 canonical hints。
2. **关联研究（已闭合 baseline）**：已固定公共时刻预测、track-to-track 马氏门控和按 source Hungarian；JPDA/MHT 高歧义对照保留。
3. **融合研究（决策已闭合，数值未闭合）**：已按 `exact_known_correlation / unknown_correlation / duplicate_information` 输出 exact request、CI request 或拒绝；数值融合由 D1 接续。
4. **身份治理研究（中心基础已闭合）**：已实现 canonical registry 和 binding history；二级 owner 与完全分布式临时 ID 权限/epoch 保留。
5. **评估研究（部分闭合）**：已实现 canonical duplicate、cross-node IDSW、关联精确率/召回率、重复拒绝和融合延迟；fusion ANEES/NEES、通信字节待 D1/D6 对齐。
6. **开源 benchmark**：Stone Soup 独立环境对照 track-to-track association + CI；不修改默认 bus，不把老旧论文仓库引入生产依赖。

## 10. 检索与证据限制

- 论文元数据通过 DOI 原始页、Crossref/OpenAlex 核验；开放稿优先使用 arXiv、机构仓储或期刊开放 PDF。
- GitHub 项目核验了 README、LICENSE/许可证可见性、实现文件和最后提交时间。
- 当前环境没有 Web of Science 订阅或导出数据，因此未声称完成 WOS 收录/被引分析。
- Google Scholar 仅可作为发现入口，本报告没有把 Scholar 搜索摘要作为证据；结论均落到 DOI、arXiv、期刊开放页或官方仓库。
- 引用年份以正式发表年份为主；部分论文 DOI 注册或 online-first 年份可能早一年。

## 11. 2026-07-15 M5N2 真实运行证据同步

本轮完成 baseline/candidate 各 10 seed 的 SimpleFlight M5N2，共 20 case。它验证的是
单中心 D2 主线在 M 对 N 任务合同下的运行时边界，不是跨节点数值融合或完全分布式
identity consensus 的完成证据：

- D2 association main-bus 3805/3805 样本可用，mean/P95/max 为
  `2.521/3.147/98.942 ms`；
- 在线 truth identity/state use 为 0，在线 IDSW/continuity 因没有 truth assignment
  保持 unavailable，不能写成 0；
- 多个 primary 仍共同引用中心维护的同一个目标 `global_track_id`，没有把多资源需求
  复制成多条全局目标航迹，也没有允许末端节点本地重绑规范 ID；
- 第二 primary 物理失败和 `collision_stop` 没有碰撞对象证据，不能归因于跨节点关联或
  canonical registry；
- 现有 GNN/Hungarian 默认路径、one canonical-to-many source registration 基础和
  D1/D2 数值融合职责边界均不变。

批次在 M5N2 20/20 后终止；终止前额外完成的 `png_ttc_2v2_seed001` 被排除，dropout
case 为 0。后续跨节点 P1 仍需 owner/epoch failover、高歧义多帧回放和独立离线真值
评分，不能用本批物理结果替代。

## 12. 2026-07-16 来源谱系治理可观测性补充

中心 canonical registry 的原则未变：`(source_node_id, local_track_id, local_epoch)` 或
等价 namespaced `source_track_id` 只是来源键，不能成为全局身份权威。D2 现将现有
binding/quarantine 明细累计为 `source_binding_conflict_count` 与
`source_lineage_quarantine_count`，并接收 frame-level
`upstream_local_identity_rejection_count` 审计上游已拒绝的本地身份塌缩。第三项只允许
非负整数，缺失为 0，非法值 fail closed；它不构造来源航迹或 canonical track。

三项计数已进入 risk 与 replay 单 seed/多 seed 聚合，但不参与当前关联代价、默认门限
或自动 owner 切换。2026-07-16 两个 3-frame synthetic seed 的结果为 conflict 均 1、
quarantine 均 1、upstream rejection 为 2/4，完整 D2 回归为
`123 passed, 1 warning`。本轮没有真实跨节点 AirSim 数据，因此 owner/epoch failover、
高歧义多帧注册、false suppression/recall 和 fusion NEES/ANEES 缺口均不重分类。

## 13. 2026-07-20 六维稀疏关联与跨节点融合边界

本轮新增的是单中心航迹链中的六维 **detection-to-track** 规则路径，不是跨平台
track-to-track 数值融合器。两条路径共享中心身份原则，但输入、候选图和输出职责不同：

| 路径 | 输入与状态 | 已实现关联 | 身份/融合职责 |
| --- | --- | --- | --- |
| 六维 detection-to-track | truth-free `Detection3D`；`GlobalTrack3D` 固定 `[pN,pE,pD,vN,vE,vD]` 与 6x6 covariance | KD-tree 空间候选、3D 位置创新/马氏门控、候选图连通分量级 GNN/Hungarian | `Scalable3DTracker` 创建并维护 `GT3D-*`；不执行跨节点 CI/exact fusion |
| cross-node track registry | namespaced `SourceTrackSummary` 与中心 canonical snapshot | 公共时刻传播、按 source track-to-track Hungarian、binding/lineage/stale 治理 | 维护 one canonical-to-many source binding 并输出 fusion directive；数值 posterior 仍由 D1 负责 |

这里两处 GNN 均表示 **Global Nearest Neighbor**。D5 的跨视角图神经网络使用匿名局部
tracklet 并输出同目标概率，不在 D2 实现，也不能创建或改写 `global_track_id`。六维
adapter 忽略 D1 对象携带的上游 `global_track_id`；source/local key 只作为命名空间化
连续性证据，不能成为 canonical identity。D1 fused-track state 按其 state-valid
timestamp 进入关联，原始 sensor measurement/arrival timestamp 另存为 source 审计字段；
这不替代 cross-node registry 对各 source track 的公共时刻传播。

在线六维结果显式保留 `id_switch_count` 和 continuity 字段，但在没有离线标签时写为
`None + unavailable`；风险摘要只使用候选重叠、cost margin、漏配和生命周期等在线
证据。`Sparse3DOfflineEvaluator` 在关联完成后单独消费 truth sidecar，计算 IDSW、
identity/coverage continuity、duplicate 和 false-alarm assignment，评分结果不回写
候选边、滤波状态或 ID binding。

**2026-07-20 D2-owned 验证证据**：

- 专项 13 个测试覆盖 5/20/50/100/200、Down 轴门控、三维交叉、连续两帧漏检、
  15 个匿名虚警、truth fail-closed、上游 ID 非权威和有界历史；完整 D2 为
  `136 passed, 1 warning`，验收阈值为零失败；
- 200 目标确定性三维规则网格执行 3 个独立 trial，每个预热 1 帧后采样 30 帧；90 个
  测量帧的候选/潜在全对均为 `200/40,000`，component matrix pair 为 `200`，peak
  component pair 为 `1`，裁剪率 `99.5%`；
- 聚合关联 mean/P50/P95/max 为 `6.683/6.306/7.056/22.471 ms`，tracker step 为
  `25.491/25.016/26.797/41.613 ms`。

该性能数据只证明单进程、单一稀疏布局下避免了无条件全密集候选历史扩张，不是
多 seed、AirSim、实时 SLA 或 200v200 全链路结论。极端全重叠或协方差过度膨胀仍会
形成大连通分量；main-owned scalable episode bus 接入、候选预算与召回率联合标定、
高歧义跨节点 JPDA/MHT、owner/epoch failover 和数值 CI/exact posterior 均保持开放。

## 14. 2026-07-20 M-to-N 离线身份指标合同补充

M-to-N 不改变 identity join 的基数规则。evaluator 按输入记录长度处理任意数量的
global tracks 和 observations：一个 truth 可对应多条由不同 lineage 支持的 track，作为
duplicate 计数；一条 track 指向多个 truth 时保持 ambiguous。资源数、目标数、2v2/5v5
场景名均不参与 mapping shape 或 truth 选择。

`d2.scalable3d_identity_evaluation.v1/v2` public artifact 让 main/D6 后续只消费 D2
公开合同，不需要读取 canonical registry 或 tracker 私有状态；v2 仅在 identity
commitment evidence 存在时使用。文件 evaluator 对 D1/D2
records、evidence、truth sidecar 的 hash/schema/sequence/truth isolation 统一 fail
closed，并要求 sequence 绑定六维 D2-owned track 与完整 track-frame 集合。23 个专项含
37 目标 x 2 帧动态规模，完整 D2 为 `162 passed, 1 warning in 30.63s`。

该变化只关闭单中心 scalable 3D 的 evaluator mapping/metrics 合同，不实现跨节点 owner
failover、分布式临时 ID 共识或数值 CI/exact fusion，也没有形成 M-to-N AirSim 多 seed
身份性能证据。main producer 跳过无 lineage track/frame 的接线仍需修正；默认
GNN/Hungarian 与 one canonical-to-many source 原则不变。

## 15. 2026-07-22 部分身份证据补充

M-to-N 输入规模下，单个不完整映射不再使全部可审计证据消失，但仍会阻断严格 IDSW。
evaluation v1 的附加诊断分别报告受评分 mapping coverage、完整帧 coverage、相邻转移
coverage、ambiguous/missing 数量、重复映射真值帧排除数和可证明 IDSW lower bound。
部分下界只接受每个真值帧唯一的可评估全局航迹；多航迹时不按持久化顺序选代表。严格
metrics 继续全局 fail closed，部分结果不进入中心 registry、跨节点 binding 或在线风险。

nominal 200v200、seed 1000 的单 seed 只读复算得到 9038 条受评分 mapping，其中 8906
条可评估；严格 IDSW unavailable。1 个真值帧因对应多条可评估航迹被排除，该帧原本也
不完整，修正后仍由 385 个唯一锚点区间证明 lower bound 7。该结果说明 M-to-N/大规模
评估需要同时给 coverage、exclusion 和 availability，不能把部分样本中的低切换数写成
完整性能。D6 多 seed 汇总、跨 owner failover 和分布式临时身份仍保持开放。
