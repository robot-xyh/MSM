# D4 v6 来源独立评价 D6 盲审

## 结论

D6 于 2026-07-30 从冻结标签数据、v6 模型参数和同快照规则策略重新计算 126 帧动作。
D4 汇总字段只用于事后对账，没有参与指标计算。D6 重算记录与 D4 JSONL、CSV 逐字段
一致，帧级不一致数为 0。

规则正类共 42 帧，冻结 actor 精确命中 0 帧，规则正类精确动作召回为 `0/42`。actor
没有形成通过干预不变量的可执行正动作，actor-derived positive 分母为 0，对应比率保持
`unavailable/null`。负类精确保持 R0 为 `77/84`，比率为 `0.916667`。

v6 没有置信校准器。manifest 中的 0.60 是保留值，本轮置信门应用数为 0。候选不得冻结，
不得进入置信校准，不得读取正式留出集，也不产生 D3、D7、接管、联盟或控制权限。126 帧
全部继续规则回退。

## 数据边界

| 项目 | 结果 |
| --- | ---: |
| 规模 | M16N24，8 区域 |
| episode | 64 |
| 帧 | 126 |
| seed | 4016-4079 |
| train/validation/test | 89/20/17 |
| 规则正类 train/validation/test | 24/9/9 |
| 正式留出 seed 1000-1019 读取 | 0 |
| 旧评价 seed 3008-3039 读取 | 0 |
| 模型拟合/检查点更新/阈值调整 | 0/0/0 |
| 置信门应用 | 0 |

训练 `0-99`、正式留出 `1000-1019`、旧设计与评价 `3000-3039`、pilot
`4000-4015` 和本次独立评价 `4016-4079` 两两无交集。source clean commit 为
`ed9e086ea8cf5c2138035f710cf4deb3e4a2801e`，exporter clean commit 为
`9bdbe31dee34907525eabc9cf278e0d11f7dd88a`。在线真值和真值标识使用数均为 0。

## 动作重算

| 划分 | 样本 | 规则正/负 | 原始/投影转移 | 精确正动作 | 负类精确 R0 | 约束失败 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| train | 89 | 24/65 | 0/0 | 0 | 61 | 6 |
| validation | 20 | 9/11 | 0/0 | 0 | 9 | 6 |
| test | 17 | 9/8 | 0/0 | 0 | 7 | 3 |

错误方向、错误数量、错误边、虚假转移和投影拒绝均为 0。15 帧约束失败来自节点动作
变化但缺少对应转移，不能计为可执行正动作。actor-derived positive 分母在三个划分中
均为 0。

## 来源独立性

冻结 v4 train 与 validation 共 425 帧、251 个唯一在线可观测键。本次外部数据为
126 帧、94 个唯一键，精确交集为 0。键只包含图架构、节点特征、边特征和边索引的
形状、类型和值，不含 seed、episode、目标标签或真值。

## 完整性

| 制品 | SHA-256 |
| --- | --- |
| source tree | `290158f7b24e7c8b155e66d7173e87ff9e4154ab43367396ee42c3ea6dbb189c` |
| labeled export tree | `b0c1044b278a16c328b0641dcb456d93cd4f3b26d8b9552f45b8069580cf9f96` |
| candidate tree | `8c9d01796c4938effda3f2f3e6e4a82eec73813581a32dc544664d7fc51665e7` |
| D4 evaluation tree | `7ea71544a361c7f301559c8fb053c80685f5817d8fe4289a6e059855b68f5861` |
| D4 artifact manifest 文件 | `1b85e8667e211bf4f01264bd7c7eac4dbaeee20f1002a446f7462b52129fb7fc` |
| D4 artifact manifest 内容 | `030ee163db60b8257c919af56b8e53e3dc36dac17e62f5d687e9f95be0e88117` |
| D6 JSON 内容 | `771ed844ab3364fde4ed25217ffd45b7fe04f300ffb8fe4bd2df5ec99d1f25e1` |
| D6 JSON 文件 | `d7c611d2cd7071d98663b62da451ebeecdeb4d327bcbe2bff95277d8041d39dc` |
| D6 split CSV | `db1b3973e6ff50681caff20695649064f6a10345ffc68ad5e28ebf651405a379` |
| D6 重算 JSONL | `771826bff66d3ba601d0ffecc95f7ab9faf416826898319de7b9f1669020c7c5` |

审计前后分别计算 source、标签导出、标签数据、冻结 v4、v6 候选和 D4 评价树摘要。
六项均未变化，`input_mutation_count=0`。D6 重算 JSONL 与 D4 JSONL 的文件摘要完全
相同。

## 验证

专项测试为 `8 passed, 1 warning in 5.20s`。D6 全量测试为
`1223 passed, 1 warning in 139.78s`。测试覆盖汇总篡改、哈希不一致、零
actor-derived 分母、test 正类独立计数、无校准器置信门拒绝，以及 seed/真值污染拒绝。
唯一警告为既有 Matplotlib `Axes3D` 环境提示。

## 下一门

当前 v6 不进入置信校准。D4 需要另立候选版本，先在全新训练数据上形成安全转移动作，
再冻结 actor。新候选必须使用未见开发数据取得非零且数量充分的精确正动作命中，之后
才可建立只使用训练划分的置信校准器，并再次由 D6 盲审。
