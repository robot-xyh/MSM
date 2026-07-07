# D6 Evaluation Metrics Plan

## 1. 模块定位与边界

D6 是系统级离线评估模块。它消费 D1-D7、main runtime、AirSim Blocks replay、合成仿真和人工/规则标注产生的日志，输出可复现的指标、CSV、Markdown 报告和 PNG 图表。

D6 不参与控制：

- 不发布航迹、分配、降级、末端配准或导引决策。
- 不生成 fire-control 参数、毁伤模型、自动处置动作或授权绕过流程。
- 不把评估侧 truth label、高威胁标签或后验 review label 回写到在线系统。
- 只读取已落盘记录；所有 AirSim/D4/D5/D7 接入均为 offline/file adapter。

D2/D6 的硬约束必须保留：`id_switch_count` 是一级显式指标，不能只被 MOTA、成功率或总体得分间接吸收。

## 2. 当前实现概览

当前 D6 已实现轻量、可测试的本地指标主线：

- 数据模型：`EpisodeMetrics`、`TrackRecord`、`AssignmentRecord`、`EventRecord`、`LinkRecord`、`TerminalRecord`。
- 收集器：`MetricsCollector.add_track/add_assignment/add_event/add_link/add_terminal()` 和 `compute_episode()`。
- 日志接口：标准化 JSONL loader、Blocks replay JSONL loader、D4 active-degradation CSV loader、D7 intercept/guidance CSV/JSON loader。
- 报告接口：`ReportGenerator` 输出 `episode_metrics.csv`、`summary_metrics.csv`、Markdown 报告和分类 PNG 图。
- 批量统计：count、mean、sample std、stderr、normal-approximation 95% CI、median、p05、p95。
- 分组统计：按 `scenario_group` 和实际 `drone_count/resource_count/target_count/camera_count` 分组。

当前依赖保持轻量：Python 标准库、NumPy、matplotlib、pytest。默认测试不依赖 AirSim 服务、Stone Soup、TrackEval、py-motmetrics、SCRIMMAGE、GPU 或网络。

## 3. 已实现指标

### 3.1 EpisodeMetrics 与规模字段

`EpisodeMetrics` 显式包含：

```text
episode_id
seed
scenario_group
batch_seed
drone_count
resource_count
target_count
camera_count
duration
metadata
```

规模口径：

- 优先读取 `truth_summary` 顶层或 `truth_summary["scenario"]` 中的 `drone_count/resource_count/target_count/camera_count`。
- Blocks replay 从 `resources`、`truth_objects`、`cameras` 计算规模。
- 缺失时从 assignment、terminal、event、link metadata 中推断资源、目标和相机集合。
- `drone_count` 缺失时默认等于 `resource_count`。
- `2v2/5v5` 只保留为 baseline 场景名，不能作为分母或规模推断来源。

测试已覆盖 `episode_id/scenario.name` 含 `5v5`，但实际规模为 `3/3/4/6` 的情况，D6 按实际字段输出。

### 3.2 探测指标

```text
detection_probability = TP / (TP + FN)
false_alarm_rate = FP / duration
missed_detection_rate = FN / (TP + FN)
```

当前实现来源：

- `TrackRecord.truth_id is not None` 作为 truth-matched detection。
- `TrackRecord.truth_id is None` 和 `EventRecord(event_type="false_alarm")` 计入 false alarm。
- `truth_summary.truth_timestamps` 或 `total_truth_opportunities` 定义真值机会数。

### 3.3 跟踪指标

```text
track_rmse = sqrt(mean(||position - truth_position||^2))
track_continuity = matched_truth_timestamp_pairs / truth_timestamp_pairs
id_switch_count = count(global_track_id changes for the same truth_id over time)
```

`id_switch_count` 对每个 `truth_id` 按时间排序，比较连续 timestamp 的 `global_track_id`。D6 不修改 `global_track_id`，只统计 D2/上游输出的身份连续性。

### 3.4 分配指标

```text
duplicate_assignment_count =
  count(targets assigned to more than one active resource in the same plan snapshot)

unassigned_high_threat_count =
  count(high-threat truth/track items without effective active assignment)
```

当前有效分配要求：

- `AssignmentRecord.active == True`。
- `authorization_state` 属于 `recorded/authorized/approved/human_approved/operator_approved` 等有效状态。
- 同一 `(timestamp, plan_id, version)` 内统计重复分配。

D6 只统计分配结果，不产生重分配建议；`AssignmentPlan` 版本有效性仍由 D3/main 控制链路负责。

### 3.5 降级指标

基础降级：

