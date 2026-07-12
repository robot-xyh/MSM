# D6 Evaluation Metrics

D6 是 MSM 的离线评估与报告模块。它只消费已经写盘的日志、CSV、JSON/JSONL 和仿真真值，输出 `EpisodeMetrics`、CSV、Markdown 报告和 PNG 图表；不参与 D1-D7 的实时控制链路，不生成任务、分配、导引、授权、火控、毁伤或自动处置动作。

## 2026-07-11 P1 统一验收与 P2 adapter

D6 已消费 main episode bus 的 `d4_coalition_commit_state`，并从事件或扩展 `CoalitionRecord` 聚合 epoch、plan/coalition version、lease、required/acked members、commit state/reason、ACK latency、timeout、aborted/reconfiguring 以及 secondary/distributed commit。相同 generation 的 `committed -> executing` 转换只计一次有效 commit，状态与原因保留在 metadata audit。

终端验收现显式分为 `contract_allowed`、`control_allowed`、`mode_switched` 和 `physical_intercept`。`physical_intercept_count` 只接受 D7 intercept summary、pair status 或带物理状态的 control evidence；只有 ComputerVision `d7_guidance_record` 时保持 `None/unavailable`，不会把状态闭环计为物理拦截。physical 层进一步拆成 `pair_physical_success_count/rate`、`target_intercept_success_count/rate` 和 `coalition_completion_count/rate`：pair 分母只含 active assigned pair，target 以任一 participating pair 成功为准，coalition 必须有全部 required primary 的 arrival window 与窗口内物理成功证据，三者不共用分母。`collision_intercept` 与 `range_intercept` 都属于 physical success。

`intercept_summary.json` 的物理判据审计保留 `intercept_radius_m`、`intercept_distance_frame`、`intercept_distance_dimension` 和 `intercept_success_criteria_version`；当前 5 m 验收要求 NED 3D Euclidean。缺 required-primary arrival window 时 coalition 指标为 unavailable，不用 pair/target 成功回填。detect/coast 诊断新增 `detection_acquisition_timeout_count`、`image_kf_predict_count`、`blind_push_count`、`visual_reacquisition_count`、`terminal_visual_lost_after_coast_count`、`truth_identity_online_use_count`，只读取 summary/control record 或从带明确 detect/coast 状态的逐 pair 时序离线推导。

隔离式 P2 `py-motmetrics` adapter 已实现冻结 `msm-offline-mot-v1` schema，输出 IDF1/MOTA/MOTP。HOTA 在 `motmetrics 1.4.0` 中不受支持，固定输出 `None/unavailable`；可选依赖缺失时同时输出兼容 `reason` 和显式 `unavailable_reason`。依赖只在 `/home/linux/.cache/msm-p2-venv` 验证，默认 requirements 和默认测试依赖不变；offline truth 禁止回流在线链路。

## 2026-07-11 M 对 N 离线指标合同

最新实测基线来自 `p1_p2_validation_20260711`：CV 10 seeds 中 8/10 形成 T001 双 primary 同帧共识与授权证据，全部 seed 的 IDSW 和错误重复锁为 0；secondary 与 distributed 正例均为 executing 3/3，missing-ACK 负例为 aborted 2/3。CV 的 `control_allowed_count=0`、`physical_intercept_count=None` 正确表示未执行物理控制。SimpleFlight 10 seeds 均保持 4 bindings、3 active + 1 standby，但 30 个 active pair 中 0 命中，包含 24 detection timeout 和 6 timeout；15 s、`control_dt=0.5 s` 仅为诊断配置。

D6 已实现中心化 M 对 N 的兼容日志与离线聚合。新增 `TargetDemandRecord`、`CoalitionRecord`、`ArrivalRecord`，并在 `AssignmentRecord`、`TerminalRecord` 保留 `coordination_mode`、`coalition_id/version/state`、`member_role`、`wave_id`、`required_resource_count`、`demand_assigned/shortfall/complete`、arrival window 和 `minimum_member_separation`。标准 JSONL 支持 `target_demand/coalition/arrival`，collector writer 可 round-trip；旧日志缺少这些字段时只对 duplicate 判定使用明确的 legacy `k=1`，其余新增指标保持 `null/unavailable`。

