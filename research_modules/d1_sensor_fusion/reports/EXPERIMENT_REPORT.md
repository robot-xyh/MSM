# D1 Sensor Fusion Offline Experiment Report

## 2026-07-24 扫描输入正式同提交准入

正式证据来自 clean commit
`d14285e4fdeb2f2e2cd32fad2f6d42e30f9e73a7`。short 使用 seeds 1101-1110、
2.2 s，long 使用 seeds 1101-1103、10 s；reference 与 candidate 的唯一运行差异是
`d1_scan_input_implementation=reference_v1/candidate_v2`。

| 组别 | scan-input reference -> candidate | 逐 pair 平均改善 | 更快 pair | 原始相对变化 bootstrap 95% CI |
| --- | ---: | ---: | ---: | ---: |
| short | `1.2124522798461839 -> 1.145650333847152 s` | `5.360121886647966%` | `9/10` | `[-8.208165356448217%, -3.0841406102053194%]` |
| long | `6.687633245543111 -> 6.3406803108907 s` | `5.142481684491682%` | `3/3` | `[-8.837128529506151%, -1.6693612946922343%]` |

13/13 pair 的业务语义、有限状态、在线真值隔离和实现身份检查通过，RSS 门通过。核心墙钟
short/long 仅改善约 `0.7187%/0.5792%`。D6 判定
`d1_optimization_admitted=true`，扫描输入优化正式矩阵 P1 关闭，`candidate_v2` 正式
准入。

系统实时缺口仍开放。`system_realtime_gap_closed=false`，候选最低实时因子为
`0.14342687633969603`。本批是三维质点结果，不是 AirSim 或实机证据，也没有目标硬件、
RMSE、NEES、NIS 和长于 10 s 的容量结论。

## 2026-07-24 协方差向量化正式准入

正式 v3 试验使用三维质点集成栈。short 组为 seeds 1101-1110、2.2 s；long 组为
seeds 1101-1103、10 s。13 组配对形成 26 个 episode，26/26 正常退出，13/13 跨构建语义
检查通过。标量 reference 提交为
`a5a472cf81496d94a98db3deb88a3d5c6951f0ce`，向量化 candidate 提交为
`064cbb979d3bab68fee995e476df25709eb666db`。两臂共同包含该 candidate 提交中的 D1
完整正半定修复和 `e4147b8` 的 D2 误警审计修复。

| 组别 | D1 融合累计墙钟 reference -> candidate | 改善 | 更快 seed | 配对原始变化 95% CI | P95 改善 |
| --- | ---: | ---: | ---: | ---: | ---: |
| short | `4.029165 -> 3.652252 s` | `9.35462%` | `10/10` | `[-10.914359,-8.113134]%` | `6.652902%` |
| long | `32.954357 -> 30.768826 s` | `6.631993%` | `3/3` | `[-7.279095,-5.406805]%` | `6.655511%` |

D6 判定 `d1_optimization_admitted=true`。P0 PSD 输出缺口和 P1 向量化准入缺口关闭。
`system_realtime_gap_closed=false`；candidate 最低实时因子为 `0.143397`。正式 manifest
SHA-256 为
`40669d10fff8367aa31e24624bab802d8bc3de6b01aaa1e5c92d054753ed93ec`。

本批没有 RMSE、NEES、NIS、AirSim 或目标硬件证据。系统实时性、融合质量和目标平台容量
继续保持开放。

## 2026-07-24 完整正半定治理

seed 1103、200v200、10 s 长时候选在仿真时刻 `7.85180018473111 s` 暴露 D1
pairwise covariance limiter 会把合法六维矩阵变为非正定矩阵。限制前/后最小特征值为
`+7.506060086e-04/-9.247657800e-04`。故障前 58,776 次 scalar/vectorized 同输入双算
完全一致，根因不是向量化。

当前在对角和逐对限制后执行相关矩阵特征值投影、单位对角恢复和单位阵凸组合，有限复核失败时
使用同一治理对角矩阵。失败回归、1 至 6 维随机/极端性质、两实现等价、双时间戳、谱系和
6 s fixed-lag 测试通过；D1 全量 `352 passed in 20.52s`。

修复后同配置 10 s episode 完成，处理 10,554 条匿名观测，状态有限、在线 truth 0，
RTF `0.157583`。该运行只证明原 PSD 断点闭合；上节补充了后续 clean 多 seed 准入。两批
均不是 AirSim、目标硬件、实时或 RMSE/NEES/NIS 结论。

## 2026-07-23 扫描 claim JSON 单次物化

clean `5263e2b343dc4b96d239f77ef09437eb132f9efb` 的
`200v200-nominal-v1`、10 s、seed 1000 冻结输入包含 771 scans/11,889 anonymous
observations，SHA-256 为
`5d033a049c2b4e09fb13d7c36e1117055b5b596d9e31f058ad2bf7cbd267ce8f`。

旧 claim 路径分别为内容摘要和完整帧摘要递归转换共享记录。新路径先生成一份 JSON 安全内容，
再添加帧专有字段并沿用原 JSON 编码与 SHA-256。claim registry、逐输入事件、release
schedule、逐 fusion 状态/协方差/双时间戳/谱系/分级、操作计数、累计诊断、终态和一致性证据
严格一致；在线 truth 使用为 0。

771 scans 交错 5 轮 P50/P95 为
`3.618/4.049 s -> 1.905/2.038 s`，P50 1.899x。`_json_safe` cProfile 累计
`5.781 -> 1.992 s`。墙钟不参与等价验收。D1 全量回归为 `185 passed in 19.69s`。

该结果只关闭 claim 重复规范化。它不是新的 AirSim、clean 候选多 seed 或实时证据；D1 fusion
和 GlobalTrack 物化、非雷达关联、fixed-lag replay 仍保持 P1。

详细证据：

- `d1_tail_latency_performance_20260723.json`
- `D1_TAIL_LATENCY_PERFORMANCE_20260723_CN.md`

## 2026-07-23 冻结 replay 尾延时归因与完整帧复用

clean `4ac3bb2c12cc6af6ebd372107ced00bcdc5adf6a` 的
`200v200-nominal-v1`、10 s、seed 1000 冻结输入包含 771 scans/11,889 anonymous
observations，SHA-256 为
`c1dda8523e48c255bbeef48d9516b05863eb1bbb3a3ae2e09733259e6a66f77a`。源 episode 的
fusion P50/P95/max 是 `33.252/224.764/592.957 ms`，scan-input 是
`1.747/177.084/361.536 ms`。

