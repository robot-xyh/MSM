# D4 分布式降级与接管实验报告

## 2026-08-02 frozen-hash repair 验证

main treatment 文件加入 D3 匿名事件处理后，D4 preflight 以
`main_treatment_implementation_file_sha256_mismatch` 失败关闭。代码段审计确认 D4 region
graph 和 supply/demand treatment 未变化。本轮验收要求 324/324 冻结 cell 通过，并要求
真实 producer 连续完成 sequence 0 和 1；任一失败均不得更新请求哈希。

| 验证项 | 验收阈值 | 结果 |
| --- | ---: | ---: |
| 冻结 episode viability | 324/324 | 324/324 |
| 审计帧与去重复组合 | 972 帧、108/108 | 972 帧、108/108 |
| 失败数/在线真值使用 | 0/0 | 0/0 |
| suspend/resume 前缀 | sequence 0/1 均成功 | 2/2，各 3 帧 |
| 请求资源数 | seed 28100/28101 为 1/2 | 每帧 1/2 |
| 权限 | 仅请求权限开放 | 通过 |
| D4 全量回归 | 无失败 | 1013 passed，1 warning |

sequence 0/1 的 plan version 和 epoch 均保持 1，端点最小 lease 余量分别为 1.81 秒和
1.71 秒；联盟确认完整，owner 有效，故障围栏未触发。诊断临时目录在检查后删除，正式
episode/sample 仍为 0。当前 main treatment、请求内容和请求文件 SHA-256 依次为
`8e77b53dc1f9a5558d4b2f73e10c03f36aa292a298c76c6182169070c5e5ae19`、
`1d53de5ca23b2de7b06aab6a0be719ffc78c8c977bcc408775e372ad677a10c1`、
`18b595057197dda06b8b2a1ec2a357f1f4d652d2512752be83db2f1e979df1e2`。这组结果是软件
来源可行性证据，不是正式生成、模型训练、AirSim 降级或物理协同结果。
全量回归耗时 130.68 秒；唯一告警为既有 Matplotlib `Axes3D` 环境问题。
统一 preflight 复核显示 D4 计划、producer adapter 和 source request 均已就绪，D4 blocker
为空。当前全局状态为 `blocked_by_dirty_generation_worktree`，没有生成命令或执行授权。

## 2026-08-01 A2 v8 来源可生成性与真实前缀

### 现象与根因

真实 producer 的 `sequence=1` 对应 seed `28101`、8 区域有向环、源区富余/目标区短缺、
名义通信、安全正向转移和资源数 2。`0.75/1.0/2.0 s` 三个帧均已形成运行证据，随后在
builder 中被 `v8_r0_transfer_insufficient_source_surplus` 拒绝，main 最终报告
`d4_no_qualifying_runtime_frames`。

旧来源合同把需求从受保护资源预算中再次扣除，与确定性投影器不一致。修正后的硬预算为
“可用资源－已承诺资源－备用下限”。供需差仍用于场景分类和在线特征，其他安全门未改变。

### 结果

| 验证项 | 结果 | 证据边界 |
| --- | ---: | --- |
| 冻结 episode 内存审计 | 324/324 | 不写数据文件 |
| 审计帧 | 972 | 规则、投影、builder、DTO 往返 |
| 完整/去重复组合 | 324/324、108/108 | 覆盖全部冻结条件 |
| 审计失败 | 0 | 任一失败都会阻断 readiness |
| 在线真值使用 | 0 | 不使用 truth ID |
| 真实 producer 连续前缀 | sequence 0/1 | 各 3 帧，共 2 个诊断 episode |

真实前缀复用了同一 writer staging，并完成暂停和恢复。它只证明前两个冻结项可以连续经过
main producer、D4 builder 和 writer。其余 322 项没有进行正式 producer 写出；正式
episode/sample 计数仍为 0，generation execution 和后续权限均为 false。

请求规范内容 SHA-256 为
`1d53de5ca23b2de7b06aab6a0be719ffc78c8c977bcc408775e372ad677a10c1`，请求文件
SHA-256 为 `18b595057197dda06b8b2a1ec2a357f1f4d652d2512752be83db2f1e979df1e2`。

### 收尾回归

D4 全量测试结果为 `1013 passed, 1 warning`，耗时 `112.25 s`。唯一警告为当前 Python
环境中的 Matplotlib `Axes3D` 导入问题。D4 全目录 Python 语法编译通过。

## 2026-08-01 v8 TRAIN 生成请求与 resume 合同验证

### 验证对象

本轮没有运行真实来源生成、AirSim、训练或策略评价。验证对象是 generation-request
readiness artifact、D4 pre-generation validator 和 `V8TrainDatasetWriter` 的跨进程恢复
合同。artifact 绑定 TRAIN seed `28100-28423`、8/9/12/16 区域 schedule，以及 request、
module registry、main allocation binding、global registry 和 writer 文件 SHA-256。

### 结果

readiness 正例输出 `source_generation_request_ready=true`，并提供仓库相对 path 与 artifact
文件 SHA-256。seed、region、split、validation/test allocation、任一引用哈希或 permission
不符时均失败关闭。唯一 true 权限是 source generation request；main execution、实际
generation、training、shadow、assist、degradation、takeover、coalition、runtime、physical
和 control 均为 false。

受控 writer 夹具覆盖完整 324 episode。前 17 项 stage 后释放原 writer 锁，新 writer 从
自哈希 sidecar 重载并验证顺序、seed、clean-source、文件库存和在线/离线 SHA-256，随后完成
剩余 307 项及严格 finalize。文件损坏、文件缺失、sidecar 哈希漂移、错序、seed 漂移、
clean-source 漂移和权限越界负例全部被拒绝。

定向 readiness/writer 为 `60 passed`；D4 全量为 `1004 passed, 1 warning`，唯一警告是既有
Matplotlib `Axes3D` 环境问题。真实 generation episode/sample 仍为 0，validation/test 仍未
分配，生成命令和 main execution authorization 均不存在。本结果证明请求与恢复合同可复现，
不证明来源数据、模型质量、运行非退化或物理效果。

## 2026-08-01 v7 失败归因与 v8 开发来源请求

### 结论

冻结 v7 外部评价保持失败关闭。validation/test 精确正动作均为 0/9；train 的三次实际
转移变化全部位于规则负类，均为错误边和虚假转移。D4 没有调整 v7 权重、阈值或固定
0.60 门，没有注册新模型或接入运行时。

### 输入完整性

诊断复载外部评价的 6 个 manifest 受控文件和 v7 候选的固定 source binding。评价树
SHA-256 为 `02b5b706...24df1`，候选树为 `7bd5419f...1a667`，前后均未变化。JSONL 与
CSV 共 128 条，逐单元对账 128/128。禁止在线身份字段、正式留出读取、输入修改、候选
修改、拟合、调门、校准和注册计数均为 0。

### 行为结果

| 划分 | 样本 | 规则正/负 | 激活帧 | 实际变化 | 精确正动作 | 负类精确 R0 | 错误边/虚假转移 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| train | 90 | 24/66 | 10 | 3 | 0/24 | 63/66 | 3/3 |
| validation | 20 | 9/11 | 0 | 0 | 0/9 | 11/11 | 0/0 |
| test | 18 | 9/9 | 0 | 0 | 0/9 | 9/9 | 0/0 |

45 个行为失败帧全部可定位到流水线阶段。42 个正类帧没有 actor 激活，3 个负类帧选择
错误边并通过投影。actor 另有 7 个负类激活帧因资源数解码为零，没有改变 R0。投影拒绝、
不变量失败、错误方向和错误数量均为 0。

供需差和特征级根因不能计算。冻结记录只有在线可观测键 SHA-256，没有逐区域供需、完整
邻接图、节点特征、边特征和逐边通信状态。阶段级可归因分母为 45/45，特征级可归因分母
为 0/45，保持 unavailable。区域拓扑只确认全部 128 帧为 8 区域；区域数字顺序不代表
物理转移方向。

D6 已从低层模型和同快照规则独立重算 128 帧。D4/D6 JSONL 文件摘要均为
`7785ded9...a5cd`，逐帧和汇总结果一致。该结果确认审计可复现，不支持来源独立能力通过。

### v8 请求

本轮生成 324 个全新 TRAIN seed 请求，范围 `28100-28423`。请求矩阵为四类 8+ 区域
拓扑、三类供需、三类通信、三类动作和三个重复。动作类包括安全正向、安全反向与困难
无转移负类。三个重复分别覆盖 1、2、3 个安全转移资源；困难负类保留 1、2、3 个候选
资源但要求投影后无转移。当前 episode、样本、训练、checkpoint、注册和运行时接线计数
均为 0。

明确拒绝 `5216-5279`、`4016-4079`、`3000-3039`、`4000-4079`、
`1000-1019`、`0-99` 和 `5200-5215`。validation/test 另行从全新来源请求，不从
TRAIN 或旧评价重切分。assist、authority、assignment、degradation、takeover、
coalition、control、physical、D3、D7 和 production 权限全部为 false。

完整产物位于
`reports/D4_V7_FAILURE_ATTRIBUTION_V8_DATA_REQUEST_20260801/`。

新增专项 8/8、D4 全量 921/921 通过。全量仅有既有 Matplotlib `Axes3D` 环境警告。

## 2026-07-31 权威代次绑定回归

本轮复核对象是统一三维 main 的真实 5v5 no-op advisory 链，不是 AirSim 物理实验。
来源 D3 计划在首次权威发布前已绑定四项 epoch/lease 字段。评价重评后，当前计划的
`plan_id/version` 和四项字段均与来源权威消息相同；租约没有更新。

同一场景只发布一条 D3 权威计划消息。advisory 没有产生 successor，也没有产生
applied adoption ACK。诊断记录了 evaluation refresh 被抑制，权威载荷摘要冲突为
零。集成文件结果为 6/6，D4 全量结果为 903/903；唯一警告是既有 Matplotlib
`Axes3D` 环境导入警告。

本轮没有修改 D4 算法或安全门。结果只证明当前源码的单场景合同成立。v4 开发制品中
epoch/lease 可比字段为 `0/100 available`，新的 v5 多 seed 批次和 D6 独立一致性
审计尚未完成。

## 2026-07-30 高威胁开发批次 v4

修复后的开发态批次覆盖 5、20、50、100、200 规模各 20 个种子，共 100 个 episode。
100/100 数值有限，在线真值使用为零，D3-D4 当前计划身份对齐，当前计划联盟执行闭合。
权威计划摘要冲突计数为零。

28 个 episode 使用过 plan-track fallback，共记录 391 次 fallback 快照，涉及 44 个
不同目标编号；本批次没有使用高协方差 tombstone。v3 的 100v100 seed 1010、
200v200 seed 1013 和 seed 1017 均由 97/100 转为闭合。fallback 只使用计划期保存的
D2 均值、协方差和时间信息，不读取离线真值。

D4 模块代码未改。D4 继续拒绝旧版本、旧 epoch、过期 lease、错误成员和不一致摘要，
没有通过放宽 ACK 校验换取闭合。main 修复了任务证据生命周期和同身份权威载荷重复
发布；D7 对缺失当前 D2 身份承诺的目标仍保持 hold。

D6 已完成独立审计。计划 ID/版本对齐为 100/100；644 个当前多成员联盟目标全部闭合；
195838 条通信处置在 100/100 episode 中均为 available/verified。D3 区域 epoch 与
lease 对照字段均为 0/100 available，属于开放 P1。

该批次关闭此前 main-owned P1 的开发态验证。仿真时长为 2 秒，只覆盖 100 个高威胁
预检 episode，来源为 dirty development，不替代完整 formal R0。正式结论仍需
clean-source 900 项重跑，并覆盖显式撤销、新版本和 lease 到期场景。D4 全量回归为
903/903；既有 Matplotlib `Axes3D` 导入警告 1 项，与本次合同复核无关。

## 2026-07-30 高威胁开发批次

以下为 v3 历史结果，已由上述 v4 开发批次完成修复验证。

开发态批次覆盖 5、20、50、100、200 规模各 20 个种子。100/100 保持有限数值，
在线真值使用为零，D3-D4 计划代次对齐为 100/100；当前计划联盟执行闭合为 97/100。

三个失败都指向 `GT3D-000011`。100v100 seed 1010 和 200v200 seed 1013 在
`t=1.10/1.15 s` 已形成 3/3 commit，随后 D2 当前输出在 `t=1.20 s` 丢失该航迹，
main 的 D4 快照同步删除 task。200v200 seed 1017 还存在同一计划身份的两份载荷摘要，
D4 正确拒绝旧摘要 ACK；新摘要 ACK 到达后，任务又因缺轨从快照消失。三例 lease 均
晚于 `2.50 s` 排空终点，问题不是 lease 过期。

本批次没有形成 D4-owned 代码缺陷。main 快照任务覆盖为开放 P1；同一计划身份的载荷
不可变性为 D3/main-owned P0 合同。详细逐消息证据见
`HIGH_THREAT_PRECHECK_V3_COALITION_DIAGNOSTIC_20260730.md`。97/100 只作为开发证据，
不更新为正式 R0 已关闭。

## 2026-07-30 main P0 补丁最终复核

D4 owner 对 main 编排补丁完成第三轮只读复核，当前 P0 全部关闭。11 个定向用例覆盖
当前计划重评、plan-id-only、旧 plan delivery、旧 ACK、错 epoch、错 lease、fresh
coordinator lease 扩展、真实 digest conflict 排空和二次失效显式桥接，结果为
11/11。上一轮 D4 全量结果为 903/903，本轮按要求未重复运行。

该结果属于 dirty development source 的补丁验收，不是新的正式 R0 结果。原 900 项
制品和 872/900 严格业务结果保持历史证据，不作改写。下一步必须从新的 clean source
完整生成正式 R0，并由 D6 独立检查当前 D3/D4 代次、执行闭合、排空状态和逐消息处置。

## 2026-07-30 正式 R0 联盟确认后验诊断

### 结果

正式 R0 共 900 个 episode，D6 严格业务通过 872 个。28 个失败全部位于
`high_threat_m_to_n`。D4 逐项复核结果如下。

| 分类 | episode 数 | 主要证据 | 责任边界 |
| --- | ---: | --- | --- |
| D3-D4 计划代次错位 | 16 | 最后 D3 为 v2，最后 D4 仍绑定 v1 | main 发布顺序 |
| 当前 ACK 晚到未重评 | 11 | 必要 ACK 晚于最后 D4 决策 0.000067-0.082041 秒 | main 事件调度 |
| 重发和时域不足 | 1 | 两次计划广播可见，当前 ACK 在 2 秒内不可消费 | main 通信与尾窗 |

28 个失败包含 38 个未提交联盟，其中 23 个属于计划代次错位，15 个属于计划对齐但 ACK
未闭合。同场景 72 个通过样本中另有 35 个计划代次错位，说明旧计划的提交状态可能被
现有规则用于判定当前 episode 通过。200 对 200 的 20 个同场景样本全部错位。

### 安全性

全部未提交联盟的 necessary member 集合保持稳定，lease 到期时间为 5.7-5.9 秒，没有
在 2 秒 episode 内过期。旧计划、旧版本或旧 epoch 的拒绝符合预期。计划对齐且在最后
D4 决策前收齐 ACK 的 106 个联盟全部提交。D4 没有把部分 ACK 或
`collecting_member_acks` 当成执行许可。

冻结源码和当前源码的专项状态机测试均为 4/4，当前 D4 全量测试为 903/903。仅出现
Matplotlib `Axes3D` 环境警告，与联盟状态机无关。本轮诊断完成，代码未变，正式结果
未重跑。

### 后续

main 需修复 D3-D4 同代次发布、中心正常状态下的 ACK 事件重评、有界重发、终止排空和
逐消息审计。修复不得降低必要成员 ACK、epoch、lease、计划版本、成员身份或原子提交门。
修复会改变正式业务语义，必须在新的 clean source 下完整重跑并由 D6 独立审计 900 项。
详细逐 cell 证据见
`FORMAL_R0_COALITION_ACK_DIAGNOSTIC_20260730.md`。

## 2026-07-30 v7 来源独立只读评价

### 结论

冻结 v7 没有通过来源独立转移动作评价。validation 和 test 各含 9 个规则正类，actor
原始残差激活、实际 transfer change 和投影后 exact 正动作均为 0。两个划分的负类
exact R0 分别为 11/11 和 9/9。test 的 actor-derived 正类分母为 0，比率保持
`unavailable`。

train 出现 10 次 actor 边激活，其中只有 3 帧形成实际 transfer change；3 帧均为
规则负类，属于错误边和虚假转移。安全检查没有失败：train、validation、test 的投影
拒绝、不变量失败和完整 R0 raw action tuple 偏差均为 0。评价处置为
`failed_closed`，确定性 R0 继续作为唯一运行路径。

### 输入

