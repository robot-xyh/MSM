# D6 正式实验矩阵准入预检报告

## D5 R0 候选图几何正式复核（2026-07-26）

### 结论

正式 R0 候选图制品通过 D6 独立复核。状态为 `formal/pass`，20 个 expected seed 与实际
seed 集合均为 `1000-1019`，场景版本统一为 `d5-crossview-visible-v1`。标签覆盖、候选召回
声明覆盖和稳定帧坐标覆盖均为 2670/2670，硬违规为 0。

该结论只覆盖几何门生成的候选图。finalized dataset 不含 G1 边概率、冻结阈值、选中边和
聚类，也不含中心绑定、导引控制或物理拦截字段。本次不能评价 G1 scoring、cluster purity、
`global_track_id` binding correctness、control outcome 或 physical intercept outcome。

### 输入完整性

输入批次由 clean source commit
`64cb865b9933d45b13878019c0e1a21a8fbb2b05` 生成。批次目录的 `SHA256SUMS` 共 8834 项，
D6 报告目录的 `SHA256SUMS` 共 3 项，两套清单均无失败项。

| 证据 | SHA-256 | 复核结果 |
| --- | --- | --- |
| 批次 manifest 规范内容 | `448b5ff15c458bb8d745f8e0a2ae80b03d9b062790f8a7fafaf18338a8c794c5` | 一致 |
| dataset manifest 文件 | `5ee284fd3a998c7ec415000cda3def1b1db7b866a762bcc68b6667858730b247` | batch 与 sidecar 绑定一致 |
| frame-index sidecar 文件 | `f0db1b13913c69ba6b4beb5c07e242135885a3fb16fc9f559f193ac632611a1e` | 2670 条记录精确覆盖 |
| D6 aggregate 规范内容 | `dc84c90b90378ba0579311b7b5654018bf3a910ad98f30a59e5dc76eecd422af` | 一致 |

sidecar 使用 `scenario_version + seed + frame_index`。2670 个坐标均唯一，episode UID
集合与 dataset 完全一致，显式场景、seed 和 frame provenance 无错配。

### 候选图结果

| 指标 | R0 结果 |
| --- | ---: |
| seed | 20 |
| 图帧 | 2670 |
| 节点 | 16842 |
| 几何候选边 | 4658 |
| 时间合格同真值跨相机节点对 | 4645 |
| 几何保留真边 | 4642 |
| 几何保留假边 | 16 |
| 微平均候选精确率 | 0.9965650494 |
| 微平均候选召回率 | 0.9993541442 |
| 微平均候选 F1 | 0.9979576481 |
| 微平均几何假边率 | 0.0034349506 |
| 逐 seed F1 均值 | 0.9976519241 |
| 逐 seed F1 总体标准差 | 0.0047860563 |
| 逐 seed F1 bootstrap 95% CI | [0.9953251507, 0.9995705026] |

微平均指标先汇总全部边计数。逐 seed 均值先在各 seed 内做微平均，再对 20 个 seed 求均值，
两者口径不同。16 条假边和 3 个未保留的时间合格真值对均保留在统计中，没有按高总体 F1
隐藏。

### 权限与限制

报告权限固定为 `evaluation_only=true`。`model_promotion`、`default_path`、`assignment`、
`failover` 和 `control` 均为 false。`candidate_graph_R0_G1_comparison` 不可用，因为本次
只有 R0 输入。G1 edge scoring benefit、selected-edge metrics、cluster purity、中心绑定、
控制结果和物理拦截结果均按缺合同字段标记 unavailable，没有从候选图指标推断。

该制品来自当前跨视角可见性校准流程，不是实机相机数据。真实外参漂移、同步偏差、检测漏检、
虚警、遮挡和纹理退化仍需独立验证。

### 软件回归

负例覆盖无真值对分母、缺标签、同相机边、超出双时间窗的候选边、formal seed 不足、场景版本
混杂、重复无向边、自环、非有限数组、重复 tracklet key、图文件篡改、sidecar 缺失和 sidecar
记录不全。缺少 sidecar 时，即使两份 dataset 的 `episode_id` 恰好一致，formal R0/G1 比较仍
失败关闭。没有通过字符串解析补出 `frame_index`。

专项测试结果为 `12 passed, 1 warning`。D6 全量结果为
`1022 passed, 1 warning in 88.77s`。warning 来自既有 Matplotlib Axes3D 导入环境，与本项
计算和报告无关。变更 Python 文件 `py_compile` 通过。

### 后续证据

1. 正式 G1 候选图比较需要同稳定坐标的 G1 dataset 与 sidecar。
2. G1 scoring、阈值后选边和聚类需要独立 prediction sidecar。
3. 中心绑定、控制和物理拦截需要独立版本化结果合同。
4. 真实相机外参、同步、漏检、虚警、遮挡和纹理退化条件仍待验证。
5. 本项没有修改 AirSim 接口、episode 顺序或运行时日志，不能视为 AirSim 验证。

## D3 A1 与 D4 A2 实际预准入审计（2026-07-26）

### 输入范围

本次分别读取
`configs/d3_a1_external_audit_actual_20260726.json` 和
`configs/d4_a2_external_audit_actual_20260726.json`。审计只消费现有文件，没有启动 AirSim、
三维质点 episode、900 单元正式矩阵或模型训练，也没有修改 D3/D4 阈值。

