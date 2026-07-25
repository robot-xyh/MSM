# 第一研究模块：多传感器融合与目标配准算法与实施说明

> 文档日期：2026-07-25
>
> 适用范围：离线科研仿真、受治理回放和系统接口验证
>
> 实现依据：当前第一研究模块代码、`README.md`、`PLAN.md`、模块原理文档和系统总汇总

## 当前权威增量（2026-07-25）

### 固定滞后回放前缀累计摘要候选

构造参数 `replay_prefix_summary` 提供显式 A/B：

```python
reference = FusionAdapter(
    replay_prefix_summary="per_checkpoint_prefix_rebuild_v1",
)
candidate = FusionAdapter(
    replay_prefix_summary="fixed_lag_checkpoint_prefix_cumulative_summary_v1",
)
```

reference 是声明默认。candidate 默认关闭，实现 ID 为
`d1.fusion.replay_prefix.frozen_cumulative_summary_lazy_evidence_ranges.v1`。
execution config schema 为
`d1.fixed_lag_replay_prefix_summary_execution_config.v1`，diagnostics schema 为
`d1.fixed_lag_replay_prefix_summary_diagnostics.v1`。这些名称与关联稀疏预筛完全独立。

#### 摘要结构

每条航迹的 `_ReplayPrefixSummary` 是 frozen/slots 数据类，保存：

1. `schema_version` 和 `checkpoint_revision`；
2. checkpoint observation ID 与排序键 tuple；
3. 从初始状态到完整 checkpoint 前缀的 NIS tuple；
4. innovation gate 拒绝 observation ID tuple；
5. 需要刷新 consistency evidence 的 observation ID tuple；
6. evidence 结构修订号。

摘要不保存可变 list、dict 或 ndarray，也不与后续 checkpoint 追加共享可变别名。状态和
协方差仍从最后一个既有 checkpoint 的独立 `EKFState.copy()` 取得。

#### 命中条件

`_try_reuse_replay_prefix_summary()` 只在下列条件同时成立时返回摘要：

1. selector 显式选择 candidate，incremental replay cache 已启用；
2. matching prefix 大于 0，并等于当前 checkpoint 列表长度；
3. summary schema、checkpoint 修订、数量、首尾身份和排序键匹配；
4. NIS、排序键和 consistency 序列长度守恒；
5. 当前 consistency capture context 属于同一 `global_track_id`；
6. cached/trusted consistency counter refresh 已启用；
7. evidence 结构修订与摘要一致，initial/checkpoint evidence 身份关系一致。

任何条件失败都会写入固定 fallback reason。候选随后精确物化未决 evidence 计数并执行
reference 的初始证据刷新、逐 checkpoint NIS/gate 重建和 evidence 更新。

#### 中间前缀完整性

命中路径保持 O(1) 完整性检查，不逐项扫描中间 checkpoint。
`replay_checkpoint_revision` 是完整中间前缀的确定性完整性边界。模块内部只有以下逻辑
可以改变 checkpoint 列表：

1. 全量清空；
2. 从受影响排序键截断后缀；
3. 在完整前缀后追加新 checkpoint；
4. fixed-lag 重基准后替换保留后缀。

四类变更都经过 `_mark_replay_checkpoint_list_changed()`：先物化该航迹未决的
consistency evidence 刷新，再递增 revision 并清除旧 summary。中间迟到观测由
`_invalidate_replay_checkpoints(from_sort_key=...)` 先截断旧后缀，随后按新顺序重新滤波。
因此旧摘要不可能跨内部列表变更命中。直接从模块外修改 `TrackRecord.replay_checkpoints`
属于私有状态破坏，不是公共 API 合同。

#### 一致性计数账本

一次摘要命中等价于对 consistency observation 前缀执行：

\[
\text{replay\_count}_i \leftarrow \text{replay\_count}_i + 1,\qquad
\text{replay\_revision}_i \leftarrow r,
\quad i < L.
\]

候选把该操作记录为 `(prefix_length=L, replay_revision=r)`。相同长度只累计事件数并保留
最新 revision。物化时从最长前缀向最短前缀做后缀累计：

\[
\Delta c_i=\sum_{L>i} n_L,\qquad
r_i=\max_{L>i} r_L.
\]

每条 evidence 最终调用 `with_replay_counters()` 一次，得到与逐回放刷新相同的
`replay_count/replay_revision`。账本在公开 evidence snapshot、记录读写、checkpoint
失配/失效和 fixed-lag 重基准前物化。它不改变 `cached_consistency_refresh_count`：
候选在命中时按逻辑覆盖条数一次性增加该既有计数。

#### 测试与微基准

专项测试覆盖正常前缀、迟到量测、门控拒绝、6 秒 fixed-lag、pre-checkpoint OOSM、
部分前缀、前缀变化、无 checkpoint、summary schema/version 失配、禁用 consistency
refresh、冻结摘要别名隔离，以及四 checkpoint 中间插入导致的 revision 推进、旧后缀
失效和新顺序重建。D1 全量回归为 `484 passed in 25.10s`。

冻结 200v200 fixture 包含 8 个扫描和 1,600 条匿名观测。7 对新鲜 A/B 每个 arm 执行
5 轮完整回放和一次公开 evidence 物化。reference/candidate 中位墙钟为
`0.037882166/0.024329944 s`，改善 `35.775%`；candidate `7/7` 更快，配对均值差
bootstrap 95% 区间为 `[-0.014455845, -0.012638062] s`。

每对的后验、协方差、NIS、门控 ID、consistency evidence、既有 operation counts、
双时间戳/gate metadata、checkpoint 和公开 `GlobalTrack` 哈希均相同。candidate 的新增
diagnostics 单独比较，不混入既有 operation-count 等价门。

当前结论仅为模块微基准通过。selector 仍默认 reference，尚未执行 main 同提交正式矩阵，
不得写成默认准入、系统实时或 AirSim/硬件证据。

### 正式拒绝后保持默认关闭的模态感知保守预筛

构造参数 `association_sparse_prefilter` 接受两个稳定 selector：

```python
reference = FusionAdapter(
    association_sparse_prefilter="disabled_v1",
)
candidate = FusionAdapter(
    association_sparse_prefilter="modality_conservative_quadratic_bound_v1",
)
```

默认值是 `disabled_v1`。reference 继续对非雷达创新协方差执行原四维矩阵栈
`np.linalg.pinv()`，没有经过候选掩码。candidate 先计算原量测模型、原投影、原雅可比、
原协方差和原残差，再认证下界。认证失败的 pair 仍进入同一精确求解；认证成功且下界严格
超过 `association_gate` 的 pair 才写为无穷代价。

认证同时要求：

1. 创新协方差全部有限并逐元素严格对称；
2. Gershgorin 最小下界在数值裕量后严格大于 0；
3. 该下界严格高于 `1e-15` 伪逆截断阈值的保守上界；
4. 残差平方范数有限；
5. 下界严格大于原门限，等于门限不删。

声学残差先调用原 `wrap_residual()`，光电残差来自原 `eo_project()`。无法为未知模态建立
上述证明时，诊断记入 `other/fallback` 并保留原行为。该路径不读取 truth ID、actor 名称或
离线标签。

`association_sparse_prefilter_execution_config()` 返回
`d1.association_sparse_prefilter_execution_config.v1`，记录声明默认、当前 selector、
实现 ID、rollback selector、旧雷达下界状态和固定逐模态策略。
`association_sparse_prefilter_diagnostics()` 返回 schema
`d1.association_sparse_prefilter_diagnostics.v2`。固定模态桶为
`radar/lidar/acoustic/acoustic_3d/eo/other`；每桶固定字段为
`candidate_pair_count`、`conservative_prefilter_rejection_count`、
`exact_innovation_solve_count`、`exact_gate_pass_count` 和 `fallback_count`，并发布
逐桶计数边界及固定桶数守恒。fallback 是无法认证 pair 与批量精确求解回退逐 pair 的
并集计数；它与 exact solve 可重叠，但同一 pair 至多记一次。

专项测试包含 selector、固定字段、1/2/3 维随机正定矩阵、角度环绕、奇异/近奇异/非有限
协方差、雷达/LiDAR/二维声学/三维声学/光电扫描、64×64 密集输入、门限等号边界和
candidate-on/off 规范输出等价。D1 全量为 `473 passed in 24.45s`。

正式集成状态不由上述模块测试决定。2026-07-25，D6 使用
`d6.d1_association_sparse_prefilter_multiseed_evaluation.v1` 评估 clean source commit
`9302ccede2ca513c2235370e1a464fc88bc41150`；冻结 matrix SHA-256 为
`a7162d014d1c3c0f207355b24a5d7159bf3486d134ca21876f7469d1e915b71d`。200 个目标、
200 个资源、2 个侦察节点的 short seeds 1131-1140 和 long seeds 1131-1133 形成
13 pair/26 个 fresh episode。13/13 pair 的业务语义、有限状态、online truth use=0 和
逐模态 exact gate-pass 相等通过；非雷达精确求解削减 `86.636767%`。

正式失败门为 short 更快 `7/10 < 8/10`、short D1 fusion 改善
`0.228437% < 1%`、short paired bootstrap 原始变化 95% 上界
`0.443531% > 0%`、short core 改善 `0.091096% < 0.25%`、long D1 fusion 改善
`0.713776% < 1%`。D6 verdict 为 `reject`。`disabled_v1` 继续作为默认，
`modality_conservative_quadratic_bound_v1` 只允许显式研究启用；不得以局部求解削减改写
默认选择或冻结矩阵。

历史上，120 航迹、14,400 pair/模态、7 次交错微基准的非雷达合计 P50 为
`0.538083 -> 0.487310 s`。LiDAR、二维声学、三维声学和光电精确求解分别为
`14,400 -> 3,126/6,306/6,306/3,295`，更快次数分别为
`7/7、6/7、7/7、7/7`。雷达两臂走同一旧下界，本轮 candidate P50 慢 `0.221%`。报告位于
`../reports/D1_ASSOCIATION_SPARSE_PREFILTER_PERFORMANCE_20260725_CN.md`。该微基准只用于
追溯候选形成过程，不是主线准入依据。正式候选最低 RTF 为 `0.206273 < 1`，系统实时、
AirSim、目标硬件、实机、实飞和正式融合精度仍未闭合。

### 在线批次到扫描帧正式默认

D6 正式 schema `d6.d1_online_batch_frame_multiseed_evaluation.v1` 绑定 source commit
`43feaf600f288a85ce76a76862334256f0d0d352` 与 matrix SHA-256
`4afbf9ac273763a16aa01cc744fd67b52e437099460b33377a128f986ac5719b`。13 pair/26
episode 的全部 gate 通过；short/long scan-input 改善
`38.289241%/36.275282%`，core wall 改善 `4.252745%/4.916501%`，candidate closed
`2665/2665`、fallback 0、online truth use 0。

当前调用方式为：

```python
default_builder = OnlineBatchFrameBuilder()
default_frame = sensor_scan_frame_from_online_batch(batch)

reference_builder = OnlineBatchFrameBuilder(
    implementation=ONLINE_BATCH_FRAME_REFERENCE_IMPLEMENTATION,
)
reference_frame = sensor_scan_frame_from_online_batch(
    batch,
    implementation=ONLINE_BATCH_FRAME_REFERENCE_IMPLEMENTATION,
)
```

前两条使用 `ONLINE_BATCH_FRAME_DEFAULT_IMPLEMENTATION` 指向的
`closed_immutable_batch_to_frame_v1`；后两条以单个 selector 参数回退
`convert_then_frame_v1`。execution config 中 `candidate_default_enabled=true`，显式
reference 的实际 implementation、implementation ID、请求计数和守恒仍完整可审计。

本次只提升默认 selector，没有改候选核心算法或安全合同。D2 单 pair 尾部关联开销仍需容量
观察；最低 RTF 为 `0.204490`，系统实时未闭合。正式证据为三维质点仿真，不是 AirSim、
目标硬件、实机、实飞或 RMSE/NEES/NIS 准入。

### 在线批次到扫描帧封闭交接（准入前实现基线）

原参考实现可以写成：

```text
完整 raw batch 身份检查
  -> 每条 raw measurement 再检查并转换
  -> 转换后 SensorObservation 集合检查
  -> SensorScanFrame 深快照和最终完整检查
```

main 的默认无 source-key R0 开发 cProfile 说明，中间两组检查与两端检查覆盖了相同对象层级。
候选不改公开转换器，而是新增专用批次到帧入口：

```text
完整 raw batch 身份检查
  -> 结构合格检查
  -> 私有深快照
  -> 私有 measurement 转换
  -> SensorScanFrame 深快照和最终完整检查
```

`sensor_scan_frame_from_online_batch()` 适合一次性调用。
`OnlineBatchFrameBuilder` 适合 main 在一个 episode 内复用，以便累计 implementation ID、
操作计数和守恒诊断。在该准入前阶段，两者默认选择 `convert_then_frame_v1`，显式
`closed_immutable_batch_to_frame_v1` 才进入候选；当前默认状态见上一节。

结构合格检查要求 batch 和 measurement 是冻结数据类，字段集合与在线合同完全一致；量测和
协方差必须是拥有自身存储的只读数值数组；metadata 必须由受支持的只读映射、元组、冻结
集合、只读数组或标量组成。该检查只决定严格快照函数能否处理当前结构，不声明 raw 对象绝对
不可变。候选随后复制全部字段，不向 `SensorScanFrame` 传递原对象别名。结构不合格时执行
完整 reference。结构检查或快照抛出普通 `Exception` 时记录失败并回退 reference；
`MemoryError` 单独记录为资源拒绝后原样抛出。`KeyboardInterrupt` 和 `SystemExit` 不被
捕获。候选不接受 `trusted`、`validated` 或 `skip_validation`，也不暴露私有快照类型。

私有转换仍执行批次非空、有限时间、arrival 不早于 measurement、sensor 与双时间戳一致、
模态维数、协方差和 NED/像平面合同。最终 `SensorScanFrame` 继续执行递归身份检查、只读
快照、扫描 ID、sensor/modality/frame、双时间戳、source namespace、重复 observation ID
和重复 lineage 检查。因此候选只合并两端完整检查已经覆盖的重复遍历，不删除边界约束。

冻结微基准脚本为 `scripts/run_online_batch_frame_performance.py`。默认负载 200 条量测、
7 次交错采样，预注册门为中位改善至少 `20%`、candidate 更快比例至少 `70%`，且规范帧、
异常摘要和计数守恒全部一致。2026-07-25 结果为
`0.089842 -> 0.050648 s`，改善 `43.625675%`，`7/7` 更快。该历史微基准当时只建议
main 进行显式同提交 A/B，不独立建议改变默认实现；后续默认提升依据上一节 D6 正式证据。

专项字段锁定以 `dataclasses.fields()` 对照 OnlineSensorBatch 的 5 个字段和
SensorMeasurement 的 11 个字段，再逐字段比较深快照。最终帧负例覆盖身份、协方差、双
时间戳、sensor/batch、模态一致性、重复 observation ID 和重复 lineage。异常注入确认
结构检查和快照 `RuntimeError` 均回退完整 reference，`MemoryError` 不回退；专项
`19 passed`，main 复跑 D1 全量 `443 passed in 24.02s`。实现 ID 中的 `closed_immutable` 保留为
稳定追踪标签，不作
raw 来源绝对不可变声明。

### 不透明来源标识缓存

main 在 clean `cd9c60c` 的 source-only profile 中记录
`process_scan_batch/global_tracks/_to_global_track=5.796/1.501/1.314 s`。11,236 次
`_to_global_track` 调用内，成员 token、source track ID 和 source key 分别为
`0.245/0.294/0.337 s`。关闭 source-key/hold 后，
`process_scan_batch/global_tracks=4.852/0.633 s`。该对比说明优化对象是显式来源证据，
不是默认融合主线。

独立构造方式为：

```python
reference = FusionAdapter(
    publish_opaque_source_key=True,
    cached_opaque_source_identity=False,
)
candidate = FusionAdapter(
    publish_opaque_source_key=True,
    cached_opaque_source_identity=True,
    opaque_source_identity_cache_capacity=1024,
)
```

reference ID 为
`d1.publication.opaque_source_identity.per_publication_build.v1`，candidate ID 为
`d1.publication.opaque_source_identity.bounded_generation_lru.v1`。selector 默认
`False`。未开启 source-only 或 hold 时 `_to_global_track()` 不请求缓存，诊断
`request_count=0`。

每次请求先读取当前 publisher node、publisher epoch 和 record track ID。候选仅在三者都是
精确字符串时使用缓存，键保存完整三元组。未命中时调用原有三个规范函数构造全部字符串，
然后把冻结 `_OpaqueSourceIdentity` 写入最近最少使用缓存；命中时只返回该冻结对象。达到
容量时驱逐最早未使用项。节点或 epoch 与当前缓存代际不同会先清空全部旧项。显式 reset
接口用于 main 在复用同一 adapter 的 episode 边界清空缓存。

`_to_global_track()` 的其余步骤不读取缓存。它仍完成：

1. 航迹协方差治理和 A95 计算；
2. 航迹分级与最近 NIS 读取；
3. identity likelihood 归一化；
4. record metadata、source support、association diagnostics 和 covariance operation
   summary 的本轮物化；
5. state 与 covariance 独立复制；
6. 双时间戳、NED、共享审计树和 `global_track_id` 原合同发布。

诊断 schema 为 `d1.opaque_source_identity_cache_diagnostics.v1`。operation counts 始终
返回固定键集合：request、hit、miss、build、eviction、bypass、peak、代际失效和显式 reset。
守恒项验证 request 分解、build 分解、驱逐上界和容量上界。构造函数在执行规范校验前计为
build attempt，因此失败关闭异常也不会破坏计数分解。

聚焦回归逐发布比较完整 JSON 规范载荷，并分别修改已发布 state、covariance、metadata、
source support 和 identity likelihood，确认后续发布不受影响。内部 record metadata、
source support、identity likelihood、association diagnostics 和协方差操作摘要更新后，
候选仍发布新值；只有三字符串保持缓存命中。测试还覆盖 node/epoch 切换、显式 reset、容量
驱逐、OOSM、固定滞后重放、新生航迹和航迹移除。

2026-07-25 微基准显式开启 source-only、关闭 hold。200 条航迹每样本发布 56 次，每轮
11,200 次物化；每臂预热 1 次后交错 7 轮。reference/candidate 中位墙钟为
`0.348622/0.127734 s`，改善 `63.360%`，加速 `2.729x`，candidate `7/7` 更快。
标识构造 `78,800 -> 200`，候选命中/未命中 `78,600/200`。模块预注册门槛
`>=2%` 和 `>=70%` 均通过，D1 全量 `424 passed in 21.81s`。

模块微基准通过后，main 在 clean source commit
`d8fc76c066f21b077154f7be33c0b43558d237e5` 上接入
`per_publication_build_v1/bounded_generation_lru_v1` 选择器。正式运行显式开启
source-only、关闭 structural ambiguity hold，short 10 pair 和 long 3 pair 共生成
26 个 fresh arm，`0 reused/0 failed`。

| 组别 | D1 融合改善 | 核心墙钟改善 | D2 关联耗时增幅 |
| --- | ---: | ---: | ---: |
| short | `9.465972%` | `2.845610%` | `4.677567%` |
| long | `6.437432%` | `2.728043%` | `5.605213%` |

全矩阵标识构造由 `312,317` 次降至 `2,612` 次，构造减少率和缓存命中率均为
`99.163670%`。long D2 关联耗时增幅超过冻结 `5%` 上限，`long_seed_1101` 的增幅为
`19.069868%`。19 个准入门中因此只有 18 个通过。D6 判定
`optimization_admitted=false`，该候选不晋级。

D1 独立构造继续默认 `cached_opaque_source_identity=False`，main 默认继续
`per_publication_build_v1`。`long_seed_1101` 和冻结门限均保留；后续若确认波动，需建立
新的预注册矩阵，不能改写本轮拒绝结论。最低实时因子为 `0.193887`，
`system_realtime_gap_closed=false`。这些结果不外推到默认无 source-key R0、AirSim、
目标硬件、实飞、RMSE、NEES 或 NIS。

### 结构稀疏数值雅可比正式准入

正式 reference/candidate 矩阵绑定 clean commit
`9d1f54f8540fdc4a7a1011121aafac5718290122`。main 在同一实现提交中接入 selector、
运行配置、摘要和最终诊断，D6 使用冻结 manifest 独立评估。矩阵配置如下：

- 200 个目标、200 个资源、2 个侦察节点；
- short 10 pair，每臂 2.2 s；
- long 3 pair，每臂 10 s；
- 共 26 个 fresh arm，`26/26 complete`、`0 reused`、`0 failed`。

13/13 pair 的制品来源、业务语义、有限状态、在线真值隔离、显式实现身份和结构操作数均
通过。short D1 融合改善 `6.084778%`、核心墙钟改善 `1.897370%`，10/10 candidate
更快；long 分别改善 `4.676061%/1.786530%`，3/3 更快。全矩阵量测函数求值减少
`53.846154%`。D6 判定 `availability=true`、`optimization_admitted=true`。
2026-07-25 D1 全量回归为 `414 passed in 21.52s`。

该结果关闭 scalable 3D main 集成候选的准入 P1。D1 独立构造默认仍是
`structured_numerical_jacobian=False`，显式 `True` 可用。main 已把 scalable 3D 的
`IntegratedStackConfig` 与 `run_episode` 命令行默认晋级为
`known_dimension_structural_columns_v1`，`dense_output_probe_v1` 继续作为显式回退。
2v2 默认 smoke 在 observation governance、episode summary 和 module final diagnostics
三个表面均记录候选，状态有限且在线真值使用为 0。

scalable 3D main 默认晋级不改变 D1 独立 `FusionAdapter` 的
`structured_numerical_jacobian=False` 构造默认。最低实时因子为 `0.180726`，因此
`system_realtime_gap_closed=false`。本次评估和 smoke 不含 AirSim、目标硬件、实飞、
RMSE、NEES 或 NIS，不能扩展为相应准入结论。

### 结构稀疏数值雅可比实现

候选入口为：

```python
reference = FusionAdapter(
    structured_numerical_jacobian=False,
)
candidate = FusionAdapter(
    structured_numerical_jacobian=True,
)
```

reference 实现 ID 为
`d1.ekf.numerical_jacobian.dense_output_probe.v1`，candidate 为
`d1.ekf.numerical_jacobian.known_dimension_structural_columns.v1`。这里的默认值
`False` 专指 D1 独立 `FusionAdapter` 构造器；scalable 3D main 集成默认已经选择
candidate。
`measurement_model_for()` 在构造量测模型时同时确定输出维数和结构活动列：

- 四维雷达使用六个状态列；
- 无径向速度雷达使用三个位置列；
- 声学、三维声学、光电和激光雷达使用三个位置列。

候选分配与 reference 同形状的零矩阵，只对活动列执行原中心差分。每个活动列仍创建独立的
正负状态副本，使用相同的相对步长，并按原顺序计算 `(h(xp) - h(xm)) / (2*step)`。输出
维数不再通过一次额外的 `h(x)` 调用探测。若量测函数返回维数与模型声明不一致，候选抛出
异常并由既有扫描关联隔离逻辑处理，不生成伪造代价。

所有 D1 内部量测模型构造点均使用同一 adapter 选择器，包括扫描代价、单观测关联、非量距
修正检查、滤波更新和一致性证据维数读取。`structured_numerical_jacobian_diagnostics()`
记录：

- `jacobian_attempt_count`、`jacobian_success_count`、`jacobian_failure_count`；
- reference/candidate 调用数；
- 输出探测执行或省略数；
- 结构零列省略数；
- 量测函数求值数。

两条守恒式检查 attempt 与 success/failure、reference/candidate 分支数。计数器固定大小，
不进入 `GlobalTrack` metadata，不改变发布摘要。

