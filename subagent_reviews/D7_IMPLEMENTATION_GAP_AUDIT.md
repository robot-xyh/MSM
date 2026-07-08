# D7 比例导引与末端视觉 PNG 实现差距审计

**审计范围**：`research_modules/d7_proportional_guidance/` 的 README、PLAN、代码和测试，`png_guidance_delivery/` 方案资料，以及 D7 在 `research_modules/airsim_runtime/intercept.py` 中被消费的实际状态。
**修改边界**：本次只更新 D7-owned 代码、测试、文档和 `subagent_reviews/D7_*`，不修改 D1-D6、main runtime、root report 或其他模块。
**系统边界**：D7 只做导引律、导引状态、末端 PNG gate 和日志合同；D7 不分配目标、不授权、不创建、不改写、不本地重绑 `global_track_id`。

## 总体结论

D7 当前已经实现可测试的二维位置 PN/PNG 几何核、中段雷达/全局航迹 PN、离线 `radar_midcourse -> vision_terminal` 质点仿真、AirSim phase-1 dry-run 记录适配、末端视觉 `png_vm/png_ttc` 轻量 gate、每个 assignment pair 独立视觉导引状态、D3/D4/D5 terminal contract、显式 `handover_pending/hold/reacquire/abort_revoke` 日志状态，以及 SimpleFlight 速度命令抽象。

真实 AirSim SimpleFlight 控制不在 D7 模块内直接执行，而是 main/runtime 的 `intercept.py` 消费 D7 API：每个 `InterceptPair` 持有自己的 `AssignmentGuidanceBinding`、`D4GuidancePermission`、D5-shaped terminal association 和 `SimpleFlightPngGuidanceFilter`，将 `PngGuidanceCommand.velocity_ned` 交给 `command_velocity_z()`/`moveByVelocityZAsync`。因此 D7 文档必须把“D7 实现了可消费的导引/gate/命令抽象”和“main runtime 实际下发 SimpleFlight 命令”分开描述。

`png_guidance_delivery` 已纳入 D7 目录作为方案和复现实验包。主线实际使用的只有轻量子集：bbox-to-bearing、LOS-rate 窗口、bbox 面积 TTC、`png_vm/png_ttc` 增益思想、质量 gate 和 SimpleFlight 速度命令。delivery 中的 truth/gimbal/strapdown、PX4/MAVLink/body-rate、YOLO/ByteTrack、KF/外推和报告仍是参考或独立实验路径，不能写成 main D7 默认路径。

2026-07-07 复核：main/runtime 已把真实 D7 控制执行产物合并进正式 `main_episode_bus_metrics.json`，并把执行前合同诊断保留为 raw `main_episode_bus_contract_metrics.json`。D3 `request_center_replan` 后的新中心 plan/binding/version 已接到 D7 current binding gate；D4 软风险和无冲突 D5 `reacquire/ambiguous` 不再被当作必然重规划/降级阻断。D7 本轮不需要修改 PN/PNG 控制律本体，只需保持 gate 和日志合同回归。

2026-07-08 D7 子智能体复核：D7-owned `runtime_bus.py`、`comparison.py`、`replay.py` 已补齐并由 D7 tests 覆盖。D7RuntimeBus 支持任意 N-pair state injection、每 pair 独立 filter、同一 pair plan/version/owner signature 变化时 reset；comparison 输出 PN/Pure Pursuit/`png_vm`/`png_ttc` 多 seed report rows；replay 将 YOLO/ByteTrack/AirSim bbox rows 离线映射到 D7 bbox/LOS/TTC gate，且显式不调用 SimpleFlight。D4 owner/version gate 已加强：D4 指定接管 owner 时，当前 D3 binding 必须携带同一 owner，旧 lock 或 owner mismatch/missing 均不得进入视觉 PNG。main runtime 已把 D7 runtime summary 接入 episode bus；controlled 5v5 center replan 与 2v2 secondary visual PNG gate 回归已通过。

2026-07-08 D7 actor asset 复核：D7 `png_guidance_delivery` truth/gimbal/strapdown example 的 `--intruder-actor-asset` 默认值已从历史 cube `1M_Cube_Chamfer` 对齐为 Blocks/AirSim 无人机 mesh asset `Quadrotor1`，并新增测试锁定默认值。main runtime 的 actor asset CLI/default 已由 main 同步为 `Quadrotor1`；cube 仅作为旧接口、旧报告或几何 baseline 显式复现选项。后续重点是真实 AirSim 验证和阈值/检测调参。

