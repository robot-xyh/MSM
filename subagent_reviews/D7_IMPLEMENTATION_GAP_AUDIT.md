# D7 比例导引与末端视觉 PNG 实现差距审计

**审计范围**：`research_modules/d7_proportional_guidance/` 的 README、PLAN、代码和测试，`png_guidance_delivery/` 方案资料，以及 D7 在 `research_modules/airsim_runtime/intercept.py` 中被消费的实际状态。
**修改边界**：本次只更新 D7-owned 代码、测试、文档和 `subagent_reviews/D7_*`，不修改 D1-D6、main runtime、root report 或其他模块。
**系统边界**：D7 只做导引律、导引状态、末端 PNG gate 和日志合同；D7 不分配目标、不授权、不创建、不改写、不本地重绑 `global_track_id`。

## 总体结论

### 2026-07-12 delivery 增强与验证同步

当前没有新增 P0 blocker。图像 KF 生命周期重置、`png_ttc` 面积治理和统一 `0.25s` 外推硬上限已经实现，D7 回归为 `141 passed`。soft innovation prediction 与水平 LOS trend coast 仍默认关闭，6D LOS KF 保持 replay-only；这些 optional 能力没有晋级默认路径，也不改变位置 PN、`png_vm/png_ttc` 核心公式。

真实 AirSim 2v2 candidate 在 10 seeds、20 pairs 中达到 `20/20` 的 5m 物理成功，在线 truth 使用为 0；旧基线为 `19/20`。该结果只证明主链非退化，自然运行中的 soft prediction 和 trend coast 均未触发，不能把 20/20 归因于增强算法。锁定后注入两帧检测丢失时，两帧均进入 `predicted/image_kf_detection_loss_predict`，2/2 物理成功，证明同 identity/plan 上下文内的短时有界预测链路有效。

M5N2 的当前结果是 3 seeds、8s 短窗口：active pair 0/9，最近距离 22-32m，soft prediction 4 次、innovation reject 2 次、reserve 越权 0。它与既有 z=-30m、35s 高净空基线不等价，禁止直接比较。本轮 D7-owned 本地 1-5 帧 dropout helper/测试、TTC 多 seed 拒绝汇总和 trend 晋级判据已经闭合；当前 P1 剩余是同几何 paired M5N2 和真实 AirSim dropout/`png_ttc`/trend 受控执行，不是继续补 DTO/topology。

P2/P3 状态保持原规划：3D PN、True PN、APN、FRPN 只在隔离 benchmark，PX4/MPC/ROS2 等不提前晋级默认 runtime。

### 历史实施记录

2026-07-11 D7 fallback commit gate 实现：`D4GuidancePermission`、coercion、`TerminalPngContractDecision` 和 runtime output 已增加 commit state、epoch、lease、required/acked member、plan/coalition version 与 gate 结果字段。中心失效/fallback 的显式 k>1 联盟仅在 `committed|executing`、lease 有效、epoch/version 一致、当前资源 required+acked 且 required 集合全部 ACK 后继续；其后仍执行 D5 coalition visual completion。standby reserve、D4 pending、reconfiguring/aborted、缺 ACK、旧 epoch、过期 lease 和版本冲突均明确阻断。中心正常及 k=1 原行为保持回归，完整 D7 测试为 `97 passed`。D7 未修改 `png_guidance_delivery` 核心公式，也未改 main/D4。

2026-07-11 D7 P2 optional benchmark 实现：新增独立 `optional_p2_benchmark.py` 和 CLI，支持固定 seed 3D PN、True PN、APN、`frpn_research_approximation` 的恒速三维质点与序列化 replay 对照，逐条输出命中、最小脱靶量、控制努力/能量、峰值加速度和 Python 计算耗时。FRPN 明确标记为研究性鲁棒增益调度近似，不宣称标准模糊 FRPN。P2 law 未加入 runtime selector，结果标记不替换默认控制、不修改 delivery、不绕过 D3/D4/D5。完整 D7 回归更新为 `105 passed`。

2026-07-11 D7 N/M topology contract 实现：新增 `build_cooperative_guidance_topology()`、`validate_cooperative_guidance_topology()` 和结构化 topology/report DTO。M=5/N=2、T001 required=3、primary=2 时输出两个 active primary、一个 standby reserve；T002 required=1 输出 independent primary，剩余资源显式保留。专项测试还覆盖 7/3 非固定规模、资源不足和现有 terminal gate：两个 primary 可获得合同许可，未激活 reserve 即使有完整 D5 视觉证据仍拒绝为 `coalition_not_activated`。完整 D7 回归为 `109 passed`。D7 只展开 D3 已排序需求，不替代分配器或 main AirSim pair 创建。

2026-07-11 D7 terminal delivery API 实现：新增 `TerminalGuidanceDelivery`/`TerminalDeliveryConfig`/`TerminalDeliveryResult`，按 assignment pair 暴露 `acquiring/measured/image_kf_predict/blind_push/reacquired/expired`。默认参数与 delivery 已验证机制一致：`0.1s` control、`0.25s` 图像角度/角速度 KF predict、连续丢失 3 帧、`0.10s` 命令平均、`0.25s` blind push、`tau=0.18s`。`D7RuntimeBus` 已消费该 API 并输出状态、原因、预测年龄、丢帧、blind decay 与命令样本字段；stale D3 version、D4 block、D5 binding/friend conflict/execution safety gate 均先于外推 fail closed 并清空 pair 状态。完整 D7 回归为 `117 passed`；未修改位置 PN、TTC PNG、VM PNG 核心公式，P2 law 仍仅离线 optional benchmark。

D7 当前已经实现可测试的二维位置 PN/PNG 几何核、中段雷达/全局航迹 PN、离线 `radar_midcourse -> vision_terminal` 质点仿真、AirSim phase-1 dry-run 记录适配、末端视觉 `png_vm/png_ttc` 轻量 gate、每个 assignment pair 独立视觉导引状态、D3/D4/D5 terminal contract、显式 `handover_pending/hold/reacquire/abort_revoke` 日志状态，以及 SimpleFlight 速度命令抽象。

真实 AirSim SimpleFlight 控制不在 D7 模块内直接执行，而是 main/runtime 的 `intercept.py` 消费 D7 API：每个 `InterceptPair` 持有自己的 `AssignmentGuidanceBinding`、`D4GuidancePermission`、D5-shaped terminal association 和 `SimpleFlightPngGuidanceFilter`，将 `PngGuidanceCommand.velocity_ned` 交给 `command_velocity_z()`/`moveByVelocityZAsync`。因此 D7 文档必须把“D7 实现了可消费的导引/gate/命令抽象”和“main runtime 实际下发 SimpleFlight 命令”分开描述。

