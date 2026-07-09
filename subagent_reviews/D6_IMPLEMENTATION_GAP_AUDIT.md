# D6 实现差距审计

审计范围：`research_modules/d6_evaluation_metrics/**` 的当前代码、测试和文档，以及 `subagent_reviews/D6_*`。本文只评估 D6 离线指标模块状态；D6 消费日志，不参与控制，不生成任务、授权、导引、火控、毁伤或自动处置动作。

## 总体结论

D6 当前已经实现一条轻量、可测试、离线的系统评估主线。`TrackRecord`、`AssignmentRecord`、`EventRecord`、`LinkRecord`、`TerminalRecord` 进入 `MetricsCollector`，输出 `EpisodeMetrics`、CSV、Markdown 和 PNG 图表。`EpisodeMetrics` 已包含探测、跟踪、分配、降级、主动降级必要性标签口径、末端、二级视角/侦察云台、通信、D7 gate/intercept 和安全指标。D6 现在也能直接读取 main runtime 已写盘的 `main_episode_bus_metrics.json` 与 `main_episode_bus_contract_metrics.json`，把 execution/contract 双口径还原为 `EpisodeMetrics`，并能通过 AirSim calibration helper 自动汇总多 seed D4/D5 stress 与 main bus metrics。

2026-07-08 main runtime 已新增 P1 D4/D5 calibration sweep，并在 batch 结束后自动调用 D6 `AirSimCalibrationReportGenerator.write_report_bundle()`，生成 `d6_airsim_calibration/airsim_calibration_records.csv`、`airsim_calibration_summary.csv`、`airsim_calibration_summary.json` 和 `airsim_calibration_report.md`。D6 只消费这些已写盘目录和文件，不参与 AirSim 启停、reset、camera/gimbal 指向、主动降级、二次分配或末端配准控制。

2026-07-08 D6 已补齐 P1 二级侦察 detect-to-registration 校准报告口径。AirSim calibration records/summary/Markdown 现在显式输出 `secondary_detect_count`、`secondary_visible_target_union_ratio`、`secondary_network_joint_full_view_frame_rate`、`projection_valid_rate`、`geometry_gate_pass_rate`、`registered_candidate_count`、`stable_cross_view_registration_count`、`not_registered_count`。reject/outcome reason 固定保留 `not_all_targets_visible`、`network_union_incomplete`、`projection_invalid`、`geometry_gate_rejected`、`stability_window_failed`、`no_global_binding`、`stale_or_missing_recon_cue`、`registered_to_global_track`，缺失字段按 0 输出，避免不同 seed/case 的 JSON key 不一致。D6 仍只统计上游写盘事实，不参与 D5 注册或 D4 降级仲裁。

规模字段 `drone_count/resource_count/target_count/camera_count` 已进入 `EpisodeMetrics`、CSV、summary 和 Markdown 报告。D6 按实际记录或 `truth_summary` 字段归一化；二级网络 full-view/coverage 与单相机 full-view 指标按实际 target/camera count 或日志显式实际计数归一化；报告按 `metric_scope/seed/scenario_group/drone_count/resource_count/target_count/camera_count` 分组；episode CSV 保留 metadata JSON，Markdown 在存在数据时输出 fixed downlook secondary vs mobile recon gimbal 对比表和 terminal switch/contract reject reason 分布；测试覆盖了场景名包含 `5v5` 但实际规模为 `3/3/4/6` 的情况。因此当前 D6 不从 `2v2/5v5` 场景名推断规模。

D2/D6 强制 `id_switch_count` 的规则已落实：`id_switch_count` 是 `EpisodeMetrics.metric_names()` 的显式字段，并有单元测试覆盖。

尚未完成的是外部 benchmark 和真实 episode 批量验收：Stone Soup metrics、TrackEval/py-motmetrics、OSPA/GOSPA/HOTA/IDF1、AirSim 原生 recording replay、live AirSim replay 和 SCRIMMAGE metrics bridge 都没有实际 import、adapter 或测试。D4/D5/D7 的离线产物已有 D6 侧 loader/指标消费能力。2026-07-07 起，main/orchestrator 已把真实 D7 AirSim 执行后的 `control_commands.csv` 与 `intercept_summary.json` 合并进正式 `main_episode_bus_metrics.json`，并把执行前合同检查保留为 `main_episode_bus_contract_metrics.json`；剩余 P1 聚焦真实 episode 持续写 D4 review/window 等字段，以及多 seed、5v5/N-v-N、非默认 episode 的双口径报告验收。

