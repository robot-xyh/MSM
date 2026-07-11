# D6 实现差距审计

审计范围：`research_modules/d6_evaluation_metrics/**` 的当前代码、测试和文档，以及 `subagent_reviews/D6_*`。本文只评估 D6 离线指标模块状态；D6 消费日志，不参与控制，不生成任务、授权、导引、火控、毁伤或自动处置动作。

## 总体结论

### 2026-07-10 P1 状态更新

本轮关闭了 D6 侧四类 P1 代码缺口：

- 二级接管 `readiness -> pending -> active` 驻留、activation latency、fallback、lease expiry、stale plan reject 已进入 `EpisodeMetrics`、AirSim calibration、CSV/Markdown 和 degradation 图表。缺 lifecycle evidence 时输出 unavailable。
- YOLOv8 + ByteTrack/BoT-SORT 质量与预算字段已进入 `EpisodeMetrics` 和 `visual_perception_metrics.png`：recall、local-ID continuity、cross-view registration、pipeline latency、CPU/GPU utilization、budget violation。离线 truth 只从 `offline_truth` 读取，在线字段泄漏单独计数。
- 四导引律同 seed 配对报告和场景库/seed matrix 已实现，输出 CSV、JSON、中文 Markdown 和 PNG；D6 不修改 D7 控制算法。
- AirSim calibration 现在按 detection backend、tracker backend、experiment guidance law 和 actual scale 保持分组，`None/unavailable` 与零值继续分离。

因此上述条目从“D6 P1 待实现”调整为“D6 已实现、待 main/D4/D5/D7 真实多 seed 写盘验收”。仍未关闭的 P1 是上游数据条件和长期回归：main 需要逐帧写 lifecycle/lease/stale 事件，D5 需要真实 YOLO/MOT latency/resource/offline truth fixture，D7/main 需要四种 experiment-level law 的同 seed 批次，CI 需要消费版本化 scenario library。外部 TrackEval/Stone Soup/OSPA 等保持 P2，不在本轮构造。

### 2026-07-11 四导引律 smoke 复核

main 已修复 guidance experiment law 的执行后回灌，并生成
`p1_guidance_four_law_smoke_20260711/d6_guidance_comparison/`。D6 产物包含 21 条同
seed 指标配对记录；其统计含义是 3 个候选律相对 Radar PN 的 7 项指标，且每项
`pair_count=1`，独立样本仅为 seed 7，不是 21 个 seeds。

四律在 2 秒短 episode 中均 timeout。PNG VM/TTC 的
`terminal_switch_allowed_rate` 约为 0.762/0.810，`min_range_m` 约为
2.812/2.798 m。该证据关闭的是“guidance law 回灌和 D6 同 seed 报告链路未被真实
数据验收”的接口缺口；不关闭“真实多 seed、较长拦截窗口下的命中率和算法排序”缺口。
后者继续列为 P1，并要求保留 timeout/abort、最小距离、视觉门控与切换率的联合解释，
不得从当前全 timeout 批次宣称某种导引律命中率更高。

D6 当前已经实现一条轻量、可测试、离线的系统评估主线。`TrackRecord`、`AssignmentRecord`、`EventRecord`、`LinkRecord`、`TerminalRecord` 进入 `MetricsCollector`，输出 `EpisodeMetrics`、CSV、Markdown 和 PNG 图表。`EpisodeMetrics` 已包含探测、跟踪、分配、降级、主动降级必要性标签口径、末端、二级视角/侦察云台、通信、D7 gate/intercept 和安全指标。D6 现在也能直接读取 main runtime 已写盘的 `main_episode_bus_metrics.json` 与 `main_episode_bus_contract_metrics.json`，把 execution/contract 双口径还原为 `EpisodeMetrics`，并能通过 AirSim calibration helper 自动汇总多 seed D4/D5 stress 与 main bus metrics。

2026-07-08 main runtime 已新增 P1 D4/D5 calibration sweep，并在 batch 结束后自动调用 D6 `AirSimCalibrationReportGenerator.write_report_bundle()`，生成 `d6_airsim_calibration/airsim_calibration_records.csv`、`airsim_calibration_summary.csv`、`airsim_calibration_summary.json` 和 `airsim_calibration_report.md`。D6 只消费这些已写盘目录和文件，不参与 AirSim 启停、reset、camera/gimbal 指向、主动降级、二次分配或末端配准控制。

