# 三维规模化仿真版本管理

## 分支

```text
main
└── feat/scalable-3d-200v200
```

- `main` 保留已验证的 2v2、5v5、M5N2 和 AirSim 基线。
- `feat/scalable-3d-200v200` 承载三维环境、D1-D7 扩展、图神经网络和强化学习集成。
- D1-D7 默认不分别创建长期分支。各模块所有者只修改自身目录，main 审查后分批提交。
- PyTorch Geometric 等高风险依赖实验可使用 `exp/<topic>` 短期分支。验证结束后合并有效部分，随后删除实验分支。
- 专项分支推送并进入协作后不改写历史，不使用强制推送。同步 `main` 使用普通合并。

## 提交

提交按可独立审查和回归的能力分组：

1. `plan: define scalable 3D contracts`
2. `feat(sim): add vectorized 3D world`
3. `feat(d1-d2): support dense 3D tracking`
4. `feat(d7): close 3D guidance loop`
5. `feat(d5): add sparse graph association`
6. `feat(d3): add RL-assisted assignment`
7. `feat(d4): add regional fallback coordination`
8. `feat(d6): add large-scale evaluation`
9. `feat(integration): connect 200v200 episode bus`
10. `docs: synchronize plans, gaps and reports`

子智能体不操作共享 Git 索引。main 检查模块测试和文档同步后统一暂存、提交和推送。

## 数据合同

代码提交号不能单独说明实验条件。每个 episode 必须同时记录以下版本：

