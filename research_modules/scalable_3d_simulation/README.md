# Scalable 3D Simulation

## A3 动作角色补采处理（2026-08-01）

main 新增显式 `balanced_action_role_v1` 主动视觉采集配置。默认
`operational_v1` 不改变既有相机执行和侦察线索行为。补采配置在非 `hold` 相机命令执行后，
按实际方位、俯仰和视场变化给出 0.12-0.30 秒的有界稳定期；下一决策时刻由 D5 现有
规则读取 `action_in_progress_until`，自然输出 `hold`。侦察线索每 1.0 秒设置 0.45 秒的
有界暂失窗口。窗口保留中心计划、航迹和版本，只停止生成该侦察相机的目标投影，因此 D5
规则输出 `search_sector`，不删除或换绑 `global_track_id`。

处理配置、稳定期参数和线索暂失参数均进入 runtime profile、episode manifest 和 generation
plan。`run_learning_dataset.py` 要求 balanced 配置同时显式启用只读侦察航迹线索；schedule
声明与命令行不一致时在 episode 运行前失败关闭。新 schedule
`d5_a3_source_independent_point_mass_v2.json` 使用 seed `22000-22099`，与旧语料
`21000-21099`、开发探针 `21900-21909` 和正式保留 `1000-1019` 均无重叠。

2026-08-01 的 10-seed 脏工作树开发探针仅验证动作可达性，共 1182 个规则样本：
`hold/interceptor=445`、`hold/recon=89`、`search_sector/recon=51`，三个单元均覆盖
10 个完整 episode 和 10 个 seed；在线真值使用为 0。该探针不作为训练、来源或晋级证据。
main 定向回归为 `159 passed, 1 warning`。完整 clean 100-seed 语料、D5 严格训练门和
D6 独立来源审计仍待执行，A3 的 BC、PPO、assist、promotion 和全部 authority 保持 false。

## A3 主动视觉来源域合同（2026-07-31）

D5 在提交 `e16f3e0` 中将主动视觉来源固定为五类显式枚举：历史未分类、软件夹具、
可扩展三维质点运行、AirSim 运行声明和真实相机运行声明。只有软件夹具可以携带
`synthetic_fixture=true`；新写入的非夹具制品必须显式携带来源域。历史无来源制品保持
保守分类，不能通过补字段升级证据等级。D5 全量回归为 `769 passed, 2 warnings`。

main 在提交 `1fe66ff` 中把集成质点 episode 导出为
`scalable_3d_point_mass_runtime`、`synthetic_fixture=false` 和
`simulation_research`。该字段来自 D5 的统一证据等级映射，不在 main 中维护第二套定义。
可扩展三维全量回归为 `445 passed, 1 warning`。

D6 在提交 `4df42ab` 中实现不调用 D5 高层校验器的独立只读审计。它从
`SHA256SUMS`、manifest、独立 descriptor 和 gzip 在线流重新核对来源、哈希、干净来源身份、
whole-seed 拆分和在线真值隔离。每个基础软件夹具包含 5 个 episode、seed `200-204`；
12 项测试分别构造来源域和篡改变体。专项为 `12 passed, 1 warning`，D6 全量为
`1360 passed, 1 warning`。

main 已从 clean `4a8c117` 使用新非正式 seed `21000-21099` 完成来源独立 A3 质点语料。
100 个 episode 覆盖 9 类场景、5 档规模和 45 个场景-规模单元，最终得到 159487 个样本；
正式保留 seed `1000-1019` 重叠为 0，在线真值使用和 checkpoint 恢复均为 0。D6 对 302 个
制品执行独立低层审计，12/12 检查通过，状态为
`simulation_research_integrity_confirmed`。

D5 的仿真研究来源门通过，但训练覆盖门失败关闭。训练集 102610 个样本中没有 `hold`，
侦察相机没有 `search_sector`；补采计划要求分别为 `hold/interceptor`、`hold/recon` 和
`search_sector/recon` 使用至少 2 个新训练 seed。当前不训练或晋级 A3。AirSim/真实相机
外部证明、模型准入、辅助、分配、降级、运行、生产、控制和 `global_track_id` 写权限全部
保持 false。完整结果见
[`docs/SCALABLE_3D_D5_A3_SOURCE_INDEPENDENT_CORPUS_20260731_CN.md`](docs/SCALABLE_3D_D5_A3_SOURCE_INDEPENDENT_CORPUS_20260731_CN.md)。

## 正式 R0 新批次分片 0-9（2026-07-31）

clean commit `80e55eb` 已冻结新的 5700 单元父清单和 900 单元 R0 作用域，execution
plan SHA-256 为
`b922ff5f95864345efa583da7256935694e5c675529989a659716522a0d7590e`。
20 个分片中的 shard 0-9 均完成 45/45，覆盖 seed 1000-1009、9 类场景和五档规模。
450 个单元均为有限状态，在线真值使用为 0，未发生孤立单元恢复。

D6 v12 使用哈希绑定的真值隔离制品重新汇总严格身份指标。严格 ID Switch 为
414/450 available，可用项合计 893，169 个 episode 为非零；36 个 episode 失败关闭，
其中 27 个是一条全局航迹对应多个真值目标，9 个是源观测超出谱系时间窗。在线 D2
producer 诊断仍为 0/450 available，这是在线无真值合同，未被当成严格指标。episode
来源提交为 clean `80e55eb`，评估器来源为 clean `b6289c5`，两类来源分别记录。

D2 已在提交 `6eacfc9` 上完成这 36 个 episode 的正式只读因果包。工具重新校验 450 个
episode、10 个分片和归档载荷，并对 76 个派生文件执行 SHA-256 复核。27 个一轨多真值
episode 含 38 个阻断映射事件，其中 36 个由最新量测引入新真值，2 个在历史谱系中已
含多个真值；最新来源为相机 17 个、雷达 21 个，完整模态转换拆分为
`radar->camera` 17、`radar->radar` 19、`camera+radar->radar` 2。9 个谱系超窗
episode 含 518 个事件，其中 517 个仅历史谱系过旧，1 个连当前承诺来源也超龄。该结果
关闭“缺少正式因果包”的 P1，不改变 36 项 strict unavailable。摘要见
[`../d2_data_association/docs/formal_r0_identity_causal_pack_summary_20260731/`](../d2_data_association/docs/formal_r0_identity_causal_pack_summary_20260731/)。

5/20/50/100/200 规模的累计平均实时倍率分别为 8.278、2.646、1.003、0.447 和
0.193。10 个分片原始大小合计 14,859,178,318 字节，确定性压缩后合计
1,419,786,552 字节，占比 9.55%；20,294 个文件均通过压缩包与源目录双端复核。
当前总进度为 450/900。shard 9 归档完成时可用空间约为 20.24 GiB，接近 20 GiB
运行保护线，不能安全启动 shard 10。继续执行前需取得移除已验证原始分片的明确授权，
或把归档迁移到独立存储。累计结果见
[`docs/SCALABLE_3D_FORMAL_R0_80E55EB_SHARDS0_9_20260731_CN.md`](docs/SCALABLE_3D_FORMAL_R0_80E55EB_SHARDS0_9_20260731_CN.md)。

main 已增加归档原生的范围合并入口。该入口要求 archive root 的归档子目录与 execution
plan 的完整分片集合精确一致；旁路 pack/verify 结果文件不计入集合，符号链接和额外目录
仍被拒绝。工具逐片验证压缩包，临时恢复一片并复用普通合并器的单元级校验，生成
合并片段和 D6 预评估行后立即清理临时目录。最终范围表、逻辑 episode 索引、归档摘要和
D6 报告绑定采用新 schema 原子发布。开发测试已覆盖两分片顺序恢复、规范单元表等价、
缺片、压缩损坏、容量保护、命令行和 D6 报告生成。该能力尚未在 20 个正式归档上运行，
也不构成删除当前原始分片的授权。

D6 已实现不依赖 main verified 状态的独立归档审计，逐片复算 checksum、manifest、payload、
计划绑定、tar 成员和低层 episode，再复核 archive-native merge 与报告 binding。归档/full
posterior 专项 `32 passed`，D6 全量 `1297 passed`。正式 10/20 预检接受 20 个旁路结果
文件，只因缺少 shard 10-19 失败关闭，实际 completed 分母为 0。正式 900-cell 尚未执行。

D6 的 `learning_scope_formal_audit` 也已接入相同的归档存储链路。G1/A1/A2/A3/C1/F1 与
显式 R0 可分别选择目录或归档输入；归档模式一次只恢复一个分片，并在释放临时目录前完成
学习采用、真值隔离、物理结果和同键 R0 非退化审计。真实 main producer 的紧凑 G1/R0
兼容夹具已覆盖 plan、shard、archive 和 `write_d6_report=True` merge，组合专项为
`89 passed`，D6 全量为 `1330 passed`。该结果只关闭归档审计接口 P1；正式学习作用域尚未
运行，不能登记模型准入、效果增益或控制许可。

## D3 A1 来源独立评价（2026-07-31）

main 已核验 clean commit `fc7a1c2` 生成的 D3-only 来源独立数据。数据覆盖 seed
`20000-20099`、100 个 episode 和 292 个匿名分配帧，包含 5、20、50、100、200 五档
规模和 10 个场景规模单元。生成进度为 `100/100`，在线真值使用和非有限状态均为 0；
schedule SHA-256 为
`468bddc8ccd5932114a1f779e093817a136a67f3c7df07fc458e1e1d5aca1009`。
该数据未与首次失败的 60-episode 诊断批次拼接。

D3 随后在 frozen bundle、归一化、教师、阈值和安全投影均不变的条件下，运行唯一一次
v2 来源独立评价。正类安全换绑为 `13/110=11.82%`，正类教师完全匹配为
`8/110=7.27%`，负类精确保持规则基线为 `182/182=100%`，均通过预注册总体门限。
94 个拒绝帧的矩阵和绑定全部恢复规则基线；重复资源、硬禁边、M-to-N 原子性、版本和
规则矩阵突变违规均为 0。结果状态为
`source_independent_evaluation_v2_gate_passed_not_admitted`。

D6 没有调用 D3 高层评价器。外部审计器重新读取 generation evidence、169 MB 匿名
数据集、292 条 JSONL、固定 21 列 CSV、合同和冻结 bundle，并独立复算数据 split、
每帧规则成本矩阵摘要及 3 组共 64,911 条选择边的安全性。CSV 与 JSONL 不一致数为 0；
R0、candidate、effective 各 21,637 条边的索引越界、资源容量超额、硬禁边和需求原子性
违规均为 0。D6 结论为
`offline_integrity_and_preregistered_machine_gate_confirmed_not_admitted`。

该结果关闭 D3 来源独立数据生成、v2 一次性评价和 D6 外部审计三个 P1。它不授予
runtime、assist、assignment、plan、control、physical、formal 或 production 权限。
test 子组教师完全匹配为 `0/25`，说明未见子组泛化仍弱；正式 seed `1000-1019` 的读取数
继续为 0。详细报告见
[`docs/SCALABLE_3D_D3_A1_SOURCE_INDEPENDENT_EVALUATION_20260731_CN.md`](docs/SCALABLE_3D_D3_A1_SOURCE_INDEPENDENT_EVALUATION_20260731_CN.md)。

## D4 建议当前代次发布修复（2026-07-31）

clean commit `49e43ea` 的 6-cell high-threat smoke 覆盖 5、100、200 三档和 seed
`7/17`。D6 确认来源、有限状态、在线真值隔离、D3-D4 计划标识/版本/时期/租约、
49 个当前联盟目标和 16101 条通信处置均通过，但 100 和 200 规模的 4 个重规划
episode 在 v2 计划发布后仍输出绑定 v1 的 D4 区域建议。四项均缺少最终 v2 建议，
因此 clean formal 只有 `2/6`，不能进入正式 900-cell。

D4 现提供持久的建议发布代次门。它把总线发布资格与后续规划采用资格分开：旧计划、
旧版本、旧时期、错误或到期租约和回滚不能发布；当前代次的故障围栏诊断可以作为
shadow 证据发布，但 `planning_consumable=false`，不能授予分配、联盟、接管或控制
权限。main 在每次分配后使用当前 D3/D4 快照生成 advice，并在写总线前核对该门。
规划前快照仍用于离线 D3/D4 干预学习帧，不再进入在线 advice。

开发回归为 D4 `913 passed, 1 warning`、scalable 3D
`416 passed, 1 warning`。clean `b063535` 的同范围复验已完成：12 条 advice 的
发布时旧代为 0，最终计划建议覆盖和低层 clean formal 均为 `6/6`。D6 独立报告见
`../d6_evaluation_metrics/reports/HIGH_THREAT_CLEAN_SMOKE_B063535_REVALIDATION_20260731_CN.md`。
该结果关闭 D4 建议代次的运行前阻断，不替代正式 900-cell。

正式分片现可使用确定性 `tar.zst` 逐片压缩、复核和恢复。完整历史分片 17 的非破坏性
探针将 1,086,483,308 字节压缩为 113,628,123 字节，1850 个文件恢复后树摘要一致，
压缩包和历史源均保留。`run-shard` 的 20 GiB 保护线没有降低。正式 900-cell 仍需按片
执行“完成、压缩、独立复核”，并在获得明确授权后才可移除已验证源分片；当前未执行该
删除步骤。

## 高威胁时期租约开发复验（2026-07-30）

main 已将 D3 权威计划的时期和租约绑定接入统一运行总线。每个新的
`plan_id + plan_version` 在进入 D4、D5 和 D7 前绑定一次
`authority_epoch/lease_expires_at_s`，同身份评价刷新复用原值且不得续租。D3 planner
同步更新内部发布签名，新身份会清除上一身份的通用绑定；二级接管、区域后继和权限 fence
继续使用各自当前代次的权限值。

开发工作树上的 `high_threat_m_to_n` 100-cell 批次覆盖 5、20、50、100、200 五档和
seed `1000-1019`。D6 只读审计确认有限状态、在线真值隔离、最终计划标识/版本、时期、
租约和当前联盟均为 `100/100`；151 次权威发布对应 151 个唯一身份和 151 次 ACK，
48 次同身份刷新没有重复发布或续租。v4 的 epoch/lease P1 已在开发证据层关闭。

批次仍为 `repository_dirty=true`，不能替代正式 R0。剩余 P1 是 clean smoke 与
900-cell 规范矩阵、51 个重规划 episode 的旧计划建议离线计量、12 项身份指标不可用
以及 50 对 50 以上非实时。main 报告见
`docs/SCALABLE_3D_HIGH_THREAT_P0_PRECHECK_V5_20260730_CN.md`，D6 独立报告见
`../d6_evaluation_metrics/reports/HIGH_THREAT_PRECHECK_V5_REVALIDATION_20260730_CN.md`。

## D3 来源独立数据故障围栏导出修复（2026-07-30）

D3 A1 来源独立数据生成首次运行完成 60/100 个 episode，进入
`center_failure` 后失败关闭。故障 episode 中，D4 规则建议明确携带
`projection_rejections` 和 `formal_d4_execution_fenced`，但批量学习导出器仍将该
建议标成可用教师目标，随后被 D4 数据合同拒绝。已完成的 60 个 episode 保留为失败
诊断，不与后续完整数据集拼接。

main-owned 导出器现将带投影或发布拒绝的 D4 建议记录为目标不可用，并保留拒绝原因
计数。D4 投影、安全围栏和权限合同没有放宽，故障建议也不会进入 D4 教师标签。中心
失效和二级失效专项回归均已通过。

批量生成器同时增加显式 `--learning-components` 合同。默认仍导出 D3、D4、D5 图
关联和 D5 主动视觉全部制品；D3 专项可冻结为 `--learning-components d3`，从而不写
无关模块制品。组件清单写入 generation plan、episode index 和批次摘要，恢复运行时
不允许改变。该模式已通过三 seed 冒烟。下一步从包含本修复的 clean commit 重新生成
完整 100-episode D3 来源独立数据。该后续批次已在 2026-07-31 完成，并通过 D3 v2
预注册总体机器门和 D6 独立审计；正式 holdout 与所有运行权限仍保持关闭，当前状态见
上方“D3 A1 来源独立评价”。

## D4 v7 来源独立评价结论（2026-07-30）

D4 v7 采用“确定性 R0 节点动作 + 学习转移残差”。owner、plan、version、epoch、
lease、配额、备用比例、侦察优先级、hold 和重规划字段全部继承同帧 R0。学习模型只
决定是否激活残差、选择一条有向边和转移资源数，组合结果仍经过确定性投影和干预
不变量。该结构消除了 v6 的节点动作与 transfer 脱节，但没有取得来源独立泛化。

冻结候选在开发 M16N24 VALIDATION 上曾取得 `2/9` 个精确正动作，负类精确保持 R0
为 `9/11`。main 随后从 commit
`4a83a373f4eb4e29704bb3cf9f62e3d54eee3aec` 生成第二组 64 个 M16N24、
8 区域 episode，使用 seed `5216-5279`，共 128 帧和 64 种新布局。数据集和 split
SHA-256 分别为 `f6c52bdd...c90ce67` 和 `4179c0a7...7521215`；与冻结 v4
TRAIN+VALIDATION 的 251 个唯一可观测键精确重合为 0。

来源独立 train/validation/test 的规则正类为 `24/9/9`。42 个正动作全部未命中；
validation/test 没有形成 transfer change。train 的 10 次原始激活中只有 3 次形成
可执行转移变化，三次均位于负类，表现为错误边和虚假转移。负类精确保持 R0 为
`83/86`。投影拒绝、不变量失败和原始 R0 完整动作元组偏差均为 0。

D6 没有调用 D4 高层评价器，而是从冻结模型、同快照 R0、残差解码、投影和不变量
重新计算全部逐帧记录。D4 与 D6 JSONL 逐字节一致，SHA-256 均为
`7785ded96360869edfb694c425321fa3323450cf1624607b53edf5d3eca6a5cd`；
五棵冻结输入树和 D4 评价树前后均未变化。

v7 已按 `failed_closed` 关闭。候选保持未注册、准入关闭和强制规则回退；置信校准、
正式 holdout、运行预检、D3、D7、降级、接管、联盟、控制和物理权限全部关闭。
后续不得继续围绕当前评价集调阈值。若继续学习路线，应另立候选版本和新数据来源，
先在全新 validation/test 上取得非零且充分的精确正动作，同时将虚假转移保持为 0。
详细结论见
`docs/SCALABLE_3D_D4_V7_SOURCE_INDEPENDENT_EVALUATION_20260730_CN.md`。

## D4 v7 独立评价准备（2026-07-30）

main 已为下一 actor 版本预留独立评价合同，但尚未运行任何新 seed。现有模型无关来源
生成器保留 v6 默认参数，并新增 campaign 标识和第二组区域布局。v7 注册表将训练、
正式 holdout、既有 `3000-3039` 与 `4000-4079`、设计 pilot `5200-5215` 和独立
评价 `5216-5279` 显式隔离。第二组 64 个 M16N24、8 区域供需布局与 v6 的 64 个布局
无重复。

该准备只冻结版本和场景边界。v7 actor 尚未完成，因此 `5216-5279` 没有生成、读取或
用于调参。D4 冻结新候选后，main 才会从 clean commit 运行该批次。

## D4 v6 独立来源合同（2026-07-30）

main 已增加 D4 v6 转移动作候选的独立来源生成器。新合同固定为 16 个目标、24 个资源、
8 个区域和四类三维场景，保留 8 个真实备用资源。64 个正式 development seed 为
`4016-4079`；训练 seed `0-99`、正式 holdout `1000-1019`、既有设计及评价 seed
`3000-3039` 和新设计 pilot `4000-4015` 均在注册表中显式隔离。生成器不加载模型，
不拟合候选，不产生分配、降级、联盟或控制权限。

区域布局由四组基础供需结构、八种轮换和镜像组合形成，64 个 seed 在重复前具有 64 个
不同的供需布局。dirty smoke 使用 seed `4016-4023`、8 个 episode 和 16 帧，有限状态
和规则标签均为 16/16，在线真值使用、模型拟合、既有评价读取和正式 holdout 读取均为
0。离线安全动作探针在 16/16 帧都找到一个通过现有确定性投影约束的单资源有向转移。
该 smoke 只验证来源合同和正动作供给能力。

clean commit `ed9e086ea8cf5c2138035f710cf4deb3e4a2801e` 随后生成完整
`4016-4079` 数据。64 个 episode 共 126 帧，有限状态和规则标签均为 126/126，
在线真值、模型拟合、既有评价读取和正式 holdout 读取均为 0。旧 v4
TRAIN+VALIDATION 有 251 个唯一可观测键，新数据有 94 个，精确重合为 0。main
导出器在 commit `9bdbe31` 增加默认关闭的 test 正类配额；冻结标签集的正类按
train/validation/test 为 `24/9/9`，负类为 `65/11/8`。

D4 在不修改 v6 actor 的条件下完成只读评价。126 帧的原始和投影后转移均为 0，
42 个规则安全正动作命中为 0；负类精确保持 R0 为 `77/84`，15 帧存在节点动作变化但
缺少配套 transfer。D6 从冻结 dataset 和逐帧记录独立重算，得到同样的 `0/42`、
`77/84` 和 15 帧不变量失败，重算 JSONL 与 D4 JSONL 的 SHA-256 均为
`771826bf...20c7c5`。v6 没有置信校准器，固定 0.60 门没有被应用。候选保持未注册、
准入关闭和规则回退，不进入运行预检、D3 后继或 D7 权限。详细结论见
`docs/SCALABLE_3D_D4_V6_SOURCE_INDEPENDENT_EVALUATION_20260730_CN.md`。

## D4 v4 外部运行与组合数据（2026-07-29）

main 已增加独立外部数据导出器。它从 D4 区域运行快照重算同键规则 R0，并只保留通过
确定性投影和 v4 干预约束的单资源跨区正样本；同键 R0 no-op 作为负样本。导出器不训练
模型、不写 D4 registry，也不产生分配、接管、联盟或控制权限。

首版数据从 clean commit `92cbded6a92ced37135784218eeb6a20b7d10b28` 导出，包含
100 个 episode、199 帧。train 正/负为 1/139，validation 为 1/29。该数据证明了
外部数据谱系、正负样本生成和 test 隔离链路，但样本过于稀疏，D4 通用行为克隆最终仍
输出全 no-op，因此没有形成候选。

第二版在 clean commit `71f5910a55b594a708f13d260d15a710535748bc` 上组合两个来源：
20 对 20、8 区域真实 runtime 数据和 100-seed、4 区域安全动作课程。组合数据包含
200 个 episode、499 帧；train 有 60 个正样本和 290 个负样本，validation 有
15 个正样本和 60 个负样本。unsafe difference、test payload 读取和在线真值使用均为
0。数据集、分割、来源制品和外部证据 SHA-256 分别为
`fa5e45ad...e00c6`、`c212fe9b...4619`、`8a9465d9...5b47` 和
`343040ca...0360`。制品位于
`outputs/d4_v4_external_composite_20v20_8region_curriculum_seed9_20260729/`。

组合数据仍高度稀疏：train 非零/零边目标为 71/3849，validation 为 16/824。D4 在
提交 `7646c95295f720a72fddd937a36384373a04c9c6` 中加入仅由 train 计算的有界类别
平衡后，Actor 的 train 正/负命中为 59/60、278/290，validation 为 14/15、58/60。
置信头在 validation 中仍有 1 条负类且动作不一致样本越过固定 0.60 门，builder 正确
失败关闭，未生成候选。后续须在不读取 test、不降低门限、不改变确定性投影和权限的
条件下完成置信校准，再进入不可变 review、D6 独立审计和 D3 后继计划验证。

D4 随后在提交 `5f2fe0d` 增加只看模型输入张量的可辨识性审计。第二版数据的 train
存在 10 个相同输入、相反置信标签的键，覆盖 22 条记录；继续调整类别权重无法解决该
冲突。main 在提交 `8a96db3` 将导出语义改为按
`node_features/edge_features/edge_index` 的值、形状和类型整组标注。同一模型输入
跨来源、train、validation 和 test 只能得到同一正负类别，seed、episode、来源和
target 不参与分组。

第三版 observable-group 数据仍包含 200 个 episode、499 帧。272 个模型输入键中，
46 个键对全部同键记录都存在一致、安全的正动作，最终选择 39 个键；train、
validation、test 正样本分别为 60、15、13，前两组负样本仍为 290、60。混合正负键、
R0 target 冲突、正动作 target 冲突、unsafe difference、在线真值使用和 test 拟合
均为 0。数据集、split、来源制品、外部证据和分组审计 SHA-256 分别为
`b31fc43f...7fb8c`、`c212fe9b...4619`、`f39d9ba9...630f`、
`f059ff5d...3ca5` 和 `3c160087...ef62`。制品位于
`outputs/d4_v4_external_composite_observable_20v20_8region_curriculum_seed9_20260729/`。

第一次 clean builder 已越过可辨识性审计，但固定 0.60 门仍未通过：train 的
positive/negative/inconsistent/executable 越门数为 58/12/12/70，validation 为
13/2/2/15。临时目录已删除，候选和 registry 均未形成。该结果把剩余问题缩小到 v4
置信校准；不能通过降低门限或读取 validation/test 拟合来绕过。

