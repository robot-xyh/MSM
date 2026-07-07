# D7 比例导引与末端视觉 PNG 实现差距审计

**审计范围**：`research_modules/d7_proportional_guidance/` 的 README、PLAN、代码和测试，`png_guidance_delivery/` 方案资料，以及 D7 在 `research_modules/airsim_runtime/intercept.py` 中被消费的实际状态。
**修改边界**：本次只更新 D7 文档和 `subagent_reviews/D7_*`，不修改 D1-D6、main runtime、root report 或代码。
**系统边界**：D7 只做导引律、导引状态、末端 PNG gate 和日志合同；D7 不分配目标、不授权、不创建、不改写、不本地重绑 `global_track_id`。

## 总体结论

D7 当前已经实现可测试的二维位置 PN/PNG 几何核、中段雷达/全局航迹 PN、离线 `radar_midcourse -> vision_terminal` 质点仿真、AirSim phase-1 dry-run 记录适配、末端视觉 `png_vm/png_ttc` 轻量 gate、每个 assignment pair 独立视觉导引状态、D3/D4/D5 terminal contract、显式 `handover_pending/hold/reacquire/abort_revoke` 日志状态，以及 SimpleFlight 速度命令抽象。

真实 AirSim SimpleFlight 控制不在 D7 模块内直接执行，而是 main/runtime 的 `intercept.py` 消费 D7 API：每个 `InterceptPair` 持有自己的 `AssignmentGuidanceBinding`、`D4GuidancePermission`、D5-shaped terminal association 和 `SimpleFlightPngGuidanceFilter`，将 `PngGuidanceCommand.velocity_ned` 交给 `command_velocity_z()`/`moveByVelocityZAsync`。因此 D7 文档必须把“D7 实现了可消费的导引/gate/命令抽象”和“main runtime 实际下发 SimpleFlight 命令”分开描述。

`png_guidance_delivery` 已纳入 D7 目录作为方案和复现实验包。主线实际使用的只有轻量子集：bbox-to-bearing、LOS-rate 窗口、bbox 面积 TTC、`png_vm/png_ttc` 增益思想、质量 gate 和 SimpleFlight 速度命令。delivery 中的 truth/gimbal/strapdown、PX4/MAVLink/body-rate、YOLO/ByteTrack、KF/外推和报告仍是参考或独立实验路径，不能写成 main D7 默认路径。

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
| D5 locked 与 ID/version 一致才切换 | 已实现 | `evaluate_terminal_png_contract()`; D7 tests | 只有 `decision_state=="locked"`、无 friend conflict、`assigned_global_track_id` 与 binding 一致、`assignment_version == track_version` 时才允许后续视觉 gate。 |
| 30m/稳定 bbox 等切换策略 | 已实现为可配置 gate，不是硬编码 | `PngGuidanceConfig`; D7 tests; `BlocksSmokeConfig` | D7 离线默认 terminal range `250m`，AirSim runtime 默认 `8m`；测试中 `30m` 左右相对距离用于验证 gate。bbox 稳定默认 `min_stable_frames=2`，还需面积、置信度、边缘、延迟、LOS 方差、闭合速度和机动裕度通过。 |
| AirSim active center/secondary 合同回归 | 已有 runtime 测试消费 D7 字段 | `airsim_runtime/tests/test_blocks_runtime.py` | runtime CSV/summary 包含 `d4_action`、`d5_decision_state`、`terminal_contract_reject_reason`、`terminal_switch_reject_reason`、`guidance_law`。 |
| Pure Pursuit baseline | 已实现轻量版 | `compute_pure_pursuit_command()`; tests | 仅用于离线对照，不引入 PythonRobotics。 |

## 部分实现

