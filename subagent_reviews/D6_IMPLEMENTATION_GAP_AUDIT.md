# D6 实现差距审计

审计范围：`research_modules/d6_evaluation_metrics/**` 的当前代码、测试和文档，以及 `subagent_reviews/D6_*`。本文只评估 D6 离线指标模块状态；D6 消费日志，不参与控制，不生成任务、授权、导引、火控、毁伤或自动处置动作。

## 总体结论

D6 当前已经实现一条轻量、可测试、离线的系统评估主线。`TrackRecord`、`AssignmentRecord`、`EventRecord`、`LinkRecord`、`TerminalRecord` 进入 `MetricsCollector`，输出 `EpisodeMetrics`、CSV、Markdown 和 PNG 图表。`EpisodeMetrics` 已包含探测、跟踪、分配、降级、主动降级必要性标签口径、末端、二级视角/侦察云台、通信、D7 gate/intercept 和安全指标。D6 现在也能直接读取 main runtime 已写盘的 `main_episode_bus_metrics.json` 与 `main_episode_bus_contract_metrics.json`，把 execution/contract 双口径还原为 `EpisodeMetrics`。

规模字段 `drone_count/resource_count/target_count/camera_count` 已进入 `EpisodeMetrics`、CSV、summary 和 Markdown 报告。D6 按实际记录或 `truth_summary` 字段归一化；二级网络 full-view/coverage 与单相机 full-view 指标按实际 target/camera count 或日志显式实际计数归一化；报告按 `metric_scope/seed/scenario_group/drone_count/resource_count/target_count/camera_count` 分组；episode CSV 保留 metadata JSON，Markdown 在存在数据时输出 fixed downlook secondary vs mobile recon gimbal 对比表和 terminal switch/contract reject reason 分布；测试覆盖了场景名包含 `5v5` 但实际规模为 `3/3/4/6` 的情况。因此当前 D6 不从 `2v2/5v5` 场景名推断规模。

D2/D6 强制 `id_switch_count` 的规则已落实：`id_switch_count` 是 `EpisodeMetrics.metric_names()` 的显式字段，并有单元测试覆盖。

尚未完成的是外部 benchmark 和真实 episode 批量验收：Stone Soup metrics、TrackEval/py-motmetrics、OSPA/GOSPA/HOTA/IDF1、AirSim 原生 recording replay、live AirSim replay 和 SCRIMMAGE metrics bridge 都没有实际 import、adapter 或测试。D4/D5/D7 的离线产物已有 D6 侧 loader/指标消费能力。2026-07-07 起，main/orchestrator 已把真实 D7 AirSim 执行后的 `control_commands.csv` 与 `intercept_summary.json` 合并进正式 `main_episode_bus_metrics.json`，并把执行前合同检查保留为 `main_episode_bus_contract_metrics.json`；剩余 P1 聚焦真实 episode 持续写 D4 review/window 等字段，以及多 seed、5v5/N-v-N、非默认 episode 的双口径报告验收。

2026-07-08 main 最新 AirSim 机动高空侦察节点测试输出在 `research_modules/airsim_runtime/outputs/p1_d4d5_mobile_recon_20260708_055948*`。该批次为 5v5 D4/D5 stress，3 seeds，每个 seed 3 case，二级侦察节点为 200 m 高差 `mobile_recon_gimbal/mobile_high_recon`，二级相机 80 deg FOV、1920x1080；所有 episode 均 `connected=True`，13 frames，`image_ok_count=13`。D6 已能消费这类 `mobile_recon_gimbal` 与 `fixed_downlook_secondary` 指标。结果显示 `secondary_gimbal_pointing_ok_rate=1.0`，`secondary_network_joint_full_view_frame_rate=0.0`，`secondary_network_mean_coverage_ratio` 聚合均值约 0.67，bbox mean 约 3.3k px^2，主要断点为 `not_all_targets_visible` 与 `network_union_incomplete`。相对固定俯视 200 m/110 deg，bbox 面积明显提升，但 full-view 仍未解决。

## P0/P1 复核结论

无 P0 blocker。`EpisodeMetrics`、`TrackRecord`、`AssignmentRecord`、`EventRecord`、`LinkRecord` 和 `TerminalRecord` 已作为 D6 离线指标主线保留；D7 guidance records 当前由 `guidance_records.csv`、`guidance_summaries.json` loader 转换为 `d7_guidance_record/d7_guidance_summary` 事件 metadata，而不是单独在线控制数据类。`id_switch_count`、实际规模字段和 D6 只消费日志不控制的边界均已写入 README/PLAN/GAP。

