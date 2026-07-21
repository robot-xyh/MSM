# D6 实现差距审计

## 2026-07-21 canonical seed split GAP 状态

### 已关闭的 D6-owned P0/P1 consumer 缺口

- 已实现 detached shared registry 的独立 schema、policy、content hash、assignment hash 和 source
  training registry SHA-256 校验，不导入 main runtime。
- 已实现 100 个训练 seed 全覆盖、`1000-1019` 保留 seed 隔离和冻结数值 seed assignment 复算。
- 已实现 D3、D4、D5 tracklet graph、D5 active-vision 四类 manifest 的 seed 数、missing、extra、
  reserved、内部冲突、mismatch seed、原 split hash 和 canonical hash 报告。
- D4/D5 可可靠下钻到 mismatch episode/sample；D3 缺逐 seed frame 索引时保留 `null+reason`。联合训练
  只有四模块 exact 时才 available，无 registry 调用保持原 D4/D5 兼容。
- CLI、audit-only 和 detached sidecar 已接线；正式源不重写。篡改、源 SHA 错配、缺失/额外/保留 seed
  和各模块 mismatch 均有 fail-closed 回归。

### 正式证据

- 数据：Git `39b097e72487567ac915c2297eaa27eed49ef76b`，900 episode，100 个训练 seed，20 个保留
  seed，源哈希全量校验通过。
- D3：60/20/20，canonical exact，0 mismatch。
- D4：70/15/15，51 mismatch seed、459 episode、917 frame。
- D5 graph：60/20/20，65 mismatch seed、8350 graph record、284 candidate edge。
- D5 active vision：60/20/20，62 mismatch seed、558 episode、713298 sample。
- 四模块 missing/extra/reserved seed 均为 0。联合训练 `available=false`，原因
  `required_module_split_not_exactly_canonical`。正式 readiness SHA-256 为
  `a0469fa0bf4f1fc80d5e5dc9afac74d4638e782161c0c3f5ebc6befd93f405d1`。
- 接受门限为注册表八项 validation 全真且四模块 exact；本次只满足注册表和 D3 条件。2026-07-21
  D6 全量 `364 passed`，仅有既有 Matplotlib `Axes3D` warning。

### 仍开放的跨模块 P1 producer 条件

1. main/D4/D5 需要基于 detached registry 生成新的规范 split view 或新版本数据；冻结的 900 episode
   源 manifest 不原地改写。四模块 exact 前，跨模块联合训练保持 fail closed。
2. shared split exact 只解决数据泄漏治理。D4 动作多样性、applied action/reward，D5 runtime ACK/reward
   和 D4/D5 PPO 条件仍未满足，不能随 split 修复自动关闭。
3. 正式 C1 联合训练还需在 canonical split 上重新生成 bundle，并用保留 seed `1000-1019` 做外部验收。
   当前 D3/D4/D5 单模块开发结果不可拼接为联合性能结论。

## 2026-07-20 正式学习标签 GAP 状态

### 已关闭的 D6-owned P0

- 已实现冻结学习导出的只读审计、truth-like 在线字段拒绝、训练/保留 seed 隔离、D4/D5 episode
  identity、模块内 split 与跨模块 split 交叉审计、全量源哈希和共享对象键校验。
- 已实现 outcome、reward、counterfactual、causal-label 四层独立 availability。不可辨识的反事实和
  因果值保持 `null`，没有使用假零。
- 已实现源外 detached sidecar、原子发布、manifest、SHA-256 和确定性重复运行。正式学习数据不需要
  原地重标，也不允许就地写入。
- D5 reward 已将 runtime ACK 设为硬门。相邻姿态或投影改善只能形成纯观测 outcome，不能证明动作
  被应用。接受 ACK 还要求后续反馈版本和时间一致。

### 正式 900 episode 证据

- 数据身份：Git `39b097e72487567ac915c2297eaa27eed49ef76b`，900 episode，100 个训练 seed；保留
  seed `1000-1019` 共 20 个，训练交集为 0。
- D4：1798 帧，observed outcome `898`，reward `0`；14384 个动作中非零 quota、hold、request-replan
  和 transfer 均为 0。行为克隆合同可用，但动作多样性不足。PPO unavailable。
- D5：1,153,242 条样本，observed outcome `1,063,214`，reward `0`；runtime/accepted ACK 均为 0，
  requested action 为 0，effective mode 全部 disabled。规则示范行为克隆可用，主动视觉 PPO
  unavailable。
- D4/D5 的 split registry 有 423/900 个 episode、47/100 个 seed 不一致。两个模块各自仍保持 seed
  原子 split，单模块训练可用；跨模块联合训练 unavailable。Counterfactual 和 causal training 同样
  unavailable。正式源未修改。审计证据日期为 2026-07-20；2026-07-21 验收为专项 `17 passed`、
  D6 全量 `351 passed`。

### 仍开放的 P1 producer 条件

1. D4/main 缺每帧 recommendation consumption/adoption、applied action digest、plan/epoch/lease 绑定、
   post-action 区域状态和终局任务结果。当前无法把区域变化归因给 D4 动作，也无法构造 PPO reward。
2. D4 正式数据动作退化为全零 quota 且无 hold/replan/transfer。行为克隆管线可读取，但训练样本不具备
   足够动作覆盖，暂不具备策略准入价值。
3. D5 生成链先捕获 learning frame，随后 main 才发布 camera-command ACK；正式 online 样本的
   `runtime_ack` 全为 null。运行态最近接受命令版本也未映射到 camera feedback。现有数据只能提供纯
   观测转移和规则示范。
4. PPO 仍缺 on-policy log probability/value。任务级奖励还缺明确终局结果和归因窗。反事实和因果标签
   仍缺同初态配对重放、随机干预或等价识别证据。
5. D4 与 D5 使用了不同的 seed split registry。main 需要冻结共享 registry 或独立规范 split sidecar；
   在此之前不能合并两个模块的数据做联合训练或联合调参。

上述 P1 均是 producer/实验设计条件。D6 已提供机器可读缺失原因和准入结论，不跨模块补造字段。

## 2026-07-20 Scalable 3D 实验矩阵 P1 状态

- **D6 consumer 已实现**：独立读取并验证 matrix schema、variant、comparison key 和 full-system flag；
  历史 episode 保持可评估，矩阵字段 unavailable，目录名不参与补值。
- **执行审计已实现**：R0/G1/A1/A2/A3/C1/F1 与四项 learning runtime 和模块实际采用证据交叉核对。
  bundle 缺失、assist 未采用或规则回退均为 execution invalid，并保留逐项原因。
- **完整性与统计已实现**：每个比较键固定六个基础 cell；三个完整体系场景固定增加 F1。按 variant
  输出 availability-aware 指标和阶段耗时；完整 R0 配对输出 delta，两个及以上配对键输出 bootstrap CI。
- **证据分层已实现**：matrix formal 必须同时满足通用 clean formal、当前 metadata 和执行有效；dirty
  development 单独统计。paired delta 明确不是因果归因。
- **验证**：producer 风格专项 `40 passed`、D6 全量 `320 passed`；真实
  R0/nominal/2v2/seed101 dirty smoke 为
  metadata/execution valid=true、cell=1/6、matrix formal=false。临时 5v5 producer smoke 的 D4 合法
  消费、D3 hint applied 和 control adoption 均为 1。
- **P1 仍开放**：main 尚未运行 clean 完整矩阵。D4 消费合同已可形成 A2 实际采用证据，但尚无正式
  多 seed A2/C1/F1 运行。整个 comparison key 完全缺失时，还需显式 matrix manifest 才能审计。

## 2026-07-20 Scalable 3D schema provenance P0 窄修复

- **P0 准入缺口已关闭**：旧 evaluator 只检查五项 manifest schema 非空，无法阻止未知或篡改值进入
  clean formal acceptance。v4 现用 D6-owned registry 做精确当前合同匹配，并额外核对 config schema。
- **fixture 偏差已关闭**：`test_scalable_3d_offline.py` 和 `test_active_vision_offline.py` 均改用真实
  producer 的 `scalable3d-observation-v1`，不再使用不存在的
  `scalable3d-online-observation-v1`。
- **历史解释保留**：原始 world/bus/scenario/online/offline schema 字段不改写。旧或未知值的 raw
  availability 仍可用，但 current-contract match=false 并带明确 failure reason；缺字段为 unavailable。
- **正式门已关闭**：`current_schema_contract_match` 是 formal acceptance critical field。五项不匹配或
  任一缺失均不能通过 clean acceptance。
- **验证**：当前匹配、五类旧/未知/篡改 schema、缺 bus schema、报告展示均通过；专项 `32 passed`、
  D6 全量 `304 passed`。真实 6v6 dirty smoke schema match=true，formal 仅因 dirty 被拒绝。
- **剩余限制**：registry 只声明当前 v1 合同。未来 producer 变更需显式升级 registry 和迁移文档，D6
  不把未知版本自动视为向后兼容。

## 2026-07-20 Scalable 3D 主动视觉运行证据 GAP 状态

- **D6 consumer P1 已关闭**：离线评估 v3 已消费 D5 主动视觉命令和 main camera-command ACK，保持
  D6 只读边界。规则动作、影子建议、辅助采用、ACK applied/rejected 和物理结果不互相回填。
- **命令执行证据 GAP 已关闭**：复合键关联 camera/resource、issued timestamp、plan/coalition/
  communication version、intent 和 mode；输出 issued、matched/unacknowledged/unexpected ACK、完成率、
  P50/P95/max latency、rule/assist applied 以及拒绝原因分布。缺日志、坏 schema、数量冲突和不完整关联
  均为 unavailable 或正式证据失败，不补零。
- **身份与真值隔离 GAP 已关闭**：target reference 只读核对命令之前最近的 D2 中心航迹集合，ACK 必须
  返回同一编号；未知引用和 ACK 改写均 fail closed。主动视觉在线记录另有 truth-like 字段违规计数。
- **归因边界 GAP 已关闭**：同一 episode 的 assist applied 与五米接近不能形成因果归因；没有同 seed
  配对规则控制组时 attribution 固定 null/unavailable。
- **2026-07-20 验证**：8 项确定性主动视觉测试覆盖三模式、ACK latency、四类 reject、中心航迹引用、
  ACK 改写、truth 污染、缺日志、summary conflict、五米非归因和双 seed 聚合。合并 scalable 专项
  `25 passed`；D6 全量 `297 passed`，仅既有 Matplotlib warning。场景显式规模为 T/R/Rc/Cam=
  `6/4/1/5`，报告测试使用 2 个不同 seed；上述 fixture 本身未启动 simulator/AirSim。
- **当前 main 接线 smoke**：6v6/recon1/camera7、seed 37、2.2 s，133 issued/matched/applied ACK，0 reject、
  0 target-reference violation、0 truth violation，summary 一致，RTF=4.740。worktree dirty 且单 seed，
  formal acceptance=false，只关闭接口兼容风险，不关闭正式多 seed 或模型性能 P1。
- **仍开放 main/D5 P1**：clean 多规模、至少 20 个未见 seed 的真实运行产物尚未提供；assist 尚无正式
  paired control/treatment 验收，因此不能发布主动视觉物理提升。main 还需确认当前未提交 runtime 合同
  落盘后与 v3 consumer 一致。
- **文档同步**：D6 README、PLAN、三份 review/GAP、docs 原理/算法/index 和实验报告已更新。
  `AIRSIM_INTEGRATION_PLAN.md` 已检查；本轮只涉及 scalable 3D 文件合同，没有改变 AirSim 话题、Blocks
  调度或产物路径，故不修改。

## 2026-07-20 Scalable 3D 学习运行时离线评估 GAP 状态

- **D6 consumer GAP 已关闭**：`d6-scalable3d-offline-evaluation-v2` 纯文件消费 config/summary 的
  learning runtime metadata、manifest/config 的 D3/D4/D5 version，以及在线日志中的 D3 learning、
  D4 region-resource advice 和 D5 fallback 字段；不导入或修改 scalable runtime，不参与控制。
- **模型 provenance GAP 已关闭**：三模块分别保留 requested/effective mode、bundle requested/loaded、
  fallback、runtime version、model fingerprint/version availability。bundle 未加载、旧 schema、缺字段
  或 fingerprint/version 不匹配均为 null/unavailable+reason，不补零。
- **D4 advice 指标 GAP 已关闭**：逐 episode 统计发布/合法/非法、requested/effective 分布、shadow
  output、assist eligible、fallback/reason、latency P50/P95、quota 守恒违规、projection rejection、
  formal mutation/unchanged、stale/missing version evidence；聚合继续按显式规模和不同 seed。
- **fail-closed GAP 已关闭**：旧 advice schema、缺 scenario/seed/policy/plan/version/epoch/lease、action/
  transfer 非法、projected quota 非守恒和 digest flag 篡改均阻止正式证据，不以剩余合法 advice 缩小
  分母。正式 acceptance 仍强制 `repository_dirty=false`。
- **语义分层 GAP 已关闭**：报告明确区分 bundle loaded、shadow output、assist eligible、control
  adoption 和 physical outcome。advice 保持正式 D4 裁决不变；独立 main 消费合同必须引用先前完整
  advice，并与 summary 和 D3 hint applied 一致，才形成 control adoption。物理接近仍不归因于模型。
- **2026-07-20 实现验证**：17 个 deterministic scalable fixtures 覆盖 disabled、三模块 missing-bundle
  fallback、assist-to-shadow、assist gate、守恒/非守恒、projection rejection、formal mutation/
  unchanged、digest 篡改、旧 schema、缺 plan version、缺 advice、dirty 和 seeds 1/2 bootstrap。接受
  门限全部满足；专项 `17 passed`、D6 全量 `289 passed`，仅既有 Matplotlib warning。未运行真实
  simulator/AirSim，不形成模型性能或准入结论。
- **仍开放的 main/producer P1**：clean 正式多规模、多 seed 学习 bundle、完整矩阵与跨提交趋势尚未
  提供；D4 消费只有单 episode 接线证据；evaluator-only global-track-to-truth mapping 仍缺失，D2
  IDSW 仍由 producer availability 决定。fixture 与 dirty smoke 不能关闭模型或物理性能 GAP。
- **文档检查**：README、PLAN、D6 原理/算法、实验报告、docs index、GAP 和两份 D6 review 已同步。
  `AIRSIM_INTEGRATION_PLAN.md` 已检查；本次不读取 AirSim API/Blocks 特有产物，也不改变 AirSim 接线，
  因此不修改。root `docs/*` 不属于本 D6 owned paths，由 main 负责跨模块同步。

