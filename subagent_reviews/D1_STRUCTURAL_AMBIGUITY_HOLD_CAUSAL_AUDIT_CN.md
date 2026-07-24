# D1 结构歧义保持因果审计

**审计日期**：2026-07-24
**审计范围**：200 对 200 三维质点场景中的 D1 结构歧义保持候选
**候选状态**：身份中性共同质心修正已作为默认关闭的 D1 模块候选实现；clean seed 1100
同输入复跑仍为零 treatment；受控冻结扫描已形成一次合法 treatment，仍未晋级
**下一候选状态**：A1 publication overlay 为
`IMPLEMENTED_UNIT_TESTED_OFFLINE_PROTOTYPE`，准备对象优化为
`IMPLEMENTED_UNIT_TESTED_OFFLINE_OPTIMIZATION`，原子接口优化为
`IMPLEMENTED_UNIT_TESTED_OFFLINE_ATOMIC_OPTIMIZATION`；main 尚未接入原子入口，A2 现有
性能门和有效 treatment 门失败，不准入；A3/A4 未实现，B 暂缓，C 交 D2 后续规划
**结构歧义基础证据提交**：`ff881316243ff5a2991a4659ab78637ed625d123`
**共同质心 clean 复核提交**：`7e15dac9cdaf6743999dfe045a70676fd31a17d6`
**A1 纯函数原型提交**：`de73cb2`；2026-07-24 原子接口优化后聚焦
`36 passed`，D1 全量 `324 passed`

## 1. 结论

候选把严格身份切换次数从 9 降到 3，同时使航迹连续性从 0.865 降到 0.826667，使 D2 航迹数
从 203 降到 201，使 D3 分配数从 200 降到 197。D1 最终航迹数在两端均为 202，退化主要来自
歧义期间的状态信息损失，不是 D1 最终少建了四条航迹。

D1 在 9 个雷达扫描中识别 46 个结构歧义分量，阻断 77 条观测，并使成员产生 91 次
prediction-only 暴露。77 条观测中，76 条在基线参考匹配中本可更新既有航迹，另 1 条是自由列
新生候选。离线真值审计表明，76 次参考更新中 69 次与真实目标一致，7 次属于错误换绑。现有
整分量保持策略以丢失 69 次有效状态修正为代价，阻止了 7 次错误修正。

唯一被 D1 延迟的新生观测对应真实目标 `TGT-0061`。它在 0.2 s 未初始化，在 0.4 s 由下一次
雷达观测建立，覆盖延迟一个雷达周期。D2 记录的四次 prevented birth 均与同一个真实目标
`TGT-0171` 的两条既有 D1 航迹有关，是重复航迹新生尝试，不是四个真实目标覆盖损失。该判断
只由离线真值完成；在线 D1、D2 和 D3 均未读取真值。

D1 已实现“身份不提交、状态中性修正”的默认关闭模块候选。它只在平衡、无自由行列、纯交替环
分量上使用置换不变的共同平移修正。成员相对几何、速度、命中数、来源谱系、质量分级和身份
状态保持不变，协方差相对当前帧精确重放基线只能膨胀。连续 generation 现采用帧替换语义，
每组件幂等记录改为固定滞后有界水位表。专项 `62 passed`、D1 全量
`282 passed in 17.81s`。main 先在未提交工作树完成 seed 1100 开发诊断，再于固定提交
`7e15dac` 完成 `repository_dirty=false` 的同输入复跑。两次运行中的 46 个候选均被 OOSM
或非平衡分量门控拒绝，没有实际状态处理。clean 复跑关闭了“证据仅来自 dirty 工作树”的
复核缺口，但没有形成算法 treatment，也没有运行多 seed，因此不能晋级。

D1 后续受控冻结扫描诊断证明同步平衡纯交替环可以在不放宽现有安全门的条件下形成一次
`15.000000 m` 共同平移。乱序平衡分量仍以 `oosm_scan` 拒绝，数量不平衡分量仍以
`unbalanced_component` 拒绝。该结果只关闭边界可执行性问题，不改变真实 clean seed 1100
的零 treatment 和系统 P1 状态。

## 2. 证据与方法

干净 A/B 制品位于：

- `/tmp/MSM-identity-freshness-final-ff88131/baseline`
- `/tmp/MSM-identity-freshness-final-ff88131/candidate`

两端使用同一提交、seed 1100、200 个目标、200 个资源、2.2 s 仿真时长和
`recon_count=2`。候选只启用结构歧义保持链路。两端
`online_truth_use_count=0`。

因果审计分为两步：

1. 使用候选的冻结在线观测和 D1 发布记录重放 89 个发布批次。逐批 observation、accepted、
   update、birth 和 track count 与候选制品一致，终态均为 202 条 D1 航迹。
2. 重放完成后，使用独立的 `offline_truth_labels.jsonl`、`offline_truth_state.npz` 和
   `offline_identity/` 制品连接观测、航迹和真实目标。真值只用于离线判断“参考更新是否正确”
   和“新生是否重复”，不进入在线匹配、滤波、身份保持或分配。

