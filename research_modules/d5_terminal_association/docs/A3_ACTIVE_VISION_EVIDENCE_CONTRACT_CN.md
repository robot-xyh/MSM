# A3 主动视觉采用证据合同

## 当前结论

D5 已实现 A3 主动视觉的独立证据组装器和严格验证器。该实现解决了“策略给出云台建议，但无法
证明建议已被 main 下发、相机实际执行并产生后续观测”的软件合同缺口。组装器接受现有
`ActiveVisionSnapshotV1`、`ActiveVisionDecisionV1`、`CameraObservationCommand`、
`runtime.camera_command_ack`、`CameraRuntimeState` 和匿名视觉轨迹/本地绑定。D5 通过公共严格
API 做结构适配，没有增加平行 ACK、姿态消息或相机控制权。

历史冻结批次按同一外生配置运行状态隔离的候选与规则 episode。2026-07-27 的受控开发批次覆盖
20 个开发 seed，共记录 536 条候选动作；536/536 disposition 已落盘并通过严格复载。152 条
可配对、384 条不可配对，不可配对主原因全部为
`candidate_physical_window_missing`。可配对覆盖率为 `28.36%`，20/20 seed 至少存在一个
可配对子集。批次 SHA-256 为
`455d181076553a485ff824618abc6d037a4477bb6342877d1d1e427fd28583a9`。

D6 使用完整候选分母审计后得到 `a3_auditable_pair_count=0`。由于批次包含合法 unpairable，
完整 A3 实际采用、物理窗口、同键 R0 和收益计数均为 `unavailable`，所有权限为 `false`。
152 条只代表可配对子集。该批次使用测试策略替身，seed 未验证为正式未见集合，也不是
AirSim、实机或模型收益证据。

D5 已增加候选阶段证据和 disposition v2。新合同在保持顶层主原因兼容的前提下，依据明确的
运行事件清单细分 ACK、命令时序、相机反馈、匿名观测和物理窗口装配断点。旧 v1 disposition
继续严格复载，已落盘的历史 v1 disposition 不追溯改写。

在 observation-frame v2 runtime 接线前，main 曾用同配置 seeds `1000-1019` 和
candidate-stage sidecar 做不落盘全量重跑。
536/536 候选有阶段证据，152 条可配对、384 条不可配对，完整可审计 seed 仍为 `0/20`。
344 条同时为匿名观测缺失和物理窗口确认缺失；其余 40 条因观测清单不完整保持
`candidate_stage_reason_codes=[]`，记为物理窗口缺失细因未解析。D6 聚合 evidenced=344、
unresolved=40、`detail_completeness=false`；每 seed 的 scope 约为 20、
evidenced=`scope-2`、unresolved=2。部分清单门控由此阻止将 40 条越界归因为物理窗口不完整。
ACK 缺失、运行确认缺失、命令过期、时序错配和相机反馈缺失均为 0。开发摘要 SHA-256 为
`1ba6040e7c3e7e3b9e7d5506dfd20cf3539ce12c5aac13cca7f02799f0cd99ef`。该摘要明确标记
`formal_evidence=false`、`source_worktree_clean=false` 和
`persisted_full_pair_inventory=false`，不能作为 clean/frozen 正式证据，也不关闭未见 seed、
非退化、收益或授权缺口。只读来源为
`research_modules/scalable_3d_simulation/docs/SCALABLE_3D_A3_STAGE_BREAKDOWN_DEVELOPMENT_20260727.json`。

D5 本轮补充 observation-frame v2，用来表达“相机图像已经处理，但该帧检测数为零”。历史 v1
仍要求至少一个匿名轨迹，字段集合和内容哈希口径不变。v2 零检测帧有分配目标时只产生
`reacquire` 和覆盖率 0；无分配目标时结果保持 unavailable。main 已在 scalable 3D 开发
writer/runtime 中接入该合同：每台相机生成 truth-free frame event，只有零检测帧进入
`sensor.camera_empty_frame`；事件保存相机/资源、双时间戳、scan index 和三类版本。A3/R0
按时间和版本绑定，观测触发命令并保留 0.25 秒证据尾窗。

