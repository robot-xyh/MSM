# D6 实现差距审计

审计范围：`research_modules/d6_evaluation_metrics/**` 的当前代码、测试和文档，以及 `subagent_reviews/D6_*`。本文只评估 D6 离线指标模块状态；D6 消费日志，不参与控制，不生成任务、授权、导引、火控、毁伤或自动处置动作。

## 总体结论

D6 当前已经实现一条轻量、可测试、离线的系统评估主线。`TrackRecord`、`AssignmentRecord`、`EventRecord`、`LinkRecord`、`TerminalRecord` 进入 `MetricsCollector`，输出 `EpisodeMetrics`、CSV、Markdown 和 PNG 图表。`EpisodeMetrics` 已包含探测、跟踪、分配、降级、末端、通信、D7 gate/intercept 和安全指标。

规模字段 `drone_count/resource_count/target_count/camera_count` 已进入 `EpisodeMetrics`、CSV、summary 和 Markdown 报告。D6 按实际记录或 `truth_summary` 字段归一化与分组；测试覆盖了场景名包含 `5v5` 但实际规模为 `3/3/4/6` 的情况。因此当前 D6 不从 `2v2/5v5` 场景名推断规模。

D2/D6 强制 `id_switch_count` 的规则已落实：`id_switch_count` 是 `EpisodeMetrics.metric_names()` 的显式字段，并有单元测试覆盖。

尚未完成的是外部 benchmark 和更深的 integrated runtime 汇总：Stone Soup metrics、TrackEval/py-motmetrics、OSPA/GOSPA/HOTA/IDF1、AirSim 原生 recording replay、live AirSim replay 和 SCRIMMAGE metrics bridge 都没有实际 import、adapter 或测试。D4/D5/D7 的离线产物已有 D6 侧 loader/指标消费能力，但完整 integrated episode metrics 仍依赖 main runtime 把所有产物写到同一 episode 目录并调用 D6 loader 合并。

## 已实现

| 能力 | 当前状态 | 代码/测试证据 |
|---|---|---|
| `EpisodeMetrics` | 已实现。包含 episode metadata、实际规模字段、八类指标和 `metadata`。 | `research_modules/d6_evaluation_metrics/d6_evaluation_metrics/metrics.py`; `tests/test_metrics.py` |
| 规模归一化 | 已实现。优先使用 `truth_summary` 或 Blocks replay 的实际 `drone_count/resource_count/target_count/camera_count`，缺失时从记录推断；报告按实际规模分组。 | `metrics.py`; `reporting.py`; `tests/test_metrics.py`; `tests/test_reporting_and_simulation.py`; `tests/test_blocks_replay.py` |
| 基础记录模型 | 已实现 `TrackRecord`、`AssignmentRecord`、`EventRecord`，并扩展 `LinkRecord`、`TerminalRecord`。 | `metrics.py`; `jsonl.py`; `tests/test_airsim_dry_run_jsonl.py` |
| 探测指标 | 已实现 `detection_probability`、`false_alarm_rate`、`missed_detection_rate`。 | `metrics.py`; `tests/test_metrics.py`; `tests/test_blocks_replay.py` |
| 跟踪指标 | 已实现 `track_rmse`、`track_continuity`、`id_switch_count`。`id_switch_count` 对同一 `truth_id` 的 `global_track_id` 变化显式计数。 | `metrics.py`; `tests/test_metrics.py` |
| 分配指标 | 已实现 `duplicate_assignment_count`、`unassigned_high_threat_count`，并按 active + 有效授权状态过滤。 | `metrics.py`; `tests/test_metrics.py` |
| 基础降级指标 | 已实现 `failover_time`、`consensus_rounds`、`degraded_completion_rate`。 | `metrics.py`; `tests/test_metrics.py` |
| D4 active/passive 降级基线 | 已实现 `active_degradation_count`、`passive_failover_count`、`secondary_node_takeover_count`、`secondary_reassignment_count`、`d4_reassign_pending_count`、`distributed_fallback_count`、`failover_active_window_delta_s`，并保留触发原因分布。 | `metrics.py`; `d4_replay.py`; `tests/test_d4_replay.py`; `tests/test_metrics.py` |
| 末端指标 | 已实现 `terminal_association_accuracy`、`terminal_id_switch_count`、`ambiguous_fov_event_count`、`friend_overlap_hold_count`、`time_to_terminal_lock`、`terminal_lock_count`。 | `metrics.py`; `tests/test_metrics.py` |
| 多视角/无 PNG 评估 | 已实现基础能力。Blocks replay 可用 bbox、相机内外参、timestamp、object label 和 truth label 生成 terminal、video/bbox link、多视角 consensus/conflict。PNG 不作为指标必需输入。 | `blocks_replay.py`; `tests/test_blocks_replay.py` |
| 通信链路指标 | 已实现 latency、drop、out-of-order、stale、video metadata delivery、bbox delivery、consensus latency。 | `metrics.py`; `tests/test_metrics.py`; `tests/test_blocks_replay.py` |
| D7 intercept replay | 已实现。读取 `control_commands.csv` 和 `intercept_summary.json`，计算 success、collision/range intercept、min range、time to intercept、gate reject 等。 | `intercept_replay.py`; `tests/test_intercept_replay.py` |
| D7 guidance time-series | 已实现。读取 `guidance_records.csv`、`guidance_summaries.json`，保留 mode switch、terminal contract reject、D4/D5 state、plan/version、guidance law。 | `intercept_replay.py`; `metrics.py`; `tests/test_intercept_replay.py` |
| D7 terminal gate/visual PNG switch | 已实现 `camera_quality_gate_pass_rate`、`los_quality_gate_pass_rate`、`maneuver_margin_gate_pass_rate`、`terminal_switch_allowed_rate`、`visual_png_switch_count`、`terminal_takeover_rate`、`terminal_switch_reject_count`。 | `metrics.py`; `tests/test_metrics.py`; `tests/test_intercept_replay.py` |
| 安全指标 | 已实现 `constraint_violation_count`、`human_override_count`。 | `metrics.py`; `tests/test_metrics.py` |
| 批量统计/报告图表 | 已实现 episode CSV、summary CSV、Markdown、按指标族 PNG 图和 selected distribution 图；summary 包含 count/mean/std/stderr/95% CI/median/p05/p95。 | `reporting.py`; `scripts/run_batch_example.py`; `tests/test_reporting_and_simulation.py` |
| JSONL 标准化接口 | 已实现 `truth_summary/track/assignment/event/link/terminal`，未知 record type 报错。 | `jsonl.py`; `tests/test_airsim_dry_run_jsonl.py` |