2026-07-08 `research_modules/airsim_runtime/outputs/p1_d4d5_mobile_recon_20260708_055948*` 是历史 mobile recon stress 批次，可作为 D6 已能消费 `mobile_recon_gimbal`、coverage、bbox、gimbal 和 funnel 字段的旧证据，但不再作为当前 P1 结论。

当前最新 P1 registration calibration v2 输出在 `research_modules/airsim_runtime/outputs/p1_d4d5_registration_calibration_runtime_v2_20260708*`，D6 bundle 已生成 `d6_airsim_calibration/airsim_calibration_records.csv`、`airsim_calibration_summary.csv`、`airsim_calibration_summary.json` 和 `airsim_calibration_report.md`。该 v2 批次为 single seed、3 case，height 200 m、FOV 110 deg、secondary_count 3；当前指标为 `projection_valid_rate=1.0`、`geometry_gate_pass_rate≈0.474`、stable cross-view registration 51/55/53、cross-view association 4/4/5、degradation case `not_registered_count=35/35`、full-view mean≈0.048、best≈0.143、coverage mean≈0.771。D6 当前结论是报告链路已能输出 projection/gate/stable registration/not-registered/funnel/D7 reject，剩余工作是更多真实 AirSim 多 seed/N-v-N 数据和 review labels，用于形成长期趋势；D6 仍只消费日志，不参与 D4/D5/D7 控制，也不从 2v2/5v5 场景名推断规模。

2026-07-09 D6 已补齐 P0-A/P0-C episode 状态和追踪字段。`EpisodeMetrics`、episode CSV、summary/Markdown 现在输出 `mission_outcome=success/partial/failed/aborted`、`success_reason`、`failure_reason`、`eval_priority`、`implementation_status`、`evidence_path`，并把同名字段冗余进 metadata 便于 main 报告消费。D6 基于 records/metadata 与已计算指标被动派生 `top_failure_causes`、`root_cause`、`failure_cause_scores` 和 `failure_cause_details`，覆盖 tracking、assignment、terminal_gate、guidance、coverage、runtime_exception、communication、safety、performance；不做控制因果推断或回写。性能监测已新增 `module_duration_ms`、`loop_latency_ms`、`record_latency_ms`、`cpu_budget_utilization`、`gpu_budget_utilization`、`performance_budget_violation_count`，summary 和 metadata 均保留，CPU/GPU 缺失时保持 placeholder schema。

2026-07-09 EVAL 三个 patch 进一步确认：当前没有新的运行级 P0 blocker；D6 已实现 mission outcome、根因诊断、性能、可复现字段和 `COURAGEOUS/MDPI/OCEF -> 当前 EpisodeMetrics` 标准化评估映射最小版。映射版本固定为 `cuas-standard-map-v1`，覆盖 mission/root cause、detection、tracking、assignment、degradation、terminal、communication、guidance/intercept、safety、performance、reproducibility/evidence。完整 COURAGEOUS/OCEF 报告、baseline 对比和统计显著性、场景库管理、CI 回归摘要仍列 P1。

## P0/P1 复核结论

本节按 `EVAL/FRAMEWORK_EVAL_P0_P1_P2_GAP_CONFIRMATION.md` 以及三个 patch 同步 D6 相关 P0/P1 缺口。口径与 EVAL 保持一致：当前没有运行级 P0 blocker；P0 是进入更可信 AirSim/封闭场地验证前的工程化硬化项，P1 是三个月内的标准化报告、对照统计、场景库和回归化工作。D6 继续只消费日志和已写盘 metrics，不参与控制、重规划、降级仲裁、末端配准或导引。

