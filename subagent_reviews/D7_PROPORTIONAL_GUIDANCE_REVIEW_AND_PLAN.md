# D7 比例导引架构评审与补充方案

## 2026-07-21 隔离双臂控制血缘评审

评审结论为 D7-owned 接口通过。新增外壳没有进入比例导引、视觉比例导引、LOS
滤波、TTC 或 coast 计算，只在既有三维命令外增加实验 arm、源计划、assignment 和
写回血缘。control 与 treatment 分别拥有独立 controller，不能以同一 pair key 共享
滤波器或模式状态。命令、binding 和完整源计划载荷均有独立 SHA-256，可在 D6 join
前发现字段篡改。

安全门评审为 fail closed。错误 arm、旧版本、同版本不同 hash 和计划载荷 hash 不符
不会返回可写入世界的 batch；D4、resource-track binding 和显式要求的 D5 terminal
gate 不满足时，batch 对应索引为零且记录 `held`。held command 不能生成 application
receipt；非 held command 只能写入 context 指定的 isolation world。receipt 固定声明
simulation-only，并禁止 production runtime ACK 语义。

2026-07-21 专项 9 项和 D7 全量 213 项全部通过；200 pair 规模样本逐对核对状态与
binding hash。该结果证明接口、隔离与篡改检测，
不证明 control/treatment 已产生不同物理结果，也不证明真实 runtime ACK 可用。main
仍需接入克隆世界、多周期计划消费、D7 command publication 和状态窗口；D6 仍需按
完整 hash/provenance 做 availability-aware join。核心公式、参数和
`png_guidance_delivery` 均未修改。

## 2026-07-20 scalable 3D 闭环评审

D7-owned 新增 `scalable_3d_guidance.py` 和
`test_scalable_3d_guidance.py`，没有修改既有二维 `pn.py`、`vision_png.py` 或
`png_guidance_delivery`。新 controller 直接消费 D2 `GlobalTrack3D` 六维 NED 状态/
6x6 协方差、D3 版本化 binding、D4 permission 和 D5 TerminalAssociation；每个
`resource_id/global_track_id` pair 独立保存航迹滤波/外推、LOS KF、TTC、coast 和模式，
按资源索引输出完整 `(resource_count,3)` finite NED 加速度矩阵。

安全评审结论为通过：stale active plan 与 D4 replan/secondary/distributed pending
均输出零命令 hold；D5 non-locked、D5 plan/assignment version mismatch、camera
recognition unavailable、maneuver unavailable 均阻断 fresh visual switch。短时 coast
只允许已有视觉命令的同 pair 在 D5 `reacquire` 且其余合同仍一致时最多 2 帧/0.25s；
controller 不分配、不授权、不改写 `global_track_id`，metadata 明确端到端 RL 未使用。

2026-07-20 新增 14 个确定性测试，D7 全量 `204 passed`，门槛为零失败。覆盖 1、7、
200 pair、实际 D2/D3 DTO、三维高度差、D5 metadata 视觉入口、TTC、dropout、D4/
version/capability 负例，以及 2-resource/1-target 无随机 seed 质点闭环。后者在任一
resource 先进入三维 5 米时通过，另一 resource 仍在阈值外，不要求同时到达。

原“online/default 3D PN 只在 P2 benchmark”的差距已对 scalable point-mass runtime
部分关闭；仍开放的 3D 标定缺口是 main episode-bus 集成、5/20/50/100/200 多 seed
闭环与耗时、world realized acceleration/turn/climb saturation、AirSim/SimpleFlight
姿态推力和控制延迟、相机外参/曝光姿态同步，以及 D6 三维统计。True PN/APN/FRPN、
MPC/NMPC、协同 impact-time/避碰仍未进入默认路径。下文旧状态保留为历史审计。

## 2026-07-15 M5N2 20-case 实测评审

main 已完成 baseline 与 `soft_prediction + trend_coast` candidate 各 10 seeds。M5N2 `20/20` 后 TERM 生效前仅额外完成 `p1_terminal_timing_funnel_10seed_20260715_png_ttc_2v2_seed001`；该单 seed 不纳入本次 M5N2 统计，也不用于分析或候选晋级，其余 tuned case 和全部 dropout 均未执行。两组合计 pair/target/coalition 为 `12/60`、`12/40`、`0/20`。第二 primary 按各 case 的 active membership 动态识别，不固定资源编号，物理结果为 `0/20`。baseline/candidate 第二 primary 最近距离均值分别为 `12.736/12.573 m`，平均改善仅 `0.163 m`。paired active-pair 成功有 6 持平、2 改善、2 退化，逐 seed non-degradation=false。

canonical actual 样本中，baseline contract/control/terminal-switch/mode 分别为 `553/75/75/12`，candidate 为 `499/89/89/12`；前三项是 sample count，mode 是 transition count，不能相互代替。第二 primary 七阶段证据为 `assigned/visible/associated/contract=20/20`、`control/mode=17/20`、physical=`0/20`。20 例最终均是 `collision_stop`，且 collision object 未写盘，因此下一步先补停控/成员间距/持续锁定证据，不盲目放宽 gate，也不能把失败归因于 PN、PNG、LOS 或外推公式。

candidate 的 trend coast 触发=0、soft-specific duration=0，继续 default-off。control tick 外层 3805 样本 mean/P95/max 为 `1069.4/1254.1/2072.5 ms`，全部超过 100 ms；main-bus 内层为 `349.3/487.4/1306.0 ms`，D7 stage 仅 `4.84/5.78 ms` mean/P95。两层不相加，当前性能瓶颈不在 D7 公式本身。online truth identity/state 总计数均为 0，本轮未修改 PN/PNG/LOS/外推核心公式。

## 2026-07-15 诊断实施复核

本批完成下一轮真实 AirSim 所需的 D7 被动证据接口：规范 pair/第二 primary 漏斗、首达时刻、current measured lock 与 historical lock 分离、单帧 dropout reacquisition 时序，以及 `png_ttc` 面积跳变和边界裁剪的受控拒绝矩阵。受控 TTC 用例同时要求 effective control 被阻断、执行律保持 `radar_pn`、D3 binding 的 `global_track_id` 不变，避免把“正确拒绝”误报成视觉控制成功。

2026-07-15 验证为 `190 passed`，阈值零失败；没有新 AirSim episode。下一轮 main 应按同一 live pair 记录逐帧 current/historical measured-lock、dropout scope/loss count、规范漏斗、原始拒绝原因、执行律和 5 米离线物理结果。位置 PN、VM/TTC PNG、LOS 和外推核心公式保持冻结。

## 2026-07-14 actual-execution 真实证据评审

两个 seed-1 required case 已形成可校验 canonical 五层证据，顺序为 contract/control/terminal-switch/mode/physical：tuned 2v2 为 `35/26/26/2/2`，M5N2 为 `67/0/0/0/2`，合计 `102/26/26/2/4`；五层均为 `available`。`terminal_switch_allowed_count` 直接从已写盘 `control_commands` 独立统计，不由 control 层回填。M5N2 active pair `2/3`、第二 primary 最近约 `11.02 m`，target `2/2` 不能替代 coalition `0/1`。D6 确认 availability `2/2`、summary/CSV/canonical physical count 与 plan identity 一致、identity/state online truth 均为 0，因此 P0 证据链关闭。

D6 formal overall fail 是完整 P1 suite 未完成的正确结论；terminal-switch 和 main/D6 canonical 聚合均已闭合。开放 P1 为第二 primary acquisition/5 米闭环、同配置 multi-seed/dropout/candidate、约 `123.3/384.6 ms` loop latency，以及 pair funnel/closing-speed/三维几何和平台机动标定。3D PN、True PN、APN、FRPN 在线化和同时到达不列当前 P1。本次只同步证据，PN、PNG、LOS、外推和上游合同门控均未修改。

## 2026-07-14 配置、候选与实际执行律专项评审

审查结论是 D7 控制逻辑没有把候选视觉律当作实际执行律：`D7RuntimeBus` 在视觉 gate 失败时构造候选 PNG 命令用于质量评估，但输出的 live `guidance_law` 仍为 `radar_pn`，不提供 `selected_velocity_ned`，也不会激活 latch/effective control。为消除外部字段名误读，D7 已新增 `d7_guidance_law_semantics_v1` canonical 合同：配置策略、配置中段/末段律、已计算候选律、实际执行律、视觉控制 active 和实际视觉入口切换分别持久化；termination snapshot 不声明执行律。

回归覆盖 camera/bbox gate 拒绝、有效视觉入口、恶意构造的无授权视觉执行和 termination snapshot。只有 `effective_control_authorized=true`、视觉 latch active 且进入 `vision_terminal` 的 live transition 才有 `executed_visual_mode_switch=true`；普通 `handover_pending/reacquire/hold` mode transition 不能算视觉切换。当前 D7 全量 `188 passed`，语义违规为 0，PN/VM/TTC PNG/LOS/外推和全部 D3/D4/D5 门控未变。