D3 静态数据、切分、全样本审计、bundle manifest 和 weights 文件可用。候选仍为
development/shadow，manifest 声明的外部 holdout 已评估数为 0。D4 的对应静态文件和
readiness 可用，候选同样为 development/shadow，final holdout 已评估数为 0；readiness 另
记录动作多样性不足和策略能力未证明。

### 结果

| 角色 | 状态 | 正式 episode | 实际采用 | 物理窗口 | 唯一 R0 | blocker |
| --- | --- | --- | --- | --- | --- | ---: |
| D3/A1 | fail_closed | unavailable | unavailable | unavailable | unavailable | 15 |
| D4/A2 | fail_closed | unavailable | unavailable | unavailable | unavailable | 15 |

表中的 unavailable 不等于 0。正式作用域文件不存在，D6 没有形成正式学习 episode 的观测值。
候选 manifest 中“已评估数为 0”是另一项静态声明，不能用于补齐正式作用域。

两份结果的 blocker code 相同：

1. `actual_adoption_unavailable`
2. `artifact_missing.formal_scope_audit`
3. `artifact_missing.formal_scope_checksums`
4. `artifact_missing.implementation_evidence`
5. `candidate_fingerprint_unavailable`
6. `current_implementation_sha256_mismatch`
7. `formal_episode_count_unavailable`
8. `formal_scope_checksum_unavailable`
9. `formal_scope_evidence_unavailable`
10. `formal_unseen_seed_count_unavailable`
11. `implementation_evidence_unavailable`
12. `paired_non_degradation_unavailable`
13. `physical_state_window_unavailable`
14. `safety_hard_constraint_unavailable`
15. `unique_same_key_r0_unavailable`

D3 配置中的预期当前实现摘要为
`86b06e0705d91f42e7cf49d9e21ef56f5118dd604b2596296624adc4a19adc27`，复跑实算为
`2e06c9d2d66e7ab672421564dcd82b0dcbc6748a871721388656cd010e9bebdf`。D4 对应值为
`ecab1eb7b4e73e622dbae86c494a4dd316b9b4ec10dd0dc9ab92f6ff2882f3d8` 和
`044284d7327a939724659c6ee5784842dcf4fd83621aa366d4d33ad50f68b431`。D6 保留来源漂移，
没有重写输入摘要。

### 制品

| 角色 | 输出目录 | JSON 文件 SHA-256 | JSON 内容 SHA-256 | SHA256SUMS 文件 SHA-256 |
| --- | --- | --- | --- | --- |
| D3/A1 | `outputs/d3_a1_external_audit_actual_20260726_strict_v2/` | `837f95c64efeab9b0a8d4db60c9fc3628b83d6e17dc36a77a2200a32b9255529` | `c1db7bb0b6e8f5776fd7e027dfc30360efd605705f1e8b4afed1047185db8c0a` | `e8af2aab72eef82d6cb071c7613a8800e9013b10b5976f4903f2c5d716836d24` |
| D4/A2 | `outputs/d4_a2_external_audit_actual_20260726_strict_v2/` | `0547fe50d11d8a3735bdfb3bbd9ba330bf1335d3e00bda368f7f49fb967c7c0a` | `e5a116794e7d582ccc16fb600efb6209e0ab642e659c0817a3b60d446025f830` | `fc53e959241cfcd08ab5df83485d8dbc670245f57b7a0107665be3067b6ef0d5` |

旧的 `actual_20260726` 和 `actual_20260726_final` 输出均保留，没有覆盖或删除。

### 验证

专项测试结果为 `31 passed, 1 warning in 8.53s`。测试包含角色正例、缺文件、文件/内容哈希
篡改、当前实现与来源 commit 漂移、错误角色采用证据、19 个未见 seed、shadow、规则 fallback、
零采用、物理状态缺失、硬约束失败、隐藏 blocker、R0 缺失/重复/复用、必选指标缺失或退化、
调用方自声明拒绝、CLI 和确定性输出。

D6 全量结果为 `975 passed, 1 warning in 103.81s`。新增 Python 入口编译通过，限定 D6 路径的
差异格式检查通过。warning 为既有 Matplotlib `Axes3D` 环境提示。

D6 没有授予模型晋级、辅助运行、分配、故障接管、默认路径或控制权限。当前两份失败结果只能供
D3/D4 assembler 读取并继续失败关闭。

## D5 G1 审计版本修正（2026-07-26）

main 的版本审查确认，六权限输出不能继续声明
`d6.d5-g1-external-audit.v1`。D6 已将主输出升为
`d6.d5-g1-external-audit.v2`。输入 spec 和 consumer 字段没有变化，分别保留 input v1 和
consumer v1。external audit v2 精确输出模型晋级、G1 辅助、默认路径、分配、故障接管和控制
六项 false 权限，并保留真实相机、中心 binding 和物理闭环三类 unavailable evidence。

post-assembly 审计输出、输入、consumer 和 profile 同步升为 v2。软件正例只接受
`d5.tracklet-model-bundle.v5`、admission report v2、authority contract v2 和 external audit
v2。v5 fixture 还包含 900 条
唯一 paired lineage；文件摘要和计数与 paired 报告、external audit、manifest 和 admission
report 交叉绑定。旧 v4、audit v1、report v1 或其他权限合同版本均有失败关闭回归。

