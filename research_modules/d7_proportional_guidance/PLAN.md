# D7 经典比例导引架构计划

## 2026-07-15 M5N2 20-case 证据收口与后续计划

main 已完成 baseline/candidate 各 10 seeds 的 20 个真实 AirSim SimpleFlight M5N2 case。M5N2 `20/20` 后 TERM 生效前仅额外完成 `p1_terminal_timing_funnel_10seed_20260715_png_ttc_2v2_seed001`；该单 seed不纳入本次 M5N2 统计，也不用于分析或候选晋级，其余 tuned case 和全部 dropout 均未执行。两组合计 pair/target/coalition 为 `12/60`、`12/40`、`0/20`；第二 primary 按各 case 的 active membership 动态识别，不写死资源编号，物理结果为 `0/20`。candidate 的逐 seed non-degradation=false、trend coast 触发=0、soft-specific duration=0，故继续 default-off，不进入主线。

当前 P1 收敛顺序调整为：

1. 先处理第二 primary 在曾达到 D5 lock/contract/control 后仍停在 `8.843-14.740 m` 的物理闭环问题；七阶段证据为 `assigned/visible/associated/contract=20/20`、`control/mode=17/20`、physical=`0/20`。20 个第二 primary 最终均为 `collision_stop`，但 collision object 未写盘，需由 main 补齐碰撞对象、成员间距和停控归因后再区分航路、平台与视觉门限；当前证据不能把失败归因于 PN、PNG、LOS 或外推公式。
2. 保持 `soft_prediction + trend_coast` 为 optional，只有在真实触发、错误绑定为 0、命令连续性不恶化、paired 物理成功不下降同时满足时才可晋级。
3. 将实时性治理置于阈值放宽之前：20 case 的 control tick 为 `1069.4/1254.1 ms` mean/P95，全部超过 100 ms；main-bus 为 `349.3/487.4 ms`，其中 D7 stage 仅 `4.84/5.78 ms`。main 应优先优化 frame sampling、D1 fusion 和 control RPC，并保持两层 timing 独立报告。
4. 下一轮真实 AirSim 必须同时写盘持续 measured lock、collision object/member separation、完整 pair first-failure 和 closing-speed/3D maneuver 证据；在此之前，第二 primary 与 coalition 物理闭环仍是 P1 未闭合项。

本轮只收口证据与计划，位置 PN、VM/TTC PNG、LOS 滤波、image-KF/有界外推核心公式和 D3/D4/D5 门控全部保持不变；online truth identity/state 使用计数为 `0/0`。

## 2026-07-15 被动诊断与受控回归计划完成

本轮已按“现有证据审计 -> 纯诊断实现 -> 定向回归 -> D7 全量回归 -> 文档同步”完成。新增规范 pair 漏斗、第二 primary 完整漏斗/首达时刻、current measured lock 与 historical lock 分离、seed2 单帧 dropout 时序，以及 `bbox_area_jump/bbox_clipping` 的控制阻断、雷达 PN 回退和身份不变校准汇总。实现只位于 D7 诊断与 calibration helper；PN/PNG/LOS/外推公式和上游门控未改。

2026-07-15 本地确定性场景共 `190 passed`，验收阈值零失败；seed2 单帧序列为 measured `0.0-0.2s`、dropout/predict `0.3s`、reacquired `0.4s`。下一步由 main 在真实 AirSim 2v2/M5N2 至少 10 seeds 中持久化相同字段，验证第二 primary 首失败分布、5 米物理完成、真实单帧 dropout 和 TTC 扰动覆盖；本轮不要求同时到达，也不据本地用例晋级任何候选算法。

## 2026-07-14 actual-execution 证据计划同步

真实 AirSim seed-1 canonical 证据已完成 P0 验收。五层按 contract/control/terminal-switch/mode/physical 独立统计：tuned 2v2 为 `35/26/26/2/2`，M5N2 为 `67/0/0/0/2`，合计 `102/26/26/2/4`；五层均为 `available`。`terminal_switch_allowed_count` 从已写盘 `control_commands` 独立统计，不由 control 层回填。M5N2 active-pair 物理成功为 `2/3`，第二 primary 最近约 `11.02 m`；target `2/2` 与 coalition `0/1` 使用独立分母。两个 required case 的可用性为 `2/2`，identity/state online truth 均为 0；D6 formal overall fail 只表示完整 P1 suite 尚未通过，terminal-switch 和 main/D6 canonical 聚合均已闭合。

后续不修改 PN/PNG/LOS/外推代码或算法，当前 P1 计划聚焦：M5N2 第二 primary 获取与 5 米闭环；同配置 multi-seed、真实 dropout 与 candidate 配对；约 `123.3 ms` 与 `384.6 ms` loop latency 的拆分和预算治理；pair funnel、range/closing speed、三维几何与平台机动能力标定。3D PN、True PN、APN、FRPN 在线化和同时到达不列当前 P1。

## 2026-07-14 导引律执行语义合同计划完成

本批按“DTO/helper 审查 -> canonical 字段补齐 -> 不变量回归 -> 文档同步”完成。D7 新增 `d7_guidance_law_semantics_v1`，把配置策略、已计算视觉候选律和实际执行律分开，并定义 `executed_visual_mode_switch` 只能在 live sample 同时满足 effective contract、visual latch、effective control 和 `vision_terminal` 入口转换时为 true。`guidance_law_semantic_violations()` 与 summary 负责发现候选/执行混写和无授权视觉执行；旧字段作为兼容 alias 保留。

D7 全量回归现为 `188 passed`。actual-v2 之前的两个 postbatch M5N2 episode 曾出现物理控制日志与 episode bus replay 使用不同 plan/state instance；当前 canonical actual 已从同一持久化执行证据独立形成五层正式聚合，并以 plan identity 一致关闭该问题。后续 multi-seed 与 pair-funnel 标定继续保留 `configured/candidate/executed`、raw gate、latch、effective control 和 executed switch，不修改导引律语义或核心控制公式。

## 2026-07-14 M5N2 no-switch 诊断计划完成

本轮按“只读真实证据审计 -> D7 状态/诊断补齐 -> 模块回归 -> 文档同步”执行。已实现 `d7_pair_guidance_funnel_v2`：按 pair 记录配置交接距离、D5 declared/measured lock、raw gate、camera/LOS/closing-speed/maneuver、latch/effective contract/control 和物理结果；新增全 pair first-failure 与 funnel available/reached 摘要。closing-speed 只暴露既有门限结果，不改变 `min_closing_speed_mps`、PN/PNG/LOS/外推公式或任何上游门控。

seed-1 现有证据确认 M5N2 baseline/candidate 的失败不是 soft prediction/trend coast 退化：两候选均未获得 raw gate，也从未建立 terminal latch/effective control；两个 pair 在约 `35-39 m` 因 collision stop 离开、一个 pair 在约 `26 m` 因 `d5_not_locked` acquisition timeout 离开。D7-owned 诊断断点和 canonical 五层聚合均已关闭。下一步扩展同配置 multi-seed、真实 dropout/candidate 和 pair-funnel 字段覆盖，并修复航路净空和 D5 acquisition；在这些证据完成前，不晋级 soft prediction/trend coast，也不修改核心控制公式。

## 2026-07-14 末端状态/指标语义 P1（代码级关闭）

本轮已关闭 runtime row 与聚合指标把 raw gate、bounded coast、terminal latch、实际控制授权和 episode 终止快照混为同一布尔值的问题。`d7_terminal_semantics_v2` 新增版本化 canonical 字段：raw terminal gate、latched visual mode、effective terminal contract、effective control authorization、mode transition 和 termination snapshot；既有 `terminal_contract_allowed`、`terminal_switch_allowed`、`terminal_control_allowed`、`visual_png_enabled/switch` 作为明确映射的 backward-compatible alias 保留。终止/abort snapshot 不再伪装成实时控制样本，也不会留下无 scope/reason 的 `contract=false/control=true` 组合。

