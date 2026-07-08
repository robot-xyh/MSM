# D6 系统评估指标综述及子方案

**定位**：D6 建立覆盖探测、跟踪、分配、降级、末端配准、通信、D7 gate/intercept 和安全约束的离线评估体系，支持批量实验统计和报告图表。
**边界**：D6 只消费日志，不参与实时控制，不生成任务、分配、导引、火控、毁伤、自动处置或授权绕过流程。
**规模规则**：指标按实际 `drone_count/resource_count/target_count/camera_count` 归一化，并按 `metric_scope/seed/scenario_group/scale` 分组，不从 `2v2/5v5` 场景名推断规模。
**ID 规则**：D2/D6 必须保留显式 `id_switch_count`。

## 1. 研究问题

多目标 C-UAS workflow 不能只报告“成功率”。一个 episode 可能最终接近目标，但仍存在虚警高、漏检、航迹断裂、ID Switch、重复分配、高威胁未分配、中心失效后接管慢、D4 reassign pending、D5 末端误配准、D7 terminal switch reject、通信 stale update 或安全约束触发等问题。

D6 的目标是把 D1-D7 和 main runtime 的离线日志统一为可比较、可复现、可画图的系统级指标。D6 的评估结果服务报告和回归分析，不回写控制。

## 2. 当前实现状态摘要

已实现：

- 数据模型：`EpisodeMetrics`、`TrackRecord`、`AssignmentRecord`、`EventRecord`、`LinkRecord`、`TerminalRecord`。
- 指标收集：`MetricsCollector`。
- JSONL：标准化 `truth_summary/track/assignment/event/link/terminal` loader。
- AirSim Blocks：`load_blocks_replay_jsonl()` 读取 `blocks_frames.jsonl` 与可选 `blocks_sensor_observations.jsonl`。
- D4：`load_d4_active_degradation_decisions()` 读取 active-degradation CSV。
- D7：`load_d7_intercept_outputs()`、`load_d7_guidance_timeseries()` 读取 control/guidance/intercept CSV/JSON。
- 报告：episode CSV、summary CSV、Markdown、PNG 图表和批量统计。
- main/orchestrator 2026-07-07 已把 D7 真实执行指标合并进正式 `main_episode_bus_metrics.json`，并把执行前合同检查保留为 `main_episode_bus_contract_metrics.json`；D6 只消费这些写盘结果，不参与控制。

部分实现 / 剩余 P1：

- D7 real execution 的正式/contract 双口径已完成主线；D6 已补 `metric_scope` 和按 seed/scenario/实际规模分组的报告口径。剩余工作是多 seed、5v5/N-v-N 和非默认 episode 持续采用同一双口径。
- D6 已具备 D4/D5/D7/Blocks 离线消费能力，但真实 integrated episode 仍需要 main runtime 在同一 episode 目录写盘、对齐时间轴并调用多个 loader 合并。
- D4 主动降级已能统计次数、secondary takeover/reassignment、pending、窗口 delta、`active_degradation_precision` 和 `unnecessary_active_degradation_count`；必要性/精度只消费真实 episode 写出的 review label 或后验字段，缺 label 不进入 precision 分母。

未实现：

- Stone Soup metrics、TrackEval/py-motmetrics、OSPA/GOSPA/HOTA/IDF1 标准输出。
- AirSim 原生 recording parser 和 live AirSim replay/API。
- SCRIMMAGE metrics bridge。

## 3. 指标体系

