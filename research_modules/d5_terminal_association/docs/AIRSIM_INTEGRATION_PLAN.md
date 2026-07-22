# AirSim 离线集成计划

## 2026-07-22 paired shadow v2 与 AirSim 边界

D5 已完成 20 seed、45 cell、900 帧的离线合成同图 paired shadow v2。该执行没有启动 AirSim，
没有读取 AirSim 图像或 detection truth ID，也没有修改 launcher、settings、相机分辨率、视场角、
外参、detector、MOT、actor、reset 顺序或云台命令。结果只验证冻结匿名 tracklet 图上的规则/模型
评分差异。

v2 模型边级和簇对级 F1 均为 1.0，但后验审查显示尺度差、尺度变化率差和角速度差对合成标签接近
确定性可分；`shared_global_track_count=1` 没有样本。因此 paired shadow 软件与冻结合成证据已完成，
真实 AirSim 多相机泛化仍开放。下一轮 AirSim 代表性子场景应保存匿名 camera-local tracklet、双
时间戳、外参和像素协方差，保持 actor/object truth 只进入 D6 离线评分，并复用冻结模型与阈值做
同图 shadow。

D6 独立审计和真实多相机困难回放前，`G1=false`、`assist=false`、`authority=false`、
`rule_fallback=true`。本次 v2 不能替代 M5N2 第二 primary、二级侦察覆盖、真实检测/MOT、视觉 PNG
接管或物理拦截验收。

当前最终源码已通过 paired-shadow 专项 5 项和 D5 全量 534 项测试；这些测试没有启动 AirSim，
不能计入真实相机或运行时验收。

## 2026-07-21 Supplemental curriculum B1b2 与 AirSim 边界

B1b2 新增的是 D5 离线 synthetic curriculum producer 和 CLI，没有修改 AirSim launcher、settings、
reset/episode order、detector、actor target、真实云台或 runtime ACK DTO。producer 内的
applied/rejected/missing 来自 `DeterministicCameraCommandExecutor` 故障注入，每 seed `4/4/4`，
只用于接口覆盖；不得写成 AirSim 或硬件 ACK 分布，也不得由此推导可见率、重捕获、关联或拦截收益。

main 已在 AirSim 之外、detached clean worktree
`13e37286d2996a227924bb1a8e2766e52116a534` 使用正式 training/shared registry 调用 CLI。ignored
output 与 tracked JSON/中文 Markdown 均位于受保护 source root 之外；正式 900-episode 输入树前后
SHA 同为 `8ffbe5cf044d121163c8acc3dce1bbd54e14bb6b211b8e1cf440f24c93294fca`。实际 100/800/1200 与
canonical `60/20/20` 已通过 clean producer 审计，因此该生成证据不再开放。

本次仍没有启动 AirSim，没有 AirSim 运行场景、图像、真实云台 ACK 或执行后 outcome。制品内
applied/rejected/missing `400/400/400` 仅为 executor 故障注入；真实 AirSim requested action、ACK、
reward/counterfactual/causal evaluator label 仍须按既有 online/offline 分流合同采集。2026-07-21
supplemental BC 全样本审计已按 100 episode/1200 sample、302/302 文件 SHA、1200/1200 有限特征和
零违规阈值通过，内容 SHA 为
`a11b65596a4c416deba6d0cb35dcc0c32342a5bae0481291d43e8de0e26550dd`；该离线证据没有运行 AirSim，
不能替代真实 ACK/outcome。D5 后续已完成 2026-07-22 权威 v2 paired shadow；下一步由 D6 独立审计
该制品并建设真实 runtime shadow 数据。离线合成 paired 通过不开放 assist/PPO/online/camera
authority，规则回退仍为必需路径。

## 2026-07-20 主动视觉 episode dataset 接线边界

D5 已完成整 episode writer/loader/audit 代码，但本轮没有修改 main runtime。main 后续应在每个
统一三维主动视觉 decision 后，用 `active_vision_sample_from_decision()` 保存 truth-free snapshot、
规则示范、requested/effective action、三个版本和相机反馈；有 `runtime.camera_command_ack` 时
附加 `ActiveVisionRuntimeAckV1`，没有 ACK 时保持 null，不伪造 accepted。

episode 结束后先调用 `stage_active_vision_episode_record()` 写 `online/`，再从独立 evaluator
结果调用 `stage_active_vision_offline_labels()` 写 `offline/`。main 不得把 actor/object/truth
identity、AirSim detection object identity 或 world snapshot 合并进 online record。offline join
只使用 `sample_key + observation_key`；reward/outcome/counterfactual/causal label 不得回流下一
episode snapshot、相机命令或关联路径。

source identity 必须来自实际 episode：完整 Git commit、dirty 状态和实际 runtime/settings config
SHA256。收齐数据后由 `finalize_active_vision_episode_dataset()` 按完整 `(scenario_version, seed)`
group 切分，并把共享同一数值 seed 的所有 scenario/scale group 原子放入同一 split；正式运行
保留默认 minimum 20 unseen seeds。少于三个唯一 seed、test unseen seed 不足、seed 跨 split 或
任一 hash/join/ID 审计失败时不得生成可训练 dataset。落盘语义使用 episode dataset v3、
record/descriptor/sample v2，后续训练 bundle 使用 v4；snapshot/action/feedback/ACK/offline-label
保持 v1。旧 v1 嵌套 record 不兼容读取。

