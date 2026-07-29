# D4 v4 落盘候选不可变审查

## 审查结论

候选通过文件完整性、来源谱系、数据绑定、训练摘要重算、开发夹具治理和离线加载审查。
现有 reviewer 从文件系统重新计算了 179 个非 manifest 制品的 SHA-256，结果与候选
manifest 完全一致。离线 development loader 成功加载模型、训练数据 manifest 和安全门。

本结论只确认该目录是一份内容寻址、可复核的 development/shadow 候选。候选未登记，
默认 loader 以 `v4_candidate_unregistered` 拒绝运行加载。正式预检、正式保留集、
assist、分配、接管、联盟提交、控制和物理权限仍然关闭。

## 审查对象

- 候选标识：`region_resource_a2_executable_transfer_shadow_v4`
- 模型版本：`d4-region-resource-graph-bc-executable-transfer-v4`
- 构建提交：`fd857457bb27a4a709a7c4937e22ebe1cbd7f848`
- 构建日期：2026-07-29
- 候选目录：
  `outputs/d4_v4_candidate_observable_calibrated_20260729/`
  `region_resource_a2_executable_transfer_shadow_v4`

审查调用现有 `review_region_resource_v4_candidate(...,
require_registered_binding=False)`，随后使用
`RegionResourceV4CandidateLoader(..., require_registered_binding=False,
evaluation_context="offline_development")` 重载。默认注册加载另行执行，结果按未登记状态
失败关闭。

## 身份清单

| 对象 | SHA-256 |
| --- | --- |
| candidate manifest 文件 | `2986d166ad6de231896e46f78aa2d9304c21b6d68714eaf34dfe21439220bebe` |
| candidate manifest 内容 | `4f3e973597469d394a594bec3dd7d2c16b24e80d2e97ba45f718d9ef8397e116` |
| 模型权重 | `33a28060f11277a549b90d2f2f365962fec057b2bfb50a70ab5a422059cb9fe5` |
| bundle manifest | `7f2b846a43bd9e3a7b106709193aba4156e7d45753fbf6a5b8d3e2634b040847` |
| 开发数据集 | `b31fc43f3d3cff34ee53f2b2c33ece0b06d7624e46e26a36c4aa834135e7fb8c` |
| 数据切分 | `c212fe9b48e9908fd4d47488711724ed361429cf9df29667ac32c3e88d094619` |
| 外部数据证据 | `f059ff5dc1436977f75593edf0cffe5fde7b1865c8db0c5b6330cc7b834e3ca5` |
| 训练摘要 | `5f32e0ee49893c2317df1131b675900ad7714c66460a108ee2964ba62839c3eb` |
| intervention gate | `bd8ce9cc2393213275687b9bbb08abb46ee63a811814a60307ea69d9afa87500` |
| 来源身份 | `8607045b232396f0a8e5a69a7f0a72077bff2177cc30085468a04162df5cb0b9` |
| 实现文件清单 | `6ec75da3359f26da95136a472bda1bbb034b1b026f1cab85487def8b43177a51` |

manifest 之外共有 179 个文件。逐文件重算结果与 `artifact_files` 完全一致，目录内未发现
符号链接。任何文件字节变化都会使 reviewer 拒绝该候选。

## 来源谱系

`source_implementation_summary.json` 记录
`source_worktree_dirty=false`、`clean_lineage_claimed=true`。记录的四个实现文件分别为
区域资源模型、数据集、图学习模型和 v4 候选构建器。

审查直接读取 Git 提交 `fd85745` 中对应 blob，逐个计算 SHA-256。四个结果均与来源摘要
一致。来源摘要还记录在线真值使用数 0、未来结果使用数 0。外部来源制品 SHA-256 为
`f39d9ba996c60ca3213f82d2547159bfbd581387bbd421824f9b5a659c37630f`。

## 数据与切分

外部证据声明 `truth_free_online_features=true`、
`generated_by_v4_builder=false`、`source_worktree_dirty=false`，并同时绑定数据集和切分
SHA-256。现有 reviewer 重新加载冻结数据并重算治理摘要，结果与训练摘要一致。

完整 manifest 保存 70 个 TRAIN seed、15 个 VALIDATION seed 和 15 个 TEST seed。
episode 清单为 TRAIN 140、VALIDATION 30、TEST 30。候选目录只复制 TRAIN 140 和
VALIDATION 30 个 payload 文件；30 个 TEST payload 文件未复制。TEST 仅保留切分与内容
身份，不进入本次 reviewer、loader、权重重算或指标重算。