`EpisodeMetrics` 已接入 demand micro/macro、unmet slots、over-support、formation/reconfiguration、simultaneous arrival/common-window、sequential wave、hybrid primary/reserve、planned/authorized/erroneous lock、same-resource lock continuity、member lifecycle/digest/stale、messages/bytes/rounds/latency、minimum separation/collision exposure、geometry rejection、canonical duplicate/cross-node IDSW/common-information rejection。`duplicate_terminal_lock_count` 保留通用“同一 timestamp+target 出现多个 resource”计数，不再由 `erroneous_duplicate_lock_count` 覆盖；后者仅计 legacy `k=1`、当前 coalition/assignment 版本冲突或超过 `required_resource_count`。同一 resource 跨帧持续锁定只进入 `same_resource_lock_continuity_count`，授权 coalition 内同帧多资源锁进入 `authorized_cooperative_lock_count`。

探测三项要求同时存在 `truth_timestamps` 机会集合与检测/航迹到 truth 的离线配对裁决。配对证据可以是落入 truth pair 集合的 `TrackRecord.truth_id`，也可以是显式 `offline_detection_match/offline_track_truth_match/offline_detection_miss/offline_missed_detection` 事件。仅有 truth opportunity 列表、所有 track 均为 `truth_id=None` 且无显式 match/miss 时，`detection_probability/missed_detection_rate/false_alarm_rate=None` 且 `metric_availability.status=unavailable`。可用时按 pair 集合求命中和漏检；`truth_id=None` 的 center track 不自动计虚警。

`center_replan_request_created/deduplicated/ack_no_change/applied/expired` 已接入请求、去重、no-change、applied、expired、pending dwell 总时长和 no-change/applied 收敛均值。D6 优先消费 `request_id/requested_at/resolved_at/pending_dwell_s`，并在 metadata 审计保留 target、coalition/version、risk signature 和 resolved plan/version。无这些事件时所有 replan 指标为 `None/unavailable`。

每个新增指标在通用 `metric_availability` 中记录 `status/reason/numerator/denominator`，M 对 N 子集继续保留兼容的 `m_to_n_metric_availability`。数值 `0` 仅表示证据完整且事件确为零；缺证据为 JSON/CSV 空值和 `unavailable`；路线无此概念为 `not_applicable`。batch summary 分别输出可用、unavailable 和 not-applicable 样本数，并继续按实际 `drone_count/resource_count/target_count/camera_count` 分组。

## 2026-07-10 P1 扩展

本轮已补齐以下离线评估接口，不运行 AirSim：

- 二级接管生命周期：统计 `registration_usable`、`takeover_ready`、`pending_secondary_plan`、`secondary_plan_active` 驻留时间、ready-to-active latency、fallback、lease expiry 和 stale-plan reject。没有显式 lifecycle event 时字段为 `None/unavailable`，不写成 0。
- D5 YOLO/MOT：统计 detection recall、local-ID continuity、cross-view registration rate、pipeline latency、CPU/GPU budget utilization 和 budget violation。recall/continuity 只读取事件中嵌套的 `offline_truth`；在线顶层出现 `truth_id/actor_name/object_name/segmentation_id` 会计入 `online_truth_field_violation_count`。
- 四导引律同 seed 对照：`GuidanceLawComparisonReportGenerator` 对 `pure_pursuit/radar_pn/png_vm/png_ttc` 按相同 `scenario_group/version/seed/actual scale` 配对，输出 CSV、JSON、中文 Markdown 和差值曲线。D6 不选择导引律。
- 场景库：`ScenarioLibrary` 输出带 tags、difficulty、expected failure modes、parameters 和 seed matrix 的 JSON/CSV/Markdown；`scenario_group` 保持跨 seed 稳定，在线 truth policy 固定为 `forbidden`。
- `ReportGenerator.write_plots()` 新增 `visual_perception_metrics.png`；AirSim calibration record/cross-seed 表同步携带 lifecycle、视觉预算、tracker backend 和 experiment guidance law。

