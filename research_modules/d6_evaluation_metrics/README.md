# D6 Evaluation Metrics

D6 是 MSM 的离线评估与报告模块。它只消费已经写盘的日志、CSV、JSON/JSONL 和仿真真值，输出 `EpisodeMetrics`、CSV、Markdown 报告和 PNG 图表；不参与 D1-D7 的实时控制链路，不生成任务、分配、导引、授权、火控、毁伤或自动处置动作。

## 当前能力

已实现的核心数据模型：

- `EpisodeMetrics`：单 episode 标量指标对象，包含 `metric_scope` 和规模字段 `drone_count/resource_count/target_count/camera_count`。
- `TrackRecord`：探测和跟踪记录，保留 `global_track_id`、`truth_id`、位置、真值位置、协方差摘要和来源。
- `AssignmentRecord`：分配快照，保留 `plan_id`、`version`、资源、目标、授权状态和评估侧真值标签。
- `EventRecord`：通用事件记录，用于降级、安全、D5/D7 gate、通信元数据等。
- `LinkRecord`：跨节点通信记录，支持 latency/drop/out-of-order/stale/video metadata/bbox delivery。
- `TerminalRecord`：末端配准记录，支持局部视觉 ID、锁定、歧义、友方 overlap hold 和正确性标签。

已实现的指标族：

- 探测：`detection_probability`、`false_alarm_rate`、`missed_detection_rate`。
- 跟踪：`track_rmse`、`track_continuity`、强制显式保留的 `id_switch_count`。
- 分配：`duplicate_assignment_count`、`unassigned_high_threat_count`。
- 降级：`failover_time`、`consensus_rounds`、`degraded_completion_rate`、`active_degradation_count`、`active_degradation_precision`、`unnecessary_active_degradation_count`、`passive_failover_count`、`secondary_node_takeover_count`、`secondary_reassignment_count`、`d4_reassign_pending_count`、`distributed_fallback_count`、`failover_active_window_delta_s`。
- 末端：`terminal_association_accuracy`、`terminal_id_switch_count`、`ambiguous_fov_event_count`、`friend_overlap_hold_count`、`time_to_terminal_lock`、`terminal_lock_count`、`multi_view_consensus_rate`、`cross_view_conflict_count`、`duplicate_terminal_lock_count`。
- 通信：`cross_node_latency_ms`、`message_drop_rate`、`out_of_order_count`、`stale_track_update_count`、`video_metadata_delivery_rate`、`bbox_delivery_rate`、`consensus_latency_s`。
- D7 gate 与拦截统计：`camera_quality_gate_pass_rate`、`los_quality_gate_pass_rate`、`maneuver_margin_gate_pass_rate`、`terminal_switch_allowed_rate`、`visual_png_switch_count`、`terminal_takeover_rate`、`terminal_switch_reject_count`、`mode_switch_count`、`terminal_contract_reject_count`、`intercept_success_count`、`collision_intercept_count`、`range_intercept_count`、`time_to_intercept_s`、`min_range_m`、`gate_reject_count`。
- 安全：`constraint_violation_count`、`human_override_count`。

D2/D6 的硬规则仍然保留：`id_switch_count` 必须显式输出，不能被综合准确率隐藏。

## 规模归一化

D6 按实际 `drone_count/resource_count/target_count/camera_count` 归一化和分组。规模优先来自 `truth_summary` 或 Blocks replay 的资源、目标和相机字段；缺失时才从已记录的资源、目标、终端和相机元数据推断。`2v2`、`5v5` 只作为 baseline 场景名，不能用于推断算法规模或报告分母。报告会按 `metric_scope`、`seed`、`scenario_group` 和实际规模字段分组，区分 execution metrics 与 contract metrics。

## AirSim 与 Runtime 输入

D6 已有离线 loader，但不直接连接 AirSim：

