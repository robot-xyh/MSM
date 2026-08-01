# D3 Assignment Planner

## 2026-08-01 A1 v2 失败归因与 v3 开发来源请求

D3 已对冻结的来源独立评价 v2 做只读复载和失败归因。诊断器固定读取原结果目录、v2
合同、冻结 development bundle、现有 D6 外部审计和 main 状态报告；它不调用模型、优化器、
计划发布或运行接口。结果文件、合同和 bundle 摘要均与冻结值一致，逐帧 JSONL 与 21 列
CSV 的 292 行逐行闭合。100 个 episode、292 帧、seed `20000-20099`、94 个拒绝帧
exact-R0 和全部权限 false 均重新确认，正式 `1000-1019` 读取数仍为 0。

test 正类教师完全匹配为 `0/25`。归因结果分为两层：9 帧由 `feature_ood` 明确触发规则
回退；其余 16 帧在非 OOD 条件下已经出现候选动作与教师动作不一致。22 帧同时被安全投影
拒绝，但投影前候选精确命中教师的帧数为 0，因此没有“投影单独阻断正确候选”的证据。
可观测路径覆盖 `25/25`，严格根因可确认 `9/25`。v2 没有输出逐边候选集合、逐边残差排序
和匿名需求槽映射，候选不可达、模型排序错误及动作槽结构归因继续标为 `unavailable`。

新增 v3 development data request 和 seed exclusion registry。请求包含 15 个场景规模单元、
300 个 episode、300 个待分配全新 seed，以及正类、负类、困难负类和 11 类动作变化需求。
训练 `0-99`、正式 `1000-1019` 和已评价 `20000-20099` 明确禁止复用；main 分配 seed 前
还必须合并全部 D3 已登记 seed，缺少规范注册表快照时失败关闭。当前
`assigned_seed_values=[]`，生成、训练、选模、调阈值、runtime、assignment、plan、control、
formal admission 和 production admission 均为 false。v2 继续 frozen/not admitted，未写
新 bundle。

诊断入口：

```bash
python3 research_modules/d3_assignment_planner/simulations/\
run_a1_source_independent_failure_diagnostics.py \
  --analyzed-at-utc <UTC_TIMESTAMP> \
  --output <NEW_D3_OUTPUT_DIRECTORY>
```

版本化结果位于
`results/a1_source_independent_v2_failure_attribution_v1_20260801/`。专项测试
`9 passed`，D3 全量为 `677 passed, 1 skipped, 1 warning`。跳过项仍为可选 OR-Tools；
告警仍是既有 Matplotlib `Axes3D` 导入环境问题。

## 2026-07-31 A1 来源独立评价 v2 结果

冻结的 v2 评价已按唯一输出身份执行一次。输入覆盖 `20000-20099` 共 100 个 seed、
100 个 episode 和 292 个匿名规划帧，包含 5、20、50、100、200 五档规模及名义、交叉、
编队分裂、机动、延迟噪声、通信退化、中心失效、二级失效和高威胁 M-to-N 场景。来源
train/validation/test 标签只用于分组，帧数分别为 `178/57/57`；本次没有训练、选模、
归一化重拟合或阈值调整。

机器门结果为 `source_independent_evaluation_v2_gate_passed_not_admitted`：

| 指标 | 实际结果 | 预注册门限 | 结论 |
| --- | ---: | ---: | --- |
| 正类安全换绑 | `13/110 = 11.82%` | `>=1` 且 `>=5%` | 通过 |
| 正类教师完全匹配 | `8/110 = 7.27%` | `>=1` 且 `>=2%` | 通过 |
| 负类 exact-R0 | `182/182 = 100%` | `>=99%` | 通过 |

94 个安全投影拒绝帧的有效矩阵和绑定均逐项恢复 R0。重复资源、硬禁边违规、M-to-N
原子性违规、版本违规、规则矩阵突变，以及模型直接输出 assignment、plan 或 runtime 的
计数均为 0。27 帧因 `feature_ood` 标记为分布外；拒绝原因可在同一帧叠加，主要包括
绑定变化上限 65 帧、规则成本差上限 53 帧、相对规则成本差上限 6 帧和分布外 27 帧。

数据中在线真值字段数和生成阶段在线真值使用数均为 0；训练 seed 与正式保留 seed 重叠
均为 0，正式 `1000-1019` 的读取数为 0。结果目录固定为
`results/a1_source_independent_evaluation_v2_20260731/`，五个固定文件齐全，
`SHA256SUMS` 全部通过。runtime、assist、authority、assignment、plan、control、
physical、formal admission 和 production admission 等权限仍全部为 false。该结果只形成
来源独立离线证据，不能解释为正式 R0、运行采用、物理效果或生产准入。D6 后续已完成
独立复算，只确认离线完整性和预注册机器门，不授予任何权限。2026-07-31 D3 全量回归为
`668 passed, 1 skipped, 1 warning`；跳过项是可选 OR-Tools，告警是既有 Matplotlib
`Axes3D` 导入环境问题。

## 2026-07-30 A1 来源独立评价器 v2（评价前历史状态）

v1 官方命令已按冻结合同运行一次。预检通过后，逐帧读取在
`source_scenario_scale_mismatch` 处失败关闭，进程退出码为 `1`，结果目录未创建。
因此 v1 状态为 `FAIL_CLOSED / EVALUATION_NOT_COMPLETED`，没有正类安全换绑、教师精确
匹配、负类 exact-R0、分布外或拒绝分布等模型指标。v1 合同、源码、bundle、门限和该失败
结论保持不变。

main 随后只做了输入结构统计。`anonymous_targets` 表示在线 D1/D2 匿名航迹，数量会因
漏检、虚警和航迹起落变化；它不是场景真值目标清单。`anonymous_resources` 仍等于配置
资源数，规则成本矩阵的行、列分别与匿名航迹和匿名资源一致。v1 将在线航迹数强制等于
配置目标数，属于输入语义错误。

v2 使用独立合同
`configs/a1_source_independent_evaluation_contract_v2.json` 和独立入口
`simulations/run_a1_source_independent_evaluation_v2.py`。cell 字段改为
`configured_scenario_target_count`，仅表示场景配置；逐帧
`observed_anonymous_target_count` 可小于、等于或大于该值。配置资源数仍须逐帧精确匹配。
成本矩阵、动作掩码、候选边、需求槽和匿名实体的内部形状继续由
`LearningFrameRecord` 严格校验。结构错误同时记录 scenario、seed、episode、frame、
匿名目标/资源数量和矩阵形状，不输出真值身份。

v2 与 v1 的 bundle 三摘要、seed/cell/split、五项性能门限和全部关闭权限逐项相同。
v2 合同 SHA-256 为
`f47ec9d095af11042c670b0e358e3e7285a166fa48e3df57829b14c1da8497e7`，冻结源码树
SHA-256 为
`b31d0b86f53ff4dc32a01dc9ecc7988539a5635cbc31b674cd74b55a69de2438`。
新增结构测试 `9 passed`，v1/v2 专项 `26 passed`，D3 全量
`649 passed, 1 skipped`。当前状态是
`evaluator_v2_ready_evaluation_not_run`；本阶段没有运行 v2 评价，也没有读取正式 seed
`1000-1019`。

## 2026-07-30 A1 来源独立只读评价器（评价前历史状态）

D3 已为冻结的 assignment-aware A1 开发候选建立第一阶段来源独立评价工具。固定合同位于
`configs/a1_source_independent_evaluation_contract_v1.json`，只接受
`mode=source_independent_evaluation`。冻结 bundle 的 manifest、state-dict 和目录树
SHA-256 分别为
`ec9f93d668e1aa319f65fcda0d73adb0527f316a2d1880e93e88697b6468ad3d`、
`c185823bd9a4cf5363d17854385aeb74c340c8ac384327281d224a1097eb8206` 和
`de7b627df9782d7d2577687f30d02d4faeeaf577ecc557c2b8d91dd6e7115dd9`。
任一摘要、权限或源码清单变化均失败关闭。

合同预注册新来源种子 `20000-20099`，覆盖 5、20、50、100、200 五档规模和九类场景。
数据原有 train、validation、test 标签只作为来源子组，统一进入一次
source-independent evaluation；不训练、不选模、不重拟合归一化、不调整阈值。预注册门限
为：正类安全换绑至少 `1` 帧且比例不低于 `5%`，正类教师完全匹配至少 `1` 帧且比例不低于
`2%`，负类 exact-R0 不低于 `99%`。重复资源、硬禁边、多机需求不完整、版本违规、在线
真值使用和所有权限必须为零；任何拒绝帧的有效矩阵和绑定必须逐项恢复 R0。

评价入口按 JSONL 单遍流式读取 200 对 200 稠密帧，不把完整数据集同时驻留内存。输出为
逐帧 JSONL/CSV、聚合 JSON、中文报告和 `SHA256SUMS`，已存在的结果目录一律拒绝覆盖。
命令入口为：

```bash
python3 research_modules/d3_assignment_planner/simulations/run_a1_source_independent_evaluation.py \
  --mode source_independent_evaluation \
  --generation-root "$GENERATION_ROOT" \
  --dataset "$GENERATION_ROOT/learning_dataset/d3_assignment" \
  --output "$NEW_ONE_SHOT_OUTPUT"
```

2026-07-30 仅完成工具和合同测试，专项 `17 passed`；D3 全量收集 641 项，结果为
`640 passed, 1 skipped`。跳过项是可选 OR-Tools。新来源评价没有运行，未生成评价结果；
正式 seed `1000-1019` 仍为 `not_read_not_evaluated`。runtime、assist、assignment、
plan、control、physical 和 formal admission 权限全部关闭。

## 2026-07-28 A1 隔离批次公共严格读取

D3 已公开 `load_a1_isolated_intervention_batch(...)` 和
`validate_a1_isolated_intervention_batch(...)`。两个入口都从输出目录重新读取文件，不
接受调用方预填的“已校验”对象。读取顺序为固定七文件布局、`SHA256SUMS` 六文件全覆盖、
四个 JSON 的精确字段和内容摘要、旧批次逐帧摘要、A1 候选及逐 seed 选择关系。

读取器复用现有真值隔离、有限值、严格映射、SHA-256 和
`validate_a1_intervention_preregistration(...)`。它重新核对固定 seed `1000-1019`、
预注册帧范围、输入 manifest、模型 manifest、state-dict、逐帧文件/内容/replay/
eligibility 摘要、候选与选择计数、首个安全候选及计划版本连续性。目录缺文件、未知文件、
符号链接、校验和路径逃逸、摘要错配、未知字段、非有限值、复合 truth/Actor/Object 身份
键和权限升级均失败关闭。

返回对象只表示离线批次工件通过软件合同验证。`plan_published`、`runtime_ack`、
`physical_window_available`、`r0_pair_available`、production admission、分配权限和控制
权限属性固定为 false。candidate/selection 不能被解释为发布、运行采用、物理窗口、同键
规则基线或正式 A1 准入。

2026-07-28 的合成合同主夹具使用 20 个 seed、每 seed 2 帧，共 40 个候选和 20 个选择
记录；另用 20-seed 零离散变化夹具验证 0 个选择可作为 unavailable 正常读取。隔离批次
专项 `46 passed`；D3 全量为 `593 passed, 1 skipped`。跳过项仍为可选
OR-Tools，既有 Matplotlib `Axes3D` 环境告警不影响读取器结论。该测试只关闭公共 strict
loader 软件缺口，既有正式 A1 `0/20 eligible`、无发布、无运行确认和无物理结果状态不变。

## 2026-07-27 A1 动作裕量校准

正式保留种子证据仍是 `20/20` 处理矩阵发生变化、`0/20` 最终绑定发生变化。当前冻结
bundle 清单为 development/shadow，`alpha=0.25`、`min_confidence=0.0`，
`assist_authorized=false`。该结果此前只能说明残差没有跨过离散分配边界，不能区分代价
间隔、残差方向、修正幅度和安全门拒绝的各自影响。

模块新增 `calibrate_a1_action_margin(...)`。输入是既有
`IsolatedLearningInterventionFrameReplay`，不接收真值或仿真实体身份。接口在同一冻结帧
上执行三步诊断：

1. 对每个目标的硬安全候选边，计算规则最低成本边与其他候选边的局部代价间隔。
2. 从已记录的 `learning_delta_c` 恢复有界方向优势，计算候选边跨越局部间隔所需的
   `alpha`，同时给出理论上限 `2*alpha` 是否可能覆盖该间隔。
3. 对显式候选 `alpha/min_confidence` 网格重新调用原 Hungarian 或需求槽 Hungarian，
   记录实际代价矩阵变化、绑定变化、规则基准成本差和安全门拒绝原因。

候选修正仍受 `max_abs_cost_correction` 和 `max_binding_change_count` 限制。置信不足、
源 bundle 未加载、源帧回退、分布外、版本不一致、修正越界、换绑数量越界或既有计划
安全检查失败时均返回失败关闭。候选不能改变 hard-safe mask，不能跳过身份承诺、计划
版本、联盟全有或全无及 Hungarian 求解。输出固定
为 `development_only=true`、`formal_evidence=false`、
`unseen_seed_evidence=false`，且发布、分配和控制权限全部为 false。

开发单元夹具使用一个三资源、两目标的 M-to-N 冻结帧。源 `alpha=0.02` 时绑定保持不变；
同一已记录残差在候选 `alpha=0.25` 时产生 3 条绑定差异。零残差始终为 no-op；
`min_confidence=1.0` 触发低置信回退；修正超过预设上限时不进入求解；换绑数量超过候选
上限时不具备可辨识候选资格。该结果只验证校准路径可区分 no-op、可辨识干预、安全门
阻断和未授权状态，不是未见 seed、模型晋级或任务收益证据。

入口会重新计算冻结重放摘要，并检查规则/处理矩阵、清单、非有限值、分解项形状和
hard-safe mask。空矩阵、无可行动作、源帧已经换绑和构造后篡改均失败关闭。候选结果保存
规则/处理绑定摘要、求解器和计划版本证据；这些字段只证明执行了版本化主线求解，不授予
发布权限。

D3 全量收集 572 项，结果为 `571 passed, 1 skipped`。跳过项为可选 OR-Tools；既有
Matplotlib `Axes3D` 环境警告不影响本接口。

## 2026-07-27 提交前复核

A1 候选反序列化现重新检查规则计划和处理计划相对前序版本只能保持或递增一次；发生绑定
变化且版本合同为真时，处理计划必须严格为 `previous_version + 1`。只修改版本字段并
重算内容摘要会以 `candidate_plan_version_lineage_invalid` 拒绝。

A1 和隔离批处理同时拒绝 `target_truth_id`、`actor_truth_id`、
`resource_actor_name`、`target_object_id` 等复合身份键。D6 后选择物理窗口中已校验的
离线制品摘要名称仍可作为 provenance，不进入候选选择。D3 全量收集 563 项，结果为
`562 passed, 1 skipped`；跳过项为可选 OR-Tools，另有既有 Matplotlib 环境警告。

Centralized rolling `M` target / `N` resource assignment research module.

Boundary: this module only supports offline simulation, evaluation, and human-review candidate planning. It excludes real fire-control parameters, damage logic, flight or hardware drivers, autonomous disposition, and authorization bypasses.

## A1/C1/F1 Assist Evidence Assembly Audit

The 2026-07-26 follow-up found that D3 did not yet have a strict
`D6 audit -> D3 evidence assembler -> new bundle` chain. Legacy v2 bundles
were already blocked from assist, but a caller could still write or hand-edit
a v3 manifest with positive booleans and syntactically valid placeholder
hashes. The loader treated those declarations as qualified evidence.

The production boundary now fails closed:

- `save_model_bundle()` writes development/research bundles only and rejects
  caller-provided qualified admission before creating bundle files;
- v2 and development v3 bundles remain available for shadow;
- a hand-edited v3 manifest that passes the existing field and promotion
  checks still cannot enter assist, and returns
  `bundle_assist_evidence_assembler_unavailable`;
- the promotion manifest remains a model-comparison record, not an authority
  source.

No second D6 audit schema was added. A future D3-specific assembler must consume
the existing D6 formal-scope audit and checksum artifacts, bind them to the
exact dataset, source, model state, and bundle tree, and emit a new immutable
bundle. Until that assembler exists, production D3 has no positive assist path.

The actual bundle at
`outputs/formal_bc_development_20260720/bundle/` remains unmodified. Its
manifest/state SHA-256 values are
`a9213d65606a9e2f921040e153488c0f4cdebb10882fa16013fce5b59f9314c0` and
`e3da9fd5b54451da83358405b6051991e0c78bcf9f538b350d459b05faf8e0b2`.
Under the `d59352b` binding algorithm its two-file tree SHA-256 is
`3c08e58171c0474de9596fd3285d17bb50614a88cd7bbf3bf9af5345c7fee085`,
and its A1 binding SHA-256 is
`70aa1b0f0f2869cdae0f9ba32b18499b003c88ebfcdb9e9dce0bc950b13542a8`.
The manifest is still `stage=development`, `allowed_modes=[shadow]`,
`assist_authorized=false`, and `promotion_status=unavailable`. Shadow loading
succeeds; assist loading returns `bundle_shadow_only`.

Main runtime resolution therefore produces `effective_mode=rule_fallback` and
`bundle_loaded=false`. With rule fallback forbidden, A1 is rejected before an
episode is written. C1 and F1 reject D3 for the same reason and also require
independently admitted D4/D5 bundles. The current D3 bundle cannot legally
create A1, C1, or F1 formal evidence.

The strongest existing independent result remains the D6 sidecar
`d6_evaluation_metrics/outputs/reserved_seed_interventions_nominal_5v5_1000_1019_formal_7891296_d6_profile_bound_v2_audit_20260722/outcome_availability_sidecar.json`
(file SHA-256
`f3852251daf02ec87fe878e7fb80aad6f381d8c0756a5c956a32e737a3871c3b`).
Its status is `pass_offline_assignment_comparison_only`; runtime ACK, physical
outcome, and paired non-degradation are explicitly unavailable. D6 now also
has a formal-scope auditor that can validate bundle-tree binding, actual assist
adoption, physical results, and same-key R0 non-degradation. No actual A1 audit
output was supplied, the auditor does not itself grant promotion, and it does
not enforce D3's minimum 20 unseen seeds. These are reusable software
capabilities, not current admission evidence.

After main/D7 produce hash-bound adoption and physical evidence for all 20
reserved seeds, D6 emits a passing checked report, and D3 implements the
module-specific assembler, main's first admission check will be:

```bash
python3 -m research_modules.scalable_3d_simulation.run_experiment_matrix_shard \
  init-scope --scope-variants A1 --formal \
  --d3-model-bundle "$D3_ADMITTED_BUNDLE" \
  --output "$A1_EXECUTION_ROOT"
```

On 2026-07-26 the focused bundle tests passed `21/21`; the complete D3 suite
completed with `465 passed, 1 skipped`. The skip is the optional installed-only
OR-Tools case. One existing Matplotlib `Axes3D` import warning does not affect
D3 admission.

## R0 Rolling-Demand Inventory Guard

On 2026-07-25 the clean-source R0 cell at commit `32b3b40`, scenario
`high_threat_m_to_n`, scale 200, seed 1000, and duration 2.0 s failed at
`t=1.0 s`. Target `GT3D-000021` changed from an empty incomplete `k=1`
coalition to a complete `k=3` candidate. Other coalition membership changes
were still inside dwell, so the global membership hold retained the previous
inventory. Previous-plan scoring had skipped demand compatibility for a
target with no executable assignment; final inventory normalization then
raised `coalition demand does not match current demand`.

The planner now evaluates the previous coalition demand contract before the
empty-assignment branch. A changed required count, primary count, coordination
mode, timing contract, or assignment demand marks the previous plan
incompatible. Hysteresis cannot retain that inventory; the current
solver-produced candidate is rebuilt and still passes the existing capacity,
unique-resource, all-or-none, primary/reserve, stale-plan, and version checks.
The plan records the incompatible target IDs and whether the rebuild was
required and applied.

An exact-configuration development rerun on 2026-07-25 completed 2.0 s with
finite state and zero online truth use. At `t=1.0 s`,
`GT3D-000021` was rebuilt as a complete `k=3` coalition under
`accepted_previous_infeasible`; 197 final assignments used 197 unique
resources, with zero overallocated targets and zero demand-summary mismatch.
The D3 suite passed `464 passed, 1 skipped`; the skip remains the optional
OR-Tools test.

This is implemented and tested development evidence. The failed formal
artifact remains bound to clean commit `32b3b40`; main must rerun the cell and
formal shard from a new clean source commit before marking formal R0 complete.

## Multi-Cycle BC Residual Shadow Evaluation

On 2026-07-25 D3 added an isolated multi-cycle evaluator for the frozen
behavior-cloning residual.  It runs independent rule/control and
residual/treatment planners on the same anonymous tracks, resources, numeric
seed, timestamps, and exogenous events.  Both arms keep the existing
Hungarian or demand-slot Hungarian solver and hard-safe candidate mask.  The
treatment cost matrix is never published to the runtime bus.
Optional `planner_config` and `cost_weights` inputs are applied symmetrically
through separate rule and treatment `CostModel` instances.

