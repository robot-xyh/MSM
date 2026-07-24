# D1 结构歧义下一候选设计

- **状态**：A1 `IMPLEMENTED_UNIT_TESTED_OFFLINE_PROTOTYPE`；A1 准备对象优化
  `IMPLEMENTED_UNIT_TESTED_OFFLINE_OPTIMIZATION`；A1 原子接口优化
  `IMPLEMENTED_UNIT_TESTED_OFFLINE_ATOMIC_OPTIMIZATION`；main 已完成 clean 原子成对
  复核，A2 安全子门通过、性能门和有效 treatment 门失败，不准入；A3/A4 未实现
- **日期**：2026-07-24
- **范围**：D1 结构歧义证据、共同质心发布语义及 D2 后续消费边界
- **实现证据**：提交 `de73cb2` 为 A1 基线；原子接口优化后聚焦
  `36 passed`，D1 全量 `324 passed`
- **非目标**：A1 不是在线 schema 或运行开关；本文不声明 A2 性能通过、AirSim 或系统收益

## 1. 决策摘要

本文比较三个可独立评审的下一步方向：

| 路线 | 核心语义 | 当前决策 |
| --- | --- | --- |
| A. 拒绝路径发布态 overlay/副作用隔离 | 规范滤波状态和历史保持不动；共同质心只在发布 DTO 上形成一次性 overlay；拒绝时直接发布规范快照 | **A1 纯函数、准备对象和原子接口优化已完成单测；main 已完成 clean 原子成对复核，A2 安全子门通过、性能/有效 treatment 门失败；A3/A4 未实现** |
| B. 固定滞后 OOSM 共同质心事件 | 把共同质心作为 measurement-time 历史事件插入固定滞后窗口并重放 | **暂不进入在线实现** |
| C. D1 只发布证据，D2 概率/多假设消费 | D1 保持 prediction-only 和证据侧车；D2 在有界窗口中维护关联概率或多个匹配假设 | **保留为主要系统研究路线，交由 D2 后续规划** |

保守顺序是：A1 已先验证纯函数和 DTO 装配合同；A2 冻结扫描 shadow 已完成原子入口接线和
一次 clean 成对复跑，但没有通过准入门，因此不开展匿名冻结输入试验。
B 只有在事件排序、过程噪声分段语义和一致性验收全部冻结后才可重新评审。C 不在本轮修改
D2，也不把 D1 source token 升级为规范身份。

seeds 1101/1102 继续停止，不因本设计恢复。任何后续确认性试验必须使用预先冻结、哈希登记的
新匿名扫描和未见 seed。

## 2. 已知问题与不可回避的数值事实

### 2.1 拒绝不等于无副作用

现有冻结扫描诊断中，`oosm_scan` 和 `unbalanced_component` 都满足
`applied_component_count=0`，共同质心 correction 没有生成平移或协方差膨胀。但候选路径
仍执行 publication-base replay + replace，用单段历史重放结果替换控制路径的分段预测发布态。
两个场景的候选减控制协方差差最小特征值分别为
`-0.0071928353214153066` 和 `-0.004617076466238031`，并已 bitwise 归因到该 replacement。

因此，下一候选首先要解决的不是扩大 treatment，而是建立以下可验证语义：

> 拒绝共同质心候选时，规范滤波状态、协方差、历史和发布航迹必须与未启用该候选的控制路径
> bitwise 相同；候选专属审计记录可以不同。

### 2.2 当前过程噪声没有分段半群等价性

当前 CV 传播使用

\[
F(h)=
\begin{bmatrix}
I_3 & hI_3\\
0 & I_3
\end{bmatrix},
\qquad
G(h)=
\begin{bmatrix}
\frac{1}{2}h^2I_3\\
hI_3
\end{bmatrix},
\qquad
Q(h)=G(h)qG(h)^\mathsf{T}.
\]

