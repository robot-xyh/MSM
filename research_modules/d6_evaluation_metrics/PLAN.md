# D6 Evaluation Metrics Plan

## 2026-07-20 正式离线 outcome/reward 标签状态

- [x] 实现只读 `audit_learning_label_readiness()` 和 CLI，校验正式生成计划、finalized checkpoint、
  100 个训练 seed、20 个保留评估 seed、900 episode index 及 D4/D5 全量文件哈希。
- [x] 实现 detached sidecar 写入和 bundle 自审计。输出目录不得位于正式学习数据源内部；manifest、
  SHA-256、规范 JSON、确定性 gzip 和原子目录发布均已接线。
- [x] 固定 outcome、reward、counterfactual、causal-label 四层 availability 合同。不可用值使用
  `null+reason+provenance`，不以 `0` 表示缺失。
- [x] D4 只从时间窗内相邻 frame 生成区域纯观测转移。正式数据没有推荐采用/执行摘要，故奖励和 PPO
  fail closed；规则 recommendation 可作为行为克隆输入，但当前动作全为零 quota、无 hold/replan/
  transfer，不能据此晋升策略。
- [x] D5 只从同相机时间窗内相邻 snapshot/projection 生成纯观测转移。奖励硬门要求 runtime ACK；
  接受 ACK 还要有版本一致、时间在 ACK 之后的 camera feedback。相邻姿态变化不作为动作应用证据。
- [x] 固定 seed `1000-1019` 为保留评估集，训练标签发现重叠时立即失败。在线 truth-like 字段、对象键
  篡改、模块内 split/identity 不一致和 source hash 变化均 fail closed；跨 D4/D5 split 不一致则保留
  单模块 sidecar，并明确阻断联合训练。
- [x] 2026-07-20 正式 900 episode 审计完成：D4 outcome `898/1798`、reward `0/1798`；D5 outcome
  `1,063,214/1,153,242`、reward `0/1,153,242`、runtime ACK `0`。D4/D5 行为克隆合同可用，PPO、
  counterfactual 和 causal training 均不可用。D4/D5 split 有 423 个 episode 不一致，联合训练不可用。
- [x] 17 项专项测试覆盖接受/拒绝/缺失 ACK、无后继、D4 无归因、schema/identity/split、跨模块 split、保留 seed、
  unavailable 空值、文件篡改、原子写和重复运行确定性。
- [x] 验证日期 2026-07-21：专项 `17 passed`，D6 全量 `351 passed`；审计输出中的证据日期保持
  2026-07-20，未启动 AirSim。

### Producer 准入条件

- [ ] D4/main 在 frame 关闭前持久化版本化 recommendation consumption/adoption、applied digest、
  plan/epoch/lease 绑定和 post-action 状态；同时增加非零 quota、hold、replan、transfer 覆盖。未补齐前
  D4 PPO 保持 unavailable。
- [ ] main 调整 active-vision 生成顺序，使 D5 样本在 episode 最终化前连接
  `runtime.camera_command_ack`，并将运行态最近接受的命令版本写入相机反馈。现有正式数据不得原地
  回填或根据姿态反推 ACK。
- [ ] 若训练奖励包含任务完成，另提供明确的终端任务结果和归因时间窗。PPO 还需 on-policy log
  probability/value；反事实或因果训练需同初态配对重放或受控干预。
- [ ] main/D4/D5 冻结共享的 seed-atomic split registry 后，重新导出或生成只读规范 split sidecar；完成
  前 D4 与 D5 只能分别训练和评估，不能混成联合训练集。

## 2026-07-20 scalable 3D 实验矩阵审计状态

- [x] 只从 `scenario_config.metadata` 读取矩阵 schema、variant、comparison key 和 full-system flag；
  历史 episode 的矩阵字段保持 unavailable，不从目录名补值。
- [x] 独立核对 R0/G1/A1/A2/A3/C1/F1 与 learning runtime diagnostics，bundle 未加载、effective mode
  非 assist、实际采用缺失或规则回退时 `variant_execution_valid=false`。
- [x] 固定每个 comparison identity 的 R0/G1/A1/A2/A3/C1 分母；仅三个完整体系场景增加 F1，缺 cell
  和重复 cell 均显式保留。
- [x] 按 variant 输出 episode/seed、有限性、在线真值、硬约束、ID switch、分配、跨视角、主动视觉、
  五米事件和阶段耗时的 availability-aware 描述统计。
- [x] 对完整 R0 配对输出 variant-minus-R0 delta；至少两个比较键才生成 bootstrap CI。clean/formal 与
  dirty development 分开，所有 paired delta 保持非因果口径。
- [x] producer 风格矩阵专项 `40 passed`，D6 全量 `320 passed`；真实 R0/nominal/2v2/seed101 dirty
  smoke 复读为执行有效、cell 完整性 1/6、正式矩阵资格 false；临时 5v5 producer smoke 的 D4 消费、
  D3 hint applied 和 control adoption 均为 1。
- [ ] main 尚未运行 clean、完整 R0/G1/A1/A2/A3/C1/F1 矩阵。没有正式算法优劣或准入结论。
- [x] D4 advice 与 main 消费证据分层审计；缺消费、旧 schema、未知或篡改 advice、summary 冲突均
  fail closed。有效消费且 D3 明确应用 hint 时，A2 可形成实际采用证据。
- [ ] 若要发现整个 comparison key 完全缺失，main 需把 matrix manifest 作为显式 D6 输入；D6 不从
  目录结构重建未出现的 key。

## 2026-07-20 scalable 3D schema registry 窄修复状态

- [x] 将两套 D6 fixture 的 online observation schema 对齐真实 producer：
  `scalable3d-observation-v1`。
- [x] 增加 D6-owned `d6-scalable3d-schema-registry-v1`，核对 world、bus、scenario、online observation、
  offline truth 和 scenario config schema，不导入 main runtime。
- [x] 保留原始 schema 字段；另输出逐项 expected/match/status/reason、整体 match 和 registry version。
- [x] 将整体 current-schema match 纳入 formal acceptance；旧、未知、篡改或缺失 schema fail closed，
  但仍可作为 descriptive historical row 展示。
- [x] 增加当前匹配、五项 manifest 不匹配和缺字段测试；专项 `32 passed`、D6 全量 `304 passed`。
- [x] 复读 6v6/seed37 当前 producer smoke，schema match=true；formal 仍只因
  `repository_dirty=true` 被拒绝。
- [ ] 后续新增 producer schema 时，必须先更新 registry 版本和迁移说明；未知版本不得自动准入。

## 2026-07-20 scalable 3D 主动视觉证据闭环状态

- [x] 将 D5 active-vision publication 与 main camera-command ACK 作为两层独立写盘证据消费；D6 不
  导入 scalable runtime，不参与相机控制。
- [x] 区分 rule command、有效 shadow suggestion、assist adopted、ACK applied/rejected 和 physical
  outcome；shadow 实际发布的规则动作不误计为 assist，assist adopted 不自动成为 applied。
- [x] 以 camera/resource、issued timestamp、plan/coalition/communication version、intent 和 mode
  关联命令与 ACK，统计完成率、未 ACK、意外 ACK、P50/P95/max 延迟和拒绝原因。
- [x] 拒绝原因拆分为过期/未来命令、过时计划/联盟/通信版本、相机或资源不可用和其他原因；summary
  四项计数及 reason distribution 与日志交叉校验。
- [x] `target_global_track_id` 只与此前 D2 中心航迹快照核对，并检查 ACK 原样回传；缺 D2 快照为
  evidence incomplete，未知引用或 ACK 改写使正式证据 fail closed。
- [x] 单独统计主动视觉在线 truth-like 字段违规；缺 active-vision/ACK 日志时指标为
  null/unavailable，不用 summary 的零替代缺失日志。
- [x] 物理归因保持 null/unavailable。assist applied 与同 episode 五米接近不能替代同 seed 配对规则
  控制组；当前 producer 尚无正式 paired-experiment 合同。
- [x] 按实际 target/resource/recon/camera 数量和不同 seed 聚合。2026-07-20 主动视觉专项 8 项、合并
  scalable 专项 `25 passed`、D6 全量 `297 passed`，仅既有 Matplotlib warning；未运行 AirSim。
- [x] 用当前 main runtime 运行 6v6/recon1/camera7、seed 37、2.2 s 临时 smoke；133 issued=133 matched
  ACK=133 applied，reject/target-reference violation/truth violation 均为 0，summary match=true。该输入
  `repository_dirty=true` 且只有单 seed，仅证明 v3 consumer 与当前未提交合同兼容，不计正式 evidence。
- [ ] main 在 clean worktree 生成至少 20 个未见 seed 的 rule/shadow/assist episode，确认命令、ACK、
  summary 和拒绝原因分布在真实持久化产物中闭合。
- [ ] main/D5 若正式开展效果归因，冻结同 seed 配对的规则控制组/assist 处理组、模型 bundle/hash、
  场景配置和实际 adopted+applied 证据；D6 再增加跨 episode 配对效应与置信区间，当前不得先写提升值。

## 2026-07-20 scalable 3D 学习运行时离线评估状态

- [x] 保持纯文件、只读、无控制边界；交叉消费 config/summary 的
  `scalable3d-learning-runtime-v1`，不读取在线真值，不导入 scalable runtime。
- [x] D3/D4/D5 分别发布 requested/effective mode、bundle requested/loaded、fallback、runtime
  version、学习模型 fingerprint/version availability；缺字段或 bundle 未加载为 null/unavailable，
  不用规则 version 冒充模型 version。
- [x] 只接受 topic `modules.d4.region_resource_advice` 的
  `d4-region-resource-advisory-runtime-v1`；逐 episode 统计发布/合法/非法、mode 分布、shadow 输出、
  assist eligible、fallback/reason、latency P50/P95、quota 守恒、projection rejection、正式裁决
  unchanged/mutation 和 stale/missing version evidence。
- [x] 对 recommendation schema、scenario/version/seed、authority digest、plan/version/epoch/lease、
  action/transfer/projection、digest flag 做 fail-closed 审计；非法或旧 schema 不缩小分母。
- [x] 报告五层证据：bundle load、shadow output、assist gate、control adoption、physical outcome。
  advice 不改变正式 D4 裁决，`assist_eligible` 不晋升为控制生效；control adoption 只来自通过完整合同
  和 summary 一致性审计的 main 消费记录及 `d3_hint_applied=true`。
- [x] 聚合继续按实际 target/resource/recon/camera 和不同 seed；单 seed descriptive-only。正式证据
  继续要求 `repository_dirty=false`，并校验 config hash、D4 policy version、finite/truth isolation。
- [x] 2026-07-20 确定性 fixture 覆盖 disabled、D3/D4/D5 missing-bundle fallback、assist-to-shadow、
  assist gate、守恒/非守恒、projection rejection、mutation/unchanged、digest 篡改、旧 schema、缺
  plan version、缺 advice 和 seeds 1/2 bootstrap；scalable 专项 `17 passed`、D6 全量 `289 passed`，
  仅既有 Matplotlib `Axes3D` warning。
- [ ] main 用 `repository_dirty=false` 的正式多规模、多 seed 学习 bundle 运行 CLI，冻结 bundle、
  shadow、assist、control 和 physical 五层跨提交趋势；fixture 或 dirty smoke 不作为模型验收。
- [x] producer 已发布独立 `d4-region-resource-consumption-v1`，携带完整建议合同、当前 snapshot、时间、
  consumable/rejection、bridge reason 和 D3 hint applied；D6 不从 advice 或模式字段推断采用。
- [ ] producer 增加 evaluator-only `global_track_id -> truth_target_id` 显式映射；D2 IDSW 继续只接受
  producer 明确 available 值，二者均不得从名称、终态或邻近事件补算。

## 2026-07-15 legacy provenance 与三档 comparator 完成状态

- [x] 对路径输入且 summary/cases/rows 全无 ClockSpeed 的 legacy suite，按 20 个注册 `case_id` 定位
  sibling generated settings；20/20 文件、显式键、有限正数和全量一致均为强制门。
- [x] 保持 mapping 输入无文件系统发现、目录名不推断、无默认 1.0；部分显式 provenance 不能触发
  fallback，缺文件/缺键/冲突/非有限值 fail closed。
- [x] 用真实 1.0/0.2/0.1 各 20 case 生成 JSON、两份 CSV、中文 Markdown 和 PNG；60 case 形成 20
  个完整跨档配对，truth identity/state 审计全 0，源组合 hash 前后不变。
- [x] 冻结 `3/2/1` 机会合同审计为 56 match/4 mismatch；0.1 candidate seed007/009、0.2 candidate
  seed006/009 的受影响 aggregate 保持 unavailable，reserve 仍排除。
- [x] D6 全量 `272 passed`；ClockSpeed 专项 `18 passed`，`py_compile` 与 `diff --check` 通过。
- [ ] candidate 0.1/0.2 因合同 mismatch 不发布完整物理 aggregate；case wall timing 源字段缺失，
  三档均 unavailable。后续由 main 修复 producer 证据后再重跑，不从当前部分数据给出准入结论。

## 2026-07-15 0.1 NameError 紧急回归状态

- [x] 将 timing input-mode 规范化函数前置并统一命名，loader/summarizer/evaluator 三处引用一致，旧
  私有名称删除。
- [x] 新增真实形态 20-case 双层 case-aware evaluator 回归：baseline/candidate 各 seed 1-10，逐 case
  frame/time 重置，manifest match，跨 case/跨层 total 为 null。
- [x] 真实 0.1 P1 只读生成成功：两层各 4036 records、20 case，输入 SHA-256 前后不变。
- [x] timing 专项 `28 passed`、D6 全量 `264 passed`、`py_compile`/`diff --check` 通过。
- [x] 已完成 1.0/0.2/0.1 三个 suite 的 ClockSpeed comparator；availability-aware 结果见顶部，
  不对 unavailable 的 candidate 0.1/0.2 发布性能结论。