- `load_blocks_replay_jsonl()` 读取 main runtime 写出的 `blocks_frames.jsonl` 和可选 `blocks_sensor_observations.jsonl`。
- `load_d4_active_degradation_decisions()` 读取 D4 主动降级 CSV，并离线消费 `review_label`、trigger/decision timestamp、selected coordinator、coverage cell 和 pre/post window 字段。
- `load_d7_intercept_outputs()` / `load_d7_guidance_timeseries()` 读取 D7 `control_commands.csv`、`intercept_summary.json`、`guidance_records.csv`、`guidance_summaries.json`。
- `load_episode_log_jsonl()` 读取 D6 标准化 dry-run JSONL。

这些 loader 都是 file/offline-only。D6 已能消费 D4/D5/D7 写盘产物；D6 不拥有 live bus 订阅、AirSim 原生 recording 通用解析器或自动跨目录 episode 聚合调度。

截至 2026-07-07，main/orchestrator 已在真实 D7 AirSim 执行后把 `control_commands.csv` 与 `intercept_summary.json` 中的执行结果合并进正式 `main_episode_bus_metrics.json`，同时把执行前的合同检查口径保留为 `main_episode_bus_contract_metrics.json`。因此正式 episode 指标中的 `intercept_success_count`、`collision_intercept_count`、`range_intercept_count`、`terminal_contract_reject_count`、`guidance_law_counts` 等字段以执行后结果为准；raw contract metrics 只用于诊断 D3/D4/D5/D7 gate 合同。D6 通过 `metric_scope=execution/contract` 保留这两个口径，并在 CSV/Markdown 中分组展示。D6 仍只读取这些文件或由 main 写出的 metrics，不参与控制或重规划。

## PNG 策略

PNG 截图不是 D6 计算指标的必需输入。D6 可用 bbox、相机内外参、timestamp、资源/相机 ID、`assigned_global_track_id`、object label、truth/validation label 和 D7 gate 结果计算多视角、末端和 visual PNG switch 指标。`--save-images` 只应在调试视角时启用；指标主线依赖 metadata。

## 文档

- 模块计划：`PLAN.md`
- AirSim 离线集成计划：`AIRSIM_INTEGRATION_PLAN.md`
- 详细算法与实施说明：`docs/ALGORITHM_AND_IMPLEMENTATION.md`
- 文档索引：`docs/README.md`
- 示例实验报告：`EXPERIMENT_REPORT.md`

## 运行测试

从仓库根目录运行：

```bash
pytest -q research_modules/d6_evaluation_metrics/tests
```

## 运行 100 Seed 示例

```bash
python3 research_modules/d6_evaluation_metrics/scripts/run_batch_example.py --seeds 100
```

默认输出：

```text
research_modules/d6_evaluation_metrics/outputs/example_batch/
  episode_metrics.csv
  summary_metrics.csv
  batch_report.md
  logs/*.jsonl
  plots/*.png
```

## 核心 API 示例

```python
from d6_evaluation_metrics import (
    AssignmentRecord,
    EventRecord,
    LinkRecord,
    MetricsCollector,
    ReportGenerator,
    TerminalRecord,
    TrackRecord,
)

collector = MetricsCollector()
collector.add_track(
    TrackRecord(
        timestamp=0.0,
        global_track_id="G0",
        truth_id="T0",
        position=(0.0, 0.0, -10.0),
        truth_position=(0.0, 0.0, -10.0),
    )
)
collector.add_event(EventRecord(timestamp=1.0, event_type="terminal_lock"))
collector.add_link(
    LinkRecord(
        timestamp=1.0,
        source_node_id="interceptor_01",
        target_node_id="center",
        payload_kind="track",
        sent_timestamp=0.9,
        received_timestamp=1.0,
    )
)
metrics = collector.compute_episode(episode_id="example", duration=10.0)
```

## 未接入项

Stone Soup metrics、TrackEval/py-motmetrics、OSPA/GOSPA/HOTA/IDF1、AirSim 原生 recording replay 和 SCRIMMAGE metrics bridge 当前都没有实际 import、adapter 或测试。原因是这些能力需要稳定的帧级 truth-track/detection 匹配表、依赖版本、坐标/时钟合同、样例数据和 CI 容差。它们是 P2/P3 的可选外部 benchmark，不替代当前本地离线指标主线。
