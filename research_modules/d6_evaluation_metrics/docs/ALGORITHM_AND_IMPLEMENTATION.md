# D6 系统级评估指标体系：算法原理与当前实现

## 1. 模块定位

D6 是 MSM 的系统级离线评估模块。它消费 D1-D7、main runtime、AirSim Blocks replay、合成仿真和人工/规则标注产生的日志，输出 episode 级指标、CSV、Markdown 报告和 PNG 图表。

D6 不参与实时控制，不发布航迹、分配、降级、末端配准或导引命令，不生成 fire-control 参数、毁伤逻辑、自动处置动作，也不绕过人工授权。所有 truth label、高威胁标签和 review label 都是评估侧信息，不能回写在线控制链路。

系统评估不能只看单一成功率。D6 把失效拆为探测、跟踪、分配、降级、末端、通信、导引门控和安全八类，避免 ID Switch、重复分配、D4 reassign pending、D5 末端误配准、D7 terminal gate reject 或安全约束被总体命中率掩盖。

D2/D6 强制规则：`id_switch_count` 必须作为显式指标保留。

## 2. 输入输出模型

### 2.1 输入数据类

| 数据类 | 当前用途 | 关键字段 |
|---|---|---|
| `TrackRecord` | 探测、跟踪、ID switch、RMSE、continuity | `timestamp`, `global_track_id`, `truth_id`, `position`, `truth_position`, `covariance_trace`, `track_state`, `association_source` |
| `AssignmentRecord` | 分配重复、高威胁未分配 | `timestamp`, `plan_id`, `version`, `resource_id`, `global_track_id`, `authorization_state`, `active`, `truth_id` |
| `EventRecord` | 降级、安全、末端事件、D7 gate、通信 metadata | `timestamp`, `event_type`, `actor_id`, `value`, `metadata` |
| `LinkRecord` | 跨节点通信、video metadata、bbox delivery | `source_node_id`, `target_node_id`, `sequence_id`, `sent_timestamp`, `received_timestamp`, `measurement_timestamp`, `arrival_timestamp`, `payload_kind`, `delivered`, `stale_after_s` |
| `TerminalRecord` | D5 末端配准、local ID switch、lock/hold/ambiguity | `resource_id`, `assigned_global_track_id`, `local_track_id`, `decision_state`, `ambiguity_score`, `friend_conflict_state`, `expected_global_track_id`, `association_correct` |
| `truth_summary` | 真值机会、高威胁标签、规模字段、场景 metadata | `truth_timestamps`, `total_truth_opportunities`, `high_threat_ids`, `high_threat_by_timestamp`, `scenario` |

### 2.2 输出

| 输出 | 当前状态 |
|---|---|
| `EpisodeMetrics` | 已实现，包含全部标量指标和 `metadata` |
| `episode_metrics.csv` | 已实现，每个 episode 一行 |
| `summary_metrics.csv` | 已实现，全局与场景/规模分组统计 |
| `batch_report.md` | 已实现，中文 Markdown 报告 |
| `plots/*.png` | 已实现，按指标族输出 PNG 图 |

## 3. 规模归一化

`EpisodeMetrics` 显式保留：

```text
drone_count
resource_count
target_count
camera_count
```

计算口径：

1. 优先使用 `truth_summary` 顶层字段或 `truth_summary["scenario"]` 字段。
2. Blocks replay 从 `resources`、`truth_objects`、`cameras` 计算实际规模。
3. 缺失时从 assignment、terminal、event、link metadata 中推断资源、目标和相机集合。
4. `drone_count` 缺失时默认等于 `resource_count`。
5. `2v2`、`5v5` 只作为 baseline 场景名，不作为算法规模或报告分母。

测试已覆盖 `scenario.name="blocks_cv_5v5"` 但实际 `drone/resource/target/camera=3/3/4/6` 的情况，D6 输出实际规模。

## 4. 指标体系

### 4.1 探测

```text
detection_probability = TP / (TP + FN)
false_alarm_rate = FP / T
missed_detection_rate = FN / (TP + FN)
```

实现来源：

- `TrackRecord.truth_id + timestamp` 落入 `truth_summary.truth_timestamps`，或显式 offline match/miss 事件完成裁决后，探测三项才可用；仅有 truth opportunity 列表不足以评分。
- `TrackRecord.truth_id is None` 不自动计 FP；离线带标签检测落在 truth pair 集合外时才计 FP。
- `truth_summary.total_truth_opportunities` 或 `truth_timestamps` 定义总机会数。

