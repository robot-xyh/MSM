# 比例导引模块中文原理

本文说明本模块在科研仿真中的职责、数学模型、跨模块合同、状态机、能力边界和截至 2026-07-13 的验证结论。本文描述的是研究软件与仿真控制抽象，不是实机控制规范，也不构成任何自动授权、真实处置或绕过人工审核的设计。

## 1. 阅读约定与缩写首次定义

为避免同形缩写和能力层级混淆，本文先统一术语：

- 反无人航空系统（Counter-Unmanned Aircraft System，C-UAS）：本项目的科研仿真领域背景。
- 比例导航制导（Proportional Navigation Guidance，PNG）：本模块的导引算法名称，核心思想是按视线角速度生成横向修正。
- 便携式网络图形文件格式（Portable Network Graphics，PNG）：一种图像文件格式，只在截图或报告图片语境中使用。它与上一条导引算法同形但含义完全不同。本文凡写 `png_vm`、`png_ttc` 或“视觉 PNG”均指比例导航制导；凡写“PNG 图像”均指图像文件。
- 比例导航（Proportional Navigation，PN）：位置和相对速度已知时使用的经典比例导航形式。本文用 PN 指经典几何核，用 PNG 强调完整导引或视觉实现路径。
- 视线（Line of Sight，LOS）：追踪资源指向目标的方向；视线角速度是比例导引的关键反馈量。
- 预计碰撞时间（Time to Collision，TTC）：由目标检测框尺度扩张估计的剩余接近时间，不是身份或授权证据。
- 速度倍增（Velocity Multiplication，VM）：本仓库对固定 `N * V_m` 视觉导引增益路径的命名，其中 `V_m` 表示导引使用的速度量级。
- 卡尔曼滤波（Kalman Filter，KF）：本模块用于短时图像角度和角速度估计的线性状态估计器。
- 指数移动平均（Exponential Moving Average，EMA）：用于平滑 LOS 角速度和检测框面积的递推滤波方法。
- 北东地坐标系（North-East-Down，NED）：融合与运行时三维位置、速度和命令的公共坐标系，第三轴向下为正。
- 指挥与控制（Command and Control，C2）：中心、二级和分布式计划所有权与许可链的统称。
- 确认应答（Acknowledgement，ACK）：分布式联盟提交时成员对当前版本的明确确认。
- 标识符（Identifier，ID）：用于区分全局航迹、本地视觉航迹、计划和资源的稳定字段。
- 视场（Field of View，FOV）：相机可观测的角域；目标贴近图像边缘时，视觉质量门会保守拒绝切换。
- 第一研究模块：传感器融合（Module One: Sensor Fusion，D1）：生成带双时间戳和协方差的融合航迹信息。
- 第二研究模块：数据关联（Module Two: Data Association，D2）：维护中心拥有的全局航迹身份和身份连续性。
- 第三研究模块：分配规划（Module Three: Assignment Planner，D3）：生成版本化资源-目标分配和联盟拓扑。
- 第四研究模块：分布式降级（Module Four: Distributed Fallback，D4）：仲裁中心、二级和分布式降级许可。
- 第五研究模块：末端关联（Module Five: Terminal Association，D5）：把本地视觉航迹保守关联到既有全局航迹。
- 第六研究模块：评估指标（Module Six: Evaluation Metrics，D6）：被动统计合同、控制、模式和物理结果。
- 第七研究模块：比例导引（Module Seven: Proportional Guidance，D7）：本文所述模块，负责中段 PN、末端视觉 PNG 和合同门控。
- 微软航空信息与机器人仿真平台（Aerial Informatics and Robotics Simulation，AirSim）：main 用于 Blocks 场景、目标 actor、检测元数据和飞行控制实验的仿真平台。
- 轻量飞行控制后端（SimpleFlight）：AirSim 中当前受控拦截机使用的飞行控制后端。
- 开源自动驾驶仪（PX4 Autopilot，PX4）：交付包中存在参考路径、但未进入本模块默认主线的飞控系统。
- 微型飞行器通信协议（Micro Air Vehicle Link，MAVLink）：交付包中用于飞控通信的参考协议，未进入默认主线。
- 只看一次目标检测算法（You Only Look Once，YOLO）：交付包和离线回放可使用的视觉检测算法；当前默认在线检测不是该路径。
- 简单在线实时跟踪（Simple Online and Realtime Tracking，SORT）与技巧集合增强的简单在线实时跟踪（Bag of Tricks for SORT，BoT-SORT）：D5 准入实验中的可选局部跟踪后端，不属于 D7 默认检测输入。
- 多目标跟踪（Multiple Object Tracking，MOT）：ByteTrack、BoT-SORT 等视觉局部跟踪路径的类别；截至当前未获准替换默认在线检测。
- 软件在环（Software in the Loop，SITL）：PX4 等飞控软件与仿真环境联调的方式，当前不属于默认控制路径。
- 第一优先级收敛阶段（Priority 1，P1）：当前合同闭环、视觉质量和物理性能校准层。
- 第二优先级离线研究阶段（Priority 2，P2）：与默认运行路径隔离的高级导引律比较层。
- 三维（three-dimensional，3D）：包含北、东、地三个方向的空间模型；默认在线位置 PN 仍为二维水平模型。
- 真比例导航（True Proportional Navigation，True PN）：P2 离线对照中的惯性几何比例导航变体。
- 增广比例导航（Augmented Proportional Navigation，APN）：P2 离线对照中加入目标法向加速度前馈的变体。
- 模糊鲁棒比例导航（Fuzzy Robust Proportional Navigation，FRPN）：P2 中只有明确标记的研究近似，不是标准模糊规则实现。
- 应用程序编程接口（Application Programming Interface，API）：代码向 main 或离线工具暴露的调用边界。
- 逗号分隔值（Comma-Separated Values，CSV）和 JavaScript 对象表示法（JavaScript Object Notation，JSON）：运行日志与摘要的主要序列化格式。
- 检测框（Bounding Box，bbox）：目标在图像平面上的矩形范围；代码通常使用左上、右下坐标表示。
- 弧度（radian，rad）和像素（pixel，px）：本文角度与图像坐标所用单位。
- 二资源对二目标基线（Two Resources to Two Targets，2v2）与五资源对二目标基线（Five Resources to Two Targets，M5N2）：实验规模名称，不是算法固定上限。

## 2. 模块定位、问题与边界

### 2.1 模块定位

D7 位于“中心航迹与分配已经形成”之后、“main 实际向仿真飞行器下发速度命令”之前。它解决的是一个受版本、身份和安全许可约束的导引问题，而不是目标发现、身份创建、资源分配或任务授权问题。

当前职责可概括为四层：

