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

**2026-07-03 P1 补充状态**：D1-D7 已完成本轮不引入重型开源栈的 P1 接口补齐：D1 增加不确定性摘要、Blocks JSONL replay、可配置雷达协方差和 source lineage 去重；D2 增加 `crossing_dense_5v5`、GNN/JPDA/MHT 对照、风险滑窗和 D1 adapter；D3 增加 `AssignmentValiditySummary`、D6 assignment record export 和更完整末端反馈 metadata；D4 增加二级节点生命周期、主动降级防抖和 D6-compatible event metadata；D5 增加 `TerminalConsistencySummary`、丢锁/重捕获摘要、跨视角重复锁定风险和二级 cue 规则；D6 增加主动/被动降级、D4 CSV、D7 guidance time-series 和分组报告字段；D7 增加 Pure Pursuit baseline、显式 handoff/hold/reacquire/revoke 状态和 terminal contract reject log；main AirSim runtime 的 batch seeds 改为单次 Blocks 启动 + reset 循环。

尚未落地的主要是**完整外部工程栈或高阶研究对照**：Stone Soup、FilterPy、ROS 2 `tf2/message_filters`、OpenDroneID Core、MAVLink signing 验证、DDS Security、AprilTag、BoT-SORT、Deep SORT、SCRIMMAGE、TrackEval/py-motmetrics、正式 OR-Tools Min Cost Flow、完整 MIT/CA-CBBA 适配、PX4/MAVLink 主线控制。

未实现的共同原因主要有四类：

1. **当前阶段优先轻量可复现**：默认测试不依赖 ROS、Stone Soup、AirSim 实时服务、PX4 或 GPU。
2. **main 数据总线仍需真实 episode 校验**：D1-D7 已有 P1 summary/record 基线，下一步是让 AirSim/integrated runtime 在同一 episode 中持续写入这些字段并做多 seed 校准。
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
| Pure Pursuit | 对照 baseline | **已实现轻量 baseline**。D7 提供 `compute_pure_pursuit_command()` 和 `GuidanceConfig.guidance_law=\"pure_pursuit\"` | D7 | 未直接引入 PythonRobotics，有意保持轻依赖 | 多 seed PN/Pure Pursuit 对照报告、AirSim controlled 选择开关 | P1 已完成基线 |
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
| D1 多传感器融合 | `SensorObservation -> NumPy EKF/FusionAdapter -> GlobalTrack`；雷达/声学/EO/合成 LiDAR；延迟补偿；协方差；AirSim dry-run；`TrackUncertaintySummary`；Blocks JSONL replay；source de-dup | Stone Soup/FilterPy 后端、UKF/IMM、ROS2 tf2、真实 AirSim CV 直连、Track-to-Track fusion | CSV schema、外部依赖、真实相机/传感器外参、跨节点相关性 | `subagent_reviews/D1_IMPLEMENTATION_GAP_AUDIT.md` |
| D2 数据关联 | GNN/Hungarian、马氏门控、二维 Kalman、轻量 JPDA/MHT、IDSW/连续性、dry-run adapter、`crossing_dense_5v5`、风险滑窗、D1 adapter | 完整 EKF/UKF/IMM、Stone Soup/FilterPy、原生 3D NED、真实 AirSim CV replay 压测 | 5v5 replay 样本、风险阈值、三维跟踪策略 | `subagent_reviews/D2_IMPLEMENTATION_GAP_AUDIT.md` |
| D3 目标分配 | SciPy Hungarian、fallback DP、滚动重分配、迟滞、版本化计划、D5 feedback helper、D7 `AssignmentGuidanceBinding`、`AssignmentValiditySummary`、D6 assignment record export、AirSim dry-run | OR-Tools Min Cost Flow、D5 feedback 自动写回真实代价、AirSim runtime 直连 | D5/D6 重复锁定聚合、D4 主动降级事件、复杂约束定义 | `subagent_reviews/D3_IMPLEMENTATION_GAP_AUDIT.md` |
| D4 降级接管 | C2Health、被动降级、主动降级、二级侦察节点模型、`SecondaryNodeLifecycleSummary`、CommunicationSummary、主动降级防抖、轻量 CBBA、中心恢复合并、D4 arbitration adapter、D6-compatible event metadata | MIT/CA-CBBA 适配、独立拍卖/合同网、真实视频 cue adapter、main bus 写入 | main 统一调用 D4 adapter、二级 heartbeat/coverage/link freshness 的真实 episode 维护 | `subagent_reviews/D4_IMPLEMENTATION_GAP_AUDIT.md` |
| D5 末端视觉配准 | 单相机几何投影、马氏门控、保守 `locked/ambiguous/hold/reacquire`、模拟身份、跨视角摘要、`TerminalConsistencySummary`、丢锁/重捕获、重复锁定风险、禁止改写 ID、AirSim stress 调用正式 `TerminalAssociator` | ByteTrack/BoT-SORT/Deep SORT、tf2、OpenDroneID Core、MAVLink signing、AprilTag、solvePnP、真实图像链路、跨相机几何联合优化 | 图像帧/检测器、协议报文、相机标定、D4/D5 stress 真值标签 | `subagent_reviews/D5_IMPLEMENTATION_GAP_AUDIT.md` |
| D6 评估指标 | 本地 EpisodeMetrics、JSONL、Blocks replay、POD/FAR/RMSE/IDSW/assignment/failover/terminal/communication、D4 active/passive degradation、D7 intercept/guidance time-series adapter、批量图表和分组报告 | Stone Soup metrics、TrackEval、SCRIMMAGE、OSPA/GOSPA/HOTA/IDF1、主动降级必要性标签 | 标准帧级匹配表、真实 D4 metadata、D7 多 seed guidance records/summaries | `subagent_reviews/D6_IMPLEMENTATION_GAP_AUDIT.md` |
| D7 比例导引 | 经典二维 PN、Pure Pursuit baseline、离线 radar->vision 记录、SimpleFlight 2v2 actor 拦截、AirSim detect、D3/D4/D5 terminal PNG gate、显式 handoff/hold/reacquire/revoke 状态、assigned collision 判据、D6 可消费 summary/time-series | FRPN、严格视觉 PN、PX4/MAVLink 主线、YOLO+ByteTrack 主线、main 5v5 plan-driven 控制 | 真实 D3/D4/D5 runtime bus、D5 状态迁移、相机/机动能力模型 | `subagent_reviews/D7_IMPLEMENTATION_GAP_AUDIT.md` |

