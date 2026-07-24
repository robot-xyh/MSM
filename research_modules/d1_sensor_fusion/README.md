# D1 Sensor Fusion Module

Offline research module for radar, acoustic, EO, and optional synthetic lidar heterogeneous observation fusion. The module estimates six-state NED `GlobalTrack` objects with covariance.

## 当前性能与治理证据（2026-07-24）

### 第二十二阶段：协方差成对限制向量化

最新 seed 1100 冻结输入剖析包含 89 个扫描、2,035 条匿名观测和 202 条终态航迹。输入
SHA-256 为
`54bed9d7f03497967c3f8478a9e0cf1385e85bcc512bf769df849b7b1ab3e0ec`，在线 truth
使用为 0。原路径共调用 `_limit_covariance_diagonal()` 14,868 次，其中状态协方差
12,833 次；10,832 次来自状态推进后的预测协方差，1,789 次来自更新后重放，202 次来自
航迹新生。预测和重放都改变了协方差，不能跳过上下界、安全对称化或原因审计。

实际局部热点是每个 `6x6` 状态协方差对 15 个上三角元素逐一调用 `np.clip`。当前实现保留
原标量循环作为 `vectorized_covariance_limit=False` 的 reference，并默认通过
`Scalable3DFusionAdapter(vectorized_covariance_limit=True)` 使用批量上三角裁剪。静态
三角索引可复用，状态和协方差本身不缓存。两条路径使用同一公式：

```text
limit(i,j) = 0.999 * sqrt(max(Pii, 0) * max(Pjj, 0))
Pij = clip(Pij, -limit(i,j), limit(i,j))
Pji = Pij
```

对角 floor/ceiling、reason 顺序、对称化、非法状态协方差重置和观测入口有限/对称/半正定
fail-closed 均未改变。开关只用于冻结输入 A/B 和回归，不改变 NED、双时间戳、6 s
fixed-lag、观测数量、关联门限、来源谱系、质量分级或 `global_track_id`。

同一输入先预热，再交错运行 5 轮。reference/optimized 的纯融合 P50 为
`3.011440/2.614061 s`，P95 为 `3.023308/2.660813 s`，对应加速
`1.152x/1.136x`；5/5 轮优化路径更快，均值由 `3.001196 s` 降至
`2.610975 s`，下降 `13.00%`。cProfile 中 `_limit_covariance_diagonal` 累计耗时由
`1.047145 s` 降至 `0.426826 s`，下降 `59.24%`；`_predict_all_to` 由
`1.098530 s` 降至 `0.584526 s`。

预热、5 轮交错和两条剖析运行均保持逐扫描状态、协方差、双时间戳、来源谱系、航迹分级、
操作计数和累计诊断严格一致；终态 `GlobalTrack` 与 consistency evidence SHA-256 也一致。
另以 seed 1000 的 10 s、771 扫描、11,889 观测夹具只运行一对长语义对照。两臂均触发
4,009 次 fixed-lag rebase 和 11,888 条 OOSM；逐扫描、延迟审计、操作计数、终态航迹和证据
严格一致。长夹具不用于性能统计。专项 `18 passed`，D1 全量 `342 passed in 19.73s`。

本项关闭 D1 内部标量裁剪热点，不关闭系统实时预算。结果来自当前未提交 D1 工作树上的
单 seed 三维质点冻结回放，不是 clean full-stack、多 seed、AirSim、传感器精度或
RMSE/NEES/NIS 证据。main 仍需在固定提交上执行 clean 全栈同输入复核。

### 第二十一阶段：A2 原子 shadow clean 成对复核

main 已在 clean commit
`7cc2d0cfd598a72d60c6ba8c7d4a283f4e5a897d` 将 A2 审计旁路改用原子入口，并完成
seed 1100、200v200、2.2 s、`recon_count=2` 的 control/atomic-shadow 成对运行。两份
manifest 均为 `repository_dirty=false`。control/shadow 墙钟为
`10.735151270986535/19.449935468961485 s`，开销比为 `0.8117989190825889`
（`+81.1799%`）；实时倍率为 `0.20493423375838704/0.1131109151241553`。

shadow 产生 9 条审计发布和 46 条决策，结果为 0 accepted、46
`oosm_scan` rejected、0 error。9/9 次 post-integrity 通过，atomic failure 和 materialized
shadow 均为 0。单次审计总时延 P50/P95/max 为
`1024.838/1536.429/1549.436 ms`。D1/D2/D3 终态均为 `202/201/186`；在线 truth 使用、
禁止写入、shadow 被 D2/D3 消费和 `global_track_id` 序列变化均为 0。

本轮关闭了默认关闭审计旁路的原子调用、安全隔离和业务非干预子门，没有关闭性能和有效性门。
墙钟开销远高于 `+5%` 门限，且没有 accepted treatment，A2 继续不准入。全拒绝场景中，旧
prepared-handle 路径本来就会在 `accepted_count=0` 时跳过 assemble；原子入口因而没有第二次
装配边界复核可消除。当前主要开销仍来自禁止写入前/后完整摘要，以及原子调用内的规范准备和
post-integrity。A3/A4 与 seeds 1101/1102 继续停止。

### 第二十阶段：A1 原子 publication overlay 接口

状态：`IMPLEMENTED_UNIT_TESTED_OFFLINE_ATOMIC_OPTIMIZATION`。D1 新增
`run_experimental_centroid_publication_overlay_atomically()`，在一个同步、显式
experimental/offline 调用中完成规范准备、决策、detached shadow 装配和操作后完整性复核。
内部 prepared handle 不跨调用方可控边界。返回的冻结结果只公开准备摘要、决策、脱离副本、
规范与 shadow 摘要、后置完整性结果和确定性工作量计数，不公开内部描述符或规范对象引用。

现有 prepare/evaluate/assemble 公共 API 保持不变。显式 prepared handle 每次跨公共调用边界
仍执行完整内容强校验。原子入口只省去同一次调用内部 evaluate/assemble 之间的重复规范载荷
复核：正常 200 航迹路径为 1 次完整 `_describe_tracks`、1 次操作后完整性复核和 200 条规范
航迹复核摘要。accepted 路径另对 200 条 detached shadow 计算发布摘要；rejected 路径不构造、
复制或序列化 shadow 全航迹。

操作后复核覆盖 state/covariance、嵌套 metadata、lineage/source support、identity、
`last_nis`、`global_track_id`、时间戳、分级、NED 和禁止身份字段所形成的完整规范内容。
调用内部发生数组或嵌套容器原地变化、字段重绑定时，原子结果丢弃 provisional shadow，撤销
generation 状态推进，并返回 `prepared_canonical_publication_mismatch` 拒绝。接受输出仍保持
ID、速度、成员相对位置、metadata 值语义和协方差不收缩；嵌套只读 `Mapping`、tuple、
frozenset、NumPy 数组和标量均为脱离复制。

公开结果的 `to_dict()` 已冻结为标准 JSON 可表示结构，`canonical_bytes()` 提供确定性编码。
canonical 与 shadow 发布摘要采用同一份按成员键排序的完整航迹摘要清单，二者可以直接比较；
装配异常与 post-integrity 失败均不公开 shadow，也不提交 generation 状态。

2026-07-24 聚焦测试为 `36 passed`，D1 全量为
`324 passed`。2/3/5 成员 canonical decision bytes 与提交 `de73cb2` 基线一致；
200 航迹工作量计数为 1 次完整描述、200 条描述摘要、1 次后置完整性复核、200 条规范复核
摘要、200 条 shadow 摘要。OOSM、数量不平衡、重复代和倒退代保持 fail closed。测试还覆盖
state/covariance、嵌套 metadata、source support、identity、`last_nis`、全局编号、时间戳和
分级的调用内篡改，以及结果冻结和规范引用隔离。

main 已按上节完成原子入口的 clean 成对复跑。安全边界闭合，但性能门和有效 treatment 门
失败，A2 不准入。不得用模块工作量下降推断系统 P95 已通过。本次不修改 `fusion.py`、
默认开关、在线 schema、共同质心数学或 AirSim 适配接口。

### 第十九阶段：A1 规范发布准备对象与只读 metadata 装配

状态：`IMPLEMENTED_UNIT_TESTED_OFFLINE_OPTIMIZATION`。D1 增加
`prepare_experimental_centroid_canonical_publication()`，对同一规范发布快照只执行一次完整
航迹校验和摘要计算。准备对象显式标记为 experimental/offline，采用冻结字段和不可变工作量
计数，不保存可由外部改写的 `GlobalTrack`、metadata 或 NumPy 引用。调用方可把该对象同时传给
`evaluate_experimental_centroid_publication_overlays(..., prepared_publication=...)` 和
`assemble_experimental_centroid_shadow_tracks(..., prepared_publication=...)`。对象与输入序列
或成员对象不匹配时 fail closed。每个复用边界还会重新计算每条航迹完整规范载荷的 SHA-256，
因此 state/covariance、metadata、source support、identity、全局编号、时间戳或分级的原地及
重绑定变化也会 fail closed。旧入口继续兼容；同一输入的 evaluation 会携带内部准备对象，使
随后装配不再重复完整 `_describe_tracks`。

准备过程仍覆盖完整 state/covariance、metadata、lineage、source support、identity、
`global_track_id` 和双时间戳，不省略成员、弱化摘要或使用 truth。工作量对象显式记录完整描述
轮次、航迹校验数及各类摘要数。接受路径改用递归值语义复制，支持嵌套只读 `Mapping`、
`tuple`、`frozenset`、NumPy 数组和 NumPy 标量；metadata 不丢弃，也不转成字符串。拒绝路径
仍返回原输入序列对象。

完整性复核会遍历全部 metadata，但不重复协方差特征值检查、身份扫描、状态/协方差独立摘要和
发布级排序摘要。正常显式 prepare -> evaluate -> assemble 的工作量为 1 次完整
`_describe_tracks`、2 次完整载荷摘要复核，共 400 条复核航迹摘要。该成本必须由 main 单独
计时，不能隐去。

2026-07-23 聚焦测试为 `21 passed`，D1 全量为 `308 passed in 19.69s`。新增固定测试证明：

- 2/3/5 成员的旧入口、准备对象入口和提交 `de73cb2` 的决策 SHA-256 逐字节一致；
- 200 航迹且每条含嵌套只读 metadata 的接受场景只执行一次完整描述，shadow 可正常装配；
- 接受后 `global_track_id`、速度、分量成员相对位置和 metadata 值语义保持，协方差不收缩；
- 准备对象不可改写；数组和嵌套 metadata 原地变化，以及其余规范表面的修改均被强摘要发现；
  输入失配、OOSM、数量不平衡、重复代和倒退代继续 fail closed。

main 已在提交 `2b976a7` 显式接入准备对象，并对 200v200、seed 1100、2.2 s、
`recon_count=2` 完成 control/shadow 成对开发复跑。9/9 次评估都记录
`explicit_prepared_handle_used=true` 且完整性校验通过；46 条 evidence 全部以
`oosm_scan` 拒绝，0 accepted/46 rejected。过滤 9 条专属审计记录并按既有跨构建规则归一化
不透明计划编号和总线序号后，3294/3294 条业务记录逐条一致，归一化 SHA-256 同为
`bb7eabca...c3855a2`。真值 NPZ、离线真值标签和 proximity 文件也分别一致；D1/D2/D3
终态均为 `202/201/186`，错误、禁止写入、D2/D3 消费和在线 truth 使用均为 0。

control/shadow 墙钟为 `10.712171729/19.376483415 s`，开销 `+80.8829%`，RTF 为
`0.205374/0.113540`。shadow 总阶段 P95 为 `1532.999 ms`；阶段均值中，禁止写入前摘要、
prepare、evaluate、禁止写入后摘要分别为 `224.461/345.095/195.421/207.312 ms`，装配和
日志仅为 `0.00247/0.0973 ms`。最大审计载荷 `11,275,939 bytes`，generation 水位
`8/1024`。安全接口接入成立，但性能门明显失败，且没有 accepted treatment 可评估有效性。
两份 manifest 均记录 `repository_dirty=true`，本批只作开发证据。A2 不准入，A3/A4 与
seeds 1101/1102 继续停止。

### 第十八阶段：A1 publication overlay 纯函数原型

状态：`IMPLEMENTED_UNIT_TESTED_OFFLINE_PROTOTYPE`。提交 `de73cb2` 已实现独立实验模块
`structural_ambiguity_publication_overlay_prototype.py`，输入只读规范 `GlobalTrack` 发布快照
和既有 `StructuralAmbiguityEvidence`，输出 detached accepted/rejected decision、成员
overlay 和新的有界 generation 水位状态。该模块是纯函数原型，没有接入
`FusionAdapter.process()`、`process_scan_batch()` 或默认发布路径，没有修改 `fusion.py`，
没有新增运行开关；其
`d1.experimental-centroid-publication-overlay-decision.v1` 明确是
`experimental_design_prototype_not_online_schema`，不是当前在线 schema。

拒绝决策的 overlays 恒为空，shadow 装配函数直接返回原规范业务 `GlobalTrack` 序列，不做
replay、replace、状态重建或加零物化。接受决策只在脱离滤波器所有权的 DTO 拷贝上增加统一
NED 位置平移和 PSD 位置协方差增量；速度、成员相对位置、`global_track_id`、双时间戳、
lineage/source support、identity、质量及其 metadata 不变。原型按动态分量大小处理平衡、
满基数、无 free row/column 的纯交替环，保持
`cross_covariance_available=false` 和在线 truth 隔离。

所有组件、成员、观测和边先规范排序，再计算摘要和 `decision_id`。重复/倒退 generation、
同代摘要冲突、重叠组件、硬容量、OOSM、stale、非满匹配、非纯交替环、身份字段和非有限输入
均 fail closed；generation 状态采用不可变返回值、固定滞后淘汰和硬容量，不随 episode
无界增长。

2026-07-23 验证口径为：

- 聚焦命令
  `PYTHONPATH=research_modules/d1_sensor_fusion/src pytest -q research_modules/d1_sensor_fusion/tests/test_structural_ambiguity_publication_overlay_prototype.py`
  得到 `7 passed`；
- D1 全量命令
  `PYTHONPATH=research_modules/d1_sensor_fusion/src pytest -q research_modules/d1_sensor_fusion/tests`
  得到 `294 passed`；
- 聚焦场景覆盖同步平衡 2/3/5 成员接受、统一平移/速度与相对位置不变/PSD 增量，OOSM、
  stale、数量或匹配结构非法、身份和非有限输入拒绝，成员/观测/边/组件排列 byte-identical，
  同代幂等、倒退代、摘要冲突、组件冲突、容量拒绝、状态有界、输入数组与 metadata 不变以及
  `global_track_id` 原样保留。

这些结果只证明 A1 纯函数和 DTO 装配合同的模块单元行为。main 已完成默认关闭、审计专用的
A2 shadow 显式准备对象接线；seed 1100 开发复跑证明业务非干预和安全审计成立，但未通过
性能门，且零 accepted treatment，A2 不准入。A3 新匿名冻结扫描 treatment 发现和 A4
预注册多 seed 确认均未开始。当前没有 AirSim、D2/D3 业务消费、系统收益或候选晋级证据。
seeds 1101/1102 继续停止。

### 第十六阶段：身份中性共同质心状态修正候选

D1 已实现默认关闭的
`radar_assignment_ambiguity_neutral_centroid_correction=False`。该开关只有在
`radar_assignment_ambiguity_hold_evidence=True` 时才能启用，与在线 truth hint 模式互斥。
它不是新的身份关联器。候选继续保留结构歧义侧车和 prediction-only 身份语义，只在满足以下
全部条件时修正集合级运动状态：

