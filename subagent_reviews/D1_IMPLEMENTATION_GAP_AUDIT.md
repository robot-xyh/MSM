# D1 实现差距审计

**模块**: D1 多传感器融合与目标配准  
**范围**: 对照 `subagent_reviews/D1_SENSOR_FUSION_REVIEW_AND_PLAN.md`、`C_UAS_MAINSTREAM_SOLUTIONS_AND_DIFFICULTIES.md`、`research_modules/d1_sensor_fusion` 源码和测试，审计共识算法、开源方案和当前实现差距。  
**边界**: 本审计只覆盖离线科研仿真、数据合同、传感器观测、航迹融合和评估接口；不涉及真实飞控、硬件驱动、火控、毁伤或自动处置。

**更新时间**: 2026-07-23。

## 0. 当前正式治理 GAP 增量（2026-07-23）

| GAP/合同 | 当前状态 | 2026-07-23 证据 | 剩余关闭条件 |
| --- | --- | --- | --- |
| Scan-input claim 重复 JSON 规范化 | **D1-owned 热点已关闭；clean 多 seed 集成收益 P1 开放** | clean `5263e2b` nominal 200v200/10 s/seed 1000 冻结输入，771 scans/11,889 obs/SHA-256 `5d033a04...67ce8f`。旧/新 claim registry、逐输入事件、发布顺序、逐 fusion 状态/协方差/双时间戳/谱系/分级、操作计数、累计诊断、终态和一致性证据严格一致；registry hash 均为 `22a71336...b8fd7`。771 scans 交错 5 轮 P50/P95 `3.618/4.049 -> 1.905/2.038 s`，P50 1.899x；`_json_safe` cProfile `5.781 -> 1.992 s`。全量 `185 passed`。原 clean 20-seed 基线 scan-input/fusion 累计均值为 `9.671/43.774 s`，episode P95 均值 `135.454/233.488 ms` | main 在当前候选提交复跑预注册多 seed clean full-stack，比较 episode scan-input P50/P95/max、核心 RTF 和 RSS。不得把单 seed函数级计时直接外推成 20-seed 或实时收益 |
| 尾延时 profiler 与完整帧复用 | **重复 frame/observation 快照热点已在 D1 冻结 replay 关闭；fusion 与 clean full-stack P1 开放** | clean `4ac3bb2` nominal 200v200/10 s/seed 1000 冻结输入，771 scans/11,889 obs/SHA-256 `c1dda852...66f77a`；帧重建 `771 -> 0`、再快照 `11,889 -> 0`；前 256 scans 交错 5 轮 P50/P95 `1.942/1.968 -> 0.881/0.894 s`，墙钟不参与验收。逐输入、逐 fusion 状态/协方差/双时间戳/谱系/分级、物化航迹、终态、证据、逐扫描操作数及累计诊断全部严格一致；operation hash `82728a8e...bfb5bf`；main 实测当前 D1 全量 `185 passed`。fusion cProfile 仍由 GlobalTrack 物化、扫描关联、代价矩阵和 replay 主导 | claim 重复 JSON 规范化已由最新一项关闭；继续治理非 claim audit/event、长期 claim registry 内存、GlobalTrack 物化及 radar/rebase，但不得缩窗口、丢观测、降频、放宽门控或使用 truth。当前工作区复放非 clean 放行、非 AirSim、非正式多 seed、未实时 |
| Nominal 200v200 clean 性能校准 | **单 seed 语义校准通过；fusion 尾延时、scan-input 与正式矩阵 P1 开放** | detached clean `4ac3bb2` 对 clean `0d2da25`，10 s/seed 1000/11,889 online obs，finite 且 online truth 0；核心 wall `94.104939744 -> 85.002427712 s`（-9.6727%，1.1071x），D1 fusion `49.697406826 -> 40.272795088 s`（-18.9640%，1.2340x），scan input `12.315225105 -> 12.560936034 s`（+1.9952%），候选 RTF `0.1176437`，fusion P50/P95/max `33.25249/224.76351/592.95713 ms`；规范在线载荷、truth state、计划谱系均通过。外部总进程 `1:55.95`、峰值 RSS `2,468,928 KiB` 与核心 wall 分列 | 执行冻结硬件/配置的预注册 20-seed 正式矩阵；RTF 达到实时目标并收敛 fusion P95/max；单独治理 scan-input。当前不是正式矩阵，不关闭 AirSim 或 RMSE/NEES/NIS |
| 非雷达逐候选创新伪逆 | **D1-owned 热点已关闭；全栈实时 P1 仍开放** | 未见 seed 1000 的 10 s 冻结输入为 771 scans/11,889 obs/201 tracks。前 256 scans 同进程预热后交错 7 次，P50 `12.242 -> 10.238 s`、P95 `13.340 -> 11.248 s`；完整输入 `50.458 -> 39.994 s`。逐扫描、终态、证据哈希及全部操作计数/累计诊断相同，在线 truth 0；`pinv` 调用 `496,625 -> 1,018`；2026-07-22 专项当次历史回归 `182 passed`，不是当前权威计数 | 完整帧再快照和 claim 重复 JSON 规范化已由后续项关闭；main 仍需复跑 clean 多 seed 全栈并重算 RTF/RSS，D1 继续治理航迹物化、非 claim audit/event 和长期内存。不得把模块单 seed 墙钟写成系统实时结论 |
| 缓存一致性证据重复完整校验 | **D1-owned 热点已关闭；系统 P1 仍开放** | clean `f80b5bd` 10 s seeds 42000-42002；完整重验/受限复制纯融合均值 `64.844/52.657 s`，加速 `1.231x`，3/3 更快。逐扫描状态/协方差/时间戳/谱系/分级、终态、一致性证据和全部操作计数严格一致，在线 truth 0；代表 seed 刷新累计 `27.122 -> 1.664 s`，D1 全量 `178 passed` | 非雷达逐候选伪逆已由后续项关闭；当前扩展长于 10 s、未见 seed、固定硬件 P50/P95/max、RSS、航迹物化、scan input 和端到端实时倍率，不得把 standalone 墙钟写成 integrated 实时证据 |
| 最终跨提交 integrated 语义复核 | **当前三 seed 已关闭；系统 P1 仍开放** | clean `8f86192 -> f80b5bd`，200v200 nominal、10 s、seeds 42000-42002；逐条总线语义审计 3/3 通过，D1 终态航迹均为 `202/207/203`，finite 且在线 truth 0。仅按 occurrence/version 归一化 opaque `plan_id`，ACK 原始载荷 SHA 先校验，owner/version/coalition/global track/command 仍参与比较 | 扩展未见 seed 和时长；保持相同跨提交审计规则，不能以数量相同替代逐条语义比较 |
| 长时 fixed-lag 超线性增长 | **D1-owned 冻结输入缺口已关闭；系统 P1 仍开放** | 10 s/764 scans/12,107 obs 对照中，history replay `170,106 -> 13,397`、filter update `120,440 -> 9,549`、墙钟 `157.237 -> 107.449 s`；clean 三 seed 全栈 D1 fusion 均值进一步为 `103.339 -> 92.991 s` | 扩展更长时和未见 seed，冻结硬件和周期预算；D1 不以丢观测、缩短 6 s fixed-lag、放宽 gate 或使用 truth 换性能 |
| 同一 fusion timestamp 重复全量快照物化 | **D1-owned 接口与 main 质点集成项已关闭** | 默认 API 不变；clean `8f86192` 三 seed 的 state-only/完整快照为 `310/454`、`328/516`、`278/504`，逐例合计全部扫描；事件、scan input、共享摘要和世界真值与旧 clean 相同 | 保持语义回归；AirSim writer、跨 tick heartbeat/lineage 和实时预算另行验收 |
| D1 全量快照持久化 | **审计 v2 已实现；跨 tick 策略仍开放** | 旧基线 764 条约 186.2 MiB；新 audit 分别统计 publication/materialized/state-only/track records，兼容 v1 数组日志和 state-only 的空数组或过渡 null | main 后续评估跨 tick heartbeat/lineage sidecar；必须保留状态/身份/生命周期/质量/lineage 事件并支持 D6 重建。D1 不修改 main 发布器 |
| 扫描水位线 clean/formal 复跑 | **已关闭** | 提交 `e4d66db02a0b8f1b867a0e81b4a73de84588426b`；20/50/100/200 各 5 seed，20/20 formal 且 `repository_dirty=false`；每例 136 帧、重排 12、拒绝/过旧/溢出 0、峰值/结束缓冲 3/0、在线 truth 0 | 保持 schema/hash/truth-isolation 回归；AirSim 和完整融合另行验收 |
| 观测治理内存边界 | 正式快速治理证据已获得 | 200 规模 `estimated_peak_memory_bytes.mean=40,914,828.4 B`，约 40.91 MB；最大 40,926,870 B | 完整融合、长历史和进程常驻集内存仍需单独记录；tracemalloc 值不是生产预算 |
| 逐小扫描全后验吞吐 | **D1-owned 冻结输入热点已关闭；系统 P1 仍开放** | profiler 定位 `_state_at`/历史 replay 和重复 health snapshot；增量后验检查点与公共审计快照使 filter update `93,234 -> 1,797`、health snapshot `16,653 -> 86`；clean 三 seed 全栈已完成 | 冻结硬件、发布频率与周期预算并扩展更长时；另验长历史内存和端到端实时倍率 |
| 扫描关联重复模型构造 | **D1-owned 与 clean 三 seed 复跑已关闭** | seed 42000 冻结对照中 model build `16,457 -> 82`、墙钟 `10.792 -> 8.635 s`；clean `8f86192` 三 seed 全栈安全与语义回归通过 | 不得用模块单 seed 1.25 倍或全栈 D1 分项 10.0% 替代系统 P95、AirSim 或实时验收 |
| 雷达候选精确创新求解成本 | **D1-owned 严格等价优化已关闭；系统实时 P1 仍开放** | 仅对有限、严格对称、Gershgorin 严格正定且高于 `pinv` cutoff 的矩阵预门控；非正定交叉协方差和近奇异截断负例均回退旧精确求解。冻结纯融合墙钟均值 `91.313 -> 88.619 s`；最终 integrated 三 seed D1 fusion 均值 `92.991088 -> 88.330438 s`、scan input `16.902643 -> 17.524242 s`，精确求解合计 `7,130,228 -> 1,578,677`，业务语义审计 3/3 通过 | 记录真实异常 covariance 的认证/回退比例，扩展未见 seed、时长和固定硬件周期统计；scan input 与长时超线性仍开放，不得放宽 gate、cutoff 或 `pinv` 语义 |
| 正式 200v200 算法效果 | 未验收 | clean 三 seed 全栈已运行，但正式 RMSE/NEES/NIS sidecar 和 D2 canonical mapping 指标仍 unavailable | 更多未见 seed、正确 D2 canonical mapping、RMSE/NEES/NIS/coverage 与置信区间 |
| AirSim 状态 | 无变化 | 两批均为合成治理或三维质点制品，未启动 Blocks/CV/SimpleFlight | 按独立 AirSim 计划采集和验收，不得把本批改写为 AirSim 证据 |

最新一轮进一步关闭 claim 内同一量测、协方差、元数据和谱系的重复 JSON 安全转换。摘要算法、
键排序、`allow_nan=False`、内容排除字段、claim registry 和拒绝策略保持不变。冻结全流水
acceptance 全部通过；函数级 P50 约 1.899x。该结果不关闭 scan-input 整体或 fusion 尾延时
GAP。当前冻结复放 fusion 累计为 `43.148 s`，主要热点仍是 GlobalTrack 物化、非雷达扫描关联
和 replay。证据文件为
`research_modules/d1_sensor_fusion/reports/d1_tail_latency_performance_20260723.json`。

前一轮关闭 organizer 对已验证完整帧的重复深快照热点。旧/新完整复放的 14 项 acceptance
均通过；当次本机未剖析 fusion P50/P95/max `34.108/178.420/354.413 ms` 仅用于同轮归因，
不能与对应 clean episode `33.252/224.764/592.957 ms` 作正式前后比较。

新增的 clean seed 1000 校准只增加描述性全栈证据，不关闭既有系统性能 GAP。核心 wall 与外部
总进程 elapsed 已按来源分列；由于核心 RTF 仅 0.1176437、fusion P95/max 仍为
224.76351/592.95713 ms，且 scan input 同比增加 1.9952%，融合尾延时和 scan-input 均继续保持
P1。20-seed 正式矩阵、AirSim 和正式 RMSE/NEES/NIS 状态不变。

本轮没有新增 D1 P0 blocker。长时冻结输入优化新增固定大小的
`FusionPerformanceDiagnostics`，可由 profiler 读取累计 filter update/checkpoint reuse 等计数，
无需在 episode summary 内保存逐扫描历史。D1 已提供同一 fusion timestamp 的
state-only/末尾快照接口和
publication audit v2；main 已在 clean `8f86192` 三种子质点全栈接线，接线项关闭，不回退 D1
已完成的长时语义等价优化。clean/formal 治理复跑缺口已
关闭，输入 SHA-256 及 60 个引用制品
均通过复核。释放后的重复后验计算已在 D1 冻结输入上完成治理；未缓存参考与优化路径保持每扫描
一对一关联、双时间戳、covariance、OOSM、observer-scan conflict、consistency evidence 和
完整 `GlobalTrack` 输出。clean 三 seed 已补充全栈接线证据，但仍不能替代实时预算、AirSim 和
融合精度验收。

最终跨提交复核进一步确认：相对 `8f86192`，`f80b5bd` 的 D1 fusion 三 seed 均值下降约 5.01%，
但 scan input 增加约 3.68%。精确创新求解下降约 77.86%，该字段只作性能诊断。三个 seed 的
D1 fused-track 规范哈希和全部在线业务语义审计通过，终态 D1 航迹数均保持 `202/207/203`。
该证据不改变系统实时与长时归一化超线性 P1 的开放状态。

后续 D1-owned 剖析进一步把合法缓存证据刷新定位为剩余重放热点。受限复制仅更新两个非负 replay
计数，不绕过新证据或变化证据的完整校验。clean `f80b5bd` 三 seed 冻结 A/B 的参考/候选均值
为 `64.844/52.657 s`，全部严格语义与操作数检查通过。代表 seed 中
`_replay_record` 累计 `35.348 -> 9.410 s`。本项可以从 P1 实现缺口移为持续回归项；整体实时、
长于 10 s 的归一化增长、非雷达候选成本、航迹物化、scan input 与正式精度继续保持 P1。

第二阶段继续治理第一阶段默认路径中的扫描关联成本。严格几何键只允许在实际量测函数参数一致时
复用非雷达预测量测和数值雅可比；每个候选对仍独立求创新协方差并参加 Hungarian 分配。冻结
输入 SHA-256 为 `bc539686b130d96c63b76b9161fadbae2dba59de44cb61ac80d92f2ea1018406`。
86 个逐扫描语义摘要、最终 201 条航迹和 consistency evidence 完全一致，在线 truth 使用为 0。
专项 `10 passed in 10.33s`，D1 全量 `161 passed in 38.02s`。当前无新增 D1 P0 blocker；
clean 三 seed 全栈复跑已完成，更多长时 seed、实时预算和正式效果指标仍为 P1。

第三阶段雷达预门控不再使用未认证的 trace 比值。当前实现以严格对称、Gershgorin 正定下界和
`pinv` cutoff 上界共同认证适用性；任何认证失败都保留全部候选并执行旧精确伪逆。两类反例
明确覆盖旧路径会保留、朴素下界可能误拒绝的情况，扫描级参考/候选语义一致。三 seed 冻结基准
和 D1 全量 `175 passed` 后，本 D1-owned 数学边界缺口关闭；系统实时、正式精度和真实异常矩阵
分布仍按 P1 保持开放。

## 0.1 历史 D1-owned GAP 增量（2026-07-16）