D4 后续形成了内容寻址的未注册 v4 development/shadow 候选。D4 不可变审查确认
180 个文件、179 个 manifest 制品、来源提交和数据用途一致，v3 registry 未改变，
全部运行和生产权限保持 false。D6 随后进行独立只读复核，开发完整性审计通过，但模型
质量未通过准入判断：固定 0.60 门下，train/validation 正类召回分别只有
0.206897/0.307692，负类特异度均为 1.0，最小正类越门裕量只有 0.000504935。

main 据此拒绝将 v4 登记或送入正式 holdout。该候选只保留为开发对照，状态继续为
`development_only`、`shadow_only`、`admission_closed` 和
`rule_fallback_required`。下一轮必须使用新的版本和制品身份，在不读取正式 holdout、
不降低 0.60 门、不放宽确定性安全外壳的条件下提高正类召回和门限裕量；通过新的模块
门与 D6 独立审计后，才允许 D3 开展后继计划和同键双臂实验。
main 的正式决定和后续开发门见
`docs/SCALABLE_3D_D4_V4_MAIN_ADMISSION_DECISION_20260729_CN.md`。

D4 随后建立了独立版本的 v5 近邻置信校准对照。它冻结 v4 actor，从实际 24 维池化
特征中保存 TRAIN 近邻库存；固定门、确定性投影、备用资源、版本、联盟和权限合同均未
改变。原同源开发统计为 train/validation 正类召回和负类特异度均 1.0，最小正裕量
0.400000/0.209319。

D6 独立审计确认上述数值可复现，也确认其主要来自记忆和近重复输入。TRAIN 的
350/350 个查询都把自身纳入近邻；按 raw observable key 和 latent exact key 留组后，
正类召回为 0.965517，负类特异度降为 0.958904，Brier 为 0.037610440。
VALIDATION 有 42/75 条与 TRAIN 完全重合，去除重合后只剩 1 个正类；最近距离不小于
0.1 的 3 条记录又全部是负类。因此当前没有足够分母评价独立正类召回和正裕量。

v5 只保留为 `development memorization baseline`。候选未注册、准入关闭、规则回退
保持必需，D3 和 D7 权限均为 false。main 已增加来源独立开发集生成器。每个 D4
真实快照在离线边界重算同键确定性规则 R0，在线 D4 建议单独保留为审计字段，不充当
教师标签。seed `3000-3007` 固定为数据设计 pilot，正式独立评价只使用未查看的
`3008-3039`。两类 seed 均禁止模型拟合，并与训练 seed `0-99`、正式 holdout seed
`1000-1019` 完全隔离。

2026-07-29 的 dirty smoke 覆盖 seed `3000-3007`。8 个 episode 共形成 16 帧，
有限状态为 8/8，在线真值使用为 0，安全规则标签为 16/16，阻断区域记录为 0。
专项测试为 `6 passed`，本模块全量测试为 `389 passed`。该结果只验证生成和数据合同，
不构成独立泛化证据。随后从 clean commit
`b66a845f51f8496876f00d013360d1334b0bcce6` 生成首轮 20 对 20 数据。40 个
episode、79 帧全部干净且标签可用，但只有 seed 3037 的 2 个安全正动作键，固定
split 的 validation 正类不可用。等量场景把全部资源用于当前分配，不能为置信评价
提供足够可执行差异。

正式独立配置因此冻结为 16 个目标、20 个资源、8 个区域和四类场景。4 个真实备用资源
用于形成安全正负动作，区域不均衡只控制三维初始布局；D3 继续全局可达，避免把
planning-only 建议误写成执行标签。clean commit
`63987592c216fbdb7e03d77183afc6e9f15748a2` 已生成 seed `3008-3039` 的 32 个
episode、63 帧。train/validation/test 为 `43/10/10` 帧；旧 v4
TRAIN+VALIDATION 的 425 帧形成 251 个唯一 observable key，新数据形成 41 个唯一键，
exact 重合为 0。

D4 只读评价和 D6 独立重算得到相同结果：规则安全正动作按 split 为 `1/1/0`，冻结
actor-derived 正类为 `0/0/0`；63 个 v5 得分均为 0，固定 0.60 门通过数、负类误接收和
候选授权均为 0，规则回退为 `63/63`。当前只建立来源独立负类拒绝证据。正类分母为 0，
正类召回保持 unavailable，不能声称候选具有来源独立正类泛化能力。

D4 与 D6 均记录 external test 的 10 帧已读；main 此前也已只读检查同一非正式 test。
这些读取不属于正式 holdout。seed `1000-1019` 的正式 holdout 读取仍为 0。D6 另在
评价前后复核 source、labeled export/dataset、v4 和 v5 五棵输入树，突变数为 0。候选
继续保持 unregistered、admission closed、rule fallback required，全部生产、D3 和 D7
权限关闭。不得依据本轮 external test 调候选、降低门限或修改 split；正式 holdout、
runtime preflight、D3 successor 和 D7 权限测试均不启动。跨模块结论见
`docs/SCALABLE_3D_D4_V5_SOURCE_INDEPENDENT_EVALUATION_20260729_CN.md`。

## D4 区域资源可执行差异探针（2026-07-29）

main 已增加默认关闭的 `scalable3d-regional-resource-probe-v1` 场景合同。该合同允许
按区域冻结目标和资源初始数量，并可将 D3 默认候选边限制在资源所在区域。普通场景不读取
该配置，原有全区域可达性保持不变。探针启用时，D4 快照同时包含已分配和未分配的
D2/D3 航迹，用于观察资源不足形成的真实 backlog；普通场景仍保持既有快照范围。在线
链路不读取目标真值编号。

当前诊断采用 20 个目标、20 个资源和 8 个区域。目标区域数量为
`2/4/2/3/2/3/2/2`，资源区域数量为 `4/1/2/3/2/3/2/3`。D3 在本区可达约束下形成
17 条绑定和 3 个未分配目标。`region-001` 有 4 个目标需求、1 个可用且已承诺资源；
`region-000` 有 4 个可用资源、2 个已承诺资源和 1 个受保护备用资源，理论上只允许转移
1 个资源。

D4 已能看到该资源缺口，但现有合同把“当前分配不可执行”和“下一周期重新规划资格”使用
同一权限门。目标区域因此返回 `authority_not_active`、`fault_fence_active` 和
`formal_d4_execution_fenced`，跨区建议被正确拒绝。该探针目前只复现并定位权限耦合，
没有证明 A2 候选形成 D3 严格后继。下一步由 D4 显式分离 planning/replan eligibility
与 assignment/control authority；执行权限、联盟权限和 D7 控制权限继续关闭。

## D4 readiness v3 隔离双臂（2026-07-29）

main 已运行 20v20、8 区域、seeds 2003-2012 的 10 组独立规则臂/候选臂
development episode。两臂使用相同初态和外生配置，但分别建立世界、总线、日志和
episode 身份。10/10 seed 完成 v3 原始推理、运行门、投影和隔离采用；D3 严格后继、
开发 ACK 和摘要级物理窗口只在 seed 2007 出现，其余 9 个 seed 因
`regional_hint_no_executable_successor` 保持规则路径。

D6 对紧凑制品重算完整性、有限值、在线真值使用和生产权限。拦截数与最小距离的有界
非退化在 10/10 seed 上可评价且通过，但双臂均无拦截，最小距离逐 seed 完全相同。
因此正收益仍为 unavailable/false，不能据此开放候选权限。

seed 2007 另保存了完整 control/treatment episode。D6 独立联接得到两臂各 4 条 ACK、
77 条 binding 和 1 次同身份 refresh，treatment 另有 1 次 D4 regional applied。
后继计划的首次发布与 refresh 保持相同严格执行签名、authority epoch 和 lease。
候选与规则臂的资源—目标、角色及联盟可执行字段相同，实际干预不可辨识。19 条 D7
非 hold 指令原生形成 18 条物理状态窗口。D2 审计确认唯一缺口是
`GT3D-000004` 在 1.035193 秒的一次 confirmed/unmatched 雷达漏检；0.833472 秒和
1.236149 秒的前后锚点均唯一映射到 `TGT-0004`。

D6 在完整链审计中增加显式 evaluator-only bounded coast bridge。该桥只接受 D2 v2、
同航迹、同真值、confirmed/unmatched、持续 committed、无竞争声明、锚点谱系完整且
间隔不超过 0.9 秒的窗口。通用 runtime replay 默认不启用，冻结的原生 18/19 事实保持
不变；完整离线审计按“原生 18 + 桥接 1”得到有效 19/19。该结果不回写在线总线，不
恢复 D2 在线身份，也不改写 `global_track_id`。

当前 v3 继续保持 development/shadow-only、admission closed 和 rule fallback
required。开发 ACK 不产生生产 authority，所有分配、降级、接管、联盟、控制和模型
晋级权限均为 false。D6 报告位于
`../d6_evaluation_metrics/outputs/d4_v3_isolated_final_v2b_paired_audit_20260729/`
和
`../d6_evaluation_metrics/outputs/d4_v3_isolated_final_v2b_full_chain_audit_20260729/`。

## D4 readiness v3 预检（2026-07-29）

本节保留单 seed 预检历史，当前状态以本文件顶部“隔离双臂”结论为准。

D4 readiness v3 已完成可复现 clean build、不可变登记和 main 单随机种子运行兼容性
预检。候选只适用于 8 区域，运行投影合同为最小备用比例 0.1、最小备用资源 1、建议
有效期 1.5 秒；固定 OOD、置信度、不一致封顶和连续动作容差为
0.05/0.60/0.59/0.10。候选 manifest 内容、模型和运行门 SHA-256 分别为
`7978aec0...ada2`、`ace5df6d...7f52d` 和 `77972834...6872`。

main 从 clean commit `83b8869b49c4ac26b6a5b6fb336dfe9af6960226` 加载固定
registry，得到以下结果：

| 场景 | seed | 帧数 | 分布内 | 原始推理 / 门应用 / 动作一致 / 许可 | 规则回退 | 结论 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 5v5 / 2 区域 / 2 侦察节点 | 2000 | 3 | 0/3 | 0 / 0 / 0 / 0 | 3 | 8 区域适用域负例，失败关闭 |
| 20v20 / 8 区域 / 2 侦察节点 | 2001 | 3 | 3/3 | 3 / 3 / 3 / 3 | 0 | 单 seed 运行兼容 |
| 200v200 / 8 区域 / 8 侦察节点 | 2002 | 3 | 3/3 | 3 / 3 / 3 / 3 | 0 | 单 seed 运行兼容 |

三组在线真值使用、非有限状态和正式 D4 决策改动均为 0。两个 8 区域正例的上下文、
正式决策摘要和候选许可分歧计数均为 0，blocker 为空。5v5 负例包含
`candidate_region_count_out_of_scope`，同时由边 `distance_log` 和
`transfer_time_log` 触发分布外。3 帧均在运行置信门前走规则路径，因此总回退为 3；
运行置信门自身的回退计数为 0。该结果不作为 v3 的 8 区域 blocker。

这批预检证据当时只关闭 20v20/200v200 单 seed 运行兼容性。后续已完成 10-seed 同键
规则基线、单 seed 完整链和离线物理窗口覆盖；可辨识区域干预、正收益、扰动场景和
正式准入仍为 P1。
`paired_development_rollout_allowed=true` 不授予实际采用或控制权限；registry 内
`runtime_preflight_completed=false` 和全部 false 权限保持不变。详细报告见
`docs/SCALABLE_3D_D4_READINESS_V3_PREFLIGHT_20260729_CN.md`。

## 学习诊断与准备度（2026-07-28）

本轮补齐 D3 批次加载、D4 当前谱系候选构建、D5 训练语料治理和 D6 G1 模型来源复核。
规则路径、版本化计划、`global_track_id` 所有权和确定性安全外壳没有变化，所有学习、
分配、降级、相机和控制权限继续为 false。

D3 的 A1 动作裕量校准在一个冻结规划帧内比较规则代价间隔、有界残差修正和 Hungarian
最终 binding。正式 20-seed 证据仍是 20/20 代价矩阵变化、0/20 binding 变化。三资源、
两目标开发夹具在候选 `alpha=0.25` 时出现 3 条 binding 差异，只说明冻结残差能够在该
夹具越过离散求解边界。A1 隔离批次现可由公共 strict loader 重算固定文件布局、摘要、
seed/帧范围、候选选择守恒和版本连续性。加载结果不等同于计划发布或运行采用。

D4 的历史实际区域策略诊断使用 20 个独立校准 seed、420 个样本。两次复跑均得到 76 个
安全非零输出和 344 个资源不可行主分类；该历史候选与当前实现谱系不一致。当前谱系候选
构建器将训练和模型选择限定在 train/validation，并拒绝 dirty source、split 重叠、摘要
篡改和权限升级。随后已从 clean commit `b0d498d9...` 构建并 review-only 复核实际
development/shadow 实物。manifest 文件和权重分别为 `7cc10ad7...de64`、
`fd1b9c4c...0047`；train/validation 固定门限诊断分别为 168/180、54/60 个安全非零
动作。test、历史 calibration 和保留 seed 读取数为 0，全部运行权限为 false。

D5 行为克隆在类别权重和逐动作指标之外增加了训练语料结构门。语料按动作、相机角色、
场景、seed 和 episode 计数；缺 `hold`、少数动作或侦察相机时拒绝训练。旧 v1 缓存可读
但不可继续训练。补采请求要求新的独立 episode 和训练 seed，不允许复制或过采样替代。

D6 readiness v2 继续拒绝 manifest 自报 facts 和通用自签 gate 文件。冻结种子适配器之外，
现已增加 G1 `model_source` 适配器。它固定复核 D5 v5 的 13 项原始制品并重跑既有
external/post-assembly 审计。对现存正式证据树的只读验证通过，只证明
`component_ids=[d5_graph]` 的来源可信。G1 其余八门、其他模型来源和全部权限仍不可用。

共享工作区验证为：D3 `593 passed, 1 skipped`、D4 `697 passed, 1 warning`、D5
`755 passed, 2 warnings`、D6 `1138 passed, 1 warning`、本模块
`352 passed, 1 warning`、跨模块合同 `8 passed, 1 warning`。2026-07-28 实测文件系统
可用空间约 32 GiB，高于 20 GiB 正式运行保护线。正式未见 seed、模型权限、运行确认和
成对非退化仍未闭合，因此没有启动 900-cell 或完整多 seed 写盘。
本轮集成记录见 `docs/SCALABLE_3D_LEARNING_EVIDENCE_CHAIN_P1_20260728_CN.md`。

## A3 零检测帧与观测节拍（2026-07-27）

main 已将 D5 零检测帧 v2 接入可扩展三维 episode。每台工作相机在每次扫描后生成
truth-free 成像事件。带检测框的帧继续使用原视觉批次；零检测帧通过独立通信主题和随机
流送入模块栈。事件保留相机、资源、双时间戳、扫描序号及计划、联盟和通信版本，不携带
目标真实标识。

A3 和独立 R0 按量测时刻选择最近的合法命令窗口，并严格核对资源和版本。已分配目标的
零检测帧输出 `reacquire` 和 `assigned_reference_visible=false`，不创建局部轨迹或身份。
主动视觉改为观测触发，并在 episode 末段保留 0.25 秒证据尾窗。旧版本、错误资源、丢包
和无后续观测均失败关闭。

同旧场景 seed 1000-1019 的开发复跑中，默认 1% 通信丢包和 0.01 秒抖动得到 492 条候选、
488 条可配对、4 条不可配对，覆盖率为 99.19%。329 条零检测帧进入有效窗口并记为
`reacquire`，159 条原视觉帧记为 `locked`，空帧合同拒绝为 0。将通信丢包和抖动设为零后，
500 条候选全部可配对。旧冻结 536/152/384 制品及哈希保持不变。

新结果来自未提交工作树和开发 seed，不替代正式证据，不证明模型收益或现实视觉性能。
所有运行权限保持为 false。结果见
`docs/SCALABLE_3D_A3_OBSERVATION_CADENCE_DEVELOPMENT_20260727_CN.md`，机器摘要见
`docs/SCALABLE_3D_A3_OBSERVATION_CADENCE_DEVELOPMENT_20260727.json`，其 SHA-256 为
`2b3fd9f2be093c3613328e330d444189b6d8ee42b43b40793f3af477a324adb5`。当前可扩展三维
全量回归为 `352 passed, 1 warning`。

## A2/A3 独立 R0 配对开发验证（2026-07-27）

main 已实现候选组与规则组的独立 episode 编排。两组使用同一外部配置摘要，但分别创建
世界、消息总线、模块栈、episode 标识和事件日志。A2 使用 D4 安全采用及物理执行窗口，
A3 使用 D5 命令、确认、相机反馈和匿名观测窗口；D6 重新计算实际采用、同键 R0 和收益
审计输入，不授予任何运行权限。

seed 1000-1019 的 A2 开发回归共审计 20 组。受控策略没有产生资源变化、保持状态或
跨区转移，20 组均记为可识别区域干预缺失，实际采纳和可审计同键收益配对均为 0。
并行发生的 D3 常规重规划不再归因给 A2。A3 开发回归冻结了全部 536 条候选的配对处置：
152 条可配对，384 条为候选物理窗口缺失，记录级覆盖率为 28.36%。存在不可配对记录时，
D6 保留原因分布，但完整 A3 采用、物理窗口、同键规则基线和收益计数保持 unavailable。

修复正式裁决上下文传递后，main 另用 D4
`ConstrainedDevelopmentRegionResourceAdapter` 完成一次 5 对 5、seed 1 的全 episode
探针。适配器只生成一个受约束 `request_replan`，形成 D3 严格后继计划、owner ACK、
安全采用和物理窗口，在线真值使用为 0。适配器仍是 development-only，标准 advisor
限制为 shadow，正式 A2 收益装配器按
`development_intervention_benefit_forbidden` 拒绝其进入收益审计。该探针只证明真实
D4 适配器与 main 运行桥可达，不替换上述 20-seed 无操作批次。

main 现已为每条 A3 候选记录命令、运行确认、相机反馈、匿名观测清单和物理窗口状态，
并持久化 `active_vision_a3_candidate_stages.json`。同配置 seed 1000-1019 的不落盘开发
复跑保持 536/152/384 分母不变，536 条均有阶段证据。384 条不可配对记录中，344 条同时
标记为匿名观测缺失和物理窗口确认缺失，剩余 40 条因 episode 结束时观测清单未闭合而
保持细因未解析；物理窗口细因完整率为 344/384。
本批没有运行确认缺失、命令过期、时序错配或相机反馈缺失。细分原因是多标签统计，不能
直接相加为候选数。该复跑来自未提交工作树，只用于定位命令频率与观测频率不匹配，不替代
原冻结批次，也不形成模型非退化或授权证据。

批量制品现在分别报告 `minimum_seed_count_met` 和
`minimum_unseen_seed_target_met`。本批数量达到 20，但
`seeds_verified_unseen=false`，因此未见 seed 门限仍未满足。实验使用受控测试策略夹具，
不是实际模型性能证据；开发配对 API 已禁止调用方通过布尔参数自声明未见性，正式结论必须
绑定冻结 seed 注册表、模型训练谱系和执行计划。D6 非退化、模型晋级及分配、降级、相机和
控制权限全部为 false。
结果和边界见
`docs/SCALABLE_3D_A2_A3_INDEPENDENT_R0_PAIRING_DEVELOPMENT_20260727_CN.md`。
阶段细分开发摘要见
`docs/SCALABLE_3D_A3_STAGE_BREAKDOWN_DEVELOPMENT_20260727.json`，文件 SHA-256 为
`1ba6040e7c3e7e3b9e7d5506dfd20cf3539ce12c5aac13cca7f02799f0cd99ef`；摘要明确
`formal_evidence=false`。
本轮 D6 严格采用审计专项为 `51 passed`，配对编排专项为 `6 passed`，D4 全量为
`674 passed, 1 warning`，可扩展三维模块全量为 `346 passed, 1 warning`，跨模块合同为
`8 passed, 1 warning`。2026-07-27 收尾回归进一步确认 D3
`551 passed, 1 skipped`、D5 `726 passed, 2 warnings`、D6
`1101 passed, 1 warning`；main 模块栈专项为 `76 passed`。既有 Matplotlib `Axes3D`
和显卡管理接口警告不影响二维报告或合同结论。

## A2/A3 运行证据桥（2026-07-26）

main 已把 D3、D4、D5、D7 的运行时证据接到同一 episode 状态机。D3 对已应用区域提示
写入统一的 owner、authority epoch 和 lease；多区域 owner、epoch 或 lease 不一致时整份
提示失败关闭。D4 的不可变 owner ACK 收据允许在同一绑定下由后续物理窗口重复引用，
同时保留消息标识、目的节点、计划版本、epoch、lease、分区代次、载荷摘要和评估时间
单调门。

5 对 5、seed 1、3.0 秒的 A2 动态正向用例现使用 D4 真实受约束开发适配器，并由
test-only admitted transport 夹具传递合同。该用例形成计划版本 2、1 次 owner ACK、
3 个同计划非 hold 绑定、1 个状态变化物理窗口和 1 条
`safe_adoption_available=true` 证据；在线真值使用为 0。适配器没有正式模型 manifest，
标准 advisor 只允许 shadow，正式收益装配器拒绝 development intervention。该结果不能
声明策略收益、assist 准入或控制权限。

A3 主动视觉桥按相机维护命令窗口队列，并按观测量测时刻匹配已经执行且仍有效的最近命令。
受控正向探针得到 40 条运行确认、21 帧匿名观测和 21 个物理观测窗口，实际采用状态可验证；
全部候选仍因 `same_key_r0_window_missing` 不具备收益证据。该结果只关闭异步命令/观测
错配，不代表正式主动视觉模型、多 seed 非退化或现实相机效果。

严格 D4 证据重发使用独立、确定性的通信随机流。新增 owner ACK、联盟 ACK 和带计划哈希/
总线序号的严格计划广播仍执行原有丢包和抖动模型，但不再改变共享传感器报文的随机序列。
规模 20、seed 1009 的延迟噪声 R0 结束缓冲已恢复为 20 条重放证据、0 条新鲜量测。

本轮验证为：D3 `546 passed, 1 skipped`，D4 `637 passed`，D5 `682 passed`，D6
`1071 passed`，scalable `338 passed`，跨模块合同 `8 passed`。跳过项是可选
OR-Tools；警告来自本机 Matplotlib 三维投影和显卡管理接口。当前工作树未冻结为 clean
正式来源，A2/A3 同键 R0、多 seed、实际模型授权和相对收益仍为 P1。

## 正式输出归档

当前规模化输出约 18 GiB。2026-07-27 实测文件系统可用空间约 15 GiB，已经低于正式
分片运行器的 20 GiB 保护下限。`artifact_archive.py` 提供非破坏性的正式输出迁移准备：

```bash
python3 -m research_modules.scalable_3d_simulation.artifact_archive \
  inventory /path/to/source /path/to/inventory.json

python3 -m research_modules.scalable_3d_simulation.artifact_archive \
  copy /path/to/source /external/path/to/archive

python3 -m research_modules.scalable_3d_simulation.artifact_archive \
  verify /external/path/to/archive --source /path/to/source \
  --result-json /path/to/verification.json
```

清单按相对路径保存每个普通文件的大小和 SHA-256，并计算完整树摘要。复制先写临时目录，
复核 payload 和复制期间未变化的源目录后原子发布。归档根目录只允许 `payload/`、
`archive_manifest.json` 和 `SHA256SUMS`。符号链接、特殊文件、内容变化、额外文件和摘要
不一致均失败关闭。

该工具没有删除入口。`source_deletion_eligible=true` 只表示指定源与归档再次逐文件相等，
不等于已经删除，也不构成自动清理授权。当前没有可用的第二个大容量挂载点，既有正式
输出保持原位，20 GiB 保护下限不降低。专项验证为 `12 passed`。

面向 20 个正式 R0 分片，`formal_shard_archive.py` 增加确定性 PAX tar 与单线程
Zstandard 压缩。归档冻结执行计划、父计划、源提交、分片编号、分片描述、单元清单以及
`shard_plan.json`、`progress.jsonl`、`checkpoint.json` 的摘要。创建前后均调用与
`merge-r0` 同口径的完整分片校验，压缩流逐文件复核。执行计划错配、源变化、压缩包损坏、
危险路径、非普通文件和恢复后语义不一致均失败关闭。

```bash
python3 -m research_modules.scalable_3d_simulation.formal_shard_archive \
  pack-shard \
  --execution-plan /path/to/formal_r0/experiment_matrix_execution_plan.json \
  --shard-index 0 \
  --destination /path/to/formal_r0_archives/shard_000_of_020 \
  --minimum-free-gib 20

python3 -m research_modules.scalable_3d_simulation.formal_shard_archive \
  verify-shard \
  --execution-plan /path/to/formal_r0/experiment_matrix_execution_plan.json \
  --shard-index 0 \
  --archive /path/to/formal_r0_archives/shard_000_of_020 \
  --source /path/to/formal_r0/shards/shard_000_of_020

python3 -m research_modules.scalable_3d_simulation.formal_shard_archive \
  restore-shard \
  --execution-plan /path/to/formal_r0/experiment_matrix_execution_plan.json \
  --shard-index 0 \
  --archive /path/to/formal_r0_archives/shard_000_of_020

python3 -m research_modules.scalable_3d_simulation.formal_shard_archive \
  merge-archives \
  --repository-root /path/to/clean/producer/worktree \
  --execution-plan /path/to/formal_r0/experiment_matrix_execution_plan.json \
  --archive-root /path/to/formal_r0_archives \
  --output /path/to/formal_r0/merged_scope_from_archives \
  --write-d6-report \
  --minimum-free-gib 20
```

