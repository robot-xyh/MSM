# Main 实现差距总审计

**审计来源**：D1-D7 子智能体分别对照 `subagent_reviews/*_REVIEW_AND_PLAN.md`、`C_UAS_MAINSTREAM_SOLUTIONS_AND_DIFFICULTIES.md` 和各自 `research_modules/` 代码完成自查。  
**审计目标**：列出共识算法与计划使用的开源代码哪些已经实现，哪些没有实现，为什么没有实现，以及缺少哪些条件。  
**边界**：本文只用于科研仿真、接口补齐和后续工程排期；不涉及真实硬件、实机处置、火控或绕过授权的自动动作。

## 1. 总体结论

当前项目已经形成一条可运行的轻量科研主线：

```text
D1 NumPy EKF/FusionAdapter
-> D2 GNN/Hungarian 关联与 ID 指标
-> D3 SciPy Hungarian 分配与迟滞
-> D4 C2Health + 主动/被动降级 + 轻量 CBBA
-> D5 几何投影门控 + 保守 TerminalAssociation
-> D7 PN / SimpleFlight 视觉 PNG gate
-> D6 离线 EpisodeMetrics / JSONL / Blocks replay 评估
```

已经落地的主要是**自研轻量实现和少量成熟 Python 科学计算库**：NumPy、SciPy、OpenCV `projectPoints`、AirSim `simGetDetections` metadata、SimpleFlight 控制、D7 delivery 包中的 YOLO+ByteTrack 可选链路。

尚未落地的主要是**完整外部工程栈或高阶研究对照**：Stone Soup、FilterPy、ROS 2 `tf2/message_filters`、OpenDroneID Core、MAVLink signing 验证、DDS Security、AprilTag、BoT-SORT、Deep SORT、SCRIMMAGE、TrackEval/py-motmetrics、正式 OR-Tools Min Cost Flow、完整 MIT/CA-CBBA 适配、PX4/MAVLink 主线控制。

未实现的共同原因主要有四类：

1. **当前阶段优先轻量可复现**：默认测试不依赖 ROS、Stone Soup、AirSim 实时服务、PX4 或 GPU。
2. **main 数据总线尚未完全冻结**：D1-D5 summary、D7 guidance summary、D6 EpisodeMetrics 之间仍有字段需要统一。
3. **真实图像/通信/身份源缺失**：MOT、Remote ID、MAVLink signing、AprilTag 需要真实图像帧、协议报文、密钥和时间同步。
4. **高阶算法需要基准场景支撑**：IMM、JPDA/MHT 完整版、FRPN、MPC、OSPA/HOTA 等应在 5v5 crossing、遮挡、主动降级和 AirSim replay 稳定后再做对照。

## 2. 横向开源/共识方案落地状态