1. 把 D1/D2 的目标状态和资源状态归一为二维 `GuidanceState`（导引状态）。
2. 对 D3 已分配的每个资源-目标 pair 独立计算中段 PN，必要时临时选择有界纯追踪完成重捕。
3. 在 D3/D4/D5 合同和视觉质量均通过后，计算末端 `png_vm` 或 `png_ttc` 候选速度命令。
4. 输出可审计的合同、质量、切换、外推、命令和模式字段，供 main 执行、供 D6 评估。

D7 的默认在线策略不是“全程视觉”，而是 `radar_pn -> vision_terminal` 的混合链路：视觉条件未满足时继续中段雷达 PN；只有选择了视觉导引律并通过全部门控时才切换。

### 2.2 工程问题

工程上需要同时处理以下矛盾：

- 中段全局航迹范围较大、身份稳定，但位置和速度存在延迟、噪声与协方差；末段视觉角分辨率较高，却容易出现检测框过小、贴边、遮挡、丢帧和局部 ID 抖动。
- 经典 PN 在闭合速度变为非正或越过最近点后缺少主动朝向目标的重捕行为，需要一个有迟滞、有限转率、可审计的临时恢复策略。
- 单帧 D5 锁定或单帧视觉质量通过不应直接导致导引模式抖动，需要驻留、释放和重捕迟滞。
- 短时丢检需要平滑过渡，但外推绝不能跨越身份、计划所有权、版本或安全许可变化。
- 多资源可共享同一个中心全局航迹，但任何滤波器、迟滞计数和外推命令都不能跨资源-目标 pair 共享。
- main 需要可消费的 NED 速度抽象，D6 需要分层日志；D7 本身又不能直接拥有 AirSim 生命周期或飞控连接。

### 2.3 科学问题

本模块围绕以下可检验问题开展研究：

- 在平面质点假设下，`a_n = N V_c dot(lambda)` 能否稳定降低距离，导航比、加速度上限和转率上限如何影响收敛与控制饱和？
- 与直接指向当前目标位置的纯追踪相比，PN 在机动目标、越目标和负闭合速度条件下的优势与失败模式是什么？
- 由像素检测框得到的 LOS 角速度在噪声、延迟、裁切和短时丢检下是否仍足以支撑末端导引？
- 检测框面积扩张估计 TTC 的可观测条件和拒绝条件是什么，`png_ttc` 与不依赖面积有效性的 `png_vm` 应如何对照？
- 合同门控、视觉门控、模式切换和物理结果如何保持统计独立，避免把“物理成功”反推成“视觉 PNG 成功”？
- 多资源同目标时，独立 pair 导引和真正的协同到达控制应如何区分？当前实现只回答前者，不回答共同剩余时间一致性或协同避碰问题。

### 2.4 明确边界

D7 不执行以下职责：

- 不生成 assignment，不选择目标，不决定资源数量，不激活 reserve，不创建联盟。
- 不创建、重写、重绑或猜测 `global_track_id`（中心拥有的全局航迹 ID）。
- 不把 `local_track_id`（单相机或单节点局部航迹 ID）提升为全局身份。
- 不直接启动、重置或关闭 AirSim，不直接调用 SimpleFlight，不管理目标 actor。
- 不提供 PX4 Offboard、MAVLink 机体角速度、姿态、推力、自动解锁或实机接口。
- 不提供真实火控、毁伤模型、自动授权、自动处置或绕过人工审核的逻辑。
- 不把 P2 离线算法、回放结论或报告建议自动晋级为默认控制律。

## 3. 跨模块数据流与合同

### 3.1 总体数据流

```text
D1 融合观测与协方差
  -> D2 中心全局航迹与身份连续性
  -> D3 版本化资源-目标分配与联盟 binding
  -> D4 当前计划所有权、降级和联盟提交许可
  -> D5 同一全局航迹的末端视觉关联
  -> D7 中段导引、末端合同/质量门和候选速度命令
  -> main AirSim runtime 实际执行与日志
  -> D6 分层评估
```

D7 的执行顺序是“先绑定、再许可、再关联、再质量、后导引”。任何后层通过都不能补偿前层失败。

### 3.2 D3 分配绑定

`AssignmentGuidanceBinding`（分配导引绑定）是 D7 的身份和版本根。主要字段如下：

| 代码字段 | 中文释义 | D7 规则 |
| --- | --- | --- |
| `plan_id` | 计划 ID | 必须与 D4 声明的新计划一致。 |
| `plan_version` | 计划版本 | 必须当前有效；回退会重置 pair 状态。 |
| `resource_id` | 资源 ID | 决定该 pair 的控制上下文。 |
| `vehicle_name` | AirSim 资源名称 | 由 main 用于仿真执行，D7 不解析平台能力。 |
| `assigned_global_track_id` | 已分配的全局航迹 ID | 是 D5 和视觉观测必须保持一致的唯一目标身份。 |
| `track_version` | 航迹/分配身份版本 | D5 的 `assignment_version`（关联所依据的版本）必须与之相等。 |
| `authorization_state` | 已记录的授权状态 | 只有有效状态才可继续；D7 不产生授权。 |
| `assignment_validity_state` | 分配有效状态 | 必须为 current/active/valid 语义。 |
| `owner_node_id` | 当前计划所有节点 ID | 真正二级接管时必须与 D4 一致。 |
| `expires_at_s` | 绑定到期时刻 | 超时后保守阻断。 |
| `coalition_id/version/epoch` | 联盟 ID、版本和时期 | 显式联盟和 fallback 提交必须一致。 |
| `member_role` | 成员角色 | `primary` 为主成员；`reserve/retry` 不能在 standby 时执行。 |
| `wave_id` | 波次编号 | primary 只能是 wave 0，reserve/retry 必须是非零波次。 |
| `coordination_mode` | 独立、同时、序贯或混合模式 | 只作为执行门控，不生成协同控制律。 |
| `arrival_window_start_s/end_s` | 视觉末端许可时间窗 | 窗口外继续雷达中段，不等于自动撤销 assignment。 |
| `activation_state` | 成员激活状态 | standby reserve 必须 fail closed。 |
| `terminal_authorization_scope` | 联盟级或逐主成员末端许可范围 | 与是否要求协同到达共同决定门控语义。 |
| `arrival_coordination_required` | 是否要求共同到达协调 | 只有显式 false 且 scope 为 per-primary 才可跳过共同到达门。 |

### 3.3 D4 降级许可

`D4GuidancePermission`（降级导引许可）只告诉 D7 当前 binding 是否可继续，不替代 D3 生成新计划。

允许进入后续检查的动作只有：

- `continue`（继续当前计划）；
- `continue_center`（继续中心计划）；
- `request_secondary_assist`（请求二级观测协助）。

其中 `request_secondary_assist` 的 `target_node_id`（观测 cue 提供节点）不是 assignment owner 转移，不要求 `takeover_ready`，也不修改当前 D3 binding。真正二级接管必须先由 D3 binding 显式标记 secondary owner 或 active takeover state，再要求 D4 owner 一致且 `secondary_readiness_class` 或 `secondary_capability_class`（二级就绪/能力等级）明确为 `takeover_ready`。

