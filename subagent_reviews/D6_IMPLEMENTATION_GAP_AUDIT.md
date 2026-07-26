# D6 实现差距审计

## 2026-07-26 D3 A1 与 D4 A2 外部审计 GAP 更新

### 已关闭

1. D6 已提供 D3/A1 和 D4/A2 evidence assembler 可消费的角色专用、版本化外部审计合同。
   共享核心不合并角色语义：A1 要求隔离实际采用，A2 要求运行确认。
2. 数据 manifest、数据内容、切分、全样本审计、模型 manifest、权重、实现文件集合、来源
   commit、正式作用域报告及校验清单均已进入显式带外 SHA-256 绑定。D4 readiness 另行绑定。
3. 至少 20 个未见 seed、训练 seed 零交集、实际采用、后续物理状态、在线真值零使用、安全/
   硬约束、唯一同键 R0 和 paired non-degradation 已进入失败关闭门。
4. `unavailable` 不补 0。正式报告缺失时，计数和
   `formal_scope_audit_passed` 均保持 `null/unavailable`。
5. 调用方自声明字段、shadow、规则 fallback、零采用、错误角色采用证据、隐藏的作用域或配对
   blocker、文件/内容篡改、来源漂移、R0 缺失/重复/复用和必选指标退化均有负向测试。
6. D6 只给 evidence audit pass/fail。模型晋级、辅助运行、分配、降级、默认路径和控制权限
   固定为 false。
7. 当前 D3/A1 与 D4/A2 实物已分别严格审计一次。两者均为 `fail_closed`，各 15 个 blocker；
   原审计目录未删除，新结果写入独立 `strict_v2` 目录。
8. 专项 `31 passed, 1 warning`，D6 全量
   `975 passed, 1 warning in 103.81s`。新增入口编译和 D6 路径差异检查通过。

### 当前 P1

1. **正式作用域证据缺失。** D3/A1 与 D4/A2 均没有正式作用域 JSON 和对应
   `SHA256SUMS`。未见 seed 数、正式 episode 数、实际采用数、物理窗口、唯一 R0 和 paired
   non-degradation 因而全部 unavailable。
2. **实现证据缺失。** 两模块均没有版本化 `implementation_evidence.json`，候选指纹和来源
   commit 无法形成完整消费合同。
3. **当前实现摘要漂移。** D3 冻结摘要/当前摘要为
   `86b06e07...c27` / `2e06c9d2...bdf`；D4 为
   `ecab1eb7...3d8` / `044284d7...431`。D6 保留
   `current_implementation_sha256_mismatch`，不通过改配置制造一致。
4. **候选仍处于开发阶段。** D3、D4 均为 development/shadow，实际正式 holdout 数为 0。
   D4 另记录动作多样性不足和策略能力未证明。开发候选可以进入预准入测试，但 shadow episode
   或只加载模型不能计作实际采用。
5. **装配器只能消费失败关闭合同。** D3/D4 assembler 需校验外部 JSON 文件哈希、
   `content_sha256`、角色/变体、所有来源摘要、availability、审计通过位和失败原因。当前结果
   不得生成正向 admission evidence。

当前无新增 D6-owned P0。D6 外部审计软件、严格 availability、报告和测试缺口已关闭。开放项
属于 D3/D4 正式证据生产和 assembler 接线；在模块 owner 补齐前，D6 按设计保持失败关闭。
本项不改变 AirSim 接口，`AIRSIM_INTEGRATION_PLAN.md` 已检查且无需修改。

## 2026-07-26 D5 G1 外部审计与装配器后谱系 GAP 更新

### 已关闭

1. D6 已提供 D5 evidence assembler 可消费的唯一外部审计 schema
   `d6.d5-g1-external-audit.v1`，并保持 D6 只读、不参与模型和控制授权。
2. 输入清单显式绑定 99fa registry、模型 manifest/weights/checksums、held-out、final
   paired-shadow 和 lineage。另一模型的 `e39a54d_v2` 不可被目录扫描误选。
3. 文件 SHA、内容 SHA、模型指纹、dataset/split/training-set、当前十文件实现和报告联合实现
   谱系均已独立重算。D6 与 D5 运行时摘要 API 使用相同文件集合和规范 JSON，实算均为
   `41381db3...4b07`。
4. 缺文件、文件/内容篡改、跨模型、跨数据集、实现错配、非正式、严格类型、阈值不足和
   unavailable 均有稳定 blocker；缺失计数不补 0。
5. JSON、证据 CSV、中文 Markdown 和 `SHA256SUMS` 已实现。相同 fixture 的重复运行逐文件
   一致。
6. D5 assembler 加入后，D6 使用独立配置对同一 99fa、held-out 和 final paired 实物完成复核。
   新旧输出目录分离；新主 JSON 文件/内容 SHA-256 为
   `98bf9e02...c8ed` / `40a42af0...90d`，原审计未覆盖。
7. 装配器后专项 `14 passed`，覆盖正负例、旧证据双文件差异和 CLI；D6 全量
   `944 passed, 1 warning in 80.12s`。
8. D5 已在 clean worktree `fa3ec10` 发布 7fb5 robust-v2 正式 registry。D6 对 registry、
   bundle、held-out、paired-shadow、lineage 和十个运行时源文件重新计算摘要，当前实现摘要为
   `408e71fe...f4fe`。
9. 2026-07-26T14:01:34Z 正式外审结果为 `pass`，blocker 为空。20 个未见 seed、900 个
   episode、45 个场景规模单元、三项安全零计数和全部冻结性能门均通过。主 JSON 文件/内容
   SHA-256 为 `10bf19f5...10b0` / `4e24ab33...9e54`。
10. 模型晋级、G1 assist、默认路径和控制权限仍全部为 false。本次只关闭 D6 冻结证据链审计
    GAP。专项为 `14 passed, 1 warning`，D6 全量为 `975 passed, 1 warning`。

### 当前 P1

1. **D5 准入装配待执行。** D5 assembler 尚未消费本次通过的 D6 合同并生成 D5-owned
   admission evidence。装配时必须重新计算 D6 JSON 文件/内容摘要和全部 consumer 字段。
2. **候选图未重建。** 五类扰动固定 post-gate 候选图。当前满分只证明评分器在固定候选边上的
   稳定性，不能证明重投影、门控和候选生成的全链路泛化。
3. **真实相机证据缺失。** 当前 20-seed/900-episode 证据来自合成三维质点投影和离线 truth
   evaluator，未覆盖真实内外参漂移、同步误差、检测漏检/虚警和纹理退化。
4. **运行作用域未验证。** G1 正式执行后还需现有 `learning_scope_formal_audit` 做同键 R0
   配对。预准入审计不能替代运行证据。
5. **运行权限保持关闭。** D6 pass 不等于模型晋级、assist、默认路径或控制授权。D5 admission
   与 main 显式配置完成前，规则路径继续保持默认。

当前无新增 D6-owned P0。7fb5 robust-v2 已关闭 D6 外部审计输入、实现谱系、冻结门和报告
缺口；上述 P1 属于 D5 准入装配、候选图全链路泛化、真实相机证据和正式运行作用域。

## 2026-07-25 正式实验矩阵准入预检 GAP 更新

### 已关闭

1. D6 已具备独立 `pre_run/post_run` 静态准入预检，不再需要先运行大矩阵才能发现清单、
   模型或制品缺口。
2. expected cell 由实际 `ExperimentMatrixPlan.cells()` 或 main 显式清单提供。当前正式合同
   动态得到 5700，而不是此前误写的 6300。
3. cell 唯一性、七变体、九场景、五规模、至少 20 个未见 seed、训练 seed 隔离、clean-source
   和禁止正式静默回退已进入失败关闭门。
4. 四类学习模型的 bundle、manifest、weights SHA 和 assist 声明已进入预检。文件存在或哈希
   正确不等于模型获准运行。
5. `post_run` 已逐 cell 检查采用模式、回退、在线真值、有限状态、D2 身份交换、五米物理指标和
   逐 seed 输入，并检查置信区间、报告、动画和模型清单。
6. 缺失 cell 使用压缩范围输出，JSON 和 CSV 仍保留逐 cell 状态。缺失指标保持 unavailable。
7. 当前静态结果 expected=5700、accepted=0、verdict=`fail_closed`。工具按设计拒绝，没有
   崩溃或生成伪指标。
8. CLI 缺少 inventory 时 expected=0 已明确标记为缺输入行为，不能与实际 5700-cell 清单
   混用。D4 保留 seed 数非法时也按未授权失败关闭，不再因类型转换异常中断。
9. 专项 `9 passed`，D6 全量 `889 passed, 1 warning`；既有 main 矩阵合同
   `7 passed, 1 warning`。当前输出的 JSON、CSV、Markdown 三项校验和均通过。

### 仍开放 P1

1. **正式运行清单。** 当前没有 `experiment_matrix_manifest.json` 和运行 cell CSV。正式
   5700-cell 矩阵尚未启动。
2. **模型准入。** D3、D4、D5 图模型、D5 主动视觉模型的 manifest/weights SHA 均匹配，但
   assist 声明均为 false。G1/A1/A2/A3/C1/F1 不能正式运行并静默回退。
3. **身份与物理指标。** D2 `id_switch_count` 和五米物理指标尚无逐 cell 正式可用证据。
4. **统计制品。** 正式逐 seed CSV、bootstrap 置信区间输入、中文报告、动画和运行模型清单仍
   缺失。
5. **系统性能。** 本项只关闭 D6 预检工具缺口，不关闭 200v200 实时性、学习收益或物理拦截
   缺口。

当前无新增 D6-owned P0。正式矩阵缺失和模型未准入属于系统 P1，预检保持失败关闭。

## 2026-07-25 D1 在线发布证据子集快照正式评估 GAP 更新

### 已关闭

1. D6 已实现独立只读 evaluator、CLI、固定 schema、确定性报告和失败关闭结果。评估器不调用
   producer 私有验收函数，也不写入 producer evidence。
2. clean commit `d0219eb14c529a4fb9bf7d6610a9f32055a09206`、matrix SHA
   `6c808c4df8759fd893c6d37ff9dce4a1efa07f9867fc71aff47a55c5f8517338`、
   13 pair、26 fresh arm、200/200/2、seed、时长、arm 顺序、命令和路径边界已冻结。
3. runtime profile、summary、module final、governance audit 和 nested governance 的 selector、
   完整实现 ID、execution config 和 diagnostics 已进入 fail-closed 校验。两臂 replay-prefix
   均要求 `per_checkpoint_prefix_rebuild_v1`。
4. D1/D2 在线记录、在线总线、业务计数、consistency record count/digest、原 D1 fusion
   operation counts、有限状态和 online truth use=0 已逐 pair 独立比较。
5. 候选 fallback、lookup miss、invalid required ID 和 empty set 为 0；reference 完整路径、
   candidate 子集路径和计数守恒均有正负测试。
6. 正式 13/13 pair 的来源、语义、身份、原操作计数、consistency 和诊断审计通过。候选
   `429/429` 次子集选择成功，返回记录削减 `91.641524%`。
7. 正式 verdict 为 `reject`。short 更快数 `4/10`、D1 改善 `-0.147877%` 和 bootstrap
   上界 `1.374681%` 未达到冻结门；门限和 pair 均未修改。
8. 正式 bundle 已生成到
   `research_modules/d6_evaluation_metrics/outputs/d1_publication_evidence_snapshot_multiseed_20260725_formal_d0219eb_d6/`。
9. 同一正式 manifest 重复评估与正式 bundle 逐文件一致。聚焦测试 `14 passed`，D6 全量
   `880 passed, 1 warning in 76.17s`。

### 仍开放 P1

1. **候选准入。** `required_observation_subset_v1` 保持默认关闭，reference 保持默认。重新准入
   必须使用新候选和新预注册矩阵。
2. **短时收益稳定性。** 记录削减已成立，short D1 墙钟收益未成立。不能用记录削减门替代
   性能门。
3. **系统实时容量。** 候选最低实时因子 `0.203423 < 1`，
   `system_realtime_gap_closed=false`。
4. **外部适用性。** 本轮仅为 200/200/2 三维质点证据，不关闭 AirSim、目标处理器、硬件、
   实机或实飞 GAP。

当前无新增 D6-owned P0。D6 evaluator、正式 evidence 消费、统计、报告和测试缺口已关闭；
候选准入、系统实时和外部适用性保持开放。

## 2026-07-25 D1 回放前缀摘要正式评估 GAP 更新

### 已关闭

1. 独立只读 evaluator、CLI、固定 schema 和六类报告制品已经实现；不调用 producer 私有
   `_episode_matches`，也不采信 producer admission 结论。
2. producer commit `7d2e987471b521a1e531bf03a5c99af5096f676a`、matrix SHA
   `85432d729877eff97e6f3dd517d4baa7a47f44a4fa42e6bfdc7ce85b8d9ec74b`、13 pair、
   26 fresh episode、200/200/2、seed、时长、命令、路径和唯一 treatment 均已冻结并从正式
   manifest 核对。正式输入 0 reused、0 failed。
3. 13/13 pair 的业务语义、在线 consistency digest/count、D1 原操作计数、实现身份、有限状态、
   在线真值隔离及导出前后诊断守恒通过。
4. 候选摘要命中、checkpoint 复用、append revision、pending preservation 和在线 snapshot
   projection 均实际发生；append 物化为 0，导出后 pending ledger 为 0。
5. 内部实际物化由逻辑刷新 `811858` 条降至 `388468` 条，减少 `52.150746%`。在线快照投影
   构造 `656481` 条记录单独披露，没有作为已消失工作量。
6. D6 已对正式 evidence 给出 `reject`，且
   `main_default_promotion_allowed=false`。失败门为 short 更快
   `5/10 < 8/10`、short D1 改善 `0.959611% < 1%`、short bootstrap 上界
   `0.619827% > 0%`、short core 改善 `-0.256641% < 0.25%` 和 long core 改善
   `-1.930083% < 0.25%`。没有调门或删除 pair。
7. long D1 改善 `2.361778%`，内部物化压缩、short/long RSS 和 D2 组均值门通过。局部通过项
   没有覆盖五个失败门。
8. 正式 bundle 位于
   `research_modules/d6_evaluation_metrics/outputs/d1_replay_prefix_summary_multiseed_20260725_formal_7d2e987_d6/`；
   `SHA256SUMS` 已通过。main 从同一 manifest 重跑后全部制品 SHA-256 与正式 bundle 一致。

### 仍开放 P1

1. **候选准入。** 候选
   `fixed_lag_checkpoint_prefix_cumulative_summary_v1` 保持默认关闭，参考
   `per_checkpoint_prefix_rebuild_v1` 保持默认。任何重新准入必须使用新候选名和新预注册
   矩阵，不得覆盖本轮 `reject`。
