# D7 比例导引与末端视觉 PNG 模块

## 2026-07-15 真实 AirSim M5N2 20-case 复核

main 已完成并停止 `p1_terminal_timing_funnel_10seed_20260715_m5n2_*` 的 20 个 SimpleFlight case：baseline 与 `soft_prediction + trend_coast` candidate 各 10 seeds，每个 case 有 3 个 active primary，物理成功按 NED 三维距离不大于 5 米的离线真值评分。两组 active-primary 均为 `6/30`，target 均为 `6/20`，coalition 均为 `0/10`；合计 pair/target/coalition 为 `12/60`、`12/40`、`0/20`。高威胁目标的第二 primary 按各 case 的 active membership 动态识别，不写死资源编号，两组均为 `0/10`、合计 `0/20`。baseline 第二 primary 最近距离均值为 `12.736 m`，candidate 为 `12.573 m`，但 paired seeds 中物理 pair 结果为 6 组持平、2 组改善、2 组退化，不构成稳定收益。

canonical 实际执行样本中，baseline 的 contract/control/terminal-switch 许可分别为 `553/5238`、`75/5238`、`75`，mode transition 为 `12`；candidate 分别为 `499/5151`、`89/5151`、`89`、`12`。第二 primary 七阶段证据全部可用：`assigned/visible/associated/contract=20/20`、`control/mode=17/20`、physical=`0/20`。20 个第二 primary 最终均为 `collision_stop`，但 collision object 未持久化，因此不能将失败归因于 PN、PNG、LOS 或外推公式。candidate 的逐 seed non-degradation 为 false，`terminal_trend_coast_applied=0`、soft-specific duration=0；通用 image-KF predicted 记录从 14 增至 19 不能解释为 candidate 已触发或已非退化，因此继续 default-off。

20 case 共有 3805 个 control tick，外层总时延 mean/P95/max 为 `1069.4/1254.1/2072.5 ms`，`3805/3805` 超过 100 ms 预算；内层 main-bus 为 `349.3/487.4/1306.0 ms`，`3649/3805` 超预算。两层是包含关系，禁止相加。内层 D7 guidance-contract 阶段 mean/P95 仅 `4.84/5.78 ms`，当前主要时延不在 D7 导引计算本身。全部 case 的 online truth identity/state 计数均为 0。M5N2 `20/20` 后 TERM 生效前仅额外完成 `p1_terminal_timing_funnel_10seed_20260715_png_ttc_2v2_seed001`，该单 seed 不纳入本次 M5N2 统计，也不用于分析或晋级；其余 tuned case 和全部 dropout 均未执行。本轮未修改位置 PN、VM/TTC 视觉 PNG、LOS 滤波或外推核心公式。

## 2026-07-15 下一轮真实 AirSim 被动诊断准备完成

本批只补充诊断、校准 helper 和受控回归，不修改 `png_guidance_delivery`、位置 PN、VM/TTC 视觉 PNG、LOS 滤波、外推核心公式，也不放宽 D3/D4/D5、身份、版本、友方、reserve 或联盟门控。`d7_pair_guidance_funnel_v2` 现在为每个 pair 同时输出规范链路 `assigned -> active -> radar -> D5 visible -> associated -> locked -> contract -> control -> mode -> physical`、细粒度质量门、各阶段首达时刻，以及联盟中第二 primary 的完整漏斗与首失败原因。

measured-lock 诊断已把“D5 声明 locked”“本帧真实图像量测”“历史上曾建立锁定”和“有界预测”分开。seed 2 的确定性单帧丢测回归为：`0.0s` 首次 measured lock，`0.3s` 单帧 `image_kf_predict`，`0.4s` reacquired，连续丢测长度为 1；这只证明时序字段可解释，不是新的真实 AirSim seed 结果。`png_ttc` 的 `bbox_area_jump` 与 `bbox_clipping` 受控用例均验证：拒绝原因正确、effective control 为 false、执行律回退 `radar_pn`、`global_track_id` 保持不变。2026-07-15 D7 全量为 `190 passed`，验收阈值零失败；本批未启动 AirSim。仍待 main 收集真实 2v2/M5N2 多 seed 的逐帧字段、第二 primary 5 米结果和真实 dropout/TTC 扰动样本。

## 2026-07-14 actual-execution 真实 AirSim 证据同步

本轮只同步 main/D6 已写盘的真实 AirSim seed-1 证据，不修改位置 PN、`png_vm/png_ttc`、LOS、外推、D3/D4/D5 gate 或 `global_track_id` 规则。canonical actual 五层已经独立可用，顺序统一为 contract/control/terminal-switch/mode/physical：tuned 2v2 为 `35/26/26/2/2`，M5N2 为 `67/0/0/0/2`，合计 `102/26/26/2/4`。`terminal_switch_allowed_count` 直接从已写盘 `control_commands` 独立统计，不由 `control_allowed_count` 推断或回填。

D6 对两个 required case 的 actual-execution availability 为 `2/2`，五层状态均为 `available`，summary/CSV/canonical physical count、plan identity 和 identity/state online truth `0/0` 均闭合，因此 canonical 证据链 P0 关闭。M5N2 active pair 物理成功为 `2/3`，第二 primary 最近约 `11.02 m`；target `2/2` 与 coalition `0/1` 仍按独立分母报告。D6 formal overall 仍为 fail，只因为完整 P1 suite 尚未通过；terminal-switch 层和 main/D6 canonical 聚合均已闭合。当前开放 P1 仅包括 M5N2 第二 primary、同配置 multi-seed/dropout/candidate、约 `123.3/384.6 ms` loop latency、pair funnel/closing speed/三维几何与平台机动标定；3D PN、True PN、APN、FRPN 在线化和同时到达不列当前 P1。

## 2026-07-14 导引律执行语义合同 P1 关闭

D7 runtime 现在以 `d7_guidance_law_semantics_v1` 明确区分三层导引律：`configured_guidance_law` 是 main 配置的完整策略，`candidate_guidance_law` 是本帧已经计算但可能被视觉门拒绝的视觉候选律，`executed_guidance_law` 才是本帧可执行命令使用的导引律。配套字段另给出配置的中段/末段律、`visual_control_active` 和仅在有效控制后进入视觉模式时为真的 `executed_visual_mode_switch`。旧 `requested_guidance_law`、`png_guidance_law_candidate` 和 `guidance_law` 保留为兼容字段；termination snapshot 的 `executed_guidance_law` 固定为 `null`。

`guidance_law_semantic_violations()` 检查 candidate 与配置不一致、无有效合同/锁存却执行视觉律、无有效控制却进入视觉模式、视觉控制缺少候选律或速度命令等不变量；runtime summary 输出 configured/candidate/executed 三套计数、实际视觉切换计数及违规原因。回归明确证明：raw/effective contract 可为 true，但 bbox/camera gate 失败时 `candidate_guidance_law=png_vm`、`executed_guidance_law=radar_pn`、latch/effective control/switch 均为 false。2026-07-14 D7 全量结果为 `188 passed`，验收阈值零失败；未修改位置 PN、VM/TTC PNG、LOS、外推公式或任何身份/版本/安全门。

actual-v2 之前的 postbatch M5N2 证据曾显示 main 物理 `control_commands.csv` 与 main episode bus replay 使用不同的 plan/state instance，且外部持久化把配置/候选 `png_vm` 写入看似“实际执行律”的列。当前 canonical actual 已以一致的 plan identity 和独立五层统计关闭该状态问题；其中 terminal-switch 层直接统计 `control_commands`，不能从候选律、普通 mode transition 或 control 层反推。后续 multi-seed 与 pair-funnel 标定仍须保持同一 live state instance 和 `executed_visual_mode_switch` 语义；main/D6 canonical 聚合状态保持 closed。