The recorded shadow run used reserved seeds 1000-1019 with zero overlap against the 100
training seeds.  Its six scenarios cover a Hungarian switching boundary,
5 resources/3 targets, 3 resources/5 targets, resource failure and recovery,
target addition/removal, and M-to-N demand change.  Across 620 paired cycles:

- the frozen residual changed 580 effective cost matrices;
- 120 cycles and 20/20 seeds produced a different final binding;
- all 20 seeds were identifiable in the controlled Hungarian boundary;
- 40 M-to-N demand-change cycles were out of distribution and restored the
  exact rule matrix;
- duplicate resources, hard-constraint or lineage violations, stale-version
  adoption, and online truth use were all zero;
- inference latency was 0.228 ms at P50 and 0.361 ms at P95 on this host.

Rule churn was 520 and treatment churn was 200, while the treatment plan cost
rescored on the rule matrix was higher by 0.000707 per cycle on average.
This is a measured tradeoff, not a benefit claim.  The evaluator has no
runtime ACK, physical outcome, causal reward, or promotion authority.
`promotion_recommended`, PPO, online assist, online authority, and runtime
publication therefore remain false.  Artifacts are under
`results/multi_cycle_shadow_bc_20260725/`.
Both CSV artifacts use an explicit LF line terminator so repository whitespace
checks do not depend on the platform default.
The artifacts bind the seed registry, bundle manifest, weights, dataset, and
split hashes, but they were generated before these source changes had a clean
commit.  They remain development evidence until a clean-worktree rerun records
the source revision and configuration digest.

## Identity Commitment Admission

`TargetTrack.identity_commitment_state` supports `committed`,
`identity_uncommitted_ambiguity_hold`, and
`identity_uncommitted_after_hold`. Missing values normalize to
`identity_commitment_missing`; unsupported values normalize to
`identity_commitment_unknown`. Both fail closed.

Only committed targets enter the hard-safe candidate mask. An uncommitted
target cannot produce a one-to-one assignment or any M-to-N primary/reserve
slot. Main owns the hold/replan trigger. Once main supplies a revoked state and
requests a new planning tick, D3 removes the target bindings, publishes a
strictly newer candidate plan, and records the reason without mutating the
previous plan or rewriting `global_track_id`.

The AirSim dry-run adapter reads a direct field, an `identity_commitment`
mapping, or metadata. It does not use actor identity or offline labels. On
2026-07-23 the focused file passed 12 tests; the full D3 suite passed
450 tests with one existing optional OR-Tools skip.

Clean scalable-runtime evidence is now available for commit
`7e15dac9cdaf6743999dfe045a70676fd31a17d6`
(`repository_dirty=false`), nominal 200-resource/200-target, 2.2 s, seed 1100.
Both `hold_only` and `hold_plus_centroid` arms published plan v1 with 193
assignments at `t=0.75`. At `t=1.0`, 11 targets previously assigned by v1
became `identity_uncommitted_ambiguity_hold`; D3 bypassed hysteresis for the
safety withdrawal and published v2 with 186 assignments. All 11 targets were
absent from v2. Plan v3 retained 186 assignments at `t=2.0`. From `t>=1.0`,
those targets had zero D3 assignments, D5 active-vision commands, D5 terminal
bindings, and D7 guidance commands.

The runtime diagnostic `d3_identity_commitment_binding_hold_count=13` is a
main binding-hold count across the event; it is not the D3 rejected-target
count, which is 11. This episode did not inject a stale plan. Active stale-plan
injection remains covered by module and AirSim regression tests. The identical
two-arm result validates the runtime safety withdrawal only; it does not prove
an algorithmic benefit from D1 centroid correction or D2 association.

## Layout

- `PLAN.md`: engineering/scientific plan and mathematical formulation.
- `src/d3_assignment_planner/`: Python implementation.
- `src/d3_assignment_planner/fixtures.py`: versioned non-equal, dynamic-event, D5-feedback, and hard-window fixtures.
- `src/d3_assignment_planner/calibration.py`: reusable full/incremental P1 matrix runner and D6-friendly summaries.
- `src/d3_assignment_planner/cooperative_prescreen.py`: versioned M-to-N cooperative candidate grid, observed-result ranking, and current-plan metadata export.
- `src/d3_assignment_planner/learning.py`: optional shared candidate-edge PyTorch residual, behavior-cloning warm-up, shadow/assist inference, masks, and rule fallback.
- `src/d3_assignment_planner/runtime_plan_ack.py`: strict read-only validation of main runtime plan adoption ACKs.
- `src/d3_assignment_planner/isolated_plan_consumption.py`: versioned, replay-safe confirmation that an isolated rollout arm consumed one exact plan; this is not a production runtime ACK.
- `src/d3_assignment_planner/runtime_reward_evidence.py`: hash-bound adopted-window to observed-outcome attribution contract; formal reward remains fail-closed.
- `src/d3_assignment_planner/paired_intervention.py`: strict seed 1000-1019 control/treatment specification, isolated execution receipt, and verified runtime-ACK reference contract.
- `tests/`: unit tests.
- `simulations/run_rolling_assignment.py`: 100 s, 2 Hz rolling simulation.
- `docs/ALGORITHM_AND_IMPLEMENTATION.md`: Chinese algorithm principles and implementation guide.
- `docs/EXPERIMENT_REPORT.md`: experiment method and latest local results.
- `docs/AIRSIM_INTEGRATION_PLAN.md`: AirSim offline integration plan.
- `results/`: generated CSV, JSON, plots, and generated report after running simulation.

## Test

```bash
cd /home/linux/Documents/MSM/research_modules/d3_assignment_planner
pytest
```

## Simulate

```bash
cd /home/linux/Documents/MSM/research_modules/d3_assignment_planner
python3 simulations/run_rolling_assignment.py
```

Optional fallback-only run:

```bash
python3 simulations/run_rolling_assignment.py --force-fallback
```

The default run uses 8 targets, 8 resources, 100 seconds, and 2 Hz. It compares no hysteresis with `delta=0.2` and `min_dwell=2.0`.

## M-to-N Demand Slots

`AssignmentPlan` now publishes `assignment_plan_v2`. A `TargetTrack` with no
`demand` keeps the original `k=1`, `independent`, Hungarian behavior. An
explicit `TargetDemand()` selects the high-threat research default `k=3`,
`hybrid`: two `primary` members in wave 0 and one `reserve` in wave 1.
`TargetDemand.primary_resource_count` controls that split and defaults to 2;
main's `--cooperative-primary-count` should be passed into this field. It must
satisfy `1 <= primary_resource_count <= required_resource_count`. The implicit
and explicit independent `k=1` demand uses `primary_resource_count=1`.

The `hungarian_demand_slots` path expands each target into role/wave/capability
slots, prioritizes higher-threat targets, and performs all-or-none admission.
An incomplete coalition publishes no executable `Assignment`; its
`CoalitionPlan` and `DemandSatisfactionSummary` retain candidate members plus
`demand_required`, `demand_assigned`, `demand_shortfall`, and completion state.
`simultaneous`, `sequential`, `hybrid`, and `independent` scheduling modes are
supported. Arrival windows, wave interval, minimum separation, and required
capability counts are explicit demand fields.

Use `assignments_by_target()` for multiplicity and `assignment_by_resource()`
for the resource index. The legacy `assignment_map()` remains valid for
one-to-one plans and raises `ValueError` for multi-resource targets. Stable
assignment signatures drive hysteresis, change counts, and switch penalties;
coalition member/role changes increment coalition version; executable window
changes increment plan version, while pure cost evaluation preserves it. D7 bindings
carry coalition identity, role, wave, mode, window, and minimum separation, and
only a current committed coalition can produce an active binding.
Changing `primary_resource_count` also changes the coalition demand signature,
increments coalition version, and is exported in binding fields/metadata.
`AssignmentPlan.execution_signature()` additionally covers executable bindings,
coalition state/members, role/wave/windows, owner, and activation/lease semantics.
For both `k=1` and `k>1`, a pure cost/evaluation refresh retains executable
`plan_id/version`, assignment `plan_version`, `created_at`, and coalition
`version/epoch`; it sets `evaluation_refresh_only=True` and updates only
diagnostic costs and `last_evaluated_at_s`. A resource/role/target/owner or
activation change advances executable identity. Secondary takeover is an
explicit new lineage. Plan and assignment metadata keep lineage creation time
in `identity_created_at_s` and the current evaluation tick separately.

An evaluation refresh is not a second authoritative transport publication.
`AssignmentPlan.requires_authoritative_publication(previous_plan)` returns
`False` when the plan identity and all authority-driving fields are unchanged,
and fails closed if a member, role, coalition, owner, lease, authorization,
inventory count, or other execution field changes under the same identity.
Main must retain the first complete bus payload and SHA-256 for that identity;
updated timestamps, costs, hysteresis decisions, input fingerprints, and edge
evidence belong in a separate evaluation/history record. Rehashing a reduced
projection is not a substitute for retaining the immutable source payload.

The initial 2026-07-30 v3 100-cell audit found 48 same-identity refresh groups.
All 48 kept the authority projection unchanged, while all 48 changed the
complete payload and 33 also changed only the serialized assignment order. In
200v200 seed1017, this produced 37 payload-digest/cross-binding rejections.

Main subsequently integrated the D3 publication-disposition contract. D3
reviewed the implementation and the v4 development batch
`/dev/shm/msm-high-threat-r0-p0-precheck-v4-20260730`. Across 100 episodes,
151 authority identities produced 151 authority publications and 151 plan
ACKs; 48 same-identity evaluation refreshes were suppressed. Digest conflicts
and duplicate transport-reference counts were both zero. D3-D4 plan
alignment and current-coalition closure were both 100/100. This closes the P0
for development validation. A clean, frozen formal R0 rerun is still required;
the v4 point-mass batch is not formal R0, AirSim, or physical-interception
evidence. The current D3 full regression collected 655 tests:
654 passed and one optional OR-Tools test was skipped. See
`reports/D3_PLAN_IDENTITY_PAYLOAD_AUDIT_20260730_CN.md`.

OR-Tools is not a default dependency. The isolated P2 benchmark feeds one
unequal-N/M, hybrid primary+reserve, capacity-constrained demand-slot problem
to SciPy Hungarian (capacity-column expansion) and optional OR-Tools min-cost
flow (native resource capacities). Missing dependencies are returned as a
structured `unavailable_reason`; the default planner does not select either
benchmark adapter dynamically.

Run the isolated comparison with:

```bash
python3 research_modules/d3_assignment_planner/simulations/run_p2_capacity_benchmark.py
```

The checked fixture has 4 resources, 3 targets, 5 demand slots, and capacities
`(2, 1, 1, 1)`. SciPy Hungarian returns objective `5.6`. In the current
environment OR-Tools is absent, so its result is `status="unavailable"` rather
than a failed benchmark run. This slot-level comparator checks capacity and
cost equivalence; it does not implement online coalition all-or-none admission.

## Incremental Planning

`AssignmentPlanner.plan_incremental(...)` accepts the current tracks/resources,
the exact published `previous_plan`, declared `changed_track_ids` and
`changed_resource_ids`, timestamp, and expected previous version. Every normal
plan stores deterministic track/resource/demand fingerprints. The incremental
entry compares those snapshots with the declared changes, builds the current
target-resource feasibility graph, and solves only the disconnected component
reachable from changed entities and their previous bindings. Unaffected
feasible assignments and coalition members retain their target/resource,
coalition identity/version, role, and wave; plan-version and evaluation metadata
are refreshed through the standard publication path.

The implementation is deliberately conservative. Missing snapshots, omitted
changed IDs, target/resource set changes, demand changes, expired plans,
time-dependent constraints, or a component that expands to the global problem
run the standard full planner and record `incremental_fallback_reason`. An
expected/current plan-version mismatch remains `StalePlanError` and exposes its
reason through `to_metadata()`; it is not silently replaced. Hysteresis is
applied after the local candidate is merged into the full plan, so relative
gain, dwell, change limits, high-threat release, M-to-N all-or-none admission,
and switch-penalty single charging keep their existing global semantics.

`summarize_incremental_planning_comparison(...)` compares incremental and full
plans by cost, assignment equivalence, latency, target-level change count, and
preserved assignment count. Latency is calibration evidence only; the planner
does not automatically choose a path from one timing sample.

`run_p1_assignment_calibration_matrix(...)` runs the same planner profile over
5v5, 3v5, 5v3, target arrival, resource failure, high-threat demand change,
D5 reserve feedback, and hard-window transitions. Each row reports full versus
incremental latency, churn, unassigned high-threat count, coalition shortfall,
hard-window rejects, equivalence, fallback reason, and role-aware primary
preservation. It is an offline calibration harness and never changes the
default Hungarian/demand-slot path from timing results.

Run the deterministic matrix as JSON with:

```bash
python3 research_modules/d3_assignment_planner/simulations/run_p1_assignment_calibration.py
python3 research_modules/d3_assignment_planner/simulations/run_p1_assignment_calibration.py \
  --output research_modules/d3_assignment_planner/results/p1_assignment_summary.json
```

The `--output` path is optional. When supplied, parent directories are created
and the same formatted `summary.as_dict()` JSON is written to the file and
printed to stdout.

## Cross-Node Contract

`AssignmentPlan` and each `Assignment` expose cross-node metadata for integration dry runs: `source_node_id`, `target_node_id`, `link_type`, `plan_version`, `stale_after_s`, `terminal_feedback_state`, and `duplicate_terminal_lock_risk`. D3 also provides `evaluate_terminal_feedback(...)` to map D5 states into conservative recommendations:

`AssignmentPlanner` is stateful for one episode. Its first `plan(...)` call may use `previous_plan=None` and creates version 1. Stale checks use only the latest published identity. `plan(..., publish=False)` returns a candidate without advancing latest, and `publish_plan(candidate)` publishes a reviewed candidate. After a plan is published, later calls must pass that exact active identity as `previous_plan`; omitting it raises `StalePlanError` with `reason="previous_plan_required"`. Main must create a new planner instance for a new episode; D3 does not provide an implicit reset.

- `ambiguous` / `hold` -> `hold`
- `reacquire` -> `replan`
- `mismatch` or duplicate terminal lock risk -> `secondary_arbitration`

The feedback decision includes `main_action` and `planner_metadata` so main can apply a conservative integration action without local rebinding. The metadata explicitly carries the backward-compatible hold/feasibility/FOV fields plus additive `feedback_constraint_class`, scope, hard-reject flag, and classification reason. `apply_terminal_feedback_to_planner_inputs(...)` classifies ordinary `ambiguous`, `hold`, `reacquire`, geometry/FOV, and detection-instability evidence as `resource_target_edge_soft`: it raises only that edge's FOV cost, keeps D7 on hold, and leaves `ResourceState.operator_hold=False`. `friend_overlap_hold` remains resource-hard, verified-friend evidence is target-hard, and safety identity conflict, duplicate assignment/lock, or explicit feasibility rejection remains fail-closed. Existing metadata names, including nested `resource_update`, remain accepted; a legacy pair hold is downgraded to soft and audited rather than expanded to the whole resource.

The writeback also preserves normalized `terminal_feedback_events` with target,
resource, source plan version, coalition reason/conflict, stable-lock counts, and
the upstream required stable window. Before ordinary cost hysteresis, both
`plan()` and `plan_incremental()` apply a version-matched dwell to coalition
primary membership. `PlannerConfig.transient_feedback_dwell_frames` defaults to
2; the effective window is the maximum of this value and D5's
`required_stable_frames`, so D3 cannot weaken the visual gate. A short
`primary_lock_stability_incomplete` or `reacquire` holds a still-feasible
primary set until that window completes. Completing the frame window does not
bypass ordinary `delta`, `min_dwell`, change-limit, or coalition-member
hysteresis. Duplicate/friendly conflict, wrong
binding, loss, resource unavailability, explicit prohibited edges, or any other
old-plan infeasibility bypass the dwell immediately. Feedback for another plan
version is audit-only and cannot protect or release the current coalition.

Per-member reserve feedback has a separate role-aware rule that does not depend
on coalition reason, stable-window fields, or a role supplied by main. D3 joins
each version-matched target/resource event to the previous plan assignment. If
every previous primary reports `consistent/continue`, at least one previous
reserve reports a soft `hold/hold` or `reacquire/replan`, and all old primary
edges and capabilities remain feasible, the demand-slot matrix pins exactly
that previous primary set. The solver may constrain or replace reserve slots
without rotating a healthy primary into reserve. The resulting reserve change
is still a candidate and must pass ordinary member/global hysteresis. Any primary failure,
duplicate/friendly/wrong-binding conflict, unavailable primary edge, changed
demand, or stale feedback disables the pin and follows the existing hard-risk
or primary-failure policy.

`ResourceState` also carries P0-B resource detail fields: `energy_fraction`, `availability_score`, `current_load`, `history_failure_rate`, `intercept_feasibility_by_target`, and `intercept_feasibility_score_by_target`. `CostModel` consumes them through `resource_state` subcomponents and hard infeasible flags, so D6-facing cost breakdowns can distinguish energy, availability, load, historical failure, and intercept feasibility causes.

`TargetTrack` supports a lightweight hard time-window baseline through explicit fields or metadata: `hard_time_window`, `time_window_open_at_s`, `time_window_close_at_s`, `time_window_state`, and resource-specific `time_window_by_resource`. When a window is explicitly closed, expired, or not yet open, `CostModel` marks that edge infeasible, sets hard-window reject flags in the breakdown, and `AssignmentPlanner` exports the rejected edge with a readable `reject_reason`; the soft `window_cost` term remains available for ordering open edges.

`compose_threat_score_baseline(...)` provides the P0-C explainable baseline for `TargetTrack.threat_score`. It combines critical-zone proximity, TTC, speed, covariance, and target state into a normalized score with components/reasons metadata. This is a baseline helper only; full outcome-aware dynamic threat assessment remains a P1 model-calibration item.

`PlannerConfig.reassignment_switch_penalty` is applied before Hungarian/fallback solve. For a target assigned in `previous_plan`, every feasible edge to a different resource receives the penalty; the edge to the same resource does not. Targets without a previous assignment and all unassigned costs are unchanged. The solver input matrix, per-edge breakdown `total`, selected `Assignment.cost`, plan objective, and exported evidence therefore share one cost value, with no post-solve double charge.

D3 also exports:

- `assignment_validity_summary_from_plan(...)` -> `AssignmentValiditySummary(plan_id, version, plan_age_s, assignment_latency_s, cost_margin, stale_plan_version, duplicate_assignment_count, unassigned_high_threat_count, resource_count, target_count, assigned_count, hysteresis_reject_count, stale_reject_count, reassign_count)`.
- `assignment_records_from_plan(...)` and `assignment_evidence_from_plan(...)` -> D6/main outputs containing current plan identity, `identity_created_at_s`, `last_evaluated_at_s`, N/M shape, costs/reject reasons, hysteresis state, secondary audit fields, plus `assignment_profile_schema`, cost/feedback profile id/version, the exact cost-weight snapshot, and planner thresholds. A record without an explicit export timestamp uses `last_evaluated_at_s`, not the stable identity creation time.
- `plan_history_record_from_plan(plan, sequence_index=..., timestamp=..., previous_plan=..., feedback_metadata=...)` -> one canonical `PlanningTickHistoryRecord` per planning tick. `feedback_metadata` is optional and accepts `TerminalFeedbackWriteback.metadata`; otherwise compatible feedback keys are read from `plan.metadata`. Call `to_dict()` before JSONL persistence. The schema is `d3_plan_history_record_v1`, and history order is the lexicographic `[sequence_index, timestamp]` key supplied by main.
- `summarize_assignment_mismatch_replay(...)` -> `AssignmentMismatchReplaySummary(resource_count, target_count, assigned_count, unassigned_high_threat_count, hysteresis_reject_count, stale_reject_count, reassign_count)` for N/M mismatch replay aggregation.
- `summarize_incremental_planning_comparison(...)` -> `IncrementalPlanningComparisonSummary` with incremental/full cost delta, equivalence, latency, change counts, and preserved targets/assignments.
- `summarize_terminal_feedback_calibration(...)` -> advisory `TerminalFeedbackCalibrationSummary` from multi-seed assignment/feedback records. It reports duplicate/friend/fov/geometry reject counts and cost/hysteresis tuning directions, but never rewrites `CostWeights` or `PlannerConfig` defaults.
- `guidance_bindings_from_assignment_plan(...)` -> versioned `AssignmentGuidanceBinding` rows whose metadata includes identity creation and last evaluation timestamps. Binding freshness and `expires_at_s` use `last_evaluated_at_s`, with `created_at` as the fallback for legacy/manual plans. Main supplies the current `plan_id/version` when exporting a secondary binding; a historical plan, an unconfirmed secondary current identity, an inactive takeover, or an expired lease cannot produce an `active/current` D7 binding.
- `prepare_secondary_takeover_plan(...)` -> activates a D4/main-selected takeover candidate only after main supplies sustained `takeover_ready`, activation time, a live lease, and a positive monotonic leader epoch. A same-signature candidate may retain the current center identity; the helper advances identity exactly once for the owner/activation transition. Successful plans audit readiness, activation, supersede, owner, lease, epoch, and `allow_local_rebind=False` in plan, assignment, record, evidence, and binding metadata.
- `continue_active_secondary_plan(...)` -> converts the next ordinary rolling candidate into a same-owner secondary plan without a second takeover. It derives the concrete owner/source from the previous active plan, requires strict version/supersede continuity, sustained readiness, non-regressing epoch, and a live non-regressing lease; main must not hand-build these metadata fields.
- `build_p1_assignment_fixtures()` -> versioned deterministic 5v5, 3v5, 5v3, new-target, resource-failure, high-threat demand-change, D5-feedback, and hard-window inputs. Labels use `resources x targets`; explicit counts and changed IDs are present in fixture metadata.
- `run_p1_assignment_calibration_matrix()` -> paired full/incremental transition rows and aggregate latency/churn/high-threat/coalition-shortfall totals for main/D6.

