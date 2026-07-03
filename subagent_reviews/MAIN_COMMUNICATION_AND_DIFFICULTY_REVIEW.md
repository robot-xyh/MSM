# Main 通信假设与工程难点复核汇总

**定位**：本文由 main agent 汇总 D1-D7 子智能体复核结果，用于更新当前多无人机拦截仿真体系的通信假设、工程难点、开源成熟方案和本项目选型。  
**依据**：各子智能体复核意见、`C_UAS_MAINSTREAM_SOLUTIONS_AND_DIFFICULTIES.md`、当前 `subagent_reviews/D1-D7` 文档。  
**边界**：本文面向科研仿真、接口设计和系统评估，不描述真实部署参数、处置授权绕过或实装毁伤细节。

---

## 1. 已同步给子智能体的通信假设

当前系统不再假设各拦截无人机是孤立节点，而是允许多层数据与视频通信：

```text
中心节点 C2
  <-> 系留高空侦察/二级节点：数据 + 视频
  <-> 拦截无人机：数据

二级节点 / 系留侦察无人机
  <-> 拦截无人机：数据 + 视频 / 图像 cue / 检测摘要

拦截无人机之间
  <-> 拦截无人机：数据通信
```

这意味着 D1-D7 的接口必须显式记录通信来源、时间戳、链路延迟和版本号。通信增强提升了多视角确认和主动降级能力，但也引入异步、重复观测、跨节点 ID 冲突和旧版本计划继续执行等风险。

推荐统一携带字段：

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
payload_kind: track | bbox | video_metadata | assignment | terminal_association | bid
plan_version
track_version
stale_after_s
```

视频本体不必默认保存，但视频元数据必须可追溯：

```text
camera_id
stream_id
frame_timestamp
bbox_xyxy
camera_intrinsics
camera_extrinsics
producer_node_id
consumer_node_id
candidate_global_track_ids
confidence
```

---

## 2. 总体结论

### 2.1 AirSim ComputerVision 5v5 阶段边界

当前新增的 AirSim ComputerVision 5v5 阶段用于验证 D1-D5 的感知、关联、分配、末端视觉配准和降级仲裁，不验证 SimpleFlight 动力学或 D7 真实拦截控制。main 统一启动 Blocks、reset 场景、移动 `MSM_TargetActor_1..5`，并对 `Interceptor_Cam_1..5` 与 `Secondary_Recon_1..2` 显式传入 `vehicle_name` 采集图像状态和 AirSim `simGetDetections` 检测框。

相机位姿不再固定。main 在每帧用 `simSetVehiclePose` 更新 CV 相机位置和姿态：`Interceptor_Cam_i` 按当前分配目标保持 standoff 距离，并计算 yaw/pitch 让镜头朝向目标；默认在 episode 中点执行二次分配，将 `Interceptor_Cam_2` 与 `Interceptor_Cam_3` 的目标互换，用于验证初次分配和二次分配后的视觉交接。`Secondary_Recon_1/2` 保持高位覆盖，并转向对应覆盖区目标质心。

默认运行入口：

```bash
python3 research_modules/airsim_runtime/run_blocks_sequence.py \
  --cv-5v5 \
  --sequence-id blocks_cv_5v5_sequence_001 \
  --duration 6.0 \
  --dt 0.5