main 的持久化要求是：同一物理执行 state instance 原样保存 `configured_guidance_law`、`candidate_guidance_law`、`executed_guidance_law`、`raw_terminal_gate_allowed`、`latched_visual_mode_active`、`effective_control_authorized` 和 `executed_visual_mode_switch`。`guidance_law` 只能作为 live executed-law 兼容列，`png_guidance_law_candidate` 只能作为 candidate 兼容列；legacy `visual_png_switch` 表示有效视觉控制 sample，不是唯一入口 transition。actual-v2 之前的 postbatch 曾有物理 control 与 episode bus replay 的 plan/state instance 不同；当前 actual-v2 已以 plan identity 一致和独立五层统计关闭 canonical P0。后续 multi-seed 与 pair-funnel 标定继续保持该口径；D7 控制门本身没有 P0。

## 2026-07-14 M5N2 no-switch 专项评审

最新 seed-1 真实输出表明，M5N2 baseline/candidate 均没有 raw terminal gate、terminal latch、effective contract 或 effective control；soft prediction/trend coast 也没有触发。三个 active pair 中，INT-01/INT-04 在约 `35-39 m` collision stop，未到候选约 `30 m` 交接区；INT-02 进入约 `26 m` 后仍以 `d5_not_locked` 和 acquisition timeout 结束。对照组 2v2 `png_ttc` 与 1-frame dropout 仍为 2/2。因此本轮不调整核心导引律，也不将 candidate 无触发解释为非退化收益。

D7 已用 `d7_pair_guidance_funnel_v2` 关闭模块内诊断断点：按 pair 分开报告 handoff range、D5 declared/measured lock、raw gate、camera/LOS/closing-speed/maneuver、latch/effective contract/control，并汇总 first-failure/funnel available/reached。既有闭合速度判定现有显式结果和阈值字段，但公式和阈值未变。当前 `188 passed`，canonical 五层正式聚合也已闭合。开放 P1 是 D5 acquisition、multi-seed/dropout/candidate 以及完整 pair-funnel/closing-speed/三维机动标定；`raw=false` 且 reason 空必须标为 evidence missing，不能在 D7 内猜测。

## 2026-07-14 末端状态/指标语义 P1 关闭

D7 runtime 现以 `d7_terminal_semantics_v2` 明确区分 raw terminal gate、latched visual mode、effective terminal contract、effective control authorization、mode transition 与 termination snapshot。bounded coast 的 raw D5 gate 可以为 false，但 effective contract 只有在 scope=`bounded_coast` 且全部身份/计划/D4/冲突门控仍通过时才为 true；旧 `terminal_contract_allowed` 映射 effective contract，旧 switch/control/visual 字段映射 effective control。termination/abort snapshot 的 live authorization 为 false，终止前状态保存在 `termination_prior_*`，不计入 live transition 或控制分母。

D5 `reacquire` 后 delivery 无命令时新增 `contract_reset`、`prediction_window`、`measured_lock_not_established` 三类审计。coast 继续要求同 resource/global/local identity、current plan/owner/version、D4 允许、无 friend/duplicate/safety 冲突，并要求 prior measured state 和 active latch。2026-07-14 模块全量现为 `188 passed`，验收阈值零失败；main/D6 canonical 五层聚合已经完成，真实 dropout/candidate 与 pair-funnel 标定仍为 P1。位置 PN、VM/TTC PNG、LOS/外推核心公式和 `global_track_id` 均未改变。

## 2026-07-14 truth-state P0 关闭与真实证据边界

main/runtime 已用 D2 estimated target state 替换 SimpleFlight 在线 actor truth state，覆盖默认、主动中心重规划和主动二级接管三条路径；estimate 携带位置、速度、协方差、量测时间和到达时间，缺失或陈旧时 fail closed。主动合同 fixture 只能覆盖 D3/D4/D5 plan/permission/lock，不再携带运动状态或 actor/object/mesh alias。actor truth 仅留在合成传感器和运行后离线 NED 三维 5 米 scorer。AirSim runtime mock 回归为 `130 passed`，D7 PN/PNG 核心公式未修改。

`truth_identity_online_use_count` 与 `truth_state_online_use_count` 是两条独立安全指标。迁移前 2v2/M5N2 的 `online truth=0` 只代表身份真值未用于在线绑定，其物理结果继续作为历史 smoke/离线评分基线。2026-07-14 actual-v2 seed-1 已同时证明两项计数为 0 并关闭 canonical P0 证据链；多 seed 和性能标定仍是 P1。用户已暂缓协同同时到达要求，因此 impact-time consensus 和到达同步不列为当前紧急 P1，当前仍按 per-primary 独立完成和联盟安全合同验收。

## 2026-07-13 M5N2 最终 P1 证据

`cooperative_diagnostics.py` 现按 case/seed 隔离 assignment pair，输出 assigned、active、radar、D5 visible/associated/locked、contract/control/mode、5m physical、closest approach、member separation、first failure、reserve unauthorized 和 owner/version mismatch，并提供 D6 兼容 `rows`。最终批次包含 40 个真实 AirSim SimpleFlight M5N2 episode，高威胁目标采用 `2 primary + 1 standby reserve`；联盟完成只要求同 episode 两个 active primary 分别进入 5m，不要求同时到达。最佳 profile coalition completion 为 `5/10`，全部 profile 合计 `8/40`，未达到 `8/10` 晋级门限。

D6 四层统计为 contract `35`、control `7`、mode switch `9`、physical `62`。四层判定条件和样本口径不同，只能分别解释，不得从 physical 反推 mode/control/contract，也不得用上层计数反推下层执行。迁移前安全审计为 reserve unauthorized `0`、`global_track_id` rewrite `0`、truth identity online use `0`；truth state 当时未单独审计。D7 当前权威全量回归值为 `188 passed`；位置 PN 与 `png_guidance_delivery` 的视觉 PNG、TTC/VM、LOS 滤波和外推核心公式均未修改。

D5 原生 ByteTrack/BoT-SORT admission 未通过，默认检测链继续使用 AirSim `simGetDetections` 经 D5 形成的 bbox/lock 证据。当前开放 P1 聚焦第二 primary、同配置 multi-seed/dropout/candidate、loop latency，以及 pair funnel/closing speed/三维几何和平台机动能力标定；P2 的 3D PN、True PN、APN、FRPN 保持隔离 optional benchmark，不进入默认控制路径。

## 2026-07-13 secondary assist 合同修订

`request_secondary_assist` 已从“二级 plan owner 转移”解释中拆出：该动作只请求观测 cue，`target_node_id` 可以与当前中心 owner 不同，且不要求 `takeover_ready`。当前 D3 binding/version、D5 lock 和安全门控有效时，assist 不阻断视觉 PNG；视觉尚未稳定时 runtime 继续输出 radar PN。真正二级接管只认 D3 binding 的显式 secondary-owner/takeover 元数据，owner mismatch、readiness 非 `takeover_ready` 仍拒绝。`request_center_replan`、未完成二级过渡和 distributed commit 未完成的既有回归保持 fail closed。该子任务完成时的阶段回归为 `175 passed`；当前权威全量值为顶部所列 `188 passed`。未改 `png_guidance_delivery` 的 PN/TTC-PNG/LOS/外推公式和参数。

## 2026-07-12 P1 delivery calibration 增量

D7 已补齐报告型 `delivery_calibration.py`，用于汇总 locked 后 1-5 帧 dropout、`png_ttc` 四类拒绝和 trend coast paired 晋级条件。`TerminalGuidanceDelivery` 的 image KF 与 blind push 现在共同受最后量测后 `0.25s` 硬上限约束；默认 10Hz 下前两帧可使用同 identity/plan 的 image KF，第 3-5 帧 expired/fail-closed。较高频率下 blind push 仍可在该上限内短暂运行。

该结果是 D7-owned 合成矩阵和接口验收，不替代真实 AirSim 多 seed；trend coast 继续默认关闭，只有 paired seeds、candidate 实际触发、wrong binding 为 0、命令不连续不恶化且物理成功不下降全部满足时，helper 才给出晋级建议。位置 PN、Pure Pursuit、`png_vm`、`png_ttc` 核心公式未修改，reserve standby 与 D3/D4/D5 gate 保持不变。

显式 per-primary terminal authorization 已完成：D3 binding 只有同时给出 `terminal_authorization_scope="per_primary"` 与 `arrival_coordination_required=false`，D7 才允许每个 active primary 凭自己的 D5 lock 独立尝试视觉 PNG，不要求其他 primary 同帧锁定或共同 arrival window。该例外不绕过 D4 pending/reconfiguring、fallback ACK/lease/epoch、D3 owner/version、D5 friend/duplicate、camera/bbox/LOS/maneuver；旧合同继续使用原 coalition visual completion gate。该字段已进入 40-episode 真实批次，当前缺口是第二 primary 的视觉性能标定，不是合同接线。

