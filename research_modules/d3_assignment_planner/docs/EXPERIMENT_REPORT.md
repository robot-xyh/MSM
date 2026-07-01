# D3 集中式资源-目标分配实验报告

## 1. 实验边界

本报告仅覆盖离线抽象资源-目标候选分配。规划器输出是候选 `AssignmentPlan`，必须经过人工或外部授权层确认。模块不包含真实火控参数、毁伤逻辑、飞控接口、硬件驱动、自动处置或绕过人工授权的流程。

## 2. 实验目的

D3 研究多目标、多资源条件下的滚动分配稳定性。重点验证：

- Hungarian 是否能作为 5v5 及更大规模的一对一分配基线。
- 迟滞逻辑是否能减少频繁重分配。
- 代价函数是否显式包含接近窗口、航迹不确定性、威胁权重、资源状态、视场难度和冲突风险。
- 分配计划是否版本化，并保持 `human_authorization_state="required"`。

完整算法原理、接口契约和调参建议见 [ALGORITHM_AND_IMPLEMENTATION.md](ALGORITHM_AND_IMPLEMENTATION.md)。

## 3. 分配模型

分配变量：

```text
x_ij in {0, 1}
```

总代价：

```text
J = sum_i sum_j x_ij C_ij
```

重分配条件：

```text
J_new < (1 - delta) * J_old
and dwell_time > min_dwell
and change_count <= max_changes_per_window
```

## 4. 场景配置

| 项目 | 设置 |
|---|---:|
| 随机种子 | 20260630 |
| 目标数 | 8 |
| 资源数 | 8 |
| 仿真时长 | 100.0 s |
| 决策频率 | 2.0 Hz |
| 步数 | 200 |
| 迟滞参数 | `delta=0.2`, `min_dwell=2.0` |

运行命令：

```bash
cd research_modules/d3_assignment_planner
python3 simulations/run_rolling_assignment.py
```

## 5. 结果表

| 工况 | 重分配事件 | 变更边数 | 总成本 | 平均成本 | 高威胁未分配比例 | 平均耗时 ms |
|---|---:|---:|---:|---:|---:|---:|
| 无迟滞 | 33 | 96 | 3261.348 | 16.307 | 0.0000 | 0.162 |
| 迟滞 `delta=0.2` | 12 | 46 | 3380.071 | 16.900 | 0.0000 | 0.171 |

## 6. 图表与曲线

### 6.1 分配成本与重分配曲线

![D3 分配成本与重分配曲线](../results/cost_reassignment.png)

该图展示无迟滞与迟滞策略下的滚动成本和重分配事件。迟滞策略牺牲少量成本，换取更少的任务抖动。

### 6.2 权重敏感性分析

![D3 权重敏感性曲线](../results/weight_sensitivity.png)

该图用于判断代价项权重变化对平均成本、重分配次数和高威胁未分配比例的影响。后续扩展到不同目标密度时，应优先扫描 `threat`、`covariance` 和 `conflict` 权重。

## 7. 结论

Hungarian 仍是中心节点存在时的默认主线。迟滞逻辑显著减少重分配事件，但会带来可解释的成本上升。当前版本已加入 stale plan 拒绝、版本递增、强制人工授权状态、换配上限和 `reassignment_switch_penalty` 分项，适合作为 D4 降级协商和 D5 终端锁定的候选计划来源。
