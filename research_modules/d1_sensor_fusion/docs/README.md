# D1 文档索引

本目录保存 D1 多传感器融合与目标配准模块的说明文档。

## 当前证据索引（2026-07-23）

最新设计决策见
`STRUCTURAL_AMBIGUITY_NEXT_CANDIDATE_DESIGN_CN.md`。该文件比较 publication overlay、
fixed-lag OOSM 共同质心事件和 D2 概率/多假设消费三条路线。A1 已在提交 `de73cb2` 达到
`IMPLEMENTED_UNIT_TESTED_OFFLINE_PROTOTYPE`：共同质心只作用于 detached 发布 DTO，拒绝
装配直接返回规范业务序列，不修改 state/covariance、历史、checkpoint 或 replay cache。
聚焦测试 `7 passed`，D1 全量 `294 passed`。A1 未接 `FusionAdapter`，没有修改 `fusion.py`
或新增运行开关，其 experimental decision 不是在线 schema。A2 冻结扫描 shadow、A3 匿名
treatment 发现和 A4 多 seed 确认均未实现。B 因当前 `Q(h)=G(h)qG(h)^T` 的单段/分段传播
不等价而暂缓；C 保留为 D2 后续主要系统研究路线。seeds 1101/1102 继续停止。

最新 D1 边界诊断复用 governed replay、扫描组织器和在线批融合入口，对同步平衡、乱序平衡和
数量不平衡三类结构歧义冻结扫描进行控制臂/共同质心候选臂比较。同步 `2x2` 纯交替环形成一次
`15.000000 m` 共同平移；乱序场景以 `oosm_scan` 拒绝；成员/观测 `2/1` 的场景以
`unbalanced_component` 拒绝。两个拒绝场景共同质心 correction 均未施加，但拒绝后的
publication-base replay + replace 造成候选减控制协方差差最小特征值
`-0.0071928353214153066`、`-0.004617076466238031`；这是有限的重放替换诊断差异，不是
严格无副作用路径，也不构成晋级，边界为 `candidate_not_promoted`。该历史诊断专项
`5 passed`，当时 D1 全量 `287 passed in 18.03s`。报告和 JSON 位于
`../reports/structural_ambiguity_centroid_replay_20260723/`。该证据只确认受控边界，不是
AirSim、多 seed 或候选晋级证据。

当前 D1 尾延时工作区验证已完成完整帧复用、冻结 replay 严格等价审计和全量回归；main 实测
该阶段 D1 全量为 `185 passed`。这是历史阶段计数，详细证据见
`../reports/D1_TAIL_LATENCY_PERFORMANCE_20260723_CN.md` 和对应 JSON。

最新 main 全栈校准来自 detached clean
`4ac3bb2c12cc6af6ebd372107ced00bcdc5adf6a` 的 `200v200-nominal-v1`、10 s、seed 1000，
并与 clean `0d2da25c14e50f8f9a10ad47a7bd74e5c5e577fb` 同 seed 对照。11,889 条匿名在线观测下，
候选状态有限、在线 truth 0；核心 wall `94.104939744 -> 85.002427712 s`
（下降 9.6727%，1.1071x），D1 fusion `49.697406826 -> 40.272795088 s`
（下降 18.9640%，1.2340x），scan input `12.315225105 -> 12.560936034 s`
（增加 1.9952%）。候选核心 RTF 为 `0.1176437`，D1 fusion P50/P95/max 为
`33.25249/224.76351/592.95713 ms`。规范在线载荷、truth state 和计划谱系跨构建检查均通过。
外部总进程 `1:55.95` 与峰值 RSS `2,468,928 KiB` 只作为进程资源口径，不能与
85.002427712 s 核心 wall 混写。本批是单 seed 描述性 clean 校准，不是 20-seed 或正式矩阵，
未达到实时；fusion 尾延时与 scan-input 继续为 P1。

历史 D1-owned 非雷达关联专项使用未见 seed 1000 的 10 s 冻结输入。前 256 个扫描和
4,087 条观测在同进程预热后交错运行 7 次，逐候选/矩阵栈路径 P50 为
`12.242/10.238 s`，P95 为 `13.340/11.248 s`。完整 771 扫描、11,889 条观测的单次墙钟
`50.458/39.994 s`；逐扫描、终态、一致性证据、操作计数和累计诊断严格一致，在线 truth 0。
完整 cProfile 的 `pinv` 调用由 496,625 降至 1,018。该 2026-07-22 专项当次历史回归为
`182 passed in 15.92s`，不是当前权威测试计数。
该结果不关闭完整系统实时、AirSim 或正式精度。