## 2026-07-15 0.2 case-aware timing 与冻结机会合同状态

- [x] `single_episode` 与 `case_aware_suite` 显式分离；suite 只接受
  `case_id/family/profile/seed` 四个 metadata，逐 case frame/timestamp 严格单调并允许 case 切换重置，
  禁止 case 重现和跨 case 伪连续。
- [x] main bus/control tick case manifest 一致性校验完成；两层仍为嵌套 scope，不相加，跨 case/跨层
  total 均为 null；P1 acceptance v6 和两个 CLI 已支持显式 suite 模式。
- [x] 用真实 0.2 merged timing 只读复测：两层各 6567 records、20 case，manifest match，P1 bundle
  成功生成，runtime 三个输入 SHA-256 前后不变。
- [x] comparator v2 冻结每 case pair/target/coalition opportunities=`3/2/1`；actual-execution
  unavailable 或机会合同不符时，受影响 case 指标整体 unavailable，不缩分母、不补零。
- [x] standby reserve 从 active-primary success 与 denominator 排除并单独审计。真实 0.2 为 18 match/
  2 mismatch：candidate seed006 是 D7 unavailable 且 `2/1/1`；candidate seed009 是 D7 available 但
  同为 `2/1/1`。
- [x] 2026-07-15 0.2 阶段 timing/ClockSpeed 专项 `27/10 passed`，当时 D6 全量 `263 passed`。
- [x] main 已运行真实 ClockSpeed=0.1，P1 case-aware 复测见顶部。
- [x] 已连同 1.0/0.2/0.1 三个完整 suite 调用 comparator；合同 mismatch 项保持 unavailable。

## 2026-07-15 ClockSpeed 1.0/0.2/0.1 对比状态

- [x] 提供 Python API 和 CLI，输入三个 suite root/summary；强制每档 baseline/candidate 各 seed
  1-10、恰好 20 case，并按 `case_id/profile/seed` 完成 suite 内连接和三档配对。
- [x] ClockSpeed 只从 suite/case provenance 或全量一致的 case result row 读取；拒绝目录名和 summary
  根部裸字段，交叉检查 suite/case/artifact 显式值。
- [x] 输出 availability-aware JSON、case CSV、aggregate CSV、中文 Markdown 与 PNG 曲线；覆盖三层
  物理成功、第二 primary 五米/距离、最终锁/共识、collision stop、wall timing、ClockSpeed 归一化
  simulated time/tick 和 truth identity/state 审计。
- [x] main bus/control tick 保持嵌套层，cross-layer total 为 null；任何缺失指标、坏 timing 或缺
  artifact 为 unavailable，不补零。
- [x] 2026-07-15 三档各 20 case 的确定性 fixture 达到接受门限；专项 `8 passed`、D6 全量
  `254 passed`，仅有既有 Matplotlib `Axes3D` warning。
- [x] main 真实运行 ClockSpeed=`0.1` 已完成，D6 P1 case-aware 只读复测通过。
- [x] 已与 1.0/0.2 同套件配对调用 comparator；真实可用值和 unavailable 边界见顶部。
- [x] 旧 1.0 suite 的 20 个 sibling generated settings 已作为显式持久化 provenance 通过全量一致
  审计；新 suite 仍应优先保证所有 20 个 result row 都持久化同一 `clock_speed`，并与
  `intercept_summary.parameters.clock_speed` 一致；缺任一 case 时整套拒绝。

## 2026-07-15 M5N2 20-case 实测状态

- [x] 只消费 baseline/candidate 各 10 seed 的 20 个真实 M5N2 case；M5N2 完成后、`TERM` 生效前
  额外完成的 `png_ttc` seed001 明确排除在本批聚合与验收之外。其余 tuned 2v2 和全部 dropout
  未执行；缺失 case 保持 unavailable，不补零，也不把本批声明为完整 terminal-closure suite。
- [x] canonical actual execution required/available/unavailable=`20/20/0`，validation reason 为 0；
  truth identity/state 在线使用均为 0，10389 条目标状态样本均来自
  `d2_estimated_global_track`，stale=0。
- [x] 正式物理分母保持独立：pair=`12/60`、target=`12/40`、coalition=`0/20`；baseline/candidate
  均为 `6/30`、`6/20`、`0/10`。总量持平不能覆盖逐 seed non-degradation=false。
- [x] 第二 primary 漏斗 availability 完整：前四阶段 `20/20`、control/mode=`17/20`、physical
  `0/20`；20 个失败原因全部可用，最近距离 mean/min/max=`12.654/8.843/14.740 m`。
- [x] 文档术语统一：`12/40` 只称为 canonical target physical success（至少一个 participating
  pair 成功）；“全部 required member 通过阶段”只称为 cooperative target-stage diagnostic，
  不得写成或回填正式 `target_intercept_success`。
- [ ] 补齐 `collision_stop` 的 collision object/actor、时间戳和来源。当前第二 primary
  `20/20` 最终为 `collision_stop`，但对象字段未写盘，D6 必须保持原因 unavailable，不推断成员
  冲突、环境碰撞或 AirSim 状态问题。
- [x] 20 个 case 的两层 timing 原始流逐 case 严格校验；每层 3805 条，main-bus 与 control-tick
  分别汇总，禁止相加。
- [x] main 的 merged timing 已由 D6 `case_aware_suite` envelope 正式消费；case 边界重置合法，
  逐 case 单调与双层 manifest 已校验，禁止改写成全局伪连续时间轴。
- [ ] 将上述 target 术语固定为 producer schema/字段级 semantics，避免后续 suite 或旧 consumer
  仍按同名字段误聚合；文档口径已统一，代码字段治理仍开放。
- [ ] 降低 main-bus `349.34 ms` 和 control-tick `1069.45 ms` 均值及其预算违例；优先定位 D1
  fusion、AirSim frame sample、bus processing 和 control RPC。
- [ ] 关闭第二 primary `0/20` 五米物理结果和 coalition `0/20`；candidate 当前不晋升默认路径。

## 2026-07-15 第二 primary/coalition 被动报告状态

- [x] 第二 primary 七阶段漏斗按显式写盘证据输出 passed/available/unavailable/rate。
- [x] pair、target、coalition 使用独立物理机会数；新增 availability-aware 物理结果和独立
  coalition completion，禁止 target 或 pair 回填 coalition。
- [x] 首失败原因只消费显式 `first_failure_reason`；缺失为 unavailable/partial，不生成
  `unspecified`，缺物理证据不补零。
- [x] 2026-07-15 确定性 fixture 专项 `11 passed`、D6 全量 `246 passed`、`py_compile` 通过；未
  启动 AirSim。
- [x] main 已完成同配置 M5N2 baseline/candidate 各 10 seed，并提供完整 actual、物理与失败原因
  证据；额外 `png_ttc` seed001 不进入本批聚合与验收，其余 tuned 2v2 和全部 dropout 未执行。第二
  primary 和 coalition 性能未达标，继续保持 P1。

## 2026-07-15 分阶段延迟可观测性 P1 状态

- [x] 严格校验两层 schema/scope、阶段状态和值、frame/timestamp 顺序、总和、未归因耗时和预算
  flag；非法证据 fail closed，旧 artifact 缺 timing 为 unavailable。
- [x] 两层分别汇总 sample、mean/P95/max、N/A/error、总 tick、预算违例和 dominant stage；禁止
  嵌套耗时跨层相加。
- [x] 提供稳定 API、CLI、CSV/JSON/中文 Markdown/PNG；历史接入 P1 acceptance v5，当前 case-aware
  接线已升级为 v6。
- [x] 2026-07-15 动态规模无关 fixture：合法两层各 2 帧，专项 `20 passed`、全量
  `236 passed`；未启动 AirSim。
- [x] 已用真实 M5N2 20 case 的逐 case timing 定位主导阶段并确认 `100 ms` 未达标；两层各 3805
  samples，main-bus/control-tick P95=`487.40/1254.06 ms`。
- [x] case-aware suite timing 注册和只读 P1 复测完成。
- [ ] 完成瓶颈优化、三档 paired comparator 与跨提交趋势；0.1 P1 输入已可用。

## 2026-07-14 actual target-state freshness/stale P1 关闭状态

- [x] 将六个最终 command 字段冻结为 canonical 必需列；缺列、空/非有限/负数、时间顺序冲突、
  age 冲突、非法 stale 布尔和空 source 全部 fail closed，不补零。
- [x] 每 case 输出 sample、mean/p95/max age、stale count/rate、source distribution，以及独立
  availability/source/semantics。
- [x] formal validator 在 source SHA256 通过后重读 CSV 复算并比对 payload，禁止只信 JSON。
- [x] case suite、pooled aggregate、aggregate CSV/JSON 和中文 Markdown 正式报告完成接入；不修改
  physical、末端五层、truth 隔离和既有 availability 语义。
- [x] 2026-07-14 最新真实持久化源达到门限：2v2 `48`、M5N2 `608` samples，stale 均为 `0`，
  source 均为 `d2_estimated_global_track`；D6 全量 `216 passed`。
- [x] 同配置 M5N2 multi-seed freshness 已由本页顶部 20 case、10389 条样本补齐，stale=0。
- [ ] 建立跨提交 freshness 趋势和 failure taxonomy；该项不回退单 seed 指标链和本批 multi-seed
  证据状态。

## 2026-07-14 actual v2 真实 AirSim 证据状态

- [x] tuned 2v2 seed-1 与 M5N2 seed-1 均生成并显式注册通过校验的 canonical
  `d7-actual-execution-metrics-v2`；required/available/unavailable=`2/2/0`，actual P0 证据门关闭。
- [x] 两场景 summary/CSV/actual 物理成功计数均为 `2/2/2`；旧
  `d7_actual_execution_command_physical_count_conflict` 未复现，不再列为开放 GAP。
- [x] 保留三层独立分母：M5N2 pair=`2/3`、target=`2/2`、coalition=available `0/1`；不得以
  target 成功覆盖 coalition 显式失败。
- [x] M5N2 baseline/candidate 同配置各 10 seed 成对比较已完成；结果见本页顶部。
- [ ] 1-5 帧 dropout 全矩阵仍未执行，完成数为 0；缺失 case 保持 unavailable，不能据此声明完整
  terminal-closure suite 通过。
- [ ] 分解并降低 2v2/M5N2 `123.3/384.6 ms` loop latency，复验性能预算违例 `19+212=231`；
  该项继续作为 P1，不由本轮 actual P0 关闭。
- [ ] 关闭 M5N2 第二 required primary 约 `11.02 m` 的物理缺口，使 coalition 从 available
  `0/1` 达到接受目标 `1/1`。

本次为证据和状态同步，不修改 D6 代码。验收日期 2026-07-14；每个场景 1 seed，共 2 case。

## 2026-07-14 actual-execution 最终复核状态（真实重跑前历史）

- [x] required case 只有校验通过的 canonical `d7-actual-execution-metrics-v2` 才算 actual
  execution available；缺失或显式 unavailable 时 `actual_execution_all_available=false`，suite
  总验收 fail closed。
- [x] legacy main row 与离线五米结果只保留 diagnostics，不能替代或补齐 actual envelope。
- [x] `arrival_coordination_required=false` 时按每个 required active primary 的独立五米成功计算
  coalition completion；required member/denominator/physical result/开关缺失或 summary-pair 冲突
  仍输出 `null/unavailable`。
- [x] 2026-07-14 代码级验收：专项 `14 passed, 24 deselected`，D6 全量 `190 passed`；唯一
  Matplotlib `Axes3D` warning 只表示 3D projection 不可用，不影响 JSON/CSV/Markdown、二维报告
  或本轮口径结论。未运行 AirSim。

**仍开放 main P0/P1**：M5N2 baseline、M5N2 candidate、2v2 PNG-TTC、1-frame dropout 四个
历史真实 seed-1 actual artifact 仍为 `unavailable`，原因均为
`d7_actual_execution_command_physical_count_conflict`。main 必须真实重跑并注册有效 v2 artifact，
先关闭 seed-1 fail-closed 门，再进行同条件 multi-seed provenance、趋势和失败原因治理。D6 本轮
不修改 runtime，也不扩展算法范围。

## 2026-07-14 actual plan identity provenance P0 状态（真实重跑前代码验收）

- [x] actual envelope 升级为 `d7-actual-execution-metrics-v2`，强制 command CSV 提供
  `plan_id/plan_version/d4_target_node_id` 列；plan ID 和正整数 version 每行必填。
- [x] 输出去重排序的 `metadata.plan_ids/plan_versions/owner_node_ids`；version 规范化为正整数，
  owner 仅在 effective-authorized secondary/distributed active/execution/reassignment 或显式
  execute action 行必填。中心授权及未授权 pending 可为空；没有 authoritative owner 时 owner
  provenance 为 `unavailable`，owner-required 行缺值 fail closed。
- [x] 为三项 metadata 写出并校验 `status/source_artifact/reason/semantics`；hash 校验路径重读
  CSV 对照 envelope，阻止 metadata 脱离持久化来源被篡改。
- [x] merge 升级为 `d6.execution-metrics-merge.v3`；清除 replay 同名字段，只从 validated
  actual envelope 写最终 `metrics.metadata`，不改变 safety/physical/mode semantics。
- [x] 2026-07-14，seed N/A，execution-evidence focused `20 passed`、D6 全量 `184 passed`；
  中心授权空 owner 和未授权 pending 空 owner 可用，secondary/distributed effective-authorized
  空 owner fail closed，plan/version 仍逐行必填；1 条既有 matplotlib warning。未运行真实 AirSim。

**后续状态**：main/runtime 已用最终 producer 文件生成并注册本页顶部两条真实 SimpleFlight
seed-1 v2 artifact；target-state freshness/stale 的单 seed 正式分布链已由本页顶部关闭。剩余 P1
是同几何、同配置 multi-seed 的 seed/config/schema/hash provenance、跨提交 freshness 趋势和
failure taxonomy。D2 lifecycle 与 D3 plan/membership churn
的 episode-clock join 也仍开放；本次单元测试不替代这些证据。