The plan-history payload stores plan identity/state/counts and owner/source/
secondary epoch/lease once per tick, then deterministically orders assignments
by target, coalition, wave, role, and resource. Each assignment includes role,
activation/active state, coalition identity/version/epoch, validity, scalar cost,
and cost breakdown. The record also contains recoverable ordered coalition
members, hysteresis and membership-change evidence, feedback classifications
with soft/hard counts, costs, stale/rollback/replan audit reasons, and plan
lineage. It uses only JSON-native values; no `truth_id` argument exists and any
truth-named nested metadata key is excluded. `assignment_records_from_plan()`
remains backward compatible, including its offline-only optional truth label.

Main should persist one line per successful planning tick as follows:

```python
history_record = plan_history_record_from_plan(
    plan,
    sequence_index=tick_sequence_index,
    timestamp=planning_timestamp_s,
    previous_plan=previous_plan,
    feedback_metadata=None if writeback is None else writeback.metadata,
)
jsonl_writer.write(history_record.to_dict())
```

D3 defines and validates this record but does not own JSONL storage. The
existing 40-case aggregate predates main persistence of these records, so its
membership/version churn remains `unavailable`; the former pair-hold promotion
is a root-cause lead, not proven causality for those outcomes. A later actual-v2
run has separately proved main persistence and D6 consumption, as recorded
below.

`PlannerConfig.human_authorization_state` is the source of the plan authorization field. The planner records both `configured_human_authorization_state` and `effective_human_authorization_state` in plan metadata so main can run record-only simulation gates without hard-coding D3 to `"required"`.

For active degradation recovery, D3 does not emit D4 actions itself. Main calls `plan(..., forced_replan=True)` with the current published plan. If executable semantics are unchanged, D3 preserves identity and returns `decision_state="replan_ack_no_change"`; if they change, D3 advances identity once and returns `decision_state="replan_applied"`. Main/runtime integrates these states and any `replan_reason`/supersede metadata. A binding from an applied current plan remains `active/current`; the old published identity is stale.

Main/runtime has connected D5 feedback writeback, center replan owner/version/source recording, secondary owner/version/source recording, and the P1 D4/D5 calibration sweep. For secondary flow, main should request `publish=False`, apply `prepare_secondary_takeover_plan()` or `continue_active_secondary_plan()`, then call `publish_plan()` on the final owner-stamped plan. This prevents an intermediate center candidate from advancing published latest.

The 2026-07-11 P1 validation used 5 resources, 2 targets, and 10
ComputerVision seeds. T001 achieved two-primary visual consensus with current
plan authorization in 8/10 seeds; seeds 7 and 27 remain regressions. Together
with the incremental planner and role-aware primary-preservation tests, this
closes the D3 P1 contract layer rather than only the earlier demand-slot DTO.
Downstream secondary and distributed commit positive cases passed, and a
missing ACK aborted fail-closed with no D7 permission. The 2026-07-12 PNG
delivery change made no D3 code or behavior change. Its 2v2 candidate reached
20/20 physical pairs and therefore demonstrated a non-regressed one-to-one
chain under the current plan gate. The M5N2 8 s run reached 0/9 active pairs,
but is not comparable to the existing z=-30 m, 35 s high-clearance baseline;
the cooperative physical loop remains open pending a same-geometry,
same-window paired run. P2 remains an isolated optional benchmark and does not
replace the default Hungarian/demand-slot planner.

Local resources must not rewrite `global_track_id`; D3 publishes versioned candidate plans for review. For `secondary_plan_v2`, D3 does not choose a concrete secondary node, renew leases, elect leaders, or perform recovery arbitration. D4/main supplies those decisions; D3 validates the activation snapshot and prevents expired, non-monotonic, or non-current plans from yielding an executable D7 binding. Normal operation uses Hungarian/demand-slot assignment. The optional same-input capacity comparator is implemented and is not an open online P1 dependency. CP-SAT/MILP coalition admission, backup-resource quotas, multi-window flow, and large-scale sweeps remain isolated P2 benchmarks. D4 secondary-node arbitration is preferred before CBBA-style fallback.

Current D3 regression baseline (2026-07-14): `157 passed, 1 skipped` with `python3 -m pytest -q research_modules/d3_assignment_planner/tests`. The five newest deterministic tests cover soft-feedback/round-trip stability, cumulative same-window change budget, cross-window recovery, hard resource failure, missing-target plus another membership hold, plan-level owner change, and history budget export. Earlier plan-history, held-scope/lifecycle, and feedback-governance cases remain covered. The skip is the installed-only OR-Tools benchmark in an environment without the optional dependency.

## Per-primary authorization and coalition membership hysteresis

Cooperative demand now carries the versioned contract
`terminal_authorization_scope="per_primary"` and
`arrival_coordination_required=False`. Each active primary may therefore be
authorized independently by downstream D4/D5/D7 gates; a reserve binding is
explicitly `hold` with `reserve_standby_not_activated` and cannot execute
without a newer plan changing its role.

Per-pair diagnostics use the same contract in both D6 records and D7 binding
metadata. They expose plan owner/version, coalition id/version/epoch, role,
wave, activation, assignment validity, authorization eligibility, plan churn,
rollback detection, and stale-reject count. Only feasible active primaries are
reported as active/eligible; reserve rows remain standby and inactive. A
compatible current-plan evaluation refresh reports zero churn and no rollback
while preserving plan identity and coalition epoch.

For `k>1`, executable members and roles have a separate membership clock.
They remain fixed for at least `PlannerConfig.min_dwell` and may be replaced
only when the previous member set is hard-infeasible, or when the candidate
coalition cost improves by more than `delta` after dwell. Plan metadata exports
the previous/current member sets, reason, target cost comparison, dwell result,
and hold basis. Ordinary compatible cost refreshes preserve both `plan_id` and
plan version; coalition `version/epoch` advances only when a resource or role
actually changes. The Hungarian/demand-slot solver is unchanged.

## P1 Cooperative Candidate Prescreen

`build_p1_cooperative_candidate_grid()` defines the stable 27-candidate grid
used by main's M5N2 paired sweep: terminal handoff range `20/30/40 m`, primary
arrival-window width `3/5/8 s`, and approach-sector separation
`20/40/60 deg`. Candidate IDs are deterministic and do not depend on resource
or target count. `demand_for_cooperative_candidate()` applies only the timing
and audit metadata to an existing `TargetDemand`; required resources, primary
count, hybrid/simultaneous/sequential mode, capability requirements, wave
interval, and minimum separation remain caller-owned.

`export_cooperative_candidate_plan_metadata()` emits candidate ID, current
plan/coalition versions, target/resource IDs, role, wave, arrival window,
minimum separation, and an explicit activation state. A primary is `active`;
a reserve/retry is `standby`. The export rejects a non-current plan, stale
assignment version, or stale/non-committed coalition. It is read-only and does
not activate a reserve or alter Hungarian/demand-slot planning.

`rank_cooperative_candidates()` accepts only complete physical observations
from main/D6. It refuses missing candidate observations instead of estimating
success. Ranking is deterministic: zero safety violations first, then maximum
coalition-completion rate, maximum pair-success rate, minimum arrival spread,
and finally candidate ID as the tie break. The default output is the top three
candidates. D3 therefore supplies experiment design and plan/reachability
metadata; it does not manufacture AirSim outcomes. Same-geometry 10-seed M5N2
execution and the `8/10` coalition-completion acceptance target remain open at
the main/runtime level.

## 2026-07-14 真实 AirSim 计划历史审计

对 `p1_terminal_closure_truthisolated_preflight_v2_20260714_m5n2_baseline_seed001`
的 `episode_006_full_flow` 做了单 seed、349 个 planning tick 的只读复核。D3
初始计划包含 T001 的 2 个 active primary、1 个 standby reserve，以及 T002
的 1 个 active primary。后段 D2 连续产生 T003/T005/T007/T008 等新航迹，最终
current plan 为 T001 三成员、T002 一成员和 T008 一成员，因此执行产物出现 5 个
pair。T008 在 34.4 秒创建、34.5 秒 confirmed、34.6 秒 engageable；D3 不使用
truth，无法把它判定为物理目标或幻影航迹。

审计发现一个 D3-owned P1 合同缺陷：当候选因普通迟滞、联盟成员迟滞或 transient
feedback dwell 被 hold 时，当前输入中的新目标曾被写入 held plan 的
`unassigned_target_ids`，从而使 execution signature 改变并错误推进 plan/version。
修复后 held plan 完整保留上一 current plan 的 assignment、coalition、unassigned
和 incomplete 执行范围；当前候选只进入 `hysteresis_candidate_*`、
`hysteresis_pending_new_target_ids` 等审计字段。候选释放前不获得 current plan
身份。该规则不依赖 truth，不写死 M/N，也不放宽 stale、version 或 coalition 门控。

本次确定性验收标准是 hold 后 plan ID/version 与 execution signature 均不变，同时
仍记录实际输入 `target_count` 和 pending target。若上一已分配目标从当前输入消失，旧计划
直接判为 infeasible 并发布新版本，不允许迟滞继续持有不存在的执行目标。D3 全量结果为 `157 passed,
1 skipped`；唯一 skip 是 optional OR-Tools installed-only benchmark。真实 episode
没有在本任务中重跑。

两个跨模块问题保持开放：AirSim adapter 当前把除 lost/dropped 外的 D2 航迹都标为
assignable，应由 main/D2 准入链只向 D3 提交 engageable 或显式批准的航迹；D3 不以
本地 dwell 掩盖 D2 幻影。其次，D3 最终仍把 INT-01 reserve 输出为 standby/hold，
`intercept_summary.json` 中后续 active 来自 runtime pair 在 primary 变为 reserve
时未撤销旧 active 状态，不属于 D3 reserve activation。

## 2026-07-14 P1 计划抖动预算与统一成本口径

最新 truth-isolated M5N2 baseline seed 001 有 347 条 canonical planning records，
执行版本为 v1..v35。稳定双目标阶段仍约每秒往返换员。记录中的一个代表性 tick
把候选联盟成本写成 `0.8868`、previous 写成 `2.8520`；previous 当前边内含
`2.2` 的 soft-feedback FOV shaping，去除该候选搜索项后 previous 基础执行成本约为
`0.6520`，候选并未达到 20% 改善。该现象证明原 membership gain 比较混用了
search objective 与 execution comparison objective。

planner 现在使用 `d3_hysteresis_current_objective_v1` 同时重评 candidate 和
previous：包含当前 target-resource 基础成本、硬可行性和
`unassigned_cost * required_resource_count`；排除只用于搜索的 switch penalty、
soft-feedback FOV shaping、demand-slot priority 和 role pin。solver/evidence 仍保留
完整 search cost，metadata 同时记录 search/comparison 两套数值，避免再把口径差异
误判为 `delta=0.2` 收益。

`max_changes_per_window` 现在由 plan metadata 延续
`d3_cumulative_window_change_budget_v1`：同一 `window_id` 累加已接受的 assignment
change count，hold/evaluation refresh 不计费，新 window 清零。execution target
缺失、资源硬失效和 plan-level owner/activation/authorization 改变仍立即生成新版本，
预算不足时记录 bypass；成员 primary/reserve 候选本身仍受 coalition hysteresis，
不会借 activation 名义绕过。missing target 与另一联盟 hold 同时出现时，消失目标
不会进入新 assignment、coalition 或 membership audit。

本批只完成确定性实现验收，未重跑 AirSim。D3 全量为 `157 passed, 1 skipped`，零
失败达到接受阈值；剩余 P1 是 main/D2 lifecycle admission、runtime reserve
demotion、至少 10 个同几何 seeds 的 churn/高威胁未分配复验，以及 M5N2 物理
coalition completion 从当前最佳 `5/10` 达到 `8/10`。

## 2026-07-14 Actual-v2 真实 AirSim 证据链

本次只同步 main 已完成的真实 AirSim 证据，不修改 D3 代码、Hungarian/demand-slot、
迟滞、版本或 primary/reserve 语义。两个 seed-1 sequence 的 command CSV、
`d7-actual-execution-metrics-v2` 与 canonical D3 history 使用相同计划身份：

| Case | command/actual/history plan | History | D6 feedback churn |
|---|---|---:|---:|
| tuned 2v2 | `d3-plan-c3cc6d28c365/1` | 24 | 3 |
| M5N2 | `d3-plan-cfdd088a10e1/1` | 214 | 50 |

D6 对两条 history 的可用/不可用 case 为 `2/0`，validation reasons 为空；actual
execution required/available/unavailable case 为 `2/2/0`。因此 D3 计划从 history
到 command 再到 actual metrics 的运行级 P0 可追溯链已关闭。M5N2 的 plan version、
成员和 owner churn 均为 0，但 feedback churn 50 仍是单 seed P1 标定信号，不是
P1 稳定性通过。物理结果为 pair `2/3`、target `2/2`、coalition `0/1`；T001 第二
primary 最近约 11.02 m，未进入 5 m。目标级 `2/2` 不能写成联盟完成。第二 primary
物理闭环和同配置多 seed 复验继续保持 P1。

## 2026-07-15 M5N2 20-Case 计划历史复核

main 在 M5N2 baseline 与 `candidate_soft_prediction_trend_coast` 各完成 10 seeds 后
终止了后续多 seed suite。D3 对这 20 个 case 的
`main_episode_bus/d3_plan_history.json` 做了只读复核：共 `3725` 个 planning tick，
其中 baseline `1869`、candidate `1856`；20/20 个文件的 `record_count` 与实际数组长度
一致，全部记录均为 `d3_plan_history_record_v1`、`assignment_plan_v2`。

每个 tick 都报告动态规模 `resource_count=5`、`target_count=2`，并保持 T001 的
`2 primary + 1 standby reserve` 和 T002 的 `1 primary`，总计 4 个 assignment。
20 个 case 各自只出现一个 `plan_id/version=1`；逐 tick 计划身份、owner 和实际成员
roster 转换均为 0，stale reject 与 rollback 也均为 0。`3555` 条
`membership_change_records` 是候选换员评估，不是实际 churn：其中 `3524` 条由成员
迟滞保持，`31` 条虽通过成员收益/驻留条件，但又由全局迟滞保持，最终未改变 current
plan。由此，canonical history 的写盘和 D3 计划/成员/churn 可用性在本批已闭合，
不再是 `unavailable`。

跨 case 不能写死“第二 primary”的资源编号。19 个 case 的 T001 primary 为
`INT-02/INT-03`，1 个 candidate seed 的 primary 为 `INT-01/INT-02`；D3 文档只按
`target_id + member_role + current plan identity` 统计。系统物理结果为 pair
`12/60`、canonical target `12/40`、coalition `0/20`，第二 primary `0/20` 进入 5 m，
20 个第二 primary 的 `stop_reason` 均为 `collision_stop`。这些结果保留为跨模块 P1：
D3 history 未记录碰撞对象，不能把物理失败归因于分配器；candidate 的配对非退化
判据失败也不等于 D3 算法退化，因为两组的 D3 执行身份和成员均保持稳定。

术语必须分开：`canonical target success` 是 D6 对两个目标的标准目标级统计；
`cooperative target diagnosis` 专指 T001 两个 active primary 与 coalition 的诊断，
不能用前者替代联盟完成。TERM 生效前额外完成的 `png_ttc_2v2_seed001` 不纳入上述
M5N2 聚合；其余 tuned case 未执行，dropout case 数为 0，缺失结果保持
`unavailable`。

本次 D3 证据同步的验收门限是 20/20 history 可读、record count 无缺失、actual
plan/member/owner churn 可计算，且模块测试零失败；结果满足。物理验收门限仍为每个
active primary 进入 5 m，第二 primary 与 coalition 未满足。D3 全量测试为
`157 passed, 1 skipped`，唯一 skip 是 optional OR-Tools installed-only case。

## Scalable 3D Rule And Learning-Assist Path (2026-07-20)

`PlannerConfig.scalable_3d(...)` is an opt-in profile around the existing rule
planner. `TargetTrack` and `ResourceState` accept NED position/velocity,
position covariance, region identifiers, and resource speed/range fields. The
rule cost adds analytic constant-speed 3D intercept time/range, normalized NED
covariance, and region cost. Unreachable edges, exhausted assignment capacity,
declared friendly conflicts, and incompatible regions are hard-masked.

Candidate generation first applies the region/reachability gates and then
retains a deterministic per-target top-k. The effective k is never below the
target's `required_resource_count`, and still-feasible members of the current
published plan are retained so sparsification alone does not force churn. The
solver input remains a deterministic Hungarian/demand-slot matrix with pruned
edges set to the infeasible penalty. For sparse profiles, plan evidence stores
candidate-edge records and reject counts rather than a dense 40,000-edge audit
bundle.

The optional learning interface is `LearningCostAssistant`. It runs one shared
PyTorch MLP over a variable-length candidate-edge feature batch and supports
`shadow` and `assist` modes. Assist mode uses exactly:

```text
C_final = C_rule + alpha * tanh(delta_C)
```

The policy cannot emit assignments or a dense target-by-resource action vector;
Hungarian/demand-slot solving, all-or-none coalition admission, capacity, friend
conflict, and version checks remain deterministic. A stale version is rejected
by `AssignmentPlanner`; standalone residual inference masks a version mismatch.
Model timeout, low confidence, OOD features, invalid output, or model exception
returns the unchanged `C_rule`. `behavior_clone_warmup(...)` is a minimal native
PyTorch supervised warm-up interface, not PPO training or acceptance evidence.

Deterministic validation on 2026-07-20 added 13 tests: 3-target/5-resource,
5-target/3-resource, one 200v200 fixture, sparse high-threat M-to-N, 3D cost,
mask/fallback/version cases, and one 32-edge synthetic behavior-cloning batch.
The 200v200 sample assigned 200/200 with 800 candidate edges (2% density) and
800 shared-edge policy actions; one local invocation took 0.621 s. This is a
single functional timing sample, not a real-time benchmark. The full D3 suite
is `170 passed, 1 skipped`, with zero failures as the acceptance threshold and
only the optional OR-Tools installed-only test skipped.

Remaining learning gaps are real D2/D3 trajectory datasets, train/validation
splits, persisted checkpoints, calibrated OOD/confidence thresholds, bounded
preemptive inference, shadow multi-seed non-degradation, and any large-scale PPO
study. `gymnasium` and `stable_baselines3` are absent and are not required by
this implementation. The analytic reachability baseline does not replace D7
dynamics, obstacle/path planning, regional quota policy, or AirSim physical
validation.

## 2026-07-20 200×200 成本构造与区域计划合同

### 稀疏成本构造

此前的 top-k 只压缩了求解和证据输出，规则成本仍先对全部 `N×M` 资源目标对执行
Python 几何计算，并为随后被剪枝的边构造完整字典。同区域 200 resource × 200 target、
每目标 32 条候选边时，实际仍执行 40,000 次边成本和 80,000 次截获量计算。

`PlannerConfig.scalable_3d()` 现默认启用 `enable_vectorized_sparse_costs`。核心三维
位置、速度、协方差、资源状态、区域许可、截获时间和距离由 NumPy 批量计算；规则排序
仍按“成本、resource_id”确定性排序。最终只为 6,400 条候选边生成完整 breakdown，
剪枝边共享拒绝模板。带资源目标字典覆盖或复杂时间窗的输入继续走旧参考路径，保持既有
约束优先级和解释字段。学习残差、有界修正、规则回退和硬门控没有改变。

SciPy `linear_sum_assignment` 仍是默认确定性求解器。候选图不连通时，求解器按二部图
连通分量构造局部矩阵并分别运行 Hungarian；无候选目标直接按未分配成本处理。该分解
不改变全局最优值，因为分量之间没有共享资源边。

2026-07-20 同一进程、同一 200×200 输入、top-32、各重复 5 次的 D3 独立基准如下。
结果保存在 `results/scalable_3d_assignment_benchmark_20260720.json`。

| 路径 | 中位耗时 | 完整边 | 候选边 | Python 全边成本调用 | 分配数 |
|---|---:|---:|---:|---:|---:|
| 旧参考路径 | 1904.261 ms | 40,000 | 6,400 | 40,000 | 200 |
| 向量化稀疏路径 | 85.367 ms | 40,000 | 6,400 | 0 | 200 |

