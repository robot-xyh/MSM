# AirSim Blocks Runtime

## 2026-08-10 D5时序关联与D6回灌

长距离扫描运行时已接入D5有状态时序几何关联。每个相机在单个episode内持有独立状态，
episode切换时重新创建，不跨reset复用。逐帧几何结果先经过0.25秒有界保持和两帧换绑确认；
只有当前帧的`measured_assignments`可进入发现、提示、完成、关联准确率和截图标注。
`active_bindings`和`coasted_records`只用于连续性审计，不能形成末端锁定或控制许可。

运行时新增`temporal_binding_events.csv`和`dropout_events.csv`。前者记录继续、待确认、
保持、确认、过期和恢复事件；后者记录恒像面角速度外推、预测年龄及增长后的像素协方差。
即使没有记录，CSV也保留固定表头，D6可区分有效空集合、历史缺失文件和损坏文件。
`metrics.json`同时保留已确认时序换绑数和逐帧瞬时换绑数，并把超过保持窗的过期事件作为
有效中断；历史多目标跟踪短缺口仍单列，不能用外推记录冒充实测观测。

每个episode核心文件写盘后，main自动调用D6只读评估器，输出
`d6_evaluation/d5_long_range_registration_per_episode.csv`、聚合JSON、中文报告和PNG曲线，
并写`d6_evaluation_index.json`。D6没有在线关联、全局编号写入或控制权限；失败关闭结论
不会反向改变运行时动作。

2026-08-10完成接口级验证：AirSim长距专项`23 passed`，D5全量`904 passed`，D6专项
`7 passed`、全量`1425 passed, 16 skipped`。覆盖0.06、0.10、0.17秒短缺口恢复、单帧
错误换绑保持、连续两帧换绑确认、预测证据不授权和episode隔离。本批没有启动新一轮真实
AirSim v3 episode；真实场景和至少10个seed的校准仍是开放P1。

## 2026-08-10 D5三千米窄视场扫描接口

已完成episode可复现的三维结果绘图。绘图器读取`actor_trajectory_truth.csv`、
`scan_gimbal.csv`、`associations.csv`和`scenario.json`，输出全局位置与轨迹、目标群局部
轨迹、四个时刻的位置切片、配准事件三维分布和汇总JSON。Actor真实位置只用于离线报告，
不会回灌在线D5关联。复现命令为：

```bash
python3 research_modules/airsim_runtime/run_d5_long_range_3d_report.py
```

默认输出到`subagent_reviews/assets/d5_20_target_long_range_20260810/`，用于主级二十目标
长距离配准报告。三维图使用北东地原始位置，纵轴显示高度`-Down`；为便于阅读，图框显示
比例经过调整，坐标刻度仍为实际米制数值。

独立的 ComputerVision 长距离扫描入口默认运行20目标，也可通过`--target-count N`设置
其他规模。中心相机为2600×2160、水平视场0.621度，记录600毫米等效焦距；拦截相机为
1920×1080、水平视场2.750979度，按三千米与五百米成像尺度相当的条件记录100毫米
等效焦距。AirSim settings只配置分辨率和水平视场，毫米焦距仅用于方案说明。

目标使用`Quadrotor1`网格和`simSetObjectPose`移动。默认速度模长为50米/秒，速度方向
朝向中心防区。场景保留前后错列和视线交叉，启动前检查全观察窗口内三维最小间距不小于
25米。默认观察12秒，逻辑频率100赫兹。

中心云台通过`simSetCameraPose`执行二维偏航/俯仰扫描。`coverage_safe`先读取中心持有的
`GlobalTrack`粗位置和协方差，以三倍标准差形成俯仰搜索边界，再按相机水平、垂直视场及
20%重叠率生成蛇形栅格。`mechanical_2s`保留180度/秒的机械速度诊断，也在多个俯仰层
扫描，但不设置强制覆盖门。拦截相机接收每条已确认航迹的偏航和俯仰提示，输出提示下发、
开始执行、完成时间和失败原因。

`simGetDetections`返回的actor名称和对象编号在runtime边界被剥离，只写入离线评分侧车。
长距专项在通用检测器之后使用恒速预测和匈牙利匹配生成匿名本地轨迹号；该跟踪器不进入
其他AirSim场景。在线几何关联携带双时间戳、像素协方差和中心航迹协方差，不改写
`global_track_id`。actor名称、对象编号和交叉窗口真值只用于离线连续性评分。

两个扫描episode在同一Blocks进程内运行，中间reset。每2秒分别保存中心和拦截相机一张
PNG截图，包括逻辑时刻0秒和可整除的结束时刻；不生成视频。运行命令：

```bash
python3 research_modules/airsim_runtime/run_d5_long_range_cv_scan.py \
  --target-count 20 \
  --target-speed 50 \
  --duration 12 \
  --snapshot-interval 2 \
  --mode both
```

若主场景在三千米处没有检测，可增加
`--diagnostic-target-scale 2.0`运行明确标记的网格放大诊断。诊断结果不能替代比例1.0的
主场景。

每个episode保留`scan_plan.json`、`scan_gimbal.csv`、`interceptor_cue_plan.*`、
`global_tracks.csv`、`detections.*`、`associations.csv`、`latency_rpc.csv`、
`mot_continuity.json`、`crossing_windows.csv`、离线actor轨迹和真值、截图清单、指标、
曲线、中文报告及`record_manifest.json`。试验根目录另存settings、scenario、Blocks日志、
诊断和总记录清单。记录清单会报告缺失项，并检查mp4、gif、avi、mov和mkv文件为零。

### 2026-08-10世界视线修正版真实Blocks复跑

修正代码已在一个真实Blocks进程内完成复跑，`mechanical_2s`和`coverage_safe`两个profile
以reset分隔。场景包含20个目标，seed为20260810，目标速度为50米/秒，观察12秒，逻辑频率
100赫兹。证据目录为
`outputs/d5_cv_long_range_20target_50mps_2d_worldray_v2_20260810/`。

`mechanical_2s`累计发现13/20个目标，13条拦截相机提示全部完成，可评分关联准确率为
0.9928826。连续可见段身份切换为0，短缺口中断为3；18个交叉窗口中1个可评分，窗口内
身份切换为0。运行与记录门控通过；该模式的多目标跟踪门控因3次短缺口中断未通过。

`coverage_safe`累计发现20/20个目标，连续五帧确认17/20个目标；17条提示全部被拦截相机
观察并完成，可评分关联准确率为0.9982063。连续可见段身份切换为0，短缺口中断为3，
长期重发现为16，连续段纯度和连续性均为1.0。18个交叉窗口中2个可评分，交叉窗口身份
切换为0，交叉纯度和连续性均为1.0。几何绑定发生4次切换。运行与记录门控通过，覆盖门
因短缺口中断未通过。

