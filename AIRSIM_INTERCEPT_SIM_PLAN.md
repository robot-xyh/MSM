# AirSim 无人机拦截仿真验证方案

## 1. 项目目标

本方案面向科研仿真验证，使用 AirSim 构建入侵无人机与拦截无人机的对抗场景，验证地面雷达探测、图像识别、目标配准、融合跟踪、导引拦截和虚拟命中判定的完整闭环。

边界限定如下：

- 仅用于 AirSim 仿真和算法研究。
- 撞击毁伤仅作为虚拟命中/失效判定。
- 不包含真实无人机硬件改造、实飞撞击参数或实际处置部署。
- 当前单目标闭环已跑通，下一阶段主线改为多入侵目标 vs 多拦截机。
- 多目标阶段默认采用中心节点统一融合、统一分配、统一评估；无人机之间直接通信作为后续对照变量。

多目标场景定义：

```text
M = 入侵无人机数量
N = 拦截无人机数量
主线问题 = M 个入侵目标 vs N 架拦截机
默认约束 = 一架拦截机同一时刻最多拦截一个目标，一个目标默认最多分配一架拦截机
```

## 2. 技术路线对比

| 路线 | 优点 | 缺点 | 建议 |
|---|---|---|---|
| 纯 AirSim 真值仿真 | 快速搭建，可直接获得位置、速度、碰撞信息 | 传感器真实性不足 | 适合第 0 阶段算法闭环 |
| AirSim + 雷达噪声模型 | 可验证误差、延迟、漏检对拦截的影响 | 雷达仍是简化模型 | 推荐作为当前多目标主路线 |
| AirSim + 图像识别 | 可验证视觉识别、遮挡、视角影响 | 训练检测器需要数据 | 作为第二阶段增强 |
| AirSim + PX4 SITL | 更接近真实飞控 | AirSim 经典版兼容性和维护风险较高 | 后续验证，不作为首版依赖 |
| Gazebo / Isaac Sim 替代 | 生态更新，物理能力更强 | 迁移成本高 | 作为后续备选 |

推荐路线：

```text
经典 AirSim + Python API + 真值加噪声雷达 + 可选视觉识别 + 虚拟撞击判定
```

## 3. 总体架构

系统建议拆分为 8 个模块：

1. **场景管理器**：管理 episode 初始化、多架目标机路径、多架拦截机初始位置、随机种子、天气、光照和障碍物。
2. **地面雷达仿真模块**：从 AirSim 真值读取多目标状态，加入测距误差、测角误差、测速误差、延迟、漏检、虚警和目标分辨率限制。
3. **图像识别模块**：使用 AirSim RGB、Depth、Segmentation 图像；当前阶段可用分割真值生成多目标检测框，后续替换为 YOLO 类检测器。
4. **目标配准模块**：统一坐标系、时间戳和传感器外参，将雷达目标、图像目标和 AirSim 真值对齐。
5. **融合跟踪模块**：使用 EKF 或 UKF 输出目标融合航迹，记录误差、丢失次数和置信度。
6. **目标分配模块**：多目标阶段默认使用中心化 Hungarian 分配，拍卖算法和 CBBA 作为分布式对照方案。
7. **导引与控制模块**：对比纯追踪、比例导引和预测拦截算法，输出 AirSim 虚拟速度或位置控制指令。
8. **命中判定与评估模块**：基于 AirSim collision info 或距离阈值判定命中，命中后目标状态置为失效并结束 episode。

## 4. 坐标与配准设计

AirSim 默认使用近似 NED 坐标：`x` 前/北，`y` 右/东，`z` 向下。建议系统内部统一使用 NED，论文展示或可视化时再转换为 ENU。

需要维护的坐标系：

- 世界坐标系：AirSim 场景原点。
- 雷达坐标系：地面雷达本体坐标。
- 相机坐标系：地面 PTZ 或拦截机机载相机。
- 拦截机机体系：用于导引控制。
- 目标机机体系：用于姿态和相对速度分析。

目标配准流程：

1. 雷达输出距离、方位、俯仰和径向速度。
2. 将雷达观测转换到世界 NED 坐标。
3. 相机检测框通过相机内参和外参反投影为方向观测。
4. 按时间戳对齐雷达、图像和仿真状态。
5. 使用滤波器融合为统一目标航迹。

