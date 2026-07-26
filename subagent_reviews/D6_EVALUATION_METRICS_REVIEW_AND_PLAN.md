# D6 系统评估指标综述及子方案

## 2026-07-26 D3 A1 与 D4 A2 预准入外部审计评审

D3/A1 和 D4/A2 的模型文件存在，不代表学习算法已经在正式作用域内实际工作。D6 将静态候选
绑定、当前实现绑定和正式运行证据分成三层。任一层缺失或来源不一致，最终 consumer contract
失败关闭。

静态层核对数据 manifest、数据内容、seed 切分、全样本审计、模型 manifest、weights 和
readiness。实现层对角色固定的源文件逐项计算 SHA-256，再对有序文件摘要计算实现 SHA-256，
并与数据、模型和来源 commit 交叉绑定。运行层只接受既有正式作用域审计器输出的
`d6.learning-scope-formal-evidence-audit.v1`，同时复核报告文件和 `SHA256SUMS`。

两个角色的采用证据不同。A1 必须在隔离执行中出现正的
`d3_learning_applied_count`，A2 必须出现正的
`d4_advice_control_adoption_count` 运行确认。正式报告还需证明预检与 episode 诊断一致。
shadow、规则 fallback、仅加载 bundle 或采用为 0 均被拒绝。开发态 bundle 可以作为预准入
候选，但不能用开发态声明替代实际采用证据。

每个学习单元按 comparison key 查找 R0。D6 从正式报告的 R0 scope 建立索引，要求同键只有一个
可接受 R0，pair 中的 `r0_cell_id` 与实际单元一致，且同一 R0 不被多个 key 复用。拦截目标数和
离线五米接近唯一目标数是必选非退化指标。缺指标、指标不可用或任一指标退化均失败关闭。

当前实物不具备正式作用域和实现证据。D3/A1、D4/A2 的正式学习 episode 均为 unavailable，
不是观测到的 0；候选 manifest 中声明的 holdout 已评估数才是 0。两份冻结配置还分别与当前
D3、D4 实现摘要不一致。因此严格复跑均为 `fail_closed`，各 15 个 blocker。D6 没有调整门限、
替换摘要、启动 900 单元矩阵或删除旧输出。

D3 严格结果的 JSON 文件/内容 SHA-256 为
`837f95c6...529` / `c1db7bb0...c0a`；D4 为
`0547fe50...c0a` / `e5a11679...830`。专项测试
`31 passed, 1 warning`，D6 全量 `975 passed, 1 warning in 103.81s`。

后续由 D3、D4 各自生成 clean-source 实现证据和至少 20 个未见 seed 的正式作用域，再由各自
assembler 消费 D6 合同。D6 不授予 promotion、assist、默认路径或控制权限。AirSim 运行接口
未变化，相关集成文档已检查，无需修改。

## 2026-07-26 D5 G1 正式外部审计

D6 将 D5 G1 预准入输入收敛为一个内容寻址的外部审计合同。合同同时绑定模型、训练数据谱系、
20-seed held-out、同权重 paired-shadow、逐 episode 谱系、当前运行实现和三项安全计数。D5
后续装配器只能消费该合同，不能用调用方构造的正向布尔值替代实物复核。

99fa 候选的两次审计保留为历史失败记录。其问题包括实现谱系漂移、单特征 AUC 超限和扰动
性能不足。D5 随后在 clean source chain 上生成 7fb5 robust-v2 候选，并由 `fa3ec10` registry
producer 发布正式冻结目录。D6 没有复用 main 的临时预检，独立复算九类文件、两份校验清单、
两份 JSON 内容摘要和十个运行时源文件摘要。当前实现摘要为 `408e71fe...f4fe`。

2026-07-26T14:01:34Z 正式外审通过。输入包含 seed `1000-1019`、900 个 episode、45 个场景规模
单元、13,344 个匿名局部航迹节点和 74,024 条候选边。held-out F1、错误合并率、候选召回和
P95 推理时延达到冻结门。最高单特征 AUC 为 `0.720073 <= 0.98`；五类扰动最低边/簇 F1 均为
`1.0 >= 0.9`。在线真值字段、`global_track_id` 改写和同相机互斥违规均为 0。blocker 为空。

正式输出位于 clean worktree 的
`outputs/d5_g1_external_audit_7fb5db8b_fa3ec10_20260726/`。主 JSON 文件/内容 SHA-256 为
`10bf19f5...10b0` / `4e24ab33...9e54`，输出校验清单复算通过。专项测试为
`14 passed, 1 warning in 4.54s`，D6 全量为 `975 passed, 1 warning in 86.70s`。

D6 的模型晋级、G1 辅助、控制和默认路径权限仍全部关闭。通过结果只允许 D5 继续执行自己的
准入装配。五类扰动固定 post-gate 候选图，尚未验证重投影、门控和候选生成全链路；当前证据
也不包含真实相机、真实外参漂移、真实遮挡和在线检测误差。G1 实际运行后仍需
`learning_scope_formal_audit` 对实际采用、回退、在线真值、物理结果和同键 R0 做第二层审计。
当前无 D6-owned P0。

## 2026-07-25 正式实验矩阵准入评审

D6 已将正式算法矩阵拆成“预期清单”和“运行证据”两层。预期清单必须来自 main 的实际
`ExperimentMatrixPlan.cells()` 或显式 cell inventory。运行目录、场景名和规模维度不能用于
补出缺失 cell。该约束使 F1 的场景范围由生产合同决定，当前默认计划为 5700 个 cell。
CLI 未提供 inventory 时显示的 expected=0 是缺输入拒绝路径，不是正式清单结果。

`pre_run` 检查清单、seed 隔离、clean source 和模型制品。`post_run` 再核对矩阵 manifest、
运行 cell、D6 逐 seed 证据、算法采用、回退、在线真值、有限状态、身份交换、五米物理指标、
置信区间输入和交付制品。任一字段 unavailable 都保留 unavailable，不转换为 0。

当前正式计划清单本身通过：七个变体、九类场景、五档规模、20 个未见 seed、训练 seed 交集为
0、无重复 cell。当前运行状态未通过。仓库中没有正式矩阵 manifest；四个学习模型的文件和内部
权重哈希一致，但 D3、D4、D5 图模型和 D5 主动视觉模型都没有 assist 授权。因此当前结论为
`fail_closed`，5700/5700 cell 保持未准入。

下一步应先由各模型 owner 完成独立准入，再由 main 在 clean detached worktree 冻结 expected
inventory 和 model inventory。D6 先跑 `pre_run`；只有通过后才值得分批生产正式矩阵。矩阵
完成后执行 `post_run`，D6 不承担模型授权或控制决策。

专项测试 `9 passed`，D6 全量 `889 passed, 1 warning`；既有 main 矩阵合同
`7 passed, 1 warning`。当前静态报告的三项 SHA-256 校验通过。

## 2026-07-25 D1 在线发布证据子集快照正式独立评审

D6 已完成 schema
`d6.d1_publication_evidence_snapshot_multiseed_evaluation.v1` 的独立评估。正式来源固定为
producer commit `d0219eb14c529a4fb9bf7d6610a9f32055a09206`、matrix SHA
`6c808c4df8759fd893c6d37ff9dce4a1efa07f9867fc71aff47a55c5f8517338` 和
manifest SHA `67813a3e850759dd4c194add4b622870345118aec5acdf74d2480f86c00735b4`。
矩阵包含 short 10 对和 long 3 对，规模为 200 个目标、200 个资源、2 个侦察节点。

参考臂每次发布读取完整 consistency 快照。候选从同一发布周期的源观测标识和已物化航迹最新
观测标识构造去重、有序的必要集合。任何非法标识、未知标识、缺失返回记录或空集合都应回退到
完整快照。正式诊断中这些异常均未发生。

D6 不使用 producer admission 结论。评估器重算五个实现表面、唯一命令处理差异、回放前缀参考
身份、D1/D2 在线记录语义、业务计数、离线 consistency digest/count、原 D1 操作计数、资源
统计及配对 bootstrap。13/13 pair 的语义与安全合同通过，429 次候选选择全部成功。

返回记录从 `1602170` 减至 `133917`，削减 `91.641524%`。性能结果如下：

| 门限 | 实测 | 判据 | 结果 |
| --- | ---: | ---: | --- |
| short candidate faster | 4/10 | >=8/10 | 失败 |
| short D1 融合改善 | -0.147877% | >=1% | 失败 |
| short bootstrap 原始变化上界 | 1.374681% | <=0% | 失败 |
| long candidate faster | 2/3 | >=2/3 | 通过 |
| long D1 融合改善 | 1.047143% | >=1% | 通过 |
| 全矩阵返回记录削减 | 91.641524% | >=50% | 通过 |

short/long core、D2 和 RSS 门通过。三个 short 门失败使 verdict 为 `reject`，
`main_default_promotion_allowed=false`。候选最低实时因子为 `0.203423`，系统实时门独立失败。
结论只覆盖冻结三维质点矩阵。候选保持默认关闭，参考实现保持默认。

同一 manifest 的重复评估与正式 bundle 逐文件一致。聚焦测试为 `14 passed`，D6 全量为
`880 passed, 1 warning in 76.17s`。

## 2026-07-25 D1 回放前缀摘要正式独立评审

D6 已完成 `d6.d1_replay_prefix_summary_multiseed_evaluation.v1` 的正式独立评估。评估器固定读取
producer clean commit `7d2e987471b521a1e531bf03a5c99af5096f676a` 和 matrix SHA
`85432d729877eff97e6f3dd517d4baa7a47f44a4fa42e6bfdc7ce85b8d9ec74b`。参考实现为
`per_checkpoint_prefix_rebuild_v1`，候选实现为
`fixed_lag_checkpoint_prefix_cumulative_summary_v1`。D1 模块微基准和 clean seed-1151 预检
没有进入正式样本。

正式矩阵包含 short seeds 1151-1160、long seeds 1151-1153，共 13 pair 和 26 个 fresh
complete episode。每个 episode 使用 200 个目标、200 个资源和 2 个侦察节点；0 reused、
0 failed。两臂来自同一 clean commit，只允许回放前缀摘要 selector 不同。

评审口径包含业务语义、在线 consistency records digest/count、D1 原有操作计数、导出前后
pending ledger、summary hit/reuse、append revision/preservation 和 snapshot projection。
13/13 pair 的业务语义、digest/count、原操作计数、实现身份、诊断守恒、有限状态和在线真值隔离
通过。内部逻辑刷新 `811858` 条记录，实际物化 `388468` 条，减少 `52.150746%`；在线快照仍
投影构造 `656481` 条记录。

冻结性能门实测如下：

| 门限 | 实测 | 判据 | 结果 |
| --- | ---: | ---: | --- |
| short candidate faster | 5/10 | >= 8/10 | 失败 |
| short D1 融合改善 | 0.959611% | >= 1% | 失败 |
| short bootstrap 原始变化 95% 上界 | 0.619827% | <= 0% | 失败 |
| short core wall 改善 | -0.256641% | >= 0.25% | 失败 |
| long core wall 改善 | -1.930083% | >= 0.25% | 失败 |
| long D1 融合改善 | 2.361778% | >= 1% | 通过 |
| 内部物化减少 | 52.150746% | >= 20% | 通过 |

short/long RSS 和 D2 组均值门通过。五个失败门使正式 verdict 为 `reject`，
`main_default_promotion_allowed=false`。候选最低实时因子为 `0.197441 < 1`，
`system_realtime_gap_closed=false`。候选保持默认关闭，参考实现保持默认。

正式 bundle 位于
`research_modules/d6_evaluation_metrics/outputs/d1_replay_prefix_summary_multiseed_20260725_formal_7d2e987_d6/`。
目录内 `SHA256SUMS` 已通过。main 使用同一 manifest 重跑，全部输出 SHA-256 与正式 bundle
一致。该结果仅适用于 2026-07-25 的三维质点仿真，不代表 AirSim、目标处理器、硬件、实机或
实飞性能。

后续若继续处理在线快照投影成本，应定义新候选名，并在新预注册矩阵上重新评估。不得调低本轮
门限、删除 pair 或覆盖本次 `reject`。

## 2026-07-25 D1 关联稀疏预筛正式评审

D6 已完成 `d6.d1_association_sparse_prefilter_multiseed_evaluation.v1` 独立 evaluator、CLI 和
确定性报告，固定绑定 matrix SHA
`a7162d014d1c3c0f207355b24a5d7159bf3486d134ca21876f7469d1e915b71d`、clean source commit
`9302ccede2ca513c2235370e1a464fc88bc41150`、short 10 pair、long 3 pair 和 200/200/2。
reference 为 `disabled_v1`，candidate 为
`modality_conservative_quadratic_bound_v1`。

评审确认 evaluator 不接受 producer admission，也不依赖 runner 私有验收函数。它严格校验
manifest/matrix SHA、fresh episode、双臂唯一 treatment、命令和路径，并在 runtime profile、
summary、module final、governance 及两个冗余表面交叉确认 selector、完整 implementation ID、
execution config 和 diagnostics。六个模态桶、逐桶计数上界、总计守恒、finite state 和 online
truth use=0 均由 D6 复核。

业务语义逐 pair 调用规范跨 episode 比较器重算。只归一化预注册 treatment、对应
execution config/diagnostics、关联精确求解诊断、运行时哈希派生 episode ID 和性能字段；
在线消息、D1-D7 业务结果、D3 计划谱系、D4 内容地址与 ACK 和离线 truth 制品不豁免。
13/13 pair 业务等价，reference/candidate 的 exact gate-pass 计数逐 pair、逐模态完全相等。

候选全矩阵 radar 的 candidate/rejection/solve/gate-pass/fallback 为
`9199071/9145313/53758/48321/3773`，eo 为
`801650/258272/39837/3979/37571`，lidar/acoustic/acoustic_3d/other 均为 0。非雷达精确求解
由 `298109` 降至 `39837`，减少 `86.636767%`，通过 20% 门。

性能实测如下：short D1 fusion/core 改善 `0.228437%/0.091096%`，候选更快 `7/10`，
bootstrap 原始变化 95% CI 为 `[-0.946192%, 0.443531%]`；long D1 fusion/core 改善
`0.713776%/0.490650%`，候选更快 `3/3`。short/long scan input 变化
`-0.452226%/-0.470110%`，D2 变化 `+0.559480%/-0.453717%`，RSS 组均值最大增幅
`0.026850%`、任一 pair 最大增幅 `0.077909%`，这些非退化门均通过。

五个冻结门失败：short 更快数、short D1 fusion 改善、short bootstrap 上界、short core 改善和
long D1 fusion 改善。正式 verdict 为 `reject`，
`main_default_promotion_allowed=false`；不得通过调门、删 pair 或语义豁免晋级。候选最低实时
因子为 `0.206273`，所以 `system_realtime_gap_closed=false`。

正式 bundle 位于
`research_modules/d6_evaluation_metrics/outputs/d1_association_sparse_prefilter_multiseed_20260725_formal_9302cce_d6/`；
`SHA256SUMS` 全部通过。定向测试 `13 passed, 1 warning in 7.22s`，D6 全量
`859 passed, 1 warning in 64.83s`。结论只适用于三维质点矩阵，不代表 AirSim、目标硬件、
实机或实飞。`AIRSIM_INTEGRATION_PLAN.md` 与
`D6_M_TO_N_EVALUATION_FRAMEWORK_REVIEW.md` 已检查，本项不改变其接口或指标合同，无需修改。

## 2026-07-25 D1 在线批帧交接正式评审

D6 已完成 `d6.d1_online_batch_frame_multiseed_evaluation.v1` 独立 evaluator、CLI 和确定性
报告，固定绑定 matrix SHA
`4afbf9ac273763a16aa01cc744fd67b52e437099460b33377a128f986ac5719b`、clean commit
`43feaf600f288a85ce76a76862334256f0d0d352`、short 10 对、long 3 对和 200/200/2。

评审确认 evaluator 不接受 producer admission。它逐层绑定 runtime profile、summary、module
final、nested governance 与 governance audit 的 selector、implementation ID、execution config
和 `d1.online_batch_frame_handoff_diagnostics.v1`，从原始 episode 重算有限状态、online truth、
业务语义、批帧守恒、scan/core/D2/RSS/实时因子和资源回归。

计划语义采用窄范围归一化：独立运行的 opaque plan ID 和由其派生的内容地址可不同，但必须先验证
原始 source plan/guidance SHA、ACK、D4 authority 内容地址和连续版本，再按首次出现谱系映射。
assignment、授权、target/resource binding、owner/coalition 业务字段、lease 有效性关系、状态机、
计数、安全结果与下游引用继续比较。不得为通过 gate 忽略真实计划差异。

正式实测为：13/13 业务语义、有限状态、实现身份、批帧审计通过，online truth use=0；
short/long candidate faster 为 `10/10`、`3/3`，scan input 改善
`38.289241%/36.275282%`，core wall 改善 `4.252745%/4.916501%`，D2 组均值增幅
`2.113047%/2.830616%`，RSS 最大组均值/任一 pair 增幅 `0.281879%/0.856727%`。重复检查
减少率、closed handoff ratio 均 `100%`，fallback=0；全部冻结 gate 通过，结论 `admit`。

候选最低实时因子为 `0.204490`，所以 `system_realtime_gap_closed=false`。该结论只适用于
2026-07-25 三维质点矩阵，不代表 AirSim、目标处理器、实机或实飞。正式 bundle 位于
`research_modules/d6_evaluation_metrics/outputs/d1_online_batch_frame_multiseed_20260725_formal_43feaf6_d6/`，
重复运行哈希一致。后续只保留系统实时容量和外部运行面证据，不重解释本次局部准入。
定向测试 `12 passed, 1 warning`，D6 全量 `846 passed, 1 warning in 59.24s`。

## 2026-07-25 D1 不透明来源标识缓存正式评审

D6 已完成独立 evaluator、CLI、失败关闭入口和确定性报告。评估 schema 为
`d6.d1_opaque_source_identity_cache_multiseed_evaluation.v1`，固定绑定 matrix SHA
`218d04f3fc4a764fef82de612c78c8fbb5490380ae5d20aff6b9089635f2060d` 与 clean producer
commit `d8fc76c066f21b077154f7be33c0b43558d237e5`。参考实现为
`per_publication_build_v1`，候选为 `bounded_generation_lru_v1`，缓存容量 1024。

评审确认本次 evidence 仅来自显式来源键发布面，结构歧义 hold 关闭。D6 在 runtime profile、
summary、module final、嵌套治理和独立治理中交叉确认 selector、实现 ID 和诊断。候选要求请求、
命中、缺失、旁路和构造守恒，旁路为 0；参考要求全部请求均旁路并构造，且无缓存活动。两臂请求
工作量和 publisher node/epoch generation 相同。

业务比较只处理预注册 selector、缓存诊断、runtime profile SHA、派生 episode 标识和性能字段。
在线 `GlobalTrack`、来源键值、状态与协方差、D2/D3/D4/D5/D7 输出、计划版本、控制语义和离线
真值继续逐条比较。任一非登记差异使语义门失败。

正式矩阵包含 short 10 pair、long 3 pair，共 26 个 fresh complete arm；0 reused、0 failed。
13/13 pair 的业务语义、有限状态、在线真值隔离、实现身份和缓存审计通过。short/long D1 融合
改善 `9.465972%/6.437432%`，核心墙钟改善 `2.845610%/2.728043%`，候选分别
`10/10`、`3/3` 更快。标识构造减少率和命中率均为 `99.163670%`，容量峰值
`202/1024`。

long D2 关联组均值增幅为 `5.605213%`，超过冻结上限 `5%`。这是唯一失败门。
`long_seed_1101` 单 pair 增幅 `19.069868%`，按预注册矩阵保留。评审结论为
`optimization_admitted=false`，不得通过删样本、调门或业务语义豁免晋级。后续只能以新的
预注册确认矩阵复核该回归。

候选最低实时因子为 `0.193887`，低于门限 1，
`system_realtime_gap_closed=false`。结果只覆盖 source-only、hold=false 的 200/200/2 三维质点
矩阵，不代表默认无来源键 R0、AirSim、目标处理器或实飞。

正式 bundle 位于
`research_modules/d6_evaluation_metrics/outputs/d1_opaque_source_identity_cache_multiseed_20260725_formal_d8fc76c_d6/`。
聚焦测试 `16 passed, 1 warning in 5.85s`，D6 全量
`834 passed, 1 warning in 59.24s`。`AIRSIM_INTEGRATION_PLAN.md` 与
`D6_M_TO_N_EVALUATION_FRAMEWORK_REVIEW.md` 已检查，本项不改变对应接口或指标合同，无需修改。

## 2026-07-25 D1 结构化数值雅可比评估评审

D6 已完成独立 evaluator、CLI 和确定性 writer。评估 schema 为
`d6.d1_structured_jacobian_multiseed_evaluation.v1`，固定绑定 matrix SHA
`c6c3cf53c89dfb3155a29ba49bb77a12c8bdf1a5d433c4f645de0d00c506d478` 与 clean producer
commit `9d1f54f8540fdc4a7a1011121aafac5718290122`。参考实现为
`dense_output_probe_v1`，候选为 `known_dimension_structural_columns_v1`。

评估器不参与控制。它只接受 13 pair、26 个 fresh complete arm，并核对 source clean 状态、返回
码、命令隔离、路径边界和输入哈希。selector、完整实现 ID、schema、candidate flag 和操作数在
runtime profile、summary、module final、嵌套 governance 与独立 governance 中交叉确认，四份
最终诊断必须相同。

操作数审计要求两臂 Jacobian attempt 工作量相同。参考臂每次 attempt 使用 13 次量测函数求值；
候选臂的量测求值数与非活动列省略数必须覆盖六维状态的十二次中心差分。未知字段、负数、失败调用、
实现混用或守恒破坏均使 evidence unavailable。

性能门固定为 short/long D1 fusion 改善至少 2%、core wall 改善至少 0.5%、候选更快数至少
`8/10` 和 `2/3`，short 配对 bootstrap 上界小于 0。D1 scan input、D2 association 和 RSS
增幅不得超过 5%，量测函数求值减少率不得低于 35%。局部准入和系统实时门分别计算。

合成合同测试已覆盖通过、拒绝、缺字段、版本错配、来源、诊断、守恒、业务语义、性能、dirty、
reused、命令和路径边界。输入无效时输出 `availability=false` 和 reason，不触发准入或默认晋级。

main 已完成正式 D6 评估。26/26 arm 均为 fresh complete，0 reused、0 failed；
`availability=true`。短时 D1 融合/核心墙钟改善 `6.084778%/1.897370%`，`10/10` 更快；
长时改善 `4.676061%/1.786530%`，`3/3` 更快。量测函数求值减少
`53.846154%`，全部冻结准入门通过，评审结论为 `optimization_admitted=true`。

候选最低实时因子为 `0.180726`，低于门限 1，所以
`system_realtime_gap_closed=false`。正式结论只覆盖 200/200/2 三维质点冻结矩阵，不自动关闭
AirSim、目标硬件或实飞实时缺口。main 已在 D6 评估之外完成 scalable 3D 默认晋级：
`IntegratedStackConfig` 与 `run_episode` CLI 默认使用
`known_dimension_structural_columns_v1`，并保留 `dense_output_probe_v1` 显式回退。D1 独立
`FusionAdapter` 默认实现不变。scalable 测试通过；2v2 默认 smoke 的三处配置/摘要/治理表面均
记录候选实现，有限状态为 true，在线真值使用为 0。该 smoke 不替代系统实时证据。正式报告位于
`research_modules/d6_evaluation_metrics/outputs/d1_structured_jacobian_multiseed_20260725_formal_9d1f54f_d6/`。
专项为 `20 passed, 1 warning in 6.05s`，D6 全量为
`818 passed, 1 warning in 55.42s`；warning 为既有 Matplotlib `Axes3D` 环境提示。
`EXPERIMENT_REPORT.md` 已同步正式结果。`AIRSIM_INTEGRATION_PLAN.md` 与
`D6_M_TO_N_EVALUATION_FRAMEWORK_REVIEW.md` 已检查，本项不改变其接口或指标合同，无需修改。