中位加速为 22.307 倍。20×23 逐边语义对照中，矩阵、候选掩码和拒绝原因一致，候选
breakdown 的浮点差在 `1e-11` 容差内。该数据是 D3 独立确定性基准，不代表 D1-D7
全栈实时性能，也不替代多 seed 或 AirSim 物理验收。

### 区域计划

新增 `RegionalAuthorityInput`、`RegionalAuthorityGrant` 和
`RegionalCoalitionCommitEvidence`。D3 不判断是否降级，只接受 D4 已裁决的区域
owner 和成员结果，生成一个普通、可版本校验的 `AssignmentPlan`。同一计划可携带
多个 secondary owner，也可携带 fully distributed peer owner；每条 assignment
记录 region、owner、epoch、lease 和 commit 状态。

发布前必须满足：D4 输入引用当前 `plan_id/version`；区域 epoch 不回退；lease 在
发布时间后有效；每个资源只属于一个目标；成员边仍在 D3 规则候选中；M-to-N 需求
完整。`k=1` 由 D4 已裁决的区域 ownership、epoch、lease、execution_allowed 和唯一
资源成员授权，不要求原子联盟提交；若 D4 同时提供 summary，只接受
`commit_required=False`、`single_member_authorized`、非 atomic、成员授权完整且租约
有效的证据。`k>1` 继续强制 committed、atomic committed、完整 ACK、成员一致且租约
有效。任一条件失败均抛出带 reason 的 `RegionalPlanAuthorityError`，不发布可执行
计划。计划执行变化继续严格递增版本，旧 previous plan 仍由 `StalePlanError` 拒绝。

本轮 D3 全量验收为 `193 passed, 1 skipped`，唯一 skip 是 optional OR-Tools。
区域合同已完成模块级测试，main 尚未把 D4 `RegionalFailoverDecision` 转换并接入
`plan_regional_authority()`；因此多 owner secondary 和 distributed 运行时闭环仍是
待集成，不得写成完整系统已通过。

## 2026-07-20 故障代际 Fence

`AssignmentPlanner.advance_authority_generation(...)` 用于中心或二级节点故障后、D4
重新裁决区域 owner 之前推进 D3 计划代际。调用方必须传入当前已发布计划、单调时间、
精确 `expected_previous_version` 和非空 `fence_reason`。接口复制原计划的 assignment
成员、coalition identity/version、目标身份、owner 和授权状态，只生成新的
`plan_id`、严格递增 `version`，并由 D3 正常发布登记。assignment 中仅同步新的计划
上下文版本；资源-目标绑定不变。

Fence metadata 使用 `d3_fault_authority_generation_fence_v1`，记录原因、来源计划、
fence generation、非重分配和非执行授权。`fault_authority_fence_requires_d4_gate=True`
表示该计划不能自行授权 D7；main/D7 仍必须执行 D4 的 hold/continue 结果。普通相同
执行签名的新身份继续被 `publish_plan()` 拒绝，只有来源、版本和安全标记完整的 fence
可推进。错误 expected version、旧来源、重复 fence 版本和篡改 coalition 均 fail
closed。

2026-07-20 新增 5 个专项测试。D3 全量共 199 项，结果为
`198 passed, 1 skipped`；唯一 skip 是 optional OR-Tools。该结果关闭 D3-owned fence
接口缺口；main 尚需在 50v50 中心故障路径调用该接口，再把新 generation 交给 D4
区域裁决。

## 2026-07-20 可复现 BC/PPO/Shadow 研究管线

本模块现提供完整但默认关闭的学习研究路径。`AssignmentPlanner` 默认仍不构造或加载
模型；规则 Hungarian/`hungarian_demand_slots`、候选 mask、联盟准入、迟滞、计划版本
和 stale 拒绝继续拥有最终决定权。模型只处理当前稀疏候选边，不输出 assignment、
target/resource index、联盟成员、owner、plan version 或 D7 控制量。

### 数据与模型合同

- `learning_data.py` 当前合同为 `d3_learning_dataset_v2`，split policy 为
  `d3_numeric_seed_atomic_split_v2`。采集帧显式标记 `unassigned`；finalize 取得完整唯一
  数值 seed catalog 后，按 seed 数量确定 train/validation/test，scenario version、规模和
  episode 不参与 seed 身份。同一数值 seed 的所有 scenario/scale/episode/frame 必须原子
  进入一个 split，三个数值 seed 集合两两不交。少于 3 个唯一 seed 或 test 少于声明的
  unseen 数时不写 manifest；正式默认声明 20，synthetic smoke 必须显式降为 1。
- v2 manifest 固化唯一 seed 数、逐 split seed/episode/frame 数、split 参数、split hash 和
  canonical `frames.jsonl` SHA256。loader 重算分配与统计并校验完整文件 SHA；v1 dataset、
  v1 scenario/seed split、冲突预分配和任何篡改均明确拒绝，不做静默迁移。
- `write_learning_dataset()` 用临时 SQLite 只保存排序键和 payload 偏移，以磁盘 JSONL
  sidecar 保存单次 canonical 编码结果，再按稳定键流式输出；
  `iter_learning_frame_records()` 可逐行消费 staged JSONL。每帧仍只保存匿名 ordinal
  target/resource 摘要、`E x 12` 候选边特征、mask、规则成本/选边、版本、反馈/迟滞和
  reward 分量，不保存原始 ID、truth actor 或上游 metadata。
- `learning_bundle.py` 保留 `d3_learning_model_bundle_v2` 兼容加载，并对正式开发模型使用
  `d3_learning_model_bundle_v3`。v3 在 feature/policy、split hash、归一化、guardrail、
  dataset/split schema 之外增加 provenance 与 admission。v1 bundle 稳定回退为
  `model_bundle_schema_unsupported`；缺失、损坏、SHA、特征或合同不匹配均返回逐元素相同
  的 `C_rule`，权重只用 `torch.load(..., weights_only=True)`。
- shadow 可加载未晋级 bundle。promotion parser 仍校验 recommended、至少 20 个未见
  test seed、安全/成本非退化和零 fallback，但该清单只用于比较诊断。production assist
  还要求尚未实现的 D3 evidence assembler；手工填写完整正向布尔和占位 SHA 仍返回
  `bundle_assist_evidence_assembler_unavailable`。

### BC、PPO 与 paired shadow

`SharedEdgeActorCriticPolicy` 共享同一 edge encoder，支持任意当前候选数 `E`。每边
actor 输出 bounded residual；value 使用 masked mean-pooled frame context；hold/replan
是按 `advice_allowed` 低频开放的建议。BC 按 frame mini-batch 跨多个 episode 学习规则
选边、规则 residual teacher 和 hold/replan，并输出 train/validation loss 与完整 seed
指标。原生 PyTorch PPO 使用 clipped objective、GAE、value loss、entropy 和 gradient
clip；每次动作经确定性 mask 与 Hungarian demand-slot solver 后，才按规则成本、高威胁
覆盖、未满足槽、churn、过期和安全拒绝重算离线 reward。

`shadow_evaluation.py` 在相同 scenario/seed/frame 上复制同一规则矩阵，分别求解 rule
和 bounded proposal，报告 assignment cost、高威胁 unmet、churn、duplicate/hard
violation、推理 P50/P95 和 fallback reason。unseen 与 whole-seed 指标按全局数值 seed
跨 scenario 聚合，输入必须先通过完整三分合同；shadow 从不改写规则矩阵，也不发布计划。

四个 CLI 子命令为：

```bash
PYTHONPATH=research_modules/d3_assignment_planner/src python3 -m d3_assignment_planner.learning_cli generate-data --output /tmp/d3_data
PYTHONPATH=research_modules/d3_assignment_planner/src python3 -m d3_assignment_planner.learning_cli train-bc --dataset /tmp/d3_data --bundle /tmp/d3_bc_bundle
PYTHONPATH=research_modules/d3_assignment_planner/src python3 -m d3_assignment_planner.learning_cli train-ppo --dataset /tmp/d3_data --input-bundle /tmp/d3_bc_bundle --bundle /tmp/d3_ppo_bundle
PYTHONPATH=research_modules/d3_assignment_planner/src python3 -m d3_assignment_planner.learning_cli shadow-eval --dataset /tmp/d3_data --bundle /tmp/d3_ppo_bundle --output /tmp/d3_shadow.json
```

### 当前证据边界

此前 30-seed synthetic smoke 的 `23/1/6` split、loss 和 shadow 时延来自 v1
scenario/seed policy，只保留为历史开发记录；v2 loader 与 bundle loader 均拒绝把该产物
解释为当前合同。该段记录的是正式训练前的软件合同阶段；最新正式 loss、成本和时延见
本文末尾的“正式数据行为克隆开发模型”。

软件合同回归覆盖同一数值 seed 在 2v2/5v5 风格 scenario、多个规模和 episode 中复用、
输入逆序确定性、三 split 零交集、唯一 seed/unseen 数不足、split/frame/hash 篡改、v1
dataset/bundle 拒绝、训练和 shadow 的全局 seed 计数。D3 全量收集 244 项，结果为
`243 passed, 1 skipped`；唯一 skip 是 optional OR-Tools installed-only case。

200v200 dense fixture 单帧含 40,000 candidate edge，canonical JSON 约 5,854,691 bytes；
NumPy payload 加 edge tuple 浅层约 5,161,640 bytes。当前 scalable main finalize 已把
`iter_learning_frame_records(staging_path)` 直接传给 writer，不再在调用侧执行
`read_text().splitlines()` 和完整 tuple 构造。正式 900-episode 数据容量、故障/密集场景
最坏值和长期磁盘预算仍需由 main 在 clean tree 上验收。

本批没有提交正式权重，没有真实 D2/D3 轨迹训练，没有至少 20 个未见真实/高保真 seed，
也没有 CPU/GPU deadline 分布、AirSim 物理收益或可抢占 timeout 证据。当前结论仅为
管线实现和合成 smoke；规则 Hungarian 继续是唯一默认路径。

本次结果是软件数据合同证据，不是模型性能、AirSim 物理收益或 assist promotion 证据。

## 2026-07-20 单帧只读规划证据

`AssignmentPlanner.latest_planning_evidence` 现返回
`PlanningFrameEvidence`（schema `d3_planning_frame_evidence_v1`）。planner 只保留最近
一次规划尝试：每次 `plan()`、`plan_incremental()` 或
`plan_regional_authority()` 开始时先替换旧帧，成功后保存与该次输入一致的 rule
`CostMatrixResult`、实际送入 solver 的 effective `CostMatrixResult`、计划
`plan_id/version`、规划时间、前序版本，以及构造 `LearningFrameRecord` 所需的
tracks/resources/plan 安全副本。新 episode 仍按既有合同创建新 planner；新实例初始
状态为 `available=False, reason="no_planning_frame"`。

证据明确区分四种 learning 状态：`rule_only`、`shadow_proposal`、
`assist_effective` 和 `rule_fallback`。shadow 的 proposal 是独立只读矩阵，effective
矩阵仍逐元素等于 rule；assist 只把有界 residual 后矩阵标为 effective；timeout、低
置信、OOD、bundle/version 等 fallback 必须保持 effective 与 rule 逐元素相同并给出
`fallback_reason`。solver 名称单独记录，因此 SciPy Hungarian 与 `fallback_dp` 也可
审计，默认 `learning_assistant=None` 和 Hungarian 行为未改变。

该接口只存在于 planner 本地对象，不写入 `AssignmentPlan.metadata`，不定义线上 DTO，
也不上 D4/D7 总线。快照把输入 ID 重映射为 `target_0000/resource_0000`，剥离上游
metadata、node/actor/object/truth alias；NumPy 数据来自独立不可写 buffer，嵌套 mapping
也只读。held、unchanged、forced-replan ack 和有效 regional authority 均保存当前输入
帧；stale/区域拒绝、无矩阵 authority fence、证据不一致或无匹配成本帧的外部 publish
只返回 `available=False` 和明确 reason，不回退到上一帧。

main 可直接调用：

```python
record = build_latest_learning_frame_record(
    planner,
    scenario_version=scenario_version,
    seed=seed,
    episode=episode,
    frame_index=frame_index,
)
```

helper 使用证据中的 timestamp 和 rule matrix，继续输出匿名 ordinal token；调用方不再
调用私有 `_build_search_matrix()`，也不重复构造可能与真实规划不一致的成本矩阵。
2026-07-20 新增 11 个专项测试，覆盖首帧、held/unchanged/forced replan、shadow、
assist、learning/solver fallback、regional 成功与拒绝、失败清旧帧、外部修改隔离及
1x3、3x2、7x4 roster。D3 全量共收集 226 项，结果为
`225 passed, 1 skipped`，零失败达到门限；skip 仍是未安装 optional OR-Tools 的
installed-only case。main 尚未用真实 AirSim episode 导出整 seed 数据，因此这里只
关闭 D3-owned recorder 接口缺口，不构成真实数据、shadow non-degradation 或 assist
晋级证据。

## 2026-07-20 上一轮区域资源提示约束下一轮候选图

普通入口现支持可选关键字 `regional_planning_hint`。D3 自有且冻结的
`RegionalPlanningHint`、`RegionalPlanningConstraint` 和
`RegionalTransferAllowance` 使用 schema `d3_regional_planning_hint_v1`；调用方也可
传入中性 mapping，由严格 `from_mapping()` 解析。该解析不导入 D4 类型，拒绝未知字段
以及 truth/actor/object/target/resource 身份字段。提示携带 advisory identity/version、
created/expiry、精确 source plan、逐区域 owner/epoch/lease、projected、quota delta、
reserve ratio、hold/request-replan 和邻区 transfer allowance。

提示只在显式提供时进入普通规划。D3 要求 source `plan_id/version` 与
`previous_plan` 完全一致，当前 timestamp 同时落在提示与全部区域 lease 内，当前 target/
resource 区域集合可解释，projected quota 总和守恒且与 transfer 净额一致。每个源区按
当前资源数、上一计划全部 assignment/coalition 成员和 post-quota reserve floor 计算
可转移容量；不满足时不把 transfer 当成 0，而是写入明确 fallback reason 后重新执行
原规则路径。

合法提示在规则矩阵和 switch penalty 之后、learning residual 之前约束候选 mask。同区
边保持原规则门控；跨区只开放给该 route 固定大小且互斥的未承诺资源池，因此普通
Hungarian 的资源唯一性直接形成 transfer count 上限。M-to-N role/wave slot 继续复制同一
mask，D5 hard edge、能力/可达性、学习有界代价、迟滞和版本发布均不被绕过。最终
`AssignmentPlan.metadata` 记录 available/considered/applied/rejected、advisory/source
identity、fallback reason、逐 route allowed/actual count 和实际跨区资源总数，供 D6
审计。无提示时规则矩阵、learning 调用和 Hungarian 路径不变。

2026-07-20 新增 14 个确定性 pytest case，覆盖严格解析、无提示等价、1-to-1 实际跨区
选边、8 类非法/过时回退、commit/reserve 保护、M-to-N 两资源 transfer 上限，以及 D5
hard edge 与 learning assist 共存。seed 不适用于该模块 fixture；接受门限为全量零失败。
D3 共收集 240 项，结果为 `239 passed, 1 skipped`，skip 是既有 optional OR-Tools
installed-only case。本批没有运行 AirSim、正式多 seed 性能或物理拦截；main 仍需把
D4 `RegionResourceRecommendation` 显式映射为 D3 DTO，并在 reset-separated episode
中验证时间基准、owner/epoch/lease 和 D6 指标。

## 2026-07-20 Learning 安全复核补正

本轮对可选 BC/PPO/shadow/assist 路径做 fail-closed 复核，不改变默认 Hungarian、
`hungarian_demand_slots`、联盟准入、计划版本或 D7 授权链：

- BC 训练入口只接受 `train`/`validation`，PPO 只接受 `train`；任一训练 API 收到
  `test` frame 都拒绝。CLI 对完整 dataset 的读取只用于内容、哈希和三分合同校验，
  test frame 不进入训练 batch、normalization 或训练期 whole-seed metric；test 仅由显式
  `shadow-eval --split test` 入口消费。
- `LearningFrameRecord.from_dict()` 对 v2 使用完整字段 allow-list；普通扩展必须升级
  schema。解析前递归拒绝 truth/actor/identity、实体 ID、UUID 和 vehicle-name 类字段，
  同时保留已知匿名 ordinal、数值/布尔字段及语义性 hard-reject reason 的兼容策略。
- `candidate_mask` 是候选提示，不是授权。候选索引、assistant 返回 mask 和 solver 消费
  mask 都始终与 `reject_reasons is None` 求交，shape 不一致失败关闭，不能重开 D5、
  可达性、容量或友方冲突 hard edge。
- bundle v2 同时绑定 split hash、canonical `frames.jsonl` SHA256 和
  `state_dict.pt` SHA256。assist 不允许关闭 promotion gate；promotion evidence 必须是
  `d3_shadow_promotion_evidence_v1`、正式 `test` split、`evidence_eligible=true`、
  `paired_rule_residual_shadow`、`rule_cost_matrix_v1`，且三项摘要与 bundle 完全一致。
  布尔和计数字段采用严格类型校验，错配或伪装均回退 `C_rule`。
- residual proposal 仍按 `C_final=C_rule+alpha*tanh(delta_C)` 产生候选方案，但 rule 与
  proposal assignment 的非退化指标都按同一个最终 `C_rule + unassigned_costs` 基准
  重新评分，禁止比较不同矩阵各自的 solver objective。学习输出始终只是受约束提案，
  不能直接授权 assignment、coalition 或 D7 执行。

2026-07-20 全量收集 252 项，结果为 `251 passed, 1 skipped`，接受门限为零失败；唯一
skip 是未安装 optional OR-Tools 的 installed-only benchmark。新增负例覆盖 test-seed
训练拒绝、训练指标隔离、递归 identity/未知字段拒绝、hard-reject mask 求交、frame SHA/
promotion 证据错配、validation/非 eligible/bypass 拒绝和共同规则代价重评分。本轮未训练
或提交正式权重，未运行 AirSim，也没有至少 20 个未见真实/高保真 test seed、正式
promotion、模型收益或物理闭环结论。

## 2026-07-20 200×200 学习帧导出性能复核

本轮只优化 D3 学习帧构造、canonical JSONL 读写和数据集 finalization，不改变
Hungarian、学习残差、硬拒绝掩码、`plan_version`、truth isolation、dataset schema 或
任何输出字段。候选特征构造按目标缓存一次 `effective_demand`；学习帧的硬拒绝计数复用
同一 action-mask 扫描结果。JSONL identity 检查改为迭代遍历容器，避免对密集数值数组
中的每个标量递归调用。

finalization 仍先验证每个 `LearningFrameRecord` 的当前数组、掩码、匿名实体和身份字段，
随后只做一次 canonical 编码。临时 SQLite 保存排序键、payload offset 和 size；payload
写入临时 JSONL。最终排序阶段只读取对应字节并替换唯一受控的 `split=unassigned`
占位符，不再执行第二轮 `json.loads -> from_dict -> replace -> to_dict -> json.dumps`。
正序、逆序输入和旧重编码语义输出逐字节相同，frame SHA256 与 manifest 规则不变。

同机开发微基准使用 200 targets、200 resources、top-32、每帧 6,400 candidate edges、
6 帧。墙钟只作归因证据，不作为单元测试门限。

| 阶段 | 修改前 | 修改后 | 变化 |
|---|---:|---:|---:|
| 单帧 frame build 中位数 | 48.19 ms | 22.99 ms | 2.10× |
| 单帧 JSON decode + validate 中位数 | 95.92 ms | 56.09 ms | 1.71× |
| 6 帧 dataset finalize 中位数 | 910.20 ms | 243.65 ms | 3.74× |
| 匹配 cProfile/Tracemalloc 峰值 | 14,575,699 B | 12,725,690 B | -12.69% |

当前 top-32 帧约 2.20 MB；九场景 D3 正式帧证据总计约 27.86 MB，数据内容和存储量按
要求未压缩或删减。模块局部测得的六帧构造、首次编码、逐行读取和 finalization 合计约
0.87 s，不能把 main 记录的 D3/D4/D5 总耗时全部归因于 D3。

main 随后在干净工作树上复跑 nominal 200v200、seed 930/931/932、每个 episode 2 s。
优化后产物由 commit `4052d9411363c39d52100c0e3a4f60ee88443cab` 生成，清单记录
`repository_dirty=false`。总生成耗时由 467.8007 s 降至 262.2866 s，artifact staging
由 225.9243 s 降至 126.4682 s，总 finalization 由 116.5624 s 降至 7.7377 s；episode
run 为 125.2205 s 与 127.9871 s，基本未变。这里的总 finalization 同时包含 D3、D4、D5，
不能作为 D3 单模块耗时。

分项记录给出的 D3 stage 分别为 0.0917 s、0.1129 s、0.0999 s。D3 数据集共 6 帧，
train/validation/test 各 2 帧，正常最终化，在线真值使用为 0。该证据关闭 D3-owned
重复编码和最终化热点及其跨模块归因问题，但不是正式 900-episode 生成、模型训练、
至少 20 个未见 seed 评估或 AirSim 结果。

