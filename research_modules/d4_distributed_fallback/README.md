# D4 分布式协同与降级接管

## 2026-07-29 readiness v3 不可变登记

main 已从 clean commit `8421de138442c17e379cd09d27e2e36c110652e0` 对 readiness v2
执行 5v5/2-region development preflight。运行总线通过，3/3 帧均在模型推理前返回
`runtime_confidence_gate_context_mismatch`。main 的实际
`RegionResourceProjectionConfig` 为最小备用比例 0.1、最小备用资源 1、建议有效期
1.5 秒；v2 bundle 固定的建议有效期为 1.0 秒。在线真值使用数为 0，
`formal_decision` 未改变投影。v2 保留为不可变失败证据，不覆盖、不重写。

D4 已实现独立候选
`region_resource_a2_8region_runtime_action_readiness_shadow_v3`，模型版本为
`d4-region-a2-8region-runtime-action-readiness-shadow-v3`。v3 配置、来源摘要、训练视图、
训练摘要和 bundle 运行门统一绑定 1.5 秒投影合同，同时固定最小备用参数、规则权重
2.0/0.5/0.05、分布外余量 0.05、置信度门限 0.60、不一致封顶 0.59 和连续动作容差
0.10。默认训练配置和运行门内容 SHA-256 分别为 `e8ce37c4...0592` 和
`77972834...6872`。1.0 秒上下文、混用 v2/v3 identity、配置或哈希篡改均失败关闭。

main 已在 detached clean worktree commit
`4ba2c8a649dab157d55a2dd7817d5a8ded494114` 构建 v3。D4 独立 review 后将 8 个文件逐字节
登记到 `model_registry/region_resource_a2_8region_runtime_action_readiness_shadow_v3/`。
候选 manifest 文件/内容、模型、源码身份、复合数据、split、运行门和登记树 SHA-256
分别为 `5e575ec4...59c3`、`7978aec0...ada2`、`ace5df6d...7f52d`、
`e260ff2f...4ef`、`5d174dd3...ee03`、`69ae1b0e...d817`、
`77972834...6872` 和 `07c770b0...a93a`。源目录与 registry 逐文件相同，v2 树摘要仍为
`324a5118...5010`。

validation 门后通过 293/344，动作不一致通过 0，动作一致率 1.0，Brier 为
0.056837453793788656；在线 truth、test payload、calibration seed 和保留 seed 使用数均为
0。v3/v2 registry 联合专项 13/13、D4 全量 754/754 passed。v3 尚未执行 main runtime
preflight，也未运行正式 seed。development/read-only shadow 边界不变；assist、
assignment、takeover、coalition、control、physical、runtime ACK 和 formal evaluation
权限全部为 false。

## 2026-07-28 readiness v2 不可变登记

readiness v2 已由 main 在 detached clean worktree commit
`891b542337ef065eee8c794d38dfa6ba382fea9e` 完整构建，并逐字节登记到
`model_registry/region_resource_a2_8region_runtime_action_readiness_shadow_v2/`。候选
manifest 文件/内容、模型权重和源码身份 SHA-256 分别为
`c3194c90...af72b`、`48148034...3852f`、`ace5df6d...7f52d` 和
`331b4f29...92ce0`。复合数据和全局 seed split 为 `996dbd66...493e`、
`69ae1b0e...d817`。登记目录八个文件与 clean-build 源目录的相对路径和逐文件 SHA-256
完全相同，旧 v1/current-lineage 候选未覆盖。

第三个 `secondary_readiness` 补样源继续绑定 commit `9a1f6fc9...c763`、manifest 文件
`a1056c72...f0c2` 和数据内容 `34244f1f...c56`。三来源复合视图包含
1100 episode、2297 frame 和 8 个区域；数字 seed 0-99 跨来源原子切为
70 train、15 validation、15 untouched test，1000-1019 使用数为 0。test payload、
校准 seed 和保留 seed 使用数均为 0。

候选使用运行时确定性一致性门。bundle 内容寻址绑定 Advisor 的投影器、规则策略、全部
配置、分布外余量 0.05、置信度门限 0.60、不一致封顶 0.59 和连续动作容差 0.10。validation
的 344 个样本中，原始置信度 344/344 越过 0.60，其中动作不一致 51 个；运行门后
293/344 越过 0.60，动作不一致通过数为 0，通过样本动作一致率 1.0，Brier 分数为
0.056837453793788656。在线规则参考与记录标签 mismatch 为 0，
`confidence_calibration_accepted=true`。validation 标签只用于统计，不参与逐样本置信度
修改。

`RegionResourceAdvisoryResult.runtime_confidence_gate_diagnostic` 可序列化原始推理、
门应用、动作一致性、原始/有效置信度、门后许可和门拒绝规则回退。该诊断是 main runtime
preflight 的只读输入，不授予 assist、分配、接管、联盟、控制或物理权限。登记专项
**3/3**、v1/v2/运行门联合专项 **37/37**、D4 全量 **743/743 passed**；仅有既有
Matplotlib `Axes3D` 环境警告。

main runtime preflight 后续已执行但未通过：实际 1.5 秒建议有效期与 v2 固定的 1.0 秒
合同不一致，3/3 帧失败关闭。正式评价保持关闭。候选仍为 development/read-only shadow；
assist、assignment、takeover、coalition、control、physical、runtime ACK 和 formal
evaluation 权限全部为 false。

## 2026-07-28 八区域复合候选与置信度校准

D4 已构建新的 8-region 专用候选
`region_resource_a2_8region_runtime_action_shadow_v1`。运行数据
`b06d741b...6158` 提供 900 episode/1798 frame 的八区域特征几何；动作课程
`7e17aba7...e72` 只提供 hold、request-replan、非零配额和转移配方。课程动作在运行快照
上重新生成，并由现有规则策略和确定性安全投影形成标签。复合视图为 1000 episode/2098
frame，数字 seed 0-99 按 70/15/15 全局原子切分，seed 1000-1019 使用数为 0。候选适用域
严格限定为 8 区域，2 区域输入按图级 OOD 失败关闭。

该候选采用独立的置信度训练阶段。动作模型训练结束后冻结，只更新
`confidence_head`。置信度目标来自模型动作与规则加安全投影标签之间的配额、备用、
侦察优先级、hold/replan 和转移误差；动作不一致样本的目标上限固定为 0.59，运行门限仍为
0.60。训练只使用 train，validation 只做审计，test、保留 seed、真值标识和未来结果使用
数均为 0。

验证集 315 个样本的 Brier 分数由 0.258170 降至 0.021107，但校准后 315/315 均越过
0.60，其中 51 个不满足动作一致性条件，门后动作一致率为 83.81%。该证据不足以接入运行
链。manifest 固化 `confidence_calibration_accepted=false`，shadow 适配器将
`candidate_failure_gate_passed` 置为 false，并记录
`candidate_confidence_calibration_not_accepted`。一个八区域代表帧的
`feature_ood=false`、置信度 0.909641、`gate_pass=false`、
`identifiable_nonzero=false`，实际执行继续使用规则回退。

候选由 clean detached checkout
`923f3f6e91af0f85aed446c66420c834d2de63fb` 构建。manifest 文件/内容、模型权重、
源码身份、bundle manifest、复合数据和全局 split SHA-256 依次为
`ad5846b1...f5e5`、`52866167...e2f`、`43157f4e...b0ee`、
`f9c52715...53ed`、`824aecf1...b8f`、`ee6bd202...cfd4` 和
`69ae1b0e...d817`。2026-07-28 最终 registry 专项 **14/14**、D4 全量
**720/720** 通过；仅有既有 Matplotlib `Axes3D` 环境警告。模块测试不授予正式评价权限。

main 随后完成两组 development preflight。5v5/2 区域 seed 2000 共 3 帧，分布内
0/3，raw model execution 0；阻断项为 `runtime_feature_distribution_mismatch`、
`no_nonfallback_model_evaluation`、`candidate_region_count_out_of_scope` 和
`candidate_confidence_calibration_not_accepted`。200v200/8 区域 seed 2001 共 3 帧，
分布内 1/3，raw model execution 1，candidate-permitted execution 0。后者 2 帧 OOD 的
唯一越界特征是 `secondary_readiness`：训练范围为 [1.0, 1.0]，运行范围为 [0.0, 1.0]，
24 个节点值中 16 个低于训练下界。两组有限值检查均通过，在线真值使用数均为 0。

双源重切分已将 raw execution 从 0 提高到 1，但运行分布仍未闭合。下一候选需补采真实
8-region、`secondary_readiness=0` 的运行帧，并修复 315 个验证样本中 51 个动作不一致
却越过固定 0.60 的校准误接收。候选许可、assist、分配、接管、联盟、控制和物理权限保持
false；正式 20-seed/900-cell 继续禁止。

## 2026-07-28 当前谱系影子运行边界

D4 已为冻结的 current-lineage development/shadow 候选增加只读运行适配器和独立
verifier。候选固定绑定 clean commit `b0d498d9...`、manifest
`7cc10ad7...de64`、权重 `fd1b9c4c...0047` 和源码身份 `b81780ce...dfdf`。每帧记录
episode/seed/frame、输入摘要、原始模型动作、确定性安全投影、非零分类、拒绝原因以及逐
节点/逐边/逐特征 OOD 详情。实际执行源始终为规则回退；D3 后继计划、runtime/owner/
coalition ACK、物理窗口、R0、收益和全部运行权限不可由该适配器生成。

候选原始字节现已登记到
`model_registry/region_resource_a2_current_lineage_development_v1/`。manifest、源码/
数据/训练摘要、配置和 bundle 三个文件与原 `outputs/` 候选逐字节相同。冻结适配器可直接
从该路径加载，因此 clean clone 不再依赖被 gitignore 的本地输出。登记只解决来源复现，
不改变候选权限和运行适用性。

main 的 5v5/2 区域 3 帧和 200v200/8 区域 2 帧预检均为 `feature_ood`，模型实际执行
0/5，在线真值使用 0。当前候选只完成可信加载和影子适配，不具运行分布兼容性，正式
20-seed 阻断，`ood_margin=0.05` 不变。900-episode 运行数据与 100-episode 动作课程的
特征 union 可覆盖 200v200/8 区域主要范围，但两个来源的数字 seed 0-99 必须全局原子
重分割；1000-1019 完全排除。5v5/2 区域的边距离仍未覆盖。新候选需在 clean checkout
重建，本轮未重训。专项 **17/17**、D4 全量 **706/706** 通过。完整证据见
`reports/D4_A2_CURRENT_LINEAGE_SHADOW_RUNTIME_BOUNDARY_20260728.md`。

## 2026-07-28 A2 当前实现谱系实物

D4 新增独立的当前谱系候选构建与复核入口。入口先检查整个 Git 工作区必须干净，再绑定当前
提交、树对象、区域策略/数据集/模型/训练/候选构建五个实现文件摘要。构建只读取既有
`train` 和 `validation` episode；训练参数只由 train 更新，早停和模型选择只使用
validation。数据集 test payload、旧 calibration 和 seed 1000-1019 的读取与使用数固定为
0。

候选 manifest 同时绑定源码摘要、数据集 manifest/内容/split 摘要、训练配置、训练摘要、
模型 manifest、模型权重和内嵌训练数据 manifest。严格复核会重新检查 clean worktree、
当前源码、原数据集、切分目录、模型参数和 validation 推理有限值。工作区脏、源码摘要变化、
切分重叠、非有限输出、制品篡改或任何权限字段为 true 时均失败关闭。

五 seed 临时开发夹具已通过真实 CLI 构建和加载：3 train、1 validation、1 untouched test，
验证非有限输出为 0。该夹具只证明软件入口可用，明确标记 development/shadow；A2 准入、
实际采用、收益、分配、接管、联盟提交和控制权限全部为 false。此前主工作区的严格检查按
预期返回 `source_worktree_dirty`，没有用该工作区伪造 clean 结论。

main 提交后，D4 已从独立 clean checkout
`b0d498d9e76e19e9045e127b6dae26ea164b3fa4` 执行实际构建和 `review-only`。候选
manifest 文件 SHA-256 为 `7cc10ad7...de64`，模型权重为 `fd1b9c4c...0047`，数据集和
split 分别为 `7e17aba7...2d7f0`、`b413fa81...0c16`，源码身份为
`b81780ce...dfdf`。复核确认 clean lineage、bundle 可加载、validation 60 个样本均为
有限输出，test/calibration/reserved seed 使用数为 0。

固定门限的 train/validation 开发诊断直接调用实际模型。训练集 180 个样本中 168 个为安全
非零动作、12 个与基线相同；验证集 60 个样本中 54 个为安全非零动作、6 个与基线相同。
两组资源不可行、模型身份错配、非有限输出和候选门回退均为 0。训练集参与参数更新，验证集
参与模型选择，因此这些结果只证明当前谱系 development 模型没有在已见开发分布上退化为
全 no-op，不属于正式未见 seed、准入、实际采用或收益证据。

2026-07-28 新增专项 **8/8 passed**，D4 全量 **697/697 passed**。构建命令、完整摘要和
证据边界见 `reports/D4_A2_CURRENT_LINEAGE_CANDIDATE_DIAGNOSTIC_20260728.md`。当前剩余
P1 是冻结该实物后完成至少 20 个正式未见 seed 的实际非零干预、严格 D3 后继计划、
runtime/owner/coalition ACK、确认后物理窗口、独立同键 R0 和 D6 配对非退化审计。不得
回看正式结果调参或放宽门限。

## 2026-07-27 A2 实际模型干预诊断

