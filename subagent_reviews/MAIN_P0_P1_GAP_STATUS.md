# Main P0/P1 缺口状态汇总

**审计目标**：把 D1-D7 当前 P0/P1 缺口集中到一个 main 可调度清单，避免各模块 GAP 文件之间口径分散。
**审计边界**：本文件只用于科研仿真、接口补齐和后续工程排期；不涉及真实硬件、实机处置、火控、自动处置或授权绕过。
**当前结论**：未发现新的 P0 阻塞断链。P0 重点是保持现有跨模块合同、安全门控和测试回归不退化。2026-07-08 已完成 D1-D7 P1 基线补齐和 main runtime bus 接线复核：执行指标回灌、`request_center_replan -> D3 new plan version -> D7 gate`、D5 feedback 写回 D3、二级接管 plan owner/version、D7 N-pair runtime bus、controlled intercept 中心/二级重分配到视觉 PNG 门控均已通过测试。D5 已新增可运行 YOLOv8 + ByteTrack/BoT-SORT/IoU fallback adapter，main runtime 已新增显式 `--detection-backend yolo` 接线，默认仍保持 AirSim detect fallback。D1-D7 owner 已同步更新各自 PLAN/GAP/review 文件，避免把已完成 P1 接口继续列为未完成。D4 现在把无冲突的持续 D5 `ambiguous/reacquire` 视为本地重捕获/二级 cue 问题，而不是中心分配失效。最新 5v5 机动高空侦察节点测试说明，雷达 cue + 云台指向能显著改善二级节点 bbox 尺寸，但二级网络同帧全覆盖和跨视角配准仍未闭合。剩余 P1 主要是真实 AirSim 多 seed 校准、二级侦察覆盖/跨视角配准、真实图像/协议/标定适配和 D6 长期报告口径扩展。

## 2026-07-08 文档同步复核

- D1-D7 已按各自 owned paths 同步 `PLAN.md`、`subagent_reviews/Dx_IMPLEMENTATION_GAP_AUDIT.md` 和 review/plan 文件；main 本轮只同步本总表与 `MAIN_IMPLEMENTATION_GAP_AUDIT.md`。
- 子模块自测结果：D1 25 passed；D2 26 passed；D3 45 passed；D4 75 passed；D5 68 passed；D6 32 passed；D7 39 passed。D2 有 1 个 warning，D6 有 1 个 matplotlib Axes3D warning，均不构成 P0。
- 最新 AirSim 5v5 D4/D5 stress 输出目录为 `research_modules/airsim_runtime/outputs/p1_d4d5_mobile_recon_20260708_055948*`。3 个 seed 均 connected，每个 seed 包含 `no_degradation`、`degrade_to_secondary`、`degrade_to_distributed` 三类 case，均为 13 帧且 `image_ok=13`。
- D4 动作与预期一致：`no_degradation -> continue_center`，`degrade_to_secondary -> degrade_to_secondary`，`degrade_to_distributed -> degrade_to_distributed`。
- 机动高空侦察节点状态：`secondary_gimbal_pointing_ok_rate=1.0`，`secondary_recon_mode=mobile_recon_gimbal`，`cue_source=radar_global_track_cue`，能力类为 `mobile_high_recon`。bbox mean 约 3326 px^2，优于固定俯视约 1145 px^2。
- 未闭合点：`secondary_network_joint_full_view_frame_rate=0.0`，二级网络平均覆盖约 0.65-0.69，主要断点为 `not_all_targets_visible` / `network_union_incomplete`；降级 case 的 cross-view association 仍为 0，`not_registered` 约 65。因此视觉 PNG 仍必须保持 D3/D4/D5 gate，不得因二级节点看清而绕过全局分配和配准合同。

## P0 状态

