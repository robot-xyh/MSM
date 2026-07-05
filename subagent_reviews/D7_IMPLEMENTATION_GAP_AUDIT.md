# D7 比例导引与末端视觉 PNG 实现差距审计

**审计范围**：`subagent_reviews/MAIN_IMPLEMENTATION_GAP_AUDIT.md`、`subagent_reviews/D7_PROPORTIONAL_GUIDANCE_REVIEW_AND_PLAN.md`、`C_UAS_MAINSTREAM_SOLUTIONS_AND_DIFFICULTIES.md`、`research_modules/d7_proportional_guidance/` 的代码、README、PLAN、tests，以及 D7 相关 AirSim runtime 合同说明。
**修改边界**：本次只更新本 GAP 文件，不修改 main GAP、不修改其他模块代码。
**系统边界**：D7 只做导引律、导引状态、末端 PNG gate 和日志合同；D7 不分配目标、不授权、不改写或本地重绑 `global_track_id`。

## 总体结论

D7 当前已经实现可测试的二维经典 PN 中段导引、Pure Pursuit 轻量 baseline、离线 `radar_midcourse -> vision_terminal` 质点仿真、AirSim phase-1 dry-run 记录适配、D3/D4/D5 terminal PNG 合同门控、显式 `handover_pending/hold/reacquire/abort_revoke` 日志状态，以及从 `png_guidance_delivery` 抽取的 SimpleFlight 兼容视觉 PNG gate。

仍未实现或未进入主线的是高机动增强导引和重型工程链路：FRPN/augmented PN/biased PN/true PN、MPC/NMPC、PX4/MAVLink 主线控制、YOLO+ByteTrack 主线检测、ViSP/ROS2 视觉伺服栈、完整相机标定/solvePnP 链路。`png_guidance_delivery` 已纳入仓库作为算法来源和复现实验包，但 main D7 主线只吸收 bbox-to-LOS、LOS-rate、TTC/VM gate 和 SimpleFlight 速度命令这一小核。

最关键的剩余缺口不是 D7 本地 API，而是 main 运行时接线：真实 D3 plan/version、D4 action、D5 `TerminalAssociation`、锁定丢失/重捕获和撤销事件还没有在同一个 N-pair AirSim 控制 state machine 中持续驱动 D7。当前 D7 侧已能按 pair 独立工作，并有 1/3/5/7 pair 单测防止固定 2v2/5v5 假设。

## 已实现