对 \(h=h_1+h_2\)，当前模型一般不满足

\[
Q(h_1+h_2)
=
F(h_2)Q(h_1)F(h_2)^\mathsf{T}+Q(h_2).
\]

因此协方差传播算子

\[
\mathcal P_h(P)=F(h)PF(h)^\mathsf{T}+Q(h)
\]

一般满足

\[
\mathcal P_{h_2}(\mathcal P_{h_1}(P))
\ne
\mathcal P_{h_1+h_2}(P).
\]

这不是浮点容差可以掩盖的接口细节。只要在 \(t_0\) 与 \(t_2\) 之间插入 \(t_1\)，传播就从
单段变为两段。即使 \(t_1\) 上的事件满足
\(\Delta x=0,\Delta P=0\)，协方差也可能改变。B 路线不能用“零更新事件无作用”作为控制假设。

## 3. 三条路线共同保持的合同

无论选择哪条路线，以下合同均不放宽：

1. 同时保留 `measurement_timestamp` 和 `arrival_timestamp`；不得删除、覆盖或用发布时间
   代替任一时间戳。
2. D1 工作帧保持 NED；成员和观测协方差继续完整携带。
3. A/B 的共同质心状态 treatment 只考虑成员数、观测数和最大匹配基数相等，free row/column
   均为 0 的平衡纯交替环；不得放宽满基数门制造 treatment。
4. `component_id`、`component_generation`、`evidence_id` 和固定滞后有界 generation 水位
   继续承担幂等语义；重复代、倒退代、超窗代和容量溢出均 fail closed。
5. 不增加 hit/miss/birth/delete，不追加 observation history、lineage 或 `source_support`，
   不刷新 identity freshness 或质量分级。
6. `global_track_id` 只从规范航迹快照原样复制；overlay、事件和证据均不得生成、改写、重绑
   或把 D1 本地/source key 冒充为 `global_track_id`。
7. D1 仍不维护成员间交叉协方差，必须保留
   `cross_covariance_available=false`。下游不得把成员边缘协方差当作相互独立。
8. 在线判定不读取 truth、actor、target 名称、D6 标签或其他离线身份字段。
9. 动态规模按输入分量运行，不把 `2x2`、2v2、5v5 或 200v200 写成算法常量。

C 可以消费含 free-row/free-column 的既有证据，但这不使这些分量成为 D1 共同质心状态
treatment 的合法输入。

## 4. 共同质心的共享数学语义

对通过满基数门的分量，设成员预测位置为 \(p_i^-\)，观测位置为 \(z_j\)，
\(m=|R|=|Z|=|M|\)：

\[
\bar p^-=\frac{1}{m}\sum_{i=1}^{m}p_i^-,
\qquad
\bar z=\frac{1}{m}\sum_{j=1}^{m}z_j,
\qquad
r_c=\bar z-\bar p^-.
\]

候选继续使用质心马氏门和去质心二阶矩形状门。通过后，共同平移和边缘协方差增量为

\[
\delta p
=
\alpha\,\operatorname{clip}_{\lVert\cdot\rVert}(r_c,r_{\max}),
\]

\[
\Delta P_{\mathrm{pos}}
=
\alpha^2\Sigma_c+
\left(
\lambda_{\mathrm{shape}}\lVert C_z-C_p\rVert_F+q_{\min}
\right)I_3.
\]

该计算只表达置换不变的集合位置证据，不选择 observation-to-member 边。成员速度和成员间
相对位置不变。由于同一 \(\delta p\) 带来共同误差，只有边缘协方差增量而没有成员间
交叉协方差时，不能声称形成了完整联合后验。

## 5. 路线 A：发布 overlay，不修改滤波历史

### 5.1 规范状态与发布状态分离

在发布时间 \(t_p\)，规范滤波快照记为
\((x_i^c(t_p),P_i^c(t_p))\)。它只能由既有正式观测历史、检查点和 CV 传播产生。共同质心
候选不得为了清除上一帧修正而重放或替换该快照。

