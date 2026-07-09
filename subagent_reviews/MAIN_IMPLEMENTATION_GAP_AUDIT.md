# Main 实现差距总审计

**审计来源**：D1-D7 子智能体分别对照 `subagent_reviews/*_REVIEW_AND_PLAN.md`、`C_UAS_MAINSTREAM_SOLUTIONS_AND_DIFFICULTIES.md` 和各自 `research_modules/` 代码完成自查。
**审计目标**：列出共识算法与计划使用的开源代码哪些已经实现，哪些没有实现，为什么没有实现，以及缺少哪些条件。
**边界**：本文只用于科研仿真、接口补齐和后续工程排期；不涉及真实硬件、实机处置、火控或绕过授权的自动动作。

**P0/P1 状态入口**：`subagent_reviews/MAIN_P0_P1_GAP_STATUS.md` 集中维护当前 P0/P1 owner、缺口、缺少条件和验收口径。当前未发现新的 P0 阻塞断链；2026-07-08 已补齐 main runtime bus 执行指标回灌、D4 软风险防抖、无冲突 D5 重捕获不降级策略、`request_center_replan -> D3 new plan version -> D7 gate`、D5 feedback 写回 D3、二级接管 plan owner/version、D7 N-pair runtime bus，以及 controlled intercept 中心/二级重分配到视觉 PNG 的 gate 回归。main runtime 已新增 P1 D4/D5 calibration sweep，并自动调用 D6 生成标准 records/summary/Markdown 报告 bundle。最新 5v5 registration calibration v2 证明 radar cue + 机动高空侦察云台指向已解决相机姿态/投影有效性问题，并恢复稳定 cross-view registration；剩余 P1 瓶颈转为二级网络全目标覆盖不足、detect 到 global-track 的长期阈值标定、真实 AirSim 多 seed 数据和 D6 长期趋势积累。

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

已经落地的主要是**自研轻量实现和少量成熟 Python 科学计算库**：NumPy、SciPy、OpenCV `projectPoints`、AirSim `simGetDetections` metadata、D5 YOLOv8 + ByteTrack/BoT-SORT/IoU fallback adapter、SimpleFlight 控制、D7 delivery 包中的 YOLO+ByteTrack 可选链路。

**2026-07-08 子智能体复核状态**：D1-D7 已分别重审并更新各自 PLAN/GAP 文件，所有子 GAP 均明确拆分为“已实现、部分实现、未实现、未实现原因、缺少条件、下一步优先级”。本轮确认：D1 的 replay schema v1、legacy JSONL、最小 CSV reader/replay、latency/OOSM audit 和区域质量摘要已实现；D2 的 replay helper、5v5 dense/crossing fixture、风险阈值敏感性和显式 ID 指标已实现；D3 的 D5 feedback writeback、secondary takeover DTO/helper、D7 binding、owner/version/source metadata 和 D6 export 已实现；D4 的主动降级硬/软风险分层、二级节点 lifecycle、secondary takeover metadata、D5 evidence 到 CBBA 和 cost gap helper 已实现；D5 的几何日志、handoff advisory、一致性窗口、truth ID 在线隔离、YOLO/ByteTrack 离线 schema adapter、可运行 YOLOv8 + ByteTrack/BoT-SORT/IoU fallback adapter 已实现；D6 的 execution/contract 双口径、实际规模分组、主动降级精度和 D7 replay 指标已实现；D7 的 runtime bus、comparison/replay helper、N-pair 状态、D4 gate blocking、owner/version gate 和 terminal contract gate 已实现。

尚未落地的主要是**完整外部工程栈或高阶研究对照**：Stone Soup、FilterPy、ROS 2 `tf2/message_filters`、OpenDroneID Core、MAVLink signing 验证、DDS Security、AprilTag、BoT-SORT、Deep SORT、SCRIMMAGE、TrackEval/py-motmetrics、正式 OR-Tools Min Cost Flow、完整 MIT/CA-CBBA 适配、PX4/MAVLink 主线控制。

未实现的共同原因主要有四类：