1. 成员数、观测数和最大匹配基数相等，free row/column 均为 0；
2. 分量只含 `alternating_cycle`，成员数不超过 `K_max`；
3. 同一 radar sensor/scan、双时间戳、NED 和非过期、非 OOSM 合同成立；
4. 没有重复/冲突来源 claim，也没有 truth、actor、target 或 offline identity 字段；
5. 质心马氏距离和去质心二阶矩形状差同时通过门限。

通过后，所有成员只增加同一个有界位置平移
`gain * clip(observed_centroid - predicted_centroid)`。速度逐元素不变，成员相对位置不变，
不选择或发布 observation-to-member 边。hit、观测历史、source support、identity likelihood、
身份 freshness、质量分级、新生/删除和 `global_track_id` 均不改变。

每个成员的位置边缘协方差增加共同质心、形状失配和最小过程不确定度三项。更新前对全部成员
原子检查有限性、对称半正定、协方差上限、非收缩和质量分级不变；任一失败时整个分量继续
prediction-only。成员交叉协方差未建模，侧车和审计继续明确
`cross_covariance_available=false`。

共同质心修正是当前发布状态上的临时候选，不写入观测历史、重放检查点或身份谱系。每个严格
递增的新 generation 都从该帧观测历史精确重放到当前发布时间，随后只施加本帧一次共同平移和
协方差膨胀。旧 generation 的临时修正不会累加。新 generation 校验失败时恢复该帧
prediction-only 基线；同代、倒退代和超出固定滞后窗口的重放直接拒绝，不改变当前发布状态。
`_predict_all_to()` 可在下一帧前传播当前临时修正；正常身份明确量测一旦接受，标准观测历史
重放会替代该临时修正，hit、lineage、source support 和质量只按正常量测更新。

主集成可使用的构造参数包括开关、`neutral_centroid_max_component_size`、增益、最大平移、
质心卡方门限、形状门限、形状膨胀系数、最小位置方差和
`neutral_centroid_generation_registry_max_entries=1024`。generation 水位表每个
`component_id` 只保存最大已见代、最大已应用代和最近量测时刻；只淘汰固定滞后窗口外条目，
硬容量已满且没有可淘汰条目时拒绝新组件。所有参数做严格类型、有限性和范围校验。候选显式
启用时，`association_audit_summary()` 还输出水位表当前/峰值条目、淘汰、容量拒绝、重复代和
倒退代计数；默认关闭时不增加这些字段，保持既有序列化逐字段不变。

专项测试为 `62 passed`，D1 全量为 `282 passed in 17.81s`。覆盖排列不变、共同平移、相对
位置和速度不变、hit/lineage/质量不变、协方差不收缩、free-row/free-column/混合分量拒绝、
过期/OOSM/重复/冲突拒绝、generation 幂等、身份字段拒绝、默认关闭严格等价以及 `K_max`
和线性操作计数。本轮还复现并修复了连续 generation 的临时修正累加，验证 24 代同组件只占
一个水位条目、窗口内容量 fail-closed、窗口外安全淘汰，以及连续 hold 后正常量测通过标准
重放替代临时修正。上述结论属于 D1 模块实现和合同测试，不是系统效果结论。

main 先在未提交工作树完成 seed 1100 dirty 开发诊断，确认 46 个候选均未形成实际状态处理。
随后已在固定提交 `7e15dac9cdaf6743999dfe045a70676fd31a17d6` 上完成 clean 同输入复跑。
两臂均为 `repository_dirty=false`、200v200、`recon_count=2`、2.2 s、seed 1100，
`config_sha256=20ef5248...b840`。控制臂为 source-key 加结构歧义 hold，候选臂只增加身份
中性共同质心。两臂场景文件和离线真值逐字节一致；89 批 `sensor.observations` 的规范化
SHA-256 均为 `bc064834...51518`，D2 在线记录 SHA-256 均为 `da7089fa...f8d2f`。

clean 两臂的 D1/D2/D3 均为 `202/201/186`，strict IDSW 均为 3，track continuity 均为
`0.8266666667`，coverage continuity 均为 `0.8283333333`。可用/不可用/未承诺映射均为
`1491/218/76`，identity commitment coverage 均为 `0.9574706212`；重复分配、在线 truth
使用、未承诺来源绑定违规和未承诺候选绑定违规均为 0。D3 身份承诺门在两臂均拒绝 11 个目标；
main 在一次 hold 事件中累计撤回或清除 13 条运行时绑定。两者统计口径不同，共同关闭了未承诺
目标继续进入下游的违规路径。

候选臂检查 46 个组件，实际施加 0 个，全部拒绝：`oosm_scan=30`、
`unbalanced_component=16`。generation 水位表当前/峰值条目为 `8/8`，淘汰和容量拒绝均为
0；finite 为真。早期 `/tmp/MSM-neutral-centroid-gate-20260723` dirty 运行仍保留为开发诊断，
当前权威复核制品位于
`/tmp/MSM-identity-gate-results-7e15dac/{hold_only,hold_plus_centroid}`。

新的 D3 安全门证明未承诺目标可被下游 fail closed，不证明 D1 共同质心修正有效。候选在
clean 复跑中仍为零 treatment，也没有恢复 hold 的连续性或映射可用性。按停止条件不运行
seeds 1101/1102；候选保持默认关闭，系统效果 P1 继续开放。

main 已完成 seed 1100 的 baseline/source-only/hold 闭环三臂。D1/D2/D3 终态数量分别为
`202/203/200`、`202/201/198`、`202/201/186`；strict IDSW 为 `9/7/3`；
track continuity 为 `.865/.865/.826667`；coverage continuity 为
`.870/.868889/.828333`。hold 端有 D2 prevented hit/miss/birth `69/69/4`、76 条未承诺记录，
D3 拒绝 11 个未承诺目标，未承诺绑定违规为 0。source-only 终态仍映射 200 个真实目标并有
1 条未映射航迹；hold 只映射 191 个真实目标并有 10 条未映射航迹。

该三臂在首个计划后因控制反馈导致传感器流分叉，是系统效果对照，不是完全冻结输入的上游因果
证明。该结果提出的下一步是先在 clean、可复现输入上解释 OOSM 和非平衡分量为何覆盖全部
46 个组件，并证明存在不放宽安全合同的有效施加窗口；D1 随后完成的受控边界诊断见第十七
阶段。真实匿名冻结扫描 A/B 与多 seed 验收仍未恢复。

### 第十七阶段：共同质心冻结扫描边界诊断

D1 已增加可复用的冻结扫描诊断入口
`run_structural_ambiguity_centroid_replay_diagnostic()` 和命令行脚本
`scripts/run_structural_ambiguity_replay_diagnostic.py`。输入先经过既有 governed replay
序列化与回读，再由 `SensorScanFrame`、`ScanInputOrganizer` 和
`FusionAdapter.process_scan_batch()` 处理。控制臂关闭共同质心，候选臂只在诊断实例中开启；
两臂按扫描编号、`measurement_timestamp`、`arrival_timestamp` 和观测数核对为同一冻结序列。
在线默认值、共同质心公式、固定滞后和 fail-closed 门均未修改。

三类确定性输入得到以下结果：

| 场景 | 成员/观测 | free row/column | 施加 | 拒绝原因 | 候选-控制协方差差最小特征值 |
| --- | ---: | ---: | ---: | --- | ---: |
| 同步平衡纯交替环 | 2/2 | 0/0 | 1 | 无 | `0.479767799918` |
| 乱序平衡纯交替环 | 2/2 | 0/0 | 0 | `oosm_scan` | `-0.0071928353214153066` |
| 数量不平衡分量 | 2/1 | 1/0 | 0 | `unbalanced_component` | `-0.004617076466238031` |

同步场景形成约 `[15.000000, 0.000000, 0.003278] m` 的共同平移，模长
`15.000000 m`，低于 `30 m` 上限。速度、成员相对位置、hit、来源谱系、身份状态和
`global_track_id` 保持不变；候选相对控制臂的协方差差最小特征值为
`0.4797678`，没有收缩。乱序目标扫描保留量测时刻 `0.300 s`、到达时刻 `0.650 s` 和
进入融合前时刻 `0.400 s`，扫描组织器记录 1 次重排，现有 OOSM 资格门据此拒绝。数量不平衡
场景记录最大匹配基数 1、free row/column `1/0`。

两个拒绝场景均为 `applied_component_count=0`，共同质心公式没有生成平移或协方差膨胀，
所以共同质心 correction 确实未施加；但候选臂在拒绝后仍各执行一次
publication-base replay + replace，以清除旧临时修正。控制臂的分段预测发布态与候选臂的
单段历史重放发布基准在当前
离散 CV 过程噪声下不满足半群等价，形成上述有限负协方差差值。诊断逐元素确认候选-控制差值
与 replacement 前后差值 bitwise 一致。因此拒绝路径不能描述为“状态和协方差严格无副作用”；
这些差值只作诊断，两项拒绝结果均为 `candidate_not_promoted`。

专项 `5 passed`，D1 全量 `287 passed in 18.03s`。机器可读结果和中文报告位于
`reports/structural_ambiguity_centroid_replay_20260723/`。这组结果证明受控同步输入中存在
不放宽时序、数量和身份门的非零施加窗口，并证明两类边界继续 fail closed。它不是现实匿名
200 对 200 收益证据，不关闭 clean seed 1100 的零 treatment、多 seed、状态一致性、下游
可用性、P95 和长时资源 P1。候选继续默认关闭，不恢复 seeds 1101/1102。

### 第十五阶段：结构歧义证据侧车与 prediction-only 分量候选

D1 已实现第三条默认关闭的实验路径
`prediction_only_maximum_matching_component_evidence_v3`。独立严格布尔开关
`radar_assignment_ambiguity_hold_evidence=False` 与已拒绝的 v1/v2 互斥。开关关闭时，
原 Hungarian 更新、birth、航迹 metadata 和结果序列化保持基线；空 evidence tuple 不写入
`to_dict()`。显式启用时，融合器复用已经通过图论 oracle 的 v2 最大匹配允许边分解，但不再
执行整分量 suppression 计数。

含结构歧义的分量按以下方式处理：

1. 不提交 observation 到单航迹的身份归属，不增加 hit，不执行量测更新；
2. 分量成员按运动模型继续 prediction-only，成员协方差不做虚假的独立量测收缩；
3. 分量 observation 不写入任一成员的 source lineage；
4. 分量内自由列 observation 延迟 birth；已被参考最大匹配占用的 observation 不计为
   deferred birth；
5. 唯一匹配和完全门外的独立 observation 继续走原更新或 birth 路径。

每个分量发布严格可序列化的 `StructuralAmbiguityEvidence`，schema 固定为
`d1.structural-ambiguity-evidence.v1`。侧车保留
`measurement_timestamp`、`arrival_timestamp`、状态有效时刻、发布时间、NED 成员状态及
`6x6` 协方差、观测 NED 位置及 `3x3` 协方差、候选边 NIS/门限、分量结构、匹配基数和
free-row/free-column 数量。固定语义包括
`posterior_update_applied=false`、`update_mode=prediction_only`、
`birth_disposition=deferred_component_birth`、`component_complete=true` 和
`cross_covariance_available=false`。
观测 evidence key 只由 sensor/modality/frame、双时间戳、雷达转换后的 NED 位置/协方差、
径向速度是否真实观测和同内容 occurrence 生成。该路径不复用可能携带离线标签的通用
`source_lineage_key`；改变 observation 名称或 truth/actor/D6 元数据不会改变侧车或参考匹配。

发布者默认值为 `publisher_node_id=D1_FUSION`、
`publisher_epoch=d1-default-epoch-v1`。成员令牌按
`SHA-256([publisher_node_id, publisher_epoch, D1 local track id])` 生成；
`source_track_id=publisher_epoch::opaque_member_track_token`，
`source_key=publisher_node_id::source_track_id`。D1 本地 track id 只作为哈希输入，不在侧车
中公开，也不声明为 D2 规范 `global_track_id`。启用候选时，D1 航迹快照发布同一
`source_node_id/source_track_id/source_key`，使 D2 可将侧车成员与快照一一对应。默认 epoch
是显式稳定配置，不从 truth、actor 或 observation 名称派生；正式 episode 应由 main 显式
注入可审计 epoch。

为分离来源键治理与结构歧义保持的影响，D1 新增严格布尔参数
`publish_opaque_source_key=False`。默认关闭且 hold 关闭时，航迹仍不发布上述五个不透明
来源字段。仅开启该参数时，融合器照常关联、更新、建轨和重放，只在发布快照中增加
`source_node_id/source_track_id/publisher_epoch/opaque_member_track_token/source_key`；
不构造结构歧义侧车，也不触发 prediction-only。hold 开启时，无论新参数是否显式开启，仍按
原规则发布相同五个字段。`association_audit_summary()` 分别记录 requested、effective 和
`disabled/source_only/structural_ambiguity_hold` 模式，供 main 构造三臂对照。

`component_kinds` 描述整个分量包含哪些结构。每条候选边的 `edge_roles` 只描述该边：
参考匹配边为 `maximum_matching_allowed + matched_reference`；替代边按实际情况携带
`alternating_cycle`、`free_row_alternating_path` 或
`free_column_alternating_path`。分量标签不会复制到每条边。逐观测 `birth_deferred` 和
`structural_ambiguity_deferred_birth_count` 只统计参考最大匹配中的自由列；平衡 `2x2` 和
free-row `3x2` 分量均为 0，free-column `2x3` 示例为 1。

该阶段专项为 `25 passed`，当时 D1 全量为 `245 passed in 17.48s`。覆盖平衡/非平衡分量、唯一匹配、
首扫、门外独立 birth、输入排列不变、来源谱系隔离、truth 字段拒绝、未观测径向速度不参与
更新、observation 名称和离线 identity metadata 不变性、默认关闭兼容、source-only
状态/协方差/计数不变、OOSM 重放不变、稳定序列化、严格类型校验、DTO roundtrip 和协方差
shape/半正定校验。该结果证明 D1 合同和模块行为，不单独证明系统身份收益。后续三臂结果见
第十六阶段；其闭环输入分叉限制不能省略。

首次 `9cd2a79` A/B 之后，main 已在固定提交 `ff88131` 完成可评估身份指标的最终干净 A/B。
两组均为 `nominal_200v200`、seed 1100、2.2 s、`recon_count=2`。候选通过
`--d1-d2-structural-ambiguity-hold` 显式启用；默认路径不变。D1 对冻结在线输入的 89 个发布
批次完成逐批重放，observation、accepted、update、birth 和 track count 与候选制品一致。
离线真值只在重放结束后用于因果审计，在线 truth use 保持 0。

| 指标 | baseline | 候选 |
| --- | ---: | ---: |
| D1 航迹数 | 202 | 202 |
| D1 evidence received / consumed | 0 / 0 | 46 / 46 |
| D2 prevented hit / miss / birth | 0 / 0 / 0 | 69 / 69 / 4 |
| D2 航迹数 | 203 | 201 |
| D3 分配数 | 200 | 197 |
| strict ID switch | 9 | 3 |
| track / coverage continuity | 0.865 / 0.870 | 0.826667 / 0.828333 |
| available / partial unavailable mappings | 1,566 / 234 | 1,491 / 296 |
| identity commitment coverage | 1.000000 | 0.957471 |
| 实时倍率 | 0.220352 | 0.207642 |

候选的严格 ID switch 已可评估并从 9 降到 3，但航迹连续性、覆盖连续性、D2 航迹、D3 分配
和映射可用性均下降。D1 离线因果审计定位到 76 次参考更新被阻断，其中 69 次是真值一致更新、
7 次是错误更新；另有一个真实新生延迟 0.2 s。D2 的四次 prevented birth 均指向同一真实目标
的重复 D1 航迹，不是四个目标覆盖损失。13 条可可靠连接真值的既有歧义成员，其平均位置误差
从 25.217 m 增至 34.184 m，位置协方差迹中位数约为基线 2.93 倍。