## 2026-07-14 M5N2 no-switch 首失败诊断 P1 关闭

本轮只修复状态语义和被动诊断，不修改位置 PN、`png_vm/png_ttc`、LOS 滤波或外推公式。`D7RuntimePairOutput` 新增 `closing_speed_gate_passed` 和实际使用的 `closing_speed_gate_threshold_mps`，把既有 `min_closing_speed_mps` 判定显式化；阈值、判定顺序和控制结果均未改变。`d7_pair_guidance_funnel_v2` 将每个 assignment pair 的漏斗细化为：assigned、active、radar、配置交接距离、D5 visible/associated/declared locked、raw terminal gate、D7 measured lock、camera/LOS/closing-speed/maneuver、effective contract、latched visual mode、effective control、terminal mode 和 5 米物理结果。摘要新增全体 pair 的首失败 stage/reason、各级 available/reached 计数和缺失拒绝原因计数。

对既有 `p1_terminal_closure_semantics_v2_seed1_20260714*` 做只读审计：M5N2 baseline/candidate 的三个 active pair 均未出现 raw gate、latch、effective contract/control；INT-01/INT-04 在约 `35.2-38.9 m` 停止，未进入候选 `30 m` 交接区，INT-02 进入约 `26.0-26.6 m` 后仍以 `d5_not_locked`/`terminal_detection_acquisition_timeout` 结束。2v2 `png_ttc` 和 1-frame dropout 均保持 `2/2`。现有 main `control_commands.csv` 没有导出 `raw_terminal_gate_reject_reason`、measured-lock history 和本轮新增 closing-speed gate 字段，因此 `raw=false` 且空 reason 必须标记为 `raw_terminal_gate_reject_reason_missing`，不能猜成 camera 或 maneuver 失败；完整字段接入属于 main/runtime P1。2026-07-14 D7 当前全量回归为 `188 passed`，验收阈值为零失败；没有运行新的 AirSim episode，也未放宽 D3/D4/D5、身份、版本或 `global_track_id` 规则。

## 2026-07-14 末端状态/指标语义 P1 关闭

`D7RuntimeBus` 现输出 `terminal_semantics_version=d7_terminal_semantics_v2`，并把六个概念分开记录：`raw_terminal_gate_*` 是本帧 D3/D4/D5 fresh gate；`latched_visual_mode_active` 是迟滞状态；`effective_terminal_contract_*` 合并 raw gate 与合规 bounded coast；`effective_control_authorized` 是本帧最终可执行视觉控制；`mode_transition*` 只表示 live mode 变化；`termination_snapshot*` 是 episode 结束时的非控制快照。旧 `terminal_contract_allowed` 映射 effective contract，旧 `terminal_switch_allowed`、`terminal_control_allowed`、`visual_png_enabled` 和 `visual_png_switch` 映射 effective control，row 与 summary 都输出 alias 映射。termination/abort snapshot 的 live contract/control 均为 false，并单独保留终止前 mode/latch/contract/control，不参与 live gate、控制或 mode-transition 聚合。

dropout 输出新增 `terminal_dropout_reason_scope/reason`、measured-lock history、contract reset reason 和 prediction-window expiry，能区分 `contract_reset`、`prediction_window`、`measured_lock_not_established`。bounded coast 仍要求 prior measured state 与 active latch，且 resource/global/local identity、current plan/owner/version、D4 和 friend/duplicate/safety gate 全部一致；只有 raw reject 为 D5 `reacquire` 对应的 `d5_not_locked` 才尝试 coast。2026-07-14 本地全量验收现为 `188 passed`，门槛为零失败；canonical actual 五层已由 main/D6 正式聚合。真实固定时刻 dropout、candidate 配对和更完整的 pair-funnel 标定仍是 P1 证据扩展。位置 PN、VM/TTC PNG 和 `png_guidance_delivery` 核心公式未修改。

## 2026-07-14 truth-state P0 关闭与证据边界

main/runtime 已在代码和 mock 回归层关闭该外部 P0。默认、主动中心重规划和主动二级接管的 SimpleFlight 路径统一消费 D2 `target_estimate` 中的位置、速度、协方差、`measurement_timestamp` 和 `arrival_timestamp`；主动合同覆盖只改变 D3 plan/version、D4 permission 和 D5 lock，不再提供目标运动状态或 actor/object/mesh alias。估计缺失或陈旧时 fail closed。AirSim actor truth 只保留给合成传感器、离线航迹到真值配对、轨迹绘图和运行后 NED 三维 5 米 scorer。`truth_identity_online_use_count` 与 `truth_state_online_use_count` 必须分别为 0；AirSim runtime 当前 mock 回归为 `130 passed`。D7 PN/PNG 核心公式没有修改。

该代码级关闭不会追溯升级迁移前的 2v2/M5N2 物理结果；旧结果中的 `online truth=0` 仍只审计了真值身份。2026-07-14 actual-v2 已以真实 seed-1 2v2/M5N2 同时证明 `truth_identity_online_use_count=0` 和 `truth_state_online_use_count=0`，并关闭 canonical 证据链 P0；由于每场景只有 1 个 seed，它不关闭多 seed、第二 primary 和性能标定 P1。

## 综合状态（截至 2026-07-14）