以下动作一律阻断视觉 PNG：

- `request_center_replan`（请求中心重规划）；
- `degrade_to_secondary`（正在降级到二级）；
- `degrade_to_distributed`（正在降级到分布式）；
- `reassign`（正在重分配）；
- hold、revoke、需要人工复核、联盟 fallback 不受支持或原子联盟未形成。

在中心失效且显式多资源联盟 fallback 时，还必须满足：commit 状态为 `committed` 或 `executing`、lease 未过期、epoch 与 plan/coalition 版本一致、当前资源属于 required 成员且已 ACK、全部 required 成员均已 ACK。`reconfiguring`、`aborted`、缺 ACK、旧版本或过期 lease 都保守拒绝。

### 3.4 D5 末端关联输入

D5 输入 D7 的 `TerminalAssociation`（末端关联）至少需要表达：

| 代码字段 | 中文释义 | D7 规则 |
| --- | --- | --- |
| `decision_state` | 关联决策状态 | fresh visual switch 只接受 `locked`；`reacquire` 只可能延续既有有界 coast。 |
| `assigned_global_track_id` | 被确认的中心全局航迹 ID | 必须等于 D3 binding。 |
| `local_track_id` | 本地视觉航迹 ID | 只用于该 pair 的滤波生命周期，不得升级为全局 ID。 |
| `assignment_version` | D5 使用的航迹/分配版本 | 必须等于 D3 `track_version`。 |
| `plan_version` | D5 使用的计划版本 | 联盟场景必须等于 D3 `plan_version`。 |
| `friend_conflict_state` | 友方冲突状态 | 非 none 时立即阻断。 |
| `duplicate_terminal_lock_risk` | 重复末端锁定风险 | 为真时立即阻断。 |
| `execution_gate_pass` / `safety_gate_pass` | D5 执行/安全门结果 | 显式 false 时立即阻断。 |
| `coalition_visual_complete` | 联盟视觉完成证据 | 默认 coalition scope 必需；per-primary 例外不免除本资源 lock。 |
| `measurement_timestamp` | 观测产生时间 | 用于几何和延迟计算。 |
| `arrival_timestamp` | 观测到达时间 | 与测量时间分离，不能替代测量时刻。 |

视觉检测框随后归一为 `VisionGuidanceObservation`（视觉导引观测），包含 `bbox_xyxy`（检测框左上和右下坐标）、置信度、相机 ID、帧时间、局部/全局航迹 ID 和视觉延迟等元数据。观测携带的全局 ID 若与 binding 不一致，同样拒绝。

### 3.5 D7 输出

D7 有两类输出：

1. `GuidanceCommand`（抽象导引命令）：记录距离、LOS 角、LOS 角速度、闭合速度、原始/限幅横向加速度、原始/限幅转率和期望航向，供离线质点或中段控制适配。
2. `PngGuidanceCommand`（视觉 PNG 命令）：记录 `velocity_ned`（NED 速度三元组）、航向、转率、视觉质量和饱和状态。只有 `visual_png_enabled=true`（视觉 PNG 最终允许）时，main 才应消费该速度。

`D7RuntimePairOutput`（单 pair 运行输出）同时给出：

- `terminal_contract_allowed`（上游合同是否允许）；
- `terminal_switch_allowed`（迟滞后是否允许视觉切换）；
- `camera_quality_gate_passed`（相机质量门）；
- `los_quality_gate_passed`（LOS 质量门）；
- `maneuver_margin_gate_passed`（机动裕度门）；
- `terminal_delivery_state/reason`（短时外推状态与原因）；
- `mode`（当前模式）和 `guidance_law`（当前生效导引律）；
- `selected_velocity_ned`（仅最终允许时可执行的速度）；
- owner、plan、track、coalition、D4/D5 consistency 和拒绝原因等审计字段。

## 4. 数学模型

### 4.1 经典位置比例导航

设追踪资源位置和速度为 `p_m`、`v_m`，目标估计位置和速度为 `p_t`、`v_t`。二维相对状态为：

```text
r = p_t - p_m = [r_x, r_y]
v = v_t - v_m = [v_x, v_y]
R = ||r||
lambda = atan2(r_y, r_x)
dot(lambda) = cross2(r, v) / R^2
V_c = -dot(r, v) / R
```

变量物理意义：

- `r`：资源到目标的相对位置向量，单位米。
- `v`：目标相对资源的速度向量，单位米每秒。
- `R`：平面距离。
- `lambda`：LOS 方位角。
- `dot(lambda)`：LOS 角速度；若为零，当前相对运动近似处于恒定方位关系。
- `V_c`：闭合速度；距离减小时为正，远离时为负。
- `N`：导航比，模块离线默认值为 3.0。

经典横向加速度命令为：

```text
a_n = N * V_c * dot(lambda)
```

代码使用 `cross2(r, v) = r_x v_y - r_y v_x`。当 `R` 近似为零时，LOS 量被置零以避免除零。输出还经过两级约束：

```text
a_clip = clip(a_n, -a_max, a_max)
omega_from_a = a_clip / ||v_m||
omega = clip(omega_from_a, -omega_max, omega_max)
psi_next = wrap_pi(psi + omega * dt)
a_effective = omega * ||v_m||
```

其中 `a_max` 是最大横向加速度，`omega_max` 是最大转率，`psi` 是当前航向，`dt` 是控制步长。`GuidanceConfig`（离线导引配置）的默认值是 `a_max=60 m/s^2`、`omega_max=0.8 rad/s`、`dt=0.05 s`；main 的 AirSim 配置可使用不同限值。

该模型只改变二维质点航向，不包含姿态环、推力、气动、旋翼动力学或执行机构延迟。默认在线中段也只使用水平分量；3D 字段仅为对照和日志，不替换该核心。

### 4.2 纯追踪对照

纯追踪直接把资源航向指向目标当前估计位置。定义当前航向 `psi` 和航向误差：

```text
e_psi = wrap_pi(lambda - psi)
omega_cmd = e_psi / dt
omega = clip(omega_cmd, -omega_max, omega_max)
psi_next = wrap_pi(psi + omega * dt)
a_n = omega * ||v_m||
```

它不使用 `N V_c dot(lambda)` 消除 LOS 角速度，而是追逐当前 LOS。因此：

- 优点是当目标已经从侧后方越过、`V_c <= 0` 或 PN 无法主动重新朝向目标时，能提供直观重捕方向。
- 代价是容易形成尾追、路径更长，且对快速横向目标通常不如 PN 具有预测性。
- 在代码中它既是 `guidance_law="pure_pursuit"` 的全程离线/运行对照，也是中段重捕时的临时有界导引律。

### 4.3 中段重捕选择