`png_guidance_delivery` 已纳入 D7 目录作为方案和复现实验包。主线实际使用 bbox-to-bearing、LOS-rate 窗口、bbox 面积 TTC、`png_vm/png_ttc` 增益思想、质量 gate、图像角度 KF、短时 command coast 和 SimpleFlight 速度命令。truth/gimbal/strapdown、PX4/MAVLink/body-rate、YOLO/ByteTrack 和报告仍是参考或独立实验路径；KF/外推只有 D7 轻量等价封装进入 runtime，不代表完整 delivery 控制栈接入。

2026-07-07 复核：main/runtime 已把真实 D7 控制执行产物合并进正式 `main_episode_bus_metrics.json`，并把执行前合同诊断保留为 raw `main_episode_bus_contract_metrics.json`。D3 `request_center_replan` 后的新中心 plan/binding/version 已接到 D7 current binding gate；D4 软风险和无冲突 D5 `reacquire/ambiguous` 不再被当作必然重规划/降级阻断。D7 本轮不需要修改 PN/PNG 控制律本体，只需保持 gate 和日志合同回归。

2026-07-08 D7 子智能体复核：D7-owned `runtime_bus.py`、`comparison.py`、`replay.py` 已补齐并由 D7 tests 覆盖。D7RuntimeBus 支持任意 N-pair state injection、每 pair 独立 filter、同一 pair plan/version/owner signature 变化时 reset；comparison 输出 PN/Pure Pursuit/`png_vm`/`png_ttc` 多 seed report rows；replay 将 YOLO/ByteTrack/AirSim bbox rows 离线映射到 D7 bbox/LOS/TTC gate，且显式不调用 SimpleFlight。D4 owner/version gate 已加强：D4 指定接管 owner 时，当前 D3 binding 必须携带同一 owner，旧 lock 或 owner mismatch/missing 均不得进入视觉 PNG；二级 plan 还必须有 D4 readiness/capability `takeover_ready`。main runtime 已把 D7 runtime summary 接入 episode bus；controlled 5v5 center replan 与 2v2 secondary visual PNG gate 回归已通过。

2026-07-08 P1 校准执行补齐：D7RuntimePairOutput 和 `summarize_runtime_bus_outputs()` 已补齐 main/D6 可消费字段。单样本记录包含 `terminal_handoff_state`、handover/terminal flags、D4/D5 state aliases、D3 plan/version、bbox、camera/LOS/maneuver gate、TTC、LOS-rate、closing speed 和 maneuver margin；summary 聚合 guidance mode、handoff 状态、D4/D5/plan 计数、contract/switch reject reasons、gate pass rate、bbox/TTC/LOS 数值摘要和 `visual_png_switch_count`。新增回归确保 D4 `request_center_replan`、`degrade_to_secondary`、`degrade_to_distributed` 时即使 bbox/D5 lock 良好也不调用视觉 PNG。

2026-07-08 P1 summary/replay 支持补齐：D7 新增 `calibration.py` 和 `summarize_guidance_calibration()`，可消费多 seed D7 runtime outputs、`GuidanceRecord`、comparison rows 或 replay dict，按 PN、Pure Pursuit、`png_vm`、`png_ttc` 汇总 terminal range、closing speed、bbox/LOS/maneuver gate 和 reject reasons。输出包含 `threshold_advisory.version="d7-p1-guidance-calibration-advisory-v1"`，覆盖 terminal range、min bbox area、max visual latency、min closing speed、min maneuver margin；所有字段均为 advisory，显式 `default_control_law_changed=False`、`d3_d4_d5_gate_bypassed=False`。3D/高度差/FRPN 仅作为 `benchmark_calibration` 字段，不替换默认 PN/PNG API。

2026-07-08 P1 main/D6 calibration sweep 对接：main runtime 已新增 P1 D4/D5 calibration sweep，支持 secondary height/FOV/count/standoff 与多 seed 组合；sweep 完成后 D6 自动生成标准报告 bundle，包括 records CSV、summary CSV、summary JSON 和 Markdown。该能力属于 main/D6 编排与报告写盘，不再作为 D7 未完成接口项。D7 仍需保持 runtime summary、comparison rows、bbox/LOS replay summary 和 `summarize_guidance_calibration()` 字段稳定，供真实 AirSim 多 seed PN/Pure Pursuit/PNG 对照、visual gate/range/closing speed 标定和 D4/D5/D3 gate 回归消费。

2026-07-08 D7 actor asset 复核：D7 `png_guidance_delivery` truth/gimbal/strapdown example 的 `--intruder-actor-asset` 默认值已从历史 cube `1M_Cube_Chamfer` 对齐为 Blocks/AirSim 无人机 mesh asset `Quadrotor1`，并新增测试锁定默认值。main runtime 的 actor asset CLI/default 已由 main 同步为 `Quadrotor1`；cube 仅作为旧接口、旧报告或几何 baseline 显式复现选项。后续重点是真实 AirSim 验证和阈值/检测调参。

2026-07-08 D4/D5 机动高空侦察 stress 复核：main 侧 5v5 D4/D5 stress 覆盖 3 seeds、200m 高差、`mobile_recon_gimbal`、80deg FOV、1920x1080；D4 action 正确，D5 能识别 mobile recon，gimbal OK rate 为 1.0。但二级网络同帧全覆盖仍为 0.0，降级 case cross-view 为 0，`not_registered` 约 65。D7 结论不变：移动侦察节点“看得更清楚”不等于可放行视觉 PNG；D7 仍必须坚持 D3 当前 version/owner、D4 action 允许、二级 readiness/capability 为 `takeover_ready`、D5 `locked` 且 `assigned_global_track_id` 一致、bbox/LOS/闭合速度/距离/机动能力 gate 全部通过。D4 `request_center_replan`、`degrade_to_secondary`、`degrade_to_distributed` 阶段若 plan owner/version 未进入可执行状态，或 D5 未 `locked`、`assigned_global_track_id` 与 binding 不一致，继续阻断视觉 PNG。当前无运行级 P0 blocker。