| 项目 | 固定值 |
| --- | --- |
| 场景 | M16N24，8 区域 |
| source commit | `4a83a373f4eb4e29704bb3cf9f62e3d54eee3aec` |
| seed | 5216-5279 |
| episode / frame | 64 / 128 |
| train / validation / test | 90 / 20 / 18 |
| 规则正类 | 24 / 9 / 9 |
| dataset SHA-256 | `f6c52bdd4ce630ae40787226383caab7833f3b034adfb0fc7e93d9e30c90ce67` |
| split SHA-256 | `4179c0a766fa93b9127dc534176d69276face35fb110a8c247100d1807521215` |

评价硬绑定 generation plan、generation summary、batch summary、evidence、
derivation 和 export summary。对应文件或内容 SHA-256 为
`16ee1200...7d936`、`9ebaf151...bc905`、`992cf4cd...0692`、
`73b35dde...de5f6`、`2a8941fe...0ed4` 和 `793064c0...d055`。

### 方法

每帧先重算同快照 R0，再运行冻结 v7。raw 记录同时保存 actor 选择的有向边和相对 R0
真正发生变化的 transfer。随后运行确定性投影，将 target、R0 和 projected action
转换为同一可执行签名。评价分别统计 exact 正动作、负类 exact R0、方向、数量、错误边、
虚假转移、投影拒绝和不变量失败。

raw action tuple 与 R0 直接比较完整不可变数据类，覆盖资源配额增量、储备比例、侦察
优先级、hold、重规划、owner、plan、version、epoch、lease 和 reasons。projected
action 另行持久化，使投影器为守恒修改配额的行为不会被误写成学习节点动作。

外部三个 split 均只用于评价。模型 fit、checkpoint update、threshold tuning、
confidence calibration、candidate/input mutation、registration、admission、正式
holdout payload 和旧评价 payload 读取计数均为 0。

### 结果

| 划分 | 样本 | 正/负 | raw 激活 | transfer change | exact 正动作 | 负类 exact R0 | 正确有向边 | 虚假转移 | 投影拒绝 | 不变量失败 | 节点偏差 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| train | 90 | 24/66 | 10 | 3 | 0/24 | 63/66 | 0 | 3 | 0 | 0 | 0 |
| validation | 20 | 9/11 | 0 | 0 | 0/9 | 11/11 | 0 | 0 | 0 | 0 | 0 |
| test | 18 | 9/9 | 0 | 0 | 0/9 | 9/9 | 0 | 0 | 0 | 0 | 0 |

冻结 v4 TRAIN+VALIDATION 有 251 个唯一在线可观测键，外部数据有 92 个，精确交集为
0。该审计只覆盖冻结 v4 来源。候选训练来源 B 的完整特征载荷未提供给评价器，因此
全训练来源可观测键重合状态为 unavailable，不能由 seed 隔离替代该项。

### 完整性

| 内容 | SHA-256 |
| --- | --- |
| candidate manifest 内容 | `fe9b18f6da8d9daf6d443a89f4cc321a9bda7645be3367b69c4ac29b3ac4f45f` |
| training audit 内容 | `1d60fbd1e3841eddc76914f7dad4421ae024eaf4ff63190269dc1a2046f6385e` |
| source binding 内容 | `04f7986709c75c9138f10282aad678872ed74a2bfa1c82b506a5a202881c7002` |
| model 内容 | `bec99032bc176854f7ba265977ed35bf828d415be4bc260c9b6703a95d70082d` |
| state 文件 | `d0f7f17599fba382d9aa436c6ae34ef5f23b582a5ed9068f3475cb545b4f88f5` |
| candidate tree | `7bd5419f9d071d6c801f72415a8eb36ac0e36d259187e94229959f5f21d1a667` |
| raw source tree | `978f94c0165ce6f79446b601c8eddf5b2e157f641fab243582a3349250d5c9a1` |
| labeled root tree | `05a375853c42a31ecf3a20b2c61d9be6f2a7932d8a5125665f04d30ebc3e6d1b` |
| dataset tree | `0b88d9afbb0e0e98cb2c59dc950a98cc57c7f5d5bd22d762278fdd81ce6a9282` |
| frozen v4 tree | `2afd692874b91a23a5525448a0c5af98f3c2d96f0b12cebbf81a570d58d500d0` |
| summary 内容 | `956082ef5096fdff925aa694dd4c9bf4e84e5e2a4c35208a3b2389080af2a9f9` |
| artifact manifest 内容 | `e089bfcc91f9fc7dbd71ba0ffe4d73c43a31828ba80e3997c1594fadb5f2d057` |

五棵输入树评价前后一致。records JSONL/CSV 文件 SHA-256 为
`7785ded96360869edfb694c425321fa3323450cf1624607b53edf5d3eca6a5cd`
和 `b8403cf34d8014b193d90f960c34e19a977e65a8b5e79e01ecc36ebdb8f42680`。

### 权限与测试

候选未注册、仅开发影子、准入关闭、强制规则回退。没有置信校准器，固定置信门没有应用。
assist、authority、assignment、degradation、takeover、coalition、control、
physical、D3、D7、生产确认、实际采用和收益声明均为 false。

专项测试 21/21、D4 全量 903/903 和三个新增 Python 文件的 `py_compile` 通过。全量
测试只有既有 Matplotlib `Axes3D` 导入警告。本次没有启动 AirSim，也没有修改 AirSim
接口。

## 2026-07-30 v7 规则节点与转移残差开发验证

### 结论

v7 通过预先固定的 M16N24 开发门。VALIDATION 上 actor 原始残差激活为 6，exact
正动作为 2/9，负类 exact R0 为 9/11，不变量失败和 R0 节点字段偏差均为 0。v7
解决了 v6 节点动作与转移边脱节的问题，也将首版 v7 的新域负类全激活降为 2 个负类
虚假转移。

该结论只覆盖两个已知来源的 TRAIN/VALIDATION。M16N24 TRAIN 正类命中为 1/24，
VALIDATION 又参与 checkpoint 选择，当前证据不支持来源独立泛化、注册或运行采用。

### 输入和隔离

| 来源 | TRAIN | VALIDATION | 用途 |
| --- | ---: | ---: | --- |
| 冻结 v4 candidate dataset | 350 | 75 | TRAIN 拟合；VALIDATION 选模 |
| M16N24 labeled dataset | 89 | 20 | TRAIN 拟合；VALIDATION 选模 |

合并 TRAIN 有 84 个正帧、355 个负帧、84 条正残差边和 5260 条零残差边。类别权重、
边权重和来源权重均从合并 TRAIN 计算。VALIDATION 的参数拟合和权重拟合计数为 0。

M16N24 TEST 17 帧的 payload read/fit 为 0。seed 5216-5279、正式 holdout
1000-1019 和旧评价 3008-3039 均未读取。M16N24 数据集和 split 摘要分别为
`b1295091...2b42c` 和 `c767a48b...ae332`。

### 方法

每帧先运行确定性 R0。actor 只输出帧激活、有向转移边和绝对资源数，不输出节点动作。
raw `RegionResourceAction` tuple 整体继承 R0，包括 `resource_quota_delta`、储备比例、
侦察优先级、hold、重规划、owner、plan、version、epoch、lease 和 reasons。转移残差
与 R0 合并后，继续通过确定性投影和 v4 干预不变量。

损失只监督转移残差，包括边激活、帧内有向边排序、正边资源数、正帧激活和负帧
no-transfer 一致性。checkpoint 先比较投影后 exact 行为和安全失败，再比较验证损失。
开发门没有在构建之间修改。

### 结果

| 来源与划分 | 正类 | 负类 | exact 正动作 | 正确有向残差 | 负类 exact R0 | raw transfer | 投影拒绝 | 不变量失败 | 节点字段偏差 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 冻结 v4 TRAIN | 60 | 290 | 58/60 | 58/60 | 278/290 | 70 | 0 | 0 | 0 |
| 冻结 v4 VALIDATION | 15 | 60 | 13/15 | 13/15 | 58/60 | 17 | 0 | 0 | 0 |
| M16N24 TRAIN | 24 | 65 | 1/24 | 1/24 | 62/65 | 5 | 0 | 0 | 0 |
| M16N24 VALIDATION | 9 | 11 | 2/9 | 2/9 | 9/11 | 6 | 0 | 0 | 0 |

最佳 checkpoint 为 epoch 137。训练在 epoch 182 提前停止。M16N24 VALIDATION
达到 raw activation 大于 0、实际 transfer change 大于 0、exact 正动作大于 0、
负类 exact R0 至少 8/11、投影拒绝为 0、不变量失败为 0 和完整 action tuple 偏差为
0 的固定门。raw activation/transfer change 均为 6。

新域仍有 7/9 个正类未形成 exact 动作，2/11 个负类产生虚假转移。现阶段主要问题已从
“完全不激活”转为“正帧覆盖不足和少量负帧误激活”。本轮不继续调参，保留给来源独立
评价判断。

### 重复构建

相同冻结输入、配置和实现执行两次独立构建。两棵候选目录执行逐文件比较无差异。

| 内容 | SHA-256 |
| --- | --- |
| 模型参数内容 | `bec99032bc176854f7ba265977ed35bf828d415be4bc260c9b6703a95d70082d` |
| 状态文件 | `d0f7f17599fba382d9aa436c6ae34ef5f23b582a5ed9068f3475cb545b4f88f5` |
| 训练审计内容 | `1d60fbd1e3841eddc76914f7dad4421ae024eaf4ff63190269dc1a2046f6385e` |
| 候选 manifest 内容 | `fe9b18f6da8d9daf6d443a89f4cc321a9bda7645be3367b69c4ac29b3ac4f45f` |
| 候选树内容 | `b143a6bc6787c97d16a8ab58af23e02341e9ce42992cb50e4bcb049b4a04a2fa` |

候选 manifest 文件摘要为
`7da207acb00f89f1f9b34559fa5b456df412065ae7affd2c88957b776d698cfe`，
训练审计文件摘要为
`4ee26a00e23a7cb3f33d45fcbc5d4bbb8709814d6b9e6b38ac288d55e1072f37`。

### 测试

- v7 专项：19 passed；
- D4 全量：882 passed；
- 新增模块、构建入口和专项测试 `py_compile`：通过；
- 两个候选目录 `diff -qr`：无差异。

全量测试有 1 条既有 Matplotlib `Axes3D` 导入警告，不影响 D4 测试结果。该段记录候选
构建验证，当时没有启动 AirSim，也没有读取预留独立评价、TEST 或 holdout；后续只读
评价结果见页首。

### 权限和后续评价

候选保持未注册、仅开发和 shadow、准入关闭、强制规则回退。没有置信校准器，未应用
固定 0.60 门。assist、assignment、degradation、takeover、coalition、control、
physical、D3 和 D7 权限全部为 false。

下一步是冻结当前制品，由独立评价方使用全新来源只读检查。当前报告不包含
5216-5279、正式 holdout、AirSim、D3 successor、D7 控制或物理收益结果。

## 2026-07-30 v6 来源独立外部评价

### 结论

v6 没有通过来源独立转移动作评价。M16N24 外部数据有 42 个规则安全正类，actor 没有
激活任何原始转移边，投影后 exact 正动作命中为 0。test 的负类 exact R0 为 7/8。
候选保持未注册、准入关闭和规则回退。

### 输入

- 候选：`region_resource_a2_edge_transfer_shadow_v6`。
- 场景：M16N24，8 区域，64 个 episode，126 帧。
- seed：4016-4079。
- 外部 split：train 89 帧、validation 20 帧、test 17 帧。
- 外部规则正类：train 24、validation 9、test 9。
- 数据集 SHA-256：`b1295091...2b42c`。
- split SHA-256：`c767a48b...ae332`。
- source clean commit：`ed9e086e...2801e`。
- exporter clean commit：`9bdbe31d...d88a`。

外部三个 split 均未参与 v6 actor 训练、checkpoint 选择或阈值拟合。旧来源独立评价
seed 3008-3039 和正式 holdout seed 1000-1019 未读取。

### 结果

| 指标 | train | validation | test |
| --- | ---: | ---: | ---: |
| 样本 | 89 | 20 | 17 |
| 规则正类/负类 | 24/65 | 9/11 | 9/8 |
| actor 原始转移 | 0 | 0 | 0 |
| actor 投影转移 | 0 | 0 | 0 |
| 正确有向边 | 0 | 0 | 0 |
| exact 正动作 | 0/24 | 0/9 | 0/9 |
| 负类 exact R0 | 61/65 | 9/11 | 7/8 |
| 错误方向 | 0 | 0 | 0 |
| 错误数量 | 0 | 0 | 0 |
| 虚假转移 | 0 | 0 | 0 |
| 投影拒绝 | 0 | 0 | 0 |
| 不变量失败 | 6 | 6 | 3 |
| actor-derived 正类分母 | 0 | 0 | 0 |

错误方向和错误数量为 0，是因为 actor 没有生成转移，不能解释为边选择正确。不变量失败
来自 actor 的节点二值动作相对 R0 发生变化，但缺少对应转移，因
`candidate_transfer_missing` 和二值动作不一致被安全检查拒绝。

### 独立性和完整性

冻结 v4 TRAIN+VALIDATION 有 251 个唯一在线可观测键，外部数据有 94 个，精确交集为
0。train/validation/test 的外部唯一键为 70/14/10，与冻结输入的交集均为 0。键不使用
seed、episode、target 或 truth。

候选树前后 SHA-256 均为 `8c9d0179...1665e7`。外部输入树前后均为
`b0c1044b...f9f96`，dataset 树前后均为 `95b7f64c...11ff5`，冻结 v4 来源树前后均为
`2afd6928...00d0`。候选突变和输入突变均为 0。

### 数据用途和权限

模型拟合、checkpoint 更新、阈值拟合、置信门应用、注册和准入计数均为 0。v6 没有
置信校准器，未校准 `confidence_head` 没有用于 0.60 门。全部 assist、assignment、
degradation、takeover、coalition、control、physical、D3、D7 权限为 false。

机器结果和中文报告位于
`outputs/d4_v6_source_independent_external_evaluation_20260730/`。本次结果不能用于
原地修改 v6；后续若继续训练，应另立候选并使用新的 TRAIN 数据。

## 2026-07-29 v6 转移动作学习验证

### 结论

v6 已形成可重复的非退化开发候选。独立边激活头消除了首次原型把目标转移数量从 1 推高
到 3 的冲突，TRAIN/VALIDATION 投影拒绝均为 0。内部 exact 正动作命中为 58/60 和
13/15，与 v4 相同；负类基线动作保持为 255/290 和 55/60，低于 v4。该负类按“与 R0
无可执行差异”定义，允许 R0 自身带转移。候选不具备准入条件。

### 数据和配置

v6 只读取冻结数据的 TRAIN 350 帧和 VALIDATION 75 帧。TRAIN 有 60/290 个正负动作、
72/3848 条正/零边。TEST、正式 holdout seed 1000-1019 和来源独立评价 seed
3008-3039 的 payload 读取均为 0。随机种子为 20260730，隐藏维度 24，消息传递 2 轮，
最多 240 epoch。

### 结果

| 指标 | TRAIN | VALIDATION |
| --- | ---: | ---: |
| exact 正动作 | 58/60 | 13/15 |
| 正确有向边 | 58/60 | 13/15 |
| 负类基线动作保持 | 255/290 | 55/60 |
| no-transfer 偏置 | 0.033333 | 0.133333 |
| 投影拒绝 | 0 | 0 |
| 不变量失败 | 23 | 5 |

最佳 checkpoint 为 epoch 119，epoch 164 提前停止。两次独立构建逐文件无差异。候选
manifest 内容、训练审计内容、模型参数内容和状态文件 SHA-256 分别为
`f40064e7...66a83f`、`ebc1334d...4bee9a`、`c09d1719...ba9e6`、
`e92ea3aa...b6ea8`。

### 验证边界

v6 专项 12/12、D4 全量 855/855 通过。当前结果来自冻结 TRAIN/VALIDATION，不含新的
来源独立正类、AirSim、D3 successor、D7 权限或物理收益。固定 0.60 门和全部权限关闭。
详细审计见 `D4_V6_EDGE_TRANSFER_DEVELOPMENT_CANDIDATE_20260729.md`。

## 2026-07-29 v5 来源独立外部评价

### 结论

冻结 v5 候选未获得准入。M16N20 外部数据与旧开发数据的精确可观测键交集为 0，当前
输入具备来源独立性。63 帧中有 2 个规则安全正动作，冻结 actor 没有输出匹配动作，
actor-derived 正类分母不可用。全部 v5 得分为 0，固定 0.60 门通过 0/63，负类误接收
0/63，规则回退 63/63。

该试验建立了当前外部负类拒绝证据。它没有建立正类召回、正式泛化或生产准入证据。

### 设置