profiler 显示 organizer 重建了已经完成深快照和合同校验的 `SensorScanFrame`。完整帧复用将
帧重建从 771 降为 0、organizer 内 observation 再快照从 11,889 降为 0。
`ScanInputOrganizer.ingest` cProfile 累计 `15.545 -> 5.754 s`；剩余主要路径为
`_claim_for_frame 5.580 s`、`_json_safe 3.910 s` 和 `_digest 3.507 s`。

前 256 scans 交错 5 轮 P50/P95 `1.942/1.968 -> 0.881/0.894 s`，P50 比 2.204x；
墙钟不参与验收。旧/新完整 replay 的 14 项 acceptance 全部通过，覆盖逐输入
organizer/audit/release、逐 fusion 状态/协方差/双时间戳/谱系/分级和物化航迹、终态、
一致性证据、逐 fusion operation counts 及累计 diagnostics。operation/diagnostic snapshot
hashes 分别为 `82728a8e...bfb5bf` 和 `b28df84d...521766`。
main 实测当前 D1 全量回归为 `185 passed`，这是当前工作区权威测试计数。

fusion 算法本轮未修改。cProfile 主要累计路径为 GlobalTrack 物化 `17.559 s`、扫描关联
`17.027 s`、`_to_global_track 16.930 s`、非雷达代价矩阵 `14.971 s`、replay
`8.601 s`。工作区未剖析 replay P50/P95/max 为 `34.108/178.420/354.413 ms`，radar P95
为 `343.059 ms`；峰值为 40,000 candidate pairs 和单扫描 197 次 fixed-lag rebase。

clean/commit 只描述冻结输入。优化验证来自当前未提交 D1 工作区，是单 seed 三维质点 replay，
不是新的 clean full-stack、AirSim、正式多 seed 或实时放行。剩余 P1 是 clean 20-seed
full-stack 重测、fusion GlobalTrack/radar/rebase 和 scan-input audit/lineage/JSON 治理。

详细证据：

- `d1_tail_latency_performance_20260723.json`
- `D1_TAIL_LATENCY_PERFORMANCE_20260723_CN.md`

## 2026-07-22 Nominal 200v200 clean 单 seed 全栈校准

main 在 detached clean `4ac3bb2c12cc6af6ebd372107ced00bcdc5adf6a` 上完成
`200v200-nominal-v1`、10 s、seed 1000 的全栈运行。参考是 clean
`0d2da25c14e50f8f9a10ad47a7bd74e5c5e577fb` 的同 seed、同配置运行。两端各包含 200 个目标、
200 个资源、771 个 D1 扫描和 11,889 条匿名在线观测。

接受条件为：两端 source clean、配置/seed/时长一致、状态有限、在线 truth 使用为 0，并且规范
在线载荷、离线 truth state、计划谱系模式及两端谱系有效性跨构建审计全部通过。候选满足
`finite_state=true`、`online_truth_use_count=0`；跨构建报告 `passed=true`，上述语义检查均为
true。

| 指标 | 参考 `0d2da25` | 候选 `4ac3bb2` | 变化 |
| --- | ---: | ---: | ---: |
| 核心 wall | 94.104939744 s | 85.002427712 s | -9.6727%，1.1071x |
| 核心 RTF | 0.1062643 | 0.1176437 | 候选仍小于 1 |
| D1 fusion 累计 | 49.697406826 s | 40.272795088 s | -18.9640%，1.2340x |
| D1 scan input 累计 | 12.315225105 s | 12.560936034 s | +1.9952% |

候选 D1 fusion 共 771 次调用，P50/P95/max 为
`33.25249/224.76351/592.95713 ms`。参考旧计时 schema 没有分位数字段，故不推算参考尾分布。
在线规范载荷、truth state 和计划谱系全部通过只证明同 seed 业务语义保持，不证明性能矩阵或
定位精度。

资源数据使用两种独立口径。`summary.json.wall_time_s=85.002427712` 是核心 episode wall；
外部 `/usr/bin/time` 的总进程 elapsed 为 `1:55.95`、峰值 RSS 为 `2,468,928 KiB`，包含启动、
离线后处理和落盘。外部 elapsed 不参与核心 wall 的 9.6727%/1.1071x 比较，二者不得混写。

本批只有一个 seed，是描述性 clean 校准，不是 20-seed，也不是正式矩阵。核心 RTF 为
0.1176437，未实时；D1 fusion P95/max 尾延时和 scan-input 增长继续作为 P1。AirSim、
RMSE/NEES/NIS 和物理拦截效果均未在本批验收。

只读证据：

- `/tmp/MSM-scalable3d-candidate-4ac3bb2/research_modules/scalable_3d_simulation/outputs/scalable_3d_timing_v2_clean_4ac3bb2_20260722/10p0s_seed_1000_nominal/`
- `/tmp/MSM-scalable3d-candidate-4ac3bb2/research_modules/scalable_3d_simulation/outputs/scalable_3d_timing_v2_clean_4ac3bb2_20260722/cross_build_seed_1000_nominal/`

## 2026-07-22 非雷达创新批处理对照

未见 seed 1000 的完整 10 s 冻结输入含 771 个扫描、11,889 条匿名观测和 201 条终态航迹。
旧路径逐候选调用伪逆；新路径按严格量测几何和矩阵形状构造创新协方差矩阵栈。观测、协方差、
残差、门限、Hungarian 分配、固定滞后和 truth 隔离合同不变，批处理失败时回退旧路径。

前 256 个扫描和 4,087 条观测在同进程预热后交错运行 7 次。旧/新 P50 为
`12.242/10.238 s`，P95 为 `13.340/11.248 s`，均值为 `12.506/10.385 s`。完整输入单次
无 profiler 对照为 `50.458/39.994 s`。逐扫描摘要、终态航迹和一致性证据哈希相同，全部操作
计数、累计诊断和物化计划也相同；在线 truth 使用为 0。

完整 cProfile 中，非雷达代价矩阵累计 `34.307 -> 17.320 s`，`numpy.linalg.pinv` 调用
`496,625 -> 1,018`，累计 `14.837 -> 0.589 s`。该 2026-07-22 非雷达专项当次历史回归为
`182 passed in 15.92s`，不是当前权威测试计数。详细证据见
`D1_NON_RADAR_INNOVATION_PERFORMANCE_BENCHMARK_CN.md` 和对应 JSON。本组不是全栈实时、
AirSim 或正式 RMSE/NEES/NIS 结论。