工具仍没有删除入口。`pack-shard` 默认按未压缩最坏情况预留 20 GiB，不能在压缩过程中
越过正式运行保护线。`restore-shard` 只恢复证据，不执行新单元。`merge-archives` 要求
完整且无额外归档目录的集合，每次只临时恢复一个分片；普通目录合并仍由
`merge-r0 --write-d6-report` 执行。归档合并的 D6 输出单独记录评估器 schema、提交、
dirty 状态、源码树摘要和全部报告文件 SHA-256。当前开发回归不能替代正式 20 分片
归档集合和 D6 独立后验审计。完整分片 17
实测压缩比例为 10.46%，恢复树摘要为
`59cd7ba239b2e0a3c7c518be85544b5a0946c284e5fc4adf364da79c5067b42b`。
验证记录见
[`docs/SCALABLE_3D_FORMAL_SHARD_ARCHIVE_VALIDATION_20260731_CN.md`](docs/SCALABLE_3D_FORMAL_SHARD_ARCHIVE_VALIDATION_20260731_CN.md)。

## D3 共同检查点物理续跑

`run_checkpoint_paired_physical.py` 使用 20 个保留 seed 的共同 D1-D4 干预帧，复制规则组
和 D3 学习处理组的独立世界，让两组计划分别经过 D7 和三维质点运动，再由 D6 离线比较。
输出仍属于隔离仿真，不是 production runtime ACK、反事实或因果证据。

2026-07-26 的名义 5 对 5 开发诊断使用 2.2 秒源 episode 和 0.5 秒物理续跑。20/20 seed
具有计划消费、导引血缘、物理窗口、成对物理效果和非退化字段；在线真值使用与
`global_track_id` 改写为 0。规则组和处理组各施加 980 条控制命令，但最终绑定变化为
0/20，平均最近距离均为 3814.253961 米，五米成功均为 0。当前候选没有形成可辨识干预，
不能进入 A1 装配或正式作用域。

首次使用相对输出路径时发现 D6 绝对路径与相对临时目录混用。writer 现在先解析绝对输出
目录；相对路径专项回归为 `3 passed, 1 warning`。开发结果和证据边界见
`docs/SCALABLE_3D_D3_CHECKPOINT_PHYSICAL_DEVELOPMENT_20260726_CN.md`。

## 学习变体准入与分片状态

2026-07-26 的实际 bundle 预检确认，G1、A1、A2、A3、C1 和 F1 当前均不能进入正式
assist。D3 模型仅允许 shadow；D4 模型仍处于运行时 shadow gate；D5 图模型和主动视觉模型
没有正式 assist 权限。正式学习 episode 仍为 0。

D3 已关闭 legacy v2 和 v3 自我晋级路径。production writer 在写文件前拒绝调用方
构造的 qualified admission；手工正向 v3 manifest 稳定返回
`bundle_assist_evidence_assembler_unavailable`。D4 复核没有发现新的 P0，自声明
qualified/assist 和无 manifest 注入仍失败关闭。D3、D4 现有 bundle 均保持
development/shadow-only。

D5 G1 evidence assembler 当前发布 `d5.tracklet-model-bundle.v5`，准入报告为
`d5.tracklet-g1-admission-report.v2`，并嵌入
`d5.tracklet-g1-authority-contract.v2`。权限合同绑定 D6 审计文件/内容哈希、证据状态、
原因和六项运行权限。模型晋级、G1 辅助、默认路径、分配、故障接管和控制权限必须精确
存在且全部为 false。证据通过只表示 eligible，不会打开在线路径。

D6 external audit 输出已升为 `d6.d5-g1-external-audit.v2`；结构未变化的 input spec
和 consumer contract 分别保留 v1。Post-assembly 的 input、output、consumer 和 profile
全部使用 v2，只接受 bundle v5、准入报告 v2、权限合同 v2 和 external audit v2。它还
交叉校验 paired lineage 文件、900 条记录、900 个唯一 episode UID 以及当前运行实现
摘要。旧 bundle v4、audit v1、report v1、混合版本和权限字段漂移均失败关闭。

历史 `99fa4428...d4cd` 模型的 post-assembler 审计为 `fail_closed`。五项 blocker 是
`implementation_evidence_unavailable`、`implementation_lineage_mismatch`、困难扰动
cluster/edge F1 未达到 `0.9`，以及单特征最佳方向曲线下面积 `0.997340` 超过 `0.98`
上限。该旧证据不能输入 v5 装配。

当前运行时证据已在 detached clean commit
`8d5e02ec989259ce3d39e1e4ad6a90dd0d8d5b54` 上重新生成。运行实现摘要为
`b0708e718b374e5bb52db41c7bd2f994e340a2b009cfd348881a5f9d549baffe`，
权重 SHA-256 为 `7fb5db8b...ca71`。held-out 覆盖 20 个未见 seed、900 个 episode
和 45 个场景规模单元；精确率、召回率、F1 和候选召回率均为 `1.0`，错误合并率为
`0`，CPU P95 推理时延约 `0.913 ms`。paired-shadow 的模型边和聚类 F1 均为
`1.0`，最高单特征 AUC 为 `0.720073`。逐帧 lineage 为 900 条记录和 900 个唯一
`episode_uid`。

D6 external audit v2 得到 `pass`、blocker 为空，文件/内容 SHA-256 为
`cbd6c72b...0cd6` / `334cf662...2d15`。D5 生产装配器生成 v5 manifest
`b431d066...317d` 后，D6 post-assembly v2 再次得到 `pass`、blocker 为空，内容
SHA-256 为 `17dda42d...3e1d`。v5 strict 和 shadow loader 均可加载；在线 assist
请求返回 `bundle_g1_assist_authority_not_granted`。这条链关闭了当前 runtime 的证据
装配缺口，但没有开放任何运行权限。

四个 owner 没有修改旧 bundle、manifest 或权重，也没有增加 implementation hash
兼容白名单或放宽阈值。本次合同修订后的 D5 全量为 `655 passed, 1 warning`，D6 全量为
`1042 passed`。D6 已用 D5 生产装配器生成的真实 v5 完成正向审计，结果为 pass、blocker
为空；lineage 篡改和缺失两个真实产物负例均失败关闭。main 另有 D5/D6 跨模块版本、
布局、lineage 和权限合同直接对照回归。D3、D4 算法没有变化。当前 R0 路径不加载模型，
本次治理修复不改变已冻结的 R0 source、execution plan 或已经完成的规则实验。

main 已将可恢复分片执行器扩展到 G1、A1、A2、A3、C1 和 F1。执行计划保存各变体所需
bundle 的完整文件树摘要、manifest 摘要、预检设备、准入诊断摘要和解析后的模型版本。
`run-shard` 必须提供同一文件树和同一设备，并在每个学习单元开始前和发布前重复校验；
缺 bundle、额外 bundle、文件篡改、设备变化、规则回退、诊断变化或模型版本变化都会在
新建 shard 或发布单元前失败关闭。旧版不含
`learning_bundles` 的 R0 执行计划仍可读取和恢复。

新增回归覆盖 G1 缺失/未准入拒绝、bundle 树绑定、设备绑定、篡改拒绝、暂停恢复和确定性
合并。实验矩阵、分片和学习运行时定向测试为 `26 passed, 1 warning`，scalable 全量为
`292 passed, 1 warning`。当前实际模型仍全部未获 assist 准入，因此本次只关闭“学习变体
没有可恢复正式执行基础设施”的实现缺口，没有生成任何 G1/A1/A2/A3/C1/F1 正式 episode。

正式学习变体分成两个证据阶段。预准入阶段由模块 owner 使用未见 seed、隔离采用和
paired-shadow 结果生成新的 evidence-bound bundle。D3 和 D4 模块专用 assembler 尚未
实现；D5 G1 已形成当前运行时 v5 证据资格，但六项运行权限均为 false；A3 assembler
仍未实现。main 已实现与 v5 分离的人工批准影子实验授权合同，但尚无批准实例；因此受控
G1 作用域仍未启动。
正式 scope 完成后，D6 使用
`d6.learning-scope-formal-evidence-audit.v1` 重新校验 execution plan、bundle 文件树、
merge、shard、cell 和 episode 证据，并与唯一同键 R0 比较。D6 审计要求模型实际采用，
shadow、规则回退、仅加载模型、D5 零候选边、缺物理结果或缺 R0 均判为
unavailable/fail-closed；该口径适用于后续 assist 收益声明。获批 G1 影子 scope 只评估
候选边概率和运行风险，不声明在线采用或物理收益。审计从不授予模型晋级或控制权限。

模型文件存在、哈希有效、开发指标可用或 D6 审计合同通过单元测试均不能替代 assist
准入。当前没有实际学习 scope、merge 或可用 R0 配对输入，正式学习 episode 仍为 0。

## 正式 R0 后验收尾状态（2026-07-25）

绑定 clean commit `2c7b425d076899e1c54a3d87d6ef23a613ba6e3a` 的正式 R0 已完成
20/20 分片和 900/900 单元。执行计划 SHA-256 为
`3e96e434c485e84aa85b654d93f9a022bd0216272390d852c73763d961ae4fb8`。
合并结果只能声明 `formal_scope_complete=true` 和
`formal_matrix_complete=false`，不能代表完整 5700 单元七变体矩阵完成。

D6 首轮评估确认 895 个单元满足 clean-formal 准入，5 个 `delayed_noisy` 单元失败：
5v5 的 seed 1000、1005、1008、1018，以及 20v20 的 seed 1009。失败原因是 main 在
episode 收尾时使用简化 D2 输入签名跳过最后 D1 后验；该签名没有包含状态有效时刻、六维
状态和协方差。五项最终 D1 后验相对 D2 最后实际消费后验均发生了语义变化，最大状态差
为 `0.415096`，最大协方差元素差为 `22.623443`，最大时刻差为 `0.255046 s`。计数守恒
不能替代完整后验内容一致性。

main 已移除 finalize 的简化签名跳过。最后一代 D1 后验现在必须实际调用 D2 Tracker，
只有 D2 成功发布后才能清除 pending generation。重复来源证据由 D2 已有 replay-coast
路径隔离，不增加命中、不创建新航迹、不刷新原始证据时钟。D7 的比例导引、视觉比例导引、
视线滤波和切换公式未修改。四个 5v5 尾帧均为 5/5 coast；20v20 seed 1009 的 20 条重复
证据全部隔离，其中 19 条在宽限期内 coast，1 条超过宽限期并按既有生命周期增加一次 miss。

五个原失败单元已按原 2.0 秒配置完成开发态定向复跑。D6 v10 对五项后验代次合同均判为
`verified`：D1 最终代次等于 D2 最终消费代次，D2 消费次数等于发布次数，
`consumption + pre_tick_merge = generation`，skip 为 0，pending 为空，在线真值使用为
0。scalable 全量为 `285 passed, 1 warning`，D2 为 `305 passed, 1 warning`，D6 为
`894 passed, 1 warning`。warning 均为本机 Matplotlib `Axes3D` 导入冲突。

这些定向结果来自脏工作树，只证明代码修复和失败 seed 回归通过。修复已形成分批提交
`4b018e4`、`dc5821f`、`8e955f3` 和 `98d01bf`，提交历史未改写。正式 R0 仍须在最终文档
同步后的 clean HEAD 和新 execution plan 下从 900 个单元整体重跑，不能将新 5 项与旧
895 项拼接。当前正式产物约 22 GiB，旧失败现场约 1.2 GiB，文件系统仅余约 24 GiB；
在保留 20 GiB 运行下限的条件下无法并存第二份约 22 GiB 正式矩阵。旧证据在获得明确
清理或迁移授权前保持不动。

专项记录见
`docs/SCALABLE_3D_FORMAL_R0_FINALIZATION_P0_20260725_CN.md`。

### 修复后正式重跑进度

修复后的正式 source 冻结为
`1e5ed8ddcf27f375e922a447decfbd875d21bfdf`，execution plan SHA-256 为
`8804ecb4dd0513db55906905f031832711012974fc911546df40e09fb297d373`。父清单仍为
5700 单元，R0 scope 仍为 900 单元，20 个分片各覆盖一个保留 seed。

当前 shards 0、5、9 已完成 45/45，共 135/900 单元，无恢复和暂停。D6 v10 单独复核
三个已覆盖的原失败 cell：

- `delayed_noisy/5v5/seed_1000`；
- `delayed_noisy/5v5/seed_1005`；
- `delayed_noisy/20v20/seed_1009`。

三项均为 `clean_formal_experiment_matrix`，formal acceptance eligible 为 3/3，
generation contract 为 3/3 `verified`，failure reason 为空。D1 最终代次等于 D2 最终
消费代次，消费次数等于发布次数，skip 为 0，pending 为空。原失败的 5v5 seeds 1008、
1018 仍未在新计划下重跑。

新批次当前约 3.3 GiB。文件系统可用字节为 `21539827712`，只比 20 GiB 下限
`21474836480` 多约 65 MB，main 已停止启动新单元。该进度证明 3/5 原失败项在新 clean
source 下正式闭合；完整 R0 仍为 135/900，不能声明 scope 完成或 900/900 正式验收。

## 正式 R0 分片合同（2026-07-25）

main 已新增正式实验矩阵的可恢复分片执行层。执行计划先保存完整
`ExperimentMatrixPlan.cells()` 清单，固定 R0、G1、A1、A2、A3、C1、F1 共 5700 个
父单元，再从同一父清单选择 900 个 R0 单元。R0 不再拆成多个互不相关的非正式子计划。
默认采用 20 个分片，每片 45 个单元。按 R0 范围索引取模后，每个分片对应一个保留 seed，
覆盖 9 类场景和 5 档规模。

每个单元先写入带计划哈希和单元编号的临时目录。episode 完整写盘、有限状态和在线真值
使用检查通过后，目录原子发布，再追加进度行并原子推进 checkpoint。恢复入口逐行验证
源提交、完整父计划、分片顺序、单元结果 SHA-256 和 episode 文件树 SHA-256。checkpoint
落后于完整进度行时可恢复；checkpoint 超前、进度截断、目录越界、重复单元或制品篡改
均失败关闭。命令行运行器默认保留 20 GiB 可用磁盘；低于下限时不启动下一个单元，只在
完整 episode 边界暂停。

分片合并只生成 `experiment_matrix_scope_manifest.json`。900 个 R0 单元完成时状态为
`formal_scope_complete`，同时明确记录 `formal_matrix_complete=false`。只有执行范围与完整
5700 单元父清单完全相等时，才允许生成兼容的完整矩阵 manifest。因此 R0 批次不能被误写
为七变体正式矩阵完成。

本轮分片专项现有 14 项测试，并保留原矩阵测试；暂停/恢复、低磁盘暂停、checkpoint 滞后
恢复、制品篡改拒绝、学习 bundle/设备绑定、学习运行证据校验、确定性合并和真实单 episode
写盘均通过。scalable 全量为 `292 passed, 1 warning`。warning 仍来自本机 Matplotlib
`Axes3D` 导入冲突。

绑定 clean commit `32b3b40` 的首次执行曾在 shard 0 第 45 个单元暴露 D3 旧联盟需求库存
问题，该现场继续作为历史失败证据。D3 修复后，main 使用 clean commit `2c7b425` 重新生成
execution plan 并从零完成 900 个 R0 单元。随后 D6 暴露的五项后验收尾失败已在上节记录；
因此当前状态是“R0 scope 执行完成，formal acceptance 待新 clean 提交整体重跑”。

## D4 因果通信与 M 对 N 联盟闭环（2026-07-25）

main 已将 D4 控制消息接入与传感器消息相同的确定性通信网络。二级节点就绪、区域计划广播
和联盟成员确认均先形成发送意图，再经过时延、抖动、丢包、带宽序列化和分区代次检查。
D4 只消费实际送达且通过 plan/version/epoch/lease/payload digest 校验的收据。关闭通信时，
中心失效后的区域授权保持失败关闭，D7 全部输出 `d4_hold_for_review`。

D4 owner 已修复联盟提案过早终结问题。提案和部分确认在租约内保持
`collecting_acks`；全部必要成员确认后原子进入 `committed`。过时或无效确认只记录并拒绝，
不授权执行，也不允许单条伪造消息永久终结仍可完成的联盟。摘要冲突、网络分区、租约到期、
成员不可执行和显式终结继续进入 `aborted/reconfiguring`。

main 使用 2 个目标、4 个资源、1 个高空侦察节点完成真实网络往返回归。高威胁目标需要
2 架主拦截机和 1 架备用机；中心在 `1.5 s` 失效，单程通信时延为 `40 ms`。二级计划在
`2.0 s` 发布，`2.05 s` 时三成员均未确认，联盟不授权；`2.10 s` 三个确认全部到达后原子
提交。提交前两架主机和备用机均保持；提交后两架主机进入三维中段比例导引，备用机继续
待命。下一周期区域计划升级为版本 3 时重新执行广播和确认，未复用旧版本授权。

本轮同时修复区域授权租约归一化：同一区域不同任务的提交证据全部收紧到该区域最短有效
租约，避免 D3 因单成员任务证据超出区域授权而拒绝下一周期计划。保留种子干预选择器也已
改为选择完成因果裁决的帧，故障代次栅栏不再被当成已完成接管。

验证结果：

- D4 模块全量：`569 passed`；
- scalable 3D 模块栈：`66 passed, 1 warning`；
- scalable 3D 全量：`272 passed, 1 warning`；
- 在线真值使用、`global_track_id` 改写和通信证据拒绝计数：本专项均为 `0`。

D6 正式矩阵准入预检仍为 `fail_closed`。实际清单为 5700 个单元，通过数为 0。正式运行
manifest、逐单元结果、置信区间、动画和已获 assist 权限的学习模型尚未形成。本轮结果只
关闭 D4 因果通信和三成员联盟的集成阻塞，不代表 5700 单元正式矩阵或 200 对 200 实时目标
已完成。

## 模块所有者收尾复核（2026-07-25）

D1、D3、D4、D5、D6 和 D7 已分别复核本轮未提交代码、测试、README、PLAN、模块文档和
GAP。复核没有发现新的运行级 P0，并修正了四个会影响后续正式证据的问题：

- D1 离线评分按唯一接受观测计算谱系覆盖率，并把真值与虚警共存计入混合谱系和纯度；
- D3 多周期影子评估把可选 `cost_weights` 对称传入规则组和处理组的独立代价模型；
- D6 对 D4 模型清单中的非法保留种子数字段按未授权失败关闭，不再抛出未治理异常；
- D7 在命令计算前回收失效 pair 状态，并在状态变更前拒绝同批次重复资源索引或资源编号。

模块回归结果为 D1 `496 passed`，D3 `464 passed, 1 skipped`，D4 `569 passed`，
D5 `552 passed`，D6 `889 passed, 1 warning`，D7 `220 passed`。D3 唯一跳过项是未安装的
可选 OR-Tools；D6 warning 和 main 模块栈 warning 均为既有 Matplotlib `Axes3D` 导入问题。
所有 owner 均完成 scoped `git diff --check` 和 Python 语法检查。修正后的统一模块栈再次
通过 `66 passed, 1 warning`。

这些结果仍是开发和合同回归证据。D3 残差、D4 区域策略、D5 图模型与主动视觉模型保持
development/shadow-only；D5 冻结图模型在遮挡重现代理下的边/簇 F1 仅为
`0.563264/0.572845`。正式 R0、多随机种子物理结果、实时目标、AirSim 和模型 assist 准入均
未关闭。

## D1 在线发布证据子集快照候选（2026-07-25）

main 已实现独立的 D1 consistency evidence 快照范围 selector。默认
`full_consistency_snapshot_v1` 继续读取当时全部在线证据；候选
`required_observation_subset_v1` 只请求同一 release cycle 内当前源扫描观测和已物化公开
航迹 `latest_observation_id` 的确定性去重集合。第一轮 A/B 的两臂均保持 D1 replay-prefix
reference `per_checkpoint_prefix_rebuild_v1`，不会把前一正式拒绝候选混入新 treatment。

候选调用 D1 既有精确非破坏性子集接口。未知或非法 ID、返回集合缺项均回退全量快照并记录
原因；正式准入要求 fallback、lookup miss 和非法 ID 为 0。episode 最终离线 consistency
export 仍走全量精确物化，不改变 pending ledger 清零、双时间戳、协方差、NED、
`global_track_id`、来源谱系、门控或 D1 fused-track payload。

selector、完整实现 ID、执行配置和诊断已进入 runtime profile、observation governance、
module final 和 episode summary；CLI 为
`--d1-publication-evidence-snapshot-implementation`。3 对 3 定向回归确认两臂 D1
publication payload 完全一致，候选 fallback/lookup miss 为 0，返回记录少于 reference；
未知 ID 和空 required 集合专项确认候选回退 full 并保留原因。
`test_module_stack.py` 为 `62 passed`，scalable 全量为 `263 passed, 1 warning`。

clean `028ac34`、seed 1151 的 200/200/2 单配对 smoke 已完成。D1/D2 在线记录 SHA、
consistency digest/count 和原 D1 操作计数一致；candidate 14/14 子集成功，
fallback/lookup miss 为 0，返回记录由 `13679` 降至 `4429`，减少 `67.621902%`。
单 pair 的 D1、module stack 和外部命令计时方向不一致，因此当前只允许进入矩阵预注册。

正式矩阵已冻结为
`configs/d1_publication_evidence_snapshot_multiseed_v1.json`，包含 10 个
2.2 秒 short seed 和 3 个 10 秒 long seed，规模固定为 200/200/2。matrix、
evidence 和 D6 evaluator 使用独立 schema；两臂只允许发布证据快照 selector 不同，
回放前缀保持 `per_checkpoint_prefix_rebuild_v1`。矩阵运行器定向测试为 `63 passed`。

clean `d0219eb` 上已完成 13 对/26 个 fresh episode，0 reused、0 failed。D6 独立确认
13/13 业务语义、consistency digest/count、原 D1 操作计数、实现身份和诊断审计通过；
候选 429/429 次子集成功，返回记录由 `1602170` 降至 `133917`，削减
`91.641524%`，且 fallback/lookup miss/非法或空 required 均为 0。

D6 正式判定 `reject`：short 候选更快 `4/10 < 8/10`，D1 fusion 改善
`-0.147877% < 1%`，bootstrap 上界 `1.374681% > 0%`。默认继续使用全量快照。
候选最低实时因子 `0.203423 < 1`；本证据不覆盖 AirSim、目标硬件、实机或实飞。当前
scalable 全量回归为 `268 passed, 1 warning`。clean smoke 与正式结果分别见
`docs/D1_PUBLICATION_EVIDENCE_SNAPSHOT_CLEAN_SMOKE_20260725_CN.md` 和
`docs/D1_PUBLICATION_EVIDENCE_SNAPSHOT_FORMAL_EVALUATION_20260725_CN.md`。

## D1 固定滞后回放前缀摘要正式拒绝（2026-07-25）

main 已接入 D1 回放前缀实现选择器。默认
`per_checkpoint_prefix_rebuild_v1` 继续逐 checkpoint 重建归一化创新平方、门控标识和
一致性证据计数；候选 `fixed_lag_checkpoint_prefix_cumulative_summary_v1` 只对版本、
身份、顺序和完整性均可信的 checkpoint 前缀复用不可变累计摘要。候选把一致性证据刷新
记录为有界区间账本。在线 publication 使用精确非破坏性快照，写入、失效、固定滞后重基准
和 episode 最终离线证据导出前精确物化。6 秒固定滞后窗口、后验状态、协方差、双时间戳、
门控元数据和原有操作计数均不变。

正式矩阵绑定 clean commit `7d2e987471b521a1e531bf03a5c99af5096f676a` 和 matrix
SHA-256 `85432d729877eff97e6f3dd517d4baa7a47f44a4fa42e6bfdc7ce85b8d9ec74b`。
short seeds 1151-1160、long seeds 1151-1153 共形成 13 对/26 个 fresh 200/200/2
三维质点 episode，0 reused、0 failed。D6 独立确认 13/13 对业务语义、consistency
records digest/count、原 D1 操作计数、实现身份、诊断守恒和在线真值隔离通过。

局部压缩没有形成稳定的全栈收益。候选总内部物化记录减少 `52.150746%`，long D1
fusion 改善 `2.361778%`；但 short 更快仅 `5/10 < 8/10`，short D1 fusion 改善
`0.959611% < 1%`，short bootstrap 原始变化 95% 上界
`0.619827% > 0%`，short core 改善 `-0.256641% < 0.25%`，long core 改善
`-1.930083% < 0.25%`。在线精确快照仍投影构造 `656481` 条记录，解释了压缩内部物化后
核心墙钟未改善的主要开销。