| 模块 | P0 状态 | 保持口径 | 验收 |
|---|---|---|---|
| D1 | 无新增 P0 blocker | `SensorObservation` 必须保留 `measurement_timestamp`、`arrival_timestamp`、协方差、NED 状态和 `GlobalTrack` 输出；fixed-lag/OOSM 与 source de-dup 不退化 | `PYTHONPATH=research_modules/d1_sensor_fusion/src pytest -q research_modules/d1_sensor_fusion/tests` |
| D2 | 无新增 P0 blocker | GNN/Hungarian、马氏门控、稳定 `global_track_id`、`id_switch_count`、continuity 和 duplicate assignment 指标不退化 | `PYTHONPATH=research_modules/d2_data_association pytest -q research_modules/d2_data_association/tests` |
| D3 | 无新增 P0 blocker | `AssignmentPlan` version、Hungarian/fallback DP、迟滞、stale/rejected plan、D7 binding 和规模字段不退化 | `python3 -m pytest -q research_modules/d3_assignment_planner/tests` |
| D4 | 无新增 P0 blocker | `C2Health`、主动/被动降级、二级节点 lifecycle、D5 distributed visual evidence 到 CBBA 风险加权、D6 event metadata 不退化 | `PYTHONPATH=research_modules/d4_distributed_fallback python3 -m pytest -q research_modules/d4_distributed_fallback/tests` |
| D5 | 无新增 P0 blocker | D5 不分配、不授权、不创建/改写/换绑 `global_track_id`；online 不使用 AirSim truth ID；friend conflict 和 duplicate risk 保守 hold/ambiguous | `pytest -q research_modules/d5_terminal_association/tests` |
| D6 | 无新增 P0 blocker | D6 只消费日志，不参与控制；显式保留 `id_switch_count` 和实际 `drone/resource/target/camera` 规模字段 | `pytest -q research_modules/d6_evaluation_metrics/tests` |
| D7 | 无新增 P0 blocker | D7 不分配、不授权、不改写 `global_track_id`；D3/D4/D5 gate 失败时阻断视觉 PNG | `python3 -m pytest -q research_modules/d7_proportional_guidance/tests` |
| main/runtime | 无新增 P0 blocker | AirSim runtime 不保存 PNG 默认截图；online D5 association 不使用 truth ID；D1-D7 record/summary 总线保持可回放 | `pytest -q research_modules/airsim_runtime/tests/test_blocks_runtime.py` |

## P1 缺口清单

