# 当前主流反无人机体系方案与难点解法

**用途**: 学术研究、体系工程论证、方案评审  
**边界**: 本文聚焦探测融合、目标关联、资源分配、通信韧性和人机授权边界；不展开真实火控参数、毁伤参数、实装控制律或绕过人工授权的自主处置流程。

---

## 一、摘要

当前学术界和工业界的共识是：反无人机体系不是单一传感器或单一拦截器问题，而是一个“多传感器探测、统一航迹融合、多目标关联、资源分配、分布式降级、人机授权”的系统工程问题。

适合当前方案的默认架构为：

```text
中心节点主控
+ 地面雷达主定位
+ 声学低空辅助
+ 高空系留侦察无人机作为二级区域节点，提供补盲、视频/图像cue和局部协调备份
+ 拦截资源机载相机局部确认
+ 拦截无人机、二级节点和中心节点之间存在仿真数据通信
+ 分布式节点作为中心/二级节点不可用后的保底能力
```

核心原则：

1. 雷达给出的不是目标真值，而是带延迟和协方差的航迹。
2. 视觉观测不能直接改任务，只能作为 `GlobalTrack` 的观测源。
3. 5对5目标分配应由中心节点统一完成，避免“看到谁就追谁”。
4. 高空系留侦察无人机在健康状态下是补盲、ID稳定器和区域图像 cue 提供者；中心节点失效时可作为二级区域协调节点，但不是与中心并列的常态全局指挥中心。
5. 中心节点仍在线但计划可靠性下降时，允许根据定位不确定度、关联风险、分配新鲜度和末端视觉一致性触发主动降级仲裁。
6. 二级节点不可用或覆盖不足时，分布式自治只承担保底态势维护和任务协商。

---

## 二、学术界与工业界主流路线

| 方向 | 主流路线 | 说明 |
|------|----------|------|
| 探测 | 雷达、RF、EO/IR、声学组合 | 单一传感器难以覆盖全部高度、天气、距离和目标类型 |
| 融合 | Kalman/EKF/UKF/IMM + 数据关联 | 雷达等传感器输出需转换为统一航迹 |
| 多目标关联 | GNN/Hungarian、JPDA、MHT | 工程上先用GNN/Hungarian，密集交叉场景再升级 |
| 资源分配 | Hungarian、最小费用流、滚动窗口优化 | 中心化情况下成熟稳定 |
| 分布式协同 | 拍卖算法、CBBA、一致性协商 | 适合通信受限或中心失效后的降级模式 |
| 工业系统 | 传感器融合 + C2态势 + 分层处置 | Anduril、Dedrone、DroneShield、Fortem 等方案均强调融合与C2 |
| 接口标准 | SAPIENT 等开放架构 | 传感器、C2、决策模块标准化互联，降低集成成本 |

### 2.1 已形成共识的默认基线

以下方案可作为当前系统设计的“默认基线”。除非后续实验或工程约束证明不适用，否则不建议一开始替换为更复杂路线。

| 问题 | 共识型默认方案 | 采用方式 |
|------|----------------|----------|
| 单目标拦截导引 | PN比例导引 | 默认主算法 |
| 单目标追踪对照 | Pure Pursuit | baseline，用于对比PN |
| 末端目标确认 | 视觉伺服/LOS角速率跟踪 | 用于保持目标在视场内和确认身份 |
| 单目标航迹滤波 | EKF/UKF | 默认航迹估计 |
| 机动目标航迹 | IMM-EKF/UKF | 目标机动明显时升级 |
| 多目标数据关联 | GNN/Hungarian | 当前多目标主线 |
| 密集目标关联 | JPDA/MHT | 交叉密集、ID切换严重时升级 |
| 中心化资源分配 | Hungarian/最小费用流 | 中心节点存在时默认 |
| 分布式资源分配 | 拍卖算法/CBBA | 中心失效或通信受限时降级 |
| 探测融合 | 雷达主定位 + 光电确认 + 声学辅助 | 工业界C-UAS常见形态 |
| 航迹表达 | 位置 + 速度 + 协方差 + 置信度 | 不把传感器点位当真值 |
| 安全边界 | 低置信度继续观测/请求确认 | 不确定目标不升级 |

可固定写入系统方案的结论：

```text
单目标导引采用PN，Pure Pursuit作为对照；
多目标航迹采用EKF/UKF + GNN/Hungarian；
多资源分配在中心节点下采用Hungarian/最小费用流；
中心失效后采用备份节点接管，必要时降级为拍卖/CBBA；
探测融合采用雷达主定位、光电确认、声学辅助、侦察无人机补盲；
所有传感器观测统一进入GlobalTrack，不允许局部相机检测直接改写任务分配。
```

参考资料：

- FAA UAS Detection Technical Considerations: <https://www.faa.gov/sites/faa.gov/files/airports/airport_safety/Attachment-3-UAS-Detection-Technical-Considerations.pdf>
- JRC C-UAS report: <https://publications.jrc.ec.europa.eu/repository/handle/JRC140692>
- Dstl SAPIENT / NATO trials: <https://www.gov.uk/government/news/nato-trials-dstl-standard-for-counter-drone-systems>
- MIT CBBA: <https://acl.mit.edu/projects/consensus-based-bundle-algorithm>
- Anduril Lattice: <https://www.anduril.com/lattice/>
- Dedrone: <https://www.dedrone.com/>
- DroneShield: <https://www.droneshield.com/>
- Fortem DroneHunter: <https://www.fortemtech.com/products/dronehunter-f700/>

### 2.2 共识算法的开源实现与可选方案

以下清单用于科研验证、仿真评估和后续工程拆解。Web of Science 和 Google Scholar 更适合论文检索，不适合作为代码实现的稳定来源；可复现实验优先参考 GitHub、arXiv、官方文档和项目主页。

成熟度标记：

```text
A = 框架成熟、文档较完整，适合作为主验证平台
B = 研究/工程原型，适合复现实验或二次封装
C = 单点示例或小型项目，只适合作为公式和思路参考
```

#### 2.2.1 核心共识算法的主流开源实现

| 模块 | 推荐实现 | 成熟度 | 适用方式 |
|------|----------|--------|----------|
| 多目标航迹滤波与关联 | Stone Soup: <https://github.com/dstl/Stone-Soup> | A | 中心节点的多目标跟踪、数据关联、航迹融合验证平台 |
| EKF/UKF 教学与快速原型 | FilterPy: <https://github.com/rlabbe/filterpy> | A/B | 快速验证EKF、UKF、IMM思路；不直接作为高频嵌入式库 |
| 机载状态估计 | PX4-Autopilot EKF2: <https://github.com/PX4/PX4-Autopilot> | A | 单机姿态、速度、本机状态估计；不承担全局多目标C2融合 |
| PX4旧版滤波库 | PX4-ECL: <https://github.com/PX4/PX4-ECL> | B | 已归档，作为EKF2历史实现参考；新项目应优先看PX4-Autopilot |
| GNN/Hungarian分配 | SciPy `linear_sum_assignment`: <https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.linear_sum_assignment.html> | A | 中心化5对5目标分配和观测-航迹硬关联基线 |
| 复杂约束分配 | Google OR-Tools Min Cost Flow: <https://developers.google.com/optimization/flow/assignment_min_cost_flow> | A | 多轮拦截、资源容量、禁配约束、任务窗口约束 |
| Pure Pursuit | PythonRobotics Pure Pursuit: <https://github.com/AtsushiSakai/PythonRobotics/blob/master/PathTracking/pure_pursuit/pure_pursuit.py> | A/B | 低速追踪baseline；用于与PN对比 |
| PN比例导引公式验证 | propNav: <https://github.com/gedeschaines/propNav>；PN Python示例: <https://github.com/alti3/missile-proportional-navigation-python> | B/C | 只作为运动学仿真和公式核对来源，不直接移植为实装控制律 |
| 改进PN/FRPN研究 | FRPN论文: <https://arxiv.org/abs/2405.13542> | B | 高机动目标的研究对照；当前更适合作为仿真算法候选 |
| 视觉伺服与视觉跟踪 | ViSP: <https://github.com/lagadic/visp>；ROS接口: <https://github.com/lagadic/vision_visp> | A | 末端视觉确认、视场保持、目标重捕获实验 |
| 图像多目标跟踪MOT | ByteTrack: <https://github.com/FoundationVision/ByteTrack>；Deep SORT: <https://github.com/nwojke/deep_sort>；BoT-SORT: <https://github.com/NirAharon/BoT-SORT>；SORT: <https://github.com/abewley/sort> | A/B | 末端视场内多个视觉目标的局部编号、短时轨迹和ID Switch评估 |
| 相机配准与投影 | OpenCV Camera Calibration: <https://docs.opencv.org/4.x/dc/dbb/tutorial_py_calibration.html>；OpenCV solvePnP: <https://docs.opencv.org/4.x/d5/d1f/calib3d_solvePnP.html> | A | 将全局航迹预测投影到相机平面，建立图像检测与`GlobalTrack`的几何门限 |
| 坐标与时间同步 | ROS 2 tf2: <https://docs.ros.org/en/rolling/Concepts/Intermediate/About-Tf2.html>；message_filters: <https://docs.ros.org/en/humble/p/message_filters/doc/Tutorials/Approximate-Synchronizer-Cpp.html> | A | 维护世界系、机体系、相机系转换；对齐雷达、相机、侦察无人机和本机状态时间戳 |
| 分布式任务分配 | MIT CBBA项目页: <https://acl.mit.edu/projects/consensus-based-bundle-algorithm> | A | 理论和算法基准，适合作为分布式降级方案依据 |
| CBBA开源原型 | CBBA-Python: <https://github.com/zehuilu/CBBA-Python>；通信受限示例: <https://github.com/keep9oing/consensus-based-bundle-algorithm>；CA-CBBA: <https://github.com/mit-acl/CACBBA> | B | Mesh低带宽协商、中心失效后的分布式保底验证 |
| 轨迹到轨迹融合 | Stone Soup Track Fusion: <https://stonesoup.readthedocs.io/en/latest/auto_examples/> | A | 多雷达、多光电或侦察无人机输出航迹时做协方差交叉/轨迹融合 |
| 雷达-相机融合资料 | Awesome Radar-Camera Fusion: <https://github.com/Radar-Camera-Fusion/Awesome-Radar-Camera-Fusion> | B | 借鉴多传感器标定、时空对齐、特征融合思路 |
| 友方协同身份认证 | FAA Remote ID: <https://www.faa.gov/uas/getting_started/remote_id>；OpenDroneID: <https://github.com/opendroneid/opendroneid-core-c>；MAVLink signing: <https://mavlink.io/en/guide/message_signing.html>；ROS 2 DDS Security: <https://design.ros2.org/articles/ros2_dds_security.html> | A/B | 用于确认己方/协同方身份和消息来源；不用于把未知目标自动判定为可处置目标 |
| 视觉友方标识 | AprilTag: <https://github.com/AprilRobotics/apriltag> | B | 实验室、近距、合作目标的视觉ID辅助；真实复杂背景下只能作为辅助证据 |
| 多智能体仿真扩展 | SCRIMMAGE: <https://github.com/gtri/scrimmage> | B | AirSim在多机通信、任务分配或大规模对抗仿真上受限时的备选平台 |

