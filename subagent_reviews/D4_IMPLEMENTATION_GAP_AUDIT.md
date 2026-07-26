# D4 实现差距审计：分布式协同与降级接管

## 2026-07-26 A2 预准入证据装配审计

- **P0 结论**：没有发现新的模块内自晋级路径。v2 writer 在文件写入前拒绝
  `qualified/assist`；loader 只能构造 development manifest；`assist_admitted` 恒为 false；
  advisor 对无 manifest 注入策略保持 shadow。生产调用方没有消费裸
  `reward_evidence_available`、`final_holdout_seed_count`、`assist_eligible` 或占位 SHA-256
  来获得 assist/authority。
- **已有软件合同**：bundle 树校验、候选建议内容身份、严格后继 D3 计划、main/D3/D7
  runtime ACK、owner/plan/epoch/lease、联盟提交状态、成员 ACK 因果投递回执、非重叠区域
  观测窗口和隔离 paired 合同均已存在。各证据 DTO 固定不能单独授予 promotion、PPO、assist
  或 authority。
- **尚未等价的链路**：当前没有 D4 evidence assembler 把同一候选的 runtime ACK、联盟
  required/acked members、每条 delivered receipt、采用后物理结果和 D6 R0 配对非退化连接
  到同一内容身份；也没有可由该装配结果生成新 admitted bundle 的 writer/loader。现有区域
  reward 只作 truth-free 非因果窗口归因，明确不是物理执行证明。
- **现有 evidence 不可拼接**：nominal formal 20-seed 的候选安全采用为 0/20；`active_risk`
  20-seed 虽有物理窗和描述性非退化，但候选 considered/adopted 为 0/20，188/188 区域记录
  均为规则回退且 `production_runtime_ack=false`。跨候选或把两批 availability 合并均不满足
  准入。
- **最小外部审计字段**：bundle manifest/tree/model/training 摘要；clean source、scenario、
  seed、comparison key；advisory/model/projector 指纹和门控结果；source/applied plan
  ID/version、new-plan adoption kind、D3/D7/main sequence 与 payload digest；owner/layer、
  epoch、lease、fault/partition generation；coalition ID/version、required/acked members
  及逐成员 receipt ID/digest/timestamps；采用后物理指标 availability；R0 pair 身份、逐项
  non-degradation 和 D6 审计制品摘要。
- **唯一剩余 P1**：D6 先冻结通用外部审计输出，main 生成实际采用正样本；D4 再实现模块专用
  装配器和独立新 bundle 发布入口。D4 不新建通用 external-audit schema，不修改旧 v2
  manifest，不在缺实物证据时先造可通过的测试 promotion。
- **权限状态**：软件合同可验证局部事实；当前 bundle 仍是 development；已有实验证据仍不可
  拼接；正式 assist、PPO、authority 均为 false。
- **验证**：2026-07-26，无新增场景或 seed；验收阈值为零自晋级路径、零跨批宽松拼接和 D4
  回归零失败。结果为 **569/569 passed**，限定范围 `git diff --check` 通过。

## 2026-07-26 A2/C1/F1 严格准入

- **代码缺口已关闭**：v2 bundle writer 只允许 development/shadow，并在任何文件写入前拒绝自声明 qualified/assist；无 manifest 注入策略不能默认进入 assist。旧 bundle/manifest 未改写。
- **当前 bundle**：`d4-region-bc-900-development-v1`；manifest/weights/training-manifest SHA-256 为 `dad2adbe...c05c9`/`3da0360b...d5f62`/`ff3081c8...30dc6`。`assist_admitted=false`。
- **nominal 证据不准入**：formal `7891296` 的 20 个候选在 0.6 门限下安全采用 0/20、规则回退 20/20；runtime ACK、physical outcome、paired non-degradation 均不可用。D6 sidecar 文件/内容 SHA-256 为 `f3852251...1c3b`/`c02a345c...5d2d`。
- **active_risk 证据不准入**：clean commit `0fa7c00c...b0b` 的 20-seed sidecar 具有 20/20 物理窗和描述性非退化，文件/内容 SHA-256 为 `dbbda161...a7515`/`1aae70cd...3489`；但 D4 candidate considered/adopted 为 0/20，188/188 区域记录均为 rule fallback，production runtime ACK=false。
- **main blocker**：`d59352b` 的 scope 基础设施已严格绑定 bundle 树和运行诊断，但 D4 预检仍为 `pending_runtime_shadow_gate`。A2/C1/F1 当前会在创建正式执行目录前失败关闭，正式学习 episode 数为 0。
- **剩余 P1**：定义 D4/D6 内容寻址 promotion schema；在 clean 未见 seed 的非 nominal 降级场景实际采用 D4 候选；绑定新执行计划 ACK、联盟成员 ACK、采用后物理窗和配对非退化；由 main 同时核验预检准入与 episode 内实际采用。
- **验证**：2026-07-26，无新增场景或 seed；D4 全量 **569/569 passed**，`py_compile` 通过。

## 2026-07-25 P1 异步 M-to-N 联盟确认

- **根因**：`RegionalFailoverCoordinator._authorize_tasks()` 在提案快照末尾无条件 `finalize=True`。真实网络 ACK 需要后续 tick 才能到达，首帧因此永久 `aborted/missing_required_acks`。
- **D4 缺口已关闭**：普通快照保持 `collecting_acks`，同一 plan/epoch/coalition generation 的 ACK 位图跨快照累积，完整后原子提交。新增显式终结开关，默认关闭；租约、分区、摘要冲突和成员不可执行继续失败关闭。
- **无效消息边界**：旧 epoch/version、过期、越权或不匹配 ACK 被拒绝且不计入位图，当前快照不授权。后续合法 ACK 可恢复，避免乱序旧包永久毒化有效代次。partition generation 仍由已实现的通信因果证据门拒绝。
- **验证**：2026-07-25 新增 5 项异步回归；三文件专项 97/97、D4 全量 569/569。验收阈值为完整 ACK 前授权 0、三成员完整 ACK 后原子提交 1、全部负例授权 0。
- **main 单随机种子证据已闭合**：2026-07-25，随机种子 `1271` 的 2 目标、4 资源、1 个二级侦察节点 scalable 3D 场景已按实际通信投递完成 0/3 ACK 保持、3/3 ACK 原子提交、两个主成员释放和备用成员待命。在线真值使用与 `global_track_id` 改写均为 0；main-owned 模块栈 66 passed，scalable 3D 全量 272 passed。
- **剩余 P1**：AirSim 多随机种子故障矩阵、真实网络时延/乱序/丢包/分区条件、长期恢复统计和 D6 正式 5700 单元矩阵仍未形成。单随机种子质点结果不能替代物理连续性或 200 对 200 性能结论。

## 2026-07-25 P0 区域通信因果证据

- **P0 历史复现**：main 曾在 5v5 `center_failure`、duration 3.2 秒、`communication_enabled=false`、雷达探测概率 1.0 条件下，输出 8/8 区域可执行二级层。
- **D4-owned 第一半已关闭**：新增不可变 delivered receipt、版本化 topic 映射、truth-free payload digest、内容寻址 receipt ID，以及 readiness、区域计划广播、联盟成员 ACK 三类验证入口。严格工厂从 delivered message/envelope/payload 提取 authority、plan、epoch、lease、partition 和 message ID，调用方不能覆盖。
- **失败关闭语义**：无实际回执固定返回 `receipt_missing`。错源/目的/类型、旧 plan/epoch、过期或错 scope lease、晚到、分区代次和 payload digest 不一致均有稳定 reason code。精确重复仅在 receipt 与 expectation 完全不变时幂等；冲突重放和跨证据复用被拒绝。结果固定 `authority_granted=false`，不改变既有状态机。
- **验证日期与范围**：2026-07-25，因果证据专项 56/56；加入异步联盟回归后 D4 全量 569/569。参数化规模为 5/20/50/100/200。
- **P0 已关闭**：main 已将三类控制消息接入 `DeterministicCommunicationNetwork`。通信关闭复现现为 0 个可执行区域、8 个失败关闭区域，D7 全部 hold。该结论关闭原因果通信 P0；真实通信 M-to-N 正例复跑列为上节 P1。

## 2026-07-22 跨提交内容身份审计

- **D4 P0 无新增代码缺口**：原始 `formal_decision_digest`、`authority_digest` 和内容寻址 `advisory_id` 的生成及校验语义正确。三者在单次运行内必须保持原值，消费 ledger 继续使用原始 advisory identity。
- **条件规范化边界已明确**：跨独立 episode 仅允许先把经 D3 谱系审计的原始 `plan_id` 映射为规范 token，再从规范正式裁决、完整规范 authority payload 和完整规范 advisory contract 重算三个摘要。事件序号只用于一一配对；直接写成事件 token、删除 advisory identity 或只比较摘要等价类均不满足 D4 完整性要求。
- **必须原值比较的语义**：region/task/global-track/resource/node/coalition identity、owner/layer/role、plan version、epoch、lease、ACK、active/fault fence、正式 decision/action/reason、策略/模型身份、动作、转移和安全证明均不可归一化。任一缺失或变化均为业务差异。
- **当前证据**：clean `8f86192` 与 `f80b5bd` 的 seed 42000-42002 中，两侧各 30 条 advice 均通过原始内容地址、formal digest、authority digest 和内部副本一致性校验；30/30 对 formal/advice 在严格规范重算后逐字段相同。
- **main P1 证据完备性仍开放**：当前 60 条原始 advice 可用 `source_version + protected_committed_resources` 精确回算 authority digest，因此本批次可审计。通用制品没有单独持久化完整 `RegionResourceSnapshot`；若 formal committed protection 与 snapshot `committed_resources` 不同，仅凭 advisory 不能无歧义恢复 authority 输入。main 后续应持久化 authority payload 或其可验证来源，缺失时必须输出不可比较，不能宽松归一化。

## 2026-07-22 中心失效物理续跑代际审计

- **D4 P0 安全门无缺口**：`RegionResourceIsolatedAdoptionVerifier` 正确拒绝不同 plan ID、相同 plan version 的执行变化。strictly-new、formal owner、epoch、lease、binding、ACK 和 `production_runtime_ack=false` 均保持不变。
- **main/D3 producer P1 仍开放**：中心失效 20-seed 共 20 pair、196 region，D7 命令已应用，但区域采用 196/196 以 `isolated_execution_plan_not_strictly_new` 拒绝。main 以 formal current plan 为 source，arm 却从 `previous_plan` 生成同版本异 ID applied plan。
- **source 规则**：`center_failed` 使用 formal secondary source；`center_and_secondary_failed` 使用逐区域 formal distributed source；`active_risk` 使用 formal center source。被动降级前的 center/secondary `previous_plan` 不属于当前 formal authority，不能直接作为 D4 source。
- **applied 规则**：执行变化必须在同一 formal owner/epoch/lease 下使用新 ID、严格更高版本和更新创建时间。无执行变化只能使用同一 plan ID/version、同 binding/未分配集合/创建时间的显式 refresh。authority 改变时先重建 formal decision 和 lineage。
- **本轮验收**：隔离专项 26/26、D4 全量 508/508、D4 owned paths 的 `git diff --check` 通过。该结果关闭 D4 公共合同说明和负例测试缺口，不关闭 main 物理采用、D6 描述性比较或降级效果 P1。

## 2026-07-21 PDT / 2026-07-22 UTC 隔离 degraded rollout 采用边界

- **D4 合同缺口已关闭**：新增 `d4-region-resource-degraded-scenario-lineage-v1`、candidate gate、isolated plan-consumption ACK 和 adoption evidence。API 由 `RegionResourceIsolatedAdoptionVerifier` 提供，按 region/arm/cycle 验证三类降级来源、源哈希、formal D4 authority、源/新 D3 plan、执行 binding 和隔离消费回执。
- **采用语义已拆分**：输出分别保存 `candidate_considered`、`gate_pass`、`new_execution_plan_applied`、`evaluation_refresh_applied`、`rule_fallback`。只有 passing candidate、非 fallback、严格更新的新 plan ID/version、当前 owner/epoch/lease 和完整 isolated receipt 同时成立，才有 `isolated_candidate_adoption_available=true`。同代 evaluation refresh 即使候选通过也不计为采用。
- **降级来源已限定**：`center_failed` 必须由可执行 secondary authority 证明；`center_and_secondary_failed` 必须由可执行 distributed authority 证明；`active_risk` 必须由中心未失败、D1/D2/D3/D5 风险和 `request_center_replan|request_secondary_assist` 证明。snapshot、decision、计划、候选门及配置/初态/通信/故障 schedule 均进入 SHA256 lineage。nominal 场景明确 rejected，既有 nominal 5v5 不能关闭策略效果 GAP。
- **安全门保持不变**：`minimum_confidence=0.6`、latency limit `50 ms`、OOD、finite、failure、deterministic projection、owner/epoch/lease、plan version 和 binding gate 均未放宽。缺 ACK、receipt replay、旧 epoch、到期/错误 lease、owner/binding 篡改、same-generation binding 变化、网络分区和缺联盟 ACK 全部失败关闭。低置信候选只允许规则 fallback 计划继续。
- **证据权限保持关闭**：隔离 receipt/evidence 固定 `production_runtime_ack=false`、`isolated_simulation_only=true`。physical outcome、paired non-degradation、counterfactual、causal、degradation-effectiveness claim、PPO、assist 和 authority 全为 false，规则回退为 true。
- **D3 回执边界已接入**：D4 可独立解析 `d3.isolated-plan-consumption-evidence.v1`，严格核对来源 lineage、计划身份、binding 完整性、消费时间窗、内容哈希以及非生产权限，再转换为 D4 隔离 ACK。它不导入 D3，也不把 D3 回执解释为生产运行时 ACK。
- **验收**：2026-07-22 本地确定性隔离合同测试 **26/26 passed**；D4 全量 **508/508 passed**。测试不是 AirSim、真实通信或完成采用的正式多 seed rollout。
- **仍开放的 P1**：main 尚未在隔离克隆世界中逐周期消费 control/treatment 计划并生成 receipt、D7 command lineage 和干预后物理状态窗口。D6 尚未按该 lineage 形成 arm-complete physical outcome、paired non-degradation 或 degradation scenario 汇总。上述 producer/评估完成前，当前工作只证明合同能拒绝错误证据，不能证明 D4 学习候选有效或降级策略优于规则。