本轮没有执行正式 external audit 或 post-assembly audit，也没有组装 v5。目录
`/tmp/MSM-d5-g1-current-runtime-d6-external-audit-64cb865-20260726-v2/`
内部仍是 external audit v1，现标记为 `rejected_transition_schema_v1`。下文保留其指标和哈希
用于追溯，但它不得进入新装配。正式 v2 证据需在本次代码提交后重新生成。

软件 fixture 验证覆盖 schema 精确值、六权限、三类 unavailable、v5 七制品、lineage 文件
摘要与 900 个唯一 episode UID、D6 文件/内容摘要、held-out、paired-shadow、运行实现摘要、
旧版本单项拒绝和组合混用拒绝。新增正例不再手工拼装 v5；它调用 D5 公共生产写包器和
`assemble_tracklet_g1_bundle()`，再依次通过 D5 公共严格加载器与 D6 post-assembly v2。
实际产物的 lineage 三字段、900/900 计数、六权限、D6 外审双哈希和运行实现摘要全部通过。
对同一产物篡改或删除 lineage 均失败关闭。

external 专项为 `14 passed, 1 warning in 4.40s`，post-assembly 专项为
`55 passed, 1 warning in 4.93s`，D6 全量为
`1042 passed, 1 warning in 91.36s`。这些结果只验证软件合同，不是正式候选审计或正式 v5
装配结果。

## D5 G1 预准入外部审计（2026-07-26）

### 输入

本次只读审计使用冻结的 99fa 候选。模型 manifest/weights SHA-256 为
`c4284b24...674` / `99fa4428...d4cd`。held-out 报告文件/内容 SHA-256 为
`765d39a5...320a` / `bada1803...067a`；paired-shadow 使用与该权重一致的 final 报告，文件/
内容 SHA-256 为 `cc960206...bf23` / `53bdc658...57a0`。绑定另一模型的 `e39a54d_v2` 未进入
输入清单。

审计没有启动 AirSim、三维质点 episode 或新多 seed 实验。它只验证已有 20-seed 实物。输入
覆盖 seed `1000-1019`、900 个 episode、45 个场景规模单元、13,344 个匿名局部航迹节点和
74,024 条候选边。

### 结果

形式化目录通过。held-out 和 paired-shadow 均绑定 99fa weights，训练数据的 dataset
manifest、split 和 training set SHA-256 一致。在线真值字段、`global_track_id` 改写和同相机
互斥违规均为 0。这些字段 availability 为 true，零值有实际证据。

整体结果为 `fail_closed`，包含四个稳定阻断项：

1. `implementation_lineage_mismatch`。held-out 与 paired 报告联合形成的九文件实现摘要为
   `81968e0d...066e7f`，当前 D5 运行实现摘要为 `ff8c744e...8a1b7`。
   `tracklet_model_bundle.py` 的证据哈希为 `b92037bb...e8cc`，当前哈希为
   `174b18b9...b0ff`。没有可验证等价桥接。
2. `synthetic_single_feature_shortcut`。检测框尺度变化率差的最高单特征 AUC 为
   `0.997340`，超过 0.98 门限。
3. `robustness_threshold_not_met.edge_f1`。遮挡重现代理下最低边 F1 为 `0.563264`，低于
   0.9。
4. `robustness_threshold_not_met.cluster_f1`。同一 profile 的最低簇 F1 为 `0.572845`，低于
   0.9。

五类扰动均使用冻结的 post-gate 候选图，`candidate_graph_rebuilt=false`。该限制已进入结构化
结果，不能把名义 held-out/paired 满分解释为重新投影和重新构图后的外部泛化能力。

### 制品与验证

结果目录为 `outputs/d5_g1_external_audit_99fa4428_20260726/`，包含 JSON、证据索引 CSV、中文
Markdown 和 `SHA256SUMS`。三项内容文件校验通过。专项测试 `13 passed`，覆盖正例、缺文件、
文件篡改、内容篡改、跨模型、跨数据集、实现变化、严格布尔/整数、阈值边界、unavailable、
CLI、内容哈希和重复运行确定性。D6 全量为 `943 passed, 1 warning in 80.56s`；warning 是既有
Matplotlib `Axes3D` 环境提示，不影响本次二维报告和哈希判定。

D6 没有授予模型晋级、G1 辅助、控制权或默认路径变更。当前证据不能被 D5 装配为正向 admission。
下一次复核需要当前实现上的新 held-out/paired 实物，并处理合成单特征捷径和扰动最低性能。

### 装配器后谱系复核

D5 在提交 `005c74e` 中增加 G1 evidence assembler，并将其纳入运行时实现摘要。D6 随后把审计
清单从九个文件对齐为同一十文件集合。D5 API 与 D6 独立计算均得到
`41381db3d11371c049e5569658820ce98abf1a9966ecf86edc0f13f140894b07`。两侧规范 JSON 的排序、
分隔符、ASCII 转义和末尾换行相同。

复核继续使用上述 99fa bundle、原 held-out 报告和正确的 final paired-shadow 报告。没有运行
AirSim、三维质点 episode、训练或新多 seed 评估。结果为 `fail_closed`，包含五个 blocker：

1. `implementation_evidence_unavailable`：旧证据没有
   `tracklet_g1_evidence_assembler.py` 的文件哈希。
2. `implementation_lineage_mismatch`：assembler 的证据哈希为 `null`；同时
   `tracklet_model_bundle.py` 的证据哈希为 `b92037bb...e8cc`，当前哈希为
   `1bc610d3...89bd`。
