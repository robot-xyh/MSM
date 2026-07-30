# D3 实现差距审计

## 2026-07-30 来源独立评价状态

assignment-aware A1 候选过去只有同一生成体系的 TRAIN/VALIDATION 开发证据，缺少新来源
的一次性只读评价边界。模块级工具缺口现已关闭：D3 新增固定 bundle 三摘要、固定源码
清单、固定 seed/场景和固定机器门的严格评价器。评价器不暴露训练、优化器、检查点选择、
归一化重拟合、阈值修改、计划发布或运行辅助接口。

输入检查绑定 main 的冻结生成 schedule SHA、clean-source 标记、100/100 episode、
有限状态、在线真值使用 0、匿名数据 schema、60/20/20 seed 子组和开发/正式 seed 零重叠。
逐帧输出同时保留 R0、模型候选、安全投影后的有效结果和全部拒绝原因。拒绝帧必须恢复
exact-R0 矩阵与绑定；重复资源、硬禁边、多机需求完整性和版本违规机器门均为零。

软件合同专项于 2026-07-30 完成 `17 passed`；D3 全量为
`640 passed, 1 skipped`，跳过项是可选 OR-Tools。状态是
`evaluator ready / evaluation not run`，不是模型泛化通过。新来源 seed `20000-20099`
尚未评价，正式 seed `1000-1019` 未读取，全部运行和正式准入权限为 false。

开放 P1：

1. main 只允许对已冻结的新来源执行一次评价，并保存唯一结果目录。
2. D3 不得在读取结果后修改 bundle、特征、归一化、教师、阈值或评价合同。
3. D6 需独立重算逐帧和聚合结果并复核校验和。
4. 只有来源独立预注册门通过后，才可另行预注册正式 holdout；当前不得启动。

本轮没有新增 P0。旧 A1 runtime ACK、物理窗口、同键 R0 和 production admission 缺口
继续保持开放，来源独立评价通过也不能自动关闭这些项。

## 2026-07-27 提交前状态

本次复核关闭两个模块内提交缺陷：A1 序列化候选过去只校验版本字段类型和内容摘要，现已
复算相对前序计划的连续版本；A1/隔离批处理过去只覆盖部分精确真值键，现已覆盖复合
truth/Actor/Object 身份键。对应负例均失败关闭。区域提示的严格后继、hold 硬禁边、
非等量规模和规则回退未发现新的 P0。

D3 全量收集 563 项，结果为 `562 passed, 1 skipped`；skip 为可选 OR-Tools。当前建议
作为独立 D3 提交，但不能标记 A1/A2 物理闭环完成。

仍开放 P1：A1 需要 clean commit 上冻结输入的可辨识 20-seed 候选，并由 main 接入发布、
运行 ACK、完整物理窗口和同键 R0；A2 需要持久化非零安全区域动作、严格后继、owner ACK
及同键物理证据；真实非等量多 seed 参数与收益仍由 main/D6 校准。没有新增 D3 P0。

**模块**: D3 集中式资源-目标分配
**审计日期**: 2026-07-26
**审计依据**: 当前 `research_modules/d3_assignment_planner/` 代码、README、PLAN、docs 和 tests，2026-07-25 的 20-seed 多周期行为克隆影子评估，既有 2026-07-13 M5N2 40-case 报告，以及 `research_modules/airsim_runtime/outputs/p1_terminal_timing_funnel_10seed_20260715_m5n2_*/episode_006_full_flow/main_episode_bus/d3_plan_history.json` 的最新 20-case/3725-record 只读复核、main/D6/D7 物理结果汇总、`subagent_reviews/MAIN_IMPLEMENTATION_GAP_AUDIT.md` 和 `EVAL/FRAMEWORK_EVAL_P0_P1_P2_GAP_CONFIRMATION.md`。
**边界**: 本审计只覆盖离线科研仿真中的抽象资源-目标分配、版本化计划、终端反馈合同、D7 guidance binding、D6 记录导出和 AirSim dry-run 适配；不涉及真实飞控、硬件、火控、毁伤逻辑或绕过人工授权的自动处置。

## A1/C1/F1 学习证据装配 GAP

### P0 软件缺口

首次复核只关闭了 legacy v2 assist。进一步检查确认 v3 仍可被调用方自我晋级：
`save_model_bundle()` 接受调用方直接传入 `stage=qualified`、正向权限布尔和任意格式正确
的 64 位哈希；测试还可手工改写 manifest 后让 production loader 返回 loaded。字段内部
一致并不证明 held-out、运行采用、物理结果或 D6 外部审计真实存在。

该 P0 已关闭：

1. production writer 只生成 development/research bundle。caller-qualified admission 在
   创建目录和权重文件前拒绝，不留下半成品。
2. v2 和 development v3 继续支持 shadow。现有 bundle 的行为和文件摘要不变。
3. 手工 v3 清单即使通过 admission 和 promotion 字段校验，assist 仍返回
   `bundle_assist_evidence_assembler_unavailable`，不能进入模型加载或代价修正路径。
4. promotion 仍可保存影子比较结论，但不再是权限来源。规则回退、硬禁边、Hungarian、
   版本、stale 和 M-to-N all-or-none 合同均未改。

2026-07-26 定向 bundle 测试为 `21 passed`；D3 全量为
`465 passed, 1 skipped`。唯一跳过为可选 OR-Tools；既有 Matplotlib `Axes3D` 告警不影响
本结论。

### 四层状态

| 层次 | 当前状态 |
| --- | --- |
| loader/writer 软件能力 | development shadow 可用；caller-qualified writer 和手工正向 loader 已失败关闭；A1 选择后阶段 DTO/assembler 已实现，但 production bundle 正向 admission assembler 尚未实现 |
| development bundle | manifest/state/tree/binding SHA 分别为 `a9213d65...9314c0`、`e3da9fd5...f8e0b2`、`3c08e581...fee085`、`70aa1b0...542a8`；文件未修改 |
| 实际外部证据 | D6 旧 sidecar 只通过同帧离线分配比较；正式 20-seed/100-frame 为 0/20 eligible；runtime ACK、物理结果和 paired non-degradation 不可用；新 formal-scope auditor 尚无实际 A1 输出 |
| 正式 assist 权限 | `false`；现有 bundle assist 返回 `bundle_shadow_only`，A1/C1/F1 在 D3 条件上失败关闭 |

### D6 字段复用与缺失

| D3 需求 | 已有 D6 字段 | 缺失字段或实际条件 | owner |
| --- | --- | --- | --- |
| 数据、切分、零泄漏 | 跨模块数据审计含 D3 manifest/frames SHA、60/20/20 seed、保留 seed 泄漏 0、全样本审计 SHA | 精确 `split_hash`、训练源码摘要与目标 bundle 的联合绑定 | D3 assembler；D6 复核输入实物 |
| 模型/文件树 | 旧 sidecar 含 manifest/state SHA；formal-scope auditor 可重算 manifest/tree/file count/size | 旧 sidecar 标明 `bundle_files_rehashed=false`；实际 A1 tree 复核不存在 | main 提供 bundle；D6 审计 |
| 运行采用 | formal-scope auditor 可验证 assist 诊断和正的 `d3_learning_applied_count`；D3 已能验证选中计划发布和现有 runtime ACK 谱系 | 旧 sidecar runtime ACK unavailable；没有真实 A1 发布/确认及其制品树绑定 | main/D7 生产；D6 审计 |
| 物理结果 | formal-scope auditor 可检查物理指标 availability；D3 已能逐 binding 装配现有窗口证据 | 当前无干预后物理状态窗口；接口能力不能替代实际窗口 | main/D7 生产；D6 审计 |
| paired non-degradation | formal-scope auditor 可唯一配对同键 R0 并逐指标判断 | 当前实际值 unavailable；新结果必须覆盖 1000-1019 全部 20 个未见 seed | main 运行；D6 判定 |
| 晋级结论 | formal-scope audit 有 `verdict` 和 `evidence_admission_allowed` | D6 明确 `model_promotion.allowed=false`，也不强制 20-seed D3 门限 | D3 assembler/owner |

D6 新审计器可直接复用，不需要 D3 再造通用审计 schema。它目前只提供软件能力。正式 A1
execution plan/merge、同键 R0、实际 bundle 根目录和审计结果均未提供。

### 开放 P1

1. 当前冻结 development policy 在正式 20-seed/100-frame 输入上为 `0/20 eligible`。
   main 需提供重新训练或重新冻结的策略；D3 继续按既有资格和预注册边界评估，不降低安全
   或离散变化条件。
2. main/D7 需把选中 `AssignmentPlan` 接入真实 D3 发布总线，并为 1000-1019 生成版本化
   模型采用 ACK、后续状态和成对物理窗口。没有选中帧时整条链保持 unavailable。
3. D6 需输出实际 A1 审计 JSON、CSV、中文报告和 `SHA256SUMS`，结果必须覆盖 20 个未见
   seed、实际采用、物理可用和规则基线非退化，不能用单 cell 或 unavailable 补零。
4. D3 的 selection-to-lifecycle assembler 已完成；production admission assembler 仍需在
   实物到位后绑定 dataset manifest、split、frames、training source、state dict、bundle
   tree 和 D6 报告双哈希。它应生成新 immutable bundle/schema，不改写 v3 development
   bundle。
5. 新 bundle 形成后由 main 执行：

```bash
python3 -m research_modules.scalable_3d_simulation.run_experiment_matrix_shard \
  init-scope --scope-variants A1 --formal \
  --d3-model-bundle "$D3_ADMITTED_BUNDLE" \
  --output "$A1_EXECUTION_ROOT"
```

现有实际 bundle 路径为
`research_modules/d3_assignment_planner/outputs/formal_bc_development_20260720/bundle/`。
其 admission 仍是 development/shadow-only，promotion unavailable。多周期 shadow
summary SHA 为 `5093e5d0...c135c`；D6 旧 sidecar 文件 SHA 为
`f3852251...1c3b`，状态为 `pass_offline_assignment_comparison_only`。这些事实不能提前
关闭上述 P1。A1 独立通过前不评审 C1/F1。

### A1 选择后阶段合同更新（2026-07-26）

D3 已关闭“selector 输出后没有分阶段可验证 DTO”的模块级缺口。新增预注册、候选、选择、
发布和生命周期五类严格 schema，复用现有
`evaluate_learning_intervention_candidate_frame(...)`、`AssignmentPlanRuntimeAckEvidence`
和 `RuntimePlanWindowRewardEvidence`，没有复制既有资格逻辑。

阶段分别为 `policy_evaluated -> cost_correction_accepted -> assignment_changed ->
plan_published -> runtime_ack -> physical_window_available -> r0_pair_available`。预注册固定
模型摘要、seed/时间范围、代价修正、规则代价差和绑定变化上限。在线 truth 与生产权限固定
关闭。处理计划增加未满足需求槽或高威胁未满足槽、违反容量/硬边/M-to-N、未严格升版或
规则成本差超限时不能被选择。

发布证据要求 main 的 D3 总线 envelope 与选中计划完整一致。ACK 必须来自现有严格验证
对象，并绑定同一 plan id/version、总线序号和 payload 摘要。物理窗口按选中计划全部
binding 检查；缺任一成员窗口时整体不可用。R0 配对同样要求全部 binding 可用。不存在
后续实物时，装配器只返回等待状态，不推断发布、采用或物理结果。

专项测试 `13 passed`，覆盖无真值、确定性、无竞争帧、安全离散变化、重复资源、硬禁边、
旧版本、绑定变化上限、发布篡改、运行确认、物理窗口、R0 配对和伪造阶段。该结果是模块
合同夹具，不是新的 20-seed 运行。D3 全量收集 535 项，结果为
`534 passed, 1 skipped`，skip 为可选 OR-Tools。正式 100 帧仍为 `0/20 eligible`，所以
本次没有实际 A1 计划发布、runtime ACK、physical window 或 R0 pair。

### A1 batch 接线状态（2026-07-27）

“main 必须复制 D3 replay 内部逻辑才能得到 candidate/selection evidence”这一模块级缺口
已关闭。现有 batch runner 增加可选预注册模式，公开
`run_a1_isolated_intervention_batch(...)`。入口在同一严格 manifest、bundle 和匿名帧
循环内复用 `replay.rule_frame/treatment_frame`，调用核心 candidate API 和 selector。

预注册必须精确覆盖 20 个 seed 及全部帧范围，并绑定实际 state-dict SHA-256。文件内容、
manifest、匿名帧、bundle manifest 和权重在运行前后都受摘要约束。truth、内容篡改、缺
seed 和帧范围不足均失败关闭，不生成部分输出。

输出保留原 v1 JSON、CSV 和中文报告，新增 A1 summary、逐帧 candidate、逐 seed selection，
统一由 `SHA256SUMS` 覆盖。写盘记录是版本化稳定投影：核心 selector 仍消费完整 A1 DTO；
跨运行输出排除随机 plan id、依赖随机身份的完整 plan payload 摘要和墙钟推理时间，同时
保留 binding、版本、成本、需求、安全和原因码。该投影明确不是
`A1PlanPublicationEvidence`。

新增 6 项通过。合成 40 帧双跑逐文件一致并得到 20/20 首帧选择；零残差为 20/20
`no_safe_discrete_intervention`。batch 合计 `20 passed`，核心 A1 加 batch 为
`33 passed`。D3 全量收集 541 项，结果为 `540 passed, 1 skipped`；skip 为可选 OR-Tools。

开放 P1 不变为运行后半链：正式策略仍需先产生 eligible/near-competitive 离散变化，main
再发布严格新版本计划，D7 提供真实 ACK，D6 提供全部 binding 物理窗口和同 seed R0
配对，最后才允许 production admission 审计。正式 100 帧没有重跑，仍为
`0/20 eligible`。

## 正式 R0 滚动需求 P0

**暴露状态**：clean commit `32b3b40`、`high_threat_m_to_n`、200v200、
seed 1000、2.0 秒的正式单元在 `t=1.0` 失败。此前 5/20/50/100 规模同 seed 完成，
该分片已有 44/45 单元完成。

**根因**：`GT3D-000021` 的上一库存是空 `k=1` incomplete coalition，当前需求升为
`k=3` 且候选完整。旧计划评分对无 executable assignment 的目标提前进入未分配分支，
没有将需求合同变化标成上一计划不可行。其他 coalition 的成员迟滞触发全局 hold 后，
旧 `k=1` coalition 泄漏到最终库存规范化。

**D3 修复**：需求合同比较已前移到旧计划可行性判定。需求数量、主资源数量、协同模式、
时间模板或 assignment demand 不一致时，旧库存失败关闭并由当前候选重建。容量、重复
资源、版本、stale、all-or-none、primary/reserve 和最终需求一致性检查均未放宽。

**开发验证**：2026-07-25 同配置复验完成 2.0 秒，有限状态为真、在线真值使用为 0。
`GT3D-000021` 在 `t=1.0` 重建为完整 `k=3` coalition；最终 assignment/唯一资源为
197/197，过分配和需求摘要失配为 0。D3 全量为 `464 passed, 1 skipped`。

**剩余边界**：代码级 P0 已修复，正式验收仍开放。当前工作树不是新的 clean source；
原 marker 和 partial 制品继续绑定 `32b3b40`。main 必须在新 clean commit 下重建正式
执行来源并重跑该单元和分片，之后才能把该 P0 标为 formal closed。

## 多周期行为克隆影子 GAP 更新

### 已关闭的 P1

1. 原 20-seed 单帧干预虽有 `20/20` 代价矩阵变化，最终绑定变化为 0，学习干预不可辨识。
   当前多周期评估在受控匈牙利边界中得到 20/20 seed 绑定差异，证明冻结行为克隆残差可以
   跨越求解切换边界。
2. 原证据没有连续 previous-plan 关系。当前两组各自连续推进计划，逐周期保存规范 plan
   token、version、输入前序、声明前序和刷新/升版状态。旧版本采用和谱系违规均为 0。
3. 原保留集只覆盖名义 5v5 单帧。当前覆盖 5资源3目标、3资源5目标、资源失效与恢复、
   目标增删和 M-to-N 需求变化，共 620 个周期。
4. 模型异常、超时和分布外回退的矩阵一致性已有专项测试。固定保留种子影子运行中
   40 个 M-to-N 周期触发分布外回退，处理矩阵与规则矩阵逐元素相同。
5. 收尾静态检查发现 `cost_weights` 参数曾被接收但未传入两组规划器。当前已改为分别构造
   同配置 `CostModel`，零权重专项验证两组规则矩阵一致且参数实际生效。
6. CSV writer 原先使用平台默认 CRLF，导致未跟踪结果在后续纳入提交时触发 Git 尾随空白
   检查。当前已固定 LF 并重生成两份 CSV，规范化内容摘要和全部证据计数不变。

### 证据

本次固定保留种子影子评估使用 1000-1019，训练种子为 0-99，交集为 0。冻结权重 SHA-256 为
`e3da9fd5b54451da83358405b6051991e0c78bcf9f538b350d459b05faf8e0b2`。580/620 个周期
实际应用代价残差，120 个周期产生不同绑定。规则组和处理组累计抖动为 520/200；处理组按
规则矩阵重评分的周期平均代价高 0.000707。重复资源、硬约束或谱系违规、旧版本采用和在线
真值使用均为 0。新增专项 9 项通过；D3 全量为 `459 passed, 1 skipped`，跳过项为可选
OR-Tools。

### 仍开放的 P1

1. 当前是离线 shadow-only 规划比较，没有生产 runtime ACK、后续状态、物理结果、
   counterfactual 或 causal reward。不能据此开放 assist 或 authority。
2. PPO 研究管线已实现并有单元测试，但没有正式训练、冻结检查点和未见种子评估。
3. M-to-N 需求增加触发分布外回退，说明现有 BC 训练分布没有覆盖动态需求 3。后续是否扩充
   数据应由 main/D6 先确认该场景的运行价值，不通过放宽 OOD 阈值解决。
4. 三维可达性仍使用简化匀速截获时间，未接入 D7 的加速度、转弯率和爬升能力约束。
5. 模型权重仍位于被忽略的输出目录，缺少正式制品仓或 Git LFS 移交路径。
7. 多周期结果已绑定种子注册表、模型、数据和切分摘要，但生成时源码尚未形成 clean
   commit，也没有结果级源码/配置清单；当前只能作为开发证据。

该影子评估本身没有新增运行级 P0。随后正式 R0 暴露的滚动需求库存 P0 已完成代码修复和
开发复验，但新 clean commit 的 formal 重跑仍待 main 完成。默认 Hungarian、规则回退、
身份承诺、版本、stale、M-to-N all-or-none 和 `global_track_id` 所有权均未改变。

## 身份承诺准入更新

- **D3 P1 已关闭**：两类 identity uncommitted、缺失和未知状态不能进入首次或滚动分配。
- **D3 P1 已关闭**：上一计划绑定目标转为 uncommitted 时，迟滞不能保留绑定；新计划严格
  升版并保留拒绝审计，旧计划不被改写。
- **D3 P1 已关闭**：M-to-N 目标未提交时，全部 primary/reserve 槽位不可执行。
- **D3 P1 已关闭**：dry-run adapter 支持顶层、嵌套和 metadata commitment；缺失及未知
  状态均失败关闭。
- **D3 P1 已关闭**：D3 不改写 `global_track_id`。main 是已有绑定 hold/replan 的触发与
  采用方；D3 只在被调用后生成去绑定的新版本候选。
- **验证**：2026-07-23 专项 `12 passed`，D3 全量 `450 passed, 1 skipped`；唯一跳过为
  可选 OR-Tools。
- **P1 跨模块接线已验证**：固定 clean 提交
  `7e15dac9cdaf6743999dfe045a70676fd31a17d6`、200v200、2.2 秒、seed 1100 的
  `hold_only` 与 `hold_plus_centroid` 两臂都在 `t=0.75` 发布 v1/193；`t=1.0` 对
  11 个原 v1 已分配目标执行身份撤回，绕过迟滞并严格发布 v2/186；`t=2.0` 发布
  v3/186。
- **下游零违规已验证**：11 个拒绝目标全部从 v2 删除，`t>=1.0` 的 D3 后续分配、D5
  主动视觉、D5 终端绑定和 D7 导引违规继续执行均为 0。两臂结果一致。
- **计数口径**：main 终态 binding hold count 为 13、event count 为 1；13 是运行时绑定
  保持计数，不是 D3 rejected target 数。D3 在 v2 的拒绝目标数是 11。
- **证据限制**：该 episode 没有主动注入 stale plan。stale rejection 仍由 AirSim/module
  unit regression 验证。本结果关闭运行时安全撤回接线，不证明 D1 质心修正或 D2 关联算法
  收益，也不是物理拦截证据。
- **无新增 P0**：版本、stale predecessor、授权、owner/epoch/lease 和全局航迹 ID 规则未
  放宽。

2026-07-23 集中测试 12 项通过，D3 全量通过并保留 1 个既有可选依赖 skip。main 已把
D2 commitment map 接到真实 scalable episode 的 D3 输入，D3 身份撤回、严格升版和下游
停止链路已形成 clean 单 seed 证据。开放项转为多 seed/动态非等量重复性、独立 stale
主动注入回归和 D1/D2 算法效果评估，不需要继续扩展 D3 准入架构。

## 1. 总体结论

D3 当前已经完成中心化一对一与显式 M-to-N demand-slot 主线：SciPy Hungarian、DP fallback、schema v2、coalition all-or-none admission、滚动与保守增量规划、set/signature 迟滞、防 stale plan、版本化 `AssignmentPlan/CoalitionPlan`、可解释代价、D5 feedback writeback、secondary activation/continuation、D7 coalition binding、D6 export 和 synthetic AirSim dry-run adapter。历史第一次真实复验暴露了 soft reserve hold 顺带旋转 healthy primary；当前实现已从 previous plan 推导 member role，在健康 primary + soft reserve failure 时固定旧 primary slots。ComputerVision 10-seed 中 T001 双 primary 视觉共识与当前计划授权为 8/10，D3 P1 合同层已闭合。P2 已补齐同一非等量 N/M、hybrid role、资源容量输入的 SciPy/optional OR-Tools 隔离 runner；当前 OR-Tools 未安装时返回结构化 `unavailable_reason`。