- 日期：2026-07-29。
- 场景：M16N20，8 个区域，32 个来源 episode，63 帧。
- seed：3008-3039。
- 场景族：nominal、dense crossing、evasive multilevel、delayed noisy，各 8 个
  episode。
- 冻结 actor：`region_resource_a2_executable_transfer_shadow_v4`。
- 冻结 calibrator：`region_resource_a2_confidence_knn_shadow_v5`。
- 固定置信门：0.60。
- 训练 seed：0-99；正式 holdout：1000-1019；设计 pilot：3000-3007。

评价没有拟合模型、更新权重、选择候选、调整门限、修改 split 或生成正类。在线 D4
recommendation 未用作教师标签。外部规则标签由同一快照离线重算的 R0 和既有一资源
安全转移过程生成。

### 结果

| split | episode | 帧 | 规则安全正动作 | actor-derived 正类 | 得分最小/均值/最大 | 门通过 | 负类误接收 | 回退 |
| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| train | 22 | 43 | 1 | 0 | 0/0/0 | 0 | 0 | 43 |
| validation | 5 | 10 | 1 | 0 | 0/0/0 | 0 | 0 | 10 |
| test | 5 | 10 | 0 | 0 | 0/0/0 | 0 | 0 | 10 |

冻结 actor 产生 16 个相对 R0 的可执行差异，其中 train/validation/test 为 12/2/2。
这些差异没有匹配两个规则安全正动作，因此不能进入 v5 正类分母。actor 与外部目标签名
相同的记录为 45 条，但其中没有规则安全正动作；R0 负类上的签名相同不能计为正类。

旧候选 TRAIN/VALIDATION 共 425 帧、251 个唯一可观测键。新数据 63 帧、41 个唯一键。
精确键交集为 0，新记录精确重合为 0。该审计不使用 seed、episode、目标或来源身份构造
输入键。

### 数据读取

D4 本次读取 train/validation/test payload 为 43/10/10。test 只用于冻结候选只读评分，
fit、weight fit、threshold fit、hyperparameter fit 和 selection 均为 0。main 此前
只读检查过同一 test 10 条记录，该过程事实在汇总中独立记录。正式 holdout 和 pilot
payload 读取为 0。

### 制品

评价输出位于
`outputs/d4_v5_source_independent_external_evaluation_20260729/`。关键摘要如下：

- 来源 dataset manifest 文件 SHA-256：
  `af12051917cfe9eedfc8587c953599112db62858e4b01820a16ddd5b0a10231d`；
- 标签 dataset 内容 SHA-256：
  `ed2fd4b1a4d50ec80e5abdaa35a1470cec03d419665ae0e08b7c4339e9b8887e`；
- 标签 split SHA-256：
  `cdaa40241195516eb1679f6ed0a8179f3d2365c9768f9ef9a44b6f85fabcefb6`；
- 来源推导文件 SHA-256：
  `ccf327717a293f63b5655e978202ff720f20c74bfd8ae401f2233cc590bb753a`；
- v4 候选树 SHA-256：
  `2afd692874b91a23a5525448a0c5af98f3c2d96f0b12cebbf81a570d58d500d0`；
- v5 候选树 SHA-256：
  `632f066fcad363531762e6b7a1ef0f21c03b7b0d0aa3b4cd39a16e4fbbf7c273`。

评价前后候选树摘要一致。新增评价专项 8/8，与既有 v5 候选专项合计 18/18、D4 全量
843/843 通过。全量测试只有既有 Matplotlib `Axes3D` 环境警告。

### 独立复核

D6 已独立重算本批制品。复核得到样本 43/10/10、规则安全正动作 1/1/0、
actor-derived 正类 0/0/0、63 个得分均为 0、0.60 门通过 0、负类误接收 0、
回退 63/63、旧/新唯一键 251/41 且重合 0、正式 holdout 读取 0，与 D4 结果一致。
正类分母仍不可用。

### 限制

当前只有一个 M16N20 配置和 63 帧。没有 actor-derived 正类，无法计算来源独立正类
召回。D6 独立复核已经完成，但没有改变这一分母缺口。正式 holdout、runtime
preflight、D3 successor、D7 权限、物理窗口和 AirSim 收益没有运行。v5 继续保持
unregistered、admission closed、rule fallback required，全部生产权限为 false。

## 2026-07-29 v4 独立审计与 v5 开发校准

### v4 独立审计

D6 对冻结 v4 候选执行独立只读复核。候选树 180 个文件、179 个 manifest artifact、
四个来源实现文件、模型、数据、切分和 v3 registry 均通过内容核验。TEST 只读取
manifest 元数据；候选 payload、builder read、D6 payload read、fit 和 weight fit
均为 0。

| split | 正类数 / 负类数 | 正类召回 | 负类特异度 | 最小越门正裕量 |
| --- | ---: | ---: | ---: | ---: |
| TRAIN | 58 / 292 | 0.206897 | 1.000000 | 0.000504935 |
| VALIDATION | 13 / 62 | 0.307692 | 1.000000 | 0.000504935 |

v4 没有负类越门，但正类召回低，且通过样本贴近 0.60 门。完整性审计通过，模型准入未
通过。v4 冻结为 development/shadow 对照，保持未注册和规则回退。

### v5 方法

v5 读取冻结 v4 actor 的实际 24 维 pooled latent。冻结 v4 `hidden_dim` 和 v5
`feature_dimension` 均为 24；这是冻结候选配置，不修改通用模型默认维度。校准器只使用
TRAIN 350 条记录的均值、标准差、标签和固定 11 近邻库存。VALIDATION 75 条记录只用于
开发审计，不拟合权重、阈值、超参数或模型。TEST 和正式 holdout payload 不读取。

开发门在构建前固定：TRAIN/VALIDATION 正类召回均不低于 0.80，负类特异度均为 1.0，
最小越门正裕量均不低于 0.02，固定门保持 0.60。

### v5 结果

| split | 正类数 / 负类数 | 正类召回 | 负类特异度 | 最小越门正裕量 | Brier |
| --- | ---: | ---: | ---: | ---: | ---: |
| TRAIN | 58 / 292 | 1.000000 | 1.000000 | 0.400000 | 0.000000 |
| VALIDATION | 13 / 62 | 1.000000 | 1.000000 | 0.209319 | 0.000485 |

v5 通过预置开发门。manifest 内容、manifest 文件、校准状态、校准摘要和 builder
源码 SHA-256 分别为 `83192d4f...2c52`、`caa77414...9459`、
`d8bd5437...12a3`、`7f0047f7...9c60` 和 `77e91e06...e1e0`。构建前后 v4 树摘要
保持 `2afd6928...00d0`，v3 registry 树摘要保持 `07c770b0...a93a`。

### v5 重合诊断

| 诊断项 | 结果 |
| --- | ---: |
| VALIDATION 记录 | 75 |
| 原始图键完全重合 | 42 |
| latent 完全重合 | 42 |
| 非完全重合且最近距离 `<1e-3` | 20 |
| 最近距离 `[1e-3,0.1)` | 10 |
| 最近距离 `>=0.1` | 3 |
| 最近 TRAIN 标签一致 | 75/75 |
| 正类完全重合 | 12/13 |

最近 latent 距离的 P50、P90 和 P95 分别为 0、0.0123058 和 0.0940144。诊断只读取
TRAIN/VALIDATION，拟合计数为 0；TEST 和正式 holdout payload 读取仍为 0。

### D6 最终审计

D6 通过固定外部哈希独立核验候选四个 artifact、v4 基线、v3 registry 树、数据用途和
全 false 权限，并独立复算原开发门。结果与候选摘要一致。TRAIN 全库存评分 self-match
为 350/350。

| 留组方式 | 正类召回 | 负类特异度 | Brier |
| --- | ---: | ---: | ---: |
| raw observable key | 0.965517 | 0.958904 | 0.037610440 |
| latent exact key | 0.965517 | 0.958904 | 0.037610440 |

VALIDATION exact overlap 为 42/75。移除 exact overlap 后只剩 33 条记录，其中正类仅
1 条；该分层的 recall 和 margin 因分母不足保持 unavailable。D6 未运行正式 holdout，
未授予任何权限。

### 证据边界

TRAIN Brier 为 0，说明近邻模型精确记住了训练 latent。VALIDATION 与 TRAIN 的高重合、
近邻标签 75/75 一致，说明当前结果不能证明来源独立泛化。v5 重分类为“记忆化开发对照，
等待来源独立扰动集”；独立性门失败，独立性与泛化 availability 均为 false。开发门通过
不关闭低召回 P1。D6 已完成当前制品的独立只读审计；v5 未运行正式 holdout、
runtime preflight、D3 successor、D7/物理窗口或收益评估。

候选保持 development only、shadow only、admission closed 和 rule fallback required。
全部生产、D3 和 D7 权限为 false，默认 loader 按未注册拒绝。定向 10/10、D4 全量
835/835 通过。全量测试仅出现环境中 Matplotlib 多版本导致 `Axes3D` 不可用的警告，
不影响本次 v5 路径。该测试结果是模块开发验证，不是 AirSim 或实飞结果。

## 2026-07-29 v4 落盘候选复核

候选由 clean commit `fd857457...7f848` 构建。现有 reviewer 从文件系统重新加载并重算
179 个 artifact，全部匹配 manifest。离线 development loader 成功；默认 loader 按
`v4_candidate_unregistered` 拒绝。

候选 manifest 内容、模型和数据集 SHA-256 分别为 `4f3e9735...7e116`、
`33a28060...b9fe5`、`b31fc43f...7fb8c`。从冻结 payload 重算 Actor 和 confidence 的
类别平衡、可辨识性和门限指标，结果与训练摘要完全一致。TRAIN 非零/零 edge 为
`72/3848`；TEST payload 未复制、未读取、未拟合。

fixture 置信度为 0.602367，裕量约 0.002367，只属于 training-domain smoke。全部权限
为 false，formal holdout、runtime preflight、D3 successor 和收益仍未完成。D6 独立
审计后结论见本报告首节。D4 完整审查见
`D4_V4_PERSISTED_CANDIDATE_IMMUTABILITY_REVIEW_20260729.md`。

## 2026-07-29 v4 observable-group 只读置信校准

本轮只读加载外部数据 `b31fc43f...7fb8c`，不调用候选 writer。数据含 TRAIN 350 帧和
VALIDATION 75 帧；test payload 读取和拟合均为 0。actor 最佳 epoch 107，train 正/负
命中 58/60、276/290，validation 为 13/15、58/60。

confidence train 标签为 58 正、292 负。14 条可执行错误硬负例的 TRAIN-only 权重为
20.857143，上限 32。原线性 head 使用固定 0.60 门、0.20 对数几率平方间隔和 0.003
学习率。完整复跑有 8 个合格 epoch，最长连续 7 个；最佳 epoch 66 的四类通过数为
train `12/0/0/12`、validation `4/0/0/4`。

首次 clean build 在 development fixture 处失败关闭。旧夹具的三项越界如下。

| 特征 | 旧夹具 | TRAIN 范围 | 固定 0.05 余量后的范围 |
| --- | ---: | ---: | ---: |
| D2 不确定度对数 | 最大 0.693147 | 0 至 0.122218 | -0.05 至 0.172218 |
| D5 视觉可见率 | 最小 0.20 | 0.85 至 1.0 | 0.80 至 1.05 |
| D5 视觉一致率 | 最小 0.20 | 0.87 至 1.0 | 0.82 至 1.05 |

只修正三项越界后，夹具置信度为 0.481511，投影转移为 0，仍不满足验收。新版本使用固定
4 区区域内代表。代表选择仅依据 TRAIN 的模型可见特征域、固定门和安全投影，不读取
target、reward、validation、test、seed 或来源身份。

同一数据的单次只读完整复跑中，新夹具不属于 OOD，置信度为 0.602367；原始和投影转移
均为 1，投影拒绝为 0，配额净和为 0，owner、epoch 和 lease 不变。treatment 的可执行
签名同时区别于同键 R0 和 source。TEST payload 读取与拟合仍为 0。

夹具指纹与 TRAIN 中的模型输入键完全一致，置信裕量为
`0.602367-0.60≈0.002367`。该结果归类为 training-domain smoke。独立泛化证据为
unavailable，正式验证声明为 false。薄裕量不能支持模型准入；独立未见图、正式 holdout
和扰动复跑仍需另行完成。

本结果只证明训练机制和 validation 固定门验收。后续 clean candidate 和 D4 不可变
review 已完成，状态见本报告首节。D6 对 v4/v5 的独立只读审计已完成；registry 登记、
D3 successor、运行采用和收益证据仍未完成。v4 全部生产权限仍为 false，v3、固定 OOD
0.05 和固定置信门 0.60 未修改。本轮治理收紧后专项 42/42、D4 全量 825/825 通过。

## 2026-07-29 D6 v2b 隔离双臂审计

### 场景与验收

本轮使用统一三维质点 development episode，不是 AirSim 或实飞。场景为名义
20 目标、20 资源、2 个侦察节点、8 个区域，窗口 3.2 秒，seeds 为 2003-2012。运行兼容
验收要求每个 seed 完成原始推理、运行门、安全投影和隔离采用，在线真值使用为 0，全部
生产权限保持 false。模型晋级还要求可辨识候选动作、完整同链物理映射和可用的正收益。

### 汇总结果

| 指标 | 结果 | 判定 |
| --- | ---: | --- |
| 原始推理 / 运行门 / 安全投影 / 隔离采用 | 10/10 | 运行兼容通过 |
| D3 后继 / development ACK / producer 物理摘要 | 1/10 | 覆盖不足 |
| `regional_hint_no_executable_successor` | 9/10 | 失败关闭 |
| 可辨识候选动作 | 0/10 | 未通过 |
| 在线真值使用 | 0 | 通过 |
| 配对非退化 | available / true | 仅限拦截数和最小距离 |
| 正收益 | unavailable / false | 未通过 |
| 生产权限 | 全部 false | 规则回退 |

seed 2007 是唯一形成后继、development ACK 和 producer 物理摘要的 case。control 与
treatment 各有 4 条 ACK 和 77 条 binding。D4 advisory、D3 后继、ACK 和 D7 指令可按同一
谱系重放；首次发布与 evaluation refresh 保持同一严格签名、authority epoch 和 lease。
19 条 D7 控制绑定中 18 条具有物理窗口，`INT-0004 / GT3D-000004` 因
`identity_mapping_unavailable` 缺少映射。该缺口由 D2/main 另行审计，D4 不补造
truth。

candidate 与规则臂的 D3 可执行 successor 字段相同，source 与 successor 的资源—目标
绑定及联盟绑定也没有变化。计划升版和开发 ACK 因而只证明隔离接线可以工作，不能归因于
学习候选。10 个 seed 的两臂拦截数均为 0，最小距离逐 seed 完全相同。有界非退化为
true，但没有严格改善。3.2 秒窗口、动作不可辨识和物理链不完整共同使正收益保持
unavailable/false。

### 当前结论

readiness v3 的 development 运行兼容性已经验证。模型收益和晋级没有通过。候选继续
development shadow，不开放普通 assist；生产分配、降级、接管、联盟提交、控制和模型
晋级权限全部为 false。运行路径保持确定性规则回退。下一轮应先形成投影后仍可由 D3 执行
且与规则臂不同的区域动作，再补齐同链物理窗口并重复 D6 配对审计。

## 2026-07-29 v3 隔离配对接口验证

本轮完成 D4 模块内接口和回归验证，未启动统一三维 control/treatment episode。测试使用
登记的 v3 registry 和 8-region 合同，development inventory 固定为 seeds 2003-2012。
旧正式保留 inventory 仍为 1000-1019。

专项用例覆盖以下路径：

- 自包含 registry 正常加载，候选 manifest、bundle、model state、策略版本和运行门身份
  一致；
- v3 `TTL=1.5`、最低置信度 0.60、分布外余量 0.05、预备比例 0.10 和预备资源 1 不可
  重配；
- manifest、model state、策略版本和 region scope 篡改或不匹配时失败关闭；
- 原始推理、动作一致性门、投影、下一周期隔离采用四阶段分别记录；
- 动作不一致、超时、分布外和非有限输出选择确定性规则；
- control/treatment 结果及 specification 支持 JSON round-trip；
- 旧 v1/v2 配对 schema、1000-1019 清单和默认 `TTL=1.0` 回归不变。

定向集合结果为 52/52 passed，D4 全量为 769/769 passed。全量测试只有既有 Matplotlib
`Axes3D` 环境警告，没有测试失败。

接口验证不提供场景收益数据。测试中的 passing candidate 用于检查状态转换和序列化；登记
模型另有实际推理用例，确认调用 bundle 内嵌运行门，并按真实门结果采用或回退。当前可以
确认 loader、门控、投影、advisory 和隔离 adoption 合同已接通。尚未确认 D3 后继计划、
隔离消费 ACK、物理窗口、两臂非退化或收益。

