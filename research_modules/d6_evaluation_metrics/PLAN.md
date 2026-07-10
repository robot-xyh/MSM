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
- 日志接口：标准化 JSONL loader、Blocks replay JSONL loader、main episode bus metrics JSON loader、D4 active-degradation CSV loader、D7 intercept/guidance CSV/JSON loader、AirSim calibration 多 seed 汇总 loader。
- 报告接口：`ReportGenerator` 输出 `episode_metrics.csv`、`summary_metrics.csv`、Markdown 报告、分类 PNG 图和 `standard_metric_mapping.csv`；`AirSimCalibrationReportGenerator` 保留原 records/逐 seed summary/Markdown，并新增 `airsim_calibration_cross_seed_aggregate.csv`、`airsim_calibration_paired_comparison.csv`、`airsim_calibration_aggregate.json`、`airsim_calibration_aggregate_report.md`。cross-seed 分组去掉 seed 并保留实际规模，统计键会从 `scenario_version` 移除运行 seed 片段但 records 保留原值；paired comparison 输出 pair/missing seed、delta mean/std、Cohen's dz 和固定 RNG 的 2000 次 bootstrap 95% CI。单一 seed 对仅为 `descriptive_only`，不输出推断 CI/effect size。
- 拦截聚合：calibration record/CSV/summary/cross-seed 直接保留 execution/contract 的成功、collision/range/abort、最小距离、拦截耗时、visual PNG、terminal switch/takeover 和 gate reject 指标。availability gate 要求 `intercept_summary.json`、`control_commands.csv`、显式 summary/pair/status 或正数 D7 execution event 证据；无证据的 read-only episode 写 `None/unavailable`，不把默认零解释为失败。计数输出跨 seed `sum`；四类 outcome 使用实际 target count 输出 opportunity/rate；距离、时间、比例输出分布统计。abort 只从同 scope 的 `intercept_status_counts` 派生，D6 不从失败原因猜测。Outcome 表只显示有证据的行并明确 scope。
- main runtime 接入：`--p1-calibration-sweep` 已在 batch 结束后自动调用 `AirSimCalibrationReportGenerator.write_report_bundle()`，输出 `d6_airsim_calibration/airsim_calibration_records.csv`、`airsim_calibration_summary.csv`、`airsim_calibration_summary.json` 和 `airsim_calibration_report.md`。D6 只消费 sweep 已写盘目录，不启动 AirSim、不控制 camera/gimbal、不参与 D4/D5 降级或配准决策。
- 批量统计：count、mean、sample std、stderr、normal-approximation 95% CI、median、p05、p95。
- 分组统计：通用报告按 `metric_scope`、`seed`、`scenario_group` 和实际 `drone_count/resource_count/target_count/camera_count` 分组；AirSim calibration bundle 按 `metric_scope`、`seed`、`scenario`、`comparison_role`、secondary height/FOV/count、detection backend 和 actual scale/trend 字段分组。

当前依赖保持轻量：Python 标准库、NumPy、matplotlib、pytest。默认测试不依赖 AirSim 服务、Stone Soup、TrackEval、py-motmetrics、SCRIMMAGE、GPU 或网络。

## 3. 已实现指标

### 3.1 EpisodeMetrics 与规模字段

`EpisodeMetrics` 显式包含：

```text
episode_id
seed
scenario_group
batch_seed
metric_scope
drone_count
resource_count
target_count
camera_count
duration
mission_outcome
success_reason
failure_reason
eval_priority
implementation_status
evidence_path
scenario_version
standard_mapping_version
standard_metric_family_summary
module_duration_ms
loop_latency_ms
record_latency_ms
cpu_budget_utilization
gpu_budget_utilization
performance_budget_violation_count
metadata
```

规模口径：

- 优先读取 `truth_summary` 顶层或 `truth_summary["scenario"]` 中的 `drone_count/resource_count/target_count/camera_count`。
- Blocks replay 从 `resources`、`truth_objects`、`cameras` 计算规模。
- 缺失时从 assignment、terminal、event、link metadata 中推断资源、目标和相机集合。
- `drone_count` 缺失时默认等于 `resource_count`。
- `2v2/5v5` 只保留为 baseline 场景名，不能作为分母或规模推断来源。