`CooperativeGuidanceTopology` typed API 已同步该合同：两个 policy 参数支持统一值与按目标 mapping，target summary 和 binding 保持一致；per-primary/false active primary 无需 arrival window，reserve 继续 standby。默认调用无行为变化。该修复关闭 SimpleFlight 初始 topology 回落旧 coalition gate 的 D7 侧原因，40-episode 真实批次已验证字段沿 runtime bus 到达 D7。

本轮新增 `cooperative_diagnostics.py`，将 D7 runtime 与 main 物理证据汇总为 assignment-pair/primary/coalition 三层诊断。动态 primary 数、第二 primary 失败阶段、到达离散和 D3 候选参数已可被 main/D6 消费；候选预筛只输出 advisory。合同失效、版本不一致、D4 降级动作、D5 非 locked 和 standby reserve 继续回退 radar PN，专项测试覆盖 area jump、bbox clipping 和 dropout seed 硬边界。

posefix 四组真实 CSV 进一步确认：pair 物理成功为 1/1/0/1，coalition completion 均为 0；`coalition_window_closed`、`coalition_not_activated`、`d4_owner_missing` 的所有样本均禁止视觉 PNG 并回退 radar PN。高频滚动 plan/version 变化此前会重复清空图像滤波和切换迟滞；现仅在同 resource/global target/owner/联盟角色、activation 不变且版本单调前进时保留 history，最新合同仍逐帧重验。w08 的 owner 缺失来自 main sparse fallback binding，D7 不做推断修复。窗口关闭改为继续 radar midcourse，不改变视觉许可结果；大量 D4 inconsistent/D5 non-locked 仍需 main/D4/D5 继续闭合。

## 2026-07-11 历史状态校准

P1 合同层已经闭合：M=5/N=2 ComputerVision 10-seed 达到 8/10 双 primary 合同验收，D4 commit-aware gate 已实现并接入，正确 topology 已接线为 T001 两个 active primary、一个 standby reserve，T002 一个 active primary，第五个资源未分配。ComputerVision 不执行 SimpleFlight 控制，8/10 不能解释为物理命中率。

同 topology 的 SimpleFlight 15 s 诊断共有 30 个 active pair，0 命中，24 个 `terminal_detection_timeout`。这是 40-episode 最终批次之前的历史诊断，只用于解释接线演进，不能作为当前 M5N2 结果。当前 P1 已收敛为第二 primary、同配置 multi-seed/dropout/candidate、loop latency 和 pair funnel/closing speed/三维机动标定。

D7 当时无 P0 blocker，阶段回归基线为 `109 passed`；当前权威全量值为 `188 passed`。P2 的 3D PN、True PN、APN、FRPN 只在隔离式 benchmark 中落地，FRPN 是研究近似，不是规范实现。位置 PN 与 `png_guidance_delivery` VM/TTC 核心公式不改，未激活 reserve 继续阻断，D7 永不本地改写 `global_track_id`。

历史状态保留：较早的 ComputerVision seeds 7/17/27 中，T002 coalition visual consensus 为 4/5/4 帧，每个 seed 产生 2 次 D7 终端合同许可，T001 双 primary 共识为 0。该段仅记录接线演进，不代表当前验证状态。

fallback gate 采用可选字段和 duck typing，不依赖 D4 包：中心失效或 fallback 的 k>1 联盟必须处于 `committed|executing`，lease、epoch、plan/coalition versions 和 required/acked member 集合全部一致。失败原因和 summary counts 已进入 runtime row；commit 通过不替代 D5 visual complete，也不激活 standby reserve。

P2 采用独立模块、独立枚举与独立 CLI，不扩展在线 selector。3D PN 使用 LOS-normal 三维向量近似，True PN 将加速度约束到 interceptor velocity normal plane，APN 加入目标法向加速度前馈；FRPN 仅为 LOS-rate/目标加速度驱动的鲁棒增益调度研究近似。输出指标可做算法筛选，但恒速质点命中不能外推为 AirSim 或实机性能。

D7 提供的通用 `CooperativeGuidanceTopology` 合同已由 main/runtime 接入 SimpleFlight pair 构造：输入规模由数组和 per-target required counts 决定，不使用 `zip(resources, targets)` 的一对一截断。helper 只按 D3 预排序资源展开 slots，输出 primary/reserve、wave 和 activation，并报告未使用资源；pair 生命周期、actor/vehicle 名称映射和 AirSim 控制仍由 main 负责。

**定位**: D7 负责中段雷达/全局航迹比例导引和末端视觉/LOS 导引的算法、状态切换、控制命令抽象与日志记录。  
**边界**: 本文只面向当前 D7 本地研究/合同模块、D7-owned runtime bus 和 AirSim Blocks 仿真闭环，不包含真实平台火控参数、毁伤模型、硬件驱动、自动处置或绕过人工授权的流程。

---

## 0. 当前状态修订

截至当前代码和测试，D7 已经从“离线 PN 研究模块”扩展为可被 main/runtime 消费的导引合同模块，但它仍不拥有 AirSim 启停、episode 编排或真实车辆控制。

已实现：