## 2026-07-22 一致性证据计数刷新对照

本次使用 clean `f80b5bd` 的 10 s 冻结在线观测 seeds 42000-42002。参考路径对合法缓存证据
执行完整 dataclass 重验；候选路径只从已经验证的冻结记录复制不变字段，并校验新的非负 replay
revision/count。两条路径的 6 s fixed-lag、扫描顺序、观测、关联、门控、协方差和 truth 隔离
合同相同。

| Seed | 扫描/观测 | 完整重验 | 受限复制 | 加速 | 缓存刷新 | 语义验收 |
| ---: | ---: | ---: | ---: | ---: | ---: | :---: |
| 42000 | 764/12,107 | 61.655 s | 48.804 s | 1.263x | 194,916 | 通过 |
| 42001 | 844/11,922 | 67.316 s | 55.069 s | 1.222x | 185,165 | 通过 |
| 42002 | 782/11,825 | 65.562 s | 54.096 s | 1.212x | 176,170 | 通过 |
| 均值 | - | 64.844 s | 52.657 s | 1.231x | - | 3/3 通过 |

逐扫描状态、协方差、时间戳、来源谱系和航迹分级完全一致；终态航迹、最终逐观测一致性证据、
全部操作计数和物化计划也一致，在线 truth 使用为 0。代表 seed cProfile 的刷新累计
`27.122 -> 1.664 s`，`_replay_record` 累计 `35.348 -> 9.410 s`。D1 全量
`178 passed in 14.80s`。

详细数据见 `D1_CONSISTENCY_COUNTER_REFRESH_PERFORMANCE_BENCHMARK_CN.md`、
`D1_CONSISTENCY_COUNTER_REFRESH_PROFILE_10S_CN.md` 和对应 JSON。结果关闭该重复校验热点，不关闭
非雷达关联、航迹物化、scan input、长于 10 s 的增长率、AirSim 或正式融合精度 P1。

## 2026-07-22 雷达候选预门控与快照物化对照

本次使用 clean `8f86192` 的 10 s 冻结在线观测 seeds 42000-42002。参考路径关闭雷达预门控和
A95 单次复用；候选路径开启两项优化。预门控仅对有限、严格对称、Gershgorin 严格正定且确认
最小特征值高于 `np.linalg.pinv` cutoff 上界的创新协方差生效，其他矩阵全部回退旧精确伪逆。

旧/新纯融合墙钟均值为 `91.313/88.619 s`，3/3 candidate 更快，聚合加速 `1.030x`。精确创新
求解合计 `7,130,228 -> 1,578,677`，下降 77.9%。三个 seed 的逐扫描后验、终态航迹和一致性
证据哈希全部一致；候选对、固定滞后操作数、扫描/观测数和完整/状态快照调度不变。非正定交叉
协方差和近奇异截断负例均确认未认证矩阵不被预拒绝，并保持扫描语义等价。专项 `6 passed`，
D1 全量 `175 passed in 26.69s`。

详细逐 seed 数据见 `D1_COALESCED_RELEASE_PERFORMANCE_BENCHMARK_CN.md` 和
`d1_coalesced_release_performance_benchmark_20260722.json`。本结果不证明 AirSim 实时性、真实
雷达精度、正式系统容量或 200 对 200 闭环实时性。

## 2026-07-22 Clean 200v200 全栈接线复跑

clean 候选提交 `8f86192` 已在 main-owned 三维质点全栈接入同一 fusion timestamp 延迟物化。10 s
seeds 42000、42001、42002 均为 clean、finite，在线 truth 使用 0，D1/D2 overflow 和安全合同
全部通过。旧对照为 clean 提交 `3bac3ff`。

| Seed | 扫描数 | State-only | 完整快照 | 旧 D1 fusion | 新 D1 fusion |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 42000 | 764 | 310 | 454 | 103.176 s | 89.796 s |
| 42001 | 844 | 328 | 516 | 106.447 s | 96.599 s |
| 42002 | 782 | 278 | 504 | 100.394 s | 92.578 s |
| 均值 | - | - | - | 103.339 s | 92.991 s |

D1 fusion 均值下降 10.0%。每例 state-only 与完整快照之和均等于接收和释放扫描数；所有扫描仍
逐个融合并发布。事件、scan input、共享摘要和世界真值与旧提交对应 seed 相同。seed 42000 的
2.2 s 全栈墙钟由 18.611 s 降至 18.302 s。

该结果关闭 main-owned 质点全栈延迟物化接线和 clean 三 seed 语义复跑项，不关闭实时预算。
10 s 输入的 D1 fusion 仍平均耗时 92.991 s；本组也不提供 AirSim、真实传感器精度、
RMSE/NEES/NIS 或物理拦截证据。当前证据摘要另见 `../docs/EXPERIMENT_REPORT.md`。

## 2026-07-22 长时固定滞后性能对照

### 输入与验收

本次直接使用 clean 长时场景的 10 s 冻结在线观测。文件 SHA-256 为
`3efa561a07bf0cdcd74d23570ee23ca173f56ddaf632c89258d02c20c299a51a`，包含 764 个扫描、
12,107 条匿名观测和 202 条终态航迹。扫描重排 49 次，峰值缓冲 64 个扫描/825 条观测，所有
扫描均释放，在线 truth 使用为 0。旧路径关闭四项长时缓存优化，优化路径全部开启；两者使用相同
输入、相同扫描顺序和相同 6 s 固定滞后窗。

### 结果

| 指标 | 旧路径 | 优化路径 |
| --- | ---: | ---: |
| 纯融合墙钟 | 157.237 s | 107.449 s |
| history replay | 170,106 | 13,397 |
| replay filter update | 120,440 | 9,549 |
| replay checkpoint reuse | 3,551,291 | 300,024 |
| checkpoint state query | 0 | 152,861 |
| fixed-lag suffix reuse | 0 | 110,891 |
| trusted prefix fast path | 0 | 300,024 |
| cached consistency refresh | 0 | 194,916 |
| candidate pair | 2,393,969 | 2,393,969 |
| innovation solve | 2,393,969 | 2,393,969 |

墙钟加速为 1.463 倍；history replay 和 filter update 分别下降 92.12% 和 92.07%。逐扫描语义、
终态航迹和一致性证据哈希均一致，说明操作数下降来自合法检查点复用，没有减少观测或改变业务
输出。累计计数可通过固定大小的 `fusion_performance_diagnostics()` 读取，便于 episode profiler
补充 summary 缺失的 filter update/checkpoint reuse 证据。