| 项 | 当前做到什么 | 还缺什么 | 原因 | 优先级 |
|---|---|---|---|---|
| AirSim SimpleFlight 真实控制 | main/runtime 已用 D7 PN/PNG gate 生成速度命令，并通过 SimpleFlight 高层速度接口执行；输出 `control_commands.csv`、`intercept_summary.json`。 | 真实 D3/D4/D5 runtime bus 持续驱动 N-pair state machine；当前部分 terminal association/active degradation 是 frame metadata 或模拟证据。 | D7 不能生成 assignment、D4 仲裁或 D5 lock；main 需要统一状态总线和日志。 | P1 |
| 相机前移 0.5m / FOV / 姿态朝向目标 | AirSim settings/tests 已覆盖 tuned terminal camera `X=0.5m`、`640x480`/`120deg` FOV；runtime 支持 `look_at_target` yaw 和 CV camera follow/look-at。 | D7 主线没有直接读取真实 camera intrinsics/extrinsics、畸变、姿态估计，也没有把 FOV 从 runtime 自动传入 `PngGuidanceConfig`。 | D7 当前保持轻量 bbox 几何；相机管理属于 main/runtime。 | P1/P2 |
| 末端视觉 PNG 与检测闭环 | AirSim detect metadata bbox 可进入 D7 gate；D5-shaped lock 通过后 runtime 可进入 `png_vm`。 | 真实 YOLO/ByteTrack 图像闭环、连续 local track、measurement age、丢检重捕获和离线 replay adapter 尚未接主线。 | 默认不保存 PNG，不要求 Ultralytics/GPU/权重；先保证合同和日志稳定。 | P1 |
| TTC 面积通道 | `png_ttc` API 和 delivery TTC 方案已文档化；D7 gate 可估计 bbox area expansion TTC。 | runtime 默认不是 `png_ttc`；TTC 对近距裁切/面积噪声的阈值需要更多 replay 和 D6 对照。 | 先用 `png_vm` 稳定 SimpleFlight 速度链路。 | P1/P2 |
| 机动能力 gate | PN 有加速度/转向率限幅；视觉 gate 估计 required turn rate、turn capacity、maneuver margin。 | 真实动力学、姿态/推力/延迟、PX4 饱和响应和三维高度通道未建模。 | SimpleFlight 高层速度接口不能代表底层飞控闭环。 | P2 |
| D6 指标输入 | D7/runtime 日志已有 mode、range、LOS、closing speed、gate reject reason、plan/D4/D5 metadata。 | 多 seed N-pair 真实运行报告、阈值版本和分组对照仍需 main/D6 汇总。 | 指标聚合属于 D6/main，不是 D7 本地测试即可完成。 | P1 |

## 未实现

| 项 | 当前状态 | 未实现原因 | 缺少条件 | 优先级 |
|---|---|---|---|---|
| 更真实机动约束 / 3D PN | D7 主线是二维水平 NED 抽象；高度由 runtime 速度/高度命令保持。 | 第一阶段重点是 PN/PNG gate、合同和日志；3D/动力学会扩大接口面。 | 3D state contract、姿态/推力/高度通道、平台响应和 D6 三维指标。 | P2 |
| FRPN / augmented PN / biased PN / true PN | 未实现。 | 高机动算法公式、目标加速度估计和场景尚未冻结。 | 高机动 fixture、目标加速度/机动模型、PN/FRPN/Pure Pursuit/PNG 多 seed 对照。 | P2 |
| MPC / NMPC | 未实现。 | 当前 PN/PNG 足够支撑第一阶段闭环；MPC 需要强约束模型和求解器。 | 平台动力学、约束、求解器依赖、实时预算、失败回退。 | P3 |
| 硬件飞控 / 实机控制 | 未实现。 | 本仓库是研究/仿真路径，不能把 D7 输出当实机控制指令。 | 实机安全流程、kill switch、围栏、台架标定、人工接管。 | P3 |
| PX4/MAVLink/body-rate 默认主线 | delivery 中有脚本和报告，main D7 主线未接入。 | Offboard、解锁、推力和坐标系风险高，不适合默认路径。 | PX4 SITL 版本、Offboard prime、推力/坐标/限幅标定、安全边界和回归基线。 | P2 |
| YOLO/ByteTrack 控制闭环 | delivery 有 detector 和报告，D7 主线未接入。 | 默认 runtime 使用 `simGetDetections` metadata，不保存 PNG，不管理模型权重/GPU。 | 图像帧流、YOLO 权重、class id、依赖版本、GPU/CPU 预算、MOT 稳定性和离线 replay。 | P1 先 replay |
| OpenCV/KCF/solvePnP/完整标定 | D7 主线未依赖。 | 当前只需 bbox 到 LOS 的轻量几何。 | 相机内外参、畸变、重投影误差、图像流、性能预算。 | P2 |
| ViSP / ROS2 tf2 / message_filters | 未实现。 | 当前项目不是 ROS2 graph 或视觉伺服栈。 | ROS2 runtime、frame tree、带戳消息 schema、bag/replay 基准。 | P3 |