## 2026-07-22 保留 seed 候选门诊断与 D6 可用性审计

- **诊断 GAP 已关闭**：arm evidence 升级为 v2，保存 candidate confidence、`minimum_confidence`、OOD、latency/limit、finite，以及 confidence/OOD/latency/finite/external-failure 五项 gate。已评估候选分别使用 `candidate_low_confidence`、`candidate_ood_rejected`、`candidate_inference_timeout`、`candidate_output_nonfinite`；旧 generic reason 只兼容保留，不能单独解释拒绝。
- **旧证据兼容**：v1 reader 先验证旧字段集合和旧 manifest content ID，再迁移为新增诊断 unavailable 的 v2 对象。冻结 bundle、权重、manifest 和历史 v1 artifact 均未修改；当前正式 v2 证据位于独立目录，未知历史字段不回填。
- **安全门未降低**：默认 `minimum_confidence=0.6`、latency limit `50 ms`、OOD、finite、bundle identity、pair input、owner/version/epoch/lease、fault fence、coalition ACK、投影和 next-cycle consumption 语义不变。任一候选门失败仍执行确定性规则，`PPO/assist/authority=false`、`rule_fallback=true`。
- **正式 v2 独立审计**：权威 `formal_7891296` 绑定源提交 `78912963b67fe86ee9a8d29186b18a9dd60c460c`，`SHA256SUMS`/manifest SHA256 为 `821f1503...72bc`/`d6ef23b2...883c`。D6 独立重算确认 20/20 source clean 且 finite、truth 使用数 0、candidate considered 20/20。confidence min/mean/max 为 `0.508892953/0.563426384/0.569492280`，在 `minimum_confidence=0.6` 下通过 0/20；OOD、latency、finite、failure gate 各 20/20，aggregate 0/20，safe adopted 0/20，规则回退 20/20。执行时延 `treatment_candidate_latency_ms` 的 nearest-rank P95 为 `2.241315 ms`；门控汇总 `candidate_gate_summary.candidate_latency_ms` 的线性插值 P95 为 `2.264415 ms`，不得合并为单一 P95。
- **D6 sidecar 状态**：profile-bound v2 outcome-availability sidecar 已形成，目录为 `research_modules/d6_evaluation_metrics/outputs/reserved_seed_interventions_nominal_5v5_1000_1019_formal_7891296_d6_profile_bound_v2_audit_20260722/`，状态为 `pass_offline_assignment_comparison_only`。sidecar 文件 SHA256 为 `f3852251daf02ec87fe878e7fb80aad6f381d8c0756a5c956a32e737a3871c3b`，规范内容 SHA256 为 `c02a345c46ddc642dea7fb6bfcfb24184e7dc2a9f35b754c90324d074b445d2d`。源 manifest 的 `d6_outcome_sidecar_attached=false` 只保留生成时历史事实，不否定后续独立 sidecar。
- **验收**：配对专项 **33/33**、D4 全量 **482/482 passed**。新增测试覆盖四个单门、组合门、原阈值边界、v1 40-arm manifest 迁移，以及 rule fallback、pair input、bundle identity 和 next-cycle safety 不退化。
- **仍开放的 P1**：bundle manifest 明确声明 confidence head uncalibrated。后续只能在与训练和保留 seed 隔离的 calibration split 上评估 reliability/ECE/Brier，校准或重训 head 后以同一 0.6 门复验；不得使用本批保留 seed 降阈值。availability sidecar 已存在不等于 physical outcome sidecar 有值；runtime ACK、post-intervention physical outcome、paired effect/non-degradation、counterfactual、causal 和故障场景降级策略效果仍 unavailable。正式 manifest 固定 `formal_twenty_seed_performance_completed=false`、`PPO/assist/authority=false`，不能宣称候选有效、优于规则或具有降级策略效果。

## 2026-07-21 区域 reward 定义与消费合同

- **模块内下一步已关闭**：新增 `d4-region-resource-observational-reward-v1`、结果窗口和 provenance schema。适配器严格绑定 ACK v2、advisory/model fingerprint、source/applied plan、owner/epoch/lease/fault generation、ACK sequence/time、源/结果区域快照、执行/联盟首尾哈希和来源制品 SHA256。ACK 证据新增可选 `ack_bus_sequence`；reward 适配器要求该字段存在。
- **正式分项口径已冻结**：高威胁积压、配额满足缺口、转移完成缺口、备用不足、通信负载、分配冲突、降级失败和计划抖动均记录 raw value、单位、归一化分母、normalized cost、来源 SHA、availability/reason。缺测分项不补零。v1 使用 `min(raw/denominator,1)` 和加权平均成本；新执行计划取负成本作为时间窗口观测奖励，评估刷新只保留观测成本。
- **失败关闭**：缺 ACK、ACK 字段不完整、窗口重叠、旧 epoch/fault generation、lease 覆盖不足、source/current plan 不一致、owner 或区域清单变化、execution/coalition 首尾哈希变化、快照/制品/窗口 SHA 错误、truth/evaluator/actor 字段和必填项缺失全部 unavailable。已接受窗口按 episode/region 防重叠。
- **验收**：新增专项 19/19，运行时 ACK 与奖励专项 52/52，D4 全量 **449/449 passed**；新增/修改 Python 的 `py_compile` 通过。验证日期为 2026-07-21，场景是单区域 deterministic contract fixture 与既有 5v5 seed 41 ACK 集成回归，样本不属于 AirSim 或正式多 seed 数据。
- **证据边界**：`new_execution_plan_applied` 的 reward 只作非因果时间窗口归因；`evaluation_refresh_applied` 没有执行变化，不能形成动作 reward。两类都不自动等于 `CoalitionMemberAck`、control/physical outcome、counterfactual、causal、paired shadow 或 on-policy evidence。PPO、assist、authority 均为 false，规则回退为 true。
- **仍开放的 P1**：main/D6 尚未按新 schema 生产真实区域时序和不重叠窗口，冻结 900 episode 与 100 episode 课程没有 ACK/result 分项。保留 seed 1000-1019 已有正式 v2 隔离 execution receipts 和 D6 availability sidecar，但 sidecar 只提供同帧离线分配比较，没有 runtime ACK、区域 outcome 或 paired non-degradation。D6 当前 `runtime_plan_outcome_join` 是目标级、带离线真值的距离进展诊断，并显式声明 formal reward/causal unavailable；D4 已拒绝把它升级为区域 reward。完成真实 producer、带外哈希、多 seed paired/on-policy 审计前，不连接 PPO loader，不启动 PPO，不评审 assist/authority。

## 2026-07-21 区域建议运行时确认

- **D4 消费端缺口已关闭**：`d4-region-resource-runtime-ack-evidence-v2` 与 main-independent parser 已支持严格新执行计划和同代评估刷新两种 adoption kind。输入可以是 D4 advisory/result 或 `to_dict()`、main consumption mapping/envelope、D3 plan runtime ACK mapping/envelope、当前 D3/D7 source envelope；同代刷新额外要求 advisory source-plan envelope。
- **严格应用判据**：两条路径都要求 advisory/consumption 一致、`consumable=true`、无 rejection、D3 considered/applied/rejected 为 `true/true/false`、main accepted 和当前 D3/D7/hash/sequence/binding 完整。执行签名变化时必须提升 plan ID/version 并完整绑定 owner/epoch/lease；评估刷新必须同 plan ID/version、refresh-only flag 唯一为真、`execution_signature_changed=false`，且前后资源/航迹/coalition/version/member/区域 owner/未分配集合一致。评估刷新只沿用 D4 advisory 的有效 authority fence，不补造新的 D3 执行权限。
- **来源绑定**：D3/D7 envelope topic/source/schema/sequence 与 ACK 一致；D4 使用与 main 相同的规范 JSON 规则复算两个 payload SHA256。D3 assignments、D7 commands 和 ACK bindings 必须具有相同的资源/全局航迹键，全部命令到达 D7 并被 main control 消费。
- **失败关闭**：缺字段、重复 `(advisory_id, advisory_version)`、旧 advisory/plan/epoch/lease、严格 expiry、schema/source/hash 错误、applied/rejected 矛盾、source mismatch、部分或缺失 binding、非有限时间均返回稳定 reason/code，不改变 formal D4 authority、D3 plan 或 D7 gate。
- **验收**：原合同 28/28，真实 main 5v5 seed 41 集成与篡改 5/5，运行时专项 33/33，该阶段 D4 全量 **430/430 passed**；加入区域 reward 合同时为 **449/449 passed**。`py_compile` 通过。真实集成属于质点 episode，不是 AirSim 或物理验证。
- **仍开放的 P1**：冻结 900 episode 没有 v2 runtime evidence。D6 已能把 runtime ACK 按 occurrence 连接到目标级离线结果，但该结果仍是非因果诊断；区域 reward producer 和正式 paired shadow 尚未完成。`evaluation_refresh_applied` 不提供 `CoalitionMemberAck`、physical outcome 或 action-attributed reward，PPO、assist 和 authority 继续 false。

## 2026-07-21 区域调度全样本准入

- **D4 模块内 P1 数据准入缺口已关闭**：新增 `d4-region-resource-full-sample-admission-audit-v1`，对正式 900 episode 和 clean supplemental 100 episode 执行只读、失败关闭的全清单、全文件和全样本审计。正式数据未修改，补充课程未重生，未训练模型、未写入 `.pt`、未开放 assist 或 authority。
- **正式数据规模与规范 split**：900 episode、1798 frame/sample、14384 action；canonical train/validation/test 为 540/180/180 episode、1079/359/360 sample、8632/2872/2880 action。900/900 episode SHA256、1798/1798 数值有限和安全合同均通过。
- **补充课程规模与规范 split**：100 episode、300 frame/sample、1200 action；canonical 为 60/20/20 episode、180/60/60 sample、720/240/240 action。100/100 episode SHA256、300/300 数值有限和安全合同均通过；hold 100、request-replan 200、nonzero quota 200、transfer 100。
- **审计内容**：manifest/source/schema 和带外预期绑定、数值有限性、action inventory、配额守恒、transfer 邻接/通信/机动/容量、owner/plan/version/epoch/lease current 与跨帧单调、确定性安全投影、保留 seed、dirty 状态和在线真值隔离。违规数为 0，审计期间输入哈希保持不变。
- **main 审查口径已固化**：`target` 是教师标签容器，`target.kind=rule` 只表示规则教师标签，不属于 truth 泄漏；`recommendation.projected=true` 只表示后投影建议通过离线确定性合同，不是 runtime applied ACK。配额守恒按 action delta 总和及 transfer 净流量合同共同验证，不从缺失字段推断能力。
- **仍开放的 P1 跨模块准入**：显式投影前 action mask、被拒旧 plan/epoch/lease 候选、真实 `CoalitionMemberAck`、observed outcome、可归因 reward、同 seed paired shadow 均为 `unavailable/pending`。D6 还需按 tracked JSON 显式路径和带外 JSON SHA256 独立复核。审计内容 SHA256 为 `94f4f4bf914dde9fee0ce1d92ac491902019dd7388502fbee5f96c4edfac3e7f`，JSON 文件带外 SHA256 为 `4245f1db36f1af47259554f0770e75a3fe97fcc5e9b75c1b04c83d5bfb5c9e46`。
- **准入边界**：模块内 formal/supplemental/combined 状态为 complete；D6 external admission 仍 pending。`ppo_allowed=false`、`assist_allowed=false`、`online_authority_allowed=false`，确定性区域规则、lease/epoch 和安全投影仍是唯一可执行路径。
- **验收**：全样本审计专项 10/10，D4 全量 **397/397 passed**，验收门限为零失败。