同配置 seeds `1000-1019` 的默认通信退化复跑为 candidate=492、pairable=488、
unpairable=4、coverage=`99.18699%`。可配对窗口含 329 个 v2
`reacquire/coverage=false` 和 159 个 v1 `locked`，empty rejected=0，全部权限为 false。
零丢包/零抖动对照为 `500/500`、coverage=`100%`。4 条缺失与默认 1% 通信丢包相关，尚未
证明唯一因果。scalable 3D 全量回归为 `352 passed, 1 warning`。

新结果均为 `formal_evidence=false`、dirty worktree，seeds 未证明 unseen；不证明主动视觉
收益、模型准入或授权。历史冻结 `536/152/384` 批次、历史开发阶段 `344/40` 细因及哈希
`455d1810...`、`1ba6040e...` 均保持不变。

## 证据层次

证据链按下列顺序独立记录。后一个状态不能反向补足前一个状态。

1. **策略评估**：记录模型指纹、bundle manifest、权重、实现和源提交摘要，并保存策略实际
   求值时间。模型文件被加载不等于策略已求值。
2. **命令建议**：从现有 `ActiveVisionDecisionV1.requested_action` 判断模型是否输出建议。
   没有建议时，后续规则动作不能记为模型采用。
3. **确定性投影**：根据 `requested_action`、`fallback_reason` 和 `effective_action` 区分
   `accepted`、`rejected` 和 `not_evaluated`。安全门、视场门、友方冲突门和版本门继续由
   确定性 D5 逻辑控制。
4. **命令下发**：结构化读取 main 的 `CameraObservationCommand`，核对相机、资源、目标只读
   引用、计划版本、联盟版本、通信版本、意图、视场模式和有效期。组装器只保存其规范载荷和
   SHA-256，不在 D5 内发送命令。
5. **运行回执**：`active_vision_runtime_ack_from_payload()` 严格适配
   `runtime.camera_command_ack`。回执必须匹配 sample、相机、资源、命令版本、三类计划版本和
   有效期。规范命令和 ACK 均计算 SHA-256；`accepted=True` 仍不足以证明姿态已经变化。
6. **姿态生效**：`active_vision_camera_feedback_from_runtime_state()` 从 ACK 后
   `CameraRuntimeState` 同时生成现有反馈和 `ActiveVisionA3CameraPoseLineage`。lineage 保存
   相机、资源、状态时间、姿态、视场、计划/联盟/通信版本和可选来源序号。验证器要求最后接受
   命令版本与 ACK 一致，并用命令前相机状态和 `effective_action` 重算期望姿态。
7. **物理观测窗**：姿态反馈之后采集带 `measurement_timestamp` 和 `arrival_timestamp` 的
   相机帧。检测到目标时，`active_vision_a3_observation_frame()` 保存逐帧匿名本地轨迹和绑定。
   图像已处理但零检测时，`active_vision_a3_zero_detection_frame()` 保存 v2 显式负观测。
   相机帧本身缺失、缺 ACK 或缺姿态 lineage 仍保持 unavailable。
8. **独立规则 R0 trace**：`ActiveVisionA3RuleArmTrace` 只接受学习关闭、无模型建议、无模型
   指纹、零模型推理时延且规则动作等于有效动作的决定。它保存规则 episode 自己的命令、ACK、
   相机反馈和姿态 lineage，不保存候选模型 bundle、权重、实现或采用 trace。
9. **规则 R0 配对**：规则 trace 可序列化并在另一进程严格重建，再与规则 episode 的匿名帧
   形成 R0 窗口。A3 与 R0 必须同场景、规模、seed、相机、资源、目标引用、窗口序号、配对
   上下文和计划版本。两臂时长相同，来源日志不同。一个 comparison key 最多接受一个 R0。
10. **逐候选 disposition**：每条候选动作均输出 `pairable` 和一个稳定主原因。成功项引用
    既有 paired evidence；失败项不携带 paired evidence。没有完整阶段清单时，候选窗口缺失
    保持粗粒度，不根据 `None` 推断断点。存在与 trace 和来源日志绑定的阶段证据时，v2 另行
    输出受控细分原因。运行细因要求完整运行清单，观测细因要求完整观测清单，物理窗口细因
    要求两类清单都完整。

## 采用判据

模型动作采用判据为：

\[
A_{\mathrm{adopt}} =
I_{\mathrm{evaluated}}
I_{\mathrm{proposal}}
I_{\mathrm{projection\ accepted}}
I_{\mathrm{model\ command\ issued}}
I_{\mathrm{runtime\ ACK}}
I_{\mathrm{pose\ applied}}
I_{\mathrm{truth}=0}
I_{\mathrm{ID\ rewrite}=0}.
\]

