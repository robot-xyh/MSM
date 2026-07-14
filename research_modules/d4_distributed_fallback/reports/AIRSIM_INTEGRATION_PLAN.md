# D4 AirSim Episode 集成计划

## 1. 范围与边界

本计划覆盖 AirSim episode 时间轴上的 D4 通信摘要输入、故障注入、顺序接管、原子 ACK、恢复审计和 D6 指标输出。D4 不直接启动 AirSim、不发布飞控命令、不处理视频帧，也不实现真实 socket、mesh、RF、硬件驱动、自动处置或授权绕过。

AirSim episode clock 只提供统一的仿真时间基准。已通过的 delay/loss/partition case 是时间轴上的可复现故障注入，不代表真实吞吐带宽、无线传播、节点时钟漂移、操作系统排队、乱序、重传或硬件链路已经验证。

## 2. 2026-07-13 当前状态

D4 当前具备两层 episode 接口：

- `d4_airsim_episode_communication_v1`：main 按严格递增的 episode timestamp 逐 tick 输入 heartbeat、消息 delay/drop、ACK、partition、digest 和恢复授权，D4 输出 owner/version、epoch、lease、commit、transition 和 fail-closed 状态。
- `d4_p1_episode_fault_validation_matrix_v1`：覆盖 normal、center failure、center+secondary failure、missing ACK、stale epoch、expired lease 和 partition 的规范合同验收。

main/runtime 已按 AirSim episode clock 对以下六类场景各运行 10 seeds，共 60 case：

1. `normal`
2. `center_failure`
3. `center_secondary_failure`
4. `delay_0_5s`
5. `loss_30pct`
6. `partition_recovery`

验收结果：

| 指标 | 结果 |
|---|---:|
| safety outcome | 60/60 |
| false degradation | 0 |
| duplicate owner | 0 |
| split-brain prevention failure | 0 |
| D4 模块回归 | 198 passed |

30% loss 场景中，7 个缺 ACK case 保守阻断，只有 3 个完整 ACK case 执行。该结果关闭 episode-clock 多 seed 安全矩阵缺口，不关闭真实网络 P1。

## 3. 状态与所有权规则

中心健康时，D4 不因 D5 视觉不一致直接转移 plan owner：

```text
center healthy
  -> 普通或持续视觉软不一致: request_secondary_assist
  -> 明确硬失配/计划不可继续: request_center_replan
  -> owner 仍为 center，由 main/D3 发布新版本计划

center failed
  -> secondary readiness/plan/ACK/epoch/lease 全部有效: secondary takeover

center failed + secondary failed/unavailable
  -> distributed negotiation
  -> required-member ACK、current epoch、valid lease 缺一即 fail closed
```

`request_secondary_assist` 只请求二级观测 cue，不是接管候选的自动批准。`request_center_replan` 只请求 D3/main 生成新版本计划，D4 不直接生成系统级 `AssignmentPlan`，也不改写 `global_track_id`。

## 4. 数据流

```text
AirSim/main episode clock and link evidence
  -> AirSimEpisodeCommunicationAdapter
  -> C2Health + active/passive degradation arbitration
  -> secondary or distributed coalition commit gate
  -> owner/version + ACK/epoch/lease + transition records
  -> main runtime bus
  -> D6 metrics and Chinese report
```

离线 AirSim export 仍可映射为 `TrackSummary`、`ResourceSummary` 和链路摘要，但高分辨率坐标、相机几何和 bbox 注册属于 D1/D5/main，不进入 D4 核心。

## 5. Episode 输入

main 每个 tick 至少提供：

- episode id、严格递增 timestamp 和 seed；
- center/secondary heartbeat 与 C2 health evidence；
- message delay/drop、partition 和 link freshness；
- current plan id/version、coalition id/version 和 owner；
- required/acked/missing members、epoch、lease expiry；
- D1/D2/D3/D5 风险摘要和 D5 terminal evidence applicability；
- center/fallback digest 与 recovery authorization。

所有输入按实际资源和任务列表长度运行，不写死 2v2 或 5v5。

## 6. Episode 输出

D4 每个 tick 输出：

- `continue_center | request_secondary_assist | request_center_replan` 等中心健康动作；
- center failed 后的 secondary/distributed 状态；
- owner、plan/coalition version、epoch、lease validity；
- required/acked/missing members 和 commit/fail-closed reason；
- false degradation、duplicate owner、split-brain prevention 和 recovery audit 字段；
- D6 可消费的 transition/event metadata。

## 7. 已完成验收流程

1. main 创建或 reset episode，并固定 seed。
2. 按 episode timestamp 注入 normal、delay、loss、中心失效、中心与二级连续失效或 partition/recovery 证据。
3. D4 adapter 逐 tick 更新健康、owner、version、epoch、lease 和 ACK 状态。
4. 缺 ACK、旧 epoch、过期 lease 或分区 generation 不完整时阻断执行。
5. 恢复后使用新 generation 全量 re-ACK；中心恢复只进入双轨审计，不立即夺权。
6. main 汇总 10 seeds，D6 统计 safety outcome、误降级、重复 owner 和脑裂防护。

当前六类 60-case 流程已完成，不再把“main 仍需注入同一 episode-clock 证据”列为缺口。

## 8. P1 剩余工作

以下项目仍为 P1，不能由当前 episode-clock 结果替代：

- 在可配置吞吐带宽和队列容量下验证消息拥塞与优先级；
- 注入 center、secondary 和 peer 节点时钟漂移与时间同步误差；
- 建模操作系统/socket 排队、网络抖动、乱序、重传和突发丢包；
- 验证 secondary-interceptor 和 peer-to-peer 实际链路分区；
- 在长时间运行中统计 false/missed degradation、恢复时间和 owner 抖动；
- 有条件时使用网络仿真器或硬件链路验证 RF/mesh 行为。

这些实验必须继续保持中心健康时不转 owner，以及 secondary/distributed 的 ACK、epoch、lease fail-closed 规则。

## 9. 非目标

- 不发布 AirSim vehicle control 命令。
- 不在 D4 内实现在线 socket bridge、视频传输或无线协议栈。
- 不把 episode clock delay/loss 结果表述为真实 RF 验证。
- 不由 D4 生成新的中心化系统级 `AssignmentPlan`。
- 不绕过 D3 版本、D5 身份/视觉门控或 D7 控制许可。

## 10. 验收命令

```bash
git diff --check -- \
  subagent_reviews/D4_DISTRIBUTED_FALLBACK_REVIEW_AND_PLAN.md \
  research_modules/d4_distributed_fallback/reports/AIRSIM_INTEGRATION_PLAN.md
```

本轮只同步文档，不运行 AirSim 或修改 D4 代码。
