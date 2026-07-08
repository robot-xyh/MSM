# D7 经典比例导引架构计划

## 目标

D7 提供一个可被主流程接入的离线二维比例导引研究模块。模块目标不是实现真实平台控制，而是给集成仿真提供清晰、可测试、可记录的“雷达中段 + 视觉末段”比例导引抽象：

- 中段使用 `radar_midcourse` 模式，输入来自全局航迹或雷达航迹估计。
- 末段使用 `vision_terminal` 模式，输入来自像素/LOS 观测估计。
- 视觉终端使用从 `png_guidance_delivery` 抽取的 SimpleFlight 兼容 PNG gate，先判断相机识别质量、LOS 质量、机动裕度和剩余窗口，再允许进入视觉 PNG/LOS 导引。
- 输出统一的 `GuidanceRecord`，便于后续闭环日志、指标统计和 GIF 可视化。

本模块只做离线二维质点运动、算法解释、日志评估和可视化准备；不提供真实飞控接口、硬件驱动、实时通信、火控参数、毁伤模型、自动处置或授权绕过逻辑。

## 当前代码与测试状态

当前 D7 主线已经落地的能力如下：

- **中段雷达 PN/PNG**：`pn.py` 的 `compute_proportional_navigation_command()` 使用二维位置和速度估计计算 `a_n = N * V_c * lambda_dot`，记录 LOS angle、LOS-rate、closing speed、range、限幅加速度和限幅转向率。`simulator.py` 和 `airsim_dry_run.py` 把上游 GlobalTrack/actor track 等价估计映射为 `GuidanceState(source="global_track" | "airsim_actor_track")`。
- **末端视觉 PNG**：`vision_png.py` 的 `SimpleFlightPngGuidanceFilter` 从 bbox 中心计算 bearing/LOS，维护 LOS-rate 窗口和 bbox 面积窗口，支持 `los`、`png_ttc`、`png_vm` 三种轻量末端输出，其中 runtime 默认走 `png_vm`。
- **每个 assignment pair 独立导引状态**：D7 filter 是实例状态，包含 `local_track_id`、稳定帧、LOS-rate history 和 TTC 面积窗口。`runtime_bus.py` 提供 D7-owned N-pair state injection adapter，按 `resource_id -> assigned_global_track_id` 维护独立 filter，并在 plan/version/owner/assignment signature 变化时重置该 pair 状态。单元测试覆盖 1/3/5/7 个 pair 和 `D7RuntimeBus` 任意 N-pair 注入，验证不同 pair 不共享视觉 filter 状态。
- **SimpleFlight 控制命令抽象**：D7 输出的是 `PngGuidanceCommand.velocity_ned`，适配 SimpleFlight 高层速度接口。真实 AirSim 控制调用位于 main/runtime 的 `intercept.py`，通过 `command_velocity_z()`/`moveByVelocityZAsync` 下发；D7 模块本身不直接调用 AirSim。
- **D3/D4/D5 gate**：`terminal_gate.py` 已实现 `AssignmentGuidanceBinding`、`D4GuidancePermission` 和 `evaluate_terminal_png_contract()`，校验授权、current/expiry、plan/version、D4 action、D5 `locked`、friend conflict、D5 `assigned_global_track_id`、D5 `assignment_version` 和观测 `assigned_global_track_id`。
- **D4 保守阻断**：`request_center_replan`、`degrade_to_secondary`、`degrade_to_distributed`、`reassign` 均映射为 `d4_reassign_pending`，`guidance_mode_from_terminal_contract()` 将其映射为 `abort_revoke`，视觉 PNG 不会被调用。D4 指明 `target_node_id/new_plan_owner_id` 时，D7 要求当前 D3 binding 携带同一 `owner_node_id`，否则拒绝为 `d4_owner_missing` 或 `d4_owner_mismatch`。
- **D4 软风险不过度阻断**：2026-07-07 D4 已将主动降级风险分成硬风险和软风险。`d3_assignment_cost_margin_low`、短时 D5 低置信度、无冲突 `ambiguous/reacquire` 若被 D4 输出为 `continue_center` 或观察类状态，D7 不再把它们当作 `d4_reassign_pending`；后续仍由 D5 locked、D3 current/version 和视觉 gate 决定是否进入 PNG。
- **D5 锁定一致性**：只有 `decision_state="locked"`、无 friend conflict、`assigned_global_track_id` 与当前 D3 binding 一致、`assignment_version == track_version` 时才允许视觉 PNG；D7 不因为本地检测结果更近或更清晰而重绑 `global_track_id`。
- **D3 重规划版本闭环**：当 D4 真的输出 `request_center_replan` 后，main/runtime 会再次调用 D3 产生新的中心 plan/binding/version。D7 只接受当前有效 binding/version；旧 plan、stale binding、revoked assignment 或 D4 `new_plan_id/new_plan_version` 与当前 binding 不一致时必须继续阻断。
- **PN/Pure Pursuit/PNG 对照接口**：`comparison.py` 提供 PN、Pure Pursuit、`png_vm`、`png_ttc` 多 seed report rows 和汇总字段，供 D6/main 后续统一报告；该接口不修改 PN/PNG 控制律本体。
- **bbox/LOS 离线 replay 接口**：`replay.py` 将 YOLO/ByteTrack、AirSim detect metadata 等 bbox replay 归一为 `VisionGuidanceObservation`，离线评估合同和 bbox/LOS/TTC gate，显式标记 `vehicle_control=False` 和 `simpleflight_control_called=False`。
- **执行指标回灌**：main/orchestrator 已把 D7 runtime summary 和真实 AirSim D7 控制执行结果接入 episode bus，并合并进正式 `main_episode_bus_metrics.json`；执行前合同诊断保留为 raw `main_episode_bus_contract_metrics.json`。D7 侧只保证输出可消费字段，不在本模块内计算最终 episode 指标。
- **AirSim P1 回归状态**：controlled 5v5 center replan 已验证 `request_center_replan -> new plan/binding/version -> D7 current binding gate`；2v2 secondary visual PNG gate 已验证 `degrade_to_secondary` 阶段阻断旧锁定，二级 plan/owner/version 生效且 D5 locked 后才允许 `png_vm`。
- **切换策略实际状态**：离线二维仿真的 `terminal_switch_range_m` 默认 `250.0m`；AirSim runtime 默认 `intercept_terminal_switch_range_m=8.0m`，可由 CLI 改动；测试中的 `30m` 级相对距离是视觉 gate 回归夹具，不是硬编码策略。bbox 稳定默认至少 2 帧，同时还要求面积、置信度、边缘、视觉延迟、LOS-rate 方差、TTC/闭合速度和机动裕度满足 gate。