- 中段雷达/全局航迹 PN：`compute_proportional_navigation_command()` 使用二维位置/速度估计计算 `N * V_c * lambda_dot`，支持限幅和日志字段。
- 末端视觉 PNG：`SimpleFlightPngGuidanceFilter` 使用 bbox center、LOS-rate、bbox 面积 TTC、闭合速度和机动裕度输出 `png_vm/png_ttc/los` 速度命令；runtime 默认 `png_vm`。
- 每个 assignment pair 独立状态：runtime 的 `InterceptPair.visual_filter` 和 D7 filter 实例分别保存稳定帧、LOS-rate 窗口、TTC 面积窗口和 local track 状态；D7 测试覆盖 1/3/5/7 pair。
- D3/D4/D5 gate：D7 校验 assignment 授权/current、plan/version、D4 action、D5 `locked`、friend conflict、D5 `assigned_global_track_id`、D5 `assignment_version` 和观测 global ID。
- D4 保守阻断：`request_center_replan`、`degrade_to_secondary`、`degrade_to_distributed` 均必须拒绝视觉 PNG，记录 `d4_reassign_pending`。
- M-to-N 收敛后门控：D4 no-change ack 最终映射 `continue_center` 后仍需本资源 D5 `locked`、D5 plan/track/coalition version 与 D3 binding 一致、coalition visual completion 及相机/LOS/机动门全部通过；缺失/未完成/冲突分别记录 `coalition_visual_completion_missing`、`coalition_visual_incomplete`、`coalition_visual_conflict`。
- T001/T002 与 reserve：T001 两个 active primary 使用独立 filter/latch，各自满足 gate 后可切换 `png_vm`；T002 k=1 保持兼容。standby reserve 即使已有视觉匹配也不切换，只有新版本显式 activation 且 activation/D4/D5 版本一致后才可进入视觉 gate。
- SimpleFlight 命令：D7 输出 `velocity_ned`，main/runtime 负责 `moveByVelocityZAsync`；D7 本模块不直接连接 AirSim。
- episode bus 指标回灌：2026-07-07 main/runtime 已把真实 D7 执行产物合并进正式 `main_episode_bus_metrics.json`，raw `main_episode_bus_contract_metrics.json` 只保留执行前合同诊断；2026-07-08 复核确认 D7 runtime summary 已接入 episode bus。
- D3 replan 闭环：`request_center_replan` 后 main/runtime 生成新的 D3 plan/binding/version，D7 只接受当前有效 binding/version，旧 plan 或 mismatch 继续阻断视觉 PNG；controlled 5v5 center replan 回归已通过。
- 2v2 secondary gate 回归：`degrade_to_secondary` 阶段阻断旧 D5 lock，二级 plan/owner/version 生效、D4 readiness/capability 为 `takeover_ready` 且 D5 locked 后才允许 `png_vm`/`vision_terminal`。
- D4 软风险口径：低 cost margin、短时 D5 低置信度、无冲突 `ambiguous/reacquire` 若由 D4 输出为 `continue_center`/观察状态，D7 不再误记为 `d4_reassign_pending`；它仍必须等待 D5 `locked` 和视觉 gate 通过。
- D7-owned runtime bus adapter：`D7RuntimeBus` 支持任意 N-pair D3/D4/D5 state injection，每个 pair 独立视觉 filter，plan/version/owner/assignment signature 变化时重置该 pair 状态。
- 四导引律 runtime selector：`RuntimeGuidanceLaw` 和 `D7RuntimePairInput.requested_guidance_law` 已支持 `pure_pursuit`、`radar_pn`、`png_vm`、`png_ttc`。前两者全程运行，后两者中段固定 radar PN，只有 D3/D4/D5 和视觉 gate 通过才切换 VM/TTC；输出 requested/active law、law/mode transition、raw gate、terminal timeout、command saturation。
- Runtime bus 可消费 summary：`D7RuntimePairOutput.as_log_record()` 已输出 terminal handoff、D4/D5 state aliases、D3 plan/version、terminal range、bbox、camera/LOS/maneuver gate、TTC、LOS-rate、closing speed、maneuver margin、D4 action block reason、secondary capability/readiness、D5 lock consistency、D3 owner/version consistency、D5 registration/projection/covariance/Yolo-MOT 摘要；`summarize_runtime_bus_outputs()` 已聚合 guidance mode、handoff 状态、D4/D5/plan 计数、gate pass rate、bbox/TTC/LOS 数值摘要、D5 registration/projection/covariance 摘要、visual PNG switch count 和 reject reason 分布，供 main episode bus 与 D6 报告消费。
- D4 assist/owner/version gate：`request_secondary_assist` 的 `target_node_id/new_plan_owner_id` 只表示 cue provider，不要求与当前中心 owner 相同；非 assist owner 指令仍要求 D3 binding 携带同一 `owner_node_id`。真正 secondary-owner binding 还要求明确 `takeover_ready`。
- P1 对照与 replay 接口：`comparison.py` 输出 PN/Pure Pursuit/`png_vm`/`png_ttc` 多 seed report rows，字段含 terminal range、closing speed、bbox/LOS/maneuver gate、D4 block、D5 lock/D3 owner-version consistency、threshold version 和 visual PNG switch count；`replay.py` 将 YOLO/ByteTrack/AirSim bbox rows 离线映射到 bbox/LOS/TTC gate，并保留 registration/projection/tracker metadata，显式不调用 SimpleFlight。
- P1 calibration summary 接口：`calibration.py` 的 `summarize_guidance_calibration()` 消费多 seed D7 runtime outputs、`GuidanceRecord`、comparison rows 或 replay dict，按 PN、Pure Pursuit、`png_vm`、`png_ttc` 汇总 terminal range、closing speed、bbox/LOS/maneuver gate、D4 action block、D5 lock consistency、D3 owner/version consistency、secondary capability/readiness、D5 registration/projection/covariance/Yolo-MOT 摘要和 reject reasons，并输出 threshold advisory。该接口只产出报告建议，显式不修改默认控制律、不绕过 D3/D4/D5 gate。
- main/D6 P1 calibration sweep 对接：main runtime 已新增 P1 D4/D5 calibration sweep，支持 secondary height/FOV/count/standoff 与多 seed 组合；sweep 完成后 D6 自动生成标准报告 bundle。D7 不拥有 sweep 或报告写盘，只保证 D7 runtime summary、comparison rows、bbox/LOS replay summary 和 threshold advisory 字段可被 main/D6 消费。
- D4/D5 机动高空侦察 stress 结论：2026-07-08 main 侧 5v5 D4/D5 stress 覆盖 3 seeds、200m 高差、`mobile_recon_gimbal`、80deg FOV、1920x1080；D4 action 正确，D5 能识别 mobile recon，gimbal OK rate 为 1.0，但二级网络同帧全覆盖仍为 0.0，降级 case cross-view 为 0，`not_registered` 约 65。D7 不能把“看得更清楚”视为视觉 PNG 放行条件，仍必须坚持 D3 当前 version/owner、D4 action 允许、二级 readiness/capability 为 `takeover_ready`、D5 `locked` 且 `assigned_global_track_id` 一致、bbox/LOS/闭合速度/距离/机动能力 gate 全部通过；`degrade_to_secondary`/`degrade_to_distributed` 阶段 plan owner/version 未进入可执行状态时继续阻断视觉 PNG。
- 历史 2v2 单 seed 执行证据：2026-07-10 `p1_gap_closure_2v2_smoke_20260710/episode_006_full_flow` 完成 2/2 assigned-target `collision_intercept`，用时 3.4s/3.5s。71 行命令记录包含 `radar_pn=49`、`png_vm=21`、`los=1`，但只有 INT-01 出现 4 帧 `vision_terminal`，raw switch allowed 仅 2/71。该证据支持当时 2v2 闭环可成功，不支持视觉 PNG 已稳定接管。
- 历史 2v2 10-seed 执行证据：`p1_gap_closure_2v2_multiseed_20260710` 共 20 pairs，18 次 assigned-target `collision_intercept`、2 次 INT-02 `terminal_detection_timeout`（seed 3/10）。D7 pair 级平均最小距离为 2.113m，D6 execution episode 聚合平均最小距离为 1.812m。该历史基线不等同于当前 M=5/N=2 物理结果。
- 历史四律 SimpleFlight smoke 证据：`p1_guidance_four_law_smoke_20260711` 固定 2v2、seed 7、同几何并用 reset 分隔各律，四律均运行 2 s 且均 timeout。该证据只确认 selector 和 gate 当时已进入 SimpleFlight，不支持命中率或导引律优劣结论。
- P0 状态：无 P0 blocker；main/runtime 的状态真值输入断链已由代码/mock 回归关闭，2026-07-14 actual-v2 seed-1 又关闭 canonical 真实执行证据链。D7 继续不分配、不授权、不改写 `global_track_id`；多 seed 和性能标定仍是 P1。

部分实现：

- AirSim SimpleFlight 真实控制已在 main/runtime 层接入 D7，正式 episode bus metrics 已能合并真实执行结果；M5N2 已完成 40 个真实 episode，最佳 profile `5/10`、overall `8/40`。剩余 P1 风险集中在第二 primary acquisition/gate、closing speed/range、二维/三维几何和平台机动标定，以及较长时长/多 seed 四律对照。3D/True PN/APN/FRPN 只属于 P2 隔离 benchmark。
- 相机前移 `0.5m`、`120deg` FOV 和 `look_at_target`/CV look-at 已在 runtime/settings/tests 中接入；D7 主线只消费 bbox 和固定焦距近似，不管理真实相机外参。
- `png_guidance_delivery` 的 truth/gimbal/strapdown、PX4/MAVLink/body-rate、YOLO/ByteTrack 是方案和复现实验包；主线只抽取轻量 gate 与 SimpleFlight 速度命令。

未实现：

- 更真实机动约束、在线/default 3D PN、True PN、APN、FRPN、MPC/NMPC；3D PN/True PN/APN/FRPN 仅有隔离 P2 benchmark，FRPN 为研究近似。
- 硬件飞控、实机 PX4 Offboard、MAVLink body-rate/attitude 默认主线。
- 原生 ByteTrack/BoT-SORT 未通过 D5 admission，不能直接进入闭环控制；D7 只提供 bbox/LOS 离线 replay adapter，默认在线检测保持 AirSim detect，后续 MOT 仍为 optional。

---

## 1. 目标与边界

D7 的目标是作为 D1-D7 主流程中的导引合同层，在 D3/D4/D5 合同通过后输出 PN/PNG guidance records，使系统从版本化分配结果进入可评估的中段/末端闭环。它只做比例导引及其改进型导引律，不负责上游态势生成或身份判断。

D7 负责：

- 基于 `GlobalTrack` 或雷达/全局航迹估计计算 `radar_midcourse` 比例导引。
- 基于 D5 已锁定的末端视觉目标计算 `vision_terminal` 视觉 PN 或 LOS 追踪。
- 维护导引阶段状态机：`launch/takeoff -> radar_midcourse -> handover_pending -> vision_terminal -> hit/abort`。
- 输出 `GuidanceRecord` 和 D7 gate/command metadata；AirSim runtime 负责写出 `control_commands.csv` 和 episode summary，供 D6 统计。
- 记录 LOS、LOS-rate、闭合速度、导航比、限幅加速度、限幅转向率、最小距离、碰撞对象和终端检测超时等字段。

D7 不负责：

- D1 传感器融合和多源状态估计。
- D2 数据关联、`global_track_id` 维护、ID Switch 处理。
- D3 资源-目标分配、重分配、迟滞和计划授权。
- D5 末端身份认证、视觉局部轨迹到全局航迹的绑定。
- D6 指标判分、报告聚合和离线统计口径。

核心约束：D7 的导引目标必须来自上游已经确认的 `assigned_global_track_id`。中段和末端必须继承同一个分配目标；D7 不得因为末端看到其他更近目标而自行换绑。

---

## 2. 当前实现评审

当前 D7 集成状态分为三层：D7 本地算法/合同模块、D7-owned runtime bus adapter，以及 main/runtime 消费 D7 API 的 AirSim controlled intercept。D7 只拥有前两层；AirSim 启停、episode 编排、SimpleFlight 调用和报告写盘仍由 main/runtime 负责。

D7 本地算法/合同模块：

```text
research_modules/d7_proportional_guidance/
  d7_proportional_guidance/models.py
  d7_proportional_guidance/pn.py
  d7_proportional_guidance/simulator.py
  d7_proportional_guidance/airsim_dry_run.py
  d7_proportional_guidance/terminal_gate.py
  d7_proportional_guidance/vision_png.py
```

该模块已经提供 `GuidanceState`、`GuidanceConfig`、`GuidanceCommand`、`GuidanceRecord`、`compute_proportional_navigation_command()`、`simulate_guidance_episode()`、`evaluate_terminal_png_contract()` 和 `SimpleFlightPngGuidanceFilter`。它记录 `range_m`、`los_angle_rad`、`los_rate_radps`、`closing_speed_mps`、PN 限幅、D3/D4/D5 contract、bbox/LOS/TTC gate 和 mode/handoff 字段。