严格测试使用六类量测模型，并通过扫描级雷达起始、光电/声学/激光雷达更新和乱序量测重放。
reference/candidate 的 `FusionBatchResult.to_dict()`、航迹 ID、状态、协方差、最新量测时刻和
最新到达时刻完全一致。冻结微基准的配置和工作负载 SHA-256 分别为
`711b799b9a36e0d9518574f027f666cb583c355f699202408d45eb083a87166e` 和
`98629f103d3e208bc36cf2b706573197b64c9922e35c74377ef2a3baab7fc470`。中位墙钟
`0.444645 -> 0.319552 s`，改善 `28.13%`，`9/9` 配对更快。该段记录准入前模块微基准；
正式同提交多 seed 结果见上一节。D1 独立默认路径始终未改变。

### 六维协方差 PSD 检查候选

候选构造方式如下：

```python
reference = FusionAdapter()
candidate = FusionAdapter(
    cholesky_covariance_psd_fast_path=True,
)
```

默认值为 `False`。reference 实现 ID 是
`d1.fusion.covariance_psd_check.eigvalsh.v1`，candidate 实现 ID 是
`d1.fusion.covariance_psd_check.cholesky_6x6_relative_determinant_guard_then_eigvalsh.v2`。

`_project_bounded_covariance_to_psd()` 仍先生成独立的对称结果。候选只在矩阵形状为
`(6, 6)` 且全部有限时调用 `np.linalg.cholesky()`。分解成功后计算 Cholesky 对角平方与
原矩阵对角线的归一化行列式比；只有该比值大于 `9.094947017729282e-13` 时才返回结果。
分解失败或安全门拒绝后不修改矩阵，随后进入原 `np.linalg.eigvalsh()` 和完整投影。该门
用于阻止线性代数库在机器精度附近接受实际带极小负特征值的矩阵。非有限输入仍由
`_limit_covariance_diagonal()` 在候选尝试前拒绝。其他维度不执行候选。

`covariance_psd_check_diagnostics()` 使用
`d1.covariance_psd_check_diagnostics.v2`，输出：

- `implementation_id` 和 `candidate_enabled`；
- 固定适用形状 `[6, 6]`；
- `relative_determinant_floor`；
- `cholesky_attempt_count`、`cholesky_success_count`、
  `cholesky_fallback_count`；
- `attempt_equals_success_plus_fallback` 守恒检查。

这些计数使用独立累计器，不进入既有 covariance limit reason 或业务操作数。候选因此不会
仅因实现审计而改变 `GlobalTrack` metadata。测试覆盖随机严格正定、近奇异严格正定、
半正定、不定、非有限、四维旁路、默认值、类型检查和输入非别名。

专项基准脚本为 `scripts/run_covariance_psd_fast_path_performance.py`。固定输入 SHA-256 为
`f26445ee25cd87ec52a993672d9900baba3b41f7999155de35b0c7bd3424a525`；9 次交替采样的
中位墙钟为 `0.558490/0.588263 s`，candidate 慢 `5.33%`，`0/9` 配对更快。cProfile
显示 `eigvalsh` 调用 `20,400 -> 600`，但新增 20,000 次 Cholesky 和安全门判断后，
当前实现没有性能收益。安全门前旧计时已失效。当前处置是保留显式研究对照，不建议 main
接线或默认启用。

### 匀速模型矩阵复用与正式准入

候选保持原匀速预测方程和浮点运算顺序，只把矩阵构造从每次预测移到有界缓存。缓存键为精确
二元组 `(dt, process_noise)`，不做时间量化或容差合并。这样不会把相近但不同的时间差误当成
同一模型。缓存值为写保护的 \(6\times6\) 状态转移矩阵和过程噪声矩阵；预测结果新建状态和
协方差数组，不持有缓存数组别名。

```python
reference = FusionAdapter()
candidate = FusionAdapter(
    cached_cv_motion_model=True,
    cv_motion_model_cache_capacity=128,
)
```

reference ID 为 `d1.fusion.cv_motion_model.per_prediction_build.v1`，candidate ID 为
`d1.fusion.cv_motion_model.bounded_exact_lru.v1`。容量必须在 1 至 4,096 之间。满容量时
淘汰最久未使用的精确键；非有限时间差、非有限过程噪声和非正传播间隔回到原
`predict_to()`。诊断接口 `cv_motion_model_cache_diagnostics()` 返回实现 ID、容量、当前
条目和固定大小操作计数，供 main 绑定正式矩阵。

该候选覆盖 `_predict_all_to()`、检查点状态查询和固定滞后重放中的同一预测入口。它不缓存
航迹状态，不跳过滤波更新，不改变量测时间与到达时间，不减少扫描或发布，也不绕过协方差
正半定治理。过程噪声属性变化后，键中的新值阻止旧矩阵复用。

模块基准执行 20,000 次 200 航迹重复传播。7 次交替采样的中位墙钟由
`0.220679 s` 降为 `0.103950 s`，构造次数由 20,000 次降为 8 次，最终状态摘要完全一致。
延迟乱序量测、结构歧义证据、缓存变异、容量淘汰、非有限绕过和确定性操作数均有测试。
D1 当次全量为 `395 passed in 21.41s`。

正式 A/B 绑定 source commit
`44223566439a446fc49f2a3fd861d1d51bd676b9`，矩阵 SHA-256 为
`9898656598f0fa282620afe2384a3d656b7496f8957109c413bcb62069fd2e9a`。short 使用
10 个 2.2 s pair，long 使用 3 个 10 s pair；每个 pair 的两臂均来自同一提交，场景固定为
200 个目标、200 个资源和 2 个侦察节点。26 个 arm 全部为新运行。

| 组别 | D1 fusion reference | candidate | 逐 pair 改善 | candidate 更快 | 核心墙钟改善 |
| --- | ---: | ---: | ---: | ---: | ---: |
| short | `3.289739 s` | `3.061518 s` | `6.9271%` | `10/10` | `2.4060%` |
| long | `23.304548 s` | `21.776847 s` | `6.6103%` | `3/3` | `2.4537%` |

short 配对原始相对变化的 bootstrap 95% 区间为
`[-7.7968%, -6.0841%]`。D2 association short/long 变化
`-0.1082%/-2.6729%`，RSS 均值增幅 `0.0145%/0.2959%`，任一 pair 最大增幅
`0.8629%`。13/13 的业务语义、有限状态、在线真值隔离、实现身份和缓存审计均通过。

缓存审计累计 896,820 次预测请求。reference 构造 875,031 次模型；candidate 构造
3,535 次、命中 871,496 次，构造减少率与命中率均为 `99.5960%`。D6 判定
`d1_optimization_admitted=true`。

`FusionAdapter` 的默认参数仍为 `cached_cv_motion_model=False`，保证直接调用的兼容性。
main 集成默认已晋级为 `bounded_exact_lru_v1`，同时保留
`per_prediction_build_v1` 对照；scalable 3D 全量 `212 tests` 已通过。候选最低实时因子
`0.1739499`，未达到系统门限 1.0；AirSim、目标硬件、RMSE、NEES、NIS 和系统实时 P1
均未由本次准入关闭。

### GlobalTrack 发布元数据 v2 准入

正式候选 `d1.publication_metadata.immutable_shared_audit.v2` 使用
`d1.publication_audit_tree.v2` 精确不可变合同共享扫描级审计树。D2 先验证合同并执行一次
truth-free 内容审计，再按同一强引用对象身份复用。本轮候选累计 702 次合同验证、702 次内容
审计、139,920 次身份复用和 0 次合同拒绝。

clean source commit `be399e138762f5e660f553c8caa812d52ab38c61` 的 13 对、26 臂矩阵覆盖
short 10 seed 和 long 3 seed。D1 fusion 改善 13.5447%/26.8298%，核心墙钟改善
6.5677%/18.2438%，D2 association 耗时降低 16.1939%/35.6213%，全部准入门通过。main
promotion `f5b350b` 已默认选择 v2；D1 构造器默认仍为 reference。最低实时因子
`0.1730801` 不满足系统实时条件，AirSim、硬件和正式 RMSE/NEES/NIS 也未由本组验证。

### 扫描输入正式准入

正式 A/B 使用 clean commit
`d14285e4fdeb2f2e2cd32fad2f6d42e30f9e73a7`。reference 和 candidate 来自同一提交，
唯一 treatment 是 `d1_scan_input_implementation`；manifest、summary、最终 diagnostics
和 governance 都必须显式报告实际实现。short 为 seeds 1101-1110、2.2 s，long 为
seeds 1101-1103、10 s。

| 组别 | reference -> candidate | 逐 pair 平均改善 | candidate 更快 | 原始相对变化 bootstrap 95% CI |
| --- | ---: | ---: | ---: | ---: |
| short | `1.2124522798461839 -> 1.145650333847152 s` | `5.360121886647966%` | `9/10` | `[-8.208165356448217%, -3.0841406102053194%]` |
| long | `6.687633245543111 -> 6.3406803108907 s` | `5.142481684491682%` | `3/3` | `[-8.837128529506151%, -1.6693612946922343%]` |

13/13 pair 的业务语义、有限状态、在线真值隔离和实现身份全部通过。核心墙钟的 short/long
改善约为 `0.7187%/0.5792%`，RSS 门通过。独立 D6 评估给出
`d1_optimization_admitted=true`，因此 `candidate_v2` 正式准入，扫描输入正式矩阵 P1
关闭。

`system_realtime_gap_closed=false`，候选最低实时因子为
`0.14342687633969603`。该矩阵只覆盖三维质点集成栈，不构成 AirSim、实机、目标硬件、
RMSE/NEES/NIS 或更长时容量结论。

### 扫描输入 A/B 实现

#### 参考边界

`reference_v1` 冻结本任务开始前的算法。对每个帧，它重新派生逐 observation
`source_lineage_key`，递归把每个 NumPy 标量转成 JSON 安全值，分别为 lineage digest 和
lineage 排序生成规范 JSON。计算候选水位线后，它先扫描缓冲得到 remaining 并求观测总数；
通过容量检查后再次扫描得到 ready。事件或 audit 每次需要缓冲观测数时重新遍历当前缓冲。

该路径没有删除，调用方式为：

```python
reference = ScanInputOrganizer(implementation="reference_v1")
```

默认 `candidate_v2` 使用相同 `ScanInputConfig` 和业务 schema：

```python
candidate = ScanInputOrganizer()
assert candidate.execution_config()["implementation"] == "candidate_v2"
```

`execution_config()` 采用 `d1.scan_input.execution_config.v1`；
`performance_diagnostics()` 采用 `d1.scan_input.performance_diagnostics.v2`。后者记录
claim 数、观测数、谱系复用/重建、排序键构造、缓冲分区访问和缓冲观测计数缓存/重扫次数。

#### Claim 单次规范化

帧构造阶段已经按原顺序得到并验证
\(L=(\ell_1,\ldots,\ell_m)\)。candidate 把 \(L\) 存为只读帧字段，并把缓存对象身份和不可变
内容纳入帧完整性封印。缓存被替换时，organizer 从 observations 重建帧。对每个谱系只执行一次：

\[
s_i=\operatorname{JSON}_{canonical}(\ell_i),\qquad
d_i=\operatorname{SHA256}(s_i).
\]

\(s_i\) 既是内容记录与帧记录共同的稳定排序键，也是 \(d_i\) 的原始输入。旧实现为 digest
和排序各生成一次规范 JSON。candidate 没有以 digest 代替排序键，因此保留原 JSON 字典序；
`sort_keys=True`、紧凑分隔符、UTF-8 和 `allow_nan=False` 均不变。

数值 `ndarray` 的 JSON 安全转换满足：

1. 仅对维数大于零且类型为布尔、整数、无符号整数或浮点的数组进入批量路径；
2. 浮点数组先执行完整 `isfinite(...).all()`；
3. 通过后只调用一次 `tolist()`；
4. 对象数组、复数数组和零维数组保留旧递归或失败行为。

因此 NaN 和正负无穷仍抛出同一 `ValueError`，不会产生 claim、发布或缓冲项。

#### 单次缓冲分区

候选水位线仍为：

\[
W=\max(t_m^{new},t_m^{seen})-\Delta t_{late}.
\]

candidate 一次遍历当前缓冲 \(B\)：

\[
B_{ready}=\{b\in B:t_m(b)<W-\epsilon\},\qquad
B_{remain}=B\setminus B_{ready}.
\]

遍历时同步累计 \(B_{remain}\) 的 observation 数。容量检查失败时不修改原缓冲；通过后将
`B_remain` 按原顺序保留，将 `B_ready` 按 `(measurement_timestamp,
received_sequence)` 排序并生成原事件。当前缓冲观测数由 append/release/expiry 同步加减，
事件字段与 audit 读取该缓存。

expiry 没有使用整体分区替换。旧实现逐项移除过期帧后立即生成事件，同一批多个过期事件中的
`current_buffered_*` 逐步下降；一次替换会改变这些字段。普通 Python 数值序列快路也未保留：
相同代码下 cProfile 由约 `1.525 s` 退化到 `1.610 s`。

#### 等价与专项性能

冻结输入文件 SHA-256 为
`5b47f3cf43a9bf78bfca0db249bbefeb709a10c1a7aa6bb4277226fc2144e2d6`，含 570 帧和
10,810 条匿名观测。严格比较范围包括每个 registered claim 的 lineage/content/frame
digest、逐输入全部事件字段、发布顺序和每一步/终态 audit。结果全部相同。

7 轮交错 organizer-only 墙钟如下：

| 指标 | reference | candidate |
| --- | ---: | ---: |
| P50 | 1.078281 s | 0.756634 s |
| P95 | 1.084012 s | 0.766820 s |
| 谱系重建 | 10,810 | 0 |
| 排序键规范化 | 21,620 | 10,810 |
| 缓冲分区 item 访问 | 35,406 | 17,703 |
| 缓冲观测计数重扫 item | 67,876 | 0 |

P50 下降 `29.830%`，加速 `1.425x`。墙钟不参与语义放行。专项覆盖正常、乱序、duplicate、
replay、payload conflict、too-late、缓冲/claim 容量、expiry、非有限数组和谱系缓存篡改；
当前专项 `26 passed in 0.29s`，D1 全量 `361 passed in 20.67s`。

这是 D1 实现与冻结回放专项。后续正式 13-pair scan-input 全栈矩阵已按上节完成；
系统实时、AirSim、RMSE/NEES/NIS、目标硬件和更长时容量状态不变。

### 正式准入方法与结果

正式 v3 使用同一预注册运行配置对标量和向量化路径做配对试验。reference 提交
`a5a472cf81496d94a98db3deb88a3d5c6951f0ce` 将
`vectorized_covariance_limit` 设为 `False`；candidate 提交
`064cbb979d3bab68fee995e476df25709eb666db` 使用向量化路径。两臂共同包含 candidate
基线中的完整正半定修复和 D2 `e4147b8` 误警审计修复，避免把正确性修复计入向量化收益。

short 组使用 seeds 1101-1110、每组 2.2 s，long 组使用 seeds 1101-1103、每组 10 s。
13 组配对形成 26 个三维质点集成 episode；全部正常退出，13/13 跨构建检查证明规范在线
载荷和业务语义一致。正式 manifest SHA-256 为
`40669d10fff8367aa31e24624bab802d8bc3de6b01aaa1e5c92d054753ed93ec`。

| 组别 | reference 融合累计墙钟 | candidate 融合累计墙钟 | 改善 | 更快 seed | 配对原始变化 95% CI | 单次融合 P95 改善 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| short | `4.029165 s` | `3.652252 s` | `9.35462%` | `10/10` | `[-10.914359,-8.113134]%` | `6.652902%` |
| long | `32.954357 s` | `30.768826 s` | `6.631993%` | `3/3` | `[-7.279095,-5.406805]%` | `6.655511%` |

D6 的全部预注册准入门通过，`d1_optimization_admitted=true`。P0 完整正半定输出和 P1
向量化准入均关闭。candidate 最低实时因子只有 `0.143397`，
`system_realtime_gap_closed=false`。该矩阵没有 RMSE、NEES、NIS、AirSim 或目标硬件
证据；它证明 treatment 的语义一致性和本机三维质点性能收益，不证明系统实时性或融合精度。

### 完整正半定治理

#### 故障机理

旧限制器先裁剪对角，再独立限制每个交叉项：

\[
|P_{ij}|\leq 0.999\sqrt{P_{ii}P_{jj}}.
\]

该条件保证每个二阶主子式非负，不保证六阶行列式和其余高阶主子式非负。seed 1103 的固定
失败中，输入 \(P\) 的最小特征值为 \(7.5061\times10^{-4}\)。只修改
\(P_{01}=P_{10}\) 后，最小特征值变为 \(-9.2477\times10^{-4}\)。标量和向量路径在故障前
58,776 次调用上逐元素相同，因此属于共同数学缺口。

#### 当前投影

设治理后的对角为 \(d\)，\(D=\operatorname{diag}(d)\)。pairwise 裁剪后的矩阵若已经
正半定，则原样返回。存在负特征值时执行：

\[
R=D^{-1/2}PD^{-1/2},
\]
\[
\widetilde R=Q\max(\Lambda,\tau I)Q^\mathsf{T},
\]
\[
C=S^{-1/2}\widetilde R S^{-1/2},
\qquad S=\operatorname{diag}(\widetilde R),
\]
\[
C_\beta=\beta C+(1-\beta)I,
\qquad
P_{\mathrm{out}}=D^{1/2}C_\beta D^{1/2}.
\]

特征值 floor \(\tau\) 根据浮点精度、维数和治理对角条件数确定。系数 \(\beta\) 同时限制最大
非对角相关系数并保留正半定；与单位阵的凸组合不会产生负特征值。恢复后的对角精确等于
floor/ceiling 后的 \(d\)。每轮复核有限性、精确对称、对角范围、完整特征值和相关上界，
最多执行 3 次。仍失败时输出 \(\operatorname{diag}(d)\)，避免向 D2 发布不可消费矩阵。

治理 reason 区分 correlation bound、PSD projection 和 diagonal fallback。operation counts
记录对角受限元素数、相关受限 pair 数、投影迭代数、特征值 floor 数和相关收缩数。
`vectorized_covariance_limit` 只控制 pairwise 阶段；两种实现共用投影和审计。

#### 验证

固定 seed 1103 故障矩阵已回归。1 至 6 维每维 96 组随机/极端矩阵、逐对范围内仍非正定的
矩阵和 detached `GlobalTrack` 审计均满足约束。标量/向量化输出、reason 和操作计数严格
相同。双时间戳、opaque 来源谱系、OOSM 和默认 6 s fixed-lag 保持。专项合计
`28 passed`，D1 全量 `352 passed in 20.52s`。

修复后的 seed 1103、200v200、10 s 集成运行处理 10,554 条在线观测并完成，
`finite_state=True`、online truth 0，原 PSD 异常消失。RTF `0.157583` 只说明运行完成；
上节已完成 clean 多 seed 准入；RMSE/NEES/NIS、AirSim、目标硬件和系统实时仍待验收。

### 协方差成对限制向量化

#### 原始路径

状态协方差经过预测、更新或固定滞后重放后，D1 先检查形状和有限性，再执行对称化、对角
floor/ceiling 和非对角相关界限。原实现对 \(n\times n\) 矩阵逐一遍历
\(n(n-1)/2\) 个上三角元素：

\[
\ell_{ij}=0.999\sqrt{\max(P_{ii},0)\max(P_{jj},0)},
\]
\[
P_{ij}\leftarrow\operatorname{clip}(P_{ij},-\ell_{ij},\ell_{ij}),
\qquad P_{ji}\leftarrow P_{ij}.
\]

六维状态每次需要 15 次 Python 循环和 15 次标量 `np.clip`。最新冻结输入中该 helper 共调用
14,868 次，形成约 22.1 万次标量裁剪。调用图同时证明，这些外层限制不能直接删除：
10,832 次发生在预测改变协方差之后，1,789 次发生在更新后重放，202 次发生在航迹新生。

#### 当前实现

新路径只提取严格上三角索引，并从已裁剪对角线构造对应的限幅向量：

\[
L_{ij}=0.999\sqrt{d_i d_j},\quad i<j,\qquad
d_i=\max(P_{ii},0),
\]

再对上三角向量执行一次 `clip`，把结果镜像到下三角。1 至 6 维严格上三角索引在模块加载
时构造并设为不可写；缓存内容只描述矩阵拓扑，不包含状态、协方差或校验结果。输入仍先执行
与旧路径相同的对称化。

`Scalable3DFusionAdapter(vectorized_covariance_limit=False)` 保留旧标量 reference；
`True` 是验证后的默认优化路径。A/B 开关同时用于状态和正式观测 covariance 限制，但不改变
观测入口的有限、维度、对称和半正定校验。非法状态 covariance 仍重置到既有 ceiling
diagonal 并记录 `track_covariance_invalid_reset`；floor/ceiling reason 的判断和顺序不变。

#### 语义与性能验收

seed 1100 冻结输入含 89 个扫描、2,035 条匿名观测，SHA-256 为
`54bed9d7f03497967c3f8478a9e0cf1385e85bcc512bf769df849b7b1ab3e0ec`。基准复用同一
扫描释放分组和同一 state-only/full materialization 调度，先预热一对，再按
reference/optimized、optimized/reference 交替运行 5 轮。

| 指标 | 标量路径 | 向量路径 |
| --- | ---: | ---: |
| 纯融合均值 | 3.001196 s | 2.610975 s |
| P50 | 3.011440 s | 2.614061 s |
| P95 | 3.023308 s | 2.660813 s |
| limiter cProfile 累计 | 1.047145 s | 0.426826 s |
| `_predict_all_to` cProfile 累计 | 1.098530 s | 0.584526 s |

每轮逐扫描后验和物化结果均严格一致。比较范围包括六维状态、`6x6` covariance、
`measurement_timestamp`、`arrival_timestamp`、来源谱系、质量分级、终态
`GlobalTrack`、一致性证据、批操作计数、累计诊断和物化调度。在线 truth 使用为 0。

长夹具通过 `compare_covariance_limit_semantics_once()` 只执行一对，不预热、不重复、不做
cProfile，也不设置性能门。seed 1000 的 771 扫描、11,889 观测输入覆盖 4,009 次
fixed-lag rebase 和 11,888 条 OOSM。两臂的逐扫描摘要、延迟审计、操作计数、终态
`GlobalTrack` 和一致性证据严格一致。

边界测试覆盖正常矩阵、对角上下界、负/零对角、极大相关项、非有限状态上层重置、非对称
状态、有限非正定状态及在线非法观测 covariance。专项 `18 passed`，D1 全量
`342 passed in 19.73s`。该证据是正式 v3 之前的冻结三维质点基线；上节已关闭 clean
full-stack 多 seed 准入。AirSim、目标硬件、实时预算和 RMSE/NEES/NIS 仍未关闭。

### A2 原子 shadow 系统复核

main 在 clean commit
`7cc2d0cfd598a72d60c6ba8c7d4a283f4e5a897d` 上完成 seed 1100、200v200、2.2 s、
`recon_count=2` 的 control/atomic-shadow 成对运行。control/shadow 墙钟为
`10.735151270986535/19.449935468961485 s`，开销比 `0.8117989190825889`；实时倍率为
`0.20493423375838704/0.1131109151241553`。shadow 的 9 次发布包含 46 条决策，全部以
`oosm_scan` 拒绝，没有 accepted treatment 或 evaluation error。

9/9 次原子调用的 post-integrity 均通过，没有 atomic failure 或 materialized shadow。
单次审计总时延 P50/P95/max 为 `1024.838/1536.429/1549.436 ms`。阶段均值为：

- 禁止写入前完整摘要：`254.599 ms`；
- 原子 overlay 调用：`544.960 ms`；
- 禁止写入后完整摘要：`196.413 ms`；
- shadow payload 摘要和日志物化：约 `0.0003/0.099 ms`。

旧 prepared-handle 路径在没有 accepted decision 时直接返回规范输入，不进入 detached
assemble。因此，本场景中原子入口没有消除第二次装配边界完整性检查；旧路径的
prepare/evaluate 均值合计约 `540.516 ms`，与本轮 atomic operation 的 `544.960 ms` 接近。
前后完整摘要仍需遍历完整规范航迹和证据表面。原子接口解决了调用边界和失败关闭问题，没有
解决本轮主要性能开销。