| 共识/开源项 | 预期用途 | 当前状态 | 涉及模块 | 未实现/未完全实现原因 | 缺少条件 | 优先级 |
|---|---|---|---|---|---|---|
| EKF | 融合和航迹滤波主线 | **已实现轻量版**。D1 自研 NumPy EKF，D2 自研二维线性 Kalman | D1, D2 | 未使用 FilterPy/Stone Soup 后端 | 外部库对照接口、三维/非线性量测合同 | P0 已可用，P2 对照 |
| UKF | 强非线性量测升级 | 未实现 | D1, D2 | 当前 EKF/CV 已满足 phase-1；不想提前引依赖 | UKF 后端、sigma-point 参数、强非线性场景 | P2 |
| IMM-EKF/UKF | 高机动目标模型切换 | 未实现 | D1, D2 | 当前场景以 CV/二维基础关联为主 | CV/CA/CT 模型、转移概率、机动基准 | P2 |
| Stone Soup | 多目标跟踪、JPDA/MHT、轨迹融合、指标对照 | **占位/文档级**，未作为运行依赖 | D1, D2, D6 | 默认环境轻依赖；Stone Soup 对象不宜直接污染系统总线 | 安装版本、adapter、对照数据和指标门限 | P2 |
| FilterPy | EKF/UKF/IMM 原型 | **占位/可用性检查**，未调用 | D1, D2 | 已有自研 NumPy fallback | 依赖策略、状态/量测模型、测试容差 | P2/P3 |
| ROS 2 `tf2` | 坐标树、外参、frame 变换 | 未实现 | D1, D5, D7 | 当前是 Python 离线/AirSim runtime，不启动 ROS 图 | ROS 2 runtime、frame tree、带戳消息 | P3 |
| ROS 2 `message_filters` | 多传感器时间同步 | 未实现 | D1, D5 | 当前用 `measurement_timestamp/arrival_timestamp` 和离线 replay | topic schema、同步策略、bag/replay | P3 |
| SciPy `linear_sum_assignment` | Hungarian 关联/分配 | **已实现** | D2, D3 | 不适用 | 仅需保持 SciPy 依赖 | P0 |
| OR-Tools Min Cost Flow | 多容量/复杂约束分配 | 接口预留，未实现 | D3 | 当前 5v5 一对一 Hungarian 足够 | OR-Tools 依赖、容量/需求/禁配边结构 | P1/P2 |
| GNN/Hungarian | 多目标硬关联主线 | **已实现** | D2 | 不适用 | 需增加 5v5 dense/crossing 压测 | P0 |
| JPDA | 密集交叉软关联 | **轻量对照版**，非完整生产级 | D2 | 仅枚举小规模假设，不做完整概率混合更新 | Stone Soup 对照、密集交叉基准、参数标定 | P1 |
| MHT | 多扫描假设跟踪 | **有界 placeholder** | D2 | 完整 MHT 延迟/内存高，不适合资源节点 | N-scan pruning、分簇、中心算力假设 | P2 |
| PN 比例导引 | 单目标/中段默认导引 | **已实现** | D7 | 当前是二维经典 PN 和 SimpleFlight gate | 三维状态、D5/D3 门控、真实飞控约束 | P0 |
| Pure Pursuit | 对照 baseline | 行为片段存在，未成独立算法/实验 | D7 | 当前作为 LOS heading 保底，不是正式 baseline | 函数、配置、测试、PN 对照批量实验 | P1 |
| 改进 PN / FRPN | 高机动增强导引 | 未实现 | D7 | 当前先稳定经典 PN 与接口 | 目标加速度估计、公式选型、机动场景 | P1 |
| 视觉 PN / PNG | 末端视觉导引 | **部分实现** | D7 | 已有 bbox gate、LOS-rate、TTC/VM，仍非严格纯视觉闭环 | D5 locked、距离/闭合速度估计、相机标定 | P0/P1 |
| AirSim `simGetDetections` | CV 检测框输入 | **已使用** | D5, D7, main runtime | D5 不直接调 AirSim，只消费 fixture/replay；D7/main 调用 runtime | 稳定 detection schema、camera/object ID 映射 | P0 |
| OpenCV `projectPoints` | 图像投影和门控 | **部分使用** | D5 | D5 用 `projectPoints`，未做标定/solvePnP | 准确 K/R/t/dist、标定数据 | P0/P2 |
| OpenCV calibration / `solvePnP` | 相机标定、外参估计 | 未实现 | D5 | 当前假设 AirSim/runtime 提供相机参数 | 2D-3D 匹配点、标定图、PnP RANSAC | P2 |
| ByteTrack | 局部 MOT 默认候选 | **D5 未用；D7 delivery 可选** | D5, D7 | D5 仅 bbox fixture；D7 可用 YOLO+ByteTrack 但不在 main 主线 | 图像帧、YOLO 权重、class id、GPU/CPU 预算 | P1 |
| BoT-SORT | 运动相机 MOT | 未实现 | D5 | 需要相机运动补偿、ReID 和检测器链 | 图像序列、依赖、ReID 模型 | P2 |
| Deep SORT | 外观辅助 MOT | 未实现 | D5 | 当前小目标外观未建模 | embedding 模型、图像帧、IDSW 真值 | P2 |
| OpenDroneID / Remote ID | 友方身份正向声明 | **模拟实现** | D5 | 只解析 `protocol=OpenDroneID` 风格 dict，未接 Core C | 报文解码器、白名单、签名/位置一致性 | P1 |
| MAVLink signing | 消息来源认证 | 未在 D5 实现；D7 delivery 有 MAVLink 控制路径 | D5, D7 | 当前没有真实 MAVLink telemetry/signing key 管理 | MAVLink source、签名库、密钥策略 | P2 |
| DDS Security | ROS 2 中间件认证 | 未实现 | D5, main | 当前无 ROS 2/DDS runtime | enclave、证书、权限文件、节点映射 | P3 |
| AprilTag | 合作视觉标签 | 未实现 | D5 | 当前无图像帧和 tag detector | 图像流、tag ID 映射、误检评估 | P2 |
| MIT CBBA / CBBA-Python / CA-CBBA | 分布式降级对照 | 未接入；自研轻量 CBBA | D4 | 外部项目接口/许可证/依赖和 summary bus 不匹配 | adapter、同场景 benchmark、许可证审查 | P1 |
| 拍卖算法 | 分布式保底 baseline | 未单独实现 | D4 | 当前 CBBA 机制覆盖拍卖式思想，但无独立 baseline | bid/award/rollback 协议和测试 | P1 |
| 合同网协议 | 分布式任务协商对照 | 未实现 | D4 | 非 5v5 最小闭环必需 | announce-bid-award 状态机 | P2 |
| SCRIMMAGE | 大规模多智能体仿真 | 未实现 | D6/main | 当前优先 AirSim CV 5v5 和质点仿真 | SCRIMMAGE 输出样例、ID 映射、时钟对齐 | P3 |
| TrackEval / py-motmetrics | HOTA/IDF1/MOTA/MOTP | 未实现 | D6 | 当前先做本地可解释指标 | MOT 格式导出、帧级匹配、依赖版本 | P2 |
| Stone Soup metrics / OSPA/GOSPA/SIAP | 标准跟踪指标对照 | 未实现 | D6 | 需要 D1/D2 Stone Soup Track adapter | cutoff/order、匹配门限、坐标合同 | P2 |
| PX4 SITL / MAVLink body-rate | 更真实飞控闭环 | delivery 包有实验路径，main 未接入 | D7 | 当前主线选 SimpleFlight，避免飞控复杂度 | PX4 SITL、Offboard 状态机、推力/坐标标定 | P2 |