- M5N2 逐 pair 诊断已补齐 `case/seed` 隔离和 `assigned -> active -> radar -> D5 visible -> associated -> locked -> contract -> control -> mode -> physical` 漏斗，输出第二 primary 首失败、5m 最近距离、成员间距、standby reserve 越权及 owner/version mismatch。`rows` 为 D6 可直接消费别名；联盟完成只要求同 episode 内各 active primary 分别进入 5m，不要求同时到达。
- P0 无未闭合 blocker：D7 核心公式无 P0，main/runtime 的 truth-state 输入组装及 actual-v2 canonical 五层真实执行证据链均已关闭。当前 D7 回归基线为 `188 passed`；P1 合同层、delivery、末端语义、导引律执行语义和 pair 首失败诊断接口已闭合，开放 P1 是第二 primary、multi-seed/dropout/candidate、延迟及 pair funnel/closing-speed/三维机动标定。3D PN、True PN、APN、FRPN 在线化和同时到达明确后置。
- D4 `request_secondary_assist` 已明确为观测 cue，不是 assignment owner 转移：`target_node_id` 可与当前中心 owner 不同，也不要求 `takeover_ready`。D7 保留当前 D3 binding/version，D5 与安全门控通过后仍可进入视觉 PNG；等待视觉稳定期间继续 radar PN。真正二级接管只认 D3 binding 的显式 `active_plan_owner=secondary`/`secondary_takeover_state`，其 owner 必须与 D4 一致且 readiness 必须明确为 `takeover_ready`。
- 新增真实 AirSim contract replay 审计。四组 posefix smoke 中，`coalition_window_closed`、`coalition_not_activated`、`d4_owner_missing` 分别始终禁止视觉 PNG 并回退 radar PN；w08 的 15 帧 `d4_owner_missing` 来自 `airsim_control_plan v1` 缺 owner，不在 D7 内推断补齐。
- 同资源、同 `global_track_id`、同 owner/联盟角色且 plan/track/coalition version 单调前进的滚动更新现在保留视觉滤波与切换迟滞历史，但最新 D3/D4/D5 合同仍逐帧重验。owner 缺失、版本回退、activation 改变和 standby reserve 均不保留为可执行视觉状态。
- 新增被动 `cooperative_diagnostics.py`：按任意数量 assignment pair 汇总 radar midcourse、重捕、terminal contract/control/mode、5m 物理完成、range/closing speed、到达窗误差、最近距离、成员间距和首个失败阶段；同时输出动态 primary ordinal、第二 primary 失败阶段和 coalition arrival spread。
- D3 的 handoff range、arrival-window width、sector separation 以版本化 candidate metadata 进入诊断/预筛。本阶段固定排序只使用安全违规、联盟完成率和 active-primary 物理成功率，不以同时到达离散作为验收或排序条件；结果仍为 `advisory_only`。
- 新增显式 `per_primary` terminal authorization scope：仅当 binding 同时给出 `terminal_authorization_scope="per_primary"` 和 `arrival_coordination_required=false` 时，active primary 可凭自己的 D5 lock 和视觉质量独立切换 PNG，不再等待其他 primary 同帧 lock 或共同 arrival window。旧合同默认仍为 `coalition`；standby reserve、D4 pending/reconfiguring、ACK/lease/epoch、身份/版本、friend/duplicate 与 bbox/LOS/机动门控全部保持 fail-closed。
- 图像 KF 生命周期重置和 `png_ttc` 面积治理已实现；soft innovation prediction 与水平 LOS trend coast 默认关闭，6D LOS KF 仅用于 replay。
- 真实 2v2 candidate 为 `20/20`，只证明相对旧基线 `19/20` 非退化；锁定后两帧 detection dropout 均进入有界 prediction。自然运行未触发 soft/trend，不能据此宣称增强收益。
- 默认 10Hz 的本地 1-5 帧 dropout 矩阵已闭合：前两帧只允许同 identity/plan 的 image KF，第三帧起因量测年龄超过 `0.25s` 而 expired/fail-closed；较高频率 blind push 也不得越过该硬上限。
- M5N2 当前 8s 短窗与既有 z=-30m、35s 高净空基线不可比较。下一真实验收是同几何 paired M5N2、AirSim dropout 注入、真实 `png_ttc` 多 seed 和 trend coast 受控晋级。
- M=5、N=2 的 ComputerVision 10-seed 验证达到约定的 8/10 双 primary 合同验收；这证明版本化计划、联盟、视觉共识和 D7 许可链可闭合，不等于控制许可或物理命中。
- D4 commit-aware gate 已实现并接入 main/runtime；正确 topology 已接线为 T001 两个 active primary、一个 standby reserve，T002 一个 active primary，第五个资源未分配。
- 历史同 topology 的 SimpleFlight 15s 诊断中，30 个 active pair 为 0 命中，其中 24 个 `terminal_detection_timeout`；该记录保留为早期断点证据，不替代当前同几何 paired 验收口径。
- 3D PN、True PN、APN、FRPN 只存在于隔离式 P2 benchmark；FRPN 是研究近似，不是规范实现，也不进入默认 runtime。
- 位置 PN 与 `png_guidance_delivery` 的 VM/TTC 核心公式保持不变，D7 不分配、不授权、不改写 `global_track_id`。

### Fallback 联盟提交门控

D7 已扩展 `D4GuidancePermission` 和 terminal coalition gate，可 duck-typed 消费 mapping、对象属性、metadata 或嵌套 commit 对象中的 `commit_state`、epoch、lease、required/acked members、plan 和 coalition versions。该 gate 只在中心失效或 fallback 的显式多资源联盟启用：

- 仅 `committed`/`executing` 可继续，`reconfiguring`、`aborted`、pending 或缺失状态均 fail closed。
- lease 必须存在且在当前时间有效；commit epoch、plan/version、coalition/version 必须与当前 binding 一致。
- 当前 resource 必须同时位于 required 和 acked 集合，且全部 required member 已 ACK。
- commit gate 通过后仍必须满足 D5 coalition visual complete、当前 primary 激活状态和原有 bbox/LOS/机动 gate；standby reserve 永不因 commit/ACK 自动激活。

runtime row 和 summary 已输出 commit state、epoch、lease、required/acked member、成员归属/ACK 状态、明确 reject reason 及聚合计数。D4/main commit-aware DTO 已接线，二级接管、完全分布式和缺 ACK 的故障注入分别验证可执行 commit 与 fail-closed；这些证据关闭合同接线，不关闭物理拦截。

### P2 隔离式三维导引 benchmark

`optional_p2_benchmark.py` 提供明确隔离的 offline API：

- `run_optional_p2_point_mass_benchmark()`：固定 seed 生成三维机动目标质点轨迹。
- `run_optional_p2_replay_benchmark()`：消费带时间戳、目标位置/速度/加速度的离线 replay。
- `run_optional_p2_benchmark_suite()` 与 `summarize_optional_p2_benchmark()`：对 3D PN、True PN、APN、FRPN 研究近似执行同场景比较。

每条结果输出 `hit`、`min_miss_distance_m`、`control_effort_mps`、`control_energy_m2ps3`、`peak_acceleration_mps2` 和 `compute_time_s`。其中 `frpn_research_approximation` 只是基于 LOS-rate 与目标加速度的确定性鲁棒增益调度近似，不是标准模糊规则 FRPN，也没有论文逐式复现结论。

命令行运行：

```bash
python3 research_modules/d7_proportional_guidance/scripts/run_optional_p2_benchmark.py \
  --seeds 7,17,27 \
  --output-dir /tmp/msm-d7-p2
```

输出 CSV、JSON 和中文 Markdown 报告。该路径始终标记 `benchmark_only=true`、`default_runtime_path_replaced=false`、`png_guidance_delivery_modified=false`，且 P2 law 未注册到在线 `RuntimeGuidanceLaw` selector。

### 通用 N/M cooperative binding topology

`build_cooperative_guidance_topology()` 将 D3 已按代价排序的 resource IDs、target IDs 和每目标需求数展开为 D7 bindings。它不做 Hungarian/CBBA、不创建 AirSim pair，也不写死 5v2：

```python
from d7_proportional_guidance import build_cooperative_guidance_topology

topology = build_cooperative_guidance_topology(
    resource_ids=("R1", "R2", "R3", "R4", "R5"),
    target_ids=("T001", "T002"),
    required_counts={"T001": 3, "T002": 1},
    coordination_mode={"T001": "hybrid", "T002": "independent"},
    primary_count=2,
    plan_id="plan-42",
    plan_version=3,
    terminal_authorization_scope={"T001": "per_primary", "T002": "coalition"},
    arrival_coordination_required={"T001": False, "T002": True},
)
```

该输入生成 T001 的两个 `primary/wave-0/active`、一个 `reserve/wave-1/standby`，以及 T002 的单 primary；第五个资源进入 `unassigned_resource_ids`。两个新参数均支持统一标量或按目标 mapping，并写入 target topology 与每个 binding。T001 的 active primary 因显式 `per_primary + false` 不要求 arrival window；其 reserve 仍 standby。默认不传新参数时保持旧 `coalition + true` 语义，coordinated target 缺 arrival window 继续 fail-closed。

本模块实现“经典比例导引架构”的二维研究核、D3/D4/D5 terminal contract、末端视觉 PNG gate 和 D7-owned runtime bus 日志适配。模块只处理抽象的 `GuidanceState`、`GuidanceCommand`、`GuidanceRecord`、`VisionGuidanceObservation` 和版本化分配/末端锁定状态；main/runtime 可以消费 D7 输出的 SimpleFlight 兼容速度命令和 gate 字段，但 D7 本身不直接连接 AirSim、SimpleFlight、PX4、硬件接口、火控参数、毁伤模型、自动处置或授权绕过流程。

## 目录

```text
research_modules/d7_proportional_guidance/
  PLAN.md
  README.md
  d7_proportional_guidance/
    __init__.py
    airsim_dry_run.py
    airsim_contract_replay.py
    calibration.py
    comparison.py
    models.py
    pn.py
    replay.py
    runtime_bus.py
    selector.py
    simulator.py
    terminal_gate.py
    vision_png.py
  png_guidance_delivery/
    README.md
    docs/
    examples/
    vision_guidance/
  tests/
    conftest.py
    test_airsim_phase1_dry_run.py
    test_coalition_guidance_gate.py
    test_proportional_guidance.py
```