2. **端到端工作量。** 在线快照仍投影构造 `656481` 条记录，是内部压缩未形成 core wall
   收益的主要线索。该问题属于后续新候选，不得回写本轮证据。
3. **系统实时容量。** 候选最低实时因子 `0.197441 < 1`，
   `system_realtime_gap_closed=false`。
4. **外部适用性。** 本轮仅覆盖 2026-07-25 的 200/200/2 三维质点矩阵，不关闭 AirSim、
   目标处理器、硬件、实机或实飞 GAP。

当前无新增 D6-owned P0。D6 正式消费、独立判定、统计、报告和确定性复跑缺口已关闭；候选准入、
系统实时、端到端快照成本和外部适用性保持开放。

## 2026-07-25 D1 关联稀疏预筛正式评估 GAP 更新

### 已关闭

1. D6 已实现 schema
   `d6.d1_association_sparse_prefilter_multiseed_evaluation.v1` 的独立只读 evaluator、CLI、
   失败关闭结果和确定性六制品 writer；不调用 producer runner 私有验收函数。
2. matrix SHA
   `a7162d014d1c3c0f207355b24a5d7159bf3486d134ca21876f7469d1e915b71d`、clean source
   commit `9302ccede2ca513c2235370e1a464fc88bc41150`、13 pair/26 fresh arm、200/200/2、
   seed、时长、arm 顺序、命令、路径和 producer pending-D6 状态已冻结。
3. runtime profile、summary、module final、governance 及冗余 configuration/nested governance
   的 selector、完整 implementation ID、execution config v1 和 diagnostics v2 已进入
   fail-closed 校验。
4. 六个固定模态桶、逐桶计数上界、总计守恒、reference 非雷达零 rejection、candidate treatment
   实际执行、逐 pair 工作量相同和逐 pair/逐模态 exact gate-pass 相等均已实现。
5. 业务语义仅归一化登记 treatment、对应诊断/运行时哈希差异和性能字段；在线消息、D1-D7
   业务输出、计划谱系、D4 内容地址与 ACK 和三个离线 truth 制品继续比较。
6. short/long D1 fusion、core wall、scan input、D2 association、RSS、RTF、候选更快数和
   10000 次 paired bootstrap 均按冻结矩阵重算；局部准入和系统实时门分离。
7. 正式 13/13 pair 的来源、业务语义、实现身份、有限状态、真值隔离、预筛审计和逐模态
   gate-pass 相等通过。非雷达精确求解由 `298109` 降至 `39837`，减少
   `86.636767%`。
8. 正式结果严格保留五个失败门：short 更快 `7/10 < 8/10`、D1 fusion 改善
   `0.228437% < 1%`、bootstrap 上界 `0.443531% > 0%`、core 改善
   `0.091096% < 0.25%`，long D1 fusion 改善 `0.713776% < 1%`。verdict 为
   `reject`，main 默认晋升不允许。
9. 正式 bundle 位于
   `research_modules/d6_evaluation_metrics/outputs/d1_association_sparse_prefilter_multiseed_20260725_formal_9302cce_d6/`；
   完整/紧凑 JSON、13 条 pair CSV、中文 Markdown、PNG 和 `SHA256SUMS` 已生成并通过校验，
   原始 evidence 未写入。
10. 正负测试覆盖 SHA、commit、selector、execution config、diagnostics schema、计数守恒、
    gate-pass mismatch、业务语义、性能、RSS、D2、online truth 和缺文件。定向
    `13 passed, 1 warning in 7.22s`，D6 全量 `859 passed, 1 warning in 64.83s`。

### 仍开放 P1

1. **候选准入。** 五个冻结性能门失败，reference `disabled_v1` 保持默认。任何重新准入需使用
   新的预注册矩阵，不得调门、删 pair 或覆盖本轮 `reject`。
2. **系统实时容量。** 候选最低实时因子 `0.206273 < 1`，
   `system_realtime_gap_closed=false`。
3. **外部适用性。** 本轮仅为 200/200/2 三维质点证据，不关闭 AirSim、目标处理器、硬件、
   实机或实飞 GAP。

当前无新增 D6-owned P0。D6 evaluator、正式 evidence 消费、统计、报告和失败关闭测试缺口已
关闭；候选准入、系统实时和外部适用性保持开放。

## 2026-07-25 D1 在线批帧交接正式评估 GAP 更新

### 已关闭

1. D6 已实现 schema `d6.d1_online_batch_frame_multiseed_evaluation.v1` 的独立只读 evaluator、
   CLI、失败关闭结果和确定性六制品 writer。
2. matrix SHA
   `4afbf9ac273763a16aa01cc744fd67b52e437099460b33377a128f986ac5719b`、clean commit
   `43feaf600f288a85ce76a76862334256f0d0d352`、13 对/26 fresh episode、200/200/2、
   seed、时长、arm 顺序、命令与路径边界已冻结。
3. runtime profile/summary/module final/nested governance/governance audit 的 selector、完整
   implementation ID、execution config 和四份最终诊断谱系已进入 fail-closed 校验。
4. request/path/result、raw batch、snapshot structure/success、final frame 和 measurement/output
   守恒均从原始诊断重算；重复检查、closed ratio 与 fallback 不采信 producer admission。
5. 业务语义只归一化预注册 treatment、诊断派生字段、episode identity 和性能。opaque plan ID
   及其内容地址先验证再按谱系映射；assignment、授权、target/resource、owner/coalition 业务字段、
   lease 状态关系、状态机、计数、安全和下游引用不豁免。
6. 正式 13/13 pair 的业务语义、有限状态、实现身份和批帧审计通过；online truth use 总数为 0。
   short/long scan 改善 `38.289241%/36.275282%`，core 改善
   `4.252745%/4.916501%`，D2 增幅 `2.113047%/2.830616%`，RSS 最大组均值/任一 pair 增幅
   `0.281879%/0.856727%`，重复检查减少和 closed ratio 均为 `100%`，fallback=0。
7. 全部冻结 gate 通过，候选优化结论 `admit`。正式目录为
   `research_modules/d6_evaluation_metrics/outputs/d1_online_batch_frame_multiseed_20260725_formal_43feaf6_d6/`；
   同目录复跑全部制品 SHA-256 一致，原始 producer evidence 未写入。
8. 新增定向测试 `12 passed, 1 warning`，覆盖矩阵/阈值篡改、身份、守恒、窄归一化和 assignment
   差异不可隐藏；D6 全量 `846 passed, 1 warning in 59.24s`。

### 仍开放

1. 候选最低实时因子 `0.204490 < 1`，200v200 系统实时 P1 未关闭。局部 `admit` 不得写作系统
   实时达标。
2. 本轮仅为三维质点证据，不是 AirSim、目标处理器、实机或实飞证据。
3. 当前无新增 D6-owned P0；已关闭的是正式只读评估和报告 GAP，不是系统实时容量 GAP。

## 2026-07-25 D1 不透明来源标识缓存评估 GAP 更新

### 已关闭

1. D6 已实现 schema
   `d6.d1_opaque_source_identity_cache_multiseed_evaluation.v1` 的独立只读 evaluator、CLI、
   失败关闭报告和确定性制品 writer。
2. matrix SHA
   `218d04f3fc4a764fef82de612c78c8fbb5490380ae5d20aff6b9089635f2060d`、clean producer
   commit `d8fc76c066f21b077154f7be33c0b43558d237e5`、13 pair、26 fresh complete arm、
   200/200/2、seed、时长、arm 顺序、命令和路径边界已固定。
3. source-only 发布键、hold=false、selector、实现 ID、诊断 schema、容量和 publisher
   generation 已进入失败关闭校验。结果明确不外推到默认无来源键 R0。
4. 候选的 `request=hit+miss+bypass`、`build=miss+bypass`、hit/miss 正值、bypass=0 和容量边界，
   以及参考的 `request=bypass=build`、零缓存活动均已实现并有负例测试。
5. D6 逐对核对在线消息、`GlobalTrack`、来源键业务值、状态/协方差、D2-D7 消费结果、计划、
   控制和离线真值。只归一化预注册处理字段与性能字段，在线真值使用要求为 0。
6. short/long D1、core、D2、RSS、候选更快数、10000 次 bootstrap、标识构造减少率和命中率
   已按冻结门实现。D2 采用候选组均值相对参考组均值的增幅。
7. 正式 bundle 已生成，包含完整 JSON、compact JSON、13 条 pair CSV、中文 Markdown、PNG 和
   `SHA256SUMS`。输入 manifest 保持只读。
8. 聚焦测试 `16 passed, 1 warning in 5.85s`，D6 全量
   `834 passed, 1 warning in 59.24s`。
9. 正式矩阵 26/26 arm 全部 fresh complete，0 reused、0 failed；13/13 业务语义、有限状态、
   真值隔离、实现身份和缓存审计通过。
10. short/long D1 融合改善 `9.465972%/6.437432%`，核心墙钟改善
    `2.845610%/2.728043%`，标识构造减少率和命中率均为 `99.163670%`。
11. long D2 关联组均值增幅 `5.605213%` 超过冻结上限 `5%`，是唯一失败门。
    `long_seed_1101` 的 `19.069868%` 单 pair 增幅未剔除。因此
    `optimization_admitted=false`，失败关闭行为符合预注册合同。

### 仍开放 P1

1. **候选性能稳定性。** 需要新的预注册确认矩阵复核 long D2 回归。不得修改本轮门限、删除
   `long_seed_1101` 或覆盖本轮不准入结论。
2. **系统实时容量。** 候选最低实时因子 `0.193887`，低于 1，
   `system_realtime_gap_closed=false`。
3. **外部适用性。** 当前证据仅覆盖 source-only、hold=false 的 200/200/2 三维质点矩阵。
   默认无来源键 R0、AirSim、目标处理器和实飞仍需独立证据。

当前无新增 D6-owned P0。D6 evaluator、正式消费、统计、报告和失败关闭测试缺口已关闭；候选准入、
系统实时和外部适用性保持开放。

## 2026-07-25 D1 结构化数值雅可比评估 GAP 更新

### 已关闭

1. D6 已实现 schema `d6.d1_structured_jacobian_multiseed_evaluation.v1` 的独立只读 evaluator、
   CLI 和确定性报告 writer。
2. matrix SHA
   `c6c3cf53c89dfb3155a29ba49bb77a12c8bdf1a5d433c4f645de0d00c506d478`、clean producer
   commit `9d1f54f8540fdc4a7a1011121aafac5718290122`、13 case、26 个 fresh arm、200/200/2、
   seed、时长、命令和证据边界已固定。
3. selector、完整实现 ID、diagnostics schema、候选标志和四份最终诊断一致性已进入失败关闭
   校验。雅可比 attempt、success/failure、reference/candidate call、probe 和 measurement
   evaluation 的操作数守恒已实现。
4. 两臂 Jacobian attempt 工作量相同、13/13 业务语义等价、有限状态和在线真值零使用已进入
   准入合同。
5. D1 fusion、core wall、D1 scan input、D2 association、RSS、逐 pair 更快数、10000 次配对
   bootstrap 和量测函数求值减少率已按冻结门实现。
6. 缺失输入、缺字段、版本错配、provenance、diagnostics、conservation、business、performance、
   dirty、reused、command 和路径篡改均有合成正负测试。证据无效时保留
   `availability=false + reason`，候选不会误准入。
7. 完整 JSON、compact JSON、逐 pair CSV、中文 Markdown 和 `SHA256SUMS` 已实现；原始 evidence
   保持只读。
8. 2026-07-25 专项 `20 passed, 1 warning in 6.05s`，D6 全量
   `818 passed, 1 warning in 55.42s`；warning 为既有 Matplotlib `Axes3D` 环境提示。
9. main 已使用 D6 CLI 完成正式评估。输入为 13 pair、26 个 fresh complete arm，0 reused、
   0 failed，`availability=true`。
10. 13/13 业务语义、有限状态、在线真值零使用、实现身份、诊断与操作数守恒通过；全部冻结准入
    门通过，`optimization_admitted=true`。
11. 短时 D1 融合/核心墙钟改善 `6.084778%/1.897370%`，`10/10` 更快；长时改善
    `4.676061%/1.786530%`，`3/3` 更快；量测函数求值减少 `53.846154%`。
12. 正式报告与校验和已由 main 生成并保持原样。D6 正式 evidence 消费和局部准入缺口关闭。
13. main 已完成 scalable 3D 默认晋级。`IntegratedStackConfig` 与 `run_episode` CLI 默认使用
    `known_dimension_structural_columns_v1`，`dense_output_probe_v1` 保留显式回退。该变更不
    影响 D6 evaluator 独立性或 D1 独立 `FusionAdapter` 默认实现。
14. scalable 测试通过；2v2 默认 smoke 的三处配置/摘要/治理表面均记录候选实现，有限状态为
    true，在线真值使用为 0。该 smoke 不用于关闭系统实时门。

### 仍开放 P1

1. **系统实时容量。** 候选最低实时因子为 `0.180726`，低于门限 1，
   `system_realtime_gap_closed=false`。需要 AirSim 和目标处理器端到端证据关闭该项。
2. **外部适用性。** 冻结矩阵属于 200/200/2 三维质点离线证据，不关闭 AirSim、目标硬件或实飞
   容量缺口。

当前无新增 D6-owned P0。D6 工具实现、正式 evidence 消费和局部准入缺口已关闭；系统实时容量和
外部验证仍为 P1。

## 2026-07-24 在线真值检查评估 GAP 更新

### 已关闭

1. D6 已实现独立、只读、失败关闭的 13-pair evaluator、CLI、完整 JSON、compact JSON、逐
   pair CSV、中文 Markdown 和校验和输出。
2. matrix schema/SHA、evidence/evaluator/diagnostics schema、clean source commit
   `8d8bb6ed7a417705236835f235361f45a021bb2b`、200/200/2、seed、时长、arm 顺序和命令已
   固定。
3. 26 个 arm 只接受 fresh complete 和零返回码；dirty、reused、错误 commit、旧 schema、路径
   越界、非登记 stderr 和命令漂移均失败关闭。
4. 每个 arm 要求 `validation_count = online_message_count > 0`，有限状态和在线真值使用为零。
5. 九类 episode 文件和 resource/stdout/stderr 均重新计算 SHA-256；config、runtime profile、
   governance、stage timing 和 truth-guard diagnostics schema 已固定。
6. 在线消息、D1/D2 航迹与关联、D3 分配、D4 内容地址、D5/D7 输出、计划谱系、治理和离线真值
   进入业务等价门。处理归一化只覆盖 selector、对应诊断、性能字段和派生 episode ID。