现有已完成状态保持不降级：`EpisodeMetrics`、`TrackRecord`、`AssignmentRecord`、`EventRecord`、`LinkRecord` 和 `TerminalRecord` 已作为 D6 离线指标主线保留；D7 guidance records 当前由 `guidance_records.csv`、`guidance_summaries.json` loader 转换为 `d7_guidance_record/d7_guidance_summary` 事件 metadata，而不是单独在线控制数据类。`id_switch_count`、实际规模字段、execution/contract 双口径、AirSim calibration bundle、detect-to-registration 漏斗、reject/outcome reason 分布和 D6 只消费日志不控制的边界均保持为已完成能力。

| EVAL 等级 | 同步条目 | D6 当前实施状态 | 已有证据/保留状态 | 剩余验收口径 |
|---|---|---|---|---|
| P0-A | 系统级任务成功指标 | 已实现，持续真实批次回归 | 每个 episode 已输出 `mission_outcome=success/partial/failed/aborted`、`success_reason`、`failure_reason`；显式 outcome 优先，上游缺失时从 intercept/abort/runtime/safety/部分进展指标被动派生。 | 在真实 AirSim 多 seed、5v5/N-v-N 和非默认 episode 中持续写盘并比较 execution/contract 口径。 |
| P0-A | failure reason/root cause 根因诊断 | 已实现，持续真实批次回归 | 已输出 terminal switch/contract reject reason、D5 detect-to-registration reject/outcome reason、D4 review label/后验字段和 D7 guidance reject metadata；新增 `top_failure_causes`、`root_cause`、`failure_cause_scores`、`failure_cause_details`。 | 根因类别保持被动消费，覆盖 tracking、assignment、terminal_gate、guidance、coverage、runtime_exception、communication、safety、performance；后续只随真实日志字段扩展。 |
| P0-A | 性能和可复现字段 | 已实现最小 schema，持续真实批次回归 | 新增 `module_duration_ms`、`loop_latency_ms`、`record_latency_ms`、`cpu_budget_utilization`、`gpu_budget_utilization`、`performance_budget_violation_count`；`eval_priority`、`implementation_status`、`evidence_path` 已进入 `EpisodeMetrics`、episode CSV、metadata 和 Markdown EVAL Tracking 表。 | main/D1-D7 真实 episode 持续写 module timing、loop latency、record latency、CPU/GPU budget、真实 evidence path 和 scenario/version metadata；D6 只消费。 |
| P0-A | 标准化评估映射最小版 | 已实现，持续真实批次回归 | 新增 `standard_mapping.py`，固定 `cuas-standard-map-v1`，输出 `engineering_metric`、`standard_metric_family`、`standard_sources`、`implementation_status`、`evidence_requirement`；`EpisodeMetrics` 增加 `scenario_version`、`standard_mapping_version`、`standard_metric_family_summary`；episode CSV、metadata、Markdown 和 `standard_metric_mapping.csv` 已输出映射。 | 真实 AirSim 多 seed、5v5/N-v-N 和非默认 episode 持续写真实 `scenario_version`、`evidence_path` 和同一 mapping version；不要求完整认证流程。 |
| P1 | COURAGEOUS/MDPI/OCEF 完整标准化报告 | P1 待补 | WebSearch patch 确认 COURAGEOUS/CEN、MDPI 综述和 OCEF 可复现纪律是 D6 标准化方向；当前已有本地最小映射、CSV/JSON/Markdown 指标报告。 | 在 P0 最小映射基础上增加测试阶段、复现纪律字段、evidence index、标准场景覆盖和外部审计说明；完整封闭场地/外部审计报告仍依赖 main 提供场景和日志。 |
| P1 | 基线对比和统计显著性 | P1 待补 | 已有 episode CSV、summary CSV、Markdown、PNG 图、95% CI、按 `metric_scope/seed/scenario_group/actual scale` 分组和 calibration bundle。 | 同一场景输出 baseline vs enhanced 表格，并补多 seed 均值/方差/置信区间或等价统计显著性口径。 |
| P1 | 场景库管理 | P1 待补 | 已保留 seed、scenario/scenario_group、actual scale 和 AirSim calibration case metadata；`2v2/5v5` 只作为 baseline 名称。 | 标准场景库包含 tags、seed、difficulty、expected failure modes 和覆盖状态；D6 只消费场景 metadata。 |
| P1 | CI 回归摘要 | P1 待补 | 当前有 D6 unit tests、报告生成测试、main bus loader 测试和手动 batch report 链路。 | 每次变更产出实验级测试矩阵、P0/P1 tracking 字段检查、性能回归摘要和 evidence path 检查。 |