## 2026-07-15 legacy ClockSpeed provenance 兼容 GAP 关闭

- **关闭范围**：路径输入且 suite/cases/rows 全无 ClockSpeed 时，按 20 个 case_id 读取固定 sibling
  generated settings；20/20 文件、显式键、有限正数和全量一致全部强制。
- **fail-closed**：不从目录名推断、不默认 1.0、不对 mapping 搜索文件系统；缺文件、缺键、冲突和
  NaN/Inf/字符串均拒绝，部分显式 provenance 不与 fallback 混合。
- **真实证据**：1.0/0.2/0.1 各 20 case 完整配对；1.0 manifest 记录 20 个 settings evidence path，
  0.2/0.1 使用 case result。23 个源的“绝对路径+内容”组合 SHA-256 前后均为
  `fdb745ee54f0c5ff414a812bf8e75eacd56fa5ea91ff02f64008fb6ee1759cd1`。
- **合同审计**：60 case 为 56 match/4 mismatch；0.1 candidate seed007/009、0.2 candidate seed006/
  009 的受影响指标 unavailable，不缩分母、不纳入 reserve。
- **验证**：ClockSpeed 专项 `18 passed`、D6 全量 `272 passed`、`py_compile` 和 `diff --check` 通过。
- **剩余限制**：candidate 0.1/0.2 物理 aggregate 因合同缺项不可用；全部 case wall timing 缺源字段。
  D6 不据部分证据发布 ClockSpeed 优劣或 candidate 准入结论。

## 2026-07-15 0.1 P1 NameError 回归 GAP 关闭

- **根因/修复**：timing input-mode helper 前置并统一为唯一名称，loader/summarizer/evaluator 三处
  dispatch 一致，删除旧缺失名称。
- **回归**：新增 baseline/candidate 各 seed 1-10 的 20-case 双层 case-aware evaluator 测试，每 case
  frame/time 重置；manifest 与跨层禁止相加口径保持不变。
- **真实证据**：ClockSpeed=0.1 M5N2 20/20 case，merged main/control 各 4036 records、20 case；P1
  v6 只读 bundle 成功，输入 SHA-256 前后不变。
- **验证**：timing 专项 `28 passed`、D6 全量 `264 passed`、`py_compile` 和 `diff --check` 通过。
- **后续状态**：本 GAP 当时只关闭 NameError 和 0.1 P1 接线；三档 comparator 随后已完成，见顶部。

## 2026-07-15 Case-aware timing 与冻结机会合同 P1 GAP 关闭

- **关闭范围**：stage timing v2 显式分离 strict single episode 与 case-aware merged suite；后者只准入
  `case_id/family/profile/seed`，逐 case 校验 frame/timestamp 并允许边界重置，拒绝 case 重现。P1
  acceptance v6 和 CLI 已接线。
- **层级安全**：main bus/control tick ordered manifest 必须一致；跨 case continuity/total 和跨层 total
  均不定义。单 episode validator 未放宽。
- **机会合同**：ClockSpeed comparator v2 冻结 M5N2 每 case pair/target/coalition=`3/2/1`。D7 actual
  unavailable 或 suite/intercept 机会不符时，受影响物理/末端指标 unavailable，不缩小分母、不补零；
  standby reserve 不计 active-primary success。
- **真实证据**：ClockSpeed=0.2 M5N2 20/20 case；merged main/control 各 6567 records、20 case，P1
  只读复测通过且输入 hash 不变。合同 18 match/2 mismatch：candidate seed006 为 D7 unavailable 并有
  三类 count conflict，seed009 为 D7 available 但同样是 `2/1/1`。seed006 reserve success=true 只作
  排除审计，active-primary success=1，raw success=2。
- **验证**：timing 专项 `27 passed`、ClockSpeed 专项 `10 passed`、D6 全量 `263 passed`，仅既有
  Matplotlib warning。
- **后续状态**：真实 0.1 P1 与三档 comparator 已由顶部复核；candidate 合同缺项和长期趋势仍
  开放，不能由 fixture 或单档 P1 证据关闭。

## 2026-07-15 ClockSpeed 三档离线汇总 P1 GAP 关闭

- **关闭范围**：新增三个 suite root/summary 的严格完整性、profile/seed、显式 M5N2 规模、
  ClockSpeed provenance 和 `case_id/profile/seed` 跨档配对校验；输出 JSON、两份 CSV、中文 Markdown
  与曲线。
- **指标范围**：active-primary pair、target、coalition 独立成功率；第二 primary 五米/最小距离；
  required active-primary 最终锁、coalition 最终锁共识、collision stop；case/main/control wall timing；
  ClockSpeed 归一化 simulated time/tick；truth identity/state 在线使用。
- **fail-closed**：目录名和 summary 根部裸 ClockSpeed 不准入；缺 seed、重复 case、跨档 key 不同、
  provenance 冲突直接拒绝。缺指标/坏 artifact 为 unavailable，不补零；任一 profile case 缺证据时
  该 aggregate 不发布部分均值。main bus/control tick 嵌套且禁止相加。
- **验证**：2026-07-15，三档各 20 case、总计 60 case 的确定性 M5N2 fixture；接受门限为三档/
  profile/seed/配对/provenance 全完整及 availability/truth/timing 负例全部通过。专项 `8 passed`、
  D6 当时全量 `254 passed`，仅有既有 Matplotlib `Axes3D` warning。
- **状态**：这是运行前关闭记录；真实 comparator 已由顶部完成。合同 mismatch 与缺失 timing 仍按
  unavailable 处理，不能由 fixture、单档或部分 aggregate 关闭。

## 2026-07-15 M5N2 20-case GAP 复核

- **P0 状态**：无新增 D6 P0。20 个 M5N2 canonical actual artifact 全部通过校验，
  required/available/unavailable=`20/20/0`；在线 truth identity/state=`0/0`，缺失证据未补零。
- **已闭合证据**：baseline/candidate 各 10 seed；pair/target/coalition 独立物理结果为
  `12/60`、`12/40`、`0/20`。10389 条 freshness 样本均来自
  `d2_estimated_global_track`，stale=0。第二 primary 七阶段和首失败原因 availability 均完整。
- **P1 第二 primary/coalition**：第二 primary physical=`0/20`，最近距离
  mean/min/max=`12.654/8.843/14.740 m`；coalition=`0/20`。首失败以预测窗过期 10 和视觉获取未
  稳定 6 为主。D6 consumer 已闭合，系统物理性能未闭合。
- **P1 candidate 准入**：baseline/candidate 总量均为 pair `6/30`、target `6/20`，但逐 seed
  non-degradation=false；soft prediction/trend coast 不建议进入默认路径。
- **P1 性能**：逐 case timing 可严格校验。main-bus/control-tick 各 3805 samples，mean/P95=
  `349.34/487.40 ms` 与 `1069.45/1254.06 ms`，预算违例 `3649/3805` 与 `3805/3805`。
  主导阶段分别是 D1 fusion 和 AirSim frame sample；性能门未闭合。
- **P1 timing 接线**：该历史缺口已由顶部 case-aware envelope 关闭；case 边界重置按 metadata 分组
  校验，不再要求伪造全局连续 frame/time，且跨 case total 仍不发布。
- **P1 target 语义治理**：canonical actual 的 target physical success 按“至少一个 participating
  pair 成功”得到 `12/40`；cooperative 七阶段 target unit 当前按“全部成员阶段通过”形成更严格
  诊断。文档统一称前者为 canonical target physical success、后者为 cooperative target-stage
  diagnostic；正式结论只使用 canonical 值。producer schema/字段级 semantics 治理仍为 P1，避免
  同名误聚合。
- **P1 collision provenance**：20 个第二 primary 最终状态均为 `collision_stop`，但 collision
  object/actor、事件时间戳和来源未写盘。D6 不从终态推断成员冲突、环境碰撞、AirSim 状态问题或
  五米成功；对象原因保持 unavailable。补齐 producer 字段和 case-aware 汇总后再分类。
- **范围边界**：M5N2 结束后、`TERM` 生效前额外完成了 `png_ttc` seed001；它明确排除在 M5N2
  20-case 聚合与验收之外。其余 tuned 2v2 和全部 dropout 未执行；缺失 case 保持 unavailable，
  不作为失败或零值，也不将本批标为完整 terminal-closure suite。

## 2026-07-15 第二 primary/独立分母 consumer P1 GAP 关闭

- **关闭范围**：`d6-cooperative-closure-v3` 已提供第二 primary 七阶段漏斗、pair/target/
  coalition 独立物理分母、独立 coalition completion，以及逐层首失败原因 availability。
- **fail-closed**：缺 `physical_intercept` 时成功/失败不发布数值；失败但缺
  `first_failure_reason` 时原因保持 unavailable/partial，不补 `unspecified`；图表中的 unavailable
  coalition 不再绘制为零。
- **验证**：2026-07-15，动态规模无关确定性 fixture，专项 `11 passed`、D6 全量
  `246 passed`、`py_compile` 通过；仅有既有 Matplotlib `Axes3D` warning，未运行 AirSim。
- **当前分类更新**：没有新增 D6 P0。D6-owned consumer/report 缺口已关闭；真实 M5N2 20-case
  证据已取得，其第二 primary/coalition 结果未达标。聚合外 `png_ttc` seed001 只作独立已完成
  case；其余 tuned 2v2 和全部 dropout 另行立项。

## 2026-07-15 D2 ceiling-aware v2 正式证据 P1 报告缺口关闭

- **关闭范围**：D6 system-evidence consumer 结构化保留 D2 source schema/policy、promotion
  recommendation/candidates、selected/default path、overall/per-difficulty assessment、五 gate
  reason、IDSW/continuity/false-track/P95/truth leakage 和 dropout truth-alignment summary。
- **正式证据**：六 difficulty confirmation 各 20 seed。总体 GNN 五 gate 通过，但仅建议评审；
  clutter/combined 分档通过，delayed_noisy/dropout/nominal/tight_crossing 因 baseline IDSW=0
  fail-closed。dropout screening/confirmation 为 10/20 个 partial case；JPDA research adapter
  不准入，`default_online_path_changed=false`。
- **fail-closed/legacy**：缺 source-level decision 的 legacy artifact 对 promotion、路径、分档和
  alignment 输出 `None/unavailable`，D6 不从逐 seed 指标重算 D2 判决。
- **bundle 边界**：D2 是唯一 available source；D1/D3/D4/D5/D7 无同批 case/seed 可安全复用，
  因此显式 unavailable，`full_system_decision=not_evaluated`，不伪造全系统通过。
- **验证**：四件套位于
  `research_modules/d6_evaluation_metrics/outputs/p1_identity_ceiling_aware_v2_20260715/`；
  2026-07-15 专项 `31 passed`、D6 全量 `243 passed`，未启动 AirSim。
- **剩余 P1**：D2/main owner 的 promotion 评审与任何默认路径变更；同一 case/seed 的完整多源
  system bundle、跨批次趋势和长期失败原因治理。以上不是当前 D6 consumer/report 缺口。

## 2026-07-15 分阶段延迟可观测性 P1 代码缺口关闭

- **关闭范围**：严格消费 main bus/control tick 两层 timing；校验 schema/scope、frame/timestamp、
  预算、阶段状态和值、阶段和、总耗时、未归因耗时、预算 flag 和 error 状态。
- **fail-closed**：负数、NaN/Inf、状态冲突、重复/倒序帧、和式及预算冲突均拒绝；旧 artifact
  缺 timing 为 unavailable，不补零。
- **报告**：每层独立输出 sample、mean/P95/max、N/A/error、总 tick、预算违例和 dominant
  stage；历史接线为 P1 acceptance v5，当前 case-aware 接线为 v6；嵌套层禁止相加。
- **证据**：2026-07-15，动态规模无关、seed N/A fixture，合法两层各 2 帧及负例矩阵；专项
  `20 passed`、D6 全量 `236 passed`，未运行 AirSim。代码门限已满足。
- **剩余 P1 更新**：M5N2 多 seed timing 已取得并确认 `100 ms` 未达标；正式 case-aware suite
  接线已关闭，瓶颈优化及 paired/跨提交趋势仍开放。聚合外 `png_ttc` seed001 不在本批，其余 tuned 2v2
  和全部 dropout 未执行。本批不改变 P2/P3。

## 2026-07-14 P1 actual target-state freshness/stale GAP 关闭

- **关闭范围**：canonical builder/validator、逐 case evidence、pooled aggregate、aggregate CSV/JSON
  与中文 Markdown 已形成正式链路。输入严格限定为最终 `control_commands.csv` 的 control、
  measurement、arrival、age、stale、source 六字段。
- **fail-closed 门**：缺列、空值、非有限/负数、measurement>arrival、arrival>control、age 冲突、
  非规范 stale 布尔和空 source 均使 case unavailable；不补零。显式零 stale 与真实正 stale 都是
  available 观测。
- **来源验证**：formal validator 先验证 path/SHA256，再从 CSV 重算完整 summary 并逐项比对
  payload；不能只信 envelope JSON。availability/source/semantics 随 case 和 aggregate 保留。
- **真实证据**：2026-07-14，tuned 2v2 seed-1=`48` samples、mean/p95/max=
  `0.0375/0.2/0.2 s`；M5N2 seed-1=`608`、`0.091118/0.2/0.2 s`。两例 stale=`0`，source
  distribution 分别为 `d2_estimated_global_track:48/608`；required freshness case=`2/2` available。
- **验收**：缺字段、时间冲突、age 冲突、非法值、显式零 stale、真实正 stale、source 分布和
  payload/source 伪造均有回归；D6 全量 `216 passed`，1 条既有 Matplotlib warning。
- **状态更新**：顶部 20-case 已补齐 10389 条同配置 multi-seed freshness 样本，stale=0。剩余 P1
  是跨提交长期回归、failure taxonomy 和独立批次复验；physical、末端五层、truth 隔离、
  availability 语义、P2/P3 均未改变。

## 2026-07-14 actual v2 真实 AirSim GAP 状态

- **P0 actual 证据门关闭**：tuned 2v2 seed-1、M5N2 seed-1 的 canonical v2 均通过校验，
  required/available/unavailable=`2/2/0`，达到 required 全可用且 unavailable=0 的接受门限。