D1/D2/D3 终态在两臂均为 `202/201/186`，在线 truth、禁止写入、D2/D3 shadow 消费和
`global_track_id` 变化均为 0。安全隔离与业务非干预子门闭合；`+5%` 性能门失败，且没有
有效 treatment 可评价。A2 不准入，不启动 A3/A4 或 seeds 1101/1102。

### A1 原子 publication overlay

新增入口
`run_experimental_centroid_publication_overlay_atomically()`，只用于默认关闭的离线实验和
审计 shadow。它把原来由调用方分三步完成的准备、判断和装配收进一次同步调用：

```text
完整规范航迹
  -> prepare：校验并描述全部航迹
  -> evaluate：使用内部描述符生成 decision
  -> accepted 时装配 detached shadow；rejected 时跳过装配
  -> 对原规范航迹执行一次完整 post-integrity verify
  -> 通过后返回冻结结果；失败时丢弃 shadow 并撤销状态推进
```

内部 prepared handle 不返回给调用方。公开的准备信息是冻结摘要，只含规范发布摘要、验证状态、
航迹数和准备工作量。evaluation 也不携带内部 prepared handle。结果同时给出规范发布摘要、
shadow 发布摘要及是否物化、后置完整性检查和分阶段工作量，便于 main 不依赖墙钟推断实际
遍历次数。结果 `to_dict()` 只包含标准 JSON 可表示值，`canonical_bytes()` 给出确定性编码。
规范和 shadow 发布摘要均由按成员键排序的完整航迹摘要清单生成，比较结果具有相同语义。

正常 200 航迹 accepted 路径执行 1 次 `_describe_tracks`。该次描述包含类型、唯一
`global_track_id`、NED、有限性、协方差对称半正定、禁止身份字段，以及 state/covariance、
metadata、lineage/source support、identity、`last_nis`、时间戳和分级的完整规范摘要。
decision 和 detached 装配只读复用描述符。装配结束后，对同一规范对象执行 1 次完整内容复核，
共 200 条后置摘要。shadow 发布摘要单独读取 detached 副本，不计为规范对象的第二次复核。
rejected 路径不调用装配 helper，shadow 复制数、shadow 航迹摘要数和发布摘要数均为 0。

后置复核发现对象重绑定或内容变化时，返回结果不含 shadow。provisional decision 被替换为
`prepared_canonical_publication_mismatch` 拒绝，`next_state` 恢复为输入状态。该边界覆盖
数组原地变化、嵌套 metadata 修改、source support、identity、`last_nis`、全局编号、时间戳
和分级变化。接受装配仍使用递归值语义复制，保持 ID、速度、成员相对位置、完整 metadata 和
协方差不收缩，并支持嵌套只读 Mapping、tuple、frozenset 与 NumPy 值。

公共 prepare/evaluate/assemble API 没有放宽。显式 prepared handle 仍在每次公共复用边界
执行完整内容强校验；原子入口只消除单次内部流水线中的重复复核。

2026-07-24 聚焦测试 `36 passed`，D1 全量
`324 passed`。2/3/5 成员 canonical decision bytes 与 `de73cb2` 基线一致。
200 航迹夹具报告 1 次完整描述、200 条描述摘要、1 次后置完整性复核、200 条规范复核摘要、
200 条 detached shadow 摘要。该结果证明 D1 模块实现；main 已按上节完成 clean 原子
shadow 成对复核。安全子门闭合，但 A2 性能门与有效 treatment 门仍失败，A3/A4 及 seeds
1101/1102 继续停止。

### A1 规范发布准备与安全复制

原型新增三步实验调用方式：

```python
prepared = prepare_experimental_centroid_canonical_publication(canonical_tracks)
evaluation = evaluate_experimental_centroid_publication_overlays(
    canonical_tracks,
    evidence_items,
    prepared_publication=prepared,
)
shadow_tracks = assemble_experimental_centroid_shadow_tracks(
    canonical_tracks,
    evaluation,
    prepared_publication=prepared,
)
```

第一步遍历完整规范航迹，校验 NED、有限性、协方差对称半正定、禁止身份字段和唯一
`global_track_id`，并计算每条航迹完整载荷摘要、状态摘要、协方差摘要及发布摘要。完整载荷
包括 metadata、lineage、source support、identity、时间戳和质量字段。准备对象以
`ExperimentalCentroidCanonicalPreparationWork` 记录完整描述轮次和各类摘要工作量。后两步
只读复用描述符。每个复用边界使用 `ExperimentalCentroidCanonicalIntegrityCheck` 核对对象
绑定，并对每条航迹的同一完整规范载荷重算 SHA-256。显式对象与输入序列、成员对象或载荷
内容不一致时，evaluation 生成 `prepared_canonical_publication_mismatch` 拒绝；assembly
返回原规范序列。

准备对象采用冻结、带 slots 的数据结构。其私有描述符只包含索引、标识、时间和摘要，不持有
可变 `GlobalTrack`、metadata 或 NumPy 数组。旧 API 保持兼容；未显式传入准备对象时，
evaluation 内部准备一次并供同一输入的后续 assembly 复用。不同但值相同的序列仍走旧 API
的完整重验路径，避免把对象绑定优化变成跨快照信任。

正常显式 prepare -> evaluate -> assemble 只调用一次 `_describe_tracks`。evaluate 和
assemble 各进行一次完整载荷摘要复核；复核遍历 metadata，但不重复 NED/协方差特征值/
身份字段校验、状态和协方差独立摘要及发布级排序摘要。200 航迹的确定性工作量为 1 次完整
描述、2 次内容摘要复核和 400 条复核航迹摘要。

接受路径不再调用会拒绝 `MappingProxyType` 的通用 `deepcopy`。递归复制按值处理任意
`Mapping`、列表、元组、集合、不可变集合、NumPy 数组和 NumPy 标量，其他受支持标量再使用
常规深拷贝。只读映射在 shadow DTO 中脱离为普通字典，嵌套 tuple/frozenset 和 NumPy 类型
保持值语义；完整 metadata 不丢失、不降级为字符串。

2026-07-23 聚焦测试 `21 passed`，D1 全量 `308 passed in 19.69s`。2/3/5 成员决策哈希与
提交 `de73cb2` 基线一致。200 航迹嵌套只读 metadata 固定夹具在 prepare/evaluate/assemble
全链路只触发一次 `_describe_tracks`，并实际形成 accepted shadow。数组、嵌套 metadata、
covariance、source support、identity、全局编号、时间戳和分级修改均阻断复用。该工作量断言
不依赖机器墙钟。

main 提交 `2b976a7` 已把上述三步接口接入默认关闭审计 shadow。seed 1100、200v200、2.2 s、
`recon_count=2` 共执行 9 次 evaluation，9/9 次记录显式准备对象和内容完整性匹配。46 条
evidence 均因 `oosm_scan` 被拒绝，assembly 直接返回原序列，因此装配均值只有
`0.00247 ms`。过滤专属审计记录并按既有跨构建规则归一化计划编号和总线序号后，
3294/3294 条业务记录逐条一致；禁止写入审计、错误、D2/D3 消费和在线 truth 使用均为 0。

当前开销主要来自完整安全审计和准备/复核：before digest、prepare、evaluate、after digest
均值为 `224.461/345.095/195.421/207.312 ms`。shadow 总 P95 `1532.999 ms`，
control/shadow 墙钟 `10.712171729/19.376483415 s`，增加 `80.8829%`；RTF
`0.205374/0.113540`。最大载荷 `11,275,939 bytes`，水位 `8/1024`。安全接口接入成立，
性能门失败；0 accepted 也使 treatment 有效性门失败。两组 manifest 均为 dirty 开发口径。
A2 不准入，不进入 A3/A4，也不运行 seeds 1101/1102。

### 结构歧义 A1 publication overlay 原型

`STRUCTURAL_AMBIGUITY_NEXT_CANDIDATE_DESIGN_CN.md` 已比较三个后续方向。提交 `de73cb2`
已实现 A1，状态为 `IMPLEMENTED_UNIT_TESTED_OFFLINE_PROTOTYPE`。A1 把共同质心修正限制为
detached publication overlay：

\[
x_i^{pub}=x_i^c+[\delta p,0]^\mathsf{T},
\qquad
P_i^{pub}=P_i^c+\operatorname{diag}(\Delta P_{pos},0),
\]

其中 \((x_i^c,P_i^c)\) 是只读规范滤波快照。拒绝时 overlay 为空，发布器直接使用规范快照，
不调用 replay/replace，并以业务发布 bitwise 等同 control 为首要验收。A 不写 state、
history、checkpoint、cache、lineage、source support 或 `global_track_id`。

实现入口为
`evaluate_experimental_centroid_publication_overlays()` 和
`assemble_experimental_centroid_shadow_tracks()`。前者读取规范 `GlobalTrack` 快照与
`StructuralAmbiguityEvidence`，返回不可变 decision/member overlays 和新的有界 generation
状态；后者只在 accepted 且全部基准摘要复核通过后复制发布 DTO。拒绝、无 accepted decision
或任一装配校验失败时，直接返回传入的规范业务序列对象，不重建状态。接受时只增加统一 NED
位置平移和 PSD 位置协方差增量，速度、相对位置、双时间戳、`global_track_id`、
lineage/source support、identity、质量和 metadata 不变。

原型使用完整组件键、UTF-8 排序、canonical JSON 和 SHA-256 生成确定性摘要及 `decision_id`；
重复/倒退 generation、同代摘要冲突、重叠组件、容量满、OOSM/stale、结构门失败、身份字段和
非有限输入均 fail closed。成员数量来自输入，不写死 2x2；仅平衡满基数纯交替环可接受，并
继续固定 `cross_covariance_available=false`。

B 路线把共同质心放入 fixed-lag measurement-time 历史。当前
\(Q(h)=G(h)qG(h)^\mathsf{T}\) 一般不满足
\(Q(h_1+h_2)=F(h_2)Q(h_1)F(h_2)^\mathsf{T}+Q(h_2)\)，所以插入零更新事件也会改变协方差
分段。事件排序、过程噪声分段和一致性 oracle 未冻结前，B 不进入在线实现。C 路线保持 D1
只发布 evidence，由 D2 后续规划概率或多假设消费；无交叉协方差时不得把成员边缘量当作独立
状态量测。

2026-07-23 A1 基线聚焦测试 `7 passed`，覆盖 2/3/5 成员接受、拒绝透传、成员/观测/边/组件排列
byte-identical、generation 幂等/倒退/摘要冲突、冲突组件、容量和输入不变；D1 全量
当时为 `294 passed`。该结果只证明 A1 离线纯函数原型，不代表 A2 shadow、在线/AirSim 接线、P95、
系统效果或晋级。A1 没有接入 `FusionAdapter.process()`/`process_scan_batch()`，没有修改
`fusion.py` 或新增 D1 默认运行开关；experimental decision schema 不是当前在线 schema。
main 已用独立、默认关闭的审计 shadow 完成 A2 接线，但性能门和有效 treatment 门未通过。
A3/A4 未实现，seeds 1101/1102 继续停止。

### 结构歧义证据侧车实验候选 v3

#### 配置与作用域

候选策略版本为
`prediction_only_maximum_matching_component_evidence_v3`，证据 schema 为
`d1.structural-ambiguity-evidence.v1`。严格布尔参数
`radar_assignment_ambiguity_hold_evidence=False` 默认关闭，并与 v1/v2 互斥。默认关闭时不
构造侧车，不改变原更新或 birth，`FusionBatchResult.to_dict()` 和
`FusionStateUpdateResult.to_dict()` 也不增加空 evidence 字段。

显式启用后，关联器使用 v2 已验证的最大匹配允许边分解。分量包含交替环、free-row 路径或
free-column 路径时，从本扫描 `assignments` 中移除分量列，但不沿用 v1/v2 suppression
干预：

```text
member track:
  prediction to measurement/arrival time
  no hit increment
  no observation append
  no measurement posterior
  no covariance contraction

component observation:
  no observation-to-member identity commit
  no member source-lineage append
  no immediate track birth

output:
  original track snapshot + StructuralAmbiguityEvidence sidecar
```

唯一匹配和完全门外的独立 observation 不进入侧车，继续执行原 update/birth。首扫没有既有
track，不形成歧义分量，仍按原规则初始化。

#### 发布者和成员键

侧车必须能与 D2 收到的 D1 track snapshot 一一对应，同时不能把 D1 本地编号冒充规范身份。
构造规则为：

```text
opaque_member_track_token =
  "d1-track-sha256:" +
  SHA256(canonical_json([
    publisher_node_id,
    publisher_epoch,
    d1_local_track_id
  ]))

source_track_id =
  publisher_epoch + "::" + opaque_member_track_token

source_key =
  publisher_node_id + "::" + source_track_id
```

默认值为 `D1_FUSION` 和 `d1-default-epoch-v1`。两者均经过严格标识符校验。默认 epoch 稳定且
显式，不能从 observation、target、actor 或 truth 名称推导；正式 episode 应由 main 配置
实际 epoch。启用候选时，`GlobalTrack.metadata` 同时发布
`source_node_id/source_track_id/publisher_epoch/opaque_member_track_token/source_key`。
D1 本地 `global_track_###` 只在哈希函数内部使用，不进入侧车，也不成为 D2 canonical
`global_track_id`。

#### 独立来源键控制臂

构造参数 `publish_opaque_source_key: bool = False` 只控制发布元数据。有效发布条件为：

```text
opaque_source_key_publication_enabled =
  radar_assignment_ambiguity_hold_evidence
  or publish_opaque_source_key
```

四种组合语义如下：

| hold | publish source key | 发布五个来源字段 | 结构歧义干预 |
| --- | --- | --- | --- |
| `False` | `False` | 否 | 无 |
| `False` | `True` | 是 | 无 |
| `True` | `False` | 是，保持原合同 | prediction-only + evidence |
| `True` | `True` | 是，保持原合同 | prediction-only + evidence |

source-only 分支只在 `_to_global_track()` 物化发布快照时写入字段。扫描关联、歧义分量检测、
滤波更新、协方差传播、hit/miss/birth、lineage、固定窗重放和 OOSM 治理均不读取该开关。
`association_audit_summary()` 增加 requested、enabled、mode、publisher node 和 epoch；
mode 为 `disabled`、`source_only` 或 `structural_ambiguity_hold`。原
`structural_ambiguity_publisher_*` 字段仍只描述 hold，不被 source-only 复用。

#### 身份中性共同质心修正

默认关闭参数为：

```text
radar_assignment_ambiguity_neutral_centroid_correction = False
```

候选要求 hold 已启用，并拒绝在线 truth hint 模式。它只接受平衡满基数、无自由行列、纯
交替环、同 radar sensor/scan/双时间戳/NED、未过期、非 OOSM、无重复/冲突来源、规模不超过
`K_max` 的分量。原始观测或成员元数据含 truth、actor、target identity 或 offline label 时，
候选 fail closed。

设成员预测位置和观测位置分别为 \(p_i^-\) 与 \(z_j\)，成员数为 \(m\)：

\[
\bar p^-=\frac{1}{m}\sum_i p_i^-,
\qquad
\bar z=\frac{1}{m}\sum_j z_j,
\qquad
r_c=\bar z-\bar p^-.
\]

成员和观测质心边缘协方差相加得到 \(\Sigma_c\)。候选要求
\(r_c^\mathsf{T}(\Sigma_c+q_{\min}I)^{-1}r_c\leq\gamma_c\)。集合形状使用去质心二阶矩：

\[
C_p=\frac{1}{m}\sum_i(p_i^--\bar p^-)(p_i^--\bar p^-)^\mathsf{T},
\qquad
C_z=\frac{1}{m}\sum_j(z_j-\bar z)(z_j-\bar z)^\mathsf{T}.
\]

只有 \(\lVert C_z-C_p\rVert_F\leq\tau_{\text{shape}}\) 时才构造修正。对全部成员施加相同
向量范数截断平移：

\[
p_i^+=p_i^-+\alpha\,\operatorname{clip}_{\lVert\cdot\rVert}(r_c,r_{\max}),
\qquad
v_i^+=v_i^-.
\]

同一平移使任意成员间相对位置保持不变，也不使用雷达量测中的未观测径向速度占位值。候选不
读取候选边排序来决定成员归属，不发布 observation-to-member 边。

每个成员只在位置边缘增加：

\[
\Delta P_{\mathrm{pos}}
=\alpha^2\Sigma_c+
\left(
\lambda_{\mathrm{shape}}\lVert C_z-C_p\rVert_F+q_{\min}
\right)I_3.
\]

实现先计算整个分量的候选状态，再逐成员检查有限性、对称半正定、协方差上限、
\(P_i^+-P_i^-\succeq0\) 和质量分级不变。任一失败时不修改任何成员。成功时不增加 hit，不
追加观测、lineage 或 source support，不刷新身份 freshness，不新建/删除航迹，也不改
`global_track_id`。成员间共同平移会引入相关误差，当前实现只提供边缘协方差，继续标记
`cross_covariance_available=false`。

实验默认参数为 `K_max=8`、`alpha=0.5`、`r_max=30 m`、质心门限
`16.26623619623813`、形状门限 `2500 m^2`、形状膨胀系数 `0.05` 和
`q_min=0.25 m^2`。generation 水位表默认容量为 1024，可配置范围为 1 至 1,000,000。这些是
候选默认值，不是实测标定。参数均严格拒绝布尔冒充整数/实数、字符串数值、非有限值和越界值；
可配置 `K_max` 范围为 2 至 256。

状态修正采用帧替换语义。证据中的成员状态仍在 `measurement_timestamp` 有效；新 generation
通过代际准入后，融合器从正式观测历史精确重放到当前 `published_at`，得到
\(x_{i,k}^{\mathrm{base}},P_{i,k}^{\mathrm{base}}\)。本帧发布后验为：

\[
x_{i,k}^{\mathrm{pub}}
=x_{i,k}^{\mathrm{base}}+
\begin{bmatrix}\Delta p_k\\0\end{bmatrix},
\qquad
P_{i,k}^{\mathrm{pub}}
=P_{i,k}^{\mathrm{base}}+
\begin{bmatrix}\Delta P_{\mathrm{pos},k}&0\\0&0\end{bmatrix}.
\]

上一 generation 的临时修正不写入观测历史或重放检查点，因此不会进入
\(x_{i,k}^{\mathrm{base}}\)。新 generation 校验失败时直接发布该帧基线。相同代或倒退代属于
重放请求，拒绝时保持当前状态不动，避免同一帧重放撤销已发布修正。`_predict_all_to()` 在新
证据到来前按运动模型传播当前临时修正；正常身份明确观测接受后，`_finalize_record_replay()`
从正式观测历史重建后验，临时修正被正常量测替代，不产生额外 hit、lineage 或 source support。

幂等状态不再保存所有 `(component_id, generation)`。每个 `component_id` 只保存最大已见代、
最大已应用代和最近量测时刻。相同代拒绝为 `duplicate_evidence_generation`，较小代拒绝为
`regressed_evidence_generation`。只有最近量测时刻严格早于
`current_time-buffer_horizon` 的条目可以淘汰；对应旧证据同时拒绝为
`evidence_outside_fixed_lag`，清理不会使有效期内旧代重新生效。容量已满且没有过期条目时，
新组件拒绝为 `generation_registry_capacity_reached`。

候选显式启用时，审计记录候选、成功、拒绝、成员、重复/倒退 generation、水位表当前/峰值
条目、淘汰、容量拒绝、线性输入操作数、最大分量规模、质心 NIS、形状差、平移和拒绝原因；
默认关闭时不增加这些字段。共同质心计算只堆叠当前分量的成员与观测，额外状态计算随 \(m+n\)
增长，不构造新的全局两两矩阵。

#### DTO 结构与校验

`StructuralAmbiguityEvidence` 至少包含：

- `evidence_id/component_id/component_generation`；
- 发布者 node/epoch、member-token/source-key 构造规则；
- measurement/arrival/state-valid/published 四类时间；
- sensor/scan、`frame_id=NED`；
- member `6` 维状态、`6x6` 协方差及 source key；
- observation NED 三维位置、`3x3` 协方差、径向速度是否真实观测、是否延迟 birth；
- candidate edge 的 member token、observation key、NIS、门限和逐边角色；
- component kinds、成员/观测/边计数、free-row/free-column 数和最大匹配基数；
- 固定 prediction-only、deferred-birth、complete 和 cross-covariance 状态。

`from_dict()` 要求键集合精确，拒绝额外 truth/actor/target identity 字段。数组必须有限、shape
正确，协方差必须对称半正定；candidate NIS 必须有限、非负且不超过门限。成员、观测、边按
opaque key 排序，输入行列排列不影响最终侧车。`evidence_id` 还包含 generation、四类时刻、
scan 和有序边内容；同一来源分量跨扫描以 `component_generation` 递增。

观测 key 不调用通用 `source_lineage_key`。后者服务于全模块重复投递治理，在合成数据缺少
payload id 时可能包含离线标签指纹，不适合作为该候选的规范排序输入。当前 observation key
只哈希 sensor/modality/frame、measurement/arrival timestamp、雷达转换后的 NED 位置、
`3x3` 协方差、径向速度是否真实观测和同内容 occurrence。该信息全部来自在线量测合同。
测试会改变 observation id 及 truth/actor/D6 metadata，并要求完整 evidence 不变。

`cross_covariance_available=false` 是约束，不是缺省说明。侧车只提供各成员边缘协方差，没有
成员间交叉协方差；D2 不得把这些成员当成统计独立量测进行协方差融合。

#### 分量、边和 birth 计数

`component_kinds` 是分量并集。`candidate_edges[*].edge_roles` 只记录该边实际角色：

```text
reference matched edge:
  maximum_matching_allowed
  matched_reference

unmatched allowed edge:
  maximum_matching_allowed
  + alternating_cycle and/or
    free_row_alternating_path and/or
    free_column_alternating_path
```

参考匹配边不继承替代边的 cycle/free-row/free-column 标签。该分离允许 D2 重建“本次参考匹配”
与“可替代边”，避免把整个 component kinds 误读为每条边都满足全部结构。

分量级 `birth_disposition=deferred_component_birth` 表明 free-column birth 被该策略接管。
逐观测 `birth_deferred` 只对参考最大匹配中未匹配的列为真。因此：

- `2x2` 平衡 cycle：0 个 deferred birth；
- `3x2` free-row：0 个 deferred birth；
- `2x3` free-column：1 个 deferred birth。

`structural_ambiguity_deferred_birth_count` 对逐观测布尔值求和，不使用分量 observation_count。
旧 `radar_assignment_ambiguity_observation_suppression_count` 和 track-coast 计数不冒充新
策略结果。新计数分别记录 evidence component、observation、member、deferred birth 和
prediction-only member。

#### 模块验证与限制

结构歧义基础阶段专项 `25 passed`，覆盖 `2x2`、`3x2`、`2x3`、唯一匹配、首扫、门外独立 birth、输入排列
不变、lineage 不污染、truth 字段拒绝、observation 名称及离线 identity metadata 不变、
未观测零径向速度不更新、默认关闭兼容、两种结果 DTO、roundtrip 和 covariance shape/半正定
拒绝；新增 source-only 只增发布字段、稳定序列化、非法参数和 OOSM 重放不变检查。D1 全量
当时为 `245 passed in 17.48s`，`py_compile` 通过。

共同质心候选修复后，结构歧义专项为 `62 passed`，D1 全量为
`282 passed in 17.81s`。新增断言覆盖共同平移、相对位置和速度不变、hit/lineage/source
support/质量分级不变、协方差半正定且不收缩、自由行列和混合分量拒绝、过期/OOSM/重复/
冲突拒绝、连续三代不累加、失败新代恢复 prediction-only、正常明确量测替代临时修正、重复/
倒退 generation 幂等、24 代单组件存储边界、固定滞后淘汰和容量 fail-closed、在线身份字段
拒绝、默认关闭等价、`K_max` 和线性操作计数。修复前专项复现中，固定 30 m 质心创新和
`alpha=0.5` 使首帧偏移约 15 m、第二帧错误累加到约 30 m；修复后三帧均保持单帧偏移。
该结果尚未包含 main、AirSim 或多 seed 系统试验，只证明 D1 模块语义。