2026-07-08 D6 已补齐 P1 二级侦察 detect-to-registration 校准报告口径。AirSim calibration records/summary/Markdown 现在显式输出 `secondary_detect_count`、`secondary_visible_target_union_ratio`、`secondary_network_joint_full_view_frame_rate`、`projection_valid_rate`、`geometry_gate_pass_rate`、`registered_candidate_count`、`stable_cross_view_registration_count`、`not_registered_count`。reject/outcome reason 固定保留 `not_all_targets_visible`、`network_union_incomplete`、`projection_invalid`、`geometry_gate_rejected`、`stability_window_failed`、`no_global_binding`、`stale_or_missing_recon_cue`、`registered_to_global_track`，缺失字段按 0 输出，避免不同 seed/case 的 JSON key 不一致。D6 仍只统计上游写盘事实，不参与 D5 注册或 D4 降级仲裁。

规模字段 `drone_count/resource_count/target_count/camera_count` 已进入 `EpisodeMetrics`、CSV、summary 和 Markdown 报告。D6 按实际记录或 `truth_summary` 字段归一化；二级网络 full-view/coverage 与单相机 full-view 指标按实际 target/camera count 或日志显式实际计数归一化；报告按 `metric_scope/seed/scenario_group/drone_count/resource_count/target_count/camera_count` 分组；episode CSV 保留 metadata JSON，Markdown 在存在数据时输出 fixed downlook secondary vs mobile recon gimbal 对比表和 terminal switch/contract reject reason 分布；测试覆盖了场景名包含 `5v5` 但实际规模为 `3/3/4/6` 的情况。因此当前 D6 不从 `2v2/5v5` 场景名推断规模。

D2/D6 强制 `id_switch_count` 的规则已落实：`id_switch_count` 是 `EpisodeMetrics.metric_names()` 的显式字段，并有单元测试覆盖。

尚未完成的是外部 benchmark 和真实 episode 批量验收：Stone Soup metrics、TrackEval/py-motmetrics、OSPA/GOSPA/HOTA/IDF1、AirSim 原生 recording replay、live AirSim replay 和 SCRIMMAGE metrics bridge 都没有实际 import、adapter 或测试。D4/D5/D7 的离线产物已有 D6 侧 loader/指标消费能力。2026-07-07 起，main/orchestrator 已把真实 D7 AirSim 执行后的 `control_commands.csv` 与 `intercept_summary.json` 合并进正式 `main_episode_bus_metrics.json`，并把执行前合同检查保留为 `main_episode_bus_contract_metrics.json`；剩余 P1 聚焦真实 episode 持续写 D4 review/window 等字段，以及多 seed、5v5/N-v-N、非默认 episode 的双口径报告验收。

2026-07-08 `research_modules/airsim_runtime/outputs/p1_d4d5_mobile_recon_20260708_055948*` 是历史 mobile recon stress 批次，可作为 D6 已能消费 `mobile_recon_gimbal`、coverage、bbox、gimbal 和 funnel 字段的旧证据，但不再作为当前 P1 结论。

当前最新 P1 registration calibration v2 输出在 `research_modules/airsim_runtime/outputs/p1_d4d5_registration_calibration_runtime_v2_20260708*`，D6 bundle 已生成 `d6_airsim_calibration/airsim_calibration_records.csv`、`airsim_calibration_summary.csv`、`airsim_calibration_summary.json` 和 `airsim_calibration_report.md`。该 v2 批次为 single seed、3 case，height 200 m、FOV 110 deg、secondary_count 3；当前指标为 `projection_valid_rate=1.0`、`geometry_gate_pass_rate≈0.474`、stable cross-view registration 51/55/53、cross-view association 4/4/5、degradation case `not_registered_count=35/35`、full-view mean≈0.048、best≈0.143、coverage mean≈0.771。D6 当前结论是报告链路已能输出 projection/gate/stable registration/not-registered/funnel/D7 reject，剩余工作是更多真实 AirSim 多 seed/N-v-N 数据和 review labels，用于形成长期趋势；D6 仍只消费日志，不参与 D4/D5/D7 控制，也不从 2v2/5v5 场景名推断规模。