- **旧 physical conflict 关闭**：两场景 summary/CSV/actual 物理成功计数均为 `2/2/2`，
  `d7_actual_execution_command_physical_count_conflict` 未复现，不再是 main P0。
- **M5N2 结果不是缺证据**：pair=`2/3`、target=`2/2`、coalition=available `0/1`。第二
  required primary 未进入 5 m 是开放性能缺口；target 成功不能重分类 coalition。
- **完整 P1 仍开放**：`overall_acceptance_passed=false` 因为本批 2 case、每配置 1 seed，缺
  baseline/candidate 配对、1-5 帧 dropout 全矩阵和 multi-seed，不是 actual unavailable。
- **性能 P1 仍开放**：loop latency=`123.3/384.6 ms`，budget violations=`19/212`、合计 `231`；
  两场景均超过 `100 ms` 预算，需 main/runtime 时延拆分和真实复验。
- **变更边界**：本项只同步 2026-07-14 真实 AirSim 证据和 GAP 分类，不修改 D6 代码、schema 或
  算法。P2/P3 状态不变。

## 2026-07-14 actual-execution/arrival 口径复核（真实重跑前历史）

- **D6 P0 状态**：代码级 P0 已关闭。required case 只有通过校验的 canonical
  `d7-actual-execution-metrics-v2` 才 available；缺失或 explicit unavailable 会令 suite 总验收
  fail closed。legacy main row 与离线五米结果仅 diagnostics，不能替代 actual envelope。
- **coalition 口径**：`arrival_coordination_required=false` 时，每个 required active primary 独立
  进行五米成功判定，全部成功才完成该 target coalition；denominator/member/physical result/
  coordination 字段缺失或 summary-pair 冲突仍为 `null/unavailable`。
- **验证**：2026-07-14，确定性代码级 fixture，专项 `14 passed, 24 deselected`、D6 全量
  `190 passed`。唯一 Matplotlib `Axes3D` warning 仅限制 3D projection，不影响 JSON/CSV/Markdown、
  二维报告或本轮结论。未运行 AirSim。
- **仍开放 main P0**：M5N2 baseline、M5N2 candidate、2v2 PNG-TTC、1-frame dropout 四个历史
  真实 seed-1 actual artifact 仍为 `unavailable`，原因均为
  `d7_actual_execution_command_physical_count_conflict`；main 必须真实重跑并注册有效 v2 artifact。
- **仍开放 P1**：seed-1 关闭后，同配置 multi-seed 的 source/schema/hash provenance、
  freshness 跨提交趋势和 failure taxonomy 仍需真实证据；单 seed 正式分布链已由顶部关闭。本轮不改变 P2/P3，也不扩展
  D6 算法范围。

## 2026-07-14 owner provenance 过严 P0 关闭

- **根因**：旧 `_row_requires_owner()` 使用 OR，导致中心已授权行以及未授权 pending 行仅因状态或
  authorization 任一条件成立就被要求提供 D4 owner。
- **关闭内容**：owner 仅在 effective control 已授权且行表示 secondary/distributed
  active/execution/reassignment，或显式 `execute_secondary/execute_distributed` action 时必填。
  中心授权和未授权 pre-transition/pending 空 owner 合法；无 authoritative owner 时 provenance
  为 unavailable；owner-required 行缺值继续 fail closed。plan ID/version 仍逐行必填。
- **验证**：2026-07-14，seed N/A，中心授权空 owner 正例与 secondary effective-authorized 空 owner
  负例达到接受门限；execution-evidence focused `20 passed`、D6 全量 `184 passed`，1 条既有
  matplotlib warning。未运行 AirSim。
- **状态**：D6-owned P0 关闭；真实 SimpleFlight seed-1 注册已由顶部证据关闭，multi-seed
  provenance P1 不变。

## 2026-07-14 actual plan identity metadata P0 关闭

- **根因**：actual truth/safety/state 已进入 envelope，但最终 merge 的
  `metrics.metadata.plan_ids` 仍可为空；旧 merge 也会保留 replay metadata，无法证明计划身份
  来自执行命令。
- **关闭内容**：v2 builder 严格提取 `plan_id/plan_version/d4_target_node_id`，发布去重
  `plan_ids/plan_versions/owner_node_ids` 及 source/availability/semantics；缺失、坏类型、同 plan
  版本冲突和来源不一致均 fail closed。validator 在 hash 路径重读 CSV，merge v3 只复制 validated
  actual metadata，绝不从 replay 推断。
- **验证**：2026-07-14，seed N/A，7 个新增及 2 个扩展的 deterministic 离线场景；focused
  `24 passed`、D6 全量 `180 passed`、`py_compile` 通过，1 条既有 matplotlib warning。没有运行
  真实 AirSim。
- **剩余 P1**：真实 seed-1 v2 artifact 与 freshness/stale 单 seed 正式链均已关闭；仍需同条件
  multi-seed 的 seed/config/schema/hash、长期 freshness 趋势和 failure taxonomy；D2 lifecycle-D3 churn
  跨源 join。P2 optional benchmark 状态不变。

## 2026-07-14 actual SimpleFlight execution evidence P0 收尾（真实重跑前代码状态）

- **确认的 P0 根因已关闭（D6 owner）**：原逐 case structural consumer 可把无显式执行阶段的
  `integrated_replay/d7_execution_metrics.json` 认作 D7 execution，merge 在 actual 缺失时也可
  回退 replay execution-like 数值。当前两条路径均 fail closed。
- **canonical 合同已实现**：`d7-actual-execution-metrics-v2` 强制 producer
  `main_airsim_runtime`、phase `post_simpleflight_control`、scope `actual_execution`、case/seed/
  scale、三份 source path+SHA256、逐指标 availability 和正 performance sample。
- **builder/writer 已实现**：main 可直接调用 `build_d7_actual_execution_evidence()` 或
  `write_d7_actual_execution_evidence()`；D6 只读最终 CSV/JSON 并原子写证据，不调度 AirSim。
- **执行语义已关闭**：actual mode 只统计同时获得 effective control 的 mode transition；强制
  `mode_switched_count <= control_allowed_count`。无样本 `0 ms`、source 缺失/冲突、hash 变化、
  raw/effective control 不一致均 unavailable。
- **现有证据复核**：2026-07-14，M5N2 seed-1 baseline/candidate。raw replay mode 为 17/13、
  loop 均为 0；builder actual mode 均为 0，sample 为 142/141，loop 为
  386.519/398.333 ms，physical 均为 0。未重新运行 AirSim。
- **测试**：D6 全量 `168 passed`，1 条既有 Matplotlib warning。
- **当时仍开放的 main P0/P1**：runtime 必须在三源 finalize 后生成独立 artifact 并注册，随后复跑真实
  seed-1；成功后才能把 D7 execution case 标为 available。multi-seed 趋势仍为 P1。不得继续
  注册 integrated replay，也不得仅改名。

本批没有修改 P2/P3 状态。

## 2026-07-14 terminal closure case evidence GAP 更新（先前四案例）

- **D3 suite consumer GAP 已关闭**：D6 直接消费 main 每行显式
  `d3_plan_history`，按 `(case_id, seed)` 独立校验并输出 case/seed/suite 汇总。现有
  `p1_terminal_closure_semantics_v2_seed1_20260714` 为 4/4 case available、543 records；不再错误
  显示 canonical history unavailable。
- **D7 D6-side fail-closed GAP 已关闭**：路径未登记、文件缺失、JSON/schema/seed mismatch 均
  输出明确 unavailable reason，缺失 metric sum 为 null。D6 不扫描相邻目录，也不把 raw D7
  metrics 当成 terminal envelope。
- **main runtime wiring 仍为 P1，owner=main**：正式 summary 的 4 个
  `d7_execution_metrics` 仍为 null，因此当前正确状态是 0/4 registered，而不是执行计数为 0。
  D6 已提供 `register_terminal_closure_case_evidence()`；main 应注册 episode output path 后重生成
  seed-1 suite，再进入 multi-seed。
- **验证**：suite aggregation、per-case、未注册、缺文件和 D3/D7 schema mismatch 均有回归；
  D6 全量 `159 passed`，1 条既有 matplotlib warning。显式注册现有 4 个 D7 文件的临时副本为
  4/4 available，control allowed sum=51，且未重复进入 main terminal layer。

本批没有新增 D6 P0。剩余 P1 是跨模块正式 path registration、正式 suite 重生成和多 seed
证据；P2/P3 状态不变。

审计范围：`research_modules/d6_evaluation_metrics/**` 的当前代码、测试和文档，以及 `subagent_reviews/D6_*`。本文只评估 D6 离线指标模块状态；D6 消费日志，不参与控制，不生成任务、授权、导引、火控、毁伤或自动处置动作。

## 2026-07-14 terminal suite P1 GAP 关闭入口

- **语义 envelope GAP 已关闭**：`d6-terminal-metric-envelope-v1` 强制 terminal count 携带
  producer、metric_scope、正 denominator、lifecycle；聚合键含 source，多个语义组时顶层不
  求和。main planned-lock 与 D7 execution 不再因同名混合。
- **D3 terminal input GAP 已关闭**：`P1AcceptanceInputs.d3_plan_history` 与 CLI
  `--d3-plan-history` 复用 canonical validator，输出 latest plan/version、primary/reserve
  membership、owner 与 feedback churn；缺文件/坏历史 unavailable。
- **性能假零 GAP 已关闭**：`loop_latency_ms` 与
  `performance_budget_violation_count` 要求正 sample count；无样本 0/0 不进入聚合。
- **promotion GAP 已关闭**：candidate non-degradation 同时要求 effectiveness；baseline/
  candidate=0 且 trigger=0 时为 inconclusive，promotion=false。
- **报告 GAP 已关闭**：`d6-p1-unified-acceptance-v2` 输出 per-seed CSV/JSON、terminal metric
  CSV、aggregate CSV/JSON、中文 Markdown 和 PNG，contract/control/mode/physical 保持分层。
- **关闭证据**：2026-07-14，4 类确定性 file fixture，seed 1/2/7 或 N/A；专项 `8 passed`、
  canonical 专项 `24 passed`、D6 全量 `154 passed`，1 条既有 matplotlib warning；未运行
  AirSim。
- **仍开放的 main P1**：`p1_terminal_closure` 需生产 envelope、physical context、performance
  sample count、candidate trigger/effect，传入 D3 history/D7 execution 文件并形成真实同条件
  multi-seed 证据。该项不属于 D6-owned 代码缺口。

## 2026-07-14 physical provenance gate P0 关闭入口

- **身份/状态混淆 P0 已关闭**：新增 availability-aware
  `truth_state_online_use_count`，与既有 `truth_identity_online_use_count` 独立；strict D2
  estimated-state 为 available `0`，显式 actor-truth fixture 为 `>0`。
- **绕过路径 P0 已关闭**：availability 不再只在 `pair_events` 非空时校验证据；summary 与
  active pair summaries 都是必需项，command-only/summary-only 均 fail closed。layered physical
  计算不再从 command rows 构造 pair，也不读取 summary aggregate 作为无 pair 回退。
- **逐 pair provenance P0 已关闭**：每个 active assigned pair 必须显式
  `physical_evidence_available=true`，且 `target_state_source` 与 summary
  `online_control_state_source` 一致。offline scorer 只接受 D2 estimated class；truth fixture
  只接受显式 fixture class，并必须写出可判定 physical result。仅 evidence=true 不足；缺结果
  使 pair/target/coalition 全部 `None/unavailable`。
- **coalition completeness P0 已关闭**：required-primary 写盘成员不足、缺 arrival window、缺
  denominator 或 summary opportunity 缺 completion 时 coalition unavailable；完整显式零保持
  available `0`。availability、coalition metadata 与 CSV/JSON/Markdown reason 一致。
- **loader 缺口已关闭**：command CSV 保留 `physical_evidence_available`，但仅作审计，不能单独
  证明 physical success；legacy 无来源 status 不晋升。
- **传播已关闭**：replay consumer、EpisodeMetrics、standard mapping、merge、CSV/JSON/Markdown
  均保留字段、availability 和 source。
- **关闭证据**：2026-07-14，7 类确定性离线 provenance 场景、seed N/A；合法 offline scorer
  与合法 truth fixture 为 available 正例，legacy/command 缺证据/summary-only/source mismatch
  为全层 unavailable 负例。D6 全量 `143 passed`，1 条既有 matplotlib warning，未运行
  AirSim；新增 7 项 result/member/window/denominator/显式零回归后全量为 `150 passed`。
- **历史限制**：2026-07-11 至 07-13 缺新 provenance 的 physical 数值只作迁移前历史证据，
  不满足当前 offline scorer 验收。
- **开放 P1**：本次 physical provenance 章节只关闭对应 D6 P0，不等于真实 multi-seed AirSim
  physical 证据完成。target-state freshness/stale 单 seed 正式链已由本文顶部关闭；同条件
  multi-seed、逐 pair provenance 和长期 freshness 趋势仍开放。

## 2026-07-14 truthless tracking P0 关闭入口

- **P0 根因已关闭**：三个 truth tracking 字段由默认 `0/0/0` 改为 Optional；collector 没有
  truth-to-track pair 时发布 null/unavailable，完整 identity history 的 IDSW 零保持
  available `0`。
- **传播缺口已关闭**：JSON、episode CSV、summary/Markdown、main-bus loader 和 execution
  merge 都以 availability 为准；遗留 unavailable 零不再进入统计，`id_switch_count` 字段仍
  显式存在。
- **关闭证据**：2026-07-14，5 个确定性场景、seed N/A。空输入/匿名 track 全 unavailable；
  不完整 sidecar 不补 RMSE/continuity 零；完整 stable/switch 的 IDSW 为 available `0/1`。
  门限全部满足，D6 全量 `137 passed`，1 条既有 matplotlib warning；未运行 AirSim。
- **仍开放 P1**：真实 multi-seed source 的 seed/config/schema/hash provenance 完整性；D2
  track lifecycle 与 D3 plan/membership churn 按 episode clock、global track ID、plan/version
  的 join 与趋势报告。两者没有被单元 fixture 关闭。
- **P2 不变**：外部 MOT/HOTA、OSPA/GOSPA、Stone Soup 和 recording parser 仍 optional。

## 2026-07-14 第二批当前 GAP 状态入口

- **canonical schema GAP 已闭合**：D6 正式识别 main `d3_plan_history_v1` wrapper 和 D3
  `d3_plan_history_record_v1` record，不再依赖 cooperative snapshot 推断 churn。
