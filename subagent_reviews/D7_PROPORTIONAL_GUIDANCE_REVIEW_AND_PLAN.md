# D7 比例导引架构评审与补充方案

**定位**: D7 负责中段雷达/全局航迹比例导引和末端视觉/LOS 导引的算法、状态切换、控制命令抽象与日志记录。  
**边界**: 本文只面向当前 D7 本地研究/合同模块、D7-owned runtime bus 和 AirSim Blocks 仿真闭环，不包含真实平台火控参数、毁伤模型、硬件驱动、自动处置或绕过人工授权的流程。

---

## 0. 当前状态修订

截至当前代码和测试，D7 已经从“离线 PN 研究模块”扩展为可被 main/runtime 消费的导引合同模块，但它仍不拥有 AirSim 启停、episode 编排或真实车辆控制。

已实现：

- 中段雷达/全局航迹 PN：`compute_proportional_navigation_command()` 使用二维位置/速度估计计算 `N * V_c * lambda_dot`，支持限幅和日志字段。
- 末端视觉 PNG：`SimpleFlightPngGuidanceFilter` 使用 bbox center、LOS-rate、bbox 面积 TTC、闭合速度和机动裕度输出 `png_vm/png_ttc/los` 速度命令；runtime 默认 `png_vm`。
- 每个 assignment pair 独立状态：runtime 的 `InterceptPair.visual_filter` 和 D7 filter 实例分别保存稳定帧、LOS-rate 窗口、TTC 面积窗口和 local track 状态；D7 测试覆盖 1/3/5/7 pair。
- D3/D4/D5 gate：D7 校验 assignment 授权/current、plan/version、D4 action、D5 `locked`、friend conflict、D5 `assigned_global_track_id`、D5 `assignment_version` 和观测 global ID。
- D4 保守阻断：`request_center_replan`、`degrade_to_secondary`、`degrade_to_distributed` 均必须拒绝视觉 PNG，记录 `d4_reassign_pending`。
- SimpleFlight 命令：D7 输出 `velocity_ned`，main/runtime 负责 `moveByVelocityZAsync`；D7 本模块不直接连接 AirSim。
- episode bus 指标回灌：2026-07-07 main/runtime 已把真实 D7 执行产物合并进正式 `main_episode_bus_metrics.json`，raw `main_episode_bus_contract_metrics.json` 只保留执行前合同诊断；2026-07-08 复核确认 D7 runtime summary 已接入 episode bus。
- D3 replan 闭环：`request_center_replan` 后 main/runtime 生成新的 D3 plan/binding/version，D7 只接受当前有效 binding/version，旧 plan 或 mismatch 继续阻断视觉 PNG；controlled 5v5 center replan 回归已通过。
- 2v2 secondary gate 回归：`degrade_to_secondary` 阶段阻断旧 D5 lock，二级 plan/owner/version 生效且 D5 locked 后才允许 `png_vm`/`vision_terminal`。
- D4 软风险口径：低 cost margin、短时 D5 低置信度、无冲突 `ambiguous/reacquire` 若由 D4 输出为 `continue_center`/观察状态，D7 不再误记为 `d4_reassign_pending`；它仍必须等待 D5 `locked` 和视觉 gate 通过。
- D7-owned runtime bus adapter：`D7RuntimeBus` 支持任意 N-pair D3/D4/D5 state injection，每个 pair 独立视觉 filter，plan/version/owner/assignment signature 变化时重置该 pair 状态。
- Runtime bus 可消费 summary：`D7RuntimePairOutput.as_log_record()` 已输出 terminal handoff、D4/D5 state aliases、D3 plan/version、bbox、camera/LOS/maneuver gate、TTC、LOS-rate、closing speed 和 maneuver margin；`summarize_runtime_bus_outputs()` 已聚合 guidance mode、handoff 状态、D4/D5/plan 计数、gate pass rate、bbox/TTC/LOS 数值摘要和 reject reason 分布，供 main episode bus 与 D6 报告消费。
- D4 owner/version gate：D4 指定 `target_node_id/new_plan_owner_id` 时，当前 D3 binding 必须携带同一 `owner_node_id`，否则 D7 拒绝为 `d4_owner_missing` 或 `d4_owner_mismatch`。
- P1 对照与 replay 接口：`comparison.py` 输出 PN/Pure Pursuit/`png_vm`/`png_ttc` 多 seed report rows；`replay.py` 将 YOLO/ByteTrack/AirSim bbox rows 离线映射到 bbox/LOS/TTC gate，显式不调用 SimpleFlight。
- P1 calibration summary 接口：`calibration.py` 的 `summarize_guidance_calibration()` 消费多 seed D7 runtime outputs、`GuidanceRecord`、comparison rows 或 replay dict，按 PN、Pure Pursuit、`png_vm`、`png_ttc` 汇总 terminal range、closing speed、bbox/LOS/maneuver gate 和 reject reasons，并输出 threshold advisory。该接口只产出报告建议，显式不修改默认控制律、不绕过 D3/D4/D5 gate。
- main/D6 P1 calibration sweep 对接：main runtime 已新增 P1 D4/D5 calibration sweep，支持 secondary height/FOV/count/standoff 与多 seed 组合；sweep 完成后 D6 自动生成标准报告 bundle。D7 不拥有 sweep 或报告写盘，只保证 D7 runtime summary、comparison rows、bbox/LOS replay summary 和 threshold advisory 字段可被 main/D6 消费。
- D4/D5 机动高空侦察 stress 结论：2026-07-08 main 侧 5v5 D4/D5 stress 覆盖 3 seeds、200m 高差、`mobile_recon_gimbal`、80deg FOV、1920x1080；D4 action 正确，D5 能识别 mobile recon，gimbal OK rate 为 1.0，但二级网络同帧全覆盖仍为 0.0，降级 case cross-view 为 0，`not_registered` 约 65。D7 不能把“看得更清楚”视为视觉 PNG 放行条件，仍必须坚持 D3 当前 version/owner、D4 action 允许、D5 `locked` 且 `assigned_global_track_id` 一致、bbox/LOS/闭合速度/距离/机动能力 gate 全部通过；`degrade_to_secondary`/`degrade_to_distributed` 阶段 plan owner/version 未进入可执行状态时继续阻断视觉 PNG。
- P0 状态：无 P0 blocker；D7 继续不分配、不授权、不改写 `global_track_id`。

