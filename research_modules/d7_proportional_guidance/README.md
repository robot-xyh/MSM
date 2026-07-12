# D7 比例导引与末端视觉 PNG 模块

## 最新状态（2026-07-11）

- P0 无未闭合 blocker，当前 D7 回归基线为 `109 passed`；P1 合同层已经闭合。
- M=5、N=2 的 ComputerVision 10-seed 验证达到约定的 8/10 双 primary 合同验收；这证明版本化计划、联盟、视觉共识和 D7 许可链可闭合，不等于控制许可或物理命中。
- D4 commit-aware gate 已实现并接入 main/runtime；正确 topology 已接线为 T001 两个 active primary、一个 standby reserve，T002 一个 active primary，第五个资源未分配。
- 同 topology 的 SimpleFlight 15 s 诊断中，30 个 active pair 为 0 命中，其中 24 个 `terminal_detection_timeout`；物理拦截闭环仍开放，当前 P1 聚焦末端检测持续性、控制频率/时长与真实命中。
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
    arrival_windows={"T001": (5.0, 12.0)},
)
```

该输入生成 T001 的两个 `primary/wave-0/active`、一个 `reserve/wave-1/standby`，以及 T002 的单 primary；第五个资源进入 `unassigned_resource_ids`。main/runtime 已按该 topology 创建实际 pair，15 s SimpleFlight 诊断的统计分母因此是 30 个 active pair，不包含 10 个 standby reserve。未提供 coordinated arrival window 时，binding 保持 terminal fail-closed；standby reserve 即使 D5 提供完整视觉锁定也以 `coalition_not_activated` 阻断视觉 PNG。

本模块实现“经典比例导引架构”的二维研究核、D3/D4/D5 terminal contract、末端视觉 PNG gate 和 D7-owned runtime bus 日志适配。模块只处理抽象的 `GuidanceState`、`GuidanceCommand`、`GuidanceRecord`、`VisionGuidanceObservation` 和版本化分配/末端锁定状态；main/runtime 可以消费 D7 输出的 SimpleFlight 兼容速度命令和 gate 字段，但 D7 本身不直接连接 AirSim、SimpleFlight、PX4、硬件接口、火控参数、毁伤模型、自动处置或授权绕过流程。

## 目录

```text
research_modules/d7_proportional_guidance/
  PLAN.md
  README.md
  d7_proportional_guidance/
    __init__.py
    airsim_dry_run.py
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
- `TerminalGuidanceDelivery`：每 assignment pair 一个实例的末端短时外推 API，状态为 `acquiring/measured/image_kf_predict/blind_push/reacquired/expired`。默认 `control_dt=0.1s`、图像角度/角速度 KF predict `0.25s`、连续丢失 `3` 帧、命令平均 `0.10s`、blind push `0.25s`、衰减 `tau=0.18s`；measured/predicted bbox 仍由 `SimpleFlightPngGuidanceFilter` 计算，不修改位置 PN、TTC PNG 或 VM PNG 公式。
- `guidance_mode_from_terminal_contract(...)`：把 D3/D4/D5 末端合同结果映射为显式 D7 日志状态，包括 `handover_pending`、`hold`、`reacquire` 和 `abort_revoke`。
- `terminal_switch_allowed_rate` / `summarize_terminal_switch_quality`：对 D7 已输出的 gate 结果做离线通过率统计，不重新执行 runtime gate 逻辑。
- `D7RuntimeBus`：D7-owned N-pair state injection adapter。调用方为每个 assignment pair 注入当前 D3 binding、D4 permission、D5 terminal association 和可选 bbox observation；D7 为每个 `resource_id -> assigned_global_track_id` 维护独立 terminal delivery 和 latch，输出 delivery state/reason、prediction age、loss count、blind decay、terminal range/closing speed、D4/D5/D3 consistency、bbox/LOS/TTC、3D PN benchmark 和 gate/log 字段，不调用 AirSim 或 SimpleFlight。
- `RuntimeGuidanceLaw` / `select_runtime_guidance_law(...)`：供 main 使用的四导引律选择合同。`pure_pursuit` 和 `radar_pn` 全程保持所选律；`png_vm` 和 `png_ttc` 先使用 `radar_pn`，仅在 D3/D4/D5 合同、视觉质量 gate 和迟滞全部通过后切换末端视觉律。旧离线名称 `pn` 只作为输入别名归一为 `radar_pn`。
- `compute_three_dimensional_pn_benchmark`：从注入的相对 NED 三维位置/速度计算 3D geometry PN 对照字段，只用于 benchmark/advisory，不替换默认二维 PN/PNG API。
- `run_guidance_strategy_comparison`：生成 PN、Pure Pursuit、`png_vm`、`png_ttc` 多 seed 对照行，字段包含 D6 可消费的 `min_range_m`、`terminal_range_m`、`closing_speed_mps`、bbox/LOS/maneuver gate pass rate、D4/D5/D3 consistency、threshold advisory version、`terminal_contract_reject_reasons`、`terminal_switch_reject_reasons` 和 `visual_png_switch_count`。
- 四律 runtime/comparison 日志显式区分 `requested_guidance_law` 与当前 `guidance_law`，并输出 law/mode transition、raw contract/gate、terminal wait/timeout 和 command saturation 字段。全程模式不伪造 D7 runtime bus 未计算的车辆命令，饱和状态为 `not_computed`。
- `evaluate_bbox_los_replay`：把 AirSim detect metadata、YOLO/ByteTrack bbox replay 归一成 `VisionGuidanceObservation`，离线评估 bbox/LOS/TTC gate；该路径显式 `vehicle_control=False`，不直接控制 SimpleFlight。
- `summarize_guidance_calibration`：消费多 seed D7 runtime outputs、`GuidanceRecord`、comparison rows 或 replay dict，按 PN、Pure Pursuit、`png_vm`、`png_ttc` 汇总 terminal range、closing speed、bbox/LOS/maneuver gate、D4 action block、D5 lock consistency、D3 owner/version consistency、secondary capability/readiness、D5 registration/projection/covariance/Yolo-MOT 摘要和 reject reasons，并输出阈值版本化 advisory。
- main runtime P1 D4/D5 calibration sweep：由 main 统一编排 secondary height/FOV/count/standoff 与多 seed 组合，D6 在 sweep 结束后自动生成标准报告 bundle；D7 只提供上述 runtime summary、comparison rows、replay summary 和 calibration advisory 字段，不直接启动 AirSim、不写报告 bundle。
- 输出 LOS angle、LOS rate、closing speed、range、模式、横向加速度限幅、转向率限幅和离线质点轨迹记录。
- `simulate_guidance_episode` 支持单个 resource-target pair 的离线闭环，返回 `records` 和 `summary`。
- `guidance_records_from_assignment_dry_run` 接收 assignment/resource/target estimate 三类普通 Python 数据，输出一条 `radar_midcourse` 和一条 `vision_terminal` 干运行记录。