两个profile均在逻辑时刻0、2、4、6、8、10和12秒保存中心、拦截相机截图，各形成14/14张
证据图；视频文件为0，记录清单缺失项为0。运动补偿将本轮连续可见段身份切换降为0，
但没有使全部门控通过。剩余P1问题是短时漏检仍会形成短缺口、18个交叉窗口仅有1至2个
可评价，以及`coverage_safe`中的4次几何绑定切换。

### 修正依据与历史对照

审查表明旧匿名跟踪器直接在像素坐标中外推，中心每帧约0.497度的扫描和机械/拦截云台
最高1.8度的转动被误认为目标运动。旧评分还把超过0.5秒的离视场重现计入连续段身份切换，
并把交叉时段内的无关目标纳入目标对指标。当前实现已改为用同步相机内外参把检测中心
反投影为NED世界单位视线，在世界视线上执行恒速匹配，同时保留检测框尺度和尺度变化
代价。在线跟踪仍不读取actor名称、object_id、global_track_id或离线真值。

评分口径现分为连续可见段、短缺口和长期重发现。间隔不超过0.05秒时评估连续段身份
切换；0.05至0.50秒单列短缺口中断；超过0.50秒单列长期重发现，并保留重发现前后的
编号变化。交叉窗口按相机和指定目标对评分，两个目标没有同时出现或样本不足时标记为
`not_evaluable`。门控至少需要一个可评分交叉窗口，不再把不可用数据视为通过证据。

历史日志离线复核写入
`outputs/d5_cv_long_range_20target_50mps_2d_20260810_mot_reaudit/`，源目录哈希保持不变。
机械模式在新口径下的连续段身份切换由16降为0，长期重发现45次，仍有3次短缺口中断；
18个交叉窗口仅1个可评分。连续覆盖模式的连续段身份切换由36降为0，长期重发现18次，
仍有3次短缺口中断；18个交叉窗口有2个可评分。运动补偿后可评分交叉窗口均为0次交换，
纯度和连续性均为1.0。两种模式均因短缺口中断保持门控未通过。该离线判断已经由上述
世界视线修正版真实复跑核对；离线结果仍只作为历史日志重评分证据。

只做离线复核、不启动AirSim的命令：

```bash
python3 research_modules/airsim_runtime/run_d5_long_range_mot_reaudit.py \
  --source-dir research_modules/airsim_runtime/outputs/d5_cv_long_range_20target_50mps_2d_20260810
```

2026-08-10早期版本已在一个真实Blocks进程内完成两个reset分隔episode。运行器在RPC首次拒绝
连接后会重建msgpack客户端；相机创建后通过`simSetCameraFov`显式设置视场并回读确认。
中心相机实际为2600×2160、0.621度，拦截相机实际为1920×1080、2.750979度。
20/20 actor生成成功，6000/6000次actor位姿更新和600/600次云台更新均成功。在线
`detections.csv/jsonl`不含actor名称、对象编号或真值全局编号；这些字段只进入
`offline_truth.csv`。

实测结果没有通过连续覆盖门。机械速度诊断模式发现并确认4/20，拦截相机观察4/4，
逐帧关联准确率0.997647，身份切换0；该模式不设置强制验收门。20%水平视场重叠模式
发现并确认8/20，拦截相机观察5/8，逐帧关联准确率1.0，但本地轨迹身份切换2次。
中心垂直视场约0.516度，目标俯仰范围约-0.408至+0.761度，早期单轴扫描因此漏掉高度层；
三秒窗口也不足以顺序处理提示。该数据是二维扫描改造前的基线，证据位于
`outputs/d5_cv_long_range_20target_20260810/`。12秒、50米/秒、二维扫描和世界视线匿名跟踪
已完成上述真实Blocks复跑；覆盖率和连续性采用修正版证据目录中的结果。当前`GlobalTrack`
仍来自合成D1/D2夹具，尚未覆盖真实雷达误差、漏报、云台动态滞后和图像检测误差。

## 2026-07-23 D3 身份承诺兼容桥

D3 现只接受显式 `committed` 航迹。当前 AirSim episode bus 使用经典二维 D2，该跟踪器尚无
结构歧义保持和 `d2.identity-evidence-commitment.v2` 侧车。main 在经典 D2 输出边界为本帧
全部中心航迹生成逐 ID 的显式 committed 清单，再交给 D3 适配器。清单必须与输入航迹集合
完全一致，不能由 AirSim actor、检测真值或目标名称推导。

直接调用 `target_tracks_from_online_d2()` 而不提供该清单时，目标状态为
`identity_commitment_missing`，D3 不会分配。该行为避免把兼容桥重新变成隐式默认值。
AirSim runtime 全量 `157 passed`，原 2v2、5v5、M5N2、二级接管和分布式故障注入软件
fixture 均恢复。此次没有启动 Blocks；真实多 seed 的承诺撤销和计划升版仍待测试。

## 2026-07-15 M5N2 ClockSpeed 1.0/0.2/0.1 Comparison

Main completed reset-separated SimpleFlight M5N2 campaigns for
`ClockSpeed=0.2` and `ClockSpeed=0.1` using the same 20-case matrix as the
existing `ClockSpeed=1.0` campaign: baseline and
`candidate_soft_prediction_trend_coast`, seeds 1-10. Intruders remained moved
Unreal actors, interceptors remained SimpleFlight vehicles, the control period
remained 0.1 s, and the 5 m offline physical-intercept criterion was unchanged.
No camera screenshots were saved.

The three-suite D6 comparison contains 60 real AirSim cases and 20 complete
cross-speed pairings. Baseline pair/target/coalition results are respectively
`6/30, 6/20, 0/10` at 1.0; `9/30, 9/20, 0/10` at 0.2; and
`4/30, 4/20, 0/10` at 0.1. Thus 0.2 is the best measured baseline setting in
this matrix; reducing to 0.1 did not improve physical completion. Baseline
control-tick wall means increased from about 1070 ms at 1.0 to 2208 ms at 0.2
and 3453 ms at 0.1. The current sequential per-primary AirSim RPC dispatch is
therefore coupled to ClockSpeed and must not be interpreted as a fixed-rate
controller.

D6 froze each M5N2 case at 3 active-primary, 2 target, and 1 coalition
opportunities. Four candidate cases have incomplete or conflicting opportunity
evidence: 0.1 seeds 7 and 9, and 0.2 seeds 6 and 9. Their candidate aggregates
remain unavailable; standby reserve outcomes are never counted as active
primary success. Identity and state online truth use are zero in all 60 cases.
The Chinese report and curves are under
`outputs/m5n2_clock_speed_comparison_20260715/`; the main interpretation is in
`subagent_reviews/MAIN_M5N2_CLOCK_SPEED_COMPARISON_REPORT_20260715.md`.

## 2026-07-15 M5N2 20-Case Stop And Result