D6 verdict 为 `reject`，main 默认继续使用 `per_checkpoint_prefix_rebuild_v1`；候选只保留
为显式研究路径。候选最低实时因子为 `0.197441 < 1`，系统实时缺口未关闭。正式报告位于
`../d6_evaluation_metrics/outputs/d1_replay_prefix_summary_multiseed_20260725_formal_7d2e987_d6/`；
同一冻结 manifest 的重复评估与正式 bundle 全部输出 SHA-256 一致。本结论只覆盖三维质点
仿真，不代表 AirSim、目标处理器、硬件、实机或实飞能力。后续若研究按 publication 所需
观测标识投影快照，必须使用新的实现标识和预注册矩阵，不修改本次冻结证据。

## D1 关联稀疏预筛正式 A/B（2026-07-25）

main 已接入 D1 关联稀疏预筛实现选择器。参考路径 `disabled_v1` 保持原精确关联；
候选 `modality_conservative_quadratic_bound_v1` 使用
`r^T S^-1 r >= ||r||^2 / ||S||_inf` 的保守下界，仅在下界已经超过原门限时提前剔除。
无法认证、奇异或非有限输入继续 fail-open 到精确求解。候选不改变精确门限、创新残差、
双时间戳、协方差、状态机、在线真值隔离或 `global_track_id`。

正式矩阵绑定 clean commit `9302ccede2ca513c2235370e1a464fc88bc41150` 和 matrix
SHA-256 `a7162d014d1c3c0f207355b24a5d7159bf3486d134ca21876f7469d1e915b71d`，
包含 10 对 short、3 对 long，共 13 对/26 个 fresh 200/200/2 三维质点 episode。
D6 独立确认 13/13 对业务语义、有限状态、实现身份、预筛审计、在线真值使用为 0，
并且逐 pair、逐模态 exact gate-pass 完全相等。候选将非雷达精确求解从 `298109`
降至 `39837`，削减 `86.636767%`。

局部求解削减没有形成稳定的全栈收益。short D1 fusion 改善 `0.228437%`、候选更快
`7/10`，short bootstrap 原始变化 95% 上界为 `0.443531%`，short core 改善
`0.091096%`；long D1 fusion 改善 `0.713776%`。这五项均未达到冻结门，D6 verdict
为 `reject`。main 默认继续使用 `disabled_v1`，候选只保留为显式研究路径。候选最低
实时因子为 `0.206273 < 1`，系统实时缺口未关闭。

正式报告位于
`../d6_evaluation_metrics/outputs/d1_association_sparse_prefilter_multiseed_20260725_formal_9302cce_d6/`。
本结论仅覆盖三维质点仿真，不代表 AirSim、目标处理器、硬件、实机或实飞能力。

## D1 在线批帧交接默认晋级（2026-07-25）

main 已将 D1 原始在线批次到 `SensorScanFrame` 的默认交接实现晋级为
`closed_immutable_batch_to_frame_v1`。该路径先完成整批在线身份检查，再生成封闭的不可变
快照，最后对只读帧执行完整身份检查；`convert_then_frame_v1` 继续保留为命令行显式回退。
选择器、完整实现标识、执行配置和
`d1.online_batch_frame_handoff_diagnostics.v1` 均进入 runtime profile、episode summary、
module final 和 observation governance。

晋级依据是 clean commit `43feaf600f288a85ce76a76862334256f0d0d352` 上的
13 对/26 episode 三维质点正式矩阵。D6 独立评估确认 13/13 对业务语义、有限状态、
在线真值隔离、实现身份和批帧守恒通过。short/long 的 scan input 墙钟分别改善
`38.289241%/36.275282%`，核心墙钟改善 `4.252745%/4.916501%`；候选
2665/2665 次请求均走 closed handoff，重复量测身份检查减少 `100%`，fallback 为 0。

该准入只支持默认选择器晋级。候选最低实时因子为 `0.204490`，200 对 200 系统实时缺口
仍未关闭；`long_seed_1121` 的 D2 association 单对增幅为 `14.408510%`，后续容量试验继续
观察尾部波动。正式报告位于
`../d6_evaluation_metrics/outputs/d1_online_batch_frame_multiseed_20260725_formal_43feaf6_d6/`。
冻结矩阵和历史证据仍保留 reference/candidate 原始语义，不随默认值修改。

## D1 不透明来源标识缓存 A/B（2026-07-25）

main 已接入 D1 来源节点、发布 epoch 和航迹标识三段字符串的显式构造实现选择器。
参考实现 `per_publication_build_v1` 在每次 GlobalTrack 发布时重新构造；候选
`bounded_generation_lru_v1` 以
`publisher_node_id + publisher_epoch + track_id` 为精确键，在同一发布代际内复用不可变
字符串。缓存容量默认 1024、上限 4096，节点或 epoch 改变时失效。候选默认关闭，命令行
参数为 `--d1-opaque-source-identity-implementation` 和
`--d1-opaque-source-identity-cache-capacity`。

该候选只在显式启用 `--d1-publish-opaque-source-key` 时有工作量。默认无来源键 R0
不会发起缓存请求，因此本次 A/B 不能外推为默认主线收益。selector、容量、实现 ID 和请求、
构造、命中、未命中、淘汰及失效诊断已进入 runtime profile、summary、module final 和
observation governance。两条路径不改变来源键业务值、双时间戳、NED 状态、协方差、
fixed-lag/OOSM、D2-D7 消费结果或全局航迹编号。

D1 模块微基准使用 200 条航迹、每样本 56 次发布和 7 次交错采样。参考/候选中位耗时为
`0.348622/0.127734 s`，候选 `7/7` 更快，标识构造由 `78,800` 次降至 `200` 次。main
随后在 clean `d8fc76c066f21b077154f7be33c0b43558d237e5` 上完成 10 组 2.2 秒 short
pair 和 3 组 10 秒 long pair，共 26 个 fresh arm，0 reused、0 failed。

D6 确认 13/13 pair 的业务语义、有限状态、在线真值隔离、实现身份和缓存守恒通过。
short/long 的 D1 fusion 改善 `9.465972%/6.437432%`，核心墙钟改善
`2.845610%/2.728043%`；候选标识构造减少率和缓存命中率均为 `99.163670%`。
long D2 association 组均值增加 `5.605213%`，超过冻结上限 `5%`，其中
`long_seed_1101` 增加 `19.069868%`。该 pair 按预注册矩阵保留，门限未调整。

D6 判定 `optimization_admitted=false`。main 默认继续使用
`per_publication_build_v1`，候选只保留为显式实验路径。候选最低实时因子为
`0.193887`，`system_realtime_gap_closed=false`。正式报告位于
`../d6_evaluation_metrics/outputs/d1_opaque_source_identity_cache_multiseed_20260725_formal_d8fc76c_d6/`。
后续若复核 D2 波动，必须使用新的预注册确认矩阵，不能覆盖本次拒绝结论。

## D1 结构稀疏数值雅可比 A/B（2026-07-25）

D1 已提供结构稀疏数值雅可比实现。参考实现
`dense_output_probe_v1` 对六维状态逐列执行中心差分；候选
`known_dimension_structural_columns_v1` 使用量测模型已知输出维数，只计算观测方程实际
依赖的状态列。声学、光电、激光雷达和无径向速度雷达只计算三个位置列；含径向速度雷达仍
计算全部六列。活动列保留相同步长和浮点运算顺序，不改变双时间戳、NED、协方差、
fixed-lag/OOSM、门限、量测频率或全局航迹编号。

D1 冻结微基准包含 480 个混合量测模型、每样本 20 轮和 9 次交错采样。参考/候选中位耗时为
`0.444645/0.319552 s`，改善 `28.13%`，候选 `9/9` 更快；量测函数求值由
`124,800` 降至 `72,000`。雅可比、归一化创新平方和门控决策 SHA-256 一致。该结果只支持
进入 main 全栈准入，不构成 200 对 200、AirSim 或系统实时证据。

main 通过 `--d1-structured-numerical-jacobian-implementation` 显式选择两臂。选择器、
D1 完整实现 ID、操作数和守恒检查进入 runtime profile、observation governance、
module final diagnostics 和 episode summary。预注册矩阵为
`configs/d1_structured_numerical_jacobian_multiseed_v1.json`，包含 10 组 2.2 秒 short
pair 和 3 组 10 秒 long pair。

main 在 clean `9d1f54f8540fdc4a7a1011121aafac5718290122` 上完成 13 组 pair、
26 个 fresh arm，0 reused、0 failed。D6 独立校验 13/13 pair 的业务语义、有限状态、
在线真值隔离、实现身份、操作数守恒、性能和内存证据。short/long 的 D1 fusion 改善
`6.084778%/4.676061%`，核心墙钟改善 `1.897370%/1.786530%`，候选分别
`10/10`、`3/3` 更快；量测函数求值减少 `53.846154%`。全部冻结准入门通过，
`optimization_admitted=true`。

scalable 3D 集成默认已晋级为 `known_dimension_structural_columns_v1`，
`dense_output_probe_v1` 继续作为显式回退和 A/B 参考。D1 独立 `FusionAdapter` 的默认值
仍由 D1 模块维护，本次集成准入不改写该边界。候选最低实时因子为 `0.180726`，
`system_realtime_gap_closed=false`；本结论不包含 AirSim、目标处理器或实飞证据。正式
报告位于
`../d6_evaluation_metrics/outputs/d1_structured_jacobian_multiseed_20260725_formal_9d1f54f_d6/`。

## 在线真值守卫实现 A/B（2026-07-24）

main 已为 episode 总线的递归在线真值字段检查增加显式实现选择器。参考实现为
`generic_recursive_v1`，候选为 `builtin_specialized_recursive_v2`，命令行参数为
`--online-truth-guard-implementation`。候选只针对精确内置 `dict/list/tuple/set/frozenset`
使用专门遍历，仍对键和值递归检查，并保留循环保护、非有限状态检查和禁止字段拒绝语义。
选择器与诊断进入 episode manifest 和 summary。候选保持默认关闭，默认路径仍为
`generic_recursive_v1`。

正式矩阵冻结在 `configs/online_truth_guard_multiseed_v1.json`，SHA-256 为
`764574b9897d00101c26c555de2f407e1736c7e6ff50420eebf131e154618dc8`，producer commit
为 `8d8bb6ed7a417705236835f235361f45a021bb2b`。矩阵完成 10 组 2.2 秒 short pair 和
3 组 10 秒 long pair，共 26 个全新 200 对 200 arm；0 个复用，0 个失败。13/13 pair 的
业务语义、有限状态、在线真值隔离、实现身份和检查数守恒全部通过。

候选将 short/long 发布总线及收尾墙钟分别由 `0.900293/3.810588 s` 降至
`0.696858/2.834910 s`，改善 `22.58%/25.63%`，对应 `10/10` 和 `3/3` 更快。short 核心
墙钟改善 `2.50%`，但 long 核心墙钟回退 `3.47%`；long D1 fusion 和 D2 association
分别增加 `5.29%` 和 `7.34%`，超过预注册 `5%` 上限。D6 正式判定
`optimization_admitted=false`、`system_realtime_gap_closed=false`，候选最低实时因子为
`0.165369`。

long seed 1102 的反向变化可在后续 balanced-order v2 诊断中复核主机热状态和运行顺序，
但诊断不得覆盖本次 v1 正式拒绝结论。正式报告位于
`research_modules/d6_evaluation_metrics/outputs/online_truth_guard_multiseed_20260724_formal_8d8bb6e/`。

## D1 常速度模型构造 A/B（2026-07-24）

main 已接入 D1 常速度状态传播模型的显式 A/B 选择器：
`per_prediction_build_v1` 为逐次构造参考实现，`bounded_exact_lru_v1` 为精确键、有界
最近最少使用缓存候选。命令行使用 `--d1-cv-motion-model-implementation` 选择实验臂，
使用 `--d1-cv-motion-model-cache-capacity` 设置 1 至 4,096 的容量。正式多 seed 准入
通过后，main 默认已晋级为 `bounded_exact_lru_v1`，容量默认 128；
`per_prediction_build_v1` 继续作为显式参考路径。

两条路径执行同一常速度状态转移和过程噪声计算，不量化时间差，不改变双时间戳、NED
坐标、协方差、固定滞后回放、量测门控或全局航迹编号。选择器、容量、D1 实现标识以及
预测请求、模型构造、缓存命中、未命中和淘汰计数进入 runtime profile、observation
governance、module final diagnostics 和 episode summary。运行清单哈希可区分两个实验臂。

D1 模块内冻结 benchmark 使用 200 个状态、100 步传播和 7 次交替采样，参考/候选中位耗时
为 `0.220679/0.103950 s`，候选约为 `2.12x`，模型构造数由 `20,000` 降至 `8`，最终状态
SHA-256 一致。main 随后在 clean
`44223566439a446fc49f2a3fd861d1d51bd676b9` 上运行 10 组 2.2 秒 short pair 和 3 组
10 秒 long pair，共 26 个全新 200 对 200 arm。13/13 业务语义、有限状态、在线真值
隔离、实现身份和缓存审计通过。

short/long 的 D1 fusion 分别由 `3.289739/23.304548 s` 降至
`3.061518/21.776847 s`，改善 `6.9271%/6.6103%`；核心墙钟改善
`2.4060%/2.4537%`。D2 association 变化为 `-0.1082%/-2.6729%`，RSS 均值增幅为
`0.0145%/0.2959%`。候选 13 个 episode 的缓存命中率和模型构造减少率均为
`99.5960%`。所有预注册门通过，D6 判定 `d1_optimization_admitted=true`。

候选最低实时因子为 `0.1739499`，未达到 `1.0`，因此
`system_realtime_gap_closed=false`。该矩阵不包含 AirSim、目标处理器、RMSE、NEES、NIS
或严格身份精度。正式报告位于
`research_modules/d6_evaluation_metrics/outputs/d1_cv_motion_model_cache_multiseed_20260724_formal_4422356/`。

## D1 GlobalTrack 发布元数据 A/B（2026-07-24）

main 通过 `--d1-publication-metadata-implementation` 显式选择参考实现
`per_track_copy_v1` 或当前候选 `immutable_shared_v2`。参考实现为每条航迹复制扫描级
审计树。v2 候选使用 D1 定义的 `d1.publication_audit_tree.v2` 不可变合同共享审计子树，
D2 对每个新对象先完成一次结构验证和内容审计，随后才允许按对象身份复用结果。选择器、
D1 实现标识、合同版本、D1 操作计数和 D2 审计计数同时写入 runtime profile、
observation governance 和 summary。当前运行时明确拒绝历史候选
`immutable_shared_v1`。

历史 v1 正式矩阵位于 `configs/d1_publication_metadata_multiseed_v1.json`。该矩阵完成
10 组 2.2 秒 short pair 和 3 组 10 秒 long pair，共 26 个同提交 200 对 200 episode。
D1 fusion 的 short/long 改善为 `16.29%/31.05%`，但 D2 association 分别增加
`53.44%/169.89%`，核心墙钟只改善 `1.65%/1.21%`，未达到预注册 `5%` 门限。D6 判定
`d1_optimization_admitted=false`。v1 配置、运行器兼容入口和报告只用于复核历史结果，
不再作为当前候选。

v2 预注册矩阵为
`configs/d1_publication_metadata_v2_multiseed_v1.json`，保持相同的 short/long seed、
规模、arm 交错顺序和同一 clean commit 约束，新增 D2 association 增幅不超过 `5%`、
D2 v2 合同验证、内容审计、身份复用和零拒绝门。运行器仍为
`scripts/run_d1_publication_metadata_matrix.py`，但 v1/v2 使用独立 evidence schema 和
D6 evaluator schema。main 在 clean 提交
`be399e138762f5e660f553c8caa812d52ab38c61` 上完成全部 13 组 pair、26 个 arm，
未复用旧 episode。13/13 业务语义、有限状态、在线真值隔离、实现身份和 D2 审计通过。

short/long 的 D1 fusion 分别改善 `13.54%/26.83%`，核心墙钟改善
`6.57%/18.24%`，D2 association 分别下降 `16.19%/35.62%`。候选累计执行
`702` 次合同验证、`702` 次内容审计、`139,920` 次身份复用和 `0` 次合同拒绝。D6 判定
`d1_optimization_admitted=true`，main 默认已晋级为 `immutable_shared_v2`；
`per_track_copy_v1` 继续作为显式参考路径。候选最低实时因子为 `0.1730801`，未达到
`1.0`，因此 `system_realtime_gap_closed=false`。正式报告位于
`research_modules/d6_evaluation_metrics/outputs/d1_publication_metadata_v2_multiseed_20260724_formal_be399e1/`。

该 main-owned 模块提供可复现、真值隔离的三维质点环境，用于逐步建设 200 架拦截无人机
对 200 个来袭目标的 D1-D7 完整闭环。现有 `integrated_simulation` 保留为小规模回归基线。

当前阶段已实现世界状态、三维动力学、透视投影、传感器场景、传感器到融合中心的通信
队列、版本化 episode 总线和确定性环境基线。通信队列按配置施加时延、抖动、批次丢失和
序列化带宽开销，并把网络投递时刻写回观测 `arrival_timestamp`。`IntegratedScalableModuleStack` 已把 D1 六维融合、D2 稀疏关联、
D3 稀疏分配、D4 区域权限、D5 匿名跨视角配准和 D7 三维比例导引接入同一在线时钟。
模块栈只做接口转换与调度，各算法仍由 D1-D7 原模块维护。

D5 主动视觉已接入同一 episode 状态机。main 持久化每个拦截/侦察相机的绝对指向、视场
模式及最近接受的计划、联盟和通信版本。D5 只读取 D2 中心航迹、D3 当前分配、D5 几何
证据和相机反馈，输出观察目标、重捕获、扇区搜索或保持命令。命令在下一视觉帧生效并产生
独立 ACK；过期、过时版本、资源不一致和退化指向均由 main 拒绝。该路径不创建分配，也不
改写 `global_track_id`。

main 还在 D3 发布新计划的同一调度周期，将计划逐项绑定到 D7 命令并发布
`runtime.assignment_plan_ack`。确认记录携带计划编号、版本、所有者、每个资源与中心航迹的
绑定、导引模式和保持原因，并绑定来源 D3/D7 总线序号与规范载荷 SHA-256，不携带仿真目标
真值。确认还原样携带 D3 学习代价和 D4 区域建议的 considered/applied/fallback 元数据，缺失
字段保持为空。该记录只证明计划被运行时接收以及绑定是否进入 D7，不把五米接近、任务完成或
规则教师诊断写成结果与奖励。

main 现已把该确认链自动接入 D6 离线结果联接。存在运行时计划确认的 episode 会额外写出
`d6_runtime_plan_outcomes/input_specification.json`，其中登记在线总线、D2 离线身份映射、
三维真值状态、五米接近事件、场景配置和 episode manifest 共 11 项输入及 SHA-256。D6 先
复载并校验该清单，再按确认序号和时间戳建立互不重叠的资源-航迹窗口。同一计划编号和版本
允许产生明确标记的评估刷新窗口，但资源绑定、联盟和 authority 执行签名必须保持不变。
每个窗口输出起始、结束、最小三维距离和五米事件；距离进展只记为诊断，不作为 D3 正式奖励。
输入清单、联接结果、中文报告和 main provenance manifest 均随 episode 保存。

## 2026-07-24 D1 扫描输入正式多 seed 准入

main 在 clean 提交 `d14285e4fdeb2f2e2cd32fad2f6d42e30f9e73a7` 上完成同提交
`reference_v1/candidate_v2` 对照。矩阵包含 10 组 2.2 秒 short pair 和 3 组 10 秒
long pair，每个 episode 为 200 个目标、200 个资源和 2 个侦察节点。26 个 arm 全部正常
退出；13/13 pair 的业务语义、有限状态、在线真值隔离和实现身份检查通过。

short 扫描输入累计墙钟均值由 `1.212452 s` 降至 `1.145650 s`，逐 pair 平均改善
`5.360122%`，9/10 seed 更快，原始相对变化 bootstrap 95% 区间为
`[-8.208165%, -3.084141%]`。long 由 `6.687633 s` 降至 `6.340680 s`，改善
`5.142482%`，3/3 更快，区间为 `[-8.837129%, -1.669361%]`。核心墙钟和内存门通过，
D6 判定 `d1_optimization_admitted=true`。

系统实时 P1 未关闭。核心墙钟 short/long 只改善 `0.7187%/0.5792%`，候选最低实时因子为
`0.143427`。当前证据来自三维质点环境，不包含 AirSim、目标硬件、RMSE、NEES、NIS 或严格
身份指标。报告、紧凑 JSON 和曲线见
`docs/SCALABLE_3D_D1_SCAN_INPUT_MULTISEED_REVIEW_CN.md`、
`docs/SCALABLE_3D_D1_SCAN_INPUT_MULTISEED_SUMMARY_20260724.json` 和
`docs/figures/d1_scan_input_multiseed_improvements.png`。原始 4.2 GB episode 不进入源码目录。

## 2026-07-24 D1 协方差优化正式多 seed 准入

PSD-safe V3 矩阵已完成 10 组 short pair 和 3 组 long pair，共 26 个 200 对 200 episode。
reference `a5a472cf81496d94a98db3deb88a3d5c6951f0ce` 与 candidate
`064cbb979d3bab68fee995e476df25709eb666db` 共同包含正半定修复，只在标量或向量化协方差
限制路径上存在处理差异。13/13 跨构建业务语义检查通过，进程退出、有限状态、D2 审计和
在线真值隔离均通过。

short 的 D1 融合累计墙钟由 `4.029165 s` 降至 `3.652252 s`，改善 `9.35462%`，
10/10 seed 更快，原始配对变化 bootstrap 95% 区间为 `[-10.914359%, -8.113134%]`。
long 由 `32.954357 s` 降至 `30.768826 s`，改善 `6.631993%`，3/3 seed 更快，区间为
`[-7.279095%, -5.406805%]`。预注册 12 项门全部通过，D6 判定
`d1_optimization_admitted=true`。

系统实时 P1 未关闭。candidate 的 short/long 实时因子均值为 `0.212769/0.149857`，最低
值为 `0.143397`；矩阵也不包含 AirSim、目标硬件、均方根误差、归一化估计误差平方或
归一化创新平方。紧凑证据、中文复核和曲线位于
`docs/SCALABLE_3D_D1_COVARIANCE_MULTISEED_V3_SUMMARY_20260724.json`、
`docs/SCALABLE_3D_D1_COVARIANCE_MULTISEED_V3_REVIEW_CN.md` 和
`docs/figures/d1_covariance_limit_multiseed_v3_improvements.png`。原始 4.2 GB episode
仅作为临时复核材料，不提交到源码目录。

## 2026-07-24 D1 多 seed 与长时矩阵预注册历史

main 已冻结 `configs/d1_covariance_limit_multiseed_v1.json`。矩阵包含 seed
`1101-1110` 的 10 组 2.2 秒 short pair，以及 seeds `1101-1103` 的 3 组 10 秒 long
pair。每组均为 200 个目标、200 个资源、2 个侦察节点，并启用同一
`--d1-d2-structural-ambiguity-hold` 运行配置。reference 固定为 `7cc2d0c`，candidate
固定为 `95bf46e`。

`scripts/run_d1_covariance_limit_matrix.py` 顺序运行所有 arm，并在相邻 case 间交替
reference/candidate 先后次序。运行器拒绝提交不匹配或脏 worktree；每个 case 显式保存两条
命令、episode 目录、GNU `time -v` 资源记录、标准输出、标准错误和跨构建语义文件。生成的
`evidence_manifest.json` 直接记录 arm 标签和路径，后续 D6 不需要从目录名推断实验臂。
`--resume` 只复用提交、seed、时长、规模、运行配置、有限状态和真值隔离均通过的 episode。

预注册时只完成矩阵、运行器和 4 项单元测试，正式 13 组 pair 尚未运行。预注册门要求 short
组至少 8/10 更快、D1 fusion 均值改善至少 5% 且配对 bootstrap 区间上界低于 0；long 组
至少 2/3 更快且均值改善至少 5%；长短单位时间成本增长、核心墙钟和内存均有独立上界。
实时因子未达到 1 时，系统实时 P1 继续开放。

首次执行完成了 10/10 short pair 和 long seed 1101，11/11 跨构建审计通过。long seed
1102 的 reference 在主仿真和基础制品完成后，被 D6 严格 consumer 以
`D2 known-false-alarm exclusion count contradicts frame mappings` 阻断。D2 producer
报告 14 个仅虚警排除映射，持久化 frame 中实际只有 11 个；进程按合同以 1 退出，矩阵立即
停止。该批只作故障定位，不进入正式性能评估。

运行器随后在进程启动前持久化 running 状态，并在异常时写入 case、arm、异常类型和消息；
专项回归增至 5 项。D2 owner 修复计数口径后，main 将同一修复叠加到 reference/candidate
两端，以新的 clean 提交和新矩阵版本重跑，未混用已完成的旧提交 episode。