D4 新增实际区域策略开发诊断，不再用受控适配器的规则派生动作代表模型能力。诊断器只读取
冻结 development 候选和候选清单指定的独立校准种子，逐区域记录原始动作、固定置信门、
分布外门、owner/plan/epoch/lease、资源可行域、安全投影和 D3 可消费字段。训练、验证、
校准和保留种子目录必须互斥；固定最低置信度 0.60 和分布外余量 0.05 均不能由诊断入口
修改。动作分类固定使用 0 ms 功能性时延覆盖，避免主机调度抖动改变分类；运行时 50 ms 门
配置未改变，本报告不提供时延性能证据。

本地候选 `region_resource_a2_development_calibrated_20260726_v1` 的 20 个校准种子共
420 个样本已完成诊断。420/420 通过候选固定门，置信度 min/mean/max 为
0.707421/0.972089/1.000000。实际模型产生
76 个安全、非零、可归因区域建议；其中动作覆盖课程 60 个，延迟噪声场景 16 个。非零字段
累计包括整数备用资源 197、请求重规划 40、资源配额 40、保持 20 和跨区转移 20。

其余 344 个样本在安全投影后回到无操作。360 个样本至少有一个区域出现“正备用请求超过
当前可行备用量”；其中 16 个样本仍由其他动作形成非零干预。主要原因是备用比例头经
Sigmoid 输出严格正值，整数向上取整后会请求至少 1 个备用资源，而部分区域的可用资源已被
任务全部承诺，确定性投影只能把该请求压回受保护基线。本批有 88 种原始可执行动作签名，
因此没有发现整批策略输出塌缩；低置信、分布外、owner/lease/epoch、动作掩码和非有限输出
拒绝均为 0。

该结果关闭“历史 development 模型是否能在互斥开发校准样本上产生非零动作”的诊断缺口，
当时不关闭当前谱系开发证据、正式采用和收益 P1。候选清单以 SHA-256
`d3c96f0...36a2` 显式锚定，其实现谱系与当前代码不一致。当前谱系实物与非零开发诊断现已
由本文件首节补齐；该历史 calibration 结果仍不能并入当前候选或用于调节门限。
seed 1000-1019 使用数仍为 0。严格后继计划、owner/coalition ACK、物理窗口、独立同键 R0
和 D6 非退化审计尚未形成。assist、assignment、failover、control、正式证据、实际安全
采用和系统收益权限全部为 false。

实现入口为 `region_resource_actual_policy_diagnostic.py`，命令入口为
`scripts/run_region_resource_actual_policy_diagnostic.py`。紧凑审计结果位于
`reports/region_resource_a2_actual_policy_calibration_20260727_v1/`。专项 10/10、D4 全量
**689/689 passed**；两次重跑的逐 seed 分母、76/344 分类、样本身份摘要和分类摘要一致。
唯一警告为既有 Matplotlib `Axes3D` 环境提示，未运行 AirSim。

## 2026-07-27 提交就绪复核

本轮收紧了 A2 安全采用边界。联盟成员 `can_execute` 只接受布尔值，成员确认和联盟提交
时间只接受有限非负数；字符串 `"false"` 和非有限时间不再可能穿过确认门。安全采用
preparation/evidence 的可用性与权限字段改为严格布尔值，不可用 preparation 不能携带已应用
建议。通信回执和期望从映射加载时要求版本化字段全集完全一致，并拒绝额外真值字段。

中心、二级和完全分布式 owner 均通过同一安全采用链回归。三层正例只证明证据链可用，
`authority_granted`、A2 收益和在线真值使用保持 false。开发适配器的策略身份现在从正式
收益审计入口即被拒绝。2026-07-27 D4 全量结果为 **679 passed, 1 warning**；警告是既有
Matplotlib `Axes3D` 环境提示。关键文件语法检查和 D4 scoped `git diff --check` 通过。

## 2026-07-27 A2 开发态非零干预探针

D4 新增 `ConstrainedDevelopmentRegionResourceAdapter`，用于解决学习 development 候选在
开发配对中持续输出零动作、导致后续合同无法被测试的问题。适配器只包装已有
`source=learned` 的未投影候选；候选原本已有可消费动作时保持原样，候选为无操作时才从现有
确定性规则策略提取一个最小干预。该干预明确标记为
`development_test_only_intervention`，不能归因于模型。

“原本已有可消费动作”现在按投影后的 D3 消费语义判断。适配器与规则策略共享同一个
`DeterministicResourceProjector`：先投影候选、构造 advisory、执行同 snapshot 消费检查，
再复用安全采用链的干预证据口径。原始 `reserve_ratio` 看似变化，但因 committed resource、
最低备用或可行域约束在投影后回到基线时，候选仍按无操作处理，不再提前返回。

适配器声明 `formal_decision_aware=true`。`RegionResourceAdvisor` 只对该显式协议传入当前
formal decision；适配器选择动作时和 advisor 发布建议时均使用同一正式裁决投影。默认
`force_request_replan_on_projected_noop=false`。开发探针显式打开该项后，即使规则策略在
“全部资源已承诺、无 deficit、无 transfer budget、无安全 hold”场景返回无操作，也只会在
权威、ACK、fault fence 和租约均有效的一个区域发出 request-replan-only。

候选选择顺序固定为：

1. 优先在权威和租约仍有效的区域输出单区域 `request_replan=true`，不同时输出 `hold` 或
   transfer。
2. 没有合法重规划请求时，输出受 `maximum_total_transfer_resources` 限制的最小跨区转移。
3. 前两项均不可用时，只允许 `committed_resources=0` 的区域进入 `hold`；已承诺区域不进入
   hold 候选。

每一级候选都重新经过上述投影和消费判定。投影后仍是无操作或出现投影/发布/消费拒绝时，
适配器继续尝试下一优先级；所有候选均不可消费时返回原始候选，由正式链路失败关闭。

适配器不修正候选的 owner、plan、version、epoch 或 lease，也不直接发布 advisory。输出仍
必须经过 `DeterministicResourceProjector`、正式 D4 裁决和
`RegionResourceSafeAdoptionAssembler`。旧时期、过期租约、网络分区、容量、备用资源和
D3 held-assignment 安全拒绝均未放宽。

该适配器没有 admitted manifest，最大建议模式固定为 `shadow`，assist、authority、control
和模型准入均为 false。正式 A2/R0 收益审计还会按策略身份返回
`development_intervention_benefit_forbidden`。它只能生成开发链路证据，不能生成模型收益
证据。

main 提供的原 hold+request helper 内存探针为 15/20；seed
1000、1002、1007、1009、1013 因固定区域已有 committed binding，依次停在
`regional_hint_no_executable_successor` 和 `regional_hint_held_assignment_infeasible`。
D4 已把这五个 seed 加入回归。新候选对它们只输出 request-replan，不输出 hold，均形成可
辨识干预并停在 `awaiting_d3_plan / d3_successor_plan_missing`。这只是 D4 模块合同结果，
main 尚需重跑同一 20-seed 内存探针。

验证日期为 2026-07-27。新增单样本回归把 3 个区域资源中的 2 个设为 committed，原始
`reserve_ratio=0.6` 表面对应 2 个备用资源，投影后受可行域限制回到基线 1 个备用资源。
原候选被正确识别为无操作，适配器继续生成一个 request-replan-only 候选；投影后的
`identifiable_intervention_available=true`，hold 和 transfer 均为空。另一单样本确认
formal-only committed member 会参与适配器首次投影。安全采用专项 **68/68 passed**，
D4 全量 **674/674 passed**，仅有既有 Matplotlib `Axes3D` 环境警告。

同日使用真实适配器和 development-only admitted transport 夹具完成 1 次内存 full episode：
5 target/5 resource/1 recon/2 region、3.0 s、seed 1、radar detection probability 0.45。
结果为 1 条 A2 记录，stage=`physical_window_available`，可辨识干预、安全采用和物理窗口
均为 true，`regional_hint_successor_state=successor_published`，在线真值使用为 0；
`authority_granted=false`、`a2_benefit_available=false`。未运行 AirSim。标准 advisor 仍把
该适配器限制为 shadow；上述夹具结果不构成模型准入、收益或生产权限结论。

## 2026-07-27 A2 无操作建议归因修正

D4 现将区域资源建议分成三层证据：建议经过确定性投影并被消费、建议产生可辨识的区域资源
干预、该干预被后继计划和物理执行采用。第一层只证明链路可达，不能直接计为学习动作采用。

可辨识干预由 D4 根据投影后建议独立重算。当前计入项为逐区域资源配额变化、跨区域转移、
按整数资源计算的备用资源变化、`hold` 和 `request_replan`。资源守恒时
`total_quota_delta=0` 很常见，因此不能单独作为无操作判据。侦察优先级尚未进入 main 到 D3
的可执行提示接口，也不计为当前 D3 可消费干预。

无操作建议仍可生成投影/消费链路证据，但 `assemble()` 在读取普通 D3 后继计划之前返回
`safe_adoption_rejected`，原因为 `identifiable_regional_intervention_missing`。后继计划、
运行确认、所有者确认、联盟提交和物理窗口均不得附着到该记录。收益审计入口也要求非空干预
字段，因而不能把同期常规 D3 重规划归因于 A2。

main/D6 已于 2026-07-27 按该口径完成 20-seed 开发批次重算。正确统计为：投影/消费链路
20/20，可辨识区域资源干预 0/20，实际 A2 动作采用 0/20，A2/R0 收益审计 0/20；20 个拒绝
原因均为 `identifiable_regional_intervention_missing`。批次 SHA-256 为
`ff3c10a089b6a94582451ae05d8a884af3a2bd7485acd4df0496442ea7e0ec55`。此前 18 个
`safe_adoption_available=true` 只反映普通计划升版与链路可达，已被本次正确结果取代，
不是模型动作采用。assist、分配、接管和控制权限继续全部为 false。

验证日期为 2026-07-27。安全采用专项 **52/52 passed**，包括“同期存在无关后继计划也不能
把无操作建议转为采用”的负例。运行时集成专项 **6/6 passed**：无操作链停在
`no_successor` 且不刷新 authority/lease；真实 `hold/request_replan` 干预形成新计划标识、
严格更高版本、正确 `previous_plan_id` 和 `new_execution_plan_applied`。D4 全量
**658/658 passed**。本轮没有运行 AirSim。

## 2026-07-27 A2 同键规则参考审计合同

D4 已增加独立的 `region_resource_a2_benefit_audit.py`。该合同位于在线安全采用证据和 D6
收益计算之间，本身不扩大 `RegionResourceSafeAdoptionEvidence` 的权限。安全采用记录先
通过上述非空干预门，再证明候选建议绑定严格后继计划、运行确认、当前所有者确认、必要联盟
提交和物理执行窗口；其中 `a2_benefit_available=false`、`authority_granted=false` 保持
不变。

每个配对审计输入显式携带 comparison key、场景及版本、规模、seed、逻辑窗口标识和
`paired_exogenous_config_sha256`。候选 A2 臂必须哈希绑定安全采用记录及其建议、计划和物理
窗口；规则 R0 臂必须使用冻结的 `d4-region-resource-rule/v1`。两臂必须来自独立
execution arm、独立 episode 事件日志和不同物理窗口载荷，同时具有相同外生配置摘要和逻辑
时间窗。跨 key、窗口复用、事件日志复用、重复 R0、版本错绑、窗口时长不一致、计划或租约
过期、窗口不完整和硬约束违规均失败关闭。

main 可直接传入进程内安全采用对象，也可从 episode 持久化的
`learning_adoption_evidence.json` 读取完整 A2 记录后离线组装。持久化路径会重新计算原记录
内容 SHA-256，再提取候选建议、严格后继计划和物理窗口绑定；不要求候选和 R0 在同一进程
运行。事件日志摘要由 main 绑定 episode identity，外生身份优先使用场景 metadata 中的
`paired_exogenous_config_sha256`。

输出只允许设置 `d6_benefit_audit_input_allowed=true`。合同不携带结果指标，不计算
non-degradation 或最终收益，也不授予模型、A2 assist、分配、故障接管或控制权限。批量
合同还会拒绝 comparison key、R0 窗口、R0 事件日志和 R0 execution arm 的重复引用。

验证日期为 2026-07-27。安全采用专项 **50/50 passed**，D4 全量 **655/655 passed**。
测试覆盖进程内与持久化记录等价、严格往返和内容哈希，以及缺失、篡改、跨键、重复、日志
复用、窗口复用、过期、不完整、时长不一致、硬约束和真值字段负例。结果来自纯 Python 合同
fixture，未启动 AirSim，也未形成实际双 episode R0 或收益证据。下一步由 main 生产独立
A2/R0 episode，由 D6 读取事件日志并计算收益；正式权限继续关闭。

## 2026-07-27 A2 确认收据后续引用

`CausalCommunicationEvidenceGate` 已修复同一不可变确认收据在后续物理窗口评估中被误判为
跨证据复用的问题。收据绑定身份现在由消息类型、源节点、目的节点、权威所有者、消息标识、
计划版本、时期号、租约范围、分区代次和载荷 SHA-256 共同确定；评估时刻不再进入该不可变
绑定身份。一个已经接受的 owner 或 coalition ACK 可在同一绑定链中被更晚的安全采用评估
再次引用。

后续引用仍重新执行时间门控。评估时刻必须不早于该绑定已处理的最新时刻，消息必须已到达，
评估必须发生在租约到期前。时间回退返回 `decision_timestamp_rewind`；租约到期返回
`lease_expired`。改变 expected message、目的节点、载荷摘要、计划、时期、租约或分区代次
仍返回 `receipt_reused_for_different_evidence`；同一 receipt ID 对应不同收据内容仍返回
`receipt_conflict_replay`。验证结果继续固定 `authority_granted=false`。