3. `synthetic_single_feature_shortcut`：最高单特征 AUC 仍为 `0.997340`。
4. `robustness_threshold_not_met.edge_f1`：最低边 F1 仍为 `0.563264`。
5. `robustness_threshold_not_met.cluster_f1`：最低簇 F1 仍为 `0.572845`。

新输入配置为
`configs/d5_g1_external_audit_99fa4428_post_assembler_20260726.json`，输出写入独立目录
`outputs/d5_g1_external_audit_99fa4428_post_assembler_20260726/`。主 JSON 文件 SHA-256 为
`98bf9e0251567a330bf16951acf07da576a6ba3dc47627c3671cd2d491cdc8ed`，内容 SHA-256 为
`40a42af015211d5e721584053e052a893e31aa35b7393195530a5d3d2dc9b90d`。`SHA256SUMS`
三项通过。定向测试 `14 passed`，D6 全量 `944 passed, 1 warning in 80.12s`。原审计目录和
原结论未覆盖。本节是同一历史证据的软件 provenance 复核，不是新实验。

### 7fb5 robust-v2 正式外审

#### 输入与来源

正式审计时间为 `2026-07-26T14:01:34Z`。D5 模型训练来源提交为
`d437744c030785859b61cf893d15d0463ab54ffb`，registry producer 和本次 clean worktree HEAD 为
`fa3ec10712cd03533c718283b36a6326bd29f5c7`。D6 使用 clean worktree 的审计脚本，不使用 main
临时预检结果。

| 输入 | SHA-256 |
| --- | --- |
| registry reference | `9441fa843928c45125cda4ee160ed22bd145e721cd82ef66163f714ffa73da5d` |
| registry audit evidence | `bcee8cbcaeda066398127fcf2da8697ace8922404774a0d84235aac4194c8f29` |
| registry checksums | `c1abebfa957d8bea5be5e03a76d2027d964ea0db219b63eb84c4aaed04097f63` |
| bundle manifest | `0eff183f7579551f83a0519d30e09abfa4f15899981ad8ffb2eb7e2e871bda77` |
| bundle weights | `7fb5db8b6099ca4da5706a3bec53ff7cd634e8bd267c036ce3ee4ee4bf71ca71` |
| bundle checksums | `bf61c96e30fe8cf338a9f98152670735be657d31f338fcaa7d23c064fab58528` |
| held-out report | `4ec0b82402a2ba415a8522bd3ac92fd049f0b10823cff48d2aeb544331b50c3a` |
| paired-shadow report | `f25c9428933fc8bd5e4bbe5db5e9fe573c60053418da224fc047576c27eef57b` |
| paired lineage | `ca122b71477000ff6cfbd6f1b5c807cf533c00366d55d9e51f7f9fbd615aab57` |

held-out 和 paired-shadow 的内容 SHA-256 分别为 `19b9d0d6...3b00` 和
`18d2cd11...dc12`，均由 D6 去除摘要字段后按规范 JSON 复算。十个 D5 运行时源文件当前实现摘要
为 `408e71fe...f4fe`，与报告联合实现谱系一致。

#### 样本与门限

正式证据覆盖 seed `1000-1019`、900 个 episode、45 个场景规模单元、13,344 个匿名局部航迹
节点和 74,024 条候选边。门限和结果如下。

| 检查项 | 冻结门 | 结果 |
| --- | ---: | ---: |
| 未见 seed | >=20 | 20 |
| held-out episode | >=900 | 900 |
| 场景规模单元 | >=45 | 45 |
| held-out F1 | >=0.92 | 1.0 |
| 错误合并率 | <=0.01 | 0.0 |
| 候选召回率 | >=0.95 | 1.0 |
| held-out P95 推理时延 | <=100 ms | 0.885900 ms |
| 单特征最高 AUC | <=0.98 | 0.720073 |
| 扰动 profile | >=5 | 5 |
| 扰动最低边 F1 | >=0.9 | 1.0 |
| 扰动最低簇 F1 | >=0.9 | 1.0 |

在线真值字段、`global_track_id` 改写和同相机互斥违规均为 0。三项计数均有来源，未使用缺测
补零。

#### 结果与制品

正式结论为 `pass`，`blocker_codes=[]`，consumer contract 的全部必选字段可用。输出目录为
clean worktree 的
`research_modules/d6_evaluation_metrics/outputs/d5_g1_external_audit_7fb5db8b_fa3ec10_20260726/`。

| 输出 | SHA-256 |
| --- | --- |
| `d5_g1_external_audit.json` | `10bf19f5fa89788c9cc0a24ab18b647c6cf863149bae08d22fc40796d15210b0` |
| JSON 内容 | `4e24ab33ca290133cf107f2c4ad5fee85d763001556f35fcd0ecdb819bef9e54` |
| 证据 CSV | `c831382e935287bf731b4477b37d259085f3dde555e115a2555d08f396f77ae8` |
| 中文报告 | `b800dfc4a04bd7b06e086f6e84d56618dd1b0765ee17a3db1385b08ca3492dc7` |
| 输出校验清单 | `adcc09453c515d83eb89ef487568f531991a819053a069d923382e6162422ac8` |

D6 的模型晋级、G1 辅助、控制和默认路径权限全部为 false。本次通过只说明冻结证据完整、一致且
达到现有门限。D5 准入装配、main 显式启用和运行作用域审计尚未完成。