## 2026-07-14 actual execution P0 收尾状态（真实重跑前代码验收）

- [x] 冻结 `d7-actual-execution-metrics-v2`，只认可显式 producer、post-control phase、actual
  scope、case/seed/规模、三份来源路径和 SHA256。
- [x] 增加 `build_d7_actual_execution_evidence()` 与
  `write_d7_actual_execution_evidence()`；输入仅为最终 `control_commands.csv`、
  `intercept_summary.json`、`main_episode_bus_metrics.json`，D6 不负责 episode 调度。
- [x] contract/control/mode 从 command rows 计算，physical 从 summary 计算，performance 从
  main bus clock 计算；来源冲突、缺样本、hash 篡改和 integrated replay 全部 fail closed。
- [x] 强制 `mode_switched_count <= control_allowed_count`；raw mode 变化只进 metadata audit。
- [x] actual diagnostic count 从 command CSV 按冻结语义计算；视觉 PNG transition 与持续授权 sample
  分离，sample 仅作 supplemental。
- [x] `truth_identity_online_use_count` 与 `truth_state_online_use_count` 并列进入 required count、
  source、semantics、availability 和 validator；identity 来自 command CSV，state 来自 intercept
  summary，禁止互相回填。
- [x] case consumer 在注册后重新计算 source hash，merge 缺 actual 时不再回退 replay。
- [x] 正负测试覆盖有效写盘、零性能样本、main/command mode 冲突、effective-control 冲突、
  source hash 篡改、raw replay 冒充 actual、安全计数来源和视觉 transition/sample 分离；D6 全量
  `173 passed`。

**后续状态**：main 已在三份 producer 文件 finalize 后生成并注册两条独立 artifact，真实 seed-1
门以 `2/2/0` 关闭。source hash 与 actual mode/control/physical/performance 的一致性要求不变；
multi-seed P1 和性能 P1 仍开放。D6 本批没有修改 runtime。

## 2026-07-14 terminal closure case evidence 计划状态（先前四案例）

本批 D6 owner 工作已完成：

- main terminal summary 中的多条 `d3_plan_history` 路径按 `case_id/seed` 独立加载、校验和聚合；
- suite 输出逐 case、逐 seed、总记录数和 churn 合计，单个缺文件或 schema mismatch 不污染其他 case；
- D7 路径缺失、文件缺失、registration/schema/seed mismatch 都保持 unavailable 并输出原因；
- 提供 `register_terminal_closure_case_evidence()` 给 main 在 producer 文件写盘后注册路径；
- raw D7 metrics 不具备 terminal envelope 时不进入四层指标，防止猜测语义和重复计数；
- suite、per-case、缺文件和 schema mismatch 回归已加入，全量 `159 passed`。

剩余跨模块 P1 由 main/runtime owner 执行：在 `_terminal_closure_result_row` 形成 summary 行前，
使用 episode `output_paths["d7_execution_metrics"]` 调用 registration helper；随后重生成
seed-1 正式 suite，验收 4/4 D7 case registered，最后再进入 multi-seed。D6 不修改 runtime，
也不会以目录搜索代替注册。当前实际 seed-1 的 D3 4/4 case、543 records 已可用；D7 原 summary
仍为 0/4 registered，这是明确 wiring 缺口，不是零执行结果。

## 2026-07-14 terminal suite P1 closure（D6-owned 已关闭）

本批次只修改 D6 owned paths，消费 main/D3/D7 已落盘文件，不参与在线控制或回写 producer。

- [x] 冻结 terminal-suite metric envelope：contract/control/mode/switch/physical 每条指标强制携带
  `producer`、`metric_scope`、`denominator`、`lifecycle`；以完整语义键隔离 main-bus
  planned-lock 与 D7 execution，禁止同名跨来源比较、求和或覆盖。
- [x] 提供 D3 canonical history file input；校验 schema/order/count/timestamp 后输出 plan/version、
  primary/reserve membership、owner 与 feedback churn；缺文件或无有效 history 必须保持
  `unavailable`。
- [x] 汇总 `loop_latency_ms`、`performance_budget_violation_count` 及逐项 availability；无样本时
  不得以 `0/0` 或数值零代替 unavailable。
- [x] candidate non-degradation 同时输出 effectiveness evidence；baseline/candidate 效果均为零且
  candidate mechanism trigger 为零时结论只能是 `inconclusive`，不得 promotion。
- [x] 输出 seed-level 与 aggregate 的中文 Markdown、JSON、CSV，并保持 contract/control/mode/
  physical 四层分离；补齐 README、PLAN、D6 GAP/review 文档。
- [x] 验收：`pytest -q research_modules/d6_evaluation_metrics/tests`；
  `git diff --check -- research_modules/d6_evaluation_metrics subagent_reviews/D6_*`。

实现冻结为 `d6-p1-unified-acceptance-v2` 与 `d6-terminal-metric-envelope-v1`。同名指标只在
`source + producer + metric_scope + lifecycle` 单一语义组内聚合；出现多个语义组时顶层
`sum/denominator_sum/mean` 为 `None`，逐组结果保留。D3 terminal-suite 新入口为
`P1AcceptanceInputs.d3_plan_history` / CLI `--d3-plan-history`；缺文件或校验失败保持
unavailable。输出新增 per-seed JSON、terminal metric CSV 和 aggregate CSV。

**验证**：2026-07-14，4 类新增确定性离线场景，seed 1/2/7 或 N/A：planned-lock 与 D7
execution 同名隔离、零样本性能、零效果且零触发 inconclusive、两 tick canonical history。
接受门限全部满足；D6 terminal-suite 专项 `8 passed`，canonical 专项 `24 passed`，D6 全量
`154 passed`，1 条既有 matplotlib `Axes3D` warning；未运行 AirSim。

**main 接线仍开放**：main-owned `p1_terminal_closure` 需逐 metric 写出 producer/scope/正分母/
lifecycle，分开 main planned-lock 与 D7 execution；逐 physical level 写
`physical_metric_context` 和 pair/target/coalition 分母；写出正 `performance sample_count`、
latency/budget violation；传入 `d3_plan_history.json`，并保留 candidate 实际 trigger/effect。
本批次不直接修改 runtime。

## 2026-07-14 truth-state/physical provenance P0 状态

- **P0 已关闭**：`truth_state_online_use_count` 与既有
  `truth_identity_online_use_count` 独立；summary、pair、command 的正证据按实际 pair 聚合，
  严格 D2 estimated-state 路径为 available `0`，truth-state fixture 必须 `>0`。
- **physical gate P0 已关闭**：summary 和 active pair summaries 都必须存在；command-only 与
  summary-only 不得发布 physical 指标。每个 active pair 必须显式
  `physical_evidence_available=true`，且 `target_state_source` 等于 summary
  `online_control_state_source`。offline scorer 只接受 D2 estimated class，truth fixture 只接受
  显式 fixture class。每个参与 pair 还必须有显式 physical 布尔结果或规范 scorer 终态；
  evidence flag 本身不代表失败结果。缺 pair result 时所有层为 `None/unavailable`。
- **coalition completeness P0 已关闭**：`required_primary_count` 超过实际 persisted required
  primary 数、缺 arrival window、缺 coalition denominator，或 summary 有 opportunity 但缺
  completion count 时，coalition count/rate 为 `None/unavailable`；证据完整的显式零保持
  available `0`。pair/target 可用性不被 coalition-only 缺口回填或降级。
- **CSV/legacy 边界已关闭**：command loader 保留 `physical_evidence_available` 供审计，但
  command rows 不生成 physical pair；无来源 legacy status 只作 raw audit。
- **报告链已关闭**：字段进入 `EpisodeMetrics`、standard mapping、execution merge、episode
  CSV、聚合 JSON 和 Markdown；coalition metadata 与各格式使用同一 unavailable reason。
- **验证**：2026-07-14，7 类确定性离线 provenance 场景、seed N/A，接受门限为合法 offline
  scorer/truth fixture available，legacy、command 缺证据、summary-only 和 pair source mismatch
  全层 unavailable，并新增 7 项 result/member/window/denominator/显式零回归；D6 全量
  `150 passed`，1 条既有 matplotlib warning，未运行 AirSim。
- **历史口径**：2026-07-11 至 07-13 缺新 provenance 的 physical 结果不得回填为新 offline
  scorer evidence，也不得与迁移后结果直接比较。
- **开放 P1**：本次只关闭 D6 代码/测试 P0。main/runtime 仍需按新 schema 形成同条件
  multi-seed AirSim 批次，逐 pair 写盘 evidence/source，并统计 target measurement/arrival age、
  stale/reject 分布和跨提交趋势。

## 2026-07-14 truth tracking P0/P1 状态

- **P0 已关闭**：`track_rmse/track_continuity/id_switch_count` 缺 truth-to-track 证据时为
  `None/unavailable`；完整 identity history 的零切换保留为 available `0`，D2/D6
  `id_switch_count` 字段仍显式存在。
- **报告链已关闭**：JSON、episode CSV、batch summary、Markdown、main-bus loader 和
  replay/execution merge 均尊重 availability；旧载荷的 unavailable `0` 不进入统计。
- **验证**：2026-07-14，5 个确定性场景、seed N/A；空输入、匿名 track、不完整 sidecar、
  完整 truth 零切换、完整 truth 有切换全部达到门限。D6 全量 `137 passed`，1 条既有
  matplotlib `Axes3D` warning；未运行 AirSim。
- **剩余 P1**：真实 multi-seed producer 的 seed/config/schema/hash provenance 完整性；
  D2 lifecycle 与 D3 plan/membership churn 按 episode clock、`global_track_id`、plan/version
  的跨源 join 和长期趋势。两项均未由本次单元回归替代。
- **剩余 P2**：外部 MOT/HOTA、OSPA/GOSPA、Stone Soup 和原生 recording parser 状态不变。

## 2026-07-14 第二批当前 P0/P1/P2 状态

- **canonical history 接线已闭合**：D6 识别 `d3_plan_history_v1` wrapper 和
  `d3_plan_history_record_v1` record，不依赖 cooperative snapshot 推断 churn。
- **严格校验已闭合**：至少 2 条；record_count 一致；sequence index 唯一且严格递增；
  ordering key 与 sequence/timestamp 一致且严格递增；timestamp 不倒退；record schema 和
  指标所需 assignment/coalition/owner/feedback 结构完整；禁止 truth 字段。失败原因进入
  CSV、聚合 JSON 和 Markdown，全部 history-derived 指标保持 unavailable。
- **指标已闭合**：计划、联盟 version/epoch churn；基于 assignment snapshot diff 的总体、
  primary、reserve membership change；owner change；soft/hard feedback；history record count
  与 validation audit。membership audit event 不作为计数来源。
- **兼容性已闭合**：旧 snapshot、旧 ordered history 和 formal cooperative-role 输入继续
  可读；只有证据充分的旧有序历史可计算，snapshot/cooperative-role 不足证据仍 unavailable。
- **验证**：2026-07-14 canonical 专项 `24 passed`，D6 全量 `132 passed`，1 条 matplotlib
  `Axes3D` 环境 warning。测试覆盖稳定零、版本/成员/owner/feedback 变化、乱序、重复索引、
  timestamp 倒退、单记录、schema/count/order key 错误和无 truth 字段。
- **剩余 P1**：在真实 AirSim/main multi-seed episode 上持续运行该入口，建立跨提交趋势、
  门限稳定性和统一 failure reason taxonomy。本轮只闭合 D6 schema/metric/report 接线，没有
  新物理实验结论。
- **剩余 P2**：真实 D2/D5 replay 的 py-motmetrics 门限、遮挡和重现标定；TrackEval/HOTA、
  Stone Soup metrics、OSPA/GOSPA、AirSim 原生 recording parser 等 optional/offline 项。

main/D6 调用保持 file-only：CLI 使用 `--d3-plan-history <episode/d3_plan_history.json>`，或
Python API 传入 `P1SystemEvidenceInputs(d3_assignment_churn=history_path)`。D6 不回写 main/D3。

以下第一批 2026-07-14 状态和 2026-07-13 更早章节是历史快照。

## 2026-07-14 第一批 P0/P1/P2 状态（历史）

- **评估级 P0 已闭合**：D3 最终快照、空 mapping、单条无序记录不再把
  `plan_version_churn_count`、`coalition_version_churn_count`、
  `coalition_epoch_churn_count`、`membership_change_count` 推断为 available `0`。
- **可用性合同已冻结**：只有显式 count，或至少两条带顺序语义且同名证据完整的历史记录，
  才计算 churn。稳定有序历史和显式零均输出 available `0`；缺字段、单快照和不完整历史输出
  `unavailable`。formal cooperative-role `pair_rows` 分支继续只报告角色，不补 churn。
- **验证**：2026-07-14 使用 5 类 fixture（最终快照、空输入、单条无序、两条稳定有序、
  显式零）验收，接受标准是前三类四项全 unavailable、后两类四项全 available `0`；专项
  `12 passed`，D6 全量 `120 passed`，1 条 matplotlib `Axes3D` 环境 warning。
- **剩余 P1**：main/D3 写出真实有序 plan history、统一 episode clock、version/epoch、source
  provenance 和 availability；建立长期真实 multi-seed 跨提交趋势；治理跨批次 failure reason
  taxonomy。最终 snapshot 仍不能替代历史。
- **剩余 P2**：真实 D2/D5 replay 的 py-motmetrics 门限、遮挡和重现标定；TrackEval/HOTA、
  Stone Soup metrics、OSPA/GOSPA、AirSim 原生 recording parser 等 optional/offline 项。

以下 2026-07-13 及更早章节均为历史状态和证据快照；历史数字不改写为当前结论。

## 2026-07-13 历史最终状态入口