其中运行回执和姿态反馈的 provenance 必须为 `runtime_observed`。确定性执行器 fixture、模拟
ACK、模拟姿态和只有日志计数的记录均不满足该判据。

D6 收益审计入口还要求：

\[
A_{\mathrm{D6}} =
A_{\mathrm{adopt}}
I_{\mathrm{candidate\ physical\ window}}
I_{\mathrm{candidate\ outcome}}
I_{\mathrm{same-key\ R0\ window}}
I_{\mathrm{R0\ outcome}}.
\]

`A_D6=true` 只允许 D6 计算配对收益或非退化结果。它不授予主动视觉辅助、相机命令、分配、
故障接管、导引、控制、模型晋级或 `global_track_id` 修改权限。G1 授权字段固定为 false。

## 现有合同复用

main 需要提供以下既有对象或其规范序列化：

- `CameraObservationCommand`：D5 通过
  `camera_observation_command_payload()` 做结构适配，不导入 main 模块；
- `runtime.camera_command_ack`：D5 通过
  `active_vision_runtime_ack_from_payload()` 转成现有 `ActiveVisionRuntimeAckV1`；
- `CameraRuntimeState`：D5 通过
  `active_vision_camera_feedback_from_runtime_state()` 同时生成
  `ActiveVisionCameraFeedbackV1` 和带三类版本的姿态 lineage；
- `ActiveVisionDecisionV1`：保留规则动作、模型建议、最终动作、回退原因和模型指纹。

新增 DTO 只承担证据组织：

- `ActiveVisionA3CameraPoseLineage`：绑定 ACK 后相机状态、三类版本和来源序号；
- `ActiveVisionA3BindingEvidence`：保存匿名簇状态和中心航迹只读引用；
- `ActiveVisionA3AnonymousObservationFrame`：v1 保存非空匿名轨迹、双时间戳和本地绑定；
  v2 另存帧处理状态与中心航迹只读清单，允许显式零检测；
- `ActiveVisionA3AdoptionTrace`：绑定策略、命令、现有 ACK、相机反馈和姿态 lineage；
- `ActiveVisionA3RuleArmTrace`：绑定独立确定性规则决定、命令、运行 ACK、相机反馈和姿态
  lineage，不含候选模型 provenance；
- `ActiveVisionA3PhysicalObservationWindow`：绑定并重新计算后续关联/覆盖窗口；
- `ActiveVisionA3BenefitAuditInput`：绑定候选窗口、同键 R0 和失败原因；
- `ActiveVisionA3CandidateStageEvidence`：保存完整性声明、命令/ACK/反馈时间、匿名观测
  计数与双时间戳、窗口装配状态，并绑定 adoption trace 和来源日志摘要；
- `ActiveVisionA3PairingDisposition`：为一条候选保存 `pairable`、稳定主原因、底层诊断码和
  可选 paired evidence 引用；v2 另存阶段证据和重算后的细分原因，不携带新的运行权限。

匿名轨迹键必须使用 `resource_id/camera_id:local_id`。D5 公共函数
`map_active_vision_binding_state()` 固定映射：

```text
bound     -> locked
ambiguous -> ambiguous
unbound   -> reacquire
```

`global_track_id` 只能来自调用方提供的中心候选集合。匿名轨迹键、簇键和状态映射都不能创建、
替换或改写该编号。

## 公共 API

main 可按以下顺序组装证据：