main 需要按事件写盘以下字段：

```text
d4_secondary_readiness:
  timestamp, readiness_state
d4_secondary_plan_state:
  timestamp, plan_state, plan_id, plan_version, owner, lease_id, lease_expiry_timestamp
secondary_takeover_fallback / secondary_lease_expired / stale_plan_reject:
  timestamp, reason, plan_id, plan_version, owner
d5_yolo_mot_frame:
  timestamp, camera_id, detection_backend, tracker_backend,
  cross_view_candidate_count, cross_view_registered_count,
  detector_latency_ms, tracker_latency_ms, pipeline_latency_ms,
  cpu_budget_utilization, gpu_budget_utilization,
  latency_budget_ms, cpu_budget_utilization_limit, gpu_budget_utilization_limit,
  offline_truth.{visible_truth_count,matched_truth_count,truth_to_local_track_id}
episode metadata:
  experiment_guidance_law, scenario_group, scenario_version, seed,
  drone_count, resource_count, target_count, camera_count
```

## 当前能力

已实现的核心数据模型：

- `EpisodeMetrics`：单 episode 标量指标对象，包含 `mission_outcome`、`success_reason`、`failure_reason`、`eval_priority`、`implementation_status`、`evidence_path`、`scenario_version`、`standard_mapping_version`、`standard_metric_family_summary`、`metric_scope` 和规模字段 `drone_count/resource_count/target_count/camera_count`。
- `TrackRecord`：探测和跟踪记录，保留 `global_track_id`、`truth_id`、位置、真值位置、协方差摘要和来源。
- `AssignmentRecord`：分配快照，保留 `plan_id`、`version`、资源、目标、授权状态和评估侧真值标签。
- `EventRecord`：通用事件记录，用于降级、安全、D5/D7 gate、通信元数据等。
- `LinkRecord`：跨节点通信记录，支持 latency/drop/out-of-order/stale/video metadata/bbox delivery。
- `TerminalRecord`：末端配准记录，支持局部视觉 ID、锁定、歧义、友方 overlap hold 和正确性标签。

已实现的指标族：