可复现命令：

```bash
python3 research_modules/d3_assignment_planner/simulations/run_learning_export_profile.py \
  --count 200 --max-candidate-edges 32 --frame-count 6 --repeat 5
```

结果文件为 `results/scalable_3d_learning_export_profile_20260720.json` 和配对比较 JSON。
D3 全量回归收集 255 项，结果 `254 passed, 1 skipped`；唯一 skip 是 optional OR-Tools。
剩余 CPU 热点是标准库 JSON 对 NumPy 数组执行 `tolist()` 和 canonical `json.dumps()`。
继续减少该部分需要引入新编码依赖或改变持久化格式，因此不在本次无 schema 变化任务中
处理。

## 2026-07-20 正式数据行为克隆开发模型

正式 D3 数据位于三维规模化仿真学习数据目录，只读审计通过。清单包含 900 episode、
1604 帧和 100 个数值 seed，train/validation/internal-test 为 962/320/322 帧，对应
60/20/20 个 seed。canonical frame SHA256 为
`6761d35d6b48639a5eb4f3306f7b3f12ca72352a1028296a0c39a4b90fdb59a2`，split hash 为
`679a9051e8637fad38d935eb685f09dd8abc8d43043a28264dab64b077ac70a2`。外部保留 seed
1000-1019 与当前数据交集为空，也未在本轮评估中消费。

训练使用固定 seed `20260720`、12 epoch、隐藏层 64、Adam 学习率 0.001、8 帧小批次和
正类权重上限 16。正类加权只处理规则已选边约 3.2% 的类别不平衡；学习输出仍是
`C_final=C_rule+alpha*tanh(delta_C)`，`alpha=0.25`。不可达边、硬拒绝、需求槽、容量、
版本、迟滞和 Hungarian 求解不进入学习动作空间。训练损失由 1.083713 降至 0.468781，
验证损失为 0.469243。内部 test 的边排序一致性为 0.8031，计划完全一致率为 0.6770，
平均规则成本差为 +0.022345，相对差约 +0.0091%；需求满足率与 rule-only 同为 0.975689，
重复分配和硬门控违规均为 0，平均重分配 churn 均为 70.1149。

内部 test 模型推理 P50/P95/P99 为 0.506/2.554/2.809 ms。按 5/20/50/100/200 名义规模，
推理 P95 分别为 0.247/0.433/0.860/1.434/2.793 ms。当前 OOD 规则按“单帧任一候选边任一
特征超过 6 个标准差”判定，内部 test 有 163/322 帧回退规则路径。该现象和轻微成本退化
说明模型不能晋级 assist，后续需在外部保留 seed 上重新标定 OOD、confidence 和 deadline。

新 bundle schema 为 `d3_learning_model_bundle_v3`，增加训练日期、数据 manifest SHA、
训练源码 SHA、Git 基线提交、工作树状态和显式 admission。提交 `39b097e...` 是正式数据
生成与训练基线；训练时存在 D3 模块改动，精确源码由 training-source SHA256 绑定。当前
状态固定为 `development/shadow-only`；即使
有人写入 recommended promotion，loader 仍返回 `bundle_shadow_only`。权重 SHA256 为
`e3da9fd5b54451da83358405b6051991e0c78bcf9f538b350d459b05faf8e0b2`。权重和 bundle 位于
ignored `outputs/formal_bc_development_20260720/bundle`，不进入普通 Git 提交；tracked
`results/formal_bc_development_20260720` 只保留审计、配置、命令、指标报告和定位说明。
当前环境没有 Git LFS，长期权重需由 main 转存到 Git LFS 可用环境或独立制品存储。

复现入口为：

```bash
PYTHONPATH=research_modules/d3_assignment_planner/src python3 \
  research_modules/d3_assignment_planner/simulations/run_formal_bc_development.py \
  --dataset research_modules/scalable_3d_simulation/outputs/learning_generation_v1_multibatchfix/learning_dataset/d3_assignment \
  --output research_modules/d3_assignment_planner/results/formal_bc_development_20260720 \
  --bundle-output research_modules/d3_assignment_planner/outputs/formal_bc_development_20260720/bundle \
  --repository-git-commit 39b097e72487567ac915c2297eaa27eed49ef76b
```

本轮没有启动 PPO，没有更改 AssignmentPlan 版本、`global_track_id` 或 D7 binding。内部
test 是开发集内的独立切分，不是最终 20 个保留 seed 准入。main 下一步必须使用同一冻结
权重运行 seed 1000-1019，并由 D6 独立汇总安全非退化、成本、需求满足、抖动、回退和时延。
新增正式审计、v3 bundle、加权 BC 与开发评估测试后，D3 全量收集 258 项，结果为
`257 passed, 1 skipped`；唯一 skip 仍是 optional OR-Tools installed-only case。

## 2026-07-21 共享 Seed 切分注册表绑定

D3 增加只读共享切分验证边界，用于 C1 跨模块联合训练前的 seed 对齐。默认
`load_learning_dataset(path)` 行为保持不变；只有同时传入 `shared_seed_registry_path` 和
`training_seed_registry_path` 时，loader 才验证 main-owned detached registry。只传一个
路径、schema/policy 不匹配、registry content/assignment SHA 不匹配、源 registry 文件
SHA 不匹配、seed 缺失或增加、保留 seed 混入、同一数值 seed 跨 split，均失败关闭。

正式 900-episode 数据只读验证结果如下：

| 项目 | 结果 |
|---|---|
| 训练 seed | 100，train/validation/internal-test 为 60/20/20 |
| 保留 seed | 1000-1019，与数据交集为 0 |
| registry file SHA256 | `68608d29d1f733beea87f1faf06464fededb68a9c2972c51c10cd4c2160f032f` |
| registry content SHA256 | `29eb6895c4aa570b068f15141cbbbfede3041519117852d1ad48e848a25af146` |
| assignment SHA256 | `31c6a3fc265d088d9958f44d579d8098e2aeab06b0daa60c68452ae4c6d46ab5` |
| source registry SHA256 | `2ab928a476a4430b99326f245222f058bc5be5025158134ba89b01b3dec7815f` |
| 原文件变化 | dataset manifest、frames、共享 registry、源 registry 前后哈希相同 |

通用学习命令和正式行为克隆入口均接受以下参数：

```bash
--shared-seed-registry \
  research_modules/scalable_3d_simulation/outputs/learning_generation_v1_multibatchfix/shared_seed_split_registry_v1/registry.json \
--training-seed-registry \
  research_modules/scalable_3d_simulation/outputs/learning_generation_v1_multibatchfix/training_seed_registry.json
```

启用后，新 bundle 的 `training_results` 和正式训练报告记录
`d3_shared_seed_split_binding_v1`；正式入口另写只读 provenance sidecar。旧 v2/v3 bundle
仍可走非联合开发路径加载，现有正式 BC bundle 和原数据没有原地修改。本项只消除 D3
切分歧义，不构成 assist 晋级证据；状态仍为 `development/shadow-only`，PPO 未启动。
D3 全量回归为 `269 passed, 1 skipped`。

## 2026-07-21 正式分配数据全样本准入审计

新增 `assignment_full_sample_audit.py`，对正式 D3 分配数据执行只读、流式、失败关闭审计。
审计绑定数据清单、883 MiB 帧文件、训练 seed 注册表、共享切分注册表、生成摘要、episode
进度和批量导出摘要共 7 个源文件。所有源文件在扫描前后重新计算 SHA256；输出目录必须
位于正式数据根目录之外。审计逐帧调用 v2 严格解析器，并复核有限数值、候选边与动作
标签维度、动作索引、资源容量、目标需求槽、匿名 token、数值 seed 切分、帧顺序、时间
顺序和前序计划版本单调性。

2026-07-21 的正式结果为：900 个实际 episode、1604 个决策帧、3658815 条候选边、
3658815 条资源-目标动作标签和 117304 条规则选中动作。100 个规范数值 seed 按
60/20/20 切分；场景展开后的实际 episode 为 540/180/180，决策帧为 962/320/322，
不能把三组计数互相替代。43905780 个候选特征值全部有限；容量、需求槽、索引、切分、
前序版本、在线真值和非法 `global_track_id` 违规均为 0。生成进度记录 900/900 个有限
episode、0 个脏 episode、0 次在线真值使用，以及 194 个明确未导出帧原因；没有以前一
帧补数。正式源文件哈希未变化。

数据结构审计状态为 `complete`，总体准入状态为 `partial`。学习帧只有匿名 ordinal token
和 `previous_plan_version`，没有当前计划 owner、当前 plan version 或运行时 stale 拒绝
记录。`reward_components` 是规则代价、覆盖、未满足需求和抖动诊断，不是可归因的运行时
回报。真实 applied ACK、outcome、因果/反事实 reward 和同 seed 配对 shadow 均为
`unavailable`。因此没有训练或写入权重，PPO、assist 和在线权限保持关闭；默认路径继续
使用规则代价与需求槽匈牙利求解。

产物为 `results/assignment_full_sample_audit_20260721.json` 和
`reports/D3_ASSIGNMENT_FULL_SAMPLE_AUDIT_20260721.md`。JSON 文件 SHA256 为
`62a47df8058c0238498f2181229a5f6d45f6d958799eda354f03e25ea24b17fb`，去除
`content_sha256` 字段后的规范内容 SHA256 为
`954f3e96d563412644ec88d1b621e2a58c781af8af99de79b859d22079fc1867`。新增 10 个负例和
正常路径测试；D3 全量收集 280 项，结果为 `279 passed, 1 skipped`，唯一 skip 为可选
OR-Tools 安装检查。

## 2026-07-21 运行计划确认消费合同

D3 新增独立的 `runtime_plan_ack.py`，用于只读消费 main 发布的
`scalable3d-assignment-plan-runtime-ack-v1`。调用方必须同时提供确认载荷、D3 来源
计划的完整总线 envelope、可选 D7 来源命令 envelope 和内存中的预期
`AssignmentPlan`。验证器不导入 main 模块，也不调用规划器或发布计划。

验证链按以下顺序失败关闭：

1. 检查 ACK schema、字段白名单、有限时间和正整数来源序号。
2. 使用 UTF-8、键排序、紧凑分隔符和 `allow_nan=false` 复算 D3/D7 payload
   SHA-256，并与 ACK 中的来源摘要逐项核对。
3. 将 D3 来源计划与预期计划的 plan id/version/schema、目标和资源计数、未分配清单、
   solver、metadata 及全部 assignment 对齐。
4. 对每个资源精确核对 `global_track_id`、coalition id/version、member role 和区域
   owner 字段；重复、缺失、额外或重绑均返回稳定错误码。
5. 将 D7 命令与每条 binding ACK 对齐，再独立重算 fully-bound、control-applied 和
   held 统计。D7 不能借 ACK 改写 D3 的中心航迹身份。

`d3_learning_evidence` 缺字段时保持 unavailable。只有来源计划明确记录
`mode=assist`、`applied=true`、`bundle_loaded=true`，并且上述来源、计划和绑定
检查全部通过时，结果才标记 `runtime_learning_applied_ack_available=true`。
`shadow`、规则教师 `reward_components` 和单纯的运行时计划接受均不满足该条件。
运行 ACK 自报物理结果或 reward 会被拒绝；这两类证据只能由后续 D6 独立 sidecar 提供。

2026-07-21 增加自动化真实 main 集成回归：当前三维集成栈执行 3v3、seed 7、1.2 秒，
总线产生 2 条计划 ACK，公开 D3 consumer 验证最后一条 ACK。最终计划 3 条 binding
全部进入 D7，control-applied 为 3、held 为 0，在线真值使用为 0。该次计划没有学习
mode，验证结果因此保持学习 applied ACK unavailable；物理 outcome 和 reward 也为
unavailable。consumer 源码不导入 main；只有 D3 测试导入 main 集成栈，以避免运行时
耦合和循环导入。

consumer 同时兼容项目现有顶层与 namespaced 两种合法 D3 包路径。兼容检查限定模块名、
类名、精确数据类字段集合和 AssignmentPlan schema，不接受任意鸭子类型。专项 24 项
测试和 D3 全量 304 项均完成，全量结果为 `303 passed, 1 skipped`，唯一 skip 仍是可选
OR-Tools。

该接口已经实现并经当前 producer smoke 验证，但冻结的 900-episode 正式数据生成于
ACK producer 之前，仍没有 current owner/version、applied ACK、outcome 或 reward。
PPO、assist 和在线 authority 继续关闭，规则代价与需求槽 Hungarian 仍是默认执行路径。

## 2026-07-21 已采用计划窗口归因合同

D3 新增 `runtime_reward_evidence.py`，将现有运行计划 ACK 与 D6
`d6.runtime-plan-outcome-join.v1` 离线结果连接为
`d3_runtime_plan_window_reward_evidence_v1`。输入必须包含经过
`validate_assignment_plan_runtime_ack(...)` 验证的 ACK、ACK 总线序号、完整 D6 联接
结果及其外部规范载荷 SHA-256，并明确指定资源和 `global_track_id`。适配器不导入 D6 或
main，不读取文件路径中的真值身份，也不修改计划。

每个输出同时绑定：

- plan id/version、中心/二级 owner、authority epoch；
- D3 来源计划、D7 消费命令和 main ACK 的严格递增总线序号；
- D3/D7 来源载荷 SHA-256、ACK 证据 SHA-256、D6 结果 SHA-256 和 11 项来源文件摘要；
- 资源-航迹、联盟、角色、ACK occurrence、刷新类型、执行签名和不重叠时间窗。

证据层明确分成 command、ACK applied、observed outcome、paired、counterfactual 和
causal。D6 的五米接近事件和有界最优距离进展只保留为离线观测诊断，不能自动写成因果
奖励。现有 `OfflineRewardComponents` 六项仍是规则教师诊断；新合同逐项输出
availability/reason，当前不补零。缺 ACK、owner、来源序号/哈希、字段、窗口，或者出现
窗口重叠、刷新语义错误、版本回退、在线真值使用和自报 reward，均失败关闭。

2026-07-21 的专项测试为 `16 passed`。其中一项运行真实 main 三维质点 3v3、seed 41、
1.2 秒，并消费 main 自动生成的 D6 结果；选定 binding 的命令、采用和结果窗口连接成功，
正式 reward 仍为 unavailable。2026-07-22 按当前调度重放时，总线包含两条来源完整的 ACK：
首条 ACK 有 3 个非保持 binding，末条 ACK 因航迹年龄超过 D7 的 `0.75 s` 门限而以
`global_track_stale` 保持。consumer 先逐条验证 ACK 及其发布时计划快照，再按总线顺序选择
首个非保持 binding 接入 D6；保持 ACK 不作为 `ack_applied` 样本。D3 全量收集 320 项，结果为
`319 passed, 1 skipped`；唯一 skip 是未安装的可选 OR-Tools。Hungarian、
`C_final=C_rule+alpha*tanh(delta_C)`、确定性安全外壳、PPO/assist/authority 状态均未改变。
当前修复后的 2026-07-22 全量回归共 439 项，结果为 `438 passed, 1 skipped, 0 failed`。

仍缺同 seed 配对运行、反事实结果、因果归因、计划级六项运行结果和外部保留 seed 证据。
这些条件闭合前，`formal_d3_runtime_reward` 保持 unavailable，PPO 不启动，规则回退保持
启用。冻结的 900-episode 数据没有新 ACK，未被回填或修改。

## 2026-07-21 保留 Seed 配对干预合同

`paired_intervention.py` 已实现规则基线与学习代价修正的正式实验边界。规范固定使用
seed `1000-1019`，每个 seed 必须同时声明相互隔离的 `control` 和 `treatment` arm。
两条 arm 必须绑定同一场景版本、场景配置、初始世界状态、观测输入快照、D1/D2 lineage、
规则代价配置、D3 bundle、阈值、安全外壳和当前计划版本。control 固定走规则代价加
Hungarian；treatment 只在离线仿真 arm 内允许有界残差影响 Hungarian 输入，且必须声明
动作掩码、可达性、容量、版本、迟滞和安全门均已执行。

规范和 manifest 均可严格 JSON 往返，并通过
`validate-paired-intervention` 命令校验。缺 arm、seed 重复或缺失、任一配对哈希不一致、
bundle/阈值未冻结、stale plan、非有限值、在线真值字段、规则回退关闭和安全门缺失均
失败关闭。输出把 `paired_input_equivalence`、隔离 treatment 是否实际应用、运行时 ACK、
outcome、counterfactual 和 causal 分层；未连接 D6 sidecar 时后三项固定为 unavailable。

本轮只完成合同和失败关闭测试，没有运行正式 20-seed episode，也没有产生性能、收益、
反事实或因果结论。`PPO=false`、`online_assist=false`、`online_authority=false`、
`rule_fallback=true` 保持不变，默认执行路径仍为规则代价与需求槽 Hungarian。2026-07-21
专项结果为 `36 passed`，D3 全量结果为 `355 passed, 1 skipped`；唯一 skip 为未安装的
可选 OR-Tools 检查。

## 2026-07-21 保留 Seed 隔离执行入口

D3 新增 `offline_intervention_execution.py`，把上一节的配对规范落实为可调用的离线执行
入口。main 只需提供完整 `PairedInterventionSpecification`、seed `1000-1019` 对应的
20 个 `PlanningFrameEvidence` 和冻结 bundle 目录。执行器在 D3 内部完成模型读取、规则
臂复放、学习臂复放、Hungarian 求解、迟滞处理、哈希计算和收据组装，不要求 main 复制
manifest、PyTorch 权重或残差模型的加载细节。

执行顺序如下：

1. 重新计算每个匿名规划帧的输入快照 SHA-256，并与 control/treatment 规范逐项核对。
2. 计算规则矩阵和硬安全动作掩码 SHA-256。两条 arm 使用同一矩阵、同一掩码、同一前序
   计划和同一时间戳。
3. 生产 `load_model_bundle(..., mode="shadow")` 先验证 manifest、权重文件、数据合同和
   state dict。离线执行器再核对 manifest 文件 SHA、policy version、development/
   shadow-only 准入、保留 seed 清单和全部权重有限性。
4. control 使用规则矩阵加 Hungarian。treatment 只在
   `offline_simulation_intervention_arm` 内使用
   `C_final=C_rule+alpha*tanh(delta_C)`；分布外输入、低置信度、超时、非有限权重、模型
   异常或 bundle 不一致均回退到同一规则矩阵。
5. 对 20 个 seed 生成一个真实配对评估报告，40 份
   `PairedInterventionExecutionReceipt` 共享该报告哈希，并直接形成
   `PairedInterventionManifest`。输出计划标记为离线、不可发布、无运行时授权。

生产加载器没有放宽。development bundle 直接请求 `mode="assist"` 仍返回
`bundle_shadow_only`；离线 treatment 不构成 PPO、在线 assist 或 authority。执行结果只
包含规则成本、需求缺口、抖动、硬约束、回退和推理时延等 D3 规划层配对指标。runtime
ACK、物理 outcome、counterfactual 和 causal 均明确为 unavailable，仍由 main/D6 后续
生成独立证据。

2026-07-21 的专项测试使用 20 个保留 seed 结构、20 个匿名规划帧和临时冻结 v3
development bundle，实际执行 40 个隔离 arm。7 项测试覆盖正常执行、manifest SHA、
policy version、分布外门控、deadline、非有限权重、输入快照不一致和 JSON 产物；全部
通过。D3 全量收集 363 项，结果为 `362 passed, 1 skipped`，唯一 skip 为未安装的可选
OR-Tools。该结果证明执行入口和失败关闭逻辑可用，尚不等于正式三维主流程已经运行 seed
`1000-1019`，也不形成模型非退化或在线晋级结论。

## 2026-07-21 保留 Seed 控制臂精确重放

main 的 nominal 5v5、2.2 秒保留-seed 源帧暴露了一个重放缺口：匿名化曾清空前序计划的
执行所有权元数据，也没有记录调用时的 `forced_replan`。离线 control planner 因此把
中心所有权误判为新的执行控制变化，绕过迟滞并产生不同 binding。严格
`control_plan_replay_mismatch` 正确阻断了这些帧。

`PlanningFrameEvidence` 现在保留精确重放所需的真值安全状态：计划所有权与激活字段、
人工授权、源/目标节点和链路、同窗口迟滞计数、联盟执行语义以及 `forced_replan`。节点、
资源、目标和联盟身份统一匿名化；仅存在于前序计划的目标或资源使用
`previous_target_*` / `previous_resource_*` 占位符。输入快照 SHA-256 已包含
`forced_replan`。离线执行器从匿名证据恢复 planner 的授权和链路配置，control 需同时
复现 binding、执行签名、版本、窗口、决策状态、changed 标志和 N/M 规模，否则仍以
`control_plan_replay_mismatch` 失败关闭。