| 项 | 实现状态 | 关键证据 | 说明 |
|---|---|---|---|
| 经典二维 PN 中段导引 | 已实现 | `d7_proportional_guidance/pn.py`; `tests/test_proportional_guidance.py` | `compute_proportional_navigation_command()` 使用 `a_n = N * V_c * lambda_dot`，记录 range、LOS、LOS-rate、closing speed，并做加速度/转向率限幅。 |
| 雷达中段 PN | 已实现 | `simulator.py`; `airsim_dry_run.py`; `README.md` | 离线 `radar_midcourse` 使用 `GuidanceState` 的二维位置/速度和 `source="global_track"` 抽象，不写死 2v2/5v5。 |
| Pure Pursuit baseline | 已实现轻量版 | `pn.py`; `models.py`; `simulator.py`; `tests/test_proportional_guidance.py` | `compute_pure_pursuit_command()` 和 `GuidanceConfig.guidance_law="pure_pursuit"` 已可做 PN 对照；未引入 PythonRobotics 依赖是有意保持轻依赖。 |
| 离线 `radar_midcourse -> vision_terminal` 质点闭环 | 已实现基础版 | `simulator.py`; `PLAN.md`; `README.md` | `simulate_guidance_episode()` 可按距离/时间阈值进入合成 `vision_los` 末端模式并输出 `GuidanceRecord`/summary。 |
| AirSim phase-1 dry-run 适配 | 已实现 | `airsim_dry_run.py`; `tests/test_airsim_phase1_dry_run.py` | 接收 assignment/resource/target estimate 普通 DTO，输出一条 `radar_midcourse` 和一条 `vision_terminal` 记录；不导入 `airsim`，不控制车辆。 |
| D3/D4/D5 terminal gate | 已实现 D7 API | `terminal_gate.py`; `tests/test_proportional_guidance.py` | `evaluate_terminal_png_contract()` 校验 `AssignmentGuidanceBinding`、授权/current/expiry、D4 action、D5 `locked`、friend conflict、ID/version 一致和观测 global ID。 |
| D4 gate 行为 | 已实现 D7 拦截 | `terminal_gate.py`; `tests/test_proportional_guidance.py` | `request_center_replan`、`degrade_to_secondary`、`degrade_to_distributed` 等均拒绝视觉 PNG，映射为 `d4_reassign_pending`。 |
| D5 gate 行为 | 已实现 D7 拦截 | `terminal_gate.py`; `tests/test_proportional_guidance.py` | 只有 `decision_state=="locked"` 且无 friend conflict 才允许视觉 PNG；`ambiguous/hold/reacquire` 不会导致 D7 换绑目标。 |
| 显式 handoff/hold/reacquire/revoke 状态 | 已实现 P1 基线 | `models.py`; `terminal_gate.py`; `tests/test_proportional_guidance.py` | `GuidanceMode` 包含 `handover_pending`、`hold`、`reacquire`、`abort_revoke`，reject reason 可映射为日志状态。 |
| SimpleFlight 视觉 PNG gate | 已实现轻量主线核 | `vision_png.py`; `README.md`; `PLAN.md`; `tests/test_proportional_guidance.py` | `SimpleFlightPngGuidanceFilter` 支持 bbox 面积/置信度/边缘、稳定帧、视觉延迟、LOS-rate 方差、TTC、闭合速度和机动裕度 gate，并输出 SimpleFlight 速度命令。 |
| TTC 捷联比例导引核心 | 已实现轻量抽取 | `vision_png.py`; `png_guidance_delivery/README.md` | 主线支持 `law="png_ttc"` 和 `law="png_vm"` 的 TTC/VM 增益思想；delivery 包保留 truth/gimbal/strapdown 复现实验。 |
| N-pair 独立 D7 上下文要求 | 已实现 D7 侧基线 | `tests/test_proportional_guidance.py`; `README.md`; `PLAN.md` | 单测覆盖 1/3/5/7 pair 独立 filter、D3/D4/D5 gate、time-series 字段；D7 API 不读取固定 drone count。 |
| `png_guidance_delivery` 纳入仓库 | 已纳入，主线只抽取子集 | `png_guidance_delivery/README.md`; `png_guidance_delivery/MANIFEST.md`; `vision_png.py` | delivery 包包含 truth/gimbal/strapdown、LOS/TTC/KF、PX4/MAVLink、YOLO/ByteTrack、脚本和报告；主线只用仿真安全、轻依赖子集。 |

## 部分实现

| 项 | 当前做到什么 | 还缺什么 | 未完全实现原因 | 优先级 |
|---|---|---|---|---|
| 末端视觉 PNG / 像素 LOS-rate | `vision_png.py` 已从 bbox center 算 bearing/LOS-rate，支持 `los/png_ttc/png_vm`，并用质量 gate 控制是否进入视觉末端。 | 严格相机模型闭环、稳定距离/闭合速度估计、D5 local track 连续性、真实像素噪声/丢检重捕获。 | 当前主线使用 AirSim detect metadata 和 SimpleFlight 速度命令，优先验证合同与日志，不引入真实检测器/标定依赖。 | P1 |
| AirSim SimpleFlight 控制 | D7 设计和 gate 可被 `airsim_runtime/intercept.py` 消费，主线使用 SimpleFlight `moveByVelocityZAsync` 和 `simGetDetections`。 | 真实 D3/D4/D5 runtime bus 到 N-pair 控制 state machine 的持续接线。 | AirSim 受控拦截仍是 baseline；main 需要统一 episode 状态、资源状态、plan/version、D5 lock 和 D6 日志。 | P1 |
| D3/D4/D5 gate 在全流程中的作用 | D7 API 能拒绝不一致/撤销/未锁定/友方冲突，测试覆盖 active-secondary 合同。 | integrated runner 仍有按距离/时间切换的离线路径；真实 episode 还需持续喂入 D5 状态迁移和 D4 revoke/reassign。 | D7 只能校验输入，不能生成上游 plan、授权或 D5 lock。 | P1 |
| D6 guidance 指标输入 | D7 记录含 mode、range、LOS、closing speed、gate reject reason；AirSim controlled episode 可写 D7 相关 CSV/summary。 | 多 seed N-pair guidance time-series、稳定阈值版本、D4/D5 plan metadata 的真实 episode 覆盖。 | 指标消费需要 main/D6 在真实运行中持续采集，而不是 D7 本地单测即可完成。 | P1 |
| 机动能力 gate | PN 有加速度/转向率限幅；视觉 gate 估计 required turn rate、turn capacity、maneuver margin。 | 真实平台动力学、姿态/推力/延迟模型、PX4 响应和饱和日志。 | 当前控制层是 SimpleFlight 高层速度命令，无法代表底层飞控闭环。 | P1/P2 |
| `png_guidance_delivery` truth/gimbal/strapdown 经验 | delivery 包内存在复现实验脚本、报告和 TTC/VM 算法。 | 分层 API、离线回放测试、依赖隔离后逐项迁移到 D7 主线。 | delivery 里包含 PX4、YOLO、body-rate、图像显示等重依赖和实验流程，不宜直接混入 main 默认路径。 | P1/P2 |