| 项目 | 当前格式 | 变更条件 |
| --- | --- | --- |
| 世界模型 | `scalable3d-world-v1` | 状态语义、坐标或动力学改变 |
| 总线合同 | `scalable3d-episode-bus-v1` | 跨模块消息出现不兼容变更 |
| 场景配置 | `scalable3d-scenario-v1` | 配置字段语义或默认场景改变 |
| 集成运行配置 | `scalable3d-integrated-stack-runtime-profile-v1` | main 运行时 treatment、D1-D7 适配器开关或调度参数改变 |
| 阶段耗时 | `scalable3d-stage-timings-v2` | 阶段调用计数、总耗时、均值、P50/P95/max 或 availability 语义改变 |
| 长时对照 | `scalable3d-long-duration-comparison-v2` | 长短 episode 可比条件、耗时增长或证据等级语义改变 |
| 在线观测 | `scalable3d-observation-v1` | 观测字段、单位或时序语义改变 |
| 离线真值 | `scalable3d-offline-truth-v1` | 标签结构或评分口径改变 |
| 学习导出 | `scalable3d-learning-export-v2` | D3/D4/D5 训练制品布局或真值隔离规则改变；v2 增加 D5 主动视觉整 episode 在线记录与独立离线标签 |
| 学习生成计划 | `scalable3d-learning-generation-plan-v1` | 场景、规模、seed、正式预检或保留评估 seed 规则改变 |
| 学习生成检查点 | `scalable3d-learning-generation-checkpoint-v2` | 暂停/恢复状态、累计调用计时、计划哈希或完成序号语义改变；v2 在每个完整 episode 后原子推进，并记录严格校验后的旧检查点滞后恢复 |
| 训练 seed 注册表 | `scalable3d-training-seed-registry-v1` | 训练/保留评估 seed 身份、来源或隔离规则改变 |
| 共享 seed 切分注册表 | `scalable3d-shared-seed-split-registry-v1` | D3/D4/D5 联合训练的数值 seed 分桶、比例、来源哈希或保留集规则改变 |
| 实验矩阵 | `scalable3d-experiment-matrix-v1` | 变体语义、配对键或正式准入条件改变 |
| D1 一致性评估清单 | `scalable3d-offline-consistency-evaluation-manifest-v1` | 在线证据、真值状态、D2 映射或哈希绑定改变 |
| D1 扫描输入审计 | `d1.scan_input.audit_summary.v1` | 水位线、扫描拒绝、缓冲容量或结束排空语义改变 |
| D1 发布元数据实现 | `per_track_copy_v1` / `immutable_shared_v2` | 共享审计树的复制、不可变共享或实现身份语义改变；`immutable_shared_v1` 仅保留为历史证据标签 |
| D1 发布审计树合同 | `d1.publication_audit_tree.v2` | 精确容器类型、叶节点集合、冻结方式、循环/重复键/非有限值拒绝或序列化边界改变 |
| main/D2 发布元数据审计 | `scalable3d-d2-publication-metadata-audit-v1` | batch/latest/totals、D2 内容审计、内置等价复用、v2 合同验证或身份复用计数语义改变 |
| D6 发布元数据 v2 准入 | `d6.d1_publication_metadata_v2_multiseed_evaluation.v1` | v2 evidence 绑定、D2 审计归一化边界、D1/D2/核心墙钟/RSS 门或准入结论语义改变 |
| D1 常速度模型构造实现 | `per_prediction_build_v1` / `bounded_exact_lru_v1` | 状态转移和过程噪声矩阵的逐次构造或精确有界缓存语义改变 |
| D1 常速度模型缓存诊断 | `d1.cv_motion_model_cache_diagnostics.v1` | 实现 ID、容量、条目数、预测请求、构造、命中、未命中或淘汰计数语义改变 |
| D1 常速度模型缓存矩阵 | `scalable3d-d1-cv-motion-model-cache-multiseed-matrix-v1` | 实验臂、seed、时长、容量、准入门或证据边界改变 |
| D1 常速度模型缓存证据 | `scalable3d-d1-cv-motion-model-cache-multiseed-evidence-v1` | clean source、episode/resource 路径、arm 状态或 D6 evaluator 绑定改变 |
| D6 常速度模型缓存准入 | `d6.d1_cv_motion_model_cache_multiseed_evaluation.v1` | 业务归一化边界、缓存守恒、D1/D2/核心墙钟/RSS 门或准入结论语义改变 |
| D1 结构歧义证据 | `d1.structural-ambiguity-evidence.v1` | 允许边分量、成员不透明令牌、双时间戳、状态/协方差或候选边语义改变 |
| D2 身份评估清单 | `scalable3d-offline-identity-evaluation-manifest-v2` | v2 在原来源哈希外绑定逐发布一致的身份恢复配置快照、配置 SHA-256、记录数和来源路径；谱系映射、身份指标、恢复配置或来源校验改变时升级 |
| D2 观测证据治理 | `d2-observation-evidence-governance-v1` | D1 观测新鲜度、重放隔离、时间冲突、暂定航迹删除或重复合并审计语义改变 |
| D2 观测声明账本 | `d2-observation-claim-ledger-v2` | 声明键、水位线、安全淘汰、容量或反重放语义改变 |
| D2 结构歧义保活策略 | `d2.ambiguity-hold-lease-policy.v1` | 租约时钟、年龄门限、软/硬截止、证据保留或失败关闭语义改变 |
| D2 身份承诺 | `d2.identity-evidence-commitment.v2` | 承诺状态、恢复水位、阻断键、来源绑定或失败关闭语义改变 |
| D3 身份承诺准入 | `d3_identity_commitment_admission_v1` | committed 集合、拒绝状态、旧绑定撤销、强制重规划或审计字段语义改变 |
| main 身份承诺下游审计 | `scalable3d-identity-commitment-gate-audit-v1` | clean 配对条件、D3 强制升版、D5/D7 继续执行检查或算法晋级判定语义改变 |
| D2 离线身份证据 | `d2.scalable3d_identity_evidence.v2` | 未承诺间隙、来源谱系、D1/D2 序号或承诺快照语义改变 |
| D2 离线身份评估 | `d2.scalable3d_identity_evaluation.v2` | 承诺覆盖、ID Switch 锚点、未承诺状态或严格指标 availability 语义改变 |
| D2 身份承诺审计 | `d2.scalable3d_identity_commitment_audit.v2` | 恢复原因、水位年龄、overflow 或绑定违规统计语义改变 |
| main 观测治理快照（历史） | `scalable3d-observation-governance-runtime-v1` | D1/D2 在线治理汇总或结束排空计数语义改变 |
| main 观测治理快照（当前） | `scalable3d-observation-governance-runtime-v2` | v2 增加 D1 后验代次、D2 待处理/已消费代次、消费次数和节拍前合并计数；这些字段或 finalize 排空语义改变时升级 |
| D6 观测治理标定输入 | `scalable3d-observation-governance-calibration-input-v1` | episode 描述、制品哈希、在线审计或 evaluator-only 侧车绑定改变 |
| D6 真值隔离清单 | `scalable3d-d6-truth-isolated-manifest-v1` | D1/D2 适配、availability 或批量聚合口径改变 |
| D6 跨模块学习准入 | `d6.cross-module-learning-data-admission.v1` | 正式/补充/离线标签/运行 ACK 分层、canonical view 绑定、动作覆盖或训练准入矩阵语义改变 |
| 跨构建语义等价审计 | `scalable3d-cross-build-semantic-equivalence-v1` | clean build 可比条件、D3 不透明计划谱系映射、D4 内容地址重算、ACK 来源哈希、真值制品或逐主题规范哈希语义改变 |
| 保留 seed 隔离干预 | `scalable3d-reserved-seed-interventions-v2` | v2 绑定 D3 二元/连续分布门语义，并在 manifest/report 中持久化 D4 v2 分门诊断；历史 `6d5bfea` 正式证据保持 v1 |
| 共同检查点隔离物理续跑 | `scalable3d-checkpoint-paired-physical-rollout-v2` | v2 在顶层清单持久化唯一源提交、源提交集合、提交一致性、源 episode 数、脏源计数和逐 seed 源清单 SHA-256；v1 不具备自证 clean-tree 来源的字段 |
| D6 保留 seed 可用性审计 | `d6.reserved-seed-intervention-outcome-availability.v2` | v2 严格绑定源 schema/commit/摘要，区分同帧 assignment comparison 与 runtime/physical/counterfactual/causal availability；历史 v1 保持只读 |
| D5 补充主动视觉全样本审计 | `d5.active-vision-supplemental-bc-full-sample-audit.v1` | 文件清单、逐样本特征、身份/版本、离线标签和权限门控语义改变 |
| D5 模型 | `d5-crossview-gnn-v0.1.0` | 网络、特征、权重或训练集改变 |
| D5 主动视觉 | `d5-active-vision-rule-v1` 或模型语义版本加指纹 | 特征、动作空间、权重或准入报告改变 |
| D5 主动视觉数据 | `d5.active-vision-episode-dataset.v3` | split、episode、在线/离线标签、运行时 ACK 或哈希语义改变 |
| D5 主动视觉 bundle | `d5.active-vision-model-bundle.v5` | 模型、特征、数据集 schema、准备度证据绑定或权重改变 |
| D5 规范种子视图 | `d5.canonical-seed-split-view.v1` | 消费者、源数据/注册表绑定、完整 episode 重分桶或内容哈希语义改变 |
| D5 规范视图准备度 | `d5.canonical-seed-readiness.v1` | 数据准入门、证据可用性或失败关闭结论字段改变 |
| D3 策略 | `d3-rl-cost-policy-v0.1.0` | 策略结构、权重或动作定义改变 |
| D4 区域策略 | `d4-region-resource-rule-v1` 或模型版本加权重 SHA 前缀 | 区域特征、动作、安全投影或权重改变 |
| 阈值配置 | `scalable3d-thresholds-v1` | 门限和回退条件改变 |
| 分配计划 | 递增 `plan_version` | 每次发布新计划 |
| 联盟状态 | `epoch + lease + version` | 所有权、成员或有效期改变 |