## 已实现

| 项 | 实现状态 | 关键证据 | 当前口径 |
|---|---|---|---|
| 中段雷达 PN/PNG | 已实现 | `d7_proportional_guidance/pn.py`; `simulator.py`; `airsim_dry_run.py`; `tests/test_proportional_guidance.py` | `compute_proportional_navigation_command()` 用二维相对位置/速度计算 `N * V_c * lambda_dot`，记录 range、LOS、LOS-rate、closing speed、限幅加速度和限幅转向率。 |
| 位置比例导引融合 | 已实现主线等价核 | `pn.py`; `airsim_runtime/intercept.py` 读取该 API | delivery 的 truth PNG 不被主线直接调用；主线用 D7 PN 几何和 actor/global-track 等价估计实现位置 PN/PNG。 |
| 末端视觉 PNG gate | 已实现轻量主线核 | `vision_png.py`; D7 tests | `SimpleFlightPngGuidanceFilter` 从 bbox 中心生成 bearing/LOS-rate，支持 `los`、`png_vm`、`png_ttc`，并输出 `PngGuidanceCommand.velocity_ned`。 |
| TTC 捷联比例导引融合 | 已实现 API/实验可用，非默认 runtime | `vision_png.py`; `png_guidance_delivery/README.md` | `law="png_ttc"` 保留 TTC 增益调度；AirSim controlled intercept 当前默认 `png_vm`，TTC 主要在 D7 API、delivery 和后续回放对照中使用。 |
| 每个 assignment pair 独立导引状态 | 已实现 D7 侧基线 | `test_runtime_sized_pairs_keep_independent_terminal_gate_and_png_time_series` | filter 实例保存 `local_track_id`、稳定帧、LOS-rate 窗口、bbox 面积窗口；测试覆盖 1/3/5/7 pair，防止 2v2/5v5 固定数量假设。 |
| SimpleFlight 控制命令抽象 | 已实现并被 runtime 消费 | `vision_png.py`; `airsim_runtime/intercept.py`; runtime tests | D7 输出 `velocity_ned`；runtime 下发 `moveByVelocityZAsync` 并记录 `control_commands.csv`。D7 模块本身不连接 AirSim。 |
| D3/D4/D5 terminal gate | 已实现 D7 API | `terminal_gate.py`; D7 tests | 校验授权/current/expiry、plan/version、D4 action、D5 locked、friend conflict、D5 ID/version 和观测 global ID。 |
| D4 主动降级保守阻断 | 已实现 | `BLOCKING_D4_ACTION_REASONS`; D7 active-secondary 测试 | `request_center_replan`、`degrade_to_secondary`、`degrade_to_distributed`、`reassign` 均拒绝视觉 PNG，reject reason 为 `d4_reassign_pending`，日志模式映射 `abort_revoke`。 |
| D4 owner/version gate | 已实现 | `terminal_gate.py`; `test_terminal_contract_blocks_d4_reassign_until_new_owner_version_and_d5_lock`; `test_runtime_bus_resets_filter_when_same_pair_plan_signature_changes` | D4 提供 `target_node_id/new_plan_owner_id` 时，D3 binding 必须带同一 `owner_node_id`；同一 pair plan/version/owner 变化会重置视觉 filter，旧 D5 lock 不能跨 plan 复用。 |
| D5 locked 与 ID/version 一致才切换 | 已实现 | `evaluate_terminal_png_contract()`; D7 tests | 只有 `decision_state=="locked"`、无 friend conflict、`assigned_global_track_id` 与 binding 一致、`assignment_version == track_version` 时才允许后续视觉 gate。 |
| 30m/稳定 bbox 等切换策略 | 已实现为可配置 gate，不是硬编码 | `PngGuidanceConfig`; D7 tests; `BlocksSmokeConfig` | D7 离线默认 terminal range `250m`，AirSim runtime 默认 `8m`；测试中 `30m` 左右相对距离用于验证 gate。bbox 稳定默认 `min_stable_frames=2`，还需面积、置信度、边缘、延迟、LOS 方差、闭合速度和机动裕度通过。 |
| D7-owned N-pair runtime bus adapter | 已实现 | `runtime_bus.py`; `test_runtime_bus_injects_n_pairs_with_independent_filters_and_summary` | 调用方注入每个 pair 的 D3/D4/D5/observation 状态；D7 输出 gate/log 字段和汇总，不创建 assignment、不控制车辆、不假设 2v2/5v5。 |
| PN/Pure Pursuit/PNG 对照 report rows | 已实现 D7 接口 | `comparison.py`; `test_guidance_strategy_comparison_reports_all_p1_fields` | 输出 PN、Pure Pursuit、`png_vm`、`png_ttc` 多 seed rows，字段含 `min_range_m`、`time_to_intercept_s`、contract/switch reject reasons 和 `visual_png_switch_count`；D6/main 后续负责正式报告。 |
| YOLO/ByteTrack bbox/LOS 离线 replay adapter | 已实现 D7 接口 | `replay.py`; `test_bbox_los_replay_normalizes_yolo_bytetrack_and_stays_offline` | bbox replay rows 归一成 `VisionGuidanceObservation`，离线评估 D3/D4/D5 contract 与 bbox/LOS/TTC gate；summary 显式 `vehicle_control=False`、`simpleflight_control_called=False`。 |
| AirSim active center/secondary 合同回归 | 已通过当前 P1 回归 | `airsim_runtime/tests/test_blocks_runtime.py`; runtime CSV/summary 字段 | controlled 5v5 center replan 验证新 plan/binding/version 后 D7 才接受视觉 PNG；2v2 secondary visual PNG gate 验证 `degrade_to_secondary` 阶段阻断旧锁定，二级 owner/version 生效且 D5 locked 后才允许 `png_vm`。 |
| episode bus 真实执行指标回灌 | 已接线，保持回归 | `main_episode_bus_metrics.json`; `control_commands.csv`; `intercept_summary.json` | D7 runtime summary 已接入 episode bus；正式 metrics 可包含 D7 真实执行后的 `intercept_success_count`、`collision_intercept_count`、`guidance_law_counts` 等；raw contract metrics 仅作执行前诊断。 |
| D3 replan 后 current binding gate | 已接线并通过 controlled 5v5 回归 | `terminal_gate.py`; runtime summary/version metadata | D4 真正请求中心重规划后，D7 只接受新的当前 D3 binding/version；旧 plan、stale binding、revoked assignment 和 plan mismatch 均阻断视觉 PNG。 |
| D4 软风险 continue_center 路径 | 已接线，保持回归 | `D4GuidancePermission(action="continue_center")`; D7 tests | 低 cost margin、短时低置信度、无冲突 `ambiguous/reacquire` 由 D4 观察时，D7 不误映射为 `d4_reassign_pending`；后续仍需 D5 `locked` 和视觉 gate 通过。 |
| Pure Pursuit baseline | 已实现轻量版 | `compute_pure_pursuit_command()`; tests | 仅用于离线对照，不引入 PythonRobotics。 |