## 未实现

| 项 | 当前状态 | 为什么未实现 | 缺少条件 | 建议优先级 |
|---|---|---|---|---|
| FRPN / 改进 PN | 未实现。代码没有 FRPN、augmented PN、biased PN、true PN 或目标加速度补偿。 | 当前优先稳定经典 PN、Pure Pursuit 对照、D3/D4/D5 gate 和 AirSim SimpleFlight 闭环；高机动算法公式和场景尚未冻结。 | 目标加速度/机动模型、FRPN 公式选型、机动目标批量场景、PN/FRPN/Pure Pursuit D6 对照指标。 | P2 |
| MPC / NMPC | 未实现。D7 没有 MPC 求解器或约束优化控制器。 | 共识文档将 MPC 作为强约束/高算力进阶项；当前二维 PN/视觉 PNG 足够支撑第一阶段科研闭环。 | 平台动力学、推力/倾角/避障/延迟约束、求解器依赖、实时预算、对照场景。 | P3 |
| PX4 SITL 主线控制 | 未接入 main D7 主线；delivery 包有配置和脚本。 | PX4 Offboard、解锁、推力标定和坐标系风险高，不应默认进入 main 控制链。 | PX4-Autopilot/SITL 版本、Offboard 状态机、推力/坐标/限幅标定、批量复现脚本、安全边界。 | P2 |
| MAVLink body-rate / attitude 控制 | 未接入 main D7 主线；delivery 包有实验代码和文档。 | 属于 PX4 Offboard 实验路径，依赖 pymavlink/heartbeat/prime/offboard 状态，风险和调试成本高。 | pymavlink、PX4 heartbeat、Offboard prime、RC/kill switch/围栏、安全流程、推力模型和回归基线。 | P2 |
| YOLO + ByteTrack 主线检测 | 未接入 main D7 主线；delivery 包有 detector。 | 当前 AirSim runtime 默认不保存 PNG，D7 主线消费 bbox metadata；不引入 Ultralytics、lap/lapx、CUDA 或权重管理。 | 图像帧流、YOLO 权重、class id、依赖版本、GPU/CPU 预算、MOT ID 稳定性指标、失败回退策略。 | P1：先离线回放，后主线控制 |
| OpenCV/KCF/标定链路 | D7 主线未依赖；delivery detector 懒加载部分 OpenCV。 | 当前 D7 只需要 bbox 到 LOS 的轻量几何，不做图像处理、KCF tracker、相机标定或 solvePnP。 | `opencv-contrib-python`、图像帧、KCF 可用性、相机内外参、重投影误差、实时性能预算。 | P2 |
| ViSP / ROS2 tf2 / message_filters | 未实现。repo 中没有 D7 ViSP 或 ROS2 节点接口。 | 当前项目是 Python 离线/AirSim 研究模块，不运行 ROS2 graph、tf tree 或同步消息管线。 | ROS2 runtime、frame tree、相机/机体/世界坐标变换、带戳消息 schema、bag/replay 基准。 | P3 |
| 严格 3D PN | 未实现。当前 D7 主线是二维水平 NED 抽象。 | 第一阶段 AirSim baseline 高度由 SimpleFlight 速度/高度命令保持，导引律先验证水平几何和接口合同。 | 3D state contract、重力/高度通道、飞控约束、D6 三维指标和测试场景。 | P2/P3 |

## 未实现原因汇总