专项测试扩展为 9 项。新增 20-seed 真实形态夹具覆盖 5v5 迟滞保持、4→5 目标的
`replan_ack_no_change`、5→4 生命周期移除和前序目标占位符；故意篡改 binding 的负例仍被
严格门拒绝。D3 全量收集 365 项，结果 `364 passed, 1 skipped`，唯一 skip 为可选
OR-Tools。

另以 main 当前源帧和冻结 development bundle 做了不写盘内存复验：20 个 seed、40 个 arm
全部完成，control 状态为 15 个 `unchanged`、3 个 `held_by_hysteresis` 和 2 个
`replan_ack_no_change`，逐 seed binding 与记录帧一致，bundle 正常读取。该复验没有生成
main 正式产物，也没有运行时确认、物理结果、反事实或因果证据。生产 assist 准入、PPO、
在线 authority 和规则回退边界均未改变。

## 2026-07-21 二元特征分布门修复

正式 nominal 5v5、2.2 秒、seed `1000-1019` 的首轮落盘证据中，20 个 treatment 均以
`out_of_distribution` 回退。复核显示 11 个连续特征的最大 z 分数不超过 `1.6229`；唯一
超出旧全局门限的是 `previous_binding=1`。该特征在训练集中的均值为 `0.013906895`、尺度
为 `0.116464332`，按对称高斯公式得到 `z=8.4669`，但其定义域是伯努利端点 `{0, 1}`。

`FeatureDistributionGuard` 现按显式特征语义检查：`previous_binding` 只接受有限的 0 或 1，
允许 `1e-6` 浮点容差，合法端点不参与连续特征 z 门。`0.5`、越界值和非有限值仍判定为
分布外；其余 11 个连续特征继续使用原 `ood_z_threshold=6.0`。bundle loader 显式绑定
manifest 的特征顺序，未修改 manifest、权重或 normalization。

新增 `d3_feature_distribution_assessment_v1` 诊断结果。学习元数据可记录触发特征、候选边
偏移、最大连续 z、对应特征和失败原因，不记录目标、资源或全局航迹身份。原 `is_ood()`
布尔接口保留，现有消费者可以继续使用。

使用原冻结 bundle 和当前源帧完成不写盘复验。20/20 treatment 均进入隔离模型推理，
applied=20、fallback=0；时延最小/均值/P50/P95/最大分别为
`0.238/0.340/0.268/0.692/0.899 ms`。规则与 treatment 的重复分配、硬约束违规和高威胁
未满足均为 0，规则矩阵保持不变。D3 全量收集 373 项，结果为
`372 passed, 1 skipped`；skip 仅为可选 OR-Tools。该证据不包含运行 ACK、物理结果、
反事实或因果结论，PPO、生产 assist、authority 继续关闭，规则回退继续启用。

## 2026-07-21 v2 正式保留 Seed 证据

D3 对 main 生成的 v2 正式目录进行了独立只读复核：
`reserved_seed_interventions_nominal_5v5_1000_1019_formal_7891296`。当前源提交为
`78912963b67fe86ee9a8d29186b18a9dd60c460c`，与 20 条 source lineage 一致；20 个源 episode
均为 clean、finite，在线 truth 使用计数为 0。`SHA256SUMS` 文件 SHA256 为
`821f15035e628d8db86f13c22d93f8e05142c5f00aae9118974a74bdc98b72bc`，manifest SHA256 为
`d6ef23b28add92e9a24a185ea72a7275e341bd796a2e11930c4d5f46b19a883c`。清单内 5 个文件全部
通过 `sha256sum -c`；D3 执行产物 SHA256 为
`e878cd97f2a0f1c84fbd68b5ee996d0dc6d4e550cce42eab53558a33a120270b`。

20 个 control 和 20 个 treatment inventory 完整。20/20 treatment 均在
`offline_simulation_intervention_arm` 内实际应用学习代价，fallback 为 0；control 与
treatment 的有效代价矩阵 SHA 在 20/20 配对中不同，证明模型改变了隔离求解输入。最终
资源目标 binding 的变化为 0/20。规则与 treatment 的规则评分均值均为
`17.0560260319065`，高威胁未满足、重复分配、硬约束违规和抖动总数均为 0。

从 20 帧重新计算的推理时延 P50/P95 为 `0.246385/0.310801 ms`，与产物汇总一致。该结果
只证明隔离学习路径已执行且本批最终分配未变化。runtime ACK、physical outcome、
counterfactual 和 causal 全部 unavailable；promotion 状态仍为 unavailable。PPO、线上
assist、authority 保持 false，规则回退保持 true，运行时发布仍被禁止。

## 2026-07-22 D6 Profile-Bound v2 可用性审计

D6 已在提交 `d4e8562` 中作为独立只读消费者完成 profile-bound v2 审计。正式目录为
`research_modules/d6_evaluation_metrics/outputs/reserved_seed_interventions_nominal_5v5_1000_1019_formal_7891296_d6_profile_bound_v2_audit_20260722/`；
`outcome_availability_sidecar.json` 状态为
`pass_offline_assignment_comparison_only`。sidecar 文件 SHA-256 为
`f3852251daf02ec87fe878e7fb80aad6f381d8c0756a5c956a32e737a3871c3b`，规范内容
SHA-256 为 `c02a345c46ddc642dea7fb6bfcfb24184e7dc2a9f35b754c90324d074b445d2d`。

D6 独立复核确认 20/20 isolated treatment applied、0 fallback、20/20 effective cost
matrix changed、0/20 final binding changed。rule 与 treatment 的同帧 assignment cost
mean 均为 `17.0560260319065`；high-threat unmet、duplicate、hard violation 和 churn
均为 0。因此 `same_frame_offline_assignment_comparison` 已标记为 available，D3 的分配层
可用性和独立消费缺口已关闭。

该 sidecar 不包含本正式 artifact set 的 runtime ACK 或干预后的物理状态窗口。
post-intervention physical outcome、paired physical effect/non-degradation、counterfactual、
causal 和 promotion 仍为 unavailable；`PPO=false`、`assist=false`、`authority=false`、
`rule_fallback=true` 保持不变。以上边界不把“最终 binding 未变化”解释为物理无退化或策略
有效。

## 2026-07-22 隔离计划消费合同

D3 新增 `isolated_plan_consumption.py`，供 main 的 control/treatment 克隆世界在开始后续
状态推进前，确认某个隔离 arm 已消费指定 `AssignmentPlan`。构造接口
`build_isolated_plan_consumption_evidence(...)` 绑定 experiment/version、pair/seed/arm、
source snapshot lineage、plan id/version/schema、计划规范载荷 SHA-256、消费周期和时刻、
assignment/binding 数量及 binding inventory SHA-256。计划摘要通过生产 runtime ACK 使用
的同一计划结构检查后计算，但输出使用独立 schema 和
`accepted_by_isolated_simulation_consumer` 状态码。

`IsolatedPlanConsumptionValidator.validate_and_record(...)` 只在完整校验后记账。同一计划
重复消费、低于已消费版本的旧计划、相同版本换 plan id、非单调周期/时刻、错 arm、错
source snapshot、错 receipt、错 payload SHA 或不完整 binding 均失败关闭。证据固定声明
`production_runtime_ack=false`、`isolated_simulation_only=true`、
`control_applied_to_production_world=false`。物理结果、reward 和 causal evidence 均为
false，PPO、online assist、online authority 均关闭，规则回退保持启用。

2026-07-22 专项 8 项和 D3 全量回归已通过，全量结果为
`380 passed, 1 skipped`；skip 仍为可选 OR-Tools。该结果只证明 D3 计划消费合同可供隔离
仿真调用。main 尚未完成 control/treatment 多周期克隆世界、D7 命令 lineage 和干预后
物理状态窗口；D6 尚未据此形成 paired physical effect、counterfactual 或 causal 证据。

## 2026-07-21 离线目标库存兼容修复

真实 reserved-seed 重放在 `seed=1011/1019` 的 control/treatment arm 中触发 4→5 目标且
保持旧绑定。旧计划报告 `target_count=5`，第五个当前目标却未进入未分配或不完整清单，
严格消费因此失败。

离线执行器现于生成 arm 计划编号和回执前，依据当前匿名 `TargetTrack` roster 规范化库存。
零绑定目标同时进入 `unassigned_target_ids` 和 `incomplete_target_ids`；部分 M-to-N 联盟只
进入不完整清单；已退出当前 roster 的旧诊断目标被移除，旧可执行绑定继续失败关闭。
生产 runtime ACK 校验器没有放宽，离线证据仍固定 `production_runtime_ack=false`。

缺失 bundle 的 20-seed 扫描共 40 个 arm，严格计划摘要和隔离消费均为 `40/40`。历史首个
失败 `arm index=22, seed=1011, control` 现保留 4 个绑定，并显式记录 `target_0004` 未分配
且不完整。D3 专项为 `19 passed`，全量为 `382 passed, 1 skipped`；skip 仅为可选 OR-Tools。

## 2026-07-22 在线故障代际目标库存

在线中心规划、增量规划和区域授权规划现统一执行版本化目标库存规范化。迟滞可以保留
已有合法绑定，但当前规划帧中的新增目标必须进入同一计划身份。零执行绑定目标同时进入
`unassigned_target_ids` 和 `incomplete_target_ids`，并生成当前需求摘要。库存变化会生成
新的 `plan_id/version`，即使已有绑定集合没有变化；旧版本随即由发布登记和 stale 检查
拒绝。

`advance_authority_generation()` 会在存在匹配的最近规划上下文时，先按该上下文补齐当前
目标库存，再推进故障代际。previous-only 可执行绑定继续失败关闭。完整联盟要求候选成员
数等于可执行绑定数；不完整联盟保留候选成员数和需求短缺，但所有成员不可执行且不发布
assignment。区域授权可为新增目标发布 `unassigned_fail_closed` 合同，不授予执行权限。
计划在发布前继续调用严格载荷校验，生产 `runtime_plan_ack` 校验规则未放宽。

2026-07-22 回归共收集 386 项，结果为 `385 passed, 1 skipped`；唯一 skip 是未安装的可选
OR-Tools。只读三维质点集成复核使用 `center_failure`、5v5、3.2 秒、seed 1011 和 1019。
两个场景均在故障后得到 2 个可用规划帧，最终计划由 `RECON-001` 持有，版本和二级 epoch
均为 3；4 个旧绑定保持不变，第 5 个目标明确未分配且不完整，5 条需求摘要齐全，严格计划
摘要全部通过，在线真值使用为 0。本轮没有启动 AirSim，也没有改变控制授权或生产 ACK。

## 2026-07-22 故障代际离线重放

`center_failure` 的离线 control replay 现按在线计划顺序执行两步：先使用前序 owner 的规划
配置和冻结规则矩阵重建候选计划，再重放规划证据中已记录的二级接管或二级延续合同。离线
执行不再以记录计划的新 owner 直接求解，因此相同 5/5 绑定可重现
`replan_ack_no_change`、`changed=false` 和对应版本，而不是误报为 `replan_applied`。

authority 重放要求 evidence path 为 `authority_identity_publish`，并严格检查 recorded plan、
前序计划、二级 owner、active/executable 状态、激活时刻、lease、epoch 和 link。重放结果
再次通过 `validated_assignment_plan_payload_sha256()`，随后仍由原
`_control_plan_replay_matches()` 精确比较 binding、execution signature、版本、窗口、决策
状态和规模。匹配器没有放宽，离线证据继续声明非生产 ACK。

真实命令运行 `center_failure`、5v5、3.2 秒、seed 1000-1019 成功。20 个 control 和 20 个
treatment 全部生成，40/40 记录二级 identity replay 和严格计划回执；20 个 control 均为
`replan_ack_no_change`。seed 1011/1019 各保留 4 个绑定，`target_0004` 同时未分配且不完整，
需求摘要为 5 条。在线真值使用为 0，输出清单 5/5 通过 SHA-256。D3 全量共 387 项，结果为
`386 passed, 1 skipped`；本轮仍未生成生产 runtime ACK、AirSim 或物理结果。

## 2026-07-22 区域授权待分配库存

`plan_regional_authority()` 现允许 D4 区域授权只覆盖上一计划中的可执行绑定目标。授权集合
小于当前目标集合时，差集中的每个目标必须由上一计划严格证明为零执行绑定，并同时存在于
`unassigned_target_ids`、`incomplete_target_ids` 和一致的需求摘要中。摘要必须为零分配、
正短缺和未完成状态；已有不完整联盟时也必须为零成员。新增目标、漏掉已分配目标、摘要
篡改、未知授权目标和 previous-only 可执行绑定继续失败关闭。

通过验证的待分配目标只进入新计划库存，不生成区域 assignment、coalition、owner、lease
或 commit。计划元数据分别记录实际授权目标和无授权待分配目标，并把后者标为
`authority_granted=false`、`execution_authorized=false`。已有 4 个绑定保持 D4 的 owner、
epoch、lease 和 commit 约束；严格计划载荷校验规则及生产 runtime ACK 未修改。

模块正反例和 `secondary_failure` 集成回归均已通过。集成场景为 5 个目标、4 个区域授权
绑定、1 个显式待分配目标，时长 4.2 秒，seed 1011/1019；main 测试文件 10 项全部通过。
D3 当前收集 391 项，结果为 `390 passed, 1 skipped`，skip 为可选 OR-Tools。本轮仍是三维
质点合同验证，没有 AirSim、生产 ACK、D7 控制采用或物理拦截证据。

## 2026-07-22 非生产隔离执行计划升版合同

D3 公共接口 `build_isolated_execution_plan(...)` 现显式接收同一
`PlanningFrameEvidence`、`offline_solve_source_plan`、`formal_authority_plan`、本 arm
离线候选、arm specification 和原始 execution receipt。离线求解源固定为规划帧的
`previous_plan`，只用于核对 arm、receipt、候选元数据和输入快照。正式权威计划固定为规划
帧的 `plan`，决定隔离执行计划真正超越的代际和降级权威。

规划帧输入快照摘要、完整帧转换摘要、两个源计划载荷摘要和候选摘要共同进入
`d3.isolated-execution-plan-conversion.v2`。跨帧、跨 seed/arm、调用方替换同 ID/version
载荷、错误前序关系和版本跳跃均失败关闭。同 ID/version 的名义评估刷新可被同一规划帧
证明；版本前进时，正式权威必须是求解源的直接下一代。

输出固定为 `formal_authority_plan.version + 1`，并以
`previous_plan_id=formal_authority_plan.plan_id` 建立单步代际关系。`created_at` 使用正式
权威创建时刻与干预时刻的较大值，再取下一可表示浮点数，保证严格递增。有效期不超过 arm
要求、权威 lease、权威 stale 截止时刻和已有计划有效期中的最早值；没有时间空间时拒绝。

转换只重写计划身份和正式权威的 owner/source/link/epoch/lease 语义。候选 binding、未分配
和不完整目标、联盟、需求摘要及 N/M 规模原样保留并重新通过严格计划校验。隔离消费构造器
必须同时获得规划帧、两个源计划、原候选和转换证据，才能接受升版计划。旧的直接离线消费
路径保持兼容，生产 runtime ACK 和在线 `AssignmentPlanner` 未修改。

新计划固定声明 `isolated_simulation_only=true`、`production_runtime_ack=false`、
`runtime_publication_allowed=false`、`runtime_execution_allowed=false` 和
`online_authority_enabled=false`。该合同不产生生产确认、控制授权、物理结果、奖励或因果
证据。专项 18 项覆盖双源正常往返、同代刷新、版本、前序计划、跨帧、时间、lease、库存、
arm/seed/source 和 truth 篡改。普通 5v5 与 `center_failure` 各自使用 20 个 reserved seed、
40 个 arm 扫描；中心失效帧的求解源版本 1、正式二级权威版本 2、隔离执行版本 3 均通过。
D3 全量结果为 `408 passed, 1 skipped`，唯一 skip 仍为可选 OR-Tools。本轮没有运行 AirSim，
也没有产生 D4 adoption、D7 控制采用或物理结果证据。

## 2026-07-22 区域权威离线重放

离线执行器现识别 `planning_path=regional_authority`。`PlanningFrameEvidence` 对匿名前序
计划、记录区域计划、帧路径和时刻生成区域权威转换摘要；记录计划或前序计划的载荷发生
变化时，摘要校验先于求解失败关闭。普通中心规划和二级身份发布路径仍把记录输出视为
重放结果，没有改变既有输入快照语义。

区域帧回放从每条已授权 assignment 恢复区域层级、区域号、owner、epoch、lease 和 commit，
再调用线上 `plan_regional_authority()`。因此旧版本、过期租约、旧代际、缺失提交和非法成员
继续使用同一套 D3 校验。显式未分配且不完整的目标不进入授权 DTO，不产生 binding、owner、
lease 或 commit。重放后仍由原精确匹配器核对 binding、完整执行签名、版本、窗口和决策状态。
处理臂不能借学习代价越过记录的区域授权集合或 action mask。

真实三维质点 `secondary_failure` 使用规模 5、时长 3.2 秒和 seed 1000-1019，20 个 control
与 20 个 treatment 均生成。seed 1011/1019 的两个 arm 均保留 4 个绑定，`target_0004`
同时在未分配和不完整清单中，且没有区域 assignment。在线真值使用为 0。离线干预专项为
`23 passed`，D3 全量为 `419 passed, 1 skipped`；skip 仍为可选 OR-Tools。本轮没有运行
AirSim，也没有生成生产 runtime ACK、D4 物理采用或拦截结果。

## 2026-07-22 规划证据性能收敛

200 目标、200 资源、每目标最多 32 条候选边时，规划器仍保留 40,000 单元的确定性求解
矩阵和 6,400 条候选边。原实现对规则矩阵和有效矩阵分别深度匿名化全部单元，即使二者共享
同一 breakdown 结构，也会重复清洗和复制。单次规划约触发 80,200 次 breakdown 清洗，
规划证据成为确定性主耗时。

当前实现按源 breakdown 对象身份缓存只读匿名结果。规则矩阵和有效矩阵共享源结构时复用
同一匿名 breakdown/reject tuple，数值矩阵仍各自保存独立、不可写副本；学习残差形成不同
有效结构时仍分别处理。迟滞比较只复制 hard-safe candidate breakdown，不复制已裁剪或硬
拒绝单元。规则代价、不可达边、资源容量、M-to-N demand slot、Hungarian、迟滞、计划版本、
stale 拒绝、联盟和 D7 binding 合同均未改变。

独立同配置开发基准的向量化中位数由 `2651.953 ms` 降至 `189.111 ms`，加速 `14.023x`；
当前工作树复跑为 `195.716 ms`。cProfile 中 breakdown 清洗由约 `80,200` 次降至 `6,601`
次。完整 seed 42000、2.2 秒、200v200 质点链路的三次 D3 规划由 `7.329949 s` 降至
`1.013593 s`。这些是开发性能证据，不是硬实时验收，也不代表完整 episode 的全部提速均
来自 D3。结果记录见 `results/scalable_3d_planner_hotpath_20260722.json`。

新增测试覆盖 3x5、5x3、200x200、M-to-N 和 previous-plan 多周期语义及操作计数。定向
回归为 `62 passed`；D3 全量选定集为 `422 passed, 1 skipped, 2 deselected`。两项
`global_track_stale` 失败可在未修改 HEAD 复现，属于 main/D7 跨模块既有断点；D3 不通过
放宽 stale 门控处理。完整 200v200 多 seed、AirSim 和物理拦截仍由 main 组织后续验收。

## 2026-07-22 AssignmentPlan 在线成本证据去重

200v200 长时输出中，每条 `modules.d3.assignment_plan` 同时携带
`cost_breakdowns_by_edge` 和内容相同的 `current_cost_breakdowns_by_edge`。只读 seed
42000 样本的一条计划包含 6,304 条边，两份列表各占 4,757,920 字节。仓库消费者检索确认，
前者是 D3、D4/D6 回放使用的规范证据字段，后者没有 Python 消费者。

当前计划元数据使用 `d3_assignment_evidence_v2`。完整边成本只保存在
`cost_breakdowns_by_edge`，同时记录 `d3_cost_breakdowns_by_edge_v1`、条目数、规范
SHA-256、`inline_canonical_single_copy` 和旧字段引用。`assignment_evidence_from_plan()`
优先读取规范字段，并兼容 v1 的双字段或仅旧别名输入；v2 的计数、摘要、存储方式或引用不
一致时拒绝导出。`assignment_plan_v2`、Hungarian、候选集、迟滞、owner、版本、stale、
联盟和执行签名没有改变。

合成 200x200、6,400 候选边计划由 10,466,292 字节降至 5,622,366 字节，减少
4,843,926 字节，即 46.28%。同一测试确认 assignment、稳定签名、执行签名和计划身份一致。
只读 10 秒样本按新字段投影由 9,905,419 字节降至 5,147,795 字节，减少 48.03%；该数字
尚不是新代码完整 episode 复跑结果。新增专项 5 项通过。D3 全量收集 430 项，其中 427 项
通过、1 项因可选 OR-Tools 跳过、2 项为既有跨模块 `global_track_stale` 失败；D3 未放宽
stale 门控。

## 2026-07-22 冻结输入性能归因