模块测试本身没有运行系统 episode。D2 有界保活消费者和 main 最终 A/B 已在固定提交
`ff88131` 接入：`nominal_200v200`、seed 1100、2.2 s、`recon_count=2` 的候选产生并一次
消费 46 个 evidence。D2 航迹 `203 -> 201`、D3 分配 `200 -> 197`，strict ID switch
`9 -> 3`，track/coverage continuity `.865/.870 -> .826667/.828333`，
available/partial-unavailable mappings `1566/234 -> 1491/296`，实时倍率
`.220352 -> .207642`。

冻结在线记录的 89 个 D1 发布批次已逐批重放。76 次参考匹配更新被跳过，其中离线真值判断
69 次正确、7 次错误；另有一个真实目标新生延迟 0.2 s。13 条可可靠连接真值的既有歧义成员
平均位置误差从 25.217 m 增至 34.184 m，位置协方差迹中位数约为基线 2.93 倍。协方差增长
保持保守，但整分量不更新损失了过多正确运动信息。

预注册门槛要求身份改善和下游可用性同时成立。本候选未通过，停止 seeds 1101/1102，并保持
默认关闭。D1 算法和 DTO 实现继续保留为实验能力。

main 后续 seed 1100 三臂结果为：baseline/source-only/hold 的 D1/D2/D3 分别是
`202/203/200`、`202/201/198`、`202/201/186`，IDSW 为 `9/7/3`，track continuity 为
`.865/.865/.826667`，coverage continuity 为 `.870/.868889/.828333`。hold 端 76 条未承诺
记录使 D3 拒绝 11 个目标，未承诺绑定违规为 0；source-only 终态映射 200 个真实目标并有
1 条未映射航迹，hold 为 191 个和 10 条。该闭环在首个计划后传感器流随控制分叉，只能解释
系统效果，不能替代完全冻结输入的上游因果比较。

main 先在未提交工作树接入共同质心开关并取得 dirty 诊断，随后在固定提交
`7e15dac9cdaf6743999dfe045a70676fd31a17d6` 运行 seed 1100 clean 同输入复跑。hold-only
与 hold+共同质心均为 `repository_dirty=false`、200v200、2.2 s、`recon_count=2`，
配置哈希 `20ef5248...b840`。两臂场景和离线真值相同，89 批传感器主题规范化 SHA-256
均为 `bc064834...51518`，D2 在线记录 SHA-256 均为 `da7089fa...f8d2f`。

两臂 D1/D2/D3 都是 `202/201/186`，strict IDSW 都是 3，track/coverage continuity 都是
`0.8266666667/0.8283333333`。可用/不可用/未承诺映射均为 `1491/218/76`，身份承诺覆盖率
均为 `0.9574706212`；重复分配、在线 truth 使用、未承诺来源绑定违规和未承诺候选绑定违规
均为 0。D3 门拒绝 11 个目标；main 在一次 hold 事件中累计撤回或清除 13 条运行时绑定，
两者统计口径不同。candidate 共检查 46 个组件，实际施加 0 个，拒绝原因为
`oosm_scan=30`、`unbalanced_component=16`。generation 水位表当前/峰值为
`8/8`，淘汰和容量拒绝为 0。

该结果只表明当前线上门控对本场景全部 fail closed。新的 D3 安全门关闭了未承诺目标下游
执行违规，但没有实际质心状态处理，不能据两臂相同推断算法有效。早期
`/tmp/MSM-neutral-centroid-gate-20260723` dirty 结果保留为开发诊断；当前 clean 制品位于
`/tmp/MSM-identity-gate-results-7e15dac/{hold_only,hold_plus_centroid}`。按开发停止条件
不再运行 seeds 1101/1102。

#### 冻结扫描边界诊断

边界诊断由
`structural_ambiguity_replay_diagnostic.py` 提供可复用 API，由
`scripts/run_structural_ambiguity_replay_diagnostic.py` 生成 JSON 和中文 Markdown。它没有
复制滤波器或扫描组织逻辑，数据路径为：

```text
确定性 SensorObservation
  -> serialize_governed_replay
  -> governed replay 回读
  -> SensorScanFrame
  -> ScanInputOrganizer
  -> FusionAdapter.process_scan_batch
  -> 控制臂/共同质心候选臂比较
```

两臂的冻结帧签名只由 `scan_id`、`measurement_timestamp`、`arrival_timestamp` 和观测数
组成，避免把候选臂专属审计计数误判为输入差异。三类输入结果如下：

| 输入 | 结构记录 | 处理结果 |
| --- | --- | --- |
| 同步平衡纯交替环 | 成员/观测 `2/2`，free row/column `0/0` | 施加 1 次共同平移，模长 `15.000000 m` |
| 乱序平衡纯交替环 | 量测/到达 `0.300/0.650 s`，融合前时刻 `0.400 s` | `oosm_scan`，施加 0 |
| 数量不平衡分量 | 成员/观测 `2/1`，最大匹配基数 1，free row/column `1/0` | `unbalanced_component`，施加 0 |

同步场景的共同平移约为 `[15.000000, 0.000000, 0.003278] m`。速度、成员相对位置、hit、
lineage、source support、identity likelihood、质量分级和 `global_track_id` 均保持不变；
候选相对控制臂的协方差差最小特征值为 `0.4797678`。乱序场景由扫描组织器记录 1 次重排，
但不会删除双时间戳或绕过 OOSM 资格门。

乱序和数量不平衡场景分别以 `oosm_scan`、`unbalanced_component` 拒绝，均为
`applied_component_count=0`，且共同质心公式没有生成平移或协方差膨胀，因此共同质心
correction 未施加。候选臂仍在拒绝后各执行一次 publication-base replay + replace，以清除
旧临时修正。控制臂的分段预测与候选臂的单段历史重放使用当前非半群等价的离散 CV 过程噪声，
使候选减控制协方差差最小特征值分别为 `-0.0071928353214153066` 和
`-0.004617076466238031`。逐元素审计确认差值与 replacement 前后差值 bitwise 一致；这只是
拒绝路径的发布态重放替换诊断，不能声称对状态和协方差严格无副作用。协方差不收缩只验收实际
施加的同步场景，两个拒绝场景均为 `candidate_not_promoted`。

专项 `5 passed`，D1 全量 `287 passed in 18.03s`。输出位于
`../reports/structural_ambiguity_centroid_replay_20260723/`。该诊断只证明受控边界存在非零
处理窗口，不能替代现实匿名冻结输入或算法晋级证据。

#### 身份中性状态修正晋级规则

共同质心候选已完成 D1 模块实现、main 接线和受控冻结扫描边界诊断，clean seed 1100 的
46 个候选仍全部被 OOSM 或非平衡分量门控拒绝。候选继续默认关闭，系统效果 P1 开放。停止
1101/1102；下一次系统试验使用新的真实匿名冻结扫描，固定同一上游扫描流比较 hold-only 与
hold+共同质心，再运行未见 seed 闭环。不得通过删除双时间戳或放宽满基数、OOSM 和
fail-closed 合同制造处理。free-row、free-column、OOSM、过期、重复、形状不一致或超规模
分量继续 prediction-only。完整数学规则、测试和 A/B 门槛见
`../../../subagent_reviews/D1_STRUCTURAL_AMBIGUITY_HOLD_CAUSAL_AUDIT_CN.md`。

### Radar assignment ambiguity 实验候选 v2

#### 输入与最大匹配

v2 的策略版本为
`fail_closed_maximum_matching_allowed_edge_component_v2`。配置
`radar_assignment_ambiguity_governance_v2=False` 默认关闭，并与 v1 开关互斥。默认关闭时不
执行新增图运算，原 Hungarian 分配、更新、birth 和审计值保持基线行为。

对一批匿名雷达扫描，设既有航迹数为 `m`，观测数为 `n`。原在线关联已在共同量测时刻使用状态、
协方差和雷达位置创新得到代价矩阵 `Q` 与门内矩阵：

```text
A[i,j] = finite(Q[i,j]) and Q[i,j] <= association_gate
```

候选不重新解释原始量测，不读取 observation 名称或离线标签。SciPy 路径保留原 Hungarian
结果。由于门外惩罚远大于门内代价，该结果先最大化门内匹配基数，再最小化当前代价。SciPy
不可用时，历史 greedy 结果可能不是最大匹配；v2 从该匹配出发，以确定性深度优先增广路径补齐
基数。增广过程只遍历 `A=True` 的边，列顺序由在线代价和列号确定，不枚举排列。

#### 允许边判定

记补齐后的一个最大匹配为 `M`。在含 `m+n` 个顶点的有向图中：

```text
(i,j) in M       : observation_j -> track_i
(i,j) in E \ M   : track_i -> observation_j
```

任意另一个最大匹配 `M'` 与 `M` 的对称差可分解为交替环或偶数长度交替路径。两组匹配基数
相同，因此路径端点位于二部图同一侧。非匹配门内边能够出现在某个最大匹配中，当且仅当至少满足
以下一个条件：

1. `track_i` 与 `observation_j` 位于同一强连通分量，对应交替环；
2. `track_i` 可由某个未匹配 track row 到达，对应 free-row 交替路径；
3. `observation_j` 可以到达某个未匹配 observation column，对应 free-column 交替路径。

第三项在实现中通过反向图从 free columns 做可达搜索。当前匹配边始终属于允许边。该判定与
Dulmage-Mendelsohn 分解的最大匹配允许边边界等价，复杂度由一次最大匹配补齐、强连通分量和
线性可达搜索构成，不使用固定 likelihood margin。

#### 不确定分量和 birth 边界

实现把允许边转成无向图。只含一条固定匹配边的分量没有替代关系，继续正常更新。分量只要包含
一条非当前允许边，就被标记为不确定分量：

```text
不确定分量中的全部 observation
  -> 从 assignments 删除
  -> 记录 radar_assignment_ambiguity_suppressed
  -> 标记 processed
  -> 跳过 EKF update
  -> 跳过 _create_track()

不确定分量中的全部既有 track
  -> 只传播到 arrival_timestamp
  -> 不做量测协方差收缩
  -> 记录统一的 component kinds、双时间戳和 policy version
```

该处理对 matched 和 unmatched observation 一致。`2x3` 图中，若 free column 可通过交替路径
替换当前匹配列，当前匹配 observation 与 free observation 同属一个分量，二者都被抑制；
free observation 不会绕过关联治理形成重复 birth。完全门外或不在替代分量中的 free
observation 仍可按原雷达初始化规则 birth。

#### 审计和边界

v2 继续使用现有真值无关审计字段。显式启用时：

```text
radar_assignment_ambiguity_governance_enabled = true
radar_assignment_ambiguity_policy_version =
  fail_closed_maximum_matching_allowed_edge_component_v2
radar_assignment_ambiguity_governance_status =
  experimental_v2_enabled_rejected_candidate
```

该 status 表示运行时显式启用了已经被系统验收门槛拒绝、默认关闭的研究候选。它不表示 v2
重新进入 clean A/B，也不改变算法开关的默认值。

为保持 `d1.association_audit.v1` 的既有消费者兼容，历史
`radar_assignment_ambiguity_policy_version` 在两种开关均关闭时仍返回 v1。新增字段消除其
语义歧义：

```text
radar_assignment_ambiguity_selected_policy_version =
  None | fail_closed_gate_feasible_alternating_cycle_v1 |
  fail_closed_maximum_matching_allowed_edge_component_v2

radar_assignment_ambiguity_candidate_policy_versions = (v1, v2)
```

下游判断顺序为 selected、enabled、status。`selected=None` 明确表示没有运行 v1 或 v2；
不得因兼容字段仍为 v1 就把基线标记为 v1 实验。

相关 track metadata 额外记录 observation component count 和以下一种或多种结构原因：

- `alternating_cycle`
- `free_row_alternating_path`
- `free_column_alternating_path`

算法只使用在线状态、协方差、双时间戳、门内边、在线代价和匹配结构。雷达第四维为零且
`radial_velocity_observed=False` 时，该值不进入消歧。`global_track_id` 只作为既有航迹引用
和审计输出，不由 D1 重写。

模块回归包括 `2x2` cycle、`3x2` free-row、`2x3` free-column、唯一最大匹配、门外边、
首扫无 track、greedy fallback、OOSM 和 200 航迹稀疏图。专项 v1/v2 共 `29 passed`，D1
全量 `220 passed`。测试检查双时间戳、有限半正定 `6x6` covariance 和既有
`global_track_id` 集合。main 独立穷举 2,666 个小型二部图，最大匹配基数与允许边分量均与
oracle 一致；scalable 模块 `142 passed`。穷举代码不属于运行路径。

#### Clean 系统 A/B 与候选拒绝

main 在 clean commit `c928727` 运行首个未见 seed 1100。baseline/v2 均为 200v200、2.2 s、
`recon_count=2`，使用同一 commit，`repository_dirty=false`、
`config_sha256=20ef5248...b840`。runtime profile 分别为 `b508f675...12a8` 和
`9680c45b...f9f4`，只改变 v2 treatment。两组 finite=true、online truth=0；online
observations=2,035、radar observations=1,954、target labels=2,352、known false alarms=90，
说明输入和离线评分标签数量一致。

结果如下：

```text
ambiguous mappings       0 -> 0
D1 tracks              202 -> 202
D2 tracks              203 -> 199
D3 assignments         200 -> 196
ID switch                9 -> 9
track continuity      .865 -> .830
coverage continuity   .870 -> .835
available mappings    1566 -> 1503
unavailable mappings   230 -> 266
```

v2 检出 9 个 ambiguity scans，抑制 `77/1954=3.94%` 的雷达观测，track coast=91。身份指标
ambiguous mapping 和 ID switch 均无改善，D1 航迹数量不变，但 D2 航迹、D3 分配、连续性和
映射可用性下降。

图论算法回答“哪些门内边可能进入某个最大匹配”。当前 intervention 进一步把含替代边的整个
允许边分量全部停止 update 和 birth。seed 1100 表明后一步过于保守：正确识别不确定边界并不
意味着所有相关信息都应在该扫描被丢弃。

该结果触发预注册停止门槛。seeds 1101/1102、10 s 和 20-seed 不再运行；v2 不晋级并保持
默认关闭。模块图论验证继续有效，系统收益结论为拒绝，P1 身份连续性保持开放。后续若设计局部
延迟提交、跨扫描证据积累或分级 suppression，必须作为新候选重新验收，不能沿用 v2 的系统
放行结论。

### Radar assignment ambiguity 实验候选 v1

生产默认 `radar_assignment_ambiguity_governance=False`，完全跳过本节候选并执行基线
Hungarian。只有显式传入严格布尔值 `True` 时，候选才挂在 `process_scan_batch()` 的全 radar
分支。原关联先在共同
`measurement_timestamp` 取得每条航迹的六维状态预测和协方差，以雷达三维位置创新构造：

```text
d_ij = z_position_j - x_position_i(t_measurement)
S_ij = P_position_i(t_measurement) + R_position_j + epsilon I
q_ij = d_ij^T pinv(S_ij) d_ij
valid_ij = finite(q_ij) and q_ij <= association_gate
```

原 Hungarian 或 SciPy 不可用时的 greedy fallback 先产生一对一集合 `M`。候选不修改
`q_ij`、门限或分配求解，而是在已匹配行列上构造有向图：

```text
column_by_row[i] = M 中分给 track row i 的 observation column
i -> k  当 i != k 且 valid[i, column_by_row[k]]
```

图中大小至少 2 的 strongly connected component 包含一条交替环。把该环上的匹配边替换为
交叉门内边，会得到另一组同基数匹配，因此当前扫描不能安全声明身份唯一。实现把整个强连通
分量作为保守治理单元：

1. 从 `assignments` 删除分量内 observation columns；
2. 为每条 observation 记录 `radar_assignment_ambiguity_suppressed` 并标记 processed；
3. 直接跳过 update 和 `_create_track()`，所以被抑制 observation 不能 birth；
4. track 只保留扫描前到 `arrival_timestamp` 的 CV prediction，不执行 EKF update；
5. 记录 component size、track IDs、measurement/arrival timestamp 和 policy version。

矩形矩阵只把 Hungarian/greedy 实际匹配的行列放入图。未匹配行不增加 ambiguity coast 计数；
未匹配列仍按原规则独立 birth，但分量内被抑制列不会落入 birth。首扫或空 track set 直接返回，
门拓扑唯一时所有 SCC 都是单点。扫描 API 已要求同 sensor、同 modality、同双时间戳和同
observer-scan key，所以 acoustic/EO/lidar 不进入该规则。

`association_audit_summary()` 的新增在线字段为：

- `radar_assignment_ambiguity_scan_count`
- `radar_assignment_ambiguity_observation_suppression_count`
- `radar_assignment_ambiguity_track_coast_count`
- `max_radar_assignment_ambiguity_component_size`
- `radar_assignment_ambiguity_governance_enabled`
- `radar_assignment_ambiguity_policy_version`
- `radar_assignment_ambiguity_governance_status`
- `latest_radar_assignment_ambiguity_track_ids`

track metadata 另保留 latest reason、双时间戳、component size 和 policy version。字段不含
truth 或 observation 名称派生身份。策略版本为
`fail_closed_gate_feasible_alternating_cycle_v1`；status 为 `disabled` 或
`experimental_enabled`。非 bool 构造参数直接抛 `TypeError`。

#### 根因与候选排除

seed 1000 中 `global_track_100/101` 在 scans 8--10 对两个 radar 谱系
swap/保持/swap-back；seed 1002 的 `global_track_187/188` 同构。相同 radar-only 输入把 delay
置零后，分配和代价保持而 OOSM 归零，说明不是 fixed-lag/OOSM。

20:1 likelihood-margin 原型只在首次近等价扫描抑制。coast 改变后验后，后续错误排列的单帧
代价会显得唯一并被提交，因此该门不能证明身份。v1 使用门拓扑可交换性而不是同一开发输入上的
真值调参。其代价是只要存在门内交替环就抑制，即使 winner 的代价明显更低。

#### 开发回放与 detached clean 阻断

truth sidecar 在参考和候选在线回放均结束后才连接。开发冻结回放只用于复现根因和候选机制，
不作为 clean 或泛化验收。main 随后对 baseline `488dc39` 与 v1 candidate `d967c96` 运行
200v200、2.2 s、`recon_count=2`、seeds 1000/1001/1002 同配置 A/B；每个 seed 的配置哈希
在两端完全相同：

| Seed | D2 ambiguous | strict identity | D1 | D2 | D3 | suppression |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| 1000 | `2 -> 0` | unavailable -> available；候选 IDSW `3`、continuity `.8600` | `203 -> 203` | `201 -> 200` | `200 -> 198` | `22/1962 = 1.12%` |
| 1001 | `0 -> 0` | available 保持；IDSW `9 -> 7`、continuity `.869444 -> .814444` | `201 -> 201` | `202 -> 194` | `200 -> 190` | `130/1966 = 6.61%` |
| 1002 | `2 -> 0` | unavailable -> available；候选 IDSW `4`、continuity `.8350` | `201 -> 201` | `200 -> 197` | `200 -> 193` | `78/1958 = 3.98%` |

strict availability 从 `1/3` 提升到 `3/3`，但 D2 航迹和 D3 分配均明显下降，seed1001
continuity 下降约 `0.055`，信息抑制为 `1.12%/6.61%/3.98%`。三组 finite=true、
`repository_dirty=false`、online truth=0、missing identity evidence=0，
target/known-false-alarm 标签数相同。因此 v1 不晋级。

早先 `/tmp/msm-clean-radar-d967c96` 的运行遗漏 `--recon-count 2`，实际是
`recon_count=8` stress，三 seed 配置哈希为 `cc6/cbb/9f45`。它不能与 recon=2 baseline 比较，
只用于结构诊断。该 stress seed1001 的 `GT3D-000210` 与 D1 既有 `global_track_187` 的终态
state/covariance 相同，不是 D1 新 birth。该 D1 track 由 scan 1 radar 初始化，scan 8 接受另一
离线谱系 radar，scan 9
回到原谱系，随后接入两条 vision；D2 在末帧重建 canonical track。scan 8 的关联矩阵为
`200x199`，有 209 条 gate-valid edge、198 个匹配、2 个 free row、1 个 free column：

```text
Hungarian: global_track_187 -> observation，cost = 0.80058
替代边:   global_track_186 -> same observation，cost = 1.58216
```

替代边占用 observation 并释放 `global_track_187`，匹配基数不变。这是 free-row alternating
path；v1 的已匹配行 SCC 看不到它。一般矩形图还存在通向 free column 的同基数路径，相关
unmatched observation 若不治理可能落入 birth。full alternating-path v2 现已按上一节完成
模块实现并经过 main seed 1100 detached clean A/B；图论验证通过，系统 intervention 被拒绝。

同一 recon=8 stress seed1001 的 1,966 条 radar 原始量测全部是三维
range/azimuth/elevation 和 `3x3` covariance。转换后的第 4 维零值明确是
`radial_velocity_observed=False`、`filter_measurement_dimension=3` 的 placeholder，不能作为
独立速度观测缩图。

专项测试现在直接使用生产参数：默认实例复现原 Hungarian 换绑，显式 True 才验证 v1
suppression；性能和规模 fixture 不再 subclass override 生产逻辑。专项还以 gate-valid `3x2`
记录 free-row blocker，并覆盖三目标环、门拓扑唯一、首扫、OOSM、greedy fallback、双时间戳、
协方差和 `global_track_id`。专项 `13 passed`，D1 全量 `204 passed in 16.70s`。

默认关闭提交 `8f17c5d` 已按上述 recon=2 同配置重跑，三 seed 的全部业务指标恢复
`488dc39` baseline。main 跨构建审计 `3/3 passed=True` 且
`normalized_online_payloads_equal=True`，证据位于
`/tmp/msm-default-off-cross-build-8f17c5d-r2`。该结果证明默认回退无业务回归，不证明 v1
可晋级。

结论是 v1 默认关闭且已被 clean A/B 拒绝，P1 未关闭。v2 已覆盖最大基数 matching allowed
edges 的 cycle/free-row/free-column，但 seed 1100 clean A/B 已确认当前整分量 suppression
没有身份收益并降低下游可用性，因此同样不晋级。10 s radar+vision
ambiguous 不能单独证明 radar-only 根因，但长期 coast 与跨模态传播仍必须进入集成验收。

### 匿名跨模态几何门控

雷达初始化的航迹在视觉扫描到达时，D1 先在 `measurement_timestamp` 取得该航迹的 NED 后验
`(x_i, P_i)`，再使用观测自身的相机模型构造像素预测：

```text
p_c = R_camera_from_ned * (p_ned - p_camera_ned)
u = fx * p_c.x / p_c.z + cx
v = fy * p_c.y / p_c.z + cy
```

`p_c.z <= 0`、非法外参或非有限投影返回 unavailable。合法候选继续计算：

```text
r_ij = z_j - h_i
S_ij = H_i P_i H_i^T + R_j
NIS_ij = r_ij^T pinv(S_ij) r_ij
```

其中 `R_j` 是当前视觉观测的像素协方差。`NIS_ij` 仍使用原 `association_gate`，扫描内仍由
Hungarian 完成一对一分配。更新后的非量距笛卡尔修正还要通过原有状态修正门。量测时刻用于
历史更新，到达时刻用于 OOSM/延迟审计；六秒 fixed-lag 不变。

根因修复位于 `CameraModel.from_metadata()`：解析器现在接受 `Mapping`，因此
`SensorScanFrame` 冻结后的嵌套 `camera_model` 不会丢失；同时兼容
`rotation_camera_from_ned` 和 `camera_intrinsics`。相机模型构造检查位置、旋转、焦距和图像
尺寸。该变化没有加入任何 truth ID、Actor/Object 名称或 D6 结果。