兼容性新增字段可保留当前主版本。不兼容的字段删除、单位变化、坐标语义变化或行为变化必须升级主版本。模型和策略采用语义化版本号。

`scalable3d-episode-bus-v1` 的 D1 航迹发布现允许两种兼容记录：`full_posterior` 携带完整
`tracks`，`state_update` 只携带扫描摘要、观测谱系和 `current_track_count`。两类记录都保持
`track_count == len(tracks)`；需要完整快照的 consumer 必须检查 `tracks_materialized`，不能
把 state update 的空数组解释为当前航迹库存归零。该新增不删除旧字段，因此保持总线 v1；
后续若改变 `track_count` 语义或取消完整快照，则必须升级总线主版本。

结构歧义侧车是 D1 发布物中的兼容新增字段，消费者必须按 schema 显式选择是否处理。
main 只有在 `d1_d2_structural_ambiguity_hold_enabled=true` 时才把侧车送入 D2，并同时
启用不透明 D1 来源令牌；该开关及租约参数全部进入 runtime profile。默认关闭与实验开启
具有不同的 runtime profile SHA-256 和 episode ID，不能按跨构建语义等价样本合并。当前
seed 1100 门槛已经拒绝该候选，schema 和测试保留不表示在线主线准入。

启用结构歧义保活的当前 D2 发布物同时携带身份承诺 v2。未承诺状态不得携带
`source_observations`，main 也不得为其回填 D1 谱系。普通已承诺航迹仍可消费待处理 D1
来源；经历歧义恢复的航迹只能发布本次被接受量测的精确来源。离线 producer 不能在同一
episode 混用 v1/v2 身份证据，D6 必须按证据 schema 选择相同版本的评估和审计路径。