### 4.1 目标配准要解决的问题

目标配准不是简单地把多个传感器数据放在一起，而是解决 4 类一致性问题：

1. **时间一致性**：雷达、图像、拦截机状态和 AirSim 真值必须对齐到同一仿真时间轴。
2. **空间一致性**：雷达坐标、相机坐标、无人机机体系和世界坐标必须能互相转换。
3. **目标一致性**：同一个入侵目标在雷达、图像和融合航迹中需要对应到同一个 `global_track_id`。
4. **置信度一致性**：不同传感器的误差不同，融合时要用协方差或置信度表达观测可靠性。

多目标阶段建议所有模块使用 AirSim 仿真时间 `sim_time`，不要直接使用系统墙钟时间。这样可以支持暂停、倍速、回放和确定性复现实验。所有传感器观测必须携带 `timestamp` 和 `sensor_id`，否则后续航迹关联和延迟消融会失去可复现性。

### 4.2 推荐坐标转换链路

雷达观测通常是球坐标形式：

```text
range, azimuth, elevation, radial_velocity
```

推荐转换链路：

```text
雷达球坐标
-> 雷达本体笛卡尔坐标
-> 世界 NED 坐标
-> 融合跟踪状态
```

雷达本体到世界坐标需要维护外参：

```text
radar_position_world = [x, y, z]
radar_rotation_world = R_radar_to_world
```

相机观测通常是图像坐标：

```text
bbox = [u_min, v_min, u_max, v_max]
```

推荐转换链路：

```text
图像检测框中心
-> 相机归一化成像平面
-> 相机坐标系方向向量
-> 世界坐标系方向向量
-> 与雷达/融合航迹做角度门限关联
```

多目标阶段图像不建议直接恢复三维位置。更稳妥的做法是：雷达给出三维位置，图像作为“方向约束”“类别确认”和“近距离 ID 辅助”。这样可以避免单目测距误差和目标遮挡导致航迹交换。

### 4.3 目标关联方法

单目标场景中，配准可以简化为固定关联；该部分已完成，可作为基线：

```text
radar_track_001 + vision_detection_best -> global_track_001
```

多目标场景中，必须使用门限关联和航迹管理：

1. 根据上一时刻融合航迹预测当前目标位置。
2. 将雷达观测转换到世界坐标。
3. 计算观测与预测航迹的马氏距离。
4. 小于门限则认为可关联。
5. 多个候选同时存在时，使用最近邻或 Hungarian 分配。
6. 未关联观测生成新航迹，长时间未更新航迹进入丢失或删除状态。

推荐多目标初始门限：

```text
position_gate = 3 sigma
angle_gate = 2-5 deg
track_timeout = 1-3 s
```

多目标配准必须重点处理 **航迹交叉和 ID switch**。建议记录 `id_switch_count` 指标：当同一个 AirSim 真值目标对应的 `global_track_id` 发生变化，或两个目标交会后 ID 互换，就计为一次 ID switch。该指标应和命中率一起作为核心结果。

### 4.4 融合滤波策略

多目标阶段推荐每条航迹维护一个独立 EKF 或 UKF：

```text
state = [x, y, z, vx, vy, vz]
```

预测步骤：

```text
x_k = F * x_{k-1}
P_k = F * P_{k-1} * F^T + Q
```

更新步骤：

```text
雷达位置/速度观测 -> 直接更新 state
图像方向观测 -> 更新目标方向或只更新 classification/confidence
```

如果目标机动明显，可以升级为 IMM：

- CV：常速度模型。
- CA：常加速度模型。
- CT：协调转弯模型。

多目标初版不建议一开始使用复杂模型。先用 “GNN/Hungarian 数据关联 + 每目标 EKF/UKF” 建立稳定基线，再通过实验量化近距离交会、遮挡、漏检和机动目标下的 ID switch 与命中率下降。

## 5. 系统通信与中心节点设计

### 5.1 是否需要中心节点

多目标对多拦截机阶段推荐采用 **中心化架构**。中心节点负责传感器汇聚、目标配准、融合跟踪、全局目标分配、导引策略选择和实验记录。