## 当前实现状态快照

截至当前代码和测试，D7 的“已实现”范围分为模块本地实现和 main/AirSim runtime 消费两层：

- 模块本地已实现经典二维 PN/PNG 几何核：`compute_proportional_navigation_command()` 使用位置/速度估计计算 `N * V_c * lambda_dot`，可用于中段雷达/全局航迹 PN，也可作为位置比例导引的离线上限模型。
- 模块本地已实现末端视觉 PNG gate：`SimpleFlightPngGuidanceFilter` 从 bbox 中心计算 bearing/LOS-rate，输出 raw/filtered LOS-rate、LOS-rate clamp/outlier evidence，支持 `law="png_vm"` 和 `law="png_ttc"`，并输出 SimpleFlight 可消费的水平 `velocity_ned`。
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
- D4 主动降级已区分硬风险与软风险。`d3_assignment_cost_margin_low`、无冲突 D5 `ambiguous/reacquire`、短时低置信度等软证据若被 D4 判为 `continue_center`/观察状态，D7 不把它们当作重规划阻断；只要 D3 current、D4 action 允许、D5 对同一 `assigned_global_track_id` 输出 `locked`，且二级 plan 的 D4 readiness/capability 已为 `takeover_ready`，D7 才继续按既有视觉 PNG gate 判定是否切换。
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

