# 第一研究模块实验结果

## 协方差向量化正式多 seed 与长时准入

**证据日期：2026-07-24**

**范围：200 个目标、200 个资源、2 个侦察节点的三维质点集成栈**

### 试验设计

正式 v3 矩阵包含 short seeds 1101-1110、每组 2.2 s，以及 long seeds 1101-1103、
每组 10 s。13 组配对共运行 26 个 episode。26/26 正常退出，13/13 跨构建语义检查通过。

标量 reference 提交为 `a5a472cf81496d94a98db3deb88a3d5c6951f0ce`，向量化 candidate
提交为 `064cbb979d3bab68fee995e476df25709eb666db`。两臂共同包含
`064cbb979d3bab68fee995e476df25709eb666db` 的 D1 完整正半定修复和 `e4147b8` 的
D2 误警审计修复。两臂唯一试验差异是
`vectorized_covariance_limit=False/True`。

正式 `evidence_manifest.json` SHA-256 为
`40669d10fff8367aa31e24624bab802d8bc3de6b01aaa1e5c92d054753ed93ec`。

### 性能结果

| 组别 | D1 融合累计墙钟 reference | candidate | 均值改善 | candidate 更快 | 配对原始变化 95% CI | 单次融合 P95 改善 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| short | `4.029165 s` | `3.652252 s` | `9.35462%` | `10/10` | `[-10.914359,-8.113134]%` | `6.652902%` |
| long | `32.954357 s` | `30.768826 s` | `6.631993%` | `3/3` | `[-7.279095,-5.406805]%` | `6.655511%` |

置信区间报告原始配对相对变化 \((candidate-reference)/reference\)，所以越低越好的性能改善
对应负区间。short 和 long 的融合累计墙钟均超过预注册 `5%` 改善门，且候选更快 seed 数
分别达到 `10/10` 和 `3/3`。D6 给出 `d1_optimization_admitted=true`。

### 缺口状态

完整正半定输出 P0 已关闭。协方差成对限制向量化的 P1 准入已关闭。candidate 在全部正式
episode 中的最低实时因子为 `0.143397`，因此
`system_realtime_gap_closed=false`。

本矩阵没有计算均方根误差（RMSE）、归一化估计误差平方（NEES）或归一化创新平方（NIS），
也不包含 AirSim、实机或目标硬件运行。它不能用于宣称系统实时、融合精度或目标平台容量。

## 完整正半定故障复现与修复

**证据日期：2026-07-24**

**场景：200 个目标、200 个资源、2 个侦察节点，seed 1103，仿真 10 s**

### 复现

原候选在外部运行约 51.4 s 后，于仿真发布时刻 `7.85180018473111 s` 将
`global_track_031` 交给 D2 时失败。最新 EO 量测/到达时刻为
`7.7/7.788263318059678 s`。限制前 covariance 最小特征值为
`+7.506060086e-04`。旧 pairwise 路径将一个位置交叉项从
`1087.599461434918` 裁到 `1086.6821912486967`，最小特征值变为
`-9.247657800e-04`，D2 按既有严格合同拒绝。

同一冻结运行对每次限制同时执行 scalar 和 vectorized 计算。在失败前共比较 58,776 次：

| 维数 | 调用数 |
| ---: | ---: |
| 2 | 851 |
| 4 | 7,443 |
| 6 | 50,482 |

两路 reason mismatch 为 0，array mismatch 为 0，最大绝对差为 0。单独 scalar 复跑也在
同一航迹、同一时刻得到同一 covariance。故障属于旧 pairwise 数学的共同缺口。

### 修复

当前在 pairwise 限制后增加完整正半定投影。投影在相关矩阵空间执行特征值 floor，恢复单位
对角，再与单位阵做确定性凸组合以满足 `0.999` 相关上界，最后恢复治理对角。最多 3 次严格
复核，极端浮点情形回退到同一治理对角矩阵。D2 门限没有修改。

固定故障矩阵用 1 次投影完成修复。输出最小特征值为
`1.513567407e-07`，最大绝对相关系数为 `0.999`，六个对角元素逐元素不变。审计记录 1 个
pair 裁剪、1 次特征值 floor、1 次相关收缩和 1 次投影迭代，没有触发对角回退。

### 验证结果

- 固定 seed 1103 故障矩阵通过；
- 1 至 6 维每维 96 组随机/极端矩阵通过；
- pairwise 上界内仍非正定的矩阵通过；
- scalar/vectorized 输出、reason 和操作数一致；
- 双时间戳、来源谱系、OOSM 和 6 s fixed-lag 回归通过；
- 专项与旧协方差性能专项合计 `28 passed`；
- D1 全量 `352 passed in 20.52s`。

修复后按原参数重新运行完整 10 s episode。运行处理 10,554 条匿名在线观测，
`finite_state=True`、`online_truth_use_count=0`，没有再次发生 D2 PSD 拒绝。实时倍率为
`0.157583`。该数值受当前主分支后续优化和本机负载影响，仅用于证明断点闭合，不与此前未完成
候选做性能 A/B。

### 证据边界

本次关闭 D1 发布非法 covariance 的 P0。其后的 13-pair clean 多 seed/长时矩阵已按本文
首节完成并准入向量化路径；RMSE、NEES、NIS、AirSim、目标硬件和系统实时准入仍未完成。

## 协方差成对限制冻结回放

**证据日期：2026-07-24**

**代码状态：当前 D1 工作树，待 main 固定提交复核**

**场景：seed 1100，200 个目标、200 个资源、仿真 2.2 s**

冻结输入为
`/tmp/msm_d1_overlay_atomic_seed1100_control_20260724_v2/online_observations.jsonl`，
SHA-256 为
`54bed9d7f03497967c3f8478a9e0cf1385e85bcc512bf769df849b7b1ab3e0ec`。共 89 个输入批次、
89 个释放扫描、16 个释放分组和 2,035 条匿名观测；扫描组织器记录 10 次重排、0 次拒绝，
在线 truth 使用为 0。

### 方法

reference 使用原有上三角双循环和标量 `np.clip`；optimized 使用同一成对限幅公式的批量
上三角裁剪，再镜像到下三角。两臂的扫描释放分组、观测顺序、state-only/full
materialization 调度和其余 `FusionAdapter` 参数相同。

先执行一对不计时预热。正式计时按交错顺序运行 5 轮，奇数轮先 reference，偶数轮先
optimized。每条样本的纯融合时间只累计 `process_scan_batch()`，逐扫描语义哈希时间不计入。
计时结束后分别运行一次 cProfile；剖析绝对时间不进入墙钟验收。

### 墙钟结果

| 轮次 | reference / s | optimized / s | 加速 |
| ---: | ---: | ---: | ---: |
| 1 | 2.974023 | 2.560473 | 1.162x |
| 2 | 2.981866 | 2.585902 | 1.153x |
| 3 | 3.025964 | 2.624568 | 1.153x |
| 4 | 3.011440 | 2.614061 | 1.152x |
| 5 | 3.012684 | 2.669874 | 1.128x |
| 均值 | 3.001196 | 2.610975 | 1.149x |
| P50 | 3.011440 | 2.614061 | 1.152x |
| P95 | 3.023308 | 2.660813 | 1.136x |

优化路径 5/5 轮更快。均值下降 `13.00%`。

### 剖析归因

| 调用链 | reference 累计 / s | optimized 累计 / s | 降幅 |
| --- | ---: | ---: | ---: |
| `_limit_covariance_diagonal` | 1.047145 | 0.426826 | 59.24% |
| `_limit_state_covariance` | 1.021350 | 0.427235 | 58.17% |
| `_limit_record_covariance` | 1.057130 | 0.460997 | 56.39% |
| `_predict_all_to` | 1.098530 | 0.584526 | 46.79% |
| `process_scan_batch` | 5.400170 | 4.694563 | 13.07% |
| cProfile 总计 | 5.300741 | 4.595590 | 13.30% |

表中 `_limit_covariance_diagonal` 的 cProfile 累计时间包含其子调用。两臂均调用 limiter
14,868 次；其中 reference 标量 helper 与 optimized 批量 helper 的累计时间分别为
`0.774697/0.164314 s`。调用数量未减少，收益来自消除每次六维状态中的 15 次标量 NumPy
调用和重复三角索引构造。