逐轨迹位置误差只用于解释已识别歧义成员的变化。它不是正式系统均方根误差，也不能替代多
seed 的归一化估计误差平方、归一化创新平方和覆盖率验收。

## 3. A/B 结果

| 指标 | 基线 | 候选 |
| --- | ---: | ---: |
| D1 航迹数 | 202 | 202 |
| D2 航迹数 | 203 | 201 |
| D3 分配数 | 200 | 197 |
| 严格身份切换次数 | 9 | 3 |
| 航迹连续性 | 0.865000 | 0.826667 |
| 覆盖连续性 | 0.870000 | 0.828333 |
| 可评估映射 | 1,566 | 1,491 |
| 部分诊断不可用映射 | 234 | 296 |
| 身份提交覆盖率 | 1.000000 | 0.957471 |
| 未提交映射 | 0 | 76 |
| 重复分配 | 0 | 0 |
| 在线真值使用 | 0 | 0 |
| 实时倍率 | 0.220352 | 0.207642 |

候选的身份指标已经可评估，首次 A/B 中
`source_observation_outside_lineage_window` 导致的不可用结论不再适用。ID 切换减少是真实
结果，但连续性、映射可用性、D2 航迹和 D3 分配同步下降，候选仍不满足晋级条件。

### 3.1 main 单 seed 三臂闭环复核

main 随后在 seed 1100 上增加独立 source-only 控制臂，并接入 D3 身份提交门控和运行时绑定
撤回。三臂为默认基线、`hold=False/source=True` 和 `hold=True`。结果如下：

| 指标 | baseline | source-only | hold |
| --- | ---: | ---: | ---: |
| D1 航迹数 | 202 | 202 | 202 |
| D2 航迹数 | 203 | 201 | 201 |
| D3 分配数 | 200 | 198 | 186 |
| strict ID switch | 9 | 7 | 3 |
| track continuity | 0.865000 | 0.865000 | 0.826667 |
| coverage continuity | 0.870000 | 0.868889 | 0.828333 |
| 终态已映射真实目标 | 未单列 | 200 | 191 |
| 终态未映射航迹 | 未单列 | 1 | 10 |

hold 端记录 D2 prevented hit/miss/birth `69/69/4`、76 条未承诺记录；D3 新身份提交门控拒绝
11 个目标，未承诺绑定违规为 0。该结果证明下游 fail-closed 合同可以阻止未承诺目标继续进入
分配和导引绑定，但 hold 端的覆盖与分配退化仍然存在。

这组三臂是闭环系统效果对照。首个分配计划发布后，资源控制会改变平台状态和后续传感器观测，
三臂的传感器流随之分叉。因此它不能冒充完全冻结输入下的上游因果证明。source-only 的 D2/D3
变化也说明来源键会改变下游治理路径；D1 模块测试只证明 source-only 不改变 D1 自身状态和
计数。正式因果分离仍需冻结同一上游扫描流，再分别重放三臂消费者。

## 4. D1 抑制路径

### 4.1 代码位置

当前路径位于 `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/fusion.py`：

- 2080-2184 行：构造门内矩阵、最大匹配、结构歧义分量，并从 `assignments` 删除分量观测；
- 2242-2444 行：识别交替环、自由行路径、自由列路径和完整允许边分量；
- 1018-1049 行：歧义观测被标记 processed 后直接 `continue`，跳过既有航迹更新和新生；
- 2694-2727 行：累计 evidence、成员、延迟新生和 prediction-only 诊断；
- 4040-4061 行：候选启用时为发布航迹增加不透明来源键。

### 4.2 hit、miss 和 birth

| 分类 | D1 直接行为 | 数量 | 离线判断 |
| --- | --- | ---: | --- |
| 参考 hit/update | 从最大匹配中删除后，在 1022-1033 行跳过 `_apply_associated_observation()` | 76 | 69 次正确更新被阻断，7 次错误更新被阻断 |
| prediction-only/miss 暴露 | 相关成员只预测，不增加 hit，不写入观测谱系 | 91 | 表示成员暴露次数，不等于 91 个不同目标 |
| 自由列 birth | 歧义自由列被标记 processed，跳过 `_create_track()` | 1 | 一个真实目标的新生延迟 0.2 s |

D2 报告的 prevented hit/miss/birth `69/69/4` 是 D2 身份保持消费者的下游计数。D1 可以证明
哪些观测和成员被置为 prediction-only，不能把 D2 的 lease、hit/miss 状态机和四次 birth 阻断
写成 D1 内部行为。

### 4.3 逐扫描离线分类