## 2026-07-24 在线真值检查正式评估评审

D6 已完成 `d6.online_truth_guard_multiseed_evaluation.v1` 只读 evaluator。它严格绑定
producer matrix SHA
`764574b9897d00101c26c555de2f407e1736c7e6ff50420eebf131e154618dc8` 与 clean source
`8d8bb6ed7a417705236835f235361f45a021bb2b`。参考/候选实现固定为
`generic_recursive_v1/builtin_specialized_recursive_v2`，候选保持默认关闭。

评审确认以下合同已经实现：

1. 13 个 pair、26 个 arm 的规模、seed、时长、执行顺序、命令、路径、状态和来源均显式绑定；
   reused、dirty 和失败 arm 不进入结果。
2. 每个 arm 从 runtime profile、summary 和 diagnostics 交叉确认实际 selector，并独立复算
   在线消息数。`validation_count` 必须与消息数相等且大于 0。
3. D6 重新计算所有输入文件 SHA-256，固定 config、runtime profile、governance、stage timing
   和 diagnostics schema。
4. 业务比较只归一化预注册处理字段。在线消息、D1-D7 业务计数、计划谱系、治理和离线真值继续
   逐对检查。
5. 发布总线主阶段和 finalize 相加后进入 10% 改善门；核心墙钟使用 0.5% 门，D1/D2 和 RSS
   使用 5% 非退化门。short/long 分组和 bootstrap 规则均已冻结。
6. 报告分别输出 `optimization_admitted` 和 `system_realtime_gap_closed`，不以局部加速替代
   系统实时结论。

main 已完成正式 13-pair/26-arm matrix。26 个 arm 全部 fresh complete，0 reused、0 failed；
13/13 pair 的业务语义、有限状态、在线真值隔离、实现身份、来源和检查数守恒通过。参考与候选各
94074 条消息完成递归检查，在线真值使用为 0。

short 发布总线及收尾由 `0.900293 s` 降至 `0.696858 s`，改善 `22.58%`，10/10 更快；long
由 `3.810588 s` 降至 `2.834910 s`，改善 `25.63%`，3/3 更快。short 核心墙钟改善
`2.50%`。long 核心墙钟回退 `3.47%`，long D1 融合与 D2 关联分别增加 `5.29%`、
`7.34%`，超过预注册门限。

评审结论为 `optimization_admitted=false`，候选 `builtin_specialized_recursive_v2` 不替代默认
`generic_recursive_v1`。候选最低实时因子为 `0.165369`，
`system_realtime_gap_closed=false`。正式结果已写入 `EXPERIMENT_REPORT.md` 和
`outputs/online_truth_guard_multiseed_20260724_formal_8d8bb6e/`。后续 balanced-order v2
只作独立诊断，不覆盖 v1 正式结果。正式结果同步后专项
`14 passed, 1 warning in 4.46s`，D6 全量
`798 passed, 1 warning in 52.01s`。

`AIRSIM_INTEGRATION_PLAN.md` 和 `D6_M_TO_N_EVALUATION_FRAMEWORK_REVIEW.md` 已检查；本项只消费
三维质点证据，不改变 AirSim 或 M-to-N 指标合同，因此无需修改。

## 2026-07-24 D1 常速度模型缓存评审

D6 已接受缓存评估接口实现。独立 evaluator 固定绑定 matrix SHA
`9898656598f0fa282620afe2384a3d656b7496f8957109c413bcb62069fd2e9a` 与 clean source
`44223566439a446fc49f2a3fd861d1d51bd676b9`，不允许调用方替换矩阵、提交、容量或准入门。
参考/候选身份为 `per_prediction_build_v1/bounded_exact_lru_v1`，容量固定为 128。

评审确认以下边界已实现：

1. 26 个 arm 必须 fresh complete、零返回码、同一 clean commit；证据路径、命令和 13 个 case
   顺序全部显式绑定。
2. 初始与最终缓存诊断分开验证。最终诊断在 summary、module final、嵌套治理和独立治理中必须
   完全一致。
3. candidate 的请求和模型构造守恒、reference 的零缓存活动、两臂相同预测工作量、容量边界、
   构造减少率和命中率均有正反测试。
4. D6 自行生成跨 episode 语义比较，只排除预注册的 runtime profile hash 差异。缓存字段被归一化
   后仍单独严格审计，其他业务字段不被整体忽略。
5. short/long D1、D2、核心墙钟、RSS、实时因子和缓存效率门全部来自冻结矩阵。局部准入与系统
   实时缺口分开输出。

评估器实现阶段专项为 `13 passed, 1 warning in 5.03s`，D6 全量为
`784 passed, 1 warning in 48.64s`。warning 是既有 Matplotlib `Axes3D` 环境提示。

main 已在冻结 clean source 上完成正式矩阵。26 个 arm 全部 fresh complete，0 reused、0 failed。
D6 对完整 JSON、compact JSON、含 13 条 pair 记录的 CSV、中文 Markdown、PNG 和
`SHA256SUMS` 完成只读复核。13/13 pair 的业务语义、有限状态、在线真值隔离、实现身份和缓存
审计通过；19/19 准入门通过。

short/long D1 融合改善为 `6.9271%/6.6103%`，核心墙钟改善为
`2.4060%/2.4537%`，D2 关联增幅为 `-0.1082%/-2.6729%`，RSS 均值增幅为
`0.0145%/0.2959%`。模型构造减少率和缓存命中率均为 `99.5960%`，short `10/10`、long
`3/3` 更快，short bootstrap 上界为 `-6.0841%`。评审接受冻结三维质点矩阵内的局部准入，
`d1_optimization_admitted=true`。

候选最低实时因子为 `0.17394990897894075`，低于 1，
`system_realtime_gap_closed=false`。该结果不自动关闭 AirSim、目标硬件、传感器精度、实飞或
物理拦截缺口。正式 bundle 位于
`research_modules/d6_evaluation_metrics/outputs/d1_cv_motion_model_cache_multiseed_20260724_formal_4422356/`。

`EXPERIMENT_REPORT.md` 已新增正式结果。`AIRSIM_INTEGRATION_PLAN.md` 和
`D6_M_TO_N_EVALUATION_FRAMEWORK_REVIEW.md` 已检查；本项不改变 AirSim 接口或 M-to-N 指标合同，
因此无需修改。本次文档同步后 D6 全量回归为
`784 passed, 1 warning in 55.02s`。

## 2026-07-24 D1 发布元数据 v2 正式评审

D6 已按独立 schema 消费 clean commit `be399e138762f5e660f553c8caa812d52ab38c61`
生成的 13 pair、26 arm 证据。评估器精确绑定冻结矩阵、规模、seed、时长、命令、实现 ID、
`d1.publication_audit_tree.v2` 合同、返回状态和资源记录，v1 评估路径保持兼容。

D2 审计被登记为处理差异诊断。候选的合同校验、完整内容审计和身份复用，以及参考的内建等价复用
分别严格验证。业务比较只归一化该审计字段，不忽略整段 summary。13/13 业务语义、有限状态、
在线真值隔离、实现身份和审计通过。

short/long D1 融合改善为 `13.5447%/26.8298%`，核心墙钟改善为
`6.5677%/18.2438%`，D2 关联增幅为 `-16.1939%/-35.6213%`。所有预注册局部门通过，
`d1_optimization_admitted=true`。候选最低实时因子 `0.17308010045846806`，所以
`system_realtime_gap_closed=false`。正式 bundle 位于
`research_modules/d6_evaluation_metrics/outputs/d1_publication_metadata_v2_multiseed_20260724_formal_be399e1/`。

当前后续项只保留系统实时容量和逐批审计可定位性。该结果属于三维质点，不写作 AirSim 或实机证据。
`AIRSIM_INTEGRATION_PLAN.md` 已检查，本项未改变 AirSim 接口，无需修改。
v1/v2 专项为 `37 passed, 1 warning`，D6 全量为
`771 passed, 1 warning in 47.61s`。

## 2026-07-24 D1 航迹发布元数据正式评审

D6 已实现独立、失败关闭的
`d6.d1_publication_metadata_multiseed_evaluation.v1` consumer。它只接受固定 clean commit
`a36f519ed954a9ba8bdc3fe149ba2835da290c39` 的 13-pair 矩阵，规模为 200 个目标、200 个资源和
2 个侦察节点。参考/候选 selector 固定为 `per_track_copy_v1/immutable_shared_v1`。

评审先验证矩阵、arm、命令和 episode 完整性，再验证实际实现。参考臂必须有逐航迹共享审计映射
复制；候选复制为 0、共享值复用为正；两臂完整航迹元数据物化数相等。实现 ID、不可变标志和
操作数在 summary、module final 和 governance 三处一致。在线真值使用为 0。JSONL 全部流式读取，
原 4.2 GB evidence 未复制。

语义比较保留 D2 身份/ID switch、D3 计划版本谱系、D4 内容地址/ACK 来源、D5/D7 输出和离线
truth/5 米事件。13/13 pair 的语义、有限状态、真值隔离和实现身份通过。D1 融合 short/long
均值比改善约 `16.29%/31.05%`，候选 `10/10`、`3/3` 更快。

候选没有通过系统级准入。D2 association short/long 增加约 `53.44%/169.89%`，使核心墙钟仅改善
约 `1.65%/1.21%`，低于两组各 5% 的预注册门。源码核对确认，D2 批量真值隔离审计只对精确内建
容器启用等值代表复用；候选只读容器导致共享诊断树逐航迹重扫。因此
`d1_optimization_admitted=false`。

候选最低实时因子为 `0.14695931849644195`，
`system_realtime_gap_closed=false`。当前结论是三维质点评审，不代表 AirSim 或实机。
正式 bundle 位于
`research_modules/d6_evaluation_metrics/outputs/d1_publication_metadata_multiseed_20260724_formal_a36f519/`。
专项正负测试为 `27 passed`，D6 全量为 `761 passed, 1 warning in 41.25s`。后续由 D1/D2
联合修复容器互操作，main 重跑同一矩阵，D6 复用原门。

## 2026-07-24 D1 扫描输入同提交评估评审

D6 已实现 `d6.d1_scan_input_multiseed_evaluation.v1` 只读评估器。它只接受 main 冻结的
short 10 seed、long 3 seed、200/200/2 证据矩阵，并要求参考和候选来自同一 clean commit。
实现处理差异固定为 `reference_v1` 与 `candidate_v2`；矩阵 SHA、case 顺序、命令、bootstrap、
准入门和 evidence boundary 任一变化都会失败关闭。真实 smoke 暴露的 summary 误拒绝已修复：
treatment 派生 episode ID、final stage timings 和 final 内嵌 governance 的实现/性能字段属于
明确白名单；其余 final diagnostics 继续严格比较。

评审顺序为来源、实现身份、业务语义和性能。实现身份从 runtime profile、summary、execution
config、performance diagnostics、module final 和 governance 多处确认。业务比较只放宽明确的
实现身份、性能计数、墙钟、资源和实时因子；D3 计划谱系、D4 内容地址与确认引用、在线载荷、
离线真值状态、标签、距离事件和其余 summary/governance 字段保持严格检查。

统计输出包括扫描输入 wall/P50/P95/max、core wall、GNU time elapsed、RSS 和实时因子。
short/long 分别给出逐 pair 原始变化、正向改善、候选更优数、均值、中位数、P95 和固定
10000 次 bootstrap 区间。优化准入和系统实时性分别判定。报告 writer 只写独立输出目录，
生成 evaluation/aggregate JSON、CSV、中文 Markdown 和 PNG，并记录输入文件 SHA256。

专项正反例和只读检查为 `15 passed`。新增真实 summary 正例通过，非白名单 `d2_track_count`
变化仍使语义和准入失败。

正式评审消费 clean commit
`d14285e4fdeb2f2e2cd32fad2f6d42e30f9e73a7` 的 13 个 pair。manifest SHA256 为
`760cd0e522b27b99de8c30c366ad7e65f16f783d71cf28e3492be299e24b2402`，26 个 arm
全部完成且退出码为 0。short 扫描输入平均改善 `5.360121886647966%`、候选 `9/10` 更快，
bootstrap 原始区间为 `[-8.208165356448217%, -3.0841406102053194%]`；long 平均改善
`5.142481684491682%`、候选 `3/3` 更快，区间为
`[-8.837128529506151%, -1.6693612946922343%]`。short/long 核心墙钟分别改善约
`0.7187%/0.5792%`，RSS 门通过。全部业务语义、有限状态、在线真值隔离和实现身份门通过，
`d1_optimization_admitted=true`。

候选最小实时因子为 `0.14342687633969603`，所以
`system_realtime_gap_closed=false`。正式 D6 评估缺口关闭，系统实时、AirSim 和目标硬件
证据继续开放。报告 bundle 已归档到
`research_modules/d6_evaluation_metrics/outputs/d1_scan_input_multiseed_20260724_formal_d14285e/`。
`EXPERIMENT_REPORT.md` 已补充正式结果；`AIRSIM_INTEGRATION_PLAN.md` 已检查，本项未改变
AirSim 接口或计划，因此不修改。M 对 N 评审不受影响。

## 2026-07-24 D1 多 seed 与长时评估评审

D6 已建立新的显式矩阵入口，预注册 short seeds 1101-1110、2.2 秒和 long seeds 1101-1103、
10 秒。13 个 pair 均须由 main 明确列出 reference/candidate episode、两份 GNU `time -v` 和
cross-build JSON。目录文本不参与 arm、seed、duration 或规模判断。

main 的正式入口是 completed `evidence_manifest.json`。D6 对内嵌矩阵的 experiment ID、固定提交、
13 个 case 与 arm order、200/200/2 规模、运行参数、10000 次 bootstrap、准入门和固定 runtime
profile 摘要执行精确核对。每个 arm 的标签、expected commit、`complete|reused` 状态、整数零
返回码和证据路径必须完整，cross 状态必须为 passed。manifest 与兼容 `--pair` 输入互斥。

consumer 只接受已登记的 v1、v2 和 v3。v1 保留原提交且不能携带 v2 谱系字段。v2 精确绑定修复后的
effective commits、原 v1 base commits、公共 D2 修复 `e4147b8` 及其主题，并要求
`v1_outputs_reused=false`。选择由 experiment ID 完成，未知 experiment 和 CLI commit override
均被拒绝。

v3 的两个 base 都是 candidate commit。两臂共享 D1 半正定修复和 D2 处置修复；reference treatment
只选择标量协方差限制。证据边界要求 v1/v2 输出均不复用，并固定 reference/candidate vectorized
为 false/true。所有字段逐项精确匹配，v1/v2 也不能携带更高版本的谱系字段。

评审将证据分为 pair、矩阵和统计三层。pair 层复用现有 clean、提交、配置、runtime、规模、有限
状态、truth、exit 和 cross-build 校验。矩阵层要求 key 集合与预注册完全一致，配置只允许顶层
seed/duration 不同，runtime profile 全部相同，26 个 arm 的结构歧义保活均为 true。统计层分别
报告 short/long 分布、paired relative change 的确定性 bootstrap，以及共同 seed 的长短单位时间
成本增长。

准入门已按预注册要求实现：short 8/10、均值 5%、bootstrap CI 上界小于 0、P95 改善；long 2/3、
均值 5%；D1 单位成本增长恶化不超过 5%；core wall/RSS 组均值和每 RSS pair 门；全部语义、truth、
finite、exit 门。核心 wall 与 external elapsed 分层，不相加。

fixture 覆盖正分支、全部性能门和 manifest 字段篡改，CSV 为 14 LF、0 CR。多 seed 专项
`67 passed`，D6 全量 `717 passed, 1 warning in 24.26s`。warning 为既有 Matplotlib `Axes3D`
环境提示。

main 矩阵运行在 long seed 1102 reference 暂停。旧 D2 producer 报告 14 个
`known_false_alarm_only`，持久化明确排除只有 11 个，另 3 个为谱系时间窗导致的 unavailable。
D6 在 truth-isolated 和 runtime join 两条路径都要求 audit 与最终持久化明确排除数精确相等，因此
旧 `14/11` 失败关闭；D2 修复后的 `11/11` 才可消费。main 已完成正式 v3 manifest 和首次报告。
评审发现实时因子方向展示错误：short/long 原始增长 `+3.222%/+3.601%` 被误写为负改善和 0/N
更优。当前 consumer 明确输出 metric direction、候选更优数和正向改善，修正为 `10/10`、`3/3`；
原始变化、bootstrap、兼容 lower count、evidence、门控和准入判定均保持不变。现有正式报告需用
同一 manifest 重生。三维质点矩阵不包含 AirSim 或目标硬件条件，系统实时性继续保持未关闭。

固定报告 bundle 已增加二维 PNG。上半图按显式 short 10 seed、long 3 seed 绘制 D1 融合配对改善；
下半图比较两组 D1 融合、融合 P95、核心墙钟、外部 elapsed 和实时因子方向化均值改善。实时因子
越高越好，其余绘制指标越低越好，图中正值统一代表候选更优。RSS 继续在图外的机器统计、Markdown
和准入门中报告。writer 对 pair 集合、指标 availability、有限值和方向执行失败关闭校验，CLI
返回固定 `outputs.png`。专项为 `69 passed`，D6 全量为
`719 passed, 1 warning in 24.65s`。

`AIRSIM_INTEGRATION_PLAN.md` 已检查。本轮不改变 AirSim 日志、topic、检测、相机、reset、actor 或
控制接口，因此无需修改。`D6_M_TO_N_EVALUATION_FRAMEWORK_REVIEW.md` 也已检查；本项不改变 M 对 N
联盟、同步到达或五米物理指标，无需修改。

## 2026-07-24 D1 协方差成对限制向量化评审

D6 以独立只读消费者复核三轮 clean reference/candidate。每轮输入显式绑定两个 episode、
cross-build JSON 和两份资源记录；评估器不扫描目录推断实验臂或规模，也不导入 D1 生产代码。
现有 scalable 3D reader 负责 manifest、配置、真值隔离和阶段时序，新入口补充外部 elapsed、RSS
和退出状态校验。

评审先要求三轮业务语义通过，再评价性能。每 arm 必须 clean、提交正确、配置和运行配置哈希有效，
两臂及三轮共享 seed 1100、场景版本、200 个目标、200 个资源、2 个侦察节点和 2.2 秒世界时间。
summary 必须为有限状态，2035 条观测、在线真值使用 0；cross-build 必须 `passed=true` 且规范化
在线载荷一致；进程退出状态均为 0。

三轮 D1 fusion wall 均值为 `4.014713519 -> 3.595533106 s`，下降 `10.4411%`，3/3 更快。episode
内调用 P95 的三轮均值为 `184.228658 -> 173.330868 ms`，下降 `5.9154%`。核心 wall 下降
`3.1417%`，外部 elapsed 下降 `3.6310%`，RSS 下降 `0.1429%`。D1 scan input 增加 `0.3607%`，
属于独立阶段，不进入本项门控。D2、D3、D7 单 seed 调度波动没有归因到 D1。

评审结论为 `d1_optimization_admitted=true`。该结论只说明冻结三维质点输入下的性能优化满足门限。
候选实时因子均值为 `0.215065`，且只有单 seed 的三次 2.2 秒重复，因此
`system_realtime_gap_closed=false`。AirSim、多 seed、长时增长率、均方根误差、归一化估计误差
平方、归一化创新平方和严格身份指标保持 P1。

专项正反例和 CSV 纯 LF 检查 `9 passed`，D6 全量
`646 passed, 1 warning in 21.65s`。机器 JSON、逐轮 CSV 和中文报告位于
`research_modules/d6_evaluation_metrics/outputs/d1_covariance_limit_clean_pair_20260724/`。
重生 CSV 为 7 个 LF、0 个 CR；warning 为既有 Matplotlib `Axes3D` 环境提示。

`AIRSIM_INTEGRATION_PLAN.md` 已检查。本项不改变 AirSim producer、topic、相机、检测、reset、actor
或控制链，因此无需修改。`D6_M_TO_N_EVALUATION_FRAMEWORK_REVIEW.md` 也已检查；本项不改变 M 对 N
需求、联盟、同步到达或五米物理分母，因此无需修改。

## 2026-07-24 D1 原子影子旁路兼容评审

D6 继续使用 `scalable3d-d1-centroid-overlay-shadow-v1`，并在 payload 内按显式执行模式分派。
旧五字段 `canonical_preparation` 仍按 prepared-handle v1 读取；没有准备字段的旧记录保留为
uninstrumented。原子模式要求固定七字段准备块，D6 不读取 evaluation 或 shadow tracks，也不根据
缺失字段推断零工作量。

评审重点是原子记录内部一致性。准备摘要、操作后完整性和原子工作量的遍历计数必须相互对应。
accepted 必须物化 detached shadow，普通 rejected 的 shadow 工作必须为 0。atomic failure 必须
取消 accepted 并隐藏 shadow；失败前已经发生的临时复制或摘要工作可以保留为审计计数。任何字段
缺失、模式混用、摘要/物化冲突和计数矛盾均使记录失败关闭。

2026-07-24 专项 `25 passed`，D6 全量
`637 passed, 1 warning in 21.89s`。seed 1100 的 9 条既有 prepared-handle 记录均可读且完整性
检查通过。

clean commit `7cc2d0c` 的 seed 1100 atomic pair 已提供正常 rejected 实际路径。9 条 atomic 记录
全部通过 integrity，canonical description/post-integrity pass 为 `9/9`，两者均覆盖 1813 条航迹
摘要；atomic failure/materialized 和三项 shadow 工作量均为 0。46 个 decision 全部为
`oosm_scan` rejected。编号、禁止表面、D2/D3 消费和在线真值均无违规，业务非干预通过，evidence
failures 为空。

control/shadow 墙钟为 `10.735151270986535/19.449935468961485 s`，相对开销
`0.8117989190825889`；P50/P95/max 为
`1024.8383930302225/1536.4285601885058/1549.4359389995225 ms`。性能门失败，accepted treatment
为 0，outcome evidence 不可用，overall admission 为 false。当前无新增 P0；真实 rejected-only
消费已关闭。后续仍需 clean accepted、atomic fail-closed、多 seed 性能和结果效果证据。D6 保持
只读且无控制权限。

`AIRSIM_INTEGRATION_PLAN.md` 已检查。本轮未改变 AirSim 日志、检测、相机、reset、actor 或控制
接口，因此不修改。`D6_M_TO_N_EVALUATION_FRAMEWORK_REVIEW.md` 也已检查；原子 D1 影子旁路不改变
M 对 N 物理分母、联盟状态或五米成功口径，保持不改。

## 2026-07-23 D1 质心发布影子旁路评审

D6 已建立 A2 旁路的只读评估边界。输入仅来自持久化 main 总线、最终模块诊断和阶段时序，输出为
availability-aware 离线指标。D6 不导入生产者，不向 D1-D3 返回结果，也不把该旁路纳入通用控制
episode 指标。

评审采用三层判据。业务非干预核对 canonical/evidence 前后摘要、摘要语义、全局航迹编号、正式航迹
替换、禁止表面、D2/D3 消费和在线真值使用。性能判据比较同场景 control/shadow 总墙钟，门限为
相对开销不高于 `+5%`。处理和效果判据要求存在 accepted treatment，并由独立 outcome effect 证明
收益。shadow/canonical SHA 不同仅表示影子副本不同，不属于正式业务输出变化。