最可能的 D1 根因是整分量 prediction-only 同时冻结正确边和错误边。候选保持默认关闭。后续
研究方向限定为默认关闭的身份中性、置换不变共同平移修正；该模块候选现已实现，接线和晋级
状态见第十六阶段。它不得增加 hit、lineage 或身份提交，且协方差只能膨胀。完整证据、数学
约束和 A/B 门槛见
`../../subagent_reviews/D1_STRUCTURAL_AMBIGUITY_HOLD_CAUSAL_AUDIT_CN.md`。

### 第十四阶段：最大匹配允许边分量 v2 模块通过与系统候选拒绝

D1 已实现默认关闭的实验策略
`fail_closed_maximum_matching_allowed_edge_component_v2`。新开关
`radar_assignment_ambiguity_governance_v2` 默认为 `False`，与 v1 开关互斥。两者均关闭时，
融合、分配及既有审计字段和值与当前基线一致；本轮只增加策略选择审计字段。显式启用 v2 时，
审计状态为
`experimental_v2_enabled_rejected_candidate`，表示运行时明确启用了一个已被系统门槛拒绝、
默认关闭的研究候选。

审计保留历史字段 `radar_assignment_ambiguity_policy_version` 及其关闭时的 v1 默认值，避免
破坏既有消费者。该字段不能单独解释为“正在运行 v1”。新增
`radar_assignment_ambiguity_selected_policy_version`：两种开关均关闭时为 `None`，显式启用
时为实际版本；`radar_assignment_ambiguity_candidate_policy_versions` 列出可选 v1/v2。
下游应结合 selected、enabled 和 status 判断运行状态。

v2 只读取在线关联已有的门内布尔矩阵、当前最大匹配、量测时刻航迹状态和协方差。对于一般
`m x n` 矩形二部图，匹配边按 observation 到 track 反向，其他门内边按 track 到 observation
正向。可进入某个最大匹配的非当前边分为三类：

1. 位于有向交替环中的边；
2. 从 free track row 可达的交替路径边；
3. 可通向 free observation column 的交替路径边。

实现先保留 Hungarian 的最大匹配；SciPy 不可用且原 greedy 结果基数不足时，以增广路径补成
最大匹配。它不枚举排列，也不使用固定代价 margin。所有允许边形成无向分量；只要分量含一条
可替代的非匹配边，该分量的全部 observation 都跳过 update 和 birth，全部相关 track 同时
coast。这样 free column 对应的 observation 不会在抑制关联后绕行进入新航迹。

模块测试覆盖 `2x2` 交替环、`3x2` free-row、`2x3` free-column、唯一最大匹配、门外独立
birth、首扫无航迹、greedy fallback、OOSM 和 200 航迹稀疏门图。测试同时检查
`measurement_timestamp`、`arrival_timestamp`、`6x6` covariance 和中心拥有的
`global_track_id` 不变。v1/v2 专项共 `29 passed`，D1 全量 `220 passed`。main 另以
2,666 个小型二部图做独立穷举 oracle，最大匹配基数和允许边分量全部通过；scalable 模块
`142 passed`。穷举只用于离线验证，不在在线算法中。这些结果证明图论识别和接口合同，不证明
整分量 suppression 对系统有收益。

候选不解析 observation 名称，不读取 target/actor/truth/D6，也不使用未观测的零径向速度。
main 已在 clean commit `c928727` 完成首个未见 seed A/B。两组均为 200v200、2.2 s、
`recon_count=2`、seed 1100，同一 git commit，`repository_dirty=false`，
`config_sha256=20ef5248...b840`。baseline/v2 runtime profile 分别为
`b508f675...12a8` 与 `9680c45b...f9f4`，差异只来自 v2 treatment。两组均
finite=true、online truth=0，且 online/radar observations、target labels、known false alarms
分别保持 `2035/1954/2352/90`。

| 指标 | baseline | v2 |
| --- | ---: | ---: |
| ambiguous mappings | 0 | 0 |
| D1 tracks | 202 | 202 |
| D2 tracks | 203 | 199 |
| D3 assignments | 200 | 196 |
| ID switch | 9 | 9 |
| track continuity | 0.865 | 0.830 |
| coverage continuity | 0.870 | 0.835 |
| available mappings | 1,566 | 1,503 |
| unavailable mappings | 230 | 266 |

v2 在 9 个 ambiguity scans 中抑制 `77/1954=3.94%` 的雷达观测，相关 track coast 为 91。
ambiguous mapping 和 ID switch 没有改善，D2 航迹、D3 分配、两项连续性和映射可用性均下降。
主要原因是允许边识别虽然正确，但“整个 allowed-edge 分量全部 fail closed”把图论不确定性
直接转换成了过强的信息抑制。

按照预注册门槛，main 已停止 seeds 1101/1102、10 s 和 20-seed，不再扩大被拒绝候选的实验。
v2 不晋级并保持默认关闭；P1 身份连续性继续开放。后续若设计新 intervention，必须保留当前
图论边界，同时减少无身份收益的整分量 suppression，并重新作为独立候选验收。

### 第十三阶段：匿名雷达交替环 v1 clean 阻断与默认回退

D1 在开发冻结输入和零延迟对照中确认 seed 1000/1002 的 radar-only 污染来自扫描间 Hungarian
swap/保持/swap-back，不是 OOSM、重捕获或缺失 identity evidence。20:1 单帧 likelihood
margin 也不能证明身份：一次 coast 改变后验后，后续错误排列会显得代价唯一。

`fail_closed_gate_feasible_alternating_cycle_v1` 只检查全 radar scan 中 Hungarian 已匹配行列
的门内强连通交替环。显式启用时，环内 observation 被 processed 后跳过 update/birth，相关
track 只预测且 covariance 不收缩。早期开发冻结回放和零延迟对照只用于复现根因及验证候选
机制，不能替代同配置 clean A/B 或泛化验收。

main 随后按完全相同配置重跑 baseline `488dc39` 与 v1 candidate `d967c96`：
200v200、2.2 s、`recon_count=2`、seeds 1000/1001/1002。每个 seed 的配置哈希在两端完全
一致，结果为：

| Seed | D2 ambiguous | strict identity | D1 tracks | D2 tracks | D3 assignments | v1 suppression |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| 1000 | `2 -> 0` | unavailable -> available；候选 IDSW `3`、continuity `.8600` | `203 -> 203` | `201 -> 200` | `200 -> 198` | `22/1962 = 1.12%` |
| 1001 | `0 -> 0` | available 保持；IDSW `9 -> 7`、continuity `.869444 -> .814444` | `201 -> 201` | `202 -> 194` | `200 -> 190` | `130/1966 = 6.61%` |
| 1002 | `2 -> 0` | unavailable -> available；候选 IDSW `4`、continuity `.8350` | `201 -> 201` | `200 -> 197` | `200 -> 193` | `78/1958 = 3.98%` |

三组 strict availability 从 `1/3` 提升到 `3/3`，但 D2 航迹和 D3 分配均下降，seed 1001
continuity 下降约 `0.055`，且三组分别抑制 `1.12%/6.61%/3.98%` 的 radar observations。
finite=true、`repository_dirty=false`、online truth=0、missing identity evidence=0，
target/known-false-alarm 离线标签数也保持相同。因此 v1 不晋级，身份连续性 P1 保持开放。

早先 `/tmp/msm-clean-radar-d967c96` 的命令遗漏 `--recon-count 2`，实际是
`recon_count=8`，三 seed 配置哈希为 `cc6/cbb/9f45`；它不能与 recon=2 基线直接比较，只保留为
独立 stress 数学诊断。该 stress 的 seed 1001 残余 `GT3D-000210` 不是 D1 新 birth。它与 D1 既有
`global_track_187` 的终态 state/covariance 完全一致；该航迹由 scan 1 radar 初始化，scan 8
接受另一离线谱系的 radar observation，scan 9 又接受原谱系 observation，随后接入两条 vision，
最终由 D2 重建 canonical track。scan 8 的门内矩阵为 `200x199`，209 条 gate-valid edge、
198 个匹配、2 个 free row 和 1 个 free column。Hungarian 给 `global_track_187` 的边代价为
`0.80058`，同一 observation 对 free row `global_track_186` 也合法，代价 `1.58216`。把该
observation 转给 free row 并释放原 row 可保持匹配基数；v1 只看已匹配行 SCC，无法发现这条
free-row alternating path。该结构性缺口独立于 stress 与 recon=2 之间不可比较的业务指标。

同一 recon=8 stress seed 1001 的 1,966 条 radar 原始量测全部是三维
`[range, azimuth, elevation]` 和 `3x3` covariance。转换后的零 radial velocity 明确标记为
`radial_velocity_observed=False`、`filter_measurement_dimension=3`，只是 placeholder，不能
用于缩小候选图。

生产默认现恢复基线 Hungarian 行为。`FusionAdapter` 和 `Scalable3DFusionAdapter` 的严格布尔
参数 `radar_assignment_ambiguity_governance` 默认为 `False`；只有显式 `True` 才运行 v1。
`association_audit_summary()` 输出 enabled、候选 policy version 及
`disabled/experimental_enabled` 状态。专项 `13 passed`，其中包含默认换绑、显式 v1
suppression 和 gate-valid `3x2` free-row blocker；D1 全量 `204 passed in 16.70s`。

默认关闭提交 `8f17c5d` 已按上述 recon=2 同配置重跑，三 seed 的全部业务指标均恢复
`488dc39` baseline。main 跨构建审计 `3/3 passed=True` 且
`normalized_online_payloads_equal=True`，证据位于
`/tmp/msm-default-off-cross-build-8f17c5d-r2`。这证明默认回退无业务回归，不证明 v1 可晋级。

full alternating-path v2 已覆盖最大基数匹配的交替环、free-row 与 free-column 路径，并通过
模块与穷举验证；但 seed 1100 clean A/B 没有身份收益且降低 continuity、D2/D3 和映射可用性，
系统候选已被拒绝。
10 s 的 7 个 radar+vision ambiguous mappings 不能单独证明 radar-only 根因，但长期 coast 和
跨模态后果属于集成验收范围，不能因其非纯 radar 而排除。

### 第十二阶段：匿名跨模态几何门控

D2 的 nominal 200v200 身份阻断审计表明，seed 1000 中存在视觉观测与另一目标雷达观测写入
同一 D1 航迹谱系的情况。D1 使用 clean `5263e2b` 的 10 s 冻结输入复现该问题，输入为
771 scans/11,889 anonymous observations，SHA-256 为
`5d033a049c2b4e09fb13d7c36e1117055b5b596d9e31f058ad2bf7cbd267ce8f`。

根因是 `SensorScanFrame` 将嵌套相机模型冻结为只读 `Mapping`，旧解析器只接受普通 `dict`。
clean 输入中的相机位置仍由顶层字段保留，但旋转矩阵和内参退回默认值，造成错误像素投影和低
创新匹配。当前解析支持冻结 `Mapping`、`rotation_camera_from_ned` 和嵌套
`camera_intrinsics`，并检查相机几何。显式非法外参、相机后方目标和非有限投影均 fail closed。

在线关联仍只使用双时间戳、NED 航迹状态、像素投影/创新、观测与航迹协方差、传感器类型和已有
航迹状态。truth target、Actor/Object 名称、距离真值和 D6 结果均未进入在线门控，
`online_truth_use_count=0`。D2 离线标签只在回放结束后复核结果。

单 seed A/B 中，D2 列出的 17 条视觉污染观测全部离开原错误航迹，且 17/17 进入离线标签单一
的候选谱系。终态航迹数 `201 -> 202`；候选新增雷达出生
`radar-s000030-d0116 -> global_track_202`，其原因是修正后的视觉后验改变了后续雷达关联集合。
规范状态/协方差/时刻/谱系摘要由 `39d0cdf5...02d7` 变为
`b0d6c4ac...d717`，属于有明确关联因果的业务变化。

`association_audit_summary()` 新增光电投影门通过、拒绝、不可用、一对一冲突和最大门内 NIS
诊断。候选计数分别为 `2255/215/0/3`，最大门内 NIS 为 `39.326205`。字段不含真值，
schema 保持 `d1.association_audit.v1` 的兼容性增量。D1 全量回归为
`191 passed in 16.88s`。专项证据：

- `reports/d1_cross_modal_geometry_governance_20260723.json`
- `reports/D1_CROSS_MODAL_GEOMETRY_GOVERNANCE_20260723_CN.md`

本项关闭已复现的 D1 相机元数据解析缺陷，不关闭 nominal 20-seed 身份审计。main 仍需在 clean
候选提交上重跑 seeds 1000-1019，再由 D2 复核 118 个历史多真值航迹帧。该证据不是 AirSim、
真实相机标定或严格身份指标放行。

### 第十一阶段：扫描 claim JSON 单次物化

本轮使用 clean `5263e2b343dc4b96d239f77ef09437eb132f9efb` 的
`200v200-nominal-v1`、10 s、seed 1000 冻结在线输入，处理 771 个扫描和
11,889 条匿名观测。输入 SHA-256 为
`5d033a049c2b4e09fb13d7c36e1117055b5b596d9e31f058ad2bf7cbd267ce8f`。

`_claim_for_frame()` 原来会为内容摘要和完整帧摘要重复递归转换同一量测、协方差、元数据和
来源谱系。当前路径先生成一次 JSON 安全内容记录，再复用该记录计算原格式 SHA-256。键排序、
`allow_nan=False`、内容排除字段、重复/重放/冲突判定及 fail-closed 异常边界均未改变。

完整旧/新 claim 流水严格等价。claim registry 哈希均为
`sha256:22a713367482532d45e131e2aa9b0e6913d75cc6a7becffa85bf82f0b6eb8fd7`；
逐扫描融合语义、操作快照和累计诊断哈希分别保持
`e5d4ec2e...f4244`、`82728a8e...bfb5bf` 和 `b28df84d...521766`。终态航迹和在线一致性
证据哈希也一致，在线 truth 使用为 0。

771 scans 交错 5 轮计时的 P50/P95 为
`3.618/4.049 s -> 1.905/2.038 s`，P50 加速 `1.899x`；墙钟不参与等价通过判定。
cProfile 中 `_json_safe` 累计由 `5.781 s` 降至 `1.992 s`。D1 全量测试为
`185 passed in 19.69s`。

本项只关闭 scan-input claim 的重复规范化热点。冻结复放的 D1 fusion 仍为
`43.148 s`，主要开放路径为 `global_tracks/_to_global_track`、非雷达扫描关联和 fixed-lag
replay。该证据是单 seed 三维质点冻结 replay，不是 AirSim、正式多 seed、clean 候选全栈或
实时放行。报告仍位于：

- `reports/d1_tail_latency_performance_20260723.json`
- `reports/D1_TAIL_LATENCY_PERFORMANCE_20260723_CN.md`

### 第十阶段：冻结 replay 尾延时归因与完整帧复用

本轮以 clean `4ac3bb2c12cc6af6ebd372107ced00bcdc5adf6a` 的
`200v200-nominal-v1`、10 s、seed 1000 冻结输入复放 771 个扫描和 11,889 条匿名在线观测；
输入 SHA-256 为
`c1dda8523e48c255bbeef48d9516b05863eb1bbb3a3ae2e09733259e6a66f77a`。
clean episode 原始 D1 fusion P50/P95/max 为
`33.252/224.764/592.957 ms`，scan-input 为
`1.747/177.084/361.536 ms`。

profiler 确认 scan-input 重复成本来自已完成深快照和合同校验的 `SensorScanFrame` 被 organizer
再次构造。当前实现对完整帧核对轻量完整性封印后直接复用；对象或标量被替换、数组恢复可写时
回退原完整重建和 fail-closed 校验。完整复放操作数如下：