2026-07-09 D6 已补齐 P0-A/P0-C episode 状态和追踪字段。`EpisodeMetrics`、episode CSV、summary/Markdown 现在输出 `mission_outcome=success/partial/failed/aborted`、`success_reason`、`failure_reason`、`eval_priority`、`implementation_status`、`evidence_path`，并把同名字段冗余进 metadata 便于 main 报告消费。D6 基于 records/metadata 与已计算指标被动派生 `top_failure_causes`、`root_cause`、`failure_cause_scores` 和 `failure_cause_details`，覆盖 tracking、assignment、terminal_gate、guidance、coverage、runtime_exception、communication、safety、performance；不做控制因果推断或回写。性能监测已新增 `module_duration_ms`、`loop_latency_ms`、`record_latency_ms`、`cpu_budget_utilization`、`gpu_budget_utilization`、`performance_budget_violation_count`，summary 和 metadata 均保留，CPU/GPU 缺失时保持 placeholder schema。

2026-07-09 EVAL 三个 patch 进一步确认：当前没有新的运行级 P0 blocker；D6 已实现 mission outcome、根因诊断、性能、可复现字段和 `COURAGEOUS/MDPI/OCEF -> 当前 EpisodeMetrics` 标准化评估映射最小版。映射版本固定为 `cuas-standard-map-v1`，覆盖 mission/root cause、detection、tracking、assignment、degradation、terminal、communication、guidance/intercept、safety、performance、reproducibility/evidence。完整 COURAGEOUS/OCEF 报告、统计显著性、场景库管理、CI 回归摘要仍列 P1；baseline/enhanced 表格已在 AirSim calibration 报告中补齐，仍需多 seed 显著性验证。

2026-07-09 D6 已按 main 的 P1 calibration 方案扩展 AirSim calibration records/summary/Markdown：records 和 summary 现在保留 `scenario_version`、`standard_mapping_version`、`standard_metric_family_summary`、`evidence_path`、`comparison_role`、`trend_key`、`secondary_height_bucket`、`metric_scope` 和 actual scale 字段；Markdown 新增 50m vs 200m 二级覆盖对比、coverage funnel、baseline vs enhanced 表格，并继续输出 stable cross-view registration、not-registered count、active degradation precision、unnecessary degradation、D7 guidance reject reason 和 Standard C-UAS Mapping。baseline/enhanced 只消费上游显式写出的 comparison role；D6 不从 `2v2/5v5` 名称推断规模或实验组，也不接 TrackEval、Stone Soup、SCRIMMAGE 等外部 evaluator。

## P0/P1 复核结论

### 2026-07-11 M 对 N 实现复核

专项框架见 `D6_M_TO_N_EVALUATION_FRAMEWORK_REVIEW.md`。D6 已实现 `TargetDemandRecord/CoalitionRecord/ArrivalRecord`，扩展 assignment/terminal coalition/member 合同，并接入 JSONL、`EpisodeMetrics`、CSV/batch summary/Markdown。已实现 target demand micro/macro、unmet slots、over-support、formation/reconfiguration、simultaneous common-window、sequential wave、hybrid primary/reserve、geometry rejection、canonical duplicate/cross-node IDSW/common-information duplicate rejection、planned/authorized/erroneous lock、same-resource lock continuity、center replan lifecycle、member loss/replacement/digest/stale、messages/bytes/rounds/latency 和 minimum separation/collision exposure。NIS/NEES 继续复用既有 D2 governance 字段，不复制同义指标。

通用 `duplicate_terminal_lock_count` 现在严格按同一 timestamp+target 的不同 resource 计数并保持独立；授权 coalition 内不超过 `k` 的同帧多锁进入 `authorized_cooperative_lock_count`，只有 legacy `k=1`、版本冲突或超需求进入 `erroneous_duplicate_lock_count`。同一 resource 跨帧续锁只进入 continuity。探测 POD/miss/FAR 同时要求 truth opportunity 和离线 match/miss 配对裁决；仅有 truth 列表且全部 center track truthless 时为 `None/unavailable`，不判 POD=0 或虚警。每项新增指标显式记录 unavailable、available zero 或 not_applicable，batch summary 分开计数。剩余 P1 是上游按冻结合同生产真实 M 对 N/replan 日志，并执行四路线 x 三中心层级 x 几何/同步/通信/成员失效实验矩阵。既有 TrackEval/py-motmetrics、Stone Soup、OSPA/GOSPA、HOTA/IDF1、AirSim recording 继续为 P2，SCRIMMAGE bridge 继续为 P3，D6 online/live control 继续禁止。

