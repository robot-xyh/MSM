# M5N2 真实 AirSim 多 Seed 结果与第二 Primary 专项报告

**日期**：2026-07-15
**范围**：M5N2 baseline 10 seed + candidate 10 seed，共 20 个 SimpleFlight case
**停止边界**：M5N2 达到 20/20 后终止批次；TERM 生效前额外完成 1 个 `png_ttc_2v2_seed001`，明确不纳入本报告，dropout 完成数为 0

## 1. 试验目的

本轮只回答三个问题：

1. M5N2 的 `2 primary + 1 reserve` 任务合同能否形成真实 5 m 物理闭环；
2. soft prediction + trend coast 是否能稳定改善第二 primary；
3. 真实 AirSim 执行中，100 ms 控制周期主要消耗在哪些阶段。

本轮没有修改 D7 的位置比例导引、视觉比例导引、视线角速率滤波或外推公式。在线控制状态来自 D2 估计的 `GlobalTrack`；AirSim actor/truth 身份和真值位置仅用于离线 D6 物理距离评分。

## 2. 场景与口径

| 项目 | 配置 |
| --- | --- |
| 资源/目标 | 5 架拦截资源、2 个 actor 目标 |
| 高威胁目标 | T001：2 个 active primary + 1 个 standby reserve |
| 普通目标 | T002：1 个 active primary |
| 物理成功 | active primary 与分配目标最近 NED 距离不大于 5 m |
| 联盟成功 | T001 的两个 required primary 均物理成功 |
| 单 case 上限 | 35 s，控制步长 0.1 s，拦截高度 NED `z=-30 m` |
| 检测 | AirSim `simGetDetections`，在线不读取 actor truth ID |
| baseline | soft prediction 关闭，trend coast 关闭 |
| candidate | soft prediction 开启，trend coast 开启 |

pair、target、coalition 使用独立分母，不把 reserve 的 standby 结果计入 active-primary 成功率，也不把缺失指标补为零。

## 3. 总体结果

| 指标 | Baseline | Candidate | 结论 |
| --- | ---: | ---: | --- |
| 已完成 case | 10/10 | 10/10 | 执行证据完整 |
| Active-primary 成功 | 6/30，20% | 6/30，20% | aggregate 无提升 |
| 目标成功 | 6/20，30% | 6/20，30% | aggregate 无提升 |
| T001 联盟完成 | 0/10 | 0/10 | 协同物理闭环未形成 |
| 第二 primary 进入 5 m | 0/10 | 0/10 | 当前主要性能断点 |
| 第二 primary 最小距离均值 | 12.74 m | 12.57 m | 仅改善 0.16 m，无工程意义 |
| 第二 primary 最小距离中位数 | 13.74 m | 13.78 m | candidate 未改善典型 case |
| 最终双 primary 视觉共识 | 1/10 | 1/10 | D5 稳定共识不足 |
| Actual-execution artifact | 10/10 available | 10/10 available | 证据链闭合 |
| 在线 truth identity/state 使用 | 0/0 | 0/0 | 安全边界通过 |

![M5N2 结果对比](../research_modules/airsim_runtime/outputs/p1_terminal_timing_funnel_10seed_20260715_m5n2/analysis_plots/m5n2_outcome_comparison.png)

按 seed 配对后，baseline 在 seed 1、2、7 获得两个物理成功，candidate 在 seed 2、3、10 获得两个物理成功。两组总数相同，但 candidate 在 seed 1 和 7 退化，只在 seed 3 和 10 改善，因此 `candidate_pair_non_degradation=false`、`candidate_target_non_degradation=false`。该 candidate 不能晋级默认路径。

## 4. 第二 Primary 分析

第二 primary 按 D5 `primary_resource_ids` 的稳定成员顺序确定，不按事后最近距离重新选择。20 个 case 中没有第二 primary 进入 5 m：

- baseline 最近距离范围为 8.87-14.74 m，均值 12.74 m；
- candidate 最近距离范围为 8.84-14.31 m，均值 12.57 m；
- baseline 最终第二 primary `locked` 为 2/10，但只有 1/10 形成双 primary 稳定视觉共识；
- candidate 最终第二 primary `locked` 为 1/10，双 primary 稳定视觉共识同样为 1/10；
- 两组各有 8/10 的最终首失败阶段停在 `visible`，原因是 `terminal_visual_evidence_expired`；
- 其余 case 分别表现为稳定锁定不足、MOT history 不足，或已重捕获但未形成 5 m 物理闭环。