```text
failover_time = mean(t(degraded_stable) - t(central_failure))
consensus_rounds = mean(consensus_rounds event values)
degraded_completion_rate =
  degraded_task_completed / (degraded_task_completed + degraded_task_failed_or_cancelled)
```

D4 active/passive 扩展已实现 P1 基线：

```text
active_degradation_count
passive_failover_count
secondary_node_takeover_count
secondary_reassignment_count
d4_reassign_pending_count
distributed_fallback_count
failover_active_window_delta_s
```

当前识别来源包括 `EventRecord.event_type`、`metadata.mode/degradation_mode`、`metadata.action`、`metadata.assignment_phase`、`metadata.fallback_type`、D7 reject reason 和 D4 CSV loader。`metadata["trigger_reason"]` 等触发原因会进入 `EpisodeMetrics.metadata["trigger_reason_distribution"]`。

尚未实现为正式 `EpisodeMetrics` 字段的主动降级质量指标：

```text
active_degradation_precision
unnecessary_active_degradation_count
terminal_center_disagreement_count
time_to_active_degradation_decision
post_degradation_id_switch_delta
post_degradation_assignment_conflict_delta
```

这些指标需要 main/D4 写入稳定的 `review_label`、`trigger_timestamp`、`decision_timestamp`、`selected_coordinator`、`coverage_cell` 和固定 pre/post 窗口。没有这些条件时，D6 只能统计发生次数和已提供的窗口 delta，不能判断主动降级是否必要。

### 3.6 末端指标

```text
terminal_association_accuracy
terminal_id_switch_count
ambiguous_fov_event_count
friend_overlap_hold_count
time_to_terminal_lock
terminal_lock_count
multi_view_consensus_rate
cross_view_conflict_count
duplicate_terminal_lock_count
```

当前来源：

- `TerminalRecord` 中的 `decision_state`、`local_track_id`、`assigned_global_track_id`、`expected_global_track_id`、`association_correct`。
- `EventRecord` 中的 `terminal_lock`、`terminal_fov_entry`、`terminal_ambiguous_fov`、`friend_overlap_hold`、`multi_view_consensus_result`、`cross_view_conflict`、`duplicate_terminal_lock`。
- Blocks replay 的同帧多相机 bbox/label metadata，可生成 multi-view consensus/conflict 基线事件。

D5 仍然负责身份确认和 `global_track_id` 合同；D6 不重绑、不改写本地或全局 ID。

### 3.7 通信指标

```text
cross_node_latency_ms
message_drop_rate
out_of_order_count
stale_track_update_count
video_metadata_delivery_rate
bbox_delivery_rate
consensus_latency_s
```

当前来源：

- `LinkRecord`。
- 带通信字段的 `EventRecord.metadata`。
- Blocks `blocks_sensor_observations.jsonl` 的 `communication` 字段。
- Blocks frame image/bbox metadata 生成的 video metadata 和 bbox delivery 样本。

推荐保留字段：

```text
source_node_id
target_node_id
relay_node_id
link_type
message_type
sequence_id
sent_timestamp
received_timestamp
measurement_timestamp
arrival_timestamp
payload_kind
delivered
stale_after_s
```

### 3.8 D7 gate、visual PNG switch 与拦截统计

D6 已能从 D7 `control_commands.csv`、`guidance_records.csv`、`guidance_summaries.json`、`intercept_summary.json` 读取：

```text
camera_quality_gate_pass_rate
los_quality_gate_pass_rate
maneuver_margin_gate_pass_rate
terminal_switch_allowed_rate
visual_png_switch_count
terminal_takeover_rate
terminal_switch_reject_count
mode_switch_count
terminal_contract_reject_count
intercept_success_count
collision_intercept_count
range_intercept_count
time_to_intercept_s
min_range_m
gate_reject_count
```

`terminal_switch_allowed_rate` 的分母只包含带有 `terminal_switch_allowed` 字段的 D7 control command。空缺字段不进入分母。

`visual_png_switch_count` 的来源包括显式 `visual_png_switch/vision_png_switch/d7_visual_png_switch` 事件，或 `guidance_law=png_vm/png_ttc` 且伴随 `mode_switch=True`、`terminal_mode_entered=True`、`mode=vision_terminal/visual_png/vision_png` 的 D7 记录。

`terminal_takeover_rate` 按 unique `(resource_id, target_id)` pair 统计，证据包括 `terminal_locked=True`、`terminal_switch_allowed=True`、`vision_terminal` mode、`terminal_mode_entered=True`，或 `guidance_law` 为 `png_vm/png_ttc/los`。`terminal_handover_pending` 和 `detection_seen` 只能说明候选可见，不能单独算 takeover。

### 3.9 安全指标

```text
constraint_violation_count
human_override_count
```