`MidcourseReacquisitionSelector`（中段重捕选择器）为每个 pair 保存独立历史。它先计算 PN，再根据闭合和越目标证据选择输出 PN 或纯追踪，不改变两种核心公式。

模块默认进入条件为：

```text
not_closing = (V_c <= 0 m/s)
overshoot = (
    R >= R_min_history + 2.0 m
    and R > R_previous + 0.05 m
)
entry_candidate = not_closing or overshoot
```

连续 2 帧出现进入候选后，选择 `pure_pursuit_reacquisition`（纯追踪重捕）；其转率上限为 `min(0.9 rad/s, caller_limit)`。重捕期间只有连续 3 帧满足 `V_c >= 1.0 m/s`，才回到 `radar_pn`。这组不同的进入/退出门限形成迟滞，避免单帧闭合速度噪声导致来回切换。

main 当前受控 AirSim 路径会在实例化选择器时把恢复门限调整为 `V_c >= 2.0 m/s`，恢复帧数调整为至少 10 帧且不少于约 1 秒控制样本；这是 runtime 配置，不是 PN 公式变化。

选择器必须在资源、目标、owner 或 binding 版本身份发生不兼容变化时重置。输出 metadata（元数据）包括选择结果、选择原因、进入/恢复连续帧数、历史最近距离和是否检测到越目标，便于 D6 定位中段发散。

### 4.4 视觉比例导航制导

#### 4.4.1 像素到 LOS

设检测框中心横坐标为 `u`，图像中心为 `c_x`，水平焦距为 `f_x`，资源当前航向为 `psi`：

```text
beta = atan((u - c_x) / f_x)
lambda = wrap_pi(psi + beta)
dot(lambda)_raw = wrap_pi(lambda_k - lambda_(k-1)) / dt
```

`beta` 是目标相对相机主轴的方位角。当前轻量主线使用水平像素几何；纵向检测框中心主要进入图像角度 KF 和短时预测，不构成默认三维制导命令。

LOS 角速度采用 EMA：

```text
dot(lambda)_f = alpha * dot(lambda)_raw
                + (1 - alpha) * dot(lambda)_(f,k-1)
```

默认 `alpha=0.45`。滤波后还可施加单步变化上限和绝对角速度上限；若检测到尖峰且 `reject_los_rate_outliers=true`，本帧 LOS 质量门拒绝。最近 5 个滤波样本的方差超过 `2.0 (rad/s)^2` 也拒绝。

#### 4.4.2 VM 路径

交付包的固定速度量级矢量形式为：

```text
a_cmd = N * V_m * (omega_LOS x lambda_I)
```

其中 `lambda_I` 是惯性系 LOS 单位向量，`omega_LOS` 是 LOS 角速度向量，`V_m` 是拦截速度量级。主模块的二维轻量 `png_vm` 先计算：

```text
V_m = max(V_c, V_min)
a_cmd = N * V_m * dot(lambda)_f
omega_cmd = a_cmd / V_m = N * dot(lambda)_f
```

当前默认 `V_min=0.2 m/s`。因此在二维转率实现中，VM 主要体现为固定 `N` 倍 LOS 角速度；最终水平速度大小由 `intercept_speed_mps`（main 注入的拦截速度）给出，航向由限幅转率更新。`png_vm` 会计算一个非强制 TTC 诊断值，但不因 TTC 无效而拒绝。

#### 4.4.3 检测框面积扩张与 TTC 路径

对尺寸近似不变、正向接近的目标，检测框面积 `A` 近似满足 `A = k/R^2`，其中 `k` 是由目标外形和相机内参决定的比例常数，因此：

```text
dot(A) / A ~= 2 / TTC
TTC ~= 2 * A / dot(A)
```

主模块仅在 `png_ttc` 中把 TTC 有效性作为质量门。处理顺序为：

1. 原始面积必须至少为 `16 px^2`。
2. 检测框不能触及图像上、下、左、右边界。
3. 相邻原始面积比不能超过 `2.5`，否则视为面积跳变。
4. 面积使用 `alpha_A=0.25` 的 EMA。
5. 对最近 5 个 `(timestamp, filtered_area)` 样本做最小二乘斜率估计。
6. `dot(A)` 必须为正，且 `TTC` 必须在 `(0, 20 s]` 内。

`png_ttc` 的转率命令为：

```text
omega_cmd = K(TTC) * dot(lambda)_f
```

默认增益在 `TTC <= 1 s` 时为 5.0，在 `TTC >= 6 s` 时为 0.5，中间使用平滑余弦插值。TTC 越短，角速度修正越强。与交付包可选的“TTC 无效时退到 soft VM guidance”不同，当前主模块 `png_ttc` 的 fresh switch 要求面积 TTC 有效；无效时记录明确拒绝原因并保持雷达中段。

#### 4.4.4 相机质量、LOS 质量和机动裕度

默认相机质量门要求：

- 检测置信度至少 0.55；
- 检测框面积占图像面积比例至少 0.0008；
- 检测框到最近图像边缘的归一化裕度至少 0.03；
- 同一局部/全局 track 至少稳定 2 帧；
- 视觉延迟不超过 0.35 秒。

LOS 质量门要求至少有两帧角速度历史、方差不过限、可选尖峰检查通过。`png_ttc` 还要求面积 TTC 有效；`png_vm` 不要求。

机动裕度定义为：

```text
omega_capacity = min(
    omega_max,
    a_max / max(current_speed, epsilon)
)
margin = 1 - |omega_cmd| / omega_capacity
```

默认要求 `margin >= 0.15`。若提供了相对位置且 `V_c <= 0.2 m/s`，则以 `not_closing`（未有效闭合）拒绝。最终转率限幅后生成：

```text
psi_next = wrap_pi(psi + omega_limited * dt)
velocity_ned = [V_cmd cos(psi_next), V_cmd sin(psi_next), z_cmd]
```

该 `velocity_ned` 是 SimpleFlight 兼容的仿真速度抽象，不是实机姿态或推力命令。

## 5. 交付包吸收范围与短时外推

### 5.1 已吸收的算法核

`png_guidance_delivery`（视觉导引交付包）保留 truth、gimbal 和 strapdown 三类复现实验。D7 主线没有整体搬入该控制栈，而是吸收了以下可在当前 SimpleFlight/AirSim detect 链路中独立验证的算法核：

| 已吸收能力 | 主模块实现 | 当前语义 |
| --- | --- | --- |
| 检测框中心到 bearing/LOS | `vision_png.py` | 使用相机内参把像素偏差转为水平视线角。 |
| LOS 角速度滤波 | `vision_png.py` | EMA、滑窗方差、可选单步/绝对限幅和尖峰拒绝。 |
| 检测框面积扩张 | `vision_png.py` | 面积 EMA、窗口斜率、跳变和裁切治理。 |
| TTC 增益 | `vision_png.py` | `png_ttc` 以 TTC 调度 LOS 角速度增益。 |
| VM 增益 | `vision_png.py` | `png_vm` 使用固定 `N * V_m` 思路，不依赖面积有效性。 |
| 图像角度 KF | `terminal_delivery.py` | 每 pair 估计水平/垂直图像角及其角速度。 |
| 有界短时外推 | `terminal_delivery.py` | 同身份、同计划上下文内的预测与衰减命令 coast。 |
| SimpleFlight 速度抽象 | `PngGuidanceCommand.velocity_ned` | 仅供 main 仿真执行。 |