- **顺序与 schema 治理已闭合**：至少 2 条、record_count 一致、sequence index 唯一严格递增、
  ordering key 一致且严格递增、timestamp 不倒退、record 结构正确且无 truth 字段。失败时
  history-derived 指标全 unavailable，原因进入 CSV/JSON/Markdown。
- **成员计数缺口已闭合**：membership 由相邻 assignment 的 target/resource/role/activation
  状态计算，不累加 `membership_change_records`；新增总体、primary、reserve 三项。
- **owner/feedback 审计已闭合**：owner 按 active owner/node 变化计数；soft/hard feedback
  汇总 canonical per-tick 显式 count。有证据才 available。
- **兼容性已闭合**：旧 snapshot、旧 ordered history、formal cooperative-role 继续可读；
  snapshot/cooperative-role 无时序证据时 churn 仍 unavailable。
- **验证**：2026-07-14 专项 `24 passed`、D6 全量 `132 passed`，1 条 matplotlib `Axes3D`
  环境 warning。覆盖稳定零、版本/成员/owner/feedback 变化、乱序、重复索引、timestamp
  倒退、单记录、schema/count/order key 错误和无 truth 字段。
- **开放 P1**：真实 AirSim/main multi-seed episode 的持续报告、跨提交趋势和统一 failure
  taxonomy。本轮没有新物理实验，不把 fixture 结论升级为系统性能结论。
- **开放 P2**：真实 py-motmetrics benchmark 标定、TrackEval/HOTA、Stone Soup metrics、
  OSPA/GOSPA 和 AirSim 原生 recording parser，均保持 optional/offline。
- **调用边界**：CLI `--d3-plan-history <d3_plan_history.json>`；Python API 传
  `P1SystemEvidenceInputs(d3_assignment_churn=history_path)`。D6 不修改 main/D3。

以下第一批 2026-07-14 GAP 与更早章节是历史审计快照。

## 2026-07-14 第一批 GAP 状态入口（历史）

- **评估级 P0 已闭合**：D3 最终快照、空 mapping、单条无序记录不再把 plan version、
  coalition version、coalition epoch 和 membership change churn 推断为 available `0`。
- **可用性判据已闭合**：显式 count（包括显式零）优先；否则必须有至少两条顺序明确且
  同名字段完整的历史记录。稳定有序历史才允许计算 available `0`，字段缺口保持 unavailable。
- **正式分支兼容**：40-case cooperative-role `pair_rows` 仍展开 D3 主用/备用角色，四项
  churn 均 unavailable，不从 `plan_id`、最终版本或 case 数推断。
- **验证证据**：2026-07-14 使用最终快照、空输入、单条无序、两条稳定有序、显式零 5 类
  fixture。验收标准为前三类四项全 unavailable、后两类四项全 available `0`；专项
  `12 passed`、D6 全量 `120 passed`，1 条 matplotlib `Axes3D` 环境 warning。
- **开放 P1**：上游 D3/main 的真实有序 plan history、统一 episode clock、version/epoch、
  provenance/availability；长期真实 multi-seed 跨提交趋势；跨批次失败原因 taxonomy 治理。
  这些是 producer/evidence 治理，不再是 D6 默认补零逻辑。
- **开放 P2**：真实 D2/D5 replay 的 py-motmetrics benchmark 标定；TrackEval/HOTA、Stone
  Soup metrics、OSPA/GOSPA、AirSim 原生 recording parser 等 optional/offline 能力。
- **边界不变**：修复仅作用于离线归一化和报告 availability，不参与分配、重规划、AirSim
  调度或控制。

以下 2026-07-13 及更早 GAP 章节是历史审计快照；其 P0 结论和测试计数不覆盖本节。

## 2026-07-13 历史最终 GAP 状态入口

- **原始与修正 schema 缺口已闭合**：统一入口支持 cooperative 原始 `cases/pair_rows/aggregates` 和修正后的 `d6-cooperative-closure-v2` aggregate；修正 aggregate 没有的逐 pair、seed 或实际规模不会被构造。
- **冻结证据展开已闭合**：当前统一报告可展开 D1 1 条、D2 3660 条、D3 40 条、D4 60 条、D5 per-primary 160 条、native MOT 18 条和 D7 164 条。D7 包含 160 条 pair/safety 记录与 4 条 profile 汇总，聚合时不重复计数。
- **M5N2 profile 分组已闭合**：最佳 profile coalition 为 `5/10`，四个 profile 总体为 `8/40`；不再按 `case_id::profile` 错分成 40 个单 seed 组。未达到 `8/10` 是实测性能结果，不是 D6 availability 或分母缺口。
- **D7 四层语义已闭合**：contract `35`、control `7`、mode switch `9`、physical `62`；contract/control/mode/physical 只读取同层证据，不跨层补值。
- **安全审计已闭合**：online truth use、`global_track_id` rewrite、reserve unauthorized execution 均为 `0` 且 available；truth 只供 D6 离线评分。
- **D3 churn 边界明确**：当前 aggregate 缺少逐时刻 plan history/churn，因此 D3 churn 必须保持 `unavailable`。D6 不从最终 snapshot、version 总数或其他模块事件伪造时序指标。
- **回归状态**：D6 全量测试为 `115 passed`；另有 1 条本机 matplotlib `Axes3D` 环境 warning，不影响二维报告图生成。
- **开放 P1**：长期真实 multi-seed 趋势、真实逐时刻 producer schema 和跨批次失败原因治理。它们属于持续 evidence/schema 治理，不是当前 D6 聚合器运行 blocker。
- **P2 边界**：TrackEval/HOTA、Stone Soup metrics、OSPA/GOSPA、py-motmetrics 扩展和其他可选工具不进入默认依赖、默认报告主线或在线控制路径。

以下较早日期章节保留历史审计演进；发生冲突时，以本节为准。

## 2026-07-13 P1SystemEvidence 正式 M5N2 schema 历史修复记录

- **原始 schema 0 行缺口已闭合**：统一入口显式识别 `cases/pair_rows/aggregates`，D3 展开 40 个 case 角色行，D5 展开 160 个 pair/safety 行，D7 展开 160 个 pair/safety 行与 4 个 profile 汇总行。
- **修正 aggregate unavailable 缺口已闭合**：`d6-cooperative-closure-v2` 可从 `funnels.pair/common_lock/primary_source.aggregates/acceptance.checks` 恢复 D5 与 D7 聚合证据；不生成不存在的逐 pair、seed 或实际规模。
- **D5 语义已分开**：visible、associated/locked、per-primary common-lock participation 与 coalition common-lock 不互相替代；reserve 不进入 active-primary 分母。
- **D7 分层已保持**：contract/control/mode/physical 不跨层推断，profile 汇总与逐 pair 层级不重复计数；coalition 总体为 `8/40`，最佳 profile 为 `5/10`。
- **安全证据已恢复**：reserve unauthorized=0、global track ID rewrite=0、online truth use=0 均为 available，不再因 loader 漏读标为 unavailable；truth 仍只供 D6 离线评估。
- **分组回归已闭合**：固定 fixture 强制 4 个 profile，而不是 40 个 `case_id::profile` 组。D6 全量测试为 `115 passed`，另有 1 条本机 matplotlib Axes3D 环境 warning。
- **当前状态**：本项 D6-owned P1 adapter 缺口已闭合。真实最佳 profile 未达到 `8/10` 是上游实验结果，不是 D6 分母或 availability 缺口。

## 2026-07-13 M5N2 真实 40-case 聚合缺口修复

- **profile 分母缺口已闭合**：acceptance 不再按 `case_id + profile` 拆成 40 个单 seed 组，而是按 profile 聚合唯一 seed；case/seed 明细仍完整保留在 CSV。
- **coalition 单位缺口已闭合**：普通单 primary 目标不再计入 coalition；同一稳定 `coalition_id` 的成员跨滚动 version/epoch 合并，版本与 epoch 仅保留审计。
- **profile 选择已闭合**：优先采用 source `best_candidate_profile`；缺失时使用确定性 fallback 排序并在报告中写明 `profile_selection_source`。
- **availability 缺口已闭合**：验收输出 passed/failed/available/unavailable seed 数；`coalition_at_least_8_of_10` 在 10 个有效 seed 下为 available，未达 8 个时为 failed，不再误标 insufficient evidence；unavailable 不计 0。
- **真实回归证据**：40 case、4 profile、每 profile 10 seed fixture 验证最佳 profile `d3-p1-h020.0-w03.0-s040.0` 为 `5/10`；四 profile 分别为 `0/10、5/10、2/10、1/10`，全 profile coalition funnel 为 `8/40`，与 source summary 一致。
- **当前状态**：该 D6-owned 聚合 bug 已闭合，没有新增 P0/P1 D6 代码 blocker。真实结果仍未达到 `8/10` 工程门限，这是上游实验结果，不是 availability 或分母问题。

## 2026-07-13 P1 统一验收 GAP 状态

- **D6-owned 代码缺口已闭合**：统一入口现可消费 D1 dense-crossing、D2 六难度关联、D3 M5N2 assignment、D4 fault matrix、D5 per-primary/native MOT 和 D7 guidance/physical evidence，输出逐 seed CSV、聚合 JSON、中文 Markdown 和 PNG。
- **四层口径已闭合**：contract/control/mode/physical 只读取同层证据；显式 0 与 unavailable 分离，未提供 physical 字段时不会由 mode 或最近距离补写。
- **可复现性已闭合**：source manifest 和逐行 CSV 保留 schema、路径、SHA256、producer/run/provenance；逐 seed bootstrap 95% CI 使用固定 2000 次重采样和固定 RNG seed，少于两个 seed 时 unavailable。
- **失败分析已闭合**：D1 rejected observation、D2 admission、D4 fault/ACK、D5 lock/MOT、D7 first-failure 均进入来源级和全局失败原因分布；缺原因字段不记为零。
- **最终 evidence 已接入**：真实 AirSim 4 m/2 m dense crossing、M5N2 10-seed、D4 episode-time fault 和 native MOT 产物已经进入统一报告。后续 P1 转为长期趋势、逐时刻 schema 和失败原因治理；D6 不构造缺失证据，也不据此调整在线算法。
- **P2 状态不变**：本轮未推广 Stone Soup、TrackEval/HOTA、OSPA/GOSPA 或其他可选算法。

## 2026-07-12 D1/D2 dense-crossing 第二批补充

**本轮 D6-owned P1 报告缺口已闭合**：新增 `d6-dense-crossing-evaluation/v1` 离线 bundle，可消费 D1 governed manifest/offline truth summary 和 D2 `d2-p1-identity-calibration/v1` 的 10-seed screening、20-seed confirmation、轻量 JPDA comparison。输出逐 seed CSV、聚合 JSON、中文 Markdown、PNG 曲线和失败原因分布，且不参与控制。

已落实的门限治理：

- GNN baseline、最佳 GNN candidate、轻量 JPDA 独立分组，adapter smoke 不参与排名。
- 历史 `d6-dense-crossing-evaluation/v1` 只有在 20-seed confirmation 同时满足 IDSW `-30%`、identity continuity `+0.10`、false track 不高于 `1.10x` baseline、p95 latency 预算和 truth isolation 时才输出 promotion；`+0.10` 已标记为 legacy，不再用于 D2 v2。当前统一 system-evidence v2 只消费 producer 显式 ceiling-aware 判决和可用性，不自行晋级算法。
- 任一指标、D1 truth-isolation 证据、预算或 seed 数不足均为 unavailable，不补 0。
- 轻量 JPDA 即使通过也只能成为隔离候选，不宣称完整 JPDA 已实现。

**仍开放的 P1 evidence**：真实 AirSim dense/crossing 10/20-seed 文件尚需 main 调度生成；D2 当前 per-seed 只提供 NIS/NEES availability，没有均值，因此 D6 对 NIS/NEES 数值保持 unavailable。该限制是上游 evidence 缺失，不是 D6 loader 缺口。

代码/测试证据：`dense_crossing_evaluation.py`、`run_dense_crossing_evaluation.py`、`test_dense_crossing_evaluation.py`。

## 2026-07-12 cooperative-closure-v2 GAP 状态

- **D6 P1 报告缺口已关闭**：通用 line-record loader、pair/target/coalition 独立分母、第二 primary failure、共同锁定、到达离散、成员间距和通信故障统计均已实现。
- **D4 communication 合同别名已关闭**：真实 D4 dataclass/`to_dict()` JSON 的顶层 `cases` 优先于 `seeds`；`scenario_id -> communication_fault`、`passed -> communication_passed` 已在 D4 专用归一化中固定，`fail_closed` 保持原始证据。`normal`/`delay_0_5s` 的 pass available/rate 已由真实 D4 合同测试覆盖。
- **availability 已关闭**：D3/D4/D5/D7 可选证据缺失时为 unavailable，不补零；共同锁定没有显式同窗证据时不从 associated 推断。
- **验收输出已关闭**：coalition `>=8/10`、reserve unauthorized、global ID rewrite、online truth use 四项检查为 advisory-only，并已输出逐 seed CSV、聚合 JSON、中文 Markdown 和 PNG。
- **剩余 P1 是上游真实 evidence**：main 需写出真实 M5N2 多 seed 行记录；D4 需写 communication fault/pass/fail-closed；D5/main 需写 common-lock 同窗证据；D3/D7 需稳定写 candidate/guidance summary。证据未落盘不构成 D6 代码 blocker。

## 2026-07-12 P1 第二批统一验收 GAP 状态