2026-07-10 P1 switch-penalty 修复已完成：`reassignment_switch_penalty` 现在在 Hungarian/fallback solve 前加入已有 target 改配到不同 resource 的可行边；同 resource、不可行边、无历史 assignment 的 target 和 unassigned cost 不变。后置 Assignment 加价路径已移除，solver matrix、edge breakdown、objective、plan cost 和 evidence 单次计费一致。当前新 plan binding 保持 `active/current`，旧 plan 继续由 latest `plan_id/version` gate 失效。

当前 D3 原合同层缺口已转为协同物理与参数校准；2026-07-25 新暴露的滚动需求 P0 则是
独立运行阻塞，当前处于“代码已修复、formal 重跑待完成”。2026-07-11 的
5-resource/2-target ComputerVision 10-seed 中，T001 双 primary 视觉共识与当前计划授权
达到 8/10；seeds 7/27 保留回归。二级接管和完全分布式 commit 正例已通过，缺 ACK 时
coalition aborted 且 D7 许可为 0，证明 D3 current plan/binding 可被下游 fail-closed
gate 正确消费。历史 `secondary_plan_active=0` 仅保留为 2026-07-10 实施前运行基线，
不再代表当前合同状态。

2026-07-13 已完成 M5N2 hybrid `2 primary + 1 standby reserve` 的真实 SimpleFlight paired 验收：baseline 与三个候选各 10 seeds，共 40 个 episode；本阶段不要求 primary 同时到达。coalition completion 为 baseline `0/10`、最佳 `20 m / 3 s / 40 deg` `5/10`、其余候选 `2/10` 和 `1/10`，未达到 `8/10` 门限。版本/stale/role 合同保持，reserve 未授权执行、旧版本执行和 `global_track_id` 本地改写均未成为该轮安全问题。

除本节新增的 formal 重跑边界外，D3 没有未关闭的 P0 或 P1 **合同层**缺口。
`previous_plan` 连续性、solve 前 switch penalty、D5/D7 禁止本地改绑、secondary
activation/current-binding、身份承诺运行时撤回、增量接口、transient feedback dwell、
role-aware primary 保持、plan/evidence schema 和 canonical planning-tick history
schema/export 均作为回归合同保留。最新 M5N2 20-case 已由 main 写盘 `3725/3725` 条
canonical records，D3 对计划版本、owner、成员 roster 和迟滞审计的可用性不再是
`unavailable`；20 个 case 的实际 version/member/owner transition 均为 0。
**P1 证据与参数标定仍开放**：身份撤回目前只有 clean seed 1100 单种子证据，第二
primary `0/20`、coalition `0/20`，并且还需完成真实 3v5、5v3 和动态事件标定。

2026-07-14 已关闭 P1 计划抖动的一个合同根因：普通 D5 `ambiguous/hold/reacquire` 以及几何、FOV、检测不稳定现在只形成当前 resource-target 边的 soft cost 和 D7 hold，不再把资源升级为 `operator_hold=True`。`friend_overlap_hold` 保持 resource-hard，verified friend 保持 target-hard；安全身份冲突、duplicate assignment/lock 和显式 feasibility reject 保持 hard reject，真实 unavailable 资源仍由成本模型整资源拒绝。分类 class/scope/reason/hard flag 写入审计 metadata，旧 `operator_hold_suggested/resource_update` pair metadata 继续可读并被审计降级。transient 帧窗口完成后仍进入 coalition/global `min_dwell` 迟滞，不再直接发布改配。

历史 40-case 仍保留为旧候选预筛证据；最新 20-case 已完成 main 逐 tick history 写盘。D3 现提供并实际写盘 `d3_plan_history_record_v1`、`PlanningTickHistoryRecord` 和 `plan_history_record_from_plan(...)`；`3725` 条记录完整输出 owner、迟滞、成本、成员与 stale/rollback 审计且排除 truth。实际 plan/member/owner churn 均为 0；`3555` 条 membership audit 是候选换员评估，其中 `3524` 条成员保持、`31` 条成员层通过后被全局迟滞保持，不能计为实际 churn。普通 pair hold 扩大为资源不可行仍只是旧 40-case 根因线索，不是已证明的物理失败因果。

2026-07-21 的 v2 正式保留 seed 证据已关闭“正式产物未更新”和“隔离 treatment 是否实际应用不可用”两项 D3 P1 证据缺口。独立复核确认 20 个 seed 全部 clean/finite，online truth 使用为 0，treatment applied=`20/20`、fallback=`0`。隔离模型修改了 `20/20` 组有效代价矩阵，但最终 Hungarian binding 变化为 `0/20`；规则与 treatment 的平均分配代价均为 `17.0560260319065`，高威胁未满足、重复、硬约束违规和 churn 均为 0。这是规划层隔离应用与同帧安全计数比较，不是 runtime ACK、物理 outcome、paired physical non-degradation、反事实、因果或生产晋级证据。

2026-07-22，D6 提交 `d4e8562` 已生成 profile-bound v2 availability sidecar，状态为 `pass_offline_assignment_comparison_only`。D6 将 same-frame offline assignment comparison 标为 available，D3 assignment 层可用性和独立消费缺口关闭。当前正式 artifact set 仍没有 runtime ACK、post-intervention physical outcome、paired physical effect/non-degradation、counterfactual 或 causal 证据；promotion、PPO、assist 和 authority 未开放，规则回退保持启用。

同日，D3 已补齐独立多周期 rollout 所需的 plan-consumption 合同。该证据能确认指定
experiment/seed/arm 消费了准确的 plan id/version/payload，并拒绝 replay、旧版本和 lineage
篡改；它固定不是 production runtime ACK，也不声明物理结果。D3-owned 接口缺口关闭，main
克隆世界推进、D7 command lineage 和 D6 paired physical outcome 仍为 P1 集成缺口。

## 2. 已实现

| 能力 | 实现状态 | 关键代码/测试依据 |
|---|---|---|
| SciPy Hungarian 默认分配 | 已实现。`HungarianAssignmentSolver` 优先调用 `scipy.optimize.linear_sum_assignment`，代价矩阵尺寸来自输入 `tracks/resources` 长度，并用 dummy unassignment 列支持目标未分配。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/solver.py`; `research_modules/d3_assignment_planner/tests/test_solver.py` |
| fallback DP | 已实现。`FallbackAssignmentSolver` 用位掩码 DP 做小规模 optional assignment；`HungarianAssignmentSolver(allow_scipy=False)` 可强制走 fallback。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/solver.py`; `research_modules/d3_assignment_planner/tests/test_solver.py` |
| 滚动重分配 | 已实现。`AssignmentPlanner.plan()` 每个 tick 构建 candidate plan，并与 `previous_plan` 在当前矩阵上重评分比较。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`; `research_modules/d3_assignment_planner/tests/test_planner.py` |
| 迟滞与 solve 前 switch penalty | P1 matrix integration done。支持 `delta`、`min_dwell`、`max_changes_per_window`；`reassignment_switch_penalty` 在 Hungarian/fallback 前进入可行改配边，matrix/breakdown/objective/evidence 单次计费一致，unassigned/release 语义不变。继续输出 `held_by_hysteresis`、`held_by_change_limit`、`accepted_gain_and_dwell`、`accepted_previous_infeasible`、`accepted_high_threat_release` 等决策状态和原因 metadata。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`; `research_modules/d3_assignment_planner/tests/test_planner.py` |
| 版本化 transient feedback dwell | P1 done。writeback 保留 source plan version、stable counts/required window 和 conflict；full/incremental 在普通迟滞前保护仍可行的 primary set。effective window 取 D3 配置与上游 required 的最大值；窗口完成仅结束前置保护，soft candidate 仍进入 coalition/global `min_dwell` 迟滞，硬风险可立即释放。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`; `research_modules/d3_assignment_planner/tests/test_transient_feedback_dwell.py` |
| Reserve soft feedback 的 primary role 保护 | P1 done。D3 从 previous assignment 推导 member role；同版本 primary 全部 consistent 且仅 reserve 普通 hold/reacquire 时，在 demand-slot matrix 固定仍可行的旧 primary 集合，只重解 reserve candidate；实际替换仍需成员/全局迟滞放行。无需 main 新增 reason/required/member_role。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`; `research_modules/d3_assignment_planner/tests/test_transient_feedback_dwell.py` |
| 旧计划不可行时绕过迟滞 | 已实现。资源不可用、旧边不可行或重复资源导致旧计划不可行时可接受新计划。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`; `research_modules/d3_assignment_planner/tests/test_planner.py` |
| 版本化 `AssignmentPlan` 与前序连续性 | P0 done。`AssignmentPlan` 有 `plan_id/version/window_id/resource_count/target_count`；首次调用允许 `previous_plan=None`，active plan 后缺失前序计划以 `previous_plan_required` 拒绝并返回 latest id/version，旧计划和 expected-version 检查保持原语义。planner 实例只对应一个 episode。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`; `research_modules/d3_assignment_planner/tests/test_planner.py` |
| 不写死 2v2/5v5 | 已实现。矩阵由输入列表长度构建，测试显式验证 3 targets / 2 resources 的 `assignment_matrix_shape=[3, 2]`、`resource_count=2`、`target_count=3`。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/costs.py`; `research_modules/d3_assignment_planner/tests/test_planner.py` |
| 可解释代价分解 | 已实现。`CostModel.edge_cost()` 输出 `window/covariance/threat/resource_state/resource_energy/resource_availability/resource_current_load/resource_history_failure/fov/conflict/reassignment_switch_penalty/intercept_feasibility/infeasible/total`。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/costs.py`; `research_modules/d3_assignment_planner/tests/test_costs.py` |
| 轻量 hard time-window rejection baseline | 已实现。`TargetTrack` 支持全局或按资源的 `hard_time_window/time_window_open_at_s/time_window_close_at_s/time_window_state/time_window_by_resource`；窗口明确 closed/expired/not-yet-open 时，`CostModel` 把边标为 hard infeasible，输出 `hard_time_window_reject` 和 `reason_time_window_*` flags，planner 不分配该边并在 evidence 中导出 `reject_reason`。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/src/d3_assignment_planner/costs.py`; `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`; `research_modules/d3_assignment_planner/tests/test_costs.py`; `research_modules/d3_assignment_planner/tests/test_planner.py` |
| P0-B 资源状态细化 | 已实现。`ResourceState` 补齐 `energy_fraction/availability_score/current_load/history_failure_rate/intercept_feasibility_by_target/intercept_feasibility_score_by_target`，`CostModel` 消费这些字段并输出资源状态子项和不可行原因 flag；dry-run adapter 已映射 synthetic AirSim-style 字段。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/src/d3_assignment_planner/costs.py`; `research_modules/d3_assignment_planner/src/d3_assignment_planner/airsim_dry_run_adapter.py`; `research_modules/d3_assignment_planner/tests/test_costs.py`; `research_modules/d3_assignment_planner/tests/test_airsim_dry_run_adapter.py` |
| P0-B 可解释 threat score baseline | 已实现。`compose_threat_score_baseline()` 将关键区接近、TTC、速度、协方差、目标状态组合为可解释 `ThreatScoreBaseline`；adapter 在缺少显式 `threat_score` 时写入 baseline score 和 components/reasons metadata。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/src/d3_assignment_planner/airsim_dry_run_adapter.py`; `research_modules/d3_assignment_planner/tests/test_costs.py`; `research_modules/d3_assignment_planner/tests/test_airsim_dry_run_adapter.py` |
| Current plan / cost evidence export | 已实现。planner metadata 记录 current plan id/version/owner/source、solver 实际使用的完整 cost matrix、target/resource ids、per-edge cost breakdown、rejected edges、hard reject reasons、stale rejection reason 和 secondary owner/source/version/supersede 字段；switch penalty 已在 solve 前进入 matrix/breakdown，`assignment_evidence_from_plan()` 导出同值 `AssignmentEvidenceExport` 供 D4/D6 replay。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`; `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/tests/test_assignment_exports.py`; `research_modules/d3_assignment_planner/tests/test_planner.py` |
| D7 guidance binding | 已实现。`guidance_bindings_from_assignment_plan()` 导出 `AssignmentGuidanceBinding`，携带 `plan_id/version/resource_id/assigned_global_track_id/authorization_state/guidance_phase/source/target/link`，并暴露 D7 兼容别名；逐 pair metadata 还包含 coalition id/version/epoch、role/wave/activation/validity、per-primary 授权资格、plan churn/rollback/stale reject。新 current plan 即使发生改配仍输出 `active/current`，旧 plan 由 plan id/version gate 失效，reserve 始终 standby/hold。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/tests/test_guidance_binding.py`; `research_modules/d3_assignment_planner/tests/test_guidance_binding_contract.py`; `research_modules/d3_assignment_planner/tests/test_m_to_n_demand_slots.py` |
| 授权状态配置透传 | 已实现。`PlannerConfig.human_authorization_state` 会写入 `AssignmentPlan.human_authorization_state`，并记录 `configured_human_authorization_state` 与 `effective_human_authorization_state`，main 可用 `"recorded"` 进行仿真记录态 gating。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`; `research_modules/d3_assignment_planner/tests/test_planner.py` |
| D5 feedback 分级写回 | P1 root-cause fix done（2026-07-14）。普通 ambiguous/hold/reacquire、几何/FOV/检测不稳定为 edge-soft，只写 FOV cost + D7 hold；friend overlap 为 resource-hard，verified friend 为 target-hard；身份冲突、duplicate 和显式 feasibility reject 为 edge-hard。兼容旧 metadata，并输出 class/scope/reason/hard flag；`allow_local_rebind=False` 不变。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`; `research_modules/d3_assignment_planner/tests/test_terminal_feedback_contract.py`; `research_modules/d3_assignment_planner/tests/test_p1_nm_feedback_governance.py`; `research_modules/d3_assignment_planner/tests/test_transient_feedback_dwell.py` |
| Secondary takeover activation/current binding | 已实现 D3 侧严格规则。`prepare_secondary_takeover_plan()` 要求 concrete secondary owner、持续 `takeover_ready`、精确 `previous_plan_id`、严格递增 version、正且单调 leader epoch、激活时未过期 lease；成功计划写入 active schema 和完整审计字段。secondary D7 binding 必须显式匹配 current plan，旧中心、非 current、未激活或 lease 过期计划均不是 `active/current`。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/tests/test_guidance_binding_contract.py`; `research_modules/d3_assignment_planner/tests/test_assignment_exports.py` |
| `AssignmentValiditySummary` | 已实现。`assignment_validity_summary_from_plan()` 输出 `plan_age_s`、`assignment_latency_s`、`cost_margin`、`stale_plan_version`、`duplicate_assignment_count`、`unassigned_high_threat_count`、规模字段和 N/M replay 字段：`assigned_count/hysteresis_reject_count/stale_reject_count/reassign_count`。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/tests/test_assignment_exports.py` |
| D6 assignment record export | 已实现并补齐多 seed current-plan 与逐 pair 字段。`assignment_records_from_plan()` 除基础 assignment/owner/cost/迟滞/stale 字段外，统一导出 coalition id/version/epoch/completeness、role/wave/activation/validity、per-primary 授权范围与资格、plan churn/rollback/stale reject。两个 primary 独立 active/current，reserve 记录为 standby 且 `active=false`，不会被统计为已激活执行 pair。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/tests/test_assignment_exports.py`; `research_modules/d3_assignment_planner/tests/test_m_to_n_demand_slots.py`; `research_modules/d3_assignment_planner/tests/test_coalition_membership_hysteresis.py` |
| Canonical planning-tick history export | P1 D3 schema/export done（2026-07-14）。`plan_history_record_from_plan()` 生成 `d3_plan_history_record_v1`：计划级身份/规模/owner/epoch/lease/lineage/cost，ordered primary/reserve assignment 和可恢复 coalition members，迟滞/成员变化、soft/hard feedback count/classification、stale/rollback/replan reason；`to_dict()` 为 JSON-native，排除 truth 字段。旧 assignment export 兼容不变。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/tests/test_plan_history_record.py` |
| D5 feedback calibration summary | 已实现。`summarize_terminal_feedback_calibration()` 输入多 seed assignment records/feedback records，输出 duplicate/friend/fov/geometry reject 计数及 cost/hysteresis 建议；`summarize_assignment_mismatch_replay()` 输出 N/M replay summary。helper 只给建议，不自动替换默认权重或迟滞参数。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`; `research_modules/d3_assignment_planner/tests/test_assignment_exports.py` |
| AirSim dry-run adapter | 已实现为 synthetic adapter。D3 接收 dict/object 风格 tracks/resources，不 import AirSim，不直接调 Blocks runtime。 | `research_modules/d3_assignment_planner/src/d3_assignment_planner/airsim_dry_run_adapter.py`; `research_modules/d3_assignment_planner/tests/test_airsim_dry_run_adapter.py`; `research_modules/d3_assignment_planner/docs/AIRSIM_INTEGRATION_PLAN.md` |

## 3. 已接入但需校准/部分实现

| 能力 | 当前状态 | 为什么只是部分实现 | 缺少条件 |
|---|---|---|---|
| D5 terminal feedback runtime 消费 | 已完成 D3 helper 与 main/runtime 接线。`evaluate_terminal_feedback()` 保持既有 action 兼容，writeback 新增 soft/hard scope 分类：普通 uncertainty 为 pair-soft，明确 friend/identity/duplicate/feasibility 风险 fail-closed；main/runtime 仍可使用原 metadata 字段。 | D3 只消费 D5/main 已聚合的 metadata，不自行判断视觉身份、不统计跨资源 duplicate lock，也不改写 `global_track_id`。 | 剩余是多 seed 校准：验证 edge-soft FOV、hard reject 和明确资源/目标 hard 在不同 N 规模、遮挡和 crossing 场景中稳定改善计划质量。 |
| duplicate terminal lock 风险 | 字段、helper 和 binding gate 已支持。`duplicate_terminal_lock_risk=True` 会请求 `secondary_arbitration`，D7 binding 进入 `hold`。 | D3 不自行从多资源视觉状态中统计 duplicate terminal lock，只消费上游传入风险。 | D5 或 main 需要聚合同一 `global_track_id` 被多个资源 terminal lock 的事件，并把结果交给 D3/D7/D6。 |
| D4 主动降级联动 | D3 已提供 validity/feedback 证据和严格 secondary activation/current-binding 合同；二级/分布式 commit 正例与缺 ACK fail-closed 已通过下游验证。 | D3 不选择二级节点、不续租、不执行 CBBA/拍卖或恢复仲裁。 | 后续中心恢复和长时 lease 校准属于 main/D4 policy，不是 D3 P1 合同缺口。 |
| D6 指标闭环 | D3 已有 `AssignmentRecord`、`AssignmentEvidenceExport`、canonical `PlanningTickHistoryRecord`、validity summary、N/M replay summary 和 feedback calibration summary helper。最新 20-case 已写盘并可计算 plan/member/owner churn。 | D3 不写 D6 存储，也不拥有 episode log 总线；calibration helper 输出建议但不自动改默认参数。 | 写盘缺口对本批已关闭；下一步统一 canonical target 与 cooperative target 术语，并在真实动态 N/M 中继续标定权重和迟滞。 |
| AirSim runtime 闭环 | D3 有 dry-run adapter、严格 secondary 合同、canonical history exporter 和 AirSim integration plan；最新 main runtime 完成 baseline/candidate 各 10 seeds 的 M5N2 20-case。默认 `2 primary + 1 standby reserve`，且不要求同时到达。 | history 20/20 可用且实际 plan/member/owner churn 为 0；但 pair/target/coalition=`12/60`/`12/40`/`0/20`，第二 primary `0/20`，20 个 stop reason 均为缺 collision object 的 `collision_stop`。 | main/runtime 补碰撞来源，D6 分离 canonical/cooperative 口径；D3 继续真实动态 N/M 标定，不因 candidate 非退化失败直接改算法。 |
| EVAL P0-B 资源状态细化（保持回归） | 已完成 baseline，当前不列为运行级 P0 blocker。`ResourceState` 现有字段外已补 `energy_fraction/availability_score/current_load/history_failure_rate/intercept_feasibility_by_target/intercept_feasibility_score_by_target`；`CostModel` 消费 energy、availability、load、history failure 和 intercept feasibility，并导出不可行原因 flag。 | 还缺真实 episode 中各字段的阈值标定和跨模块日志分布，不缺 D3 DTO/schema。若字段缺失、cost metadata 丢失或不可行原因不可解释，再列 P0 backlog。 | 用多 seed/N 规模回放校准 energy/availability/current_load/history_failure_rate 的默认阈值和 D6 聚合展示，同时保持现有 cost metadata 单元测试回归。 |
| EVAL P0-B 增强迟滞和 stale rejection（保持回归） | 已完成 baseline，当前不列为运行级 P0 blocker。已有 `delta`、`min_dwell`、`max_changes_per_window`、旧边不可行绕过、stale plan 拒绝、high-threat release condition 和 D6 held/released 原因导出；P1 已进一步把 `reassignment_switch_penalty` 前移到 solver matrix 并消除双重计费。 | 多 seed 标定尚未完成，尤其是 release condition 与 churn/漏分配之间的参数平衡。若 min dwell、switch penalty、release condition 或 stale reason 无法解释，再列 P0 backlog。 | 用多 seed/N 规模回放校准 `delta/min_dwell/max_changes_per_window/reassignment_switch_penalty`，D6 报告同时展示重分配下降、高威胁未分配不升高、matrix/objective 一致和 stale rejection reason 可聚合。 |
| EVAL P0-B 可解释 threat baseline（保持回归） | 已完成 baseline，当前不列为运行级 P0 blocker。`compose_threat_score_baseline()` 将接近关键区、TTC、速度、协方差、目标状态合成为可解释 threat score；`TargetTrack.threat_score`、`unassigned_high_threat_count` 和 cost breakdown 继续消费该字段。 | 完整动态威胁评估尚未实现，不应把 baseline 伪装成 outcome-aware 模型。若 TTC、关键区接近、速度、协方差或目标状态无法进入 baseline 解释，再列 P0 backlog。 | 用 D6 多 seed outcome 标定完整模型，并保留 Hungarian/baseline 对照；P0 回归只要求 baseline 组件和 reasons 可解释、可导出。 |
| EVAL P1 完整动态威胁评估 | 未作为完整模型实现。当前仅消费/记录 threat baseline 所需字段。 | 完整威胁模型需要场景定义、保护区、TTC、速度、目标类别、协方差、资源状态和 D6 mission outcome 支撑，不能用单一 `threat_score` 字段伪装完成。 | 先保持 P0-B baseline 可解释，再用 D6 多 seed outcome 标定完整模型，并保留 Hungarian baseline 对照。 |
| EVAL P1 增量分配 | 接口和可复用校准矩阵已实现。`plan_incremental()` 校验输入快照与 declared changed IDs，只求解受影响的独立可行连通分量，随后在完整计划上应用迟滞；其余情况带原因回退全量。paired runner 覆盖 8 类转换并汇总 latency、churn、unassigned high-threat、coalition shortfall 和 reject/fallback。 | deterministic 3v5/5v3、目标新增、资源失效、需求变化、D5 reserve feedback、hard-window、all-or-none、switch penalty 和 full/incremental equivalence 已覆盖；真实 AirSim 多 seed 尚未标定。 | main/D6 用相同 schema/profile/version 的真实动态事件统计 incremental applied/fallback reason、延迟、cost equivalence、churn、高威胁未分配和 coalition shortfall；版本不一致继续 hard reject，不静默回退。 |
| EVAL P1 时间窗口硬约束 | 轻量 baseline 已实现。`TargetTrack.window_cost` 仍是软排序项；新增 hard close/open schema、不可行窗口拒绝、`reject_reason`、cost breakdown flags 和测试。 | 目前是轻量 baseline，不是完整多窗口/到达时间网络；未做真实多 seed 标定，也未接 OR-Tools 复杂约束。 | 用 AirSim/point-mass 多 seed/N 规模回放校准 hard window 输入、到达时间和 reject reason 分布；多窗口/容量/配额后续可进入 optional min-cost-flow 对照。 |
| P2 optional OR-Tools Min Cost Flow 对照 | 容量 benchmark contract done。共享 problem 同时进入 SciPy 容量列展开与 flow 原生容量 arc；覆盖非等量 N/M、hybrid primary+reserve、容量限制、objective/assignment 解码和结构化 unavailable。SciPy 当前 objective `5.6`。 | 当前环境未安装 OR-Tools，installed-only 求解 test skip，故尚无 flow objective 实证；slot-level flow 不表达 coalition 原子 admission。 | 在隔离环境运行 installed solver 并保存 objective delta/assignment；CP-SAT/MILP、备份配额、多窗口和分组配额继续作为 P2 optional，默认在线 planner 不变。 |