新增 `performance_diagnostics.py` 和
`simulations/run_planner_performance_diagnostics.py`。接口使用定长
`D3PlannerOperationCounts` 记录成本矩阵、候选边、候选连通分量、Hungarian 准备矩阵、
计划边物化与规范哈希、迟滞重评分、匿名证据复制和发布校验的结构操作数。墙钟只写入
benchmark JSON/Markdown，不进入 `AssignmentPlan.metadata`、`plan_id`、执行签名或运行时
ACK。

冻结输入为 200 个匿名 GlobalTrack 代理和 200 个资源，seed 42000、top-32，输入
SHA-256 为
`c7c86f22252add5a6e201577ec99baa63050e56d00898e66d514ab3c0c46c7ff`。每帧保留
40,000 个全量目标资源对、6,400 条候选边、一个 200×200 候选连通分量和 80,000 个
Hungarian 准备矩阵单元。首帧匿名证据复制 80,000 个数值单元并访问 40,000 个 breakdown
单元，实际净化 6,401 个共享对象；上一计划帧另访问 6,400 条迟滞边并重评分 400 个绑定。

三次暖启动中，默认首帧/上一计划帧中位端到端为 `274.275/334.735 ms`。上一计划帧的
计划边证据、迟滞和离线匿名证据中位耗时分别为 `82.342/31.602/74.305 ms`，Hungarian
约 `4.460 ms`。关闭离线证据的归因参考为 `223.147 ms`，只说明该证据边界的成本，不是
允许在线关闭证据的新配置。

发布链路在一次规划调用内复用候选执行签名。latest published execution signature 由规划器
自有缓存跨帧保存并作为发布权威；caller previous 只计算一次签名并与该权威值做一致性校验，
不能替代 latest。公共 `publish_plan()` 仍从待发布对象计算 candidate signature。区域接管
先校验 plan id/version 和专用 pending inventory，再执行通用语义一致性校验。上一计划帧中，
默认身份固化/发布边界
为 `2.967/0.156 ms`，重复计算参考为 `15.629/13.246 ms`。默认、重复计算参考和关闭证据
参考的 binding SHA-256、计划版本和规范业务 SHA-256 完全一致；规则代价、Hungarian、
需求槽、迟滞、版本及 D5/D7 binding 未修改。原始结果见
`results/d3_planner_performance_attribution_20260722.json`，中文说明见
`reports/D3_PLANNER_PERFORMANCE_ATTRIBUTION_20260722_CN.md`。

该性能阶段初次收集 439 项，结果为 `436 passed, 1 skipped, 2 failed`。skip 是可选
OR-Tools；两个失败表现为 main/D7 `global_track_stale`。后续 seed 7 由 main 的未消费后验
锁存恢复，seed 41 由本模块修正 ACK 取样口径；当前同一全量集为
`438 passed, 1 skipped, 0 failed`，且没有放宽 stale 门。身份缓存、直接发布、authority
fence、区域错误优先级和性能诊断定向组合为 `46 passed`。

## 2026-07-22 clean 10 秒三种子集成复核

main 已在 clean commit `8f86192` 上完成 200v200、10 秒、seed 42000-42002 复跑。三组
`repository_dirty=false`、`finite_state=true`、`online_truth_use_count=0`。每组均发布
10 份 D3 计划并收到 10 次计划 ACK。D3 assignment 累计墙钟分别为
`3.437/3.319/3.110 s`，均值 `3.289 s`；旧 clean commit `3bac3ff` 的对应均值为
`3.348 s`，变化约 `-1.8%`。

三组的调用次数、计划发布数、计划 ACK，以及 binding ACK、control applied、hold 业务摘要
与旧提交逐 seed 一致。该复跑确认 D1 快照优化没有改变 D3 的计划执行语义。1.8% 的墙钟差异
按基本持平和调度噪声处理，不作为 D3 优化归因、实时能力或晋级依据。

冻结 200x200 benchmark 与本次集成复核是两组独立证据。前者保持默认上一计划帧
`334.735 ms` 等原始数字，用于固定输入下的热点归因；后者记录完整 10 秒 episode 中 10 次
D3 调用的累计墙钟和业务一致性。当前仍未证明 AirSim、物理拦截、长期内存上限或生产实时
能力。

## 2026-07-22 独立运行计划身份等价审计

`AssignmentPlanner` 有意使用 `uuid4` 为每个新执行谱系生成 `d3-plan-*`。因此，同一 seed、
同一输入和同一时间轴交给两个全新的 planner 实例时，首份计划及后续新谱系的原始
`plan_id` 应不同。这个随机身份用于避免不同 episode 或不同发布者把计划误认为同一对象，
不是规划算法的随机动作。单个 planner 实例内，纯成本或评估刷新必须复用原
`plan_id/version`；assignment、owner、activation 或 coalition 执行语义变化时才建立新
谱系。在线计划发布链路中，authority generation fence 是唯一允许“执行签名不变但身份升版”的显式隔离事件，
它必须保留专用原因和前序关系。

跨独立运行比较不得直接比较原始 `plan_id`，也不得递归删除所有 `*_id`。先按 D3 发布记录
的 `sequence_index` 或总线序号排序，对每个原始计划号按首次出现依次映射为
`P0000/P0001/...`。同一原始计划号的刷新继续映射到同一规范号；新计划必须保留
`version=parent.version+1` 和 `previous_plan_id/supersedes_plan_id -> parent` 的关系。
`current_plan_id`、`latest_plan_id`、区域提示的 source plan 引用及 fault fence source 引用
使用同一映射。由计划号拼接出的 binding/decision 标识应在替换计划号后重建，完整 payload
摘要也应对规范载荷重新计算。

下列内容仍须精确一致：计划版本与窗口、执行签名、目标-资源绑定、未分配和不完整目标、
成本与迟滞结果、decision/changed/published 状态、owner/source/link、stale/reject 原因、
coalition id/version/epoch/member/role/wave/commit/lease，以及 resource、target、
`global_track_id` 和节点标识。`coalition_id` 当前由目标标识确定，不属于随机计划身份，不能
归一化。原始 runtime payload SHA-256 包含随机计划号，跨运行不要求相同；同一运行内 ACK
仍必须精确匹配收到的原始摘要。

现有 `canonical_plan_business_sha256(...)` 是冻结 D3 基准的快速业务哈希，只删除少量计划
身份字段，不验证完整前序图、stale 引用或二级 owner 转换，不能单独作为跨模块长时运行的
谱系等价证明。完整算法和字段分类见 `docs/ALGORITHM_AND_IMPLEMENTATION.md`。当前
scalable runtime 的简化 D3 publication 未直接携带顶层 `previous_plan_id`；main 对现有
产物只能在版本连续且发布事件无缺失时用前一份已发布计划推导父关系，并应将证据标记为
`derived`。该简化载荷也不是完整 `AssignmentPlan.execution_signature()` 的序列化形式，
因此现有日志只能证明规范化后的发布业务载荷等价。后续正式审计优先持久化 D3 已提供的
`PlanningTickHistoryRecord`，需要完整签名证明时同时保留规范计划载荷。

## 2026-07-26 真值无关干预候选帧资格

D3 新增版本化 `LearningInterventionFrameEvidence`。它从同一时刻的规则组和处理组
`PlanningFrameEvidence` 推导候选帧资格，不接收调用方填写的 eligibility、准入或执行权限
布尔值。公开接口如下：

- `evaluate_learning_intervention_candidate_frame(...)`：严格核验一对规划帧并生成证据；
- `validate_learning_intervention_frame_evidence(...)`：拒绝缺字段、额外字段、占位摘要和
  内容篡改；
- `select_first_eligible_learning_intervention_frame(...)`：只接受 `sequence_index` 和
  `timestamp_s` 同时严格递增的历史，返回按规划时间的首个合格帧；重复或逆序时间戳拒绝；
- `canonical_learning_intervention_frame_evidence_sha256(...)`：计算除自引用内容摘要外的
  完整证据 SHA-256。

资格必须由同输入快照、同前序计划、模型实际作用、无回退、无分布外、无超时、无非有限值、
两份计划均可行、硬候选边有效、版本链有效、需求槽与 M-to-N 全有或全无合同完整，以及
规则/处理绑定确有差异共同成立。任一条件不满足时输出稳定原因码并
`eligible=false`。证据作用域固定为
`checkpoint-selection-only-no-admission-no-authority`，不改变规则 Hungarian、需求槽
Hungarian、代价公式、迟滞、分布外门限、生产模型加载器或 assist 权限。

main 先前对 20 个保留 seed 的共同检查点做过物理续跑。规则组和处理组各施加 980 条控制
命令，计划消费及物理观察窗口均为 20/20，但最终绑定变化为 0/20，轨迹和指标相同。该结果
来自脏工作树开发运行，只能判定本批检查点没有形成可辨识规划干预，不能用于模型准入。
后续 main 应按 seed 向上述 API 提供规则/处理帧，并保证序号和规划时间戳分别严格递增，
再把 D3 首个合格帧与 D7 共同检查点求交。一个规划周期只允许一个时间戳，不采用二级排序
容纳同刻帧。

2026-07-26 专项测试为 `19 passed`。D3 全量收集 485 项，结果为
`484 passed, 1 skipped`，唯一跳过仍是可选 OR-Tools。此次没有改变 AirSim 输入输出、
episode 编排或控制行为。

## 2026-07-26 单帧隔离干预重放

D3 新增 `replay_isolated_learning_intervention_frame(...)`。main 可把一份冻结的
`learning_state=rule_only` 匿名规划帧、时间序号、development/shadow-only bundle 路径及
带外 manifest SHA-256、policy version 交给该接口。接口复用既有安全 bundle loader、
冻结规则矩阵和规划器，分别以 `publish=False` 重放规则组与处理组，再调用
`evaluate_learning_intervention_candidate_frame(...)` 生成资格证据。

返回对象 `IsolatedLearningInterventionFrameReplay` 同时保存完整规则帧、处理帧、bundle
实际装载状态、稳定回退原因、输入谱系摘要、资格证据和完整内容 SHA-256。源帧必须满足：

- 规则矩阵与有效矩阵的完整输入证据一致；
- 前序计划版本、当前计划身份、升版关系和有效期均合法；
- 航迹与资源标识的集合、顺序和矩阵谱系一致；
- 输入不含 truth、物理结果、拦截成功或 reward 字段，所有数值有限；
- 处理学习只在 manifest/hash/version 正确且 bundle 保持 v3 development、
  shadow-only 时实际应用；其他情况使用原规则回退并保持 `eligible=false`。

接口内部调用 `planner.publish_plan(previous_plan)` 只为新的隔离规划器设置本地前序状态。
两个候选计划仍以 `publish=False` 计算，不发布到运行总线。DTO 固定声明运行发布、运行 ACK
和 authority 均不可用，也不提供 outcome、reward 或正式 admission。

匿名 `PlanningFrameEvidence` 不携带实验 seed。保留 seed `1000-1019`、split 身份、清单
完整性和逐 seed 首个共同检查点由 main/D6 外层 manifest/runner 校验；本接口不单独声称
holdout inventory 验证。2026-07-26 新增专项 `17 passed`，与既有离线执行和资格测试合并
为 `59 passed`。D3 全量收集 502 项，结果为 `501 passed, 1 skipped`，唯一跳过是可选
OR-Tools。该接口形成时尚未完成的 20-seed 外层正式运行，现已按下节批量合同完成。

## 2026-07-26 隔离干预 20-seed 批量合同

D3 新增 `isolated_intervention_batch`。该模块把单帧重放扩展为固定 seed
`1000-1019` 的外层检查点选择合同，仍不进入物理世界。输入必须是一份显式
`d3.isolated-learning-intervention-batch-manifest.v1` 清单，内容包括：

- 唯一且按数值顺序排列的 20 个 seed；
- 每个 seed 按 `sequence_index` 和 `timestamp_s` 同时严格递增的匿名
  `PlanningFrameEvidence` 文件、文件 SHA-256 和内容 SHA-256；
- development bundle 目录、manifest SHA-256、policy version；
- 生成输入的 40 位源提交和 `worktree_state=clean`；
- 完整 `PlannerConfig` 与 `CostWeights`，避免调用方使用隐式默认值。

runner 不扫描相邻目录，也不从物理结果、真值、Actor 标识或调用方布尔值推导资格。每个
显式帧调用既有 `replay_isolated_learning_intervention_frame(...)`，然后使用既有 selector
选择本 seed 的首个合格帧。没有合格帧时写入 `unavailable/no_eligible_frame`，不补选。
manifest、帧文件、模型文件在运行前后都复算 SHA-256；输入变化、seed 缺失或重复、乱序、
schema/hash/bundle 不匹配、非有限值及非空输出目录均失败关闭。

输出目录以 staging 目录完整生成后原子替换，固定包含 JSON、逐 seed CSV、中文 Markdown
和 `SHA256SUMS`。逐帧 replay/evidence 摘要只覆盖可复现业务语义；本地随机计划号和墙钟
推理耗时不进入批量摘要。相同清单和固定 `evaluated_at` 写到两个空目录时，四个文件应逐
字节一致。所有输出固定 `publish=false`，运行 ACK、生产分配权限、生产控制权限、物理
结果和 reward 均不可用，`global_track_id` 改写计数为 0。

2026-07-26 使用三资源、两目标、一个双 primary 目标的开发夹具验证 20 个 seed。正残差
夹具 20/20 seed 选出首个合格帧；零残差夹具 20/20 seed 明确不可用。两次独立输出逐文件
一致。该结果仍只属于合同测试。

main 随后在 clean source commit
`0ed7ca2730f5354be1e6021f9882f1ae26bc42df` 生成真实 manifest，固定 seed
`1000-1019`，每 seed 5 帧，共 100 个匿名规划帧，在线 truth 字段计数为 0。输入
manifest SHA-256 为
`e5367d2651955f809b482d78ef3205cbdf44d57eae576c80f64cbd38eac59a44`，输入
`SHA256SUMS` 全部通过。首次运行在 seed 1011、序号 3 失败。新增目标的记录联盟匿名标识
为 `coalition_0004`，隔离规划器按匿名目标名生成
`d3-coalition-target_0004`；资源绑定、成本、迟滞、版本、窗口和决策状态均一致。D3 现先
校验记录、重放和前序计划的联盟库存、唯一性、assignment、需求摘要和 metadata 引用，再
只为新联盟恢复已哈希绑定的记录标识。既有联盟标识变化、重复标识或引用不一致继续失败
关闭，最终仍执行原完整控制签名比较。

修复后的正式 clean evaluator 使用代码提交
`bdb665eb8e63a17f5f15dbf3fe472af10e5e5b5c`，完成 20 seed/100 帧重放。输出
`SHA256SUMS` 全部通过，内容 SHA-256 为
`c01b13fb5925d99078a3bb9505dc0f9511ec5ab700a432399d3ebe0fcfb55592`。输入与正式输出的
外部归档 SHA-256 为
`127ad91d864b136ab10cde7111bf6241a7a765ad4467aa449ef29cbb5557ef5e`；临时证据未复制进
本模块。

正式结果为 `eligible_seed_count=0`，20/20 seed 均为
`unavailable/no_eligible_frame`。80 帧实际应用学习代价，20 帧因分布外使用规则回退；
每个 seed 的 binding change 均为 0，规则组和处理组硬违规均为 0。输出固定
`publish=false`、`production_assignment_authority=false` 和
`production_control_authority=false`，运行 ACK、物理结果和 reward 均不可用，
`global_track_id` 改写为 0。相同 manifest 与固定评估时刻的开发确定性复核还验证了两个
空目录四个文件逐字节一致。

新增真实形态正负例后，单帧专项为 `23 passed`；相关干预合同组合为 `79 passed`。D3 全量
结果为 `521 passed, 1 skipped`（522 项），唯一 skip 仍是可选 OR-Tools。Matplotlib
`Axes3D` 环境警告不影响 D3 合同测试。正式结果只关闭隔离批量重放合同。0 个 eligible
seed 表明当前 development policy 没有越过 Hungarian 离散绑定边界，不能形成 D7
checkpoint，也不能授予 A1 准入、默认路径、PPO、assist、物理收益或生产权限。

## 2026-07-26 A1 选择后阶段证据

D3 新增 `a1_intervention_selection`，用于把候选帧选择后的事实分阶段记录。该模块不重复
`learning_intervention_eligibility` 的输入谱系、模型作用、硬约束、需求槽或 M-to-N
原子性判断。`evaluate_a1_intervention_candidate(...)` 先调用既有
`evaluate_learning_intervention_candidate_frame(...)`，再在预注册范围内检查学习代价
修正上限、规则代价下的近似竞争程度、需求覆盖非退化、高威胁目标覆盖非退化和严格升版。

预注册合同冻结实验标识、模型制品摘要、seed 清单、序号和时间范围、最大代价修正、规则
代价差及最大绑定变化数。在线真值固定禁用，规则回退和确定性安全外壳固定启用，预注册本身
不授予生产权限。selector 按严格序号和时间顺序选取首个安全离散变化；没有候选时返回
`no_safe_discrete_intervention`，不会用绑定未变化的帧补位。

阶段证据分别记录：

1. `policy_evaluated`：冻结学习策略在该帧实际完成安全评估；
2. `cost_correction_accepted`：代价修正通过既有资格层和预注册边界；
3. `assignment_changed`：资源、目标或联盟绑定出现可审计的离散变化；
4. `plan_published`：main 的 D3 总线载荷与选中 `AssignmentPlan` 完全一致；
5. `runtime_ack`：既有运行确认合同验证同一计划、来源序号、载荷摘要和学习采用状态；
6. `physical_window_available` 与 `r0_pair_available`：计划全部执行 binding 分别具备完整
   后续观察窗口和同 seed 规则基线配对证据。

后续证据缺失时状态停留在最后一个已证明阶段。发布记录不能推出运行确认，运行确认不能
推出物理窗口，部分 binding 窗口不能推出整份计划可用，未配对窗口不能推出 R0 非退化。
候选证据和选择结果固定声明运行阶段为 false，防止调用方预填后续事实。

专项测试 `13 passed`，覆盖无真值选择、确定性复现、无竞争帧失败关闭、安全近似竞争下的
离散变化、重复资源、硬禁边、旧版本、预注册绑定变化上限、发布谱系、运行确认、完整物理
窗口、R0 配对及伪造阶段字段拒绝。D3 全量收集 535 项，结果为
`534 passed, 1 skipped`，skip 为可选 OR-Tools。正式 20-seed/100-frame 结果没有重跑，仍为
`0/20 eligible`；本次没有形成新的计划发布、运行确认或物理结果。AirSim 接口和 episode
流程未改变。

## 2026-07-27 A1 隔离批处理入口

现有隔离 batch 新增可选 `--a1-preregistration` 模式。main 不再需要复制 bundle 校验、
匿名帧读取或单帧 replay 逻辑。公开 Python 入口为：

```python
run_a1_isolated_intervention_batch(
    manifest_path,
    preregistration_path,
    output_dir,
)
```

命令行入口继续使用原脚本：

```bash
PYTHONPATH=research_modules/d3_assignment_planner/src \
python3 research_modules/d3_assignment_planner/scripts/run_isolated_intervention_batch.py \
  --manifest <strict_batch_manifest.json> \
  --a1-preregistration <a1_preregistration.json> \
  --output <empty_output_directory>
```

入口只执行一次既有 batch replay。每帧直接把
`replay.rule_frame/replay.treatment_frame` 交给核心
`evaluate_a1_intervention_candidate(...)`，每 seed 再调用
`select_a1_intervention_candidate(...)`。重新生成的 eligibility 内容摘要必须与 replay
已有证据一致，否则失败关闭。

预注册 seed 必须精确覆盖 `1000-1019`，序号和时间范围必须覆盖清单全部帧，
`policy_artifact_sha256` 必须等于 bundle 的 state-dict SHA-256。预注册文件与 manifest、
匿名帧、bundle manifest 和 state-dict 一并在运行前后复核，真值字段、摘要篡改、作用域
缺失或运行中变化均阻断输出。

A1 模式原子写出：

- `isolated_intervention_batch.json`；
- `isolated_intervention_per_seed.csv`；
- `D3_ISOLATED_INTERVENTION_BATCH_REPORT_CN.md`；
- `a1_intervention_batch.json`；
- `a1_intervention_candidates.json`；
- `a1_intervention_selections.json`；
- `SHA256SUMS`，覆盖前六个文件。

候选和选择文件使用独立、版本化的隔离 batch schema。核心 A1 选择仍在内存中使用完整
DTO；写盘投影保留阶段布尔、成本、需求缺口、版本、规则/处理 binding 摘要、拒绝原因和
预注册谱系。随机 plan id、完整 plan payload SHA-256 及墙钟推理时间不进入稳定投影。
因此相同输入的独立重跑可逐文件一致。该投影不能作为后续 `plan_published` 证据；main
实际发布时仍须用精确运行计划和总线 envelope 构造
`A1PlanPublicationEvidence`。