同时补齐真实 dropout 审计：D5 `reacquire` 后没有可用 delivery command 时，明确区分 `contract_reset`、`prediction_window` 和 `measured_lock_not_established`。bounded coast 仍只允许同 resource/global/local identity、current plan/owner/version、D4 明确允许且无 friend/duplicate/safety 冲突；任何不一致继续 fail closed。2026-07-14 本地 D7 全量场景现为 `188 passed`，验收门槛为全量零失败，覆盖 termination snapshot、raw/latch/effective scope、三类 dropout 原因、local-ID coast 阻断、pair first-failure/funnel、导引律执行语义和旧字段 alias。canonical actual 五层已经正式可用；真实 dropout/candidate 与 pair-funnel/closing-speed 标定继续作为 P1。位置 PN、VM/TTC PNG 与 `png_guidance_delivery` 核心公式未修改。

## 2026-07-14 truth-state P0 关闭与后续验收

main/runtime 已完成代码级修复：默认、主动中心重规划和主动二级接管的 SimpleFlight 控制均消费 D2 estimated target state、协方差和双时间戳；D3/D4/D5 主动合同覆盖不能注入目标运动状态或 actor alias；无估计或陈旧估计时 fail closed。actor truth 只允许进入合成传感器和运行后离线 NED 三维 5 米评分。AirSim runtime mock 回归 `130 passed`，其中覆盖 actor truth 扰动命令不变、两条主动路径 `truth_state_online_use_count=0` 以及 `target_state_source=d2_estimated_global_track`。D7 PN/PNG 核心公式未修改。

后续计划不再把它列为 P0 代码或证据阻塞。2026-07-14 actual-v2 真实 AirSim seed-1 已同时记录 `truth_identity_online_use_count=0` 和 `truth_state_online_use_count=0`，canonical P0 证据链关闭；迁移前 2v2/M5N2 数字仍只保留为历史接口/离线评分基线。后续只把多 seed、第二 primary、延迟和几何标定列为 P1。

## 目标

D7 提供一个可被主流程接入的二维比例导引研究核和被动 runtime 导引合同模块。模块目标不是实现真实平台控制，而是给集成仿真提供清晰、可测试、可记录的“雷达中段 + 视觉末段”比例导引、D3/D4/D5 gate 和 N-pair 日志抽象：

- 中段使用 `radar_midcourse` 模式，输入来自全局航迹或雷达航迹估计。
- 末段使用 `vision_terminal` 模式，输入来自像素/LOS 观测估计。
- 视觉终端使用从 `png_guidance_delivery` 抽取的 SimpleFlight 兼容 PNG gate，先判断相机识别质量、LOS 质量、机动裕度和剩余窗口，再允许进入视觉 PNG/LOS 导引。
- 输出统一的 `GuidanceRecord`，便于后续闭环日志、指标统计和 GIF 可视化。

本模块只做离线二维质点运动、被动 runtime state injection、算法解释、日志评估和 calibration/advisory 字段生成；不提供真实飞控接口、硬件驱动、实时通信、火控参数、毁伤模型、自动处置或授权绕过逻辑。

## 2026-07-13 当前状态同步

commit `33e6fa0` 已完成 delivery 增强：图像 KF 按 resource/global/local track 与 plan owner 隔离；`png_ttc` 已加入面积 EMA、窗口斜率、跳变、裁剪和 TTC 范围治理。当前增量又将所有丢检外推统一限制在最后量测后 `0.25s` 内，并提供 dropout/TTC/trend 三类报告 helper。soft innovation prediction 与水平 LOS trend coast 仍为默认关闭的 candidate，6D LOS KF 只用于 replay，不进入默认在线控制。2026-07-14 当前权威 D7 全量回归值为 `188 passed`；后文较小计数均为对应历史子任务完成时的阶段值，不代表当前全量结果。

2026-07-12 已实现显式 per-primary terminal authorization。`AssignmentGuidanceBinding` 新增 `terminal_authorization_scope` 和 `arrival_coordination_required`；只有 `per_primary + false` 的 active primary 可跳过共同视觉完成与 arrival window，按本资源 D5 lock 和视觉/机动门控独立切换。旧合同缺省仍走完整 coalition gate；standby reserve、D4 pending/reconfiguring、身份/版本、fallback commit/ACK/lease/epoch 均未放宽。runtime 输出 scope 和 `bypassed_arrival_only` 等审计字段，PN、`png_vm`、`png_ttc` 公式未修改。

2026-07-12 posefix replay 专项已定位滚动 binding 抖动：四组真实 CSV 中 plan identity change 为 `159-276` 次、版本回退为 `35-90` 次；三类指定拒绝样本全部 `visual=0` 且使用 radar PN。D7 现仅对同资源/目标/owner/联盟角色、activation 不变且版本单调前进的 current binding 保留图像滤波历史，并仍以最新版本逐帧重验 D3/D4/D5。`coalition_window_closed` 只关闭本窗口视觉 PNG，继续 radar midcourse；`d4_owner_missing` 不做 owner 推断。真实 main/runtime 仍需修复 `airsim_control_plan v1` 瞬态和验证多 seed 收益。

本轮新增 P1 M5N2 被动诊断与候选预筛接口。`cooperative_diagnostics.py` 消费既有 D7 runtime output、D3 candidate metadata 和 main 注入的物理/成员间距证据，按 case/seed/pair 输出 assigned、active、radar、D5 visible/associated/locked、terminal contract/control/mode、5m physical 及首个失败原因，并汇总第二 primary、成员间距、reserve 越权和 owner/version mismatch。联盟完成只要求同 episode 分别进入 5m；到达离散保留为观察值但不进入本阶段预筛排序。接口只给 main/D6 提供 advisory/rows，不改变候选默认值，不绕过 D3/D4/D5 gate，也不修改 PN/PNG 核心公式。

迁移前真实 AirSim 2v2 candidate 在 10 seeds、20 pairs 中达到 `20/20` 的 5m 离线评分成功；当时的 `online truth=0` 只覆盖 truth identity，未覆盖 truth state provenance。该结果只满足当时相对旧基线 `19/20` 的接口非退化检查，不能作为当前 truth-isolated 物理闭环证据；自然运行也未触发 soft prediction 或 trend coast，不能据此宣称增强算法提高成功率。锁定后注入两帧检测丢失的专项仍可证明 0.25s 内同身份、同计划上下文的有界预测状态机工作，但物理结果须由同 seed 重跑复核。

2026-07-13 最终 P1 批次完成了 40 个迁移前真实 AirSim SimpleFlight M5N2 episode，拓扑固定为高威胁目标 `2 primary + 1 standby reserve`，联盟完成只要求两个 active primary 在同一 episode 内分别进入 5m，不要求同时到达。最佳 profile 的 coalition completion 为 `5/10`，全部 profile 合计为 `8/40`，未达到 `8/10` 晋级门限。D6 四层统计为 contract `35`、control `7`、mode switch `9`、physical `62`；四层来自不同判定层和统计口径，必须分别解释。该批次的 `online truth=0` 只证明 truth identity 使用为 0，truth state 当时未单独审计，因此 physical 层只保留为迁移前离线评分基线。位置 PN 与 `png_guidance_delivery` 视觉 PNG 核心公式均未修改。

D5 原生 ByteTrack/BoT-SORT 在本轮 admission sweep 中未准入，D7 默认视觉输入继续来自 AirSim `simGetDetections` 经 D5 形成的 bbox/lock 证据。当前开放 P1 不再是 DTO/topology 或 canonical 聚合，而是第二 primary 的视觉 gate/acquisition 稳定性、同配置 multi-seed/dropout/candidate、loop latency，以及 pair funnel/closing speed/三维几何与平台机动能力标定；soft prediction、真实 `png_ttc` 和 trend coast 仍作为受控 candidate，不自动晋级默认路径。

当前优先级固定如下：

