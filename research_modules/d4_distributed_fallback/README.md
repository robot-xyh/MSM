# D4 分布式协同与降级接管

本模块用于离线科研仿真：当中心 C2 节点不可用时，评估区域二级节点接管、完全无中心协商、中心恢复合并等被动降级机制；当中心仍可用但 D1/D2/D3/D5 的不确定性或末端视觉不一致升高时，评估主动降级仲裁机制。模块只使用内存网络和粗粒度摘要，不包含真实通信、飞控、硬件、火控、毁伤、自动处置或授权绕过逻辑。

## 目录

- `PLAN.md`：模块研发计划、问题定义、状态机和仿真边界。
- `docs/ALGORITHM_AND_IMPLEMENTATION.md`：算法原理、数学模型、接口、调参建议和实施细节。
- `docs/README.md`：D4 文档索引。
- `d4_distributed_fallback/`：Python 包源码。
- `scripts/run_failover_simulation.py`：默认离线降级仿真入口。
- `tests/`：状态机、CBBA、接管和仿真测试。
- `reports/EXPERIMENT_REPORT.md`：实验报告与曲线。
- `reports/AIRSIM_INTEGRATION_PLAN.md`：AirSim 离线回放集成计划。

## 快速运行

```bash
PYTHONPATH=research_modules/d4_distributed_fallback \
python3 research_modules/d4_distributed_fallback/scripts/run_failover_simulation.py --drone-count 5
```

运行 D4 测试：

```bash
PYTHONPATH=research_modules/d4_distributed_fallback \
python3 -m pytest -q research_modules/d4_distributed_fallback/tests
```

## 当前能力

- `C2Health` 状态机：`normal -> degraded -> suspect -> failed`，中心恢复需双轨合并，不能只靠 heartbeat。
- 被动降级链路：中心 C2 失效 -> 高空系留二级侦察节点/地面备份 -> 完全无中心 CBBA。
- 主动降级仲裁：中心未失效但 D1/D2/D3/D5 风险升高时，输出继续、请求中心重分配、请求二级辅助、降到二级节点或分布式的离线决策。
- 二级节点建模：`NodeRole.SECONDARY_RECON`、`coordinator_only`、`coverage_cell`、`lease_epoch`、heartbeat、video cue freshness、link stale 和 priority。
- 二级节点生命周期摘要：`SecondaryNodeLifecycleSummary` 输出 `heartbeat`、`lease_epoch`、`coverage_cell`、`video_cue_freshness_s`、`link_stale` 和 `secondary_available`，供 D4 仲裁与 D6 日志审计。
- 增强通信摘要：`CommunicationSummary` 记录 `source_node_id`、`target_node_id`、`relay_node_id`、`link_type`、`sent_timestamp`、`received_timestamp`、`payload_kind`、`stale_after_s`，用于判断二级节点辅助链路是否新鲜。
- 主动降级迟滞/防抖：`ActiveDegradationConfig` 提供 `min_dwell_s`、`release_consecutive_consistent_frames`、`mismatch_frame_limit`、`risk_window_size` 和 `risk_window_threshold`；默认保持轻量单步规则，复用 arbiter 时可启用 dwell/release 行为。
- D5 cross-view 风险：`TerminalAssociationSummary.cross_view_risk_score` 和 `duplicate_terminal_lock` 会阻止“误判为一致锁定”。
- 指标输出：`ActiveDegradationDecision.to_metrics()` 输出 `d4_action`、`degradation_mode`、`target_node_id`、`risk_factors`、`terminal_consistent`、`failover_time`、`secondary_selected_rate`、`distributed_conflict_count`。
- D6 兼容事件：`D4ArbitrationAdapter` 输出 `EventRecord` kwargs，metadata 含 `degradation_mode`、`selected_coordinator`、`coverage_cell`、`trigger_reason`、`trigger_timestamp`、`decision_timestamp` 和 `review_label`，并保留 `d4_degradation_mode` 兼容 D4 原始枚举。
- CBBA 风格协商：用于二级节点不可用后的连续性分配基线。
- 与 D3/D5/D6 的接口：接收上一版分配摘要，向 D5 提供区域观测/cue 语义，向 D6 输出接管、共识和冲突指标。

## 主动降级入口

`ActiveDegradationArbiter` 接收 D1 定位不确定度、D2 关联风险、D3 分配有效性、D5 末端视觉关联摘要、`C2Health` 和二级节点健康状态，输出 `ActiveDegradationDecision`。典型策略：

- D5 与分配目标一致且风险低：`continue_center`。
- D1/D2 风险升高但 D5 仍一致：优先 `request_secondary_assist`。
- D3 分配 stale 或无效但 D5 仍一致：优先 `request_center_replan`。
- D5 多帧 `ambiguous/hold/reacquire` 或长期不一致：二级节点覆盖则 `degrade_to_secondary`，否则 `degrade_to_distributed`。
- D5 `friend_conflict=True`：强制 `hold_for_review`；`duplicate_terminal_lock=True` 不视为一致锁定。
- 若传入通信摘要，二级节点必须有未过期的 `secondary_relay`、`video_cue` 或 `c2_direct` 链路才可作为主动辅助/接管目标。
- 若二级节点 `heartbeat_timestamp_s` 超过 `heartbeat_stale_after_s`，即使视频链路摘要新鲜，也不会被选为二级接管目标。
- `--drone-count`/main runtime 的 N 只决定输入摘要数量；D4 按实际 `TrackSummary[]`、`ResourceSummary[]` 和二级节点列表长度运行，不在仲裁里固定 2v2 或 5v5。
- 2v2/5v5 AirSim ComputerVision 专项 case 只作为测试 baseline：`case_001_no_degradation` 期望 `continue_center`；`case_002_degrade_to_secondary` 期望二级节点优先；`case_003_degrade_to_distributed` 期望二级不可用/过期后才分布式。

## P1 状态

- 已完成：二级节点 lifecycle summary、主动降级 dwell/release/window 防抖配置、D6-compatible decision event metadata、对应单元测试。
- 保持不变：轻量 CBBA 仍是完全无中心保底基线；未接入 MIT CBBA、CA-CBBA、独立 auction 或 contract-net。
- 仍属 main/runtime 侧后续：真实 AirSim episode 中统一调用 `D4ArbitrationAdapter`、写入 D6 collector、按 episode 聚合主动/被动降级指标。