五类扰动使用固定 post-gate 候选图，没有在扰动后重新执行相机投影、门控和候选图构建。当前
样本来自合成三维质点投影和离线 truth evaluator，不代表真实相机、真实外参漂移、真实遮挡、
在线检测误差或实机时延。专项测试为 `14 passed, 1 warning in 4.54s`；D6 全量为
`975 passed, 1 warning in 86.70s`。warning 来自既有 Matplotlib `Axes3D` 导入环境，不影响本次
文件、内容哈希和二维报告。

### 当前运行实现 64cb865 外审

#### 输入

受审输入位于 `/tmp/MSM-d5-g1-current-runtime-retrain-64cb865-20260726/`，源码来自 clean
commit `64cb865b9933d45b13878019c0e1a21a8fbb2b05`。输入 JSON 文件 SHA-256 为
`f98b42d328f8def4fabfca779ce9e322de90b053ef69ff98e579d7b8f8d423a5`。

| 输入 | SHA-256 |
| --- | --- |
| registry reference | `a8b93ba2fafaee2f6aeddb3becc404c864a9a64f066ebca54e63890cba4e7e5b` |
| registry audit evidence | `c18f414907521f90a3eade261ad7f511c24594423ecb6daa4c8dc504166e4477` |
| registry checksums | `8d5c6b39313b9bb899077f4f393e1139942236a21679cd95a853e3497897b81a` |
| bundle manifest | `db908b05f10b277f3e8415b0576d3ec43f3572851ea443d658c9837075671d14` |
| bundle weights | `7fb5db8b6099ca4da5706a3bec53ff7cd634e8bd267c036ce3ee4ee4bf71ca71` |
| bundle checksums | `2fe079ed0224e7eda24f5a1388e0f2977fd72de4312011737b635d3234100856` |
| held-out 文件/内容 | `9393c1929eb62fb9564398b33bf07a08f1f41cd8c0c1c80c41f0e985f12d0294` / `e031f7fe2c0f93f0955b30d3e1c0e994c0e461be0cbd46f8dd8c2b28f0eb36e9` |
| paired-shadow 文件/内容 | `2caac3f770f0174b5f48f964e036f6d4d8763e573d11a914c2d125e588f2546b` / `380c9092a208cd67ee470cedc666794895aeec4d14370fc6b29533e86d4be190` |
| paired lineage | `21204bc36964ff80da81d9223be79120b83d163c10bd4d6b7dad0e333c43b8b5` |

顶层、bundle、formal 和 current-runtime registry 的 `SHA256SUMS` 分别覆盖 24、2、2 和
3 项，全部通过。当前十文件 runtime implementation SHA-256 为
`5506638201623048fb53c8e15493a2dc367d5682abbee3b7235704721586b8ea`，与输入期望、
manifest 和 held-out/paired 联合证据相同。九个 artifact 均来自当前批次，paired 没有
`supersedes` 项，所有交叉绑定均一致。

#### 结果

| 核对项 | 门限 | 结果 |
| --- | ---: | ---: |
| 未见 seed | >=20 | 20 |
| held-out episode | >=900 | 900 |
| 场景规模单元 | >=45 | 45 |
| held-out F1 | >=0.92 | 1.0 |
| held-out 错误合并率 | <=0.01 | 0.0 |
| held-out 候选召回 | >=0.95 | 1.0 |
| held-out P95 推理时延 | <=100 ms | 0.8715935983 ms |
| 单特征最高 AUC | <=0.98 | 0.7200734257 |
| 扰动 profile | >=5 | 5 |
| 扰动最低边 F1 | >=0.9 | 1.0 |
| 扰动最低簇 F1 | >=0.9 | 1.0 |

在线真值字段、同相机候选边、同相机互斥违规、`global_track_id` 改写以及创建或换绑违规均为
0。900 条 lineage 的 episode UID 全部唯一。审计前后输入树 80 个文件逐字节一致，未发生
输入修改。

按当时性能和完整性门，结果为 `pass` 且 `blocker_codes=[]`；版本治理结论为
`rejected_transition_schema_v1`。过渡输出目录为
`/tmp/MSM-d5-g1-current-runtime-d6-external-audit-64cb865-20260726-v2/`。

| 输出 | SHA-256 |
| --- | --- |
| JSON 文件 | `24c8b0cd80c20d0dc2929fbf10cf7982109e9627b633dcd8a81ef19549e9ad7d` |
| JSON 内容 | `f17acecff26285c3fdfc228399468af784ea5760abed25ec7d6bc54bd1cb135f` |
| 证据 CSV | `a2e9004c9501a4b8a57053dd70caf97e7fc75eab66ca6bcd54d5cb59adcfe380` |
| 中文报告 | `8a3b90ad340b2ba512695027e0c036f62339ae231d315dfdfe754c6d6ed8087d` |
| 输出校验清单 | `92a9ab327312730de308d7252e6ba0904f629ea2f1b1a040d950f634fcc18768` |

同输入再次写入独立目录，JSON、CSV、Markdown 和校验清单逐字节一致。确定性不能替代正确的
schema 版本。输出只给证据审计结论；
model promotion、G1 assist、default、control、assignment 和 failover 权限全部为 false。

#### 限制