1. **当前阶段优先轻量可复现**：默认测试不依赖 ROS、Stone Soup、AirSim 实时服务、PX4 或 GPU。
2. **main runtime bus 接口基线已接入**：AirSim runtime 已在同一 episode 中持续写入 D1-D7 summary/record 和 D6 JSONL；2026-07-08 已把执行拦截结果回灌到正式 main bus metrics，接入 D5 feedback、二级接管 owner/version 和 D7 runtime bus，并保留 raw contract metrics；P1 calibration sweep 已自动回灌 D6 标准 CSV/JSON/Markdown 报告 bundle；下一步仍需真实 Blocks 多 seed 校准。
3. **二级侦察看清不等于可接管**：2026-07-08 5v5 registration calibration v2 中，二级云台指向成功率为 1.0，`projection_valid_rate=1.0`，几何门通过率约 0.474，稳定跨视角注册约 51/55/53，cross-view association 为 4/4/5；但 `secondary_network_joint_full_view_frame_rate` 均值仍约 0.048，联合覆盖约 0.771，主要断点是 `not_all_targets_visible` / `network_union_incomplete`。它说明二级节点已能提供有效注册证据，但不能绕过 D3/D4/D5 的分配、仲裁和视觉 PNG gate。
4. **真实图像/通信/身份源仍需标定**：D5 已能运行 YOLOv8 + MOT 并由 main runtime 显式接线；Remote ID、MAVLink signing、AprilTag 仍需要真实报文、密钥和时间同步，YOLO/MOT 仍需要 AirSim 多 seed 阈值标定。
5. **高阶算法需要基准场景支撑**：IMM、JPDA/MHT 完整版、FRPN、MPC、OSPA/HOTA 等应在 5v5 crossing、遮挡、主动降级和 AirSim replay 稳定后再做对照。

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
| Pure Pursuit | 对照 baseline | **已实现轻量 baseline**。D7 提供 `compute_pure_pursuit_command()` 和 `GuidanceConfig.guidance_law=\"pure_pursuit\"` | D7 | 未直接引入 PythonRobotics，有意保持轻依赖 | 多 seed PN/Pure Pursuit 对照报告、AirSim controlled 选择开关 | P1 已完成基线 |
| 改进 PN / FRPN | 高机动增强导引 | 未实现 | D7 | 当前先稳定经典 PN 与接口 | 目标加速度估计、公式选型、机动场景 | P1 |
| 视觉 PN / PNG | 末端视觉导引 | **部分实现** | D7 | 已有 bbox gate、LOS-rate、TTC/VM，仍非严格纯视觉闭环 | D5 locked、距离/闭合速度估计、相机标定 | P0/P1 |
| AirSim `simGetDetections` | CV 检测框输入 | **已使用** | D5, D7, main runtime | D5 不直接调 AirSim，只消费 fixture/replay；D7/main 调用 runtime | 稳定 detection schema、camera/object ID 映射 | P0 |
| OpenCV `projectPoints` | 图像投影和门控 | **已实现单相机主线**。D5 优先调用 `cv2.projectPoints`，无 OpenCV 时有针孔 fallback，并传播像素协方差 | D5 | 未实现 calibration/solvePnP/跨相机联合优化 | 准确 K/R/t/dist、标定样本、PnP 2D-3D 对应 | P0 已可用，P2 标定增强 |
| OpenCV calibration / `solvePnP` | 相机标定、外参估计 | 未实现 | D5 | 当前假设 AirSim/runtime 提供相机参数 | 2D-3D 匹配点、标定图、PnP RANSAC | P2 |
| YOLOv8 + ByteTrack/BoT-SORT | 局部检测/MOT 默认候选 | **P1 已接入显式运行路径**。D5 `YoloMotAdapter` 可加载 `best.pt`，优先 ByteTrack/BoT-SORT，失败时 deterministic IoU fallback；main runtime 可用 `--detection-backend yolo` 将内存图像送入 D5，并转换为现有 detection contract | D5, main runtime, D7 | 默认仍不保存 PNG；MOT ID 只作为 `LocalVisualTrack.local_track_id`，不得替代 `global_track_id` | AirSim 多 seed 阈值、class id、GPU/CPU 预算、MOT IDSW 标签 | P1 接线已完成，P1/P2 标定 |
| BoT-SORT | 运动相机 MOT | 未实现 | D5 | 需要相机运动补偿、ReID 和检测器链 | 图像序列、依赖、ReID 模型 | P2 |
| Deep SORT | 外观辅助 MOT | 未实现 | D5 | 当前小目标外观未建模 | embedding 模型、图像帧、IDSW 真值 | P2 |
| OpenDroneID / Remote ID | 友方身份正向声明 | **模拟实现** | D5 | 只解析 `protocol=OpenDroneID` 风格 dict，未接 Core C | 报文解码器、白名单、签名/位置一致性 | P1 |
| MAVLink signing | 消息来源认证 | 未在 D5 实现；D7 delivery 有 MAVLink 控制路径 | D5, D7 | 当前没有真实 MAVLink telemetry/signing key 管理 | MAVLink source、签名库、密钥策略 | P2 |
| DDS Security | ROS 2 中间件认证 | 未实现 | D5, main | 当前无 ROS 2/DDS runtime | enclave、证书、权限文件、节点映射 | P3 |
| AprilTag | 合作视觉标签 | 未实现 | D5 | 当前无图像帧和 tag detector | 图像流、tag ID 映射、误检评估 | P2 |
| MIT CBBA / CBBA-Python / CA-CBBA | 分布式降级对照 | 未接入；自研轻量 CBBA | D4 | 外部项目接口/许可证/依赖和 summary bus 不匹配；本轮 P1 明确暂不构造外部开源算法 | adapter、同场景 benchmark、许可证审查 | P2 |
| 拍卖算法 | 分布式保底 baseline | 未单独实现 | D4 | 当前 CBBA 机制覆盖拍卖式思想，但无独立 baseline | bid/award/rollback 协议和测试 | P1 |
| 合同网协议 | 分布式任务协商对照 | 未实现 | D4 | 非 5v5 最小闭环必需 | announce-bid-award 状态机 | P2 |
| SCRIMMAGE | 大规模多智能体仿真 | 未实现 | D6/main | 当前优先 AirSim CV 5v5 和质点仿真 | SCRIMMAGE 输出样例、ID 映射、时钟对齐 | P3 |
| TrackEval / py-motmetrics | HOTA/IDF1/MOTA/MOTP | 未实现 | D6 | 当前先做本地可解释指标 | MOT 格式导出、帧级匹配、依赖版本 | P2 |
| Stone Soup metrics / OSPA/GOSPA/SIAP | 标准跟踪指标对照 | 未实现 | D6 | 需要 D1/D2 Stone Soup Track adapter | cutoff/order、匹配门限、坐标合同 | P2 |
| PX4 SITL / MAVLink body-rate | 更真实飞控闭环 | delivery 包有实验路径，main 未接入 | D7 | 当前主线选 SimpleFlight，避免飞控复杂度 | PX4 SITL、Offboard 状态机、推力/坐标标定 | P2 |