当前“部分实现”的能力如下：

- AirSim SimpleFlight 真实控制已在 main/runtime 层接入 D7 API，并能输出 `control_commands.csv`、`intercept_summary.json`、D7 runtime summary 和 D6 可消费字段；正式 episode bus metrics 已可合并真实执行结果。剩余 P1 风险不在 D7 接口本体，而在真实 AirSim 多 seed calibration、阈值版本化和长期 D5 事件流稳定性。
- 相机 `X=0.5m` 前移、`640x480`/`120deg` FOV、`look_at_target` yaw 或 ComputerVision 相机朝向目标已在 AirSim runtime/settings/tests 中接入；D7 主线只消费 bbox 和固定 `focal_length_px` 近似，不直接管理真实相机外参、畸变或姿态估计。
- `png_guidance_delivery` 的 truth/gimbal/strapdown、PX4、MAVLink body-rate、YOLO/ByteTrack 代码作为复现实验资料随 D7 保存；主线只抽取 bbox-to-bearing、LOS-rate、TTC/VM 增益和 SimpleFlight 速度命令这一轻量核。

当前未实现且不应在文档中表述为已接入的能力：

- 更真实的机动约束、3D PN、目标加速度补偿、FRPN/augmented PN、MPC/NMPC。
- 硬件飞控、实机 PX4 Offboard、MAVLink body-rate/attitude 作为默认 main runtime 控制路径。
- YOLO/ByteTrack/真实视觉检测闭环直接控制 D7 主线；现阶段只允许作为 delivery 或 D7 离线 bbox/LOS replay adapter，不直接进入 SimpleFlight 控制。
- D7 本地分配、授权、重分配或 `global_track_id` 改写。

## PNG guidance delivery 学习与融合

已验证的 `png_guidance_delivery` 包含 truth、gimbal、strapdown 三类 AirSim PNG 验证路径。D7 主线只吸收其中对当前 SimpleFlight Blocks 仿真直接有用的算法核：