| GAP/合同 | 当前状态 | 2026-07-16 证据 | 剩余关闭条件 |
| --- | --- | --- | --- |
| `LocalImageTrackObservation` 到 D1 EO 合同 | D1-owned 已关闭 | `measured -> eo/pixel`，`lost -> None`；双时间戳、2×2 covariance、confidence、quality flags 和 spectral band 保真 | main/runtime producer 接线和真实 episode 消费验证 |
| 非法视觉 covariance | P0 边界持续通过 | 缺失、non-finite、non-symmetric、wrong-shape、non-PSD 均在适配边界拒绝 | 保持上游直接提供有来源的 pixel covariance，不增加在线默认回填 |
| 本地视觉来源与全局身份隔离 | D1-owned 已关闭 | global/truth identity（含嵌套键）拒绝；`source_track_key` 只累积为 `source_track_ids`，不重绑定 global ID | main/D2/D5 继续保持本地来源键与 canonical/global ID 分离 |
| 重复来源 lineage | D1-owned 已关闭 | sensor/stream/epoch/local ID/measurement time 形成确定性 ID 和显式 lineage；重复样本 key 相同 | 真实 runtime 重投递计数仍由 main 验证 |
| 2026-07-16 验收 | 通过 | 无随机 seed；专项 `13 passed`，D1 全量 `111 passed` | 本轮无 AirSim、RMSE/NIS/NEES 或时延预算新证据 |

因此本轮关闭的是此前缺失的模块中立本地图像航迹适配层及其 D1 元数据传播，不关闭真实
AirSim producer wiring、相机标定、像素 covariance 标定或 100 ms 运行预算 P1。默认 AirSim
检测源、launch/reset/episode 顺序和图片保存策略均未改变。

## 0.2 历史系统 GAP 增量（2026-07-15）

本节覆盖后文按日期保留的历史状态，不删除既有实现与验证记录。

| GAP/合同 | 当前状态 | 2026-07-15 证据 | 剩余关闭条件 |
| --- | --- | --- | --- |
| 在线 identity/state truth 隔离 | P0 持续回归通过 | M5N2 baseline/candidate 各 10 case，共 20 case；两项在线使用计数均为 0 | 保持所有 runtime 入口 fail-closed，不把 offline sidecar 回灌在线链 |
| 双时间戳、covariance、NED | P0 合同保持 | 本轮未修改合同；D1 仍以正式观测合同进入 main bus | 后续性能优化不得丢观测、改时间或人为收紧 covariance |
| 真实运行时 100 ms 预算 | P1 开放，历史 AirSim 系统证据 | 3,805 tick；D1 fusion mean/P95/max=`320.00/451.46/1234.88 ms`，为 main-bus 内层主导阶段；后续 D1-only 冻结输入热点已优化 | main 用当前实现复跑真实多 seed；P95 达到预注册系统预算且数值/审计不退化 |
| 真实传感器精度与 consistency | P1 开放 | 本批 NIS/NEES/RMSE 均不可用 | 独立 sensor-specific 多 seed case，带 truth sidecar、正确身份映射和 availability |
| M5N2 停止边界 | 已冻结 | M5N2 20/20；额外 1 个 `png_ttc_2v2_seed001` 排除；dropout=0 | 缺失 case 保持 unavailable，不补零、不混入本批统计 |

因此当前没有新增 D1 P0 blocker。此前 D1-owned `process_batch()`、fixed-lag 重放最小化和
covariance 合同实现保持有效，但真实 M5N2 证明“接口存在”不等于“运行时预算闭合”。下一步
P1 应优先治理 D1 fusion 内层耗时，并另行补 NIS/NEES/RMSE；两类验收不得互相替代。

## 1. 总体结论

D1 当前已经实现了可运行的轻量主线：`SensorObservation -> NumPy EKF/FusionAdapter -> GlobalTrack`，支持雷达、声学、EO、可选合成 LiDAR，具备测量时刻/到达时刻分离、fixed-lag replay 延迟补偿、可参数化距离/置信度相关协方差、AirSim dry-run fake fixture 与 schema 检查、跨节点通信元数据、source lineage 去重基线、`TrackUncertaintySummary` 导出、replay schema v1/legacy JSONL 兼容、最小 CSV reader/replay、真实 Blocks/CV 字段保真、raw replay latency/OOSM audit helper、`LatencyAuditSummary`、`SensorHealthSummary`、协方差 floor/ceiling reason、covariance scale reason passthrough、timestamp uncertainty、轻量 `FusionQualityRegionSummary`、`FusionQualityRegionWindowSummary` 和 `ReconCueSummary` 粗指向摘要。D1 接收 main 提供的 N 个 target truth/观测源，并按输入数组长度处理 `SensorObservation[]` 与 `GlobalTrack[]`；真实 AirSim runtime bridge 仍由 shared/main 层负责，D1 不直连 AirSim。

尚未实现的主要是外部成熟框架集成：Stone Soup、FilterPy、ROS 2 `tf2`、`message_filters`、UKF、IMM、D1 包内真实 AirSim ComputerVision/Blocks 运行时适配。这些目前有文档计划或占位类，但未作为 D1 运行依赖接入。原因主要是当前阶段强调依赖轻、可复现、离线测试稳定，且缺少 ROS 2 runtime、稳定真实 AirSim detection schema/外参标定链路、长期真实样本回归和多模型评估基准。

优先级建议已同步 `EVAL/FRAMEWORK_EVAL_P0_P1_P2_GAP_CONFIRMATION.md` 中的 D1 P0/P1 口径：

- **P0**: 无运行级 P0 blocker；当前 NumPy EKF、传感器观测模型、延迟补偿、AirSim dry-run、`measurement_timestamp`/`arrival_timestamp`、协方差和 NED `GlobalTrack` 合同均作为持续回归基线维护。EVAL 确认的 D1 工程化 P0-A 已实现：FDIR-light、协方差上下界限制和时间戳不确定性建模已进入代码与接口回归；后续若真实多 seed/闭环样本发现未覆盖验收场景，按第 1.2 节的最小验收口径进入 P0 backlog。
- **P1**: `TrackUncertaintySummary`、replay/schema/governance、source de-dup、区域/窗口质量、`ReconCueSummary` 和真实 CV 字段保真均已完成。2026-07-11 又完成中心化协同定位数值基础：typed cooperative DTO/summary、2..N bearing-ray WLS、几何/时间/covariance 门控、共同估计时刻传播及最小 CI。剩余 D1 P1 是 IMM/CV-CA-CT、场景自适应协方差、D1/D2 association-to-fusion 接线、真实 AirSim multi-seed 协同 replay、D6 长期 schema/阈值和分布式全链路；Stone Soup、FilterPy、MATLAB 仍只作对照。
- **P2**: 接入 Stone Soup/FilterPy/OpenCV/UKF/IMM 作为离线对照，不替换 NumPy fallback；ROS 2 `tf2/message_filters` 和真实 AirSim bus 直连只有在运行环境、topic schema 和 main/shared runtime 合同稳定后再评估。

2026-07-08 补充复核：main runtime 已新增 P1 D4/D5 calibration sweep，并在 sweep 结束后自动生成 D6 标准报告 bundle。该能力属于 main/D6 集成层，不改变 D1 职责边界。D1 当前 P1 重点是保持 replay schema、measurement/arrival timestamp、covariance、latency/OOSM audit、区域质量/窗口摘要和二级侦察 cue 字段稳定，并继续补真实 AirSim multi-seed fixture 与阈值校准样本。

2026-07-09 补充复核：D1 已补齐 main P1 缺口方案中的轻量输入支撑项，包括 dry-run fixture schema version 检查、raw replay observation latency/OOSM audit helper、unsupported JSONL schema 回归、`covariance_scale_reason` passthrough 以及 secondary/mobile recon cue metadata 在 JSONL/CSV reader 和 `GlobalTrack.metadata` 中的保真回归。`SensorHealthSummary`、协方差上下界 reason 和 `timestamp_uncertainty_s` 继续作为已实现 P0-A 质量证据提供给 main/D6；P1 calibration sweep/D6 bundle 对 D1 的消费口径是汇总 observation latency、OOSM、区域质量、窗口趋势、sensor health、covariance reason 和 timing uncertainty，不由 D1 触发主动降级。剩余 P1 不再是这些轻量字段本身，而是更多 main/shared 真实 multi-seed Blocks/CV 样本、D6 长期批量 schema、持续阈值和算法增强项。

2026-07-10 真实 2v2 smoke 复核：六个 episode 共 1,528 条观测全部保留双时间戳和
covariance，未发现时间倒置、非有限 covariance、非对称 covariance 或负特征值；
full-flow main bus 的 36 个 tick 也持续保留观测双时间戳、covariance trace 和
`TrackUncertaintySummary` timing/covariance 字段，未发现 D1 合同回归。实际产物也暴露了
三个仍需明确保留的 P1：main writer 未写 `schema_version`，所以新日志仍走 legacy
兼容路径；观测缺 `coverage_cell` 且 main tick 未发布区域/窗口、latency/sensor-health
摘要，真实区域质量闭环尚未验收；固定 0.2 s 延迟产生的大量合法 OOSM 会使当前 advisory
sensor-health 阈值误报 `isolated`，必须先做 expected-latency/OOSM 基线标定，不能直接
作为 D4 降级证据；main bus 依赖 simulation-only truth hint 保持 2 条航迹，而默认
truth-free replay 会对 TGT-002 产生重复初始化并输出 3 条航迹，说明 replay 配置 provenance
和无真值关联一致性尚未闭合。本轮不修改 main/runtime，也不把上述集成/标定项误写成
D1 已闭合，更不把 truth metadata 当作真实在线身份依据。

2026-07-10 十 seed/身份隔离证据同步：main 已完成 2v2 十 seed 系统运行，说明 D1 DTO 在
reset-separated episode 中可重复被消费；另一个 5v5 truth-isolation smoke 已确认 D5 在线
local detection/MOT ID 不再依赖 actor/object 名称。这两项不新增 D1 P0，也不关闭 D1 的
truth-free replay P1：D1 合成观测中的 `truth_id` 仍只能作离线评分标签，main 的
simulation-only truth-hint 配置仍需写入 provenance 并通过无 truth-hint 多 seed replay
对照。1,528 条观测仍是本轮已逐条验证双时间戳和 covariance 的直接 D1 证据；十 seed
产物尚需固化为带显式 schema、coverage cell、CV bbox covariance 和二级侦察 metadata 的
长期 fixture。

## 1.1 2026-07-07 P1 复核结论

本次复核背景是 main runtime bus 已将真实 AirSim D7 执行结果回灌到正式 episode metrics，D3 补充了中心重规划后的新 `AssignmentPlan` owner/version 元数据，D4 将主动降级硬风险与软质量风险拆分，D5 修正了终端一致性窗口的 key。D1 侧结论如下：

- **2026-07-08 状态确认**: 无 P0 blocker。`ReconCueSummary` 与 `summarize_recon_cue_from_tracks()` 已进入已实现基线，可从 `GlobalTrack[]` 或 track-like dict 输出移动高空侦察节点的 radar/global-track cue，并保留 measurement/arrival timestamp、协方差和 NED 合同。
- **无新增运行级 P0**: D1 的 `SensorObservation -> FusionAdapter -> GlobalTrack -> TrackUncertaintySummary` 合同仍满足下游输入要求，测试仍应作为 P0 回归；EVAL 工程化 P0-A 硬化项已按 1.2 和第 7 节闭合。
- **D4 接口语义收紧**: D1 的协方差、freshness、latency、source support 和 handover readiness 只能作为态势质量证据。单帧 `coarse/stable` 波动、短时 latency 或低 handover readiness 不应被 D4 直接解释为中心节点失效或立即主动降级；D4 需要结合 D3 plan freshness、D5 terminal evidence、C2 health 和持续窗口仲裁。
- **D3/D7 使用边界不变**: D3 可把 D1 质量摘要纳入分配代价和 replan 依据，D7 可按 `stable/handover`、协方差和 freshness 做导引门控；D1 不生成 plan version，也不修改 D7 PN/PNG 控制律。
- **D5 使用边界不变**: D1 继续提供可投影的 NED state、6x6 covariance、EO bbox/camera metadata lineage 和时间戳。D5 的跨视角/终端一致性结果只能作为反馈证据，不能反向改写 D1 的 `global_track_id`。
- **严格 subagent 流程**: D1 owned 代码、README、PLAN、GAP 和 review 的能力状态由 D1 子智能体自己检查、修改和测试；main 只汇总与集成验证。若 main 临时代改 D1 文件，后续必须由 D1 复核并同步文档状态。


## 1.2 EVAL P0/P1 同步口径

本节只同步 EVAL 确认的 D1 P0/P1，不新增、移动或改写下方既有 P2/P3 项。P0 口径为工程化硬化项，不是当前仓库测试运行级 blocker；P1 口径为三个月内能力增强和多 seed 标定项。Stone Soup、FilterPy、MATLAB 等外部工具仅作为对照或工程参考，不是当前 P0 依赖。所有后续实现必须继续保持 D1 合同：`SensorObservation[]` 和 `GlobalTrack[]` 按输入数组长度处理，2v2/5v5 只作为 baseline 名称；观测和航迹保留 `measurement_timestamp`、`arrival_timestamp`、covariance，并以 NED 为融合工作坐标系。

| EVAL 优先级 | D1 条目 | 当前 D1 状态 | GAP 同步结论 | 最小验收口径 |
|---|---|---|---|---|
| P0-A | FDIR-light | 已实现传感器级 `SensorHealthSummary`，从延迟/OOSM、stale、低质量/遮挡、异常协方差和重复观测派生 health/status、fault reason、reject count、isolation hint 和 recovery state | 已实现，保持现有门控和摘要基线回归；若故障恢复/隔离建议在真实样本中缺字段，则作为 P0 backlog 补齐 | 故障注入下输出 sensor health、fault reason、reject count、isolation hint 和 recovery state |
| P0-A | 协方差上下界限制 | 已实现观测 covariance floor/ceiling、低质量/遮挡协方差放大、track 6x6 covariance floor/ceiling 和 reason metadata | 已实现，保持 covariance 输出、floor/ceiling reason 和质量分级回归；若低质量/遮挡/外推场景缺 reason，则作为 P0 backlog 补齐 | 协方差不发散、不虚假收敛；D6/报告能解释 floor/ceiling reason |
| P0-A | 时间戳不确定性建模 | 已实现 `SensorObservation.timestamp_uncertainty_s` 标准化，并在观测 metadata、`GlobalTrack.metadata`、`TrackUncertaintySummary` 和 `SensorHealthSummary` 中导出 timing uncertainty | 已实现，保持双时间戳合同和 timing uncertainty 回归；若 D6 延迟报告无法消费，则作为 P0 backlog 补齐 | 注入 10-50 ms 时钟漂移时输出 timing uncertainty，并能关联误差变化曲线 |
| P1 | IMM/CV-CA-CT 多模型滤波 | 当前 CV/EKF 主线可用；CV/CA/CT 模型集、IMM 权重、UKF/Stone Soup/FilterPy 后端仍未接入 | 作为 D1 P1 能力增强 backlog，先做 CV/CA/CT 或等价模型对照，不替换 NumPy fallback；Stone Soup/FilterPy/MATLAB 只作参考或 benchmark | 机动目标 replay/AirSim 样本中输出模型对照，机动 RMSE 或 NIS/连续性指标优于 CV-only 基线 |
| P1 | 场景自适应协方差 | 已有距离/质量相关协方差、bbox confidence/occlusion 输入、低质量/遮挡 scale reason、replay passthrough 和雷达参数化；尚缺杂波、SNR、来源差异和延迟的完整动态 covariance scale rule | 作为 D1 P1 标定 backlog，保留现有 covariance-required replay/schema 已完成状态；MATLAB fusion 调参逻辑只作工程参考 | AirSim/replay 中稳定输出 covariance scale reason，并用多 seed 标定阈值 |
| P1 | Track-to-Track 融合原型 | NumPy CI helper 已实现同 canonical ID、1..N 状态、共同时间传播、message UUID/完整 lineage 去重和保守 covariance；未接 D2/runtime 多节点输入 | D1-owned 最小数值原型已关闭；保留 D1/D2 双阶段合同、真实 replay、部分共享 lineage 和分布式共识为 P1 | 构造测试已满足不重复计数和 CI 不比错误独立融合更自信；真实多节点日志仍需验收 |

