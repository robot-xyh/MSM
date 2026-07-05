# D7 比例导引架构评审与补充方案

**定位**: D7 负责中段雷达/全局航迹比例导引和末端视觉/LOS 导引的算法、状态切换、控制命令抽象与日志记录。  
**边界**: 本文只面向当前离线研究模块和 AirSim Blocks 仿真闭环，不包含真实平台火控参数、毁伤模型、硬件驱动、自动处置或绕过人工授权的流程。

---

## 1. 目标与边界

D7 的目标是在已有 D1-D6 主流程之后补齐“导引律”层，使系统从版本化分配结果进入可评估的中段/末端闭环。它只做比例导引及其改进型导引律，不负责上游态势生成或身份判断。

D7 负责：

- 基于 `GlobalTrack` 或雷达/全局航迹估计计算 `radar_midcourse` 比例导引。
- 基于 D5 已锁定的末端视觉目标计算 `vision_terminal` 视觉 PN 或 LOS 追踪。
- 维护导引阶段状态机：`launch/takeoff -> radar_midcourse -> handover_pending -> vision_terminal -> hit/abort`。
- 输出 `GuidanceRecord`、AirSim `control_commands.csv` 和 episode summary，供 D6 统计。
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

当前 main 已实现两条 D7 相关链路。

第一条是离线 D7 模块：

```text
research_modules/d7_proportional_guidance/
  d7_proportional_guidance/models.py
  d7_proportional_guidance/pn.py
  d7_proportional_guidance/simulator.py
  d7_proportional_guidance/airsim_dry_run.py
```

该模块已经提供 `GuidanceState`、`GuidanceConfig`、`GuidanceCommand`、`GuidanceRecord`、`compute_proportional_navigation_command()` 和 `simulate_guidance_episode()`。它是二维质点研究模型，记录 `range_m`、`los_angle_rad`、`los_rate_radps`、`closing_speed_mps`、`commanded_lateral_accel_mps2`、`limited_lateral_accel_mps2`、`limited_turn_rate_radps` 和 `mode_switch`。

第二条是 AirSim 2v2 actor 受控拦截 baseline：

```text
research_modules/airsim_runtime/intercept.py
```

该实现中，拦截无人机使用 SimpleFlight，多旋翼控制接口由 main 显式启用、解锁、起飞并发送 `moveByVelocityZAsync` 速度/高度命令。目标不是 AirSim 车辆，不使用 SimpleFlight，而是非车辆 Unreal actor，由 main 通过 `simSetObjectPose` 按水平速度移动。目标识别使用 AirSim `simGetDetections` 检测框。

数量边界需要和 baseline 区分：main runtime 的无人机/目标数量由 `--drone-count N` 统一控制。D7 不应假设 2v2 或 5v5；main 应为 D3 输出的每个有效 assignment pair 创建独立 D7 控制上下文，分别持有 D3 binding、D4 permission、D5 locked evidence、初段位置 PNG/PN 记录状态和末端视觉 PNG filter。

当前 Blocks 稳定闭环采用：

- 中段：使用 actor 真值/全局航迹等价估计调用 D7 PN，输出二维期望航向和速度命令。
- 末端：进入 `terminal_locked` 后采用目标相对方位的 LOS 追踪，让控制器稳定追向已分配目标。
- 成功判据：`range_m <= intercept_radius_m` 或碰撞对象名匹配已分配 actor/object name。
- 失败判据：资源/目标缺失、末端检测超时、异常高度、episode 超时等。

新增融合：用户已提供并多轮测试过的 `png_guidance_delivery` 已作为 D7 的算法来源进入主线。当前主线没有直接调用其中的 PX4/MAVLink/YOLO 示例，而是抽取为 `SimpleFlightPngGuidanceFilter`：

- `VisionGuidanceObservation`：承接 D5/AirSim detect 的 bbox、置信度、local/global ID 和时间戳。
- `PngGuidanceConfig`：配置 `los`、`png_ttc`、`png_vm` 三类末端导引/保底律。
- `VisionGuidanceQuality`：输出 bbox 质量、LOS 质量、机动裕度、TTC、拒绝原因。
- `PngGuidanceCommand`：输出 SimpleFlight 可用的水平速度命令和导引日志字段。

主线明确不接入 delivery 包中的 PX4 Offboard、MAVLink body-rate、attitude 控制、YOLO/TensorRT 和真实平台安全流程。当前仿真仍使用 SimpleFlight `moveByVelocityZAsync`，目标检测来自 AirSim `simGetDetections`。

需要明确的限制：

