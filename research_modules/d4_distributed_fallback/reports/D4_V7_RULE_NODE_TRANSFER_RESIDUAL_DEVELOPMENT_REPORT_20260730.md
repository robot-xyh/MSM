# D4 v7 规则节点与转移残差开发报告

## 结论

v7 通过固定的 M16N24 VALIDATION 开发门。该划分上 actor 原始残差激活为 6，
exact 正动作为 2/9，负类 exact R0 为 9/11，不变量失败、投影拒绝和 R0 节点字段
偏差均为 0。

候选解决了 v6 的节点动作与 transfer 脱节问题，并抑制了首版 v7 对 M16N24 负类的
全激活。M16N24 TRAIN 的 exact 正动作只有 1/24，当前模型仍存在正帧覆盖不足。报告
结论限定为开发验证，不包含来源独立评价、注册、运行采用或物理收益。

## 任务

v6 在冻结 v4 来源上可以生成转移，在新的 M16N24 来源上 raw transfer 为 0。同时，
学习节点动作会偏离同帧 R0，造成没有配套转移的节点动作变化和不变量失败。v7 采用
确定性规则节点动作加学习转移残差，目标如下：

1. 节点动作逐字段继承同帧 R0；
2. actor 只学习是否激活残差、选择哪条有向边和转移多少资源；
3. M16N24 VALIDATION 同时保留正类激活和负类 R0；
4. 所有组合动作继续经过确定性投影和既有干预不变量；
5. 候选保持未注册和无运行权限。

## 架构

### 规则基线

输入为区域资源快照。`RuleRegionResourcePolicy` 先生成 R0。R0 包含区域动作和基线
转移集合。区域动作中的 `resource_quota_delta`、储备比例、侦察优先级、hold、
request-replan、owner、plan、version、epoch、lease 和 reasons 均属于确定性安全
合同。raw action tuple 必须与 R0 完整数据类相等。

### 转移残差

actor 使用节点特征、边特征、源目标节点差、全局节点统计和 R0 转移比例。输出分为
三个部分：

- 帧激活值：判断当前快照是否需要学习残差；
- 有向边激活值：在帧门打开时选择得分最高的一条边；
- 资源数：给出该边覆盖 R0 后的绝对资源数。

帧门关闭时输出保持 R0。帧门打开时最多修改一条有向边，其他 R0 转移不变。资源数受
边容量限制。资源数为 0 时删除该边原有转移。

### 投影和不变量

原始节点动作直接引用 R0。转移合并后由 `DeterministicResourceProjector` 重算配额
增量，检查容量和总量守恒。投影后继续检查 owner、plan、epoch、lease、备用资源、
区域邻接和可执行动作一致性。

模型没有节点动作头，也不能生成 D3 计划或 D7 控制。节点字段保持检查在四个来源划分
上的失败数均为 0。

## 训练

### 数据来源

训练使用两个冻结来源：

1. v4 candidate 的 TRAIN 350 帧和 VALIDATION 75 帧；
2. M16N24 labeled dataset 的 TRAIN 89 帧和 VALIDATION 20 帧。

M16N24 数据集 SHA-256 为
`b1295091d4d79e423e1ced02269895d486e2dbcca9d80834d5af0cc14882b42c`，
split SHA-256 为
`c767a48b90f6e2a3f077be4f931d95102a6b2a925a2f813ca8440c8951aae332`。

合并 TRAIN 有 439 帧，其中正帧 84、负帧 355。边标签中正残差边 84、零残差边
5260。正负和来源权重只从 TRAIN 推导。

M16N24 TEST 17 帧没有加载为 episode payload。seed 5216-5279、正式 holdout
1000-1019 和旧评价 3008-3039 均未读取。4016-4079 已是 v7 开发来源，后续不能
作为 v7 未见评价使用。

### 损失

训练损失只作用于 transfer 残差：

1. 边激活二分类；
2. 帧内正确有向边排序；
3. 正残差边资源数；
4. 正帧激活；
5. 负帧 no-transfer 一致性。

边排序 margin 固定为 0.5。损失权重固定为 1.0、0.75、0.50、2.0 和 2.0。独立
负帧损失抑制帧级过度激活。VALIDATION 不拟合参数、权重或阈值。

### 选模

checkpoint 先看投影后行为：

1. M16N24 固定开发门；
2. exact 正动作；
3. 正确有向残差边；
4. 负类 exact R0；
5. 不变量失败、虚假转移和投影拒绝；
6. 固定 TRAIN 权重下的验证损失。

全 no-transfer 和仅节点变化的 checkpoint 均不能通过。最佳 checkpoint 为 epoch
137，训练在 epoch 182 提前停止。

## 指标

