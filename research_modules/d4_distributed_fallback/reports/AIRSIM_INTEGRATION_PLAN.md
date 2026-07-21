# D4 AirSim Episode 集成计划

## 1. 范围与边界

本计划覆盖 AirSim episode 时间轴上的 D4 通信摘要输入、故障注入、顺序接管、原子 ACK、恢复审计和 D6 指标输出。D4 不直接启动 AirSim、不发布飞控命令、不处理视频帧，也不实现真实 socket、mesh、RF、硬件驱动、自动处置或授权绕过。

AirSim episode clock 只提供统一的仿真时间基准。已通过的 delay/loss/partition case 是时间轴上的可复现故障注入，不代表真实吞吐带宽、无线传播、节点时钟漂移、操作系统排队、乱序、重传或硬件链路已经验证。

## 2. 2026-07-21 当前状态

最新 M5N2 baseline/candidate 各 10 seeds 已完成，共 20/20 case。该批中心 owner 始终有效且 `active degradation=0`，是中心继续执行负对照：coalition completion `0/20`、第二 primary 进入 5 m `0/20`，20 个第二 primary 均为 `collision_stop`。由于 collision object 未写盘，runtime 后续必须补充碰撞对象/来源字段，D4 不能把该终态自动转换成主动降级事件。D4 main-bus 阶段 mean/P95/max 约 `5.59/6.70/94.10 ms`。`png_ttc_2v2_seed001` 排除在 M5N2 聚合之外，dropout case 完成数为 0。

该证据没有运行二级或完全分布式接管，故真实 secondary/distributed 多 seed 仍为 P1。后续 AirSim 集成必须构造与中心负对照配对的故障 case，并让 D4 从 D1/D2/D3/D5 摘要得出动作，不得由 `collision_stop` 标签直接注入动作。

2026-07-21，D4 的 main-independent 区域建议运行时确认验证器升级为 v2。AirSim 或质点 runtime 启用区域建议时，main 必须保存 `modules.d4.region_resource_consumption`、当前 `modules.d3.assignment_plan`、同周期 `modules.d7.guidance_commands` 和 `runtime.assignment_plan_ack`。执行签名变化时仍必须发布严格更新的新计划并携带完整 owner/epoch/lease。同 plan ID/version 的评估刷新还必须保存 advisory 对应的前序 D3 plan envelope；D4 只在 refresh-only flags、时间、绑定集合、coalition/version、source sequence 与 payload SHA 全部一致时输出 `evaluation_refresh_applied`。5v5 seed 41 质点集成与篡改专项 5/5，运行时专项合计 33/33，D4 全量 430/430。该结果不是 AirSim 证据；冻结历史 episode 仍不能回填，验证器也不改变 AirSim 控制、D3 计划或 D7 gate。

D4 当前具备两层 AirSim episode 接口、一个已接入 main 质点模块栈的 scalable3d 区域接口，以及一个默认 disabled/shadow 的区域资源建议接口：

- `d4_airsim_episode_communication_v1`：main 按严格递增的 episode timestamp 逐 tick 输入 heartbeat、消息 delay/drop、ACK、partition、digest、恢复授权，以及按 secondary node keyed 的 `SecondaryReadinessEvidence`。readiness DTO 必须显式携带 current time、lease epoch/expiry、heartbeat/cue/communication 时间、gimbal、coverage/full-view 和 sustained window；heartbeat 单独存在不得 propose secondary owner。
- `d4_p1_episode_fault_validation_matrix_v1`：覆盖 normal、center failure、center+secondary failure、missing ACK、stale epoch、expired lease 和 partition 的规范合同验收。
- `d4-regional-failover-v1`：D4-owned truth-free payload，包含动态 scenario/node/region/task metadata、逐区域 ownership、D1/D2/D3/D5 risk、机动高空二级 coverage/readiness、最早 lease、跨区域 capacity fallback assignment 和全层 coalition commit。main-owned scalable 3D 质点模块栈已消费该接口并发布 secondary/distributed D3 plan；AirSim 区域 episode 仍未验证。
- `d4-region-resource-snapshot-v1` / `d4-region-resource-recommendation-v1` / `d4-region-resource-advisory-v1`：只传区域聚合图与配额/邻区转移/备用/侦察/hold-replan 建议，不传 actor/truth/object identity 或具体 assignment。advisory 在确定性投影后增加内容 ID、严格有效期、逐区域/transfer source generation、资源与 edge proof；main 下一轮消费时还必须对 current snapshot/formal verdict 重验，并拒绝 replay。它不能替代 D4 仲裁、D3 plan 或 D7 gate。

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
| D4 模块回归 | 397/397 passed（2026-07-21，含全样本准入专项 10/10） |
| 区域资源建议/消费合同专项 | 49/49 passed |
| 区域学习 episode 数据合同 | 13/13 passed |
| scalable 3D 质点接口定向测试 | 8/8 passed |

30% loss 场景中，7 个缺 ACK case 保守阻断，只有 3 个完整 ACK case 执行。该结果关闭 episode-clock 多 seed 安全矩阵缺口，不关闭真实网络 P1。

