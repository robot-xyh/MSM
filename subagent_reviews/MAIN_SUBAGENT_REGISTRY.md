# Main Subagent Registry

## 目的

本文件记录 MSM 项目的子智能体调度规则。稳定角色定义已经迁移到 `agents/`，本文件不再保存某次会话中的 agent ID。

## 当前结论

- main agent 是主线程，不计入 subagent 槽位。
- 可同时打开的 subagent 槽位上限为 6。
- D1-D7 共 7 个模块角色，因此不能长期全部打开。
- 已完成但未关闭的 subagent 仍会占用槽位。
- 后续应通过 `agents/*.md` 的稳定角色定义来创建/恢复 subagent，而不是复制长提示词或依赖旧 ID。

## 稳定角色

| 角色 | 定义文件 | 模块职责 |
| --- | --- | --- |
| main | `agents/main-agent.md` | 全局调度、AirSim runtime、跨模块接口、总报告 |
| D1 | `agents/d1_sensor_fusion.md` | 多传感器融合与目标配准 |
| D2 | `agents/d2_data_association.md` | 多目标跟踪与数据关联 |
| D3 | `agents/d3_assignment_planner.md` | 集中式资源-目标分配 |
| D4 | `agents/d4_distributed_fallback.md` | 分布式协同与降级接管 |
| D5 | `agents/d5_terminal_association.md` | 末端视觉配准与身份认证 |
| D6 | `agents/d6_evaluation_metrics.md` | 系统级评估指标 |
| D7 | `agents/d7_proportional_guidance.md` | 比例导引与末端视觉 PNG |

## 调度规则

1. 不再长期保持 D1-D7 全部打开。
2. 子智能体完成任务后立即关闭。
3. 需要 D1-D7 全参与时分两批执行。
4. main 负责总体接口、AirSim 编排、日志和报告，不替代模块所有权。
5. 共享上下文以代码、`agents/`、模块 README/PLAN/GAP 为准。

## 推荐并行组合

| 场景 | 推荐打开的 subagent | 原因 |
| --- | --- | --- |
| AirSim 5v5 传感器/关联/分配联调 | D1, D2, D3, D6 | D1-D3 是主链路，D6 负责评估 |
| D4/D5 降级与跨视角专项 | D4, D5, D6 | D4/D5 是专项主体，D6 做指标 |
| D7 拦截闭环 | D3, D5, D7, D6 | D3 给分配，D5 给锁定，D7 控制，D6 评估 |
| 全链路方案更新 | D1, D2, D3, D4, D5, D7，然后 D6 | 先让模块给输出，最后 D6 统计评估 |
| 文档总汇总 | main only | 直接读取模块文档，不需要打开所有 subagent |

## 标准恢复/创建动作

1. 读取对应 `agents/<role>.md`。
2. 发送只包含当前任务增量的短指令。
3. 限定写入范围。
4. 要求更新对应 README/PLAN/GAP 或测试。
5. main 检查结果。
6. 关闭 subagent。