原因：

- AirSim 仿真中所有状态可由一个进程读取，中心化实现最简单。
- 多目标配准和目标分配需要全局视角，中心化方案更容易避免重复拦截和任务冲突。
- 配准、分配和评估指标集中处理，便于复现实验。
- 后续研究分布式协同时，可以把中心化结果作为性能上界和对照组。

推荐中心节点名称：

```text
Mission Control / C2 Node
```

中心节点功能：

- 订阅雷达观测、图像检测、无人机状态。
- 维护全局目标航迹表。
- 运行多目标多拦截机分配算法。
- 向每架拦截机发布目标 ID、导引模式、任务优先级和速度/位置指令。
- 监控拦截机之间的空间冲突和任务重复分配。
- 记录 episode 日志和评估指标。

### 5.2 无人机之间是否需要通信

多目标中心化阶段 **默认不需要无人机之间直接通信**。目标机和拦截机都只与 AirSim/中心节点交互，拦截机只执行中心节点下发的任务。

推荐通信关系：

```text
Target UAVs -> AirSim -> C2 Node
Interceptor UAVs -> AirSim -> C2 Node
C2 Node -> AirSim -> Interceptor UAVs
```

多目标阶段可对比三种通信模式：

| 通信模式 | 特点 | 适用阶段 |
|---|---|---|
| 中心化通信 | 所有无人机只和 C2 通信，C2 做全局分配 | 推荐主线 |
| 分布式通信 | 无人机之间交换状态、意图和任务 | 多机协同研究 |
| 混合通信 | C2 给全局任务，无人机局部避碰/协同 | 工程上更均衡 |

推荐演进路线：

1. 已完成单目标单拦截机：无机间通信。
2. 多目标多拦截机主线：中心节点统一分配，无机间通信。
3. 多拦截机局部避碰：拦截机广播自身位置、速度和当前任务 ID。
4. 通信受限研究：加入机间通信和分布式任务分配。
5. 抗通信丢包研究：加入延迟、丢包、断链和局部自治。

是否需要无人机间通信的结论：

- **做中心化多目标分配**：不需要机间通信。
- **做分布式分配/拍卖/CBBA**：需要机间通信。
- **做局部避碰**：可以不需要，但加入机间广播会更自然。
- **做通信受限鲁棒性论文点**：需要把机间通信建模为实验变量。

### 5.3 推荐消息流

核心消息流如下：

```text
AirSim State
  -> Radar Simulator
  -> SensorTrack
  -> Track Fusion
  -> FusedTrack
  -> Assignment
  -> Guidance
  -> GuidanceCommand
  -> AirSim Control
```

如果加入视觉：

```text
AirSim Image
  -> Vision Detector
  -> VisionDetection
  -> Registration / Fusion
  -> FusedTrack
```

如果加入多拦截机：

```text
InterceptorState[]
  -> Assignment
  -> AssignmentResult[]
  -> GuidanceCommand[]
```

多机状态广播可选消息流：

```text
InterceptorState[i]
  -> C2 Node
  -> InterceptorStateBroadcast
  -> Interceptor[j] local deconfliction
```

### 5.4 推荐通信协议

当前多目标阶段可先使用 Python 进程内对象或队列，降低系统复杂度。若需要模块解耦，推荐 ROS 2。

| 方案 | 优点 | 缺点 | 建议 |
|---|---|---|---|
| Python 单进程 | 最简单，调试方便，可复现实验 | 模块边界弱 | 多目标理想闭环推荐 |
| Python 多进程 + Queue | 接近真实模块分离 | 调试复杂度增加 | 第 2 阶段可用 |
| ROS 2 Topic/Service | 消息清晰，适合多模块和后续迁移 | 初期工程成本高 | 第 3 阶段推荐 |
| gRPC/ZeroMQ | 跨语言和分布式友好 | 需自定义协议 | 后续扩展 |

推荐 ROS 2 topic 设计：

```text
/radar/tracks
/vision/detections
/uav/interceptor/state
/uav/target/state
/tracks/fused
/mission/assignments
/guidance/commands
/episode/events
/episode/metrics
```

### 5.5 消息数据结构

建议核心消息如下：