7. 发布总线及 finalize、核心墙钟、外层耗时、实时因子、D1、D2、RSS、short/long 配对统计和
   10000 次 bootstrap 已实现。全部数值门从冻结 matrix 读取。
8. 合成专项覆盖正常矩阵、只读报告、CLI、检查数不守恒、实现身份、业务漂移、性能门和来源/
   schema/matrix/command 篡改。
9. main 已完成正式矩阵。26 个 arm 全部 fresh complete，0 reused、0 failed；D6 已复核完整
   JSON、compact JSON、13 条 pair CSV、中文 Markdown 和 `SHA256SUMS`。
10. 13/13 pair 的业务语义、有限状态、在线真值隔离、实现身份、来源和检查数守恒通过。参考与
    候选各 94074 条在线消息均完成检查，在线真值使用为 0。
11. short/long 发布总线及收尾改善 `22.58%/25.63%`，候选分别 `10/10`、`3/3` 更快；
    short 核心墙钟改善 `2.50%`。
12. long 核心墙钟回退 `3.47%`，long D1/D2 分别增加 `5.29%/7.34%`，三项预注册门失败。
    `optimization_admitted=false`，候选保持默认关闭，默认仍为 `generic_recursive_v1`。
13. 正式结果同步后专项 `14 passed, 1 warning in 4.46s`，D6 全量
    `798 passed, 1 warning in 52.01s`。

### 仍开放 P1

1. **系统实时容量。** 候选最低实时因子为 `0.165369`，低于 1，
   `system_realtime_gap_closed=false`。
2. **候选性能稳定性。** long seed 1102 出现核心、D1 和 D2 同向回退。可选 balanced-order v2
   可以诊断运行顺序与主机热状态，但不得覆盖 v1 正式结论。重新准入必须使用预先冻结的新矩阵。
3. **外部适用性。** 本 evaluator 只覆盖三维质点 episode。AirSim、目标处理器和实飞容量继续
   需要独立证据。

当前无新增 D6-owned P0。评估工具和正式 evidence 消费缺口已关闭；候选不准入、系统实时与外部
验证保持开放。

## 2026-07-24 D1 常速度模型缓存评估 GAP 更新

### 已关闭

1. D6 已实现独立、只读、失败关闭的 13-pair 缓存 evaluator、CLI、完整 JSON、compact JSON、
   CSV、中文 Markdown、PNG 和校验和输出。
2. matrix SHA
   `9898656598f0fa282620afe2384a3d656b7496f8957109c413bcb62069fd2e9a`、clean source
   `44223566439a446fc49f2a3fd861d1d51bd676b9`、200/200/2、容量 128、seed、时长、arm 顺序、
   命令和准入门均已固定。
3. selector、实现 ID、candidate flag、诊断 schema、容量和诊断副本的一致性已覆盖 runtime
   profile/configuration、summary、module final、嵌套治理和独立治理。
4. candidate 请求/构造守恒、hit/miss/build 非零、entry/peak 容量，以及 reference 零缓存活动
   和构造请求关系已有失败关闭测试。两臂请求工作量必须相等。
5. D6 内部执行跨 episode 语义比较，只排除 `same_runtime_profile`；非白名单业务变化会关闭
   semantic gate。
6. D1、D2、core、RSS、实时因子、模型构造减少率、缓存命中率、逐 pair 变化和 10000 次配对
   bootstrap 已实现，门限从冻结矩阵读取。
7. 评估器实现阶段专项 `13 passed, 1 warning in 5.03s`；D6 全量
   `784 passed, 1 warning in 48.64s`，零失败。
8. main 已完成正式矩阵。26 个 arm 全部 fresh complete，0 reused、0 failed；D6 对完整 JSON、
   compact JSON、含 13 条 pair 记录的 CSV、中文 Markdown、PNG 和 `SHA256SUMS` 进行只读复核。
9. 13/13 pair 的业务语义、有限状态、在线真值隔离、实现身份和缓存审计通过，19/19 准入门通过。
10. short/long D1 融合改善 `6.9271%/6.6103%`，核心墙钟改善
    `2.4060%/2.4537%`，D2 增幅 `-0.1082%/-2.6729%`，RSS 均值增幅
    `0.0145%/0.2959%`。
11. 构造减少率和命中率均为 `99.5960%`，short `10/10`、long `3/3` 更快，short bootstrap
    上界为 `-6.0841%`；`d1_optimization_admitted=true`。D6-owned 正式证据消费缺口关闭。
12. 本次正式结论文档同步后 D6 全量回归为 `784 passed, 1 warning in 55.02s`；warning 为既有
    Matplotlib `Axes3D` 环境提示。

### 仍开放 P1

1. **系统实时容量。** 候选最低实时因子为 `0.17394990897894075`，低于 1，
   `system_realtime_gap_closed=false`。AirSim 和目标硬件容量仍需独立证据。
2. **外部适用性。** 冻结矩阵只覆盖 200/200/2 三维质点场景。它不替代不同规模、AirSim、
   目标处理器、传感器精度或实飞验证，也不能推导物理拦截效果。

当前无新增 D6-owned P0。D6 评估器、正式证据消费、统计、报告和失败关闭测试缺口已关闭；
系统级实时与外部验证证据保持 P1。

## 2026-07-24 D1 发布元数据 v2 正式评估 GAP 更新

### 已关闭

1. v2 独立 evaluator、schema、CLI、正式报告和失败关闭测试已完成；v1 行为和历史结论未改写。
2. 13 pair/26 arm 的矩阵 SHA、clean commit、规模、seed、时长、命令、资源和返回状态已严格绑定。
3. D1 v2 合同和 D2 审计已在四个位置交叉校验。审计只作处理诊断归一化，非白名单业务字段仍比较。
4. short/long D1、核心墙钟、D2 增幅、RSS、候选更快数和 bootstrap 门均输出实际值和阈值。
5. 正式结果全部局部准入门通过，`d1_optimization_admitted=true`。制品已归档，未复制原始 episode。
6. v1/v2 专项 `37 passed, 1 warning`，覆盖审计篡改、业务漂移、D2 回归、核心墙钟和 provenance；
   D6 全量为 `771 passed, 1 warning in 47.61s`。

### 仍开放 P1

1. **系统实时容量。** 候选最低实时因子为 `0.17308010045846806`，低于 1；
   `system_realtime_gap_closed=false`。三维质点证据不能关闭 AirSim 或目标硬件实时缺口。
2. **逐批审计可定位性。** 当前 producer 只保留 latest 和 totals。D6 能验证累计合同，不能重放
   每一批的明细。逐批异常定位需 producer 增加日志，不影响本次准入结论。

当前无新增 D6-owned P0。v2 正式评估消费缺口已关闭。

## 2026-07-24 D1 航迹发布元数据正式评估 GAP 更新

### 已关闭

1. D6 已实现独立 13-pair manifest consumer、CLI 和合成 fixture，不从目录名推断 arm、seed、
   duration 或规模，不参与控制。
2. evidence/matrix schema、固定 SHA256、source commit、case/arm 顺序、命令隔离、200/200/2、
   bootstrap 和准入门均精确校验。
3. 26 个 arm 必须 complete、返回码为 0、文件完整；stderr 只允许空或唯一登记的 Matplotlib
   `Axes3D` 环境警告。
4. selector、D1 实现 ID、不可变标志和操作数在三个持久化位置交叉确认。参考复制为正，候选复制
   为 0、共享复用为正，两臂完整物化数相等。
5. D2 身份/ID switch、D3 计划谱系、D4 内容地址和 ACK 来源、D5/D7 输出、非白名单业务字段、
   离线真值状态/标签/5 米事件及在线 truth=0 已进入等价门。
6. D1 fusion wall/P50/P95/max、scan input、D2/D3/D5/D7、publication bus、core wall、
   external elapsed、RSS、实时因子、配对统计、均值比和固定 bootstrap 已实现。
7. JSON/aggregate/CSV/中文 Markdown/PNG/SHA256 bundle 已归档，原 4.2 GB evidence 保持外部只读。
8. 专项 `27 passed`，覆盖错误实现 ID、假 selector、候选仍复制、参考不复制、共享复用为零、
   物化数不等、不可变标志、语义漂移、truth 泄漏、失败状态/返回码、非登记 stderr、RSS/性能/
   bootstrap 门和路径边界。D6 全量为 `761 passed, 1 warning in 41.25s`。

### 正式证据结论

1. D1 fusion short/long 均值比改善约 `16.29%/31.05%`，候选 `10/10`、`3/3` 更快。
2. 13/13 业务语义、有限状态、真值隔离、实现身份和 RSS 门通过。
3. D2 association short/long 增加约 `53.44%/169.89%`。候选自定义只读容器未进入 D2 精确内建
   容器等值复用，真值隔离审计重复扫描共享诊断树。
4. short/long 核心墙钟仅改善约 `1.65%/1.21%`，两项 5% 门失败；
   `d1_optimization_admitted=false`。
5. 候选最低实时因子为 `0.14695931849644195`；
   `system_realtime_gap_closed=false`。

### 仍开放 P1

1. **D1/D2 容器互操作性能。** D1 共享只读树和 D2 真值隔离批审计需形成不重复扫描且仍失败关闭的
   合同。该修复不属于 D6 所有权。
2. **正式重评。** D1/D2 修复后，main 需按相同 clean、13-pair、200/200/2 矩阵重跑；D6 使用原
   预注册门复评。未通过前候选不得写成默认性能准入。
3. **系统实时、AirSim 和目标硬件。** 当前最低实时因子远低于 1，三维质点证据不能关闭系统实时
   或替代 AirSim/目标硬件容量验证。

当前无新增 D6-owned P0。D6 consumer、门控、报告和正式 evidence 消费缺口已关闭；跨模块
D1/D2 性能和系统实时保持 P1。

## 2026-07-24 D1 扫描输入同提交评估 GAP 更新

### 已关闭

1. D6 已实现严格只读的 13-pair manifest consumer，不从路径名推断 arm、seed、duration 或规模。
2. 冻结矩阵 SHA、schema、experiment、case 顺序、200/200/2、bootstrap、准入门和 evidence
   boundary 均精确校验。
3. 同一 clean commit、arm 状态、命令隔离和多处实现身份检查已进入失败关闭合同。
4. 在线业务输出、D3 计划谱系、D4 内容地址/确认引用、离线真值和 summary/governance 等价检查
   已接入；允许差异使用显式白名单。
5. 扫描输入分位、core wall、external elapsed、RSS、实时因子、配对统计、bootstrap、准入门和
   独立实时门已实现。
6. evaluation/aggregate JSON、逐 pair CSV、中文 Markdown、PNG 和输入文件 SHA256 已实现；
   evidence root 只读约束已有回归。
7. 2026-07-24 初始专项 `13 passed`，覆盖规定的合同和篡改负例。
8. 已关闭真实 summary 误拒绝。白名单仅增加 treatment 派生 `episode_id`、final
   `stage_timings` 和 final 内重复 governance 的实现/性能字段；非白名单业务字段仍严格比较。
   更新后专项为 `15 passed`。
9. 已消费 clean commit
   `d14285e4fdeb2f2e2cd32fad2f6d42e30f9e73a7` 的正式 13-pair evidence。26 个 arm
   全部完成且零退出；manifest SHA256 为
   `760cd0e522b27b99de8c30c366ad7e65f16f783d71cf28e3492be299e24b2402`。
10. short 扫描输入平均改善 `5.360121886647966%`、`9/10` 更快，bootstrap 原始区间
    `[-8.208165356448217%, -3.0841406102053194%]`；long 改善
    `5.142481684491682%`、`3/3` 更快，区间
    `[-8.837128529506151%, -1.6693612946922343%]`。
11. 全部业务语义、有限状态、在线真值隔离、实现身份、核心墙钟和 RSS 门通过，
    `d1_optimization_admitted=true`。正式 bundle 已带 SHA256 归档；D6-owned 正式评估缺口关闭。

### 仍开放 P1

1. **系统实时性保持独立开放。** 候选最小实时因子为 `0.14342687633969603`，未达到 1；
   `system_realtime_gap_closed=false`。三维质点结论不能替代 AirSim 或目标硬件容量证据。

当前无新增 D6-owned P0。评估器实现和正式证据消费缺口已关闭；系统级实时容量、AirSim 和
目标硬件证据保持开放。

## 2026-07-24 D1 多 seed 与长时评估 GAP 更新

### 已关闭

1. D6 已实现固定 short 10 seed、long 3 seed 的显式矩阵 consumer，不根据目录名推断实验语义。
2. 现有单 pair clean、commit、config、runtime、scale、finite、truth、exit 和 cross-build 检查
   已复用；跨矩阵增加配置除 seed/duration 外一致、runtime profile 一致和结构歧义保活检查。
3. short/long 的均值、中位数、P95、paired relative change 和确定性 bootstrap 95% CI 已实现。
4. 共同 seed 的 D1 fusion、core wall、external elapsed 单位时间增长已实现，核心 wall 与 external
   elapsed 没有相加。
5. 全部预注册性能门和失败关闭门已形成机器结论；JSON、LF CSV 和中文 Markdown writer 已完成。
6. completed evidence manifest loader 已实现。内嵌矩阵的 experiment、提交、13 个 case、规模、
   运行参数、10000 次 bootstrap、准入门和固定 runtime profile 均精确校验；arm 标签、提交、状态、
   零返回码、路径和 cross 状态均失败关闭。manifest 与 `--pair` CLI 互斥。
7. loader 已登记 v1/v2/v3 三套完整矩阵。v2 的 effective/base commits、公共 D2 修复来源和主题、
   `v1_outputs_reused=false` 均精确匹配；未知实验、任意提交、谱系篡改或 v1 注入 v2 字段失败关闭。
8. v3 的 effective/base commits、公共 D1/D2 修复、reference treatment、v1/v2 输出复用边界和
   reference/candidate 向量化标志均精确匹配；v2 注入 v3 字段及 v3 任一字段篡改失败关闭。
9. D2 处置 consumer 继续要求 `known_false_alarm_only_mapping_count` 与持久化
   `status=excluded && reason=known_false_alarm_only` 数量精确相等。旧 `14/11` 被拒绝，修复后
   `11/11` 通过；3 个 unavailable mapping 不进入计数。
10. v3 注册完成时的基线为多 seed 专项 `65 passed`、truth/runtime 相关专项 `87 passed`、原
    clean-pair 专项 `9 passed`、D6 全量 `715 passed, 1 warning in 24.28s`。
11. 已关闭矩阵指标方向展示缺口。六项成本/资源指标按越低越好，实时因子按越高越好；兼容字段和
    原始 bootstrap 不变，新增候选更优计数和方向化改善。正式 v3 的实时因子 short/long 应显示
    `10/10`、`3/3`，本轮不改变 evidence、门控或准入结果。更新后专项 `67 passed`、D6 全量
    `717 passed, 1 warning in 24.26s`。
