# D1 Sensor Fusion Offline Experiment Report

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