## 2. 按实现状态归类

### 2.1 已实现

- `SensorObservation` 统一合同已落地，支持 `radar/acoustic/eo/lidar`，强制保留 `measurement_timestamp`、`arrival_timestamp`、`frame_id`、`measurement`、`covariance`、置信度、质量标记、通信元数据和 `timestamp_uncertainty_s`。
- `FusionAdapter` 已实现 NumPy EKF 融合主线，输出六维 NED `GlobalTrack`、6x6 协方差、`source_support`、质量等级、`valid_at/published_at`、最近量测时间、最近到达时间、timestamp uncertainty、covariance limit reason 和 sensor health snapshot。
- fixed-lag/OOSM 延迟补偿已实现，观测按 `measurement_timestamp` 插入历史并重放到当前 `arrival_timestamp`；消融测试要求补偿 RMSE 明显优于未补偿基线。
- 雷达距离相关协方差已通过 `RadarCovarianceConfig` 参数化；声学为弱方位约束；EO 为 pinhole 像素投影约束；合成 LiDAR 作为 dry-run NED 三维位置量测。
- AirSim dry-run fixture 已实现，不导入 AirSim，可生成 radar/acoustic/eo/lidar `SensorObservation[]` 并喂给 `FusionAdapter`。
- Blocks JSONL replay reader 已实现并升级为 replay schema v1/legacy 兼容，D1 可读取 `blocks_sensor_observations.jsonl` 与未来 `sensor_observations.jsonl` 并回放融合；N actor 合同测试覆盖按输入数组长度输出 `GlobalTrack[]`。
- 最小 CSV reader/replay 已实现，支持以 JSON array/object 单元格表达 measurement、covariance、metadata、communication 和 source support，便于 D6/人工审计复用观测记录。
- `TrackUncertaintySummary` 已实现数据类与导出方法，包含协方差迹、`a95`、等级、measurement age、source support、coverage cell、measurement/arrival timestamp 和 handover readiness。
- `LatencyAuditSummary` 已实现，导出 max/mean delay、replay count、OOSM/stale count、重复观测数和最大 replay 历史长度。
- `SensorHealthSummary` 已实现，导出 per-sensor `status`、`fault_reason`、`reject_count`、`isolation_hint`、`recovery_state`，并保留 duplicate、OOSM/stale、低质量/遮挡、异常协方差和 timestamp uncertainty 计数。
- 协方差上下界限制已实现，观测协方差进入 EKF 前会 floor/ceiling，低质量或遮挡观测会保守放大，track 6x6 covariance 在预测/replay/update 后会 floor/ceiling，并在 metadata/summary 中记录 reason。
- `FusionQualityRegionSummary` 已实现轻量区域聚合，按 `coverage_cell` 汇总 track 数、a95、measurement age、handover readiness、source support、source gap、stale track 数和可选协方差增长率。
- `FusionQualityRegionWindowSummary`、`annotate_covariance_growth_rates()` 和 `summarize_region_quality_windows()` 已实现轻量窗口趋势，区分区域协方差增长、freshness 下降、source gap 与 latency/OOSM。
- `ReconCueSummary` 已实现轻量侦察相机粗指向摘要，按全部 tracks 或指定 `coverage_cell` 子群输出协方差加权 `cue_position_ned`、`cue_covariance`、`active_target_ids`、measurement/arrival timestamp、可选二级/移动侦察 metadata 和基础诊断。
- source lineage 去重基线已实现，可抑制同一 source/sequence/payload 经 relay 重复投递导致的重复更新。
- 中心化协同定位 typed DTO、2..N bearing-ray WLS、几何质量摘要、共同时间传播和 NumPy CI 已作为独立 helper 实现；不改变 `FusionAdapter` 默认路径，也不执行 D2 关联。
- `generate_truth(target_count=N)` 和 CLI `--drone-count N` 已按输入 N 运行，不把算法限制为 2v2 或 5v5；历史 2v2/5v5/3-target 仅作为 baseline 名称或样例。

### 2.2 部分实现

- Stone Soup 和 FilterPy 仅有 placeholder/可用性探测与转换边界，未接入真实 tracker、updater、UKF、IMM、JPDA/MHT 或 OOSM 后端。
- AirSim/Blocks 集成在 D1 侧完成 fake fixture 和 JSONL replay；真实 AirSim 连接、`simGetDetections` 调用、frame capture 和 JSONL 写出属于 main/shared runtime，不在 D1 包内直连。
- EO 无截图合同已实现，D1 只消费 bbox、相机元数据、时间戳和协方差；但未实现 OpenCV calibration、畸变模型、`solvePnP` 或 `projectPoints` 对照。
- 合成 LiDAR 仅是 dry-run/replay 观测模型，不是 AirSim LiDAR plugin 或真实硬件桥。
- `TrackUncertaintySummary` 是单航迹摘要；轻量 `FusionQualityRegionSummary`、`FusionQualityRegionWindowSummary` 和 `ReconCueSummary` 已按当前 track summary/track input 聚合。D6 批量日志 schema、真实多 seed 样本阈值、真实样本回归和更细 NIS 统计仍需后续补齐。
- source lineage 去重覆盖观测主线；独立 CI helper 已覆盖 message UUID/完整 lineage 重复和未知交叉相关保守融合。部分共享 lineage 建模、D2/runtime 接线和分布式共识仍未实现。
- JSONL replay schema v1/legacy 兼容、真实 CV 字段保真和最小 CSV reader 已完成；更多 main/shared 真实 Blocks/CV multi-seed fixture 回归仍未完成。
- 2026-07-08 已补强 CSV 缺省 schema 行的 v1/covariance 验证、嵌套 EO camera metadata 解析、真实 CV bbox/camera/detection metadata 字段保真、区域窗口/协方差增长 helper 和 Blocks calibration CSV 回归；更多 main/shared 真实 Blocks/CV multi-seed fixture 回归仍未完成。

### 2.3 未实现

- UKF 与 IMM-EKF/IMM-UKF 未实现。
- 真实 Stone Soup 后端和真实 FilterPy 后端未实现。
- ROS 2 `tf2` 坐标树和 `message_filters` 时间同步未实现。
- D1 包内真实 AirSim ComputerVision/Blocks runtime 直连、`simGetDetections` 直接 adapter 未实现；这属于 P2 后置直连能力，当前 P1 只跟踪 D1 可消费的 Blocks/CV fixture 回归和字段合同。
- OpenCV calibration、畸变校正、`solvePnP`、`projectPoints` 对照未实现。
- 声学 TDOA/阵列主定位未实现，当前按计划只作为粗方位和类别辅助。
- 多节点 D1/D2/runtime Track-to-Track 全链路和 Stone Soup Track Fusion 对照未实现；NumPy CI 数值基础已实现。

## 3. 逐项差距表