2026-07-08 EVAL P0/P1 同步：`EVAL/FRAMEWORK_EVAL_P0_P1_P2_GAP_CONFIRMATION.md` 确认 D7 没有新的运行级 P0 blocker，但新增工程化 P0 backlog。D7 P0-B 为末端视觉 PNG 切换迟滞和 LOS 角速率滤波；P0-C 为 3D PN geometry benchmark/log，只有下一阶段继续测试 200m 高差、3D target 或高度差拦截时保持 P0-C，否则按 P1 calibration/benchmark 处理。3D True PN/APN/ADRC 对照、预测拦截点、动力学补偿和 PN/Pure Pursuit/PNG 多 seed 对照保持 P1 能力增强边界；默认 PN/PNG 不被替换，不绕过 D3/D4/D5 gate。

2026-07-09 D7 P0-B/P0-C 修复：D7-owned `vision_png.py` 已补 raw/filtered LOS-rate、低通、限幅和 outlier reject evidence；`runtime_bus.py` 已补每 pair terminal latch，显式记录 dwell/release/reacquire grace，并在 D5 non-locked/reacquire 等 contract reject 后重置视觉 filter、要求后续重新稳定，不把 D5 non-locked 转成可用视觉命令；`pn.py` 已补 `compute_three_dimensional_pn_benchmark()`，runtime bus 可输出 3D geometry PN benchmark/log 字段。默认二维 PN/PNG 控制律未改变，D3/D4/D5 gate 未绕过，D4 `request_center_replan`/`degrade_to_secondary`/`degrade_to_distributed` 仍阻断视觉 PNG。

2026-07-09 D7 P1 switch/gate calibration 输出补齐：D7-owned `terminal_gate.py`、`runtime_bus.py`、`comparison.py`、`replay.py` 和 `calibration.py` 已补齐 main/D6 直接消费字段。单样本记录和 runtime summary 现在包含 `terminal_range_m`、`closing_speed_mps`、bbox/LOS/maneuver gate、`d4_action_block_reason`、`secondary_capability_class`/`secondary_readiness_class`、D5 lock consistency、D3 owner/version consistency、D5 `detect_registration_outcome`/reject reasons、measurement age、projection/covariance trace、YOLO/MOT metadata 和 `threshold_advisory_version`。D4 `request_center_replan`、`degrade_to_secondary`、`degrade_to_distributed` 继续阻断视觉 PNG；二级 plan 若 D4 readiness/capability 非 `takeover_ready`，D7 拒绝为 `secondary_capability_not_takeover_ready`，只解释阻断，不绕过 D3/D4/D5 gate。comparison rows 已覆盖 PN/Pure Pursuit/`png_vm`/`png_ttc` 多 seed 字段，calibration summary 按 guidance law 聚合上述 switch/gate 字段。默认 PN/PNG 控制律未改变，未引入 FRPN/APN/OGL/MPC 主线。

历史基线（2026-07-10 真实 AirSim 2v2 单 seed）只读复核：`p1_gap_closure_2v2_smoke_20260710/episode_006_full_flow` 的 `intercept_summary.json` 记录 2/2 `collision_intercept`，assigned actor/object name 匹配，时间为 3.4s/3.5s。71 行 `control_commands.csv` 中 `guidance_law` 为 `radar_pn=49`、`png_vm=21`、`los=1`，但 `vision_terminal=4` 且仅 INT-01 进入；raw `terminal_switch_allowed=True` 为 2/71，camera/LOS/maneuver gate pass rate 分别为 0.2254/0.2394/0.0563。主要合同拒绝为 `d5_not_locked=30`、`d4_reassign_pending=18`，主要视觉拒绝为 `maneuver_margin_low=13`、`bbox_near_image_edge=7`、`los_rate_window_too_short=2`。该结果只证明当时单次控制链路可完成 assigned-target 碰撞拦截，不能代表当前 M=5/N=2 物理结果。D6 aggregate 的 `visual_png_switch_count=3` 与 raw CSV allowed row count=2 属不同口径，后续必须区分 row pass、mode transition 和 aggregate switch event。

历史基线（2026-07-10 真实 AirSim 2v2 10-seed）复核：`p1_gap_closure_2v2_multiseed_20260710` 覆盖 seeds 1-10 和 20 pairs，得到 18 次 assigned-target `collision_intercept` 与 2 次 `terminal_detection_timeout`，后两次均为 INT-02（seed 3/10）。全 pair 平均 `min_range_m=2.113m`，成功 pair 平均拦截时间 3.589s。884 行控制记录和 execution metrics 汇总为 `radar_pn=530`、`png_vm=289`、`los=65`、`visual_png_switch_count=88`，跨 seed `terminal_switch_allowed_rate` 均值 0.0822。该批次仅作 2v2 历史基线，不能覆盖当前 M=5/N=2 的 0/30 结果；PN/Pure Pursuit/`png_vm`/`png_ttc` 长时多 seed 对照、timeout 根因和阈值 advisory 仍为 P1。

历史基线（2026-07-11 真实 AirSim 四律 smoke）复核：`p1_guidance_four_law_smoke_20260711` 在固定 2v2、seed 7、同几何、reset 分隔条件下完成 Pure Pursuit、Radar PN、PNG-VM、PNG-TTC 各 2 s 的真实 SimpleFlight 执行。四律均 timeout。该证据只证明 selector 和 D3/D4/D5 gate 当时进入 SimpleFlight，不关闭“较长时长、多 seed 受控对照”。D6 产物中的 21 条是指标配对行，不是 21 个独立 seed；不得用该 smoke 推导命中率或导引律优劣。

本次文档状态复核确认：README/PLAN/review 中早期“离线研究模块”和“2v2 actor baseline”口径已调整为“离线研究核 + D7-owned runtime bus + main/runtime AirSim consumer”的三层描述。D7 已完成的 runtime bus、terminal contract gate、owner/version gate、D4 gate blocking、D5 locked/ID/version gate、replay/comparison/calibration summary 状态保持不变；新增 P0/P1 只作为 EVAL backlog 同步，不把已实现 gate/API 倒退为未实现。

## 已实现