- bbox 中心到相机 LOS/bearing 的几何转换。
- LOS-rate 滑窗质量评估和方差门限。
- bbox 面积扩张估计 TTC。
- `LAW=TTC` 的 TTC 增益调度和 `LAW=VM` 的固定 `N * V_m` 思路。
- bbox 太小、贴边、检测不连续、视觉延迟高、机动裕度不足时拒绝切换。

两类 delivery 方案在系统中的融合口径如下：

- **位置比例导引 / truth PNG**：delivery 的 `truth` 路径使用目标真实相对位置和速度验证 PNG 上限。D7 主线不调用 delivery 的 truth 脚本，而是用 `compute_proportional_navigation_command()` 和 AirSim actor/global-track 等价估计实现同一类位置 PN/PNG 几何。实际代码路径是 `d7_proportional_guidance/pn.py`、`simulator.py`、`airsim_dry_run.py`，以及 main/runtime 的 `intercept.py` 中段控制。
- **TTC 捷联比例导引 / strapdown PNG**：delivery 的 `strapdown` 路径把固定相机 bbox 转成 LOS/LOS-rate，并用 bbox 面积扩张估计 TTC。D7 主线不接入它的完整相机姿态、KF、YOLO、body-rate 或 PX4 控制，而是在 `vision_png.py` 中保留轻量 TTC/VM gate：`PngGuidanceConfig(law="png_ttc")` 使用 TTC 增益，`law="png_vm"` 使用固定 `N * V_m` 思路。实际 AirSim controlled intercept 默认 `png_vm`，`png_ttc` 目前主要是 D7 API/复现实验可用能力。
- **文档化状态**：delivery 仍是方案、报告和复现实验包；D7 README/PLAN/GAP 只把其中已抽取到 `vision_png.py` 或 runtime 实际调用的内容列为主线实现。

命名口径：

- 当前 main/runtime 默认目标 actor 和 AirSim detect filter 为 `MSM_TargetActor_*`，实际对象名通常类似 `MSM_TargetActor_1`。
- 当前 runtime 默认目标 asset 为 `1M_Cube_Chamfer`。
- `png_guidance_delivery` 内历史默认仍为 `Intruder*` mesh filter 和 `IntruderActor` actor name；它们只作为 delivery 复现实验与旧日志的 legacy alias。

暂不接入：

- PX4 Offboard、MAVLink、body-rate、attitude 控制。
- YOLO/TensorRT 推理链路。
- 自动 arm/offboard 或任何真实平台控制流程。

主线新增 `SimpleFlightPngGuidanceFilter`，它输出 SimpleFlight 速度命令和 gate 质量字段，不直接调用 AirSim API。

## D3/D4/D5 切换合同

D7 的末端视觉 PNG 入口必须按以下顺序保守判定：

1. D3 binding 必须存在、授权有效、assignment current，且 plan/version/track_version 未过期。
2. D4 action 必须允许末端继续。`continue`、`continue_center`、`request_secondary_assist` 可进入后续检查；`request_center_replan`、`degrade_to_secondary`、`degrade_to_distributed`、`reassign` 均表示当前绑定正在重分配或降级，D7 必须记录 `d4_reassign_pending` 并阻断视觉 PNG。
3. 若 D4 提供 `new_plan_id/new_plan_version`，必须与当前 D3 binding 一致，否则拒绝为 `d4_plan_mismatch`。若 D4 提供 `target_node_id`、`new_plan_owner_id`、`new_owner_node_id`、`plan_owner_id` 或 `owner_node_id`，当前 D3 binding 必须携带同一 `owner_node_id`，否则拒绝为 `d4_owner_missing` 或 `d4_owner_mismatch`。D4 对低 cost margin、短时低置信度或无冲突 reacquire 的观察类 `continue_center` 不自动阻断；它只表示还没有进入重规划/降级窗口。
4. D5 terminal association 必须 `decision_state="locked"` 且无 friend conflict；`ambiguous`、`hold`、`reacquire` 只能让 D7 保持 `handover_pending`、`hold` 或 `reacquire` 日志状态，不能本地换目标。
5. D5 的 `assigned_global_track_id` 必须与 D3 binding 的 `assigned_global_track_id` 一致，D5 的 `assignment_version` 必须等于 D3 binding 的 `track_version`；观测 bbox 上携带的 `assigned_global_track_id` 若不一致也必须拒绝。
6. 只有 contract 通过后，D7 才评估该 pair 自己的 `SimpleFlightPngGuidanceFilter`；若 bbox/LOS/TTC/机动 gate 不通过，记录 `terminal_switch_reject_reason` 并保持中段/等待状态。