### 发布审计

`modules.d1.fused_tracks` 共 764 条、195,260,766 B（186.2 MiB）。日志包含 94 个唯一 runtime
时刻、407 个唯一融合时刻、470 个唯一航迹快照；357 条记录可在同一融合时刻合并，294 条与前一
快照相同。D1 的逐扫描有序融合仍然必要。按唯一融合时刻持久化最后后验，并以 heartbeat/lineage
sidecar 保存未变化证据，是给 main 的后续建议；本次没有修改 main，也没有实现发布合并。

### 结论边界

本专项关闭的是冻结输入下长时固定滞后重复计算的 D1-owned 缺口。它不关闭 clean 完整全栈多
seed、端到端实时倍率、峰值常驻内存、AirSim、RMSE、NEES、NIS 或物理拦截验收。详细机器可读
证据见 `D1_LONG_DURATION_PERFORMANCE_BENCHMARK_CN.md` 和
`d1_long_duration_performance_benchmark_20260722.json`。

## 2026-07-22 扫描关联工作区优化

### 基线与输入

第一阶段增量后验默认路径在 clean `492979e` 的 200 规模五个 seed 上，D1 fusion 分别为
10.096、13.693、12.895、11.973 和 11.856 s，均值 12.103 s。该组是第二阶段开始前的完整
五 seed 基线，优化后的同组全栈尚未复跑。

专项对照使用 seed 42000 的冻结 `online_observations.jsonl`。文件 SHA-256 为
`bc539686b130d96c63b76b9161fadbae2dba59de44cb61ac80d92f2ea1018406`，包含 86 个扫描和
2,051 条匿名观测。扫描输入审计记录 10 次重排，峰值缓冲 33 个扫描/623 条观测，拒绝、过旧和
溢出均为 0，在线 truth 使用为 0。

### Profiler 结论

current-default 的 cProfile 显示，剩余主要成本位于扫描一对一关联。`process_scan_batch()`
累计 16.743 s，`_scan_one_to_one_assignments()` 累计 6.876 s，逐候选调用的
`_association_score()` 累计 5.733 s；其中 `measurement_model_for()` 累计 2.453 s，
`numerical_jacobian()` 累计 1.685 s。`global_tracks()` 累计 1.387 s，未成为本轮首选改动点。
cProfile 会放大绝对墙钟，本组数值只用于确认调用结构。

非雷达扫描原先按“航迹数乘观测数”重复校验几何并构造量测模型。优化路径为扫描建立临时工作区：
量测模型按观测构造一次，航迹状态按共同量测时刻取得一次；仅在实际传感器和相机几何完全相同
时复用预测量测和数值雅可比。每个候选对的残差、创新协方差、伪逆、门控和 Hungarian 分配保持。

### 语义和操作数

| 指标 | current-default | 优化路径 |
| --- | ---: | ---: |
| candidate pair | 371,054 | 371,054 |
| innovation solve | 371,054 | 371,054 |
| measurement model build | 16,457 | 82 |
| projection build | 16,457 | 14,648 |
| radar track state build | 1,804 | 1,804 |
| radar observation state build | 1,769 | 1,769 |
| GlobalTrack materialization | 16,653 | 16,653 |
| 纯融合墙钟 | 10.792 s | 8.635 s |

量测模型构造下降 99.50%，投影构造下降 10.99%，本机单次墙钟加速 1.25 倍。86 个逐扫描语义
哈希完全一致；最终 201 条航迹哈希均为
`a60c8614f5e4dd59d77d1212112e9e0a2750610efed9365a0eb6043a67073457`；一致性证据哈希均为
`e9bea4499fc82b3e4f354c751fdf2c43d2635eb4fb78e5a7e0e63e04dbb6e52f`。

专项测试覆盖 1/7/200 动态规模、current-default 与优化路径等价、乱序插入、fixed-lag 检查点前
OOSM、候选对/创新求解保持和模型构造下降，结果为 `10 passed in 10.33s`。D1 全量回归为
`161 passed in 38.02s`。

### 结论边界

本阶段关闭的是 D1 冻结输入上的非雷达扫描重复模型构造。它没有丢弃观测、降低发布内容、缩短
fixed-lag、压低 covariance、放宽门控或读取在线 truth。优化后的 clean 五 seed 完整全栈、
AirSim、RMSE、NEES、NIS 和物理拦截尚未复跑，1.25 倍不能写成 200v200 系统实时结论。

详细结果见 `D1_SCAN_ASSOCIATION_PERFORMANCE_BENCHMARK_CN.md` 和
`d1_scan_association_performance_benchmark_20260722.json`。

## 2026-07-22 逐扫描融合性能治理

### 输入与方法

本次直接使用 seed 42000 的冻结 200v200 在线观测，不重新生成世界，也不读取离线 truth。输入
SHA-256 为 `38d24429711b67d612f2f398478386ebf0df690fae55cd9dcc36434aac4fb078`，包含
86 个扫描和 2,051 条匿名观测；输入整理记录 10 次重排，峰值缓冲 33 个扫描/623 条观测，拒绝
为 0，结束缓冲为 0。

对照路径关闭增量后验检查点和公共发布审计快照，作为同一代码中的未缓存参考。优化路径启用
两项能力。两个路径按同一扫描顺序运行，逐扫描比较航迹和批次语义哈希，结束后比较最终航迹与
consistency evidence 哈希。验收使用确定性操作数，墙钟和 cProfile 只用于说明成本分布。

### Profiler 结果

| 函数 | 未缓存调用 | 未缓存累计时间 | 优化调用 | 优化累计时间 |
| --- | ---: | ---: | ---: | ---: |
| `process_scan_batch` | 86 | 64.744 s | 86 | 17.657 s |
| `_replay_record` | 18,249 | 46.097 s | 18,249 | 6.837 s |
| `_state_at` | 18,299 | 38.120 s | 18,299 | 1.722 s |
| `_filter_update` | 93,234 | 37.615 s | 1,797 | 0.826 s |
| `global_tracks` | 86 | 9.856 s | 86 | 1.595 s |
| `sensor_health_summaries` | 16,653 | 7.291 s | 86 | 0.040 s |

cProfile 会放大绝对墙钟。表中结果用于定位重复工作：状态查询反复重放相同观测前缀；航迹发布
又为每条航迹重复生成同一扫描的传感器健康摘要。