## 3. 各子模块核心结论

| 模块 | 已实现主线 | 关键未实现项 | 直接阻塞条件 | 详细文件 |
|---|---|---|---|---|
| D1 多传感器融合 | `SensorObservation -> NumPy EKF/FusionAdapter -> GlobalTrack`；measurement/arrival timestamp；NED 六维状态；协方差；雷达/声学/EO/合成 LiDAR；延迟补偿；AirSim dry-run；Blocks JSONL reader/replay；replay schema v1/legacy JSONL；最小 CSV reader/replay；`TrackUncertaintySummary`；`LatencyAuditSummary`；`FusionQualityRegionSummary`；source de-dup；N-target 输入 | Stone Soup/FilterPy 后端、UKF/IMM、ROS2 tf2/message_filters、D1 包内真实 AirSim CV 直连、Track-to-Track fusion、更多真实 Blocks/CV fixture | 真实相机/传感器外参、稳定 detection schema、外部依赖、跨节点相关性策略、D6 长期批量 schema | `subagent_reviews/D1_IMPLEMENTATION_GAP_AUDIT.md` |
| D2 数据关联 | GNN/Hungarian、马氏门控、二维 Kalman、轻量 JPDA/MHT、IDSW/连续性、dry-run adapter、`crossing_dense_5v5`、风险滑窗、D1 adapter | 完整 EKF/UKF/IMM、Stone Soup/FilterPy、原生 3D NED、真实 AirSim CV replay 压测 | 5v5 replay 样本、风险阈值、三维跟踪策略 | `subagent_reviews/D2_IMPLEMENTATION_GAP_AUDIT.md` |
| D3 目标分配 | SciPy Hungarian、fallback DP、滚动重分配、迟滞、版本化计划、D5 feedback helper、D7 `AssignmentGuidanceBinding`、`AssignmentValiditySummary`、D6 assignment record export、AirSim dry-run、main episode bus plan/version 输出 | OR-Tools Min Cost Flow、D5 feedback 自动写回真实代价 | D5/D6 重复锁定聚合校准、复杂约束定义 | `subagent_reviews/D3_IMPLEMENTATION_GAP_AUDIT.md` |
| D4 降级接管 | C2Health、被动降级、主动降级、二级侦察节点模型、`SecondaryNodeLifecycleSummary`、CommunicationSummary、主动降级防抖、轻量 CBBA、中心恢复合并、D4 arbitration adapter、D6-compatible event metadata、main episode bus D4 event 写入 | MIT/CA-CBBA 适配、独立拍卖/合同网、真实视频 cue adapter | 二级 heartbeat/coverage/link freshness 的真实 Blocks 多 seed 校准 | `subagent_reviews/D4_IMPLEMENTATION_GAP_AUDIT.md` |
| D5 末端视觉配准 | `GlobalTrack -> CameraModel -> projected image point -> LocalVisualTrack -> TerminalAssociation`；OpenCV `projectPoints`/fallback；马氏门控；保守 `locked/ambiguous/hold/reacquire`；AirSim bbox adapter；YOLOv8 + MOT runtime adapter；truth ID 在线隔离；二级 cue；跨视角摘要；`TerminalConsistencySummary`；视觉 PNG handoff advisory；main episode bus terminal record；禁止改写 ID | Deep SORT/ReID、OpenDroneID Core、MAVLink signing、DDS Security、AprilTag、solvePnP/calibration、ROS2 tf2、跨相机几何联合优化 | 协议报文/密钥、相机标定样本、二级节点真实 pose/detection、真实 AirSim 多 seed YOLO/MOT 阈值标定 | `subagent_reviews/D5_IMPLEMENTATION_GAP_AUDIT.md` |
| D6 评估指标 | 本地 EpisodeMetrics、JSONL、Blocks replay、POD/FAR/RMSE/IDSW/assignment/failover/terminal/communication、D4 active/passive degradation、D7 intercept/guidance time-series adapter、批量图表和分组报告 | Stone Soup metrics、TrackEval、SCRIMMAGE、OSPA/GOSPA/HOTA/IDF1、主动降级必要性标签 | 标准帧级匹配表、真实 D4 metadata、D7 多 seed guidance records/summaries | `subagent_reviews/D6_IMPLEMENTATION_GAP_AUDIT.md` |
| D7 比例导引 | 经典二维 PN、雷达中段 PN、Pure Pursuit baseline、离线 radar->vision 质点闭环、AirSim phase-1 dry-run、SimpleFlight 视觉 PNG gate、TTC/VM 捷联导引核心、D3/D4/D5 terminal contract gate、显式 handoff/hold/reacquire/revoke、N-pair 独立 filter 单测、D6 guidance time-series 字段、main episode bus D7 guidance event 写入 | FRPN/augmented PN、严格 3D PN、严格视觉闭环、PX4/MAVLink 主线、YOLO+ByteTrack 主线检测、MPC/NMPC、ViSP/ROS2 | D5 状态迁移真实标定、相机/距离/闭合速度估计、平台动力学/飞控约束、多 seed 对照 | `subagent_reviews/D7_IMPLEMENTATION_GAP_AUDIT.md` |