- **D6 聚合代码缺口已关闭**：新增统一 loader/report bundle，离线消费 main `p1_terminal_closure_summary.json` 和 D1/D2/D3/D4/D5/D7 版本化 summary，输出逐 seed CSV、聚合 JSON、中文 Markdown 和 PNG 图。
- **语义门控已关闭**：contract/control/mode/physical 四层不互推；pair/target/coalition 不互相回填；旧字段缺失保持 unavailable。D2 `id_switch_count` 继续显式输出。
- **本地 fixture 已覆盖**：M5N2 paired、1-5 帧 dropout、`png_ttc` 四类拒绝、trend coast 晋级、D4 failover 和 D2 IDSW/continuity 的消费与报告均有测试。
- **仍开放的 P1 是真实 evidence**：main 尚需运行同几何/同窗口的 AirSim M5N2 paired 和真实 dropout/`png_ttc`；D4 的 9/9 合成扰动矩阵尚需映射到真实链路时序；D5 真实外参/时间同步与持续视觉仍需多 seed；D1-D3 合成长 replay 尚需真实 Blocks/CV 对照。
- **P2 不变**：Stone Soup、TrackEval/HOTA、OSPA/GOSPA 和完整外部 benchmark 不进入本轮主线。
- **main-summary fallback 已修复**：独立 D7 summary 缺失时，D6 直接消费 main 的版本化 dropout matrix、`png_ttc` family rows 和 candidate trend 实际触发；不再把三类专项误报为 unavailable。
- **真实 smoke 已复核**：1-5 帧 dropout complete/compliant；`png_ttc` seed=1、not-expanding=1；trend trigger=0、promotion=false。四层同名字段当前尚未写入该 smoke，因此保持 unavailable，等待 main 新输出后自动读取。
- **M5N2 分母已收紧**：pair/target/coalition 只汇总 `m5n2_paired`，不再混入 2v2 dropout/`png_ttc` 行。

## 2026-07-12 D7 PNG Delivery GAP 状态

- **D6 侧接口已闭合**：terminal filter measured/predicted/innovation-rejected/reset/expired、TTC 四类拒绝、soft prediction/coast duration/expiry、terminal lock continuity、visual mode duration、command discontinuity 已进入 `EpisodeMetrics`、availability 和标准映射。
- **报告已闭合**：baseline/candidate 多 seed 可输出逐 episode CSV、聚合 JSON 和中文 Markdown，按显式 profile、scope、scenario 与实际 N/M 分组；2v2/M5N2 以及 pair/target/coalition 口径保持分离。
- **P0 保持闭合**：当前没有新增运行级 P0 blocker。实际规模、显式 `id_switch_count`、online truth 隔离、execution/contract/evidence availability 和标准映射保持原状态。
- **P1 实测已更新**：D6 对照包消费 26 个 episode 并形成 4 个独立分组。2v2 baseline 10 seeds 为 pair/target `19/20`，candidate 10 seeds 为 `20/20`；四层 logging smoke 为 `contract_allowed=4/36`、`control_allowed=2/36`、`mode_switched=5`、`physical_intercept=2/2`。早期日志缺新列时继续为 NA。
- **P1 M5N2 仍开放**：35 s 高净空 baseline 为 target `6/6`、active-primary pair `6/9`、coalition `0/3`；8 s candidate 为 active pair `0/9`、最近距离 22-32 m。两批条件不等价，不能形成 paired 结论。
- **P1 上游 evidence 仍开放**：main/D7 需要持续写出 profile、滤波状态/原因、TTC 拒绝原因、soft/coast elapsed、锁定状态、视觉模式和三轴速度命令。还需完成同几何/同窗口 M5N2 paired baseline/candidate、独立 `png_ttc` 多 seed、1-5 帧 dropout 矩阵和 trend coast 默认 profile 判定。缺失字段由 D6 标为 unavailable，不构成 D6 代码 blocker。
- **模块边界不变**：D6 不根据这些指标调整 D7 参数，不把 coast 当授权证据，也不参与导引控制。
- **该 D7 专项边界**：当时任务只同步 PLAN/GAP/README；本轮已经新增 P1 多来源统一 loader/report/tests。P2/P3 保持原规划。

2026-07-12 D7 专项阶段回归为 `84 passed`；加入 P1 第二批统一验收和 main-summary fallback 后，D6 当前回归为 `88 passed`，另有 1 条本机 matplotlib `Axes3D` warning。D7 专项直接证据仍为 `PNG_DELIVERY_ENHANCEMENT_AIRSIM_VALIDATION_REPORT_20260712.md` 及 `png_delivery_enhancement_eval_20260712/` 下的 D6 CSV/JSON/Markdown bundle。

## 2026-07-11 历史实测状态

以下内容保留当日批次结论；当前 P0/P1 判定以上一节为准。

- **P0 已闭合**：当前没有运行级 P0 blocker。实际规模、显式 `id_switch_count`、truth isolation、execution/contract/evidence availability 和标准映射继续作为强制回归。
- **P1 合同/指标接口已完成**：在既有 M 对 N/replan 能力上，新增 `d4_coalition_commit_state` 消费、扩展 CoalitionRecord、联盟 generation 去重、ACK/commit/epoch/lease/failure/secondary/distributed lifecycle 指标，以及 contract/control/switch/physical 四层验收。
- **P1 5m/M-to-N 分层验收已完成**：`collision_intercept/range_intercept` 均进入 pair physical success；pair、target、coalition 使用独立分母，coalition 只有在全部 required primary 的 arrival window 证据齐全且窗口内成功时可用。summary 的 5 m、NED、3D Euclidean 和 criteria version 被保留审计；ComputerVision physical 继续 unavailable。
- **P1 detect/coast 诊断已完成**：新增 acquisition timeout、image-KF predict、blind push、visual reacquisition、coast 后最终视觉丢失和 online truth identity use 六项离线计数，不参与控制。
- **P1 合同层已闭合**：CV 10 seeds 中 8/10 有 T001 双 primary 同帧共识与授权，10/10 IDSW=0、错误重复锁=0；secondary executing 3/3、distributed executing 3/3、missing-ACK aborted 2/3 三组正负例均被 D6 正确读取。
- **P1 物理执行仍开放**：SimpleFlight 10 seeds 已验证 4 bindings 和 3 active + 1 standby，但 30 个 active pair 为 0 命中、24 detection timeout、6 timeout。15 s 与 `control_dt=0.5 s` 只支持诊断，不支持导引律或系统命中率结论。
- **P1 长期项仍开放**：`ScenarioLibrary` 版本化接口已实现，但长期场景语料、跨提交 CI 趋势、阈值回归和真实 review/window 标签仍未建立完成。
- **P2 optional**：py-motmetrics 1.4.0 adapter 代码已隔离实现，当前真实 backend evidence 仅为 2 帧离线 smoke fixture；IDF1/MOTA/MOTP 在冻结 schema 上可计算，HOTA 明确 unavailable，可选依赖缺失时显式输出 `unavailable_reason`。真实 D2/D5 replay benchmark、TrackEval、Stone Soup metrics、OSPA/GOSPA 和其他非参数统计仍未实现。

CV 的 `control_allowed_count=0`、`physical_intercept_count=None` 与 SimpleFlight 的 `physical_intercept_count=0`（evidence available）保持分离，说明 D6 四层口径正确。可选 P2 adapter 没有替换默认在线关联/导引路径，也没有替换 D6 本地离线指标主线。该历史批次的 D6 回归基线为 `82 passed`。

同批 P2 evidence 仍按原限制标注：D2 FilterPy/Stone Soup 是对象 adapter smoke，D5 OpenCV 是离线合成标定/PnP 对照，D6 py-motmetrics 是 2 帧 smoke，D7 3D PN/APN/FRPN 是离线质点 benchmark 且 FRPN 为研究近似。上述结果均未替换默认在线路径。

### P1 闭合与开放项

| 条目 | 实测结论 | 状态 |
|---|---|---|
| D5/D6 双 primary 合同 | 8/10 seeds 达到验收阈值；2 个 seed 未形成双锁 | P1 验收闭合，保留尾部回归 |
| 二级接管 commit | plan v2 active、executing、ACK 3/3 | P1 闭合 |
| 完全分布式 commit | peer executing、ACK 3/3 | P1 闭合 |
| 缺 ACK fail closed | aborted、ACK 2/3、D7 allowed=0 | P1 闭合 |
| 绑定和角色 | 每 seed 4 bindings、3 active + 1 standby | P1 闭合 |
| 5m/M-to-N 分层指标 | pair/target/coalition 独立 count/rate；coalition 强制 required-primary arrival window | D6 接口闭合，待 main 持续写盘 |
| detect/coast 诊断 | 6 项 summary/control record 离线计数，truth identity use 可显式报告 | D6 接口闭合 |
| 2v2 SimpleFlight 非退化 | baseline `19/20`；candidate `20/20`；自然 soft/trend 均未触发 | P1 本轮验收闭合，不宣称增强贡献 |
| M5N2 paired 物理/联盟 | 35 s baseline 与 8 s candidate 不可比；candidate `0/9` | P1 开放 |
| `png_ttc` / dropout / trend coast | 2 帧 post-lock dropout 已闭合；其余缺同条件多 seed 或完整矩阵 | P1 开放 |

## 总体结论

### 2026-07-10 P1 状态更新

本轮关闭了 D6 侧四类 P1 代码缺口：

- 二级接管 `readiness -> pending -> active` 驻留、activation latency、fallback、lease expiry、stale plan reject 已进入 `EpisodeMetrics`、AirSim calibration、CSV/Markdown 和 degradation 图表。缺 lifecycle evidence 时输出 unavailable。
- YOLOv8 + ByteTrack/BoT-SORT 质量与预算字段已进入 `EpisodeMetrics` 和 `visual_perception_metrics.png`：recall、local-ID continuity、cross-view registration、pipeline latency、CPU/GPU utilization、budget violation。离线 truth 只从 `offline_truth` 读取，在线字段泄漏单独计数。
- 四导引律同 seed 配对报告和场景库/seed matrix 已实现，输出 CSV、JSON、中文 Markdown 和 PNG；D6 不修改 D7 控制算法。
- AirSim calibration 现在按 detection backend、tracker backend、experiment guidance law 和 actual scale 保持分组，`None/unavailable` 与零值继续分离。

因此上述条目从“D6 P1 待实现”调整为“D6 已实现、待 main/D4/D5/D7 真实多 seed 写盘验收”。仍未关闭的 P1 是上游数据条件和长期回归：main 需要逐帧写 lifecycle/lease/stale 事件，D5 需要真实 YOLO/MOT latency/resource/offline truth fixture，D7/main 需要四种 experiment-level law 的同 seed 批次，CI 需要消费版本化 scenario library。外部 TrackEval/Stone Soup/OSPA 等保持 P2，不在本轮构造。

### 2026-07-11 四导引律 smoke 复核

main 已修复 guidance experiment law 的执行后回灌，并生成
`p1_guidance_four_law_smoke_20260711/d6_guidance_comparison/`。D6 产物包含 21 条同
seed 指标配对记录；其统计含义是 3 个候选律相对 Radar PN 的 7 项指标，且每项
`pair_count=1`，独立样本仅为 seed 7，不是 21 个 seeds。

四律在 2 秒短 episode 中均 timeout。PNG VM/TTC 的
`terminal_switch_allowed_rate` 约为 0.762/0.810，`min_range_m` 约为
2.812/2.798 m。该证据关闭的是“guidance law 回灌和 D6 同 seed 报告链路未被真实
数据验收”的接口缺口；不关闭“真实多 seed、较长拦截窗口下的命中率和算法排序”缺口。
后者继续列为 P1，并要求保留 timeout/abort、最小距离、视觉门控与切换率的联合解释，
不得从当前全 timeout 批次宣称某种导引律命中率更高。

D6 当前已经实现一条轻量、可测试、离线的系统评估主线。`TrackRecord`、`AssignmentRecord`、`EventRecord`、`LinkRecord`、`TerminalRecord` 进入 `MetricsCollector`，输出 `EpisodeMetrics`、CSV、Markdown 和 PNG 图表。`EpisodeMetrics` 已包含探测、跟踪、分配、降级、主动降级必要性标签口径、末端、二级视角/侦察云台、通信、D7 gate/intercept 和安全指标。D6 现在也能直接读取 main runtime 已写盘的 `main_episode_bus_metrics.json` 与 `main_episode_bus_contract_metrics.json`，把 execution/contract 双口径还原为 `EpisodeMetrics`，并能通过 AirSim calibration helper 自动汇总多 seed D4/D5 stress 与 main bus metrics。

2026-07-08 main runtime 已新增 P1 D4/D5 calibration sweep，并在 batch 结束后自动调用 D6 `AirSimCalibrationReportGenerator.write_report_bundle()`，生成 `d6_airsim_calibration/airsim_calibration_records.csv`、`airsim_calibration_summary.csv`、`airsim_calibration_summary.json` 和 `airsim_calibration_report.md`。D6 只消费这些已写盘目录和文件，不参与 AirSim 启停、reset、camera/gimbal 指向、主动降级、二次分配或末端配准控制。

2026-07-08 D6 已补齐 P1 二级侦察 detect-to-registration 校准报告口径。AirSim calibration records/summary/Markdown 现在显式输出 `secondary_detect_count`、`secondary_visible_target_union_ratio`、`secondary_network_joint_full_view_frame_rate`、`projection_valid_rate`、`geometry_gate_pass_rate`、`registered_candidate_count`、`stable_cross_view_registration_count`、`not_registered_count`。reject/outcome reason 固定保留 `not_all_targets_visible`、`network_union_incomplete`、`projection_invalid`、`geometry_gate_rejected`、`stability_window_failed`、`no_global_binding`、`stale_or_missing_recon_cue`、`registered_to_global_track`，缺失字段按 0 输出，避免不同 seed/case 的 JSON key 不一致。D6 仍只统计上游写盘事实，不参与 D5 注册或 D4 降级仲裁。

规模字段 `drone_count/resource_count/target_count/camera_count` 已进入 `EpisodeMetrics`、CSV、summary 和 Markdown 报告。D6 按实际记录或 `truth_summary` 字段归一化；二级网络 full-view/coverage 与单相机 full-view 指标按实际 target/camera count 或日志显式实际计数归一化；报告按 `metric_scope/seed/scenario_group/drone_count/resource_count/target_count/camera_count` 分组；episode CSV 保留 metadata JSON，Markdown 在存在数据时输出 fixed downlook secondary vs mobile recon gimbal 对比表和 terminal switch/contract reject reason 分布；测试覆盖了场景名包含 `5v5` 但实际规模为 `3/3/4/6` 的情况。因此当前 D6 不从 `2v2/5v5` 场景名推断规模。

D2/D6 强制 `id_switch_count` 的规则已落实：`id_switch_count` 是 `EpisodeMetrics.metric_names()` 的显式字段，并有单元测试覆盖。

尚未完成的外部 benchmark 包括 Stone Soup metrics、TrackEval、OSPA/GOSPA/HOTA、AirSim 原生 recording replay 和 SCRIMMAGE bridge。py-motmetrics 已有隔离 adapter、冻结 schema 和真实 1.4.0 环境的 2 帧 smoke 验证；这只证明 IDF1/MOTA/MOTP 接线可用，不是生产级 MOT benchmark。coalition commit、终端四层指标和 2v2 非退化已有真实正负例；剩余 P1 聚焦同条件 M5N2 paired 物理/联盟验收、`png_ttc`/dropout/trend coast、长期场景库/CI 趋势、D4 review/window 长期趋势，以及更多 N-v-N、非默认 episode 的双口径回归。