### 优化结果

| 指标 | 未缓存参考 | 优化路径 |
| --- | ---: | ---: |
| replay filter update | 93,234 | 1,797 |
| replay checkpoint reuse | 0 | 91,437 |
| sensor-health snapshot build | 16,653 | 86 |
| GlobalTrack materialization | 16,653 | 16,653 |
| 纯融合墙钟 | 34.701 s | 9.073 s |

滤波更新操作数下降 98.07%，本机单次墙钟加速 3.82 倍。航迹物化数量没有减少，说明结果仍在
每个扫描完整发布。逐扫描语义摘要、最终 201 条航迹和 consistency evidence 哈希全部一致；
在线 truth 使用为 0。

专项测试覆盖 1/7/200 动态规模、优化开关语义等价、操作数下降、窗口内乱序插入、检查点前
合法 OOSM、一致性证据 revision 和发布数组防别名。性能专项 `6 passed`，main 复跑 D1 全量
`157 passed in 28.77s`。

### 结论边界

D1-owned 冻结输入逐扫描热点已关闭。该结论不表示 200v200 全系统已经实时，也不提供
RMSE、NEES、NIS coverage、AirSim 或物理拦截证据。下一步由 main 从 clean commit 运行完整
未见多 seed 全栈，固定硬件和发布频率后统计 P50/P95/max、峰值内存与实时倍率。

详细机器可读结果见 `D1_SCAN_FUSION_PERFORMANCE_BENCHMARK_CN.md` 和
`d1_scan_fusion_performance_benchmark_20260722.json`。

## 2026-07-22 Scalable 3D 正式治理证据复核

### 证据层次

本节只复核 main 生成的公开制品，不重新运行 scalable 场景。正式治理批来自 clean 提交
`e4d66db02a0b8f1b867a0e81b4a73de84588426b`。20/50/100/200 四档各 5 个互异 seed，共
20 个 episode；每例 136 帧、33.75 s。20/20 manifest 均为 `repository_dirty=false`、
`evidence_tier=formal`，在线 truth 使用总数为 0。

| 规模 | formal episode | 每例扫描 | 每例重排 | 拒绝/过旧/溢出 | 峰值/结束缓冲 | 峰值内存均值 | 峰值内存最大值 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 20 | 5/5 | 136 | 12 | 0/0/0 | 3/0 | 4.30 MB | 4,419,125 B |
| 50 | 5/5 | 136 | 12 | 0/0/0 | 3/0 | 10.36 MB | 10,411,011 B |
| 100 | 5/5 | 136 | 12 | 0/0/0 | 3/0 | 20.53 MB | 20,537,990 B |
| 200 | 5/5 | 136 | 12 | 0/0/0 | 3/0 | 40.91 MB | 40,926,870 B |

内存值取 D6 聚合中的 `estimated_peak_memory_bytes`，均值以十进制 MB 表示。它是 Python
tracemalloc 派生指标，不等同进程常驻集、AirSim 总内存或生产硬件预算。runner 仍明确记录
`full_system_evidence=false`，评估端也记录 `runtime_modules_imported=false`；该组只运行快速
治理 benchmark，不运行完整 D1 EKF/fixed-lag 融合。

独立哈希复核结果如下：聚合报告绑定的输入 SHA-256 为
`dd62ae9b6efd86d9669b42ccc0630127bc504a18f37c84be5b3ac8b519a42655`，与实际输入文件一致；
输入清单引用的 20 份 manifest、20 份在线审计和 20 份评估侧车，共 60 个文件全部匹配声明值。

另保留 seed 42000 的 200v200 单次三维质点全栈 development smoke。该批来自旧 dirty
development 工作区，不能由正式治理结果自动升级。仿真推进 2.2 s，墙钟耗时
60.210 s，实时倍率 0.037。在线共 2,051 条匿名观测，其中 radar 1,966 条、EO 85 条；声学为
0。D1 的 86 个扫描全部释放，重排 10、拒绝 0，峰值缓冲 33 个扫描/623 条观测，结束缓冲为 0，
在线 truth 使用为 0。

| D1 阶段 | 调用次数 | 累计耗时 | 平均耗时 |
| --- | ---: | ---: | ---: |
| 扫描输入整理 | 86 | 2.682 s | 31.186 ms |
| 融合处理 | 86 | 35.115 s | 408.313 ms |
| 无扫描时钟推进 | 44 | 0.001 s | 0.026 ms |
| 扫描尾部关闭 | 1 | 0.0002 s | 0.234 ms |

### 结果判断

正式治理结果证明当前 lateness 配置在这组预注册构造流中可以重排预置乱序且不触发拒绝、过旧
或溢出，缓冲在 episode 结束后归零，且来源、提交和哈希链可复核。clean/formal 治理复跑缺口
据此关闭。它没有执行完整融合，不能用 20 个 episode 的通过结果证明 200v200 实时性、定位
精度或航迹质量。

单次全栈结果暴露了明确的 P1 性能缺口。每个释放扫描都会调用一次 `process_scan_batch()`；
小 EO 扫描与大 radar 扫描都可能触发关联、fixed-lag 重放和完整后验快照。main 的尾部发布合并
减少了下游重复发布，但没有减少 D1 对各释放扫描的后验处理。35.115 s 的 D1 fusion 占本次
60.210 s 墙钟的大部分，当前实现不能据此声称实时。

单次全栈批没有正式 evaluator sidecar 产生的 RMSE、NEES、NIS coverage、近邻召回、错误抑制
或确认时延；相关指标在该批治理报告中为 unavailable。D1 终态 201 条 source track 与 D2 的
200 条 canonical track 也不能直接解释为精度或身份结果。该批只有一个 seed，未覆盖复杂机动、
虚警、持续漏检或长 episode 历史增长。

### 后续验收

1. 在相同冻结输入上按 scan size、modality、正常释放/尾部释放拆分关联、状态获取、历史重放、
   后验物化和证据序列化耗时。
2. 评估同一关闭量测时刻的 release micro-batch、dirty-track-only 重放/快照和跨小扫描缓存复用；
   每帧审计、扫描原子性和一对一关联顺序保持不变。
3. 优化前后对比 track 集、state/covariance、双时间戳、innovation evidence、拒绝原因和在线
   truth 使用；数值等价容差沿用 `1e-9`。