finalize 现在逐 episode 流式检查一次 online record/offline join，并在处理完当前 episode 后释放
对象；最终结构复核在文件指纹不变时复用同一调用内的 stream/SHA 证据。公开 audit 每次仍独立
读盘、复算全部 SHA256 并逐 episode 检查，不接受 finalize 内存证据。不再调用
`load_active_vision_episode_dataset()` 累积全部 episode。正式训练应使用
`load_active_vision_episode_dataset_lazy()` 及其 split/BC/PPO iterator；兼容全量 loader 只用于
明确有界的小数据。该 API 变化不改变 v3 磁盘合同，故不再升版。

record loader 还强制 mode/action 一致：shadow、disabled 和 assist fallback 只能保留规则 effective
action，不能把模型请求伪装成已执行动作。dataset root 可使用相对或绝对路径；该修正不改变
launcher/reset/episode order，也不形成新的 AirSim 执行证据。

main 已用新格式完成 nominal seed 91、每档 2 s 容量复测：5/20/50/100/200v200 总制品约
`0.086/0.295/0.733/1.543/2.884 MB`；200v200 online/offline `1.064/1.818 MB`、`3536` samples、
RSS约 `1.04 GB`、online truth=0。该结果关闭单 episode 去重容量门，不关闭约 900 episode corpus
的 finalize/训练峰值与吞吐验收。D5 数据管线 `16 passed`、全量
`398 passed in 15.75s`；6-episode 计数确认 finalize 每 episode 一次 stream/offline parse、每制品
一次 SHA256，独立 audit 另做完整一轮。该变化只影响离线数据处理开销，不改变 AirSim 相机、
detector、云台命令、reset 或 episode order。
本轮 D5 未修改 launcher/reset/episode order；没有新增 AirSim 云台、正式 BC/PPO、20-seed 性能
或 assist 准入结论。

## 2026-07-20 主动视觉 v1 统一三维接线与 AirSim 后续工作

D5 已提供 `ActiveVisionSnapshotV1 -> ActiveVisionDecisionV1`，main-owned
`scalable_3d_simulation` 已在每个统一三维 decision tick 注入：当前中心 GlobalTrack 候选、
AssignmentPlan/coalition version、recon/interceptor 模拟相机的 yaw/pitch/FOV 和最近接受版本、
候选 projection covariance、visibility/occlusion/freshness、communication version 与友方
exclusive observation reservation。输入不含 actor/object/truth identity。

main 只执行 `effective_action`，并持久化 requested/effective mode、rule/requested/effective action、
fallback reason、inference latency、model fingerprint 和 plan/coalition/communication version。
库默认 disabled；CLI 默认 shadow。shadow 必须继续执行规则动作，不发送模型动作。assist 在
没有绑定同一模型和 dataset SHA 的正式 20-unseen-seed paired non-degradation 报告前不得启用。
当前仓库没有正式主动视觉 checkpoint。

统一三维 runtime 已将 `effective_action` 转成版本化相机/FOV 命令，对 plan/coalition/
communication version、有效期和资源一致性复核后，在下一视觉帧应用并发布
`runtime.camera_command_ack`。D5 动作只有 observe/search/hold/reacquire、有限 yaw/pitch 和
wide/zoom，不得转换成飞行控制或 D3 重分配。D5 safety projection 与 runtime actuator gate
同时保留；任一拒绝都执行规则观察策略。

开发冒烟中，5v5 命令 `84/84` applied，200v200 seed 17、1.2 s 命令 `1872/1872` applied。
这些是单 seed、脏工作树下的模拟接口证据。真实 AirSim 云台、硬件速率/ACK、reset、传输时延
和实机执行仍需后续接线与验证，不能由上述计数推导主动视觉收益。

在线 `SensorMeasurement.observation_id` 现在由 D5 只读导出为 `source_observation_id ->
tracklet_key` 审计连接。main 应在 episode 内保存该 truth-free link，episode 结束后再与独立
`OfflineTruthLabel(observation_id -> truth_entity_id)` 合并并调用
`join_offline_observation_labels()`。offline label 不得回流在线 graph/policy；假目标无标签时必须
保持 labels incomplete。同帧同 observation 多 tracklet 会由 D5 拒绝。

D5-owned 接口开发阶段没有启动 AirSim，也没有修改 settings、detector、actor 或 handoff。
2026-07-20 主动视觉专项 `17 passed`、D5 全量 `376 passed in 9.94s`。随后完成的统一三维模拟
接线仍不是 AirSim 执行或性能证据。

## 2026-07-20 稀疏 tracklet 图接线状态

D5 已实现匿名稀疏图、相机视锥/时间/空间桶索引、相机对与 tracklet 候选预算、原生 PyTorch
边评分、受约束聚类、中心 Hungarian binding、camera-only 主动视觉接口及
`scalable_3d_adapter.py` 模块入口。本轮没有启动或修改 AirSim，也没有改变
`settings.json`、CameraDefaults、分辨率、视场角、外参来源、默认 AirSim detect/几何注册或
`TerminalAssociator`。

