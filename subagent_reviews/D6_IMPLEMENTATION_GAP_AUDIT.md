# D6 实现差距审计

审计范围：对照 `subagent_reviews/MAIN_IMPLEMENTATION_GAP_AUDIT.md`、`subagent_reviews/D6_EVALUATION_METRICS_REVIEW_AND_PLAN.md`、`C_UAS_MAINSTREAM_SOLUTIONS_AND_DIFFICULTIES.md`、`research_modules/d6_evaluation_metrics/README.md`、`PLAN.md`、`docs/ALGORITHM_AND_IMPLEMENTATION.md`、现有代码与测试。本文只评估 D6 离线指标实现状态；D6 消费日志，不参与控制，不生成任务、授权、导引或处置动作。

## 总体结论

D6 当前已经实现轻量、可测试的离线评估主线：`TrackRecord`、`AssignmentRecord`、`EventRecord`、`LinkRecord`、`TerminalRecord` 进入 `MetricsCollector`，输出 `EpisodeMetrics`、CSV、Markdown 和 PNG 图表。`EpisodeMetrics` 显式保留 `drone_count/resource_count/target_count/camera_count`，并由 `truth_summary` 或记录内容推断，测试覆盖了场景名为 `blocks_cv_5v5` 但实际规模为 3/3/4/6 的情况；因此当前 D6 不从 `2v2/5v5` 场景名推断规模。

与 main 总审计一致，D6 已具备 P0/P1 的本地指标、Blocks replay、D4 active/passive 降级、D7 intercept/guidance time-series 和批量报告基线。尚未落地的是 Stone Soup metrics、TrackEval/py-motmetrics、OSPA/GOSPA/HOTA/IDF1 标准输出、SCRIMMAGE 统计桥接和通用 AirSim recording 解析。这些缺口主要是外部对照和论文级评估能力，不阻塞当前 main 侧用 D6 消费 JSONL/CSV 日志做离线评估。

## 已实现