### 语义验收

预热、5 轮交错和 profile 对照全部通过以下检查：

| 检查项 | 结果 |
| --- | --- |
| 每扫描状态、协方差、双时间戳、谱系和分级 | 严格一致 |
| 每扫描物化 `GlobalTrack` | 严格一致 |
| 终态航迹 SHA-256 | 两臂均为 `ec8c2c76...84e9` |
| 一致性证据 SHA-256 | 两臂均为 `50078979...7462` |
| 操作计数 | 严格一致 |
| 累计诊断 | 严格一致 |
| 扫描/观测/航迹数 | 严格一致，终态 202 条航迹 |
| 物化调度 | 严格一致 |
| 在线 truth 使用 | 0 |

操作计数包括 369,215 个关联候选对、8,180 次创新求解、1,789 次历史/终结重放、
7,104 次 replay checkpoint 复用和 12,637 次航迹物化，两臂相同。

### 长夹具语义对照

长夹具来自 seed 1000 的 10 s 冻结输入，SHA-256 为
`5d033a049c2b4e09fb13d7c36e1117055b5b596d9e31f058ad2bf7cbd267ce8f`。共 771 个
扫描、11,889 条匿名观测、94 个释放组；量测/到达跨度为 `9.8/9.827020 s`，48 个扫描发生
重排，拒绝数为 0。

该夹具只执行一次 reference 和一次 optimized，不预热、不重复、不剖析，不设置计时准入。
两臂均记录 4,009 次 fixed-lag rebase、11,888 条 OOSM、15,425 次历史重放和 447,181 次
checkpoint 复用。463 次完整物化、308 次 state-only、202 条终态航迹均一致。终态航迹
SHA-256 同为 `8f208405...b39a5d`，一致性证据同为 `df41efd8...ce3e2`。逐扫描状态、
协方差、双时间戳、来源谱系、分级、操作计数、累计诊断和延迟审计全部相同，在线 truth 为
0。记录墙钟为 `36.146524/33.513020 s`，仅用于确认任务完成，不作为长夹具性能结论。

专项测试 `18 passed`，D1 全量 `342 passed in 19.73s`。

### 证据边界

本项关闭 D1 内部的标量成对裁剪热点。它没有改变上下界、协方差原因、关联门限、观测数量、
6 s fixed-lag、NED、双时间戳、来源谱系或全局航迹编号。

该结果来自当前未提交 D1 工作树和单 seed 三维质点冻结回放。它不是 clean commit 的全栈
结果，也不是多 seed、AirSim、实时发布、传感器精度或实机证据。main 仍需在固定提交上完成
clean full-stack 对照；RMSE、归一化估计误差平方、归一化创新平方和长时资源预算继续开放。

## A2 原子 shadow clean 成对复核

**证据日期：2026-07-24**

**代码状态：clean commit `7cc2d0cfd598a72d60c6ba8c7d4a283f4e5a897d`**

**场景：seed 1100，200 个目标、200 个资源、2 个侦察节点，仿真 2.2 s**

原始 control 与 atomic-shadow 产物均记录 `repository_dirty=false`。结果如下。

| 指标 | control | atomic-shadow | 判断 |
| --- | ---: | ---: | --- |
| 墙钟 | 10.735151271 s | 19.449935469 s | 增加 `81.1799%`，未通过 `+5%` 门 |
| 实时倍率 | 0.204934234 | 0.113110915 | shadow 更慢 |
| D1/D2/D3 终态 | 202/201/186 | 202/201/186 | 一致 |
| 审计发布 | 0 | 9 | 符合默认关闭对照设计 |
| 决策 | 0 | 46 | 0 accepted，46 `oosm_scan` rejected |
| post-integrity | 不适用 | 9/9 通过 | 原子后置检查通过 |
| atomic failure | 不适用 | 0 | 通过 |
| materialized shadow | 不适用 | 0 | 全拒绝路径未物化 |
| 审计 P50/P95/max | 不适用 | 1024.838/1536.429/1549.436 ms | 性能门失败 |
| 在线 truth 使用 | 0 | 0 | 通过 |
| 禁止写入 | 0 | 0 | 通过 |
| D2/D3 shadow 消费 | 0/0 | 0/0 | 通过 |
| 全局编号变化 | 0 | 0 | 通过 |

shadow 阶段均值为：禁止写入前摘要 `254.599 ms`、原子调用 `544.960 ms`、禁止写入后摘要
`196.413 ms`、shadow payload 摘要约 `0.0003 ms`、日志物化约 `0.099 ms`。旧三步
prepared-handle 路径在 0 accepted 时本来就跳过 detached assemble，其 prepare/evaluate
均值合计约 `540.516 ms`。原子入口没有可消除的装配边界复核，主要前后摘要开销继续存在。

安全隔离与业务非干预子门已闭合。性能门失败，且没有 accepted treatment，无法评价共同质心
overlay 的效果。A2 不准入，A3/A4 与 seeds 1101/1102 继续停止。本结果属于科研仿真中的
单 seed 描述性证据，不代表 AirSim 或实机性能。

## A1 原子接口模块验证

**证据日期：2026-07-24**

**状态：`IMPLEMENTED_UNIT_TESTED_OFFLINE_ATOMIC_OPTIMIZATION`**

**范围：D1 单元测试；main 系统接入结果见上一节**

本轮新增单个 experimental/offline 原子入口，在一次同步调用内完成完整规范准备、decision、
detached shadow 装配和操作后完整性复核。现有公共 prepared handle 的逐边界强校验保持不变。
测试使用确定性工作量计数，不设置机器墙钟阈值。

| 验收项 | 结果 |
| --- | --- |
| 聚焦测试 | `36 passed` |
| D1 全量 | `324 passed` |
| 决策兼容 | 2/3/5 成员 canonical decision SHA-256 与提交 `de73cb2` 基线逐字节一致 |
| 200 航迹规范工作量 | `_describe_tracks=1`；描述摘要 200；post-integrity pass 1；后置规范摘要 200 |
| accepted shadow 工作量 | detached 复制 200；shadow 航迹摘要 200；shadow 发布摘要 1 |
| rejected shadow 工作量 | 复制 0；shadow 航迹摘要 0；shadow 发布摘要 0 |
| 发布摘要 | canonical/shadow 使用同一完整航迹摘要清单语义，可直接比较 |
| 序列化 | `to_dict()` 可由标准 JSON 编码；`canonical_bytes()` 输出确定性字节 |
| 只读 metadata | 嵌套 `MappingProxyType`、tuple、frozenset、NumPy 数组和标量可形成 accepted shadow |
| 接受不变量 | `global_track_id`、速度、成员相对位置和 metadata 值语义保持；协方差不收缩 |
| 调用内篡改 | state/covariance、嵌套 metadata、source support、identity、`last_nis`、全局编号、时间戳和分级变化均丢弃 shadow 并撤销状态推进 |
| 拒绝边界 | OOSM、数量不平衡、重复代和倒退代继续 fail closed |
| 引用隔离 | 结果与准备摘要冻结；不公开内部描述符；shadow 数组和嵌套 metadata 不引用规范对象 |

原子入口在 accepted 和 rejected 两条路径上都执行 post-integrity verify。rejected 路径不进入
shadow 装配函数。accepted 路径先形成 detached 副本和 shadow 摘要，再复核规范对象；复核
失败时不公开 provisional shadow，decision 改为
`prepared_canonical_publication_mismatch`，generation 状态恢复到调用输入。
装配异常同样恢复输入状态，返回 `atomic_shadow_assembly_failed`，不公开部分结果。

该结果只关闭 D1 模块接口和工作量断言。main 后续 clean 原子成对复核仍显示性能门失败，且
0 accepted/46 rejected。A2 不准入，A3/A4 和 seeds 1101/1102 继续停止。

## A1 准备对象与只读 metadata 验证

**证据日期：2026-07-23**

**状态：`IMPLEMENTED_UNIT_TESTED_OFFLINE_OPTIMIZATION`**

**范围：D1 单元测试；A2 系统接线证据单独列于下一节**