seed 1100、200 对 200、2.2 s 的 dirty development prepared pair 已完成只读复核。shadow 有
9 条 sidecar、46 个 decision，accepted/rejected/error 为 `0/46/0`，拒绝原因均为 `oosm_scan`。
禁止修改、
全局航迹编号变化、D2/D3 消费和在线真值使用均为 0，业务非干预通过。P50/P95/max 为
`1009.256/1532.999/1619.053 ms`，watermark 为 `8/8/1024`，payload 峰值为
`11,275,939 B`。

control/shadow 总墙钟为 `10.712171729/19.376483415 s`，相对开销比 `0.808828677`，性能门失败。
accepted treatment 为 0，outcome effect 不可用。评审结论固定为
`business_nonintervention=true`、`performance_gate=false`、`overall_admitted=false`。当前没有
新增 P0；A2 仍是 P1 开放项。该输入来自 dirty 工作树且只有一个 seed，只形成描述性开发证据。

2026-07-23 的适配器专项为 `11 passed`，scalable 与后验治理联合回归为 `77 passed`，D6 全量
为 `623 passed, 1 warning in 21.67s`。warning 是既有 Matplotlib `Axes3D` 环境提示。

后续由 main/D1 在提交生产端后提供 clean/frozen 同输入多 seed pair，并至少包含一组有效 accepted
treatment。D6 继续只读复核非干预、性能和效果三层，不用 shadow SHA 差异代替业务收益。性能超过
`+5%`、没有 accepted treatment 或缺效果证据时，准入继续失败关闭。

`AIRSIM_INTEGRATION_PLAN.md` 已检查。本轮不改变 AirSim 日志 producer、相机、检测、reset 或控制
接口，因此无需修改。`D6_M_TO_N_EVALUATION_FRAMEWORK_REVIEW.md` 也已检查；A2 旁路不改变 M 对 N
联盟分母和物理结果口径，无需修改。

## 2026-07-23 离线观测处置评审

D6 当前以 schema 为唯一处置语义来源。v2 将观测分为 target、known false alarm 和 unknown。
known false alarm 从身份映射分母中排除，unknown 关闭严格身份指标。v1 继续按 target-only 合同
读取，但不把缺少非目标标签能力解释为两类计数均为零。

直接 sidecar 路径逐行校验 main v1/v2；D2 路径验证 normalized v1/v2、来源文件 SHA-256、
identity evaluation、identity manifest 和 audit count。D6 不从 observation ID、距离、
actor/object 名称或在线状态推断 disposition，也不利用处置计数或部分身份下界回填 strict IDSW。

评审结论为 consumer、报告和失败关闭合同已完成。2026-07-23 新增处置及相关专项 `130 passed`，
D6 全量 `586 passed, 1 warning in 21.99s`，scalable learning export 联调
`5 passed, 1 warning in 3.13s`。当前证据是确定性接口验证，不是实际虚警率或身份性能结论。

后续由 main/D2 生成 clean v2 多 seed sidecar，D6 再统计三态分布和 strict availability。AirSim
虚警需显式离线标注，在线总线继续禁止 truth/disposition。上游混轨未修复前，strict IDSW 保持
unavailable。

`AIRSIM_INTEGRATION_PLAN.md` 与 `D6_M_TO_N_EVALUATION_FRAMEWORK_REVIEW.md` 已检查。本轮没有改变
AirSim 运行时接口或 M-to-N 指标分母，因此不修改这两份文档。

## 2026-07-22 scalable 3D 阶段分位评审

本次改动扩展 D6 的离线性能证据，不改变 D1-D7 控制链。main 的
`scalable3d-stage-timings-v2` 同时发布累计耗时和单次调用分位。D6 将两类量分开：累计墙钟用于阶段
占比，P50/P95/max 用于描述 episode 内调用延时分布。两者不能互相反推。

v2 以显式 availability 为准。`distribution_available=true` 时三个分位必须齐全、有序且与最大值
上界一致；false 时三个字段必须全空并给出原因。legacy 没有 availability 列时只根据完整三元组
推断；没有分位证据时保留空值。该规则兼容历史文件，同时阻止半缺字段和假零进入报告。

跨 seed 统计的基本样本是每个 episode 内的 P50、P95 或 max。输出中的均值、范围和 bootstrap
区间描述这些 episode 分位在不同 seed 上的分布。它们不是所有调用样本的 pooled quantile。原始
逐调用样本未持久化时，D6 明确输出 pooled quantile unavailable。

评审结论是 D6 consumer、逐 episode 行、跨 seed 聚合和中文尾延时表已闭合。2026-07-23 当前权威
全量回归为 `567 passed, 1 warning in 22.96s`；相较 555 项新增的 12 项来自部分身份合同的
3 项独立测试和 9 项篡改参数化用例。阶段尾延时真实性能证据尚未闭合：main 需用当前 producer
重跑 clean 200 对 200 多 seed，并显式冻结稳定窗口定义。现有 5v5 冒烟和旧格式 20-seed 输入
不能升级为该证据。

`AIRSIM_INTEGRATION_PLAN.md` 已检查。本次不改变 AirSim 日志 schema、reset 或控制接口，未修改该
文档。

## 2026-07-22 clean 20-seed 后验代次证据评审

D6 已独立复核 clean commit
`0d2da25c14e50f8f9a10ad47a7bd74e5c5e577fb` 的 nominal 200 对 200、10.0 s、
seed `1000-1019` 批次。20 个主 episode 与 20 行 D6 v6 逐 seed 记录一一对应；来源均 clean、
状态有限、在线真值使用为 0、分配 hold 为 0，源进程退出码为 0。

20/20 episode 的 D1 完整后验序列连续。D2 来源代次严格递增、无重复，并且只引用此前已发布的
D1 完整后验。最终 pending 全部排空，D1 generation 等于 D2 consumed generation，D2 consumption
等于 D2 publication，consumption 加 pre-tick merge 等于 D1 generation。generation contract
均为 verified，integrity 均为 true。

D1 generation 均值为 `471.65`，范围 `410-499`；D2 consumption 均值为 `47.95`，范围
`47-48`；pre-tick merge 均值为 `423.7`。D3 coverage 均值为 `0.989606`，95% bootstrap
区间为 `[0.987144, 0.991813]`。D5 binding 均值为 `25.95`，范围 `9-41`，只代表本批
10.0 s 名义窗口。20 个 episode 均无 5 m 接近。

评审结论是 clean 未见 20-seed runtime v2 代次合同输入缺口已经关闭。基础
`formal_acceptance_eligible_episode_count=20` 不等于正式算法验收：20 个 episode 全部仍是
`descriptive_clean_source_calibration`，experiment-matrix episode 为 0。正式变体矩阵、D2
ID switch、物理接近身份、物理拦截和学习效果保持开放。

聚合与报告 SHA-256 已独立复算。main 给出的 D6 墙钟 `3:20.42` 和峰值 RSS
`1,448,612 KiB` 未持久化在 D6 五个输出制品中，只登记为外部运行诊断。`AIRSIM_INTEGRATION_PLAN.md`
和 `D6_M_TO_N_EVALUATION_FRAMEWORK_REVIEW.md` 已检查；本批不改变对应接口、层级或分母，无需修改。

## 2026-07-22 后验代次合同评审

runtime v2 使 D6 可以判断 D1 后验是否被 D2 按发布代次消费。评审同时使用在线总线和 episode 最终
summary。只看 summary 无法发现中间重复或倒序；只看总线无法证明 finalize 后 pending 已排空。

D1 完整后验代次从 1 连续递增。D2 来源代次严格递增且已在此前 D1 完整后验集合中。pending 为空时
最终消费代次必须等于 D1，消费次数必须等于 D2 发布数。D1 在一个 D2 节拍前产生多个后验属于允许
的合并，但消费次数加 pre-tick merge 必须等于 D1。

历史 v1 不能完成上述判断，报告保持 unavailable。v2 的重复、未知引用、非单调、累计矛盾和 pending
未排空均失败关闭。D6 只读消费持久化制品，不读取 truth，不更改 D1/D2 调度。

独立 D1/D5 性能 JSON 只说明模块在指定回放或微基准中的描述性结果。登记包含 schema 和文件
SHA-256，明确排除全栈实时和控制效果声明。专项 `58 passed`，D6 全量
`542 passed, 1 warning`。

main 已用 clean commit `0d2da25` 完成 nominal 200 对 200、10.0 s、seed
`42000/42001/42002`。D1 final/full publication 为 `453/453`、`516/516`、`505/505`；D2
final/consumption/publication 为 `453/48/48`、`516/48/48`、`505/48/48`；pre-tick merge 为
`405/468/457`，pending 全部排空。三次 integrity 与基础 formal provenance gate 均通过，失败原因空，
在线真值使用为 0。

该批归类为三个 `descriptive_clean_source_calibration`，是首批 runtime v2 正例。后续同一 clean
commit 的 20 个未见 seed 已由本页上一节复核，输入数量子项关闭。两批均没有实验矩阵 metadata，
正式矩阵 episode 数仍为 0；正式矩阵和算法差异验收仍为 P1。

`AIRSIM_INTEGRATION_PLAN.md` 和 `D6_M_TO_N_EVALUATION_FRAMEWORK_REVIEW.md` 已检查。后验代次合同不
改变 AirSim 接口，也不改变 M 对 N 联盟分母和物理结果口径，因此两份文档无需修改。

## 2026-07-22 200 对 200 长时三 seed 集成评审

main 提供的 reference `8f86192` 与 candidate `f80b5bd` 使用相同 nominal 200 对 200 配置、10.0 s
世界时长和 seed `42000/42001/42002`，两组来源均为 clean。candidate 三个 episode 均为有限状态，
在线真值使用为 0，D1/D2/D3/D5/D7 最终数量与 reference 相同。逐条审计先核验 ACK 原始载荷 SHA-256，
再按计划 occurrence/version 规范 D3 随机 `plan_id`；owner、version、coalition、`global_track_id`、
command 和其他业务字段不被忽略。三 seed 的规范业务语义全部相同。

核心墙钟均值为 `155.895422 -> 150.874890 s`，进程总墙钟为
`222.780 -> 195.363 s`，峰值 RSS 为 `2.888697 -> 2.359147 GiB`，进程残差约
`66.885 -> 44.488 s`。candidate `total_before_timing_artifact` 分别为
`39.274048705/41.663056382/40.982858311 s`，均值 `40.639988 s`。reference 缺同构
`post_run_timings.csv`，残差改善只能作为核心外整体成本变化，不归因于单个 D6 函数。

D6 的 JSONL streaming 保持主题过滤前的全记录真值检查，降低整文件常驻内存；D2 identity index 在
严格校验后复用不可变身份映射；main 的规范 D1/D2 视图在写在线总线时同步生成，并由离线 identity
消费者复用。三项优化与其他模块优化共同作用，当前进程级 A/B 不支持分解单项贡献。

D6 aggregate 为 episode 3、基础 formal provenance eligibility 3、dirty 0、运行失败原因分布为空。
三个 episode 的证据状态仍为 `descriptive_clean_source_calibration`，没有完整实验矩阵 metadata。
实时因子仅约 `0.064-0.068`，七个在线/模块栈阶段仍通过超线性判据。结论是集成等价和资源用量得到
三 seed clean 证据；正式 20 未见 seed、实时 P1、五米物理闭环和学习效果仍开放。

文档同步后 D6 全量回归为 `530 passed, 1 warning`，耗时 33.75 s。既有 Matplotlib `Axes3D` warning
不影响本批文件合同。AirSim 计划和 M 对 N 专项已检查；本次无对应接口或指标变化，保持不改。

## 2026-07-22 runtime outcome join 性能与安全复核

本轮选择默认严格路径优化，没有接受“main 已检查”的无结构声明。在线文件仍从带外 SHA 开始逐条
解码；禁用真值 key 在 JSON object hook 中与 duplicate key 同时检查，随后才执行主题过滤。因此优化
删除的是第二次 Python 对象树递归，不是安全审计。Unicode 转义 key 经过标准 decoder 还原后仍命中。

留存面缩小到联接真实依赖的五类主题。D1/D2 只保留规范整行摘要并与 filtered source 双侧重算；
D3/D7/ACK 继续保留完整载荷以核验 source sequence、payload SHA、binding、authority 和执行状态。
D2 evaluation 仍先完成 source hash、lineage、帧顺序和帧内唯一性检查，之后的只读航迹索引仅消除
594 个窗口对同一 mapping 列表的重复扫描。

固定 3380 条、63,014,782 B、200v200/2.2 s/seed 42000 development 输入上，`8f86192` 与 candidate
返回 mapping 完全一致。总评估三次均值从 5.302515 s 降到 2.901966 s；在线加载从 2.777838 s 降到
1.506296 s；窗口从 0.451765 s 降到 0.028150 s。业务 JSON、漂亮打印 JSON 和 Markdown 摘要均不变。
专项 25 项和 D6 全量 530 项通过，真值注入和 D2 filtered-source 偏离负例均失败关闭。

复核结论是 D6-owned 离线重复解析/扫描 P1 已关闭，证据边界未升级。该批不是 clean formal 容量测试，
也不评价 AirSim、控制实时性或物理效果。下一优先级是正式长时多 seed 容量门限；若 main 后续确需
跨进程快速路径，必须先给出绑定源 SHA 与真值策略版本的可审计证明合同，独立入口仍默认重验。

## 2026-07-22 Scalable 3D 批次发现评审

批次根目录不是 episode 身份依据。主 episode 内的离线一致性、身份评估和真值隔离制品各自带有
manifest，它们描述的是评估侧车，不具备完整在线 episode 合同。仅凭 manifest 递归会扩大分母，
还会把缺在线记录的 sidecar 送入状态收口。

D6 现以三项结构制品识别主 episode：manifest 固定来源，scenario config 固定场景，summary 固定
episode 结果。三项必须位于同一目录。online observations、阶段时序、近距事件、离线真值和各模块
sidecar 不参与身份判断；它们缺失时按各自 availability 处理。显式 episode 路径不受递归筛选影响，
便于审计历史不完整记录。

计数收口使用“availability、类型、范围”三步检查。available 的值必须是非负整数；unavailable 的
值保持 null。该规则防止 `None` 被转成 0，也防止缺证据目录使整批评估崩溃。clean provenance 只
说明来源可复核。没有 experiment-matrix metadata 的批次归为描述性 clean-source calibration。

真实复核批次包含 20/50/100/200 四档，每档 5 seed。修复前发现 100 个 manifest 目录；修复后发现
20 个主 episode，sidecar 为 0。20/20 clean、20/20 无实验矩阵声明，最终证据类别均为描述性
clean-source calibration。该结果验证发现和报告合同，不评价 D1-D7 性能。

## 2026-07-22 长 Episode 观测治理评审

D6 已完成面向 main 长 episode 标定的公共只读合同。批输入、manifest、在线 D1/D2 审计和
evaluator-only 侧车分别版本化并由 SHA-256 绑定。episode 的 scale/target/resource/seed/
duration、Git、配置和 schema provenance 必须跨制品一致；formal dirty、重复 seed、在线
truth 或缺失来源链均 fail closed。

报告按实际规模聚合 D1 扫描 OOSM 和 D2 claim ledger。在线指标给出 mean/P95/max 和可用
episode 数。近邻 recall、false suppression、erroneous coalescence 与 confirmation latency
只消费离线侧车；比例保留 evaluator 分母和 bootstrap 95% 区间。unavailable 继续使用空值，
不写成零。

2026-07-22 合成专项 `14 passed`、D6 全量 `521 passed`。D6-owned parser/report GAP 已关闭。

同日 development 快速基准已提供 20/50/100/200 各 5 seed，共 20 个 33.75 s episode。在线
真值使用数为 0；D1 每档重排 12、拒绝/过旧/溢出 0、峰值缓冲 3；D2 峰值 claim/容量为
2390/4800、6020/12000、12070/24000、24170/48000，安全淘汰为 285/735/1485/2985，溢出
为 0。evaluator-only 近邻召回 1.0，错误抑制和错误合并 0，确认时延 0.25 s；全部指标有
availability 和 95% bootstrap 区间。200 规模 D1+D2 tracemalloc 口径峰值约 58.99 MB。

实际 D1-D7 质点栈的 200 对 200 单 seed 冒烟单独记录：2.2 s 世界时间、60.21 s 墙钟、实时
因子 0.0365、online truth use 为 0。该结果只说明全栈能够运行并产出治理审计。快速基准不代表
全栈，单次冒烟也不代表快速治理的 33.75 s 统计。

快速治理矩阵随后在 clean 提交 `e4d66db02a0b8f1b867a0e81b4a73de84588426b` 上以
`formal_only` 完整复跑。权威制品覆盖 20 episode/20 seed，四档各 5 seed；online truth use
为 0。D6 聚合记录 `runtime_modules_imported=false`，D1/D2 控制修改均为 false。正式四档
D1/D2 计数与上方 development 治理结果一致；近邻召回 1.0 的 95% 区间为 [1,1]，错误抑制和
错误合并 0 的区间为 [0,0]，确认时延为 0.25 s，全部为 5/5 available。

aggregate SHA-256 为 `6fb64252292aaedd3c68d1bfea64b76496136ce6edb32add61a281d511c4ed22`，
中文报告 SHA-256 为 `6198854b867d39fb2f1300cddeb1f75972ba8b7952361622213050115feb0827`。
快速治理 clean/formal 缺口已经关闭。200 对 200 全栈冒烟仍是 dirty/development；精度、身份、
AirSim、实时性和五米物理闭环不从治理 formal 结果继承，仍需独立正式证据。D6 不参与参数调整
或控制。

## 2026-07-22 D2 修复后 active_risk 开发期复核

D6 已只读检查 `/tmp/msm_active_risk_d2_fix_20260722/` 的 manifest、共同检查点报告、D6 sidecar、中文
报告和 seed 1005 control 离线身份文件。根目录 447 个摘要和 D6 目录 3 个摘要全部通过。20 个 seed
的计划消费、导引血缘、物理窗、D4 adoption、配对物理差值、配对非退化和降级配对比较均为 20/20
可用；D4 区域采用合计 `188/188`，control/treatment 各有 `1960` 条实际命令。

seed 1005 已恢复为 5 条唯一中心航迹到 5 个目标的离线一对一映射，online truth use 为 0，整批审计
也没有 `global_track_id` 改写。该结果表明 D2 重复航迹导致的离线身份映射断点在本次开发期输入中已
消失。D6 消费算法和 schema 未改变。

本批两臂 5 m 成功数均为 0，配对差值为 0；20/20 非退化是描述性判定。counterfactual/causal 均为
0/20 available，production runtime ACK 未评估，降级有效性声明禁止。该批由脏工作树生成，只作为
development rerun；下方原有 clean formal 19/20 历史证据保持原文，不由本批替换。

文档同步后 D6 全量为 `507 passed, 1 warning`，owned-path `git diff --check` 通过；warning 为既有
Matplotlib `Axes3D` 环境问题。

## 2026-07-22 隔离双臂多周期物理结果复核方案

D6 已增加独立的 paired-isolated physical consumer。输入按 seed 固定一份初始状态和三份外生日程，
再分别列出 control 与 treatment 的 episode、计划、隔离消费确认、导引命令、世界应用、离线身份和
真值轨迹。所有文件都由调用方提供带外 SHA-256；D6 不搜索相邻目录，也不导入 producer 私有状态。
两臂可以读取相同的不可变日程，但必须运行在不同 episode、world 和文件树中。

每个 arm 现在可显式携带 D4 区域采用文件。input spec 与 arm manifest 必须同时声明并绑定该文件；
D6 逐区域重算 source/applied plan、场景 lineage、candidate gate、isolated plan ACK 和 adoption verdict
之间的摘要、arm、seed、region、owner/epoch/lease 关系。文件未声明、名义空文件、完整采用和部分区域
不可用分别保留，不从相邻路径推断证据，也不把隔离确认称为生产运行 ACK。

生产者可以保留一条通过独立校验的隔离 ACK，同时令 verdict 的
`isolated_plan_consumption_ack_available=false` 和 `ack_id=null`。D6 此时继续审计 ACK 的计划、血缘、
执行绑定和非生产属性，但不将其计为 adoption。只有 verdict 声明 ACK available 时才强制编号一致。
ACK 本体伪造、顶层 available 与 verdict unavailable 矛盾、以及生产确认冒充仍失败关闭。

计划消费层重新核对 D3 的计划编号、版本、规范载荷摘要和 binding inventory。该确认只说明隔离仿真
读取了计划，不能称为 production runtime ACK。导引层继续核对 D7 command 到消费确认、资源、中心
航迹和 world application 的血缘；每个绑定需要至少一个实际世界应用，整个 arm 至少覆盖两个控制周期。
online 制品不允许携带 truth-like 字段，`global_track_id` 不由 D6 创建或改写。离线阶段才使用一对一
身份映射和真值轨迹计算三维距离。

物理窗按资源的计划消费区间划分，首次已应用命令为起点，下一次已接受计划或 episode 终点为终点。
距离不大于 5 m 计为成功；同时统计最小距离、首次进入 5 m 时间、错误目标进入 5 m、硬约束和唯一目标
成功数。treatment-control 差值是描述性结果。非退化 v1 要求成功数不下降、平均最近距离不增大、硬
约束不增加、错误绑定不增加；无成功时到达时间保持 null，不强行进入总体判断。

证据层在原有 plan consumption、guidance lineage、physical window、paired physical effect 和 paired
non-degradation 之外，增加 d4 degraded adoption 与 degraded paired physical comparison。后者要求
control/treatment 全部区域采用、区域清单和 intervention 一致，并同时具备计划、导引和物理窗。它仍
只支持 paired isolated simulation comparison；counterfactual 和 causal 保持 null。2026-07-22 的
24 个合成合同测试、D6 全量 `507 passed` 和 main 20 seed producer 集成专项 `1 passed` 证明接口、
篡改检测、空值逻辑和真实嵌套合同可运行。`active_risk` seed `1000-1019` 的只读复跑进一步确认 D4
adoption/降级比较为 0/20 available，物理窗为 19/20。尚无 clean、冻结的正式降级效果报告，也没有
改变 PPO、assist、authority 或规则回退状态。

## 2026-07-22 D3/D4 保留 seed v1/v2 独立复核

D6 已将原 v1-only consumer 改为按权威顶层 schema 严格分派。v1 的 source commit、带外摘要、零采用
fail-close 和五项 availability map 保持兼容；v2 独立绑定 commit
`78912963b67fe86ee9a8d29186b18a9dd60c460c`、checksum `821f1503...72bc` 和 manifest
`d6ef23b2...883c`。CLI profile 同时绑定预期源 schema；同 schema 摘要可带外覆盖，跨 schema 失败关闭。
历史 Python API 的位置参数顺序和默认 v1 不变。两版共同执行六文件 inventory/checksum、20 条 lineage、seed/dirty/truth/配对标志、
D3/D4 各 40 arm、pair input/bundle identity 和输入前后快照校验。

v2 D3 的 safety shell v2/config SHA 在 40/40 arm 上一致。treatment applied/fallback=`20/0`；20 对
target-resource 选择相同。按冻结规则 cost 基准，rule/treatment mean 均为 `17.0560260319065`，
high-threat unmet、duplicate、hard violation 和 churn 均为 0，inference P95(linear) 为
`0.310801 ms`。该层只支持 `offline_assignment_comparison=available`。