| 来源与划分 | 样本 | 正类/负类 | exact 正动作 | 正确有向边 | 负类 exact R0 | actor 激活 | 虚假转移 | 投影拒绝 | 不变量失败 | 节点字段偏差 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 冻结 v4 TRAIN | 350 | 60/290 | 58/60 | 58/60 | 278/290 | 70 | 12 | 0 | 0 | 0 |
| 冻结 v4 VALIDATION | 75 | 15/60 | 13/15 | 13/15 | 58/60 | 17 | 2 | 0 | 0 | 0 |
| M16N24 TRAIN | 89 | 24/65 | 1/24 | 1/24 | 62/65 | 5 | 3 | 0 | 0 | 0 |
| M16N24 VALIDATION | 20 | 9/11 | 2/9 | 2/9 | 9/11 | 6 | 2 | 0 | 0 | 0 |

M16N24 VALIDATION 的固定要求为 raw activation 大于 0、实际 transfer change 大于
0、exact 正动作大于 0、负类 exact R0 至少 8/11、投影拒绝为 0、不变量失败为 0、
完整 action tuple 偏差为 0。实际结果为 6、6、2/9、9/11、0、0、0，开发门通过。

旧域保持较高正类命中。M16N24 正类命中明显较低，说明帧激活和边选择没有在新来源上
形成充分覆盖。负类 exact R0 达到 9/11，过度激活已受控制。本轮冻结超参数，不继续
使用开发验证集调门。

## 重复构建

两次构建使用相同冻结输入、实现和配置。输出目录分别为：

- `outputs/d4_v7_rule_node_residual_failclosed_final_20260730/`；
- `outputs/d4_v7_rule_node_residual_failclosed_final_repro_20260730/`。

两个候选目录执行逐文件比较无差异。候选树内容摘要根据排序后的相对路径和各文件
SHA-256 计算。

| 制品 | 内容 SHA-256 | 文件 SHA-256 |
| --- | --- | --- |
| 模型参数/状态文件 | `bec99032bc176854f7ba265977ed35bf828d415be4bc260c9b6703a95d70082d` | `d0f7f17599fba382d9aa436c6ae34ef5f23b582a5ed9068f3475cb545b4f88f5` |
| 训练审计 | `1d60fbd1e3841eddc76914f7dad4421ae024eaf4ff63190269dc1a2046f6385e` | `4ee26a00e23a7cb3f33d45fcbc5d4bbb8709814d6b9e6b38ac288d55e1072f37` |
| 候选 manifest | `fe9b18f6da8d9daf6d443a89f4cc321a9bda7645be3367b69c4ac29b3ac4f45f` | `7da207acb00f89f1f9b34559fa5b456df412065ae7affd2c88957b776d698cfe` |
| 候选树 | `b143a6bc6787c97d16a8ab58af23e02341e9ce42992cb50e4bcb049b4a04a2fa` | 同内容摘要 |

其他文件摘要：

- source binding 内容：`04f7986709c75c9138f10282aad678872ed74a2bfa1c82b506a5a202881c7002`；
- source binding 文件：`460c790294e78787e135693ed9baf27c914bfe82edd4b2919528b9194e0b8ff1`；
- bundle manifest 内容：`2274370f458bc9359ffcecc3dcb9e47723f8a8516483d2bdaac58dc33e494ee6`；
- bundle manifest 文件：`9c5270e8fe7b24048347775ded50ae8306a8b9be2f8750eb212a26e136450b03`；
- training config 文件：`74908f13b3194c2ed9dff312b03c8b1749e82a91f7e570051fb7f142e21b765f`；
- 实现文件：`a27f0c1d8653a83b8a5a8036d8aa860ab9ded50e18e1dce7700f878bb6096338`。

## 权限

v7 保持以下状态：

- unregistered；
- development 和 shadow only；
- admission closed；
- rule fallback required；
- 无置信校准器；
- 不应用固定 0.60 门。

assist、assignment、degradation、takeover、coalition commit、control、physical、
D3 和 D7 权限全部为 false。候选没有修改 owner、epoch、lease 或运行时权限。

## 测试

最终代码和文档同步后完成以下检查：

- v7 专项测试：19 passed；
- D4 模块全量测试：882 passed；
- v7 模块、构建入口和专项测试 Python 语法检查：通过；
- 两次候选目录逐文件比较：无差异。

全量测试报告 1 条既有 Matplotlib `Axes3D` 导入警告，没有测试失败。测试过程没有启动
AirSim，也没有执行 5216-5279 或读取 M16N24 TEST、正式 holdout 和旧评价数据。

## 验证边界

当前验证证明：

- R0 节点字段由结构保证保持；
- transfer 残差能够在 M16N24 VALIDATION 激活；
- 新域负类 exact R0 达到固定门；
- 投影后不变量没有失败；
- 两次构建内容一致。

当前验证不证明：

- 对新 seed 或新来源的泛化；
- 置信校准和固定 0.60 门；
- D3 计划或 D7 控制权限；
- AirSim、真实网络或物理收益；
- 生产注册和准入。

后续只允许冻结候选的来源独立只读评价。评价结果不足时继续失败关闭，确定性 R0 保持
唯一允许的在线路径。