```python
trace = assemble_active_vision_a3_adoption_trace(
    ...,
    snapshot=snapshot,
    decision=decision,
    issued_command=camera_command,
    runtime_ack_payload=runtime_ack_payload,
    post_command_camera_state=camera_runtime_state,
    runtime_ack_evidence_kind="runtime_observed",
    camera_feedback_evidence_kind="runtime_observed",
)

frame = active_vision_a3_observation_frame(
    frame_key=frame_key,
    observations=anonymous_local_tracklets,
    bindings=d5_local_bindings,
    target_global_track_id=trace.target_global_track_id,
    center_global_track_ids=center_global_track_ids,
    plan_version=plan_version,
    coalition_version=coalition_version,
    communication_version=communication_version,
    evidence_kind="runtime_observed",
)

# 图像已处理但没有检测输出时，使用 v2 负观测工厂，不能传伪造轨迹。
zero_frame = active_vision_a3_zero_detection_frame(
    frame_key=frame_key,
    camera_id=camera_id,
    resource_id=resource_id,
    measurement_timestamp=measurement_timestamp,
    arrival_timestamp=arrival_timestamp,
    plan_version=plan_version,
    coalition_version=coalition_version,
    communication_version=communication_version,
    target_global_track_id=trace.target_global_track_id,
    center_global_track_ids=center_global_track_ids,
    evidence_kind="runtime_observed",
    source_sequence=source_sequence,
)

a3_window = assemble_active_vision_a3_physical_observation_window(
    trace,
    arm="A3",
    observation_frames=(frame,),  # 零检测时改传 (zero_frame,)
    window_start_timestamp=window_start,
    window_end_timestamp=window_end,
)

rule_trace = assemble_active_vision_a3_rule_arm_trace(
    comparison_key=comparison_key,
    scenario_id=scenario_id,
    scale=scale,
    seed=seed,
    window_index=window_index,
    sample_key=r0_sample_key,
    pairing_context_sha256=pairing_context_sha256,
    source_event_log_sha256=r0_source_event_log_sha256,
    snapshot=r0_snapshot,
    rule_decision=r0_rule_decision,
    issued_command=r0_camera_command,
    runtime_ack_payload=r0_runtime_ack_payload,
    post_command_camera_state=r0_camera_runtime_state,
)

# rule_trace 可先 to_dict() 持久化，再在独立进程 from_mapping() 重建。
r0_window = assemble_active_vision_a3_rule_arm_physical_observation_window(
    rule_trace,
    observation_frames=r0_anonymous_frames,
    window_start_timestamp=r0_window_start,
    window_end_timestamp=r0_window_end,
)

audit_input = assemble_active_vision_a3_paired_evidence(
    trace,
    candidate_window=a3_window,
    same_key_r0_windows=() if r0_window is None else (r0_window,),
)

disposition = attempt_active_vision_a3_pairing(
    trace,
    candidate_window=a3_window,
    same_key_r0_windows=() if r0_window is None else (r0_window,),
    candidate_stage_evidence=candidate_stage_evidence,
)
```

上述 R0 API 不接收候选 trace、模型指纹、bundle 摘要或模型评估时间。两次 episode 不要求
共享 Python 进程或对象，只共享规范 comparison identity 和同一冻结外生配置摘要。缺任一输入
时，组装结果携带 blocker 且
`d6_benefit_audit_input_allowed=False`。API 不以空窗口或零指标填补缺失相机帧；v2 的覆盖
率 0 只表示已有相机帧经处理后没有检测到中心分配目标。
`candidate_stage_evidence` 是可选输入。调用方没有任何可审计清单时应传 `None`，不得构造
虚假的 `inventory_complete=true` 空记录。只有一类清单完整时，可以保存部分阶段证据，但
只能生成该完整清单所属的细因；部分字段不能用于跨阶段归因。

`attempt_active_vision_a3_pairing()` 不把预期的失败关闭路径抛给批处理调用方。它将每条候选
归入以下稳定主原因之一：

```text
pairable
model_action_not_adopted
candidate_physical_window_missing
same_key_r0_window_missing
same_key_r0_duplicate_or_ambiguous
pairing_key_or_configuration_mismatch
candidate_physical_evidence_incomplete
r0_physical_evidence_incomplete
benefit_outcome_unavailable
evidence_contract_invalid
```

主原因用于总数守恒和批量统计，`detail_codes` 保存现有 blocker 或严格 validator 的错误码。
如果 trace 本身无法严格重建，候选引用保持 unavailable；main 应继续用输入序号或外层记录键
定位原记录，不能信任篡改载荷内的身份字段。

## disposition 持久化验证

main 持久化 `disposition.to_dict()` 后，D6 或其他只读消费者使用以下任一入口复载：

```python
validated = validate_active_vision_a3_pairing_disposition(payload)
# 等价入口
validated = ActiveVisionA3PairingDisposition.from_mapping(payload)
```