五类扰动均保持原 post-gate 候选图，`candidate_graph_rebuilt=false`。因此满分只证明固定
候选边上的评分稳定性。真实相机泛化、中心 `global_track_id` 绑定正确率和物理闭环结果在
输入合同中不存在，均为 unavailable。本次没有启动 G1 episode，没有调用 D5 assembler，也
没有生成新的 bundle。该制品不得用于 v5 装配。

外审专项为 `14 passed, 1 warning in 4.39s`，D6 全量为
`1022 passed, 1 warning in 89.39s`。Python 编译通过。warning 来自既有 Matplotlib
`Axes3D` 导入环境，不影响本次文件、内容哈希和审计判定。

## D5 G1 历史 v4 装配后正式审计（2026-07-26）

本节记录旧 v4/report v1/audit v1/post-assembly v1 链路。该结果不满足当前 v5/v2 受理条件，
不能作为新装配或新准入证据复用。

### 输入

正式审计时间为 `2026-07-26T14:43:17Z`。输入配置 SHA-256 为
`972bdfeb756e23c0001be2de36693aef43345eaa5d040c9d280e4786bda4bd17`。配置显式冻结 clean
worktree 中的 v4 manifest、weights、bundle 校验清单和三份内嵌 evidence，没有按目录搜索
替代文件。审计器只枚举指定 bundle 根目录核对实际树，不跟随符号链接。

| 输入 | 文件 SHA-256 | JSON 内容 SHA-256 |
| --- | --- | --- |
| v4 manifest | `a5a53de7d7a6b0aebd60f478b3c2768aa2767f4b3e440c92db4891b324337154` | 不适用 |
| weights | `7fb5db8b6099ca4da5706a3bec53ff7cd634e8bd267c036ce3ee4ee4bf71ca71` | 不适用 |
| bundle `SHA256SUMS` | `1221ec238f6b5dfeef70fca05c111877ea20ec2792eb262d8ada50f422c75956` | 不适用 |
| held-out evidence | `4ec0b82402a2ba415a8522bd3ac92fd049f0b10823cff48d2aeb544331b50c3a` | `19b9d0d61fcaaeb3c92bfe3ded414e546b26b0eb5c354cab1b483fa844da3b00` |
| paired-shadow evidence | `f25c9428933fc8bd5e4bbe5db5e9fe573c60053418da224fc047576c27eef57b` | `18d2cd1177dcb0690309d18eba0b0edf350ca9019f91a1f6a8ae77185f9ddc12` |
| 原 D6 外审 evidence | `10bf19f5fa89788c9cc0a24ab18b647c6cf863149bae08d22fc40796d15210b0` | `4e24ab33ca290133cf107f2c4ad5fee85d763001556f35fcd0ecdb819bef9e54` |

bundle `SHA256SUMS` 精确覆盖 manifest、weights 和三份 evidence，没有缺项或额外项。v4 manifest
中的来源 development-v3 manifest/checksums SHA-256 为
`0eff183f7579551f83a0519d30e09abfa4f15899981ad8ffb2eb7e2e871bda77` /
`bf61c96e30fe8cf338a9f98152670735be657d31f338fcaa7d23c064fab58528`。十文件运行实现摘要为
`408e71fe6a31bca03de61d10cefbf73c6b32e193fd6b2d7bf734389972f9f4fe`。

强化复核枚举到六个普通文件：根目录的 manifest、weights、校验清单，以及 `evidence/` 下三份
JSON。目录项只有 `evidence/`。没有额外文件、额外目录、特殊文件或符号链接，
`tree_evidence.exact=true`。

### 核对结果

v4 schema 为 `d5.tracklet-model-bundle.v4`。模型、数据、代码来源、admission report、
held-out、paired-shadow 和原 D6 外审交叉绑定一致。形式化证据覆盖 20 个未见 seed、900 个
episode 和 45 个场景规模单元。在线真值字段、`global_track_id` 改写和同相机互斥违规均为 0，
三项字段 availability 均为 true。

正式结论为 `pass`，`blocker_codes=[]`。v4 中只有 `g1_assist_eligible=true`；default model、
全局航迹标识、分配和控制权限均为 false。D6 输出中的模型晋级、G1 assist、默认路径变更、
全局航迹标识、分配和控制授权也全部为 false。本次结论只确认装配证据完整性。

### 首次正式输出

正式输出位于 clean worktree：

```text
research_modules/d6_evaluation_metrics/outputs/
  d5_g1_post_assembly_audit_7fb5db8b_a5a53de7_20260726/
```

| 输出 | SHA-256 |
| --- | --- |
| `d5_g1_post_assembly_audit.json` | `a78c5edb3c70e2d92cf45f7fb8085149b9932d943ccd3cc53f8f578c4529cf33` |
| JSON 内容 | `91d627fb9cf0978e95d2bdca14fa90dad8eb1489c24833668068760d3497007e` |
| 证据 CSV | `5e50f1e75fb918864a434e154e4e781f10a53efc3d757ff32631b834af229162` |
| 中文 Markdown | `1e1fe11e8f098a94317ab00493a26fb9888bb6fd8c7897955389a7fd0af1c9e2` |
| 输出 `SHA256SUMS` | `a974734cdb5903078e00169db5705a95468be7d618f82d8001a5d6903e1e9f8a` |

输出通过临时目录原子发布，没有残留 staging 目录。固定时间和同一输入重复写入不同空目录时，
JSON、CSV、Markdown 和校验清单逐字节一致。