## 4. 未实现

| 能力 | 当前状态 | 未实现原因 | 缺少条件 | 下一步优先级 |
|---|---|---|---|---|
| 完整 runtime secondary takeover 仲裁策略 | D3 已实现 activation/current-binding 严格校验和审计导出，且下游 commit 正例与缺 ACK fail-closed 已通过。 | D3 不是 D4 二级节点选择器，不维护 heartbeat/lease 续期，也不拥有中心恢复仲裁。 | D4/main policy 继续校准租约续期、中心恢复合并和 stale secondary runtime 拒绝。 | 外部 policy，非 D3 DTO/P1 缺口。 |
| CP-SAT / MILP | 未实现，仅作为更复杂的隔离研究方向。 | 高频滚动主线不需要 MILP；求解时间、建模复杂度和约束定义都未定。 | 需要明确组合约束、求解时间预算、失败降级策略和对比场景。 | P2 optional benchmark。 |
| D3 内部 CBBA/拍卖 | 未实现，且不建议在 D3 实现。 | D3 是中心化分配模块；中心失效或通信受限后的 CBBA/拍卖属于 D4 分布式 fallback 边界。 | D4 需要以 D3 最新中心计划作为基线实现/对比 CBBA、拍卖或合同网。 | 不列入 D3 优先级。 |
| 直接 AirSim/Blocks import 和控制 | 未实现，且不应放入 D3。 | D3 边界是抽象规划；AirSim launch/reset/episode/log collection 属于 main/runtime。 | main/runtime adapter 提供抽象输入和日志输出。 | 不列入 D3 内部实现。 |

## 5. 未实现原因汇总

1. **模块边界**: D3 只发布中心化候选计划、有效性证据和跨模块 DTO，不执行 D4 降级、D5 视觉改绑、D6 存储或 AirSim runtime 控制。
2. **当前算法需求**: 默认无显式 demand 时保持 `k_j=1` Hungarian；显式 M-to-N 使用 demand-slot all-or-none 主线。更复杂的最小费用流、CP-SAT/MILP 只在隔离 benchmark 中评估。
3. **依赖策略**: OR-Tools 不进入默认依赖；容量 benchmark 在缺失时输出 `status=unavailable` 和 `unavailable_reason`，installed solver 实证仍待补，也不进入默认 planner。
4. **运行时总线持续校准**: D3 helper 已输出 metadata、summary、record、evidence、canonical history、binding、N/M replay summary 和 D5 feedback calibration summary。最新 20-case 已完成 main 写盘和 D3 只读复核；后续重点转为动态 N/M 多 seed、canonical/cooperative 术语统一和碰撞来源回灌。
5. **上游事件缺失**: duplicate terminal lock、D5 连续状态迁移、D2/D1 不确定性摘要和 D4 仲裁结果需要由其他模块或 main 聚合后再反馈给 D3。

## 6. 缺少条件

| 缺少条件 | 影响 |
|---|---|
| 真实非等量 N/M 与事件驱动多 seed | 2026-07-15 最新 M5N2 baseline/candidate 共 20 case 已有 3725 条逐时刻计划历史；仍缺真实 3v5、5v3、目标新增、资源失效、D5 模糊、D2 不确定和 crossing/dense 动态数据。 |
| D5 feedback 权重阈值长期标定数据 | D3 已能生成 advisory calibration summary；仍需要真实 D6 records 反复校准 `fov_difficulty_by_resource`、禁配边、operator hold、hold/replan/secondary_arbitration 阈值，避免过度重规划或过度 hold。 |
| D5/main duplicate lock 和多帧不一致聚合分布 | D3 不自行判断多资源终端锁定冲突；需要上游持续提供聚合事件，供 D3 权重阈值校准。 |
| P0-B 多 seed 标定证据 | baseline schema/helper 已完成；仍需要覆盖非等量 M/N、资源不足、高威胁目标、D5 模糊和 crossing/dense 场景，用于校准增强迟滞参数、资源状态阈值和 threat score baseline 权重。 |
| P1 增量/hard-window 长期校准 | 增量 API/schema 已完成；仍需真实动态事件和 hard time-window 多窗口/到达时间多 seed 校准。 |
| P2 optional 求解器证据 | 同输入容量 runner 与 SciPy 结果已完成；仍缺 installed Min-Cost Flow objective/assignment 对照，CP-SAT/MILP coalition 参考与复杂 flow 尚未实现。 |

## 7. 当前 D3 P0/P1 缺口与下一步优先级

1. **P0 done / 当前无开放 blocker**: 历史上曾发现 active plan 后 `previous_plan=None` 导致 version 回退到 1 的 P0 blocker；该缺口现已修复，因此当前恢复并确认无开放 P0 blocker。现在固定以 `previous_plan_required` 拒绝并携带 latest plan id/version，首次调用和新 planner 实例仍从 version 1 开始。Hungarian、fallback DP、迟滞、其他 stale/expected-version 检查、D7 binding、D6 export、current evidence export、P0-B 资源状态细化、P0-B 增强迟滞/stale rejection、P0-B threat baseline 和轻量 hard time-window baseline 继续保持回归。
2. **P1 switch-penalty matrix integration done**: penalty 已在 solve 前加入可行改配边，零 penalty/中等 penalty/较大 penalty 构造测试覆盖换配、单次计费和保持原资源；边界测试同时确认不可行边、无历史 assignment 的新目标和 unassigned cost 不受 penalty 污染，release 与 current binding 语义保持不变。
3. **P1 合同层 done / 协同物理闭环 open**: 2026-07-13 的 40 个真实 SimpleFlight M5N2 episode 中，baseline 为 `0/10`，最佳 `20 m / 3 s / 40 deg` 为 `5/10`，其余为 `2/10`、`1/10`，未达 `8/10`。`2 primary + 1 standby reserve`、无同时到达要求、版本/stale/role 和 reserve 安全合同保持；D3 history schema/export 已完成，下一验收是 main 写盘、D6 churn 与参数闭环。
4. **P1 D5 feedback 权重标定**: 用真实逐 tick D6 records 对 edge-soft FOV、hard reject、明确 resource/target hard、`delta/min_dwell/max_changes_per_window/reassignment_switch_penalty` 做配对扫描；验收抖动下降且高威胁未分配不恶化。40-case 现状只能提供根因线索，不能证明分类修复与 outcome 的因果。
5. **P1 非等量 N/M 与增量校准支撑 done / 真实校准待办**: versioned 8-scenario matrix 覆盖 3v5、5v3、目标新增、资源失效、高威胁需求变化、D5 reserve feedback 和 hard-window；paired runner 的 8/8 转换 assignment/cost 等价，并报告 latency、churn、unassigned high-threat、coalition shortfall、hard reject、fallback 和 primary 保持。下一步补真实多 seed，不预设局部路径必然更快。
6. **P1 完整动态威胁评估**: 在 baseline 上加入保护区、目标类别、资源状态和 mission outcome 标定，并保留 baseline 对照。
7. **P1 时间窗口硬约束校准**: 已有单窗口 closed-edge baseline 不重复实现；补到达时间、多窗口、not-yet-open/expired 分布和 reject reason 聚合。
8. **P1 D3 secondary activation 合同 done**: 模块内 concrete owner、持续 readiness、严格 version/epoch、live lease、旧中心 stale、非 current/过期 binding 阻断和审计导出已验收；下游 commit 正例和缺 ACK fail-closed 已验证，中心恢复长期校准仍属 main/D4。
9. **P2 capacity benchmark contract done / installed evidence pending**: 同一 4-resource/3-target、5-slot hybrid 和容量输入已接 SciPy/optional flow；SciPy objective `5.6`，缺 OR-Tools 时结构化报告原因。当前环境仍未运行 installed flow；Hungarian/demand-slot 默认在线路径不变。
10. **P1 合同保持回归**: published active-plan `previous_plan` 必填；k=1/k>1 纯 evaluation refresh 均保持 `plan_id/version`，真实可执行语义变化才推进版本；forced ack/applied、未发布 candidate 不推进 latest、switch penalty solve 前单次计费、D5/D7 禁止本地换绑、transient dwell、reserve standby、secondary current/lease/rolling gate、schema v2/M-to-N、增量 snapshot/fallback 和 D6 schema 必须继续通过。当前回归基线见本文件末尾。
11. **P2 optional benchmark remaining**: 补 installed Min-Cost Flow objective/assignment 结果，并实现 CP-SAT/MILP coalition 参考、复杂 flow 和 10x10/20x20 参数扫描；只使用离线同输入数据形成最优差距、延迟和参数长期对照表，不进入默认 planner。

## 8. 跨模块接口影响

### 8.1 D4 主动/被动降级

被动降级由 D4 的 C2Health、通信和进程状态触发，D3 只提供最新中心 `AssignmentPlan` 作为接管基线。主动降级时，D3 的影响是提供证据而不是执行动作：`AssignmentValiditySummary`、`d4_request`、stale/version 状态、成本 margin、重复分配和高威胁未分配计数。若中心仍可用且 Hungarian 能明显改善，D4/main 应优先 `request_center_replan`；该请求完成后 main/runtime 已记录新的中心 plan owner、`plan_id/version`、`replan_reason`、superseded 旧计划和 stale 拒绝结果。若 D5 多帧不一致、D2/D1 不确定性高或计划持续 stale，再进入二级仲裁；secondary owner/version/source runtime 记录已接入，真实 secondary owner 选择、租约和中心恢复合并策略仍由 D4/main 负责，D3 侧只提供 DTO/helper 和多 seed 记录校准。

### 8.2 D5 terminal association

D5 只做末端视觉配准和一致性证据。D3 给 D5 的 assignment 是“资源当前应关注的 `global_track_id`”，不是允许 D5 改绑的授权。D5 反馈被 D3 helper 转为 `hold/replan/secondary_arbitration` 建议，并通过 `apply_terminal_feedback_to_planner_inputs()` 分级写回 edge-soft FOV、hard reject 或明确 resource/target hard；普通 pair hold 不设置 `operator_hold`。main/runtime 已负责调用和记录。D3 文档和 DTO 均明确 `allow_local_rebind=False`，后续重点是用真实多 seed 结果长期标定 D5 feedback 权重阈值。

### 8.3 D7 PN/PNG gating

D7 中段 PN 和末端视觉 PNG 只消费当前版本 binding。对 secondary plan，main 必须把当前 `plan_id/version` 传给 D3 binding helper；不匹配、缺失 current confirmation、takeover 未激活或 lease 过期时 binding 为 stale/hold。D7 仍必须同时检查 D4 action 和 D5 lock，且不得本地换绑 `global_track_id`。

### 8.4 N 规模输入

D3 的 `target_count/resource_count` 来自输入数组长度。main 的 `--drone-count N` 只决定资源状态记录数量；目标数可以大于、小于或等于资源数。2v2 和 5v5 只作为 baseline 名称，非等量 M/N 也应通过同一 `AssignmentPlanner.plan()` 路径。

## 9. 关键依据路径

- `research_modules/d3_assignment_planner/src/d3_assignment_planner/solver.py`: SciPy Hungarian、dummy unassignment、DP fallback。
- `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`: 滚动 plan、迟滞、版本推进、stale previous plan 拒绝、规模 metadata。
- `research_modules/d3_assignment_planner/src/d3_assignment_planner/costs.py`: 代价矩阵和 cost breakdown。
- `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`: `AssignmentPlan`、D5 feedback decision/writeback、secondary takeover DTO、D7 binding、`AssignmentValiditySummary`、D6 `AssignmentRecord`、`PlanningTickHistoryRecord` 与 canonical exporter。
- `research_modules/d3_assignment_planner/src/d3_assignment_planner/min_cost_flow.py`: optional OR-Tools Min Cost Flow benchmark 与 unavailable gate。
- `research_modules/d3_assignment_planner/src/d3_assignment_planner/p2_benchmark.py`: 共享非等量 N/M、hybrid role、容量约束输入和结构化双 solver outcome。
- `research_modules/d3_assignment_planner/src/d3_assignment_planner/airsim_dry_run_adapter.py`: synthetic AirSim dry-run adapter。
- `research_modules/d3_assignment_planner/tests/test_planner.py`: 非 5v5 规模、迟滞、stale plan、cross-node fields。
- `research_modules/d3_assignment_planner/tests/test_solver.py`: Hungarian/fallback 行为。
- `research_modules/d3_assignment_planner/tests/test_terminal_feedback_contract.py`: D5 feedback 映射、写回下一轮输入和不允许 local rebind。
- `research_modules/d3_assignment_planner/tests/test_guidance_binding_contract.py`: D7 binding stale/revoked/hold/reassigned/secondary takeover schema/owner/source/version。
- `research_modules/d3_assignment_planner/tests/test_assignment_exports.py`: validity summary 和 D6 assignment record export。
- `research_modules/d3_assignment_planner/tests/test_plan_history_record.py`: canonical ordering、primary/reserve、owner/epoch/lease、feedback/hysteresis/cost、JSON 与 truth 排除。
- `research_modules/d3_assignment_planner/tests/test_m_to_n_demand_slots.py`: schema v2、3v1/2v1/5v2、能力、角色/波次、版本/迟滞、multiplicity、binding。
- `research_modules/d3_assignment_planner/tests/test_min_cost_flow.py`: OR-Tools optional installed/skip/unavailable 合同。
- `research_modules/d3_assignment_planner/tests/test_p2_capacity_benchmark.py`: 同输入容量、objective、role、unavailable reason 和在线 planner 隔离合同。

## 10. M 对 N 联盟分配 P0/P1 补充（2026-07-11）

证据综述：`subagent_reviews/D3_M_TO_N_ASSIGNMENT_AND_SCHEDULING_REVIEW.md`。本节只新增 P0/P1 状态，不改写既有 P2/P3 项。

### 10.1 现状判定

- `AssignmentPlan schema v2`、`TargetDemand`、`CoalitionPlan/member/summary` 已实现。无显式 demand 时仍为 `k=1 independent primary=1`；显式 `TargetDemand()` 启用默认 `k=3 hybrid primary=2`。`primary_resource_count` 可接收 main `--cooperative-primary-count`，不再硬编码 `min(2,k)`。
- `hungarian_demand_slots` 已实现 role/wave/capability slot 展开、威胁优先和全有或全无 admission。不完整 coalition 记录 tentative members/shortfall，但不发布 executable assignment。
- assignment signature/set 驱动迟滞；`k>1` 成员/角色有独立 dwell 与 coalition epoch。兼容成本/诊断刷新保留 plan ID/version 且不推进 coalition epoch；成员/角色变化才推进 coalition epoch。只有真实新执行版本发布后旧 binding 才 stale。
- D7 binding 已携带 coalition/role/wave/mode/window/min separation；只有 committed/current coalition 可 active。
- duplicate 统计允许同 coalition 且 `<=k_j` 的合法 multiplicity，只计资源跨目标冲突、超额、stale/revoked/unauthorized。
- OR-Tools Min-Cost Flow 已接 optional 容量 benchmark；共享 input 的 SciPy 路径已运行，当前 OR-Tools 缺失状态可机读，且未加入默认依赖。它不是 coalition CP-SAT 参考模型。

### 10.2 P0/P1 状态表

| 缺口 | 当前状态 | 优先级 | 缺少条件/验收口径 |
|---|---|---|---|
| 既有一对一安全合同 | 已实现并保持回归 | P0 done | `k_j=1` 时 Hungarian、版本、stale、迟滞、禁止本地 rebind 不退化 |
| `target_demand=k_j` 与 demand satisfaction | 已实现 | P1 done | required/assigned/shortfall/complete 已进入 plan；部分联盟不发布 executable assignment |
| Coalition 原子 admission、能力和成员角色 | 已实现 baseline | P1 done | id/version/state、primary/reserve/retry、能力槽与 all-or-none admission 已覆盖 |
| 同时、分批、混合时序策略 | 已实现合同/baseline | P1 done | hybrid primary 数为显式 `primary_resource_count`，进入 role/wave/signature/version/binding；真实 ETA 同步与 reserve feedback 激活仍由后续跨模块验证 |
| Coalition-aware 重分配与迟滞 | 已实现成员级 gain+dwell | P1 done | 当前成员至少保持 2 s；仅硬不可行或成本改善超过 20%且 dwell 满足时替换；输出前后成员、原因和保持依据 |
| 合法多资源与 duplicate 区分 | 已实现 | P1 done | 合法 `<=k_j`、超额、资源冲突和 stale/unauthorized 均有测试 |
| OR-Tools flow baseline | 同输入容量 benchmark 合同完成，installed solver 未在本轮运行 | P2 contract done / evidence pending | 默认 requirements/path 不变；隔离环境补 objective/assignment 结果 |
| CP-SAT/MILP 小规模参考 | 未实现 | P2 optional | 表达 `sum_i x_ij=k_j z_j`、能力、同步和波次，并设置求解超时/不可行报告；不得替换默认主线 |

### 10.3 开源证据结论

OR-Tools、NetworkX、Pyomo 和 PuLP 是成熟优化工具，但都不会自动提供 MSM coalition 业务合同。`dynamic_task_allocation`、HeteroMRTA、Hierarchical-LTL-STAP、CapAM-MRTA 等仓库可作算法/场景对照；其中多个明确是 SR-ST/ST-MR 或缺少清晰许可证，不能声称已经存在可直接集成的成熟 `k_j=3` C-UAS 方案。2019 ICRA OTMaM 有直接论文证据，但本轮未找到作者官方、许可证明确的实现。

## 11. P1 协同候选预筛缺口更新（2026-07-12）

| 项目 | 当前状态 | 结论 |
|---|---|---|
| 20/30/40 m、3/5/8 s、20/40/60 deg 候选 DTO | 已实现 | 27 个稳定 candidate ID；不写死 M/N，不修改 Hungarian 主线 |
| 动态 demand 映射 | 已实现 | 保留 required/primary count、coordination mode、能力、wave interval 和 minimum separation |
| main/D6 元数据导出 | 已实现 | 输出 candidate、窗口、扇区、成员 role/wave/activation、plan/coalition version；reserve 保持 standby |
| stale/version 拒绝 | 已实现并单测 | 非 current plan、assignment version 冲突、coalition version/state 冲突均 fail closed |
| 候选结果排序 | 已实现 | 仅消费完整实测 observation；按安全、coalition completion、pair success、arrival spread、candidate ID 排序并返回前三 |
| M5N2 真实物理预筛数据 | 已执行，P1 evidence partial | baseline 与前三候选各 10 seeds，共 40 个真实 SimpleFlight episode；结果为 `0/10`、`5/10`、`2/10`、`1/10`，最佳未达 `8/10` |
| per-primary 真实物理验收 | 已具备 case/pair 结果，P1 performance open | 两个 active primary 独立验收，不要求同时到达；reserve 保持 standby 且无越权执行 |
| membership/version churn | D3 schema/export done；跨模块消费 open / unavailable | D3 已提供 canonical history；main 未写入 40-case aggregate、D6 未计算，不得将缺测推断或补零 |

本轮关闭的是 D3-owned 的候选设计、排序合同和 current-plan 元数据出口，不是 AirSim 物理闭环。P0 合同无变化：k=1 回归、版本连续、stale rejection、迟滞、reserve standby 和禁止本地改写 `global_track_id` 必须继续通过。

## 12. 独立 Primary 与成员版本语义更新（2026-07-12）