2026-07-27 新增 6 项 batch 专项。40 帧合成正例两次独立运行逐文件一致，20/20 seed 均
选择序号 0 的首帧；零残差负例 20/20 seed 返回
`no_safe_discrete_intervention`。真值、预注册内容篡改、seed 范围和帧范围均被拒绝。
batch 专项共 `20 passed`，与核心 A1 合计 `33 passed`。D3 全量收集 541 项，结果为
`540 passed, 1 skipped`；skip 仍为可选 OR-Tools。正式 20-seed/100-frame 数据没有重跑，
既有 `0/20 eligible` 结论不变。

## 2026-07-27 A2 区域提示权属绑定

D3 在采用区域规划提示前，现要求全部区域约束具有完全相同的 `owner_layer`、`owner_id`、
`owner_epoch` 和 `lease_expires_at_s`。任一字段不一致时，整份提示以
`regional_hint_authority_scope_mismatch` 拒绝，规划器回到原规则候选图。单个区域租约
过期、提示超出租约等既有检查仍先返回原有的更具体原因。

提示通过原有来源计划、时间、区域集合、租约、资源守恒、保护资源和跨区额度检查，并且
形成新的可执行语义后，D3 才把统一权属写入严格后继计划。`plan_owner`、
`active_plan_owner`、`current_plan_owner` 及对应 owner node 字段采用同一权属；
`authority_epoch` 和 `lease_expires_at_s` 同时写入。`runtime_plan_ack` 原有解析器会从
计划 metadata 读取这两个字段，因此无需另建 ACK 字段。提示被拒绝、没有提示或没有形成
可辨识后继时，不刷新 epoch/lease，也不改变源计划的执行权属。

2026-07-27 的模块夹具覆盖两目标增加到三目标后的严格新计划、owner/epoch/lease 三类
不一致、同权属无动作提示和无提示刷新。无动作提示保持源计划身份，并明确返回
`no_successor`，不再以“提示已应用”表示后继计划已发布。

本次只关闭 D3 计划缺失权属元数据的合同缺口。测试没有生成真实 main ACK、owner ACK、
coalition ACK、后续物理窗口或同键规则基线，不能据此声明 A2 已完成物理采用。
本段记录的是后续 20-seed 重跑前的模块合同状态；当前证据以“2026-07-27 A2 后继计划
判定”一节为准。

## 2026-07-27 A2 后继计划判定

早期开发输出曾将 18/20 普通 D3 滚动重规划归因给 A2，并只在 seed 1002、1007 观察到
版本门拒绝。该结论已被按修正后 successor 合同完成的 20-seed 重跑取代。新证据显示：
20/20 seed 均有候选评估记录，但受控策略在全部 seed 都没有资源配额变化、hold、
`request_replan` 或跨区 transfer。可识别区域干预、实际 A2 采用和 A2/R0 收益审计均为
0/20。普通滚动重规划不得反向归因给 A2。

区域提示结果现使用 `d3_regional_planning_hint_successor_v1` 合同。内部候选约束是否生效
由 `regional_hint_constraint_applied` 记录。只有执行签名改变、`plan_id` 不同、
`version` 严格递增且 `previous_plan_id` 指向源计划时，
`regional_hint_successor_plan_available=true` 和
`regional_hint_successor_state=successor_published` 才成立。

执行签名未变化时，D3 保持源身份和原权属控制字段，返回
`regional_hint_successor_state=no_successor`、
`regional_hint_successor_plan_available=false` 和
`regional_hint_no_executable_successor`。`regional_hint_applied` 同时为 false，防止旧
消费者继续把该结果包装成后继计划。无效或过时提示使用 `hint_rejected`，仍按原规则路径
规划。上述处理没有机械升版，也没有放宽迟滞、旧版本拒绝或幂等发布。

验收结果：区域提示专项 `21 passed`；区域提示、计划身份、规划证据和运行回执组合
`65 passed, 1 warning`；D3 全量收集 548 项，结果为 `547 passed, 1 skipped`。唯一
skip 为可选 OR-Tools，warning 为既有 Matplotlib 三维导入提示。

main 重跑已验证上述失败关闭行为。20 条候选均以
`identifiable_regional_intervention_missing` 保留为无操作拒绝，不携带后继计划、运行
确认、所有者确认、联盟提交或物理窗口。证据文件 SHA-256 为
`ff3c10a089b6a94582451ae05d8a884af3a2bd7485acd4df0496442ea7e0ec55`。

A2 下一步必须提供经过确定性投影后仍能形成受约束非零配额、hold、重规划请求或 transfer
的候选，再重新建立 successor、运行确认和同键 R0 物理窗口。D3 继续对无执行变化返回
`no_successor`；不得机械升版，也不得把同期普通规划变化计作 A2 采用。

## 2026-07-27 A2 非零区域干预消费边界

D3 进一步补齐区域 `hold` 的实际候选图语义。处于 hold 的区域不允许新增或更换目标-资源
边；仅保留来源计划中触及该区域且仍通过硬安全门的绑定。来源绑定已经因资源不可用、身份
门或其他硬约束失效时，整份提示以 `regional_hint_held_assignment_infeasible` 拒绝并
回到无提示规则规划。该拒绝不能为提高 A2 采用率而绕过。

`request_replan=true` 表示本轮需要重新求解并留下审计记录。重新求解后的执行签名不变时，
仍返回 `no_successor`，计划号和版本不变。无来源承诺的区域可以合法进入 hold：若新目标
进入该区域，规则基线会形成新绑定，而 hold 约束会保持其未分配状态；该执行库存变化可
形成严格后继。另一条合法路径是守恒的非零配额和跨区转移直接改变可执行绑定。

严格后继现显式携带 advisory id/version、source plan id/version、owner layer/id、
authority epoch 和 lease，同时记录 hold 与 request-replan 区域。模块测试以三区域构造
验证 A→B 的守恒转移、C 区来源绑定保持、无承诺 C 区保持、request-replan-only 无操作和
held edge 硬失效拒绝。区域提示专项为 `25 passed`；D3 全量收集 552 项，结果为
`551 passed, 1 skipped`，另有 1 条既有 Matplotlib `Axes3D` 环境警告。skip 仍为可选
OR-Tools。

main 提供的未落盘 20-seed 诊断中，15/20 形成 safe/auditable A2，seed
1000/1002/1007/1009/1013 停在 `d3_successor_plan_missing`。seed 1000 在 t=1 为
`regional_hint_no_executable_successor`，t=2 为
`regional_hint_held_assignment_infeasible`。该诊断用于定位策略选择边界，不替代前述
正式 20-seed 0/20 证据，也不构成运行确认或物理结果。

## 2026-07-28 D4 当前谱系 A2 严格后继证据

D3 新增只读 `a2_successor_evidence`。该模块复用现有 `RegionalPlanningHint`、
`AssignmentPlan.execution_signature()` 和计划载荷校验，不进入规划热路径，也不改变
Hungarian、需求槽 Hungarian、迟滞、硬约束或规则回退。公开入口包括：

- `load_a2_current_lineage_identity(...)`：独立读取 D4 当前谱系候选清单，复算文件与内容
  摘要，绑定候选编号、模型版本、权重和源码身份，并确认全部权限为 false；
- `build_a2_successor_plan_evidence(...)`：核对 D4 实际模型诊断、确定性投影动作、D3
  区域提示、前序计划、同输入 R0 计划和候选后继；
- `validate_a2_successor_plan_evidence(...)`：重新读取单条证据并复核全部摘要和关闭状态；
- `build/load/write_a2_successor_evidence_batch(...)`：为通过运行兼容性预检的新候选保存
  正式 20-seed 独立影子评价所需的候选一致、比较键唯一记录集。

证据只承认候选计划相对同输入 R0 的执行签名增量。R0 相对前序计划是否因普通周期重规划
改变单独记录，不能计入 A2 作用。安全投影后的区域配额、备用资源数、hold、
`request_replan` 和跨区 transfer 必须与 D3 实际消费提示一致；候选计划还须相对前序
严格 `version+1`。无操作、资源不可行、过时版本、候选身份错配、候选/R0 混用和候选与
R0 执行签名相同均失败关闭。

当前本地 D4 实物已通过身份读取：

- candidate manifest 文件 SHA-256：
  `7cc10ad770bd95fcb813dbf3d16b17040ec5f41f80fe0dc53e3e291a32f4de64`；
- candidate manifest 内容 SHA-256：
  `b51f2ed01d7f8b963166fe1d7e73acd6a481c5359d54ed5c3712371733aa6ba9`；
- model state SHA-256：
  `fd1b9c4cf7580083fadc04a70b87aa6439930eba764a970279611ccc57f30047`；
- source identity SHA-256：
  `b81780cece11c792acb3113af2d4be48a19b51c0337a67c926b388197d09dfdf`。

上述结果只证明当前候选身份可读。D4/main 的运行兼容性检查显示，该候选在 5v5、2 区域
的 3/3 次预检和 200v200、8 区域的 2/2 次预检中均触发 `feature_ood`，非回退模型执行
为 0。因此不得使用该候选启动正式 20-seed successor 批次。

正式批次的前置顺序是：D4 先基于实际运行特征和动作课程构建 clean-lineage、
runtime-compatible 的新 development/shadow 候选；D3 loader 再核对候选身份和关闭权限；
main 随后执行非正式兼容性预检。只有预检出现非回退模型执行，且确定性安全投影继续通过，
才能冻结新候选身份并生成至少 20 个真正未见 seed 的正式 successor 证据。预检仍全部
回退时必须停止，不能用合同夹具或当前候选补足正式分母。

新增专项 `16 passed`，区域提示与新证据组合 `41 passed`。D3 全量收集 610 项，结果为
`609 passed, 1 skipped`；跳过项仍是可选 OR-Tools。以上只证明软件边界和当前候选身份
可读。运行兼容的新候选、正式 successor 记录、运行确认、owner/coalition ACK、物理
窗口、D7 执行或收益证据尚未生成，全部相应字段固定为 false。

## 2026-07-29 readiness-v3 增量跨区合同

main 在修改前冻结了 seeds 2003-2012 的 20v20、8-region 隔离基线。10/10 seed 的
readiness-v3 原始推理、运行门、确定性投影和隔离采用均通过，但 D3 严格后继为 0/10。
拒绝分布为 `regional_hint_no_executable_successor` 3/10、
`regional_hint_previous_cross_region_commit_exceeds_allowance` 7/10。后者来自 D3
把来源计划已有跨区绑定再次计入本轮 transfer allowance，与 D4 的配额/转移增量语义不
一致。

D3 现将 `RegionalTransferAllowance.resource_count` 定义为来源计划之外的新增跨区资源
上限。来源计划已有跨区绑定作为基线承诺，只能在原 target-resource edge 上继承，并且
必须继续通过可用性、身份、友方冲突、三维可达性等硬安全门。它不消耗新增 allowance，
也不能换绑到同区域的另一个目标。新跨区资源仍从未承诺资源中选择，继续受 quota 守恒、
备用资源下限、route 容量、资源唯一性和 Hungarian/需求槽 Hungarian 约束。

审计输出同时记录来源基线、保留基线、新增许可、新增实际和总实际跨区资源数。旧的
allowed/actual 字段保留总量口径，新增 incremental 字段用于验证
`incremental_actual <= incremental_allowed`。来源边硬失效时仍以
`regional_hint_protected_transfer_edge_infeasible` 拒绝整份提示并回退规则规划。

`reconnaissance_priority` 没有进入 D3 可执行合同。D3 当前没有区域搜索任务、侦察资源
资格、离散优先级档位或优先级到分配代价的确定映射；约 `1e-4` 的连续变化不能形成
`AssignmentPlan` 执行语义。单独改变 reserve ratio 也只改变新增 transfer 的安全余量，
不会凭空生成区域备用资源名单或机械提升计划版本。未来若需要执行侦察优先级，调用方
必须先提供版本化搜索任务、合格侦察资源集合、量化/死区规则、有效期和可审计的成本作用。

2026-07-29 的区域提示专项为 `30 passed`。D3 全量结果为
`614 passed, 1 skipped`；skip 仍是可选 OR-Tools，另有一条既有 Matplotlib 三维导入
警告。该结果关闭 D3 对既有跨区承诺重复计数的软件缺口，没有生成新的 readiness-v3
后继、运行 ACK 或物理结果。main 仍需对同一 seeds 2003-2012 重跑；若候选没有新增
可执行动作，原 7 个跨区拒绝应转为诚实的 `no_executable_successor`，不得直接计为采用。

## 2026-07-29 区域后继同身份刷新

区域提示已经形成严格后继后，后续无新提示周期若绑定、联盟、未分配清单和权限作用域均
未变化，D3 继续使用原 `plan_id/version`。刷新精确继承原 owner、authority epoch、lease
及既有 assignment 权限字段；租约不会因评估周期推进而延长。`authority_epoch` 和
`lease_expires_at_s` 现属于计划执行签名，候选与同输入 R0 的不可区分判断也必须处于相同
权属作用域。

租约到期、owner 明确失活、同身份 epoch 篡改或 fault generation fence 均失败关闭。绑定
或联盟发生变化时仍发布严格新计划，不能用 evaluation refresh 隐藏执行变化。main 已用
seed 2007 完整 episode 验证写盘：D6 runtime join 接受 4 条 ACK、77 条 binding 和 1 次
合法同身份 evaluation refresh，online truth 计数为 0。

模块验收为 A2 successor 专项 `16 passed`，区域提示/身份/围栏组合 `51 passed`，D3
全量 `618 passed, 1 skipped`。唯一 skip 仍是可选 OR-Tools；Matplotlib 三维导入警告为
既有环境提示。

## 2026-07-29 规划专用区域转移因果审计

D3 对 D4 规划专用区域转移补充了同输入三臂合同证据，未修改规划器实现。确定性夹具先
发布 source，再以相同下一时刻航迹、资源和前序计划构造不带提示且不发布的 R0，最后消费
合法区域提示构造 treatment。三份计划都通过规范
`AssignmentPlan.execution_signature()` 比较，计划号、版本、租约或 metadata 刷新本身
不作为干预。

具体结果如下：

- source 为版本 1，绑定集合为
  `{T-A->R-A0, T-B->R-B0, T-C->R-C0}`，3 条 assignment，未分配集合为空；
- 同输入 R0 为未发布的版本 2 候选，绑定集合为
  `{T-A->R-A0, T-C->R-C1}`，2 条 assignment，未分配集合为 `{T-B}`；
- treatment 为已发布的严格版本 2 后继，绑定集合为
  `{T-A->R-A0, T-B->R-A1, T-C->R-C0}`，3 条 assignment，未分配集合为空。

treatment 的规范执行签名同时区别于 source 和 R0。相对 source 的新增绑定为
`T-B->R-A1`；相对 R0 新增了 `T-B` 的目标覆盖，因此该后继不是只刷新
`plan_id/version/lease/metadata`。treatment 的 `previous_plan_id` 精确指向 source，
owner 保持 center，authority epoch 等于 source 版本，lease 截止为 10 秒。跨区许可仍为
1，来源绑定保护、区域 hold、资源不可用、备用余量、可达性和旧版本门限均沿用现有合同。

main 已在 `scalable_3d_simulation/tests/test_module_stack.py` 固化两项跨模块回归。永久
正例采用 20v20、8 区域、seed 29：source 17 条 assignment、3 个未分配目标；区域转移
`region-000 -> region-001`、数量 1 后，严格后继为 18 条 assignment、2 个未分配目标，
版本 1 递增到 2。在线真值使用为 0，D4 的 assignment、coalition、takeover 和 control
execution authority 均为 false。永久负例在 `t=2.0` 注入中心 fault generation 变化，
规划专用转移被阻断。

main 两项专项测试通过；scalable world 与 module stack 全量 `100 passed`，D4 全量
`794 passed`。D3 本次测试不导入 main 或 D4，因此这些结果作为已完成的跨模块合同证据，
不扩展为 D6 同键多 seed 非退化、学习策略收益或物理结果。

区域提示专项 `34 passed`，D3 全量收集 619 项，结果为
`618 passed, 1 skipped`。唯一跳过仍为可选 OR-Tools；既有 Matplotlib `Axes3D` 环境
警告不影响本项。

## 2026-07-30 A1 分配感知开发候选

D3 新增与旧行为克隆 bundle 并存的
`d3_a1_assignment_aware_cost_residual_policy_v1`。新入口只解析源数据中的 TRAIN 和
VALIDATION。优化器只读取 962 个 TRAIN 帧；检查点选择只读取 320 个 VALIDATION 帧。
内部 TEST 不参与本轮开发，外部正式种子 `1000-1019` 的读取计数为 0。

开发教师先用原始规则矩阵和需求槽 Hungarian 形成 R0，再从仍硬安全的历史绑定中选择
规则成本间隔最小的困难边。只有替代绑定降低历史换绑量、保持需求覆盖、满足 M-to-N
all-or-none、绑定对称差不超过 8，且原规则成本绝对差不超过 0.10、相对差不超过
0.002 时，才形成正类。其余帧的修正目标为逐元素零，绑定目标为 exact-R0。

模型使用边编码、帧上下文门和有界成本残差。输出仍为
`C_final=C_rule+alpha*tanh(delta_C)`，离散结果仍由现有需求槽 Hungarian 和安全投影
产生。模型不输出 plan、version、target id 或控制命令。所有 assist、authority、
assignment、runtime publication、control、physical、formal holdout 和 production
admission 权限为 false。

同输入独立训练两次后，模型、manifest 和 tree SHA-256 完全一致。所选第 7 轮检查点的
验证结果为：

- 教师正例安全换绑 `13/95`，教师绑定完全一致 `9/95`；
- 负类 exact-R0 `224/225`，比例 99.56%；
- 有效绑定的重复资源、硬边、M-to-N 完整性和版本违规均为 0；
- 79 帧因分布外、换绑数量或规则成本差超限失败关闭，矩阵和绑定均恢复 R0。

模型 SHA-256 为
`c185823bd9a4cf5363d17854385aeb74c340c8ac384327281d224a1097eb8206`，
manifest SHA-256 为
`ec9f93d668e1aa319f65fcda0d73adb0527f316a2d1880e93e88697b6468ad3d`，
tree SHA-256 为
`de7b627df9782d7d2577687f30d02d4faeeaf577ecc557c2b8d91dd6e7115dd9`。

该结果关闭“开发候选无法形成任何安全离散变化”的模块内 P1。来源独立评价、正式
holdout、收益、运行采用和物理闭环仍开放。旧正式 `0/20 eligible` 证据不改写。

2026-07-30 的 D3 全量测试共收集 624 项，结果为
`623 passed, 1 skipped`。跳过项仍是可选 OR-Tools。

## 2026-07-31 Opt-in 权威代际绑定

`AssignmentPlan.bind_authority_generation(authority_epoch,
lease_expires_at_s)` 为发布前显式绑定 API。epoch 必须是非负整数，lease 必须有限且严格
晚于计划 `created_at`。首次调用返回保持相同 `plan_id/version` 的新冻结对象，并在
metadata 同时写入 `authority_epoch`、`lease_expires_at_s`、
`regional_max_epoch` 和 `regional_min_lease_expires_at_s`。原对象不变；同值重复调用
返回同一对象；已绑定身份改 epoch 或 lease 立即抛出 `ValueError`。四个字段均进入
`authority_signature()`。

默认 `AssignmentPlanner.plan()` 不生成 epoch 或 lease。main 对默认已在 planner 内部
发布的返回值做后置绑定时，必须使用
`AssignmentPlanner.bind_published_authority_generation(...)`：

```python
plan = planner.plan(tracks, resources, timestamp)
plan = planner.bind_published_authority_generation(plan, epoch, lease)
next_plan = planner.plan(
    next_tracks,
    next_resources,
    next_timestamp,
    previous_plan=plan,
)
```

planner 级入口同时更新内部已发布对象和可信 execution signature，避免下一轮
`previous_plan` 被误判为语义不一致。同身份 evaluation refresh 只继承原绑定，即使评估
时刻已超过 lease 也不续租；assignment、联盟、owner 或其他执行语义变化时，新身份保持
未绑定，main 必须显式绑定新的代际。只调用 plan 级 API 后再把副本传回已缓存未绑定签名
的 planner 是不安全顺序。

authority fence 和普通执行变化的新身份会移除旧四键。secondary takeover/continuation
也移除旧四键，但保留该身份新生成的 `secondary_leader_epoch` 和
`secondary_lease_expires_at_s`；绑定值必须与二者完全一致。regional authority 或
regional-hint successor 不继承旧 `authority_epoch/lease_expires_at_s`，其
`regional_max_epoch/regional_min_lease_expires_at_s` 则由当前 grant/successor 重新
生成，供 main 选择同一身份的 epoch/lease，planner 级绑定再补齐并校验四键。secondary
helper 的安全顺序是 `prepare/continue`、`publish_plan()`、planner 级绑定、外部发布。

2026-07-31 验证场景为 plan identity 单元合同和 D3 全量回归。身份专项
`28 passed`；全量收集 669 项，结果为 `668 passed, 1 skipped`。唯一跳过项是未安装的
可选 OR-Tools；既有 Matplotlib `Axes3D` 警告不影响结果。本 API 不选择 authority、不
签发或续租，也不改变 Hungarian、需求槽或迟滞。