### 强化版正式输出

首次正式输出保持历史只读。树完整性与符号链接检查加入后，main 在 detached clean evaluator
commit `107cf0756d7b75cd6bf1456d1f1aa940fec6a63c` 上执行正式复核，输出写入：

```text
research_modules/d6_evaluation_metrics/outputs/
  d5_g1_post_assembly_audit_7fb5db8b_a5a53de7_formal_107cf07_20260726/
```

结果为 `status=pass`、`audit_passed=true`、`blocker_codes=[]`。
`tree_evidence.exact=true`，实际树精确包含六个约定文件和 `evidence/` 目录，没有符号链接或
特殊文件。20 个未见 seed、900 个 episode、45 个场景规模单元均可用；在线真值字段、
`global_track_id` 改写和同相机互斥违规均为 0。

| 输出 | SHA-256 |
| --- | --- |
| `d5_g1_post_assembly_audit.json` | `12f457e2e7cc721960fe05e31022d3779652aa8452e7cfba2fb8ad06f662a8ea` |
| JSON 内容 | `3738444168138584c7ec3eb895d123178092176ec751a5b455e575b177a2d852` |
| 证据 CSV | `5e50f1e75fb918864a434e154e4e781f10a53efc3d757ff32631b834af229162` |
| 中文 Markdown | `1e1fe11e8f098a94317ab00493a26fb9888bb6fd8c7897955389a7fd0af1c9e2` |
| 输出 `SHA256SUMS` | `0cad5c0b9176ab9d555ed78114ed4c76063fd6178e98bda4683ade94ba192113` |

`SHA256SUMS` 中的 Markdown、JSON 和 CSV 三项均复算通过。producer evidence 和首次正式输出均
未覆盖。

### 验证与限制

专项测试为 `35 passed, 1 warning in 4.33s`。六类冻结制品分别执行字节篡改；其余负例覆盖
缺文件、额外未列文件、校验清单缺项/重复/路径逃逸、符号链接、bundle 权限误开、原 D6 外审
权限误开、三份 evidence 内容摘要错误、外审绑定不一致、输出路径重叠、原子写入和确定性。
D6 全量为 `1010 passed, 1 warning in 87.38s`。新增模块、命令行入口和测试文件编译通过。
warning 是既有 Matplotlib `Axes3D` 环境提示。

本次证据仍使用固定 post-gate 候选图，没有在扰动后重新投影、门控和构图。样本来自合成三维
质点投影，没有真实相机证据。G1 的正式在线作用域、规则回退情况和同键 R0 非退化尚未审计。
本次 `pass` 只确认 v4 装配后的文件、内容、谱系和权限边界一致，不授予默认路径、模型晋级、
身份、分配或控制权限。
`AIRSIM_INTEGRATION_PLAN.md` 已检查；本项不改变 AirSim 数据、episode 或控制接口，因此未修改。

## 结论

2026-07-25，D6 对 R0、G1、A1、A2、A3、C1、F1 正式实验矩阵执行静态
`post_run` 准入预检。预检读取实际 `ExperimentMatrixPlan.cells()`，没有启动 episode。

当前 expected inventory 为 5700 个 cell。清单本身通过唯一性和范围检查，训练 seed 与评估
seed 没有交集。运行制品尚未形成，通过 cell 为 0，结论为 `fail_closed`。

该结果通过实际 `ExperimentMatrixPlan` 对象调用 D6 接口获得。CLI 未提供 `--inventory` 时也会
失败关闭，但 expected=0 只表示缺少 expected inventory，不代表正式矩阵规模。

## 清单

当前计划包含九类场景、五档规模和 seeds 1000-1019。R0、G1、A1、A2、A3、C1 覆盖九类
场景，共 5400 个 cell。F1 只覆盖中心失效、二级失效和高威胁多对一场景，共 300 个 cell。
合计 5700。

预检不使用固定的 6300。F1 场景范围来自 main 的 cell 枚举。专项测试把 F1 增加到四个场景，
预期数量随清单变为 5800。

## 模型制品

| 模型 | manifest | weights | SHA-256 | assist 声明 |
| --- | --- | --- | --- | --- |
| D3 分配模型 | 存在 | 存在 | 匹配 | 未授权 |
| D4 区域模型 | 存在 | 存在 | 匹配 | 未授权 |
| D5 图模型 | 存在 | 存在 | 匹配 | 未授权 |
| D5 主动视觉模型 | 存在 | 存在 | 匹配 | 未授权 |

文件完整性通过不能替代模型准入。当前四个模型分别处于开发、影子或未完成保留 seed 评估状态。
G1、A1、A2、A3、C1 和 F1 不能在正式矩阵中声明 assist 后静默回退规则路径。

## 缺失证据

当前没有正式 `experiment_matrix_manifest.json`、运行 cell CSV、D6 逐 seed CSV 和聚合 JSON。
逐 cell 的在线真值、有限状态、D2 身份交换与五米物理指标无法评估。正式中文报告、动画和运行
模型清单也未形成。

缺失范围压缩为四条记录：5400 个基础变体 cell 和 300 个 F1 cell 分别缺运行记录与 D6 离线
证据。完整 JSON 和 CSV 仍保留 5700 个 cell 的独立状态。

## 制品

当前预检制品位于
`../outputs/formal_matrix_admission_precheck_20260725_current/`：