| 项目 | 状态 | 验收结果 |
|---|---|---|
| per-primary 终端授权 | P1 done | demand/coalition/assignment/plan/binding 均携带版本化字段；不要求同时到达 |
| reserve 越权阻断 | P0/P1 done | reserve binding 固定为 hold，原因 `reserve_standby_not_activated` |
| coalition 成员级迟滞 | P1 done | 独立 2 s membership clock；硬不可行立即释放，其他替换要求 `>20%` gain 与 dwell 同时通过 |
| evaluation 与 executable identity 拆分 | P1 done | 纯成本重评保留 plan_id/version 和 coalition epoch；真实 assignment/owner/activation/coalition 变化才推进；secondary takeover 显式新建 lineage |
| 审计字段 | P1 done | 输出 `membership_change_reason`、previous/current members、成本、dwell/gain 和 hold basis |
| 默认 solver | 未改变 | 继续使用 Hungarian/demand-slot；未引入新依赖 |

本轮 D3 回归基线为 `157 passed, 1 skipped`（2026-07-14）；新增 5 个计划抖动/预算确定性测试函数，既有 canonical history 和 held-scope/lifecycle case 继续通过，唯一 skip 为 optional OR-Tools installed-only test。当前 D3-owned history/hold identity 和周期性换员实现 P1 已关闭；跨模块真实多 seed、生命周期准入和 reserve demotion 仍为 P1；OR-Tools/CP-SAT/MILP 保持 P2 optional。

## 13. Seed 001 计划范围泄漏 P1 复核（2026-07-14）

| 项目 | 级别/状态 | 证据与结论 |
|---|---|---|
| hold 时新目标进入 current unassigned scope | P1 done | 三类 hold 分支改为保留上一 execution scope；普通/M-to-N 新目标回归均保持 plan ID/version/signature |
| hold 候选范围审计 | P1 done | 新增 candidate/unassigned/incomplete、pending/missing target 和 audit-only policy 字段 |
| 上一执行目标从输入消失仍被 hold | P1 done | missing previous execution target 使 previous plan infeasible，绕过 same-assignment/dwell 并输出明确目标列表 |
| T008 等后段新生航迹准入 | P1 open，main/D2 owner | T008 34.4 s birth、34.5 s confirmed 并被提交、34.6 s engageable；D3 无 truth，不能本地删除 |
| 稳定双目标阶段周期性换配 | D3-owned P1 implementation done；main+D6 real replay open | 最新 347-record/v1..v35 seed 证明 soft-feedback/search cost 与 previous execution cost 混口径；现已统一比较口径并实现同 window 累计 change budget，确定性往返不再推进版本；至少 10 seeds 真实复验仍开放 |
| reserve 后续 active | P0/P1 integration open，main runtime owner | D3 v45 中 INT-01 仍是 standby reserve；runtime 未随角色变化撤销旧 active pair |
| 真实多 seed 复验 | P1 open，main+D6 owner | 历史审计为 349 tick/v45，最新 postfix 审计为 347 records/v35，均只有 seed 1；需至少 10 个同几何 seeds |

D3-owned hold identity 缺口已关闭，未新增 P0。全量 `157 passed, 1 skipped`，唯一
skip 为 optional OR-Tools。D3 不采用固定 M/N、truth 过滤、降低高威胁门限或放宽
stale/coalition gate 来掩盖 D2 幻影；正确 fail-closed 位置是 main/D2 lifecycle
admission 进入 `TargetTrack.assignable` 之前。

## 14. 同窗口累计预算与统一迟滞成本 P1（2026-07-14）

| 项目 | 状态 | 证据与验收 |
|---|---|---|
| `max_changes_per_window` 语义 | P1 done | `d3_cumulative_window_change_budget_v1` 从 previous plan metadata 延续同 `window_id` 已接受 change count；hold/refresh 不消耗，新 window 清零 |
| candidate/previous 成本口径 | P1 done | `d3_hysteresis_current_objective_v1` 双侧包含 base edge、hard feasibility、当前 demand/unassigned；双侧排除 switch、soft-feedback FOV、slot priority/role pin search shaping |
| 往返换员稳定性 | P1 deterministic done | 小幅往返噪声和 soft feedback candidate 不再虚假通过 `delta=0.2`；同 window 第二次普通 change 在累计 2/1 时 hold |
| 硬条件优先 | P0/P1 safety regression done | missing execution target、资源 unavailable 和 plan-level owner/activation/authorization 变化立即产生新 identity；预算耗尽的资源硬失效记录 bypass |
| missing + membership hold | P1 done | previous-only target 不作为 membership change 审计；另一联盟即使要求 hold，消失目标也不进入 assignment/coalition/audit |
| 动态规模与身份 | 保持 | 实现按输入 target/resource/demand 运行，无 2v2/5v5 常量，不消费 truth，不改写 `global_track_id` |

验证日期为 2026-07-14。动因样本是最新 truth-isolated M5N2 seed 1 的 347 条
planning records 和 v1..v35；代表性旧记录为 candidate coalition `0.8868` 对
previous `2.8520`，其中 previous 含 `2.2` soft-feedback FOV，统一 base 后 previous
约 `0.6520`，候选不满足 20% 改善。本批新增 5 个确定性测试函数，D3 全量
`157 passed, 1 skipped`，接受阈值为零失败；skip 为 optional OR-Tools 未安装。
未重跑 Blocks，因此真实 10-seed churn、高威胁未分配和物理完成率仍开放，不能把
确定性关闭写成系统物理 P1 已关闭。

## 15. Actual-v2 P0 证据链与开放 P1（2026-07-14）

| 项目 | 真实证据 | 状态 |
|---|---|---|
| 2v2 plan identity | command/actual/history=`d3-plan-c3cc6d28c365/1`；24 条 history | P0 done |
| M5N2 plan identity | command/actual/history=`d3-plan-cfdd088a10e1/1`；214 条 history | P0 done |
| D6 history validation | available/unavailable=`2/0`；reasons=`{}` | P0 done |
| M5N2 feedback | churn=50；plan/membership/owner churn=0 | P1 open |
| M5N2 physical | pair/target/coalition=`2/3`/`2/2`/`0/1`；第二 primary 约 11.02 m | P1 open |
| 统计充分性 | 两个场景均仅 seed 1 | P1 open |

本批只关闭计划身份从 history 到 command 和 actual metrics 的可追溯性。目标级
`2/2` 不能用于关闭 required-primary 联盟完成；第二 primary 与多 seed 保持 P1。

## 16. 最新 M5N2 20-Case GAP 状态（2026-07-15）

| GAP/证据 | 最新状态 | 结论 |
|---|---|---|
| canonical history 写盘 | P1 evidence done for this batch | 20/20 case、3725/3725 record 可用；baseline 1869、candidate 1856 |
| 动态 N/M 与任务结构 | P1 evidence done for M5N2 | 3725 条均为 5 resources/2 targets；T001 2 primary+1 reserve，T002 1 primary |
| plan/version churn | available，0 transition | 每 case 单一 `plan_id/version=1`；首次发布不计重分配 |
| member roster churn | available，0 transition | 3555 条 membership audit 均未改变 current roster |
| owner/stale/rollback | available，均为 0 | owner 始终 center；无 stale reject 或 rollback |
| 第二 primary/coalition 物理闭环 | P1 open | 第二 primary 0/20，coalition 0/20；canonical target 12/40 不能替代联盟结果 |
| collision lineage | P1 open，main/runtime owner | 20 个第二 primary 均 `collision_stop`，但没有 collision object/category |
| candidate 晋级 | 未通过，不归类为 D3 退化 | baseline/candidate 的 D3 current plan 与成员均稳定；candidate 系统级 paired non-degradation=false |
| 真实动态 N/M | P1 open | 仍缺 3v5、5v3、目标新增、资源失效和需求切换的 AirSim 多 seed |
| 术语统一 | P1 cross-module open | 区分 `canonical target success` 与 `cooperative target diagnosis` |

本轮不新增 D3 P0。D3 计划历史写盘/churn availability 缺口已对最新 M5N2 批次关闭，
但物理联盟闭环不能因此关闭。跨 case 成员组合存在差异，第二 primary 必须按 current
plan 的 target/role 识别，不能固定资源编号。`png_ttc_2v2_seed001` 排除在本批聚合
之外；其余 tuned case 未执行，dropout=0，缺失项保持 `unavailable`。

验收命令 `python3 -m pytest -q research_modules/d3_assignment_planner/tests` 返回
`157 passed, 1 skipped`，零失败达到门限；owned-path `git diff --check` 通过。

## 17. Scalable-3D / Learning-Assist GAP（2026-07-20）

| GAP/能力 | 当前状态 | 证据与边界 |
|---|---|---|
| 三维 rule cost | P1 interface done | NED position/velocity/covariance、解析 reachability、region cost/hard gate 单测通过 |
| 稀疏候选 | P1 deterministic done | per-target top-k、不低于 demand、保留 previous feasible edge；200v200=800 edges |
| 非等量 N/M | deterministic support done | 3v5、5v3 同路径通过；真实多 seed 仍 open |
| M-to-N 稀疏槽 | regression done | 2-target/5-resource、high-threat k=3 完整联盟；all-or-none 不变 |
| action mask | P0/P1 safety done | 不可达、capacity=0、friendly conflict、version mismatch 均不可学习绕过 |
| residual formula | P1 interface done | 严格 `C_final=C_rule+alpha*tanh(delta_C)`，最终 Hungarian 不变 |
| fail-safe fallback | P0/P1 deterministic done | timeout、low confidence、OOD、invalid/error 返回逐元素相同 `C_rule` |
| shared PyTorch edge policy | minimal tested | 32-edge synthetic BC loss 下降；无固定 40,000-action head |
| 真实 BC 数据/checkpoint | P1 open | 尚无 D2/D3 trajectory labels、split、版本化 artifact 和 replay evaluation |
| shadow non-degradation | P1 open | 尚无未见 seed、收益/安全配对统计和 confidence/OOD threshold calibration |
| PPO | P2 unavailable | gymnasium/SB3 不在环境；未实现、未训练、未验收 |
| 200v200 系统性能 | P1 open | 单样本 200/200、0.621 s；无重复分布/阶段归因/闭环实时结论 |

本轮关闭的是 D3-owned 规则/接口/确定性安全 GAP，不关闭真实训练或系统 outcome GAP。
新增 13 个测试后全量为 `170 passed, 1 skipped`，零失败达到门限；skip 仍是 optional
OR-Tools。`docs/AIRSIM_INTEGRATION_PLAN.md` 已检查：本批未接 AirSim adapter、runtime
或 actor/control 合同，因此不改其已验证/未验证状态。`docs/EXPERIMENT_REPORT.md` 只
记录本地确定性样本，并明确不是 AirSim/PPO 证据。

## 18. 200×200 性能与区域计划合同 GAP 更新（2026-07-20）

| GAP/能力 | 当前状态 | 证据与剩余边界 |
|---|---|---|
| top-32 仍遍历全部 Python pair | D3-owned closed | 40,000 次全边调用降为 0；只物化 6,400 个候选 breakdown |
| 200×200 D3 成本/求解耗时 | deterministic benchmark done | 同进程 5 次中位 1904.261 ms -> 85.367 ms，22.307×；不是全栈实时验收 |
| 向量化规则语义 | D3-owned closed | 20×23 矩阵、mask、reject reason 一致，breakdown 容差 `1e-11` |
| 稀疏 Hungarian | D3-owned closed | SciPy 默认；候选二部图按连通分量求解，无候选目标走未分配代价 |
| 复杂 pair-specific 约束 | regression protected | 自动回退旧路径；尚未向量化，不影响既有语义 |
| D4 裁决的多个 secondary owner | D3 interface done | 单计划、多区域 owner、epoch/lease/source 校验通过；main/D4 尚待映射 |
| secondary/distributed k=1 | D3 contract aligned | 区域授权可不建原子联盟；显式 summary 只接受 single_member_authorized、非 atomic、完整成员和当前 lease |
| fully distributed k>1 coalition | D3 interface done | commit_required、committed、atomic、完整 ACK、成员/epoch/lease 一致才发布；运行时闭环仍 open |
| stale/old epoch/expired lease/missing ACK | D3 fail-closed done | 专项测试均拒绝；尚需 main 故障注入复验 |
| 区域计划 D6 指标 | cross-module P1 open | 尚缺 owner transition、commit latency、reject reason 和 lease violation 汇总 |
| AirSim/多 seed | P1 open | 本批未运行，不以模块 benchmark 替代系统证据 |

本轮没有新增 D3 P0。D3 全量共收集 194 项，`193 passed, 1 skipped`，零失败满足门限；
唯一 skip 为 optional OR-Tools。main 需要复跑施工中间态曾失败的 5v5、200v200、中心
失效和二级失效 module-stack 回归，并把 D4 区域裁决接入
`plan_regional_authority()`。在该接线完成前，多 owner 和 fully distributed 仍标为
接口已实现、系统未集成。

`docs/AIRSIM_INTEGRATION_PLAN.md` 已复核。本轮未改变 AirSim adapter、actor、控制、
话题或 settings，因此不改该文件。实验文档已新增本地性能和合同证据，并明确未运行
AirSim、多 seed 或全栈实时验收。

本次 D4-D3 复审关闭了 distributed k=1 被误判为缺少原子提交的合同缺口。修复只按
需求数区分 single-member authority 与 atomic coalition commit；k>1 的 committed、
atomic committed、全 ACK、成员/协调者/epoch/lease 一致性门限保持不变。main 仍需
把 D4 `CoalitionCommitSummary.commit_required` 原样映射并运行 module-stack 回归。

## 19. 故障代际 Fence GAP 更新（2026-07-20）

| GAP/能力 | 当前状态 | 证据与边界 |
|---|---|---|
| 分配未变时 forced replan 不升版 | 语义保持 | 普通重规划仍正确返回原 identity，不用于故障隔离 |
| D4 owner change generation fence | D3-owned closed | `advance_authority_generation()` 严格 +1 并正常 publish |
| assignment/coalition 不变 | deterministic done | k=3 成员、角色、coalition id/version 和执行签名一致 |
| stale/rollback/重复版本 | fail-closed done | expected mismatch、旧 source 和 duplicate fence 均拒绝 |
| fence 伪造执行变化 | fail-closed done | coalition 篡改及 owner/授权变化不允许进入 fence 路径 |
| D4/D7 安全边界 | interface done | metadata 标记非授权并要求 D4 gate；D7 不得仅凭 fence continue |
| 50v50 中心故障接线 | cross-module blocker open | main 尚未在 D4 裁决前调用接口和复跑场景 |

发现时该问题阻断 50v50 中心故障区域裁决，属于运行级 P0 集成阻塞。D3-owned 接口和
发布门控已关闭，系统级状态仍为 main/D4 接线待验。新增 5 个测试后全量共 199 项，
`198 passed, 1 skipped`，零失败达到门限。AirSim 集成文档已检查：本轮没有修改
AirSim adapter、settings、actor 或控制合同，因此无需更新；scalable 3D runtime 由
main 另行接线，D3 不跨模块修改。

## 20. BC/PPO/Shadow 研究管线 GAP 更新（2026-07-20）

| GAP/能力 | 当前状态 | 证据与剩余边界 |
|---|---|---|
| 可复现学习数据 schema | legacy v1 superseded by section 23 | 原 scenario+seed split 存在跨场景同数值 seed 泄漏；v1 不再接受 |
| truth/edge leakage | deterministic fail-closed | allow-list entity schema，不保存原 ID/metadata；同 seed 跨 split 和重复 frame 均拒绝 |
| model bundle | D3-owned implemented/tested | manifest+state_dict+SHA256；feature/schema/policy/split/normalization/guardrail/training/promotion 完整，weights-only strict load |
| bundle fallback | P0/P1 safety done | missing、SHA、feature/policy mismatch 和 version constraint 返回逐元素相同规则矩阵 |
| multi-episode BC | pipeline implemented/synthetic tested | frame mini-batch 学习 rule edge/residual/advice，输出 train/validation loss 与 whole-seed metrics |
| native PyTorch PPO | P2 research pipeline implemented | clipped actor-critic、GAE、pooled value、bounded sparse residual、low-frequency advice；counterfactual reward 仍经 deterministic solver |
| fixed 200x200 action head | closed | shared edge network 对 3v5、5v3、200 candidate edges 输出同形 residual，无 roster-size 参数 |
| paired shadow evaluator | pipeline implemented/synthetic tested | 同 seed rule/proposal 成本、high-threat unmet、churn、duplicate/hard violation、P50/P95、fallback 可报告；规则矩阵不变 |
| assist promotion gate | fail-closed implemented | manifest 必须 >=20 unseen test seed、零 fallback、安全和成本非退化；19 seed 即使手写 recommended 也拒绝 |
| 正式训练/准入 | development BC complete; P1 admission open | 正式三维质点数据 900 episode/1604 帧已训练 v3 shadow-only bundle；内部 test 不是外部保留证据，1000-1019、AirSim outcome、OOD/confidence/deadline 准入仍开放 |

以下 30-seed、60-frame synthetic smoke 属于 legacy v1：split 为 23/1/6 seed 和 46/2/12 frame。BC train
loss `1.1001 -> 0.5014`、validation `0.3768`；46-transition PPO 更新指标有限；test
shadow P50/P95=`0.281/0.350 ms`，fallback/duplicate/hard violation 均为 0。但
assignment-cost non-degradation=false，test 只有 6 seed，且 source synthetic，所以
promotion 为 `false/unavailable`。该结果把旧“数据/checkpoint/PPO 管线未实现”改为
“管线已实现、真实数据和准入仍开放”，不关闭 outcome GAP。

新增 16 个专项测试后 D3 全量共收集 215 项，最终为 `214 passed, 1 skipped`
（6.95 s），零失败达到门限；唯一 skip 是 optional OR-Tools installed-only case。
`research_modules/d3_assignment_planner/docs/AIRSIM_INTEGRATION_PLAN.md` 已检查：没有修改
adapter、actor、settings、控制、D7 或 runtime 接口，因此无需变更。实验文档只记录
synthetic smoke，并明确不是 AirSim、正式 PPO 收益或 promotion 证据。

## 21. 真实 Episode 学习帧证据 GAP 更新（2026-07-20）

| GAP/能力 | 当前状态 | 证据与剩余边界 |
|---|---|---|
| main 无法取得真实规划矩阵 | D3-owned closed | 公开 `latest_planning_evidence` 同时保存 rule/effective `CostMatrixResult` 和计划上下文 |
| main 重建私有矩阵可能漂移 | D3-owned closed | `build_latest_learning_frame_record()` 直接消费 planner 最近成功帧；synthetic generator 已移除私有调用 |
| shadow/assist/fallback 混淆 | deterministic closed | `rule_only/shadow_proposal/assist_effective/rule_fallback` 分离；fallback 要求 effective 与 rule 完全一致 |
| held/unchanged/forced replan | deterministic closed | 当前 timestamp/previous version 与当前输入矩阵可记录，不复用旧矩阵 |
| regional authority | D3 interface done | 有效 authority 记录 `selection_source=regional_authority`；拒绝路径清空旧 payload 并给 reason |
| 失败后返回陈旧帧 | fail-closed done | stale、invalid regional、fence、unmatched publish 和一致性失败均 `available=False`、payload 为空 |
| 外部反向修改 planner | deterministic closed | ID 匿名化，array 为 immutable buffer，mapping 只读；修改生成 record 不影响 retained evidence |
| 在线总线/仿真身份泄漏 | D3-owned closed | 证据不进 plan metadata/DTO；track/resource/assignment 仅 ordinal token，无 truth/actor/object/upstream metadata |
| 真实整 seed 导出 | scalable-3D closed; AirSim open | main 已形成 900 episode、1604 帧三维质点正式数据；尚未形成等价 AirSim sequential dataset |
| 真实 shadow/assist 准入 | P1 open/unavailable | internal-test 已完成但存在成本轻微退化和 163/322 OOD 回退；仍缺外部 seed 1000-1019、deadline/OOD/confidence 标定和 paired non-degradation |

本轮把“D3 已有 frame builder 但无法取得真实调用使用的矩阵”从接口 GAP 改为
implemented/tested；它不关闭真实数据与系统 outcome GAP。新增 11 个专项测试覆盖首帧、
held/unchanged/forced replan、shadow、assist、learning/solver fallback、regional 正负例、
失败清旧帧、外部修改隔离和 1x3/3x2/7x4。2026-07-20 D3 全量收集 226 项，结果
`225 passed, 1 skipped`，零失败达到门限；唯一 skip 是 optional OR-Tools。

`README.md`、`PLAN.md`、三份 D3 review/GAP 和模块内四份主题文档已同步。AirSim 文档
只新增 recorder 接线计划，明确本轮未修改 adapter、settings、actor/control 或运行真实
episode。根级 main/system 文档不在 D3 owned paths，由 main 在集成 helper 后同步实际
seed/frame/result。

## 22. 区域资源提示到候选图 GAP 更新（2026-07-20）

| GAP/能力 | 当前状态 | 证据与剩余边界 |
|---|---|---|
| D4 recommendation 无 D3 公共入口 | D3-owned closed | `regional_planning_hint` 可接 DTO 或严格中性 mapping；不导入 D4 |
| 提示来源与时效 | deterministic fail-closed | source plan 精确匹配，created/expiry 和逐区域 lease 同时有效 |
| quota/transfer 资源守恒 | deterministic fail-closed | projected、总 delta=0、逐区域 transfer 净额一致；非法提示有 reason 并回退 |
| committed/coalition/reserve 保护 | deterministic closed | previous assignments/coalition members 全保护，reserve 按 post-quota 向上取整 |
| 跨区许可只写 metadata | closed | 合法 route 真实修改 candidate mask，1-to-1/M-to-N 均由 Hungarian 选中 |
| transfer cardinality | deterministic closed | route 固定互斥资源池 + 全局资源唯一性，actual 不超过 allowance |
| D5/learning/迟滞兼容 | regression covered | hard edge 不重开，learning 只见受约束 mask，既有反馈/版本路径保留 |
| D6 审计字段 | D3 interface done | available/considered/applied/rejected、identity/reason、allowed/actual 和跨区总数 |
| main/D4 映射 | cross-module P1 open | 尚未把 `RegionResourceRecommendation` 映射为 DTO，也未处理 reset 后 advisory 生命周期 |
| AirSim/多 seed/性能 | P1 open | 无新 episode、正式多 seed、时延分位数或物理结果 |