所有输出权限字段保持 false。`next_cycle_isolated_adoption=true` 只允许 main 在独立
treatment episode 的下一周期使用该 advisory；它不是生产 runtime ACK，也不开放 assist、
assignment、degradation、takeover、coalition commit 或 control。

## 2026-07-29 readiness v3 名义多 seed preflight

main 从 clean commit `83b8869b49c4ac26b6a5b6fb336dfe9af6960226` 加载固定 v3
registry，对 seeds 2003-2012 运行名义 development preflight。seeds 不属于训练 0-99，
也不与正式保留 1000-1019 重叠。每个 case 为 2.2 秒；每档批次门限为累计至少 20 帧、
分布内比例不低于 0.80、至少 1 帧完成模型评价。

| 场景 | recon | cases / frames | 分布内 | raw / gate / consistent / permitted | 回退 / 安全异常 |
| --- | ---: | ---: | ---: | --- | --- |
| 20v20 / 8-region | 2 | 10 / 30 | 30/30 | 30 / 30 / 30 / 30 | 0 / 0 |
| 200v200 / 8-region | 8 | 10 / 30 | 30/30 | 30 / 30 / 30 / 30 | 0 / 0 |

安全异常统计覆盖 online truth、gate truth、nonfinite、context/formal/permission mismatch
和 formal decision changed。两档 blocker、candidate blocker 和 fallback reason 均为空，
`paired_development_rollout_allowed=true`。

| 制品 | SHA-256 |
| --- | --- |
| 20v20 JSON | `5f97c81802dcd0cb3dddfa5ba85728c3cca47c728da8a79d4c7de9d085c53db9` |
| 200v200 JSON | `77a3ef455a9f155b30d8cf7f598121e4a8b66a17c6c2a2e0bac814ccf65d6cf4` |
| 两档中文报告 | `a37c16341eab4cc6c43cb883e2bb10f7e325ca5e7234bbac1bf5ac2aa26648b0` |

两份中文报告使用同一模板文本，因此文件哈希相同；不同规模、侦察节点数和 case 仍由各自
JSON 保存。本批关闭名义 10-seed 运行兼容性，只证明固定候选在两档名义输入上完成原始
推理和运行门检查。未形成实际区域干预、D3 后继计划、ACK、物理窗口、执行时延、规则基线
非退化或收益。正式 holdout 与全部权限继续关闭。

## 2026-07-29 readiness v3 单 seed development preflight

main 从 clean commit `83b8869b49c4ac26b6a5b6fb336dfe9af6960226` 加载固定 v3
registry。三组场景均运行 2.2 秒并产生 3 帧。验收阈值为至少 2 帧、分布内比例不低于
0.80、至少 1 帧完成模型评价。候选 manifest、模型和 gate 分别为
`7978aec0...ada2`、`ace5df6d...7f52d` 和 `77972834...6872`。

| 场景 | seed | region / recon | exit | 分布内 | raw / gate / consistent / permitted | 回退 |
| --- | ---: | --- | ---: | ---: | --- | ---: |
| 5v5 | 2000 | 2 / 2 | 2 | 0/3 | 0 / 0 / 0 / 0 | 规则回退 3 |
| 20v20 | 2001 | 8 / 2 | 0 | 3/3 | 3 / 3 / 3 / 3 | 0 |
| 200v200 | 2002 | 8 / 8 | 0 | 3/3 | 3 / 3 / 3 / 3 | 0 |

三组 finite 均为 true，在线 truth、gate truth、非有限值和 formal decision 变化数均为 0。
20v20 与 200v200 的 context、formal 和 permission mismatch 均为 0，blocker 为空，
`paired_development_rollout_allowed=true`。两份 JSON 的 SHA-256 为
`cd90ab75...a1b` 和 `cf98552f...7db`。

5v5 是 2-region 负例。候选声明适用域为 8-region，`candidate_scope_compatible=false`；
`distance_log` 与 `transfer_time_log` 各有 6/6 个边值越界。其 JSON SHA-256 为
`06458d5e...3ff`。exit 2 表示预期失败关闭，不是 v3 在 8-region 正例中的兼容性失败。

本批闭合单 seed 8-region 运行兼容性。后续名义 10-seed 结果见上一节；单 seed 结果自身
不提供执行时延、相对规则收益、实际接管或正式 holdout 证据。paired rollout 许可只是
开发试验入口。registry 内 `runtime_preflight_completed=false` 和全部权限字段保持不变。

## 2026-07-29 readiness v3 构建与登记

main 在 detached clean worktree commit
`4ba2c8a649dab157d55a2dd7817d5a8ded494114` 构建 v3。D4 独立调用 review loader，核对
候选身份、三来源、全局 seed 切分、1.5 秒投影合同、规则权重、四个安全门常数和权限后，
将 8 个文件逐字节登记到新 v3 registry。本轮没有启动 AirSim、main runtime preflight 或
正式 seed。

| 检查项 | 结果 |
| --- | --- |
| v3 投影配置 | reserve ratio 0.1 / reserve resources 1 / TTL 1.5 s |
| v3 规则权重 | 2.0 / 0.5 / 0.05 |
| 固定 OOD / confidence / cap / tolerance | 0.05 / 0.60 / 0.59 / 0.10 |
| validation 门后通过 | 293 / 344 |
| validation 动作不一致通过 | 0 |
| validation 通过动作一致率 | 1.0 |
| validation Brier | 0.056837453793788656 |
| 在线真值使用 | 0 |
| test / calibration / reserved 使用 | 0 / 0 / 0 |
| v3/v2 registry 联合专项 | 13 / 13 passed |
| D4 全量 | 754 / 754 passed |
| v3 clean-build / registry / 单 seed 8-region preflight | 已完成 / 已登记 / 已通过 |
| 正式评价和运行权限 | 关闭 |

实际哈希如下：

| 制品 | SHA-256 |
| --- | --- |
| 候选 manifest 文件 | `5e575ec4c0cd40ddb33ae9f06ce3b5ca015825c5ad3364733234349f143459c3` |
| 候选 manifest 内容 | `7978aec0bdf577571b9b85df10cf91f11a70f5d1b937f9dd5083bbf7e836ada2` |
| 模型权重 | `ace5df6dae62f8a9a80a4cd141d50a93427e609e4caa605b9962494ebfe7f52d` |
| 源码身份 | `e260ff2f69660142985569a73634920700325dbd6282b7e76e78a8a6562214ef` |
| 复合数据 | `5d174dd3526a0262990c5472556b024ac0306b33262fd805a38da16c999bee03` |
| 全局 split | `69ae1b0e40c6478ac62d65d89b1634f867d10b8167c523763741827a6f96d817` |
| 运行门 | `7797283405cad532f2911ea5965102f3b916c4ce6ccf60c17f955ea87e0e6872` |
| 登记文件树 | `07c770b05ffc70f190cd8b45d762d579857747e0efb12b472a2354ee5aeaa93a` |

源目录与 registry 的相对路径和逐文件 SHA-256 完全相同。隔离副本在禁止访问源数据 loader
时仍可加载和 review，篡改 bundle manifest 后失败关闭。v2 文件树继续保持
`324a5118...5010`。

上述结果是 shadow 候选构建和软件回归证据，不是 AirSim 性能或正式准入证据。后续单
seed 8-region preflight 已通过，2-region 负例按适用域拒绝，名义 10-seed 兼容性也已
闭合；扰动多 seed、配对非退化、收益和正式 holdout 仍未完成。全部权限为 false。

## 2026-07-28 readiness v2 构建与登记

main 在 detached clean worktree commit `891b542337ef065eee8c794d38dfa6ba382fea9e`
完成候选构建。D4 独立调用 review loader 复核后，将八个候选文件逐字节登记到独立 v2
registry。源目录和登记目录的相对路径、文件数量及逐文件 SHA-256 完全相同。本轮没有启动
AirSim、main runtime preflight 或正式 seed。

| 检查项 | 结果 |
| --- | --- |
| 第三 readiness 源 | 100 episode / 199 frame / 100 seed |
| readiness 零值 | 1572 / 1592 |
| readiness 范围 | [0, 1] |
| 在线真值 / dirty episode | 0 / 0 |
| 三来源复合视图 | 1100 episode / 2297 frame / 8 region |
| 全局数字 seed 切分 | 70 train / 15 validation / 15 untouched test |
| test / calibration / reserved 使用 | 0 / 0 / 0 |
| 固定 OOD / confidence / cap / tolerance | 0.05 / 0.60 / 0.59 / 0.10 |
| validation 原始门限通过 | 344 / 344 |
| 原始动作不一致通过 | 51 |
| validation 门后通过 | 293 / 344 |
| 门后动作不一致通过 | 0 |
| 门后通过动作一致率 | 1.0 |
| 门后 Brier | 0.056837453793788656 |
| 规则参考/记录标签 mismatch | 0 |
| validation 接受 | true |
| registry 专项 | 3 / 3 passed |
| v1/v2/运行门联合专项 | 37 / 37 passed |
| D4 全量 | 743 / 743 passed |
| clean v2 候选 | 已构建并逐字节登记 |
| main runtime preflight | 后续已执行但因 TTL 上下文不匹配未通过 |
| 正式评价和运行权限 | 关闭 |

候选 manifest 文件/内容、模型、源码身份、复合数据、split 和运行门配置 SHA-256 分别为
`c3194c90...af72b`、`48148034...3852f`、`ace5df6d...7f52d`、
`331b4f29...92ce0`、`996dbd66...493e`、`69ae1b0e...d817` 和
`acdcb781...cde`。运行源、动作课程源和 readiness 补样源内容地址为
`b06d741b...6158`、`7e17aba7...9e72`、`34244f1f...c56`。

测试证明 Advisor 使用同一个 projector、rule policy 和 formal decision 完成门内投影与
最终建议。匹配的非默认配置可运行；上下文或配置不匹配、门限降低、门参数或内容哈希篡改
均失败关闭。注册表测试在只复制候选八个文件、禁止访问三个源数据 loader 的条件下完成
加载和 review，篡改 bundle manifest 后按制品哈希拒绝。旧 v1/current-lineage 测试继续
通过。

validation 接受不等于运行准入。main 后续 preflight 在模型推理前发现 TTL 上下文不匹配，
因此仍未形成 OOD、时延、门应用 coverage 或模型输出分布证据。候选保持 development/
read-only shadow；全部权限为 false。

## 2026-07-28 八区域候选构建与专项测试

本轮完成离线候选构建和 D4 专项测试，没有启动 AirSim、正式 20-seed 或 900-cell。两个源
数据保持只读，seed 1000-1019 未进入训练、验证、测试或阈值选择。

| 项目 | 结果 |
| --- | --- |
| 运行特征源 | 900 episode / 1798 frame / 8 region |
| 动作课程源 | 100 episode / 300 frame / 4 region |
| 复合视图 | 1000 episode / 2098 frame / 8 region |
| 全局数字 seed 切分 | 70 train / 15 validation / 15 untouched test |
| 置信度拟合/审计样本 | 1468 train / 315 validation |
| 固定最低置信度 | 0.60 |
| validation Brier | 0.258170 -> 0.021107 |
| validation 十箱期望校准误差 | 0.028258 |
| validation 门限通过 | 315/315 |
| 门后动作一致 | 264/315，83.81% |
| 动作不一致但越过门限 | 51 |
| 校准接受 | false |
| test/reserved/truth/future 使用 | 0/0/0/0 |
| runtime preflight / 正式评价 | 已执行但未通过 / 禁止 |

置信度目标不是常量标签。validation 目标范围为 0.59 至 0.998032；动作不一致样本被限制在
0.59 以下。训练后的置信度头仍将 51 个不一致样本推到 0.60 以上，说明当前图级表示和回归
损失没有形成足够的门限分离。候选未因 Brier 改善而获得准入。

代表帧来自八区域运行数据，并用独立 seed 2000 注册为只读审计输入。结果为
`feature_ood=false`、特征违规 0、confidence 0.909641、
`candidate_failure_gate_passed=false`、`gate_pass=false`、
`identifiable_nonzero=false`、`candidate_executed=false`。唯一拒绝原因为
`candidate_confidence_calibration_not_accepted`。

候选身份如下：

| 制品 | SHA-256 |
| --- | --- |
| clean source commit | `923f3f6e91af0f85aed446c66420c834d2de63fb` |
| 候选 manifest 文件 | `ad5846b13652298a0b7b9428d1a21bcc3cbadb9cd605398ffcfde7fa5739f5e5` |
| 候选 manifest 内容 | `52866167cdb34200119c54af3fe6d6e1537fb81dd26e0596b9ca872011d05e2f` |
| 模型权重 | `43157f4ea6cee18fe575615b03661ab806a4217c9914c351b75638ccb082b0ee` |
| 源码身份 | `f9c527155ce38ee0190787784e4033ff0f5dbef1b476edad0d944111e5bd53ed` |
| 源码摘要文件 | `195c81cd49ac67a8ebfb1928536a46ad2c039d4a5abfd23ee14f533f400f4e1e` |
| bundle manifest | `824aecf1f6cfb1572693401f3789190ea3c7d5e41f870cfccad8204d8748cb8f` |
| 运行特征数据 | `b06d741bd22a0cd84ef1e47a48a0b8cd81ceb7e4ea294eeeb38b892e69d36158` |
| 动作课程数据 | `7e17aba7911602c1b9e9f5b917aea97f1eeec478f03963b119fbcfc8de299e72` |
| 复合数据 | `ee6bd2029f8754e77b731643e24acde5eb5451df154cf34644c067e756cdcfd4` |
| 全局 split | `69ae1b0e40c6478ac62d65d89b1634f867d10b8167c523763741827a6f96d817` |

2026-07-28 最终 registry 专项 14/14、D4 全量 720/720 通过。一个既有 Matplotlib
`Axes3D` 导入警告不影响本轮二维测试。main 已完成 2-region/8-region development
preflight，但结果未通过；正式评价继续阻断。

### 八区域候选开发预检

| 场景 | 帧数 | 分布内 | raw model execution | candidate-permitted execution |
| --- | ---: | ---: | ---: | ---: |
| 5v5/2 区域，seed 2000 | 3 | 0 | 0 | 0 |
| 200v200/8 区域，seed 2001 | 3 | 1 | 1 | 0 |

2 区域场景同时触发运行特征不匹配、无非回退模型评价、区域数超出候选适用域和置信度校准
未接受。8 区域场景的运行阻断为特征分布不匹配，候选阻断为置信度校准未接受。两组均为
有限状态，在线真值使用数为 0。

8 区域的 2 个 OOD 帧只有 `secondary_readiness` 越界。该特征训练范围为 [1.0, 1.0]，
运行范围为 [0.0, 1.0]；3 帧共 24 个节点值，16 个低于训练下界。双源重切分将 raw
execution 从 0 提高到 1，但运行分布仍未闭合。后续需补采真实 8-region、
`secondary_readiness=0` 运行帧，并修复 315 个验证样本中 51 个动作不一致却过 0.60 的
校准误接收。正式 20-seed/900-cell 继续禁止。

## 2026-07-28 当前谱系运行分布预检

main 使用冻结候选执行两组 development preflight。D4 只读核对输出，没有启动 AirSim、
修改主运行时或使用在线真值。

| 场景 | D4 快照 | OOD | 模型实际执行 | 在线真值 |
| --- | ---: | ---: | ---: | ---: |
| 5 资源/5 目标/2 区域，seed 2000 | 3 | 3 | 0 | 0 |
| 200 资源/200 目标/8 区域，seed 2001 | 2 | 2 | 0 | 0 |

两组均触发资源承诺、D1/D2、D5、二级节点、租约和通信范围偏移；2 区域场景还触发边距离与
转移时间偏移。逐特征预检与候选 OOD gate 一致，有限状态正常。当前候选只完成可信加载和
影子适配，不具运行分布兼容性，正式 20-seed 阻断。

冻结候选的 8 个原始文件已逐字节复制到受控 `model_registry`。源目录与登记目录
`diff -qr` 无差异。新增测试不替换固定哈希，直接从登记路径加载候选并生成一条 seed 2000
影子记录；执行源为规则回退，candidate executed 为 false，全部证据和权限字段为 false。
专项 **17/17**、D4 全量 **706/706** 通过。

源数据审计确认：900 episodes/1798 frames 的运行数据覆盖默认 8 区域主要运行特征，但目标
动作全为规则零动作；100 episodes/300 frames 的课程数据提供 hold 100、重规划 200、
非零配额 200 和转移 100。两者数字 seed 都是 0-99，原 split 不同，下一训练视图必须
全局原子重分割。seed 1000-1019 不使用。本轮没有重训或生成新权重。

## 2026-07-28 当前谱系候选构建与复核