| 量测时刻（s） | 正确参考更新被阻断 | 错误参考更新被阻断 | D1 新生延迟 |
| ---: | ---: | ---: | ---: |
| 0.2 | 9 | 1 | 1 |
| 0.4 | 8 | 2 | 0 |
| 0.6 | 8 | 0 | 0 |
| 0.8 | 9 | 0 | 0 |
| 1.0 | 10 | 0 | 0 |
| 1.2 | 5 | 2 | 0 |
| 1.4 | 8 | 0 | 0 |
| 1.6 | 6 | 1 | 0 |
| 1.8 | 6 | 1 | 0 |
| 合计 | 69 | 7 | 1 |

候选共产生 46 个分量、77 条阻断观测和 91 次成员 prediction-only 暴露。其中 30 个分量含
交替环，15 个含自由行路径，1 个含自由列路径。

## 5. 新生审计

### 5.1 D1 延迟新生

唯一 D1 延迟新生为：

- 观测：`radar-s000002-d0060`
- 量测时刻：0.2 s
- 离线目标：`TGT-0061`
- 后续新生：0.4 s 的 `radar-s000003-d0059`
- 后续 D1 航迹：`global_track_200`

该观测不是假目标，也不是已有 D1 航迹的重复观测。当前策略造成一个雷达周期的真实覆盖延迟，
但终态 D1 航迹总数恢复为 202。

### 5.2 D2 四次 prevented birth

D2 在 1.4、1.6、1.8 和 2.0 s 各记录一次 prevented birth。四次均来自同一结构分量中的
`global_track_164` 和 `global_track_201`。离线真值把两条 D1 航迹都映射到
`TGT-0171`，因此这是同一真实目标的重复航迹新生尝试。

本结论只说明“四次阻断没有分别损失四个真实目标”。是否继续阻断、何时解除身份 lease、如何
合并两条重复航迹属于 D2/runtime。D1 不应依据该结果放宽自由列新生。

## 6. 状态退化

对首次歧义前已经存在、且可在两端可靠连接离线真值的 13 条成员航迹进行定向诊断：

| 指标 | 基线 | 候选 | 变化 |
| --- | ---: | ---: | ---: |
| 平均位置误差 | 25.217 m | 34.184 m | 增加 35.6% |
| 位置协方差迹中位数 | 156.217 | 458.349 | 约 2.93 倍 |

典型结果：

- `global_track_057` 的雷达命中从 9 降到 1，位置误差从 17.11 m 增至 35.28 m；
- `global_track_079` 的雷达命中从 9 降到 1，位置误差从 2.98 m 增至 36.03 m；
- `global_track_185` 的雷达命中从 9 降到 2，位置误差从 6.55 m 增至 16.17 m。

协方差增长符合 prediction-only 的保守方向，没有产生虚假确定性。问题是均值状态长期得不到
正确雷达修正，导致位置误差和下游门控风险增加。

## 7. 身份中性状态修正候选

### 7.1 使用条件

已实现候选只在同时满足以下条件时运行：

1. 分量成员数和观测数相等，最大匹配基数等于成员数；
2. `free_row_count=0` 且 `free_column_count=0`；
3. `component_kinds` 只包含 `alternating_cycle`；
4. 全部分量观测来自同一 sensor、scan、量测时刻、到达时刻和 NED 坐标合同；
5. 量测未过期，不是 OOSM 重放，不含重复或冲突 source claim；
6. 不使用未观测的径向速度，不执行成员速度修正；
7. 分量规模不超过预注册的 `K_max`，质心创新和集合形状差均通过独立门限；
8. 新 generation 的任一校验失败时恢复该帧精确重放的 prediction-only 基线，不能退化为
   参考匹配更新；
9. 同代、倒退代和固定滞后窗口外重放 fail closed，不改变当前已发布状态。

### 7.2 数学规则

设分量有 \(m\) 个成员，成员预测位置为 \(p_i^-\)，观测位置为 \(z_j\)。定义置换不变质心：

\[
\bar p^-=\frac{1}{m}\sum_{i=1}^{m}p_i^-,
\qquad
\bar z=\frac{1}{m}\sum_{j=1}^{m}z_j,
\qquad
r_c=\bar z-\bar p^-.
\]

质心创新必须满足：

\[
d_c^2=r_c^\mathsf{T}S_c^{-1}r_c\leq\gamma_c.
\]

集合形状使用去质心二阶矩：

\[
C_p=\frac{1}{m}\sum_i(p_i^--\bar p^-)(p_i^--\bar p^-)^\mathsf{T},
\quad
C_z=\frac{1}{m}\sum_j(z_j-\bar z)(z_j-\bar z)^\mathsf{T},
\]

并要求 \(\lVert C_z-C_p\rVert_F\leq\tau_{\text{shape}}\)。通过后，对全部成员施加同一有界平移：

\[
p_i^+=p_i^-+\alpha\,\operatorname{clip}(r_c,r_{\max}),
\qquad
v_i^+=v_i^-,
\qquad 0\leq\alpha\leq1.
\]

共同平移保证 \(p_i^+-p_k^+=p_i^--p_k^-\)，因此不会通过成员排列隐式提交身份。令
\(G=[I_3\;0]^\mathsf{T}\)，协方差候选为：