## 核心能力

- `radar_midcourse`：使用抽象 GlobalTrack/雷达航迹估计，计算中段二维 PN 指令。
- `vision_terminal`：使用抽象像素/LOS 观测估计，计算末段二维 PN 指令。
- `pure_pursuit`：轻量纯追踪 baseline，通过 `GuidanceConfig.guidance_law="pure_pursuit"` 启用，用于和默认 PN 做离线对照；没有引入 PythonRobotics 依赖。
- `SimpleFlightPngGuidanceFilter`：从 `png_guidance_delivery` 抽取的轻量视觉 PNG gate，支持 bbox 质量、LOS-rate 低通/限幅/尖峰拒绝、TTC/VM 增益和机动裕度判断。
- `TerminalGuidanceDelivery`：每 assignment pair 一个实例的末端短时外推 API，状态为 `acquiring/measured/image_kf_predict/blind_push/reacquired/expired`。默认 `control_dt=0.1s`、图像角度/角速度 KF predict `0.25s`、连续丢失 `3` 帧、命令平均 `0.10s`、blind push `0.25s`、衰减 `tau=0.18s`；所有外推命令受最后量测后 `0.25s` 统一硬上限约束。resource/global/local track、plan owner、activation 或版本回退会清空历史；同控制身份的单调滚动版本更新只刷新当前合同版本，不清空图像历史。输出 `measured/predicted/innovation_rejected/reset/expired` 滤波审计状态，以及 contract reset、prediction window、measured lock 未建立三类 dropout scope。soft innovation prediction 和水平 LOS trend coast 默认关闭，后者启用时上限为 `0.75m/s`。
- `guidance_mode_from_terminal_contract(...)`：把 D3/D4/D5 末端合同结果映射为显式 D7 日志状态，包括 `handover_pending`、`hold`、`reacquire` 和 `abort_revoke`。
- `terminal_switch_allowed_rate` / `summarize_terminal_switch_quality`：对 D7 已输出的 gate 结果做离线通过率统计，不重新执行 runtime gate 逻辑。
- `D7RuntimeBus`：D7-owned N-pair state injection adapter。调用方为每个 assignment pair 注入当前 D3 binding、D4 permission、D5 terminal association 和可选 bbox observation；D7 为每个 `resource_id -> assigned_global_track_id` 维护独立 terminal delivery 和 latch，输出 canonical terminal semantics、termination snapshot、lifecycle reset、KF innovation、prediction/coast、TTC 面积预处理及既有 D3/D4/D5 gate/log 字段，不调用 AirSim 或 SimpleFlight。
- `OptionalLos6DKalmanReplay`：delivery 风格 6D LOS KF 的离线 replay 后端。优先消费 D5 已组合的 `camera_to_ned_rotation`，否则使用 `body_to_ned_rotation @ camera_to_body_rotation`；两条路径都要求曝光时间与姿态/相机位姿时间同步，缺字段时明确 `unavailable`。在线默认仍使用现有 EMA/滑窗，不由该后端授权控制。
- `RuntimeGuidanceLaw` / `select_runtime_guidance_law(...)`：供 main 使用的四导引律选择合同。`pure_pursuit` 和 `radar_pn` 全程保持所选律；`png_vm` 和 `png_ttc` 先使用 `radar_pn`，仅在 D3/D4/D5 合同、视觉质量 gate 和迟滞全部通过后切换末端视觉律。旧离线名称 `pn` 只作为输入别名归一为 `radar_pn`。
- `compute_three_dimensional_pn_benchmark`：从注入的相对 NED 三维位置/速度计算 3D geometry PN 对照字段，只用于 benchmark/advisory，不替换默认二维 PN/PNG API。
- `run_guidance_strategy_comparison`：生成 PN、Pure Pursuit、`png_vm`、`png_ttc` 多 seed 对照行，字段包含 D6 可消费的 `min_range_m`、`terminal_range_m`、`closing_speed_mps`、bbox/LOS/maneuver gate pass rate、D4/D5/D3 consistency、threshold advisory version、`terminal_contract_reject_reasons`、`terminal_switch_reject_reasons` 和 `visual_png_switch_count`。
- 四律 runtime/comparison 日志显式区分 `requested_guidance_law` 与当前 `guidance_law`，并输出 law/mode transition、raw contract/gate、terminal wait/timeout 和 command saturation 字段。全程模式不伪造 D7 runtime bus 未计算的车辆命令，饱和状态为 `not_computed`。
- `evaluate_bbox_los_replay`：把 AirSim detect metadata、YOLO/ByteTrack bbox replay 归一成 `VisionGuidanceObservation`，离线评估 bbox/LOS/TTC gate；该路径显式 `vehicle_control=False`，不直接控制 SimpleFlight。
- `summarize_guidance_calibration`：消费多 seed D7 runtime outputs、`GuidanceRecord`、comparison rows 或 replay dict，按 PN、Pure Pursuit、`png_vm`、`png_ttc` 汇总 terminal range、closing speed、bbox/LOS/maneuver gate、D4 action block、D5 lock consistency、D3 owner/version consistency、secondary capability/readiness、D5 registration/projection/covariance/Yolo-MOT 摘要和 reject reasons，并输出阈值版本化 advisory。
- `summarize_locked_dropout_matrix`：汇总 1-5 帧 locked dropout 的状态、量测年龄、identity/plan 一致性、命令可用性与 fail-closed 合规率。
- `summarize_png_ttc_calibration`：按 seed 汇总有效 TTC，以及 area jump、bbox clipping、area not expanding、TTC out-of-range 四类拒绝覆盖。
- `evaluate_trend_coast_promotion`：只在 paired seeds、candidate 实际触发、wrong binding 为 0、命令不连续不恶化和物理成功不下降全部满足时给出 `promotion_recommended=True`；不会自动开启 trend coast。
- `summarize_cooperative_guidance_diagnostics` / `prescreen_cooperative_guidance_candidates`：消费 D7 runtime row 与 main 注入的物理/成员间距证据，形成 pair/primary/coalition 漏斗，并按“安全违规为 0、coalition completion、active-primary success、arrival spread”固定顺序预筛候选。该接口不生成 assignment、不授权、不调用车辆控制。
- main runtime P1 D4/D5 calibration sweep：由 main 统一编排 secondary height/FOV/count/standoff 与多 seed 组合，D6 在 sweep 结束后自动生成标准报告 bundle；D7 只提供上述 runtime summary、comparison rows、replay summary 和 calibration advisory 字段，不直接启动 AirSim、不写报告 bundle。
- 输出 LOS angle、LOS rate、closing speed、range、模式、横向加速度限幅、转向率限幅和离线质点轨迹记录。
- `simulate_guidance_episode` 支持单个 resource-target pair 的离线闭环，返回 `records` 和 `summary`。
- `guidance_records_from_assignment_dry_run` 接收 assignment/resource/target estimate 三类普通 Python 数据，输出一条 `radar_midcourse` 和一条 `vision_terminal` 干运行记录。

## 当前实现状态快照

截至当前代码和测试，D7 的“已实现”范围分为模块本地实现和 main/AirSim runtime 消费两层：