## 部分实现

| 项 | 当前做到什么 | 还缺什么 | 原因 | 优先级 |
|---|---|---|---|---|
| 真实 AirSim 多 seed calibration | main/runtime 已用 D7 PN/PNG gate 生成速度命令，并通过 SimpleFlight 高层速度接口执行；输出 `control_commands.csv`、`intercept_summary.json`、D7 runtime summary，正式 episode bus metrics 已能合并真实执行结果。 | 需要用真实 AirSim 多 seed 校准 terminal range、`png_vm/png_ttc`、bbox/LOS/TTC gate、视觉延迟、机动裕度和阈值版本，并形成 D6/main 分组报告。 | D7 不能生成 assignment、D4 仲裁或 D5 lock；D7 只提供可消费字段，校准数据和正式报告由 main/D6 组织。 | P1 |
| 相机前移 0.5m / FOV / 姿态朝向目标 | AirSim settings/tests 已覆盖 tuned terminal camera `X=0.5m`、`640x480`/`120deg` FOV；runtime 支持 `look_at_target` yaw 和 CV camera follow/look-at。 | D7 主线没有直接读取真实 camera intrinsics/extrinsics、畸变、姿态估计，也没有把 FOV 从 runtime 自动传入 `PngGuidanceConfig`。 | D7 当前保持轻量 bbox 几何；相机管理属于 main/runtime。 | P1/P2 |
| 末端视觉 PNG 与检测闭环 | AirSim detect metadata bbox 可进入 D7 gate；D5-shaped lock 通过后 runtime 可进入 `png_vm`；D7 已提供 bbox/LOS 离线 replay adapter；D7 delivery actor 默认外观和 main runtime actor asset default 均已对齐到无人机 mesh asset `Quadrotor1`。 | YOLO/ByteTrack 真实图像链路只作为离线 replay 或 optional 实验路径；若接入，也只产出 D5 local track 与 D7 bbox/LOS gate 摘要，不进入默认 SimpleFlight 控制；后续需要真实 AirSim 验证和阈值/检测调参。 | 默认不保存 PNG，不要求 Ultralytics/GPU/权重；先用 replay/calibration 稳定阈值。 | P1 optional |
| TTC 面积通道 | `png_ttc` API 和 delivery TTC 方案已文档化；D7 gate 可估计 bbox area expansion TTC。 | runtime 默认不是 `png_ttc`；TTC 对近距裁切/面积噪声的阈值需要更多 replay 和 D6 对照。 | 先用 `png_vm` 稳定 SimpleFlight 速度链路。 | P1/P2 |
| 机动能力 gate | PN 有加速度/转向率限幅；视觉 gate 估计 required turn rate、turn capacity、maneuver margin。 | 真实动力学、姿态/推力/延迟、PX4 饱和响应和三维高度通道未建模。 | SimpleFlight 高层速度接口不能代表底层飞控闭环。 | P2 |
| D6 指标输入 | D7/runtime 日志已有 mode、range、LOS、closing speed、gate reject reason、plan/D4/D5 metadata；正式 main bus metrics 已可合并真实执行结果；D7 已提供 comparison rows 和 replay summary。 | 多 seed N-pair 真实运行报告、阈值版本、分组对照和 raw contract vs execution metrics 双口径说明仍需 main/D6 汇总。 | 指标聚合属于 D6/main，不是 D7 本地测试即可完成。 | P1 |