- **P0 已闭合**：继续保持 D7 不分配、不授权、不改写 `global_track_id`，D4 重规划/降级期间阻断视觉 PNG，未激活 reserve 保持 standby；main/runtime 必须持续保证在线 truth identity/state 分别为 0。
- **P1 接口已完成**：coalition/version/role/wave/arrival-window/activation gate、每 pair 独立 filter/latch、D5 coalition visual completion 和 D3/D4/D5 一致性检查均已进入回归。
- **P1 fallback commit gate 已完成**：中心失效/fallback 的显式多资源联盟必须具备 `committed|executing` 状态、有效 lease、匹配 epoch/plan/coalition version、完整 required ACK；中心正常和无 coalition 的 k=1 保持原 gate。
- **P1 per-primary scope 已完成**：显式 `per_primary + arrival_coordination_required=false` 只取消共同到达和其他 primary 同帧锁要求；每个 active primary 的 D3/D4/D5、身份、视觉质量和机动门控保持独立强制，reserve 不自动激活。
- **P1 合同层已闭合**：CV 8/10、D4 commit-aware gate 与 M=5/N=2 topology 均已有集成证据。
- **P1 delivery 实现已闭合**：生命周期重置、统一 `0.25s` 外推硬上限和 `png_ttc` 面积治理已实现；默认 10Hz 本地 1-5 帧矩阵为前两帧 image KF、后三帧 expired/fail-closed。soft prediction/trend coast 默认关闭，6D LOS KF 保持 replay-only。
- **P1 calibration helper 已闭合**：`delivery_calibration.py` 可汇总 1-5 帧 dropout、`png_ttc` 四类拒绝和 paired trend 晋级判据；它只输出 advisory，不改变控制配置。
- **P1 协同诊断接口已闭合**：任意 primary 数的 pair/coalition 漏斗、第二 primary 失败定位、到达窗误差、最近距离、成员间距和 candidate 预筛已进入回归；canonical actual 五层正式报告已闭合，真实 AirSim multi-seed/dropout/candidate 与 pair-funnel 标定仍开放。
- **P1 真实证据扩展**：2026-07-14 actual-v2 seed-1 已证明 identity/state 双重真值隔离并关闭 canonical P0 证据链；迁移前 40 个 SimpleFlight M5N2 episode 的最佳 profile coalition `5/10`、overall `8/40` 仍只作历史基线。下一轮扩展同配置多 seed，并校准第二 primary 的视觉获取/锁定 gate、closing speed/range、延迟和二维/三维机动裕度；trend coast 仅在错误绑定为 0、命令跳变不恶化且 truth-isolated 物理成功不下降时才可晋级默认 profile。
- **P2 optional benchmark 已实现**：独立 API/CLI 已用固定 seed 离线质点场景对照 3D PN、True PN、APN、FRPN 研究近似，输出命中、最小脱靶量、控制努力和耗时；replay 只是可选输入接口，本轮验收证据仅为质点 benchmark，不替换当前二维位置 PN 与 `png_guidance_delivery` VM/TTC 主线。

P2 对照已经以隔离 benchmark 运行，不依赖 P1 物理闭环完成，也不能替代 P1 验收。位置 PN 与 `png_guidance_delivery` 的 VM/TTC 核心公式保持不变；reserve 只有在新版本明确激活并重新通过全部合同与视觉 gate 后才可执行。

fallback commit 合同通过 `D4GuidancePermission` 的可选字段和 duck-typed coercion 接入，不导入 D4 类型。D7 runtime 输出 `coalition_commit_gate_*`、state/epoch/lease、required/acked members、commit plan/coalition versions，并聚合 allowed/reject/state/lease/member counts。D7 已覆盖两个 primary 分别许可、standby reserve、缺 ACK、旧 epoch、过期 lease、重构/中止、D4 pending、D5 incomplete、版本冲突和 k=1 回归；main/D4 已完成 commit-aware 接线及二级、分布式、缺 ACK 故障注入。

通用 N/M topology contract 已补齐并由 main/runtime 接线：`build_cooperative_guidance_topology()` 消费 D3 已排序 resource/target IDs、required counts、coordination mode、primary count，以及统一或按目标的 terminal authorization scope/arrival policy，按需求槽输出 `AssignmentGuidanceBinding`。每目标前 `min(primary_count, required_count)` 个成员为 `primary/wave-0/active`，其余为 `reserve/wave-1/standby`；required=1 自动保持 independent/k=1。显式 per-primary/false 的 active primary 可不提供 arrival window；默认旧调用仍要求 coordinated window。`validate_cooperative_guidance_topology()` 同时检查 policy 与 binding 一致性。helper 不优化分配。

## 当前代码与测试状态

当前 D7 主线已经落地的能力如下：