```

默认 settings：`research_modules/airsim_runtime/settings/blocks_cv_5v5_settings.json`。

阶段分工：

| 模块 | CV 5v5 职责 |
|------|-------------|
| main | 创建 CV 相机节点、移动 5 个 actor target、收集 detection metadata、驱动 replay |
| D1 | 根据 actor truth 合成带延迟和协方差的 radar/acoustic/EO 观测，输出 `GlobalTrack` |
| D2 | 对 D1 航迹做 5v5 GNN/Hungarian 关联，记录 ID switch 和关联风险 |
| D3 | 对 5 个 `Interceptor_Cam_*` 与 5 个 `GlobalTrack` 做中心化 Hungarian 分配 |
| D4 | 根据 C2/二级节点状态和 D1-D5 风险决定继续中心、二级接管或无中心保底 |
| D5 | 将多相机 `simGetDetections` bbox 转为 `LocalVisualTrack`，执行终端配准和跨视角汇总 |
| D6 | 消费 frame、assignment、terminal、D4 decision 和 link metadata，生成指标 |

此阶段默认不保存 PNG。图像到视觉模块的交接只依赖 `blocks_frames.jsonl` 中的 camera pose、bbox、时间戳、source node、local track id 和检测元数据。D1 的可复现输入同步写入 `blocks_sensor_observations.jsonl`，包含 measurement/arrival timestamp、协方差和通信 metadata。AirSim actor 名称只用于离线真值评估，不作为 D5 在线配准依据。

五个核心难点均已参考 `C_UAS_MAINSTREAM_SOLUTIONS_AND_DIFFICULTIES.md` 的主流共识，但目前不存在一套开箱即用、覆盖 C-UAS 全闭环的成熟开源系统。成熟方案主要是组件级：

| 能力 | 成熟开源/资料 | 成熟度 | 本项目选型 |
|------|---------------|--------|------------|
| 多目标融合/关联 | Stone Soup、FilterPy | A / A-B | 自研轻量 EKF/FusionAdapter 为主，Stone Soup 做对照 |
| 坐标/时间同步 | ROS 2 tf2、message_filters | A | 后续 AirSim/ROS 2 接口采用 |
| 相机几何 | OpenCV calibration、solvePnP/projectPoints | A | D5 投影门控主线 |
| 中心分配 | SciPy `linear_sum_assignment` | A | D3 Hungarian 主线 |
| 复杂约束分配 | OR-Tools Min Cost Flow | A | 作为容量/禁配/备份资源升级项 |
| 分布式降级 | MIT CBBA、CBBA-Python、CA-CBBA、拍卖/合同网 | 理论 A，工程原型 B | D4 简化 CBBA/拍卖保底 |
| 末端 MOT | ByteTrack、BoT-SORT、Deep SORT | A-B | D5 局部视觉候选，几何门控优先 |
| 友方正向身份 | OpenDroneID、MAVLink signing、DDS Security、AprilTag | A-B | 只用于确认协同/友方，不反推未知为敌方 |
| 比例导引 | PN 公式/小型仿真、FRPN 论文、ViSP | PN 理论 A，开源控制库 B-C | D7 自研轻量 PN/LOS，开源仅用于公式核对和视觉伺服参考 |
| 评估 | Stone Soup metrics、TrackEval、py-motmetrics | A-B | D6 自定义 EpisodeMetrics + CSV/JSON/图表 |

工程结论：

1. 正常态采用中心化主控，不提前全分布式。
2. 二级系留侦察节点是区域感知增强和降级接管节点，不直接绕过 D3/D4 权威。
3. 拦截机之间可通信，但只能交换状态、锁定摘要、局部观测和冲突提示，不能自行重写 `global_track_id`。
4. 视频 cue 只作为 D5/D1 的辅助观测或复核证据，不能代替几何门控、身份确认和分配版本一致性。
5. D7 中段到末端切换必须同时满足身份一致、视觉质量、LOS 质量、机动能力和拦截窗口要求。

---

## 3. 五个工程难点复核

### 3.1 难点一：多源融合与不确定度表达

对应模块：D1。

是否参考主流方案：是。D1 已对齐“雷达主定位、EO/视觉确认、声学辅助、统一 `GlobalTrack`、协方差表达、测量时间和到达时间分离”的共识。

成熟开源方案：

- Stone Soup：多目标跟踪、航迹融合、OOSM、JPDA/MHT 对照，成熟度 A。
- FilterPy：EKF/UKF/IMM 原型，成熟度 A-B。
- ROS 2 tf2/message_filters：坐标树和时间同步，成熟度 A。
- OpenCV：相机标定和投影，成熟度 A。
- 声学主定位：没有统一成熟主线，应保持粗方位/类别辅助。

本项目采用：

- 当前仿真主线采用轻量自研 NumPy EKF + `FusionAdapter` + fixed-lag replay。
- Stone Soup 作为中心节点多目标跟踪和 OOSM 对照验证。
- 声学仅作为弱约束，不单独初始化三维可交接航迹。

通信假设影响：

- 系留无人机、拦截机、中心节点、二级节点都会产生观测或检测摘要，D1 必须记录 `sensor_id/node_id/frame_id/source_support`。
- 多节点观测提升覆盖，但会增加重复观测。D1 需要按时间、外参、协方差和来源相关性做去重/降权。
- 视频通信不要求保存 PNG。D1 应消费检测框、相机位姿、内外参、置信度和时间戳。

建议新增工程字段：

```text
latest_measurement_timestamp
latest_arrival_timestamp
mean_latency_s
max_latency_s
source_support
sensor_coverage_gap
active_degrade_hint
```

---

### 3.2 难点二：多目标 ID 保持与跨视角反馈

对应模块：D2。

是否参考主流方案：是。D2 已对齐 `EKF/UKF + GNN/Hungarian` 主线，交叉密集时升级 JPDA/MHT，并强制记录 `id_switch_count`。

成熟开源方案：

- SciPy `linear_sum_assignment`：Hungarian 基线，成熟度 A。
- Stone Soup：GNN/JPDA/MHT/Track Fusion，成熟度 A。
- FilterPy：滤波器原型，成熟度 A-B。
- ByteTrack/BoT-SORT/Deep SORT：属于 D5 局部视觉 MOT，不直接替代 D2 全局关联。

本项目采用：

- 5v5 基线：GNN/Hungarian + Kalman/EKF。
- 协方差重叠、IDSW、D5 不一致升高时，JPDA 作为优先升级。
- MHT 只用于中心节点或离线评估，不在资源节点运行。

通信假设影响：

- 多视角数据可降低遮挡和单视角误配，但也会增加异步冲突。
- D2 仍是 `global_track_id` 权威维护者。D5、二级节点和拦截机只能提交 `TerminalAssociation`、`IdentityClaim`、候选 ID、置信度和时间戳。
- 系留无人机俯视 cue 可作为二级辅助关联源，进入 D2 前必须变成带协方差和时间戳的观测或 `TrackSummary`。

主动降级输出：

```text
id_switch_count
id_switch_rate
track_continuity
covariance_overlap_rate
duplicate_track_risk
association_ambiguity
missed_detection_duration
d5_disagreement_count
```

---

### 3.3 难点三：动态分配、迟滞与末端不一致处理

对应模块：D3。

是否参考主流方案：是。D3 已对齐中心化 Hungarian/最小费用流，中心失效后由 D4 进入 CBBA/拍卖降级。

成熟开源方案：

- SciPy `linear_sum_assignment`：一对一快速分配，成熟度 A。
- OR-Tools Min Cost Flow：容量、禁配、备份资源、时间窗约束，成熟度 A。
- CP-SAT/MILP：表达力强，但不适合高频主线。

本项目采用：

- 正常态：`SciPy Hungarian + 可解释代价矩阵 + plan_version + 迟滞`。
- 复杂约束：OR-Tools Min Cost Flow。
- 分布式保底：由 D4 运行简化 CBBA/拍卖，不放入 D3 主流程。

通信假设影响：

- 拦截机可与中心/二级节点通信，使 D3 能持续接收资源状态、D5 终端反馈、二级侦察 cue。
- 拦截机间通信可交换 `assigned_global_track_id`、`plan_version`、`terminal_locked/hold`，用于发现重复锁定。
- 系留视频只影响 D3 的代价项和可行边，不允许绕过版本化 `AssignmentPlan`。

末端不一致处理：

```text
D5 locked 且版本一致       -> continue
D5 ambiguous/reacquire     -> hold 或请求中心重规划
D5 mismatch 多帧持续       -> 请求二级节点仲裁
duplicate_terminal_lock    -> D3/D4 调整主备资源
friend_conflict            -> hold_for_review，不自动重分配
```

---

### 3.4 难点四：主动降级、被动降级与二级节点接管

对应模块：D4。

是否参考主流方案：是。D4 遵循“中心化正常运行，备份/二级节点优先，CBBA/拍卖保底”的共识。

成熟开源方案：

- MIT CBBA：理论成熟度 A。
- CBBA-Python、CA-CBBA：研究原型 B，适合仿真验证。
- 拍卖/合同网协议：成熟思想，但工程实现差异大。

本项目采用：

```text
正常态：中心 C2 + D3 Hungarian/Min Cost Flow
被动降级：中心失效 -> 二级系留侦察节点 / 地面备份节点
二次被动降级：二级节点失效 -> cluster_representative
最终保底：简化 CBBA / auction
主动降级：中心在线但计划不可信 -> 请求中心重规划或二级节点辅助
```

通信假设影响：

- 拦截机间通信支持 `TrackSummary/ResourceSummary/BidState` 传播。
- 拦截机与中心/二级节点通信支持 plan version、lease、健康状态同步。
- 系留无人机与拦截机的视频/数据通信主要用于二级节点辅助仲裁。
- 系留无人机与中心通信使二级节点成为区域感知增强节点，而不是只在中心失效后才工作。

主动降级仲裁顺序：

```text
1. friend_conflict -> hold_for_review
2. D5 与分配一致 -> continue
3. D3 plan stale/cost恶化 -> request_center_replan
4. D1/D2 不确定度升高 -> request_secondary_assist
5. D5 多帧 mismatch 且二级覆盖 -> degrade_to_secondary
6. 二级不可用且局部通信存在 -> cluster_representative / CBBA
7. 通信不足或身份冲突无法消解 -> hold
```

---

### 3.5 难点五：末端多视角配准、身份确认与 D7 切换

对应模块：D5、D7。

是否参考主流方案：是。D5 已对齐“局部视觉只作为全局航迹确认源，不能直接改任务”的共识；D7 已对齐“PN 为单目标默认导引，Pure Pursuit/LOS 为基线或保底”的共识。

成熟开源方案：

- OpenCV calibration/projectPoints/solvePnP：成熟度 A。
- ROS 2 tf2/message_filters：成熟度 A。
- ByteTrack/BoT-SORT/Deep SORT：单视角 MOT 成熟度 A-B。
- OpenDroneID、MAVLink signing、DDS Security、AprilTag：正向身份确认 A-B。
- ViSP：视觉伺服参考 A。
- PN 开源仓库：多为公式核对或小型仿真 B-C，不建议直接接入控制闭环。

本项目采用：

- D5：`GlobalTrack` 投影门控 + OpenCV/tf2 + 局部 MOT + Hungarian/门限代价 + `IdentityClaim` 正向确认。
- D5 跨视角：`TerminalObservationBus` 收集拦截机局部观测，`TerminalCrossViewFusion` 输出支持证据、歧义和重复锁定风险。
- D7：中段 `radar_midcourse` 使用 D1/D2 航迹做经典 PN；末端 Blocks 当前采用 D5 确认后的 LOS tracking；后续升级严格像素 LOS-rate visual PN。

典型多视角场景：

```text
UAV1 sees {1, 2, 3}
UAV2 sees {2, 3, 4}
```

处理原则：

1. `local_track_id` 只在本机/本相机内有效，不能跨 UAV 字符串比较。
2. 目标 2/3 若被两个视角支持，提升跨视角一致性置信。
3. 目标 1/4 只被单视角看到，不是错误，只降低跨视角支持度。
4. 两资源同时锁定同一 `global_track_id` 时，D5 只上报 `duplicate_terminal_lock_risk`，由 D3/D4 仲裁。
5. 未知、无签名或过期身份不能反推为可处置目标；友方重叠必须 `hold`。

---

## 4. D7 中段到末端切换策略修正

D7 切换策略不能只看：

```text
D5 TerminalAssociation(decision_state="locked")
AND assigned_global_track_id 与 D3 AssignmentPlan 一致
```

这只是身份和任务一致性门槛。进入 `vision_terminal` 还必须同时满足相机识别能力、LOS 质量、平台机动能力和剩余拦截窗口。

### 4.1 身份与任务一致性门槛

```text
TerminalAssociation.decision_state == locked
TerminalAssociation.assigned_global_track_id == AssignmentPlan.assigned_global_track_id
AssignmentPlan.plan_version == current_plan_version
GlobalTrack.track_version 未过期
无 friend_conflict / mismatch / duplicate_terminal_lock_risk
```

### 4.2 相机识别能力门槛

```text
bbox_width / bbox_height / bbox_area 超过最小可识别门槛
detection_confidence 超过门槛
连续 k 帧稳定检测
local_track_id 未频繁切换
bbox 中心距离图像边缘有足够余量
目标不处于严重遮挡、截断或即将出框状态
```

### 4.3 LOS 测量质量门槛

```text
像素中心时间戳连续
LOS angle / LOS-rate 可稳定估计
LOS-rate 方差低于门槛
相机帧率满足导引更新需要
曝光、处理、通信延迟小于终端窗口可承受值
```

### 4.4 平台机动能力门槛

```text
需求横向加速度未超过平台能力裕度
需求转弯率未超过平台能力裕度
期望速度方向变化可在剩余窗口内完成
速度/加速度/高度控制未持续饱和
闭合速度合理，目标不是持续远离
```

### 4.5 剩余拦截窗口门槛

```text
range_m 在终端切换窗口内
closing_speed_mps 合理
estimated_time_to_go 有足够余量
D3 plan_age 未过期
D1/D2 目标协方差未发散
terminal_detection_timeout 风险可接受
```

### 4.6 推荐 D7 状态转移

```text
radar_midcourse
  -> handover_pending
       条件：进入终端距离窗口，D3计划有效，D1/D2航迹稳定