D2 修复现已提交为 `e4147b8`。真实 seed 1102 离线重放把
`known_false_alarm_only_mapping_count` 从 14 修正为 11，等于最终持久化排除映射数；其余
身份评估载荷不变。main 将同一提交分别叠加到原 reference/candidate，形成
`3c134c34655618b2e4d41302f9fbf3b6b4b78929` 和
`8c1188267c37c5e4a546abc8e7dd6c5a4bb48dba`。v2 矩阵位于
`configs/d1_covariance_limit_multiseed_v2.json`，保持全部 case、顺序和门限不变，
明确禁止复用 v1 episode。

上述 V1/V2 记录保留为阻断定位历史。正式准入以本页前述 PSD-safe V3 矩阵为准。

## 2026-07-24 D1 协方差成对限制单 seed clean 准入

D1 已把六维协方差 15 个非对角元素的逐项标量裁剪改为只读上三角索引上的批量裁剪。旧路径
通过 `vectorized_covariance_limit=False` 保留为 reference，默认使用优化路径。两条路径执行
相同的对角上下界、`0.999` 相关上界、对称化、非有限值重置和六秒 fixed-lag 重放；优化只减少
Python 层标量调用，不跳过预测、更新或重放。

main 使用 reference `7cc2d0cfd598a72d60c6ba8c7d4a283f4e5a897d` 与 candidate
`95bf46e34321127313757986bb28bfb14b7e3c59` 完成三轮交错 clean A/B。每轮均为
seed 1100、200 个目标、200 个资源、2 个侦察节点、2.2 秒和 2,035 条匿名观测。三轮配置
SHA-256 与运行配置 SHA-256 固定，六个进程均正常退出。跨构建审计确认规范在线载荷、真值
状态和标签、D3 计划谱系、ACK 来源及 D4 内容地址一致，在线真值使用为 0。

D1 融合累计墙钟均值由 `4.014714 s` 降至 `3.595533 s`，下降 `10.4411%`，三轮均改善；
单次调用 P95 均值由 `184.228658 ms` 降至 `173.330868 ms`，下降 `5.9154%`。核心墙钟下降
`3.1417%`，外部进程 elapsed 下降 `3.6310%`，最大常驻内存下降 `0.1429%`。D6 判定
`d1_optimization_admitted=true`。

候选实时因子均值为 `0.215065`。该早期批次只有单 seed 的三次短回放，也没有 AirSim、
均方根误差、归一化估计误差平方、归一化创新平方或严格身份指标。因此
`system_realtime_gap_closed=false`。完整复核见
`docs/SCALABLE_3D_D1_COVARIANCE_LIMIT_CLEAN_AB_REVIEW_CN.md`，D6 独立评估见
`../d6_evaluation_metrics/outputs/d1_covariance_limit_clean_pair_20260724/`。

## 2026-07-24 D1 共同质心原子影子

D1 新增单次同步原子入口。main 的默认关闭审计旁路不再把 prepared handle 暴露在三个公共
调用之间。一次调用完成规范准备、overlay 决策、可选 detached shadow、操作后完整性复核和
工作量统计。原子失败时丢弃 provisional shadow，并撤销本次 generation 状态推进。旧公共
接口保持可用，正式 D1 航迹、D2/D3 输入和 `global_track_id` 所有权没有变化。

D6 在原 runtime v1 主题中按执行模式区分历史 prepared-handle 和
`atomic_experimental_offline_v1`。atomic 记录必须完整携带准备摘要、后置完整性、canonical/
shadow 摘要、物化状态、工作量和失败原因；字段半缺或交叉关系矛盾时失败关闭。

clean `7cc2d0c` 的 seed 1100、200 对 200、2.2 秒 pair 产生 9 条 atomic 记录。9/9
post-integrity 通过，原子失败和 shadow 物化均为 0；46 条决策全部因 `oosm_scan` 拒绝。
去除审计主题并按业务相对序号规范化后，两臂各 3294 条业务记录、逐主题摘要、计划谱系、
ACK 来源和离线真值制品一致。

control/atomic-shadow 核心墙钟为 `10.735/19.450 s`，相对增加 `81.1799%`。完整影子阶段
mean/P95 为 `996.127/1536.429 ms`，没有通过 `+5%` 性能门。全拒绝时旧路径本就不执行
shadow assembly，原子入口没有消除规范准备、后置复核和禁止表面前后摘要。A2 保持默认
关闭，A3/A4 和 seeds `1101/1102` 继续停止。完整复核见
`docs/SCALABLE_3D_CENTROID_OVERLAY_A2_ATOMIC_REVIEW_CN.md`。

## 2026-07-23 D1 共同质心发布影子 A2

main 已把 D1 的实验准备对象接入默认关闭的审计旁路。规范航迹先生成不可变 prepared
handle，再由同一对象完成 overlay 评估和 detached shadow 装配；每次复用仍对完整规范载荷
执行强摘要复核。旁路只发布 `audit.d1.centroid_publication_overlay_shadow`，不替换
`latest_d1_tracks`，不进入 D2 或 D3。运行时分别记录禁止表面前摘要、准备、评估、装配、
禁止表面后摘要、影子摘要和日志物化耗时。模块栈与 scalable 3D 全量回归分别为
`43/168 passed`。

提交 `2b976a7213ccdaa35fe0e22dea88def2651e9467` 的 seed 1100 开发 pair 使用
200 对 200、2 个侦察节点和 2.2 秒。控制臂与影子臂最终 D1/D2/D3/D7 数量均为
`202/201/186/186`。过滤 9 条影子审计记录后，两端各 3294 条在线业务记录经计划谱系、
确认来源和序号偏移规范化后逐条一致；真值状态、离线标签和五米事件也一致。禁止表面修改、
全局编号变化、D2/D3 消费和在线真值使用均为 0。

旁路共评估 46 条证据，全部因 `oosm_scan` 拒绝，接受数为 0。控制/影子墙钟为
`10.7122/19.3765 s`，增量 `80.88%`；影子阶段 P95 为 `1533.00 ms`，未通过
`+5%` 门。主要平均成本来自 prepared 构造 `345.10 ms`、前摘要 `224.46 ms`、
后摘要 `207.31 ms` 和评估 `195.42 ms`。装配与日志物化不是瓶颈。

两个 manifest 均记录 `repository_dirty=true`，本轮只属于单 seed 开发复核。D6 判定
`overall_admitted=false`，阻断项为性能门失败、无接受样本和无结果效果证据。D1 共同质心
发布 A2 保持默认关闭；A3、A4 和 seeds `1101/1102` 不启动。完整结果见
`docs/SCALABLE_3D_CENTROID_OVERLAY_A2_PREPARED_REVIEW_CN.md` 和同名 JSON。

## 2026-07-23 身份承诺下游准入

main 已把 D2 的 `d2.identity-evidence-commitment.v2` 按 `global_track_id` 显式接入 D3。
D3 只接受 `committed`；歧义保持、保持后未承诺、字段缺失和未知状态都不进入可执行计划。
若现有计划中的目标被撤销承诺，main 在同一 D2 关联周期清除该目标的 D7 binding，设置强制
重规划标志，并在下一 D3 周期要求新计划严格升版。D5 主动视觉和 D7 导引还各自按当前承诺
集合再次过滤，旧计划不能在重规划间隙继续驱动相机或控制。

AirSim 经典二维 D2 尚不产生该 v2 侧车。AirSim main 因此在该可信中心跟踪器边界逐航迹生成
显式 `committed` 清单，并要求清单与适配航迹集合完全一致；直接调用适配器但不提供清单时，
状态为 `identity_commitment_missing`，D3 继续失败关闭。旧版 integrated point-mass 适配器也
显式标记其中心 D2 航迹来源，不再依赖 D3 的隐式默认值。

当前软件回归为 D1 `282 passed`、D2 `291 passed`、D3 `450 passed, 1 skipped`、
AirSim runtime `158 passed`、scalable 3D `157 passed`、integrated point-mass
`7 passed` 和跨模块合同 `7 passed`。AirSim 新增部分承诺清单拒绝负例；过时计划主动
注入继续由运行时回归覆盖。

detached clean `7e15dac9cdaf6743999dfe045a70676fd31a17d6` 已按相同
nominal 200 对 200、2.2 秒、2 个侦察节点和 seed 1100 重跑 hold 控制臂与
hold + 身份中性质心候选。t=1.0 秒时，D3 将计划从 v1/193 项强制升为
v2/186 项，11 个已分配但撤销承诺的目标全部退出新计划；该周期绕过迟滞。此后 D3、
D5 主动视觉、D5 终端绑定和 D7 对这 11 个目标的继续执行违规均为 0。两臂在线真值使用、
重复分配和未承诺绑定违规均为 0。

该复跑关闭 seed 1100 的下游合同验证，不晋级结构歧义算法。两臂的 D1/D2/D3、
严格 ID Switch、连续性和身份映射完全相同；质心候选 46 个组件中 0 个实际施加，
30 个因乱序量测扫描关闭，16 个因组件不平衡关闭。真实 AirSim 多 seed 的承诺侧车和
撤销时序仍为 P1。可复用审计入口为
`scripts/audit_identity_commitment_gate.py`，结果位于
`docs/SCALABLE_3D_IDENTITY_COMMITMENT_GATE_CLEAN_AB_20260723/`。

## 2026-07-23 当前优化 20-seed 校准

detached clean `5263e2b343dc4b96d239f77ef09437eb132f9efb` 已完成
seed `1000-1019`、nominal 200 对 200、10 秒规则全栈顺序运行。20/20 状态有限，
在线真值使用总数为 0，D1-D2 后验代次和 D6 schema/provenance 审计通过。候选与已有
`0d2da25` 同 seed 参考的 20/20 直接跨构建审计均通过，规范在线载荷、真值和计划/确认
语义一致。

核心墙钟均值由 `96.391 s` 降至 `86.099 s`，20/20 seed 均改善；配对变化均值为
`-10.63%`，95% seed bootstrap 区间为 `[-11.71%, -9.61%]`。实时倍率均值由
`0.1039` 提升到 `0.1163`，仍未达到实时。D1 扫描输入、D1 融合和 D2 关联分别下降
`22.06%/15.15%/6.41%`。严格 `id_switch_count` 在 20/20 seed 上继续为
unavailable。部分身份映射/完整帧/相邻转换覆盖为
`98.5760%/10.7404%/0.6118%`，19 个 episode 的保守下界合计 199；该值未回填 strict。
D1 RMSE/NEES 因同一 lineage mapping 缺口不可用。学习 bundle、正式七变体矩阵和五米
物理结果均不属于本轮证据。

完整结果见
`docs/SCALABLE_3D_LONG_DURATION_PERFORMANCE_CALIBRATION_CN.md`，机器摘要见
`docs/SCALABLE_3D_20SEED_PERFORMANCE_CALIBRATION_20260723.json`。

## 2026-07-23 后续热点复核

D1 已把扫描 claim 中重复的 JSON 规范化改为单次物化。冻结 seed 1000 的
771 个扫描、11,889 条观测上，旧/新 claim registry、逐次融合状态、协方差、
双时间戳、谱系和最终航迹严格一致；五轮交错 P50/P95 由
`3.618/4.049 s` 降至 `1.905/2.038 s`。该证据来自冻结输入，不代替新的
20-seed 全栈校准。

D2 对上述 20 个 clean episode 重放了离线身份 producer。严格 `id_switch_count`
仍为 unavailable：118 个航迹帧存在同一 `global_track_id` 对应多个真实目标，
形成 107 个多真值连续区间并涉及 83 个 episode/航迹组合；另有 2,464 个受评分
映射缺少显式真值、已知虚警或标签未知标记。D1 的 191,425 条可用估计中可形成
188,951 条唯一候选映射，剩余 2,474 条因 `truth_label_missing` 未解析，因此
20/20 episode 均未发布可消费的部分映射。在线 D2 关联器、门限和
`global_track_id` 均未修改。

D7 使用固定 200 pair、185 frame replay 对两个历史构建各运行 6 次。37,000 条
命令、世界加速度和最终 pair 状态严格相同，候选内核变化为 `+0.626%`，95%
bootstrap 区间为 `[-1.828%, +3.178%]`。该结果没有确认 D7 内核回归，因此
PN/PNG、LOS/TTC、切换门和调用频率保持不变。

main 对 3,430 条持久化在线载荷缓存真值守卫的重复键布局，同时继续逐次递归检查
嵌套值。四组同 seed、同配置、交错 clean 2.2 秒复测中，发布总线累计耗时中位数由
`0.887 s` 降至 `0.775 s`，下降 12.69%；核心墙钟中位数由
`10.824 s` 变为 `10.776 s`，只下降 0.44%，不能认定系统吞吐显著改善。
组合提交 `d79aba3` 的 clean smoke 状态有限、在线真值使用为 0、实时倍率为
`0.204`，跨构建 3,430 条规范在线记录和真值制品全部等价。

## 2026-07-23 离线三态与几何治理复测

D1 已修复冻结相机元数据的解析边界。扫描帧中的只读 `Mapping`、
`rotation_camera_from_ned` 和嵌套相机内参不再退回默认相机模型；非法外参、相机后方目标
和非有限投影失败关闭。冻结 seed 1000 的 771 个扫描和 11,889 条匿名观测中，D2 先前定位的
17 条视觉污染观测全部离开原错误航迹。该核验只在在线回放结束后使用离线标签，没有把真值
身份送入 D1。

main 离线真值合同升级为 `scalable3d-offline-truth-v2`。每条标签显式标记 `target`、
`known_false_alarm` 或 `unknown`；合成视觉虚警与在线量测一一生成，但处置类型仍只写入
离线 sidecar。D2 规范化为 `d2.scalable3d_observation_truth.v2`，已知虚警不进入严格身份
交换分母，未知或冲突标签继续阻断指标。D5 旧训练导出和保留 seed 身份桥只消费 `target`
标签。D6 三个消费入口分别报告三态数量，不从名称、距离或在线状态推断处置，也不回填严格
ID Switch。

detached clean 提交 `488dc39` 包括三组 2.2 秒和一组 10 秒 nominal 200 对 200。四组状态有限，
在线禁用身份字段命中和 `online_truth_use_count` 均为 0。三组短回放共生成 7,098 条目标
标签和 312 条已知虚警标签，缺失身份映射均为 0；seed 1001 的严格 ID Switch 可用且为 9，
seed 1000、1002 各有 2 个雷达多真值映射。10 秒 seed 1000 生成 10,829 条目标标签和
402 条已知虚警标签，剩余 7 个多真值映射，分布在 6 帧和 6 条航迹；来源均为雷达谱系。
严格指标因此继续保持 unavailable，部分下界 49 只用于诊断。

四个 episode 的 manifest 均为 `repository_dirty=false`。该批属于 clean 描述性校准，
尚不是 formal acceptance；它证明标签缺失已从新 producer 消失，并把剩余身份阻断收敛到
雷达扫描间关联。该批机器摘要见
`docs/SCALABLE_3D_IDENTITY_DISPOSITION_RECALIBRATION_20260723.json`，后续雷达候选评审见
下一节。

## 2026-07-23 雷达交替环候选评审

main 对 baseline `488dc39` 和 D1 v1 candidate `d967c96` 完成同配置 clean A/B。设置固定为
nominal 200 对 200、2.2 秒、`recon_count=2`、seeds 1000/1001/1002，各 seed 的配置哈希
在两端相同。候选把 ambiguous mapping 从 `2/0/2` 降到 `0/0/0`，严格身份指标可用 seed
由 `1/3` 增至 `3/3`。代价是 D2 航迹数由 `201/202/200` 降至 `200/194/197`，D3 分配数由
`200/200/200` 降至 `198/190/193`；seed 1001 的 continuity 由 `0.869444` 降至
`0.814444`。候选还抑制 `22/130/78` 条雷达观测，占各 seed 雷达量测的
`1.12%/6.61%/3.98%`。

v1 因航迹、分配和连续性退化不晋级，默认在线路径保持原 Hungarian。提交 `8f17c5d` 将
候选改为默认关闭后，同配置三 seed 的全部业务指标恢复 baseline；跨构建审计
`3/3 passed=True` 且规范在线载荷 `3/3` 相等。早先使用 8 架侦察机的结果只保留为
stress 诊断，不能与本次 `recon_count=2` A/B 比较。该诊断揭示 v1 尚未覆盖最大匹配图中的
free-row 和 free-column 交替路径，雷达量测也没有可用于消歧的真实径向速度。

严格身份 P1 继续开放。下一候选必须同时覆盖交替环、free-row 和 free-column 路径，并联合
验收身份可用性、D1/D2 航迹、D3 分配、连续性、抑制率、birth 和 recall。在新的短时 clean
候选通过前，不运行被拒绝 v1 的 10 秒或 20-seed 批次。机器摘要见
`docs/SCALABLE_3D_RADAR_ASSIGNMENT_CANDIDATE_REVIEW_20260723.json`。

main 运行时现提供显式
`--d1-radar-assignment-ambiguity-governance-v2` 实验开关。默认不传入时保持关闭；启用后，
`summary.json` 和 `observation_governance_audit.json` 会记录 D1 的
`selected_policy_version`、enabled/status 及抑制诊断。兼容字段
`policy_version` 不能单独用于判断实际启用策略。`manifest.json` 另存完整
`scalable3d-integrated-stack-runtime-profile-v1` 和 SHA-256，episode ID 同时携带该哈希前缀，
因此相同场景的基线与 treatment 不会共用身份。该接线允许同一代码提交分别运行规则基线和
实验候选，不再通过修改模块默认值制造 A/B。

detached clean `c928727` 已用未见 seed 1100 运行首个 200 对 200、2.2 秒、
`recon_count=2` 同构建门槛。v2 的身份交换保持 `9`，航迹连续性由 `0.865` 降至
`0.830`，D2 航迹由 `203` 降至 `199`，D3 分配由 `200` 降至 `196`；77 条雷达观测被抑制。
候选没有身份收益且下游可用性下降，因此按预注册门槛停止剩余短 seed、10 秒和 20-seed。
v2 保持默认关闭。评审见
`docs/SCALABLE_3D_RADAR_ASSIGNMENT_V2_CLEAN_AB_REVIEW_CN.md`，机器摘要见
`docs/SCALABLE_3D_RADAR_ASSIGNMENT_V2_CLEAN_AB_REVIEW_20260723.json`。

## 2026-07-23 D1-D2 结构歧义保活复核

D1 和 D2 的默认关闭候选链路现已增加显式身份承诺合同。D1 仍只发布带双时间戳、NED
六维状态、协方差和完整允许边的结构歧义侧车。D2 在租约期间发布
`identity_uncommitted_ambiguity_hold`，租约结束但没有新原始证据时发布
`identity_uncommitted_after_hold`。这两类记录不携带来源观测，也不进入 D3 当前分配
窗口。只有不同、更新且首次接受的原始证据可恢复 `committed`。main 对普通已承诺航迹
保留窗口内 D1 谱系；经历歧义恢复的航迹只发布本次被接受量测的精确谱系。D6 使用 v2
证据独立重算承诺覆盖、恢复水位和绑定违规，不回填严格身份指标。

发布新鲜度门已加入 D2 恢复承诺。量测必须晚于 hold 水位，并且
`D2 帧时刻 - measurement_timestamp <= 0.9 s`。超龄证据保持未承诺，等待更新的原始
观测。完整恢复配置由每条 D2 发布携带；离线身份清单升级为
`scalable3d-offline-identity-evaluation-manifest-v2`，绑定本 episode 的规范配置快照、
配置 SHA-256 和记录数。D6 同时验证清单、在线 D2 JSONL 和逐发布配置，历史 v1 清单保持
只读兼容。

detached clean `ff881316243ff5a2991a4659ab78637ed625d123` 使用相同 nominal 200 对 200、
2.2 秒、`recon_count=2` 和 seed 1100 完成最终同构建 A/B。候选形成
`1711/69/7` 条 committed/hold/after-hold 记录；其中 3 条超龄恢复证据被新鲜度门阻断。
严格 ID Switch 由 `9` 降至 `3`，重复分配保持为 0，未承诺来源和候选绑定违规为 0。
两组清单均绑定 9 条 D2 发布，D6 episode 与 runtime provenance 均验证通过。

候选仍未通过准入。D2 航迹由 `203` 降至 `201`，D3 分配由 `200` 降至 `197`，可用
身份映射由 `1566` 降至 `1491`，航迹连续性由 `0.865` 降至 `0.826667`，覆盖连续性由
`0.870` 降至 `0.828333`。seeds 1101/1102、10 秒和 20-seed 按停止规则不执行，默认
路径不变。配置谱系缺口已关闭；结构歧义保活的算法准入仍是 P1。
完整评审见
`docs/SCALABLE_3D_STRUCTURAL_AMBIGUITY_HOLD_CLEAN_AB_REVIEW_CN.md`，机器摘要见
`docs/SCALABLE_3D_STRUCTURAL_AMBIGUITY_HOLD_CLEAN_AB_REVIEW_20260723.json`。

## 2026-07-23 身份中性质心校正开发门槛

main 已接入两个默认关闭的独立运行开关：
`--d1-publish-opaque-source-key` 用于来源键控制臂，
`--d1-identity-neutral-centroid-correction` 用于结构歧义 hold 下的质心状态校正。
后者必须与 `--d1-d2-structural-ambiguity-hold` 同时启用。D1 对连续 generation
采用帧替换语义：每帧从正式观测历史重放到发布时间，再施加一次身份中性的平移和
协方差膨胀，不累计上一帧临时修正。

早期未提交工作树完成 seed 1100 开发门槛，固定提交 `7e15dac` 随后完成同输入 clean
复验。两臂均为 nominal 200 对 200、2 个侦察节点和 2.2 秒；控制臂启用 source-key 与
hold，候选臂只增加质心校正。
两臂的 D1/D2/D3 数量均为 `202/201/186`，严格 ID Switch 均为 `3`，
track/coverage continuity 均为 `0.826667/0.828333`，最终有效映射均为 `191`，
未承诺绑定违规均为 `0`。

候选审计记录 46 个组件，实际施加为 `0`。其中 30 个因 `oosm_scan` 失败关闭，
16 个因 `unbalanced_component` 失败关闭。该次运行没有形成有效 treatment，不能证明
质心校正改善或恶化系统，也没有恢复结构歧义 hold 的航迹和分配可用性。按门槛停止
seeds 1101/1102；候选保持默认关闭，P1 继续开放。早期开发制品为
`repository_dirty=true`，只作为开发诊断；固定提交的 clean 同输入复验见
`docs/SCALABLE_3D_IDENTITY_COMMITMENT_GATE_CLEAN_AB_20260723/`。开发门槛详情见
`docs/SCALABLE_3D_NEUTRAL_CENTROID_DEV_GATE_CN.md`。

## 2026-07-23 共同质心冻结扫描边界诊断

D1 已在模块内复用 governed replay、扫描组织器和在线批融合入口，构造三类冻结扫描做
hold-only/共同质心候选对照。同步平衡纯交替环的成员/观测为 `2/2`，实际施加一次模长
`15.000000 m` 的共同平移；速度、相对位置、hit、谱系、身份和规范航迹编号不变，候选减
控制臂协方差差的最小特征值为 `0.4797678`。乱序平衡分量以 `oosm_scan` 拒绝，成员/观测
`2/1` 的数量不平衡分量以 `unbalanced_component` 拒绝。双时间戳、NED、协方差和身份门
没有放宽。

拒绝场景的共同质心公式没有输出，`applied_component_count=0`。候选路径仍会执行一次
publication-base replay + replace，以清除可能存在的旧临时修正。当前离散匀速过程噪声在
单段重放和分段预测下不满足半群等价，因此候选减控制臂协方差差的最小特征值分别为
`-0.0071928353214153066` 和 `-0.004617076466238031`。D1 诊断已逐位确认最终差值来自该
替换路径，不能把拒绝场景表述为状态和协方差严格无副作用。

专项与 D1 全量分别为 `5/287 passed`。该证据只关闭“受控合法输入能否形成非零施加窗口”
的边界问题。它没有证明真实匿名 200 对 200 输入会自然出现该窗口，也没有证明连续性、
状态误差或下游可用性收益。候选继续默认关闭，晋级边界为 `candidate_not_promoted`；
seeds 1101/1102 继续停止。机器证据和中文报告位于
`../d1_sensor_fusion/reports/structural_ambiguity_centroid_replay_20260723/`。

下一候选的设计决策已经冻结，但尚未实现。D1 先做 detached publication overlay 最小原型：
规范滤波状态、协方差、观测历史、检查点和重放缓存保持不动；候选接受时只改一次发布 DTO，
拒绝时直接使用规范快照，并要求业务发布与 control byte-identical。固定滞后 OOSM 共同质心
事件暂缓，直至事件排序、过程噪声分段和一致性 oracle 单独冻结。D1 结构证据由 D2 概率或
多假设层消费的路线保留为主要系统研究方向，由 D2 owner 另行规划。完整设计见
`../d1_sensor_fusion/docs/STRUCTURAL_AMBIGUITY_NEXT_CANDIDATE_DESIGN_CN.md`。

## 2026-07-22 规则全栈性能校准