```text
SensorTrack
- timestamp
- sensor_id
- local_track_id
- measurement_id
- position_ned
- velocity_ned
- covariance
- confidence
- class_hint
```

```text
VisionDetection
- timestamp
- camera_id
- detection_id
- bbox
- class_label
- confidence
- bearing_world
- associated_track_id
```

```text
FusedTrack
- timestamp
- global_track_id
- truth_id(optional, only for evaluation)
- position_ned
- velocity_ned
- covariance
- classification
- confidence
- track_status
```

```text
InterceptorState
- timestamp
- interceptor_id
- position_ned
- velocity_ned
- heading
- available
- energy_proxy
- assigned_target_id
- current_task_status
```

```text
AssignmentResult
- timestamp
- assignment_id
- interceptor_id
- target_track_id
- task_type
- priority
- valid_until
- assignment_cost
```

```text
GuidanceCommand
- timestamp
- interceptor_id
- target_track_id
- guidance_mode
- velocity_command
- position_setpoint
- command_limits
- abort_condition
```

多目标系统中建议中心节点按批处理发布：

```text
SensorTrackArray
VisionDetectionArray
FusedTrackArray
InterceptorStateArray
AssignmentResultArray
GuidanceCommandArray
```

批处理的好处是同一仿真步内的目标集合一致，避免一架拦截机基于旧航迹、另一架基于新航迹做出互相冲突的决策。

## 6. 目标分配设计

单目标单拦截机场景已经跑通，后续只作为 baseline。当前主线是多入侵目标 vs 多拦截机，目标分配需要解决 4 个问题：

1. 哪些目标值得拦截。
2. 哪些拦截机可用。
3. 哪架拦截机拦截哪个目标总代价最低。
4. 如何避免多架拦截机重复追击同一目标或轨迹冲突。

推荐默认方案：**中心节点统一维护目标表和拦截机表，每个决策周期运行一次 Hungarian 分配**。单目标固定规则仅保留为 baseline，不再作为主线。

### 6.1 目标状态分级

融合航迹建议分为 4 类状态：

| 状态 | 含义 | 动作 |
|---|---|---|
| tentative | 新出现但未确认 | 继续观测，不分配 |
| confirmed | 连续多帧稳定存在 | 可分配拦截 |
| lost | 短时间未更新 | 保持预测，暂不新分配 |
| dropped | 超时未恢复 | 删除航迹 |

推荐确认规则：

```text
连续 3 帧被雷达探测到，或雷达 + 图像同时确认 -> confirmed
超过 1-3 s 未更新 -> lost
超过 3-5 s 未更新 -> dropped
```

### 6.2 多目标分配流程

每个分配周期执行：

```text
输入：
- FusedTrackArray
- InterceptorStateArray
- 当前 AssignmentResultArray

步骤：
1. 筛选 confirmed 目标，剔除 lost/dropped 目标。
2. 筛选 available 拦截机，剔除失效、越界、能量不足或已命中的拦截机。
3. 计算每个 interceptor-target 对的可行性。
4. 对不可行组合赋予 infinite cost。
5. 构建代价矩阵 cost[i, j]。
6. 使用 Hungarian 得到一对一匹配。
7. 对未匹配目标按威胁等级进入等待队列。
8. 对未匹配拦截机进入待命、巡逻或补位状态。
9. 发布 AssignmentResultArray。
```

可行性判断建议包含：

```text
预计拦截时间 < 最大允许时间
拦截机能量余量 > 最小阈值
目标航迹置信度 > 最小阈值
拦截路径不穿越禁区
拦截机之间最小间隔可满足
```

### 6.3 多目标多拦截机代价函数

中心节点构建代价矩阵：

```text
cost[i, j] = w1 * time_to_intercept
           + w2 * distance
           + w3 * energy_cost
           + w4 * target_priority_penalty
           + w5 * track_uncertainty
           + w6 * heading_change_cost
           + w7 * conflict_risk
```

其中：

- `i` 是拦截机。
- `j` 是目标航迹。
- `time_to_intercept` 可用相对距离除以闭合速度估计。
- `energy_cost` 用路径长度或速度变化近似。
- `target_priority_penalty` 由目标威胁等级决定。
- `track_uncertainty` 来自融合协方差。
- `heading_change_cost` 避免频繁大角度重规划。
- `conflict_risk` 惩罚与其他拦截机预测轨迹过近的分配。