D5 对 20 个 case 的第二 primary 时序记录进一步复核为 3725/3725 可用：
`locked=1721`、`ambiguous=795`、`reacquire=1209`、`hold=0`。失败漏斗主要落在
bbox 稳定性（34.44%）、检测/新鲜度（32.46%）和视觉关联（20.51%）；真正达到
bbox stable/handoff-ready 的样本只有 `161/3725`（4.32%）。本批记录能够从漏斗字段
重建这些分布，但没有在最终产物中直接保存统一 `failure_category`，该 producer 接线仍是 P1。
第二 primary 必须按 D5 primary membership 顺序识别，不能写死资源编号：candidate seed 2
为 `INT-02`，其余 19 个 case 为 `INT-03`。

D6 七阶段漏斗对第二 primary 的 20 个结果均可用：前四阶段为 `20/20`，control/mode
为 `17/20`，5 m physical 为 `0/20`。D7 进一步确认 20 个第二 primary 的最终
`control_stop_reason` 全部为 `collision_stop`，但当前 artifact 没有持久化 collision object、
碰撞法向或碰撞时的成员/环境距离。因此暂时不能判断是联盟成员冲突、环境碰撞，还是
AirSim 碰撞状态异常。该诊断证据必须先补齐，不能把 0/20 全部归因于视觉门限。

![第二 Primary 最近距离](../research_modules/airsim_runtime/outputs/p1_terminal_timing_funnel_10seed_20260715_m5n2/analysis_plots/m5n2_second_primary_min_range.png)

结果表明问题不是单一的“相机完全看不到”。部分 case 已经完成 D5 视觉锁定甚至双 primary 视觉共识，但第二 primary 仍停在 8.8-10.2 m；其余多数 case 的视觉证据在末段过期。当前断点横跨 D5 证据持续性、D7 门控后的有效控制窗口和 AirSim 控制周期延迟，不能通过单独放宽 D5 安全门限解决。

## 5. Candidate 行为

candidate 相比 baseline：

| 执行计数 | Baseline | Candidate |
| --- | ---: | ---: |
| Contract allowed | 553 | 499 |
| Control allowed | 75 | 89 |
| Mode switched | 12 | 12 |
| Terminal prediction | 14 | 19 |
| Delivery expired | 239 | 332 |
| Prediction window expired | 157 | 257 |

soft prediction + trend coast 增加了预测和控制许可样本，但模式切换数不变、物理成功数不变，过期事件明显增加。说明 candidate 当前主要延长了末端证据生命周期，没有稳定扩大有效控制窗口；继续保持 optional/candidate-only，默认关闭。

## 6. 分阶段时序

20 个 case 共得到 3805 个有效 main-bus tick 和 3805 个 control tick。成功 case 会提前终止，因此总数小于固定 4200 tick。

| 层级 | Mean | P95 | Max | 100 ms 违例 | Dominant stage |
| --- | ---: | ---: | ---: | ---: | --- |
| Main bus 内层 | 349.34 ms | 487.40 ms | 1305.99 ms | 3649/3805，95.90% | D1 fusion，均值 320.00 ms |
| Control tick 外层 | 1069.45 ms | 1254.06 ms | 2072.51 ms | 3805/3805，100% | AirSim frame sample，均值 432.29 ms |

外层 `bus_processing` 均值为 351.80 ms，与 main-bus 内层 349.34 ms 是包含关系，严禁相加。外层另外包含 AirSim frame sample 432.29 ms、guidance/control RPC 290.85 ms 和 pair sync 0.57 ms。

![M5N2 时序分解](../research_modules/airsim_runtime/outputs/p1_terminal_timing_funnel_10seed_20260715_m5n2/analysis_plots/m5n2_stage_timing.png)

100 ms 实时预算没有闭合。当前首先应优化 D1 每 tick 的批量融合路径、减少 AirSim 同步图像/RPC 阻塞，并把控制 RPC 与非关键评估处理解耦；在性能下降前不应通过放宽视觉安全门限换取成功率。

## 7. D1-D4 跨模块复核

| 模块 | 本批可确认内容 | 不能据此确认的内容 |
| --- | --- | --- |
| D1 | 3805 个 D1 fusion 样本全部可用，mean/P95/max=`320.00/451.46/1234.88 ms`；在线双时间戳、协方差和 NED 合同保持 | 本批没有可用真值一致性分母，不能关闭 NIS、NEES 或 RMSE 标定 |
| D2 | association mean/P95/max=`2.521/3.147/98.942 ms`；默认 GNN/Hungarian 和中心 `global_track_id` 所有权不变 | truthless 在线 IDSW/continuity 保持 unavailable，不能补为 0；第二 primary 失败不能归因 D2 |
| D3 | `3725/3725` 条计划历史可用；每个 case 始终为单一 `plan_id/version=1`，实际 plan/member/owner churn 为 0；T001 始终为 2 primary + 1 reserve | 3555 条成员记录是候选评估，不是实际换员；candidate 物理非退化失败不等于 D3 计划退化 |
| D4 | 本批 `active_degradation=0`，是中心继续执行负对照；D4 arbitration mean/P95/max=`5.59/6.70/94.10 ms` | 没有验证二级接管或完全分布式联盟；物理失败不会自动触发主动降级 |