本节按 `EVAL/FRAMEWORK_EVAL_P0_P1_P2_GAP_CONFIRMATION.md` 以及三个 patch 同步 D6 相关 P0/P1 缺口。口径与 EVAL 保持一致：当前没有运行级 P0 blocker；P0 是进入更可信 AirSim/封闭场地验证前的工程化硬化项，P1 是三个月内的标准化报告、对照统计、场景库和回归化工作。D6 继续只消费日志和已写盘 metrics，不参与控制、重规划、降级仲裁、末端配准或导引。

2026-07-10 P1 报告聚合已修复：旧逐 seed `GROUP_FIELDS` 和 records/summary 文件保持不变，新增 cross-seed aggregate 与严格 baseline/enhanced seed 配对。原始 `scenario_version` 在 records 中保留；统计键移除其中 seed 运行参数，避免真实 `seed1..seedN` 被拆成 N 个单样本组。配对仍要求稳定 `scenario_group`、规范化版本、实际规模、几何、backend 和 seed 一致；case-specific scenario/case_name 只审计。单一配对样本标记 `descriptive_only`，不输出伪 bootstrap CI/effect size。active-degradation 四字段优先消费 d4d5 stress 显式标注，再 fallback main metrics；label count 为 0 时 precision unavailable/null。

同日复核 `p1_gap_closure_2v2_smoke_20260710/episode_006_full_flow`：D6 从正式 execution main-bus 文件读得实际规模 `2/2/2/2`、`intercept_success_count=2`、`visual_png_switch_count=3`，contract 文件独立读取；D6 不消费 Blocks summary 中仍为 `3/3/2/0` 的旧 `integrated_result.metrics`。新增回归测试固定该优先级并保证 execution/contract record 的 evidence path 分别指向各自文件。旧 Blocks 摘要不一致属于 main runtime P1，不是 D6 控制或回写职责。

10-seed 拦截聚合缺口已在 D6 侧关闭。calibration record/CSV/summary/cross-seed 已加入 success、collision/range/abort、min range、time-to-intercept、visual PNG switch、terminal switch allowed/takeover 和 gate reject。availability gate 已补：只有 intercept summary/control command/显式 pair-status/D7 execution event 证据才消费这些字段；episode_001..005 read-only 默认零改为 unavailable，且不进入 Outcome 表。现有 `seed001..010` summaries 实测 full-flow execution 仍为 `18/20`、collision/range/abort=`18/0/2`；execution/contract 按 scope 分组，未混合。计数行输出 sum，拦截 outcome 额外输出 opportunity/rate。

D6 owner 2026-07-11 验收为 `67 passed`，`git diff --check` 通过。execution/contract 双口径、各自 evidence path、truth/evidence availability、read-only unavailable、cross-seed aggregate、paired bootstrap、二级 lifecycle、YOLO/MOT 核心预算、四导引律同 seed 报告、D1-D3 governance、scenario library、M 对 N 锁定口径和 replan 生命周期聚合均归入“已实现并保持回归”。下一阶段缺口转向真实多 seed/CI trends、上游 M 对 N/replan evidence、CV 5v5 D1-D3 联合聚合、YOLO/MOT 扩展资源字段和完整标准化报告。

现有已完成状态保持不降级：`EpisodeMetrics`、`TrackRecord`、`AssignmentRecord`、`EventRecord`、`LinkRecord` 和 `TerminalRecord` 已作为 D6 离线指标主线保留；D7 guidance records 当前由 `guidance_records.csv`、`guidance_summaries.json` loader 转换为 `d7_guidance_record/d7_guidance_summary` 事件 metadata，而不是单独在线控制数据类。`id_switch_count`、实际规模字段、execution/contract 双口径、AirSim calibration bundle、detect-to-registration 漏斗、reject/outcome reason 分布和 D6 只消费日志不控制的边界均保持为已完成能力。