| Scan-input 操作数 | 旧路径 | 新路径 |
| --- | ---: | ---: |
| organizer 内帧重建 | 771 | 0 |
| organizer 内 observation 再快照 | 11,889 | 0 |
| 已验证完整帧直接复用 | 0 | 771 |

前 256 scans 交错 5 轮总耗时 P50/P95 为
`1.942/1.968 s -> 0.881/0.894 s`，P50 比为 2.204x；墙钟不参与验收。完整旧/新复放的逐输入
结果、close/audit、94 个 release groups、逐 fusion posterior（状态、协方差、时间戳、谱系、
分级）、物化 `GlobalTrack`、终态、一致性证据、逐 fusion 操作数和累计诊断全部严格一致。
逐 fusion 操作快照哈希均为
`sha256:82728a8e0fed0adedd0254368e29a3c117157b066158595d7ca6dac558bfb5bf`。
main 实测当前 D1 全量回归为 `185 passed`，这是本工作区的当前权威测试计数。

fusion 数学路径未修改。cProfile 主要累计路径仍为 `global_tracks 17.559 s`、
`_scan_one_to_one_assignments 17.027 s`、`_to_global_track 16.930 s`、
`_cached_non_radar_scan_cost_matrix 14.971 s` 和 `_replay_record 8.601 s`。本机未剖析复放
P50/P95/max 为 `34.108/178.420/354.413 ms`，只用于和同轮操作数配对，不能与 clean episode
作正式前后比较。当前验证运行在未提交 D1 工作区，是单 seed 三维质点 replay，不是新的 clean
full-stack、AirSim、正式多 seed 或实时放行。证据：

- `reports/d1_tail_latency_performance_20260723.json`
- `reports/D1_TAIL_LATENCY_PERFORMANCE_20260723_CN.md`
- `scripts/run_tail_latency_performance.py`

### 第九阶段：nominal 200v200 clean 单 seed 全栈校准

main 在 detached clean 提交
`4ac3bb2c12cc6af6ebd372107ced00bcdc5adf6a` 上运行
`200v200-nominal-v1`、10 s、seed 1000 的 D1-D7 全栈，并与同 seed、同配置的 clean
`0d2da25c14e50f8f9a10ad47a7bd74e5c5e577fb` 对照。两次运行各处理 771 个 D1 扫描和
11,889 条匿名在线观测；候选世界状态有限，`online_truth_use_count=0`。

| 指标 | clean `0d2da25` | clean `4ac3bb2` | 候选变化 |
| --- | ---: | ---: | ---: |
| 核心 wall（`summary.json.wall_time_s`） | 94.104939744 s | 85.002427712 s | 下降 9.6727%，1.1071x |
| `module.d1_fusion` 累计 | 49.697406826 s | 40.272795088 s | 下降 18.9640%，1.2340x |
| `module.d1_scan_input` 累计 | 12.315225105 s | 12.560936034 s | 增加 1.9952% |

候选核心实时倍率为 `0.1176437`。771 次 `module.d1_fusion` 调用的
P50/P95/max 为 `33.25249/224.76351/592.95713 ms`。跨构建审计确认
`normalized_online_payloads_equal=true`、`truth_state_equal=true`、
`plan_lineage_pattern_equal=true`，参考与候选计划谱系也分别有效。

外部 `/usr/bin/time` 记录的候选总进程 elapsed 为 `1:55.95`，峰值 RSS 为
`2,468,928 KiB`。该 elapsed 包含解释器启动、核心 episode、离线后处理和制品落盘，不能与
85.002427712 s 的核心 wall 混写或用于上述同口径加速比。

本批接受条件仅为同 seed/配置、两端 clean、状态有限、在线 truth 为 0，以及规范在线载荷、
离线 truth state 和计划谱系审计全部通过；这些条件均通过。它仍只是单 seed 描述性 clean
校准，不是 20-seed，不是正式性能矩阵，也未达到实时。D1 融合尾延时和 scan-input 成本继续
保持 P1；本批不新增 AirSim、正式 RMSE/NEES/NIS 或物理拦截效果证据。只读证据位于：

- `/tmp/MSM-scalable3d-candidate-4ac3bb2/research_modules/scalable_3d_simulation/outputs/scalable_3d_timing_v2_clean_4ac3bb2_20260722/10p0s_seed_1000_nominal/`
- `/tmp/MSM-scalable3d-candidate-4ac3bb2/research_modules/scalable_3d_simulation/outputs/scalable_3d_timing_v2_clean_4ac3bb2_20260722/cross_build_seed_1000_nominal/`

### 第八阶段：非雷达创新矩阵栈批处理

未见 seed 1000 的 10 s、200v200 冻结输入含 771 个扫描和 11,889 条匿名观测，终态为
201 条航迹，在线 truth 使用为 0。cProfile 将当前最大融合热点定位到
`_cached_non_radar_scan_cost_matrix()`：旧路径累计 34.307 s，其中 496,625 次
`numpy.linalg.pinv()` 累计 14.837 s。对应扫描内的相机几何和航迹投影可复用，但每个
航迹-观测候选仍通过 Python 单独调用伪逆。

默认路径现按量测几何、量测/协方差形状和角度残差维度分组。每条观测继续保留自己的量测和
协方差，每条航迹继续保留自己的预测状态、投影和雅可比；只把形状一致的创新协方差组成矩阵栈，
一次调用 `numpy.linalg.pinv()`。每个候选的残差包角和马氏二次型仍按旧操作顺序计算。
批处理失败时整组回退逐候选求解。`batched_non_radar_innovation_solve=False` 保留旧路径用于
冻结对照。EKF、门限、Hungarian 分配、双时间戳、NED、协方差、固定滞后、
`global_track_id` 和后验 generation 语义均未改变。

同进程稳定性基准选取该输入的前 256 个已释放扫描和 4,087 条观测。每个变体先预热
128 个扫描一次，再交错运行 7 次。逐候选/批处理 P50 为 `12.242/10.238 s`，P95 为
`13.340/11.248 s`，均值为 `12.506/10.385 s`；P50 加速 `1.196x`。完整 771 扫描单次
交叉验证的无 profiler 纯融合墙钟为 `50.458/39.994 s`，加速 `1.262x`。逐扫描语义摘要、
终态航迹、一致性证据、操作计数和累计诊断全部严格相同。完整输入 cProfile 中非雷达代价矩阵
降至 17.320 s，`pinv` 调用降至 1,018 次。该 2026-07-22 非雷达专项当次历史回归为
`182 passed in 15.92s`，不是当前权威测试计数。

详细证据见 `reports/D1_NON_RADAR_INNOVATION_PERFORMANCE_BENCHMARK_CN.md` 和对应 JSON。
该结果关闭非雷达逐候选伪逆的 D1-owned 热点，不是完整 D1-D7 实时结论。其后完整帧再快照和
claim 重复 JSON 规范化也已关闭；航迹物化、非 claim 的 audit/event 持久化、长期 claim
registry 内存、长于 10 s 的增长率、常驻内存、AirSim 和正式 RMSE/NEES/NIS 仍为 P1。

### 第七阶段：一致性证据计数刷新

在 clean `f80b5bd` 的 10 s、200v200 冻结输入上，函数级剖析显示当前默认路径仍有大量已缓存
证据刷新。固定滞后历史的模型、后验、门控、协方差和来源谱系均未变化时，旧实现仍调用
`dataclasses.replace()`，使不可变记录重新执行完整构造校验。代表 seed 42000 共发生
194,916 次这类刷新；旧路径 `_refresh_cached_consistency_evidence_if_enabled()` 累计
27.122 s，成为固定滞后重放链的主要成本。

`OnlineConsistencyEvidenceRecord.with_replay_counters()` 只接受一个已经通过完整构造校验的冻结
记录，并只校验新的非负 `replay_revision/replay_count`。其余槽位逐项复用；双时间戳、状态、
协方差、可用性、来源谱系和由谱系生成的 `evidence_id` 均不重算。新建证据、真实滤波更新、
重复观测、OOSM 标记和不可用记录仍执行完整校验。融合器保留
`trusted_consistency_counter_refresh=False` 参考开关，便于冻结 A/B。

seeds 42000、42001、42002 的扫描/观测数分别为 `764/12,107`、`844/11,922`、
`782/11,825`。完整重验与受限复制纯融合墙钟均值为 `64.844/52.657 s`，加速 `1.231x`，
3/3 候选更快。每一扫描的状态、协方差、时间戳、来源谱系和航迹分级，以及终态航迹、逐观测
一致性证据、物化计划和全部融合操作计数均严格一致；在线 truth 使用为 0。代表 seed 的
cProfile 中，证据刷新累计 `27.122 -> 1.664 s`，`_replay_record` 累计
`35.348 -> 9.410 s`。D1 全量回归为 `178 passed in 14.80s`。

详细证据见 `reports/D1_CONSISTENCY_COUNTER_REFRESH_PERFORMANCE_BENCHMARK_CN.md`、
`reports/D1_CONSISTENCY_COUNTER_REFRESH_PROFILE_10S_CN.md` 及对应 JSON。本阶段关闭的是已缓存
一致性证据的重复完整校验热点。其后非雷达逐候选伪逆已由第八阶段关闭；航迹物化、scan input、
长于 10 s 的增长率和系统实时倍率仍为 P1。

### 第六阶段：最终跨提交全栈语义审计

main 使用相同的 `200v200-nominal-v1` 配置，在 clean 参考提交 `8f86192` 与 clean 候选提交
`f80b5bd` 上分别运行 10 s seeds 42000、42001、42002。三组运行均保持有限状态和
`online_truth_use_count=0`；候选与参考的 D1 终态航迹数逐 seed 均为 `202/207/203`。

D1 fusion 累计耗时的三 seed 均值为 `92.991088 -> 88.330438 s`，下降约 5.01%。D1 scan
input 同期为 `16.902643 -> 17.524242 s`，增加约 3.68%，因此不能把融合分项改善解释成 D1
全部阶段同比改善。雷达关联的精确创新求解总数由 `7,130,228` 降至 `1,578,677`，下降约
77.86%；该计数只描述执行成本，不是业务输出或精度指标。

main 对两个提交的在线总线执行逐条语义审计。三个 seed 全部通过。审计只把 D3 每次规划生成的
不透明 `plan_id` 按出现次序和版本归一化；归一化前先校验 ACK 原始载荷摘要，且 owner、version、
coalition、`global_track_id`、导引命令等业务字段仍参与比较。D1 fused-track 主题的逐条规范哈希
一致，说明 certified radar pre-gating 没有改变本组业务语义。未通过有限性、严格对称、
Gershgorin 正定下界和 `pinv` cutoff 认证的创新协方差仍完整回退原精确 `np.linalg.pinv` 路径。

证据目录为
`../scalable_3d_simulation/outputs/scalable_3d_long_duration_candidate_20260722_clean_f80b5bd/`。
该结果关闭当前三 seed 的跨提交 D1 业务等价复核，不关闭系统实时预算、长时归一化超线性、
AirSim 或正式 RMSE/NEES/NIS P1。

### 第五阶段：可证明雷达预门控与单次 A95 物化

本阶段继续使用 clean 候选提交 `8f86192` 的冻结在线观测，不重新生成场景，也不读取在线
truth。雷达扫描关联先构造创新协方差 `S`。只有 `S` 有限、逐元素严格对称，且 Gershgorin
最小圆盘下界在数值安全裕量后仍为正并高于 `1e-15 * ||S||_2` 的保守上界时，才认证
`np.linalg.pinv` 不会截断任何奇异方向。对已认证矩阵，使用
`d.T @ pinv(S) @ d >= ||d||^2 / ||S||_inf` 排除必然越过原关联门限的候选。未认证矩阵全部执行
原有精确 `pinv`；关联门限、Hungarian 分配、6 s fixed-lag、观测数和扫描数不变。

两类负例覆盖了该适用边界：带非正定交叉协方差的矩阵，以及存在会被 `pinv` 截断近零特征值的
矩阵。构造差向量使旧 `pinv` 代价仍在门内、朴素 trace 下界却在门外；新 rejection mask 对
两类样本均不预拒绝，扫描级路径也对全部候选执行精确求解并保持终态语义。完整航迹物化同时把
同一协方差的 A95 计算由分级和 metadata 各算一次改为一次计算复用，输出值不变。

10 s seeds 42000、42001、42002 的冻结对照中，旧/新纯融合墙钟均值为
`91.313/88.619 s`，加速 `1.030x`，3/3 candidate 更快。精确创新求解合计由
`7,130,228` 降至 `1,578,677`，下降 77.9%；逐扫描后验、终态航迹和一致性证据哈希逐 seed
完全一致。完整/状态快照仍为 `454/310`、`516/328`、`504/278`。负例专项 `6 passed`，D1
全量 `175 passed in 26.69s`。详细结果见
`reports/D1_COALESCED_RELEASE_PERFORMANCE_BENCHMARK_CN.md` 及对应 JSON。

该结果只证明当前冻结三维质点输入上的语义等价和本机稳定收益。优化后处理 10 s 输入仍平均
耗时 88.619 s，不构成实时闭合、AirSim 或正式融合精度证据。

### Clean 200v200 全栈接线复跑

main 已在 clean 候选提交 `8f86192` 中接入同一运行时刻延迟物化合同，并对 10 s、200v200
三维质点场景运行 seeds 42000、42001、42002。3/3 episode 均为 clean、状态有限、在线 truth
使用 0，D1/D2 溢出和跨模块安全合同均通过。相对旧 clean 提交 `3bac3ff`，D1 fusion 三 seed
均值由 `103.339 s` 降至 `92.991 s`，下降 10.0%。seed 42000 的 2.2 s 全栈墙钟由
`18.611 s` 降至 `18.302 s`。

三个 10 s episode 的 state-only 扫描数分别为 `310/328/278`，完整物化快照数分别为
`454/516/504`；两类记录之和分别为 `764/844/782`，与各 episode 的接收和释放扫描数相同。
每个扫描仍按原顺序执行关联、固定时滞重放、状态更新和发布，只有同一 fusion timestamp 的中间
`GlobalTrack` 快照不再重复构造。事件、扫描输入、共享摘要和世界真值与旧提交 `3bac3ff`
对应 seed 保持一致。

该结果关闭 main-owned 质点全栈的延迟物化接线与 clean 三 seed 语义复跑项，不关闭实时预算。
10 s 仿真中的 D1 fusion 均值仍为 92.991 s，也不构成 AirSim、真实传感器精度、
RMSE/NEES/NIS 或完整拦截效果证据。证据目录为
`../scalable_3d_simulation/outputs/scalable_3d_long_duration_candidate_20260722_clean_8f86192/`。

### 第四阶段：同一运行时刻延迟物化

`process_scan_batch(observations)` 的默认返回、字段和序列化保持不变，仍生成完整
`FusionBatchResult`。当 `ScanInputOrganizer` 在一个 main runtime tick 内释放多个扫描时，调用方
可对每个扫描显式传入 `materialize_tracks=False`。D1 仍逐扫描完成一对一关联、固定时滞重放、
双时间戳审计、协方差限制、传感器健康、一致性证据、来源谱系和累计诊断，只跳过中间
`GlobalTrack` 快照构造。

状态更新返回 `FusionStateUpdateResult`。该结果明确给出 `tracks_materialized=False`、
`current_track_count`、`state_updated_at` 和完整扫描摘要；`tracks` 不是空元组，访问时抛出
`TracksNotMaterializedError`。最后一个扫描处理完后，调用
`materialize_global_tracks()` 得到 `FusionTrackSnapshot`。快照包含完整航迹、协方差、生命周期、
元数据和发布审计，并把实际物化数计入 `fusion_performance_diagnostics()`。