### 5.2 图像 KF 模型

每个 pair 的图像 KF 状态为：

```text
x = [theta_x, theta_y, dot(theta_x), dot(theta_y)]
```

其中 `theta_x/theta_y` 是检测框中心相对图像中心的水平/垂直角，后两项是角速度。常角速度预测矩阵为：

```text
F = [[1, 0, dt, 0],
     [0, 1, 0, dt],
     [0, 0, 1,  0],
     [0, 0, 0,  1]]
```

默认测量角噪声为 0.006 弧度，角加速度过程噪声量级为 8.0 弧度每二次方秒，角度限幅 1.0 弧度，角速度限幅 8.0 弧度每秒。新量测与预测的创新范数超过 0.20 弧度时，默认拒绝创新并重置，而不是继续沿旧预测控制。soft innovation prediction（创新拒绝后的软预测）默认关闭。

### 5.3 有界短时外推

`TerminalGuidanceDelivery`（末端导引交付器）的状态为：

```text
acquiring
  -> measured
  -> image_kf_predict
  -> blind_push
  -> reacquired | expired
```

默认参数：控制周期 0.1 秒、KF 最大预测年龄 0.25 秒、连续丢失阈值 3 帧、命令平均窗口 0.10 秒、blind push 最大 0.25 秒、指数衰减时间常数 0.18 秒。

关键约束如下：

1. 所有预测或 blind push 都受“距离最后真实量测不超过 0.25 秒”的统一硬上限约束。
2. 在连续丢帧少于 3 帧时，若 KF 预测年龄有效，则把预测角重新投影成同尺寸检测框，再经过原 VM/TTC 质量门。
3. 达到丢失帧阈值但仍在 0.25 秒内时，才可能对最近已接受命令做短时平均和 `exp(-t/0.18)` 衰减；较高频控制下该分支才有时间空间。
4. 默认 10 赫兹（hertz，Hz）下，前两帧丢失可预测，第三帧时量测年龄通常已超过 0.25 秒，因而直接 `expired`（到期并 fail closed）。
5. blind push 必须已有通过质量门的历史命令；没有历史命令时不能生成。
6. 水平 LOS trend coast（基于近期 LOS 趋势的水平速度补偿）默认关闭；即使显式启用，其补偿上限也为 0.75 米每秒。
7. D4、身份、版本、owner、friend/duplicate 或 D5 safety gate 失败会立即清空 KF、命令窗口和 blind push，不能等待 0.25 秒后再停。

### 5.4 未吸收的实机与完整控制能力

以下能力虽然在交付包中可能有源码、说明或独立实验，但没有进入 D7 默认主线：

- PX4 Offboard 与 SITL 飞控链；
- MAVLink 机体角速度、姿态和推力控制；
- 自动 arm、自动 Offboard、实机解锁或安全接管流程；
- 云台闭环、完整捷联姿态补偿和真实相机外参/畸变标定；
- YOLO 在线推理及其推理优化链直接驱动默认受控拦截；
- ByteTrack、BoT-SORT 等 MOT 后端替换默认在线检测；
- 实机通信、时钟同步、无线链路认证、硬件故障管理；
- 真实平台空气动力学、旋翼动力学、推力裕度和执行机构模型。

当前 main 仍使用 AirSim `simGetDetections`（内置目标检测元数据接口）形成检测框，目标是移动 actor，不是 SimpleFlight 目标车辆。默认不保存便携式网络图形文件格式的 PNG 截图；`--save-images` 仅用于相机调试，导引主线不依赖已保存图像文件。

## 6. 雷达中段到视觉末段的状态机

### 6.1 总体状态

```text
radar_midcourse
  -> handover_pending
  -> terminal_dwell / reacquire_grace
  -> vision_terminal

任一检查失败：
  -> radar_midcourse | hold | reacquire | abort_revoke

既有 measured lock 的短时丢测：
  vision_terminal -> image_kf_predict/blind_push -> reacquired | expired
```

状态含义：

- `radar_midcourse`：使用位置 PN 或中段纯追踪重捕。
- `handover_pending`：已进入视觉交接窗口，但合同、视觉稳定或迟滞尚未全部通过；继续雷达 PN。
- `vision_terminal`：合同、视觉质量和 latch 均允许，视觉速度候选可被 main 消费。
- `hold`：授权、人工复核、友方冲突或联盟激活等安全条件不允许继续视觉切换。
- `reacquire`：D5 未锁定、身份/版本不一致或视觉外推到期，需要重新建立同一目标的末端证据。
- `abort_revoke`：assignment 撤销/过期、重分配、降级过渡、联盟提交失败或 terminal timeout 等不可继续条件。

离线二维仿真的 `terminal_switch_range_m` 默认 250 米，只用于质点研究。main 当前 AirSim controlled intercept 的默认末端距离是 8 米，可由命令行配置；测试夹具中出现的其他距离不是算法硬编码。

### 6.2 状态转换顺序

每个视觉候选样本按以下顺序处理：

1. 归一化 D3 binding，并确认 authorization、current、expiry、resource 和版本。
2. 检查 D4 action、owner、二级 readiness 和 fallback commit。
3. 检查 D5 `locked`、全局身份、版本、friend/duplicate 和 safety gate。
4. 检查联盟角色、activation、时间窗和视觉完成策略。
5. 仅合同通过后，更新本 pair 的检测框、LOS、TTC 和图像 KF。
6. 依次检查相机质量、LOS 质量、`png_ttc` 的 TTC 质量和机动裕度。
7. 应用 terminal dwell/release/reacquire latch。
8. 只有最终 `visual_png_enabled=true` 时输出 `selected_velocity_ned`；否则继续 `radar_pn` 或进入保守状态。

### 6.3 驻留、释放和重捕迟滞

`PngGuidanceConfig` 提供三个按 pair 的帧计数参数：

- `terminal_dwell_frames`（切入驻留帧数）：视觉候选连续允许达到该数后，terminal latch 才激活。
- `terminal_release_frames`（释放确认帧数）：激活后候选连续拒绝达到该数，latch 才释放。
- `terminal_reacquire_grace_frames`（重捕后再驻留帧数）：发生 D5 non-lock、身份/版本等重捕类合同拒绝后，即使候选重新通过，也先等待指定帧数再切入。

