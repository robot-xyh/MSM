# D1 文档索引

本目录保存 D1 多传感器融合与目标配准模块的说明文档。

## 当前证据索引（2026-07-22）

最新正式治理证据来自 clean 提交 `e4d66db02a0b8f1b867a0e81b4a73de84588426b`。
20/50/100/200 各 5 seed，共 20/20 formal episode；每例 136 帧/33.75 s，D1 重排 12、拒绝/
过旧/溢出 0、峰值缓冲 3、尾部缓冲 0、在线 truth 使用 0。200 规模峰值内存均值约
40.91 MB、最大 40,926,870 B。输入和 60 个引用制品的 SHA-256 均通过复核。

单次 200v200 三维质点全栈 smoke 仍为 development seed 42000/2.2 s，D1
处理 86 个扫描和 2,051 条观测，重排 10、拒绝 0、峰值 33 帧/623 条观测；fusion 累计
35.115 s，扫描输入累计 2.682 s，全栈墙钟 60.210 s。正式治理结果和该 development 全栈结果
都不是 AirSim、融合精度或完整 200v200 拦截验收。

最新 D1-owned 合同增量仍是版本化扫描输入整理。15 项确定性专项覆盖水位线、整帧 too-late、
duplicate/replay/conflict、有限缓冲、同时间多源、动态 1/7/200 点输入及嵌套只读视觉元数据
快照；既有权威 D1 全量回归为 `151 passed`。clean 治理复跑已关闭，但逐小扫描全后验处理造成
的融合吞吐仍是 P1，clean 全栈多 seed 和精度标定仍开放。

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

## 实验报告与图表

现有实验报告位于 `../reports/EXPERIMENT_REPORT.md`，并引用以下图表：

- `../reports/tracks_xy.png`
- `../reports/rmse_latency_ablation.png`

更新文档时不要移动或重命名上述图表，避免破坏报告中的相对链接。