候选拒绝时：

\[
\mathcal O_k=\varnothing,\qquad
x_i^{\mathrm{pub}}\equiv x_i^c,\qquad
P_i^{\mathrm{pub}}\equiv P_i^c.
\]

这里的 \(\equiv\) 是逐字段、逐数组 bitwise 同一语义，不是数值近似。发布器直接使用规范快照，
不经过加零、重建、重新对称化或 replay。

候选接受时，只在脱离滤波器所有权的发布 DTO 上应用：

\[
x_i^{\mathrm{pub}}
=x_i^c(t_p)+
\begin{bmatrix}
\delta p_k\\0
\end{bmatrix},
\qquad
P_i^{\mathrm{pub}}
=P_i^c(t_p)+
\begin{bmatrix}
\Delta P_{\mathrm{pos},k}&0\\
0&0
\end{bmatrix}.
\]

overlay 只对本次 `published_at` 有效，不写入下一次预测的起点。下一次发布重新从当时的规范
快照和当代证据计算；没有合格证据时自然退回规范快照。A 因而不需要“先重放再清除旧临时
修正”。

### 5.2 明确禁止的写入

A 的计算和发布装配不得修改：

- 航迹内部 state/covariance、filter timestamp、track revision；
- observation history、fixed-lag checkpoint、replay cache 和失效水位；
- hit/miss、birth/delete、质量等级、identity freshness；
- lineage、`source_support`、source key 和 `global_track_id`；
- 扫描水位线、claim registry 和既有一致性证据。

允许变化的状态仅限候选专属的有界 generation 水位和审计计数。水位提交必须发生在全部成员
overlay 原子验证通过或确定拒绝之后，不得借水位更新触发滤波 replay。

### 5.3 建议的数据结构

以下是不带实验前缀的概念字段表。提交 `de73cb2` 已用显式
`ExperimentalCentroidPublicationDecisionV1`、
`ExperimentalCentroidMemberOverlayV1`、`ExperimentalCentroidPublicationState` 和
`ExperimentalCentroidPublicationEvaluation` 实现 A1；实际 schema 字符串为
`d1.experimental-centroid-publication-overlay-decision.v1`，并固定声明
`experimental_design_prototype_not_online_schema`。它不是当前在线 schema，概念字段表也
不构成 A2 接线合同：

```text
CentroidPublicationDecisionV1
  schema_version
  decision_id
  decision = accepted | rejected
  reject_reason
  evidence_id
  component_id
  component_generation
  publisher_node_id
  publisher_epoch
  sensor_id
  scan_id
  measurement_timestamp
  arrival_timestamp
  state_valid_timestamp
  published_at
  base_publication_revision
  base_publication_digest
  state_semantics = publication_overlay_not_filter_posterior
  overlay_valid_for_publication_id
  member_overlays[]
  cross_covariance_available = false
  mutates_filter_history = false

CentroidMemberOverlayV1
  source_key
  opaque_member_track_token
  base_track_revision
  base_state_digest
  base_covariance_digest
  delta_position_ned[3]
  delta_position_covariance[3,3]
```

拒绝决策的 `member_overlays` 必须为空。接受时，发布装配先验证每个 source member 在规范快照
中恰好出现一次，revision 和 digest 均匹配，再一次性生成全部新 DTO；任一成员缺失、重复或
基准不匹配时整个分量拒绝。`global_track_id` 不进入 overlay key，只从匹配到的规范 DTO
原样复制。未来若越过 shadow 阶段，accepted 发布必须同时携带 `decision_id` 和
`state_semantics`，使消费者不能把 overlay 冒充为规范滤波后验；拒绝发布不增加这些业务字段，
以保持 control bitwise 等价。

### 5.4 确定性排序键

时间字段使用既有规范数值表示，不做容差分桶或本地化字符串排序。一个发布批次中的组件键为：