推荐落地组合：

```text
中心C2验证：Stone Soup + SciPy + OR-Tools
快速滤波原型：FilterPy
单机状态估计参考：PX4-Autopilot EKF2
末端视觉验证：ViSP / vision_visp
末端MOT验证：ByteTrack / BoT-SORT / Deep SORT
图像-航迹配准：OpenCV calibration / solvePnP + ROS 2 tf2
友方身份认证：Remote ID / OpenDroneID / MAVLink signing / DDS Security
低速追踪baseline：PythonRobotics Pure Pursuit
PN公式核对：propNav / PN Python示例 / FRPN论文
分布式降级验证：CBBA-Python / CA-CBBA
多机规模扩展：AirSim优先，必要时评估SCRIMMAGE
```

注意：`PythonRobotics`适合作为Pure Pursuit和机器人路径跟踪参考；PN建议使用专门PN示例或论文公式核对。`PX4-ECL`已归档，工程参考应迁移到`PX4-Autopilot`中的EKF2实现。未核实或维护状态不清的仓库不应写入主线依赖。

#### 2.2.2 尚未达成绝对共识的进阶方案

| 问题 | 可选方案 | 开源/资料 | 选择建议 |
|------|----------|-----------|----------|
| 密集目标交叉后的ID保持 | JPDA | Stone Soup JPDA教程: <https://stonesoup.readthedocs.io/en/latest/auto_tutorials/08_JPDATutorial.html> | 5对5编队交叉时优先于GNN；算力和内存可控 |
| 高杂波、多扫描关联 | MHT | Stone Soup MHT示例: <https://stonesoup.readthedocs.io/en/v1.4/auto_examples/dataassociation/mht_example.html>；pymht: <https://github.com/yoon28/pymht>；C++ MHT: <https://github.com/PrinceVictor/MHT> | 只建议中心节点或离线评估使用；资源节点不跑MHT |
| 高机动目标导引 | 改进PN/FRPN | FRPN论文、PN小型实现 | 作为PN增强路线，工程代价低于MPC |
| 约束强的制导/轨迹控制 | MPC/NMPC | ETH-ASL `mav_control_rw`: <https://github.com/ethz-asl/mav_control_rw>；do-mpc: <https://github.com/do-mpc/do-mpc> | 有严格推力、倾角、避障或延迟约束时考虑；移植成本高 |
| 全中心化 vs 全分布式 | 中心化主控 + CBBA降级 | MIT CBBA、CBBA-Python、CA-CBBA | 正常态不建议全分布式；中心失效后用分布式保底 |
| 视觉深度学习关联 | ReID/深度MOT | 可参考通用MOT项目，但不作为主线 | 小目标、遮挡和跨视角一致性不稳定；应先建立几何/航迹关联 |
| 声学主定位 | 声阵列TDOA/DOA | 多为特定硬件工程项目 | 只作为低空告警、粗方位和类别辅助，不建议主导全局定位 |

选择顺序建议：

```text
目标稀疏：EKF/UKF + GNN/Hungarian
目标交叉：EKF/UKF/IMM + JPDA
强杂波且中心算力充足：MHT离线或中心节点验证
单目标默认：PN
目标机动明显：改进PN/FRPN
约束极强且算力充足：MPC/NMPC
中心正常：Hungarian/最小费用流
中心失效：备份节点 -> CBBA/拍卖 -> 局部保守策略
```

#### 2.2.3 针对当前5对5场景的推荐技术栈

当前阶段建议固定为“共识主线 + 可插拔进阶算法”：

1. 中心节点维护`GlobalTrack`，用Stone Soup验证EKF/UKF、GNN、JPDA、MHT等关联器。
2. 5对5资源分配先用SciPy Hungarian，复杂约束再升级OR-Tools最小费用流。
3. 每架资源节点只接收`AssignmentPlan`和目标航迹摘要，不直接用局部相机检测改写全局分配。
4. 资源节点相机只输出`LocalObservation`：相对方位、置信度、时间戳、候选`global_track_id`。
5. 中心失效时，先由备份节点接管；无备份时再启用CBBA/拍卖式任务协商。
6. 侦察无人机只承担补盲、ID稳定和轨迹交接辅助，不作为第二套独立分配中心。

接口边界建议：

```text
SensorObservation -> FusionAdapter -> GlobalTrack
GlobalTrack + ResourceState -> AssignmentPlanner -> AssignmentPlan
AssignmentPlan -> ResourceNode
ResourceNode -> LocalObservation / ResourceState
DistributedFallback -> BidState / TrackSummary / ResourceSummary
```

不建议把开源PN、MPC或MHT示例直接接入实机闭环。正确用法是：先在合成数据和仿真数据上验证误差、ID Switch、延迟鲁棒性和任务重分配稳定性，再决定是否进入工程化重写。

#### 2.2.4 后续代码生成提示词边界

如后续需要生成代码，提示词应限定在科研仿真、算法评估和接口脚手架范围内，不生成真实火控参数、毁伤逻辑、绕过人工授权的处置流程或可直接部署的实装控制律。

可用提示词模板：

```text
请为科研仿真项目生成一个中心节点多目标跟踪模块骨架。
输入为合成SensorObservation序列，输出为GlobalTrack列表。
实现范围仅限EKF/UKF接口、GNN/Hungarian关联接口、JPDA可插拔接口和日志记录。
不要生成真实传感器驱动、实机飞控接口、毁伤逻辑或自动处置流程。
```

```text
请生成一个5对5资源分配评估脚手架。
输入为GlobalTrack和ResourceState的离线JSON样例，输出AssignmentPlan。
先实现Hungarian代价矩阵和可解释日志，预留OR-Tools最小费用流接口。
代码仅用于仿真评估，不生成飞控指令、目标打击参数或硬件部署配置。
```

```text
请生成一个分布式降级任务协商仿真脚手架。
使用CBBA/拍卖算法思想，节点只交换TrackSummary、ResourceSummary和BidState。
模拟通信丢包、延迟和中心节点失效后的任务重分配。
不要包含真实通信频点、加密绕过、武器控制或自主处置授权逻辑。
```

---

## 三、核心难点与推荐方案

### 3.0 单目标拦截的共识基线

**共识**: 单目标拦截导引优先采用 PN 比例导引，Pure Pursuit 作为最小基线，末端使用视觉伺服或LOS角速率跟踪完成目标确认与视场保持。

推荐分层：

| 阶段 | 默认方案 | 说明 |
|------|----------|------|
| 基线对照 | Pure Pursuit | 简单、可解释、用于验证系统闭环 |
| 主导引 | PN比例导引 | 成熟、计算轻、拦截效率通常优于纯追踪 |
| 增强导引 | 改进PN/FRPN | 目标机动明显或视场约束明显时考虑 |
| 末端确认 | 视觉伺服/LOS角速率跟踪 | 不替代中心航迹，只做局部确认和视场保持 |

单目标链路建议：

```text
雷达/融合航迹给出目标预测状态
-> 资源节点飞向PredictedInterceptVolume
-> PN根据相对位置和视线变化生成接近方向
-> 机载相机进入视场后做视觉确认
-> 若视觉确认失败，回退到中心航迹/侦察无人机辅助确认
```