- 探测：`detection_probability`、`false_alarm_rate`、`missed_detection_rate`。
- 跟踪：`track_rmse`、`track_continuity`、强制显式保留的 `id_switch_count`。
- 分配：`duplicate_assignment_count`、`unassigned_high_threat_count`。
- 降级：`failover_time`、`consensus_rounds`、`degraded_completion_rate`、`active_degradation_count`、`active_degradation_precision`、`active_degradation_label_count`、`unnecessary_active_degradation_count`、`passive_failover_count`、`secondary_node_takeover_count`、`secondary_reassignment_count`、`d4_reassign_pending_count`、`distributed_fallback_count`、`failover_active_window_delta_s`。precision 只以可分类 review label 样本为分母；`active_degradation_label_count=0` 时输出 unavailable/JSON `null`，不伪装成 0 精度。
- 末端：`terminal_association_accuracy`、`terminal_id_switch_count`、`ambiguous_fov_event_count`、`friend_overlap_hold_count`、`time_to_terminal_lock`、`terminal_lock_count`、`multi_view_consensus_rate`、`cross_view_conflict_count`、`duplicate_terminal_lock_count`。
- 二级视角/侦察：`secondary_network_joint_full_view_frame_rate`、`secondary_network_mean_coverage_ratio`、`secondary_visible_target_union_ratio`、`secondary_single_camera_full_view_frame_rate`、`secondary_detect_count`、`projection_valid_rate`、`geometry_gate_pass_rate`、`registered_candidate_count`、`stable_cross_view_registration_count`、`not_registered_count`、`cross_view_association_count`、`secondary_detect_available_but_not_registered_count`、`cue_pointing_error_*`、`gimbal_pointing_error_*`。
- 通信：`cross_node_latency_ms`、`message_drop_rate`、`out_of_order_count`、`stale_track_update_count`、`video_metadata_delivery_rate`、`bbox_delivery_rate`、`consensus_latency_s`。
- D7 gate 与拦截统计：`camera_quality_gate_pass_rate`、`los_quality_gate_pass_rate`、`maneuver_margin_gate_pass_rate`、`terminal_switch_allowed_rate`、`visual_png_switch_count`、`terminal_takeover_rate`、`terminal_switch_reject_count`、`mode_switch_count`、`terminal_contract_reject_count`、四层 execution funnel、pair/target/coalition 三层 physical success、detect/coast 六项诊断、`collision_intercept_count`、`range_intercept_count`、`time_to_intercept_s`、`min_range_m`、`gate_reject_count`。
- 安全：`constraint_violation_count`、`human_override_count`。
- 任务结果/root cause：每个 episode 输出 `mission_outcome=success/partial/failed/aborted`、`success_reason`、`failure_reason`，metadata 保留 `root_cause`、`top_failure_causes`、`failure_cause_scores` 和 `failure_cause_details`；根因只从已写盘 records/metadata 和 D6 指标被动派生，覆盖 tracking、assignment、terminal_gate、guidance、coverage、runtime_exception、communication、safety、performance 等类别。
- 性能监测：`module_duration_ms`、`loop_latency_ms`、`record_latency_ms`、`cpu_budget_utilization`、`gpu_budget_utilization`、`performance_budget_violation_count` 进入 summary；metadata 保留 module/loop/record latency 分布和 CPU/GPU budget 占位状态。
- 标准化评估映射最小版：`cuas-standard-map-v1` 已把 `COURAGEOUS/MDPI/OCEF -> EpisodeMetrics` 映射落到 D6。映射字段为 `engineering_metric`、`standard_metric_family`、`standard_sources`、`implementation_status`、`evidence_requirement`，覆盖 mission/root cause、detection、tracking、assignment、degradation、terminal、communication、guidance/intercept、safety、performance、reproducibility/evidence。`MetricsCollector.compute_episode()` 在 metadata 中写入 `standard_mapping_version`、`standard_metric_families`、`scenario_version` 和 `standard_mapping` 摘要；`ReportGenerator.write_standard_mapping_csv()` 可输出 `standard_metric_mapping.csv`，Markdown 报告在 `EVAL Tracking` 后输出 `Standard C-UAS Mapping` 表。

D2/D6 的硬规则仍然保留：`id_switch_count` 必须显式输出，不能被综合准确率隐藏。

## 规模归一化

D6 按实际 `drone_count/resource_count/target_count/camera_count` 归一化和分组。规模优先来自 `truth_summary` 或 Blocks replay 的资源、目标和相机字段；缺失时才从已记录的资源、目标、终端和相机元数据推断。`2v2`、`5v5` 只作为 baseline 场景名，不能用于推断算法规模或报告分母。二级网络 full-view/coverage 和单相机 full-view 指标使用实际 target/camera count 或日志中显式记录的实际计数作为分母。报告会按 `metric_scope`、`seed`、`scenario_group` 和实际规模字段分组，区分 execution metrics 与 contract metrics。

## AirSim 与 Runtime 输入

D6 已有离线 loader，但不直接连接 AirSim：