## 未实现

| 项 | 当前状态 | 未实现原因 | 缺少条件 | 优先级 |
|---|---|---|---|---|
| 更真实机动约束 / 3D PN | D7 主线是二维水平 NED 抽象；高度由 runtime 速度/高度命令保持。 | 第一阶段重点是 PN/PNG gate、合同和日志；3D/动力学会扩大接口面。 | 3D state contract、姿态/推力/高度通道、平台响应和 D6 三维指标。 | P2 |
| FRPN / augmented PN / biased PN / true PN | 未实现。 | 高机动算法公式、目标加速度估计和场景尚未冻结。 | 高机动 fixture、目标加速度/机动模型、PN/FRPN/Pure Pursuit/PNG 多 seed 对照。 | P2 |
| MPC / NMPC | 未实现。 | 当前 PN/PNG 足够支撑第一阶段闭环；MPC 需要强约束模型和求解器。 | 平台动力学、约束、求解器依赖、实时预算、失败回退。 | P3 |
| 硬件飞控 / 实机控制 | 未实现。 | 本仓库是研究/仿真路径，不能把 D7 输出当实机控制指令。 | 实机安全流程、kill switch、围栏、台架标定、人工接管。 | P3 |
| PX4/MAVLink/body-rate 默认主线 | delivery 中有脚本和报告，main D7 主线未接入。 | Offboard、解锁、推力和坐标系风险高，不适合默认路径。 | PX4 SITL 版本、Offboard prime、推力/坐标/限幅标定、安全边界和回归基线。 | P2 |
| YOLO/ByteTrack 控制闭环 | delivery 有 detector 和报告，D7 已提供 bbox/LOS 离线 replay adapter，但主线不直接控制。 | 默认 runtime 使用 `simGetDetections` metadata，不保存 PNG，不管理模型权重/GPU。 | 图像帧流、YOLO 权重、class id、依赖版本、GPU/CPU 预算、MOT 稳定性、D5 local track 事件流和 main/D6 replay 数据。 | P1 先 replay |
| OpenCV/KCF/solvePnP/完整标定 | D7 主线未依赖。 | 当前只需 bbox 到 LOS 的轻量几何。 | 相机内外参、畸变、重投影误差、图像流、性能预算。 | P2 |
| ViSP / ROS2 tf2 / message_filters | 未实现。 | 当前项目不是 ROS2 graph 或视觉伺服栈。 | ROS2 runtime、frame tree、带戳消息 schema、bag/replay 基准。 | P3 |

## 缺少条件