P1 缺口保持为离线评估能力、真实 episode 写盘和长期趋势问题，不是 D6 在线控制职责：D7 real execution metrics 的正式/contract 双口径已完成；D6 已补 `metric_scope`、seed/scenario/实际规模报告分组、main bus metrics JSON loader、reject reason 分布输出、二级视角/侦察云台 coverage/cross-view/registration/pointing-error 指标、detect-to-registration 分层漏斗、AirSim 多 seed calibration 自动汇总，以及 `active_degradation_precision`/`unnecessary_active_degradation_count` 的 review label/后验最小实现。main runtime P1 sweep 已自动调用 D6 bundle，D6 当前 P1 重点是 COURAGEOUS/MDPI/OCEF 完整报告、baseline 对比和统计显著性、场景库、CI 回归摘要、多 seed 自动汇总回归、coverage/funnel/gimbal/projection/gate/stable registration 长期趋势、active degradation precision 真实标签、D7 guidance reject reason 和 actual scale 分组；剩余项是更多批次的数据沉淀，以及 main/D4/D5/D7 在真实 episode 中持续写出可对齐的 D4/D5/D7/Blocks 文件。D6 按实际 `drone_count/resource_count/target_count/camera_count` 归一化，`2v2/5v5` 只作为 baseline 场景名。

非本轮范围保持 P2/P3 或禁止项：Stone Soup metrics、OSPA/GOSPA、TrackEval/py-motmetrics、HOTA/IDF1、AirSim 原生 recording parser、SCRIMMAGE bridge、live replay/API。它们不替代当前 D6 本地离线指标主线。

## 已实现