v2 D4 的 20 条 treatment evidence 均为 arm evidence v2。candidate considered 20/20，confidence
0/20 pass，OOD/latency/finite/failure 各 20/20 pass，aggregate 0/20；low-confidence 20/20，safe
adopted 0/20，fallback 20/20。分门逻辑、置信度/时延分布、拒绝原因和 manifest gate summary 均由
D6 重算。执行时延最近秩 P95=`2.241315 ms`，门控汇总线性插值 P95=`2.264415 ms`。nominal 5v5
不能解释为降级策略评估。

最终状态是 `pass_offline_assignment_comparison_only`。runtime ACK、physical outcome、paired physical
outcome/effect/non-degradation、counterfactual 和 causal 仍为 null/unavailable；D4 零采用不是效果 0，
D3 同帧无退化也不证明候选策略有效或开放线上权限。正式 v2 输出位于
`research_modules/d6_evaluation_metrics/outputs/reserved_seed_interventions_nominal_5v5_1000_1019_formal_7891296_d6_profile_bound_v2_audit_20260722/`。
sidecar/报告/provenance/checksum 文件 SHA-256 为 `f3852251...71c3b`、`bd80c1dd...f9949`、
`0d50a95d...f7dc6`、`db4af357...7b87c`，sidecar 内容 SHA 为 `c02a345c...5d2d`。固定时间戳
CLI 复生四文件逐字节一致，内部 checksum 通过。
测试内 v2 fixture 保证无 ignored output 时仍执行关键成功和篡改诊断；正式 bundle 复算继续保留。
专项 `18 passed`、无权威输出路径 `16 passed`、D6 全量 `483 passed`。下一步只在取得严格绑定的 runtime ACK
和采用后物理窗口后新增 physical outcome/effect sidecar。

## 2026-07-21 D3/D4 保留 seed 隔离执行独立复核（历史 v1）

D6 已对 main 生成的 `nominal` 5 资源/5 目标、seed `1000-1019` 隔离执行制品建立只读审计链。审计先
用带外摘要固定 `SHA256SUMS`、顶层 manifest、源提交和四个 bundle digest，再从 20 条 lineage、D3
arm/receipt 和 D4 specification/evidence 重算所有计数。审计不导入 D3/D4 producer，不修改输入；
六个输入文件的审计前后集合摘要一致。

完整性复核通过：五个 checksum 成员和 manifest 内全部 artifact SHA 一致；20 条 lineage 均来自
`6d5bfead31d53258b020a5f157b2ad5e7f25ee35`，dirty、nonfinite、online truth use 为 0，且每个 seed
的 control/treatment 共享 source episode、sensor random stream、communication schedule 和 fault
schedule。D3/D4 各 40 arm，均为 20 control + 20 treatment；每对 input、lineage、specification 和
bundle digest identity 均通过。

执行结果体现的是失败关闭。D3 候选 learning cost `0/20` 实际应用，全部因 `out_of_distribution`
回退；control 决策为 unchanged 15、held_by_hysteresis 3、replan_ack_no_change 2。D4 candidate
`0/20` safe-adopted，全部因 `candidate_threshold_or_finite_gate_rejected` 回退。D3 receipt latency
n=20、mean/P95=0/0 ms；D4 candidate latency n=20、mean 8.291408 ms、median 1.196097 ms、
nearest-rank P95 35.255481 ms、max 42.301505 ms。时延可用不等于 outcome 可用。

评审结论为 `pass_fail_closed_only`。sidecar 仅将 execution receipts 标为 available；runtime ACK、
physical outcome、counterfactual 和 causal 均为 unavailable。由于两种 treatment adoption 都是 0，
paired outcome、paired effect 和 non-degradation 的值必须为 null，不能把回退后的相等输出解释为
effect=0 或非退化。该证据证明失败关闭和证据完整性，不证明候选策略有效、非退化、外部泛化或因果
收益，也不改变 PPO、assist、authority 和默认规则路径。

下列 v1 目录是 schema binding 序列化前发布的历史制品。当前 consumer 保持 v1 API/算法语义，但新生成
文件属于 profile-bound provenance，不以旧哈希作为当前复生目标。历史输出位于
`research_modules/d6_evaluation_metrics/outputs/reserved_seed_interventions_nominal_5v5_1000_1019_d6_audit_20260721/`。
专项 `7 passed`、D6 全量 `472 passed`；输出 `SHA256SUMS` 已二次复算。下一步前置条件是 producer/main
提供严格绑定的非零安全采用 ACK 和采用后的物理状态窗；在此之前不追加 paired performance 声明。

## 2026-07-22 D5 配对影子权威 v2 独立复核

D6 已实现独立、只读、显式路径和带外 SHA-256 的权威 v2 消费器。输入固定绑定 v2 report/lineage、
保留种子 corpus/evaluation、冻结模型包、D5 实现源码和 superseded v1 证据。审计验证 2702 项语料
inventory、7 个实现文件和全部关键输入；审计前后 2718 项输入集合摘要一致。旧 v1 只保留为被替代
证据，未与 v2 源码或结果混用。

20 个 seed、45 个场景规模单元、900 条 lineage 和 74024 条已标注候选边完整。每帧只加载一个图；
规则臂与模型臂的 graph、candidate 和 label identity 均为 1.0，候选增删为 0。D6 独立重算逐 seed、
逐单元和总体边级、簇级计数及延时，45/45 单元无质量退化。同相机候选边、未标注候选边、在线真值
特征和 `global_track_id` 改写均为 0。

合成可分性复核改变了证据等级。中心共享航迹计数恒为 0，中心投影马氏距离的最佳单特征 F1 为
0.370482，未发现中心身份线索直接决定标签。三个运动或尺度差特征近确定性可分，最强特征覆盖 35/45
单元。当前结果可关闭配对执行与核算缺口，不能证明独立几何和真实视觉条件下的外部泛化。

最终状态限定为 paired-shadow=`complete`、research-shadow=
`qualified_with_synthetic_separability_caveat`。G1、近端策略优化、辅助模式和控制权限保持 false，
规则回退保持 true。后续优先生成去合成捷径、独立相机几何、外参和时间扰动语料，并运行
no-center-feature 同 seed 配对复验。

2026-07-22 回归结果为专项 `8 passed`、D6 全量 `465 passed`。输出 `SHA256SUMS`、JSON/manifest 内容
摘要和输入前后集合摘要均已复算通过。

## 2026-07-21 D5 clean 跨视角图证据复核（v2 前置阶段）

D6 已提供显式、只读、带外 SHA-256 约束的 D5 clean 数据消费者。复核覆盖 supplemental summary、
composite admission/view、formal/supplemental canonical view、supplemental manifest/dataset 和 formal
source manifest。实现不搜索 D5 ignored output，不修改来源，也不改变既有 runtime outcome
diagnostic。

当前 4,972 episode、245,040 条候选边的 composite 数据通过数据支持和训练来源门；未标注边为 0，
seed 为 60/20/20，保留 seed 无重叠，45 个场景规模单元和 clean source 合同成立。本节记录 v2 生成
前状态；当前模型内部测试、保留 seed 和 paired shadow 状态以上一节为准。G1、assist、authority 和
PPO 仍关闭，规则回退继续启用。

D6 输入合同现为 `d6.d5-clean-graph-inputs.v2`，可成对接收显式 held-out evaluation report/manifest；
v1 继续只读兼容原无 held-out 结构。消费者不扫描 D5 输出目录，独立复算调用方文件 SHA 和 D5 内容
SHA，并严格核对 held-out report/corpus schema、20 个 seed `1000-1019`、45 cell、900 episode、内部
model weights/bundle manifest、冻结 validation 温度/阈值、零权重更新、零 online truth/同相机边/
未标注边及零 `global_track_id` 创建换绑。未知字段、哈希篡改和权限伪造均拒绝。

结构合法且门限通过只完成 `held_out_seed`；门限失败标为 `failed` 并保留 producer `fail_closed`；缺
制品为 `unavailable`。paired shadow 未提供时 G1、assist、authority 保持 false，规则回退为 true。
专项合成合同测试 `34 passed`，D6 全量 `457 passed`，仅证明当时的接口合同。权威 v2 的正式合成证据
及其限制以上一节独立复核为准。

冻结模型、正式 900 帧 held-out 制品和同 seed paired formal shadow 已形成。下一步转为去合成捷径的
外部泛化复验；D6 只复核证据，不把 clean data、held-out 或 paired-shadow 单层通过写成模型 promotion。

## 2026-07-21 运行时计划结果联接复核

### 复核结论

D6 已建立从 main 运行时计划确认到离线观测结果的独立消费者。实现不导入控制栈，不向在线总线暴露
truth，也不根据距离重建 `global_track_id`。身份只来自 D2 已验证的 source-observation lineage；物理
状态和 5 米事件在身份确定后才进入离线窗口统计。

每条 ACK 重新核对 D3 plan 和可选 D7 guidance 的 bus sequence 与规范 payload SHA。assignment、
guidance 和 ACK 三侧 binding 必须一致。一个资源的结果窗从本次 ACK 开始，到下一条同资源 ACK 前
结束；最后一窗到 episode 终点。该设计避免一个物理样本同时归属于相邻两次决策。

输出的 `bounded_assigned_pair_best_distance_progress_v1` 只表示分配目标在窗口内的最佳距离闭合程度。
hold、缺 D7、映射歧义、状态窗不完整或 ACK 未接受时为 null 并给出原因。即使观测到 5 米事件，该值
也不升级为正式 D3 reward；反事实和因果字段保持 unavailable。

### 验证

- 专项：`22 passed`，覆盖正常双窗口、合法同身份 refresh、真实 main 3v3、清单/CLI、外层和内部哈希、
  sequence/payload 错配、错误或陈旧 plan version、同版本执行签名篡改、额外 binding、D2 映射缺失/
  歧义、truth/proximity 篡改、ACK 自报结果、hold/缺 D7 和错误目标事件。
- 全量：`423 passed`，1 条既有 Matplotlib `Axes3D` 环境 warning。
- 真实集成正例：3 目标/3 资源、recon=1、seed=70、1.2 秒，2 ACK occurrence、6 binding window、
  online truth=0、PPO/assist/authority=false。
- 篡改负例：同版本刷新改变 coalition binding，即使同步重算单条消息摘要，仍按执行签名漂移拒绝。

上述测试是代码和接口证据，不是正式多 seed 性能实验。下一步由 main 把 hash spec 和 D6 输出自动
接入 episode，随后运行同 seed paired formal shadow、学习实际采用和保留 seed 验收；三类学习权限
在此之前不开放。

## 2026-07-21 跨模块学习数据联合准入评审

D6 已实现独立、只读的联合准入入口。输入包括 training/shared seed registry、D3 正式 manifest、D4
正式 manifest 与 main 生成的独立 canonical view、D5 tracklet 和 active-vision 的正式
manifest/view/readiness，以及 D4/D5 supplemental summary。入口验证 schema、来源身份、文件与内容
SHA-256、dirty source、缺失输入和 seed assignment。入口现在显式接收 D3、D4、D5 三份 producer
全样本审计及调用方提供的文件 SHA-256，不调用 main runtime，也不修改生产者制品。

真实审计覆盖 900 episode 和 100 个训练 seed。规范 train/validation/test 为 60/20/20，保留 seed
`1000-1019` 泄漏为 0。D4 formal view 文件 SHA-256 为
`73a365d32b0439fbf805f40ea7941b8e992fe4c68687cbc5496704f230440b11`，与 D4 supplemental
canonical view 分层。D4 补充课程覆盖 hold 100、request-replan 200、nonzero quota 200、transfer
100，canonical episode/frame 切分为 `60/20/20` 和 `180/60/60`。D5 补充课程覆盖
hold/observe-target/reacquire/search-sector=`200/600/200/200`、
wide/zoom=`1000/200`、interceptor/recon=`600/600`。

D5 tracklet 的 480 条候选边中，362 条为正标签、19 条为负标签、99 条未标注。D6 发布
`labeled_count=381`、`unlabeled_count=99`、`complete=false` 和 `status=partial`，不再用单一
`available=true` 表述部分标签。

D5 synthetic ACK 的 applied/rejected/missing 各 400，只能说明故障注入分支被测试，不能归因到运行时
动作执行。当前 reward、outcome、counterfactual、causal、runtime ACK 和 paired shadow 证据均
unavailable。D5 supplemental BC 的 producer 全样本审计已完成：100 episode、1200 sample，canonical
episode=`60/20/20`、sample=`720/240/240`，online/offline/descriptor 各 100 个，`302/302` 个登记
制品通过校验，有限特征 `1200/1200`。online truth、保留 seed、dirty episode 和 D5 身份创建、改写、
换绑计数均为 0；四类离线标签保持 unavailable 且没有补零。

D3 全样本审计覆盖 900 episode、1604 decision frame、3,658,815 candidate edge、117,304 selected
action 和 43,905,780 个有限特征值。D4 全样本审计覆盖正式 900 episode/1798 sample/14384 action，
以及补充 100 episode/300 sample/1200 action。D3/D4/D5 审计文件 SHA-256 分别为
`62a47df8...17fb`、`4245f1db...9e46`、`9a036535...2d3`，内容 SHA-256 分别为
`954f3e96...1867`、`94f4f4bf...3e7f`、`a11b6559...50dd`。D6 重新校验 expected/actual binding、
binding checks、计数、零违规和来源绑定。任一文件篡改、错绑定、状态或权限误开都会失败关闭。

联合状态分为 D3/D4/D5 full-sample 和跨模块 structural full-sample=`complete`，overall admission=
`partial`。D3 `reward_components` 不是 runtime reward，D4 projected recommendation 和
`target.kind=rule` 不是 runtime ACK 或 truth。当前没有训练结果或模型收益结论。下一步由 producer
补齐真实动作采用、版本绑定、runtime ACK、可归因 reward/outcome 和终局结果；由 main 组织因果/
反事实、同 seed paired shadow 与保留 seed `1000-1019` 独立验收。上述证据形成前，PPO、在线 assist
和控制 authority 不开放，规则回退保持强制。

报告写盘前会拒绝 output directory 等于或位于正式 generation 根下，避免审计输出改变正式树却仍声明
source mutation 为 false。2026-07-21 联合审计专项 `37 passed`，D6 全量 `401 passed`；仅有既有
Matplotlib `Axes3D` 环境 warning。真实 JSON 与中文 Markdown 已写入 D6 自有输出目录，正式 900
episode 源数据未修改。

## 2026-07-21 历史共享种子划分评审

以下内容记录 detached canonical views 生成前，对原始 manifest 的直接比较结果。当前联合准入结论
以上一节为准，历史 mismatch 仍用于说明原始 split 来源。

D6 已形成独立的 canonical split consumer。它从 detached registry 和源 training registry 读取证据，
复算内容哈希、assignment 哈希和冻结数值 seed 排序，不调用 main 仿真或学习运行时。模块 manifest 只读，
D6 没有修改 D3、D4 或 D5 划分的权限。

正式 900 episode 审计确认注册表自身有效，训练 seed 100 个、保留 seed 20 个且无重叠。D3 的
60/20/20 划分与 canonical exact。D4 的 70/15/15 划分有 51 个 seed 不一致；D5 图数据和主动视觉数据
各为 60/20/20，但具体 seed 分配分别有 65 和 62 个不一致。对应受影响记录为 D4 459 episode/917 frame、
D5 图数据 8350 graph record/284 candidate edge、D5 主动视觉 558 episode/713298 sample。

评审结论是联合训练继续不可用。单模块行为克隆开发结果可以保留，但不能跨模块拼接训练、调参或发布
联合测试指标。下一步由 main 协调 D4/D5 生成 canonical split view；D6 只复核 exact match 和保留 seed
隔离。即使 split 修复，奖励、运行确认和 PPO producer 条件仍需分别验收。
本次接受门限是注册表八项 validation 全真且四模块 exact。注册表有效但联合门未通过。2026-07-21
D6 全量回归为 `364 passed`，仅有既有 Matplotlib `Axes3D` warning。

## 2026-07-20 正式学习标签审计评审

D6 已新增独立的学习标签审计和 sidecar 构造边界。实现不导入 D4/D5 在线控制，不修改正式学习数据，
也不把 actor/object/truth ID 写入在线特征。校验范围覆盖正式生成身份、900 episode、100 个训练 seed、
20 个保留评估 seed、模块内及跨 D4/D5 split、文件哈希、共享对象键和 offline 四层标签空值合同。

评审确认 outcome 与动作归因必须分开。D5 相邻 snapshot、projection 或相机姿态可以说明后续观测变化，
不能证明相机命令已经应用。正式 1,153,242 条样本的 runtime ACK 全为 null，后续相机反馈也没有形成
可用的 accepted command version 链。因此 D5 observed outcome `1,063,214` 条可用，reward 为 0 条
可用；行为克隆合同可用，PPO 不可用。D4 同理只有 `898/1798` 条相邻区域 outcome，缺少 recommendation
采用/执行证据，reward 为 0 条可用。

当前 D4 规则动作共 14384 个，但非零 quota、hold、request-replan 和 transfer 均为 0。该数据可以
验证行为克隆输入合同，不能用于说明策略覆盖或性能。D5 规则 intent 有 observe-target、reacquire 和
search-sector，effective mode 全为 disabled；这些规则动作可以作为示范，不能解释为已执行动作或因果
最优动作。

D4 与 D5 的 seed split registry 不同。423/900 个 episode 的 split 不一致，涉及 47/100 个 seed。
两个模块各自没有 seed 跨 split，因而单模块行为克隆仍可准备；联合训练会发生跨模块 train/test 污染，
当前明确标为 unavailable，不通过改写某一侧 split 来掩盖问题。

反事实和因果标签保持 unavailable。单事实轨迹没有同初态替代动作结果，填 0 会把“未知”错误写成
“无效果”。后续只有在 main/D4/D5 持久化版本化动作采用、运行确认、后续反馈、终局结果，以及同初态
配对重放或干预证据后，D6 才重新开放对应 reward、PPO、counterfactual 或 causal 准入。

专项 17 项测试覆盖 accepted/rejected/missing ACK、无后继、D4 无归因、schema/identity/split、跨模块
split、保留 seed、离线空值、篡改和确定性发布。2026-07-21 D6 全量 `351 passed`，仅有既有
Matplotlib `Axes3D` warning。审计证据日期固定为 2026-07-20。该结论属于正式离线数据审计，不是
AirSim 或实飞性能结果。

## 2026-07-20 Scalable 3D 实验矩阵评审

评审确认 D6 v5 保持只读边界。矩阵身份仅来自 scenario config metadata；D6 不导入 main runner，不按
R0/G1 等目录名识别变体。R0/G1/A1/A2/A3/C1/F1 的 runtime 解析和实际采用分开审计，规则回退或采用
证据缺失时不报告执行有效。

完整性按每个显式比较键使用固定六 cell 分母，三个完整体系场景增加 F1。variant 统计覆盖有限状态、
在线真值、硬约束、ID switch、分配、跨视角、主动视觉、五米事件和阶段耗时。R0 配对差值按同键计算，
至少两个键才产生 bootstrap CI；clean/formal 与 dirty development 使用不同统计子集，报告不做无配对
或仅开发证据的因果归因。

producer 风格专项 `40 passed`、D6 全量 `320 passed`。既有 R0 dirty smoke 仅有 1/6 cell，不能形成
算法比较。D4 advice 单独仍不证明采用；main 消费合同通过完整引用、summary 一致性和 D3 hint applied
审计后可形成 A2 adoption evidence。正式完整矩阵尚未运行，后续由 main 提供 clean、多场景、多规模和
未见 seed 的 episode 集合及显式 matrix manifest。

## 2026-07-20 Scalable 3D schema 合同复核

评审确认真实 online observation schema 为 `scalable3d-observation-v1`。D6 fixture 已对齐；离线
consumer v4 使用独立、版本化 registry 精确核对 world、bus、scenario、online observation、offline
truth 和 config schema。该 registry 只描述评估器当前支持合同，不调用 main 运行逻辑。

历史 row 继续展示原始 schema 值。当前匹配状态单独输出；旧值、未知值和篡改值为 match=false 并保留
failure reason，缺字段为 unavailable。整体 match 已进入 clean formal acceptance，避免“字段非空即
合法”。专项 `32 passed`、D6 全量 `304 passed`；当前 6v6 producer smoke match=true。

## 2026-07-20 Scalable 3D 主动视觉证据评审

评审确认 D6 v3 只消费持久化主动视觉命令、运行时 ACK 和 summary counters，不调用 D5 policy 或 main
控制接口。命令层分为规则实际动作、影子模型建议和经安全外壳采用的 assist 动作；ACK 层再区分 applied
与 rejected。shadow 输出不替换规则动作，assist adopted 也不能替代 main runtime applied。

命令与 ACK 使用 camera/resource、issued timestamp、plan/coalition/communication version、intent 和
requested/effective mode 关联。任何 schema、数量、版本键或 summary reason distribution 冲突都保留
失败原因；过期、过时版本、相机不可用和其他拒绝分别统计。目标航迹编号只核对此前 D2 中心航迹快照，
ACK 改写或引用未知编号使正式 evidence fail closed。该检查不授予 D6 任何重绑定权。

物理层继续保持不可归因。一个 assist 命令 applied 后出现五米接近，只能证明两个事件都发生；没有同
seed 的规则控制组、相同配置和模型版本证据时，物理 attribution 必须为 null。正式主动视觉效果比较
至少需要 20 个未见 seed 的配对输入，再按 seed 聚合，不允许用帧数扩大样本量。

2026-07-20 的 8 项确定性测试和既有 17 项 scalable 测试合计 `25 passed`，D6 全量 `297 passed`。
覆盖显式 T/R/Rc/Cam=`6/4/1/5`、双 seed 报告和全部主要负例；上述 fixture 本身未启动 runtime/AirSim。当前可
关闭 D6 consumer/report 缺口，不能关闭 main producer 持久化、assist 准入或物理性能 P1。

当前 main runtime 的 6v6/recon1/camera7、seed 37、2.2 s 临时 smoke 进一步产生 133 条 command 与
133 条 applied ACK，零 reject、零中心航迹引用违规、零 truth field violation，summary 一致。该
worktree 为 dirty 且只有单 seed，因此评审只确认 producer/consumer 接线，不把它列为正式模型或物理
证据。

## 2026-07-20 Scalable 3D 学习运行时与 D4 advice 评审

评审确认 `d6-scalable3d-offline-evaluation-v2` 保持 D6 被动边界：只读取 main 已写盘 episode，
不导入 scalable runtime、不发布总线消息、不参与控制，也不读取在线真值。config/summary 的
`scalable3d-learning-runtime-v1` 必须按来源保留并做一致性检查；manifest/config 的 D3/D4/D5 runtime
version 交叉验证。模型 fingerprint/version 只有 bundle loaded 且 fingerprint 与 version 后缀一致时
才 available，规则 fallback version 不作为学习模型证据。

D4 advice consumer 只准入 `d4-region-resource-advisory-runtime-v1` 和经过安全投影的 recommendation。
审计覆盖 schema/scenario/version/seed、authority digest、policy、plan/version、epoch、lease、action、
transfer、quota conservation、projection rejection 及 formal decision digest。任一旧 schema、缺版本、
过期栅栏、非法字段、非守恒 quota 或 digest flag 篡改均 fail closed；报告同时保留非法/版本原因，
不从合法子集计算看似可用的 mode、fallback 或 latency 分布。

证据解释分为五层：bundle loaded 只证明可加载；shadow output 只证明产生合法 recommendation；assist
eligible 只证明准入门；control adoption 需要独立 producer evidence；physical outcome 仍是离线几何
结果。D4 advice 的正式裁决 digest 保持 unchanged，`assist_eligible=true` 不能报告控制生效。当前
独立证据是 `d4-region-resource-consumption-v1`；合法消费且 D3 明确应用 hint 才计 adoption，后续五米
事件仍不归因于 advice。