D7 不分配目标、不授权、不创建或改写 `global_track_id`，也不把本地 `local_track_id` 升级为全局身份。

## 工程问题

### 雷达比例导引中段

中段通常拥有较稳定的全局航迹估计，适合用目标位置和速度估计计算 LOS 几何量。D7 中的 `radar_midcourse` 模式把 `GlobalTrack`/雷达航迹抽象为 `GuidanceState`：

- `position_m`：二维位置估计，单位米。
- `velocity_mps`：二维速度估计，单位米每秒。
- `source="global_track"`：标记估计来源。
- 可配置位置/速度高斯噪声，用于离线鲁棒性实验。

工程重点：

- 与上游 D1/D2/D3 的航迹/分配结果保持弱耦合，只依赖二维状态字段。
- 记录 LOS angle、LOS rate、closing speed 和 range，便于 D6 指标模块消费。
- 不输出真实控制信号，只输出抽象横向加速度和转向率建议。

### 视觉比例导引末段

末段假设全局航迹切换为更高频的像素/LOS 观测。D7 中的 `vision_terminal` 模式使用离线几何生成 LOS 观测：

- `los_angle_rad`：二维视线角。
- `pixel_x`：由焦距和相对方位投影得到的抽象像素横坐标。
- `range_estimate_m`：用于离线闭环的合成距离估计。
- `relative_velocity_source`：记录速度估计来自有限差分还是初始化。

工程重点：

- 模式切换由距离阈值或时间阈值触发，进入末段后锁定 `vision_terminal`。
- 视觉观测只用于离线估计，不绑定真实相机、云台或实时图像流。
- 支持 LOS 噪声和距离噪声，便于评估末段记录质量。

## 数学模型

二维相对状态定义为：

```text
r = target_position - pursuer_position
v = target_velocity - pursuer_velocity
R = ||r||
lambda = atan2(r_y, r_x)
lambda_dot = cross2(r, v) / R^2
V_c = -dot(r, v) / R
```

经典比例导引横向加速度为：

```text
a_n = N * V_c * lambda_dot
```

其中：

- `N` 为 navigation constant。
- `V_c` 为 closing speed，接近时为正。
- `lambda_dot` 为 LOS rate。
- `a_n` 的符号表示相对当前速度方向的左/右横向修正。

D7 在输出前施加两级限制：

```text
a_limited = clip(a_n, -max_lateral_accel, max_lateral_accel)
omega = a_limited / pursuer_speed
omega_limited = clip(omega, -max_turn_rate, max_turn_rate)
heading_next = heading + omega_limited * dt
```

仿真更新采用二维恒速质点模型：追踪点只改变航向，目标保持给定速度匀速运动。该模型用于算法研究和日志生成，不代表真实动力学或控制律。

## 接口

### 数据模型

- `GuidanceMode`：`radar_midcourse`、`handover_pending`、`vision_terminal`、`hold`、`reacquire`、`abort_revoke`。
- `GuidanceState`：二维位置、速度、时间戳、来源和可选元数据。
- `GuidanceConfig`：步长、导引律选择 `guidance_law`、PN 系数、加速度限制、转向率限制、末段切换阈值、噪声参数。当前 `guidance_law` 支持 `pn` 和 `pure_pursuit`。
- `GuidanceCommand`：单步 PN 输出，包含 LOS、closing speed、原始/限幅加速度、原始/限幅转向率、期望航向。
- `GuidanceRecord`：离线 episode 的逐步记录，包含 truth、estimate、observation 和 PN 字段。
- `PngGuidanceConfig`：视觉 PNG gate 参数，包括 bbox、LOS、TTC、机动裕度和导引律。
- `VisionGuidanceObservation`：D5/AirSim detect 提供的 bbox、置信度、local/global ID 和时间戳。
- `VisionGuidanceQuality`：相机质量、LOS 质量、机动裕度和切换拒绝原因。
- `PngGuidanceCommand`：SimpleFlight 速度命令、导引律、饱和状态和 gate 质量。
- `D7RuntimeBus` / `D7RuntimePairInput` / `D7RuntimePairOutput`：D7-owned N-pair runtime state injection 和日志字段输出。该 adapter 不创建 assignment、不调用控制 API，只维护每个 pair 的视觉 filter 状态。
- `GuidanceStrategyComparisonRow`：PN/Pure Pursuit/`png_vm`/`png_ttc` 对照报告行，包含 D6 可消费的距离、切换、合同拒绝和视觉 gate 拒绝字段。