新增 adapter 已用真实 `OnlineSensorBatch`/`SensorMeasurement` 类型形状做合成输入测试，
main scalable module stack 已调用它。运行时必须把 bus payload 原样交给 adapter，不得把同批
evaluator labels 或 world snapshot 合并；camera pose covariance 应显式放入 metadata。若当前
DTO 缺少 covariance，D5 只使用带 provenance 的 configured fallback。

后续 main 接线必须保持三路分离：

1. 在线 `vision_bbox` 及本地 MOT 只形成 camera-local tracklet，保留 measurement/arrival
   timestamp、像素协方差和 camera projection metadata；D5 入图构造器与递归 payload guard
   继续拒绝 truth/actor/object/global identity，并拒绝 `TGT-0001`、`TargetDrone_1` 等
   truth-like local ID；`cam01-track-0001` 等 camera-local sequence 保持合法。
2. 中心 GlobalTrack 作为只读投影输入；图模型只输出边概率，受约束聚类后才用 Hungarian
   引用中心 ID。任何未绑定簇保持 anonymous/unbound，不得生成 `global_track_id`。
3. `OfflineTruthLabel` 只路由到训练/评估进程，不能并入 tracklet、图特征、云台动作或
   online bus。困难负样本挖掘也必须在在线图已经冻结后执行。

主动视觉 v1 接线只允许 `observe_target/search_sector/hold/reacquire` camera intent，并在同一
action 中携带安全投影后的 yaw/pitch 增量和 wide/zoom。main-owned runtime 负责实际云台/FOV
命令、ACK、速率限制和 timeout；低置信或超时必须执行规则扫描。学习型策略当前未正式训练和
验收，不得替换规则 fallback。

进入真实 AirSim 前的最低门槛为：独立 train/validation/test split，多 seed 200v200 的边
precision/recall、ROC/PR 与校准误差，近邻交叉/遮挡/时延/外参漂移困难集，CPU/GPU P50/P95，
以及 online truth use 和 `global_track_id` rewrite 均为 0。本轮 seed 200 合成投影压力测试
为 800 节点/1923 最终边，本次约 `0.442 s`。5/20/50/100/200 相机结构测试已证明相机检查数
和 tracklet 候选度受预算约束；200 相机样本只检查 400/19900 个相机对。该结果不构成 AirSim
runtime 性能或模型准入。main 仍需把 `association.diagnostics` 持久化，并在真实 representative
子场景中评估预算召回、内存和 P50/P95；AirSim 不计划运行 200 路物理相机。

## 2026-07-16 独立 ComputerVision 5+1 专项接线结果

main 已完成真实 AirSim 接线：5 个 `1920x1080`、60 度局部相机，1 个
`3840x2160`、75 度侦察相机，5 个 `Quadrotor1` actor；两个 reset-separated
episode 各运行 12 秒、49 帧、seed 7。每个相机 batch 均按自己的
`measurement_timestamp` 投影，不使用最后一帧时间替代逐批量测时间。

AirSim detect 几何基线的召回/配准/稳定/联合覆盖/侦察全覆盖/IDSW =
`1.000/1.000/0.975/1.000/0.918/0`，通过全部门限。YOLOv8 + 原生 ByteTrack =
`0.622/0.996（严格 0.966）/0.955/1.000/0.878/25`，P50/P95 约
`10.42/12.37 ms`；召回、侦察全覆盖和 IDSW 未通过。两路 online truth use 和
`global_track_id` rewrite 均为 0。

验收门限为 detect/YOLO 召回 `>=0.95/>=0.90`、严格配准 `>=0.95`、稳定
`>=0.90`、联合覆盖 `>=0.95`、侦察全覆盖 `>=0.90`、IDSW `<=0/<=5`，
并要求 truth use/rewrite=0。接线结论是 detect 几何基线通过；YOLO+ByteTrack
继续作为 optional 分支，后续需改善召回、IDSW、侦察全覆盖并运行多 seed。
本单 seed 专项不触发默认后端或主线晋级，也不替换默认 D1-D7 episode 流程。

该隔离专项本身没有运行 D1/D2。main 读取 actor truth 运动学，合成带中心
`global_track_id` 的 `GlobalTrack` fixture，truth 另用于离线评分。这里的
`online_truth_identity_use=0` 只约束 D5 的 local bbox 到 fixture 关联代价、
Hungarian 选择和稳定窗口不读取 actor/object/truth identity，不能解释为整个专项
完全不读取 truth。

## 2026-07-15 M5N2 20-case 接线复核

main 已完成 M5N2 baseline/candidate 各 10 seeds。TERM 生效前额外完整生成一个 `png_ttc_2v2_seed001` 的 `intercept_summary.json`，但该 case 明确排除在本节 M5N2 证据之外；其余 tuned case 和 dropout case 均未执行。20 场 M5N2 `main_episode_bus_ticks.jsonl` 对第二 primary 的 decision 与 `d5_live_visual_funnel_v1.first_failure_stage/reason` 为 `3725/3725` available，actual execution artifact 与离线 5 m 物理结果均为 `20/20` available。在线 truth identity/state use 为 `0/0`。