本轮把“D4 区域聚合建议只能停留在 metadata/离线报告”改为“D3 候选约束合同已实现，
系统接线待完成”。新增 14 个 fixture case；2026-07-20 全量收集 240 项，结果为
`239 passed, 1 skipped`，接受门限为零失败，skip 是 optional OR-Tools。该证据不关闭
main-owned 时序接线、D6 多 seed 非退化、AirSim 或物理拦截 GAP。

## 23. 跨场景数值 Seed 隔离与流式写出 GAP 更新（2026-07-20）

| GAP/能力 | 当前状态 | 证据与剩余边界 |
|---|---|---|
| 同 seed 跨 scenario/scale 泄漏 | D3-owned closed | split identity 改为纯数值 seed；2v2/5v5 风格双 scenario、多 episode/多 frame 复用测试通过 |
| episode/frame 原子性 | deterministic closed | 完整 catalog finalize；同 seed 任一 frame 改 split 即拒绝，重复 frame 由唯一键拒绝 |
| 三 split 数量与零交集 | fail-closed closed | 按唯一数值 seed 数量分配；少于 3、任一 split 空、声明 unseen 不足均拒绝 |
| dataset/split schema | v2 implemented/tested | `d3_learning_dataset_v2` + `d3_numeric_seed_atomic_split_v2`；manifest 固化 split 参数、逐 split seed/episode/frame 数、split hash、frame SHA |
| bundle/shadow schema | v2 implemented/tested | bundle v2 绑定 dataset/split v2；shadow report v2 按数值 seed 聚合；v1 稳定拒绝 |
| hash/loader 篡改 | deterministic fail-closed | 逆序输入同 canonical frames/manifest/hash；frame SHA、split 映射、统计和 policy 均重算 |
| training/shadow unseen 计数 | closed | BC/PPO/shadow 先验完整三分；whole-seed/unseen 不再把同一 seed 的多个 scenario 重复计数 |
| D3 writer 全量内存 | D3-owned closed | iterator + 临时 SQLite + 批次提交 + 增量 SHA；输入不再 `tuple(sorted(...))` |
| main batch finalize 全量内存 | integrated/closed | scalable main 已把 `iter_learning_frame_records(...)` 直接传给 writer，不再完整读取/构造 tuple |
| 正式模型与性能 | development evidence complete; P1 promotion open | v3 BC shadow-only 权重、loss、共同规则成本和 5 档时延已生成；无 AirSim/物理收益，internal-test 不构成 assist promotion |

200v200 dense fixture 有 40,000 candidate edge；单帧 canonical JSON 为 5,854,691 bytes，
NumPy payload 加 edge tuple 浅层约 5,161,640 bytes。40 帧时，main 现有文本加上述对象的
保守下界超过约 440 MB，尚未计 `read_text`/`splitlines` 重复和 JSON 临时对象。因此
D3 API 的有界写出已实现，但正式 200v200 全链路内存 GAP 只有 main 调用 iterator 后才能
关闭。

2026-07-20 D3 全量收集 244 项，结果为 `243 passed, 1 skipped`，接受门限零失败达到；
唯一 skip 是 optional OR-Tools installed-only benchmark。`README.md`、`PLAN.md`、D3
review/GAP、模块内 `MODULE_PRINCIPLES_CN.md`、`ALGORITHM_AND_IMPLEMENTATION.md`、
`AIRSIM_INTEGRATION_PLAN.md`、`EXPERIMENT_REPORT.md` 和 docs index 已同步。AirSim 文档
明确本批未改 adapter/settings/actor/control、未运行 episode；实验文档只记录软件合同。
根级 `docs/**`、main/scalable 调用点不在 D3 owned paths，由 main 汇总同步。

## 24. Learning 训练与 Promotion Fail-Closed GAP 更新（2026-07-20）

| GAP/能力 | 当前状态 | 证据与剩余边界 |
|---|---|---|
| BC/PPO 消费 test seed | D3-owned closed | BC 只接收 train/validation、PPO 只接收 train；任一训练 API 遇 test 报错，BC whole-seed metric 无 test |
| frame truth/identity 泄漏 | deterministic closed | v2 完整字段 allow-list；任意层级 truth/actor/identity/entity-ID/UUID/vehicle-name 键拒绝，匿名字段强类型校验 |
| candidate hint 重开 hard reject | safety closed | 候选索引、assistant 返回与 solver mask 均和 reject-reason allow mask 求交；shape 错误失败关闭 |
| bundle 与数据内容脱钩 | integrity closed | bundle/promotion evidence 同时绑定 split SHA、canonical frame SHA、state-dict SHA；错配拒绝 |
| promotion 口径可绕过 | safety closed | assist 强制 eligible 正式 test paired evidence、严格类型、>=20 unseen seed、零 fallback、安全/成本非退化；bypass/validation/non-eligible 拒绝 |
| shadow objective 不可比 | metric closed | rule/proposal 方案统一按 `rule_cost_matrix_v1 + unassigned_costs` 重评分，不比较不同矩阵 objective |
| 正式权重/promotion | development weight complete; P1 promotion open | 本地 ignored v3 权重已冻结并绑定 SHA；1000-1019 未验收，成本轻微退化且 OOD 回退高，assist 明确未授权 |
| AirSim/200v200 模型收益 | P1 open/unavailable | 本轮未运行 AirSim 或全栈模型性能实验；同步 timeout 仍不可抢占 |

负例覆盖 test-seed 输入、指标隔离、递归字段、mask 不一致、frame/evidence hash、证据
split/eligibility/bypass/type 和共同成本基准。2026-07-20 D3 全量收集 252 项，结果为
`251 passed, 1 skipped`，零失败达到门限；唯一 skip 是 optional OR-Tools installed-only
benchmark。上述关闭项是 D3 software contract，不把模型提案升级为计划或执行授权。

## 25. 200×200 学习帧导出 CPU/内存 GAP 更新（2026-07-20）

| GAP/能力 | 当前状态 | 证据与剩余边界 |
|---|---|---|
| 候选边重复 demand 构造 | D3-owned closed | 6,400 edge 从逐边构造改为 200 target 缓存；frame build 48.19 -> 22.99 ms |
| reject reason 重复扫描 | D3-owned closed | frame 复用 action-mask reason count；硬拒绝内容不变 |
| JSONL identity 递归标量调用 | D3-owned closed | 改显式容器栈；递归字段拒绝正负例保持，decode/validate 95.92 -> 56.09 ms |
| SQLite 保存完整 payload | D3-owned closed | SQLite 只存 key/offset/size；payload 使用临时 JSONL sidecar |
| finalization 二次 decode/rebuild/encode | D3-owned closed | 受控 split 占位符流式替换；6-frame median 910.20 -> 243.65 ms |
| 构造后可变状态逃逸校验 | fail-closed closed | writer 重新校验 mask/shape/finite/anonymous schema；真值键和 mask 篡改均拒绝 |
| schema/content/hash 漂移 | deterministic closed | expected legacy semantic bytes 与优化输出完全相同；正逆序、frame SHA、manifest 回归通过 |
| D3 finalization 峰值 | improved, not zero-copy | 匹配 cProfile/Tracemalloc 14,575,699 -> 12,725,690 B，下降 12.69% |
| 联合 staging 的 D3 归因 | closed by clean-tree integration evidence | postopt 三 seed 的 D3 stage 为 0.0917/0.1129/0.0999 s；其余耗时不归入 D3 |
| JSON `tolist/dumps` | residual P2 optimization | 已为主要热点；无新依赖和无格式变化条件下保留，后续只能 optional adapter 对照 |
| 正式数据/模型准入 | data/BC development closed; P1 admission open | 900 episode 与 BC 开发训练已完成；仍缺外部 20 seed 非退化、OOD/confidence/deadline 标定和 assist promotion |

本轮没有新增 P0。top-32 单帧约 2.20 MB、九场景 D3 帧约 27.86 MB，因 schema/content
保持要求没有减少。微基准属于同机开发归因证据，不是硬实时、AirSim 或 200v200 全栈
验收。D3 全量收集 255 项，结果 `254 passed, 1 skipped`，唯一 skip 为 optional
OR-Tools，零失败达到门限。

`README.md`、`PLAN.md`、`MODULE_PRINCIPLES_CN.md`、
`ALGORITHM_AND_IMPLEMENTATION.md`、`EXPERIMENT_REPORT.md` 和 D3 review 已同步。
`AIRSIM_INTEGRATION_PLAN.md` 仅纠正 main 已采用 iterator 并记录未运行 AirSim；没有改变
settings、actor、camera、control 或 episode 合同。M-to-N 算法和成员合同未变化，因此
`D3_M_TO_N_ASSIGNMENT_AND_SCHEDULING_REVIEW.md` 检查后无需修改。

## 26. Clean-tree 200v200 复测 GAP 更新（2026-07-20）

| GAP/能力 | 当前状态 | 证据与剩余边界 |
|---|---|---|
| D3 优化是否进入 main 生成链 | closed | producer commit `4052d9411363c39d52100c0e3a4f60ee88443cab`；`repository_dirty=false` |
| D3 stage 归因 | closed | seed 930/931/932 分别为 0.0917/0.1129/0.0999 s；不是此前 74-76 s 联合耗时来源 |
| D3 数据收口 | closed for probe | 6 帧正常最终化，train/validation/test 各 2 帧；在线 truth 使用为 0 |
| 联合 finalization 归因 | protected/open by owner | 总值 `116.5624 -> 7.7377 s` 同时包含 D3/D4/D5，不能全部归因 D3 |
| 正式 900-episode 生成 | closed | 正式目录包含 900 episode、1604 D3 帧、100 seed、五档规模，hash 与切分审计通过 |
| 正式训练和晋级 | BC development closed; P1 promotion open | BC shadow-only 权重已训练；PPO 未启动，外部 seed 1000-1019 与 assist promotion 未完成 |

同一对照中，总生成 `467.8007 -> 262.2866 s`，artifact stage
`225.9243 -> 126.4682 s`，episode run `125.2205 -> 127.9871 s`。这些总量用于确认集成
效果，不替代模块归因。D3-owned 重复编码/最终化性能缺口保持关闭；本轮没有新增 P0。

模块 README、PLAN、五份指定主题文档、D3 review/GAP 已同步检查。M-to-N 需求槽、联盟
成员和调度合同没有变化，专项 M-to-N review 无需修改。

## 27. 正式行为克隆开发模型 GAP 更新（2026-07-20）

| GAP/能力 | 当前状态 | 证据与剩余边界 |
|---|---|---|
| 正式数据完整性 | closed | 900 episode、1604 帧、100 seed；train/validation/internal-test 为 962/320/322 帧，frame/split SHA 和 1000-1019 排除均通过 |
| 五档规模覆盖 | closed for development data | 5/20/50/100/200 均有数据与时延；动态目标数未被写死 |
| BC 类别不平衡 | implemented/tested | 正边约 3.2%，训练支持绑定到配置的正类权重上限；正式 run 使用 16，不改变硬门控或求解器 |
| rule-only/BC shadow evaluator | implemented/tested | 输出残差损失、边排序、计划成本、需求满足、duplicate/hard violation、churn、fallback 和分档时延 |
| bundle provenance | v3 implemented/tested | 绑定 data/split/model SHA、feature schema、训练配置、训练源码 SHA、Git 基线提交/角色、工作树状态和训练日期 |
| 开发权重误晋级 | P0 safety closed | admission 固定 development/shadow-only；assist 返回 `bundle_shadow_only`，规则路径不变 |
| 权重版本管理 | local development closed; long-term open | `.pt` 仅在 ignored `outputs/`，tracked results 只存 SHA/定位；当前无 Git LFS，长期制品待 main 归档 |
| 内部 test 质量 | available, not passing promotion | 排序 AUC 0.8031、计划完全一致 0.6770、成本差 +0.022345；需求满足不变，duplicate/hard violation 为 0 |
| OOD/置信门限 | P1 open | internal-test 163/322 帧因“任一边超 6σ”回退，min confidence 约 0.5；需外部 seed 标定 |
| 外部保留集 | P1 open | seed 1000-1019 未消费；内部 test 不能写成最终 20-seed 准入结论 |
| PPO | unavailable/not started | 本任务没有把行为克隆演示或规则 reward 分量伪装为强化学习回报 |
| AirSim/物理收益 | P1 open | 本批为三维质点离线训练，无 AirSim、飞行或物理拦截证据 |

本轮没有新增 P0。正式 BC 开发管线和 bundle fail-closed 语义已闭合，P1 卡点转为外部
1000-1019 配对验证和门限标定。当前结果不支持把学习策略接入 assist：规则成本轻微增加，
且约一半内部 test 帧回退。main 应先保留 rule-only 默认路径，再调度 D6 对外部批次做
共同口径验收。

新增测试后 D3 全量收集 258 项，结果 `257 passed, 1 skipped`；唯一 skip 为 optional
OR-Tools。`AIRSIM_INTEGRATION_PLAN.md` 已检查，本轮没有改变 AirSim adapter、settings、
actor、episode 或控制接口，无需更新。M-to-N 专项 review 已检查，需求槽、角色和时序合同
未变化，无需更新。

## 28. C1 共享 Seed 注册表 GAP 更新（2026-07-21）

| GAP/能力 | 当前状态 | 证据与剩余边界 |
|---|---|---|
| D3 与跨模块 split 映射歧义 | D3-owned closed | 正式 100 seed 的 60/20/20 映射与 main detached registry 逐项相同 |
| registry schema/policy | fail-closed closed | 只接受 shared schema/policy v1 和 D3 v2 ordering compatibility |
| registry 完整性 | fail-closed closed | file/content/assignment/source 四类 SHA 均验证；自洽篡改仍须通过 D3 算法重算 |
| seed 全集与原子性 | fail-closed closed | manifest 与 records 必须完整覆盖 source 100 seed，无缺失/增加；同 seed 不跨 split |
| 保留 seed 隔离 | fail-closed closed | 1000-1019 不允许进入 manifest 或 records；正式交集为 0 |
| 原数据和旧 bundle 兼容 | closed | 验证只读；默认 loader 和旧非联合开发 bundle 路径不变，无原地迁移 |
| 新 bundle/report provenance | implemented | 启用 registry 后写入 bundle `training_results`；正式入口另写 binding sidecar |
| D3 当前 BC 准入 | unchanged/open | 仍为 development/shadow-only；共享 split 一致不关闭外部 20-seed 非退化门 |
| C1 联合训练 | cross-module P1 open | D4/D5 尚需同 registry、可用 label/ACK/reward、join schema 和联合保留 seed 证据 |

正式只读验证覆盖 900 episode、1604 帧和 100 个训练 seed。registry file/content/
assignment/source SHA 分别为 `68608d29...032f`、`29eb6895...f146`、
`31c6a3fc...6ab5`、`2ab928a4...15f`，四个输入文件前后 SHA 相同。新增负例覆盖 schema、
policy、content、assignment、源 SHA、缺 seed、多 seed、保留 seed、跨 split 和参数成对
要求。D3 全量结果为 `269 passed, 1 skipped`。

本项不修改 Hungarian、`C_final=C_rule+alpha*tanh(delta_C)`、硬门控、迟滞、计划版本
或 D7 binding。PPO 未启动，现有 bundle 未晋级。D3-owned P1 split ambiguity 已关闭；
C1 是否可启动由 main 汇总 D4/D5 数据条件后决定。

## 29. 正式分配数据全样本准入 GAP 更新（2026-07-21）

### 已关闭

- **P1 正式数据逐样本审计**：已新增只读流式审计器并扫描全部 883 MiB frame 数据。
  900 个实际 episode、1604 个决策帧、3658815 条候选边、117304 条选中动作均完成
  schema、有限数值、维度、索引、容量、需求槽、切分、匿名身份和前序版本复核。
- **P1 来源绑定与篡改检测**：manifest、frames、训练 registry、共享 registry、生成摘要、
  episode 进度和批量导出摘要共 7 个文件绑定冻结 SHA256；源文件审计前后哈希一致。
  审计 JSON 另有规范内容摘要，可供 D6 带外复核。
- **P1 统计口径歧义**：规范 seed/episode 身份明确为 60/20/20，实际场景 episode 为
  540/180/180，决策帧为 962/320/322，候选边为 2229182/721445/708188。报告不再把
  seed 比例写成样本比例。
- **P1 truth/dirty/identity 审计**：在线 truth 使用、脏 episode、非法 `global_track_id`
  字段、容量/需求/索引/版本违规均为 0。194 个未导出帧原因原样保留，没有补旧帧。

数据结构状态由 `pending` 更新为 `complete`。专项 10 项和全量 280 项通过，结果为
`279 passed, 1 skipped`；唯一 skip 为 optional OR-Tools。

### 仍开放

- **P1 运行计划绑定**：正式 learning frame 只有匿名 token 和 `previous_plan_version`，
  current owner/current version、stale runtime rejection 为 `unavailable`。需要 main 的
  版本化运行记录，不能由 D3 frame 推断。
- **P1 ACK 与 outcome 归因**：真实 applied ACK、执行结果及其 AssignmentPlan 绑定未形成。
  `feedback_result`/`hysteresis_result` 是字符串诊断；`reward_components` 是规则教师分量，
  都不能替代运行结果。
- **P1/P2 学习准入**：因果/反事实 reward、同 seed paired shadow 非退化和外部保留 seed
  验收仍未闭合。PPO、assist、online authority 和权重写入保持关闭，规则代价与需求槽
  Hungarian 继续为默认路径。
- **跨模块 D6 消费**：D3 已给出 tracked JSON 和文件 SHA，D6 尚需独立校验并与 D4、D5
  全样本证据合并。该项由 main/D6 负责，不回写或修改正式 D3 数据。

当前没有新增 P0。D3 全样本数据 GAP 已关闭，跨模块总体准入仍为 `partial`。

## 30. 运行计划 ACK GAP 更新（2026-07-21）

### 已关闭

- **D3-owned ACK 消费接口**：已实现
  `d3_assignment_plan_runtime_ack_evidence_v1`，不依赖 main 包，不发布或修改计划。
- **来源序号和哈希验证**：D3/D7 完整 envelope 的正整数 sequence 和规范 payload
  SHA-256 必须与 ACK 一致；错误或缺少来源失败关闭。
- **current plan/binding 验证**：plan id/version/schema、decision id、assignment
  inventory、资源/`global_track_id`、coalition/version/role、owner 和统计逐项复核。
- **学习采用口径**：只有 assist + applied + bundle-loaded 且整个来源链通过才标为
  available；shadow、规则教师分量和 accepted plan 均为 unavailable。
- **结果自报隔离**：ACK 中 physical outcome/reward 必须为 false；无独立 D6 sidecar 时
  自报 true 被拒绝。

跨导入路径类身份问题已关闭。consumer 接受项目现有顶层与 namespaced 两种明确 D3
模块/类身份，同时要求精确数据类字段集合和受支持计划 schema；任意鸭子类型继续失败
关闭。consumer 源码不导入 main，main 集成栈只在 D3 自动化测试中导入。

专项 24 项和自动化 3v3、seed 7、1.2 秒真实 main 集成测试通过。集成测试最终
assignment/binding/control 为 3/3/3，held=0，online truth use=0。D3 全量 304 项，结果
`303 passed, 1 skipped`。

### 仍开放

- **冻结正式数据 ACK 覆盖**：900 episode/1604 frame 生成于 producer 之前，逐样本
  runtime ACK 仍为 unavailable，不能回填该 3v3 自动化集成测试。
- **D6 离线 join**：需按 source sequence/hash、plan id/version 和时间窗连接 D3
  evidence、D7 控制、独立 outcome/reward sidecar，并保留 availability。
- **学习与策略准入**：可归因 reward、因果/反事实证据、同 seed paired shadow 和外部
  保留 seed 未闭合。PPO、assist、online authority 继续 false。

当前没有新增 P0。原“D3 无严格 ACK 消费器”已关闭；跨模块正式采用与结果归因仍为 P1。

## 31. 已采用计划窗口归因 GAP 更新（2026-07-21）

### 已关闭

- **ACK 到 D6 observed outcome 的 D3 适配器**：已实现
  `d3_runtime_plan_window_reward_evidence_v1`。它只接受已验证 ACK 和带外部规范载荷
  SHA-256 的 D6 v1 联接结果，不依赖 main/D6 包。
- **来源、消费和窗口绑定**：plan id/version、owner、source/consumption/ACK sequence、
  D3/D7 payload hash、ACK evidence hash、D6 result hash、资源-航迹、联盟角色、
  occurrence、执行签名和时间窗均进入输出。
- **窗口和刷新治理**：同资源重叠、非单调 ACK、计划版本回退、occurrence 缺口、刷新类型
  错误、同 identity 执行签名变化均失败关闭。
- **真值与自报隔离**：在线真值使用非零、ACK/D6 自报正式 reward、反事实或因果结果均
  拒绝。D6 离线 truth identity 不进入 D3 输出。
- **缺失值口径**：六个原始 reward 分项逐项保存 availability/reason；当前值均为 null，
  不补 0。五米事件和距离进展保持 observed diagnostic，不能升级为 causal reward。

2026-07-21 专项为 `16 passed`，含 1 个真实 main 三维质点 3v3、seed 41、1.2 秒 D6 自动
结果消费样本。D3 全量为 `319 passed, 1 skipped`，唯一 skip 为 optional OR-Tools。

### 仍开放

- **P1 正式 reward 证据**：当前只有命令、采用和观测窗口，没有同 seed paired
  intervention、counterfactual 或 causal attribution。`formal_d3_runtime_reward` 保持
  unavailable。
- **P1 计划级原始分项**：D6 v1 binding window 没有完整提供高威胁覆盖、总代价、未满足
  槽、计划抖动、过期和安全拒绝的可归因运行结果。现有 `OfflineRewardComponents` 仍是
  规则教师诊断。