2026-07-27 的正向回归先在 `t=2.05 s` 验证 owner ACK 并停留在
`awaiting_physical_window`，再于 `t=2.30 s` 使用同一收据装配物理窗口，结果进入
`physical_window_available`。通信与安全采用专项 **99/99 passed**，D4 全量
**637/637 passed**。这些结果来自纯 Python 合同 fixture，不是 AirSim、真实网络或 A2 收益
证据；same-key R0 仍未形成。

## 2026-07-27 A2 所有者确认公共合同

D4 已补齐 main runtime 可直接调用的 A2 所有者确认和联盟成员确认公共接口。生产
`runtime.assignment_plan_ack` 经 `RegionResourceRuntimeAckParser` 验证后，除原有 D3/D7
计划与导引摘要外，还保留该确认载荷的 SHA-256 和确认 envelope 的总线序号。当前二级或
对等所有者生成的 `RegionResourceOwnerPlanAck` 必须同时绑定权限所有者和层级、时期号、
租约、分区代次、建议谱系、D3 严格后继计划 ID/版本/载荷摘要/总线序号，以及 main 运行时
确认载荷摘要和总线序号。发送时间由确认对象记录，实际到达时间由
`CommunicationDeliveryReceipt` 记录。

公共调用入口如下：

- `build_region_resource_owner_plan_ack()`：从已投影建议、D3 后继计划、运行时确认和当前
  context 构造期望确认，不要求 main 重复填写交叉绑定字段。
- `RegionResourceOwnerPlanAck.from_transport_payload()`：严格解析
  `d4.regional_plan_owner_ack.v1` 的 payload，拒绝缺字段、额外字段和别名不一致。
- `RegionResourceOwnerAckDelivery.from_delivered_message()`：从实际 delivered message
  解析 payload，并调用 D4 内容寻址回执工厂。
- `RegionResourceCoalitionAckDelivery.from_delivered_message()`：严格解析嵌套
  `CoalitionMemberAck`。该嵌套对象沿用现有
  resource/global-track/coalition/plan/epoch/can-execute/evidence-time/valid-until 字段，
  未增加虚构字段。
- `validate_region_resource_owner_ack_delivery()` 和
  `validate_region_resource_coalition_ack_delivery()`：复核内容寻址回执、source、
  destination、topic、payload 摘要、计划代次、租约、双时间戳和分区代次。结果固定
  `authority_granted=false`。

安全采用顺序保持为：学习候选通过确定性投影，D3 发布严格后继计划，main 发布并验证运行时
计划确认，当前所有者确认实际到达，需要联盟时全部必要成员确认并原子提交，最后形成不含真值
和奖励的物理执行窗口。缺运行时确认、所有者确认、联盟提交、物理窗口或同键 R0 时保持
unavailable。确定性规则回退不计为 learned adoption。

验证日期为 2026-07-27。所有者/运行时/通信/联盟四文件联合回归 **130/130 passed**，D4
全量 **626/626 passed**。验收门限为公共正例全部通过、篡改运行时确认摘要或联盟嵌套字段
全部失败关闭、权限授予数为 0。测试为纯 Python 合同 fixture，未运行 AirSim、真实网络或
新随机种子；main 尚未生产真实 owner ACK、采用后物理窗口和同键 R0，正式 A2 采用仍为
0，收益仍不可用。

## 2026-07-26 A2 安全采用生产合同

D4 新增 `RegionResourceSafeAdoptionAssembler`，用于连接真实学习候选与既有 A2 最终证据
装配器。该合同不改写 `region_resource_a2_evidence.py` 的 20 个实际采用、同键规则基线、
物理窗口、配对非退化和联盟完整性要求。它只负责生成并核验最终装配器之前的单次采用证据。

采用分为两个阶段。`prepare()` 只接受 `source=learned`、没有规则回退标记、模型摘要有效且
置信度不低于冻结门限 0.60 的候选。候选经过现有确定性资源投影后，继续检查区域邻接和容量、
保留与已提交资源、正式 D4 所有者、计划版本、时期号、租约、中心/二级/对等节点优先级和网络
分区。通过后生成 `RegionResourceAppliedRecommendation`。该对象仍固定
`execution_authority_granted=false` 和 `a2_benefit_claimed=false`。

`assemble()` 要求 D3 严格后继计划引用同一建议标识、版本和载荷摘要，并核对计划总线序号及
载荷摘要。随后验证现有 `new_execution_plan_applied` 运行时确认、二级或对等所有者通过
`d4.regional_plan_owner_ack.v1` 实际投递的确认、必要联盟的全部成员确认及执行态提交，以及
租约内的物理执行窗口。所有者确认、联盟确认和物理窗口均以内容寻址摘要绑定后继计划。缺计划、
缺确认、旧版本或时期、过期租约、非法转移、容量超限、网络分区、联盟不完整或物理窗口缺失时，
输出明确的 `awaiting_*` 或 `safe_adoption_rejected`，不形成可用采用证据。

在线输入递归拒绝真值、结果和奖励字段。混合所有者区域必须由 main 按权威域拆分，D4 不跨域
声称原子采用。即使全部采用证据完整，D4 也只输出 `safe_adoption_available=true`；
候选相对规则基线的收益仍由 D6 带外验证，同键规则基线和 20 个正式采用仍由既有 A2 装配器
强制检查。

2026-07-26 模块专项 **27/27 passed**，与通信因果证据和既有 A2 装配器联合测试
**100/100 passed**，D4 全量 **621/621 passed**。这是纯 Python 合同与单元测试结果。本轮未
运行 AirSim、真实网络或正式多随机种子试验；现有 main 隔离制品仍为
`candidate_considered=false`、`execution_source=deterministic_rule_fallback`，因此真实
学习候选采用数仍为 0，不能宣称 A2 收益或开放 assist、PPO、默认模型和运行权威。

## 2026-07-26 A2 证据装配合同

D4 已实现版本化 `d4-region-resource-a2-evidence-bundle-v1` 装配器、严格加载器和命令行
入口。原 `d4-region-resource-model-bundle-v2` 继续作为不可变的
`development/shadow` 内层；装配器只在新目录发布外层证据包，不修改原 manifest、权重或
训练清单，也拒绝覆盖已有输出目录。

外层包要求同一候选的开发 manifest/权重、训练数据身份、当前实现摘要、D6 外部审计、
seed 1000-1019 的 20 个未见 seed 正式 scope 及精确 `SHA256SUMS`、逐 seed 运行证据全部
闭合。每条运行证据必须证明候选置信度不低于 0.6，实际通过安全投影并被采用，D3 生成严格
更高版本后继计划，runtime ACK 有效，owner/node/epoch/lease/fault generation 当前，联盟
全部必要成员已确认并进入执行态，ACK 后物理窗口可用，同 comparison key 只有一个 R0，
配对指标非退化且硬约束违规为零。nominal 回退和 `active_risk` 规则臂都不能冒充学习采用。

成功装配只授予 `a2_assist_eligible=true`。`default_model`、`ppo_enabled`、模型晋级、
故障接管权、分配权和控制权均保持 false，规则回退保持必需。严格加载器重新计算精确文件
清单、全部文件和 JSON 内容摘要、候选指纹、实现谱系及跨证据绑定；额外文件、额外字段、
旧 epoch、过期 lease、权限误开或任一摘要不一致均失败关闭。

2026-07-26 的合成完整 fixture 验证装配与严格加载正向路径，专项 **17/17 passed**；
runtime ACK、配对干预、结果证据、联盟安全和候选合同联合回归 **124/124 passed**；D4
全量 **594/594 passed**。这些是软件合同测试，不是正式模型性能证据。

当前实物路径仍拒绝装配。实际 development bundle 与 D6
`d4_a2_external_audit_actual_20260726_final` 组合返回
`d6_external_audit_fail_closed`；原 manifest、权重、训练清单 SHA-256 前后分别保持
`dad2adbe...c05c9`、`3da0360b...d5f62`、`ff3081c8...30dc6`，没有生成外层包。仍缺当前
实现 evidence、正式 20-seed scope 及校验清单、候选实际安全采用、D3 严格后继计划、
runtime ACK、干预后物理窗口、唯一同键 R0、配对非退化和硬约束/联盟完整性证据。因此当前
候选没有获得 A2 assist 资格。

## 2026-07-26 A2 校准 development 候选

D4 已生成新版区域资源 `development/shadow` 候选
`region_resource_a2_development_calibrated_20260726_v1`。该候选合并正式 900
episode 与 clean supplemental 100 episode 的规范只读 60/20/20 视图；训练、验证和校准
分别使用 seed 0-99 中互不重叠的 60、20、20 个 seed。保留 seed 1000-1019 的使用数为
0，未参与训练、置信拟合、阈值选择或场景选择。

行为克隆使用动作平衡损失和补充课程重复采样，置信头只在 validation 正样本与合成分布外
样本上拟合；test 桶仅作独立校准，不调门限。校准 420 个样本中，候选
considered/gate-pass 为 **420/420**，置信度 min/mean/max 为
**0.707421/0.972089/1.000000**，推理时延 P95/max 为
**0.969215/1.294533 ms**。固定置信门仍为 **0.6**，固定时延门仍为 **50 ms**。
合成分布外样本 **420/420** 被硬门拒绝。

校准桶的后投影动作覆盖非零配额 40、跨区转移 20、hold 20 和 request-replan 40。
数据总目标动作清单为 15584 条，其中非零配额 200、transfer 100、hold 100、
request-replan 200。候选清单文件 SHA-256 为
`d3c96f0abf059d6726b4706f8380a59687d8635898253cfa04f0a8a61df036a2`，权重
SHA-256 为 `cf393eaa2e7777e63645ef244f8e9bf733123fdc768f2610a91954c5f6c4632f`。

该结果只证明新版候选具有动作多样性、固定门可通过且证据可绑定加载。候选仍固定
`lifecycle_stage=development`、`maximum_advisor_mode=shadow`，
`assist_enabled=false`、`authority_enabled=false`。正式保留 seed 降级试验、D3 严格后继
计划、运行消费 ACK、联盟成员 ACK、采用后物理窗、规则基线配对非退化和 D6 外部审计均未
执行，不能据此宣称系统收益、assist、生产 authority 或正式准入。

2026-07-26 D4 全量模块回归为 **577/577 passed**。本轮未运行 AirSim 或
reserved-seed 正式矩阵。

## 2026-07-26 A2 预准入证据装配盘点

本节记录新版校准候选形成前的盘点。当前候选状态和后续限制以上一节为准；旧冻结 bundle 和
历史 20-seed 结果继续保留为基线，不被新版产物改写。

当时的结论是：D4 已有多段严格证据合同，但尚不具备与“D6 外部审计 -> D4 证据装配器 ->
新 bundle”等价的完整链路。该软件缺口现已按页首关闭，真实证据缺口仍为 P1，不是 P0。
原安全判断的原因是
`d4-region-resource-model-bundle-v2`、loader 和 advisor 已共同把模型限制在
`development/shadow`；正式调用方不能用裸布尔、未绑定摘要、无 manifest 注入策略或
20 个未见 seed 自行进入 assist。测试代码中的合成布尔和测试摘要不进入生产加载或准入路径。

现有合同按证据能力分为四层：

1. **bundle 完整性**：writer/loader 校验 manifest、权重、训练清单、模型版本和
   SHA-256，并在写目录前拒绝 `qualified/assist`。
2. **候选实际采用**：`RegionResourceRuntimeAckParser` 可证明建议经过 main 消费、D3
   形成严格后继计划、D7 形成同代 binding，且 owner、plan、epoch、lease 和总线
   sequence/hash 一致。它不证明物理结果或模型准入。
3. **联盟和通信**：`CoalitionCommitState` 保存 required/acked members 和联盟代次；
   `CausalCommunicationEvidenceGate` 校验每个成员 ACK 的实际投递回执。当前这两类证据尚未
   与某个 A2 候选的 runtime ACK 和 D6 cell 审计装配为同一个内容身份。
4. **结果和配对**：区域 reward 适配器可绑定 ACK 后的非重叠、truth-free 观测窗口，但明确
   固定 `physical_execution_outcome_available=false`；隔离 paired 合同和
   `ShadowPairedEvaluator` 也不授予物理、因果、assist 或 authority。正式物理结果和配对
   非退化仍必须来自 main 运行制品及 D6 独立审计。

现有 D4 专用装配器的最小输入包含：候选 bundle 全树和模型摘要；场景、seed、comparison
key、advisory 及模型指纹；候选实际通过门控且未走规则回退；源计划和严格后继计划身份；
owner/layer、plan version、epoch、lease 和 fault/partition generation；联盟
ID/version、required/acked members、每个成员 ACK 的 delivered receipt 内容摘要；运行 ACK
与 D3/D7/main 的序列和载荷摘要；采用后物理结果 availability；同外生输入 R0 配对及逐项
non-degradation；D6 审计制品和带外校验摘要。任何一项缺失都保持 unavailable。D4 不复制
D6 的通用外部审计 schema；D4 已实现语义校验和内容寻址装配，并只在新目录生成新版本
bundle，旧 v2 manifest 保持不变。当前 D6 实物输出仍失败关闭，所以尚无真实外层包。

现有 development bundle、nominal 20-seed 和 `active_risk` 20-seed 证据仍不能拼接：
前者候选安全采用为 0/20，后者 188/188 区域记录执行的是规则回退且
`production_runtime_ack=false`。正式 assist、PPO 和 authority 继续关闭。