当前接线仍缺少直接持久化的 `failure_category` envelope，不能从“代码已有分类器”推断本批 artifact 已包含分类字段。后续 main/D6 应从 D5 producer 原样落盘该字段和 availability，而不是在报告层把缺失值补为 unknown。第二 primary 应由 current active-primary 合同动态选择；本批 19 场为 `INT-03`，candidate seed 002 为 `INT-02`。

实测 P1 重点已从“是否有 D5 记录”收敛到“证据能否连续到达交接门”：measured bbox `2516/3725`、visual fresh `2657/3725`、bbox stable/handoff-ready `161/3725`、strict complete `52/3725`。第二 primary 5 m `0/20`、coalition completion `0/20`。下一次 AirSim 运行前应冻结成员合同或按成员变化分层报告，并分别校准 bbox 尺度/连续性、候选唯一性、重获取几何和量测 freshness；不得使用 truth ID 修正在线结果。

20 个第二 primary 最终均以 `collision_stop` 停控，但该字段属于 D7 控制结果证据；当前输出未持久化碰撞对象，不能区分成员冲突、环境碰撞或 AirSim 状态问题，也不能将 `0/20` 单独归因于 D5。后续 runtime 应在不引入在线 truth 身份的前提下补充 collision object/category 的离线诊断字段。

## 2026-07-15 下一轮第二 primary 诊断接线

下一轮真实 2v2/M5N2 多 seed 应直接持久化 `CooperativeVisualFunnelSummary.to_dict()` 新增的 `failure_category_counts` 与 `second_primary_failure_category_counts`，无需运行时新增 D5 DTO。每个 seed 应同时保存逐资源 `first_failure_stage/reject_reason/failure_category`、双时间戳、plan/version、friend/duplicate、bbox edge、online truth use 和 global-ID rewrite 计数。

验收要求：至少 10 seeds；每个 active primary 快照恰有一个类别；错误 assigned-global-ID 必须计入合同不一致而非 visibility；online truth use/global ID rewrite 为 0；分类总数与 active-primary 分母一致。2026-07-15 代码级 11-case 专项和 D5 全量 `272 passed`，但未启动 AirSim，因此类别分布、第二 primary 5 m/联盟完成和 detector/MOT 性能仍未验收。

## 2026-07-14 actual-v2 接线证据与开放验收

main 已用同一套持久化 actual-execution schema 跑通两个真实 AirSim seed-1 case，默认检测均为 AirSim detect：

| case | canonical actual 末端证据 | 物理结果 | 判读 |
|---|---|---|---|
| tuned 2v2 | lock acquisition `3`；visual control `26`；visual/mode switch `2/2` | pair/target `2/2` | 单 seed 已发生真实末端切换，不代表完整多 seed P1 |
| M5N2 | lock acquisition `24`；visual control/visual switch/mode switch `0/0/0` | pair `2/3`；target `2/2`；coalition `0/1`；第二 primary 约 `11.02 m` | 有 lock acquisition，但视觉接管与联盟完成未闭合 |

canonical actual 的 `terminal_switch_allowed_count` 已从最终 `control_commands.csv` 独立统计并注册同名 envelope，2v2/M5N2 为 `26/0`；它不由 `control_allowed_count` 推断。两 case 五层 contract/control/terminal-switch/mode/physical 总计为 `102/26/26/2/4`，状态均为 available。

两 case 的 online identity/state truth use 为 `0/0`。runtime 必须继续把 actor/object truth 保留在离线 scorer，在线 D5 只消费匿名 camera-local detection 和中心既有 `global_track_id`；任何 consumer 均不得据此改写或换绑全局 ID。YOLO/native-MOT 未晋级，默认仍为 AirSim detect。

本批 actual artifact 与五层 schema 可用性 `2/2` 达到 P0 证据门，但 D6 formal overall status=`fail`。下一 P1 AirSim 验收聚焦 M5N2 第二 primary、真实几何 drift、detect/YOLO/MOT 多 seed 和二级证据同一 decision tick freshness；五层 schema 与 main 接线不再开放。IBVS、真实身份源、完整在线 PnP/ROS 2 保持 P2/P3。M5N2 既有视觉完成接受阈值仍至少 `8/10`，与 physical coalition `0/1` 分母独立。本节不要求修改 D5 代码或保存 PNG。

## 2026-07-14 postbatch DTO 接口状态与后续验证

D5 代码级 producer DTO 已闭合：main 可从 `local_visual_evidence` 或 `d7_handoff_input` 取得同一资源相机的 `bbox_xyxy`、`center_px`、resource/camera/stream/backend、双时间戳和 measured/stability 状态。必须同时检查 `d7_handoff_input_ready=true` 与 `execution_lock_allowed=true`；不能仅以 `decision_state="locked"` 解释为视觉控制许可，也不能用 cross-view/predicted 历史填充当前本机 bbox。