- **P1 外部验收**：seed 1000-1019、正式 paired shadow、非退化和 multi-seed 学习采用
  结果未完成。PPO、assist、online authority 保持 false，规则回退为 true。
- **历史数据覆盖**：冻结 900 episode 生成于 ACK producer 之前，保持不可回填。

本轮没有新增 P0。原“D6 离线 join 尚无 D3 consumer”改为已关闭；“正式可归因 reward”
继续为 P1，且缺失原因已由版本化合同固定。

## 32. 保留 Seed 配对干预 GAP 更新（2026-07-21）

### 已关闭

- **P1 D3 配对实验清单边界**：新增版本化 specification/manifest，严格覆盖 seed
  `1000-1019` 和每 seed 两个隔离 arm。场景配置、初始状态、输入快照、D1/D2 lineage、
  规则代价、bundle、阈值、安全外壳及计划版本均按 SHA/版本配对。
- **P1 control/treatment 语义**：control 固定走规则/Hungarian；treatment 只在离线仿真
  干预 arm 内允许有界学习残差影响计划。它不开放 online assist 或 authority。
- **P1 安全与失败关闭**：动作掩码、可达性、容量、版本、迟滞、安全门和规则回退进入
  执行收据合同。缺 arm、seed 重复、配对哈希不等价、bundle/阈值未冻结、stale plan、
  非有限值、在线 truth key 和非法身份改写均拒绝。
- **P1 证据分层**：manifest 分别报告 paired input equivalence、isolated treatment applied、
  runtime ACK、outcome、counterfactual 和 causal。ACK 引用复用现有 verified ACK 对象；
  D3 不计算 D6 outcome、反事实或因果值。

### 仍开放

- **P1 正式执行证据**：本轮没有运行 seed `1000-1019`，因此 execution receipt、完整
  runtime ACK inventory 和 treatment applied 结果仍为 unavailable。
- **P1 D6 结果与因果统计**：outcome、counterfactual、causal 仍需 main/D6 以独立
  sidecar 按 pair/arm/hash 联接。D3 合同不能自行关闭该缺口。
- **P1 准入结论**：尚无正式同 seed 性能和非退化结果。PPO、assist、online authority
  继续关闭，规则回退继续启用；冻结 900-episode 数据不修改、不回填。

本项关闭了“D3 没有正式保留 seed 配对干预 specification/manifest”的接口缺口，没有
关闭正式实验和因果证据缺口，也没有新增 P0。2026-07-21 专项 `36 passed`，D3 全量
`355 passed, 1 skipped`；唯一 skip 为可选 OR-Tools。

## 33. 保留 Seed 隔离执行 GAP 更新（2026-07-21）

### 已关闭

- **P1 D3 本地执行入口**：`execute_offline_paired_intervention(...)` 已能一次消费完整
  specification 和 20 个 `PlanningFrameEvidence`，真实运行 40 个隔离 arm，并返回共享
  配对报告、40 份 `PairedInterventionExecutionReceipt` 与严格 manifest。main 不再需要
  复制 D3 模型加载和矩阵求解逻辑。
- **P1 同帧输入一致性**：输入快照、规则矩阵和动作掩码均重新计算规范 SHA-256。两条
  arm 的前序计划、时间戳、矩阵、掩码和版本不一致时失败关闭；control 复放 binding 与
  原规划帧不一致也会拒绝。
- **P1 development bundle 隔离加载**：执行器校验 manifest 文件 SHA、state dict SHA、
  policy version、v3 development/shadow-only admission、保留 seed inventory 和权重
  有限性。生产 assist 加载器未放宽，同一 development bundle 仍被
  `bundle_shadow_only` 阻断。
- **P1 运行门控与规则回退**：分布外输入、低置信度、deadline、非有限权重、模型异常、
  manifest/版本/权重不一致均产生真实 treatment fallback receipt。规则矩阵和硬安全动作
  掩码保持不变，PPO、online assist、authority 和 runtime publication 均未开放。

### 仍开放

- **P1 正式 1000-1019 episode 执行**：本轮 7 项专项使用临时冻结 v3 bundle 和匿名单元
  规划帧验证 API，未消费 main 的正式三维 episode。正式 40 臂产物、逐 seed applied/
  fallback 分布和多周期计划结果仍需 main 调度生成。
- **P1 D6 非退化与结果侧车**：D3 配对报告只计算规划层规则成本、需求缺口、抖动、硬约束、
  回退和推理时延。runtime ACK、物理 outcome、counterfactual、causal 和正式 reward 仍为
  unavailable，不能由 D3 自行补齐。
- **P1 模型准入**：尚无正式保留 seed 的成本/安全非退化、分布外率、deadline 分位数和
  applied ACK。bundle 保持 development/shadow-only，PPO/assist/authority 继续 false，
  rule fallback 继续 true。

本项关闭原“D3 没有 paired intervention 实际执行 API 和真实收据生成器”的模块缺口；
正式主流程执行和 D6 独立判定仍是 P1。没有新增 P0。专项 `7 passed`，D3 全量收集 363
项，结果 `362 passed, 1 skipped`，唯一 skip 为可选 OR-Tools。

## 34. 保留 Seed 精确重放 GAP 更新（2026-07-21）

### 已关闭

- **P1 control 重放状态缺失**：`PlanningFrameEvidence` 已保存 `forced_replan`、执行所有权、
  激活、授权、节点/链路、迟滞窗口计数和联盟执行语义。匿名化不再把状态机输入清空。
- **P1 roster 生命周期重放**：前序计划独有目标和资源使用 `previous_target_*` 与
  `previous_resource_*`，既保留缺目标/缺资源判定，又不泄漏真值、Actor 或对象身份。
- **P1 严格控制臂校验**：`control_plan_replay_mismatch` 保留并加强。control 必须精确复现
  binding、执行签名、版本、窗口、决策状态、changed 和规模；篡改 binding 负例继续失败
  关闭。
- **P1 当前源帧阻塞复核**：main nominal 5v5、duration 2.2、seed 1000-1019 的 20 个源帧
  已在内存中通过 D3 执行器。40 个 arm 完成，20 个 control 状态为 15 个 unchanged、3 个
  held、2 个 replan ACK，失配为 0。冻结 development bundle 正常读取。

### 仍开放

- **P1 正式产物与 D6 sidecar**：本轮不修改 main runner，也未写出完整 D3/D4 正式目录。
  main 仍需重跑并落盘，D6 再计算非退化、回退、分布外和时延统计。
- **P1 运行和结果证据**：runtime ACK、物理 outcome、counterfactual、causal 和 formal
  reward 均 unavailable。D3 内存执行不能替代这些证据。
- **P1 模型晋级**：本轮只修复 control 基准可信度，没有证明 treatment 优于规则路径。
  bundle 继续 development/shadow-only，PPO、online assist、authority 为 false，规则回退
  为 true。

本项关闭导致正式 20-seed runner 中断的 D3 P1 阻塞，没有新增 P0。专项 `9 passed`，D3
全量收集 365 项，结果 `364 passed, 1 skipped`；skip 仅为 optional OR-Tools。

## 35. 二元特征 OOD GAP 更新（2026-07-21）

### 已关闭

- **P1 二元端点误拒绝**：`previous_binding` 已按伯努利 `{0,1}` 语义校验，合法端点不再
  使用对称高斯 z 门。`0.5`、越界和非有限值继续 OOD；其余连续特征仍使用原 6σ。
- **P1 OOD 可解释性**：新增真值安全的版本化诊断，记录触发特征、候选边偏移、最大连续
  z 和原因。既有 `is_ood()` 布尔消费者不需修改。
- **P1 loader 语义绑定**：生产 shadow loader 将 manifest 的已验证特征顺序显式交给 guard。
  bundle、权重、normalization、阈值和 production admission 均未改变。
- **P1 隔离模型可达性**：同一冻结 bundle 与 nominal 5v5、2.2 秒、seed `1000-1019`
  不写盘复验得到 applied=20、fallback=0；最大连续 z=`1.6229`，P95=`0.692 ms`，重复、
  硬违规和高威胁未满足均为 0。

### 仍开放

- **P1 正式产物更新**：main 首轮落盘产物仍保留 20 次旧 OOD。main 需用当前代码重跑并
  生成新哈希，D3 不修改该目录。
- **P1 D6 非退化与运行结果**：当前成本和 binding 未变化，但 runtime ACK、物理 outcome、
  counterfactual、causal 和正式 reward 仍 unavailable。需要 D6 对新落盘产物独立复核。
- **P1 模型晋级**：20/20 隔离推理只关闭错误门控和可达性缺口，不构成生产晋级结论。
  PPO、online assist、authority 保持 false，规则回退保持 true。

本项没有新增 P0。D3 全量收集 373 项，结果 `372 passed, 1 skipped`；skip 仅为 optional
OR-Tools。

## 36. v2 正式保留 Seed 证据 GAP 更新（2026-07-21）

### 独立复核

- **来源与完整性**：证据来源提交为
  `78912963b67fe86ee9a8d29186b18a9dd60c460c`。`SHA256SUMS` 文件的 SHA-256 为
  `821f15035e628d8db86f13c22d93f8e05142c5f00aae9118974a74bdc98b72bc`；
  `manifest.json` 为
  `d6ef23b28add92e9a24a185ea72a7275e341bd796a2e11930c4d5f46b19a883c`；D3 产物
  `d3_offline_paired_intervention.json` 为
  `e878cd97f2a0f1c84fbd68b5ee996d0dc6d4e550cce42eab53558a33a120270b`。
  `sha256sum -c` 对五个受管文件全部通过，D3 产物无非有限数。
- **样本与真值隔离**：来源 lineage 包含唯一 seed `1000-1019`，20 个源样本全部
  clean/finite，online truth 使用计数为 0。control/treatment 各 20 条，未发现样本数、
  seed 或 arm 缺失。
- **规划层结果**：treatment applied=`20/20`、fallback=`0`，有效代价矩阵变化
  `20/20`，最终 binding 变化 `0/20`。规则臂与 treatment 臂的 assignment cost mean 均为
  `17.0560260319065`；高威胁未满足、duplicate、hard violation 和 churn 均为 0。
  推理时延 P50/P95 为 `0.246385/0.310801 ms`，最小/最大为
  `0.234524/0.792214 ms`。

### 已关闭

- **P1 正式产物更新**：第 35 节中“旧 OOD 产物待重跑”状态已被本节 v2 证据取代。
- **P1 隔离 treatment 应用可用性**：20 个 treatment 全部进入隔离模型推理，无 OOD、
  deadline 或其他规则回退。
- **P1 规划层非退化复核**：安全计数、高威胁满足、churn 和规则评分均未恶化。
  代价矩阵变化但最终 binding 不变，因此不声明已获得任务性能收益。

### 仍开放

- **P1 运行与物理结果**：runtime ACK、physical outcome、counterfactual 和 causal 均为
  unavailable；现有证据不支持运行采用或物理效果结论。
- **P1 正式奖励与生产晋级**：formal reward 和 promotion 仍为 unavailable。PPO、assist、
  authority 保持 false，rule fallback 保持 true，runtime publication 保持 false。

本项没有新增 P0，也没有更改冻结 bundle、线上准入或默认规则路径。

## 37. D6 Profile-Bound v2 Availability GAP 更新（2026-07-22）

### 已关闭

- **P1 D3 assignment 层可用性**：D6 profile-bound v2 sidecar 已独立消费正式 producer
  bundle，状态为 `pass_offline_assignment_comparison_only`。正式目录是
  `research_modules/d6_evaluation_metrics/outputs/reserved_seed_interventions_nominal_5v5_1000_1019_formal_7891296_d6_profile_bound_v2_audit_20260722/`。
- **P1 独立消费**：sidecar 文件 SHA-256 为
  `f3852251daf02ec87fe878e7fb80aad6f381d8c0756a5c956a32e737a3871c3b`，规范内容 SHA-256
  为 `c02a345c46ddc642dea7fb6bfcfb24184e7dc2a9f35b754c90324d074b445d2d`。来源 schema、
  manifest、bundle identity、收据和逐 pair 结果均由 D6 只读校验。
- **P1 same-frame offline comparison**：treatment applied=`20/20`、fallback=`0`、effective
  matrix changed=`20/20`、final binding changed=`0/20`。rule/treatment cost mean 均为
  `17.0560260319065`，high-threat unmet、duplicate、hard violation 和 churn 均为 0。

### 仍开放

- **P1 运行采用与物理结果**：本正式 artifact set 的 runtime ACK、post-intervention
  physical outcome 和 paired physical effect/non-degradation 均为 unavailable。
- **P1 反事实、因果和晋级**：counterfactual、causal 和 promotion 仍 unavailable；
  `PPO=false`、`assist=false`、`authority=false`、`rule_fallback=true`。same-frame
  assignment comparison 不得扩展成候选策略有效、物理无退化或生产准入结论。

本项不新增 P0，不改变 D3 代码、冻结 bundle、默认 Hungarian、线上发布权限或安全门控。

## 38. 隔离计划消费 GAP 更新（2026-07-22）

### 已关闭

- **P1 D3 计划消费证据接口**：新增版本化、JSON 可序列化的 isolated plan-consumption
  evidence。experiment/seed/arm、source snapshot lineage、receipt、plan id/version/schema、
  payload SHA、消费时刻、assignment/binding 数量和 binding inventory 均有明确字段。
- **P1 receipt 与生产 ACK 语义混淆**：独立 schema 和状态码固定
  `production_runtime_ack=false`、`isolated_simulation_only=true`。生产世界控制、物理
  outcome、reward、causal、PPO、assist 和 authority 均不能由该证据声明。
- **P1 stale/replay 门控**：有状态 validator 在完整校验后才写账本。重复消费、错 arm、
  source snapshot/receipt/payload 不匹配、旧版本、相同版本二次消费、周期或时间回退均
  失败关闭。
- **P1 main 稳定调用面**：公开构造、无状态校验和有状态校验 API，现有 AssignmentPlan、
  paired receipt 和 production runtime ACK API 保持兼容。2026-07-22 专项 `8 passed`，
  D3 全量 `380 passed, 1 skipped`。

### 仍开放

- **P1 多周期隔离世界执行**：main 尚未让 control/treatment 从同一初始世界和外生调度
  分别推进多个周期。当前 D3 证据只确认计划被隔离 consumer 接受，不证明控制命令已改变
  隔离世界状态。
- **P1 D7 命令与物理窗口 lineage**：仍需 main/D7 记录每个 arm 的命令来源、应用周期和
  后续状态窗口。该证据不能替代 production runtime ACK，也不能替代 D6 outcome sidecar。
- **P1 可辨识场景与 D4 degraded 场景**：nominal 5v5 正式批次 final binding change 为
  `0/20`。需增加接近 Hungarian 切换边界的场景，并单独运行 D4 降级条件，才能评价候选
  策略的运行效果。
- **P1 结果和因果层**：paired physical effect/non-degradation、counterfactual、causal、
  promotion 继续 unavailable；PPO、assist、authority 保持 false，规则回退保持 true。

本项关闭 D3-owned 计划消费合同缺口，没有关闭 main 多周期执行、D7 控制 lineage、D6
物理结果或生产 runtime ACK 缺口，也没有新增 P0。

## 39. 离线目标库存兼容 GAP 更新（2026-07-21）

### 已关闭

- **P1 reserved-seed 计划消费阻塞**：4→5 目标且迟滞保持旧绑定时，新增目标现由离线执行
  规范化为未分配且不完整，不再出现 `target_count` 大于唯一目标库存的问题。
- **P1 全 arm 严格校验**：缺失 bundle 规则回退条件下逐一扫描 20 seed、40 arm，严格计划
  SHA 和隔离消费构造为 `40/40`；首个历史失败 `index=22, seed=1011, control` 已通过。
- **P1 生命周期与 M-to-N 语义**：当前不可分配目标保留在 roster；部分联盟只计一次并标为
  incomplete；previous-only 诊断项移除，previous-only 可执行绑定继续失败关闭。
- **P1 receipt 哈希边界**：离线 receipt 只对通过严格结构校验的规范计划计算载荷摘要。
  生产 runtime ACK 校验没有放宽，也未伪造线上 ACK。

### 仍开放

- main 多周期克隆世界、D7 命令 lineage、D6 post-intervention physical outcome 和 paired
  effect 仍未由 D3 证明。PPO、assist、authority 保持 false，规则回退保持 true。
- **P1 生产保持计划 roster 语义**：本轮只规范化不可发布的 offline arm。生产 planner 在
  “保持旧执行绑定、审计新候选目标”时仍由严格 runtime ACK 失败关闭；若后续要在线发布
  该状态，需单独统一 execution roster 与 current input roster 的 `target_count` 语义。

本轮 D3 专项 `19 passed`，全量 `382 passed, 1 skipped`。没有新增 D3 P0。

## 40. 在线故障代际库存 GAP 更新（2026-07-22）

### 已关闭

- **P1 生产保持计划 roster 语义**：中心、增量和区域授权路径现以当前规划帧形成完整目标
  库存。新增目标即使没有绑定，也随新 `plan_id/version` 发布为未分配且不完整。
- **P1 故障代际 4→5 目标断点**：`advance_authority_generation()` 在匹配规划上下文存在时
  先规范库存，再推进 fence。seed 1011/1019 的二级接管计划均保留 4 个合法绑定并显式
  登记第 5 个目标。
- **P1 不完整联盟双计数**：候选联盟成员数用于需求完成度；可执行 assignment 数用于控制
  授权。不完整联盟保留前者、清零后者，避免把候选成员误发布为执行绑定。
- **P1 故障后规划证据可用性**：严格同语义的二级 owner 转换可以把当前成本帧重绑定到新
  计划身份。两个指定 seed 各有 2 个故障后可用帧，严格计划摘要全部通过。
- **P0/P1 安全门控保持**：previous-only 可执行绑定继续拒绝；旧版本、摘要篡改、联盟计数
  不一致继续失败关闭。生产 runtime ACK 校验逻辑未放宽。

### 仍开放

- **P1 规模和场景覆盖**：当前在线故障证据只有三维质点 5v5、seed 1011/1019、每组 3.2
  秒。更大规模、多 seed、二级再次失效和通信退化组合仍需 main 验证。
- **P1 上下文缺失边界**：故障 fence 只能使用与当前已发布计划匹配的真实规划上下文补齐
  库存。上下文不可用时不推测目标，调用方需先形成新规划帧或区域授权输入。
- **P1 AirSim 证据**：本轮未启动 Blocks、ComputerVision 或 SimpleFlight，不能作为
  AirSim 接管结果。

D3 全量为 `385 passed, 1 skipped`，共收集 386 项。当前没有新增 D3 P0。

## 41. 故障代际离线重放 GAP 更新（2026-07-22）

### 已关闭

- **P1 center_failure control replay mismatch**：离线执行现重放“前序 owner 求解候选 -> 二级
  authority identity 转换”的在线计划顺序，不再直接以记录计划的新 owner 求解。
- **P1 决策身份一致性**：seed 1000 的 control 重现 v2/window 2、
  `replan_ack_no_change`、`changed=false` 和 5/5 binding。全 20 个 control 均通过原精确
  replay gate。
- **P1 4→5 库存兼容**：seed 1011/1019 的 4 个旧绑定保持，`target_0004` 明确进入
  unassigned/incomplete，需求摘要数量为 5；control/treatment 共 4 个 incomplete arm。
- **P1 authority 来源审计**：40/40 arm 带 authority replay 标记和输出计划严格回执，二级
  active 状态、owner、lease、epoch 或 link 缺失时失败关闭。
- **P0 安全边界保持**：`_control_plan_replay_matches()` 未放宽，严格 payload 校验未绕过，
  production ACK、PPO、assist 和线上 authority 仍为 false。

### 仍开放

- **P1 其他降级层级**：本轮未验证 secondary_failure 和完全 distributed 的离线计划重放。
- **P1 更大规模与通信故障**：真实验收仅为 5v5、20 seed、3.2 秒；更大规模、目标快速增删
  和通信退化组合仍需 main 运行。
- **P1 AirSim/物理证据**：本轮是三维质点 reserved-seed 验收，没有 AirSim、生产 ACK、
  D7 控制采用或物理拦截结果。

D3 全量共 387 项，结果为 `386 passed, 1 skipped`。当前没有新增 D3 P0。

## 42. 区域授权待分配库存 GAP 更新（2026-07-22）

### 已关闭

- **P1 区域目标集合不匹配**：D4 只覆盖已有可执行绑定时，D3 可接受上一计划已经严格证明
  的零绑定待分配目标，不再要求为它伪造区域授权。
- **P1 当前库存完整性**：未授权待分配目标继续进入 `target_count`、未分配和不完整清单，
  并保留 `0/required` 需求摘要；输出通过既有严格计划载荷校验。
- **P0/P1 授权边界保持**：待分配目标不生成 assignment、coalition、owner、lease 或
  commit。漏掉已绑定目标、未证明新增目标、库存篡改、未知 grant 目标和 previous-only
  可执行绑定均失败关闭。
- **P0/P1 既有门控保持**：旧版本、旧 epoch、过期 lease、缺 commit/ACK 和禁止执行继续
  拒绝；生产 runtime ACK 校验器未修改。

### 验证

模块区域专项及规划证据共 `34 passed`。三维质点 `secondary_failure`、规模 5、4.2 秒、
seed 1011/1019 的 main 集成测试文件为 `10 passed`。D3 全量收集 391 项，结果为
`390 passed, 1 skipped`。

### 仍开放

- **P1 扩大验证**：secondary-to-distributed 仍需更多 seed、更大规模、目标增删和通信
  退化组合。
- **P1 AirSim 与执行证据**：本轮没有 AirSim、生产 runtime ACK、D7 控制采用或物理结果。
  区域计划可发布不等于控制已执行。

该断点已在 D3 owned path 内关闭，没有新增 D3 P0。

## 43. 非生产隔离执行计划升版 GAP 更新（2026-07-22）

### 已关闭