Main completed only the M5N2 portion of
`p1_terminal_timing_funnel_10seed_20260715`: baseline seeds 1-10 and
`candidate_soft_prediction_trend_coast` seeds 1-10. The batch was terminated
after 20/20 M5N2 cases. One `png_ttc_2v2_seed001` case completed during the
process transition before TERM took effect; it is excluded from this M5N2
result and is not a multi-seed result. Dropout completed zero cases, and no
missing outcome may be represented as a zero-valued result.

Both profiles produced `6/30` active-primary physical successes, `6/20`
target successes, and `0/10` coalition completions. The second required
primary reached the 5 m threshold in `0/10` cases for both profiles. Candidate
prediction/control activity increased but paired non-degradation failed, so
soft prediction and trend coast remain candidate-only and disabled by default.
All 20 canonical actual-execution artifacts are available; online truth
identity/state use is zero.

Pooled real timing contains 3805 records per layer. Main bus mean/P95/max is
`349.34/487.40/1305.99 ms`, dominated by D1 fusion. Control tick
mean/P95/max is `1069.45/1254.06/2072.51 ms`, dominated by AirSim frame
sampling; all 3805 outer ticks exceed 100 ms. The outer layer includes bus
processing and must not be added to the inner total. Raw per-case timing is
valid, while suite-level D6 timing remains unavailable until a versioned
multi-episode manifest supports reset frame indices without weakening the
strict single-episode schema.

All 20 second-primary executions ended with `collision_stop`. The stop record
does not yet persist the collision object, contact normal, or member/environment
separation, so this remains a P1 provenance gap rather than evidence that D5
alone caused the physical failure.

Evidence and figures are indexed by
`subagent_reviews/MAIN_M5N2_TIMING_AND_SECOND_PRIMARY_REPORT_20260715.md` and
`outputs/p1_terminal_timing_funnel_10seed_20260715_m5n2/`.

## 2026-07-15 Strict Secondary Readiness Integration

Main no longer treats a secondary heartbeat as sufficient takeover evidence.
The episode communication tick consumes only the previous completed D4
decision and requires the shared D4 readiness contract: explicit episode time,
valid epoch/lease, fresh heartbeat/cue/communication, valid gimbal and coverage
state, network full-view evidence, and sustained readiness. Missing, stale, or
incomplete evidence fails closed. Multiple records for the same secondary are
merged conservatively; conflicting lease epoch or expiry rejects that node
instead of allowing last-write-wins ownership.

The heartbeat-only negative case, complete-readiness positive case, and
conflicting-lease negative case pass. Current deterministic regressions are
`D4 278`, AirSim runtime `147`, and integrated point-mass `7`. No new AirSim
episode was launched for this change. Real network delay, loss, reordering,
clock drift, retransmission, and multi-seed failover timing remain P1.

## 2026-07-14 Actual-Execution Real AirSim Validation

The P0 evidence path has now been exercised in real Blocks for tuned 2v2 and
M5N2 seed 1. Both runs generated `d7_actual_execution_metrics.json` with
schema `d7-actual-execution-metrics-v2`; neither generated an unavailable
artifact. The command CSV, intercept summary, and actual envelope agree on
physical successes (`2/2` for 2v2 and `2/3` active pairs for M5N2), and command,
actual metadata, and canonical D3 history carry the same plan ID. Online truth
identity and state use are both zero.

Direct-run evidence identity follows `case_id > sequence_id > episode_id`.
This keeps independent full-flow sequences distinct even though each contains
an episode named `episode_006_full_flow`. The combined D6 report is under
`outputs/p0_actual_v2_validation_20260714/d6_acceptance/` and reports canonical
actual availability `2/2`. Its overall P1 acceptance remains false because the
two-case P0 smoke does not include the full paired candidate, dropout, and
multi-seed matrix.

M5N2 remains a P1 performance issue: both targets were intercepted by at least
one resource, but the second active primary for the high-threat target reached
only about `11.02 m`, so coalition completion was `0/1`. Loop latency was about
`123.3 ms` for 2v2 and `384.6 ms` for M5N2.

The actual envelope validates five independent layers: contract, control,
terminal-switch permission, mode switch, and physical interception. The
terminal-switch count is recomputed from the final command CSV and is not
inferred from control permission. D6 also recomputes target-state freshness
from the source-hash-verified command CSV. The two seed-1 cases provide 656
available samples, pooled mean/P95/max age of about `0.0872/0.2/0.2 s`, zero
stale samples, and only `d2_estimated_global_track` as the online state source.
The remaining P1 is multi-seed distribution and latency calibration, not
schema registration.

## 2026-07-14 Actual-Execution Plan Provenance

After SimpleFlight control completes, main now asks D6 to build
`d7_actual_execution_metrics.json` with schema
`d7-actual-execution-metrics-v2`. The artifact hashes the final command,
intercept-summary, and main-bus metric sources and preserves the plan IDs,
positive plan versions, owner availability, online truth safety counts,
effective visual-control transitions, physical results, and runtime samples.
Integrated replay data is diagnostic only and cannot supply missing execution
provenance.

Plan ID and version are mandatory on each command row. Owner provenance is
required for effectively authorized secondary or distributed execution; an
ordinary center row or a non-authorized transition may leave it unavailable.
The two controlled center/secondary regressions and the full runtime suite now
pass (`142 passed`). The real seed-1 gate described above is complete; the
remaining campaign is the same-configuration multi-seed P1 calibration.

## 2026-07-14 P1 Terminal Semantics Integration

Main now passes stable camera/stream/detector/tracker identity, executable
primary membership, and duplicate-lock risk into D5. D7 guidance events use
the module's canonical `d7_terminal_semantics_v2` record, and SimpleFlight
termination rows force live contract/control fields false while retaining
prior latch/authorization audit fields. The P1 terminal-closure sweep writes
metric envelopes with producer/scope/denominator/lifecycle, physical and
performance context, D3 history paths, D7 execution paths, and automatic D6
suite/per-case reports.

This closes runtime schema wiring only. It does not replace the required real
AirSim rerun for M5N2 second-primary acquisition, 30/50 m visual recall,
native-MOT admission, dropout behavior, physical interception, or loop-latency
calibration.

This package runs the first real AirSim Blocks gates. It starts Blocks with a
repository-local settings file, connects through the Python RPC API, samples
vehicle poses, actor targets, scene images, LiDAR metadata, AirSim built-in
detections, scene objects, and replays the captured frames into the existing
D1-D7 integration.

The default path is read-only. When `--execute-intercept` is passed, only
`episode_006_full_flow` enables SimpleFlight API control for the interceptor
vehicles. Intruders remain non-vehicle Unreal actors moved with
`simSetObjectPose`. Target recognition defaults to AirSim `simGetDetections`,
but `--detection-backend yolo` routes in-memory Scene images through D5
YOLOv8 + MOT using `research_modules/d5_terminal_association/best.pt` unless a
different `--yolo-weights` path is supplied. D7 terminal handoff uses the
SimpleFlight-compatible PNG guidance gate: detector boxes must pass bbox,
LOS-rate, visual latency, and maneuver-margin checks before the controller
switches from `radar_midcourse` to
`vision_terminal`.