```text
K_component = (
  published_at,
  state_valid_timestamp,
  measurement_timestamp,
  arrival_timestamp,
  publisher_node_id,
  publisher_epoch,
  sensor_id,
  scan_id,
  component_id,
  component_generation,
  evidence_id
)
```

成员按 `(source_key, opaque_member_track_token)` 排序；观测沿用既有 `observation_key`；
候选边按 `(member_source_key, observation_key, canonical_edge_roles)` 排序。字符串均按
UTF-8 字节序，`edge_roles` 先按固定枚举序规范化。任何完整键碰撞、相同 source member 被两个
组件覆盖或同代内容摘要冲突都 fail closed，不能依赖输入遍历顺序解决。

`decision_id` 由 schema version、`K_component`、decision/reject reason、规范基准摘要和有序
member overlays 的 canonical JSON 计算 SHA-256。所有数值先通过有限性和 shape 校验；不允许
NaN/Inf、容差分桶或字典自然顺序进入摘要。

### 5.5 A 的主要风险

1. overlay 不进入动力学历史，连续发布可能出现“有证据时偏移、无证据时回落”的可见跳变。
2. D1 内部规范状态与下游看到的发布状态暂时不同；审计和消费者必须能区分
   `canonical_filter_state` 与 `publication_overlay_state`。
3. 下游若把 overlay 状态回灌为 D1 先验，会破坏隔离边界；原型不得增加该反馈路径。
4. 同一成员被重叠组件覆盖时不能叠加多个共同平移，必须整批或冲突组件 fail closed。
5. 缺少交叉协方差仍限制统计解释；协方差膨胀只能称为边缘保守量，不能称为联合一致。
6. 纯发布计算虽然避免 replay，仍可能增加物化、复制、哈希和 P95 成本。

## 6. 路线 B：固定滞后 OOSM 共同质心事件

### 6.1 事件语义

B 把接受的共同质心证据建模为 measurement-time 事件
\(e_k=(t_m,t_a,\delta p_k,\Delta P_k,\ldots)\)，插入固定滞后历史，在 \(t_m\) 对成员执行

\[
x_i(t_m^+)=x_i(t_m^-)+[\delta p_k,0]^\mathsf{T},
\qquad
P_i(t_m^+)=P_i(t_m^-)+\operatorname{diag}(\Delta P_{\mathrm{pos},k},0),
\]

再按全部后续历史事件重放到 \(t_p\)。这比 A 更接近“状态事件”，也能使后续正式量测在同一
历史中解释该处理，但会改变规范滤波后验。

拒绝事件不得插入历史，不能用零更新占位。即使零更新不改 \(x,P\)，传播到该时刻再继续传播
也会改变当前 \(Q(h)=G(h)qG(h)^\mathsf{T}\) 的分段。

### 6.2 建议的数据结构与排序

设计占位结构为：

```text
CentroidHistoryEventV1
  event_id
  evidence_id
  component_id
  component_generation
  publisher_node_id
  publisher_epoch
  sensor_id
  scan_id
  measurement_timestamp
  arrival_timestamp
  accepted_at
  member_source_keys[]
  delta_position_ned[3]
  delta_position_covariance[3,3]
  cross_covariance_available = false
  base_history_revision
```

若未来实现，所有历史事件必须共享一个完整排序表。当前预案键为：

```text
K_event = (
  measurement_timestamp,
  arrival_timestamp,
  event_kind_rank,
  publisher_node_id,
  publisher_epoch,
  sensor_id,
  scan_id,
  component_id,
  component_generation,
  event_id
)
```

`event_kind_rank` 必须覆盖既有 observation update、birth/lifecycle 和新 centroid event，
不能只为新事件临时指定。本设计的预注册顺序表为：