### 4.2 跟踪

```text
track_rmse = sqrt(mean(||position - truth_position||^2))
track_continuity = matched_truth_timestamp_pairs / truth_timestamp_pairs
id_switch_count = count(global_track_id changes for the same truth_id over time)
```

`id_switch_count` 以 `truth_id` 分组、按 timestamp 排序，统计同一真值目标对应 `global_track_id` 的变化次数。D6 只统计，不修改 D2/main 中心维护的 `global_track_id`。

### 4.3 分配

```text
duplicate_assignment_count =
  count(targets assigned to more than one active resource in the same plan snapshot)

unassigned_high_threat_count =
  count(high-threat targets without active effective assignment)
```

有效分配要求：

- `AssignmentRecord.active == True`
- `authorization_state` 属于 `recorded/authorized/approved/human_approved/operator_approved`
- 同一 `(timestamp, plan_id, version)` 内比较资源和目标

D6 不拒绝 stale plan、不生成 replan；版本化 `AssignmentPlan` 的在线合同由 D3/main 负责，D6 只在离线报告中统计结果。

### 4.4 降级

基础指标：

```text
failover_time = mean(t(degraded_stable) - t(central_failure))
consensus_rounds = mean(consensus_rounds event values)
degraded_completion_rate =
  degraded_task_completed / (degraded_task_completed + degraded_task_failed_or_cancelled)
```

D4 主/被动降级扩展已进入 `EpisodeMetrics`：

```text
active_degradation_count
active_degradation_precision
unnecessary_active_degradation_count
passive_failover_count
secondary_node_takeover_count
secondary_reassignment_count
d4_reassign_pending_count
distributed_fallback_count
failover_active_window_delta_s
```

识别来源：

- `EventRecord.event_type`：`active_degradation_decision`、`passive_failover`、`secondary_node_takeover`、`secondary_reassignment`、`d4_reassign_pending`、`distributed_fallback` 等。
- `metadata.mode/degradation_mode/action/assignment_phase/fallback_type/d4_state`。
- D7 reject reason 中的 `d4_reassign_pending`。
- D4 active-degradation CSV loader。

`EpisodeMetrics.metadata` 当前保留：

```text
trigger_reason_distribution
failover_active_window_deltas_s
active_degradation_review_label_counts
active_degradation_reviewed_count
active_degradation_necessary_count
```

P1 最小主动降级必要性口径已经正式输出：`active_degradation_precision` 只统计带有 `review_label`、`active_degradation_necessary`、`post_window_outcome` 或 pre/post risk/window 后验字段的主动降级样本；缺标签样本只进入 `active_degradation_count`，不进入 precision 分母。`unnecessary_active_degradation_count` 只统计被 review/后验判为不必要的主动降级。D6 不从事件名自证主动降级是否必要。

仍未正式输出的扩展主动降级质量指标：

```text
terminal_center_disagreement_count
time_to_active_degradation_decision
post_degradation_id_switch_delta
post_degradation_assignment_conflict_delta
```

原因是这些扩展指标仍需要 main/D4 持续提供 `trigger_timestamp`、`decision_timestamp`、`selected_coordinator`、`coverage_cell`、固定 pre/post 窗口、ID switch delta 和 assignment conflict delta。D6 当前只消费已写盘 review/window 字段，不参与 D4 仲裁或重分配。

### 4.5 末端配准

```text
terminal_association_accuracy =
  correct_terminal_associations / terminal_association_attempts

terminal_id_switch_count =
  count(local_track_id changes for the same assigned_global_track_id)

time_to_terminal_lock =
  first terminal_lock time - first fov_entry time
```

当前字段：

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

来源：

- `TerminalRecord.decision_state`、`ambiguity_score`、`friend_conflict_state`、`association_correct`。
- `EventRecord`：`terminal_lock`、`terminal_fov_entry`、`terminal_ambiguous_fov`、`friend_overlap_hold`、`multi_view_consensus_result`、`cross_view_conflict`、`duplicate_terminal_lock`。
- Blocks replay 的 bbox、相机内外参、camera ID、object label 和 truth label。