- **四导引律运行选择合同**：`selector.py` 暴露 `RuntimeGuidanceLaw` 和 `select_runtime_guidance_law(...)`；`D7RuntimePairInput.requested_guidance_law` 支持 `pure_pursuit`、`radar_pn`、`png_vm`、`png_ttc`。前两者为全程模式，后两者为 `radar_pn -> visual PNG` 混合模式。runtime 输出请求律/生效律、law/mode transition、raw gate、terminal timeout 和 command saturation 字段；不改变 `png_guidance_delivery` 核心公式。
- **中段雷达 PN/PNG**：`pn.py` 的 `compute_proportional_navigation_command()` 使用二维位置和速度估计计算 `a_n = N * V_c * lambda_dot`，记录 LOS angle、LOS-rate、closing speed、range、限幅加速度和限幅转向率。`simulator.py` 和 `airsim_dry_run.py` 把上游 GlobalTrack/actor track 等价估计映射为 `GuidanceState(source="global_track" | "airsim_actor_track")`。
- **中段 PN 越目标重捕**：`midcourse_reacquisition.py` 提供每 pair 独立 `MidcourseReacquisitionSelector`。默认连续 2 帧不闭合或越过最近点后 range 回升 `2m` 进入 bounded Pure Pursuit，连续 3 帧 closing `>=1m/s` 后回 PN；PP 转率上限默认 `0.9rad/s` 且不超过调用方上限。metadata 显式记录 selection/reason、entry/recovery streak、overshoot 和 minimum range。经典位置 PN、Pure Pursuit、VM/TTC PNG 公式均未修改。
- **末端视觉 PNG**：`vision_png.py` 的 `SimpleFlightPngGuidanceFilter` 从 bbox 中心计算 bearing/LOS，维护 filtered LOS-rate 窗口；仅 `png_ttc` 增加 delivery 等价 ScaleExpansionTTC 面积 EMA、5 帧斜率、跳变/裁剪/TTC 范围拒绝，runtime 默认 `png_vm` 行为不变。
- **末端短时外推**：`terminal_delivery.py` 已把 delivery 的图像角度/角速度 KF、连续丢帧、短窗口命令平均和 blind push 等价封装为主模块 API。默认 `0.1s` control、`0.25s` KF predict、3 帧丢失、`0.10s` command average、`0.25s` blind push、`tau=0.18s`；所有 KF/blind 输出同时受最后量测后 `0.25s` 硬上限约束。按 resource/global/local track 与 plan owner/version 管理生命周期，输出滤波审计状态。soft innovation prediction 与 `delivery_trend_coast` 均默认关闭，趋势 coast 仅水平且上限 `0.75m/s`。
- **每个 assignment pair 独立导引状态**：`runtime_bus.py` 按 `resource_id -> assigned_global_track_id` 维护独立 `TerminalGuidanceDelivery` 和 latch；image KF、丢帧计数、命令窗口、blind push、LOS/TTC history 均不跨 pair，并在 binding signature、请求律变化或 `reset_pair()` 时重置。
- **runtime bus 状态与 summary 字段**：row/log 新增 `terminal_delivery_state/reason`、measured lock、extrapolation、loss count、prediction age、blind elapsed/decay 和 command sample count；summary 新增 delivery state/reason、外推、重捕与 coast 到期计数，并保留既有 D3/D4/D5、bbox/LOS/TTC、3D benchmark 和 switch/reject 指标。
- **SimpleFlight 控制命令抽象**：D7 输出的是 `PngGuidanceCommand.velocity_ned`，适配 SimpleFlight 高层速度接口。真实 AirSim 控制调用位于 main/runtime 的 `intercept.py`，通过 `command_velocity_z()`/`moveByVelocityZAsync` 下发；D7 模块本身不直接调用 AirSim。
- **D3/D4/D5 gate**：`terminal_gate.py` 校验授权、current/expiry、plan/version、D4 action、D5 `locked`、friend conflict、显式 `execution_gate_pass/safety_gate_pass`、D5 `assigned_global_track_id`/`assignment_version` 和观测 global ID。D4、身份/版本、friend conflict 或 safety gate 失败立即阻断并清空该 pair 外推状态；只有既有 measured lock 的同一 pair 在 D5 明确 `reacquire`、本帧无 observation 且其余合同仍一致时，可进入 bounded coast，不能据此 fresh switch。
- **per-primary terminal scope**：binding 明确 `terminal_authorization_scope="per_primary"` 且 `arrival_coordination_required=false` 时，本 pair 不消费共同 arrival window 或 coalition visual completion 作为切换前置；仍消费本资源 D5 locked、coalition identity/version、D4 permission/commit、friend/duplicate 和 camera/bbox/LOS/maneuver gate。scope 改变属于 binding identity 改变，会重置本 pair 的视觉历史。
- **D4 assist/接管语义**：`request_secondary_assist` 只请求观测 cue，`target_node_id` 是 cue 提供者，不是 assignment owner；该动作不要求 owner 相等或 `takeover_ready`，当前中心 D3 binding/version 继续有效，等待视觉稳定期间继续 radar PN。`request_center_replan`、`degrade_to_secondary`、`degrade_to_distributed`、`reassign` 仍映射为 `d4_reassign_pending`。真正二级接管只认 binding 的显式 `active_plan_owner=secondary`/`secondary_takeover_state`，此时 D4 owner 必须一致且 readiness 必须明确为 `takeover_ready`，否则 fail closed。
- **D4 软风险不过度阻断**：2026-07-07 D4 已将主动降级风险分成硬风险和软风险。`d3_assignment_cost_margin_low`、短时 D5 低置信度、无冲突 `ambiguous/reacquire` 若被 D4 输出为 `continue_center` 或观察类状态，D7 不再把它们当作 `d4_reassign_pending`；后续仍由 D5 locked、D3 current/version 和视觉 gate 决定是否进入 PNG。
- **D5 锁定一致性**：只有 `decision_state="locked"`、无 friend conflict、execution/safety gate 未显式失败、`assigned_global_track_id` 与当前 D3 binding 一致、`assignment_version == track_version` 时才允许 fresh visual PNG；短时 `reacquire` 仅能延续已建立的 bounded coast。D7 不因为本地检测结果更近或更清晰而重绑 `global_track_id`。
- **D3 重规划版本闭环**：当 D4 真的输出 `request_center_replan` 后，main/runtime 会再次调用 D3 产生新的中心 plan/binding/version。D7 只接受当前有效 binding/version；旧 plan、stale binding、revoked assignment 或 D4 `new_plan_id/new_plan_version` 与当前 binding 不一致时必须继续阻断。
- **PN/Pure Pursuit/PNG 对照接口**：`comparison.py` 提供 PN、Pure Pursuit、`png_vm`、`png_ttc` 多 seed report rows 和汇总字段，并补充标准化 runtime law、mode/law transition、raw gate、terminal timeout 和 command saturation 统计，供 D6/main 后续统一报告；该接口不修改 PN/PNG 控制律本体。
- **bbox/LOS 离线 replay 接口**：`replay.py` 将 YOLO/ByteTrack、AirSim detect metadata 等 bbox replay 归一为 `VisionGuidanceObservation`，离线评估合同和 bbox/LOS/TTC gate，显式标记 `vehicle_control=False` 和 `simpleflight_control_called=False`。
- **可选 6D LOS replay**：`los_replay.py` 复用 delivery 的 6D LOS KF 思路；优先接收 D5 `camera_to_ned_rotation`，否则组合 body-to-NED 与 camera-to-body，且两种路径均校验曝光/姿态时间同步。缺旋转或时间字段时显式 unavailable，保持在线 EMA/滑窗为默认，不进入控制授权链。
- **P1 calibration summary helper**：`calibration.py` 的 `summarize_guidance_calibration()` 可消费多 seed D7 runtime outputs、`GuidanceRecord`、comparison rows 或 replay dict，按 PN、Pure Pursuit、`png_vm`、`png_ttc` 汇总 terminal range、closing speed、bbox/LOS/maneuver gate、D4 action block、D5 lock consistency、D3 owner/version consistency、secondary capability/readiness、D5 registration/projection/covariance/Yolo-MOT 摘要和 reject reasons，并输出 versioned threshold advisory。该 helper 只产出报告建议，标记 `advisory_only=True`、`default_control_law_changed=False`、`d3_d4_d5_gate_bypassed=False`，不改变默认控制律。
- **P1 delivery calibration helper**：`delivery_calibration.py` 暴露 `summarize_locked_dropout_matrix()`、`summarize_png_ttc_calibration()` 和 `evaluate_trend_coast_promotion()`；分别检查同身份/同计划的外推时限、四类 TTC 拒绝覆盖以及 paired seed 的错误绑定/命令不连续/物理成功非退化标准。
- **main P1 AirSim calibration sweep 对接状态**：main runtime 已新增 P1 D4/D5 calibration sweep，可按 secondary height/FOV/count/standoff 与多 seed 组合批量运行；sweep 结束后由 D6 自动生成标准报告 bundle，包括 records CSV、summary CSV、summary JSON 和 Markdown。D7 不拥有 sweep 编排或报告写盘，只保持 `D7RuntimeBus`、comparison rows、bbox/LOS replay 和 `summarize_guidance_calibration()` 字段稳定，供 main/D6 消费。
- **执行指标回灌**：main/orchestrator 已把 D7 runtime summary 和真实 AirSim D7 控制执行结果接入 episode bus，并合并进正式 `main_episode_bus_metrics.json`；执行前合同诊断保留为 raw `main_episode_bus_contract_metrics.json`。D7 侧只保证输出可消费字段，不在本模块内计算最终 episode 指标。
- **AirSim P1 回归状态**：controlled 5v5 center replan 已验证 `request_center_replan -> new plan/binding/version -> D7 current binding gate`；2v2 secondary visual PNG gate 已验证 `degrade_to_secondary` 阶段阻断旧锁定，二级 plan/owner/version 生效、D4 readiness/capability 为 `takeover_ready` 且 D5 locked 后才允许 `png_vm`。D7 模块回归另验证中心 owner 与 assist cue 不同不触发 owner/readiness 拒绝。
- **历史基线：2026-07-10 真实 2v2 单 seed**：`p1_gap_closure_2v2_smoke_20260710/episode_006_full_flow` 完成 2/2 `collision_intercept`，时间为 3.4s/3.5s。71 行控制记录中 `guidance_law` 为 `radar_pn=49`、`png_vm=21`、`los=1`，但 `vision_terminal` 只有 4 行且只发生在 INT-01；原始 `terminal_switch_allowed` 只有 2/71。该历史样本只证明当时 radar PN、二级 plan 和保守视觉 gate 可以形成闭环，不能代表当前 M=5/N=2 物理结果。
- **历史基线：2026-07-10 gate 校准**：合同拒绝以 `d5_not_locked=30`、`d4_reassign_pending=18` 为主；视觉拒绝以 `maneuver_margin_low=13`、`bbox_near_image_edge=7`、`los_rate_window_too_short=2` 为主。后续同场景多 seed 必须按 pair 区分 radar PN 成功、实际 `vision_terminal` 驻留和 collision outcome，并核对 aggregate `visual_png_switch_count=3` 与 raw CSV allowed row count=2 的统计定义；只调整切换/gate advisory，不修改 `png_guidance_delivery` 控制律。
- **历史基线：2026-07-10 真实 2v2 10-seed**：`p1_gap_closure_2v2_multiseed_20260710` 覆盖 seeds 1-10，共 20 pairs；18 次 `collision_intercept`、2 次 `terminal_detection_timeout`，D7 pair 级平均最小距离为 2.113m，成功 pair 平均拦截时间为 3.589s。D6 execution episode 聚合给出的平均最小距离为 1.812m；该值与 D7 pair 级均值属于不同聚合口径。该批次仅作历史基线，不能替代 2026-07-13 的 40-episode M5N2 最终证据。
- **历史基线：2026-07-11 四律 SimpleFlight smoke**：`p1_guidance_four_law_smoke_20260711` 在固定 2v2、seed 7、同几何、reset 分隔条件下运行 Pure Pursuit、Radar PN、PNG-VM、PNG-TTC，证明 selector 和 D3/D4/D5 gate 当时已进入 SimpleFlight。每律仅 2 s 且均 timeout；D6 的 21 条是指标配对行，不是 21 个 seed。该 smoke 不支持命中率或导引律优劣结论。
- **2026-07-12 真实 5m 2v2 pilot 复核**：episode 006 为 2/2 collision intercept，但 96 行均未允许 terminal switch；9 行 measured 后的 60 行 `expired` 中 59 行实际原因为 `d4_terminal_inconsistent`，不是 `terminal_visual_lost_after_coast`。真实位置差分显示闭合约 `2.9-4.4m/s`、水平速度约 `6.3-6.9m/s`，而 AirSim state velocity 仅约 `1.5-1.7m/s` 并令 PN CSV 闭合速度为负；该日志不能用于 PNG closing gate 标定。D7 已补 raw required turn/capacity 和 bounded-coast 合同字段；默认 `max_turn_rate=0.9rad/s`、`min_maneuver_margin=0.15` 对该 pilot 的约 `0.78-0.9rad/s` 需求会保守拒绝，先校准状态/相机/能力字段，不直接放宽核心公式。
- **2026-07-12 M5N2 seed1 中段发散证据**：INT-01 在 `min_range=34.13m` 后增至 `143.64m`，INT-04 在 `24.14m` 后增至 `151.04m`，二者仍全程/大部分运行 radar PN。经典 PN 的 closing 变负后横向命令无法提供直接朝向目标的重捕行为，因此新增上述 bounded Pure Pursuit selector；main 仍需在真实 AirSim 多 seed 验证默认 `2/3` 帧迟滞和 `0/1m/s` closing 门限。
- **当前 P1 物理闭环缺口**：2v2 candidate 已以 `20/20` 通过迁移前非退化验收，M5N2 已完成 40 个迁移前真实 SimpleFlight episode，但当前 canonical 只有每场景 1 seed。下一步完成第二 primary、同配置 multi-seed/dropout/candidate、loop latency 和 pair funnel/closing speed/三维机动标定。不得修改 `png_guidance_delivery` 核心算法或绕过合同 gate。
- **D4/D5 机动高空侦察 stress 对 D7 的影响**：2026-07-08 main 侧 5v5 D4/D5 stress 覆盖 3 seeds、200m 高差、`mobile_recon_gimbal`、80deg FOV、1920x1080；D4 action 正确，D5 能识别 mobile recon，gimbal OK rate 为 1.0。但二级网络同帧全覆盖仍为 0.0，降级 case cross-view 为 0，`not_registered` 约 65。因此 D7 不能因为移动侦察节点“看得更清楚”就放行视觉 PNG；仍必须同时满足 D3 当前 version/owner、D4 action 允许、二级 readiness/capability 为 `takeover_ready`、D5 `locked` 且 `assigned_global_track_id` 一致，以及 bbox/LOS/闭合速度/距离/机动能力 gate 通过。`degrade_to_secondary`/`degrade_to_distributed` 阶段若 plan owner/version 尚未进入可执行状态，继续阻断视觉 PNG。
- **切换策略实际状态**：离线二维仿真的 `terminal_switch_range_m` 默认 `250.0m`；AirSim runtime 默认 `intercept_terminal_switch_range_m=8.0m`，可由 CLI 改动；测试中的 `30m` 级相对距离是视觉 gate 回归夹具，不是硬编码策略。bbox 稳定默认至少 2 帧，同时还要求面积、置信度、边缘、视觉延迟、filtered LOS-rate/方差、TTC/闭合速度和机动裕度满足 gate。terminal latch 支持 `terminal_dwell_frames`、`terminal_release_frames` 和 `terminal_reacquire_grace_frames`，用于抑制 D5 locked/reacquire 抖动对视觉 PNG 切换的直接传导。