提交 `33101656b0cf1967a778cdb36a440611e02109b1` 已完成 20、50、100、200 四档 clean-source
校准，每档 seed 42000-42004，共 20 个 2.2 秒 episode。20/20 状态有限，在线真值使用为 0。
平均实时倍率依次为 `1.504/0.540/0.240/0.092`。20 对 20 达到实时，200 对 200 平均墙钟
23.969 秒，仍未达到实时。

200 规模 D1 融合、D2 常规关联和 D3 分配的平均累计时间分别为 `10.275/2.037/0.665 s`，
D2 尾部收束为 `0.640 s`。相对上一轮同配置 clean 批次，200 规模平均墙钟下降 26.7%。
D1 仍是首要热点，下一轮优先处理创新求解、数值雅可比和发布物化，再处理 main 结束收束与
发布序列化。本批没有正式实验矩阵元数据，D6 将其归类为干净来源的
描述性校准，不是 formal acceptance，也不证明融合精度、AirSim 或物理拦截。

完整条件、逐规模表、同 seed 开发对照和制品哈希见
`docs/SCALABLE_3D_RULE_PERFORMANCE_CALIBRATION_CN.md`。

## 2026-07-22 长时性能对照工具

`long_duration_performance.py` 和
`scripts/compare_long_duration_episodes.py` 用于比较同一 clean 提交、同一 seed、仅仿真
时长不同的两个 episode。工具只读取 manifest、场景配置、summary、阶段耗时和可选的
`/usr/bin/time -v` 资源记录，不扫描大体积在线 JSONL 内容。

对照结果包含总墙钟、实时倍率、峰值驻留内存、在线日志速率、D1/D2 治理状态、计划确认
以及各阶段的单位仿真时间增长、调用密度增长和单次调用成本增长。比较前强制核对提交号、
场景版本、seed、目标/资源/侦察节点数量及去除时长后的配置摘要，避免把不同来源 episode
混为同一性能样本。

```bash
python3 research_modules/scalable_3d_simulation/scripts/compare_long_duration_episodes.py \
  --short-episode <2.2-second-episode> \
  --long-episode <10-second-episode> \
  --output-dir <comparison-output>
```

提交 `c0460e0` 的 seed 42000 基线显示，2.2 秒与 10 秒运行的单位仿真时间墙钟由
`9.868 s` 增至 `26.329 s`，归一化增长 `2.668x`；峰值驻留内存由 `1.054 GiB` 增至
`3.154 GiB`。D1 fusion 和 D2 association 的单次调用成本分别增长约 `2.107x` 和
`3.467x`。该结果只用于定位长时历史增长。

模块优化后的 detached clean 提交 `3bac3ff` 已复跑相同 pair，并由 D6 独立消费。2.2 秒与
10 秒核心墙钟为 `18.611/172.214 s`，10 秒相对旧基线下降 34.6%；实时倍率为
`0.118/0.058`。候选长短单位时间成本增长为 `2.036x`，峰值驻留内存为
`1.002/2.981 GiB`。D1/D2/D3/D5/D7 最终规范输出和 201 帧三维世界状态均与旧基线一致，
在线真值使用和 D1/D2 overflow 为 0，最终中心身份集合未发生变化。

该结果证明当前模块优化有效，但 200 对 200 仍未实时，长时内存和发布量仍明显增长。D1 10 秒
融合为 103.176 秒，D5 终端配准单次成本增长 2.696 倍，在线日志仍为 296.336 MiB。详细条件、
阶段耗时、语义哈希和后续边界见
`docs/SCALABLE_3D_LONG_DURATION_PERFORMANCE_CALIBRATION_CN.md`。

同一 clean 提交随后完成 seed 42001、42002 的 10 秒运行。三 seed 核心墙钟均值为
172.097 秒，实时倍率均值 0.0581，峰值驻留内存均值 3.055 GiB；D1/D2/D3/D5 阶段均值为
103.339/8.203/3.348/2.699 秒。3/3 状态有限、在线真值为 0、D1/D2 overflow 为 0，3/3
没有五米接近事件。该批继续属于描述性性能校准，不是拦截效果或学习算法验收。

## 2026-07-22 发布边界与冻结热点复测

detached clean 提交 `8f8619246298bdce34fabb7c7199bc282487bd45` 完成相同 seed 42000
的 2.2/10 秒对照，以及 seeds 42000-42002 的三组 10 秒运行。D1 对每个扫描继续执行状态
更新并保留一条发布；同一融合时刻内只有最后一个后验构造完整航迹数组，其余发布携带空的
`tracks`、`track_count=0`、真实 `current_track_count`、扫描摘要和观测谱系。旧 schema 对
`track_count == len(tracks)` 的约束保持成立。

三组 10 秒核心墙钟均值为 155.895 秒，实时倍率均值 0.0642，峰值驻留内存均值
2.889 GiB。相对上一候选，三项变化分别为 -9.4%、+10.4% 和 -5.4%。D1 融合均值由
103.339 秒降至 92.991 秒；模块发布总线均值由 7.574 秒降至 6.211 秒；文件系统写出块
均值下降 23.4%。state-only/full 快照数量分别为 `310/454`、`328/516` 和 `278/504`。

seed 42000 的长短单位仿真时间成本增长由 2.036 倍降至 1.830 倍，在线日志增长由
1.436 倍降至 1.249 倍。D5 终端配准单次调用成本增长由 2.696 倍降至 2.423 倍，但仍为
开放 P1。D3 三 seed 累计时间由 3.348 秒变为 3.289 秒，按基本持平处理，不据此修改代价、
迟滞或求解主线。

3/3 episode 均为 clean、有限状态、在线真值使用为 0，D1/D2 overflow 为 0。场景配置、
离线真值标签、三维真值数组、接近事件、扫描事件和既有业务摘要与上一候选相同。D6 将三组
结果归类为 `descriptive_clean_source_calibration`；该证据不关闭实时性、物理拦截、AirSim
或学习模型准入。详细结果见
`docs/SCALABLE_3D_LONG_DURATION_PERFORMANCE_CALIBRATION_CN.md`。

## 2026-07-22 创新求解治理与跨构建审计

clean 候选提交 `f80b5bd42e2c1beb707fd68bfb820d9607c80df3` 使用与 `8f86192` 相同的
200 对 200 名义场景、10 秒时长和 seeds 42000-42002。三 seed 核心墙钟均值由
155.895 秒降至 150.875 秒，下降 3.22%；进程总耗时均值由 222.780 秒降至
195.363 秒，峰值驻留内存均值由 2.889 GiB 降至 2.359 GiB。D1 实际创新方程求解次数由
7,130,228 次降至 1,578,677 次，下降 77.86%。D1 融合、D2 关联和 D5 终端关联均值分别为
88.330、7.671 和 1.974 秒。D3 与 D7 均略有增长，按单机描述性波动处理，不改变规则代价、
迟滞或比例导引算法。

`cross_build_equivalence.py` 对两个独立 clean build 的同 seed 制品执行流式语义审计。工具
先验证 D3/D7 原始来源载荷的 SHA-256，再按首次发布顺序映射 D3 不透明计划编号。D4 的
authority digest、正式裁决 digest 和 advisory ID 不按事件号删除或替换；审计先验证原始
内容地址，再用规范化计划谱系重新计算。owner、版本、epoch、lease、区域、资源、目标、
联盟、动作和下游引用仍逐条比较。三个 seed 均通过在线记录数、主题计数、逐主题规范哈希、
真值数组、离线标签、接近事件和 summary 合同检查。

提交 `12c5073` 已为 D1 posterior 跨 D2 调度周期的漏消费建立新的行为基线。main 只锁存
尚未消费的真实后验，并在下一关联 tick 交给 D2；不把航迹时间改为控制时刻，也不放宽
D7 的 `max_track_age_s`。seed 42000 的两次 clean 10 秒运行通过逐主题载荷、计划谱系、
真值数组和摘要合同的同提交语义等价审计，核心墙钟为 `107.853/122.032 s`，波动约 13%。

该修复有意改变旧的漏消费行为。`f80b5bd` 在 `1.00 s` 仍以旧 D2 后验形成 197 条分配，
`12c5073` 在同一时刻消费待处理后验并形成 200 条分配，控制状态从下一积分步开始分叉；
两者不能再要求跨提交业务等价。main 随后在 `b681c8f` 增加后验代次、D2 消费代次、
节拍前合并计数和结束排空回归，观测治理快照升级为
`scalable3d-observation-governance-runtime-v2`。新代次字段不改 D1/D2 算法、量测时间或
协方差，只提供可回放的消费血缘。

detached clean 提交 `0d2da25c14e50f8f9a10ad47a7bd74e5c5e577fb` 已完成新的三 seed
10 秒基线。seed `42000/42001/42002` 的核心墙钟为 `96.787/103.472/103.633 s`，均值
`101.298 s`；实时倍率均值为 `0.0988`。D1 融合、D1 扫描输入、D2 关联、D3 分配、D5
终端配准和 D7 导引累计时间均值分别为 `55.275/12.743/5.679/2.455/1.247/3.981 s`。
该批建立当前行为和性能基线，仍未达到实时目标。

三次 D1 最终代次为 `453/516/505`，完整后验发布数与之逐项相等；D2 最终消费代次逐项
追平 D1，D2 发布/消费均为 48 次，节拍前合并数为 `405/468/457`，结束时 pending 均为空。
D6 v6 被动评估将 3/3 判为 generation integrity 通过，failure reason 为空，在线真值使用
为 0。seed 42000 同提交重复运行通过全量语义等价审计，核心墙钟为 `96.787/96.704 s`。
与 `12c5073` 的 811 处在线差异全部来自新增的 D1/D2 代次字段；summary 合同、真值、计划
谱系和其余载荷一致。该批仍是三 seed 描述性 clean 校准，不是 20 个未见 seed 或正式实验
矩阵验收。

同一 detached clean 提交随后顺序完成 seed `1000-1019` 的 20 组 nominal 200 对 200、
10 秒规则全栈。20/20 进程退出为 0、状态有限、在线真值使用为 0、分配保持为 0；D1 完整
后验代次从 `410` 到 `499`，D2 最终消费逐组追平 D1，消费次数与节拍前合并次数之和逐组
等于 D1 代次，pending 均为空。核心墙钟均值/范围为 `96.391/88.035-102.573 s`，实时倍率
均值/范围为 `0.1039/0.0975-0.1136`，仍未达到实时目标。D1 融合、扫描输入、D2 关联、
D3 分配、D5 终端配准和 D7 导引均值为 `51.649/12.418/5.492/2.448/1.185/3.638 s`。

D6 v6 对 20/20 给出基础 clean provenance 可用、generation integrity=true、failure reason
为空。D3 计划覆盖率均值为 `0.989606`，2000 次 seed bootstrap 95% 区间为
`[0.987144, 0.991813]`；D5 最终 binding 数均值/范围为 `25.95/9-41`。该批没有五米接近，
学习 bundle 未加载，且 episode 未声明实验矩阵 metadata，因此全部只能归类为
`descriptive_clean_source_calibration`。它不是正式 R0/G1/A1/A2/A3/C1/F1 算法比较，也不
证明物理拦截或学习策略采用。

后续诊断代码将 `stage_timings.csv` 升级为
`scalable3d-stage-timings-v2`。每个阶段除总耗时、调用次数和均值外，新增单次调用
`P50/P95/max` 及 availability；缺少调用样本时保留空值和原因，不回填为 0。模块内分布
只在 episode 收束时计算，在线 step 不执行重复分位计算。
5v5、1.2 秒、seed 41 冒烟验证了新列、有限状态和在线真值使用为 0；该冒烟只验证记录
合同。长时对照输出同步升级为 `scalable3d-long-duration-comparison-v2`，可读取无分位列的
历史 CSV，但将其明确标为 unavailable。200 对 200 的稳定窗口分布仍需在下一 clean 候选上
重新测量。

detached clean `4ac3bb2` 已完成 nominal 200 对 200、seed 1000 的 2.2 秒与 10 秒同源
校准。10 秒核心墙钟为 `85.002 s`，实时倍率为 `0.1176`；相对 `0d2da25` 同 seed 的
`94.105 s` 下降 `9.67%`。D1 融合从 `49.697 s` 降至 `40.273 s`，下降 `18.96%`；
D1 扫描输入从 `12.315 s` 增至 `12.561 s`。跨构建审计确认 21,366 条在线记录的规范载荷、
真值状态、计划谱系和运行确认一致。该结果证明优化没有改变当前规则基线业务语义，但仍是
单 seed 描述性校准。

10 秒 episode 的 D1 融合单次调用 `P50/P95/max` 为
`33.252/224.764/592.957 ms`，D2 关联为 `121.972/137.335/145.966 ms`。2.2 秒与 10 秒
长短对照安全合同全部通过，但 D1 融合、D2 关联和 D5 终端配准的单次成本仍随 episode
展开增长。外部进程总时长为 `1:55.95`，峰值驻留内存为 `2,468,928 KiB`；这两个值与
`summary.wall_time_s` 分栏解释。D6 v7 对该 episode 的离线消费耗时为 `10.24 s`、峰值
驻留内存为 `936,056 KiB`。正式七变体矩阵仍为 0 episode，实时性和多 seed 尾延时 P1
继续开放。

原始 episode 约 1.1 GiB，继续按生成物规则保存在忽略目录，不提交 Git。仓库内的紧凑证据
摘要为 `docs/SCALABLE_3D_STAGE_TIMING_CALIBRATION_20260722.json`，记录两端 clean
提交、场景配置哈希、manifest/summary/online 产物哈希、跨构建审计哈希、阶段分位和验收
边界。报告结论不依赖临时目录路径本身。

D1 使用该 seed 1000 冻结输入完成 scan-input 尾延时专项。771 个已校验
`SensorScanFrame` 在快照完整时直接复用，检测到对象、标量或数组可写状态变化时回退原有
完整快照和 fail-closed 校验。帧重建由 771 次降至 0，organizer 内 observation 再快照由
11,889 次降至 0。前 256 个扫描交错 5 轮的 P50/P95 由
`1.942/1.968 s` 降至 `0.881/0.894 s`，P50 描述性加速 `2.204x`；
`ScanInputOrganizer.ingest` cProfile 累计由 `15.545 s` 降至 `5.754 s`。

逐输入结果、审计、释放顺序、融合状态与协方差、双时间戳、谱系、分级、物化航迹、
终态及操作数共 14 项等价条件全部通过，在线 truth 使用为 0。机器报告 SHA-256 为
`9510bd60b862be98a3816f238cd27c08c942e501e9dec27b96d598c45dc2d1df`。
该专项运行来自当前未提交 D1 工作区，只关闭重复快照热点；clean full-stack、多 seed、
AirSim、实时性和融合 P95/max 仍未验收。

D6 更新后的真值隔离入口已实际复读同一 seed 1000 身份制品。严格 ID Switch 仍为
unavailable；部分诊断在来源 SHA 和 identity manifest 校验通过后给出映射/帧/相邻转移覆盖率
`98.54%/6.25%/0%`、385 个锚点区间和保守下界 7。报告明确
`strict_id_switch_count_backfilled=false`、`id_switch_upper_bound_reported=false`。该结果只关闭
单 seed partial consumer 接线。D6 当前全量回归为 `567 passed, 1 warning`；新增 12 项包含
3 项独立合同测试和 9 项来源篡改参数化测试。

D2 随后在同一 seed 1000 冻结总线上完成 profiler v2 和语义等价热点优化。48/48 周期
公开输出、完整 tracker 状态及重复语义哈希一致；输入、fresh、replay quarantine、候选边和
匹配数保持 `9626/9038/588/8862/8823`。D2 core 中位数由 `2.928830 s` 降至
`2.204672 s`，描述性加速 `1.328465x`。优化消除了相同 `dt` 的 9,200 次重复常速度矩阵
构造、19,252 次可信 marginal 冗余比较和每帧一次重复 ledger 全量汇总。`global_track_id`、
ID Switch availability、门控、版本、claim ledger 和在线 truth 隔离语义均未变化。

该回放不构成实时验收。候选早晚 regular 窗口比为 `1.123036x`，与基线
`1.119661x` 基本相同；绝对常数成本下降，长窗口增长没有改善。报告固定在
`research_modules/d2_data_association/docs/d2_clean_4ac3bb2_seed1000_hotpath_20260723.json`，
SHA-256 为 `2256d6fdd29223ed5dd75351cd6bb208a4d67c55925eeba047620ac865b6c7da`。

D5 使用同一 seed 1000 的 25 帧短序列和 114 帧长序列完成热点归因。增量 history gauge
在长序列 723 次刷新中避免扫描 91,871 个 tracker 引用；2,289 个 singleton cluster
直接复用投影距离行，79 个多节点 cluster 保留完整有限性聚合；匿名 payload 内建叶子
快路径和 8,192 项有界 local-ID 缓存保持原 truth 审计与正则规则。pre-boundary-fix
cProfile 中 `process()` 累计由 `2.320 s` 降至 `1.987 s`，两轮 A/B 中位值均值由
`1.149 s` 降至 `0.929 s`。这些墙钟只用于方向归因。

最终源码另行修复了 singleton 行复用的 `-0.0` 符号位边界。修复后冻结短/长重放的业务、
最终 binding 和冻结 v1 操作数哈希均与原发布记录一致；在线 truth 使用和
`global_track_id` 改写均为 0。当前 D5 全量为 `551 passed`。机器报告明确区分 pre-fix
profiler 与 post-fix 语义验证，SHA-256 为
`7be68d15a982f720355e30b631cf44b860a5b017a6b4221819d9c9c08b26c449`。
长序列中 tracker pair、投影矩阵和绑定矩阵仍随输入组成显著增长；完整集成、多 seed、
AirSim 和固定硬件实时性 P1 保持开放。

## 2026-07-21 正式数据与开发训练状态

修复逐 episode checkpoint 和 D5 同流多批次边界后，新的正式生成目录已经完成全部
900 episode。数据覆盖 9 类场景、5 档规模和 100 个训练 seed，每个场景/规模 cell 为
20 episode；seed `1000-1019` 保留给最终验收。episode index 连续且唯一，在线真值字段
使用总数为 0，来源提交为干净的 `39b097e72487567ac915c2297eaa27eed49ef76b`。正式数据约
2.03 GB，未因后续标签或训练工作原地改写。

D3 已在完整数据上完成行为克隆开发训练，内部测试边排序一致性为 `0.803085`，计划完全
一致率为 `0.677019`，推理 P95 为 `2.554 ms`；bundle 保持 `development/shadow-only`，
未启动近端策略优化。D4 行为克隆内部测试 loss 为 `0.071545`、推理 P95 为 `0.7774 ms`，
但 14384 个区域动作没有非零 quota、hold、replan 或 transfer，因而同样不能进入 assist，
近端策略优化不可用。D5 正式跨视角图共有 12851 个图帧，其中 97.52% 没有候选边，负边
只有 19 条；原开发模型的高 F1 来自极弱的负样本分母，不能晋级。D5 已在独立 clean
补充课程中生成 4500 帧和 245032 条默认几何门候选边，正/负/未标注为
`57292/187740/0`，数据支持与训练数据来源门已通过。D5 后续已完成 clean composite 模型
训练和 seed `1000-1019` 的 paired shadow v2，覆盖 45 个场景规模单元、900 帧、13344 个
匿名节点和 74024 条候选边。冻结图模型边/簇 F1 为 1.0，但尺度差、尺度变化率差和角速度差
的单特征最佳方向曲线下面积约为 0.9973，说明合成保留集接近确定性可分。该结果不能代表真实
跨视角泛化；G1、assist 和 authority 仍关闭，等待 D6 独立审计与更困难的独立扰动数据。

D4 已另建不修改正式 900 episode 的区域动作覆盖课程。clean commit `9445ed6` 生成
100 个 seed、100 个 episode 和 300 帧，覆盖 hold 100、request_replan 200、非零配额
200 和跨区转移 100；硬约束、在线真值和保留 seed 泄漏均为 0。课程已具备 canonical
60/20/20 行为克隆只读视图，但没有可归因 outcome/reward，PPO、assist 和在线 authority
继续关闭。

D5 已另建主动视觉补充规则课程。clean commit `13e3728` 生成 100 episode、800 segment
和 1200 sample，覆盖 hold/observe-target/reacquire/search-sector=`200/600/200/200`、
wide/zoom=`1000/200`，拦截与侦察相机各 600 条。applied/rejected/missing 各 400 是确定性
故障注入覆盖，不是真实运行 ACK；reward、outcome、counterfactual 和 causal 标签均为
`0/1200 available`，PPO、assist 和相机权限继续关闭。

D5 已对该补充课程完成只读全样本审计。100 个 episode、1200 个样本、302 个受清单约束的
文件全部通过；1200 个样本的 35 维候选特征均为有限值，规范 episode/sample 切分为
`60/20/20` 和 `720/240/240`，在线真值、保留 seed 泄漏、dirty episode 和身份改写均为 0。
审计文件和内容 SHA-256 分别为
`9a03653538e6dae054da8c127ad4a20aae2481af6c9bbef987edfddff0b423d3` 和
`a11b65596a4c416deba6d0cb35dcc0c32342a5bae0481291d43e8de0e26550dd`。

D5 主动视觉已在 1,153,242 个规则示范样本上完成五轮完整行为克隆。测试精确动作准确率
为 `0.955978`，CPU 推理 P95 为 `0.1203 ms`，但 `reacquire` 占 92.16%，4,051 个
`observe_target` 测试样本的召回率为 0，hold 没有正样本，侦察相机精确动作准确率为
`0.621823`。该 bundle 只允许 shadow 加载，assist 和 PPO 均失败关闭。

D6 对正式数据生成了源外标签 sidecar，并完成 D3、D4、D5 producer 的全样本结构审计。
D3 覆盖 900 episode/1604 frame、3,658,815 条候选边和 117,304 条选择边；D4 覆盖正式
900 episode/1798 frame 及补充 100 episode/300 frame；D5 主动视觉补充覆盖 100 episode/
1200 sample/302 个制品。三类 producer 全样本状态均为 complete，联合报告 JSON/中文
Markdown SHA-256 分别为
`6593ee8a11d33b7c75d633f87e0fbd84cea421798bab0920ef4117cb044a87f5` 和
`7b6480d08870cbf21f532235ddfdbe9ca7f23ce05f681f2d18846f988355a4ba`。总体准入仍为 partial：
D4 只有 `898/1798` 帧具备无动作归因的相邻状态结果，D5 主动视觉虽有大量相邻观测结果，
但两者可归因 reward 均为 0；正式数据也没有新的 runtime ACK、paired shadow 和保留 seed
性能。D5 正式图的 99 条未标注边因缺少精确 lineage 保持 unavailable，clean 补充图数据尚未
训练模型。在正式 reward、同 seed 对照和学习实际采用证据闭合前，不能开展 PPO、在线辅助或
因果训练。

D6 还已在真实 main 3v3 质点 episode 上完成运行时计划确认与离线结果联接。2 条确认被识别
为 1 条新计划身份和 1 条同身份评估刷新，共形成 6 个资源-航迹窗口；来源序号、载荷哈希、
D2 身份映射和离线三维状态均通过校验，在线真值使用为 0。所有窗口具备有界距离进展诊断，
但当前没有同 seed 配对影子、保留 seed 结果、正式强化学习奖励或因果证据，因此 PPO、assist
和 authority 仍为 false，规则回退保持启用。

跨模块切分现由 detached `scalable3d-shared-seed-split-registry-v1` 统一管理。100 个训练
seed 固定为 `60/20/20`，映射与现有 D3 正式开发数据逐项一致，保留 seed 未进入任一桶。
原 D4、D5 manifest 仍保留各自历史切分；源外 canonical views 已形成，并通过 D6 的
manifest/view/readiness/summary 层一致性审计。D5 补充课程进一步通过 D6 的全样本证据消费，
但 D3、D4 仍停留在清单层。C1 联合训练继续关闭，原因已从 seed 切分不一致转为 D3/D4
全样本审计、真实动作采用/ACK、reward/outcome 和 paired shadow 缺失。
生成命令为：

```bash
python3 research_modules/scalable_3d_simulation/run_shared_seed_split.py \
  <formal-output>/training_seed_registry.json \
  <formal-output>/shared_seed_split_registry_v1/registry.json
```

main 已增加可选侦察观察线索，把 D3 当前计划中已有的 `global_track_id` 作为 D5 观察任务
送给侦察相机。它不改变 D3 分配，也不读取真值。2026-07-21 的 5v5、3 秒、seed 70-74
同 seed 对照中，启用线索后平均视觉观测从 `157.4` 增至 `163.4`，但候选边总数从 128
降至 64，命令拒绝均为 0。问题集中在观察目标选择与过早变焦的协同，当前默认关闭；专项
运行必须显式使用 `--d5-recon-track-cues`，该选项同时写入学习生成计划。

## 运行

```bash
python3 research_modules/scalable_3d_simulation/run_episode.py \
  --drone-count 200 \
  --duration 10 \
  --integrated-stack \
  --output research_modules/scalable_3d_simulation/outputs/smoke_200v200
```

三维静态图、GIF 和 MP4 只在需要时显式增加 `--plot`、`--gif` 或 `--mp4`。动画读取离线
真值状态文件，不进入在线 D1-D7 总线。

批量课程测试：