- `load_blocks_replay_jsonl()` 读取 main runtime 写出的 `blocks_frames.jsonl` 和可选 `blocks_sensor_observations.jsonl`。
- `load_main_episode_bus_metrics()` / `load_main_episode_bus_metric_files()` 读取 main runtime 写出的 `main_episode_bus_metrics.json` 与 `main_episode_bus_contract_metrics.json`，还原为 `EpisodeMetrics`，保留 execution/contract 口径、seed/scenario/实际规模字段和 metadata 分布。
- `load_d4_active_degradation_decisions()` 读取 D4 主动降级 CSV，并离线消费 `review_label`、trigger/decision timestamp、selected coordinator、coverage cell 和 pre/post window 字段。
- `load_d7_intercept_outputs()` / `load_d7_guidance_timeseries()` 读取 D7 `control_commands.csv`、`intercept_summary.json`、`guidance_records.csv`、`guidance_summaries.json`。
- `load_episode_log_jsonl()` 读取 D6 标准化 dry-run JSONL。
- `load_airsim_calibration_records()` / `AirSimCalibrationReportGenerator` 自动扫描 main runtime 已写盘的 `d4d5_stress_metrics.json`、`airsim_blocks_summary.json` 和 `main_episode_bus/*.json`，保留旧的逐 seed `GROUP_FIELDS`/CSV，并新增去 seed、包含实际规模的 cross-seed aggregate。records 保留原始 `scenario_version`，统计键只移除其中 `seed1/seed2/...` 这类运行参数，防止真实多 seed 被拆成单样本组；baseline/enhanced 仍要求相同稳定 `scenario_group`、规范化版本、实际 `drone_count/resource_count/target_count/camera_count`、几何、detection backend 和 seed。case-specific `scenario/case_name` 只保留审计。active-degradation 显式标注优先读取 d4d5 stress metrics，再 fallback main `EpisodeMetrics`。

这些 loader 都是 file/offline-only。D6 已能消费 D4/D5/D7 写盘产物；D6 不拥有 live bus 订阅、AirSim 原生 recording 通用解析器或自动跨目录 episode 聚合调度。

截至 2026-07-10，main runtime 的 `--p1-calibration-sweep` 仍由 main 负责 AirSim 启动、settings 组合、reset-separated seeds/cases 和日志落盘。D6 bundle 保留 `airsim_calibration_records.csv`、`airsim_calibration_summary.csv`、`airsim_calibration_summary.json`、`airsim_calibration_report.md`，并新增 `airsim_calibration_cross_seed_aggregate.csv`、`airsim_calibration_paired_comparison.csv`、`airsim_calibration_aggregate.json`、`airsim_calibration_aggregate_report.md`。D6 只读取 main 已写盘目录，不参与 sweep 调度或场景控制。

配对统计中，`pair_count=1` 只标记为 `descriptive_only`，保留单次差值但不输出 bootstrap CI 或 Cohen's dz；至少两个有效 seed 对才标记 `available` 并运行固定 RNG 的 percentile bootstrap。缺 baseline/enhanced seed、指标不可用和零 review-label precision 都显式保留，不会按 0 或成功样本处理。

AirSim calibration record 和 cross-seed aggregate 现直接消费 execution/contract `EpisodeMetrics` 中的 `intercept_success_count`、`collision_intercept_count`、`range_intercept_count`、`min_range_m`、`time_to_intercept_s`、`visual_png_switch_count`、`terminal_switch_allowed_rate`、`terminal_takeover_rate`、`gate_reject_count`；`intercept_abort_count` 从各 scope 自己的 `metadata.intercept_status_counts` 派生。只有 episode 存在 `intercept_summary.json`、`control_commands.csv`、显式 intercept summary/pair/status，或正数 D7 control execution event count 时这些字段才可用；read-only episode 的 dataclass 默认零会转换为 `None/unavailable`。execution 与 contract 不合并。cross-seed 对计数指标输出 `sum`，对四类拦截 outcome 额外输出实际 `target_count` 累计得到的 `opportunity_count` 和 `rate`；距离、时间和比例只使用 mean/std/min/max，不把它们的跨 seed 求和解释为工程指标。`Interception Outcome` 只列有执行证据且 opportunity 可计算的行，scope 列明确区分 execution 与 contract。