## 2026-07-21 区域动作覆盖补充课程

- **P1 producer 缺口部分关闭**：D4 已在 owned paths 内增加独立 `d4-region-action-coverage-curriculum-v1` producer/CLI。它复用现有 `RegionResourceSnapshot`、`RuleRegionResourcePolicy`、`DeterministicResourceProjector`、dataset-v1 和 shared canonical registry，不修改 main/scalable3d 或正式 `learning_generation_v1_multibatchfix`。
- **覆盖结果**：正式注册表的 100 个训练 seed 各生成 hold、request-replan、transfer 三帧，共 100 episode/300 frame/1200 action。动作分布为 hold 100、request-replan 200、nonzero quota action 200、transfer 100；canonical 60/20/20 三桶均有四类正样本。
- **安全与隔离**：`hard_constraint_violation_count=0`、在线 truth key 数 0、保留 seed 1000-1019 出现数 0。训练 seed registry 和 shared registry 文件 SHA256 仍为 `2ab928a4...15f`、`68608d29...320f`，正式 900 episode 未写入。
- **clean 准入证据**：main 已在 detached clean worktree commit `9445ed6` 上重生课程。dirty episode 数为 0，dataset SHA256 为 `7e17aba...9e72`，canonical view SHA256 为 `9aa28765...cc8de`，`behavior_cloning_manifest_available=true`，canonical train 的 180 个样本可由 BC 只读 view 加载。首次 dirty 产物只保留为开发历史。
- **reward 与准入边界**：300/300 reward 和 outcome 显式 unavailable，PPO、online assist 和 authority 保持关闭。clean BC 数据准入不等于模型收益或在线策略准入，PPO loader 继续因 reward 缺失失败关闭。
- **剩余 P1**：冻结正式 episode 与补充课程采样比例；保留已完成的 D6 profile-bound availability sidecar 绑定，继续提供版本化、可归因 runtime ACK、outcome/reward、paired non-degradation、causal/counterfactual 和制品 SHA。完成前不得启动 PPO、评审 assist 或宣称学习策略优于规则。
- **验收**：课程专项 6/6，该阶段 D4 全量 **387/387 passed**；加入全样本审计专项后当时为 **397/397 passed**，运行时确认专项后为 **430/430 passed**，区域 reward 合同阶段为 **449/449 passed**，当前为 **482/482 passed**。

## 2026-07-21 共享 seed 切分消费端闭合

- **D4 侧缺口已关闭**：新增只读 `d4-canonical-region-seed-split-view-v1`，严格消费 `scalable3d-shared-seed-split-registry-v1`。消费者独立复现 D3 兼容排序和 60/20/20 分配，不导入 main runtime。
- **失败关闭条件**：schema、policy、ordering、unit、consumer contract、content SHA、assignment SHA、源 registry SHA、源 Git/schedule 元数据、seed catalog、split catalog 或 60/20/20 计数任一不一致均拒绝。100 个 dataset seed 必须完整覆盖且不得多出 seed；1000-1019 不得进入 registry assignment 或 dataset。
- **只读绑定**：canonical view 同时绑定原 dataset SHA `b06d741b...6158`、原 split SHA `18a2c600...7f0`、源 registry SHA `2ab928a4...15f`、共享 registry content SHA `29eb6895...146` 和 assignment SHA `31c6a3fc...ab5`。原 70/15/15 manifest、900 个 episode 及其 split 字段未改写；审计前后数据目录树 SHA256 均为 `8cde5cace4bd8106e35801f6179775ae39298592f3b556f712ea857b9c496bc1`。
- **正式视图结果**：60/20/20 seed 对应 540/180/180 episode 和 1079/359/360 frame，同一数值 seed 原子。BC loader 需显式传入 canonical view；默认 D4 70/15/15 行为保持兼容。
- **证据边界**：这是 development/data-governance 能力，不是模型性能证据。PPO 仍因 1798/1798 reward unavailable 而关闭，14384 个动作仍缺 quota/transfer/hold/replan 正样本，assist 和策略能力声明仍禁止。D3/D5 消费端、联合模型训练及外部 20-seed paired 评估不由本项自动关闭。
- **验收**：共享切分正反测试 12/12，该阶段 D4 全量 **381/381 passed**；加入动作覆盖课程专项后为 **387/387 passed**，加入全样本审计专项后为 **397/397 passed**，运行时确认专项后为 **430/430 passed**，区域 reward 合同阶段为 **449/449 passed**，当前为 **482/482 passed**。

## 2026-07-21 正式数据、行为克隆与准入审计

- **正式数据已审计**：D4 只读验证 900 episode、1798 frame、全部 900 个 episode SHA256、dataset/source/schema identity 和 70/15/15 数值 seed 原子划分。外部保留 seed 1000-1019 未进入训练、验证或内部测试；在线数据未发现 truth ID 泄漏。
- **动作多样性不足**：14384 个区域动作中的 nonzero quota、transfer、hold、request_replan 均为 0。reserve ratio 与 reconnaissance priority 存在变化，但配额、转移、保持和重规划的低误差或高准确率没有正类支持，不能作为调度策略能力证据。
- **D6 回报边界**：D6 正式审计确认 898/1798 帧只有无归因相邻状态转移，reward、causal、counterfactual 可用数均为 0。D4 未伪造 reward，也未把规则 target 或相邻状态变化改写成回报；PPO loader 继续失败关闭。D6 审计制品 SHA256 尚未绑定。
- **开发训练结果**：固定 seed `20260720` 完成 66 epoch，最佳 epoch 54，内部测试 loss `0.071545`；2026-07-21 准入复跑耗时 66.02 秒、推理 P95 `0.7774 ms`，权重 SHA256 `3da0360be8788f3ffeb8e9f9eba3e0d5369ec0bdf9e05729dfb1db07d71d5f62` 与首次训练一致。结果只证明训练、加载、推理和确定性投影管线可运行。
- **bundle admission**：manifest 与 model readiness 固化 `lifecycle_stage=development`、`maximum_advisor_mode=shadow`、`action_diversity_sufficient=false`、`strategy_capability_claim_allowed=false`、`reward_evidence_available=false` 及全部动作计数；即使调用方声明 20 个 unseen seed 也不能进入 assist。当前严格结论为“管线可用但动作多样性不足，shadow-only”。
- **仍开放的 P1**：独立 producer 已生成 quota/transfer/hold/replan 规则 teacher 正样本，clean 课程及 canonical BC 只读 view 已准入，但该课程不是正式状态分布。仍需正式/课程混合策略、D6 版本化 outcome/reward/causal/counterfactual 字段与审计制品 SHA256，以及外部 1000-1019 paired shadow。上述项目未完成前，不启动 PPO，不评审 assist，不宣称 learned policy 优于规则。
- **版本与验收**：权重和完整 bundle 位于 ignored `outputs/`，当前无 Git LFS；可跟踪结果只含配置、命令、指标、准备度、权重 SHA256 和本地定位。全样本审计专项 10/10 后为 397/397；运行时原合同 28/28、真实集成与篡改 5/5；区域 reward 专项 19/19 加入后为 449/449，候选门诊断阶段 D4 全量 **482/482 passed**，2026-07-25 当前全量为 **569/569 passed**。

## 2026-07-20 区域资源建议与 main 质点接线同步

- **main 接线事实已关闭旧表述**：main-owned scalable 3D 质点模块栈已消费 `d4-regional-failover-v1`，验证单一二级 owner、两个二级节点的多区域 owner、中心与二级连续失效后的 distributed D3 plan；D7 仅在 current owner/node、plan version、epoch、lease、commit mode 和 fault generation 下恢复导引。本轮只读定向测试 8/8 passed。该证据不是 AirSim、真实网络、硬件或长时 200v200 多 seed。
- **D4-owned 新能力**：`region_resource.py` 定义 truth-free、版本化、变长 `RegionResourceSnapshot` 和区域边；只输出区域 quota delta、邻边 transfer、备用比例、侦察优先级与 hold/replan，不含 actor truth ID、具体 target/member 或 resource-target assignment。
- **安全所有权**：`DeterministicResourceProjector` 重新构造 quota delta，保证总资源守恒、可通信/可机动邻边、最低备用、formal owner/plan/epoch/lease、fault fence、ACK/commit 和已提交联盟成员资源。学习层不能选择 leader、改变 health、生成 D3 plan 或授权 D7。
- **下一轮消费合同**：新增 `d4-region-resource-advisory-v1`、`RegionResourceAdvisoryContract`、`RegionResourceConsumptionView` 和一次性 `RegionResourceAdvisoryGate`。内容 SHA256 ID、默认 1.0 s 且受最早 lease 截断的有效期、source plan 集合、逐区域/transfer snapshot/owner/plan/epoch/lease、资源与 edge proof 已固化；main 只能在 current snapshot/formal verdict 重验为 `consumable=true` 后作为下一轮 D3 输入，D4 不修改 D3 plan。
- **消费 fail-closed**：旧 snapshot/plan/epoch、严格到期 lease、非 projected、ACK 不完整、fault fence、formal commit 变化、总量或逐区 transfer delta 不守恒、reserve/committed 未保护、未知/非邻接/不可用/超 capacity transfer 和 advisory replay 均拒绝。规则 fallback 与学习候选共享 advisor 内同一 `DeterministicResourceProjector`；学习模型只能返回 raw proposal。
- **学习研究管线**：规则基线、共享 node/edge 变长图 actor-critic、行为克隆、原生 clipped PPO、完整 episode/数值 seed 原子 split、bundle v2 + state_dict + SHA256、OOD/timeout/低置信/非有限/版本/SHA 回退和 paired shadow evaluator 已实现。API 默认 disabled、CLI 默认 shadow；少于 20 个未见 seed 不得 assist。
- **正式数据合同**：新增 `d4-region-learning-dataset-v1` 与公开 source/frame、stage/finalize/load API。source 固化 scenario/version/scale、数值 seed、episode ID、Git commit/dirty、config SHA；target/reward 必须 available 或显式 unavailable。完整 episode 是最小 split 单元，同数值 seed 的全部场景/规模/episode 同桶且三份 seed 零交集；唯一 seed 少于 3、unseen 少于声明、truth/evaluator key、哈希篡改均失败。BC/PPO loader 对 dirty、缺 target/reward 默认 fail closed，不补 0；bundle v2 可嵌入 dataset/split provenance。
- **合同阶段验证**：2026-07-20 建议/消费合同为 49/49，数据合同为 13/13，合计 62/62、当时 D4 全量 365/365 passed。该数字保留为历史合同证据；当前计数和正式训练证据见上一节。
- **新增/重分类 GAP**：D4 后投影消费合同、episode 数据合同、正式数据审计和 development checkpoint 已关闭到模块/离线开发层。main/D3 planning-loop 与跨进程 consumed-ID ledger 仍属于 main ownership。assist 资格、至少 20 个实际未见 seed、动作多样性、D6 回报/因果归因、paired backlog/transfer/churn/communication/fail-closed/safety/latency 结果、AirSim 和真实网络仍开放。

## 2026-07-20 scalable3d 区域化增量

- **已关闭的 D4 模块缺口**：新增 `d4-regional-failover-v1`，不导入 main-owned simulator 即可消费 `scalable3d-scenario-v1` mapping，按动态 resource/recon/region/task 数量输出 truth-free 逐区域 authority payload，并拒绝 schema 或声明节点数量溢出。中心未 `failed` 时保持中心 owner；中心失效后按区域 coverage + strict readiness + lease epoch 选择 `mobile_high_recon`；无有效二级节点时才进入 bounded capability/跨区域 capacity bid fallback。
- **安全合同**：owner/layer 变化要求 `epoch` 与 `plan_version` 同时提升，租约严格 `timestamp < expiry` 并收缩到 authority、D3 task 和二级 lease 的最早 expiry。中心、二级、distributed 任一 `k>1` candidate 都必须 required ACK 完整且 target/coalition/plan version、epoch、lease 一致后原子 `committed`；commit metadata 分别使用 `d3_center_assignment`、`d3_assignment_secondary_coordination` 和 `bounded_constrained_bid_selection`，只有 distributed fallback 使用最后一种 formation。缺 ACK、旧 authority/ACK epoch、旧 plan version、过期 lease 和任一层级网络分区均 fail closed。
- **输入证据**：逐任务显式消费 D1 covariance/measurement age、D2 ambiguity/IDSW/duplicate、D3 plan id/version/epoch/lease/current/feasible、D5 consistent/inconsistent/binding/friend/duplicate 及 member support/hold/ambiguity；D4 只复制上游 `global_track_id`。
- **验证日期/样本/结果**：2026-07-20，23 个确定性 pytest case，无随机 seed。五档参数分别为 5/20/50/100/200 region，每档构造相同数量 active task/resource metadata；其余 case 覆盖声明节点数上限、中心/二级连续失效、双区域 coverage、全层完整/缺失 ACK、D5 member hold、单成员多能力、跨区域 capacity、旧 generation、最早 lease 和全层分区。新增 23/23、当时 D4 全量 **303/303 passed**；候选门诊断阶段为 482/482，当前全量为 569/569。
- **仍开放**：长时 200v200 与多 seed 性能、真实 AirSim/RF/mesh/socket/时钟漂移/队列、D6 区域统计、物理拦截。bounded candidate formation 是确定性贪心，不是 CBBA 多轮共识或 CCBBA，也无全局组合最优、timing coupling、reserve 激活、补位/缩编/整盟重构。
- **所有权边界**：根级系统文档与 scalable3d/main 文件不在 D4 owned paths，本轮未修改，需 main 在集成时同步。