### 核心函数

- `compute_proportional_navigation_command(...)`
  - 输入：pursuer state、target estimate、`dt_s`、`navigation_constant`、mode 和限制参数。
  - 输出：`GuidanceCommand`。

- `compute_pure_pursuit_command(...)`
  - 输入：pursuer state、target estimate、`dt_s`、mode 和转向率限制参数。
  - 输出：`GuidanceCommand`。
  - 用途：作为 Pure Pursuit baseline 与 PN 对照；当前为本地轻量实现，不引入 PythonRobotics 依赖。

- `simulate_guidance_episode(...)`
  - 输入：初始 pursuer/target 状态、`GuidanceConfig`、resource/target 标识。
  - 过程：按 `guidance_law` 选择 PN 或 Pure Pursuit；`radar_midcourse` 中段闭环，满足阈值后切换到 `vision_terminal`。
  - 输出：`list[GuidanceRecord]` 和 `summary` 字典。

- `summarize_guidance_records(...)`
  - 输入：records。
  - 输出：初始距离、末距离、最小距离、最近时刻、模式序列、是否进入末段等摘要。

- `SimpleFlightPngGuidanceFilter.evaluate(...)`
  - 输入：`VisionGuidanceObservation`、当前航向/速度、相对位置/速度、SimpleFlight 速度上限。
  - 过程：验证 D5 视觉目标的 bbox 质量、LOS-rate、TTC、闭合速度和机动裕度。
  - 输出：`PngGuidanceCommand`。若 gate 未通过，`terminal_switch_allowed=False`，调用方保持 `handover_pending` 或回退中段 PN。

- `terminal_switch_allowed_rate(...)` / `summarize_terminal_switch_quality(...)`
  - 输入：D7 已生成的 `PngGuidanceCommand`、`VisionGuidanceQuality` 或持久化 metadata 字典。
  - 输出：`terminal_switch_allowed_rate`、样本数、允许数、拒绝数和拒绝原因计数。
  - 边界：只统计已有 gate 输出，不重新实现 D6 指标聚合或 runtime gate 判定。

- `guidance_mode_from_terminal_contract(...)`
  - 输入：D3/D4/D5 terminal PNG contract 判定、handover pending 和 terminal locked 状态。
  - 输出：显式 D7 日志状态。D5 未锁定、版本/身份不一致映射为 `reacquire`；友方冲突、D4 hold 或授权缺失映射为 `hold`；assignment revoked/expired/reassign pending 映射为 `abort_revoke`。

- `D7RuntimeBus.inject_state(...)`
  - 输入：任意长度 assignment pair 状态样本，每个样本包含 D3 binding、D4 permission、D5 terminal association、bbox observation 和当前运动上下文。
  - 输出：每个 pair 的合同/gate/导引日志字段；每个 `resource_id -> assigned_global_track_id` 独立 filter，plan/version/owner/assignment 变化时重置。

- `evaluate_bbox_los_replay(...)`
  - 输入：YOLO/ByteTrack、AirSim detect metadata 或其他 bbox replay rows，以及 D3/D4/D5 合同字段。
  - 输出：`D7RuntimePairOutput` 序列和 replay summary；只做离线 gate 分析，不控制 SimpleFlight。

- `run_guidance_strategy_comparison(...)`
  - 输入：seed 列表和策略列表。
  - 输出：PN、Pure Pursuit、`png_vm`、`png_ttc` report rows；用于 D6/main 后续统一统计。

## 交付物