测试已覆盖 `episode_id/scenario.name` 含 `5v5`，但实际规模为 `3/3/4/6` 的情况，D6 按实际字段输出。

### 3.1.1 Mission outcome、root cause、性能和 EVAL tracking

P0-A/P0-C 字段已进入 D6 episode 主线：

```text
mission_outcome in {success, partial, failed, aborted}
success_reason
failure_reason
root_cause
top_failure_causes
eval_priority
implementation_status
evidence_path
module_duration_ms
loop_latency_ms
record_latency_ms
cpu_budget_utilization
gpu_budget_utilization
performance_budget_violation_count
```

实现口径：

- `mission_outcome` 优先消费 `truth_summary` 或 event metadata 中显式写盘的 outcome；缺失时基于 intercept success、required success count、abort/runtime exception、安全事件和部分进展被动派生。
- `success_reason`、`failure_reason` 优先使用上游写盘原因；缺失时由 D6 根据指标摘要生成简短解释。
- `top_failure_causes` / `root_cause` 从 records/metadata 和 D6 已计算指标派生，覆盖 tracking、assignment、terminal_gate、guidance、coverage、runtime_exception、communication、safety、performance；D6 不做控制链路因果推断或回写。
- 性能监测消费上游写盘的 module duration、loop latency、record latency、CPU/GPU budget utilization 和 budget violation；缺失时输出 0 和 metadata placeholder，便于 main 报告保持 schema 稳定。
- `eval_priority`、`implementation_status`、`evidence_path` 用于 main 报告追踪 P0/P1 状态，优先来自 truth_summary/metadata。

### 3.1.2 标准化评估映射最小版

P0-A 标准化评估映射最小版已实现，版本固定为 `cuas-standard-map-v1`。D6 只建立离线报告映射，不引入外部认证流程，也不改变 D1-D7/main runtime 控制链路。

映射最小字段：

```text
engineering_metric
standard_metric_family
standard_sources
implementation_status
evidence_requirement
```

覆盖的标准指标族：

```text
mission/root cause
detection
tracking
assignment
degradation
terminal
communication
guidance/intercept
safety
performance
reproducibility/evidence
```

实现口径：