目标威胁等级可按以下因素计算：

```text
threat = a1 * protected_zone_proximity
       + a2 * target_speed_toward_zone
       + a3 * target_class_confidence
       + a4 * time_to_reach_zone_inverse
```

拦截时间估计可先用简化闭合速度：

```text
time_to_intercept = relative_distance / max(closing_speed, min_closing_speed)
```

若目标机动强，后续可用短时轨迹预测或采样法估计拦截时间。

### 6.4 分配算法对比

| 算法 | 优点 | 缺点 | 推荐用途 |
|---|---|---|---|
| 固定规则 | 简单可靠 | 不能处理多目标最优性 | 已完成单目标 baseline |
| 最近邻 | 实现简单 | 容易局部最优 | 多目标 baseline |
| Hungarian | 全局最优匹配，成熟稳定 | 需要中心节点和代价矩阵 | 当前推荐主线 |
| 拍卖算法 | 分布式友好 | 参数和收敛需要调试 | 通信受限研究 |
| CBBA | 适合多智能体任务规划 | 实现复杂 | 后续科研扩展 |

推荐路线：

```text
最近邻 baseline -> Hungarian 主线 -> 拍卖/CBBA 对照
```

### 6.5 重分配策略

以下情况需要触发重分配：

- 目标航迹变为 `lost` 或 `dropped`。
- 拦截机失效、越界或能量不足。
- 新目标威胁等级更高。
- 当前拦截预计无法在限定时间内完成。
- 多架拦截机同时追踪同一低优先级目标。

为避免频繁抖动，建议加入重分配迟滞：

```text
只有当新分配代价比当前分配低 20% 以上，或当前任务不可行时，才切换任务。
```

### 6.6 多拦截机冲突消解

多目标对多拦截机时，目标分配不够，还需要处理拦截机之间的空间冲突。推荐先在中心节点做预测冲突检测：

```text
对每架拦截机预测未来 T 秒轨迹
若任意两架拦截机距离小于 separation_min
则提高对应 assignment 的 conflict_risk
必要时让低优先级拦截机延迟启动或改飞中间等待点
```

推荐默认参数：

```text
prediction_horizon = 3-5 s
separation_min = 仿真安全间隔，可按机体包围球半径放大 3-5 倍
deconfliction_policy = priority_yield
```

冲突消解策略对比：

| 策略 | 说明 | 建议 |
|---|---|---|
| 中心节点重规划 | C2 修改任务或路径 | 多目标主线推荐 |
| 优先级让行 | 低优先级拦截机减速或等待 | 简单可靠 |
| 局部避碰 | 拦截机本地根据邻机状态避让 | 后续混合通信方案 |
| 分布式协同 | 拦截机之间协商任务和路径 | 后续科研扩展 |

### 6.7 目标数量与拦截机数量不等

需要明确三种情况：

| 情况 | 策略 |
|---|---|
| 目标数 = 拦截机数 | Hungarian 一对一分配 |
| 目标数 > 拦截机数 | 按威胁等级和代价选择前 N 个目标，其余进入等待队列 |
| 目标数 < 拦截机数 | 多余拦截机待命、巡逻或作为备份拦截机 |

如果允许多架拦截机协同拦截一个高威胁目标，可作为后续扩展，不建议当前阶段加入。当前阶段默认 **一架拦截机最多追一个目标，一个目标最多分配一架拦截机**。

## 7. 地面雷达仿真

当前多目标阶段采用“AirSim 真值 + 噪声”的雷达模型，不做高保真电磁仿真。

雷达输出建议包含：

```text
timestamp
target_id
range
azimuth
elevation
radial_velocity
position_estimate
velocity_estimate
covariance
confidence
```

可配置参数：

- 探测距离上限。
- 水平和俯仰视场。
- 测距噪声。
- 测角噪声。
- 测速噪声。
- 固定延迟或随机延迟。
- 漏检概率。
- 虚警概率。
- 多目标分辨率阈值：两个目标角距离或空间距离过近时，雷达可合并为一个观测。
- 最大同时航迹数：模拟雷达处理能力上限。