验证器按 schema 要求精确字段集合，并检查字符串、严格布尔、整数、字符串列表和 JSON
`null` 类型。旧 v1 按原字段集合复载；v2 额外要求
`candidate_stage_reason_codes` 和 `candidate_stage_evidence`。pairable 记录必须携带 paired
evidence 对象；验证器调用现有
`validate_active_vision_a3_evidence()`，重新计算采用 trace、候选/R0 窗口、阻断项、D6
eligibility、全部权限和内部摘要。unpairable 记录的 `paired_evidence` 必须为 `null`。顶层
对象重建后再复算 `content_sha256`，并与完整规范字典逐字段比较。pairable 顶层候选引用还须
逐项等于嵌套 adoption trace，即使调用方重算顶层摘要也不能替换 comparison key、seed、相机、
资源、目标或配对上下文。v2 阶段证据同时复算自身摘要、trace 引用和细分原因；未知原因或将
一个已知原因替换成另一个已知原因后重算顶层摘要也会拒绝。

通过该验证只说明 disposition 制品完整且内部自洽。validator 没有重新采集命令、ACK、相机
反馈或匿名观测，也没有访问物理环境，因此不能独立证明 `reason_code` 是实际缺失的因果解释。
原因真实性仍由原始事件日志、双时间戳链、配置摘要和 D6 外部审计共同证明。

## main 接线

main 在一个主动视觉决策周期内需要保存以下字段。

```text
comparison_key
scenario_id / scale / seed / window_index
sample_key
pairing_context_sha256
source_event_log_sha256
model_fingerprint
bundle_manifest_sha256
bundle_weights_sha256
implementation_sha256
source_git_commit
ActiveVisionDecisionV1
pre-command ActiveVisionCameraState
CameraObservationCommand canonical payload
ActiveVisionRuntimeAckV1
post-command ActiveVisionCameraFeedbackV1
post-command ActiveVisionA3CameraPoseLineage
ACK / feedback provenance
command / ACK / feedback SHA-256 or source sequence
online_truth_use_count
global_track_id_rewrite_count
candidate stage inventory start/end timestamp
runtime_event_inventory_complete
command issued/expires timestamp
runtime ACK timestamp/applied state, including rejected or late ACK
camera feedback timestamp
observation_inventory_complete
anonymous frame count and first/last measurement/arrival timestamp
physical_window_status = unknown | missing | incomplete | complete
```

后续观测窗需要保存每个匿名观测帧、`resource_id/camera_id:local_id`、窗口起止时间、逐帧
measurement timestamp、arrival timestamp、三类版本、本地绑定、关联状态、已分配目标引用和
来源日志摘要。v2 零检测帧还要保存 `processed_zero_detections`、中心航迹只读清单和
`source_sequence`，不得伪造本地轨迹填充空结果。A3 与 R0 的 `pairing_context_sha256` 应由
main 对相同初始状态、传感器/通信/
故障日程和冻结配置生成。当前 main 优先读取
`config.metadata.paired_exogenous_config_sha256` 作为该摘要。`source_event_log_sha256` 已纳入
`episode_id`，因此同外生配置的候选和规则 episode 仍会得到不同来源日志摘要。每个 episode 的
中间结果写入 `learning_adoption_evidence.json`。

批处理必须对每条候选调用一次 `attempt_active_vision_a3_pairing()`，不能只保存
`pairable=true` 的子集。建议逐条保存 `disposition.to_dict()`，并至少汇总候选总数、可配对
数量、不可配对数量和各 `reason_code` 数量。验收关系为：

\[
N_{\mathrm{candidate}} =
N_{\mathrm{pairable}} +
\sum_r N_{\mathrm{unpairable},r}.
\]

当前开发批次的输入总数是 536，可配对数量是 152，不可配对数量是 384；原因计数之和与候选
总数一致。384 条不可配对记录的主原因均为 `candidate_physical_window_missing`。该批次没有
阶段清单，因此不能追溯性推断为 ACK、相机反馈、命令后观测或过期时序中的某一项。后续批次
由 main 在调用 `attempt_active_vision_a3_pairing()` 时显式传入
`candidate_stage_evidence`，D5 才会生成细分原因。

## D6 接线

D6 应先对每条 v1 或 v2 A3 pairing disposition 调用公共 disposition validator。
unpairable 项只进入原因完整性和 availability 统计；pairable 项再从已验证 DTO 读取嵌套的
`d5.active-vision-a3-benefit-audit-input.v1`。后者已经由 disposition validator 递归复载，
D6 仍可按自身边界再次执行 paired evidence validator，并至少检查：