## 2026-07-15 M5N2 中心负对照增量

- 真实 AirSim M5N2 baseline/candidate 各 10 seeds，共 20/20 case 完成；`active degradation=0`，中心 owner 持续有效。
- coalition completion `0/20`、第二 primary 5 m 成功 `0/20`，20 个第二 primary 均为 `collision_stop`。collision object 未持久化，故不能把该终态解释为成员冲突或自动转成 D4 主动降级动作。
- 该批只增加“中心继续执行且不误降级”的负对照证据，没有执行 secondary takeover 或 distributed commit；真实二级/完全分布式多 seed 继续是 P1。
- 验收口径：`active degradation=0` 且 center owner current 的负对照门限满足；第二 primary 进入 5 m 且 coalition 完成的物理门限未满足；fallback 性能门限因未执行而 unavailable。
- D4 main-bus 阶段 mean/P95/max 约 `5.59/6.70/94.10 ms`，不是系统 control tick 超时的主要来源。
- `png_ttc_2v2_seed001` 排除在 M5N2 聚合之外；dropout case 为 0，不以缺失 case 补零。

**审计范围**：本文件只审计 D4 分布式协同与降级接管模块，对照 `subagent_reviews/MAIN_IMPLEMENTATION_GAP_AUDIT.md`、`subagent_reviews/D4_DISTRIBUTED_FALLBACK_REVIEW_AND_PLAN.md`、`C_UAS_MAINSTREAM_SOLUTIONS_AND_DIFFICULTIES.md`、以及 `research_modules/d4_distributed_fallback/` 当前代码、README、PLAN、文档和测试。
**修改边界**：本次只更新 D4 GAP 审计结论；不修改 `MAIN_IMPLEMENTATION_GAP_AUDIT.md`，也不修改 D1/D2/D3/D5/D6/D7 或 runtime 代码。
**安全边界**：结论仅用于离线科研仿真、接口补齐、AirSim ComputerVision dry-run/stress 规划和后续工程排期；不涉及真实通信链路、飞控、硬件、火控、毁伤、自动处置或授权绕过。

## 2026-07-15 P0 公开 secondary takeover 入口闭合

P0 已关闭：`FailoverCoordinator`、`AirSimEpisodeCommunicationAdapter` 和 `CoalitionCommitCoordinator` 的 secondary proposal 统一消费 strict readiness evidence；current time、lease epoch/expiry、fresh heartbeat/cue/communication、gimbal=true、coverage >=0.65、network full-view >=0.80 和 sustained readiness 缺一不可。`build_d7_secondary_handoff()` 与 `build_secondary_takeover_plan_metadata()` 也已改为 active secondary evidence exact-true：expected/actual source、plan/required lease epoch、expiry/current time 必须显式存在并满足合同，同一 active plan 维持不豁免。

2026-07-15 当日 D4 全量验收阈值为零失败，结果 280/280 passed。此前 278/278 未覆盖两个公开 helper 的 sustained/source/epoch `None`，不能证明所有公开入口闭锁；新增逐字段 `None`、完整正例、same-plan 维持和 distributed bypass 后才关闭该 P0。该历史计数先由 303/303、430/430，再由当前 482/482 回归取代，P0 判定不变。

## 2026-07-14 P0 secondary lease fail-closed 闭合

新确认的 P0 边界已关闭：secondary resource candidate、plan 发布/维持、active owner 消费和 D7 handoff 统一要求 expiry/current time 均存在且严格 `current_time < expiry`。缺 expiry、缺 current time、`now == expiry`、`now > expiry`、旧 lease epoch 和 source mismatch 均不可发布或维持 executable secondary plan；active secondary owner 失效时转为 `hold_review`。中心健康、主动降级策略及 heartbeat/readiness/cue/gimbal/link 门控未改变。

该轮 2026-07-14 历史验收为 211/211 passed；2026-07-15 的 278/278 与 280/280、区域阶段 303/303、建议管线阶段 335/335、消费合同阶段 350/350、共享切分阶段 381/381、课程阶段 387/387、全样本阶段 397/397、运行时确认阶段 430/430、候选门诊断阶段 482/482 都是历史结果，2026-07-25 当前 D4 全量为 569/569。未运行新 AirSim episode。member replacement 仍只是测试手工给定替换成员后的 replay，不是自主 reserve 激活、补位、缩编或整盟重组。

## 2026-07-13 P1 episode-time 故障验收增量

D4 已把原四场景 replay 扩展为 7 个规范 episode-time 场景：`normal`、`center_failure`、`center_secondary_failure`、`missing_ack`、`stale_epoch`、`expired_lease`、`partition`。`center_secondary_failure` 现在严格先完成二级 `executing`，再注入二级 heartbeat loss，随后以更高 plan/coalition version 和 epoch 发起 peer 原子提交，不再用“中心与二级同时不可用后直接 distributed”替代顺序接管验证。

模块内 0.25 s tick 验收为 7/7 通过：normal false degradation=0；中心故障注入到二级 executable=1.25 s，满足 <=1.5 s；二级故障注入到 peer atomic executing=1.00 s，满足 <=2.5 s；缺 ACK、旧 epoch、过期 lease 和 partition 全部 fail closed。每 tick 均可审计 `owner_id`、`plan_id/version`、`coalition_id/version`、`epoch`、lease expiry/remaining/validity、required/acked/missing members 和 commit reason。矩阵和 case 输出固定携带 `validation_scope=episode_time_fault_injection`、`real_rf_network_validated=false`、`real_hardware_validated=false`。

在此基础上，2026-07-13 AirSim episode clock 批量矩阵对 `normal`、`center_failure`、`center_secondary_failure`、`delay_0_5s`、`loss_30pct` 和 `partition_recovery` 六类场景各运行 10 seeds，共 60 case。60/60 safety outcome 通过，`false_degradation_count=0`、`duplicate_owner_count=0`、`split_brain_prevention_failure_count=0`；30% loss 下 7 个缺 ACK case fail closed，3 个完整 ACK case 才执行。该结果关闭 D4 当前 episode-time 多 seed 安全矩阵缺口。

该增量不构成真实 RF、mesh、socket、链路设备或硬件故障验证。剩余 P1 是实际吞吐带宽和拥塞、节点时钟漂移、操作系统与网络排队抖动、乱序/重传时序、secondary-interceptor/peer 真实链路以及长时间恢复统计；需要独立链路仿真器、网络仿真或硬件条件。该 2026-07-13 增量阶段 D4 全量回归为 198 项通过。

## 总体结论

D4 所属 P1 合同层已闭合。2026-07-11 ComputerVision 总体验收为 8/10；二级协调者 `Secondary_Recon_1` 以 ACK 3/3 进入 `executing`，完全分布式 `INT-02` peer 以 ACK 3/3 进入 `executing`，确认窗口显式截止后的缺 ACK 场景以 2/3 ACK 进入 `aborted` 并令 T001 三成员 `hold_for_review`。2026-07-25 后，截止前普通快照保持 `collecting_acks`。因此 secondary/distributed commit 正例和缺 ACK fail-closed 都属于已通过，不再列为当前缺口。

状态分层如下，后续审计不得合并这些口径：

| 层级 | 状态 | 审计边界 |
|---|---|---|
| scalable3d 区域合同与质点接线 | **D4 合同及 main 质点接口已完成** | 区域阶段 23/23、main 定向 8/8；覆盖单二级、多二级 owner、distributed D3 plan 和 D7 fencing。不等于 AirSim、真实网络、长时 200v200、多 seed、全局组合最优或完整 CCBBA |
| 区域资源建议、episode 数据、开发训练与 next-cycle 消费合同 | **D4 接口、clean 补充课程、development checkpoint、严格 runtime ACK 消费端和区域 reward schema/适配器已实现；D4 全样本准入 complete，D6 external admission 仍 pending** | 全样本专项 10/10、runtime ACK 专项 33/33、reward 专项 19/19、D4 全量 449/449；规则教师 target/projected 不代表 runtime ACK。新执行计划需严格更新的 plan ID/version 与完整 owner/epoch/lease；同代评估刷新需 source-plan envelope 和不变 binding，且不能获得动作 reward。冻结数据无 v2 ACK/result window，paired shadow 和 D6 外部复核仍缺失，bundle 强制 shadow-only |
| P1 合同层 | **已完成** | 已关闭 secondary/peer 3/3 ACK `executing` 正例和显式截止后 missing ACK 2/3 `aborted` fail-closed；不等于自主成员形成或物理执行完成 |
| P1 扰动合同矩阵 | **模块 replay 已完成** | `d4_p1_failover_disturbance_replay_v1` 九场景 9/9 通过，覆盖正常中心、secondary takeover、missing ACK、member replacement、partition recovery、stale epoch、expired lease、digest conflict 和 center recovery dual-track audit；不生成 `AssignmentPlan`，不降低外部 gate |
| P1 episode-time 批量验收 | **已完成** | `d4_airsim_episode_communication_v1` 支持逐 tick 输入；2026-07-13 六类、10-seed、60-case 矩阵为 60/60 safety outcome，误降级、重复 owner 和 split-brain prevention failure 均为 0。该结果仅覆盖 AirSim episode clock 故障注入 |
| P1 真实网络/长期标定 | **仍开放** | episode-time 注入不能替代真实带宽、拥塞、时钟漂移、网络排队/抖动/乱序/重传和 RF 链路；secondary-interceptor/peer 实际网络与长时间恢复仍未闭合 |
| D4 P2 optional benchmark | **本轮未完成实际外部 benchmark** | `P1_P2_VALIDATION_SUMMARY_CN.md` 的 P2 结果仅列 D2/D5/D6/D7，没有 D4；D4 现有 cost-gap helper 仅为离线单场景接口/单元测试，不是 MIT/CA-CBBA adapter 验收 |

P2 后续只允许隔离式 benchmark，不替换本地轻量 CBBA、commit lifecycle 或 ACK/lease/epoch 门控。D4 的 ComputerVision 故障注入、summary adapter、内存网络和本地轻量 CBBA属于合同验证/adapter/研究近似；默认在线路径没有被外部算法替换。

D4 当前已具备 `C2Health`、被动降级、主动降级仲裁、固定系留/机动高空二级节点摘要、二级节点 lifecycle、secondary takeover plan lifecycle metadata、通信 freshness、D1/D2/D3/D5 evidence adapter、主动降级 review label、plan activation delay、D5 distributed visual evidence 风险加权、CBBA cost gap helper、D6-compatible metadata、轻量 CBBA、中心恢复合并、按输入列表长度运行的仿真入口和 main 可复用的逐 tick episode 通信状态接口。

2026-07-13 主动降级层级已按当前系统策略闭合：中心可用时，低风险保持 `continue_center`；进入末端窗口后的持续 D5 视觉软不一致先输出 `request_secondary_assist`，event 明确区分 `secondary_assist_requested` 与 `secondary_takeover_candidate`，并保持中心 plan owner/version。只有形成明确硬失配或当前计划不可继续时才输出 `request_center_replan`，D4 仍不直接转移 owner。新增 `terminal_evidence_applicable` 后，远距未进入末端窗口的视觉软证据和 streak 不再逐帧请求辅助；中心正常/current/feasible 且 binding 安全时，仅含 D1/D2/D3 非 hard-active 因子的组合也继续中心并保留风险审计。只有 C2 health 进入 `failed` 才允许 secondary 接管，二级随后失效或不可用才进入 distributed。该阶段只记录 fallback generation 的 ACK 门，D4 全量测试为 193 项；2026-07-20 区域合同已将完整 ACK、epoch 和 lease 原子门扩展到中心、二级、distributed 三层全部 `k>1`，当前总数见本文顶部。

### 历史实施记录（不作为当前状态）

历史状态（2026-07-11 原子 commit 实施前）：高威胁目标要求 `k_j=3` 时，single-winner `CBBANegotiator` 不能被解释为多机联盟分配。基础 CBBA 是成熟分布式基线，但 CCBBA、consensus-based grouping 和 distributed coalition formation 的公开代码成熟度不足。当时该项作为跨 D3/D4/D6/D7/main 的 P1 合同缺口；当前原子 commit 合同已关闭，成员形成、重构、恢复和时序可达性仍开放。证据见 `D4_M_TO_N_DISTRIBUTED_COALITION_REVIEW.md`。