handover_pending
  -> vision_terminal
       条件：D5 locked + 版本一致 + 相机质量达标 + LOS质量达标 + 机动余量达标

handover_pending
  -> radar_midcourse
       条件：视觉质量不足但航迹仍稳定

handover_pending
  -> hold/reacquire
       条件：D5 ambiguous/reacquire，或二级 cue 需要复核

vision_terminal
  -> hit/range_intercept
       条件：仿真成功判据满足

vision_terminal
  -> abort/hold
       条件：版本冲突、friend_conflict、目标出框、控制饱和、碰撞对象不匹配
```

---

## 5. 新通信假设下的模块分工

| 模块 | 通信输入 | 通信输出 | 不能做的事 |
|------|----------|----------|------------|
| D1 | 多节点观测、检测框、相机元数据、声学/雷达摘要 | `GlobalTrack`、协方差、延迟/覆盖质量 | 不处理授权，不保存 PNG 作为必要依赖 |
| D2 | D1 航迹、D5 末端反馈、二级节点摘要 | 稳定 `global_track_id`、ID 风险量 | 不允许 D5 或本地节点直接改 ID |
| D3 | `GlobalTrack`、资源状态、D5/D4 风险 | 版本化 `AssignmentPlan` | 不允许本地相机看到谁就重分配 |
| D4 | C2/二级健康、D1-D5 summary、peer 状态 | `DegradationDecision`、降级模式、仲裁原因 | 不直接处理视频流，不跳过 D3/D5 |
| D5 | 多拦截机视觉摘要、二级视频 cue、身份声明 | `TerminalAssociation`、`IdentityClaim`、冲突/歧义 | 不改写 `global_track_id`，不生成 AssignmentPlan |
| D6 | 全部结构化日志、链路日志、视频元数据 | EpisodeMetrics、图表、报告 | 不参与实时控制 |
| D7 | D1/D2 航迹、D3计划、D5锁定、D4模式、二级 cue | 导引模式、命令摘要、拦截指标 | 不自行选目标，不绕过分配版本和视觉质量门槛 |

---

## 6. 当前项目应固定的实现路线

### 6.1 正常态

```text
D1 多源融合 -> D2 全局关联 -> D3 Hungarian 分配
-> D7 radar_midcourse PN
-> D5 终端视觉配准
-> D7 vision_terminal LOS/visual PN
-> D6 评估
```

### 6.2 中心在线但态势质量下降

```text
D1 协方差/延迟升高
OR D2 ID 风险升高
OR D3 plan stale/cost恶化
OR D5 多帧 ambiguous/mismatch