PN 是默认主线，但不应让PN绕过航迹置信度、视场确认和授权状态。PN解决的是“怎么接近目标”，不是“目标是谁、是否可以处置”。

### 3.1 雷达定位精度不是固定值

**难点**: 雷达定位质量随距离、高度、遮挡、杂波、目标密度和扫描周期变化，不能写成固定精度。

**主流做法**: 用协方差表达航迹质量。

**推荐方案**:

```text
GlobalTrack
- position
- velocity
- covariance
- confidence
- track_state
```

航迹质量分为：

| 等级 | 含义 | 可执行动作 |
|------|------|------------|
| coarse_track | 只知道大致区域和方向 | 预警、扇区指向、资源预备 |
| stable_track | 位置和速度连续稳定 | 资源分配、航迹预测、接近点生成 |
| handover_track | 位置、速度、类别、ID均较稳定 | 允许交接给光电或机载相机确认 |

### 3.2 雷达延迟导致追旧点

**难点**: 雷达观测到达中心节点时已经过期，资源节点若追逐上一帧点位，会产生系统性偏差。

**主流做法**: 延迟补偿 + 航迹预测。

**推荐方案**:

```text
radar_measurement_time = 雷达实际观测时刻
c2_receive_time = 中心节点收到观测时刻
latency = c2_receive_time - radar_measurement_time
predicted_target_state = track_state_at_measurement_time + velocity_model * latency
```

资源节点不飞向单点，而飞向预测接近区：

```text
PredictedInterceptVolume
- center_position
- velocity_vector
- covariance_ellipsoid
- valid_until
- primary_sensor
- backup_sensor
```

协方差越大，接近区越大，系统越倾向于请求空中侦察无人机、地面光电或声学阵列补充确认。

### 3.3 多目标容易发生ID交换

**难点**: 目标交叉、并行、编队或距离很近时，系统可能把 `T1` 和 `T3` 互换，导致重复分配或漏分配。

**主流做法**: 最近邻作为基线，GNN/Hungarian作为工程主线，密集目标再考虑JPDA/MHT。每条目标航迹默认由EKF/UKF维护，机动目标再升级IMM-EKF/UKF。

**推荐方案**:

| 算法 | 用途 |
|------|------|
| 最近邻 | 快速基线，便于调试 |
| GNN/Hungarian | 当前主线，多目标一对一关联 |
| JPDA | 密集目标和关联不确定性较高时使用 |
| MHT | 小规模高精度研究使用 |
| IMM-EKF/UKF | 目标机动模型变化明显时使用 |

必须记录：

```text
id_switch_count
duplicate_assignment_count
unassigned_high_threat_count
handover_success_rate
```

### 3.4 视觉看到的目标不一定是分配目标

**难点**: 资源节点相机看到一个目标，不代表它就是中心节点分配给该资源的目标。

**主流做法**: 视觉观测只作为融合航迹的观测源，不直接改变任务。

**推荐方案**:

| 状态 | 含义 | 处理 |
|------|------|------|
| in_fov_confirmed | 相机看到目标，且与中心航迹匹配 | 继续跟踪原 `global_track_id` |
| in_fov_unmatched | 相机看到目标，但无法匹配现有航迹 | 上报中心节点，尝试关联或新建 tentative 航迹 |
| out_of_fov_tracked | 相机未看到目标，但中心航迹仍稳定 | 继续飞向预测接近区，请求雷达/侦察无人机/声学更新 |

关联约束：

```text
角度一致性
时间一致性
运动一致性
类别一致性
历史连续性
```

### 3.4.1 末端视场内多目标配准与友方识别

**难点**: 分配完成后，资源节点进入末端视场，画面中可能同时出现多个来袭目标、己方资源节点、侦察无人机或无关飞行物。此时“相机看到的最近目标”不一定是`AssignmentPlan`指定的`global_track_id`。如果局部视觉ID与中心航迹ID绑定错误，就会造成ID Switch、重复拦截、漏拦截或友方安全风险。

**结论**: 这是多目标拦截里的核心难点之一。它不是单纯图像识别问题，而是“中心航迹预测 + 相机几何投影 + 局部MOT + 协同身份认证 + 保守授权”的联合问题。

推荐处理链路：

```text
AssignmentPlan.assigned_global_track_id
-> 中心节点预测目标在资源节点相机时刻的状态和协方差
-> 使用世界系/机体系/相机系转换，把GlobalTrack投影到图像平面
-> 在图像平面生成候选门限区域，而不是全图任意选择目标
-> 局部MOT生成LocalVisualTrack
-> 对LocalVisualTrack和GlobalTrack做代价匹配
-> 匹配唯一且置信度足够时，确认terminal_track_lock
-> 匹配不唯一时，上报ambiguous并请求中心/侦察无人机辅助
```

末端配准代价建议保持可解释：

```text
terminal_association_cost =
    图像平面投影误差
  + 方位角/LOS角速率一致性误差
  + 时间戳延迟惩罚
  + 航迹协方差惩罚
  + 局部MOT历史连续性惩罚
  + 目标类别不一致惩罚
  + 友方身份冲突惩罚
```

可落地默认方案：

| 环节 | 默认方案 | 升级方案 | 说明 |
|------|----------|----------|------|
| 局部视觉多目标跟踪 | ByteTrack/BoT-SORT/Deep SORT | 自定义小目标MOT | 给视场内目标临时编号，评估ID Switch |
| 图像-航迹配准 | OpenCV标定 + tf2坐标变换 + 投影门限 | 联合优化/因子图 | 把`GlobalTrack`预测到图像平面后再关联 |
| 观测-航迹匹配 | Hungarian + 门限拒配 | JPDA/MHT | 多目标密集、遮挡或交叉时升级 |
| 友方识别 | 加密协同ID + 位置航迹一致性 | UWB/视觉标识辅助 | 只能可靠确认友方，不能反向证明“敌方” |
| 不确定处理 | 继续观测/请求确认 | 中心或备份节点重分配 | 不允许局部节点自行改写全局分配 |

友方识别建议采用“正向确认”原则：

```text
friend_confirmed:
  已认证协同消息 + 时间新鲜度有效 + 位置/速度与友方ResourceState一致

friend_possible:
  视觉/航迹与友方资源存在重叠，但认证不足或时间较旧

unknown_non_cooperative:
  未通过友方认证，且与已知友方航迹不重叠

spoof_suspected:
  身份消息与运动状态、位置来源或历史轨迹明显冲突
```

关键边界：

1. `unknown_non_cooperative`不等价于“敌方”，只能表示非协同/未知。
2. 友方认证必须优先使用加密通信、签名遥测、Remote ID/OpenDroneID或任务内协同ID，视觉标签只作辅助。
3. 如果任一友方航迹协方差与末端候选门限重叠，应触发`friend_overlap_abort_or_hold`，进入保守状态。
4. 资源节点可以上报`terminal_track_lock`，但不能因为局部相机看到另一个目标就自行换绑`global_track_id`。
5. 中心失效时，分布式节点只能交换`TrackSummary/ResourceSummary/IdentityClaim`做保守协商，不能绕过授权边界。

推荐数据结构：

```text
LocalVisualTrack
- local_track_id
- sensor_id
- timestamp
- bbox_or_bearing
- bearing_rate
- visual_confidence
- mot_history_length
- candidate_global_track_ids

TerminalAssociation
- resource_id
- assignment_version
- assigned_global_track_id
- local_track_id
- association_confidence
- ambiguity_score
- friend_conflict_state
- decision_state: locked | ambiguous | hold | reacquire

IdentityClaim
- platform_id
- claim_type: cooperative_id | remote_id | visual_tag | operator_tag
- auth_state: verified | stale | unverified | spoof_suspected
- associated_track_id
- timestamp
```

需要记录的指标：

```text
terminal_association_accuracy
terminal_id_switch_count
ambiguous_fov_event_count
friend_overlap_hold_count
wrong_reassignment_count
time_to_terminal_lock
terminal_reacquire_success_rate
```

参考文献与代码：

- ByteTrack, ECCV 2022, multi-object tracking by associating detection boxes: <https://github.com/FoundationVision/ByteTrack>
- Deep SORT, online tracking with deep association metric: <https://github.com/nwojke/deep_sort>
- BoT-SORT, robust MOT baseline: <https://github.com/NirAharon/BoT-SORT>
- SORT, simple online realtime tracking baseline: <https://github.com/abewley/sort>
- OpenCV camera calibration and `solvePnP`: <https://docs.opencv.org/4.x/dc/dbb/tutorial_py_calibration.html>, <https://docs.opencv.org/4.x/d5/d1f/calib3d_solvePnP.html>
- ROS 2 `tf2` and approximate time synchronizer: <https://docs.ros.org/en/rolling/Concepts/Intermediate/About-Tf2.html>, <https://docs.ros.org/en/humble/p/message_filters/doc/Tutorials/Approximate-Synchronizer-Cpp.html>
- Stone Soup JPDA/MHT examples for ambiguous association: <https://stonesoup.readthedocs.io/en/latest/auto_tutorials/08_JPDATutorial.html>, <https://stonesoup.readthedocs.io/en/v1.4/auto_examples/dataassociation/mht_example.html>
- FAA Remote ID and OpenDroneID: <https://www.faa.gov/uas/getting_started/remote_id>, <https://github.com/opendroneid/opendroneid-core-c>
- MAVLink message signing and ROS 2 DDS Security: <https://mavlink.io/en/guide/message_signing.html>, <https://design.ros2.org/articles/ros2_dds_security.html>
- AprilTag visual fiducial system: <https://github.com/AprilRobotics/apriltag>

