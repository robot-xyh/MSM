# 第一研究模块实验结果

## 冻结 replay 尾延时 profiler 与完整帧复用

**证据日期：2026-07-23**

**冻结输入来源：clean `4ac3bb2c12cc6af6ebd372107ced00bcdc5adf6a`**

**场景与样本：`200v200-nominal-v1`，10 s，seed 1000，771 scans /
11,889 observations，单 episode**

冻结输入 SHA-256 为
`c1dda8523e48c255bbeef48d9516b05863eb1bbb3a3ae2e09733259e6a66f77a`。clean episode
原始 D1 fusion P50/P95/max 为 `33.252/224.764/592.957 ms`，scan-input 为
`1.747/177.084/361.536 ms`。

### Scan-input 结果与验收

| 项目 | 再快照参考路径 | 完整帧复用路径 |
| --- | ---: | ---: |
| organizer 内帧重建 | 771 | 0 |
| organizer 内 observation 快照 | 11,889 | 0 |
| `ScanInputOrganizer.ingest` cProfile 累计 | 15.545 s | 5.754 s |
| `SensorScanFrame.__post_init__` cProfile 累计 | 9.710 s | 0 s |
| `_claim_for_frame` cProfile 累计 | 5.681 s | 5.580 s |

前 256 scans 交错 5 轮的总耗时 P50/P95 为
`1.942/1.968 s -> 0.881/0.894 s`，P50 比 2.204x。墙钟不参与通过判定。14 项严格 acceptance
全部通过，包括逐输入结果、close/audit、release schedule、逐 fusion 状态/协方差/双时间戳/
谱系/分级、物化航迹、终态、一致性证据、逐 fusion 操作数及累计诊断。关键哈希：

- fusion semantic：`sha256:e5d4ec2ee902b1fa9e423f7b08380e14a08efec254cea193fad4611a022f4244`
- operation snapshots：`sha256:82728a8e0fed0adedd0254368e29a3c117157b066158595d7ca6dac558bfb5bf`
- diagnostic snapshots：`sha256:b28df84d6664ba17d097990f7186a2a611f2e3469394e3d2a12122dbec521766`
- final tracks：`sha256:b53d506ee3bd4d9a50a3635387832db0c5321f74ccf3f77c18993e3892763d98`

main 实测当前 D1 全量回归为 `185 passed`；这是当前工作区权威测试结果。

### Fusion 归因

fusion 数学路径未修改。cProfile 主要累计路径为 `global_tracks 17.559 s`、扫描一对一关联
`17.027 s`、`_to_global_track 16.930 s`、非雷达代价矩阵 `14.971 s` 和 replay
`8.601 s`。未剖析工作区复放 P50/P95/max 为 `34.108/178.420/354.413 ms`；48 个 radar
scans 的 P95 为 `343.059 ms`，物化扫描 P95 为 `216.991 ms`。候选对峰值 40,000，单扫描
fixed-lag rebase 峰值 197。

该工作区分位只用于和同轮操作数及 cProfile 配对，不与 clean episode 作正式前后比较。
GlobalTrack 物化、radar candidate/rebase 和剩余 audit/lineage/JSON 摘要继续为 P1。

### 限制与证据路径

clean/commit 仅描述冻结输入来源；优化和等价复放运行在当前未提交 D1 工作区。该实验是单 seed
三维质点 replay，不是新的 clean full-stack、AirSim、正式多 seed 或实时放行，且不新增
RMSE/NEES/NIS 或物理拦截效果证据。

- `../reports/d1_tail_latency_performance_20260723.json`
- `../reports/D1_TAIL_LATENCY_PERFORMANCE_20260723_CN.md`

## Nominal 200v200 clean 单 seed 全栈校准

**证据日期：2026-07-22**

**参考/候选提交：clean `0d2da25c14e50f8f9a10ad47a7bd74e5c5e577fb` / detached clean
`4ac3bb2c12cc6af6ebd372107ced00bcdc5adf6a`**

**场景与样本：`200v200-nominal-v1`，10 s，seed 1000，200 个目标、200 个资源，单 episode**

### 验收方法

本轮是描述性 clean 校准。接受条件是参考与候选均来自 clean source，seed、场景版本、时长和
配置相同，候选状态有限且在线 truth 使用为 0，并且跨构建审计中的规范在线载荷、离线 truth
state、计划谱系模式及两端计划谱系有效性全部通过。性能数据用于同口径描述，不构成正式放行
门限；实时判断仍要求核心 RTF 至少达到 1。

两端各处理 771 个 D1 扫描和 11,889 条匿名在线观测。跨构建审计结果为
`normalized_online_payloads_equal=true`、`truth_state_equal=true`、
`plan_lineage_pattern_equal=true`、`reference_plan_lineage_valid=true` 和
`candidate_plan_lineage_valid=true`，总审计 `passed=true`。