训练摘要记录 TRAIN 350 帧、VALIDATION 75 帧。外部治理
`test_payload_read_count=0`，正式保留 seed 使用数为 0。

## Actor 训练审查

从冻结 TRAIN payload 重新生成类别平衡对象，结果与训练摘要完全一致。

| 项目 | 结果 |
| --- | ---: |
| 正类 / 负类 frame | 60 / 290 |
| 正类 / 负类权重 | 4.833333 / 1 |
| 非零 / 零 edge target | 72 / 3848 |
| 非零 / 零 edge 权重 | 32 / 1 |
| 非零 edge 原始比例 | 53.444444 |
| validation 权重拟合 | 0 |
| TEST 权重拟合 | 0 |

非零 edge 权重按 TRAIN 比例计算并在 32 封顶。TRAIN Actor 正/负命中为
58/60、276/290；VALIDATION 为 13/15、58/60。重算指标与
`train_actor_audit`、`validation_actor_audit` 完全一致。

## 置信训练审查

冻结 Actor 后重新构造 TRAIN/VALIDATION 置信记录。TRAIN-only 类别平衡、可辨识性审计和
固定门指标均与训练摘要完全一致。

| 项目 | 结果 |
| --- | ---: |
| TRAIN 正 / 负标签 | 58 / 292 |
| 正类权重 | 5.034483 |
| 动作不一致负例 / 权重 | 16 / 8 |
| 可执行错误负例 / 权重 | 14 / 20.857143 |
| 普通负例 / 权重 | 276 / 1 |
| validation 权重拟合 | 0 |
| TEST 拟合 | 0 |

固定 0.60 门下，TRAIN 的
positive/negative/inconsistent/executable 通过数为 `12/0/0/12`。VALIDATION 为
`4/0/0/4`。VALIDATION 只承担 checkpoint 选择和固定门审计，没有参与权重或参数拟合。

## Development Fixture

fixture 的 observable key 为
`5bf1fc1e09006bef3b8e859b566ce26cc9467da42827a3a723d35cb7133e2a3c`。
该 key 与 TRAIN 模型输入键完全一致，因此 fixture 只用于 training-domain smoke。

- `training_domain_smoke_only=true`
- `independent_generalization_evidence_available=false`
- `formal_validation_claim_allowed=false`
- 固定 OOD 余量：0.05
- 固定置信门：0.60
- 有效置信度：0.6023671627044678
- 门上裕量：0.0023671627044677956
- 原始 / 投影转移：1 / 1
- 投影拒绝：0
- 相对 source 和同键 R0 均有可执行差异

该薄裕量不能支持准入或泛化声明。fixture 未使用 target、reward、validation、test、
seed 或来源身份做选择，在线真值使用数为 0。

## 权限与登记

manifest 中以下权限均为 false：

- 正式评估授权；
- assist；
- authority；
- assignment；
- takeover；
- coalition commit；
- control；
- production runtime ACK；
- physical permission；
- actual adoption 与 benefit claim。

候选状态为 `development_only=true`、`shadow_only=true`、
`admission_closed=true`、`rule_fallback_required=true`。正式 holdout 和 runtime
preflight 均未完成。bundle 的最大模式为 shadow，正式保留 seed 数为 0，收益证据和策略
能力声明均为 false。

五项 v4 registry 摘要仍为空。默认 loader 的复核结果为
`v4_candidate_unregistered`；离线 development loader 的
`registered_binding_verified=false`。本审查没有写入 registry。

## v3 回归边界

v3 registry 目录重算摘要为
`07c770b05ffc70f190cd8b45d762d579857747e0efb12b472a2354ee5aeaa93a`，
与冻结常量完全一致。v3 文件树未被 v4 候选构建或本次审查修改。

## 审查决定

该落盘候选通过 D4 范围内的不可变制品审查和离线 development 加载审查。可以保留为后续
独立评估输入。它不具备登记、正式预检、正式保留集评估、运行采用或生产权限。

后续若开展 D6 独立审计、D3 successor 或 control/treatment 对照，应继续以本报告列出的
完整 SHA-256 为输入身份。任一身份不一致时终止评估，不从当前报告推导准入结论。