4. clean/formal 快速治理多 seed 已完成；下一步从 clean commit 对 20/50/100/200 运行 D1-only
   与完整全栈未见多 seed，保存硬件、配置、P50/P95/max、峰值内存和实时倍率。另行运行 AirSim
   与传感器精度标定，不混用本节分母。

制品入口：

- `research_modules/scalable_3d_simulation/outputs/observation_governance_calibration_20260722_formal_e4d66db/`；
- `research_modules/scalable_3d_simulation/outputs/point_mass_integrated_observation_smoke_20260722_development_coalesced/`。

## 2026-07-16 Local Image Track 合同回归

本轮是无随机 seed 的 API/合同构造测试，不是 AirSim episode 或传感器精度实验。13 项专项
覆盖 visible、infrared、lost、measurement/arrival 双时间戳、2×2 covariance 深复制、
confidence/quality flags、bbox/center 与 backend/batch metadata、确定性 observation ID、可去重
lineage、多个视觉来源累积，以及 global/truth identity 拒绝。另通过构造后变异验证 D1 边界会
拒绝缺失、non-finite 和 non-PSD covariance；lost 即使被错误附上旧像素也保持 0 输出。

接受阈值与结果：

| 验收项 | 阈值 | 结果 |
| --- | --- | --- |
| 合法可见光/红外字段保真 | 所有指定字段逐项相等 | 通过 |
| lost 旧量测抑制 | 输出数为 0 | 通过 |
| 非法 covariance | 100% fail closed | 通过 |
| global/truth identity | 顶层与嵌套注入 100% 拒绝 | 通过 |
| source lineage | 重复样本 key 相同；不同来源集合累积 | 通过 |
| global ID 边界 | 接受视觉来源后 global ID 不变且不等于 source key | 通过 |
| 专项/全量回归 | 13/13；111/111 | 通过 |

本轮未启动 AirSim，AirSim 默认 `simGetDetections`/detector box 输入、launch/reset/episode 顺序
和截图策略均未改变；seed、样本帧数、RMSE、NIS、NEES 和 runtime latency 不适用。真实
producer 接线、相机模型与 pixel covariance 标定仍需 main 后续 episode 证据。

## 2026-07-15 真实 AirSim M5N2 历史权威增量

本节是当前最新系统证据；后文 3-target RMSE 表和 2026-07-14 专项均为独立历史实验，分母和
用途不能混用。

| 项目 | 结果 | 可用性解释 |
| --- | ---: | --- |
| M5N2 case | 20/20 | baseline 10 + candidate 10 |
| Main-bus timing samples | 3,805 | 逐 case 原始 timing 汇总 |
| D1 fusion mean/P95/max | 320.00/451.46/1234.88 ms | main-bus 内层主导阶段 |
| Main-bus mean/P95/max | 349.34/487.40/1305.99 ms | 与 control-tick 外层是嵌套关系，不相加 |
| Online truth identity/state use | 0/0 | truth 仅允许进入离线评分旁路 |
| NIS/NEES/RMSE | unavailable | 本批不是传感器精度与一致性标定实验 |
| Excluded extra case | 1 | `png_ttc_2v2_seed001`，不计入 M5N2 |
| Dropout case | 0 | 未执行，不补零 |

双时间戳、观测/航迹 covariance 和 NED 合同保持为强制基线。结果说明此前 D1-only batch
replay 的等价性与加速并未关闭真实运行时 P1：D1 fusion 仍占 main-bus 绝大部分时间，100 ms
预算未达到。后续优化必须在相同输入下减少重复 fixed-lag 传播、重放和非关键记录开销，同时
保持全部正式观测和不确定性语义。

证据入口：

- `subagent_reviews/MAIN_M5N2_TIMING_AND_SECOND_PRIMARY_REPORT_20260715.md`；
- `research_modules/airsim_runtime/outputs/p1_terminal_timing_funnel_10seed_20260715_m5n2/m5n2_analysis_summary.json`；
- 同目录 `p1_terminal_closure_summary.json`。

## Scope

This report covers offline research simulation only. It does not include real fire-control parameters, damage logic, vehicle control, hardware drivers, automatic action, or bypass of human authorization.

## Scenario

- Targets: 3
- Baseline: this checked-in report is a historical 3-target baseline; integrated runs size D1 inputs from main `--drone-count N`.
- Duration: 8.0 s
- Base step: 0.50 s
- Seed: 7
- Sensors: delayed range-dependent radar, acoustic bearing with voiceprint hints, EO pixel-box projection.
- Filter: NumPy EKF fallback with fixed-lag measurement-time replay.

## Metrics

| Metric | Value |
|---|---:|
| Compensated RMSE (m) | 2.200 |
| Uncompensated RMSE (m) | 7.732 |
| Compensated track continuity | 0.909 |
| Uncompensated track continuity | 0.909 |
| Compensated grading accuracy | 1.000 |
| Uncompensated grading accuracy | 0.981 |
| Observation count | 153 |
| Mean radar latency (s) | 1.284 |

## Figures

- `tracks_xy.png`
- `rmse_latency_ablation.png`

## Interpretation

The compensated run updates each track at `measurement_timestamp` and replays to the current arrival time. The uncompensated run intentionally updates stale measurements at `arrival_timestamp`, which provides the latency-ablation baseline.

## Online identity-boundary regression (2026-07-14)

This contract regression is separate from the historical RMSE experiment above. It used two EO
batches with two observations each. Target, actor, and truth names changed between batches while
measurement, covariance, both timestamps, bbox, and camera geometry remained identical.

Acceptance required exact field equality after `anonymize_online_observations()`, unchanged numeric
and camera geometry, zero nested identity-key/token leakage, fail-closed rejection of an injected
identity token, and preservation of the original evaluator-only truth sidecar. All four focused tests
passed, and the full D1 suite passed `83/83`. No AirSim episode was run for this API-level regression;
main/runtime call-site integration remains outside this D1-owned report.

## 2026-07-14 关联与固定滞后专项回归

历史 AirSim M5N2 seed-001 记录用于只读根因审计：31.3 秒严格关联失败后产生重复雷达 birth，
31.8 秒固定滞后回放从过旧锚点传播后出现状态跳变。修复内容包括同扫描唯一更新、唯一雷达
重捕、模糊 birth 抑制、非测距修正审计，以及对齐已接受量测时刻的后验检查点和旧 OOSM
archive 回放。