部分实现：

- AirSim SimpleFlight 真实控制已在 main/runtime 层接入 D7，正式 episode bus metrics 已能合并真实执行结果；main runtime 已新增 P1 D4/D5 calibration sweep，D6 标准报告 bundle 已自动生成；D7 本地已补齐多 seed calibration summary/advisory helper，D4 降级阻断、D5 locked、D3 owner/version 和 D4 allowed gate 已有 D7 单元测试覆盖。剩余 P1 风险集中在真实 AirSim 多 seed PN/Pure Pursuit/PNG 数据采集、视觉 gate/range/closing speed 阈值建议验证、这些 gate 在真实多 seed 执行中的回归呈现、3D/高度差、机动能力/FRPN benchmark 数据和长期 D5 事件流稳定性。
- 相机前移 `0.5m`、`120deg` FOV 和 `look_at_target`/CV look-at 已在 runtime/settings/tests 中接入；D7 主线只消费 bbox 和固定焦距近似，不管理真实相机外参。
- `png_guidance_delivery` 的 truth/gimbal/strapdown、PX4/MAVLink/body-rate、YOLO/ByteTrack 是方案和复现实验包；主线只抽取轻量 gate 与 SimpleFlight 速度命令。

未实现：

- 更真实机动约束、3D PN、FRPN/augmented PN、MPC/NMPC。
- 硬件飞控、实机 PX4 Offboard、MAVLink body-rate/attitude 默认主线。
- YOLO/ByteTrack 图像检测直接闭环控制；D7 只提供 bbox/LOS 离线 replay adapter，真实图像流、模型和控制主线接入仍需 main/D5/D6 后续完成。

---

## 1. 目标与边界

D7 的目标是作为 D1-D7 主流程中的导引合同层，在 D3/D4/D5 合同通过后输出 PN/PNG guidance records，使系统从版本化分配结果进入可评估的中段/末端闭环。它只做比例导引及其改进型导引律，不负责上游态势生成或身份判断。

D7 负责：

- 基于 `GlobalTrack` 或雷达/全局航迹估计计算 `radar_midcourse` 比例导引。
- 基于 D5 已锁定的末端视觉目标计算 `vision_terminal` 视觉 PN 或 LOS 追踪。
- 维护导引阶段状态机：`launch/takeoff -> radar_midcourse -> handover_pending -> vision_terminal -> hit/abort`。
- 输出 `GuidanceRecord` 和 D7 gate/command metadata；AirSim runtime 负责写出 `control_commands.csv` 和 episode summary，供 D6 统计。
- 记录 LOS、LOS-rate、闭合速度、导航比、限幅加速度、限幅转向率、最小距离、碰撞对象和终端检测超时等字段。

D7 不负责：

- D1 传感器融合和多源状态估计。
- D2 数据关联、`global_track_id` 维护、ID Switch 处理。
- D3 资源-目标分配、重分配、迟滞和计划授权。
- D5 末端身份认证、视觉局部轨迹到全局航迹的绑定。
- D6 指标判分、报告聚合和离线统计口径。

核心约束：D7 的导引目标必须来自上游已经确认的 `assigned_global_track_id`。中段和末端必须继承同一个分配目标；D7 不得因为末端看到其他更近目标而自行换绑。

---

## 2. 当前实现评审

当前 D7 集成状态分为三层：D7 本地算法/合同模块、D7-owned runtime bus adapter，以及 main/runtime 消费 D7 API 的 AirSim controlled intercept。D7 只拥有前两层；AirSim 启停、episode 编排、SimpleFlight 调用和报告写盘仍由 main/runtime 负责。

D7 本地算法/合同模块：

```text
research_modules/d7_proportional_guidance/
  d7_proportional_guidance/models.py
  d7_proportional_guidance/pn.py
  d7_proportional_guidance/simulator.py
  d7_proportional_guidance/airsim_dry_run.py
  d7_proportional_guidance/terminal_gate.py
  d7_proportional_guidance/vision_png.py
```

该模块已经提供 `GuidanceState`、`GuidanceConfig`、`GuidanceCommand`、`GuidanceRecord`、`compute_proportional_navigation_command()`、`simulate_guidance_episode()`、`evaluate_terminal_png_contract()` 和 `SimpleFlightPngGuidanceFilter`。它记录 `range_m`、`los_angle_rad`、`los_rate_radps`、`closing_speed_mps`、PN 限幅、D3/D4/D5 contract、bbox/LOS/TTC gate 和 mode/handoff 字段。