## 4. 当前最重要的缺口

### P0：本轮已补齐的端到端接口缺口

1. **D3 到 D7 的版本化绑定已实现**
   D3 新增 `AssignmentGuidanceBinding` 与 `guidance_bindings_from_assignment_plan()`，D7 可消费 `plan_id/version/resource_id/assigned_global_track_id/authorization_state` 等字段。

2. **D4 主动降级输入 adapter 已实现**
   D4 新增 `D4ArbitrationAdapter`、`D4DecisionRecord` 与 `D4ArbitrationResult`，可把 D1/D2/D3/D5-like summary 转为主动降级仲裁输入，并输出 D6 `EventRecord` 兼容 metadata。

3. **D5 AirSim stress 已调用正式关联器**
   `d4d5_stress.py` 已从 frame/replay 构造 `GlobalTrack`、`CameraModel`、`LocalVisualTrack`、`Assignment` 和二级侦察 cue，并调用 `TerminalAssociator.decide()`。

4. **D7 末端 PNG 合同门控已实现**
   D7 新增 `terminal_gate.py`，在 AirSim controlled intercept 进入 `SimpleFlightPngGuidanceFilter` 前校验 D3 binding、D4 permission/action、D5 `locked`、ID/version 一致、授权状态和友方冲突。

5. **D6 已能消费 D7 拦截闭环结果**
   D6 新增 `intercept_replay.py`，可读取 `control_commands.csv` 与 `intercept_summary.json`，把成功类型、最小距离、拦截时间、碰撞/距离命中和 gate reject 纳入 `EpisodeMetrics`。

### P1：本轮已补齐的模块接口基线

1. **D1-D7 P1 模块接口已补齐**
   详见第 3 节各子模块：不确定性摘要、关联风险滑窗、分配有效性摘要、主动降级生命周期/防抖、末端一致性摘要、D6 分组指标和 D7 Pure Pursuit/显式 reject 状态均已落地。

2. **AirSim batch seed 运行模式已调整**
   `--batch-seeds` 现在通过一次 Blocks 启动和多次 reset 顺序运行，降低端口残留和重复启动风险；batch summary 写入 `single_blocks_reset_loop`。

### P1：仍需 main 统筹的运行时闭环

1. main 需要把真实 D1/D2/D3/D4/D5 流接入同一个 5v5 AirSim 控制状态机，替换当前 2v2 controlled intercept 中的 simulation-only binding/association。
2. D5 的 `locked/ambiguous/hold/reacquire` 状态迁移、丢锁、重捕获、friend conflict 和 duplicate lock 事件需要进入 D7 pair state machine 和 D6 指标。
3. D4 主动/被动降级细分指标已由 D6 提供基础聚合，但 main 仍需在真实 episode 中写入二级节点、分布式模式、触发原因和窗口前后效果。

### P1：开源对照与压力测试缺口

1. D2 已有 deterministic 5v5 crossing/dense fixture；后续需要真实 AirSim CV replay 压测。
2. D4 需要 CBBA vs auction vs centralized Hungarian gap 的同场景 benchmark。
3. D5 需要先把 ByteTrack 作为可选 adapter 接入 `LocalVisualTrack`，再评估 BoT-SORT/Deep SORT。
4. D7 已有 Pure Pursuit baseline；后续需要 PN/Pure Pursuit/visual PN 多 seed 对照实验。
5. D6 已有 D4 主动降级细分和 D7 guidance time-series/分组统计基线；后续再考虑 TrackEval/Stone Soup metrics。

## 5. 建议实施顺序

1. **保持 P0 合同回归**
   继续用 D3-D7 与 AirSim runtime 测试覆盖 `AssignmentGuidanceBinding`、`D4DecisionRecord`、`TerminalAssociation`、D7 terminal gate 和 D6 intercept adapter。

2. **把 P1 合同接入 main runtime bus**
   main 负责把 D3 plan/version、D4 action、D5 terminal decision、资源状态和 D7 控制 pair 合并到同一个 5v5 AirSim episode state machine，并写入 D6 已支持的分组/降级/guidance 字段。

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