2026-07-08 `research_modules/airsim_runtime/outputs/p1_d4d5_mobile_recon_20260708_055948*` 是历史 mobile recon stress 批次，可作为 D6 已能消费 `mobile_recon_gimbal`、coverage、bbox、gimbal 和 funnel 字段的旧证据，但不再作为当前 P1 结论。

2026-07-08 registration calibration v2 历史基线输出在 `research_modules/airsim_runtime/outputs/p1_d4d5_registration_calibration_runtime_v2_20260708*`，D6 bundle 已生成 `d6_airsim_calibration/airsim_calibration_records.csv`、`airsim_calibration_summary.csv`、`airsim_calibration_summary.json` 和 `airsim_calibration_report.md`。该 v2 批次为 single seed、3 case，height 200 m、FOV 110 deg、secondary_count 3；当时指标为 `projection_valid_rate=1.0`、`geometry_gate_pass_rate≈0.474`、stable cross-view registration 51/55/53、cross-view association 4/4/5、degradation case `not_registered_count=35/35`、full-view mean≈0.048、best≈0.143、coverage mean≈0.771。该批次只保留为报告链路历史证据，不再作为当前 P1 结论。

2026-07-09 D6 已补齐 P0-A/P0-C episode 状态和追踪字段。`EpisodeMetrics`、episode CSV、summary/Markdown 现在输出 `mission_outcome=success/partial/failed/aborted`、`success_reason`、`failure_reason`、`eval_priority`、`implementation_status`、`evidence_path`，并把同名字段冗余进 metadata 便于 main 报告消费。D6 基于 records/metadata 与已计算指标被动派生 `top_failure_causes`、`root_cause`、`failure_cause_scores` 和 `failure_cause_details`，覆盖 tracking、assignment、terminal_gate、guidance、coverage、runtime_exception、communication、safety、performance；不做控制因果推断或回写。性能监测已新增 `module_duration_ms`、`loop_latency_ms`、`record_latency_ms`、`cpu_budget_utilization`、`gpu_budget_utilization`、`performance_budget_violation_count`，summary 和 metadata 均保留，CPU/GPU 缺失时保持 placeholder schema。

2026-07-09 EVAL 三个 patch 进一步确认：当前没有新的运行级 P0 blocker；D6 已实现 mission outcome、根因诊断、性能、可复现字段和 `COURAGEOUS/MDPI/OCEF -> 当前 EpisodeMetrics` 标准化评估映射最小版。映射版本固定为 `cuas-standard-map-v1`，覆盖 mission/root cause、detection、tracking、assignment、degradation、terminal、communication、guidance/intercept、safety、performance、reproducibility/evidence。完整 COURAGEOUS/OCEF 报告、统计显著性、场景库管理、CI 回归摘要仍列 P1；baseline/enhanced 表格已在 AirSim calibration 报告中补齐，仍需多 seed 显著性验证。

2026-07-09 D6 已按 main 的 P1 calibration 方案扩展 AirSim calibration records/summary/Markdown：records 和 summary 现在保留 `scenario_version`、`standard_mapping_version`、`standard_metric_family_summary`、`evidence_path`、`comparison_role`、`trend_key`、`secondary_height_bucket`、`metric_scope` 和 actual scale 字段；Markdown 新增 50m vs 200m 二级覆盖对比、coverage funnel、baseline vs enhanced 表格，并继续输出 stable cross-view registration、not-registered count、active degradation precision、unnecessary degradation、D7 guidance reject reason 和 Standard C-UAS Mapping。baseline/enhanced 只消费上游显式写出的 comparison role；D6 不从 `2v2/5v5` 名称推断规模或实验组，也不接 TrackEval、Stone Soup、SCRIMMAGE 等外部 evaluator。

## P0/P1 复核结论

### 2026-07-11 M 对 N 实现复核

专项框架见 `D6_M_TO_N_EVALUATION_FRAMEWORK_REVIEW.md`。D6 已实现 `TargetDemandRecord/CoalitionRecord/ArrivalRecord`，扩展 assignment/terminal coalition/member 合同，并接入 JSONL、`EpisodeMetrics`、CSV/batch summary/Markdown。已实现 target demand micro/macro、unmet slots、over-support、formation/reconfiguration、simultaneous common-window、sequential wave、hybrid primary/reserve、geometry rejection、canonical duplicate/cross-node IDSW/common-information duplicate rejection、planned/authorized/erroneous lock、same-resource lock continuity、center replan lifecycle、member loss/replacement/digest/stale、messages/bytes/rounds/latency 和 minimum separation/collision exposure。NIS/NEES 继续复用既有 D2 governance 字段，不复制同义指标。

通用 `duplicate_terminal_lock_count` 现在严格按同一 timestamp+target 的不同 resource 计数并保持独立；授权 coalition 内不超过 `k` 的同帧多锁进入 `authorized_cooperative_lock_count`，只有 legacy `k=1`、版本冲突或超需求进入 `erroneous_duplicate_lock_count`。同一 resource 跨帧续锁只进入 continuity。探测 POD/miss/FAR 同时要求 truth opportunity 和离线 match/miss 配对裁决；仅有 truth 列表且全部 center track truthless 时为 `None/unavailable`，不判 POD=0 或虚警。每项新增指标显式记录 unavailable、available zero 或 not_applicable，batch summary 分开计数。当前 M 对 N 合同层已由 CV 8/10、二级/分布式 commit 和 missing-ACK fail-closed evidence 闭合；2v2 candidate 已达到 `20/20` 非退化门槛，M5N2 同条件 paired 物理/联盟验收与完整实验矩阵仍开放。py-motmetrics IDF1/MOTA/MOTP 已作为隔离 P2 benchmark 实现；TrackEval、Stone Soup、OSPA/GOSPA、HOTA 和 AirSim recording 仍为 P2，SCRIMMAGE bridge 仍为 P3，D6 online/live control 继续禁止。

本节按 `EVAL/FRAMEWORK_EVAL_P0_P1_P2_GAP_CONFIRMATION.md` 以及三个 patch 同步 D6 相关 P0/P1 缺口。口径与 EVAL 保持一致：当前没有运行级 P0 blocker；P0 是进入更可信 AirSim/封闭场地验证前的工程化硬化项，P1 是三个月内的标准化报告、对照统计、场景库和回归化工作。D6 继续只消费日志和已写盘 metrics，不参与控制、重规划、降级仲裁、末端配准或导引。

2026-07-10 P1 报告聚合已修复：旧逐 seed `GROUP_FIELDS` 和 records/summary 文件保持不变，新增 cross-seed aggregate 与严格 baseline/enhanced seed 配对。原始 `scenario_version` 在 records 中保留；统计键移除其中 seed 运行参数，避免真实 `seed1..seedN` 被拆成 N 个单样本组。配对仍要求稳定 `scenario_group`、规范化版本、实际规模、几何、backend 和 seed 一致；case-specific scenario/case_name 只审计。单一配对样本标记 `descriptive_only`，不输出伪 bootstrap CI/effect size。active-degradation 四字段优先消费 d4d5 stress 显式标注，再 fallback main metrics；label count 为 0 时 precision unavailable/null。

同日历史基线 `p1_gap_closure_2v2_smoke_20260710/episode_006_full_flow`：D6 从正式 execution main-bus 文件读得实际规模 `2/2/2/2`、`intercept_success_count=2`、`visual_png_switch_count=3`，contract 文件独立读取；D6 不消费 Blocks summary 中仍为 `3/3/2/0` 的旧 `integrated_result.metrics`。新增回归测试固定该优先级并保证 execution/contract record 的 evidence path 分别指向各自文件。该数据只保留为历史读取优先级基线；旧 Blocks 摘要不一致属于 main runtime P1，不是 D6 控制或回写职责。

10-seed 拦截聚合缺口已在 D6 侧关闭。calibration record/CSV/summary/cross-seed 已加入 success、collision/range/abort、min range、time-to-intercept、visual PNG switch、terminal switch allowed/takeover 和 gate reject。availability gate 已补：只有 intercept summary/control command/显式 pair-status/D7 execution event 证据才消费这些字段；episode_001..005 read-only 默认零改为 unavailable，且不进入 Outcome 表。2026-07-10 `seed001..010` summaries 的 full-flow execution `18/20`、collision/range/abort=`18/0/2` 只作为历史场景基线，不与 2026-07-11 M=5、N=2 SimpleFlight 的 0/30 诊断混合；execution/contract 按 scope 分组，未混合。计数行输出 sum，拦截 outcome 额外输出 opportunity/rate。

D6 owner 2026-07-11 当日回归基线为 `82 passed`，coalition commit、终端 contract/control/switch/physical 四层验收、pair/target/coalition 分层 physical success、detect/coast 诊断和 py-motmetrics adapter 均归入“已实现并保持回归”。合同层真实 P1 evidence 已闭合；该批次下一阶段聚焦物理执行和长期回归，不改变在线主线。

现有已完成状态保持不降级：`EpisodeMetrics`、`TrackRecord`、`AssignmentRecord`、`EventRecord`、`LinkRecord` 和 `TerminalRecord` 已作为 D6 离线指标主线保留；D7 guidance records 当前由 `guidance_records.csv`、`guidance_summaries.json` loader 转换为 `d7_guidance_record/d7_guidance_summary` 事件 metadata，而不是单独在线控制数据类。`id_switch_count`、实际规模字段、execution/contract 双口径、AirSim calibration bundle、detect-to-registration 漏斗、reject/outcome reason 分布和 D6 只消费日志不控制的边界均保持为已完成能力。

| EVAL 等级 | 同步条目 | D6 当前实施状态 | 已有证据/保留状态 | 剩余验收口径 |
|---|---|---|---|---|
| P0-A | 系统级任务成功指标 | 已实现，持续真实批次回归 | 每个 episode 已输出 `mission_outcome=success/partial/failed/aborted`、`success_reason`、`failure_reason`；显式 outcome 优先，上游缺失时从 intercept/abort/runtime/safety/部分进展指标被动派生。 | 在真实 AirSim 多 seed、5v5/N-v-N 和非默认 episode 中持续写盘并比较 execution/contract 口径。 |
| P0-A | failure reason/root cause 根因诊断 | 已实现，持续真实批次回归 | 已输出 terminal switch/contract reject reason、D5 detect-to-registration reject/outcome reason、D4 review label/后验字段和 D7 guidance reject metadata；新增 `top_failure_causes`、`root_cause`、`failure_cause_scores`、`failure_cause_details`。 | 根因类别保持被动消费，覆盖 tracking、assignment、terminal_gate、guidance、coverage、runtime_exception、communication、safety、performance；后续只随真实日志字段扩展。 |
| P0-A | 性能和可复现字段 | 已实现最小 schema，持续真实批次回归 | 新增 `module_duration_ms`、`loop_latency_ms`、`record_latency_ms`、`cpu_budget_utilization`、`gpu_budget_utilization`、`performance_budget_violation_count`；`eval_priority`、`implementation_status`、`evidence_path` 已进入 `EpisodeMetrics`、episode CSV、metadata 和 Markdown EVAL Tracking 表。 | main/D1-D7 真实 episode 持续写 module timing、loop latency、record latency、CPU/GPU budget、真实 evidence path 和 scenario/version metadata；D6 只消费。 |
| P0-A | 标准化评估映射最小版 | 已实现，持续真实批次回归 | 新增 `standard_mapping.py`，固定 `cuas-standard-map-v1`，输出 `engineering_metric`、`standard_metric_family`、`standard_sources`、`implementation_status`、`evidence_requirement`；`EpisodeMetrics` 增加 `scenario_version`、`standard_mapping_version`、`standard_metric_family_summary`；episode CSV、metadata、Markdown 和 `standard_metric_mapping.csv` 已输出映射。 | 真实 AirSim 多 seed、5v5/N-v-N 和非默认 episode 持续写真实 `scenario_version`、`evidence_path` 和同一 mapping version；不要求完整认证流程。 |
| P1 | COURAGEOUS/MDPI/OCEF 完整标准化报告 | P1 待补 | WebSearch patch 确认 COURAGEOUS/CEN、MDPI 综述和 OCEF 可复现纪律是 D6 标准化方向；当前已有本地最小映射、CSV/JSON/Markdown 指标报告。 | 在 P0 最小映射基础上增加测试阶段、复现纪律字段、evidence index、标准场景覆盖和外部审计说明；完整封闭场地/外部审计报告仍依赖 main 提供场景和日志。 |
| P1 | 基线对比和统计显著性 | 配对统计实现完成，待真实批次验证 | 保留旧逐 seed summary；新增 cross-seed aggregate、规范化 seed-bearing scenario version、严格 role/seed/actual-scale/geometry/backend 配对、missing seed、delta mean/std、paired Cohen's dz 和确定性 bootstrap 95% CI；单 pair 仅描述。 | main 持续提供显式 comparison role 和至少两个真实多 seed/N-v-N 成对数据；缺失/单一配对不形成 A/B 推断结论。 |
| P1 | 场景库管理 | D6 接口已实现，main/CI 接线待补 | `ScenarioLibrary` 已输出 stable scenario group/version、tags、difficulty、expected failure modes、parameters、seed matrix 和 online truth policy；`2v2/5v5` 只作为 baseline 名称。 | main/CI 使用标准场景库调度真实批次，并回填 coverage/evidence/trend 状态。 |
| P1 | CI 回归摘要 | P1 待补 | 当前有 D6 unit tests、报告生成测试、main bus loader 测试和手动 batch report 链路。 | 每次变更产出实验级测试矩阵、P0/P1 tracking 字段检查、性能回归摘要和 evidence path 检查。 |

