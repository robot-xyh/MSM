# D7 AirSim 集成计划

## 2026-07-15 M5N2 集成证据收口

`p1_terminal_timing_funnel_10seed_20260715_m5n2_*` 已完成 baseline/candidate 各 10 seeds，所有 20 个 case 均有 `intercept_summary.json`、`control_commands.csv`、`d7_actual_execution_metrics.json`、control-tick timing 和 main-bus stage timing。M5N2 `20/20` 后 TERM 生效前仅额外完成 `p1_terminal_timing_funnel_10seed_20260715_png_ttc_2v2_seed001` 的 1 个 `intercept_summary.json`；该单 seed 不纳入本次 M5N2 统计，也不用于分析或晋级。其余 tuned case 和全部 dropout 均未执行，不得以缺失值或0 写入本轮结论。

本轮 5 米 NED 三维评分得到：baseline 和 candidate 的 active pair 均为 `6/30`、target 均为 `6/20`、coalition 均为 `0/10`，合计 pair/target/coalition 为 `12/60`、`12/40`、`0/20`。第二 primary 按各 case 的 active membership 动态识别，不固定资源编号；七阶段为 `assigned/visible/associated/contract=20/20`、`control/mode=17/20`、physical=`0/20`。20 个第二 primary 均为 `collision_stop`，但 collision object 缺失，不能据此归因于导引公式。candidate 逐 seed non-degradation=false、trend coast 触发=0、soft-specific duration=0，继续 default-off。online truth identity/state 使用计数在 20 case 中均为 0。

下一轮 AirSim 集成优先项：

1. 为 `collision_stop` 增加 collision object/vehicle、成员间距、停控前后速度和近距离时间线，解决 20 个第二 primary 对象名缺失的归因空白。
2. 为每个 primary 持续写盘 current measured lock、historical lock、bounded prediction、closing speed、三维机动余度和首失败原因，避免用“曾经 locked”替代“持续可控”。
3. 外层 control tick 和内层 main-bus 保持独立报告。本轮 3805 tick 外层 mean/P95/max 为 `1069.4/1254.1/2072.5 ms`，全部超过 100 ms；内层为 `349.3/487.4/1306.0 ms`，`3649/3805` 超预算；D7 stage mean/P95 为 `4.84/5.78 ms`。
4. 保持默认导引律、视觉 gate、reserve standby、plan/version 和 `global_track_id` 约束不变；未补齐证据前不用阈值放宽代替归因。

## 2026-07-15 下一轮逐帧字段合同

真实 2v2/M5N2 多 seed 必须从控制该 pair 的同一 live output 保存：assignment/resource/target/plan/coalition identity，activation 与 radar 状态，D5 visible/associated/decision，`terminal_visual_lock_measured`、history/ever-established、delivery state/reason、dropout scope/reason、loss-frame count、prediction age，raw/effective contract、control、mode、TTC reject、executed law、range/closing speed、termination 和离线 5 米结果。联盟摘要由这些行产生第二 primary 完整漏斗和首达时刻，不允许由 episode 末值回填。

针对 seed2 单帧 dropout，必须至少保存 dropout 前 measured 行、丢测行和重获行；针对 `bbox_area_jump/bbox_clipping`，必须同时保存扰动标签、expected/assigned global-track identity、TTC reject、effective control 和 executed law。2026-07-15 本地受控回归 `190 passed`，但未启动 AirSim；下一轮验收要求真实 2v2/M5N2 至少 10 seeds，且不默认保存 PNG 截图、不要求多 primary 同时到达。

## 2026-07-14 actual-execution 接入状态

真实 AirSim seed-1 canonical 接线已达到 P0 门。五层按 contract/control/terminal-switch/mode/physical 独立可用：tuned 2v2 为 `35/26/26/2/2`，M5N2 为 `67/0/0/0/2`，合计 `102/26/26/2/4`。`terminal_switch_allowed_count` 直接从已写盘 `control_commands` 独立统计，不从 control 层回填。M5N2 active pair `2/3`、第二 primary 最近约 `11.02 m`，target `2/2` 与 coalition `0/1` 必须分别上报。两个 required case 均 available，summary/CSV/canonical physical count 与 plan identity 一致，identity/state online truth 均为 0。D6 formal overall fail 只表示 P1 suite 尚未完成；terminal-switch 和 canonical 聚合均已闭合。

## 当前边界