### 3.5 5对5目标分配不是一次性问题

**难点**: 初始一对一分配后，目标可能丢失，资源可能失败，某些资源可能未确认目标，目标威胁等级也可能变化。

**主流做法**: 中心化滚动分配，持续更新 `AssignmentPlan`。中心节点存在时默认使用 Hungarian；存在容量、备份资源或多约束时升级为最小费用流。

**推荐方案**:

```text
TrackTable = [T1, T2, T3, T4, T5]
ResourceTable = [R1, R2, R3, R4, R5]
ScoutTrack = S1
```

中心节点每个分配周期执行：

1. 筛选 `confirmed/engageable` 目标。
2. 筛选 `available` 资源。
3. 计算每个 `Ri-Tj` 组合的分配代价。
4. 对不可行组合赋予不可分配状态。
5. 使用 Hungarian 或最小费用流生成一对一分配。
6. 为高威胁目标保留备份或补位规则。
7. 发布带版本号的 `AssignmentPlan`。

分配代价保持抽象：

```text
assignment_cost = 接近窗口代价
                + 航迹不确定性惩罚
                + 目标威胁权重
                + 资源状态惩罚
                + 视场确认难度
                + 资源间冲突风险
```

### 3.6 空中侦察无人机的角色容易越界

**难点**: 空中侦察无人机很有用，但如果它独立改任务，会形成多头指挥。

**主流做法**: 空中节点作为补盲、通信中继、光电确认和ID稳定器。

**推荐方案**:

```text
ScoutObservation
- scout_id
- timestamp
- bbox_or_bearing
- classification_hint
- confidence
- candidate_global_track_ids
```

侦察无人机参与三类交接：

| 交接类型 | 作用 |
|----------|------|
| 雷达到侦察无人机 | 雷达提供预测位置，侦察无人机确认类别和队形 |
| 侦察无人机到资源节点 | 侦察无人机给出候选ID和方位，资源节点尝试局部确认 |
| 资源节点到侦察无人机 | 资源节点丢失目标时，侦察无人机维持ID并辅助重捕获 |

原则：侦察无人机只能提供观测，不直接覆盖中心节点的 `GlobalTrack` 和 `AssignmentPlan`。

### 3.7 中心节点是优势也是风险

**难点**: 有中心节点时，全局分配更稳定；中心失效时，系统不能立刻瘫痪。

**主流做法**: 中心化正常运行，分布式降级保底。

**推荐方案**:

```text
C2Health
- heartbeat_age
- last_track_update_age
- assignment_update_age
- command_ack_rate
- clock_sync_error
- link_quality
- health_state
```

健康状态：

```text
normal -> degraded -> suspect -> failed
```

接管顺序：

1. 地面备份节点优先。
2. 空中侦察/中继节点次优先。
3. 资源集群代表节点局部接管。
4. 分布式拍卖/共识只作为保底。

### 3.8 分布式节点如何自主决策

**难点**: 分布式节点信息不完整，不能复制完整指挥所。

**主流做法**: 分布式节点只做局部态势维护、资源占用声明和冲突消解。任务分配采用拍卖算法或CBBA作为降级方案，不作为正常主控方案。

**推荐方案**:

```text
TrackSummary
- estimated_global_id
- timestamp
- position
- velocity
- covariance
- classification
- confidence

ResourceSummary
- node_id
- resource_id
- availability
- current_task_id
- energy_state
- local_constraints
```

分布式协商流程：

```text
每个节点根据本地航迹计算目标优先级
每个可用资源对候选目标计算本地代价
节点广播自身出价和任务占用声明
邻居节点比较出价，低代价者获得临时任务权
若出现冲突，按航迹版本、节点优先级和代价差消解
若多轮后未收敛，保留原任务或进入待命
```

边界：高不确定性目标和不可逆处置必须保留人工授权或预设约束。

### 3.9 高威胁目标的 M 对 N 协同拦截

现有 5 对 5 只描述资源数和目标数相等，不代表每个目标只能由一架资源处置。对高威胁目标，应显式定义目标资源需求 \(k_j\)，例如 \(k_j=3\)。

这类问题不能通过复制三次 Hungarian 任务或让三架无人机各自运行 PN 来宣称已经解决。完整链路必须同时包含：

- D1/D2：把多个平台对同一目标的观测注册到同一个中心 GlobalTrack，并保守处理公共先验和未知相关性。
- D3：形成带 required count、成员角色、到达策略和版本的联盟计划。
- D4：维护联盟 lease/epoch，处理中心、二级节点、完全无中心下的成员补位和重组。
- D5：区分计划内 planned cooperative lock 与错误 duplicate lock。
- D7：执行成员级 PN/PNG，并在上层协调到达窗口、波次、终端扇区和最小安全间距。
- D6：按目标需求满足率、到达离散、定位一致性、联盟重构和安全风险评估。

三种策略的推荐边界：

| 策略 | 推荐条件 | 限制 |
| --- | --- | --- |
| simultaneous 3 | 逃逸窗口短、共同到达时间可达、通信和时钟可靠、已分配不同终端扇区 | 同点进入的碰撞、遮挡、命令饱和和 FOV 丢失风险高 |
| sequential 1+1+1 | 身份/航迹不确定、首批结果可反馈、成员性能差异大或通信退化 | 总完成时间长，目标可能在波次间机动 |
| hybrid 2+1 | 高威胁需要冗余，但三机同时进入不安全 | 需要明确 primary/reserve、继续条件和版本化反馈 |

下一阶段默认研究假设采用 hybrid 2+1，而不是把三机严格同时到达写成固定工程规则。严格同时只在任务效果、几何、通信、机动和安全条件均被证明后启用。

开源结论：

- 基数需求可优先评估 OR-Tools/NetworkX 最小费用流或 b-matching。
- 能力、联盟原子性、同步和波次可用 OR-Tools CP-SAT、Pyomo/PuLP 构造参考模型。
- Stone Soup、OpenCV、GTSAM、ByteTrack/BoT-SORT 可分别提供融合、几何和本地 MOT 构件。
- 基础 CBBA 是单 winner 研究基线，不原生支持原子 \(k_j>1\) 联盟。
- 未发现可直接覆盖 MSM 全合同的成熟开源协同分配与协同导引库。

详细证据和任务拆解见 `subagent_reviews/MAIN_M_TO_N_COOPERATIVE_INTERCEPTION_SYNTHESIS.md` 及 D1-D7 的 M_TO_N 专项报告。当前相关能力登记为 P1；现有 \(k_j=1\) 主线无新增 P0。

---

## 四、按距离的推荐闭环

| 距离阶段 | 主要信息源 | 航迹质量 | 推荐动作 |
|----------|------------|----------|----------|
| 远距预警段 | 浮空器雷达、地面主雷达 | 位置误差较大，速度方向可用 | 建立 tentative/confirmed 航迹，不急于分配近距资源 |
| 中距跟踪段 | 地面雷达、角站雷达、空中侦察无人机 | 三维位置和速度稳定 | 形成 engageable 航迹，启动资源可行性计算 |
| 近距交接段 | 空中侦察无人机光电、地面光电、声学阵列 | 类别确认增强，ID稳定性成为重点 | 完成目标-资源初始分配 |
| 末端确认段 | 资源节点机载相机、侦察无人机、地面雷达 | 局部视场精细，视场外依赖中心航迹 | 视场内确认，视场外继续按预测航迹维持 |
| 效果评估段 | 侦察无人机、雷达、光电/声学 | 判断航迹是否消失或继续存在 | 标记 completed、failed、lost 或需要补位 |

状态闭环：

```text
远距雷达/浮空器发现
-> 中心节点建立GlobalTrack
-> 中距地面雷达稳定航迹
-> 空中侦察无人机辅助确认类别和队形
-> 中心节点对T1-T5与R1-R5做一对一分配
-> R1-R5飞向各自PredictedInterceptVolume
-> 视场内目标由机载相机确认
-> 视场外目标由雷达/侦察无人机/声学继续维持
-> 中心节点处理ID冲突、重复分配和重分配
-> 任务完成、失败、丢失或补位
```

---

## 五、5对5目标关联与分配方案

假设：

```text
入侵目标：T1, T2, T3, T4, T5
拦截资源：R1, R2, R3, R4, R5
高空系留二级侦察无人机：S1, S2
中心节点：C2
通信链路：C2-S1/S2、C2-R1...R5、S1/S2-R1...R5、R1...R5之间均可传递仿真数据摘要；S1/S2可向覆盖范围内资源定向发送图像/视频cue
降级想定：中心失效为被动降级；中心在线但分配计划因定位误差、动态延迟或末端视觉不一致而失效时，可触发主动降级仲裁
```