- 模块本地已实现经典二维 PN/PNG 几何核：`compute_proportional_navigation_command()` 使用位置/速度估计计算 `N * V_c * lambda_dot`，可用于中段雷达/全局航迹 PN，也可作为位置比例导引的离线上限模型。
- 模块本地已实现可解释的中段重捕 selector：每个 assignment pair 独立持有 `MidcourseReacquisitionSelector`。默认连续 2 帧 `closing_speed<=0`，或越过历史最近点后 range 回升至少 `2m`，切到最大转率 `0.9rad/s` 的 bounded Pure Pursuit；连续 3 帧 `closing_speed>=1m/s` 后回到 radar PN。返回命令 metadata 记录 `midcourse_guidance_selection`、`midcourse_selection_reason`、entry/recovery streak、overshoot 和 minimum range；不修改 PN 或 Pure Pursuit 核心函数。
- 模块本地已实现末端视觉 PNG gate：`SimpleFlightPngGuidanceFilter` 从 bbox 中心计算 bearing/LOS-rate，输出 raw/filtered LOS-rate、LOS-rate clamp/outlier evidence，支持 `law="png_vm"` 和 `law="png_ttc"`。仅 `png_ttc` 使用 delivery 等价的面积 EMA `0.25`、5 帧斜率、`16px2` 最小面积、`2.5` 跳变比、裁剪拒绝和 `20s` 最大 TTC；`png_vm` 不受该 TTC 有效性 gate 影响。
- 模块本地已实现每个 assignment pair 独立状态：`TerminalGuidanceDelivery` 保存该 pair 的 image KF、连续丢帧、命令窗口、blind push、`local_track_id`、filtered LOS-rate 和 bbox 面积窗口；`D7RuntimeBus` 按 `resource_id -> assigned_global_track_id` 持有独立 delivery/latch，并在 plan/version/owner/assignment signature、请求导引律变化或显式 `reset_pair()` 时重置。D7 不提供全局单例，也不假设 2v2/5v5。
- 模块本地已实现四律 runtime 选择：`D7RuntimePairInput.requested_guidance_law` 接受 `pure_pursuit|radar_pn|png_vm|png_ttc`；混合模式按 pair 选择 VM/TTC filter，模式切换会重置视觉候选状态但不会修改 `png_guidance_delivery` 的位置 PN/TTC/VM 公式。secondary pending、assignment/lease 过期、D4 owner/version 不一致、D5 非 `locked` 或目标 ID/version 不一致时，视觉 PNG 必须保持阻断。
- 模块本地已补齐 runtime bus 可消费记录：`D7RuntimePairOutput.as_log_record()` 暴露 `terminal_delivery_state/reason`、measured lock、extrapolation、loss count、prediction age、blind elapsed/decay、command sample count，以及既有 handoff、D3/D4/D5、bbox/LOS/TTC 和 3D PN 字段；`summarize_runtime_bus_outputs()` 聚合 delivery state/reason、外推、重捕、coast 到期和既有 gate/switch/reject 指标。
- 模块本地已实现 PN/Pure Pursuit/`png_vm`/`png_ttc` 多 seed 对照接口、YOLO/ByteTrack bbox replay 到 LOS gate 的离线接口，以及 P1 calibration summary helper；这些接口只生成报告行、gate 摘要和 advisory，不进入 SimpleFlight 控制主线。
- `summarize_guidance_calibration()` 输出 `threshold_advisory.version="d7-p1-guidance-calibration-advisory-v1"` 和顶层 `threshold_advisory_version`，字段覆盖 `terminal_range_m`、`min_bbox_area_ratio`、`max_visual_latency_s`、`min_closing_speed_mps`、`min_maneuver_margin`、D4 action block、D5 lock/D3 owner-version consistency、secondary capability/readiness 和 D5 registration/projection/covariance/Yolo-MOT 摘要。所有建议均带 `advisory_only=True`、`default_control_law_changed=False`、`d3_d4_d5_gate_bypassed=False`，不修改默认 PN/PNG 控制律。
- main runtime 已新增 P1 D4/D5 calibration sweep，D6 标准报告 bundle 已自动生成 records CSV、summary CSV、summary JSON 和 Markdown。D7 不把该 sweep 记为本模块未完成能力；D7 的职责是保证可被 sweep/D6 消费的 gate、handoff、reject reason、guidance law 和 threshold advisory 字段稳定。
- 3D/高度差/FRPN 在 D7 summary 中只作为 benchmark/advisory 字段：`compute_three_dimensional_pn_benchmark()` 和 runtime bus 可记录 `height_delta_m`、`range_3d_m`、`pn3d_los_rate_norm_radps`、`pn3d_commanded_accel_norm_mps2`、`frpn_benchmark_score` 和 FRPN variant 计数；这些字段不会替换默认 `compute_proportional_navigation_command()` 或 `SimpleFlightPngGuidanceFilter` API。
- runtime 已实际消费 D7 API：`research_modules/airsim_runtime/intercept.py` 为每个 `InterceptPair` 持有独立 `visual_filter`、`guidance_binding`、D4 permission 和 D5-shaped terminal association，并把 `PngGuidanceCommand.velocity_ned` 交给 SimpleFlight `moveByVelocityZAsync` 链路。D7 模块本身不直接连接 AirSim。
- 2026-07-07 main/runtime 复核后，真实 D7 执行结果已由 main/orchestrator 合并进正式 `main_episode_bus_metrics.json`；执行前合同诊断仍保留在 raw `main_episode_bus_contract_metrics.json`。D7 只提供 gate/command/log 字段，D6 和 main 负责正式指标聚合。
- D3 `request_center_replan` 闭环已接线到 main/runtime：中心重规划后必须生成新的有效 plan/binding/version。D7 只接受当前生效的 D3 binding/version；stale、revoked、plan mismatch、D4 owner mismatch/missing 或 D4 reassign/degrade 窗口内的旧 D5 lock 均不得进入视觉 PNG。
- D4 主动降级已区分硬风险与软风险。`d3_assignment_cost_margin_low`、无冲突 D5 `ambiguous/reacquire`、短时低置信度等软证据若被 D4 判为 `continue_center` 或 `request_secondary_assist`，D7 不把它们当作重规划阻断。assist 的 `target_node_id` 只标识 cue 提供者；只有 D3 binding 已显式切为二级 owner 时才要求 D4 `takeover_ready`。
- runtime 默认 `intercept_guidance_law="png_vm"`；`png_ttc` 在 D7 API 和 delivery 复现实验中可用，但不是当前默认 AirSim controlled intercept 路径。

以下 2v2 与四律 smoke 段落是历史证据，用于保留当时配置和结论；当前状态以本页顶部的 M=5、N=2 验证为准。

### 历史证据：2026-07-10 真实 AirSim 2v2 单 seed

只读复核 `outputs/p1_gap_closure_2v2_smoke_20260710/episode_006_full_flow/` 后，可以确认当前链路已在一次 seed=1 的 Blocks/SimpleFlight episode 中完成 2/2 assigned-target 碰撞拦截。两个 pair 的 `status` 均为 `collision_intercept`，碰撞对象分别匹配 `MSM_TargetActor_1` 和 `MSM_TargetActor_2`；拦截时间为 3.4s、3.5s，记录的最小距离为 2.003m、1.758m。该结果验证的是当前 actor mesh 碰撞判据下的单次闭环成功，不是统计意义上的命中率或视觉 PNG 稳定性结论。

本次 `control_commands.csv` 共 71 行。`guidance_law` 记录为 `radar_pn=49`、`png_vm=21`、`los=1`；状态模式为 `radar_midcourse=30`、`reacquire=30`、`abort_revoke=7`、`vision_terminal=4`。只有 INT-01 出现 4 帧 `vision_terminal`，INT-02 全程没有进入该模式，因此 2/2 成功主要证明雷达 PN、保守回退、二级重分配和碰撞判据能够闭合，不能归因为两架资源都稳定完成了视觉 PNG 接管。