| 项 | 实现状态 | 关键证据 | 当前口径 |
|---|---|---|---|
| 中段雷达 PN/PNG | 已实现 | `d7_proportional_guidance/pn.py`; `simulator.py`; `airsim_dry_run.py`; `tests/test_proportional_guidance.py` | `compute_proportional_navigation_command()` 用二维相对位置/速度计算 `N * V_c * lambda_dot`，记录 range、LOS、LOS-rate、closing speed、限幅加速度和限幅转向率。 |
| 中段 PN 越目标重捕 selector | 已实现，待真实多 seed 标定 | `midcourse_reacquisition.py`; `tests/test_midcourse_reacquisition.py` | M5N2 seed1 的 INT-01/INT-04 在最近距离后发散到 143.64m/151.04m。每 pair selector 连续不闭合或 range 从最近点回升时选择 bounded Pure Pursuit，连续恢复正 closing 后回 PN；metadata 记录 selection/reason/streak。未修改核心公式。 |
| 位置比例导引融合 | 已实现主线等价核 | `pn.py`; `airsim_runtime/intercept.py` 读取该 API | delivery 的 truth PNG 不被主线直接调用；主线用 D7 PN 几何和 actor/global-track 等价估计实现位置 PN/PNG。 |
| 末端视觉 PNG gate | 已实现轻量主线核 | `vision_png.py`; D7 tests | `SimpleFlightPngGuidanceFilter` 从 bbox 中心生成 bearing/LOS-rate，支持 `los`、`png_vm`、`png_ttc`，输出 raw/filtered LOS-rate、限幅/outlier evidence 和 `PngGuidanceCommand.velocity_ned`。 |
| TTC 捷联比例导引融合 | 已实现 delivery 等价预处理，非默认 runtime | `vision_png.py`; `tests/test_png_delivery_enhancements.py` | `png_ttc` 增加面积 EMA=.25、window=5、min area=16px2、jump ratio=2.5、裁剪拒绝和 max TTC=20s；`png_vm` 不受 TTC 有效性 gate 影响。 |
| 每个 assignment pair 独立导引状态 | 已实现 | `terminal_delivery.py`; `test_runtime_keeps_terminal_delivery_state_independent_per_assignment_pair`; 既有 1/3/5/7 pair tests | 每 pair 独立保存 image KF、loss count、command window、blind push、LOS/TTC filter 和 latch；binding signature/请求律/reset_pair 变化时只重置对应 pair。 |
| 末端短时 KF/coast delivery API | 已实现 | `terminal_delivery.py`; `test_terminal_delivery.py` | 状态覆盖 acquiring/measured/image_kf_predict/blind_push/reacquired/expired；第一次无锁不伪造视觉 lock，同 global track 才标记 reacquired，到期为 `terminal_visual_lost_after_coast`。 |
| SimpleFlight 控制命令抽象 | 已实现并被 runtime 消费 | `vision_png.py`; `airsim_runtime/intercept.py`; runtime tests | D7 输出 `velocity_ned`；runtime 下发 `moveByVelocityZAsync` 并记录 `control_commands.csv`。D7 模块本身不连接 AirSim。 |
| D3/D4/D5 terminal gate | 已实现 D7 API | `terminal_gate.py`; `test_runtime_contract_failure_immediately_clears_pair_coast` | 校验授权/current/expiry、plan/version、D4 action、D5 locked、friend conflict、execution/safety gate、D5 ID/version 和观测 global ID；任一失败不继续 KF/coast。 |
| D4 主动降级保守阻断 | 已实现 | `BLOCKING_D4_ACTION_REASONS`; D7 active-secondary 测试 | `request_center_replan`、`degrade_to_secondary`、`degrade_to_distributed`、`reassign` 均拒绝视觉 PNG，reject reason 为 `d4_reassign_pending`，日志模式映射 `abort_revoke`。 |
| D4 owner/version/secondary readiness gate | 已实现 | `terminal_gate.py`; `test_terminal_contract_blocks_d4_reassign_until_new_owner_version_and_d5_lock`; `test_runtime_bus_blocks_secondary_plan_until_takeover_ready_and_reports_reason`; `test_runtime_bus_resets_filter_when_same_pair_plan_signature_changes` | D4 提供 `target_node_id/new_plan_owner_id` 时，D3 binding 必须带同一 `owner_node_id`；同一 pair plan/version/owner 变化会重置视觉 filter，旧 D5 lock 不能跨 plan 复用；二级 plan 只有 D4 readiness/capability 为 `takeover_ready` 时才进入视觉 gate。 |
| D5 locked 与 ID/version 一致才切换 | 已实现 | `evaluate_terminal_png_contract()`; D7 tests | 只有 locked、无 friend conflict、execution/safety gate 未显式失败、global ID/version 一致时才允许后续 measured/predicted visual gate。 |
| 30m/稳定 bbox 等切换策略 | 已实现为可配置 gate，不是硬编码 | `PngGuidanceConfig`; D7 tests; `BlocksSmokeConfig` | D7 离线默认 terminal range `250m`，AirSim runtime 默认 `8m`；测试中 `30m` 左右相对距离用于验证 gate。bbox 稳定默认 `min_stable_frames=2`，还需面积、置信度、边缘、延迟、LOS 方差、闭合速度和机动裕度通过。 |
| D7-owned N-pair runtime bus adapter | 已实现 | `runtime_bus.py`; `test_runtime_bus_injects_n_pairs_with_independent_filters_and_summary`; `test_runtime_bus_blocks_visual_png_for_d4_reassign_actions_even_with_good_bbox`; `test_runtime_bus_reports_d5_registration_projection_and_yolo_mot_metadata` | 调用方注入每个 pair 的 D3/D4/D5/observation 状态；D7 输出 terminal handoff、D4/D5/plan/version、terminal range、closing speed、D4 block reason、D5 lock/D3 owner-version consistency、secondary readiness、D5 registration/projection/covariance/Yolo-MOT、bbox/LOS/TTC、gate pass 和 guidance summary 字段，不创建 assignment、不控制车辆、不假设 2v2/5v5。 |
| 四导引律 runtime selector 与审计字段 | 已实现并进入历史 SimpleFlight smoke | `selector.py`; `runtime_bus.py`; `comparison.py`; D7 selector/gate tests; `p1_guidance_four_law_smoke_20260711` | main 可按 pair 请求 `pure_pursuit|radar_pn|png_vm|png_ttc`；混合模式仅在 D3/D4/D5 + 视觉 gate 通过后由 radar PN 切换。历史单 seed、2 s smoke 只证明合同接线，不证明命中率或四律优劣。pending、过期 lease、旧 owner/version、D5 非 locked 或 ID 不一致均保持视觉阻断。未修改 delivery 核心公式。 |
| P0-B terminal latch / reacquire grace | 已实现 | `runtime_bus.py`; `test_runtime_bus_applies_reacquire_grace_after_d5_locked_jitter` | contract 通过后才评估视觉 PNG；D5 non-locked/reacquire 等 contract reject 不发布视觉命令，并触发 filter reset 与后续 reacquire grace；日志字段包含 `terminal_dwell_active`、`terminal_release_grace_active`、`terminal_reacquire_grace_active` 和对应 reject reason。 |
| P0-B bounded detect-loss coast contract | 已实现 | `terminal_gate.py`; `terminal_delivery.py`; `runtime_bus.py`; `test_runtime_allows_bounded_coast_for_consistent_d5_reacquire_only` | fresh switch 仍要求 D5 locked；既有 measured lock 后的 D5 `reacquire` 空观测，仅在 D3/D4、身份/版本、friend conflict 与 safety 字段均一致时允许 bounded KF/coast。D4 硬阻断立即清空。 |
| delivery 生命周期与创新审计 | 已实现，默认保守 | `terminal_delivery.py`; `runtime_bus.py`; `tests/test_png_delivery_enhancements.py` | resource/global/local track、owner/version 变化重置历史；输出 measured/predicted/innovation_rejected/reset/expired。soft reject prediction 与水平 trend coast 默认关闭，friend/duplicate conflict 和旧版本继续 fail-closed。 |
| 6D LOS KF replay | 已实现 optional backend | `los_replay.py`; `tests/test_png_delivery_enhancements.py` | 优先消费 D5 组合后的 `camera_to_ned_rotation`，否则使用 split rotations；两者都保留曝光/姿态时间同步检查。在线 EMA/滑窗默认不变，该项不解决 M5N2 coalition closure。 |
| P1 maneuver-margin diagnostics | 已校正 | `vision_png.py`; `test_maneuver_margin_uses_unclipped_required_turn_rate` | `required_turn_rate_radps` 改为未限幅需求并新增 `turn_rate_capacity_radps`；超能力需求产生负 margin，不修改 PN/VM/TTC 核心公式。 |
| P0-B filtered LOS-rate / spike evidence | 已实现 | `vision_png.py`; `test_visual_png_filters_los_rate_spike_before_near_range_command` | 视觉 PNG 使用 filtered LOS-rate 计算命令；输出 `raw_los_rate_radps`、`filtered_los_rate_radps`、`los_rate_clamped`、`los_rate_outlier_rejected`，尖峰可拒绝为 `los_rate_spike_rejected`。 |
| P2 isolated 3D geometry PN benchmark/log | 已实现为 benchmark/advisory | `pn.py`; `runtime_bus.py`; `test_3d_pn_benchmark_logs_advisory_fields_without_replacing_default_png` | `compute_three_dimensional_pn_benchmark()` 和 runtime bus 输出 `height_delta_m`、`range_3d_m`、`pn3d_los_rate_norm_radps`、`pn3d_commanded_accel_norm_mps2`；显式 `benchmark_only`，不替换默认二维 PN/PNG API。 |
| PN/Pure Pursuit/PNG 对照 report rows | 已实现 D7 接口 | `comparison.py`; `test_guidance_strategy_comparison_reports_all_p1_fields` | 输出 PN、Pure Pursuit、`png_vm`、`png_ttc` 多 seed rows，字段含 `min_range_m`、`terminal_range_m`、`closing_speed_mps`、标准化 runtime law、mode/law transition、raw gate、terminal timeout、command saturation、D4/D5/D3 consistency 和 reject reasons；D6/main 后续负责真实同 seed 报告。 |
| YOLO/ByteTrack bbox/LOS 离线 replay adapter | 已实现 D7 接口 | `replay.py`; `test_bbox_los_replay_normalizes_yolo_bytetrack_and_stays_offline` | bbox replay rows 归一成 `VisionGuidanceObservation`，保留 registration outcome、measurement age、projection 和 tracker metadata，离线评估 D3/D4/D5 contract 与 bbox/LOS/TTC gate；summary 显式 `vehicle_control=False`、`simpleflight_control_called=False`。 |
| 多 seed calibration summary/advisory | 已实现 D7 接口 | `calibration.py`; `test_guidance_calibration_summary_groups_multiseed_runtime_records_and_advisory` | 汇总 runtime outputs、`GuidanceRecord`、comparison rows 或 replay dict，按 PN/Pure Pursuit/`png_vm`/`png_ttc` 输出 terminal range、closing speed、bbox/LOS/maneuver gate、D4 block、D5 lock/D3 owner-version consistency、secondary readiness、D5 registration/projection/covariance/Yolo-MOT 和 reject reasons；阈值建议只作为 advisory，不改默认控制律。 |
| AirSim active center/secondary 合同回归 | 已通过当前 P1 回归 | `airsim_runtime/tests/test_blocks_runtime.py`; runtime CSV/summary 字段 | controlled 5v5 center replan 验证新 plan/binding/version 后 D7 才接受视觉 PNG；2v2 secondary visual PNG gate 验证 `degrade_to_secondary` 阶段阻断旧锁定，二级 owner/version 生效、D4 readiness/capability 为 `takeover_ready` 且 D5 locked 后才允许 `png_vm`。 |
| episode bus 真实执行指标回灌 | 已接线，保持回归 | `main_episode_bus_metrics.json`; `control_commands.csv`; `intercept_summary.json` | D7 runtime summary 已接入 episode bus；正式 metrics 可包含 D7 真实执行后的 `intercept_success_count`、`collision_intercept_count`、`guidance_law_counts` 等；raw contract metrics 仅作执行前诊断。 |
| D3 replan 后 current binding gate | 已接线并通过 controlled 5v5 回归 | `terminal_gate.py`; runtime summary/version metadata | D4 真正请求中心重规划后，D7 只接受新的当前 D3 binding/version；旧 plan、stale binding、revoked assignment 和 plan mismatch 均阻断视觉 PNG。 |
| D4 软风险 continue_center 路径 | 已接线，保持回归 | `D4GuidancePermission(action="continue_center")`; D7 tests | 低 cost margin、短时低置信度、无冲突 `ambiguous/reacquire` 由 D4 观察时，D7 不误映射为 `d4_reassign_pending`；后续仍需 D5 `locked` 和视觉 gate 通过。 |
| Pure Pursuit baseline | 已实现轻量版 | `compute_pure_pursuit_command()`; tests | 用于离线对照，并由中段重捕 selector 以有界转率临时调用；不引入 PythonRobotics。 |