本轮没有运行 AirSim 或正式多 seed。先验证当前谱系候选 builder、loader 和 reviewer。
临时 clean Git fixture 使用五个 seed：3 个训练、1 个验证、1 个未触碰测试。训练 2 个
epoch 后模型包可从磁盘加载，validation 非有限输出为 0；test payload、旧 calibration 和
seed 1000-1019 使用数均为 0。

负例覆盖 dirty worktree、后续干净源码提交、split overlap、权限改写、配置篡改和非有限
推理。全部负例失败关闭。新增专项 **8/8 passed**，D4 全量 **697/697 passed**。

main 分批提交后，D4 从 clean checkout commit
`b0d498d9e76e19e9045e127b6dae26ea164b3fa4` 运行默认冻结配置。实际候选构建成功，
随后 `review-only` 独立复核通过。

| 项目 | 结果 |
| --- | --- |
| 候选 manifest 文件 SHA-256 | `7cc10ad770bd95fcb813dbf3d16b17040ec5f41f80fe0dc53e3e291a32f4de64` |
| 模型权重 SHA-256 | `fd1b9c4cf7580083fadc04a70b87aa6439930eba764a970279611ccc57f30047` |
| 数据集 SHA-256 | `7e17aba7911602c1b9e9f5b917aea97f1eeec478f03963b119fbcfc8de299e72` |
| split SHA-256 | `b413fa810ae426ad143b713afac2c7a3366fae123e397054dbb9b0449d7b0c16` |
| source identity SHA-256 | `b81780cece11c792acb3113af2d4be48a19b51c0337a67c926b388197d09dfdf` |
| train / validation 样本 | 180 / 60 |
| validation 非有限输出 | 0 |
| test / calibration / reserved 使用 | 0 / 0 / 0 |
| 生命周期 / 最高模式 | development / shadow |
| 全部运行权限 | false |

固定门限的实际模型诊断只遍历 train 和 validation。train 为 168/180 安全非零、12/180
与基线相同；validation 为 54/60 安全非零、6/60 与基线相同。两组门控回退、资源不可行、
模型身份错配和非有限输出均为 0。训练和验证均属于候选开发过程，不能作为正式未见 seed。
该结果关闭“当前谱系实物未生成”和“当前谱系模型是否全 no-op”两个开发子项，不关闭 A2
准入、实际采用、系统收益、接管、分配或控制 P1。

## 2026-07-27 A2 实际模型校准诊断

本轮没有使用受控开发适配器。诊断直接加载
`region_resource_a2_development_calibrated_20260726_v1` 的实际模型权重，只读取候选
manifest 指定的 20 个 calibration seed。训练、验证和 seed 1000-1019 均未进入本批，
阈值没有调整。

| 项目 | 结果 |
| --- | ---: |
| calibration seed | 20 |
| 样本 | 420 |
| 固定候选门通过/回退 | 420/0 |
| 安全非零实际模型动作 | 76 |
| 资源不可行无操作 | 344 |
| 原始可执行动作签名 | 88 |
| 保留 seed 使用 | 0 |
| 在线真值使用 | 0 |
| 正式采用/收益/权限 | false |

置信度 min/mean/max 为 0.707421/0.972089/1.000000。动作分类固定使用 0 ms 功能性时延
覆盖，以免主机调度抖动改变分类；本批不提供时延性能数据，运行时 50 ms 门配置未改变。
76 个非零样本中，动作覆盖课程提供 60 个，延迟噪声 50/100/200 规模场景分别提供 6/6/4
个。字段累计为整数备用资源
197、请求重规划 40、资源配额 40、保持 20 和跨区转移 20。

344 个无操作均归为资源不可行。360 个样本至少有一个区域请求的整数备用资源超过
`available_resources - committed_resources`，其中 16 个样本仍有其他非零动作。该现象
来自严格正的备用比例输出和整数向上取整；区域资源已经全部承诺时，安全投影必须把备用资源
压回 0 或受保护基线。本批没有低置信、分布外、owner/lease/epoch、分区动作掩码或非有限
输出拒绝。88 种原始动作签名也不支持“模型整批输出同一动作”的判断。

候选 manifest SHA-256 为 `d3c96f0...36a2`，implementation lineage 与当前代码不一致。
20 个 seed 各包含 21 个样本；两次重跑的 76/344 分类、逐 seed 分母、样本身份摘要和分类
摘要一致。该批只记录历史谱系模型的非零观察，并定位 nominal 无操作的资源约束原因；当前
谱系开发证据为 false。它不证明 D3 后继计划采用、owner/coalition ACK、物理执行、独立 R0
或系统收益。全部权限保持 false。
紧凑 JSON 和中文结果位于
`region_resource_a2_actual_policy_calibration_20260727_v1/`。专项 **10/10 passed**，加入后
D4 全量 **689/689 passed**；未运行 AirSim 或正式大规模实验。

## 2026-07-27 提交就绪回归

本轮使用纯 Python 合同 fixture 复核 A2 安全采用、通信因果证据和三层 owner。新增负例
确认字符串 `"false"` 不能作为成员执行确认，非有限联盟执行时间、额外通信字段和真值前缀
字段均被拒绝。开发适配器在正式收益审计来源入口失败关闭。中心、二级和完全分布式正例的
证据链可用，但 authority、收益和在线真值使用均为 false。

专项回归为 **156/156 passed**，D4 全量为 **679/679 passed**。唯一警告来自既有
Matplotlib `Axes3D` 环境。本轮没有 AirSim episode、真实网络、独立同键 R0 或新增未见
随机种子，因此不形成 A2 收益和运行授权结论。

## 2026-07-27 A2 开发态候选验证

main 先使用固定最小区域的 hold+request helper 做了 20-seed 不落盘诊断，15 个 seed 形成
safe/auditable 链。seed 1000、1002、1007、1009、1013 没有形成 D3 后继计划。seed 1000
的直接原因为 `regional_hint_no_executable_successor`，下层原因为
`regional_hint_held_assignment_infeasible`。所选区域存在 committed binding，D3 拒绝
冻结该 assignment。该拒绝符合安全约束。

D4 随后增加受约束开发适配器。候选选择改为 request-replan-only 优先；没有该动作时才选择
总量不超过 1 个资源的 transfer；hold 只允许 `committed_resources=0` 的区域。适配器保留
原候选的 owner、plan、epoch 和 lease，并继续调用原投影器。

本次增加投影一致性复核。测试构造两个区域，其中区域 A 有 3 个可用资源、2 个已承诺资源和
1 个基线备用资源。原候选给出 `reserve_ratio=0.6`，未投影时表面对应 2 个备用资源；投影器
按可行备用上限把它裁回 1 个，与基线一致。旧判定会提前返回原候选，新判定确认该候选没有
D3 可消费干预，并继续生成 request-replan-only。

第二个回归把 committed member 只放在 formal decision 中，确认适配器首次选择时已使用
正式裁决。第三个回归把区域资源全部置于 committed + reserve 保护下，显式打开开发 request
开关后只生成 1 个 request-replan，不生成 hold 或 transfer。

五个问题 seed 已作为参数化模块回归。每个输入都在高需求区域设置 committed resource，
结果均只包含一个 request-replan，不包含 hold 和 transfer。确定性投影形成可辨识
`request_replan` 字段，安全采用装配在缺少 D3 输入时停在
`awaiting_d3_plan / d3_successor_plan_missing`。测试没有伪造后继计划，也没有降低
held-assignment 门。

新增样本的原候选投影干预为空；适配器候选包含 1 个 request-replan、0 个 hold、0 条
transfer，投影后干预字段非空。其余负例覆盖均衡场景保持无操作、已承诺区域禁止 hold、旧
epoch 被投影拒绝、assist 请求保持 shadow，以及开发策略不能进入正式收益审计。安全采用
专项 **68/68 passed**，D4 全量 **674/674 passed**，仅有既有 Matplotlib `Axes3D` 环境
警告。本轮未启动 AirSim。

随后运行 1 次不落盘 full episode。参数为 5 target、5 resource、1 recon、2 region、
duration 3.0 s、seed 1、radar detection probability 0.45。调用链使用真实
`ConstrainedDevelopmentRegionResourceAdapter`，首次选择和夹具二次投影均传入相同 formal
decision，并显式设置 `force_request_replan_on_projected_noop=true`。结果如下：

| 字段 | 结果 |
| --- | --- |
| A2 record | 1 |
| stage | `physical_window_available` |
| identifiable / safe / physical | true / true / true |
| D3 successor | `successor_published` |
| online truth use | 0 |
| authority / benefit | false / false |

该 full episode 使用 development-only admitted transport 夹具。标准 advisor 下适配器仍为
shadow，不能进入 assist。结果不能写成模型准入、收益或生产权限。

## 2026-07-27 A2 无操作归因复核

main/D6 于 2026-07-27 对 seed 1000-1019 的 A2 开发证据完成正确重算。20 个建议均已通过
确定性投影和消费链路，但逐区域资源配额均为零，跨区域转移为空，投影后资源数量和整数备用
资源均未变化，`hold=false`，`request_replan=false`。侦察优先级存在变化，但当前 D3
提示接口不消费该字段。

| 证据层级 | 修正结果 | 说明 |
| --- | ---: | --- |
| 投影/消费链路 | 20/20 | 证明候选链路可达 |
| 可辨识区域资源干预 | 0/20 | 没有 D3 可消费的状态或动作变化 |
| 实际 A2 动作采用 | 0/20 | 普通 D3 计划升版不能归因于 A2 |
| A2/R0 收益审计 | 0/20 | 无候选干预窗口，不进入收益比较 |
| assist/分配/接管/控制权限 | 0 | 全部保持 false |

此前 18 个 `safe_adoption_available=true` 来自同一时段的普通 D3 计划升版。该计数只说明
后继计划链存在，不能证明计划由 A2 无操作建议引起，已被本次结果取代。新门控在读取后继
计划前拒绝无操作建议，并阻止后继计划、确认和物理窗口附着。20 个拒绝原因均为
`identifiable_regional_intervention_missing`；批次 SHA-256 为
`ff3c10a089b6a94582451ae05d8a884af3a2bd7485acd4df0496442ea7e0ec55`。

纯 Python 安全采用专项为 **52/52 passed**。运行时集成专项修正后为 **6/6 passed**：
无操作建议返回 `regional_hint_no_executable_successor`，没有采用 ACK；显式
`hold/request_replan` 干预形成严格 successor 并输出 `new_execution_plan_applied`。D4
全量为 **658/658 passed**。本轮未运行 AirSim，也没有生成新的物理性能数据。

## 2026-07-27 A2 同键 R0 合同验证

### 结论

D4 已能从进程内安全采用对象或 episode 持久化 A2 JSON 生成相同的候选来源视图，并把候选
物理窗口与一个独立规则 R0 窗口组装为 D6 只读审计输入。该结果关闭模块软件合同缺口，不是
候选收益结果。

### 方法

正例使用相同 comparison key、场景版本、规模、seed、逻辑窗口和
`paired_exogenous_config_sha256` 构造 A2/R0 两臂。两臂使用不同 execution arm、episode
事件日志 ID/hash 和物理窗口 ID/hash。候选窗口绑定安全采用内容摘要、建议、D3 后继计划、
租约和物理窗口；R0 使用冻结确定性规则身份。

负例覆盖缺少 R0、持久化内容哈希篡改、候选计划版本错绑、跨 comparison key、重复 R0、
候选与 R0 复用事件日志/执行臂/物理窗口、窗口时长错误、计划或租约过期、窗口不完整、
未观察物理执行、硬约束违规和真值字段。

### 结果

验证日期为 2026-07-27。安全采用专项 **50/50 passed**，D4 全量
**655/655 passed**。所有结构篡改和证据复用负例均失败关闭；过期、不完整和硬约束负例均
输出 D6 不可审计。`a2_benefit_available`、`authority_granted` 和全部运行权限保持 false。

### 限制

测试为纯 Python 合同 fixture，没有启动 AirSim、真实网络或独立多 seed episode。没有结果
指标进入 D4，也没有计算 non-degradation。main 仍需生成实际 A2/R0 双 episode，D6 仍需
从两份独立事件日志计算收益。当前不能声明候选优于规则策略。

## 2026-07-27 A2 确认收据后续引用验证

本轮验证修复了同一 owner ACK 在后续物理窗口组装时被误判为跨证据复用的问题。确定性用例
在 `t=2.05 s` 首次验证确认，因缺物理窗口保持 `awaiting_physical_window`；在
`t=2.30 s` 继续引用相同收据并提供物理窗口，结果进入
`physical_window_available`。

反向用例修改 source、destination、authority、message ID、plan version、epoch、lease
scope、partition generation、payload digest 和 evidence kind，均失败关闭。评估时刻回退
返回 `decision_timestamp_rewind`，租约到期返回 `lease_expired`，同 receipt ID 内容冲突
返回 `receipt_conflict_replay`。

验证日期为 2026-07-27。通信与安全采用专项 **99/99 passed**，D4 全量
**637/637 passed**。测试为纯 Python 合同 fixture，没有启动 AirSim、真实网络或多随机种子
场景。该结果不证明 A2 收益；same-key R0 仍不可用。

## 0.000 2026-07-27 A2 公共确认合同验证

### 结论

main 所需的 owner ACK 和 coalition ACK 构造、严格解析、内容寻址回执及公共校验入口已经
补齐。owner ACK 现在同时绑定 D3 后继计划和 main 发布的 runtime assignment ACK。该修改
关闭 D4 模块 API 缺口，没有关闭 main 消息路由、物理执行窗口和 D6 同键对照缺口。

### 方法

正例从学习候选 fixture 经过确定性投影、严格后继计划和
`RegionResourceRuntimeAckEvidence`，构造 owner ACK transport payload，再模拟实际
delivered message。D4 从 delivered message 重新解析 payload、计算 receipt ID 和 payload
SHA-256，并通过公共 validator 核对 source/destination、计划、时期、租约、分区和双时间戳。

联盟正例使用原有 `CoalitionMemberAck` 字段构造嵌套 payload，验证目标、成员、联盟版本、
计划版本、时期、有效期及实际送达。负例分别篡改 runtime assignment ACK 摘要、删除 owner
payload 必填字段、删除嵌套 member 的 `global_track_id`。全部负例必须失败关闭。

### 结果

验证日期为 2026-07-27。运行时确认、安全采用、通信因果和联盟状态四文件联合
**130/130 passed**；D4 全量 **626/626 passed**。验收阈值为正例全部通过、负例全部拒绝、
`authority_granted` 为 0。测试为纯 Python 合同测试，没有 AirSim、真实网络、硬件或新增
随机种子。

### 限制

当前 main 实际 episode 尚未生产 owner ACK delivery、coalition delivery sidecar、采用后
物理窗口和 same-key R0。既有 formal 记录仍执行确定性规则回退，真实 learned adoption 为
0。缺失证据继续标记 unavailable，不填 0；A2 收益、assist、PPO 和运行 authority 均未
开放。

## 0.0000 2026-07-26 A2 安全采用合同验证

### 结论

真实候选安全采用的模块生产与验证合同已完成。该结果只证明错误或不完整的采用证据会被拒绝，
不证明现有学习候选已经被 main 实际采用，也不证明候选优于规则策略。

### 验证范围

专项测试构造了二级所有者和完全分布式对等所有者两类确定性 fixture。正例依次经过学习候选、
确定性资源投影、D3 严格后继计划、生产运行时确认、所有者实际投递确认、多成员联盟提交和
物理窗口。负例覆盖缺计划、缺确认、缺联盟、缺物理窗口、旧版本或时期、过期租约、非法转移、
容量超限、网络分区、中心正常误降级、二级优先级违反、真值/结果/奖励字段、规则回退、低置信
和载荷摘要错绑。

2026-07-26 的结果为专项 27/27、通信与既有 A2 装配器联合 100/100、D4 全量
621/621 passed。所有正例均为单元测试 fixture。本轮未启动 AirSim，未运行正式 seed
1000-1019，未产生真实网络回执或多随机种子物理窗口。

### 当前状态

现有 main 隔离记录仍为 `candidate_considered=false`，执行来源为确定性规则回退。真实学习
候选采用数仍为 0。main 尚需接入 D3 后继计划、owner ACK、联盟 ACK 和物理窗口；D6 尚需
形成同键规则基线、配对非退化和收益审计。在这些证据形成前，A2 assist、PPO、默认模型和
运行 authority 保持关闭。

## 0.000 2026-07-26 A2 证据装配验证

### 结论

D4 A2 证据装配器和严格加载器的软件正向路径已经通过。当前实际候选仍被 D6 外部审计拒绝，
没有生成 A2 外层包，没有改变 development/shadow 状态。

### 合成合同试验

试验生成一个完整的 development bundle、当前实现摘要、D6 通过型外审、seed 1000-1019
正式 scope、逐 seed runtime ACK、ACK 后物理窗口、唯一 same-key R0、paired
non-degradation 及完整联盟 ACK。装配器生成
`d4-region-resource-a2-evidence-bundle-v1`，strict loader 随后重新计算清单、摘要、候选
指纹、实现谱系和跨证据绑定。