D7-owned runtime bus adapter：

```text
research_modules/d7_proportional_guidance/
  d7_proportional_guidance/runtime_bus.py
  d7_proportional_guidance/comparison.py
  d7_proportional_guidance/replay.py
  d7_proportional_guidance/calibration.py
```

该层让调用方注入任意长度 assignment pair 的 D3 binding、D4 permission、D5 terminal association 和 bbox observation；D7 为每个 `resource_id -> assigned_global_track_id` 独立维护视觉 filter，输出 main/D6 可消费的 gate、handoff、reject reason、guidance law、summary 和 calibration advisory 字段。它不创建 assignment、不授权、不控制车辆，也不假设 2v2 或 5v5。

AirSim controlled intercept 的 runtime consumer：

```text
research_modules/airsim_runtime/intercept.py
```

该实现中，拦截无人机使用 SimpleFlight，多旋翼控制接口由 main 显式启用、解锁、起飞并发送 `moveByVelocityZAsync` 速度/高度命令。目标不是 AirSim 车辆，不使用 SimpleFlight，而是非车辆 Unreal actor，由 main 通过 `simSetObjectPose` 按水平速度移动。目标识别使用 AirSim `simGetDetections` 检测框。2v2 和 5v5 只作为 baseline/回归场景；实际仿真规模由 main runtime 的 `--drone-count N` 决定。

数量边界需要和 baseline 区分：D7 不应假设 2v2 或 5v5；main 应为 D3 输出的每个有效 assignment pair 创建独立 D7 控制上下文，分别持有 D3 binding、D4 permission、D5 locked evidence、初段位置 PNG/PN 记录状态和末端视觉 PNG filter。

当前 Blocks 稳定闭环采用：

- 中段：只使用 episode bus 发布的 D2 estimated global track state 调用 D7 PN，输出二维期望航向和速度命令；在线控制不得读取 actor truth state。
- 末端：进入 terminal handoff 后先过 D3/D4/D5 contract；contract 通过后调用该 pair 自己的 `SimpleFlightPngGuidanceFilter`，若 bbox/LOS/TTC/机动 gate 通过则进入 `vision_terminal` 并使用 `png_vm`/`png_ttc` 速度命令；未通过时保持中段 PN 或保守 LOS heading。
- 在线停止条件：D2 estimate 的三维距离进入 5 米时记录 `estimated_range_stop`；它不是物理命中评分。
- 离线成功判据：episode 结束后由 D6/offline scorer 使用 actor truth pairing 计算 NED 三维 5 米结果；该结果不反馈在线控制。碰撞对象名只可作离线诊断，不得用于在线目标身份或状态选择。
- 失败判据：资源/目标缺失、末端检测超时、异常高度、episode 超时等。

新增融合：用户已提供并多轮测试过的 `png_guidance_delivery` 已作为 D7 的算法来源进入主线。当前主线没有直接调用其中的 PX4/MAVLink/YOLO 示例，而是抽取为 `SimpleFlightPngGuidanceFilter`：

- `VisionGuidanceObservation`：承接 D5/AirSim detect 的 bbox、置信度、local/global ID 和时间戳。
- `PngGuidanceConfig`：配置 `los`、`png_ttc`、`png_vm` 三类末端导引/保底律。
- `VisionGuidanceQuality`：输出 bbox 质量、LOS 质量、机动裕度、TTC、拒绝原因。
- `PngGuidanceCommand`：输出 SimpleFlight 可用的水平速度命令和导引日志字段。

主线明确不接入 delivery 包中的 PX4 Offboard、MAVLink body-rate、attitude 控制、YOLO/TensorRT 和真实平台安全流程。当前仿真仍使用 SimpleFlight `moveByVelocityZAsync`，目标检测来自 AirSim `simGetDetections`。

需要明确的限制：

- 当前 AirSim 末端已实际消费视觉 gate 和 `png_vm` 速度命令；`png_ttc` 在 D7 API 和 delivery 中可用，但不是 runtime 默认导引律。
- 严格像素 `center_px -> bearing -> bearing_rate -> visual PN` 已以轻量形式接入 D7 gate；更复杂的 strapdown body-rate、YOLO、KF、TTC relaxed baseline 保留为 delivery 参考，不进主线。
- AirSim 默认不保存相机 PNG，只保留检测框、相机/图像元数据、D5 所需的本地视觉观测字段和拦截控制日志；`--save-images` 只用于调试。
- 碰撞不能只看 `has_collided=True`。只有 `collision_object_name` 包含 assigned actor name 或 assigned object id 时，才算 `collision_intercept`；撞地、撞障碍、撞其他目标都不能记为成功。
- 正式 main bus metrics 应看执行后合并口径；raw contract metrics 可用于诊断 D3/D4/D5 gate，但不能单独代表真实拦截执行结果。
- D7 本地 `D7RuntimeBus`、comparison rows、bbox/LOS replay adapter 和 calibration summary helper 只提供可消费的 gate/report/advisory 字段；本轮已补齐 handoff/guidance summary、gate pass rate、bbox/TTC/LOS 摘要、D4 action block、secondary readiness、D5 lock/D3 owner-version consistency、D5 registration/projection/covariance/Yolo-MOT 摘要、threshold advisory 和 3D/FRPN benchmark-only 字段。真实 AirSim 40-episode 数据和 D6 正式报告已经形成；原生 MOT replay/准入仍由 main/D5/D6 作为 optional 路径集成。

---

## 3. 算法原理

### 3.1 中段雷达比例导引

中段输入来自 D1/D2 输出的 `GlobalTrack` 或等价雷达/全局航迹估计，再由 D3/D4 的分配结果限定目标 ID。D7 只需要以下状态：

```text
pursuer:
- resource_id
- timestamp_s
- position_m / position_ned
- velocity_mps / velocity_ned

target estimate:
- assigned_global_track_id
- timestamp_s / valid_at
- position_m / position_ned
- velocity_mps / velocity_ned
- covariance_trace
- source: global_track | radar_track | airsim_actor_track
```

二维相对状态定义为：

```text
r = target_position - pursuer_position
v = target_velocity - pursuer_velocity
R = ||r||
lambda = atan2(r_y, r_x)
lambda_dot = cross2(r, v) / R^2
V_c = -dot(r, v) / R
```

其中：

- `lambda` 是 LOS angle。
- `lambda_dot` 是 LOS-rate，表示视线角速度。
- `V_c` 是 closing speed，目标距离缩小时为正。
- `N` 是导航比，当前默认 `3.0`，可在离线实验中扫参。

经典 PN 横向加速度：

```text
a_n = N * V_c * lambda_dot
```

D7 输出前需要进行工程限幅：

```text
a_limited = clip(a_n, -max_lateral_accel, max_lateral_accel)
omega = a_limited / pursuer_speed
omega_limited = clip(omega, -max_turn_rate, max_turn_rate)
desired_heading = current_heading + omega_limited * dt
```

离线模块记录加速度和转向率；AirSim 运行时把 `desired_heading` 转为水平速度命令：

```text
command_vx_mps = intercept_speed_mps * cos(desired_heading)
command_vy_mps = intercept_speed_mps * sin(desired_heading)
command_z_ned_m = intercept_altitude_ned_z
```

这仍是仿真控制抽象，不是可直接迁移到真实平台的飞控接口。

### 3.2 改进 PN 的扩展点

当前代码实现经典 PN。后续可在同一接口下增加改进型 PN，但必须保持输入输出和日志字段兼容：

- `biased_pn`: 在末端给 LOS 收敛方向增加小偏置，用于离线比较末端可见性。
- `augmented_pn`: 在 target acceleration estimate 可用时加入目标机动补偿项。
- `true_pn`: 使用惯性 LOS-rate 与闭合速度的标准形式。
- `pure_pursuit_fallback`: 当 `V_c <= 0`、速度过小或 LOS-rate 数值不稳定时退化到追踪 LOS heading。

改进 PN 只改变 `commanded_lateral_accel_mps2` 的生成方式，不改变目标来源和授权边界。

### 3.3 末端视觉 PN / LOS 导引

末端触发条件必须来自 D5 的 `TerminalAssociation`，而不是 D7 自己识别图像目标。推荐触发链路：

```text
D3 AssignmentPlan
-> assigned_global_track_id
-> D5 TerminalAssociation(decision_state="locked")
-> association.assigned_global_track_id == assignment.assigned_global_track_id
-> D7 enters vision_terminal
```

末端视觉输入建议包含：

```text
TerminalAssociation:
- assigned_global_track_id
- local_track_id
- decision_state: locked | ambiguous | hold | reacquire
- association_confidence
- assignment_version
- plan_id / plan_version

LocalVisualTrack / AirSimDetectionBox:
- camera_id
- bbox_xyxy
- center_px
- timestamp
- detection_score / quality
- object_id / airsim_detection_name
- mot_history_length
```