最新 postbatch seed-1 中，baseline/candidate 分别有 `330/311` 条控制记录和 `151/120` 条 D5 几何 locked，但两组都只有 INT-03 在控制阶段保留 `40` 条非零 bbox；active pair 在约 `23-29 m` 因 acquisition timeout 退出。baseline 的最大控制 bbox 面积比约 `2.4943e-4`，仍低于当前 `8e-4` 门。该现象不是 camera scope 串线：作用域分别为 `InterceptorN:0`。main 后续应在不保存截图的正常批量运行中记录每资源 detection last-seen、进入 30 m 时的当前 bbox、相机分辨率/FOV、异常大框来源和至少 10 seeds 分布。

本轮没有新 AirSim episode；2026-07-14 D5 全量 `261 passed`。真实持续 detection、bbox 尺度和异常框治理继续为 P1，不能通过降低既有门限解决。

## 2026-07-14 live funnel 接线要求

semantics_v2 M5N2 seed-1 已证明 live detect 与 raw lock 可到达 INT-02，但旧 runtime 输出把后续失败压缩为 `d5_not_locked`。main 应逐帧持久化 `TerminalAssociation.to_runtime_record()` 的 `d5_live_visual_funnel` 及顶层 `visual_match_decision_state`、`execution_gate_pass/reason`、`measured_lock_streak_count`、`measured_stable_lock`、`bbox_stable`、`handoff_recommended` 和首断点字段。postbatch 已证明当前 local track 可路由到 D7；当资源末端阶段没有当前 measured bbox 时必须保持空值，不能用历史或 peer bbox 补齐。

该历史 seed-1 的窗口在 `2.2 s` 结束，而 INT-02 bbox 在约 `19 s` 才稳定。postbatch 已在 `arrival_coordination_required=false` 时取消共同到达窗口；显式协调模式仍必须定义统一时基，D5 对过期合同继续输出 `execution_contract/arrival_window_expired`。后续至少 10 seeds 验收必须同时检查 raw lock、execution lock、bbox stable、handoff 和 D7 consumption，而非只看最终拦截结果。

2026-07-14 D5 全量 `258 passed`，零失败；本任务没有启动新 AirSim。身份、friend、duplicate、timestamp、calibration、版本和 `global_track_id` 门控均未降低。

## 2026-07-14 bbox 历史 producer 接线合同

postfix seed-1 只读复核显示，M5N2 baseline/candidate 的 `bbox_stable=true` 均为 `0/1388`，2v2 PNG/TTC 为 `0/52`；旧记录全部 `visible_frame_count <= 1`。runtime 每 tick 只传当前 `scoped_local_tracks`，因此旧 stateless handoff 无法达到四帧稳定门限。D5 已在 associator 内维护 measured history，普通 plan refresh 不再清空；真实 membership、binding、local track、camera/backend/stream、producer reset 与 identity/friend/duplicate conflict 仍安全重置。

main 必须向 `TerminalAssociator.decide()` 传当前 executable/committed coalition 的 `committed_coalition_member_ids`，以及决策前已有的 `duplicate_terminal_lock_risk`。每条 `LocalVisualTrack`/调用上下文必须稳定保留 `camera_id`、`stream_id`、`detector_backend`、`tracker_backend`、`local_track_id`、`local_track_state`、`track_transition_state`、`track_reset_reason`、`mot_history_length`。AirSim builtin detection 可由 `detection_source` 映射稳定 backend；YOLO/MOT 必须显式提供 detector/tracker backend，缺失即 fail closed。共同视觉只使用 current committed active primary。

接线后的验收应检查 `bbox_history_length/CV/reset_reason/key/signature/evidence_source` 与 raw/effective MOT 字段，并重跑 M5N2/2v2；不得降低 N=4、CV=0.30、身份/duplicate/版本门限，不得改写 `global_track_id`。2026-07-14 D5 全量 `255 passed`，零失败；本轮未启动 AirSim，真实 acquisition、30/50 m recall 和至少 10 seeds native-MOT admission 仍开放。

## 2026-07-14 原生 MOT stream/episode 状态要求

main 必须为每路连续图像保持稳定的 `resource_id + camera_id`，不得跨相机复用同一 stream key。D5 现按该 stream、native backend 和 tracker ID 累计连续实测历史；空帧不切到 IoU fallback，而是保留 native backend 的空输出并中断 measured history。原生调用异常或返回有检测但无 tracker ID 时才进入 fallback，并使故障前 native history 失效。

AirSim reset-separated episode 之间必须调用 `YoloMotAdapter.reset_episode()`（兼容 `reset_all_streams()`）；单路相机重连可调用 `reset_stream(resource_id, camera_id)`。两类 reset 都会释放对应 native model、IoU tracker、active backend 和历史。2026-07-14 D5 Results-like 回归为 `241 passed`，但本批没有启动 AirSim、没有新增 seed 或真实图像结果；真实多 seed 准入、远距召回和计算预算仍按既有计划执行。

## 2026-07-14 runtime feedback 映射约束

AirSim/main runtime 不得把 D5 的任意非 `locked` 状态直接映射为 `resource_unavailable`。`ambiguous`、普通 `hold/reacquire`、geometry gate、bbox 或 measurement/arrival timestamp 不稳定只阻断当前 pair 的 visual PNG handoff，并保持 radar PN/重新检测等既有路径；可消费 `observe/request_secondary_cue`，但不得形成 D3 hard planner feedback。