| 能力 | 当前状态 | 代码/测试证据 |
|---|---|---|
| `EpisodeMetrics` | 已实现。包含 episode metadata、实际规模字段、八类指标和 `metadata`。 | `research_modules/d6_evaluation_metrics/d6_evaluation_metrics/metrics.py`; `tests/test_metrics.py` |
| 规模归一化 | 已实现。优先使用 `truth_summary` 或 Blocks replay 的实际 `drone_count/resource_count/target_count/camera_count`，缺失时从记录推断；报告按 `metric_scope/seed/scenario_group` 和实际规模分组。 | `metrics.py`; `reporting.py`; `tests/test_metrics.py`; `tests/test_reporting_and_simulation.py`; `tests/test_blocks_replay.py` |
| 基础记录模型 | 已实现 `TrackRecord`、`AssignmentRecord`、`EventRecord`，并扩展 `LinkRecord`、`TerminalRecord`。 | `metrics.py`; `jsonl.py`; `tests/test_airsim_dry_run_jsonl.py` |
| 探测指标 | 已实现 `detection_probability`、`false_alarm_rate`、`missed_detection_rate`。 | `metrics.py`; `tests/test_metrics.py`; `tests/test_blocks_replay.py` |
| 跟踪指标 | 已实现 `track_rmse`、`track_continuity`、`id_switch_count`。`id_switch_count` 对同一 `truth_id` 的 `global_track_id` 变化显式计数。 | `metrics.py`; `tests/test_metrics.py` |
| 分配指标 | 已实现 `duplicate_assignment_count`、`unassigned_high_threat_count`，并按 active + 有效授权状态过滤。 | `metrics.py`; `tests/test_metrics.py` |
| 基础降级指标 | 已实现 `failover_time`、`consensus_rounds`、`degraded_completion_rate`。 | `metrics.py`; `tests/test_metrics.py` |
| D4 active/passive 降级基线 | 已实现 `active_degradation_count`、`active_degradation_precision`、`unnecessary_active_degradation_count`、`passive_failover_count`、`secondary_node_takeover_count`、`secondary_reassignment_count`、`d4_reassign_pending_count`、`distributed_fallback_count`、`failover_active_window_delta_s`，并保留触发原因、review label 和必要性后验分布。 | `metrics.py`; `d4_replay.py`; `tests/test_d4_replay.py`; `tests/test_metrics.py` |
| 末端指标 | 已实现 `terminal_association_accuracy`、`terminal_id_switch_count`、`ambiguous_fov_event_count`、`friend_overlap_hold_count`、`time_to_terminal_lock`、`terminal_lock_count`。 | `metrics.py`; `tests/test_metrics.py` |
| 多视角/无 PNG 评估 | 已实现基础能力。Blocks replay 可用 bbox、相机内外参、timestamp、object label 和 truth label 生成 terminal、video/bbox link、多视角 consensus/conflict。PNG 不作为指标必需输入。 | `blocks_replay.py`; `tests/test_blocks_replay.py` |
| 二级视角/侦察云台指标 | 已实现。统计 `secondary_network_joint_full_view_frame_rate`、`secondary_network_mean_coverage_ratio`、`secondary_single_camera_full_view_frame_rate`、`cross_view_association_count`、`secondary_detect_available_but_not_registered_count`、`cue_pointing_error_*`、`gimbal_pointing_error_*`，并在 metadata 中保留 node-type 对比。 | `metrics.py`; `reporting.py`; `tests/test_metrics.py`; `tests/test_reporting_and_simulation.py` |
| 通信链路指标 | 已实现 latency、drop、out-of-order、stale、video metadata delivery、bbox delivery、consensus latency。 | `metrics.py`; `tests/test_metrics.py`; `tests/test_blocks_replay.py` |
| D7 intercept replay | 已实现。读取 `control_commands.csv` 和 `intercept_summary.json`，计算 success、collision/range intercept、min range、time to intercept、gate reject 等。 | `intercept_replay.py`; `tests/test_intercept_replay.py` |
| D7 guidance time-series | 已实现。读取 `guidance_records.csv`、`guidance_summaries.json`，保留 mode switch、terminal contract reject、D4/D5 state、plan/version、guidance law。 | `intercept_replay.py`; `metrics.py`; `tests/test_intercept_replay.py` |
| D7 terminal gate/visual PNG switch | 已实现 `camera_quality_gate_pass_rate`、`los_quality_gate_pass_rate`、`maneuver_margin_gate_pass_rate`、`terminal_switch_allowed_rate`、`visual_png_switch_count`、`terminal_takeover_rate`、`terminal_switch_reject_count`。 | `metrics.py`; `tests/test_metrics.py`; `tests/test_intercept_replay.py` |
| 安全指标 | 已实现 `constraint_violation_count`、`human_override_count`。 | `metrics.py`; `tests/test_metrics.py` |
| 批量统计/报告图表 | 已实现 episode CSV、summary CSV、Markdown、按指标族 PNG 图和 selected distribution 图；summary 包含 count/mean/std/stderr/95% CI/median/p05/p95。 | `reporting.py`; `scripts/run_batch_example.py`; `tests/test_reporting_and_simulation.py` |
| P0-A 标准化评估映射最小版 | 已实现。`cuas-standard-map-v1` 覆盖 mission/root cause、detection、tracking、assignment、degradation、terminal、communication、guidance/intercept、safety、performance、reproducibility/evidence；`MetricsCollector.compute_episode()` 写入 mapping metadata，`ReportGenerator.write_standard_mapping_csv()` 输出 `standard_metric_mapping.csv`，Markdown 在 `EVAL Tracking` 后输出 `Standard C-UAS Mapping` 表。 | `standard_mapping.py`; `metrics.py`; `reporting.py`; `main_bus.py`; `tests/test_metrics.py`; `tests/test_reporting_and_simulation.py` |
| JSONL 标准化接口 | 已实现 `truth_summary/track/assignment/event/link/terminal`，未知 record type 报错。 | `jsonl.py`; `tests/test_airsim_dry_run_jsonl.py` |
| main bus metrics JSON | 已实现。读取 `main_episode_bus_metrics.json` 与 `main_episode_bus_contract_metrics.json`，还原 execution/contract `EpisodeMetrics`，保留 seed/scenario/实际规模和 metadata 分布。 | `main_bus.py`; `tests/test_main_bus_metrics.py` |
| 二级节点对比与 reject reason 报告输出 | 已实现。episode CSV 保留 metadata JSON；Markdown 在有数据时输出 fixed downlook secondary vs mobile recon gimbal 对比表，以及 terminal switch/contract reject reason 分布。 | `reporting.py`; `tests/test_reporting_and_simulation.py` |
| AirSim 多 seed calibration 汇总 | 已实现。自动扫描 batch/seed/case 目录中的 `d4d5_stress_metrics.json`、`airsim_blocks_summary.json`、main bus execution/contract metrics，按 `metric_scope/seed/scenario/secondary_height/FOV/secondary_count/detection_backend` 输出 CSV、JSON 和中文 Markdown；main runtime P1 D4/D5 calibration sweep 已自动调用该 bundle。 | `airsim_calibration.py`; `tests/test_airsim_calibration.py` |
| P1 detect-to-registration 校准漏斗 | 已实现。records/summary/Markdown 显式输出 `secondary_detect_count`、`secondary_visible_target_union_ratio`、`projection_valid_rate`、`geometry_gate_pass_rate`、`registered_candidate_count`、`stable_cross_view_registration_count`、`not_registered_count`，并固定保留八类 reject/outcome reason。 | `airsim_calibration.py`; `tests/test_airsim_calibration.py` |