专项测试 `5/5`、D1 全量 `87/87`；main 另行验证 AirSim runtime 全量 `134/134`。这些结果
证明代码和接口回归通过，不代表修复后真实 AirSim 场景已经完成。相同 seed 的第三航迹消除和
31.8 秒连续性仍待 main 复跑确认。

## 2026-07-14 Covariance 合同回归

该回归是 API/合同验证，不是新的 AirSim 或传感器精度实验。构造样本无随机 seed，覆盖 radar
covariance 缺失、非有限、非对称、非半正定和错误维度，以及一条无 covariance 的 legacy
record 显式 offline migration。接受阈值为非法输入在任何滤波状态修改前 `100%` 拒绝，迁移
provenance 完整且 JSON-safe，迁移对象在线入口 `100%` 拒绝，合法 governed replay、OOSM 和
七条 AirSim freeze fixture 行为不回归。

D1 全量结果为 `92/92 passed`，满足上述阈值。本轮未启动真实 AirSim，样本 seed 不适用，也
未产生新的 RMSE/NIS/NEES 数值。offline migration 使用的 model default 仅用于历史 evaluator
兼容；真实 radar/acoustic/EO/lidar covariance、故障/遮挡 scale 与长期 consistency 仍待多
seed 真实数据标定。

## 2026-07-14 同帧批量 fixed-lag 性能与等价性报告

### 目的与方法

本次不启动 AirSim，而是使用两类输入验证 D1-owned 优化：第一类为无随机 seed 的构造性
5 航迹、15 条同帧 radar/lidar/acoustic observation；第二类为已有
`p1_terminal_closure_semantics_v2_seed1_20260714_m5n2_baseline_seed001` 的前 40 帧持久化
`blocks_sensor_observations.jsonl`，共 786 条 observation。两个适配器从相同配置和输入顺序
开始，分别逐条 `process()` 与按 frame `process_batch()`，比较最终航迹、状态、covariance、
时间审计和 `_replay_record` 实际调用次数。

接受条件为：

- 不改变输入 measurement/arrival timestamp、covariance、frame、modality 和 source lineage；
- 最终 track ID 集合一致；state/covariance 最大绝对差不超过 `1e-9`；
- 构造场景 history replay 至少下降 50%；
- duplicate、OOSM 和 fixed-lag 边界专项全部通过。

### 结果

| 场景 | 逐条 history replay | batch history replay | 逐条耗时 | batch 耗时 | 数值差异 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 5 航迹、15 条同帧多模态构造输入 | 95 | 24 | 未作为验收量 | 未作为验收量 | `<=1e-9` |
| M5N2 seed-001 前 40 帧、786 条持久化观测 | 1267 | 351 | 18.05 s | 5.70 s | 0 |

构造场景 replay 减少 74.7%；真实持久化输入 D1-only 加速约 3.17 倍、replay 减少 72.3%。
batch summary 在构造场景记录 61 次 cache hit、19 次 miss、5 次终结 replay，并将 15 次接受
更新的逐次发布收敛为 5 个航迹终结发布。专项 `6 passed`，D1 全量 `98 passed`，格式检查通过。

### 结论与限制

结果证明性能瓶颈确由重复 fixed-lag replay 主导，批处理在不减少证据的前提下可显著降低计算，
并保持当前逐条路径的数值结果。该结论仅针对 D1-only 重放；main 尚未改用接口，完整 AirSim
循环的 RPC、观测生成、日志和 D6 报告耗时未包含。下一步由 main 接线后复测完整 245/248 帧
和多 seed，若仍超 100 ms，应继续按分项 profile 治理，不能通过丢观测或改时间戳达标。

## 2026-07-20 可扩展三维扫描融合合同报告

本轮没有启动 AirSim。输入来自 main-owned 三维质点 producer，schema 为
`scalable3d-world-v1`/`scalable3d-observation-v1`，固定 seed 7；雷达探测率仅为合同验收设为
1.0。5/20/50/100/200 五档各运行初始扫描和 0.2 s 后第二扫描，共 10 batch、750 条在线匿名
radar measurement。接受阈值为：首扫航迹数等于点迹数、第二扫 100% 一对一更新且不新建、
ID 集不变、状态有限、covariance 为半正定 `6x6`、在线身份真值读取为 0。

| 规模 | 首扫 birth/track | 次扫 update/track | 未接受量测 |
| ---: | ---: | ---: | ---: |
| 5 | 5/5 | 5/5 | 0 |
| 20 | 20/20 | 20/20 | 0 |
| 50 | 50/50 | 50/50 | 0 |
| 100 | 100/100 | 100/100 | 0 |
| 200 | 200/200 | 200/200 | 0 |

补充合同包括：2 目标、3 scan/6 measurement 中 2 条迟到量测被识别并按 OOSM 重放，航迹数
保持 2；单声学节点 5 条二维 bearing 在无雷达先验时 0 birth、有先验时 5 update；注入
truth/actor/object ID 全部 fail closed；球坐标原 `3x3` covariance 在 canonical radar
observation 中逐元素保留并传播为 `6x6` NED covariance。专项 `9/9`、D1 全量 `120/120`。

开发期间一次本机非门限化探针记录 200 点首扫约 0.108 s、次扫约 0.392 s。该单次结果没有
预热、重复统计或置信区间，不能作为实时验收。当前结论只关闭 D1 扫描级适配、批量 birth/
update、OOSM 和类别声纹边界；多 seed 漏检/虚警/交叉场景 recall、false-track 生命周期、
IDSW、RMSE/NIS/NEES、D2 六维关联和 main 总线接线仍开放。

## 2026-07-20 无多普勒六维速度稳定性报告

### 场景与方法

本轮没有启动 AirSim。输入为 scalable 3D radar-only 匿名批次，radar detection probability
设为 1.0 以隔离速度滤波行为。正式自动化规模为 seed 17、200 条航迹、10 个 scan（measurement
time `0.0..1.8 s`，周期 0.2 s），共 2,000 条 measurement。D1 在线路径只接收 range、
azimuth、elevation、covariance、双时间戳、sensor/scan lineage，不接收 truth/actor/object ID，
也不读取场景 4.7 m/s 上界。

修复将无多普勒量测从“补零后四维更新”改为“canonical 四维占位、滤波三维更新”，速度起始为
`v0=0`、`Pvv=25I m2/s2`、`Ppv=0`。三维更新使用 `chi2_3(0.999)=16.2662` NIS 门限，并输出
replay innovation/update/rejection 审计。

### 验收与结果