| `event_kind_rank` | 事件 |
| ---: | --- |
| 0 | `canonical_observation_update` |
| 1 | `canonical_birth_or_lifecycle_transition` |
| 2 | `accepted_structural_centroid_event` |

同一扫描先完成既有规范 observation/lifecycle 事件，再处理 centroid event。未映射到该表的
历史事件类型、重复 rank 或运行时扩展类型都阻断 B，不允许以容器遍历顺序兜底。该顺序在实现
前仍需用历史回放 oracle 冻结；成员和边的内部排序沿用 A。

### 6.3 B 暂缓的必要条件

B 不得进入在线实现，除非先完成并预注册：

1. 冻结所有历史事件种类、同时间戳 tie-break 和 replay 起止边界；
2. 冻结过程噪声分段策略。可选方向只能是“所有臂共享固定时间分段”或单独验证另一套满足所需
   组合律的离散化；不得把过程噪声变更夹带在共同质心候选中；
3. 对零事件、拒绝事件、同代重放和 OOSM 插入建立逐事件 state/covariance oracle；
4. 明确共同误差的交叉协方差模型，或证明所用保守上界不会被下游误读；
5. 预先冻结 NEES/NIS、RMSE、历史重放成本、P95 和内存门槛。

在这些条件完成前，B 的数值语义无法与当前基线公平隔离，风险高于 A。

## 7. 路线 C：D1 证据发布，D2 概率或多假设消费

### 7.1 D1 边界

C 不给 D1 增加联合概率关联器。D1 继续发布
`d1.structural-ambiguity-evidence.v1`，保留候选边、NIS、分量结构、双时间戳、成员/观测
边缘协方差、generation、来源键和 `cross_covariance_available=false`。歧义成员继续
prediction-only，D1 不选择一条身份边，也不更改 `global_track_id`。

### 7.2 D2 概率语义

令 \(\mathcal H_k\) 为 evidence 允许边图上的满基数匹配假设集合。D2 可在有界窗口中维护

\[
\log w_k(h)
=
\log w_{k-1}(\operatorname{parent}(h))
+\log p(Z_k\mid h)
+\log p(h\mid\operatorname{parent}(h))
-\log C_k,
\]

或计算 JPDA 类边缘概率

\[
\beta_{ij}
=
\sum_{h\in\mathcal H_k:(i,j)\in h}w_k(h).
\]

这些权重首先是关联/身份证据，不是 D1 成员状态的独立量测融合权重。由于 D1 没有发布成员间
交叉协方差，D2 不得把多个成员边缘协方差相乘为独立似然再收缩物理状态。任何状态融合都需
单独的相关性模型和验收。

### 7.3 D2 后续规划的数据结构

建议 D2 规划以下内部结构，不在本轮创建：

```text
AmbiguityWindowState
  window_id
  ordered_evidence_ids[]
  oldest_measurement_timestamp
  newest_arrival_timestamp
  hypotheses[]
  max_hypotheses
  expiry_timestamp

AssociationHypothesis
  hypothesis_id
  parent_hypothesis_id
  ordered_assignment_edges[]
  log_weight
  generation_vector[]
  lifecycle_disposition
  canonical_track_references[]
```

evidence 先按 A 的 `K_component` 排序。每个假设内部边按
`(member_source_key, observation_key)` 排序，
`hypothesis_id=SHA-256(schema_version, ordered_evidence_ids, ordered_assignment_edges,
parent_hypothesis_id)`。剪枝先按 `(-log_weight, hypothesis_id)` 排序；相同数值权重由
`hypothesis_id` 决胜，不能依赖容器遍历顺序。

D2 的规范 ID 仍由中心身份合同管理。假设只能引用已有 canonical track，不能把 D1
`source_key` 改名为 `global_track_id`，也不能通过局部换绑修改已发布规范 ID。

### 7.4 C 的主要风险