验证日期为 2026-07-26。本轮没有新增场景、seed 或性能样本；验收标准为不存在
development bundle 自晋级入口、历史证据不被宽松拼接、D4 全量回归零失败。结果为
**569/569 passed**。剩余限制是 D6 冻结外部审计和真实候选采用正样本尚未形成。

## 2026-07-26 A2/C1/F1 学习准入复核

对照 main 提交 `d59352be83c24238fc8c41a9fe7a1c0db40a6d31` 的正式学习 scope 合同，D4 当前不能合法进入 A2、C1 或 F1。现有区域策略 bundle 为 `d4-region-bc-900-development-v1`，manifest、权重和训练清单 SHA-256 分别为 `dad2adbe9c36dd9ff8ee8bb3c11b1e07e66743c6f80dd8e956799208a10c05c9`、`3da0360be8788f3ffeb8e9f9eba3e0d5369ec0bdf9e05729dfb1db07d71d5f62` 和 `ff3081c8e320d9c8e1b032fb6234cd24159f0feedb1c6a706633cea6c1030dc6`。其生命周期和模式上限仍是 `development/shadow`。

本轮收紧 `d4-region-resource-model-bundle-v2`：bundle writer 只能生成 `development/shadow`，调用方不能再靠布尔字段生成 `qualified/assist`；拒绝发生在目录和权重写入前。没有 D4 manifest 的注入策略也不能进入 assist。旧 bundle、manifest 和权重未修改。

已有两组证据都不能用于晋级。正式 nominal 20-seed 干预的源 manifest SHA-256 为 `d6ef23b28add92e9a24a185ea72a7275e341bd796a2e11930c4d5f46b19a883c`，D4 干预文件 SHA-256 为 `aa6b22d252184d9bfc58c6e35cf6798551d26447a74ea7619c8a37a8969e2329`；候选安全采用为 0/20，运行 ACK 和物理结果不可用。`active_risk` 20-seed 隔离物理 sidecar 文件/内容 SHA-256 为 `dbbda16194f14a63b66e3fc9f2360103b8fe401a6db9b1f1e693dc8c169a7515`/`1aae70cd5612cce3f20ab4e2723533bd6ab1a0775d5e254cf425aeede85e3489`，虽然物理窗和描述性非退化为 20/20 可用，但 D4 候选均为 `candidate_considered=false`，执行的是确定性规则回退，且 `production_runtime_ack=false`。这两组制品不能拼接为模型准入。

2026-07-26 D4 全量回归为 **569 passed**。正式晋级仍需新的、内容寻址的 promotion 合同，以及在 clean、未见 seed、真实降级场景中绑定 D4 候选实际采用、新执行计划 ACK、联盟成员 ACK、采用后物理窗和配对非退化的 D6 独立审计。在此之前保持 fail-closed。

## 2026-07-25 异步 M-to-N 联盟确认

区域联盟确认现按真实通信到达顺序跨快照累积。提案建立后进入 `collecting_acks`；没有 ACK 或只有部分 ACK 时保持该状态，`execution_authorized=false`。同一 `plan_id/plan_version/epoch/coalition_version` 的后续快照复用现有成员位图，全部必要成员 ACK 到达后才原子进入 `committed`。普通评估不再把“当前缺 ACK”解释为“确认窗口已经结束”。

`RegionalFailoverSnapshot.finalize_coalition_collection` 是向后兼容的显式终结开关，默认关闭。只有调用方明确终结、租约到期、网络分区、联盟摘要冲突或成员明确不可执行时，当前代次才进入 `aborted` 或 `reconfiguring`。旧 epoch/version、过期、越权或内容不匹配 ACK 被拒绝，不进入 ACK 位图，当前快照继续失败关闭；后续合法 ACK 可在租约内完成同一代次，避免单个乱序旧包永久阻断合法联盟。

2026-07-25 新增 5 项异步生命周期回归。三文件专项为 **97 passed**，D4 全量为 **569 passed**。验收要求是：完整 ACK 前授权数为 0；三个必要成员分三次送达后一次性提交；显式终结、租约到期、分区、陈旧代次和无效 ACK 均不能产生执行权限。该组数字来自纯 Python 模块测试，不是 AirSim 或 scalable 3D 系统级证据。

main 随后完成单随机种子 scalable 3D 集成复跑。场景为 2 目标、4 资源、1 个二级侦察节点，高威胁目标要求 2 个主成员和 1 个备用成员，随机种子 `1271`。中心在 `1.5 s` 失效，二级计划版本 2 在 `2.00 s` 发布；`2.05 s` 为 0/3 ACK 和 `collecting_acks`，`2.10 s` 为 3/3 ACK 和原子 `committed`。提交前主成员保持，提交后两个主成员进入三维中段比例导引，备用成员继续待命；在线真值使用和 `global_track_id` 改写均为 0。main-owned 模块栈为 66 passed，scalable 3D 全量为 272 passed。该结果关闭单随机种子质点接线缺口，AirSim 多随机种子、真实网络、正式 5700 单元矩阵和 200 对 200 性能仍未验证。

## 2026-07-25 P0 区域通信因果证据门

D4 已完成运行级 P0 的模块合同部分。新增不可变 `CommunicationDeliveryReceipt`，记录回执号、消息号、源节点、目的节点、版本化 topic、总线序号、envelope schema、发送/到达时间、authority、plan version、epoch、lease expiry、partition generation 和 payload SHA-256。`CommunicationDeliveryReceipt.from_delivered_message()` 采用 duck typing，直接从 main 的 delivered message、envelope 和 truth-free payload 提取这些字段，不导入 main、AirSim 或 scalable3d。调用方不能覆盖消息类型、authority、plan、epoch、lease、partition generation 或 message ID；回执号按实际投递事实内容寻址生成。

版本化 topic 固定映射为 `d4.secondary_readiness.v1`、`d4.regional_plan_broadcast.v1`、
`d4.regional_plan_owner_ack.v1` 和 `d4.coalition_member_ack.v1`。payload 必须同时携带
`schema/message_id/message_kind/authority_id/plan_version/epoch/lease_expires_at_s/partition_generation`，
且 envelope source/timestamp、topic 映射和 payload 自声明必须相互一致。缺字段、truth
字段、错源、错时间或错消息类型在构造阶段失败关闭。

`CausalCommunicationEvidenceGate` 分别验证二级 readiness、区域计划广播、区域计划所有者确认和
联盟成员 ACK。缺回执、冲突重放、错源/目的/类型、旧 plan/epoch、过期或错 scope lease、
到达晚于决策、分区代次和 payload digest 不一致均输出稳定 reason code。完全相同的 receipt
和 expectation 可幂等重放；同 receipt ID 的内容变化或跨证据复用被拒绝。验证结果固定
`authority_granted=false`，不修改既有 owner、epoch、lease、plan 或 coalition 状态机。

main 已把 readiness、计划广播和 ACK 接入 `DeterministicCommunicationNetwork`，只用实际 delivered message 建立回执。原 5v5 通信关闭复现现为 D4 可执行区域 0、失败关闭区域 8，全部 D7 命令保持 `hold/d4_hold_for_review`，原 P0 已关闭。异步联盟修复后的 2 目标/4 资源单随机种子系统正例也已按上一节通过；该证据仍不能替代 AirSim 多随机种子、真实网络或正式规模验收。

## 2026-07-22 跨独立运行内容身份边界

D3 使用不透明计划号区分独立执行谱系。同 seed、同输入的两个独立 planner 可以产生不同的原始 `plan_id`。D4 的 `authority_digest` 包含区域 `plan_id`，`formal_decision_digest` 包含正式裁决中的计划号，`advisory_id` 又对完整建议合同做内容寻址，因此三类值会随 D3 原始计划号确定性变化。它们仍是单次运行内的正式身份和完整性字段，不能从原始日志、消费 ledger 或运行时回执中删除或改写。

跨提交业务等价比较只允许生成独立的规范比较视图。比较器必须先验证原始运行：D3 谱系连续；同时间正式裁决可重算出 advice 的 before/after digest 且二者相等；`RegionResourceAdvisoryContract.from_dict()` 能从原始合同重算相同 `advisory_id`；顶层、recommendation、每个 region 和 transfer 的 authority digest 一致，并可由完整 authority payload 重算。随后只把已经通过 D3 谱系审计的原始计划号映射为规范计划 token，重算规范 authority digest、正式裁决 digest 和 `d4-rr-advisory-<SHA256>`。事件序号只用于配对，不得替代 `advisory_id`，也不得把任意摘要改成“同一摘要类别”。

以下字段不得归一化：区域、任务、全局航迹、资源、节点和联盟身份；owner/layer/role；plan version、epoch、lease、ACK、active/fault fence；正式 action/reason/decision；recommendation 的策略、模型、置信度、区域动作、转移和安全证明。任一源事件缺失、原始哈希不闭合、未知计划引用、谱系不连续或上述字段不同，比较均失败关闭。

本次只读复核覆盖 clean `8f86192` 与 `f80b5bd` 的 seed 42000-42002、三组 10 秒 200v200 episode。两侧各 30 条正式裁决和 30 条建议中，原始 advisory 内容地址、正式裁决摘要、authority 摘要和摘要副本一致性均为 30/30；按上述规则重算后，30/30 对正式裁决和建议逐字段相同。当前制品可由 `source_version + protected_committed_resources` 回算原始 authority 摘要；未来若该回算不成立，必须持久化完整 `RegionResourceSnapshot` authority payload 后才能比较。

## 2026-07-22 隔离物理续跑计划代际复核

main 的中心失效 20-seed 物理续跑共形成 20 个 pair、196 条区域记录，D7 世界命令已经应用，但 D4 区域采用全部以 `isolated_execution_plan_not_strictly_new` 拒绝。该结果不是 owner、epoch、lease 或物理消费失败。适配器把同帧 `d3_planning_frame.plan` 作为 formal source，同时把从 `previous_plan` 重新求解得到的同版本 arm plan 作为 applied plan。两者计划标识不同而版本相同，不满足严格后继，也不属于同身份刷新。

main 必须按以下规则构造证据：

- `center_failed`：source 是与同帧 formal secondary decision 完全一致的区域计划；owner 为选中的二级节点，epoch 和 lease 取 formal ownership。applied 必须由该 source 继续生成，使用新 plan ID、严格更高版本，并保持同一 formal owner/epoch/lease。
- `center_and_secondary_failed`：source 是与 formal distributed decision 一致的区域计划；每个区域使用该 decision 的分布式 owner、epoch 和 lease。applied 同样必须是该 source 的严格后继。
- `active_risk`：source 是 formal center authority 的当前计划。若中心重规划改变执行签名，applied 必须严格更新；若实际执行未改变，只能以相同 plan ID/version、相同 binding/未分配清单和相同 owner/epoch/lease 形成显式 evaluation refresh。
- `d3_planning_frame.previous_plan` 只表示 D3 规划祖先。被动降级时它仍属于上一个 authority，不能直接冒充 D4 source，除非另有同代 formal D4 decision 明确绑定它。

D4 没有放宽 strictly-new、owner、epoch、lease 或 production-runtime-ack 门。模块测试新增同版本异 ID、故障前 owner 和三类刷新回归，隔离专项 **26/26 passed**，该阶段 D4 全量 **508/508 passed**。2026-07-25 main-owned 选择逻辑已改为跳过仅含故障栅栏的帧，并只选择已完成 D4 裁决且由 D3 采用对应区域计划的帧；相关保留种子选择测试 11/11 通过。原 20-seed 物理证据尚未按新逻辑正式重生，本次历史全拒绝仍不能计为降级采用成功。

## 2026-07-21 PDT / 2026-07-22 UTC 隔离多周期采用合同

新增 `region_resource_isolated_rollout.py`，为 main 后续克隆世界多周期 rollout 提供 `d4-region-resource-isolated-adoption-evidence-v1`。合同只接受 `center_failed`、`center_and_secondary_failed` 和 `active_risk` 三类来源；snapshot、formal D4 decision、源 D3 plan、候选门、场景配置、初始状态、通信 schedule 和故障 schedule 均以 SHA256 进入 lineage。场景名含 nominal、来源哈希不一致、网络分区或 formal decision 未形成可执行二级/分布式 authority 时，降级策略证据保持不可用。

候选证据显式区分 `candidate_considered`、`gate_pass`、`new_execution_plan_applied`、`evaluation_refresh_applied` 和 `rule_fallback`。候选置信门保持 `0.6`，时延门保持 `50 ms`。只有新 plan ID、严格更高 plan version、当前 owner/epoch/lease、完整 binding hash 和 main 隔离世界消费回执全部一致时，才输出 `isolated_candidate_adoption_available=true`。同 plan ID/version 只允许 binding、未分配集合、owner、epoch、lease 和创建时间不变的 evaluation refresh；它不计为候选采用。候选低置信、缺 ACK、旧 epoch、到期 lease、ACK/plan binding 篡改、缺联盟确认或分区均失败关闭，低置信候选只能回到确定性规则计划。

隔离回执固定 `isolated_simulation_only=true`、`production_runtime_ack=false`。证据同时固定 physical outcome、paired non-degradation、counterfactual、causal、degradation-effectiveness claim、PPO、assist 和 authority 为 false，规则回退为 true。D4 还提供 D3 `d3.isolated-plan-consumption-evidence.v1` 到本合同的严格桥接：不导入 D3，只校验字段集合、来源 lineage、计划、binding 数量、时间窗、内容哈希和隔离权限，再生成非生产 D4 回执。2026-07-22 本地验证覆盖三类正例、三类刷新、同版本异 ID 拒绝、故障前 authority 来源拒绝、规则回退、D3 回执桥接和篡改/过期负例，专项 **26/26 passed**，D4 全量 **508/508 passed**。当前只完成 D4 消费合同；main 的首轮中心失效物理续跑尚未形成有效区域采用，D6 也不能据此给出成对非退化结论。既有 nominal 5v5 结果不得关闭该缺口。