## 4. 当前最重要的缺口

### 4.1 已完成的 P0/P1 接口基线

1. **D1 融合合同已成型**
   `SensorObservation`、`measurement_timestamp/arrival_timestamp`、协方差、NED 六维状态、fixed-lag 延迟补偿、雷达距离相关协方差、source lineage 去重、`TrackUncertaintySummary` 和 Blocks JSONL reader/replay 已实现。

2. **D2 关联与身份指标已成型**
   GNN/Hungarian、马氏门控、二维 Kalman、轻量 JPDA/MHT 对照、`id_switch_count`、continuity、duplicate assignment、D1 adapter、AirSim dry-run adapter、`crossing_dense_5v5` 和风险滑窗已实现。

3. **D3 分配到 D7 的版本化合同已成型**
   SciPy Hungarian、fallback DP、迟滞、stale plan 拒绝、版本化 `AssignmentPlan`、D5 feedback helper、`AssignmentGuidanceBinding`、`AssignmentValiditySummary` 和 D6-compatible `AssignmentRecord` 导出已实现。

4. **D4 主动/被动降级仲裁已成型**
   `C2Health`、被动降级、主动降级、二级节点 lifecycle、communication freshness、D1/D2/D3/D5 evidence adapter、D6 event metadata、轻量 CBBA、D7 two-stage secondary handoff 和中心恢复合并基础版已实现。2026-07-07 已增加硬/软风险分层：`d3_assignment_not_current/stale` 仍触发中心重规划，`d3_assignment_cost_margin_low` 与早期 D5 低置信度只进入观察；无 observed mismatch、资源错配、重复锁定或友方冲突的持续 D5 `ambiguous/reacquire` 不再造成名义场景每帧 `request_center_replan` 或分布式降级。