当前默认值分别是 1、1、0，因此默认不会额外增加驻留或重捕延迟；接口支持在实验中提高阈值。当前实现中 release grace 帧会标记 `terminal_release_grace`，但该帧仍不输出可执行视觉速度；它是模式释放迟滞的审计状态，不是无条件延续旧命令。真正的短时命令延续由上一节有界 coast 单独控制。

### 6.4 coast 的额外条件

coast 不能用于 fresh visual switch。只有同时满足以下条件才可尝试：

- 本 pair 已有真实 measured lock 和历史观测；
- 当前帧无 observation；
- D5 明确为 `reacquire`；
- D3 binding、D4 permission、全局身份、版本、friend/duplicate 和 safety 条件仍全部一致；
- terminal latch 之前已激活，且预测仍在 0.25 秒硬上限内。

任何新目标、旧版本、owner 变化或 safety block 都会清空状态，不存在“借旧框切新目标”的路径。

模块自有 `D7RuntimeBus` 路径要求 D5 显式给出 `reacquire`。main 的 `intercept.py` 还保留一个兼容适配：仅对已经 `terminal_locked`、当前无 observation 且拒绝原因属于视觉暂时缺失的 pair，把该帧交给同一个有界 delivery 处理。该适配不允许 fresh switch，不绕过 D3/D4、owner、版本或 friend/duplicate 检查，也受同一 0.25 秒硬上限约束；正式跨模块语义仍以显式 `reacquire` 为准。

## 7. 每 pair 独立状态与安全规则

### 7.1 状态隔离

`D7RuntimeBus`（D7 运行总线适配器）以：

```text
control_context_id = resource_id + "->" + assigned_global_track_id
```

标识控制上下文。每个上下文独立保存：

- `MidcourseReacquisitionSelector` 的最近距离和进入/恢复连续帧；
- `TerminalGuidanceDelivery` 的图像 KF、真实锁定、丢帧计数、命令窗口和 blind push；
- `SimpleFlightPngGuidanceFilter` 的局部 track 稳定帧、LOS EMA/方差窗口和 TTC 面积窗口；
- terminal latch 的 dwell/release/reacquire 计数；
- 上一次模式和导引律，用于 transition 日志。

多个资源可以被 D3 分配到同一个 `global_track_id`，但其状态仍按资源分别保存。一个 pair 的 D5 丢锁、面积跳变或 D4 拒绝不应污染其他 pair。

### 7.2 版本与生命周期

以下兼容滚动更新可以保留视觉历史：资源、全局目标、非空 owner、联盟角色、wave、coordination mode、activation、coalition ID、terminal scope 和 arrival policy 均不变；plan/track/coalition version 单调不回退；assignment 仍 authorized/current；请求导引律不变。

即使保留滤波历史，最新 D3/D4/D5 合同仍逐帧完整重验。状态保留只避免无意义地重启滤波器，不构成许可缓存。

以下变化会重置或清空 pair 历史：

- `resource_id`、`assigned_global_track_id` 或 `local_track_id` 改变；
- plan owner、member role、wave、activation 或 terminal scope 改变；
- plan、track 或 coalition version 回退；
- 请求导引律从一种切到另一种；
- assignment 被撤销、过期或显式 `reset_pair()`；
- D4/D5 身份与安全合同失败。

### 7.3 身份与联盟安全

身份规则：

- `global_track_id` 由中心拥有；D7 只比较，不写入新值。
- D5 `assigned_global_track_id`、D3 binding 和视觉 observation 三者必须一致。
- D5 `local_track_id` 只限定图像滤波生命周期，不能替代中心身份。
- friend conflict、duplicate lock risk 或 D5 execution/safety false 都立即 fail closed。
- 在线 D5/D7 不使用 AirSim actor truth ID 做身份绑定；truth 只允许在写盘后由 D6 离线评分。

联盟规则：

- 默认 `terminal_authorization_scope="coalition"` 要求当前资源自己的 D5 lock、联盟 ID/版本一致、联盟视觉完成和有效 arrival window。
- 只有显式 `terminal_authorization_scope="per_primary"` 且 `arrival_coordination_required=false` 的 active primary，才可跳过共同视觉完成和共同 arrival window。它仍必须通过自身 D5、D4 commit、身份、版本、friend/duplicate、相机、LOS、TTC/闭合和机动门。
- standby reserve 即使看到目标、已有 bbox 或有 D5 匹配，也以 `coalition_not_activated` 拒绝。只有新版本显式激活并重新通过全部合同后才可执行。
- 中心失效时，D7 只消费 D4/main 已形成的原子联盟提交，不自行补成员、不推断 ACK、不延长 lease。
- arrival window 是视觉接管许可窗。窗口未开或已关闭时继续雷达中段，等待当前计划后续时刻或新版本，不把窗口关闭误判为目标撤销。

### 7.4 独立多 pair 不等于协同导引

当前多个资源对同一目标分别运行 PN/PNG，只是多个独立控制器并行。真正协同导引还需要共享或协调 time-to-go、共同到达时刻、终端扇区、成员最小间距、通信拓扑和碰撞规避约束。当前 D7 没有 coalition-level clock、impact-time consensus、成员间预测避碰或协同控制消息，因此不得把 coalition binding gate 描述为 cooperative PNG 控制律。

## 8. 默认主线、离线对照与未实现能力

### 8.1 默认主线

截至 2026-07-13，默认 main AirSim 受控拦截路径为：

```text
二维位置 radar PN
  + 中段有界纯追踪重捕选择
  -> D3/D4/D5 合同
  -> AirSim detect 检测框质量门
  -> png_vm 视觉末段
  -> main 调用 SimpleFlight 高层速度接口
```

运行时默认 `intercept_guidance_law="png_vm"`。`pure_pursuit` 和 `radar_pn` 可作为全程策略选择；`png_vm` 和 `png_ttc` 都先用 `radar_pn` 中段。D7 模块只输出命令抽象和日志，main 的 `intercept.py` 才调用 `moveByVelocityZAsync`。

当前 `png_ttc` 已有主模块实现和真实 2v2 运行证据，但不是默认 AirSim controlled intercept 导引律。图像 KF 的常规丢帧预测已实现；soft innovation prediction、水平 trend coast 和六状态 LOS KF 在线控制均非默认，其中六状态 LOS KF 只用于离线 replay。

### 8.2 P2 隔离式离线对照

`optional_p2_benchmark.py`（P2 可选基准）只运行恒速追踪质点和带时间戳目标 replay，对照：

- `pn_3d`：三维几何 PN；
- `true_pn`：True PN；
- `apn`：加入目标法向加速度前馈的 APN；
- `frpn_research_approximation`：基于 LOS 角速度与目标加速度的确定性鲁棒增益调度近似。