`association_audit_summary()` 增加以下在线诊断：

- `eo_projection_gate_pass_count`
- `eo_projection_gate_rejection_count`
- `eo_projection_unavailable_count`
- `eo_one_to_one_unassigned_count`
- `max_eo_projection_gate_pass_nis`
- `latest_eo_projection_rejection_reason`

字段只反映投影门和一对一分配结果。seed 1000 候选计数为通过 2,255、拒绝 215、不可计算 0、
一对一冲突 3；最大门内 NIS 为 39.326205。构造负例另行覆盖非法外参和相机后方点，因此该
episode 的不可计算为 0 不表示拒绝分支未测试。

专项 A/B 使用同一 771 scans/11,889 observations。旧/新规范状态与谱系哈希分别为
`39d0cdf5...02d7` 和 `b0d6c4ac...d717`。D2 标出的 17 条污染视觉观测 17/17 得到单一离线标签
谱系；标签只用于回放后核验。D1 全量回归为 `191 passed in 16.88s`。

### Scan claim 单次 JSON 安全物化

`ScanInputOrganizer` 在接纳扫描前构造 `_ScanClaim`。claim 包含逐 observation 谱系摘要、
整扫描谱系摘要、内容摘要和完整帧摘要。旧路径先构造带 NumPy 数组和冻结 mapping 的 Python
记录，再由两个 `_digest()` 分别递归执行 `_json_safe()`。共享内容因此被处理两次。

当前 `_claim_for_frame()` 按以下顺序执行：

```text
只读 SensorScanFrame
  -> 每条来源谱系转换一次并计算原 SHA-256
  -> 每条 observation 的共享内容转换一次
  -> 共享内容 + 到达/转发/scan 字段形成完整帧记录
  -> 两组记录按相同谱系键排序
  -> 使用原 JSON 编码参数分别计算内容摘要和帧摘要
  -> 原 claim registry 与拒绝状态机
```

`_digest_json_safe()` 只接收已经完成规范化的内部记录；外部任意对象仍通过 `_digest()` 进入完整
`_json_safe()` 校验。帧专有字段也单独执行一次 `_json_safe()`，因此非有限通信时间戳或不支持
类型仍会 fail closed。`ScanInputOrganizer._build_claim()` 是受保护覆写点，仅用于冻结性能基准
运行旧参考实现，生产默认始终使用新路径。

clean `5263e2b` seed 1000 冻结输入的完整参考/候选流水均处理 771 scans 和 11,889
observations。claim registry、逐输入结果、release schedule、逐 fusion 后验、操作数、累计
诊断、终态和一致性证据严格一致。5 轮交错计时 P50 由 `3.618 s` 降至 `1.905 s`；
`_json_safe` cProfile 累计由 `5.781 s` 降至 `1.992 s`。门限、协方差、6 s fixed-lag、观测
数量和滤波公式没有变化。

### SensorScanFrame 完整性封印与 organizer 复用

`SensorScanFrame.__post_init__` 继续执行原有完整流程：逐 observation alias-free 快照、只读
数组和递归冻结 metadata、在线 truth 隔离、协方差合同、双时间戳、统一 frame/scan identity
及 source lineage 校验。新增 `_snapshot_integrity` 描述该已验证快照的对象和不可变结构，
包括已缓存 source-lineage tuple 的对象身份与内容，不替代上述校验。

`ScanInputOrganizer.ingest()` 收到 `SensorScanFrame` 时先调用
`_frame_snapshot_is_intact()`。封印完整则直接进入原 `_ingest_frame()`，继续生成相同
claim、content/frame digest、audit event、watermark 和 release schedule；封印不完整则按
原路径重新构造 `SensorScanFrame`。`performance_diagnostics()` 记录完整帧复用、变异帧重建、
iterable 帧构造和 organizer 内 observation 快照数，供冻结 benchmark 使用。

测试覆盖完整帧对象直接复用、谱系缓存被替换后的 observations 重建、数组恢复可写后的
alias-free 回退，以及 metadata 注入 truth 后的 fail-closed 拒绝。缓存篡改回归同时比较
reference/candidate 的 claim、结果和 audit 摘要。完整 `4ac3bb2` seed 1000 冻结复放进一步比较：

- 771 个逐输入 organizer 结果、close 结果、audit 和 94 个 release groups；
- 771 个逐 fusion posterior，包括状态、协方差、时间戳、source lineage 和 track level；
- 每次物化的 `GlobalTrack`、201 条终态航迹和一致性证据；
- 每个 fusion 的 batch operation counts 与累计 `FusionPerformanceDiagnostics`。

所有语义检查相等。逐 fusion operation snapshot hash 为
`sha256:82728a8e0fed0adedd0254368e29a3c117157b066158595d7ca6dac558bfb5bf`，累计诊断
snapshot hash 为
`sha256:b28df84d6664ba17d097990f7186a2a611f2e3469394e3d2a12122dbec521766`。
main 实测当前 D1 全量回归为 `185 passed`，作为本工作区当前权威测试计数。

### Fusion profiler 结论

fusion 算法代码本轮未改。完整 cProfile 的主要累计路径为
`global_tracks 17.559 s`、`_scan_one_to_one_assignments 17.027 s`、
`_to_global_track 16.930 s`、`_cached_non_radar_scan_cost_matrix 14.971 s`、
`_replay_record 8.601 s`、`_state_at 5.023 s` 和完整 checkpoint 查询 `3.735 s`。
累计操作数与 clean episode 相同：2,345,793 candidate pairs、505,926 innovation solves、
152,799 checkpoint queries、3,837 fixed-lag rebases、286,792 checkpoint reuses 和
91,151 次 GlobalTrack 物化。

48 个 radar scans 的未剖析 P95 为 `343.059 ms`，候选对峰值 40,000，单扫描 rebase 峰值
197；308 次同 fusion timestamp 调用保持 state-only，463 次完整物化。进一步减少
GlobalTrack audit metadata 或 radar/rebase 成本需要单独合同设计，本轮不实施不确定优化。

当前优化验证运行在未提交 D1 工作区，并使用 clean `4ac3bb2` 的单 seed 三维质点冻结输入；
不是新的 clean full-stack、AirSim、正式多 seed 或实时证据。

## 前一权威增量（2026-07-22）

### Nominal 200v200 clean 单 seed 全栈校准

算法实现完成后，main 在 detached clean
`4ac3bb2c12cc6af6ebd372107ced00bcdc5adf6a` 上运行 10 s、seed 1000 的
`200v200-nominal-v1` 全栈，并以 clean
`0d2da25c14e50f8f9a10ad47a7bd74e5c5e577fb` 的同 seed、同配置运行作为基线。候选世界状态
有限，11,889 条匿名在线观测均保持 truth 隔离，`online_truth_use_count=0`。

| 计时口径 | 基线 | 候选 | 变化 |
| --- | ---: | ---: | ---: |
| episode 核心 wall | 94.104939744 s | 85.002427712 s | -9.6727%，1.1071x |
| D1 fusion 累计 | 49.697406826 s | 40.272795088 s | -18.9640%，1.2340x |
| D1 scan input 累计 | 12.315225105 s | 12.560936034 s | +1.9952% |

候选核心 RTF 为 `0.1176437`。`stage_timings.csv` 对 771 次 D1 fusion 调用给出的
P50/P95/max 为 `33.25249/224.76351/592.95713 ms`。跨构建审计的规范在线载荷、离线 truth
state 和计划谱系比较全部通过；因此当前结果支持同 seed 业务语义保持，但 fusion 尾部仍有
显著长调用，scan-input 也没有同步改善。

外部 `/usr/bin/time` 总进程 elapsed `1:55.95`、峰值 RSS `2,468,928 KiB` 是不同层次的
资源证据。总进程包含解释器启动、离线后处理和写盘，不能与核心 wall 混用。验收范围只覆盖
两端 clean、同 seed/配置、有限状态、在线 truth 0 和跨构建语义一致。这是单 seed 描述性 clean
校准，不是 20-seed 或正式性能矩阵，且 RTF 小于 1；fusion P95/max 尾延时与 scan-input 成本
仍是 P1，不扩展为 AirSim、RMSE/NEES/NIS 或物理效果结论。

### 非雷达创新协方差矩阵栈

非雷达候选的归一化创新平方仍定义为：

```text
r_ij = wrap(z_j - h_i)
S_ij = H_i P_i H_i^T + R_j
q_ij = r_ij^T pinv(S_ij) r_ij
```

其中 `i` 是候选航迹，`j` 是同一扫描内观测。旧路径对每个 `(i,j)` 单独进入
`numpy.linalg.pinv()`。新路径只在量测几何、量测维度、协方差维度和角度残差索引完全相同时
分组，构造 `S[group, track, observation, :, :]` 后批量求伪逆。`R_j` 不共享，`P_i/H_i`
不跨航迹共享。批量返回后仍按旧顺序逐候选计算 `r_ij^T pinv(S_ij) r_ij`，因此代价矩阵、
门控和 Hungarian 分配保持。批量调用异常时，该组逐候选回退。

```text
同一扫描观测
  -> 按实际几何与矩阵形状分组
  -> 每航迹构造一次 h_i、H_i、H_i P_i H_i^T
  -> 每观测加入自己的 R_j
  -> pinv(S_stack)
  -> 逐候选原顺序计算 q_ij
  -> 原门限与 Hungarian
```

未见 seed 1000 的完整 10 s 输入含 771 个扫描和 11,889 条观测。旧/新无 profiler 墙钟为
`50.458/39.994 s`；逐扫描摘要、终态航迹和一致性证据哈希相同，操作计数和累计诊断也相同。
前 256 扫描在同进程预热后交错 7 次，P50 加速 `1.196x`。实现保留
`batched_non_radar_innovation_solve=False` 参考开关，便于后续冻结回归。

### 缓存一致性证据的计数更新

固定滞后检查点复用时，`_refresh_cached_consistency_evidence_if_enabled()` 只需要把缓存证据推进到
当前 replay revision，并增加 replay count。旧实现调用通用 `replace()`。该调用会重新验证
记录的双时间戳、状态、协方差、NIS、门控、可用性和谱系，并重新推导 `evidence_id`。代表
10 s seed 中这一路径调用 194,916 次，累计 27.122 s。

新实现增加 `OnlineConsistencyEvidenceRecord.with_replay_counters()`。方法先把两个输入按旧语义
转换为整数并拒绝负值，再从原冻结记录复制全部 slots，只覆盖两个计数。原对象已经通过
`__post_init__`，其余字段没有写入口；嵌套 availability 和状态/协方差元组也都是不可变值。
融合器以 `trusted_consistency_counter_refresh` 控制 A/B，默认启用受限路径，关闭时继续执行旧
完整重验。

```text
合法缓存前缀
    -> 后验、门控、协方差、时间戳、谱系均未变化
    -> 校验 replay_revision/replay_count 为非负整数
    -> 复制冻结记录并覆盖两个计数

新证据或内容变化
    -> 完整构造
    -> 完整字段校验
    -> 重新生成当前证据内容
```

冻结 A/B 对 seeds 42000-42002 逐扫描比较内部后验和航迹分级，并比较终态航迹、最终证据、操作
计数和物化计划。全部通过，在线 truth 使用为 0。未剖析纯融合均值
`64.844 -> 52.657 s`；代表 seed 的重放累计 `35.348 -> 9.410 s`。其后的非雷达代价矩阵工作
已由上节完成，下一性能工作转向航迹物化和 scan input，不应放宽固定滞后、门控或协方差合同。

### 集成执行与等价验收

certified radar pre-gating 在扫描代价矩阵构造阶段工作。通过认证且保守下界已越过原门限的候选
不再执行伪逆；其余候选仍进入原精确 `np.linalg.pinv`、原门限和 Hungarian 一对一分配。该优化
没有更改 `SensorObservation`、固定时滞重放、`GlobalTrack` 或下游 D2-D7 合同。

main 以 clean `8f86192` 为参考、clean `f80b5bd` 为候选，对 10 s、200v200 nominal seeds
42000/42001/42002 独立运行完整总线。三组 D1 终态航迹数在两条路径均为 `202/207/203`，有限
状态和在线 truth 使用 0 均保持。D1 fusion 累计耗时均值由 `92.991088 s` 降至
`88.330438 s`；scan input 由 `16.902643 s` 增至 `17.524242 s`。精确创新求解总数由
`7,130,228` 降至 `1,578,677`。

业务等价检查逐条比较在线总线。独立运行产生的 D3 `plan_id` 按规划出现次序和版本建立一一
映射；映射前先校验 ACK 原始载荷 SHA，映射后仍比较 predecessor、owner、version、coalition、
`global_track_id` 和 command 等业务字段。三个 seed 的全部主题检查均通过，D1 fused-track 主题
规范哈希一致。`association_innovation_solve_count` 是实现成本计数，明确不参与业务等价比较，
不能用来解释融合精度。

该验收说明预门控和 A95 复用在当前 integrated 三 seed 上保持业务语义。它不证明 D1 已实时，
也不解决当前长时归一化超线性、AirSim 接线或正式 RMSE/NEES/NIS。

### 雷达候选的可证明预门控

雷达扫描中每个航迹和观测候选原本都计算
`q = d.T @ np.linalg.pinv(S) @ d`。直接用 `||d||^2 / trace(S)` 预拒绝并不安全：`S` 可能不定，
也可能包含被 `pinv` 截断的近零奇异值，此时该比值不是旧伪逆二次型的可靠下界。

当前实现先执行廉价认证。设第 `i` 行非对角绝对值和为 `r_i`：

```text
g = min_i(S_ii - r_i)
U = max_i(sum_j(abs(S_ij)))
```

只有 `S` 全部有限、逐元素严格对称，且加入浮点安全裕量后的 `g > 0` 并满足
`g > 1e-15 * U` 时才认证。严格对称与 `g > 0` 通过 Gershgorin 圆盘定理保证 `S` 严格正定；
`U` 是其最大特征值和谱范数的保守上界。第二个条件保证最小特征值高于旧
`np.linalg.pinv` 的 cutoff 上界，因此伪逆不会截断任何方向并等于通常逆。此时：

```text
d.T @ pinv(S) @ d >= ||d||^2 / U
```

只有右侧在保守数值裕量后严格大于原关联门限，候选才记为无穷代价而跳过精确求解。不定、近
奇异、非对称或非有限矩阵全部回退旧 `pinv`。原门限、伪逆、Hungarian 分配和候选集合生成没有
放宽。

负例分别使用带负特征值的交叉协方差和 `diag(1e12, 1, 1e-20)`。差向量沿负特征方向或被截断
方向设置，使旧 `pinv` 代价不超过门限，而朴素 trace 比值超过门限。新认证对两者均失败，
rejection mask 全 false；扫描回归中参考和候选路径执行相同数量的精确求解并输出相同后验。

完整快照物化还把同一航迹协方差的 A95 从分级和 metadata 两次特征分解改为一次计算复用。
关闭开关后的参考路径与默认路径输出逐字段相同。10 s seeds 42000-42002 的精确创新求解合计
`7,130,228 -> 1,578,677`，逐扫描、终态和一致性证据哈希一致；旧/新墙钟均值
`91.313/88.619 s`。这仍是冻结三维质点输入上的 D1-only 证据，不代表实时或正式精度。

### Clean 200v200 接线证据

算法接口完成后，main 在 clean 候选提交 `8f86192` 中按量测扫描顺序执行状态更新，并仅在同一
fusion timestamp 的最后后验构造完整 `GlobalTrack` 快照。10 s、200v200 三维质点 seeds
42000、42001、42002 均 clean、finite，在线 truth 使用 0，D1/D2 overflow 和全部安全合同通过。

三例 scan/state-only/full snapshot 计数分别为
`764/310/454`、`844/328/516`、`782/278/504`。state-only 与 full snapshot 之和逐例等于扫描
总数，说明每个扫描仍被融合并发布。与旧 clean `3bac3ff` 相比，事件、scan input、共享摘要及
世界真值相同；D1 fusion 三 seed 均值 `103.339 -> 92.991 s`，下降 10.0%。seed 42000 的
2.2 s 全栈墙钟 `18.611 -> 18.302 s`。

该结果验证 main 调用方式和算法语义，没有改变滤波公式、门控、固定时滞窗口、双时间戳、
协方差或规范身份。D1 fusion 处理 10 s 输入仍平均耗时 92.991 s，实时性、AirSim 和正式精度
继续开放。

### 扫描状态更新与航迹物化分离

同一 runtime tick 可能由扫描整理器释放多个不同传感器或不同量测时刻的扫描。扫描不能拼接成一个伪
扫描，因为每个扫描都有独立 observer-scan key、一对一关联集合、双时间戳和乱序语义。当前实现
保持逐扫描状态更新，只把完整航迹对象构造从同一 fusion timestamp 的中间扫描移到该组末尾：

```text
released scan 1 -> process_scan_batch(..., materialize_tracks=False) -> state/audit
released scan 2 -> process_scan_batch(..., materialize_tracks=False) -> state/audit
released scan n -> process_scan_batch(..., materialize_tracks=False) -> state/audit
                                                            |
                                                            v
                                         materialize_global_tracks() once
                                                            |
                                                            v
                                  GlobalTrack snapshot -> D2 / persistence
```

状态-only 调用完整执行观测校验、扫描级代价矩阵和一对一分配、航迹起始、固定时滞重放、检查点
前 OOSM、预测、协方差限制、健康统计、一致性证据修订、来源谱系和性能计数。它只不调用
`global_tracks()`。返回的 `FusionStateUpdateResult` 包含准确的 `current_track_count`，因此 main
可记录轻量状态，而无须从 `tracks` 推导数量。`tracks` 属性主动抛出
`TracksNotMaterializedError`，防止空列表被解释为当前没有航迹。main-owned scalable 三维质点
runtime 已按该调用方式完成上述 clean 三 seed 复跑。

显式物化接口在当前内部后验上构造 `FusionTrackSnapshot`。它共享一次 association/latency/
sensor-health 发布上下文，再逐航迹复制状态、协方差、生命周期、支持来源和元数据。物化不执行
新关联或新滤波，也不改变 `global_track_id`。实际航迹物化数和健康快照构造数进入累计性能诊断。

测试序列包含 3 个目标、量测时刻 0/3/10 秒的扫描和一帧量测时刻 1.5 秒、到达时刻 10.2 秒的
检查点前 OOSM。默认 6 秒固定时滞使检查点推进到 3 秒。逐扫描完整发布与四次 state-only 后一次
物化的终态航迹、协方差、分级、元数据、时延审计、健康摘要和 consistency evidence 相同；
物化数从 12 降到 3。

发布日志审计 schema 升为 `d1.fused_track_publication_audit.v2`。没有
`tracks_materialized` 的旧记录按完整快照读取。新状态记录使用
`tracks_materialized=false`、`tracks=[]`、`track_count=0` 和准确的 `current_track_count`；
audit 仍兼容过渡期的 `tracks=null`。审计分别统计总发布数、完整快照数、状态更新数和完整快照
内航迹记录数。定向测试 `30 passed`，D1 全量 `168 passed in 29.43s`。没有运行
AirSim；完整 200v200 运行时的 clean 三 seed 结果见上节，但仍未形成实时闭合结论。

### 长时固定滞后检查点复用

长时专项使用同一份 10 s 冻结扫描序列对照旧路径和优化路径。输入包含 764 个扫描、12,107 条
匿名观测和 202 条终态航迹，在线 truth 使用为 0。优化由四个可关闭开关组成，默认开启：

1. 完整缓存可用时，`_state_at()` 在有序检查点中二分定位最近后验，再预测到查询时刻；
2. 固定滞后重基时保留重基边界之后的合法检查点后缀；
3. 检查点失效逻辑已维护合法前缀时，不再逐项重复比较 observation ID 和排序键；
4. 未变化前缀的一致性证据复用原后验、归一化创新平方和门控结果，仅刷新 replay revision/count。

任何历史插入、起始状态变化或检查点前乱序量测仍按原规则失效缓存并完整重算。6 s fixed-lag、
`measurement_timestamp`/`arrival_timestamp`、协方差、候选集合、Hungarian 分配、创新门限、
`GlobalTrack` 和在线真值隔离保持不变。

确定性对照结果为 history replay `170,106 -> 13,397`、filter update `120,440 -> 9,549`，候选对
和创新求解均为 2,393,969。纯融合墙钟 `157.237 s -> 107.449 s`。逐扫描、终态和一致性证据
哈希全部一致。`FusionAdapter.fusion_performance_diagnostics()` 返回 schema 版本化、固定大小的
累计计数，包含用户侧 episode summary 缺失的 `replay_filter_update_count` 和
`replay_checkpoint_reuse_count`。本次优化路径记录状态查询 152,861、固定滞后后缀复用 110,891、
合法前缀快路径 300,024 和缓存一致性刷新 194,916 次；该接口不保留逐扫描快照，不要求修改 main
合同。

冻结日志的 764 条全量航迹发布约 186.2 MiB，只有 407 个唯一融合时刻。该数据来自延迟物化接口
引入前。D1 已提供同一 tick 中间状态更新和末尾快照接口，main 也已在 scalable 三维质点全栈
接线。跨 tick 合并和轻量 heartbeat/lineage 仍是后续建议，必须保留规范状态、身份、生命周期、
质量跨档和来源谱系事件。

### 第二阶段扫描关联工作区

第一阶段增量后验成为默认路径后，clean `492979e` 的 200 规模五 seed D1 fusion 均值仍为
12.103 s。第二阶段使用 seed 42000 的冻结输入进行 current-default 与优化路径对照；输入
SHA-256 为 `bc539686b130d96c63b76b9161fadbae2dba59de44cb61ac80d92f2ea1018406`，包含
86 个扫描和 2,051 条匿名观测。

`FusionAdapter` 新增默认启用的扫描关联模型缓存。非雷达扫描先为每条观测构造一次
`MeasurementModel`，并为每条候选航迹取得一次共同量测时刻状态。`MeasurementModel` 的
`geometry_key` 由实际参与量测函数的传感器位置、相机位置、世界到相机旋转矩阵和相机内参组成。
几何键相同的观测可复用该航迹的预测量测和数值雅可比；不同几何仍分别投影。

缓存不保存候选对判定。每个航迹-观测对继续独立计算角度残差、创新协方差、伪逆、归一化创新
平方和门限结果，再形成完整代价矩阵并执行 Hungarian 一对一分配。雷达继续使用原有批量状态和
门控矩阵路径。扫描原子性、OOSM、fixed-lag、双时间戳、covariance、observer-scan conflict、
航迹起始/分级、consistency evidence 和 `global_track_id` 均未改变。

新增操作计数分别记录候选对、量测模型构造、投影构造、创新求解、雷达航迹状态和雷达观测状态
构造。冻结输入中 candidate pair 和 innovation solve 均保持 371,054；measurement model build
为 `16,457 -> 82`，projection build 为 `16,457 -> 14,648`，radar 状态构造和 16,653 次
`GlobalTrack` 物化均保持。86 个逐扫描语义哈希、终态航迹哈希和 consistency evidence 哈希
完全一致，在线 truth 使用为 0。

模块级纯融合墙钟为 `10.792 s -> 8.635 s`，本机单次 1.25 倍。专项
`10 passed in 10.33s`，D1 全量 `161 passed in 38.02s`。性能单测不使用墙钟阈值；验收依赖
确定性操作计数和输出哈希。后续 clean 三 seed 全栈已经复跑，AirSim 尚未复跑。

### 第一阶段增量后验与发布快照

本轮在 `FusionAdapter` 中实现逐航迹增量后验检查点和每扫描公共发布审计快照。检查点记录观测
身份、量测/到达排序键、滤波后验、归一化创新平方和 gate 结果。正常顺序扫描直接复用匹配前缀；
窗口内乱序只失效插入点及之后的后缀；固定滞后重基、起始观测变化和检查点前 OOSM 清空相关
缓存。缓存命中仍执行 consistency evidence 捕获，以当前 replay revision 重建证据。