D7-owned runtime bus adapter：

```text
research_modules/d7_proportional_guidance/
  d7_proportional_guidance/runtime_bus.py
  d7_proportional_guidance/comparison.py
  d7_proportional_guidance/replay.py
  d7_proportional_guidance/calibration.py
```

该层让调用方注入任意长度 assignment pair 的 D3 binding、D4 permission、D5 terminal association 和 bbox observation；D7 为每个 `resource_id -> assigned_global_track_id` 独立维护视觉 filter，输出 main/D6 可消费的 gate、handoff、reject reason、guidance law、summary 和 calibration advisory 字段。它不创建 assignment、不授权、不控制车辆，也不假设 2v2 或 5v5。

AirSim controlled intercept 的 runtime consumer：

```text
research_modules/airsim_runtime/intercept.py
```

该实现中，拦截无人机使用 SimpleFlight，多旋翼控制接口由 main 显式启用、解锁、起飞并发送 `moveByVelocityZAsync` 速度/高度命令。目标不是 AirSim 车辆，不使用 SimpleFlight，而是非车辆 Unreal actor，由 main 通过 `simSetObjectPose` 按水平速度移动。目标识别使用 AirSim `simGetDetections` 检测框。2v2 和 5v5 只作为 baseline/回归场景；实际仿真规模由 main runtime 的 `--drone-count N` 决定。

数量边界需要和 baseline 区分：D7 不应假设 2v2 或 5v5；main 应为 D3 输出的每个有效 assignment pair 创建独立 D7 控制上下文，分别持有 D3 binding、D4 permission、D5 locked evidence、初段位置 PNG/PN 记录状态和末端视觉 PNG filter。

当前 Blocks 稳定闭环采用：

- 中段：使用 actor 真值/全局航迹等价估计调用 D7 PN，输出二维期望航向和速度命令。
- 末端：进入 terminal handoff 后先过 D3/D4/D5 contract；contract 通过后调用该 pair 自己的 `SimpleFlightPngGuidanceFilter`，若 bbox/LOS/TTC/机动 gate 通过则进入 `vision_terminal` 并使用 `png_vm`/`png_ttc` 速度命令；未通过时保持中段 PN 或保守 LOS heading。
- 成功判据：`range_m <= intercept_radius_m` 或碰撞对象名匹配已分配 actor/object name。
- 失败判据：资源/目标缺失、末端检测超时、异常高度、episode 超时等。

新增融合：用户已提供并多轮测试过的 `png_guidance_delivery` 已作为 D7 的算法来源进入主线。当前主线没有直接调用其中的 PX4/MAVLink/YOLO 示例，而是抽取为 `SimpleFlightPngGuidanceFilter`：

- `VisionGuidanceObservation`：承接 D5/AirSim detect 的 bbox、置信度、local/global ID 和时间戳。
- `PngGuidanceConfig`：配置 `los`、`png_ttc`、`png_vm` 三类末端导引/保底律。
- `VisionGuidanceQuality`：输出 bbox 质量、LOS 质量、机动裕度、TTC、拒绝原因。
- `PngGuidanceCommand`：输出 SimpleFlight 可用的水平速度命令和导引日志字段。

主线明确不接入 delivery 包中的 PX4 Offboard、MAVLink body-rate、attitude 控制、YOLO/TensorRT 和真实平台安全流程。当前仿真仍使用 SimpleFlight `moveByVelocityZAsync`，目标检测来自 AirSim `simGetDetections`。

需要明确的限制：

- 当前 AirSim 末端已实际消费视觉 gate 和 `png_vm` 速度命令；`png_ttc` 在 D7 API 和 delivery 中可用，但不是 runtime 默认导引律。
- 严格像素 `center_px -> bearing -> bearing_rate -> visual PN` 已以轻量形式接入 D7 gate；更复杂的 strapdown body-rate、YOLO、KF、TTC relaxed baseline 保留为 delivery 参考，不进主线。
- AirSim 默认不保存相机 PNG，只保留检测框、相机/图像元数据、D5 所需的本地视觉观测字段和拦截控制日志；`--save-images` 只用于调试。
- 碰撞不能只看 `has_collided=True`。只有 `collision_object_name` 包含 assigned actor name 或 assigned object id 时，才算 `collision_intercept`；撞地、撞障碍、撞其他目标都不能记为成功。
- 正式 main bus metrics 应看执行后合并口径；raw contract metrics 可用于诊断 D3/D4/D5 gate，但不能单独代表真实拦截执行结果。
- D7 本地 `D7RuntimeBus`、comparison rows、bbox/LOS replay adapter 和 calibration summary helper 只提供可消费的 gate/report/advisory 字段；本轮已补齐 handoff/guidance summary、gate pass rate、bbox/TTC/LOS 摘要、threshold advisory 和 3D/FRPN benchmark-only 字段。真实 AirSim 多 seed 数据采集、YOLO/ByteTrack replay 数据源和 D6 正式报告仍由 main/D5/D6 集成。

---

## 3. 算法原理

### 3.1 中段雷达比例导引

中段输入来自 D1/D2 输出的 `GlobalTrack` 或等价雷达/全局航迹估计，再由 D3/D4 的分配结果限定目标 ID。D7 只需要以下状态：