本模块用于离线科研仿真：当中心 C2 节点不可用时，评估区域二级节点接管、完全无中心协商、中心恢复合并等被动降级机制；当中心仍可用但 D1/D2/D3/D5 的不确定性或末端视觉不一致升高时，评估主动降级仲裁机制。模块只使用内存网络和粗粒度摘要，不包含真实通信、飞控、硬件、火控、毁伤、自动处置或授权绕过逻辑。

**2026-07-21 保留 seed 配对候选门诊断**：`RegionResourcePairedArmEvidence` 已升级为 `d4-region-resource-paired-arm-evidence-v2`。新证据除 aggregate `candidate_thresholds_passed` 外，还持久化 candidate confidence、冻结的 `minimum_confidence`、OOD 状态、candidate latency 与 latency limit、finite 状态，以及 confidence/OOD/latency/finite/external-failure 五项 gate 结果。executor 对已考虑候选至少输出 `candidate_low_confidence`、`candidate_ood_rejected`、`candidate_inference_timeout`、`candidate_output_nonfinite` 中对应的明确拒绝码；旧 `candidate_threshold_or_finite_gate_rejected` 仅作为兼容汇总码保留，不能单独解释拒绝。v1 reader 先按旧字段集合和旧 manifest content ID 验证，再迁移为 v2 且令新增诊断显式 unavailable；历史 v1 artifact 保持只读，新 v2 正式证据使用独立目录，不覆盖旧运行。

当前权威输入为 `research_modules/scalable_3d_simulation/outputs/reserved_seed_interventions_nominal_5v5_1000_1019_formal_7891296`，源提交 `78912963b67fe86ee9a8d29186b18a9dd60c460c`，`SHA256SUMS` 文件 SHA256 为 `821f15035e628d8db86f13c22d93f8e05142c5f00aae9118974a74bdc98b72bc`，manifest SHA256 为 `d6ef23b28add92e9a24a185ea72a7275e341bd796a2e11930c4d5f46b19a883c`。D6 已在 `research_modules/d6_evaluation_metrics/outputs/reserved_seed_interventions_nominal_5v5_1000_1019_formal_7891296_d6_profile_bound_v2_audit_20260722/` 生成 profile-bound v2 outcome-availability sidecar，状态为 `pass_offline_assignment_comparison_only`；sidecar 文件 SHA256 为 `f3852251daf02ec87fe878e7fb80aad6f381d8c0756a5c956a32e737a3871c3b`，规范内容 SHA256 为 `c02a345c46ddc642dea7fb6bfcfb24184e7dc2a9f35b754c90324d074b445d2d`。D6 独立重算确认 20/20 source clean 且 finite、在线 truth 使用数为 0，20/20 treatment candidate 被评估；confidence gate 在保持不变的 `minimum_confidence=0.6` 下通过 0/20，OOD、latency、finite、failure gate 各通过 20/20，aggregate gate 通过 0/20，safe adoption 0/20，规则回退 20/20。候选 confidence min/mean/max=`0.508892953/0.563426384/0.569492280`。`treatment_candidate_latency_ms` 的执行时延 P95 采用 nearest-rank，为 `2.241315 ms`；`candidate_gate_summary.candidate_latency_ms` 的门控汇总 P95 采用线性插值，为 `2.264415 ms`，两者不得混称。sidecar 已存在只表示同帧离线分配比较可用；runtime ACK、干预后物理结果、paired effect/non-degradation、counterfactual、causal 及故障场景降级策略效果仍为 unavailable。bundle manifest 继续声明 `confidence_head_uncalibrated`，`formal_twenty_seed_performance_completed=false`，`PPO/assist/authority=false`、`rule_fallback=true`；该 nominal 5v5 只证明门控分解和失败回退，不能证明候选或降级策略有效。配对专项 **33/33 passed**，D4 全量 **482/482 passed**。

**2026-07-21 区域结果与奖励证据合同**：新增 `region_resource_reward_evidence.py`，冻结 `d4-region-resource-observational-reward-v1`。适配器只接受已通过 ACK v2 的区域建议，并把 advisory/模型指纹、源计划与当前计划、owner/epoch/lease/fault generation、ACK sequence/time、源/结果区域快照、执行与联盟绑定以及来源制品 SHA256 固定到一个左闭右开的非重叠窗口。高威胁积压、配额满足缺口、转移完成缺口、备用不足、通信负载、分配冲突、降级失败和计划抖动均保留 raw value、单位、归一化分母、来源 SHA、availability 和 reason；缺测分项保持 `unavailable`，不补零。冻结观测成本为 `sum(weight*min(raw/denominator,1))/sum(weight)`，新执行计划的时间窗口观测奖励取其负值；`evaluation_refresh_applied` 只输出观测成本，不获得动作归因奖励。窗口重叠、缺 ACK、旧 generation、租约覆盖不足、执行/联盟绑定变化、哈希篡改、真值字段或缺字段均失败关闭。该阶段新增专项 **19/19 passed**，运行时 ACK 与奖励专项合计 **52/52 passed**，D4 全量 **449/449 passed**。该合同没有回填正式 900 episode，也没有产生 paired、counterfactual、causal 或 on-policy 证据；`CoalitionMemberAck`、物理执行、PPO、assist 和 authority 继续不可用，规则回退保持必选。

**2026-07-21 区域建议运行时确认接口**：`region_resource_runtime_ack.py` 已升级为只读 `d4-region-resource-runtime-ack-evidence-v2`，在不导入 main、D3、D7 或 scalable3d 的条件下消费 D4 advisory/result、main consumption、运行时 ACK，以及 D3/D7 源 envelope。输出用 `adoption_kind` 区分两种证据：执行签名变化时，只有 plan ID 和版本严格推进、owner/epoch/lease 完整、D3/D7 序列/哈希与全部 binding 一致，才产生 `new_execution_plan_applied`；执行签名不变时，parser 仍能校验显式同代 `evaluation_refresh_applied`，但它不属于 A2 动作采用。2026-07-27 集成夹具已按当前合同改为：无操作建议只产生 `no_successor`，不生成 applied ACK 或刷新 authority/lease；显式 `hold/request_replan` 干预才形成具有新 ID、严格更高版本和正确 `previous_plan_id` 的 successor。当前集成专项 **6/6 passed**，D4 全量 **658/658 passed**。验证器继续保持 `CoalitionMemberAck`、物理 outcome、真实 paired reward、PPO、assist 和 authority 为不可用/false。冻结 900 episode 没有新 runtime 字段，仍不能补造 applied ACK。

**2026-07-21 区域调度全样本准入审计**：新增只读、失败关闭的 `region_resource_full_sample_audit.py`。正式数据路径为 `research_modules/scalable_3d_simulation/outputs/learning_generation_v1_multibatchfix/learning_dataset/d4_region`，共 900 episode、1798 frame/sample、14384 个区域动作；规范只读切分为 train/validation/test = 540/180/180 episode、1079/359/360 sample、8632/2872/2880 action。补充课程路径为 `outputs/region_action_coverage_curriculum_20260721_clean_9445ed6/dataset`，共 100 episode、300 frame/sample、1200 action；规范切分为 60/20/20 episode、180/60/60 sample、720/240/240 action。900/900 和 100/100 episode 文件哈希均通过，全部样本数值有限并通过动作/transfer 合同、配额守恒、owner/plan/epoch/lease/version、保留 seed、dirty 状态和在线真值隔离检查，违规数为 0。`target.kind=rule` 只表示规则教师标签；`recommendation.projected=true` 只表示离线确定性投影通过，二者都不是运行时 applied ACK。显式投影前动作掩码、被拒旧计划/旧租约样本、真实 `CoalitionMemberAck`、outcome、可归因 reward 和同 seed paired shadow 均为 `unavailable/pending`。D6 外部路径与带外 SHA256 复核尚未完成；PPO、assist、authority 继续关闭，确定性规则、lease/epoch 和安全投影仍是唯一可执行路径。审计专项 10/10，该阶段 D4 全量 **397/397 passed**；后续候选门诊断阶段为 **482/482 passed**，当前全量见本文顶部的 **569/569 passed**。

**2026-07-20 scalable 3D 接线事实同步**：main-owned `IntegratedScalableModuleStack` 已消费 `d4-regional-failover-v1`，闭合单一二级 owner、两个二级节点的多区域 owner，以及中心与二级连续失效后的 distributed D3 plan。D7 在恢复质点导引前核对区域 owner/node、plan version、epoch、lease、commit mode 和 fault generation；过期 lease、缺 commit 或旧 source plan 均 fail closed。本轮只读定向复核 `research_modules/scalable_3d_simulation/tests/test_module_stack.py` 为 **8/8 passed**。这是三维质点接口/集成测试证据，不是 AirSim、真实 RF/mesh/socket、硬件或实飞证据，也不代表长时 200v200 多 seed 已验收。

**2026-07-20 可选区域资源建议层**：新增版本化 `RegionResourceSnapshot`、确定性规则基线、安全投影、共享区域图 actor-critic、行为克隆、原生 clipped PPO、manifest + `state_dict` + SHA256 bundle、完整 episode/数值 seed 原子划分和 paired shadow evaluator。快照只含区域聚合需求、不确定性、可见/一致性、资源/备用、二级覆盖/就绪、通信和当前 authority fence，不含 actor truth ID 或具体目标身份。输出只允许区域配额增减、相邻区域资源转移、备用比例、侦察优先级与 hold/replan；不能生成 resource-target assignment。学习层默认 `disabled`，CLI 默认 `shadow`，任何超时、低置信、OOD、非有限输出、模型版本或 SHA 不匹配都回退规则建议；少于 20 个未见 seed 不得进入 assist。所有建议仍经 owner/version/epoch/lease、fault fence、ACK/commit、邻边和资源守恒投影，D4 确定性安全状态机继续拥有最终降级裁决。原建议/学习管线专项 **32/32 passed**；增加下一周期消费、正式 bundle 准入和动作多样性失败关闭回归后该文件当前 **51/51 passed**。这些测试证明合同和研究管线可运行，不证明模型优于规则、AirSim 收益或真实网络性能。

**2026-07-20 区域学习 episode 数据合同**：新增 D4-owned `d4-region-learning-dataset-v1`。`RegionLearningEpisodeSource` 固化 scenario/version/scale、数值 seed、episode ID、Git commit/dirty 和 config SHA256；每帧必须提供 truth-free `RegionResourceSnapshot`、`rule|formal` target 或显式 unavailable、显式 reward/unavailable，并可附 recommendation。训练 target 会按固定 projector 版本重验 owner/plan/version/epoch/lease、备用、邻边、容量、分区和 quota 证明，不信任外部 `projected=true`；actor/object/global-track/evaluator/offline-truth key 变体均拒绝。manifest 还会把 episode 顺序、availability 和可重放 split 对照 episode inventory。数据与正式训练准入测试为 **15/15 passed**，共享切分专项为 **12/12 passed**；候选门诊断阶段 D4 全量为 **482/482 passed**，当前全量见本文顶部。96-episode/192-frame 高基数用例仍只是合成确定性合同回归，正式数据和开发模型结论单列如下。

**2026-07-20 正式数据审计与行为克隆开发模型**：D4 只读审计 `learning_generation_v1_multibatchfix` 的 900 episode/1798 frame 数据，900 个 episode SHA256、dataset SHA、source identity、schema 和数值 seed 原子划分均通过。训练/验证/内部测试为 70/15/15 个 seed、1258/270/270 帧；外部保留 seed 1000-1019 未进入数据。2026-07-21 使用固定 seed `20260720` 复跑后，共享区域图行为克隆在 CPU 单线程运行 66 epoch，最佳 epoch 54，内部测试损失 `0.071545`、推理 P95 `0.7774 ms`，权重 SHA256 仍为 `3da0360be8788f3ffeb8e9f9eba3e0d5369ec0bdf9e05729dfb1db07d71d5f62`。该结果只能证明训练和安全投影管线可运行：14384 个区域动作中非零 quota、transfer、hold、request_replan 均为 0；D6 还确认 898/1798 帧只有无归因相邻状态转移，reward/causal/counterfactual 可用数均为 0。bundle admission 直接记录 `action_diversity_sufficient=false`、`strategy_capability_claim_allowed=false` 和全部动作计数。当前结论是“管线可用但动作多样性不足，shadow-only”；低损失不能作为调度策略能力证据，PPO 与 assist 均失败关闭。权重只保存在 ignored `outputs/`，普通 Git 只保留配置、指标、审计、SHA256 和本地定位说明。

**2026-07-21 跨模块共享 seed 切分**：新增 `canonical_seed_split.py`，独立消费 main 发布的 `scalable3d-shared-seed-split-registry-v1`，不导入 main runtime。加载器严格核对 schema/policy、D3 兼容排序、assignment/content SHA256、源 training-seed-registry SHA、100 个数据 seed 的完整覆盖、无额外或保留 seed，并绑定原 dataset SHA、原 split SHA 和共享 registry 文件/内容 SHA。D4 原 70/15/15 manifest 与 episode 文件保持只读；显式 canonical 内存视图将同一批数据映射为 60/20/20 seed、540/180/180 episode 和 1079/359/360 frame。BC loader 只有收到 `canonical_split_view` 时采用该视图，默认行为不变。正式只读审计前后源数据目录树 SHA256 均为 `8cde5cace4bd8106e35801f6179775ae39298592f3b556f712ea857b9c496bc1`。该能力只解决 D3/D4/D5 未来联合训练的数据切分治理，不提供新模型性能证据；PPO、assist 和正式裁决状态均未改变。

