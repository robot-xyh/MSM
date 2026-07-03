# D7 经典比例导引架构计划

## 目标

D7 提供一个可被主流程接入的离线二维比例导引研究模块。模块目标不是实现真实平台控制，而是给集成仿真提供清晰、可测试、可记录的“雷达中段 + 视觉末段”比例导引抽象：

- 中段使用 `radar_midcourse` 模式，输入来自全局航迹或雷达航迹估计。
- 末段使用 `vision_terminal` 模式，输入来自像素/LOS 观测估计。
- 视觉终端使用从 `png_guidance_delivery` 抽取的 SimpleFlight 兼容 PNG gate，先判断相机识别质量、LOS 质量、机动裕度和剩余窗口，再允许进入视觉 PNG/LOS 导引。
- 输出统一的 `GuidanceRecord`，便于后续闭环日志、指标统计和 GIF 可视化。

本模块只做离线二维质点运动、算法解释、日志评估和可视化准备；不提供真实飞控接口、硬件驱动、实时通信、火控参数、毁伤模型、自动处置或授权绕过逻辑。

## PNG guidance delivery 学习与融合

已验证的 `png_guidance_delivery` 包含 truth、gimbal、strapdown 三类 AirSim PNG 验证路径。D7 主线只吸收其中对当前 SimpleFlight Blocks 仿真直接有用的算法核：

- bbox 中心到相机 LOS/bearing 的几何转换。
- LOS-rate 滑窗质量评估和方差门限。
- bbox 面积扩张估计 TTC。
- `LAW=TTC` 的 TTC 增益调度和 `LAW=VM` 的固定 `N * V_m` 思路。
- bbox 太小、贴边、检测不连续、视觉延迟高、机动裕度不足时拒绝切换。

命名口径：

- 当前 main/runtime 默认目标 actor 和 AirSim detect filter 为 `MSM_TargetActor_*`，实际对象名通常类似 `MSM_TargetActor_1`。
- 当前 runtime 默认目标 asset 为 `1M_Cube_Chamfer`。
- `png_guidance_delivery` 内历史默认仍为 `Intruder*` mesh filter 和 `IntruderActor` actor name；它们只作为 delivery 复现实验与旧日志的 legacy alias。

暂不接入：

- PX4 Offboard、MAVLink、body-rate、attitude 控制。
- YOLO/TensorRT 推理链路。
- 自动 arm/offboard 或任何真实平台控制流程。

主线新增 `SimpleFlightPngGuidanceFilter`，它输出 SimpleFlight 速度命令和 gate 质量字段，不直接调用 AirSim API。

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

- `GuidanceMode`：`radar_midcourse`、`vision_terminal`。
- `GuidanceState`：二维位置、速度、时间戳、来源和可选元数据。
- `GuidanceConfig`：步长、PN 系数、加速度限制、转向率限制、末段切换阈值、噪声参数。
- `GuidanceCommand`：单步 PN 输出，包含 LOS、closing speed、原始/限幅加速度、原始/限幅转向率、期望航向。
- `GuidanceRecord`：离线 episode 的逐步记录，包含 truth、estimate、observation 和 PN 字段。
- `PngGuidanceConfig`：视觉 PNG gate 参数，包括 bbox、LOS、TTC、机动裕度和导引律。
- `VisionGuidanceObservation`：D5/AirSim detect 提供的 bbox、置信度、local/global ID 和时间戳。
- `VisionGuidanceQuality`：相机质量、LOS 质量、机动裕度和切换拒绝原因。
- `PngGuidanceCommand`：SimpleFlight 速度命令、导引律、饱和状态和 gate 质量。

### 核心函数

- `compute_proportional_navigation_command(...)`
  - 输入：pursuer state、target estimate、`dt_s`、`navigation_constant`、mode 和限制参数。
  - 输出：`GuidanceCommand`。

- `simulate_guidance_episode(...)`
  - 输入：初始 pursuer/target 状态、`GuidanceConfig`、resource/target 标识。
  - 过程：`radar_midcourse` 中段闭环，满足阈值后切换到 `vision_terminal`。
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

## 交付物

- `PLAN.md`：中文工程计划、数学模型、接口说明和边界。
- `README.md`：中文模块说明、运行命令、示例代码。
- `d7_proportional_guidance/models.py`：dataclass 和模式枚举。
- `d7_proportional_guidance/pn.py`：经典二维 PN 计算函数。
- `d7_proportional_guidance/simulator.py`：单 resource-target pair 离线闭环仿真。
- `d7_proportional_guidance/vision_png.py`：从 delivery 包抽取的 SimpleFlight 兼容视觉 PNG gate。
- `d7_proportional_guidance/__init__.py`：核心 API 导出。
- `tests/`：pytest 覆盖距离收敛、模式切换、限幅和记录字段。

## 后续集成建议

主智能体后续可在不改变 D7 内部边界的前提下，把上游分配结果映射为 `GuidanceState`，把 `GuidanceRecord.as_dict()` 写入统一 episode log，并在 GIF 中绘制 pursuer、target、LOS 线、模式颜色和距离曲线。

AirSim runtime 集成要求：

- 当前阶段只使用 SimpleFlight `moveByVelocityZAsync`。
- 当前 runtime 目标 actor/detection filter 使用 `MSM_TargetActor_*`，目标 asset 使用 `1M_Cube_Chamfer`。
- `Intruder*`/`IntruderActor` 只作为 `png_guidance_delivery` 和历史日志的 legacy alias，不应作为新 runtime handoff 的默认目标名。
- 目标检测输入来自 AirSim `simGetDetections` 的 bbox，不依赖默认保存 PNG。
- 进入视觉终端前必须同时满足 D5 locked/版本一致、bbox 质量、LOS 质量、机动裕度和窗口门槛。
- 若 gate 失败，记录 `terminal_switch_reject_reason`，并保持 `handover_pending` 或回退 `radar_midcourse`。