```text
pursuer:
- resource_id
- timestamp_s
- position_m / position_ned
- velocity_mps / velocity_ned

target estimate:
- assigned_global_track_id
- timestamp_s / valid_at
- position_m / position_ned
- velocity_mps / velocity_ned
- covariance_trace
- source: global_track | radar_track | airsim_actor_track
```

二维相对状态定义为：

```text
r = target_position - pursuer_position
v = target_velocity - pursuer_velocity
R = ||r||
lambda = atan2(r_y, r_x)
lambda_dot = cross2(r, v) / R^2
V_c = -dot(r, v) / R
```

其中：

- `lambda` 是 LOS angle。
- `lambda_dot` 是 LOS-rate，表示视线角速度。
- `V_c` 是 closing speed，目标距离缩小时为正。
- `N` 是导航比，当前默认 `3.0`，可在离线实验中扫参。

经典 PN 横向加速度：

```text
a_n = N * V_c * lambda_dot
```

D7 输出前需要进行工程限幅：

```text
a_limited = clip(a_n, -max_lateral_accel, max_lateral_accel)
omega = a_limited / pursuer_speed
omega_limited = clip(omega, -max_turn_rate, max_turn_rate)
desired_heading = current_heading + omega_limited * dt
```

离线模块记录加速度和转向率；AirSim 运行时把 `desired_heading` 转为水平速度命令：

```text
command_vx_mps = intercept_speed_mps * cos(desired_heading)
command_vy_mps = intercept_speed_mps * sin(desired_heading)
command_z_ned_m = intercept_altitude_ned_z
```

这仍是仿真控制抽象，不是可直接迁移到真实平台的飞控接口。

### 3.2 改进 PN 的扩展点

当前代码实现经典 PN。后续可在同一接口下增加改进型 PN，但必须保持输入输出和日志字段兼容：

- `biased_pn`: 在末端给 LOS 收敛方向增加小偏置，用于离线比较末端可见性。
- `augmented_pn`: 在 target acceleration estimate 可用时加入目标机动补偿项。
- `true_pn`: 使用惯性 LOS-rate 与闭合速度的标准形式。
- `pure_pursuit_fallback`: 当 `V_c <= 0`、速度过小或 LOS-rate 数值不稳定时退化到追踪 LOS heading。

改进 PN 只改变 `commanded_lateral_accel_mps2` 的生成方式，不改变目标来源和授权边界。

### 3.3 末端视觉 PN / LOS 导引

末端触发条件必须来自 D5 的 `TerminalAssociation`，而不是 D7 自己识别图像目标。推荐触发链路：

```text
D3 AssignmentPlan
-> assigned_global_track_id
-> D5 TerminalAssociation(decision_state="locked")
-> association.assigned_global_track_id == assignment.assigned_global_track_id
-> D7 enters vision_terminal
```

末端视觉输入建议包含：

```text
TerminalAssociation:
- assigned_global_track_id
- local_track_id
- decision_state: locked | ambiguous | hold | reacquire
- association_confidence
- assignment_version
- plan_id / plan_version

LocalVisualTrack / AirSimDetectionBox:
- camera_id
- bbox_xyxy
- center_px
- timestamp
- detection_score / quality
- object_id / airsim_detection_name
- mot_history_length
```

当前 Blocks 控制实现中，进入 terminal handoff 后先构造 `VisionGuidanceObservation`，再由 D7 gate 将检测框中心转换为相机视线角。若 contract 和 gate 通过，runtime 使用 `PngGuidanceCommand.velocity_ned`；若未锁定或 gate 失败，则继续中段 PN 或保守 LOS heading。核心像素链路为：

```text
relative_bearing = atan((center_px.x - cx) / fx)
los_angle = vehicle_heading + relative_bearing
los_rate = finite_difference(los_angle, dt)
a_n = N * V_c_estimate * los_rate
```

如果缺少可靠距离或闭合速度，末端仍采用两级策略：

1. `vision_los_tracking`: 只用像素中心偏差/LOS heading 做稳定追踪。
2. `vision_png`: 在 D3/D4/D5 contract 通过，检测连续、时间戳稳定、像素 LOS-rate、TTC/闭合速度和机动裕度可靠后启用 `png_vm` 或 `png_ttc`。

---

## 4. 阶段切换状态机

推荐 D7 状态机如下：

```text
launch/takeoff
  -> radar_midcourse
  -> handover_pending
  -> vision_terminal
  -> hit

任一阶段
  -> abort
```

### 4.1 `launch/takeoff`

入口：

- D3/D4 提供有效 `AssignmentPlan`。
- `resource_id`、`vehicle_name`、`assigned_global_track_id` 可解析。
- AirSim 控制 episode 中 SimpleFlight API control 已启用、已 arm、已 takeoff，并移动到 `intercept_altitude_ned_z`。

出口到 `radar_midcourse`：

- 资源状态可用。
- 目标 `GlobalTrack` 或 actor truth estimate 可用。
- 当前计划版本未过期。

失败到 `abort`：

- 起飞失败、API control 不可用、资源缺失、计划未授权或版本不匹配。

### 4.2 `radar_midcourse`

入口：

- 有 assigned target 的全局航迹估计。
- D5 尚未输出稳定 `locked`，或目标未进入终端距离窗口。

行为：

- 使用 `GlobalTrack`/actor track 计算 PN。
- 输出限幅后的水平速度/航向命令。
- 记录 `range_m`、`los_rate_radps`、`closing_speed_mps`、`mode="radar_midcourse"`。

出口到 `handover_pending`：