发布阶段先生成一份 association、latency 和 sensor-health 上下文，再复制到当前扫描的全部
`GlobalTrack`。每条航迹仍独立物化，state/covariance 与内部后验不共享数组。新增四项确定性
计数：实际 replay filter update、checkpoint reuse、global-track materialization 和
sensor-health snapshot build。

冻结 seed 42000/200v200 输入包含 86 个扫描、2,051 条匿名观测，SHA-256 为
`38d24429711b67d612f2f398478386ebf0df690fae55cd9dcc36434aac4fb078`。未缓存参考与优化路径
的逐扫描语义、最终 201 条航迹和 consistency evidence 哈希一致；filter update
`93,234 -> 1,797`，health snapshot `16,653 -> 86`。墙钟 `34.701 s -> 9.073 s`，本机单次
3.82 倍。该结果只关闭 D1-owned 冻结输入热点。

## 历史权威增量（2026-07-16）

本轮新增 `local_image_track.py` 的保守适配算法。输入是 main-owned
`LocalImageTrackObservation`，输出是 `SensorObservation | None`：

```text
track_state == lost
  -> None

track_state == measured
  -> revalidate timestamps/confidence/center/bbox/2x2 covariance/metadata identity
  -> SensorObservation(modality=eo, frame_id=pixel)
  -> explicit lineage=(local_image_track, source_track_key, measurement_time)
```

visible 与 infrared 不拆成新的内部 modality，而是统一使用 EO 量测模型，并在
`metadata.spectral_band` 区分。默认 observation ID 显式编码 sensor、stream、local epoch、
local track ID 和量测时刻；因此同一本地样本重投递生成同一 ID/lineage，新量测时刻仍保持
唯一。输入 metadata 深复制并保留 backend、batch 与相机等在线审计字段；global/truth identity
键在任意嵌套层级触发拒绝。

融合器接受 EO 更新后，将 namespaced `source_track_key` 去重累积到
`GlobalTrack.metadata.source_track_ids`。该集合用于来源审计而非规范身份，算法不读取它来
生成、选择或改写 `global_track_id`。2026-07-16 的无随机 seed 构造验证为专项 13/13、D1
全量 111/111；没有运行 AirSim，也没有新增 RMSE/NIS/NEES 或 runtime 性能结论。

## 历史权威增量（2026-07-15）

最新真实 AirSim 证据覆盖 M5N2 baseline 10 case 和 candidate 10 case，共 20 case、3,805 个
main-bus tick。D1 fusion 的 mean/P95/max 为 `320.00/451.46/1234.88 ms`，明显主导
main-bus 内层 `349.34/487.40/1305.99 ms`，所以当前算法实施缺口是 fixed-lag/batch 路径在
真实多航迹、多观测循环中的运行时预算，而不是缺少接口级批处理函数。

当前实施约束保持不变：

- 以 `measurement_timestamp` 更新，以 `arrival_timestamp` 审计传输和乱序；
- 每条正式观测和每条航迹必须携带合法 covariance；
- 工作状态在 NED 表达，AirSim truth identity/state 不进入在线估计；本批计数均为 0；
- 性能优化只允许复用预测/雅可比/历史状态和减少重复终结回放，不允许通过观测降采样、时间
  伪同步或 covariance 人为收紧绕过正确性合同。

本批没有输出可用 NIS、NEES 或 RMSE，故不用于选择 EKF/UKF/IMM，也不用于关闭真实
sensor-specific covariance 标定。M5N2 之外仅额外完成 1 个被排除的 `png_ttc_2v2_seed001`，
dropout 为 0；二者不构成算法比较证据。后文历史算法与实现记录继续保留。

## 1. 文档目的与模块边界

第一研究模块的项目代号为 D1。D1 将异步雷达、声学、光电和可选合成激光雷达观测统一到
同一时间基准和坐标工作空间，输出带完整不确定度证据的 `GlobalTrack`。它解决的是“不同
传感器的观测如何形成可供后续处理的航迹候选”，不负责下列事项：

- 不承担第二研究模块（D2）的密集多目标身份保持；
- 不决定第三研究模块（D3）的资源分配；
- 不决定第四研究模块（D4）的主动或被动降级；
- 不执行第五研究模块（D5）的末端视觉绑定；
- 不计算第七研究模块（D7）的导引控制量；
- 不提供真实飞控、硬件驱动、火控、毁伤或自动处置接口。

当前默认在线研究路径是 NumPy 数值计算库实现的常速度扩展卡尔曼滤波、基础门控关联和固定
滞后乱序量测回放。代码按输入数组长度处理目标与观测，不把 2 对 2 或 5 对 5 写成算法常量。

## 2. 术语、缩写与代码名称

本文首次使用的英文缩写统一在此定义，后文直接使用缩写或代码名称。

| 中文名称 | 英文全称与缩写 | 本文含义 |
| --- | --- | --- |
| 北-东-地坐标系 | North-East-Down，NED | D1 的状态估计和跨模块工作空间 |
| 东-北-天坐标系 | East-North-Up，ENU | 外部工具可能使用的本地切平面坐标 |
| 世界大地测量系统 1984 | World Geodetic System 1984，WGS84 | 外部地理参考，不直接作为滤波状态坐标 |
| 扩展卡尔曼滤波 | Extended Kalman Filter，EKF | 当前默认非线性状态估计器 |
| 无迹卡尔曼滤波 | Unscented Kalman Filter，UKF | 尚未进入默认实现的可选对照 |
| 交互多模型 | Interacting Multiple Model，IMM | 尚未进入默认实现的多运动模型路线 |
| 常速度模型 | Constant Velocity，CV | 当前默认运动模型；不是 AirSim 计算机视觉模式 |
| 常加速度模型 | Constant Acceleration，CA | 后续运动模型对照项 |
| 协调转弯模型 | Coordinated Turn，CT | 后续运动模型对照项 |
| 乱序量测 | Out-of-Sequence Measurement，OOSM | 到达顺序晚于物理量测时间顺序的观测 |
| 光电传感器 | Electro-Optical sensor，EO | 当前以像素中心和检测框表达的视觉观测 |
| 激光雷达 | Light Detection and Ranging，LiDAR | 当前仅有合成三维位置观测路径 |
| 归一化创新平方 | Normalized Innovation Squared，NIS | 不使用真值的创新一致性和门控统计量 |
| 归一化估计误差平方 | Normalized Estimation Error Squared，NEES | 需要离线真值的状态一致性指标 |
| 均方根误差 | Root Mean Square Error，RMSE | 需要离线真值和正确身份映射的误差指标 |
| 轻量故障检测、隔离与恢复 | Fault Detection, Isolation and Recovery Light，FDIR-light | 输出健康证据，不执行硬件隔离 |
| 加权最小二乘 | Weighted Least Squares，WLS | 已确认同一身份后的多视线定位助手 |
| 协方差交集 | Covariance Intersection，CI | 未知交叉相关性下的保守状态融合助手 |
| 视线 | Line of Sight，LOS | 观察者到目标的方向射线 |
| 逗号分隔值 | Comma-Separated Values，CSV | 可审计表格回放格式 |
| 逐行存储的 JavaScript 对象表示法 | JSON Lines，JSONL | 观测和运行日志回放格式 |
| JavaScript 对象表示法 | JavaScript Object Notation，JSON | 清单、配置和摘要的结构化文本格式 |
| 应用程序编程接口 | Application Programming Interface，API | 模块对外的 Python 调用接口 |
| 命令行界面 | Command-Line Interface，CLI | 脚本执行入口 |
| 机器人操作系统第二版 | Robot Operating System 2，ROS 2 | 后置工程消息与坐标变换运行环境 |
| 第二代坐标变换库 | Transform Library Version 2，tf2 | ROS 2 中维护坐标变换关系的库 |
| 开源计算机视觉库 | Open Source Computer Vision Library，OpenCV | 后置相机标定和几何后端候选 |
| 佐治亚理工平滑与建图库 | Georgia Tech Smoothing and Mapping，GTSAM | 后置图优化几何后端候选 |

AirSim 是微软开源的无人系统仿真平台；本文中的 AirSim 数据只作为仿真输入和离线评分证据。
`SensorObservation`、`GlobalTrack` 等名称是当前 Python 数据类或字段名，不属于英文缩写。

## 3. 软件结构与实施职责

D1 的主要实现文件如下。

| 文件 | 当前职责 |
| --- | --- |
| `src/d1_sensor_fusion/types.py` | 观测、航迹、质量、健康、协同定位和回放摘要数据合同 |
| `src/d1_sensor_fusion/motion.py` | 常速度状态转移、过程噪声和角度残差处理 |
| `src/d1_sensor_fusion/observations.py` | 雷达、声学、EO、合成 LiDAR 观测模型和默认协方差 |
| `src/d1_sensor_fusion/local_image_track.py` | 本地图像航迹到 EO/pixel 观测的 fail-closed 适配与来源谱系 |
| `src/d1_sensor_fusion/ekf.py` | EKF 预测、数值雅可比、Joseph 协方差更新 |
| `src/d1_sensor_fusion/fusion.py` | `FusionAdapter`、关联、OOSM 回放、分级和健康审计 |
| `src/d1_sensor_fusion/replay.py` | JSONL/CSV 读写、版本化回放和受治理序列化 |
| `src/d1_sensor_fusion/airsim_replay_freeze.py` | 真实 AirSim 持久化输入冻结和在线真值隔离 |
| `src/d1_sensor_fusion/quality.py` | 协方差增长率和区域时间窗口汇总 |
| `src/d1_sensor_fusion/recon_cue.py` | 给机动高空侦察节点的粗指向摘要 |
| `src/d1_sensor_fusion/cooperative.py` | 可选多观察者方位 WLS 和 CI 数值助手 |
| `src/d1_sensor_fusion/long_replay.py` | 可复现长时异步合成回放和摘要 |
| `src/d1_sensor_fusion/p2_benchmark.py` | 隔离的滤波器和一致性指标对照入口 |

main 全局编排模块负责 AirSim 启动、场景重置、回合顺序、跨模块消息路由和结果收集。D1 只
负责上述数据合同和算法，不在模块内部启动 AirSim，也不控制 D2-D7。

## 4. 统一输入合同

### 4.1 `SensorObservation`

统一观测数据类位于 `types.py`，关键字段如下。

```python
SensorObservation(
    observation_id: str,
    sensor_id: str,
    modality: str,
    measurement_timestamp: float,
    arrival_timestamp: float,
    frame_id: str,
    measurement: np.ndarray,
    covariance: np.ndarray | None,
    classification_hint: str | None,
    confidence: float,
    quality_flags: tuple[str, ...],
    metadata: dict[str, Any],
    source_node_id: str | None,
    target_node_id: str | None,
    relay_node_id: str | None,
    link_type: str | None,
    sent_timestamp: float | None,
    received_timestamp: float | None,
    payload_kind: str | None,
    stale_after_s: float | None,
    source_support: dict[str, int] | None,
    timestamp_uncertainty_s: float | None,
)
```

硬性合同如下。

1. `measurement_timestamp` 和 `arrival_timestamp` 必须同时存在且为有限数。
2. `measurement_timestamp` 表示物理采样时刻；`arrival_timestamp` 表示融合节点接收时刻。
3. 每条严格受治理观测必须携带与量测维度匹配的协方差。
4. `radar`、`acoustic` 和 `lidar` 只接受 `frame_id="ned"`；`eo` 只接受
   `frame_id="pixel"`。
5. 外部 WGS84、ENU、机体系和传感器体系必须在进入融合器前转换，或提供构成观测模型所需
   的完整外参。
6. `classification_hint` 是类别提示，不是规范目标身份。
7. 通信字段描述来源、转发和新鲜度，不会自动改变任务分配或控制状态。

数据类会规范化通信元数据和时间戳不确定度。秒和毫秒形式的时钟偏差、抖动或不确定度会归并
为 `timestamp_uncertainty_s`。若到达时刻早于量测时刻，异常差值也会计入时间不确定度证据。

### 4.2 来源谱系与重复抑制

`source_lineage_key` 用于识别“同一源载荷经不同中继重复到达”的情况。优先使用显式
`source_lineage_key` 或 `lineage_id`；否则组合源节点、传感器、模态、载荷类型、源序号和
载荷指纹。`FusionAdapter` 默认启用 `source_deduplication=True`，重复载荷只增加审计计数，
不能再次执行滤波更新并虚假缩小协方差。

来源谱系只用于去重和审计。它不能替代 D2 的目标身份关联，也不能把不同观察者的相关估计
当成独立信息重复融合。

### 4.3 在线身份和真值隔离

在线 D1 输入不得携带或使用 AirSim actor 名称、对象名称、真值目标编号或真值位置来选择
航迹。当前 `FusionAdapter` 保留 `use_truth_hints_for_association` 测试兼容参数和部分旧仿真
元数据兼容代码，但受治理回放、main 运行总线和正式在线验证必须保持该参数为 `False`，且在
进入在线记录前递归移除身份真值。

真值只允许写入 evaluator-only truth sidecar，即“仅评估器可见的真值旁路文件”。D2 和
第六研究模块（D6）在在线算法完成后读取该旁路计算身份切换、RMSE 或 NEES。任何真值进入
在线观测、`GlobalTrack`、D5 或 D7 都属于合同违规。

## 5. 输出合同与质量证据

### 5.1 `GlobalTrack`

输出状态为 NED 下的六维向量：

```text
x = [p_n, p_e, p_d, v_n, v_e, v_d]^T
```

其中前三项是北、东、地位置，后三项是对应速度。`GlobalTrack` 同时携带：

- `global_track_id`：D1 候选航迹编号；进入规范身份链后由 D2 维护稳定身份；
- `state`：六维状态均值；
- `covariance`：6×6 状态协方差；
- `timestamp`：状态有效时刻；
- `track_level`：粗略、稳定、可交接或枚举中的丢失等级；
- `source_support`：各传感器模态的累计支持；
- `identity_likelihood`：类别提示的归一化权重，不是敌我结论；
- `last_nis`：最近创新一致性证据；
- `metadata`：时间、帧、来源、健康、时延和协方差治理审计。

发布元数据至少说明 `frame_id="ned"`、`valid_at`、`published_at`、`hits`、最近量测和到达
时刻、延迟补偿状态、来源支持、重复计数、时延审计和传感器健康摘要。

### 5.2 衍生摘要

D1 还提供以下只读证据，不直接作出分配或降级决定。

- `TrackUncertaintySummary`：位置/速度协方差迹、水平 95% 误差尺度、量测年龄、来源多样性、
  NIS、协方差限制原因、增长率和交接准备度；
- `SensorHealthSummary`：每个传感器的观测、拒绝、重复、OOSM、陈旧、低质量、协方差异常、
  期望时延偏差和恢复状态；
- `LatencyAuditSummary`：融合回放、OOSM、陈旧、重复、最大/平均时延和最大回放观测数；
- `FusionQualityRegionSummary`：同一覆盖单元内的航迹数量、质量分布、时延、协方差和来源缺口；
- `FusionQualityRegionWindowSummary`：多个时刻的区域趋势、增长率和时延窗口统计；
- `ReconCueSummary`：给机动高空侦察节点的粗位置、协方差、时间戳和来源摘要。

这些摘要是 D3 成本、D4 仲裁、D5 投影门限和 D6 评估的输入证据。D1 不输出
`active_degrade_recommendation`，也不直接改变中心、二级或分布式模式。

## 6. 时间处理与固定滞后回放

### 6.1 双时间戳语义

量测时延定义为：

```text
latency = arrival_timestamp - measurement_timestamp
```

通信时延在同时存在 `sent_timestamp` 和 `received_timestamp` 时定义为：

```text
communication_latency = received_timestamp - sent_timestamp
```

量测时刻决定状态在哪一时刻更新；到达时刻只决定消息何时可见、回放顺序和延迟审计。把二者
合并会让迟到雷达量测在错误时刻修正当前状态，造成系统性位置偏差和过度自信。

### 6.2 OOSM 处理流程

`FusionAdapter.process()` 按到达顺序接收观测，默认执行以下步骤：

1. `_prepare_observation()` 补齐或限制量测协方差，记录时间不确定度和质量放大原因；
2. 更新当前到达时刻和时延、陈旧、OOSM、传感器健康计数；
3. 将现有航迹预测到当前到达时刻；
4. 按来源谱系拒绝重复载荷；
5. 在观测的 `measurement_timestamp` 计算关联分数；
6. 将新观测插入航迹历史，按“量测时刻、到达时刻、观测编号”确定性排序；
7. 从最早雷达初始化状态开始，逐条预测到各量测时刻并更新；
8. 将回放后的状态重新传播到当前发布时刻；
9. 裁剪固定滞后窗口内非必要旧观测，保留初始化观测；
10. 发布当前 `GlobalTrack` 和审计摘要。

默认 `buffer_horizon=6.0 s`，`bucket_size=0.1 s`。固定滞后窗口必须覆盖预期最大传感器延迟；
超出窗口的行为需通过陈旧计数和场景配置审计，不能假定任意长延迟都能无损恢复。

设置 `latency_compensation=False` 时，融合器把量测时刻替换为到达时刻，形成延迟补偿消融
基线。该开关用于对比，不是推荐在线配置。

## 7. 坐标转换与空间基准

D1 内部统一使用 NED：`x` 轴指北、`y` 轴指东、`z` 轴向下。推荐外部链路为：

```text
WGS84 -> 本地 ENU -> NED -> 传感器观测模型
机体系/传感器体系 -> 标定外参 -> NED
NED 目标状态 -> 相机外参和内参 -> EO 像素平面
```

实施规则如下。

1. WGS84 只作为外部参考；应固定局部原点后转换为本地切平面。
2. 雷达和声学桥接器先将传感器位置、姿态和方向转换到 NED。
3. EO 保留像素量测，但必须提供相机 NED 位置、世界到相机旋转和内参。
4. 相机默认模型只是测试后备值；真实回放必须携带场景实际标定值和版本。
5. 不允许把像素中心、声学方位或检测器编号直接解释为三维目标位置或规范身份。
6. 当前 D1 未接入机器人操作系统第二版（Robot Operating System 2，ROS 2）的坐标变换库
   `tf2`；工程部署中的动态坐标树仍属于后置适配。

## 8. 状态模型与滤波算法

### 8.1 常速度预测

当前状态转移为：

```text
x_k = F(dt) x_(k-1) + w_k

F(dt) = [[I3, dt I3],
         [03, I3   ]]
```

过程噪声采用白加速度谱密度近似：

```text
Q(dt) = q [[dt^4/4 I3, dt^3/2 I3],
           [dt^3/2 I3, dt^2 I3  ]]
```

默认 `process_noise=6.0`。仿真真值可以转弯或加速，但当前滤波器不切换模型，只依靠过程噪声
吸收机动误差。因此高动态目标的状态滞后和协方差一致性必须通过后续多模型基准验证。

### 8.2 EKF 更新

对非线性观测 `z=h(x)+v`，当前实现执行：

```text
x_minus = F x
P_minus = F P F^T + Q
y = wrap(z - h(x_minus))
S = H P_minus H^T + R
K = P_minus H^T S^(-1)
x_plus = x_minus + K y
P_plus = (I-KH) P_minus (I-KH)^T + K R K^T
NIS = y^T S^(-1) y
```

`H` 由数值雅可比计算。角度残差使用包角处理，避免正负圆周边界跳变。协方差采用 Joseph
稳定形式更新，并在矩阵求解失败时使用伪逆后备路径。

### 8.3 默认选型理由

当前使用 NumPy EKF 的原因是状态维度低、实现可审计、依赖少，且适合大量随机种子回放。
UKF、IMM、FilterPy 和 Stone Soup 并未替换默认路径。它们只有在同一冻结输入上证明身份、
一致性或时延收益，并满足运行预算后，才可能进入后续升级评审。

## 9. 各传感器观测模型

### 9.1 雷达

雷达量测为：

```text
z_radar = [range, azimuth, elevation, radial_velocity]^T
```

设目标与雷达的 NED 相对向量为 `r=p-s`，则：

```text
range = ||r||
azimuth = atan2(r_e, r_n)
elevation = atan2(-r_d, sqrt(r_n^2+r_e^2))
radial_velocity = v dot (r / ||r||)
```

缺少显式协方差时，默认标准差按距离增长：

```text
sigma_range = 2.0 + 0.012 * range
sigma_azimuth = deg2rad(0.25 + 0.0008 * range)
sigma_elevation = deg2rad(0.35 + 0.0010 * range)
sigma_radial_velocity = 0.35 + 0.0015 * range
```

这些系数由 `RadarCovarianceConfig` 管理，可由场景配置覆盖。当前只有雷达可初始化新航迹，
因为它能提供三维位置骨架和径向速度。雷达初始化不代表完整三维速度已被直接观测，未观测的
切向速度以较大初始协方差表达。

### 9.2 声学

声学量测只包含水平粗方位：

```text
z_acoustic = [azimuth]
azimuth = atan2(r_e, r_n)
```

默认角度标准差为：

```text
sigma_deg = 2.5 + 8.0 * (1 - confidence)
```

单个声学方位不包含距离和高度信息，不能独立初始化三维航迹，也不能单独把粗略航迹提升为
可交接航迹。声纹或类别提示只进入 `classification_hint` 和来源支持，不构成敌我身份判定。

### 9.3 EO

当前 EO 量测是检测框中心：

```text
z_eo = [u_center, v_center]^T
p_camera = R_world_to_camera (p_ned - camera_position_ned)
u = fx * x_camera / z_camera + cx
v = fy * y_camera / z_camera + cy
```

相机模型支持嵌套或扁平元数据，包含位置、世界到相机旋转、焦距、主点和图像尺寸。缺少显式
像素协方差时，`eo_covariance_from_bbox()` 根据检测框大小和置信度生成后备值：置信度越低，
误差越大；`occluded` 和 `small_bbox` 标志继续放大协方差。

EO 只提供投影方向约束，不把单帧检测框恢复成无协方差三维点。原始图像和视频不由 D1 保存；
D1 接收的是检测框、相机参数、时间戳、质量和协方差。

### 9.4 合成 LiDAR

合成 LiDAR 量测为 NED 三维位置：

```text
z_lidar = [p_n, p_e, p_d]^T
h_lidar(x) = x[0:3]
```

默认标准差为：

```text
sigma_xy = (0.35 + 0.0025 * distance) / confidence
sigma_z = (0.50 + 0.0035 * distance) / confidence
```

该路径用于 dry-run 和回放合同测试，不表示真实 LiDAR 驱动或 AirSim LiDAR 插件已经接入。
LiDAR 当前不能创建新航迹，只能更新已有航迹。

## 10. 量测关联、初始化与生命周期边界

### 10.1 D1 基础关联

D1 的 `_associate()` 对每条观测和已有航迹计算量测时刻的分数：

- 雷达使用三维位置差及观测、预测位置协方差构成马氏距离；
- 声学、EO 和 LiDAR 使用对应观测创新的 NIS；
- 最小分数不超过 `association_gate` 时接受，否则尝试新建航迹；
- 非雷达观测无法初始化时被拒绝并记录 `unsupported_track_initializer`。

默认 `association_gate=40.0`。该关联器只是融合前端的轻量基线，不替代 D2 的全局最近邻、
联合概率数据关联或多假设跟踪。密集交叉场景中的规范身份、身份切换计数和航迹连续性归 D2。

### 10.2 身份所有权

D1 创建的 `global_track_001` 等编号是融合候选编号。规范 `global_track_id` 的跨时保持由 D2
确认；D5 和 D7 禁止自行改写。协同 WLS/CI 也要求调用方先提供由 D2 确认的同一规范身份，
不能利用几何助手绕过身份确认。

### 10.3 当前生命周期限制

`TrackLevel` 枚举包含 `LOST`，但默认 `_classify()` 只输出 `COARSE`、`STABLE` 和
`HANDOVER`。当前没有完整的超时丢失、删除、合并、拆分或带迟滞质量状态机。因此长期目标
消失时，上层运行总线和后续模块必须显式治理，不能把枚举存在误写为完整生命周期已实现。