中心节点维护：

```text
TrackTable
ResourceTable
ScoutObservation / SecondaryReconCue
AssignmentPlan
```

关键规则：

1. `R1-R5` 不直接根据本机相机自行改任务。
2. 所有局部视觉观测回传中心节点。
3. 中心节点用 `global_track_id` 统一目标身份。
4. 看到目标但无法匹配时，新建 `tentative` 航迹，不立即重分配。
5. 看不到目标但中心航迹仍稳定时，继续向预测接近区移动。
6. 目标丢失时先请求雷达、声学、侦察无人机补充确认。
7. 重分配必须带版本号，避免多个节点执行不同版本任务。

---

## 六、中心节点失效与分布式降级

中心节点存在时：

```text
中心融合
-> 中心分配
-> 资源节点执行
-> 局部观测回传中心
```

中心节点失效时：

```text
检测C2Health进入failed
-> 备份节点接管
-> 若无备份，分布式节点交换TrackSummary/ResourceSummary
-> 拍卖式协商生成局部AssignmentPlan
-> 中心恢复后进行航迹表和任务表合并
```

分布式模式定位：保底，不是首选。

---

## 七、默认推荐架构

当前方案建议采用：

```text
主控：中心节点C2
主定位：地面雷达/浮空器雷达
低空辅助：声学阵列
补盲与ID稳定：空中侦察无人机S1
局部确认：资源节点机载相机
单目标导引：PN比例导引
单目标对照：Pure Pursuit
末端确认：视觉伺服/LOS角速率跟踪
航迹滤波：EKF/UKF，机动目标升级IMM
目标身份：GlobalTrack.global_track_id
多目标关联：GNN/Hungarian，密集交叉场景升级JPDA/MHT
资源分配：AssignmentPlan + Hungarian，复杂约束升级最小费用流
末端配准：图像MOT + GlobalTrack投影门限 + Hungarian/JPDA
友方识别：加密协同ID正向确认，未知目标不自动等同敌方
分布式降级：备份节点优先，拍卖/共识保底
授权边界：高不确定性不升级，不绕过人工授权
```

一句话总结：

```text
中心节点负责“谁是谁、谁去哪里”；
雷达负责“目标大概在哪里并如何运动”；
侦察无人机负责“目标是否仍是同一个、是否被遮挡或交叉”；
资源节点相机负责“局部视场内确认和回传候选观测”；
末端配准负责“把局部视觉目标绑定回中心分配的GlobalTrack”；
友方识别负责“正向确认己方，未知目标保持保守状态”；
分布式节点只在中心失效时维持最低限度任务连续性。
```

---

## 八、七子智能体研发编排与统一数据总线

本节把系统拆成七个科研子智能体并行推进。边界仍然保持在传感器融合、目标关联、资源分配、降级协同、末端配准、评估统计和比例导引合同门控层面；不定义真实火控参数、毁伤模型、自动处置控制律或绕过人工授权的流程。

### 8.0 子智能体综述与子方案索引

每个子智能体的详细综述、开源选型、接口设计、伪代码和测试计划已拆分为独立文档：

| 子智能体 | 文档 | 主题 |
|----------|------|------|
| D1 | [D1_SENSOR_FUSION_REVIEW_AND_PLAN.md](subagent_reviews/D1_SENSOR_FUSION_REVIEW_AND_PLAN.md) | 多传感器融合、时空基准、协方差建模 |
| D2 | [D2_DATA_ASSOCIATION_REVIEW_AND_PLAN.md](subagent_reviews/D2_DATA_ASSOCIATION_REVIEW_AND_PLAN.md) | 多目标跟踪、GNN/JPDA/MHT、ID Switch |
| D3 | [D3_ASSIGNMENT_PLANNER_REVIEW_AND_PLAN.md](subagent_reviews/D3_ASSIGNMENT_PLANNER_REVIEW_AND_PLAN.md) | 中心化资源分配、滚动重分配、迟滞逻辑 |
| D4 | [D4_DISTRIBUTED_FALLBACK_REVIEW_AND_PLAN.md](subagent_reviews/D4_DISTRIBUTED_FALLBACK_REVIEW_AND_PLAN.md) | 中心失效、备份接管、CBBA/拍卖降级 |
| D5 | [D5_TERMINAL_ASSOCIATION_REVIEW_AND_PLAN.md](subagent_reviews/D5_TERMINAL_ASSOCIATION_REVIEW_AND_PLAN.md) | 末端视觉配准、局部MOT、友方正向认证 |
| D6 | [D6_EVALUATION_METRICS_REVIEW_AND_PLAN.md](subagent_reviews/D6_EVALUATION_METRICS_REVIEW_AND_PLAN.md) | 评估指标、日志模型、批量实验统计 |
| D7 | [D7_PROPORTIONAL_GUIDANCE_REVIEW_AND_PLAN.md](subagent_reviews/D7_PROPORTIONAL_GUIDANCE_REVIEW_AND_PLAN.md) | 雷达中段 PN、末端视觉 PNG、导引合同门控 |

### 8.1 总体依赖与数据总线

统一数据总线采用事件流模式，所有模块只消费订阅主题并发布结构化消息，不直接改写其他模块内部状态。

```text
D1 SensorFusion
  SensorObservation -> GlobalTrack

D2 DataAssociation
  GlobalTrack candidates -> stable global_track_id / AssociationResult

D3 AssignmentPlanner
  GlobalTrack + ResourceState -> AssignmentPlan

D4 DistributedFallback
  C2Health + TrackSummary + ResourceSummary -> degradation action / fallback metadata

D5 TerminalAssociation
  GlobalTrack + AssignmentPlan + LocalVisualTrack + IdentityClaim
  -> TerminalAssociation

D7 ProportionalGuidance
  AssignmentPlan + D4 action + TerminalAssociation -> PN/PNG guidance records

D6 Evaluation
  consumes all logs -> EpisodeMetrics / BatchExperimentReport
```

核心依赖：

| 上游 | 下游 | 传递内容 | 约束 |
|------|------|----------|------|
| D1 | D2/D3/D5 | `GlobalTrack` | 必须带时间戳、坐标系、协方差和置信度 |
| D2 | D3/D5 | 稳定 `global_track_id` | ID切换必须记录，不允许静默覆盖 |
| D3 | D5/D4 | `AssignmentPlan` | 带`plan_id/version`，禁止局部节点自行换绑 |
| D4 | D3/D5/D7/D6 | 降级动作、二级接管 metadata、fallback 协商摘要 | D4 不直接生成中心系统级计划，二级 plan version 由 main/D3 回填 |
| D5 | D2/D3 | `TerminalAssociation`、`IdentityClaim` | 只修正置信度和歧义状态，不直接改任务 |
| D5/D3/D4 | D7 | 当前分配、降级允许状态、末端锁定证据 | D7 只在 D3/D4/D5 gate 全通过时进入视觉 PNG |
| D6 | 全部 | 日志与指标 | 独立运行，不参与任务决策 |

统一消息约定：

```text
timestamp:
  measurement_timestamp = 传感器实际测量/曝光/采样时间
  arrival_timestamp     = 消息到达融合系统时间
  publish_timestamp     = 模块输出时间

frame:
  sensor_frame -> body_frame -> NED/ENU -> map/global
  frame_id 和 transform_version 必须随消息记录

uncertainty:
  所有空间状态必须带 covariance
  分类、声纹、Remote ID 等身份线索只作为 likelihood 或 IdentityClaim
```

推荐总线主题：

```text
/sensor_observation
/global_track
/association_result
/resource_state
/assignment_plan
/c2_health
/distributed_bid_state
/local_visual_track
/terminal_association
/identity_claim
/guidance_record
/evaluation_event
```

### 8.2 D1 多传感器融合与目标配准

**任务**: 雷达、声学、光电时空基准不同，统一输出带协方差的`GlobalTrack`。

**文献与共识**: 2015-2026年的异构融合主线是“原始观测保留传感器坐标，融合状态在局部米制坐标系中估计”。滤波应使用`measurement_timestamp`，`arrival_timestamp`只用于链路延迟、缓存超时和质量评估。乱序观测按 OOSM 处理，可用 fixed-lag buffer、重传播或平滑更新。雷达误差随距离、SNR、波束宽度和杂波变化；声学 DOA 是粗方位，声纹更适合作身份似然；光电像素框需通过相机模型转换为角度/投影约束，遮挡、小框、逆光和低置信度时放大协方差。

**开源选型**:

| 工具 | 用途 | 集成工作量 |
|------|------|------------|
| Stone Soup | 多目标跟踪、OOSM、轨迹融合、JPDA/MHT实验 | 5-10人日 |
| FilterPy | EKF/UKF/IMM快速原型 | 3-6人日 |
| ROS 2 tf2 | 时间化坐标树、外参管理 | 3-5人日 |
| message_filters | Exact/Approx时间同步和缓存 | 1-3人日 |

**数据结构**:

```text
SensorObservation
- observation_id
- sensor_id
- modality: radar | acoustic | eo
- measurement_timestamp
- arrival_timestamp
- frame_id
- measurement
- covariance
- classification_hint
- confidence
- quality_flags

GlobalTrack
- global_track_id
- state_ned_or_enu: position + velocity
- covariance
- timestamp
- track_state: tentative | confirmed | engageable | lost | dropped
- source_support
- identity_likelihood
```

**UML文本类图**:

```text
SensorObservation --> FusionAdapter
FusionAdapter --> CanonicalDetection
CanonicalDetection --> DelayCompensator
DelayCompensator --> TrackFilter
TrackFilter --> GlobalTrack
```

**核心伪代码**:

```python
class FusionAdapter:
    def to_detection(self, obs, tf_buffer, target_frame="ned"):
        t = obs.measurement_timestamp
        z, R = self.normalize_measurement(obs)
        T = tf_buffer.lookup_transform(target_frame, obs.frame_id, t)
        z_out, J = transform_measurement(z, T)
        R_out = J @ R @ J.T + calibration_covariance(obs.sensor_id)
        return CanonicalDetection(z=z_out, covariance=R_out, timestamp=t)

class DelayCompensator:
    def update(self, track, detection):
        if detection.timestamp < track.timestamp:
            track = self.rewind_to(track, detection.timestamp)
            track.correct(detection)
            return self.replay_to_now(track)
        track.predict_to(detection.timestamp)
        track.correct(detection)
        return track
```

**雷达定位误差分档**:

```text
a95 = sqrt(chi2_2_0.95 * lambda_max(P_xy))
T_h < T_s < T_c 由仿真/标定数据确定

coarse_track:
  a95 > T_s，或只有短时单源支持；只用于提示和继续观测

stable_track:
  连续多帧 NIS 通过门限，a95 <= T_s，协方差无发散

handover_track:
  a95 <= T_h，多源一致，时间戳稳定；仅表示可交给下游配准/显示，
  不等价于处置授权
```

### 8.3 D2 多目标跟踪与数据关联

**任务**: 目标交叉、编队密集时抑制ID Switch。默认GNN/Hungarian，JPDA/MHT作为可插拔升级项。

**算法边界**:

| 算法 | 类型 | 优点 | 风险 |
|------|------|------|------|
| GNN/Hungarian | 硬关联 | 低延迟、实现简单、适合5对5基线 | 目标交叉时易ID Switch |
| JPDA | 软关联 | 多候选加权，交叉时更稳 | 目标过密时可能航迹合并 |
| MHT | 延迟决策 | 抗遮挡、抗交叉能力强 | 内存/延迟高，只建议中心节点或离线评估 |
| IMM-EKF/UKF | 运动模型增强 | 改善机动预测 | 不直接解决关联歧义 |

**类图**:

```text
abstract DataAssociator
  + associate(tracks, detections, timestamp) -> AssociationResult

GNNHungarianAssociator --|> DataAssociator
JPDAAssociator         --|> DataAssociator
MHTAssociator          --|> DataAssociator

TrackStateMachine
  tentative -> confirmed -> engageable -> engaged -> lost -> dropped

MetricsRecorder
  id_switch_count
  track_continuity
  duplicate_assignment_count
```

**核心伪代码**:

```python
class GNNHungarianAssociator(DataAssociator):
    def associate(self, tracks, detections, timestamp):
        cost = gated_mahalanobis_cost(tracks, detections)
        rows, cols = linear_sum_assignment(cost)
        return reject_large_cost_pairs(rows, cols, cost)

class JPDAAssociator(DataAssociator):
    def associate(self, tracks, detections, timestamp):
        hypotheses = enumerate_joint_hypotheses(tracks, detections)
        marginals = marginalize_probabilities(hypotheses)
        return weighted_update_result(marginals)

class MetricsRecorder:
    def update_identity(self, truth_id, track_id):
        old = self.last_truth_to_track.get(truth_id)
        if old is not None and old != track_id:
            self.id_switch_count += 1
        self.last_truth_to_track[truth_id] = track_id
```

**测试要求**:

1. 两条或多条真值航迹交叉，固定随机种子。
2. 加入漏检、虚警、延迟和杂波。
3. 同一输入分别运行 GNN、JPDA、MHT。
4. 必须输出`id_switch_count`、交叉窗口延迟、运行时间和失败日志。

### 8.4 D3 中心化资源-目标分配

**任务**: 5对5及更多目标下滚动重分配，避免任务抖动。输出`AssignmentPlan`，供末端配准和降级协商使用。

**开源选型**:

| 工具 | 适用场景 | 说明 |
|------|----------|------|
| SciPy `linear_sum_assignment` | 一对一快速分配 | 5x5到数百规模足够快，API简单 |
| OR-Tools Min Cost Flow | 容量、禁配、分组、时间窗 | 约束表达强，建模复杂度更高 |
| CP-SAT/MILP | 复杂逻辑约束 | 适合离线研究或中心节点增强 |

**数据结构**:

```text
ResourceState
- resource_id
- status: available | busy | degraded | unavailable
- capability_class
- health_score
- busy_until
- last_assignment
- operator_hold

AssignmentPlan
- plan_id
- version
- window_id
- assignments
- costs
- created_at
- human_authorization_state
```

**代价函数**:

```text
assignment_cost =
    接近窗口代价
  + 航迹不确定性惩罚
  + 目标威胁权重
  + 资源状态惩罚
  + 视场确认难度
  + 资源间冲突风险
  + 切换惩罚
```

**迟滞逻辑伪代码**:

```python
class AssignmentPlanner:
    def plan(self, tracks, resources, previous_plan):
        cost = build_cost_matrix(tracks, resources)
        candidate = solve_hungarian_or_min_cost_flow(cost)

        gain = previous_plan.total_cost - candidate.total_cost
        changed = count_assignment_changes(previous_plan, candidate)

        if gain < self.min_switch_gain:
            candidate = previous_plan.keep_with_new_window()

        if changed > self.max_changes_per_window:
            candidate = limit_reassignments(candidate, previous_plan)

        for resource in resources:
            if not min_hold_time_satisfied(resource, previous_plan):
                candidate.keep_previous(resource)

        candidate.version = previous_plan.version + 1
        candidate.human_authorization_state = "required"
        return candidate
```

**离线验证指标**:

```text
total_assignment_cost
reassignment_count
average_assignment_hold_time
unassigned_high_threat_count
duplicate_assignment_count
single_window_runtime_ms
version_conflict_count
```

### 8.5 D4 中心失效与分布式降级

**任务**: 中心节点失效后，优先备份节点接管；无备份时用CBBA/拍卖式协商维持保底连续性。

**核心原则**:

1. 正常状态使用中心化分配，不主动全分布式。
2. 中心失效后不假设各节点拥有完整态势。
3. 分布式结果只作为保底，不追求中心化全局最优。
4. 中心恢复后不立即夺权，必须双轨校验和人工确认。

**C2Health状态机**:

```text
normal
  -> degraded : 航迹/分配更新延迟升高，但心跳仍存在
  -> suspect  : 心跳过期、摘要不一致或链路异常

suspect
  -> normal : 双轨校验恢复
  -> failed : 多源确认中心不可用或自检失败

failed
  -> degraded : 备份节点lease有效或peer quorum成立

degraded
  -> normal  : 中心恢复且双轨校验通过
  -> suspect : 备份摘要冲突或网络分区
```

**接管优先级**:

```text
1. 地面备份节点
2. 空中侦察/中继节点
3. 资源集群代表
4. CBBA/拍卖式保底协商
5. 无共识时进入 hold / continue_observe / return_safe
```

**摘要消息**:

```text
TrackSummary
- id_hash
- coarse_cell
- age
- confidence_band
- source_count

ResourceSummary
- node_id
- capability_class
- availability_band
- comm_band
- operator_hold

BidState
- task_id
- bidder
- score_rank
- constraints_hash
- epoch
```

**伪代码**:

```python
def update_c2_health(heartbeat, track_digest, assignment_digest):
    if heartbeat.ok and track_digest.ok and assignment_digest.ok:
        return "normal"
    if heartbeat.stale or track_digest.conflict:
        return "suspect"
    if heartbeat.failed_by_quorum:
        return "failed"
    return "degraded"

def degraded_takeover(state):
    if state != "failed":
        return current_assignment_plan()
    if backup_lease_valid():
        return backup_plan(mode="safe_only")
    if peer_quorum_available():
        summaries = exchange_track_resource_bid_summaries()
        return cbba_or_auction(summaries, whitelist="continuity_only")
    return hold_or_return_safe()
```

**故障注入测试**:

```text
heartbeat_loss
delayed_or_out_of_order_updates
primary_backup_lease_conflict
network_partition_dual_leader
stale_track_summary
resource_degradation_not_broadcast
bid_replay_or_epoch_conflict
cbba_timeout
center_recovery_with_old_epoch
human_authorization_denied
```

### 8.6 D5 末端视觉配准与协同身份认证

**任务**: 末端视场内多个目标、友方资源和未知飞行物共存时，把局部视觉目标绑定回中心分配的`global_track_id`，并进行友方正向认证。

**关键结论**: 相机最近目标不等于分配目标。末端节点只能提交`AssociationProposal/TerminalAssociation`，严禁自行改写`global_track_id`或绕过中心/授权边界。

