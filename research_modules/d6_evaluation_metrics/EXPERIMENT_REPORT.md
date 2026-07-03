# D6 系统级评估指标实验报告

## 1. 实验边界

D6 是离线评估模块，只消费记录、仿真日志或脱敏数据，输出指标、表格和图表。它不参与实时任务决策，不提供火控参数，不建模毁伤，不自动处置目标，也不绕过人工授权。

## 2. 实验目的

D6 的目标是避免只用“命中率”评价系统，而是同时覆盖探测、跟踪、分配、降级、末端配准和安全约束六类指标。本轮实验验证：

- `EpisodeMetrics` 能否统一记录所有关键指标。
- D3 未授权候选分配是否不会被算作有效分配。
- 高威胁目标在无有效分配时是否被正确计为未分配。
- D5 的 `TerminalRecord` 与 `EventRecord` 是否不会对同一歧义/友方 hold 事件双计数。

详细算法原理、公式、日志来源和 D4/D5 后续扩展字段见 `docs/ALGORITHM_AND_IMPLEMENTATION.md`。

## 3. 批量实验配置

运行命令：

```bash
python3 research_modules/d6_evaluation_metrics/scripts/run_batch_example.py --seeds 100
```

| 项目 | 设置 |
|---|---:|
| 数据来源 | 合成离线日志 |
| episode 数 | 100 |
| 单 episode 时长 | 60 s |
| 输出目录 | `outputs/example_batch/` |

## 4. 指标体系

| 类别 | 指标 |
|---|---|
| 探测 | `detection_probability`, `false_alarm_rate`, `missed_detection_rate` |
| 跟踪 | `track_rmse`, `track_continuity`, `id_switch_count` |
| 分配 | `duplicate_assignment_count`, `unassigned_high_threat_count` |
| 降级 | `failover_time`, `consensus_rounds`, `degraded_completion_rate` |
| 主动降级扩展 | `passive_failover_count`, `active_degradation_count`, `active_degradation_precision`, `unnecessary_active_degradation_count`, `terminal_center_disagreement_count`, `time_to_active_degradation_decision`, `post_degradation_id_switch_delta`, `post_degradation_assignment_conflict_delta` |
| 末端 | `terminal_association_accuracy`, `terminal_id_switch_count`, `ambiguous_fov_event_count`, `friend_overlap_hold_count`, `time_to_terminal_lock`, `multi_view_consensus_rate`, `cross_view_conflict_count`, `duplicate_terminal_lock_count` |
| 通信 | `cross_node_latency_ms`, `message_drop_rate`, `out_of_order_count`, `stale_track_update_count`, `video_metadata_delivery_rate`, `bbox_delivery_rate`, `consensus_latency_s` |
| 导引门控 | `camera_quality_gate_pass_rate`, `los_quality_gate_pass_rate`, `maneuver_margin_gate_pass_rate`, `terminal_switch_allowed_rate`, `terminal_switch_reject_count`, `intercept_success_count`, `collision_intercept_count`, `range_intercept_count`, `time_to_intercept_s`, `min_range_m`, `gate_reject_count` |
| 安全 | `constraint_violation_count`, `human_override_count` |

主动降级扩展目前是 D6 文档侧定义的离线评估合同，详见 `docs/ALGORITHM_AND_IMPLEMENTATION.md`。正式纳入代码前，D4 应在 `EventRecord.metadata` 中提供 `degradation_mode`, `trigger_sources`, `selected_coordinator`, `coverage_cell`, `arbiter_score`, `trigger_timestamp` 等字段。

## 5. 图表与曲线

### 5.1 探测指标统计图

![D6 探测指标统计图](outputs/example_batch/plots/detection_metrics.png)

该图展示探测概率、虚警率和漏检率的批量均值及置信区间，用于评估前端探测网是否稳定。

### 5.2 跟踪指标统计图

![D6 跟踪指标统计图](outputs/example_batch/plots/tracking_metrics.png)

该图展示 RMSE、航迹连续性和 ID Switch。ID Switch 应与 D2 的身份连续性结果一起分析，避免只看覆盖率。

### 5.3 分配与降级指标图

![D6 分配指标统计图](outputs/example_batch/plots/assignment_metrics.png)

![D6 降级指标统计图](outputs/example_batch/plots/degradation_metrics.png)

分配图用于检查重复分配和高威胁未分配。降级图用于分析中心节点失效后的接管耗时、共识轮数和任务完成率。

### 5.4 末端与安全指标图

![D6 末端指标统计图](outputs/example_batch/plots/terminal_metrics.png)

![D6 安全指标统计图](outputs/example_batch/plots/safety_metrics.png)

末端图反映终端锁定准确率、终端 ID Switch、视场歧义和友方 hold。安全图用于记录约束违反和人工覆盖事件。

### 5.5 关键指标分布曲线

![D6 关键指标分布曲线](outputs/example_batch/plots/selected_metric_distributions.png)

分布图用于发现均值掩盖的长尾问题。例如少数 episode 的 ID Switch 或 safety violation 可能比平均值更值得关注。

## 6. 输出文件

| 文件 | 用途 |
|---|---|
| `episode_metrics.csv` | 每个 episode 一行 |
| `summary_metrics.csv` | 每个指标的均值、标准差、置信区间和分位数 |
| `batch_report.md` | 自动生成的批量摘要 |
| `plots/*.png` | 六类指标图和分布图 |
| `logs/*.jsonl` | 原始离线记录 |

## 7. 结论

D6 已能覆盖探测、跟踪、分配、降级、末端和安全六类指标。当前版本特别修正了两个系统级统计风险：无有效分配时高威胁目标不会漏报，末端歧义/友方 hold 不会因同时记录 `TerminalRecord` 和 `EventRecord` 而双计数。后续系统集成时，D1-D5 必须遵守 `INTEGRATION_CONTRACT.md` 中的时间戳、坐标系、授权和版本字段约束。