| 检查范围 | 结果 |
|---|---:|
| A2 assembler 专项 | 17/17 passed |
| runtime/paired/reward/coalition/candidate 相关合同 | 124/124 passed |
| D4 全量模块测试 | 594/594 passed |
| `py_compile` | 4/4 入口通过 |

负例包含文件和内容哈希篡改、候选指纹错配、实现谱系过期、权限字段误开、低于 0.6、规则
回退冒充学习采用、后继计划未严格升版、旧 epoch、过期 lease、物理窗越界、R0/配对失败、
联盟 ACK 不完整、额外文件和覆盖已有输出。所有负例均失败关闭。

### 当前实物拒绝

实际输入使用现有 development bundle 和 D6
`d4_a2_external_audit_actual_20260726_final`。装配返回
`d6_external_audit_fail_closed`。D6 blocker 包括实现 evidence 缺失、正式 scope 及其
校验清单缺失、候选指纹不可用、正式 episode/实际采用不可用、物理状态窗口不可用、唯一
same-key R0 不可用、paired non-degradation 不可用及硬约束证据不可用。

拒绝前后，原 manifest、权重和训练清单 SHA-256 分别保持
`dad2adbe...c05c9`、`3da0360b...d5f62`、`ff3081c8...30dc6`，输出目录不存在。软件验证未
运行 AirSim、真实网络或正式物理 episode，也没有把 nominal 或 `active_risk` 规则回退计为
候选采用。

### 权限状态

合成正例的最高输出仅为 `a2_assist_eligible=true`。默认模型、PPO、模型晋级、故障接管权、
分配权和控制权均为 false，规则回退为 true。当前实物未达到该最高输出，A2 assist 仍未
授予。

## 0.00 2026-07-26 A2 development 候选训练与校准

### 结论

新版候选完成训练、validation 置信拟合和独立 calibration，并在固定门下形成正样本。候选
仍属于 development/shadow，不具备 assist、authority、production 或系统收益结论。

### 数据与切分

- 正式数据：900 episode、1798 frame、14384 action。
- clean supplemental：100 episode、300 frame、1200 action。
- 规范切分：train/validation/calibration 为 60/20/20 个 seed；对应样本为
  1259/419/420。
- 保留评估 seed：1000-1019；本次使用数为 0。
- 总动作正类：非零 quota 200、transfer 100、hold 100、request-replan 200。

### 训练

动作模型在 CPU 单线程运行 26 epoch 后早停，最佳 epoch 为 14，最佳 validation loss 为
0.073481。每 epoch 有效训练样本为 1979，其中正式样本 1079，补充样本 180 并重复 5 次。
置信头在 419 个 validation 正样本和 419 个合成 OOD 负样本上训练 50 epoch，最终二元交叉
熵为 0.033995。

### 校准结果

| 指标 | 结果 |
|---|---:|
| candidate considered | 420/420 |
| candidate gate-pass | 420/420 |
| 置信度 min/mean/max | 0.707421 / 0.972089 / 1.000000 |
| 时延 mean/P95/max | 0.834955 / 0.969215 / 1.294533 ms |
| 合成 OOD 拒绝 | 420/420 |
| Brier score | 0.004789 |
| 期望校准误差 | 0.028378 |
| 预测非零 quota | 40 |
| 预测 transfer | 20 |
| 预测 hold | 20 |
| 预测 request-replan | 40 |

固定门限为置信度 0.6、时延 50 ms、OOD margin 0.05。test/calibration 桶没有参与门限选择。
专项 fixture 还验证低置信、OOD、超时、非有限、旧 epoch、到期 lease、ACK 不完整、网络
分区和安全投影异常均回退规则。fixture 不代表实际系统收益。

### 产物与限制

候选清单文件 SHA-256 为
`d3c96f0abf059d6726b4706f8380a59687d8635898253cfa04f0a8a61df036a2`，权重
SHA-256 为 `cf393eaa2e7777e63645ef244f8e9bf733123fdc768f2610a91954c5f6c4632f`，组合
数据 SHA-256 为 `7779d1447b2a770851cb25de0b04a7ea5a1899c299d463d21b0b966fc20d318a`。
保留 seed 的实际候选采用、严格后继计划、运行 ACK、联盟成员通信回执、物理结果和 paired
non-degradation 尚未验证。后续必须由 main 调度隔离降级实验并由 D6 独立审计。

2026-07-26 D4 全量模块测试为 **577/577 passed**。本轮未运行 AirSim、真实网络或
reserved-seed 物理试验。

## 0.0A 2026-07-26 A2 证据装配审计

本节记录新版候选形成前的证据盘点。旧候选 0/20 门控结果继续作为冻结基线；新版候选的训练
和 calibration 结果见上一节，尚不能替代 reserved-seed 采用与物理结果。

本节记录当时的代码和制品链盘点，没有新增仿真场景或随机种子。D4 已有开发 bundle
完整性、候选运行采用、严格后继计划、联盟状态、成员通信投递和区域结果窗口合同；当时尚未
实现把这些合同与 D6 物理结果和 R0 配对非退化装配为新准入 bundle 的模块。该软件模块现已
按 0.000 节完成，真实外部制品仍不满足装配条件。现有 v2 bundle 继续为
development/shadow，未发现生产调用方通过裸布尔或占位摘要打开 assist/authority。

nominal 20-seed 的候选安全采用为 0/20；`active_risk` 20-seed 的 188/188 区域记录均执行
确定性规则回退且 `production_runtime_ack=false`。两批 evidence 不能拼接。后续只有在 D6
外部审计输出冻结、main 产生真实候选 `new_execution_plan_applied`、逐成员 delivered ACK、
采用后物理结果和同键 R0 非退化后，才进入 D4 专用装配器实现。本轮未改变算法、阈值、AirSim
接口或正式权限。

本轮验收阈值为零自晋级路径、零跨批证据拼接和 D4 全量回归零失败。结果为
**569/569 passed**；限制是没有新增仿真样本，不能据此评价候选效果。

## 0.0 2026-07-26 A2/C1/F1 准入复核

本轮执行代码合同审计，没有启动新仿真。D4 全量测试为 **569/569 passed**。新增验收点为：调用方自声明 `qualified/assist` 时，在创建 bundle 目录前拒绝；没有 admitted manifest 的注入策略即使提供 20 个未见 seed，也保持 shadow。旧 bundle 文件摘要复核不变。

正式 nominal 20-seed 干预中，D4 candidate considered 为 20/20，但置信度门通过 0/20、安全采用 0/20、规则回退 20/20；运行 ACK 和物理结果不可用。`active_risk` clean 20-seed 制品中，物理窗、描述性非退化和降级计划执行均为 20/20 可用，但 D4 候选 considered/adopted 为 0/20，188 条区域执行证据记录全部指向确定性规则回退，隔离 ACK 明确不是 production runtime ACK。两组结果都不满足模型准入。

main `d59352b` 的正式 scope 会绑定 bundle 文件树、设备、预检诊断和模型版本。D4 当前诊断仍为 `pending_runtime_shadow_gate`，因此 A2/C1/F1 正式 episode 为 0。剩余工作是新的证据绑定 promotion 合同、clean 未见 seed 降级候选实际采用、运行/联盟 ACK、采用后物理窗和 D6 配对非退化审计。

## 0. 2026-07-25 异步联盟确认

本轮针对真实通信下 M-to-N 联盟确认开展模块回归。原区域编排在提案快照末尾立即执行显式终结，网络 ACK 尚未到达时就把联盟永久置为 `aborted/missing_required_acks`。后续同一代次 ACK 即使全部送达，也无法恢复该状态。

修复后，提案无 ACK、一个 ACK 和两个 ACK 均保持 `collecting_acks`，执行授权为 0；第三个必要成员 ACK 在后续快照到达后，状态一次性转为 `committed`。显式终结和租约到期进入 `aborted`，网络分区撤销或重构已有提交。陈旧和无效 ACK 不进入确认位图，当前快照保持失败关闭；通信因果证据门继续拒绝旧 partition generation。

测试日期为 2026-07-25。新增 5 项异步生命周期用例；联盟、区域和通信证据三文件专项 **97 passed**，D4 全量 **569 passed**。验收标准为完整 ACK 前授权 0、完整 ACK 后原子提交、负例授权 0，全部满足。该组数字来自确定性纯 Python 合同测试。

main-owned scalable 3D 随后完成 2 目标、4 资源、1 个二级侦察节点的单随机种子集成复跑。随机种子为 `1271`，中心在 `1.5 s` 失效，通信时延为 `0.04 s`，无抖动和丢包。二级计划版本 2 在 `2.00 s` 发布；`2.05 s` 为 0/3 ACK 和 `collecting_acks`，`2.10 s` 为 3/3 ACK 和原子 `committed`。提交前两个主成员保持，提交后进入 `midcourse_pn_3d`；备用成员始终待命。在线真值使用和 `global_track_id` 改写均为 0。main-owned 模块栈为 66 passed，scalable 3D 全量为 272 passed。该系统证据仍不是 AirSim、多随机种子、真实网络或 200 对 200 性能结果。

## 1. 实验边界

本报告覆盖两类离线降级逻辑：中心节点失效后的被动降级连续性仿真，以及中心节点未失效但局部不确定性升高时的主动降级仲裁规则测试。节点通过内存网络交换粗粒度摘要，不涉及真实无线通信、火控参数、毁伤逻辑、实机飞控、硬件驱动、自动处置或绕过人工授权的流程。

2026-07-15 AirSim 证据严格限定为已完成的 20 个真实 M5N2 case。2026-07-20 D4-owned 证据包括区域 authority、区域资源建议和 next-cycle advisory 消费合同测试；main-owned scalable 3D 定向接口测试为 8/8。2026-07-21 增加正式数据审计、共享切分、区域动作覆盖课程和区域建议运行时确认接口。新增证据均为确定性纯 Python 合同验证，不是 AirSim、真实网络、硬件或长时运行结果。本轮没有启动新 AirSim episode。终止命令生效前额外完成的 `png_ttc_2v2_seed001` 不纳入 M5N2 聚合；其余 tuned case 未执行，dropout case 完成数为 0，缺失项保持 unavailable。

2026-07-21 又增加区域结果/奖励证据合同测试。19 个新增用例覆盖新执行计划、同代评估刷新、分项缺测不补零、ACK 缺失、旧 generation、租约过期、窗口重叠、执行与联盟绑定变化、快照/来源哈希篡改、在线真值字段和 D6 目标级诊断误用。新增专项 19/19，ACK 与奖励证据专项 52/52，D4 全量 449/449。测试使用单区域确定性 fixture，不是多 seed 性能试验。它证明 schema、公式和失败关闭逻辑可运行，没有提供正式 episode 的实际区域 reward、策略收益、物理执行或因果证据。

同日增加保留 seed 配对干预合同、冻结候选只读加载和候选门诊断。arm evidence 升级为 v2，保存 candidate confidence、冻结最小置信门、OOD、latency/limit、finite 和逐项 gate；v1 reader 在验证旧 manifest content ID 后迁移，未知诊断保持 unavailable。专项现为 33/33，D4 全量 482/482。当前权威 `formal_7891296` 已生成 nominal 5v5 seed 1000-1019 的正式 v2 execution receipts；D4 仅做只读复核，不改写该输出。2026-07-22，D6 在 `research_modules/d6_evaluation_metrics/outputs/reserved_seed_interventions_nominal_5v5_1000_1019_formal_7891296_d6_profile_bound_v2_audit_20260722/` 生成 profile-bound v2 outcome-availability sidecar，状态为 `pass_offline_assignment_comparison_only`；sidecar 文件 SHA256 为 `f3852251daf02ec87fe878e7fb80aad6f381d8c0756a5c956a32e737a3871c3b`，规范内容 SHA256 为 `c02a345c46ddc642dea7fb6bfcfb24184e7dc2a9f35b754c90324d074b445d2d`。该 sidecar 只使同帧离线分配比较可用；`formal_twenty_seed_performance_completed=false`，runtime ACK、物理结果、paired effect/non-degradation、counterfactual 和 causal 均保持 unavailable。

2026-07-22 又对 clean `8f86192` 与 `f80b5bd` 的 seed 42000-42002、三组 10 秒 200v200 运行执行 D4 跨提交只读审计。两侧各 30 条正式裁决和 30 条区域建议均通过原始 advisory 内容地址、正式裁决摘要、authority 摘要和摘要副本一致性检查。独立 D3 planner 的原始计划号规范化后，重新计算 authority、正式裁决和 advisory 三层内容身份，30/30 对载荷逐字段相同。该结果是同输入描述性等价证据；它不改变运行时原始 `advisory_id`，也不证明降级性能、真实通信或学习策略收益。

## 2. 实验目的

D4 验证中心节点异常时的保底策略：

- 使用 `C2Health` 状态机判断 `normal/degraded/suspect/failed`。
- 正常状态由中心节点统一融合、分配和发布计划。
- 中心节点失效后，优先降级到高空系留侦察无人机等二级节点，由二级节点作为区域协调者。
- 二级节点失效或不可用时，才进入完全无中心的 CBBA 风格协商。
- 优先考虑备份节点、二级侦察节点、lease 优先级和覆盖小区。
- 中心恢复后不允许靠单次心跳直接回到 normal，必须经过双轨合并和人工确认。
- CBBA 未收敛时只输出审计信息，不发布有效 assignment。
- 中心节点未失效但 D1/D2/D3/D5 风险升高时，由 `ActiveDegradationArbiter` 判断继续中心计划、请求中心重分配、请求二级节点辅助或安全保持；不转移 plan owner。

## 3. 二级节点降级层级

本阶段假设存在若干高空系留侦察无人机，作为区域二级节点。二级节点具备更稳定的视场和更大的通信覆盖，但在本模块中只作为离线协调与观测摘要源，不代表真实通信、控制或执行链路。

降级顺序为：

```text
中心 C2 正常
  -> 中心失效：二级侦察节点接管局部区域协调
  -> 二级节点失效或不可用：集群代表 / CBBA 完全无中心协商
  -> CBBA 不收敛：保持/继续观测/安全回退的离线状态
```

`ResourceSummary.node_role` 用于区分 `ground_backup`、`secondary_recon`、`cluster_representative` 和 `interceptor`。`coordinator_only=True` 表示该节点只做协调/观测摘要，不作为执行资源参与任务所有权分配。

## 4. 主动降级仲裁

主动降级不是中心被摧毁后的接管，而是中心仍在运行时的保守仲裁。D4 汇总四类输入：

- D1：`TrackUncertaintySummary`，表示定位协方差、位置标准差和量测年龄。
- D2：`AssociationRiskSummary`，表示关联 ambiguity、ID switch、重复航迹和连续性。
- D3：`AssignmentValiditySummary`，表示分配版本、是否 current、计划年龄、cost margin 和资源可行性。
- D5：`TerminalAssociationSummary`，表示末端视觉是否来自被指派 `resource_id`、是否 `locked`、是否多帧 `ambiguous/hold/reacquire`、是否与 assigned `global_track_id` 一致。

仲裁结论：

| 场景 | D4 输出 |
|---|---|
| D5 与分配目标一致，且 D1/D2/D3 风险低 | `continue_center` |
| D1/D2 风险上升但 D5 一致 | `request_secondary_assist`，请求二级节点辅助观测/cue |
| D3 分配 stale/not current 或资源不可行 | `request_center_replan` |
| 仅 cost margin 过低且 D5 一致 | `continue_center` 或请求二级 cue，继续观察 |
| D5 多帧非锁定但无观测 ID mismatch、资源错配、重复锁定或友方冲突 | `continue_center` 或 `request_secondary_assist` |
| D5 持续 global-track mismatch、资源错配或重复锁定 | 中心可用时 `request_center_replan` |
| 中心 failed，二级节点持续 ready | `degrade_to_secondary` |
| 中心 failed 且二级节点不可用/不覆盖 | `degrade_to_distributed` |
| 友方身份冲突 | `hold_for_review` |

该逻辑已由 `tests/test_active_degradation.py` 的规则测试覆盖。当前报告图表仍是被动降级/CBBA 通信退化曲线；主动降级的批量统计曲线应在后续 D6 集成后生成。

### 4.1 2026-07-15 secondary readiness/lease P0 边界验证

本次只运行 D4 Python 模块测试，未启动 AirSim。此前 278/278 验收覆盖 coordinator election、episode readiness DTO、secondary coalition proposal、resource lease 和 D6 metadata，但没有覆盖两个公开 secondary plan helper 对 sustained/source/epoch 的 `None`；此前“所有公开入口都已闭锁”的结论过度，现不再作为证据。新增矩阵对 `build_d7_secondary_handoff()` 与 `build_secondary_takeover_plan_metadata()` 逐项删除 readiness、expected/actual source、plan/required lease epoch、expiry/current time，并覆盖完整 evidence 与同一 active plan 维持正例。统一判定为仅 exact-true readiness、匹配 source、有效 epoch 且 `current_time < expiry` 的二级 plan 可 execute；interceptor peer distributed fallback 不使用二级视觉门。