**处理链路**:

```text
AssignmentPlan.assigned_global_track_id
-> GlobalTrack按measurement_timestamp预测
-> tf2转换到camera_frame
-> OpenCV投影到图像平面
-> 生成几何门限
-> ByteTrack/BoT-SORT/Deep SORT生成LocalVisualTrack
-> Hungarian/JPDA做LocalVisualTrack到GlobalTrack匹配
-> IdentityClaim做友方正向确认
-> locked | ambiguous | hold | reacquire
```

**数据结构**:

```text
LocalVisualTrack
- local_track_id
- bbox
- center_px
- bearing_rate
- mot_history_length
- candidate_global_track_ids
- quality

TerminalAssociation
- assigned_global_track_id
- local_track_id
- association_confidence
- ambiguity_score
- friend_conflict_state
- decision_state: locked | ambiguous | hold | reacquire
- assignment_version

IdentityClaim
- platform_id
- claim_type: cooperative_id | remote_id | visual_tag
- auth_state: verified | stale | unverified | spoof_suspected
- associated_track_id
- timestamp
```

**匹配代价**:

```text
terminal_association_cost =
    图像平面投影误差
  + LOS角速率一致性误差
  + 时间戳延迟惩罚
  + 航迹协方差惩罚
  + 局部MOT连续性惩罚
  + 类别不一致惩罚
  + 友方身份冲突惩罚
```

**伪代码**:

```python
def terminal_association(global_track, assignment, local_tracks, claims):
    projected_gate = project_global_track_to_image(global_track)
    scores = []
    for local in local_tracks:
        if not inside_gate(local, projected_gate):
            continue
        cost = projection_cost(local, projected_gate)
        cost += los_rate_cost(local, global_track)
        cost += identity_conflict_cost(local, claims)
        scores.append((cost, local))

    best, margin = select_unique_candidate(scores)
    friend_state = evaluate_positive_friend_claim(best, claims)

    if friend_state == "friend_conflict":
        return TerminalAssociation(decision_state="hold")
    if best is None or margin < MIN_ASSOCIATION_MARGIN:
        return TerminalAssociation(decision_state="ambiguous")
    if assignment.assigned_global_track_id != global_track.global_track_id:
        return TerminalAssociation(decision_state="hold")
    return TerminalAssociation(decision_state="locked")
```

**失败案例测试**:

```text
nearest_visual_target_is_not_assigned_target
short_occlusion_then_reacquire
remote_id_matches_but_signature_fails
apriltag_visible_but_projection_residual_bad
camera_extrinsic_bias
timestamp_latency_shift
two_candidates_have_close_cost
```

### 8.7 D6 系统评估与批量实验

**任务**: 不能只报命中率；必须覆盖探测、跟踪、分配、降级、末端配准和安全约束。

**指标体系**:

| 类别 | 指标 |
|------|------|
| 探测 | `detection_probability`、`false_alarm_rate`、`missed_detection_rate` |
| 跟踪 | `track_rmse`、`track_continuity`、`id_switch_count` |
| 分配 | `duplicate_assignment_count`、`unassigned_high_threat_count` |
| 降级 | `failover_time`、`consensus_rounds`、`degraded_completion_rate` |
| 末端配准 | `terminal_association_accuracy`、`terminal_id_switch_count`、`ambiguous_fov_event_count`、`friend_overlap_hold_count`、`time_to_terminal_lock` |
| 安全约束 | `constraint_violation_count`、`human_override_count` |

**日志模型**:

```text
TrackRecord
- global_track_id
- truth_id
- timestamps
- states
- covariance_trace
- association_source

AssignmentRecord
- plan_id
- version
- resource_id
- global_track_id
- cost_breakdown
- authorization_state

EventRecord
- timestamp
- event_type
- actor_id
- severity
- note

EpisodeMetrics
- detection
- tracking
- assignment
- degradation
- terminal
- safety
```

**批量统计伪代码**:

```python
class BatchExperimentAnalyzer:
    def compute_episode(self, log):
        metrics = EpisodeMetrics(log.episode_id)
        metrics.detection = calc_detection_metrics(log.truth, log.detections)
        metrics.tracking = calc_tracking_metrics(log.truth, log.tracks)
        metrics.assignment = calc_assignment_metrics(log.assignments)
        metrics.degradation = calc_degradation_metrics(log.events)
        metrics.terminal = calc_terminal_metrics(log.terminal_associations)
        metrics.safety = calc_safety_metrics(log.events)
        return metrics

    def aggregate(self, episodes):
        return mean_std_ci95([episode.to_dict() for episode in episodes])
```

**实验报告模板**:

```text
实验名称：
场景/日期/版本/随机种子：
数据来源：仿真/回放/脱敏日志
算法组合：D1融合 / D2关联 / D3分配 / D4降级 / D5配准
人工授权记录：human_override_count =

探测：POD / FAR / MAR
跟踪：RMSE / continuity / IDSW
分配：duplicate / unassigned_high_threat / reassignment_count
降级：failover_time / consensus_rounds / degraded_completion_rate
末端配准：association_accuracy / terminal_IDSW / lock_time
安全约束：friend_overlap_hold / constraint_violation

批量统计：N、均值、标准差、95%CI、异常样本
结论：能力边界、失效模式、需人工复核事项
```

### 8.8 四周并行推进计划

| 周期 | 六智能体共同目标 | 交付物 |
|------|------------------|--------|
| 第1-2周 | 文献调研 | 每个智能体输出综述、适用边界、失败模式 |
| 第3周 | 开源代码调研 | 选型对比表、复用性、集成工作量 |
| 第4周 | 架构与接口设计 | UML、数据结构、伪代码、测试用例 |
| 第5周 | 数据总线联调 | 消息schema、契约测试、日志字段冻结 |
| 第6周 | 批量实验 | D6生成对比表和失效模式报告 |

最小可行联调顺序：

```text
1. D1发布GlobalTrack
2. D2稳定global_track_id并记录IDSW
3. D3生成带version的AssignmentPlan
4. D5验证AssignmentPlan与LocalVisualTrack配准
5. D4注入中心失效并验证保底协商
6. D6离线统计所有日志
```

### 8.9 参考资料索引

- Stone Soup tracking framework: <https://github.com/dstl/Stone-Soup>
- Stone Soup JPDA tutorial: <https://stonesoup.readthedocs.io/en/latest/auto_tutorials/08_JPDATutorial.html>
- Stone Soup MHT example: <https://stonesoup.readthedocs.io/en/latest/auto_examples/dataassociation/mht_example.html>
- FilterPy EKF/UKF/IMM: <https://filterpy.readthedocs.io/>
- SciPy `linear_sum_assignment`: <https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.linear_sum_assignment.html>
- Google OR-Tools Min Cost Flow: <https://developers.google.com/optimization/flow/mincostflow>
- MIT CBBA: <https://acl.mit.edu/projects/consensus-based-bundle-algorithm>
- CBBA-Python: <https://github.com/zehuilu/CBBA-Python>
- CA-CBBA: <https://github.com/mit-acl/CACBBA>
- ByteTrack: <https://github.com/FoundationVision/ByteTrack>
- BoT-SORT: <https://github.com/NirAharon/BoT-SORT>
- Deep SORT: <https://github.com/nwojke/deep_sort>
- OpenCV camera calibration: <https://docs.opencv.org/4.x/dc/dbb/tutorial_py_calibration.html>
- OpenCV `solvePnP`: <https://docs.opencv.org/4.x/d5/d1f/calib3d_solvePnP.html>
- ROS 2 tf2: <https://docs.ros.org/en/rolling/Concepts/Intermediate/About-Tf2.html>
- ROS 2 message_filters: <https://docs.ros.org/en/humble/p/message_filters/doc/Tutorials/Approximate-Synchronizer-Cpp.html>
- FAA Remote ID: <https://www.faa.gov/uas/getting_started/remote_id>
- OpenDroneID Core C: <https://github.com/opendroneid/opendroneid-core-c>
- MAVLink message signing: <https://mavlink.io/en/guide/message_signing.html>
- ROS 2 DDS Security design: <https://design.ros2.org/articles/ros2_dds_security.html>
- AprilTag: <https://github.com/AprilRobotics/apriltag>
- TrackEval: <https://github.com/JonathonLuiten/TrackEval>
- py-motmetrics: <https://github.com/cheind/py-motmetrics>
- AirSim recording APIs: <https://microsoft.github.io/AirSim/apis/>
- SCRIMMAGE: <https://github.com/gtri/scrimmage>

---

## 九、系统通信假设与工程难点复核

本节合并原独立通信复核文档。第三章给出算法难点，本节固定跨节点通信、消息责任链、主动/被动降级和 D7 中末段切换的系统约束。

### 9.1 允许的通信拓扑

当前系统允许多层数据与视频通信：

```text
中心节点 C2
  <-> 高空侦察/二级节点：数据 + 视频
  <-> 拦截无人机：数据

高空侦察/二级节点
  <-> 拦截无人机：数据 + 视频 cue + 检测摘要

拦截无人机
  <-> 拦截无人机：状态、观测摘要、锁定摘要和协商消息
```

通信能力增强不改变权限边界：