构造回归使用 4 个扫描、3 个目标和默认 6 s fixed-lag，其中最后一帧是检查点前 OOSM。逐扫描均
物化与中间 state-only、末尾一次物化的终态航迹、传感器健康、时延审计和一致性证据完全相同；
物化数由 12 降为 3。新旧接口及混合发布审计定向测试 `30 passed`，D1 全量
`168 passed in 29.43s`。这是确定性合同测试，不是完整 200v200 墙钟或 AirSim 结果。

`audit_fused_track_publications()` 输出 schema 已升级为
`d1.fused_track_publication_audit.v2`，分别统计 `publication_count`、
`materialized_snapshot_count`、`state_only_count` 和 `track_record_count`。无
`tracks_materialized` 字段的 v1 日志继续按完整快照读取。新 state-only writer 使用
`tracks=[]`、`track_count=0` 和准确的 `current_track_count`；audit 也兼容过渡期的
`tracks=None`。main-owned scalable 三维质点 runtime 已按该接口接线并完成上述 clean 三 seed
复跑；系统实时预算、AirSim 接线和正式精度仍是开放 P1。

### 第三阶段：长时固定滞后检查点复用

本阶段直接回放 clean 长时对照的冻结 `sensor.observations`，不重新生成场景，也不读取在线
truth。输入 SHA-256 为
`3efa561a07bf0cdcd74d23570ee23ca173f56ddaf632c89258d02c20c299a51a`，包含 764 个扫描、
12,107 条匿名观测和 202 条终态航迹；扫描重排 49 次，峰值缓冲 64 个扫描/825 条观测，拒绝、
过旧和溢出均为 0，在线 truth 使用为 0。

长时增长来自完整缓存历史仍被逐项查询、固定滞后重基后丢失可复用后缀，以及一致性证据对未变化
前缀重复执行滤波。默认路径现采用完整检查点二分状态查询、固定滞后检查点后缀复用、受失效逻辑
维护的合法前缀快路径和缓存一致性证据标量刷新。6 s 固定滞后窗、观测数量和顺序、双时间戳、
covariance、关联/创新门限、`GlobalTrack` 字段和在线真值隔离均未改变。

相同输入的旧路径与优化路径逐扫描、终态航迹和一致性证据哈希完全一致。纯融合墙钟为
`157.237 s -> 107.449 s`，加速 1.463 倍；history replay 为 `170,106 -> 13,397`，replay
filter update 为 `120,440 -> 9,549`。候选对和创新求解均保持 2,393,969 次。D1 同时提供固定
大小的 `FusionAdapter.fusion_performance_diagnostics()` 累计诊断快照，其中包含
`replay_filter_update_count`、`replay_checkpoint_reuse_count` 和检查点快路径计数。优化路径实际
执行检查点状态查询 152,861 次、固定滞后后缀复用 110,891 次、合法前缀快路径 300,024 次和
缓存一致性刷新 194,916 次；调用方可按 episode 采样，不需要保存逐扫描历史。

发布审计记录 764 条 `modules.d1.fused_tracks`，共 186.2 MiB；其中只有 407 个唯一融合时刻，
357 条可在同一融合时刻保留最后后验，另有 294 条连续未变化快照。这是延迟物化接口引入前的
历史基线；D1 后续已提供同一 fusion timestamp 内的显式 state-only 接口，main 已按该接口完成
clean 三 seed 质点全栈接线复跑，但仍未实现跨 tick 发布节流或 heartbeat/lineage sidecar。详细证据见
`reports/D1_LONG_DURATION_PERFORMANCE_BENCHMARK_CN.md` 和对应 JSON。

### 第二阶段：扫描关联工作区

第一阶段增量后验成为默认路径后，clean 提交 `492979e` 的 200 规模五个 seed 中，D1 fusion
分别为 10.096、13.693、12.895、11.973 和 11.856 s，均值 12.103 s。第二阶段使用其中
seed 42000 的冻结输入继续剖析。文件 SHA-256 为
`bc539686b130d96c63b76b9161fadbae2dba59de44cb61ac80d92f2ea1018406`，包含 86 个扫描和
2,051 条匿名观测；10 个扫描发生重排，峰值缓冲为 33 个扫描/623 条观测，在线 truth 使用为 0。

当前默认路径新增扫描内关联工作区。非雷达观测的量测模型按观测构造一次；同一量测时刻的航迹
状态按航迹取得一次；只有实际传感器位置、相机位置、旋转和内参完全一致时，才复用预测量测与
数值雅可比。每个候选航迹-观测对仍独立计算残差、创新协方差、伪逆和门控，Hungarian 一对一
分配、扫描原子性、OOSM、fixed-lag 和 `GlobalTrack` 发布数量均未改变。

冻结输入的 current-default 与新默认路径逐扫描语义哈希、最终 201 条航迹哈希和 consistency
evidence 哈希一致。候选对和创新求解均保持 371,054 次；量测模型构造由 16,457 次降至 82 次，
投影构造由 16,457 次降至 14,648 次；`GlobalTrack` 物化仍为 16,653 次。纯融合墙钟由
10.792 s 降至 8.635 s，本机单次加速 1.25 倍。专项测试 `10 passed in 10.33s`，D1 全量
`161 passed in 38.02s`。操作计数和语义哈希是验收依据，墙钟只作复核。

详细结果见 `reports/D1_SCAN_ASSOCIATION_PERFORMANCE_BENCHMARK_CN.md` 和
`reports/d1_scan_association_performance_benchmark_20260722.json`。后续 clean 提交
`8f86192` 已完成 200v200 三 seed 全栈复跑，结果见本节首段；1.25 倍模块对照和 10.0% 全栈 D1
分项改善都不能解释为 AirSim 或 200v200 完整系统已经实时。

### 第一阶段：增量后验与发布快照

D1 已用 seed 42000 的冻结 200v200 在线观测完成逐扫描融合热点治理。输入 SHA-256 为
`38d24429711b67d612f2f398478386ebf0df690fae55cd9dcc36434aac4fb078`，包含 86 个扫描和
2,051 条匿名观测，重排 10 次，峰值缓冲 33 个扫描/623 条观测，在线 truth 使用为 0。
函数剖析确认主要重复工作来自 `_state_at()` 和 `_replay_record()` 对不变历史反复执行滤波，
以及每条发布航迹重复构造传感器健康快照。

当前默认路径为每航迹维护增量后验检查点。顺序输入复用已完成后验；窗口内乱序只删除插入点
及其后的检查点；固定滞后重基、起始观测变化和检查点前 OOSM 会完整失效相关缓存。每个扫描
仍执行原有一对一关联，并重建一致性证据 revision。发布阶段每扫描只构造一次关联、时延和
传感器健康公共快照；所有 `GlobalTrack` 仍完整携带审计字段，发布数组与内部缓存不共享内存。

同一冻结输入的未缓存参考与优化路径逐扫描语义哈希、最终航迹哈希和一致性证据哈希完全一致。
replay 滤波更新由 93,234 次降至 1,797 次，传感器健康快照由 16,653 次降至 86 次；未缓存参考
墙钟为 34.701 s，优化路径为 9.073 s，本机单次加速 3.82 倍。操作计数和语义哈希是验收依据，
墙钟只作复核。报告见 `reports/D1_SCAN_FUSION_PERFORMANCE_BENCHMARK_CN.md` 和
`reports/d1_scan_fusion_performance_benchmark_20260722.json`。

性能专项 `6 passed`；main 复跑 D1 全量 `157 passed in 28.77s`。

main 已从 clean 提交 `e4d66db02a0b8f1b867a0e81b4a73de84588426b` 完成版本化扫描输入
治理的正式复跑。20/50/100/200 四档各 5 个互异 seed，共 20 个 episode；每例 136 帧、
33.75 s。20/20 manifest 均为 `repository_dirty=false`、`evidence_tier=formal`。D1 每例重排
12 帧，拒绝、过旧和溢出均为 0，峰值缓冲 3 帧，结束缓冲 0 帧，在线 truth 使用为 0。

200 规模的 D1 `estimated_peak_memory_bytes` 五例均值为 40,914,828.4 B，约 40.91 MB；最大值
为 40,926,870 B。聚合报告绑定的输入 SHA-256 为
`dd62ae9b6efd86d9669b42ccc0630127bc504a18f37c84be5b3ac8b519a42655`；输入清单引用的 20 份
manifest、20 份在线审计和 20 份评估侧车共 60 个文件均通过独立 SHA-256 复核。

该批仍标记 `full_system_evidence=false`，完整运行时模块未导入。它关闭的是“从 clean commit
正式复跑观测治理并验证哈希、容量和 truth 隔离”的缺口，不运行完整 D1 EKF 融合，也不验证
定位精度、AirSim 或完整拦截效果。

第二组是 seed 42000 的 200v200 单次三维质点全栈 development smoke。2.2 s 仿真接收并释放
86 个扫描、2,051 条匿名观测；重排 10 帧、拒绝 0 帧，峰值缓冲为 33 帧/623 条观测，episode
结束后为 0。`module.d1_fusion` 的 86 次调用累计 35.115 s，平均 408.313 ms；D1 扫描输入整理
累计 2.682 s，平均 31.186 ms。全栈墙钟时间为 60.210 s，实时倍率仅 0.037。在线 truth 使用
仍为 0，但该批只有一个 seed、工作区非 clean、没有可用的融合精度或一致性验收指标。它保留为
development 全栈性能证据，不因上述正式治理复跑而升级。

D1-owned 的冻结输入逐扫描热点已关闭。优化没有合并扫描、丢弃观测、缩短固定滞后窗、改变
双时间戳、压低 covariance 或放宽门控。clean 三 seed 全栈与同一运行时刻延迟物化已经复跑；
剩余系统 P1 是扩大未见 seed 和时长，冻结硬件、发布频率和周期预算，并分别验收长历史内存、
正式融合精度和端到端实时倍率。

证据入口：

- `../scalable_3d_simulation/outputs/observation_governance_calibration_20260722_formal_e4d66db/`；
- `../scalable_3d_simulation/outputs/point_mass_integrated_observation_smoke_20260722_development_coalesced/`；
- `../scalable_3d_simulation/outputs/scalable_3d_long_duration_candidate_20260722_clean_8f86192/`；
- `reports/D1_SCAN_FUSION_PERFORMANCE_BENCHMARK_CN.md`。

正式治理、D1-only 性能和 clean 三 seed 质点全栈结果都不是 AirSim、传感器精度或 200v200
实时系统验收。全栈仍需更长时、多 seed、冻结硬件/配置和逐阶段 P50/P95/max；融合效果仍需
RMSE/NIS/NEES availability 与正确 D2 canonical mapping。

## 历史 D1-owned 增量（2026-07-16）

- 顶层 API 新增 `sensor_observation_from_local_image_track()`，把 main-owned
  `LocalImageTrackObservation` 保守适配为 D1 `SensorObservation | None`。只有 `measured`
  输出 `modality="eo"`、`frame_id="pixel"`；`lost` 始终返回 `None`，不会把旧像素再次送入融合。
- 适配器逐字段复制 measurement/arrival 双时间戳、2×2 pixel covariance、confidence 和
  quality flags；可见光/红外统一进入 EO 模态，同时以 `metadata.spectral_band` 保留波段。
  缺失、非有限、非对称、错误形状或非半正定 covariance 在 D1 边界 fail closed。
- metadata 保留 namespaced sensor/stream/epoch/local track、bbox/center 和 backend/batch 等
  在线审计字段；global/truth identity（含嵌套键）被拒绝。未显式传入 observation ID 时，ID
  由 sensor/stream/epoch/local track/measurement time 确定性生成；显式 source lineage 可对
  重复投递去重。
- 被接受的视觉观测把 `source_track_key` 去重累积到
  `GlobalTrack.metadata.source_track_ids`，但不会把本地来源键写成或重绑定
  `global_track_id`。
- 2026-07-16 无随机 seed 的构造合同回归为专项 `13 passed`、D1 全量 `111 passed`。本轮未
  启动 AirSim，未改变默认检测源、launch/reset/episode 顺序，也未生成新的 RMSE/NIS/NEES。

## 历史系统增量（2026-07-15）

- main 已完成真实 AirSim M5N2 baseline 10 case 与 candidate 10 case，共 20 case；本轮
  在线 `truth_identity` 与 `truth_state` 使用计数均为 0。
- 20 case 共记录 3,805 个 main-bus tick。D1 fusion 阶段 mean/P95/max 为
  `320.00/451.46/1234.88 ms`，是 main-bus 内层主导阶段；main-bus 整体为
  `349.34/487.40/1305.99 ms`。因此 100 ms 系统预算仍是开放 P1，不能把此前 D1-only
  batch replay 加速写成真实运行时已经达标。
- `measurement_timestamp`、`arrival_timestamp`、观测/航迹 covariance 和 NED 工作空间合同
  继续作为强制基线保持。本批是终端闭环与时序实验，未提供可用的 NIS、NEES 或 RMSE 标定
  结果，不能据此声称传感器噪声模型或估计一致性已经闭合。
- M5N2 达到 20/20 后批次终止；TERM 生效前额外完成的 1 个 `png_ttc_2v2_seed001` 被明确
  排除，dropout 完成数为 0。

权威证据为 `subagent_reviews/MAIN_M5N2_TIMING_AND_SECOND_PRIMARY_REPORT_20260715.md` 和
`research_modules/airsim_runtime/outputs/p1_terminal_timing_funnel_10seed_20260715_m5n2/`
下的两个汇总 JSON。后文保留历史实现与验证记录。

## Scope

This directory is limited to simulation and offline evaluation. It does not include real fire-control parameters, damage logic, hardware drivers, real vehicle control, automatic action, or bypass of human authorization.

## Runtime

The implementation uses NumPy/SciPy-compatible fallback code and does not require FilterPy or Stone Soup. Optional placeholders are available in `d1_sensor_fusion.compat`.

## Ownership

D1 owns this module and `subagent_reviews/D1_*`. Under the strict project workflow, main dispatches D1 tasks, D1 edits and tests only its owned paths, and main performs integration summary. D1 module changes must check whether README, PLAN, GAP, and review files need matching updates.

As of the 2026-07-09 P0-A hardening pass, D1 has closed the engineering P0-A items for FDIR-light, covariance floor/ceiling limits, and timestamp uncertainty metadata while preserving the existing `measurement_timestamp`, `arrival_timestamp`, covariance, and NED `GlobalTrack` contracts. D1 continues to provide `GlobalTrack[]`, `TrackUncertaintySummary[]`, latency/quality summaries, and sensor-health evidence only; it does not generate `AssignmentPlan` versions, decide active degradation, rewrite `global_track_id`, or modify D7 PN/PNG control behavior.

## Run Tests

From repository root:

```bash
PYTHONPATH=research_modules/d1_sensor_fusion/src pytest -q research_modules/d1_sensor_fusion/tests
```

## Run Full Simulation

```bash
PYTHONPATH=research_modules/d1_sensor_fusion/src \
python3 research_modules/d1_sensor_fusion/scripts/run_simulation.py \
  --drone-count 3 \
  --duration 60 \
  --dt 0.1 \
  --seed 7 \
  --output research_modules/d1_sensor_fusion/reports
```

The command above is the historical 3-target baseline. In integrated runs, main owns the scenario size and passes N via `--drone-count`; D1 consumes the resulting N target truth/observation sources without a 2v2 or 5v5 cap.

The script writes:

- `reports/EXPERIMENT_REPORT.md`
- `reports/tracks_xy.png`
- `reports/rmse_latency_ablation.png`

## AirSim Dry-Run Fixture

The module includes a no-AirSim dependency dry-run adapter for integration tests:

```python
from d1_sensor_fusion import (
    make_minimal_airsim_dry_run_fixture,
    observations_from_airsim_dry_run_fixture,
)

fixture = make_minimal_airsim_dry_run_fixture(include_lidar=True)
observations = observations_from_airsim_dry_run_fixture(fixture)
```