本轮保留 A1 数学、安全门、拒绝顺序、decision schema 和默认关闭状态。新增准备对象对一个
完整规范发布只执行一次航迹描述，并在 evaluation 与 accepted shadow assembly 间复用。
准备过程仍校验并摘要全部 200 条航迹，而非只处理歧义分量成员。

| 验收项 | 结果 |
| --- | --- |
| 聚焦测试 | `21 passed` |
| D1 全量 | `308 passed in 19.69s` |
| 旧决策兼容 | 2/3/5 成员 decision SHA-256 与提交 `de73cb2` 基线逐字节一致 |
| 200 航迹工作量 | `_describe_tracks=1`；完整性复核 2 次、共 400 条航迹强摘要 |
| 只读 metadata | 嵌套 `MappingProxyType`、tuple、frozenset、NumPy 数组和标量可完成 accepted shadow 装配 |
| 值语义 | metadata、lineage/source support、identity 内容保持；NumPy 数组脱离复制 |
| 状态不变量 | `global_track_id`、速度和分量成员相对位置保持；协方差增量不收缩 |
| 内容完整性 | state/covariance、嵌套 metadata、source support、identity、全局编号、时间戳和分级修改均拒绝复用 |
| fail closed | 内容或对象失配、OOSM、数量不平衡、重复代和倒退代均拒绝；拒绝返回原序列 |
| 可变性 | 准备对象及工作量字段不可由调用方改写，描述符不持有可变航迹或数组 |

性能测试采用完整描述次数和摘要工作量计数，不采用机器相关的相对墙钟断言。完整性复核遍历
全部 metadata，但不重复协方差特征值、身份扫描、状态/协方差独立摘要和发布级排序摘要。
该结果证明 D1 原型接口、过期摘要阻断和复制路径，不单独证明 main A2 达到实时门。

## A2 显式准备对象成对复跑

**证据日期：2026-07-23**

**main 接入提交：`2b976a7213ccdaa35fe0e22dea88def2651e9467`**

**范围：三维质点 200v200 开发复跑；未运行 AirSim 或 seeds 1101/1102**

control 和 shadow 使用相同 `scenario_config.json`，均为 seed 1100、200 个目标、200 个资源、
2 个侦察节点、2.2 s。两份 manifest 记录同一提交，但 `repository_dirty=true`，因此本节是
开发证据，不是 clean/formal 准入结果。

| 审计项 | control | prepared shadow | 判定 |
| --- | ---: | ---: | --- |
| 结构歧义 evidence | 46 | 46 | 一致 |
| A2 evaluation | 0 | 9 | shadow 专属 |
| accepted/rejected | 0/0 | 0/46 | 全部 `oosm_scan` |
| D1/D2/D3 终态 | 202/201/186 | 202/201/186 | 一致 |
| 在线 truth 使用 | 0 | 0 | 通过 |
| 墙钟 | 10.712171729 s | 19.376483415 s | `+80.8829%` |
| 实时倍率 | 0.205374 | 0.113540 | 下降 |
| shadow 总阶段 P95 | 不适用 | 1532.999 ms | 性能门失败 |

9/9 条审计记录均为 `explicit_prepared_handle_used=true`，evaluation 内容完整性校验 9/9
通过，完整描述总计 9 次。错误、禁止写入、D2 消费、D3 消费和在线 truth 使用均为 0；
generation 水位当前/峰值为 `8/8`，容量 1024，最大审计载荷 `11,275,939 bytes`。

| shadow 阶段 | mean ms |
| --- | ---: |
| 禁止写入表面 before digest | 224.461 |
| prepare canonical publication | 345.095 |
| evaluate overlays | 195.421 |
| 禁止写入表面 after digest | 207.312 |
| assemble shadow tracks | 0.00247 |
| audit log materialization | 0.0973 |

shadow 的 `online_observations.jsonl` 比 control 多 9 条
`audit.d1.centroid_publication_overlay_shadow`。过滤这些专属审计记录，先验证两端计划谱系、
ACK 来源哈希和 D4 内容地址，再按既有跨构建规则归一化不透明计划编号及由审计插入造成的总线
序号偏移，3294/3294 条业务记录逐条一致。两端归一化 SHA-256 均为
`bb7eabca7aaf3d0219a784e3bdb3e75ce31332ce1aa14817d683e56b3c3855a2`。

`offline_truth_state.npz` 的六组数组所在归档逐字节一致，SHA-256 均为
`50268d447e1d146656167c25ed5cea45065b0d253cdba8df7e8715622e1e9c0a`。
`offline_truth_labels.jsonl` 均为
`4fefeeb68ab9d6fbc1679d534c92cfbc55f74b1b1e288a6437e7e87e4abbe30d`；
空的 `offline_proximity_intercepts.jsonl` 均为
`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。

业务非干预、安全摘要和有界水位子门通过。总墙钟增加 80.8829%，远超 P95 增幅不超过 5%
的设计门；46 条决策没有一条 accepted，无法评价有效 treatment。A2 不准入，A3/A4 和
seeds 1101/1102 继续停止。

## A1 publication overlay 纯函数原型验证

**证据日期：2026-07-23**

**状态：`IMPLEMENTED_UNIT_TESTED_OFFLINE_PROTOTYPE`**

**实现提交：`de73cb2`**

**范围：D1 纯函数单元测试；未接 FusionAdapter，未运行 main、AirSim 或系统多 seed**

A1 读取只读规范 `GlobalTrack` 发布快照和 `StructuralAmbiguityEvidence`，输出 detached
accepted/rejected decision、成员 overlays 和新的有界 generation 状态。拒绝时 overlays 为空，
shadow 装配直接返回原业务序列；接受时只在 DTO 拷贝上增加统一 NED 位置平移和 PSD 位置
协方差增量。实验 decision 明确为
`experimental_design_prototype_not_online_schema`。

| 验收项 | 2026-07-23 结果 |
| --- | --- |
| A1 聚焦文件 | `7 passed` |
| D1 全量 | `294 passed` |
| 接受规模 | 同步平衡纯交替环 2/3/5 成员均接受 |
| 接受不变量 | 统一平移；速度、相对位置、`global_track_id`、metadata、lineage/source support、identity 和质量不变；协方差增量 PSD |
| 拒绝范围 | OOSM、stale、数量/匹配结构非法、非纯交替环、身份字段、非有限输入均 fail closed，overlays 为空 |
| 确定性 | 成员、业务航迹、观测、边和组件全排列得到 byte-identical decision/overlay |
| generation/资源 | 同代不重复作用；倒退代、摘要冲突、重叠组件和容量满拒绝；状态条目不超过硬容量 |
| 输入隔离 | 输入 `GlobalTrack` 数组和 metadata 未修改；拒绝装配返回原序列对象 |

聚焦命令：

```bash
PYTHONPATH=research_modules/d1_sensor_fusion/src pytest -q \
  research_modules/d1_sensor_fusion/tests/test_structural_ambiguity_publication_overlay_prototype.py
```

全量命令：

```bash
PYTHONPATH=research_modules/d1_sensor_fusion/src pytest -q \
  research_modules/d1_sensor_fusion/tests