## EVAL P0/P1 同步状态

| EVAL 条目 | 当前项目状态 | D7 GAP 同步口径 | 优先级 |
|---|---|---|---|
| 末端切换迟滞 | 已补 terminal latch：dwell/release/reacquire grace 字段和 reject reason 可被 runtime/D6 消费；D5 non-locked/reacquire 不会绕过 contract 发布视觉命令。 | 保持 D3/D4/D5 gate，不让 D7 分配、授权或改写 `global_track_id`；真实 AirSim 多 seed 中继续观察 switch count。 | P0-B done / P1 runtime validation |
| LOS 角速率滤波 | 已补 raw/filtered LOS-rate、低通、限幅和 outlier reject evidence；近距视觉 PNG 尖峰由 D7 测试覆盖。 | 不引入复杂控制器；后续用真实 bbox replay/AirSim 数据校准 `max_los_rate_*` 阈值。 | P0-B done / P1 calibration |
| 三维 PN 几何对照和日志 | 已补 `compute_three_dimensional_pn_benchmark()` 和 runtime bus 3D benchmark/log 字段；主线仍是二维水平 NED PN/PNG。 | 继续 200m 高差、3D target 或高度差拦截时保持 P0-C；否则作为 P1 calibration/benchmark。完整三维控制律和高度通道不替换默认 API。 | P0-C conditional / P1 benchmark otherwise |
| 3D PN/True PN/APN/FRPN 对照 | 隔离式离线质点 benchmark 已实现，replay 只保留为可选输入接口；FRPN 是研究近似。 | 只作为 P2 benchmark/advisory 比较 miss distance、控制努力、峰值加速度和耗时；不进入默认主线，不替换 PN/PNG。 | P2 optional benchmark |
| PN/Pure Pursuit/PNG 多 seed 对照 | D7 已完成四律 selector、comparison rows、迁移/raw gate/timeout/saturation 字段和 calibration helper；main 已有历史 `png_vm` 2v2 10-seed 基线和四律单-seed 2 s smoke。 | 历史短时 smoke 只证明 selector 和 D3/D4/D5 gate 进入 SimpleFlight；仍需在当前 topology、相同 seed/几何/阈值下运行较长时长、多 seed 四律对照，D7 保持字段稳定且不允许对照路径绕过 gate。 | P1 main/D6 integration |
| 预测拦截点 | 当前主要基于 PN 视线率，D7 comparison/calibration 可输出对照字段但未形成默认 intercept-point guidance。 | 输出 predicted intercept point 并与 PN 对比；只作为 P1 对照能力。 | P1 |
| 动力学补偿 | SimpleFlight 高层速度接口已可执行，D7 已记录 turn/maneuver margin；真实执行延迟、加速度限制和饱和响应仍需标定。 | 将命令饱和、响应延迟和加速度限制进入 guidance log/report；不直接升级为 PX4/body-rate 默认主线。 | P1 |