最新 D1-owned 长时优化处理合法缓存一致性证据的重复完整校验。clean `f80b5bd` 10 s seeds
42000-42002 的完整重验/受限复制纯融合均值为 `64.844/52.657 s`，3/3 更快，聚合加速
`1.231x`。逐扫描状态、协方差、时间戳、谱系和分级，终态航迹、最终证据及操作计数严格一致；
在线 truth 使用为 0。代表 seed 的证据刷新累计 `27.122 -> 1.664 s`。D1 全量
`178 passed in 14.80s`。该结果不关闭实时、AirSim、长于 10 s 的增长率或正式精度。

最新 D1-owned 雷达关联优化使用 clean `8f86192` 的 10 s 冻结输入 seeds 42000-42002。
预门控只处理通过有限性、严格对称、Gershgorin 严格正定和 `pinv` cutoff 安全裕量认证的创新
协方差；其余矩阵全部回退旧精确 `pinv`。非正定交叉协方差和近奇异截断负例均证明 rejection
mask 不会预拒绝旧路径会保留的候选，扫描级语义保持一致。三 seed 旧/新纯融合墙钟均值为
`91.313/88.619 s`，3/3 更快；精确创新求解合计 `7,130,228 -> 1,578,677`。逐扫描、终态和
一致性证据哈希完全一致，D1 全量 `175 passed in 26.69s`。结果不关闭实时、AirSim 或正式精度。

clean 候选提交 `8f86192` 已完成 200v200 三维质点全栈的同一运行时刻延迟物化接线复跑。
10 s seeds 42000、42001、42002 均为 clean、finite，在线 truth 使用 0，D1/D2 overflow 和安全
合同全部通过。相对旧 clean `3bac3ff`，D1 fusion 三 seed 均值
`103.339 -> 92.991 s`（-10.0%）；state-only 扫描为 `310/328/278`，完整快照为
`454/516/504`，两者逐例合计全部 `764/844/782` 个扫描。事件、扫描输入、共享摘要和世界真值
保持一致。seed 42000 的 2.2 s 全栈墙钟为 `18.611 -> 18.302 s`。该结果不关闭实时预算、
AirSim 或正式精度。证据目录为
`../../scalable_3d_simulation/outputs/scalable_3d_long_duration_candidate_20260722_clean_8f86192/`。

长时固定滞后专项直接回放 10 s 冻结输入，SHA-256 为
`3efa561a07bf0cdcd74d23570ee23ca173f56ddaf632c89258d02c20c299a51a`，包含 764 个扫描、
12,107 条匿名观测和 202 条终态航迹。旧路径与优化路径保持逐扫描、终态和一致性证据哈希
一致；history replay `170,106 -> 13,397`，filter update `120,440 -> 9,549`，纯融合墙钟
`157.237 s -> 107.449 s`。报告位于
`../reports/D1_LONG_DURATION_PERFORMANCE_BENCHMARK_CN.md` 和对应 JSON。发布侧 186.2 MiB
全量快照是延迟物化接入前的历史基线；main 现已在同一 fusion timestamp 内仅物化末次后验，
跨 tick 发布节流和 heartbeat/lineage sidecar 仍是计划项。

第二阶段扫描关联工作区使用 clean `492979e` 的 seed 42000 冻结输入，SHA-256 为
`bc539686b130d96c63b76b9161fadbae2dba59de44cb61ac80d92f2ea1018406`。current-default 与
优化路径保持 86 个逐扫描语义、最终 201 条航迹和 consistency evidence 哈希一致；候选对和
创新求解均保持 371,054，量测模型构造 `16,457 -> 82`，墙钟 `10.792 s -> 8.635 s`。
专项 10 项和 D1 全量 161 项通过。详细结果位于
`../reports/D1_SCAN_ASSOCIATION_PERFORMANCE_BENCHMARK_CN.md` 和对应 JSON。后续 clean 三 seed
全栈复跑已完成，结果见上文；该结果仍不代表 AirSim 或完整系统实时。

最新 D1-owned 性能证据使用 seed 42000 的冻结 200v200 输入：86 个扫描、2,051 条匿名观测，
输入 SHA-256 为 `38d24429711b67d612f2f398478386ebf0df690fae55cd9dcc36434aac4fb078`。
增量后验检查点和每扫描公共发布审计快照保持逐扫描、终态航迹及 consistency evidence 哈希
等价；filter update `93,234 -> 1,797`，health snapshot `16,653 -> 86`，墙钟
`34.701 s -> 9.073 s`。详细结果位于
`../reports/D1_SCAN_FUSION_PERFORMANCE_BENCHMARK_CN.md` 和对应 JSON。

最新正式治理证据来自 clean 提交 `e4d66db02a0b8f1b867a0e81b4a73de84588426b`。
20/50/100/200 各 5 seed，共 20/20 formal episode；每例 136 帧/33.75 s，D1 重排 12、拒绝/
过旧/溢出 0、峰值缓冲 3、尾部缓冲 0、在线 truth 使用 0。200 规模峰值内存均值约
40.91 MB、最大 40,926,870 B。输入和 60 个引用制品的 SHA-256 均通过复核。