\[
P_i^+=P_i^-+
G\left(
\alpha^2\Sigma_c+
\lambda_{\text{shape}}\lVert C_z-C_p\rVert_F I_3+
q_{\min}I_3
\right)G^\mathsf{T}.
\]

\(\Sigma_c\)、\(\lambda_{\text{shape}}\) 和 \(q_{\min}\) 必须非负，因此：

\[
P_i^+-P_i^-\succeq0.
\]

共同平移会在成员之间引入相关误差。当前 D1 不维护分量交叉协方差，因此输出必须继续标记
`cross_covariance_available=false`，并把共同平移不确定度加入每个成员边缘协方差。

上述 \(p_i^-\) 用于量测时刻的质心创新。发布状态另采用帧替换语义。设
\(x_{i,k}^{\mathrm{base}},P_{i,k}^{\mathrm{base}}\) 是只由正式观测历史精确重放到本帧
发布时间的状态，则：

\[
x_{i,k}^{\mathrm{pub}}
=x_{i,k}^{\mathrm{base}}+
\begin{bmatrix}\Delta p_k\\0\end{bmatrix},
\qquad
P_{i,k}^{\mathrm{pub}}
=P_{i,k}^{\mathrm{base}}+
\begin{bmatrix}\Delta P_{\mathrm{pos},k}&0\\0&0\end{bmatrix}.
\]

上一帧共同修正不写入观测历史和检查点，不会进入下一帧基线。`_predict_all_to()` 在下一份
证据到来前传播当前临时发布状态；`_state_at()` 始终查询正式重放状态。正常身份明确量测接受
后，标准重放包含该正常量测并替代临时修正。

### 7.3 安全合同

候选即使执行状态修正，也必须保持：

- 不增加 hit，不写 observation lineage，不增加 source support；
- 不改变身份提交状态，不选择或发布 observation-to-member 边；
- 不新建或删除航迹，不改写 `global_track_id`；
- 不提升航迹质量分级，不刷新身份 freshness；
- 保留 `measurement_timestamp` 和 `arrival_timestamp`；
- 状态、协方差有限，协方差对称半正定且相对先验不收缩；
- 同一 evidence/replay generation 只能应用一次，倒退 generation 不得重新生效；
- generation 清理不得使固定滞后有效期内旧证据重新生效；
- 默认关闭时逐字段保持当前行为；
- 在线代码拒绝 truth、actor、target 和离线标签字段。

### 7.4 当前实现

构造参数
`radar_assignment_ambiguity_neutral_centroid_correction=False` 默认关闭，并要求
`radar_assignment_ambiguity_hold_evidence=True`。与在线 truth hint 模式同时启用会在构造
阶段拒绝。当前实验默认值为：

- `neutral_centroid_max_component_size=8`；
- `neutral_centroid_gain=0.5`；
- `neutral_centroid_max_translation_m=30.0`；
- `neutral_centroid_gate_chi2=16.26623619623813`；
- `neutral_centroid_shape_gate_m2=2500.0`；
- `neutral_centroid_shape_inflation_scale=0.05`；
- `neutral_centroid_min_position_variance_m2=0.25`；
- `neutral_centroid_generation_registry_max_entries=1024`。

这些数值是模块实验默认值，不是雷达实测标定结果。布尔、整数和实数参数均做严格类型、有限性
和范围校验，`K_max` 可配置范围为 2 至 256，generation 水位容量可配置范围为 1 至
1,000,000。候选使用成员和观测的质心边缘协方差构造
\(S_c\)，以质心马氏距离和去质心二阶矩 Frobenius 范数双门控。通过后按向量范数截断质心创新
并乘以增益。位置边缘协方差增加
\(\alpha^2\Sigma_c+(\lambda_{\text{shape}}\Delta_{\text{shape}}+q_{\min})I_3\)；速度状态和
速度协方差块不变。

每个严格递增的新 generation 先注册为最大已见代，再从正式观测历史重建全部成员在当前
发布时间的基线。更新前对全部成员计算候选协方差。只要一个成员出现非有限状态、非半正定
协方差、上限越界、相对当前帧基线收缩或质量分级变化，整个分量原子拒绝并发布基线。成功时
只发布 `基线 + 本帧共同修正`，不把任何分量观测追加到成员历史。结构歧义侧车继续表达身份层
prediction-only，`cross_covariance_available=false`；共同状态修正通过独立审计计数记录。

每个组件水位只保存 `max_seen_generation`、`max_applied_generation` 和最近量测时刻。同代拒绝
为 `duplicate_evidence_generation`，倒退代拒绝为 `regressed_evidence_generation`。条目只有
在最近量测时刻早于 `current_time-buffer_horizon` 时才能淘汰；被淘汰证据再次进入时同时因
超出固定滞后窗口拒绝。容量满且没有过期条目时，新组件 fail closed。