D5 负责在线身份确认和跨视角一致性；D6 只统计结果，不改写 `global_track_id`。

### 4.6 通信链路

```text
cross_node_latency_ms =
  mean((received_timestamp - sent_timestamp) * 1000)

message_drop_rate =
  dropped_messages / attempted_messages

out_of_order_count =
  explicit out-of-order events + decreasing sequence IDs per stream

stale_track_update_count =
  track payload latency/age > stale_after_s

video_metadata_delivery_rate =
  delivered video_metadata payloads / attempted video_metadata payloads

bbox_delivery_rate =
  delivered bbox payloads / attempted bbox payloads

consensus_latency_s =
  mean(consensus start-to-stable latency or consensus/bid link latency)
```

`measurement_timestamp` 和 `arrival_timestamp` 必须保留。D6 用它们评估 stale track update，但不改变 D1 的时间合同。

### 4.7 D7 gate、visual PNG switch 与拦截

当前字段：

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

来源：

- `d7_control_command` / `control_command` event metadata。
- `d7_guidance_record`、`d7_guidance_summary`、`d7_guidance_pair_summary`。
- `d7_intercept_summary`、`d7_intercept_pair_summary`。
- `control_commands.csv`、`guidance_records.csv`、`guidance_summaries.json`、`intercept_summary.json`。

规则：

- `terminal_switch_allowed_rate` 的分母只包含带 `terminal_switch_allowed` 字段的 D7 command。
- `visual_png_switch_count` 统计视觉 PNG/PNG guidance mode switch，不要求保存 PNG 文件。
- `terminal_takeover_rate` 按 unique `(resource_id, target_id)` pair 统计；`terminal_handover_pending` 和 `detection_seen` 不能单独算 takeover。
- reject reason、guidance law、D4/D5 state、plan/version 会进入 `EpisodeMetrics.metadata`，用于报告分组解释。

### 4.8 安全

```text
constraint_violation_count
human_override_count
```

安全事件是一级指标，不能被总体成功率平均掉。D6 只统计约束触发和人工覆盖/拒绝事件，不做在线干预。

## 5. 已实现适配器

| 适配器 | 输入 | 输出/用途 |
|---|---|---|
| `load_episode_log_jsonl()` | D6 标准化 JSONL | `MetricsCollector` + `truth_summary` |
| `load_blocks_replay_jsonl()` | `blocks_frames.jsonl`、可选 `blocks_sensor_observations.jsonl` | Blocks truth、视觉检测、terminal、通信和规模字段 |
| `load_main_episode_bus_metrics()` / `load_main_episode_bus_metric_files()` | `main_episode_bus_metrics.json`、`main_episode_bus_contract_metrics.json` | 还原 execution/contract 双口径 `EpisodeMetrics` |
| `load_d4_active_degradation_decisions()` | D4 active-degradation CSV | D4 主动降级事件 |
| `load_d7_intercept_outputs()` | D7 control/intercept CSV/JSON | D7 gate、visual switch、takeover、intercept 指标 |
| `load_d7_guidance_timeseries()` | D7 guidance/control/intercept CSV/JSON | D7 time-series 与 metadata |
| `load_airsim_calibration_records()` / `AirSimCalibrationReportGenerator` | AirSim batch/seed/case 目录 | 多 seed D4/D5 calibration records、summary 和中文 Markdown |

所有适配器都只读文件，不 import AirSim，不调用车辆控制 API。

## 6. AirSim 与 D4/D5/D7 integrated metrics 状态

D6 侧已经具备消费能力：

- Blocks：truth summary、实际规模字段、visual detection、terminal records、video metadata/bbox links、多视角 consensus/conflict。
- D4：active/passive、secondary takeover/reassignment、D4 reassign pending、distributed fallback、review label 和后验必要性字段。
- D5：terminal association、local ID switch、lock、ambiguity、friend hold、多视角一致/冲突/重复锁定、secondary detection available but not registered、cross-view registration 和 cue/gimbal pointing metadata。
- D7：gate pass/reject、visual PNG switch、terminal takeover、mode switch、contract reject、intercept 结果。
- AirSim calibration：自动扫描 `d4d5_stress_metrics.json`、`airsim_blocks_summary.json` 和 main bus metrics，输出 `airsim_calibration_records.csv`、`airsim_calibration_summary.csv`、`airsim_calibration_summary.json`、`airsim_calibration_report.md`。