D6 的统一离线报告入口已经兼容 cooperative 原始 `cases/pair_rows/aggregates` 和修正后的 `d6-cooperative-closure-v2` aggregate。当前冻结证据可展开为：D1 1 条、D2 3660 条、D3 40 条、D4 60 条、D5 per-primary 160 条、native MOT 18 条、D7 164 条。D7 的 164 条由 160 条 pair/safety 记录和 4 条 profile 汇总组成，profile 汇总不与逐 pair 四层指标重复计数。

当前验收结果：

- M5N2 最佳 profile coalition 为 `5/10`，四个 profile 总体为 `8/40`；未达到 `8/10` 是实测结果，不是 D6 分组或分母错误。
- D7 四层显式计数为 contract `35`、control `7`、mode switch `9`、physical `62`；四层只读取同层证据，不跨层反推。
- online truth use、`global_track_id` rewrite 和 reserve unauthorized execution 均为 `0`，且 evidence available。
- D3 输入没有逐时刻 plan history/churn 记录，因此 D3 churn 保持 `unavailable`；D6 不从最终 snapshot、版本总数或其他模块记录重建该值。
- 缺值保持 `unavailable`，显式观测到零才是 0。source manifest 和逐行记录保留 schema、SHA256、producer/run、evidence path 与 provenance。
- bootstrap 95% CI 仅对至少两个显式 seed 的逐 seed 均值计算，固定 2000 次重采样和 RNG seed；不足样本不产生区间。

截至本状态，D6-owned cooperative schema、聚合、availability、四层分离和中文报告缺口均已闭合，全量回归为 `115 passed`。仍开放的 P1 只包括长期真实 multi-seed 趋势、producer 逐时刻 schema（特别是 D3 churn）和跨批次失败原因治理。P2 工具继续保持 optional/offline，不进入默认依赖、默认报告主线或在线控制路径。

以下较早日期章节保留历史实现与证据演进；发生冲突时，以本节为准。

## 2026-07-13 P1 统一系统证据验收历史记录

D6 已将统一离线报告入口收敛到 D1-D7 当前 P1 证据：D1 dense-crossing freeze summary、D2 六难度逐 seed 关联、D3 M5N2 计划/联盟 churn、D4 episode tick 或 fault matrix、D5 per-primary/native MOT、D7 pair guidance/physical intercept。输出为逐 seed/source CSV、聚合 JSON、中文 Markdown 和 PNG，不导入在线 producer，也不控制 AirSim。

验收口径：

- `contract_allowed/control_allowed/mode_switched/physical_intercept` 只读取各自同名语义，不跨层反推。
- 缺值为 `unavailable`；显式观测到零才是 0。source manifest 和逐行记录保留 schema、SHA256、producer/run、evidence path 与 provenance。
- bootstrap 95% CI 只对至少两个显式 seed 的逐 seed 均值计算，固定 2000 次重采样和 RNG seed；不足样本不产生区间。
- D1/D2/D5 truth 只作离线评分，在线 truth use 和 `global_track_id` rewrite 单独审计。
- 失败原因按全局和来源分别统计；成功行的显式空失败列表是“available 且 0”，缺失败字段是 unavailable。

真实 AirSim M5N2 40-case 原始 summary 与修正 cooperative aggregate 已进入统一入口回归。原始 schema 按 40 个 case 展开 D3 显式角色、D5 160 个 pair/safety 行，以及 D7 160 个 pair/safety 行和 4 个 profile 汇总行；修正 aggregate 在没有逐 pair 明细时保守恢复 profile、D5 funnel/common-lock 与 D7 四层/coalition/safety 汇总。两条路径均得到最佳 profile `5/10`、总体 coalition `8/40`，且不再按 `case_id::profile` 形成 40 个单 seed 组。

该批次 D4 fault、native MOT 和 M5N2 证据已经进入最终统一报告；后续新批次继续沿相同 schema 接入。producer 文件缺失或字段尚未写盘时，D6 保持 unavailable，不补零或构造替代数据。

## 2026-07-12 P1 dense-crossing 第二批报告状态

D6 已实现 `d6-dense-crossing-evaluation/v1` 文件协议报告器，直接兼容 D1 `d1.governed_replay_manifest.v1`/offline truth summary 和 D2 `d2-p1-identity-calibration/v1`。D6 不 import D1/D2，不运行 tracker，不把评估结果回写控制。

当前能力包括：

- 10-seed screening 只用于选出明确标记或按 IDSW、continuity、false track、latency 排序的最佳 GNN candidate；不足 10 seeds 不形成选择。
- 20-seed confirmation 分开聚合 GNN baseline、同 config ID 的最佳 GNN candidate 和轻量 JPDA；不足 20 seeds 不形成晋级。
- 历史 `d6-dense-crossing-evaluation/v1` promotion 对照固定检查 IDSW `-30%`、identity continuity `+0.10`、false track `+10%` 上限、冻结 p95 loop latency budget 和 truth leak `=0`；该 `+0.10` 已标记为 legacy，不再用于解释 D2 v2。统一 system-evidence v2 忠实消费 D2 ceiling-aware admission 的显式 gate、门限值和失败原因，不在 D6 内重算判决。
- 每个指标独立携带 available/unavailable 与原因。当前 D2 仅写 NIS/NEES availability 而未写 per-seed mean 时，均值保持 unavailable。
- FilterPy/Stone Soup object adapter smoke、MHT 和未分类实现不进入本轮晋级；轻量 JPDA 保留 `research_approximation` 成熟度标签。
- 固定输出 `dense_crossing_per_seed.csv`、`dense_crossing_aggregate.json`、中文 `DENSE_CROSSING_CALIBRATION_REPORT.md` 和 `dense_crossing_metrics.png`。

下一步由 main 提供真实 AirSim 冻结 replay 的 10/20-seed D1/D2 写盘 evidence 并调用该报告器。若 D2 后续增加 NIS/NEES 均值或置信区间，D6 只沿现有 availability 字段扩展读取；不得把 availability count 当成统计值。

## 2026-07-12 P1 cooperative-closure-v2 状态

本轮离线报告能力已经实现：主行记录支持 JSON/JSONL/CSV 与内存对象，按实际 M/N 形成逐 seed 数据集；pair、target、coalition 使用独立分母；第二 primary failure、共同锁定率、到达离散、最小成员间距和 D4 通信故障可独立统计。D3 candidate、D4 communication、D5 visibility、D7 guidance 均为可选证据，manifest 明确 available/unavailable。

D4 真实合同已对齐：`CommunicationFaultReplayReport` 同时含 `seeds` 和 `cases` 时固定消费 `cases`；case 的 `scenario_id/passed/fail_closed` 分别进入 fault key、pass rate 和 fail-closed rate。别名仅位于 D4 communication 专用归一化，不扩展到 main/D3/D5/D7 通用业务行。

2026-07-13 已用真实 M5N2 40-case/4-profile/10-seed summary 完成 schema 回归并修正聚合键：逐 case/seed 明细继续保留，但 acceptance 按 profile 的唯一 seed 计数；稳定 `coalition_id` 用于跨滚动 version/epoch 合并联盟；只有至少两个 active primary 的目标进入 coalition 分母。source 声明的 `best_candidate_profile` 优先于 D6 fallback 排序，缺少声明时才按通过数、完成率、available seed 数和稳定名称排序。

修正后 source 最佳 profile `d3-p1-h020.0-w03.0-s040.0` 为 `5/10`，`coalition_at_least_8_of_10` 明确为 available+failed，不再因 40 个单 seed case group 误报 insufficient evidence。四 profile 完成数 `0/10、5/10、2/10、1/10` 与 source summary 一致；缺失 seed 继续单列 unavailable，不补 0。后续只需 main 持续提供同 schema 证据，D6 不负责 AirSim 调度。

## 2026-07-15 D2 v2/legacy 准入证据兼容计划状态

本批计划已经完成：

1. 将统一 system-evidence 输出升级为 v2，增加 D2 策略版本、连续率上限感知字段、全部门限状态和逐字段 availability。
2. 失败原因按 v2 gates、legacy structured checks、legacy bool checks 的顺序解析；v2 具体 gate reason 优先，缺 reason 时仍保留 gate 名。
3. aggregate JSON 和中文 Markdown 新增 D2 准入评审段，明确 recommendation-only，不参与控制或默认主线切换。
4. 新增通过、失败、structured legacy、bool legacy 和缺字段回归；缺失值保持 `None/unavailable`。
5. 同步 README、PLAN、GAP/review、模块原理、算法、AirSim 接口和实验文档。

2026-07-15 正式证据闭环：

6. [x] 消费 frozen replay 的 `d2-p1-identity-calibration/v2`，生成 D2-only CSV/JSON/中文
   Markdown/PNG；其他六源显式 unavailable，`full_system_decision=not_evaluated`。
7. [x] aggregate 保留 promotion recommendation/candidates、selected/default path、14 条 overall/
   分档 assessment、五 gate reason 和 dropout truth-alignment summary；legacy 缺字段仍为
   `None/unavailable`，D6 不重算 producer decision。
8. [x] 记录总体五 gate 通过但仅建议评审；仅 clutter/combined 分档通过，四档 baseline IDSW=0
   fail-closed；JPDA research adapter 不准入，默认在线 GNN/Hungarian 未改变。

验收日期 2026-07-15：system-evidence 专项 `31 passed`，D6 全量 `243 passed`；本批未运行
AirSim。“D6 尚无 D2 v2 正式证据”的 P1 报告缺口已关闭。仍需 D2/main owner 完成 promotion
评审决定；D1/D3/D4/D5/D7 未与本批同 case/seed 组合，因此全系统判决仍未评估。

## 1. 模块定位与边界

D6 是系统级离线评估模块。它消费 D1-D7、main runtime、AirSim Blocks replay、合成仿真和人工/规则标注产生的日志，输出可复现的指标、CSV、Markdown 报告和 PNG 图表。

D6 不参与控制：

- 不发布航迹、分配、降级、末端配准或导引决策。
- 不生成 fire-control 参数、毁伤模型、自动处置动作或授权绕过流程。
- 不把评估侧 truth label、高威胁标签或后验 review label 回写到在线系统。
- 只读取已落盘记录；所有 AirSim/D4/D5/D7 接入均为 offline/file adapter。

D2/D6 的硬约束必须保留：`id_switch_count` 是一级显式指标，不能只被 MOTA、成功率或总体得分间接吸收。

## 0.1 2026-07-12 P1 第二批统一验收实现

- `P1AcceptanceInputs/P1AcceptanceReportGenerator` 已形成 file/offline-only 聚合边界，可消费 main P1 terminal closure 与 D1-D5/D7 的版本化 replay/calibration summary；不 import 或调用在线模块。
- 统一 bundle 输出 `p1_acceptance_per_seed.csv`、`p1_acceptance_aggregate.json`、中文 `P1_UNIFIED_ACCEPTANCE_REPORT.md` 和 `p1_acceptance_overview.png`。
- contract/control/mode/physical 四层和 pair/target/coalition 三层分别聚合；上游旧字段缺失保持 unavailable，不做跨层推断。
- D7 dropout、TTC 四类拒绝和 trend 晋级判据，D4 failover matrix，以及 D2 IDSW/continuity 均有独立报告区；D1、D3、D5 保留 source schema 和关键摘要。
- 本轮关闭的是 D6 离线消费和统一报告代码缺口。真实同条件 M5N2 AirSim paired、真实 dropout/`png_ttc`、D5 持续视觉和 D4 物理接管 evidence 仍由 main 与上游模块生成。
- 当独立 D7 summary 缺失时，统一报告从 main suite 的版本化 `acceptance.dropout_matrix` 和显式 family rows 派生 dropout/`png_ttc`/trend 专项摘要；来源写为 `main_terminal_closure`。独立 D7 summary 仍具有优先级。
- `physical_levels` 只统计 `family=m5n2_paired`，不混入 2v2 dropout 或 `png_ttc` 成功。contract/control/mode/physical 继续只读同名字段。
- `p1_terminal_closure_smoke_v2_20260712` 已验证 fallback：dropout complete/compliant，TTC 1 seed 且 not-expanding=1，trend trigger=0/promotion=false；四层字段等待 main 新版本写盘。

## 1.0 2026-07-12 D7 PNG Delivery 评估交付

- 已在 `EpisodeMetrics` 和 D7 CSV/JSON replay 中接入 terminal filter、TTC 面积有效性、soft prediction/coast、锁定连续性、视觉模式驻留和命令跳变指标。
- 所有新增指标使用 `Optional` 与 `metric_availability`；只有上游写出对应证据时才可用。
- 已提供 baseline/candidate 多 seed CSV、JSON、中文 Markdown bundle，并按显式 profile 和实际 N/M 规模分组。
- 继续保持 contract/control/switch/physical 四层与 pair/target/coalition 三层分离；D6 不修改阈值、不授权 coast、不参与控制。
- main/D7 后续需要稳定写出 profile、terminal filter state/reason、TTC reject reason、elapsed time、terminal lock、visual mode 和三轴速度命令；字段缺失时报告保持 NA。

本节是 2026-07-12 的当前 P0/P1 状态入口；后续 2026-07-11 小节只保留历史批次口径：