1. 已关闭离线 arm 计划“新 `plan_id`、旧 version”以及首次修复仍错误超越求解源版本的
   D3 合同缺口。公共入口现区分规划帧 `previous_plan` 对应的离线求解源与规划帧 `plan`
   对应的正式权威；输出版本固定为正式权威版本加一，前序计划固定为正式权威计划号。
2. 已关闭 main 自行拼接版本、receipt 被误当作新计划证明及离线候选库存可能在升版时丢失的
   风险。规划帧输入摘要、完整帧转换摘要、求解源、正式权威、候选、arm 和 receipt 均进入
   v2 转换证据。跨 frame、同 ID/version 载荷替换和错误 authority 前序链失败关闭。
3. 已补齐 assignment、unassigned/incomplete、coalition、demand summary、N/M 规模和正式
   authority 语义的完整性检查。跨 seed/arm/source、过期源、真值字段和载荷篡改均失败关闭。
4. 已提供与升版计划一致的隔离消费证据路径；原 receipt 继续保持非生产、候选级语义。
   生产 runtime ACK 和在线 authority 门没有放宽。

### 验证与剩余项

专项 `18 passed`。普通 5v5 和 `center_failure` 分别完成 20 seed、40 arm 扫描；后者验证
求解源版本 1、正式二级权威版本 2、隔离执行版本 3 的严格链路。D3 全量
`408 passed, 1 skipped`，skip 是未安装的可选 OR-Tools。验证日为 2026-07-22，证据范围
是 D3 单元和离线合同回归，没有 AirSim、生产 runtime ACK、D4 adoption 或物理结果。

main 尚需按新签名把同一 planning frame、求解源、正式权威、候选和 receipt 接入真实
reserved-seed 隔离多周期 rollout，并让 D4 adoption、D7 命令 lineage 和 D6 sidecar 共同
引用返回的新计划。该系统级接线保持 P1；D3 本地双源升版合同缺口已关闭，没有新增 D3 P0。

## 44. 区域权威离线重放 GAP 更新（2026-07-22）

### 已关闭

1. 已关闭 `secondary_failure` 控制臂在区域授权帧保留中心/二级执行身份、导致
   `control_plan_replay_mismatch` 的 D3 P1 断点。
2. 区域记录计划与前序计划现由转换摘要绑定。区域 owner、source/link、epoch、lease、
   commit、版本、前序关系和时间篡改均失败关闭。
3. 离线区域路径复用线上 `plan_regional_authority()`。处理臂不能绕过 action mask 或采用
   记录 grant 之外的成员；生产 runtime ACK 校验器未修改。
4. seed 1011/1019 的第 5 个目标继续显式未分配且不完整，不获得区域 owner、lease、commit
   或 assignment。

### 验证与剩余项

真实三维质点 `secondary_failure`、规模 5、3.2 秒、seed 1000-1019 共 40 个 arm 全部生成，
在线真值使用为 0。离线干预专项 `23 passed`，D3 全量 `419 passed, 1 skipped`。验证日为
2026-07-22。本项没有新增 D3 P0。

仍开放的 P1 是 main 侧隔离物理 rollout 联合验收：D4 adoption、D7 命令 lineage 和 D6
物理结果必须绑定同一升版计划。真实 M-to-N 区域原子联盟、多规模通信退化和 AirSim 尚未
验证；这些结果不能由当前单成员区域重放推导。

## 45. 200×200 规划证据热点 GAP 更新（2026-07-22）

### 已关闭

1. P1 确定性性能热点已关闭：规则和有效矩阵共享同一 breakdown/reject 源结构时，不再对
   40,000 单元重复深度匿名化；不同学习结构仍分别处理。
2. previous-plan 迟滞比较不再复制全部 breakdown，只复制 hard-safe candidate edge；既有
   binding 仍通过 preserved candidate 合同进入比较范围。
3. 数值 rule/effective 矩阵继续使用独立不可写快照，匿名 breakdown 继续只读。证据 schema、
   哈希输入和回放语义未改变。
4. 规则代价、不可达边、容量、M-to-N demand slot、Hungarian、迟滞、计划版本、stale、
   联盟及 D7 binding 均保持原合同。

### 证据

独立 200x200 开发基准中，向量化中位数由 `2651.953 ms` 降至 `189.111 ms`，完整链路
seed 42000 的三次 D3 规划由 `7.329949 s` 降至 `1.013593 s`。breakdown 清洗由约
80,200 次降至 6,601 次。结构仍为 40,000 完整边、6,400 候选边和 200 个 assignment。
新增 3x5、5x3、200x200、M-to-N 和 previous-plan 多周期测试，定向 `62 passed`，语法
检查通过。D3 全量选定集为 `422 passed, 1 skipped, 2 deselected`。墙钟只作为 benchmark，
不设单元测试硬门限。

### 仍开放

1. 完整 200v200 多 seed、候选上限扫描、长周期 previous-plan、AirSim 和物理拦截仍是 main
   侧系统验收 P1，不由本次 D3 微基准关闭。
2. D3 完整收集中的两项 `global_track_stale` 在该阶段未修改 HEAD 可复现。后续确认 seed 7
   是 main 未消费后验调度问题，seed 41 是 D3 测试错误选择末条保持 ACK；两项均已按真实
   原因修复，D3 stale 拒绝未放宽。
3. 更大规模 sparse flow、区域分解和复杂容量求解保持 P2/P3 optional，不进入默认主线。
4. 当前没有新增 D3 P0。

## 46. AssignmentPlan 在线成本证据重复物化 GAP 更新（2026-07-22）

### 已关闭

1. **P1 在线计划载荷重复**：`d3_assignment_evidence_v2` 只内联一份完整
   `cost_breakdowns_by_edge`。旧 `current_cost_breakdowns_by_edge` 改为字段引用，不再随
   每次 JSON 发布复制全部候选边。
2. **P1 审计完整性**：规范列表继续包含全部候选边及成本分解，并新增内容 schema、条目数、
   规范 SHA-256 和存储方式。没有删除候选集、拒绝边、Hungarian 输入、迟滞或 D6 所需成本
   证据。
3. **P1 旧产物读取**：公共导出函数兼容 v1 规范字段、双字段和仅旧别名。双字段冲突、v2
   计数/摘要/引用错误均失败关闭。
4. **P0 合同保持**：assignment、`global_track_id`、执行签名、owner、plan id/version、
   stale、联盟和 D7 binding 不变。完整 payload SHA 随 schema 正常变化，运行确认仍按实际
   payload 重算。

### 证据

合成 200x200、6,400 候选边计划从 10,466,292 字节降至 5,622,366 字节，减少 46.28%。
只读 10 秒 seed 42000 样本的一条在线计划按 v2 投影后从 9,905,419 字节降至 5,147,795
字节，减少 48.03%。专项 5 项通过。D3 全量收集 430 项，其中 427 passed、1 skipped、
2 个既有跨模块 `global_track_stale` failed。

### 状态与仍开放

1. main 已在 clean commit `8f86192` 完成 10 秒、seed 42000-42002 新 episode。每组 D3
   发布和计划 ACK 均为 10，计划业务摘要与旧提交一致，clean/finite/truth0 门通过。总线
   长时复跑和 runtime ACK 证据已补齐；长期内存峰值仍需单独测量。
2. 该阶段的两项 `global_track_stale` 后续分别由 main 修复未消费后验调度、D3 修复 ACK
   取样口径；当前全量零失败，且未通过放宽 stale 门关闭。
3. 外部直接读取旧别名的未知消费者需迁移到规范字段或公共导出函数。仓库内没有此类
   Python 消费者。

当前没有新增 D3 P0。D3-owned 重复物化缺口已关闭，系统级长时复跑保持 P1。

## 47. 冻结输入性能归因与身份签名复用 GAP 更新（2026-07-22）

### 已关闭

1. **P1 热点归因不可复现**：新增固定字段的结构操作计数，分别覆盖 40,000 个完整目标资源
   对、6,400 条候选边、候选连通分量、Hungarian 准备矩阵、计划边规范哈希、迟滞访问、
   匿名证据复制和发布校验。操作计数不随采样频率或机器负载变化。
2. **P1 诊断污染计划合同风险**：诊断对象和墙钟只存在于独立 benchmark 结果，不写入
   `AssignmentPlan.metadata`、`plan_id`、执行签名、运行时 ACK 或控制许可。
3. **P1 身份边界重复计算与权威来源**：候选执行签名在一次规划调用内复用；latest published
   execution signature 由 planner-owned cache 跨帧保存并作为权威。caller previous 只做
   一致性校验，不能替代 latest。公共发布仍从待发布对象计算 candidate signature。
4. **P1 参考路径语义不明确**：身份重复计算和关闭离线证据只作为归因参考。两者没有成为
   PlannerConfig 开关，也不能用于在线绕过规划证据。
5. **P1 区域异常优先级回归**：区域接管先完成 plan id/version 校验，再检查 pending
   inventory，最后执行通用执行语义校验。库存篡改继续返回 `RegionalPlanAuthorityError`；
   其他同 identity 执行语义篡改返回 `StalePlanError`。直接发布和 authority fence 门控未放宽。

### 证据

冻结输入为 200×200、seed 42000、每目标最多 32 条候选边，输入 SHA-256 为
`c7c86f22252add5a6e201577ec99baa63050e56d00898e66d514ab3c0c46c7ff`。默认路径上一
计划帧的暖启动中位为 `334.735 ms`；身份重复计算参考为 `389.673 ms`；关闭离线证据参考
为 `223.147 ms`。默认上一计划帧中，成本矩阵、Hungarian、计划边证据、迟滞、身份固化、
发布和匿名证据中位分别为 `66.401/4.460/82.342/31.602/2.967/0.156/74.305 ms`。

三条路径的 binding SHA-256、计划版本和规范业务 SHA-256 一致，刷新帧均复用原计划号。
身份缓存、区域异常优先级、直接发布、authority fence 和性能诊断定向组合为 `46 passed`。
D3 全量收集 439 项，初次结果为 `436 passed, 1 skipped, 2 failed`。skip 是可选 OR-Tools；
两个失败均表现为 main/D7 `global_track_stale`。后续按真实根因修复后，当前结果为
`438 passed, 1 skipped, 0 failed`。

### clean 集成复核与仍开放

1. main 已在 clean commit `8f86192` 完成 10 秒、seed 42000-42002 复跑。D3 assignment
   累计墙钟为 `3.437/3.319/3.110 s`，均值 `3.289 s`；旧 clean commit `3bac3ff` 均值
   为 `3.348 s`。约 `-1.8%` 的变化按基本持平和调度噪声处理，不形成性能归因或晋级。
2. 三组均 clean、finite、online truth use=0；每组 D3 调用和计划 ACK 均为 10。binding
   ACK、control applied 和 hold 摘要与旧提交逐 seed 一致，确认 D1 快照优化未改变 D3
   执行语义。
3. 冻结 benchmark 的 `334.735 ms` 等原数字继续用于固定输入归因；clean episode 只提供
   累计墙钟与业务一致性证据。长期内存峰值、AirSim、物理拦截和系统实时预算仍开放。
4. 初次两项 `global_track_stale` 已分别通过 main 调度修复和 D3 测试取样修复关闭。D3 未
   放宽 stale 门控。
5. 当前没有新增 D3 P0。clean 三种子集成复测这一 P1 证据项已关闭。

## 48. 独立运行计划谱系比较 GAP 更新（2026-07-22）

### 结论

1. **D3 身份合同无缺口**：`_build_plan()`、secondary takeover 和 authority fence 为新谱系
   使用 `uuid4`；独立 planner 的原始 `plan_id` 不相同是有意行为。单实例 refresh 保持身份，
   执行变化严格升版，publish/stale/previous-plan 校验继续失败关闭。
2. **文档口径缺口已关闭**：README、PLAN、算法文档、模块原理和 review 现统一规定跨运行
   比较必须先验证单运行链，再按首次出现序号规范 plan identity，并精确保留版本、父关系、
   owner、stale、coalition、epoch/lease/commit 和全部外部业务标识。
3. **旧快速哈希的适用边界已澄清**：`canonical_plan_business_sha256()` 适用于冻结中心规划
   benchmark，不验证完整 lineage 图，不能独立证明 D4/D7/ACK 的跨运行等价。原始 payload
   摘要仍用于单运行 ACK 完整性，跨运行摘要须从规范载荷重算。

### main 集成限制

当前 scalable publication 未直接输出顶层 `previous_plan_id`，而 D3 的
`PlanningTickHistoryRecord` 已有 previous/supersedes/latest 和配对版本。对现有 clean 线性
episode，main 可在 D3 发布事件完整、版本逐一递增且 owner 唯一时按相邻发布推导父关系，
但必须标记 `lineage_relation_source=derived_from_contiguous_publication_order`。存在事件缺失、
版本跳跃、未发布候选或并行 owner 时应判证据不足。把 planning-tick history 接入 scalable
持久化及完整规范计划载荷接线属于 main-owned P1 集成项，不通过固定或删除 D3 UUID 处理。

本次没有修改算法代码、schema 或默认配置，没有新增 D3 P0。该阶段初次全量运行结果为
`436 passed, 1 skipped, 2 failed`；两项失败均表现为 main/D7 `global_track_stale`。其中 seed 7
已由 main 的未消费 D1 posterior 锁存恢复，D3 没有改写航迹时间戳。seed 41 在末条 ACK 前
确实没有新后验，D7 保持是正确安全行为，不应作为待放宽的门控缺口。

## 49. ACK 结果窗口取样口径修复（2026-07-22）

旧 D3 集成用例固定选择 seed 41 的最后一条 ACK，再从中查找非保持 binding。当前真实时序下，
首条 ACK 有 3 个非保持 binding，末条 ACK 的 3 个 binding 因航迹年龄约 `0.770941 s` 超过
`0.75 s` 门限而全部保持，因此旧取样会错误失败。

D3 测试现保存每次发布时的只读计划快照，按来源计划载荷 SHA-256 对回 ACK，验证全部 D3、
D7 来源和 ACK 后，再按总线顺序选择首个非保持 binding 接入 D6 observed-only 窗口。测试
同时断言末条 ACK 的保持原因是 `global_track_stale`。未修改 D3 生产代码、计划 schema、
Hungarian、迟滞、时间戳、D7 时效门或 PN/PNG。定向测试通过；D3 全量 439 项为
`438 passed, 1 skipped, 0 failed`，唯一跳过仍是可选 OR-Tools。该测试口径缺口已关闭，
没有形成新的 P0/P1 算法缺口。

## 50. 真值无关候选帧资格 GAP 更新（2026-07-26）

### 已关闭的 D3 缺口

旧 20-seed 共同检查点续跑中，规则和处理两组各执行 980 条控制命令，计划消费与物理窗口
均为 20/20，但最终绑定变化为 0/20。旧流程缺少一个可在物理运行前证明“模型实际改变安全
候选成本并改变最终绑定”的严格选择合同。

D3 已增加 `d3.learning-intervention-frame-evidence.v1` 和四个公开接口，用匿名规则/处理
`PlanningFrameEvidence` 重新计算输入谱系、模型实际作用、回退和分布外状态、超时与有限
性、计划可行性、硬候选边、版本和前序计划、需求槽、联盟全有或全无及绑定差异。证据缺
字段、额外字段、手工 eligibility、占位摘要、内容篡改、序号乱序、重复和逆序时间戳均
失败关闭。模型未应用、任一回退、分布外、超时、非有限值、绑定不变、旧版本和 M-to-N
部分执行均不能成为候选。

专项 `19 passed`；D3 全量 `484 passed, 1 skipped`（485 项），skip 为可选 OR-Tools。
当前没有新增 D3 P0。D3-owned 的候选帧资格与 first-eligible 选择接口缺口已关闭。

### 仍开放的 main 集成项

main 尚需把每个 seed 的规则/处理规划帧按权威时间顺序持久化，保证 `sequence_index` 与
`timestamp_s` 分别严格递增，再调用 D3 API 并与 D7 同 seed 的可执行检查点求交。旧
20-seed 脏工作树结果不能事后补写为合格证据。没有共同合格帧时应报告 unavailable，不能
降低分布外或硬安全门。本项属于 main/scalable 集成和后续 clean 运行证据，不要求 D3
改写默认 Hungarian、阈值、生产 loader 或权限边界。

`docs/AIRSIM_INTEGRATION_PLAN.md` 已检查。本次没有 AirSim DTO、settings、episode 调度或
控制行为变化，因此无需修改。

## 51. 单帧隔离重放生产者 GAP 更新（2026-07-26）

### 已关闭的 D3 缺口

main 只有规则组 `PlanningFrameEvidence` 时，旧 API 无法在资格判断前公开返回同输入的
规则组和处理组完整规划帧。D3 已增加
`replay_isolated_learning_intervention_frame(...)` 和
`d3.isolated-learning-intervention-frame-replay.v1`。接口复用既有 development bundle
loader、冻结规则矩阵、Hungarian/需求槽规划器和学习安全外壳，不复制求解器。

源帧现严格检查规则/有效输入证据一致、前序版本和有效期、当前计划升版链、航迹与资源标识
顺序、数值有限性及线上标签隔离。bundle hash/version、清单权限、OOD、超时或非有限值不
满足时使用规则回退，处理资格不得为真。DTO 绑定完整规则帧、处理帧、资格证据、bundle
身份、输入谱系和内容 SHA-256；内容或谱系篡改失败关闭。运行发布、runtime ACK 和
authority 固定为 false。

新增专项 `17 passed`。原离线执行器 23 项继续通过；单帧重放、离线执行和资格选择组合为
`59 passed`。D3 全量 502 项结果为 `501 passed, 1 skipped`，skip 是可选 OR-Tools。
当前没有新增 D3 P0。D3-owned 的单帧生产者、资格评估和 first-eligible 选择合同已完成。

### 仍开放的外层 P1

匿名 `PlanningFrameEvidence` 不携带 seed。seed `1000-1019`、split 身份、清单完整性和
逐 seed 权威时间顺序必须由外层 manifest/runner 校验。该段形成时尚未完成的 clean
20-seed 正式运行，现已由第 52 节所列正式 evaluator 完成。D7 共同检查点、runtime ACK、
outcome、reward 和正式 admission 仍未形成。

`docs/AIRSIM_INTEGRATION_PLAN.md` 再次检查。本项没有 AirSim DTO、相机/飞行设置、episode
编排或控制路径变化，因此不修改该文件。

## 52. 20-seed 隔离批量 runner GAP 更新（2026-07-26）

### 已关闭的 D3-owned P1

D3 已提供固定 seed `1000-1019` 的版本化外层 manifest/runner。它显式绑定 source
commit/clean 状态、test split、development bundle 路径/hash/version、planner config、
cost weights，以及每个 seed 严格时序的匿名规划帧路径、文件 SHA 和内容 SHA。runner
逐帧调用既有单帧生产者，逐 seed 调用既有 first-eligible selector。没有合格帧时输出
`no_eligible_frame`，不伪造候选。

输入缺失、重复、乱序、hash/schema/bundle/holdout 错配、dirty source、truth、非有限值、
运行中变化和非空输出目录均失败关闭。JSON、逐 seed CSV、中文报告与校验清单以 staging
目录原子生成。输出固定不发布、无运行 ACK、无生产分配/控制权限、无物理结果和奖励。

### 验证与状态

2026-07-26 单元夹具使用 20 seed、每 seed 1 帧。可辨识残差为 20/20 eligible，零残差为
20/20 unavailable；两个空目录的四份输出逐字节一致。该证据只验证合同。

main 随后在 clean source commit `0ed7ca2730f5354be1e6021f9882f1ae26bc42df`
生成真实 manifest，固定 seed `1000-1019`、每 seed 5 帧，共 100 个匿名规划帧，在线 truth
计数为 0。manifest SHA-256 为
`e5367d2651955f809b482d78ef3205cbdf44d57eae576c80f64cbd38eac59a44`，输入
`SHA256SUMS` 全部通过。首次重放在 seed 1011 序号 3 因新增目标联盟 token 不一致失败。
D3 已加入严格记录联盟身份恢复，仅恢复已哈希绑定的新联盟匿名标识，并继续验证前序联盟
连续性、assignment、需求摘要、metadata 及最终控制执行签名。重复标识、前序重写和引用
篡改均失败关闭。

正式 clean evaluator 使用代码提交
`bdb665eb8e63a17f5f15dbf3fe472af10e5e5b5c`。输出 `SHA256SUMS` 全部通过，内容
SHA-256 为 `c01b13fb5925d99078a3bb9505dc0f9511ec5ab700a432399d3ebe0fcfb55592`。
输入与输出外部归档 SHA-256 为
`127ad91d864b136ab10cde7111bf6241a7a765ad4467aa449ef29cbb5557ef5e`。
20/20 seed 均为 `unavailable/no_eligible_frame`。100 帧中 80 帧应用学习代价，20 帧
分布外回退；每个 seed 的 binding change、规则/处理硬违规和 `global_track_id` 改写均为
0。`publish=false`，生产分配和控制权限均为 false。两个独立空目录的逐文件一致性属于
此前开发确定性复核；本次正式输出另由校验清单和内容摘要约束。

当前没有新增 D3 P0。**真实 clean batch 生成和 D3 批量重放这一 P1 已关闭**。仍开放的
策略与跨模块 P1 是：当前 development policy 没有跨过 Hungarian 离散边界，因而没有
D3/D7 共同检查点，也不能形成 A1 证据。后续需由 main 选择新的冻结训练结果，再由 D6 连接
运行 ACK、outcome 和成对比较。PPO、online assist、A1 admission、默认路径和生产
authority 仍未开放，不能通过降低 eligibility 或联盟连续性门限关闭。

`docs/AIRSIM_INTEGRATION_PLAN.md` 已检查。本项是离线检查点选择，不改变 AirSim runtime
输入输出或控制接口，因此不修改该文档。

最终测试：单帧专项 `23 passed`；干预合同组合 `79 passed`；D3 全量
`521 passed, 1 skipped`（522 项），唯一 skip 为可选 OR-Tools。

## 53. A2 区域权属元数据 GAP 更新（2026-07-27）

### 已关闭的 D3 缺口