2026-07-11 原子联盟安全语义已落地：`CoalitionSafetyEvidence` 可序列化输出 D3 schema v2 的 plan/coalition version、需求、完整性、授权成员、锁成员和冲突原因，并可选消费 `CoalitionCommitState`。冻结 `CoalitionMemberAck`、`CoalitionCommitState` 和轻量 `CoalitionCommitCoordinator` 已实现版本/epoch 单调、成员 ACK、lease、分区和 digest 门控；该历史阶段先要求 secondary/distributed 全部 required ACK 且 lease 有效。2026-07-20 区域合同进一步要求中心、二级和 distributed 三层全部 `k>1` 原子提交，并分别记录真实 assignment/formation source。无有效 commit 保持 `coalition_fallback_unsupported`/`hold_or_revoke`。合法联盟内多个授权资源锁同一 `global_track_id` 不再计 duplicate；联盟外/超额成员及旧 plan/coalition version fail closed。最新真实 episode 已关闭 secondary/peer commit 正例与缺 ACK 负例；中心层新增证据仍是模块测试。reserve 激活、成员补位/缩编、完整重构/恢复矩阵仍是后续 P1。

真实 AirSim 目录 `blocks_cv_m5_n2_cooperative_live_20260711` 证明需要对“最终动作”再次门控：中心 alive/owner=center，T001 demand required/assigned 为 3/3、coalition complete、version current，但 D5 长期 reacquire 后 D4 曾输出 `degrade_to_distributed`。该结果不能解释为可执行联盟 fallback，因为现有 distributed 仍是 single-winner；修正后同类候选在中心可用时请求 D3 重规划。

2026-07-11 中心重规划请求 lifecycle 的 D4 模块缺口已闭合：公开冻结 DTO `CenterReplanStatus` 及稳定 risk-signature helper，adapter 只读消费四态请求。默认 cooldown 为 2.0 秒，以 `resolved_at` 或 pending 的 `requested_at` 为起点；窗口内新增 medium ambiguity 等非硬风险仍 suppress，严格边界到期后才重新请求。持续 `terminal_persistent_disagreement` 只负责首次请求和风险分类，不绕过 cooldown。expired、center failed 和 friend/非法重复锁/assignment-version/IDSW/coalition conflict 不受冷却。事件保留 request/status/current signature/是否恶化/是否抑制/绕过原因及 cooldown seconds/until/active。D4 的 `continue_center` 不清除 D5 不一致，D5/D7 gate 仍独立；`k>1` 原子联盟 fail closed 与 `k=1` 兼容均有回归。

2026-07-11 assignment freshness 误判缺口已闭合：稳定 plan identity 不再因 `created_at` 超过 4 秒自动 stale。adapter 优先使用 metadata 最近评估时间计算活性 `plan_age_s`，缺失字段保持原 `created_at` 回退；identity age、age reference 与 reference timestamp 保留在 assignment evidence metadata。阈值仍严格使用 `plan_age_s > stale threshold`，stale 后原 hard-risk 与 cooldown bypass 语义不变。

历史基线（2026-07-11 最终 P1 验证前）：M-to-N ComputerVision 三 seed 证据进一步确认中心重规划 lifecycle 已闭合；seeds 7/17/27 均为 replan request 6、no-change ACK 6、applied 0、expired 0，需求满足率 1.0，错误重复锁 0。T002 共识帧为 4/5/4，D7 每 seed 获得 2 次终端合同许可；T001 双 primary 共识均为 0。当时二级 active plan 和完全无中心原子联盟仍列为 P1；该状态已被最新 3/3、3/3、2/3 故障注入验收取代。ComputerVision 流程成功不得表述为物理拦截完成。

仍需明确的是：D4 本体只输出仲裁结果，不直接控制 D3/D7。2026-07-08 main runtime bus 已经接入 `D4ArbitrationAdapter.evaluate()`，能在收到 `request_center_replan` 后触发下一轮 D3 plan version，把 D4 event 写入 D6 collector，并已把 secondary takeover owner/version 回灌到 D3/D7；controlled 2v2 secondary visual PNG 回归已通过。main runtime 已新增 P1 D4/D5 calibration sweep，可批量改变二级节点高度、FOV、数量和 standoff，且 sweep 结束后自动生成 D6 标准 AirSim calibration report bundle。D4 仍没有真实通信/视频链路，也没有引入 MIT CBBA、CA-CBBA、独立 auction 或 contract-net。`degrade_to_secondary` 是二级接管/重分配触发语义，系统级 plan 发布、owner/version 消费和 D7 gate 由 main/D3/D7 负责；修复后口径保持为 D4 只输出 pending/active metadata 与仲裁记录，不生成系统级 `AssignmentPlan`。完全无中心模式现在使用 D5 视觉证据调节轻量 CBBA 出价，不构造虚拟中心 Hungarian，不改写 `global_track_id`。

2026-07-12 P0/P1 复核当时无 P0 blocker。P0-B 已在 D4 模块内闭合到单元测试层；heartbeat smoothing、secondary readiness/lease/source、主动降级防抖、中心重规划 lifecycle、assignment freshness 和原子联盟 ACK/commit 合同均有回归。D4 区分“末端暂时看不清/重捕获”和“末端观测与分配冲突”，并要求 `k>1` fallback 具有有效 atomic commit。D4 record/D6 metadata 已增加 commit state、epoch、coordinator、required/acked/missing member、lease 和 `atomic_coalition_formed`；恢复双轨 digest 不一致只进入审计。新增 P1 确定性扰动 replay 后该阶段 D4 测试 155 项通过，九场景 9/9 满足预期，并包含四成员规模无关回归；当前测试总数见本文顶部。

### 2026-07-12 P0/P1 状态增量

本节依据 commit `33e6fa0` 后当前 D4 代码/测试、`subagent_reviews/MAIN_IMPLEMENTATION_GAP_AUDIT.md` 和 `research_modules/airsim_runtime/outputs/PNG_DELIVERY_ENHANCEMENT_AIRSIM_VALIDATION_REPORT_20260712.md`；只更新 P0/P1 判定，不改 P2/P3 规划。

| 核对项 | 当前判定 | 2026-07-12 证据与边界 |
|---|---|---|
| P0 terminal plan-binding 一致性 | **已修复，保持回归** | posefix smoke 证明旧逻辑仍把 D5 readiness 当作 binding：四组历史输出各有 1087/1094/585/1064 条无 hard risk 的 false，并导致 158/112/113/122 条控制拒绝。现 `terminal_consistent` 只由 current resource/global-track/version/coalition binding 与 friend/duplicate/mismatch 决定；持续失锁只请求 cue，不单独置 false。D5/D7 lock/handoff 仍独立 |
| P0 hard mismatch/stale gate | **已实现，保持回归** | resource/global-track mismatch、friend、duplicate、not-current/stale plan 和显式 resource infeasible 均不允许二级 readiness 改写中心 owner；observed mismatch 达到 `mismatch_frame_limit/risk_window` 后请求中心重规划，单窗口暂态仍防抖 |
| 其他 P0 合同 | **无行为变化、保持原状态** | heartbeat smoothing、secondary readiness/source/lease/epoch、center-replan cooldown/lifecycle、D2 truth 隔离和 `global_track_id` ownership 本轮未改；没有新增 P0 blocker 或新增完成项 |
| P1 原子联盟 commit/ACK | **合同层仍已完成；异步收集语义已更新** | secondary ACK 3/3 `executing`、peer ACK 3/3 `executing`、显式截止后 missing ACK 2/3 `aborted` 仍是正负例；截止前普通快照保持 `collecting_acks`。PNG delivery 工作未改变 commit、epoch、lease、digest 或 recovery 行为 |
| P1 真实运行与长期标定 | **部分实现，仍开放** | 早期 PNG delivery 的 M5N2 `0/9` 是历史短窗口结果；最新中心继续执行 paired 负对照已完成 20/20 case，coalition 和第二 primary 5 m 均为 0/20，`active degradation=0`。该批没有 secondary/distributed 动作，不能关闭 D4 完整扰动、成员重构/恢复、误降级成对标定或物理协同缺口 |

下一验收条件：main 复用已完成的 M5N2 20-case 几何/seeds，增加中心失效、中心与二级连续失效和 D1/D2/D3/D5 可审计主动风险 paired case；同时补充 collision object/source lineage。验证所有无硬冲突 reacquire 保持 binding、D5/D7 仍独立阻止未锁定 PNG，并对任意 mismatch/friend/duplicate/stale-plan/version/ACK/lease 保持立即阻断；报告 D4 action/reject、错误绑定、active-primary、coalition completion、误降级和恢复。旧 epoch、过期 lease、成员不可执行、分区恢复、digest conflict 和成员补位已由版本化模块 replay 固化，六类 episode-time 的 60-case 批量安全矩阵也已完成；其余 P1 为真实带宽、时钟漂移、网络排队/抖动/乱序/重传、secondary-interceptor/peer 实际链路与长时恢复统计。

历史基线（2026-07-10，非当前状态）：`research_modules/airsim_runtime/outputs/p1_gap_closure_calibration_20260710/` 及其 50/200 m case 目录包含 10 seeds、3 个二级节点、FOV 110 度、1920x1080，共 60 个 5v5 case。20 个 `degrade_to_secondary` case 的最终帧和 dominant action 均为 `degrade_to_distributed`。50 m/200 m 的 network joint full-view 均值为 0.023/0.000，coverage 均值为 0.685/0.708；projection valid 均为 1.0，cross-view association 均值为 4.6/4.0，stable registration 均值为 86.3/96.7，not-registered 均为 0。该批次表明当时注册链已显著改善但同帧全覆盖不稳定；它不否定后续 secondary 3/3 ACK `executing` 合同正例，也不能作为当前接管率。

同一历史基线中的 1300 条 secondary-case D4 决策提供了门限级证据：heartbeat/link/cue/gimbal、visible 和 registered 全部通过，capability score 无低于 0.70；1285 条的 network full-view < 0.80，因而 readiness 为 `registration_usable`，其中 600 条同时 coverage < 0.65。仅 50 m seed 2/5 的三个 frame 产生 15 条 `takeover_ready` 记录，但均为 `pending_secondary_plan`，0 条 `secondary_plan_active`、0 条 executable，随后回落 distributed。该历史数据用于冻结门限解释，不代表最新 commit 正例仍未闭合。D4 保持这些硬门限，并新增默认 3 个不同时间戳决策、至少 0.2 s、evidence gap <= 1.0 s 的持续 readiness gate；单帧和同时间戳重复判定均不能接管。

逐决策证据的 D4 输出缺口已闭合：lifecycle/event 现在同时记录 stable/not-registered value、presence、`registration_evidence_source`、streak、since/duration、sustained 和 fallback reason，明确标识 D5/resource 显式计数与 cross-view compatibility 回退。历史 1300 条 D4 input 的两个显式计数仍为 `null`，所以剩余的是 main/D5 真实接线缺口，不是 D4 字段缺口。

D4 模块内 pending/active 合同也已补齐：只有 sustained readiness 才能进入 pending；active 还要求 source 与选中二级节点一致、plan version 单调或保持同一已激活 secondary plan、plan lease epoch 不低于节点要求且 lease 未过期。原子联盟、center-replan recovery 和 D2 duplicate score/count 分离测试覆盖正常中心、secondary/distributed commit、缺 ACK、旧 epoch、过期 lease、重复/非成员 ACK、能力撤销、分区、digest 冲突、soft pending recovery、continuous risk=0.8/count=0、explicit count=1、stale visual coalition version 和 center failure；2026-07-11 当时为 144 项通过，2026-07-12 增加 terminal consistency 回归后当前为 148 项通过。真实 AirSim 的 secondary/peer commit DTO 与 action 正负例已经接线，2026-07-13 episode-time 六类 60-case 网络故障矩阵也已通过；剩余 P1 是物理执行、coverage-cell 长期聚合、成员退出/补位/缩编/整盟重构，以及真实带宽、时钟漂移和实际网络时序下的长期验证。

2026-07-12 通信 replay 更新：D4 新增 `d4_p1_communication_fault_replay_v1`，在不修改 main runtime 的前提下完成 normal、0.5 s delay、30% loss、center failure、center+secondary failure、partition+recovery 六类 10-seed 内存通信矩阵。60/60 case 满足安全预期，正常误降级、重复 owner 和 split-brain prevention failure 均为 0；30% loss 的 7 个缺 ACK case 全部 fail-closed，3 个完整 ACK case 才执行；分区恢复 10/10 使用新 generation 全量 re-ACK。逐 case 已输出 main/D6 可消费的层级轨迹、owner/version、ACK/lease/epoch、首个失败原因、消息、退出/重构和恢复字段。加入 posefix terminal consistency 回归后该阶段 D4 全量测试为 167 项通过。2026-07-13 已进一步在 AirSim episode clock 批量矩阵中确认相同六类场景 60/60 safety outcome；当前测试总数见本文顶部，真实网络带宽、漂移和时序仍保持 P1。