候选显式启用时，审计输出请求/生效状态、参数、候选/成功/拒绝分量数、成功成员数、重复/倒退
generation、水位表当前/峰值条目、淘汰、容量拒绝、线性输入操作数、最大分量规模、最大质心
NIS、最大形状差、最大平移、拒绝原因分布及最近拒绝原因；默认关闭时不增加候选审计字段。

## 8. 模块测试

候选实现已增加以下测试：

1. 平衡 `2x2` 分量对成员和观测输入排列保持不变；
2. 所有成员只施加同一平移，相对位置和速度逐元素不变；
3. hit、lineage、source support、质量分级和身份状态不变；
4. 协方差有限、对称、半正定，且 \(P^+-P^-\) 半正定；
5. free-row、free-column 和非纯交替环继续 fail closed；
6. 未观测径向速度占位值不参与状态修正；
7. 过期、OOSM、重复和冲突证据不执行或重复执行修正；
8. truth/actor/target 字段继续被在线合同拒绝；
9. 默认关闭时输出、序列化和诊断逐字段与当前基线一致；
10. 连续三代使用同一质心创新时，发布偏移保持单帧大小，不累加旧临时修正；
11. 新 generation 校验失败时恢复精确重放基线；
12. 连续 hold 后的正常唯一量测通过标准重放替代临时修正，candidate sidecar 不重复计入
    hit、lineage、source support 或质量；
13. 24 代同组件只保留一个水位条目，重复和倒退代状态逐元素不变；
14. 固定滞后窗口内条目不淘汰，容量满时拒绝新组件，窗口外淘汰后旧证据仍拒绝；
15. 200 规模稀疏门图不引入二次全量复制或不可接受的额外复杂度。

修复前复现用例在每帧固定 30 m 质心创新、增益 0.5 时得到首帧约 15 m、第二帧约 30 m 的
错误累加。修复后三帧均保持单帧偏移。2026-07-23 专项结果为 `62 passed`，D1 全量结果为
`282 passed in 17.81s`。测试还覆盖严格参数校验、候选要求 hold、与 truth hint 模式互斥、
`K_max` 边界和按成员数加观测数计量的线性输入操作数。该测试证明模块合同，不证明系统效果。

## 9. A/B 验收门槛

新候选应先比较“当前 hold-only”与“hold + 身份中性状态修正”，再与默认基线比较。验收门槛
预注册如下：

1. 硬安全项：在线真值使用、`global_track_id` 改写、未提交来源绑定违规、重复分配、非有限
   状态和过期 evidence 重放均为 0；
2. D1 语义：正确 reference update 不直接恢复为身份绑定；free-column 的真实新生延迟不得比
   hold-only 更长；假目标新生不得增加；
3. 身份：严格 IDSW 不高于 hold-only，95% bootstrap 置信区间上界不高于默认基线；
4. 连续性：相对 hold-only 至少恢复其相对基线损失的 75%；多 seed 下候选与默认基线的航迹、
   覆盖连续性差值 95% 置信区间下界不得低于 -0.005；
5. 下游可用性：同 seed 的 D2 航迹数和 D3 分配数不得低于 hold-only；高威胁未分配率不得
   增加；
6. 状态：本审计 13 条成员口径的平均位置误差和位置协方差迹均不得劣于 hold-only，正式验收
   另使用全部可评估目标的均方根误差、归一化估计误差平方和覆盖率；
7. 成本：D1 融合 P95 不得增加超过 5%；虽然水位表已有硬容量和固定滞后清理，系统长时 RSS、
   淘汰率和容量拒绝率仍需实测。

seed 1100 只用于缺陷解释，不能再作为唯一晋级样本。正式候选应使用未见 seed，并把单 seed
诊断与多 seed 统计分开报告。

## 10. 责任边界与混杂因素

D1 可以确认：

- 46 个分量、77 条阻断观测、91 次 prediction-only 成员暴露和 1 次 D1 新生延迟；
- 76 次参考更新中，离线有 69 次正确、7 次错误；
- 唯一 D1 延迟新生是真实目标，覆盖在下一雷达周期恢复；
- 选定歧义成员的状态误差和协方差增长；
- 当前整分量跳过 update/birth 的具体代码路径。

D2/runtime 负责：

- prevented hit/miss/birth `69/69/4` 的身份 lease 语义；
- 四次重复新生阻断后的合并、恢复和 lease 到期；
- D2 航迹数、身份提交覆盖率和严格 IDSW；
- 三条 stale recovery 阻断及来源 freshness。

D3 和 main 负责 D3 分配数、episode 调度和系统连续性汇总。D1 不据此修改 D2/D3 逻辑。