- **P0 保持闭合**：没有新增运行级 P0 blocker。实际规模归一化、显式 `id_switch_count`、online truth 隔离、execution/contract 分离、evidence availability 和 `cuas-standard-map-v1` 保持原状态。
- **P1 D6 实现闭合**：terminal filter measured/predicted/innovation-rejected/reset/expired、TTC 四类拒绝、soft prediction/coast duration/expiry、terminal lock continuity、visual mode duration、command discontinuity 已进入指标、availability、标准映射和离线 replay；terminal delivery 对照 bundle 已实现。
- **2026-07-12 实际证据**：D6 对照包消费 26 个 episode，按 scope/scenario/profile/实际 N/M 形成 4 组。2v2 baseline 10 seeds 为 pair/target `19/20`，candidate 10 seeds 为 `20/20`；candidate 自然运行未触发 soft prediction 或 trend coast，因此只闭合非退化验收，不证明增强算法贡献。四层 logging smoke 为 `contract_allowed=4/36`、`control_allowed=2/36`、`mode_switched=5`、`physical_intercept=2/2`；早期 10-seed 文件缺新列时保持 NA。
- **M5N2 证据边界**：35 s 高净空 baseline 为 target `6/6`、active-primary pair `6/9`、coalition `0/3`；8 s candidate 为 active pair `0/9`、最近距离 22-32 m。两批几何和窗口不等价，不能形成 baseline/candidate 结论，也不能把 target success 回填为 coalition completion。
- **当前开放 P1**：同一 z=-30 m、35 s 几何和同 seed 的 M5N2 paired baseline/candidate；独立 `png_ttc` 多 seed；1-5 帧锁后 dropout 矩阵与 0.25 s fail-closed；trend coast 在错误绑定、命令跳变和物理成功三项均不退化后再决定是否进入默认 profile；以及既有完整标准化报告、场景库/CI 接线、长期真实 replay/review/window/阈值趋势。
- **下一验收条件**：M5N2 必须分别报告 target、active-primary pair、coalition completion；`png_ttc` 必须报告 area jump、bbox clipping、not expanding、TTC out-of-range；旧日志缺字段继续为 unavailable，不得补 0。D6 只消费 main/D5/D7 写盘证据。
- **验证与变更边界**：该 D7 专项阶段指定测试为 `84 passed`；加入本轮 P1 统一验收和 main-summary fallback tests 后，D6 当前为 `88 passed`，伴随 1 条本机 matplotlib `Axes3D` warning。

## 1.1 P1/P2 历史状态（2026-07-11）

以下内容保留 2026-07-11 当日证据；当前 P0/P1 判定以 1.0 节为准。

D6 当日仍保持 offline-only。当日状态按证据成熟度分为四层：

- **P0 已闭合并保持回归**：实际规模归一化、显式 `id_switch_count`、truth isolation、execution/contract 分离、evidence availability 和 `cuas-standard-map-v1` 均已进入本地主线；当前没有运行级 P0 blocker。
- **P1 合同/指标接口已完成**：M 对 N DTO/loader/writer/聚合、合法协同锁与错误重复锁拆分、center replan 生命周期、联盟 ACK/commit/epoch/lease、二级 lifecycle、D5 YOLO/MOT 预算、四导引律配对和多 seed 报告接口均已实现。
- **P1 合同层实测已闭合**：CV 10-seed 达到 8/10 T001 双 primary 同帧共识与授权证据；secondary 和 distributed 均形成 executing 3/3 commit；missing-ACK 以 aborted 2/3 fail closed。10 个 CV seed 的 IDSW 与错误重复锁均为 0。
- **P1 物理与长期 evidence 仍开放**：SimpleFlight 虽已验证每 seed 4 bindings、3 active + 1 standby，但 30 个 active pair 物理命中为 0；24 个 detection timeout、6 个 timeout。当前 15 s、`control_dt=0.5 s` 仅是诊断窗口，不能用于导引律有效性结论。`ScenarioLibrary` 只是已完成的版本化接口，不等于长期场景语料和 CI 趋势已经建立；D1-D3 长期 replay、YOLO/MOT 长时预算、四导引律长窗口多 seed、跨提交场景覆盖和阈值趋势仍是 P1。
- **P2 optional benchmark**：最小 frame-level schema 与 py-motmetrics adapter 代码已实现，但当前真实 backend 验证仅覆盖 2 帧离线 smoke fixture；IDF1/MOTA/MOTP 在该冻结 schema 上可计算，尚未完成真实 D2/D5 replay 的门限、遮挡和重现标定，HOTA 不可用。TrackEval、Stone Soup metrics、OSPA/GOSPA 和其他非参数统计仍待实现。所有 P2 能力只作隔离离线对照，不替换默认在线关联/导引路径或 D6 本地指标主线，也不进入默认依赖。

同批 P2 evidence 的标签不得升级：D2 FilterPy/Stone Soup 仍只是对象 adapter smoke，D5 OpenCV 结果是离线合成标定/PnP 对照，D6 py-motmetrics 是 2 帧 smoke，D7 3D PN/APN/FRPN 是离线质点对照且 FRPN 仍为研究近似。D6 只在报告中保留这些边界，不把它们表述成默认算法替换或在线能力。

已完成的 D6 代码能力包括：

1. `MetricsCollector` 已实现二级 readiness/plan 状态驻留、activation latency、fallback/lease/stale reject；上游没有显式 lifecycle event 时保持 unavailable。
2. D5 perception event 已实现 YOLOv8 recall、ByteTrack/BoT-SORT local-ID continuity、cross-view rate、latency 和 CPU/GPU budget 统计；离线 truth 只能位于 `metadata.offline_truth`。
3. 四导引律同 seed 配对已独立实现，要求 main 写 `experiment_guidance_law`；command-level `guidance_law_counts` 不作为实验选型，避免把中末段混合模式误判为实验组。
4. `ScenarioLibrary` 已实现 tags、difficulty、expected failure modes、parameters、seed matrix 与 online truth policy，输出 JSON/CSV/中文 Markdown。
5. 通用报告和 AirSim calibration 已接入新指标，提供 CSV/JSON/Markdown 和 PNG 曲线接口。

最新 evidence 根目录为 `research_modules/airsim_runtime/outputs/p1_p2_validation_20260711/`。CV 结果的 `physical_intercept_count=None`、`control_allowed_count=0` 是正确口径：ComputerVision 状态合同没有执行 SimpleFlight 控制。SimpleFlight `physical_intercept_count=0` 且 evidence available，表示确实运行了物理控制但未命中；两者不得合并。

后续顺序固定为：先延长/细化 SimpleFlight 物理实验并解决 detection timeout，再持续补 D1-D3、YOLO/MOT 和四律长窗口 evidence；D6 继续按 contract/control/switch/physical 四层指标汇总。未写出的指标保持 unavailable，禁止用默认 0 补齐。

## 1.2 P1/P2 历史实现状态（2026-07-11）

1. P1 已接入 `d4_coalition_commit_state`，同时兼容扩展 `CoalitionRecord`；按 target/coalition/plan/epoch generation 去重，输出成员 ACK 完成率、ACK latency、lease、timeout、aborted/reconfiguring 和 secondary/distributed commit。
2. P1 已新增终端四层指标：`contract_allowed`、`control_allowed`、`mode_switched`、`physical_intercept`。四层分别按各自 evidence 计数，不从前一层推断后一层；当前 ComputerVision 的 `control_allowed_count=0`，且缺拦截 summary/pair/control status，因此 physical 保持 unavailable。
3. physical 层新增三个独立验收分母：active assigned pair、唯一 target、需要协同的 target。`collision_intercept/range_intercept` 均为 pair physical success；target 只需任一 participating pair 成功；coalition 要求全部 required primary 在各自 arrival window 内成功。缺 arrival window 时 coalition 为 unavailable，不能用 pair 或 target 成功代替。
4. summary 判据审计读取 5 m、NED、3D Euclidean 和 criteria version；ComputerVision 即使存在状态记录也保持 physical unavailable。control record 可报告 detect/coast 六项诊断与 `truth_identity_online_use_count`，D6 不把诊断用于控制。
5. P1 字段已进入 `EpisodeMetrics`、通用报告、标准映射和 main-bus JSON loader；旧 CoalitionRecord、旧 JSONL 和旧 metrics JSON 继续兼容。
6. P2 已实现冻结 `msm-offline-mot-v1` schema 与可选 py-motmetrics adapter；当前只在 2 帧离线 smoke fixture 上验证 IDF1/MOTA/MOTP 可计算，HOTA 明确 unavailable，可选依赖缺失时输出 `unavailable_reason`。依赖仅位于 `/home/linux/.cache/msm-p2-venv`，版本 `motmetrics 1.4.0`，默认 requirements、在线路径和 D6 本地指标主线均不变。
7. 当日 D6 全量回归为 `82 passed`；指定 P2 环境的 2 帧 fixture 输出 IDF1=1.0、MOTA=1.0、MOTP=0.15。该数值只证明 adapter/backend 接线可运行，不是跟踪质量、算法收益或生产 benchmark 结论。

## 1.3 P1 历史实测验收矩阵（2026-07-11）

| 场景 | D6 核对结果 | 状态 |
|---|---|---|
| CV 10 seed 中心正常 | 8/10 T001 双 primary 共识与授权；10/10 IDSW=0、错误重复锁=0；control=0、physical unavailable | 合同层验收闭合；2 个尾部 seed 保留回归 |
| 二级接管 | `secondary_plan_v2` active，secondary executing commit，ACK 3/3 | P1 状态合同闭合 |
| 完全分布式 | interceptor peer executing commit，ACK 3/3 | P1 状态合同闭合 |
| missing ACK | aborted，ACK 2/3，D7 commit/contract/control 均不允许 | P1 fail-closed 负例闭合 |
| SimpleFlight 10 seed | 每 seed 4 bindings、3 active + 1 standby；0/30 active pair 命中，24 detection timeout、6 timeout | 绑定合同闭合；物理拦截开放 |

本矩阵只引用现有小型 JSON/JSONL evidence，不复制 AirSim 大型日志。15 s 和 `control_dt=0.5 s` 是本批次限制，不应外推为系统上限。

## 2. 当前实现概览

当前 D6 已实现轻量、可测试的本地指标主线：

- 数据模型：`EpisodeMetrics`、`TrackRecord`、`AssignmentRecord`、`EventRecord`、`LinkRecord`、`TerminalRecord`。
- 收集器：`MetricsCollector.add_track/add_assignment/add_event/add_link/add_terminal()` 和 `compute_episode()`。
- 日志接口：标准化 JSONL loader、Blocks replay JSONL loader、main episode bus metrics JSON loader、D4 active-degradation CSV loader、D7 intercept/guidance CSV/JSON loader、AirSim calibration 多 seed 汇总 loader。
- 报告接口：`ReportGenerator` 输出 `episode_metrics.csv`、`summary_metrics.csv`、Markdown 报告、分类 PNG 图和 `standard_metric_mapping.csv`；`AirSimCalibrationReportGenerator` 保留原 records/逐 seed summary/Markdown，并新增 `airsim_calibration_cross_seed_aggregate.csv`、`airsim_calibration_paired_comparison.csv`、`airsim_calibration_aggregate.json`、`airsim_calibration_aggregate_report.md`。cross-seed 分组去掉 seed 并保留实际规模，统计键会从 `scenario_version` 移除运行 seed 片段但 records 保留原值；paired comparison 输出 pair/missing seed、delta mean/std、Cohen's dz 和固定 RNG 的 2000 次 bootstrap 95% CI。单一 seed 对仅为 `descriptive_only`，不输出推断 CI/effect size。
- 拦截聚合：calibration record/CSV/summary/cross-seed 直接保留 execution/contract 的成功、collision/range/abort、最小距离、拦截耗时、visual PNG、terminal switch/takeover 和 gate reject 指标。availability gate 要求 `intercept_summary.json`、`control_commands.csv`、显式 summary/pair/status 或正数 D7 execution event 证据；无证据的 read-only episode 写 `None/unavailable`，不把默认零解释为失败。计数输出跨 seed `sum`；四类 outcome 使用实际 target count 输出 opportunity/rate；距离、时间、比例输出分布统计。abort 只从同 scope 的 `intercept_status_counts` 派生，D6 不从失败原因猜测。Outcome 表只显示有证据的行并明确 scope。
- main runtime 接入：`--p1-calibration-sweep` 已在 batch 结束后自动调用 `AirSimCalibrationReportGenerator.write_report_bundle()`，输出 `d6_airsim_calibration/airsim_calibration_records.csv`、`airsim_calibration_summary.csv`、`airsim_calibration_summary.json` 和 `airsim_calibration_report.md`。D6 只消费 sweep 已写盘目录，不启动 AirSim、不控制 camera/gimbal、不参与 D4/D5 降级或配准决策。
- 批量统计：count、mean、sample std、stderr、normal-approximation 95% CI、median、p05、p95。
- 分组统计：通用报告按 `metric_scope`、`seed`、`scenario_group` 和实际 `drone_count/resource_count/target_count/camera_count` 分组；AirSim calibration bundle 按 `metric_scope`、`seed`、`scenario`、`comparison_role`、secondary height/FOV/count、detection backend 和 actual scale/trend 字段分组。

当前依赖保持轻量：Python 标准库、NumPy、matplotlib、pytest。默认测试不依赖 AirSim 服务、Stone Soup、TrackEval、py-motmetrics、SCRIMMAGE、GPU 或网络；可选 benchmark 没有替换任何默认在线路径或 D6 本地离线评估路径。

## 3. 已实现指标

### 3.1 EpisodeMetrics 与规模字段

`EpisodeMetrics` 显式包含：

```text
episode_id
seed
scenario_group
batch_seed
metric_scope
drone_count
resource_count
target_count
camera_count
duration
mission_outcome
success_reason
failure_reason
eval_priority
implementation_status
evidence_path
scenario_version
standard_mapping_version
standard_metric_family_summary
module_duration_ms
loop_latency_ms
record_latency_ms
cpu_budget_utilization
gpu_budget_utilization
performance_budget_violation_count
metadata
```

规模口径：

- 优先读取 `truth_summary` 顶层或 `truth_summary["scenario"]` 中的 `drone_count/resource_count/target_count/camera_count`。
- Blocks replay 从 `resources`、`truth_objects`、`cameras` 计算规模。
- 缺失时从 assignment、terminal、event、link metadata 中推断资源、目标和相机集合。
- `drone_count` 缺失时默认等于 `resource_count`。
- `2v2/5v5` 只保留为 baseline 场景名，不能作为分母或规模推断来源。