12. 已关闭固定图表 bundle 缺口。writer 新增确定文件名的二维 PNG，覆盖 13 个 D1 融合配对改善
    和 short/long 五项方向化均值改善；RSS 不进入主图。缺 pair、指标 unavailable、方向错误或
    非有限值时删除旧图并失败关闭，CLI 返回 `outputs.png`。更新后专项 `69 passed`、D6 全量
    `719 passed, 1 warning in 24.65s`。

### 仍开放 P1

1. **正式报告需要重生。** main 已完成正式 v3 manifest 和首次报告。当前代码已修复实时因子方向，
   并增加固定 PNG；仍需使用同一 manifest 重生 JSON/CSV/Markdown/PNG bundle，不需要重跑矩阵
   或改写 evidence。
2. **系统实时性未关闭。** 该矩阵属于三维质点。AirSim 或目标硬件的处理、调度和资源证据仍缺失。
3. **精度指标不在本门内。** 均方根误差、归一化估计误差平方、归一化创新平方和严格身份指标仍需
   独立 truth-isolated 评估。

当前无 D6-owned P0。evaluator、manifest consumer、方向化统计、门控和含 PNG 的报告接口已关闭；既有正式
报告制品重生以及系统实时/精度证据保持 P1。

## 2026-07-24 D1 协方差成对限制向量化 GAP 更新

### 已关闭

1. D6 已新增显式三轮 clean pair 入口，不从目录名推断 reference/candidate、规模或 seed。
2. manifest clean、提交绑定、配置/运行配置 SHA-256、场景版本、seed、规模、世界时间、summary
   有限值、2035 条观测、在线真值零使用、cross-build 载荷等价和进程零退出均已进入失败关闭检查。
3. D1 fusion wall、episode P95、核心 wall、外部 elapsed、RSS、实时因子和独立 scan input 已按
   每轮及聚合输出 availability/reason。核心 wall 与外部 elapsed 没有相加。
4. 准入门已形成机器判据：fusion 3/3 更快且聚合下降至少 5%，P95 均值下降，核心 wall 不恶化且
   至少 2/3 更快，RSS 聚合及任一轮增幅不超过 5%，业务/有限值/truth/exit 全通过。
5. 三轮 clean seed 1100 结果为 fusion wall 下降 `10.4411%`、P95 下降 `5.9154%`、核心 wall
   下降 `3.1417%`、外部 elapsed 下降 `3.6310%`、RSS 下降 `0.1429%`，全部门控通过，
   `d1_optimization_admitted=true`。
6. 正例、CSV 纯 LF 写入及 cross false、配置/seed 不一致、truth 非零、阶段缺失、非零退出、
   RSS 越门共 `9 passed`；D6 全量 `646 passed, 1 warning in 21.65s`。

### 仍开放 P1

1. **系统实时容量。** 候选实时因子均值只有 `0.215065`。当前不能关闭实时 P1，也不能把 D1
   单阶段加速解释为完整 D1-D7 栈实时。
2. **独立 seed 与长时稳定性。** 现有三轮都是 seed 1100 的 2.2 秒重复。多个独立 seed、长稳定
   窗口、增长率和置信区间仍未提供。
3. **精度与一致性。** 本批没有均方根误差、归一化估计误差平方、归一化创新平方、严格
   ID Switch 或航迹连续性证据。cross-build 业务载荷等价不能替代精度验收。
4. **AirSim 和目标硬件。** 本批是三维质点，不包含 AirSim、真实相机/雷达负载或目标处理器资源
   预算。

当前无新增 P0。D6-owned 显式 pair consumer、失败关闭门和报告缺口已关闭；系统实时、独立
multi-seed、精度和 AirSim/硬件容量保持 P1。

## 2026-07-24 D1 原子影子旁路兼容 GAP 更新

### 已关闭

1. D6 已在现有 runtime v1 consumer 内区分 legacy uninstrumented、legacy prepared handle 和
   显式 atomic 三类记录，历史 episode 无需迁移。
2. atomic 记录的 preparation、post-integrity、canonical/shadow digest、materialization、work
   和 failure 字段均执行精确字段及交叉关系校验。atomic 字段没有显式模式标记、半缺或混入 legacy
   字段时失败关闭。
3. historical missing 保持 unavailable。只有 atomic 记录真实存在时，其失败数和各项工作量才
   输出可用数值；D6 没有把缺失字段补成 0。
4. D6 只读消费持久化日志，不导入 D1/main，不写控制状态。accepted/rejected/atomic failure 的
   shadow 物化和工作量边界已有正负回归。
5. 2026-07-24 专项 `25 passed`，D6 全量
   `637 passed, 1 warning in 21.89s`。seed 1100 的 9 条历史 prepared-handle 记录全部兼容读取，
   9/9 integrity passed。
6. clean commit `7cc2d0c` 的 seed 1100、200 对 200、2.2 s atomic rejected-only pair 已由
   D6 从原始制品复核。9/9 integrity passed，atomic failure/materialized 为 `0/0`，
   accepted/rejected/error 为 `0/46/0`，业务非干预通过，evidence failures 为空。

### 仍开放 P1

1. 真实 atomic rejected 路径已提供；accepted 和 atomic failure 仍只有确定性 fixture，没有
   clean 实际 episode。
2. clean 单 seed control/shadow 墙钟为
   `10.735151270986535/19.449935468961485 s`，相对开销
   `0.8117989190825889`，仍远高于 `+5%` 性能门。
3. accepted treatment 为 0，独立 outcome effect 不可用，overall admission 保持 false。
4. 当前只有一个 clean seed。多 seed 性能稳定性、有效处理和结果效果仍未闭合。

当前无新增 P0。D6-owned 原子载荷兼容和真实 rejected-only 消费缺口已关闭；accepted/failure
实际路径、性能、处理效果和多 seed 证据保持 P1。

## 2026-07-23 D1 质心发布影子旁路 GAP 更新

### 已关闭

1. D6 已实现独立只读适配器，固定消费
   `audit.d1.centroid_publication_overlay_shadow` 和
   `scalable3d-d1-centroid-overlay-shadow-v1`。该适配器不导入 main/D1 runtime，不参与控制，
   不进入通用 `EpisodeMetrics`。
2. canonical/shadow SHA 可用性、相等/不同计数、`global_track_id` 序列、禁止修改、正式航迹替换、
   accepted/rejected/error、拒绝原因、双时间戳、watermark、payload、D2/D3 消费和在线真值使用
   已形成 availability-aware 指标。缺字段不补零。
3. `digest_semantics`、canonical tracks 前后 SHA、结构歧义 evidence 前后 SHA 和两层 manifest
   SHA 已进入重算校验。任一摘要变化、语义未知或重算不一致均失败关闭。
4. 每条 `evaluation_wall_time_ms` 的 P50/P95/max 已由 D6 重算，并与 v2 stage timing 交叉核对。
5. 业务非干预判据与 shadow SHA 差异分离。shadow 与 canonical 不同不能解释为正式业务输出变化；
   非干预要求 canonical/evidence 未变、编号未变、正式链未替换、禁止表面为 0、D2/D3 消费为 0、
   在线真值使用为 0。
6. 显式 control/shadow pair 接口已将业务非干预、`+5%` 总墙钟性能门、accepted treatment 和效果
   证据分层输出。任何一层通过都不会自动把 `overall_admitted` 改为 true。
7. seed 1100 开发期 shadow 已由 D6 实际消费：9 条 sidecar、46 个 decision、0 accepted、46 个
   `oosm_scan` rejected、0 error；禁止修改、D2/D3 消费、在线真值使用和编号变化均为 0，业务
   非干预通过。当前权威输入为 control/shadow prepared pair，来源提交 `2b976a7...`，两臂配置
   SHA-256 相同。
8. 2026-07-23 适配器专项 `11 passed`，scalable 与后验治理联合回归 `77 passed`，D6 全量
   `623 passed, 1 warning in 21.67s`。warning 为既有 Matplotlib 环境提示。

### 仍开放 P1

1. **性能准入失败。** control/shadow 总墙钟为 `10.712171729/19.376483415 s`，相对开销比
   `0.808828677`，高于 `+5%` 门限。影子评估 P95 为 `1532.999 ms`，payload 峰值为
   `11,275,939 B`。需要生产端优化和 clean 同输入复测。
2. **没有有效处理。** 当前 46 个 decision 全部因 `oosm_scan` 被拒绝，accepted treatment 为 0。
   现有输入只能验证拒绝路径和非干预，不能评价候选修正质量。
3. **没有效果证据。** D6 尚未收到独立 outcome effect 合同。shadow/canonical SHA 差异不能作为
   结果提升代理。
4. **证据等级不足。** prepared seed 1100 来自 dirty/development 工作树且只有一个 seed，当前
   只构成描述性开发证据。仍需
   clean/frozen、同输入、多个自然结构歧义 seed，并持久化完整阶段时序和硬件环境。

当前无新增 P0。A2 的 D6 consumer 和失败关闭合同已完成；性能、有效 treatment、结果效果和正式
多 seed 证据继续保持 P1。业务非干预通过不能关闭这些 P1，也不能判定 A2 admitted。

## 2026-07-23 observation truth v2 GAP 更新

### 已关闭

1. D6 已接受 external 与 D2 normalized 的 v1/v2 sidecar，并对 v2 三态执行字段、身份和重复冲突
   校验。
2. target、known false alarm、unknown、missing disposition 已分别输出 availability/count/reason。
   v1 无法表达的非目标计数保持 unavailable。
3. known false alarm 不进入 target mapping；unknown 强制 strict identity/IDSW fail-closed；D6
   不回填 strict IDSW。
4. runtime outcome 已把 sidecar 文件、D2 evaluation、D2 manifest 的 SHA-256 和 audit count
   交叉绑定。truth-isolated adapter 已明确仅从 D2 audit 获取计数，并保存来源摘要。
5. 缺 disposition、非法状态、identity 冲突、重复冲突、schema 和 audit 篡改均有负例。
6. 2026-07-23 新增处置及相关专项 `130 passed`，D6 全量 `586 passed, 1 warning in 21.99s`，
   scalable learning export 联调 `5 passed, 1 warning in 3.13s`。warning 为既有 Matplotlib
   `Axes3D` 环境问题。

### 仍开放 P1

1. 当前 20-seed 证据来自旧 target-only sidecar，尚未用 v2 producer 重跑，不能据此报告真实虚警和
   unknown 分布。
2. D2 strict IDSW 仍受上游混轨和 truth label 缺口阻断；处置计数与 partial lower bound 不能关闭
   该缺口。
3. AirSim 视觉虚警尚需由 evaluator-only sidecar 显式标为 known false alarm，并验证在线总线保持
   truth/disposition 为零泄漏。

当前无新增 P0。D6 consumer 代码缺口已关闭，真实多 seed、AirSim 和 strict 身份证据保持 P1。

## 2026-07-22 stage timing v2 GAP 更新

### 已关闭的 D6-owned P1

1. `scalable3d-stage-timings-v2` 已进入 scalable 3D 离线 consumer。schema、基础字段、分位字段、
   显式 availability 和不可用原因均严格校验；重复 stage 和非法分布失败关闭。
2. v2 可用分布要求 P50/P95/max 全部存在、有限、非负且有序，均值不超过最大值；不可用分布要求
   三项全空并给出原因。缺失不能补 0。
3. 无 schema legacy 保持兼容。无分位列或三项全空时保持 unavailable；三项齐全时推断 available；
   列或值半缺时拒绝。
4. 逐 episode CSV、跨 seed group aggregate 和中文 Markdown 已接入三个分位及 availability。
   聚合明确描述各 episode 内单次调用分位在 seed 间的分布，不生成 pooled quantile。
5. 正常 v2、显式不可用、legacy、半缺、非有限、顺序错误、均值上界、重复 stage 和混合可用性均有
   回归。2026-07-23 当前权威 D6 全量为 `567 passed, 1 warning in 22.96s`。相较 555 项新增的
   12 项来自部分身份合同的 3 项独立测试和 9 项篡改参数化用例。

### 仍开放的 P1

1. main 尚未提供由当前 v2 producer 生成的 clean 200 对 200 多 seed 正式输入。现有 clean
   20-seed 产物是旧计时格式，不能据此回填真实阶段 P50/P95/max。
2. “稳定窗口”必须由 main 冻结并写入场景或 manifest。D6 当前只消费完整 episode 分位，不从路径、
   时长或场景名猜测稳定窗口。
3. producer 只落盘 episode 汇总分位，没有逐调用样本。D6 可统计 episode 分位的 seed 分布，但
   pooled P50/P95/max 必须保持 unavailable。
4. 正式实验矩阵、实时容量和五米物理闭环仍按既有 GAP 保持开放。5v5 冒烟不能替代 200 对 200
   性能证据。

当前没有新增 P0。AirSim 接口未改变，`AIRSIM_INTEGRATION_PLAN.md` 检查后无需更新。

## 2026-07-22 clean 20-seed runtime v2 GAP 更新

### 已关闭的 D6-owned P1

1. main 已提供 clean commit `0d2da25c14e50f8f9a10ad47a7bd74e5c5e577fb` 的 nominal
   200 对 200、10.0 s、seed `1000-1019` 输入。D6 已独立核对 20 个主 episode，未把 80 个
   sidecar manifest 混入分母。
2. 20/20 episode 有限、工作树 clean、在线真值使用为 0、分配 hold 为 0，源进程退出码为 0。
3. 20/20 generation contract 为 verified、integrity 为 true、pending 为空。D1 generation 与
   D2 consumed generation 相等；D2 consumption 与 publication 相等；consumption 加 pre-tick
   merge 与 D1 generation 相等。
4. D1 generation 均值/范围为 `471.65 / 410-499`；D2 consumption 为
   `47.95 / 47-48`；pre-tick merge 均值为 `423.7`。D3 coverage 均值和 95% bootstrap 区间为
   `0.989606 / [0.987144, 0.991813]`。D5 binding 为 `25.95 / 9-41`。
5. D6 v6 聚合、逐 seed CSV 和中文报告已生成，failure reason 为空；输出哈希已独立复算一致。

因此，“runtime v2 尚无 clean 未见 20-seed 输入”的 P1 子项关闭。此前三 seed 正例保留为历史
接口验证，不再作为当前样本量缺口。

### 仍开放的 P1

1. 20 个 episode 全部为 `descriptive_clean_source_calibration`。实验矩阵 episode 为 0，尚无
   R0/变体完整矩阵、同 seed 配对和正式算法差异验收。