## 2026-07-14 Feedback Contract

The episode bus now separates terminal uncertainty from safety conflicts before
the next D3 planning cycle. Ordinary D5 `ambiguous`, `hold`, and `reacquire`
states are emitted as resource-target edge-soft feedback: they still block the
current pair's visual handoff, but they do not mark the whole interceptor
unavailable. Verified-friend overlap, spoof-suspected identity conflict,
duplicate lock, and explicit assignment conflicts remain fail-closed hard
feedback. Assignment evidence also derives `active` from D3's
`activation_state`, so an unactivated reserve is recorded as standby rather
than active.

This is a contract and regression fix, not new AirSim performance evidence.
The M5N2 `5/10` result remains the pre-fix baseline until main reruns the same
geometry and seeds.

## Online Truth Boundary

The main episode bus now keeps AirSim actor identity out of online D1/D2 DTOs,
delivers observations only after their arrival timestamp, and leaves truthless
D2/D6 metrics unavailable instead of reporting zero. Offline integrated replay
uses an explicit offline truth policy.

The controlled SimpleFlight executor now consumes the D2 estimated target
position, velocity, covariance, measurement timestamp, and arrival timestamp.
The default path, active center replan path, and active secondary takeover path
all use the same truth-isolated control evidence. Active-degradation fixtures
may override D3 plan/version, D4 permission, and D5 lock state, but they cannot
provide target kinematics or actor/object/mesh aliases. Missing or stale target
estimates fail closed.

AirSim actor truth remains available only to synthetic sensor generation,
trajectory plotting, offline global-track-to-truth pairing, and the post-run
three-dimensional 5 m scorer. `truth_state_online_use_count` is distinct from
`truth_identity_online_use_count`; strict integrated paths require both online
uses to be zero. The D7 PN/PNG core formulas were not changed. Runtime and
module regressions close the code-level P0, but historical physical results do
not become truth-isolated evidence retroactively. The same-seed real AirSim
rerun remains a P1 evidence task.

## Run

```bash
python3 research_modules/airsim_runtime/run_blocks_smoke.py \
  --episode-id blocks_smoke_001 \
  --duration 2.0 \
  --dt 0.5
```

Run the main-managed staged sequence with one Blocks launch and reset between
episodes:

```bash
python3 research_modules/airsim_runtime/run_blocks_sequence.py \
  --sequence-id blocks_sequence_001 \
  --duration 2.0 \
  --dt 0.5 \
  --blocks-arg=-windowed \
  --blocks-arg=-ResX=640 \
  --blocks-arg=-ResY=480 \
  --blocks-arg=-NoVSync \
  --blocks-arg=-NoHMD \
  --blocks-arg=-NoSound
```

Run multiple random seeds without restarting Blocks for every seed:

```bash
python3 research_modules/airsim_runtime/run_blocks_sequence.py \
  --cv-5v5 \
  --batch-seeds 1,2,3,4,5 \
  --sequence-id blocks_cv_5v5_batch_001 \
  --duration 6.0 \
  --dt 0.5 \
  --blocks-arg=-windowed \
  --blocks-arg=-ResX=640 \
  --blocks-arg=-ResY=480 \
  --blocks-arg=-NoVSync \
  --blocks-arg=-NoHMD \
  --blocks-arg=-NoSound
```

When `--batch-seeds` contains more than one seed, main now starts Blocks once,
runs each seed as a separate sequence, resets between sequences/episodes, and
then stops Blocks at the end. The batch summary records
`batch_mode=single_blocks_reset_loop` and
`blocks_launched_once_for_batch=true`.

## N-Drone Parameter

Main now owns the run-size parameter. For AirSim actor/CV scenarios, pass
`--drone-count N`; main generates N resources, N moved actor targets, and a
matching AirSim settings file under the run output directory. D1-D7 consume the
resulting arrays and must not assume a fixed 2v2 or 5v5 size.

For unequal scale, use `--resource-count M --target-count N`. This enables the
centralized cooperative-demand fixture when `M != N`; `--drone-count` remains
the equal-count shorthand and cannot be combined with the two independent
count options. The default high-threat policy is `k=3`, `hybrid 2+1`:

```bash
python3 research_modules/airsim_runtime/run_blocks_sequence.py \
  --cv-5v5 \
  --resource-count 5 \
  --target-count 2 \
  --high-threat-resource-count 3 \
  --cooperative-coordination-mode hybrid \
  --cooperative-primary-count 2 \
  --cooperative-wave-gap 2.0 \
  --sequence-id blocks_cv_m5_n2_cooperative_001 \
  --duration 6.0 \
  --dt 0.5
```

The online fixture assigns the high-threat prior by stable center-owned track
order and never consults AirSim truth IDs. D3 admits complete demand slots only;
D5/D7 keep one state per resource-target pair. If the center is unavailable,
`k>1` execution requires the current D4 atomic coalition commit, ACK, epoch,
lease, and digest contract. Missing or conflicting evidence remains fail-closed.

Examples:

```bash
python3 research_modules/airsim_runtime/run_blocks_sequence.py \
  --cv-5v5 \
  --drone-count 3 \
  --secondary-count 1 \
  --sequence-id blocks_cv_n3_sequence_001 \
  --duration 4.0 \
  --dt 0.5
```

```bash
python3 research_modules/airsim_runtime/run_blocks_sequence.py \
  --actor-5v5 \
  --execute-intercept \
  --drone-count 4 \
  --sequence-id blocks_actor_n4_intercept_001 \
  --duration 8.0 \
  --dt 0.2 \
  --control-dt 0.1
```

For D5 geometric registration:

```bash
python3 research_modules/airsim_runtime/run_d5_geometric_registration.py \
  --drone-count 4 \
  --episode-id d5_cv_n4_geometric_001 \
  --duration 6.0 \
  --dt 0.5
```

Run the first 2v2 actor-target sequence. Intruders are spawned/moved actors,
not SimpleFlight vehicles. The default target-recognition backend is AirSim
`simGetDetections`; add `--detection-backend yolo` to use D5 YOLOv8 + MOT:

```bash
python3 research_modules/airsim_runtime/run_blocks_sequence.py \
  --actor-2v2 \
  --sequence-id blocks_2v2_actor_sequence_001 \
  --duration 3.0 \
  --dt 0.5 \
  --blocks-arg=-windowed \
  --blocks-arg=-ResX=640 \
  --blocks-arg=-ResY=480 \
  --blocks-arg=-NoVSync \
  --blocks-arg=-NoHMD \
  --blocks-arg=-NoSound
```

YOLOv8 + ByteTrack/BoT-SORT input can be enabled without saving PNG frames:

```bash
python3 research_modules/airsim_runtime/run_blocks_sequence.py \
  --actor-2v2 \
  --execute-intercept \
  --detection-backend yolo \
  --yolo-weights research_modules/d5_terminal_association/best.pt \
  --yolo-tracker-backend bytetrack
```

By default, sampled camera frames are checked but not written as PNG files. Add
`--save-images` only when debugging camera views or detection boxes.

Run the isolated D5 5-primary-camera plus 1-recon-camera branch experiment:

```bash
python3 research_modules/airsim_runtime/run_d5_multicamera_branch.py \
  --campaign-id d5_cv_5v5_multicamera_fast_detect \
  --drone-count 5 \
  --primary-backend detect \
  --duration 6 \
  --dt 0.25 \
  --target-speed-scale 5.0 \
  --snapshot-interval 0.5
```

The branch scales from `--drone-count N`; `5` is the formal baseline rather than
an algorithm limit. `--target-speed-scale 5.0` multiplies every component of the
original converging velocity pattern, preserving direction while producing
about 3.48-4.72 m/s in the 5-target case. `--snapshot-interval` is converted to
runtime frame intervals, so `0.5` with `--dt 0.25` saves every second sampled
frame. The 6 s fast run ends before the linear lateral trajectories meet, so
the sampled formation remains convergent throughout the episode.

With `--primary-backend detect`, the branch runs one anonymous AirSim detect
episode on all cameras. Use `--primary-backend all` to launch Blocks once and
run the detect baseline plus YOLOv8/native ByteTrack candidate as
reset-separated episodes; the recon camera remains on AirSim detect. This
isolated D5 branch does not run D1/D2: main synthesizes the center-side
`GlobalTrack` fixture from actor kinematics and keeps actor identity available
for offline scoring. D5 association costs and selections receive only the
pre-existing GlobalTrack IDs, camera-local tracks, timestamps, covariance, and
geometry; they do not read local actor/object/truth identity. Interval images
are enabled deliberately for this visual-inspection branch and remain disabled
by default elsewhere.

Recompute registration metrics and the Chinese report from the captured frames
without launching Blocks:

```bash
python3 research_modules/airsim_runtime/run_d5_multicamera_branch.py \
  --campaign-id d5_cv_5v5_multicamera_fast_detect \
  --drone-count 5 \
  --primary-backend detect \
  --replay-existing
```

Registration projects each `GlobalTrack` at the individual camera batch
measurement timestamp. Passing the last episode timestamp for every frame
causes a systematic image-plane shift in moving-target sequences and is
explicitly avoided. The report separates detector recall, scored and strict
association accuracy, per-camera errors, local ID switches, coverage, online
truth use, and `global_track_id` rewrite count.

Run the ComputerVision 5v5 D1-D5 replay sequence. All interceptor and secondary
nodes are `ComputerVision` camera vehicles; targets remain spawned/moved actors.
This mode validates fusion, association, assignment, terminal visual
registration, and degradation arbitration without SimpleFlight dynamics:

```bash
python3 research_modules/airsim_runtime/run_blocks_sequence.py \
  --cv-5v5 \
  --sequence-id blocks_cv_5v5_sequence_001 \
  --duration 6.0 \
  --dt 0.5 \
  --blocks-arg=-windowed \
  --blocks-arg=-ResX=640 \
  --blocks-arg=-ResY=480 \
  --blocks-arg=-NoVSync \
  --blocks-arg=-NoHMD \
  --blocks-arg=-NoSound
```

The CV 5v5 settings define `Interceptor_Cam_1..5` plus
`Secondary_Recon_1..2`. Main samples every camera with explicit `vehicle_name`,
records detector boxes, and feeds synthetic radar/acoustic/EO
observations into D1 using the same actor truth with latency and covariance.
LiDAR capture is disabled in this mode because the vehicles are camera-only CV
nodes.
During capture, main also updates CV camera poses with `simSetVehiclePose`.
`Interceptor_Cam_i` follows the currently assigned target at a configurable
standoff distance and the pose orientation is set to look at that target. The
default secondary reassignment swaps the second and third camera targets halfway
through the episode, so both initial assignment and reassignment views are
validated. `Secondary_Recon_1/2` keep overwatch positions and rotate toward
their coverage-cell target centroids.

Run the dedicated D4/D5 5v5 stress sequence:

```bash
python3 research_modules/airsim_runtime/run_blocks_sequence.py \
  --cv-5v5-d4d5-stress \
  --sequence-id blocks_cv_5v5_d4d5_stress_001 \
  --duration 6.0 \
  --dt 0.5 \
  --blocks-arg=-windowed \
  --blocks-arg=-ResX=640 \
  --blocks-arg=-ResY=480 \
  --blocks-arg=-NoVSync \
  --blocks-arg=-NoHMD \
  --blocks-arg=-NoSound
```

This profile uses `settings/blocks_cv_5v5_d4d5_stress_settings.json`. The five
targets start about 50 m in front of the interceptor cameras, target spacing is
20 m, interceptor camera spacing is 20 m, and the two secondary reconnaissance
cameras are about 50 m above the target layer.
Targets use the Blocks AirSim `Quadrotor1` actor asset by default and a 4 m
visual scale so the default AirSim detector reliably produces multi-target
terminal frames; this profile tests D5/D4 logic, not small-object detection
limits. Pass `--target-asset-name 1M_Cube_Chamfer` only for legacy geometry
baseline replay. Main runs three reset-separated cases: no degradation,
degrade to secondary node, and degrade to distributed mode. Outputs include
`d5_terminal_observations.jsonl`, `d5_cross_view_associations.json`,
`d4_decisions.jsonl`, per-case reports, and the aggregate
`D4_D5_5V5_STRESS_AIRSIM_REPORT.md`.

Run the P1 D4/D5 calibration matrix when the goal is to compare secondary
recon geometry rather than one fixed setting:

```bash
python3 research_modules/airsim_runtime/run_blocks_sequence.py \
  --p1-calibration-sweep \
  --sequence-id p1_d4d5_calibration_sweep_001 \
  --batch-seeds 1,2,3 \
  --drone-count 5 \
  --p1-secondary-heights 50,100,200 \
  --p1-secondary-fovs 60,80,110 \
  --p1-secondary-counts 1,2,3 \
  --p1-secondary-standoffs 0,5,15 \
  --duration 6.0 \
  --dt 0.5 \
  --blocks-arg=-windowed \
  --blocks-arg=-ResX=640 \
  --blocks-arg=-ResY=480 \
  --blocks-arg=-NoVSync \
  --blocks-arg=-NoHMD \
  --blocks-arg=-NoSound
```