1. **真实 AirSim 多 seed calibration**：D7 已提供本地 `D7RuntimeBus` adapter，main 已把 D7 runtime summary 接入 episode bus，并已通过 controlled 5v5 center replan 与 2v2 secondary visual PNG gate 回归。剩余需要按真实 AirSim 多 seed 运行固化 terminal range、`png_vm/png_ttc`、bbox/LOS/TTC gate、视觉延迟、机动裕度和阈值版本。
2. **D5 状态事件流**：`locked/ambiguous/hold/reacquire`、锁定丢失、重捕获、friend conflict、duplicate lock 和 timeout 需要持续进入 D7 pair state machine 与 D6 指标。
3. **视觉 replay 条件**：D7 已提供 bbox rows 到 bbox/LOS gate 的离线接口；YOLO/ByteTrack 或真实图像链路只作为 replay/optional，需要图像或 bbox replay 数据源、camera intrinsics/extrinsics、bbox timestamp、local track 连续性、measurement age、LOS-rate 噪声、丢检策略和 D5 local track 事件流。
4. **飞控/动力学条件**：PX4/MAVLink 或真实飞控升级前必须有 Offboard 状态机、推力/坐标/限幅标定、饱和日志、安全边界和回归 baseline。
5. **对照实验条件**：PN、Pure Pursuit、`png_vm`、`png_ttc`、FRPN/MPC 需要同批多 seed 场景、统一成功/失败判据、阈值版本和 D6 报告。

## 下一步优先级

| 优先级 | 下一步 | 验收口径 |
|---|---|---|
| P0 保持 | 保持 D7 不分配、不授权、不改写 `global_track_id`，并保持 D4/D5 gate 回归。 | D7 tests 通过；D4 reassign、D5 non-locked、ID/version mismatch、friend conflict 均拒绝视觉 PNG。 |
| P1 done/保持 | D7RuntimeBus、comparison、replay、D4 gate blocking、D3/D4/D5 terminal contract gate、owner/version gate、episode bus runtime summary、controlled 5v5 center replan 和 2v2 secondary visual PNG gate。 | D7 tests 通过；main CSV/summary 持续写出 `plan_id/plan_version/owner_node_id/track_version/d4_action/d5_decision_state/terminal_contract_reject_reason`；D4 replan/degrade 阶段不调用旧锁定视觉 PNG。 |
| P1 | 真实 AirSim 多 seed calibration。 | D6/main 报告按 seed/scenario 输出 `min_range_m`、`time_to_intercept_s`、terminal contract reject、terminal switch reject、visual PNG switch、threshold version 和 raw contract vs execution metrics 双口径。 |
| P1 optional | 将 D7 bbox/LOS replay adapter 接入 YOLO/ByteTrack 或 AirSim detect replay 数据。 | replay 生成 D5 local track 与 D7 bbox/LOS gate 摘要；`vehicle_control=False`、`simpleflight_control_called=False`，不进入默认 SimpleFlight 控制。 |
| P2 optional | 评估 FRPN/augmented PN、3D PN、PX4/MAVLink/body-rate 和 MPC/NMPC benchmark。 | 有高机动 fixture、目标加速度估计、平台动力学/安全边界、D6 对照指标和失败回退，且不破坏现有 PN/PNG API。 |
| P3 | 评估 MPC/NMPC、ViSP、ROS2。 | 仅在需要强约束控制或机器人中间件集成时进入，不作为当前 D7 主线阻塞项。 |

## 关键依据路径

- `research_modules/d7_proportional_guidance/d7_proportional_guidance/pn.py`
- `research_modules/d7_proportional_guidance/d7_proportional_guidance/simulator.py`
- `research_modules/d7_proportional_guidance/d7_proportional_guidance/terminal_gate.py`
- `research_modules/d7_proportional_guidance/d7_proportional_guidance/vision_png.py`
- `research_modules/d7_proportional_guidance/d7_proportional_guidance/runtime_bus.py`
- `research_modules/d7_proportional_guidance/d7_proportional_guidance/replay.py`
- `research_modules/d7_proportional_guidance/d7_proportional_guidance/comparison.py`
- `research_modules/d7_proportional_guidance/d7_proportional_guidance/airsim_dry_run.py`
- `research_modules/d7_proportional_guidance/tests/test_proportional_guidance.py`
- `research_modules/d7_proportional_guidance/tests/test_airsim_phase1_dry_run.py`
- `research_modules/d7_proportional_guidance/README.md`
- `research_modules/d7_proportional_guidance/PLAN.md`
- `research_modules/d7_proportional_guidance/png_guidance_delivery/README.md`
- `research_modules/airsim_runtime/intercept.py`