| EVAL 等级 | 同步条目 | D6 当前实施状态 | 已有证据/保留状态 | 剩余验收口径 |
|---|---|---|---|---|
| P0-A | 系统级任务成功指标 | 已实现，持续真实批次回归 | 每个 episode 已输出 `mission_outcome=success/partial/failed/aborted`、`success_reason`、`failure_reason`；显式 outcome 优先，上游缺失时从 intercept/abort/runtime/safety/部分进展指标被动派生。 | 在真实 AirSim 多 seed、5v5/N-v-N 和非默认 episode 中持续写盘并比较 execution/contract 口径。 |
| P0-A | failure reason/root cause 根因诊断 | 已实现，持续真实批次回归 | 已输出 terminal switch/contract reject reason、D5 detect-to-registration reject/outcome reason、D4 review label/后验字段和 D7 guidance reject metadata；新增 `top_failure_causes`、`root_cause`、`failure_cause_scores`、`failure_cause_details`。 | 根因类别保持被动消费，覆盖 tracking、assignment、terminal_gate、guidance、coverage、runtime_exception、communication、safety、performance；后续只随真实日志字段扩展。 |
| P0-A | 性能和可复现字段 | 已实现最小 schema，持续真实批次回归 | 新增 `module_duration_ms`、`loop_latency_ms`、`record_latency_ms`、`cpu_budget_utilization`、`gpu_budget_utilization`、`performance_budget_violation_count`；`eval_priority`、`implementation_status`、`evidence_path` 已进入 `EpisodeMetrics`、episode CSV、metadata 和 Markdown EVAL Tracking 表。 | main/D1-D7 真实 episode 持续写 module timing、loop latency、record latency、CPU/GPU budget、真实 evidence path 和 scenario/version metadata；D6 只消费。 |
| P0-A | 标准化评估映射最小版 | 已实现，持续真实批次回归 | 新增 `standard_mapping.py`，固定 `cuas-standard-map-v1`，输出 `engineering_metric`、`standard_metric_family`、`standard_sources`、`implementation_status`、`evidence_requirement`；`EpisodeMetrics` 增加 `scenario_version`、`standard_mapping_version`、`standard_metric_family_summary`；episode CSV、metadata、Markdown 和 `standard_metric_mapping.csv` 已输出映射。 | 真实 AirSim 多 seed、5v5/N-v-N 和非默认 episode 持续写真实 `scenario_version`、`evidence_path` 和同一 mapping version；不要求完整认证流程。 |
| P1 | COURAGEOUS/MDPI/OCEF 完整标准化报告 | P1 待补 | WebSearch patch 确认 COURAGEOUS/CEN、MDPI 综述和 OCEF 可复现纪律是 D6 标准化方向；当前已有本地最小映射、CSV/JSON/Markdown 指标报告。 | 在 P0 最小映射基础上增加测试阶段、复现纪律字段、evidence index、标准场景覆盖和外部审计说明；完整封闭场地/外部审计报告仍依赖 main 提供场景和日志。 |
| P1 | 基线对比和统计显著性 | 配对统计实现完成，待真实批次验证 | 保留旧逐 seed summary；新增 cross-seed aggregate、规范化 seed-bearing scenario version、严格 role/seed/actual-scale/geometry/backend 配对、missing seed、delta mean/std、paired Cohen's dz 和确定性 bootstrap 95% CI；单 pair 仅描述。 | main 持续提供显式 comparison role 和至少两个真实多 seed/N-v-N 成对数据；缺失/单一配对不形成 A/B 推断结论。 |
| P1 | 场景库管理 | D6 接口已实现，main/CI 接线待补 | `ScenarioLibrary` 已输出 stable scenario group/version、tags、difficulty、expected failure modes、parameters、seed matrix 和 online truth policy；`2v2/5v5` 只作为 baseline 名称。 | main/CI 使用标准场景库调度真实批次，并回填 coverage/evidence/trend 状态。 |
| P1 | CI 回归摘要 | P1 待补 | 当前有 D6 unit tests、报告生成测试、main bus loader 测试和手动 batch report 链路。 | 每次变更产出实验级测试矩阵、P0/P1 tracking 字段检查、性能回归摘要和 evidence path 检查。 |