雷达模型演进路线：

| 模型 | 特点 | 推荐阶段 |
|---|---|---|
| 理想真值 | 无噪声，验证算法闭环 | 第 0 阶段 |
| 真值加高斯噪声 | 实用、可控，便于消融实验 | 第 1 阶段 |
| 加漏检、虚警和延迟 | 更接近真实系统 | 第 2 阶段 |
| 加目标合并/分裂 | 检验多目标配准和 ID switch | 多目标阶段推荐 |
| 微多普勒或电磁仿真 | 科研价值高但复杂 | 后续专题研究 |

## 8. 图像识别方案

图像识别建议分三步实施：

| 阶段 | 方法 | 目的 |
|---|---|---|
| A | AirSim segmentation 真值 | 快速得到目标框，验证闭环 |
| B | 合成图像训练检测器 | 验证视觉识别鲁棒性 |
| C | 真实或公开数据微调 | 提升真实迁移能力 |

当前多目标阶段视觉模块重点验证：

- 雷达 cue 相机是否能把目标带入视场。
- 图像目标框能否修正雷达航迹。
- 目标短时遮挡后能否恢复跟踪。
- 不同光照、背景和距离下检测性能变化。

检测指标：

- Precision / Recall。
- 目标框 IoU。
- 检测延迟。
- 目标丢失率。
- 雷达引导后目标进入画面的成功率。

## 9. 导引算法方案

| 算法 | 优点 | 缺点 | 建议 |
|---|---|---|---|
| 纯追踪 Pure Pursuit | 简单、稳定、容易调试 | 拦截路径长，容易尾追 | 作为 baseline |
| 比例导引 PN | 拦截效率高，适合机动目标 | 对观测误差和控制限制敏感 | 当前多目标阶段重点算法 |
| 预测拦截点 | 直观，适合匀速目标 | 目标机动时误差大 | 与 PN 对比 |
| MPC | 可加入约束和优化目标 | 建模和计算复杂 | 后续增强 |
| 强化学习 | 可能适应复杂场景 | 训练成本高，可解释性弱 | 不建议当前主线 |

推荐实验组合：

1. Pure Pursuit 作为基线。
2. PN 作为主算法。
3. 预测拦截作为工程对照。
4. 后续再加入 MPC 或强化学习方法。

导引输出仅用于 AirSim 虚拟控制，不设计真实飞控参数。

## 10. 虚拟撞击毁伤模型

建议采用三层命中判定，逐步增强。

### 方案 A：碰撞事件判定

使用 AirSim 返回的 collision info。若拦截机与目标机发生碰撞，则判定目标失效。

优点：简单直接。  
缺点：多机碰撞可靠性受模型碰撞体设置影响。

### 方案 B：距离阈值判定

若两机距离小于目标包围球半径之和，则判定命中。

优点：稳定、可控、适合科研复现。  
缺点：不是高保真碰撞物理。

### 方案 C：相对速度和命中角度评分

在距离阈值基础上加入相对速度、交会角和接触位置，计算虚拟毁伤分数。

优点：更适合论文分析。  
缺点：参数假设更多。

当前多目标阶段推荐使用 **方案 A + 方案 B 双判定**。如果 AirSim collision 不可靠，则以距离阈值作为主判据。

输出指标：

```text
hit_success
collision_detected
minimum_distance
relative_speed_at_hit
intercept_time
target_disabled_time
episode_end_reason
```

## 11. 实验设计

建议至少设计 8 类多目标实验：

1. **多目标理想闭环实验**：无噪声、无延迟，验证多架拦截机能否完成一对一命中。
2. **目标数量扫描实验**：设置 `M` 个入侵目标、`N` 架拦截机，测试 `M<N`、`M=N`、`M>N` 三种资源关系。
3. **交叉航迹实验**：多个目标近距离交会或交叉飞行，评估目标配准和 ID switch。
4. **雷达误差实验**：逐步增加测距、测角、测速误差和目标合并概率，观察命中率变化。
5. **延迟实验**：加入传感器延迟、中心节点处理延迟和通信延迟，评估分配稳定性和 PN 稳定性。
6. **目标机动实验**：目标执行直线、转弯、蛇形、爬升、下降和分散突防轨迹。
7. **视觉辅助实验**：对比仅雷达和雷达加图像修正的航迹稳定性、ID switch 和命中率。
8. **分配算法对比实验**：比较最近邻、Hungarian、拍卖算法或 CBBA 在多目标条件下的效果。