P1 缺口保持为离线评估能力、真实 episode 写盘和长期趋势问题，不是 D6 在线控制职责：D7 real execution metrics 的正式/contract 双口径与 PNG delivery 对照 bundle 已完成；D6 已补 `metric_scope`、seed/scenario/profile/实际规模报告分组、main bus metrics JSON loader、reject reason 分布输出、二级视角/侦察云台 coverage/cross-view/registration/pointing-error 指标、detect-to-registration 分层漏斗、50m vs 200m 覆盖对比、baseline vs enhanced 表格、AirSim 多 seed calibration 自动汇总，以及 `active_degradation_precision`/`unnecessary_active_degradation_count` 的 review label/后验最小实现。D6 当前 P1 重点是同条件 M5N2 paired 验收、`png_ttc` 多 seed、dropout/trend coast 判定、COURAGEOUS/MDPI/OCEF 完整报告、场景库/CI、多 seed 自动汇总回归、coverage/funnel/gimbal/projection/gate/stable registration 长期趋势、active degradation precision 真实标签、D7 guidance reject reason 和 actual scale 分组；剩余项是更多批次的数据沉淀，以及 main/D4/D5/D7 在真实 episode 中持续写出可对齐的 D4/D5/D7/Blocks 文件。D6 按实际 `drone_count/resource_count/target_count/camera_count` 归一化，`2v2/5v5` 只作为 baseline 场景名。

非本轮范围保持 P2/P3 或禁止项：Stone Soup metrics、OSPA/GOSPA、TrackEval、HOTA、AirSim 原生 recording parser、SCRIMMAGE bridge、live replay/API。py-motmetrics IDF1/MOTA/MOTP 已隔离实现，但不替代当前 D6 本地离线指标主线。

## 已实现

| 能力 | 当前状态 | 代码/测试证据 |
|---|---|---|
| `EpisodeMetrics` | 已实现。包含 episode metadata、实际规模字段、八类指标和 `metadata`。 | `research_modules/d6_evaluation_metrics/d6_evaluation_metrics/metrics.py`; `tests/test_metrics.py` |
| 规模归一化 | 已实现。优先使用 `truth_summary` 或 Blocks replay 的实际 `drone_count/resource_count/target_count/camera_count`，缺失时从记录推断；报告按 `metric_scope/seed/scenario_group` 和实际规模分组。 | `metrics.py`; `reporting.py`; `tests/test_metrics.py`; `tests/test_reporting_and_simulation.py`; `tests/test_blocks_replay.py` |
| 基础记录模型 | 已实现 `TrackRecord`、`AssignmentRecord`、`EventRecord`，并扩展 `LinkRecord`、`TerminalRecord`。 | `metrics.py`; `jsonl.py`; `tests/test_airsim_dry_run_jsonl.py` |
| 探测指标 | 已实现 `detection_probability`、`false_alarm_rate`、`missed_detection_rate`。 | `metrics.py`; `tests/test_metrics.py`; `tests/test_blocks_replay.py` |
| 跟踪指标 | 已实现 `track_rmse`、`track_continuity`、`id_switch_count`。`id_switch_count` 对同一 `truth_id` 的 `global_track_id` 变化显式计数。 | `metrics.py`; `tests/test_metrics.py` |
| 分配指标 | 已实现 `duplicate_assignment_count`、`unassigned_high_threat_count`，并按 active + 有效授权状态过滤。 | `metrics.py`; `tests/test_metrics.py` |
| 基础降级指标 | 已实现 `failover_time`、`consensus_rounds`、`degraded_completion_rate`。 | `metrics.py`; `tests/test_metrics.py` |
| D4 active/passive 降级基线 | 已实现 `active_degradation_count`、`active_degradation_precision`、`active_degradation_label_count`、`unnecessary_active_degradation_count` 等；label count 为 0 时 precision 为 unavailable/null。 | `metrics.py`; `main_bus.py`; `d4_replay.py`; `tests/test_d4_replay.py`; `tests/test_metrics.py`; `tests/test_main_bus_metrics.py` |
| 末端指标 | 已实现 `terminal_association_accuracy`、`terminal_id_switch_count`、`ambiguous_fov_event_count`、`friend_overlap_hold_count`、`time_to_terminal_lock`、`terminal_lock_count`。 | `metrics.py`; `tests/test_metrics.py` |
| 多视角/无 PNG 评估 | 已实现基础能力。Blocks replay 可用 bbox、相机内外参、timestamp、object label 和 truth label 生成 terminal、video/bbox link、多视角 consensus/conflict。PNG 不作为指标必需输入。 | `blocks_replay.py`; `tests/test_blocks_replay.py` |
| 二级视角/侦察云台指标 | 已实现。统计 `secondary_network_joint_full_view_frame_rate`、`secondary_network_mean_coverage_ratio`、`secondary_single_camera_full_view_frame_rate`、`cross_view_association_count`、`secondary_detect_available_but_not_registered_count`、`cue_pointing_error_*`、`gimbal_pointing_error_*`，并在 metadata 中保留 node-type 对比。 | `metrics.py`; `reporting.py`; `tests/test_metrics.py`; `tests/test_reporting_and_simulation.py` |
| 通信链路指标 | 已实现 latency、drop、out-of-order、stale、video metadata delivery、bbox delivery、consensus latency。 | `metrics.py`; `tests/test_metrics.py`; `tests/test_blocks_replay.py` |
| D7 intercept replay | 已实现。读取 `control_commands.csv` 和 `intercept_summary.json`，计算 success、collision/range intercept、min range、time to intercept、gate reject 等。 | `intercept_replay.py`; `tests/test_intercept_replay.py` |
| D7 guidance time-series | 已实现。读取 `guidance_records.csv`、`guidance_summaries.json`，保留 mode switch、terminal contract reject、D4/D5 state、plan/version、guidance law。 | `intercept_replay.py`; `metrics.py`; `tests/test_intercept_replay.py` |
| D7 terminal gate/visual PNG switch | 已实现 `camera_quality_gate_pass_rate`、`los_quality_gate_pass_rate`、`maneuver_margin_gate_pass_rate`、`terminal_switch_allowed_rate`、`visual_png_switch_count`、`terminal_takeover_rate`、`terminal_switch_reject_count`。 | `metrics.py`; `tests/test_metrics.py`; `tests/test_intercept_replay.py` |
| 安全指标 | 已实现 `constraint_violation_count`、`human_override_count`。 | `metrics.py`; `tests/test_metrics.py` |
| 批量统计/报告图表 | 已实现 episode CSV、summary CSV、Markdown、按指标族 PNG 图和 selected distribution 图；summary 包含 count/mean/std/stderr/95% CI/median/p05/p95。 | `reporting.py`; `scripts/run_batch_example.py`; `tests/test_reporting_and_simulation.py` |
| P0-A 标准化评估映射最小版 | 已实现。`cuas-standard-map-v1` 覆盖 mission/root cause、detection、tracking、assignment、degradation、terminal、communication、guidance/intercept、safety、performance、reproducibility/evidence；`MetricsCollector.compute_episode()` 写入 mapping metadata，`ReportGenerator.write_standard_mapping_csv()` 输出 `standard_metric_mapping.csv`，Markdown 在 `EVAL Tracking` 后输出 `Standard C-UAS Mapping` 表。 | `standard_mapping.py`; `metrics.py`; `reporting.py`; `main_bus.py`; `tests/test_metrics.py`; `tests/test_reporting_and_simulation.py` |
| JSONL 标准化接口 | 已实现 `truth_summary/track/assignment/event/link/terminal`，未知 record type 报错。 | `jsonl.py`; `tests/test_airsim_dry_run_jsonl.py` |
| main bus metrics JSON | 已实现。读取 `main_episode_bus_metrics.json` 与 `main_episode_bus_contract_metrics.json`，还原 execution/contract `EpisodeMetrics`，保留 seed/scenario/实际规模和 metadata 分布。 | `main_bus.py`; `tests/test_main_bus_metrics.py` |
| 二级节点对比与 reject reason 报告输出 | 已实现。episode CSV 保留 metadata JSON；Markdown 在有数据时输出 fixed downlook secondary vs mobile recon gimbal 对比表，以及 terminal switch/contract reject reason 分布。 | `reporting.py`; `tests/test_reporting_and_simulation.py` |
| AirSim 多 seed calibration 汇总 | 已实现。旧 records/逐 seed summary 不变；新增 `airsim_calibration_cross_seed_aggregate.csv`、`airsim_calibration_paired_comparison.csv`、`airsim_calibration_aggregate.json`、`airsim_calibration_aggregate_report.md`，包含严格配对、missing seed、effect size 和 bootstrap CI。 | `airsim_calibration.py`; `tests/test_airsim_calibration.py` |
| 2v2/N-v-N 拦截多 seed 汇总 | 已实现。records/summary/cross-seed 覆盖 success、collision/range/abort、min range、intercept time、visual PNG、terminal switch/takeover 和 gate reject；outcome 有 sum/opportunity/rate。availability gate 排除 read-only 默认零；2026-07-12 2v2 baseline/candidate 分别聚合为 `19/20`、`20/20`。 | `airsim_calibration.py`; `tests/test_airsim_calibration.py`; 2026-07-12 D6 对照包 |
| P1 PNG delivery 被动指标与对照报告 | 已实现。滤波/TTC/soft-coast/锁定/视觉模式/命令跳变指标保持 availability；26 个 episode 按 profile/scope/scenario/actual N/M 分为 4 组，2v2/M5N2 与 pair/target/coalition 不混合。 | `metrics.py`; `intercept_replay.py`; `reporting.py`; `tests/test_terminal_delivery_evaluation.py`; 2026-07-12 D6 对照包 |
| P1 detect-to-registration 与 coverage 校准漏斗 | 已实现。records/summary/Markdown 显式输出 `secondary_detect_count`、`secondary_visible_target_union_ratio`、`secondary_network_joint_full_view_frame_rate`、`projection_valid_rate`、`geometry_gate_pass_rate`、`registered_candidate_count`、`stable_cross_view_registration_count`、`not_registered_count`，固定保留八类 reject/outcome reason，并新增 50m vs 200m 覆盖对比、coverage funnel 与 baseline/enhanced 表格。 | `airsim_calibration.py`; `tests/test_airsim_calibration.py` |

## 部分实现

| 能力 | 当前状态 | 为什么只是部分实现 | 缺少条件 | 优先级 |
|---|---|---|---|---|
| D7 real execution metrics 回灌到正式 main bus metrics | D6 消费主线已完成。2026-07-10 历史 2v2 基线的正式 execution 为 `2/2/2/2`、成功 2、visual PNG switch 3；contract 独立保留。 | 同 episode 的 Blocks legacy integrated snapshot 仍过时；D6 已忽略并用测试固定 main-bus 优先级，不负责回写运行时。 | main 修复 Blocks/sequence summary 的旧快照一致性；多 seed、5v5/N-v-N 持续采用同一双口径。 | D6 P1 已完成，main P1 待对齐 |
| 真实 episode 日志完整性 | D6 已有 Blocks、D4 loader、D5/terminal/multi-view 指标和 D7 guidance/intercept loader；可以消费写盘文件。历史 mobile recon stress 与 registration calibration v2 提供了旧链路证据；2026-07-11 P1 合同验证已提供 CV/commit/fail-closed 当前证据。 | D6 loader 是离线入口，不负责 main runtime 写盘、目录扫描、episode clock 对齐或多 loader 合并调度。 | 每个 episode 目录稳定写出 Blocks/D4/D5/D7/D6 日志；汇总脚本合并到一个 `MetricsCollector`；同一 episode clock 和实际规模字段。 | P1 持续回归 |
| D4 review/window 真实写盘 | D6 已实现 `active_degradation_precision` 与 `unnecessary_active_degradation_count` 的最小可测口径，D4 CSV loader 可消费 review label、trigger/decision timestamp、selected coordinator、coverage cell 和 pre/post window 字段。 | 真实 AirSim episode 是否每次写出 review/window 字段仍取决于 main/D4；缺 label 的 active degradation 不进入 precision 分母。 | main/D4 持续写盘；固定 pre/post 窗口；后续扩展 decision latency、ID switch delta、assignment conflict delta。 | P1 |
| 多 seed execution/contract 报告口径 | D6 已按 `metric_scope/seed/scenario_group/drone_count/resource_count/target_count/camera_count` 输出通用 summary，并新增 AirSim calibration 分组到 `metric_scope/seed/scenario/comparison_role/secondary_height/FOV/secondary_count/detection_backend`。 | 仍需要真实批量 episode 持续提供 execution metrics 与 contract metrics；D6 不从 `2v2/5v5` 场景名推断规模。 | 多 seed、5v5/N-v-N 和非默认 episode 的正式 metrics 与 raw contract metrics 成对落盘。 | P1 持续回归 |
| 移动侦察云台 AirSim 报告字段 | D6 已有被动指标、Markdown 对比表和 AirSim calibration 自动汇总，可消费 `mobile_recon_gimbal` metadata；2026-07-08 stress 与 registration calibration v2 历史基线验证了 gimbal、coverage、funnel、bbox、projection/gate/stable registration/not-registered/D7 reject 字段可进入 bundle；2026-07-09 已新增 50m/200m、coverage funnel、baseline/enhanced 和 trend/evidence 字段。 | v2 只是 single seed、3 case；该历史结果只能说明报告链路可用，长期趋势和阈值校准还缺更多真实 AirSim 多 seed/N-v-N 数据与 review labels。 | 用新增汇总报告持续比较 `mobile_recon_gimbal` / `fixed_downlook_secondary` 的 coverage、funnel、projection/gate、stable registration、not-registered、D7 reject、bbox、cue/gimbal pointing 指标。 | P1 持续回归 |
| 多视角末端几何质量 | 已能统计 consensus/conflict/duplicate lock 和 bbox delivery。 | 尚未计算跨视角重投影误差、外参质量评分或时延补偿。 | 稳定相机标定、跨节点时钟、D5 输出几何误差字段和候选集。 | P2 |
| 批量统计 CI | 通用 summary 已输出正态近似 95% CI；AirSim baseline/enhanced 已新增 paired percentile bootstrap 95% CI。 | 非配对的其他长尾/偏态指标仍未统一使用 bootstrap。 | 足够多真实 episode；按指标选择方法并标注。 | P2 |
| TrackEval/OSPA 对照 | py-motmetrics 已在 2 帧离线 smoke fixture 上通过冻结 schema 输出 IDF1/MOTA/MOTP；TrackEval、HOTA 与 OSPA/GOSPA 未实现。 | 当前只证明 adapter 可运行，尚未导出或标定真实 TrackEval/OSPA 所需标准 frame-level/set benchmark 格式。 | 真实 D2/D5 帧级 truth/detection/track 匹配表、IoU/距离门限、遮挡/重现规则。 | P2 |

## P2 adapter 与未实现项