P1 缺口保持为真实 episode 写盘、自动汇总和长期趋势问题，不是 D6 在线控制职责：D7 real execution metrics 的正式/contract 双口径已完成；D6 已补 `metric_scope`、seed/scenario/实际规模报告分组、main bus metrics JSON loader、reject reason 分布输出、二级视角/侦察云台 coverage/cross-view/registration/pointing-error 指标，以及 `active_degradation_precision`/`unnecessary_active_degradation_count` 的 review label/后验最小实现。剩余项是多 seed 报告自动汇总、coverage/funnel/gimbal 指标长期趋势、main/D4 写出真实 `review_label`/后验字段支撑 active degradation precision，以及 main/D4/D5/D7 在真实 episode 中持续写出可对齐的 D4/D5/D7/Blocks 文件。

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
| JSONL 标准化接口 | 已实现 `truth_summary/track/assignment/event/link/terminal`，未知 record type 报错。 | `jsonl.py`; `tests/test_airsim_dry_run_jsonl.py` |
| main bus metrics JSON | 已实现。读取 `main_episode_bus_metrics.json` 与 `main_episode_bus_contract_metrics.json`，还原 execution/contract `EpisodeMetrics`，保留 seed/scenario/实际规模和 metadata 分布。 | `main_bus.py`; `tests/test_main_bus_metrics.py` |
| 二级节点对比与 reject reason 报告输出 | 已实现。episode CSV 保留 metadata JSON；Markdown 在有数据时输出 fixed downlook secondary vs mobile recon gimbal 对比表，以及 terminal switch/contract reject reason 分布。 | `reporting.py`; `tests/test_reporting_and_simulation.py` |

## 部分实现

| 能力 | 当前状态 | 为什么只是部分实现 | 缺少条件 | 优先级 |
|---|---|---|---|---|
| D7 real execution metrics 回灌到正式 main bus metrics | 已完成主线。main/orchestrator 把 `control_commands.csv` 与 `intercept_summary.json` 合并进正式 `main_episode_bus_metrics.json`，并保留 raw `main_episode_bus_contract_metrics.json`。 | D6 仍只消费文件，不负责运行 D7 或写正式 metrics；多 seed 验收属于批量报告口径。 | 在多 seed、5v5/N-v-N 和非默认 episode 中持续产出并采用同一双口径。 | P1 已完成，持续回归 |
| 真实 episode 日志完整性 | D6 已有 Blocks、D4 loader、D5/terminal/multi-view 指标和 D7 guidance/intercept loader；可以消费写盘文件。2026-07-08 mobile recon stress 已提供 3 seeds x 3 cases 的 D4/D5 stress metrics。 | D6 loader 是离线入口，不负责 main runtime 写盘、目录扫描、episode clock 对齐或多 loader 合并调度。 | 每个 episode 目录稳定写出 Blocks/D4/D5/D7/D6 日志；汇总脚本合并到一个 `MetricsCollector`；同一 episode clock 和实际规模字段。 | P1 |
| D4 review/window 真实写盘 | D6 已实现 `active_degradation_precision` 与 `unnecessary_active_degradation_count` 的最小可测口径，D4 CSV loader 可消费 review label、trigger/decision timestamp、selected coordinator、coverage cell 和 pre/post window 字段。 | 真实 AirSim episode 是否每次写出 review/window 字段仍取决于 main/D4；缺 label 的 active degradation 不进入 precision 分母。 | main/D4 持续写盘；固定 pre/post 窗口；后续扩展 decision latency、ID switch delta、assignment conflict delta。 | P1 |
| 多 seed execution/contract 报告口径 | D6 已按 `metric_scope/seed/scenario_group/drone_count/resource_count/target_count/camera_count` 输出 summary 和 Markdown 分组，并可直接读取 main bus execution/contract metrics JSON。 | 需要真实批量 episode 持续提供 execution metrics 与 contract metrics；D6 不从 `2v2/5v5` 场景名推断规模。 | 多 seed、5v5/N-v-N 和非默认 episode 的正式 metrics 与 raw contract metrics 成对落盘。 | P1 |
| 移动侦察云台 AirSim 报告字段 | D6 已有被动指标和 Markdown 对比表，可消费 `mobile_recon_gimbal` metadata；2026-07-08 stress 已验证 gimbal OK、coverage、funnel breakpoint 和 bbox 指标可落盘。 | 仍缺 D6 批量报告层的跨 seed 自动汇总和长期趋势；当前批次显示 bbox 提升但 full-view 仍为 0.0。 | 把 `mobile_recon_gimbal` / `fixed_downlook_secondary` 的 coverage、funnel、bbox、cue/gimbal pointing 指标纳入长期趋势报告。 | P1 |
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

## P1 下一步

1. 多 seed 报告自动汇总：把 `p1_d4d5_mobile_recon_20260708_055948*` 这类跨 seed/case 输出自动汇总为 D6 批量 Markdown/CSV。
2. coverage/funnel/gimbal 长期趋势：跟踪 mobile recon 与 fixed downlook 的 coverage、full-view、funnel breakpoint、bbox area 和 cue/gimbal pointing 指标；当前 mobile recon bbox 面积提升，但 full-view 仍未解决。
3. active degradation precision 真实标签：main/D4 持续写入 `review_label`、`active_degradation_necessary` 或后验 outcome/risk 字段；D6 不从事件名推断必要性。
4. 真实 episode 日志完整性：D4/D5/D7/Blocks 产物持续落到同一 episode clock 和目录，D6 汇总阶段调用 loader 合并；D6 不参与控制、重规划或导引。
5. 多 seed 双口径报告：在 2v2、5v5、N-v-N 和非默认 episode 批量运行中持续保留 `metric_scope=execution/contract`、seed/scenario/实际规模字段、D7 guidance/control/intercept 元数据和 reject reason metadata；D6 已能读取 main bus 双口径 metrics JSON 并输出相应分组。

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