只有 verified friend、spoof、duplicate lock、assignment authorization/version 或持续 local/global ID conflict 对应的 `conflict/inconsistent + report_conflict/arbitrate` 才可作为 hard feedback 候选。main 仍需结合 D3 plan version、D4 commit 和自身 resource health 做最终决定。D5 不生成 resource health，不改写 `global_track_id`，在线不读取 AirSim actor/object/truth ID。

2026-07-14 运行 D5 确定性专项 `52 passed` 和当时全量 `235 passed`，接受阈值为零失败和普通不确定性零 hard action；本日原生 MOT 历史修复后最新全量为 `241 passed`。未启动新的 AirSim Blocks episode，因此没有新增 seed、物理命中或资源故障证据。后续 main 集成验收应分别计数 soft visual reacquire 与 hard safety conflict，确认前者不会触发 resource removal。

## 范围

本计划只描述 AirSim 数据采集、离线回放和评估接入。不调用实机飞控、硬件驱动、武器/毁伤模型、自动处置接口，也不绕过人工授权。D5 模块只输出 `TerminalAssociation`，不改写中心维护的 `global_track_id`。

## 2026-07-13 最新实测基线

- M5N2 paired AirSim 已形成 `120` 条 active-primary 证据、`120` 条 visible 证据和 `74` 条 D5 关联/锁定证据；最佳 coalition completion 为 `5/10`。当前 P1 是第二 primary 的持续检测、稳定 bbox 和连续 measured lock，主要失败原因为 `d5_not_locked` 与 `terminal_detection_acquisition_timeout`。
- 原生 MOT 已完成 `18`-case 正式 screening：`1920x1080`、FOV `90`、距离 `20/30/50 m`、confidence `0.1/0.2/0.3`、ByteTrack/BoT-SORT。20 m native active rate/continuity 均为 `1.0`、IDSW 为 `0`、P95 约 `7.4/16.2 ms`；precision/recall 仅约 `0.26-0.33`，30/50 m 无检测。
- screening 准入候选为 `0`，two-camera confirmation 为 `0`。默认在线检测保持 AirSim `simGetDetections`，不得把 20 m tracker 连续性写成原生 MOT 已晋级。
- 2026-07-13 当日 D5 全量回归为 `232 passed`，2026-07-14 最新全量为 `241 passed`。开放 P1 为第二 primary 稳定锁定、bbox 口径/尺度/时间对齐、远距召回，以及候选通过 screening 后的多 seed confirmation。

## 数据来源

从 AirSim 场景离线采集：

- RGB 相机帧和时间戳。
- 相机内参 `K`、外参 `R, t`，或可转换为 `P_c = R P_w + t` 的位姿。
- 仿真对象世界坐标、速度、类别和中心系统生成的 `global_track_id`。
- 合作/友方对象的模拟 OpenDroneID 或任务标签消息。
- 可选：分割图、深度图、标注框，用于生成或校验本地检测输入。

## 坐标与投影

AirSim 采集层负责把仿真世界位姿转换为 D5 的 `CameraModel`：

```text
P_c = R_cw P_w + t_cw
p = K [R_cw | t_cw] P_w
```

如果使用 ROS 2/tf2，只在离线回放时提供坐标变换；D5 不订阅或发布控制指令。

## 本地视觉输入

两种离线输入模式：

- 标注模式：由 AirSim 真值投影和噪声模型生成 `LocalVisualTrack`，用于算法单元评估。
- 检测模式：将 AirSim RGB 帧送入本地检测器或 MOT，例如 ByteTrack、BoT-SORT、Deep SORT，再归一化为 `LocalVisualTrack`。

MOT 的 `local_track_id` 只作为本地观测 ID，不得替代或重写 `global_track_id`。

### 当前实际实现状态

当前 D5 已实现的是 AirSim ComputerVision bbox dry-run adapter、相机几何离线验证辅助、detect-to-global-track registration helper 和可选 YOLO/MOT frame adapter：