## 3. 各子模块核心结论

| 模块 | 已实现主线 | 关键未实现项 | 直接阻塞条件 | 详细文件 |
|---|---|---|---|---|
| D1 多传感器融合 | `SensorObservation -> NumPy EKF/FusionAdapter -> GlobalTrack`；雷达/声学/EO/合成 LiDAR；延迟补偿；协方差；AirSim dry-run | Stone Soup/FilterPy 后端、UKF/IMM、ROS2 tf2、真实 AirSim CV 直连、Track-to-Track fusion | JSONL/CSV schema、外部依赖、真实相机/传感器外参 | `subagent_reviews/D1_IMPLEMENTATION_GAP_AUDIT.md` |
| D2 数据关联 | GNN/Hungarian、马氏门控、二维 Kalman、轻量 JPDA/MHT、IDSW/连续性、dry-run adapter | 完整 EKF/UKF/IMM、Stone Soup/FilterPy、原生 3D NED、5v5 crossing 压测、自动关联风险滑窗 | D1->D2 强类型合同、5v5 replay、风险阈值 | `subagent_reviews/D2_IMPLEMENTATION_GAP_AUDIT.md` |
| D3 目标分配 | SciPy Hungarian、fallback DP、滚动重分配、迟滞、版本化计划、D5 feedback helper、AirSim dry-run | OR-Tools Min Cost Flow、`AssignmentValiditySummary`、D5 feedback 自动写回代价、AirSim runtime 直连 | D5/D6 重复锁定聚合、D4 主动降级字段、复杂约束定义 | `subagent_reviews/D3_IMPLEMENTATION_GAP_AUDIT.md` |
| D4 降级接管 | C2Health、被动降级、主动降级、二级侦察节点模型、CommunicationSummary、轻量 CBBA、中心恢复合并 | MIT/CA-CBBA 适配、拍卖/合同网、真实视频 cue adapter、二级节点生命周期、D1-D5 summary 自动适配 | main 统一 EventRecord、D1-D5 summary、二级 heartbeat/coverage/link freshness | `subagent_reviews/D4_IMPLEMENTATION_GAP_AUDIT.md` |
| D5 末端视觉配准 | 单相机几何投影、马氏门控、保守 `locked/ambiguous/hold/reacquire`、模拟身份、跨视角摘要、禁止改写 ID | ByteTrack/BoT-SORT/Deep SORT、tf2、OpenDroneID Core、MAVLink signing、AprilTag、solvePnP、AirSim stress 真实调用 `TerminalAssociator` | 图像帧/检测器、协议报文、相机标定、D4/D5 stress 输入结构 | `subagent_reviews/D5_IMPLEMENTATION_GAP_AUDIT.md` |
| D6 评估指标 | 本地 EpisodeMetrics、JSONL、Blocks replay、POD/FAR/RMSE/IDSW/assignment/failover/terminal/communication、批量图表 | Stone Soup metrics、TrackEval、SCRIMMAGE、OSPA/GOSPA/HOTA/IDF1、D7 拦截成功指标 adapter、主动降级细分 | 标准帧级匹配表、D4 metadata、D7 guidance summary schema | `subagent_reviews/D6_IMPLEMENTATION_GAP_AUDIT.md` |
| D7 比例导引 | 经典二维 PN、离线 radar->vision 记录、SimpleFlight 2v2 actor 拦截、AirSim detect、视觉 PNG gate、assigned collision 判据 | D5 locked + D3 version 门控、Pure Pursuit 正式 baseline、FRPN、严格视觉 PN、PX4/MAVLink 主线、YOLO+ByteTrack 主线、D6 guidance adapter | `AssignmentGuidanceBinding`、D5 TerminalAssociation 流、授权状态、相机/机动能力模型 | `subagent_reviews/D7_IMPLEMENTATION_GAP_AUDIT.md` |