## 部分实现

| 项 | 当前做到什么 | 还缺什么 | 原因 | 优先级 |
|---|---|---|---|---|
| 真实 AirSim 多 seed calibration | 2v2 candidate 已完成 10 seeds、`20/20` 非退化验收；锁定后两帧 prediction 已在真实链路验证。M5N2 当前只有 8s 短窗 0/9。 | 在同一 z=-30m、35s 高净空几何下做 M5N2 baseline/candidate paired，分层统计 target、active-primary、coalition completion。 | 8s 与 35s 的几何和运行窗口不等价；D7 不生成 assignment、D4 仲裁或 D5 lock。 | P1 physical closure |
| 相机前移 0.5m / FOV / 姿态朝向目标 | AirSim settings/tests 已覆盖 tuned terminal camera `X=0.5m`、`640x480`/`120deg` FOV；runtime 支持 `look_at_target` yaw 和 CV camera follow/look-at。 | D7 主线没有直接读取真实 camera intrinsics/extrinsics、畸变、姿态估计，也没有把 FOV 从 runtime 自动传入 `PngGuidanceConfig`。 | D7 当前保持轻量 bbox 几何；相机管理属于 main/runtime。 | P1/P2 |
| 末端视觉 PNG 与检测闭环 | AirSim detect metadata bbox 可进入 D7 gate；D5-shaped lock 通过后 runtime 可进入 `png_vm`；D7 已提供 bbox/LOS 离线 replay adapter；D7 delivery actor 默认外观和 main runtime actor asset default 均已对齐到无人机 mesh asset `Quadrotor1`。 | YOLO/ByteTrack 真实图像链路只作为离线 replay 或 optional 实验路径；若接入，也只产出 D5 local track 与 D7 bbox/LOS gate 摘要，不进入默认 SimpleFlight 控制；后续需要真实 AirSim 验证和阈值/检测调参。 | 默认不保存 PNG，不要求 Ultralytics/GPU/权重；先用 replay/calibration 稳定阈值。 | P1 optional |
| TTC 面积通道 | `png_ttc` 已实现面积 EMA=.25、5 帧斜率、16px2 最小面积、2.5 跳变比、裁剪拒绝和 20s 最大 TTC；`png_vm` 不变。 | 运行真实 `png_ttc` 多 seed，统计 jump/clipping/non-expanding/out-of-range 拒绝及物理结果。 | 当前 2v2 candidate 主场景仍使用 `png_vm`，不能用其结果关闭 `png_ttc` 标定。 | P1 calibration |
| soft prediction / trend coast | 两者实现完成但库默认关闭；本地 1-5 帧矩阵已验证统一 `0.25s` 硬上限，trend helper 固化 paired seed、实际触发、错误绑定、命令跳变和物理成功判据。 | 在真实 AirSim 受控触发 dropout/trend 并把 execution rows 输入 helper。 | optional candidate 不能因代码存在或 2v2 非退化结果自动晋级。 | P1 optional validation |
| 机动能力 gate | PN 有加速度/转向率限幅；视觉 gate 估计 required turn rate、turn capacity、maneuver margin。 | 真实动力学、姿态/推力/延迟、PX4 饱和响应和三维高度通道未建模；200m 高差 mobile recon stress 只能证明观测可见性改善，不能替代机动能力 gate。 | P1 继续标定现有二维 gate；3D PN、True PN、APN、FRPN 仅进入 P2 optional benchmark。 | P1 calibration / P2 benchmark |
| D6 指标输入 | D7/runtime 日志已有 mode、range、LOS、closing speed、gate reject reason、plan/D4/D5 metadata；D7 runtime summary 已补齐 guidance mode、handoff、D4/D5/plan、camera/LOS/maneuver gate、bbox/TTC/LOS 数值摘要和 reject reason 分布；正式 main bus metrics 已可合并真实执行结果；D7 已提供 comparison rows 和 replay summary。 | 多 seed N-pair 真实运行报告、阈值版本、分组对照和 raw contract vs execution metrics 双口径说明仍需 main/D6 汇总。 | 指标聚合属于 D6/main，不是 D7 本地测试即可完成。 | P1 |