## 部分实现

| 能力 | 当前状态 | 为什么只是部分实现 | 缺少条件 | 优先级 |
|---|---|---|---|---|
| D7 real execution metrics 回灌到正式 main bus metrics | 已完成主线。main/orchestrator 把 `control_commands.csv` 与 `intercept_summary.json` 合并进正式 `main_episode_bus_metrics.json`，并保留 raw `main_episode_bus_contract_metrics.json`。 | D6 仍只消费文件，不负责运行 D7 或写正式 metrics；多 seed 验收属于批量报告口径。 | 在多 seed、5v5/N-v-N 和非默认 episode 中持续产出并采用同一双口径。 | P1 已完成，持续回归 |
| 真实 episode 日志完整性 | D6 已有 Blocks、D4 loader、D5/terminal/multi-view 指标和 D7 guidance/intercept loader；可以消费写盘文件。历史 mobile recon stress 已提供 D4/D5 stress metrics 旧证据；当前 P1 registration calibration v2 已提供 single seed x 3 case 的 AirSim calibration bundle。 | D6 loader 是离线入口，不负责 main runtime 写盘、目录扫描、episode clock 对齐或多 loader 合并调度。 | 每个 episode 目录稳定写出 Blocks/D4/D5/D7/D6 日志；汇总脚本合并到一个 `MetricsCollector`；同一 episode clock 和实际规模字段。 | P1 |
| D4 review/window 真实写盘 | D6 已实现 `active_degradation_precision` 与 `unnecessary_active_degradation_count` 的最小可测口径，D4 CSV loader 可消费 review label、trigger/decision timestamp、selected coordinator、coverage cell 和 pre/post window 字段。 | 真实 AirSim episode 是否每次写出 review/window 字段仍取决于 main/D4；缺 label 的 active degradation 不进入 precision 分母。 | main/D4 持续写盘；固定 pre/post 窗口；后续扩展 decision latency、ID switch delta、assignment conflict delta。 | P1 |
| 多 seed execution/contract 报告口径 | D6 已按 `metric_scope/seed/scenario_group/drone_count/resource_count/target_count/camera_count` 输出通用 summary，并新增 AirSim calibration 分组到 `metric_scope/seed/scenario/secondary_height/FOV/secondary_count/detection_backend`。 | 仍需要真实批量 episode 持续提供 execution metrics 与 contract metrics；D6 不从 `2v2/5v5` 场景名推断规模。 | 多 seed、5v5/N-v-N 和非默认 episode 的正式 metrics 与 raw contract metrics 成对落盘。 | P1 持续回归 |
| 移动侦察云台 AirSim 报告字段 | D6 已有被动指标、Markdown 对比表和 AirSim calibration 自动汇总，可消费 `mobile_recon_gimbal` metadata；历史 stress 验证了 gimbal、coverage、funnel、bbox 字段可落盘，当前 registration calibration v2 进一步验证 projection/gate/stable registration/not-registered/D7 reject 可进入 bundle。 | v2 仍只是 single seed、3 case；现有结果只能说明报告链路可用，长期趋势和阈值校准还缺更多真实 AirSim 多 seed/N-v-N 数据与 review labels。 | 用新增汇总报告持续比较 `mobile_recon_gimbal` / `fixed_downlook_secondary` 的 coverage、funnel、projection/gate、stable registration、not-registered、D7 reject、bbox、cue/gimbal pointing 指标。 | P1 持续回归 |
| 多视角末端几何质量 | 已能统计 consensus/conflict/duplicate lock 和 bbox delivery。 | 尚未计算跨视角重投影误差、外参质量评分或时延补偿。 | 稳定相机标定、跨节点时钟、D5 输出几何误差字段和候选集。 | P2 |
| 批量统计 CI | 已输出正态近似 95% CI 和分位数。 | 长尾/偏态指标还没有 bootstrap 或非参数 CI。 | 足够多真实 episode；bootstrap 配置；报告方法标注。 | P2 |
| 外部 MOT/OSPA 对照 | D6 已实现本地 POD/FAR/RMSE/continuity/IDSW 等分量。 | 未导出标准 frame-level benchmark 格式，未调用外部 evaluator。 | 帧级 truth/detection/track 匹配表、IoU/距离门限、遮挡/重现规则。 | P2 |