另有一个 A/B 混杂因素：候选开关启用时会给全部发布航迹增加不透明 `source_key`。在首个
歧义 evidence 被消费前，D2 航迹数已经出现基线 195、候选 193 的差异。D1 已于
2026-07-23 增加默认关闭的 `publish_opaque_source_key` 控制参数。它允许在 hold 关闭时只发布
五个不透明来源字段，不产生 evidence，不执行 prediction-only，也不改变 hit/miss/birth、
状态、协方差或重放。该阶段专项 `25 passed`，当时 D1 全量 `245 passed in 17.48s`。main
后续闭环三臂表明 source-only 的 D2/D3 和 IDSW 会变化，但首个计划后传感器流随控制分叉。
因此 D2 消费来源键的上游因果影响仍需固定同一扫描流重放，不能由该闭环三臂单独证明。

## 11. 共同质心 clean 复核

main 先在未提交工作树完成共同质心开关接线和 seed 1100 dirty 开发诊断，制品位于
`/tmp/MSM-neutral-centroid-gate-20260723`。该历史诊断首次暴露了 46 个候选全部被拒的
零 treatment 现象，不能作为 clean acceptance。

现已在固定提交 `7e15dac9cdaf6743999dfe045a70676fd31a17d6` 完成 clean 同输入复跑。
两臂均为 `repository_dirty=false`、200v200、2.2 s、seed 1100、`recon_count=2`，
`config_sha256=20ef5248...b840`。控制臂为 source-key 加结构歧义 hold，候选臂只增加
identity-neutral centroid。clean 制品位于：

- `/tmp/MSM-identity-gate-results-7e15dac/hold_only`
- `/tmp/MSM-identity-gate-results-7e15dac/hold_plus_centroid`

两臂 `scenario_config.json` 和离线真值逐字节一致。89 批 `sensor.observations` 规范化
SHA-256 均为 `bc064834...51518`，D2 在线记录 SHA-256 均为
`da7089fa...f8d2f`。完整总线文件包含候选审计字段和不同 episode 标识，因此其文件哈希
不同；这不构成外部传感器输入差异。

| 指标 | hold-only | hold+共同质心 |
| --- | ---: | ---: |
| D1/D2/D3 | 202/201/186 | 202/201/186 |
| strict IDSW | 3 | 3 |
| track continuity | 0.8266666667 | 0.8266666667 |
| coverage continuity | 0.8283333333 | 0.8283333333 |
| available/unavailable/uncommitted mapping | 1491/218/76 | 1491/218/76 |
| identity commitment coverage | 0.9574706212 | 0.9574706212 |
| duplicate assignment | 0 | 0 |
| 未承诺来源/候选绑定违规 | 0/0 | 0/0 |
| D3 拒绝目标数/一次 hold 事件累计撤回或清除运行时绑定数 | 11/13 | 11/13 |
| candidate/applied/rejected | 不适用 | 46/0/46 |
| generation 水位 current/peak | 不适用 | 8/8 |
| eviction/capacity rejection | 不适用 | 0/0 |
| finite / online truth use | true / 0 | true / 0 |

46 个组件中，30 个以 `oosm_scan` 拒绝，16 个以 `unbalanced_component` 拒绝。线上门控没有
允许一次共同质心修正，候选臂相对 hold-only 没有 treatment。两臂结果相同只证明当前实现
fail closed，不能证明共同质心修正恢复连续性、覆盖或映射可用性。

新的 D3 身份承诺安全门已阻断未承诺目标继续分配、视觉绑定或导引，因而两臂下游绑定违规为
0。该安全结果属于身份承诺合同，不是 D1 共同质心收益。clean 复跑仍为零 treatment，按停止
条件不继续 seeds 1101/1102。候选保持默认关闭，P1 继续开放。

### 11.1 冻结扫描边界诊断

D1 使用模块内确定性输入构造三类扫描，并先经过 governed replay 序列化和回读，再交给
`SensorScanFrame`、`ScanInputOrganizer` 和在线批融合入口。控制臂关闭共同质心，候选臂只在
诊断实例中开启。两臂按扫描编号、`measurement_timestamp`、`arrival_timestamp` 和观测数
核对为同一冻结序列。

| 输入 | 成员/观测 | free row/column | 施加 | 结果 | 候选-控制协方差差最小特征值 |
| --- | ---: | ---: | ---: | --- | ---: |
| 同步平衡纯交替环 | 2/2 | 0/0 | 1 | 平移模长 `15.000000 m` | `0.479767799918` |
| 乱序平衡纯交替环 | 2/2 | 0/0 | 0 | `oosm_scan` | `-0.0071928353214153066` |
| 数量不平衡分量 | 2/1 | 1/0 | 0 | `unbalanced_component` | `-0.004617076466238031` |

同步场景的共同平移约为 `[15.000000, 0.000000, 0.003278] m`。成员速度、相对位置、hit、
lineage、identity 和 `global_track_id` 均保持不变；候选相对控制臂的协方差差最小特征值为
`0.4797678`。乱序扫描量测/到达时刻为 `0.300/0.650 s`，进入融合前时刻为
`0.400 s`，扫描组织器记录 1 次重排。数量不平衡场景的最大匹配基数为 1。