| Owner | P1 缺口 | 当前状态 | 缺少条件 | 验收口径 |
|---|---|---|---|---|
| main | 统一 AirSim episode bus 多 seed 校准 | `MainAirSimEpisodeBus` 已接入 D1-D7 summary/record；2026-07-08 已将真实 D7 控制执行指标合并到正式 `main_episode_bus_metrics.json`，保留 raw contract metrics，并补齐 D5 feedback、二级接管、D7 runtime bus 字段 | 稳定 episode 目录、seed/scenario 命名、真实 Blocks 多 seed 阈值和状态迁移校准 | 多 seed 报告能按 seed/scenario 汇总 D3/D4/D5/D7/D6 指标，并区分 contract 与 execution 指标 |
| D1/main | D1 replay schema version、CSV reader、更多 Blocks fixture | **P1 基线已补齐**：replay schema v1、legacy JSONL 兼容、最小 CSV reader/replay 已实现 | 更多真实 Blocks/CV fixture、D6 长期批量字段、长期回归样本 | D1 能读取带 version 的 replay fixture，D6 可追踪 observation latency/OOSM |
| D1/D4/D6 | 区域质量摘要和 OOSM 审计字段 | **P1 基线已补齐**：`LatencyAuditSummary` 和轻量 `FusionQualityRegionSummary` 已实现 | 区域时间窗口、协方差增长率窗口、D6 长期趋势字段 | D4 可消费区域级不确定度；D6 可输出 OOSM/latency 统计 |
| D2/main/D6 | 真实 5v5 AirSim replay 的 association log 和 risk threshold 校准 | **P1 基线已补齐**：D2 replay helper、AirSim-like replay、threshold sensitivity 和 risk split 已实现 | 真实 replay、truth offline labels、阈值版本、D6 grouped report | 输出 IDSW、continuity、risk summary 和 threshold sensitivity |
| D3/main/D4 | `request_center_replan` 后新 plan owner/version 闭环 | **P1 基线已补齐**：main 监听 D4 `request_center_replan`，下一规划周期强制 D3 生成新 version，并写入 `replan_reason/supersedes_plan_id/supersedes_plan_version/active_plan_owner=center`；D7 gate 继续按当前 binding/version 放行或拒绝 | 仍需二级 owner/version 规则和多 seed 校准 | D4 request/replan 后 D3 发布新 version，D7 只接受当前 version；名义场景不能因软 cost margin 每帧 replan |
| D4/main/D3/D5 | 主动降级过敏抑制 | **P1 基线已补齐**：D4 已将 `d3_assignment_not_current/stale` 作为硬风险，将 `d3_assignment_cost_margin_low` 作为软风险；软 margin + 早期 D5 low confidence 只 `continue_center/observe_more`；持续 D5 `ambiguous/reacquire` 若无 observed mismatch/资源错配/重复锁定/友方冲突，则不触发分布式降级 | 真实 Blocks 多 seed 下的 threshold、dwell/release 和 review label 校准 | 名义 2v2/5v5 不应全帧 `request_center_replan` 或 `degrade_to_distributed`；硬 stale/not-current 和真实 terminal mismatch 仍触发仲裁 |
| D3/D5/main | D5 feedback 写回下一轮 D3 代价 | **P1 基线已补齐**：D3 feedback helper 已接入 main runtime bus，输出 `d3_terminal_feedback_writeback`，无冲突 ambiguous/reacquire 不再误触发 operator hold | 真实多 seed 下 duplicate/friend/fov/feasibility metadata 阈值校准 | D5 feedback 能生成 `operator_hold/prohibited_edges/fov_difficulty` 输入 |
| D4/main/D3/D7 | 二级接管 plan version 与 D7 two-stage handoff | **P1 基线已补齐**：D4 secondary takeover metadata、D3 secondary plan owner/version、D7 owner gate 和 controlled 2v2 visual PNG 回归已通过 | 真实 Blocks 多 seed 的 secondary heartbeat/link freshness 校准 | `degrade_to_secondary` 阶段 1 阻断 visual PNG，阶段 2 新 plan 生效后才放行 |
| D4/D5/main/D6 | 机动高空侦察二级节点覆盖与接管必要性 | **P1 接线已补齐，校准未闭合**：2026-07-08 5v5 stress 中 radar cue + gimbal 指向正常，bbox 尺寸改善，但二级网络同帧全覆盖仍为 0.0，联合覆盖约 0.65-0.69 | 二级节点站位/扫描策略、target grouping、coverage cell、heartbeat/link freshness、review label、plan activation delay 和 D6 长期趋势 | D6 报告能同时输出单相机全局视野率、二级网络联合覆盖率、coverage funnel breakpoint、接管必要性和误降级率 |
| D4/D3/D6 | CBBA vs 中心 Hungarian cost gap | **P1 基线已补齐**：D4 已有 `CBBACostGapBenchmark` helper | 同 episode 保存 D3 center cost matrix/current plan；D6 cost gap 长期聚合 | 同场景输出 completion/conflict/cost gap/rounds/messages |
| D4 | 独立 auction baseline 是否后置 | 未单独实现；当前 CBBA 覆盖 winner/bid 思想 | bid/award/rollback 协议和测试预算 | 若进入 P1/P2，需与 CBBA 同输入对照；默认本轮不实现 |
| D5/main/D6 | AirSim geometry、TerminalConsistencySummary 全量写盘 | **P1 基线已补齐**：D5 geometry log fields、handoff advisory、consistency 连续窗口和 main event/snapshot 字段已接入 | 真实多 seed 下 projected pixel、Mahalanobis、duplicate risk 的长期统计 | D6 能按 episode/seed 统计 terminal lock、ambiguous、hold、duplicate risk 和重捕获连续性 |
| D5/D4/main | 多相机/二级视角 detect 到 global track 的跨视角配准 | **P1 metadata-only 基线已补齐，真实转换未闭合**：D5 有 `TerminalObservationBus`、`CrossViewAssociation`、`TerminalCrossViewFusion` 和覆盖漏斗诊断；最新 stress 中二级 detect 可见但未转成有效 cross-view 支持 | 多相机外参/时间同步、二级 cue 重投影、D2/D3 binding、稳定 bbox/MOT、全局航迹投影门限和离线 truth label 校准 | 降级 case 不再停留在 visible-only，`secondary_detect_available_but_not_registered` 显著下降，cross-view association 可被 D4/D6 消费 |
| D5/D7 | 视觉 PNG 前置证据合同固化 | **P1 基线已补齐**：D5 handoff advisory、D7 D3/D4/D5 gate、center/secondary controlled intercept owner/version 回归均通过 | 真实 bbox 稳定窗口、measurement age、duplicate risk、friend conflict 多 seed 校准 | D7 仅在 D5 locked、assigned ID 一致、D3/D4 gate 通过时视觉 PNG |
| D5/main | YOLOv8 + MOT detector adapter | **P1 基线已补齐**：D5 可加载 `best.pt` 运行 YOLOv8，优先 ByteTrack/BoT-SORT，缺依赖时 deterministic IoU fallback；main runtime 可用 `--detection-backend yolo` 将内存图像送入 D5 adapter | 真实 AirSim 多 seed 目标尺寸、置信度、tracker backend 和 FOV 阈值标定 | adapter 只输出 `LocalVisualTrack`，tracker ID 不替代 `global_track_id` |
| D6/main | D4/D5/D7 产物统一回灌 | **P1 基线已补齐**：执行拦截时，main 将 `control_commands.csv` 和 `intercept_summary.json` 中的成功数、碰撞拦截数、guidance law、terminal reject 等回灌到正式 main bus metrics；raw contract metrics 单独保留 | episode clock、records merge order、review label 和多 seed 报告 | `EpisodeMetrics` 能从一个 episode 目录汇总 Blocks/D4/D5/D7 指标，且执行前 contract 指标与执行后 intercept 指标不混淆 |
| D6 | 主动降级必要性/精度 | **P1 基线已补齐**：`metric_scope`、`active_degradation_precision`、`unnecessary_active_degradation_count` 和 review label/后验最小口径已实现 | 真实 episode 持续写出 review/window 字段 | 输出 active_degradation_precision 和 unnecessary_active_degradation_count |
| D7/main/D6 | N-pair runtime bus 与多 seed PN/Pure Pursuit/PNG 对照 | **P1 基线已补齐**：D7 `runtime_bus.py`、`comparison.py`、`replay.py` 已实现，main 已注入每 pair D3/D4/D5 状态并写 D7 runtime summary | 真实多 seed grouped guidance report | 多 seed 报告输出 min range、mode switch、terminal reject、visual PNG switch |
| D7/D5/main | YOLO/MOT 到 D7 bbox/LOS gate | **P1 接线已补齐**：D5 运行 adapter 输出 `LocalVisualTrack`，main runtime 将 YOLO/MOT track 转为现有 detection contract，D7 bbox/LOS replay 可消费 YOLO/ByteTrack 或 AirSim bbox schema | 真实图像/检测框回放、失败回退策略、多 seed 样本 | replay 可生成 D7 gate 摘要；默认控制仍需 D3/D4/D5 gate 全部通过 |

## 本轮 Subagent 补充规则

1. D1-D7 只修改各自 owned paths。
2. 本轮默认补文档/GAP 状态，不引入外部开源算法或强依赖。
3. 若发现真正 P0 blocker，只在本模块 GAP 中标为 blocker 并汇报 main，不跨模块实现。
4. P2/P3 项保留在 GAP，不进入本轮执行。
5. 所有模块继续遵守：不写死 2v2/5v5，不改写 `global_track_id`，D6 不控制系统，main 统一 AirSim runtime。

## Main 验收

```bash
git diff --check
git status --short
pytest -q research_modules/airsim_runtime/tests/test_blocks_runtime.py
python3 -m pytest -q research_modules/airsim_runtime/tests/test_blocks_runtime.py::test_controlled_5v5_active_center_replan_visual_png research_modules/airsim_runtime/tests/test_blocks_runtime.py::test_controlled_2v2_active_degradation_secondary_plan_visual_png
```