-> D4 active_degradation arbitration
-> 优先 request_center_replan 或 request_secondary_assist
-> 二级节点提供 scoped ReconImageCue / TrackSummary
-> D3 重规划或保持 hold
```

### 6.3 中心被动失效

```text
C2 heartbeat/lease 失效
-> D4 passive_failover
-> 二级系留侦察节点接管区域协调
-> 若二级节点也失效，进入 cluster_representative
-> 最后才 CBBA/auction 保底
```

### 6.4 末端视觉不一致

```text
D5 mismatch / duplicate_terminal_lock / friend_conflict
-> D7 hold，不切换目标
-> D3/D4 仲裁
-> 二级节点发送 cue 或中心重规划
-> 一致后才恢复 terminal guidance
```

---

## 7. 需要补入后续代码/测试的检查项

1. D1：多节点重复观测去重、通信延迟对协方差放大、`source_support`。
2. D2：跨视角弱证据融合、IDSW 对 D4 主动降级的触发测试。
3. D3：`duplicate_terminal_lock` 后的 hold/replan 单元测试。
4. D4：主动降级中 `request_secondary_assist` 优先于全分布式的测试。
5. D5：`TerminalObservationBus` 和 `CrossViewAssociation` 数据结构。
6. D6：链路质量指标、视频元数据责任链、无 PNG 的多视角评估。
7. D7：视觉切换门槛从单一 `locked` 扩展为五类门槛：身份一致、相机质量、LOS 质量、机动余量、拦截窗口。

推荐新增指标：

```text
cross_node_latency_ms
message_drop_rate
out_of_order_count
stale_track_update_count
video_metadata_delivery_rate
bbox_delivery_rate
multi_view_consensus_rate
cross_view_conflict_count
duplicate_terminal_lock_count
camera_quality_gate_pass_rate
los_quality_gate_pass_rate
maneuver_margin_gate_pass_rate
terminal_switch_reject_count
terminal_switch_reject_reason
```

---

## 8. 最终判断

当前五个难点都已经参考主流共识，并且已有成熟开源组件可用，但没有完整的一体化成熟开源 C-UAS 方案。本项目最合理路线是组件化集成：

```text
Stone Soup / FilterPy / ROS 2 / OpenCV
+ SciPy / OR-Tools
+ ByteTrack / BoT-SORT / Deep SORT
+ CBBA-Python / CA-CBBA 作为降级参考
+ 自研 D7 PN/LOS 导引核心
+ 自研 D6 结构化评估
```

最关键的工程原则仍然是：

```text
通信增强用于共享证据和提升仲裁质量；
不能让局部节点、局部相机或二级 cue 直接改写 global_track_id、AssignmentPlan 或导引目标。
```