## 未实现

| 项 | 当前状态 | 未实现原因 | 缺少条件 | 优先级 |
|---|---|---|---|---|
| 更真实机动约束 / 在线 default 3D PN 控制律 | D7 主线仍是二维水平 NED 控制抽象；3D PN、True PN、APN、FRPN 的本轮验证证据仅为隔离式离线质点 benchmark。 | 默认三维控制、动力学和高度通道会扩大接口面，不属于当前 P1 物理闭环。 | 3D state contract、姿态/推力/高度通道、平台响应和 D6 三维指标。 | P2 benchmark complete / online deferred |
| 在线 default True PN / APN / FRPN | 未实现为默认主线；隔离 P2 benchmark 已实现，其中 FRPN 是研究近似。 | 高机动算法公式、目标加速度估计和场景尚未冻结，FRPN 也不是规范实现。 | 保持 P2 与在线 runtime 隔离；不绕过 D3/D4/D5 gate，不替换默认 PN/PNG。 | P2 optional benchmark complete / online deferred |
| MPC / NMPC | 未实现。 | 当前 PN/PNG 足够支撑第一阶段闭环；MPC 需要强约束模型和求解器。 | 平台动力学、约束、求解器依赖、实时预算、失败回退。 | P3 |
| 硬件飞控 / 实机控制 | 未实现。 | 本仓库是研究/仿真路径，不能把 D7 输出当实机控制指令。 | 实机安全流程、kill switch、围栏、台架标定、人工接管。 | P3 |
| PX4/MAVLink/body-rate 默认主线 | delivery 中有脚本和报告，main D7 主线未接入。 | Offboard、解锁、推力和坐标系风险高，不适合默认路径。 | 继续后置，不属于本轮 P2 benchmark。 | deferred |
| YOLO/ByteTrack 控制闭环 | delivery 有 detector 和报告，D7 已提供 bbox/LOS 离线 replay adapter，但主线不直接控制。 | 默认 runtime 使用 `simGetDetections` metadata，不保存 PNG，不管理模型权重/GPU。 | 图像帧流、YOLO 权重、class id、依赖版本、GPU/CPU 预算、MOT 稳定性、D5 local track 事件流和 main/D6 replay 数据。 | P1 先 replay |
| OpenCV/KCF/solvePnP/完整标定 | D7 主线未依赖。 | 当前只需 bbox 到 LOS 的轻量几何。 | 相机内外参、畸变、重投影误差、图像流、性能预算。 | P2 |
| ViSP / ROS2 tf2 / message_filters | 未实现。 | 当前项目不是 ROS2 graph 或视觉伺服栈。 | ROS2 runtime、frame tree、带戳消息 schema、bag/replay 基准。 | P3 |

## 缺少条件

1. **真实 AirSim 多 seed calibration**：D7 已提供本地 `D7RuntimeBus` adapter、comparison rows、bbox/LOS replay adapter 和 `summarize_guidance_calibration()` advisory helper，main 已把 D7 runtime summary、delivery audit 和正确 M5N2 topology 接入 episode bus。下一验收必须使用同一 z=-30m、35s 高净空几何运行 baseline/candidate paired；当前 8s 短窗不可与既有基线比较。
2. **D5 状态事件流**：`locked/ambiguous/hold/reacquire`、锁定丢失、重捕获、friend conflict、duplicate lock 和 timeout 需要持续进入 D7 pair state machine 与 D6 指标。
3. **视觉 replay 条件**：D7 已提供 bbox rows 到 bbox/LOS gate 的离线接口；YOLO/ByteTrack 或真实图像链路只作为 replay/optional，需要图像或 bbox replay 数据源、camera intrinsics/extrinsics、bbox timestamp、local track 连续性、measurement age、LOS-rate 噪声、丢检策略和 D5 local track 事件流。
4. **飞控/动力学条件**：PX4/MAVLink 或真实飞控升级前必须有 Offboard 状态机、推力/坐标/限幅标定、饱和日志、安全边界和回归 baseline。
5. **对照实验条件**：P1 的 PN、Pure Pursuit、`png_vm`、`png_ttc` 物理闭环需要同批多 seed 场景、统一成功/失败判据、阈值版本和 D6 报告。3D PN、True PN、APN、FRPN 本轮仅有隔离式离线质点 P2 benchmark，不能与在线 P1 验收混写；默认 PN/PNG API 不替换，D3/D4/D5 gate 不绕过。

## 下一步优先级