这些结果把当前根因范围进一步收窄到 D1/runtime 性能、第二 primary 末端证据持续性和
`collision_stop` provenance。D2/D3/D4 的当前合同没有在本批出现可直接解释 0/20 的异常，
但仍需在各自专项场景中继续验证，不能将负对照写成性能闭合。

## 8. D6 报告可用性

D6 已生成 M5N2 专用 pair/target/coalition、actual-execution 和 per-seed 报告。两层时序原始 JSONL 均完整，但 main 的 suite 合并文件附加了 case 标签且每个 case 的 `frame_index` 从零重置，D6 当前严格单 episode timing loader 会拒绝额外字段和跨 episode frame reset。因此：

- 本报告的时序统计直接从 20 个原始、逐 case JSONL 汇总；
- main-bus 与 control-tick 分开统计，未跨层求和；
- D6 标准 M5N2 acceptance bundle 中的 suite timing 保持 unavailable，而不是伪造连续 frame index；
- “多 episode timing envelope/manifest”列为新的 P1 集成缺口，不影响每个 case 的原始时序真实性。

## 9. 当前结论

1. M5N2 20-case 执行、actual artifact、5 m 离线物理评分和在线 truth 隔离已经完成。
2. 第二 primary 与联盟物理闭环没有完成，baseline/candidate 均为 0/10。
3. candidate 在总成功数上持平，但逐 seed 非退化失败，且过期事件增加，不晋级。
4. 控制 tick 平均约 1.07 s，100 ms 预算全面违例；D1、AirSim frame sample 和控制 RPC 是主要耗时。
5. 第二 primary 全部以 `collision_stop` 结束，但碰撞对象未写盘；碰撞根因是当前最直接的诊断缺口。
6. 按用户指令，本轮在 M5N2 20/20 后停止。进程切换期间仅额外完成 1 个 `png_ttc` seed 1，未形成多 seed 证据且不进入本报告；dropout 未执行。

## 10. D1-D7 文档同步

| Owner | 已同步范围 | Owner 验证 |
| --- | --- | --- |
| D1 | README、PLAN、算法/原理、AirSim、实验、3 份 GAP/review | `98 passed` |
| D2 | README、PLAN、算法/原理、AirSim、实验、3 份 GAP/review | `113 passed` |
| D3 | README、PLAN、算法/原理、AirSim、实验、3 份 GAP/review | `157 passed, 1 skipped`（可选 OR-Tools） |
| D4 | README、PLAN、算法/原理、AirSim、实验、3 份 GAP/review | `280 passed` |
| D5 | README、PLAN、算法/原理、AirSim、实验、3 份 GAP/review | `272 passed` |
| D6 | README、PLAN、算法/原理、AirSim、实验、3 份 GAP/review | `246 passed` |
| D7 | README、PLAN、算法/原理、AirSim、实验、3 份 GAP/review | 最近一次 `190 passed`；本轮仅文档变更 |

所有 owner 均确认本轮未修改模块代码。文档统一排除额外 `png_ttc seed001`，dropout
完成数保持 0；历史证据保留，但顶部 2026-07-15 增量为当前权威口径。

## 11. 证据索引

- 执行索引：`research_modules/airsim_runtime/outputs/p1_terminal_timing_funnel_10seed_20260715_m5n2/p1_terminal_closure_summary.json`
- 逐 case 指标：`research_modules/airsim_runtime/outputs/p1_terminal_timing_funnel_10seed_20260715_m5n2/m5n2_case_metrics.csv`
- 分析汇总：`research_modules/airsim_runtime/outputs/p1_terminal_timing_funnel_10seed_20260715_m5n2/m5n2_analysis_summary.json`
- D6 bundle：`research_modules/airsim_runtime/outputs/p1_terminal_timing_funnel_10seed_20260715_m5n2/d6_acceptance_m5n2/`
- 原始 case：`research_modules/airsim_runtime/outputs/p1_terminal_timing_funnel_10seed_20260715_m5n2_{baseline,candidate_soft_prediction_trend_coast}_seed*/episode_006_full_flow/`