当前“部分实现”的能力如下：

- AirSim SimpleFlight 真实控制已在 main/runtime 层接入 D7 API，并能输出 `control_commands.csv`、`intercept_summary.json`、D7 runtime summary 和 D6 可消费字段；正式 episode bus metrics 已可合并真实执行结果。2v2 candidate 的 `20/20` 是迁移前非退化证据，不是 soft/trend 收益证明；M5N2 的 40-episode 批次只保留为迁移前历史基线。剩余 P1 是第二 primary、同配置 multi-seed/dropout/candidate、loop latency 以及 pair funnel/closing speed/三维机动标定；3D PN、True PN、APN、FRPN 在线化不属于当前 P1，只保留 P2 隔离 benchmark。
- 相机 `X=0.5m` 前移、`640x480`/`120deg` FOV、`look_at_target` yaw 或 ComputerVision 相机朝向目标已在 AirSim runtime/settings/tests 中接入；D7 主线只消费 bbox 和固定 `focal_length_px` 近似，不直接管理真实相机外参、畸变或姿态估计。
- `png_guidance_delivery` 的 truth/gimbal/strapdown、PX4、MAVLink body-rate、YOLO/ByteTrack 代码作为复现实验资料随 D7 保存；主线抽取 bbox-to-bearing、LOS-rate、TTC/VM 增益、图像角度 KF、短时 command coast 和 SimpleFlight 速度命令这一轻量核。

当前未实现且不应在文档中表述为已接入默认主线的能力：

- 更真实的机动约束，以及在线/default 3D PN、True PN、APN、FRPN、MPC/NMPC。3D PN、True PN、APN、FRPN 的本轮证据仅为隔离式离线质点 benchmark，其中 FRPN 是研究近似；这些 P2 law 不替代默认二维位置 PN 或 `png_guidance_delivery` VM/TTC API。
- 硬件飞控、实机 PX4 Offboard、MAVLink body-rate/attitude 作为默认 main runtime 控制路径。
- YOLO/ByteTrack/真实视觉检测闭环直接控制 D7 主线；现阶段只允许作为 delivery 或 D7 离线 bbox/LOS replay adapter，不直接进入 SimpleFlight 控制。
- D7 本地分配、授权、重分配或 `global_track_id` 改写。

## PNG guidance delivery 学习与融合

已验证的 `png_guidance_delivery` 包含 truth、gimbal、strapdown 三类 AirSim PNG 验证路径。D7 主线只吸收其中对当前 SimpleFlight Blocks 仿真直接有用的算法核：

- bbox 中心到相机 LOS/bearing 的几何转换。
- LOS-rate 低通、滑窗质量评估、方差门限、限幅和尖峰拒绝。
- bbox 面积扩张估计 TTC。
- `LAW=TTC` 的 TTC 增益调度和 `LAW=VM` 的固定 `N * V_m` 思路。
- bbox 太小、贴边、检测不连续、视觉延迟高、机动裕度不足时拒绝切换。

两类 delivery 方案在系统中的融合口径如下：