规模与统计口径未改变：按 scenario/version 和实际 target/resource/recon/camera 分组，以不同 seed 的
episode 均值 bootstrap；单 seed descriptive-only。正式 evidence 继续要求 `repository_dirty=false`，
并校验 config hash、D4 policy version、finite 和 online truth 隔离。

2026-07-20 的 deterministic fixture 验收覆盖 disabled、三模块 missing bundle、assist-to-shadow、
assist gate、守恒/非守恒、projection、mutation/unchanged、digest 篡改、旧 schema、缺 plan version、
缺 advice 和 seeds 1/2 聚合；scalable 专项 `17 passed`、D6 全量 `289 passed`。结果只关闭 D6 consumer/
report GAP，不证明真实模型性能。消费合同扩展后的 scalable 专项为 `40 passed`、D6 全量
`320 passed`；临时 5v5 producer smoke 的合法消费与 adoption 均为 1。后续由 main 提供 clean、多规模、
多 seed 正式矩阵；D6 不从 mode、终态、目录名或物理接近推断缺失层。

## 2026-07-15 legacy provenance 与真实三档评审

评审确认 legacy fallback 是 case 注册驱动的持久化证据审计，不是目录名推断：仅路径输入且所有
summary/case/result provenance 缺失时，要求 20/20 sibling generated settings 显式、有限、正数且
一致。缺文件、缺键、冲突、NaN/Inf/字符串均 fail closed；mapping 与部分显式 provenance 不回退。

真实三档报告已生成：60 case、20 个跨档配对、truth identity/state 全 0；1.0 由 20 份 settings
闭合，0.2/0.1 为 case result provenance。冻结合同为 56 match/4 mismatch，四个受影响 candidate
case 明列原因且 aggregate unavailable；reserve 排除和 timing 分层不变。baseline 可用物理结果为
0.1 `4/30,4/20,0/10`、0.2 `9/30,9/20,0/10`、1.0 `6/30,6/20,0/10`。case wall timing 缺源字段。
因此不从 candidate 0.1/0.2 部分证据给出性能或准入结论。专项 `18 passed`、全量 `272 passed`。

## 2026-07-15 0.1 P1 NameError 紧急评审

评审确认根因修复不是放宽 case-aware 合同，而是消除模式 helper 的名称/定义顺序漂移：唯一 helper
在所有 dispatch 之前定义，三个调用点一致。新增 20-case 双层 merged evaluator 回归直接覆盖此次
失败入口。

真实 0.1 P1 v6 只读报告生成成功，两层各 4036 records、20 case，manifest match，runtime 输入 hash
不变。timing 专项 `28 passed`、D6 全量 `264 passed`。该证据关闭 D6 runtime NameError 回归，不代表
三档 comparator 已完成或形成性能结论，无新增 D6 P0。

## 2026-07-15 0.2 case-aware 与机会合同评审

评审确认 `d6-stage-timing-report-v2`/P1 v6 已关闭 merged suite loader 缺口。suite 模式仅接受
`case_id/family/profile/seed`，每 case 内保持严格单调，边界可重置；双层 manifest 必须一致，禁止
跨 case 连续化和 main/control 求和。默认 single episode 行为未改变。

`d6-m5n2-clock-speed-comparison-v2` 将每 case 机会冻结为 `3/2/1`。actual-execution unavailable 或
机会不符时，整项 unavailable，报告列 case/reasons；standby reserve 即使成功也不计 active-primary。
真实 0.2 20-case 审计为 18 match/2 mismatch：candidate seed006 为 D7 unavailable 且 reserve success
被排除，candidate seed009 的 D7 available 但机会仍为 `2/1/1`。两层 merged timing 各 6567 records/
20 case 的只读 P1 复测通过。该 0.2 阶段专项 `27/10 passed`、当时全量 `263 passed`。真实 0.1 P1
状态见顶部；该段记录 0.2 阶段状态，三档 comparator 随后已完成。

## 2026-07-15 ClockSpeed 三档能力评审

评审确认当时的 `d6-m5n2-clock-speed-comparison-v1` 已关闭 D6 离线比较入口缺口；当前 schema 已按
顶部合同审计升级为 v2。三档输入必须各包含
baseline/candidate seed 1-10，并按 `case_id/profile/seed` 完整配对；ClockSpeed 来自 suite/case
persisted provenance，不能由目录名决定。result row 全量一致的显式 `clock_speed` 可作为 case-level
provenance，并与注册 artifact 中的显式值交叉校验。

报告保留三层独立物理分母、第二 primary 五米/距离、最终锁/coalition consensus、collision stop、
case wall、main-bus/control-tick wall timing、归一化 simulated time/tick 和 truth identity/state
审计。缺证据为 unavailable；main bus 是 control tick 内层，禁止相加。任一 profile 的 10 case
不完整时不发布部分 aggregate。

2026-07-15 三档各 20 case 的确定性验收专项 `8 passed`、D6 全量 `254 passed`，仅有既有
Matplotlib `Axes3D` warning。该段是运行前结论；真实三档 comparator 随后已完成，availability-aware
结果见顶部。candidate 0.1/0.2 仍因合同 mismatch 不形成完整准入结论，无新增 D6 P0。

## 2026-07-15 M5N2 20-case 评审结论

评审范围严格限定为 baseline/candidate 各 10 seed 的 20 个真实 AirSim M5N2 case。M5N2 完成后、
`TERM` 生效前额外完成的 `png_ttc` seed001 明确排除在 M5N2 20-case 聚合与验收之外。其余 tuned
2v2 和全部 dropout 未执行；缺失 case 保持 unavailable，不补零，也不构成完整 suite。canonical
actual evidence 为 `20/20` available，校验原因 0，在线 truth identity/state 均为 0。

正式物理结果是 pair `12/60`、target `12/40`、coalition `0/20`。第二 primary 七阶段
availability 全部完整，前四阶段通过 `20/20`、control/mode=`17/20`、physical=`0/20`；20 个
首失败原因全部可用。该结果说明 D6 口径已经能定位断点，但第二 primary 和联盟物理闭环未完成。
baseline/candidate 总成功数相同，逐 seed non-degradation=false，candidate 不应晋升默认路径。

术语审计统一为：canonical target physical success 是至少一个 participating pair 成功，本批为
`12/40`；cooperative target-stage diagnostic 是全部 required member 通过某一阶段。后者不能覆盖
正式 `target_intercept_success`。20 个第二 primary 最终均为 `collision_stop`，但 collision object
未写盘，D6 不推断成员冲突、环境碰撞或 AirSim 状态问题，原因对象保持 unavailable。

两层 timing 各 3805 条。main bus mean/P95=`349.34/487.40 ms`，control tick=
`1069.45/1254.06 ms`；二者嵌套，禁止相加。逐 case 原始文件可严格消费，但 partial acceptance
没有注册路径，suite 合并流又在 case 边界重置 frame/time，正式 timing 仍 unavailable。下一步由
main 修复 case-aware 接线；系统侧优先降低 D1 fusion、AirSim frame sample、bus processing 和
control RPC 延迟。另需区分 canonical “任一 pair 成功”的 target physical 与 cooperative “全部
成员阶段通过”的 target 诊断，后者不能覆盖正式 `target_intercept_success`。D6 不参与控制或阈值
放宽。

## 2026-07-15 第二 primary 与联盟完成口径评审

评审确认 `d6-cooperative-closure-v3` 已关闭 D6 被动报告缺口。第二 primary 具备从分配到物理结果
的七阶段漏斗；pair、target、coalition 保持独立机会数和 availability，coalition completion 不由
target success 推断。producer 未写首失败原因时，D6 只报告原因缺失，不构造 `unspecified`。

确定性专项 `11 passed`、当时 D6 全量 `246 passed`，`py_compile` 通过。其后 main 已生产本页顶部
的 20-case M5N2 证据；结果确认第二 primary 未完成五米拦截，coalition 未达门限。额外完成的
`png_ttc` seed001 不进入该聚合，其余 tuned 2v2 和全部 dropout 需作为后续独立批次。

## 2026-07-15 D2 ceiling-aware v2 正式证据评审

评审确认 D6 已关闭“尚无 D2 v2 正式证据”的 P1 报告缺口。aggregate 直接保留 producer 的
`promotion_recommended=true`、promotion candidate、selected/default path、14 条 overall/分档
assessment、五 gate reason 和 dropout truth alignment；legacy 缺字段保持 `None/unavailable`，
`producer_decision_recalculated_by_d6=false`。

总体 GNN 五 gate 通过且仅建议评审。分档只有 clutter/combined 通过；delayed_noisy、dropout、
nominal、tight_crossing 因 baseline IDSW=0 无可测 reduction evidence 而 fail-closed。dropout 在
10-seed screening 和 20-seed confirmation 全部为 partial truth alignment；JPDA 是 research-only
adapter 且不准入。默认在线 GNN/Hungarian 未改变。

本批没有安全复用异批 D1/D3/D4/D5/D7，六源均 unavailable，因此不是全系统通过证据。输出四件套
位于 `research_modules/d6_evaluation_metrics/outputs/p1_identity_ceiling_aware_v2_20260715/`；专项
`31 passed`、D6 全量 `243 passed`，未启动 AirSim。剩余 P1 是 promotion 评审、同批多源系统判决
和长期趋势，不再包括 D6 v2 parser/aggregate/中文报告能力。

## 2026-07-15 分阶段延迟评审结论

D6 已具备 main bus 与 SimpleFlight control tick 两层持久化计时的严格离线消费能力。非法合同、
数值、状态、顺序、和式或预算标志 fail closed；旧日志缺 timing 保持 unavailable。每层独立报告
分布、状态计数、预算违例和 dominant stage，禁止把 control tick 内的 `bus_processing` 与 main
bus 相加。该历史阶段 P1 acceptance 为 v5，当前 case-aware 接线为 v6。

2026-07-15 合法两层各 2 帧及负例矩阵专项 `20 passed`、D6 全量 `236 passed`，未启动 AirSim。
关闭的是计时可观测性代码 P1，不是系统性能 P1；其后 M5N2 20-case 已确认 `100 ms` 不达标，
case-aware 正式接线已关闭，瓶颈优化仍开放。

## 2026-07-14 actual target-state freshness/stale P1 评审结论

评审确认 D6 已关闭从最终 command 到 canonical actual evidence、source-hash validator、逐 case、
pooled aggregate 和正式 CSV/JSON/中文 Markdown 的完整 freshness/stale 指标链。六个字段均为必需；
所有缺失、非法数值、时间/age 冲突、非法 stale 或空 source 都 fail closed。显式零和真实正 stale
均保留 availability，不以零代替缺证据。

真实证据为 2026-07-14 tuned 2v2 seed-1 48 samples 与 M5N2 seed-1 608 samples；mean/p95/max
分别为 `0.0375/0.2/0.2 s` 和 `0.091118/0.2/0.2 s`，stale 均 0，来源均为
`d2_estimated_global_track`。validator 已用 source path+SHA256 重算并与 payload 对照，2/2 case
available。D6 全量 `216 passed`。该结论只关闭单 seed 正式指标链；multi-seed 趋势、跨提交回归
和 failure taxonomy 当时仍为 P1。顶部 20-case 已补齐 10389 条同配置 multi-seed 样本；当前剩余
跨提交回归、failure taxonomy 和独立批次复验，physical、五层、truth 与 availability 语义不变。

## 2026-07-14 actual v2 真实 AirSim 最终评审

评审读取统一 D6 acceptance report 与 main 实验报告，确认 tuned 2v2 seed-1、M5N2 seed-1 的
required/available/unavailable=`2/2/0`，actual execution P0 全可用门通过。两例
summary/CSV/actual 物理成功计数均为 `2/2/2`，旧
`d7_actual_execution_command_physical_count_conflict` 未复现并关闭。

M5N2 pair=`2/3`、target=`2/2`、coalition=available `0/1`；coalition 是完整证据下的失败，
不能由 target `2/2` 代替。`overall_acceptance_passed=false` 的范围是完整 P1 suite：当前仅
2 个 seed-1 case，未覆盖 baseline/candidate 配对、1-5 帧 dropout 和 multi-seed。性能结果
`123.3/384.6 ms`、budget violations 合计 `231` 仍为 P1；M5N2 第二 primary 物理闭环也保持
开放。D6 本批只同步文档状态，不改代码或控制边界。

## 2026-07-14 actual-execution/arrival 最终评审（真实重跑前历史）

评审确认 D6 formal gate 只接受通过校验的 canonical `d7-actual-execution-metrics-v2`。任一
required case 缺失或 explicit unavailable 时 `actual_execution_all_available=false`，suite 总验收
fail closed；legacy main row 与离线五米结果仅作 diagnostics，不能替代 actual envelope。

`arrival_coordination_required=false` 时，coalition completion 采用每个 required active primary
独立五米成功的口径，全部 required primary 成功才完成 target coalition。required-primary
denominator/member、physical result 或 coordination 字段缺失，以及 summary/pair 冲突，仍输出
`null/unavailable`，不补零或推断 arrival window。

2026-07-14 仅完成代码级回归：专项 `14 passed, 24 deselected`、D6 全量 `190 passed`。唯一
Matplotlib `Axes3D` warning 只限制 3D projection，不影响 JSON/CSV/Markdown、二维报告或本轮
结论；未运行 AirSim。D6-owned P0 已关闭，但 main-owned P0 仍开放：M5N2 baseline、M5N2
candidate、2v2 PNG-TTC、1-frame dropout 四个历史真实 seed-1 actual artifact 均为
`unavailable`，原因均为 `d7_actual_execution_command_physical_count_conflict`，需 main 真实重跑
并注册有效 v2 artifact。P1 继续为同配置 multi-seed provenance/freshness 趋势与 failure taxonomy，
不因本轮 fixture 回归关闭。

## 2026-07-14 owner provenance 最终评审结论

D6 actual envelope 不把 owner 当作每行无条件必填 provenance。plan ID/version 仍逐行必填；owner
只对 effective-authorized 的 secondary/distributed active/execution/reassignment 或显式 execute
action 行必填。中心授权与未授权 pre-transition/pending 行可为空，整集无 authoritative owner 时
`owner_node_ids` 为空且 availability 为 unavailable；需要 owner 的执行行缺值继续 fail closed。

2026-07-14 确定性离线验收（seed N/A）为 execution-evidence focused `20 passed`、D6 全量
`184 passed`，1 条既有 matplotlib warning；未运行 AirSim。评审结论关闭 D6 owner 语义 P0，
不改变 main 的真实 seed-1 注册和 multi-seed P1。

## 2026-07-14 actual plan identity 评审结论

本轮确认并关闭了 D6-owned P0：最终计划身份现在由 actual command CSV 证明。envelope v2 输出
去重的 `plan_ids/plan_versions/owner_node_ids` 和逐项 provenance；合法多版本保留，同一 plan 的
版本冲突、缺列、坏类型及 payload/source 不一致全部拒绝。merge v3 会移除 replay 的同名字段，
只采用 validator 返回的 actual metadata，不影响既有 safety、physical 和 mode 口径。

2026-07-14 离线 focused `24 passed`、全量 `180 passed`，`py_compile` 通过；该阶段没有真实
AirSim。评审结论覆盖 D6 consumer/validator/merge；真实 seed-1 注册和单 seed freshness/stale
正式链已由顶部证据关闭，同条件 multi-seed provenance、freshness 趋势/failure taxonomy 和
D2-D3 跨源 join 仍为 P1。

## 2026-07-14 actual execution 评审结论（真实重跑前实现评审）

D6 已完成执行证据来源隔离。`integrated_replay` 只说明离线重放状态；SimpleFlight actual
execution 必须由最终 command、physical summary 和 main bus performance 三源联合证明，并由
独立 `d7-actual-execution-metrics-v2` 固化路径与 SHA256。raw mode change 不等于获授权的执行
模式切换，规范计数使用 `mode_switched AND effective_control_authorized`；无性能样本不允许发布
零时延。

main 的稳定调用入口为 `write_d7_actual_execution_evidence()`。writer 成功后再调用既有
`register_terminal_closure_case_evidence(..., d7_execution_metrics_path=actual_path)`。任一来源
缺失或冲突时不注册，不得搜索相邻文件或回退 replay。

两组最新既有 M5N2 seed-1 离线复核证明原歧义真实存在：raw replay mode 17/13 与 actual
effective control 0 冲突，raw loop 0 又无性能样本；final main bus loop 为 386.519/398.333 ms。
新 builder 生成 actual mode 0、sample 142/141，符合控制和性能证据。D6 `168 passed`。本批关闭
D6 代码级 P0；main 此后已生成/注册顶部两条独立 artifact 并完成真实 AirSim seed-1 复验。
multi-seed、完整 P1 矩阵和性能仍开放；D6 不越界修改 runtime。

## 2026-07-14 多案例 D3/D7 证据评审（先前四案例）

D6 已把 terminal closure 的评估单位从“一个可选 D3/D7 summary”扩展为 main rows 中显式登记的
`(case_id, seed, path)`。D3 逐 case 运行 canonical validation，再输出逐 seed 和 suite count/churn；
D7 逐 case 验证结构与 seed，但 raw EpisodeMetrics 缺 terminal envelope 语义时不进入四层聚合。
该设计的工程理由是：同一 suite 可包含 M5N2、2v2 PNG-TTC 和 dropout，不应选择一个 D3 文件
代表全部 case，也不应因某个坏文件使其余 case 丢失。

现有 seed-1 suite 验证结果：D3 4/4 case、543 records；D7 原 main summary 0/4 path registered，
原因全部为 `d7_execution_metrics_path_not_registered_by_main`。临时显式登记现有文件后 D7 4/4
结构有效，control allowed 合计 51，与 main 四层值一致但未二次累计。D6 全量测试
`159 passed`。

后续计划由 main owner 执行 runtime helper 接线和正式 suite 重生成；D6 owner 只在 producer
合同变化时扩展 schema validator，不通过 glob 或目录命名规则补路径。正式 D7 4/4 registered
之前，multi-seed 的 D7 execution evidence 不准声明闭合。

## 2026-07-14 terminal suite P1 评审结论

D6-owned terminal suite schema、consumer 和报告链已关闭。`P1AcceptanceReportGenerator` v2
将 contract/control/switch/mode/physical 计数转为带 producer/scope/denominator/lifecycle 的
长表；只在 source+producer+scope+lifecycle 单一组内聚合。main planned-lock 与 D7 execution
同名指标并存时顶层 sum 为 null，各组单列，不比较或覆盖。

terminal suite 新增 D3 canonical file input，输出 latest plan/version、primary/reserve membership、
owner 和 feedback churn。性能指标要求正 sample count；无样本零不可用。candidate
non-degradation 与 effectiveness 分离，双零且零触发为 inconclusive，不推荐晋级。产物已覆盖
per-seed/aggregate JSON/CSV 和中文 Markdown。

2026-07-14 确定性离线验证专项 `8 passed`、canonical `24 passed`、全量 `154 passed`，1 条
既有 matplotlib warning；未运行 AirSim。下一步不在 D6：main `p1_terminal_closure` 需生产
规范 envelope、physical/performance/candidate 字段并传 D3/D7 文件，随后运行真实同条件
multi-seed batch。以下 physical provenance 等章节保留其独立状态。

## 2026-07-14 truth-state/physical provenance 评审结论

D6 已将 truth identity 与 truth state 正式拆成两个 availability-aware 计数。strict
`d2_estimated_global_track` 路径为 state-use available `0`，显式
`airsim_actor_truth_fixture` 为 `>0`；summary 零不能覆盖 pair/command 正证据。physical layer
现在要求 summary 与 active pair summaries 同时存在，command-only 和 summary-only 均 fail
closed。每个 active pair 必须显式 `physical_evidence_available=true`，且
`target_state_source` 与 summary online source 一致；offline scorer 只允许 D2 estimated
class，truth fixture 只允许显式 fixture class。command loader 保留 evidence 字段供审计，但
layered metrics 不再从 command rows 构造 physical pair。任一 gate 失败时 pair/target/
coalition 与 physical count/rate 全为 `None/unavailable`，旧无来源 status 只保留 raw audit。
每个 participating pair 还必须有显式 physical 布尔结果或规范 scorer 终态；coalition 缺
required member、arrival window、denominator 或 summary completion 时单独 unavailable，完整
显式失败保持 available `0`。各报告格式与 coalition metadata 使用同一 reason。

2026-07-14 使用 7 类确定性离线 provenance 场景达到全部 exact 门限，seed N/A；D6 全量
`150 passed`，1 条既有 matplotlib warning，未运行 AirSim；其中新增 7 项覆盖 result/member/
window/denominator/显式零。2026-07-11 至 07-13 历史
physical 数值若缺新 provenance，不作为迁移后 offline scorer evidence。本次只关闭 D6 P0
代码/测试；单 seed freshness/stale 正式分布已由本文顶部关闭，真实同条件 multi-seed AirSim
physical evidence 和跨提交 freshness 趋势仍为 P1。

## 2026-07-14 truth tracking 当前评审结论

truthless tracking 假零 P0 已关闭。`EpisodeMetrics`、collector、main-bus loader、merge 与
reporting 统一使用 null/unavailable；合法 truth identity history 中无切换则显式输出
available `id_switch_count=0`。JSON、CSV 和 Markdown 都携带同一 availability，旧载荷即使
含零也不能覆盖 unavailable。

2026-07-14 以 5 个确定性场景验收，seed N/A；空输入、匿名 track、不完整 sidecar、完整
truth 稳定/切换均达到预定门限，D6 全量 `137 passed`，1 条既有 matplotlib warning。本轮
没有 AirSim 物理实验。真实 multi-seed seed/config/schema/hash provenance，以及 D2 lifecycle
与 D3 churn 的 episode clock/global ID/plan version join 仍为 P1；P2 external benchmark
状态不变。

## 2026-07-14 第二批当前评审结论

D6 已接入 `d3_plan_history_v1/history[]` canonical ordered evidence。该分支严格校验 wrapper、
record、record_count、sequence/order key、timestamp、assignment/coalition/feedback/owner 和
truth 隔离；不对坏文件重排序，不从 plan version 推断 tick 顺序。无效历史的 churn、成员、
owner 与 feedback 指标全部 unavailable，稳定原因码进入 CSV、aggregate JSON 和 Markdown。

membership 现在比较相邻 assignment snapshot 的 target/resource/role/activation 状态；重复的
producer audit event 不增加计数。新增 primary/reserve membership 分项、soft/hard feedback，
并让 D3 canonical 行正式输出 owner change。计划、联盟 version 和 coalition epoch churn 由
同一 validated history 计算。

2026-07-14 专项 `24 passed`、D6 全量 `132 passed`，1 条 matplotlib `Axes3D` 环境 warning。
旧 snapshot/cooperative-role 回归继续通过。当前剩余 P1 为真实 multi-seed episode 趋势和
failure taxonomy；P2 external benchmark 不变。本轮无新 AirSim 物理结果，D6 仍为 file-only
被动消费者。以下第一批和更早章节为历史评审记录。

## 2026-07-14 第一批评审结论（历史）

已确认的 D3 churn availability 评估级 P0 已修复。统一报告现在只在 producer 显式写出
count，或至少两条记录具有顺序语义且该指标证据完整时，才计算
`plan_version_churn_count`、`coalition_version_churn_count`、
`coalition_epoch_churn_count` 和 `membership_change_count`。显式零和稳定有序历史输出
available `0`；最终快照、空 mapping、单条无序记录与不完整历史输出 unavailable。

2026-07-14 的 5 类 fixture 验收标准是前三类四项全 unavailable、后两类四项全 available
`0`；专项结果 `12 passed`，D6 全量 `120 passed`，另有 1 条 matplotlib `Axes3D` 环境
warning。正式 40-case cooperative-role 分支继续只报告角色，四项 churn 保持 unavailable，
因此现有 M5N2 角色/coalition 报告兼容。