视觉切换通过率仍低：原始 CSV 只有 2/71 行 `terminal_switch_allowed=True`，D6 execution metrics 给出的通过率为 0.0282；camera、LOS、maneuver gate 通过率分别为 0.2254、0.2394、0.0563。合同拒绝主要是 `d5_not_locked=30` 和 `d4_reassign_pending=18`，视觉 gate 拒绝主要是 `maneuver_margin_low=13`、`bbox_near_image_edge=7`、`los_rate_window_too_short=2`。`d7_execution_metrics.json` 的合并拒绝计数把合同拒绝也纳入 terminal switch reject，并记录 `bbox_near_image_edge=9`；同时其 `visual_png_switch_count=3` 与原始 CSV 的 2 个 allowed 样本不是同一统计口径。后续多 seed 报告必须同时保留 raw row gate pass、mode transition 和 aggregate switch count，不能把三者混为一个指标。

### 历史证据：2026-07-10 真实 AirSim 2v2 10-seed

main 随后完成 `p1_gap_closure_2v2_multiseed_20260710` 的 seeds 1-10。20 个 pair 中 18 个为 assigned-target `collision_intercept`，成功率为 90%；另外 2 个均为 INT-02 的 `terminal_detection_timeout`，分别发生在 seed 3 和 seed 10。D7 pair 级平均 `min_range_m=2.113m`，18 个成功 pair 的平均拦截时间为 3.589s；D6 execution episode 聚合的平均最小距离为 1.812m。两种最小距离来自不同聚合层级，必须分别标注，不能直接互换。该批次证明默认 SimpleFlight 混合闭环在多数 seed 可完成任务，同时把末端检测连续性暴露为真实失败模式。

884 行控制记录的 `guidance_law` 聚合为 `radar_pn=530`、`png_vm=289`、`los=65`；`visual_png_switch_count=88`，各 seed `terminal_switch_allowed_rate` 的算术均值为 0.0822。该通过率跨 seed 波动显著：seed 3 为 0.3642，seed 4 和 seed 10 为 0。D7 execution metrics 合并口径下，主要拒绝原因为 `d5_not_locked=309`、`maneuver_margin_low=194`、`bbox_near_image_edge=182`、`d4_reassign_pending=165`；这些是逐帧/合并计数，不能直接解释为独立失败 episode 数。

这一批次完成了默认 radar PN + `png_vm`、必要时 LOS fallback 的首轮多 seed 验证。其中两次 `terminal_detection_timeout` 仍需按 pair/seed 分离 D5 检测连续性、bbox 边缘裁切、机动裕度和 D4 重分配窗口的影响。

### 历史证据：2026-07-11 真实 AirSim 四导引律同条件 smoke

`p1_guidance_four_law_smoke_20260711` 已将 D7 四律 selector 接入真实 Blocks/SimpleFlight 执行。试验固定 2v2、seed 7 和初始几何，四律之间用 AirSim reset 隔离，每律只运行 2 s。Pure Pursuit、Radar PN、PNG-VM 和 PNG-TTC 的 pair 平均最小距离分别为 `2.922 m`、`3.905 m`、`2.913 m`和 `2.884 m`；四律均为 `timeout`。PNG-VM/PNG-TTC 的 `terminal_switch_allowed` 率约为 `0.762/0.810`，非视觉律为 `0`，符合 Pure Pursuit/Radar PN 不进入视觉交接的设计。该证据确认 D3 版本化 binding、D4 许可、D5 locked/ID 一致性和 D7 视觉 gate 已进入真实 SimpleFlight 四律执行链。

D6 生成的 21 条是指标配对行，不是 21 个独立 seed。由于本轮只有单 seed、2 s 短窗口且四律全部 timeout，最小距离只能用于确认接口和口径，不能据此比较命中率、优劣或定型阈值。较长时长、多 seed 同条件四律对照仍为 P1；3D PN、True PN、APN、FRPN 转入 P2 optional benchmark。后续只允许校准切换策略和 advisory，不修改 `png_guidance_delivery` 核心公式，不放宽 D3/D4/D5 合同。

当前切换策略不是单一距离阈值：

- 中段 PN/PP 重捕由 `MidcourseReacquisitionConfig` 控制，进入和退出使用不同 closing-speed 门限及连续帧迟滞。M5N2 seed1 中 INT-01/INT-04 分别在 `34.13m/24.14m` 后发散到 `143.64m/151.04m`，说明 closing 变负后继续经典 PN 不能自行恢复；该 helper 只在中段临时选择 bounded Pure Pursuit，恢复正 closing 后回 PN。
- D7 离线仿真的 `GuidanceConfig.terminal_switch_range_m` 默认是 `250.0m`，只用于二维质点研究。
- AirSim controlled intercept 的默认 `intercept_terminal_switch_range_m` 是 `8.0m`，命令行可通过 `--intercept-terminal-range` 改动；若测试使用 `30m` 左右的 `relative_position_ned`，那是 gate/回归夹具，不是算法硬编码常量。
- 进入视觉 PNG 前必须先通过 D3/D4/D5 contract，再通过 bbox 面积、置信度、边缘距离、稳定帧、视觉延迟、filtered LOS-rate/方差、TTC/闭合速度和机动裕度 gate。默认稳定帧阈值为 `min_stable_frames=2`，默认 terminal latch 不额外增加 dwell/reacquire 延迟；需要抑制 locked/reacquire 抖动时，可配置 `terminal_dwell_frames`、`terminal_release_frames` 和 `terminal_reacquire_grace_frames`，拒绝原因为 `terminal_dwell_active`、`terminal_release_grace` 或 `reacquire_grace_active`。
- Fresh visual PNG 仍要求 D5 `decision_state="locked"`。既有 measured lock 之后，D5 明确 `reacquire`、本帧无 observation、D3/D4/身份/版本/friend/safety 合同仍一致时，只允许 bounded KF/coast；D4 或安全合同失败仍立即清空该 pair 外推状态。
- D4 `request_center_replan`、`degrade_to_secondary`、`degrade_to_distributed` 均被保守映射为 `d4_reassign_pending`，D7 必须阻断视觉 PNG。`request_secondary_assist` 不改变当前 plan owner，也不要求 takeover readiness；真正二级 plan 由 D3 binding 的显式 secondary-owner 元数据识别，并且只有 D4 readiness/capability 明确为 `takeover_ready` 时才可进入后续视觉 gate。D7 会记录 `d4_action_block_reason` 解释阻断，直到新的中心/二级 plan 生效并与 D3 binding 的 plan/version/owner 一致。
- D4 `continue_center` 不等于强制视觉切换；它只表示没有重规划/降级阻断。D7 仍必须继续检查 D5 `locked`、D3 version、bbox 稳定、延迟、LOS-rate、TTC/闭合速度和机动裕度。

## N-pair AirSim runtime 接入边界

D7 不拥有 AirSim 控制状态机，也不创建 `InterceptPair`。仿真规模由 main runtime 的 `--drone-count N` 统一决定；main/runtime 当前已按 D3 输出和 cooperative topology 枚举有效 assignment pair，并为每个 pair 创建独立 D7 控制上下文。该上下文至少持有 resource/target ID、D3 binding、D4 permission、D5 `TerminalAssociation`、初段位置 PNG/PN 记录状态和该 pair 自己的 `TerminalGuidanceDelivery` 实例。`D7RuntimeBus.inject_state(...)` 接受任意长度 pair 输入，不假设固定 2v2 或 5v5：