- D7 离线仿真的 `GuidanceConfig.terminal_switch_range_m` 默认是 `250.0m`，只用于二维质点研究。
- AirSim controlled intercept 的默认 `intercept_terminal_switch_range_m` 是 `8.0m`，命令行可通过 `--intercept-terminal-range` 改动；若测试使用 `30m` 左右的 `relative_position_ned`，那是 gate/回归夹具，不是算法硬编码常量。
- 进入视觉 PNG 前必须先通过 D3/D4/D5 contract，再通过 bbox 面积、置信度、边缘距离、稳定帧、视觉延迟、filtered LOS-rate/方差、TTC/闭合速度和机动裕度 gate。默认稳定帧阈值为 `min_stable_frames=2`，默认 terminal latch 不额外增加 dwell/reacquire 延迟；需要抑制 locked/reacquire 抖动时，可配置 `terminal_dwell_frames`、`terminal_release_frames` 和 `terminal_reacquire_grace_frames`，拒绝原因为 `terminal_dwell_active`、`terminal_release_grace` 或 `reacquire_grace_active`。
- D5 必须为 `decision_state="locked"`，无 friend conflict，显式 `execution_gate_pass/safety_gate_pass` 不能为 false，且 `assigned_global_track_id`、`assignment_version` 与当前 D3 binding 一致；任一失败时 D7 立即清空该 pair 的外推状态并拒绝视觉 PNG。
- D4 `request_center_replan`、`degrade_to_secondary`、`degrade_to_distributed` 均被保守映射为 `d4_reassign_pending`，D7 必须阻断视觉 PNG；二级 plan 只有在 D4 secondary readiness/capability 明确为 `takeover_ready` 时才可进入后续视觉 gate。D7 会记录 `d4_action_block_reason` 解释阻断，直到新的中心/二级 plan 生效并与 D3 binding 的 plan/version/owner 一致。
- D4 `continue_center` 不等于强制视觉切换；它只表示没有重规划/降级阻断。D7 仍必须继续检查 D5 `locked`、D3 version、bbox 稳定、延迟、LOS-rate、TTC/闭合速度和机动裕度。

## N-pair AirSim runtime 接入边界

D7 不拥有 AirSim 控制状态机，也不创建 `InterceptPair`。仿真规模由 main runtime 的 `--drone-count N` 统一决定；main/runtime 当前已按 D3 输出和 cooperative topology 枚举有效 assignment pair，并为每个 pair 创建独立 D7 控制上下文。该上下文至少持有 resource/target ID、D3 binding、D4 permission、D5 `TerminalAssociation`、初段位置 PNG/PN 记录状态和该 pair 自己的 `TerminalGuidanceDelivery` 实例。`D7RuntimeBus.inject_state(...)` 接受任意长度 pair 输入，不假设固定 2v2 或 5v5：

- 中段用 `compute_proportional_navigation_command(..., mode=GuidanceMode.RADAR_MIDCOURSE)` 输出 radar PN 几何量。
- 末端先调用 `evaluate_terminal_png_contract(...)`；只有 D3/D4/D5 合同持续通过时，才允许该 pair 的 `TerminalGuidanceDelivery` 处理 measured bbox 或 `observation=None` 的 bounded prediction/coast。
- 第一次进入末端但没有 D5 lock 时只输出 `acquiring`，不伪造 visual lock；同一 `assigned_global_track_id` 在短时丢测后恢复才输出 `reacquired`；coast 到期输出 `expired/terminal_visual_lost_after_coast`。
- 合同拒绝时 runtime 立即清空 image KF、命令窗口和 blind push，记录原 `terminal_contract_reject_reason`，且 `selected_velocity_ned=None`。调用方只有在 `visual_png_enabled=True` 时才消费 `selected_velocity_ned`。
- 每个 time-series 样本建议额外保留 `terminal_delivery_state`、`terminal_delivery_reason`、`terminal_visual_lock_measured`、`terminal_using_extrapolation`、`terminal_loss_frame_count`、`terminal_prediction_age_s`、`terminal_blind_elapsed_s`、`terminal_blind_decay` 和 `terminal_command_sample_count`。

`tests/test_proportional_guidance.py::test_runtime_sized_pairs_keep_independent_terminal_gate_and_png_time_series` 覆盖 1/3/5/7 个 pair 的并行 D7 合同、初段 radar PN、`png_vm`、TTC 和 time-series 字段形状；`test_runtime_bus_injects_n_pairs_with_independent_filters_and_summary` 覆盖 `D7RuntimeBus` 任意 N-pair 注入、D6-friendly summary 和 gate pass rate；`test_runtime_bus_blocks_visual_png_for_d4_reassign_actions_even_with_good_bbox` 覆盖 D4 `request_center_replan`、`degrade_to_secondary`、`degrade_to_distributed` 阶段即使 bbox 良好也不调用视觉 PNG；`test_runtime_bus_applies_reacquire_grace_after_d5_locked_jitter` 覆盖 locked/reacquire 抖动后的 reacquire grace；`test_visual_png_filters_los_rate_spike_before_near_range_command` 覆盖近距视觉 PNG LOS-rate 尖峰限幅/拒绝；`test_3d_pn_benchmark_logs_advisory_fields_without_replacing_default_png` 覆盖 3D geometry PN benchmark/log 字段。2v2 actor 拦截仍可作为 baseline 和 active-secondary 合同回归，但不能作为 main runtime 的数量假设。

## 中心化 M-to-N coalition 导引门控