5. **D5 末端视觉配准安全合同已成型**
   OpenCV `projectPoints`/fallback、像素协方差传播、马氏门控、`LocalVisualTrack`、`TerminalAssociation`、`IdentityClaim`、AirSim/YOLO bbox schema adapter、AirSim truth ID 在线隔离、二级 cue、跨视角重复锁定风险、`TerminalConsistencySummary` 和视觉 PNG handoff advisory 已实现。

6. **D6 离线评估主线已成型**
   `EpisodeMetrics` 显式保留实际 `drone_count/resource_count/target_count/camera_count`，并可消费 track/assignment/event/link/terminal、Blocks replay、D4 active/passive degradation、D7 intercept replay、D7 guidance time-series、批量 CSV/Markdown/PNG 报告。

7. **D7 PN/PNG 导引合同已成型**
   经典二维 PN、雷达中段 PN、Pure Pursuit baseline、离线 radar-to-vision 质点闭环、SimpleFlight 视觉 PNG gate、TTC/VM 捷联导引核心、D3/D4/D5 terminal contract gate、handoff/hold/reacquire/revoke 状态和 N-pair 独立 filter 单测已实现。

### 4.2 当前最关键的未闭合项

1. **main runtime bus 已完成接口闭合，仍需真实多 seed 校准**
   `research_modules/airsim_runtime/episode_bus.py` 已由 main 串接 D1 track、D2 risk、D3 plan/version、D4 action、D5 terminal decision、D7 pair state 和 D6 collector，并在每个 Blocks episode 输出 `main_episode_bus.jsonl`、ticks、metrics 和 summary。执行拦截时，main 还会把 `control_commands.csv` 和 `intercept_summary.json` 的成功数、碰撞拦截数、guidance law 和 terminal reject 回灌到正式 metrics，同时保留 contract-only metrics。2026-07-08 已补齐 D5 terminal feedback 到 D3、D4 二级接管 owner/version 到 D3/D7，以及 D7 N-pair runtime summary。P1 calibration sweep 已自动调用 D6 `AirSimCalibrationReportGenerator` 扫描 persisted sequence/episode artifacts，输出标准 CSV/JSON/Markdown 报告。未闭合的是在真实 Blocks 长时/多 seed 条件下校准阈值、状态迁移和降级必要性标签。

2. **N-pair 真实控制状态机已有 main 接线，仍需真实多 seed 校准**
   D7 已支持每个 assignment pair 独立 filter，main runtime bus 已按每个有效 pair 注入 `AssignmentGuidanceBinding`、D4 permission/action、D5 `TerminalAssociation`、资源状态、目标估计并写 D6 guidance log。下一步重点不是再补接口，而是在真实 Blocks 多 seed 下校准终端切换、重捕获和拒绝原因分布。

3. **D4/D5/D7 的状态迁移需要真实 episode 校准**
   `locked/ambiguous/hold/reacquire`、锁定丢失、重捕获、friend conflict、duplicate lock、`request_center_replan`、`degrade_to_secondary`、`degrade_to_distributed` 和 terminal contract reject 需要在多 seed AirSim replay 中统一记录与评估。本轮已修正软 cost margin 造成的 replan 抖动，并把“无冲突持续重捕获”与“真实 terminal mismatch”分离，但阈值仍需 5v5/multi-seed 统计确认。

4. **机动高空侦察二级节点仍需覆盖/配准校准**
   5v5 registration calibration v2 已验证二级节点 `mobile_recon_gimbal`、`radar_global_track_cue`、200 m 高差、110 deg FOV 和 1920x1080 观测链路能稳定出图、保持有效投影，并把二级 detect 转成稳定 cross-view registration。当前未闭合的不是姿态/投影，而是二级网络同帧全目标覆盖：`secondary_network_joint_full_view_frame_rate` 均值约 0.048，主要断点为 `not_all_targets_visible` / `network_union_incomplete`。下一步应优先校准二级站位/扫描策略、coverage cell、cue freshness、外参/时间戳和 D6 coverage funnel 指标。