- `range_m <= terminal_switch_range_m`，或 terminal handoff 时间/视场条件满足。

失败到 `abort`：

- assigned target 丢失超过阈值。
- `GlobalTrack` stale 或 covariance 发散到不可用。
- D3/D4 撤销当前分配。

### 4.3 `handover_pending`

入口：

- 已进入末端距离窗口。
- D7 请求 D5 对同一 `assigned_global_track_id` 做终端确认。

行为：

- 保持中段 PN 或低增益 LOS 追踪。
- 等待 D5 `TerminalAssociation.decision_state`。
- 记录 terminal handoff latency 和检测可见性。

出口到 `vision_terminal`：

- D5 返回 `locked`。
- `TerminalAssociation.assigned_global_track_id == AssignmentPlan.assigned_global_track_id`。
- `assignment_version` 或 `plan_version` 匹配当前计划。

保持或回退：

- D5 返回 `hold` 或 `ambiguous` 时，保持 `handover_pending` 或回到 `radar_midcourse`。
- D5 返回 `reacquire` 时，继续按上游航迹导引并请求重新捕获。

失败到 `abort`：

- 末端窗口内持续未检测到 assigned target。
- `terminal_detection_timeout_s` 超时。
- D5 明确报告 friend conflict 或 assigned target mismatch。

### 4.4 `vision_terminal`

入口：

- D5 对 assigned target 输出 `locked`。
- AirSim 当前实现中 `pair.terminal_locked=True`。

行为：

- 当前 Blocks runtime 在 gate 通过时采用 `SimpleFlightPngGuidanceFilter` 输出的视觉 PNG 速度命令，默认 `guidance_law=png_vm`。
- 若视觉 gate 暂未通过但仍处于 handoff，保持中段 PN 或保守 LOS heading，不把失败归因为目标重绑。
- 继续检查 assigned target 检测是否存在；短时丢失可用 `last_detection_s` 保持，但超过阈值必须 abort。

出口到 `hit`：

- `range_m <= intercept_radius_m`。
- 或 AirSim collision object name 匹配 assigned actor/object name。

失败到 `abort`：

- 检测超时。
- 碰撞对象不是 assigned actor/object。
- 撞地、异常高度、撞障碍、撞其他目标。
- D5 锁定丢失且无法在窗口内恢复。

### 4.5 `hit` / `abort`

`hit` 只表示仿真 episode 的闭环成功事件，推荐细分：

- `range_intercept`: 最近距离达到阈值。
- `collision_intercept`: AirSim 碰撞对象名匹配 assigned target。

`abort` 必须记录原因：

- `resource_missing`
- `target_missing`
- `terminal_detection_timeout`
- `below_ground_or_invalid_altitude`
- `assignment_revoked`
- `terminal_identity_mismatch`
- `timeout`

---

## 5. 与其他模块接口

### 5.1 D1/D2 `GlobalTrack`

D7 中段消费 D1/D2 的航迹状态，但不修改航迹：

```text
GlobalTrack / CanonicalTrack
- global_track_id
- position_ned: [x, y, z]
- velocity_ned: [vx, vy, vz]
- covariance / covariance_trace
- valid_at / timestamp
- track_version
- lifecycle_state / quality_state
```

二维 D7 只使用水平 `x/y/vx/vy`；高度由 AirSim 控制参数保持，例如 `intercept_altitude_ned_z`。如果后续扩展三维 PN，应新增独立模式并保留二维字段兼容。

### 5.2 D3 `AssignmentPlan`

D7 启动导引前必须读取版本化分配：

```text
AssignmentPlan
- plan_id
- version
- created_at
- human_authorization_state
- assignments[]

Assignment
- resource_id
- target_id / assigned_global_track_id
- cost_breakdown
- feasibility_state
```

建议给 D7 的最小绑定 DTO：

```text
AssignmentGuidanceBinding
- resource_id
- vehicle_name
- assigned_global_track_id
- plan_id
- plan_version
- track_version
- assignment_validity_state
- authorization_state
```

若计划版本过期、分配被撤销或资源被重分配，D7 必须停止当前导引并输出 `abort` 或 `hold`，不能继续沿旧目标闭环。

### 5.3 D5 `TerminalAssociation`

D5 是末端进入视觉导引的门控模块。D7 只接受如下保守状态：

```text
TerminalAssociation
- assigned_global_track_id
- local_track_id
- decision_state
- association_confidence
- ambiguity_score
- friend_conflict_state
- assignment_version
```

处理规则：

- `locked`: 若 ID 和版本匹配，进入或保持 `vision_terminal`。
- `hold`: 不切换目标；保持 handover 或低增益中段。
- `ambiguous`: 不使用视觉导引；继续等待或请求 D3/D4 仲裁。
- `reacquire`: 保持 assigned ID，尝试重新进入 D5 末端确认。
- `friend_conflict_state != none`: 立即停止末端导引并记录安全事件。

### 5.4 D6 指标日志

D7 不计算最终指标，只输出 D6 可消费日志。推荐统一记录：

```text
GuidanceRecord
- timestamp_s
- resource_id
- assigned_global_track_id / target_id
- mode
- range_m
- los_angle_rad
- los_rate_radps
- closing_speed_mps
- commanded_lateral_accel_mps2
- limited_lateral_accel_mps2
- limited_turn_rate_radps
- mode_switch
- observation.source

InterceptCommandRecord
- timestamp_s
- resource_id
- vehicle_name
- target_id
- mode
- range_m
- command_vx_mps
- command_vy_mps
- command_z_ned_m
- terminal_locked
- detection_seen
- collision_seen
- collision_object_name
- status
- abort_reason
```