`AssignmentGuidanceBinding` 可选携带 `coalition_id/coalition_version`、`member_role`、`wave_id`、`coordination_mode`、`arrival_window_start_s/arrival_window_end_s`、`activation_state` 和 activation 的 plan/track/coalition version。未提供这些字段的 k=1 binding 保持原合同兼容；显式 coalition binding 才启用联盟门控。

- `primary` 只能处于 wave 0；在 `simultaneous/sequential/hybrid` 模式下，进入 arrival window 前继续 radar PN，窗口关闭后阻断视觉 PNG。
- 所有显式 coalition 成员都要求本资源 D5 `locked`，D5 plan/track/coalition version 与 D3 binding 一致，并提供完整 coalition visual completion 证据。D7 接受显式 `coalition_visual_complete=true`，或由 `planned_cooperative_lock=true`、`support_count >= required_resource_count` 且无 coalition conflict 推导完成；缺证据、未完成或冲突分别拒绝为 `coalition_visual_completion_missing`、`coalition_visual_incomplete`、`coalition_visual_conflict`。
- `reserve/retry` 必须位于非零 wave；即使已有视觉匹配，standby 仍以 `coalition_not_activated` 阻断。只有新版本显式 `active/activated`，且 activation plan/track/coalition version、D4 新 plan/coalition version 和 D5 双版本均与当前 binding 一致时，才进入已有视觉 PNG gate。
- D4 `request_center_replan/degrade_to_secondary/degrade_to_distributed` 和 pending 阶段保持 `d4_reassign_pending` 阻断；最终 no-change ack 映射为 `continue_center` 后仍必须重新通过 D5/coalition/视觉质量门。D4 `hold/revoke/coalition_fallback_unsupported` 直接阻断；中心不可用且 `atomic_coalition_formed` 不为真时，以 `atomic_coalition_missing` 阻断。
- 每个 `resource_id -> assigned_global_track_id` 仍持有独立 filter/latch；多个 pair 可以共享同一个 center-owned `global_track_id`，D7 不改写该 ID，也不自行形成联盟、激活 reserve 或选择波次。
- runtime row 明确输出 `terminal_contract_allowed`、`visual_png_switch` 及合同/切换拒绝原因，summary 聚合 `terminal_contract_allowed_count`、`visual_png_switch_count` 和 reject reason 分布。`tests/test_coalition_guidance_gate.py` 覆盖 T001 两个 primary 独立切换、T002 k=1、未激活 reserve、新版本激活、coalition visual completion 缺失/未完成、版本不一致、D4 pending/no-change ack 和时间窗阻断。

该能力是中心下发合同的执行门控，不是 impact-time consensus、协同 PN 或碰撞规避控制律；`png_guidance_delivery` 的位置比例导引和 TTC 捷联比例导引核心公式未修改。

## 2v2 active-secondary 视觉 PNG 合同

AirSim Blocks 2v2 主动降级链路采用保守解释：D4 `degrade_to_secondary` 是重分配发起事件，不是 D7 视觉终端授权。D7 必须把它视为 `d4_reassign_pending`，日志模式映射为 `abort_revoke`，即使当前位置 PN、TTC、检测框和 D5 旧锁定状态看起来可用，也不能调用视觉 PNG。

二级节点 plan 生效后，D7 才能评估视觉 PNG。进入 `mode=vision_terminal` 且输出 `guidance_law=png_vm` 的必要条件是：

- D3 binding 已切到二级 resource/plan/version，且 assignment 仍为 authorized/current。
- D4 action 为 `request_secondary_assist` 或 `continue_center`，可选的 `new_plan_id/new_plan_version/target_node_id` 与当前 D3 binding 的 plan/version/owner 一致，且二级 plan 的 D4 `secondary_capability_class` 或 `secondary_readiness_class` 明确为 `takeover_ready`。
- D5 terminal association 为 `decision_state=locked`，无 friend conflict，`assigned_global_track_id` 和 `assignment_version` 与当前 binding 一致。
- 当前视觉观测的 `assigned_global_track_id` 与 binding 一致，随后才允许调用该二级 pair 自己的 `SimpleFlightPngGuidanceFilter(PngGuidanceConfig(law="png_vm"))`。

`tests/test_proportional_guidance.py::test_2v2_active_secondary_visual_png_requires_effective_secondary_plan` 固化该合同：主动降级阶段拒绝为 `d4_reassign_pending`；二级 plan 版本不一致拒绝为 `d4_plan_mismatch`；二级 plan 生效、D4 readiness/capability 为 `takeover_ready` 且 D5 locked 后才产生 `png_vm`/`vision_terminal`。

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
