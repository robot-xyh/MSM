# Project Agent Registry

本目录定义 MSM 项目的稳定子智能体角色。后续 main agent 不应反复临时发长提示词新建同类智能体，而应按本目录的角色说明恢复/创建对应 subagent，并在任务结束后关闭。

## 调度原则

- main agent 负责全局编排、AirSim runtime、跨模块接口、总报告和最终验证。
- D1-D7 只负责各自模块，不跨模块改文件。
- 同时打开的 subagent 不超过 6 个；D1-D7 全参与时分两批执行。
- 不把一次会话中的 agent ID 写成长期事实；长期事实写入代码、模块文档、GAP 审计和本目录角色定义。
- 每次分派任务必须写清文件范围、验收命令、不得 revert 他人改动。
- 完成后关闭 subagent，释放并发槽位。

## 固定角色

| 角色 | 定义文件 | 责任边界 |
| --- | --- | --- |
| main | `main-agent.md` | 总体调度、AirSim 启停、episode 编排、日志汇总、跨模块合同 |
| D1 | `d1_sensor_fusion.md` | 雷达/声学/视觉观测融合，输出 GlobalTrack |
| D2 | `d2_data_association.md` | 多目标关联、ID continuity、ID switch 统计 |
| D3 | `d3_assignment_planner.md` | 中心化资源-目标分配、迟滞、版本化 AssignmentPlan |
| D4 | `d4_distributed_fallback.md` | 中心/二级/分布式降级，主动降级仲裁 |
| D5 | `d5_terminal_association.md` | 末端视觉配准、身份确认、跨视角一致性 |
| D6 | `d6_evaluation_metrics.md` | 系统指标、批量统计、报告图表 |
| D7 | `d7_proportional_guidance.md` | 中段 PN、末端视觉 PNG、导引合同门控 |

## 推荐并行组合

| 场景 | 推荐 subagent |
| --- | --- |
| AirSim 5v5 传感器/关联/分配联调 | D1, D2, D3, D6 |
| D4/D5 主动降级与跨视角专项 | D4, D5, D6 |
| D7 拦截闭环 | D3, D5, D7, D6 |
| 全链路方案更新 | D1, D2, D3, D4, D5, D7 后再 D6 |
| 文档总汇总 | main only |

## 标准分派模板

```text
你是 <Dx> 子智能体，工作目录 /home/linux/Documents/MSM。
只修改 <owned paths>。
任务目标：<goal>。
必须遵守：
- 不修改其他模块；
- 不 revert 他人改动；
- 2v2/5v5 只作为 baseline，算法按输入数组长度运行；
- 完成后更新对应 README/PLAN/GAP；
- 运行 <tests> 并汇报结果。
```