截至 2026-07-07，main/orchestrator 已完成 D7 真实执行指标的正式回灌：`control_commands.csv` 与 `intercept_summary.json` 会在执行后合并到正式 `main_episode_bus_metrics.json`；执行前合同检查口径保留为 `main_episode_bus_contract_metrics.json`。D6 文档和报告口径以正式 metrics 表示执行后系统结果，以 raw contract metrics 表示 D3/D4/D5/D7 gate 诊断结果。

截至 2026-07-08，main runtime 的 `--p1-calibration-sweep` 已在 batch 结束后自动调用 D6 `AirSimCalibrationReportGenerator.write_report_bundle()`。D6 report bundle 覆盖 coverage/funnel/gimbal、`secondary_detect_count`、`secondary_visible_target_union_ratio`、`secondary_network_joint_full_view_frame_rate`、`projection_valid_rate`、`geometry_gate_pass_rate`、`registered_candidate_count`、`stable_cross_view_registration_count`、`not_registered_count`、active degradation precision 和 D7 guidance reject reason。报告按实际 count 字段和 `metric_scope/seed/scenario/secondary_height/FOV/secondary_count/detection_backend` 分组，不从 `2v2/5v5` 场景名推断规模。

当前 P1 AirSim 结论仍是评估状态而非控制动作：mobile recon gimbal 批次显示 bbox 面积改善、`secondary_gimbal_pointing_ok_rate=1.0`，但网络联合 full-view 和稳定注册仍需更多多 seed/N-v-N 批次沉淀长期趋势。

仍需 main runtime bus/episode 写盘接线：

- 在同一 episode 目录持续写出 Blocks、D4、D5、D7、D6 标准化日志。
- 保持统一 episode clock 和实际规模字段。
- main 汇总时把多个 loader 的记录合并到同一个 `MetricsCollector`；D7 real execution 的单次正式指标合并已完成，但多 seed、5v5/N-v-N 和非默认 episode 仍需要持续验证。
- D5 的 terminal consistency、cross-view conflict、duplicate lock、friend hold 和 validation label 需要稳定回灌。
- D4 的 `review_label` 和窗口统计需要稳定回灌，才能计算主动降级必要性/精度。

## 7. PNG 策略

PNG 截图不是指标主线输入。D6 依赖 metadata：

```text
bbox_xyxy
camera_intrinsics
camera_extrinsics
timestamp
resource_id
camera_id
local_track_id
assigned_global_track_id
object_name
truth_label / validation_label
gate outcome
```

`--save-images` 只用于调试视角或人工复核。`visual_png_switch_count` 表示 D7 切换到视觉 PNG/PNG guidance 相关模式，不表示必须保存 PNG 文件。

## 8. 与 OSPA、CLEAR MOT、HOTA/IDF1 的关系

D6 当前默认输出工程可解释指标，而不是完整外部 MOT benchmark：

- 已有本地 POD/FAR/MAR、RMSE、continuity、`id_switch_count`。
- OSPA/GOSPA 只在文档中保留公式和扩展方向，未进入 `EpisodeMetrics.metric_names()`。
- py-motmetrics 隔离 adapter 已基于 `msm-offline-mot-v1` 输出 IDF1/MOTA/MOTP；TrackEval 未接入，HOTA unavailable。
- Stone Soup 未 import，也没有 Track/Detection/GroundTruthPath adapter。

原因：

1. 当前系统评估跨越探测、分配、降级、通信、末端和导引，不只是 MOT benchmark。
2. 默认测试需要轻依赖、可离线、可在 CI 中快速运行。
3. 外部 evaluator 需要稳定帧级 truth-track/detection 匹配表、遮挡/重现规则、IoU/距离门限和依赖版本。

## 9. 批量统计与报告

当前 `ReportGenerator` 输出：

- `episode_metrics.csv`
- `summary_metrics.csv`
- `batch_report.md`
- `plots/detection_metrics.png`
- `plots/tracking_metrics.png`
- `plots/assignment_metrics.png`
- `plots/degradation_metrics.png`
- `plots/terminal_metrics.png`
- `plots/secondary_sensing_metrics.png`
- `plots/communication_metrics.png`
- `plots/guidance_metrics.png`
- `plots/safety_metrics.png`
- `plots/selected_metric_distributions.png`