截至 2026-07-07，main/orchestrator 已在真实 D7 AirSim 执行后把 `control_commands.csv` 与 `intercept_summary.json` 中的执行结果合并进正式 `main_episode_bus_metrics.json`，同时把执行前的合同检查口径保留为 `main_episode_bus_contract_metrics.json`。因此正式 episode 指标中的 `intercept_success_count`、`collision_intercept_count`、`range_intercept_count`、`terminal_contract_reject_count`、`guidance_law_counts` 等字段以执行后结果为准；raw contract metrics 只用于诊断 D3/D4/D5/D7 gate 合同。D6 通过 `metric_scope=execution/contract` 保留这两个口径，并在 CSV/Markdown 中分组展示。episode CSV 保留 metadata JSON；Markdown 在存在数据时输出 terminal switch/contract reject reason 分布。D6 仍只读取这些文件或由 main 写出的 metrics，不参与控制或重规划。

2026-07-10 对 `outputs/p1_gap_closure_2v2_smoke_20260710/episode_006_full_flow` 的复核表明：正式 execution 文件记录实际规模 `2/2/2/2`、`intercept_success_count=2`、`visual_png_switch_count=3`；contract 文件保持独立诊断口径。该 episode 的 `airsim_blocks_summary.integrated_result.metrics` 仍含执行前旧快照（规模 `3/3/2/0`）。D6 loader 明确以两个 `main_episode_bus` metrics 文件为准并忽略旧快照，且每个 calibration record 的 evidence path 指向其实际 execution/contract 文件；旧快照一致性需要 main runtime 单独修复，D6 不回写运行时文件。

同日使用 `p1_gap_closure_2v2_multiseed_20260710_seed001..010/blocks_sequence_summary.json` 验收：full-flow execution 聚合为 10 seeds、成功 `18/20`（0.9）、碰撞拦截 18、距离拦截 0、abort 2；`min_range_m` 均值约 1.812 m，`time_to_intercept_s` 均值约 3.66 s，visual PNG switch 合计 88，terminal switch allowed rate 均值约 0.0822，terminal takeover rate 均值 1.0，gate reject 合计 881。该结果证明 D6 可以直接从现有 summaries 生成多 seed 拦截结果，D6 未参与任何控制。

D6 现在也能离线汇总 main/D4/D5 已写盘的二级视角 metadata，并在报告中明确对比 `fixed_downlook_secondary` 与 `mobile_recon_gimbal`。该口径只消费覆盖、FOV、分辨率、cue source、cross-view association、D5 registration 和 cue/gimbal pointing error 字段；D6 不下发 cue、不控制云台、不参与接管或重分配。

P1 二级侦察 detect-to-registration 校准报告已经补齐分层漏斗字段：`secondary_detect_count`、`secondary_visible_target_union_ratio`、`secondary_network_joint_full_view_frame_rate`、`projection_valid_rate`、`geometry_gate_pass_rate`、`registered_candidate_count`、`stable_cross_view_registration_count` 和 `not_registered_count`。reject/outcome reason 统一保留 `not_all_targets_visible`、`network_union_incomplete`、`projection_invalid`、`geometry_gate_rejected`、`stability_window_failed`、`no_global_binding`、`stale_or_missing_recon_cue`、`registered_to_global_track`，缺失时按 0 输出，便于跨 seed 比较。

截至 2026-07-09，P1 AirSim calibration Markdown 进一步输出 50m vs 200m 二级覆盖对比、coverage funnel、Detect-to-registration funnel、baseline vs enhanced 对照、D7 guidance reject reason 和 Standard C-UAS Mapping。baseline/enhanced 只使用日志显式写出的 comparison role；D6 不从 `2v2/5v5` 场景名推断规模或对照组，不接 TrackEval、Stone Soup、SCRIMMAGE 等外部 evaluator。

截至 2026-07-08，`research_modules/airsim_runtime/outputs/p1_d4d5_mobile_recon_20260708_055948*` 是历史 mobile recon stress 批次，可作为 D6 已能消费 `mobile_recon_gimbal`、coverage、bbox、gimbal 和 funnel 字段的旧证据。