**2026-07-21 区域动作覆盖补充课程**：新增独立 `region_resource_curriculum.py` 和 CLI。每个共享训练 seed 构造保持、请求重规划和跨区转移三帧，复用 `RegionResourceSnapshot`、`RuleRegionResourcePolicy`、`DeterministicResourceProjector`、dataset-v1 和 canonical registry，不修改正式 900 episode。commit `9445ed6` 的 clean 课程为 100 seed/100 episode/300 frame、4 区域/17 聚合资源，含 hold 100、request-replan 200、非零 quota action 200、transfer 100；60/20/20 三个 canonical 桶均覆盖四类动作，硬约束违规、在线真值字段和保留 seed 泄漏均为 0。clean dirty episode 数为 0，行为克隆只读 view 可用；300/300 reward/outcome 仍显式 unavailable，PPO、assist、authority 均关闭。首次 dirty 产物只保留为开发历史。该课程只关闭“规则 teacher 动作覆盖 producer 与 clean BC 数据准入”缺口，不证明策略收益或正式 900 数据已有动作多样性。

**2026-07-20 下一轮规划 advisory contract**：`d4-region-resource-advisory-v1` 是 `RegionResourceRecommendation` 经 `DeterministicResourceProjector` 后的只读消费视图。内容寻址 `advisory_id` 同时充当幂等键；合同给出 episode-clock 创建时间、默认 1.0 s 可配置 TTL、最早 authority lease 截止时间、scenario/snapshot/authority、source plan 集合、policy/model/projector identity，并为每个区域和 transfer 固化 snapshot version、owner/layer、plan id/version、epoch、lease、ACK/fault 状态、资源前后量、protected reserve/committed、edge 端点与 capacity。`RegionResourceAdvisoryGate` 在下一轮严格重验 current snapshot/plan/epoch/lease、ACK、fault fence、守恒、transfer 邻接/容量和已消费 ID；任一不满足均输出 `consumable=false`。它只给 main 提供下一轮 D3 规划输入，不修改 D3 plan，不授权 D7，也不包含 truth/actor/object identity、成员或目标级分配。

**2026-07-20 区域化合同状态**：新增 `d4-regional-failover-v1`，面向 scalable3d 场景按输入长度维护逐区域唯一 authority。中心未 `failed` 时保持中心 owner，仅根据 D1 协方差/时效、D2 ambiguity/IDSW/duplicate、D3 plan/version/epoch/lease/current/feasible 和 D5 consistent/inconsistent/binding/friend/duplicate 证据输出继续中心、请求机动高空侦察辅助、中心重规划或保持复核；中心 `failed` 后只选择对该区域具有完整持续 readiness、coverage 和有效 lease epoch 的 `mobile_high_recon`，没有有效二级节点时才进入受约束 bid fallback。任一层级的 `k>1` 任务都必须由全部 required member 对同一 plan/coalition version、epoch 和有效 lease 完成 ACK 才成为 `committed`；区域 authority/commit lease 取 authority、D3 task 和二级 lease 的最早到期值。缺 ACK、旧 epoch/version、过期 lease 或分区均闭锁。该阶段纯 Python 验收新增 23 项，覆盖 5/20/50/100/200 区域元数据、声明节点数上限、中心与二级连续失效、双区域 coverage、中心/二级/distributed 原子门、分区、D5 member hold、跨区域 capacity、单成员多能力、旧 generation 和 lease；当时 D4 全量 **303/303** 通过，后续运行时确认阶段为 430/430、候选门诊断阶段为 482/482，当前全量见本文顶部。该模块合同本身没有 AirSim、真实网络或物理拦截样本；受约束成员选择是确定性基线，不等于完整 CCBBA、reserve 激活或在线联盟重构。

**2026-07-15 P0 历史状态**：当日重新确认的二级接管 P0 已关闭。此前 278/278 回归覆盖 coordinator、episode adapter、secondary coalition proposal 和 D6 metadata，但把它表述为“所有公开 secondary owner 入口均已闭锁”属于过度声明：`build_d7_secondary_handoff()` 与 `build_secondary_takeover_plan_metadata()` 仍会把缺失的 sustained readiness、expected/actual source 或 plan/required lease epoch 当成“不是 False”而放行。两个 helper 及 adapter 后续均要求这些字段显式存在，`secondary_readiness_sustained is True`、source 相等、plan epoch 不低于 required epoch，且 current time/expiry 存在并严格满足 `current_time < expiry`；同 id/version 的已激活 secondary plan 维持路径也执行同一复核。当日 D4 单元测试 280/280 通过；候选门诊断阶段全量为 482/482，当前全量见本文顶部。

**2026-07-15 M5N2 负对照同步**：真实 AirSim M5N2 baseline/candidate 各 10 seeds，共 20/20 case 完成。该批全程保持中心 owner，`active degradation=0`，因此只用于验证“中心继续执行时不误降级”和定位协同末端断点，不能宣称二级接管或完全分布式联盟性能闭合。聚合结果为 coalition completion `0/20`、第二 primary 进入 5 m `0/20`，20 个第二 primary 均以 `collision_stop` 结束；当前产物未记录碰撞对象，不能把该状态自动解释为成员冲突，也不能把它作为主动降级触发。D4 仍必须联合 D1 不确定度、D2 关联风险、D3 plan/version/可行性和 D5 当前绑定/身份/视觉一致性证据进行仲裁。D4 main-bus 阶段 mean/P95/max 约为 `5.59/6.70/94.10 ms`，不是本批约 1 s control tick 的主要耗时。终止前额外完成的 `png_ttc_2v2_seed001` 不纳入 M5N2 聚合，dropout case 完成数为 0。真实 secondary/distributed 多 seed 仍为 P1。

## 目录

- `PLAN.md`：模块研发计划、问题定义、状态机和仿真边界。
- `docs/ALGORITHM_AND_IMPLEMENTATION.md`：算法原理、数学模型、接口、调参建议和实施细节。
- `docs/README.md`：D4 文档索引。
- `d4_distributed_fallback/`：Python 包源码。
- `scripts/run_failover_simulation.py`：默认离线降级仿真入口。
- `scripts/run_p1_failover_replay.py`：版本化 P1 二级/分布式接管扰动矩阵。
- `scripts/run_p1_communication_fault_replay.py`：六场景、多 seed 的 P1 通信故障矩阵。
- `scripts/run_p1_episode_fault_replay.py`：使用 AirSim 兼容 episode 时钟运行 P1 故障注入验收矩阵；不启动 AirSim，也不模拟真实 RF 网络。
- `d4_distributed_fallback/episode_communication.py`：供 main 按真实 AirSim episode 时钟逐 tick 调用的通信故障状态接口及七场景纯 Python replay。
- `d4_distributed_fallback/regional_failover.py`：scalable3d 兼容的区域场景元数据、逐区域 authority、主动证据、二级 readiness/coverage 和原子 fallback 合同。
- `d4_distributed_fallback/region_resource.py`：truth-free 区域资源快照、规则建议、确定性安全投影、下一周期 advisory contract/一次性消费门、reward、数值 seed 原子划分和 paired shadow 指标。
- `d4_distributed_fallback/region_resource_dataset.py`：版本化 episode source/frame、原子 stage/finalize/load、数值 seed split、manifest/哈希与 availability 校验。
- `d4_distributed_fallback/canonical_seed_split.py`：共享 seed registry 的独立严格校验，以及不改源数据的 canonical 内存切分视图。
- `d4_distributed_fallback/region_resource_learning.py`：可选共享区域图 actor-critic、BC、原生 clipped PPO、bundle/SHA/OOD 与 fail-closed advisor。
- `d4_distributed_fallback/region_resource_training.py`：正式 dataset 只读审计、固定 seed 行为克隆、逐字段/安全/延时评估和 shadow-only 准入报告。
- `d4_distributed_fallback/region_resource_full_sample_audit.py`：正式数据和补充课程的全清单、全 episode、全 frame/sample 只读准入审计；输出显式 availability 和 fail-closed 状态。
- `d4_distributed_fallback/region_resource_runtime_ack.py`：独立解析和核对 advisory、main consumption、D3 plan ACK、D3/D7 source envelope 的只读运行时 applied-ACK 证据；不授予执行权。
- `d4_distributed_fallback/region_resource_reward_evidence.py`：把已确认采用的区域建议与非重叠、哈希绑定、真值隔离的区域结果窗口连接，输出分项观测成本和严格受限的时间窗口奖励证据；不接入 PPO 或执行权。
- `d4_distributed_fallback/region_resource_paired_intervention.py`：冻结保留 seed 的 control/treatment 同输入合同、`region_resource_bc_900_20260720` 只读候选加载与三文件 SHA 复核、隔离 arm 安全采用证据和完整 manifest；复用规则策略、确定性投影、运行确认/奖励 schema 与 paired evaluator，但不生成线上 ACK 或结果标签。
- `scripts/run_region_resource_advisor.py`：区域资源建议与 shadow paired evaluator CLI；默认 `shadow`，不改变正式 D4 verdict。
- `scripts/run_region_resource_paired_intervention.py`：严格校验并规范化 round-trip 配对 specification/manifest；不运行 episode、PPO 或性能评估。
- `scripts/train_region_resource_bc.py`：数据审计与行为克隆命令入口。
- `reports/region_resource_bc_900_20260720/`：不含权重的正式审计、训练配置、指标、模型准备度和本地 bundle 定位。
- `reports/D4_REGION_RESOURCE_FULL_SAMPLE_ADMISSION_20260721.{json,md}`：供 D6 通过显式路径和带外 SHA256 复核的全样本证据。
- `scripts/run_p2_coalition_replay.py`：隔离式 P2 联盟故障 replay；不接入在线 D4。
- `tests/`：状态机、CBBA、接管和仿真测试。
- `reports/EXPERIMENT_REPORT.md`：实验报告与曲线。
- `reports/AIRSIM_INTEGRATION_PLAN.md`：AirSim 离线回放集成计划。

## 快速运行

```bash
PYTHONPATH=research_modules/d4_distributed_fallback \
python3 research_modules/d4_distributed_fallback/scripts/run_failover_simulation.py --drone-count 5
```

运行隔离式 P2 联盟 replay：

```bash
PYTHONPATH=research_modules/d4_distributed_fallback \
python3 research_modules/d4_distributed_fallback/scripts/run_p2_coalition_replay.py
```

只有显式提供本地参考树时才探测外部能力：`--mit-cbba-path PATH`、`--ca-cbba-path PATH`。探测不会 import 或执行外部代码，也不新增默认依赖。

运行 P1 接管扰动矩阵：

```bash
PYTHONPATH=research_modules/d4_distributed_fallback \
python3 research_modules/d4_distributed_fallback/scripts/run_p1_failover_replay.py
```

运行 10-seed 通信故障矩阵；成员数和二级节点数均由入口参数决定：

```bash
PYTHONPATH=research_modules/d4_distributed_fallback \
python3 research_modules/d4_distributed_fallback/scripts/run_p1_communication_fault_replay.py \
  --member-count 3 --secondary-count 2 --seed-count 10
```

运行 episode-time 故障注入验收矩阵：

```bash
PYTHONPATH=research_modules/d4_distributed_fallback \
python3 research_modules/d4_distributed_fallback/scripts/run_p1_episode_fault_replay.py \
  --member-count 3 --secondary-count 1
```

该入口覆盖正常中心、中心失效后二级接管、二级再次失效后 peer 接管、缺 ACK、旧 epoch、过期 lease 和分区。输出中的 `real_rf_network_validated=false` 与 `real_hardware_validated=false` 是固定边界：结果只验证 episode 时钟上的合同和故障注入，不代表真实无线链路、网络设备或硬件故障验证。

运行任意区域数的 shadow 建议 demo：

```bash
PYTHONPATH=research_modules/d4_distributed_fallback \
python3 research_modules/d4_distributed_fallback/scripts/run_region_resource_advisor.py \
  demo --region-count 8 --mode shadow
```

正式 snapshot 使用 `recommend --snapshot PATH [--bundle-dir PATH]`；advisor 结果同时给出 projected recommendation 与 `advisory_contract`。main 若要将其作为下一轮 D3 规划输入，必须用同配置 `DeterministicResourceProjector.validate_for_consumption()` 或 `RegionResourceAdvisoryGate.consume()` 在 current snapshot 上重验。paired 评估使用 `shadow-evaluate --baseline PATH --candidate PATH`。即使显式请求 `--mode assist`，少于 20 个未见 seed、规则回退或任一模型门失败时仍降为 shadow。

正式行为克隆训练命令记录在 `reports/region_resource_bc_900_20260720/TRAINING_COMMAND.md`。本地 bundle 位于 Git 忽略目录，加载前必须核对模型版本和权重 SHA256。当前包的最高模式固定为 `shadow`，不能由 `--mode assist` 或调用方传入的 seed 数解除。