- 假设数随分量和窗口组合爆炸，需要硬上限、确定性剪枝和超限 fail closed；
- NIS 到 likelihood 的标定不足会产生虚假高置信度；
- 延迟 birth/death 可能继续降低 D2/D3 可用性；
- 无交叉协方差限制状态融合，只能先研究身份连续性；
- 多假设 lineage、重放和过期处理必须保持幂等；
- D2/D3 合同变化属于跨模块工作，不能由 D1 文档直接宣称完成。

## 8. 路线比较

| 维度 | A 发布 overlay | B 固定滞后事件 | C D2 概率/多假设 |
| --- | --- | --- | --- |
| 是否改 D1 规范滤波历史 | 否 | 是 | 否 |
| 拒绝路径可做到规范发布 bitwise 不变 | 可以，设计目标 | 只有“不插入事件”才可能 | 可以 |
| 是否受过程噪声分段影响 | overlay 本身不插入传播段 | **直接受影响** | D1 状态不受影响 |
| 是否解决身份歧义 | 否 | 否 | 目标是概率化保留身份假设 |
| 交叉协方差缺失风险 | 有，但局限于发布边缘量 | 高，进入历史后更难解释 | 有，禁止独立状态融合 |
| 实现与验证范围 | 最小、D1-local | 大、改 fixed-lag 核心语义 | 跨 D1/D2，主要由 D2 owning |
| 当前推荐 | **A1 已完成；A2 不准入并停止 A3/A4** | 暂缓 | 主要系统研究路线 |

## 9. 阶段拆分

### 阶段 D0：设计冻结

本文件初版及当时的 PLAN/GAP/review 同步属于 D0。D0 的历史完成标志只是设计、风险和验收
口径成文；后续 A1 实现不改变该历史定义。

### 阶段 A1：纯函数最小原型

- **状态：`IMPLEMENTED_UNIT_TESTED_OFFLINE_PROTOTYPE`，提交 `de73cb2`。**
- 输入为不可变规范发布快照和既有 `StructuralAmbiguityEvidence`；
- 输出只包含 accepted/rejected decision 和 detached member overlays；
- 不接在线发布，不调用 replay/replace，不修改滤波对象；
- 用同步平衡 2/3/5 成员、OOSM、stale、数量/匹配结构非法、重复/倒退代、摘要冲突、冲突
  组件、容量、非有限和身份字段 fixture 验证；
- 组件、成员、观测、边和业务航迹输入排列产生 byte-identical decision/overlay；拒绝装配
  直接返回原规范序列，接受只复制 DTO 并保持速度、相对位置、`global_track_id`、metadata、
  lineage/source support、identity 和质量不变；
- 2026-07-23 聚焦测试 `7 passed`，D1 全量 `294 passed`。这只关闭 A1 单元原型范围，不是
  A2、在线发布、AirSim、P95 或系统效果证据。

### 阶段 A2：离线发布装配 shadow

- **状态：main 原子入口接线和 seed 1100 clean 成对复跑已完成；A2 不准入。**
- 在默认关闭条件下对冻结扫描计算 overlay，但不向 D2/D3 发布；
- 同批记录规范快照摘要、shadow DTO 摘要和全部禁止写入对象摘要；
- clean commit 为 `7cc2d0cfd598a72d60c6ba8c7d4a283f4e5a897d`，两份 manifest 均为
  `repository_dirty=false`；
- 9/9 次 post-integrity 通过，atomic failure、materialized shadow、禁止写入、错误、D2/D3
  shadow 消费、在线 truth 和全局编号变化均为 0；D1/D2/D3 两臂均为 `202/201/186`；
- control/shadow 墙钟 `10.735151270986535/19.449935468961485 s`，开销 `+81.1799%`，
  shadow P50/P95/max 为 `1024.838/1536.429/1549.436 ms`；
- 46 条 evidence 为 0 accepted/46 `oosm_scan` rejected。安全与业务非干预子门通过，性能门
  和有效 treatment 门失败；