| 类别 | 已实现指标 | 含义 |
|---|---|---|
| 探测 | `detection_probability` | 真值机会中被检测到的比例 |
| 探测 | `false_alarm_rate` | 单位时间虚警数 |
| 探测 | `missed_detection_rate` | 漏检比例 |
| 跟踪 | `track_rmse` | 航迹位置与真值的均方根误差 |
| 跟踪 | `track_continuity` | 真值 timestamp 被匹配覆盖的比例 |
| 跟踪 | `id_switch_count` | 同一 `truth_id` 对应 `global_track_id` 变化次数 |
| 分配 | `duplicate_assignment_count` | 同一 plan snapshot 中多个资源分配到同一目标 |
| 分配 | `unassigned_high_threat_count` | 评估侧高威胁目标未被有效 active assignment 覆盖 |
| 降级 | `failover_time` | 中心失效到降级稳定的平均耗时 |
| 降级 | `consensus_rounds` | 离线记录的协商轮数均值 |
| 降级 | `degraded_completion_rate` | 降级任务完成比例 |
| 降级 | `active_degradation_count` | D4 主动降级决策次数 |
| 降级 | `active_degradation_precision` | 有 review/后验标签的主动降级中必要标签比例 |
| 降级 | `unnecessary_active_degradation_count` | 有 review/后验标签且判为不必要的主动降级次数 |
| 降级 | `passive_failover_count` | 被动 failover 次数 |
| 降级 | `secondary_node_takeover_count` | 二级节点接管/协助次数 |
| 降级 | `secondary_reassignment_count` | 二级节点重分配次数 |
| 降级 | `d4_reassign_pending_count` | D4 重分配未完成导致的 pending/reject |
| 降级 | `distributed_fallback_count` | 分布式 fallback 次数 |
| 降级 | `failover_active_window_delta_s` | active window 与 failover/takeover 之间的平均 delta |
| 末端 | `terminal_association_accuracy` | D5 末端局部绑定正确率 |
| 末端 | `terminal_id_switch_count` | 同一 `assigned_global_track_id` 下 local visual ID 变化次数 |
| 末端 | `ambiguous_fov_event_count` | 末端视场歧义事件数 |
| 末端 | `friend_overlap_hold_count` | 友方 overlap 导致 hold 的事件数 |
| 末端 | `time_to_terminal_lock` | FOV entry 到 terminal lock 的平均时间 |
| 末端 | `terminal_lock_count` | 唯一 terminal lock 事件/记录数 |
| 末端 | `multi_view_consensus_rate` | 多视角一致成功比例 |
| 末端 | `cross_view_conflict_count` | 跨视角绑定冲突数 |
| 末端 | `duplicate_terminal_lock_count` | 同一目标被多个资源重复锁定次数 |
| 通信 | `cross_node_latency_ms` | 跨节点平均 latency |
| 通信 | `message_drop_rate` | 消息丢弃比例 |
| 通信 | `out_of_order_count` | 显式乱序事件和序列号倒退 |
| 通信 | `stale_track_update_count` | 超过 stale threshold 的 track payload |
| 通信 | `video_metadata_delivery_rate` | video metadata delivery 比例 |
| 通信 | `bbox_delivery_rate` | bbox delivery 比例 |
| 通信 | `consensus_latency_s` | consensus/bid 或 start-to-stable latency |
| D7 gate | `camera_quality_gate_pass_rate` | 相机质量 gate 通过率 |
| D7 gate | `los_quality_gate_pass_rate` | LOS 质量 gate 通过率 |
| D7 gate | `maneuver_margin_gate_pass_rate` | 机动余量 gate 通过率 |
| D7 gate | `terminal_switch_allowed_rate` | D7 允许末端切换的 command 比例 |
| D7 gate | `visual_png_switch_count` | 切换到视觉 PNG/PNG guidance 相关模式的次数 |
| D7 gate | `terminal_takeover_rate` | unique pair 中进入末端接管的比例 |
| D7 gate | `terminal_switch_reject_count` | 末端切换拒绝次数 |
| D7 intercept | `mode_switch_count` | guidance mode switch 次数 |
| D7 intercept | `terminal_contract_reject_count` | terminal contract reject 次数 |
| D7 intercept | `intercept_success_count` | 离线成功状态计数 |
| D7 intercept | `collision_intercept_count` | collision threshold 命中计数 |
| D7 intercept | `range_intercept_count` | range threshold 命中计数 |
| D7 intercept | `time_to_intercept_s` | 达到拦截状态的平均时间 |
| D7 intercept | `min_range_m` | episode/pair 最小距离 |
| D7 intercept | `gate_reject_count` | gate/reject 事件总数 |
| 安全 | `constraint_violation_count` | 安全约束违反次数 |
| 安全 | `human_override_count` | 人工覆盖或拒绝次数 |