当前 Blocks 控制实现中，进入 terminal handoff 后先构造 `VisionGuidanceObservation`，再由 D7 gate 将检测框中心转换为相机视线角。若 contract 和 gate 通过，runtime 使用 `PngGuidanceCommand.velocity_ned`；若未锁定或 gate 失败，则继续中段 PN 或保守 LOS heading。核心像素链路为：

```text
relative_bearing = atan((center_px.x - cx) / fx)
los_angle = vehicle_heading + relative_bearing
los_rate = finite_difference(los_angle, dt)
a_n = N * V_c_estimate * los_rate
```

如果缺少可靠距离或闭合速度，末端仍采用两级策略：

1. `vision_los_tracking`: 只用像素中心偏差/LOS heading 做稳定追踪。
2. `vision_png`: 在 D3/D4/D5 contract 通过，检测连续、时间戳稳定、像素 LOS-rate、TTC/闭合速度和机动裕度可靠后启用 `png_vm` 或 `png_ttc`。

---

## 4. 阶段切换状态机

推荐 D7 状态机如下：

```text
launch/takeoff
  -> radar_midcourse
  -> handover_pending
  -> vision_terminal
  -> hit

任一阶段
  -> abort
```

### 4.1 `launch/takeoff`

入口：

- D3/D4 提供有效 `AssignmentPlan`。
- `resource_id`、`vehicle_name`、`assigned_global_track_id` 可解析。
- AirSim 控制 episode 中 SimpleFlight API control 已启用、已 arm、已 takeoff，并移动到 `intercept_altitude_ned_z`。

出口到 `radar_midcourse`：

- 资源状态可用。
- D2 estimated `GlobalTrack` 可用且未陈旧；actor truth estimate 不得进入在线控制。
- 当前计划版本未过期。

失败到 `abort`：

- 起飞失败、API control 不可用、资源缺失、计划未授权或版本不匹配。

### 4.2 `radar_midcourse`

入口：

- 有 assigned target 的全局航迹估计。
- D5 尚未输出稳定 `locked`，或目标未进入终端距离窗口。

行为：

- 使用 `GlobalTrack`/actor track 计算 PN。
- 输出限幅后的水平速度/航向命令。
- 记录 `range_m`、`los_rate_radps`、`closing_speed_mps`、`mode="radar_midcourse"`。

出口到 `handover_pending`：

- `range_m <= terminal_switch_range_m`，或 terminal handoff 时间/视场条件满足。

失败到 `abort`：

- assigned target 丢失超过阈值。
- `GlobalTrack` stale 或 covariance 发散到不可用。
- D3/D4 撤销当前分配。

### 4.3 `handover_pending`

入口：

- 已进入末端距离窗口。
- D7 请求 D5 对同一 `assigned_global_track_id` 做终端确认。

行为：

- 保持中段 PN 或低增益 LOS 追踪。
- 等待 D5 `TerminalAssociation.decision_state`。
- 记录 terminal handoff latency 和检测可见性。

出口到 `vision_terminal`：

- D5 返回 `locked`。
- `TerminalAssociation.assigned_global_track_id == AssignmentPlan.assigned_global_track_id`。
- `assignment_version` 或 `plan_version` 匹配当前计划。

保持或回退：

- D5 返回 `hold` 或 `ambiguous` 时，保持 `handover_pending` 或回到 `radar_midcourse`。
- D5 返回 `reacquire` 时，继续按上游航迹导引并请求重新捕获。

失败到 `abort`：

- 末端窗口内持续未检测到 assigned target。
- `terminal_detection_timeout_s` 超时。
- D5 明确报告 friend conflict 或 assigned target mismatch。

### 4.4 `vision_terminal`

入口：

- D5 对 assigned target 输出 `locked`。
- AirSim 当前实现中 `pair.terminal_locked=True`。

行为：

- 当前 Blocks runtime 在 gate 通过时采用 `SimpleFlightPngGuidanceFilter` 输出的视觉 PNG 速度命令，默认 `guidance_law=png_vm`。
- 若视觉 gate 暂未通过但仍处于 handoff，保持中段 PN 或保守 LOS heading，不把失败归因为目标重绑。
- 继续检查 assigned target 检测是否存在；短时丢失可用 `last_detection_s` 保持，但超过阈值必须 abort。

出口到 `hit`：

- `range_m <= intercept_radius_m`。
- 或 AirSim collision object name 匹配 assigned actor/object name。

失败到 `abort`：

- 检测超时。
- 碰撞对象不是 assigned actor/object。
- 撞地、异常高度、撞障碍、撞其他目标。
- D5 锁定丢失且无法在窗口内恢复。

### 4.5 `hit` / `abort`

`hit` 只表示仿真 episode 的闭环成功事件，推荐细分：

- `range_intercept`: 最近距离达到阈值。
- `collision_intercept`: AirSim 碰撞对象名匹配 assigned target。

`abort` 必须记录原因：

- `resource_missing`
- `target_missing`
- `terminal_detection_timeout`
- `below_ground_or_invalid_altitude`
- `assignment_revoked`
- `terminal_identity_mismatch`
- `timeout`

---

## 5. 与其他模块接口

### 5.1 D1/D2 `GlobalTrack`

D7 中段消费 D1/D2 的航迹状态，但不修改航迹：

```text
GlobalTrack / CanonicalTrack
- global_track_id
- position_ned: [x, y, z]
- velocity_ned: [vx, vy, vz]
- covariance / covariance_trace
- valid_at / timestamp
- track_version
- lifecycle_state / quality_state
```

二维 D7 只使用水平 `x/y/vx/vy`；高度由 AirSim 控制参数保持，例如 `intercept_altitude_ned_z`。如果后续扩展三维 PN，应新增独立模式并保留二维字段兼容。

### 5.2 D3 `AssignmentPlan`

D7 启动导引前必须读取版本化分配：

```text
AssignmentPlan
- plan_id
- version
- created_at
- human_authorization_state
- assignments[]

Assignment
- resource_id
- target_id / assigned_global_track_id
- cost_breakdown
- feasibility_state
```

建议给 D7 的最小绑定 DTO：

```text
AssignmentGuidanceBinding
- resource_id
- vehicle_name
- assigned_global_track_id
- plan_id
- plan_version
- track_version
- assignment_validity_state
- authorization_state
```

若计划版本过期、分配被撤销或资源被重分配，D7 必须停止当前导引并输出 `abort` 或 `hold`，不能继续沿旧目标闭环。

### 5.3 D5 `TerminalAssociation`

D5 是末端进入视觉导引的门控模块。D7 只接受如下保守状态：

```text
TerminalAssociation
- assigned_global_track_id
- local_track_id
- decision_state
- association_confidence
- ambiguity_score
- friend_conflict_state
- assignment_version
```

处理规则：

- `locked`: 若 ID 和版本匹配，进入或保持 `vision_terminal`。
- `hold`: 不切换目标；保持 handover 或低增益中段。
- `ambiguous`: 不使用视觉导引；继续等待或请求 D3/D4 仲裁。
- `reacquire`: 保持 assigned ID，尝试重新进入 D5 末端确认。
- `friend_conflict_state != none`: 立即停止末端导引并记录安全事件。

### 5.4 D6 指标日志

D7 不计算最终指标，只输出 D6 可消费日志。推荐统一记录：

```text
GuidanceRecord
- timestamp_s
- resource_id
- assigned_global_track_id / target_id
- mode
- range_m
- los_angle_rad
- los_rate_radps
- closing_speed_mps
- commanded_lateral_accel_mps2
- limited_lateral_accel_mps2
- limited_turn_rate_radps
- mode_switch
- observation.source

InterceptCommandRecord
- timestamp_s
- resource_id
- vehicle_name
- target_id
- mode
- range_m
- command_vx_mps
- command_vy_mps
- command_z_ned_m
- terminal_locked
- detection_seen
- collision_seen
- collision_object_name
- status
- abort_reason
```

D6 可从这些记录聚合 `time_to_intercept_s`、`min_range_m`、`guidance_mode_switch_count`、`terminal_mode_entry_rate`、`collision_object_name`、`terminal_detection_timeout_count` 等指标。

---

## 6. AirSim 当前实现与限制

### 6.1 控制链路

AirSim 受控拦截链路：

```text
Blocks launch/reset
-> prepare_interceptor_control()
-> enableApiControl / armDisarm / takeoffAsync / moveToZAsync
-> sample_frame()
-> D7 PN / LOS heading command
-> moveByVelocityZAsync(vx, vy, z, duration, vehicle_name)
-> collision/range/detection timeout check
-> hover / land / release
```

拦截无人机是 SimpleFlight 多旋翼；目标 actor 不是车辆。这样避免目标机也受到 SimpleFlight 飞控和碰撞物理的额外状态影响，便于主流程精确设置 2v2 水平穿越 baseline 目标。该 baseline 不能扩展为 main runtime 的固定数量假设；N-pair 控制必须由 main 按 `--drone-count` 和有效 assignment pair 显式创建 D7 上下文。

### 6.2 目标 actor 与检测

目标配置来自 `BlocksActorTargetSpec`：