```bash
python3 research_modules/scalable_3d_simulation/run_batch.py \
  --scales 5 20 50 100 200 \
  --seeds 7 17 27 \
  --scenarios nominal dense_crossing formation_split evasive_multilevel \
  --integrated-stack --export-learning-data
```

`--export-learning-data` 只在集成栈下可用。单次运行输出 D3 匿名规划帧、D4 区域图、
D5 跨视角图和 D5 主动视觉整 episode staging；D5 不会在单一 seed 上伪造训练、验证和
测试集。主动视觉在线记录保存快照、规则示范、请求/实际动作和同帧相机反馈，离线文件
明确把 reward/outcome/counterfactual 标成 unavailable，不以数值零填充，也不伪造运行时
ACK。批量运行把完整 `(scenario_version, seed)` 组汇总到 `learning_dataset/`，至少有
三个组时才最终化 D5 跨视角图数据集；主动视觉数据集还必须满足至少 20 个完全未见 seed
的自身准入条件。D5 数值图与 `truth_entity_id` 标签保存为不同文件，主动视觉在线记录与
离线结果标签也物理分离，图特征和在线总线均不含真值编号。

大量训练 episode 使用流式入口，避免保存每个 episode 的完整世界状态：

```bash
python3 research_modules/scalable_3d_simulation/run_learning_dataset.py \
  --output research_modules/scalable_3d_simulation/outputs/learning_generation \
  --scenarios nominal dense_crossing \
  --scales 5 20 50 100 200 \
  --seeds 1 2 3 \
  --reserved-evaluation-seeds 1001 1002 1003 \
  --duration 2
```

该入口每个 episode 结束后立即写入 D3/D4/D5 staging，只在内存中保留轻量进度行。批次
成功最终化后，根目录保留 `episodes.jsonl`，已经转换为正式 D3 数据集的重复 staging 会被
删除；finalizer 异常或 D4 数据条件不足时保留相应 staging 供诊断和恢复。正式模式要求完整
场景目录、五档规模、训练 seed 与保留评估 seed 零重叠、干净工作树和 Git
忽略的输出目录。D5 主动视觉按数值 seed 跨场景/规模原子切分；默认 20% 测试比例和至少
20 个未见测试 seed，因此正式计划还必须提供足够的唯一生成 seed。该条件在 episode 启动
前检查，不能等批量运行结束后再失败。

冻结的首版训练计划为 `configs/learning_generation_balanced_v1.json`。它使用 100 个生成
seed，按五个 20-seed 分块均衡分配到 9 类场景和 5 档规模；每个场景/规模 cell 有 20 个
episode，总计 900 个。seed 1000-1019 完全保留给最终评估。正式运行命令为：

```bash
python3 research_modules/scalable_3d_simulation/run_learning_dataset.py \
  --schedule research_modules/scalable_3d_simulation/configs/learning_generation_balanced_v1.json \
  --formal \
  --max-episodes-per-run 45 \
  --output research_modules/scalable_3d_simulation/outputs/learning_generation_v1
```

每个完整 episode 都先同步写入 `episode_progress.jsonl`，再原子推进
`generation_checkpoint.json`；模块 staging 与进度索引必须一一对应。继续运行时使用相同参数并
增加 `--resume`。恢复入口逐字比较生成计划和训练 seed 注册表，校验 Git 提交、计划 SHA256、
连续 sequence、在线安全结果和 batch episode index。版本 2 checkpoint 允许在全部进度和
staging 已通过校验时恢复“进度领先旧 checkpoint”的崩溃窗口，并记录恢复次数与行数；checkpoint
领先、重复 episode、未索引或不完整制品仍失败关闭。全部 900 个 cell 完成后才执行统一最终化。
开发回归已覆盖 `1 + 2` 分块、单 episode 后异常续跑、旧版本 checkpoint 滞后恢复和篡改拒绝。
冻结 schedule 使用 `round_robin_cells_v1`，每连续 45 个 episode 各覆盖一次 9 类场景和
5 档规模，避免首个分块只运行单一场景或单一规模。

正式预检要求完整 45 个场景/规模组合且每个组合至少 20 个 seed，同时记录 schedule SHA256。
九场景存储门、三 seed 批次最终化门和代表分块启动门已经通过。D5 主动视觉仍占代表性
200v200 staging 的 96.8%，但三 seed 只需 12.04 秒，写入与最终化合计低于 episode 计算，
不再形成系统级阻塞。2026-07-20 的第一次正式运行曾在 209/900 后暴露 D5 同流多批次边界
问题；该未最终化目录只保留作故障证据。修复后使用干净提交从零生成的新目录已完成
900/900，旧、新 episode 没有拼接。

学习模型默认关闭。显式研究运行可增加下列参数；bundle 缺失、校验失败、分布外、低置信或
超时均保留规则路径：

```bash
python3 research_modules/scalable_3d_simulation/run_episode.py \
  --drone-count 20 --duration 3 --integrated-stack \
  --d3-learning-mode shadow --d3-model-bundle <d3_bundle> \
  --d4-learning-mode shadow --d4-model-bundle <d4_bundle> \
  --d5-model-bundle <d5_bundle> \
  --d5-active-vision-mode shadow \
  --d5-active-vision-bundle <d5_active_vision_bundle> \
  --output <episode_output>
```

D3 的 `assist` 只有在 bundle 内准入清单证明至少 20 个未见 seed、成本与安全非退化且
无回退帧时才可能生效。D4 建议先经过资源守恒、通信邻接、owner、epoch、lease、故障
围栏和联盟提交约束投影。只有运行时实际进入 `assist` 的后投影建议，main 才会在下一分配
周期使用冻结的来源快照和正式裁决进行一次性重验，再转换为 D3-owned 区域提示。D3 仍会
按当前计划、资源、已提交成员、备用和候选边二次校验。shadow 建议、重放、严格到期、
fault generation 变化和 regional authority 路径都不生效。D4 不修改正式裁决，也不直接
授权 D7。当前没有正式 D4 未见 seed 准入制品，实际研究运行仍保持 disabled/shadow。
D5 只有显式给出校验通过的 bundle 才使用图边概率，异常时继续采用几何规则。

主动视觉即使在学习模式 `disabled` 下也运行确定性 look-at/reacquire/scan 策略；这里的
`disabled` 只表示学习模型关闭。`shadow` 记录学习建议但实际执行规则动作，`assist` 仅在
bundle 内正式准入报告覆盖至少 20 个完全未见 seed、无安全/可见性/重捕获延迟退化时允许
采用学习动作。bundle 缺失、校验失败、分布外、超时或未准入时均执行规则命令。

场景目录还包含时延噪声、通信退化、中心失效、二级失效和高威胁多机需求配置。单一二级
接管、多二级区域所有权和二级再次失效后的完全分布式计划已经接入质点模块栈。所有路径
仍校验计划版本、区域所有者、故障代际、租约和提交模式；证据缺失或过期时保持闭锁。

默认不生成 200 路图像。相机模块只输出匿名 bbox、像素中心、投影协方差和独立离线真值
标签。远距离投影只有达到相机类型对应的最小 bbox 面积后才形成在线视觉观测，避免把
亚像素投影误报为可用检测。高频状态写入压缩 NPZ，事件写入 JSONL，汇总写入 JSON、
CSV 和中文 Markdown。

传感器自身处理时延与网络传输时延分开计算。批次先在 `measurement_timestamp + sensor
latency` 时刻进入通信队列，再按链路时延、抖动、带宽和丢包结果到达融合中心。episode
汇总记录发送、投递、丢弃、在途批次数和字节数。当前 D1-D7 仍作为同一进程内的组合栈
执行，模块间发布消息尚未拆成独立通信节点；报告不把传感器链路验证写成全分布式网络
闭环。

传感器场景包含中心雷达、分布式声学阵列和拦截/侦察相机。声学观测输出粗方位、协方差
和类别级声纹概率，`soundprint_is_identity=False`，不能作为目标身份编号使用。

`ScalableModuleStack` 是后续 D1-D7 的统一在线端口。输入只包含本时刻到达的匿名传感器
批次以及拦截机、侦察机自身导航状态；输出为 NED 三维加速度和版本化模块记录。目标真值
状态不会通过该端口传入在线模块，模块记录仍经过递归真值字段检查。

## 实验矩阵

`run_experiment_matrix.py` 统一编排 R0 纯规则、G1 跨视角图网络、A1 D3 代价修正、A2
D4 区域策略、A3 主动视觉、C1 学习组合和 F1 故障/高威胁完整体系。可比较变体使用相同的
场景、规模和 seed 形成 `comparison_key`。F1 只运行中心失效、二级失效和高威胁 M 对 N
场景，避免把与 C1 相同的模型组合重复解释为一种新算法。

矩阵运行强制使用 `entity_fixed_v1` 传感器随机序列。每个雷达、声学和视觉扫描按固定目标
槽位预取检测与噪声随机量，目标是否进入视场、是否已失活不会改变后续随机数位置。每个
`comparison_key` 另记录剔除算法版本后的外生配置 SHA-256；不同变体的该哈希不一致时停止
运行。普通 episode 继续默认 `sequential_v1`，因此既有正式数据和小规模回归不被重解释。

学习变体必须提供对应 bundle。A1/A2/A3/C1/F1 仍要求运行时诊断证明模型实际加载、辅助
模式获得相应权限并生效；缺 bundle、未准入或规则回退时不能把规则结果记到学习组。G1
采用更窄的人工授权影子路径：D5 v5 证据合格只说明候选可供评估，不能授予运行权限；独立
授权文件只允许模型为已经由确定性几何规则生成的匿名候选边计算概率。模型概率不参与在线
聚类、中心身份绑定、分配、降级、主动视觉或控制。

G1 影子授权固定绑定干净 Git 提交、D5 manifest/文件树/权重 SHA-256、场景、规模、seed、
时长、设备、有效期和撤销表。批准者必须显式确认请求 SHA-256 和固定短语
`APPROVE G1 SHADOW SCORING ONLY`。授权文件、请求和可变撤销表保存在仓库外。缺文件、
摘要不符、超期、撤销、设备或 scope 不符均失败关闭。运行栈保持 `d5_edge_model=None`，
只在独立 `d5_shadow_edge_model` 中计算旁路结果，并发布
`modules.d5.g1_shadow_scoring`；所有记录固定 `model_output_applied=false`。

正式模式还要求完整 R0/G1/A1/A2/A3/C1/F1、完整场景目录、5/20/50/100/200 五档规模、
至少 20 个唯一 seed、独立训练 seed 注册表、训练/测试 seed 零重叠和干净工作树。每个
episode 写盘后由 D6 从离线目录统一评分，矩阵本身不读取在线真值。

学习 scope 使用 `init-scope`、`run-shard` 和 `merge-scope`。G1 的准备、审批和执行分开
进行。`prepare` 只生成待审批请求和空撤销表，不授予权限；下列路径应位于仓库外：

```bash
COMMIT=$(git rev-parse HEAD)
python3 research_modules/scalable_3d_simulation/run_experiment_authorization.py \
  prepare \
  --authorization-id g1-shadow-eval-001 \
  --purpose "bounded G1 shadow comparison" \
  --expected-git-commit "$COMMIT" \
  --scenarios nominal dense_crossing \
  --scales 5 20 \
  --seeds 1000 1001 \
  --duration 2.0 \
  --d5-graph-model-bundle /path/to/d5_v5_bundle \
  --device cpu \
  --not-before-utc 2026-07-27T00:00:00+00:00 \
  --expires-at-utc 2026-07-28T00:00:00+00:00 \
  --revocation-registry-id g1-shadow-eval-registry \
  --request-output /external/control/g1_request.json \
  --revocation-registry-output /external/control/g1_revocations.json

# 读取 request_sha256 后，由获授权人员独立执行；程序不会自动批准。
python3 research_modules/scalable_3d_simulation/run_experiment_authorization.py \
  approve \
  --request /external/control/g1_request.json \
  --output /external/control/g1_authorization.json \
  --expected-request-sha256 <REQUEST_SHA256> \
  --approver-id <APPROVER_ID> \
  --approval-reason "bounded shadow evaluation" \
  --confirmation "APPROVE G1 SHADOW SCORING ONLY"

python3 research_modules/scalable_3d_simulation/run_experiment_matrix_shard.py \
  init-scope \
  --scope-variants G1 \
  --scenarios nominal dense_crossing \
  --scales 5 20 \
  --evaluation-seeds 1000 1001 \
  --duration 2.0 \
  --device cpu \
  --d5-graph-model-bundle /path/to/d5_v5_bundle \
  --experiment-authorization /external/control/g1_authorization.json \
  --experiment-authorization-sha256 <AUTHORIZATION_FILE_SHA256> \
  --revocation-registry /external/control/g1_revocations.json \
  --output /path/to/g1_shadow_scope

python3 research_modules/scalable_3d_simulation/run_experiment_matrix_shard.py \
  run-shard \
  --execution-plan /path/to/g1_shadow_scope/experiment_matrix_execution_plan.json \
  --shard-index 0 \
  --device cpu \
  --d5-graph-model-bundle /path/to/d5_v5_bundle \
  --experiment-authorization /external/control/g1_authorization.json \
  --revocation-registry /external/control/g1_revocations.json \
  --minimum-free-gib 20

python3 research_modules/scalable_3d_simulation/run_experiment_matrix_shard.py \
  merge-scope \
  --execution-plan /path/to/g1_shadow_scope/experiment_matrix_execution_plan.json \
  --write-d6-report
```

`run-shard` 在新建、恢复和每个新 cell 前重新检查干净来源、授权摘要、有效期、撤销表和
scope。旧版 v1 R0/开发执行计划保持兼容；带授权的 G1 计划使用执行计划 schema v2。当前
代码只完成授权合同和影子执行入口，尚未生成真实批准文件，也未运行正式 G1 scope。
完整边界见
[`docs/SCALABLE_3D_G1_SHADOW_AUTHORIZATION_CONTRACT_CN.md`](docs/SCALABLE_3D_G1_SHADOW_AUTHORIZATION_CONTRACT_CN.md)。

变体与 bundle 的对应关系为：G1 使用 D5 图模型，A1 使用 D3 代价修正模型，A2 使用 D4
区域策略模型，A3 使用 D5 主动视觉模型，C1/F1 同时要求四类 bundle。执行计划不保存本机
绝对路径；内容完全一致的 bundle 可以迁移目录。文件树、设备或运行时准入诊断不一致时
不得续跑旧计划。`merge-scope` 仍只声明当前 scope 完成；只有 scope 与完整父清单一致时
才允许声明完整矩阵完成。

正式 R0 使用独立入口。初始化命令必须在 clean commit 上执行，且输出目录应位于 Git
忽略目录或仓库外：

```bash
python3 research_modules/scalable_3d_simulation/run_experiment_matrix_shard.py \
  init-r0 \
  --output research_modules/scalable_3d_simulation/outputs/formal_r0_v1
```

默认 20 个分片可以顺序执行，也可以由 main 在受控资源预算下并行调度。`run-shard`
默认保留 20 GiB 可用磁盘；低于下限时不启动下一个 episode，并在当前完整单元边界写入
`paused` checkpoint。可用空间恢复后使用 `--resume` 继续。`--minimum-free-gib` 可以显式
调整保留量，但正式运行不得关闭该保护。暂停只发生在完整 episode 边界：

```bash
python3 research_modules/scalable_3d_simulation/run_experiment_matrix_shard.py \
  run-shard \
  --execution-plan research_modules/scalable_3d_simulation/outputs/formal_r0_v1/experiment_matrix_execution_plan.json \
  --shard-index 0 \
  --max-new-cells 5 \
  --minimum-free-gib 20

python3 research_modules/scalable_3d_simulation/run_experiment_matrix_shard.py \
  run-shard \
  --execution-plan research_modules/scalable_3d_simulation/outputs/formal_r0_v1/experiment_matrix_execution_plan.json \
  --shard-index 0 \
  --resume \
  --minimum-free-gib 20
```

20 个分片全部完成后再执行 `merge-r0`。合并器重新读取并校验全部单元，不信任 checkpoint
中的完成数字：

```bash
python3 research_modules/scalable_3d_simulation/run_experiment_matrix_shard.py \
  merge-r0 \
  --execution-plan research_modules/scalable_3d_simulation/outputs/formal_r0_v1/experiment_matrix_execution_plan.json \
  --write-d6-report
```

2026-07-20 使用 2v2、nominal、seed 101、0.25 秒完成一次脏工作树 R0 开发冒烟，有限状态
为真、在线真值使用为 0，并成功生成矩阵 manifest、逐 cell CSV 和 D6 离线报告。该结果只
验证编排与写盘，不属于正式消融或性能证据。

## 当前验证

2026-07-21 的 main 集成回归当前为 **90/90 passed**。其中 5v5、seed 7、1.2 秒场景形成
5 条 D1 航迹、5 条 D2 中心航迹、5 项 D3 分配和 5 路 D7 中段指令，在线真值字段使用为
0。200v200、seed 17、0.25 秒雷达烟测形成 200 条 D1/D2 航迹和 200 项分配；D3 从
40000 个完整 pair 中保留 6400 条候选边，D7 输出 `(200, 3)` 有限加速度。

同日补齐 D1/D2/D6 真值隔离评估链。D1 最终在线证据按观测保存创新平方和、门控、
六维估计、协方差、距离分档和乱序重放版本；D2 只依据 D1 源观测谱系生成逐帧中心航迹
真值映射。main 以 `observation_id + measurement_timestamp` 将每条 D1 在线证据精确连接
到 D2 `global_track_id` 和离线 `truth_id`，不使用航迹区间前向填充。连接不完整时相关
身份指标保持 unavailable。在线证据、离线真值状态、规范映射和结果文件分别写盘并绑定
真实文件 SHA256。D6 再通过公开适配器
输出逐 seed CSV、传感器/距离分档 CSV、聚合 JSON 和中文报告。5v5、seed 7、1.2 秒
回归中 D1 位置/速度 RMSE、NEES、NIS 均为 available，D2 `id_switch_count=0` 是有证据
的零；无模块栈时该字段保持 null/unavailable。该结果验证合同和写盘链，不是多 seed
精度达标结论。

中心失效场景已验证单一高空侦察节点覆盖全部活动区域时，D3 发布严格更新版本且 owner
切换为 `RECON-001`。两个二级节点可发布一份多 owner 区域计划；中心和二级先后失效时，
D3 可发布与 D4 裁决一致的 distributed 区域计划。D7 只对具有当前 owner、epoch、lease
和提交证据的任务区域恢复导引，空区域继续闭锁。该结果是接口和质点仿真证据，不是
AirSim、真实网络或实飞证据。

同一 seed、0.25 秒、仅启用雷达的短时规模测试结果如下。该数据用于定位开销，不作为
长时多 seed 验收结果。

| 目标/资源规模 | 实时因子 | D3 分配累计耗时/ms |
| ---: | ---: | ---: |
| 5 | 8.54 | 3.2 |
| 20 | 2.32 | 25.5 |
| 50 | 0.61 | 136.5 |
| 100 | 0.28 | 495.2 |
| 200 | 0.09 | 1970.7 |

200v200 条件下，D1、D2 和 D7 的累计耗时分别约为 120.0、107.8 和 20.3 毫秒，D3
约为 1970.7 毫秒，是当前首要性能瓶颈。D3 虽将 40000 条完整资源目标边压缩到 6400
条候选边，内部代价构造或求解仍存在密集矩阵和 Python 循环开销。episode 输出现在同时
记录世界、传感器、在线发布总线和 `module.d1_fusion` 至 `module.d7_guidance` 的分阶段
累计耗时。在线真值字段检查保持递归覆盖，已改为循环安全的迭代扫描并缓存重复字段名，
避免大批量航迹发布时重复执行昂贵的类型解析。外部模块发布仍默认深拷贝；集成模块栈对
每次新建且不再修改的负载显式转移所有权，省去一次大型航迹负载复制，真值扫描仍然执行。

2026-07-20 完成 D1 无多普勒雷达速度先验和 D2 相关六维后验修复后，以 radar-only、
seed 17 复测：

| 规模/时长 | D1 速度 P50/P90/max m/s | D2 速度 P50/P90/max m/s | D3 分配 | 实时因子 |
| --- | --- | --- | ---: | ---: |
| 50v50 / 2.2 s | 4.53 / 6.15 / 9.27 | 3.94 / 5.28 / 8.83 | 50 | 1.055 |
| 200v200 / 2.2 s | 4.13 / 6.78 / 9.19 | 3.51 / 6.02 / 8.34 | 195 | 0.254 |
| 200v200 / 3.2 s | - | - | 200 | 0.210 |

2.2 秒结果中的 5 项差额不是 `intercept_unreachable_3d`。首个雷达周期受检测概率影响只形成
195 条航迹，D3 在最小驻留时间内保留版本 1；`t=3.0 s` 时发布版本 2 并覆盖全部 200 条
航迹。D2 没有继续放大 D1 速度均值，200 条航迹和 ID 集保持稳定。上面的原 0.25 秒表是
稀疏分配优化前的历史短测，仅保留作性能演进参照。

保留 seed `1000-1019` 上的 D1/D2 NIS、NEES、门控率和长期速度 coverage 仍未完成。
D5 已完成 20-seed paired shadow，但 `shared_global_track_count=0` 且尺度特征接近确定性
可分，满分结果只说明当前合成保留集可分，不能外推到真实跨视角泛化。D3、D4 和 D5 均已
具备模块内数据、训练、bundle 与规则回退管线；现有 bundle 均未获得 assist 准入。D3/D4
clean v2 保留集和 D6 profile-bound availability sidecar 已完成，D3 同帧 assignment comparison
可用。当前剩余条件是取得严格绑定的 runtime ACK 和采用后物理结果窗口，并在独立故障场景
评估 D4 降级策略。缺少这些证据时不计算 paired physical effect，也不开放 PPO、assist 或
authority。

同日完成主动视觉运行时接线后，5v5、1.4 秒开发冒烟发出并确认 84 条相机命令，拒绝数为
0。200v200、seed 17、1.2 秒开发诊断发出并确认 1872 条命令，主动视觉 9 次调用累计约
0.374 秒；整段实时因子为 0.068。该运行来自未提交工作树和单一 seed，只用于接口及耗时
定位。D1、D2、D3 累计耗时分别约 7.76、3.50、3.82 秒，仍是主要开销，主动视觉不是本次
实时性下降的首要来源。

同日补齐 D4 区域建议的下一周期消费桥接。定向回归验证一次正常消费与 D3 应用，以及
advisory replay、严格到期和 fault generation 变化三类闭锁；在线真值使用仍为 0。该结果
关闭的是单进程质点 planning-loop 接线，不代表已有可准入 D4 checkpoint，也不包含跨进程
持久化 consumed-ID ledger、长时 200v200 或真实通信验证。

D5 主动视觉整 episode 数据已接入 main 学习导出。单 episode 和三 seed staging 测试证明
在线记录与离线标签分目录写入，奖励不可用时保持 null；三 seed 不满足 20 个未见 seed，
因此数据集按预期不最终化。该结果只证明数据合同和失败关闭，尚无 D6 outcome/
counterfactual 回填、正式行为克隆或近端策略优化结果。

同日新增 `run_learning_dataset.py` 流式生成入口，并以 nominal、2v2/5v5、seed 1/2/3、
每例 2 秒完成 6 个开发 episode。6/6 均为有限状态，在线真值使用为 0；导出 D3 12 帧、
D4 12 帧、D5 图 11 帧和主动视觉 107 帧。D5 图数据集成功最终化；主动视觉因计划测试
seed 只有 1 个而以 `insufficient_unseen_test_seeds` 保留 staging，符合失败关闭。开发输出
共 4.4 MB，其中主动视觉约 3.6 MB。

容量探针随后完成九类 200v200、每例 2 秒的干净工作树复测。9/9 状态有限，在线真值使用为
0，最终学习目录为 55.36 MB；全部 900 例均按该 200v200 平均值计算的存储保守上界为
5.54 GB。D3、D4 和 D5 跨视角图正常最终化，D5 主动视觉因不足 20 个未见测试 seed 保留
staging，符合失败关闭。

同一 nominal seed 930-932 的 clean-tree 计时经过两轮优化后，总耗时由 467.8 秒降至
144.6 秒，staging 由 225.9 秒降至 12.4 秒，批次最终化由 116.6 秒降至 7.3 秒；episode
运行保持在 124.7-125.2 秒。第二轮 D5 主动视觉写入为 12.04 秒，三场分别为
4.05/3.99/4.00 秒。D5 仍占 staging 的 96.8%，但写入与最终化合计 19.7 秒，已低于
episode 计算的 124.7 秒，不再主导总耗时。存储、最终化和首个正式代表分块启动门已经
通过；完整 900 episode、20 个未见 seed 和 200v200 实时性目标仍开放。两个正式代表分块
已完成到 90/900，连续运行随后完成到 209/900，并在第 210 项触发 D5 同流多批次异常。
runner 的 checkpoint 已升级为逐 episode 原子推进并兼容严格校验后的旧 checkpoint 滞后恢复；
这只解决异常后的完整边界恢复，不允许跨 Git 提交拼接正式数据。详细结果见
`docs/SCALABLE_3D_CAPACITY_AND_RUNTIME_REPORT_CN.md`。