P1 缺口保持为离线评估能力、真实 episode 写盘和长期趋势问题，不是 D6 在线控制职责：D7 real execution metrics 的正式/contract 双口径已完成；D6 已补 `metric_scope`、seed/scenario/实际规模报告分组、main bus metrics JSON loader、reject reason 分布输出、二级视角/侦察云台 coverage/cross-view/registration/pointing-error 指标、detect-to-registration 分层漏斗、50m vs 200m 覆盖对比、baseline vs enhanced 表格、AirSim 多 seed calibration 自动汇总，以及 `active_degradation_precision`/`unnecessary_active_degradation_count` 的 review label/后验最小实现。main runtime P1 sweep 已自动调用 D6 bundle，D6 当前 P1 重点是 COURAGEOUS/MDPI/OCEF 完整报告、统计显著性/非参数 CI、场景库、CI 回归摘要、多 seed 自动汇总回归、coverage/funnel/gimbal/projection/gate/stable registration 长期趋势、active degradation precision 真实标签、D7 guidance reject reason 和 actual scale 分组；剩余项是更多批次的数据沉淀，以及 main/D4/D5/D7 在真实 episode 中持续写出可对齐的 D4/D5/D7/Blocks 文件。D6 按实际 `drone_count/resource_count/target_count/camera_count` 归一化，`2v2/5v5` 只作为 baseline 场景名。

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
| D4 active/passive 降级基线 | 已实现 `active_degradation_count`、`active_degradation_precision`、`active_degradation_label_count`、`unnecessary_active_degradation_count` 等；label count 为 0 时 precision 为 unavailable/null。 | `metrics.py`; `main_bus.py`; `d4_replay.py`; `tests/test_d4_replay.py`; `tests/test_metrics.py`; `tests/test_main_bus_metrics.py` |
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
| AirSim 多 seed calibration 汇总 | 已实现。旧 records/逐 seed summary 不变；新增 `airsim_calibration_cross_seed_aggregate.csv`、`airsim_calibration_paired_comparison.csv`、`airsim_calibration_aggregate.json`、`airsim_calibration_aggregate_report.md`，包含严格配对、missing seed、effect size 和 bootstrap CI。 | `airsim_calibration.py`; `tests/test_airsim_calibration.py` |
| 2v2/N-v-N 拦截多 seed 汇总 | 已实现。records/summary/cross-seed 覆盖 success、collision/range/abort、min range、intercept time、visual PNG、terminal switch/takeover 和 gate reject；outcome 有 sum/opportunity/rate。availability gate 排除 read-only 默认零；10-seed 实测只由 full-flow 输出 `18/20`。 | `airsim_calibration.py`; `tests/test_airsim_calibration.py`; 现有 10-seed summaries |
| P1 detect-to-registration 与 coverage 校准漏斗 | 已实现。records/summary/Markdown 显式输出 `secondary_detect_count`、`secondary_visible_target_union_ratio`、`secondary_network_joint_full_view_frame_rate`、`projection_valid_rate`、`geometry_gate_pass_rate`、`registered_candidate_count`、`stable_cross_view_registration_count`、`not_registered_count`，固定保留八类 reject/outcome reason，并新增 50m vs 200m 覆盖对比、coverage funnel 与 baseline/enhanced 表格。 | `airsim_calibration.py`; `tests/test_airsim_calibration.py` |

## 部分实现