测试已覆盖 `episode_id/scenario.name` 含 `5v5`，但实际规模为 `3/3/4/6` 的情况，D6 按实际字段输出。

### 3.1.1 Mission outcome、root cause、性能和 EVAL tracking

P0-A/P0-C 字段已进入 D6 episode 主线：

```text
mission_outcome in {success, partial, failed, aborted}
success_reason
failure_reason
root_cause
top_failure_causes
eval_priority
implementation_status
evidence_path
module_duration_ms
loop_latency_ms
record_latency_ms
cpu_budget_utilization
gpu_budget_utilization
performance_budget_violation_count
```

实现口径：

- `mission_outcome` 优先消费 `truth_summary` 或 event metadata 中显式写盘的 outcome；缺失时基于 intercept success、required success count、abort/runtime exception、安全事件和部分进展被动派生。
- `success_reason`、`failure_reason` 优先使用上游写盘原因；缺失时由 D6 根据指标摘要生成简短解释。
- `top_failure_causes` / `root_cause` 从 records/metadata 和 D6 已计算指标派生，覆盖 tracking、assignment、terminal_gate、guidance、coverage、runtime_exception、communication、safety、performance；D6 不做控制链路因果推断或回写。
- 性能监测消费上游写盘的 module duration、loop latency、record latency、CPU/GPU budget utilization 和 budget violation；缺失时输出 0 和 metadata placeholder，便于 main 报告保持 schema 稳定。
- `eval_priority`、`implementation_status`、`evidence_path` 用于 main 报告追踪 P0/P1 状态，优先来自 truth_summary/metadata。

### 3.1.2 标准化评估映射最小版

P0-A 标准化评估映射最小版已实现，版本固定为 `cuas-standard-map-v1`。D6 只建立离线报告映射，不引入外部认证流程，也不改变 D1-D7/main runtime 控制链路。

映射最小字段：

```text
engineering_metric
standard_metric_family
standard_sources
implementation_status
evidence_requirement
```

覆盖的标准指标族：

```text
mission/root cause
detection
tracking
assignment
degradation
terminal
communication
guidance/intercept
safety
performance
reproducibility/evidence
```

实现口径：

- `standard_mapping.py` 保存 `COURAGEOUS/MDPI/OCEF -> EpisodeMetrics` 的静态映射表。
- `MetricsCollector.compute_episode()` 从 `truth_summary` 或 event metadata 读取 `scenario_version`，固定写入 `standard_mapping_version=cuas-standard-map-v1`，并在 metadata 中保留 `standard_metric_families`、`standard_metric_family_summary` 和 `standard_mapping` 摘要。
- `EpisodeMetrics.metric_names()` 不包含 `scenario_version`、`standard_mapping_version`、`standard_metric_family_summary`，避免污染数值统计。
- `ReportGenerator.write_episode_csv()` 输出这三个非数值字段；`write_markdown_report()` 在 `EVAL Tracking` 后输出 `Standard C-UAS Mapping` 表；`write_standard_mapping_csv()` 输出 `standard_metric_mapping.csv`。
- AirSim calibration records/summary 也保留 `scenario_version`、`standard_mapping_version`、`standard_metric_family_summary`、`evidence_path`、`trend_key`、`secondary_height_bucket`、`metric_scope` 和 actual scale 字段，便于 main 长期趋势报告复用。

### 3.2 探测指标

```text
detection_probability = TP / (TP + FN)
false_alarm_rate = FP / duration
missed_detection_rate = FN / (TP + FN)
```

当前实现来源：

- 落入 `truth_timestamps` 的 `TrackRecord.truth_id + timestamp` 或显式 offline match/miss 事件构成离线配对裁决；仅有 truth opportunity 列表不足以使指标可用。
- `TrackRecord.truth_id is None` 的在线隔离航迹不自动计 false alarm；只有离线裁决为 truth-pair 集合外的带标签检测才计虚警。
- `truth_summary.truth_timestamps` 或 `total_truth_opportunities` 定义真值机会数。

### 3.3 跟踪指标

```text
track_rmse = sqrt(mean(||position - truth_position||^2))
track_continuity = matched_truth_timestamp_pairs / truth_timestamp_pairs
id_switch_count = count(global_track_id changes for the same truth_id over time)
```

`id_switch_count` 对每个 `truth_id` 按时间排序，比较连续 timestamp 的 `global_track_id`。D6 不修改 `global_track_id`，只统计 D2/上游输出的身份连续性。

### 3.4 分配指标

```text
duplicate_assignment_count =
  count(targets assigned to more than one active resource in the same plan snapshot)

unassigned_high_threat_count =
  count(high-threat truth/track items without effective active assignment)
```

当前有效分配要求：

- `AssignmentRecord.active == True`。
- `authorization_state` 属于 `recorded/authorized/approved/human_approved/operator_approved` 等有效状态。
- 同一 `(timestamp, plan_id, version)` 内统计重复分配。

D6 只统计分配结果，不产生重分配建议；`AssignmentPlan` 版本有效性仍由 D3/main 控制链路负责。

### 3.5 降级指标

基础降级：

```text
failover_time = mean(t(degraded_stable) - t(central_failure))
consensus_rounds = mean(consensus_rounds event values)
degraded_completion_rate =
  degraded_task_completed / (degraded_task_completed + degraded_task_failed_or_cancelled)
```

D4 active/passive 扩展已实现 P1 基线：

```text
active_degradation_count
active_degradation_precision
unnecessary_active_degradation_count
passive_failover_count
secondary_node_takeover_count
secondary_reassignment_count
d4_reassign_pending_count
distributed_fallback_count
failover_active_window_delta_s
```

当前识别来源包括 `EventRecord.event_type`、`metadata.mode/degradation_mode`、`metadata.action`、`metadata.assignment_phase`、`metadata.fallback_type`、D7 reject reason 和 D4 CSV loader。`metadata["trigger_reason"]` 等触发原因会进入 `EpisodeMetrics.metadata["trigger_reason_distribution"]`。

已补 P1 最小主动降级必要性口径：

```text
active_degradation_precision
unnecessary_active_degradation_count
```

D6 只在 D4/main 写入可分类的 `review_label`、`active_degradation_necessary`、`post_window_outcome` 或 pre/post risk/window 后验字段时计入 precision 分母；缺少标签时 `active_degradation_label_count=0` 且 precision 输出 unavailable/JSON `null`，只保留 `active_degradation_count`。

### 3.6 末端指标

```text
terminal_association_accuracy
terminal_id_switch_count
ambiguous_fov_event_count
friend_overlap_hold_count
time_to_terminal_lock
terminal_lock_count
multi_view_consensus_rate
cross_view_conflict_count
duplicate_terminal_lock_count
```

当前来源：

- `TerminalRecord` 中的 `decision_state`、`local_track_id`、`assigned_global_track_id`、`expected_global_track_id`、`association_correct`。
- `EventRecord` 中的 `terminal_lock`、`terminal_fov_entry`、`terminal_ambiguous_fov`、`friend_overlap_hold`、`multi_view_consensus_result`、`cross_view_conflict`、`duplicate_terminal_lock`。
- Blocks replay 的同帧多相机 bbox/label metadata，可生成 multi-view consensus/conflict 基线事件。

D5 仍然负责身份确认和 `global_track_id` 合同；D6 不重绑、不改写本地或全局 ID。

### 3.7 二级视角与侦察云台指标

```text
secondary_network_joint_full_view_frame_rate
secondary_network_mean_coverage_ratio
secondary_visible_target_union_ratio
secondary_single_camera_full_view_frame_rate
secondary_detect_count
projection_valid_rate
geometry_gate_pass_rate
registered_candidate_count
stable_cross_view_registration_count
not_registered_count
cross_view_association_count
secondary_detect_available_but_not_registered_count
cue_pointing_error_count / mean_deg / rmse_deg / max_deg
gimbal_pointing_error_count / mean_deg / rmse_deg / max_deg
```

当前来源：

- `EventRecord`/`LinkRecord.metadata` 中的 `secondary_node_type/node_type/camera_node_type`，规范化为 `fixed_downlook_secondary`、`mobile_recon_gimbal` 或 `secondary_network`。
- main/D4/D5 写盘的覆盖/FOV 记录，例如 `covered_target_ids`、`covered_target_count`、`coverage_ratio`、`joint_full_view`、`single_camera_full_view_count`。
- D5 跨视角事件，例如 `d5_cross_view_association`、`cross_view_association_count`、`multi_view_consensus_result`。
- D5 注册缺失事件，例如 `secondary_detect_available_but_not_registered_count`、`detect_available=True` 且 `d5_registered=False`。
- D5 detect-to-registration 校准字段，例如 `projection_valid_rate`、`geometry_gate_pass_rate`、`registered_candidate_count`、`stable_cross_view_registration_count`、`not_registered_count`，以及 reject/outcome reason `not_all_targets_visible`、`network_union_incomplete`、`projection_invalid`、`geometry_gate_rejected`、`stability_window_failed`、`no_global_binding`、`stale_or_missing_recon_cue`、`registered_to_global_track`。
- cue/gimbal 指向误差字段，例如 `cue_pointing_error_deg/rad`、`gimbal_pointing_error_deg/rad`、`pointing_error_deg/rad`。

归一化口径：

- network joint full-view 先按 frame 聚合二级网络覆盖集合，再除以实际 target count，不从 `2v2/5v5` 场景名推断目标数。
- mean coverage ratio 使用实际 target count；只有日志显式给出 per-frame ratio 时才直接消费 ratio。
- single-camera full-view rate 使用 camera-frame 分母；分母来自日志显式 camera frame count 或实际 camera count，而不是场景名。
- `EpisodeMetrics.metadata["secondary_sensing_node_type_metrics"]` 保留 node-type 级指标，报告中对比固定俯视二级节点和机动高空侦察云台节点。

D6 只消费 main/D4/D5 写盘日志，不下发 cue、不控制云台、不触发接管/重分配。

2026-07-08 `p1_d4d5_mobile_recon_20260708_055948*` 是历史 mobile recon stress 批次，可作为 D6 已能消费 `mobile_recon_gimbal`、coverage、bbox、gimbal 和 funnel 字段的旧证据。

2026-07-08 registration calibration v2 历史基线已验证 D6 侧消费口径：

- 输出目录：`research_modules/airsim_runtime/outputs/p1_d4d5_registration_calibration_runtime_v2_20260708*`。
- D6 bundle：`d6_airsim_calibration/airsim_calibration_records.csv`、`airsim_calibration_summary.csv`、`airsim_calibration_summary.json`、`airsim_calibration_report.md`。
- 场景：single seed，3 case；height 200 m，FOV 110 deg，secondary_count 3，detection backend 为 `simGetDetections`。
- 关键结果：`projection_valid_rate=1.0`；`geometry_gate_pass_rate≈0.474`；stable cross-view registration 为 51/55/53；cross-view association 为 4/4/5；degradation case `not_registered_count=35/35`；full-view mean≈0.048，best≈0.143；coverage mean≈0.771。
- 结论：D6 报告链路已能输出 projection/gate/stable registration/not-registered/funnel/D7 reject；剩余是更多真实 AirSim 多 seed/N-v-N 数据和 review labels，用于形成长期趋势。D6 记录该结论为离线评估状态，不参与 D4/D5/D7 控制或云台调度，也不从 `2v2/5v5` 场景名推断规模。

### 3.8 通信指标

```text
cross_node_latency_ms
message_drop_rate
out_of_order_count
stale_track_update_count
video_metadata_delivery_rate
bbox_delivery_rate
consensus_latency_s
```

当前来源：

- `LinkRecord`。
- 带通信字段的 `EventRecord.metadata`。
- Blocks `blocks_sensor_observations.jsonl` 的 `communication` 字段。
- Blocks frame image/bbox metadata 生成的 video metadata 和 bbox delivery 样本。

推荐保留字段：

```text
source_node_id
target_node_id
relay_node_id
link_type
message_type
sequence_id
sent_timestamp
received_timestamp
measurement_timestamp
arrival_timestamp
payload_kind
delivered
stale_after_s
```

### 3.9 D7 gate、visual PNG switch 与拦截统计

D6 已能从 D7 `control_commands.csv`、`guidance_records.csv`、`guidance_summaries.json`、`intercept_summary.json` 读取：

```text
camera_quality_gate_pass_rate
los_quality_gate_pass_rate
maneuver_margin_gate_pass_rate
terminal_switch_allowed_rate
visual_png_switch_count
terminal_takeover_rate
terminal_switch_reject_count
mode_switch_count
terminal_contract_reject_count
intercept_success_count
collision_intercept_count
range_intercept_count
time_to_intercept_s
min_range_m
gate_reject_count
```

`terminal_switch_allowed_rate` 的分母只包含带有 `terminal_switch_allowed` 字段的 D7 control command。空缺字段不进入分母。

`visual_png_switch_count` 的来源包括显式 `visual_png_switch/vision_png_switch/d7_visual_png_switch` 事件，或 `guidance_law=png_vm/png_ttc` 且伴随 `mode_switch=True`、`terminal_mode_entered=True`、`mode=vision_terminal/visual_png/vision_png` 的 D7 记录。

`terminal_takeover_rate` 按 unique `(resource_id, target_id)` pair 统计，证据包括 `terminal_locked=True`、`terminal_switch_allowed=True`、`vision_terminal` mode、`terminal_mode_entered=True`，或 `guidance_law` 为 `png_vm/png_ttc/los`。`terminal_handover_pending` 和 `detection_seen` 只能说明候选可见，不能单独算 takeover。

### 3.10 安全指标

```text
constraint_violation_count
human_override_count
```

安全事件是一级输出。即使其他指标良好，也不能把安全约束触发或人工覆盖事件用总体成功率平均掉。

## 4. 已实现输入适配器