当前 `AirSimCalibrationReportGenerator` 额外输出：

- `airsim_calibration_records.csv`
- `airsim_calibration_summary.csv`
- `airsim_calibration_summary.json`
- `airsim_calibration_report.md`

该 bundle 的中文 Markdown 显式解释 coverage/funnel/gimbal、projection valid、geometry gate pass、stable registration、not registered、active degradation precision 和 D7 guidance reject reason。D6 只读取 main/D4/D5/D7 写盘结果，不控制 AirSim、camera/gimbal、D4 降级或 D5 注册。

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

偏态或长尾指标，例如 `id_switch_count`、`constraint_violation_count`、`terminal_switch_reject_count`，正式论文/报告应补 bootstrap 或非参数 CI。当前实现主要服务工程回归和批量对比。

## 10. 外部项状态与原因

| 项目 | 当前状态 | 原因 | 缺少条件 |
|---|---|---|---|
| Stone Soup metrics | 未实现直接依赖和 adapter | 保持轻依赖；D1/D2 输出未冻结到 Stone Soup 对象 | 版本锁定、对象映射、测试 fixture、门限合同 |
| OSPA/GOSPA | 未输出字段 | 需要帧级集合序列 | cutoff/order、truth/estimate set、birth/death/遮挡规则 |
| py-motmetrics | 隔离 P2 adapter 已实现 IDF1/MOTA/MOTP | 默认依赖保持轻量 | 冻结 `msm-offline-mot-v1` schema；真实 replay 门限仍需校准 |
| TrackEval/HOTA | 未实现；HOTA unavailable | py-motmetrics 1.4.0 不提供 HOTA | 完整帧级身份评估、重现/遮挡规则、标准格式导出 |
| AirSim 原生 recording parser | 未实现 | 当前 Blocks JSONL 已满足主线；原生 recording schema 差异大 | 样例数据、字段版本、NED/相机/时间轴映射 |
| Live AirSim replay | 未实现且非 D6 目标 | D6 只能离线读日志 | 由 main runtime replay 并导出日志 |
| SCRIMMAGE metrics bridge | 未实现 | 当前无 SCRIMMAGE 输出样例和 schema | ID 映射、通信事件字段、episode clock、批量目录 |

## 11. P1 下一步

1. 多 seed 自动汇总与长期趋势：持续使用 main runtime P1 calibration sweep 生成的 D6 bundle，跟踪 `mobile_recon_gimbal` 与 `fixed_downlook_secondary` 的 coverage、full-view、projection valid、geometry gate pass、registered candidate、stable registration、bbox area、cue/gimbal pointing 指标。
2. D4 主动降级必要性：main/D4 持续写出 `review_label`、trigger/decision timestamp、selected coordinator、coverage cell、pre/post window 和后验 outcome/risk 字段；D6 不从事件名推断必要性。
3. 真实 episode 日志完整性：D4/D5/D7/Blocks 产物持续落到同一 episode clock 和目录，D6 汇总阶段调用 loader 合并；D6 继续只消费日志，不参与控制、重规划或导引。
4. 多 seed 双口径与 actual scale 分组：在 2v2、5v5、N-v-N 和非默认 episode 批量运行中持续保留 `metric_scope=execution/contract`、实际规模字段、seed/scenario 分组、D7 guidance reject reason metadata 和 D4/D5 calibration geometry 字段。

## 12. P2 下一步

1. 定义帧级 truth/detection/track 匹配表。
2. 接入 py-motmetrics 或 TrackEval 作为可选 benchmark。
3. 接入 Stone Soup/OSPA/GOSPA 作为论文级对照。
4. 增加 AirSim 原生 recording parser，仅在 Blocks JSONL 不足时推进。
5. 增加 bootstrap/非参数 CI。
6. 仅在 AirSim 无法回答通信或多机规模问题时，评估 SCRIMMAGE bridge。

## 13. 推荐验证

```bash
pytest -q research_modules/d6_evaluation_metrics/tests
python3 research_modules/d6_evaluation_metrics/scripts/run_batch_example.py --seeds 100
```

文档/空白检查：

```bash
git diff --check -- research_modules/d6_evaluation_metrics subagent_reviews/D6_*
```