- `standard_mapping.py` 保存 `COURAGEOUS/MDPI/OCEF -> EpisodeMetrics` 的静态映射表。
- `MetricsCollector.compute_episode()` 从 `truth_summary` 或 event metadata 读取 `scenario_version`，固定写入 `standard_mapping_version=cuas-standard-map-v1`，并在 metadata 中保留 `standard_metric_families`、`standard_metric_family_summary` 和 `standard_mapping` 摘要。
- `EpisodeMetrics.metric_names()` 不包含 `scenario_version`、`standard_mapping_version`、`standard_metric_family_summary`，避免污染数值统计。
- `ReportGenerator.write_episode_csv()` 输出这三个非数值字段；`write_markdown_report()` 在 `EVAL Tracking` 后输出 `Standard C-UAS Mapping` 表；`write_standard_mapping_csv()` 输出 `standard_metric_mapping.csv`。
- AirSim calibration records/summary 也保留 `scenario_version`、`standard_mapping_version`、`standard_metric_family_summary`、`evidence_path`、`trend_key`、`secondary_height_bucket`、`metric_scope` 和 actual scale 字段，便于 main 长期趋势报告复用。

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
active_degradation_precision
unnecessary_active_degradation_count
passive_failover_count
secondary_node_takeover_count
secondary_reassignment_count
d4_reassign_pending_count
distributed_fallback_count
failover_active_window_delta_s
```

当前识别来源包括 `EventRecord.event_type`、`metadata.mode/degradation_mode`、`metadata.action`、`metadata.assignment_phase`、`metadata.fallback_type`、D7 reject reason 和 D4 CSV loader。`metadata["trigger_reason"]` 等触发原因会进入 `EpisodeMetrics.metadata["trigger_reason_distribution"]`。

已补 P1 最小主动降级必要性口径：

```text
active_degradation_precision
unnecessary_active_degradation_count
```

D6 只在 D4/main 写入可分类的 `review_label`、`active_degradation_necessary`、`post_window_outcome` 或 pre/post risk/window 后验字段时计入 precision 分母；缺少标签时 `active_degradation_label_count=0` 且 precision 输出 unavailable/JSON `null`，只保留 `active_degradation_count`。

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

### 3.7 二级视角与侦察云台指标

```text
secondary_network_joint_full_view_frame_rate
secondary_network_mean_coverage_ratio
secondary_visible_target_union_ratio
secondary_single_camera_full_view_frame_rate
secondary_detect_count
projection_valid_rate
geometry_gate_pass_rate
registered_candidate_count
stable_cross_view_registration_count
not_registered_count
cross_view_association_count
secondary_detect_available_but_not_registered_count
cue_pointing_error_count / mean_deg / rmse_deg / max_deg
gimbal_pointing_error_count / mean_deg / rmse_deg / max_deg
```

当前来源：

- `EventRecord`/`LinkRecord.metadata` 中的 `secondary_node_type/node_type/camera_node_type`，规范化为 `fixed_downlook_secondary`、`mobile_recon_gimbal` 或 `secondary_network`。
- main/D4/D5 写盘的覆盖/FOV 记录，例如 `covered_target_ids`、`covered_target_count`、`coverage_ratio`、`joint_full_view`、`single_camera_full_view_count`。
- D5 跨视角事件，例如 `d5_cross_view_association`、`cross_view_association_count`、`multi_view_consensus_result`。
- D5 注册缺失事件，例如 `secondary_detect_available_but_not_registered_count`、`detect_available=True` 且 `d5_registered=False`。
- D5 detect-to-registration 校准字段，例如 `projection_valid_rate`、`geometry_gate_pass_rate`、`registered_candidate_count`、`stable_cross_view_registration_count`、`not_registered_count`，以及 reject/outcome reason `not_all_targets_visible`、`network_union_incomplete`、`projection_invalid`、`geometry_gate_rejected`、`stability_window_failed`、`no_global_binding`、`stale_or_missing_recon_cue`、`registered_to_global_track`。
- cue/gimbal 指向误差字段，例如 `cue_pointing_error_deg/rad`、`gimbal_pointing_error_deg/rad`、`pointing_error_deg/rad`。

归一化口径：

- network joint full-view 先按 frame 聚合二级网络覆盖集合，再除以实际 target count，不从 `2v2/5v5` 场景名推断目标数。
- mean coverage ratio 使用实际 target count；只有日志显式给出 per-frame ratio 时才直接消费 ratio。
- single-camera full-view rate 使用 camera-frame 分母；分母来自日志显式 camera frame count 或实际 camera count，而不是场景名。
- `EpisodeMetrics.metadata["secondary_sensing_node_type_metrics"]` 保留 node-type 级指标，报告中对比固定俯视二级节点和机动高空侦察云台节点。

D6 只消费 main/D4/D5 写盘日志，不下发 cue、不控制云台、不触发接管/重分配。

2026-07-08 `p1_d4d5_mobile_recon_20260708_055948*` 是历史 mobile recon stress 批次，可作为 D6 已能消费 `mobile_recon_gimbal`、coverage、bbox、gimbal 和 funnel 字段的旧证据。

当前最新 P1 registration calibration v2 已验证 D6 侧消费口径：

- 输出目录：`research_modules/airsim_runtime/outputs/p1_d4d5_registration_calibration_runtime_v2_20260708*`。
- D6 bundle：`d6_airsim_calibration/airsim_calibration_records.csv`、`airsim_calibration_summary.csv`、`airsim_calibration_summary.json`、`airsim_calibration_report.md`。
- 场景：single seed，3 case；height 200 m，FOV 110 deg，secondary_count 3，detection backend 为 `simGetDetections`。
- 关键结果：`projection_valid_rate=1.0`；`geometry_gate_pass_rate≈0.474`；stable cross-view registration 为 51/55/53；cross-view association 为 4/4/5；degradation case `not_registered_count=35/35`；full-view mean≈0.048，best≈0.143；coverage mean≈0.771。
- 结论：D6 报告链路已能输出 projection/gate/stable registration/not-registered/funnel/D7 reject；剩余是更多真实 AirSim 多 seed/N-v-N 数据和 review labels，用于形成长期趋势。D6 记录该结论为离线评估状态，不参与 D4/D5/D7 控制或云台调度，也不从 `2v2/5v5` 场景名推断规模。

### 3.8 通信指标

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

### 3.9 D7 gate、visual PNG switch 与拦截统计

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

### 3.10 安全指标

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
| `load_main_episode_bus_metrics()` / `load_main_episode_bus_metric_files()` | `main_episode_bus_metrics.json`、`main_episode_bus_contract_metrics.json` | 已实现并测试 | 只还原已写盘 `EpisodeMetrics`；不运行 AirSim、不合并控制结果 |
| `load_d4_active_degradation_decisions()` | D4 active-degradation CSV | 已实现并测试 | 只消费已写盘 review/window 字段；有 label/后验字段才计算必要性，不从事件名判定 |
| `load_d7_intercept_outputs()` | `control_commands.csv`、`intercept_summary.json` | 已实现并测试 | 只离线评估 D7 输出，不发控制 |
| `load_d7_guidance_timeseries()` | `guidance_records.csv`、`guidance_summaries.json`、D7 control/intercept 输出 | 已实现并测试 | 保留 D4/D5 state、plan/version、guidance law 和 reject reason metadata |
| `load_airsim_calibration_records()` / `AirSimCalibrationReportGenerator` | AirSim batch/seed/case 目录中的 `d4d5_stress_metrics.json`、`airsim_blocks_summary.json`、`main_episode_bus_metrics.json`、`main_episode_bus_contract_metrics.json` | 已实现并测试 | 只读已写盘文件；按真实 count 字段、settings FOV 和 metadata 分组，不从场景名推断规模 |

## 5. 已完成接入与 main runtime bus 剩余条件

当前 D6 已能消费 D4/D5/D7 产物。完整 integrated episode metrics 仍取决于 main runtime 的写盘和汇总接线，但 D7 真实执行结果的 main/orchestrator 合并已经完成一条主线。

截至 2026-07-07 的已完成接线：

- 真实 AirSim D7 执行后，main/orchestrator 从 `control_commands.csv` 与 `intercept_summary.json` 提取执行结果并合并进正式 `main_episode_bus_metrics.json`。
- 执行前的合同检查口径保留为 `main_episode_bus_contract_metrics.json`，用于诊断 D3/D4/D5/D7 gate 与合同拒绝，不再覆盖正式执行指标。
- 正式指标中的 `intercept_success_count`、`collision_intercept_count`、`range_intercept_count`、`terminal_contract_reject_count`、`gate_reject_count`、`guidance_law_counts` 等以执行后合并结果为准。
- D6 仍然只消费日志/CSV/JSON/metrics 文件；不订阅 runtime bus，不触发 replan、failover 或 guidance。

已具备 D6 侧消费能力：

- D4：可读取 active-degradation CSV；可从事件 metadata 中识别 active/passive、secondary takeover/reassignment、distributed fallback、D4 reassign pending、触发原因、review label、trigger/decision timestamp、selected coordinator、coverage cell 和 pre/post window 字段。
- main bus：可读取正式 execution `main_episode_bus_metrics.json` 与 raw contract `main_episode_bus_contract_metrics.json`，保留 `metric_scope`、seed/scenario/实际规模字段、D7 guidance/intercept 指标和 reject reason metadata。
- D5：可通过 `TerminalRecord`、terminal/multi-view event、Blocks bbox/camera metadata 计算末端准确率、ID switch、lock、歧义、friend hold、多视角一致和冲突；可消费 cross-view association、secondary detection available but not registered 和 cue/gimbal pointing error metadata。
- D7：可读取 control/guidance/intercept CSV/JSON，计算 gate、visual PNG switch、terminal takeover、模式切换、拦截结果和 reject metadata。
- Blocks CV：可从 `blocks_frames.jsonl` 与 `blocks_sensor_observations.jsonl` 构建 truth summary、规模字段、视觉检测、terminal records、video/bbox link records 和通信链路样本。

P0/P1 状态：

- 无 P0 blocker。D6 离线主线、`id_switch_count` 显式输出、实际规模归一化、main bus metrics loader、D4/D5/D7 写盘消费和二级侦察指标消费均已具备。
- 剩余 P1 不是 D6 在线控制职责，而是真实 episode 写盘、自动汇总和长期趋势报告的持续性要求：

- 真实 episode 需要持续写出 D4 `review_label`、`trigger_timestamp`、`decision_timestamp`、`selected_coordinator`、`coverage_cell` 和固定 pre/post window 字段；D6 已能消费这些字段并计算主动降级必要性/精度。
- 同一 episode 目录仍需稳定聚合 Blocks、D4、D5、D7 和 D6 标准化 JSONL/CSV/JSON，并保持同一 episode clock；D6 loader 本身不会扫描 runtime bus、启动 AirSim 或补写上游日志。
- D5 terminal association、cross-view conflict、duplicate lock、friend overlap hold、validation label 等真实 AirSim 事件应持续进入 D6 可读记录；D6 已有指标和 Blocks metadata 基线。
- AirSim 报告已能把 `mobile_recon_gimbal` / `fixed_downlook_secondary` 的 50m/200m coverage、detect-to-registration funnel、coverage funnel、baseline/enhanced、bbox 和 cue/gimbal 指向指标纳入多 seed 自动汇总；长期趋势仍需要 main 持续产出更多 5v5/N-v-N 批次。
- main runtime P1 D4/D5 calibration sweep 已自动调用 D6 `AirSimCalibrationReportGenerator` 生成标准 records/summary/Markdown bundle；D6 当前重点是保持多 seed 自动汇总口径稳定，沉淀 coverage/funnel/gimbal、projection/gate/stable registration、not-registered、D7 guidance reject 和 `trend_key/evidence_path` 长期趋势，统计 active degradation precision，并按真实 `drone_count/resource_count/target_count/camera_count` 做 actual scale 分组。
- 多 seed、5v5/N-v-N 和非默认 episode 需要继续保持 `metric_scope=execution/contract` 双口径，正式指标采用执行后 metrics，contract metrics 仅用于诊断；D6 已能直接读取两类 main bus metrics JSON，报告分组已按 `metric_scope + seed + scenario_group + scale` 实现，不从场景名推断规模，并在 metadata/Markdown 中保留 reject reason 分布。

2026-07-10 D6 owner 验收结论：D6 全量测试为 `48 passed`。execution/contract 分离、各自 evidence path、拦截证据 availability gate、read-only episode 的 `unavailable` 处理、cross-seed aggregate、严格 paired comparison 和确定性 bootstrap CI 均已完成。现有 2v2 10-seed execution 结果为 `18/20`；该结果用于证明报告链路和统计口径，不把 D6 变成控制模块。后续不再把“补充同一批拦截字段”列为开发任务，只做 schema 回归和新场景数据验收。

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

- `episode_metrics.csv`：每个 episode 一行，包含规模字段、`scenario_version`、`standard_mapping_version`、`standard_metric_family_summary`、所有 `EpisodeMetrics.metric_names()` 和 metadata JSON。
- `summary_metrics.csv`：全局与 `metric_scope + seed + scenario_group + scale` 分组统计。
- `standard_metric_mapping.csv`：输出固定版本 `cuas-standard-map-v1` 的标准映射行，字段为 `engineering_metric/standard_metric_family/standard_sources/implementation_status/evidence_requirement`。
- Markdown 报告：中文说明、规模范围、场景分组、`Standard C-UAS Mapping` 表、固定俯视二级节点 vs 机动侦察云台节点对比表、汇总表、reject reason 分布和图表链接。
- PNG 图表：`detection`、`tracking`、`assignment`、`degradation`、`terminal`、`secondary_sensing`、`communication`、`guidance`、`safety` 和 selected metric distributions。
- AirSim calibration bundle：旧 records/逐 seed summary 文件保持不变；新增 cross-seed aggregate CSV、paired comparison CSV、aggregate JSON/Markdown。main 必须显式写 `comparison_role=baseline|enhanced`；配对键包含稳定 `scenario_group`、去除运行 seed 参数后的 `scenario_version`、实际 N/M/camera count、几何、backend 和 seed，case_name 只审计。active-degradation count/precision/label_count/unnecessary 优先消费 d4d5 stress 显式字段，再 fallback main metrics。

2026-07-10 的 2v2 execution 回灌复核固定以下读取优先级：正式 `main_episode_bus_metrics.json` 为执行口径，`main_episode_bus_contract_metrics.json` 为合同诊断口径，`airsim_blocks_summary.integrated_result.metrics` 仅是可能过时的历史快照，不进入 D6 calibration record。当前实测正式 execution 为实际规模 `2/2/2/2`、成功拦截 `2/2`、视觉 PNG 切换 3 次；旧 Blocks 快照仍为 `3/3/2/0`，该上游摘要一致性由 main runtime 负责。

10-seed 真实验收使用 `p1_gap_closure_2v2_multiseed_20260710_seed001..010`：full-flow execution cross-seed 行完整包含十项拦截指标，并直接输出 `intercept_success_count sum=18`、`opportunity_count=20`、`rate=0.9`，collision/range/abort 为 `18/0/2`。验收报告由 D6 离线读取 summaries 生成，不启动 AirSim、不发控制。

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

1. 长期场景库和 CI 趋势：由 main 提供稳定的 `scenario_id/version`、tags、difficulty、expected failure modes、actual scale、test matrix 和 evidence path；D6 生成跨提交趋势、阈值回归和证据完整性摘要，不能只保留一次性 AirSim 报告。
2. CV 5v5 的 D1-D3 联合聚合：在同一 episode clock 下汇总 D1 detection/fusion/latency/covariance、D2 association/continuity/ID switch 和 D3 assignment/version/hysteresis 指标，形成从感知到分配的 funnel。D6 只消费 main 写盘的稳定 schema，不从 truth name、场景名或后验结果重建在线决策。
3. YOLO/MOT 资源预算报告：消费 D5 写盘的 detection backend、模型/权重版本、输入分辨率、目标像素尺度、inference latency、throughput、CPU/GPU/内存利用率、drop/fallback 和 detection/MOT 质量字段，形成 accuracy-latency-budget 对照。D6 不加载 `best.pt`、不运行 YOLO，也不把缺失性能样本记为 0。
4. COURAGEOUS/MDPI/OCEF 完整标准化报告：在 `cuas-standard-map-v1` 基础上补测试阶段、复现纪律、evidence index、场景覆盖矩阵、限制条件和外部审计说明，并把 D1-D7 指标映射到统一中文报告模板。
5. 长期多 seed 对照：现有 cross-seed aggregate、严格 paired comparison、effect size 和 bootstrap CI 只需用真实成对 5v5/N-v-N 批次持续验收；missing seed、单 pair、无 review label 和 read-only unavailable 继续保持不可推断状态。
6. D4/D5 长期趋势与真实标签：持续跟踪 coverage/funnel/gimbal、projection/gate/registration、D7 reject 和 active-degradation review/window；`active_degradation_precision` 只使用 main/D4 写盘的真实 review label 或后验 outcome/risk。
7. execution/contract/evidence availability 已完成，后续仅作为 schema 回归项：正式 execution、raw contract、各自 evidence path 和 availability 状态不得互相覆盖，不再重复扩展同义拦截字段。

## 9. P2 下一步

1. 帧级匹配表：定义 D1/D2/D5 的 frame-level truth/detection/track export，包含 timestamp、truth_id、global/local track ID、position/IoU/distance、occlusion/reappearance 状态。
2. 外部 MOT 对照：优先做 TrackEval 或 py-motmetrics adapter，作为可选 benchmark，不替换 D6 本地指标。
3. Stone Soup/OSPA 对照：在 D1/D2 对象映射和版本锁定后接入 Stone Soup metrics 与 OSPA/GOSPA。
4. Bootstrap/非参数 CI：在真实多 seed 数据规模足够后，为偏态指标提供可选统计方法。
5. SCRIMMAGE bridge：仅当 AirSim 多机规模或通信建模不足以回答实验问题，并且已有真实 SCRIMMAGE 样例和 schema 时作为 P3 可选项推进。
6. AirSim 原生 recording parser：只有在 Blocks JSONL 不能满足评估需求时，才补通用 recording parser。

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
- 明确 D4/D5/D7 AirSim 产物的 D6 侧 loader 已实现；D7 real execution metrics 已由 main/orchestrator 合并进正式 `main_episode_bus_metrics.json`，raw contract metrics 保留为诊断文件。
- 明确 Stone Soup、AirSim replay、SCRIMMAGE 等开源/外部项的实际未实现状态、原因和缺少条件。