The adapter emits `SensorObservation[]` with `measurement_timestamp`, `arrival_timestamp`, `frame_id`, and `covariance` filled for synthetic radar, acoustic, EO, and optional lidar observations.

## Blocks JSONL Replay

Main/AirSim runtime `blocks_sensor_observations.jsonl` files can be read back and replayed without importing AirSim:

```python
from d1_sensor_fusion import FusionAdapter, read_blocks_sensor_observations_jsonl

observations = read_blocks_sensor_observations_jsonl("blocks_sensor_observations.jsonl")
adapter = FusionAdapter()
tracks = adapter.ingest_many(observations)
summaries = adapter.track_uncertainty_summaries()
```

For the current Blocks N-actor integration, D1 expects upstream runtime logs to provide
simulation-derived observations from AirSim truth and `simGetDetections`/detector boxes. D1
receives the N target truth/observation sources provided by main and sizes `SensorObservation[]`
ingest and `GlobalTrack` output from those input arrays. Historical 2v2 and 5v5 logs are baselines,
not algorithm limits. These records must include `measurement_timestamp`, `arrival_timestamp`,
`measurement`, and `covariance`. D1 then publishes `GlobalTrack` objects with `position`,
`velocity`, and 6x6 `covariance`. This is a simulation contract only; it does not claim real radar,
acoustic, or lidar hardware is connected.

As of the 2026-07-08 P1 AirSim multi-seed calibration prep, D1 has regression coverage for
Blocks-style CSV replay preserving measurement/arrival timestamps, covariance, NED `GlobalTrack`
state, source support, coverage cell, latency/OOSM audit, and region quality summaries. JSONL replay
also preserves nested EO `camera_model` metadata for the projection model.

Main runtime now owns the P1 D4/D5 calibration sweep and automatically invokes the D6 standard
report bundle after the sweep. D1 does not launch that sweep or write AirSim runtime reports; it
keeps the replay/schema/latency/OOSM/region-quality fields stable so the main/D6 calibration reports
can consume them.
For that bundle, D1-owned evidence is limited to observation delay/quality fields such as raw and
post-fusion `LatencyAuditSummary`, `TrackUncertaintySummary`, `FusionQualityRegionSummary[]`,
`FusionQualityRegionWindowSummary[]`, `SensorHealthSummary[]`, covariance-limit reasons,
`covariance_scale_reason`, and `timestamp_uncertainty_s`. Main/D6 may report or aggregate these
fields; D1 does not turn them into active degradation actions.

As of the 2026-07-09 P1 input-support pass, the dry-run fixture includes
`schema_version="d1.airsim_dry_run_fixture.v1"` and rejects unsupported fixture schema versions.
Generated dry-run observations annotate `d1_fixture_schema_version`, and replay records annotate
`d1_replay_schema_version` so downstream audits can distinguish fixture/replay provenance.
The current P1 fixture path also accepts real Blocks/CV-style JSONL/CSV fields such as top-level
`bbox_xyxy`, `center_px`, `camera_metadata`, `detection_metadata`, `source_support`,
`coverage_cell`, `covariance_scale_reason`, and secondary/mobile recon cue metadata. These are
normalized into `SensorObservation.metadata` and carried into the latest `GlobalTrack.metadata`
lineage without requiring PNG frames or an AirSim Python dependency.

## Historical Baseline: 2026-07-10 AirSim 2v2 Contract Audit

The reset-separated 2v2 smoke output under
`research_modules/airsim_runtime/outputs/p1_gap_closure_2v2_smoke_20260710/` was replayed through
the D1 reader without changing main/runtime. Across six episodes, all 1,528 radar, acoustic, EO,
and synthetic-lidar records retained measurement/arrival timestamps and finite symmetric positive
semidefinite covariance; no record had `arrival_timestamp < measurement_timestamp`. The full-flow
main episode bus also retained both timestamps and covariance trace in every D1 observation summary
and retained timing/covariance fields in `TrackUncertaintySummary`. No D1 timestamp or covariance
contract regression was found.

The smoke also makes the remaining P1 boundary explicit. The current main Blocks writer omits
`schema_version`, so new output is accepted through `legacy.blocks_sensor_observations` rather than
the versioned v1 path. It also omits `coverage_cell`, so D1 can only emit the fallback `unassigned`
region, and the main tick currently serializes per-track uncertainty summaries but not region/window,
latency-audit, or sensor-health summaries. Finally, the fixed 0.2 s delayed multi-sensor stream makes
raw OOSM counts high; advisory sensor-health isolation thresholds require expected-latency calibration
before D4/D6 may consume them as fault evidence. The main bus also enables simulation-only truth-hint
association and retains two tracks, while default truth-free replay of the same file can create a
duplicate third track; replay configuration provenance and truth-free association parity therefore
remain P1. These are writer/schema/calibration items, not a reason to weaken the D1 dual-timestamp or
covariance contract or to treat truth labels as online identity evidence.

The subsequent 10-seed 2v2 run under
`research_modules/airsim_runtime/outputs/p1_gap_closure_2v2_multiseed_20260710/` confirms that the
D1 contract can be consumed repeatedly by reset-separated system episodes. The separate
`p0_truth_isolation_smoke_20260710` run confirms that online D5 local detection/MOT identifiers no
longer depend on AirSim actor/object names. This does not close D1 truth-free replay parity: synthetic
D1 observations may still carry `truth_id` as an offline label, and the main fusion configuration may
still enable simulation-only truth hints. The next D1 integration pass therefore keeps configuration
provenance, truth-free multi-seed replay, explicit writer schema/coverage fields, expected-latency
health calibration, and durable Blocks/CV fixtures open as P1.

## Historical Baseline: 2026-07-11 Truth-Isolated 5v5 Runtime Evidence

The three reset-separated 5v5 episodes under
`research_modules/airsim_runtime/outputs/p1_runtime_truth_isolated_d4d5_smoke_20260711/`
provide the first main-bus evidence after online truth-hint isolation. The no-degradation,
secondary-degradation, and distributed-degradation cases each completed five frames with D1, D2,
and D3 health reported as `ok`; D1 published 15 module records per episode and D3 retained full
assignment coverage. This demonstrates that the online D1 -> D2 -> D3 path remains connected when
truth labels are unavailable to association.

D1 governance is now represented in `main_episode_bus_metrics.json`: all three episodes report
latency audit and region-quality metrics, including `d1_max_delay_s` about 0.2 s,
`d1_region_quality_coverage_rate=1.0`, and one `d1_latency_audit` plus one
`d1_region_quality_window` event per episode. The observed
`d1_oosm_observation_rate=0.9866666667` is the current asynchronous replay accounting result for
fixed-delay, sequentially ingested sensor batches. It is not evidence of a sensor fault and must not
directly trigger D4 degradation. The scan-level watermark API is now explicit and tested, while
sensor-specific lateness budgets, runtime adoption, and fault-injection thresholds still require
calibration.

This is a seed-7, five-frame, 0.4 s smoke run. It closes neither the multi-seed P1 calibration item nor
long-duration latency/region threshold governance. Truth-isolated multi-seed replay, longer windows,
sensor-specific delay distributions, and negative fault cases remain required before D1 runtime
thresholds can be considered calibrated.

## Main Interfaces

- `SensorObservation`: canonical sensor input with `measurement_timestamp`, `arrival_timestamp`, optional cross-node communication metadata, covariance, and normalized `timestamp_uncertainty_s` / `timing_uncertainty_s` metadata.
- `FusionAdapter`: EKF fusion, fixed-lag replay, covariance limiting, and FDIR-light sensor-health accounting. Required methods are `predict_track()`, `update_at_measurement_time()`, `compensate_latency()`, `_bucket()`, `track_uncertainty_summaries()`, and `sensor_health_summaries()`.
- `GlobalTrack`: output state `[px, py, pz, vx, vy, vz]`, covariance, timestamp, source support, identity likelihood, quality level, covariance-limit reasons, latest timestamp uncertainty, latency audit, and sensor-health metadata.
- `TrackUncertaintySummary`: compact quality export with track IDs, covariance trace/a95, level, measurement age, source support, coverage cell, timing fields, timestamp uncertainty, and covariance-limit reasons.
- `SensorHealthSummary`: per-sensor FDIR-light export with `sensor_id`, `status`, `fault_reason`, `reject_count`, `isolation_hint`, `recovery_state`, and counters for duplicate, OOSM/stale, low-quality, anomalous covariance, and timestamp-uncertainty evidence.
- `FusionQualityRegionWindowSummary`: windowed coverage-cell trend export for covariance growth, freshness, source gaps, and latency/OOSM audit flags.
- `ReconCueSummary`: compact radar/GlobalTrack cue for second-stage recon camera pointing, generated by `summarize_recon_cue_from_tracks()`.
- `RadarCovarianceConfig`: optional distance-dependent radar covariance parameters. Defaults preserve the original noise model.
- `CooperativeBearingObservation` / `CooperativeObservationGroup`: D2-confirmed, same-canonical-ID bearing rays with observer lineage, platform pose/extrinsics covariance, dual timestamps, and a common estimate time.
- `localize_bearing_observation_group()`: NumPy-only weighted bearing-ray localization for 2..N observers with baseline, LOS angle, time-skew, information rank/condition, residual, and covariance-completeness gates.
- `CooperativeTrackEstimate` / `covariance_intersection()`: conservative same-ID state fusion with CV propagation, process/timing covariance growth, and message UUID/source-lineage deduplication.

## Cross-Node Metadata

`SensorObservation` accepts optional communication fields directly or through `metadata`: `source_node_id`, `target_node_id`, `relay_node_id`, `link_type`, `sent_timestamp`, `received_timestamp`, `payload_kind`, `stale_after_s`, and `source_support`. `FusionAdapter` preserves the latest observation communication metadata in `GlobalTrack.metadata` and publishes modality counts in `GlobalTrack.source_support`. It also suppresses repeated updates from the same source/sequence/payload lineage, including relay duplicates.

## Replay Schema And CSV

D1 replay schema v1 is `d1.sensor_observation.v1`. New `sensor_observations.jsonl` and Blocks replay records should include `schema_version` plus `observation_id`, `sensor_id`, `modality`, `measurement_timestamp`, `arrival_timestamp`, `frame_id`, `measurement`, and `covariance`. Existing `blocks_sensor_observations.jsonl` files without an explicit version are still accepted as legacy records when the required observation fields are present; the parser annotates them as `legacy.blocks_sensor_observations` in metadata.

Minimal CSV replay is available through `read_sensor_observations_csv()` and `replay_sensor_observations_csv()`. CSV cells for `measurement` and `covariance` should contain JSON arrays; `metadata`, `communication`, and `source_support` should contain JSON objects. CSV support is for replay/audit convenience and does not replace JSONL as the primary runtime log format.
CSV rows without an explicit `schema_version` are treated as `d1.sensor_observation.v1`, so
`covariance` is required for calibration replay instead of being silently accepted as a legacy
record.

New governed writers are available through `write_sensor_observations_jsonl()` and
`write_sensor_observations_csv()`. They always emit `schema_version="d1.sensor_observation.v1"`
and require `ReplayProvenance` with `scenario_id`, `scenario_version`, `config_id`, and
`config_digest`. The writer removes `truth_id`, actor name, and equivalent truth keys from online
metadata by default. An explicit `include_offline_truth=True` places those labels only under
`offline_truth`; they are never used by `FusionAdapter` association in the governed replay tests.

`summarize_sensor_observation_latency_audit()` can compute raw replay observation latency, OOSM,
stale, and duplicate-lineage counters from `SensorObservation[]` before a full `FusionAdapter`
run. The fusion-side `FusionAdapter.latency_audit_summary()` remains the authoritative post-fusion
audit when replay compensation is executed.

## Quality And Latency Audit Exports

`FusionAdapter.latency_audit_summary()` exports `observation_count`, `max_delay_s`, `mean_delay_s`, `replay_count`, `oosm_observation_count`, `stale_observation_count`, `stale_or_oosm_observation_count`, duplicate count, and maximum replay history size. OOSM means an arriving observation's `measurement_timestamp` is older than the fusion time already processed; stale means it is stale at processing time or its arrival delay exceeds `stale_after_s` when that budget is supplied.

`FusionAdapter.sensor_health_summaries()` exports per-sensor FDIR-light status derived from duplicate payload suppression, OOSM/stale latency evidence, low-confidence or occluded observations, anomalous covariance, and timestamp uncertainty. `SensorTimingExpectation` can configure an expected latency, tolerance, and whether fixed-delay OOSM is normal for a sensor. The health export then separates total OOSM from unexpected OOSM and reports mean/max latency plus budget exceedance count/rate. The summary is intentionally advisory: it gives D4/D6 explainable health evidence and isolation hints, but it does not isolate sensors outside D1 or issue control decisions.

Observation covariance is bounded before EKF use, and 6x6 track covariance is bounded after prediction/replay/update. Floor/ceiling reasons such as `observation_covariance_floor`, `track_covariance_floor`, `track_covariance_ceiling`, `long_extrapolation`, `low_quality_observation`, and `occluded_observation` are preserved in `GlobalTrack.metadata` and `TrackUncertaintySummary.to_dict()` without removing the covariance matrices themselves.

`FusionAdapter.region_quality_summaries()` derives lightweight `FusionQualityRegionSummary[]` records from `TrackUncertaintySummary[]`, grouped by `coverage_cell`. The region summary aggregates track count, a95, measurement age, handover readiness, source support, source gaps, and stale-track count for D4/D6 quality consumption while preserving the existing per-track `TrackUncertaintySummary` contract.

`annotate_covariance_growth_rates()` fills `TrackUncertaintySummary.covariance_growth_rate` from adjacent summary snapshots, and `summarize_region_quality_windows()` emits `FusionQualityRegionWindowSummary[]` over region snapshots plus optional `LatencyAuditSummary` snapshots. Supplying `window_size_s` creates deterministic `coverage_cell` time buckets and aligns timestamped latency audits to each bucket. This gives D4/D6 separate fields/flags for regional covariance growth, freshness degradation, source gaps, and latency/OOSM instead of forcing those causes into one quality number.

`summarize_recon_cue_from_tracks()` derives a lightweight `ReconCueSummary` from `GlobalTrack[]` or track-like dicts. It can summarize all tracks or a single `coverage_cell`, computes `cue_position_ned` as an inverse-covariance-trace weighted centroid, emits `cue_covariance`/`covariance_trace`, `active_target_ids`, timing fields, and diagnostics including `track_count`, `stale_count`, and `default_covariance_count`. Missing covariance uses a conservative default and is reported instead of changing the `GlobalTrack` contract.
Optional cue metadata can carry the secondary/mobile recon node, cue source, or mode through `ReconCueSummary.metadata`.

Video/image streams are represented only by derived observations such as bounding boxes, camera metadata, timestamps, and covariance. D1 does not require or store PNG frames.

As of the final 2026-07-11 validation, the D1 governed writer/provenance contract is adopted by the
main episode bus, online records strip truth/actor/object identity, and offline truth labels are written
separately for evaluation. This closes the D1 contribution to the P1 contract layer. Remaining D1 work
is validation and algorithm enhancement: longer real multi-seed maneuver/occlusion/node-loss replay,
sensor-specific latency and health-window calibration, broader camera/bbox fixtures, RMSE/NIS/NEES
consistency, cooperative runtime validation, and model-set/adaptive-covariance comparisons.
Replay schema v1, legacy JSONL compatibility,
covariance-required CSV replay, raw and fusion latency audit, sensor-health summaries, timestamp
uncertainty, covariance floor/ceiling limiting, covariance scale reason passthrough, region quality
summaries, region window helpers, covariance-growth helpers, recon cue summaries, source de-dup,
nested EO camera metadata replay, real CV field normalization, dry-run fixture schema checks, and
Blocks JSONL replay are already implemented baselines.