安全事件是一级输出。即使其他指标良好，也不能把安全约束触发或人工覆盖事件用总体成功率平均掉。

## 4. 已实现输入适配器

| 适配器 | 输入 | 当前状态 | 边界 |
|---|---|---|---|
| `load_episode_log_jsonl()` | 标准化 `truth_summary/track/assignment/event/link/terminal` JSONL | 已实现并测试 | 未知 record type 直接报错，避免 schema drift 静默进入报告 |
| `load_blocks_replay_jsonl()` | `blocks_frames.jsonl`、可选 `blocks_sensor_observations.jsonl` | 已实现并测试 | 只读文件，不 import AirSim，不调用 runtime API |
| `load_d4_active_degradation_decisions()` | D4 active-degradation CSV | 已实现并测试 | 只统计 D4 已写盘决策，不判定必要性 |
| `load_d7_intercept_outputs()` | `control_commands.csv`、`intercept_summary.json` | 已实现并测试 | 只离线评估 D7 输出，不发控制 |
| `load_d7_guidance_timeseries()` | `guidance_records.csv`、`guidance_summaries.json`、D7 control/intercept 输出 | 已实现并测试 | 保留 D4/D5 state、plan/version、guidance law 和 reject reason metadata |

## 5. 部分实现与 main runtime bus 接线缺口

当前 D6 已能消费 D4/D5/D7 产物，但是否形成完整 integrated episode metrics 取决于 main runtime 的写盘和汇总接线。

已具备 D6 侧消费能力：

- D4：可读取 active-degradation CSV；可从事件 metadata 中识别 active/passive、secondary takeover/reassignment、distributed fallback、D4 reassign pending 和触发原因。
- D5：可通过 `TerminalRecord`、terminal/multi-view event、Blocks bbox/camera metadata 计算末端准确率、ID switch、lock、歧义、friend hold、多视角一致和冲突。
- D7：可读取 control/guidance/intercept CSV/JSON，计算 gate、visual PNG switch、terminal takeover、模式切换、拦截结果和 reject metadata。
- Blocks CV：可从 `blocks_frames.jsonl` 与 `blocks_sensor_observations.jsonl` 构建 truth summary、规模字段、视觉检测、terminal records、video/bbox link records 和通信链路样本。

仍需 main runtime 接线或上游日志条件：

- 在每个 integrated episode 目录稳定写出 D4、D5、D7、Blocks 和 D6 标准化 JSONL/CSV/JSON，并保持同一 episode clock。
- 将 D5 terminal association、cross-view conflict、duplicate lock、friend overlap hold 等事件持续写入 D6 可读记录；当前 D6 有指标和 Blocks metadata 基线，但不保证 main 每条 AirSim episode 都已全量回灌。
- 将 D4 `review_label`、`trigger_timestamp`、`decision_timestamp`、`selected_coordinator`、`coverage_cell`、pre/post 窗口统计写入日志，才能计算主动降级必要性/精度。
- 将 D7 `guidance_records.csv`、`guidance_summaries.json`、`control_commands.csv`、`intercept_summary.json` 纳入 main 的 episode 汇总调用，而不是只作为独立离线 loader。
- 在 summary/report pipeline 中统一调用多个 loader 并合并到同一个 `MetricsCollector`；D6 loader 本身不会主动扫描 runtime bus 或启动 AirSim。

## 6. 未实现的开源/外部项

| 项目 | 当前状态 | 未实现原因 | 缺少条件 | 优先级 |
|---|---|---|---|---|
| Stone Soup metrics | 没有 Stone Soup import、对象转换器或 metric generator 调用 | 保持默认依赖轻量；D1/D2 track/truth 尚未冻结到 Stone Soup 类型 | 版本锁定；D1/D2 adapter；GroundTruthPath/Track/Detection 映射；坐标和门限合同；CI 样例 | P2 |
| OSPA/GOSPA | 文档有公式，`EpisodeMetrics` 未输出字段 | 需要帧级 truth/estimate set 序列和 cutoff/order | 稳定集合序列；匹配门限；目标 birth/death/遮挡规则 | P2 |
| CLEAR MOT/MOTA/MOTP 标准库对照 | D6 已实现本地 RMSE/continuity/IDSW 等分量，未接标准库 | 系统评估跨越分配、降级、通信、末端和导引；默认输出优先本地可解释指标 | MOTChallenge/accumulator 导出；TrackEval/py-motmetrics 版本；距离/IoU 门限 | P2 |
| HOTA/IDF1 | 未实现 | 需要帧级检测、关联和身份评估表 | D2/D5 稳定 frame-level 输出；occlusion/reappearance 规则；外部 evaluator | P2 |
| AirSim 原生 recording replay | 未实现通用 parser | main 已提供更直接的 Blocks JSONL；原生 recording 字段、坐标、相机版本差异大 | 原生 recording 样例；schema 版本；NED/相机/时间轴映射；测试容差 | P2 |
| Live AirSim replay/API | 未实现，且不作为 D6 默认能力 | D6 边界是 offline-only | 如未来需要，也应由 main runtime 导出日志，D6 仍只读文件 | 禁止在线控制 |
| SCRIMMAGE metrics bridge | 未实现 | 当前仿真主线是 AirSim Blocks 和合成日志；仓库没有 SCRIMMAGE 输出样例或 message schema | SCRIMMAGE episode 输出；agent/resource/target ID 映射；通信事件字段；episode clock 对齐 | P3 |