main 的 region-learning writer 不应再自行拼接 D4 私有 JSON。每个 episode 结束时构造公开 `RegionLearningEpisodeSource` 与 `RegionLearningFrame[]`，逐帧把缺 target/reward 写成带原因的 unavailable，再调用 `stage_region_learning_episode()`；批次完成后调用 `finalize_region_learning_dataset(..., minimum_unseen_seeds=声明值)`。训练端先调用 `load_region_learning_dataset()` 验证全部哈希，再分别使用 `load_region_behavior_cloning_samples()` 或 `load_region_ppo_training_episodes()`；PPO 返回的是完整 episode 预处理记录，不伪造 old log probability、value、advantage 或 return。

跨模块联合训练必须由调用方显式加载共享视图，再传给 BC loader：

```python
view = load_canonical_region_learning_split_view(
    dataset,
    shared_registry_path=shared_registry,
    training_seed_registry_path=training_seed_registry,
)
samples = load_region_behavior_cloning_samples(
    dataset,
    split="train",
    canonical_split_view=view,
)
```

不传 `canonical_split_view` 时继续使用 D4 manifest 内的 70/15/15 切分。共享视图不会写 sidecar 到源数据目录，也不能解除 reward、动作多样性、PPO 或 assist 门槛。

运行 D4 测试：

```bash
PYTHONPATH=research_modules/d4_distributed_fallback \
python3 -m pytest -q research_modules/d4_distributed_fallback/tests
```

## 当前能力

- 区域化 scalable3d 合同：`RegionalScenarioMetadata.from_scalable_scenario()` 只读消费 `scalable3d-scenario-v1` 的 target/resource/recon/region count，并拒绝 schema 或声明数量溢出；`RegionalFailoverCoordinator` 按实际 region/task/node 列表运行并输出 truth-free `d4-regional-failover-v1` bus payload。逐区域 owner 变更必须同时提升 `epoch` 和 `plan_version`，租约严格使用 `timestamp < expiry` 且收缩到最早 D3 task/secondary expiry，同 generation 不允许换 owner，分区时所有层级闭锁。
- 全局区域资源建议：`RegionResourceSnapshot` 和 `RegionResourceEdge` 按变长区域图运行；规则 fallback 与学习候选共用同一 `DeterministicResourceProjector` 实例，保证总资源守恒、只走可通信/可机动邻边、最低备用、当前 authority fence 和已提交联盟资源。`RegionResourceAdvisoryContract`/`RegionResourceAdvisoryGate` 进一步提供版本化、限时、幂等且 fail-closed 的下一周期消费接口。`SharedRegionGraphActorCritic`、BC/PPO 与模型 bundle 只属可选研究路径，默认不参与正式 D4 裁决。
- `C2Health` 状态机：`normal -> degraded -> suspect -> failed`，heartbeat 使用滑动窗口和 `degraded/suspect` 防抖确认，中心恢复需双轨合并，不能只靠单次 heartbeat。
- 被动降级链路：中心 C2 失效 -> 固定系留或机动高空二级侦察节点/地面备份 -> 完全无中心 CBBA。
- 主动降级仲裁：中心未失效时只输出继续中心、请求中心重分配、请求二级观测辅助或安全保持；`degrade_to_secondary/degrade_to_distributed` 只属于中心失效后的被动接管链路。
- 中心重规划请求生命周期：包顶层导出冻结 DTO `CenterReplanStatus` 和 `build_center_replan_risk_signature()`；`D4ArbitrationAdapter.evaluate(center_replan_status=...)` 只读消费 `pending|applied|acknowledged_no_change|expired`。`ActiveDegradationConfig.center_replan_cooldown_s` 默认 2.0 秒，以 `resolved_at`、pending 无 resolved 时以 `requested_at` 为起点；窗口内新增非硬风险继续 `continue_center`，在严格 `timestamp >= reference+cooldown` 边界才重新开放请求。若 pending 属于 current coalition，且中心 alive、D3 plan/coalition 双版本 current、D5 全部 current primary 已稳定 locked 并形成无冲突 consensus，D4 将旧请求收敛为 `continue_center`，输出 `center_replan_resolution_hint=acknowledged_no_change`。friend/duplicate/wrong-binding、plan/coalition version、center health、coalition conflict 或 commit 缺 ACK 均优先 fail closed，不会被 recovery 覆盖。该 `continue_center` 保留风险 evidence，不替代 D5/D7 独立门控。
- 二级节点建模：支持 `NodeRole.SECONDARY_RECON`、`MOBILE_HIGH_RECON`、`MOBILE_SECONDARY_RECON`、`FIXED_TETHERED_SECONDARY` 或 `capability_class=mobile_high_recon/mobile_secondary_recon/fixed_tethered_secondary/tethered_recon`；二级节点默认 `coordinator_only`，只做协调和侦察证据，不作为拦截执行资源。
- 二级节点生命周期摘要：`SecondaryNodeLifecycleSummary` 输出 `heartbeat`、lease、coverage、cue/gimbal/link、network full-view、stable/not-registered 计数及其 `registration_evidence_source`/presence 标志，并区分节点类型与 `not_ready|visible_only|registration_usable|takeover_ready` 四级瞬时 readiness。heartbeat/current time、cue、gimbal、communication summary 或 network full-view 缺失均不能达到 `takeover_ready`。adapter 进一步记录 `takeover_ready_consecutive_decisions`、ready since/duration、required decisions/duration、`takeover_ready_sustained` 和回落原因，供 D4 仲裁与 D6 逐决策审计。
- 增强通信摘要：`CommunicationSummary` 记录 `source_node_id`、`target_node_id`、`relay_node_id`、`link_type`、`sent_timestamp`、`received_timestamp`、`payload_kind`、`stale_after_s`，用于判断二级节点辅助链路是否新鲜。
- 主动降级迟滞/防抖：`ActiveDegradationConfig` 提供 `min_dwell_s`、`release_consecutive_consistent_frames`、`mismatch_frame_limit`、`risk_window_size`、`risk_window_threshold` 和 `center_replan_cooldown_s`；默认保持轻量单步规则，复用 arbiter 时可启用 dwell/release 行为。adapter 同时输出 hard/soft risk 拆分、center replan cooldown 状态和 `active_degradation_false_trigger_candidate`，供 D6 统计误触发。
- D2 在线指标可用性：`AssociationRiskSummary` 显式携带 `truth_metrics_available`、`continuity_available` 和连续 `duplicate_track_risk`。在线 truth 隔离时，IDSW/continuity 的数值占位不参与主动降级；`duplicate_track_risk >= 0.5` 只产生 soft `d2_duplicate_track_risk_high` 观察证据，不再合成 observed count。只有显式 `duplicate_track_count/duplicate_assignment_count`、对应 delta/delta sum 或明确 observed flag 才产生 hard `d2_duplicate_track_observed` 并立即阻断。
- D5 末端证据适用性：`TerminalAssociationSummary.terminal_evidence_applicable` 显式表示当前是否已进入末端视觉适用窗口，默认 `true` 保持旧调用兼容。窗口外不消费低 confidence、高 ambiguity、cross-view 软风险或连续非锁定/无明确观测的 mismatch streak；friend conflict、duplicate lock、resource/assigned-track mismatch 和明确 observed-track mismatch 仍保持硬门控。adapter 兼容 `evidence_applicable`、`visual_evidence_applicable`、`within_terminal_visual_window` 和 `terminal_visual_window_active` 别名，并将最终值写入 D6 event metadata。
- M-to-N 原子联盟安全语义：`CoalitionSafetyEvidence` 以 duck typing/dict 消费 D3 `assignment_plan_v2` 的 `coalitions`、member、plan/coalition version、`required_resource_count` 和可选 commit。有效 secondary/distributed commit 必须满足完整 required-member ACK、双版本、epoch、成员、lease 和 digest 门控，随后才设置 `atomic_coalition_formed=true`；无有效 commit 时仍按中心可用性输出 `request_center_replan` 或 `coalition_fallback_unsupported`/`hold_or_revoke`。event 记录 `candidate_action`、`gated_action` 和 commit 审计；single-winner CBBA 不冒充 `k>1` 成员形成。合法联盟内多个已授权资源锁定同一 `global_track_id` 不算 duplicate；联盟外、超额、旧 plan 或旧 coalition version 均 fail closed。D4 不改写 `global_track_id`。
- D5 current-coalition recovery 最小接口：`cross_view_summary` 需提供 `global_track_id`、`plan_id/plan_version`、`coalition_id/coalition_version`、`primary_required_count`、`primary_locked_resource_ids`、`primary_lock_complete`、`coalition_visual_consensus` 和 `coalition_conflict_state`；若 `coalition_commit_required=true`，还需 commit state、required/acked member IDs、valid 和 conflict reasons。字段缺失、scope 不 current 或 commit 不完整只会使 recovery 不成立。main 当前已传递该 D5 summary，D4 无需也不会修改 main adapter。
- D5 二级覆盖/转换漏斗诊断：adapter 可消费 `cue_freshness_s/cue_freshness`、`gimbal_pointing_ok`、`secondary_coverage_ratio`、`secondary_single_camera_full_view_frame_rate`、`secondary_network_joint_full_view_frame_rate`、`secondary_network_mean_coverage_ratio`、`cross_view_support_count`、`cross_view_association_count`、`stable_cross_view_registration_count`、`not_registered_count`、`cross_view_conversion_gap` 和 `secondary_detect_to_cross_view_reject_reasons`；当二级检测可见但 cross-view/global binding/registration 未完成时，event metadata 写入 `secondary_detect_available_but_not_registered`、计数和诊断原因，但不会把该证据直接升级为 `secondary_plan_active`。
- 二级侦察校准解释口径：D4 只消费 D5/D6/main 输出的 coverage、freshness、stable cross-view registration、not-registered 和 review label，不做像素投影或视觉注册。硬门限保持 score >= 0.70、coverage >= 0.65、network full-view >= 0.80；瞬时 `takeover_ready` 还必须通过默认 3 个不同时间戳决策、至少 0.2 s 驻留且相邻证据间隔不超过 1.0 s 的 `SecondaryReadinessWindowConfig`，才允许进入 pending。相同时间戳的多资源/多目标决策不会重复累计。
- 完全无中心视觉证据接入：`DistributedVisualEvidenceSummary`、`build_distributed_visual_evidence_summary()` 和 `merge_distributed_visual_evidence_into_tracks()` 可用 duck typing/dict 消费 D5 的 distributed terminal association / cross-peer hypothesis，不导入 D5 类型，也不创建或改写 `global_track_id`。
- 指标输出：`ActiveDegradationDecision.to_metrics()` 输出 `d4_action`、`degradation_mode`、`target_node_id`、`risk_factors`、`terminal_consistent`、`failover_time`、`secondary_selected_rate`、`distributed_conflict_count`。
- D6 兼容事件：`D4ArbitrationAdapter` 输出 `EventRecord` kwargs，除既有风险、review、coverage 和 capability 字段外，新增逐决策注册证据来源/presence、readiness streak/duration/sustained、`previous_state/transition`、pending since、activated at、activation delay 和 `secondary_takeover_fallback_reason`。
- 二级接管 plan metadata：`SecondaryTakeoverPlanMetadata` 明确 `not_applicable`、`pending_secondary_plan`、`secondary_plan_active` 三种状态。active 必须同时满足持续 readiness exact-true、expected/actual source 均存在且与选中二级节点一致、plan version 严格更新或保持同一已激活 secondary plan、plan/required lease epoch 均存在且前者不低于后者，并能证明 `current_time < lease_expiry`。任一字段缺失、`current_time == lease_expiry`、过期、旧 epoch 或 source mismatch 均保持 pending/not executable；已激活 secondary owner 也重新校验。D4 只输出合同和审计，不生成完整系统级 `AssignmentPlan`。
- CBBA 风格协商：用于二级节点不可用后的连续性分配基线；D5 视觉支持会提高对应资源出价，`hold`、友方冲突、过期/缺失/冲突 `global_track_id` 会阻止可执行出价，重复锁定风险进入 `assignment_audit` 且不允许多个 owner。
- CBBA gap benchmark：`build_cbba_cost_gap_benchmark()` 使用 D3/main 提供的中心 plan 与 cost matrix，计算 D4 CBBA 相对中心 Hungarian/Min Cost Flow 基线的 cost/completion/conflict/message 差距；D4 不在 no-center 路径运行虚拟中心 Hungarian。
- P2 隔离联盟 replay：`run_p2_coalition_fault_replay()` 复用原生 `CoalitionCommitCoordinator`，并将 `CBBANegotiator` 限定为协调者/补位候选选择，不把 single-winner 结果冒充 `k>1` 原子联盟。固定覆盖中心 -> 二级 -> 完全分布式、missing ACK、stale epoch、expired lease、partition、member loss/replacement，逐场景输出收敛轮数、完成率、冲突和最优差距或 `unavailable_reason`。MIT CBBA/CA-CBBA 只通过 `ExternalCoalitionReplayAdapter` 返回 path/source/capability/unavailable 审计，不替换在线 D4。
- P1 通信故障 replay：`run_p1_communication_fault_matrix()` 接收任意长度的 member/secondary 列表和 seed 集合，固定输出 `normal`、0.5 s delay、30% loss、center failure、center+secondary failure、partition+recovery 六类逐 seed 记录。记录包含层级轨迹、owner/plan/coalition version、ACK/lease/epoch、首个失败原因、消息统计、节点退出/重构、重复 owner 和 split-brain prevention；乱序旧 version ACK 被拒绝但不阻塞后续有效全量 ACK，分区恢复必须提升 generation 并全员重新 ACK。
- AirSim episode 通信接口：`AirSimEpisodeCommunicationAdapter.tick()` 读取 main 提供的单调仿真时间、中心/二级 heartbeat、消息延迟、ACK 丢弃、partition、digest 和恢复授权，逐 tick 输出 heartbeat/message/ACK、lease、epoch、owner、plan/coalition version、plan transition、commit 和恢复状态。接管收集 ACK 期间无可执行 owner；只有全部 required member ACK、lease 有效且 commit=`executing` 才发布单一 fallback owner。取消 primary 同时到达要求不会取消多成员原子授权。中心恢复必须连续通过双轨 digest 校验并取得显式授权，不因 heartbeat 恢复立即夺权。规范 episode-time 矩阵 7/7 通过：normal 误降级为 0，中心故障到二级可执行 1.25 s，二级故障到 peer 原子执行 1.00 s；missing ACK、stale epoch、expired lease 和 partition 均 fail closed。上述数字是 0.25 s tick 的逻辑故障注入结果，不是 RF/真实网络时延。
- D6 CBBA report metadata：`build_cbba_d6_metadata()` 将 `CBBAResult`、`coordination_mode`、`assignment_audit` 和可选 `CBBACostGapBenchmark` 归一化为多 seed 可聚合字段；`run_failover_simulation()` 顶层 metrics 透出 `d4_action`、`coordination_mode`、`selected_coordinator`、leader 和 coverage。
- 与 D3/D5/D6 的接口：接收上一版分配摘要，向 D5 提供区域观测/cue 语义，向 D6 输出接管、共识和冲突指标。

