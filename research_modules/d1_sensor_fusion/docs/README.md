# D1 文档索引

本目录保存 D1 多传感器融合与目标配准模块的说明文档。

## 当前证据索引（2026-07-15）

最新权威增量为真实 AirSim M5N2 baseline/candidate 各 10 case，共 20 case。在线 identity/state
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