| 项目 | 样本/阈值 | 结果 |
| --- | --- | --- |
| 量测/先验合同 | 1 条三值 radar；滤波维数必须为 3，`Pvv=25I`、`Ppv=0` | 通过 |
| 创新门控 | 3 scan；离群点保持在关联门限 40 内但超过 NIS 16.2662；必须 1 次拒绝并留审计 | 通过 |
| OOSM 等价 | 2 航迹、顺序/乱序各 3 scan；共同发布时刻 state/covariance 差 `<=1e-9` | 通过，2 条 OOSM，双时间戳和 `6x6` covariance 保持 |
| 200 条多帧 | seed 17、10 scan、2,000 条匿名 measurement；数量/ID/有限性全程保持 | 200/200，ID 集不变 |
| 末帧速度 | 不使用真实速度上界；检查均值相对显式 covariance 不发散 | median/P90/max=`3.87/6.43/8.54 m/s` |
| 末帧速度 covariance trace | 不得坍缩或隐藏 | median/P90/max=`57.97/60.69/61.19` |

同一 seed 的 50 条开发探针用于对照根因，修复前后 D1 速度由
`6.28/12.16/21.03` 变为 `3.99/6.12/9.69 m/s`；修复后速度 covariance trace 仍为
`58.22/60.43/60.90`。专项测试 `13/13`，D1 全量 `124/124`。

### 结论与限制

D1-owned 的补零径向速度误用和短基线速度均值放大缺口已关闭。结果不是硬限速：速度状态仍可
超过任意场景速度，后验同时携带较大的显式方差。零均值固定先验会收缩早期速度，至少 20 个
未见 seed 的速度误差 coverage、NIS/NEES、机动、漏检/虚警和门控率仍未完成。D2 会再次滤波
D1 六维输出，D2 速度和 D3 第二轮分配数量需由 main 使用当前代码正式复测。本轮未改变 AirSim
producer/runtime、launch/reset/episode 顺序或持久化 schema。

## 2026-07-20 Scalable 3D consistency evidence 合同报告

### 场景、样本与接受条件

本报告验证 evaluator contract，不做正式精度标定。构造 provenance 使用 scenario
`scalable-consistency-contract`、run `seed-019`；测试是确定性 oracle，不是随机 seed-19
性能样本。新增 12 项覆盖：3 条 radar 初始化/接受/门控拒绝、顺序与迟到 OOSM、四档 range、
acoustic/EO available/unavailable、1/4/7 输入规模、缺失/错误 D2 observation-lineage mapping、
在线额外 truth 字段拒绝、truth/hash 篡改、
六维与时间错位、奇异 covariance 和 non-finite 输入。

接受条件为：在线字段无 truth/actor/object identity key；records/content hash 可验证；OOSM 最终
state/covariance 与顺序处理差 `<=1e-9`；缺失或不一致输入不产生 truth metric；奇异 covariance
不产生 NEES；所有 bundle 可由 `json.dumps(..., allow_nan=False)` 序列化；记录数量等于输入，
不依赖 2v2/5v5。

### 结果

| 项目 | 结果 |
| --- | --- |
| innovation evidence | 一条 accepted、一条 rejected，均保留 3 维 NIS/gate；初始化 NIS unavailable |
| OOSM | 迟到记录标记 replay，最终 update state/covariance 与顺序路径 `<=1e-9` |
| range/multimodal | 四档 radar range 正确；无 track acoustic/EO 显式 unavailable；acoustic update NIS available、gate coverage unavailable |
| evaluator oracle | position RMSE `5 m`；velocity RMSE `12 m/s`；两条 gated update coverage `0.5`；NEES 有限 |
| fail closed | 缺 lineage mapping、未知 truth、digest mismatch、在线额外 truth 字段、truth 篡改、维数/时间错位全部拒绝或 unavailable |
| singular/finite | RMSE 保持 available，NEES unavailable；NaN online artifact 整体拒绝且输出无 NaN |
| tests | 新增专项 `12 passed`；main 复跑 D1 全量 `136 passed` |

### 结论与限制

D1-owned 的逐更新持久化 DTO、schema/hash/source provenance、基于 observation lineage 的
离线严格对齐和聚合 row 合同已
关闭。没有修改 EKF/量测模型/门限/track ID，也没有执行 AirSim 或正式多 seed 实验。上述
`5 m/12 m/s/0.5` 是故意设置的 oracle，不是算法表现。按 sensor/range/scenario 的正式多 seed
RMSE、NEES、NIS coverage、置信区间和验收阈值仍未闭合。

## 2026-07-22 扫描输入整理合同回归

本轮是纯 Python API/合同测试，不是 AirSim episode，也不测融合精度。输入为构造的匿名 radar
扫描，无随机 seed。测试把完整扫描按 arrival 顺序提交给 `ScanInputOrganizer`，检查
measurement-time 水位线、有限缓冲和整帧拒绝，再把 `released_scans` 交给既有
`Scalable3DFusionAdapter.process_scan_batch()`。

| 验收项 | 样本与阈值 | 结果 |
| --- | --- | --- |
| 有序与窗口内乱序 | 释放顺序必须按 measurement time；双时间戳和 covariance 逐项不变 | 通过 |
| 超窗迟到 | 7 点扫描必须整帧拒绝，释放数为 0 | 通过 |
| 同时间多源 | 两来源 4 点和 6 点扫描均保留，不发生 scan-key 冲突 | 通过 |
| duplicate/replay/conflict | 三类分别计数，均不进入 released scans | 通过 |
| 时间/数量上限 | arrival regression、scan/observation overflow、residence expiry 均 fail closed | 通过 |
| 动态数量 | 1、7、200 点扫描无固定 2v2/5v5 假设 | 通过 |
| 在线身份边界 | truth 注入在 claim/digest 前拒绝 | 通过 |
| 只读视觉元数据 | 嵌套 `mappingproxy` 可建立独立只读快照；嵌套 truth 仍拒绝 | 通过 |
| main 组合路径 | `OnlineSensorBatch -> SensorScanFrame -> released_scans -> process_scan_batch` | 通过，3 条六维航迹 |
| 测试 | 专项/全量 | `15/15`；`151/151` |

结果证明 D1-owned 的扫描释放边界可执行。它没有改变 EKF、fixed-lag replay、关联门限或
`global_track_id`。未运行 AirSim，未给出 RMSE/NIS/NEES、实时吞吐、too-late 误拒率或长 episode
容量结论。main 仍需在 20/50/100/200 规模下接线并标定配置。