历史 smoke（2026-07-11、最终故障注入验证前）：`p1_runtime_truth_isolated_d4d5_smoke_20260711`（200 m、2 secondary）、`p1_runtime_truth_isolated_d4d5_50m_20260711`（50 m、2 secondary）和 `p1_runtime_truth_isolated_d4d5_secondary5_20260711`（200 m、5 secondary）中，中心保持正例均为 `continue_center`，二级不可用负例均为 `degrade_to_distributed`。三组预期二级接管正例当时同样为 `degrade_to_distributed`，其共同证据是 `secondary_network_joint_full_view_frame_rate=0.0`、readiness 非持续 `takeover_ready`。5-secondary 配置虽把 `secondary_network_mean_coverage_ratio` 提升到约 0.80，仍未形成同帧全目标联合覆盖。该历史结果说明安全回落正确并冻结 readiness 门限；二级 3/3 ACK `executing` 正例现已由后续验证关闭，但平均覆盖、累计检测或单帧可见性仍不能解释为 active secondary plan，也不得用于降低门限。

本轮 D4 P1 校准口径补充：D4 把二级侦察结果解释为四级 readiness，而不是把“检测可见”直接当成“可接管”。`not_ready` 表示 coverage、heartbeat、link、cue、lease 或 gimbal 不足；`visible_only` 表示二级可见但未注册，常见证据是 `secondary_detect_available_but_not_registered=True`、`cross_view_association_count=0`、`not_registered_count>0` 且无稳定注册，或 reject reasons 指向 global binding/registration 断点；`registration_usable` 表示已有 stable registration/cross-view support，但 `secondary_network_joint_full_view_frame_rate`、coverage 或综合 score 仍不足以接管；`takeover_ready` 才作为 `degrade_to_secondary` 接管依据。D4 event 顶层输出 readiness `secondary_capability_class`，lifecycle 保留节点类型字段并新增 `secondary_readiness_class` 与 `secondary_capability_inputs`；D7 handoff 必须看到 `secondary_capability_class=takeover_ready`。系统级 plan owner/version 仍由 main/D3 回填。

## EVAL P0/P1 同步

本节仅同步 `EVAL/FRAMEWORK_EVAL_P0_P1_P2_GAP_CONFIRMATION.md` 中已经确认的 D4 P0/P1 条目，不改变下面“已实现/部分实现/未实现”表中已经完成的状态，也不调整 P2/P3 对照项。当前没有新增运行级 P0 blocker；已实现的 P0 项按“保持回归”处理，若后续出现未完成 P0，只能列为 P0 backlog 并绑定明确验收口径。

### P0-B 降级层级硬化

D4 的 P0-B 硬化继续按四级层级解释，不把单个传感器或终端软证据直接提升成完全分布式降级，也不绕过 D3/D5/D7 gate：

1. **中心正常**：`continue_center` 是默认路径；heartbeat 短时抖动先进入 `suspect/degraded` 观察，不直接判定中心失效。
2. **主动重规划**：中心仍可用但 D1/D2/D3/D5 证据显示硬风险时，D4 只输出 `request_center_replan`，由 main/D3 发布新版本计划；主动降级防抖继续依赖 dwell/release、硬/软风险分层和三值 review label。
3. **二级节点接管**：中心失效或需要二级接管时，D4 输出 `degrade_to_secondary` 和 pending/active metadata；可接管性必须同时审计 coverage、freshness、stable cross-view registration、not-registered 断点、lease/epoch 和 source node。
4. **完全分布式降级**：只有中心不可用且二级节点不可用、不可达或覆盖不足时才进入 `degrade_to_distributed`；当前默认仍是本地轻量 CBBA 保底，不构造虚拟中心，不改写 `global_track_id`。

| EVAL P0-B 条目 | D4 当前状态 | 同步后的缺口/验收口径 |
|---|---|---|
| Heartbeat 平滑 | 已完成，保持回归。`FailoverCoordinator` 新增 heartbeat sliding window、miss threshold、`degraded/suspect/failed` dwell；有 heartbeat 样本流时，短时丢包/延迟先进入 degraded/suspect，不直接 failed | `tests/test_health.py::test_heartbeat_window_suppresses_single_delayed_sample_before_failed`；真实 AirSim false failover rate 仍属于 P1 多 seed 校准 |
| Lease/epoch 严格合同 | 已完成 D4 合同层，保持回归。除 expiry/version 外，现校验 plan source、required lease epoch、sustained readiness，并记录 transition/timing/fallback；过期/stale lease、错误 source、能力回落均不可执行 | `tests/test_arbitration_adapter.py::test_active_secondary_plan_rejects_stale_lease_epoch_and_wrong_source`；`::test_active_plan_rolls_back_on_expired_lease_and_capability_regression`；系统级计划仍由 main/D3/D7 负责 |
| 二级能力评估 | 已完成 D4 合同层，保持回归。瞬时四级 readiness 后增加默认 3 decisions/0.2 s 连续窗口；相同 timestamp 不累计；not-ready 边沿和回落后重新初始化 since/count。lifecycle/event 输出逐决策 registration source/presence、streak/duration/sustained/fallback；D7 helper 可显式拒绝未 sustained 的 `takeover_ready` | `tests/test_arbitration_adapter.py::test_default_readiness_window_blocks_single_frame_takeover_and_audits_evidence`；`::test_readiness_window_restarts_after_not_ready_edge_and_after_regression`；`::test_sustained_readiness_enters_pending_then_active_with_transition_timing` |
| 主动降级防抖 | 已完成 D4 合同层，保持回归。迟滞按 `(resource_id, global_track_id)` 隔离；`terminal_evidence_applicable=false` 且中心正常时，窗口外视觉软证据、streak 和仅含 D1/D2/D3 非 hard-active 因子的组合不触发辅助，风险仍进入 D6；进入窗口后的持续无硬冲突 reacquire 才可请求 cue。高 D1/D2 事件风险和硬安全/绑定冲突始终有效 | `tests/test_active_degradation.py::test_far_range_midcourse_d1_d2_d3_soft_risks_continue_center`；`::test_far_range_high_track_uncertainty_keeps_secondary_assist_path`；`tests/test_arbitration_adapter.py::test_adapter_keeps_far_range_airsim_soft_risk_combination_on_center`；真实 false trigger rate 仍需 main 重跑同目录 P1 多 seed 标定 |

### P1 边界

以下 D4 条目按 EVAL 保留为 P1 后续项。它们用于增强网络退化、选举对照、分布式通信效率和通信统计可信度，但不提升为当前 P0，也不替换现有四级降级主线。etcd/Raft/SwarmRaft/DDS 是对照或后续工程化方向，不是当前 P0 强依赖；任何 P1 对照只能丰富 D4 record/D6 统计，不能绕过 D3 plan version、D5 身份/终端 gate 或 D7 handoff gate。D4 主链路 action 合同仍保持 `continue_center`、`request_secondary_assist`、`request_center_replan`、`degrade_to_secondary`、`degrade_to_distributed` 和必要时的 `hold_for_review`。

| EVAL P1 条目 | 当前边界 | 验收口径 |
|---|---|---|
| Raft/SwarmRaft leader election 对照 | 当前默认是二级接管排序和轻量 CBBA，尚无成熟 Raft/SwarmRaft leader election 对照；P1 只能作为可复现实验对照，不替代 `degrade_to_secondary`/CBBA 默认路径，也不要求当前集成 etcd | 选举日志可回放，leader change、term/epoch、timeout、conflict 与二级接管结果可被 D6 统计，且不产生执行绕过 |
| Event-Driven CBBA 通信优化 | 当前本地轻量 CBBA 已有 round/message/conflict 统计和内存网络 packet loss/delay，但仍按现有协商节奏运行；P1 只评估事件触发消息减少，不替换 no-center 默认保底语义 | 同一任务/资源输入下输出 baseline vs event-driven 的 message count、consensus rounds、conflict rate、completion rate 和 cost gap，且不改写 `global_track_id` 或 D3 plan owner |
| 网络分区检测与恢复韧性指标 | D4 模块内已完成分区 fail-closed、新 generation 全量 re-ACK、旧 owner 拒绝、重复 owner/split-brain prevention 和恢复时间摘要；尚缺真实 episode 的 peer view/digest 差异和长期韧性聚合 | main 在 AirSim 分区注入下复用当前 summary，D6 聚合 conflict、peer digest、merge audit、恢复时间和 `resilience_score`/等价指标 |
| 误降级/漏降级标定 | 已有 false-trigger metadata、三值 review label、pre/post review window 和 D6 active-degradation precision 字段；现有 60-case 正常 freshness 基线不足以形成成对故障真值 | main/D6 用同 seed 正常/故障成对场景输出 false-degradation rate、missed-degradation rate、动作混淆矩阵、dwell/release 抖动和 review label coverage；不得通过降低二级 readiness 门限改善表面接管率 |
| DDS QoS 通信策略仿真 | 当前通信是仿真 summary/内存网络合同，真实 DDS/ROS2 QoS 不属于 D4 直接拥有路径；P1 先建模丢包、优先级、stale link、message durability/reliability 和消息 freshness，不把 DDS/RTI/ROS2 生产化列为 P0 | D6 可统计 packet loss、delay、priority delivery、stale link、freshness age、QoS profile 和对 failover/CBBA 收敛的影响 |

## 完全无中心模式边界

完全无中心只在中心不可用且二级节点不可用、不可达或不覆盖当前区域时作为保底路径。当前实现使用本地轻量 `CBBANegotiator`，把 D5 distributed visual evidence 作为 CBBA 风险/代价修正项：视觉支持资源获得正向加权，`hold`、friend conflict、stale/missing/conflicting `global_track_id` 阻止可执行 bid，duplicate terminal lock 写入 `assignment_audit` 并惩罚相关资源。

D4 不构造“虚拟中心”，不在 no-center 路径临时调用 Hungarian/Min Cost Flow 伪装中心化最优，也不创建、改写或本地重绑定 `global_track_id`。D3 的中心化 cost matrix 只能作为后续离线 gap benchmark 输入，不能替代 D4 的完全无中心 CBBA 保底。

## 已实现