- 中段为每个 pair 保存一个 `MidcourseReacquisitionSelector`，调用 `compute_midcourse_reacquisition_command(...)` 输出 radar PN 或 bounded Pure Pursuit 重捕命令。D7 terminal filter 对兼容的单调滚动版本更新保留状态，对 owner/target/activation/角色变化或版本回退重置；该保持不替代 main 的中段 selector 生命周期管理。
- 末端先调用 `evaluate_terminal_png_contract(...)`；只有 D3/D4/D5 合同持续通过时，才允许该 pair 的 `TerminalGuidanceDelivery` 处理 measured bbox 或 `observation=None` 的 bounded prediction/coast。
- 第一次进入末端但没有 D5 lock 时只输出 `acquiring`，不伪造 visual lock；同一 `assigned_global_track_id` 在短时丢测后恢复才输出 `reacquired`；coast 到期输出 `expired/terminal_visual_lost_after_coast`。
- 合同拒绝时 runtime 立即清空 image KF、命令窗口和 blind push，记录原 `terminal_contract_reject_reason`，且 `selected_velocity_ned=None`。调用方只有在 `visual_png_enabled=True` 时才消费 `selected_velocity_ned`。
- 每个 time-series 样本建议额外保留 `terminal_delivery_state`、`terminal_delivery_reason`、`terminal_visual_lock_measured`、`terminal_using_extrapolation`、`terminal_loss_frame_count`、`terminal_prediction_age_s`、`terminal_blind_elapsed_s`、`terminal_blind_decay` 和 `terminal_command_sample_count`。

`tests/test_proportional_guidance.py::test_runtime_sized_pairs_keep_independent_terminal_gate_and_png_time_series` 覆盖 1/3/5/7 个 pair 的并行 D7 合同、初段 radar PN、`png_vm`、TTC 和 time-series 字段形状；`test_runtime_bus_injects_n_pairs_with_independent_filters_and_summary` 覆盖 `D7RuntimeBus` 任意 N-pair 注入、D6-friendly summary 和 gate pass rate；`test_runtime_bus_blocks_visual_png_for_d4_reassign_actions_even_with_good_bbox` 覆盖 D4 `request_center_replan`、`degrade_to_secondary`、`degrade_to_distributed` 阶段即使 bbox 良好也不调用视觉 PNG；`test_runtime_bus_applies_reacquire_grace_after_d5_locked_jitter` 覆盖 locked/reacquire 抖动后的 reacquire grace；`test_visual_png_filters_los_rate_spike_before_near_range_command` 覆盖近距视觉 PNG LOS-rate 尖峰限幅/拒绝；`test_3d_pn_benchmark_logs_advisory_fields_without_replacing_default_png` 覆盖 3D geometry PN benchmark/log 字段。2v2 actor 拦截仍可作为 baseline 和 active-secondary 合同回归，但不能作为 main runtime 的数量假设。

## 中心化 M-to-N coalition 导引门控

`AssignmentGuidanceBinding` 可选携带 `coalition_id/coalition_version`、`member_role`、`wave_id`、`coordination_mode`、`arrival_window_start_s/arrival_window_end_s`、`activation_state`、activation 的 plan/track/coalition version，以及 `terminal_authorization_scope/arrival_coordination_required`。未提供这些字段的 k=1 binding 保持原合同兼容；显式 coalition binding 才启用联盟门控，新字段缺省为旧 `coalition + arrival required` 语义。

- `primary` 只能处于 wave 0；在 `simultaneous/sequential/hybrid` 模式下，进入 arrival window 前继续 radar PN，窗口关闭后仍阻断视觉 PNG，但模式解释为继续 `radar_midcourse` 等待新版本/时间窗，不再把有效 assignment 误记为撤销。
- 默认 `coalition` scope 下，所有显式 coalition 成员都要求本资源 D5 `locked`，D5 plan/track/coalition version 与 D3 binding 一致，并提供完整 coalition visual completion 证据。D7 接受显式 `coalition_visual_complete=true`，或由 `planned_cooperative_lock=true`、`support_count >= required_resource_count` 且无 coalition conflict 推导完成；缺证据、未完成或冲突分别拒绝为 `coalition_visual_completion_missing`、`coalition_visual_incomplete`、`coalition_visual_conflict`。
- 仅对显式 `per_primary + arrival_coordination_required=false`，D7 跳过共同 arrival window 和 coalition visual completion 两个协调条件；当前资源自己的 `locked`、D3 owner/version current、D4 permission、coalition identity/version、fallback commit/ACK/lease/epoch、friend/duplicate、camera/bbox/LOS/maneuver 仍全部必需。runtime row/summary 输出 scope、`per_primary_authorization_active`、`coalition_visual_completion_bypassed` 和 `bypassed_arrival_only`，便于确认只取消协同到达/同帧锁要求。
- `reserve/retry` 必须位于非零 wave；即使已有视觉匹配，standby 仍以 `coalition_not_activated` 阻断。只有新版本显式 `active/activated`，且 activation plan/track/coalition version、D4 新 plan/coalition version 和 D5 双版本均与当前 binding 一致时，才进入已有视觉 PNG gate。
- D4 `request_center_replan/degrade_to_secondary/degrade_to_distributed` 和 pending 阶段保持 `d4_reassign_pending` 阻断；最终 no-change ack 映射为 `continue_center` 后仍必须重新通过 D5/coalition/视觉质量门。D4 `hold/revoke/coalition_fallback_unsupported` 直接阻断；中心不可用且 `atomic_coalition_formed` 不为真时，以 `atomic_coalition_missing` 阻断。
- 每个 `resource_id -> assigned_global_track_id` 仍持有独立 filter/latch；多个 pair 可以共享同一个 center-owned `global_track_id`，D7 不改写该 ID，也不自行形成联盟、激活 reserve 或选择波次。
- runtime row 明确输出 raw/effective contract、latched visual mode、effective control、mode transition 和 termination snapshot；summary 分层聚合并保留 `terminal_contract_allowed_count`、`visual_png_switch_count` 等 effective 口径兼容 alias。`tests/test_coalition_guidance_gate.py` 覆盖旧 coalition scope、per-primary 独立切换、T002 k=1、未激活 reserve、新版本激活、视觉完成缺失/未完成、版本不一致、D4 pending/reconfiguring、ACK/lease 和时间窗阻断。

该能力是中心下发合同的执行门控，不是 impact-time consensus、协同 PN 或碰撞规避控制律；`png_guidance_delivery` 的位置比例导引和 TTC 捷联比例导引核心公式未修改。

## 2v2 active-secondary 视觉 PNG 合同

AirSim Blocks 2v2 主动降级链路采用保守解释：D4 `degrade_to_secondary` 是重分配发起事件，不是 D7 视觉终端授权。D7 必须把它视为 `d4_reassign_pending`，日志模式映射为 `abort_revoke`，即使当前位置 PN、TTC、检测框和 D5 旧锁定状态看起来可用，也不能调用视觉 PNG。

二级节点 plan 生效后，D7 才能评估视觉 PNG。进入 `mode=vision_terminal` 且输出 `guidance_law=png_vm` 的必要条件是：

- D3 binding 已切到二级 resource/plan/version，且 assignment 仍为 authorized/current。
- D4 action 为 `continue`/`continue_center`，当前 D3 binding 已显式标记 secondary owner，可选的 `new_plan_id/new_plan_version/target_node_id` 与当前 plan/version/owner 一致，且 D4 `secondary_capability_class` 或 `secondary_readiness_class` 明确为 `takeover_ready`。单纯 `request_secondary_assist` 仍使用中心 plan，`target_node_id` 仅表示 cue 提供者。
- D5 terminal association 为 `decision_state=locked`，无 friend conflict，`assigned_global_track_id` 和 `assignment_version` 与当前 binding 一致。
- 当前视觉观测的 `assigned_global_track_id` 与 binding 一致，随后才允许调用该二级 pair 自己的 `SimpleFlightPngGuidanceFilter(PngGuidanceConfig(law="png_vm"))`。

