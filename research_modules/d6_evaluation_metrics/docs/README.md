# D6 文档索引

本目录保存 D6 的详细设计和实现状态文档。D6 的长期边界是离线评估：只消费日志，不参与 D1-D7 控制链路。

| 文档 | 位置 | 说明 |
|---|---|---|
| 模块 README | `../README.md` | 当前能力、规模归一化、AirSim/D4/D5/D7 离线入口、测试命令和 API 示例 |
| 模块计划 | `../PLAN.md` | 已实现、部分实现、未实现、main runtime 接线缺口、P1/P2 下一步 |
| AirSim 离线集成计划 | `../AIRSIM_INTEGRATION_PLAN.md` | Blocks JSONL、D4/D5/D7 AirSim 产物回灌、PNG 策略和未实现 replay 项 |
| 算法原理与当前实现 | `ALGORITHM_AND_IMPLEMENTATION.md` | 指标公式、数据模型、`EpisodeMetrics` 字段、D4/D5/D7 gate、开源 benchmark 缺口 |
| 示例实验报告 | `../EXPERIMENT_REPORT.md` | 批量示例报告和图表引用；不是代码或在线控制输出 |

核心规则：

- `id_switch_count` 是 D2/D6 强制显式指标。
- 指标按实际 `drone_count/resource_count/target_count/camera_count` 分组和归一化，不从 `2v2/5v5` 场景名推断。
- D7 guidance records 通过 `guidance_records.csv` / `guidance_summaries.json` loader 转为 `EventRecord` metadata；D6 只做离线 gate/intercept 统计，不提供在线导引控制通道。
- 2026-07-07 起，main/orchestrator 已把 D7 真实执行指标合并进正式 `main_episode_bus_metrics.json`，并把执行前合同检查保留为 `main_episode_bus_contract_metrics.json`；D6 仍只消费这些写盘产物。
- PNG 截图不是默认指标输入；bbox、相机参数、timestamp、ID 和 gate metadata 才是指标主线。
- Stone Soup、OSPA/GOSPA、TrackEval/py-motmetrics、HOTA/IDF1、AirSim 原生 recording replay、live AirSim replay/API 和 SCRIMMAGE bridge 当前都是未实现的可选后续项或禁止在线控制项。