### 结果

| 指标 | clean `0d2da25` | clean `4ac3bb2` | 候选变化 |
| --- | ---: | ---: | ---: |
| 核心 wall | 94.104939744 s | 85.002427712 s | 下降 9.6727%，1.1071x |
| 核心 RTF | 0.1062643 | 0.1176437 | 仍未实时 |
| D1 fusion 累计 | 49.697406826 s | 40.272795088 s | 下降 18.9640%，1.2340x |
| D1 scan input 累计 | 12.315225105 s | 12.560936034 s | 增加 1.9952% |
| 在线观测数 | 11,889 | 11,889 | 相同 |
| 在线 truth 使用 | 0 | 0 | 相同 |

候选 771 次 D1 fusion 调用的 P50/P95/max 为
`33.25249/224.76351/592.95713 ms`。参考计时 schema 没有阶段分布字段，因此本次不构造参考
分位数，也不把候选累计下降解释为尾延时已关闭。

### 进程资源口径

候选核心 wall 85.002427712 s 来自 `summary.json.wall_time_s`。外部 `/usr/bin/time` 记录的
总进程 elapsed 为 `1:55.95`，峰值 RSS 为 `2,468,928 KiB`。外部 elapsed 还包含解释器启动、
离线后处理和制品落盘，不能与核心 wall 混写，也没有用于 9.6727%/1.1071x 的核心比较。

### 判定与限制

语义接受条件全部通过，候选核心和 fusion 累计时间较同 seed 基线下降；但核心 RTF 只有
0.1176437，fusion P95/max 为 224.76351/592.95713 ms，scan input 反而增加 1.9952%。因此
D1 融合尾延时和 scan-input 均继续作为 P1。

本批只有 seed 1000，是单 seed 描述性 clean 校准，不是 20-seed，不是正式性能矩阵，未达到
实时。它不新增 AirSim、真实传感器精度、正式 RMSE/NEES/NIS 或物理拦截效果证据。

只读证据目录：

- `/tmp/MSM-scalable3d-candidate-4ac3bb2/research_modules/scalable_3d_simulation/outputs/scalable_3d_timing_v2_clean_4ac3bb2_20260722/10p0s_seed_1000_nominal/`
- `/tmp/MSM-scalable3d-candidate-4ac3bb2/research_modules/scalable_3d_simulation/outputs/scalable_3d_timing_v2_clean_4ac3bb2_20260722/cross_build_seed_1000_nominal/`

## 非雷达创新批处理

**证据日期：2026-07-22**

**冻结输入：未见 seed 1000，10 s，771 个扫描，11,889 条匿名观测**

函数剖析把当前最大 D1 fusion 热点定位到非雷达扫描代价矩阵。旧路径为每个航迹-观测候选单独
调用伪逆。候选路径保留每条观测的量测和协方差，只把相同量测几何和形状的创新协方差组成矩阵
栈。每个候选的残差、马氏二次型、门限和 Hungarian 分配不变，矩阵栈失败时逐候选回退。

| 口径 | 逐候选路径 | 批处理路径 | 结果 |
| --- | ---: | ---: | --- |
| 前 256 扫描 P50，7 次 | 12.242 s | 10.238 s | 1.196x |
| 前 256 扫描 P95，7 次 | 13.340 s | 11.248 s | 下降 15.7% |
| 前 256 扫描均值，7 次 | 12.506 s | 10.385 s | 1.204x |
| 完整 771 扫描，无 profiler | 50.458 s | 39.994 s | 1.262x |
| 完整 cProfile 非雷达代价矩阵 | 34.307 s | 17.320 s | 调用链下降 |
| 完整 cProfile `pinv` 调用 | 496,625 | 1,018 | 下降 99.8% |

稳定性基准在同一 Python 进程中执行，每个变体先预热 128 个扫描一次，再交错运行 7 次。所用
前缀含 256 个扫描和 4,087 条观测，终态 201 条航迹。逐扫描语义摘要、终态航迹、一致性证据、
全部操作计数和累计诊断严格一致，在线 truth 使用为 0。该 2026-07-22 非雷达专项当次历史
回归为 `182 passed in 15.92s`，不是当前权威测试计数。

证据见 `../reports/D1_NON_RADAR_INNOVATION_PERFORMANCE_BENCHMARK_CN.md` 和对应 JSON。本组关闭
D1 冻结回放的逐候选伪逆热点，不证明完整 D1-D7 实时、AirSim 性能或真实融合精度。

## 一致性证据计数刷新

**证据日期：2026-07-22**