## 7. 批量统计与报告

D6 报告生成器当前输出：

- `episode_metrics.csv`：每个 episode 一行，包含规模字段和所有 `EpisodeMetrics.metric_names()`。
- `summary_metrics.csv`：全局与 `scenario_group + scale` 分组统计。
- Markdown 报告：中文说明、规模范围、场景分组、汇总表和图表链接。
- PNG 图表：`detection`、`tracking`、`assignment`、`degradation`、`terminal`、`communication`、`guidance`、`safety` 和 selected metric distributions。

统计口径：

```text
mean
sample_std
stderr = sample_std / sqrt(N)
ci95 = mean +/- 1.96 * stderr
median
p05 / p95
```

偏态或长尾指标，例如 `id_switch_count`、`constraint_violation_count`、`terminal_switch_reject_count`，在正式结论中仍需要 bootstrap 或非参数方法复核。当前实现先满足回归和工程比较。

## 8. P1 下一步

1. Integrated episode 汇总接线：由 main 在每个 AirSim episode 目录统一写出 Blocks、D4、D5、D7 和 D6 标准化日志，并调用 D6 loader 合并成同一个 `MetricsCollector`。
2. D4 主动降级质量指标：要求 main/D4 写入 `review_label`、`trigger_timestamp`、`decision_timestamp`、`selected_coordinator`、`coverage_cell` 和窗口统计，补齐 `active_degradation_precision`、`unnecessary_active_degradation_count`、`time_to_active_degradation_decision`、`post_degradation_id_switch_delta`、`post_degradation_assignment_conflict_delta`。
3. D5 AirSim 末端回灌：把 terminal association、cross-view conflict、duplicate lock、friend overlap hold、terminal center disagreement 和验证标签稳定写入 D6 可读日志。
4. D7 多 seed gate/intercept 汇总：保证 `guidance_records.csv`、`guidance_summaries.json`、`control_commands.csv`、`intercept_summary.json` 在 2v2/5v5/N-v-N 中持续产出，并保留 plan/version、D4/D5 state、guidance law 和 reject reason。
5. 报告质量：在 Markdown 中增加 D4/D5/D7 分组解读和长尾风险提示，继续按实际规模字段分组，不从场景名推断。

## 9. P2 下一步

1. 帧级匹配表：定义 D1/D2/D5 的 frame-level truth/detection/track export，包含 timestamp、truth_id、global/local track ID、position/IoU/distance、occlusion/reappearance 状态。
2. 外部 MOT 对照：优先做 py-motmetrics 或 TrackEval adapter，作为可选 benchmark，不替换 D6 本地指标。
3. Stone Soup/OSPA 对照：在 D1/D2 对象映射和版本锁定后接入 Stone Soup metrics 与 OSPA/GOSPA。
4. AirSim 原生 recording parser：只有在 Blocks JSONL 不能满足评估需求时，才补通用 recording parser。
5. Bootstrap/非参数 CI：在真实多 seed 数据规模足够后，为偏态指标提供可选统计方法。
6. SCRIMMAGE bridge：仅当 AirSim 多机规模或通信建模不足以回答实验问题，并且已有真实 SCRIMMAGE 样例和 schema 时推进。

## 10. 验收命令

从仓库根目录运行：

```bash
pytest -q research_modules/d6_evaluation_metrics/tests
git diff --check -- research_modules/d6_evaluation_metrics subagent_reviews/D6_*
```

文档验收点：

- 明确 D6 只消费日志，不参与控制。
- 明确 `id_switch_count` 是 D2/D6 强制显式指标。
- 明确指标按实际 `drone_count/resource_count/target_count/camera_count` 归一化。
- 明确 D4/D5/D7 AirSim 产物的 D6 侧 loader 已实现，但 integrated episode metrics 仍依赖 main runtime 写盘和汇总接线。
- 明确 Stone Soup、AirSim replay、SCRIMMAGE 等开源/外部项的实际未实现状态、原因和缺少条件。