## 11. 协方差治理与轻量健康诊断

### 11.1 量测协方差

`_prepare_observation()` 对每条观测执行：

1. 根据模态和元数据生成缺省协方差；
2. 验证维度、有限性和对称性；
3. 对对角值施加模态相关下限和统一上限；
4. 对不合理成对相关项限幅；
5. 根据低置信度、杂波、遮挡或低信噪比记录 `covariance_scale_reason`；
6. 将限制原因写入观测和后续航迹元数据。

严格受治理回放要求原始协方差存在且满足合同；普通运行入口允许使用后备模型是为了原型兼容，
不应掩盖真实传感器未标定的问题。

### 11.2 状态协方差

默认六维状态协方差对角下限为：

```text
[0.25, 0.25, 0.25, 0.04, 0.04, 0.04]
```

位置上限为 `1e6`，速度上限为 `1e4`。长时间外推、量测异常或限制动作都会写入
`covariance_limit_reasons`。当前普通入口主要执行有限性、对称性、对角和相关项治理，尚未
形成统一特征值投影和真实统计一致性保证。

### 11.3 FDIR-light

传感器健康摘要统计：

- 重复、拒绝、OOSM 和陈旧观测；
- 低质量、异常协方差和时间戳不确定度；
- 实际时延相对 `SensorTimingExpectation` 的超限；
- 预期或意外 OOSM；
- 故障原因、隔离提示和故障后的名义样本数量。

达到拒绝阈值只产生健康和隔离建议，不会关闭真实传感器、切断通信或触发 D4 降级。恢复状态
同样是审计证据，不是硬件认证。

## 12. 航迹质量等级与交接准备度

水平 95% 误差尺度由位置协方差左上 2×2 子矩阵计算：

```text
a95 = sqrt(chi2_2_0.95 * max_eigenvalue(P_xy))
chi2_2_0.95 = 5.991464547...
```

当前分类规则是：

- `handover`：`a95 <= 12 m`、至少两类传感器支持、命中不少于 8 次、近期 NIS 通过率不低于
  0.55；
- `stable`：`a95 <= 30 m`、命中不少于 3 次、近期 NIS 通过率不低于 0.45；
- `coarse`：其他情况。

`handover_readiness` 被限制在 `[0,1]`，取协方差、量测新鲜度、来源多样性、NIS 和等级得分
中的最小值。它是保守质量证据，不是行动授权。单帧高协方差、等级回退或 OOSM 不应直接触发
D4 主动降级；D4 必须结合持续时间、D2 身份风险、D3 计划状态、D5 末端冲突和指挥控制健康。

质量等级当前没有独立迟滞，因此阈值附近可能往返变化。D3/D4 应在各自决策层实施版本、驻留
时间和恢复门限，D1 不越权实现任务状态迟滞。

## 13. 受治理回放与证据链

### 13.1 一般 JSONL/CSV 回放

`replay.py` 支持版本化 JSONL、兼容旧 Blocks JSONL 和最小 CSV 读写。回放记录保留：

- 双时间戳和量测协方差；
- 规范观测帧和 NED 融合工作空间；
- 通信、相机、覆盖单元和来源谱系；
- 可用的处理/发布时间、健康和质量元数据。

旧格式可读取不代表满足严格证据合同。正式比较应使用受治理入口。

### 13.2 受治理序列化

`serialize_governed_replay()` 返回：

```text
{
  "manifest": {...},
  "records": [...]
}
```

清单结构版本为 `d1.governed_replay_manifest.v1`，记录观测结构、NED 工作空间、场景/配置标识
及版本、摘要、随机种子、时间范围、覆盖单元和每条观测的不透明来源谱系。严格路径会在返回前
验证整个批次：双时间戳必须有限且有序，协方差必须匹配量测维度，覆盖单元和来源谱系必须存在，
所有记录必须可安全序列化。

在线记录递归删除真值、actor 和对象身份。`serialize_offline_governed_replay()` 是唯一显式
离线入口，将评估标签置于独立 `offline_truth`，不会把标签恢复到在线元数据。

### 13.3 AirSim 持久化输入冻结

`freeze_airsim_replay_payloads()` 和对应 CLI 不连接 AirSim 软件开发工具包，只读取 main 已经
落盘的 JSON/JSONL。输出为：

- `manifest.json`；
- `sensor_observations.jsonl`；
- `offline_truth.json`；
- `summary.json`。

冻结器只为真实存在的量测创建观测。遮挡、漏检或节点退出事件若没有量测，只记录事件，不
伪造传感器数据。在线观测编号改为不透明序号；真值编号和 NED 真值位置只进入旁路。

捕获端必须显式声明场景版本、配置版本、随机种子、`target_spacing_m` 和 `evidence_path`。
目标间距以捕获声明为权威，不从真值位置反推；调用参数、不同载荷声明或证据摘要冲突时拒绝
冻结。清单和真值旁路通过来源摘要绑定。

同一 `(truth_id, timestamp)` 的离线真值样本确定性去重：有位置样本覆盖仅身份样本；两个位置
在 `1e-6 m` 容差外不一致时拒绝冻结；缺失位置不插值、不外推。

### 13.4 长回放构造器

`build_long_replay_scenario()` 可生成任意配置目标数的 60 秒级合成挑战，包含雷达距离噪声、
声学粗方位、EO 像素观测、交叉杂波、遮挡、延迟雷达 OOSM 和中继重复。在线观测不含稳定
目标槽位，真值轨迹只在独立旁路。该构造器验证回放和审计链，不替代真实传感器数据。

## 14. 可选协同定位与保守航迹融合

### 14.1 多观察者方位定位

`localize_bearing_observation_group()` 对已经由 D2 确认为同一 `global_track_id` 的 2..N 条
标定方位射线执行中心化 WLS。每条 `CooperativeBearingObservation` 携带：

- 双时间戳；
- 平台 NED 位置和机体到 NED 旋转；
- 传感器安装平移和旋转；
- 传感器系单位方位向量；
- 方位、平台位姿、外参和时间不确定度协方差；
- 不可变观察者来源谱系。

助手拒绝观察者不足、基线过短、LOS 近共线、时间偏斜过大、缺少必需协方差、信息矩阵病态、
负深度或残差过大。输出保留所有量测/到达时刻、交会角、信息矩阵条件数、残差、协方差膨胀
和明确拒绝原因。

### 14.2 协方差交集

`covariance_intersection()` 将多个六状态 NED 估计传播到共同时间，在未知交叉相关性时搜索
保守权重。它按消息编号和来源谱系去重，保持调用方给定的规范身份，并避免把相关信息按独立
估计简单相加。

WLS 和 CI 当前是已实现的独立数值基础，但没有接入默认 `FusionAdapter` 或真实多节点运行
总线。它们不执行 D2 关联、不实现分布式共识，也不证明 3->2->1 观察节点退出时的端到端性能。

## 15. 跨模块接口和消费方式

```mermaid
flowchart LR
    S[雷达/声学/EO/合成LiDAR观测] --> D1[第一研究模块融合]
    D1 -->|GlobalTrack与协方差| D2[第二研究模块身份关联]
    D1 -->|质量与时延摘要| D3[第三研究模块资源分配]
    D1 -->|区域质量与侦察粗指向| D4[第四研究模块降级协同]
    D2 -->|规范global_track_id| D5[第五研究模块末端视觉关联]
    D1 -->|NED状态与协方差| D5
    D1 -->|中段状态证据| D7[第七研究模块导引]
    D1 -.日志与旁路真值.-> D6[第六研究模块离线评估]
```

### 15.1 D2

D2 消费 D1 航迹候选、状态、协方差、时间和来源证据，维护规范身份并计算身份切换。D1 的
最近邻门控不能替代 D2；离线真值只有 D2 关联完成后才能用于评分。

### 15.2 D3

D3 可把位置/速度协方差、量测年龄、等级和交接准备度加入分配成本。高不确定度应产生惩罚或
更强迟滞，但不应由 D1 直接取消分配。

### 15.3 D4

D4 聚合 `TrackUncertaintySummary`、区域窗口、传感器健康和时延审计，区分节点失效导致的
被动降级与态势质量不足导致的主动降级。D1 只提供证据；二级节点接管、完全分布式协商、租约
和仲裁均由 D4 管理。

### 15.4 D5

D5 使用 NED 状态、完整协方差、双时间戳和相机标定，将规范航迹投影到各相机像素平面。
D5 的局部检测或多目标跟踪编号不得回写 D1/D2 的 `global_track_id`。D5 反馈可以作为质量
冲突证据，但不能让 D1 利用局部真值重新绑定。

### 15.5 D6

D6 只读消费在线记录、质量摘要和离线真值旁路，计算 RMSE、NIS、NEES、时延、健康和区域
趋势。指标缺少真值、身份映射、协方差或分母时必须标为不可用，不能填零。

### 15.6 D7

D7 使用 D1/D2 的中段状态和协方差支撑位置比例导引，并在 D5 与 D3/D4 合同一致时考虑末端
视觉切换。D1 不计算导引律，也不决定控制许可。

## 16. 默认参数与调参原则

| 参数 | 当前默认值 | 实施含义 |
| --- | ---: | --- |
| `process_noise` | 6.0 | 机动吸收能力；过小会滞后，过大会膨胀协方差 |
| `bucket_size` | 0.1 s | 时间离散桶和摘要对齐粒度 |
| `buffer_horizon` | 6.0 s | 固定滞后历史窗口 |
| `stable_threshold_m` | 30.0 m | 稳定等级水平误差门限 |
| `handover_threshold_m` | 12.0 m | 可交接等级水平误差门限 |
| `association_gate` | 40.0 | 基础马氏距离/NIS 关联门限 |
| `latency_compensation` | `True` | 在量测时刻更新并重传播 |
| `source_deduplication` | `True` | 抑制中继重复载荷 |
| `long_extrapolation_s` | 3.0 s | 记录长外推协方差原因的门限 |
| `timestamp_uncertainty_fault_s` | 0.05 s | 时间不确定度健康告警门限 |
| `sensor_isolation_reject_threshold` | 3 | 生成隔离提示的连续拒绝基线 |

调参必须使用版本化场景、冻结输入和 D6 统计。不能为了降低单次 RMSE 人为压小协方差；不能
用单帧表现设定 D4 降级门限；不能用离线真值帮助在线关联。真实雷达距离曲线、相机检测框误差、
声学置信度和传感器时延应分别标定，不能共用一个经验放大系数。

## 17. 当前实施流程

典型离线或 main 运行总线调用链如下。

1. main 或传感器适配器构造满足合同的 `SensorObservation`。
2. 严格运行先通过受治理序列化或 AirSim 持久化冻结，建立清单、来源和真值旁路。
3. 观测按 `arrival_timestamp` 输入 `FusionAdapter.process()`。
4. D1 完成协方差准备、健康审计、基础关联、雷达初始化和固定滞后回放。
5. `global_tracks()` 发布当前航迹候选。
6. `track_uncertainty_summaries()`、`sensor_health_summaries()`、
   `latency_audit_summary()` 和 `region_quality_summaries()` 发布质量证据。
7. D2 维护规范身份，D3/D4/D5/D7 按各自合同消费，不反向改写 D1 航迹身份。
8. D6 在回合结束后读取在线日志和隔离真值，输出可用性、指标和失败原因。

基础测试命令为：

```bash
PYTHONPATH=research_modules/d1_sensor_fusion/src \
pytest -q research_modules/d1_sensor_fusion/tests
```

长回放和隔离基准分别由 `scripts/run_long_replay.py`、
`scripts/run_p2_isolated_benchmark.py` 调用。文档更新不改变这些入口。

## 18. 当前能力状态

### 18.1 默认主线已实现

- NED 六状态、观测和航迹协方差；
- 双时间戳、时间不确定度和固定滞后 OOSM 回放；
- 雷达、声学、EO 和合成 LiDAR 观测模型；
- NumPy CV/EKF、数值雅可比和 Joseph 协方差更新；
- 雷达初始化、基础马氏距离/NIS 关联和来源谱系去重；
- 粗略、稳定和可交接质量分级；
- 协方差限制原因、FDIR-light、时延和区域质量摘要；
- JSONL/CSV 回放、受治理清单、AirSim 输入冻结和在线真值隔离；
- 不写死 2 对 2、5 对 5或固定目标数。

### 18.2 已实现但不在默认主线

- 2..N 个已确认同一身份观察者的方位 WLS；
- 未知交叉相关性的 CI；
- 合成长回放和隔离滤波评分；
- 旧 Blocks JSONL 兼容读取；
- `use_truth_hints_for_association` 测试兼容参数。该参数严禁用于受治理在线验证。

### 18.3 尚未实现或尚未闭合

- UKF、IMM-EKF、IMM-UKF 和完整多运动模型主线；
- FilterPy、Stone Soup 可执行后端替换；
- ROS 2 `tf2`、消息同步和真实传感器驱动；
- D1 直连 AirSim 在线传感器；
- 纯 EO/声学新航迹初始化；
- 完整 `lost/dropped` 生命周期、航迹合并/拆分和质量迟滞；
- WLS/CI 的真实多节点运行总线闭环；
- 工程级真实雷达、声学和相机误差曲线冻结。

## 19. 2026-07-13 验证结果

### 19.1 D1 回归基线

当前模块原理和计划记录的 D1 全量回归为 **79 passed**。本次只同步文档，没有修改代码，
因此不重新声称执行全量测试。

### 19.2 真实 AirSim 密集交叉输入

当前严格输入证据包括：

- AirSim 计算机视觉模式，5 个目标；
- 常规相邻间距严格 4 m、紧密相邻间距严格 2 m；
- 每种间距 20 个随机种子，共 40 个真实 AirSim 回合；
- 每回合 51 帧，默认不保存截图；
- evaluator-only truth sidecar 共 10,200 个样本；
- 在线真值泄漏计数为 0；
- 全部冻结记录保留双时间戳、协方差、NED、来源谱系、场景/配置版本、随机种子、目标间距和
  证据路径；
- D6 将 `d1_dense_crossing` 证据标记为可用。

这组结果证明 AirSim 持久化输入冻结、捕获来源校验、真值旁路隔离和下游可消费性已经闭合。
它不证明真实雷达/声学/EO 误差模型已经标定，也不证明 D1 在密集交叉中保持规范身份；后者
属于 D2 的离线评分。

### 19.3 隔离合成基准

六条雷达观测的小型冻结样本曾得到：

- 位置 RMSE 约 0.2335 m；
- 平均 NIS 约 0.0426；
- 平均 NEES 约 0.0651；
- 验证主机相关耗时约 6.9 至 10.1 ms。

该样本规模很小，低 NIS/NEES 反而说明协方差偏保守。它只证明评分路径可运行，不能作为真实
传感器精度或实时性结论。验证环境中的 FilterPy 和 Stone Soup 均不可用，结果明确标记
`unavailable_reason`，没有替换当前 NumPy 路径。

### 19.4 合成长回放证据

默认长回放曾生成 843 条观测、21 个注入雷达 OOSM、6 个被抑制中继重复和 29 个区域窗口，
在线真值泄漏为 0。RMSE/NEES 在缺少 D2 规范身份映射时保持不可用，不由 D1 猜测或填零。

## 20. 剩余限制与下一步实施重点

当前优先级一限制如下。

1. **真实传感器挑战数据不足**：现有严格 4 m/2 m 回放主要验证几何声明、冻结和离线身份
   输入，尚未覆盖有代表性的雷达/声学/EO 漏检、匿名虚警、遮挡、异步采样、特定时延、时钟
   异常和节点退出分布。
2. **长期阈值未冻结**：区域协方差增长、量测新鲜度、交接准备度、NIS/NEES、期望时延和
   健康误报/漏报仍需正常/故障多随机种子对照。
3. **协同定位未运行时闭环**：WLS/CI 助手存在，但 D1/D2 规范身份适配、部分共享谱系、
   真实多节点回放和 3->2->1 节点退出质量退化尚未闭合。
4. **单模型限制**：高机动目标仍由 CV 过程噪声吸收，缺少 CA/CT/IMM 同输入对照。
5. **长期 D6 一致性**：跨场景和长时运行中的结构版本、可用性、证据路径、健康、区域窗口和
   RMSE/NIS/NEES 汇总还需持续校验。
6. **数值治理边界**：普通入口未形成统一半正定特征值投影与统计一致性保证。
7. **生命周期不完整**：默认融合器尚无完整丢失、删除、合并、拆分和状态迟滞。

优先级二只做隔离对照：UKF、IMM、FilterPy、Stone Soup、OpenCV/GTSAM 协同几何后端和
ROS 2 适配均不得在未完成冻结输入、依赖、指标和收益评审前写成默认能力。下一阶段应先由
main 提供版本化真实多随机种子长回放，D1 冻结实际观测并保持真值隔离，再由 D2/D6 完成身份
映射和统计校准。

## 21. 实施结论

D1 已形成一条可执行、可审计的研究链：异构观测先经过双时间戳、坐标和协方差规范化，再由
常速度 EKF 在量测时刻更新，通过固定滞后回放传播到发布时刻，最后输出带质量、来源、健康和
不确定度证据的 `GlobalTrack`。严格回放将在线算法与离线真值物理分离，来源谱系避免中继重复
造成虚假收敛。

当前结论应限定为“科研仿真的融合合同和证据链已经闭合，真实传感器长期标定和高机动、多节点
协同融合仍需验证”。不得把 AirSim 几何回放、合成低误差样本或枚举中存在的状态解释为真实
设备性能、完整身份保持或工程部署能力。

## 22. 在线 Scene Observation 匿名化算法（2026-07-14）

scene-derived observation 的边界流程为：

```text
scene truth
-> sensor projection/noise/miss/occlusion generation
-> SensorObservation[] + separate offline truth labels
-> anonymize_online_observations()
-> assert_online_observations_identity_free()
-> online D1/D2 algorithms
```

匿名化先从调用方 `identity_tokens` 和递归身份 metadata 键收集 token。随后深拷贝观测，删除
truth/actor/object/segmentation/identity/instance 等身份键，清理嵌套字符串、quality flag 和
`classification_hint` 中的 token，并删除原 source-lineage metadata。frame 优先使用已存在的
frame index，否则使用 `measurement_timestamp`；每个 frame 按输入顺序分配不透明 observation
序号。原始 source lineage 在 frame 内按首次出现顺序映射为不透明 source 序号，因此 relay
重复可保持同 lineage，而目标名字不会进入新 ID。

算法只复制而不改写输入，并逐元素复制 measurement/covariance。双时间戳、sensor ID、通信
时间、payload kind、NED/pixel frame、bbox 和相机内外参保持。构造完成后 validator 遍历全部
在线字符串、metadata 容器和 dataclass；任何身份键或已知 token 立即抛出 `ValueError`。对于
未出现在身份键中的任意别名，main/runtime 必须通过 `identity_tokens` 显式声明，不能假设 D1
可从任意字符串自动判断语义身份。

2026-07-14 单测以两组各 2 条仅更换 target/actor/truth 名字的 EO 观测验证全字段严格相等、
数值和 camera geometry 不变、嵌套 key/value、observation ID、classification 和 lineage 无
泄漏；同时验证人工注入泄漏 fail closed，以及原始 observation/offline sidecar 不变。专项
`4 passed`，模块全量 `83 passed`。本实现不改变 dry-run、replay reader、offline serializer
或 evaluator sidecar。

## 23. 无真值关联治理与事件对齐检查点（2026-07-14）

关联阶段为每条已接受观测生成 `(modality, observer_id, scan_id)` 键。同一航迹已消费该键时，
后续候选记为 `observer_scan_conflict`，不更新也不生成新航迹。因为键中含 modality，同一时刻
的 radar 与 acoustic/EO 可分别提供一次支持。雷达严格关联失败后，只对近期、至少已有两次
雷达支持且总命中成熟的航迹计算独立重捕候选；唯一候选可重捕，多候选记为
`ambiguous_radar_birth_suppressed`。非测距更新则以更新前后位置改变量对先验位置协方差计算
马氏分数，异常修正拒绝并记录传感器健康原因。

固定滞后裁剪不再把初始雷达状态长期作为唯一回放起点。算法先找到滞后边界之前最新的已接受
量测时刻，重放到该时刻并保存量测后的后验，再只保留其后的活动窗口。选择量测时刻而不是任意
墙钟边界，是因为当前常随机加速度离散过程噪声不满足任意分段后协方差完全等价；事件对齐可
保持原预测区间和后续更新增益。被裁剪观测进入 archive，仅在合法旧 OOSM 到达时从 origin
重建检查点。输出审计使用 `d1.association_audit.v1`，不包含 actor/truth ID。

专项测试覆盖同扫描去重、唯一雷达重捕、非测距异常修正拒绝、检查点连续性和检查点之前的
声学 OOSM。结果专项 `5/5`、D1 全量 `87/87`；main 的 AirSim runtime 接口回归为
`134/134`。修复后的真实同 seed episode 仍待 main 复跑。

## 24. Observation Covariance 硬门控（2026-07-14）

`validate_sensor_observation_covariance()` 按 modality 固定 measurement/covariance 维度，并依次
检查缺失、数值转换、shape、finite、symmetry 和最小特征值。`FusionAdapter` 使用
`validate_online_sensor_observation()`，额外拒绝带 offline imputation provenance 的对象；
测量模型和雷达初始化不再调用 default covariance 作为缺值回退。合法输入随后仍执行既有低
质量 scale、diagonal floor/ceiling、EKF 更新和 fixed-lag/OOSM replay。

普通 JSONL/CSV reader 对 legacy 和 v1 均要求 covariance，且不再把 flat array reshape 成矩阵。
`migrate_offline_legacy_sensor_observation()` 是唯一缺值兼容入口：根据 radar range、acoustic
confidence、EO bbox/confidence/flags 或 synthetic lidar distance 显式生成研究默认值，并写入
可 JSON 序列化的 model/default provenance。该 observation 在 online/governed/AirSim 路径被
拒绝。

2026-07-14 验收覆盖 missing、non-finite、non-symmetric、non-PSD、wrong shape、显式 legacy
migration、governed round trip、合法 OOSM 和 AirSim freeze 回归；无随机 seed，D1 `92/92`。
这些测试证明合同行为，不证明默认噪声模型已按真实传感器标定。

## 25. 批量观测的惰性状态重放算法（2026-07-14）

逐条模式对每条观测执行两类高成本操作：关联时计算每个候选航迹的 measurement-time 状态，
接受后再把该航迹全历史重放到 current time。同一帧有 `M` 条观测、`N` 条航迹时，未缓存的
关联近似重复执行 `O(MN)` 次历史遍历，接受更新又增加 `O(M)` 次发布重放。

批量实现维护 `_BatchProcessingContext`：

```text
state_cache[(track_id, history_revision, measurement_timestamp)] -> EKFState
dirty_track_ids                                               -> set
checkpoint_dirty_track_ids                                    -> set
```

算法步骤：

1. 先对全批观测执行不修改滤波状态的正式 covariance/online 合同校验；
2. 按调用方输入顺序逐条更新融合器的 current arrival-time cursor、latency/OOSM 和 sensor health；
3. 逐条执行 duplicate、observer scan、关联和非测距修正门控；
4. `_state_at()` 先按 track history revision 查缓存，命中返回副本；
5. 接受量测后写入原始 observation history，并仅增加对应 track revision；
6. 检查点前 OOSM 写入 archive 并标记 checkpoint dirty，只有需要检查点后状态时才重建；
7. 批末按 track ID 排序，每个 dirty track 重放一次到最终 current time、更新 NIS、covariance
   限制和 fixed-lag checkpoint，然后统一生成 `GlobalTrack[]`。

缓存不能跨 batch 保留，避免配置、健康状态或外部调用导致隐式陈旧。输出顺序沿用内部 track
插入顺序，终结处理使用 track ID 排序，因此相同初始状态和相同输入序列产生确定输出。异常
语义与 streaming API 一致：预校验失败不修改状态；处理阶段发生意外异常时已经成功处理的前缀
不会自动回滚。