两个拒绝场景都是 `applied_component_count=0`，共同质心公式没有产生平移或协方差膨胀，
因此共同质心 correction 未施加。候选臂仍在拒绝后各执行一次 publication-base replay +
replace，以清除旧临时修正。控制臂的分段预测与候选臂从观测历史单段重放得到的发布基准使用
当前非半群等价的离散 CV 过程噪声，因而产生表中的有限协方差差值。诊断逐元素确认候选-控制
差值与 replacement 前后差值 bitwise 一致。不能声称拒绝路径对状态和协方差严格无副作用；
这些差值只作诊断，两项均为 `candidate_not_promoted`。

专项 `5 passed`，D1 全量 `287 passed in 18.03s`。制品位于
`research_modules/d1_sensor_fusion/reports/structural_ambiguity_centroid_replay_20260723/`。
协方差不收缩只对实际施加的同步场景作验收；拒绝场景仍保留控制臂/候选臂数值差异用于解释
重放发布基准，不据此放宽门控。该结果不是 AirSim、真实匿名 200 对 200、多 seed 或算法收益
证据。

## 12. 建议

当前 v3 和身份中性共同质心修正均保持默认关闭。独立来源键控制臂、共同质心模块候选及单元
测试已完成；main 的 seed 1100 闭环三臂已经给出系统效果对照，但上游传感器流在首个计划后
分叉，不能替代冻结输入因果重放。共同质心开发接线也已完成，但首个开发门槛为零 treatment。
固定提交 `7e15dac` 的 clean 同输入复跑已经确认该零 treatment，不再重复 seeds 1101/1102。
受控冻结扫描现已证明同步平衡分量存在有效施加窗口，并确认 OOSM 与数量不平衡边界继续拒绝。
下一步不直接恢复当前 replay/replace 语义下的系统 A/B。publication overlay A1 纯函数原型
已完成：拒绝 overlays 为空且装配直接返回原规范业务序列，接受只复制 DTO；原型不调用
replay/replace，也不接 `FusionAdapter`。main 已在提交 `2b976a7` 的独立默认关闭审计
shadow 中显式接入准备对象。业务非干预和禁止写入审计通过，但墙钟开销 `+80.8829%`，
46 条 evidence 没有 accepted treatment，A2 不准入。不再使用新的真实匿名冻结扫描或未见
seed 扩大该候选；不得通过忽略时序或放宽满基数门制造 treatment。

free-row、free-column、大分量、过期/OOSM 量测、重复/冲突来源、身份字段、质心门限失败和
形状不一致分量继续 prediction-only。不得依据四次 D2 重复 birth 放宽 D1 自由列新生，也不得
用离线真值参与在线门控或状态更新。候选在完成多 seed 连续性恢复、身份不退化、状态一致性、
下游可用性、P95 和长时水位表/RSS 验收前不得晋级。

## 13. 下一候选设计与 A1 实现状态

完整设计见
`research_modules/d1_sensor_fusion/docs/STRUCTURAL_AMBIGUITY_NEXT_CANDIDATE_DESIGN_CN.md`。
该设计比较三条路线：

1. A 使用 detached publication overlay。A1 已在提交 `de73cb2` 实现纯函数原型：接受时只改
   发布 DTO，拒绝时 overlay 为空并直接使用规范快照；state/covariance、history、checkpoint、
   cache、lineage/source support 和 `global_track_id` 均不修改。D1 准备对象优化已完成；
   main A2 显式接线的业务非干预通过，但性能门和有效 treatment 门失败，A3/A4 未实现；
2. B 把共同质心变成 fixed-lag measurement-time 事件。当前
   `Q(h)=G(h)qG(h)^T` 的单段与分段传播不等价，零更新事件也会改变协方差分段；事件总排序、
   过程噪声分段和一致性验收冻结前，B 不进入在线实现；
3. C 保持 D1 只发布 evidence，由 D2 后续规划有界概率/多假设消费。D1 source token 不升级
   为 canonical `global_track_id`，无交叉协方差时不得做独立状态融合。

设计规定组件、成员、观测、候选边和未来历史事件的确定性排序键，并保持双时间戳、平衡满基数
门、generation 有界幂等及 lineage/source support 不变。A1 聚焦 `7 passed` 验证 2/3/5
成员、拒绝透传、全排列、幂等/冲突/容量和输入不变，D1 全量 `294 passed`。A1 没有修改
`fusion.py`、运行开关或默认路径，experimental decision 不是在线 schema。

A2 已在冻结扫描上证明归一化业务发布与 control 等价，并记录滤波内部禁止写入摘要、阶段
计时和有界水位；性能门失败且零 treatment，按停止条件不进入 A3/A4。seeds 1101/1102
继续停止。A1 完成和 A2 安全子门通过均不改变在线共同质心候选的
`candidate_not_promoted` 状态。

## 14. 准备对象与只读 metadata 专项