- 中心或当前合法 owner 维护 global_track_id 和版本化 AssignmentPlan。
- 二级节点可做区域感知增强和降级接管，但不能绕过 D3/D4 发布本地任务。
- 拦截机可以共享证据、资源状态和 bid，不能根据本地画面自行换绑目标。
- 视频 cue 是辅助观测，不等于身份确认、全局配准或处置授权。
- 未知、无签名或过期身份不能反推为敌方；友方冲突必须 hold。

### 9.2 通信与视频元数据合同

所有跨节点消息至少保留：

```text
source_node_id
target_node_id
relay_node_id
link_type: c2_direct | secondary_relay | interceptor_peer | video_cue
message_type
sequence_id
sent_timestamp
received_timestamp
measurement_timestamp
arrival_timestamp
clock_sync_error
payload_kind
plan_id / plan_version
track_version
stale_after_s
```

视频本体默认不落盘，帧级元数据必须可追溯：

```text
camera_id / stream_id
frame_timestamp
bbox_xyxy
camera_intrinsics
camera_extrinsics
producer_node_id
consumer_node_id
candidate_global_track_ids
confidence
```

双时间戳用于 OOSM 和延迟补偿；source/relay/sequence 用于重复消息去重；plan/track version 和 stale deadline 用于阻断旧任务继续执行。

### 9.3 ComputerVision 5v5 阶段边界

AirSim ComputerVision 5v5 用于验证 D1-D5 的感知、关联、分配、末端视觉配准和降级仲裁，不验证 SimpleFlight 动力学或 D7 真实控制效果。

main 负责：

- 单次启动 Blocks、reset 分隔 episode。
- 移动 actor target，并按 assignment 调整拦截相机位置、yaw 和 pitch。
- 让高空侦察相机根据 GlobalTrack cue 指向覆盖区目标。
- 收集 camera pose、bbox、时间戳、source node、local track 和 detection metadata。
- actor 名称只进入离线 truth，不进入 D5 在线关联。

此阶段默认不保存 PNG。`blocks_frames.jsonl` 和 `blocks_sensor_observations.jsonl` 分别承载视觉元数据和带双时间戳/协方差的传感器观测。

### 9.4 五类工程难点与当前选型

| 难点 | 主流构件 | 当前主线 | 仍需验证 |
| --- | --- | --- | --- |
| 多源融合与不确定度 | Stone Soup、FilterPy、tf2/message_filters | 轻量 FusionAdapter、NED、双时间戳、协方差、OOSM | 多节点相关性、真实外参和区域质量 |
| 多目标 ID 与跨视角 | GNN/Hungarian、JPDA/MHT、MOT | D2 全局身份 + D5 camera-local MOT/投影门控 | 跨节点 registry、真实 YOLO/MOT、IDSW 阈值 |
| 动态分配与末端反馈 | SciPy Hungarian、OR-Tools | 版本化计划、迟滞、D5 feedback writeback | M 对 N、复杂约束和多 seed 权重 |
| 主动/被动降级 | 二级接管、CBBA/auction | 中心 -> 二级 -> cluster/distributed | secondary active plan 正例、分区和联盟原子性 |
| 末端配准与导引切换 | OpenCV、ByteTrack/BoT-SORT、PN/PNG | GlobalTrack 投影、保守锁定、D3/D4/D5 gate | 视觉质量、LOS、机动裕度和长时闭环 |

成熟开源方案主要是组件级，不存在一套可直接覆盖 C-UAS 全闭环的成熟库。Stone Soup、FilterPy、OpenCV、SciPy、OR-Tools、ByteTrack/BoT-SORT、TrackEval 等应先作为隔离 benchmark 或 adapter，而不是直接替换轻量主线。

基础 CBBA 只解决 single-winner 任务。MIT ACL 的 MATLAB 包可作研究基线；`zehuilu/CBBA-Python` 是个人实现；`mit-acl/CACBBA` 当前没有可运行源码，不能称为已接入实现。

### 9.5 主动与被动降级仲裁

被动降级链：

```text
C2 heartbeat/lease 失效
-> 可用地面备份或高空侦察二级节点接管
-> 二级节点失效时选择 cluster representative
-> 最后进入 CBBA/auction 保底
```

主动降级适用于中心仍在线但态势或计划不再可信：

```text
1. friend conflict -> hold_for_review
2. D5 与当前分配一致 -> continue
3. plan stale/not-current -> request_center_replan
4. D1/D2 不确定度或关联风险升高 -> request_secondary_assist
5. D5 持续 mismatch 且二级证据可用 -> degrade_to_secondary
6. 二级不可用但 peer 网络可用 -> distributed/cluster representative
7. 身份或版本冲突无法消解 -> hold
```

低 cost margin、早期视觉低置信度或无冲突的短时 reacquire 只进入 observe/replan，不应直接触发全分布式降级。

### 9.6 D7 中段到末端的五类门槛

D5 locked 且 assigned global track 与 D3 一致只是必要条件。进入 vision terminal 还必须同时通过以下五类门槛。

#### 9.6.1 身份和任务一致性

- TerminalAssociation 为 locked。
- assigned global_track_id、plan id/version、owner 和 D7 binding 一致。
- GlobalTrack/plan 未过期。
- 无 friend conflict、错误 duplicate lock、local-to-global mismatch。
- M 对 N 场景中的多机锁定必须由有效 coalition 授权。

#### 9.6.2 相机识别能力

- bbox 宽、高、面积和 detector confidence 达到标定门限。
- 连续稳定帧数足够，local track 没有频繁切换。
- bbox 不严重遮挡、截断或贴近图像边缘。
- 相机内外参、位姿来源和 calibration health 有效。

#### 9.6.3 LOS 测量质量

- 像素中心时间戳连续。
- LOS angle/LOS rate 可稳定估计，方差和异常值率低于门限。
- 帧率、曝光、处理和通信延迟满足终端窗口。
- bbox/LOS 证据来自当前相机流和当前 plan epoch。

#### 9.6.4 平台机动能力

- 所需横向加速度、转弯率和速度方向变化不超过平台裕度。
- 高度、速度和加速度控制未持续饱和。
- closing speed 合理，预计 FOV 不会因命令立即丢失。
- 多机协同时满足 terminal sector 和 minimum separation。

#### 9.6.5 剩余拦截窗口

- range 位于标定后的切换窗口，不把固定 30 m 当成所有场景常数。
- estimated time-to-go 足以完成视觉稳定、模式切换和剩余机动。
- D1/D2 协方差未发散，measurement age 可接受。
- terminal detection timeout 和 D4 replan pending 风险在门限内。

推荐状态机：

```text
radar_midcourse
  -> handover_pending
       进入终端候选窗口，计划有效，D1/D2 航迹稳定

handover_pending
  -> vision_terminal
       D5 locked + 版本一致 + 相机/LOS/机动/时间门槛全部通过
  -> radar_midcourse
       视觉不足但雷达航迹仍稳定
  -> hold/reacquire
       ambiguous、friend conflict、版本冲突或需要二级复核

vision_terminal
  -> intercept
       仿真成功判据满足
  -> hold/abort
       目标出框、错误绑定、版本失效、控制饱和或安全冲突
```

### 9.7 模块通信责任

| 模块 | 主要通信输入 | 主要输出 | 禁止事项 |
| --- | --- | --- | --- |
| D1 | 雷达/声学/视觉/LiDAR、节点位姿和链路元数据 | GlobalTrack、协方差、延迟和覆盖质量 | 不授权、不以 PNG 为必要依赖 |
| D2 | D1 航迹、D5/二级证据 | canonical global_track_id、关联风险和 IDSW | 不让本地节点改写 ID |
| D3 | GlobalTrack、资源状态、D4/D5 风险 | 版本化 AssignmentPlan/coalition plan | 不按最近视觉目标直接换绑 |
| D4 | C2/二级健康、D1-D5 summary、peer 状态 | DegradationDecision、owner/epoch/lease | 不处理原始视频，不跳过 D3/D5 |
| D5 | 多拦截机视觉、二级 cue、身份声明 | TerminalAssociation、IdentityClaim、冲突证据 | 不生成计划，不改 global_track_id |
| D6 | 结构化 episode/link/terminal/guidance 日志 | 指标、图表和报告 | 不参与在线控制 |
| D7 | D1/D2 航迹、D3 plan、D4 permission、D5 lock | mode/command/gate summary | 不自行选目标或绕过版本/安全门槛 |

### 9.8 通信与切换评估指标

除第八章的系统指标外，通信和中末段切换至少记录：

```text
cross_node_latency_ms
message_drop_rate
out_of_order_count
stale_track_update_count
video_metadata_delivery_rate
bbox_delivery_rate
multi_view_consensus_rate
cross_view_conflict_count
planned_cooperative_lock_count
erroneous_duplicate_lock_count
camera_quality_gate_pass_rate
los_quality_gate_pass_rate
maneuver_margin_gate_pass_rate
terminal_switch_reject_count
terminal_switch_reject_reason
```

最终原则是：通信用于共享证据、减少不确定性和提高仲裁质量；通信本身不授予局部节点改写 global_track_id、AssignmentPlan 或导引目标的权力。