离线身份清单 v2 要求每条 D2 发布都携带
`payload.association.identity_commitment.recovery_config`。同一 episode 的快照必须完全
一致；缺失、非规范 JSON 或帧间漂移直接失败关闭。清单保存规范快照、SHA-256、记录数和
固定来源路径。D6 对清单文件、在线 D2 JSONL 哈希和逐条快照独立复核，并在 episode、
batch 和 runtime provenance 中暴露结果。历史 v1 清单可继续读取严格和部分身份指标，但
恢复配置谱系必须标记为 unavailable，不能补算。

D3 的身份承诺准入不允许兼容性缺省。scalable 3D main 必须从同一 D2 发布按
`global_track_id` 提供完整承诺集合；集合缺失、键不一致、状态未知或非 committed 时，
对应目标不得进入新计划、D5 主动视觉和 D7 导引。现有 binding 被撤销时必须先 hold，
再发布严格更新的计划版本。AirSim 经典 D2 的兼容桥只能在 main-owned 可信跟踪器边界生成
逐航迹显式 `committed` 清单，且清单必须精确覆盖本帧适配航迹；普通适配器调用没有清单时
保持 `identity_commitment_missing`。后续经典 D2 一旦支持歧义承诺，必须改为消费实际侧车，
不能继续无条件生成 committed。

身份中性质心校正是默认关闭的 D1 实验行为，不改变
`d1.structural-ambiguity-evidence.v1` 的外部字段。main 必须把
`d1_publish_opaque_source_key`、`d1_d2_structural_ambiguity_hold_enabled` 和
`d1_identity_neutral_centroid_correction_enabled` 全部写入 runtime profile；
不同组合必须生成不同 profile SHA-256 和 episode ID。质心候选的帧替换语义、门限、
代际水位或协方差膨胀规则发生改变时，即使外部侧车 schema 不变，也必须形成新的
runtime profile，不得与既有实验结果合并。2026-07-23 的 dirty seed 1100 开发门槛中
候选实际施加数为 0，因此不能作为 schema 或策略晋级证据。

## 实验清单

每个输出目录必须包含 `manifest.json`，至少记录：

```json
{
  "git_commit": "<commit>",
  "repository_dirty": false,
  "config_sha256": "<sha256>",
  "runtime_profile_schema": "scalable3d-integrated-stack-runtime-profile-v1",
  "runtime_profile_sha256": "<sha256>",
  "scenario_version": "200v200-nominal-v1",
  "seed": 17,
  "world_schema": "scalable3d-world-v1",
  "bus_schema": "scalable3d-episode-bus-v1",
  "d5_model_version": "d5-crossview-gnn-v0.1.0",
  "d3_policy_version": "d3-rl-cost-policy-v0.1.0",
  "d4_policy_version": "d4-region-resource-rule-v1",
  "threshold_version": "scalable3d-thresholds-v1"
}
```

`config_sha256` 只绑定外生场景配置。启用集成模块栈时，manifest 另存完整 runtime profile
及其 SHA-256，episode ID 增加 `-r<hash-prefix>`。规则基线和实验 treatment 可以共享场景
配置哈希，但不能共享 runtime profile 哈希或 episode ID。跨构建语义等价审计要求 runtime
profile 相同；有意改变策略开关的候选评审应使用专门的 treatment 对照，不得伪装成语义等价。
任一侧缺少合法的 64 位 runtime profile SHA-256 时，跨构建审计按不可比处理并失败关闭。

观测治理另写独立子清单，绑定 D1 扫描审计、D2 声明账本、在线治理快照、源总线和
evaluator-only 侧车的 schema 与 SHA-256。通用 episode manifest 不重复嵌入这些运行期
审计字段。

bundle 的本地绝对路径不写入 manifest。解析成功后记录语义版本和权重 SHA256；解析失败时
保留规则版本，并在 scenario metadata 与在线诊断中记录请求模式、实际模式和稳定回退原因。

正式验收只使用 `repository_dirty=false` 的结果。开发期脏工作树结果可以用于调试，但报告必须明确标注，不能作为阶段标签依据。