真实集成探针已证明：D4 区域提示可以被 D3 considered/applied，目标集合变化也能产生严格
新执行计划，但新计划此前只携带 `active_plan_owner/owner_node_id`。缺少
`authority_epoch/lease_expires_at_s` 时，D4 runtime adoption parser 必须失败关闭。

D3 现从全部严格约束提取统一 `(owner_layer, owner_id, owner_epoch, lease)`。四项任一不
一致，整份提示以 `regional_hint_authority_scope_mismatch` 拒绝并回退原规则规划。提示
成功采用时，owner 系列字段保持同源，并成对写入 epoch/lease。提示拒绝或不存在时，不补写
权属代次与租约。

专项验证覆盖目标集合 2 到 3 的严格新计划、owner/id/lease 三类不一致、同权属无动作提示
和无提示刷新。无动作提示现明确返回 `no_successor`，不再把旧身份称为后继计划。

### 仍开放的跨模块 P1

本项关闭的是 D3 计划元数据合同，不是 A2 物理采用。main 仍须发布真实新计划并形成同 tick
runtime ACK；D4 仍须完成 owner ACK、必要 coalition ACK、租约内执行和物理窗口；D6 仍须
对完整谱系只读审计。上述实物缺一项时，A2 状态继续为 unavailable 或 fail closed。

该段是 20-seed successor 重跑前的通用采用条件。最新批次没有产生真实后继，当前状态以
第 54 节“最新证据和开放 P1”为准。

本次没有运行 AirSim，也没有新的物理指标、奖励或模型准入。AirSim 集成计划和实验报告已
检查，接口与证据未变化，因此未修改。

## 54. A2 严格后继计划 GAP 更新（2026-07-27）

### 已关闭的 D3 P1

早期 A2 独立配对批次只把 seed 1002、1007 识别为零动作区域建议，并把其余 18 个 seed
的普通 D3 滚动重规划误归因给 A2。修正 successor 合同后的重跑证明，20/20 策略候选均为
零动作。D3 保留来源计划身份符合幂等合同；旧 `regional_hint_applied` 把候选约束生效与
后继计划发布混为一个状态。

D3 现公开版本化后继结果合同。真实执行变化必须产生不同计划号、严格递增版本，并正确
引用来源计划；任一条件不满足均失败关闭。执行签名不变时返回 `no_successor`，不刷新来源
计划的权属代次和租约，也不把旧计划交给 D4 当作新计划。提示无效时返回
`hint_rejected`。迟滞、stale 拒绝、幂等发布和默认 Hungarian 路径没有放宽。

确定性测试使用两种资源规模复现零配额、无转移、无重规划请求条件，并重复消费同一提示；
测试不写死 seed 或 5v5。严格新计划正例同时核对来源和后继身份字段。

区域提示专项 `21 passed`；相关合同组合 `65 passed, 1 warning`；D3 全量收集 548 项，
结果为 `547 passed, 1 skipped`。唯一 skip 为可选 OR-Tools。

### 最新证据和开放 P1

main 已按新合同重跑 seed 1000-1019。20/20 均有候选评估；非零配额、hold、
`request_replan` 和 transfer 均为 0/20；可识别区域干预、实际 A2 采用及 A2/R0 收益审计
均为 0/20。输出 SHA-256 为
`ff3c10a089b6a94582451ae05d8a884af3a2bd7485acd4df0496442ea7e0ec55`。

D3 successor 合同 P1 已关闭。当前开放 P1 是 A2 候选策略可辨识性和后续物理证据：策略
必须产生安全投影后仍非零的区域动作，才可进入严格后继、运行确认和同键 R0 审计。普通
D3 重规划不得计入 A2 采用，D3 也不得机械升版。

本轮没有新增 D3 P0。没有运行 AirSim 或产生新的物理、收益、非退化和准入证据。
`docs/AIRSIM_INTEGRATION_PLAN.md`、`docs/EXPERIMENT_REPORT.md` 与 M-to-N 专项已检查，
本次不需要修改。

## 55. A2 非零区域干预消费 GAP 更新（2026-07-27）

### 已关闭的 D3 P1

`hold` 此前仅作为 transfer 禁止条件和审计字段，不能证明 held region 的来源绑定被实际
保持。D3 现将其落实到 hard-safe candidate mask：触及 hold 区域的候选只能是来源计划原
边。原边已硬不可行时，整份提示以
`regional_hint_held_assignment_infeasible` 拒绝。该分支继续保留规则回退和完整拒绝原因。

后继合同已补齐 advisory id/version、source plan id/version、owner layer/id、epoch 和
lease 的显式同域绑定。`request_replan` 不单独触发版本；执行签名不变时仍为
`no_successor`。无来源承诺区域 hold 新目标和守恒非零 transfer 均已有严格后继正例。

区域提示专项 `25 passed`；D3 全量为 `551 passed, 1 skipped`（552 项）。没有新增 P0。

### 仍开放的跨模块 P1

main 的未落盘探针当前只有 15/20 safe/auditable。五个失败 seed 的
`d3_successor_plan_missing` 不是 D3 版本故障：其中 seed 1000 先无执行变化，后因 held
来源边硬失效而拒绝。D4 策略应选择无来源承诺区域，或生成满足守恒、备用和承诺保护的
非零 transfer；不得要求 D3 保留硬失效边。

正式关闭仍需持久化 20-seed advisory/consumption/plan/guidance envelope、owner ACK、
租约内 runtime ACK、完整物理窗口和同键 R0。上述字段由 main/D4/D6 提供，不属于 D3
模块内可补造证据。现有正式 20-seed 0/20 结果和 SHA-256 保持不变。

D4-D3 runtime ACK 集成专项当前还被 D6
`_validate_a3_pairing_inventory_output` 未定义的 `NameError` 阻断。6 个用例均未进入
D3-D4 合同断言。该项归 D6/main 集成修复，不重开 D3 模块内 P1。

本轮未改变 AirSim DTO、episode、M-to-N 需求槽或控制链；AirSim 集成计划、实验报告和
M-to-N 专项检查后无需更新。

## 56. A1 动作裕量可诊断性 GAP 更新（2026-07-27）

### 已关闭的 D3 P1

正式 A1 证据是处理矩阵 `20/20` 变化而最终绑定 `0/20` 变化。旧接口只能给出
`binding_unchanged`，无法判断规则候选间隔、残差方向、候选修正幅度和安全门各自造成的
影响。

D3 已增加单冻结帧、truth-free 的动作裕量校准接口。它按目标计算硬安全候选边到规则最低
成本边的局部间隔，恢复记录残差的有界方向优势和临界 `alpha`，再用原 Hungarian/需求槽
Hungarian 对显式 `alpha/min_confidence` 网格求解。输出包含实际矩阵变化、binding change、
规则基准成本差、局部可跨越数量、fallback 和安全拒绝原因。

该接口不改变 hard-safe mask、身份承诺、版本、迟滞、M-to-N 联盟原子性或前序计划检查。
候选修正超过显式绝对上限时不进入求解；换绑数量超过显式上限时不能成为可辨识候选；
置信不足时使用既有规则回退。报告没有 seed 字段，且固定 `development_only=true`、
formal/unseen-seed 为 false，发布、分配和控制权限均为 false。

复核后，入口会重新计算冻结重放内容摘要并校验矩阵、清单、分解项、动作掩码和非有限值。
空矩阵、无可行动作、源帧已经换绑和构造后篡改均失败关闭。候选保存规则/处理绑定摘要、
求解器与计划版本证据，不绕过版本化 `AssignmentPlan`。

开发夹具已区分四类状态：零残差 no-op；源 `alpha=0.02` 不换绑而候选
`alpha=0.25` 产生 3 条绑定差异；低置信和修正越界失败关闭；可辨识候选仍未授权。专项
9 项通过，D3 全量 `571 passed, 1 skipped`，唯一跳过为可选 OR-Tools。正式证据仍保持
矩阵变化 `20/20`、最终绑定变化 `0/20`；开发夹具的 3 条绑定变化未写入正式结果。

### 保持开放的 P1

1. 当前 development bundle 和现有正式 20-seed 产物未修改。上述夹具不是新模型、未见
   seed、AirSim、运行或物理证据。
2. main/D6 需在新 clean commit 上对实际冻结帧运行校准并保存逐帧间隔和拒绝原因。旧正式
   产物不能事后补写。
3. 新候选只有重新冻结 bundle、预注册修正上限、完成 20-seed paired runtime ACK、
   D7 命令谱系、物理窗口、同键 R0 非退化和 D6 独立审计后，才可进入 admission 评审。
4. 如果记录残差方向不能跨越间隔，应修正训练数据和目标；不得通过无界放大 `alpha` 或
   降低身份、版本、联盟和安全门关闭缺口。

本项没有新增 P0。`docs/AIRSIM_INTEGRATION_PLAN.md`、`docs/EXPERIMENT_REPORT.md` 和
D3 M-to-N 专项已检查。没有 AirSim 接口或新物理证据，故无需修改。

## 57. A1 isolated batch 公共 strict loader GAP 更新（2026-07-28）

### 已关闭的 D3 模块级 P1

D6 此前只能看到 A1 candidate/selection 文件，没有 D3-owned 公共 strict loader，因而
以 `a1_batch_public_strict_loader_unavailable` 阻断。D3 现公开目录级
`load_a1_isolated_intervention_batch(...)` 和重新读取别名
`validate_a1_isolated_intervention_batch(...)`。

读取器严格验证 writer 的七文件布局和六文件 `SHA256SUMS` 覆盖；四个 JSON 继续检查精确
字段、schema、有限值、内容摘要和整树在线身份隔离。预注册复用核心 validator。input
manifest、bundle manifest、state-dict、逐帧文件/内容/replay/eligibility、candidate
inventory 和 selection inventory 摘要形成交叉绑定。

候选必须完整覆盖旧批次 20-seed 帧，逐 seed 选择重新计算阶段计数、候选历史和首个安全
离散变化。计划版本只能相对前序保持或递增一次；有效版本合同下的换绑必须严格升一版。
缺文件、额外文件、符号链接、路径逃逸、摘要错配、未知字段、非有限值、truth/Actor/Object
身份键和权限升级均失败关闭。

主合成合同夹具为 20 seed、40 candidate、20 selection，另有 20-seed 零选择夹具。专项
`46 passed`；D3 全量 `593 passed, 1 skipped`。唯一跳过为可选 OR-Tools。该结果关闭
loader 软件缺口，不是
正式未见 seed 或物理试验结果。

### 保持开放的 P1

1. 当前冻结 development policy 的正式 A1 结果仍为 `0/20 eligible`。loader 没有生成新
   候选，也不改变 bundle。
2. candidate/selection inventory 仍不是计划发布、runtime ACK、physical window 或同键
   R0。main/D7/D6 仍需提供这些独立实物和跨 episode provenance。
3. production admission assembler 仍须在真实可辨识策略、20 个未见 seed、实际采用、
   完整物理窗口和成对非退化审计形成后实现。
4. A2 非零策略、owner ACK、租约内采用和物理配对等既有 P1 不受本项影响。

`docs/AIRSIM_INTEGRATION_PLAN.md` 已检查。本项不改变 AirSim DTO、settings、episode 或
控制路径，不修改该文件。D3 M-to-N 调度和相关专项文档也未变化。

## 58. D4 current-lineage A2 严格后继证据 GAP 更新（2026-07-28）

### 已关闭的 D3 模块级 P1

现有 `d3_regional_planning_hint_successor_v1` 能判断提示是否形成严格后继，但序列化证据
没有绑定 D4 current-lineage 候选编号、模型权重、源码身份、输入/决策/动作摘要和同输入
R0。调用方仍可能把普通周期重规划、其他候选或 R0 计划误包装成 A2 后继。

D3 已新增独立、只读、失败关闭的 A2 successor verifier/loader。它复用现有提示与计划
对象，不触碰 Hungarian/需求槽主线。当前候选 manifest 文件摘要
`7cc10ad770bd95fcb813dbf3d16b17040ec5f41f80fe0dc53e3e291a32f4de64`、
权重摘要
`fd1b9c4cf7580083fadc04a70b87aa6439930eba764a970279611ccc57f30047` 和
source identity
`b81780cece11c792acb3113af2d4be48a19b51c0337a67c926b388197d09dfdf`
已由 D3 loader 独立读取。candidate manifest 的全部权限保持 false。

证据要求安全投影后的配额、备用资源数、hold、重规划请求和 transfer 与 D3 提示逐项
一致。前序 owner、版本、epoch、lease 必须完整且与各区域约束一致。候选计划必须严格
`version+1`，执行签名必须同时区别于前序和同输入 R0。R0 相对前序的普通周期变化单独
记录，A2 归因只覆盖候选相对 R0 的增量。

专项 `16 passed`，区域提示组合 `41 passed`，D3 全量
`609 passed, 1 skipped`（610 项）。当前没有新增 P0。

### 保持开放的跨模块 P1

1. 当前只完成候选身份加载和确定性合同夹具。D4/main 预检中，当前候选在 5v5、2 区域
   为 3/3 `feature_ood`，在 200v200、8 区域为 2/2 `feature_ood`，非回退模型执行为
   0。该候选的正式 20-seed A2/R0 successor 批次必须阻断。
2. D4 需基于实际运行特征和动作课程构建 clean-lineage、runtime-compatible 的新
   development/shadow 候选。D3 loader 需重新核对 candidate、manifest、model state、
   source identity 和全关闭权限。
3. main 必须先做非正式兼容性预检。只有出现非回退模型执行，且确定性安全投影继续通过，
   才能冻结新候选并启动至少 20 个真正未见 seed 的正式批次；预检全回退时继续阻断。
4. 每个正式 seed 还需保存 D4 实际非零决策、同输入 R0、D3 严格后继及拒绝分母。没有
   后继时必须保留明确原因，不能以普通重规划或其他 candidate 补位。
5. runtime ACK、owner ACK、必要 coalition ACK、确认后物理窗口、D7 执行和 benefit
   仍不可用。新 DTO 将这些字段固定为 false，不能据软件验证推断。
6. D4 候选仍是 development/shadow-only；A2 assist、assignment authority、takeover、
   coalition commit 和 control authority 均未开放。

`README.md`、`PLAN.md`、原则、算法和实验报告已同步。AirSim 集成计划已检查；没有接口或
实验变化，无需修改。M-to-N 专项不受本项影响。

## 59. readiness-v3 区域提示合同 GAP 更新（2026-07-29）

### 已关闭的 D3 P1

main 的修改前固定基线为 seeds 2003-2012、20v20、8-region。10/10 seed 的 D4
raw/gate/projection/isolated adoption 通过，D3 successor 为 0/10；其中 7/10 被
`regional_hint_previous_cross_region_commit_exceeds_allowance` 拒绝，3/10 为
`regional_hint_no_executable_successor`。

7/10 拒绝暴露 D3 合同误差。D4 advisory 的 quota 和 transfer 表示相对来源快照的增量，
D3 却要求已有跨区绑定再次出现在新增 allowance 中。修复后，来源计划精确绑定是基线，
新增 allowance 只限制新增跨区资源。基线资源只能保持原边，不能借基线身份换绑；全部
来源跨区边继续通过 hard-safe mask，失效时返回
`regional_hint_protected_transfer_edge_infeasible`。stale plan、来源身份、统一 owner、
epoch、TTL/lease、quota 守恒、备用下限和资源唯一性没有放宽。

区域提示专项 `30 passed`，D3 全量 `614 passed, 1 skipped`。该项关闭模块内重复计数
缺口，没有证明任一 readiness-v3 候选形成严格后继。

### 保持开放的跨模块 P1

1. 修复后 seeds 2003-2012 尚未由 main 重跑。7 个旧跨区拒绝可能转为
   `no_executable_successor`；这种原因重分类不等于采用率提升。
2. 当前 D3 不消费 `reconnaissance_priority`。缺少版本化区域搜索任务、侦察资源资格、
   量化/死区、代价映射、有效期和 ACK。约 `1e-4` 差异继续被排除在执行语义之外。
3. reserve ratio 当前是新增 transfer 的安全余量，不是具体备用 roster。若候选只有比例
   变化且没有配额、hold、可执行重规划效果或 transfer，严格后继仍不可用。
4. runtime ACK、owner/coalition ACK、物理窗口、D7 执行和同键 R0 收益继续 unavailable。

本轮没有新增 P0。AirSim 集成计划已检查；代码未改变 AirSim DTO、settings、episode 或
控制接口，因此不修改。实验报告已记录模块测试和修改前 main 基线。

## 60. 区域后继同身份刷新 GAP 更新（2026-07-29）

### 已关闭的 D3 P1

严格区域后继在下一无提示周期重新构造中心 metadata，曾丢失 owner epoch、lease 和
successor binding，却继续声明相同 plan id/version 与 evaluation-only。D6 因此以
`same_plan_execution_signature_changed` 失败关闭。

D3 现把 epoch/lease 纳入执行签名，并只在原租约有效、owner 未失活、无 fault generation
fence 且完整执行签名相同时继承权限。租约不延长。A2/R0 不可区分负例也改为同权属比较，
没有删除安全字段或放宽 stale、身份、跨区和联盟约束。

main 的 seed 2007 完整 episode 已成功写盘。D6 验证 4 ACK、77 bindings 和 1 次合法
同身份 evaluation refresh，online truth=0。模块全量为 `618 passed, 1 skipped`。

### 保持开放的跨模块 P1

单 seed 运行接线已闭合，更多 readiness-v3 seed 的刷新/升版分布和物理结果仍由 main、
D4、D6 后续统计。owner 活性和 fault generation 变化必须继续通过显式 D4 判决或 generation
fence 输入；D3 不从无提示状态自行推断外部节点健康。

AirSim 集成计划已检查；无 DTO、settings 或控制接口变化，不修改。M-to-N 专项不受影响。

## 61. 规划专用区域转移因果审计 GAP 更新（2026-07-29）

### 已关闭的 D3 P1

区域提示已有严格后继合同，但原专项没有在一个测试中完整列出 source、同输入 R0 和
treatment 的规范执行签名、绑定集合、assignment 数量与未分配库存，存在把身份刷新误报
为 intervention 的审计风险。

D3 现用同一下一周期输入和同一 source plan 构造三臂。source 为 3 条绑定；未发布 R0
因 B 区资源不可用降为 2 条，`T-B` 未分配；treatment 消费一个合法 A 到 B 转移后恢复
3 条，并形成新绑定 `T-B->R-A1`。treatment 执行签名同时区别于 source 和 R0，目标覆盖
相对 R0 增加 `T-B`。R0 和 treatment 都是 source 的 `version+1` 候选，只有 treatment
发布；没有通过机械升版、lease 刷新或 metadata 变化制造干预。

owner/version/epoch/lease、来源承诺、reserve、可达性、资源唯一性、hold 和 stale plan
门限均保持。未发现 D3 实现缺陷。区域提示专项 `34 passed`，D3 全量
`618 passed, 1 skipped`。本轮没有新增 P0。

### 已完成的跨模块证据

main 已在 `scalable_3d_simulation/tests/test_module_stack.py` 固化 20v20、8 区域、
seed 29 永久正例。该正例从 17 条绑定形成 18 条严格后继绑定，未分配目标由 3 降到 2，
在线真值为 0，D4 各执行权限为 false。配套负例在 `t=2.0` 注入中心 fault generation
变化，并确认规划专用转移失败关闭。

main 两项专项测试通过；scalable world 与 module stack 全量 `100 passed`，D4 全量
`794 passed`。因此“固化永久正例”和“增加真实故障代际负例”不再是开放 P1。

### 保持开放的跨模块 P1

1. D6 需独立连接 advisory、消费、D3 successor 和新 binding，并保留同输入 R0 与
   非退化口径。
2. D4 v4 仍未注册，当前没有 clean truth-free 候选的独立配对多 seed 收益。模块合同
   正例不能开放学习采用、分配执行或控制权限。

AirSim 集成计划已检查；没有 DTO、settings、episode 或控制接口变化，因此不修改。
M-to-N 专项也已检查；本项没有需求槽、联盟成员、角色或到达调度变化，因此不修改。

## 62. A1 分配感知开发候选 GAP 更新（2026-07-30）

### 已关闭的 D3 P1 子缺口

旧 development bundle 偏向边残差拟合，正式 20-seed/100-frame 仍为
`0/20 eligible`。D3 现另立 assignment-aware 策略和 bundle schema，把安全投影后的
离散绑定变化作为检查点选择首要目标。旧 bundle、正式结果、Hungarian、规则代价、硬禁
边、迟滞、M-to-N all-or-none、计划版本和 stale rejection 均未修改。

训练只读取 962 个 TRAIN 帧，选模只读取 320 个 VALIDATION 帧；正式 `1000-1019` 未读。
所选检查点形成 13/95 个正类安全换绑、9/95 个教师精确匹配；负类 exact-R0 为 224/225。
有效结果的重复资源、硬边、M-to-N 和版本违规为 0，规则矩阵改写为 0，失败关闭矩阵和
绑定均 exact-R0。同输入两次构建摘要一致，全部运行和生产权限为 false。

该结果关闭“开发数据无法形成任何安全离散变化”的模块内 P1 子缺口，不关闭 A1 正式
准入。旧 `0/20 eligible` 证据保持有效。

### 保持开放的 P1

1. main 需提供与本轮 TRAIN/VALIDATION 不同来源、不同布局的数据，通过严格只读 loader
   独立评价。D3 不依据该结果重新选模。
2. 独立评价必须报告正类安全换绑、负类 exact-R0、失败关闭分母、规则矩阵不变和全部
   安全违规。当前负类 `224/225` 不能写成全保持。
3. 只有来源独立评价仍有安全离散变化，才可另行预注册正式 `1000-1019`。
4. 当前教师提供可辨识连续性干预，不提供收益标签。同键 R0 非退化、D6 审计、runtime
   ACK、D7 binding 和物理窗口仍不可用。
5. 上述证据形成前，不创建 admitted/production bundle，不开放在线 assist、分配或控制。

本项没有新增 P0。AirSim 集成计划已检查；未改变 AirSim DTO、settings、episode 或控制
接口，因此不修改。M-to-N 专项已检查；联盟角色、波次和到达调度未改变。