- 已接入：`simGetDetections` 风格 `box2D/bbox_xyxy/xyxy` schema 转 `LocalVisualTrack`，`TerminalObservationBus` 汇总多相机观测，`TerminalCrossViewFusion` 输出 metadata-only peer evidence。
- 已接入：`register_local_visual_tracks_to_global_tracks()` 按 `GlobalTrack[]`、D2/D3 binding/`Assignment`、每相机 `CameraModel(K/R/t)`、timestamp、像素协方差和 `LocalVisualTrack[]` 做像素马氏门控 + Hungarian/确定性唯一匹配，输出 registration candidate、`TerminalObservation`、即时 `CrossViewAssociation` 和稳定 `stable_cross_view_associations`。candidate/observation metadata 携带 `pixel_error_px`、`mahalanobis_d2`、`gate_pass`、`projection_valid`、`camera_pose_source`、`bbox_area_px`、`offline_truth_global_id` 和 3 帧 2 次通过的稳定窗口字段；truth/actor ID 只作为离线 metadata。
- 已接入：`YoloMotAdapter.process_frame()` 可消费图像帧或 mock detector 输出；默认权重路径为 `/home/linux/Documents/MSM/research_modules/d5_terminal_association/best.pt`，可请求 ultralytics ByteTrack/BoT-SORT 原生 tracker，依赖、权重或原生 tracker 不可用时返回 `unavailable` 或退回确定性 IoU tracker，并在 metadata 中标明实际 detector/tracker backend。原生 `mot_history_length` 按资源/相机/backend/native ID 累计连续实测命中，空帧、reset 和 backend 切换不继承稳定证据。main/AirSim 连续 RGB episode 接线已用于 18-case 正式 screening。
- 部分接入：OpenCV 用于 `projectPoints` 投影和可选畸变参数消费；OpenDroneID/MAVLink/DDS/AprilTag 仅可通过仿真字典转为 `IdentityClaim`。
- 未闭合：bbox 定义/尺度/时间对齐、30/50 m 远距召回、候选多 seed confirmation、GPU/CPU 长期预算、Deep SORT/ReID、OpenCV calibration/`solvePnP` 真实标定链、ROS 2 `tf2/message_filters`、真实 OpenDroneID/MAVLink/DDS/AprilTag 身份认证链路。

因此，若 main/runtime 提供真实 frame、detector 或 tracker 输出，D5 只消费归一化后的 bbox、类别、置信度、时间戳和本地 track ID；D5 不管理 AirSim 图像采集、GPU 部署或 episode 调度，也不把 tracker ID 提升为全局身份。

### ComputerVision N-v-N 多镜头压力输入

本轮 D4/D5 专项测试采用 AirSim ComputerVision Vehicle 场景的离线检测合同，不要求 D5 导入 AirSim 或调用仿真 API。数量由 main runtime 的 `--drone-count N` 统一控制；D5 按传入的 `LocalVisualTrack[]`、`GlobalTrack[]`、camera/resource 列表和 bus observation 长度运行。5v5 只是 stress baseline，推荐几何假设：

- 5 个 `Interceptor_Cam_*` 主镜头。
- 5 个目标，目标距拦截镜头约 50m。
- 目标间距约 20m，镜头间距约 20m，使每个主镜头视场内出现多个目标。
- 一个或多个可机动高空侦察节点，可保持约 200m 高差，携带高分辨率、高性能光电云台，并按 GlobalTrack/radar cue 指向目标簇。

每个主镜头的 `simGetDetections` 结果应被转换为：

```text
DetectionInfo / fixture bbox
-> LocalVisualTrack(local_track_id, center_px, bbox, category, quality, timestamp)
-> TerminalObservationBus.publish_local_track(...)
```

在线转换不得使用 AirSim detection 的 `object_id`、`actor_name` 或 truth ID 来生成、过滤或改写 `LocalVisualTrack`/`TerminalAssociation`。这些真值字段只能作为离线评估标签写入单独 metadata 或 evaluation map。

若已经完成单机配准，则继续发布：

```text
TerminalAssociation
-> TerminalObservationBus.publish_terminal_association(...)
-> CrossViewAssociation summary
```

D5 只生成 `LocalVisualTrack`、`TerminalAssociation`、`IdentityClaim`、`ReconImageCue` 和 `TerminalObservationBus/cross_view summaries`。不得生成 `AssignmentPlan`，不得改写 `global_track_id`。

## 身份声明输入

将合作对象元数据转换为模拟身份消息：

```json
{
  "protocol": "OpenDroneID",
  "platform_id": "FRIEND_SIM_1",
  "local_track_id": "L_friend",
  "timestamp": 12.0,
  "is_friend": true,
  "signature_valid": true
}
```

`IdentityChecker` 只把已验证且新鲜的声明作为正向友方确认。过期、未签名、签名失败或几何不一致的声明不会升级为 `locked`。

## 二级侦察节点图像 cue

AirSim 场景中可加入可机动高空侦察无人机作为二级节点。节点携带高性能光电云台，按 GlobalTrack/radar cue 指向目标簇；二级节点正常时，将其覆盖小区内的离线图像 cue 转换为 `ReconImageCue`：

```json
{
  "cue_id": "sec_cue_001",
  "producer_node_id": "secondary_recon_1",
  "image_frame_id": "secondary_recon_1/camera",
  "timestamp": 12.0,
  "global_track_id": "G_ASSIGNED",
  "center_px": [320.0, 240.0],
  "confidence": 0.8,
  "scoped_resource_ids": ["R1", "R2"]
}
```

`ReconImageCue` 只在 `scoped_resource_ids` 指定的小范围资源中降低视觉关联代价。它不能替代中心授权、版本匹配、友方认证和本地 MOT 质量门槛，也不能让局部节点改写 `global_track_id`。

坐标语义要求：

- 若 `center_px` 来自二级侦察节点相机，回放预处理层必须先根据目标三维位置、二级相机位姿和当前拦截资源相机位姿，将 cue 重投影到当前拦截资源相机平面。
- `image_frame_id` 应标识 cue 当前所属的目标相机帧；建议在 `metadata` 中保留 `source_image_frame_id`。
- 未重投影的二级相机像素不得直接与 `LocalVisualTrack.center_px` 比较。
- 后续离线实验应记录 `recon_cue_used_count`，并对 stale cue、跨资源 cue、空 `scoped_resource_ids` 语义进行回放测试。