The sweep uses `ComputerVision` D4/D5 stress episodes with mobile secondary
recon enabled. Different height/FOV/secondary-count combinations generate
different AirSim settings, so main launches Blocks once per geometry
combination and runs all requested seeds inside that combination with reset
separation. The top-level output contains `p1_calibration_sweep_summary.json`
and `P1_AIRSIM_CALIBRATION_SWEEP_REPORT.md`, including single-secondary
coverage, network union coverage, detect-to-registration gap, cross-view
association count, gimbal pointing, and bbox size metrics. Main also asks D6
to scan the persisted sequence/episode artifacts and write
`d6_airsim_calibration/airsim_calibration_records.csv`,
`d6_airsim_calibration/airsim_calibration_summary.csv`,
`d6_airsim_calibration/airsim_calibration_summary.json`, and
`d6_airsim_calibration/airsim_calibration_report.md` for the standard
multi-seed reporting path.

Run the frozen P1 terminal-closure suite for comparable M5N2, real
`png_ttc`, and locked 1-5 frame detection dropout evidence:

```bash
python3 research_modules/airsim_runtime/run_blocks_sequence.py \
  --p1-terminal-closure-sweep \
  --sequence-id p1_terminal_closure_001 \
  --batch-seeds 1,2,3,4,5,6,7,8,9,10 \
  --p1-dropout-frames 1,2,3,4,5 \
  --p1-controlled-ttc-disturbances bbox_area_jump,bbox_clipping \
  --control-dt 0.1 \
  --no-lidar \
  --blocks-arg=-windowed \
  --blocks-arg=-ResX=640 \
  --blocks-arg=-ResY=480 \
  --blocks-arg=-NoVSync \
  --blocks-arg=-NoHMD \
  --blocks-arg=-NoSound
```

The version-4 suite adds two post-lock `png_ttc` cases per seed. Main freezes
the current D3 binding, then injects one bbox area jump or edge clipping into
the D7 observation after D5 has produced a locked association. Each injected
sample must persist the planned disturbance, expected and assigned
`global_track_id`, TTC rejection, effective control state, and executed law.
The acceptance row passes only when D7 reports the expected rejection, blocks
effective visual control, falls back to `radar_pn`, and preserves identity.
This hook does not change the PNG, LOS-filter, extrapolation, D3/D4/D5 gate, or
assignment logic.

Run only the two controlled cases when checking this boundary:

```bash
python3 research_modules/airsim_runtime/run_blocks_sequence.py \
  --p1-terminal-closure-sweep \
  --p1-terminal-closure-controlled-ttc-only \
  --sequence-id p1_terminal_controlled_ttc_seed001 \
  --batch-seeds 1 \
  --no-lidar
```

The M5N2 baseline/candidate cases use the same `z=-30 m`, 35-second
high-clearance geometry. Real `png_ttc` and the dropout matrix use tuned 2v2
camera settings at `z=-5 m` so SimpleFlight can settle at the requested global
NED altitude before horizontal control; dropout starts at 0.8 seconds,
after the stable-lock warm-up and before the usual 5 m intercept. The two
settings families use separate Blocks launches and reset-separated cases. The suite writes
`p1_terminal_closure_summary.json`, `p1_terminal_closure_rows.csv`, and a
Chinese Markdown execution report without saving PNG screenshots.

Run the first controlled 2v2 intercept. Main still launches Blocks once and
resets between episodes; the first five episodes stay read-only/replay, and the
last episode arms `Interceptor1/2`, takes off, and sends D7 PN velocity commands:

```bash
python3 research_modules/airsim_runtime/run_blocks_sequence.py \
  --actor-2v2 \
  --execute-intercept \
  --sequence-id blocks_2v2_actor_intercept_001 \
  --duration 8.0 \
  --dt 0.2 \
  --control-dt 0.1 \
  --intercept-speed 6.0 \
  --intercept-altitude-z -5.0 \
  --intercept-radius 5.0 \
  --intercept-detection-timeout 5.0 \
  --blocks-arg=-windowed \
  --blocks-arg=-ResX=640 \
  --blocks-arg=-ResY=480 \
  --blocks-arg=-NoVSync \
  --blocks-arg=-NoHMD \
  --blocks-arg=-NoSound
```

Run the controlled 5v5 intercept. This uses five SimpleFlight interceptors
(`Interceptor1..5`) from
`settings/blocks_5v5_actor_tuned_settings.json` and five moved actor targets
(`MSM_TargetActor_1..5`). The target actor asset defaults to the Blocks AirSim
drone mesh `Quadrotor1`, which matches the YOLO UAV detector path better than
the old cube actor. The D7 midcourse law is radar PN; terminal visual PNG is
only entered after the per-pair D3/D4/D5 contract and camera/LOS/maneuver gates
pass:

```bash
python3 research_modules/airsim_runtime/run_blocks_sequence.py \
  --actor-5v5 \
  --execute-intercept \
  --sequence-id p1_5v5_intercept_20260703 \
  --duration 8.0 \
  --dt 0.2 \
  --control-dt 0.1 \
  --intercept-speed 6.0 \
  --intercept-altitude-z -5.0 \
  --intercept-radius 5.0 \
  --intercept-terminal-range 8.0 \
  --intercept-detection-timeout 5.0 \
  --intercept-yaw-mode look_at_target \
  --actor-target-distance 20.0 \
  --actor-target-speed-scale 0.25 \
  --target-scale-m 2.0 \
  --blocks-arg=-windowed \
  --blocks-arg=-ResX=640 \
  --blocks-arg=-ResY=480 \
  --blocks-arg=-NoVSync \
  --blocks-arg=-NoHMD \
  --blocks-arg=-NoSound
```

The 5v5 run writes `P1_5V5_INTERCEPT_AIRSIM_REPORT_20260703.md` in the
sequence output directory. Each pair owns an independent D7 visual filter; do
not share terminal PNG state across interceptors.

`--intercept-radius` is a NED three-dimensional Euclidean threshold and is
inclusive; the default `5.0m` produces `range_intercept`, while an assigned
collision remains `collision_intercept`. The detection timeout now applies to
initial terminal acquisition only. After a valid visual handoff, D7 handles a
brief loss with image-KF prediction and bounded command coast; expiry is logged
as `terminal_visual_lost_after_coast`. The example uses `-5m` NED altitude to
keep the intercept path above Blocks scene obstacles; read-only actor runs
still default to `-2m`.

Default sequence order:

```text
episode_001_d1_sensor -> reset
episode_002_d2_association -> reset
episode_003_d3_assignment -> reset
episode_004_d5_terminal -> reset
episode_005_d4_degradation -> reset
episode_006_full_flow
```

## Main Episode Bus

Every Blocks smoke episode now also runs the main-owned episode bus on the
captured `AirSimFrame[]`. This is additive to the older `integrated_replay`:
the bus consumes the same real AirSim frames and writes one D6-compatible
episode log that keeps the D1-D7 runtime state together:

```text
AirSimFrame
-> D1 SensorObservation / GlobalTrack
-> D2 associated tracks, id_switch_count, continuity
-> D3 AssignmentPlan, version, AssignmentGuidanceBinding
-> D5 TerminalAssociation and cross-view terminal observations
-> D4 active/passive degradation decision events
-> D7 PN/PNG guidance records and terminal contract gate state
-> D6 MetricsCollector JSONL
```