1. **轻量可复现优先**：默认 D7 测试不依赖 AirSim 服务、PX4、ROS2、GPU、YOLO 权重或图像保存；核心算法保持 NumPy/math 级依赖。
2. **D7 不能替代上游授权与身份链**：D7 只能校验 D3/D4/D5 输入，不能生成 `AssignmentPlan`、授权状态、D5 `locked` 或 friend conflict 判断。
3. **主线控制仍处于 SimpleFlight 阶段**：当前工程目标是先让 PN/PNG gate、日志和 D6 指标在 AirSim Blocks 中稳定，再考虑 PX4/MAVLink/body-rate。
4. **真实视觉条件不足**：YOLO/ByteTrack、OpenCV 标定、KCF、ViSP 需要连续图像帧、相机参数、权重、实时性能预算和离线 replay 基准。
5. **高机动对照缺少基准**：FRPN/MPC 需要目标机动场景、平台动力学和 D6 多 seed 对照指标，否则会把算法复杂度提前引入主线。

## 缺少条件

1. **main N-pair runtime bus**：按 `--drone-count N` 枚举有效 D3 assignment pair，为每个 pair 提供 `AssignmentGuidanceBinding`、D4 permission/action、D5 `TerminalAssociation`、资源状态、目标估计和独立 D7 filter。
2. **D5 状态事件流**：`locked/ambiguous/hold/reacquire`、锁定丢失、重捕获、friend conflict、duplicate lock 和 terminal detection timeout 需要进入 D7 pair state machine 与 D6 指标。
3. **真实视觉 replay 条件**：图像帧或稳定 bbox replay、camera intrinsics/extrinsics、bbox timestamp、local track 连续性、LOS-rate 滤波、距离/闭合速度估计和丢检策略。
4. **飞控/动力学条件**：若升级 PX4/MAVLink，需要 PX4 SITL、Offboard 状态机、推力/坐标/限幅标定、饱和日志、安全边界和回归 baseline。
5. **对照实验条件**：PN/Pure Pursuit/FRPN/MPC/visual PNG 需要同一批多 seed 场景、统一 D6 指标、成功/失败判据和阈值版本。

## 下一步优先级

| 优先级 | 下一步 | 验收口径 |
|---|---|---|
| P0 保持 | 保持 D7 单元测试和 terminal gate 回归，不允许 D7 本地重绑目标或绕过 D3/D4/D5。 | `python3 -m pytest -q research_modules/d7_proportional_guidance/tests` 通过；reject reason 覆盖 D4 reassign、D5 non-locked、ID/version mismatch、friend conflict。 |
| P1 | main 将真实 D3/D4/D5 bus 接入 D7 N-pair 控制上下文。 | 每个 assignment pair 独立 D7 filter；CSV/summary 持续写出 `plan_id/plan_version/track_version/d4_action/d5_decision_state/terminal_contract_reject_reason`。 |
| P1 | 做 PN vs Pure Pursuit vs visual PNG 多 seed 对照。 | D6 能输出 min range、time to intercept、mode switch、terminal gate reject、terminal contract reject 和分组报告。 |
| P1 | YOLO+ByteTrack 先做离线 replay adapter，不直接进入控制主线。 | 图像/检测 replay 可生成 D5 local track 与 D7 bbox/LOS gate 质量摘要，失败可回退 AirSim detect metadata。 |
| P2 | 在 SimpleFlight 稳定后评估 FRPN/augmented PN。 | 有高机动 fixture、目标加速度估计、D6 对照指标和不破坏现有 PN API 的实现。 |
| P2 | PX4/MAVLink/body-rate 作为独立实验路径保留。 | 独立脚本和报告验证 PX4 SITL、Offboard prime、推力/坐标标定和安全流程，不默认并入 main runtime。 |
| P3 | 评估 MPC/NMPC、ViSP、ROS2 tf2/message_filters。 | 仅在需要强约束控制或机器人中间件集成时进入，不作为当前 D7 主线阻塞项。 |

## 关键依据路径

- `research_modules/d7_proportional_guidance/d7_proportional_guidance/pn.py`
- `research_modules/d7_proportional_guidance/d7_proportional_guidance/simulator.py`
- `research_modules/d7_proportional_guidance/d7_proportional_guidance/terminal_gate.py`
- `research_modules/d7_proportional_guidance/d7_proportional_guidance/vision_png.py`
- `research_modules/d7_proportional_guidance/d7_proportional_guidance/airsim_dry_run.py`
- `research_modules/d7_proportional_guidance/tests/test_proportional_guidance.py`
- `research_modules/d7_proportional_guidance/tests/test_airsim_phase1_dry_run.py`
- `research_modules/d7_proportional_guidance/README.md`
- `research_modules/d7_proportional_guidance/PLAN.md`
- `research_modules/d7_proportional_guidance/png_guidance_delivery/README.md`