```text
- object_id: TGT-001 ... TGT-N
- actor_name: MSM_TargetActor_1 ... MSM_TargetActor_N
- start_ned
- velocity_ned
- asset_name
- fallback_actor_name
```

当前与 YOLO/视觉 PNG 联调推荐并默认使用 Blocks/AirSim 无人机 mesh asset `Quadrotor1`；main runtime actor asset default 已由 main 同步为 `Quadrotor1`，后续重点是真实 AirSim 验证和阈值/检测调参。`1M_Cube_Chamfer` 只保留给旧接口、旧报告和几何 baseline 复现。D7 delivery 脚本的 `Intruder*`/`IntruderActor` 仍是 legacy alias，不应成为新 runtime handoff 的默认目标命名。

每个采样时刻由 `position_at(timestamp)` 得到目标位置，再通过 `simSetObjectPose` 更新 actor。检测链路通过：

```text
simClearDetectionMeshNames
simSetDetectionFilterRadius
simAddDetectionFilterMeshName
simGetDetections
```

把 AirSim 内置检测框转换为 `AirSimDetectionBox` / D5 `LocalVisualTrack`，保留：

- `object_id`
- `camera_id`
- `bbox_xyxy`
- `center_px`
- `classification_hint`
- `confidence`
- `mot_history_length`
- `airsim_detection_name`

默认不保存 PNG，不影响 D5/D6，因为检测框、相机元数据、目标 actor 名和时间戳已经足够支撑当前评估。

### 6.3 当前限制

当前实现适合作为 Blocks 第一阶段稳定闭环：

- 2v2/5v5 只作为 baseline 场景；main runtime N-pair 执行时应按 `--drone-count N` 和每个有效 assignment pair 独立发命令、记日志和维护 D7 filter。
- 中段 PN 使用二维 NED 平面。
- 末端使用 D5 locked 和 D3/D4/D5 contract 允许后的 D7 视觉 PNG gate；gate 通过时使用 `png_vm`/`png_ttc` 速度命令，未通过时保持保守 PN/LOS。
- 成功严格绑定 assigned target 的 range 或 collision object。

限制和下一步：

- 轻量像素 LOS-rate visual PNG 已接入，真实 AirSim 多 seed 批次已经运行；剩余重点是第二 primary acquisition/gate、距离/闭合速度估计口径、三维/机动标定和长期 D5 事件流。
- `simGetDetections` 是 AirSim 内置检测，不等价于真实视觉模型。
- 当前 actor 目标速度简单，适合验证接口和状态机；复杂机动应在后续离线批量实验中加入。
- `collision_intercept` 对 Blocks 物理和 actor mesh 有依赖，因此必须同时保留 `range_intercept` 作为可复现补充判据。
- 控制命令是 `moveByVelocityZAsync` 高层速度接口，不代表底层姿态、推力或真实飞控。

---

## 7. 测试与指标方案

### 7.1 单元测试

离线 D7 已覆盖：

- PN 能降低距离。
- `terminal_switch_range_m` 能触发 `vision_terminal`。
- 加速度和转向率限幅生效。
- `GuidanceRecord` 包含几何字段。
- AirSim dry-run adapter 输出 `radar_midcourse` 和 `vision_terminal` 记录。

建议新增或保持的测试：

- `closing_speed_mps <= 0` 时不产生发散命令，回退到 LOS heading 或限幅命令。
- `range_m` 接近 0 时 LOS-rate 数值稳定。
- `assigned_global_track_id` 不匹配时禁止进入 `vision_terminal`。
- D5 `ambiguous/hold/reacquire` 不会导致 D7 换绑目标。

### 7.2 AirSim actor baseline 与 N-pair 测试

受控 2v2 episode 应验证：

- `default_2v2_actor_target_specs()` 生成两个 actor target。
- actor 使用 `simSetObjectPose` 移动，目标不在 `target_vehicle_names` 中作为 SimpleFlight 车辆出现。
- 两架拦截无人机调用 `enableApiControl`、`armDisarm`、`takeoffAsync`、`moveToZAsync`、`moveByVelocityZAsync`。
- `simGetDetections` 能返回 assigned actor 的 bbox。
- `control_commands.csv` 和 `intercept_summary.json` 写出。
- 未指定 `--save-images` 时不写 PNG。

N-pair runtime 回归还应验证：

- `--drone-count N` 只由 main runtime 解释，D7 不读取固定数量常量。
- main 对每个有效 assignment pair 创建独立 D7 控制上下文。
- 初段位置 PNG/PN 和末端视觉 PNG 的 time-series 都按 `resource_id/target_id/assignment_id` 隔离。
- D5 `locked`、D3 assignment/version、相机 bbox/LOS 稳定性、机动裕度和距离/闭合条件逐 pair 判定，任一 pair 拒绝不影响其他 pair。

### 7.3 成功与失败判据

成功：

```text
status == range_intercept
  if range_m <= intercept_radius_m

status == collision_intercept
  if collision.has_collided
  and collision_object_name matches assigned actor/object name
```

失败：

```text
status == aborted
abort_reason in {
  resource_missing,
  target_missing,
  terminal_detection_timeout,
  below_ground_or_invalid_altitude,
  terminal_identity_mismatch,
  assignment_revoked
}

status == timeout
  if episode ends before hit/abort
```

撞地、撞障碍、撞非 assigned target 只能记为失败或安全事件，不能记为命中。

### 7.4 D6 指标

建议 D6 从 D7/AirSim 日志中聚合：

| 指标 | 来源 | 含义 |
|------|------|------|
| `time_to_intercept_s` | `InterceptPair.time_to_intercept_s` | 从导引开始到首次成功判据的时间 |
| `min_range_m` | `InterceptPair.min_range_m` / `GuidanceRecord.range_m` | 每个资源-目标 pair 的最近距离 |
| `collision_object_name` | `InterceptCommandRecord.collision_object_name` | 验证是否撞到 assigned actor/object |
| `collision_intercept_count` | pair status | 碰撞对象匹配的成功次数 |
| `range_intercept_count` | pair status | 距离阈值成功次数 |
| `terminal_detection_timeout_count` | abort reason | 末端检测超时次数 |
| `guidance_mode_switch_count` | `mode_switch` / command mode sequence | 中段到末端切换次数 |
| `terminal_mode_entry_rate` | pair count vs terminal locked count | 已分配 pair 中进入末端模式比例 |
| `command_saturation_rate` | D7 command saturation fields | 加速度/转向率限幅比例 |
| `assigned_collision_mismatch_count` | collision object vs assigned target | 撞错对象或撞地事件数 |
| `main_episode_bus_execution_metrics_merged` | main bus metrics metadata | 正式 metrics 是否已经合并真实 D7 执行产物 |
| `raw_contract_reject_count` | raw contract metrics | 执行前 D3/D4/D5 合同诊断拒绝数，不等同于最终拦截失败数 |
| `owner_mismatch_count` | D7 terminal contract rejects | D4 指定接管 owner 与 D3 binding owner 不一致或缺失的拒绝数 |
| `bbox_los_replay_vehicle_control` | D7 replay summary | 离线 replay 必须为 `False`，防止 YOLO/ByteTrack replay 误入控制主线 |

报告图建议包括：

- `range_m` 随时间曲线。
- `radar_midcourse / handover_pending / vision_terminal` 模式时间线。
- 每个 pair 的 `min_range_m` 柱状图。
- `collision_object_name` 与 assigned target 对照表。
- `terminal_detection_timeout_count` 按 episode 的统计。

---

## 8. 补充实施计划

### 8.1 短期：固化当前 Blocks 稳定闭环

- 保持 2v2 actor target 和 SimpleFlight interceptor 作为 baseline 架构。
- 对 main runtime，按 `--drone-count N` 为每个有效 assignment pair 创建独立 D7 控制上下文，不共享视觉 filter 状态。
- actor target 默认外观已由 main/runtime 与 D7 delivery 对齐到 `Quadrotor1`；cube asset 仅作为 legacy 几何 baseline 显式复现选项，后续需要真实 AirSim 验证和阈值/检测调参。
- 明确 `collision_intercept` 必须匹配 assigned actor/object name。
- 在 summary 中保留 `time_to_intercept_s`、`min_range_m`、`status`、`abort_reason` 和 `collision_object_name`。
- 默认继续不保存 PNG，只保存检测框和相机元数据。
- 将 `handover_pending` 显式写入日志状态，即使控制命令仍沿用中段 PN。

### 8.2 P1 done/保持：D3/D4/D5 runtime gate 与 episode bus