- **位置比例导引 / truth PNG**：delivery 的 `truth` 路径使用目标真实相对位置和速度验证 PNG 上限。D7 主线不调用 delivery 的 truth 脚本，而是用 `compute_proportional_navigation_command()` 和 AirSim actor/global-track 等价估计实现同一类位置 PN/PNG 几何。实际代码路径是 `d7_proportional_guidance/pn.py`、`simulator.py`、`airsim_dry_run.py`，以及 main/runtime 的 `intercept.py` 中段控制。
- **TTC 捷联比例导引 / strapdown PNG**：delivery 的 `strapdown` 路径把固定相机 bbox 转成 LOS/LOS-rate，并用 bbox 面积扩张估计 TTC。D7 主线不接入它的完整相机姿态、KF、YOLO、body-rate 或 PX4 控制，而是在 `vision_png.py` 中保留轻量 TTC/VM gate：`PngGuidanceConfig(law="png_ttc")` 使用 TTC 增益，`law="png_vm"` 使用固定 `N * V_m` 思路。实际 AirSim controlled intercept 默认 `png_vm`，`png_ttc` 目前主要是 D7 API/复现实验可用能力。
- **文档化状态**：delivery 仍是方案、报告和复现实验包；D7 README/PLAN/GAP 只把其中已抽取到 `vision_png.py` 或 runtime 实际调用的内容列为主线实现。

命名口径：

- 当前 main/runtime 默认目标 actor 和 AirSim detect filter 为 `MSM_TargetActor_*`，实际对象名通常类似 `MSM_TargetActor_1`。
- 当前与 YOLO/视觉 PNG 联调推荐并默认使用 Blocks/AirSim 无人机 mesh asset `Quadrotor1`；main runtime actor asset default 已由 main 同步为 `Quadrotor1`，后续重点是真实 AirSim 验证和阈值/检测调参。
- `png_guidance_delivery` 内仍保留 `Intruder*` mesh filter 和 `IntruderActor` actor name；它们只作为 delivery 复现实验与旧日志的 legacy alias。
- `1M_Cube_Chamfer` 只用于旧接口、旧报告或几何 baseline 复现，需要时显式指定 `--intruder-actor-asset 1M_Cube_Chamfer`。

暂不接入：

- PX4 Offboard、MAVLink、body-rate、attitude 控制。
- YOLO/TensorRT 推理链路。
- 自动 arm/offboard 或任何真实平台控制流程。

主线新增 `SimpleFlightPngGuidanceFilter`，它输出 SimpleFlight 速度命令和 gate 质量字段，不直接调用 AirSim API。

## D3/D4/D5 切换合同

D7 的末端视觉 PNG 入口必须按以下顺序保守判定：

1. D3 binding 必须存在、授权有效、assignment current，且 plan/version/track_version 未过期。
2. D4 action 必须允许末端继续。`continue`、`continue_center`、`request_secondary_assist` 可进入后续检查；后者只请求 cue，既不转移 owner，也不要求 takeover readiness。`request_center_replan`、`degrade_to_secondary`、`degrade_to_distributed`、`reassign` 均表示当前绑定正在重分配或降级，D7 必须记录 `d4_reassign_pending` 并阻断视觉 PNG。
3. 若 D4 提供 `new_plan_id/new_plan_version`，必须与当前 D3 binding 一致，否则拒绝为 `d4_plan_mismatch`。非 assist 动作提供 `target_node_id/new_plan_owner_id/new_owner_node_id/plan_owner_id/owner_node_id` 时，必须与当前 D3 owner 一致；assist 动作的同一字段只作为 cue provider 审计。binding 显式声明 secondary owner 时，还必须有匹配 owner 和 `takeover_ready`；中心 owner、peer fallback 和 cue provider 的角色不得按节点名字猜测。
4. D5 terminal association 必须 `decision_state="locked"`、无 friend conflict，且显式 `execution_gate_pass/safety_gate_pass` 不能为 false；否则立即阻断并清空外推状态，不能本地换目标。
5. D5 的 `assigned_global_track_id` 必须与 D3 binding 的 `assigned_global_track_id` 一致，D5 的 `assignment_version` 必须等于 D3 binding 的 `track_version`；观测 bbox 上携带的 `assigned_global_track_id` 若不一致也必须拒绝。
6. 只有 contract 持续通过后，D7 才评估该 pair 自己的 `TerminalGuidanceDelivery`；本帧无 observation 时才允许已锁定同一 global track 做 bounded KF/coast。到期输出 `expired/terminal_visual_lost_after_coast`，而不是继续命令。

D7 不分配目标、不授权、不创建或改写 `global_track_id`，也不把本地 `local_track_id` 升级为全局身份。

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

末段假设全局航迹切换为更高频的像素/LOS 观测。离线仿真中，D7 的 `vision_terminal` 模式使用合成几何生成 LOS 观测；runtime/gate 路径则消费 D5/AirSim detect 或 replay 归一后的 `VisionGuidanceObservation`：

- `los_angle_rad`：二维视线角。
- `pixel_x`：由焦距和相对方位投影得到的抽象像素横坐标。
- `range_estimate_m`：用于离线闭环的合成距离估计。
- `relative_velocity_source`：记录速度估计来自有限差分还是初始化。

工程重点：

- 模式切换由距离阈值或时间阈值触发，进入末段后锁定 `vision_terminal`。
- D7 只消费 bbox、时间戳、local/global ID 和必要的相机元数据，不拥有真实相机、云台、图像流或 YOLO/ByteTrack 控制闭环。
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

- `GuidanceMode`：`radar_midcourse`、`handover_pending`、`vision_terminal`、`hold`、`reacquire`、`abort_revoke`。
- `GuidanceState`：二维位置、速度、时间戳、来源和可选元数据。
- `GuidanceConfig`：步长、导引律选择 `guidance_law`、PN 系数、加速度限制、转向率限制、末段切换阈值、噪声参数。当前 `guidance_law` 支持 `pn` 和 `pure_pursuit`。
- `GuidanceCommand`：单步 PN 输出，包含 LOS、closing speed、原始/限幅加速度、原始/限幅转向率、期望航向。
- `ThreeDimensionalPnBenchmark`：3D geometry PN 对照字段，包含三维距离、高差、3D LOS-rate norm 和 benchmark-only 标志；不代表默认控制律。
- `GuidanceRecord`：离线 episode 的逐步记录，包含 truth、estimate、observation 和 PN 字段。
- `PngGuidanceConfig`：视觉 PNG gate 参数，包括 bbox、LOS、TTC、机动裕度和导引律。
- `VisionGuidanceObservation`：D5/AirSim detect 提供的 bbox、置信度、local/global ID 和时间戳。
- `VisionGuidanceQuality`：相机质量、LOS 质量、机动裕度和切换拒绝原因。
- `PngGuidanceCommand`：SimpleFlight 速度命令、导引律、饱和状态和 gate 质量。
- `D7RuntimeBus` / `D7RuntimePairInput` / `D7RuntimePairOutput`：D7-owned N-pair runtime state injection 和日志字段输出。该 adapter 不创建 assignment、不调用控制 API，只维护每个 pair 的视觉 filter 状态；输出字段包含 terminal handoff 状态、D3/D4/D5 合同字段、bbox/LOS/TTC gate 质量和 D6 常用 summary 计数。
- `GuidanceStrategyComparisonRow`：PN/Pure Pursuit/`png_vm`/`png_ttc` 对照报告行，包含 D6 可消费的距离、terminal range、closing speed、bbox/LOS/maneuver gate、D4/D5/D3 consistency、secondary capability/readiness、threshold advisory version、切换、合同拒绝和视觉 gate 拒绝字段。
- `GuidanceCalibrationThresholds`：P1 calibration advisory 的版本化阈值容器，字段覆盖 terminal range、min bbox area、max visual latency、closing speed 和 maneuver margin；只用于报告建议，不改变默认导引律。

### 核心函数

- `compute_proportional_navigation_command(...)`
  - 输入：pursuer state、target estimate、`dt_s`、`navigation_constant`、mode 和限制参数。
  - 输出：`GuidanceCommand`。