2026-07-23，D1 在不改变 A1 数学、拒绝顺序、安全门和 decision schema 的条件下加入一次性
规范发布准备对象。对象对完整航迹集合执行校验和 SHA-256 描述，evaluation 与 accepted
shadow assembly 只读复用。显式对象与输入序列或成员对象不匹配时以
`prepared_canonical_publication_mismatch` 拒绝；拒绝装配仍返回原序列对象。

准备对象采用冻结字段和不可变描述符，只保存航迹索引、对象绑定和摘要，不保存可修改的
`GlobalTrack`、metadata 或 NumPy 引用。每个复用边界重新计算每条航迹完整规范载荷
SHA-256。完整 metadata、lineage、source support、identity、双时间戳、state/covariance 和
`global_track_id` 均继续进入校验和强摘要。工作量计数明确报告完整描述轮次、完整性复核轮次
与摘要数量，禁止通过只处理成员子集或弱哈希换性能。

接受装配用递归值语义复制处理嵌套只读 `Mapping`、tuple、frozenset、NumPy 数组和标量。
200 航迹固定夹具实际形成 accepted shadow，完整描述轮次为 1，完整载荷复核为 2 次、
400 条航迹摘要；metadata 内容保持，数组与规范输入脱离。state、covariance、嵌套 metadata、
source support、identity、全局编号、时间戳和分级的修改均阻断复用。2/3/5 成员 decision
SHA-256 与提交 `de73cb2` 基线逐字节一致。聚焦测试 `21 passed`，D1 全量
`308 passed in 19.69s`。

main 已在提交 `2b976a7` 显式接入准备对象，并对 200v200、seed 1100、2.2 s、
`recon_count=2` 完成成对开发复跑。9/9 次评估均记录显式 prepared handle 和内容完整性
匹配；46 条 evidence 为 0 accepted/46 rejected，拒绝原因均为 `oosm_scan`。过滤 9 条专属
审计记录并按既有跨构建规则归一化计划编号和总线序号后，3294/3294 条业务记录逐条一致，
归一化 SHA-256 同为 `bb7eabca...c3855a2`。truth NPZ、离线 truth labels 和 proximity
文件分别一致。D1/D2/D3 终态均为 `202/201/186`，finite=true；错误、禁止写入、D2/D3
消费和在线 truth 使用均为 0。

control/shadow 墙钟 `10.712171729/19.376483415 s`，开销 `+80.8829%`；RTF
`0.205374/0.113540`，shadow 总 P95 `1532.999 ms`。before digest、prepare、evaluate、
after digest、assemble、log 均值分别为
`224.461/345.095/195.421/207.312/0.00247/0.0973 ms`。最大载荷
`11,275,939 bytes`，generation 水位 `8/1024`。两份 manifest 均记录
`repository_dirty=true`，只作开发证据。安全接口和业务非干预子门通过；性能门和有效
treatment 门失败。A2 不准入，A3/A4 与 seeds 1101/1102 继续停止。

## 15. 原子 publication overlay 接口

2026-07-24，D1 在三步 prepared-handle API 之外增加单个 experimental/offline 原子入口。
该入口在一次同步调用中内部持有描述符，完成 prepare、evaluate、detached shadow assemble
和 post-integrity verify。公开结果不含内部描述符，只给出冻结准备摘要、decision、可选
shadow、规范与 shadow 摘要、后置完整性结果和工作量计数。现有三步公共 API 及其每次复用
完整内容强校验保持不变。

200 航迹 accepted 固定夹具只执行 1 次完整 `_describe_tracks` 和 1 次操作后完整规范复核，
后置复核摘要数为 200。accepted shadow 单独复制并摘要 200 条 detached 航迹；rejected 路径
不进入装配，不构造或序列化 shadow。完整 metadata、lineage/source support、identity、
`last_nis`、全局编号、时间戳、分级、state/covariance、NED 和禁止身份字段覆盖没有减少。

调用内部发生 state/covariance 数组、嵌套 metadata、source support、identity、`last_nis`、
全局编号、时间戳或分级变化时，post-integrity 检查阻断返回，丢弃 provisional shadow，
decision 以 `prepared_canonical_publication_mismatch` fail closed，generation 状态恢复到
调用输入。只读嵌套 Mapping、tuple、frozenset 和 NumPy 值可按值复制，规范对象与 shadow
之间没有数组或 metadata 引用共享。

公开结果可由标准 JSON 编码，并提供确定性字节形式。canonical/shadow 发布摘要使用相同的
完整航迹摘要清单语义；装配异常也丢弃 shadow、恢复输入 generation 状态。

聚焦测试为 `36 passed`，D1 全量为 `324 passed`。2/3/5 成员
canonical decision bytes 与 `de73cb2` 基线一致。该结果只证明 D1 原子接口和工作量边界；
main 尚未接入或复跑。`2b976a7` 的 A2 性能失败和零有效 treatment 结论继续有效，A2 不准入，
A3/A4 与 seeds 1101/1102 继续停止。