每条结果可输出是否进入 5 米半径、最小脱靶距离、控制努力、控制能量、峰值加速度和 Python 计算耗时。所有结果都标记 `benchmark_only=true`（仅基准）、`default_runtime_path_replaced=false`（未替换默认路径）、`png_guidance_delivery_modified=false`（未修改交付包）和 `d3_d4_d5_gate_bypassed=false`（未绕过合同）。这些导引律没有注册到在线 `RuntimeGuidanceLaw`（运行导引律枚举），也不输出车辆控制命令。

FRPN 项尤其只是 research approximation，未复现标准模糊规则库，不能称为成熟 FRPN，更不能据此声称已实现协同鲁棒比例导引。

### 8.3 未实现或未晋级能力

以下能力必须继续标为未实现、部分参考或未晋级：

- 默认在线 3D PN、True PN、APN 或 FRPN；
- 共同 time-to-go、impact-time consensus、leader/neighbor 协同导引通信；
- 终端 sector/impact-angle 分配、成员间碰撞规避和协同到达控制；
- 多旋翼完整动力学、底层姿态/推力闭环和硬件在环验证；
- PX4/MAVLink/body-rate 实机默认控制链；
- YOLO、ByteTrack 或 BoT-SORT 直接替换默认在线 detect；
- 真实无线链路、时钟漂移、带宽限制和多机网络认证；
- 自动创建 assignment、自动授权、自动激活 reserve 或绕过人工审核。

## 9. 2026-07-13 结果与结论边界

### 9.1 2v2 PNG-TTC

截至 2026-07-13 的批量证据中，2 资源对 2 目标的 `png_ttc` 场景覆盖 10 个 seed、20 个资源-目标 pair：

- 5 米物理成功 `20/20`；
- 目标成功 `20/20`；
- 视觉控制允许样本 84；
- 模式切换计数 20；
- 在线 truth identity 使用 0；
- 面积不扩张和 TTC 越界拒绝在日志中实际出现，说明面积质量门不是空门。

该结果证明当前 `png_ttc` API、D3/D4/D5 gate、面积治理和 SimpleFlight 执行链在该 2v2、8 秒、10-seed 几何下能够闭合。它不证明：

- `png_ttc` 优于 `png_vm` 或雷达 PN；
- 20/20 都由视觉模式单独贡献；
- 同样参数可推广到 M5N2、不同高度、不同目标机动或真实平台；
- 检测框面积 TTC 等于真实测距或真实碰撞时间；
- 已完成实机飞控、真实视觉或通信安全验证。

### 9.2 M5N2 联盟物理闭环

五资源对二目标场景（M equals 5, N equals 2，M5N2）的最终收敛批次包含 40 个 SimpleFlight episode：baseline 和三个 D3 profile 各 10 seeds。高威胁目标使用 2 个 active primary 和 1 个 standby reserve；联盟完成定义为同一 episode 内两个 active primary 分别进入 NED 三维 5 米范围，不要求同时到达。

结果为：

| profile | coalition completion |
| --- | ---: |
| baseline | 0/10 |
| 20 米 handoff / 3 秒 arrival window / 40 度 sector separation | 5/10 |
| 20 米 / 5 秒 / 40 度 | 2/10 |
| 20 米 / 8 秒 / 40 度 | 1/10 |

最佳 profile 是 `5/10`，未达到 `8/10` 晋级门限；全部 profile 合计 `8/40`。主要失败断点是第二 primary 的 `d5_not_locked`（D5 未锁定）和 `terminal_detection_acquisition_timeout`（末端检测获取超时），少量为 `bbox_area_too_small`（检测框面积过小）。安全结果为 reserve unauthorized 0、`global_track_id` rewrite 0、online truth use 0。

D6 在统一报告中分别统计 contract 35、control 7、mode switch 9、pair physical 62。这四层样本口径和判定条件不同，只能分别审计，不能相互反推。尤其：

- 物理进入 5 米不能证明本帧视觉合同、控制或模式切换都通过；
- 合同通过不能证明视觉质量通过，更不能证明物理成功；
- 2v2 PNG-TTC 的 20/20 与 M5N2 的 5/10 使用不同规模、几何、时限和联盟判据，不能直接比较算法优劣；
- M5N2 当前只证明合同和执行链已接通、最佳性能仍未达标，不证明真正的协同到达控制已经实现。

因此当前结论是：默认位置 PN/视觉 PNG 主线保持，M5N2 下一步应聚焦第二 primary 的视觉获取、锁定稳定性、closing speed/range 口径和二维/三维机动裕度校准，而不是放宽身份、版本、reserve 或安全 gate。

## 10. 与 D1-D6 和 main AirSim runtime 的接口

### 10.1 D1：传感器融合

D1 负责把雷达、声学或视觉观测变成共同 NED 状态，并保留：

- `measurement_timestamp`（物理量测产生时间）；
- `arrival_timestamp`（消息到达处理端时间）；
- 位置/速度和 covariance（协方差）；
- 观测来源、质量和 lineage（来源谱系）。

D7 不直接融合原始观测。它通过 D2/global track 或 main 适配后的 `GuidanceState` 消费位置、速度、时间和 `covariance_trace`（协方差迹）审计字段。D7 不应丢弃双时间戳语义，也不应用到达时间替代量测时刻做图像几何。

### 10.2 D2：数据关联

D2 维护中心 `global_track_id`、航迹状态、协方差和 track version。D7 中段使用其水平位置/速度，D5 末端仍必须回到同一中心 ID。D2/D6 的 `id_switch_count`（全局身份切换显式计数）必须保留；D7 只记录和拒绝不一致，不修复或重写身份。

### 10.3 D3：分配规划

D3 输出 `AssignmentPlan`（分配计划）和逐 assignment binding。main 把其映射为 `AssignmentGuidanceBinding`。D7 只执行当前 authorized/current binding：

- stale、revoked、expired 或版本回退均阻断；
- resource-target 重分配必须建立新上下文；
- coalition role、wave、arrival window、activation 和 per-primary policy 都来自 D3；
- D7 的 topology helper 只展开 D3 已排序资源需求，不重新求解或优化 assignment。

### 10.4 D4：分布式降级

D4 提供 `D4GuidancePermission`，包括 action、mode、owner、new plan/version、secondary readiness 和 fallback commit。D7 将过渡中的 replan/degrade/reassign 解释为“旧 binding 不可用于视觉 PNG”，而不是自行寻找新 owner。只有 D3 新 binding 已生效且 D4 许可一致后，才重新进入 D5/视觉质量检查。

### 10.5 D5：末端关联

D5 负责将相机局部航迹关联到 D2 的中心全局航迹，并输出 lock、ambiguity、friend/duplicate、安全门、测量/到达时间和相机几何证据。D7 不读取 truth ID 做在线选择，只消费：

- 与 binding 一致的 `assigned_global_track_id`；
- `locked/hold/ambiguous/reacquire` 状态；
- plan/track/coalition version；
- bbox、置信度、局部 track、视觉延迟和相机元数据。