| 适配器 | 输入 | 当前状态 | 边界 |
|---|---|---|---|
| `load_episode_log_jsonl()` | 标准化 `truth_summary/track/assignment/event/link/terminal` JSONL | 已实现并测试 | 未知 record type 直接报错，避免 schema drift 静默进入报告 |
| `load_blocks_replay_jsonl()` | `blocks_frames.jsonl`、可选 `blocks_sensor_observations.jsonl` | 已实现并测试 | 只读文件，不 import AirSim，不调用 runtime API |
| `load_main_episode_bus_metrics()` / `load_main_episode_bus_metric_files()` | `main_episode_bus_metrics.json`、`main_episode_bus_contract_metrics.json` | 已实现并测试 | 只还原已写盘 `EpisodeMetrics`；不运行 AirSim、不合并控制结果 |
| `load_d4_active_degradation_decisions()` | D4 active-degradation CSV | 已实现并测试 | 只消费已写盘 review/window 字段；有 label/后验字段才计算必要性，不从事件名判定 |
| `load_d7_intercept_outputs()` | `control_commands.csv`、`intercept_summary.json` | 已实现并测试 | 只离线评估 D7 输出，不发控制 |
| `load_d7_guidance_timeseries()` | `guidance_records.csv`、`guidance_summaries.json`、D7 control/intercept 输出 | 已实现并测试 | 保留 D4/D5 state、plan/version、guidance law 和 reject reason metadata |
| `load_airsim_calibration_records()` / `AirSimCalibrationReportGenerator` | AirSim batch/seed/case 目录中的 `d4d5_stress_metrics.json`、`airsim_blocks_summary.json`、`main_episode_bus_metrics.json`、`main_episode_bus_contract_metrics.json` | 已实现并测试 | 只读已写盘文件；按真实 count 字段、settings FOV 和 metadata 分组，不从场景名推断规模 |

## 5. 已完成接入与 main runtime bus 剩余条件

当前 D6 已能消费 D4/D5/D7 产物。完整 integrated episode metrics 仍取决于 main runtime 的写盘和汇总接线，但 D7 真实执行结果的 main/orchestrator 合并已经完成一条主线。

截至 2026-07-07 的已完成接线：

- 真实 AirSim D7 执行后，main/orchestrator 从 `control_commands.csv` 与 `intercept_summary.json` 提取执行结果并合并进正式 `main_episode_bus_metrics.json`。
- 执行前的合同检查口径保留为 `main_episode_bus_contract_metrics.json`，用于诊断 D3/D4/D5/D7 gate 与合同拒绝，不再覆盖正式执行指标。
- 正式指标中的 `intercept_success_count`、`collision_intercept_count`、`range_intercept_count`、`terminal_contract_reject_count`、`gate_reject_count`、`guidance_law_counts` 等以执行后合并结果为准。
- D6 仍然只消费日志/CSV/JSON/metrics 文件；不订阅 runtime bus，不触发 replan、failover 或 guidance。

已具备 D6 侧消费能力：

- D4：可读取 active-degradation CSV；可从事件 metadata 中识别 active/passive、secondary takeover/reassignment、distributed fallback、D4 reassign pending、触发原因、review label、trigger/decision timestamp、selected coordinator、coverage cell 和 pre/post window 字段。
- main bus：可读取正式 execution `main_episode_bus_metrics.json` 与 raw contract `main_episode_bus_contract_metrics.json`，保留 `metric_scope`、seed/scenario/实际规模字段、D7 guidance/intercept 指标和 reject reason metadata。
- D5：可通过 `TerminalRecord`、terminal/multi-view event、Blocks bbox/camera metadata 计算末端准确率、ID switch、lock、歧义、friend hold、多视角一致和冲突；可消费 cross-view association、secondary detection available but not registered 和 cue/gimbal pointing error metadata。
- D7：可读取 control/guidance/intercept CSV/JSON，计算 gate、visual PNG switch、terminal takeover、模式切换、拦截结果和 reject metadata。
- Blocks CV：可从 `blocks_frames.jsonl` 与 `blocks_sensor_observations.jsonl` 构建 truth summary、规模字段、视觉检测、terminal records、video/bbox link records 和通信链路样本。

P0/P1 状态（2026-07-12）：

- 无 P0 blocker。D6 离线主线、`id_switch_count` 显式输出、实际规模归一化、main bus metrics loader、D4/D5/D7 写盘消费和二级侦察指标消费均已具备。
- D6 terminal delivery 指标、availability-aware replay 和 baseline/candidate 对照 bundle 已闭合；2v2 candidate `20/20` 达到非退化验收。M5N2 同几何/同窗口 paired 对照、`png_ttc` 多 seed、dropout 矩阵、trend coast 默认 profile 决策及长期趋势仍开放。
- 剩余 P1 不是 D6 在线控制职责，而是真实 episode 写盘、自动汇总、paired 验收和长期趋势报告的持续性要求：

- 真实 episode 需要持续写出 D4 `review_label`、`trigger_timestamp`、`decision_timestamp`、`selected_coordinator`、`coverage_cell` 和固定 pre/post window 字段；D6 已能消费这些字段并计算主动降级必要性/精度。
- 同一 episode 目录仍需稳定聚合 Blocks、D4、D5、D7 和 D6 标准化 JSONL/CSV/JSON，并保持同一 episode clock；D6 loader 本身不会扫描 runtime bus、启动 AirSim 或补写上游日志。
- D5 terminal association、cross-view conflict、duplicate lock、friend overlap hold、validation label 等真实 AirSim 事件应持续进入 D6 可读记录；D6 已有指标和 Blocks metadata 基线。
- AirSim 报告已能把 `mobile_recon_gimbal` / `fixed_downlook_secondary` 的 50m/200m coverage、detect-to-registration funnel、coverage funnel、baseline/enhanced、bbox 和 cue/gimbal 指向指标纳入多 seed 自动汇总；长期趋势仍需要 main 持续产出更多 5v5/N-v-N 批次。
- main runtime P1 D4/D5 calibration sweep 已自动调用 D6 `AirSimCalibrationReportGenerator` 生成标准 records/summary/Markdown bundle；D6 当前重点是保持多 seed 自动汇总口径稳定，沉淀 coverage/funnel/gimbal、projection/gate/stable registration、not-registered、D7 guidance reject 和 `trend_key/evidence_path` 长期趋势，统计 active degradation precision，并按真实 `drone_count/resource_count/target_count/camera_count` 做 actual scale 分组。
- 多 seed、5v5/N-v-N 和非默认 episode 需要继续保持 `metric_scope=execution/contract` 双口径，正式指标采用执行后 metrics，contract metrics 仅用于诊断；D6 已能直接读取两类 main bus metrics JSON，报告分组已按 `metric_scope + seed + scenario_group + scale` 实现，不从场景名推断规模，并在 metadata/Markdown 中保留 reject reason 分布。

2026-07-12 D6 owner 当前回归为 `88 passed`，另有 1 条本机 matplotlib `Axes3D` warning。coalition commit、终端 contract/control/switch/physical 四层验收、pair/target/coalition 分层 physical success、detect/coast、PNG delivery 诊断、main-summary fallback 及 P1 多来源统一报告均已实现并保持回归。2v2 candidate 的 `20/20` 只闭合本轮非退化门槛；M5N2 candidate 与历史 baseline 不可直接配对，仍须按相同几何、窗口和 seed 验收。`physical_intercept_count` 没有物理 evidence 时保持 unavailable，有物理 evidence 且未命中时为 0。

## 6. 开源/外部项状态

| 项目 | 当前状态 | 未实现原因 | 缺少条件 | 优先级 |
|---|---|---|---|---|
| Stone Soup metrics | 没有 Stone Soup import、对象转换器或 metric generator 调用 | 保持默认依赖轻量；D1/D2 track/truth 尚未冻结到 Stone Soup 类型 | 版本锁定；D1/D2 adapter；GroundTruthPath/Track/Detection 映射；坐标和门限合同；CI 样例 | P2 |
| OSPA/GOSPA | 文档有公式，`EpisodeMetrics` 未输出字段 | 需要帧级 truth/estimate set 序列和 cutoff/order | 稳定集合序列；匹配门限；目标 birth/death/遮挡规则 | P2 |
| CLEAR MOT/MOTA/MOTP 标准库对照 | py-motmetrics 1.4.0 隔离 adapter 已实现 IDF1/MOTA/MOTP；真实 backend 仅有 2 帧 smoke，默认环境可无依赖 | 只消费冻结 offline truth/association schema，不覆盖系统级指标，尚未形成真实 replay benchmark | main/D2/D5 持续产出 `msm-offline-mot-v1` fixture；距离/IoU 门限由 fixture metadata 固定 | P2 adapter 已实现，benchmark 未完成 |
| HOTA | unavailable；py-motmetrics 1.4.0 不提供该指标 | 需要支持 HOTA 的外部 evaluator 与完整帧级检测、关联和身份评估表 | 稳定 frame-level 输出；occlusion/reappearance 规则；TrackEval 等 evaluator | P2 |
| AirSim 原生 recording replay | 未实现通用 parser | main 已提供更直接的 Blocks JSONL；原生 recording 字段、坐标、相机版本差异大 | 原生 recording 样例；schema 版本；NED/相机/时间轴映射；测试容差 | P2 |
| Live AirSim replay/API | 未实现，且不作为 D6 默认能力 | D6 边界是 offline-only | 如未来需要，也应由 main runtime 导出日志，D6 仍只读文件 | 禁止在线控制 |
| SCRIMMAGE metrics bridge | 未实现 | 当前仿真主线是 AirSim Blocks 和合成日志；仓库没有 SCRIMMAGE 输出样例或 message schema | SCRIMMAGE episode 输出；agent/resource/target ID 映射；通信事件字段；episode clock 对齐 | P3 |

## 7. 批量统计与报告

D6 报告生成器当前输出：

- `episode_metrics.csv`：每个 episode 一行，包含规模字段、`scenario_version`、`standard_mapping_version`、`standard_metric_family_summary`、所有 `EpisodeMetrics.metric_names()` 和 metadata JSON。
- `summary_metrics.csv`：全局与 `metric_scope + seed + scenario_group + scale` 分组统计。
- `standard_metric_mapping.csv`：输出固定版本 `cuas-standard-map-v1` 的标准映射行，字段为 `engineering_metric/standard_metric_family/standard_sources/implementation_status/evidence_requirement`。
- Markdown 报告：中文说明、规模范围、场景分组、`Standard C-UAS Mapping` 表、固定俯视二级节点 vs 机动侦察云台节点对比表、汇总表、reject reason 分布和图表链接。
- PNG 图表：`detection`、`tracking`、`assignment`、`degradation`、`terminal`、`secondary_sensing`、`communication`、`guidance`、`safety` 和 selected metric distributions。
- AirSim calibration bundle：旧 records/逐 seed summary 文件保持不变；新增 cross-seed aggregate CSV、paired comparison CSV、aggregate JSON/Markdown。main 必须显式写 `comparison_role=baseline|enhanced`；配对键包含稳定 `scenario_group`、去除运行 seed 参数后的 `scenario_version`、实际 N/M/camera count、几何、backend 和 seed，case_name 只审计。active-degradation count/precision/label_count/unnecessary 优先消费 d4d5 stress 显式字段，再 fallback main metrics。

2026-07-10 的 2v2 execution 回灌复核是历史基线，用于固定以下读取优先级：正式 `main_episode_bus_metrics.json` 为执行口径，`main_episode_bus_contract_metrics.json` 为合同诊断口径，`airsim_blocks_summary.integrated_result.metrics` 仅是可能过时的历史快照，不进入 D6 calibration record。该历史基线的正式 execution 为实际规模 `2/2/2/2`、成功拦截 `2/2`、视觉 PNG 切换 3 次；旧 Blocks 快照仍为 `3/3/2/0`，该上游摘要一致性由 main runtime 负责。

历史 10-seed 基线 `p1_gap_closure_2v2_multiseed_20260710_seed001..010` 验证了 full-flow execution cross-seed 行可完整包含十项拦截指标，并输出 `intercept_success_count sum=18`、`opportunity_count=20`、`rate=0.9`，collision/range/abort 为 `18/0/2`。这些数值只保留为当时场景的历史基线，不代表 2026-07-11 M=5、N=2 SimpleFlight 诊断结果；报告由 D6 离线读取 summaries 生成，不启动 AirSim、不发控制。

统计口径：

```text
mean
sample_std
stderr = sample_std / sqrt(N)
ci95 = mean +/- 1.96 * stderr
median
p05 / p95
```

偏态或长尾指标，例如 `id_switch_count`、`constraint_violation_count`、`terminal_switch_reject_count`，在正式结论中仍需要 bootstrap 或非参数方法复核。当前实现先满足回归和工程比较。

## 8. P1 最终开放项

1. 建立长期真实 multi-seed 趋势：按冻结 scenario/version/profile/actual scale 持续生成跨提交趋势、门限稳定性和 bootstrap 置信区间，不把单批次结果外推为长期结论。
2. 完成真实逐时刻 producer schema：优先补 D3 plan history/churn，并统一 episode clock、version/epoch、source provenance 和 availability；最终 snapshot 不能替代逐时刻记录。
3. 治理跨批次失败原因：稳定 reason taxonomy、字段版本和 unknown/unavailable 口径，避免不同 producer 对同一失败重复计数或重命名。

以上三项是当前 D6 P1 的唯一开放主线。下列内容保留为历史专项规划，不改变本节最终优先级。

### 2026-07-12 PNG Delivery 历史验收规划

1. 用同一 z=-30 m、35 s 高净空几何、相同运行窗口和相同 seed 运行 M5N2 baseline/candidate；分别统计 target、active-primary pair 和 coalition completion，不跨层回填。
2. 独立运行 `png_ttc` 多 seed，持续写出并汇总 area jump、bbox clipping、not expanding 和 TTC out-of-range 拒绝。
3. 固定锁定后 dropout 时刻覆盖 1-5 帧；1-2 帧核对有界预测，3-5 帧必须按 0.25 s 上限 fail-closed，且 online truth use 和错误身份绑定保持 0。
4. trend coast 只有在错误绑定为 0、命令跳变不恶化、物理成功不下降时才可进入默认 AirSim profile；否则保持 candidate-only。
5. 所有新批次稳定写出 profile、filter state/reason、TTC reject、soft/coast elapsed、lock、visual mode、三轴速度命令和四层结果；缺字段保持 unavailable。