## 部分实现

| 能力 | 当前状态 | 为什么只是部分实现 | 缺少条件 | 优先级 |
|---|---|---|---|---|
| D4/D5/D7 AirSim 产物回灌到 integrated episode metrics | D6 已有 Blocks、D4、D7 loader 和 D5/terminal/multi-view 指标；可以消费写盘文件。 | D6 loader 是离线入口，不负责 main runtime 写盘、目录扫描、episode clock 对齐或多 loader 合并调度。 | main 在每个 episode 目录稳定写出 Blocks/D4/D5/D7/D6 日志；汇总脚本合并到一个 `MetricsCollector`；同一 episode clock 和实际规模字段。 | P1 |
| D5 terminal/multi-view AirSim 全量回灌 | D6 已能评估 `TerminalRecord`、terminal events、Blocks bbox/camera metadata。 | 当前不能保证每条真实 AirSim episode 都已有 D5 terminal consistency、cross-view conflict、duplicate lock、friend hold、validation label 写盘。 | main/D5 写出 terminal association、identity claim、conflict/hold/lock、validation label、bbox、相机参数、timestamp。 | P1 |
| 主动降级必要性/精度 | D6 已能统计 active/passive 次数、secondary takeover/reassignment、pending、distributed fallback、窗口 delta。 | `active_degradation_precision`、`unnecessary_active_degradation_count` 等需要 review label 或稳定后验规则，不能只靠事件名判断。 | `review_label`、`trigger_timestamp`、`decision_timestamp`、`selected_coordinator`、`coverage_cell`、固定 pre/post 窗口。 | P1 |
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
3. 主动降级“是否必要”不能由 D6 只看事件名自证，需要 D4/main 写入 review label 或稳定后验判据。
4. AirSim 原生 recording 和 SCRIMMAGE 都需要样例、schema、ID 映射和时钟/坐标对齐规则。
5. D6 不参与控制是模块边界，所有指标只用于离线报告和回归分析。

## P1 下一步

1. main integrated episode 汇总接线：每个 AirSim episode 目录写出 Blocks、D4、D5、D7 和 D6 标准化日志，并由 main 调用 D6 loader 合并成同一 `EpisodeMetrics`。
2. D4 主动降级质量：补 `review_label`、`trigger_timestamp`、`decision_timestamp`、`selected_coordinator`、`coverage_cell` 和 pre/post 窗口，形成必要性与改善 delta。
3. D5 末端回灌：稳定写出 terminal association、identity claim、cross-view conflict、duplicate lock、friend overlap hold、terminal-center disagreement 和 validation label。
4. D7 多 seed 汇总：确保 guidance/control/intercept 文件在 2v2、5v5、N-v-N 下持续产出，并保留 plan/version、D4/D5 state、guidance law、reject reason。
5. 报告增强：按实际 `drone_count/resource_count/target_count/camera_count` 和 `scenario_group` 输出 D4/D5/D7 分组解释，不从场景名推断规模。

## P2 下一步

1. 定义 frame-level truth/detection/track 匹配表，为 TrackEval/py-motmetrics/Stone Soup 提供输入。
2. 优先接 py-motmetrics 或 TrackEval adapter，作为可选 benchmark。
3. 在 D1/D2 对象映射和版本锁定后接入 Stone Soup metrics 与 OSPA/GOSPA。
4. 仅在 Blocks JSONL 不足时增加 AirSim 原生 recording parser。
5. 为长尾指标增加 bootstrap 或非参数 CI。
6. 只有当 AirSim 多机规模或通信建模不足以回答实验问题时，再推进 SCRIMMAGE bridge。

## 验收建议

```bash
pytest -q research_modules/d6_evaluation_metrics/tests
git diff --check -- research_modules/d6_evaluation_metrics subagent_reviews/D6_*
```