验收命令为 `PYTHONPATH=research_modules/d4_distributed_fallback python3 -m pytest -q research_modules/d4_distributed_fallback/tests`，阈值为 100% 测试通过且任何不完整 readiness/source/epoch/time evidence 都不得产生 executable secondary owner。结果为 280/280 passed，满足阈值；本次样本为确定性单元测试，无 AirSim seed/episode 样本。剩余限制是未生成新的 AirSim、真实网络或物理任务证据；P1 自主成员形成、reserve 激活、补位/缩编/整盟重组也未实现。

### 4.2 2026-07-15 M5N2 中心负对照

| 项目 | 结果 | D4 解释 |
|---|---:|---|
| 完整 case | 20/20 | baseline/candidate 各 10 seeds |
| active degradation | 0 | 中心 owner 继续执行，无 secondary/distributed 动作 |
| coalition completion | 0/20 | M-to-N 联盟物理闭环未完成 |
| 第二 primary 进入 5 m | 0/20 | 第二 primary 仍是主要物理断点 |
| 第二 primary `collision_stop` | 20/20 | collision object 未记录，不能判定碰撞类型 |
| D4 main-bus mean/P95/max | 5.59/6.70/94.10 ms | 不是当前 control tick 的主要瓶颈 |

该批是负对照，不评价二级接管或完全分布式联盟性能。`collision_stop` 和 5 m 未闭合只进入诊断记录，不自动触发主动降级。D4 动作仍需 D1/D2/D3/D5 的可审计组合证据；本批没有这些降级条件，因此 `active degradation=0` 是预期行为。

验收阈值按证据域分开：中心负对照要求 `active degradation=0` 且 center owner 持续 current，本批满足；M-to-N 物理闭环要求第二 primary 进入 5 m 且 coalition completion 成立，本批 `0/20`，未满足；secondary/distributed 性能因本批未执行而标记 unavailable，不以零值替代。

### 4.3 2026-07-20 区域化 200v200 元数据与故障合同

新增 `test_regional_failover.py` 共 23 个确定性 test case。规模参数化用例分别构造 5、20、50、100、200 个 region，并为每个 region 构造一个 active task 和对应 resource metadata；这验证输入数组长度、region ownership 和 bus summary，不运行 200v200 动力学。其余 case 覆盖 scenario 声明 resource/recon 数量上限、中心健康时 D1/D2 风险只请求机动高空侦察辅助且 owner 保持 center、D3/D5 硬风险 fail closed、中心失效后二级 coverage/readiness 接管、二级失效后 distributed candidate、双区域 coverage 隔离、中心/二级/distributed `k>1` 完整/缺失 ACK、旧 ACK epoch、中心健康与 fallback 分区、旧 authority epoch/plan version、最早 task/authority lease、旧 secondary lease epoch、D5 member hold、单成员多能力与跨区域 capacity。

| 验收项 | 门限 | 结果 |
|---|---:|---:|
| 新增区域合同测试 | 23/23 | 23/23 passed |
| D4 全量测试（区域合同阶段） | 零失败 | 303/303 passed |
| 五档 metadata region/task 完整性 | 5/20/50/100/200 全部匹配 | 5/5 scales passed |
| 中心正常时 owner 转移 | 0 | 0 |
| `k>1` 缺 ACK 部分提交 | 0 | 0 |
| 旧 epoch/version、过期 lease、分区后执行 | 0 | 0 |

完整 `k=2` ACK 用例在中心、二级与 distributed 三层都只在两成员 ACK 均匹配 plan/coalition version、epoch 且最早 lease 有效后进入 `committed`。当前实现中，普通快照缺一 ACK 保持 `collecting_acks` 和零授权；显式截止或租约到期才进入 `aborted`。任一层级分区闭锁，已提交 coalition 遇分区转为 `reconfiguring`。该结果关闭 D4 模块内区域 authority 和安全合同；main 后续已经完成质点模块栈接口接线，但完整 CBBA/CCBBA 共识、全局组合最优性、reserve/补位/缩编/重构、AirSim、真实网络和物理拦截仍未关闭。

### 4.4 2026-07-20 区域资源建议与质点接口验证

原 `test_region_resource_advisor.py` 32 个 test case，验收阈值零失败，结果 32/32；当时 D4 全量为 335/335。参数化规模为 3、5、8、32 个区域，不固定 8 区或 200 架资源。安全用例覆盖资源守恒、最低备用、断边/网络分区、中心 owner、两个二级 owner、完全 distributed owner、旧 epoch、过期 lease、缺 ACK、fault fence 和 formal committed member 保护。研究管线用例覆盖 BC loss/update、原生 clipped PPO 有限更新、manifest/state_dict/SHA256、版本/SHA/OOD/timeout/低置信/非有限回退和 shadow formal verdict 不变。旧 split 用例只保证单个 `(scenario, seed)` group 不拆分，未证明相同数值 seed 跨场景/规模不泄漏；该缺口由 4.6 的 dataset-v1 回归关闭。

paired evaluator 的合成 19-seed case 按门槛拒绝 assist；合成 20-seed case 报告 backlog、transfer time、plan churn、communication load、fail-closed、安全违规和 candidate latency P50/P95。该 20-seed fixture 只测试 evaluator 逻辑，不是已训练模型的未见 seed 实验，不能作为 assist 推荐证据。后续虽已生成开发 checkpoint，但实际至少 20 个未见 seed paired suite、AirSim 或真实网络收益仍未形成，默认保持 disabled/shadow。

同日只读运行 main-owned `scalable_3d_simulation/tests/test_module_stack.py` 为 8/8 passed。已有测试验证：单一二级接管后 D3 plan version 提升且 owner 为 `RECON-001`；两个二级节点发布多 owner 区域 plan；中心和二级连续失效后发布 distributed 区域 plan；D7 仅在当前 owner、epoch、lease、commit 和 fault fence 下继续质点导引。该结果是接口/质点证据，不写成 AirSim、真实网络或实飞结果。

### 4.5 2026-07-20 下一周期 advisory 消费合同验证

在原 32 项基础上新增 15 个 pytest case，该消费合同阶段 `test_region_resource_advisor.py` 为 **47/47 passed**，D4 全量为 **350/350 passed**，验收阈值均为零失败；当前结果见 4.6。测试覆盖：`d4-region-resource-advisory-v1` 内容寻址 ID 与 JSON 回读、`projected=true`、scenario/snapshot/authority/创建时间/source plan/policy/model identity、默认 1.0 s 且受最早 lease 限制的有效期、逐区域 owner/epoch/lease 与 reserve/committed proof、逐 transfer endpoint generation 与 edge capacity proof、下一周期首次消费及同 ID 重放拒绝、严格过期边界、旧 snapshot/plan/epoch、ACK 不完整、fault fence、非 projected、总资源不守恒、未知/非邻接 transfer、partition/edge unavailable，以及 `k>1` formal committed member 不被转出。

规则 fallback 与学习候选共用同一 `DeterministicResourceProjector` 实例；学习测试替身只生成 raw proposal，advisor 输出才为 projected recommendation/advisory contract。序列化断言确认合同不含 `global_track_id`、actor truth ID 或 target ID，也不输出目标级分配。`RegionResourceAdvisoryGate` 当前重放记录是进程内状态，main 跨进程持久化 ledger 和真实 D3 planning-loop 消费尚未实现。

这 15 个 case 没有随机 seed、AirSim episode、训练后 checkpoint、物理运动或真实网络输入，只证明 D4 合同构造和 fail-closed 消费门。它不改变上一节 main 质点接口 8/8，也不增加 2026-07-15 AirSim 20-case 结果；正式至少 20 个未见 seed paired shadow、AirSim secondary/distributed 扰动和物理连续性仍开放。

### 4.6 2026-07-20 区域学习 episode 数据合同验证

`tests/test_region_resource_dataset.py` 当前 15 个 pytest case，结果 **15/15 passed**；`test_region_resource_advisor.py` 当前 **51/51 passed**，二者合计 **66/66**。共享切分、动作覆盖课程、全样本准入和运行时确认阶段分别达到 381/381、387/387、397/397 和 430/430。加入 19 项区域 reward 合同和候选门诊断回归后，2026-07-21 候选门诊断阶段全量为 **482/482 passed**；2026-07-25 当前全量为 **569/569 passed**。版本固定为 `d4-region-learning-dataset-v1`、`d4-region-resource-model-bundle-v2` 和 `d4-region-resource-observational-reward-v1`。

高基数正例仍为 96 episode/192 frame，正序和逆序输入得到相同 manifest，同数值 seed 不跨 split。复核新增：训练 target 重新验证 projector、owner/plan/version/epoch/lease、备用和 edge/quota 证明；中心、二级、distributed owner 序列化回读；manifest availability 与可重放 split 对 episode inventory 的一致性；truth/object/global-track key 变体拒绝；区域图规模增加到 200。BC/PPO 缺值仍失败关闭。

该结果只证明数据合同、确定性 split 和 fail-closed loader。96 episode 是程序生成的测试 fixture，不是正式导出，不含 AirSim 动力学或真实网络样本。正式数据、开发 checkpoint 和训练指标见 4.7；两类证据不能合并。main 后续 writer 仍需使用公开 source/frame DTO 和 D4 stage/finalize/load API，不应解析 D4 私有 JSON 结构。

### 4.7 正式数据审计与行为克隆开发训练

2026-07-20 正式数据包含 900 episode、1798 frame 和 14384 个区域动作。900 个 episode SHA256 全部通过，数据集 SHA256 为 `b06d741bd22a0cd84ef1e47a48a0b8cd81ceb7e4ea294eeeb38b892e69d36158`，split SHA256 为 `18a2c60097fefe05cb70ed811d28faf90c51bbbba0bbe984e07f23fb12f8d7f0`。训练、验证和内部测试按数值 seed 原子划分为 70/15/15，外部保留 seed 1000-1019 未进入数据。

固定随机 seed `20260720` 的复跑完成 66 epoch，最佳 epoch 54，训练耗时 66.02 秒。内部测试损失为 `0.071545`，保留比例平均绝对误差为 `0.000317`，侦察优先级平均绝对误差为 `0.000100`，端到端建议和确定性投影推理 P95 为 `0.7774 ms`。权重 SHA256 为 `3da0360be8788f3ffeb8e9f9eba3e0d5369ec0bdf9e05729dfb1db07d71d5f62`，与首次正式训练一致。

动作标签审计给出明确限制：14384 个动作中的非零配额、跨区域转移、保持和请求重规划数量均为 0。保持与重规划表面准确率为 `0.992593`，但两类都没有正样本；配额和转移的零误差同样只反映零动作基线。D6 审计中 898/1798 帧只有无归因相邻状态转移，reward、causal 和 counterfactual 可用数均为 0。训练器没有把这些相邻状态变化改写成回报。

当前结论为“管线可用但动作多样性不足，shadow-only”。bundle admission 保存动作计数，并固定 `action_diversity_sufficient=false`、`strategy_capability_claim_allowed=false`、`reward_evidence_available=false`。内部测试低损失不能用于宣称调度策略能力。没有 D6 可验证回报和外部 20-seed paired shadow 结果前，PPO 与 assist 均不可用。权重只保存在 ignored `outputs/`，文本结果仅记录配置、命令、指标、SHA256 和本地定位。

### 4.8 共享 seed 切分只读审计

2026-07-21，D4 使用独立消费者读取正式 shared registry，没有导入 main runtime。校验项包括 schema/policy、D3 兼容排序、consumer contract、content/assignment SHA256、源 training-seed-registry SHA、100 个 dataset seed 的完整覆盖、无额外 seed 和保留 seed 1000-1019 隔离。正式视图结果如下。

| 项目 | 原 D4 split | canonical view |
|---|---:|---:|
| 训练 seed | 70 | 60 |
| 验证 seed | 15 | 20 |
| 测试 seed | 15 | 20 |
| 训练 episode | 630 | 540 |
| 验证 episode | 135 | 180 |
| 测试 episode | 135 | 180 |
| 训练 frame | 1258 | 1079 |
| 验证 frame | 270 | 359 |
| 测试 frame | 270 | 360 |

数据集 SHA256 为 `b06d741bd22a0cd84ef1e47a48a0b8cd81ceb7e4ea294eeeb38b892e69d36158`；原 split SHA256 为 `18a2c60097fefe05cb70ed811d28faf90c51bbbba0bbe984e07f23fb12f8d7f0`；源 registry SHA256 为 `2ab928a476a4430b99326f245222f058bc5be5025158134ba89b01b3dec7815f`；共享 registry content SHA256 为 `29eb6895c4aa570b068f15141cbbbfede3041519117852d1ad48e848a25af146`，assignment SHA256 为 `31c6a3fc265d088d9958f44d579d8098e2aeab06b0daa60c68452ae4c6d46ab5`。

审计前后正式 D4 dataset 目录树 SHA256 均为 `8cde5cace4bd8106e35801f6179775ae39298592f3b556f712ea857b9c496bc1`。原 manifest 和 900 个 episode 文件未改写。新增 12 项测试覆盖成功映射、BC 显式选择、哈希篡改、漏/多 seed、保留 seed 和源 SHA 不匹配；该共享切分阶段 D4 全量为 381/381。该结果只证明跨模块数据切分治理可用。PPO 仍不可用，assist 仍关闭，行为克隆性能不因重新分桶自动更新；候选门诊断阶段全量为 482/482，2026-07-25 当前全量为 569/569。

### 4.9 区域动作覆盖补充课程

2026-07-21 使用正式训练 seed 注册表和共享切分注册表生成独立课程。main 在 detached clean worktree commit `9445ed6` 上完成当前证据生成。配置为 4 个区域、17 份聚合资源、100 个数值 seed，每 seed 生成保持、请求重规划和跨区转移三帧，共 100 episode/300 frame。正式 900 episode 目录及两个 registry 文件哈希在生成前后保持不变。

| 指标 | 结果 | 验收门限 |
|---|---:|---:|
| hold 正类 | 100 | > 0 |
| request-replan 正类 | 200 | > 0 |
| 非零 quota action | 200 | > 0 |
| transfer | 100 | > 0 |
| 硬约束违规 | 0 | 0 |
| 在线真值字段 | 0 | 0 |
| 保留 seed 泄漏 | 0 | 0 |
| reward available | 0/300 | 必须为 0 |
| PPO available | 否 | 必须为否 |
| online assist available | 否 | 必须为否 |

canonical 视图为 60/20/20 seed，对应 180/60/60 frame。训练桶含 hold 60、request-replan 120、非零 quota 120、transfer 60；验证和测试桶各含 20、40、40、20。clean 数据集 SHA256 为 `7e17aba7911602c1b9e9f5b917aea97f1eeec478f03963b119fbcfc8de299e72`，view SHA256 为 `9aa28765bc6e09fd912b2899716e8f0b046d538a0cb96da610519963784cc8de`。

专项测试 6/6、该阶段 D4 全量 387/387 通过。clean 课程的 dirty episode 数为 0，180 个 canonical 训练样本可由 BC 只读 view 消费，`behavior_cloning_manifest_available=true`；PPO loader 因 reward unavailable 拒绝，assist 和 authority 仍关闭。首次 dirty 课程只保留为开发期结构审计历史。该课程只补规则 teacher 动作覆盖，不构成模型收益或 AirSim 策略证据。

### 4.10 区域调度全样本准入审计

2026-07-21 使用 `d4-region-resource-full-sample-admission-audit-v1` 对两类冻结数据执行只读、失败关闭审计。正式数据位于 `research_modules/scalable_3d_simulation/outputs/learning_generation_v1_multibatchfix/learning_dataset/d4_region`；clean supplemental 课程位于 `research_modules/d4_distributed_fallback/outputs/region_action_coverage_curriculum_20260721_clean_9445ed6/dataset`。审计不修改两类数据，不训练模型，不生成权重，也不开放 online assist 或 authority。

| 数据 | episode | frame/sample | action | train/validation/test episode | train/validation/test sample | train/validation/test action |
|---|---:|---:|---:|---:|---:|---:|
| 正式数据 | 900 | 1798 | 14384 | 540/180/180 | 1079/359/360 | 8632/2872/2880 |
| clean supplemental | 100 | 300 | 1200 | 60/20/20 | 180/60/60 | 720/240/240 |