- D7 API 已将 D3 binding、D4 action 和 `TerminalAssociation(decision_state="locked")` 作为 `vision_terminal` 的必要入口；D7 本地 `D7RuntimeBus` 已提供 N-pair injection adapter。
- D4 gate blocking、D3/D4/D5 terminal contract gate、owner/version gate 已完成。D7 持续校验 D3 `plan_id/plan_version/owner_node_id/track_version`、D5 `assigned_global_track_id`、`assignment_version` 和 D4 `new_plan_id/new_plan_version/target_node_id`，并把不一致写成 `terminal_contract_reject_reason`。
- D4 `request_center_replan`、`degrade_to_secondary`、`degrade_to_distributed` 和 `reassign` 阶段必须阻断视觉 PNG，确认重分配窗口内不使用旧 D5 lock。`request_secondary_assist` 不转移 owner，也不要求 takeover readiness；只有 binding 已显式切为 secondary owner 时才应用 owner/readiness gate。随后仍需 D5 `locked`、D3 version 和全部视觉/安全门控通过。
- controlled 5v5 center replan 与 2v2 secondary visual PNG gate 回归已通过。main runtime 已把 D7 runtime summary 接入 episode bus，D7 文档不再把这些列为待补能力。
- 最新 5v5 D4/D5 mobile recon/gimbal stress 只改善侦察观测质量：二级网络同帧覆盖和降级 cross-view 仍不足，因此 D7 不放宽视觉 PNG gate；`degrade_to_secondary`/`degrade_to_distributed` 期间若 plan owner/version 尚不可执行，继续记录合同拒绝并保持中段/等待状态。
- 对 `ambiguous/hold/reacquire` 分别输出保守行为，不切换目标，不改写 `global_track_id`；D4 软风险 `continue_center` 不应让 D7 全帧进入 `abort_revoke`。

### 8.3 P1 optional：视觉 PNG 回放与真实检测链路

- D7 已将 `simGetDetections` bbox、YOLO/ByteTrack bbox replay 统一成 D7 `VisionGuidanceObservation` 的离线 adapter。D5 原生 ByteTrack/BoT-SORT admission 未通过，默认在线路径继续使用 AirSim detect；MOT 只保留为 optional replay，后续达到准入指标后再评估。
- 对同一 `local_track_id` 做时间连续性、measurement age、丢检重捕获和 LOS-rate 噪声评估。
- 引入距离/闭合速度估计来源：D2 全局航迹预测、多视角估计、或 AirSim truth-only 离线标签；控制主线不得使用 truth ID 做在线身份绑定。
- 在日志中区分 `source="airsim_detect_metadata"`、`source="yolo_replay"`、`source="truth_only_eval"`，并保留 `terminal_switch_reject_reason`。
- 继续用 D7 离线 replay 评估 LOS-rate、TTC 面积噪声、近距裁切和限幅。YOLO/ByteTrack/BoT-SORT 真实图像链路只作为离线 replay 或 optional 实验路径，不进入默认 SimpleFlight controlled intercept。

### 8.4 P1：真实 AirSim 多 seed calibration 与报告

- D7-owned selector 和对照字段已由 main/runtime 消费；当前保持每 pair 参数与控制日志一致。secondary pending/lease 过期/旧 owner-version、D5 非 locked/ID 不一致的阻断测试已由 D7 固化，main 不得用 CLI 模式选择绕过这些 gate。
- D7 已提供 `run_guidance_strategy_comparison(...)` 和 `summarize_guidance_strategy_comparison(...)`，覆盖 PN、Pure Pursuit、`png_vm`、`png_ttc`。
- D7 已提供 `summarize_guidance_calibration(...)`，可把 comparison rows、replay summary、D7 runtime outputs 和 `GuidanceRecord` 统一成按 guidance law 分组的 calibration summary，字段覆盖 terminal range、closing speed、bbox/LOS/maneuver gate、D4 action block、D5 lock consistency、D3 owner/version consistency、secondary capability/readiness、D5 registration/projection/covariance/Yolo-MOT、reject reason、threshold version 和 benchmark-only 3D/FRPN 口径。
- main runtime 已完成 P1 calibration sweep，40 个真实 SimpleFlight M5N2 episode 和 D6 标准报告已经生成。高威胁目标采用 `2 primary + 1 standby reserve`，不要求同时到达；最佳 profile coalition `5/10`、overall `8/40`。D7 不再把 sweep 编排、M5N2 未运行或报告写盘列为本模块缺口。
- D6 已汇总迁移前 contract `35`、control `7`、mode switch `9`、physical `62`，四层不得相互反推；reserve unauthorized、`global_track_id` rewrite、truth identity online use 均为 `0`，但 truth state 当时不可用。后续报告继续保留 `min_range_m`、`terminal_range_m`、`closing_speed_mps`、`time_to_intercept_s`、两类 truth online use、各类 reject reason、`visual_png_switch_count`、guidance mode/handoff distribution、bbox/TTC/LOS gate、threshold version 和 raw contract vs execution 双口径。
- 2026-07-10 单 seed 已提供首份真实执行校准样本：2/2 collision success 与低 `terminal_switch_allowed_rate=0.0282` 同时出现。后续报告必须按 pair 分开呈现“碰撞成功”“进入 `vision_terminal`”“raw gate allowed”和“aggregate visual PNG switch event”，并核对当前 aggregate `visual_png_switch_count=3` 与 raw CSV allowed row count=2 的定义差异，避免把 radar PN 主导的成功误归因为视觉 PNG。
- 历史 2026-07-10 2v2 10-seed 基线得到 18/20 collision success，历史四律单-seed 2 s smoke 四律均 timeout；历史 M5N2 15 s 诊断为 0/30 active-pair 命中和 24 次 `terminal_detection_timeout`。这些阶段数据已被 40-episode 最终批次覆盖，仍可用于解释第二 primary 的 acquisition/gate 失败演进，不得作为当前结果。
- 当前 P1 校准第二 primary、同配置 multi-seed/dropout/candidate、loop latency，以及 pair funnel/closing speed/三维几何和平台机动裕度；位置 PN 与 `png_guidance_delivery` 核心公式保持不变。3D PN、True PN、APN、FRPN 只在隔离 P2 benchmark 中统计，不进入默认在线 calibration 或物理闭环结论。
- 该对照接口只补报告字段和切换/gate 日志，不修改 PN/PNG 控制律本体。

---

## 9. 结论

D7 当前已经具备可测试的经典 PN 研究模块、D3/D4/D5 terminal contract、SimpleFlight 视觉 PNG gate，以及被 AirSim controlled intercept 消费的 N-pair 导引上下文。架构上应继续坚持四条原则：

1. 目标 ID 来自 D1/D2/D3/D5，D7 不创建、不关联、不改绑。
2. 中段使用全局航迹 PN，末端必须由 D5 对同一 `assigned_global_track_id` 锁定后进入视觉导引。
3. 在线控制只认 D2 estimate 和当前 D3 binding；actor/object identity 只用于运行后离线配对与 5 米评分，撞地或撞错对象不能计为离线成功。
4. main runtime 由 `--drone-count N` 控制规模，并为每个有效 assignment pair 创建独立 D7 控制上下文；2v2 只能作为 baseline，不是数量假设。

当前 P1 合同层和 canonical 五层执行链已经接通。剩余 P1 聚焦第二 primary、同配置 multi-seed/dropout/candidate、loop latency，以及 pair funnel/closing speed/三维几何与平台机动标定。D5 原生 MOT 未准入，默认继续使用 AirSim detect。D7 当前权威全量回归为 `188 passed`，安全三项违规为 0，核心 PN/PNG 公式不变。P2 optional benchmark 仅包含 3D PN、True PN、APN、FRPN 的质点/replay 对照，FRPN 为研究近似；这些导引律在线化、同时到达、PX4/MAVLink/body-rate、MPC/NMPC、ViSP/ROS2 等继续后置。

## 10. M 对 N 协同导引评审补充（2026-07-11）

专项综述 `D7_M_TO_N_COOPERATIVE_GUIDANCE_REVIEW.md` 已核验 12 篇主要同行评审论文和 5 个开源候选。结论是：impact-time consensus、finite/fixed/prescribed-time cooperative guidance 和两阶段 consensus-to-PN 在论文中已有稳定研究路线，但没有成熟、许可证明确、带测试、适配多旋翼与现有 D3/D4/D5 合同的开源默认实现。

对本项目的直接影响：

1. 当前每个 assignment pair 仍独立运行 PN/PNG；新增 coalition/version/role/wave/window/activation 只做中心化执行门控，不是 cooperative PN 或 impact-time consensus。
2. `k_j=3` 时，同步、序贯或混合模式必须由 D3/D4 的版本化任务语义决定；D7 不自行选择成员或波次。
3. 同步到达必须绑定不同 terminal approach sectors/impact angles 和成员最小距离；否则三机同点同时到达会放大互撞、遮挡和饱和风险。
4. 每个成员仍独立满足 D5 locked、D3 owner/version、D4 action 和视觉/机动 gate；任何成员 locked 都不能自动放行全联盟。
5. P1 coalition 合同层已完成并在 CV 10-seed 达到 8/10 验收；D4 commit-aware gate 和正确 M=5/N=2 topology 已接线。真实 SimpleFlight 40-episode 最终结果为最佳 `5/10`、overall `8/40`，当前重点是第二 primary 视觉获取/gate 与 range/closing speed/3D/机动标定，不再把“M5N2 未运行”列为缺口。3D PN、True PN、APN、FRPN 只进入 P2 optional benchmark，FRPN 为研究近似。