The output directory contains:

- `main_episode_bus/main_episode_bus.jsonl`: D6 records with
  `truth_summary`, `track`, `assignment`, `event`, `link`, and `terminal`.
- `main_episode_bus/main_episode_bus_ticks.jsonl`: per-frame D1-D7 debug
  snapshots, including D1 timestamps/covariance, D2 ID metrics, D3 plan
  version, D4 actions, D5 decision states, and D7 gate rejects.
- `main_episode_bus/stage_timings.jsonl`: availability-aware per-frame main-bus
  stage timings (`main-stage-timing-v1`) for communication, D1, D2, D6 track
  recording, D3, coalition commit, D5, D4, D7, and link/cross-view recording.
  A stage that did not run is `not_applicable` with a null duration, not zero.
- `main_episode_bus/d3_plan_history.json`: ordered canonical D3 planning-tick
  records with assignments, primary/reserve activation, coalition
  version/epoch, owner/lease, hysteresis, feedback classification, and costs.
  Non-planning frames do not duplicate this history, and online truth fields
  are excluded.
- `main_episode_bus/main_episode_bus_metrics.json`: D6 episode metrics from
  the bus records.
- `main_episode_bus/main_episode_bus_summary.json`: final module summaries and
  record counts.

SimpleFlight control episodes additionally write `control_tick_timings.jsonl`
with `control-tick-stage-timing-v1`. It separates AirSim frame sampling,
main-bus processing, control-evidence/pair synchronization, and guidance plus
control RPC from the enclosing control tick. Both timing contracts use the
monotonic `perf_counter` clock, retain partial timing on errors, record the
configured budget and unattributed residual, and never feed timing values back
into D1-D7 decisions. Legacy outputs without these files remain unavailable
for stage-level analysis instead of being reconstructed from total latency.

`airsim_blocks_summary.json` includes the same paths and `main_episode_bus`
metadata. Online D5 association in this bus uses geometric detection data only;
AirSim object IDs are carried only as offline scoring labels.

Generate the availability-aware D6 churn report directly from one episode:

```bash
python3 research_modules/d6_evaluation_metrics/scripts/run_p1_system_evidence_report.py \
  --d3-plan-history /path/to/main_episode_bus/d3_plan_history.json \
  --output-dir /path/to/d6_d3_history_report
```

The report rejects duplicate or non-monotonic sequence indices, timestamp
regression, wrapper/record schema mismatch, and histories shorter than two
planning ticks. Rejected evidence remains `unavailable`; it is never converted
to zero churn.

Use `--no-launch` when Blocks is already running with compatible settings.
By default the launcher adds `-windowed -ResX=640 -ResY=480 -NoVSync` and
NVIDIA PRIME offload environment variables to reduce first-run rendering risk.
The smoke client defaults to AirSim `VehicleClient`, matching the official
camera/LiDAR examples for read-only sensing. `--execute-intercept`
automatically switches the runtime client to AirSim `MultirotorClient`.

The bundled settings use `VehicleType: SimpleFlight`, `ViewMode: NoDisplay`,
`DefaultVehicleState: Inactive`, ground-level `Z: 0`, enabled collisions, and
disabled collision passthrough. This prevents multirotors from falling before
the smoke test has an RPC connection and keeps the main render path light.
Control episodes should explicitly request API control, arm, take off, and
command hover or motion at the start of each episode instead of starting airborne.
For D1-D5 ComputerVision replay, use
`settings/blocks_cv_5v5_settings.json`; those vehicles have no physics, gravity,
LiDAR, arming, or collision behavior.

Outputs are written under
`research_modules/airsim_runtime/outputs/<sequence-id>/<episode-id>/`,
including `airsim_blocks_summary.json`, raw frame JSONL, camera metadata, Blocks
stdout/stderr, `blocks_sensor_observations.jsonl` D1 replay inputs, integrated
replay metrics, main episode bus JSONL/ticks/metrics/summary, and for controlled episodes:
`intercept_summary.json`, `control_commands.csv`, and
`airsim_3d_intercept_trajectories.png`.
`control_commands.csv` includes D7 `guidance_law`, terminal handoff state,
camera/LOS/maneuver gate booleans, `terminal_switch_reject_reason`,
`terminal_contract_reject_reason`, D4/D5 state fields, and plan/version
metadata. Terminal contract rejects are logged as explicit D7 states such as
`hold`, `reacquire`, or `abort_revoke` where possible.
Camera PNG screenshots are omitted unless `--save-images` is used.
For CV 5v5, the handoff from visual capture to D5 is metadata-only:
`blocks_frames.jsonl` stores per-camera image status, camera pose, detection
bbox, local track id, actor/object id for offline truth evaluation, and
timestamps. D5 consumes the bbox metadata and never rewrites D2/D3
`global_track_id`.

## Radar-Direct Midcourse Policy

Normal ComputerVision episodes keep the current center-owned D3 plan unless a
real hard invalidation, center failure, or an explicit stress option is
present. Main publishes `terminal_evidence_applicable=false` while the assigned
resource remains outside `intercept_terminal_switch_range_m`. D4 then records
ordinary D1/D2/D3 soft risk without requesting secondary visual assistance;
stale or infeasible plans, observed ID switches/duplicate tracks, friend
conflict, duplicate terminal lock, and explicit resource/track mismatches keep
their existing fail-closed behavior. D7 remains on radar PN until the normal
D5 terminal contract is applicable and passes.

`--cv-reassignment-time` is reserved for a deliberate camera/association
stress injection. Once its timestamp is reached, the runtime overrides the
live D3/D2 camera pointing command with the configured reassignment geometry
and labels it `explicit_reassignment_stress`. Omitting the option preserves the
live center binding for the complete episode.

The 2026-07-13 real AirSim validation report and evidence are at:

- `subagent_reviews/MAIN_RADAR_DIRECT_ASSIGNMENT_AIRSIM_VALIDATION_REPORT_20260713.md`
- `research_modules/airsim_runtime/outputs/radar_direct_2v2_far_policy_v2_20260713/`
- `research_modules/airsim_runtime/outputs/radar_direct_5v5_yolo_bytetrack_20260713/`
- `research_modules/airsim_runtime/outputs/explicit_cv_reassignment_stress_5v5_v2_20260713/`

## P1 Cooperative Closure V2

`--p1-cooperative-closure-sweep` preserves the frozen terminal-closure v1
suite and creates a separate `p1-cooperative-closure-v2` evidence bundle. Main
first runs the D3 27-profile grid through D7's offline 2D point-mass model,
then promotes three profiles using the fixed safety/coalition/pair/arrival
ordering. Baseline and candidates run as M5N2 SimpleFlight episodes with
`2 primary + 1 reserve`, 35 s duration, NED `z=-30 m`, AirSim detect, PNG-VM,
and the 5 m physical success rule. Soft prediction and trend coast remain off.