2. D2 ID switch 由 producer 声明 unavailable；D6 不把缺失证据补成 0。
3. 5 m 接近事件为 0，物理接近身份和物理拦截没有证据。D5 binding 只适用于当前 10.0 s 名义窗口。
4. D6 评估器的 `3:20.42` 和 `1,448,612 KiB` 是 main 侧进程测量，未进入可哈希输出 provenance；
   正式容量门仍需持久化运行资源字段和冻结硬件环境。

当前没有新增 P0。本批只关闭 clean 20-seed 后验代次合同输入缺口，不关闭正式实验矩阵、实时容量、
算法效果或物理闭环。

## 2026-07-22 后验代次治理 GAP 更新

### 已关闭的 D6-owned P1

1. runtime v1/v2 已分派。v1 缺少后验代次证据时保持 null/unavailable，不会被误读为 0。
2. v2 已逐条核对 D1 完整后验代次连续性，以及 D2 来源代次严格递增、不重复和先发布后引用。
3. 最终 pending、D1/D2 最终代次、D2 消费次数、实际 D2 发布数及节拍前合并数已进入交叉审计；
   pending 为空时 consumed 必须等于 D1，消费数加合并数也必须等于 D1。
4. 异常原因写入 episode failure，formal acceptance 失败关闭；D6 不参与控制，不读取在线真值。
5. 逐 seed CSV、聚合 JSON 和中文 Markdown 已包含代次、计数、完整性和 availability。
6. D1/D5 模块性能 JSON 可显式登记，但固定为 standalone descriptive evidence，不形成全栈实时声明。

### 已补充的 clean 运行证据

main 已在 clean commit `0d2da25` 上完成 nominal 200 对 200、10.0 s、seed
`42000/42001/42002`。三次 D1 final/full publication 为 `453/453`、`516/516`、`505/505`；
D2 final/consumption/publication 为 `453/48/48`、`516/48/48`、`505/48/48`；pre-tick merge 为
`405/468/457`；pending 全部为空。3/3 基础 formal provenance gate 和 integrity 通过，失败原因空，
在线真值使用为 0。

### 仍开放的 P1

本节三 seed 是首批 runtime v2 正例。后续 clean 20-seed 输入已由本页上一节复核，样本输入子项关闭。
两批输入都没有实验矩阵 metadata，正式矩阵 episode 数仍为 0。仍需完整矩阵声明和配对变体，
才能评价算法差异；clean runtime v2 合同通过不能替代正式矩阵验收。

专项 `58 passed`，D6 全量 `542 passed, 1 warning`。当前没有新增 P0。AirSim 计划已检查；本次未
改变其 producer 或指标口径，因此无需修改。

## 2026-07-22 长时三 seed 集成 GAP 更新

### 已闭合的 D6 证据缺口

1. reference `8f86192` 与 candidate `f80b5bd` 已在相同 nominal 200 对 200、10.0 s、seed
   `42000/42001/42002` 的 clean 输入上完成集成复核。candidate 三 seed 均有限、在线真值使用为 0，
   D1/D2/D3/D5/D7 最终数量相同。
2. main 的逐条语义审计没有把随机计划号直接删去。审计先验证原始 ACK 载荷 SHA-256 和运行内版本链，
   再按 occurrence/version 规范 D3 不透明 `plan_id`；owner/version/coalition/`global_track_id`/command
   等业务字段精确比较。三个 seed 均通过。
3. D6 单 seed runtime outcome 优化已获得长时集成侧证：JSONL streaming 继续全记录真值检查，D2
   identity index 保持来源重算和 freshness 语义，main 规范 D1/D2 视图避免离线身份阶段再次遍历完整
   总线。
4. 三 seed D6 aggregate 已生成：episode 3、基础 formal provenance eligibility 3、dirty 0、
   `failure_reason_distribution={}`。三个来源仍明确归类为描述性 clean-source calibration。
5. 性能口径已拆分为核心、进程、残差和 candidate 写盘后处理。核心均值下降 3.22%，进程总墙钟下降
   12.31%，峰值 RSS 下降 18.33%，进程残差下降 33.49%。candidate 后处理总量均值固定为
   `40.639988 s`；reference 缺相同制品，因此没有伪造单阶段跨提交结论。

### 仍开放的 P1

1. **正式统计覆盖。** 当前只有 3 个校准 seed，不是至少 20 个未见 seed。输入缺完整实验矩阵 metadata，
   `formal_acceptance_eligible_episode_count=3` 仅表示基础来源门通过。
2. **实时与增长率。** candidate 三 seed 实时因子约 `0.064-0.068`。D1 扫描输入/融合、D2 关联、
   D5 主动视觉/终端关联、D7 导引和模块栈仍为超线性，实时及归一化长时 P1 未关闭。
3. **同构后处理基线。** reference 没有 `scalable3d-post-run-timings-v1`。进程残差包含 D6 之外的写盘、
   离线身份、一致性和一般进程开销；需要两版同 schema 计时后才能冻结阶段预算。
4. **任务效果。** 空运行失败原因分布不等于物理成功。本批没有五米拦截、学习采用或因果效果证据，
   对应指标继续 unavailable。

当前没有新增 P0。此次只闭合三 seed clean 集成等价、真值隔离和资源量测证据，不把描述性校准提升为
最终规模化验收。文档同步后 D6 全量回归为 `530 passed, 1 warning`；warning 为既有 Matplotlib
`Axes3D` 环境问题。

## 2026-07-22 runtime outcome join 性能 GAP 更新

### 已关闭的 D6-owned P1 子项

1. 完整在线 JSONL 不再先全量物化、再递归遍历同一对象树。全部记录改为逐行唯一键解码，truth-like
   key 检查融合到 object hook，主题过滤仍位于安全检查之后。
2. 联接只保留 D1/D2/D3/D7/assignment ACK。D1/D2 以规范记录 SHA 参与 filtered-source 复算，
   不在内存保留大载荷；来源 sequence/payload 合同未放宽。
3. D2 identity 原有逐帧严格校验完成后建立一次航迹索引。594 个窗口不再重复扫描同一 1799 条
   mapping，freshness、歧义、availability 和时间边界不变。
4. 新增 baseline 业务哈希和被过滤主题 Unicode 转义真值注入回归。独立入口没有布尔跳过参数；
   `ground\u002dtruth` 仍以 `online_truth_field_present` 失败关闭。

### 证据

固定 development 输入为 200v200、2.2 s、seed 42000，input spec SHA `1e41bc47...c2c24a`；
在线操作数 63,014,782 B/3380 条，全部审计，130 条保留，3 ACK/594 窗口。`8f86192` 与 candidate
各 3 次同进程均值为总 evaluate `5.302515 -> 2.901966 s`，online load
`2.777838 -> 1.506296 s`，D2 identity `1.544734 -> 0.866780 s`，窗口
`0.451765 -> 0.028150 s`。单进程峰值 RSS 描述值为 `289716 -> 142000 KiB`。

两版 report mapping 完全相等；业务/JSON/Markdown SHA 分别为 `7325b468...cec0a7`、
`10db5198...58d3`、`97a364f1...5d76`。admission、availability、contract/control/physical、正式
reward/counterfactual/causal 和规则回退状态未变化。专项 `25 passed`，D6 全量
`530 passed, 1 warning`。

### 仍开放的 P1

1. 当前 A/B 是单 seed dirty/development 性能证据。仍需 clean/frozen、长时、多 seed、对称和非对称
   M 对 N 输入及硬件信息，才能形成正式容量与内存门限。
2. main 审计证明快速路径尚未定义或实现。独立 D6 继续重验全部记录；未来证明必须绑定文件 SHA、
   schema、真值策略版本和验证者，不能由裸布尔值替代。
3. 完整 JSON 解码和 D1/D2 双侧规范摘要仍是主要 CPU 成本。任何后续优化都必须保留真值扫描与来源
   复算，不能用性能理由降低失败关闭等级。
4. 本项不关闭 AirSim、实时控制、规划质量、五米物理效果或因果识别 GAP。

当前没有由本次优化引入的 P0。`AIRSIM_INTEGRATION_PLAN.md` 已检查；无 producer 或 runtime 接口变化。

## 2026-07-22 Scalable 3D sidecar 误发现 GAP 状态

### 已关闭的 D6-owned P0

1. `--episode-root` 原先递归接收所有 `manifest.json` 父目录。20 个主 episode 各含四类
   sidecar manifest，实际发现 100 个目录；sidecar 被当作 episode 后缺少在线日志，最终在
   `int(None)` 处中止整批评估。
2. 发现合同现要求 manifest、scenario config 和 summary 三项结构制品共存。给定 clean 批次只
   发现 20 个主 episode，80 个 sidecar 全部排除；缺 online observations 的 episode 仍会被发现，
   再由 evaluator 标记相关证据 unavailable。
3. 状态收口现按 availability 读取非负整数。缺文件、缺字段和 `None` 保持 unavailable，不补零、
   不伪造在线真值审计值。
4. clean 来源与实验矩阵 formal 分层。给定 20 episode 全部 clean，但均未声明 experiment matrix；
   最终状态为 `descriptive_clean_source_calibration`，实验矩阵 formal 仍为 unavailable。
5. 确定性测试覆盖 batch-root、显式 episode、四类 sidecar、批次根缺在线记录仍计入和 summary
   `None`。专项 `46 passed`，D6 全量 `527 passed`；CLI 2000 次 bootstrap 正常生成四类报告制品。

### 仍开放的 P1

- 本次没有增加实验矩阵 metadata、长期多 seed 趋势、位置/速度精度、身份连续性、实时性或五米
  物理闭环证据。这些输入条件沿用本文件后续开放项。
- `formal_acceptance_eligible` 继续表示基础 clean provenance 门；最终证据类别和
  `experiment_matrix_formal_acceptance_eligible` 决定是否具备实验矩阵 formal 资格，二者不得混写。

当前没有由该问题遗留的 P0。`AIRSIM_INTEGRATION_PLAN.md` 已检查；离线目录发现不改变 AirSim
日志 producer、运行时编排或控制接口，因此无需修改。

## 2026-07-22 长 Episode 观测治理 GAP 状态

### D6-owned 已关闭

- 已实现 `scalable3d-observation-governance-calibration-v1` 的只读解析、fail-closed 校验、
  availability-aware 汇总和 CSV/JSON/中文 Markdown 输出。
- 已覆盖 D1 scan OOSM 和 D2 claim ledger 的当前/峰值、淘汰、过旧、溢出、重放、时间戳冲突、
  缓冲/重排/拒绝及内存估算。
- 已将近邻召回、错误抑制、错误合并和确认时延限制为 evaluator-only sidecar；D6 不读取原始
  truth，不参与 D1/D2 控制。
- 已实现不一致 scale、重复 seed、脏正式源、缺 schema/hash/provenance、制品篡改和在线真值
  泄漏的整批拒绝。
- 2026-07-22 合成专项 `14 passed`、D6 全量 `521 passed`，覆盖 20/50/100/200 和非基线动态规模。

### Development 证据已形成

- 快速治理基准覆盖 20/50/100/200，各 5 seed、共 20 个 33.75 s episode；全部为
  dirty/development，online truth use 为 0。
- D1 每档重排 12，拒绝/过旧/溢出 0，峰值扫描缓冲 3。D2 峰值 claim/容量从
  2390/4800 增至 24170/48000，安全淘汰从 285 增至 2985，溢出保持 0。
- evaluator-only 近邻召回 1.0，错误抑制和错误合并 0，确认时延 0.25 s；四档均有明确
  availability、有效分母和 95% bootstrap 区间。
- 200 规模 D1+D2 tracemalloc 口径峰值约 58.99 MB。该值仅是快速基准的开发期内存描述。
- 实际 D1-D7 质点栈另完成 200 对 200 单 seed 冒烟：2.2 s 世界时间、60.21 s 墙钟、实时
  因子 0.0365、online truth use 为 0。该制品不与快速基准合并，也不构成正式性能证据。

### Clean/formal 治理证据已关闭

- 权威制品 `observation_governance_calibration_20260722_formal_e4d66db` 使用 `formal_only`，
  绑定 clean 提交 `e4d66db02a0b8f1b867a0e81b4a73de84588426b`，覆盖 20 episode/20 seed。
- 四档各 5 seed、每回合 33.75 s，online truth use 为 0；D6 不导入运行模块，D1/D2 控制
  修改均为 false。
- D1 重排/峰值缓冲为 12/3，拒绝/过旧/溢出为 0；D2 峰值 claim/容量和安全淘汰分别为
  2390/4800/285、6020/12000/735、12070/24000/1485、24170/48000/2985，溢出为 0。
- evaluator-only 近邻召回为 1.0、95% 区间 [1,1]；错误抑制和错误合并为 0、区间 [0,0]；
  确认时延为 0.25 s。四档全部指标为 5/5 available。
- aggregate SHA-256 为 `6fb64252292aaedd3c68d1bfea64b76496136ce6edb32add61a281d511c4ed22`；
  中文报告 SHA-256 为 `6198854b867d39fb2f1300cddeb1f75972ba8b7952361622213050115feb0827`。

### 仍开放的跨模块 P1 输入条件

1. **治理 formal 已关闭，其他证据未继承。** 快速治理矩阵已有 clean/formal 结果；单次全栈
   冒烟仍为 development。formal 标签不能用于关闭精度、AirSim、实时性或物理拦截 GAP。
2. **统计覆盖。** 快速基准每档只有 5 seed，且输入模式固定。仍需增加 seed、时长、乱序幅度、
   近邻密度、漏检和虚警条件，才能冻结 claim retention、OOSM buffer 和内存门限。
3. **全系统精度。** 快速侧车的近邻指标只评价治理基准。实际 D1-D7 全栈单 seed 制品缺少完整的
   位置/速度精度、身份连续性和关联真值侧车，相关指标必须保持 unavailable。
4. **物理闭环。** 2.2 s 全栈冒烟没有足够时间评价计划消费、导引许可和五米物理接近。需要多 seed
   长时全栈回合，才能形成拦截成功率和失败原因分布。
5. **性能门限。** 60.21 s 墙钟和 0.0365 实时因子是单机 development 描述值。尚未建立硬件配置、
   进程拆分、内存覆盖和可接受实时因子的正式门限。

D6 当前没有新增 P0 代码缺口。剩余项目依赖 main 和各 producer 提供对应证据层的正式输入；
D6 保持只读、availability-aware 和 fail-closed，不通过补零、复用治理侧车或放宽来源校验关闭缺口。

## 2026-07-22 D2 修复后 development evidence GAP 更新

### 本批已关闭

1. `active_risk` seed `1000-1019` 在 D2 重复航迹治理后已形成完整开发期输入。计划消费、导引血缘、
   物理窗、D4 adoption、配对物理差值、配对非退化和降级配对比较均为 `20/20 available`。