当前剩余 P1 为真实有序 D3 plan history/provenance、长期 multi-seed 跨提交趋势和跨批次
failure reason taxonomy；P2 为真实 py-motmetrics benchmark 标定及 TrackEval/HOTA、Stone
Soup metrics、OSPA/GOSPA 等 optional/offline 对照。D6 仍只读写盘证据，不控制 AirSim，
不参与分配或导引。以下 2026-07-13 及更早章节是历史评审记录。

## 2026-07-13 历史最终统一报告状态

D6 已消费正式 AirSim/main 产物并形成七源统一离线报告，不再处于“等待 main 后续提供真实 AirSim evidence”的阶段。当前各源均为 available，展开行数为 D1 `1`、D2 `3660`、D3 `40`、D4 `60`、D5 per-primary `160`、native MOT `18`、D7 `164`。D7 的 164 条包含 160 条 pair/safety 记录和 4 条 profile 汇总，聚合时不重复计数。

正式结果为：M5N2 最佳 profile coalition `5/10`、全部 profile overall `8/40`；D7 四层分别为 contract `35`、control `7`、mode switch `9`、physical `62`。online truth use、`global_track_id` rewrite 和 reserve unauthorized execution 均为 0。D3 当前只有 case/final aggregate，没有逐时刻 plan history，因此 churn 明确保持 `unavailable`，不得从 version 总数或最终 snapshot 反推。

D6-owned schema adapter、availability、分组、四层分离和中文报告缺口已经闭合，当前回归为 `115 passed`。开放 P1 收敛为三项：长期 multi-seed 趋势、producer 逐时刻 schema（优先 D3 churn）和跨批次失败原因治理。P2 工具继续只作 optional/offline benchmark，不进入默认依赖、默认报告主线或在线控制路径。下文较早批次内容只保留演进记录；冲突时以本节为准。

## 2026-07-13 M5N2 正式写盘 schema 评审补充

统一系统证据报告器此前只识别通用 `summaries/rows/records`，会把 main 的
`cases/pair_rows/aggregates` 原始文件读成 0 个 D5 行，并把修正后的
`d6-cooperative-closure-v2` 指标标为 unavailable。本轮增加两个明确、只读的 schema
adapter，不改变 cooperative producer 或在线控制。

原始路径按显式 case/pair 展开：D3 只统计 active primary 与 reserve 角色，不从无序
plan version 推断 churn；D5 把 visible、由 `d5_decision_state=locked` 生成的
associated、common-lock participation 和 global ID rewrite 分开；D7 只对 active primary
统计四层 funnel，reserve 仅进入越权安全审计，并用 4 个 source aggregate 统计 coalition。
修正 aggregate 路径只恢复其真实保留的 funnel、共同锁定、profile 和安全计数，不构造
丢失的逐 pair 或 seed 数据。

两种路径均复现正式结果：40 case、4 profile、最佳 profile `5/10`、总体 coalition
`8/40`，D7 active-primary 四层为 `35/7/9/62`，reserve unauthorized、global ID rewrite、
online truth use 均为 0。profile 分组键仅为 `profile`，`case_id` 只保留逐行审计，避免再次
出现 40 个单 seed 组。D6 继续被动评估，不写回控制链路，也不导出 truth identity。

## 2026-07-13 P1 统一系统验收补充

本轮将既有专项报告收敛为一个被动统一入口。输入覆盖 D1 frozen dense-crossing、D2 difficulty profile、D3 M5N2 case/final aggregate、D4 episode/fault case、D5 per-primary/native MOT 和 D7 pair guidance/intercept；D6 只读取写盘 JSON/对象，不加载生产者算法，不参与 AirSim 调度。D3 未提供逐时刻 plan history，因此 churn 保持 unavailable。

报告采用三项硬约束：第一，合同允许、控制允许、模式切换和物理拦截是四个独立观测层，禁止逐级推断；第二，所有数值保留 availability，缺字段不补 0；第三，source schema、SHA256、producer/run、provenance 和在线 truth 审计随 CSV/JSON 保留。多 seed 指标使用固定 RNG 的 percentile bootstrap 95% CI，单 seed 只作描述性结果。D1 rejection、D2 admission、D4 fault/ACK、D5 lock/MOT 和 D7 first-failure 统一进入失败原因分布，但不把失败统计回写控制链路。

该能力关闭 D6 的 P1 聚合与报告代码缺口。正式 4 m/2 m replay、M5N2、D4 fault 和 native MOT 产物现已由统一入口消费；后续新批次缺失 evidence 时继续保持 unavailable。

## 2026-07-12 D1/D2 dense-crossing 标定评估补充

D6 新增独立、只读的 dense-crossing 报告路径。输入为 D1 governed manifest、evaluator-only truth summary 和 D2 10-seed/20-seed calibration 文件；输出按 seed 与算法配置保存，不参与在线关联、算法切换或控制授权。

评估口径固定如下：

1. screening 至少 10 seeds，只选择最佳 GNN 参数配置，不产生主线变更。
2. confirmation 至少 20 seeds，分别比较 GNN baseline、相同 config ID 的最佳 GNN candidate 和轻量 JPDA。
3. 历史 `d6-dense-crossing-evaluation/v1` 使用 IDSW 相对下降 30%、identity continuity 绝对增加 0.10、false track 增幅不超过 10%、p95 loop latency 预算和 truth isolation；其中 `+0.10` 已废弃为 D2 v2 判据。当前统一 system-evidence v2 直接消费 D2 ceiling-aware gate，不在 D6 内重算或覆盖 producer 判决。
4. FilterPy/Stone Soup object adapter smoke 没有端到端身份指标，固定排除；轻量 JPDA 标记为 research approximation，不等同于完整 JPDA filter。
5. IDSW、identity/coverage continuity、false track、RMSE、NIS/NEES、初始化延迟、p95 latency 和 truth leak 各自保留 availability。当前 D2 未提供 NIS/NEES mean 时，报告明确 unavailable。

本轮关闭的是 D6 报告和严格 recommendation 逻辑。正式 AirSim 10/20-seed evidence 已由统一入口消费；是否晋级继续只按冻结门限判定，不因报告接线完成而自动晋级算法。

## 2026-07-12 cooperative-closure-v2 实施复核

D6 已新增完全离线的协同闭环报告器。逐 case/seed/profile 明细完整保留，但 acceptance 按 `profile` 聚合唯一 `seed`；分别构造 resource-target pair、target 和稳定 coalition 三种单位。coalition 只包含至少两个 active primary 的目标，并按 `coalition_id` 跨滚动 version/epoch 合并；版本和 epoch 只作审计 provenance。该口径避免把 pair、target 和 coalition 结果互相回填，也避免把普通单 primary 目标或未激活 reserve 当成联盟失败。

D4 通信矩阵按其真实写盘合同读取：report 顶层的 `cases` 是评估行，`seeds` 只是批次索引；case 使用 `scenario_id` 作为故障分组、`passed` 作为 pass evidence，并原样保留 `fail_closed`。这组别名只在 D4 communication adapter 内生效，避免污染通用 cooperative row 的 `passed` 语义。

共同锁定采用 D5/main 的显式 `common_lock` 证据；没有共同时间窗时不根据单机 `associated` 推断。到达离散使用同一 coalition 内 primary 的 arrival error 极差。第二 primary 按 member order/role 排序，只有 physical outcome 可用时才进入失败分母。所有验收结果均标记 `advisory_only=true`，D6 不参与控制。

2026-07-13 真实 M5N2 summary 包含 40 个 case、4 个 profile、每 profile 10 个 seed。修复后的 profile 选择优先读取 source `best_candidate_profile`，缺失时才采用确定性 fallback；source 最佳 `d3-p1-h020.0-w03.0-s040.0` 得到 `5/10`，其余 profile 为 `0/10、2/10、1/10`，全 profile 完成 `8/40`，与 source aggregates 一致。门限检查因此是 available+failed，而不是 insufficient evidence；unavailable seed 单独计数，不折算为 0。

## 2026-07-12 P1 第二批统一报告补充

D6 已新增独立的 P1 summary 聚合入口，直接消费 main terminal closure 和 D1-D5/D7 的版本化离线产物，不要求 D6 导入生产者模块。统一报告固定输出逐 seed/source CSV、聚合 JSON、中文 Markdown 和 PNG 概览图，并显式审计 source schema 与 evidence availability。

报告保持两组不可替代的层级：`contract_allowed/control_allowed/mode_switched/physical_intercept` 四层，以及 pair/target/coalition 三层。锁定、允许控制、模式切换和物理命中之间不做推断；M5N2 的任一 pair 命中也不会被回填成 coalition complete。D7 dropout、`png_ttc` 四类拒绝和 trend coast 晋级判据，D4 failover matrix，以及 D2 IDSW/continuity 已进入统一版式。

该实现关闭 D6 的离线消费与报告缺口，但不改变真实试验结论：没有对应 AirSim 文件时字段仍为 unavailable；合成 D1-D4 replay 只能证明 schema、回归和 fail-closed 逻辑可测，不能替代真实多 seed 物理验收。

复核 `p1_terminal_closure_smoke_v2_20260712` 后，D6 增加 main-summary 专项回退。独立 D7 summary 缺失时，版本化 `acceptance.dropout_matrix` 可直接形成完整性/合规性结论，`png_ttc` 和 candidate trend 只聚合逐行显式计数。该 smoke 的 dropout complete/compliant 均为 true，TTC 仅 not-expanding=1，trend 未触发且不建议晋级。执行四层仍等待 main 写出同名字段，不从 pair、switch 或专项结果推断。

**定位**：D6 建立覆盖探测、跟踪、分配、降级、末端配准、通信、D7 gate/intercept 和安全约束的离线评估体系，支持批量实验统计和报告图表。
**边界**：D6 只消费日志，不参与实时控制，不生成任务、分配、导引、火控、毁伤、自动处置或授权绕过流程。
**规模规则**：指标按实际 `drone_count/resource_count/target_count/camera_count` 归一化，并按 `metric_scope/seed/scenario_group/scale` 分组，不从 `2v2/5v5` 场景名推断规模。
**ID 规则**：D2/D6 必须保留显式 `id_switch_count`。

## 2026-07-11 最终实测同步结论

D6 当前没有运行级 P0 blocker。`p1_p2_validation_20260711` 已给出合同层真实验收：CV 10 seeds 中 8/10 有 T001 双 primary 同帧共识与授权，全部 seed 的 IDSW 和错误重复锁为 0；secondary plan v2 executing 3/3、peer distributed executing 3/3、missing-ACK aborted 2/3 且 D7 allowed=0。D6 重放这些 JSONL 后得到相同结果，未发现 loader 错误。

contract/control/switch/physical 四层口径保持严格分离：CV 10 seeds 的 `control_allowed_count=0`、`physical_intercept_count=None`；SimpleFlight 10 seeds 的物理 evidence 可用，但 30 个 active pair 为 0 命中、24 detection timeout、6 timeout。每 seed 均保持 4 bindings、3 active + 1 standby。本批次只有 15 s、`control_dt=0.5 s`，因此合同层 P1 已闭合，物理拦截和导引律效果仍开放。P2 py-motmetrics IDF1/MOTA/MOTP adapter 已实现，HOTA unavailable。D6 当前回归基线为 `77 passed`。

## 2026-07-10 P1 评估补充

本轮在不参与控制的前提下增加了四条可执行评估链路：

| 链路 | D6 输入 | D6 输出 | 当前状态 |
|---|---|---|---|
| 二级接管生命周期 | readiness/plan state、owner/version/lease、fallback/stale 事件 | 状态驻留、activation latency、fallback/lease/stale count | 代码与单元测试完成，待真实 AirSim 多 seed 写盘 |
| YOLO/MOT | D5 frame event、backend、local track、latency/resource、嵌套 offline truth | recall、local-ID continuity、cross-view rate、latency/budget、truth-field violation | 代码与单元测试完成，D6 不加载 `best.pt` |
| 四导引律 | experiment-level law、稳定场景、相同 seed/规模、D7 execution metrics | same-seed CSV/JSON/中文 Markdown/差值曲线 | 代码与单元测试完成，PNG 核心算法不变 |
| 场景库 | stable scenario group/version、tags、difficulty、expected failure、seeds | scenario library JSON、seed matrix CSV、中文 Markdown | 代码与单元测试完成，CI 接线待 main |

availability 规则：状态、latency、recall、continuity 和资源指标缺真实证据时为 `null/unavailable`；显式记录且实际为零时才输出 0。`offline_truth` 永远只用于 D6 评估，不能回流 D4/D5/D7 在线状态。

### 2026-07-11 四导引律真实短 episode 结果

main 修复 experiment-level guidance law 回灌后，D6 已从
`p1_guidance_four_law_smoke_20260711` 生成同 seed CSV、JSON、中文 Markdown 和差值
曲线。结果表有 21 条指标配对行，但每行只配对 seed 7，不能把指标行数当成独立样本
数。四种导引律在 2 秒窗口内全部 timeout，成功率均为 0；PNG VM/TTC 的末端切换允许
率约 0.762/0.810，最小距离约 2.812/2.798 m。

因此当前结论仅是 D6 的回灌、配对、切换率、拒绝数和最小距离报告链路可用。单 seed、
短窗口无法支持最终命中率、置信区间或导引律优劣结论。P1 下一步由 main/D7 运行较长
窗口的真实多 seed 同条件批次，D6 继续离线报告成功/timeout/abort、距离、切换和门控
原因，不修改任何控制或导引逻辑。

main 写盘合同见 D6 README。尤其需要显式写 `readiness_state`、`plan_state`、plan owner/version/lease、`detection_backend`、`tracker_backend`、cross-view candidate/registered count、pipeline latency、CPU/GPU budget、嵌套 `offline_truth`、`experiment_guidance_law` 和稳定 `scenario_group/scenario_version/seed/actual scale`。

## 1. 研究问题

多目标 C-UAS workflow 不能只报告“成功率”。一个 episode 可能最终接近目标，但仍存在虚警高、漏检、航迹断裂、ID Switch、重复分配、高威胁未分配、中心失效后接管慢、D4 reassign pending、D5 末端误配准、D7 terminal switch reject、通信 stale update 或安全约束触发等问题。

D6 的目标是把 D1-D7 和 main runtime 的离线日志统一为可比较、可复现、可画图的系统级指标。D6 的评估结果服务报告和回归分析，不回写控制。

### 1.1 M 对 N 评估补充（2026-07-11）

完整公式、输入事件、聚合层级、12 组合实验矩阵、指标来源和开源候选见 `D6_M_TO_N_EVALUATION_FRAMEWORK_REVIEW.md`。框架区分合法 coalition multiplicity 与异常 duplicate，并覆盖 target demand/unmet slots、formation/reconfiguration、simultaneous/wave/hybrid、RMSE/NIS/NEES/geometry、canonical duplicate/cross-node IDSW/common-information rejection、planned/authorized/erroneous lock、same-resource continuity、center replan lifecycle、member loss/digest/stale、messages/bytes/rounds/latency 及 minimum separation/collision risk。

聚合固定为 `frame/member/wave/coalition-version/target-episode/episode/batch`，且 `unavailable/null`、真实 `0`、`not_applicable` 三者不可混用。实验采用 independent、simultaneous、sequential、hybrid primary/reserve 四路线，覆盖中心正常、二级接管、完全无中心和几何/同步/通信/成员失效扰动。现有场景无新增 P0；新增合同与聚合列 P1，现有 P2/P3 保持。

实现状态：D6 已新增 `TargetDemandRecord/CoalitionRecord/ArrivalRecord`，扩展 assignment/terminal 合同并接入 JSONL、`EpisodeMetrics`、CSV、batch summary 和 Markdown。通用同帧多资源锁、授权协同锁、错误重复锁与跨帧同资源连续锁已拆分；探测三项由离线 truth pair gate；五类规范 `center_replan_*` 事件已接入请求/去重/解析/pending/convergence 指标。availability 逐指标记录 status/reason/numerator/denominator。剩余 P1 是上游真实日志与 12 组合多 seed 实验，不是 D6 聚合代码缺口。

## 2. 当前实现状态摘要

已实现：

- 数据模型：`EpisodeMetrics`、`TrackRecord`、`TargetDemandRecord`、`CoalitionRecord`、`ArrivalRecord`、`AssignmentRecord`、`EventRecord`、`LinkRecord`、`TerminalRecord`。
- 指标收集：`MetricsCollector`。
- JSONL：标准化 `truth_summary/track/assignment/target_demand/coalition/arrival/event/link/terminal` loader/writer。
- AirSim Blocks：`load_blocks_replay_jsonl()` 读取 `blocks_frames.jsonl` 与可选 `blocks_sensor_observations.jsonl`。
- main bus：`load_main_episode_bus_metrics()` / `load_main_episode_bus_metric_files()` 读取 `main_episode_bus_metrics.json` 与 `main_episode_bus_contract_metrics.json`。
- D4：`load_d4_active_degradation_decisions()` 读取 active-degradation CSV。
- D7：`load_d7_intercept_outputs()`、`load_d7_guidance_timeseries()` 读取 control/guidance/intercept CSV/JSON。
- 报告：episode CSV、summary CSV、Markdown、PNG 图表和批量统计；episode CSV 保留 metadata JSON，Markdown 在存在数据时输出 fixed downlook secondary vs mobile recon gimbal 对比表、D4/D5 detect-to-registration 漏斗和 terminal switch/contract reject reason 分布。
- 标准映射：`cuas-standard-map-v1` 已实现 `COURAGEOUS/MDPI/OCEF -> EpisodeMetrics` 最小映射，输出 `engineering_metric`、`standard_metric_family`、`standard_sources`、`implementation_status`、`evidence_requirement`；episode CSV 和 Markdown 报告保留 `scenario_version`、`standard_mapping_version`、`standard_metric_family_summary`，并可通过 `ReportGenerator.write_standard_mapping_csv()` 输出 `standard_metric_mapping.csv`。
- AirSim calibration：`load_airsim_calibration_records()` 与 `AirSimCalibrationReportGenerator` 读取 D4/D5 stress metrics、AirSim summary 和 main bus metrics，按 `metric_scope/seed/scenario/comparison_role/secondary_height/FOV/secondary_count/detection_backend` 输出 CSV、JSON 和中文 Markdown；P1 二级侦察校准字段覆盖 `secondary_detect_count`、`secondary_visible_target_union_ratio`、`secondary_network_joint_full_view_frame_rate`、`projection_valid_rate`、`geometry_gate_pass_rate`、`registered_candidate_count`、`stable_cross_view_registration_count`、`not_registered_count`，并保留 `scenario_version`、`standard_mapping_version`、`evidence_path`、`trend_key`、`secondary_height_bucket` 和 actual scale 字段。
- main runtime 接入：2026-07-08 起，`--p1-calibration-sweep` 在 batch 结束后自动调用 D6 `AirSimCalibrationReportGenerator.write_report_bundle()`，生成 `d6_airsim_calibration/airsim_calibration_records.csv`、`airsim_calibration_summary.csv`、`airsim_calibration_summary.json` 和 `airsim_calibration_report.md`。D6 不启动 AirSim、不调度 episode、不控制二级节点或终端关联。
- main/orchestrator 2026-07-07 已把 D7 真实执行指标合并进正式 `main_episode_bus_metrics.json`，并把执行前合同检查保留为 `main_episode_bus_contract_metrics.json`；D6 只消费这些写盘结果，不参与控制。
- 2026-07-08 `p1_d4d5_mobile_recon_20260708_055948*` 是历史 mobile recon stress 批次，可保留为 D6 已能消费 `mobile_recon_gimbal`、coverage、bbox、gimbal 和 funnel 字段的旧证据。
- 2026-07-08 registration calibration v2 历史基线为 `research_modules/airsim_runtime/outputs/p1_d4d5_registration_calibration_runtime_v2_20260708*`，D6 bundle 已生成 `airsim_calibration_records.csv`、`airsim_calibration_summary.csv`、`airsim_calibration_summary.json` 和 `airsim_calibration_report.md`；该批次不再表述为当前最新 P1 结论。

部分实现 / 剩余 P1：

- P0：无 P0 blocker；P0-A 标准化评估映射最小版已实现并进入 D6 CSV/Markdown/metadata。
- D7 real execution 的正式/contract 双口径已完成主线；D6 已补 `metric_scope`、main bus metrics JSON loader、reject reason 分布输出和按 seed/scenario/实际规模分组的报告口径。剩余工作是多 seed、5v5/N-v-N 和非默认 episode 持续采用同一双口径。
- D6 已具备 D4/D5/D7/Blocks 离线消费能力，但真实 integrated episode 仍需要 main runtime 在同一 episode 目录写盘、对齐时间轴并调用多个 loader 合并。
- D4 主动降级已能统计次数、secondary takeover/reassignment、pending、窗口 delta、`active_degradation_precision` 和 `unnecessary_active_degradation_count`；必要性/精度只消费真实 episode 写出的 review label 或后验字段，缺 label 不进入 precision 分母。
- D6 已补二级视角/侦察云台指标，能从 main/D4/D5 写盘 metadata 汇总 fixed downlook secondary 与 mobile recon gimbal 的 coverage、cross-view、D5 registration miss、projection/gate/stable registration 和 cue/gimbal pointing error；2026-07-08 历史 registration calibration v2 为 single seed、3 case，height 200 m、FOV 110 deg、secondary_count 3，指标为 `projection_valid_rate=1.0`、`geometry_gate_pass_rate≈0.474`、stable cross-view registration 51/55/53、cross-view association 4/4/5、degradation case `not_registered_count=35/35`、full-view mean≈0.048、best≈0.143、coverage mean≈0.771。
- 2026-07-09 P1 AirSim calibration Markdown 已新增 50m vs 200m 二级覆盖对比、coverage funnel、baseline vs enhanced 表格和 D7 guidance reject reason 表；baseline/enhanced 只消费显式 comparison role，不从 `2v2/5v5` 场景名推断规模或实验组。
- 2026-07-10 已保留旧逐 seed 产物并新增 cross-seed aggregate、严格 baseline/enhanced seed 配对、missing seed、paired delta mean/std、Cohen's dz 和固定 RNG 的 2000 次 bootstrap 95% CI。真实 runtime 的 `scenario_version` 含 seed 参数，D6 统计键现仅移除该运行参数，原值继续留在 records；单 pair 标记 `descriptive_only`，不产生推断 CI/effect size。剩余 P1 聚焦至少两个真实配对 seed、N-v-N 数据和 review labels 验证；D6 继续只消费日志，不参与控制。

- 2v2 回灌专项已复核：`p1_gap_closure_2v2_smoke_20260710/episode_006_full_flow` 的正式 execution main-bus 指标为实际规模 `2/2/2/2`、成功拦截 2、视觉 PNG 切换 3，contract 指标单独保留。Blocks summary 的 legacy integrated snapshot 仍是过时 `3/3/2/0`；D6 loader 不消费该快照，并通过 fixture 测试固定 execution/contract 优先级与 evidence path。上游 summary 对齐由 main 负责。

- 2v2 10-seed 拦截报告专项已完成：AirSim calibration record/CSV/summary/cross-seed 新增 success、collision/range/abort、min range、time-to-intercept、visual PNG switch、terminal switch allowed/takeover 和 gate reject。availability gate 要求 intercept summary/control command/显式 pair-status/D7 execution event 证据，episode_001..005 read-only 默认零因此为 unavailable 且不进入 Outcome 表。对 `seed001..010` summaries 的离线验收仍得到 full-flow execution `18/20=0.9`、collision/range/abort=`18/0/2`；contract 保持独立并由 scope 明示。D6 仍不参与控制。