## 未实现

| 能力 | 当前状态 | 未实现原因 | 缺少条件 | 优先级 |
|---|---|---|---|---|
| Stone Soup metrics adapter | 未实现。没有 `stonesoup` import、对象转换器或 metric generator 调用。 | 保持默认测试轻依赖；D1/D2 输出尚未固定到 Stone Soup `Track/Detection/GroundTruthPath`。 | Stone Soup 版本锁定；D1/D2 adapter；坐标/时间/门限合同；CI fixture。 | P2 |
| OSPA/GOSPA 默认输出 | 未实现。文档保留公式，`EpisodeMetrics.metric_names()` 不含这些字段。 | 需要帧级 truth/estimate set 和 cutoff/order。 | 集合序列、birth/death/遮挡规则、门限配置。 | P2 |
| TrackEval / py-motmetrics | 未实现。没有 MOTChallenge 导出、TrackEval runner 或 motmetrics accumulator。 | D2/D5 frame-level 输出未稳定；当前系统评估不只 MOT。 | 帧级匹配表；IoU/距离门限；依赖版本和回归容差。 | P2 |
| HOTA/IDF1 | 未实现。 | 需要完整帧级身份评估和外部 evaluator。 | 稳定 visual/MOT 输出、遮挡/重现规则、标准格式导出。 | P2 |
| AirSim 原生 recording parser | 未实现。 | 当前 main Blocks JSONL 已更直接；原生 recording 字段、坐标和相机版本差异大。 | 原生 recording 样例；字段版本；NED/相机/episode clock 映射；测试。 | P2 |
| Live AirSim replay/API | 未实现，且不应作为 D6 默认目标。 | D6 的边界是 offline-only；live replay/control 属于 main runtime。 | 如需 replay，应由 main 导出 D6 可读日志。 | 禁止在线控制 |
| SCRIMMAGE metrics bridge | 未实现。没有 SCRIMMAGE import、日志解析器或统计桥接。 | 当前仿真主线是 AirSim Blocks 和合成数据；仓库没有 SCRIMMAGE 输出样例或 message schema。 | SCRIMMAGE episode 输出；agent/resource/target ID 映射；通信字段；episode clock；批量目录。 | P3 |
| D6 对实时控制/在线决策的参与 | 未实现，且不应实现。 | D6 只消费日志，不能回写控制链路。 | 不适用。 | 禁止项 |

## 未实现原因汇总