`locked` 是必要但非充分条件，后续仍要通过 D4、相机、LOS、TTC/闭合和机动门。

### 10.6 D6：评估指标

D6 消费 D7 和 main 的逐帧/逐 pair 记录，不回写控制。关键字段包括：

- `range_m`、`min_range_m`、`closing_speed_mps`；
- `terminal_contract_allowed`、`terminal_control_allowed`、`terminal_switch_allowed`；
- `guidance_law`、`mode`、`mode_transition`；
- 相机/LOS/机动门和拒绝原因；
- 外推状态、预测年龄、coast 到期和重捕计数；
- `time_to_intercept_s`、assigned collision object、5 米 physical result；
- reserve 越权、owner/version mismatch、global ID rewrite 和 online truth use。

D6 必须保留 raw contract 与 execution 的双口径，不能用 aggregate 计数覆盖逐帧事实。

### 10.7 main AirSim runtime

main 拥有仿真生命周期和实际执行：

1. 按 `--drone-count N` 和 D3 有效 assignment 创建任意数量 pair，不把 2v2/5v5 写死进算法。
2. 一次启动 AirSim Blocks，尽量以 reset 分隔 episode。
3. 移动 `MSM_TargetActor_*` actor，调用 `simGetDetections` 取得检测框和相机元数据。
4. 为每个 pair 保存独立 D7 binding、D4 permission、D5 association、中段 selector、terminal delivery 和 latch。
5. 只有 D7 输出可执行视觉速度时才消费 `velocity_ned`；其他时刻使用雷达 PN/纯追踪重捕或保守状态。
6. 通过 `moveByVelocityZAsync` 向 SimpleFlight 拦截机下发高层水平速度和高度命令。
7. 输出 `control_commands.csv`（逐帧控制日志）、`intercept_summary.json`（拦截摘要）、D6 metrics 和 Markdown 报告。

目标 actor 当前不是 SimpleFlight 车辆。成功判据必须绑定 assigned target：距离进入阈值，或 collision object name 与 assigned actor/object 匹配。撞地、撞障碍或撞到其他目标不能记为成功。

## 11. 中文术语表

| 中文术语 | 代码/英文对应 | 本文定义 |
| --- | --- | --- |
| 资源-目标 pair | assignment pair | 一个资源执行一个已分配全局目标的独立导引上下文。 |
| 全局航迹 ID | `global_track_id` | 中心拥有的稳定目标身份，D7 只读。 |
| 本地航迹 ID | `local_track_id` | 单相机/单节点视觉跟踪身份，只限定局部滤波生命周期。 |
| 分配导引绑定 | `AssignmentGuidanceBinding` | D3 计划到 D7 的版本化资源-目标合同。 |
| 导航比 | `navigation_constant`, `N` | 比例导引对 LOS 角速度的增益。 |
| 闭合速度 | `closing_speed_mps`, `V_c` | 相对距离减少的速度，接近时为正。 |
| 视线角 | `los_angle_rad`, `lambda` | 资源指向目标的方位角。 |
| 视线角速度 | `los_rate_radps`, `dot(lambda)` | LOS 方向随时间的变化率。 |
| 纯追踪 | `pure_pursuit` | 直接指向目标当前估计位置的基线导引。 |
| 中段重捕 | `pure_pursuit_reacquisition` | PN 越目标或不闭合时临时启用的有界纯追踪。 |
| 交接等待 | `handover_pending` | 已进入视觉窗口但尚未完成合同、质量或迟滞条件。 |
| 视觉末段 | `vision_terminal` | 最终门控通过、可使用视觉 PNG 候选速度的状态。 |
| 切入驻留 | `terminal_dwell_frames` | 候选连续通过多少帧后才激活视觉 latch。 |
| 释放确认 | `terminal_release_frames` | 候选连续失败多少帧后释放视觉 latch。 |
| 重捕宽限 | `terminal_reacquire_grace_frames` | 重捕类拒绝后重新切入前额外等待的通过帧数。 |
| 图像角度预测 | `image_kf_predict` | 在 0.25 秒内用图像角度/角速度 KF 生成预测检测框。 |
| 盲推 | `blind_push` | 对近期已接受命令做短时平均和指数衰减，不创建新锁定。 |
| 到期 | `expired` | 预测窗口、coast 或合同已不可继续，停止视觉命令。 |
| 相机质量门 | `camera_quality_gate_passed` | 检查置信度、面积、边缘、稳定帧和视觉延迟。 |
| LOS 质量门 | `los_quality_gate_passed` | 检查角速度历史、方差、限幅和尖峰。 |
| 机动裕度门 | `maneuver_margin_gate_passed` | 检查所需转率相对平台加速度/转率容量的余量。 |
| 联盟级许可 | `terminal_authorization_scope="coalition"` | 要求联盟视觉完成和共同 arrival window 的默认语义。 |
| 逐主成员许可 | `terminal_authorization_scope="per_primary"` | 只在明确不要求共同到达时，允许 active primary 独立切换。 |
| 主成员 | `primary` | 当前版本中可执行的主要资源成员。 |
| 备用成员 | `reserve` | 默认 standby，必须由新版本显式激活后才可执行。 |
| fail closed | conservative rejection | 缺字段、过期、冲突或不一致时拒绝执行，而不是猜测补值。 |
| 合同允许 | `terminal_contract_allowed` | D3/D4/D5、身份、版本和联盟规则通过。 |
| 控制允许 | `terminal_control_allowed` | 候选控制经过执行侧条件允许。 |
| 模式切换 | `mode_transition` | 当前导引模式相对上一样本发生变化。 |
| 物理成功 | `physical_intercept` | assigned pair 达到规定距离或匹配碰撞对象；不能反推前述各门均通过。 |

## 12. 实现与证据索引

- 经典位置 PN、纯追踪和 3D 对照字段：`d7_proportional_guidance/pn.py`
- 中段重捕选择：`d7_proportional_guidance/midcourse_reacquisition.py`
- 四导引律运行选择：`d7_proportional_guidance/selector.py`
- D3/D4/D5 末端合同：`d7_proportional_guidance/terminal_gate.py`
- 像素 LOS、VM/TTC 和视觉质量门：`d7_proportional_guidance/vision_png.py`
- 图像 KF 与有界短时外推：`d7_proportional_guidance/terminal_delivery.py`
- 每 pair 状态、迟滞和日志：`d7_proportional_guidance/runtime_bus.py`
- P2 隔离 benchmark：`d7_proportional_guidance/optional_p2_benchmark.py`
- 交付包边界：`png_guidance_delivery/README.md`
- 2v2 PNG-TTC 批量证据：`research_modules/airsim_runtime/outputs/p1_terminal_closure_10seed_20260712/`
- M5N2 最终收敛证据：`subagent_reviews/MAIN_P1_CONVERGENCE_VALIDATION_REPORT_20260713.md`