正式学习数据生成必须在启动 episode 前验证训练 seed 与保留评估 seed 零重叠，并验证
D5 主动视觉默认 20% 测试切分可提供至少 20 个唯一未见 seed。生成过程中逐 episode 检查
剩余磁盘；容量不足时停止，不删除或覆盖既有制品。

长批次可以通过 `--max-episodes-per-run` 在完整 episode 边界暂停，并以 `--resume` 继续。
恢复必须保持生成计划、训练 seed 注册表、Git 提交和计划 SHA256 不变，并逐项核对连续
progress 与 batch episode index。未索引、重复或不完整 staging 失败关闭；只有全部 cell
完成后才执行统一数据集最终化。正式标签仍绑定最终生成摘要和冻结 schedule，不以单个分块
替代完整批次证据。
版本 2 checkpoint 在 progress 行同步写盘后逐 episode 原子替换。进程若在 progress 已完整
落盘而 checkpoint 尚未替换的窄窗口退出，恢复入口只在全部 progress、staging、计划顺序、
在线真值隔离和安全字段均通过校验时接受滞后，并记录恢复次数、恢复行数和最后 episode。
checkpoint 领先、staging 领先或来源提交改变仍拒绝恢复。不同 Git 提交产生的 episode 不得
拼接为同一个正式学习数据集。
冻结的 balanced schedule 显式记录 `round_robin_cells_v1`。每轮依次遍历全部声明 cell 的
同一 seed offset，因此连续 45 个 episode 各覆盖一次 9 类场景和 5 档规模；执行顺序变化会
改变 schedule SHA256 和 generation plan，已有 checkpoint 必须拒绝恢复。

批次学习导出在成功最终化后把 episode 索引固化为根目录 `episodes.jsonl`，并删除已经转换
为正式 D3 数据集的重复 staging。任一 finalizer 异常时保留尚未消费的 staging；D4 因 seed
或标签条件未最终化时，其暂存目录继续保留。临时 `_staging/` 路径不属于长期消费合同。

正式实验矩阵还必须记录 R0/G1/A1/A2/A3/C1/F1、完整场景目录、5/20/50/100/200
规模、至少 20 个测试 seed 和训练 seed 注册表摘要。测试 seed 与训练 seed 有交集、模型
bundle 未加载、assist 未准入或运行时回退规则时，相关学习变体不得进入正式比较。矩阵
manifest 只记录版本和摘要，不记录 bundle 的本地绝对路径。

跨模块学习另使用源外 `scalable3d-shared-seed-split-registry-v1`。注册表绑定冻结的
`training_seed_registry.json` 文件 SHA256，以数值 seed 为不可分单元，统一采用
`60%/20%/20%` 的 train/validation/test 划分，并保持与 D3
`d3_numeric_seed_atomic_split_v2` 的排序兼容。它不修改 D3/D4/D5 原 dataset。任一模块的
seed 缺失、增加、错桶，或 source/assignment/content SHA 不一致时，C1 联合训练失败关闭。
正式 900-episode 数据对应的 detached 注册表文件 SHA256 为
`68608d29d1f733beea87f1faf06464fededb68a9c2972c51c10cd4c2160f032f`；其来源训练 seed 注册表
SHA256 为 `2ab928a476a4430b99326f245222f058bc5be5025158134ba89b01b3dec7815f`。保留 seed
`1000-1019` 不出现在三个训练桶中。

D5 在 2026-07-21 基于上述注册表为跨视角图和主动视觉数据建立 detached、只读的规范种子视图。
两类视图均按数值 seed 使用 `60/20/20` 分桶，保留 seed `1000-1019` 泄漏为 0，且不改写正式数据
manifest 或样本。跨视角图 view/readiness 文件 SHA256 分别为
`59d63560eccb443b09a868c7eb6abc159fea10ea823f6aee0378f3d3c0be85b6` 和
`e2feac1aec55a1a34e24545115c80006982ced65a43057771dc8510f1be96908`；主动视觉 view/readiness
文件 SHA256 分别为 `a019854fd87224996f5c84015bb66ccd37b7a0b5605f4784ffc59751e1716703` 和
`aac5d4ec82c27f26dd919f26d93e5eb4452a8f3c98ecbee7fad62577a43fcc09`。该登记只关闭 D3/D4/D5
学习消费者的 split 身份不一致。跨视角图仍因候选边和困难负边不足而 `fail_closed`；主动视觉仍为
`development_shadow_only`，不开放 assist、PPO 或相机命令权限。