D7 不启动、重置或控制 AirSim 生命周期。main 为每个 assignment pair 注入 D3 binding、D4 permission、D5 terminal association、目标估计相对状态和视觉观测；D7 返回中段雷达 PN 或末端视觉 PNG 的候选 NED 速度及被动诊断。`global_track_id` 始终由中心链路拥有，D7 不创建或重绑身份。

## 2026-07-14 导引律字段持久化合同

main 必须从控制该物理 pair 的同一个 live `D7RuntimePairOutput.as_log_record()` 原样持久化以下字段，不能用另一次 episode bus replay 的状态替换：

- `guidance_law_semantics_version=d7_guidance_law_semantics_v1`；
- `configured_guidance_law`、`configured_midcourse_guidance_law`、`configured_terminal_guidance_law`；
- `candidate_guidance_law`、`executed_guidance_law`；
- `raw_terminal_gate_allowed`、`latched_visual_mode_active`、`effective_control_authorized`；
- `visual_control_active`、`executed_visual_mode_switch`。

视觉 gate 失败时，允许记录 `configured/candidate=png_vm|png_ttc`，但 `executed_guidance_law` 必须为 `radar_pn`，视觉速度命令必须为空，effective control 和 executed switch 必须为 false。D6 应使用 `executed_visual_mode_switch` 统计真实入口切换，使用 `visual_control_active` 统计视觉控制驻留 sample；不得从 `requested_guidance_law`、candidate、`handover_pending`、普通 `mode_transition` 或 legacy `visual_png_switch` 反推入口切换。termination snapshot 的 executed law 必须为空。

actual-v2 之前的 postbatch M5N2 曾出现物理 control plan 与 main episode bus replay plan/state instance 不一致；当前 actual-v2 已以 plan identity 一致和独立五层统计关闭 canonical P0。后续 multi-seed/dropout/candidate 与 pair-funnel 标定必须继续保持同一 live instance 的完整逐帧持久化；main/D6 canonical 状态保持 closed。

## 2026-07-14 no-switch 诊断接线

main 的逐帧记录应从 `D7RuntimePairOutput.as_log_record()` 保留下列 canonical 字段，不应以缺失字段的默认 `false` 代替：

- `raw_terminal_gate_applicable/allowed/reject_reason`；
- `terminal_visual_lock_measured`、`terminal_measured_lock_history_available/ever_established`；
- `camera_quality_gate_passed`、`los_quality_gate_passed`；
- `closing_speed_gate_passed/threshold_mps`、`closing_speed_mps`；
- `maneuver_margin_gate_passed`、`maneuver_margin`；
- `latched_visual_mode_active`、`effective_terminal_contract_allowed`、`effective_control_authorized`；
- `terminal_range_m`、termination snapshot/status/reason。

canonical actual 五层现已由 main/D6 正式聚合。后续 P1 pair-funnel 标定仍应把同一 pair 的 live rows 适配成 `CooperativeGuidanceDiagnosticSample`，调用 `summarize_cooperative_guidance_diagnostics()`，保存 `schema=d7_pair_guidance_funnel_v2` 的 pair rows、首失败统计和 funnel available/reached。若 raw gate 为 false 且原因缺失，结果必须保持 `raw_terminal_gate_reject_reason_missing`，不能回填 camera、LOS 或 maneuver 原因。

## 下一轮验收

1. 聚焦 M5N2 第二 primary 从约 `11.02 m` 到 5 米的 acquisition、航路净空和平台响应，不修改 PN/PNG 核心公式。
2. 使用同一 Blocks 实例、reset 分隔 episode，把 seed-1 准入扩展到至少 10 seeds。
3. 拆分 2v2 约 `123.3 ms`、M5N2 约 `384.6 ms` loop latency，并校准 range、closing speed 和三维几何/机动裕度。
4. 同时报告 2v2、M5N2 baseline/candidate、dropout，保持五层独立统计，并扩展 raw gate、pair funnel、pair/target/coalition 和 5 米物理结果。
5. 不默认保存相机 PNG；轨迹图和结构化日志由 main/D6 管理。

截至 2026-07-14，D7 模块回归为 `188 passed`。seed-1 canonical 五层 P0 证据链已关闭；开放 P1 是第二 primary、multi-seed/dropout/candidate、延迟和 pair-funnel/closing-speed/三维机动标定。3D PN、True PN、APN、FRPN 在线化和同时到达不列当前 P1。