2. D4 区域采用从此前不可用记录恢复为两臂各 `94/94`，合计 `188/188`；control/treatment 各有
   `1960` 条控制命令实际写入隔离 world。
3. seed 1005 的离线映射为 5 条唯一 D2 中心航迹到 5 个真值目标的一对一关系，online truth use 为 0；
   整批审计的 truth 隔离、摘要完整性和 `global_track_id` 不改写均通过。
4. D6 既有消费者无需算法修改即可生成完整报告。根结果集 447 个摘要和 D6 输出 3 个摘要均通过，
   证明此前 19/20 中 seed 1005 的评估断点不是 D6 空值或映射放宽所掩盖。文档同步后 D6 全量为
   `507 passed, 1 warning`，warning 为既有 Matplotlib `Axes3D` 环境问题。

### 仍开放的 P1

1. **正式证据。** 本批是 2026-07-22 脏工作树 development rerun，不具备 clean formal 发布条件。
   需要 main 在冻结提交和 clean worktree 上按相同合同重跑；此前 clean formal 19/20 历史证据不改写。
2. **物理有效性。** 两臂 5 m 成功数均为 0，20/20 非退化和零差值只说明短窗内未退化，不证明拦截
   或降级收益。
3. **识别边界。** production runtime ACK 仍不可用，counterfactual/causal 为 `0/20 available`；
   `degradation_effectiveness_claim_allowed=false`。这些层不能由开发期 20/20 availability 关闭。

当前无新增 P0。此次只关闭 D2 修复后 active-risk 开发期证据链完整性缺口，不关闭正式发布、生产确认
或因果识别 GAP。

## 2026-07-22 隔离双臂物理结果 GAP 更新

### 已关闭的 D6-owned P1

1. 已实现版本化双臂输入清单和逐文件带外 SHA-256 验证。control/treatment 必须同 seed、同场景、同
   初态、同传感器/通信/故障日程，但 episode、world 和所有 arm 文件路径相互隔离；初始真值状态和
   时间轴由 D6 重新核对。
2. 已实现 D3 计划 identity/version/hash、隔离计划消费和 binding inventory 的严格消费者。隔离消费
   证据固定为 simulation-only；任何 `production_runtime_ack=true` 声明均按冒充生产确认失败关闭。
3. 已实现 D7 命令到 consumed plan、资源、中心航迹、command payload 和 world application 的完整血缘
   校验。只有至少两个控制周期，且每个已消费绑定有独立 `control_applied_to_world` 记录，才开放物理窗。
4. 已实现离线身份和真值隔离、NED 三维 5 m 判据、逐绑定结果、逐 seed 及聚合差值。指标包含成功数、
   最近距离、到达 5 m 时间、硬约束、错误目标接近形成的错误绑定和 treatment-control 差值。
5. 已将可选 `d4_adoption_evidence.jsonl` 纳入 input spec/arm manifest 声明一致性、路径隔离、逐文件
   SHA-256 和前后快照；旧输入为 not-declared，显式名义空文件为 not-applicable，不搜索邻近文件。
6. 已逐区域复核 D4 schema、arm/region/seed/intervention、source/applied plan、场景 lineage、candidate
   gate、isolated plan ACK 和 adoption verdict。部分区域不可用时保留 region/available/reason/
   intervention 汇总，`degraded_paired_physical_comparison` 保持 null。
7. 已实现九层 availability 和确定性 sidecar。降级比较只有在两臂完整 D4 adoption 及既有计划、导引、
   物理窗均可用时开放，且仍只称 paired isolated simulation comparison；counterfactual/causal 不开放。
8. 已关闭真实生产者 unavailable 记录兼容缺口。保留的隔离 ACK 始终独立校验；只有 verdict 声明 ACK
   available 时才绑定 verdict `ack_id`。未准入 ACK 可审计但不提升 adoption，伪造 ACK、available 状态
   矛盾和生产确认冒充继续失败关闭。
9. 合成专项 `24 passed`，D6 全量 `507 passed`，仅有既有 Matplotlib warning。main 当前 20 seed
   producer 集成专项 `1 passed`。`active_risk` 20-seed 只读复跑已正常生成 D6 报告：D4 adoption 和降级
   比较均 0/20 available，物理窗 19/20，聚合 effect/non-degradation 不开放。

### 仍开放的 P1

1. **正式证据发布。** main 已接通 D4 文件到 arm manifest 和 D6 input spec，并完成 20 seed 集成与
   `active_risk` 只读评估；当前区域均因计划不够新或场景证据无效而 unavailable，且 1/20 对缺完整
   物理窗。尚无 clean、冻结、可保留且 D4 adoption 可用的正式降级物理效果报告。
2. **实际多周期差异。** 需要近边界场景使 treatment 与 control 的计划或后续轨迹产生可辨差异；同帧
   assignment cost 改变但绑定不变的 nominal 5v5 不足以评价物理收益。
3. **D4 降级性能。** 中心失效、中心与二级同时失效、主动风险三类输入均需按预先冻结的比较问题形成
   可保留多 seed 证据。合同通过只证明采用血缘完整，不证明降级策略有效。
4. **结论边界。** 本轮不关闭 counterfactual、causal、线上 promotion、PPO、assist 或 authority。
   即使正式双臂共享全部外生日程，除非另有冻结的识别假设和实验设计，这些层仍保持 unavailable。

当前无新增 P0。关闭的是 D6 只读消费、完整性验证、空值和报告合同，不是 D3/D4 学习策略性能 GAP。
`AIRSIM_INTEGRATION_PLAN.md` 已检查；本轮未改变 AirSim runtime 或生产 ACK 接口。

## 2026-07-22 D3/D4 保留 seed v1/v2 GAP 更新

### 已关闭的 D6-owned P1

1. 保留 seed consumer 已从 v1-only 改为顶层 schema 严格分派，历史 v1 输入、默认 API 绑定、状态与
   availability 结构继续通过；v2 有独立 sidecar/provenance schema 和 CLI profile。profile 现显式
   绑定预期 source schema，同 schema 摘要覆盖可用，跨 schema 失败关闭。
2. v2 权威输入的 checksum、manifest artifact SHA、20 条 lineage、seed `1000-1019`、source commit、
   dirty/truth/共享标志、D3/D4 40 arm、pair input/bundle identity 已独立复核。
3. D3 safety shell v2/config SHA 的 40/40 arm 绑定已关闭；20/20 treatment applied，D6 从 20 条 frame
   重算同帧规则基准 cost、安全/churn 和 inference latency，并与 receipt/report 闭合。
4. D4 arm evidence v2、confidence/OOD/latency/finite/failure 分门逻辑和顶层 manifest gate summary 已
   关闭严格消费缺口。重算结果为 confidence 0/20 pass，其余四门 20/20，safe adopted 0、fallback 20。
5. availability 已区分 offline assignment comparison 与 physical outcome。前者在 D3 v2 可用；后者及
   runtime ACK、paired effect、counterfactual、causal 均为 null/unavailable。测试覆盖 gate/schema/
   safety hash/summary 篡改。合同完整 v2 fixture 已消除 clean clone 对 ignored output 的关键路径依赖；
   正式 bundle 仍作条件性复算。D4 两个 P95 已分别标注 nearest-rank=`2.241315 ms` 和 linear
   interpolation=`2.264415 ms`。sidecar/provenance schema binding 和同时间戳四文件逐字节复生均已
   纳入验收。专项 `18 passed`、无权威输出路径 `16 passed`、D6 全量 `483 passed`。

### 仍开放的 P1

1. **物理结果与效果。** D3 虽在隔离 assignment 层 20/20 applied，但没有 runtime ACK 或采用后物理
   状态窗；D4 safe adoption 仍为 0。paired physical outcome/effect/non-degradation 不能计算或补 0。
2. **策略有效性。** 同帧 assignment cost/safety/churn 无退化不证明候选策略在轨迹、终局或外部场景
   有效，也不支持 promotion、PPO、assist 或 authority。
3. **降级评估。** 本批是 nominal 5v5；D4 low-confidence fail-close 不关闭通信、节点、资源故障条件下
   的降级策略性能 GAP。

profile-bound v2 canonical 位于
`research_modules/d6_evaluation_metrics/outputs/reserved_seed_interventions_nominal_5v5_1000_1019_formal_7891296_d6_profile_bound_v2_audit_20260722/`。
四文件 SHA 为 `f3852251...71c3b`、`bd80c1dd...f9949`、`0d50a95d...f7dc6`、`db4af357...7b87c`，
sidecar 内容 SHA 为 `c02a345c...5d2d`。旧 v1/v2 目录未覆盖。
`AIRSIM_INTEGRATION_PLAN.md` 已检查；本次没有 AirSim runtime、episode 或控制接口变化，因此保持不改。

## 2026-07-21 D3/D4 保留 seed 隔离执行 GAP 更新（历史 v1）

### 已关闭的 D6-owned P1

1. 已实现可复用的 D3/D4 保留 seed 独立只读 consumer 和 CLI。输入只通过显式目录及带外
   `SHA256SUMS`、顶层 manifest、源提交和 D3/D4 bundle digest 绑定；输出不得位于 producer 输入树。
2. 已重新校验五个 `SHA256SUMS` 成员、manifest 内全部 artifact SHA、20 条 source lineage 和审计
   前后六文件快照。seed 精确为 `1000-1019`，source commit 为
   `6d5bfead31d53258b020a5f157b2ad5e7f25ee35`，dirty、nonfinite、online truth use 均为 0；
   同源/随机/通信/故障四类标志均为 `20/20`。
3. 已从 D3 arm/receipt 和 D4 specification/evidence 独立重算各 40 arm、20 control/20 treatment、
   pair input/lineage identity、bundle digest identity、回退原因和时延，不采用 producer 汇总替代明细。
4. 已固定 outcome availability sidecar：execution receipts 可用；runtime ACK、physical outcome、
   counterfactual、causal 不可用。零采用时 paired outcome/effect/non-degradation 固定为
   `available=false,status=unavailable,value=null`。
5. 已原子生成 JSON sidecar、中文 Markdown、provenance manifest 和 `SHA256SUMS`。专项 `7 passed`、
   D6 全量 `472 passed`，输出校验和复算通过，输入摘要前后不变。

### 真实结果与证据等级

- D3 treatment 应用 `0/20`，`20/20` 因 `out_of_distribution` 回退；control 为 unchanged 15、
  held-by-hysteresis 3、replan-ACK-no-change 2。D3 treatment receipt latency 的 20 条记录可用且均为
  `0 ms`，表示失败关闭路径记录，不表示效果为 0。
- D4 treatment 安全采用 `0/20`，`20/20` 因 `candidate_threshold_or_finite_gate_rejected` 回退；
  candidate latency mean/P95/max 为 `8.291408/35.255481/42.301505 ms`。
- D3 bundle manifest/state 绑定为 `a9213d...14c0`/`e3da9f...e0b2`，D4 为
  `dad2ad...5c9`/`3da036...f62`。bundle 文件不在输入目录内，故这是 digest identity binding，
  不是 D6 对模型文件的重新哈希。

### 仍开放的 P1

1. **实际采用。** 两类候选路径实际采用均为 0。失败关闭得到验证，但没有候选动作进入后续物理状态。
2. **运行时与物理结果。** 当前没有严格绑定的 runtime ACK、采用后状态窗或终局结果；paired outcome、
   effect、non-degradation、counterfactual 和 causal 不能计算，也不能用回退后 control/treatment 同值补 0。
3. **策略有效性与权限。** 本批不证明 D3/D4 候选策略有效，不关闭 promotion、PPO、assist、authority
   或外部泛化缺口。后续必须先取得非零安全采用和严格绑定的多 seed 物理结果，再按冻结门限复审。

下列 v1 输出是 schema binding 序列化前的历史已发布制品；当前 consumer 重新生成 v1 会产生
profile-bound provenance，不把旧哈希作为当前可复生值。历史 D6 输出为
`research_modules/d6_evaluation_metrics/outputs/reserved_seed_interventions_nominal_5v5_1000_1019_d6_audit_20260721/`。
审计时间 `2026-07-22T04:06:26Z`（本地日期 2026-07-21）。当前无新增 P0；关闭的是 D6 consumer、
证据完整性和 availability 表达缺口，不是上游候选性能 GAP。

## 2026-07-22 D5 paired-shadow 权威 v2 GAP 更新

### 已关闭的 D6-owned P1

1. 已实现权威 v2 独立消费者。v2 report/lineage、held-out corpus/evaluation、冻结模型包、D5 实现源码
   和 superseded report/lineage 均要求显式路径和带外 SHA-256。
2. 已核验 2702 项 corpus inventory、7 个实现文件和全部关键输入；审计前后 2718 项输入集合哈希一致，
   D5 冻结报告、语料、模型和旧证据没有被修改。
3. 20 seed、45 cell、900 lineage、74024 条已标注候选边完整。每帧图只加载一次，规则/模型两臂的
   graph/candidate/label identity 均为 1.0，模型增删候选边为 0。
4. 逐 seed、逐 cell 和总体边级/簇级计数及延时由 D6 重算并与 producer 对齐。45/45 cell 无质量退化；
   同相机候选边、未标注边、online truth、`global_track_id` 改写和输入改写均为 0。
5. paired-shadow 层已从 `unavailable` 更新为 `complete`。研究影子资格为
   `qualified_with_synthetic_separability_caveat`，不是线上准入。

### 仍开放的 P1

1. **外部泛化。** `shared_global_track_count` 恒为 0，中心投影马氏距离单特征 F1 仅 0.370482，未发现
   中心身份线索直接决定标签；但三个尺度/角速度差特征近确定性可分，最强特征在 35/45 cell 达到门限。
   当前满分只能作为合成语料上的结果。
2. **去捷径复验。** 仍需随机化或移除近确定性合成特征，增加独立相机噪声、外参漂移、目标外观与运动
   扰动，并在 no-center-feature 条件下重复同 seed paired shadow。
3. **线上权限。** 外部泛化和跨模块真实采用证据未闭合。G1/PPO/assist/authority 均保持 false，规则
   回退保持 true；本次审计不改变模型 promotion 或默认运行路径。

输出为 `research_modules/d6_evaluation_metrics/outputs/d5_paired_shadow_e39a54d/`。专项测试
`8 passed`，D6 全量测试 `465 passed`；摘要和输入不变性检查全部通过。唯一警告为既有 Matplotlib
`Axes3D` 导入问题，不影响本次离线审计。

## 2026-07-21 D5 clean 图数据分层准入 GAP（v2 前置状态）

### 已关闭的 D6-owned P1

1. 已实现八类显式 D5 clean 制品和逐文件带外 SHA-256 消费，输入清单也要求独立 SHA-256；不依赖
   ignored output 的隐式路径。