- `compute_pure_pursuit_command(...)`
  - 输入：pursuer state、target estimate、`dt_s`、mode 和转向率限制参数。
  - 输出：`GuidanceCommand`。
  - 用途：作为 Pure Pursuit baseline 与 PN 对照，也由中段重捕 selector 在有界转率下临时调用；当前为本地轻量实现，不引入 PythonRobotics 依赖。

- `compute_midcourse_reacquisition_command(...)`
  - 输入：每 pair 的 `MidcourseReacquisitionSelector`、pursuer/target state、`dt_s`、PN 参数和限幅。
  - 输出：原 PN 或 bounded Pure Pursuit `GuidanceCommand`，metadata 带 selection/reason 和迟滞状态。
  - 边界：不分配目标；assignment identity/version 改变时由调用方 reset selector；不修改任何导引律核心公式。

- `compute_three_dimensional_pn_benchmark(...)`
  - 输入：相对 NED 三维位置/速度和 `navigation_constant`。
  - 输出：`ThreeDimensionalPnBenchmark`，包含 `range_3d_m`、`height_delta_m`、3D LOS-rate norm 和 3D PN 加速度 norm。
  - 边界：只用于 geometry benchmark/log/advisory，不输出车辆命令，不替换默认二维 PN/PNG API，不绕过 D3/D4/D5 gate。

- `simulate_guidance_episode(...)`
  - 输入：初始 pursuer/target 状态、`GuidanceConfig`、resource/target 标识。
  - 过程：按 `guidance_law` 选择 PN 或 Pure Pursuit；`radar_midcourse` 中段闭环，满足阈值后切换到 `vision_terminal`。
  - 输出：`list[GuidanceRecord]` 和 `summary` 字典。

- `summarize_guidance_records(...)`
  - 输入：records。
  - 输出：初始距离、末距离、最小距离、最近时刻、模式序列、是否进入末段等摘要。

- `SimpleFlightPngGuidanceFilter.evaluate(...)`
  - 输入：`VisionGuidanceObservation`、当前航向/速度、相对位置/速度、SimpleFlight 速度上限。
  - 过程：验证 D5 视觉目标的 bbox 质量、filtered LOS-rate、TTC、闭合速度和机动裕度；输出 raw/filtered LOS-rate、限幅和 outlier reject evidence。
  - 输出：`PngGuidanceCommand`。若 gate 未通过，`terminal_switch_allowed=False`，调用方保持 `handover_pending` 或回退中段 PN。

- `terminal_switch_allowed_rate(...)` / `summarize_terminal_switch_quality(...)`
  - 输入：D7 已生成的 `PngGuidanceCommand`、`VisionGuidanceQuality` 或持久化 metadata 字典。
  - 输出：`terminal_switch_allowed_rate`、样本数、允许数、拒绝数和拒绝原因计数。
  - 边界：只统计已有 gate 输出，不重新实现 D6 指标聚合或 runtime gate 判定。

- `guidance_mode_from_terminal_contract(...)`
  - 输入：D3/D4/D5 terminal PNG contract 判定、handover pending 和 terminal locked 状态。
  - 输出：显式 D7 日志状态。D5 未锁定、版本/身份不一致映射为 `reacquire`；友方冲突、D4 hold 或授权缺失映射为 `hold`；assignment revoked/expired/reassign pending 映射为 `abort_revoke`。

- `D7RuntimeBus.inject_state(...)`
  - 输入：任意长度 assignment pair 状态样本，每个样本包含 D3 binding、D4 permission、D5 terminal association、bbox observation 和当前运动上下文。
  - 输出：每个 pair 的合同/gate/导引日志字段；每个 `resource_id -> assigned_global_track_id` 独立 filter 和 terminal latch，plan/version/owner/assignment 变化时重置。单样本记录包含 `terminal_handoff_state`、`terminal_contract_reject_reason`、`terminal_switch_reject_reason`、dwell/release/reacquire grace flags、D4/D5 state aliases、D4 action block reason、secondary capability/readiness、D5 lock consistency、D3 owner/version consistency、terminal range、closing speed、plan/version、bbox、TTC、raw/filtered LOS-rate、D5 registration/projection/covariance/Yolo-MOT 摘要、3D benchmark 和三类 gate pass。

- `evaluate_bbox_los_replay(...)`
  - 输入：YOLO/ByteTrack、AirSim detect metadata 或其他 bbox replay rows，以及 D3/D4/D5 合同字段。
  - 输出：`D7RuntimePairOutput` 序列和 replay summary；只做离线 gate 分析，不控制 SimpleFlight。

- `run_guidance_strategy_comparison(...)`
  - 输入：seed 列表和策略列表。
  - 输出：PN、Pure Pursuit、`png_vm`、`png_ttc` report rows；用于 D6/main 后续统一统计。

- `summarize_guidance_calibration(...)`
  - 输入：多 seed D7 runtime outputs、`GuidanceRecord`、comparison rows 或 replay dict。
  - 输出：按 guidance law 分组的 terminal range、closing speed、bbox/LOS/maneuver gate、D4 action block、D5 lock consistency、D3 owner/version consistency、secondary capability/readiness、D5 registration/projection/covariance/Yolo-MOT、reject reason 摘要，以及 versioned threshold advisory。
  - 边界：只做 P1 summary/replay calibration，不重跑控制律、不调用 SimpleFlight、不绕过 D3/D4/D5 gate；3D/高度差/FRPN 只进入 benchmark/calibration 字段，不替换默认 PN/PNG API。

## 交付物

- `PLAN.md`：中文工程计划、数学模型、接口说明和边界。
- `README.md`：中文模块说明、运行命令、示例代码。
- `d7_proportional_guidance/models.py`：dataclass 和模式枚举。
- `d7_proportional_guidance/pn.py`：经典二维 PN 计算函数、Pure Pursuit baseline 和 3D geometry PN benchmark helper。
- `d7_proportional_guidance/simulator.py`：单 resource-target pair 离线闭环仿真。
- `d7_proportional_guidance/vision_png.py`：从 delivery 包抽取的 SimpleFlight 兼容视觉 PNG gate。
- `d7_proportional_guidance/runtime_bus.py`：D7-owned N-pair state injection、每 pair filter registry 和日志汇总。
- `d7_proportional_guidance/replay.py`：YOLO/ByteTrack/AirSim bbox replay 到 D7 bbox/LOS gate 的离线 adapter。
- `d7_proportional_guidance/comparison.py`：PN/Pure Pursuit/`png_vm`/`png_ttc` 多 seed 对照 report rows。
- `d7_proportional_guidance/calibration.py`：多 seed D7 runtime/comparison/replay/guidance record summary、versioned threshold advisory 和 3D/FRPN benchmark-only 字段。
- `d7_proportional_guidance/__init__.py`：核心 API 导出。
- `tests/`：pytest 覆盖距离收敛、PN/Pure Pursuit 模式切换、限幅、terminal contract 状态映射、N-pair runtime bus、D4 owner/version gate、terminal latch/reacquire grace、LOS-rate spike filter、3D benchmark log、bbox/LOS replay、comparison report rows、calibration advisory 和记录字段。

## 后续集成建议

主智能体后续可在不改变 D7 内部边界的前提下，把上游分配结果映射为 `GuidanceState`，把 `GuidanceRecord.as_dict()` 写入统一 episode log，并在 GIF 中绘制 pursuer、target、LOS 线、模式颜色和距离曲线。

AirSim runtime 集成要求：