2026-07-08 registration calibration v2 历史基线位于 `research_modules/airsim_runtime/outputs/p1_d4d5_registration_calibration_runtime_v2_20260708*`。D6 bundle 已生成 `d6_airsim_calibration/airsim_calibration_records.csv`、`airsim_calibration_summary.csv`、`airsim_calibration_summary.json` 和 `airsim_calibration_report.md`。该 v2 批次为 single seed、3 case，height 200 m、FOV 110 deg、secondary_count 3；当时指标为 `projection_valid_rate=1.0`、`geometry_gate_pass_rate≈0.474`、stable cross-view registration 51/55/53、cross-view association 4/4/5、degradation case `not_registered_count=35/35`、full-view mean≈0.048、best≈0.143、coverage mean≈0.771。该历史批次证明 D6 报告链路能够输出 projection/gate/stable registration/not-registered/funnel/D7 reject，但不作为 2026-07-11 P1 当前结论。D6 仍只消费日志，不参与控制，也不从 `2v2/5v5` 场景名推断规模。

## 当前 P0/P1 状态

### 2026-07-11 四导引律短窗口实测证据

main 已修复 experiment-level guidance law 的执行后回灌，并从
`research_modules/airsim_runtime/outputs/p1_guidance_four_law_smoke_20260711/`
生成 D6 同 seed 对照产物。`guidance_same_seed_pairs.csv` 包含 21 条“候选导引律 x
指标”配对记录，但每条记录的 `pair_count=1`，实际只有 seed 7 一个独立 seed；不能把
21 条指标行解释为 21 次独立实验。

该 smoke 使用 2 秒短窗口，Pure Pursuit、Radar PN、PNG VM 和 PNG TTC 均 timeout，
拦截成功率均为 0。PNG VM/TTC 的 `terminal_switch_allowed_rate` 分别约为 0.762 和
0.810，最小距离分别约为 2.812 m 和 2.798 m。这些结果证明四律标签回灌、同 seed
配对、末端切换事件和距离指标能够被 D6 正确消费；它们不构成最终命中率、导引律优劣
或统计显著性结论。延长运行窗口并开展真实多 seed、同几何、同规模对照仍为 P1。

- P0：P0-A/P0-C 字段已补齐。D6 当前输出 mission outcome、success/failure reason、top failure causes/root cause、性能监测字段、EVAL tracking schema 和 `cuas-standard-map-v1` 标准化评估映射最小版；仍保持离线消费日志，不参与控制；指标继续按实际规模归一化，不从 `5v5` 名称推断分母。
- P1：D6 侧 coalition commit、`contract/control/switch/physical` 四层验收、pair/target/coalition 分层 physical success 与 detect/coast 诊断接口已补齐；CV T001 8/10 达到合同验收阈值，二级/分布式 commit 和 missing-ACK fail-closed 正负例已形成真实 evidence，P1 合同层闭合。两个 CV 尾部 seed 只保留为鲁棒性回归，不是合同闭合 blocker。SimpleFlight 15 s 批次只有物理 evidence 可用的 0/30 命中诊断，物理拦截仍未闭合。当前回归基线为 `82 passed`。
- P2：py-motmetrics IDF1/MOTA/MOTP adapter 已作为冻结 replay 上的 optional benchmark 实现；TrackEval、Stone Soup、OSPA/GOSPA、HOTA 和非参数统计仍待实现。所有 P2 能力均不进入在线链路、默认依赖或控制决策。

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
ReportGenerator().write_standard_mapping_csv("standard_metric_mapping.csv")
```

## 外部项状态

py-motmetrics 已有隔离 adapter、冻结 schema、available/unavailable 测试及 `motmetrics 1.4.0` 实际环境验证。Stone Soup metrics、TrackEval、OSPA/GOSPA/HOTA、AirSim 原生 recording replay 和 SCRIMMAGE metrics bridge仍没有实际 adapter；它们继续作为 P2/P3 可选项，不替代当前本地离线指标主线。