推荐实验矩阵：

| 维度 | 建议取值 |
|---|---|
| 入侵目标数 M | 2, 4, 6, 8 |
| 拦截机数 N | 2, 4, 6 |
| 目标轨迹 | 平行、交叉、分散、集群、随机机动 |
| 传感器条件 | 理想、噪声、漏检、延迟、目标合并 |
| 通信条件 | 无延迟、固定延迟、随机延迟、丢包 |
| 分配算法 | 最近邻、Hungarian、拍卖/CBBA |

## 12. 评价指标

核心指标：

- 命中率。
- 多目标总体拦截完成率。
- 单目标平均命中率和最差目标命中率。
- 平均拦截时间。
- 最小接近距离。
- 轨迹长度。
- 控制指令平滑性。
- 目标航迹 RMSE。
- 目标丢失次数。
- ID switch 次数。
- 重复分配次数。
- 未分配高威胁目标数量。
- 重分配次数和重分配成功率。
- 拦截机间最小间隔。
- 任务冲突次数。
- 传感器延迟敏感性。
- 不同初始条件下的成功率分布。

论文表格建议：

| 分配算法 | 导引算法 | 总体完成率 | 平均拦截时间 | ID switch | 重复分配 | 最小机间距离 |
|---|---|---:|---:|---:|---:|---:|
| 最近邻 | PN | | | | | |
| Hungarian | PN | | | | | |
| 拍卖/CBBA | PN | | | | | |

## 13. 实施阶段

### 阶段 0：单目标基线

已完成单目标、单拦截机闭环，保留为回归测试和算法 baseline。

### 阶段 1：多机 AirSim 基础场景

完成多架入侵目标、多架拦截机启动、目标轨迹生成、拦截机控制、状态读取和多目标命中/失效判定。

### 阶段 2：多目标理想探测与中心节点闭环

直接使用 AirSim 真值或理想雷达观测，建立中心节点消息流、FusedTrackArray、AssignmentResultArray 和 GuidanceCommandArray，跑通最近邻与 Hungarian 分配。

### 阶段 3：多目标雷达仿真与配准闭环

加入雷达噪声、延迟、漏检、虚警、目标合并和目标分裂，用 GNN/Hungarian 数据关联加 EKF/UKF 输出多目标融合航迹。

### 阶段 4：多目标视觉辅助闭环

加入 AirSim 图像，先用 segmentation 真值，后续替换为检测模型，重点验证图像辅助能否降低 ID switch 和错误分配。

### 阶段 5：系统性多目标实验

批量随机 episode，输出统计结果、轨迹图、消融实验、分配算法对比和通信延迟/丢包敏感性。

### 阶段 6：分布式通信与协同扩展

在中心化 Hungarian 主线稳定后，扩展机间通信、分布式拍卖/CBBA、局部避碰、MPC/强化学习和复杂城市或山区场景。

## 14. 最终推荐配置

当前多目标阶段推荐配置：

```text
平台：经典 AirSim
场景：多入侵目标 + 多拦截机 + 地面雷达站
探测：AirSim 真值/理想雷达起步，逐步加入雷达噪声、漏检、虚警和目标合并
识别：先用 segmentation 真值，后续 YOLO 类检测器
融合：GNN/Hungarian 数据关联 + 每目标 EKF / UKF
通信：中心节点统一调度，默认无无人机间直接通信
分配：最近邻 baseline + Hungarian 主线，拍卖/CBBA 作为后续对照
导引：PN 主算法，Pure Pursuit 和预测拦截作为导引 baseline
命中：AirSim collision + 距离阈值双判定
评估：批量 episode + 固定随机种子 + 多目标完成率 + ID switch + 重复分配 + 冲突次数
```

该方案以已跑通的单目标闭环为 baseline，重点转向多目标配准、多目标分配、多拦截机冲突消解和通信约束下的任务协同。