## 4. 日志模型

### 4.1 Tracking / Detection

```text
TrackRecord
- timestamp
- global_track_id
- truth_id
- position
- truth_position
- covariance_trace
- track_state
- association_source
```

要求：

- `global_track_id` 由中心/上游维护，D6 不重写。
- `truth_id` 是离线评估标签，不可进入在线 D5/D7 控制判断。
- D1 输出应保留测量时间、到达时间和协方差；D6 通过记录或 link metadata 消费这些信息。

### 4.2 Assignment

```text
AssignmentRecord
- timestamp
- plan_id
- version
- resource_id
- global_track_id
- cost_breakdown
- authorization_state
- active
- truth_id
```

D6 只统计 active 且有效授权状态的分配。stale plan reject 由 D3/main 在线链路负责，D6 可在日志中统计结果但不执行拒绝。

### 4.3 Event

```text
EventRecord
- timestamp
- event_type
- actor_id
- severity
- note
- value
- metadata
```

典型事件：

```text
central_failure
degraded_stable
consensus_rounds
degraded_task_completed
degraded_task_failed
active_degradation_decision
passive_failover
secondary_node_takeover
secondary_reassignment
d4_reassign_pending
distributed_fallback
terminal_lock
terminal_fov_entry
terminal_ambiguous_fov
friend_overlap_hold
multi_view_consensus_result
cross_view_conflict
duplicate_terminal_lock
d7_control_command
d7_guidance_record
d7_intercept_pair_summary
constraint_violation
human_override
```

### 4.4 Link

```text
LinkRecord
- timestamp
- source_node_id
- target_node_id
- relay_node_id
- link_type
- message_type
- sequence_id
- sent_timestamp
- received_timestamp
- measurement_timestamp
- arrival_timestamp
- payload_kind
- delivered
- stale_after_s
- metadata
```

`measurement_timestamp` 和 `arrival_timestamp` 必须保留，用于 stale 和 latency 统计。

### 4.5 Terminal

```text
TerminalRecord
- timestamp
- resource_id
- assigned_global_track_id
- local_track_id
- decision_state
- ambiguity_score
- friend_conflict_state
- assignment_version
- expected_global_track_id
- association_correct
```

D5 不得本地改写 `global_track_id`。D6 只统计末端绑定与中心/评估标签的一致性。

## 5. AirSim / D4 / D5 / D7 接入方案

### 5.1 Blocks replay

已实现 `load_blocks_replay_jsonl()`：

- `blocks_frames.jsonl` 提供 truth objects、resources、cameras、visual detections、image metadata。
- `blocks_sensor_observations.jsonl` 提供 D1 replay observation 和 communication metadata。
- D6 从中构建 truth summary、实际规模字段、visual track、terminal records、video metadata links、bbox links、multi-view consensus/conflict。
- PNG 不必保存；`metadata.images[].path` 只进入 `png_saved` 元数据。

### 5.2 D4

已实现：

- D4 active-degradation CSV loader。
- 主/被动降级、secondary takeover/reassignment、distributed fallback、D4 reassign pending、触发原因分布。
- `review_label`、`active_degradation_necessary`、`post_window_outcome`、trigger/decision timestamp、selected coordinator、coverage cell 和 pre/post window 字段离线消费。

仍需 main/D4：

- 持续写出真实 episode 的 D4 决策日志。
- 在每个 episode 稳定提供 `review_label`、`trigger_timestamp`、`decision_timestamp`、`selected_coordinator`、`coverage_cell`。
- 固定 pre/post 窗口，支持真实数据中的必要性、改善 delta、decision latency、ID switch delta 和 assignment conflict delta。