2. 已复核文件/内容摘要、formal/supplemental 来源、60/20/20 seed、保留 seed 零重叠、正负边、
   未标注 0、45 cell、dirty=false 和来源未改写。篡改、泄漏、门限降低和伪模型报告均失败关闭。
3. 已形成数据支持、训练来源、模型内部测试、保留 seed、paired shadow 五层输出。该段记录 v2 生成
   前的状态；当前各层状态以上一节权威 v2 审计为准。
4. 未来模型 bundle 已固定权重 SHA、配置 SHA、训练来源 SHA、测试指标、45 cell 和 latency 合同。
   内部测试通过也不能越过保留 seed 和 paired shadow 门。
5. 输入 schema 已升级到 `d6.d5-clean-graph-inputs.v2`：held-out evaluation report/manifest 为成对
   可选制品；v1 只兼容原无 held-out 结构，不接受新增字段，也不做邻近路径发现。
6. 已实现 `d5.tracklet-heldout-model-evaluation.v1` 与 `d5.tracklet-heldout-corpus.v1` 的独立严格
   消费。调用方 SHA、D5 newline-canonical 内容 SHA、seed `1000-1019`、45 cell、900 episode、
   model weights/config、held-out manifest、冻结 validation 温度/阈值及零权重更新均有交叉绑定。
7. online truth、同相机边、未标注边、`global_track_id` 创建/换绑和伪造 authority 任一非零/true 均
   拒绝。结构合法的门限失败保留为 `held_out_seed=failed`、producer `fail_closed`，不会伪装成输入
   不可用；缺成对制品仍明确为 `unavailable`。
8. 2026-07-21 专项合成合同测试 `34 passed`、D6 全量 `457 passed`，仅有既有 Matplotlib warning。
   合成正例不构成正式 900 帧性能证据。

### 历史开放项处置

真实冻结权重、内部测试、held-out 和同 seed paired shadow 已形成并由上一节关闭核算缺口。它们没有
关闭外部泛化、真实运行采用、因果/反事实和线上权限缺口；这些项目不得由合成满分回填。

## 2026-07-21 运行时结果联接 GAP 更新

### 当前判断

本轮未发现新的 D6-owned P0 阻塞。运行时计划确认到离线观测结果的严格消费者已经实现并完成专项、
全量和真实 3v3 双 occurrence 接口复核。该能力关闭了“D6 没有公开 API 校验 plan ACK、D2 身份旁路和物理状态窗”
这一 P1 实现缺口，但没有关闭强化学习正式准入。

### 已关闭的 P1 子项

1. 11 类输入均要求显式路径与带外 SHA-256。D2 evaluation/manifest 的内部来源哈希还要与 D1/D2
   filtered source、观测真值标签、identity evidence 和完整在线日志逐 sequence/载荷一致。
2. D3 plan、D7 guidance 与 main ACK 的 sequence、规范 payload SHA、plan id/version 和 binding 集合
   已形成失败关闭联接。同 plan identity 的合法 refresh 按 ACK occurrence 留痕；重复 sequence、
   同版本执行签名漂移、旧版本、错误版本、额外 binding 和 ACK 越权声明 outcome/reward 均有测试。
3. 每个资源的 binding 已按相邻 ACK 切成非重叠观察窗。D6 输出 D2 lineage 映射可用性、三维距离、
   进展、正确/错误目标 5 米事件以及 D3/D4 原始证据。
4. 有界配对进展诊断只在 accepted、D7 applied、非 hold、唯一身份映射和完整状态窗下可用。该值明确
   标记 `formal_reward=false`、`causal=false`、`counterfactual=false`。
5. 22 项专项和 423 项 D6 全量测试通过。真实 main 3v3、seed=70、1.2 秒输入形成 2 个 ACK
   occurrence/6 个 binding window，online truth=0，三类学习权限均为 false。

### 仍开放的 P1

1. **main episode 接线。** main 还没有在每个 episode 自动生成 11 项 hash spec、调用本 API、登记
   输出文件及 SHA。当前公开 API/CLI 可用，生产接线不属于 D6-owned 路径。
2. **正式可归因结果。** 当前值是单事实轨迹上的 observed pair diagnostic。缺同 seed paired formal
   shadow、动作实际采用的跨 episode 归因、学习与规则差异、保留 seed 和多 seed 置信区间。
3. **正式 PPO 数据。** 仍缺 on-policy log probability/value、冻结 reward 定义和保留 seed 非退化
   验收。当前 `ppo_allowed=false`、`assist_allowed=false`、`authority_allowed=false`、规则回退强制。

### P2 边界

正式 P1 配对和保留 seed 未完成前，不进入奖励塑形、因果模型或策略训练。当前有界诊断可以用于发现
距离闭合失败和错误目标接近，不能作为训练回报直接写回 D3。

## 2026-07-21 跨模块学习数据联合准入 GAP

### 已关闭的 D6-owned P0

- 已实现独立的跨模块只读审计入口和 CLI，显式接收 training/shared registry、D3 formal manifest、
  D4 formal manifest 与独立 canonical view、D5 tracklet/active-vision formal
  manifest/view/readiness、D4/D5 supplemental summary，以及 D3/D4/D5 producer 全样本审计和调用方
  提供的三个审计文件 SHA-256。生产者制品保持只读，报告不记录输入绝对路径。
- 已实现 schema、来源身份、文件/内容 SHA-256、dirty source、missing input、seed assignment 和 reserved
  leakage 的失败关闭校验。负例覆盖 schema/hash 篡改、错误切分、保留 seed 泄漏、formal/supplemental
  混用、synthetic ACK 冒充 runtime ACK、unavailable 标签补零和外部 D4 view 哈希不一致。
- 已将 formal observation corpus、supplemental rule-teacher curriculum、offline evaluator labels 和
  runtime ACK evidence 分层。D4 独立 formal view 的文件 SHA-256 为
  `73a365d32b0439fbf805f40ea7941b8e992fe4c68687cbc5496704f230440b11`，不会被 D4 supplemental
  canonical view 替代。
- 已禁止报告输出目录等于或位于正式 generation 根下，检查发生在目录创建和文件写入之前；D6 自有
  outputs 路径保持可用。
- 已对 D3/D4/D5 审计复算 file/content SHA，交叉核对 schema/date/purpose、expected/actual binding、
  binding checks、完整计数、canonical 60/20/20、零违规、availability 和 admission。D3/D4 的 file/
  content SHA、schema、计数、binding、status、availability/admission 篡改均有稳定错误码并失败关闭。
- 已输出中文 JSON/Markdown 准入报告。2026-07-21 专项 `37 passed`、D6 全量 `401 passed`；仅有既有
  Matplotlib `Axes3D` 环境 warning。

### 真实证据与当前准入

- 正式观测数据为 900 episode、100 个训练 seed；规范 train/validation/test=`60/20/20`，保留 seed
  `1000-1019` 泄漏为 0，online truth 使用为 0。
- D4 supplemental 为 100 episode/300 frame，hold 100、request-replan 200、nonzero quota 200、
  transfer 100；canonical episode=`60/20/20`、frame=`180/60/60`。D5 supplemental 为 100
  episode/800 segment/1200 sample，intent
  `200/600/200/200`，wide/zoom=`1000/200`，interceptor/recon=`600/600`。
- D5 tracklet 480 条 candidate edge 中正标签 362、负标签 19、未标注 99。离线关联标签状态为
  `partial`，`labeled_count=381`、`complete=false`，不具备完整监督标签口径。
- D5 synthetic ACK applied/rejected/missing 各 400，只是确定性故障注入覆盖，runtime ACK attribution
  仍 unavailable。reward、outcome、counterfactual 和 causal 仍 unavailable；D5 图关联 paired shadow
  已由顶部权威 v2 审计关闭，但不替代这些控制归因证据。
- D5 supplemental BC 的 producer 全样本审计已完成：100 episode、1200 sample，canonical episode=
  `60/20/20`、sample=`720/240/240`；online/offline/descriptor 各 100 个，`302/302` 个登记制品通过
  SHA-256，有限特征 `1200/1200`。online truth、保留 seed、dirty episode 和 D5 创建、改写或换绑
  `global_track_id` 均为 0；四类离线标签保持 unavailable 且没有补零。
- D3 全样本审计覆盖 900 episode/1604 frame/3,658,815 edge/117,304 selected action/43,905,780 finite
  value。D4 覆盖 formal 900/1798/14384 和 supplemental 100/300/1200。三份审计的文件 SHA-256 为
  `62a47df8...17fb`、`4245f1db...9e46`、`9a036535...2d3`，内容 SHA-256 为
  `954f3e96...1867`、`94f4f4bf...3e7f`、`a11b6559...50dd`。
- 当前状态为 **D3/D4/D5 full-sample complete**、**跨模块 structural full-sample complete**、
  **overall admission partial**。PPO、assist 和 authority 均关闭，规则回退强制启用；没有模型收益证据。

### 仍开放的 P1 前置条件

1. producer 需要持久化真实动作采用、plan/coalition/communication 版本绑定、applied/rejected runtime
   ACK、后续反馈和明确终局结果。synthetic ACK 不能用于关闭该条件。
2. reward/outcome 需有明确归因窗；PPO 还需 on-policy log probability/value。counterfactual/causal 需
   同初态配对重放、随机干预或等价识别证据。
3. D5 图关联同 seed paired shadow 和保留 seed 已完成；仍需去合成捷径的外部泛化复验，以及 D3/D4
   真实动作采用和反事实证据。条件未关闭前，不开放在线 assist、控制 authority 或 PPO。

## 2026-07-21 历史 canonical seed split GAP 状态

以下内容记录 detached canonical views 生成前，直接审计原始 manifest 得到的 mismatch。当前准入状态
以上一节为准；原始 900 episode manifest 未被改写。

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

## 2026-07-23 D2 部分身份诊断消费 GAP

### 已闭合的 D6-owned 项

1. `d2.scalable3d_partial_identity_diagnostics.v1` 已接入 truth-isolated adapter；旧 v1
   evaluation 无 partial 时继续读取并给出独立 missing reason。
2. mapping/frame/adjacent-transition coverage、IDSW lower bound、anchor interval count 和
   exclusion reason 已进入 DTO、逐 seed CSV、aggregate JSON 和中文 Markdown 的独立栏。
3. strict IDSW 与 partial lower bound 的数据路径和 availability 完全分离。D6 固定声明不回填
   strict、不发布 upper bound、不参与控制。
4. sidecar schema/scope/denominator、有限值、availability/reason、计数守恒、lower-bound 范围、
   audit/config 均已 fail-closed 校验。
5. identity manifest schema/episode/availability、evaluation SHA-256、D1/D2/truth/evidence 四类
   source hash 和 truth-isolation provenance 已绑定。manifest 缺失、错版本、hash 不符或制品
   篡改均有明确 reason。
6. 2026-07-23 专项 `26 passed`、D6 全量
   `567 passed, 1 warning in 22.96s`，零测试失败。
7. clean `4ac3bb2` 的 nominal 200 对 200、seed 1000、10 秒真实 producer episode 已只读消费。
   manifest/evaluation 及四个实际源文件摘要全部匹配；strict IDSW 因
   `multiple_truth_targets_for_global_track` 保持 unavailable。partial mapping/frame/transition
   coverage 为 `8906/9038`、`3/48`、`0/9400`，lower bound 为 7/385 anchor intervals，
   strict 未回填且 upper bound 未生成。
8. clean `5263e2b` 的 seed `1000-1019` 已形成 nominal 200 对 200、20 episode 描述性汇总。
   manifest 链、producer 重建与持久化记录一致性、在线真值隔离均为 20/20。partial
   mapping/frame/transition micro coverage 为 `178531/181110`、`103/959`、
   `1149/187800`，lower bound 合计 199/15215 anchor intervals，并继续保持 strict/partial
   分栏。

### 仍开放的 P1

1. nominal 200 对 200 的 20 seed partial evaluation/manifest 已可发布为描述性批量证据。
   main/D2 尚未生成正式 5/20/50/100/200 多规模、困难场景和长时输入；当前 coverage、
   blocker、anchor exclusion 和 lower-bound 分布不能外推。
2. 完整 sidecar 下的 strict IDSW/continuity 多 seed 统计仍开放。partial lower bound 不能关闭
   strict unavailable，也不能作为 promotion 或控制证据。
3. 真实 AirSim、遮挡/杂波/漏检/OOSM、目标密度变化和长时 episode 的 coverage 稳定性尚未验证。
4. D6 已生成独立 20 seed truth-isolated bundle。main 仍需把 partial 分栏纳入最终统一
   scalable 3D 总报告，并冻结跨提交 reason taxonomy；D6 不复制 producer 私有 frame mapping。

当前无新增 P0。D6 consumer GAP 已关闭，数据与系统性能 P1 保持开放；P2/P3 外部 evaluator
状态不变。

## 2026-07-23 D2 identity commitment v2 消费 GAP

### 已闭合的 D6-owned 项

1. evaluation v1/v2 精确分流和 v1 commitment unavailable 兼容已实现；不存在 missing-to-zero。
2. v2 embedded evidence bundle SHA、四类 source provenance、all/observed denominator、
   coverage、state/reason、blocker/watermark/overflow 和零 binding violation 已独立复算。
3. typed commitment evidence 已进入 episode DTO、逐 seed CSV、aggregate JSON 和中文
   Markdown；专用 aggregate 使用 micro denominator 与 count-weighted summary。
4. strict IDSW 只消费 D2 值，跨 uncommitted gap 不回算；普通 lineage missing 继续
   fail-closed unavailable，partial lower bound 也不回填 strict。
5. runtime plan outcome join 已接受 evaluation v2。显式 uncommitted 只使命中 binding
   identity/state/距离诊断 unavailable，保留 reason/details 且 truth 为 null；合同篡改仍拒绝。
6. 合法、兼容、缺字段、篡改、负年龄、overflow、binding 违规、跨 gap、报告和 runtime 专项
   已覆盖。2026-07-23 D6 全量 `598 passed, 1 warning in 21.44s`，零失败。

### 2026-07-23 已补充证据

1. main 已在 clean commit `909669b2eefeab2ce30c8ac389d6bf9c0a8cbabc` 将 seed 1100
   baseline/candidate 的 `identity_commitment_by_track`、v2 evidence、evaluation、audit 和
   manifest 原子持久化。D6 v2 consumer 和独立审计已实际消费，不再是 fixture-only。
2. baseline strict IDSW、track continuity、coverage continuity、commitment coverage 为
   `9/0.865/0.870/1.0`；D2/D3 数量为 `203/200`。
3. candidate commitment coverage 为 `1714/1787=0.9591494124`，1714 committed、69 hold、
   4 after hold。source/candidate binding violation 为 `0/0`，在线真值隔离通过。