- `experiment_matrix_admission_precheck.json`
- `experiment_matrix_admission_cells.csv`
- `EXPERIMENT_MATRIX_ADMISSION_PRECHECK_CN.md`
- `SHA256SUMS`

该结果只说明正式矩阵尚未具备准入条件，不构成算法性能比较，也不代表物理拦截结果。
专项测试为 `9 passed`，D6 全量为 `889 passed, 1 warning`；既有 main 矩阵合同测试为
`7 passed, 1 warning`。当前 JSON、CSV 和中文 Markdown 的 SHA-256 校验均通过。

## R0 后验代次定向复核

clean 提交 `2c7b425d076899e1c54a3d87d6ef23a613ba6e3a` 的 900-cell R0 已完成结构性
执行，原 D6 结果为 895 个 clean-formal 和 5 个 delayed-noisy 后验代次失败。逐轨审计确认
这 5 项的最终状态、协方差和有效时刻已经变化，原运行时将其错误登记为一次 no-op skip。
D6 v10 保持失败关闭，未用扩展计数式放行，并已提交为 `8e955f3`。

main 修复 finalization 后，在 dirty 工作树定向重跑原 5 项。D6 合并结果为：

| 场景与 seed | D1 final / D2 consumed | consume / publication / merge | skip | pending | contract |
| --- | --- | --- | ---: | :---: | --- |
| delayed_noisy 20v20 seed 1009 | 27 / 27 | 7 / 7 / 20 | 0 | empty | verified |
| delayed_noisy 5v5 seed 1000 | 13 / 13 | 6 / 6 / 7 | 0 | empty | verified |
| delayed_noisy 5v5 seed 1005 | 9 / 9 | 5 / 5 / 4 | 0 | empty | verified |
| delayed_noisy 5v5 seed 1008 | 13 / 13 | 5 / 5 / 8 | 0 | empty | verified |
| delayed_noisy 5v5 seed 1018 | 14 / 14 | 6 / 6 / 8 | 0 | empty | verified |

五项均由 D2 实际消费最终后验，generation integrity reasons 为空。该批次的
`repository_dirty=true`，因此正式验收资格仍为 0/5，只能作为修复后的开发态定向证据。
旧 clean 895 项与新 dirty 5 项不能拼接。runtime 修复已形成 clean source commit
`98d01bf`。完整 R0 formal rerun 已在后继 clean source `1e5ed8d` 上启动，当前完成
135/900，尚未形成整体结果。D6 仍保持旧正式结论 895/900。
详细清单和判定边界见 `FORMAL_R0_POSTERIOR_SKIP_AUDIT_CN.md`。

## Clean-source 正式增量复核

执行计划 SHA-256 为
`8804ecb4dd0513db55906905f031832711012974fc911546df40e09fb297d373`。shard 0、5、9
均完成 45/45。D6 定向结果覆盖三个原失败 cell，3/3 均为
`clean_formal_experiment_matrix`，基础与矩阵 formal eligibility 均为 true，generation
contract 为 `verified`，episode/matrix/variant failure reasons 全为空。

三个 cell 分别为 5v5 seed 1000、1005 和 20v20 seed 1009。D1/D2 最终代次分别为
13/13、9/9、27/27；skip 均为 0，pending 均为空。该证据不能外推到其余已执行 cell。
新批次剩余 765 个 cell，原失败项 5v5 seed 1008、1018 仍开放。磁盘可用空间仅比 20 GiB
下限多约 64 MB。完整批次结束前，旧正式结论保持 895/900。

## 学习作用域审计合同验证

2026-07-26 完成 D6 学习作用域审计器的合同测试。测试使用临时构造且完整哈希绑定的
G1/R0 单 cell 制品，不是 d59352b 的正式运行结果，也不是 AirSim 或物理拦截证据。

完整 G1 与唯一 R0 配对时，审计可验证正候选边上的实际模型评分、零 fallback、在线真值使用
为 0、物理结果可用和两项必选指标非退化，同时明确
`model_promotion.allowed=false`。其余 35 项负向测试覆盖：

1. 缺 R0 时配对 availability 为 unavailable，`non_degraded=None`；
2. shadow/fallback 时实际采用状态为 unavailable，不能进入比较；
3. bundle 文件树被篡改时在准入前阻断；
4. 预检设备与预期不一致时阻断；
5. 物理结果缺失时不以 0 补齐，配对非退化保持空值；
6. scope merge 未完成时阻断整个作用域；
7. execution plan 内容或摘要、merge checksum、progress/checkpoint、episode tree 被篡改时
   阻断；
8. R0 comparison key 重复，或来源提交、父计划、外生配置、随机计划不一致时阻断；
9. D3、D4、D5 主动视觉仅加载 bundle、处于 shadow 或实际采用为 0 时阻断；
10. C1/F1 任一必要组件未采用，以及 D5 图模型候选边为 0 时阻断。

定向测试结果为 `36 passed, 1 warning in 2.35s`，D6 全量回归为
`930 passed, 1 warning in 78.98s`。warning 为既有 Matplotlib `Axes3D` 环境提示。正式审计
仍需 main 提供学习 execution plan、完整 merge、同键 R0 计划与 merge、实际绑定 bundle
根目录，以及可选预期设备。上述实物输入缺失前，D6 不形成学习采用率、R0 非退化或晋级结论。