- 全拒绝路径旧 prepared-handle 实现本来就跳过 assemble，原子入口不能消除主要前后摘要
  开销。

### 阶段 A3：匿名冻结扫描 treatment 发现

- **状态：未实现。**
- 使用新匿名扫描，只判断合法平衡分量是否自然出现；
- 不运行 seeds 1101/1102，不放宽 OOSM、满基数、形状或身份门；
- 若仍为零 treatment，记录停止结论，不进入效果试验。

### 阶段 A4：预注册确认性试验

- **状态：未实现。**
- 独立冻结输入、提交、配置、seed 清单和指标实现；
- 比较 hold-only 与 hold+publication-overlay；
- 满足全部状态、身份、下游和资源门槛后，才讨论是否保留为默认关闭候选。

### 阶段 B0：仅做语义研究

先完成事件排序、过程噪声分段和一致性 oracle，不接在线实现。任一项未冻结，B 保持 hold。

### 阶段 C0：D2 规划移交

D1 提供本设计和既有 evidence schema；D2 单独制定假设窗口、概率标定、剪枝、canonical ID
和 D3 可用性计划。D1 不越界修改 D2 文档或代码。

## 10. 预注册验收与停止条件

### 10.1 A1/A2 必过门槛

1. 对每个拒绝原因，候选与 control 的发布 `GlobalTrack[]` 序列化结果 bitwise 相同；只允许
   候选专属 decision/audit 不同。
2. 处理前后，滤波 state/covariance、history、checkpoint、cache、replay/扫描水位、revision、
   hit/miss、birth/delete、lineage、`source_support`、质量、身份状态和 `global_track_id`
   摘要完全相同；候选专属 generation 水位只允许按第 5.2 节的有界幂等语义变化。
3. 接受路径的 \(\delta p\) 和 \(\Delta P_{\mathrm{pos}}\) 与冻结公式 oracle 一致；
   速度和相对位置逐元素不变，\(P_i^{pub}-P_i^c\succeq0\)。
4. 任一成员校验失败时整个组件原子拒绝，不允许部分 overlay。
5. 输入成员、观测、边和组件的全排列产生 byte-identical decision/overlay。
6. 同代重放不重复发布新作用；倒退代、超窗代、冲突摘要和容量满均 fail closed。水位仍有
   固定滞后淘汰和硬容量。
7. 双时间戳、满基数、NED、协方差、lineage/source support、truth 隔离和
   `cross_covariance_available=false` 全部保持。
8. shadow 模式不得改变 D1/D2/D3 业务输出。D1 发布 P95 增幅不超过 5%，候选水位和 overlay
   暂存均不随 episode 时长无界增长。

任一 bitwise 拒绝门、身份合同或有界存储门失败，A 停止，不进入 A3。

A1 已在纯函数 fixture 范围验证第 1、3-7 项及输入对象不变；由于它从未接触滤波器，不能把
单元测试外推为在线 filter/history/checkpoint/cache 审计。A2 开发复跑已补充第 2 项的禁止
写入摘要，并证明第 8 项的业务输出等价和水位有界；性能不合格，且没有 accepted treatment。
因此 A2 整体未关闭，不能进入 A3。

### 10.2 A3/A4 数据与效果门槛

1. 在运行前登记 repository commit、`repository_dirty=false`、配置 SHA-256、扫描流 SHA-256、
   truth sidecar SHA-256、指标版本和 seed 清单；确认性集合至少 20 个新未见 seed，明确排除
   1101/1102。
2. 在线 truth use 必须为 0；确认性输入中必须自然出现至少一次合法 treatment。零 treatment
   立即形成停止结论，不以放宽门限补样。
3. strict IDSW 不得劣于 hold-only；track/coverage continuity 至少恢复 hold 相对独立
   source-only 控制臂损失的 75%。