```

该验证关闭的范围仅是 A1 纯函数和 DTO 装配合同。A1 没有修改 `fusion.py`，没有 D1 默认运行
开关，也不是在线 schema。main 已完成 A2 默认关闭审计 shadow 接线；业务非干预通过，但
性能门和有效 treatment 门未通过。A3 新匿名 treatment 发现以及 A4 预注册多 seed、
RMSE/NEES/NIS 和 D2/D3 系统收益均未实现。seeds 1101/1102 继续停止。

## 身份中性共同质心候选模块验证

**证据日期：2026-07-23**

**范围：D1 单元测试；未运行 main、AirSim 或多 seed**

候选在结构歧义 hold 的平衡纯交替环分量上计算集合质心和形状。只有满基数、无自由行列、
同一传感器/扫描/双时间戳/NED、非过期、非 OOSM、无重复/冲突来源、无在线身份字段且两项
几何门限通过时，才对成员施加同一有界位置平移。

| 验收项 | 结果 |
| --- | --- |
| 结构歧义专项 | `62 passed` |
| D1 全量 | `282 passed in 17.81s` |
| 默认开关 | `False` |
| 默认关闭与显式关闭 | 结果、侧车、序列化和审计逐字段一致 |
| `2x2` 输入排列 | 状态、协方差和审计一致 |
| 成员位置 | 只增加同一平移，相对位置不变 |
| 成员速度 | 逐元素不变 |
| hit/观测历史/source support/质量分级 | 不变 |
| 协方差 | 有限、对称、半正定，且相对该帧精确重放基线不收缩 |
| free-row/free-column/混合分量 | fail closed |
| 过期/OOSM/重复/冲突来源 | fail closed |
| truth/actor/target/offline identity 字段 | fail closed |
| 连续新 generation | 每帧替换上一帧临时修正，不跨帧累加 |
| 同代/倒退 generation 重放 | 拒绝且当前状态逐元素不变 |
| generation 水位存储 | 24 代同组件保持 1 条记录 |
| 固定滞后清理 | 窗口内不淘汰；窗口外清理后旧证据仍拒绝 |
| 容量满 | 没有过期条目时拒绝新组件 |
| 正常身份明确量测 | 标准重放替代临时修正，只增加正常量测的 hit/lineage/support |
| `K_max` | 超限拒绝 |
| 操作计数 | 成功分量按成员数加观测数计数 |

测试还确认未观测径向速度占位值不参与修正，侧车继续为
`posterior_update_applied=false`、`update_mode=prediction_only` 和
`cross_covariance_available=false`。这里的 prediction-only 描述身份边。D1 的集合级共同
状态平移通过独立候选审计字段记录。

修复前先用三帧强制 `2x2` 歧义扫描复现跨 generation 累积。每帧观测质心相对精确重放基线
固定偏移 30 m，候选增益为 0.5。首帧发布偏移约 15 m，第二帧错误增长到约 30 m。原因是
创新从不含临时修正的观测历史重算，修正却累加到已修正的 `current_state`。修复后每帧先从
观测历史重建当前发布基线，再只施加本帧修正，连续三帧均保持单帧偏移。

连续 hold 后的唯一匹配扫描验证了替代路径。临时修正在下一扫描前可以由运动模型传播；
`_state_at()` 始终返回不含临时修正的正式重放基线。正常量测接受后，两条候选航迹与纯 hold
对照的状态、协方差和质量重新一致，hit、观测谱系和 radar support 各只增加一次。

候选当前不能晋级。clean 同输入 A/B 已完成，但没有一次共同质心修正，仍缺少有实际 treatment
的冻结输入 A/B、未见 seed 多 seed、正式均方根误差、归一化估计误差平方、归一化创新平方、
D2/D3 下游可用性、D1 P95 和长时内存/吞吐证据。本轮证明 generation 注册表具有硬容量和
固定滞后安全清理，不等于完成长时系统性能验收。

### main clean 同输入复核

**证据日期：2026-07-23**

**范围：固定提交 `7e15dac9cdaf6743999dfe045a70676fd31a17d6` 的三维质点单 seed
同输入复跑；未运行 AirSim 或多 seed**

main 先在未提交工作树接入共同质心构造参数并完成 dirty 开发诊断。该历史运行首次确认
46 个候选均未形成实际处理，但不能作为 clean acceptance。随后使用固定提交 `7e15dac` 重跑
hold-only 与 hold+共同质心两臂。两臂均为 `repository_dirty=false`、
`nominal_200v200`、`recon_count=2`、2.2 s、seed 1100，
`config_sha256=20ef5248...b840`。控制臂为 source-key 加结构歧义 hold，候选臂只增加共同
质心修正。

两臂 `scenario_config.json`、离线真值状态和离线真值标签逐字节一致。89 批
`sensor.observations` 的规范化 SHA-256 均为 `bc064834...51518`；D2 在线记录 SHA-256
均为 `da7089fa...f8d2f`。完整总线文件包含不同的候选审计字段和 episode 标识，其文件哈希
不同，不代表外部传感器输入不同。

| 指标 | hold-only | hold+共同质心 |
| --- | ---: | ---: |
| D1/D2/D3 | 202/201/186 | 202/201/186 |
| strict ID switch | 3 | 3 |
| track continuity | 0.8266666667 | 0.8266666667 |
| coverage continuity | 0.8283333333 | 0.8283333333 |
| available/unavailable/uncommitted mapping | 1491/218/76 | 1491/218/76 |
| identity commitment coverage | 0.9574706212 | 0.9574706212 |
| duplicate assignment | 0 | 0 |
| 未承诺来源/候选绑定违规 | 0/0 | 0/0 |
| D3 拒绝目标数/一次 hold 事件累计撤回或清除运行时绑定数 | 11/13 | 11/13 |
| 共同质心候选/施加/拒绝 | 不适用 | 46/0/46 |
| generation 水位当前/峰值 | 不适用 | 8/8 |
| 水位淘汰/容量拒绝 | 不适用 | 0/0 |
| finite / online truth use | true / 0 | true / 0 |

46 个候选中，30 个因 `oosm_scan` 拒绝，16 个因 `unbalanced_component` 拒绝。当前门控没有
产生一次状态修正，因此两臂相同属于零 treatment 结果。它证明候选在该输入上安全拒绝，没有
证明共同质心修正能够恢复 hold 的连续性或映射可用性。

新的 D3 身份承诺门阻断了未承诺目标继续分配、视觉绑定和导引，解释了两臂下游绑定违规为 0；
该安全结果不属于 D1 共同质心算法收益。早期 dirty 制品保留在
`/tmp/MSM-neutral-centroid-gate-20260723`，当前 clean 制品位于
`/tmp/MSM-identity-gate-results-7e15dac/{hold_only,hold_plus_centroid}`。
按开发停止条件不运行 seeds 1101/1102。候选保持默认关闭，P1 继续开放。后续先解释 OOSM
和非平衡分量覆盖全部候选的原因；下一节记录该边界诊断。真实匿名冻结输入和新的未见 seed
验收仍未恢复。

## 共同质心冻结扫描边界诊断

**证据日期：2026-07-23**

**范围：D1 受控冻结扫描重放；未运行 main、AirSim 或多 seed**

本次诊断使用既有 governed replay、扫描组织器和在线批融合入口。控制臂关闭共同质心，候选臂
只在诊断实例中开启。两臂的扫描编号、量测时刻、到达时刻和观测数逐帧一致。测试不读取在线
真值，不改变生产默认值、质心公式、固定滞后或 fail-closed 门。

| 场景 | 成员/观测 | free row/column | 共同质心施加 | 结果 | 候选-控制协方差差最小特征值 |
| --- | ---: | ---: | ---: | --- | ---: |
| 同步平衡纯交替环 | 2/2 | 0/0 | 1 | 平移模长 `15.000000 m` | `0.479767799918` |
| 乱序平衡纯交替环 | 2/2 | 0/0 | 0 | `oosm_scan` | `-0.0071928353214153066` |
| 数量不平衡分量 | 2/1 | 1/0 | 0 | `unbalanced_component` | `-0.004617076466238031` |

同步场景的共同平移约为 `[15.000000, 0.000000, 0.003278] m`，低于 `30 m` 上限。两个成员
保持速度、相对位置、hit、来源谱系、身份状态和 `global_track_id` 不变。候选相对控制臂的
协方差差最小特征值为 `0.4797678`，没有收缩。

乱序场景的目标扫描量测时刻为 `0.300 s`，到达时刻为 `0.650 s`。扫描组织器记录一次重排，
但该扫描进入融合前，融合时刻已为 `0.400 s`，因此现有资格门返回 `oosm_scan`。诊断保留原
处理顺序和双时间戳，没有通过忽略时序使候选通过。

数量不平衡场景的最大匹配基数为 1，free row/column 为 `1/0`，并明确报告
`unbalanced_component`。

两个拒绝场景均为 `applied_component_count=0`，共同质心公式没有产生平移或协方差膨胀，
所以共同质心 correction 未施加。候选臂仍在拒绝后各执行一次 publication-base replay +
replace，以清除旧临时修正。控制臂保留分段预测发布态，候选臂换成从观测历史单段重放到发布
时刻的基准；当前离散 CV 过程噪声在两种分段下不满足半群等价，因此产生表中的有限协方差
差值。候选-控制差值与 replacement 前后差值经逐元素 bitwise 归因一致。这不是严格无状态/
协方差副作用路径；差值仅作诊断，不用于放宽门控。

专项测试 `5 passed`，D1 全量 `287 passed in 18.03s`。机器可读结果和中文报告位于
`../reports/structural_ambiguity_centroid_replay_20260723/`。该证据关闭受控输入中“是否
存在合法非零施加窗口”的边界问题。现实 clean seed 1100 仍为 46 个候选、0 个施加；真实匿名
冻结扫描、多 seed、RMSE/NEES/NIS、D2/D3 可用性、P95 和长时资源验收仍开放。候选未晋级。
机器可读晋级边界为 `candidate_not_promoted`。

## 结构歧义证据侧车模块验证

**证据日期：2026-07-23**

**范围：D1 单元测试，以及固定提交 `ff88131` 的单 seed 三维质点全栈 A/B 和离线因果审计；
未运行 AirSim**

本轮验证默认关闭的
`prediction_only_maximum_matching_component_evidence_v3`。候选复用最大匹配允许边图，
对结构歧义分量停止单航迹身份提交和量测更新，并发布
`d1.structural-ambiguity-evidence.v1` 侧车。测试输入只含在线可得状态、协方差、双时间戳、
门内边和匹配结构。

### 结果

| 验收项 | 结果 |
| --- | --- |
| 侧车基础阶段专项测试 | `25 passed` |
| 侧车基础阶段当时 D1 全量 | `245 passed in 17.48s` |
| Python 语法检查 | 通过 |
| 默认关闭序列化 | 与显式 `False` 一致，空侧车不增加字段 |
| 平衡 `2x2` deferred birth | 0 |
| free-row `3x2` deferred birth | 0 |
| free-column `2x3` deferred birth | 1 |
| 参考匹配边角色 | `maximum_matching_allowed + matched_reference` |
| 替代边角色 | 只含该边成立的 cycle/free-row/free-column 标签 |
| truth/actor/target identity | 侧车严格 DTO 拒绝；在线使用为 0 |
| observation 名称及离线 identity metadata | 改变后完整 evidence 不变 |
| 单航迹 lineage | 歧义 observation 未写入 |
| 未观测零径向速度 | 未用于状态更新 |

输入排列不变测试同时置换 observation 顺序和 track 输入顺序，得到相同 evidence、component、
edge 和 source key。成员令牌由显式 publisher node/epoch 与 D1 本地 track id 哈希得到；侧车
不公开本地编号。启用候选的 track snapshot 使用相同 source key，验证了成员到 D1 快照的一一
对应。观测 key 只使用数值量测证据和双时间戳，不使用通用 source lineage；后者可能在合成
回放中携带离线标签。

### 独立来源键控制臂

本轮增加 `publish_opaque_source_key=False`，用于把来源键治理与 hold 干预分开。专项将同一
个 `2x2` 门内代价输入分别送入默认基线和 source-only 融合器。source-only 发布五个不透明
来源字段，但两组的 accepted、updated、created、track count、状态、协方差、hit、观测历史
长度和关联诊断计数一致，且结构歧义 evidence 数量为 0。

另一组输入先按时间顺序更新，再送入一条量测时刻更早、到达时刻更晚的雷达观测。两组的
OOSM 数、重放数、最大重放观测数、终态和协方差一致。双实例序列化结果相同；`None`、整数和
字符串开关均被严格类型校验拒绝。该结果确认 D1 控制臂实现边界，尚未确认 D2 消费 source
key 后的系统影响。

main 后续完成 seed 1100 的闭环三臂：

| 指标 | baseline | source-only | hold |
| --- | ---: | ---: | ---: |
| D1/D2/D3 | 202/203/200 | 202/201/198 | 202/201/186 |
| strict IDSW | 9 | 7 | 3 |
| track continuity | 0.865000 | 0.865000 | 0.826667 |
| coverage continuity | 0.870000 | 0.868889 | 0.828333 |
| 终态已映射真实目标 | 未单列 | 200 | 191 |
| 终态未映射航迹 | 未单列 | 1 | 10 |

hold 端有 prevented hit/miss/birth `69/69/4`、76 条未承诺记录，D3 拒绝 11 个目标，未承诺
绑定违规为 0。首个计划后控制反馈改变后续平台状态和传感器流，因此该三臂是系统效果对照，
不是完全冻结输入的上游因果证明。

### 模块判定

两项 main 复核语义已进入断言：

1. `structural_ambiguity_deferred_birth_count` 只统计自由列，不统计分量中已匹配观测；
2. 每条 edge 保留自己的结构角色，参考匹配边不复制分量级 kinds。

模块合同通过。该结果只确认 D1 侧车结构、默认关闭兼容和 prediction-only 行为，不确认身份
连续性或全栈收益。

### 全栈 A/B

main 在固定提交 `ff88131` 上使用 `nominal_200v200`、seed 1100、2.2 s、
`recon_count=2` 运行 baseline 和
`--d1-d2-structural-ambiguity-hold` 候选。候选开关之外的实验条件保持一致。

| 指标 | baseline | 候选 |
| --- | ---: | ---: |
| D1 航迹数 | 202 | 202 |
| D1 evidence received / consumed | 0 / 0 | 46 / 46 |
| D2 prevented hit / miss / birth | 0 / 0 / 0 | 69 / 69 / 4 |
| D2 航迹数 | 203 | 201 |
| D3 分配数 | 200 | 197 |
| strict ID switch | 9 | 3 |
| track continuity | 0.865000 | 0.826667 |
| coverage continuity | 0.870000 | 0.828333 |
| available mappings | 1,566 | 1,491 |
| partial unavailable mappings | 234 | 296 |
| identity commitment coverage | 1.000000 | 0.957471 |
| 实时倍率 | 0.220352 | 0.207642 |

两组身份指标均可计算，在线 truth use 均为 0。候选减少了 6 次严格 ID switch，但航迹连续性
下降 0.038333，覆盖连续性下降 0.041667，可评估映射减少 75，身份提交覆盖率下降约
0.042529。

46 个 evidence 均被一次消费，证明 D1 侧车在该 episode 中正常生成并越过 D1-D2 接口。D2
身份保持消费者阻止了对应 hit、miss 和 birth。候选同时减少 D2 航迹和 D3 分配，实时倍率也
下降，因此没有达到预注册晋级条件。

### 因果审计

候选冻结在线输入共重放 89 个 D1 发布批次。逐批 observation、accepted、update、birth 和
track count 与原候选制品一致，终态为 202 条 D1 航迹。重放结束后才连接独立离线真值。

| 量测时刻（s） | 正确参考更新被阻断 | 错误参考更新被阻断 | D1 新生延迟 |
| ---: | ---: | ---: | ---: |
| 0.2 | 9 | 1 | 1 |
| 0.4 | 8 | 2 | 0 |
| 0.6 | 8 | 0 | 0 |
| 0.8 | 9 | 0 | 0 |
| 1.0 | 10 | 0 | 0 |
| 1.2 | 5 | 2 | 0 |
| 1.4 | 8 | 0 | 0 |
| 1.6 | 6 | 1 | 0 |
| 1.8 | 6 | 1 | 0 |
| 合计 | 69 | 7 | 1 |

唯一 D1 延迟新生 `radar-s000002-d0060` 对应 `TGT-0061`，不是假目标或重复航迹；它在
0.4 s 由下一次雷达观测建立，覆盖延迟 0.2 s。D2 的四次 prevented birth 均涉及
`global_track_164`、`global_track_201`，两者离线均对应 `TGT-0171`，属于同一目标的重复
航迹尝试。

对 13 条首次歧义前已存在的成员航迹，平均位置误差从 25.217 m 增至 34.184 m；位置协方差迹
中位数从 156.217 增至 458.349。该子集用于解释整分量 prediction-only 的因果，不是正式系统
均方根误差。

### 系统判定

候选不晋级，保持默认关闭。预注册停止条件已触发，不运行 seeds 1101/1102。D1 结构证据合同
和模块单测继续保留。最可能的 D1 根因是整分量保持同时阻断 69 次正确状态修正和 7 次错误
修正。后续只研究身份不提交、置换不变共同平移且协方差不收缩的新候选，并用未见 seed 同时
验收身份、连续性、状态误差、下游可用性和运行开销。

## 匿名跨模态几何门控

**证据日期：2026-07-23**

**冻结输入来源：clean `5263e2b343dc4b96d239f77ef09437eb132f9efb`**

**场景与样本：`200v200-nominal-v1`，10 s，seed 1000，771 scans /
11,889 anonymous observations，单 episode**

D2 阻断报告在该 episode 中标出 17 条参与多真值航迹帧的视觉观测。D1 先使用冻结输入复现旧
关联，再只修复相机元数据解析和非法投影边界。在线门控未读取离线目标标签、Actor/Object 名称、
真值距离或 D6 结果。

### 根因

冻结扫描帧中的 `camera_model` 是只读 `Mapping`。旧解析器只接受普通 `dict`，因此相机位置虽
由顶层字段保留，旋转和内参却退回默认值。错误投影改变创新代价，并把视觉观测分配给另一目标的
雷达航迹。

### 结果

| 指标 | 旧解析参考 | 候选 |
| --- | ---: | ---: |
| 终态航迹数 | 201 | 202 |
| EO 投影门通过 | 647 | 2,255 |
| EO 投影门拒绝 | 1,823 | 215 |
| EO 投影不可计算 | 0 | 0 |
| 门内但一对一未分配 | 382 | 3 |
| 非量距修正拒绝 | 126 | 44 |
| 最大门内 EO NIS | 39.920615 | 39.326205 |

D2 标出的 17 条污染视觉观测全部离开原错误航迹，17/17 所在候选航迹只包含与该观测一致的离线
目标标签。离线标签在在线回放完成后连接，不参与关联。

规范状态、协方差、时刻和有序谱系摘要由
`39d0cdf55b0d6bb988b9c5631eb472336e92a0510896ec4d63b602477fcb02d7`
变为
`b0d6c4acfbcb776b186014215d236c5050bb7e01385510906d2c42fd2a02d717`。
候选新增 `radar-s000030-d0116 -> global_track_202`。正确视觉后验改变后续雷达关联资格，
因此摘要和航迹数变化有明确因果。

### 回归

测试覆盖合法匿名雷达+视觉融合、错误交叉拒绝、非法相机外参、相机后方点、协方差边界、六秒
OOSM 边界、双时间戳和拒绝分支状态/谱系不变。D1 全量结果为
`191 passed in 16.88s`。

### 限制

本项只关闭 seed 1000 已复现的解析缺陷。nominal seeds 1000-1019 尚未在候选 clean 提交重跑，
D2 的 118 个历史多真值航迹帧和严格身份指标仍未复核。该实验不是 AirSim 或真实相机标定证据。

- `../reports/d1_cross_modal_geometry_governance_20260723.json`
- `../reports/D1_CROSS_MODAL_GEOMETRY_GOVERNANCE_20260723_CN.md`

## 扫描 claim JSON 单次物化

**证据日期：2026-07-23**

**冻结输入来源：clean `5263e2b343dc4b96d239f77ef09437eb132f9efb`**

**场景与样本：`200v200-nominal-v1`，10 s，seed 1000，771 scans /
11,889 observations，单 episode**

输入 SHA-256 为
`5d033a049c2b4e09fb13d7c36e1117055b5b596d9e31f058ad2bf7cbd267ce8f`。参考路径保留旧的
重复 JSON 安全转换；候选路径对共享内容只规范化一次。两条路径均复用完整
`SensorScanFrame`，使用相同扫描水位线、6 s fixed-lag、关联门限、滤波模型和发布计划。

### 等价验收

| 验收项 | 结果 |
| --- | --- |
| Claim registry SHA-256 | 两端均为 `22a71336...b8fd7` |
| 逐输入事件、audit、close 和 release schedule | 一致 |
| 逐 fusion 状态、协方差、双时间戳、谱系和分级 | 一致 |
| 逐 fusion operation/diagnostic snapshots | `82728a8e...bfb5bf` / `b28df84d...521766`，一致 |
| 终态 `GlobalTrack` | `b53d506e...63d98`，一致 |
| 在线一致性证据 | `fc2e5694...fa2ac`，一致 |
| 在线 truth 使用 | 0 |

全部 acceptance 通过。未缩短固定滞后窗口，未丢观测，未改变扫描频率、门限、协方差治理或
滤波公式。

### 性能结果

| 指标 | 旧路径 | 新路径 | 变化 |
| --- | ---: | ---: | ---: |
| 771 scans 交错 5 轮 P50 | 3.618 s | 1.905 s | 1.899x |
| 771 scans 交错 5 轮 P95 | 4.049 s | 2.038 s | 下降 49.7% |
| 单次调用 P95 | 54.575 ms | 25.625 ms | 下降 53.0% |
| `_json_safe` cProfile 累计 | 5.781 s | 1.992 s | 下降 65.5% |
| claim 构造 cProfile 累计 | 8.358 s | 3.758 s | 下降 55.0% |

墙钟不参与语义验收。D1 全量回归为 `185 passed in 19.69s`。本轮未运行新的 clean 候选全栈；
原 clean 20-seed 基线的 scan-input/fusion 累计均值仍为 `9.671/43.774 s`，episode P95
均值为 `135.454/233.488 ms`。候选多 seed 集成收益待 main 复跑。

### 限制

该实验是单 seed 三维质点冻结 replay，不是 AirSim、真实传感器、正式多 seed 或实时放行证据。
冻结候选流水中的 D1 fusion 累计仍为 `43.148 s`。GlobalTrack 物化、非雷达扫描关联和
fixed-lag replay 继续作为 P1 热点。

- `../reports/d1_tail_latency_performance_20260723.json`
- `../reports/D1_TAIL_LATENCY_PERFORMANCE_20260723_CN.md`

## 冻结 replay 尾延时 profiler 与完整帧复用

**证据日期：2026-07-23**

**冻结输入来源：clean `4ac3bb2c12cc6af6ebd372107ced00bcdc5adf6a`**

**场景与样本：`200v200-nominal-v1`，10 s，seed 1000，771 scans /
11,889 observations，单 episode**

冻结输入 SHA-256 为
`c1dda8523e48c255bbeef48d9516b05863eb1bbb3a3ae2e09733259e6a66f77a`。clean episode
原始 D1 fusion P50/P95/max 为 `33.252/224.764/592.957 ms`，scan-input 为
`1.747/177.084/361.536 ms`。

### Scan-input 结果与验收

| 项目 | 再快照参考路径 | 完整帧复用路径 |
| --- | ---: | ---: |
| organizer 内帧重建 | 771 | 0 |
| organizer 内 observation 快照 | 11,889 | 0 |
| `ScanInputOrganizer.ingest` cProfile 累计 | 15.545 s | 5.754 s |
| `SensorScanFrame.__post_init__` cProfile 累计 | 9.710 s | 0 s |
| `_claim_for_frame` cProfile 累计 | 5.681 s | 5.580 s |

前 256 scans 交错 5 轮的总耗时 P50/P95 为
`1.942/1.968 s -> 0.881/0.894 s`，P50 比 2.204x。墙钟不参与通过判定。14 项严格 acceptance
全部通过，包括逐输入结果、close/audit、release schedule、逐 fusion 状态/协方差/双时间戳/
谱系/分级、物化航迹、终态、一致性证据、逐 fusion 操作数及累计诊断。关键哈希：

- fusion semantic：`sha256:e5d4ec2ee902b1fa9e423f7b08380e14a08efec254cea193fad4611a022f4244`
- operation snapshots：`sha256:82728a8e0fed0adedd0254368e29a3c117157b066158595d7ca6dac558bfb5bf`
- diagnostic snapshots：`sha256:b28df84d6664ba17d097990f7186a2a611f2e3469394e3d2a12122dbec521766`
- final tracks：`sha256:b53d506ee3bd4d9a50a3635387832db0c5321f74ccf3f77c18993e3892763d98`

main 实测当前 D1 全量回归为 `185 passed`；这是当前工作区权威测试结果。

### Fusion 归因

fusion 数学路径未修改。cProfile 主要累计路径为 `global_tracks 17.559 s`、扫描一对一关联
`17.027 s`、`_to_global_track 16.930 s`、非雷达代价矩阵 `14.971 s` 和 replay
`8.601 s`。未剖析工作区复放 P50/P95/max 为 `34.108/178.420/354.413 ms`；48 个 radar
scans 的 P95 为 `343.059 ms`，物化扫描 P95 为 `216.991 ms`。候选对峰值 40,000，单扫描
fixed-lag rebase 峰值 197。

该工作区分位只用于和同轮操作数及 cProfile 配对，不与 clean episode 作正式前后比较。
该阶段识别的 claim 重复 JSON 规范化已由本报告首节关闭。GlobalTrack 物化、
radar candidate/rebase、非 claim audit/event 持久化和长期 claim registry 内存继续为 P1。

### 限制与证据路径

clean/commit 仅描述冻结输入来源；优化和等价复放运行在当前未提交 D1 工作区。该实验是单 seed
三维质点 replay，不是新的 clean full-stack、AirSim、正式多 seed 或实时放行，且不新增
RMSE/NEES/NIS 或物理拦截效果证据。

- `../reports/d1_tail_latency_performance_20260723.json`
- `../reports/D1_TAIL_LATENCY_PERFORMANCE_20260723_CN.md`

## Nominal 200v200 clean 单 seed 全栈校准

**证据日期：2026-07-22**

**参考/候选提交：clean `0d2da25c14e50f8f9a10ad47a7bd74e5c5e577fb` / detached clean
`4ac3bb2c12cc6af6ebd372107ced00bcdc5adf6a`**

**场景与样本：`200v200-nominal-v1`，10 s，seed 1000，200 个目标、200 个资源，单 episode**

### 验收方法

本轮是描述性 clean 校准。接受条件是参考与候选均来自 clean source，seed、场景版本、时长和
配置相同，候选状态有限且在线 truth 使用为 0，并且跨构建审计中的规范在线载荷、离线 truth
state、计划谱系模式及两端计划谱系有效性全部通过。性能数据用于同口径描述，不构成正式放行
门限；实时判断仍要求核心 RTF 至少达到 1。

两端各处理 771 个 D1 扫描和 11,889 条匿名在线观测。跨构建审计结果为
`normalized_online_payloads_equal=true`、`truth_state_equal=true`、
`plan_lineage_pattern_equal=true`、`reference_plan_lineage_valid=true` 和
`candidate_plan_lineage_valid=true`，总审计 `passed=true`。

### 结果

| 指标 | clean `0d2da25` | clean `4ac3bb2` | 候选变化 |
| --- | ---: | ---: | ---: |
| 核心 wall | 94.104939744 s | 85.002427712 s | 下降 9.6727%，1.1071x |
| 核心 RTF | 0.1062643 | 0.1176437 | 仍未实时 |
| D1 fusion 累计 | 49.697406826 s | 40.272795088 s | 下降 18.9640%，1.2340x |
| D1 scan input 累计 | 12.315225105 s | 12.560936034 s | 增加 1.9952% |
| 在线观测数 | 11,889 | 11,889 | 相同 |
| 在线 truth 使用 | 0 | 0 | 相同 |

候选 771 次 D1 fusion 调用的 P50/P95/max 为
`33.25249/224.76351/592.95713 ms`。参考计时 schema 没有阶段分布字段，因此本次不构造参考
分位数，也不把候选累计下降解释为尾延时已关闭。

### 进程资源口径

候选核心 wall 85.002427712 s 来自 `summary.json.wall_time_s`。外部 `/usr/bin/time` 记录的
总进程 elapsed 为 `1:55.95`，峰值 RSS 为 `2,468,928 KiB`。外部 elapsed 还包含解释器启动、
离线后处理和制品落盘，不能与核心 wall 混写，也没有用于 9.6727%/1.1071x 的核心比较。

### 判定与限制

语义接受条件全部通过，候选核心和 fusion 累计时间较同 seed 基线下降；但核心 RTF 只有
0.1176437，fusion P95/max 为 224.76351/592.95713 ms，scan input 反而增加 1.9952%。因此
D1 融合尾延时和 scan-input 均继续作为 P1。

本批只有 seed 1000，是单 seed 描述性 clean 校准，不是 20-seed，不是正式性能矩阵，未达到
实时。它不新增 AirSim、真实传感器精度、正式 RMSE/NEES/NIS 或物理拦截效果证据。

只读证据目录：

- `/tmp/MSM-scalable3d-candidate-4ac3bb2/research_modules/scalable_3d_simulation/outputs/scalable_3d_timing_v2_clean_4ac3bb2_20260722/10p0s_seed_1000_nominal/`
- `/tmp/MSM-scalable3d-candidate-4ac3bb2/research_modules/scalable_3d_simulation/outputs/scalable_3d_timing_v2_clean_4ac3bb2_20260722/cross_build_seed_1000_nominal/`

## 非雷达创新批处理

**证据日期：2026-07-22**

**冻结输入：未见 seed 1000，10 s，771 个扫描，11,889 条匿名观测**

函数剖析把当前最大 D1 fusion 热点定位到非雷达扫描代价矩阵。旧路径为每个航迹-观测候选单独
调用伪逆。候选路径保留每条观测的量测和协方差，只把相同量测几何和形状的创新协方差组成矩阵
栈。每个候选的残差、马氏二次型、门限和 Hungarian 分配不变，矩阵栈失败时逐候选回退。

| 口径 | 逐候选路径 | 批处理路径 | 结果 |
| --- | ---: | ---: | --- |
| 前 256 扫描 P50，7 次 | 12.242 s | 10.238 s | 1.196x |
| 前 256 扫描 P95，7 次 | 13.340 s | 11.248 s | 下降 15.7% |
| 前 256 扫描均值，7 次 | 12.506 s | 10.385 s | 1.204x |
| 完整 771 扫描，无 profiler | 50.458 s | 39.994 s | 1.262x |
| 完整 cProfile 非雷达代价矩阵 | 34.307 s | 17.320 s | 调用链下降 |
| 完整 cProfile `pinv` 调用 | 496,625 | 1,018 | 下降 99.8% |

稳定性基准在同一 Python 进程中执行，每个变体先预热 128 个扫描一次，再交错运行 7 次。所用
前缀含 256 个扫描和 4,087 条观测，终态 201 条航迹。逐扫描语义摘要、终态航迹、一致性证据、
全部操作计数和累计诊断严格一致，在线 truth 使用为 0。该 2026-07-22 非雷达专项当次历史
回归为 `182 passed in 15.92s`，不是当前权威测试计数。

证据见 `../reports/D1_NON_RADAR_INNOVATION_PERFORMANCE_BENCHMARK_CN.md` 和对应 JSON。本组关闭
D1 冻结回放的逐候选伪逆热点，不证明完整 D1-D7 实时、AirSim 性能或真实融合精度。

## 一致性证据计数刷新

**证据日期：2026-07-22**

**冻结输入来源：clean `f80b5bd`，10 s，seeds 42000、42001、42002**

参考路径在每次合法缓存证据刷新时执行完整 dataclass 构造校验。候选路径只从已验证冻结记录
复制不变字段，并校验新的非负 replay revision/count。两条路径使用同一扫描释放计划、6 s
fixed-lag、关联和滤波配置。没有缩短窗口、跳过观测、改变门限或使用在线 truth。

| Seed | 扫描/观测 | 终态航迹 | 完整重验 | 受限复制 | 加速 | 严格语义 |
| ---: | ---: | ---: | ---: | ---: | ---: | :---: |
| 42000 | 764/12,107 | 202 | 61.655 s | 48.804 s | 1.263x | 通过 |
| 42001 | 844/11,922 | 207 | 67.316 s | 55.069 s | 1.222x | 通过 |
| 42002 | 782/11,825 | 203 | 65.562 s | 54.096 s | 1.212x | 通过 |
| 均值 | - | - | 64.844 s | 52.657 s | 1.231x | 3/3 通过 |

严格语义检查覆盖每一扫描的状态、协方差、时间戳、来源谱系和航迹分级，以及终态航迹、最终逐
观测一致性证据、全部操作计数和 state-only/full 物化计划。三个 seed 的在线 truth 使用均为 0。
代表 seed cProfile 中，缓存证据刷新累计 `27.122 -> 1.664 s`，历史重放累计
`35.348 -> 9.410 s`。D1 全量测试 `178 passed in 14.80s`。

本次关闭缓存证据重复完整校验热点。候选仍需平均 52.657 s 处理 10 s 冻结输入，不能据此认定
实时。非雷达扫描代价矩阵、航迹物化、scan input、长于 10 s 的增长率、AirSim 和正式
RMSE/NEES/NIS 继续保持开放。

## 最终跨提交集成复核

**证据日期：2026-07-22**

**参考/候选提交：`8f86192` / `f80b5bd`**

**场景：`200v200-nominal-v1`，仿真时长 10 s，seeds 42000、42001、42002**

### 方法

参考和候选均从 clean 工作区独立运行相同场景。验收先比较 seed、场景版本、时长、完整配置、
真值侧车和在线主题计数，再逐条比较在线载荷。D3 每次独立规划产生的不透明 `plan_id` 按出现次序
和版本归一化。归一化前先校验 ACK 原始载荷 SHA；计划 owner/version/coalition、
`global_track_id`、导引 command 及其他业务字段不被忽略。

验收条件为 3/3 seed 的来源工作区 clean、状态有限、在线 truth 使用 0、场景合同一致、D1 终态
航迹数一致，并且逐条在线业务载荷审计全部通过。任一 seed 不满足即不接受本组集成等价结论。

D1 的 `association_innovation_solve_count` 只记录实际执行的精确伪逆次数。它是允许变化的性能
诊断，不参与业务等价判定。候选实现只对通过有限性、严格对称、Gershgorin 正定下界和 `pinv`
cutoff 认证的雷达创新协方差应用预门控；所有未认证矩阵保留原精确 `pinv` fallback。

### 结果

| Seed | 参考/候选 D1 fusion | 参考/候选 scan input | 精确求解参考/候选 | 终态 D1 航迹参考/候选 | 逐条语义审计 |
| ---: | ---: | ---: | ---: | ---: | :---: |
| 42000 | 89.796179/87.209720 s | 16.999921/18.233643 s | 2,393,969/511,264 | 202/202 | 通过 |
| 42001 | 96.598587/92.323182 s | 16.902916/17.148000 s | 2,387,139/527,925 | 207/207 | 通过 |
| 42002 | 92.578497/85.458411 s | 16.805091/17.191083 s | 2,349,120/539,488 | 203/203 | 通过 |
| 均值/合计 | 92.991088/88.330438 s | 16.902643/17.524242 s | 7,130,228/1,578,677 | - | 3/3 通过 |

D1 fusion 三 seed 均值下降约 5.01%，精确创新求解下降约 77.86%。scan input 均值增加约
3.68%。三个 seed 均为有限状态，`online_truth_use_count=0`；D1、D2、D3、D5、D7 最终数量均
保持。D1 fused-track、传感器观测及其余在线主题的规范哈希逐 seed 一致。

### 判定

该结果证明 `f80b5bd` 的 D1 预门控在当前三组 integrated 200v200 输入上保持业务语义，并降低
融合分项和精确创新求解成本。solve count 不能作为定位精度、召回率或业务效果指标。scan input
没有同步改善，候选 10 s episode 的系统实时倍率仍显著低于 1，当前长时比较仍把 D1 scan
input、D1 fusion 和 module stack 标为归一化超线性。因此系统实时/长时超线性 P1、AirSim 和
正式 RMSE/NEES/NIS 均未关闭。

证据目录：

`../../scalable_3d_simulation/outputs/scalable_3d_long_duration_candidate_20260722_clean_f80b5bd/`

## 雷达预门控严格等价复核

**证据日期：2026-07-22**

**冻结输入来源：clean candidate `8f86192`**

本次复核针对雷达候选预门控。候选路径只对有限、严格对称、通过 Gershgorin 严格正定及
`pinv` cutoff 安全裕量认证的创新协方差使用马氏距离下界。未认证矩阵全部执行旧精确
`np.linalg.pinv`。测试另构造非正定交叉协方差和近奇异截断矩阵，使旧 `pinv` 代价在门内而
朴素 trace 下界在门外；两类 rejection mask 均未预拒绝，扫描级参考和候选后验一致。

| Seed | 扫描/观测 | 旧路径 | 新路径 | 加速 | 精确求解旧/新 | 完整/状态快照 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 42000 | 764/12,107 | 90.007 s | 84.613 s | 1.064x | 2,393,969/511,264 | 454/310 |
| 42001 | 844/11,922 | 94.712 s | 94.079 s | 1.007x | 2,387,139/527,925 | 516/328 |
| 42002 | 782/11,825 | 89.220 s | 87.165 s | 1.024x | 2,349,120/539,488 | 504/278 |
| 均值/合计 | - | 91.313 s | 88.619 s | 1.030x | 7,130,228/1,578,677 | - |

3/3 candidate 更快。每个 seed 的逐扫描后验、终态航迹和一致性证据哈希完全相同；候选对、
固定滞后操作数、扫描/观测数以及 state-only/full 调度保持不变。精确创新求解下降 77.9%。
专项 `6 passed`，D1 全量 `175 passed in 26.69s`。

结果只适用于当前冻结三维质点输入和本机环境。优化路径处理 10 s 输入仍平均需要 88.619 s，
没有形成实时闭合，也没有增加 AirSim、真实雷达精度或正式 RMSE/NEES/NIS 证据。

## Clean 200v200 全栈接线复跑

**证据日期：2026-07-22**

**候选提交：`8f86192`**

**场景：200 个目标、200 个资源的三维质点全栈，仿真时长 10 s**

### 验收方法

clean 候选路径启用同一 fusion timestamp 延迟物化。扫描整理器释放的每个扫描仍按原顺序调用
D1；中间后验写入 state-only 发布，该 fusion timestamp 的最后后验写入完整 `GlobalTrack`
快照。对照路径为
旧 clean 提交 `3bac3ff`。两条路径使用相同 seed 和场景配置。

验收要求为：工作区 clean、状态有限、在线 truth 使用为 0、D1/D2 无 overflow、安全合同通过；
扫描总数必须等于 state-only 与完整快照数量之和；事件、scan input、共享摘要和世界真值必须与
旧路径对应 seed 相同。

### 结果

| Seed | 扫描数 | 匿名观测数 | State-only | 完整快照 | 旧 D1 fusion | 新 D1 fusion |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 42000 | 764 | 12,107 | 310 | 454 | 103.176 s | 89.796 s |
| 42001 | 844 | 11,922 | 328 | 516 | 106.447 s | 96.599 s |
| 42002 | 782 | 11,825 | 278 | 504 | 100.394 s | 92.578 s |
| 均值 | - | - | - | - | 103.339 s | 92.991 s |

3/3 episode 均为 clean、finite，在线 truth 使用 0，D1/D2 overflow 和安全合同全部通过。
D1 fusion 三 seed 均值下降 10.0%。seed 42000 的 2.2 s 全栈墙钟由 18.611 s 降至
18.302 s。每个 seed 的 state-only 与完整快照之和等于扫描总数；事件、scan input、共享摘要和
世界真值与旧提交 `3bac3ff` 对应 seed 相同。

### 结果解释

本次结果证明 main 已按 D1 接口完成延迟物化接线，并在三个 clean seed 上保持逐扫描融合和发布
语义。下降来自同一运行时刻中间 `GlobalTrack` 快照不再重复构造，不来自合并扫描、删除观测、
缩短固定时滞窗口或改变协方差和门控。

D1 fusion 对 10 s 输入仍平均耗时 92.991 s，实时预算没有闭合。本组是三维质点证据，不是
AirSim、真实传感器精度、RMSE、归一化估计误差平方、归一化创新平方或物理拦截验收。证据目录：

`../../scalable_3d_simulation/outputs/scalable_3d_long_duration_candidate_20260722_clean_8f86192/`

历史模块级性能、融合精度和时延消融实验见 `../reports/EXPERIMENT_REPORT.md`。