- 当前阶段只使用 SimpleFlight `moveByVelocityZAsync`。
- main runtime 用 `--drone-count N` 决定本次仿真的无人机/目标数量；D7 不读取固定数量，也不假设 2v2/5v5。
- main 必须为每个有效 D3 assignment pair 创建独立 D7 控制上下文，分别运行初段位置 PNG/PN 和末端视觉 PNG gate/filter，不能在多个 pair 之间共享 `SimpleFlightPngGuidanceFilter` 的 LOS/TTC/稳定帧状态。
- 当前 runtime 目标 actor/detection filter 使用 `MSM_TargetActor_*`；main 已将 runtime actor asset default 同步为 `Quadrotor1`，与 YOLO/视觉 PNG 联调默认外观一致；`1M_Cube_Chamfer` 仅保留为旧接口/几何 baseline 复现选项，后续需要真实 AirSim 验证和阈值/检测调参。
- `Intruder*`/`IntruderActor` 只作为 `png_guidance_delivery` 和历史日志的 legacy alias，不应作为新 runtime handoff 的默认目标名。
- 目标检测输入来自 AirSim `simGetDetections` 的 bbox，不依赖默认保存 PNG。
- 进入视觉终端前必须同时满足 D5 locked/版本一致、bbox 质量、LOS 质量、机动裕度和窗口门槛。
- 若 gate 失败，记录 `terminal_switch_reject_reason`，并保持 `handover_pending` 或回退 `radar_midcourse`。

P0/P1 当前状态：

- P0-B 已在 D7-owned API 中补齐：terminal latch 支持 dwell/release/reacquire grace，LOS-rate 输出 raw/filtered 字段并可限幅/拒绝尖峰，近距视觉 PNG 尖峰回归由 D7 测试覆盖；D7 仍不分配、不授权、不改写 `global_track_id`。
- 3D geometry PN 已归入隔离 P2 benchmark/advisory：`compute_three_dimensional_pn_benchmark()` 和 runtime bus log 可输出对照字段；默认二维 PN/PNG 控制律未改变，D3/D4/D5 gate 未绕过。
- D7-owned `runtime_bus.py`、`comparison.py`、`replay.py`、`calibration.py` 已补齐。N-pair runtime bus、PN/Pure Pursuit/`png_vm`/`png_ttc` 多 seed report rows、bbox/LOS replay、多 seed calibration summary/advisory、D4 gate blocking、D3/D4/D5 terminal contract gate、owner/version gate、handoff/guidance summary、bbox/TTC/LOS/gate pass rate、LOS-rate filter、3D benchmark 字段均有 D7 测试覆盖。
- main runtime 已把 D7 runtime summary 接入 episode bus。controlled 5v5 center replan 与 2v2 secondary visual PNG gate 回归已通过，D7 文档不再把这些列为待补能力。
- 2026-07-13 M5N2 已完成 40 个真实 SimpleFlight episode：高威胁目标使用两个 active primary 和一个 standby reserve，不要求同时到达；最佳 profile coalition `5/10`、overall `8/40`。D6 分别记录 contract `35`、control `7`、mode switch `9`、physical `62`，四层不得相互反推。reserve unauthorized、`global_track_id` rewrite、online truth 均为 `0`。
- D4 `request_center_replan`、`degrade_to_secondary`、`degrade_to_distributed`、`reassign` 仍是保守阻断项。`request_secondary_assist` 本身不阻断且不要求 takeover readiness；真正 secondary-owner binding 仍必须通过 owner/readiness。随后只有 D5 `locked`、D3 version 一致及其余安全门控通过，才尝试该 pair 的视觉 PNG。
- mobile recon/gimbal 改善只能作为 D5 观测质量输入，不能绕过 D3/D4/D5 contract 或 bbox/LOS/闭合速度/距离/机动能力 gate；二级网络同帧覆盖不足和降级 cross-view 为 0 时，D7 继续按不可执行 plan owner/version 阻断视觉 PNG。

P1 剩余：

- 保持已通过的 CV 8/10 双 primary 合同验收和未激活 reserve 阻断；不再把 DTO、topology 或合同接线列为未完成项。
- 针对最佳 profile 未达到 `8/10` 的结果，逐 seed 校准第二 primary 的 D5 acquisition/locked/gate，按 terminal range、closing speed、bbox/LOS 和 maneuver margin 分层定位失败；保持 `2 primary + 1 standby reserve` 和非同时到达口径。
- D7 本地 1-5 帧 dropout helper/回归已闭合；main 仍需在真实 AirSim 固定时刻注入，确认 1-2 帧 prediction、超过 0.25s 后 fail-closed 与物理结果一致。
- D7 本地 `png_ttc` 四类拒绝多 seed 汇总 helper 已闭合；仍需单独运行真实 `png_ttc` 多 seed，默认 `png_vm` 不因此改动。
- 受控触发 trend coast；只有错误绑定为 0、命令跳变不恶化、物理成功不下降时，才提出默认 profile 晋级。
- 将 D7 calibration summary 对接到真实 AirSim 多 seed 报告数据源；D7 侧只保证字段稳定和 advisory 输出，正式报告仍由 main/D6 聚合。
- D5 原生 ByteTrack/BoT-SORT admission 未通过，默认继续使用 AirSim detect；YOLO/MOT 只作为离线 replay 或 optional 实验路径，生成 D5 local track 与 D7 bbox/LOS gate 摘要，不进入默认 SimpleFlight controlled intercept。

P2 下一步：

- 3D PN、True PN、APN、FRPN 的离线质点 optional benchmark 已落地，输出逐 seed CSV、JSON、中文 Markdown 和 advisory 对照指标；FRPN 明确标记为研究性增益调度近似，replay 只保留为可选输入接口。
- 后续只扩展离线 scenario/replay 样本与统计，不把 P2 law 注册到默认 runtime，不修改位置 PN 或 `png_guidance_delivery` VM/TTC 核心公式。
- PX4/MAVLink/body-rate、MPC/NMPC 和实机控制继续后置，不属于本轮 P2 benchmark。

## M 对 N 协同导引调研补充（2026-07-11）

文献与开源审计见 `subagent_reviews/D7_M_TO_N_COOPERATIVE_GUIDANCE_REVIEW.md`。后续实现已补齐中心化 coalition 执行门控，但未修改 SimpleFlight 路径或 `png_guidance_delivery` 的位置比例导引/TTC 捷联比例导引核心公式。

`AssignmentGuidanceBinding` 和 runtime bus 现可消费 `coalition_id/version`、`member_role`、`wave_id`、`coordination_mode`、arrival window、activation state、activation plan/track/coalition version 及 terminal authorization scope。默认 coalition scope 对 primary wave-0、reserve/retry 新版本激活、D4/D5/版本一致性、D5 coalition visual completion 和 coordinated 时间窗做完整门控；显式 per-primary scope 只跳过共同视觉完成/到达窗。多个 resource-target pair 可以共享同一个 center-owned `global_track_id`，但 filter/latch 仍按 pair 独立。

合同门控 P1 已完成：D4 replan/degrade/pending、`coalition_fallback_unsupported`、hold/revoke、中心失效且未形成新原子联盟均阻断视觉 PNG；D4 no-change ack 最终映射 `continue_center` 后仍执行 D5 gate。显式 coalition 缺少完整视觉完成证据、support 未满足需求或 plan/track/coalition version 冲突时 fail closed；standby reserve 即使有视觉匹配也不切换，只有新版本显式 activation 后才可重新进入 gate。T001 两个 primary 分别持有独立 filter/latch 并可各自切换，T002 k=1 无 coalition binding 保持回归。row/summary 保留 `terminal_contract_allowed`、`visual_png_switch`、`visual_png_switch_count` 和拒绝原因。

剩余 P1 调研路线：

- 用 point-mass 对照独立 PN、同步 impact-time consensus、序贯 arrival windows 和混合主备。
- 同步方案必须同时研究 terminal sector/impact angle、成员最小间距、命令饱和和 FOV 丢失，不能只比较到达时间误差。
- 序贯/混合的波次和继续条件归 D3/D4；D7 已能跟踪版本化到达窗口并执行成员级 gate，但尚无 impact-time consensus 或协同控制律。
- leader/中心、二级节点和完全分布式模式分别评估时延、间歇通信、成员失联和 consensus 可行性。
- 暂不引入候选仓库：许可证明确的候选只实现单机 ITCG，真正展示齐射/协同的候选缺许可证或工程验证。