| 能力 | 当前状态 | 为什么只是部分实现 | 缺少条件 | 优先级 |
|---|---|---|---|---|
| D7 real execution metrics 回灌到正式 main bus metrics | D6 消费主线已完成。2v2 实测正式 execution 为 `2/2/2/2`、成功 2、visual PNG switch 3；contract 独立保留。 | 同 episode 的 Blocks legacy integrated snapshot 仍过时；D6 已忽略并用测试固定 main-bus 优先级，不负责回写运行时。 | main 修复 Blocks/sequence summary 的旧快照一致性；多 seed、5v5/N-v-N 持续采用同一双口径。 | D6 P1 已完成，main P1 待对齐 |
| 真实 episode 日志完整性 | D6 已有 Blocks、D4 loader、D5/terminal/multi-view 指标和 D7 guidance/intercept loader；可以消费写盘文件。历史 mobile recon stress 已提供 D4/D5 stress metrics 旧证据；当前 P1 registration calibration v2 已提供 single seed x 3 case 的 AirSim calibration bundle。 | D6 loader 是离线入口，不负责 main runtime 写盘、目录扫描、episode clock 对齐或多 loader 合并调度。 | 每个 episode 目录稳定写出 Blocks/D4/D5/D7/D6 日志；汇总脚本合并到一个 `MetricsCollector`；同一 episode clock 和实际规模字段。 | P1 |
| D4 review/window 真实写盘 | D6 已实现 `active_degradation_precision` 与 `unnecessary_active_degradation_count` 的最小可测口径，D4 CSV loader 可消费 review label、trigger/decision timestamp、selected coordinator、coverage cell 和 pre/post window 字段。 | 真实 AirSim episode 是否每次写出 review/window 字段仍取决于 main/D4；缺 label 的 active degradation 不进入 precision 分母。 | main/D4 持续写盘；固定 pre/post 窗口；后续扩展 decision latency、ID switch delta、assignment conflict delta。 | P1 |
| 多 seed execution/contract 报告口径 | D6 已按 `metric_scope/seed/scenario_group/drone_count/resource_count/target_count/camera_count` 输出通用 summary，并新增 AirSim calibration 分组到 `metric_scope/seed/scenario/comparison_role/secondary_height/FOV/secondary_count/detection_backend`。 | 仍需要真实批量 episode 持续提供 execution metrics 与 contract metrics；D6 不从 `2v2/5v5` 场景名推断规模。 | 多 seed、5v5/N-v-N 和非默认 episode 的正式 metrics 与 raw contract metrics 成对落盘。 | P1 持续回归 |
| 移动侦察云台 AirSim 报告字段 | D6 已有被动指标、Markdown 对比表和 AirSim calibration 自动汇总，可消费 `mobile_recon_gimbal` metadata；历史 stress 验证了 gimbal、coverage、funnel、bbox 字段可落盘，当前 registration calibration v2 进一步验证 projection/gate/stable registration/not-registered/D7 reject 可进入 bundle；2026-07-09 已新增 50m/200m、coverage funnel、baseline/enhanced 和 trend/evidence 字段。 | v2 仍只是 single seed、3 case；现有结果只能说明报告链路可用，长期趋势和阈值校准还缺更多真实 AirSim 多 seed/N-v-N 数据与 review labels。 | 用新增汇总报告持续比较 `mobile_recon_gimbal` / `fixed_downlook_secondary` 的 coverage、funnel、projection/gate、stable registration、not-registered、D7 reject、bbox、cue/gimbal pointing 指标。 | P1 持续回归 |
| 多视角末端几何质量 | 已能统计 consensus/conflict/duplicate lock 和 bbox delivery。 | 尚未计算跨视角重投影误差、外参质量评分或时延补偿。 | 稳定相机标定、跨节点时钟、D5 输出几何误差字段和候选集。 | P2 |
| 批量统计 CI | 通用 summary 已输出正态近似 95% CI；AirSim baseline/enhanced 已新增 paired percentile bootstrap 95% CI。 | 非配对的其他长尾/偏态指标仍未统一使用 bootstrap。 | 足够多真实 episode；按指标选择方法并标注。 | P2 |
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

1. M 对 N 真实证据：D6 合同与聚合已实现；下一步由 D3/main/runtime 写出冻结 schema，运行 12 组合多 seed 实验并验证真实 formation/arrival/wave/member/communication/safety evidence。D6 不修改上游生产逻辑。
2. `ScenarioLibrary` 已实现；下一步由 main/CI 使用标准化 scenario group/version、tags、difficulty、expected failure modes、actual scale、seed matrix 和 evidence path 调度真实批次，再输出跨提交趋势和阈值回归摘要。
3. CV 5v5 D1-D3 联合聚合：按同一 episode clock 合并 D1 detection/fusion/latency/covariance、D2 association/continuity/ID switch、D3 assignment/version/hysteresis，形成感知到分配的漏斗与失败归因。前置条件是 main/D1-D3 提供稳定 schema 和证据路径。
4. YOLO/MOT 核心 recall/continuity/cross-view/latency/CPU/GPU budget 已实现；下一步消费 D5 的 model version、输入分辨率、目标像素尺度、throughput、内存、drop/fallback 字段，形成完整 accuracy-latency-budget 报告；D6 不加载权重或执行检测。
5. COURAGEOUS/MDPI/OCEF 完整标准化报告：补测试阶段、复现纪律、evidence index、场景覆盖矩阵、限制条件和外部审计说明。
6. 真实成对多 seed/N-v-N 数据：继续验证已实现的 paired effect size/bootstrap CI；无配对、单 pair、read-only unavailable 或无 review label 时不得输出推断结论。
7. D4/D5 长期趋势：持续消费 coverage/funnel/gimbal、projection/gate/registration 和真实 active-degradation review/window 标签。
8. execution/contract/evidence availability 仅保持回归，不再新增重复或同义拦截字段。

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