## 缺少条件

1. **真实 N-pair runtime bus**：main 需要按 `--drone-count N` 枚举有效 D3 assignment pair，为每个 pair 提供 `AssignmentGuidanceBinding`、D4 action、D5 `TerminalAssociation`、目标估计、资源状态和独立 D7 filter。
2. **D5 状态事件流**：`locked/ambiguous/hold/reacquire`、锁定丢失、重捕获、friend conflict、duplicate lock 和 timeout 需要持续进入 D7 pair state machine 与 D6 指标。
3. **视觉 replay 条件**：图像或 bbox replay、camera intrinsics/extrinsics、bbox timestamp、local track 连续性、measurement age、LOS-rate 滤波和丢检策略。
4. **飞控/动力学条件**：PX4/MAVLink 或真实飞控升级前必须有 Offboard 状态机、推力/坐标/限幅标定、饱和日志、安全边界和回归 baseline。
5. **对照实验条件**：PN、Pure Pursuit、`png_vm`、`png_ttc`、FRPN/MPC 需要同批多 seed 场景、统一成功/失败判据、阈值版本和 D6 报告。

## 下一步优先级

| 优先级 | 下一步 | 验收口径 |
|---|---|---|
| P0 保持 | 保持 D7 不分配、不授权、不改写 `global_track_id`，并保持 D4/D5 gate 回归。 | D7 tests 通过；D4 reassign、D5 non-locked、ID/version mismatch、friend conflict 均拒绝视觉 PNG。 |
| P1 | main 接入真实 D3/D4/D5 bus 到 N-pair D7 控制上下文。 | 每个 pair 独立 filter；CSV/summary 持续写出 `plan_id/plan_version/track_version/d4_action/d5_decision_state/terminal_contract_reject_reason`。 |
| P1 | 做 PN vs Pure Pursuit vs `png_vm`/`png_ttc` 多 seed 对照。 | D6 输出 `min_range_m`、`time_to_intercept_s`、mode switch、terminal contract reject、terminal switch reject 和 visual PNG switch 分组报告。 |
| P1 | YOLO/ByteTrack 先做离线 replay adapter。 | replay 生成 D5 local track 与 D7 bbox/LOS gate 摘要；失败可回退 AirSim detect metadata，不直接控制 SimpleFlight。 |
| P1 | 固化 D4 主动降级阻断。 | `request_center_replan`、`degrade_to_secondary`、`degrade_to_distributed` 期间 `guidance_law` 保持 `radar_pn`/保守状态，只有新 plan 生效且 D5 locked 一致后才允许 `png_vm`。 |
| P2 | 评估 FRPN/augmented PN 和三维机动约束。 | 有高机动 fixture、目标加速度估计、D6 对照指标，且不破坏现有 PN API。 |
| P2 | 保留 PX4/MAVLink/body-rate 为独立实验路径。 | 独立脚本和报告验证 PX4 SITL、Offboard prime、推力/坐标标定和安全流程，不默认并入 main runtime。 |
| P3 | 评估 MPC/NMPC、ViSP、ROS2。 | 仅在需要强约束控制或机器人中间件集成时进入，不作为当前 D7 主线阻塞项。 |

## 关键依据路径

- `research_modules/d7_proportional_guidance/d7_proportional_guidance/pn.py`
- `research_modules/d7_proportional_guidance/d7_proportional_guidance/simulator.py`
- `research_modules/d7_proportional_guidance/d7_proportional_guidance/terminal_gate.py`
- `research_modules/d7_proportional_guidance/d7_proportional_guidance/vision_png.py`
- `research_modules/d7_proportional_guidance/d7_proportional_guidance/airsim_dry_run.py`
- `research_modules/d7_proportional_guidance/tests/test_proportional_guidance.py`
- `research_modules/d7_proportional_guidance/tests/test_airsim_phase1_dry_run.py`
- `research_modules/d7_proportional_guidance/README.md`
- `research_modules/d7_proportional_guidance/PLAN.md`
- `research_modules/d7_proportional_guidance/png_guidance_delivery/README.md`
- `research_modules/airsim_runtime/intercept.py`