`tests/test_proportional_guidance.py::test_2v2_active_secondary_visual_png_requires_effective_secondary_plan` 固化真正接管合同；`test_secondary_assist_target_is_cue_not_assignment_owner` 固化中心 owner 与 assist cue 不同仍可继续 radar PN 并在视觉稳定后进入 `png_vm`。重规划、二级未 ready 和 distributed commit 未完成的负向回归保持不变。

## PNG guidance delivery 融合边界

`png_guidance_delivery` 已复制到本模块下作为算法来源和复现实验资料。主线当前只吸收其中与 SimpleFlight/AirSim detect 兼容的算法核：

- 相机检测框到视线角的几何转换。
- LOS-rate 低通、滑窗质量判断、限幅和尖峰拒绝。
- bbox 面积扩张 TTC 估计。
- `png_ttc` 与 `png_vm` 两种终端导引增益。
- bbox 太小、贴边、检测不连续、视觉延迟过高、机动裕度不足时拒绝切入视觉终端。
- `terminal_image_kf.py` 的常角速度图像角度/角速度预测，以及 `terminal_extrapolation.py` 的连续丢帧、短窗口命令平均、blind duration 和指数衰减参数。

`terminal_delivery.py` 已把上述 KF/短时 coast 等价封装为 D7 可消费 API；measured/predicted bbox 继续调用现有 VM/TTC filter，P2 law 不进入该路径。以下内容仍不接入主线：PX4 Offboard、MAVLink body-rate/attitude、YOLO/TensorRT、真实飞控解锁和实机安全流程。AirSim 当前阶段继续使用 SimpleFlight `moveByVelocityZAsync`，视觉输入来自 AirSim `simGetDetections` 的 bbox 和相机元数据，不默认保存 PNG 图像。

## AirSim 目标命名约定

本次核对 `png_guidance_delivery` 后，D7 文档采用以下命名口径：

- 当前 main/runtime 默认目标 actor 和检测过滤名为 `MSM_TargetActor_*`，实际 spawn 名通常类似 `MSM_TargetActor_1`。D7 与 D5/D6 的运行时日志、handoff 记录和新测试应优先使用这个命名。
- 当前与 YOLO/视觉 PNG 联调推荐并默认使用 Blocks/AirSim 的无人机 mesh asset `Quadrotor1`；main runtime actor asset default 已由 main 同步为 `Quadrotor1`，后续重点是真实 AirSim 验证和阈值/检测调参。
- `png_guidance_delivery` 复现实验脚本仍保留历史 alias：`--mesh Intruder*`、`--intruder-actor-name IntruderActor`；truth/gimbal/strapdown actor 路径默认 `--intruder-actor-asset Quadrotor1`。`Intruder*`/`IntruderActor` 仅作为 legacy alias 和旧报告复现口径。
- `1M_Cube_Chamfer` 仅用于旧接口、旧报告或几何 baseline 复现；如需复现 cube 口径，应显式传入 `--intruder-actor-asset 1M_Cube_Chamfer`。

## 运行测试

从仓库根目录执行：

```bash
python3 -m pytest -q research_modules/d7_proportional_guidance/tests
```

## 接口示例

```python
from d7_proportional_guidance import (
    GuidanceConfig,
    GuidanceState,
    PngGuidanceConfig,
    SimpleFlightPngGuidanceFilter,
    VisionGuidanceObservation,
    simulate_guidance_episode,
)

config = GuidanceConfig(
    dt_s=0.05,
    navigation_constant=3.0,
    terminal_switch_range_m=250.0,
    max_lateral_accel_mps2=60.0,
    max_turn_rate_radps=0.8,
)
pursuer = GuidanceState("R0", 0.0, (0.0, 0.0), (180.0, 0.0))
target = GuidanceState("T0", 0.0, (1200.0, 150.0), (-20.0, 0.0))

records, summary = simulate_guidance_episode(pursuer, target, config)
print(summary["min_range_m"], summary["terminal_mode_entered"])
print(records[0].los_angle_rad, records[0].closing_speed_mps)
```

Pure Pursuit 对照示例：

```python
pp_config = GuidanceConfig(guidance_law="pure_pursuit", dt_s=0.05)
records, summary = simulate_guidance_episode(pursuer, target, pp_config)
print(summary["guidance_law"], summary["min_range_m"])
```

中段 PN 越目标重捕示例：

```python
from d7_proportional_guidance import (
    MidcourseReacquisitionSelector,
    compute_midcourse_reacquisition_command,
)

selector = MidcourseReacquisitionSelector()  # 每个 assignment pair 一个实例
command = compute_midcourse_reacquisition_command(
    selector,
    pursuer=pursuer,
    target=target,
    dt_s=0.1,
    navigation_constant=3.0,
    max_lateral_accel_mps2=20.0,
    max_turn_rate_radps=0.9,
)
print(command.metadata["midcourse_guidance_selection"])
print(command.metadata["midcourse_selection_reason"])
```

视觉 PNG gate 示例：

```python
gate = SimpleFlightPngGuidanceFilter(PngGuidanceConfig(law="png_vm"))
cmd = gate.evaluate(
    VisionGuidanceObservation(
        timestamp_s=0.2,
        bbox_xyxy=(300.0, 220.0, 360.0, 280.0),
        detection_confidence=0.9,
        local_track_id="R1:det-1",
        assigned_global_track_id="TGT-001",
    ),
    current_heading_rad=0.0,
    current_speed_mps=6.0,
    intercept_speed_mps=6.0,
    relative_position_ned=(20.0, 1.0, 0.0),
    relative_velocity_ned=(-4.0, 0.0, 0.0),
)
print(cmd.quality.terminal_switch_allowed, cmd.quality.reject_reason)
```

AirSim phase-1 干运行接口只接受离线夹具或 DTO，不导入 `airsim`，不连接仿真器，也不调用车辆控制 API：

```python
from d7_proportional_guidance import (
    guidance_records_from_airsim_dry_run_fixture,
    make_minimal_airsim_dry_run_fixture,
)

fixture = make_minimal_airsim_dry_run_fixture()
records, summary = guidance_records_from_airsim_dry_run_fixture(fixture)
print([record.mode.value for record in records], summary["boundary"])
```

如果未安装为包，可在命令行示例中临时加入模块路径：

```bash
PYTHONPATH=research_modules/d7_proportional_guidance python3 - <<'PY'
from d7_proportional_guidance import simulate_guidance_episode

records, summary = simulate_guidance_episode()
print(len(records), summary)
PY
```

## 数据约定

- 所有位置为米 `m`，速度为米每秒 `m/s`，加速度为米每二次方秒 `m/s^2`。
- 角度为弧度 `rad`，角速度/LOS rate 为 `rad/s`。
- `GuidanceRecord.range_m` 是真实二维几何距离；`los_angle_rad` 和 `closing_speed_mps` 来自当前模式的估计状态。
- `GuidanceCommand` 中 `commanded_*` 为原始 PN 计算值，`limited_*` 为加速度和转向率约束后的值。
- `GuidanceMode` 当前包括 `radar_midcourse`、`handover_pending`、`vision_terminal`、`hold`、`reacquire`、`abort_revoke`。`hold/reacquire/abort_revoke` 是日志和状态机语义，不表示绕过 D3/D4/D5 授权链路的本地重分配。

## 边界

该模块用于离线二维质点仿真、runtime state injection、末端视觉 PNG gate 和报告/advisory 字段生成。它不读取或写入真实平台接口，不控制实体设备，不处理作战授权，不提供毁伤评估，也不创建、分配或改写 `global_track_id`；`PngGuidanceCommand.velocity_ned` 是供 main/runtime 仿真消费的 SimpleFlight 速度抽象，不是可直接用于真实系统执行的控制命令。