**冻结输入来源：clean `f80b5bd`，10 s，seeds 42000、42001、42002**

参考路径在每次合法缓存证据刷新时执行完整 dataclass 构造校验。候选路径只从已验证冻结记录
复制不变字段，并校验新的非负 replay revision/count。两条路径使用同一扫描释放计划、6 s
fixed-lag、关联和滤波配置。没有缩短窗口、跳过观测、改变门限或使用在线 truth。

| Seed | 扫描/观测 | 终态航迹 | 完整重验 | 受限复制 | 加速 | 严格语义 |
| ---: | ---: | ---: | ---: | ---: | ---: | :---: |
| 42000 | 764/12,107 | 202 | 61.655 s | 48.804 s | 1.263x | 通过 |
| 42001 | 844/11,922 | 207 | 67.316 s | 55.069 s | 1.222x | 通过 |
| 42002 | 782/11,825 | 203 | 65.562 s | 54.096 s | 1.212x | 通过 |
| 均值 | - | - | 64.844 s | 52.657 s | 1.231x | 3/3 通过 |

严格语义检查覆盖每一扫描的状态、协方差、时间戳、来源谱系和航迹分级，以及终态航迹、最终逐
观测一致性证据、全部操作计数和 state-only/full 物化计划。三个 seed 的在线 truth 使用均为 0。
代表 seed cProfile 中，缓存证据刷新累计 `27.122 -> 1.664 s`，历史重放累计
`35.348 -> 9.410 s`。D1 全量测试 `178 passed in 14.80s`。

本次关闭缓存证据重复完整校验热点。候选仍需平均 52.657 s 处理 10 s 冻结输入，不能据此认定
实时。非雷达扫描代价矩阵、航迹物化、scan input、长于 10 s 的增长率、AirSim 和正式
RMSE/NEES/NIS 继续保持开放。

## 最终跨提交集成复核

**证据日期：2026-07-22**

**参考/候选提交：`8f86192` / `f80b5bd`**

**场景：`200v200-nominal-v1`，仿真时长 10 s，seeds 42000、42001、42002**

### 方法

参考和候选均从 clean 工作区独立运行相同场景。验收先比较 seed、场景版本、时长、完整配置、
真值侧车和在线主题计数，再逐条比较在线载荷。D3 每次独立规划产生的不透明 `plan_id` 按出现次序
和版本归一化。归一化前先校验 ACK 原始载荷 SHA；计划 owner/version/coalition、
`global_track_id`、导引 command 及其他业务字段不被忽略。

验收条件为 3/3 seed 的来源工作区 clean、状态有限、在线 truth 使用 0、场景合同一致、D1 终态
航迹数一致，并且逐条在线业务载荷审计全部通过。任一 seed 不满足即不接受本组集成等价结论。

D1 的 `association_innovation_solve_count` 只记录实际执行的精确伪逆次数。它是允许变化的性能
诊断，不参与业务等价判定。候选实现只对通过有限性、严格对称、Gershgorin 正定下界和 `pinv`
cutoff 认证的雷达创新协方差应用预门控；所有未认证矩阵保留原精确 `pinv` fallback。

### 结果

| Seed | 参考/候选 D1 fusion | 参考/候选 scan input | 精确求解参考/候选 | 终态 D1 航迹参考/候选 | 逐条语义审计 |
| ---: | ---: | ---: | ---: | ---: | :---: |
| 42000 | 89.796179/87.209720 s | 16.999921/18.233643 s | 2,393,969/511,264 | 202/202 | 通过 |
| 42001 | 96.598587/92.323182 s | 16.902916/17.148000 s | 2,387,139/527,925 | 207/207 | 通过 |
| 42002 | 92.578497/85.458411 s | 16.805091/17.191083 s | 2,349,120/539,488 | 203/203 | 通过 |
| 均值/合计 | 92.991088/88.330438 s | 16.902643/17.524242 s | 7,130,228/1,578,677 | - | 3/3 通过 |

D1 fusion 三 seed 均值下降约 5.01%，精确创新求解下降约 77.86%。scan input 均值增加约
3.68%。三个 seed 均为有限状态，`online_truth_use_count=0`；D1、D2、D3、D5、D7 最终数量均
保持。D1 fused-track、传感器观测及其余在线主题的规范哈希逐 seed 一致。

### 判定

该结果证明 `f80b5bd` 的 D1 预门控在当前三组 integrated 200v200 输入上保持业务语义，并降低
融合分项和精确创新求解成本。solve count 不能作为定位精度、召回率或业务效果指标。scan input
没有同步改善，候选 10 s episode 的系统实时倍率仍显著低于 1，当前长时比较仍把 D1 scan
input、D1 fusion 和 module stack 标为归一化超线性。因此系统实时/长时超线性 P1、AirSim 和
正式 RMSE/NEES/NIS 均未关闭。