- D6 owner 2026-07-11 当前回归基线为 `77 passed`。除既有能力外，coalition epoch/lease/member ACK/commit failure 指标、secondary/distributed commit、terminal contract/control/mode/physical 分层指标和 py-motmetrics adapter 已闭合；CV 8/10 与 commit/fail-closed 已提供合同层 evidence，后续 schema 回归必须继续区分 CV physical unavailable 与 SimpleFlight physical=0 available。

未实现：

- Stone Soup metrics、TrackEval、OSPA/GOSPA 和 HOTA 标准输出。py-motmetrics 的 IDF1/MOTA/MOTP 已实现为隔离式 P2 adapter。
- AirSim 原生 recording parser 和 live AirSim replay/API。
- SCRIMMAGE metrics bridge。

## 3. 指标体系

| 类别 | 已实现指标 | 含义 |
|---|---|---|
| 探测 | `detection_probability` | 真值机会中被检测到的比例 |
| 探测 | `false_alarm_rate` | 单位时间虚警数 |
| 探测 | `missed_detection_rate` | 漏检比例 |
| 跟踪 | `track_rmse` | 航迹位置与真值的均方根误差 |
| 跟踪 | `track_continuity` | 真值 timestamp 被匹配覆盖的比例 |
| 跟踪 | `id_switch_count` | 同一 `truth_id` 对应 `global_track_id` 变化次数 |
| 分配 | `duplicate_assignment_count` | 同一 plan snapshot 中多个资源分配到同一目标 |
| 分配 | `unassigned_high_threat_count` | 评估侧高威胁目标未被有效 active assignment 覆盖 |
| 降级 | `failover_time` | 中心失效到降级稳定的平均耗时 |
| 降级 | `consensus_rounds` | 离线记录的协商轮数均值 |
| 降级 | `degraded_completion_rate` | 降级任务完成比例 |
| 降级 | `active_degradation_count` | D4 主动降级决策次数 |
| 降级 | `active_degradation_precision` | 有 review/后验标签的主动降级中必要标签比例 |
| 降级 | `active_degradation_label_count` | precision 的可分类 review-label 分母；为 0 时 precision unavailable/null |
| 降级 | `unnecessary_active_degradation_count` | 有 review/后验标签且判为不必要的主动降级次数 |
| 降级 | `passive_failover_count` | 被动 failover 次数 |
| 降级 | `secondary_node_takeover_count` | 二级节点接管/协助次数 |
| 降级 | `secondary_reassignment_count` | 二级节点重分配次数 |
| 降级 | `d4_reassign_pending_count` | D4 重分配未完成导致的 pending/reject |
| 降级 | `distributed_fallback_count` | 分布式 fallback 次数 |
| 降级 | `failover_active_window_delta_s` | active window 与 failover/takeover 之间的平均 delta |
| 末端 | `terminal_association_accuracy` | D5 末端局部绑定正确率 |
| 末端 | `terminal_id_switch_count` | 同一 `assigned_global_track_id` 下 local visual ID 变化次数 |
| 末端 | `ambiguous_fov_event_count` | 末端视场歧义事件数 |
| 末端 | `friend_overlap_hold_count` | 友方 overlap 导致 hold 的事件数 |
| 末端 | `time_to_terminal_lock` | FOV entry 到 terminal lock 的平均时间 |
| 末端 | `terminal_lock_count` | 唯一 terminal lock 事件/记录数 |
| 末端 | `multi_view_consensus_rate` | 多视角一致成功比例 |
| 末端 | `cross_view_conflict_count` | 跨视角绑定冲突数 |
| 末端 | `duplicate_terminal_lock_count` | 同一目标被多个资源重复锁定次数 |
| 二级视角 | `secondary_network_joint_full_view_frame_rate` | 二级网络联合 full-view frame 比例 |
| 二级视角 | `secondary_network_mean_coverage_ratio` | 二级网络按实际 target count 归一化的平均覆盖比例 |
| 二级视角 | `secondary_visible_target_union_ratio` | 二级网络可见目标并集比例 |
| 二级视角 | `secondary_single_camera_full_view_frame_rate` | 单相机 camera-frame full-view 比例 |
| 二级视角 | `secondary_detect_count` | 二级检测机会计数 |
| 二级视角 | `projection_valid_rate` | GlobalTrack 投影到二级相机图像平面后有效的比例 |
| 二级视角 | `geometry_gate_pass_rate` | D5 几何门控通过比例 |
| 二级视角 | `registered_candidate_count` | 单帧/候选级注册候选计数 |
| 二级视角 | `stable_cross_view_registration_count` | 多帧稳定跨视角注册计数 |
| 二级视角 | `not_registered_count` | 二级检测未注册到既有 global track 的计数 |
| 二级视角 | `cross_view_association_count` | D5/main 写盘的跨视角配准成功计数 |
| 二级视角 | `secondary_detect_available_but_not_registered_count` | 二级检测可用但 D5 未注册计数 |
| 二级视角 | `cue_pointing_error_*` | cue 指向误差 count/mean/rmse/max |
| 二级视角 | `gimbal_pointing_error_*` | 云台指向误差 count/mean/rmse/max |
| 通信 | `cross_node_latency_ms` | 跨节点平均 latency |
| 通信 | `message_drop_rate` | 消息丢弃比例 |
| 通信 | `out_of_order_count` | 显式乱序事件和序列号倒退 |
| 通信 | `stale_track_update_count` | 超过 stale threshold 的 track payload |
| 通信 | `video_metadata_delivery_rate` | video metadata delivery 比例 |
| 通信 | `bbox_delivery_rate` | bbox delivery 比例 |
| 通信 | `consensus_latency_s` | consensus/bid 或 start-to-stable latency |
| D7 gate | `camera_quality_gate_pass_rate` | 相机质量 gate 通过率 |
| D7 gate | `los_quality_gate_pass_rate` | LOS 质量 gate 通过率 |
| D7 gate | `maneuver_margin_gate_pass_rate` | 机动余量 gate 通过率 |
| D7 gate | `terminal_switch_allowed_rate` | D7 允许末端切换的 command 比例 |
| D7 gate | `visual_png_switch_count` | 切换到视觉 PNG/PNG guidance 相关模式的次数 |
| D7 gate | `terminal_takeover_rate` | unique pair 中进入末端接管的比例 |
| D7 gate | `terminal_switch_reject_count` | 末端切换拒绝次数 |
| D7 intercept | `mode_switch_count` | guidance mode switch 次数 |
| D7 intercept | `terminal_contract_reject_count` | terminal contract reject 次数 |
| D7 intercept | `intercept_success_count` | 离线成功状态计数 |
| D7 intercept | `collision_intercept_count` | collision threshold 命中计数 |
| D7 intercept | `range_intercept_count` | range threshold 命中计数 |
| D7 intercept | `time_to_intercept_s` | 达到拦截状态的平均时间 |
| D7 intercept | `min_range_m` | episode/pair 最小距离 |
| D7 intercept | `gate_reject_count` | gate/reject 事件总数 |
| 安全 | `constraint_violation_count` | 安全约束违反次数 |
| 安全 | `human_override_count` | 人工覆盖或拒绝次数 |

## 4. 日志模型

### 4.1 Tracking / Detection

```text
TrackRecord
- timestamp
- global_track_id
- truth_id
- position
- truth_position
- covariance_trace
- track_state
- association_source
```

要求：

- `global_track_id` 由中心/上游维护，D6 不重写。
- `truth_id` 是离线评估标签，不可进入在线 D5/D7 控制判断。
- D1 输出应保留测量时间、到达时间和协方差；D6 通过记录或 link metadata 消费这些信息。

### 4.2 Assignment

```text
AssignmentRecord
- timestamp
- plan_id
- version
- resource_id
- global_track_id
- cost_breakdown
- authorization_state
- active
- truth_id
```

D6 只统计 active 且有效授权状态的分配。stale plan reject 由 D3/main 在线链路负责，D6 可在日志中统计结果但不执行拒绝。

### 4.3 Event

```text
EventRecord
- timestamp
- event_type
- actor_id
- severity
- note
- value
- metadata
```

典型事件：

```text
central_failure
degraded_stable
consensus_rounds
degraded_task_completed
degraded_task_failed
active_degradation_decision
passive_failover
secondary_node_takeover
secondary_reassignment
d4_reassign_pending
distributed_fallback
terminal_lock
terminal_fov_entry
terminal_ambiguous_fov
friend_overlap_hold
multi_view_consensus_result
cross_view_conflict
duplicate_terminal_lock
d7_control_command
d7_guidance_record
d7_intercept_pair_summary
constraint_violation
human_override
```

### 4.4 Link

```text
LinkRecord
- timestamp
- source_node_id
- target_node_id
- relay_node_id
- link_type
- message_type
- sequence_id
- sent_timestamp
- received_timestamp
- measurement_timestamp
- arrival_timestamp
- payload_kind
- delivered
- stale_after_s
- metadata
```

`measurement_timestamp` 和 `arrival_timestamp` 必须保留，用于 stale 和 latency 统计。

### 4.5 Terminal

```text
TerminalRecord
- timestamp
- resource_id
- assigned_global_track_id
- local_track_id
- decision_state
- ambiguity_score
- friend_conflict_state
- assignment_version
- expected_global_track_id
- association_correct
```

D5 不得本地改写 `global_track_id`。D6 只统计末端绑定与中心/评估标签的一致性。

## 5. AirSim / D4 / D5 / D7 接入方案

### 5.1 Blocks replay

已实现 `load_blocks_replay_jsonl()`：

- `blocks_frames.jsonl` 提供 truth objects、resources、cameras、visual detections、image metadata。
- `blocks_sensor_observations.jsonl` 提供 D1 replay observation 和 communication metadata。
- D6 从中构建 truth summary、实际规模字段、visual track、terminal records、video metadata links、bbox links、multi-view consensus/conflict。
- PNG 不必保存；`metadata.images[].path` 只进入 `png_saved` 元数据。

### 5.2 Main bus metrics

已实现 `load_main_episode_bus_metrics()` / `load_main_episode_bus_metric_files()`：

- 读取正式 execution `main_episode_bus_metrics.json` 和 raw contract `main_episode_bus_contract_metrics.json`。
- 把已写盘 `metrics` payload 还原为 `EpisodeMetrics`，保留 `metric_scope`、seed、`scenario_group`、实际规模字段和 metadata。
- 可消费 `terminal_switch_reject_reasons`、`terminal_contract_reject_reasons`、`guidance_law_counts`、D7 intercept/guidance 指标等由 main/D7 合并出的字段。
- 只读文件，不运行 AirSim，不触发 D7 执行，不合并或覆盖控制链路结果。

### 5.3 D4

已实现：

- D4 active-degradation CSV loader。
- 主/被动降级、secondary takeover/reassignment、distributed fallback、D4 reassign pending、触发原因分布。
- `review_label`、`active_degradation_necessary`、`post_window_outcome`、trigger/decision timestamp、selected coordinator、coverage cell 和 pre/post window 字段离线消费。

长期 producer schema 治理：

- 持续写出真实 episode 的 D4 决策日志。
- 在每个 episode 稳定提供 `review_label`、`trigger_timestamp`、`decision_timestamp`、`selected_coordinator`、`coverage_cell`。
- 固定 pre/post 窗口，支持真实数据中的必要性、改善 delta、decision latency、ID switch delta 和 assignment conflict delta。

### 5.4 D5

已实现：

- D6 指标和数据模型可消费 D5 terminal/multi-view 日志。
- Blocks replay 可提供无 PNG 的 bbox/camera metadata 基线。
- 二级视角指标可消费 `secondary_node_type=fixed_downlook_secondary/mobile_recon_gimbal`、coverage/full-view、cross-view association、detect-available/not-registered 和 cue/gimbal pointing error metadata。

长期 producer schema 治理：

- 写出 terminal association、identity claim、terminal-center disagreement、cross-view conflict、duplicate lock、friend overlap hold、validation label。
- 保留 bbox、相机内外参、timestamp、`resource_id/camera_id`、`local_track_id`、`assigned_global_track_id`。
- 为移动侦察云台节点稳定记录几何、FOV、分辨率、cue source、目标覆盖集合/计数、cross-view association 结果、D5 registration 状态和指向误差。
- 2026-07-08 mobile recon stress 已写出 `mobile_recon_gimbal`、`mobile_high_recon`、coverage、bbox、funnel breakpoint 和 gimbal OK 指标，是 D6 消费该类字段的历史证据；同日 registration calibration v2 进一步写出 height 200 m、FOV 110 deg、secondary_count 3、projection/gate/stable registration/not-registered/D7 reject 指标，并由 D6 bundle 汇总。两者均保留为历史基线。

### 5.5 D7

已实现：

- D7 control/guidance/intercept 文件 loader。
- gate pass rate、switch allowed/reject、visual PNG switch、takeover rate、mode switch、contract reject、intercept counts。
- `metadata` 中保留 guidance law、reject reason、D4/D5 state、plan/version。

main/orchestrator 已完成：

- 真实执行后的 `control_commands.csv` 与 `intercept_summary.json` 合并进正式 `main_episode_bus_metrics.json`。
- 执行前合同检查口径保留为 `main_episode_bus_contract_metrics.json`，用于诊断 gate/reject，而不覆盖执行后拦截结果。

长期 producer schema 治理：

- 每个 integrated AirSim episode 稳定写出 D7 文件。
- 在多 seed、5v5/N-v-N 和非默认 episode 中保持正式 metrics 与 raw contract metrics 的双口径，并让 D6 报告继续按 `metric_scope/seed/scenario_group/scale` 分组。

## 6. 开源工具与外部 benchmark

| 工具/接口 | 当前实际状态 | 原因和条件 |
|---|---|---|
| Stone Soup metrics | 未使用 | 需要 Stone Soup 版本锁定、D1/D2 到 `Track/Detection/GroundTruthPath` 的 adapter、坐标/门限合同和 CI fixture |
| TrackEval | 未使用 | 需要 MOTChallenge 格式或等价 frame-level export、IoU/距离门限和依赖容差 |
| py-motmetrics | 已隔离使用 `motmetrics 1.4.0` | `msm-offline-mot-v1` 提供 accumulator 输入；输出 IDF1/MOTA/MOTP，HOTA unavailable |
| OSPA/GOSPA | 未输出字段 | 需要 truth/estimate set 序列、cutoff/order、birth/death/遮挡规则 |
| HOTA | unavailable；py-motmetrics 1.4.0 不支持 | 需要支持 HOTA 的 evaluator、完整帧级检测/关联/身份评估表和遮挡规则 |
| AirSim 原生 recording parser | 未实现 | Blocks JSONL 已满足当前主线；原生 recording 需要样例、schema、坐标和时钟映射 |
| Live AirSim replay/API | 未实现且非 D6 目标 | D6 只读文件；live replay 应由 main runtime 执行并导出日志 |
| SCRIMMAGE metrics | 未实现 | 当前无 SCRIMMAGE 输出样例、message schema、ID 映射和 episode clock 合同 |

这些外部项是 P2/P3 的可选 benchmark 或扩展，不替代当前本地离线指标。

## 7. 批量统计与报告

当前报告生成：

```text
episode_metrics.csv
summary_metrics.csv
standard_metric_mapping.csv
batch_report.md
plots/detection_metrics.png
plots/tracking_metrics.png
plots/assignment_metrics.png
plots/degradation_metrics.png
plots/terminal_metrics.png
plots/secondary_sensing_metrics.png
plots/communication_metrics.png
plots/guidance_metrics.png
plots/safety_metrics.png
plots/selected_metric_distributions.png
```

`episode_metrics.csv` 保留每个 episode 的 metadata JSON、`scenario_version`、`standard_mapping_version` 和 `standard_metric_family_summary`。`standard_metric_mapping.csv` 保留固定版本 `cuas-standard-map-v1` 的本地指标到标准 C-UAS family 映射。`batch_report.md` 在 `EVAL Tracking` 后输出 `Standard C-UAS Mapping` 表，并在存在数据时输出 fixed downlook secondary vs mobile recon gimbal 对比表，以及 terminal switch/contract reject reason 分布，便于对比 execution/contract 双口径下的拒绝原因。

AirSim calibration bundle 额外输出：

```text
airsim_calibration_records.csv
airsim_calibration_summary.csv
airsim_calibration_summary.json
airsim_calibration_report.md
```

该 bundle 保留原逐 seed 分组与文件，并新增 `airsim_calibration_cross_seed_aggregate.csv`、`airsim_calibration_paired_comparison.csv`、`airsim_calibration_aggregate.json`、`airsim_calibration_aggregate_report.md`。配对键包含稳定 `scenario_group`、移除运行 seed 参数后的 `scenario_version`、实际 N/M/camera count、几何、backend 和 seed；case_name 只审计。单 pair 只描述，不输出推断 CI。active-degradation 显式标注优先读取 d4d5 stress metrics，再 fallback main metrics。

统计量：

```text
count
mean
sample_std
stderr
normal-approximation 95% CI
median
p05
p95
```

偏态或长尾指标在正式结论前应补 bootstrap 或非参数 CI；当前实现满足工程回归和批量对比。

## 8. 示例实验报告模板

```text
实验名称：
episode / batch seed：
metric_scope：execution / contract / not_recorded
scenario_group：
实际规模：
- drone_count:
- resource_count:
- target_count:
- camera_count:

数据来源：
- synthetic / Blocks JSONL / D4 CSV / D5 terminal JSONL / D7 CSV+JSON
- 是否保存 PNG:

探测：
- detection_probability:
- false_alarm_rate:
- missed_detection_rate:

跟踪：
- track_rmse:
- track_continuity:
- id_switch_count:

分配：
- duplicate_assignment_count:
- unassigned_high_threat_count:

降级：
- active_degradation_count:
- active_degradation_precision:
- unnecessary_active_degradation_count:
- passive_failover_count:
- secondary_node_takeover_count:
- secondary_reassignment_count:
- d4_reassign_pending_count:
- distributed_fallback_count:
- failover_time:
- consensus_rounds:
- degraded_completion_rate:

末端：
- terminal_association_accuracy:
- terminal_id_switch_count:
- ambiguous_fov_event_count:
- friend_overlap_hold_count:
- terminal_lock_count:
- time_to_terminal_lock:
- multi_view_consensus_rate:
- cross_view_conflict_count:
- duplicate_terminal_lock_count:

二级视角/侦察：
- secondary_network_joint_full_view_frame_rate:
- secondary_network_mean_coverage_ratio:
- secondary_visible_target_union_ratio:
- secondary_single_camera_full_view_frame_rate:
- secondary_detect_count:
- projection_valid_rate:
- geometry_gate_pass_rate:
- registered_candidate_count:
- stable_cross_view_registration_count:
- not_registered_count:
- cross_view_association_count:
- secondary_detect_available_but_not_registered_count:
- cue_pointing_error_mean_deg:
- gimbal_pointing_error_mean_deg:

通信：
- cross_node_latency_ms:
- message_drop_rate:
- out_of_order_count:
- stale_track_update_count:
- video_metadata_delivery_rate:
- bbox_delivery_rate:
- consensus_latency_s:

D7 gate/intercept：
- terminal_switch_allowed_rate:
- visual_png_switch_count:
- terminal_takeover_rate:
- terminal_switch_reject_count:
- mode_switch_count:
- terminal_contract_reject_count:
- intercept_success_count:
- collision_intercept_count:
- range_intercept_count:
- time_to_intercept_s:
- min_range_m:
- gate_reject_count:

安全：
- constraint_violation_count:
- human_override_count:

结论：
- 主要失效模式：
- 长尾风险：
- 需 main/D4/D5/D7 补充的日志：
- 是否需要人工复核：
```

## 9. P1 最终开放项

1. **长期 multi-seed 趋势**：按冻结 scenario/version/profile/actual scale 持续形成跨提交趋势、门限稳定性、paired effect size 和 bootstrap CI；单批次结果不外推为长期结论。
2. **producer 逐时刻 schema**：统一 episode clock、version/epoch、provenance 和 availability，优先补 D3 有序 plan history/churn；缺逐时刻记录时 churn 必须保持 unavailable。
3. **跨批次失败原因治理**：冻结 reason taxonomy 和 schema version，明确 unknown、unavailable、not_applicable 与显式零，避免不同 producer 对同一失败重复计数或名称漂移。

现有 execution/contract 四层、M5N2 profile、native MOT、D4 fault 和 dense-crossing 结果只需继续回归，不再列为首次接入缺口。

## 10. P2 可选离线对照

以下工具不进入默认依赖、默认七源报告主线或在线控制路径，只在 evidence schema 和样本条件满足时单独运行：

1. `msm-offline-mot-v1` 最小 frame-level truth/detection/track schema 已完成；下一步只补真实 replay fixture 与门限版本。
2. py-motmetrics adapter 已完成；使用真实冻结 replay 校准距离门限。TrackEval/HOTA 仍为可选 benchmark，HOTA 不得由现有指标推断或伪造。
3. 接入 Stone Soup 与 OSPA/GOSPA 作为论文级对照。
4. 为长尾指标增加 bootstrap/非参数 CI。
5. 有真实 SCRIMMAGE schema 和样例后再把 SCRIMMAGE bridge 作为 P3 可选项评估。
6. 仅在 Blocks JSONL 不足时增加 AirSim 原生 recording parser。

## 11. 验收命令

```bash
pytest -q research_modules/d6_evaluation_metrics/tests
git diff --check -- research_modules/d6_evaluation_metrics subagent_reviews/D6_*
```

## 12. 参考资料

- Stone Soup metrics: <https://stonesoup.readthedocs.io/en/latest/stonesoup.metricgenerator.tracktotruthmetrics.html>
- Stone Soup OSPA metrics: <https://stonesoup.readthedocs.io/en/latest/stonesoup.metricgenerator.ospametric.html>
- TrackEval: <https://github.com/JonathonLuiten/TrackEval>
- py-motmetrics: <https://github.com/cheind/py-motmetrics>
- AirSim APIs: <https://microsoft.github.io/AirSim/apis/>
- AirSim recording: <https://microsoft.github.io/AirSim/modify_recording_data/>
- SCRIMMAGE: <https://github.com/gtri/scrimmage>

## 13. 2026-07-12 P1 汇总接口评审结论

本轮 D6 以新增 `P1SystemEvidenceReportGenerator` 的方式扩展现有报告体系，未修改旧 `P1AcceptanceReportGenerator` 的字段和验收口径。该接口只读取 producer 已写盘 JSON-like summary，不导入 D2-D5/D7 在线模块，也不控制 AirSim。

评审结论：

1. D5 native MOT admission 已能按 backend、camera、resource 输出 native/fallback、precision/recall、continuity、local IDSW、P95 latency 和拒绝原因。
2. D2 六难度结果按 difficulty profile 和 candidate 保留，IDSW 仍为必须项，non-discriminative 场景不会被隐藏。
3. D3 接口可把普通 plan refresh 与 coalition membership/version/epoch churn 分开统计，per-primary 与 arrival coordination 配置进入证据行；本批正式 aggregate 没有逐时刻 history，因此 churn 仍为 unavailable。
4. D4 按真实 tick 序列统计通信和接管状态，中心失效后的无 owner fail-closed 阶段不会被过滤。
5. D7 的合同允许、控制允许、模式切换和物理拦截为四个独立 availability-aware 指标，不允许相互反推。
6. 汇总输出不包含 raw truth ID；precision/recall/IDSW 只作为离线评估结果消费，显式在线 truth 使用单独报错。

当前 D6-owned 代码缺口已闭合，正式 AirSim 多 seed 产物已经写盘并由 main 调用 D6 统一入口生成报告。剩余 P1 仅为长期趋势、逐时刻 producer schema 和跨批次失败原因治理；D6 不应把接口可用误写成算法通过 admission，也不把缺失时序证据补成 churn。