| 能力 | 当前状态 | 关键证据 |
|---|---|---|
| `EpisodeMetrics` 与规模归一化字段 | 已实现。包含 `drone_count/resource_count/target_count/camera_count`，`compute_episode()` 从 `truth_summary` 或记录集合推断实际规模，报告按这些字段分组。 | `research_modules/d6_evaluation_metrics/d6_evaluation_metrics/metrics.py`; `research_modules/d6_evaluation_metrics/d6_evaluation_metrics/reporting.py`; `research_modules/d6_evaluation_metrics/tests/test_metrics.py`; `research_modules/d6_evaluation_metrics/tests/test_reporting_and_simulation.py` |
| 基础记录模型 | 已实现。`TrackRecord`、`AssignmentRecord`、`EventRecord` 已实现，且补充了通信 `LinkRecord` 和末端 `TerminalRecord`。 | `research_modules/d6_evaluation_metrics/d6_evaluation_metrics/metrics.py`; `research_modules/d6_evaluation_metrics/docs/ALGORITHM_AND_IMPLEMENTATION.md` |
| 探测/跟踪/分配基础指标 | 已实现。覆盖 `detection_probability`、`false_alarm_rate`、`missed_detection_rate`、`track_rmse`、`track_continuity`、`id_switch_count`、`duplicate_assignment_count`、`unassigned_high_threat_count`。 | `research_modules/d6_evaluation_metrics/d6_evaluation_metrics/metrics.py`; `research_modules/d6_evaluation_metrics/tests/test_metrics.py` |
| 降级基础指标 | 已实现。覆盖 `failover_time`、`consensus_rounds`、`degraded_completion_rate`，并按事件流计算中心失效到稳定降级的时间。 | `research_modules/d6_evaluation_metrics/d6_evaluation_metrics/metrics.py`; `research_modules/d6_evaluation_metrics/tests/test_metrics.py`; `research_modules/d6_evaluation_metrics/docs/ALGORITHM_AND_IMPLEMENTATION.md` |
| D4 active/passive 降级细分 | 已实现 P1 基线。支持 `active_degradation_count`、`passive_failover_count`、`secondary_node_takeover_count`、`secondary_reassignment_count`、`d4_reassign_pending_count`、`distributed_fallback_count`、`failover_active_window_delta_s`，并可读取 D4 active-degradation CSV。 | `research_modules/d6_evaluation_metrics/d6_evaluation_metrics/metrics.py`; `research_modules/d6_evaluation_metrics/d6_evaluation_metrics/d4_replay.py`; `research_modules/d6_evaluation_metrics/tests/test_d4_replay.py`; `research_modules/d6_evaluation_metrics/tests/test_metrics.py` |
| 末端配准指标 | 已实现。覆盖 `terminal_association_accuracy`、`terminal_id_switch_count`、`ambiguous_fov_event_count`、`friend_overlap_hold_count`、`time_to_terminal_lock`、`terminal_lock_count`。 | `research_modules/d6_evaluation_metrics/d6_evaluation_metrics/metrics.py`; `research_modules/d6_evaluation_metrics/tests/test_metrics.py`; `research_modules/d6_evaluation_metrics/tests/test_blocks_replay.py` |
| 多视角/无 PNG 评估 | 已实现基础能力。D6 使用 bbox、相机内外参、timestamp、object label/truth label 和事件 metadata，不要求 PNG 截图；Blocks replay 可从同一 frame 多 camera 检测生成 multi-view consensus 事件。 | `research_modules/d6_evaluation_metrics/d6_evaluation_metrics/blocks_replay.py`; `research_modules/d6_evaluation_metrics/tests/test_blocks_replay.py`; `research_modules/d6_evaluation_metrics/README.md`; `research_modules/d6_evaluation_metrics/AIRSIM_INTEGRATION_PLAN.md` |
| Blocks replay | 已实现 D6-only 离线读取。支持 `blocks_frames.jsonl` 和可选 `blocks_sensor_observations.jsonl`，提取 truth、camera metadata、bbox、local track、object label、video metadata、D1 replay 观测和通信链路。 | `research_modules/d6_evaluation_metrics/d6_evaluation_metrics/blocks_replay.py`; `research_modules/d6_evaluation_metrics/tests/test_blocks_replay.py` |
| 通信链路指标 | 已实现。支持 latency、drop、out-of-order、stale、video metadata delivery、bbox delivery、consensus latency。 | `research_modules/d6_evaluation_metrics/d6_evaluation_metrics/metrics.py`; `research_modules/d6_evaluation_metrics/tests/test_metrics.py`; `research_modules/d6_evaluation_metrics/tests/test_blocks_replay.py` |
| D7 intercept replay | 已实现。读取 `control_commands.csv` 和 `intercept_summary.json`，计算拦截成功、碰撞阈值命中、距离阈值命中、最小距离、拦截时间、gate reject 等。 | `research_modules/d6_evaluation_metrics/d6_evaluation_metrics/intercept_replay.py`; `research_modules/d6_evaluation_metrics/tests/test_intercept_replay.py`; `subagent_reviews/MAIN_IMPLEMENTATION_GAP_AUDIT.md` |
| D7 guidance time-series | 已实现 P1 基线。读取 `guidance_records.csv` 与 `guidance_summaries.json`，保留 mode switch、terminal contract reject、D4/D5 state、plan/version、guidance law 等 metadata，并纳入 guidance 面板。 | `research_modules/d6_evaluation_metrics/d6_evaluation_metrics/intercept_replay.py`; `research_modules/d6_evaluation_metrics/d6_evaluation_metrics/metrics.py`; `research_modules/d6_evaluation_metrics/d6_evaluation_metrics/reporting.py`; `research_modules/d6_evaluation_metrics/tests/test_intercept_replay.py` |
| 批量图表/报告 | 已实现。输出 episode CSV、summary CSV、Markdown、分类 PNG 图；summary 包含 count/mean/std/stderr/95% CI/median/p05/p95，并按 scenario 与实际规模分组。 | `research_modules/d6_evaluation_metrics/d6_evaluation_metrics/reporting.py`; `research_modules/d6_evaluation_metrics/scripts/run_batch_example.py`; `research_modules/d6_evaluation_metrics/tests/test_reporting_and_simulation.py`; `research_modules/d6_evaluation_metrics/README.md` |
| JSONL 标准化记录接口 | 已实现。支持 `truth_summary`、`track`、`assignment`、`event`、`link`、`terminal`，未知 record type 报错。 | `research_modules/d6_evaluation_metrics/d6_evaluation_metrics/jsonl.py`; `research_modules/d6_evaluation_metrics/tests/test_airsim_dry_run_jsonl.py` |