- `PLAN.md`：中文工程计划、数学模型、接口说明和边界。
- `README.md`：中文模块说明、运行命令、示例代码。
- `d7_proportional_guidance/models.py`：dataclass 和模式枚举。
- `d7_proportional_guidance/pn.py`：经典二维 PN 计算函数和 Pure Pursuit baseline。
- `d7_proportional_guidance/simulator.py`：单 resource-target pair 离线闭环仿真。
- `d7_proportional_guidance/vision_png.py`：从 delivery 包抽取的 SimpleFlight 兼容视觉 PNG gate。
- `d7_proportional_guidance/runtime_bus.py`：D7-owned N-pair state injection、每 pair filter registry 和日志汇总。
- `d7_proportional_guidance/replay.py`：YOLO/ByteTrack/AirSim bbox replay 到 D7 bbox/LOS gate 的离线 adapter。
- `d7_proportional_guidance/comparison.py`：PN/Pure Pursuit/`png_vm`/`png_ttc` 多 seed 对照 report rows。
- `d7_proportional_guidance/__init__.py`：核心 API 导出。
- `tests/`：pytest 覆盖距离收敛、PN/Pure Pursuit 模式切换、限幅、terminal contract 状态映射、N-pair runtime bus、D4 owner/version gate、bbox/LOS replay、comparison report rows 和记录字段。

## 后续集成建议

主智能体后续可在不改变 D7 内部边界的前提下，把上游分配结果映射为 `GuidanceState`，把 `GuidanceRecord.as_dict()` 写入统一 episode log，并在 GIF 中绘制 pursuer、target、LOS 线、模式颜色和距离曲线。

AirSim runtime 集成要求：

- 当前阶段只使用 SimpleFlight `moveByVelocityZAsync`。
- main runtime 用 `--drone-count N` 决定本次仿真的无人机/目标数量；D7 不读取固定数量，也不假设 2v2/5v5。
- main 必须为每个有效 D3 assignment pair 创建独立 D7 控制上下文，分别运行初段位置 PNG/PN 和末端视觉 PNG gate/filter，不能在多个 pair 之间共享 `SimpleFlightPngGuidanceFilter` 的 LOS/TTC/稳定帧状态。
- 当前 runtime 目标 actor/detection filter 使用 `MSM_TargetActor_*`，目标 asset 使用 `1M_Cube_Chamfer`。
- `Intruder*`/`IntruderActor` 只作为 `png_guidance_delivery` 和历史日志的 legacy alias，不应作为新 runtime handoff 的默认目标名。
- 目标检测输入来自 AirSim `simGetDetections` 的 bbox，不依赖默认保存 PNG。
- 进入视觉终端前必须同时满足 D5 locked/版本一致、bbox 质量、LOS 质量、机动裕度和窗口门槛。
- 若 gate 失败，记录 `terminal_switch_reject_reason`，并保持 `handover_pending` 或回退 `radar_midcourse`。

P1 当前状态：

- D7-owned `runtime_bus.py`、`comparison.py`、`replay.py` 已补齐。N-pair runtime bus、PN/Pure Pursuit/`png_vm`/`png_ttc` 多 seed report rows、bbox/LOS replay、D4 gate blocking、D3/D4/D5 terminal contract gate、owner/version gate 均有 D7 测试覆盖。
- main runtime 已把 D7 runtime summary 接入 episode bus。controlled 5v5 center replan 与 2v2 secondary visual PNG gate 回归已通过，D7 文档不再把这些列为待补能力。
- D4 `request_center_replan`、`degrade_to_secondary`、`degrade_to_distributed`、`reassign` 仍是保守阻断项；只有 D5 `locked`、D3 version/owner 一致且 D4 action 允许后，才尝试该 pair 的视觉 PNG。

P1 剩余：

- 用真实 AirSim 多 seed 运行校准 `png_vm`、`png_ttc`、bbox/LOS/TTC gate 阈值、terminal range、视觉延迟和机动裕度，形成阈值版本、seed 分组和 D6/main 汇总口径。
- 将 D7 comparison rows 和 replay summary 对接到真实 AirSim 多 seed 报告数据源；D7 侧只保证字段稳定，正式报告仍由 main/D6 聚合。
- YOLO/ByteTrack 真实图像链路只作为离线 replay 或 optional 实验路径：生成 D5 local track 与 D7 bbox/LOS gate 摘要，不进入默认 SimpleFlight controlled intercept。

P2 下一步：

- FRPN/augmented PN/目标加速度补偿、3D PN、真实相机标定、相机外参/畸变、PX4/MAVLink/body-rate、MPC/NMPC 都保持 optional benchmark；必须先有高机动 fixture、平台动力学/安全边界、D6 对照指标和失败回退，不能进入默认 SimpleFlight 控制主线。