| 预期项 | 当前状态 | 证据文件 | 未实现原因 | 缺失条件 | 建议优先级 |
|---|---|---|---|---|---|
| 统一 `SensorObservation` 数据合同 | 已实现。支持 `radar/acoustic/eo/lidar`、`measurement_timestamp`、`arrival_timestamp`、`frame_id`、`covariance`、质量字段、通信元数据、真实 CV bbox/camera/detection metadata 和 secondary/mobile recon cue metadata；replay schema v1、legacy JSONL 和最小 CSV replay 已落地 | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/types.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/replay.py`; `research_modules/d1_sensor_fusion/tests/test_interfaces.py`; `research_modules/d1_sensor_fusion/tests/test_airsim_dry_run.py` | 不适用 | 仍需更多 main/shared 真实 Blocks/CV multi-seed fixture、真实样本回归和 D6 长期批量 schema 对齐 | P0/P1 |
| `GlobalTrack` 六维航迹输出 | 已实现。输出 `[px, py, pz, vx, vy, vz]`、6x6 协方差、`track_level`、`source_support`、`metadata.frame_id/valid_at/published_at/a95_m/latest_measurement_timestamp/latest_arrival_timestamp` | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/types.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/fusion.py` | 不适用 | 需要继续补充 track/schema version 与下游日志命名标准化 | P0/P1 |
| 跨节点通信元数据 | 已实现最小支持。字段包括 `source_node_id`、`target_node_id`、`relay_node_id`、`link_type`、`sent_timestamp`、`received_timestamp`、`payload_kind`、`stale_after_s`、`source_support` | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/types.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/fusion.py`; `research_modules/d1_sensor_fusion/tests/test_interfaces.py` | 不适用 | 需要 main 确定节点 ID、链路类型和 stale 策略的枚举 | P0 |
| EKF 主滤波器 | 已实现。自研 NumPy EKF、数值雅可比、Joseph 形式协方差更新、NIS 输出 | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/ekf.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/fusion.py` | 不适用 | 后续需增加与 FilterPy/Stone Soup 的数值对照 | P0 |
| 常速度 CV 运动模型 | 已实现。六维 CV 预测和白加速度谱密度过程噪声 | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/motion.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/ekf.py` | 不适用 | 对高机动目标需更多模型 | P0 |
| UKF | 未实现。文档中列为强非线性场景升级项 | `research_modules/d1_sensor_fusion/docs/ALGORITHM_AND_IMPLEMENTATION.md`; `subagent_reviews/D1_SENSOR_FUSION_REVIEW_AND_PLAN.md` | 当前 EKF 足够覆盖离线主线；未引入 FilterPy/Stone Soup 依赖 | 需要 UKF 后端接口、sigma-point 参数、对照场景和误差指标 | P2 |
| IMM-EKF/IMM-UKF | 未实现。文档中列为机动目标升级项 | `C_UAS_MAINSTREAM_SOLUTIONS_AND_DIFFICULTIES.md`; `research_modules/d1_sensor_fusion/docs/ALGORITHM_AND_IMPLEMENTATION.md` | 当前状态维度和场景仍以 CV/EKF 为主；D2 关联先用基础航迹 | 需要 CV/CA/CT 模型集合、模型转移概率、机动场景和 D2 接口约定 | P2 |
| Stone Soup 集成 | 占位实现。只提供不导入 Stone Soup 的 placeholder 和 detection dict 转换；未接入真实 Stone Soup tracker/fuser/OOSM | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/compat.py`; `research_modules/d1_sensor_fusion/tests/test_interfaces.py` | 保持当前测试不依赖外部包；Stone Soup 适合作为离线对照而非主运行依赖 | 需要安装依赖、设计 D1 observation/track 转换、选择 Stone Soup updater/initiator/fuser、定义对照实验 | P2 |
| FilterPy 集成 | 占位实现。只检测可用性并说明 fallback 状态；未调用 FilterPy EKF/UKF/IMM | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/compat.py`; `research_modules/d1_sensor_fusion/tests/test_interfaces.py` | 当前已有自研 EKF，避免新增依赖和版本差异 | 需要明确 FilterPy 后端接口、测试容差、UKF/IMM 目标 | P2 |
| ROS 2 `tf2` | 未实现，仅文档计划。当前只用 `metadata` 中的 NED 位置和相机外参 | `research_modules/d1_sensor_fusion/docs/AIRSIM_INTEGRATION_PLAN.md`; `research_modules/d1_sensor_fusion/docs/ALGORITHM_AND_IMPLEMENTATION.md` | 当前仓库没有 ROS 2 runtime 和 tf tree；AirSim dry-run 不需要 ROS | 需要 ROS 2 环境、frame 命名规范、外参版本、tf buffer 与时间戳策略 | P2 后置 |
| ROS 2 `message_filters` | 未实现，仅文档计划。当前依赖 `arrival_timestamp` 排序和 fixed-lag replay | `research_modules/d1_sensor_fusion/docs/AIRSIM_INTEGRATION_PLAN.md`; `subagent_reviews/D1_SENSOR_FUSION_REVIEW_AND_PLAN.md` | 离线 replay 不需要 ROS message filters；OOSM 补偿已经在 D1 内实现 | 需要 ROS topic schema、同步策略、允许延迟窗口和 bag/replay 工具 | P2 后置 |
| 雷达观测模型 | 已实现。`[range, azimuth, elevation, radial_velocity]`，支持传感器位置和角度 wrap | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/observations.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/simulation.py` | 不适用 | 需要真实/仿真雷达配置时再参数化噪声模型 | P0 |
| 雷达距离相关协方差 | 已实现并可参数化。`RadarCovarianceConfig` 保持默认行为兼容，也可按距离系数覆盖 | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/observations.py`; `research_modules/d1_sensor_fusion/tests/test_interfaces.py` | 不适用 | 后续可按真实雷达型号、SNR、杂波、遮挡策略扩展配置来源 | P1 已完成基线 |
| 雷达初始化新航迹 | 已实现。`_create_track()` 只允许雷达初始化，避免声学/EO 单独造三维真值 | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/fusion.py` | 不适用 | 如果要 EO/depth 初始化，需要额外深度/多视角约束 | P0 |
| 声学观测模型 | 已实现弱约束。仅方位角 + confidence 相关角度协方差 + `classification_hint` | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/observations.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/simulation.py` | 不适用 | 未实现 TDOA/声阵列硬件模型；缺少阵列几何和声学仿真参数 | P0 |
| 声学主定位/TDOA | 未实现，且不建议作为主线。文档明确声学只作粗方位和类别辅助 | `C_UAS_MAINSTREAM_SOLUTIONS_AND_DIFFICULTIES.md`; `subagent_reviews/D1_SENSOR_FUSION_REVIEW_AND_PLAN.md` | 主流共识认为声学主定位场景受限，且硬件相关性强 | 需要阵列几何、采样率、TDOA 估计、风噪/混响模型 | P2 后置 |
| EO 像素观测模型 | 已实现。使用 pinhole 相机模型，像素中心观测，bbox/置信度/遮挡影响协方差 | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/observations.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/simulation.py` | 不适用 | 需要与 D5/主程序统一 camera metadata schema | P0 |
| EO 无截图输入 | 已实现合同层面。D1 只需要 bbox、相机元数据、时间戳和协方差，不要求 PNG | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/observations.py`; `research_modules/d1_sensor_fusion/docs/ALGORITHM_AND_IMPLEMENTATION.md`; `subagent_reviews/D1_SENSOR_FUSION_REVIEW_AND_PLAN.md` | 不适用 | 需要 main 从 AirSim CV 输出稳定 JSONL/CSV detection 记录 | P1 |
| OpenCV calibration / solvePnP / projectPoints | 未实现。当前是自研简单 pinhole 投影，不依赖 OpenCV | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/observations.py`; `C_UAS_MAINSTREAM_SOLUTIONS_AND_DIFFICULTIES.md` | 当前仅需 dry-run 和离线约束；OpenCV 更适合 D5 精细投影/标定 | 需要真实相机内外参、畸变模型、坐标链和 D5 共同接口 | P2 |
| 合成 LiDAR 观测 | 已实现 optional dry-run。作为 NED 三维位置量测，含 3x3 covariance | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/types.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/observations.py`; `research_modules/d1_sensor_fusion/tests/test_airsim_dry_run.py` | 不适用 | 当前为合成 dry-run，不是 AirSim LiDAR plugin 或真实硬件 | P1 |
| fixed-lag / OOSM 延迟补偿 | 已实现。按 `measurement_timestamp` 重排历史观测、回放更新并传播到当前时刻，并导出 max/mean delay、replay count、OOSM/stale count 审计摘要 | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/fusion.py`; `research_modules/d1_sensor_fusion/tests/test_interfaces.py`; `research_modules/d1_sensor_fusion/tests/test_simulation_metrics.py` | 不适用 | 后续可补窗口化成本统计和 D6 长期趋势字段 | P0/P1 |
| 延迟补偿消融实验 | 已实现。测试要求补偿 RMSE 明显优于未补偿 | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/simulation.py`; `research_modules/d1_sensor_fusion/tests/test_simulation_metrics.py`; `research_modules/d1_sensor_fusion/reports/EXPERIMENT_REPORT.md` | 不适用 | 需要扩大到 main `--drone-count N` 集成、跨节点通信、二级节点转发延迟；历史 2v2/5v5 只作为 baseline | P1 |
| 协方差输出与航迹分级 | 已实现。输出 6x6 协方差、`a95_m`、`coarse/stable/handover`、NIS 通过率参与分级，并可导出 `TrackUncertaintySummary` 与轻量 `FusionQualityRegionSummary` | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/fusion.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/metrics.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/types.py` | 不适用 | 后续可继续对齐 D4/D6 长期窗口和批量日志字段 | P1 已完成基线 |
| `TrackUncertaintySummary` / `FusionQualityRegionSummary` / `FusionQualityRegionWindowSummary` | 已实现 D1 单航迹摘要、`FusionAdapter.track_uncertainty_summaries()`、`FusionAdapter.region_quality_summaries()`、`annotate_covariance_growth_rates()` 和 `summarize_region_quality_windows()` 导出。字段包含 track IDs、协方差迹/a95、协方差增长率、等级、measurement age、source support、coverage cell、时间戳、source gap、stale track 数、窗口趋势和 latency/OOSM flags | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/types.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/fusion.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/quality.py`; `research_modules/d1_sensor_fusion/tests/test_interfaces.py` | 不适用 | 后续可继续对齐 D6 批量日志 schema、真实多 seed 阈值和更细 NIS 统计 | P1 已完成轻量基线 |
| `ReconCueSummary` 侦察粗指向摘要 | 已实现。`summarize_recon_cue_from_tracks()` 可从 `GlobalTrack[]` 或 track-like dict 生成全部目标或指定 `coverage_cell` 的协方差加权 `cue_position_ned`/centroid、`cue_covariance`、`active_target_ids`、时间戳、可选二级/移动侦察 metadata 和 `track_count/stale_count/default_covariance_count` 诊断 | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/recon_cue.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/types.py`; `research_modules/d1_sensor_fusion/tests/test_recon_cue.py` | 不适用 | main/AirSim runtime 仍负责消费该摘要并控制二级侦察相机指向；D1 不修改 runtime | P1 已完成基线 |
| 多传感器来源去重/相关性降权 | 观测主线 source lineage 去重已实现；CI helper 额外按 message UUID 或完整 source lineage 去重，并用 CI 处理未知交叉相关 | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/types.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/fusion.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/cooperative.py`; `research_modules/d1_sensor_fusion/tests/test_cooperative_localization.py` | 不适用 | 部分 lineage overlap 的相关性建模和真实 relay/runtime 对照待补 | P1 中心化基础已完成 |
| 航迹到航迹融合 / 协方差交叉 | 最小 NumPy CI 已实现 1..N 个 6-state NED estimate、共同时间 CV 传播、process/timing covariance 和 canonical ID 保持 | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/cooperative.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/types.py`; `research_modules/d1_sensor_fusion/tests/test_cooperative_localization.py` | 不适用 | D2 关联确认、runtime TrackSummary adapter、真实多 seed 和分布式共识未接 | P1 数值基础完成，集成待补 |
| AirSim dry-run fake fixture | 已实现。可从 fake fixture 生成 radar/acoustic/eo/lidar `SensorObservation[]`，不连接真实 AirSim；fixture 已带 `d1.airsim_dry_run_fixture.v1` schema version 并拒绝 unsupported fixture schema | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/airsim_dry_run.py`; `research_modules/d1_sensor_fusion/tests/test_airsim_dry_run.py`; `research_modules/d1_sensor_fusion/docs/AIRSIM_INTEGRATION_PLAN.md` | 不适用 | 需要继续与 shared/main 的 Blocks JSONL 输出保持回归一致 | P0 |
| 共享 AirSim dry-run orchestrator 对接 | 已由共享模块复用 D1 dry-run 适配器；D1 侧合同可用 | `research_modules/airsim_dryrun/adapters.py`; `research_modules/airsim_dryrun/tests/test_dryrun_contracts.py` | 不适用 | 该模块不属于 D1；后续由 main 维护统一 runtime | P0 |
| shared/main AirSim Blocks D1 replay 写出 | shared runtime 可从 Blocks frame 生成 `SensorObservation` 并写 `blocks_sensor_observations.jsonl`；D1 包内已能读取该 JSONL 并回放 `FusionAdapter` | `research_modules/airsim_runtime/adapters.py`; `research_modules/airsim_runtime/orchestrator.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/replay.py`; `research_modules/d1_sensor_fusion/tests/test_airsim_dry_run.py` | 不适用 | 后续需继续跟随 schema 演进补更多真实输出回归样本 | P1 已完成基线 |
| 真实 AirSim ComputerVision / Blocks runtime | 未在 D1 包内实现。D1 只提供 fake fixture 和 `SensorObservation` 类型；真实 AirSim 连接、frame capture、`simGetDetections` 和 JSONL 写出在 main/shared 层 | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/airsim_dry_run.py`; `research_modules/d1_sensor_fusion/docs/AIRSIM_INTEGRATION_PLAN.md`; `research_modules/airsim_runtime/real_runtime.py` | 避免 D1 依赖 AirSim Python 包和 runtime；真实 AirSim orchestration 由 main/shared 层负责 | 需要稳定 Blocks JSONL/detection schema、真实相机外参、actor ID 映射、时间戳来源和长期 fixture 回归 | P1 fixture / P2 后置直连 |
| AirSim `simGetDetections` 直接适配 | 未实现 D1 直连。当前要求 main/shared runtime 转成 bbox/camera metadata JSONL/CSV 或 fake fixture，D1 负责离线 reader/replay 和字段回归 | `research_modules/d1_sensor_fusion/docs/AIRSIM_INTEGRATION_PLAN.md`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/airsim_dry_run.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/replay.py` | 避免 D1 依赖 AirSim Python 包和 runtime | P1 需要 main/shared 真实 Blocks/CV multi-seed fixture 覆盖 detection 字段；D1 直连 AirSim API 需等 runtime 合同稳定后再评估 | P1 fixture / P2 后置直连 |
| JSONL/CSV replay 输入合同 | 已实现 replay schema v1、legacy `blocks_sensor_observations.jsonl` 兼容、未来 `sensor_observations.jsonl` reader 和 CSV reader/replay；CSV 缺省 schema 行按 v1 验证并要求 covariance，unsupported JSONL schema 已回归拒绝，Blocks calibration CSV 测试覆盖 timestamps、covariance、source support、NED state、raw/fusion latency/OOSM audit、区域质量摘要、`covariance_scale_reason` 和 secondary/mobile recon cue metadata，真实 CV JSONL 测试覆盖 bbox/camera/detection/secondary/mobile recon metadata 字段保真 | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/replay.py`; `research_modules/d1_sensor_fusion/tests/test_airsim_dry_run.py`; `research_modules/airsim_runtime/orchestrator.py` | 不适用 | 需要更多 main/shared 真实 Blocks/CV multi-seed fixture 和 D6 长期批量 schema 对齐 | P1 已完成轻量基线 |
| N-target D1 独立真值生成 | 已实现。`generate_truth(target_count=N)` 不再把目标数裁剪到 2/5 或 1-3，命令行统一使用 `--drone-count N`，历史 3 目标输出保留为 baseline | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/simulation.py`; `research_modules/d1_sensor_fusion/scripts/run_simulation.py` | 不适用 | 系统级真值仍由 main/integrated 场景提供，D1 只消费其输出 | P1 已完成基线 |
| 单元/接口测试 | 已实现。覆盖时间戳、桶、协方差增长与参数化、延迟观测、通信元数据、dry-run schema、JSONL/CSV replay、unsupported schema、raw/fusion latency audit、source de-dup、TrackUncertaintySummary、LatencyAuditSummary、FusionQualityRegionSummary、FusionQualityRegionWindowSummary、ReconCueSummary、N actor 合同、嵌套 camera metadata replay、真实 CV bbox/camera/detection/covariance scale/recon metadata 字段保真、Blocks calibration CSV 字段保真和仿真指标 | `research_modules/d1_sensor_fusion/tests/test_interfaces.py`; `research_modules/d1_sensor_fusion/tests/test_airsim_dry_run.py`; `research_modules/d1_sensor_fusion/tests/test_recon_cue.py`; `research_modules/d1_sensor_fusion/tests/test_simulation_metrics.py` | 不适用 | 更多真实 AirSim CV multi-seed 场景和 JSONL/CSV 样本仍可后续扩充；2v2/5v5 只作为 baseline 回归命名 | P0/P1 |

## 4. 主要未实现原因归类

1. **依赖与环境未固定**: Stone Soup、FilterPy、ROS 2、tf2、message_filters 和真实 AirSim runtime 都会引入外部环境约束。当前 D1 选择 NumPy fallback，保证仓库在无外部服务时可测试。
2. **消息合同仍需继续演进**: D1 已有 replay schema v1、legacy Blocks JSONL 兼容和最小 CSV reader，但更多真实 detection 字段映射、D6 长期批量字段和长期回归样本仍需补齐。
3. **算法升级需要对照场景**: UKF、IMM、完整 Track-to-Track runtime 和外部 CI 后端仍需要强非线性、高机动、多节点相关观测基准；当前仅关闭依赖轻的中心化 WLS/CI 数值基础。
4. **ROS/真实运行时不是 D1 当前职责边界**: D1 负责 `SensorObservation` 到 `GlobalTrack`，真实 AirSim/ROS topic、bag、tf tree 和 runtime orchestration 应由 main/shared 层提供。
5. **安全边界**: D1 保持为传感器融合与态势估计模块，不输出控制、处置或授权动作，因此未接任何真实飞控/硬件/火控接口。


## 5. 缺少条件汇总

- **真实运行环境条件**: ROS 2 runtime、tf tree、topic schema、bag/replay 工具、AirSim Blocks 稳定启动和长期 fixture 样本。
- **传感器/坐标条件**: 真实或稳定仿真的相机内外参、畸变模型、AirSim detection 字段映射、actor ID 映射、统一时间戳来源和 WGS84/ENU 到 NED 的外部转换合同。
- **数据合同条件**: `sensor_observations.jsonl` schema v1、legacy Blocks JSONL 兼容、最小 CSV reader、真实 CV 字段保真、轻量区域质量摘要、区域窗口摘要和 `ReconCueSummary` 粗指向摘要已落地；仍需 D6 可消费的长期批量摘要字段、真实多 seed 阈值和 coverage cell 规则细化。
- **算法评估条件**: UKF/IMM/Stone Soup/FilterPy 对照场景、强非线性/高机动/多节点相关观测基准、误差门限和与 NumPy EKF fallback 的容差定义。
- **多节点融合条件**: typed state/CI 数值合同已具备；仍需 D2-confirmed 节点级 TrackSummary adapter、融合权威规则、部分共享 lineage 模型、runtime 日志和分布式共识。

## 6. 对后续模块的影响

### 6.1 对 D2 数据关联

- D1 已输出 `GlobalTrack[]`、NED 六维状态、6x6 协方差、`track_level`、`source_support`、`latest_measurement_timestamp`、`latest_arrival_timestamp` 和可选 `truth_id` 元数据。D2 应把这些字段作为中心航迹输入，并继续显式统计 `id_switch_count`。
- `global_track_id` 当前由 D1/FusionAdapter 生成；D2 可以维护关联连续性，但不应把 D5/D7 的局部身份重绑定写回覆盖该 ID。
- 当前 D1 的 N actor 合同按输入数组长度输出航迹；D2 不应把 2v2/5v5 写成关联算法限制，2v2/5v5 只能作为 baseline 场景名。
- AirSim truth ID 和 dry-run `truth_id` 只能作为离线评估/测试辅助，不能作为在线关联真值捷径。

### 6.2 对 D3 分配规划

- D3 可使用 `track_level`、`a95_m`、协方差、`measurement_age_s`、`source_support` 和 `handover_readiness` 判断目标是否进入分配候选。
- D1 不生成 `AssignmentPlan`，也不管理 plan version；D3 必须继续按版本化计划拒绝 stale input。
- 如果 D1 航迹只处于 `coarse` 或 measurement age 过大，D3 应倾向继续观测、请求补传感器或保守分配，而不是把低质量航迹当成稳定目标。
- `ReconCueSummary` 可帮助 main/runtime 指向目标群或 `coverage_cell` 子群，但不替代 D3 的资源分配、版本化计划或重规划逻辑。

### 6.3 对 D5 末端关联

- D1 已支持 EO bbox/center pixel/camera metadata 的无截图合同，并输出可投影的 NED `GlobalTrack` 与协方差。D5 可用这些字段做相机平面门控和末端身份确认。
- `ReconCueSummary` 可作为二级侦察相机的粗指向 cue；D5 仍需用自身终端观测做身份确认，不能把 cue 当作在线 truth ID。
- D5 不得改写 `global_track_id`；末端视觉结果应作为 `TerminalAssociation`、`IdentityClaim` 或反馈证据回流，而不是本地重绑定中心 ID。
- 当前 D1 未实现 OpenCV calibration、畸变校正、`solvePnP` 或跨视角几何一致性；这些若进入 D5，应通过相机 metadata 和投影残差与 D1 合同对齐。

### 6.4 对 D6 评估指标

- D6 可消费 D1 已有 RMSE、track continuity、grading accuracy、延迟补偿消融、`TrackUncertaintySummary`、`FusionQualityRegionSummary`、`FusionQualityRegionWindowSummary`、`ReconCueSummary`、`LatencyAuditSummary`、source diversity 和 duplicate observation count。
- D1 已提供最小 CSV reader、区域质量摘要、区域窗口趋势、协方差增长率 helper 和 OOSM replay 计数；仍未提供 D6 长期批量 schema 和真实多 seed 阈值。
- D6 的 `id_switch_count` 仍由 D2/系统日志显式提供；D1 不应用 truth ID 在线替代该指标。

### 6.5 对 D7 导引

- D7 应只消费 `stable` 或 `handover` 级 `GlobalTrack` 作为离线中段导引输入，并使用协方差、新鲜度和 source support 做门控。
- 当 D1 的 `measurement_age_s` 或 `latest_observation_latency_s` 过大时，D7 应扩大预测门限、请求 D3/D4 重新规划或保持保守状态。
- D1 不提供真实飞控、硬件、毁伤或自动处置接口；`handover` 是仿真质量标签，不是授权状态。

## 7. 历史优先级基线（截至 2026-07-10）

### P0: EVAL 工程化硬化项（已实现，保持回归）

当前无运行级 P0 blocker。以下三项是已实现的 P0-A 保持回归项；若真实多 seed/闭环样本暴露未覆盖字段或验收缺口，按第 1.2 节最小验收口径进入 P0 backlog。

1. **FDIR-light**: 已实现 `SensorHealthSummary` 和 `FusionAdapter.sensor_health_summaries()`，输出 sensor health、fault reason、reject count、isolation hint 和 recovery state。
2. **协方差上下界限制**: 已实现观测与 track covariance floor/ceiling，长时间外推、低质量观测、遮挡和异常观测会记录 covariance limit reason。
3. **时间戳不确定性建模**: 已保持 `measurement_timestamp` 与 `arrival_timestamp` 双时间戳合同，并在观测、track metadata、summary 和 sensor health 中显式记录 timing uncertainty；10-50 ms clock drift 注入已进入接口回归。

### P1: 稳定 D1 到 main/D2-D7 的数据合同

已完成的 P1 基线：

1. **JSONL schema version**: 已固化 D1 replay schema v1，字段覆盖 `measurement_timestamp`、`arrival_timestamp`、`frame_id`、`measurement`、`covariance`、camera metadata、communication metadata、source lineage 和可选评估标签；legacy Blocks JSONL 继续兼容。
2. **CSV reader/转换工具**: 已实现最小 CSV reader/replay；JSONL-to-CSV 导出工具可在 D6 长期 schema 稳定后再补。
3. **区域质量摘要**: 已基于 `TrackUncertaintySummary` 增加轻量 `FusionQualityRegionSummary`，聚合 coverage cell、source gap、freshness、a95 和 handover readiness。
4. **延迟补偿审计**: 已记录 max/mean latency、OOSM replay 次数、stale/OOSM count、重复观测计数和 replay 历史长度。
5. **侦察粗指向摘要**: 已提供 `ReconCueSummary`/`summarize_recon_cue_from_tracks()`，覆盖全部 tracks、`coverage_cell` 过滤、缺省协方差保守降权和时间戳保留。
6. **source de-dup 与 replay 回归**: source lineage de-dup、Blocks JSONL replay、legacy JSONL 兼容和 N actor 合同已进入测试基线。
7. **P1 输入支撑字段回归**: dry-run fixture schema 检查、raw replay latency/OOSM helper、unsupported JSONL schema 回归、`covariance_scale_reason` passthrough 和 secondary/mobile recon cue metadata 保真已进入 D1 测试基线；sensor health、covariance floor/ceiling reason 和 timestamp uncertainty 继续作为 D6 可消费质量证据保持回归。

剩余 P1：

1. **显式 replay schema 与区域字段**: D1 v1 reader 已实现，但当前 main Blocks writer 的真实 2v2 日志没有 `schema_version` 和 `coverage_cell`，只能走 legacy schema 并生成 `unassigned` 区域；main/shared writer 需显式写 `d1.sensor_observation.v1` 并传递覆盖区域，D1 保持兼容但不修改 main/runtime。
2. **main/D6 长期批量 schema**: main tick 已发布 `TrackUncertaintySummary[]`，但尚未发布 `LatencyAuditSummary`、`FusionQualityRegionSummary[]`、`FusionQualityRegionWindowSummary[]` 和 `SensorHealthSummary[]`；需统一长期 JSONL/CSV 字段、covariance reason 与 timestamp uncertainty 命名。
3. **expected-latency/OOSM 健康阈值**: 扫描级水位线、整帧 too-late 拒绝和有限缓冲 API 已于 2026-07-22 在 D1 内闭合；真实 smoke 的固定 0.2 s 延迟仍需 main 采用该 API，并用传感器延迟预算和滑动比率区分正常 replay 与 clock/stale 故障，避免 advisory FDIR-light 在正常流上建议隔离。
4. **truth-free replay 一致性**: main bus 的 simulation-only truth-hint 配置未写入 replay provenance；默认无 truth-hint 重放同一 2v2 JSONL 会产生一条重复航迹。需记录融合/关联配置并校准无真值门控，使离线 replay 与真实在线约束一致，truth metadata 仅作离线标签。
5. **AirSim CV/Blocks multi-seed 回归**: 单次真实 2v2 smoke 已完成输入审计，但仍需 `simGetDetections`/detector boxes 的 N actor、多 seed JSONL/CSV 样本，覆盖 actor label、camera metadata、bbox covariance 和 secondary/mobile recon metadata；D1 不直连真实 AirSim runtime bus。
6. **真实样本区域/质量阈值**: 用带 `coverage_cell` 的多 seed 样本校准区域窗口、freshness/source-gap、协方差增长率和 handover readiness 的持续阈值。
7. **IMM/CV-CA-CT 多模型滤波**: 按 EVAL P1 同步为三个月内能力增强项，先做 CV/CA/CT 或等价模型对照和机动目标 replay/AirSim 评估，不替换当前 NumPy CV/EKF fallback；Stone Soup、FilterPy、MATLAB 只作为 benchmark 或调参参考。
8. **场景自适应协方差**: 在现有距离/质量协方差、bbox confidence/occlusion 输入和雷达参数化基础上，补遮挡、杂波、SNR、来源差异、延迟等 covariance scale rule，并在 replay/AirSim 输出 scale reason。
9. **Track-to-Track 融合原型**: 最小 NumPy CI、source/message 去重、共同时间传播和协方差保守性测试已完成；下一步是 D2-confirmed adapter、真实多节点 replay、成员退出和部分共享 lineage，完整外部库后端仍按收益评估。

### P2: 开源库和算法对照

1. **FilterPy 对照后端**: 以可选依赖方式验证 EKF/UKF 数值差异、运行时间和协方差一致性，不替换现有 NumPy fallback。
2. **Stone Soup 离线实验**: 先做 observation/track 转换、OOSM replay 或 JPDA/MHT/Track Fusion 对照，只有指标收益明确后再扩大接入。
3. **UKF/IMM 基准**: 构造高机动、强非线性和多模型场景，定义相对当前 CV/EKF 的 RMSE、NIS、连续性和计算成本收益门限。
4. **OpenCV/D5 几何对齐**: 将 calibration、畸变、`projectPoints`、`solvePnP` 作为 D5/D1 边界对照项，D1 保持 bbox/camera metadata/协方差合同。
5. **ROS 2 `tf2/message_filters` 评估**: 等 topic schema、tf tree、bag/replay 和 main/shared runtime 稳定后再接入；接入前仍由上游转成 NED 或提供完整外参元数据。

## 8. 历史基线：2026-07-11 P1 缺口复核

| 项目 | 当前状态 | 证据 | 后续责任 |
| --- | --- | --- | --- |
| writer `schema_version` | D1-owned 已关闭 | governed JSONL/CSV writer 强制输出 `d1.sensor_observation.v1` | main/shared 改用该 writer，D1 保留 legacy reader |
| config/scenario provenance | D1-owned 已关闭 | `ReplayProvenance` 强制 scenario/config ID、version/digest | main 传入真实 settings/config digest 和 episode seed |
| 在线 truth hint 隔离 | D1 fixture 已关闭，main 单 seed smoke 已接线 | writer 默认剥离 truth/actor/object ID；`p1_runtime_truth_isolated_d4d5_smoke_20260711` 三个 5v5 episode 在在线 truth 隔离后仍保持 D1 -> D2 -> D3 和 1.0 assignment coverage | 继续做 truth-isolated 多 seed、长时 replay 和离线 truth-only 评分审计 |
| `coverage_cell` 时间窗口 | D1-owned 已关闭 | 固定 `window_size_s` 分桶，窗口输出带开始/结束/持续时间 | main/D6 发布并聚合真实窗口 |
| 协方差增长率窗口 | D1-owned 已关闭 | track growth annotation 与 region window 聚合已回归 | 多 seed 标定报警持续阈值 |
| expected latency/OOSM health | 字段和判定基线已关闭 | 总/非预期 OOSM、期望延迟、容差、均值/最大值和超限率已导出 | 按真实 radar/acoustic/EO 延迟分布校准预算 |
| Blocks/CV JSONL/CSV fixture | 基础 P1 已关闭 | 静态 fixture 保留双时间戳、协方差、NED、coverage 和 provenance | 扩充真实 camera/bbox/遮挡、多 seed fixture |

当前无 D1 P0 blocker。剩余 P1 不再包含最小协同 DTO/WLS/CI 字段和数值 helper，而是 main/D2 runtime 接线、真实多 seed 阈值治理、视觉/协同 fixture、D6 长期趋势、IMM/场景自适应协方差和分布式 Track-to-Track 全链路。Stone Soup、FilterPy 仍未引入。

## 9. 历史基线：2026-07-11 Truth-Isolated 5v5 证据状态

证据目录：
`research_modules/airsim_runtime/outputs/p1_runtime_truth_isolated_d4d5_smoke_20260711/`。

| 核查项 | 当前证据 | 缺口判定 |
| --- | --- | --- |
| D1 -> D2 -> D3 在线断链 | 三个 5v5 case 均运行 5 帧；D1/D2/D3 health 为 `ok`，D1 每组 15 条记录，D3 assignment coverage 为 1.0 | 单 seed 短时 smoke 已通过，无 P0 断链 |
| 在线 truth 隔离 | main 在线关联不再依赖 truth hint，仍输出中心航迹和分配 | 单 seed 接线已通过；multi-seed/长时一致性仍为 P1 |
| D1 governance 进入 main bus | 每组均有 `d1_latency_audit`、`d1_region_quality_window`；metrics 含 delay、OOSM、region quality/readiness | 基础接线已完成；长期 schema 和完整 health/reason 字段仍为 P1 |
| OOSM 口径 | 三组 `d1_oosm_observation_rate=0.9866666667`，mean/max delay 约 0.2 s，stale rate 为 0 | 这是旧逐观测异步回放累计口径，不是传感器故障率；扫描水位线 API 已实现，main 接线后的预算和故障对照标定仍为 P1 |
| multi-seed 阈值治理 | 当前只有 seed 7、5 帧、0.4 s | 未关闭；必须保留 P1 |

因此本轮只更新证据状态，不关闭 D1 的真实多 seed、长时间窗口、sensor-specific latency、
故障注入负例、D6 长期 schema 和真实 Blocks/CV fixture P1。尤其不得把 raw OOSM rate
直接解释为 FDIR 隔离建议或 D4 主动降级条件。

## 10. M 对 N 协同定位 P0/P1 状态（2026-07-11）

文献与开源证据详见 `D1_M_TO_N_COOPERATIVE_LOCALIZATION_REVIEW.md`。本节只增加 P0/P1 现状，不改既有 P2/P3 外部库接入条目。

- **P0**：无新增 blocker。双时间戳、NED、观测/航迹 covariance、source lineage 去重和 canonical `global_track_id` 禁止本地改写仍为硬回归。
- **P1-协同几何质量 D1-owned 基础完成**：typed DTO/summary 已输出共同估计时刻、平台位姿/外参 covariance、measurement skew、LOS 交会角、联合信息矩阵秩/条件数、bearing residual、observer lineage 和 accept/reject reason；三架平台数量仍不得直接解释为 `handover` 就绪。
- **P1-异步三机构造基准完成，真实 replay 未完成**：单元测试覆盖 1/2/3/N observer、良好三视角、退化几何和 0.4 s 异步传播；near-synchronous/range、机动、遮挡、节点退出、AirSim 多 seed 及 RMSE/NIS/NEES consistency 仍缺。
- **P1-D1/D2 合同**：D2 应先确认 local TrackSummary 与 canonical `global_track_id` 的关联，D1 再进行数值 Track-to-Track 融合；当前尚无该双阶段合同和拒绝误融合事件。D1 不得因三角化结果自行创建替代身份。
- **P1-保守 Track-to-Track 数值原型完成**：NumPy CI 支持 1/2/3/N source、共同时间 CV 传播、process/timing covariance、message UUID/完整 lineage 去重并保持 canonical ID；已验证不比错误独立融合更自信。部分共享 lineage、D2/runtime adapter、成员退出 replay 和 Stone Soup 对照仍待补。
- **P1-到达时序边界**：D1 不要求三机严格同时观测或同时到达拦截点；必须按 measurement time 传播到共同估计时刻并报告 covariance growth。同步/分波次拦截决策属于 D3/D7。

P1 最小验收：良好几何下三机融合不劣于最佳双机；退化几何必须增大 covariance 或拒绝融合；relay 重发不改变 posterior；未知相关性融合保持保守；节点从 3 降到 2/1 时航迹连续且质量显式下降；在线链路不使用 truth/actor ID。

## 11. 历史基线与双轨实施顺序（2026-07-11 三 seed）

最新依据为
`research_modules/airsim_runtime/outputs/blocks_cv_m5_n2_liveness_batch_20260711/M_TO_N_AIRSIM_CONVERGENCE_REPORT_CN.md`：
seeds 7/17/27 均为 6 次 replan request、6 次 no-change ACK、0 applied、0 expired，需求满足率
1.0，错误重复锁定 0；T002 共识为 4/5/4 且 D7 每 seed 许可 2 次；T001 双 primary 共识为
0。该证据证明 ComputerVision 状态合同收敛，不是物理拦截证据，也没有关闭 D1 的真实
传感器、多机协同定位或长期阈值标定。

| 层级 | 当前结论 | 后续动作 |
| --- | --- | --- |
| P0 | 无运行级 blocker；双时间戳、NED、covariance、FDIR-light、上下界、时间戳不确定性、lineage 去重和 N-target 输入已闭合 | 维持 `62 passed` 回归，不降低合同 |
| P1 已完成接口 | governed writer/schema/provenance、truth 默认剥离、区域/窗口摘要、expected-latency/OOSM、recon cue、协同 DTO/WLS/CI | 接入 main/D2/D6，不重复实现 helper |
| P1 待实现/标定 | main writer 采用、D2-confirmed runtime adapter、真实多 seed 机动/遮挡/节点退出/camera fixture、RMSE/NIS/NEES、health/window 阈值、IMM/场景自适应 covariance、长期 D6 schema | 按真实 replay 逐项关闭；T001 共识由 D5/D7 主责，D1 只提供状态/协方差/几何质量 |
| P2 optional | FilterPy、Stone Soup、OpenCV/GTSAM、ROS 2 | 仅隔离 benchmark；不得替换默认 NumPy 主线 |

实施顺序为：main/shared 采用 governed writer 和离线 truth 分离；D1/D2 接通 canonical-ID
确认后的可选 WLS/CI adapter；main 采集 crossing、机动、遮挡、漏检、延迟和节点退出的
真实多 seed replay；D1/D6 校准统计与阈值；最后才运行 P2 第三方对照。每次 D1 能力变更后
使用
`PYTHONPATH=research_modules/d1_sensor_fusion/src pytest -q research_modules/d1_sensor_fusion/tests`
验收，并同步本审计、PLAN、README 和 review。

## 12. Governed Replay Manifest/Serializer P1 状态

本轮已关闭 D1-owned 的严格 manifest/serializer 实现缺口：

| 项目 | 当前状态 | 边界 |
| --- | --- | --- |
| manifest schema | 已实现 `d1.governed_replay_manifest.v1`，汇总 observation schema、NED working frame、时间范围、coverage cells、lineage 和 truth policy | main 负责持久化位置和 episode 组织 |
| scenario/config identity | strict provenance 要求 scenario/config ID、version、digest 和 seed | main 必须传入真实 settings/config digest；D1 不猜测 |
| record validation | 已校验双时间戳、covariance 形状/有限性/对称/半正定、coverage cell 和 source lineage | legacy reader 继续宽松兼容旧日志，不视为 governed 输入 |
| online truth isolation | 默认批量 serializer 递归剥离 truth/actor/object ID，opaque lineage 不含 truth fingerprint | 离线标签仅由 `serialize_offline_governed_replay()` 写入 `offline_truth` |
| 多目标与数值保真 | 已测试任意长度批次、双时间戳、NED frame、covariance、coverage 和 lineage 往返 | 未代表真实 AirSim 传感器标定完成 |

当前 D1 全量测试为 `62 passed`。因此“构造可供 main 调用的 governed manifest/serializer”
不再列为 P1 缺口；最新 main episode bus 也已采用该 API 并分离在线记录与离线 truth 标签。
仍开放的是更长的真实 multi-seed 数据生成与阈值标定、D1/D2-confirmed runtime fusion
adapter、D6 长期统计一致性和算法增强。P2 外部库安排不变。

## 13. 当前缺口判定（2026-07-11 最终验证）

最终依据为
`research_modules/airsim_runtime/outputs/p1_p2_validation_20260711/P1_P2_VALIDATION_SUMMARY_CN.md`。

| 层级 | 当前结论 | D1 边界 |
| --- | --- | --- |
| P1 合同层 | 已闭合 | main episode bus 已写 D1 governed replay；双时间戳、covariance、coverage/lineage 和 provenance 进入同一 episode 合同链，在线 truth/actor/object ID 被剥离，truth 仅进入独立离线标签 |
| CV 验收 | 8/10 通过 | 证明 D1 合同可被下游双 primary 链路消费；不表示 D1 负责视觉共识或控制许可 |
| 二级/分布式故障语义 | 3/3 ACK commit 正例和 2/3 ACK abort fail-closed 均通过 | D1 只提供状态、协方差、时间和质量证据，不参与 coalition commit/ACK 仲裁 |
| P1 物理/长期标定 | 未闭合 | SimpleFlight 15 s 为诊断，30 个 active pair 为 0 命中；不作为 D1 真实传感器或融合精度验收。D1 仍需真实 multi-seed 长 replay、sensor-specific latency/health/window 与 RMSE/NIS/NEES 标定；系统物理拦截闭环不由 D1 单独负责 |
| P2 optional benchmark | 隔离 harness 已完成；第三方后端 unavailable | 冻结 governed replay 已对当前 NumPy EKF/fixed-lag 输出 RMSE/NIS/NEES/耗时；FilterPy/Stone Soup 当前均未安装，结果包含 `unavailable_reason` 且指标为空。未新增默认依赖、未替换在线路径；真实第三方 adapter、UKF/IMM 仍开放 |

当前 D1 的 AirSim dry-run adapter、静态 JSONL/CSV fixture 和 ComputerVision 合同验证属于
adapter/smoke 证据；合成 radar/acoustic/EO 观测、CV/EKF 机动吸收及 WLS/CI 数值 helper
属于科研仿真基线。它们证明接口、数值合同和 truth policy 可回归，不等于真实传感器模型、
长时物理 replay、完整分布式 Track-to-Track 或第三方 tracker/fuser 已完成。

当前 D1 P1 后续项只保留真实 replay 与标定：D1/D2-confirmed cooperative adapter、机动、
遮挡、节点退出、camera/bbox、sensor-delay/fault 多 seed 数据，以及 RMSE/NIS/NEES、
sensor-specific expected latency、health/region window、模型集和场景自适应 covariance。
不得再把 governed writer 接入、在线 truth 隔离或 CV 双 primary 合同验收列为当前未完成项。

## 14. P2 隔离 Benchmark GAP 收敛（2026-07-11）

| 核查项 | 当前证据 | GAP 判定 |
| --- | --- | --- |
| 冻结输入治理 | `p2_governed_filter_benchmark_v1.json` 固定 manifest、scenario/config digest、seed、NED、双时间戳、covariance 和 lineage | 最小离线 benchmark 输入已闭合；不替代真实 multi-seed replay |
| truth 隔离 | online records 禁止 truth/actor/object metadata，truth 六状态只在独立 offline sidecar，测试覆盖泄漏拒绝 | benchmark 未向 `FusionAdapter` 注入 truth |
| 当前路径指标 | runner 输出 position RMSE、NIS、NEES、normalized consistency 和 wall time；结果为 `0.2335 m`、`0.0426`、`0.0651`，两次耗时 `6.9-10.1 ms` | 指标 plumbing 已闭合；小型合成样本的低 NIS/NEES 不关闭真实标定 |
| FilterPy | 当前环境依赖不可用，adapter 为 placeholder，输出 null metrics 和 `unavailable_reason` | 不得写成已接入；隔离安装后的可执行 EKF/UKF 对照仍为 P2 |
| Stone Soup | 当前环境依赖不可用，adapter 为 placeholder，输出 null metrics 和 `unavailable_reason` | 不得写成已接入；OOSM/JPDA/MHT/Track Fusion 对照仍为 P2 |
| 默认路径 | requirements 和在线 `FusionAdapter` 未修改 | NumPy EKF/fixed-lag 继续是唯一默认路径 |

本轮 D1 全量回归为 `62 passed`。因此 P2 可用性、不可用原因和当前路径指标证据已收敛；
第三方后端的算法收益仍未证明，不能因本轮 harness 完成而关闭相应实现 GAP。

## 15. 2026-07-12 P0/P1 状态同步

### 15.1 证据边界

- 当前仓库 `HEAD=33e6fa0`。该 commit 没有修改
  `research_modules/d1_sensor_fusion/**` 或 `subagent_reviews/D1_*`，因此 D1 无源码、测试和
  运行行为变化。
- `subagent_reviews/MAIN_IMPLEMENTATION_GAP_AUDIT.md` 的当前集中状态仍判定 D1 无新增 P0
  blocker，并把 D1/D2/D3/main 的真实长期 replay 治理列为开放 P1。
- `PNG_DELIVERY_ENHANCEMENT_AIRSIM_VALIDATION_REPORT_20260712.md` 验证的是 D5/D6/D7 与
  main/runtime 的 PNG delivery、2v2、dropout 和 M5N2 行为；报告没有 D1 实现变更或 D1
  精度验收。2v2 `20/20` 和 M5N2 `0/9` 均不改变 D1 GAP 判定。
- 2026-07-12 执行
  `PYTHONPATH=research_modules/d1_sensor_fusion/src pytest -q research_modules/d1_sensor_fusion/tests`
  得到 `62 passed in 11.60s`，与既有 D1 回归基线一致。

### 15.2 P0 状态

| P0 合同 | 实际状态 | GAP 判定 | 下一验收 |
| --- | --- | --- | --- |
| `measurement_timestamp`/`arrival_timestamp`、NED、观测/航迹 covariance | 已实现，当前回归通过 | 无开放 P0；本轮无行为变化/保持原状态 | 后续 replay 继续拒绝时间倒置、非法 frame 和非法 covariance，并保持六状态 NED `GlobalTrack` |
| fixed-lag/OOSM、source de-dup、N-target | 已实现，当前回归通过 | 无开放 P0；本轮无行为变化/保持原状态 | 乱序补偿、重复 lineage 抑制和任意输入长度回归不得退化，online path 不得消费 truth identity |
| FDIR-light、covariance floor/ceiling、timestamp uncertainty | 已实现，当前回归通过 | 无开放 P0；本轮无行为变化/保持原状态 | 正常 expected latency 不触发虚假隔离；故障注入输出 reason、reject/isolation hint 和 recovery evidence |

当前仍无 D1 运行级 P0 blocker。下游 PNG 物理拦截结果不是 D1 滤波 RMSE/NIS/NEES 或真实
传感器标定证据，不能据此重开或关闭 P0。

### 15.3 P1 状态与开放 GAP

| P1 项 | 实际状态 | 仍开放内容 | 下一验收条件 |
| --- | --- | --- | --- |
| governed replay/schema/provenance、coverage/lineage 与 truth policy | 已实现，main 已采用；本轮保持原状态 | 长时真实 multi-seed 治理验证 | 冻结 scenario/config version、digest、seed 和 evidence path；online truth 泄漏为 0，offline label 只用于评分 |
| region/window、expected-latency/OOSM、sensor health、recon cue | helper/字段已实现，真实阈值部分实现；本轮保持原状态 | sensor-specific 延迟预算、正常/故障对照、长窗口与 D6 趋势 | 多 seed fault-injection replay 量化误报/漏报；raw OOSM 不得直接解释为故障或 D4 降级动作 |
| 协同定位与 Track-to-Track | WLS/CI 数值基础已实现，runtime 全链路部分实现；本轮保持原状态 | D2-confirmed canonical-ID adapter、部分共享 lineage、节点退出和真实多视角 replay | 关联不唯一时 fail-closed；良好三视角不劣于最佳双视角；退化几何保守；3 -> 2 -> 1 时 continuity 保持且质量下降；重复 relay 不改变 posterior |
| 真实长期 replay 与统计一致性 | 未闭合；本轮保持原状态 | crossing、机动、遮挡、漏检、camera/bbox、节点退出、sensor delay/fault 的版本化多 seed fixture | 同一 governed replay 下审计 RMSE/NIS/NEES、continuity、health/region window；短时 SimpleFlight 命中率不得替代 D1 验收 |
| IMM/CV-CA-CT 与场景自适应 covariance | 未实现/待标定；本轮保持原状态 | 模型集对照及杂波、SNR、来源、遮挡、延迟 scale rule | 对冻结 replay 给出 CV-only 对照、RMSE/NIS/连续性/成本和稳定 `covariance_scale_reason`，收益不足时不替换默认 NumPy CV/EKF |
| D6 长期 schema/趋势 | 部分实现；本轮保持原状态 | 跨 seed 长期字段一致性、阈值和 unavailable 语义 | D6 稳定消费 latency、health、region/window、RMSE/NIS/NEES 和 evidence path；缺失字段显式 unavailable |

因此截至 2026-07-12，D1 仍开放的 P1 是：D1/D2-confirmed cooperative runtime 验证、真实
长期多 seed replay、sensor-specific health/window 与 RMSE/NIS/NEES 标定、CV/CA/CT/IMM
模型对照、场景自适应 covariance 和 D6 长期统计一致性。governed serializer、online truth
隔离、WLS/CI 数值 helper 与现有质量摘要不再重复列为未实现。P2/P3 保持原有规划，不删除、
不移动，也不因本轮 PNG delivery 验证新增完成项。

## 16. 2026-07-12 P1 合成长 Replay 收敛

### 16.1 已实现

| 项目 | 当前证据 | GAP 判定 |
| --- | --- | --- |
| 长时 challenge fixture | `long_replay.py` 提供可配置 N-target、60 s 默认 crossing、EO 遮挡、雷达 clutter/延迟/OOSM 和 relay duplicate | D1-owned 合成场景构造缺口关闭；不替代真实 AirSim 数据 |
| 版本与 provenance | scenario/config/summary/threshold profile 均冻结版本，并继续使用 `d1.sensor_observation.v1`、scenario/config digest、seed 和 run ID | 合成长 replay 治理关闭 |
| 在线 truth 隔离 | observation ID/lineage 不含稳定目标 slot；在线 metadata/records/`GlobalTrack` 无 truth/actor/object identity；真值只在显式 offline sidecar | 本轮测试 truth leak 为 0 |
| 延迟和质量汇总 | `summarize_long_replay()` 复用 raw/fusion latency audit、sensor health、region window、track level/source support 和 unavailable reason | D1-owned 汇总入口关闭 |
| 回归与默认成本 | long replay 新增 3 项接口测试和 1 项 CLI 子进程测试；默认 smoke 843 observations、21 injected OOSM、6 relay duplicates、29 region windows，约 8.8 s；D1 全量 `66 passed` | 可供 main 单 seed/批量调用；高频率仍由 main 显式配置 |
| 官方 CLI | `scripts/run_long_replay.py` 支持 seed/duration/target-count/output，写 `LongReplaySummary.to_dict()` JSON | main 可直接从仓库根目录调用；CLI 不形成第二套算法路径 |

### 16.2 仍开放 P1

1. **真实数据而非合成 fixture**：main 仍需采集真实 Blocks/CV crossing、遮挡、漏检、bbox、
   sensor delay/fault 和节点退出的长期多 seed replay；本轮生成器只用于可重复接口与故障口径
   回归。
2. **D1/D2 canonical-ID 对齐**：没有 D2 离线 canonical 对应时，summary 中 RMSE/NEES
   必须 unavailable。后续由 D2 提供确认映射后才能用 offline sidecar 评分，D1 不得把 sidecar
   注入在线关联。
3. **真实阈值治理**：sensor-specific expected latency、OOSM、health、region/window、NIS/
   NEES 和 covariance scale 阈值仍需多 seed 正常/故障对照标定。raw OOSM 比例不能直接解释为
   故障率或主动降级动作。
4. **模型与协同链路**：CV/CA/CT/IMM、场景自适应 covariance、D2-confirmed cooperative
   runtime、部分共享 lineage 和 3 -> 2 -> 1 节点退出仍未闭合。
5. **D6 长期趋势**：D6 仍需消费真实 evidence path、跨 seed schema 和 unavailable 语义；
   D1 本轮只保证 summary 为 JSON-safe 并显式标注 metric availability。

本轮没有新增或关闭 P2/P3 外部依赖项。Stone Soup/FilterPy 仍为隔离 benchmark，不进入默认
运行路径。

## 17. 真实 AirSim Replay 冻结缺口更新（2026-07-12）

| P1 项 | 当前状态 | 本轮证据 | 后续缺口 |
| --- | --- | --- | --- |
| main JSON/JSONL 到 governed replay | D1-owned 已实现 | 直接观测/frame 内嵌观测 loader、冻结 API、CLI 和四文件输出；不导入 AirSim SDK | main 仍需采集更长真实 multi-seed dense/crossing payload |
| 时间、NED、covariance、health 和 provenance | 已实现冻结合同 | measurement/arrival 严格保留；processing/publish、health、scene/profile/source schema 可用则保留，否则 unavailable；canonical frame/covariance/coverage 强校验 | sensor-specific latency 与 health/window 阈值仍需真实数据标定 |
| online truth 隔离 | 已实现并强化 | observation ID 不透明化；递归剥离 actor/object/truth key 和已知 identity token；truth ID/position 只进 evaluator-only sidecar | D2/D6 只可离线消费 sidecar，仍需 canonical mapping 审计 |
| crossing/遮挡/漏检/虚警/OOSM/节点退出 | 输入与诊断合同已实现 | 事件进入 summary；没有 measurement 的 frame 不生成 observation，`missing_measurements_fabricated=0` | 需要真实多 seed 事件分布和故障对照，不以 fixture 代替精度验收 |
| D2/D6 可消费产物 | D1-owned 输出已实现 | manifest、records JSONL、offline truth JSON、diagnostic summary JSON | RMSE/NIS/NEES、ID continuity 和长期趋势仍由 D2/D6 离线计算 |

当前 D1 无新增 P0 blocker。该实现关闭“D1 无法冻结 main 已持久化真实 AirSim 输入”的 P1
代码缺口，但不关闭真实采集、统计标定、D2 identity association 或 D6 长期报告缺口。D1
全量回归在 sidecar follow-up 后为 `74 passed`。

### 17.1 Truth sidecar 重复键修复

| 项目 | 当前状态 | 规则与证据 |
| --- | --- | --- |
| 同键 available/unavailable | 已修复 | `(truth_id,timestamp)` 唯一；available 确定性覆盖 unavailable，输入顺序不影响结果 |
| 同键 available 冲突 | fail-closed | 三维位置差异超过 `1e-6 m` 时直接拒绝 freeze，不选择任一来源 |
| 不同 timestamp | 保留 | 同一 identity 的时序 truth 样本不合并 |
| 仅 unavailable | 保守保留 | 不伪造位置；sidecar/summary 输出 availability counts 和 unavailable sample count |

该修复关闭 D1 -> D2 strict offline adapter 的重复键兼容缺口，不改变在线 replay、D2 关联或
main 采集逻辑。

### 17.2 Capture provenance 冻结合同

| P1 项 | 状态 | 证据 | 剩余条件 |
| --- | --- | --- | --- |
| 4 m/2 m 几何声明 | D1-owned 已关闭，真实采集已验证 | `target_spacing_m` 必须来自捕获 provenance；不从 truth 几何推断；调用或跨帧冲突 fail closed | 保持 4 m/2 m 各 20 seeds、共 40 episode 的回归，不把几何合同等同传感器精度标定 |
| scenario/config/seed/evidence | D1-owned 已关闭，D6 已消费 | manifest、records provenance、summary 均保留版本、seed、evidence path 和 digest；D6 将 `d1_dense_crossing` 标记为 `available` | 继续验证长时、跨场景 schema 和 evidence availability 一致性 |
| truth 在线隔离 | 保持关闭 | 在线 records 不含 truth；sidecar evaluator-only 并与 capture digest 绑定 | D2 仅离线消费 sidecar |
| 20-seed 合同回归 | 已实现并完成真实运行 | 4 m/2 m 各 20 seeds，共 40 个真实 AirSim episode；每 episode 51 帧；D1 全量 `79 passed` | 该证据验证冻结、truth policy 与可消费性，不替代 radar/acoustic/EO 长期误差标定 |

当前 D1 无 P0 blocker。仍开放的 D1 P1 是实际 Blocks/CV 长 replay 的 sensor-specific latency、
health/window、covariance 和 NIS/NEES 标定，不是冻结接口缺失。

## 18. 2026-07-13 P1 证据收敛复核

### 18.1 已关闭或保持关闭

| 项目 | 2026-07-13 真实证据 | GAP 判定 |
| --- | --- | --- |
| strict dense crossing 输入 | nominal 4 m 与 tight 2 m 各 20 seeds，共 40 个真实 AirSim episode、每 episode 51 帧、5 个目标 | D1 输入冻结与严格几何 provenance 缺口关闭 |
| evaluator-only truth | sidecar 共 10,200 个样本，`online_truth_leak_count=0` | 在线 truth 隔离保持关闭；truth 只供 D2/D6 离线评分 |
| governed replay 核心合同 | 双时间戳、covariance、NED、source lineage、scenario/config/seed/spacing/evidence path 均被保留和校验 | P0/P1 合同层已闭合，后续作为强制回归，不再列为实现缺口 |
| D6 消费状态 | 统一报告中 `d1_dense_crossing=available`，schema、digest 和 evidence path 可追溯 | D1 summary 可消费性关闭；缺失指标仍必须为 `unavailable` |
| D1 回归 | `79 passed` | 当前无 D1 P0 blocker |

### 18.2 仍开放的 P1

| P1 缺口 | 当前边界 | 关闭条件 |
| --- | --- | --- |
| 真实漏检/虚警/遮挡/异步率 fixture | 当前 strict 4 m/2 m capture 不能代表完整 radar/acoustic/EO 工程误差和故障分布 | 采集版本化多 seed 长 replay，显式覆盖各传感器漏检、匿名虚警、部分/完全遮挡、异步采样、sensor-specific latency 和节点退出；缺失量测保持缺失，不补造 |
| 区域窗口与协方差长期治理 | region/window、expected-latency/OOSM、sensor health 和 covariance reason 接口已实现，但真实持续阈值未冻结 | 正常/故障对照下给出跨 seed 误报/漏报、covariance growth、NIS/NEES 和 handover readiness 阈值；raw OOSM 不直接解释为故障或主动降级 |
| D1/D2-confirmed 协同融合 | WLS/CI helper 已实现，真实 canonical-ID adapter、部分共享 lineage 和节点退出 replay 未闭合 | 关联不唯一时 fail closed；3 -> 2 -> 1 节点退出时 continuity 保持且质量显式下降；relay 重发不改变 posterior |
| D6 长期趋势一致性 | 本轮 D1 source 已为 `available`，但证据集中于 dense crossing | D6 在跨场景长 replay 上稳定消费 availability、evidence path、latency/health/region window 和 RMSE/NIS/NEES；缺失项不补零 |
| 模型与自适应 covariance 标定 | 默认仍为 NumPy CV/EKF；CV/CA/CT/IMM 和 scene-aware scale 尚未完成真实对照 | 同一冻结 replay 下比较 RMSE/NIS/NEES、continuity、耗时和 reason 稳定性；收益不足不替换默认路径 |

### 18.3 P2 可选项不变

FilterPy、Stone Soup、UKF/IMM、OpenCV/GTSAM 和 ROS 2 `tf2`/`message_filters` 仍是可选
benchmark 或后续工程适配。当前第三方后端未安装或未接入时必须记录 `unavailable_reason`；
不得把 placeholder、availability probe 或当前 NumPy 结果写成第三方算法已实现。

## 19. 2026-07-14 P0 在线身份 Truth 暴露修复

| 项目 | 状态 | 证据 | 剩余边界 |
| --- | --- | --- | --- |
| Scene-derived `SensorObservation` 匿名化 API | D1-owned P0 已关闭 | 包顶层导出 `anonymize_online_observations()`；递归清理 truth/actor/object/segmentation 身份并重写 observation ID/source lineage | main/runtime 必须在每个 scene-state 在线入口调用；D1 不修改 main-owned call site |
| Fail-closed 在线 validator | 已关闭 | `assert_online_observations_identity_free()` 对残留身份键或已知 token 抛 `ValueError`；匿名化返回前强制调用 | 未出现在身份键下的别名必须由调用方通过 `identity_tokens` 完整提供 |
| 数值与几何保真 | 已关闭 | 两组各 2 条 EO 观测仅改身份名，匿名输出所有字段严格相等；measurement/covariance/双时间戳/bbox/camera geometry 不变 | 后续 main 集成需保持同一 API 顺序，不得在匿名化后重新附加 scene metadata |
| Offline truth sidecar | 保持原能力 | 单测证明输入对象未修改，`serialize_offline_governed_replay()` 仍保留原 truth/actor/object/classification 标签 | sidecar 仅供离线 evaluator，在线算法不得消费 |
| 2026-07-14 回归 | 通过 | 专项 `4 passed`；D1 全量 `83 passed`；接受阈值为全字段严格相等、0 泄漏、注入泄漏全部拒绝 | 本轮未运行 AirSim，系统 call-site 由 main 集成验证 |

该修复明确区分“仿真器使用 scene truth 生成噪声量测”和“在线算法看到身份 truth”：前者允许，
后者禁止。当前无 D1-owned P0 blocker。仍开放 P1 不变：真实 radar/acoustic/EO challenge 长
replay 与 sensor-specific latency/health，区域/covariance/NIS/NEES 持续阈值，D1/D2-confirmed
协同融合与节点退出，D6 跨场景长期一致性，以及同冻结输入上的模型/自适应 covariance 对照。

## 20. 2026-07-14 P1 重复 Birth 与状态跳变修复状态

| 项目 | 当前状态 | D1 证据 | 剩余关闭条件 |
| --- | --- | --- | --- |
| 同 observer scan 重复更新 | 代码与单测已关闭 | `(modality, observer, scan)` 每航迹只接受一次；跨 modality 同 scan 合法 | 同 seed 真实 replay 中 suppression 原因分布合理 |
| 雷达严格门限外重复 birth | 最小修复已实现 | 仅近期成熟唯一候选允许重捕；多候选 fail-closed 并审计 | 多 seed 标定重捕/误抑制率；不得使用 truth |
| 非测距状态异常修正 | 最小修复已实现 | 使用先验位置协方差审计修正分数，超门限拒绝 | 真实 EO/acoustic 场景标定门限和拒绝原因 |
| fixed-lag 后验丢失 | 代码与单测已关闭 | 检查点对齐最近已接受量测后验；origin/archive 支持旧 OOSM | 量测间隔、archive 内存和循环耗时多 seed 验证 |
| 历史 31.3/31.8 s AirSim 现象 | 根因已定位，场景证据未关闭 | D1 `87/87`；main runtime `134/134` | main 复跑同 M5N2 seed-001，航迹保持 2 且状态 teleport 消失 |

本轮未新增 D1 P0。开放 P1 是修复后同 seed 与多 seed 真实 AirSim 验收、门限统计和回放资源
预算；不把单元测试通过写成真实 episode 已闭合。Stone Soup、FilterPy、UKF/IMM、ROS 2
等可选项状态不变。

## 21. 2026-07-14 Covariance 合同硬化状态

| 项目 | 当前状态 | D1 证据 | 剩余边界 |
| --- | --- | --- | --- |
| 正式 online covariance | D1-owned 缺口已关闭 | `FusionAdapter`/在线匿名 validator 统一拒绝缺失、非有限、非对称、非半正定及 radar 4x4/legacy acoustic 1x1/`acoustic_3d` 2x2/EO 2x2/lidar 3x3 维度错误；拒绝发生在滤波状态修改前 | main/runtime 仍须调用 D1 正式入口，不得旁路构造内部滤波更新 |
| versioned governed replay | 已关闭 | reader、writer、manifest/serializer 共用严格 numeric contract；不再把一维数组静默 reshape | schema 新版本仍须保持相同或更强合同 |
| AirSim freeze | 已关闭并保持回归 | 缺/坏 covariance candidate 被拒绝，不生成在线 observation；现有七条合法 freeze record 保持通过 | 本轮未运行真实 AirSim episode，真实采集仍由 main 负责 |
| legacy 缺 covariance | 仅显式 offline migration 可用 | `migrate_offline_legacy_sensor_observation()` 写完整 imputation provenance；普通 reader 和所有在线/governed/AirSim 入口拒绝 migration object | migration default 仅供历史离线重放，不是传感器标定结果 |
| 2026-07-14 验收 | 通过 | 构造用例无 seed；覆盖缺失、non-finite、non-symmetric、non-PSD、wrong-shape、显式 migration 和合法正式路径；D1 `92/92` | 真实多 seed NIS/NEES 与 sensor-specific covariance 标定仍开放 |

该实现关闭“缺 covariance 可由在线融合器静默补成可信量测”的合同缺口，不关闭真实雷达、
声学、EO、lidar 噪声模型标定、长期 consistency 或场景自适应 scale。现有 covariance floor/
ceiling 只在合法输入通过后生效，不再承担输入修复。

## 22. 2026-07-14 P1 fixed-lag 批处理性能缺口

| 项目 | 当前状态 | D1 证据 | 剩余关闭条件 |
| --- | --- | --- | --- |
| 正式 batch API | D1-owned 已关闭 | `process_batch() -> FusionBatchResult`；逐条校验/审计/关联，批末每 dirty track 一次发布 | main/runtime 改为每 tick 一次调用 |
| 双时间戳/covariance/NED/source 保真 | 已关闭并回归 | 逐条与 batch 保留所有原始观测；重复 source 仅按 lineage 抑制；不同 modality 不合并 | main 接线不得预丢观测或改写 measurement time |
| OOSM 与 fixed-lag 边界 | 已关闭并回归 | checkpoint 前 observation 从 origin/archive 重放；dirty checkpoint 按需只重建必要次数 | 长时多 seed 继续审计 archive 内存和极端乱序成本 |
| 数值确定性 | 已关闭 | 同一输入顺序的 track ID/state/covariance 等价；构造容差 `1e-9`，真实 40 帧最大差 0 | main 完整 episode 比较 D1/D2 下游输出 |
| D1 重放性能 | D1-owned 代码缺口关闭 | 5-track/15-observation replay 95 -> 24；M5N2 seed-001 前 40 帧 1267 -> 351、18.05 -> 5.70 s | 完整 245/248 帧及至少 10 seeds 预算证据 |
| 系统 100 ms loop | 仍开放 P1，main-owned | 当前仅 D1-only persisted replay 证明 3.17 倍加速 | main 接线后拆分 RPC、观测生成、D1-D7、日志和 D6；达标前不得关闭 |

2026-07-14 D1 专项 `6 passed`、全量 `98 passed`，`git diff --check` 通过。当前仍无 D1 P0
blocker。该批关闭“D1 没有最少重放批处理能力”的 P1 实现缺口，不关闭完整 AirSim 实时预算、
真实 sensor-specific covariance/NIS/NEES、多 seed 长时阈值和 D1/D2-confirmed 协同融合。

## 23. 2026-07-20 可扩展三维扫描融合 GAP 状态

| GAP/合同 | 当前状态 | D1-owned 证据 | 剩余关闭条件 |
| --- | --- | --- | --- |
| 匿名 scalable bus adapter | 已实现 | `Scalable3DFusionAdapter` 鸭子类型消费 `OnlineSensorBatch`/等价 measurement；递归拒绝 truth/actor/object/entity/target ID 和 offline truth 对象 | main 将 bus topic 正式接线并验证 episode manifest/schema |
| 200 点迹批量起始 | D1 实现缺口已关闭 | 扫描前航迹与全扫描点迹做一对一 Hungarian；未匹配 radar 全部独立 birth；seed 7 的 200 首扫为 `200/200`，不再约 34 | 多 seed 漏检/虚警/dense crossing 的长期 recall/false-track 生命周期由 main/D2/D6 联验 |
| 六维 NED/covariance | 已关闭并回归 | 球坐标解析 Jacobian；状态 `[pN,pE,pD,vN,vE,vD]`、`6x6` covariance；原 `3x3` covariance 左上块严格保留，双时间戳同时发布 | 真实 sensor-specific NIS/NEES 与噪声标定仍开放 |
| 扫描级更新与 OOSM | 已实现 | 五档次扫全部一对一 update；2 目标延迟扫描的 2 条 OOSM 均重放且 ID/数量不变 | 长时极端乱序、fixed-lag archive 内存和吞吐继续验证 |
| 二维 acoustic bearing | 已实现弱约束 | `acoustic_3d=[azimuth,elevation]` 只更新既有 radar track；无先验时 5 条 bearing 为 0 birth | 多声学节点异步几何、误关联率和真实噪声标定开放 |
| 声纹身份边界 | 已关闭合同层 | 强制 `soundprint_is_identity=False`，转为 `soundprint_category_only=True`；类别概率不进入关联/birth/ID/truth hint | 后续若增加声纹类别标签，仍不得把类别或 embedding 当稳定目标身份 |
| 旧 baseline | 保持关闭 | 旧 `process()`/`process_batch()` 语义未改；D1 全量 `120 passed` | main 继续执行 2v2/5v5/M5N2 集成回归 |

验收日期 2026-07-20。五档各 2 个 scan，共 10 batch/750 条匿名 radar measurement；首扫与
次扫分别达到 `5/20/50/100/200` 全量 birth/update，未接受数均为 0。专项 `9 passed`，全量
`120 passed`。本轮证据是 seed 7 的确定性模块回归，不是 20 个未见 seed 的系统统计，也未
运行 AirSim。当前 D1-owned P0/P1 实现阻塞项已关闭；main 接线、D2 六维身份连续、D6 多 seed
recall/IDSW/RMSE/NIS/NEES 和长期性能仍开放。

## 24. 2026-07-20 无多普勒速度稳定性 GAP 状态

main 的只读诊断显示，radar-only、seed 17、50 条短 episode 中，D1 速度模长
median/P90/max=`6.28/12.16/21.03 m/s`，而速度 covariance trace 仍为
`101.24/110.31/112.32`。根因不是隐藏的低方差，而是三值雷达在 canonical 合同中补成四值后，
补零径向速度仍被量测模型消费，加上 0.2 s 短基线位置噪声通过 CV 交叉协方差进入速度均值。

| GAP/合同 | 当前状态 | 2026-07-20 D1-owned 证据 | 剩余关闭条件 |
| --- | --- | --- | --- |
| 未观测径向速度语义 | 已关闭 | canonical 仍为 4 维/`4x4`，但 `radial_velocity_observed=False` 时滤波严格使用前三维；测试直接检查 `z/R/h` 维数 | 真实 producer 若提供 Doppler，必须显式标为 observed 并单独标定四维模型 |
| 六维速度起始 | 已关闭代码缺口 | `v0=0`、`Pvv=25I m2/s2`、`Ppv=0`，参数公开可配置；无 truth/actor/object ID 和场景速度上界读取 | 多 seed 速度误差 coverage 和先验敏感性仍需 D6 标定 |
| 更新级创新门控 | 已关闭最小实现 | 三自由度 99.9% 卡方阈值 `16.2662`；构造离群点关联到既有航迹但滤波更新被拒绝，metadata 保留 innovation/update/rejection 审计 | 漏检、虚警、机动场景下误拒/漏拒率尚未冻结 |
| OOSM 与双时间戳 | 保持关闭 | 2 航迹、顺序/乱序 3 scan 在共同发布时刻 state/covariance 差 `<=1e-9`；2 条 OOSM、双时间戳与 `6x6` covariance 保持 | 长 fixed-lag/archive 内存和极端乱序吞吐开放 |
| 200 条多帧稳定性 | D1 模块缺口关闭 | seed 17、10 scan、2,000 条匿名 radar measurement 始终为 200 个 ID；末帧速度 `3.87/6.43/8.54 m/s`，速度 trace `57.97/60.69/61.19` | 20 个未见 seed、漏检/虚警/crossing 与 D2/D3 正式集成仍开放 |

专项由 `9` 增至 `13 passed`，D1 全量由 `120` 增至 `124 passed`。50 条开发探针修复后速度为
`3.99/6.12/9.69 m/s`，速度 covariance trace 仍为 `58.22/60.43/60.90`；这关闭的是 D1
短基线均值放大代码缺口，不代表速度已经高精度收敛。D2 二次滤波和 D3 第二轮分配必须由 main
使用当前代码正式复测。AirSim 集成计划已检查，本轮没有 AirSim 接口或运行证据变化，无需修改。

## 25. 2026-07-20 Scalable consistency evidence GAP 状态

| GAP/合同 | 当前状态 | D1-owned 证据 | 剩余关闭条件 |
| --- | --- | --- | --- |
| 逐更新 NIS/门控 DTO | 已关闭 | versioned truth-free record 覆盖 birth/update/gate reject/OOSM/未关联；保留 lineage、sensor、双时间戳、dimension/NIS/gate、range/quality/covariance reason、D1 source-track/estimate availability | main episode writer 持久化正式 artifacts |
| Schema/hash/provenance | 已关闭 | source/config、records、bundle digest；tamper、额外在线 truth 字段与 non-finite fail closed；online/offline aggregation rows 可按 scenario/sensor/range 分组 | main/D6 冻结跨模块文件名和 retention policy |
| Offline truth 与 D2 mapping 隔离 | 已关闭 D1 adapter 合同 | 独立六维 NED truth sidecar；D2 evaluator-only adapter 按 `observation_id + measurement_timestamp` 绑定 online/truth digest，并分离 D1 `source_global_track_id` 与 D2 canonical `global_track_id`；无 mapping 不算 RMSE/NEES | main/D2 将正式 D2 `source_observation_ids` artifact 转成该 adapter 并验证完整覆盖 |
| RMSE/NEES/NIS coverage evaluator | 已关闭公式/API | 精确 measurement-time 对齐；RMSE、NEES、normalized metrics、NIS gate coverage；无近邻/名称猜测；奇异 covariance 不算 NEES | D6 接线并冻结多 seed 统计阈值 |
| 正式多 seed consistency | 仍开放 P1 | 本轮只有确定性 oracle；`5 m/12 m/s/0.5` 仅验证公式 | 至少 20 个未见 seed，按 sensor/range/scenario 统计 CI/coverage 并通过预注册阈值 |

验收日期 2026-07-20。新增合同专项 `12 passed`，main 复跑 D1 全量 `136 passed`。该批只关闭
“episode producer 没有可持久化 consistency evidence DTO”和“无严格离线 evaluator 合同”两个
D1-owned 评估接口缺口；不关闭真实 covariance 标定、滤波一致性、速度/位置精度、复杂场景
生命周期、D2 identity continuity 或系统实时预算。AirSim 影响已检查并在模块计划中记录：未接线、
未运行、历史 availability 不变。

## 26. 2026-07-22 整帧迟到扫描输入 GAP 状态

| GAP/合同 | 当前状态 | D1-owned 证据 | 剩余关闭条件 |
| --- | --- | --- | --- |
| arrival-order 扫描入口 | 已关闭 | `SensorScanFrame` 和 `ScanInputOrganizer.ingest()`；每帧保留双时间戳、covariance、canonical/NED source frame 和 lineage；字段级只读快照兼容嵌套 `mappingproxy` | main-owned bus 将每个 `OnlineSensorBatch` 转为一帧并调用 |
| measurement-time 水位线 | 已关闭 | `W=max_seen_measurement-max_lateness`；边界等时刻保持开放，严格早于既有水位线整帧 too-late | 20/50/100/200 长 episode 标定 `max_lateness_s` 和误拒率 |
| duplicate/replay/conflict | 已关闭 | 不使用 truth 的 scan/content/lineage digest；逐帧和累计分项审计 | main/D6 持久化 schema 并校验长期 claim 上限 |
| 有限缓冲 | 已关闭 | 驻留时间、扫描数、观测数和 claim scan/lineage 均有配置上限；溢出保守拒绝新整帧 | 多 sensor 高负载下冻结容量并测峰值/吞吐 |
| 动态 N | 已关闭模块合同 | 1/7/200 点扫描均可接收/关闭/释放，无 2v2/5v5 常量 | 系统多 seed 规模化运行仍由 main 验收 |
| D1/D2 边界 | 已关闭接口，未接线 | `released_scans` 是唯一可进入 `process_scan_batch()` 的集合；rejected/buffered 不产生航迹 | main 仅将融合后的 tracks 交给 D2，并发布 audit 给 D6 |

版本为 `d1.scan_input.config/frame/audit_event/audit_summary/result.v1`。2026-07-22 的 15 项构造
测试无随机 seed、无 AirSim，覆盖有序、窗口内乱序、too-late、同时间多源、duplicate、relay
replay、timestamp conflict、arrival regression、容量、驻留超时、动态 N、truth 注入和
`OnlineSensorBatch -> SensorScanFrame -> process_scan_batch` 组合，并覆盖嵌套 `mappingproxy`
视觉元数据的独立只读快照与 truth 隔离；D1 全量 `151 passed`。

本项关闭的是 D1-owned 可执行输入合同，不是完整 fixed-lag Kalman OOSM 回溯。后者仍由
`FusionAdapter` 在释放后执行。main 接线、实际 lateness/residence/capacity 参数、无扫描 tick 的
`advance_arrival_time()`、episode 尾部 `close()`、长期 claim memory 和 D2/D6 持久化是开放
系统 P1。当前无新增 D1 P0 blocker。

## 27. 2026-07-22 正式治理与 development 吞吐 GAP 状态

### 27.1 制品核验

快速治理制品的 runner 标记为 `fast_3d_governance_benchmark`、`formal`、clean worktree，
提交为 `e4d66db02a0b8f1b867a0e81b4a73de84588426b`，并显式给出
`full_system_evidence=false`。20 个 episode 覆盖四档规模、每档 5 个 seed；20/20 manifest
均为 `repository_dirty=false`。每个 episode 136 帧/33.75 s，D1 每例重排 12、拒绝/过旧/
溢出 0、峰值缓冲 3、结束缓冲 0，在线 truth 使用 0。200 档峰值内存均值
40,914,828.4 B、最大 40,926,870 B。

聚合报告绑定的输入 SHA-256 与实际文件一致，输入清单引用的 60 个制品全部通过独立 SHA-256
复核。因此 clean/formal 观测治理复跑缺口关闭。该 runner 不导入完整运行时模块，不能据此
关闭融合吞吐、精度或完整系统效果。

全栈制品为单一 seed 42000 的 200v200 三维质点 2.2 s smoke，工作区同样 dirty。D1 接收并
释放 86 个扫描/2,051 条观测，重排 10、拒绝 0、峰值缓冲 33 个扫描/623 条观测，结束缓冲 0。
`module.d1_fusion` 累计 35.114923 s，平均 408.313 ms；`module.d1_scan_input` 累计
2.681969 s，平均 31.186 ms。全栈墙钟 60.210 s，实时倍率 0.037。单次治理报告没有正式
evaluator sidecar，精度、召回和一致性指标不可用。

### 27.2 P1 根因边界

当前 main 对水位线释放的每个 scan 都调用一次 `process_scan_batch()`。该调用保持正确的扫描级
一对一关联，却同时执行 measurement-time 状态获取、fixed-lag replay、changed-track 终结传播、
全航迹结果快照和在线 evidence 更新。相机产生的少量观测小扫描也承担相同调用边界；episode
尾部虽然可合并 D2 中间发布，D1 仍要处理所有释放扫描。现有数据只能证明该调用粒度与 200
规模下的高耗时相关，尚未完成函数级 profiler，不能把全部 35.115 s 归因于单一内部函数。

### 27.3 优化与验收思路

1. 按 scan modality/size、正常/尾部释放、track/history 数量采集关联、`_state_at`、历史重放、
   发布传播、后验物化和 evidence 序列化的独立耗时与 cache 命中率。
2. 以不改变扫描级关联顺序为前提，研究已关闭 measurement-time cohort 的 release micro-batch；
   对多个小扫描延迟全局发布，但逐扫描保留 audit 和接受/拒绝证据。
3. 将最终传播和快照限定为 dirty tracks，复用未变航迹的只读结果；缓存必须以 history revision
   为键，任何新观测只失效受影响航迹。
4. 相同冻结输入上要求 track ID 集、state/covariance、双时间戳、OOSM、innovation/gate 和
   truth-use 与基线一致，数值容差沿用 `1e-9`。不得丢观测、缩短合法历史、伪同步或收紧
   covariance。
5. clean/formal 快速治理多 seed 已完成。后续从 clean commit 运行 20/50/100/200 未见多 seed
   D1-only 和完整全栈基准，记录固定硬件下 P50/P95/max、峰值内存和实时倍率。D1 周期预算由
   main 预注册；历史 100 ms AirSim 预算只作参考，不能自动当作 200v200 正式阈值。

P1 关闭需要同时满足治理审计、数值等价和吞吐预算。AirSim、传感器精度与 200v200 任务效果
仍是独立验收项。

## 28. 2026-07-22 逐扫描融合性能 GAP 状态

| GAP/合同 | 当前状态 | D1-owned 证据 | 剩余关闭条件 |
| --- | --- | --- | --- |
| 函数级性能归因 | 已关闭 | 未优化 cProfile：`_state_at=38.120 s`、`_replay_record=46.097 s`、`_filter_update=37.615 s/93,234 calls`；`global_tracks=9.856 s`、`sensor_health_summaries=7.291 s/16,653 calls` | 保持 benchmark 输入哈希和操作计数可复核 |
| 重复 fixed-lag 后验计算 | 已关闭 D1-owned 热点 | 每航迹增量后验检查点；顺序复用前缀，窗口内 OOSM 仅失效后缀，重基/起始变化/检查点前 OOSM 完整失效 | clean 多 seed 长历史的峰值内存和检查点增长由 main 验收 |
| consistency evidence 等价 | 已关闭 | 缓存命中仍重建 evidence revision；86 个扫描逐扫描语义、终态 201 航迹和 evidence 哈希与未缓存参考一致 | D6 继续消费现有 schema，不把性能计数解释为精度指标 |
| 重复发布审计 | 已关闭 | association/latency/sensor-health 每扫描构造一次，全部 `GlobalTrack` 仍携带完整副本；health snapshot `16,653 -> 86` | 后续 schema 扩展须保持公共快照只读和每航迹输出独立 |
| 发布数组别名 | 已关闭 | `GlobalTrack.state/covariance` 与内部后验解耦，外部原地修改后再次发布仍保持内部值 | 保持防别名单测 |
| 完整系统周期预算 | **P1 开放，main-owned** | D1-only 未缓存 34.701 s、优化 9.073 s，单机单次 3.82 倍；操作数下降 98.07% | clean 20/50/100/200 未见多 seed 全栈 P50/P95/max、固定硬件配置和预注册预算 |

冻结输入 SHA-256 为
`38d24429711b67d612f2f398478386ebf0df690fae55cd9dcc36434aac4fb078`，含 86 个扫描和
2,051 条匿名观测，10 次重排，峰值 33 扫描/623 观测，在线 truth 使用 0。专项覆盖
1/7/200 动态规模、逐扫描语义等价、操作数下降、乱序后缀失效、检查点前合法 OOSM、
consistency evidence 和发布数组隔离。D1-owned 冻结输入性能热点据此关闭；正式融合精度、
AirSim 和完整 200v200 实时性保持开放。性能专项 `6 passed`，main 复跑 D1 全量
`157 passed in 28.77s`。

## 29. 2026-07-22 Clean 200v200 延迟物化接线 GAP 状态

| GAP/合同 | 当前状态 | 证据 | 剩余关闭条件 |
| --- | --- | --- | --- |
| main state-only/末尾快照接线 | 已关闭三维质点集成项 | clean `8f86192`；10 s seeds 42000-42002；state-only `310/328/278`，完整快照 `454/516/504`，逐例合计全部扫描 `764/844/782` | AirSim writer 和跨 tick heartbeat/lineage sidecar 仍独立开放 |
| 逐扫描语义与审计 | 已关闭本组回归 | 所有扫描仍逐个融合和发布；事件、scan input、共享摘要和世界真值与旧 clean `3bac3ff` 对应 seed 相同 | 后续 schema 变更保持该等价检查 |
| 在线安全合同 | 已关闭本组回归 | 3/3 clean、finite，在线 truth 使用 0，D1/D2 overflow 0，安全合同全部通过 | 扩展更多未见 seed、故障和更长历史 |
| D1 全栈分项改善 | 已形成描述性证据 | 10 s 三 seed D1 fusion 均值 `103.339 -> 92.991 s`，下降 10.0%；2.2 s seed 42000 全栈墙钟 `18.611 -> 18.302 s` | 固定硬件和预算后统计 P50/P95/max、峰值内存与更长时增长 |
| 完整系统实时预算 | **P1 仍开放** | 候选 10 s D1 fusion 均值仍为 92.991 s | 达到预注册周期预算；不能以三 seed 平均改善替代实时验收 |
| 正式融合精度与 AirSim | **P1 仍开放** | 本组是匿名三维质点输入，未改变 AirSim 或生成正式 RMSE/NEES/NIS | D2 canonical mapping、独立 truth sidecar、多 seed consistency 与真实 AirSim 接线 |

本轮没有新增 D1 P0。clean 三 seed 已关闭“main 尚未接入延迟物化”和“没有 clean 全栈语义
复跑”的旧表述；实时、长历史资源、正式精度、真实时延分布和 AirSim 仍是开放 P1。证据目录为
`research_modules/scalable_3d_simulation/outputs/scalable_3d_long_duration_candidate_20260722_clean_8f86192/`。

## 30. 2026-07-22 最终跨提交集成 GAP 状态

| GAP/合同 | 当前状态 | 证据 | 剩余关闭条件 |
| --- | --- | --- | --- |
| certified radar pre-gating 集成等价 | **当前三 seed 已关闭** | clean `8f86192 -> f80b5bd`；三个 seed 的 D1 fused-track 规范哈希一致，终态航迹 `202/207/203` 一致；未认证矩阵保留精确 `pinv` fallback | 对更多未见 seed、异常 covariance 和更长历史保持同一审计 |
| 跨提交业务语义 | **当前三 seed 已关闭** | 逐条总线语义 3/3 通过；仅归一化 opaque `plan_id`，且 ACK 原始载荷 SHA 先验证；owner/version/coalition/`global_track_id`/command 未忽略 | 后续任何算法变更继续执行逐条语义审计，不能只比较最终数量 |
| D1 fusion 性能 | 已形成描述性改善 | 三 seed 累计耗时均值 `92.991088 -> 88.330438 s`，约 -5.01%；精确求解总数约 -77.86% | 固定硬件预算、P50/P95/max、更多 seed 和长时增长 |
| D1 scan input 性能 | **P1 开放** | 三 seed 累计耗时均值 `16.902643 -> 17.524242 s`，约 +3.68% | 剖析增长来源并在不改变双时间戳、水位线、拒绝/释放语义的条件下治理 |
| 系统实时与长时超线性 | **P1 开放** | 候选仍未达到实时，当前长时归一化检查继续标记 D1 scan input、D1 fusion 和 module stack | 达到预注册固定硬件预算，并通过更长时、多 seed 归一化增长验收 |

证据位于
`research_modules/scalable_3d_simulation/outputs/scalable_3d_long_duration_candidate_20260722_clean_f80b5bd/`。
本轮没有新增 D1 P0 blocker，也没有新增 AirSim 或正式 RMSE/NEES/NIS 证据。