5. **YOLO/MOT 已有显式运行路径，真实协议/标定链路仍待推进**
   D5 YOLOv8 + ByteTrack/BoT-SORT/IoU fallback adapter 和 main `--detection-backend yolo` 接线已完成；Deep SORT/ReID、OpenDroneID Core、MAVLink signing、DDS Security、AprilTag、solvePnP/calibration 和 ROS2 tf2/message_filters 仍需真实图像/报文、密钥、相机外参、时间同步和依赖隔离。

6. **高阶算法仍需作为 optional benchmark 接入**
   UKF/IMM、完整 JPDA/MHT、Stone Soup、FilterPy、OR-Tools Min Cost Flow、MIT/CA-CBBA、TrackEval/py-motmetrics、OSPA/GOSPA/HOTA/IDF1、FRPN、MPC、PX4/MAVLink 都不应直接替换当前轻量主线，应先在同场景对照报告中验证收益。

### 4.3 直接下一步缺口

1. main 继续用 `MainAirSimEpisodeBus` 做 Blocks episode 的统一 DTO/record 总线，并保持 `main_episode_bus.jsonl` 可由 D6 `load_episode_log_jsonl()` 反读。
2. main 在真实 Blocks 多 seed 中校准 D3 `AssignmentPlan`、D3 `AssignmentGuidanceBinding`、D4 action、D5 terminal decision 和 D7 guidance records 的状态迁移阈值。
3. main/AirSim runtime 继续固化 Blocks JSONL/replay schema，保留实际目标数、资源数、相机数、bbox、相机内外参、truth offline label、plan/version、D4/D5/D7 状态字段，并避免在线 D5 使用 truth ID。
4. main/D4/D5/D6 继续跑机动高空侦察节点 5v5 stress，分别统计单相机全局视野率、二级网络联合覆盖率、detect-to-registration 转换率、`secondary_detect_available_but_not_registered` 和 cross-view association。
5. D5 已实现 YOLOv8 + MOT runtime adapter，main 已接入显式 YOLO 检测后端。下一步用真实 AirSim 多 seed 校准 `best.pt`、置信度、tracker backend、目标尺度和 FOV 条件；adapter 只输出 `LocalVisualTrack`，不允许 tracker ID 替代 `global_track_id`。
6. D6 已实现主动降级必要性最小指标口径，main P1 sweep 已自动生成 D6 标准报告 bundle。下一步要求 main/D4 在真实 multi-seed episode 中持续写出 review/window 字段，形成可比较的 active degradation precision 和 unnecessary active degradation count。

## 5. 建议实施顺序

1. **保持 P0 合同回归**
   继续用 D3-D7 与 AirSim runtime 测试覆盖 `AssignmentGuidanceBinding`、`D4DecisionRecord`、`TerminalAssociation`、D7 terminal gate 和 D6 intercept adapter。

2. **用 main runtime bus 做真实 episode 校准**
   main 已把 D3 plan/version、D4 action、D5 terminal decision、资源状态和 D7 控制 pair 合并到同一个 AirSim episode state machine，并写入 D6 已支持的分组/降级/guidance 字段；下一步用真实 Blocks 多 seed 校准阈值和报告口径。

3. **跑多 seed 校准**
   使用单次 Blocks 启动 reset 循环跑 CV 5v5、D4/D5 stress 和 2v2 intercept，校准 D4 防抖、D5 一致性、D7 terminal handoff 和 D6 分组指标。

4. **随后做开源对照，不替换主线**
   Stone Soup、FilterPy、TrackEval、ByteTrack、MIT/CA-CBBA、OR-Tools 都建议以 optional benchmark/adapter 方式接入，先生成同场景对照报告，再决定是否进入默认运行路径。

## 6. 子智能体交付文件

- `subagent_reviews/D1_IMPLEMENTATION_GAP_AUDIT.md`
- `subagent_reviews/D2_IMPLEMENTATION_GAP_AUDIT.md`
- `subagent_reviews/D3_IMPLEMENTATION_GAP_AUDIT.md`
- `subagent_reviews/D4_IMPLEMENTATION_GAP_AUDIT.md`
- `subagent_reviews/D5_IMPLEMENTATION_GAP_AUDIT.md`
- `subagent_reviews/D6_IMPLEMENTATION_GAP_AUDIT.md`
- `subagent_reviews/D7_IMPLEMENTATION_GAP_AUDIT.md`