D6 可从这些记录聚合 `time_to_intercept_s`、`min_range_m`、`guidance_mode_switch_count`、`terminal_mode_entry_rate`、`collision_object_name`、`terminal_detection_timeout_count` 等指标。

---

## 6. AirSim 当前实现与限制

### 6.1 控制链路

AirSim 受控拦截链路：

```text
Blocks launch/reset
-> prepare_interceptor_control()
-> enableApiControl / armDisarm / takeoffAsync / moveToZAsync
-> sample_frame()
-> D7 PN / LOS heading command
-> moveByVelocityZAsync(vx, vy, z, duration, vehicle_name)
-> collision/range/detection timeout check
-> hover / land / release
```

拦截无人机是 SimpleFlight 多旋翼；目标 actor 不是车辆。这样避免目标机也受到 SimpleFlight 飞控和碰撞物理的额外状态影响，便于主流程精确设置 2v2 水平穿越 baseline 目标。该 baseline 不能扩展为 main runtime 的固定数量假设；N-pair 控制必须由 main 按 `--drone-count` 和有效 assignment pair 显式创建 D7 上下文。

### 6.2 目标 actor 与检测

目标配置来自 `BlocksActorTargetSpec`：

```text
- object_id: TGT-001 ... TGT-N
- actor_name: MSM_TargetActor_1 ... MSM_TargetActor_N
- start_ned
- velocity_ned
- asset_name
- fallback_actor_name
```

当前与 YOLO/视觉 PNG 联调推荐并默认使用 Blocks/AirSim 无人机 mesh asset `Quadrotor1`；main runtime actor asset default 已由 main 同步为 `Quadrotor1`，后续重点是真实 AirSim 验证和阈值/检测调参。`1M_Cube_Chamfer` 只保留给旧接口、旧报告和几何 baseline 复现。D7 delivery 脚本的 `Intruder*`/`IntruderActor` 仍是 legacy alias，不应成为新 runtime handoff 的默认目标命名。

每个采样时刻由 `position_at(timestamp)` 得到目标位置，再通过 `simSetObjectPose` 更新 actor。检测链路通过：

```text
simClearDetectionMeshNames
simSetDetectionFilterRadius
simAddDetectionFilterMeshName
simGetDetections
```

把 AirSim 内置检测框转换为 `AirSimDetectionBox` / D5 `LocalVisualTrack`，保留：

- `object_id`
- `camera_id`
- `bbox_xyxy`
- `center_px`
- `classification_hint`
- `confidence`
- `mot_history_length`
- `airsim_detection_name`

默认不保存 PNG，不影响 D5/D6，因为检测框、相机元数据、目标 actor 名和时间戳已经足够支撑当前评估。

### 6.3 当前限制

当前实现适合作为 Blocks 第一阶段稳定闭环：

- 2v2/5v5 只作为 baseline 场景；main runtime N-pair 执行时应按 `--drone-count N` 和每个有效 assignment pair 独立发命令、记日志和维护 D7 filter。
- 中段 PN 使用二维 NED 平面。
- 末端使用 D5 locked 和 D3/D4/D5 contract 允许后的 D7 视觉 PNG gate；gate 通过时使用 `png_vm`/`png_ttc` 速度命令，未通过时保持保守 PN/LOS。
- 成功严格绑定 assigned target 的 range 或 collision object。

限制和下一步：

- 轻量像素 LOS-rate visual PNG 已接入；剩余重点是真实 AirSim 多 seed calibration、真实相机/检测框 replay 数据、距离/闭合速度估计口径和长期 D5 事件流。
- `simGetDetections` 是 AirSim 内置检测，不等价于真实视觉模型。
- 当前 actor 目标速度简单，适合验证接口和状态机；复杂机动应在后续离线批量实验中加入。
- `collision_intercept` 对 Blocks 物理和 actor mesh 有依赖，因此必须同时保留 `range_intercept` 作为可复现补充判据。
- 控制命令是 `moveByVelocityZAsync` 高层速度接口，不代表底层姿态、推力或真实飞控。

---

## 7. 测试与指标方案

### 7.1 单元测试

离线 D7 已覆盖：

- PN 能降低距离。
- `terminal_switch_range_m` 能触发 `vision_terminal`。
- 加速度和转向率限幅生效。
- `GuidanceRecord` 包含几何字段。
- AirSim dry-run adapter 输出 `radar_midcourse` 和 `vision_terminal` 记录。

建议新增或保持的测试：

- `closing_speed_mps <= 0` 时不产生发散命令，回退到 LOS heading 或限幅命令。
- `range_m` 接近 0 时 LOS-rate 数值稳定。
- `assigned_global_track_id` 不匹配时禁止进入 `vision_terminal`。
- D5 `ambiguous/hold/reacquire` 不会导致 D7 换绑目标。

### 7.2 AirSim actor baseline 与 N-pair 测试

受控 2v2 episode 应验证：

- `default_2v2_actor_target_specs()` 生成两个 actor target。
- actor 使用 `simSetObjectPose` 移动，目标不在 `target_vehicle_names` 中作为 SimpleFlight 车辆出现。
- 两架拦截无人机调用 `enableApiControl`、`armDisarm`、`takeoffAsync`、`moveToZAsync`、`moveByVelocityZAsync`。
- `simGetDetections` 能返回 assigned actor 的 bbox。
- `control_commands.csv` 和 `intercept_summary.json` 写出。
- 未指定 `--save-images` 时不写 PNG。