2026-07-15 的 280/280 回归关闭了公开 secondary plan helper 的 readiness/source/epoch/time 缺失门控，更早 278/278 不再作为全部入口证据。区域合同阶段为 303/303，建议管线阶段 335/335，next-cycle 消费合同阶段 350/350，课程阶段为 387/387，全样本准入阶段为 397/397；2026-07-21 增加运行时确认专项后，当前 D4 全量为 430/430。全样本审计和确认接口不改变任何 AirSim 控制、场景或在线门控，也不提供新的 AirSim、真实网络或硬件证据。main 既有质点模块栈定向 8/8 覆盖单一二级、多二级区域 owner、连续失效后的 distributed D3 plan，以及 D7 owner/epoch/lease/commit/fault fence。正式 development checkpoint 强制 shadow-only；规则教师 target 和 projected recommendation 都不能解释为运行时 ACK，冻结数据中的真实 ACK/outcome/reward 仍 unavailable，PPO、assist 和 authority 继续关闭。

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

- episode id、严格递增且不可缺失的 timestamp 和 seed；
- center/secondary heartbeat 与 C2 health evidence；
- message delay/drop、partition 和 link freshness；
- current plan id/version、coalition id/version 和 owner；
- required/acked/missing members、epoch、不可缺失的 lease expiry；
- D1/D2/D3/D5 风险摘要和 D5 terminal evidence applicability；
- center/fallback digest 与 recovery authorization。

所有输入按实际资源和任务列表长度运行，不写死 2v2 或 5v5。

scalable3d 质点接线现已由 main 按在线时钟提供 scenario/region definition、D1/D2/D3/D5 evidence、逐区域 secondary readiness 和 member ACK，并消费 D4 ownership 生成 D3 secondary/distributed plan。D4 仍不从真值位置推导 region 或 ID，也不生成 D3 系统计划；后续缺口是长时 200v200、多 seed、D6 区域趋势和 AirSim 区域 episode，而不是接口“未接线”。

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

1. 在相同 M5N2 几何和 seeds 下增加中心失效、中心与二级连续失效两组 paired case，验证 secondary/distributed owner、版本、epoch、lease、完整 ACK 和物理连续性。
2. 增加可审计主动风险 case：D1 协方差/陈旧、D2 关联冲突、D3 stale/infeasible、D5 current binding/身份/跨视角不一致；单纯物理未命中或 `collision_stop` 不得直接触发降级。
3. 在控制日志中持久化 collision object/source lineage，用于区分成员碰撞、环境碰撞和 AirSim 状态异常；该字段只供诊断和 D6 评分，不绕过 D4 仲裁。
4. 保持已完成的 scalable3d versioned envelope 接线回归，扩展 5/20/50/100/200 长时多 seed episode，记录逐区域 owner、generation、lease、commit、fault fence、stage timing、churn 和分区恢复；该工作属于 main-owned 集成，不由 D4 修改。
5. 区域资源学习建议先在 shadow 中运行至少 20 个未见 seed，paired 报告 backlog、transfer、churn、communication、fail-closed、安全违规和 P50/P95 latency。未满足门槛前不进入 assist；即使满足也不绕过正式 D4/D3/D7 gate。
6. main 如在 AirSim planning loop 消费区域资源建议，只接受 `d4-region-resource-advisory-v1`，在每个 D3 planning boundary 使用 current snapshot/formal verdict 重验，并跨进程持久化 consumed advisory ID。不得直接消费 raw/non-projected recommendation；D4 不修改 main/D3-owned 实现。
7. main 的逐 episode region-learning writer 改为调用 D4 公开 API：episode 开始固化 `RegionLearningEpisodeSource`（scenario/version/scale、seed、episode ID、Git commit/dirty、config SHA），逐帧构造带显式 target/reward availability 的 `RegionLearningFrame`，episode 完成后 stage，批次完成后 finalize。旧 JSONL 只有 frame_index/timestamp/snapshot/recommendation，不满足正式训练合同；main 不应解析 D4 私有 artifact。
8. 动作覆盖课程保持离线独立。main 不把课程 frame 注入 AirSim episode bus，也不把规则 teacher 当作实际 D4 运行结果。clean worktree 重生已经完成；后续训练配置仍须单独记录正式 episode 与课程样本比例，缺真实 outcome 时不得启动 PPO。

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
python3 -m py_compile \
  research_modules/d4_distributed_fallback/d4_distributed_fallback/region_resource.py \
  research_modules/d4_distributed_fallback/d4_distributed_fallback/region_resource_learning.py \
  research_modules/d4_distributed_fallback/d4_distributed_fallback/region_resource_curriculum.py \
  research_modules/d4_distributed_fallback/d4_distributed_fallback/region_resource_curriculum_cli.py
PYTHONPATH=research_modules/d4_distributed_fallback \
python3 -m pytest -q research_modules/d4_distributed_fallback/tests
```

本轮新增 D4 独立动作覆盖课程、canonical 绑定、审计、测试和文档，不启动 AirSim，也不修改 main/runtime、scalable_3d_simulation、D3、D5、D6 或 D7。既有 main-owned 质点集成 8/8 仅作为此前接口事实保留，本轮未把 D4 单元测试外推为新的 AirSim 或多 seed 证据。