4. candidate 三个恢复航迹的 measurement timestamp 与评分帧相差 `0.9308153039 s`，超过固定
   `0.9 s` lineage window。strict identity metrics 按合同 unavailable；D6 未扩大窗口，也未
   回填 strict IDSW。D2/D3 数量为 `201/197`。

### 仍开放的跨模块 P1

1. 结构歧义候选的 promotion gate 仍失败。上游需在固定 `0.9 s` 合同内恢复 strict identity
   availability，并解释 D2/D3 数量下降；D6 不通过改评分口径掩盖该问题。
2. seed 1101/1102 已停止。单 seed 候选准入通过前，不启动该候选的多 seed 性能统计。
3. 真实 AirSim、多 seed、多规模、困难谱系、长时 blocker/watermark/overflow 分布及最终统一
   scalable 3D 报告仍开放。

GAP 状态：D6 consumer 和 main v2 真实 episode 持久化子项已关闭；候选算法准入与系统性能 P1
保持开放。当前无新增 P0，外部 evaluator P2/P3 状态不变。

## 2026-07-23 发布新鲜度 A/B 与 partial 分类绑定 GAP

### 已闭合的 D6-owned 项

1. 已独立消费 clean commit `65568579c99e4ef9939f0519f66c46d3076ef035` 的 seed 1100
   baseline/candidate。episode identity、identity evaluation/manifest SHA、D6 manifest
   来源摘要和在线真值隔离均通过。
2. 新 publication-stale recovery reason 已进入 commitment reason/recovery-blocked count。
   candidate 计数为 3；1711 committed、69 hold、7 after hold，coverage
   `0.9574706212`，source/candidate binding violation 为 `0/0`。
3. strict-unavailable 消费缺口已关闭。baseline/candidate 的 strict IDSW 为 `9/3`，
   track continuity `0.865/0.8266667`，coverage continuity `0.870/0.8283333`，
   duplicate assignment `0/0`，均保持 producer availability。
4. 发现并修复明确 D6-owned partial 绑定回归。D2 audit 对
   `unavailable/excluded/uncommitted` 分栏，partial 将三者合并；D6 现按分类和校验并保持
   total 守恒。baseline 的 `230+4+0=234`、candidate 的 `218+2+76=296` 均通过。
5. 修复后两组 partial provenance 均 verified，IDSW lower bound `9/3`，未回填 strict。
   新增生产分区正例和分类缺口负例；D6 全量
   `600 passed, 1 warning in 21.55s`。

### 仍开放的跨模块 P1

1. 当前制品没有持久化 `identity_commitment_recovery_config` 完整快照。main/D2 需将
   schema、config version、门控开关、年龄预算、时钟和 stale behavior 纳入公共
   runtime profile/manifest；D6 再做 SHA-bound 配置消费。现在只能验证门控行为，不能独立
   证明配置版本和 `0.9 s` 预算。
2. 原 A/B 目录的 `d6_truth_isolated/episode_record.json` 由修复前 consumer 生成，partial
   仍显示 mismatch。main 应在集成 D6 修复后写出新的派生 bundle，不覆盖原 clean 证据目录。
3. 结构歧义候选仍未准入。D2 tracks `203 -> 201`、D3 assignments `200 -> 197`、
   track continuity 下降 `0.0383333`、coverage continuity 下降 `0.0416667`。seeds
   1101/1102 继续停止。
4. 真实 AirSim、多 seed、多规模、困难谱系、长时 recovery/blocker/overflow 和最终统一
   scalable 3D 报告仍开放。

截至该轮无新增 P0。D6 partial consumer 回归和 strict availability 子项已经关闭；算法准入、
旧制品配置 provenance 与正式性能证据仍为 P1。配置 consumer 的后续关闭状态见下一节。
P2/P3 外部 evaluator 状态不变。

## 2026-07-23 Manifest v2 配置谱系 GAP 更新

### 已闭合

上一节“D6 再做 SHA-bound 配置消费”已完成。D6 现在：

1. 接受 `scalable3d-offline-identity-evaluation-manifest-v1/v2`；
2. 对 v2 复算完整 recovery config 的规范 SHA-256；
3. 验证配置 schema、非空快照、记录数、`d2_record_count`、consistency/source 声明；
4. 验证 online D2 JSONL 文件 SHA 同时匹配调用方、identity evaluation 与 manifest；
5. 逐条比较 `payload.association.identity_commitment.recovery_config`；
6. 在 episode JSON、CSV、batch provenance 和 runtime admission 中暴露验证结果；
7. 对 v1 保留 strict/partial 指标，并将新增谱系标为 unavailable；
8. 对 v2 篡改、缺字段、错误摘要、帧间漂移和计数不符失败关闭。

专项 `83 passed`，D6 全量 `611 passed, 1 warning in 21.55s`，验收零失败。D6-owned 配置
谱系 consumer P1 关闭。真实 main 三维质点 3 对 3、seed 70、1.2 秒生产接线用例同时通过，
manifest v2 绑定 3 条 D2 发布；该证据不是 AirSim 或 200 对 200 性能结论。

### 仍开放 P1

1. 结构歧义候选仍需先解决 D2/D3 数量与 continuity 退化，再决定是否恢复 seeds
   1101/1102。
2. 真实 AirSim、多 seed、多规模、困难谱系和长时 recovery/blocker/overflow 证据未完成。

当前无 D6-owned P0。P2/P3 外部 evaluator 状态不变。旧 A/B 制品的配置谱系不可用属于历史
证据限制，不应重新归类为 consumer 缺口。

### 最终端到端证据更新

main 已在 detached clean `ff881316243ff5a2991a4659ab78637ed625d123` 上完成 seed 1100
baseline/candidate 重跑。两组 identity manifest 均为 v2，配置 SHA 均为
`sha256:bd8e362ec4ca128ed902826750b26d862286770d3c0c4d0b75960a50911a201a`，
配置记录数、D2 记录数和在线 JSONL 实际记录数均为 9。D6 episode 与 runtime provenance
均 verified，关闭“新 producer episode 尚未端到端绑定”的 P1。

最终 baseline/candidate 的 strict IDSW 为 `9/3`，track continuity 为
`0.865/0.8266667`，coverage continuity 为 `0.870/0.8283333`，D2/D3 数量为
`203/200` 和 `201/197`。partial lower bound 为 `9/3`，未回填 strict；在线真值使用和两类
binding violation 均为 0。

GAP 分类更新：

- **已关闭 P1**：恢复配置快照、规范 SHA、online D2 records SHA、逐条配置和 D6
  episode/runtime provenance 的端到端绑定。
- **仍开放 P1**：结构歧义保活算法准入。candidate 未通过 D2/D3 可用性与 continuity
  非退化门，保持默认关闭。
- **仍开放 P1**：AirSim、多 seed、多规模、困难谱系和长时 recovery/blocker/overflow
  性能证据。

按冻结停止规则未运行 seeds 1101/1102、10 秒或 20-seed 矩阵。当前无新增 D6-owned P0。

## 2026-07-23 身份承诺执行门 clean 单种子 GAP 更新

### 已关闭

1. D6 已独立消费 clean commit `7e15dac9cdaf6743999dfe045a70676fd31a17d6` 的
   `hold_only` 与 `hold_plus_centroid`。manifest、summary、identity evaluation、
   truth-isolated、runtime outcome 和 online observations 的 episode 与来源摘要一致。
2. 当前 D6 API 从原 producer 制品重建的 truth-isolated episode record 完全一致，4 个派生
   文件逐字节相同；runtime outcome JSON 也逐字节相同。
3. 两臂 strict IDSW/track continuity/coverage continuity 为
   `3/0.8266666667/0.8283333333`，mapping 为 `1491/218/76`，commitment coverage
   `0.9574706212`。duplicate assignment、online truth use 和两类未承诺绑定违规均为 0。
4. `t=1.0 s` 的 11 个未承诺目标触发 D3 `v1 -> v2` 强制升版和迟滞绕过。版本 2、版本 3、
   D5 主动视觉/终端绑定、D7 导引和 runtime control 对该集合的继续执行均为 0。
5. 候选组 46 个质心候选全部拒绝，原因 `oosm_scan=30`、`unbalanced_component=16`。
   该结果证明零 treatment 下的失败关闭和安全门，不证明算法收益。

### 仍开放 P1

1. 需要 `applied component count > 0` 的同输入 A/B，才能评估质心修正的 IDSW、连续率、
   D2/D3 可用性和非退化门。
2. treatment 门通过后仍需多 seed、长时、困难谱系和 AirSim 证据。
3. 本次 D3/D5/D7 未承诺继续执行计数由 D6 专项只读审计得到，尚未成为标准派生 JSON/CSV
   字段。
4. 通用 scalable 3D 汇总与 truth-isolated strict identity 仍为两条输出。后续统一报告需
   显式联接并保留来源 availability，不能覆盖在线 summary。

GAP 状态：当前无 D6-owned P0。clean 单 seed 安全合同证据已闭合；有效 treatment、自动化
门控统计和正式多 seed/AirSim 性能证据保持 P1。P2/P3 外部 evaluator 状态不变。

## 2026-07-25 正式 R0 后验跳过 GAP 更新

### P0

原始正式提交存在跨模块 runtime P0。D2 finalization 的输入签名没有覆盖状态、协方差和
有效时刻，5 个 delayed-noisy episode 因此把变化后的 D1 最终后验当作 no-op，跳过消费后
仍清空 pending。
规模和 seed 为 5v5 `1000/1005/1008/1018`、20v20 `1009`。最大差值范围为状态
`0.043312-0.415096`、协方差 `1.515708-22.623443`、时刻 `0.018609-0.255046 s`。

该 P0 不属于 D6 控制代码所有权。D6 已补齐检测并保持 fail-closed，v10 已提交为
`8e955f3`。main/D2 修复已形成 clean source commit `98d01bf`。5 个异常 cell 的 dirty
定向回归已经通过。正式 R0 已在后继 clean source `1e5ed8d` 上启动，当前完成 135/900。
旧 895 个通过项不能与此前 dirty 工作树的 5 个修复项或新批次局部结果拼接。

### D6 状态

D6 v10 对 declared skip 增加完整公开后验审计，并要求上游版本化完整 D2 输入摘要。当前摘要
尚未发布，5 项仍为
`descriptive_or_incomplete_evidence`。900/900 只关闭执行范围完整性，正式 clean evidence
为 895/900；`formal_matrix_complete` 仍为 false。D6-owned 解析 P0 已关闭。

验证结果：D6 全量 `894 passed, 1 warning in 85.66s`，5 个原始异常 episode 逐条重评均
保持 generation integrity、基础 formal eligibility 和矩阵 formal eligibility 为 false。

### 定向修复复核

main 已修复 runtime finalization，并在 dirty 工作树中重跑原 5 个异常 cell。D6 v10 合并
结果确认五项 generation contract 全部 `verified`，具体为：

- D1 final 与 D2 consumed 分别为 `27/27`、`13/13`、`9/9`、`13/13`、`14/14`；
- consumption 与 publication 分别为 `7/7`、`6/6`、`5/5`、`5/5`、`6/6`；
- pre-tick merge 分别为 `20`、`7`、`4`、`8`、`8`；
- skip 全为 0，pending 全为空，generation integrity reasons 全为空。

跨模块 runtime P0 现处于“代码已进入 clean source、定向开发证据通过、完整 R0 待正式重跑”
状态。五项的
`repository_dirty=true`，D6 正确保留为 5 个
`descriptive_or_incomplete_evidence`，formal eligibility 为 0/5。旧 clean 895 项不得与
该批次拼接。修复已由 clean source commit `98d01bf` 固化，后继 source `1e5ed8d` 的完整
R0 已执行 135/900，但尚未完成。D6 继续保持旧正式结论 895/900，900/900 formal
acceptance 仍是开放验收项。

D6 的 skip 门没有放宽。此次修复通过来自 skip=0 和实际消费闭环；未来任何未经版本化完整
D2 输入摘要验证的 skip 仍不能进入 formal 守恒式。

### Clean-source 增量正式状态（2026-07-25）

- source/plan 为 `1e5ed8d` /
  `8804ecb4dd0513db55906905f031832711012974fc911546df40e09fb297d373`，来源 dirty=false。
- shard 0、5、9 各完成 45/45，总计 135/900；剩余 765。
- D6 定向报告中的 5v5 seed 1000/1005、20v20 seed 1009 为 3/3 clean-formal、两层
  formal eligible、generation verified，failure reasons 为空。
- 该 3/3 关闭三个目标 cell，不关闭其余已执行 cell。5v5 seed 1008/1018 仍开放。
- 当前磁盘仅比 20 GiB 下限高 63,950,848 bytes。该运行条件阻塞完整批次，不改变 D6
  evaluator 状态；当前无新增 D6-owned 代码 P0。

## 2026-07-26 学习作用域证据审计 GAP

### 已关闭的 D6-owned 项

1. 已实现对 execution plan、scope merge、分片状态、cell 结果和 episode 制品树的完整性与
   SHA-256 绑定审计。
2. 已实现模型 bundle binding、preflight device、resolved versions 和 config/summary
   diagnostics 一致性检查。
3. 已实现逐 episode 实际 assist 采用门。D5 图模型除模型来源、评分状态和零回退外，还要求
   候选边计数 available 且大于 0。shadow、fallback、仅加载 bundle、采用计数为 0 或零边
   空调用均不构成 adoption。
4. 已实现同 `comparison_key` 的唯一 R0 配对和 availability-aware 非退化。必选物理指标缺失
   时 `non_degraded=None`，不补零。
5. 已实现在线真值使用为 0、有限状态和物理结果可用性检查，以及 JSON/CSV/中文
   Markdown/校验和输出。

主审补充后定向回归为 `36 passed, 1 warning in 2.35s`，其中新增 29 项；D6 全量回归为
`930 passed, 1 warning in 78.98s`。新增测试证明 execution plan 内容/摘要、merge checksum、
progress/checkpoint、episode tree 篡改，重复或 lineage 错配 R0，D3/D4/D5 主动视觉空采用，
C1/F1 缺任一必要组件和 D5 零候选边均返回 `fail_closed`。warning 为既有 Matplotlib
`Axes3D` 环境提示。

### 仍开放的跨模块证据项

main 尚未向本任务提供 d59352b 的实际学习 execution plan/merge、同键 R0 execution
plan/merge、实际绑定 bundle 根目录和可选预期设备。因此正式 scope 的实际采用、R0 非退化和
模型准入均为 unavailable。该项属于待运行证据，不是 D6 解析器代码 P0。

当前无新增 D6-owned P0。D6 审计器完成后仍不拥有模型晋级权，不修改默认控制路径。