- 当前 AirSim 末端已具备视觉 gate 和 `png_ttc/png_vm` 速度命令接口，但仍是 SimpleFlight 速度控制，不是 PX4 body-rate 闭环。
- 严格像素 `center_px -> bearing -> bearing_rate -> visual PN` 已以轻量形式接入；更复杂的 strapdown body-rate、YOLO、TTC relaxed baseline 保留为 delivery 参考，不进主线。
- AirSim 默认不保存相机 PNG，只保留检测框、相机/图像元数据、D5 所需的本地视觉观测字段和拦截控制日志；`--save-images` 只用于调试。
- 碰撞不能只看 `has_collided=True`。只有 `collision_object_name` 包含 assigned actor name 或 assigned object id 时，才算 `collision_intercept`；撞地、撞障碍、撞其他目标都不能记为成功。

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

当前 Blocks 稳定实现中，进入 `terminal_locked` 后使用相对位置直接计算 LOS heading，并发送水平速度追踪命令。严格视觉 PN 的下一阶段应将检测框中心转换为相机视线角：

```text
relative_bearing = atan((center_px.x - cx) / fx)
los_angle = vehicle_heading + relative_bearing
los_rate = finite_difference(los_angle, dt)
a_n = N * V_c_estimate * los_rate
```

如果缺少可靠距离或闭合速度，末端可采用两级策略：

1. `vision_los_tracking`: 只用像素中心偏差/LOS heading 做稳定追踪。
2. `vision_pn`: 在检测连续、时间戳稳定、像素 LOS-rate 和距离估计可靠后启用严格 visual PN。

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

- 当前 Blocks 稳定实现采用 LOS heading 追踪。
- 下一阶段可切换到像素 LOS-rate visual PN。
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

- 2v2 actor baseline 目标水平移动。
- baseline 中两架 SimpleFlight 拦截无人机发速度/高度命令；main runtime N-pair 执行时应按每个有效 pair 独立发命令和记日志。
- 中段 PN 使用二维 NED 平面。
- 末端使用 D5 检测锁定后的 LOS heading 追踪。
- 成功严格绑定 assigned target 的 range 或 collision object。

限制和下一步：

- 严格像素 LOS-rate visual PN 尚未实装到 AirSim 控制闭环。
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
- 明确 `collision_intercept` 必须匹配 assigned actor/object name。
- 在 summary 中保留 `time_to_intercept_s`、`min_range_m`、`status`、`abort_reason` 和 `collision_object_name`。
- 默认继续不保存 PNG，只保存检测框和相机元数据。
- 将 `handover_pending` 显式写入日志状态，即使控制命令仍沿用中段 PN。

### 8.2 中期：接入 D5 locked 门控

- 将 `TerminalAssociation(decision_state="locked")` 作为 `vision_terminal` 的唯一入口。
- 校验 `assigned_global_track_id`、`assignment_version`、`plan_version`。
- 对 `ambiguous/hold/reacquire` 分别输出保守行为，不切换目标。
- 把 D5 检测超时和锁定丢失写成 D6 可统计事件。

### 8.3 后续：严格像素 LOS-rate visual PN

- 从 `bbox_xyxy` / `center_px` 和相机内参计算 `relative_bearing_rad`。
- 对同一 `local_track_id` 做时间连续性检查，计算 `los_rate_radps`。
- 引入距离估计来源：D2 全局航迹预测、双目/多视角估计、或 AirSim truth-only 实验标签。
- 在 `GuidanceRecord.observation` 中区分 `source="vision_los_tracking"` 与 `source="vision_pixel_pn"`。
- 使用离线回放先评估 LOS-rate 噪声、丢检和限幅，再进入 AirSim 控制闭环。

---

## 9. 结论

D7 当前已经具备可测试的经典 PN 研究模块和 AirSim 2v2 actor 拦截 baseline。架构上应继续坚持四条原则：

1. 目标 ID 来自 D1/D2/D3/D5，D7 不创建、不关联、不改绑。
2. 中段使用全局航迹 PN，末端必须由 D5 对同一 `assigned_global_track_id` 锁定后进入视觉导引。
3. AirSim 成功判据必须绑定 assigned actor/object name；撞地或撞错对象不能算成功。
4. main runtime 由 `--drone-count N` 控制规模，并为每个有效 assignment pair 创建独立 D7 控制上下文；2v2 只能作为 baseline，不是数量假设。

下一阶段的主要增量不是重写当前稳定闭环，而是在保持状态机和日志兼容的前提下，把末端 LOS 追踪升级为严格像素 LOS-rate visual PN，并把所有切换、超时、碰撞对象和最小距离纳入 D6 指标体系。
