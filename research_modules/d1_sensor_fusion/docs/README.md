# D1 文档索引

本目录保存 D1 多传感器融合与目标配准模块的说明文档。

## 当前证据索引（2026-07-22）

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

- `ALGORITHM_AND_IMPLEMENTATION.md`：算法原理、数学模型、接口、调参、仿真验证、主动降级不确定度信号和跨模块关系。
- `AIRSIM_INTEGRATION_PLAN.md`：AirSim/离线回放集成计划，说明时间戳、坐标和传感器桥接策略。
- `MODULE_PRINCIPLES_CN.md`：中文模块原理、已实现边界和当前证据解释。
- `EXPERIMENT_REPORT.md`：2026-07-22 clean 200v200 全栈接线复跑摘要和证据边界。

## 实验报告与图表

现有实验报告位于 `../reports/EXPERIMENT_REPORT.md`，并引用以下图表：

- `../reports/tracks_xy.png`
- `../reports/rmse_latency_ablation.png`

逐扫描性能基准另提供：

- `../reports/D1_SCAN_FUSION_PERFORMANCE_BENCHMARK_CN.md`
- `../reports/d1_scan_fusion_performance_benchmark_20260722.json`
- `../reports/D1_SCAN_ASSOCIATION_PERFORMANCE_BENCHMARK_CN.md`
- `../reports/d1_scan_association_performance_benchmark_20260722.json`
- `../reports/D1_LONG_DURATION_PERFORMANCE_BENCHMARK_CN.md`
- `../reports/d1_long_duration_performance_benchmark_20260722.json`

更新文档时不要移动或重命名上述图表，避免破坏报告中的相对链接。