N-pair runtime 回归还应验证：

- `--drone-count N` 只由 main runtime 解释，D7 不读取固定数量常量。
- main 对每个有效 assignment pair 创建独立 D7 控制上下文。
- 初段位置 PNG/PN 和末端视觉 PNG 的 time-series 都按 `resource_id/target_id/assignment_id` 隔离。
- D5 `locked`、D3 assignment/version、相机 bbox/LOS 稳定性、机动裕度和距离/闭合条件逐 pair 判定，任一 pair 拒绝不影响其他 pair。

### 7.3 成功与失败判据

成功：

```text
status == range_intercept
  if range_m <= intercept_radius_m

status == collision_intercept
  if collision.has_collided
  and collision_object_name matches assigned actor/object name
```

失败：

```text
status == aborted
abort_reason in {
  resource_missing,
  target_missing,
  terminal_detection_timeout,
  below_ground_or_invalid_altitude,
  terminal_identity_mismatch,
  assignment_revoked
}

status == timeout
  if episode ends before hit/abort
```

撞地、撞障碍、撞非 assigned target 只能记为失败或安全事件，不能记为命中。

### 7.4 D6 指标

建议 D6 从 D7/AirSim 日志中聚合：

| 指标 | 来源 | 含义 |
|------|------|------|
| `time_to_intercept_s` | `InterceptPair.time_to_intercept_s` | 从导引开始到首次成功判据的时间 |
| `min_range_m` | `InterceptPair.min_range_m` / `GuidanceRecord.range_m` | 每个资源-目标 pair 的最近距离 |
| `collision_object_name` | `InterceptCommandRecord.collision_object_name` | 验证是否撞到 assigned actor/object |
| `collision_intercept_count` | pair status | 碰撞对象匹配的成功次数 |
| `range_intercept_count` | pair status | 距离阈值成功次数 |
| `terminal_detection_timeout_count` | abort reason | 末端检测超时次数 |
| `guidance_mode_switch_count` | `mode_switch` / command mode sequence | 中段到末端切换次数 |
| `terminal_mode_entry_rate` | pair count vs terminal locked count | 已分配 pair 中进入末端模式比例 |
| `command_saturation_rate` | D7 command saturation fields | 加速度/转向率限幅比例 |
| `assigned_collision_mismatch_count` | collision object vs assigned target | 撞错对象或撞地事件数 |
| `main_episode_bus_execution_metrics_merged` | main bus metrics metadata | 正式 metrics 是否已经合并真实 D7 执行产物 |
| `raw_contract_reject_count` | raw contract metrics | 执行前 D3/D4/D5 合同诊断拒绝数，不等同于最终拦截失败数 |
| `owner_mismatch_count` | D7 terminal contract rejects | D4 指定接管 owner 与 D3 binding owner 不一致或缺失的拒绝数 |
| `bbox_los_replay_vehicle_control` | D7 replay summary | 离线 replay 必须为 `False`，防止 YOLO/ByteTrack replay 误入控制主线 |

报告图建议包括：

- `range_m` 随时间曲线。
- `radar_midcourse / handover_pending / vision_terminal` 模式时间线。
- 每个 pair 的 `min_range_m` 柱状图。
- `collision_object_name` 与 assigned target 对照表。
- `terminal_detection_timeout_count` 按 episode 的统计。

---

## 8. 补充实施计划

### 8.1 短期：固化当前 Blocks 稳定闭环

- 保持 2v2 actor target 和 SimpleFlight interceptor 作为 baseline 架构。
- 对 main runtime，按 `--drone-count N` 为每个有效 assignment pair 创建独立 D7 控制上下文，不共享视觉 filter 状态。
- actor target 默认外观已由 main/runtime 与 D7 delivery 对齐到 `Quadrotor1`；cube asset 仅作为 legacy 几何 baseline 显式复现选项，后续需要真实 AirSim 验证和阈值/检测调参。
- 明确 `collision_intercept` 必须匹配 assigned actor/object name。
- 在 summary 中保留 `time_to_intercept_s`、`min_range_m`、`status`、`abort_reason` 和 `collision_object_name`。
- 默认继续不保存 PNG，只保存检测框和相机元数据。
- 将 `handover_pending` 显式写入日志状态，即使控制命令仍沿用中段 PN。

### 8.2 P1 done/保持：D3/D4/D5 runtime gate 与 episode bus