证据目录：

`../../scalable_3d_simulation/outputs/scalable_3d_long_duration_candidate_20260722_clean_f80b5bd/`

## 雷达预门控严格等价复核

**证据日期：2026-07-22**

**冻结输入来源：clean candidate `8f86192`**

本次复核针对雷达候选预门控。候选路径只对有限、严格对称、通过 Gershgorin 严格正定及
`pinv` cutoff 安全裕量认证的创新协方差使用马氏距离下界。未认证矩阵全部执行旧精确
`np.linalg.pinv`。测试另构造非正定交叉协方差和近奇异截断矩阵，使旧 `pinv` 代价在门内而
朴素 trace 下界在门外；两类 rejection mask 均未预拒绝，扫描级参考和候选后验一致。

| Seed | 扫描/观测 | 旧路径 | 新路径 | 加速 | 精确求解旧/新 | 完整/状态快照 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 42000 | 764/12,107 | 90.007 s | 84.613 s | 1.064x | 2,393,969/511,264 | 454/310 |
| 42001 | 844/11,922 | 94.712 s | 94.079 s | 1.007x | 2,387,139/527,925 | 516/328 |
| 42002 | 782/11,825 | 89.220 s | 87.165 s | 1.024x | 2,349,120/539,488 | 504/278 |
| 均值/合计 | - | 91.313 s | 88.619 s | 1.030x | 7,130,228/1,578,677 | - |

3/3 candidate 更快。每个 seed 的逐扫描后验、终态航迹和一致性证据哈希完全相同；候选对、
固定滞后操作数、扫描/观测数以及 state-only/full 调度保持不变。精确创新求解下降 77.9%。
专项 `6 passed`，D1 全量 `175 passed in 26.69s`。

结果只适用于当前冻结三维质点输入和本机环境。优化路径处理 10 s 输入仍平均需要 88.619 s，
没有形成实时闭合，也没有增加 AirSim、真实雷达精度或正式 RMSE/NEES/NIS 证据。

## Clean 200v200 全栈接线复跑

**证据日期：2026-07-22**

**候选提交：`8f86192`**

**场景：200 个目标、200 个资源的三维质点全栈，仿真时长 10 s**

### 验收方法

clean 候选路径启用同一 fusion timestamp 延迟物化。扫描整理器释放的每个扫描仍按原顺序调用
D1；中间后验写入 state-only 发布，该 fusion timestamp 的最后后验写入完整 `GlobalTrack`
快照。对照路径为
旧 clean 提交 `3bac3ff`。两条路径使用相同 seed 和场景配置。

验收要求为：工作区 clean、状态有限、在线 truth 使用为 0、D1/D2 无 overflow、安全合同通过；
扫描总数必须等于 state-only 与完整快照数量之和；事件、scan input、共享摘要和世界真值必须与
旧路径对应 seed 相同。

### 结果

| Seed | 扫描数 | 匿名观测数 | State-only | 完整快照 | 旧 D1 fusion | 新 D1 fusion |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 42000 | 764 | 12,107 | 310 | 454 | 103.176 s | 89.796 s |
| 42001 | 844 | 11,922 | 328 | 516 | 106.447 s | 96.599 s |
| 42002 | 782 | 11,825 | 278 | 504 | 100.394 s | 92.578 s |
| 均值 | - | - | - | - | 103.339 s | 92.991 s |

3/3 episode 均为 clean、finite，在线 truth 使用 0，D1/D2 overflow 和安全合同全部通过。
D1 fusion 三 seed 均值下降 10.0%。seed 42000 的 2.2 s 全栈墙钟由 18.611 s 降至
18.302 s。每个 seed 的 state-only 与完整快照之和等于扫描总数；事件、scan input、共享摘要和
世界真值与旧提交 `3bac3ff` 对应 seed 相同。

### 结果解释

本次结果证明 main 已按 D1 接口完成延迟物化接线，并在三个 clean seed 上保持逐扫描融合和发布
语义。下降来自同一运行时刻中间 `GlobalTrack` 快照不再重复构造，不来自合并扫描、删除观测、
缩短固定时滞窗口或改变协方差和门控。

D1 fusion 对 10 s 输入仍平均耗时 92.991 s，实时预算没有闭合。本组是三维质点证据，不是
AirSim、真实传感器精度、RMSE、归一化估计误差平方、归一化创新平方或物理拦截验收。证据目录：

`../../scalable_3d_simulation/outputs/scalable_3d_long_duration_candidate_20260722_clean_8f86192/`

历史模块级性能、融合精度和时延消融实验见 `../reports/EXPERIMENT_REPORT.md`。