## 4. 当前最重要的缺口

### P0：端到端闭环接口缺口

1. **D5 到 D7 的门控未接上**  
   D7 进入视觉末端还没有严格要求 D5 `TerminalAssociation(decision_state="locked")`、`assigned_global_track_id` 与 D3 一致、版本一致和授权有效。

2. **D3 到 D7 的版本化绑定缺失**  
   AirSim 控制闭环当前按初始 pair/assigned object 绑定，不是完整 `AssignmentPlan(plan_id/version)` 驱动。

3. **D4 主动降级输入仍需 main 适配**  
   D4 已有 `ActiveDegradationArbiter`，但 D1 协方差、D2 ID switch、D3 plan validity、D5 terminal mismatch 还没有稳定自动转为 D4 summary。

4. **D5 AirSim stress 没有真实调用正式关联器**  
   `d4d5_stress.py` 目前手工构造 `TerminalAssociation`，验证了 D4 case 和 D5 evidence 格式，但没有验证 `TerminalAssociator.decide()` 在 AirSim replay 中的几何门控结果。

5. **D6 还没有正式消费 D7 拦截闭环结果**  
   D7 已输出 `control_commands.csv` 和 `intercept_summary.json`，D6 还缺 guidance/intercept adapter，把最小距离、碰撞对象、成功类型、gate reject 纳入 `EpisodeMetrics`。

### P1：开源对照与压力测试缺口

1. D2 需要 deterministic 5v5 crossing/dense fixture，比较 GNN、轻量 JPDA、轻量 MHT 的 IDSW 与耗时。
2. D4 需要 CBBA vs auction vs centralized Hungarian gap 的同场景 benchmark。
3. D5 需要先把 ByteTrack 作为可选 adapter 接入 `LocalVisualTrack`，再评估 BoT-SORT/Deep SORT。
4. D7 需要正式 Pure Pursuit baseline 和 PN/visual PN 对照实验。
5. D6 需要把 D4 主动降级和 D7 guidance summary 变成正式指标，再考虑 TrackEval/Stone Soup metrics。

## 5. 建议实施顺序

1. **先补 P0 数据合同**  
   定义 `AssignmentGuidanceBinding`、`D4DecisionRecord`、`TerminalConsistencySummary`、`GuidanceRecord`/`InterceptSummary` 的统一字段。

2. **把 D5 正式关联器接入 AirSim D4/D5 stress**  
   从 replay frame 构造 `GlobalTrack[]`、`Assignment`、`CameraModel`、`LocalVisualTrack[]`，调用 `TerminalAssociator.decide()`，保留当前手工 case 作为对照。

3. **把 D7 视觉末端切换改为由 D3+D5+D4 共同授权**  
   只有 D3 plan/version 有效、D5 locked 且 ID 一致、D4 没有 hold/reassign、相机/机动 gate 通过时，才允许进入视觉 PNG。

4. **补 D6 guidance/intercept adapter**  
   读取 D7 `control_commands.csv` 和 `intercept_summary.json`，输出 `intercept_success_count`、`min_range_m`、`time_to_intercept_s`、`collision_intercept_count`、`gate_reject_count`。

5. **随后做开源对照，不替换主线**  
   Stone Soup、FilterPy、TrackEval、ByteTrack、MIT/CA-CBBA、OR-Tools 都建议以 optional benchmark/adapter 方式接入，先生成同场景对照报告，再决定是否进入默认运行路径。

## 6. 子智能体交付文件

- `subagent_reviews/D1_IMPLEMENTATION_GAP_AUDIT.md`
- `subagent_reviews/D2_IMPLEMENTATION_GAP_AUDIT.md`
- `subagent_reviews/D3_IMPLEMENTATION_GAP_AUDIT.md`
- `subagent_reviews/D4_IMPLEMENTATION_GAP_AUDIT.md`
- `subagent_reviews/D5_IMPLEMENTATION_GAP_AUDIT.md`
- `subagent_reviews/D6_IMPLEMENTATION_GAP_AUDIT.md`
- `subagent_reviews/D7_IMPLEMENTATION_GAP_AUDIT.md`