## 14. Native MOT 专项评审（2026-07-12）

早期专项报告位于 `research_modules/d6_evaluation_metrics/outputs/p1_native_mot_20260712/`；最终七源统一报告已消费正式 native MOT execution index 的 18 条记录。旧专项的 discovery/range/confirmation 分层只作历史过程记录，不替代最终 source manifest 行数。

评审结论：20 m confirmation 的两种原生 MOT 都保持连续、无 IDSW、无 fallback；ByteTrack P95 约 8.292 ms，低于 BoT-SORT 的 18.232 ms。两者离线 precision/recall 分别约 0.324 和 0.293，均未通过准入。30/50 m 短检查无接受检测。当前只能确认 20 m 原生跟踪运行稳定，不能确认检测准确性达标，也不能确认 30/50 m 可用。

D6 报告接口状态为完成；算法准入状态仍为拒绝。下一步先核对离线 truth 框、IoU/几何门限和时间对齐，再由 main/D5 复跑多 seed confirmation。D6 不参与在线检测、跟踪或阈值放宽。

## 15. Main Bus 执行指标合并评审（2026-07-13）

D6 新增 `d6.execution-metrics-merge.v1`。该接口解决历史 integrated replay 与实际 main bus 执行指标分裂的问题，不修改现有 `EpisodeMetrics` 和 loader，也不参与在线控制。

评审结论：

1. replay 继续保留离线评估结果，main bus 只对终端、cross-view、在线 truth、合同/控制/切换和物理执行字段拥有规范优先级，避免扩大覆盖范围到 D1-D3 离线指标。
2. 所有覆盖均可审计：输出同时保存两侧值、availability、source path 和 selected source，历史 replay 值不会丢失。
3. 缺失 execution 时 `execution_metrics_merged=false`，缺失指标为 unavailable，不因 `EpisodeMetrics` 默认字段而制造执行证据。
4. 持久化 11 帧与包含 warmup 的 12 帧按两个字段记录，D6 不假设两者固定相差一帧。
5. main 仍负责调用和写盘；本轮 D6 只提供纯函数、包导出、单元测试和文档合同。

## 16. 三维规模化 D1/D2 公共制品评审（2026-07-20）

本轮新增 `truth_isolated_offline.py`，目标是让 D6 消费 D1/D2 已完成真值隔离的公开离线
结果。评审结论如下：

1. D1 adapter 同时验证 schema、内部 content digest、record count、offline-only truth 声明、
   aggregation provenance 和逐记录内容；以 `d2_lineage_mapping` 为规范输入/输出名，旧
   `canonical_mapping` 仅输入兼容，双字段冲突或可用 truth metrics 缺摘要时拒绝。
2. D2 adapter 不解析逐帧 mapping 来生成新身份，只保留 producer 指标。来源摘要与 record
   sequence、完整四类 expected source hash、在线真值隔离、无身份启发式和正数 frame/
   truth-frame 证据缺一时，IDSW/continuity/duplicate 与 truth counts 全部 fail-closed。
3. `id_switch_count` 在 DTO、CSV、JSON 和 Markdown 中为固定字段。真实零与缺证据空值已经
   由单元测试分开。
4. context 对齐阻止 D1 和 D2 跨 scenario/run/seed/episode 混用。规模按 actual
   target/resource/recon/camera count 分组，不从场景名推断。
5. batch 对不同 seed 统计；单 seed 不输出置信区间。输出包含 D2 confusion/coverage 与 D1
   sensor/range 指标，评估 truth 不进入在线链路。

2026-07-20 专项 `14 passed`、D6 全量 `334 passed`。该结果只支持“D6 公共适配合同已完成”。
main-owned reporting 已调用 episode/batch API；2026-07-23 又完成 nominal 200 对 200 的
20 seed 描述性批量复核。D1/D2 strict 性能仍未闭合。下一步由 main 将已冻结的
manifest/hash 关系和 partial 分栏接入最终统一规模化报告。

## 17. D2 evaluator-only 部分身份诊断评审（2026-07-23）

本轮评审接受 D6 接入
`d2.scalable3d_partial_identity_diagnostics.v1`，但不改变 2026-07-20 冻结的 strict
identity adapter 语义。

评审结论：

1. partial 的 mapping/frame/adjacent-transition coverage 均保留分子、分母、availability 和
   reason；零分母不写 0。
2. conservative IDSW lower bound 与 strict `id_switch_count` 分栏。strict unavailable 时
   lower bound 可独立 available；strict available 时校验 lower bound 不超过 strict。lower bound
   不进入 continuity、promotion 或控制。
3. anchor interval count 和
   `multiple_evaluable_global_tracks_for_truth_frame` 等 exclusion reason 单独报告；重复映射不由
   D6 选择代表航迹。
4. D6 不解析 frame mapping 重算身份。它只验证 producer 汇总的 schema、固定 denominator
   definitions、有限值、计数守恒和 audit/config，再校验 identity manifest 对 evaluation SHA 和
   四类 source hash 的绑定。
5. legacy missing、manifest missing、错版本、hash mismatch、NaN、计数不守恒均只关闭 partial，
   strict 保持原 availability/value。evaluation 文件自身 SHA 篡改仍由顶层 adapter 直接拒绝。
6. DTO、CSV、aggregate JSON 和 Markdown 固定声明
   `strict_id_switch_count_backfilled=false`、`id_switch_upper_bound_reported=false`、
   `control_consumed=false`。

确定性正例使用 10 帧、12 mapping 汇总，得到 mapping/frame/adjacent coverage
`8/10`、`4/10`、`3/5`，4 个 anchor interval、lower bound 2 和 1 个 anchor exclusion。另一
正例保留 strict IDSW 3 与 lower bound 2。该数值只用于合同测试，不是 D2 正式实验结果。
专项 `26 passed`，D6 全量 `567 passed, 1 warning in 22.96s`，验收门限零失败。

真实制品复核使用 clean `4ac3bb2` 的 nominal 200 对 200、seed 1000、10 秒 episode。
manifest/evaluation 文件摘要为 `5b9238fe...e3463`、`b743cd7f...f83a1`；online D1、online D2、
observation truth labels、identity evidence 四项实际文件摘要逐项匹配。输出中在线真值隔离为真，
完整身份指标证据为假；strict IDSW 保持 unavailable。partial mapping/frame/transition coverage
为 `8906/9038`、`3/48`、`0/9400`，IDSW lower bound 为 7/385 anchor intervals。逐 seed CSV、
聚合 JSON 和中文 Markdown 均保持 strict/partial 分栏，未回填 strict、未生成 upper bound。

随后对 clean `5263e2b` 的 nominal 200 对 200、seed `1000-1019` 执行 20 episode 批量复核。
每个 episode 的 D1/D2/D6 manifest 来源与输出摘要均重新计算，producer 制品重建记录与
`episode_record.json` 完全一致。manifest 链、记录一致性和在线真值隔离均为 20/20。
partial mapping/frame/transition micro coverage 为 `178531/181110`、`103/959`、
`1149/187800`，lower bound 在 19 个 episode 可用并合计 199/15215 anchor intervals。
strict IDSW 仍为 0/20 可用，逐 episode 原因为
`multiple_truth_targets_for_global_track`。报告保持不回填 strict、不生成 upper bound。

评审状态更新为“D6 consumer、报告合同和 nominal 200 对 200 的 20 seed 描述性聚合完成”。
剩余 P1 是 main/D2 的正式多规模/困难场景 evaluation、完整 sidecar 下 strict
IDSW/continuity、真实 AirSim coverage 稳定性和最终统一报告。当前 20 seed 结果不能作为
算法晋级或控制证据。

## 2026-07-23 identity commitment evaluation v2 消费评审

### 接受项

1. 接受 D6 对 `d2.scalable3d_identity_evaluation.v1/v2` 的精确版本分流。v1 commitment
   全部 unavailable，v2 必须通过 evaluation/evidence/commitment/audit schema/policy 和
   embedded evidence bundle SHA-256。
2. 接受 `D2IdentityCommitmentEvidenceRecord` 及其 all/observed coverage、committed/
   uncommitted count、uncommitted mapping、blocked reasons、blocker/watermark summary、
   overflow 和两个 binding violation 指标。逐 seed CSV、aggregate JSON 和中文报告均已接入。
3. 接受 D6 复算所有 v2 commitment 聚合，不信任持久化 audit。缺字段、count/coverage 篡改、
   负水位线年龄、overflow 矛盾和未提交 candidate/source binding 均 fail-closed。
4. 接受 strict IDSW、commitment coverage 和 partial diagnostics 三层分栏。D6 不把
   uncommitted gap 当 IDSW=0，不重算 committed anchors，不覆盖 D2 strict 值；普通
   lineage missing 继续使 strict unavailable。
5. 接受 runtime join 的局部不可用语义。assignment window 命中 uncommitted 时保留
   track/frame/reason/policy details、truth 为 null，只关闭该 binding；其他合法 binding 和
   episode 继续处理。v2 audit/SHA 篡改仍全局拒绝。

### 验证与状态

确定性 3-record fixture 得到 all committed/uncommitted `2/1`、coverage `2/3`，observed
`2/0`、coverage `1.0`，blocker sum/mean/max `2/0.666667/2`，watermark age `0.5 s`，
overflow record/track `1/1`，binding violation `0/0`；D2 strict IDSW `1` 原样消费。
runtime 2-window fixture 验证第一个 binding 局部 unavailable、第二个 available。

专项结果为 truth-isolated `39 passed`、runtime join `31 passed`；D6 全量
`598 passed, 1 warning in 21.44s`，验收门限零失败。warning 为既有 Matplotlib 环境提示。

评审结论为“D6-owned v2 consumer、聚合、报告与 runtime 局部不可用合同完成”。

### clean seed 1100 A/B 复核

main 随后在 clean commit `909669b2eefeab2ce30c8ac389d6bf9c0a8cbabc` 完成 nominal
200 对 200、2 个侦察节点、2.2 秒的 seed 1100 A/B，并实际持久化 v2
evidence/evaluation/audit/manifest。baseline strict IDSW、track continuity、coverage
continuity 和 commitment coverage 为 `9/0.865/0.870/1.0`，D2/D3 数量为 `203/200`。

candidate commitment coverage 为 `1714/1787=0.9591494124`，1714 条 committed、69 条
ambiguity hold、4 条 after hold。source/candidate binding violation 为 `0/0`，online truth
isolation 为 true。这三项接受为真实 episode 证据。

candidate 的 `GT3D-000185/186/202` 在 `2.1308153039 s` 评分帧只携带
`measurement_timestamp=1.2 s` 的恢复来源，差值 `0.9308153039 s` 超过固定 `0.9 s`
window。strict identity metrics 因
`source_observation_outside_lineage_window` unavailable，D6 不扩大窗口、不回填 strict
IDSW。candidate D2/D3 数量为 `201/197`。评审拒绝候选准入并停止 seed 1101/1102。

当前关闭的是 main v2 原子持久化和 D6 真实 episode 消费子项。结构歧义候选的 promotion
gate 仍开放且本次判定为失败。该实验不是 AirSim，真实 AirSim 与多 seed 证据仍开放。

## 2026-07-23 发布新鲜度候选与 D6 分类绑定复审

main 在 clean commit `65568579c99e4ef9939f0519f66c46d3076ef035` 重跑 seed 1100 后，
D6 对 baseline/candidate 的 summary、offline identity、truth-isolated episode record 和
manifest 做了独立复核。episode ID 与 SHA 来源链一致，在线真值使用为 0。

评审接受：

1. 新 publication-stale reason 的消费正确。candidate 有 3 条超龄恢复继续
   uncommitted，commitment state 为 `1711 committed + 69 hold + 7 after hold`，两个
   binding violation 为 0。
2. strict availability 已恢复。baseline/candidate 的 IDSW 为 `9/3`，track continuity 为
   `0.865/0.8266667`，coverage continuity 为 `0.870/0.8283333`。
3. D6 partial adapter 的原 mismatch 不是预期可选诊断缺失。根因是 consumer 比较了不同
   分区的同名计数。修复后的守恒关系为
   `partial unavailable = audit unavailable + excluded + uncommitted`，并继续要求全分类覆盖
   total。
4. 修复后两组 partial manifest/provenance 均通过，lower bound 为 `9/3`。strict 与 partial
   仍分栏，lower bound 不回填 strict、不进入控制。
5. 新增两项正负回归；D6 全量 `600 passed, 1 warning in 21.55s`，零失败。

评审不接受结构歧义候选晋级。D2/D3 数量由 `203/200` 降至 `201/197`，track continuity 和
coverage continuity 分别下降 `0.0383333`、`0.0416667`。IDSW 下降不能抵消可用性与连续性
退化。候选保持默认关闭，seeds 1101/1102 不执行。

当前制品只持久化了新阻断行为，没有 `identity_commitment_recovery_config` 完整配置快照。
该轮将配置 schema/version、enabled 和 `0.9 s` 预算的独立 provenance 列为跨模块 P1；
consumer 的后续关闭状态见下一节。原 A/B 目录中的旧 D6 partial mismatch 是修复前派生结果；
main 集成后应生成新的 D6 bundle，保留原 producer 制品不变。

## 2026-07-23 Manifest v2 配置谱系复审

D6 已完成上一节开放的 consumer 子项。新增配置谱系记录独立验证 manifest v2 中的完整
recovery config，并读取 online D2 JSONL 复核每条发布。验证范围包括配置 schema、规范
SHA-256、manifest schema/SHA、evaluation/manifest/调用方文件摘要、配置记录数、
`d2_record_count`、consistency 和 source 声明。

评审接受：

1. manifest v1 继续保留 strict/partial 指标，配置谱系以
   `identity_recovery_config_not_manifest_bound_v1` 显式不可用；
2. manifest v2 正例在 episode JSON、逐 seed CSV、batch provenance 和 runtime admission
   中完整暴露；
3. 配置 SHA 篡改、内容篡改、帧间漂移、缺字段和记录数不符均有稳定失败关闭测试；
4. runtime join 对 v2 错误拒绝整个联接，离线 adapter 只关闭新增谱系字段；
5. 全部路径保持在线真值隔离和 `strict_id_switch_count_backfilled=false`。

专项为 `83 passed`，D6 全量为 `611 passed, 1 warning in 21.55s`，零失败。warning 是既有
Matplotlib 环境提示。真实 main 三维质点 3 对 3、seed 70、1.2 秒用例生成 manifest v2 和
3 条 D2 发布，逐条谱系验证通过。评审关闭 D6 配置谱系 consumer P1。

上述合同测试阶段尚未形成最终 A/B 证据。main 随后在 detached clean
`ff881316243ff5a2991a4659ab78637ed625d123` 上完成同一 seed 1100 baseline/candidate
重跑。两组均为 nominal 200 对 200、2 个侦察节点、2.2 秒三维质点 episode，场景 SHA 为
`34f5563579d9d2e7d1ea2b57cf353d2465b3bd16c5310570d40e72fc7aeac461`。

最终评审接受：

1. 两组 identity manifest 均为 v2，完整 recovery config 规范 SHA 均为
   `sha256:bd8e362ec4ca128ed902826750b26d862286770d3c0c4d0b75960a50911a201a`，
   配置记录数与 D2 记录数均为 9。
2. D6 episode 和 runtime outcome join 均验证 manifest SHA、在线 D2 JSONL SHA、逐条配置、
   consistency/source 和记录数，provenance 均为 verified。
3. baseline/candidate strict IDSW 为 `9/3`，partial lower bound 为 `9/3`，partial
   unavailable mappings 为 `234/296`，严格指标未回填。
4. candidate 的 3 条 stale recovery 正确失败关闭，两类 binding violation 为 `0/0`，
   在线真值使用为 `0/0`。

评审关闭配置谱系 P1。结构歧义保活候选仍不准入：D2 航迹 `203 -> 201`、D3 分配
`200 -> 197`、track continuity `0.865 -> 0.8266667`、coverage continuity
`0.870 -> 0.8283333`。候选保持默认关闭，不运行 seeds 1101/1102、10 秒或 20-seed
矩阵。该证据不是 AirSim；AirSim、多规模、困难谱系和长时性能项继续开放。

## 2026-07-23 identity commitment execution gate 独立评审

D6 复核提交 `7e15dac9cdaf6743999dfe045a70676fd31a17d6` 的 hold-only 与
hold-plus-centroid。两组均为 clean nominal 200 对 200、2 个侦察节点、2.2 秒、seed
1100。场景配置、离线真值状态和离线观测真值标签逐字节相同，runtime profile 只差质心候选
开关。

评审接受：

1. 两臂 strict IDSW、track continuity、coverage continuity 均为
   `3/0.8266666667/0.8283333333`。mapping `1491 available + 218 unavailable +
   76 uncommitted + 2 excluded` 与 1787 条承诺记录守恒；coverage
   `1711/1787=0.9574706212`。
2. duplicate assignment、online truth use、uncommitted source/candidate binding
   violation 均为 0。identity manifest v2 的配置、9 条 D2 发布和来源 SHA 均验证通过。
3. `t=1.0 s` 时 D3 对 11 个未承诺旧绑定执行 `v1 -> v2` 强制升版并绕过迟滞。版本 2、
   版本 3、D5 主动视觉/终端绑定、D7 导引和 runtime control 对该集合的继续执行为 0。
4. 当前 D6 代码重建 truth-isolated episode 后与原 record 完全一致，4 个派生文件逐字节
   相同。runtime outcome 重建 JSON 同样逐字节一致，audit violation 为 0。
5. 候选组 46 个质心候选全部失败关闭，`oosm_scan=30`、
   `unbalanced_component=16`，实际应用为 0。

评审不接受算法收益或晋级结论。两臂没有有效 treatment，指标相同不能解释为质心修正
“无影响”或“非劣”。本轮只关闭 clean 单 seed 安全合同证据。需要先形成至少一个合法应用，
再进入多 seed、长时、困难谱系和 AirSim 评估。

D6 后续补充两项自动化：把 D3/D5/D7 未承诺继续执行计数写入标准派生制品；在统一 scalable
3D 报告中显式联接 truth-isolated strict identity，同时保留在线 summary availability。
完整专项报告见
`research_modules/d6_evaluation_metrics/docs/IDENTITY_GATE_CLEAN_SEED_1100_AUDIT_CN.md`。

## 2026-07-25 正式 R0 后验跳过评审

评审读取 `2c7b425d...` 的 900 个 R0 episode。scope manifest 的 900/900 完成、分片哈希和
`formal_scope_complete=true` 可以接受。D6 episode 证据只能接受 895/900 clean-formal。

其余 5 项声明的 finalization skip 不是合法 no-op。D1 最终后验相对 D2 最后消费后验存在
非零状态、协方差和有效时刻差。main 的 D2 输入签名没有覆盖这些字段。仅把 skip 加入代次
计数会掩盖未消费后验，评审不接受该做法。

D6 v10 已收紧为逐轨完整公开后验比较，并输出最大差值。公开字段相等仍需版本化完整 D2
输入摘要；摘要缺失时继续失败关闭。5 项当前均有内容差异。评审将根因列为
main 运行时 P0。D6 v10 已提交为 `8e955f3`，main 修复已形成 clean source commit
`98d01bf`。旧正式目录保持只读，不能用新评估器或新 episode 原地覆盖。

评审回归为 D6 全量 `894 passed, 1 warning in 85.66s`。五个原始 episode 的 v10 逐条复核
均保留最终代次未消费、公开完整后验不等价和未验证处置守恒原因。

### 修复后评审

main 在 `/tmp/msm-r0-finalize-fix-20260725` 重跑原 5 个异常 cell。D6 v10 的
`combined_d6` 结果确认五项均满足最终代次一致、消费与发布一致、消费加节拍前合并等于 D1
代次、skip 为 0、pending 为空，generation contract 状态均为 `verified`。因此原 runtime
错误跳过现象已在定向开发回归中消失。

五个 episode 均来自 dirty 工作树。D6 将其全部归入
`descriptive_or_incomplete_evidence`，正式验收资格为 0/5，失败原因只剩 dirty/non-clean
provenance。评审接受该结果作为修复确认，不接受把它与旧 clean 提交的 895 项拼接，也不接受
据此声明 R0 900/900 formal acceptance。

完整 R0 formal rerun 已在 clean source `1e5ed8d` 上启动，当前完成 135/900。D6 继续保持
旧正式结论 895/900，并在新批次中使用 v10 逐项核对 generation contract、clean provenance
和实验矩阵门。任何 `skip=1` 若没有版本化完整 D2 输入摘要，仍须失败关闭；本次 `skip=0`
的结果不能作为放宽先例。

### 2026-07-25 增量正式评审

评审核对 execution plan SHA-256
`8804ecb4dd0513db55906905f031832711012974fc911546df40e09fb297d373`。shard 0、5、9
checkpoint 均为 complete，各 45/45。`targeted_formal_d6` 中三个原失败 cell 为：

1. delayed_noisy 5v5 seed 1000；
2. delayed_noisy 5v5 seed 1005；
3. delayed_noisy 20v20 seed 1009。

三项均为 clean-formal，基础与矩阵 formal eligibility 为 true，generation contract 为
verified，integrity 为 true，episode/matrix/variant failure reasons 全为空；D1 final 与
D2 consumed 一致，skip 为 0，pending 为空。评审接受这三个 cell 的新批次正式准入。

评审不接受 898/900、135/135 或 900/900 的组合声明。旧 895/900 属于旧 source 的整体结论；
新 source 当前只有 135/900 执行完成，D6 定向报告只覆盖其中三项。5v5 seed 1008/1018 和
其余 765 个 cell 保持开放。磁盘可用空间仅比 20 GiB 下限多约 64 MB，main 应先处理运行空间，
再继续同一 source、同一 plan 的剩余分片。

## 2026-07-26 学习作用域正式证据审计评审

评审接受 D6 新增的可选只读审计接口。接口要求 main 显式提供学习 execution plan、完整
scope merge、R0 对照和实际 bundle 根目录。它复核计划、分片、cell、episode、模型绑定、
设备、版本、诊断和在线真值隔离，不读取控制器内部状态，也不改变默认规则路径。

评审采用以下硬门：

1. `requested_mode` 和 `effective_mode` 都必须为 `assist`，bundle 已加载且无 fallback。
2. D3/D4/D5 各自必须存在正的实际采用证据。D5 图模型还要求
   `loaded_edge_model + model_scored + fallback_count=0`，并要求候选边计数 available 且
   大于 0；D5 主动视觉同时要求选择计数和 runtime ACK 应用计数为正。
3. shadow、fallback、仅加载 bundle 和 applied count 为 0 全部不算 adoption。
4. 每个学习 cell 必须有唯一同 `comparison_key` R0，且父计划、来源提交、外生配置和传感器
   随机计划一致。
5. `intercepted_target_count` 与 `offline_proximity_unique_target_count` 两侧均可用且
   学习侧不低于 R0，才可给出必选指标非退化。缺值保持 unavailable。
6. scope merge 不完整、episode 物理结果缺失、在线真值非零或任何哈希不一致均失败关闭。

主审补充后的定向测试为 `36 passed, 1 warning in 2.35s`，D6 全量回归为
`930 passed, 1 warning in 78.98s`。29 个新增负例对计划和持久化制品篡改、重复/错配 R0、
三个单组件空采用、C1/F1 必要组件缺失和 D5 零候选边作直接断言。缺 R0 或 lineage 不可比时
`non_degraded=None`。评审不接受把该合同测试写成 d59352b 的正式性能证据。main 实物输入
尚未提供，当前不形成学习准入或模型晋级结论。