### 2026-07-11 M 对 N 评估框架

专项框架见 `subagent_reviews/D6_M_TO_N_EVALUATION_FRAMEWORK_REVIEW.md`。D6 将四条研究路线 `independent/simultaneous/sequential/hybrid_primary_reserve` 按中心正常、二级接管、完全无中心三个层级评估，并覆盖几何退化、时间同步、通信异常和成员失效。所有新增指标按 `frame/member/wave/coalition-version/target-episode/episode/batch` 分层聚合，继续区分 `unavailable/null`、证据完整的真实 `0` 和 `not_applicable`。

2026-07-11 已冻结并实现 `TargetDemandRecord/CoalitionRecord/ArrivalRecord`，扩展 assignment/terminal coalition/member 字段，接入 JSONL loader/writer、`EpisodeMetrics`、episode CSV、batch summary 和 Markdown。已实现 demand/unmet slots、formation/reconfiguration、arrival/wave/hybrid、geometry rejection、canonical duplication/cross-node IDSW/common-information rejection、planned/authorized/erroneous lock、same-resource continuity、成员生命周期、通信预算和安全聚合；既有 RMSE/NIS/NEES 指标继续复用 track/governance 路径。探测 POD/miss/FAR 现同时要求 truth opportunity 与离线 match/miss 配对裁决；仅有 truth 列表或 truthless center tracks 时统一 `None/unavailable`。

`duplicate_terminal_lock_count` 保持通用同帧多资源观测计数，不再被错误锁覆盖；`erroneous_duplicate_lock_count` 仅计 `k=1`、版本冲突和超需求。规范 `center_replan_request_created/deduplicated/ack_no_change/applied/expired` 事件已接入请求数、去重数、no-change、applied、expired、pending dwell 与收敛时间；缺事件为 unavailable。当前 P1 合同层已有 CV 8/10、二级/分布式 commit 和 missing-ACK fail-closed 实测证据；2026-07-12 的 2v2 candidate 已达到 `20/20` 非退化验收，未闭合的是同几何 M5N2 paired 物理/联盟验收和长窗口实验矩阵，不是 D6 聚合合同。第 9 节 P2 项只作为隔离 benchmark，其中 SCRIMMAGE 保持 P3。

### 2026-07-11 四导引律证据边界

`p1_guidance_four_law_smoke_20260711` 已验证 main 的 guidance law 回灌和 D6 同 seed
配对链路。当前 CSV 有 21 条指标配对行，但每行 `pair_count=1`，只覆盖 seed 7；四种
导引律在 2 秒窗口内均 timeout。PNG VM/TTC 的末端切换允许率约为 0.762/0.810，最小
距离约为 2.812/2.798 m。该批次只作为接口、写盘和指标口径验收，不作为最终命中率或
算法排序证据。

四律对照的 P1 验收仍要求：使用相同场景版本、实际 N/M/camera count、初始几何和
seed 集合；延长 `intercept_max_duration`；至少形成多个独立 paired seeds；同时报告
timeout、成功/abort、最小距离、切换允许率、接管率和 gate reject 原因。只有样本量满足
要求后才输出 effect size/bootstrap CI 和算法优劣结论。

1. 场景库接口已完成；下一步由 main/CI 使用稳定的 `scenario_group/version`、tags、difficulty、expected failure modes、actual scale、seed matrix 和 evidence path 调度真实批次，D6 再生成跨提交趋势、阈值回归和证据完整性摘要。
2. CV 5v5 的 D1-D3 联合聚合：在同一 episode clock 下汇总 D1 detection/fusion/latency/covariance、D2 association/continuity/ID switch 和 D3 assignment/version/hysteresis 指标，形成从感知到分配的 funnel。D6 只消费 main 写盘的稳定 schema，不从 truth name、场景名或后验结果重建在线决策。
3. YOLO/MOT 的 recall、local-ID continuity、cross-view rate、pipeline latency 和 CPU/GPU budget 已实现；下一步消费 D5 写盘的模型/权重版本、输入分辨率、目标像素尺度、throughput、内存、drop/fallback 字段，形成更完整的 accuracy-latency-budget 对照。D6 不加载 `best.pt`、不运行 YOLO，也不把缺失性能样本记为 0。
4. COURAGEOUS/MDPI/OCEF 完整标准化报告：在 `cuas-standard-map-v1` 基础上补测试阶段、复现纪律、evidence index、场景覆盖矩阵、限制条件和外部审计说明，并把 D1-D7 指标映射到统一中文报告模板。
5. 长期多 seed 对照：现有 cross-seed aggregate、严格 paired comparison、effect size 和 bootstrap CI 只需用真实成对 5v5/N-v-N 批次持续验收；missing seed、单 pair、无 review label 和 read-only unavailable 继续保持不可推断状态。
6. D4/D5 长期趋势与真实标签：持续跟踪 coverage/funnel/gimbal、projection/gate/registration、D7 reject 和 active-degradation review/window；`active_degradation_precision` 只使用 main/D4 写盘的真实 review label 或后验 outcome/risk。
7. execution/contract/evidence availability 已完成，后续仅作为 schema 回归项：正式 execution、raw contract、各自 evidence path 和 availability 状态不得互相覆盖，不再重复扩展同义拦截字段。

## 9. P2 下一步

1. 帧级匹配表：定义 D1/D2/D5 的 frame-level truth/detection/track export，包含 timestamp、truth_id、global/local track ID、position/IoU/distance、occlusion/reappearance 状态。
2. 外部 MOT 对照：py-motmetrics adapter 代码与 2 帧离线 smoke 已完成；IDF1/MOTA/MOTP 在冻结 schema 上可用，但真实 benchmark 尚未完成。下一步用真实冻结 replay 校准距离/IoU 门限、遮挡和重现规则。TrackEval/HOTA 保持未实现 optional，不能用 py-motmetrics 结果伪造 HOTA，也不能替换默认在线关联路径。
3. Stone Soup/OSPA 对照：在 D1/D2 对象映射和版本锁定后接入 Stone Soup metrics 与 OSPA/GOSPA。
4. Bootstrap/非参数 CI：在真实多 seed 数据规模足够后，为偏态指标提供可选统计方法。
5. SCRIMMAGE bridge：仅当 AirSim 多机规模或通信建模不足以回答实验问题，并且已有真实 SCRIMMAGE 样例和 schema 时作为 P3 可选项推进。
6. AirSim 原生 recording parser：只有在 Blocks JSONL 不能满足评估需求时，才补通用 recording parser。

## 10. 验收命令

从仓库根目录运行：

```bash
pytest -q research_modules/d6_evaluation_metrics/tests
git diff --check -- research_modules/d6_evaluation_metrics subagent_reviews/D6_*
```

文档验收点：

- 明确 D6 只消费日志，不参与控制。
- 明确 `id_switch_count` 是 D2/D6 强制显式指标。
- 明确指标按实际 `drone_count/resource_count/target_count/camera_count` 归一化。
- 明确 D4/D5/D7 AirSim 产物的 D6 侧 loader 已实现；D7 real execution metrics 已由 main/orchestrator 合并进正式 `main_episode_bus_metrics.json`，raw contract metrics 保留为诊断文件。
- 明确 P1 合同层和联盟 lifecycle 指标已完成，但物理命中、长期场景库与 CI 趋势仍为 P1。
- 明确 py-motmetrics 当前只完成 2 帧离线 smoke；IDF1/MOTA/MOTP 可用、HOTA 不可用，且默认在线路径与 D6 本地主线未替换。
- 明确 Stone Soup、AirSim replay、SCRIMMAGE 等开源/外部项的实际未实现状态、原因和缺少条件。

## 11. 2026-07-12 P1 汇总接口实施状态

本轮新增 `p1_system_evidence.py`，执行边界仍是“消费而不控制”。D2 六难度、D3 membership/version churn、D4 episode communication、D5 native MOT admission 和 D7 per-primary 四层漏斗，已进入同一版本化 CSV/JSON/中文 Markdown/PNG 输出。

已完成：

1. 输入接受 JSON 路径、mapping、dataclass/to_dict 对象或记录序列，不导入在线 producer。
2. 每个指标独立携带 availability；缺失物理拦截时不会由 mode switch 或 control allowed 推断。
3. D5 按 ByteTrack/BoT-SORT backend 分组，IoU fallback 与 native active 分开。
4. D2 按 `scenario_difficulty` 分组，保留 non-discriminative 标记。
5. D3 分开统计 plan、coalition version、epoch、membership change/hold，并保留 per-primary/arrival 配置。
6. D4 从 tick 序列统计 ACK、lease、epoch、owner、commit/fail-closed；`owner=None` 阶段作为真实 owner transition 保留。
7. D7 四层只消费同名持久化证据，禁止跨层回填。
8. truth identity 不写入汇总，显式在线 truth 使用会使 truth policy 失败。

后续 P1 由 main 提供真实 AirSim 多 seed 路径并调用 CLI；D6 只校验 schema、availability、分组和报告结果。没有真实 producer summary 时，相应 source manifest 必须保持 unavailable。

## 12. 真实 AirSim Native MOT 专项（2026-07-12）

D6 已离线消费 `preflight_rows.json`、`range_rows.json` 和 `confirm_rows.json`，生成 `outputs/p1_native_mot_20260712/` 下的中文 CSV/JSON/Markdown/PNG。证据固定分为 32 帧 discovery、实际 42 帧的约 40 帧 range precheck、102 帧 confirmation，禁止跨等级池化。

本轮结果：20 m confirmation 中 ByteTrack/BoT-SORT 均为 native rate 1.0、continuity 1.0、IDSW 0、fallback 0；P95 分别约 8.292/18.232 ms。但离线 precision/recall 仅约 0.324/0.293，均未准入。30/50 m precheck 无接受检测。下一步由 main/D5 核对离线 truth 框、IoU/几何门限和时间对齐后复测；D6 保持被动消费，不降低准入阈值。

## 13. Replay/Execution 合并计划状态（2026-07-13）

已完成 `d6.execution-metrics-merge.v1` 纯函数接口：

1. integrated replay 保留离线探测、跟踪、分配等指标；main episode bus 对终端、cross-view、在线 truth、合同/控制/切换和物理执行指标具有优先权。
2. 每个执行指标同时记录 replay 值、execution 值、availability、source path 和最终 selected source；显式 `0` 是有效证据，缺字段或 `None` 是 unavailable。
3. `persisted_frame_count` 和 `warmup_inclusive_frame_count` 分开保存，不进行 `+1` 或其他隐式推断。
4. main 后续只需调用合并函数并写盘；D6 不导入 AirSim runtime，也不修改在线 episode 状态。

后续回归要求：真实样本 replay `cross_view_association_count=0`、main bus `=55` 时最终值必须为 55；execution 缺失时不得制造执行值；帧数两层必须分别有 provenance。

## 14. 三维规模化 D1/D2 离线制品接入（2026-07-20）

### 已完成

1. 新增版本化 D6 公共记录：D1 consistency adapter、D1 sensor-range record、D2 identity
   adapter、truth-isolated episode 和 batch summary。
2. D1 入口校验公开 result schema、record schema、内部 content digest、record count、
   `truth_usage=offline_evaluation_only`、aggregation provenance 和逐记录内容一致性。总体
   metric 由 D1 原样保留，sensor/range 统计只基于 D1 公开 aggregation records。输入和
   输出以 `d2_lineage_mapping` 为规范字段；旧 `canonical_mapping` 显式兼容，双字段冲突
   或可用 truth metrics 缺映射摘要时拒绝。
3. D2 入口校验 evaluation/metrics/policy schema 和四类来源摘要。D6 不读取 frame mapping
   来猜测身份，只保留 D2 已发布的指标；文件输入缺任一 expected source hash 时拒绝，在线
   真值隔离或有效 frame/truth-frame 证据不完整时指标和 truth counts 均 fail-closed。
4. episode context 显式携带 scenario/version/run/seed 和实际 target/resource/recon/camera
   数量。D1 provenance 或 D2 episode ID 不一致时拒绝合并。
5. batch 按 scenario/version/actual scale 分组，distinct seed 计算描述统计与固定随机种子
   percentile bootstrap。单 seed 只给描述统计。
6. 报告输出逐 seed CSV、D1 sensor-range CSV、聚合 JSON 和中文 Markdown；所有输出均
   显式包含 `id_switch_count`，缺证据时值为空且原因可追溯。

### 验证

2026-07-20 使用最小公开制品 fixture 覆盖 5/20/50/100/200，专项 `14 passed`，D6 全量
`334 passed`。测试验收为接口、D1 lineage 新字段/旧字段/冲突/缺失、文件/来源哈希、
availability、假零拒绝和规模分组正确；未运行 AirSim，未运行
正式 20 个未见 seed，未验证任何工程阈值。

### 后续计划

1. 当前工作树 main-owned reporting 已持久化 D1/D2 公开制品并调用 D6 episode/batch builder；
   D6 不接入在线总线，也不在本任务修改该接线。
2. main 仍需冻结正式 producer 文件名、manifest key 和跨制品 source hash 关系，并将 D6
   结果纳入最终统一 scalable 3D 总报告，而不复制 producer 私有 schema。
3. 在 5/20/50/100/200 正式多 seed 数据具备后，报告 sensor/range RMSE、NEES、NIS 与
   IDSW/continuity/duplicate 的置信区间和不可用原因分布。
4. 在以上证据完成前，GAP 状态为“D6 适配合同与当前工作树接线已闭合、正式多 seed
   性能验收和最终统一报告仍开放”。
