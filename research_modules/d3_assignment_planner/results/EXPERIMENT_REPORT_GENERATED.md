# D3 分配仿真自动生成报告

边界：本报告仅用于离线抽象资源-目标分配评估，不包含真实火控、毁伤、硬件、自动执行或绕过授权逻辑。

## 1. 场景配置

- 目标数: 8
- 资源数: 8
- 仿真时长: 100.0 s
- 决策频率: 2.0 Hz
- 步数: 200

## 2. 主要结果

| 工况 | 重分配事件 | 总成本 | 平均成本 | 高威胁未分配比例 | 平均耗时 ms | p95 耗时 ms |
|---|---:|---:|---:|---:|---:|---:|
| no_hysteresis | 33 | 3261.348 | 16.307 | 0.0000 | 0.162 | 0.184 |
| hysteresis_delta_0.2 | 12 | 3380.071 | 16.900 | 0.0000 | 0.179 | 0.200 |

## 3. 结果解读

- 重分配次数最低的工况：`hysteresis_delta_0.2`。
- 总成本最低的工况：`no_hysteresis`。
- 迟滞策略预期会减少重分配事件；当旧计划仍可行时，保持旧计划可能带来少量成本上升。

## 4. 图表与曲线

![D3 分配成本与重分配曲线](cost_reassignment.png)

![D3 权重敏感性曲线](weight_sensitivity.png)

## 5. 权重敏感性表

| 代价项 | 权重倍率 | 重分配事件 | 平均成本 | 高威胁未分配比例 |
|---|---:|---:|---:|---:|
| window | 0.5 | 13 | 15.930 | 0.0000 |
| window | 1.0 | 12 | 16.900 | 0.0000 |
| window | 1.5 | 12 | 17.843 | 0.0000 |
| window | 2.0 | 12 | 18.776 | 0.0000 |
| covariance | 0.5 | 13 | 15.746 | 0.0000 |
| covariance | 1.0 | 12 | 16.900 | 0.0000 |
| covariance | 1.5 | 12 | 18.042 | 0.0000 |
| covariance | 2.0 | 11 | 19.150 | 0.0000 |
| threat | 0.5 | 13 | 14.885 | 0.0000 |
| threat | 1.0 | 12 | 16.900 | 0.0000 |
| threat | 1.5 | 11 | 18.698 | 0.0000 |
| threat | 2.0 | 11 | 20.289 | 0.0000 |
| resource_state | 0.5 | 13 | 15.903 | 0.0000 |
| resource_state | 1.0 | 12 | 16.900 | 0.0000 |
| resource_state | 1.5 | 12 | 17.800 | 0.0000 |
| resource_state | 2.0 | 12 | 18.699 | 0.0000 |
| fov | 0.5 | 10 | 15.904 | 0.0000 |
| fov | 1.0 | 12 | 16.900 | 0.0000 |
| fov | 1.5 | 14 | 17.696 | 0.0000 |
| fov | 2.0 | 13 | 18.232 | 0.0000 |
| conflict | 0.5 | 13 | 15.801 | 0.0000 |
| conflict | 1.0 | 12 | 16.900 | 0.0000 |
| conflict | 1.5 | 13 | 17.811 | 0.0000 |
| conflict | 2.0 | 11 | 18.593 | 0.0000 |

## 6. 生成文件

- timeseries: `/home/linux/Documents/MSM/research_modules/d3_assignment_planner/results/rolling_assignment_timeseries.csv`
- summary: `/home/linux/Documents/MSM/research_modules/d3_assignment_planner/results/summary.json`
- sensitivity_csv: `/home/linux/Documents/MSM/research_modules/d3_assignment_planner/results/weight_sensitivity.csv`
- cost_plot: `/home/linux/Documents/MSM/research_modules/d3_assignment_planner/results/cost_reassignment.png`
- sensitivity_plot: `/home/linux/Documents/MSM/research_modules/d3_assignment_planner/results/weight_sensitivity.png`