## 部分实现

| 能力 | 当前状态 | 为什么只是部分实现 | 缺少条件 | 优先级 |
|---|---|---|---|---|
| Stone Soup metrics / SIAP / CLEAR MOT primitives | D6 已有 POD/FAR/RMSE/continuity/IDSW 等本地标量，可和 Stone Soup 指标交叉核对；未调用 Stone Soup metric generator。 | 当前主线保持轻依赖，且 D1/D2 尚未冻结 Stone Soup Track/Detection/GroundTruthPath 转换合同。 | 固定 Stone Soup 版本；D1/D2 到 Stone Soup 对象的 adapter；OSPA cutoff/order、SIAP/CLEAR MOT 匹配门限和坐标合同。 | P2 |
| TrackEval / py-motmetrics 对照 | D6 已实现 MOT/CLEAR MOT 相关基础分量和 IDSW 计数；未导出 MOTChallenge 格式，也未调用 TrackEval/py-motmetrics。 | 当前系统评估还覆盖分配、降级、通信、末端和导引，默认输出选择本地可解释指标；视觉 MOT 输出尚未形成稳定帧级表。 | 帧级 truth/detection/track 匹配表；IoU/距离门限；MOTChallenge 或 accumulator 导出；依赖版本和回归阈值。 | P2 |
| OSPA/GOSPA/HOTA/IDF1 | OSPA 公式写入 PLAN/算法文档，HOTA/IDF1 在审计和计划中列为对照目标；代码未输出这些标准指标。 | 需要标准帧级集合匹配和外部 evaluator，且当前本地标量已满足 main 集成回归。 | truth/estimate set 序列；cutoff/order；帧级匹配历史；TrackEval/py-motmetrics 或自研 evaluator；D1/D2/D5 稳定输出。 | P2 |
| 主动降级必要性/精度 | 已能统计 active/passive 次数、接管、pending 和窗口 delta；未完整实现 `active_degradation_precision` 与不必要主动降级计数。 | 这类指标需要离线 `review_label` 或一致的后验判据，否则 D6 只能统计发生次数，不能判定必要性。 | main/D4 写入 `review_label`、`trigger_timestamp`、`decision_timestamp`、`selected_coordinator`、`coverage_cell`；固定 pre/post 窗口和必要性规则。 | P1 |
| 多视角末端几何质量 | 已能统计 consensus/conflict/duplicate lock；未计算跨视角重投影误差、外参质量评分或视角间时延补偿。 | 当前 Blocks replay metadata 足以做基础统计，但几何质量需要更严格相机标定和跨节点时钟。 | 稳定 camera intrinsics/extrinsics；跨节点时钟同步；D5 输出冲突候选集、验证标签和几何误差字段。 | P1/P2 |
| 通用 AirSim recording 解析 | 已支持 main 写出的 Blocks JSONL；未解析 AirSim 原生 recording CSV 或其他录制格式。 | main 已把可评估字段转成 JSONL，直接解析原生 recording 会引入坐标、相机、字段版本差异。 | 原生 recording 样例；字段版本说明；recording 到 D6 Record 的转换规则；与 Blocks JSONL 的时间轴对齐策略。 | P2 |
| 批量统计置信区间 | 已输出正态近似 95% CI 和分位数；未实现 bootstrap 或非参数 CI。 | 当前用于回归和快速比较；长尾/偏态指标的正式统计结论需要后续增强。 | 多 seed 真实 episode；bootstrap 配置；报告中标注统计方法版本。 | P2 |

## 未实现