1. `content_sha256`、trace、命令、ACK、反馈和两个窗口摘要；
2. `d6_benefit_audit_eligible=true` 且 blocker 为空；
3. `model_action_adopted=true`；
4. 候选和唯一 R0 的同键身份、时长与不同来源日志；
5. 两臂 association/coverage outcome 均 available；
6. 所有权限字段除 `d6_benefit_audit_input_allowed` 外均为 false；
7. 离线 truth sidecar 与在线证据分离，在线对象不含 AirSim actor/object ID。

D6 可以在通过上述检查后计算覆盖率变化、锁定/模糊/保持/重捕获分布变化及置信区间。D5
assembler 不计算“模型优于规则”，也不根据单个窗口改变模型准入状态。

本批次的完整分母审计结果为 `a3_auditable_pair_count=0`。只要存在合法 unpairable，D6 就将
完整批次的实际采用、物理窗口、同键 R0 和收益计数标记为 `unavailable`，并保持全部权限为
`false`。pairable 子集可用于定位证据覆盖，但不能脱离完整分母发布收益统计。

## 失败关闭

验证器覆盖以下主要拒绝路径：

- 策略未求值、模型未给出建议或确定性投影拒绝；
- 最终仍使用规则回退；
- 命令未下发；
- ACK 缺失、拒绝、非运行时来源、版本不符或时间越界；
- 相机反馈缺失、命令版本未生效、姿态/视场不符；
- 姿态 lineage 缺失，或相机/资源、时间、计划/联盟/通信版本与命令不符；
- 匿名观测帧缺失、v1 使用空轨迹、v2 零检测夹带轨迹/绑定、轨迹键命名空间错误、双时间戳
  倒置或引用非中心航迹；
- v1/v2 帧时间、版本、来源或内容哈希被篡改，或同一窗口混入 runtime/synthetic provenance；
- 候选物理窗口缺失或关联/覆盖结果不可用；
- 同键 R0 缺失、身份/版本/时长不一致或复用同一日志；
- 同一 comparison key 提供两个及以上 R0；
- 每条候选没有 disposition，或 disposition 总数与候选总数不守恒；
- R0 携带 assist/shadow 决定、模型建议、模型指纹、非零推理时延或候选采用 trace；
- 在线真值字段、truth 使用计数或 `global_track_id` 改写计数非零；
- 命令、ACK、反馈、窗口或总合同 SHA-256 被修改。

## 验证记录

2026-07-27 observation-frame v2 加入后，专项合同测试为
`84 passed in 1.38s`。验证覆盖明确断点分类、部分或无完整清单时禁止越界推断、历史 v1
严格复载与空帧拒绝、v2 零检测、中心目标引用、v1/v2 同源混合窗口、时间/版本/来源/哈希
篡改、零覆盖、全部权限关闭，以及 disposition v1/v2 的既有严格行为。所有正例都是软件
fixture，不是 AirSim 或实机结果。
当前 D5 完整回归为 `739 passed, 2 warnings in 97.98s`，零失败；警告来自 Matplotlib
`Axes3D` 多版本环境和 NVML 初始化失败。
只读 D6 严格采用审计消费者回归为 `58 passed, 1 warning in 9.40s`，零失败；警告为既有
Matplotlib `Axes3D` 环境提示。该检查没有修改 D6。

## 开放工作

1. main 在 clean/frozen 新批次按本合同持久化 v2 stage evidence、disposition 和完整 pair
   inventory。当前开发内存重跑不能替代正式制品，旧持久化记录不得追溯改写。
2. 在 clean/frozen 条件下复核默认 1% 通信丢包相关的 4 条缺失，保存通信事件与候选窗口的
   因果时间链，不能用零丢包对照直接替代退化配置。
3. main 在后续批次继续按 comparison identity 使用唯一规则 R0；当前 A3 assist 仍需独立
   授权，不得由本合同自行开启。
4. D6 继续分别报告 pairable 覆盖和不可配对原因，不把不可用物理指标补零。
5. 运行至少 20 个明确验证为未见的 seed 后，再判断 A3 是否达到 held-out 和非退化门。当前
   开发批次没有 paired benefit、物理收益或模型晋级结论。