| 优先级 | 下一步 | 验收口径 |
|---|---|---|
| P0-B done | 工程化闭环稳定性：末端视觉 PNG 切换迟滞和 LOS 角速率滤波已在 D7-owned runtime bus/filter 中补齐；继续保持 D7 不分配、不授权、不改写 `global_track_id`。 | D7 tests 通过；D4 `request_center_replan`/`degrade_to_secondary`/`degrade_to_distributed`、D5 non-locked、D5 `assigned_global_track_id` 与 binding 不一致、ID/version mismatch、friend conflict 均拒绝视觉 PNG；输出 filtered LOS rate，近距命令尖峰被限幅/拒绝。 |
| P1 done/保持 | D7RuntimeBus、comparison、replay、calibration summary/advisory、D4 gate blocking、D4 secondary readiness block、D3/D4/D5 terminal contract gate、owner/version gate、D5 registration/projection/Yolo-MOT reporting、episode bus runtime summary、handoff/guidance summary fields、controlled 5v5 center replan 和 2v2 secondary visual PNG gate。 | D7 tests 通过；main CSV/summary 持续写出 `plan_id/plan_version/owner_node_id/track_version/d4_action/d4_action_block_reason/d5_decision_state/terminal_contract_reject_reason/terminal_range_m/closing_speed_mps`；D7 summary 保留 `guidance_mode_counts`、`terminal_handoff_state_counts`、gate pass rate、bbox/TTC/LOS 摘要、D5 lock/D3 owner-version consistency、secondary readiness、registration/projection 摘要和 `visual_png_switch_count`；D7 calibration summary 保留 threshold advisory 和 benchmark-only 3D/FRPN 字段；D4 replan/degrade 或 secondary 非 `takeover_ready` 阶段不调用旧锁定视觉 PNG。 |
| P1 paired M5N2 | 在相同 z=-30m、35s、seeds 和阈值下运行 baseline/candidate；不得把 8s 短窗与 35s 基线混算。 | 分层输出 target、active-primary、coalition completion、最近距离、D5 hold/reacquire、D7 filter state 和 truth-use。 |
| P1 dropout/TTC helper done | D7-owned 本地 1-5 帧矩阵和 TTC 四类拒绝多 seed 汇总已经实现。 | `141 passed`；1-2 帧保持同 identity/plan 的有界预测，默认 10Hz 第 3-5 帧超过 0.25s 后 fail-closed；TTC helper 报告 jump/clipping/non-expanding/out-of-range。 |
| P1 trend candidate helper done | trend coast 保持默认关闭，paired 晋级 helper 已实现。 | 仅当 seeds 配对、candidate 实际触发、错误绑定为 0、命令跳变不恶化且物理成功不下降时，才输出晋级建议。 |
| P1 real execution open | 真实 AirSim dropout、`png_ttc` 和 trend candidate 仍待 main 编排。 | execution rows 必须输入上述 helper，并由 D6 形成正式多 seed 结论。 |
| P1 midcourse validation | 在 M5N2 多 seed 验证 PN -> bounded PP reacquisition -> PN 的重捕闭环。 | 按 pair 记录 selection/reason、负 closing entry、正 closing recovery、切换次数、重捕时间和发散后最终 min/final range；校准 enter/exit closing 与 2/3 帧迟滞。 |
| P1 | 预测拦截点、二维 gate 与动力学响应标定。 | 命令饱和、响应延迟和加速度限制进入在线 guidance log；不混入 P2 的 3D/True PN/APN/FRPN benchmark。 |
| P1 optional | 将 D7 bbox/LOS replay adapter 接入 YOLO/ByteTrack 或 AirSim detect replay 数据。 | replay 生成 D5 local track 与 D7 bbox/LOS gate 摘要；`vehicle_control=False`、`simpleflight_control_called=False`，不进入默认 SimpleFlight 控制。 |
| P2 optional | 保持已完成的隔离式离线质点 3D PN、True PN、APN、FRPN benchmark；replay 只作为可选输入接口。 | 不修改位置 PN 或 `png_guidance_delivery` VM/TTC 核心公式，不进入默认 SimpleFlight runtime。 |
| P3 | 评估 MPC/NMPC、ViSP、ROS2。 | 仅在需要强约束控制或机器人中间件集成时进入，不作为当前 D7 主线阻塞项。 |

## 关键依据路径

- `research_modules/d7_proportional_guidance/d7_proportional_guidance/pn.py`
- `research_modules/d7_proportional_guidance/d7_proportional_guidance/midcourse_reacquisition.py`
- `research_modules/d7_proportional_guidance/d7_proportional_guidance/simulator.py`
- `research_modules/d7_proportional_guidance/d7_proportional_guidance/terminal_gate.py`
- `research_modules/d7_proportional_guidance/d7_proportional_guidance/vision_png.py`
- `research_modules/d7_proportional_guidance/d7_proportional_guidance/runtime_bus.py`
- `research_modules/d7_proportional_guidance/d7_proportional_guidance/replay.py`
- `research_modules/d7_proportional_guidance/d7_proportional_guidance/comparison.py`
- `research_modules/d7_proportional_guidance/d7_proportional_guidance/airsim_dry_run.py`
- `research_modules/d7_proportional_guidance/tests/test_proportional_guidance.py`
- `research_modules/d7_proportional_guidance/tests/test_airsim_phase1_dry_run.py`
- `research_modules/d7_proportional_guidance/README.md`
- `research_modules/d7_proportional_guidance/PLAN.md`
- `research_modules/d7_proportional_guidance/png_guidance_delivery/README.md`
- `research_modules/airsim_runtime/intercept.py`

## M 对 N 协同导引 P0/P1 复核（2026-07-11）

依据 `D7_M_TO_N_COOPERATIVE_GUIDANCE_REVIEW.md` 的 12 篇主要论文和 5 个开源候选审计，D7 已实现中心化 coalition 合同的成员级执行门控，但仍未实现 impact-time consensus、终端扇区协调或成员间避碰控制律。不得把版本/时间窗 gate 或多个独立 PN pair 称为完整协同导引。

- **P0：无新增 blocker。** N-pair PN/PNG、D3/D4/D5 gate、SimpleFlight 消费链和 k=1 合同保持回归；D7 继续不分配、不授权、不改写 `global_track_id`，也未修改 `png_guidance_delivery` 核心公式。
- **P1 done：中心化 coalition 合同门控。** binding/runtime 已携带 coalition/version、role、wave、coordination mode、arrival window 和 activation/version；所有 coalition 成员要求本资源 D5 locked、D5 plan/track/coalition version 一致及 coalition visual completion。测试覆盖 T001 两个 primary 独立切换、T002 k=1、D4 replan/pending 与 no-change ack、standby reserve 视觉匹配阻断/新版本激活、visual completion 缺失/未完成和版本冲突。row/summary 明确保留 `terminal_contract_allowed`、`visual_png_switch(_count)` 与拒绝原因。
- **P1：协同控制律与基准缺口。** 仍需研究独立 PN、同步 ITCG、序贯和混合主备四种策略；D7 不拥有联盟形成、成员选择、波次授权或原子联盟重构。
- **P1：终端安全缺口。** 同步到达必须增加 terminal sector/impact angle、成员最小间距、碰撞风险、命令饱和和 FOV 丢失评价；time-to-go consensus 本身不能证明安全。
- **P1：通信与失效缺口。** 需要比较 leader/中心、二级节点和分布式邻居通信，在时延、间歇通信、成员退出和版本失配下的到达误差与保守退出行为。
- **P1：开源实现缺口。** 未发现同时具备协同到达、多旋翼模型、避碰、清晰许可证和自动测试的成熟库。许可证明确的 MATLAB 候选仅支持单拦截器 ITCG，其余协同候选不可直接复制。

本轮 D7 P2 只保留 3D PN、True PN、APN、FRPN 的隔离式离线质点 benchmark；其他实机或全栈升级继续后置，不进入当前 P1/P2 执行序列。