| 能力 | 当前实现状态 | 关键证据 |
|---|---|---|
| `C2Health` 枚举和状态迁移 | 已实现 `normal/degraded/suspect/failed`，覆盖 heartbeat warning/stale/failure、heartbeat sliding window、miss threshold、dwell、peer quorum、digest conflict、center epoch stale；恢复 heartbeat/digest 后先进入 `suspect`，不能直接回 normal | `research_modules/d4_distributed_fallback/d4_distributed_fallback/models.py`；`coordinator.py`；`tests/test_health.py` |
| 被动降级入口 | 已实现中心 failed 后才运行 `plan_degraded()`；可选二级/备份/代表节点 leader；无 leader 或 CBBA 不收敛时不发布有效 assignments | `coordinator.py`；`tests/test_coordinator.py`；`tests/test_airsim_phase1_dry_run_contracts.py` |
| 二级系留/高空节点模型 | 已实现 `NodeRole.SECONDARY_RECON`、`GROUND_BACKUP`、`FIXED_TETHERED_SECONDARY`、`MOBILE_HIGH_RECON`、`MOBILE_SECONDARY_RECON`，并支持等价 `capability_class=mobile_high_recon/mobile_secondary_recon/fixed_tethered_secondary/tethered_recon`；`coordinator_only`、`coverage_cell`、coverage ratio、`takeover_priority`、`lease_epoch`、heartbeat/cue freshness、gimbal 字段和 leader 排序均已覆盖 | `models.py`；`coordinator.py`；`active_degradation.py`；`README.md`；`PLAN.md` |
| 主动降级仲裁 | 已实现规则版 `ActiveDegradationArbiter`；中心可用时只输出 `continue_center`、`request_center_replan`、`request_secondary_assist` 或 `hold_for_review`，中心 failed 后才允许 `degrade_to_secondary/degrade_to_distributed`。显式 terminal evidence applicability 防止远距未锁被误判为辅助需求 | `active_degradation.py`；`adapter.py`；`tests/test_active_degradation.py`；`tests/test_arbitration_adapter.py` |
| D1/D2/D3/D5 evidence adapter | D4 侧已实现 `D4ArbitrationAdapter`，用 duck typing/dict 读取 D1 covariance/age、D2 ambiguity/IDSW/continuity、D3 plan/version/freshness/cost margin、D5 terminal/cross-view/friend-conflict 摘要 | `adapter.py`；`tests/test_arbitration_adapter.py` |
| D2 online truth 隔离语义 | 已实现 `truth_metrics_available`/`continuity_available` 透传与门控；不可用的 IDSW/continuity 数值占位不产生硬风险。连续 `duplicate_track_risk >= 0.5` 输出 soft `d2_duplicate_track_risk_high`，不合成 count；只有显式 duplicate count、delta/delta sum 或 observed flag 输出 hard `d2_duplicate_track_observed` | `active_degradation.py`；`adapter.py`；`tests/test_arbitration_adapter.py` |
| D5 友方/重复锁定保守处理 | 已实现 `friend_conflict` 强制 `hold_for_review`；`duplicate_terminal_lock` 不视为一致绑定。cross-view ambiguity、低置信度和持续 `ambiguous/hold/reacquire` 只作 readiness/软风险，不再被 D4 重复解释为 global binding 错误 | `active_degradation.py`；`adapter.py`；`tests/test_active_degradation.py`；`tests/test_arbitration_adapter.py` |
| D5 二级覆盖/转换漏斗诊断 | 已实现 D5 secondary detect coverage/conversion evidence 透传，新增 `cue_freshness_s/cue_freshness`、`gimbal_pointing_ok`、`secondary_coverage_ratio`、`secondary_network_joint_full_view_frame_rate`、`cross_view_support_count`、`stable_cross_view_registration_count` 和 `not_registered_count`；当二级覆盖可用但 cross-view association 为 0，或 D5 在 global binding/registration 断点拒绝时，D4 event metadata 写入 `secondary_detect_available_but_not_registered`、reject reasons、计数和 diagnostic；该诊断不直接激活 `secondary_plan_active`。D4 文档口径已明确区分 `visible_only`、`registration_usable` 和 `takeover_ready` | `active_degradation.py`；`adapter.py`；`tests/test_arbitration_adapter.py` |
| D5 分布式视觉证据接入 CBBA | 已实现 `DistributedVisualEvidenceSummary`、`build_distributed_visual_evidence_summary()`、`merge_distributed_visual_evidence_into_tracks()`；轻量 CBBA 会优先视觉支持资源，阻止 `hold`、友方冲突、过期/缺失/冲突 `global_track_id` 的可执行 bid；测试覆盖完全无中心 CBBA 使用 D5 evidence 风险加权 | `models.py`；`adapter.py`；`cbba.py`；`tests/test_arbitration_adapter.py`；`tests/test_cbba.py` |
| 完全无中心 CBBA 风险加权 | 已实现 visual support 正向加权、`hypothesis_only` 弱加权、ambiguous/duplicate/local conflict 风险惩罚、single-winner 防重复 owner；没有虚拟中心 Hungarian fallback | `cbba.py`；`tests/test_cbba.py` |
| `assignment_audit` | 已实现每个带视觉证据任务的 owner、support/hold/ambiguous/duplicate resource、confidence/ambiguity、hypothesis、stale/missing/global/local conflict、risk reasons 审计 | `models.py`；`cbba.py`；`tests/test_cbba.py` |
| 二级节点 lifecycle 和链路 freshness | 已实现 heartbeat/lease/coverage/cue/gimbal/link、四级瞬时 readiness，并新增逐决策 stable/not-registered source/presence、连续 readiness streak/since/duration/sustained/fallback。默认要求 3 个不同 timestamp 决策和 0.2 s 驻留，单帧不接管 | `models.py`；`active_degradation.py`；`adapter.py`；`tests/test_active_degradation.py`；`tests/test_arbitration_adapter.py` |
| 主动降级防抖/迟滞 | 已实现 `risk_window_size`、`risk_window_threshold`、`min_dwell_s`、`release_consecutive_consistent_frames`，并按 resource/track binding 隔离 arbiter 状态。`non_locked_frame_limit=3` 只在 `terminal_evidence_applicable=true` 时决定何时进入持续视觉 cue 仲裁；窗口外普通失锁不触发辅助，D5/D7 仍独立判断 visual lock/handoff。friend/duplicate/resource/assigned-track/明确 observed-track mismatch/stale-plan 冲突始终 fail closed，过期 active secondary lease 显式 hold | `active_degradation.py`；`adapter.py`；`tests/test_active_degradation.py`；`tests/test_arbitration_adapter.py`；`tests/test_airsim_terminal_consistency_replay.py` |
| D7/metadata 二级接管公开 helper | 阶段 2 与 maintained secondary owner 均要求 readiness exact-true、expected/actual source、plan/required lease epoch 和严格 `current_time < expiry`；逐字段 `None` 输出稳定原因并保持 phase 1/pending/not executable | `active_degradation.py`；`tests/test_airsim_phase1_dry_run_contracts.py` |
| secondary takeover plan metadata | pending/active 发布与维持统一要求可证明严格 `<`；缺字段、等值、过期均 not executable，active owner fail-closed 到 hold；D4 不生成系统级 `AssignmentPlan` | `active_degradation.py`；`adapter.py`；`tests/test_arbitration_adapter.py` |
| D6 event metadata | 已实现既有 D4/D6 metadata，并新增逐决策 registration source/presence、readiness streak/duration/sustained、transition、pending since、activated at、activation delay、required lease epoch、source match 和 fallback reason | `adapter.py`；`tests/test_arbitration_adapter.py` |
| D6 CBBA report metadata | 已实现 `build_cbba_d6_metadata()`，metadata 含 `coordination_mode`、`selected_coordinator`、leader、coverage、CBBA completion/conflict/round/message、`assignment_audit` 和 cost gap 扁平字段；`run_failover_simulation()` 顶层 metrics 已透出 secondary/distributed 分组字段 | `cbba.py`；`simulation.py`；`tests/test_cbba.py`；`tests/test_simulation.py` |
| 简化分布式 CBBA | 已实现本地 `CBBANegotiator`、winner/bid 扩散、确定性 tie-break、bundle release/rebuild、packet loss/delay 内存网络、收敛/冲突/消息统计 | `cbba.py`；`network.py`；`tests/test_cbba.py`；`tests/test_coordinator.py` |
| CBBA vs 中心化 cost gap helper | 已实现 `CBBACostGapBenchmark` 和 `build_cbba_cost_gap_benchmark()`，用 D3/main 提供的中心 plan 与 cost matrix 计算 CBBA cost/completion/conflict/message gap；不接入外部 CBBA，也不在 no-center 路径运行 Hungarian | `models.py`；`cbba.py`；`tests/test_cbba.py` |
| P2 隔离 coalition fault replay | 已实现 6 场景原生 replay、逐场景 round/completion/conflict/gap-or-unavailable 输出、MIT/CA-CBBA path/source capability probe 和 CLI；明确 `isolated_from_online_d4=true`、`replaces_online_d4=false`、`adds_default_dependency=false` | `p2_coalition_replay.py`；`scripts/run_p2_coalition_replay.py`；`tests/test_p2_coalition_replay.py` |
| main/runtime secondary owner/version 消费 | main 已接入 D4 event、`request_center_replan -> D3 new version`、secondary takeover owner/version 和 D7 owner gate；controlled 2v2 secondary visual PNG 回归已通过；P1 D4/D5 calibration sweep 已能生成多组合 stress episode，D6 标准 AirSim calibration report bundle 已自动生成。该项是 main-owned 集成证据，D4 仍只输出仲裁/metadata | `research_modules/airsim_runtime/tests/test_blocks_runtime.py::test_main_episode_bus_marks_secondary_takeover_plan_for_d7`；`::test_controlled_2v2_active_degradation_secondary_plan_visual_png` |
| 中心恢复合并基础版 | 已实现 `merge_recovery()`，比较 center/fallback assignments；冲突或 review 未清空时保持 degraded，只有 clean merge 且 `human_accept=True` 才 normal | `coordinator.py`；`tests/test_coordinator.py` |
| N 规模输入 | 仿真和 CBBA 按 `ResourceSummary[]`、`TrackSummary[]`、`node_ids` 长度运行；`--drone-count` 只是输入规模，2v2/5v5 仅作为 baseline 名称 | `simulation.py`；`scripts/run_failover_simulation.py`；`tests/test_simulation.py` |

## 部分实现

| 能力 | 已有部分 | 未完成部分 | 缺少条件 |
|---|---|---|---|
| 完整 `C2Health` 审计 | 有 heartbeat、digest、epoch、peer vote 和 transition log | 未持久比较完整 center track digest、assignment digest、terminal lock log、communication log | main 需要生成并持久化中心/peer 双轨日志，D6 需要消费状态迁移和 merge outcome |
| 被动降级二级接管 | 中心 failed 后可选固定系留/机动高空二级/备份节点；二级不可用时落到 cluster representative/CBBA；`coordination_mode`、leader capability 和 secondary capability 写入 `CBBAResult.final_views`，并由 `build_cbba_d6_metadata()`/`run_failover_simulation()` 透传到报告字段 | 二级节点没有真实区域 TrackSummary 缓存、局部 plan 发布器或持续 heartbeat 维护 | main/AirSim episode 需要维护 `Secondary_Recon_*`/mobile recon heartbeat、coverage ratio、lease、gimbal、视频/检测 cue 和链路事件 |
| main runtime bus episode-time 接线 | D4/D5 sweep、二级/peer commit 正负例、7 场景规范矩阵及 2026-07-13 六类、10-seed、60-case AirSim episode clock 批量验收均已完成；owner/version/epoch/lease 可审计，误降级、重复 owner 和 split-brain prevention failure 均为 0 | 真实吞吐带宽、时钟漂移、网络排队/抖动/乱序/重传、secondary-interceptor/peer 实际链路与硬件 RF 未验证 | 保持现有 schema；真实网络需链路仿真器、网络仿真或硬件条件 |
| D3 `request_center_replan` 自动调用 | main 已监听 D4 `request_center_replan`，下一规划周期强制 D3 生成新版本 `AssignmentPlan`，并写入 `replan_reason/supersedes_plan_id/supersedes_plan_version/active_plan_owner=center`；D4 已避免软 cost margin、低终端置信度和无冲突持续 reacquire 每帧触发 replan | 真实多 seed 中的触发阈值、dwell/release 和 review label 还未标定 | main/D3 需要保持 version/supersedes/stale rejection，并用多 seed 统计验证 |
| secondary takeover plan version 闭环 | D4 sustained readiness、pending/active/source/lease/timing/fallback 合同已完成；最新二级正例由 `Secondary_Recon_1` 以 ACK 3/3 进入 `executing` | 合同正例已通过；完整扰动、回落与恢复统计仍开放 | 保持正例回归，扩展 lease/分区/成员故障矩阵；不降低门限 |
| D1/D2/D3/D5 evidence adapter | D4 已逐决策记录 stable/not-registered source/presence，并保留 compatibility 来源 | 历史 AirSim input 两个显式计数仍为 null；D5 peer evidence 合流仍需校准 | main/D5 将真实逐帧 stable/not-registered 摘要送入 adapter，D6 汇总 source 分布 |
| D6 metadata | D4 已能产出 D6 `EventRecord` kwargs，含 active degradation precision 所需三值 label、`active_degradation_necessity_label`、review window、readiness class、stable/not-registered count 和 false-trigger candidate；main/runtime P1 基线已写入 D6 collector，P1 sweep 已自动生成 D6 AirSim calibration records/summary/report bundle | episode-level 长期聚合、主动/被动降级次数、二级接管率、分布式冲突率和人工/离线 review label 分布仍需多 seed 报告固化 | main/D6 保留 batch seed 维度并统一聚合字段 |
| 中心恢复合并 | assignment-only merge 已实现 | 未比较 track version、plan digest、terminal lock、communication link、D5/D7 gate 状态 | 需要完整双轨 episode log 和恢复前后版本序列 |
| CBBA vs 中心化最优差距 | D4 已有单场景 helper、benchmark 字段和 `build_cbba_d6_metadata()`，可比较 D4 CBBA 与 D3/main 提供的中心 plan/cost matrix 并输出多 seed 报告字段 | 真实 episode 还未持续保存 D3 cost matrix/current plan，D6 还未做多 seed 聚合 | main/D3 需要保存中心化 cost matrix/current plan，D6 需要聚合 cost gap |
| D5 distributed visual evidence 运行时接线 | D4 模块内可消费 D5 distributed association/hypothesis 的对象或 dict，并在 CBBA scoring 中使用 | 真实多 seed no-center case 中 D5 多 peer 输出到 D4 `TrackSummary.visual_evidence` 的合流频率和风险权重还未标定 | main 需要在 episode 状态机中持续调用 `merge_distributed_visual_evidence_into_tracks()` 或等价接线并形成 D6 统计 |
| AirSim D4/D5 stress | 历史 sweep 与 commit 正负例均可审计；二级和 peer 3/3 `executing`、显式截止后缺 ACK 2/3 `aborted` 已通过；模块 replay 九类扰动 9/9 通过 | 同类扰动在真实 AirSim 中的成员退出/重构、误降级和恢复多 seed 统计仍开放 | main 使用统一 D4 schema 增加同 seed 成对扰动 |
| M 对 N 联盟降级 | 已实现 member ACK、commit lifecycle、lease/epoch、digest、分区和恢复审计；secondary/peer commit 正例与缺 ACK fail-closed 已通过，member replacement 仅为手工 replay | 自主成员形成、reserve 激活、补位/缩编/整盟重组、D7 时序可达性和真实 AirSim 扰动矩阵尚未闭合 | P1 保持开放；P2 隔离比较不得绕过合同 |

## 未实现