## Centralized Cooperative Localization P1 Foundation

The optional `cooperative.py` path implements the D1-owned centralized numerical foundation without
changing `FusionAdapter` defaults. A caller must provide observations that already share a
center-owned canonical `global_track_id`; the helper never associates targets, consumes truth IDs,
or creates/rebinds a track identity.

Bearing observations are transformed from calibrated sensor/body geometry into NED rays and
propagated to one estimate timestamp. The weighted least-squares solution includes bearing,
platform-pose, sensor-extrinsics, timing, and process uncertainty. It rejects fewer than two unique
rays, short baselines, near-collinear LOS geometry, excessive time skew, missing covariance under
the default policy, deficient/ill-conditioned information, negative depth, and excessive residual.
The summary retains all measurement/arrival timestamps and reports observer lineage, pairwise LOS
angles, information rank/condition, residuals, covariance inflation, and the accept/reject reason.

`covariance_intersection()` provides a dependency-light state-fusion baseline for unknown cross
correlation. It propagates 6-state NED estimates to a common time, suppresses repeated message UUID
or identical source lineage, preserves the supplied canonical ID, and produces a covariance no more
confident than the corresponding false-independent information sum. This is not a distributed
consensus path, a D2 association implementation, or a runtime integration claim. AirSim multi-seed
replay, D1/D2 two-stage association/fusion, maneuver and occlusion benchmarks, and distributed
end-to-end validation remain open.

## Current P0/P1/P2 Status (2026-07-12 Documentation Sync)

The current main-level status is recorded in
`subagent_reviews/MAIN_IMPLEMENTATION_GAP_AUDIT.md`. The D1 capability baseline remains
`research_modules/airsim_runtime/outputs/p1_p2_validation_20260711/P1_P2_VALIDATION_SUMMARY_CN.md`.
Commit `33e6fa0` and the 2026-07-12 PNG delivery validation changed D5/D6/D7 and main/runtime, not
D1 source or tests. D1 therefore has no behavior change in that delivery pass: its full regression
remains `62 passed`, its P0 contracts stay closed as regression baselines, and its open P1 replay,
cooperative-runtime, statistical-calibration, model-set, and adaptive-covariance work remains open.
The 2v2 `20/20`, post-lock dropout, and M5N2 `0/9` results are downstream control evidence, not D1
fusion-accuracy acceptance. P2/P3 planning is unchanged.

The P1 contract layer is closed: the main episode bus writes the D1 governed replay manifest and
truth-stripped online records while keeping truth in a separate offline-label path. In the 10-seed
ComputerVision batch, the downstream T001 two-primary contract met its 8/10 acceptance threshold;
the secondary and distributed 3/3-ACK commit cases passed, and the 2/3-ACK case aborted fail-closed.
These downstream results show that D1 state, covariance, timing, and lineage can feed the governed
contract chain; they do not add control or coalition responsibilities to D1.

- **P0 closed/regression baseline:** dual timestamps, NED, covariance, FDIR-light, covariance bounds,
  timestamp uncertainty, source-lineage de-duplication, and N-target input remain mandatory. The
  current D1 regression baseline is `62 passed`.
- **P1 contract layer closed:** governed replay/schema/provenance is used by main, online truth is
  isolated from offline scoring labels, and D1 timing/covariance/lineage records are present in the
  accepted CV and degradation/fail-closed episode chain.
- **Open D1 validation/enhancement:** real multi-seed maneuver/occlusion/node-loss/cooperative replay,
  sensor-specific latency and health-window calibration, camera/bbox fixture expansion,
  RMSE/NIS/NEES consistency, and model-set/adaptive-covariance comparison remain open. These are not
  reasons to reopen the P1 contract-layer result.
- **Physical boundary:** the 15 s SimpleFlight batch is diagnostic only. Its 0/30 active-pair physical
  intercept result does not close physical interception and is not a D1 fusion-accuracy acceptance.
- **P2 isolated only:** the frozen governed-replay harness now reports RMSE/NIS/NEES/time for the
  current path. FilterPy and Stone Soup are unavailable in the validated environment and emit an
  explicit `unavailable_reason`; they do not replace the NumPy EKF/fixed-lag default path.

The next D1 sequence is real multi-seed replay and statistical calibration, followed by optional
association-to-fusion and model-set comparisons. The acceptance command is:

```bash
PYTHONPATH=research_modules/d1_sensor_fusion/src pytest -q research_modules/d1_sensor_fusion/tests
```

## Governed Replay Manifest And Serializer

`serialize_governed_replay()` is the frozen online entry point for main. It returns a JSON-safe
`{"manifest": ..., "records": [...]}` bundle and validates the full batch before returning. The
manifest uses `d1.governed_replay_manifest.v1` and records the observation schema, NED fusion working
frame, scenario/config IDs, versions and digests, seed, timestamp ranges, coverage cells, and an
opaque source-lineage entry for every observation.

The strict path requires finite ordered dual timestamps, covariance matching the measurement shape,
`coverage_cell`, and JSON-safe lineage. Online records recursively remove truth, actor, and object
identifiers. `serialize_offline_governed_replay()` is the explicit offline-only path that places such
labels under `offline_truth`; it never restores them into online metadata. Existing unversioned
Blocks JSONL remains readable through the legacy compatibility reader, but it does not satisfy the
strict governed manifest contract.

This closes the D1-owned P1 manifest/serializer implementation. The main episode bus now adopts the
API with scenario/config provenance and seed data; D1 still does not own AirSim launch, episode order,
or runtime report generation.

## Isolated P2 Filter Benchmark

`p2_benchmark.py` consumes the frozen
`tests/fixtures/p2_governed_filter_benchmark_v1.json` bundle. It validates the governed manifest,
NED working frame, dual timestamps, observation covariance, source lineage, and truth-stripped online
records before running the existing `FusionAdapter`. The separate `offline_truth` sidecar is used only
after filtering to compute position RMSE and six-state NEES; track NIS is read from the current path.

Run the benchmark with:

```bash
PYTHONPATH=research_modules/d1_sensor_fusion/src \
python3 research_modules/d1_sensor_fusion/scripts/run_p2_isolated_benchmark.py
```

The 2026-07-11 validation produced RMSE `0.2335 m`, mean NIS `0.0426`, mean NEES `0.0651`, and
`6.9-10.1 ms` wall time across two runs of six observations on the validation host. The low NIS/NEES values indicate a
conservative covariance on this small synthetic fixture; they are evidence that the metric path runs,
not a real-sensor consistency acceptance. Neither optional dependency is installed. FilterPy and
Stone Soup therefore report `status=unavailable`, null metrics, and a non-empty `unavailable_reason`.
No optional package was added to default requirements and no online D1 code path was changed.

## Governed Long-Replay Challenge (2026-07-12)

D1 now exposes a deterministic, main-callable synthetic long-replay fixture without changing the
default NumPy EKF path:

```python
from d1_sensor_fusion import build_long_replay_scenario, summarize_long_replay

scenario = build_long_replay_scenario()
summary = summarize_long_replay(scenario).to_dict()
```

The official CLI writes the same `LongReplaySummary.to_dict()` payload as JSON:

```bash
python3 research_modules/d1_sensor_fusion/scripts/run_long_replay.py \
  --seed 17 --duration 60 --target-count 5 \
  --output research_modules/d1_sensor_fusion/reports/long_replay_summary.json
```

`--output` is a JSON file path; its parent directory is created when needed. The CLI defaults to
seed 7, 60 seconds, three targets, and `reports/long_replay_summary.json`.

The default fixture runs for 60 seconds with three crossing targets and generates range-dependent
radar observations, coarse acoustic bearings, EO pixel observations, a dense-crossing clutter
window, full/partial EO occlusion, delayed radar OOSM, and relay duplicates. Main can override the
target count, seed, duration, rates, and event intervals through `LongReplayConfig`; no 2v2/5v5
constant is used.

The fixture freezes scenario, config, replay-schema, summary-schema, and threshold-profile versions.
Every online observation keeps measurement/arrival timestamps, covariance, NED working-frame
metadata, coverage cell, and opaque source lineage. Observation IDs and lineage contain no stable
target slot. Truth labels and six-state trajectories are returned only through the explicit
`d1.long_replay_offline_truth.v1` sidecar and never enter online observations or `GlobalTrack`.

`summarize_long_replay()` reuses `FusionAdapter`, raw/fusion latency audits, sensor health, and fixed
region windows. It reports modality/event counts, final track/source summaries, truth-leak count,
and metric availability. RMSE/NEES remain explicitly unavailable until offline D2 canonical-ID
mapping exists. A default smoke run produced 843 observations, 21 injected radar OOSM events, six
deduplicated relay copies, 29 region windows, and zero online truth leaks in about 8.8 seconds on the
validation host. This closes the D1-owned synthetic long-replay construction/summary gap, not the
real Blocks/CV multi-seed calibration gap. The CLI has a subprocess regression that verifies
argument propagation, output-directory creation, summary schema, and zero online truth leakage.

## Real AirSim persisted-input freeze

`airsim_replay_freeze.py` reads main-persisted JSON/JSONL observations or frames with embedded
`sensor_observations`/`observations`/`records`. It does not import the AirSim SDK and processes the
input array length without a 2v2/5v5 constant.

The output is `manifest.json`, `sensor_observations.jsonl`, `offline_truth.json`, and `summary.json`.
Online records reuse `d1.sensor_observation.v1` and preserve measurement/arrival timestamps,
covariance, canonical observation frames, NED fusion working frame, coverage cell, lineage, sensor
health, event labels, and scene/profile/source-schema identity. Missing processing/publish timestamps
or sensor health are explicitly `unavailable`; they are not inferred from arrival time.

Legacy Blocks IDs may encode actor/object/truth identity. The freezer replaces online observation IDs
with opaque sequence IDs and recursively removes identity keys and strings containing known identity
tokens. Truth ID and NED position are written only to the evaluator-only
`d1.airsim_offline_truth.v1` sidecar. Crossing, occlusion, missed detection, false alarm, OOSM, and
node-exit labels are diagnostic evidence; a frame without a real measurement never creates a sensor
observation.

```bash
python3 research_modules/d1_sensor_fusion/scripts/freeze_airsim_replay.py \
  INPUT.jsonl OUTPUT_DIR \
  --scenario-id dense-crossing --scenario-version 2 \
  --config-id blocks-settings-v4 --config-version 4 --seed 17 \
  --target-spacing-m 4.0 \
  --profile-id p1-dense-v1
```

This closes the D1-owned persisted-input freeze and truth-sidecar separation gap. Main still owns real
AirSim capture; D2/D6 still own offline identity scoring and multi-seed RMSE/NIS/NEES and threshold
calibration. D1 full regression after the sidecar follow-up is `74 passed`.

### Offline truth sidecar deduplication

The evaluator sidecar has one deterministic sample per `(truth_id, timestamp)`. If a frame truth
sample has a position and observation metadata has only the same identity, the available position
replaces the unavailable sample regardless of input order. Two available positions within `1e-6 m`
are treated as the same sample; inconsistent available positions reject the freeze instead of
silently selecting one. Samples at different timestamps remain separate. An identity with no source
position remains `position_availability="unavailable"`; no position is interpolated or fabricated.

Both the sidecar and summary publish position-availability counts so D2/D6 can distinguish valid
position labels from identity-only labels before strict offline scoring.

### Capture provenance gate

AirSim freezing now requires an explicit capture-side declaration containing scenario/config version,
seed, `target_spacing_m`, and `evidence_path`. The captured spacing is authoritative and is never
inferred from truth positions. A conflicting CLI/API declaration or inconsistent declaration across
payloads fails closed. Manifest and summary expose per-field availability; online records remain
truth-free, while the evaluator sidecar is bound by the capture-provenance digest. Regression coverage
includes 4 m and 2 m profiles across 20 seeds each. Current D1 regression: `79 passed`.

## Online scene-observation anonymization (2026-07-14)

AirSim or another simulator may use scene truth to generate a noisy `SensorObservation`; that does
not authorize the online fusion path to receive the actor/object identity used to generate it. Main
or runtime must apply the public boundary before sending scene-derived observations to online D1/D2
algorithms:

```python
from d1_sensor_fusion import (
    anonymize_online_observations,
    assert_online_observations_identity_free,
)

online = anonymize_online_observations(
    scene_observations,
    identity_tokens=scene_actor_names,
    stream_id="online",
)
assert_online_observations_identity_free(
    online,
    identity_tokens=scene_actor_names,
)
```

`anonymize_online_observations()` returns new objects. It recursively removes truth/actor/object/
segmentation identity keys, removes inferred or caller-supplied identity tokens from nested values
and `classification_hint`, and replaces `observation_id` plus source lineage with frame-local opaque
IDs. It preserves measurement, covariance, both timestamps, sensor fields, communication timing,
and sensor/camera geometry. `assert_online_observations_identity_free()` fails closed on any remaining
identity key or supplied/inferred identity token.

The existing dry-run and offline evaluator paths are unchanged. In particular, evaluator-only truth
sidecars remain available from the original scene observations; callers must not build an offline
sidecar from the anonymous online copies. Validation on 2026-07-14 used two two-observation EO batches
whose geometry and all non-identity fields were identical while target, actor, and truth names were
changed. Acceptance required exact equality of every anonymized `SensorObservation` field, unchanged
numeric/camera geometry, zero identity leakage, validator rejection of injected leaks, and unchanged
offline sidecar labels. All conditions passed; full D1 regression is `83 passed`.

This closes the D1-owned P0 API gap. System closure still requires main/runtime to call this boundary
at every scene-state online ingress. Values whose identity is not represented by an identity metadata
key must be supplied through `identity_tokens`; omission is a caller contract violation and the main
integration must maintain the complete scene identity-token set.

## Association governance and fixed-lag checkpoint correction (2026-07-14)

An audit of the persisted AirSim M5N2 seed-001 episode found that D1 could update one track more than
once from one physical observer scan, create a duplicate radar birth after a strict-gate miss, and
discard intermediate filter posteriors while pruning the fixed-lag window. The last behavior made a
later replay restart from the original anchor and could move an existing state discontinuously.

`FusionAdapter` now limits each `(modality, observer, scan)` to one update per track, permits only a
unique recent mature-track radar reacquisition under a separate chi-square gate, suppresses ambiguous
radar births, and audits inconsistent bearing-only Cartesian corrections. Fixed-lag pruning now places
the posterior checkpoint immediately after the latest accepted observation not newer than the lag
boundary. This preserves the original process-noise intervals; observations older than the checkpoint
remain available in a history archive for legal measurement-time OOSM replay. Modality is part of the
scan key, so a delayed acoustic observation is not rejected merely because radar used the same scan
number.

Validation on 2026-07-14: focused association/OOSM tests passed `5/5`, the complete D1 suite passed
`87/87`, and main reported the complete AirSim runtime suite passed `134/134`. These are code and
interface regressions. The corrected D1 implementation has not yet rerun the same real AirSim seed;
elimination of the historical third birth and 31.8 s state jump remains a P1 episode acceptance item.

## Covariance contract hardening (2026-07-14)

Every observation entering `FusionAdapter`, online anonymization validation, versioned replay writing/
reading, or AirSim persisted-input freezing must now carry a modality-sized covariance: radar `4x4`,
legacy acoustic `1x1`, scalable `acoustic_3d` `2x2`, EO `2x2`, and lidar `3x3`. The matrix must be finite, symmetric, and positive
semidefinite. Invalid or missing input raises `ValueError` before a filter update; D1 no longer repairs
it with a default model, reshapes flat arrays, symmetrizes it, or resets it silently. Existing quality
scaling and covariance floor/ceiling handling still apply after a legal input passes this gate.