| 能力 | 当前状态 | 未实现原因 | 缺少条件 | 优先级 |
|---|---|---|---|---|
| Stone Soup metrics adapter | 未实现。没有 `stonesoup` import、对象转换器或 metric generator 调用。 | 保持默认测试轻依赖；D1/D2 输出尚未固定到 Stone Soup `Track/Detection/GroundTruthPath`。 | Stone Soup 版本锁定；D1/D2 adapter；坐标/时间/门限合同；CI fixture。 | P2 |
| OSPA/GOSPA 默认输出 | 未实现。文档保留公式，`EpisodeMetrics.metric_names()` 不含这些字段。 | 需要帧级 truth/estimate set 和 cutoff/order。 | 集合序列、birth/death/遮挡规则、门限配置。 | P2 |
| py-motmetrics | 已实现 `msm-offline-mot-v1` loader、accumulator adapter、IDF1/MOTA/MOTP 和 available/unavailable 测试；真实 backend 仅验证 2 帧离线 smoke，HOTA unavailable。 | 默认依赖保持轻量，adapter 只在隔离 venv 运行；“已完成”仅指 adapter/schema，不指真实 benchmark 标定。 | 真实 D2/D5 冻结 replay、明确距离/IoU 门限和遮挡/重现规则。 | P2 adapter 已完成，benchmark 未完成 |
| TrackEval / HOTA | TrackEval 未实现，HOTA unavailable。 | py-motmetrics 1.4.0 不支持 HOTA，且尚无 MOTChallenge/TrackEval 导出。 | 帧级匹配表、遮挡/重现规则、版本与回归容差。 | P2 |
| AirSim 原生 recording parser | 未实现。 | 当前 main Blocks JSONL 已更直接；原生 recording 字段、坐标和相机版本差异大。 | 原生 recording 样例；字段版本；NED/相机/episode clock 映射；测试。 | P2 |
| Live AirSim replay/API | 未实现，且不应作为 D6 默认目标。 | D6 的边界是 offline-only；live replay/control 属于 main runtime。 | 如需 replay，应由 main 导出 D6 可读日志。 | 禁止在线控制 |
| SCRIMMAGE metrics bridge | 未实现。没有 SCRIMMAGE import、日志解析器或统计桥接。 | 当前仿真主线是 AirSim Blocks 和合成数据；仓库没有 SCRIMMAGE 输出样例或 message schema。 | SCRIMMAGE episode 输出；agent/resource/target ID 映射；通信字段；episode clock；批量目录。 | P3 |
| D6 对实时控制/在线决策的参与 | 未实现，且不应实现。 | D6 只消费日志，不能回写控制链路。 | 不适用。 | 禁止项 |

## 未实现原因汇总

1. 当前阶段优先保持 D6 轻量、离线、可复现，默认测试不依赖重型外部库、AirSim 服务、GPU 或网络。
2. py-motmetrics 已基于 2 帧离线 smoke 和冻结 schema 输出 IDF1/MOTA/MOTP，只证明 adapter 可运行；真实 benchmark、TrackEval、OSPA/GOSPA 和 HOTA 仍需要更完整的帧级 truth-track/detection 匹配表、遮挡/重现规则和统一门限。
3. 主动降级“是否必要”不能由 D6 只看事件名自证；当前 D6 只消费 D4/main 写入的 review label、明确必要性布尔值、post-window outcome 或 pre/post risk 后验字段。
4. AirSim 原生 recording 和 SCRIMMAGE 都需要样例、schema、ID 映射和时钟/坐标对齐规则。
5. D6 不参与控制是模块边界，所有指标只用于离线报告和回归分析。

## P0 保持回归

1. 标准化评估映射最小版已实现，后续保持 `cuas-standard-map-v1`、`scenario_version`、`standard_mapping_version`、`standard_metric_family_summary`、`standard_metric_mapping.csv` 和 Markdown `Standard C-UAS Mapping` 表回归；D6 仍只消费日志，不参与控制，不要求完整认证或外部平台接入。

## P1 最终开放项

1. **长期 multi-seed 趋势**：按冻结 scenario/version/profile/actual scale 持续生成跨提交趋势、门限稳定性和 bootstrap 置信区间；单批次不得外推为长期结论。
2. **真实逐时刻 schema**：由 producer 写出有序 history/ticks，优先补 D3 plan history/churn，并保留 episode clock、version/epoch、source provenance 和 availability。缺少该证据时 churn 保持 unavailable。
3. **失败原因治理**：统一跨 producer、跨批次的 reason taxonomy 和 schema version，明确 unknown、unavailable、not_applicable 与显式零，避免重复计数和原因漂移。

以上三项是当前 D6 P1 的唯一开放主线。下列编号保留为历史专项规划，不作为 2026-07-13 当前待办。

1. 使用同一 z=-30 m、35 s 高净空几何、相同窗口和 seed 完成 M5N2 baseline/candidate paired 验收；分别报告 target、active-primary pair、coalition completion，不跨层回填。
2. 独立运行 `png_ttc` 多 seed，汇总 area jump、bbox clipping、not expanding、TTC out-of-range；固定锁后 1-5 帧 dropout，3-5 帧必须按 0.25 s 上限 fail-closed。
3. trend coast 只有在错误绑定为 0、命令跳变不恶化且物理成功不下降时才可进入默认 profile；现阶段保持 candidate-only。
4. M 对 N 合同证据已达到当前验收：T001 8/10、secondary/distributed 3/3 与 missing-ACK 2/3 均已核对；2 个未双锁 seed 只作为鲁棒性回归。所有新批次继续分离 contract/control/switch/physical 四层指标。
5. `ScenarioLibrary` 已实现；下一步由 main/CI 使用标准化 scenario group/version、tags、difficulty、expected failure modes、actual scale、seed matrix 和 evidence path 调度真实批次，再输出跨提交趋势和阈值回归摘要。
6. CV 5v5 D1-D3 联合聚合：按同一 episode clock 合并 D1 detection/fusion/latency/covariance、D2 association/continuity/ID switch、D3 assignment/version/hysteresis，形成感知到分配的漏斗与失败归因。前置条件是 main/D1-D3 提供稳定 schema 和证据路径。
7. YOLO/MOT 核心 recall/continuity/cross-view/latency/CPU/GPU budget 已实现；下一步消费 D5 的 model version、输入分辨率、目标像素尺度、throughput、内存、drop/fallback 字段，形成完整 accuracy-latency-budget 报告；D6 不加载权重或执行检测。
8. COURAGEOUS/MDPI/OCEF 完整标准化报告：补测试阶段、复现纪律、evidence index、场景覆盖矩阵、限制条件和外部审计说明。
9. 真实成对多 seed/N-v-N 数据：继续验证已实现的 paired effect size/bootstrap CI；无配对、单 pair、read-only unavailable 或无 review label 时不得输出推断结论。
10. D4/D5 长期趋势：持续消费 coverage/funnel/gimbal、projection/gate/registration 和真实 active-degradation review/window 标签。
11. execution/contract/evidence availability 仅保持回归，不再新增重复或同义拦截字段。

## P2 下一步

1. `msm-offline-mot-v1` 已作为 py-motmetrics 最小帧级 schema；当前证据仅为 2 帧离线 smoke，后续用真实 D2/D5 replay 固定距离语义、门限、遮挡和重现规则。
2. py-motmetrics adapter/schema 已完成，真实 benchmark 未完成；TrackEval/HOTA 继续作为可选 benchmark，禁止伪造 HOTA 或替换默认在线关联路径。
3. 在 D1/D2 对象映射和版本锁定后接入 Stone Soup metrics 与 OSPA/GOSPA。
4. 为长尾指标增加 bootstrap 或非参数 CI。
5. 只有当 AirSim 多机规模或通信建模不足以回答实验问题时，再把 SCRIMMAGE bridge 作为 P3 可选项推进。
6. 仅在 Blocks JSONL 不足时增加 AirSim 原生 recording parser。

## 验收建议

```bash
pytest -q research_modules/d6_evaluation_metrics/tests
git diff --check -- research_modules/d6_evaluation_metrics subagent_reviews/D6_*
```

## 2026-07-12 本轮 P1 GAP 更新

### 已闭合的 D6-owned 缺口

- 已新增统一 P1 系统证据聚合器，消费 D2 六难度 profile、D3 membership/plan/coalition churn、D4 episode communication、D5 native ByteTrack/BoT-SORT admission 和 D7 per-primary 结果。
- 已提供 CSV、JSON、中文 Markdown、PNG 四类可复用输出及 CLI，不依赖场景名推断 N/M。
- D5 指标已覆盖 native active rate、fallback、precision/recall、continuity、local IDSW、P95 latency、admitted/reasons。
- D4 指标已覆盖 failover、ACK/missing/rejected ACK、lease invalid、epoch/version/owner churn、execution allowed 和 fail-closed。
- D7 已强制区分 contract allowed、control allowed、mode switched、physical intercept；不存在跨层补值。
- availability 和 truth 隔离已进入 schema：缺字段为 unavailable，显式在线 truth 使用使汇总 truth policy 失败。

### 仍开放的 P1 条件缺口

- main 尚需把真实 native MOT screening/confirmation、D2 六 profile、D3 plan history、D4 tick replay 和 D7 per-primary execution summary 按 episode/seed 写盘并调用该聚合器。
- D5 admission 是否达到阈值、D2 profile 是否有区分度、D3 churn 是否下降、D4 failover 是否通过以及 D7 physical intercept 是否成立，必须由真实多 seed 证据决定；本轮只闭合 D6 消费和报告接口。
- D3/D4 输入若只给最终 snapshot，D6 无法恢复中间 churn；需要 producer 提供有序 history/ticks。
- 真实批次必须显式提供 actual resource/target count、seed、schema/version 和 evidence path；缺失时报告保持 unavailable，不从 `2v2/5v5/M5N2` 名称推断。

### P2 状态不变

本轮没有把 TrackEval/HOTA、Stone Soup、OSPA/GOSPA 或 AirSim 原生 recording parser 引入默认路径；这些项目继续保持既有 P2 状态。

## 2026-07-12 Native MOT 真实证据更新

- D6-owned 专项报告缺口已闭合：三类真实 AirSim 输入已生成中文 CSV、JSON、Markdown 和指标 PNG，未保存 AirSim 截图。
- availability/truth 隔离通过：在线 truth 使用、truth identity 在线使用和 `global_track_id` 改写均为 0；无检测档位的 continuity/precision/recall 保持 unavailable。
- 仍开放的 P1 是上游能力缺口，不是 D6 聚合缺口：ByteTrack 与 BoT-SORT 在 102 帧 20 m confirmation 均因 precision/recall 不足被拒绝；30/50 m 无接受检测。
- 42 帧 range precheck 与 102 帧 confirmation 明确作为不同证据等级，不合并样本、不互相替代。
- 后续需要 main/D5 提供修正后的 truth 几何/时间标定和真实多 seed confirmation，D6 再按相同 schema 复报。

## 2026-07-13 Replay/Execution 合并 GAP 状态

- **D6-owned P1 合并接口已闭合**：新增 `merge_replay_with_execution_metrics()`，main 可直接输入 integrated replay 与 main episode bus execution 两份 mapping。
- **执行口径优先级已闭合**：cross-view、终端关联、在线 truth 审计、合同/控制/模式切换和物理执行字段，在 execution 有明确值时覆盖 replay；真实样本 `55 vs 0` 已验证选择 55。
- **provenance/availability 已闭合**：逐指标保留 replay/execution 原值、source path、availability 和 selected source；缺失值不补 `0`，显式 `0` 可作为有效证据。
- **帧数分层已闭合**：`persisted_frame_count` 与 `warmup_inclusive_frame_count` 独立写出 availability/source，不互相推导。
- **仍开放的是 main 集成项**：main 需在 AirSim episode 完成后实际调用该纯函数并把 bundle 写入规范输出；D6 不修改 `airsim_runtime`，因此历史输出不会自动回填。

测试证据：`tests/test_execution_metrics_merge.py` 覆盖 cross-view `55 vs 0`、execution 缺失和 `11 persisted vs 12 warmup-inclusive`。

## 2026-07-20 三维规模化 D1/D2 离线评估 GAP

### 已闭合的 D6-owned 项

1. D1 `OfflineConsistencyResult` 和 `aggregation_records()` 已有公共 adapter。总体和
   scenario/sensor/range 指标保留 RMSE、NEES、NIS、sample count、availability、不可用
   原因、result digest 和三类 input digest。D1 当前规范 `d2_lineage_mapping` 已接入；旧
   `canonical_mapping` 仅兼容读取，新旧冲突和 truth metrics 可用但摘要缺失均 fail-closed。
2. D2 `Scalable3DIdentityEvaluation` 已有公共 adapter。`id_switch_count`、continuity、
   duplicate、confusion 和 coverage 显式保留；缺身份评估时 IDSW 为 `None/unavailable`，
   不能补零；零帧、无 truth-frame、来源摘要不完整或隔离未验证时 truth details 不聚合。
3. D6 不解析 D1/D2 私有 tracker 状态，不重建 `global_track_id -> truth`。D2 原始来源和
   在线真值隔离未完整验证时 fail-closed。
4. episode/batch 接口和逐 seed CSV、D1 sensor-range CSV、aggregate JSON、中文 Markdown
   已实现，actual scale 支持 5/20/50/100/200 及其他正整数规模。
5. 2026-07-20 专项 `14 passed`，D6 全量 `334 passed`；一条既有 Matplotlib `Axes3D`
   环境 warning 不影响本轮无图报告。

### 仍开放的 P1

1. 当前工作树 main-owned scalable 3D reporting 已写出 D1/D2 制品并调用 D6 episode/batch
   接口；稳定文件名、manifest/hash 关系和最终统一报告仍由 main 冻结。
2. D1/D2 尚未提供覆盖 5/20/50/100/200、至少 20 个未见 seed 的正式制品，因此 RMSE、
   NEES、NIS、IDSW、continuity 和 duplicate 没有可验收的性能统计。
3. 现有 `Scalable3DOfflineReportGenerator` 与新公共制品报告尚未由 main 合并为最终一份
   200 对 200报告。合并时必须保留 source hash 和 availability，不能回到旧在线记录猜测。

当前无新增 P0。P2 外部 evaluator 状态不变；本轮没有引入 Stone Soup、TrackEval、HOTA、
OSPA/GOSPA 或 AirSim 原生 recording parser。