- D7 API 已将 D3 binding、D4 action 和 `TerminalAssociation(decision_state="locked")` 作为 `vision_terminal` 的必要入口；D7 本地 `D7RuntimeBus` 已提供 N-pair injection adapter。
- D4 gate blocking、D3/D4/D5 terminal contract gate、owner/version gate 已完成。D7 持续校验 D3 `plan_id/plan_version/owner_node_id/track_version`、D5 `assigned_global_track_id`、`assignment_version` 和 D4 `new_plan_id/new_plan_version/target_node_id`，并把不一致写成 `terminal_contract_reject_reason`。
- D4 `request_center_replan`、`degrade_to_secondary`、`degrade_to_distributed` 和 `reassign` 阶段必须阻断视觉 PNG，确认重分配窗口内不使用旧 D5 lock；只有 D5 `locked`、D3 version/owner 一致、D4 action 允许后才尝试视觉 PNG。
- controlled 5v5 center replan 与 2v2 secondary visual PNG gate 回归已通过。main runtime 已把 D7 runtime summary 接入 episode bus，D7 文档不再把这些列为待补能力。
- 最新 5v5 D4/D5 mobile recon/gimbal stress 只改善侦察观测质量：二级网络同帧覆盖和降级 cross-view 仍不足，因此 D7 不放宽视觉 PNG gate；`degrade_to_secondary`/`degrade_to_distributed` 期间若 plan owner/version 尚不可执行，继续记录合同拒绝并保持中段/等待状态。
- 对 `ambiguous/hold/reacquire` 分别输出保守行为，不切换目标，不改写 `global_track_id`；D4 软风险 `continue_center` 不应让 D7 全帧进入 `abort_revoke`。

### 8.3 P1 optional：视觉 PNG 回放与真实检测链路

- D7 已将 `simGetDetections` bbox、YOLO/ByteTrack bbox replay 统一成 D7 `VisionGuidanceObservation` 的离线 adapter；后续由 main/D5 接入真实 D5 local track 事件流。
- 对同一 `local_track_id` 做时间连续性、measurement age、丢检重捕获和 LOS-rate 噪声评估。
- 引入距离/闭合速度估计来源：D2 全局航迹预测、多视角估计、或 AirSim truth-only 离线标签；控制主线不得使用 truth ID 做在线身份绑定。
- 在日志中区分 `source="airsim_detect_metadata"`、`source="yolo_replay"`、`source="truth_only_eval"`，并保留 `terminal_switch_reject_reason`。
- 先用 D7 离线 replay 评估 LOS-rate、TTC 面积噪声、近距裁切和限幅。YOLO/ByteTrack 真实图像链路只作为离线 replay 或 optional 实验路径，不进入默认 SimpleFlight controlled intercept。

### 8.4 P1：真实 AirSim 多 seed calibration 与报告

- D7 已提供 `run_guidance_strategy_comparison(...)` 和 `summarize_guidance_strategy_comparison(...)`，覆盖 PN、Pure Pursuit、`png_vm`、`png_ttc`。
- D7 已提供 `summarize_guidance_calibration(...)`，可把 comparison rows、replay summary、D7 runtime outputs 和 `GuidanceRecord` 统一成按 guidance law 分组的 calibration summary，字段覆盖 terminal range、closing speed、bbox/LOS/maneuver gate、reject reason、threshold version 和 benchmark-only 3D/FRPN 口径。
- main runtime 已新增 P1 D4/D5 calibration sweep，D6 标准报告 bundle 已自动生成 records CSV、summary CSV、summary JSON 和 Markdown。D7 不再把 sweep 编排或报告写盘列为本模块缺口；D7 后续只需保持输出字段稳定，并配合真实 AirSim 多 seed 样本校准。
- D6/main 后续应把这些 rows、D7 calibration summary 与真实 N-pair episode metrics 汇总，统一报告 `min_range_m`、`time_to_intercept_s`、`terminal_contract_reject_reason`、`terminal_switch_reject_reason`、`visual_png_switch_count`、guidance mode/handoff distribution、bbox/TTC/LOS gate 摘要、threshold version、D4 降级窗口视觉 PNG 阻断、D5 locked + D3 owner/version + D4 allowed gate 和 raw contract vs execution metrics 双口径。
- 真实 AirSim 多 seed calibration 应校准 `png_vm`、`png_ttc`、bbox/LOS/TTC gate、terminal range、视觉延迟、闭合速度/距离估计、3D/高度差、机动裕度和 FRPN/augmented PN benchmark；D7 侧保持字段稳定，只输出 advisory，不在本模块内替代 D6/main 聚合，也不把 calibration 结果用于绕过 D3/D4/D5 gate。
- 该对照接口只补报告字段和切换/gate 日志，不修改 PN/PNG 控制律本体。

---

## 9. 结论

D7 当前已经具备可测试的经典 PN 研究模块、D3/D4/D5 terminal contract、SimpleFlight 视觉 PNG gate，以及被 AirSim controlled intercept 消费的 N-pair 导引上下文。架构上应继续坚持四条原则：

1. 目标 ID 来自 D1/D2/D3/D5，D7 不创建、不关联、不改绑。
2. 中段使用全局航迹 PN，末端必须由 D5 对同一 `assigned_global_track_id` 锁定后进入视觉导引。
3. AirSim 成功判据必须绑定 assigned actor/object name；撞地或撞错对象不能算成功。
4. main runtime 由 `--drone-count N` 控制规模，并为每个有效 assignment pair 创建独立 D7 控制上下文；2v2 只能作为 baseline，不是数量假设。

剩余 P1 聚焦真实 AirSim 多 seed PN/Pure Pursuit/PNG 数据采集、视觉 gate 阈值建议验证、闭合速度/距离估计、3D/高度差、机动能力/FRPN benchmark 数据、D6/main 报告聚合，以及 YOLO/ByteTrack 或 AirSim detect 数据的离线 replay/optional 路径。P2 optional benchmark 包括 PX4/MAVLink/body-rate、MPC/NMPC、ViSP/ROS2 等非默认主线；这些都不能进入默认 SimpleFlight 控制主线，除非先具备高机动 fixture、平台动力学/安全边界、D6 对照指标和失败回退。