Unversioned historical records that omitted covariance are accepted only through
`migrate_offline_legacy_sensor_observation()`. That explicit evaluator-only API records the migration
mode, original missing reason, model/default identifier, parameter source, generation inputs, and
resulting dimensions under `covariance_imputation_provenance`. Migrated observations are rejected by
online fusion, online governed serialization, and AirSim freeze. Ordinary legacy readers fail closed.

Validation on 2026-07-14 covered missing, non-finite, non-symmetric, non-PSD, and wrong-sized radar
covariance; explicit radar legacy migration; governed replay; legal OOSM/fixed-lag observations; and
the existing seven-record AirSim freeze fixture. The full D1 suite passed `92/92`. No real AirSim
episode was run. Sensor-model defaults used for offline migration remain research defaults, not
real-sensor calibration evidence.

## 同帧批量 fixed-lag 处理（2026-07-14）

`FusionAdapter.process_batch(observations)` 是正式的同帧/同到达批次入口。它保留调用方给定
的到达顺序，并对每条观测分别执行 covariance 合同、`measurement_timestamp`/
`arrival_timestamp` 审计、NED/pixel 帧校验、source lineage 去重、observer scan 约束和关联；
优化仅缓存同一航迹历史版本在同一测量时刻的状态，并把每条更新后的全历史发布重放合并为
每个受影响航迹一次。它不会丢弃观测、伪造同步时间、缩短 fixed-lag 证据或改写来源信息。

main 的推荐调用为：

```python
batch_result = fusion_adapter.process_batch(frame_observations)
global_tracks = list(batch_result.tracks)
batch_audit = batch_result.summary.to_dict()
```

`tracks` 是处理完整个输入序列后、统一发布于本批最终融合时刻的确定性快照，不是每条观测的
中间快照。`summary` 显式给出输入/接受/未接受/重复观测数、创建/更新数量、受影响航迹、历史
重放数、origin 重放数、状态缓存命中/未命中、终结重放数和被合并的更新重放数。空批次返回
当前航迹快照；`ingest_many()` 保持先按 arrival 排序的兼容语义并改用该批处理实现。

2026-07-14 验证包含 6 个无随机 seed 的构造测试：逐条/批量数值等价、乱序 OOSM、relay
重复 source、radar/lidar/acoustic 跨模态、fixed-lag 检查点边界和确定性重放性能。5 航迹、
15 条同帧观测中，历史重放由 95 次降至 24 次，减少 74.7%，状态与 covariance 在
`1e-9` 绝对容差内等价。对已有 M5N2 seed-001 baseline 的前 40 帧、786 条持久化观测做
D1-only 重放，逐条为 18.05 s/1267 次重放，批处理为 5.70 s/351 次重放，约 3.17 倍加速，
状态与 covariance 最大绝对差均为 0。D1 全量 `98 passed`。

这些证据关闭 D1-owned 的批量 API 与最少重放实现缺口，但 main/runtime 尚未改用该接口，
完整 245/248 帧控制循环、多 seed 增益和 100 ms 预算仍是系统 P1 验收项。

## 可扩展三维扫描融合入口（2026-07-20）

`Scalable3DFusionAdapter` 是面向 `scalable_3d_simulation` 在线总线的 D1-owned 入口。它以
鸭子类型消费 `OnlineSensorBatch` 或同合同 `SensorMeasurement` 扫描，不导入 main-owned
模块；递归拒绝 truth/actor/object/entity/target ID 和 offline truth sidecar。雷达输入
`[range, azimuth, elevation]` 在 canonical 合同中保留一个补零径向速度和对应方差，但同时
标记 `radial_velocity_observed=False`；滤波量测模型只消费前三维，补零值不进入 EKF 更新。
位置 covariance 通过解析 Jacobian 传播，速度以零均值、各轴方差 `25 m2/s2` 的独立高斯
先验起始，位置-速度交叉块为零。原始 `3x3` 球坐标 covariance、
`measurement_timestamp`、`arrival_timestamp`、sensor position 和匿名 observation lineage
均被保留。

新 `process_scan_batch()` 与旧 `process_batch()` 语义不同。旧入口继续保证逐条处理等价，供
2v2、5v5、M5N2 回归使用；新入口先针对扫描前航迹和整扫描点迹构造三维马氏代价矩阵，再用
一对一匈牙利匹配更新，每个未匹配雷达点迹都可独立 birth。这样不会再因同 observer scan 的
固定门限把多个可分点迹误当成对同一航迹的重复更新。数量完全由输入扫描长度决定。

main 新增的二维 `acoustic_bearing=[azimuth,elevation]` 映射为 `acoustic_3d` NED 弱约束；
它只能更新既有雷达航迹，不能单独 birth。输入 `soundprint_is_identity` 必须为 `False`，随后
转换为 `soundprint_category_only=True`；类别概率只进入 track metadata/类别提示，不进入几何
关联、航迹 ID 或 truth hint。`Scalable3DFusionAdapter` 禁止启用
`use_truth_hints_for_association`。

2026-07-20 使用 `scalable3d-world-v1`/`scalable3d-observation-v1`、seed 7，在
5/20/50/100/200 五档各运行两次无漏检雷达扫描，共 10 个 batch、750 条匿名雷达量测。首扫
birth 和次扫 update 均为 `5/5、20/20、50/50、100/100、200/200`；200 规模不再收缩为约
34 条，track ID 集保持不变。另有 2 目标、6 条量测的迟到扫描回归，2 条 OOSM 均在量测时刻
重放且航迹数保持 2；二维声学专项证明无雷达先验时 `0` birth、有先验时只更新 5 条航迹。
新增专项 `9 passed`，D1 全量 `120 passed`。一次本机非门限化探针中 200 点首扫约 0.108 s、
次扫约 0.392 s；该单次耗时不是实时性能验收。

当前 D1-owned 实现和合同回归已完成，main scalable 三维质点 runtime 也已接入此 adapter，并在
clean `8f86192` 的 200v200 三 seed 中通过安全与语义回归。D2 的原生六维关联、漏检/虚警下的
航迹确认与删除、多 seed dense crossing 的 recall/ID continuity、长期 NIS/NEES 和实时预算仍需
跨模块验收；该接线结论不扩展到 AirSim runtime。

### 无多普勒速度稳定性修复（2026-07-20）

`Scalable3DFusionAdapter` 对位置-only radar 使用 3 自由度 NIS 门控，默认阈值为
`chi2_3(0.999)=16.26623619623813`。门外观测保留在合法 observation history 中供确定性 OOSM
重放，但不修改该时刻的预测状态；航迹 metadata 记录本次 replay 的创新数、实际滤波更新数、
拒绝数和匿名 observation ID。速度先验方差和门限均为显式可配置参数，不读取场景目标速度，
也不对状态做速度裁剪。

自动化验证使用 2026-07-20、radar-only、seed 17。200 条航迹连续 10 个 scan，共 2,000 条
匿名 radar measurement，数量和 ID 集始终保持 200，所有速度有限、covariance 保持 `6x6`；
末帧速度模长 median/P90/max 为 `3.87/6.43/8.54 m/s`，速度 covariance trace 为
`57.97/60.69/61.19`。50 条开发探针的修复前后速度分别为
`6.28/12.16/21.03 -> 3.99/6.12/9.69 m/s`，修复后 covariance trace 仍为
`58.22/60.43/60.90`，没有通过隐藏方差宣称精确速度。顺序/乱序 2 航迹、3 scan 回归在共同
发布时刻的 state/covariance 差不超过 `1e-9`，并保留原始双时间戳。专项 `13 passed`，D1
全量 `124 passed`。

当前限制是零均值先验会在短时间窗内收缩速度均值；其方差仍需至少 20 个未见 seed 的
NIS/NEES 与速度误差覆盖率标定。D2 会再次滤波 D1 六维状态，D2 速度均值和 D3 可达性/分配
数量必须由 main 用当前代码正式复测。本轮没有启动或修改 AirSim runtime。

## Versioned consistency evidence contract（2026-07-20）

D1 现提供独立于 track metadata 的逐观测 consistency evidence。在线 schema 为
`d1.consistency.online_evidence_record.v1` 和
`d1.consistency.online_evidence_bundle.v1`；`FusionAdapter.consistency_evidence_records()`
返回当前最终 replay 口径的 DTO，`export_consistency_evidence(provenance)` 冻结 episode
bundle。记录保留匿名 `observation_id`、opaque source-lineage digest、sensor ID/type、双时间戳、
innovation 维数、NIS、gate/accepted、直接 radar range 与 versioned range bin、confidence/
quality/covariance scale reason、可用时的 D1 `source_global_track_id`、六维 NED
estimate/covariance、OOSM
和 replay revision。未关联 acoustic/EO、重复和其他拒绝项保留显式 unavailable reason，不补零。

在线 bundle 固定 `source_schema_version/source_digest/config_digest`，并分别计算 records SHA-256
与 bundle SHA-256。固定字段中不含 truth target、actor 或 object identity。在线结果和离线结果
是两个物理 artifact：`build_offline_truth_state_sidecar()` 构建独立 truth state sidecar；D2 先按
source observation lineage 形成 canonical-ID 决策，再用
`build_d2_lineage_mapping_sidecar()` 输出 digest-bound evaluator adapter。adapter 以
`observation_id + measurement_timestamp` 连接 D1 evidence，同时保留 D2-owned
`global_track_id`，不把 D1 source ID 提升为 canonical ID；`evaluate_offline_consistency()` 才计算 position/velocity
RMSE、NEES、normalized NEES、NIS/normalized NIS 和 gate coverage。缺 sidecar/mapping、未知或重叠
映射、hash/provenance、六维、精确 measurement-time 对齐失败时对应 truth metric unavailable；
不使用近邻、名称或目标顺序猜测。奇异 estimate covariance 只使 NEES fail closed，RMSE 仍可用。

两个 bundle 的 `aggregation_records()` 输出含 scenario/run/seed、sensor、range bin 和输入 digest
的扁平有限 JSON rows，供 main writer 持久化和 D6 分组。2026-07-20 构造合同回归新增 `12`
项：接受/拒绝创新、顺序/OOSM、四档 radar range、acoustic/EO availability、1/4/7 输入规模、
缺失/错误 lineage mapping、额外在线 truth 字段拒绝、truth 篡改、维数/时间错位、奇异
covariance 和 non-finite fail-closed；
已知误差夹具得到 position RMSE `5 m`、velocity RMSE `12 m/s`、NIS gate coverage `0.5`。
main 复跑 D1 全量为 `136 passed`。这些结果只关闭 evidence/evaluator 合同，不是正式多 seed
精度、coverage 或 covariance 标定达标结论；现有 NumPy EKF、量测模型、门限和 track ID 未改。

## 版本化扫描输入整理（2026-07-22）

`ScanInputOrganizer` 位于在线批次转换与 `process_scan_batch()` 之间。其输入是完整
`SensorScanFrame`，输出只包含越过量测时间水位线后可以安全释放的 `released_scans`。扫描中的
每条 `SensorObservation` 原样保留 `measurement_timestamp`、`arrival_timestamp`、covariance、
canonical frame、NED/source frame 元数据和 source lineage。输入先执行 covariance 与在线身份
隔离检查；truth/actor/object 字段不会进入摘要、缓冲或摘要哈希。

`SensorScanFrame` 采用字段级不可变快照，不对包含 `mappingproxy` 的观测做通用深拷贝。量测、
协方差和元数据中的数组均建立独立只读副本；嵌套 `Mapping`、序列和集合递归冻结。该处理兼容
main 的只读视觉相机模型元数据，并在快照完成后继续执行协方差和递归 truth 隔离检查。

水位线定义为当前已接收唯一扫描的最大量测时刻减去 `max_lateness_s`。量测时刻严格早于既有
水位线的扫描整帧拒绝；等于边界的扫描继续留在窗口中，以允许多个来源在同一量测时刻到达。
窗口内乱序扫描按量测时刻、再按接收序号确定性释放。同一 scan/payload、同一 source lineage
重发及 scan ID/时间/内容冲突分别记为 duplicate、replay 和 timestamp conflict。任何拒绝都不
产生部分扫描，也不会出现在 `released_scans`。

配置和运行 DTO 使用以下版本：

- `d1.scan_input.config.v1`；
- `d1.scan_input.frame.v1`；
- `d1.scan_input.audit_event.v1`；
- `d1.scan_input.audit_summary.v1`；
- `d1.scan_input.result.v1`。

缓冲同时受 `max_buffer_residence_s`、`max_buffered_scans` 和
`max_buffered_observations` 限制。scan/source-lineage claim ledger 也有独立数量上限。容量不足
时拒绝新整帧，不驱逐一个已接受扫描来换取另一个扫描。逐帧事件和累计摘要明确记录 received、
buffered、reordered、released、duplicate、replay、timestamp conflict、too-late、buffer
overflow、buffer expiry 和 claim capacity overflow。

main-owned `scalable_3d_simulation` 推荐按以下方式接入，但 D1 本轮没有修改 main 文件：

```python
observations = sensor_observations_from_online_batch(online_sensor_batch)
frame = SensorScanFrame.from_observations(
    observations,
    scan_id=online_sensor_batch.batch_id,
)
decision = scan_input_organizer.ingest(frame)

last_state_result = None
for scan_index, released_frame in enumerate(decision.released_scans):
    state_result = fusion_adapter.process_scan_batch(
        released_frame.observations,
        materialize_tracks=False,
    )
    if scan_index + 1 < len(decision.released_scans):
        publish_lightweight_d1_audit(state_result.to_dict())
    last_state_result = state_result
if last_state_result is not None:
    track_snapshot = fusion_adapter.materialize_global_tracks()
    full_payload = last_state_result.to_dict()
    full_payload.update(track_snapshot.to_dict())
    persist_full_d1_publication(full_payload)
    publish_to_d2(track_snapshot.tracks)

scan_events = [event.to_dict() for event in decision.events]
scan_audit = decision.audit.to_dict()
```

进入同一 organizer 的扫描必须已经换算到统一 episode 时钟和 D1 canonical frame；该 adapter
不估计传感器时钟偏差，也不替代坐标变换。当 episode 时钟继续前进但没有扫描到达时，main 调用
`advance_arrival_time(current_episode_time)`，以执行缓冲驻留时间上限；该调用不会伪造量测或
推进量测水位线。episode 输入结束时调用 `close()`，再按量测时刻释放尚未过期的尾部扫描，并
同样逐帧送入 `process_scan_batch()`，再发布最后一个融合快照。`close()` 后不再接收新扫描。每个 episode 的 manifest
应记录上述 schema 和 `ScanInputConfig.to_dict()`，D6 消费 event/audit，不参与控制路径。

2026-07-22 的确定性 API 测试不使用随机 seed，也未运行 AirSim。15 项专项覆盖有序扫描、窗口
内乱序、超窗迟到、同时间多源、duplicate、relay replay、timestamp conflict、到达时刻回退、
扫描/观测容量、驻留超时、1/7/200 动态观测数量、truth 注入拒绝及
`OnlineSensorBatch -> SensorScanFrame -> released_scans -> process_scan_batch` 组合。新增回归还
覆盖嵌套 `mappingproxy` 相机元数据的独立只读快照及其中 truth 字段拒绝。专项 `15 passed`，
D1 全量 `151 passed`。

该 adapter 只整理扫描输入，不是固定滞后卡尔曼 OOSM 平滑器。释放后的量测仍由现有
`FusionAdapter` 依据 measurement time 做 EKF 更新和 fixed-lag replay。D1-owned P1 输入合同
已关闭；main 正式接线、20/50/100/200 长 episode 的 lateness/residence/capacity 标定、无扫描
时钟推进策略、吞吐和误拒率仍是系统 P1。