历史单次 200v200 三维质点全栈 smoke 为 development seed 42000/2.2 s，D1
处理 86 个扫描和 2,051 条观测，重排 10、拒绝 0、峰值 33 帧/623 条观测；fusion 累计
35.115 s，扫描输入累计 2.682 s，全栈墙钟 60.210 s。正式治理结果和该 development 全栈结果
都不是 AirSim、融合精度或完整 200v200 拦截验收。

版本化扫描输入整理仍是强制合同。15 项确定性专项覆盖水位线、整帧 too-late、
duplicate/replay/conflict、有限缓冲、同时间多源、动态 1/7/200 点输入及嵌套只读视觉元数据
快照。逐小扫描重复后验热点已经在冻结输入上关闭；clean 全栈多 seed、长历史内存和精度标定
仍开放。

历史最新真实 AirSim 证据仍为 2026-07-15 M5N2：

该 AirSim 增量包含 M5N2 baseline/candidate 各 10 case，共 20 case。在线 identity/state
truth use 均为 0；D1 fusion 的 3,805 个时序样本 mean/P95/max 为
`320.00/451.46/1234.88 ms`，真实运行时 100 ms 预算尚未闭合。本批不提供可用 NIS、NEES
或 RMSE，不能替代 D1 传感器精度与一致性专项。额外 `png_ttc_2v2_seed001` 已排除，dropout
完成数为 0。

详细系统证据见 `../../../subagent_reviews/MAIN_M5N2_TIMING_AND_SECOND_PRIMARY_REPORT_20260715.md`；
D1 侧解释见本目录各算法/AirSim 文档和 `../reports/EXPERIMENT_REPORT.md`。

## 文档

- `STRUCTURAL_AMBIGUITY_NEXT_CANDIDATE_DESIGN_CN.md`：结构歧义 A/B/C 下一候选比较、数学语义、数据结构、排序键、风险、阶段和预注册验收；A1 离线纯函数与准备对象优化已完成单元测试，main A2 开发接线未通过性能门，A3/A4 未实现。
- `ALGORITHM_AND_IMPLEMENTATION.md`：算法原理、数学模型、接口、调参、仿真验证、主动降级不确定度信号和跨模块关系。
- `AIRSIM_INTEGRATION_PLAN.md`：AirSim/离线回放集成计划，说明时间戳、坐标和传感器桥接策略。
- `MODULE_PRINCIPLES_CN.md`：中文模块原理、已实现边界和当前证据解释。
- `EXPERIMENT_REPORT.md`：A1 纯函数单元验证、历史 clean 200v200 全栈复跑摘要和证据边界。

## 实验报告与图表

现有实验报告位于 `../reports/EXPERIMENT_REPORT.md`，并引用以下图表：

- `../reports/tracks_xy.png`
- `../reports/rmse_latency_ablation.png`

逐扫描性能基准另提供：

- `../reports/D1_NON_RADAR_INNOVATION_PERFORMANCE_BENCHMARK_CN.md`
- `../reports/d1_non_radar_innovation_performance_benchmark_20260722.json`
- `../reports/D1_SCAN_FUSION_PERFORMANCE_BENCHMARK_CN.md`
- `../reports/d1_scan_fusion_performance_benchmark_20260722.json`
- `../reports/D1_SCAN_ASSOCIATION_PERFORMANCE_BENCHMARK_CN.md`
- `../reports/d1_scan_association_performance_benchmark_20260722.json`
- `../reports/D1_LONG_DURATION_PERFORMANCE_BENCHMARK_CN.md`
- `../reports/d1_long_duration_performance_benchmark_20260722.json`
- `../reports/D1_COALESCED_RELEASE_PERFORMANCE_BENCHMARK_CN.md`
- `../reports/d1_coalesced_release_performance_benchmark_20260722.json`
- `../reports/D1_COALESCED_RELEASE_PROFILE_2P2_CN.md`
- `../reports/d1_coalesced_release_profile_2p2_20260722.json`
- `../reports/D1_CONSISTENCY_COUNTER_REFRESH_PERFORMANCE_BENCHMARK_CN.md`
- `../reports/d1_consistency_counter_refresh_performance_benchmark_20260722.json`
- `../reports/D1_CONSISTENCY_COUNTER_REFRESH_PROFILE_10S_CN.md`
- `../reports/d1_consistency_counter_refresh_profile_10s_20260722.json`
- `../reports/structural_ambiguity_centroid_replay_20260723/STRUCTURAL_AMBIGUITY_CENTROID_REPLAY_DIAGNOSTIC_CN.md`
- `../reports/structural_ambiguity_centroid_replay_20260723/structural_ambiguity_centroid_replay_diagnostic.json`

更新文档时不要移动或重命名上述图表，避免破坏报告中的相对链接。