## 主动降级入口

`ActiveDegradationArbiter` 接收 D1 定位不确定度、D2 关联风险、D3 分配有效性、D5 末端视觉关联摘要、`C2Health` 和二级节点健康状态，输出 `ActiveDegradationDecision`。典型策略：

- D5 与分配目标一致且风险低：`continue_center`。
- D1/D2 风险升高但 D5 仍一致：优先 `request_secondary_assist`。
- D3 分配 `is_current=False` 或 `plan_age_s` stale 属于硬风险，D5 仍一致时优先 `request_center_replan`；`plan_age_s` 表示计划活性年龄，优先以 `plan.metadata.last_evaluated_at_s`（兼容 `last_evaluated_at/evaluated_at_s/evaluated_at`）为参考，缺失时才回退 `created_at`。稳定 plan ID 的身份年龄保留在证据 `metadata.identity_age_s`，不会把每帧已重新评估的稳定计划误判为 stale。`d3_assignment_cost_margin_low` 属于软证据，单独出现时只继续观察或请求二级 cue，不触发每帧重规划。
- 未进入末端视觉适用窗口时，D5 普通 `ambiguous/hold/reacquire`、低 confidence、高 ambiguity、cross-view 软风险和 non-locked streak 不参与主动辅助/重规划判定；D1/D2/D3 风险低且中心 binding 有效时直接 `continue_center`。
- 已进入末端视觉适用窗口后，D5 多帧 `ambiguous/hold/reacquire` 但没有 observed global track mismatch、资源错配、重复锁定或友方冲突时，不视为分配失效：有二级覆盖则 `request_secondary_assist`，否则 `continue_center` 并继续观察。
- D5 持续 observed global-track mismatch、资源错配、重复锁定，或 D3 plan stale/not-current、显式 `resource_feasible=False` 时，中心可用路径只输出 `request_center_replan`；friend conflict 仍 `hold_for_review`。单窗口 observed mismatch 继续受 `mismatch_frame_limit/risk_window` 防抖。
- D5 `friend_conflict=True`：强制 `hold_for_review`；`duplicate_terminal_lock=True` 不视为一致锁定。
- 二级辅助/接管必须显式提供通信摘要，并证明存在未过期的 `secondary_relay`、`video_cue` 或 `c2_direct` 链路；缺通信证据不是“跳过检查”，而是 fail-closed。
- 若二级节点 `heartbeat_timestamp_s` 超过 `heartbeat_stale_after_s`，即使视频链路摘要新鲜，也不会被选为二级接管目标。
- 机动高空侦察节点随拦截机出动但不拦截；它用 D1/D2 `GlobalTrack` 或雷达 cue 指向目标簇，中心可用时只给局部拦截群提供图像/cross-view 辅助，保持中心 plan owner/version。只有中心失效后，持续 `takeover_ready` 才允许它成为二级协调节点。仅有侦察图像、云台指向正常或 coverage ratio > 0 不会自动改变 action；event 用 `secondary_assist_requested` 与 `secondary_takeover_candidate` 分别审计辅助和接管。
- 当中心和二级节点都不可用时，D4 使用 D5 分布式视觉证据作为 CBBA 的风险/代价输入：多资源视觉支持只增加对应资源的出价，不构造“虚拟中心”，也不重新绑定 `global_track_id`。
- `--drone-count`/main runtime 的 N 只决定输入摘要数量；D4 按实际 `TrackSummary[]`、`ResourceSummary[]` 和二级节点列表长度运行，不在仲裁里固定 2v2 或 5v5。
- 2v2/5v5 AirSim ComputerVision 专项 case 只作为测试 baseline：中心可用且硬绑定失效时应 `request_center_replan`；中心 failed 且二级持续 ready 时才允许 secondary pending/active；中心和二级均不可用、证据不持续或 lease 过期时才进入 distributed。

## P0-B 状态

- 已完成：heartbeat smoothing 使用滑动窗口、miss threshold 和 `degraded/suspect/failed` dwell，短时丢包/延迟不会直接进入 `failed`。
- 已完成：secondary resource、takeover plan、active owner 和 D7 handoff 统一按严格 `current_time < lease_expiry` 校验。公开 helper 对 readiness、expected/actual source、plan/required lease epoch、expiry/current time 的 `None` 分别输出稳定 reject reason；当前 secondary-owned 同 id/version 计划只有在全套证据仍有效时才可维持 active。D7 handoff 还必须看到 `secondary_capability_class=takeover_ready`；distributed action 直接走自身 ACK/lease/epoch/commit 合同，不进入该视觉门。
- 已完成：二级能力评分区分 `not_ready`、`visible_only`、`registration_usable` 和 `takeover_ready`，并消费 coverage ratio、network full-view rate、heartbeat/link/cue freshness、gimbal、stable registration count、not-registered count 和 reject reason；只有 `takeover_ready` 会成为接管依据。
- 已完成：adapter 在瞬时门限之后增加连续 readiness 窗口；单帧或同时间戳重复的 `takeover_ready` 不会进入 pending，heartbeat/link/cue/gimbal/lease 或能力回落会清零 streak 并阻断接管。`not_ready -> takeover_ready` 边沿会重新初始化 `ready_since_s` 和 count=1，能力回落后再次 ready 也从新窗口计时。
- 已完成：主动降级继续保留 hard/soft risk、防抖和 release 条件；`terminal_consistent` 只表示 current plan 的 resource/global-track/version/coalition binding 是否仍可信。`terminal_evidence_applicable=false` 且中心正常时，低置信度、歧义、cross-view 软风险、连续非锁定/无明确观测的 mismatch streak，以及 D1/D2/D3 的非 hard-active 风险组合只保留审计，不触发二级视觉辅助；进入适用窗口后才按既有策略请求 cue。高位置/协方差不确定度、陈旧量测、observed IDSW/duplicate track、低 continuity、not-current/stale/resource infeasible、friend/duplicate terminal lock 和明确 binding mismatch 仍执行原强门控。该字段不能单独授权 terminal PNG。
- 已完成：`AssignmentValiditySummary.resource_feasible` 默认向后兼容为 true；adapter 可从 assignment/plan 字段或 metadata 读取显式可行性。不可行资源、stale/not-current plan、重复末端锁、资源/计划绑定错配和持续 global-track mismatch 在中心可用时统一请求中心重规划，不因二级 readiness 高而转移 owner。
- 2026-07-12 posefix smoke 审计：四组历史输出中分别有 1087/1094/585/1064 条 `terminal_consistent=false` 同时满足中心 owner、coalition safe 和 hard risk 为空，导致 control CSV 出现 158/112/113/122 条 `d4_terminal_inconsistent` 拒绝。根因是 D4 重复解释 D5 readiness，并由单一有状态 arbiter 跨 resource/track 共享迟滞。adapter 现按 `(resource_id, global_track_id)` 隔离状态，event 新增 `terminal_binding_reject_reasons`、`terminal_visual_state` 和 `arbitration_state_key`；旧 plan/coalition version、缺 ACK、过期 lease 继续 fail closed。历史日志不回写，需 main 重跑 AirSim 生成修复后系统证据。
- 已完成：D2 online truth 隔离语义已接入 D4；`truth_metrics_available=False`/`continuity_available=False` 时不再把 `id_switch_count` 或 `track_continuity=0` 占位解释为硬风险，在线 ambiguity/duplicate/quality 风险路径保持有效。

## P1 状态

- P1 联盟合同结论仍以 `p1_p2_validation_20260711/P1_P2_VALIDATION_SUMMARY_CN.md` 为准：D4 所属合同层已闭合。2026-07-12 PNG delivery 的 M5N2 `0/9` 是历史短窗口结果；2026-07-15 已完成中心继续执行的 baseline/candidate 各 10 seeds，最新同口径负对照为 coalition `0/20`、第二 primary 5 m `0/20`、`active degradation=0`。该更新不关闭 D4 物理协同、真实 fallback 扰动、成员重构/恢复或误降级标定缺口。
- `d4_p1_failover_disturbance_replay_v1` 已形成版本化九场景矩阵：正常中心无误降级、二级完整 ACK 接管、缺 ACK、手工预编排的成员丢失/替换、分区/恢复、旧 epoch、过期 lease、digest conflict 和中心恢复双轨审计均通过。replay 中替换后的联盟必须提升 epoch/plan/coalition version 并全员重新 ACK；这不代表在线 D4 已实现自主 reserve 发现、激活、缩编、补位或整盟重组。中心恢复不立即夺权，D4 不生成 `AssignmentPlan`，不降低 D3/D5/D7 gate。
- `d4_p1_communication_fault_replay_v1` 已完成 10 seeds x 6 场景的 60/60 安全结果：正常中心误降级为 0；0.5 s 延迟 10/10 完整提交；30% 丢包下 3/10 完整 ACK 后执行、7/10 缺 ACK 后 fail-closed；中心失效 10/10 降到二级，中心和二级连续失效 10/10 降到 distributed；分区恢复 10/10 使用新 epoch/version 全量 re-ACK，并拒绝旧 owner。重复 owner 和 split-brain prevention failure 均为 0。
- 2026-07-21 全样本准入阶段为 397/397 项通过，新增专项 10/10；加入运行时确认、区域奖励合同、冻结 bundle 隔离加载和候选门诊断回归后，该历史阶段 D4 全量为 482/482。2026-07-25 当前全量为 569/569。正式和补充数据的模块内准入状态为 complete，但 D6 外部带外 SHA256 复核、真实运行时 ACK/outcome、可归因 reward、20-seed 同 seed paired outcome、真实链路、误降级率、恢复时间和物理任务连续性仍开放。机器可读准入固定禁止把规则教师标签、后投影 recommendation、隔离采用或低损失写成运行策略能力、applied ACK 或 assist 资格。
- 二级接管正例：协调者 `Secondary_Recon_1`，required-member ACK 3/3，最终 `executing`，D4 动作为 `degrade_to_secondary`。
- 完全分布式正例：协调者为 `INT-02` peer，required-member ACK 3/3，最终 `executing`，D4 动作为 `degrade_to_distributed`。
- 缺 ACK 负例：确认窗口显式截止时 ACK 仍为 2/3，最终 `aborted`；T001 三个成员保持 `hold_for_review`，D7 许可为 0。普通快照在截止前保持 `collecting_acks`。该结果确认 fail-closed；有有效 commit 的二级/分布式路径已获正例验证。
- SimpleFlight 15 s 结果仅用于断点诊断：30 个 active pair 物理命中为 0，不能据此宣称 D4 fallback 或系统物理拦截闭环完成。
- 仍开放：将已冻结的 P1 扰动合同映射到真实 AirSim 同 seed 成对试验，完成 heartbeat/link/cue/gimbal/source、secondary-interceptor/peer split、误降级、恢复时间及物理连续性多 seed 统计。模块 replay 不等于系统矩阵验收完成。
- P2 只允许隔离式 benchmark；MIT/第三方 CBBA、auction/contract-net 或其他 adapter 不替换当前轻量 CBBA 和 ACK/lease/epoch 合同。
- P2 原生确定性 replay 已收敛：6/6 场景符合预期安全结果；中心 -> 二级 -> 分布式和手工预编排的 member-loss/replacement 场景均以 7 轮、完成率 1.0、冲突 2/1、最优绝对差距 0.0 收敛。该结果只验证调用方给定替换成员后的版本/ACK 合同，不是自主补位能力。missing ACK、stale epoch、expired lease、partition 分别以 2/1/2/3 轮 fail closed，完成率均为 0，并输出对应 optimality-gap unavailable reason。
- 默认环境未配置 MIT CBBA 或 CA-CBBA 参考路径，因此各 6 个外部对照行分别输出 `mit_cbba_reference_path_not_configured`、`ca_cbba_reference_path_not_configured`。MIT MATLAB 源码树即使被检测到也报告 runtime adapter 未集成；已审计的 CA-CBBA 公共仓库没有可执行源码。上述 unavailable 是 capability 结论，不是外部算法性能结论。

历史基线：2026-07-10 calibration sweep 和 2026-07-11 早期 truth-isolated smoke 曾因 network full-view/readiness 不持续而未形成二级 active plan。该结论只描述实施前场景，不再作为当前能力状态；门限与 fail-closed 规则仍保留。