D5 补充主动视觉课程已完成 100 episode、1200 sample 的全样本审计，审计文件和内容 SHA256
分别为 `9a03653538e6dae054da8c127ad4a20aae2481af6c9bbef987edfddff0b423d3` 和
`a11b65596a4c416deba6d0cb35dcc0c32342a5bae0481291d43e8de0e26550dd`。D6 必须同时接收该文件
及带外文件 SHA，并重新核对 dataset/view/config/registry/summary 绑定。当前 D5 子项为
`complete`，D3/D4 仍为 `pending`，跨模块总状态为 `partial`；该状态不开放 PPO、assist 或
authority。

保留 seed 隔离干预的新制品使用 `scalable3d-reserved-seed-interventions-v2`。v2 将 D3
`d3-offline-intervention-safety-shell-v2` 的二元端点检查纳入安全配置哈希，并要求 D4
`d4-region-resource-paired-arm-evidence-v2` 保存 confidence/OOD/latency/finite 分门结果。
提交 `6d5bfea` 生成的历史正式制品继续按 `scalable3d-reserved-seed-interventions-v1` 只读解释，
不得就地改写。一次制品必须完整绑定
seed `1000-1019`、源 episode 的 Git 提交和 dirty 状态、场景/初始状态/通信/故障/D3 输入/
D4 区域快照 SHA-256、D3/D4 冻结 bundle 身份，以及每个 treatment 的采用、回退和拒绝
原因。control 与 treatment 必须共享同一来源 episode；不得把两个独立重跑称为 paired。
运行器只生成隔离执行收据，不生成 runtime ACK、physical outcome、counterfactual 或 causal
字段。顶层目录通过临时目录原子发布并附 `SHA256SUMS`。正式证据要求 20 个源 episode 均为
`repository_dirty=false`；脏工作树输出只可用于调试。

clean 源提交 `78912963b67fe86ee9a8d29186b18a9dd60c460c` 已生成 v2 正式制品；`SHA256SUMS` 与
source manifest SHA-256 分别为 `821f15035e628d8db86f13c22d93f8e05142c5f00aae9118974a74bdc98b72bc`
和 `d6ef23b28add92e9a24a185ea72a7275e341bd796a2e11930c4d5f46b19a883c`。D6 profile-bound v2
审计由提交 `d4e8562` 的代码逐字节复生，sidecar 文件/内容 SHA-256 分别为
`f3852251daf02ec87fe878e7fb80aad6f381d8c0756a5c956a32e737a3871c3b` 和
`c02a345c46ddc642dea7fb6bfcfb24184e7dc2a9f35b754c90324d074b445d2d`。该 sidecar 只证明同帧
assignment comparison 可用，不把缺失的运行确认或物理结果补零。

每个持久化 episode 的 D1、D2 和 D6 子目录分别保存独立 manifest。D1 结果必须绑定在线
总线、离线真值状态和 D2 规范映射；D2 结果必须绑定原始 D1/D2 记录、观测真值标签和身份
证据；D6 在消费前重新校验结果文件及 D2 四类来源文件 SHA256。缺文件、哈希不一致或真值
隔离未验证时，指标保持 unavailable，不能填零。

## 模型文件

- 训练中间检查点和临时数据放入忽略目录，不进入普通 Git 提交。
- 长期保留的模型权重使用 Git LFS 或独立制品存储。
- 仓库提交模型说明、训练配置、数据集版本、输入特征定义和权重 SHA256。
- 在线加载权重前校验模型版本、特征版本和 SHA256；不匹配时回退规则路径。

## 阶段标签

阶段验收后由 main 创建带说明标签：

| 标签 | 验收范围 |
| --- | --- |
| `scalable3d-v0.1.0` | 三维环境、传感器和真值隔离 |
| `scalable3d-v0.2.0` | 200v200 规则跟踪和分配基线 |
| `scalable3d-v0.3.0` | D5 稀疏图关联 |
| `scalable3d-v0.4.0` | D3 学习代价修正和规则回退 |
| `scalable3d-v0.5.0` | 区域降级和三维导引闭环 |
| `scalable3d-v1.0.0` | 20 个未见 seed 的最终验收 |

标签只在对应测试、实验产物、GAP/PLAN 和中文报告齐全后创建。当前阶段未达到要求时不得提前打标签。