`FusionBatchResult.tracks` 是批末快照，`summary` 给出接受/拒绝/重复、创建/更新、实际 replay、
cache hit/miss 和合并的发布重放。2026-07-14 的 5 航迹/15 观测测试中 replay 为 95 -> 24；
真实 M5N2 seed-001 前 40 帧 D1-only 为 1267 -> 351，最终数值完全一致。完整 D1 回归为
`98 passed`。

## 26. 可扩展三维扫描级一对一融合算法（2026-07-20）

### 26.1 总线适配与球坐标 covariance 传播

`Scalable3DFusionAdapter` 通过字段合同而非 Python 类型依赖读取 `OnlineSensorBatch`。适配前
递归遍历字段名并拒绝在线身份真值。三维雷达量测为

```text
z = [rho, azimuth, elevation]
```

当 producer 未提供径向速度时，D1 为兼容 canonical radar 合同扩展为：

```text
z_contract = [rho, azimuth, elevation, 0]
R_contract = block_diag(R_spherical_3x3, sigma_rdot_placeholder^2)
radial_velocity_observed = false
```

第 4 维只是序列化/接口占位。`measurement_model_for()` 在该标志为 false 时构造
`z_filter=z_contract[:3]`、`R_filter=R_contract[:3,:3]`，观测函数也只返回 range/azimuth/
elevation；因此补零径向速度不会进入创新。位置转换为：

```text
pN = sN + rho cos(elevation) cos(azimuth)
pE = sE + rho cos(elevation) sin(azimuth)
pD = sD - rho sin(elevation)
```

位置 Jacobian `Jp` 只对前三维球坐标求导。无多普勒起始状态和 covariance 为：

```text
x0 = [pN, pE, pD, 0, 0, 0]
P0 = [[Jp R_spherical Jp^T + P_sensor, 0],
      [0,                                  25 I3]]
```

`25 m2/s2` 是公开可配置的各轴零均值高斯先验，不是速度裁剪，也不读取场景真实速度。若 producer
确实提供第 4 维多普勒且标为 observed，则保留原四维量测路径，并仅对未观测切向速度增加方差。
输入原 `3x3` spherical covariance 不被默认模型替换，canonical observation 的左上块逐元素
保留。最终 track 始终是 `[pN,pE,pD,vN,vE,vD]` 和 `6x6` covariance。

### 26.2 扫描级关联与批量 birth

设扫描前航迹数为 `T`、点迹数为 `O`。radar 路径先把所有航迹传播/重放到统一
measurement time，把每个点迹转为 NED 位置和 covariance，再向量化计算：

```text
d(i,j) = (z_j - x_i)^T (P_i + R_j)^-1 (z_j - x_i)
```

门外项设为大代价，使用 `scipy.optimize.linear_sum_assignment` 求一对一最小代价；SciPy
不可用时退化为确定性门内贪心匹配。求解后再次检查原始门限。所有匹配只针对 scan 前航迹，
随后再应用 measurement-time EKF/OOSM 更新；未匹配 radar 点迹逐条调用合法起始器。这样第一
条 birth 不会参与同一 scan 后续点迹的竞争，从算法上消除固定门限造成的空间 packing 上限。

更新仍使用 `_BatchProcessingContext`：同测量时刻的 track state 只重放一次，dirty track 在
批末各重放一次到融合发布时刻。历史 scan 迟到时写入原 observation history，并按既有
fixed-lag/origin/archive 规则重建；track 输出同时保留 measurement/arrival timestamp。

### 26.3 三维声学弱约束

`acoustic_3d` 的观测函数为：

```text
h(x) = [atan2(rE, rN), atan2(-rD, sqrt(rN^2 + rE^2))]
```

两个角度残差均 wrap，Jacobian 数值计算，输入 `2x2` covariance。该模态只进入已有航迹的
创新和 EKF 更新，不属于 radar 起始器。soundprint 概率先检查有限、非负、和大于零，再归一化
并仅作为 category metadata 保存；它不进入代价矩阵，也不作为 truth hint。

### 26.4 回归证据与复杂度边界

2026-07-20、seed 7，5/20/50/100/200 各两次 scan，共 750 条匿名 radar measurement：首扫
全部 birth，次扫全部一对一 update，200 档航迹数保持 200；状态有限、`6x6` covariance 半
正定。2 目标 delayed scan 验证 2 条 OOSM 重放；声学验证 0 birth/5 update 类别边界；身份注入
全部拒绝。专项 `9 passed`、模块全量 `120 passed`。

radar 关联的矩阵规模为 `O(T*O)`，200x200 当前可接受，但本轮没有给出长 episode、多 sensor、
虚警增长下的正式实时上界。track confirmation/deletion、跨 scan ID continuity 和至少 20 个
未见 seed 的 recall/NIS/NEES 由后续 D2/D6/main 集成验收。

### 26.5 位置-only radar 创新门控与速度稳定性

对于预测状态 `x-`、covariance `P-` 和三维量测模型，先计算：

```text
nu = z_filter - h_filter(x-)
S = H P- H^T + R_filter
NIS = nu^T S^-1 nu
```

默认门限 `gamma=chi2_3(0.999)=16.26623619623813`。若 `NIS>gamma`，replay 保留预测状态和预测
covariance，不应用该 measurement update；量测仍保留在按 measurement timestamp 排序的历史
中，所以顺序处理与 OOSM 重放会得到相同的门控判定。metadata 记录本次 replay 的创新数、
实际滤波更新数、拒绝数及匿名 observation IDs。扫描关联接受数和滤波更新数因此是两个不同
审计口径。

2026-07-20 的自动化证据包括：无多普勒三维模型/`25I` 先验、一个门内关联但超 NIS 阈值的
离群点、2 航迹顺序/乱序 3 scan 数值等价，以及 seed 17 的 200 航迹/10 scan/2,000 条匿名
radar measurement。200 条末帧速度 median/P90/max=`3.87/6.43/8.54 m/s`，速度 covariance
trace=`57.97/60.69/61.19`；数量和 ID 全程保持 200。专项 `13 passed`、模块全量
`124 passed`。

该结果只证明短基线噪声不再被当前 D1 路径过度写入速度均值，且不确定性仍显式存在。固定
零均值先验会收缩早期速度；过程噪声仍为现有 CV 参数。多 seed 速度误差 coverage、NIS/NEES、
机动和漏检/虚警，以及 D2 二次滤波/D3 分配仍需后续正式验证。

## 27. 逐更新 consistency evidence 与纯离线 evaluator（2026-07-20）

### 27.1 在线 evidence 采集

`FusionAdapter` 为每个 observation 建立固定 schema record。track birth 写六维初始化 estimate，
不伪造 innovation；正式 `_finalize_record_replay()` 和 checkpoint 前 origin replay 在已有
`_filter_update()` 返回后记录 posterior/prediction、NIS 与 gated 标志。采集不参与 association
candidate 的临时 `_state_at()` 查询，因此不会把代价矩阵内部探针误写成 episode evidence。
OOSM 触发新 replay 时，同一 observation record 按 revision 更新；算法仍调用原 NumPy EKF 和
原 gate，evidence 不反馈状态、门限或 track ID。

online record 使用 opaque lineage SHA-256，保留 sensor 和 lineage 等价关系但不复制潜在身份
值。radar 直接 range 按 `d1.consistency.range_bins.v1` 输出 `[0,1000)`、`[1000,3000)`、
`[3000,5000)`、`[5000,+inf)`；同时保留 `range_m`，D6 可按正式实验另行重分箱。records digest
覆盖排序后的所有 DTO，bundle digest 覆盖 schema、range profile、provenance、count 和 records
digest。所有序列化均要求 `allow_nan=False` 可通过。

### 27.2 离线严格对齐与指标

truth sidecar 的键为 `(truth_id, timestamp)`，state 必须是六维 NED；D2 先用 source
observation lineage 形成 canonical identity，再输出以
`(observation_id, measurement_timestamp) -> (D2 global_track_id, truth_id)` 表示的 adapter，
并绑定 online/truth digest。D1 evidence 内的航迹键明确命名为 `source_global_track_id`，不进入
D2 canonical namespace。对每个 available estimate，evaluator 要求：

```text
estimate_timestamp == measurement_timestamp
exactly_one_lineage_mapping(observation_id, measurement_timestamp)
exactly_one_truth_sample(truth_id, estimate_timestamp)
```

容差默认 `1e-9 s`，不插值、不外推、不做 proximity matching。对误差 `e=x_est-x_truth`：

```text
position_rmse = sqrt(mean(||e_position||^2))
velocity_rmse = sqrt(mean(||e_velocity||^2))
NEES = e^T P^-1 e
normalized_nees = NEES / 6
nis_gate_coverage = mean(NIS <= configured_gate)
```

NEES 先对 `P` 做 Cholesky 正定检查，再使用 `solve`；任一样本奇异则 episode-level NEES
unavailable，不能仅挑选可逆样本形成偏置统计。NIS 与 gate coverage 不依赖 truth，因此缺失
mapping/truth 时仍可单独 available。result 不嵌入 online state 或完整 truth，只保留误差、
metric availability 与三个输入 digest，形成物理分离的离线 artifact。

### 27.3 输出和验证边界

online/offline `aggregation_records()` 均输出 scenario/version/run/seed、sensor ID/type、range、
observation/update 指标和 source/input digest，记录数随输入变化，无 2v2/5v5 常量。2026-07-20
新增 `12` 项合同测试，包含额外在线 truth 字段 fail-closed；main 复跑 D1 全量
`136 passed`。oracle 夹具为 position RMSE `5 m`、
velocity RMSE `12 m/s`、NIS gate coverage `0.5`；其目的仅是验证公式和 fail-closed 路径。
正式多 seed 精度、统计 coverage 和传感器 covariance 校准尚无新证据。

## 28. 扫描输入的事件时间水位线（2026-07-22）

### 28.1 与固定滞后回放的分工

扫描输入整理和卡尔曼 OOSM 回放是两个连续阶段。输入整理判断完整扫描能否进入融合器；固定
滞后回放在扫描释放后，根据 measurement time 重建状态。前者不读取航迹、不计算 Kalman 增益，
后者不负责等待未来扫描或限制上游缓冲。

```text
arrival-order scans
  -> ScanInputOrganizer
  -> measurement-order released scans
  -> process_scan_batch
  -> measurement-time EKF/fixed-lag replay
```

设已经接收的唯一扫描最大量测时刻为 `M_k`，最大允许迟到为 `L`，水位线为：

```text
W_k = M_k - L
```

接收新帧前，如果 `t_measurement < W_(k-1)`，该帧已越过关闭边界，全部拒绝。接收后，缓冲中
满足 `t_measurement < W_k` 的帧按 `(t_measurement, received_sequence)` 排序释放。严格不等号
保留了 `t_measurement == W_k` 的边界，使不同来源的同时间扫描能在迟到窗口内汇合。episode
结束的 `close()` 表示调用方确认不再有新帧，此时按同一顺序释放尚未过期的尾部。

### 28.2 扫描身份与冲突

每帧由 source namespace、sensor/modality/frame、scan ID 和 observation lineage 描述。在线输入
先经过 covariance 与 truth 隔离检查，再计算两个摘要：

```text
content_digest = H(measurement time, measurement, covariance, lineage,
                   geometry, quality, non-transport metadata)
frame_digest   = H(content_digest, scan ID, arrival/transport envelope)
```

- 相同 scan key 和相同 frame digest：duplicate；
- 相同 source lineage/content、不同 transport envelope：replay；
- scan key 或 lineage 被不同 measurement time、covariance 或 payload 复用：timestamp/payload
  conflict；
- 一帧中只有部分 lineage 已出现：mixed replay/conflict，整帧拒绝。

摘要不使用 truth、actor、object、目标顺序或 `global_track_id`。拒绝分类可以与 too-late 同时为
真，便于区分“来源重复”和“已经越过水位线”两个事实。

### 28.3 有限资源与审计

扫描帧不再调用通用 `deepcopy`。D1 按 `SensorObservation` 字段建立快照：measurement、
covariance 以及相机内外参等元数据数组独立复制并设为只读；嵌套 `Mapping`、列表和集合递归
冻结。这样可以直接接收 main `OnlineSensorBatch` 中的 `mappingproxy` 相机模型，同时保持原始
生产者后续修改不会影响已接收帧。递归 truth 检查在快照后执行，冻结结构不会绕过身份隔离。

配置同时限制：最大迟到时间、最大缓冲驻留时间、缓冲扫描数、缓冲观测数、claim scan 数和
claim observation-lineage 数。新帧会推进水位线时，先原子计算可释放集合和加入后的容量；只有
容量满足才接收。已关闭的扫描先释放，再接收边界帧，因此缓冲在函数执行期间也不超过数量
上限。驻留超时、buffer/claim overflow 都 fail closed，不用丢弃旧帧换入新帧。

`ScanInputAuditEvent` 按扫描记录 buffered/reordered/released/duplicate/replay/conflict/too-late/
overflow/expiry，`ScanInputAuditSummary` 累计上述数量，并给出当前和最大缓冲、latest arrival、
max measurement、水位线和 closed 状态。事件与摘要使用独立 v1 schema，可直接有限 JSON
序列化。

### 28.4 main 组合接口

```python
observations = sensor_observations_from_online_batch(batch)
frame = SensorScanFrame.from_observations(observations, scan_id=batch.batch_id)
decision = organizer.ingest(frame)
latest_result = None
for released in decision.released_scans:
    latest_result = adapter.process_scan_batch(released.observations)
if latest_result is not None:
    publish_to_d2(latest_result.tracks)
```

输入时间必须先归一到同一 episode clock，观测坐标必须先符合 D1 canonical frame。organizer
本身不估计 clock offset，也不做外部 frame 变换。没有扫描的 episode tick 只调用
`advance_arrival_time(now)` 维护驻留上限；它不改变 event-time
水位线。episode 结束必须调用 `close()` 并处理尾部 `released_scans`。main 只把融合后的 tracks
交给 D2，逐帧 events 和累计 audit 交给 D6。D1 本轮未修改 main-owned runtime。

2026-07-22 的 15 项确定性合同测试和 D1 全量 `151 passed` 验证该行为，无随机 seed、无
AirSim。main 随后从 clean 提交对 20/50/100/200 各运行 5 个 formal 快速治理 episode，完成
延迟窗口、缓冲、拒绝和资源审计复跑；这些结果仍不代替 fixed-lag 数值正确性、融合吞吐或真实
传感器精度验收。

## 29. 扫描释放粒度与后验处理预算（2026-07-22）

main 正式治理接线表明，输入整理和融合计算需要分别计时。提交
`e4d66db02a0b8f1b867a0e81b4a73de84588426b` 的快速治理 benchmark 中，四档规模各 5 个
seed 的每个 episode 都能在峰值 3 帧缓冲下处理 136 帧，重排 12、拒绝/过旧/溢出 0、尾部缓冲
0；20/20 为 clean/formal，200 规模峰值内存均值约 40.91 MB、最大 40,926,870 B。该路径不运行
完整融合。旧 development 单次 200v200 全栈则对 86 个释放扫描逐一调用
`process_scan_batch()`，fusion 累计 35.115 s、平均 408.313 ms，明显高于输入整理的
2.682 s/31.186 ms。

扫描级一对一关联不能被简单跨来源合并。雷达 scan、拦截相机 scan 和侦察相机 scan 有不同的
observer namespace；把它们拼成一个伪扫描会改变“一条航迹每 observer scan 最多一次更新”的
语义。性能优化只能复用计算和延迟后验物化：先按原顺序完成每帧关联和 evidence，再对同一已
关闭 measurement-time cohort 合并发布传播；只重放 revision 变化的 dirty tracks，未变航迹
复用只读快照。

优化的数值护栏是相同冻结输入下 track 集、每条 state/covariance、双时间戳、OOSM、innovation/
gate、接受/拒绝和 truth-use 与当前基线一致，容差沿用 `1e-9`。该段记录优化前方案；增量后验
检查点和公共发布快照已经按下节实现。

## 30. 增量后验检查点（2026-07-22）

### 30.1 检查点结构

对航迹 `r`，将除起始观测外、截至查询时刻 `t` 的有效观测按以下键排序：

```text
k_i = (measurement_timestamp_i, arrival_timestamp_i, observation_id_i)
```

第 `i` 个检查点保存应用该观测后的后验 `(x_i+, P_i+)`、NIS 和 gate 结果。新的状态查询先从
第一项开始比较观测身份与排序键，最长匹配前缀直接复用；余下后缀运行原有 `predict_to()` 和
`_filter_update()`。检查点不缓存发布时刻外推，因此查询末端仍按原有过程噪声传播到 `t`。

### 30.2 失效规则

- 顺序追加观测：保留全部旧前缀，只计算新后缀；
- 历史中部插入 OOSM：删除第一个排序键不小于插入键的检查点及其后缀；
- 起始观测变化：重新生成起始状态并清空全部检查点；
- 固定滞后重基：旧锚点后验成为新的初始状态，清空检查点后按保留窗口重建；
- 检查点前合法 OOSM：从可用历史锚点完整重建，不使用旧后验。

`_capture_consistency_update_if_enabled()` 对缓存命中和新计算路径都执行。缓存只复用数值后验，
不复用或跳过当前 replay revision 的证据记录。observer-scan conflict、measurement/arrival 双
时间戳和航迹 covariance 均沿用原路径。

### 30.3 发布快照

association audit、latency audit 和 sensor-health 都是扫描完成时的全局快照。优化前每物化一条
航迹都会重新构造一次；优化后每扫描构造一次，再为每条航迹复制字典。状态和协方差数组使用
独立副本，调用方修改发布对象不会改变内部 `TrackRecord`。协方差限幅增加内部状态标志，只在
状态变化后重新执行，限幅原因和阈值保持不变。

### 30.4 可复核基准

`scan_fusion_performance.py` 从冻结 JSONL 读取 `topic=sensor.observations`，仍经过正式
`sensor_observations_from_online_batch()` 和 `ScanInputOrganizer`，然后分别运行关闭/开启优化
的两个适配器。每扫描计算输出与批次摘要哈希，结束后计算航迹和 consistency evidence 哈希。
性能验收使用操作计数；墙钟和 cProfile 用于解释热点，不进入脆弱单测。

冻结输入上 filter update 下降 98.07%，逐扫描和终态语义相同。1/7/200 动态规模、乱序后缀
失效、检查点前 OOSM、evidence revision 和发布数组防别名均进入测试。性能专项 `6 passed`，
main 复跑 D1 全量 `157 passed in 28.77s`。该基准不读取在线 truth，也不证明 AirSim、正式
传感器精度或完整系统实时性。

## 31. 不可变共享审计树（2026-07-24）

### 31.1 重复工作

对一个发布扫描记全局审计树为

```text
A_k = {association_audit, latency_audit, sensor_health}
```

reference 已在扫描级只计算一次 `A_k`，但对扫描内每条航迹 `i` 继续构造
`copy(A_k.association)`、`copy(A_k.latency)` 和
`{sensor: copy(summary)}`。复杂度中的复制项近似为
`O(T_k * (|A_k| + S_k))`，其中 `T_k` 为航迹数，`S_k` 为传感器健康摘要数。

### 31.2 候选

候选先执行一次递归冻结：

```text
F_k = freeze(copy_recursive(A_k))
metadata_i = copy(track_metadata_i)
metadata_i["association_audit"] = F_k.association_audit
metadata_i["latency_audit"] = F_k.latency_audit
metadata_i["sensor_health"] = F_k.sensor_health
```

v1 冻结映射和列表继承标准容器，常规变异方法抛出 `TypeError`。该方式不能阻止
`dict.__setitem__(instance, ...)` 或 `list.append(instance, ...)` 直接操作基类存储，也不能让
下游仅凭精确类型证明递归不可变。v1 已经由正式多 seed 矩阵拒绝。

v2 把映射的 `(str, value)` 对保存到 `frozenset`，把 JSON 数组保存为不可变元组。两个公开
类型都没有实例字典或可写槽位，也没有 `dict/list` 基类存储。精确递归验证规则为：

```text
root type == ImmutablePublicationAuditMap
map value  := exact ImmutablePublicationAuditMap
            | exact ImmutablePublicationAuditSequence
            | None | bool | int | finite float | str
map key    := exact str, unique within one map
```

`validate_immutable_publication_audit_tree()` 逐节点检查精确类型、键和叶值。任意自定义
`Mapping`、`mappingproxy`、marker、容器子类、循环输入、重复键、可变叶值和非有限浮点数均
失败。即使调用者用 `tuple.__new__` 绕过类型构造器，验证器也会检查底层每个键值对和叶值。
`freeze_publication_audit_tree()` 只接受精确内建 `dict/list/tuple` 及可转为受支持叶值的
NumPy 数组，先复制再生成 v2 合同。

合同认证只证明树在当前 Python 对象模型中递归不可变，不证明内容已经通过在线 truth 隔离。
D2 应先认证对象，再对该对象执行一次原有内容审计，并以强引用对象身份缓存通过结果。后续只
在遇到同一对象时复用；不能按 `__eq__`、marker、摘要值或裸 `id()` 复用。

`GlobalTrack.to_dict()` 调用 `publication_audit_to_builtin()`，在 JSON 和持久化边界还原普通
`dict/list`。深拷贝可复用原不可变对象；pickle 往返后仍须重新执行精确合同验证。候选复制项
保持 `O(|A_k| + S_k + T_k)`，不共享任何轨迹专属可变对象。

### 31.3 A/B 保护

`immutable_shared_publication_metadata` 显式选择 reference/candidate，默认 `False`。专用
benchmark 在相同 `SensorScanFrame` 序列上交错运行两条路径，并逐发布计算完整
`GlobalTrack.to_dict()` 摘要。验收还比较扫描输入、claim registry、发布顺序、逐扫描融合摘要、
融合操作计数、累计诊断、终态和 consistency evidence。独立变异测试检查顶层 metadata 可各自
修改，共享审计树不可修改。

冻结 seed 1101 的 v1 完整物化数保持 71,515。reference 的共享审计映射复制计数为 8,832,271，
candidate 为 0；candidate 记录 214,545 次共享值复用。该计数证明减少的是重复容器复制，不是
航迹、扫描、观测或审计字段。单 seed profile 显示 `_to_global_track` 累计
`10.700 -> 2.198 s`。

v1 正式 short 10 seed、long 3 seed 中 D1 fusion wall 改善 16.29%/31.05%，但 D2 因逐航迹
重审自定义容器而增加 53.44%/169.89%，核心墙钟改善 1.65%/1.21%，未达到 5% 准入门。
v2 在 D1 合同和 389 项全量回归后，已由 main 与 D2 按精确合同完成系统接线。正式矩阵使用
clean source commit `be399e138762f5e660f553c8caa812d52ab38c61`，包含 short seeds
1101-1110、long seeds 1101-1103，共 13 对、26 个 arm，场景规模为 200 目标、200 资源和
2 个侦察节点。全部 arm 为本轮新执行，0 reused、0 failed。

v2 候选的 D1 fusion short/long 改善为 13.5447%/26.8298%，超过 10% 门；核心墙钟改善为
6.5677%/18.2438%，超过 5% 门；D2 association 耗时变化为
-16.1939%/-35.6213%，满足回归不高于 5% 的门限。13/13 业务语义、有限状态、在线真值隔离、
实现身份、D2 审计和 RSS 检查通过。候选累计 702 次精确合同验证、702 次内容审计、
139,920 次强引用身份复用，合同拒绝为 0。D6 判定
`d1_optimization_admitted=true`。

D1 的布尔配置默认仍为 `False`，直接构造时保留 reference。main promotion commit `f5b350b`
已将系统默认 selector 晋级为 `immutable_shared_v2`，并保留 `per_track_copy_v1` 显式对照。
最低实时因子为 `0.1730801`，所以该实现只完成发布元数据候选准入，没有关闭系统实时、
AirSim、硬件、RMSE/NEES/NIS 或物理拦截验收。逐批 D2 审计明细仍为 P1。