每个物理步结束后，离线评估侧按三维 5 米门限登记唯一接近事件。事件中的真值目标号只
写入 `offline_proximity_intercepts.jsonl`，不进入在线总线；D6 还需结合分配与身份映射
判断该物理接近是否属于正确任务。

### 保留种子隔离干预

`run_reserved_seed_interventions.py` 对 seed `1000-1019` 各运行一个规则源 episode，固定
`entity_fixed_v1` 传感器随机流，并在同一个 D3/D4 时刻派生 control 和 treatment 两臂。
每个源 episode 只运行一次，两臂共享量测、规划帧、区域快照、通信日程和故障日程。输出
包含 20 条来源谱系、D3/D4 各 40 条隔离收据、顶层 manifest、中文报告和 SHA-256 清单。
任何臂均不可发布到在线总线，也不生成运行确认、物理结果、反事实或因果结论。

2026-07-21 已在 detached clean worktree 的提交 `6d5bfea` 上完成 nominal 5v5、2.2 秒、
seed `1000-1019` 的 v1 正式运行。20 个源 episode 均为干净、有限状态，在线真值使用为 0。
D6 已独立校验输入清单、lineage、D3/D4 各 40 条收据和全部 SHA-256。v1 中 D3 的 20 个
treatment 均因旧 OOD 门回退；复核确认 `previous_binding` 是二元特征，合法值 1 被错误套用
连续高斯 z 门。D3 已按二元端点修复，连续 6σ 门、模型和权重未变。D4 的候选分布外、有限值
和 50 ms 时延门均为 20/20 通过，置信度范围为 `0.508893-0.569492`，低于冻结门限 `0.6`，
因此 20/20 继续规则回退。D6 对 v1 的 paired outcome/effect 保持 `unavailable/null`。

运行器现升级为 `scalable3d-reserved-seed-interventions-v2`。D3 安全外壳标识升级为
`d3-offline-intervention-safety-shell-v2`，绑定二元端点与连续特征分离检查；顶层 manifest
和中文报告增加 D4 v2 的 confidence/OOD/latency/finite/failure 分门统计。clean 源提交
`78912963b67fe86ee9a8d29186b18a9dd60c460c` 的 v2 正式结果包含 20 个有限、在线真值使用为 0
的源 episode。D3 20/20 treatment 实际应用、0 回退，20/20 有效代价矩阵变化但最终 binding
均未变；D4 20/20 候选被评估，只有 confidence gate 为 0/20，其余四门均为 20/20，最终全部
规则回退。

D6 在提交 `d4e8562` 中完成 v1/v2 严格 consumer 和 profile/schema 绑定。当前 canonical 输出为
`reserved_seed_interventions_nominal_5v5_1000_1019_formal_7891296_d6_profile_bound_v2_audit_20260722`，
sidecar 文件/内容 SHA-256 分别为 `f3852251...c3b` / `c02a345c...d2d`。审计只开放同帧 offline
assignment comparison；runtime ACK、physical outcome/effect、counterfactual 和 causal 仍不可用。
学习权限继续固定为 `PPO/assist/authority=false`、`rule_fallback=true`。

### D1/D2 观测治理

2026-07-22，D1 前置扫描组织器和 D2 观测声明账本已接入统一 episode 状态机。D1 按量测
时间水位线对完整扫描做有界排序，重复、冲突、过晚和容量溢出整扫描拒绝。D2 使用不透明
观测标识、源命名空间和量测时刻区分新证据与后验重放；声明按安全水位线淘汰，超过容量时
失败关闭。main 总线保留双时间戳、协方差、公开审计和中心航迹身份所有权。

active-risk 5v5 seed 1005 的当前 1.1 秒集成路径始终保持 5 条规范航迹，起始数为 5，重复
出生、暂定删除和错误合并均为 0。结束排空阶段先按量测顺序融合并发布全部 D1 尾部扫描，
只把最终融合后验送 D2 一次，并在该次中心关联中归档所有待发布的 D1 源观测谱系。因此旧
实现由逐尾帧产生的 9 次人工重放现为 0，离线一致性映射仍覆盖全部已融合观测。正常运行期
的周期关联、短时 coast、失联老化和控制门控没有改变。

快速治理基准位于
`outputs/observation_governance_calibration_20260722_development`。20、50、100、200 四档各
运行 5 个 seed，每例 136 帧、33.75 秒。全部 episode 在线真值使用为 0；每例 D1 正确重排
12 个扫描，拒绝、过旧和溢出均为 0，峰值缓冲为 3 个扫描。D2 峰值声明数分别为
2390/4800、6020/12000、12070/24000 和 24170/48000，安全淘汰数分别为 285、735、1485
和 2985，容量溢出为 0。离线侧车的近邻召回为 1.0，错误抑制和错误合并为 0，确认时延为
0.25 秒。200 规模 D1 与 D2 合计峰值 `tracemalloc` 约 58.99 MB。

上述 development 批次来自脏工作树。同配置已在 detached clean 提交
`e4d66db02a0b8f1b867a0e81b4a73de84588426b` 正式复跑，输出位于
`outputs/observation_governance_calibration_20260722_formal_e4d66db`。20 个 episode 均为
`formal/clean`，D6 采用 `formal_only` 输入策略；在线真值、D1 结束缓冲、D1/D2 溢出均为
0。200 规模 D1+D2 峰值内存均值为 58996981 B，最大为 59007120 B。聚合 JSON 和中文报告
SHA-256 分别为 `6fb64252292aaedd3c68d1bfea64b76496136ce6edb32add61a281d511c4ed22`
和 `6198854b867d39fb2f1300cddeb1f75972ba8b7952361622213050115feb0827`。

该正式批次只测试观测治理，不是完整 D1/D2 精度、AirSim 或 200 对 200 拦截验收。另行运行
的 200v200 单 seed、2.2 秒全栈质点烟测在尾部合并后用时 60.21 秒，实时倍率 0.0365；相比
合并前 95.41 秒有所下降，但仍明显不实时。当前主要耗时为 D1 融合累计 35.12 秒和 D3 三次
分配累计 7.33 秒。完整多 seed 物理闭环、真实 AirSim 时延分布和阈值冻结仍开放。

## 版本

- 世界：`scalable3d-world-v1`
- 总线：`scalable3d-episode-bus-v1`
- 场景：`scalable3d-scenario-v1`
- 在线观测：`scalable3d-observation-v1`
- 离线真值：`scalable3d-offline-truth-v2`，读取端继续兼容 target-only v1
- D4 区域策略：`d4-region-resource-rule-v1` 或带权重 SHA256 的显式模型版本
- 学习导出：`scalable3d-learning-export-v2`
- 学习生成计划：`scalable3d-learning-generation-plan-v1`
- D5 主动视觉数据集：`d5.active-vision-episode-dataset.v3`
- D5 主动视觉模型 bundle：按 D5 当前代码和权重 manifest 记录，不从目录名推断
- 主动视觉快照/动作：`d5.active-vision-snapshot.v1` / `d5.active-vision-action.v1`
- 主动视觉策略：`d5-active-vision-rule-v1` 或模型语义版本加权重指纹
- 相机命令确认：`scalable3d-camera-command-ack-v1`
- 实验矩阵：`scalable3d-experiment-matrix-v1`
- D1 离线一致性清单：`scalable3d-offline-consistency-evaluation-manifest-v1`
- D1 扫描输入审计：`d1.scan_input.audit_summary.v1`
- D2 身份评估清单：当前 producer 使用 `scalable3d-offline-identity-evaluation-manifest-v2`，D6 只读兼容 v1
- D2 观测证据治理：`d2-observation-evidence-governance-v1`
- D2 观测声明账本：`d2-observation-claim-ledger-v2`
- main 观测治理快照：`scalable3d-observation-governance-runtime-v2`
- D1 融合性能诊断：`d1.fusion_performance_diagnostics.v1`
- D5 终端操作数诊断：`d5-scalable3d-operation-counts-v1`
- D6 观测治理标定输入：`scalable3d-observation-governance-calibration-input-v1`
- D6 真值隔离清单：`scalable3d-d6-truth-isolated-manifest-v1`
- 跨模块共享 seed 切分：`scalable3d-shared-seed-split-registry-v1`
- 保留 seed 隔离干预：新制品使用 `scalable3d-reserved-seed-interventions-v2`；历史正式证据保留 v1
- 共同检查点隔离物理续跑：`scalable3d-checkpoint-paired-physical-rollout-v2`，记录源 Git 提交、源提交一致性、源 episode 数和脏源计数

每个 episode 的 `manifest.json` 记录上述版本、Git commit、配置 SHA256、seed、模型版本和
阈值版本。在线总线拒绝任何包含 truth/actor/object identity 字段的观测负载。

分支、提交、模型制品和阶段标签规则见 [VERSIONING.md](VERSIONING.md)。

### D3 隔离批量输入

`run_d3_intervention_batch_input.py` 负责把统一三维 episode 中的规则规划证据转换为
D3 隔离重放输入。运行器固定使用保留 seed `1000-1019`，每个 seed 保留所有可重放的
匿名规划帧。帧必须来自规则路径，已有前序计划，并携带完整代价矩阵、计划、资源和航迹
快照。在线运行不加载 D3 学习 bundle。

输出目录包含严格 `manifest.json`、逐 seed 帧文件、冻结 development bundle 副本、
来源摘要和整树 `SHA256SUMS`。生产者要求 20 个源 episode 来自同一 clean commit，状态
有限且在线真值使用为 0。D3 后续只在隔离环境内重放 control/treatment，按时间顺序选择
首个合格帧。该输入不发布分配计划，不生成运行确认、物理结果、奖励或控制权限。

2026-07-26 已完成生产者软件回归 `3 passed`。main 随后在 clean source commit
`0ed7ca2730f5354be1e6021f9882f1ae26bc42df` 生成 seed `1000-1019`、每 seed
5 帧的 100 帧冻结输入，输入 manifest SHA-256 为
`e5367d2651955f809b482d78ef3205cbdf44d57eae576c80f64cbd38eac59a44`。
代码提交 `bdb665eb8e63a17f5f15dbf3fe472af10e5e5b5c` 的 clean evaluator 完成正式
重放，输出内容 SHA-256 为
`c01b13fb5925d99078a3bb9505dc0f9511ec5ab700a432399d3ebe0fcfb55592`。
80 帧应用学习代价，20 帧分布外回退；20/20 seed 的绑定变化、硬违规和
`global_track_id` 改写均为 0。隔离批量合同已经闭合，但当前策略没有越过
Hungarian 离散分配边界，A1 准入、默认路径、在线 assist 和生产权限继续关闭。

### D5 跨视角可见性校准

`configs/d5_crossview_visibility_calibration_v1.json` 是 5v5、2 个侦察节点的近距
几何校准场景。目标、拦截资源和侦察节点仍使用原三维质点、针孔投影、双时间戳和
协方差合同。该配置缩小世界范围，关闭视觉虚警和通信丢包，用于确认至少两个相机能
同时生成真实目标匿名航迹；它不替代 `nominal_200v200.json`，也不用于声明远距光电
性能。

2026-07-26 的 seed 1000、12 秒开发运行状态有限，在线真值读取为 0，相机命令
`791/791` 接受。离线侧车记录 667 条目标视觉观测、0 条虚警，覆盖 5 个目标。D5 的
131 次发布累计形成 796 个图节点、294 条候选边和 247 条通过几何门的边；单帧最大
11 个节点、8 条边，跨调用复用相机快照计数为 139，中心航迹绑定累计 530 次。该运行
基于包含新配置的开发工作树，只证明正向输入和异步同图链路可达。真实错误合并率、
边分类精度、G1 模型收益和多 seed 稳定性仍待 clean paired evaluation。

`run_d5_crossview_calibration_batch.py` 负责冻结后续正式校准输入。运行器要求至少
3 个不同 seed；正式模式固定使用 `1000-1019`，并拒绝脏工作树。每个 seed 保存完整
episode 输出，同时把匿名关联图与 evaluator-only 标签分别写入
`d5.tracklet-dataset.v2`。图中每个带来源节点必须恰有一条 observation link，链接
保留相机命名空间、量测时间和到达时间。帧坐标固定为
`scenario_version + seed + frame_index`，不依赖 R0/G1 运行目录或配置哈希。

批次输出包含 `manifest.json`、`per_seed.csv`、中文运行报告、逐 seed episode、
冻结数据集和整树 `SHA256SUMS`。manifest 显式记录源提交、工作树状态、配置哈希、
规则或模型实际使用帧数以及所有权限均为关闭。数据集中的 `edge_index` 表示通过在线
几何候选门的边，不等同于模型阈值后的关联决定；模型精度和收益必须由独立模型评分
制品计算，不能从候选图直接推断。

2026-07-26 的 3-seed 开发复跑覆盖 seed `1000-1002`，状态有限且在线真值读取为 0。
累计得到 2473 个图节点、833 条几何候选边、713 条图边和 2473 条来源链接；392 个图帧
标签完整，来源链接违规为 0。稳定帧坐标 sidecar 覆盖 392/392 个图帧，并通过 D6 的
dataset-manifest 哈希绑定检查。D6 开发评估得到 713 个时间合格同目标跨相机对，713 条
几何边均为真边，几何候选精确率、召回率和 F1 均为 1.0。该场景关闭虚警且目标分离
明显，结果只说明正向几何门可用，不能作为困难负样本、真实跨视角泛化或 G1 模型收益
证据。该复跑来自脏工作树，不是正式 R0。批处理器单元测试为 `5 passed`。

2026-07-26，main 在 detached clean commit
`64cb865b9933d45b13878019c0e1a21a8fbb2b05` 完成正式 R0。固定 seed
`1000-1019` 共形成 2670 个完整标签图帧、16842 个节点、5400 条门前候选边和
4658 条几何图边；16842 条来源链接全部覆盖，在线真值读取、来源违规和非有限状态均
为 0。dataset manifest SHA-256 为
`5ee284fd3a998c7ec415000cda3def1b1db7b866a762bcc68b6667858730b247`，
稳定帧 sidecar SHA-256 为
`f0db1b13913c69ba6b4beb5c07e242135885a3fb16fc9f559f193ac632611a1e`。

D6 正式评估状态为 `pass`，无 blocker、硬违规为 0。4645 个时间合格同目标跨相机对
中保留 4642 条真边，另有 16 条假边。微平均精确率为 0.996565，召回率为 0.999354，
F1 为 0.997958，假边率为 0.003435。20-seed F1 均值为 0.997652，95% bootstrap
置信区间为 `[0.995325, 0.999571]`。评估内容 SHA-256 为
`dc84c90b90378ba0579311b7b5654018bf3a910ad98f30a59e5dc76eecd422af`。
该结论只验收当前近距、无视觉虚警配置下的几何候选图。G1 边概率和阈值、聚类纯度、
中心绑定正确率、控制结果及物理拦截结果仍不可用。

## D4 当前谱系运行兼容性预检

2026-07-28，main 新增 D4 区域策略运行兼容性预检。预检从统一三维质点运行时采集
匿名区域快照，并按候选模型清单中的固定特征边界逐节点、逐边检查。模型来源可信、
运行特征分布兼容和实际采用是三项独立结论。预检不会修改确定性资源投影器，不会放宽
`ood_margin=0.05`，也不会授予辅助、分配、降级或控制权限。

冻结的 current-lineage 候选绑定以下身份：

- 受版本控制的审计副本位于
  `research_modules/d4_distributed_fallback/model_registry/region_resource_a2_current_lineage_development_v1`；
- 来源提交 `b0d498d9e76e19e9045e127b6dae26ea164b3fa4`；
- 候选清单 `7cc10ad770bd95fcb813dbf3d16b17040ec5f41f80fe0dc53e3e291a32f4de64`；
- 权重 `fd1b9c4cf7580083fadc04a70b87aa6439930eba764a970279611ccc57f30047`；
- 数据集 `7e17aba7911602c1b9e9f5b917aea97f1eeec478f03963b119fbcfc8de299e72`；
- 原切分 `b413fa810ae426ad143b713afac2c7a3366fae123e397054dbb9b0449d7b0c16`。

开发预检得到两组一致的阻断结果。5 资源、5 目标、2 区域、seed 2000 产生 3 个区域
快照，3/3 为 `feature_ood`；200 资源、200 目标、8 区域、seed 2001 产生 2 个区域
快照，2/2 为 `feature_ood`。两组非回退模型执行均为 0，在线真值使用为 0，状态均为
有限值。主要越界项包括资源承诺比例、D1/D2 不确定度、租约剩余时间、二级覆盖与就绪度、
D5 可见性与一致性、通信容量，以及部分边带宽和转移时间。

当前候选因此不能进入正式 20-seed A2/R0 评价。下一候选需组合两类现有数据：

- 运行数据集 `b06d741bd22a0cd84ef1e47a48a0b8cd81ceb7e4ea294eeeb38b892e69d36158`，
  共 900 个 episode、1798 帧，用于覆盖统一运行时的真实特征范围；
- 动作课程 `7e17aba7911602c1b9e9f5b917aea97f1eeec478f03963b119fbcfc8de299e72`，
  共 100 个 episode、300 帧，用于提供安全的 hold、重规划、配额和跨区转移动作。

两个来源都使用数字 seed 0 至 99，但原切分不同。新训练视图必须按数字 seed 全局原子
重分割，分别绑定两个来源的 SHA-256 和动作库存，并完全排除正式评估 seed 1000 至 1019。
首个新候选先限定 8 区域适用域，在 D4 变更形成干净提交后从 clean checkout 构建。
main 先使用非正式 seed 重跑兼容性预检；只有出现分布内、非回退模型执行且安全投影保持
有效，才允许冻结新候选并准备正式 20-seed。

### 8 区域双源候选预检

D4 已从 clean commit `923f3f6e91af0f85aed446c66420c834d2de63fb` 构建
`region_resource_a2_8region_runtime_action_shadow_v1`。候选组合 900 个运行 episode
和 100 个动作课程 episode，数字 seed 0 至 99 按 70/15/15 全局原子切分，
seed 1000 至 1019 使用数为 0。候选只适用于 8 区域，置信度门限保持 0.60，
全部辅助、分配、降级、联盟和控制权限为关闭。

main 预检现可识别裸模型包或带审计清单的候选根目录，并分别记录原始模型前向执行和
候选门控许可执行。新候选的开发结果如下：

| 场景 | 区域快照 | 分布内 | 原始模型执行 | 候选许可执行 | 在线真值 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 5 资源/5 目标/2 区域，seed 2000 | 3 | 0 | 0 | 0 | 0 |
| 200 资源/200 目标/8 区域，seed 2001 | 3 | 1 | 1 | 0 | 0 |

2 区域场景同时触发运行分布和候选适用域拒绝。8 区域场景的 2 个越界帧只涉及
`secondary_readiness`：训练范围为 `[1.0, 1.0]`，运行范围为 `[0.0, 1.0]`，
16/24 个节点值低于边界。置信度校准仍是独立阻断项。315 个验证样本全部超过 0.60，
其中 51 个不满足登记的动作一致性条件，因此候选许可执行为 0。

这轮结果说明双源训练视图已让 8 区域原始模型出现非回退执行，但运行覆盖和置信度校准
都未闭合。下一轮先补采真实 8 区域、部分二级节点未就绪的匿名运行帧，再由 D4 重训和
校准。OOD 余量、置信度门限和确定性规则回退保持不变；正式 20-seed/900-cell 仍关闭。

## D4 规划专用区域转移合同

2026-07-29，main 将区域资源不均衡接入统一三维 episode。专项场景使用 20 个目标、
20 个资源和 8 个区域；目标区域库存为 `2/4/2/3/2/3/2/2`，资源区域库存为
`4/1/2/3/2/3/2/3`。区域局部可达性只在该显式 probe 中启用，普通场景保持原资源
可达规则。

seed 29 的中心计划先形成 17 条分配和 3 个未分配目标。D4 规则建议器在正式决策约束下
发布 `d4-region-resource-advisory-v2`，允许 `region-000 -> region-001` 转移 1 个资源。
来源区域 4 个资源中保护 2 个已承诺资源和 1 个备用资源。目标区域只取得
`planning_replan_eligible=true`；assignment、coalition、takeover、control 及汇总执行
权限全部保持 false。D3 在下一规划周期发布新计划标识和版本 2，形成 18 条分配和
2 个未分配目标。新增目标覆盖为 1，在线真值使用为 0。

中心在 2.0 秒失效的负例把真实 `_fault_generation_changed` 写入每个 D4 区域快照。
该帧所有区域 `fault_generation_fenced=true`，规划专用资格关闭，不发布转移、不消费旧
建议，也不形成区域提示后继。D6 对正例输出 `contract_chain_verified`，对负例输出
`fault_generation_fence_verified`，安全违规均为 0。

D3 另用同一下一周期输入构造 source、未发布规则 R0 和已发布 treatment。三份计划的
`execution_signature()` 均按业务绑定比较；treatment 相对 source 和 R0 都存在真实绑定
或目标覆盖变化，机械升版、续租和元数据刷新不计作干预。当前模块回归为 scalable
world/module stack `100 passed`、D3 `618 passed, 1 skipped`、D4 `794 passed`、D6
`1202 passed`。skip 为可选 OR-Tools，warning 为既有 Matplotlib 三维后端提示。

该证据使用测试专用规则建议器，只关闭规划建议、D3 严格后继和故障代际围栏的运行合同。
D4 v4 仍未注册，独立同键 R0、多 seed 配对物理 episode 和模型收益均不可用；assist、
分配、降级、联盟和控制权限继续关闭。

## 高威胁计划身份与联盟连续性前置复核

2026-07-30，main 修复统一运行时的两个 P0 合同断点。同一
`plan_id + plan_version` 现在只发布一次不可变 D3 权威计划；同身份评估刷新只进入
诊断，不再发布第二份计划或生成运行确认。相同身份出现不同权限签名或载荷摘要时立即
失败关闭，通信层继续保留首次序号和内容寻址引用。

D4 为当前计划任务保留最后一份真值隔离的 D2 六维状态与协方差。D2 临时缺少当前目标
时，D4 保持任务和已提交联盟，直至新计划、明确撤销或租约到期。该缓存不进入 D7；
D7 仍要求当前 D2 航迹、身份承诺、当前计划和联盟许可，缺轨目标不会生成制导输入。

开发工作树上的 `high_threat_m_to_n` 100 组前置批次覆盖 5/20/50/100/200 五档、
每档 seed 1000 至 1019。100/100 状态有限、在线真值为零、D3-D4 最终计划一致且当前
联盟闭合；151 次权威计划发布对应相同数量的运行确认，48 次同身份评估刷新被抑制，
重复身份发布和载荷摘要冲突均为零。D4 缓存连续性在 28 个 episode、391 个任务快照中
触发。

D6 独立只读审计进一步确认 644 个当前多成员联盟目标全部闭合，195838 条通信处置记录
在 100/100 个 episode 中可用并通过结构检查。当前 D3 载荷没有发布可与 D4 对照的区域
时期编号和区域租约，两项均为 `0/100 available`，不得记作一致或不一致。

该批次 manifest 明确记录 `repository_dirty=true`，因此只作为 development 证据。
200 对 200 平均实时倍率约 0.156，仍未达到实时。D2 严格离线身份指标只有 88/100 个
seed 可用，其中 200 对 200 为 10/20；不可用项不按零处理。详细结果见
[高威胁多机协同 P0 前置复核](docs/SCALABLE_3D_HIGH_THREAT_P0_PRECHECK_V4_20260730_CN.md)。
正式 R0 和 900-cell 矩阵继续等待干净提交、模块所有者复核及 clean smoke。

## D1 光电关联风险留出审查

2026-07-31，main 在不修改 D1 后验和 D2 关联行为的前提下，将 D1 光电病态投影风险旁路
接入统一三维总线。开关 `--d1-association-risk-evidence-shadow` 默认关闭；开启后只在 D1
载荷中发布原始风险证据和版本化正负分类，并在 observation governance 中保存独立审计。

独立留出执行覆盖 nominal 100v100 与 200v200 的 seeds 2000 至 2019，共 40 个 2.0 秒
episode。40/40 状态有限、在线真值使用为 0，D2 只读因果诊断完成 40/40。排除 4 个非相机
阻断样本后，36 个可评估 case 产生 1,015 条原始证据和 1,015 条在线分类；在线分类与离线
冻结 v2 复算 `1015/1015` 一致。

故障事件命中为 `11/13`，召回 `0.8461538462`，低于冻结门限 `0.90`；严格身份可用对照
告警为 `0/25`。样本数量门通过，性能门未通过。v2 继续 default-off、shadow、
`evidence_only`，D2 enforcement 禁止。本留出集不得用于调参，下一候选必须使用新的开发数据
和新的独立留出集。

两组控制/影子复核在剔除四个风险旁路字段后，D1、D2、严格身份语义和 truth NPZ 均保持
相同。正式基线仍为 `450/900`、shards 0 至 9；本轮没有启动 shards 10 至 19。完整审查见
[D1 光电关联风险留出审查](docs/SCALABLE_3D_D1_ASSOCIATION_RISK_HELDOUT_REVIEW_20260731_CN.md)。