正式数据 900/900 episode 哈希通过，1798/1798 样本数值有限且安全合同有效。补充课程 100/100 episode 哈希通过，300/300 样本数值有限且安全合同有效。两类数据的 manifest/source/schema、规范 60/20/20 切分、资源配额守恒、transfer 邻接和容量、owner/plan/epoch/lease/version 单调与有效性、保留 seed、dirty 状态和真值隔离均通过，违规数为 0。补充课程动作覆盖为 hold 100、request-replan 200、非零 quota 200、transfer 100；正式数据四类正动作仍均为 0。

`target.kind=rule` 仅表示规则教师标签，`target` 字段名不属于真值泄漏。`recommendation.projected=true` 仅说明建议通过离线确定性安全投影，不能解释为 runtime applied ACK。当前数据没有显式投影前 action mask、被拒旧 plan/epoch/lease 候选、真实 `CoalitionMemberAck`、observed outcome、可归因 reward 或同 seed paired shadow；这些证据均标为 unavailable/pending。模块内正式、补充和联合全样本状态为 complete，D6 外部准入仍 pending。

审计专项 10/10、当时 D4 全量 397/397 通过。审计内容 SHA256 为 `94f4f4bf914dde9fee0ce1d92ac491902019dd7388502fbee5f96c4edfac3e7f`，tracked JSON 文件带外 SHA256 为 `4245f1db36f1af47259554f0770e75a3fe97fcc5e9b75c1b04c83d5bfb5c9e46`。D6 需按显式 JSON 路径和该带外哈希独立复核。复核完成、真实 ACK/outcome/reward 与 paired shadow 形成前，确定性规则、lease/epoch 和安全投影仍是唯一可执行路径。

### 4.11 区域建议运行时确认接口

2026-07-27 按非空干预合同重做运行时集成测试。5v5 无操作用例的配额、转移、资源、保持和
重规划动作均未变化。建议可消费，但 D3 返回 `regional_hint_no_executable_successor`，
保持原 plan ID/version，不刷新 authority/lease，也不发布 applied ACK。

第二个 5v5 用例显式加入一个受约束的 `hold/request_replan` 干预。D3 发布新 plan ID、
严格更高版本和指向源计划的 `previous_plan_id`，运行时验证器输出
`new_execution_plan_applied`。四项负例分别篡改 refresh 标志、执行变化标志、计划 ID 和
计划版本，全部失败关闭。运行时集成专项 **6/6 passed**，D4 全量 **658/658 passed**。
冻结 900 episode 没有这些 runtime 字段，`CoalitionMemberAck`、物理 outcome、可归因
reward、paired shadow、PPO、assist 和 authority 状态未改变。

### 4.12 冻结候选隔离加载与门诊断

2026-07-21，D4 对 `region_resource_bc_900_20260720/bundle` 增加只读、内容寻址的隔离加载验证。冻结 manifest SHA256 为 `dad2adbe9c36dd9ff8ee8bb3c11b1e07e66743c6f80dd8e956799208a10c05c9`，权重为 `3da0360be8788f3ffeb8e9f9eba3e0d5369ec0bdf9e05729dfb1db07d71d5f62`，训练清单为 `ff3081c8e320d9c8e1b032fb6234cd24159f0feedb1c6a706633cea6c1030dc6`。加载器同时复核 development 生命周期、shadow-only 最高模式、正式数据集和切分摘要，并在每次 raw inference 前后重新计算三文件指纹。

专项测试由 26 项增至 33 项。新增用例分别覆盖 low-confidence、OOD、timeout、nonfinite、四门组合、原 `0.6/50 ms` 边界和 v1 40-arm manifest 迁移；既有 bundle identity、pair input、authority/projection、next-cycle safety 和规则回退回归保持通过。明确拒绝码与旧 generic 汇总码可同时存在，但任何已评估单门失败都不能只留下 generic。

正式输入为 `research_modules/scalable_3d_simulation/outputs/reserved_seed_interventions_nominal_5v5_1000_1019_formal_7891296`，源验证日期 2026-07-21，D6 独立审计日期 2026-07-22，场景 nominal 5v5，源提交 `78912963b67fe86ee9a8d29186b18a9dd60c460c`。D4 对 `SHA256SUMS`、manifest、20 条 source lineage 和 40 条 arm evidence v2 做了只读复核，D6 随后按 profile-bound v2 合同独立重算。执行时延与门控汇总使用不同 P95 方法，必须分列。旧 v1 latency 只属于历史运行，不进入下表。

| 验收项 | 门限 | 结果 |
|---|---:|---:|
| 配对专项 | 33/33 | 33/33 passed |
| D4 全量 | 零失败 | 482/482 passed |
| `SHA256SUMS` 文件 SHA256 | `821f1503...72bc` | 匹配 |
| manifest SHA256 | `d6ef23b2...883c` | 匹配 |
| source lineage | 20 clean/finite，truth=0 | 20/20，20/20，0 |
| arm evidence schema | 全部 v2 | 40/40 |
| 冻结 bundle 读取前后 SHA 变化 | 0 | 0 |
| candidate considered | 20/20 | 20/20 |
| confidence min/mean/max | 诊断统计 | 0.508892953/0.563426384/0.569492280 |
| confidence 通过数 | `>=0.6` | 0/20 |
| OOD 通过数 | 全部通过 | 20/20 |
| latency 通过数 | `<=50 ms` | 20/20 |
| finite 通过数 | 全部通过 | 20/20 |
| failure gate 通过数 | 全部通过 | 20/20 |
| 执行时延 P95 | `treatment_candidate_latency_ms`，nearest-rank | 2.241315 ms |
| 门控汇总时延 P95 | `candidate_gate_summary.candidate_latency_ms`，线性插值 | 2.264415 ms |
| aggregate gate 通过数 | 全部门通过 | 0/20 |
| safe adopted | 必须由 aggregate gate 决定 | 0/20 |
| 明确阈值拒绝 | 分解到具体门 | `candidate_low_confidence`: 20 |
| generic 兼容理由 | 允许与明确理由并存 | `candidate_threshold_or_finite_gate_rejected`: 20 |
| 候选失败后规则回退 | 20/20 | 20/20 |
| PPO/assist/online authority | 全部 false | 全部 false |
| runtime ACK/outcome/causal 伪造 | 0 | 0 |

默认 `minimum_confidence=0.6` 未下调，正式 20 个 treatment 均继续规则回退，候选有效数仍为 0。bundle manifest 明确包含 `confidence_head_uncalibrated`；后续应在与训练和保留 seed 隔离的 calibration split 上报告 reliability/ECE/Brier，校准或重训 confidence head 后仍按同一 0.6 门复验。本轮没有修改 bundle、权重、manifest、当前 v2 正式输出或历史 v1 artifact，也没有开放 PPO/assist/authority。D6 availability sidecar 已形成，但 runtime ACK、post-intervention physical outcome、paired effect/non-degradation、counterfactual、causal 和故障场景降级策略效果仍不可用。nominal 5v5 只证明门控分解和失败回退，不能说明候选策略有效、优于规则或具有降级策略效果。

### 4.13 隔离 degraded rollout 合同验证

2026-07-21 本地运行 `test_region_resource_isolated_rollout.py`。测试使用单区域确定性合同 fixture，source seed 字段为 1000，但没有运行保留 seed 批次、AirSim、真实网络或质点多周期状态积分。验收目标是验证错误证据不能形成隔离候选采用。

| 验收项 | 结果 | 判据 |
|---|---:|---|
| `center_failed` 正例 | 通过 | secondary formal authority、严格新计划和隔离 receipt 一致 |
| `center_and_secondary_failed` 正例 | 通过 | distributed formal authority、严格新计划和隔离 receipt 一致 |
| `active_risk` 正例 | 通过 | 中心未失效、风险 action、严格新计划和隔离 receipt 一致 |
| 三类同代 evaluation refresh | 通过 | refresh 可记录，candidate adoption 必须为 false |
| 同版本、不同 plan ID | 拒绝 | 既非同身份 refresh，也不是严格更高版本 |
| 被动降级故障前 authority 作为 source | 拒绝 | source 必须匹配 formal secondary/distributed ownership |
| 低置信候选 | 通过 | `0.59 < 0.6`，仅规则 fallback 计划可继续 |
| 缺 ACK / receipt replay | 通过 | applied 和 candidate adoption 均为 false |
| 旧 epoch / 到期 lease / owner 篡改 | 通过 | authority gate 拒绝 |
| plan 或 ACK binding 篡改 | 通过 | binding SHA gate 拒绝 |
| same-generation binding 变化 | 通过 | refresh gate 拒绝 |
| 网络分区 / 缺联盟 ACK | 通过 | formal degraded execution 拒绝 |
| nominal 场景重标记 | 通过 | degraded evidence 不可用 |
| production ACK 伪标记 | 通过 | isolated ACK schema 拒绝 |
| 隔离专项 | 26/26 | 零失败 |
| D4 全量 | 508/508 | 零失败 |

三类正例输出 `isolated_simulation_only=true`、`production_runtime_ack=false`。它们只证明 D4 能验证来源、候选门、计划代次、authority 和隔离消费回执。physical outcome、paired non-degradation、counterfactual、causal、degradation effectiveness、PPO、assist 和 authority 均保持 false。main 尚未生成 arm-complete 多周期 rollout，D6 尚未接入干预后物理窗口，因此本节没有降级策略性能结果。

### 4.14 中心失效物理续跑适配审计

2026-07-22 审查 main 的中心失效 20-seed 物理续跑。20 个 pair 共生成 196 条区域采用记录。D7 世界命令已经写入隔离世界，D6 对 196 条记录的拒绝原因均为 `isolated_execution_plan_not_strictly_new`。

在线 D3 帧同时保存故障前 `previous_plan` 和故障后 `plan`。formal D4 decision 绑定故障后的当前 plan。现有物理 arm 从 `previous_plan` 重新求解，得到与 formal source 版本相同、计划标识不同的结果。D4 将该转换判为执行变化，但版本没有严格提高，因此拒绝。把 `previous_plan` 直接改作 source 也不成立：中心失效场景的 previous owner 是 center，中心与二级连续失效场景的 previous owner 是 secondary，均与当前 formal ownership 不符。

修正工作位于 main/D3 producer：以 formal current plan 为 source，再产生严格更高版本 applied plan；若实际世界只继续执行 formal current plan，则输出同身份、同 binding 的 evaluation refresh。D4 本轮只增加回归和说明，没有调整安全门。该 20-seed 结果证明错误代际被一致拒绝，不证明降级计划已采用，也不能用于 paired non-degradation 或策略效果结论。

### 4.15 区域通信因果证据合同

2026-07-25 运行 `test_communication_causal_evidence.py` 和 D4 全量回归。实验对象是 D4 本地 Python 合同，不启动 AirSim、不修改 main 运行栈，也不模拟真实无线链路。

| 验收项 | 样本或规模 | 结果 |
|---|---:|---:|
| 二级 readiness 实际投递正例 | 5/20/50/100/200 | 全部通过 |
| 区域计划逐成员投递 | 5/20/50/100/200 | 全部通过 |
| 联盟成员 ACK 逐成员投递 | 5/20/50/100/200 | 全部通过 |
| 正序与逆序验证 | 五档规模 | 结果一致 |
| 精确 receipt 重复 | 同 receipt、同 expectation | 幂等通过 |
| 内容冲突重放 | 同 receipt ID、不同摘要 | 失败关闭 |
| 跨证据复用 | 同 receipt、不同 expectation | 失败关闭 |
| 缺回执 | 三类入口 | `receipt_missing` |
| 错源/目的/类型/authority | 参数化负例 | 失败关闭 |
| 旧 plan/epoch、过期 lease、晚到 | 参数化负例 | 失败关闭 |
| 分区代次和 payload digest 不一致 | 参数化负例 | 失败关闭 |
| payload 缺必填字段 | 8 个字段逐项删除 | 构造失败 |
| envelope source/time/topic 冲突 | 参数化负例 | 构造失败 |
| truth 字段 | payload truth ID | 构造失败 |
| 专项测试 | 56 | 56/56 passed |
| D4 全量（加入异步联盟回归后） | 569 | 569/569 passed |

main 的系统复现条件为 5v5 `center_failure`、duration 3.2 秒、通信关闭、雷达探测概率 1.0。原运行在 2.0/3.0 秒仍有 8/8 区域 `selected_layer=secondary` 且 `execution_allowed=true`，自报 heartbeat/communication/sustained readiness 全为 true。D4 合同测试保留相同语义：八个区域即使自报全部为真，只要没有 delivered receipt，就全部返回 `receipt_missing`，且验证结果固定 `authority_granted=false`。

main 已让 readiness、区域计划和成员 ACK 经过实际 `DeterministicCommunicationNetwork`，并把 gate 结果接入区域 `execution_allowed`。8/8 通信关闭系统负例已转为失败关闭。随机种子 `1271` 的异步三成员系统正例也已通过：二级计划版本 2 发布后先出现 0/3 ACK 的保持帧，随后 3/3 ACK 原子提交；主成员释放，备用成员待命。AirSim 多随机种子、真实网络和正式矩阵仍待复跑。

## 5. 默认被动降级场景

运行命令：

```bash
python3 research_modules/d4_distributed_fallback/scripts/run_failover_simulation.py --nodes 5 --tasks 4 --packet-loss 0.10 --seed 7
```

| 项目 | 设置 |
|---|---:|
| 节点数 | 5 |
| 连续性任务数 | 4 |
| 中心故障时间 | 30.0 s |
| heartbeat warning | 1.0 s |
| suspect 阈值 | 2.0 s |
| failed 阈值 | 4.0 s |
| 网络延迟 | 0.1-0.5 s |
| 默认丢包率 | 10% |
| CBBA round period | 0.5 s |

## 6. 样例结果

| 指标 | 数值 |
|---|---:|
| 接管开始时间 | 34.0 s |
| 接管完成时间 | 36.0 s |
| 接管耗时 | 6.0 s |
| 共识轮数 | 5 |
| 任务完成率 | 1.0 |
| transient conflict count | 5 |
| messages sent | 80 |
| messages delivered | 73 |
| messages dropped | 7 |
| estimated bytes | 22404 |

## 7. 图表与曲线

### 7.1 丢包率对降级接管的影响

![D4 丢包率与接管性能曲线](failover_packet_loss_curve.png)

图中横轴为丢包率，曲线同时展示接管耗时、共识轮数和任务完成率。它用于判断分布式降级是否在通信质量下降时仍能保守运行。若 CBBA 不收敛，当前实现会输出空的安全保持结果，而不是把不一致分配当成成功。

## 8. 结果解读

- 中心故障后，状态机先进入 `failed`，再启动降级规划。
- 当存在可用二级侦察节点时，`coordination_mode=secondary_node`，二级节点承担局部协调者角色。
- 当二级节点不可用时，系统才切换到 `coordination_mode=distributed_cbba`。
- 备份/二级节点/lease 优先级先于普通资源质量排序，可避免“能力强但不是协调节点”的资源抢占接管权。
- 非收敛 CBBA 结果不再写入有效分配，这可以防止 D6 将失败降级错误统计为完成。
- 中心恢复必须通过 `merge_recovery()` 的双轨校验和人工接受，不允许由一次 heartbeat 自动恢复 normal。
- 主动降级中，D5 与中心/二级分配一致时不会直接切到完全分布式；只有多帧末端不一致或二级节点不可用时才进入更强降级。

## 9. 结论

D4 当前适合作为“中心节点、机动高空二级侦察节点、完全分布式”三级被动降级链路，以及“中心未失效但局部证据冲突”的主动降级仲裁框架。区域 authority、secondary resource、plan、owner、epoch/version/lease 和 `k>1` 原子 ACK 已执行 fail-closed，但 bounded bid selection 不是完整 CCBBA，该模块结果也不是 AirSim/scalable3d 物理闭环或自主成员补位证明。系统应继续通过 D3/D5/D6 的统一合同传递 `plan_id/version/authorization_state`、`global_track_id`、`risk_factors` 和 `terminal_consistent`。

区域学习 dataset-v1 已形成正式 900 episode 数据和可复现的 development checkpoint。独立补充课程已提供四类规则教师正样本，两类数据的 D4 全样本准入均为 complete，但仍没有 runtime applied ACK、动作执行结果或 reward。证据只支持数据结构、有限值、动作覆盖和确定性安全合同；D6 外部复核、回报归因、外部保留种子和成对收益不足以支持策略能力结论。bundle-v2 继续强制 shadow-only，其 manifest/SHA 溯源不能替代 paired 性能报告，也不改变 D4 主动/被动降级控制逻辑。

M5N2 中心负对照已完成 20/20，但 coalition 和第二 primary 5 m 均为 0/20；这说明物理协同闭环仍开放，不说明 D4 fallback 失败。本批未执行二级或完全分布式接管，真实 secondary/distributed 多 seed 继续列为 P1。后续必须补 collision object，并运行同 seeds 的中心失效、中心与二级连续失效和可审计主动风险 paired case。