| 能力 | 当前状态 | 未实现原因 | 缺少条件 | 优先级 |
|---|---|---|---|---|
| Stone Soup 直接依赖与 metrics adapter | 未实现。没有 Stone Soup import、对象转换器或 metric generator 调用。 | 避免默认测试依赖重型外部库；上游 Track/Truth 合同未固定到 Stone Soup 类型。 | Stone Soup 版本锁定；D1/D2 adapter；标准数据集；对照阈值。 | P2 |
| TrackEval / py-motmetrics 直接接口 | 未实现。没有 MOTChallenge 导出、TrackEval runner 或 motmetrics accumulator。 | D2/D5 视觉 MOT 帧级结果仍在稳定中；当前本地指标优先支撑系统级回归。 | 帧级匹配表；IoU/距离门限；依赖安装策略；CI 可运行样例。 | P2 |
| GOSPA/HOTA/IDF1 默认输出字段 | 未实现。`EpisodeMetrics.metric_names()` 中没有这些字段。 | 这些是外部标准对照项，当前没有 frame-level evaluator 和匹配合同。 | 标准 evaluator 或自研实现；truth/track 序列；遮挡和重现规则。 | P2 |
| SCRIMMAGE metrics 桥接 | 未实现。没有 SCRIMMAGE import、日志解析器或统计桥接。 | 当前仿真主线是 AirSim Blocks 和合成数据；仓库没有 SCRIMMAGE 输出样例或消息 schema。 | SCRIMMAGE 场景输出样例；agent/resource/target ID 映射；通信事件字段；episode clock 对齐；批量目录结构。 | P3 |
| D6 对实时控制/在线决策的参与 | 未实现，且不应实现。 | D6 的模块边界就是离线评估，main/D1-D7 控制链路不能由 D6 指标回写。 | 不适用；只需继续保持接口单向消费日志。 | 禁止项 |

## 未实现原因汇总

1. 当前阶段优先保持 D6 轻量、离线、可复现，默认测试不依赖 Stone Soup、TrackEval、py-motmetrics、SCRIMMAGE、AirSim 实时服务或 GPU。
2. 标准 MOT/OSPA/HOTA/IDF1 需要帧级 truth-track/detection 匹配表、遮挡/重现规则和统一门限；现有 D6 记录已能支撑本地指标，但还不是外部 benchmark 格式。
3. 主动降级“是否必要”不是 D6 单靠事件名能判断的事实，需要 D4/main 写入复核标签或稳定后验判据。
4. 通用 AirSim recording 与 SCRIMMAGE 都需要样例、schema 和时钟/坐标对齐规则；当前 main 已提供更直接的 Blocks JSONL，优先级更高。
5. D6 不参与控制是设计边界，所有指标只用于离线报告和回归分析。

## 缺少条件

1. D1/D2/D5 输出稳定的帧级 truth-track/detection 匹配表，包含 timestamp、truth_id、global_track_id/local_track_id、匹配距离或 IoU、遮挡/重现状态。
2. main/D4 在真实 episode 中持续写入 `degradation_mode`、`selected_coordinator`、`coverage_cell`、`trigger_timestamp`、`decision_timestamp`、`review_label`、接管节点 ID 和窗口化风险事件。
3. D7 多 seed episode 稳定输出 `guidance_records.csv`、`guidance_summaries.json`、`control_commands.csv`、`intercept_summary.json`，并保留 plan/version、D4/D5 state、guidance law 和 gate reject reason。
4. Blocks/AirSim 日志保留实际 `drone_count/resource_count/target_count/camera_count` 或可推断字段，不仅保留 `2v2/5v5` 场景名。
5. 外部对照需要固定 Stone Soup、TrackEval、py-motmetrics 版本，以及 CI 可运行的小样例和指标容差。
6. SCRIMMAGE 接入需要真实输出样例、ID 映射、通信事件字段和 episode clock 对齐规则。

## 下一步优先级

1. P0：保持现有 `MetricsCollector`、JSONL、Blocks replay、D4 CSV、D7 intercept/guidance replay 和 reporting 测试稳定，作为 main 集成回归基线。
2. P1：让 main 在真实 5v5/multi-seed episode 中持续写入 D4 active/passive metadata、D5 terminal consistency、D7 guidance time-series 和实际规模字段，用 D6 生成分组报告。
3. P1：补主动降级必要性标签或后验判据，形成 `active_degradation_precision`、`unnecessary_active_degradation_count` 和窗口化 IDSW/duplicate-assignment delta 的正式输出。
4. P2：在帧级匹配表稳定后，优先做 py-motmetrics/TrackEval adapter，再做 Stone Soup metrics/OSPA/GOSPA 对照，均作为可选 benchmark，不替换当前本地指标主线。
5. P2：补通用 AirSim recording parser 和 bootstrap/non-parametric CI，仅在真实数据规模和报告需求明确后推进。
6. P3：只有当 AirSim 多机规模或通信建模不足以回答实验问题时，再接入 SCRIMMAGE metrics。
