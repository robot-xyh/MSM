# D4 v7 来源独立评价报告

## 结论

冻结 v7 没有通过来源独立转移动作评价。validation 和 test 均包含 9 个规则正类，
actor 原始残差激活、相对 R0 的实际转移变化和投影后精确正动作均为 0。两个划分的
规则负类全部保持 R0，分别为 11/11 和 9/9。

train 的 90 帧中出现 10 次 actor 边激活，只有 3 帧形成实际转移变化。3 帧均属于规则
负类，表现为错误边和虚假转移。三个划分均没有投影拒绝、不变量失败或 R0 原始节点动作
继承失败。模型的安全外壳保持有效，学习残差没有形成来源独立正类行为。评价处置为失败
关闭，确定性 R0 继续作为唯一运行路径。

## 输入

评价场景为 M16N24 和 8 个区域。原始来源固定在 commit
`4a83a373f4eb4e29704bb3cf9f62e3d54eee3aec`，使用 seed 5216-5279，共 64 个
episode 和 128 帧。

| 划分 | 帧数 | 规则正类 | 规则负类 |
| --- | ---: | ---: | ---: |
| train | 90 | 24 | 66 |
| validation | 20 | 9 | 11 |
| test | 18 | 9 | 9 |

数据集 SHA-256 为
`f6c52bdd4ce630ae40787226383caab7833f3b034adfb0fc7e93d9e30c90ce67`，
划分 SHA-256 为
`4179c0a766fa93b9127dc534176d69276face35fb110a8c247100d1807521215`。

候选身份固定如下：

| 内容 | SHA-256 |
| --- | --- |
| candidate manifest 内容 | `fe9b18f6da8d9daf6d443a89f4cc321a9bda7645be3367b69c4ac29b3ac4f45f` |
| training audit 内容 | `1d60fbd1e3841eddc76914f7dad4421ae024eaf4ff63190269dc1a2046f6385e` |
| source binding 内容 | `04f7986709c75c9138f10282aad678872ed74a2bfa1c82b506a5a202881c7002` |
| model 内容 | `bec99032bc176854f7ba265977ed35bf828d415be4bc260c9b6703a95d70082d` |
| state 文件 | `d0f7f17599fba382d9aa436c6ae34ef5f23b582a5ed9068f3475cb545b4f88f5` |

## 方法

评价器只执行前向推理和确定性投影。每帧先运行规则策略得到同快照 R0，再运行冻结 v7。
raw 记录保留 actor 激活有向边、预测资源数和相对 R0 的实际 transfer change。资源数
预测为 0 时，actor 可以产生激活记录但不形成实际变化，两类指标分别统计。

投影后动作与 target、R0 使用同一 D3 可消费签名比较。规则正类要求投影后动作与目标
完整一致，规则负类要求投影后完整回到 R0。评价分开记录正确有向边、错误方向、错误
数量、错误边、虚假转移、投影拒绝和不变量失败。

raw `RegionResourceAction` 逐字段与 R0 比较，范围包括资源配额增量、储备比例、侦察
优先级、hold、重规划、owner、plan、version、epoch、lease 和 reasons。projected
action 单独保存，避免把投影器为资源守恒产生的配额变化误写成学习模型改写节点。

actor-derived 正类分母只包含相对 R0 产生可执行差异、通过不变量、没有投影拒绝且完整
继承 R0 raw 节点动作的帧。test 分母为 0，因此比率记为 `unavailable`。

## 结果

| 划分 | raw 激活 | transfer change | 精确正动作 | 负类 exact R0 | 正确有向边 | 错误边 | 虚假转移 | 投影拒绝 | 不变量失败 | R0 节点偏差 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| train | 10 | 3 | 0/24 | 63/66 | 0 | 3 | 3 | 0 | 0 | 0 |
| validation | 0 | 0 | 0/9 | 11/11 | 0 | 0 | 0 | 0 | 0 | 0 |
| test | 0 | 0 | 0/9 | 9/9 | 0 | 0 | 0 | 0 | 0 | 0 |

开发阶段 M16N24 VALIDATION 曾达到 2/9 个精确正动作。该划分参与过 checkpoint 选择，
不能作为独立证据。本次全新来源 validation/test 均为 0/9，说明开发门通过没有转化为
来源独立正类能力。

冻结 v4 TRAIN+VALIDATION 有 251 个唯一在线可观测键，外部数据有 92 个，精确交集为
0。该比较只覆盖冻结 v4 来源。候选训练来源 B 的完整特征载荷没有提供给评价器，全训练
来源可观测键重合状态保持 unavailable。

## 完整性

评价前后五棵输入树均未变化：

| 输入树 | SHA-256 |
| --- | --- |
| v7 candidate | `7bd5419f9d071d6c801f72415a8eb36ac0e36d259187e94229959f5f21d1a667` |
| raw source | `978f94c0165ce6f79446b601c8eddf5b2e157f641fab243582a3349250d5c9a1` |
| labeled root | `05a375853c42a31ecf3a20b2c61d9be6f2a7932d8a5125665f04d30ebc3e6d1b` |
| dataset | `0b88d9afbb0e0e98cb2c59dc950a98cc57c7f5d5bd22d762278fdd81ce6a9282` |
| frozen v4 source | `2afd692874b91a23a5525448a0c5af98f3c2d96f0b12cebbf81a570d58d500d0` |

模型拟合、checkpoint 更新、阈值调整、置信校准、候选修改、输入修改、注册、准入、
正式 holdout payload 和旧评价 payload 读取计数均为 0。逐帧 JSONL 和 CSV 文件
SHA-256 为
`7785ded96360869edfb694c425321fa3323450cf1624607b53edf5d3eca6a5cd`
和 `b8403cf34d8014b193d90f960c34e19a977e65a8b5e79e01ecc36ebdb8f42680`。

## 权限

候选保持未注册、仅开发影子、准入关闭和规则回退。候选没有置信校准器，固定置信门没有
应用。assist、authority、assignment、degradation、takeover、coalition、control、
physical、D3、D7、生产确认、实际采用和收益声明权限全部为 false。

## 验收

v7 来源独立评价专项 21/21、D4 全量 903/903 和新增 Python 文件语法检查通过。全量
测试只有既有 Matplotlib `Axes3D` 导入警告。评价没有启动 AirSim，也没有改变 AirSim
消息、节点、episode 或适配器。

D6 后续已完成 128 帧低层独立重算，D4/D6 逐帧 JSONL 字节摘要和分层结果一致。该复核
确认评价可复现，不改变失败关闭处置。当前评价数据不得反向用于 v7 的拟合、选模、阈值
调整或置信校准。后续学习路线已冻结独立的 v8 TRAIN 来源请求，尚未生成数据。