| 未实现项 | 当前结论 | 为什么未实现 | 缺少条件 | 优先级 |
|---|---|---|---|---|
| MIT CBBA / CA-CBBA 外部执行 | 已有隔离 capability adapter 和逐场景 unavailable 结果，但没有 import/执行外部算法 | MIT 参考为 MATLAB 且 runtime adapter 未集成；CA-CBBA 公共参考无可执行源码；外部项目也不提供 MSM coalition commit | 获得许可证明确的可执行源码和隔离 runtime 后，按现有 schema 增加 execution adapter；不得替换默认路径 | P2 execution unavailable |
| 独立 auction baseline | 未单独实现，后置为可选对照基线 | 当前 `CBBANegotiator` 已覆盖 winner/bid 思想，并已接入 D5 visual evidence，但不是 single-round auction；当前 P1 主线先做 runtime adapter 接线和 CBBA gap benchmark | 定义 bid/award/rollback、reserve/confirm、重复任务消解和失败回滚测试 | P2 后置 |
| Contract Net 协议 | 未实现 manager/contractor announce-bid-award 状态机 | 不是 D4 最小闭环必需；二级节点 healthy 时也仍需和 D3 plan version 对齐 | 消息类型、超时、拒绝/重招标、manager 失效和 D3 映射规则 | P2 |
| 真实通信/视频链路 | 未实现真实 socket、ROS 2 topic、mesh、视频帧传输或无线协议 | D4 边界是离线摘要和内存网络，不拥有 runtime 通信层 | main/runtime 生成 `LinkRecord`/video metadata；D5/D1 消费图像/检测 cue | P2/P3 |
| 二级节点真实图像/检测 cue adapter | D4 只消费/记录 cue freshness，不处理图像或 bbox 几何 | 像素配准、相机标定和 local visual track 属于 D5/main；D4 剩余工作是 heartbeat/link freshness 的多 seed 标定 | AirSim detection schema、camera calibration、二级节点视角日志、D5 cue schema | P1 校准 / P2 适配 |
| OpenDroneID/MAVLink signing/DDS Security/AprilTag | D4 不实现 | 这些是身份/协议证据源，D4 只消费 D5 汇总后的 `friend_conflict`、auth/duplicate/cross-view 风险 | D5/main 提供身份摘要，不让 D4 直接判定身份 | P2/P3 |
| D4 直接写 shared bus | 不实现为 D4 责任；main 已统一调用 adapter 并写 D6 collector | D4 遵守模块边界，只返回 record/kwargs，不发布全局事件 | 需要 main 继续保持 episode bus 接线和多 seed 回归 | P1 main 基线已完成，后续校准 |
| D4 直接生成新 `AssignmentPlan` | 不作为 D4 能力实现；D4 只输出仲裁/metadata/CBBA 保底结果 | 中心化计划属于 D3/main；D4 降级 CBBA 只是保底 continuity assignment；main 已完成 secondary owner/version 消费基线 | D4 继续保持 `SecondaryTakeoverPlanMetadata` 输出，不生成系统级计划 | 非 D4 主线 |
| 大规模 SCRIMMAGE 或替代仿真 | 未实现 | 当前目标仍是 AirSim CV 和本地 point-mass/内存仿真 | 完成 5v5 stress 后再评估场景导出、ID 映射和通信退化模型 | P3 |

## 未实现原因汇总

1. **模块边界**：D4 只负责降级仲裁、摘要模型、保底协商和事件记录。main 才拥有 runtime bus、AirSim episode、D6 collector 和跨模块状态机。
2. **轻量可复现优先**：当前默认测试不能依赖 AirSim 服务、ROS、真实通信、GPU 或外部 CBBA 工程；因此保留本地 NumPy/内存网络实现。
3. **针对性 episode 数据仍不足**：常规 freshness 下的 10-seed 5v5 CV stress 已完成，但尚缺持续 network full-view、heartbeat/link/cue 故障、coverage-cell 切换和 active secondary plan 样本，不能据此标定全部阈值或接管延迟。
4. **外部开源适配成本**：MIT/CA-CBBA capability 探测已实现并以 unavailable 收尾；真实 execution 仍要求额外 runtime、协议状态、消息模型和许可证审查，不能直接替换主线。
5. **安全/身份边界**：D4 不应直接处理身份认证、图像语义、飞控动作或授权状态，只能消费 D5/main 的保守摘要。

## 缺少条件

- main 在同一 episode 中持续提供 D1 `TrackUncertaintySummary`、D2 `AssociationRiskSummary`、D3 `AssignmentValiditySummary`、D5 `TerminalAssociationSummary` 或等价对象/dict；P1 基线已接入，D2 truth/continuity unavailable 已有 D4 回归，仍需多 seed 缺测路径和其他字段分布校准。
- main/runtime 统一调用 `D4ArbitrationAdapter.evaluate()`，不再分散手工构造 D4 summary；2026-07-08 已在 main episode bus 中形成基线接线。
- main/runtime 对每个 resource/track pair 同时消费 `d4_action`、`terminal_consistent`、`risk_factors`/`hard_risk_factors`、`plan_id`、`plan_version` 和 D5 `decision_state`/lock gate。`terminal_consistent=true` 只允许保留 current center binding，不能单独授权 terminal PNG；`terminal_consistent=false` 继续作为 D4 fail-closed 输入。
- D6 collector 接收 `D4DecisionRecord.to_event_record_kwargs()` 和 `build_cbba_d6_metadata()` 输出，并按 active/passive、secondary/distributed、coverage_cell、batch seed、review label 和 review window 聚合指标；长期报告口径仍需多 seed 固化。
- AirSim stress 已完成 2026-07-10 的 10-seed 常规 freshness 基线，2026-07-13 episode-time 六类、10-seed、60-case 故障矩阵也已完成。下一批应把持续 network full-view、heartbeat/lease/video-cue/link stale 和 active secondary plan 摘要接到带宽、时钟漂移、排队抖动、乱序/重传模型，校准接管驻留、回落和 plan activation delay。D4 只消费这些摘要，不修正视觉几何注册。
- D3 在收到 `request_center_replan` 后已能由 main 触发新版本 `AssignmentPlan` 并把 plan id/version 写入后续 gate；main/D3/D7 已完成 secondary owner/version P1 基线和 controlled 2v2 secondary visual PNG 回归，D4 已输出 activation delay/pending duration 字段，仍需真实多 seed 校准 delay 分布、freshness 和恢复合并窗口。
- 中心恢复需要完整双轨日志：track digest、assignment digest、terminal lock、communication link、plan version、降级期间 fallback assignments。
- MIT/CA-CBBA capability adapter 已完成；若未来做外部 execution，仍需许可证/依赖审查、隔离 runtime 和 D6 cost/communication gap 报告。做独立 auction baseline 前，先完成同一任务集的 CBBA vs 中心化多 seed gap 聚合。

## P1/P2 下一步

0. **P1 M 对 N 联盟合同回归**：二级 ACK 3/3 `executing`、peer ACK 3/3 `executing` 和显式截止后缺 ACK 2/3 `aborted` 已通过；截止前普通快照保持 `collecting_acks`。后续保持这些场景并增加成员退出 `reconfiguring`、恢复和误降级统计。不得把 single-winner CBBA 宣称为自主 `k_j=3` 成员形成算法。
1. **P1 terminal consistency 重跑验收**：对同 plan/同 ID 的 1-5 帧及长时 dropout 逐帧记录 `d4_action`、`terminal_consistent`、binding reject reasons、hard/soft risk、D5 decision/lock 和 D7 gate；无硬冲突始终保留 binding，但未锁定 PNG 仍由 D5/D7 阻断；任意 mismatch/friend/duplicate/stale-plan/version/ACK/lease 必须立即 fail closed 且错误绑定为 0。
2. **P1 D4/D5 定向校准**：D4 逐决策审计和连续 readiness 已完成；main/D5 继续输入真实 stable/not-registered，构造持续 network full-view 与 coverage-cell 切换 case，统计各状态驻留、source 分布和接管必要性。该视觉证据校准与已通过的 episode-time 60-case 安全矩阵分开统计。
3. **P1 真实链路时序验证**：保持已通过的 secondary/peer 顺序接管和 ACK/epoch/lease fail-closed，不降低门限；引入可配置带宽、节点时钟漂移、排队抖动、乱序/重传以及 secondary-interceptor/peer 断链，统计 executing 后回落、恢复和 activation delay。
4. **P1 长期误降级/脑裂统计**：当前 episode-time 矩阵已得到 false degradation=0、duplicate owner=0、split-brain prevention failure=0；下一步在真实网络时序和长时间同 seed 正常/故障对照中，由 D6 统计 false/missed degradation、动作混淆、恢复时间和 dwell/release 抖动。
5. **P1 同几何 M5N2 paired 验收**：中心继续执行 baseline/candidate 各 10 seeds 已完成，形成 `active degradation=0`、coalition `0/20`、第二 primary 5 m `0/20` 的负对照。尚需在相同几何/seeds 下运行中心失效、中心与二级连续失效，以及由 D1/D2/D3/D5 证据驱动的主动风险 case，分别报告 action/reject、误降级、owner/version、target、active-primary、coalition completion 和恢复；中心负对照不关闭 fallback P1。
6. **P1 CBBA gap benchmark 聚合**：D4 已有单场景 helper；main/D3 仍需保存中心化 cost matrix/current plan，D6 仍需聚合 lightweight CBBA 与中心化 Hungarian/Min Cost Flow 的 cost/completion/conflict gap。
7. **P1 D6 全样本外部准入**：D6 读取 `reports/D4_REGION_RESOURCE_FULL_SAMPLE_ADMISSION_20260721.json`，先用带外 SHA256 `4245f1db36f1af47259554f0770e75a3fe97fcc5e9b75c1b04c83d5bfb5c9e46` 校验文件，再核对 content SHA、source paths、binding checks 和 availability。不得将 `target.kind=rule` 计为 truth 泄漏，也不得将 recommendation/projected 计为 applied ACK。缺真实 ACK/outcome/reward/paired shadow 时保持 pending。

P2（保持原规划）：

5. **P2 隔离 optional auction baseline（未开始）**：只能在隔离环境用同一 summary/task/resource 输入与 CBBA 对照，不进入默认路径。
6. **P2 隔离 MIT/CA-CBBA adapter（capability 已完成，execution unavailable）**：原生 6 场景 replay 与外部逐场景 unavailable 行已落地；默认未配置参考路径。即使检测到 MIT MATLAB 源码也不执行，CA-CBBA 公共参考无可执行源码。未来 execution 仍不可替换默认轻量 CBBA，也不可绕过联盟 ACK/lease/epoch 合同。
7. **P2 恢复合并增强**：把 `merge_recovery()` 从 assignment-only 扩展到 track digest、terminal lock、communication link、coalition digest 和 plan version 的组合校验。

实施顺序更新为：保持 P1 commit 正负例回归 -> 完整扰动/成员重构矩阵 -> D6 多 seed 聚合 -> P2 隔离 benchmark。后续实现验收命令为 `PYTHONPATH=research_modules/d4_distributed_fallback python3 -m pytest -q research_modules/d4_distributed_fallback/tests`。

## 关键依据路径

- `research_modules/d4_distributed_fallback/d4_distributed_fallback/models.py`
- `research_modules/d4_distributed_fallback/d4_distributed_fallback/active_degradation.py`
- `research_modules/d4_distributed_fallback/d4_distributed_fallback/adapter.py`
- `research_modules/d4_distributed_fallback/d4_distributed_fallback/coordinator.py`
- `research_modules/d4_distributed_fallback/d4_distributed_fallback/cbba.py`
- `research_modules/d4_distributed_fallback/d4_distributed_fallback/network.py`
- `research_modules/d4_distributed_fallback/d4_distributed_fallback/simulation.py`
- `research_modules/d4_distributed_fallback/d4_distributed_fallback/p1_failover_replay.py`
- `research_modules/d4_distributed_fallback/d4_distributed_fallback/p2_coalition_replay.py`
- `research_modules/d4_distributed_fallback/d4_distributed_fallback/region_resource_full_sample_audit.py`
- `research_modules/d4_distributed_fallback/reports/D4_REGION_RESOURCE_FULL_SAMPLE_ADMISSION_20260721.json`
- `research_modules/d4_distributed_fallback/tests/test_region_resource_full_sample_audit.py`
- `research_modules/d4_distributed_fallback/README.md`
- `research_modules/d4_distributed_fallback/PLAN.md`
- `research_modules/d4_distributed_fallback/docs/ALGORITHM_AND_IMPLEMENTATION.md`
- `research_modules/d4_distributed_fallback/tests/test_health.py`
- `research_modules/d4_distributed_fallback/tests/test_coordinator.py`
- `research_modules/d4_distributed_fallback/tests/test_active_degradation.py`
- `research_modules/d4_distributed_fallback/tests/test_arbitration_adapter.py`
- `research_modules/d4_distributed_fallback/tests/test_cbba.py`
- `research_modules/d4_distributed_fallback/tests/test_airsim_phase1_dry_run_contracts.py`
- `research_modules/d4_distributed_fallback/tests/test_simulation.py`