Candidate initial sectors are applied after every reset with
`simSetVehiclePose`; reset alone does not reload a new settings file. The
stored frames therefore contain the actual candidate positions rather than
metadata-only geometry. Outputs include the point-mass screen, pair funnel,
pair/target/coalition summary, D4 six-case communication replay, and D6
Chinese report bundle.

For D1/D2 dense-crossing calibration, first collect real CV 5-target episodes,
then pass their full-flow directories to `run_p1_identity_pipeline.py` using
repeated `--episode SEED=PATH`. Main joins frame truth with anonymous sensor
observations, D1 writes truth-isolated governed replay and evaluator-only truth
sidecars, D2 runs the fixed 54-profile 10/20-seed matrix, and D6 produces the
availability-aware identity report. Fewer than 10/20 unique seeds remain
explicitly unavailable and do not promote a candidate.

The current cooperative terminal policy is `per_primary` with arrival-time
coordination disabled. Each active primary must independently pass its own
D3/D4/D5/camera/maneuver gates and is scored against the 5 m NED success
radius. The standby reserve cannot switch until a newer plan explicitly
activates it. D4 atomic ACK/epoch/lease checks remain mandatory after center
loss; a pending, partitioned, or ownerless episode communication state blocks
visual PNG.

Native MOT calibration is available as a separate, non-promoting sweep:

```bash
python3 research_modules/airsim_runtime/run_blocks_sequence.py \
  --p1-mot-calibration-sweep \
  --sequence-id p1_native_mot \
  --yolo-weights research_modules/d5_terminal_association/best.pt
```

Main runs 18 reset-separated single-camera screening cases for ByteTrack and
BoT-SORT at confidence 0.1/0.2/0.3 and range 20/30/50 m, then runs 10 seeds of
two-camera confirmation per selected backend. Cameras use 1920x1080, 90 deg
FOV. IoU fallback is disabled and cannot pass admission. AirSim truth boxes
and actor identity are fetched only after each online result and are consumed
only by D5/D6 offline scoring. Outputs include the execution index, Chinese
Markdown report, and D6 CSV/JSON/PNG report bundle.

For D2 identity calibration, pass nominal 4 m captures with `--episode` and
tight 2 m captures with `--tight-episode`:

```bash
python3 research_modules/airsim_runtime/run_p1_identity_pipeline.py \
  --episode 7=/path/to/nominal_seed007/episode_006_full_flow \
  --tight-episode 7=/path/to/tight_seed007/episode_006_full_flow \
  --output-dir /path/to/p1_identity
```

D1 first freezes both geometries. D2 then creates deterministic, truth-free
dropout, clutter, delayed/noisy, and combined governed replays. Tight geometry
is never synthesized: `tight_crossing` and `combined` require a declared
approximately 2 m AirSim capture. Screening and confirmation require 10 and 20
unique seeds per difficulty profile.

## AirSim Docs And Source Findings

- `docs/settings.md` confirms `SimMode: Multirotor`, `ViewMode: NoDisplay`,
  NED vehicle `X/Y/Z`, per-vehicle `Sensors`, and `ApiServerPort`.
- AirSim source reads the RPC switch from `EnableRpc`; older docs also show
  `RpcEnabled`, so the bundled settings keep both keys for compatibility.
- `docs/simple_flight.md` states SimpleFlight vehicles start armed by default.
  The smoke settings therefore use `DefaultVehicleState: Inactive` and `Z: 0`
  so vehicles do not immediately fall before any control episode starts.
- `docs/multi_vehicle.md` and `PythonClient/multirotor/multi_agent_drone.py`
  show multi-drone settings and per-call `vehicle_name` usage.
- `PythonClient/airsim/client.py` documents that `simGetVehiclePose()` returns
  pose in each vehicle's starting-point frame. The runtime adapter therefore
  adds the settings `X/Y/Z` start offset back into truth/resource positions
  before emitting global NED records.
- `docs/object_detection.md` and `PythonClient/detection/detection.py` show
  `simSetDetectionFilterRadius`, `simAddDetectionFilterMeshName`, and
  `simGetDetections` for per-camera object detection. The runtime can instead
  use D5 YOLOv8 + MOT when `--detection-backend yolo` is selected.
- `PythonClient/environment/create_objects.py` shows `simSpawnObject`, and
  `PythonClient/computer_vision/objects.py` shows `simSetObjectPose` for Blocks
  actors such as `OrangeBall` and `PulsingCone`.
- `docs/lidar.md` and the LiDAR Python examples show that LiDAR is disabled
  unless configured under vehicle `Sensors`, and readback uses `getLidarData`.
- `docs/image_apis.md` and `PythonClient/computer_vision/cv_mode.py` show a
  `ComputerVision` mode that can isolate RPC/camera startup from multirotor
  physics. Use `settings/blocks_cv_rpc_settings.json` for that diagnostic.
- `SimHUD.cpp` calls `initializeSettings()`, `loadLevel()`, `createSimMode()`,
  `createMainWidget()`, `setupInputBindings()`, then `simmode_->startApiServer()`.
  If logs show vehicle creation and engine initialization but no listening RPC
  port, the next suspect is this late API-server startup path.

## Diagnostics

If RPC does not become ready, the launcher now writes:

- `blocks_stdout_stderr.log`: raw Blocks output.
- `blocks_diagnostics.json`: parsed settings path, command-line settings check,
  game mode, engine initialization, vehicle log hits, OpenXR/HMD counts, RPC
  start errors, and local TCP port status.

Useful launch variants while debugging the current packaged Blocks binary:

```bash
python3 research_modules/airsim_runtime/run_blocks_smoke.py \
  --episode-id blocks_minimal_nodisplay_001 \
  --duration 0 \
  --settings research_modules/airsim_runtime/settings/blocks_minimal_settings.json \
  --no-integrated-pipeline \
  --blocks-arg=-windowed \
  --blocks-arg=-ResX=640 \
  --blocks-arg=-ResY=480 \
  --blocks-arg=-NoVSync \
  --blocks-arg=-NoHMD \
  --blocks-arg=-NoSound
```

```bash
python3 research_modules/airsim_runtime/run_blocks_smoke.py \
  --episode-id blocks_cv_rpc_001 \
  --duration 0 \
  --settings research_modules/airsim_runtime/settings/blocks_cv_rpc_settings.json \
  --camera-vehicle-name "" \
  --target-vehicles "" \
  --resource-vehicles "" \
  --no-integrated-pipeline \
  --blocks-arg=-windowed \
  --blocks-arg=-ResX=640 \
  --blocks-arg=-ResY=480 \
  --blocks-arg=-NoVSync \
  --blocks-arg=-NoHMD \
  --blocks-arg=-NoSound
```