### 5.3 D5

已实现：

- D6 指标和数据模型可消费 D5 terminal/multi-view 日志。
- Blocks replay 可提供无 PNG 的 bbox/camera metadata 基线。

仍需 main/D5：

- 写出 terminal association、identity claim、terminal-center disagreement、cross-view conflict、duplicate lock、friend overlap hold、validation label。
- 保留 bbox、相机内外参、timestamp、`resource_id/camera_id`、`local_track_id`、`assigned_global_track_id`。

### 5.4 D7

已实现：

- D7 control/guidance/intercept 文件 loader。
- gate pass rate、switch allowed/reject、visual PNG switch、takeover rate、mode switch、contract reject、intercept counts。
- `metadata` 中保留 guidance law、reject reason、D4/D5 state、plan/version。

main/orchestrator 已完成：

- 真实执行后的 `control_commands.csv` 与 `intercept_summary.json` 合并进正式 `main_episode_bus_metrics.json`。
- 执行前合同检查口径保留为 `main_episode_bus_contract_metrics.json`，用于诊断 gate/reject，而不覆盖执行后拦截结果。

仍需 main/D7：

- 每个 integrated AirSim episode 稳定写出 D7 文件。
- 在多 seed、5v5/N-v-N 和非默认 episode 中保持正式 metrics 与 raw contract metrics 的双口径，并让 D6 报告继续按 `metric_scope/seed/scenario_group/scale` 分组。

## 6. 开源工具与外部 benchmark

| 工具/接口 | 当前实际状态 | 原因和条件 |
|---|---|---|
| Stone Soup metrics | 未使用 | 需要 Stone Soup 版本锁定、D1/D2 到 `Track/Detection/GroundTruthPath` 的 adapter、坐标/门限合同和 CI fixture |
| TrackEval | 未使用 | 需要 MOTChallenge 格式或等价 frame-level export、IoU/距离门限和依赖容差 |
| py-motmetrics | 未使用 | 需要 accumulator 输入、帧级匹配表和门限 |
| OSPA/GOSPA | 未输出字段 | 需要 truth/estimate set 序列、cutoff/order、birth/death/遮挡规则 |
| HOTA/IDF1 | 未输出字段 | 需要完整帧级检测/关联/身份评估表 |
| AirSim 原生 recording parser | 未实现 | Blocks JSONL 已满足当前主线；原生 recording 需要样例、schema、坐标和时钟映射 |
| Live AirSim replay/API | 未实现且非 D6 目标 | D6 只读文件；live replay 应由 main runtime 执行并导出日志 |
| SCRIMMAGE metrics | 未实现 | 当前无 SCRIMMAGE 输出样例、message schema、ID 映射和 episode clock 合同 |

这些外部项是 P2/P3 的可选 benchmark 或扩展，不替代当前本地离线指标。

## 7. 批量统计与报告

当前报告生成：

```text
episode_metrics.csv
summary_metrics.csv
batch_report.md
plots/detection_metrics.png
plots/tracking_metrics.png
plots/assignment_metrics.png
plots/degradation_metrics.png
plots/terminal_metrics.png
plots/communication_metrics.png
plots/guidance_metrics.png
plots/safety_metrics.png
plots/selected_metric_distributions.png
```

统计量：

```text
count
mean
sample_std
stderr
normal-approximation 95% CI
median
p05
p95
```

偏态或长尾指标在正式结论前应补 bootstrap 或非参数 CI；当前实现满足工程回归和批量对比。

## 8. 示例实验报告模板