1. 当前阶段优先保持 D6 轻量、离线、可复现，默认测试不依赖重型外部库、AirSim 服务、GPU 或网络。
2. 标准 MOT/OSPA/HOTA/IDF1 需要帧级 truth-track/detection 匹配表、遮挡/重现规则和统一门限；当前 D6 记录满足本地系统指标，但还不是外部 benchmark 格式。
3. 主动降级“是否必要”不能由 D6 只看事件名自证；当前 D6 只消费 D4/main 写入的 review label、明确必要性布尔值、post-window outcome 或 pre/post risk 后验字段。
4. AirSim 原生 recording 和 SCRIMMAGE 都需要样例、schema、ID 映射和时钟/坐标对齐规则。
5. D6 不参与控制是模块边界，所有指标只用于离线报告和回归分析。

## P0 保持回归

1. 标准化评估映射最小版已实现，后续保持 `cuas-standard-map-v1`、`scenario_version`、`standard_mapping_version`、`standard_metric_family_summary`、`standard_metric_mapping.csv` 和 Markdown `Standard C-UAS Mapping` 表回归；D6 仍只消费日志，不参与控制，不要求完整认证或外部平台接入。

## P1 下一步

1. COURAGEOUS/MDPI/OCEF 完整标准化报告：在 P0 最小映射基础上补测试阶段、复现纪律字段、evidence index、标准场景覆盖和外部审计说明；D6 只消费 main/D1-D7 已写盘日志和 scenario metadata。
2. 基线对比框架：在现有 episode/summary/reporting 基础上增加 baseline vs enhanced 同场景对比、统计显著性或等价置信口径和 `evidence_path`；当前按 scenario/metric_scope/实际规模分组的汇总不等同于正式 A/B baseline。
3. 场景库管理：把 scenario metadata 扩展为标准场景库，至少包含 tags、seed、difficulty、expected failure modes 和 actual scale；保留 2v2/5v5 作为 baseline 名称，不用作规模推断。
4. CI/回归摘要：形成实验级测试矩阵和性能回归摘要；`eval_priority` / `implementation_status` / `evidence_path` 字段检查已进入 D6 单元测试，后续需要 main CI 持续消费真实 evidence path。
5. 多 seed 自动汇总与 coverage/funnel/gimbal 长期趋势：用 main runtime P1 calibration sweep 自动生成的 D6 AirSim calibration bundle 持续跟踪 mobile recon 与 fixed downlook 的 coverage、full-view、projection valid、geometry gate pass、registered candidate、stable registration、not-registered、D7 reject、bbox area 和 cue/gimbal pointing 指标；当前 v2 已验证报告链路，剩余是更多真实 AirSim 多 seed/N-v-N 批次和 review labels 形成长期趋势。
6. active degradation precision 真实标签：main/D4 持续写入 `review_label`、`active_degradation_necessary` 或后验 outcome/risk 字段；D6 不从事件名推断必要性。
7. 真实 episode 日志完整性：D4/D5/D7/Blocks 产物持续落到同一 episode clock 和目录，D6 汇总阶段调用 loader 合并；D6 不参与控制、重规划或导引。
8. 多 seed 双口径与 actual scale 报告：在 2v2、5v5、N-v-N 和非默认 episode 批量运行中持续保留 `metric_scope=execution/contract`、seed/scenario/实际规模字段、D7 guidance/control/intercept 元数据、guidance reject reason metadata 和 D4/D5 calibration geometry 字段；D6 已能读取 main bus 双口径 metrics JSON 并输出相应分组。

## P2 下一步

1. 定义 frame-level truth/detection/track 匹配表，为 TrackEval/py-motmetrics/Stone Soup 提供输入。
2. 优先接 TrackEval 或 py-motmetrics adapter，作为可选 benchmark。
3. 在 D1/D2 对象映射和版本锁定后接入 Stone Soup metrics 与 OSPA/GOSPA。
4. 为长尾指标增加 bootstrap 或非参数 CI。
5. 只有当 AirSim 多机规模或通信建模不足以回答实验问题时，再把 SCRIMMAGE bridge 作为 P3 可选项推进。
6. 仅在 Blocks JSONL 不足时增加 AirSim 原生 recording parser。

## 验收建议

```bash
pytest -q research_modules/d6_evaluation_metrics/tests
git diff --check -- research_modules/d6_evaluation_metrics subagent_reviews/D6_*
```