4. 多 seed continuity 相对预注册基线的配对 95% 置信区间下界不得低于 `-0.005`。
5. D1 位置 RMSE 比值的配对 95% 置信区间上界不得超过 `1.05`；NEES/NIS 的维度、自由度、
   置信带和样本排除规则必须在运行前冻结，候选不得比 hold-only 降低合格覆盖率超过
   `0.005`。
6. D2 航迹数、D3 可分配目标数、identity commitment coverage 和 available mapping 均不得
   低于 hold-only；重复分配、未承诺来源/候选绑定违规必须为 0。
7. D1 publication/fusion P95 增幅不得超过 5%；峰值 RSS 增幅不得超过 5%；不得出现 generation
   容量拒绝、overlay 冲突漏检或长时无界增长。
8. 报告必须同时列出 treatment 数、拒绝原因、每 seed 结果和停止事件；不得只报告聚合改善。

### 10.3 B 进入实现前的门槛

- 对所有事件种类发布完整 `event_kind_rank` 表和 canonical replay oracle；
- 选择并冻结过程噪声分段基线，单独证明迁移语义，不把它归因于共同质心收益；
- 证明拒绝事件完全不入历史，且同代/倒退代不改变历史 revision；
- 为共同误差定义交叉协方差或经证明的保守界；
- 预注册 RMSE/NEES/NIS、P95、replay 次数和 fixed-lag 内存上限。

未全部满足时，B 状态保持 `DESIGN_HOLD_NOT_IMPLEMENTED`。

### 10.4 C 进入系统试验前的门槛

- 由 D2 owner 完成正式计划、数据合同和测试范围；
- 冻结 hypothesis 上限、窗口、剪枝 tie-break、权重归一化和欠流处理；
- 证明 evidence/generation 重放幂等，且 canonical `global_track_id` 不被局部重绑；
- 在不做独立状态融合的控制模式下先验证 IDSW、连续性、birth delay 和 D3 可用性；
- 超限、权重非有限、证据缺失或跨窗冲突全部 fail closed。

## 11. 当前状态

截至 2026-07-24：

- A1：`IMPLEMENTED_UNIT_TESTED_OFFLINE_PROTOTYPE`，提交 `de73cb2`；准备对象优化状态为
  `IMPLEMENTED_UNIT_TESTED_OFFLINE_OPTIMIZATION`，每个复用边界核对完整载荷 SHA-256，
  原子接口优化状态为 `IMPLEMENTED_UNIT_TESTED_OFFLINE_ATOMIC_OPTIMIZATION`。原子入口
  在单次调用中执行 1 次完整描述和 1 次操作后完整规范复核，聚焦
  `36 passed`，D1 全量 `324 passed`；公开结果可由标准 JSON 编码，canonical/shadow
  发布摘要使用同一完整航迹摘要清单语义；
- A2：main clean commit `7cc2d0cfd598a72d60c6ba8c7d4a283f4e5a897d` 已完成默认关闭
  原子 shadow 成对复核。9/9 次 post-integrity 通过，禁止写入、错误、下游消费、在线 truth
  和全局编号变化均为 0；但墙钟增加 `81.1799%`，shadow P95 `1536.429 ms`，且
  0 accepted/46 rejected。安全子门通过，性能门和有效 treatment 门失败，不准入；
- A3/A4：未实现；
- B：设计比较完成，在线实现暂停；
- C：研究方向保留，尚未形成 D2 实施计划；
- A1 新增独立实验 Python 模块和单元测试，但没有修改 `fusion.py`、在线开关、默认路径或当前
  在线 schema，也没有系统运行；
- seeds 1101/1102 继续停止。

当前共同质心候选仍保持默认关闭和 `candidate_not_promoted`。本文不能作为在线实现完成、
算法收益、AirSim 验证或系统晋级证据；现有证据范围是 A1 离线纯函数、准备对象和原子接口
单测，以及 A2 默认关闭审计 shadow 的 clean 单 seed 安全/性能拒绝结论。