## 评估循环

每帧离线回放：

1. 读取中心分配 `Assignment.assigned_global_track_id`。
2. 读取或预测中心全局轨迹 `GlobalTrack`。
3. 构造当前 `CameraModel`。
4. 从标注或 MOT 结果构造 `LocalVisualTrack`。
5. 从模拟 OpenDroneID/友方标签构造 `IdentityClaim`。
6. 可选读取二级侦察节点 `ReconImageCue`。
7. 调用 `TerminalAssociator.decide(...)`。
8. 记录 `locked/ambiguous/hold/reacquire`、候选成本、cue 使用情况、正确性和 ID 不变式。

ComputerVision N-v-N 专项回放中，额外执行：

1. 对 runtime 当前提供的所有 camera/resource 分别调用检测转换 helper，统计每个镜头检测数量。
2. 对每个资源发布本地观测和终端关联结果。
3. 对二级可机动高空侦察节点的光电云台发布已重投影的 `ReconImageCue`；云台按 GlobalTrack/radar cue 指向目标簇，过期或不可用 cue 必须显式标记。
4. 调用 `register_local_visual_tracks_to_global_tracks()` 把本地 detect 注册为既有 `global_track_id` 的候选/稳定跨视角支持；单帧 gate pass 只作为 candidate，默认 3 帧内 2 次通过才进入稳定支持。
5. 调用 `TerminalObservationBus.cross_view_associations()` 或 registration result 中的 `cross_view_associations` / `stable_cross_view_associations` 汇总重叠视场支持。
6. 调用 `compute_terminal_stress_metrics()`、`summarize_degradation_case()`、`summarize_multiseed_calibration_readiness()` 和 `summarize_secondary_visual_coverage_funnel()` 生成 D5 证据、字段覆盖审计和二级 detect 漏斗。

三类证据输出语义：

- `no_degradation`：终端 `locked` 与 D3 分配及评估真值一致，无持续歧义或冲突。
- `degrade_to_secondary`：终端局部证据与中心分配持续不一致或歧义，且二级侦察 cue 新鲜可用。
- `degrade_to_distributed`：终端局部证据与中心分配持续不一致或歧义，但二级 cue 不可用、过期或被标记失效，只能给 D4 提供分散降级证据。

## 指标

- 终端关联正确率。
- locked precision。
- 错误 locked 数。
- `ambiguous` 次数。
- `hold` 次数，尤其是友方重叠触发次数。
- `reacquire` 次数和遮挡恢复耗时。
- 输入 `global_track_id` 变更次数，期望恒为 0。
- `per_camera_detection_count`。
- `multi_target_fov_rate`。
- `cross_view_overlap_count`。
- `duplicate_terminal_lock_risk`。
- `terminal_lock_accuracy`。
- `ambiguous_fov_event_count`。
- `registered_to_global_track` / `geometry_gate_rejected` / `stability_window_failed` / `network_union_incomplete` reason counts。
- `camera_pose_source`、`bbox_area_px`、`pixel_error_px`、`mahalanobis_d2`、`gate_pass` 和 `projection_valid` 字段覆盖率。
- `secondary_single_camera_full_view_frame_rate` 与 `secondary_network_joint_full_view_frame_rate`。
- `detector_backend` / `tracker_backend` 分布，以及 YOLO/MOT 多 seed 阈值标定结果。
- `native_active_frame_rate`、fallback frame、local continuity、terminal local IDSW、P95 latency、offline precision/recall、admission candidate 和 confirmation case 数。

## 防护约束

- D5 不调用 AirSim 控制 API。
- D5 不输出控制量、拦截点、打击参数或毁伤判断。
- D5 不改变中心全局轨迹表。
- 友方重叠默认 `hold`。
- 未知身份默认保持未知，不自动推断为对抗目标。
- 所有自动输出仅供离线评估和人工审查。

## 里程碑

1. 已完成 AirSim `simGetDetections` bbox dry-run、geometry log、truth ID 在线隔离、YOLO/MOT frame adapter、连续 RGB episode 接线、detect-to-global-track registration、multi-seed readiness helper 和 secondary coverage funnel。
2. 已完成 P1 D4/D5 calibration sweep、M5N2 120/120/74 漏斗、原生 MOT 18-case screening 与 D6 bundle 的 D5 evidence 输入口径；0 个 MOT 候选进入 confirmation，默认 detect 不变。
3. 剩余 P1：M5N2 第二 primary；真实 AirSim/replay 外参 drift 与时延标定；detect/YOLO/MOT 多 seed；二级证据同一 decision tick freshness。五层 canonical schema 和 main actual 接线已闭合。
4. 剩余 P2：BoT-SORT/Deep SORT/ReID 质量、真实身份来源 `IdentityClaim` adapter，以及完整在线 PnP/PnP RANSAC、真实标定和畸变校正链。
5. 剩余 P3：IBVS replay 对照和按需 ROS 2 `tf2/message_filters`；二者均不改变 D5 只产出证据且不控制的边界。