```text
实验名称：
episode / batch seed：
metric_scope：execution / contract / not_recorded
scenario_group：
实际规模：
- drone_count:
- resource_count:
- target_count:
- camera_count:

数据来源：
- synthetic / Blocks JSONL / D4 CSV / D5 terminal JSONL / D7 CSV+JSON
- 是否保存 PNG:

探测：
- detection_probability:
- false_alarm_rate:
- missed_detection_rate:

跟踪：
- track_rmse:
- track_continuity:
- id_switch_count:

分配：
- duplicate_assignment_count:
- unassigned_high_threat_count:

降级：
- active_degradation_count:
- active_degradation_precision:
- unnecessary_active_degradation_count:
- passive_failover_count:
- secondary_node_takeover_count:
- secondary_reassignment_count:
- d4_reassign_pending_count:
- distributed_fallback_count:
- failover_time:
- consensus_rounds:
- degraded_completion_rate:

末端：
- terminal_association_accuracy:
- terminal_id_switch_count:
- ambiguous_fov_event_count:
- friend_overlap_hold_count:
- terminal_lock_count:
- time_to_terminal_lock:
- multi_view_consensus_rate:
- cross_view_conflict_count:
- duplicate_terminal_lock_count:

通信：
- cross_node_latency_ms:
- message_drop_rate:
- out_of_order_count:
- stale_track_update_count:
- video_metadata_delivery_rate:
- bbox_delivery_rate:
- consensus_latency_s:

D7 gate/intercept：
- terminal_switch_allowed_rate:
- visual_png_switch_count:
- terminal_takeover_rate:
- terminal_switch_reject_count:
- mode_switch_count:
- terminal_contract_reject_count:
- intercept_success_count:
- collision_intercept_count:
- range_intercept_count:
- time_to_intercept_s:
- min_range_m:
- gate_reject_count:

安全：
- constraint_violation_count:
- human_override_count:

结论：
- 主要失效模式：
- 长尾风险：
- 需 main/D4/D5/D7 补充的日志：
- 是否需要人工复核：
```

## 9. P1 下一步

1. 真实 episode review/window 写盘：main/D4 稳定写出 review label、trigger/decision timestamp、selected coordinator、coverage cell、pre/post window 和后验 outcome/risk 字段；D6 不从事件名推断必要性。
2. 多 seed 报告口径：在 2v2、5v5、N-v-N 和非默认 episode 批量运行中持续保留 `metric_scope=execution/contract`、seed/scenario/实际规模字段和 D7 guidance/control/intercept metadata。
3. 真实 episode 日志完整性：D4/D5/D7/Blocks 产物持续落到同一 episode clock 和目录，D6 汇总阶段调用 loader 合并；D6 继续只消费日志，不参与控制、重规划或导引。

## 10. P2 下一步

1. 定义 frame-level truth/detection/track 匹配表。
2. 接入 TrackEval 或 py-motmetrics 作为可选 MOT benchmark。
3. 接入 Stone Soup 与 OSPA/GOSPA 作为论文级对照。
4. 为长尾指标增加 bootstrap/非参数 CI。
5. 有真实 SCRIMMAGE schema 和样例后再把 SCRIMMAGE bridge 作为 P3 可选项评估。
6. 仅在 Blocks JSONL 不足时增加 AirSim 原生 recording parser。

## 11. 验收命令

```bash
pytest -q research_modules/d6_evaluation_metrics/tests
git diff --check -- research_modules/d6_evaluation_metrics subagent_reviews/D6_*
```

## 12. 参考资料

- Stone Soup metrics: <https://stonesoup.readthedocs.io/en/latest/stonesoup.metricgenerator.tracktotruthmetrics.html>
- Stone Soup OSPA metrics: <https://stonesoup.readthedocs.io/en/latest/stonesoup.metricgenerator.ospametric.html>
- TrackEval: <https://github.com/JonathonLuiten/TrackEval>
- py-motmetrics: <https://github.com/cheind/py-motmetrics>
- AirSim APIs: <https://microsoft.github.io/AirSim/apis/>
- AirSim recording: <https://microsoft.github.io/AirSim/modify_recording_data/>
- SCRIMMAGE: <https://github.com/gtri/scrimmage>
