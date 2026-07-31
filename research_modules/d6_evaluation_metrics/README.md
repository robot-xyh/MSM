# D6 Evaluation Metrics

## 2026-07-31 学习作用域归档原生审计

`learning_scope_formal_audit` 现支持显式目录模式和归档模式。learned scope 与每个 R0
scope 分别选择存储模式，允许 G1/A1/A2/A3/C1/F1 使用归档、R0 使用目录，也允许两侧都
使用归档。接口不检查目录内容后自动猜测模式：目录模式提供 `merge_dir`；归档模式提供
`archive_root` 和 `archive_merge_dir`，两组输入不能同时出现。原目录构造方式、审计顺序和
CLI 参数继续兼容。

归档模式先读取冻结 execution plan 和 archive-native merge 索引，再由 D6 的通用归档集合
验证入口处理精确 shard 子目录集合。普通 sidecar 文件记录在结果中；缺片、额外目录、
symlink 和非普通项失败关闭。每片依次完成 checksum、manifest、payload、计划绑定、
inventory、tar 成员路径/元数据/大小/SHA-256 验证。验证后的 shard 单独恢复到系统临时
目录，在清理前执行既有学习证据审计和 `evaluate_scalable_3d_episode()` 离线评价。

全部分片处理后，D6 复核 archive-native merge 的 manifest、cell CSV、逻辑 episode index、
archive binding 和 D6 报告 binding。逻辑 episode 路径只用于索引对账，不按 canonical
materialized 路径读取。实际 assist adoption、模型 bundle、在线真值隔离、物理结果、同
comparison key 的 R0 配对和非退化规则沿用目录模式，没有零填充，也不授予模型晋级或控制
权限。

archive-native merge 必须由 producer 使用 `write_d6_report=True`（CLI 为
`--write-d6-report`）生成。D6 要求该输出是为了复核报告文件、评价器来源与执行计划绑定，
不采信 producer 的 verified 状态或报告 verdict。通用归档集合入口还会在读取归档前独立
校验 `plan.sharding`、排除布尔值的正整数 `shard_count`、descriptor 数量、连续索引和规范
`shard_{index:03d}_of_{count:03d}` 名称，不依赖上游 learning scope 计划加载器兜底。

公开 scope 结果新增 `storage_mode`、`archive_root`、`verified_archive_count`、
`peak_staged_shard_count` 和 `sidecar_files`。目录模式明确报告未执行归档验证、归档计数 0 和
峰值 0。CLI 新增 `--scope-archive-root`、`--scope-archive-merge-dir` 与可重复的
`--r0-archive-scope`；同一 scope 的目录和归档参数冲突时由参数解析器拒绝。

2026-07-31 使用两类开发夹具完成验证。D6 自建夹具覆盖六种学习变体、归档 R0、归档/目录
混合、无 materialized shard、普通 sidecar 和安全负例。新增耐久兼容测试只在测试代码中导入
`scalable_3d_simulation`，通过真实 execution-plan writer/loader、shard runner、正式归档创建器
和 `write_d6_report=True` 归档 merge 生成一对紧凑 G1/R0 scope；D6 归档验证函数未被
monkeypatch。该测试的父矩阵声明满足 producer 正式约束，cell 枚举和执行单元在测试中缩减，
因此属于 producer 兼容开发夹具，不是正式学习运行。

学习作用域专项为 `68 passed, 1 warning in 8.35s`；learning/archive 组合专项为
`89 passed, 1 warning in 9.61s`；D6 全量为
`1330 passed, 1 warning in 120.34s`。分片声明负例、缺片、额外目录、symlink、payload/
计划错绑、merge 篡改和重复/缺失 cell 均失败关闭。warning 为既有 Matplotlib `Axes3D`
环境提示。

本轮没有启动正式 shard，没有读取或修改 `/tmp` 正式证据，也没有删除源目录或归档。
正式 G1/A1/A2/A3/C1/F1 学习 scope 仍未运行；正式结果需由 main 提供完整归档集合、启用
D6 report 写出的归档 merge 和模型 bundle 后再执行本入口。

## 2026-07-31 正式分片归档独立审计

`formal_r0_full_posterior_audit` 的 v1 配置新增可选 `archive_root`。未配置时继续使用原始
目录模式；配置后进入归档模式。D6 不调用 producer 的归档验证函数，也不信任
`verified_formal_shard_archives_v1` 状态。D6 独立复算每片 `SHA256SUMS`、manifest、
payload、执行计划绑定、文件清单和 tar.zst 成员的路径、大小、摘要及确定性元数据。

完整集合校验通过后，D6 一次只把一个 shard 恢复到系统临时目录，调用现有 targeted
posterior 低层审计，再删除临时目录后处理下一片。900 项低层行来自恢复后的 episode，
不读取 producer D6 汇总。归档 merge 的 manifest、cell CSV、逻辑 episode index、archive
binding 和 `archive_d6_evaluation_binding.json` 单独复核；绑定的五类 D6 报告逐文件重算
路径、大小和 SHA-256，但报告中的 producer 结论不作为 full posterior 输入。

配置仍使用 `d6.formal-r0-full-posterior-audit-input.v1`，新增字段示例为：

```json
{
  "archive_root": "/path/to/formal-r0-archives",
  "merged_scope_relative_path": "merged_scope_from_archives"
}
```

归档集合只比较计划规定的子目录，普通 pack/verify sidecar 文件可以原位保留。缺片、额外
目录、任意符号链接、压缩损坏、不安全成员、计划绑定错配、单元缺失及 D6 报告篡改均返回
`fail_closed`。merge core、D6 artifact 及其父目录不得通过 symlink 间接读取。D6 还会
校验 evaluator schema、Git 提交、dirty 状态和源码树摘要。源码树摘要严格采用当前
evaluator provenance 合同的 `sha256:<64位小写十六进制>`；空值、裸摘要、错误前缀和
非十六进制载荷均失败关闭。源 shard 和 archive 均不删除。
2026-07-31 归档/full posterior 专项为 `32 passed`，
D6 全量为 `1297 passed, 1 warning in 114.12s`；
现有正式归档的 10/20 非破坏性预检只因缺 shard 10-19 失败关闭；sidecar 被接受，实际
低层完成数为 0，未生成 merge 输出。正式 20-shard、
900-cell 归档审计尚未运行。`learning_scope_formal_audit` 的 archive 模式已在同日后续任务
关闭，见本页顶部；该开发验证不改变正式 R0 的完成状态。

## 2026-07-31 预评估行报告接口

`Scalable3DOfflineReportGenerator.write_report_bundle_from_rows()` 接受
`evaluate_scalable_3d_episode()` 已生成的行，统一写出逐 episode CSV、aggregate JSON、
模块性能证据、中文 Markdown 和阶段耗时曲线。main 可以临时恢复一个正式分片，逐
episode 生成评估行，释放该分片占用的空间，最后用全部行一次生成报告包。

目录入口 `write_report_bundle()` 现在只负责读取 episode 并调用预评估行入口。阶段列补齐、
证据状态终结、bootstrap、实验矩阵聚合、性能证据注册和五类文件写出只有一套实现。预评估
入口要求当前 v12 schema、episode/evaluator 来源字段、在线真值审计字段和严格离线身份
字段完整；缺失字段、重复 episode 或空输入均失败关闭。

报告生成前会深拷贝每一行。调用方累积的原始行及其中的阶段记录、失败原因、availability、
严格身份、真值隔离和来源字段不会被原地修改。等价性测试证明目录入口与预评估行入口的
CSV、aggregate JSON、模块性能 JSON、中文 Markdown 和曲线摘要一致。聚焦测试
`3 passed`，`test_scalable_3d_offline.py` 为 `77 passed`，D6 全量为
`1277 passed, 1 warning in 116.32s`。本次没有改变在线总线、控制流程或 truth 使用边界。

## 2026-07-31 D4 历史候选源漂移审计

D4 v4/v5 候选制品和审计配置固定绑定 clean commit
`fd857457bb27a4a709a7c4937e22ebe1cbd7f848`。其中
`region_resource.py` 的外部锚点为
`1b534b4b3d73724e2ed778f05182eac45052087efc05afa8a7900daf3dbd65e4`。
D4 在 `20895c7` 增加逐区域建议发布代次安全门后，当前文件摘要变为
`1f47de6104f16c563ca6fc8cca3f1540437d77f3d3617225eef7b8b2423a78c2`。
历史候选没有失效为历史证据，但已不再是当前 D4 源的候选。

D6 生产审计继续失败关闭。v4 返回
`source_current_file_differs_from_audited_commit`，v5 返回
`v4_source_external_anchor_mismatch`。原配置、候选树和哈希均未覆盖，也没有把当前文件
摘要写回历史锚点。重叠诊断负例已改用受控内存夹具，独立验证
`validation_overlap_expected_crosscheck_mismatch`，不再依赖已经源漂移的真实候选前置链。
本次没有修改生产审计代码。专项测试 `3 passed`，D6 全量测试
`1274 passed, 1 warning`；warning 为既有 Matplotlib `Axes3D` 环境提示。

新的当前候选仍需由 D4 生成新版本制品。D6 随后以新的 clean 源提交、源身份、实现文件
清单、候选树、数据划分、校准制品和独立 holdout/runtime 证据建立新审计配置。完成前，
v4/v5 历史候选保持未注册、未准入，规则路径继续生效。

## 2026-07-31 正式 R0 前 450 项严格身份重聚合

`scalable_3d_offline` 已把两类含义分开。`d2_online_producer_id_switch_count`
保留在线 D2 的原始诊断声明；在线链路没有真值时，该字段通常为 unavailable。
公共 `d2_id_switch_count` 只表示严格离线身份交换，唯一来源是
`d6_truth_isolated/episode_record.json` 中的 `d2_identity`。

D6 在读取严格指标前核对真值隔离清单 schema、episode 身份和规模、episode record
SHA-256、离线身份清单 SHA-256、身份评价及四类源文件 SHA-256，并复用现有 D2 身份
适配器重验合同。重验结果必须与 episode record 中持久化的 `d2_identity` 完全一致，
且 `strict_id_switch_backfilled=false`。旧版 CSV 只有同名数值而没有上述来源声明时，
正式后验审计和实验矩阵准入不把它计为严格指标。

main 已使用 D6 v12 评估器提交
`b6289c54ff0057a07148bfe906d48bcf5e2e099e`，对正式 R0 clean producer
`80e55eb43bc4a5feeac9c9af0d718d461a46401f` 的 shard 0-9 共 450 个 episode 重新生成
派生汇总。输出中有限状态为 `450/450`；严格 `id_switch_count` 为
`414/450 available`、`36/450 fail-closed`。可用项合计 893 次身份交换，169 个 episode
为非零。36 个不可用项中，27 个为 `multiple_truth_targets_for_global_track`，9 个为
`source_observation_outside_lineage_window`，全部保持 null。

在线 producer 指标仍为 `0/450 available`，450 项原因均为
`producer_declared_id_switch_count_unavailable`。这符合在线真值隔离合同。严格制品的
哈希和合同复核为 `450/450`，episode producer 来源与 evaluator 来源分开记录；重聚合
没有改写原 episode 或冻结执行计划。

修复前 90-cell 诊断继续作为历史证据保留：通用汇总曾错误得到 `0/90 available`，同批
离线严格证据实际为 `73/90 available`、17 项失败关闭。原“main 待重聚合 135 项”已经
由本次 450 项重聚合取代，不再是当前状态。当前结果仍是半程派生汇总；正式 full posterior
和 post-run experiment matrix admission 必须等 900-cell 完整范围生成后执行。

## 2026-07-31 高威胁 clean smoke 修复后复核

D6 只读复核 clean commit `b063535c5473b67e41683f84c33c088ce5c7d41a` 生成的
6 个高威胁 episode。范围为 5、100、200 三档规模，每档 seed `7/17`、仿真 2 秒。
42 个核心制品、配置哈希、有限状态、在线真值隔离、最终 D3-D4 计划标识/版本/时期/
租约和当前联盟闭合均为 `6/6`。10 次权威发布、10 个计划身份和 10 次计划确认守恒；
49 个当前联盟目标闭合，16101 条通信处置通过验证。

12 条 D4 区域建议全部匹配各自发布时刻的最新正式代次，发布时旧代为 0；四个重规划
episode 均补齐最终 v2 建议，最终计划建议覆盖为 `6/6`。低层
`formal_acceptance_eligible` 从旧批次的 `2/6` 恢复为 `6/6`，D4 建议代次的
6-cell 预准入通过。该 smoke 不含冻结 execution plan 和正式矩阵 metadata，不能替代
targeted/full posterior 的 900-cell 审计。完整 ID Switch 仍为 `3/6 available`，
100/200 规模仍低于实时。完整报告见
`reports/HIGH_THREAT_CLEAN_SMOKE_B063535_REVALIDATION_20260731_CN.md`；旧
`49e43ea` 报告保留为修复前对照。

## 2026-07-31 高威胁 M 对 N v5 时期租约复验

D6 只读复核
`/dev/shm/msm-high-threat-r0-p0-precheck-v5-20260730` 的 100 个 episode。五档规模均为
20 seeds、2 秒质点仿真。制品完整、配置哈希、有限状态、在线真值零使用、最终
D3-D4 计划标识/版本、时期、租约和当前联盟闭合均为 `100/100`。

151 次 D3 权威发布对应 151 个不同计划身份和 151 次运行时计划确认。同身份重复权威发布
为 0，48 次同身份评价刷新只保留诊断，不续租。逐消息通信处置
`100/100 available/verified`，当前联盟目标为 644 个。D4 航迹回退出现在 28 项，共
391 个快照；D7 的当前航迹和身份门控没有因此放宽。

v4 的时期/租约不可用 P1 已在开发证据层关闭。v5 原始批次中的 51 项旧计划建议继续作为
历史证据保留；其运行时断点已由 `b063535` clean smoke 的 12/12 发布时代次和 6/6 最终
计划覆盖关闭。仍开放的 P1 是正式 900 项重跑、12 项离线身份切换不可用，以及 50 以上
规模未达到实时。200 对 200 墙钟均值/P95 为 `14.209/15.566` 秒，实时倍率均值为 0.142。
完整报告见
`reports/HIGH_THREAT_PRECHECK_V5_REVALIDATION_20260730_CN.md`。

## 2026-07-30 高威胁 M 对 N 开发态 100 项修复复验

D6 只读重算
`/dev/shm/msm-high-threat-r0-p0-precheck-v4-20260730` 的 100 个 episode。范围为
5、20、50、100、200 五个规模，每个规模 seed `1000-1019`，仿真时长 2 秒。该批次来自
提交 `2790b165` 对应的未提交工作树，不是 clean formal shard，也不替代 900 项正式 R0。

最终 D3-D4 计划标识、版本和当前联盟闭合均为 `100/100`。151 次 D3 权威发布对应 151
个不同的 `(plan_id, plan_version)`，同身份重复发布为 0。v3 的三个最终快照断点已关闭，
`payload_digest_mismatch` 和 `cross_binding_invalid` 均为 0。当前计划共审计 644 个
多成员联盟目标，均在最终 D4 快照中完成原子提交。

有限状态和在线真值零使用均为 `100/100`。逐消息通信处置
`100/100 available/verified`，共 195838 条，其中 delivered 186213、dropped 1950、
pending 7675。离线 D2 身份切换为 `88/100 available`，可用部分合计 52；其余 12 项
保持 unavailable。D3 未发布区域时期编号和租约对照字段，因此两项 D3-D4 交叉核对仍为
`0/100 available`，不能写成一致。

200 对 200 的实时倍率均值为 0.156，墙钟时间均值/P95 为 `12.928/14.296` 秒。该结果
只说明 2 秒开发态三维质点批次的运行成本，不证明部署实时性。完整复验见
`reports/HIGH_THREAT_PRECHECK_V4_REVALIDATION_20260730_CN.md`。下一步仍需补齐时期和
租约对照，并在 clean source 上整体执行正式 900 项。

## 2026-07-30 正式 R0 当前计划绑定审计器

D6 已补充最后 D3 计划与最后 D4 决策的严格绑定审计。审计以
`modules.d3.assignment_plan` 的最后一次发布为当前代次，逐区域核对 D4 `ownership`
中的 `plan_id` 和 `plan_version`。D3 发布中存在区域 epoch 或 lease 时继续交叉核对；
缺少可比较字段时保留明确的 unavailable，不用默认值补齐。

当前计划包含多成员联盟或 D4 声明 `commit_required=true` 时，审计要求当前 D4 决策中
存在唯一对应提交，状态为 `committed/executing`，required 与 acked 成员闭合、
missing 为空、`atomic_committed=true`、`execution_authorized=true`，且租约在决策时刻
有效。必需联盟目标只由同一 `global_track_id` 的多个当前 D3 资源分配，或同代 D4 的
`commit_required=true` 确定。单成员 assignment 的非空 `coalition_id` 只作为来源信息，
不触发原子提交要求。`collecting_acks` 和 `proposed` 均失败关闭。D4 即使对旧计划已经
committed，只要与最后 D3 的计划标识或版本不同，也不能替代当前计划的联盟证据。

审计器可选读取 episode 下的 `communication_dispositions.jsonl`，合同为
`scalable3d-communication-disposition-v1`。文件存在时核对逐消息 transport ID、主题、
源宿、最终处置、时间戳和重试代次；文件不存在时只报告 availability 和缺失原因，不从
summary 计数推造逐消息记录。

正式 targeted/full posterior 输出 schema 已升级到 v2。新增专项与既有正式审计测试合计
`27 passed`，D6 全量为 `1261 passed, 1 warning in 128.21s`。warning 是既有
Matplotlib `Axes3D` 环境提示。

main runtime 已按 `(plan_id, plan_version, epoch)` 冻结 D4 租约，并实现 ACK 到达重评、
有限重发、重发耗尽失败关闭、终止尾部排空且不续租，以及逐消息处置落盘。D6 已只读核对
落盘文件名、schema 和字段合同。本轮没有读取或运行新的正式保留集，也没有覆盖既有正式
制品。历史 `872/900` 仍是旧门禁结果；必须在新的 clean source 上整体重跑 900 项，再由
D6 v2 给出新结论。

## 2026-07-30 D4 v7 来源独立外部评价盲审

D6 新增版本隔离的 v7 审计器、固定哈希配置、命令行入口和 11 项专项测试。审计器只使用
冻结标签数据、v7 低层模型加载器、同快照确定性 R0 规则、残差边解码、确定性投影和干预
不变量逐帧重建动作；D4 v7 高层评价器调用数为 0，D4 summary 只在重算结束后参与对账。

输入为 M16N24、8 区域、64 episode、128 帧，seed 为 `5216-5279`。独立重算结果为：

| split | 样本 | 规则正/负 | 原始激活 | 转移变化 | 精确正动作 | 负类精确 R0 | 错误边/虚假转移 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| train | 90 | 24/66 | 10 | 3 | 0 | 63 | 3/3 |
| validation | 20 | 9/11 | 0 | 0 | 0 | 11 | 0/0 |
| test | 18 | 9/9 | 0 | 0 | 0 | 9 | 0/0 |

规则正类精确动作召回为 `0/42`。聚合 actor-derived positive 分母为 3，精确命中为
`0/3`；validation 和 test 的该分母均为 0，相关比率保持 `unavailable/null`。错误方向、
错误数量、投影拒绝、干预不变量失败和原始 R0 完整动作元组偏差均为 0。投影后动作元组
变化 3 帧，原因是错误转移进入投影后的配额联动。

D6 重算的 JSONL 与 D4 JSONL 逐字节相同，SHA-256 均为
`7785ded96360869edfb694c425321fa3323450cf1624607b53edf5d3eca6a5cd`。
D4 CSV、summary、input integrity、observable overlap 和 artifact manifest 已独立核对，
未发现字段或绑定不一致。raw source、labeled export、labeled dataset、冻结 v4 和 v7
候选五棵输入树在审计前后保持不变；D4 评价树也未变化。

模型拟合、检查点更新、阈值调整、置信校准、输入或候选修改、注册、准入、正式留出和既有
评价 payload 读取均为 0。审计执行通过不代表候选通过：v7 结论为 `failed_closed`，
candidate unregistered、admission closed、rule fallback required；置信校准、正式留出、
运行预检、D3、D7、降级、接管、联盟、控制和物理权限全部为 false。

完整输出位于
`outputs/d4_v7_source_independent_external_audit_m16n24_20260730/`，跟踪版格式化报告与
紧凑结果分别为 `docs/D4_V7_SOURCE_INDEPENDENT_EXTERNAL_AUDIT_CN.md` 和
`docs/D4_V7_SOURCE_INDEPENDENT_EXTERNAL_AUDIT_RESULT_20260730.json`。输出目录内完整
JSON、split CSV、逐帧 JSONL 和中文报告 SHA-256 分别为
`064002af52617a8cbe35f55acf3c82c8c26b0ef0a9fbe9a5b608eae44e6ca176`、
`3210d4dc7d66196aebdb1ac9762f7ba0f939ddab708b5bc8efdd31a478b89907`、
`7785ded96360869edfb694c425321fa3323450cf1624607b53edf5d3eca6a5cd` 和
`ba5430744f600d2e817112cb965aca33c84c6741416a482228df67216aa291eb`。
专项测试为 `11 passed, 1 warning in 4.65s`，D6 全量回归为
`1234 passed, 1 warning in 126.73s`。warning 是既有 Matplotlib `Axes3D` 环境提示。

## 2026-07-30 D4 v6 来源独立外部评价盲审

D6 新增
`d4_v6_source_independent_external_audit.py`、固定哈希配置、命令行入口和 8 项专项
测试。审计器直接读取冻结标签数据、v6 bundle/manifest、D4 JSONL/CSV 和完整性制品；
不调用 D4 高层评价函数，也不把 D4 summary 当作指标来源。D6 从冻结模型重新推理
M16N24、8 区域、64 episode、126 帧，seed 为 `4016-4079`。

审计固定 source clean commit
`ed9e086ea8cf5c2138035f710cf4deb3e4a2801e` 和 exporter clean commit
`9bdbe31dee34907525eabc9cf278e0d11f7dd88a`。训练 `0-99`、正式 holdout
`1000-1019`、旧设计与评价 `3000-3039`、pilot `4000-4015` 和本次独立评价
`4016-4079` 两两无交集。source、labeled export、labeled dataset、冻结 v4、v6
候选和 D4 评价树在审计前后摘要一致，`input_mutation_count=0`。在线 truth、旧评价和
正式 holdout 读取均为 0。

独立重算结果为：

| split | 样本 | 规则正/负 | raw/projected transfer | 精确正动作 | 负类精确 R0 | invariant failure |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| train | 89 | 24/65 | 0/0 | 0 | 61 | 6 |
| validation | 20 | 9/11 | 0/0 | 0 | 9 | 6 |
| test | 17 | 9/8 | 0/0 | 0 | 7 | 3 |

规则正类精确动作召回为 `0/42`，属于分母可用的 0。actor-derived positive 分母为 0，
对应比率保持 `unavailable/null`，不得填 0。负类精确保持 R0 为 `77/84=0.916667`。
错误方向、错误数量、错误边、虚假转移和投影拒绝均为 0。15 帧节点动作差异因缺少对应
转移而未通过干预不变量。

冻结 v4 train+validation 的 425 帧形成 251 个唯一在线可观测键，外部 126 帧形成
94 个，精确重合为 0。键不含 seed、episode、目标标签或 truth。D6 重算的 126 条 JSONL
与 D4 JSONL 文件 SHA-256 完全相同，均为
`771826bff66d3ba601d0ffecc95f7ab9faf416826898319de7b9f1669020c7c5`；
D4 summary、JSONL、CSV 与 D6 重算不一致时均失败关闭。

v6 没有置信校准器，manifest 中的 0.60 未被应用。candidate unregistered、
admission closed、rule fallback required；置信校准、正式 holdout、runtime preflight、
D3、D7、接管、联盟和控制权限全部关闭。当前候选不能继续进入置信校准，下一门是另立
actor 版本并在全新未见数据上取得非零且充分的精确正动作命中。

完整输出位于
`outputs/d4_v6_source_independent_external_audit_m16n24_20260730/`，跟踪版报告为
`docs/D4_V6_SOURCE_INDEPENDENT_EXTERNAL_AUDIT_CN.md`。JSON content/file、split CSV、
逐帧 JSONL、中文报告和 `SHA256SUMS` 文件 SHA-256 分别为
`771ed844ab3364fde4ed25217ffd45b7fe04f300ffb8fe4bd2df5ec99d1f25e1`、
`d7c611d2cd7071d98663b62da451ebeecdeb4d327bcbe2bff95277d8041d39dc`、
`db1b3973e6ff50681caff20695649064f6a10345ffc68ad5e28ebf651405a379`、
`771826bff66d3ba601d0ffecc95f7ab9faf416826898319de7b9f1669020c7c5`、
`b123db5c02dd8d196cefab138d9afb67968f915fa6ec05544c97708e984134b7` 和
`aa58c178cf947eb3957a54ba43fa6dc4f2ac9991fd03907b7867a3064e94369c`。
专项测试为 `8 passed, 1 warning in 5.20s`，D6 全量为
`1223 passed, 1 warning in 139.78s`。warning 是既有 Matplotlib `Axes3D` 环境提示。

## 2026-07-29 D4 v5 来源独立外部评价

D6 新增只读审计入口
`d4_v5_source_independent_external_audit.py`、固定输入配置、命令行脚本和逐 split
CSV。输入固定为 clean commit
`63987592c216fbdb7e03d77183afc6e9f15748a2` 生成的 M16N20 数据：
32 个 episode、63 帧、16 个目标、20 个资源，独立评价 seed 为 `3008-3039`。
训练 seed `0-99`、正式 holdout `1000-1019`、设计 pilot `3000-3007` 和独立评价
`3008-3039` 两两无交集。

审计逐项复核 source manifest、labeled dataset/split、source artifact、external
evidence、label audit、v4 actor 和 v5 calibrator 的文件与内容摘要。来源 manifest 文件
SHA-256 为
`af12051917cfe9eedfc8587c953599112db62858e4b01820a16ddd5b0a10231d`；
labeled dataset/split 为
`ed2fd4b1a4d50ec80e5abdaa35a1470cec03d419665ae0e08b7c4339e9b8887e` /
`cdaa40241195516eb1679f6ed0a8179f3d2365c9768f9ef9a44b6f85fabcefb6`；
source artifact、evidence 内容和 label audit 内容为
`ccf327717a293f63b5655e978202ff720f20c74bfd8ae401f2233cc590bb753a`、
`1d9cfa165f4fe24fa3881d66b73c0ed14f3902dd9f901c29d29fa7d6dae60191` 和
`8798bd28037a7c52abc972e9a13551525e68eeb590d49e497b0db6cd31800336`。
审计开始前及全部加载、评分和 observable key 重合计算结束后，D6 分别重算 source、
labeled export、labeled dataset、v4 actor 和 v5 calibrator 完整文件树。五项 before/after
摘要逐项一致，`input_mutation_count=0`；任一摘要变化均以
`audit_input_mutated_during_execution` 失败关闭。

D6 独立重建可观测图键、冻结 actor 池化特征、k=11 逆距离评分和动作签名匹配。旧 v4
TRAIN+VALIDATION 为 425 帧、251 个唯一键；新外部数据为 63 帧、41 个唯一键，exact
重合为 0。外部分片为 train/validation/test `43/10/10` 帧，规则安全正动作分别为
`1/1/0`。冻结 actor 没有输出与这两个安全动作签名一致的可执行动作，因此
actor-derived positive 为 `0/0/0`。63 个评分均有限且均为 0，固定 0.60 门通过数和负类
误接收均为 0，规则回退为 63/63。

正类召回的 actor-derived denominator 为 0，指标写为 `unavailable/null`，不写成 0。
本轮支持来源独立负类拒绝，不支持正类泛化或准入。external test 的 10 帧是非正式开发
test；main 此前读取 10 帧和 D6 本轮读取 10 帧均如实记录。正式 holdout
`1000-1019` 读取为 0。没有拟合、调门、改 split、运行 runtime preflight、D3 successor、
D7 权限测试或在线控制。

输出位于
`outputs/d4_v5_source_independent_external_audit_m16n20_20260729/`。JSON content/file、
CSV、中文报告和 `SHA256SUMS` 文件 SHA-256 分别为
`cb9b9e2dc9481c9ac83c55158279f5d5b3f2c5ae2d7f12043ba851ed6fbc7a06`、
`f1f8047b2b858594425dd2e7e5e216025623e49d6e34bfe0f4aaa4790624aa6e`、
`8e74ed1d35f75d7f7e30585a6609ed35398300d353bbcea8fd59f703eec4a7e2`、
`7fabd3a0602a245aa644fdcc9f1582d94db5d1b81c20d954e7d379b38767426f` 和
`33d4e867390d986ac359ae5f90981a894cdaf17a4f91773cef9d90889fd6ac82`。
逐 split CSV 由 `DictWriter` 显式使用 LF，当前为 4 个 LF、0 个 CR，且不存在空格或制表符
行尾。重生制品中的 `audit_repository_head` 为
`b3147fcae56cb1ff1e67cdd1bd8dad353d567460`；冻结来源提交仍为
`63987592c216fbdb7e03d77183afc6e9f15748a2`。
候选状态保持 unregistered、admission closed、rule fallback required，生产、D3 和 D7
权限继续关闭。专项测试为 `5 passed, 1 warning in 2.33s`，D6 全量回归为
`1215 passed, 1 warning in 123.70s`。warning 是环境中的 Matplotlib `Axes3D` 多版本提示，
不影响本次哈希、Torch 推理或 JSON/CSV 输出。

## 2026-07-29 D4 v5 置信校准候选独立审计

D6 新增 `d4_v5_confidence_candidate_audit.py`、固定配置、CLI、专项测试和原子报告输出，
对未注册候选 `region_resource_a2_confidence_knn_shadow_v5` 执行只读、失败关闭审计。
调用方固定 manifest file/content、state、summary、gate 和 builder source 六个外部锚；
候选自身的 content hash 和 artifact map 只作为待核声明，不能替换信任根。候选四个文件
逐项复哈希，普通 artifact 篡改和同步修改 payload、artifact hash、content hash、manifest
的自重签攻击均被外部锚拒绝。

审计同时复核冻结 v4 候选 180 文件树、v4 manifest/model/dataset/split、四个 v4 实现文件和
v3 registry 8 文件树。v4/v5 登记常量均为 `None`，对应 registry 路径不存在。候选、
summary 和权限合同中的生产、D3、D7 权限全部为 false。TEST 文件只参与 v4 树字节完整性
哈希，不做 payload 语义解析；D6 的 TEST/formal holdout payload read/fit 均为 0。

D6 不信任候选 summary 指标。从冻结 v4 actor 和 TRAIN 350 条、VALIDATION 75 条记录重建
池化消息传递 latent、TRAIN 标准化状态和 k=11 逆距离评分。冻结模型和候选 state 的实际
latent 维数均为 24，重建均值、标准差和 350 条归一化特征与 state 的最大差均不超过
`1e-12`。D4 报告和任务口径写为 64 维，与冻结制品不一致；D6 未补造 64 维结果，将其列为
严格 profile blocker。

固定 0.60 开发门独立复算结果为：

| split | 正/负 | 正类召回 | 负类特异度 | 最小正裕量 | Brier |
| --- | ---: | ---: | ---: | ---: | ---: |
| TRAIN | 58/292 | 1.000000 | 1.000000 | 0.400000 | 0.000000000 |
| VALIDATION | 13/62 | 1.000000 | 1.000000 | 0.209319 | 0.000484791 |

完整开发门通过，但 TRAIN 评分把 350/350 个被评样本自身放入近邻库。逐样本留一后的召回、
特异度和 Brier 为 `1.000000/0.993151/0.006652708`；按 raw observable key 或 latent exact
key 整组留出后均为 `0.965517/0.958904/0.037610440`。TRAIN 的 raw/latent 分组均为
229 组，其中 115 组含副本，最大组大小 3。

VALIDATION 独立重算得到 42/75 raw graph exact overlap、42/75 latent exact overlap；
非 exact 且距离 `<1e-3` 为 20 条，`[1e-3,0.1)` 为 10 条，`>=0.1` 仅 3 条，最近邻标签
75/75 一致，13 个正类中 12 个 exact。去除 exact 后仅余 1 正/32 负；距离 `>=1e-3`
仅余 1 正/12 负；距离 `>=0.1` 的 3 条均为负类。固定最小分母为 5，分母不足的 recall、
margin、specificity 或 Brier 明确写为 `unavailable`，不补 0。

四层结论分别为：artifact 哈希、v4/v3 绑定和实际 24 维算法复算通过；同源重合数据上的固定
开发门通过；独立验证和泛化不可用；正式准入关闭。状态保持
`development memorization baseline`、candidate unregistered、admission closed、
rule fallback required，不运行 formal holdout/runtime preflight，不授予 D3/D7 权限。

机器可读 JSON、中文报告和 `SHA256SUMS` 位于
`outputs/d4_v5_confidence_candidate_independent_audit_20260729/`。JSON content/file
SHA-256 为
`7317fc0c19a8c2f149c3f7193e725db9470851526d329c6f897ee2da8762b1d9` /
`c12fdd740120193e071452abdce487b05d79f230ac907ebc7ad7c15bcbeb2bac`；
中文报告/`SHA256SUMS` 文件 SHA-256 为
`e56faa01c04e2010c577d7f1c810ce0b8d9f5eed3b42b17d0cd35c8638700abf` /
`0aa7921cb2643b1acf792377b37dbee5e7283de6b29eba8a77aca4e7288f3cab`。
专项测试为 `5 passed, 1 warning in 12.56s`；D6 全量回归为
`1210 passed, 1 warning in 119.78s`。

## 2026-07-29 D4 v4 未注册候选独立审计

D6 新增只读审计器 `d4_v4_candidate_audit.py`、CLI、固定输入配置和真实候选负例测试，
独立复核未注册候选
`region_resource_a2_executable_transfer_shadow_v4`。外部信任锚固定为 clean source
commit `fd857457bb27a4a709a7c4937e22ebe1cbd7f848`、manifest content SHA-256
`4f3e973597469d394a594bec3dd7d2c16b24e80d2e97ba45f718d9ef8397e116`、model state
SHA-256 `33a28060f11277a549b90d2f2f365962fec057b2bfb50a70ab5a422059cb9fe5`
和 dataset SHA-256
`b31fc43f3d3cff34ee53f2b2c33ece0b06d7624e46e26a36c4aa834135e7fb8c`。
候选树共 180 个文件；manifest 之外的 179 个 artifact 全部逐项复哈希，目录、文件模式、
symlink/特殊文件和清单闭包均受审。4 个 source implementation 文件同时与 clean commit
blob 和当前只读实现逐字节一致。

外部 composite evidence、source derivation、export summary、dataset manifest、split 和
170 个 train/validation episode 完成交叉绑定。D6 只加载 train 和 validation payload：
train 为 70 seeds、140 episodes、350 samples，目标正/负 `60/290`；validation 为
15 seeds、30 episodes、75 samples，目标正/负 `15/60`。test 只核对 manifest 中的
15 seeds、30 episodes、74 frames；候选 test payload 文件、builder/D6 payload read、fit
和 weight fit 均为 0。truth identifier、future outcome 和 reward 的可用或使用计数均为 0。

actor checkpoint 独立重算为 epoch 107。train 正/负召回为
`0.966667/0.951724`，validation 为 `0.866667/0.966667`；actor 正类样本权重
`4.833333` 和非零边权重上限 `32` 只由 train 库存推导。confidence checkpoint 独立重算
为 epoch 66；固定 0.60 门的 train/validation 正类召回分别为
`0.206897/0.307692`，负类特异度均为 `1.0`，Brier 分别为
`0.186847275/0.186468779`。最小越门裕量仅 `0.000504935`，最接近门的 train
负类仅低 `0.000029838`，结论保留薄裕量告警。

development fixture 的 confidence 为 `0.602367163`，高于门限
`0.002367163`；它固定分类为 `training_domain_smoke_only`，generalization 和 formal
validation evidence 均为 false。v3 registry 的 8 文件树摘要仍为
`07c770b05ffc70f190cd8b45d762d579857747e0efb12b472a2354ee5aeaa93a`；
v4 注册常量全为 `None`，目标 registry 路径不存在。全部逻辑权限为 false，候选保持
unregistered、shadow-only、admission closed；formal holdout 与 runtime preflight 均未完成。

最终治理收紧后的 `admission_blocker_codes` 为
`candidate_unregistered`、`formal_holdout_not_completed`、
`runtime_preflight_not_completed`、`development_fixture_train_domain_smoke_only`、
`confidence_positive_recall_low`、`confidence_threshold_passing_margin_too_thin` 和
`runtime_outcome_and_benefit_unavailable`。这些 blocker 不改变开发完整性通过状态。

机器可读 JSON、中文报告和输出清单位于
`outputs/d4_v4_candidate_independent_audit_20260729/`，状态为
`pass_development_integrity_only_admission_closed`。篡改普通候选 artifact，以及修改权限
声明后重算候选自有 manifest content hash，两类负例都由外部锚失败关闭。专项测试
`3 passed, 1 warning in 4.97s`；2026-07-29 D6 全量回归为
`1205 passed, 1 warning in 112.59s`。本次没有运行正式 holdout、preflight 或候选登记，
也没有改变任何权限。

最终审计时间为 `2026-07-29T23:15:40Z`。JSON content/file SHA-256 分别为
`3a4ed311c55e6419d3db1b3ba830f0ea6ce22c638eb363aa03c3f4510fdcd7c2` /
`e225a1a16ae2b1988ce5ea34b3cceaa30d7c829004663368ecc6514de3eb3887`；
中文 Markdown 和 `SHA256SUMS` 文件 SHA-256 分别为
`16a2e5a4efacd4b58b22b7b9dd9d0d632cedb3e7b8d6cc6d55a0dce954870fe0` /
`6ee4e7822800401b531acc93f03f105fc1ff02a77c1842fe1d36546bc9500af6`。

## 2026-07-29 D4 readiness-v3 v2b 隔离审计

D6 使用两个只读入口审计最终 v2b：紧凑 10-seed 配对审计和 seed 2007 完整 episode
链路重放。两者均先固定根 `SHA256SUMS` 外部摘要。v2 manifest 还必须携带精确
`source_provenance`，包括提交、dirty 状态、双臂 episode manifest 摘要、11 个关键实现
文件摘要及实现集合摘要。完整 episode 允许动态文件清单，但目录内每个文件都必须被根
清单绑定。

最终 compact anchor 为
`4077379face18c036b1cec3fe62e158c9cedb2e42da0d4e5c1573090b2da7745`。
20 目标/20 资源、8 区域、seeds 2003-2012、3.2 秒批次中，10/10
通过输入完整性、初态/外生配置一致声明和候选推理门；1/10 形成 D3 后继及开发 ACK，9/10
为 `regional_hint_no_executable_successor`。已声明的拦截数和最小距离具有 10/10 覆盖，
两臂逐 seed 完全相同，因此有界非退化可用且通过。全批无拦截、无最小距离改善，正收益
保持 unavailable/false。

最终 full anchor 为
`a061b2d69c98e07d506c28ce322761c5968417ac08ef607c1775a34f90c3d72c`。
重生后的 D6 full-chain 输出 `SHA256SUMS` 摘要为
`6201eed6f7bcb6396c33631fe484d452cc050c630b5fb9783c11fde0ecf00199`。
control/treatment 均独立重算为 4 ACK、77 bindings、1 次同身份 refresh；treatment 有
1 条 D4 regional applied ACK。source sequence/hash 全部通过，在线真值使用为 0。
后继首次发布和 refresh 的严格执行签名均为
`sha256:00f71e0f06063c042e224af82faf19ec59d5319ac0c5cfb5ced3afe85576b4ad`，
epoch 1 和 lease 5.85 秒保持不变，确认原 D6 拒绝正确且 D3 refresh 已修复。

该后继的 19 条 D7 指令和非 hold 控制均同链。冻结 persisted runtime join 及默认
`evaluate_runtime_plan_outcomes` 语义保持原生 18/19，二者除可迁移暂存路径外逐字段一致。
full-chain audit 另以显式 evaluator-only
`offline_confirmed_unmatched_double_anchor_v1` 桥接
`GT3D-000004` 的 1 个 confirmed/unmatched 空档帧：前锚
`0.833472220197s`、空档 `1.035192721089s`、后锚 `1.236148794089s`，锚间隔
`0.402676573892s <= 0.9s`。因此统计为原生 18 + bridge 1 = effective 19/19。
该策略默认关闭，仅支持 `d2.scalable3d_identity_evaluation.v2`；不写回 D2、不改
`global_track_id`，`online_exposure_allowed=false`。双锚有效上限为
`min(configuration.lineage_time_window_s, 0.9s)`，调用方配置不能放宽 D6 的 0.9 秒硬门。

source 与 successor 的资源—目标及联盟绑定仍完全相同，因此实际候选动作不可辨识，正收益
仍为 unavailable/false。开发 ACK 不产生生产权限，admission 继续关闭并要求规则回退。
2026-07-29 验证覆盖 seed 2007 的 1 个完整双臂 episode、19 条 applied-chain D7 绑定及
全部 D6 测试；`pytest -q research_modules/d6_evaluation_metrics/tests` 为 `1196 passed`。

## 2026-07-28 D4 A2 来源、分布、动作与采用审计

D6 已为 D4 current-lineage A2 候选增加只读可信来源适配器。当前信任锚固定为 clean
commit `b0d498d9e76e19e9045e127b6dae26ea164b3fa4`、候选清单文件 SHA-256
`7cc10ad770bd95fcb813dbf3d16b17040ec5f41f80fe0dc53e3e291a32f4de64` 和权重
SHA-256 `fd1b9c4cf7580083fadc04a70b87aa6439930eba764a970279611ccc57f30047`。
reference 和测试只从受版本控制的
`research_modules/d4_distributed_fallback/model_registry/region_resource_a2_current_lineage_development_v1/`
读取原始字节，不再依赖被忽略的 `outputs/`。适配器重新解析清单、实现摘要和训练摘要，
复算七项制品摘要，加载模型包，检查参数有限性、数据划分使用和全部 false 权限。通过时只得到
`model_source_verified=true`。候选生命周期仍为 `development/shadow`。

readiness 合同升级为 v3，新增独立门
`runtime_distribution_compatible`。运行分布 reference 只引用原始 D4 shadow JSONL。
D6 使用 D4 公共数据对象逐条复载，并按总量和 seed 重算：

```text
audited_snapshot_count
finite_record_count / nonfinite_record_count
compatible_snapshot_count / feature_ood_snapshot_count
model_action_count / missing_model_action_count
rule_fallback_count
feature_ood_counts
candidate_binding_sha256
```

来源、分布、影子动作和实际采用保持四层分离：

1. `model_source_verified` 只验证来源、权重、实现和训练边界；
2. `runtime_distribution_compatible` 只检查存在受审样本、记录有限、特征无 OOD 和分母一致；
3. 模型动作、非零干预和规则回退是独立 rollout 诊断，不改变分布兼容布尔值；
4. treatment 只由严格采用、D3 后继、ACK、物理窗口和独立 R0 证据建立。

因此，分布内 no-op/hold 或规则回退可以得到
`runtime_distribution_compatible=true`，但不能形成 treatment。D6 确定性合同 fixture 使用
5 资源/5 目标、2 区域和 6 帧，结果为 6/6 `feature_ood`；该 fixture 的模型动作 0、规则
回退 6 作为单独诊断保留。它不是 main 运行证据。

main 实际预检另有两组：5 资源/5 目标、2 区域、seed 2000 的 3 帧为 3/3 OOD；
200 资源/200 目标、8 区域、seed 2001 的 2 帧为 2/2 OOD。两组均说明当前候选运行分布
不兼容，但不使用 D6 fixture 的动作和 fallback 计数。

新增 `d4_a2_paired_shadow_audit.py` 和
`scripts/run_d4_a2_paired_shadow_audit.py`。逐 seed 只有同时具备执行前冻结注册、相同外生
配置但不同 episode/日志、可辨识非零模型干预、D3 严格后继、runtime/owner/coalition
ACK、确认后物理窗口、truth-use=0、有限状态和完整相等指标分母，才成为可审计 treatment。
正式聚合至少需要 20 个预注册未见 seed。规则 fallback、no-op、普通规则重规划和
development train/validation 诊断均不能进入 treatment 或非退化分母。

新增分布内 no-op/规则回退回归，验证分布门通过而 rollout 前置条件、采用和配对收益仍
unavailable。定向测试为 `38 passed, 1 warning in 6.10s`，D6 全量为
`1144 passed, 1 warning in 108.47s`。warning 是既有 Matplotlib `Axes3D` 环境提示。
当前仍缺至少 20 个真正预注册未见 seed 上的兼容运行记录、非零模型动作、完整采用/ACK/
物理窗口、独立 R0 和完整指标分母。D6 不产生准入、辅助、权属、分配、接管或控制权限。

## 2026-07-28 G1 模型来源可信适配器

readiness v2 现有两类可信来源适配器：

1. `frozen_unseen_seeds` 继续通过 canonical seed auditor 重算；
2. `model_source` 新增
   `d6.learning-run-d5-g1-model-source-reference.v1`，当前只覆盖 G1 的
   `d5_graph` 组件。

模型来源 sidecar 只列出正式 external audit v2、正式 post-assembly audit v2、D5 v5
bundle、两套 `SHA256SUMS`、held-out、paired-shadow 和 paired lineage 的相对路径与文件
SHA-256。它不携带 `audit_passed`、formal、模型身份或权限断言。适配器在调用方显式指定的
`artifact_root` 内逐文件解析和复哈希，并执行以下重算：

```text
reference sidecar
  -> 固定 G1/d5_graph 组件覆盖
  -> 固定制品布局与正式候选 SHA-256 信任锚
  -> audit_d5_g1_external_evidence()
  -> persisted/embedded external audit 精确一致
  -> audit_d5_g1_post_assembly_bundle()
  -> persisted post-assembly audit 精确一致
  -> v5 模型指纹、运行时实现谱系和两级内容摘要交叉一致
```

2026-07-28 使用显式外部根
`/tmp/MSM-d5-g1-formal-evidence-8d5e02e-20260727` 完成一次只读正向验证。clean source
worktree 位于同级 `/tmp/MSM-d5-g1-formal-8d5e02e`。结果为
`source_class=formal_post_assembly_audit`、`component_ids=[d5_graph]`、
`audit_passed=true`，模型身份为
`sha256:7fb5db8b6099ca4da5706a3bec53ff7cd634e8bd267c036ce3ee4ee4bf71ca71`。
适配器没有扫描 `/tmp`，也没有修改该证据树；路径由
`configs/d5_g1_model_source_reference_7fb5db8b_20260728.json` 明确列出。

仓库目录本身只保留审计输出、配置和 reference，不包含上述 182 MiB 原始证据树。若
`artifact_root` 指向仓库根，13 项原制品引用会保持 unavailable；不会用仓库内 audit JSON
替代原始生产链。只有显式外部根或完整 fixture 才能形成 model-source 正例。

仓库根缺少的 13 个 reference 目标如下。这里列的是 sidecar 约定位置，不表示同名文件在其他
目录出现时可以被自动采用。

```text
d6_external_audit_input.json
d6_external_audit/d5_g1_external_audit.json
d6_external_audit/SHA256SUMS
d6_post_assembly_input.json
d6_post_assembly_audit/d5_g1_post_assembly_audit.json
d6_post_assembly_audit/SHA256SUMS
g1_assist_v5_7fb5db8b_d6_cbd6c72b/manifest.json
g1_assist_v5_7fb5db8b_d6_cbd6c72b/weights.pt
g1_assist_v5_7fb5db8b_d6_cbd6c72b/SHA256SUMS
g1_assist_v5_7fb5db8b_d6_cbd6c72b/evidence/heldout_evaluation.json
g1_assist_v5_7fb5db8b_d6_cbd6c72b/evidence/paired_shadow_report.json
g1_assist_v5_7fb5db8b_d6_cbd6c72b/evidence/paired_episode_lineage.jsonl
g1_assist_v5_7fb5db8b_d6_cbd6c72b/evidence/d6_external_audit.json
```

G1 模型来源软件门由此关闭。G1 的实际采用、运行确认、物理窗口、唯一同键 R0、运行成对
非退化、truth-use、有限状态和外部权限仍 unavailable。external/post-assembly 中的
`online_truth_feature_count=0` 只覆盖该模型证据链，不提供 readiness truth-use 所需的同一
运行采用谱系与受审记录分母；finite-state 也没有受审值分母。因此两门没有顺带接入。
C1/F1 需要 D3、D4、D5 图关联和 D5 主动视觉四组件，只有 `d5_graph` 时按组件覆盖不足拒绝。

新增专项 14 项通过；与 readiness v2 原测试合并为 32 项通过。攻击覆盖 sidecar 自签事实/
权限断言、完整但未登记的替代模型、嵌套原制品篡改、路径逃逸、符号链接、摘要错配、schema
错配、模型身份错配、组合变体缺组件和重签权限升级。所有 readiness 输出中的模型晋级、
分配、接管、相机和控制权限继续为 false。仓库根失败关闭用例同时证明适配器不会自动发现
`/tmp` 外部树。完整 D6 回归为 `1138 passed, 1 warning in 126.65s`。

## 2026-07-27 正式学习运行准备度审计

D6 新增只读聚合器 `learning_run_readiness.py`，统一检查
`G1/A1/A2/A3/C1/F1` 六个学习变体。v2 输入 manifest 的每个 gate 只携带相对制品路径和
文件 SHA-256，不再接受调用方自报的来源类别、formal 标志或 facts。聚合器以 manifest
所在目录为只读根目录，拒绝绝对路径、`..` 路径逃逸、目录、缺文件、符号链接出口、文件
摘要错配和未知 schema。文件只读取一次，文件摘要通过后再校验内部内容摘要，并从原始记录
重算 gate facts。

输入、输出和 consumer schema 分别为 `d6.learning-run-readiness-input.v2`、
`d6.learning-run-readiness-audit.v2` 和
`d6.learning-run-readiness-consumer.v2`。当前只接入冻结未见 seed gate。它通过
`d6.learning-run-canonical-seed-source-reference.v1` 引用既有训练 seed 注册表、共享 split
注册表及 D3/D4/D5 四个数据集 manifest，并调用现有
`audit_canonical_seed_split_readiness()` 重读和重算。该 sidecar 只保存六个原制品路径和
文件摘要，不携带通过断言。

其余九类 gate 没有受信 adapter，全部保持 unavailable。上一版十类
`d6.learning-run-*-evidence.v1` 通用 wrapper 不再受支持，公共 builder 已移除。聚合器不扫描
输出目录，不加载策略进入控制链，也不启动 900-cell 或多 seed 正式实验。

每个变体分别报告十类门：模型来源、冻结未见 seed、可辨识实际采用、运行确认、物理窗口、
唯一同键 R0、成对非退化、在线真值使用、有限状态和外部权限。缺失输入保持
`availability=false`、结果值为 `null`，并输出稳定原因码。证据存在但不满足条件时保留
`availability=true`，同时将 `passed=false`，例如 A1 实际采用但最终绑定没有变化、A2
采用记录只是无操作、A3 候选与 R0 未完整一一配对。

当前只有 seed 来源类别和 formal 状态由既有严格审计链产生。模型、采用、运行确认、物理
窗口、同键规则基线、成对指标、真值使用、有限状态和外部权限不接受新 wrapper，自报记录
不能提升可用性。C1/F1 还必须同时具备 D3、D4、D5 图关联和 D5 主动视觉四个组件的模型、
采用和确认，缺一项即失败关闭。

准备度分为四层：

1. `model_readiness` 只由模型外审和冻结未见 seed 决定；
2. `runtime_evidence_readiness` 汇总采用、确认、物理、R0、非退化、真值隔离和有限状态；
3. `formal_evidence_readiness` 合并前两层，不读取磁盘或权限；
4. `execution_startability` 再加入外部权限和存储资源。

D6 不生成权限。即使前三层全部通过，未提供独立外部权限决定时仍不能启动。固定存储保护线为
`20 GiB`（`21474836480` 字节），输入不能降低该值。2026-07-27 对当前文件系统的只读观测为
可用 `14139191296` 字节，约 `13.168 GiB`，且没有第二个可用于正式输出的大容量挂载点。
因此存储原因固定包含 `formal_runtime_disk_below_20_gib_threshold` 和
`alternate_large_capacity_mount_unavailable`。该结论只阻断执行，不能改写模型或算法
readiness。

当前证据边界如下：

- 既有独立报告记录 G1 正式 v5 模型、外部审计和 20-seed held-out/paired-shadow 模型证据，
  但 readiness 尚未接入对应原制品 adapter；该 gate 仍 unavailable。G1 也没有实际
  G1 运行采用、运行确认、物理窗口、运行同键 R0 或运行成对非退化。paired-shadow 不替代
  这些运行证据。
- A1 当前 development/shadow 模型没有生产准入。保留 seed 对照虽然出现 20/20 代价矩阵变化，
  最终绑定变化为 0/20；运行确认、物理窗口和运行成对非退化仍不可用。
- A2 的 20-seed 开发候选均为无操作，可辨识区域干预为 0。单 seed 受约束开发适配器可走通
  后继计划和物理窗口，但被正式收益装配器明确拒绝，不能作为模型采用证据。
- A3 最新开发复跑为 492 个候选、488 个可配对、4 个通信丢包缺失；来源工作树、未见 seed
  和完整落盘清单未形成正式证明，因而不能作为正式配对或非退化证据。
- C1/F1 依赖上述四个学习组件同时就绪。当前组件准入、复合采用、复合运行确认和正式同键
  配对均未闭合。

专项测试 18 项通过。正例使用既有六类 seed producer schema 的临时 fixture，并经过现有
canonical auditor；攻击用例构造十类摘要完全正确的旧通用 wrapper，六个变体的
`formal_evidence_readiness` 仍全部 unavailable。其余负例覆盖原制品和 sidecar 篡改、摘要
错配、未知 schema、缺文件、内外层路径逃逸、目录、缺制品根、输出权限与摘要语义篡改。
全量验收结果见本节后续最终记录。测试没有启动正式矩阵或产生大制品；正向 fixture 不构成
任何变体已有正式证据。

## 2026-07-27 A1/A2/A3 实际采用与同键配对审计

`strict_learning_adoption_audit.py` 保持只读。旧输入
`d6.strict-learning-adoption-audit-input.v1` 继续兼容；显式提供
`a3_pairing_dispositions` 时使用
`d6.strict-learning-adoption-audit-input.v2`。输出和 consumer 分别升为
`d6.strict-learning-adoption-audit.v4` 与
`d6.strict-learning-adoption-audit-consumer.v4`。v2 是加入完整 disposition 分母后的冻结
输出；v3 增加候选物理窗口阶段细分和输出严格复载；v4 增加候选观测结果清单，明确区分
“证据可审计”和“目标可见或收益为正”，避免在旧版本上静默增加结果字段。
D6 不运行策略、不发布计划、不移动相机，也不授予模型、分配、降级或控制权限。

每个变体独立输出实际采用、候选物理窗口、同键规则参考和收益审计输入四级可用性。新规范字段为
`benefit_auditable_count`，旧 `auditable_benefit_count` 作为等值兼容别名保留。四级输入完整时
状态只写 `audit_input_available`；`positive_benefit_claimed` 和
`non_degradation_claimed` 始终为 false。没有结果指标时不能从窗口完整性推导正收益或非退化。

A2 现在按 schema 两遍处理。第一遍严格重建旧
`RegionResourceSafeAdoptionEvidence`，按原始 `content_sha256` 建立唯一来源索引。第二遍读取
`RegionResourceA2BenefitAuditInput` 或其 batch，使用 wrapper 的
`safe_adoption_evidence_sha256` 查找唯一旧记录，再调用 D4 公开
`validate_region_resource_a2_benefit_audit_input()`。被 wrapper 引用的旧记录只作来源，不重复
计数；未被引用的旧记录继续按兼容路径报告实际采用和物理窗口，R0 与收益保持 unavailable。

旧记录中的拒绝态分为投影前 `candidate_rejected` 和投影后
`safe_adoption_rejected`。后者只有在 preparation、学习建议投影和拒绝原因完整，同时 D3
后继计划、运行确认、权属确认、联盟执行证据及物理窗口全部不存在时，才作为“实际采用数为
0”审计。该记录不生成候选物理窗口、同键 R0 或收益输入；缺少拒绝原因、投影字段篡改或夹带
后续执行证据均失败关闭。无联盟要求时 D4 的 `coalition_commit_available=true` 表示无需联盟
提交，不等同于存在联盟执行证据。

D6 不信任 wrapper 汇总字段。它独立核对候选物理窗口与安全采用摘要，重算场景、场景版本、
规模、种子、逻辑窗口、窗口时长和冻结的 `paired_exogenous_config_sha256`，并检查候选与 R0
来自不同 execution arm、事件日志摘要不跨 episode、窗口不跨键复用、一个 R0 不重复配对。
D4 实际 pair DTO、batch 和 public validator 已进入共享合同，D6 正向
测试直接使用 D4 生产装配器，不再使用预留 fake validator。

A3 继续调用 D5 公共 `validate_active_vision_a3_evidence()`。D6 使用 trace 已有字段显式重算
窗口 comparison identity，不假设 trace 暴露派生属性。批次检查要求 comparison key 唯一、
候选与 R0 身份完全一致、`pairing_context_sha256` 对应冻结外生配置、候选和 R0 episode 不同，
且窗口和 R0 不重复消费。同一 episode 的多个窗口允许共享该 episode 的
`source_event_log_sha256`；同一摘要不得绑定不同 episode，同一 episode 也不得出现第二个日志
身份摘要。该口径与 main 当前 `episode_id + stream + schema` 日志身份一致。

A3 v2 输入还逐条调用 D5 公共
`validate_active_vision_a3_pairing_disposition()`。D6 要求
`adoption_trace_sha256` 唯一，每条 pairable disposition 与一条顶层 A3 paired evidence
双向对应，且 disposition 内嵌证据与顶层记录逐字段相同。输出
`pairing_disposition_inventory`，包含候选数、pairable/unpairable 数、覆盖率、全量 reason
code 计数、inventory completeness 和 paired-evidence completeness。D5
`d5.active-vision-a3-pairing-disposition.v2` 还可携带
`candidate_stage_reason_codes` 和哈希绑定的 `candidate_stage_evidence`。D6 将顶层原因与
阶段细分分别统计，输出阶段证据有/无记录数、细分原因记录数、细分原因 assignment 数、全局
细分分布和“顶层原因→细分原因”矩阵。一个候选可以同时具有确认缺失、反馈缺失、时序过期和
匿名观测缺失等多个细分原因，因此细分 assignment 数允许大于候选数；有细分/无细分记录数之和
必须等于候选数。

候选物理窗口缺失另有独立分母：`physical_window_missing_detail_scope_count` 等于顶层
`candidate_physical_window_missing` 数量，evidenced 与 unresolved 之和必须等于该分母。
D5 disposition v1 没有阶段证据，继续保留顶层原因，但对应记录计入 unresolved，不能以零个
细分原因解释为阶段无故障。未知细分枚举、重复细分、细分与绑定 stage evidence 不一致、
schema 计数不守恒或输出重载时计数被篡改均使 inventory 失败关闭。

v4 在 `variants.A3.observation_outcome_inventory` 中只读汇总已经通过 D5 公共校验器的候选
物理窗口。清单分别记录普通轨迹帧、已处理零检测帧、锁定、模糊、保持、重新捕获、分配目标
引用和可见引用数量。覆盖率由可见引用数除以分配引用数重算。D5 v2 零检测帧有分配目标时只
能贡献 `reacquire` 和 0 覆盖；无分配目标时关联与覆盖结果保持不可用。零检测帧一旦被写成
`locked`、`ambiguous` 或可见，D6 输出复载立即失败。完整观测清单仍不改变
`positive_benefit_claimed=false`、`non_degradation_claimed=false` 和全部权限为 false。

合法 unpairable disposition 可以进入原因分布，但 A3 实际采用、物理窗口、同键 R0 和收益
计数保持 unavailable。`complete_model_evidence_claimed` 固定为 false。因而只审计 152 条
pairable 记录不能写成 536 个候选的完整模型证据；完整分母必须作为 v2 disposition inventory
显式输入。阶段细分完整也不会改变该规则。旧 strict input v1 继续按 pairable 记录范围运行，
inventory 以
`a3_pairing_disposition_inventory_not_declared_v1` 标为 unavailable。

main 已用当前 v2 consumer 审计 seeds 1000-1019 的开发批次。A2 共评估 20/20 个候选，
可识别区域干预、实际采用和 A2/R0 收益审计均为 0；20 条原因均为
`identifiable_regional_intervention_missing`。这表示无操作候选没有被归因成学习采用。A2
批次 SHA-256 为
`ff3c10a089b6a94582451ae05d8a884af3a2bd7485acd4df0496442ea7e0ec55`。

A3 完整输入包含 536 条 disposition，其中 152 条 pairable、384 条 unpairable，配对覆盖率为
28.36%，20/20 个 seed 均有 pairable 子集。384 条不可配对原因均为
`candidate_physical_window_missing`。在完整清单口径下，`a3_auditable_pair_count=0`，实际
采用、物理窗口、同键 R0 和收益四级计数均为 unavailable。该批次 SHA-256 为
`455d181076553a485ff824618abc6d037a4477bb6342877d1d1e427fd28583a9`。152 条子集只说明局部
记录可配对，不能作为完整 A3 模型证据或准入依据。该冻结批次生成时没有 D5 v2
`candidate_stage_evidence`，其自身仍只能给出粗粒度物理窗口缺失原因。

main 随后以相同配置和 seeds 1000-1019 完成一次不落盘的候选阶段开发探针。536/536 个候选
均形成 stage evidence；152 条 pairable、384 条 unpairable，完整可审计 seed 仍为 0。多标签
细分为 344 条 `candidate_anonymous_observation_missing`、同 344 条
`candidate_physical_window_confirmed_missing`。剩余 40 条 unpairable 的 observation
inventory 不完整，但 stage reason 为空；D6 不补造原因，将物理窗口缺失细分记为
scope `384`、evidenced `344`、unresolved `40`、completeness `false`。运行 ACK、运行确认、
命令窗口过期、命令时序错配和相机反馈缺失均为 0。非正式摘要路径为
`research_modules/scalable_3d_simulation/docs/SCALABLE_3D_A3_STAGE_BREAKDOWN_DEVELOPMENT_20260727.json`，
文件 SHA-256 为
`1ba6040e7c3e7e3b9e7d5506dfd20cf3539ce12c5aac13cca7f02799f0cd99ef`。该探针声明
`source_worktree_clean=false`、`formal_evidence=false`、
`persisted_full_pair_inventory=false`。它只定位开发态断点，不替换上述冻结 v1 批次，不开放
A3 四级指标、模型准入或任何运行权限。

main 在 D5 零检测帧 v2 和 truth-free 相机帧事件接线后，用相同 seeds 1000-1019 做了第二次
未提交工作树开发复跑。候选数为 492，可配对 488，不可配对 4，配对覆盖率
99.18699%。候选窗口消费 329 个零检测帧，拒绝 0 个；159 个 v1 帧为 locked，329 个 v2
零检测帧为 reacquire，零检测帧没有进入 locked 或 ambiguous。4 个缺失均来自默认 1% 通信
丢包；对应 4 个 seed 将丢包设为 0 后全部配对。该统计没有持久化完整逐候选 pair inventory，
来源工作树不干净，seed 也未证明未见泛化，因此只作为开发性链路诊断。D6 不把 0 覆盖帧解释
为正收益，不开放模型、相机或控制权限。旧 536/152/384 冻结批次及其 SHA-256 保持不变。

运行时持久化文件使用
`scalable3d-learning-adoption-evidence-records-v1`。新增
`load_learning_adoption_episode_evidence()` 和
`build_learning_adoption_audit_input_from_episode_files()`，只读取调用方明确给出的
`learning_adoption_evidence.json`，逐文件校验字段、episode 标识和内容摘要，不扫描目录，也
不由 D6 自动制造 A2/A3 配对。跨文件读取时，D4 候选安全采用记录所在 episode 必须与候选
execution arm 一致，候选和 R0 episode 文件都必须显式列入输入；D5 paired evidence 的 trace、
候选窗和 R0 窗所引用 episode 也必须存在。pair wrapper 必须先由 D4/D5 公共装配器形成并且只
持久化一次。

main 传给 D6 的 `a3_pairing_dispositions` 必须保留每条 D5 原始记录及其
`schema_version`、`reason_code`、`detail_codes`、`content_sha256`。D5 v2 记录还必须原样携带
`candidate_stage_reason_codes` 与 `candidate_stage_evidence`；后者包含候选/日志摘要、命令
生效时间、确认与反馈时间、观测清单完整性、双时间戳和物理窗口状态。main 不能只传预聚合计数，
也不能用后续窗口或离线真值回填缺失阶段。D6 对 D5 v1 记录保留顶层统计并将阶段细分标为未解决；
对 D5 v2 记录调用公共 validator 后再独立重算分层统计。

A1 仍复用 D3 公共 validator。批量 candidate/selection inventory 缺公共 strict loader，
lifecycle 缺可独立复核的运行来源、物理窗口载荷和 R0 身份，这些计数继续 unavailable。
公共模块解析兼容顶层包和 `research_modules...` 两种布局，内部依赖错误保持可见。

2026-07-27 本次候选阶段细分后，strict audit 专项为 `59 passed, 1 warning in 11.75s`。新增
用例覆盖 D5 disposition v2 分层原因、D5 disposition v1 粗粒度兼容、输入/输出 JSON
round-trip、未知/重复/证据矛盾的细分原因及重算摘要后的输出计数不守恒。原有用例继续覆盖真实
D4 pair 正向输入、旧记录兼容、缺候选窗、摘要/汇总篡改、R0 重复配对、跨 episode 文件来源、
A3 trace 身份显式重算、同 episode 多窗口共享日志身份，以及投影后拒绝态的正向、篡改、缺
原因和夹带执行证据负例。新增干净子进程用例不加载 D5 测试夹具，直接构造、生成并复载当前
v3 输出。`_validate_a3_pairing_inventory_output` 入口现在位于公开输出校验器之前，D6
初始化不再依赖测试装配顺序。warning 是既有 Matplotlib `Axes3D` 环境提示。纯模块和包导入
均通过；main A3 paired smoke 为 `1 passed, 1 warning in 3.29s`。此前 main
`paired_learning_adoption 5 passed`、scalable `345 passed, 1 warning`、cross-module
`8 passed` 以及 D6 全量 `1093 passed, 1 warning in 98.33s` 均是本次 v3/阶段细分改动前的
冻结历史证据。v3 完成后的 D6 全量回归为 `1101 passed, 1 warning in 101.09s`；当前 v4
全量回归为 `1106 passed, 1 warning in 100.94s`。warning 仍是既有 Matplotlib `Axes3D`
环境提示。本轮没有运行 AirSim 或性能实验。

## 2026-07-27 D5 G1 v5 正式证据链

D6 已在 detached clean commit
`8d5e02ec989259ce3d39e1e4ad6a90dd0d8d5b54` 上完成正式外部审计和装配后审计。证据根目录为
`/tmp/MSM-d5-g1-formal-evidence-8d5e02e-20260727`。external audit 输出 schema 为
`d6.d5-g1-external-audit.v2`，结果为 `status=pass`、`blocker_codes=[]`。主 JSON 文件
SHA-256 为 `cbd6c72b2d9e7b78bf3aa36f975e6627250d2bf18de5a0b0ebc2c8f6cf760cd6`，
内容 SHA-256 为 `334cf662e49c735931019ff358be1894d1358f1b4a5a868759eee41d3d282d15`。

受审 paired lineage 包含 900 条记录和 900 个唯一 `episode_uid`，文件 SHA-256 为
`83e105290f3e624f267d92ceaf050d32291bd5bbbabf98580846cd31498b1af1`。D5 生产
assembler 随后生成 `d5.tracklet-model-bundle.v5`，manifest 文件 SHA-256 为
`b431d066362005868374d038eb93a83b773c03715a53d8a9dfd0da21784f317d`。D5 strict loader
和 shadow loader 均通过。

D6 对该 v5 执行 post-assembly v2。输出 schema 为
`d6.d5-g1-post-assembly-audit.v2`，结果为 `status=pass`、`blocker_codes=[]`，内容
SHA-256 为 `17dda42d06b4be1d21ff8f1f8baecc320fd49b532be06a9f9f6b304341763e1`；
consumer schema 为 `d6.d5-g1-post-assembly-audit-consumer.v2`。模型晋级、G1 辅助、
默认路径变更、分配、故障接管和控制六项权限在外审及装配后审计中均为 `false`。D5 assist
请求按 `bundle_g1_assist_authority_not_granted` 失败关闭。

该结果关闭“正式 external audit v2、正式 v5、正式 post-assembly v2 待运行”的 GAP。真实
相机泛化、中心 `global_track_id` 绑定正确性和物理闭环结果仍为 explicit unavailable。
审计通过只证明冻结证据和 v5 装配完整、一致，不授予模型晋级、辅助运行、默认路径、分配、
故障接管或控制权限。

## 2026-07-26 D5 v5 生产装配正向复核

D6 已逐字段复核 D5 公共 `assemble_tracklet_g1_bundle()`、v5 manifest、admission report v2
和公共严格加载器。新增测试先调用 D5 生产写包器生成 development-v3，再提供冻结的 held-out、
paired-shadow、external audit v2 和 900 条 lineage，最终由 D5 生产装配器生成
`d5.tracklet-model-bundle.v5`。D6 不再只用手工 manifest 正例证明跨模块兼容。

真实生产装配测试确认七文件布局、`SHA256SUMS` 精确覆盖、lineage 文件 SHA-256、900 条记录、
900 个唯一 `episode_uid`、admission report 的 lineage 三字段、六项 false 权限、external
audit 文件/内容 SHA-256 和十文件运行实现摘要全部通过 D6 post-assembly v2。对同一生产产物
篡改 lineage 或删除 lineage 均失败关闭。字段结构一致，未放宽门限，也未修改审计器。

软件回归结果：external audit 专项 `14 passed, 1 warning in 4.40s`，post-assembly 专项
`55 passed, 1 warning in 4.93s`，D6 全量 `1042 passed, 1 warning in 91.36s`。warning 为
既有 Matplotlib `Axes3D` 导入提示。本节记录正式执行前的软件兼容性复核；正式证据链已于
2026-07-27 闭合，见本页顶部。

## 2026-07-26 D5 G1 审计版本治理修正

D5 G1 external audit 的输出 schema 已升为
`d6.d5-g1-external-audit.v2`。输入字段没有变化，继续使用
`d6.d5-g1-external-audit-input.v1`；D5 consumer 字段也没有变化，继续使用
`d6.d5-g1-external-audit-consumer.v1`。三个版本分别写入主输出、`input_contract` 和
`d5_consumer_contract`，不再用一个 schema 表达四权限和六权限两种语义。

external audit v2 精确输出六项权限：模型晋级、G1 辅助、默认路径变更、分配、故障接管和
控制，六项均为严格布尔 `false`。真实相机泛化、中心 `global_track_id` 绑定正确率和物理
闭环结果继续以 `unavailable + reason` 输出。审计通过只表示冻结证据满足门限。

装配后审计同步升级为
`d6.d5-g1-post-assembly-audit.v2`。输入为
`d6.d5-g1-post-assembly-audit-input.v2`，consumer 为
`d6.d5-g1-post-assembly-audit-consumer.v2`，profile 为
`d6.d5-g1-post-assembly-integrity.v2`。受理制品和交叉绑定语义发生了破坏性变化。新入口只接受：

- `d5.tracklet-model-bundle.v5`；
- `d5.tracklet-g1-admission-report.v2`；
- `d5.tracklet-g1-authority-contract.v2`；
- `d6.d5-g1-external-audit.v2`。

v5 bundle 必须打包 held-out、paired-shadow、paired lineage 和 D6 external audit 四类证据。
装配后审计逐项核对六权限、D6 文件/内容 SHA-256、held-out 文件/内容 SHA-256、
paired-shadow 文件/内容 SHA-256、900 条唯一 lineage、运行实现摘要，以及 manifest、准入
报告和权限合同之间的精确一致性。旧 bundle v4、external audit v1、admission report v1 或
其他权限合同版本在任一组合中均失败关闭。

目录
`/tmp/MSM-d5-g1-current-runtime-d6-external-audit-64cb865-20260726-v2/`
是被版本审查否决的过渡制品。目录名含 `v2`，其中 JSON 的输出 schema 仍为
`d6.d5-g1-external-audit.v1`。其 20-seed/900-episode 统计仅保留为历史证据，不得用于 v5
装配，也不得替代 external audit v2。该待运行项已由 2026-07-27 clean commit 正式证据链
关闭；过渡目录仍保持拒绝状态，不得重新绑定或复用。

本模块当前没有 `docs/AIRSIM_INTEGRATION_PLAN.md`。本次证据来自离线合成 held-out 和
paired-shadow 审计，不改变 AirSim episode、相机、检测、运行总线或控制接口，因此不为该项
新建文档。

最新软件回归结果见上节。版本治理专项已由真实 D5 生产装配正例和两个生产产物 lineage
负例补强。

## 2026-07-26 D5 跨视角候选图几何校准

D6 已新增只读评估器 `d5_crossview_calibration.py` 和命令行入口
`scripts/run_d5_crossview_calibration.py`。输入复用 D5 finalized
`d5.tracklet-dataset.v2` 严格加载器。匿名图数组和 evaluator 标签在加载前保持物理分离，
D6 只在离线评估阶段按 `tracklet_key` 连接。

本工具评价几何门后的候选图，不评价 G1 模型打分。数据集的 `graph.edge_index` 只有几何候选
边，不含 `edge_probabilities`、判定阈值和模型聚类。报告中的精确率、召回率、F1 和假边率均
使用 `geometry_candidate_*` 语义。G1 打分收益、聚类纯度、中心
`global_track_id` 绑定正确率、控制结果和物理拦截结果固定为 unavailable。

候选召回分母只统计同真值、不同相机，且量测时间差不超过 `0.35 s`、到达时间差不超过
`1.0 s` 的节点对。没有分母时指标保持 unavailable，不补 0。每个 finalized dataset episode
按一个图帧处理，逐帧指标进入 aggregate JSON，逐 seed 微平均指标进入 CSV。至少 20 个
available seed 时输出均值、总体标准差和固定随机数 bootstrap 95% 置信区间。

R0/G1 候选图配对不使用 `episode_id`。调用方需为每个数据集提供
`d6.d5-crossview-frame-index.v1` sidecar。sidecar 绑定 dataset manifest SHA-256，并精确覆盖
全部 episode；唯一配对坐标为 `scenario_version + seed + frame_index`。缺少或损坏 sidecar
时比较 unavailable，formal 成对比较失败关闭。

formal 模式要求显式 expected seed 列表不少于 20，实际 seed 集精确一致，场景版本单一，标签
和候选召回声明全覆盖，候选召回分母可用，硬违规为 0。输出为 aggregate JSON、逐 seed CSV、
中文 Markdown 和 `SHA256SUMS`。权限固定为 evaluation only；模型晋级、默认路径、分配、
降级和控制均为 false。

### 正式 R0 制品独立复核

2026-07-26，D6 对 clean source commit
`64cb865b9933d45b13878019c0e1a21a8fbb2b05` 生成的正式 R0 候选图制品完成独立复核。
批次 `SHA256SUMS` 的 8834 项和 D6 报告 `SHA256SUMS` 的 3 项全部通过。批次 manifest
内容 SHA-256 为
`448b5ff15c458bb8d745f8e0a2ae80b03d9b062790f8a7fafaf18338a8c794c5`，D6 aggregate
内容 SHA-256 为
`dc84c90b90378ba0579311b7b5654018bf3a910ad98f30a59e5dc76eecd422af`。

dataset manifest 文件 SHA-256 为
`5ee284fd3a998c7ec415000cda3def1b1db7b866a762bcc68b6667858730b247`。frame-index
sidecar 绑定同一摘要，sidecar 文件 SHA-256 为
`f0db1b13913c69ba6b4beb5c07e242135885a3fb16fc9f559f193ac632611a1e`。sidecar 的
2670 条记录精确覆盖 2670 个 dataset episode；`scenario_version + seed + frame_index`
坐标无重复、无错配。场景版本为 `d5-crossview-visible-v1`，seed 为 `1000-1019`。

正式输入包含 2670 帧、16842 个节点和 4658 条几何候选边。时间合格同真值跨相机节点对为
4645，候选图保留真边 4642 条、假边 16 条。微平均候选精确率为 `0.9965650494`，召回率为
`0.9993541442`，F1 为 `0.9979576481`，假边率为 `0.0034349506`。20 个 seed 的逐 seed
F1 均值为 `0.9976519241`，总体标准差为 `0.0047860563`，bootstrap 95% 置信区间为
`[0.9953251507, 0.9995705026]`。标签与候选召回声明覆盖均为 2670/2670，硬违规为 0。

该 `formal/pass` 只关闭 R0 几何候选图合同及其统计证据。输入不含 G1 边概率、冻结阈值、
选中边或聚类，不能形成 G1 model scoring、cluster purity、中心
`global_track_id` binding、control 或 physical intercept 结论。报告权限保持
`evaluation_only=true`；model promotion、default path、assignment、failover 和 control
authority 全部为 false。

2026-07-26 合成合同测试覆盖完整正例、真/假候选边混合、无分母、缺标签、同相机边、超时边、
seed 不足、场景混杂、重复边、自环、非有限数组、重复航迹键、sidecar 缺失/缺记录、CLI 和
SHA 清单。专项 `12 passed, 1 warning`，D6 全量
`1022 passed, 1 warning in 88.77s`。这些 fixture 结果只证明评估软件合同；上述正式 R0
制品提供单臂候选图证据，仍没有 G1 输出 sidecar 或真实相机证据。

## 2026-07-26 D3 A1 与 D4 A2 预准入外部审计

D6 已新增 D3/A1、D4/A2 两套角色明确的预准入外部审计接口。两者共用只读校验核心，但分别使用
以下版本化合同和命令行入口：

- D3/A1：`d6.d3-a1-external-audit.v1`、
  `d6.d3-a1-external-audit-consumer.v1`、
  `scripts/run_d3_a1_external_audit.py`；
- D4/A2：`d6.d4-a2-external-audit.v1`、
  `d6.d4-a2-external-audit-consumer.v1`、
  `scripts/run_d4_a2_external_audit.py`。

审计输入显式冻结数据 manifest、数据内容、切分、全样本审计、模型 manifest、权重、当前实现
摘要、正式作用域报告和校验清单。D4 还绑定模型 readiness。D6 不扫描相邻目录，不接受调用方
附加 `promotion_allowed` 等自声明字段。每个文件先核对输入清单给出的带外 SHA-256；带内容
摘要的 JSON 再重算 `content_sha256`。

正式作用域必须包含至少 20 个与训练集不重叠的未见 seed。D3/A1 只认可隔离执行中
`d3_learning_applied_count` 已实际采用的 episode；D4/A2 只认可
`d4_advice_control_adoption_count` 已形成运行确认的 episode。加载模型、shadow、规则回退和
采用计数为 0 均不算实际采用。每个学习单元还必须有后续物理状态、在线真值零使用、安全与硬
约束通过，以及唯一同 comparison key 的 R0 单元。R0 配对至少要求拦截目标数和离线五米接近
唯一目标数可用且不退化。

缺失证据保持 `null`，并在 `field_availability` 中标记 `unavailable`。审计结果中的模型晋级、
辅助运行、分配、降级、默认路径和控制权限始终为 false。通过软件正例 fixture 只证明 schema
和判定器可工作，不代表当前 D3 或 D4 候选通过。

2026-07-26 对当前实际证据进行严格复跑。两者均为 `fail_closed`，正式学习 episode、实际采用、
物理窗口和唯一 R0 均不可用。D3 与 D4 各有 15 个 blocker：

- 正式作用域报告、正式校验清单和实现证据文件缺失；
- 未见 seed、正式 episode、实际采用、物理窗口、唯一 R0、paired non-degradation 和安全门
  均不可用；
- 候选指纹无法在缺失实现证据时形成；
- 冻结配置中的当前实现摘要与现工作树源文件摘要不一致。

D3 配置摘要为 `86b06e07...c27`，当前实算为 `2e06c9d2...bdf`。D4 配置摘要为
`ecab1eb7...3d8`，当前实算为 `044284d7...431`。D6 没有更新输入配置来消除该阻断。D3 候选
仍声明 development/shadow 且外部 holdout 实际评估数为 0；D4 候选也为
development/shadow，final holdout 为 0，并记录动作多样性和策略能力不足。这些静态限制继续
保留在报告中，不能替代正式运行证据。

严格复跑输出位于：

- `outputs/d3_a1_external_audit_actual_20260726_strict_v2/`：JSON 文件 SHA-256
  `837f95c6...529`，内容 SHA-256 `c1db7bb0...c0a`；
- `outputs/d4_a2_external_audit_actual_20260726_strict_v2/`：JSON 文件 SHA-256
  `0547fe50...c0a`，内容 SHA-256 `e5a11679...830`。

专项测试 `31 passed, 1 warning`，覆盖正例、负例、文件与内容篡改、实现和提交来源漂移、
角色采用证据替换、缺测 availability、shadow/fallback、物理窗口、隐藏 blocker、R0 缺失/
重复/复用及必选指标退化。D6 全量为
`975 passed, 1 warning in 103.81s`。warning 是既有 Matplotlib `Axes3D` 环境提示。

`AIRSIM_INTEGRATION_PLAN.md` 已检查。本项只消费持久化证据，不改变 AirSim settings、actor、
相机、episode、reset、检测或控制接口，因此无需修改。

## 2026-07-26 D5 G1 预准入外部审计与装配器后复核

D6 已实现独立、只读、失败关闭的 D5 G1 外部审计。首版输出 schema 为
`d6.d5-g1-external-audit.v1`，现已被本页顶部的 v2 合同替代。命令行入口为
`scripts/run_d5_g1_external_audit.py`。输入清单显式冻结 registry reference、registry audit、
模型 manifest/weights/checksums、held-out 报告、paired-shadow 报告和逐 episode lineage，
不扫描相邻目录，也不接受文件名推断模型身份。

审计直接重算文件 SHA-256、JSON 内容 SHA-256、模型指纹、训练数据 manifest/split/training-set
谱系，以及与 D5 `tracklet_runtime_implementation_sha256()` 一致的十个运行源文件实现摘要。
held-out 与 paired-shadow 必须绑定同一模型和
数据集；布尔值、非负整数和 metric availability 使用严格类型。缺文件、缺字段、类型错误、
文件或内容哈希不符、跨模型、跨数据集、实现错配、非正式、门限不足和 unavailable 均返回稳定
blocker code，缺失计数保持 `null`，不补成 0。

固定形式化门要求 seed `1000-1019`、至少 20 个未见 seed、900 个 held-out episode、45 个场景
规模单元、完整 paired catalog 和只读输入。安全计数要求在线真值字段、`global_track_id` 改写、
同相机互斥违规均为 0。泛化门单独限制单特征最高 AUC 不高于 0.98，五类扰动的最低边/簇 F1
均不低于 0.9。候选图是否在扰动后重建作为显式限制字段，不由名义满分覆盖。

### 64cb865 历史运行实现外审

2026-07-26T17:56:00Z，D6 对 clean commit
`64cb865b9933d45b13878019c0e1a21a8fbb2b05` 的当次 D5 运行实现执行独立外审。输入 JSON
SHA-256 为
`f98b42d328f8def4fabfca779ce9e322de90b053ef69ff98e579d7b8f8d423a5`。顶层 24 项、
bundle 2 项、formal 2 项和 current-runtime registry 3 项 `SHA256SUMS` 全部通过。

当次 manifest/weights/checksums SHA-256 为
`db908b05...d14` / `7fb5db8b...a71` / `2fe079ed...856`。held-out 文件/内容 SHA-256
为 `9393c192...294` / `e031f7fe...6e9`，paired-shadow 文件/内容 SHA-256 为
`2caac3f7...546b` / `380c9092...e190`，paired lineage SHA-256 为 `21204bc3...b8b5`。
registry reference/audit/checksums SHA-256 为
`a8b93ba2...e5b` / `c18f4149...477` / `8d5c6b39...81a`。

D6 逐文件重算十个运行源文件，当次实现、输入期望和 held-out/paired 联合证据摘要均为
`5506638201623048fb53c8e15493a2dc367d5682abbee3b7235704721586b8ea`，无文件冲突或
错配。所有九个受审 artifact 路径均属于当次批次，paired `supersedes=[]`；模型、训练数据、
held-out、paired、lineage 和运行实现的交叉绑定全部一致。审计前后输入树 80 个文件的摘要
清单逐字节相同。

形式化目录包含 seed `1000-1019`、900 个 episode 和 45 个场景规模单元。held-out
F1/错误合并率/候选召回/P95 推理时延为 `1.0/0.0/1.0/0.8715935983 ms`。五类扰动最低
边/簇 F1 为 `1.0/1.0`，最高单特征 AUC 为 `0.7200734257 <= 0.98`。在线真值字段、
同相机候选边、同相机互斥违规和 `global_track_id` 创建或换绑违规均为 0。

按当时冻结门计算，外审结果为 `pass` 且 blocker 为空；版本治理状态现为
`rejected_transition_schema_v1`。该结果位于
`/tmp/MSM-d5-g1-current-runtime-d6-external-audit-64cb865-20260726-v2/`。JSON 文件/内容
SHA-256 为 `24c8b0cd...ad7d` / `f17acecf...135f`，三项内容文件的 `SHA256SUMS` 通过；
同输入重复运行四个输出逐字节一致。该确定性不消除 schema 版本错误，制品不得进入新装配。

该历史 v1 输出将 assignment、failover、control、default path、G1 assist 和 model promotion
权限全部显式写为 false。真实相机泛化、中心 `global_track_id` 绑定正确率和物理闭环结果
保持 unavailable。五类扰动仍固定 post-gate 候选图。本次没有运行 G1 episode，没有生成或
装配新的 v4，也没有改变默认规则路径。

外审专项为 `14 passed, 1 warning in 4.39s`，D6 全量为
`1022 passed, 1 warning in 89.39s`。变更 Python 入口编译通过；warning 为既有 Matplotlib
`Axes3D` 导入提示，不影响哈希、审计结论或二维报告。

### 7fb5 robust-v2 正式外审

2026-07-26T14:01:34Z，D6 使用 clean worktree
`/home/linux/Documents/MSM-d5-training-clean` 的 `fa3ec10` 源码，对正式 registry
`tracklet_gnn_7fb5db8b_registry_fa3ec10` 执行独立外审。冻结配置为
`configs/d5_g1_external_audit_7fb5db8b_fa3ec10_20260726.json`。D6 独立重算九类输入文件、
registry 与 bundle 的 `SHA256SUMS`、held-out/paired-shadow 内容摘要，以及十个 D5 运行时源文件
摘要；当次实现摘要为
`408e71fe6a31bca03de61d10cefbf73c6b32e193fd6b2d7bf734389972f9f4fe`。

正式输入绑定 manifest `0eff183f...a77`、weights `7fb5db8b...a71`、20 个未见 seed、900 个
episode 和 45 个场景规模单元。held-out F1、错误合并率、候选召回率和 P95 推理时延均满足
`0.92/0.01/0.95/100 ms` 冻结门。最高单特征 AUC 为 `0.720073 <= 0.98`；五类扰动最低边/簇
F1 均为 `1.0 >= 0.9`。在线真值字段、`global_track_id` 改写和同相机互斥违规均为 0。

外审结果为 `pass`，blocker 为空。正式输出位于 clean worktree 的
`outputs/d5_g1_external_audit_7fb5db8b_fa3ec10_20260726/`。主 JSON 文件 SHA-256 为
`10bf19f5...10b0`，内容 SHA-256 为 `4e24ab33...9e54`，输出 `SHA256SUMS` 全部通过。D6 的模型
晋级、G1 辅助、控制和默认路径权限仍全部为 false。该结果只关闭冻结证据链外审，不表示模型已
进入在线主路径。

五类扰动仍固定 post-gate 候选图，没有重新执行相机重投影、门控和候选图构建。证据也未覆盖
真实相机、真实外参漂移、真实遮挡和在线检测误差。该历史实例生成时，D5 尚未消费通过合同形成
准入证据；该待执行项已由本页顶部的 2026-07-27 v5 正式证据链关闭。实际 G1 运行及其同键 R0
作用域审计仍未发生。专项测试为 `14 passed, 1 warning in 4.54s`，D6 全量为
`975 passed, 1 warning in 86.70s`。

### 历史 v4 装配后正式外审

D5 已将上述正式外审 JSON 与同一 held-out、paired-shadow 装配为
`d5.tracklet-model-bundle.v4`。D6 为此新增独立 post-assembly 合同
`d6.d5-g1-post-assembly-audit.v1` 和命令行入口
`scripts/run_d5_g1_post_assembly_audit.py`。该审计不重跑 development-v3 预准入逻辑，也不把
manifest 内的通过布尔值当作审计结论。

本节记录旧版历史结果。v4、admission report v1、external audit v1 和 post-assembly v1
均不满足当前 v5/v2 合同，不得作为新装配或新准入证据复用。

输入配置
`configs/d5_g1_post_assembly_audit_7fb5db8b_a5a53de7_20260726.json`
显式冻结 v4 manifest、weights、`SHA256SUMS` 和三份内嵌 evidence 的文件摘要，并单独冻结原
D6 外审 JSON 内容摘要。审计要求 `SHA256SUMS` 精确且有序覆盖五项文件，逐项重算文件和内容
SHA-256；同时交叉核对 source development bundle、训练数据、十文件运行实现、admission
report、20/900/45 和三项安全零计数。审计器不会到相邻目录发现替代证据，但会在不跟随符号
链接的前提下枚举指定 bundle 根目录。目录树只能包含六个约定文件和 `evidence/` 目录；额外
文件、空目录、符号链接、特殊文件、清单缺项/重复/越界、篡改、权限误开、内容摘要不符和外部
审计绑定错误均返回稳定 blocker。

2026-07-26T14:43:17Z，正式 v4 manifest/weights/checksums SHA-256 为
`a5a53de7...7154` / `7fb5db8b...ca71` / `1221ec23...5956`。正式结果为 `pass`，
blocker 为空。输出位于 clean worktree 的
`outputs/d5_g1_post_assembly_audit_7fb5db8b_a5a53de7_20260726/`。主 JSON 文件/内容 SHA-256
为 `a78c5edb...cf33` / `91d627fb...007e`，输出校验清单复算通过。

上述输出保留为首次正式装配审计记录，没有被覆盖。main 随后在 detached clean evaluator commit
`107cf0756d7b75cd6bf1456d1f1aa940fec6a63c` 上运行强化后的同一合同，正式输出位于
`outputs/d5_g1_post_assembly_audit_7fb5db8b_a5a53de7_formal_107cf07_20260726/`。结果仍为
`pass`，`audit_passed=true`，blocker 为空；目录树精确包含六个文件和一个 `evidence/` 目录。
结果 JSON 文件/内容 SHA-256 为 `12f457e2...8ea` / `37384441...d852`。Markdown、JSON 和 CSV
三项 `SHA256SUMS` 全部复算通过。

v4 的 `g1_assist_eligible=true` 是 D5 装配后的资格声明。D6 输出中的模型晋级、G1 assist、
默认路径、`global_track_id`、分配和控制权限仍全部为 false。本轮 post-assembly 专项为
`35 passed, 1 warning in 4.33s`，D6 全量为
`1010 passed, 1 warning in 87.38s`。负例覆盖六类制品逐项篡改、额外未列文件、清单缺项/
重复/路径逃逸、直接和父目录符号链接、bundle 与原 D6 外审权限误开、三份内容摘要错误及外审
绑定不一致。`AIRSIM_INTEGRATION_PLAN.md` 已检查；本项只审计文件，不改变 AirSim 接口，因此
未修改。

### 99fa 历史审计

2026-07-26 首次对实际 99fa 候选运行审计。候选 bundle 为
`d5_composite_internal_training_clean_6dc471b/model_bundle`；held-out 和 final paired-shadow
均绑定 weights SHA-256 `99fa4428...d4cd`。20 个 seed、900 个 episode、45 个单元和三项安全
零计数可用。结果仍为 `fail_closed`：

- 报告联合实现摘要为 `81968e0d...066e7f`，当次运行实现摘要为
  `ff8c744e...8a1b7`，差异位于 `tracklet_model_bundle.py`，没有可验证等价桥接；
- 单特征最高 AUC 为 `0.997340`，超过 0.98；
- 扰动最低边/簇 F1 为 `0.563264/0.572845`，低于 0.9；
- 五类扰动均固定原候选图，不能代替重新投影和重新构图的外部泛化证据。

该历史输出包含 JSON、证据索引 CSV、中文 Markdown 和 `SHA256SUMS`，位于
`outputs/d5_g1_external_audit_99fa4428_20260726/`。专项测试为 `13 passed`，D6 全量为
`943 passed, 1 warning in 80.56s`。warning 是既有 Matplotlib `Axes3D` 环境提示。D6 输出仅表示
evidence audit pass/fail，不授予模型晋级、G1 辅助、控制权或默认路径变更。后续 D5 evidence
assembler 只能消费该 JSON 及其文件/内容哈希；执行 G1 后，D6 现有
`learning_scope_formal_audit` 仍负责运行作用域与同键 R0 的下游复核。

D5 在提交 `005c74e` 中加入 G1 evidence assembler，并把该文件纳入运行时实现摘要。D6 随后将
审计文件集合对齐为同一十文件集合；两侧均使用排序键、紧凑 JSON、ASCII 转义和末尾换行计算
规范摘要，实算结果均为 `41381db3...4b07`。本次只对同一 99fa bundle、同一 held-out 和同一
final paired-shadow 重新核对软件谱系，没有启动新 episode，也没有生成新模型性能样本。

装配器后复核继续 `fail_closed`。旧证据没有
`tracklet_g1_evidence_assembler.py` 哈希，`tracklet_model_bundle.py` 的证据哈希也与当前文件
不同，因此同时产生 `implementation_evidence_unavailable` 和
`implementation_lineage_mismatch`。单特征、边 F1 和簇 F1 三项原阻断保持不变。新审计写入
`outputs/d5_g1_external_audit_99fa4428_post_assembler_20260726/`，主 JSON 文件 SHA-256 为
`98bf9e02...c8ed`，JSON 内容 SHA-256 为 `40a42af0...90d`。原审计目录保持不变。装配器后
定向回归为 `14 passed`，D6 全量为 `944 passed, 1 warning in 80.12s`。

```bash
PYTHONPATH=research_modules/d6_evaluation_metrics \
python3 research_modules/d6_evaluation_metrics/scripts/run_d5_g1_external_audit.py \
  --input-spec research_modules/d6_evaluation_metrics/configs/d5_g1_external_audit_99fa4428_post_assembler_20260726.json \
  --repository-root . \
  --output-dir research_modules/d6_evaluation_metrics/outputs/d5_g1_external_audit_99fa4428_post_assembler_20260726
```

## 2026-07-25 正式实验矩阵准入预检

D6 已实现只读、失败关闭的正式矩阵准入预检
`experiment_matrix_admission.py`，并提供命令行入口
`scripts/run_experiment_matrix_admission_precheck.py`。入口支持两种模式：

- `pre_run` 读取实际 `ExperimentMatrixPlan.cells()` 或 main 明确生成的 cell 清单，检查清单、
  clean source 和模型制品，不运行 episode；
- `post_run` 在上述检查之外，读取矩阵 manifest、逐 cell 清单、D6 逐 seed CSV、聚合 JSON、
  中文报告、曲线、动画和模型清单。

预检不会依据目录名重建缺失 cell。只有矩阵维度而没有显式 cell 清单时，结果固定为
`fail_closed`。当前 formal 计划由实际 `cells()` 枚举得到 5700 个 cell：R0、G1、A1、A2、
A3、C1 覆盖九类场景，F1 覆盖三类全系统场景，五档规模各使用 20 个未见 seed。若 main 修改
F1 场景范围，D6 的数量随传入清单变化，不使用 6300 这一固定数。

命令行入口没有传入 `--inventory` 时仍会生成失败关闭报告，此时
`expected_cell_count=0` 只表示 expected inventory 缺失。它不是正式矩阵规模，也不是下述
5700-cell 预检结果。命令行和中文报告现均显式输出该缺输入状态。

逐 cell 检查覆盖唯一性、模型准入、声明采用模式、静默回退、在线真值、有限状态、D2 身份交换
指标可用性、五米物理指标可用性和逐 seed 输入。聚合检查覆盖训练/评估 seed 零交集、置信区间
输入、报告、动画和模型哈希清单。输出为完整 JSON、逐 cell CSV、中文 Markdown 和
`SHA256SUMS`。

2026-07-25 当前仓库静态 `post_run` 预检结果为 `fail_closed`。预期 5700 个 cell，运行
manifest 和逐 cell 制品均不存在，因此通过数为 0。现有 D3、D4、D5 图模型和 D5 主动视觉模型
的 manifest 与 weights SHA-256 均一致，但四个模型都只声明开发或影子模式，尚未获正式 assist
准入。该结论不运行大矩阵，也不把缺失的 D2 身份交换、五米物理结果或置信区间补成数值。

当前预检制品位于
`outputs/formal_matrix_admission_precheck_20260725_current/`。
专项测试 `9 passed`，D6 全量回归 `889 passed, 1 warning`；既有 main 矩阵合同测试
`7 passed, 1 warning`。当前预检 `SHA256SUMS` 三项均校验通过。warning 为既有 Matplotlib
三维投影导入提示，不影响本预检的 JSON、CSV 或 Markdown。

## 2026-07-25 D1 在线发布证据子集快照正式独立评估

D6 已新增只读 evaluator
`d1_publication_evidence_snapshot_multiseed.py` 和 CLI
`scripts/evaluate_d1_publication_evidence_snapshot_multiseed.py`。输出 schema 为
`d6.d1_publication_evidence_snapshot_multiseed_evaluation.v1`。入口固定绑定
producer clean commit `d0219eb14c529a4fb9bf7d6610a9f32055a09206`、matrix SHA-256
`6c808c4df8759fd893c6d37ff9dce4a1efa07f9867fc71aff47a55c5f8517338`、
200 个目标、200 个资源、2 个侦察节点及 13 个平衡顺序 pair。

参考实现为 `full_consistency_snapshot_v1`，候选为
`required_observation_subset_v1`。两臂的回放前缀实现均固定为
`per_checkpoint_prefix_rebuild_v1`，唯一运行处理差异是在线发布证据快照 selector。loader
只接受 26 个 fresh complete arm，拒绝 dirty、reused、failed、提交或矩阵漂移、命令漂移、
路径越界和未知字段。

D6 在 runtime profile、summary、module final、governance audit 和 nested governance
核对 selector、完整 implementation ID、execution config 和 diagnostics。逐 pair 重新比较
在线总线、D1/D2 在线记录、业务计数、离线 consistency record count/digest、原 D1 fusion
operation counts、有限状态和在线真值使用。候选 fallback、lookup miss、invalid required ID
和 empty required set 必须为 0，参考臂必须全程使用完整快照路径。

正式输入 manifest SHA-256 为
`67813a3e850759dd4c194add4b622870345118aec5acdf74d2480f86c00735b4`。
13/13 pair 的业务语义、有限状态、在线真值隔离、实现身份、D1/D2 在线记录、consistency
digest/count、原操作计数和诊断审计均通过。候选返回记录由 `1602170` 减至 `133917`，
削减 `91.641524%`；429 次候选选择全部成功，回退、查询缺失、非法和空集合计数均为 0。

正式 verdict 为 `reject`。short 候选仅 `4/10` 更快，D1 融合配对改善均值为
`-0.147877%`，short 原始变化 bootstrap 95% 上界为 `1.374681%`，分别未达到
`8/10`、`>=1%` 和 `<=0%`。long 候选 `2/3` 更快，D1 改善 `1.047143%`；short/long
core、D2 和 RSS 门通过。候选最低实时因子为 `0.203423 < 1`，该系统门独立于优化 verdict。

候选保持默认关闭，参考实现保持默认。正式 bundle 位于
`outputs/d1_publication_evidence_snapshot_multiseed_20260725_formal_d0219eb_d6/`，包含完整
JSON、compact JSON、13 条 pair CSV、中文 Markdown 和 `SHA256SUMS`。该结论只覆盖
2026-07-25 的三维质点冻结矩阵，不代表 AirSim、目标处理器、硬件、实机或实飞性能。
同一正式 manifest 的第二次只读评估与正式 bundle 逐文件一致。聚焦测试为
`14 passed, 1 warning`，D6 全量为 `880 passed, 1 warning in 76.17s`；warning 为既有
Matplotlib `Axes3D` 环境提示，不影响本入口的二维文件、统计或判定。

```bash
python3 research_modules/d6_evaluation_metrics/scripts/evaluate_d1_publication_evidence_snapshot_multiseed.py \
  --evidence-manifest /tmp/msm_d1_publication_evidence_multiseed_20260725_formal_d0219eb/evidence_manifest.json \
  --output-dir research_modules/d6_evaluation_metrics/outputs/d1_publication_evidence_snapshot_multiseed_20260725_formal_d0219eb_d6
```

## 2026-07-25 D1 回放前缀摘要正式独立评估

D6 已使用只读 evaluator `d1_replay_prefix_summary_multiseed.py` 和 CLI
`scripts/evaluate_d1_replay_prefix_summary_multiseed.py` 完成正式评估。输出 schema 为
`d6.d1_replay_prefix_summary_multiseed_evaluation.v1`，producer clean commit 为
`7d2e987471b521a1e531bf03a5c99af5096f676a`，matrix SHA-256 为
`85432d729877eff97e6f3dd517d4baa7a47f44a4fa42e6bfdc7ce85b8d9ec74b`。参考实现为
`per_checkpoint_prefix_rebuild_v1`，候选实现为
`fixed_lag_checkpoint_prefix_cumulative_summary_v1`。

正式矩阵包含 200 个目标、200 个资源和 2 个侦察节点。short 组使用 seeds 1151-1160、
每个 episode 2.2 秒；long 组使用 seeds 1151-1153、每个 episode 10 秒。共 13 pair、
26 个 fresh complete episode，0 reused、0 failed。clean seed-1151 预检和 D1 模块微基准未
计入正式样本。

评估器失败关闭检查 manifest/matrix schema 与摘要、同一 clean commit、seed/时长/规模、命令和
路径边界。两臂只允许 `d1_replay_prefix_summary_implementation` 不同。selector、完整实现标识、
6 秒固定滞后执行配置和诊断分别在 runtime profile、summary、module final、nested governance
和 governance audit 核对。逐对审计覆盖业务语义、在线 consistency `record_count` 与
`records_digest`、D1 原有操作计数、导出前后 ledger 守恒及在线真值隔离。

正式 verdict 为 `reject`，`main_default_promotion_allowed=false`。五个失败门为：

- short 候选更快数 `5/10 < 8/10`；
- short D1 融合改善 `0.959611% < 1%`；
- short 配对 bootstrap 原始变化 95% 上界 `0.619827% > 0%`；
- short 核心墙钟改善 `-0.256641% < 0.25%`；
- long 核心墙钟改善 `-1.930083% < 0.25%`。

13/13 pair 的业务语义、consistency digest/count、D1 原有操作计数、实现身份、诊断守恒和
真值隔离均通过。long D1 融合改善 `2.361778%`；全矩阵内部物化减少
`52.150746%`；short/long RSS 与 D2 组均值门通过。候选仍在线投影构造 `656481` 条记录，
因此内部物化压缩不能解释为端到端工作量按同等比例下降。

候选最低实时因子为 `0.197441 < 1`，
`system_realtime_gap_closed=false`。候选保持默认关闭，参考实现保持默认。正式 bundle 位于
`outputs/d1_replay_prefix_summary_multiseed_20260725_formal_7d2e987_d6/`；目录内
`SHA256SUMS` 已校验通过。main 从同一 manifest 重跑后，完整 JSON、紧凑 JSON、逐 pair CSV、
PNG、中文 Markdown 和校验文件的 SHA-256 均与正式 bundle 一致。

该证据只覆盖 2026-07-25 的三维质点仿真矩阵，不代表 AirSim、目标处理器、硬件、实机或实飞
性能。后续若评估改进候选，必须使用新候选名和新预注册矩阵，不得覆盖本次 `reject`。

## 2026-07-25 D1 关联稀疏预筛多种子正式评估入口

D6 已实现独立、只读、失败关闭 evaluator
`d1_association_sparse_prefilter_multiseed.py` 和 CLI
`scripts/evaluate_d1_association_sparse_prefilter_multiseed.py`，schema 为
`d6.d1_association_sparse_prefilter_multiseed_evaluation.v1`。入口固定绑定 matrix SHA-256
`a7162d014d1c3c0f207355b24a5d7159bf3486d134ca21876f7469d1e915b71d`、clean source
commit `9302ccede2ca513c2235370e1a464fc88bc41150`、200 个目标、200 个资源、2 个侦察节点，
以及 short seeds 1131-1140、long seeds 1131-1133。13 pair/26 arm 必须全部 fresh
complete，producer 状态必须为 `episodes_complete_pending_d6`。

评估器重新计算 manifest/matrix SHA、提交、命令和路径边界，并在 runtime profile、summary、
module final 与 governance 四个主表面核对 selector、完整 implementation ID、execution config
和 `d1.association_sparse_prefilter_diagnostics.v2`；runtime configuration 与 nested
governance 另作冗余检查。六个固定模态桶、逐桶计数上界、总计守恒、有限状态和 online truth
use=0 均失败关闭。

业务语义逐 pair 调用规范跨 episode 比较器重算。归一化只覆盖预注册 treatment、对应
execution config/diagnostics、关联精确求解诊断、运行时哈希派生 episode ID 和性能字段。
在线消息、D1-D7 业务结果、D3 计划谱系、D4 内容地址与 ACK 及离线 truth 制品继续比较。
reference/candidate 的 exact gate-pass 计数必须逐 pair、逐模态相等。

正式输入为 13 pair/26 fresh episode，0 reused、0 failed；13/13 业务语义、实现身份、有限状态、
真值隔离、逐模态 gate-pass 和稀疏预筛审计通过。候选全矩阵诊断中，radar 的
candidate/rejection/solve/gate-pass/fallback 为
`9199071/9145313/53758/48321/3773`，eo 为
`801650/258272/39837/3979/37571`，其余四个模态桶均为 0。非雷达精确求解由
`298109` 降至 `39837`，减少 `86.636767%`。

正式 verdict 为 `reject`。short D1 fusion 改善仅 `0.228437%`、候选更快 `7/10`，short
bootstrap 原始变化 95% 上界为 `0.443531%`，short core 改善 `0.091096%`；long D1 fusion
改善 `0.713776%`。这五项分别未达到冻结的 `1%`、`8/10`、`<=0%`、`0.25%` 和 `1%` 门。
其余来源、语义、诊断、非雷达精确求解削减、scan input、D2 和 RSS 门均通过。main 默认晋升
不允许，reference `disabled_v1` 保持默认。候选最低实时因子为 `0.206273 < 1`，系统实时缺口
仍开放；任一 pair 最大 RSS 增幅仅 `0.077909%`，通过 5% 上限。

正式 bundle 位于
`outputs/d1_association_sparse_prefilter_multiseed_20260725_formal_9302cce_d6/`，包含完整/紧凑
JSON、13 条 pair CSV、中文 Markdown、PNG 曲线和 `SHA256SUMS`。定向测试
`13 passed, 1 warning in 7.22s`，D6 全量 `859 passed, 1 warning in 64.83s`。本证据只覆盖
三维质点仿真，不代表 AirSim、目标硬件、实机或实飞结论。

```bash
PYTHONPATH=research_modules/d6_evaluation_metrics \
python3 research_modules/d6_evaluation_metrics/scripts/evaluate_d1_association_sparse_prefilter_multiseed.py \
  --evidence-manifest /tmp/msm_d1_association_sparse_prefilter_multiseed_9302cce/evidence_manifest.json \
  --output-dir research_modules/d6_evaluation_metrics/outputs/d1_association_sparse_prefilter_multiseed_20260725_formal_9302cce_d6
```

`AIRSIM_INTEGRATION_PLAN.md` 已检查。本入口不改变 AirSim topic、相机、actor、reset、检测、控制或
episode 调度，因此无需修改。

## 2026-07-25 D1 在线批帧交接多种子正式评估入口

D6 已实现独立只读、失败关闭 evaluator
`d1_online_batch_frame_multiseed.py` 及 CLI
`scripts/evaluate_d1_online_batch_frame_multiseed.py`，schema 为
`d6.d1_online_batch_frame_multiseed_evaluation.v1`。入口固定绑定 matrix SHA-256
`4afbf9ac273763a16aa01cc744fd67b52e437099460b33377a128f986ac5719b`、clean source commit
`43feaf600f288a85ce76a76862334256f0d0d352`、short seeds 1121-1130、long seeds
1121-1123、200 个目标、200 个资源和 2 个侦察节点。13 对/26 episode 必须全部 fresh
complete，producer 状态只能是 `episodes_complete_pending_d6`。

selector、完整 implementation ID、execution config 和
`d1.online_batch_frame_handoff_diagnostics.v1` 在 runtime profile、summary、module final、
嵌套治理和治理 audit 表面交叉绑定。D6 从原始 episode 重算有限状态、online truth use、
批帧 request/path/result/snapshot/final-frame 守恒、scan/core/D2/RSS/实时因子、重复检查减少、
closed handoff ratio 和 fallback count，不读取 producer admission 判定。

业务等价只归一化预注册 treatment、批帧诊断及派生字段、处理派生 episode ID 和性能字段。
跨运行 opaque plan ID 按已验证的首次出现谱系映射；源 payload SHA、ACK 和 D4 内容地址先校验，
分配关系、授权状态、目标/资源绑定、状态机结果、计数和安全结果仍逐条比较。

正式结果为 `admit`：13/13 业务等价、有限状态、实现身份和批帧审计通过，online truth use 为 0；
short/long scan input 改善 `38.289241%/36.275282%`，core wall 改善
`4.252745%/4.916501%`，D2 组均值增幅 `2.113047%/2.830616%`，RSS 最大组均值增幅
`0.281879%`、任一 pair 最大增幅 `0.856727%`。重复检查减少率和 closed handoff ratio 均为
`100%`，fallback 为 0。候选最低实时因子 `0.204490 < 1`，所以 200v200 系统实时仍不足。
证据仅为三维质点，不是 AirSim、实机或实飞证据。正式 bundle 位于
`outputs/d1_online_batch_frame_multiseed_20260725_formal_43feaf6_d6/`。定向测试
`12 passed, 1 warning`，D6 全量 `846 passed, 1 warning in 59.24s`。

```bash
python3 research_modules/d6_evaluation_metrics/scripts/evaluate_d1_online_batch_frame_multiseed.py \
  --evidence-manifest /tmp/msm_d1_online_batch_frame_multiseed_43feaf6/evidence_manifest.json \
  --output-dir research_modules/d6_evaluation_metrics/outputs/d1_online_batch_frame_multiseed_20260725_formal_43feaf6_d6
```

## 2026-07-25 D1 不透明来源标识缓存评估入口

D6 新增独立、只读、失败关闭的离线消费者
`d1_opaque_source_identity_cache_multiseed.py` 和命令行
`scripts/evaluate_d1_opaque_source_identity_cache_multiseed.py`。入口固定绑定 evaluator schema
`d6.d1_opaque_source_identity_cache_multiseed_evaluation.v1`、matrix SHA-256
`218d04f3fc4a764fef82de612c78c8fbb5490380ae5d20aff6b9089635f2060d`、clean producer
commit `d8fc76c066f21b077154f7be33c0b43558d237e5`、200 个目标、200 个资源、2 个侦察节点，
以及 short `1101-1110 @ 2.2 s`、long `1101-1103 @ 10 s` 的 13 个 pair。26 个 arm 必须
全部 fresh complete；dirty、reused、failed、提交漂移、矩阵字节变化、命令漂移和路径越界均
失败关闭。

本矩阵显式启用 `--d1-publish-opaque-source-key`，结构歧义 hold 为 false。结果只适用于
source-only 发布面，不能写成默认无来源键 R0 路径的收益。参考实现
`per_publication_build_v1` 每次发布构造来源节点、发布 epoch 和航迹键；候选
`bounded_generation_lru_v1` 以三者为键复用三个不可变字符串，容量固定为 1024。

selector 与 `d1.opaque_source_identity_cache_diagnostics.v1` 在 runtime profile、summary、
module final、嵌套治理和独立治理中交叉校验。候选必须满足
`request=hit+miss+bypass`、`build=miss+bypass`、hit/miss 均大于 0、bypass 为 0，并满足容量和
峰值边界；参考必须满足 `bypass=request=build`，且 hit、miss、entry、peak 和 eviction 均为 0。
两臂发布请求数和 publisher node/epoch generation 必须相同。

业务语义只归一化预注册 selector、对应缓存诊断、runtime profile SHA、处理派生 episode 标识和
性能字段。`GlobalTrack`、来源键业务值、在线观测、状态与协方差、D2-D7 消费结果、计划和控制
语义继续逐条比较，在线真值使用必须为 0。D6 分别输出局部
`optimization_admitted` 和系统 `system_realtime_gap_closed`。

正式 13-pair/26-arm 评估已完成，0 reused、0 failed，13/13 业务语义、有限状态、真值隔离、
实现身份和缓存审计通过。short/long D1 融合改善 `9.465972%/6.437432%`，候选分别
`10/10`、`3/3` 更快；核心墙钟改善 `2.845610%/2.728043%`。候选标识构造减少率和缓存命中率
均为 `99.163670%`。

唯一失败门是 long D2 关联墙钟组均值增幅 `5.605213%`，高于冻结上限 `5%`。
`long_seed_1101` 的单 pair 增幅 `19.069868%` 已保留，没有剔除或改门。因此
`optimization_admitted=false`。候选最低实时因子为 `0.193887`，
`system_realtime_gap_closed=false`。后续只能通过新的预注册确认矩阵复核 D2 长时回归。

正式 bundle 位于
`outputs/d1_opaque_source_identity_cache_multiseed_20260725_formal_d8fc76c_d6/`，包含完整
JSON、compact JSON、逐 pair CSV、中文 Markdown、PNG 曲线和 `SHA256SUMS`。聚焦测试为
`16 passed, 1 warning in 5.85s`，D6 全量为
`834 passed, 1 warning in 59.24s`；warning 为既有 Matplotlib `Axes3D` 环境提示。

```bash
python3 research_modules/d6_evaluation_metrics/scripts/evaluate_d1_opaque_source_identity_cache_multiseed.py \
  --evidence-manifest /path/to/evidence_manifest.json \
  --output-dir /path/to/independent_d6_report
```

`AIRSIM_INTEGRATION_PLAN.md` 已检查。本入口只读消费三维质点 episode，不改变 AirSim topic、
相机、actor、reset、检测、控制或调度接口，因此无需修改。

## 2026-07-25 D1 结构化数值雅可比评估入口

D6 新增可选离线消费者
`d1_structured_numerical_jacobian_multiseed.py` 和命令行
`scripts/evaluate_d1_structured_numerical_jacobian_multiseed.py`。该入口不进入在线控制，也不改变
D1 默认实现。它固定绑定：

- evaluator schema `d6.d1_structured_jacobian_multiseed_evaluation.v1`；
- matrix schema `scalable3d-d1-structured-jacobian-multiseed-matrix-v1`；
- matrix SHA-256
  `c6c3cf53c89dfb3155a29ba49bb77a12c8bdf1a5d433c4f645de0d00c506d478`；
- clean producer commit
  `9d1f54f8540fdc4a7a1011121aafac5718290122`；
- 参考/候选实现
  `dense_output_probe_v1/known_dimension_structural_columns_v1`；
- short seeds `1101-1110 @ 2.2 s`、long seeds `1101-1103 @ 10 s`，规模为
  200 个目标、200 个资源和 2 个侦察节点。

loader 只接受 13 pair、26 个 fresh complete arm，不接受 reused、failed、dirty source、错误提交、
旧 schema、命令漂移或 evidence root 外路径。selector、完整实现 ID 和
`d1.structured_numerical_jacobian_diagnostics.v1` 在 runtime profile、summary、module final、
嵌套 governance 和独立 governance 中交叉校验。四份最终诊断必须相同，并满足雅可比尝试、成功/
失败、参考/候选调用、输出探测和量测函数求值的操作数守恒。

业务语义比较只归一化预注册 selector、诊断、性能字段和处理派生 episode ID。在线载荷、航迹、
关联、分配、控制、计划谱系和离线真值继续逐对比较，在线真值使用必须为 0。输入缺失或合同无效时，
正式入口返回 `availability.available=false` 和 `reason`，同时固定
`optimization_admitted=false`、`system_realtime_gap_closed=false`；严格加载入口仍可抛出异常用于
定位篡改。

冻结门要求 short/long D1 融合改善均不低于 2%，核心墙钟改善均不低于 0.5%，D1 更快 pair 数
分别至少为 `8/10` 和 `2/3`，short 的 10000 次配对 bootstrap 上界小于 0。D1 scan input、D2
association 和 RSS 增幅分别受 5% 上限约束，候选量测函数求值减少率不得低于 35%。局部准入与
系统实时门分别计算。

截至 2026-07-25，evaluator、CLI、确定性 writer 和合成正负合同测试已实现。main 已使用 D6 CLI
完成正式评估：`availability=true`、`optimization_admitted=true`、
`system_realtime_gap_closed=false`。输入包含 13 pair、26 个 fresh complete arm，0 reused、
0 failed，全部冻结准入门通过。

短时 D1 融合与核心墙钟分别改善 `6.084778%/1.897370%`，候选 `10/10` 更快；长时分别改善
`4.676061%/1.786530%`，候选 `3/3` 更快。量测函数求值减少 `53.846154%`。候选最低实时因子为
`0.180726`，未达到系统实时门限 1。

局部准入只覆盖 200 个目标、200 个资源、2 个侦察节点的冻结三维质点矩阵。它不代表 AirSim、
目标硬件或实飞实时能力。main 已依据独立 D6 准入结果，将 scalable 3D
`IntegratedStackConfig` 和 `run_episode` CLI 的默认实现晋级为
`known_dimension_structural_columns_v1`，并保留 `dense_output_probe_v1` 显式回退。该集成决策
不改变 D6 评估独立性，也不改变 D1 独立 `FusionAdapter` 的默认实现。scalable 测试已通过；
2v2 默认 smoke 的三处配置/摘要/治理表面均记录候选实现，有限状态为 true，在线真值使用为 0。
正式报告位于
`outputs/d1_structured_jacobian_multiseed_20260725_formal_9d1f54f_d6/`。
专项回归为 `20 passed, 1 warning in 6.05s`，D6 全量为
`818 passed, 1 warning in 55.42s`；warning 为既有 Matplotlib `Axes3D` 环境提示。

```bash
PYTHONPATH=research_modules/d6_evaluation_metrics \
python3 research_modules/d6_evaluation_metrics/scripts/evaluate_d1_structured_numerical_jacobian_multiseed.py \
  --evidence-manifest /path/to/evidence_manifest.json \
  --output-dir /path/to/independent_d6_report
```

`AIRSIM_INTEGRATION_PLAN.md` 已检查。本入口只消费三维质点离线证据，不改变 AirSim topic、相机、
actor、reset、检测或控制接口，因此无需修改。

## 2026-07-24 在线真值检查正式评估入口

D6 新增独立只读消费者 `online_truth_guard_multiseed.py` 和命令行
`scripts/evaluate_online_truth_guard_multiseed.py`。入口严格绑定：

- producer matrix schema
  `scalable3d-online-truth-guard-multiseed-matrix-v1`；
- matrix SHA-256
  `764574b9897d00101c26c555de2f407e1736c7e6ff50420eebf131e154618dc8`；
- clean source commit
  `8d8bb6ed7a417705236835f235361f45a021bb2b`；
- evidence/evaluator schema
  `scalable3d-online-truth-guard-multiseed-evidence-v1` /
  `d6.online_truth_guard_multiseed_evaluation.v1`；
- short seeds `1101-1110 @ 2.2 s`、long seeds `1101-1103 @ 10 s`；
- 200 个目标、200 个资源、2 个侦察节点；
- 参考/候选实现
  `generic_recursive_v1/builtin_specialized_recursive_v2`。

loader 只接受 13 pair、26 个 fresh complete arm。reused、失败返回、脏来源、错误 commit、旧
schema、命令漂移、路径越界和非登记 stderr 均直接拒绝。每个 arm 从 runtime profile、summary
和诊断交叉确认实际实现，并要求：

```text
truth_guard_validation_count = online_message_count > 0
online_truth_use_count = 0
```

D6 对每个输入路径计算 SHA-256，固定核对场景、运行配置、治理、阶段时序和诊断 schema。业务比较
只归一化预注册 selector、诊断、性能字段和处理派生 episode ID；在线消息、D1/D2 航迹与关联、
分配、控制计数、计划谱系、治理和离线真值继续严格比较。

性能主指标为 `module_publication_bus + module_publication_bus_finalize`。报告同时包含核心墙钟、
外层耗时、实时因子、D1 融合、D2 关联和最大常驻内存。short/long 分别使用 10000 次固定配对
bootstrap。准入门从冻结 matrix 读取：发布总线改善至少 10%，核心墙钟改善至少 0.5%，D1/D2
均值增幅和 RSS 增幅不超过 5%。输出为完整 JSON、compact JSON、逐 pair CSV、中文 Markdown
和 `SHA256SUMS`。

2026-07-24 已完成正式 13-pair/26-arm matrix 的独立只读消费。short 10 pair、long 3 pair 均为
fresh complete，0 reused、0 failed；13/13 pair 业务语义相等，在线真值使用为 0，参考与候选各
94074 条在线消息均满足检查数守恒。short 发布总线及收尾由 `0.900293 s` 降至
`0.696858 s`，改善 `22.58%`，10/10 更快；long 由 `3.810588 s` 降至 `2.834910 s`，
改善 `25.63%`，3/3 更快。

候选没有通过全部预注册门。short 核心墙钟改善 `2.50%`，但 long 核心墙钟回退 `3.47%`；
long D1 融合和 D2 关联分别增加 `5.29%`、`7.34%`，均超过 `5%` 上限。因此
`optimization_admitted=false`，候选 `builtin_specialized_recursive_v2` 保持默认关闭，默认仍为
`generic_recursive_v1`。候选最低实时因子为 `0.165369`，
`system_realtime_gap_closed=false`。正式 bundle 位于
`outputs/online_truth_guard_multiseed_20260724_formal_8d8bb6e/`。后续 balanced-order v2
只能作为独立诊断，不能覆盖本次 v1 正式结论；开发期三配对短测仍不进入正式证据。
本次同步专项为 `14 passed, 1 warning in 4.46s`，D6 全量为
`798 passed, 1 warning in 52.01s`；warning 是既有 Matplotlib `Axes3D` 环境提示。

```bash
PYTHONPATH=research_modules/d6_evaluation_metrics \
python3 research_modules/d6_evaluation_metrics/scripts/evaluate_online_truth_guard_multiseed.py \
  --evidence-manifest /path/to/evidence_manifest.json \
  --output-dir /path/to/independent_d6_report
```

## 2026-07-24 D1 常速度模型缓存正式评估入口

D6 新增独立只读消费者 `d1_cv_motion_model_cache_multiseed.py` 和命令行
`scripts/evaluate_d1_cv_motion_model_cache_multiseed.py`。入口固定绑定：

- matrix schema
  `scalable3d-d1-cv-motion-model-cache-multiseed-matrix-v1`；
- matrix SHA-256
  `9898656598f0fa282620afe2384a3d656b7496f8957109c413bcb62069fd2e9a`；
- clean source commit
  `44223566439a446fc49f2a3fd861d1d51bd676b9`；
- short seeds `1101-1110 @ 2.2 s`、long seeds `1101-1103 @ 10 s`；
- 200 个目标、200 个资源、2 个侦察节点、缓存容量 128；
- 参考/候选实现
  `per_prediction_build_v1/bounded_exact_lru_v1`。

loader 要求 13 pair、26 个 arm 全部为 `complete` 且返回码为 0，不接受 reused arm。它从
manifest runtime profile、runtime configuration、summary、module final、嵌套治理和独立治理
文件交叉确认 selector、实现 ID、诊断 schema、候选标志和容量。候选逐 arm 检查：

```text
prediction requests
  = nonpositive bypass + cache hit + cache miss + nonfinite bypass
model builds = cache miss + nonfinite bypass
entry count <= 128
peak entry count <= 128
```

参考臂不得出现 hit、miss、eviction、entry、peak 或 candidate nonfinite bypass，且
`prediction requests = nonpositive bypass + model builds`。缺失操作计数字段按 0 解释；未知字段、
负值、非整数、候选 hit/miss/build 为 0、两臂请求工作量不同均失败关闭。

D6 在每个 pair 内部调用 `compare_cross_build_episodes()`。只把
`same_runtime_profile` 作为预注册处理差异排除，并对常速度缓存 selector、诊断、处理派生 episode
标识和性能字段做窄范围归一化；在线消息、D3 计划谱系、D4 内容地址、其余 summary/governance 和
离线真值仍比较。在线真值使用必须为 0，状态和真值数组必须有限。

输出包含 D1 融合、D2 关联、核心墙钟、RSS、实时因子、模型构造减少率和缓存命中率。short/long
分别做逐 pair 相对变化和 10000 次配对 bootstrap。准入门直接消费并严格核对冻结矩阵：D1 融合
改善至少 5%，核心墙钟改善至少 2%，D2 关联增幅不超过 5%，RSS 均值和任一 pair 增幅不超过 5%，
模型构造减少率和命中率均至少 95%。局部准入和系统实时门分别输出
`d1_optimization_admitted`、`system_realtime_gap_closed`。

报告 bundle 含完整 JSON、compact JSON、逐 pair CSV、中文 Markdown、PNG 曲线和
`SHA256SUMS`，输出目录必须位于原始 evidence root 外。评估器实现时专项为
`13 passed, 1 warning in 5.03s`，D6 全量为
`784 passed, 1 warning in 48.64s`；warning 是既有 Matplotlib `Axes3D` 环境提示。

2026-07-24 已只读消费正式 13-pair/26-arm evidence。26 个 arm 全部为 fresh complete，
0 reused、0 failed；13/13 pair 的业务语义、有限状态、在线真值隔离、实现身份和缓存审计通过，
19/19 准入门通过。正式结果如下：

- short/long D1 融合改善 `6.9271%/6.6103%`，核心墙钟改善
  `2.4060%/2.4537%`；
- short/long D2 关联增幅 `-0.1082%/-2.6729%`，RSS 均值增幅
  `0.0145%/0.2959%`，任一 pair 最大 RSS 增幅 `0.8629%`；
- 模型构造减少率和缓存命中率均为 `99.5960%`，候选最大当前/峰值条目均为 `128/128`；
- short `10/10`、long `3/3` 的 D1 融合更快，short bootstrap 上界为 `-6.0841%`；
- `d1_optimization_admitted=true`。

候选最低实时因子为 `0.17394990897894075`，未达到 1，
`system_realtime_gap_closed=false`。正式 bundle 位于
`outputs/d1_cv_motion_model_cache_multiseed_20260724_formal_4422356/`。该准入只适用于冻结的
200/200/2 三维质点矩阵，不是 AirSim、目标硬件、传感器精度或实飞证据。
本次正式结论文档同步后，D6 全量回归为 `784 passed, 1 warning in 55.02s`；warning 仍是既有
Matplotlib `Axes3D` 环境提示。

```bash
PYTHONPATH=research_modules/d6_evaluation_metrics \
python3 research_modules/d6_evaluation_metrics/scripts/evaluate_d1_cv_motion_model_cache_multiseed.py \
  --evidence-manifest /path/to/evidence_manifest.json \
  --output-dir /path/to/independent_d6_report
```

## 2026-07-24 D1 发布元数据 v2 正式评估

D6 新增独立 v2 消费者 `d1_publication_metadata_v2_multiseed.py` 和命令行
`scripts/evaluate_d1_publication_metadata_v2_multiseed.py`。原 v1 evaluator、schema、测试和
历史报告保持不变。v2 入口只接受冻结矩阵
`51429554d58b82e94f922f7e0042144fd3440044f5188b51d77c578424d96927`，绑定 clean commit
`be399e138762f5e660f553c8caa812d52ab38c61`、13 pair/26 arm、200 个目标、200 个资源和
2 个侦察节点。

业务比较只对 D1 实现诊断、性能字段和 `d2_publication_metadata_audit` 处理差异做窄范围归一化。
D2 审计随后在 summary、module final、嵌套治理和独立治理文件四处严格校验。候选要求合同校验、
完整内容审计和共享子树完整审计计数一致且为正，身份复用为正，内建等价复用和拒绝为零；参考要求
完整审计和内建等价复用为正，全部 v2 计数为零。非白名单业务字段仍参与规范摘要和在线总线比较。

正式结果中，13/13 业务语义、有限状态、在线真值隔离、实现身份和 D2 审计通过。short/long 的
D1 融合平均改善为 `13.5447%/26.8298%`，核心墙钟改善为 `6.5677%/18.2438%`，D2 关联增幅为
`-16.1939%/-35.6213%`，全部预注册门通过，`d1_optimization_admitted=true`。候选最低实时因子
为 `0.17308010045846806`，所以 `system_realtime_gap_closed=false`。证据属于三维质点仿真，
不是 AirSim、目标硬件或实飞证据。

正式制品位于
`outputs/d1_publication_metadata_v2_multiseed_20260724_formal_be399e1/`。v1/v2 专项为
`37 passed, 1 warning`，D6 全量为 `771 passed, 1 warning in 47.61s`；warning 为既有
Matplotlib `Axes3D` 环境提示。

```bash
PYTHONPATH=research_modules/d6_evaluation_metrics \
python3 research_modules/d6_evaluation_metrics/scripts/evaluate_d1_publication_metadata_v2_multiseed.py \
  --evidence-manifest /path/to/evidence_manifest.json \
  --output-dir /path/to/independent_d6_report
```

## 2026-07-24 D1 航迹发布元数据正式评估

D6 新增独立只读消费者 `d1_publication_metadata_multiseed.py` 和命令行
`scripts/evaluate_d1_publication_metadata_multiseed.py`。输入固定为
`scalable3d-d1-publication-metadata-multiseed-evidence-v1`：同一 clean commit
`a36f519ed954a9ba8bdc3fe149ba2835da290c39`，short seeds `1101-1110 @ 2.2 s`，
long seeds `1101-1103 @ 10 s`，200 个目标、200 个资源、2 个侦察节点。参考臂为
`per_track_copy_v1`，候选臂为 `immutable_shared_v1`。

loader 精确校验冻结矩阵 SHA256、13 个 case、arm 顺序、命令隔离、26 个 complete/零返回码
episode、实际 selector、D1 `implementation_id`、不可变标志和操作计数。参考臂必须出现逐航迹
共享审计映射复制；候选复制数必须为 0 且共享复用数大于 0；两臂完整 `GlobalTrack` 元数据物化数
必须相等。所有 JSONL 采用逐行读取，D6 不把 4.2 GB 证据整体载入内存。

业务等价审计保留 D2 身份与 ID switch、D3 计划版本谱系、D4 内容地址和确认来源、D5/D7 输出、
在线非白名单字段及离线真值状态、标签和 5 米事件。允许差异只限预注册 selector、实现诊断和
操作数、性能/资源、由 runtime profile 派生的 episode ID/哈希及已验证的不透明计划编号。
在线真值使用必须为 0。26 个 stderr 仅含相同的已登记 Matplotlib `Axes3D` 环境警告；其他
stderr 内容失败关闭。

正式结果：

- D1 融合累计墙钟均值比：short `3.688192 -> 3.087261 s`，改善 `16.2935%`，
  `10/10` 更快；long `30.639399 -> 21.126366 s`，改善 `31.0485%`，`3/3` 更快。
- D2 关联累计墙钟：short `0.644394 -> 0.988737 s`，增加约 `53.44%`；
  long `5.713552 -> 15.420213 s`，增加约 `169.89%`。
- 核心墙钟：short `10.272705 -> 10.103672 s`，改善约 `1.65%`；
  long `66.643720 -> 65.840401 s`，改善约 `1.21%`。两组均未达到预注册 `5%`。
- 13/13 业务语义、有限状态、在线真值隔离、实现身份和 RSS 门通过。短、长核心墙钟门失败，
  所以 `d1_optimization_admitted=false`。
- 候选最低实时因子为 `0.14695931849644195`，所以
  `system_realtime_gap_closed=false`。

D2 反向开销的只读源码归因已确认：批量真值隔离审计的等值代表复用只接受精确内建容器，
候选只读映射/序列包装未通过该类型门，导致共享诊断树按每条航迹递归重扫。该结论要求 D1 与
D2 联合修复后重跑同一正式矩阵，当前候选不得按默认性能准入。

正式 bundle 位于
`outputs/d1_publication_metadata_multiseed_20260724_formal_a36f519/`，含完整 evaluation JSON、
aggregate JSON、逐 pair CSV、中文 Markdown、PNG 和 `SHA256SUMS`。原 4.2 GB episode 未复制。
证据属于三维质点仿真，不是 AirSim 或实机。2026-07-24 专项为 `27 passed`，D6 全量为
`761 passed, 1 warning in 41.25s`；warning 为既有 Matplotlib `Axes3D` 环境提示。

调用方式：

```bash
PYTHONPATH=research_modules/d6_evaluation_metrics \
python3 research_modules/d6_evaluation_metrics/scripts/evaluate_d1_publication_metadata_multiseed.py \
  --evidence-manifest /path/to/evidence_manifest.json \
  --output-dir /path/to/independent_d6_report
```

## 2026-07-24 D1 扫描输入同提交评估入口

D6 新增 `d1_scan_input_multiseed.py` 和
`scripts/evaluate_d1_scan_input_multiseed.py`，只读消费 main 生成的
`scalable3d-d1-scan-input-multiseed-evidence-v1`。输入固定为 short seeds
`1101-1110 @ 2.2 s`、long seeds `1101-1103 @ 10 s`、200 个目标、200 个资源和
2 个侦察节点。两臂必须来自同一 40 位 clean commit，参考实现为 `reference_v1`，
候选实现为 `candidate_v2`。

评估器精确核对冻结矩阵 SHA、13 个 case 及执行顺序、bootstrap `10000/20260724`、
全部准入门和 evidence boundary。每个 episode 从 manifest runtime profile、summary
顶层、execution config、performance diagnostics、module final diagnostics 和治理审计
交叉确认实现身份。运行配置、治理审计和 summary 只对明确登记的实现身份、性能计数、
墙钟、实时因子、treatment 派生 episode ID 和 final stage timings 做归一化；
final 中重复的 observation governance 使用顶层同一严格规则递归处理，其余字段保持严格等价。
在线总线继续核对 D3 不透明计划谱系、
D4 内容地址和确认引用，离线真值状态、标签和距离事件只参与等价审计。

逐 pair 提取扫描输入累计墙钟、P50、P95、最大值、核心墙钟、GNU time elapsed、RSS
和实时因子。short/long 分别输出配对相对变化、正向改善、候选更优计数、均值、中位数、
P95 和固定随机数的百分位 bootstrap 区间。报告 bundle 包含完整 evaluation JSON、
aggregate JSON、逐 pair CSV、中文 Markdown 和改善曲线 PNG。输出目录必须位于 evidence
root 之外，完整 JSON 保留所有消费文件 SHA256。

调用方式：

```bash
PYTHONPATH=research_modules/d6_evaluation_metrics \
python3 research_modules/d6_evaluation_metrics/scripts/evaluate_d1_scan_input_multiseed.py \
  --evidence-manifest /path/to/evidence_manifest.json \
  --output-dir /path/to/independent_d6_report
```

2026-07-24 专项正反例和只读检查为 `15 passed`。其中真实 summary 结构验证上述三类允许差异，
并确认非白名单业务字段变化仍会使评估失败。

正式证据来自 clean commit
`d14285e4fdeb2f2e2cd32fad2f6d42e30f9e73a7`。manifest SHA256 为
`760cd0e522b27b99de8c30c366ad7e65f16f783d71cf28e3492be299e24b2402`，
13 个 pair、26 个 arm 全部完成且退出码为 0。short 扫描输入累计墙钟平均改善
`5.360121886647966%`，候选 `9/10` 更快，配对原始变化 bootstrap 95% 区间为
`[-8.208165356448217%, -3.0841406102053194%]`；long 平均改善
`5.142481684491682%`，候选 `3/3` 更快，区间为
`[-8.837128529506151%, -1.6693612946922343%]`。short/long 核心墙钟分别改善约
`0.7187%/0.5792%`，RSS 组均值和逐 pair 门全部通过。

全部业务语义、有限状态、在线真值隔离和实现身份门通过，
`d1_optimization_admitted=true`。候选最小实时因子只有
`0.14342687633969603`，因此 `system_realtime_gap_closed=false`。D6 正式评估消费缺口已关闭；
系统实时、AirSim 和目标硬件证据继续开放。归档 bundle 位于
`outputs/d1_scan_input_multiseed_20260724_formal_d14285e/`，只保存独立 D6 报告及校验和，
没有复制 4.2GB episode evidence。该结论仅适用于冻结的三维质点场景。

## 2026-07-24 D1 协方差优化多 seed 与长时评估入口

D6 新增 `d1_covariance_limit_multiseed_long.py`。该入口复用现有显式 pair 读取与失败关闭逻辑，
用于 main 后续提供的 13 个 clean A/B 单元：

- short：seed `1101-1110`，每个 episode 世界时间 `2.2 s`；
- long：seed `1101-1103`，每个 episode 世界时间 `10.0 s`；
- v1 reference/candidate commit：
  `7cc2d0cfd598a72d60c6ba8c7d4a283f4e5a897d` /
  `95bf46e34321127313757986bb28bfb14b7e3c59`；
- v2 reference/candidate commit：
  `3c134c34655618b2e4d41302f9fbf3b6b4b78929` /
  `8c1188267c37c5e4a546abc8e7dd6c5a4bb48dba`；
- v3 reference/candidate commit：
  `a5a472cf81496d94a98db3deb88a3d5c6951f0ce` /
  `064cbb979d3bab68fee995e476df25709eb666db`；
- 规模：200 个目标、200 个资源、2 个侦察节点；
- 运行配置要求 `d1_d2_structural_ambiguity_hold_enabled=true`。

loader 只接受三个已登记实验。v1 保留原提交绑定；v2 还必须精确绑定
reference/candidate base commit、公共 D2 修复来源 `e4147b8`、修复主题
`fix(d2): align false alarm exclusion audit` 和 `v1_outputs_reused=false`。不能用 manifest
中的任意提交创建新实验，也不能在 v1 中混入 v2 谱系字段。

v3 的两个 base commit 均为 `064cbb979d3bab68fee995e476df25709eb666db`。公共 D1 修复固定为
`fix(d1): preserve covariance positive semidefiniteness`，参考臂 treatment 固定为
`test(d1): select scalar covariance reference`。证据边界必须同时声明 v1/v2 输出均未复用、
参考臂未启用向量化协方差限制、候选臂已启用。v1/v2 中出现任一 v3 专属字段也会失败关闭。

每个 `D1CovarianceLimitMatrixPairInput` 显式携带 group、seed、duration、reference/candidate episode、
两份 GNU `time -v` 资源记录和 cross-build JSON。评估器不读取目录名称推断 arm、seed、duration
或规模。每个 arm 必须为 clean manifest，提交、配置和运行配置哈希有效，规模正确，summary 有限，
在线真值使用为 0，进程退出为 0；cross-build 必须整体通过且规范化在线载荷一致。全矩阵进一步要求
场景配置删除顶层 `seed` 和 `duration_s` 后逐字节规范化摘要一致，runtime profile 全部相同。

main 可通过 `--evidence-manifest` 提供
`scalable3d-d1-covariance-limit-multiseed-evidence-v1`。D6 只接受状态为 `complete` 的 manifest，
先按 experiment ID 选择完整的已知 v1、v2 或 v3 注册，再核对内嵌矩阵的有效提交、可选谱系字段、
13 个 case 的顺序和元数据、200/200/2 规模、
运行参数、准入门、bootstrap 设置，以及固定 runtime profile 摘要
`deabac3fbf2a788f68a0b807945e5f1bedacf8c5917c4d3b49c5cffb3c90da70`。每个 arm 必须显式声明
`reference` 或 `candidate`、正确的 `expected_commit`、`complete|reused` 状态和零返回码；
cross-build 状态必须为 `passed`。episode、资源记录和 cross-build JSON 从字段直接读取并要求存在，
不根据路径名称推断实验语义。`--evidence-manifest` 与兼容的重复 `--pair` 入口互斥。

short 和 long 分别输出每 seed 配对值，以及 reference/candidate 的均值、中位数、P95、配对相对
变化分布。配对相对变化定义为 `(candidate-reference)/reference`。确定性 bootstrap 固定使用
10000 次重采样和 RNG seed `20260724`，重采样单位为完整 seed pair，输出配对相对变化均值的 95%
百分位置信区间。P95 使用 `(n-1)` 位置的线性插值。

分组指标显式携带 `improvement_direction`。wall、P95、scan、core、external elapsed 和 RSS 为
`lower_is_better`，实时因子为 `higher_is_better`。原始 `mean_relative_change_pct`、
`candidate_lower_count` 和 bootstrap 区间保持兼容；新增 `candidate_better_count`，并将
`mean_improvement_pct` 统一解释为正值代表候选更优。bootstrap 仍报告原始相对变化方向，不翻转
符号。

固定报告 bundle 新增
`d1_covariance_limit_multiseed_long_improvements.png`。上半图绘制 short 10 个 seed 与 long
3 个 seed 的 D1 融合配对改善；下半图比较两组的 D1 融合、融合 P95、核心墙钟、外部 elapsed 和
实时因子方向化均值改善。正值统一表示候选更优，实时因子按越高越好，其余绘制指标按越低越好。
RSS 继续保留在 JSON、CSV 和 Markdown 的资源审计与准入门中，不进入主图。writer 只有在 13 个
配对和五项分组指标完整、方向一致且数值有限时才生成 PNG；缺 pair 或指标不可用时删除旧图并失败
关闭。CLI 的 `outputs` 同步返回固定 `png` 路径。

seed `1101-1103` 同时存在 short 和 long。对 D1 fusion、核心 episode wall 和外部 elapsed 分别
计算：

```text
unit_cost_growth =
    (long_cost / long_duration) / (short_cost / short_duration)
candidate_relative_degradation =
    candidate_growth / reference_growth - 1
```

核心 wall 与外部 elapsed 始终分层，不能相加。正式准入门固定为 short D1 fusion 至少 8/10 更快、
均值改善至少 5%、bootstrap 95% CI 上界小于 0、P95 聚合改善；long 至少 2/3 更快且均值改善至少
5%；candidate 的 D1 长短单位成本增长相对 reference 任一同 seed 恶化不超过 5%；short/long 的
core wall 和 RSS 均值恶化不超过 5%，任一 RSS pair 恶化不超过 5%；矩阵、语义、有限状态、真值和
退出门全部通过。

输出接口生成机器 JSON、13 行逐 pair CSV、中文 Markdown 和固定二维 PNG。CSV 固定使用 LF。
系统实时性单独输出：该预注册矩阵是三维质点证据，不包含 AirSim 或目标硬件运行条件，因此
`system_realtime_gap_closed` 不由该矩阵关闭。

当前只完成 evaluator、v1/v2/v3 manifest loader 和测试 fixture。旧 v1 矩阵曾运行到 long seed 1102
reference；旧 D2 producer 将 14 个“纯已知虚警处置组”写入
`known_false_alarm_only_mapping_count`，但持久化帧中只有 11 条
`status=excluded && reason=known_false_alarm_only`，另 3 条为
`source_observation_outside_lineage_window` 的 unavailable mapping。D6 按持久化最终映射执行
精确计数，旧 `14/11` 证据失败关闭；D2 修复后的 producer 写出 `11/11` 才能通过。

main 已完成正式 v3 manifest 和首次报告。首次报告将越高越好的实时因子沿用了越低越好的展示
口径，把 short/long 原始增长 `+3.222%/+3.601%` 写成负改善并显示 0/N 更优。当前 evaluator 已
修正为 short `10/10`、long `3/3` 候选更优，改善值为正；原始相对变化和 bootstrap 区间保持正值。
该修复不改变正式 evidence、提交绑定、准入门或 `d1_optimization_admitted`。正式报告需由 main
使用同一 manifest 重生。

多 seed 专项为 `69 passed, 1 warning`，D6 全量为
`719 passed, 1 warning in 24.65s`。新增回归检查 PNG 固定文件名、签名、非空内容、CLI 输出以及
缺 pair/缺指标失败关闭。warning 为既有 Matplotlib `Axes3D` 环境提示。

## 2026-07-24 D1 协方差成对限制向量化准入

D6 新增 `d1_covariance_limit_clean_pair.py`，对 main 显式列出的三轮 reference/candidate
证据做独立只读复核。输入必须逐轮提供两个 episode 目录、cross-build 语义等价 JSON 和两份 GNU
`time -v` 资源记录；评估器不扫描目录名推断实验臂或规模。现有
`evaluate_scalable_3d_episode()` 继续负责 manifest、场景配置、在线真值和 v2 阶段时序读取，
新增入口独立核对资源文件中的外部 elapsed、最大常驻内存和退出状态。

每轮要求 manifest 为 clean、参考/候选提交分别等于
`7cc2d0cfd598a72d60c6ba8c7d4a283f4e5a897d` 和
`95bf46e34321127313757986bb28bfb14b7e3c59`，并要求配置摘要、seed、运行配置摘要、场景版本、
200 个目标、200 个资源、2 个侦察节点和 2.2 秒世界时间一致。summary 必须全部为有限数，
`finite_state=true`、`online_truth_use_count=0`、观测数为 2035；cross-build 必须整体通过且
规范化在线载荷一致；六个进程退出状态均须为 0。

准入门要求 D1 融合累计墙钟 3/3 更快、三轮均值至少下降 5%，episode 内调用 P95 的三轮均值下降，
核心墙钟均值不恶化且至少 2/3 更快，最大常驻内存的均值和任一轮增幅均不超过 5%。核心 episode
墙钟与外部进程 elapsed 分层报告，不相加。D1 scan input 是独立阶段，只作描述性核对；D2、D3、
D7 的单 seed 调度波动不归因于本项 D1 优化。

2026-07-24 三轮 clean 结果为：

- D1 融合累计墙钟均值 `4.014713519 -> 3.595533106 s`，下降 `10.4411%`，3/3 更快；
- D1 融合单次 P95 的逐 episode 均值 `184.228658 -> 173.330868 ms`，下降 `5.9154%`；
- 核心墙钟均值 `10.561416472 -> 10.229605524 s`，下降 `3.1417%`，3/3 更快；
- 外部 elapsed 均值 `18.176667 -> 17.516667 s`，下降 `3.6310%`；
- 最大常驻内存均值 `1,076,584 -> 1,075,045.333 KiB`，下降 `0.1429%`；
- D1 scan input 均值增加 `0.3607%`，不进入准入门。

三轮业务语义、有限值、真值隔离和退出状态全部通过，`d1_optimization_admitted=true`。候选实时因子
均值只有 `0.215065`，且本批只有 seed 1100 的三次 2.2 秒三维质点重复，不是多 seed、AirSim、
均方根误差、归一化估计误差平方或归一化创新平方证据，因此
`system_realtime_gap_closed=false`。机器 JSON、逐轮 CSV 和中文报告位于
`outputs/d1_covariance_limit_clean_pair_20260724/`。新增正例、CSV 纯 LF 写入及 cross false、
配置/seed 不一致、真值非零、阶段缺失、退出非零和内存越门负例共 `9 passed`；D6 全量为
`646 passed, 1 warning in 21.65s`，warning 是既有 Matplotlib `Axes3D` 环境提示。

## 2026-07-24 D1 原子影子旁路只读兼容

D6 在既有 `scalable3d-d1-centroid-overlay-shadow-v1` 消费器内增加执行模式分派。历史无准备
审计记录继续按 `legacy_uninstrumented_runtime_v1` 读取；历史五字段
`canonical_preparation` 按 `legacy_prepared_handle_v1` 严格校验。新记录只有在 payload 顶层显式
声明 `overlay_execution_mode=atomic_experimental_offline_v1` 时，才按原子入口解释
`prepared_publication`、`post_integrity_check`、canonical/shadow publication digest、
`shadow_materialized`、原子工作量和 `atomic_failure_reason`。

原子记录要求字段集合完整且无 legacy 混入。准备工作必须完成一次全发布描述，航迹、状态、协方差
摘要计数需与有效航迹数一致；操作后完整性计数需与原子工作量一致。accepted 记录必须物化一个脱离
正式链路的 shadow 并给出摘要，普通 rejected 记录不得产生 shadow 工作，原子失败必须保持
accepted 为 0 且不暴露可用 shadow。缺字段、未知模式、摘要与物化冲突或计数矛盾均使该记录失败
关闭。历史记录没有原子字段时，原子工作量和失败指标保持 `null/unavailable`，不补零。

D6 只读取持久化日志，不向 D1、main、D2/D3 或控制链返回结果。2026-07-24 确定性专项
`25 passed`，D6 全量 `637 passed, 1 warning in 21.89s`。既有 seed 1100 prepared-handle 文件的
9 条记录均按 legacy 模式读取，9/9 完整性检查通过。warning 为既有 Matplotlib `Axes3D` 环境提示。

main 随后在 clean commit `7cc2d0cfd598a72d60c6ba8c7d4a283f4e5a897d` 完成 seed 1100、200 对
200、2.2 s 的 control/atomic-shadow pair。D6 从原始总线、summary 和 v2 阶段时序独立复算：
9 条 atomic 记录全部通过 post-integrity，累计覆盖 1813 条 canonical 航迹摘要；46 个 decision
全部因 `oosm_scan` rejected，accepted/error/atomic failure/materialized 均为 0，shadow
copy/full digest/publication digest 工作量均为 0。`global_track_id` 变化、禁止表面违规、D2/D3
消费和在线真值使用均为 0，业务非干预通过，evidence failure 为空。

control/shadow 墙钟为 `10.735151270986535/19.449935468961485 s`，相对开销
`0.8117989190825889`。影子评估 P50/P95/max 为
`1024.8383930302225/1536.4285601885058/1549.4359389995225 ms`。性能门失败；accepted treatment
为 0，outcome evidence 不可用，`overall_admitted=false`。该 clean 单 seed 关闭了真实 atomic
rejected-only 消费缺口；真实 accepted、真实 atomic failure、多 seed 性能和处理效果仍未提供。

## 2026-07-23 D1 质心发布影子旁路只读评估

D6 新增 `d1_centroid_overlay_shadow.py`，只读取 main episode 总线中的
`audit.d1.centroid_publication_overlay_shadow`、最终模块诊断和阶段时序。输入 schema 固定为
`scalable3d-d1-centroid-overlay-shadow-v1`，D6 输出口径为
`d6.d1-centroid-overlay-shadow-readonly.v1`。实现不导入 main、D1 或可扩展三维运行代码，不写控制
状态，也不把指标放入通用 `EpisodeMetrics`。可扩展三维离线输出升级为
`d6-scalable3d-offline-evaluation-v9`。

评估逐域输出 `value/availability/unavailable_reason`，覆盖：

- canonical/shadow 航迹摘要可评估数、相等数和不同数；
- `global_track_id` 序列不变/变化计数；
- 禁止表面修改、正式航迹替换、D2/D3 消费和在线真值使用；
- accepted、rejected、error 及拒绝原因分布；
- `measurement_timestamp`、`arrival_timestamp` 和双时间戳完整发布数；
- 每条 `evaluation_wall_time_ms` 重算的 P50/P95/max，并与阶段时序交叉核对；
- generation watermark 当前值、峰值、容量和 shadow payload 峰值字节数。

`forbidden_mutation_audit` 必须声明
`sha256_of_canonical_track_and_evidence_digest_manifest_v1`，并分别携带 canonical tracks 与结构
歧义 evidence 的前后 SHA-256。D6 重算两层摘要，任一对象前后变化、摘要语义未知或 manifest 摘要
不一致均失败关闭。

`shadow SHA != canonical SHA` 只表示脱离正式链路的实验副本发生变化。业务非干预使用独立字段
`d1_centroid_overlay_shadow_business_nonintervention_passed`，要求逐条日志与最终摘要一致、全局航迹
编号序列不变、禁止表面无违规、正式航迹未替换、D2/D3 消费为 0、在线真值使用为 0。该判据不要求
shadow SHA 与 canonical SHA 相等。缺字段、未知 schema、阶段分布缺失、摘要不一致或消费非零均
失败关闭；历史 episode 未声明 A2 能力时保持 `null/unavailable`，不补零，也不影响原有正式证据。

2026-07-23 的确定性验证包含 11 个适配器测试和 1 个 episode 接入正例。两条日志正例包含 1 个
accepted、1 个 rejected，`global_track_id` 不变 2/2，D2/D3/在线真值使用均为 0，业务非干预通过。
测试时序仅为夹具值，用于验证 P50/P95/max 接线，不是运行性能。专项 `11 passed`，scalable 与后验
治理联合回归 `77 passed`；D6 全量回归为
`623 passed, 1 warning in 21.67s`。warning 是既有 Matplotlib `Axes3D` 环境提示。

同日 D6 只读消费 development/dirty 的 seed 1100、200 对 200、2.2 s control/shadow pair。两臂
config SHA-256 均为 `20ef5248c8b45ff5aced9080c8d47e65a43aaba54f18ce824dc50fac7a52b840`，
来源提交均为 `2b976a7213ccdaa35fe0e22dea88def2651e9467`。shadow 有 9 条
sidecar、46 个 decision，accepted/rejected/error=`0/46/0`，拒绝原因全部为 `oosm_scan`；
`global_track_id` 变化、forbidden mutation、D2/D3 consumption 和 online truth use 均为 0，因此
业务非干预通过。每条日志重算的开销 P50/P95/max 为
`1009.256/1532.999/1619.053 ms`，与 stage timing 一致；watermark 当前/峰值/容量为
`8/8/1024`，shadow DTO 峰值为 `11,275,939 B`。

control/shadow episode 墙钟为 `10.712171729/19.376483415 s`，相对开销比为
`0.808828677`（`80.88%`），未通过不高于 `+5%` 的配对性能门。accepted 为 0，当前也没有
treatment outcome。D6 输出保持
`business_nonintervention=true`、`performance_gate=false`、`overall_admitted=false`。该 pair
来自 dirty 工作树且只有一个 seed，只能作为描述性开发诊断，不形成正式性能或算法收益结论。
AirSim、多 seed、clean/frozen 性能和有效 treatment 证据尚未提供。

## 2026-07-23 离线观测三态处置

D6 已将可扩展三维离线观测真值从 target-only v1 扩展为 disposition-aware v2 消费合同。
`observation_truth_sidecar.py` 独立校验 main 原始 sidecar 和 D2 归一化 sidecar，不导入
main、D1 或 D2 运行代码。当前 schema registry 为 `d6-scalable3d-schema-registry-v2`，
正式当前值为 `scalable3d-offline-truth-v2`；离线评估输出升级为
`d6-scalable3d-offline-evaluation-v8`。

main 原始 v2 记录必须包含：

```text
schema_version = scalable3d-offline-truth-v2
observation_id
measurement_timestamp
disposition = target | known_false_alarm | unknown
truth_entity_id = 仅 target 非空；其余两态必须为 null
```

D2 归一化 v2 使用 `d2.scalable3d_observation_truth.v2`。target 记录携带
`truth_target_id`，known false alarm 和 unknown 记录不得携带该字段。D6 不从
`observation_id`、距离、actor/object 名称或在线状态推断 disposition。sidecar 混用 schema、v2
缺 disposition、非法状态、目标身份与状态冲突、重复 observation 或 manifest 声明与记录不一致时
失败关闭。

每个 episode 分别输出 target label、known false alarm、unknown 和 missing disposition 的
availability、count 与 reason。v1 继续可读，全部记录按 v1 schema 合同视为 target；v1 无法表达的
known false alarm 和 unknown 计数保持 `null/unavailable`，不得写成 0。v2 的 known false alarm
不进入目标身份映射；存在 unknown 时 strict identity eligibility 为 false。D6 只消费 D2 strict
IDSW 的原 availability/value，不使用部分映射或处置计数回填。

`runtime_plan_outcome_join` 对 D2 sidecar 文件、identity evaluation 和 identity manifest 的
SHA-256 逐项绑定，再交叉核对 D2 audit 中的 schema 和三态计数。`truth_isolated_offline` 只拿到
D2 已归一化结果时，计数来源明确记录为
`identity_evaluation.audit.observation_truth_disposition_counts`，来源摘要为
`source_hashes.observation_truth_labels`；旧 D2 audit 未声明 schema 时，三态计数保持 unavailable，
既有 strict 指标仍按原合同读取。

D2 audit 的 `known_false_alarm_only_mapping_count` 只统计持久化最终映射中同时满足
`status=excluded` 和 `reason=known_false_alarm_only` 的记录。D6 在 truth-isolated 和 runtime join
两条路径都从 `frames[].mappings[]` 独立计数并要求精确相等；由谱系窗口等其他原因形成的
unavailable mapping 不进入该计数。audit 与帧映射出现 `14/11` 一类差异时保持失败关闭。

本轮没有重跑历史 20-seed episode，也没有将旧 v1 证据宣称为 v2 结果。确定性专项覆盖 v1、v2 三态、
缺 disposition、非法状态、身份冲突、重复冲突、schema 篡改、D2 audit 计数篡改和 unknown
fail-closed。新增处置及相关专项 `130 passed`，D6 全量
`586 passed, 1 warning in 21.99s`，scalable learning export 联调
`5 passed, 1 warning in 3.13s`。warning 为既有 Matplotlib `Axes3D` 环境问题。AirSim 日志、
reset、话题和控制接口未变化。

## 2026-07-22 scalable 3D 阶段分位接入

D6 已接入 `scalable3d-stage-timings-v2`，离线评估输出升级为
`d6-scalable3d-offline-evaluation-v7`。v2 每个阶段必须给出 schema、累计调用数、累计墙钟、
单次均值、P50、P95、最大值以及显式分布可用性。分布可用时三个分位值必须齐全、有限、非负，
满足 `P50 <= P95 <= max`，不可用原因必须为空；分布不可用时三个值必须全部为空并给出原因。
重复阶段、半缺字段、未知 schema、非有限数、顺序错误和均值大于最大值均失败关闭。

历史无 schema 的 CSV 继续可读。没有分位列时，P50/P95/max 为 `null/unavailable`；有完整三列时
由三项是否全部存在推断可用性。legacy 半缺三项同样拒绝，不能把缺失值补成 0。

逐 episode CSV 为每个阶段输出三个分位及各自 availability。跨 seed 聚合统计的是“每个 episode
内部单次调用分位”在不同 seed 上的分布，并记录可用 episode/seed 数和缺失原因。D6 没有原始逐调用
样本，因此 `pooled_call_quantiles` 固定 unavailable，不把 seed P95 写成所有调用的合并 P95。中文
报告新增阶段尾延时表，并明确 5v5 冒烟不能作为 200 对 200 验收。

2026-07-22 验证覆盖正常 v2、显式不可用 v2、三类 legacy、半缺字段、未知 schema、非有限值、
分位顺序、均值上界、重复阶段和跨 seed 混合 availability。2026-07-23 当前权威 D6 全量测试为
`567 passed, 1 warning in 22.96s`；相较上一版 555 项，新增 12 项均来自
`test_truth_isolated_offline.py` 的部分身份合同，其中 3 项为独立正负合同，9 项为篡改参数化用例。
warning 是既有 Matplotlib `Axes3D` 环境问题。阶段分位当前只完成 consumer、聚合和报告合同。
main 仍需用包含 v2 分位的 clean 200 对 200 多 seed episode 重跑，才能形成真实阶段尾延时证据。

## 2026-07-22 clean 20-seed runtime v2 复核

D6 独立复核了 clean commit
`0d2da25c14e50f8f9a10ad47a7bd74e5c5e577fb` 的 nominal 200 对 200、10.0 s、
seed `1000-1019` 批次。20/20 episode 状态有限，`repository_dirty=false`，
`online_truth_use_count=0`，分配 hold 为 0，源进程退出码为 0。D6 v6 输出中 20/20
episode 均通过后验代次合同，pending 全部排空：

- D1 最终代次、D2 最终消费代次逐 seed 相等；D1 完整后验发布数也与最终代次相等；
- D2 消费次数与实际 D2 发布数相等；
- D2 消费次数加节拍前合并次数与 D1 最终代次相等；
- D1 最终代次均值为 `471.65`，范围 `410-499`；D2 消费次数均值为 `47.95`，
  范围 `47-48`；节拍前合并次数均值为 `423.7`。

D3 计划覆盖率均值为 `0.989606`，按不同 seed 重采样的 95% bootstrap 置信区间为
`[0.987144, 0.991813]`。D5 绑定数均值为 `25.95`，范围 `9-41`；该数值只描述
10.0 s 名义窗口。20 个 episode 均无 5 m 接近事件，不能证明物理拦截。

聚合中的 `formal_acceptance_eligible_episode_count=20` 只表示基础 clean provenance、schema、
真值隔离和代次合同通过。全部 episode 仍归类为
`descriptive_clean_source_calibration`，实验矩阵 episode 数为 0，不能称为正式算法矩阵或完整
20-seed 算法验收。聚合 JSON 和中文报告 SHA-256 分别为
`da9525ac0f189e2a1f281f5baa4af2ab22d12c43c0f3a2f5738ff06a446c9022` 和
`924745063e9f443bba0ea36cf5263eb6ed6ccf1ae52fe0d768abc204c840f734`。输出位于
`outputs/scalable3d_posterior_v2_unseen_20seed_clean_0d2da25_20260722/`，作为生成制品不纳入源码
追踪。

D6 评估器的 `3:20.42` 墙钟和 `1,448,612 KiB` 峰值常驻内存来自 main 侧进程测量，不是上述五个
D6 输出制品中的可恢复字段，因此只作为运行诊断登记。此前三 seed 结果仍保留为 runtime v2 首批
正例；本批关闭的是 clean 未见 20-seed 代次合同输入缺口，不改变正式实验矩阵和物理效果边界。

## 2026-07-22 D1-D2 后验代次被动审计

D6 已在可扩展三维离线评估中接入 `scalable3d-observation-governance-runtime-v2`。评估同时读取
`summary.module_final_diagnostics.observation_governance` 和持久化在线总线，不导入 D1/D2 运行时，
不读取在线真值。D1 完整后验的 `posterior_generation` 必须从 1 连续递增；D2 的
`source_d1_posterior_generation` 必须严格递增、不得重复，并且只能引用此前已发布的完整后验。

最终快照还需满足 pending generation 为空，D2 consumed generation 等于 D1 generation，
consumption count 等于实际 D2 publication 数，且 consumption count 加 pre-tick merge count 等于
D1 generation。最终 consumed generation 同时与最后一次 D2 来源一致。
任一矛盾进入 episode 失败原因并使 formal acceptance 失败关闭。历史 runtime v1 因未发布这些
字段，所有代次指标为 `null/unavailable`，不会被写成 0。

离线评估 schema 升级为 `d6-scalable3d-offline-evaluation-v6`。报告新增后验代次表。CLI 可用
`--module-performance-json` 显式登记 D1/D5 独立性能 JSON；登记项固定为描述性模块证据，不能解释为
全栈实时能力或控制效果。专项测试 `58 passed`，D6 全量测试 `542 passed, 1 warning`，耗时
21.82 s。warning 是既有 Matplotlib `Axes3D` 环境问题。

main 随后在 clean commit `0d2da25c14e50f8f9a10ad47a7bd74e5c5e577fb` 上完成 nominal
200 对 200、10.0 s、seed `42000/42001/42002` 的 runtime v2 校准。v6 consumer 得到：

| seed | D1 final/full pub | D2 final/consumption/pub | pre-tick merge | pending empty |
| ---: | --- | --- | ---: | :---: |
| 42000 | 453/453 | 453/48/48 | 405 | true |
| 42001 | 516/516 | 516/48/48 | 468 | true |
| 42002 | 505/505 | 505/48/48 | 457 | true |

三个 episode 均 `formal_acceptance_eligible=true`、失败原因空、在线真值使用为 0。证据分类为
`descriptive_clean_source_calibration`，没有实验矩阵 metadata，不能写成 20 未见 seed 验收或正式
算法矩阵。报告位于
`outputs/scalable3d_posterior_v2_clean_0d2da25_20260722/`。v6 评估日期已修正为
`2026-07-22` 并重生成该目录的 CSV、aggregate 和中文报告。

## 2026-07-22 200 对 200 长时三 seed 集成校准

main 在 clean worktree 上使用相同 nominal 200 对 200 配置、10.0 s 世界时长和 seed
`42000/42001/42002`，对 reference `8f86192` 与 candidate `f80b5bd` 做了跨提交复核。candidate
三个 episode 均为有限状态，`online_truth_use_count=0`，D1、D2、D3、D5、D7 最终输出数量与
reference 一致。逐条语义审计在校验原始 ACK 载荷 SHA-256 后，只把 D3 的不透明随机 `plan_id`
按计划出现次序和版本规范化；owner、version、coalition、`global_track_id`、命令及其他业务字段均未
忽略。三个 seed 全部通过。

| 进程级口径 | reference 均值 | candidate 均值 | 变化 |
| --- | ---: | ---: | ---: |
| 仿真核心墙钟时间 | 155.895422 s | 150.874890 s | -3.22% |
| 进程总墙钟时间 | 222.780 s | 195.363 s | -12.31% |
| 峰值常驻内存 | 2.888697 GiB | 2.359147 GiB | -18.33% |
| 进程残差，进程总墙钟减核心墙钟 | 约 66.885 s | 约 44.488 s | -33.49% |

candidate 的 `post_run_timings.csv` 将写盘后处理总量测为
`39.274048705/41.663056382/40.982858311 s`，均值 `40.639988 s`。reference 没有该制品，因而
跨提交残差只能表示核心计时之外的整体成本，不能称为某个 D6 函数的耗时或加速比。D6 的 JSONL
流式校验避免整文件常驻内存，D2 identity 索引避免每个绑定窗口重复扫描；main 同次序列化写出的
规范 D1/D2 视图供离线身份评估复用，避免再次遍历完整在线总线。这三项共同减少后处理时间和内存，
但不能从当前进程级数据中拆分各自贡献。

D6 三 seed 聚合结果为 `episode_count=3`、`formal_acceptance_eligible_episode_count=3`、
`repository_dirty_episode_count=0`、`failure_reason_distribution={}`。三个 episode 的证据状态仍是
`descriptive_clean_source_calibration`，且没有冻结实验矩阵 metadata。该结果不是正式 20 个未见
seed 验收。candidate 三个 seed 的实时因子约为 `0.067/0.064/0.068`，长时比较仍标记 D1 扫描输入、
D1 融合、D2 关联、D5 主动视觉、D5 终端关联、D7 导引和模块栈为超线性阶段，因此实时 P1 保持开放。
本次文档同步后 D6 全量回归为 `530 passed, 1 warning`；warning 是既有 Matplotlib `Axes3D` 环境问题。

## 2026-07-22 runtime plan outcome join 严格等价性能优化

`runtime_plan_outcome_join.py` 现逐行解析完整在线 JSONL。每条记录仍校验唯一 JSON key、有限数、
envelope 精确字段、严格递增 sequence 和全部层级的 truth-like key；禁用键检查融合到 JSON
`object_pairs_hook`，不再在解码后递归遍历同一对象树。过滤发生在完整解析与真值检查之后，因此即使
`runtime.camera_command_ack` 等非联接主题包含 Unicode 转义的 `ground-truth`，独立 D6 入口也会以
`online_truth_field_present` 失败关闭。实现没有调用方布尔跳过开关，也没有仅凭“main 已检查”绕过
真值隔离。

D6 只长期保留后续合同实际需要的 D1 fused tracks、D2 associated tracks、D3 assignment、D7 guidance
和 main assignment ACK。D1/D2 在线记录在解码后保存规范整行 SHA-256，并立即释放大载荷；离线 D2
过滤源仍逐条重算规范摘要后比对。D2 identity 完成原有逐帧类型、顺序和重复航迹校验后，只建立一次
`global_track_id -> [(frame_time, mapping)]` 只读索引，所有窗口继续使用原有 freshness、availability、
歧义和时间边界公式。

固定 A/B 输入为 development 制品
`point_mass_integrated_observation_smoke_20260722_development_coalesced/nominal/200v200/seed_42000`，
input spec SHA-256 为 `1e41bc47e2ea0215674285e770054c45f52c32405c8e9566631a21d9ebc2c24a`。
场景为 200 对 200、2.2 s、seed 42000；在线文件为 63,014,782 B、3380 条 envelope，全部 3380 条
执行真值检查，仅 130 条保留，其中 95 条 D1/D2 只保留规范摘要、35 条 D3/D7/ACK 保留载荷；输出
包含 3 条 ACK 和 594 个绑定窗。`8f86192` baseline 与 candidate 在同一 Python 3.12 进程内交替运行
3 次，`perf_counter` 阶段均值如下：

| 阶段 | baseline/s | candidate/s | 降幅 |
| --- | ---: | ---: | ---: |
| `evaluate_runtime_plan_outcomes` | 5.302515 | 2.901966 | 45.27% |
| `_load_online_envelopes` | 2.777838 | 1.506296 | 45.77% |
| `_load_and_validate_d2_identity` | 1.544734 | 0.866780 | 43.89% |
| `_build_binding_windows` | 0.451765 | 0.028150 | 93.77% |

candidate cProfile 的 evaluate/online-load 为 3.651/2.473 s；旧递归 truth guard 已消失。两个独立
新进程的单次 `/usr/bin/time` 结果为 baseline 5.03 s、289,716 KiB，candidate 2.58 s、142,000 KiB；
该单次 RSS/进程墙钟只作本机开发期描述，不是部署门限。

两版报告 mapping 完全相等。规范业务 JSON SHA-256 同为
`7325b46857163ed692b13ae84d83834dae1282c07ac554839fd7575d7dcec0a7`；漂亮打印 JSON 与中文
Markdown 文件 SHA-256 分别保持
`10db519870924a221ff2b197519dea0c4514195843425876f56dc1612b4158d3` 和
`97a364f1e347b829c0fe3375244a5026fc31c3a1f331526b4669d254cc255d76`。admission、availability、
contract/control/physical 分层、正式 reward/counterfactual/causal 空值及规则回退均未改变。
专项 `25 passed`，D6 全量 `530 passed, 1 warning`；warning 仍为本机 Matplotlib `Axes3D` 环境问题。

剩余 P1 是对长时、多 seed、clean/frozen 输入建立正式容量门限，以及在确有跨进程复用需求时设计
版本化、绑定源文件 SHA 和真值策略版本的 main 审计证明。该证明尚未实现；独立 D6 文件入口继续默认
重验每条在线记录。当前主要剩余 CPU 热点是完整 JSON 解码和 D1/D2 规范摘要，不能通过放宽隔离删除。

## 2026-07-22 Scalable 3D 批次根发现修复

`run_scalable_3d_offline_evaluation.py --episode-root` 递归扫描批次目录时，原实现只检查
`manifest.json`。每个主 episode 下的 `d6_truth_isolated`、`offline_identity`、
`offline_consistency` 等 sidecar 也有 manifest，因而会被错误送入 episode 评估。sidecar 缺少
在线记录后，状态收口又对 unavailable 的 `None` 计数执行 `int()`，导致整批报告中止。

发现阶段现要求同一目录至少同时存在 `manifest.json`、`scenario_config.json` 和 `summary.json`。
这三项只用于区分主 episode 与 sidecar。在线日志、阶段时序、近距事件和离线真值等制品仍由
评估器逐项判断；缺失时保留 `null/unavailable+reason`。显式
`--episode-dir` 继续直接评估调用方指定目录，历史记录不会因缺少可选制品而被发现逻辑静默丢弃。

状态收口仅对 availability 为 available 且值为非负整数的计数做比较。缺字段、缺文件和 `None`
不再按零处理，也不会触发类型转换异常。无实验矩阵声明但基础 clean provenance 完整的 episode
标记为 `descriptive_clean_source_calibration`；只有实验矩阵合同完整并通过时才标记
`clean_formal_experiment_matrix`。

2026-07-22 使用
`scalable_3d_rule_performance_calibration_20260722_clean_492979e` 复核：修复前递归命中
100 个 manifest 目录，其中 80 个为 sidecar；修复后只发现 20 个主 episode，四档规模各 5 seed，
sidecar 混入为 0，CLI 以 2000 次 bootstrap 完整生成 CSV、JSON、中文 Markdown 和时序曲线。
20/20 来源 `repository_dirty=false`，20/20 缺实验矩阵声明，最终均为
`descriptive_clean_source_calibration`。本次只修复离线输入发现和空值收口，不新增精度、实时性、
AirSim 或物理拦截证据。专项 `46 passed`，D6 全量 `527 passed`；仅保留既有 Matplotlib
`Axes3D` 环境 warning。

## 2026-07-22 长 Episode 观测治理标定合同

D6 新增 `scalable3d-observation-governance-calibration-v1` 只读评估合同，用于 main 后续
生成的 20/50/100/200 及其他动态规模长 episode。实现位于
`d6_evaluation_metrics/observation_governance_calibration.py`，命令行入口为
`scripts/run_observation_governance_calibration.py`。该路径只读取 episode 结束后的公共
JSON 制品，不导入 D1/D2 runtime，也不回写控制状态。

输入分为批输入清单、episode manifest、在线治理审计和可选 evaluator-only 侧车。每个
episode 显式记录 `scale/target_count/resource_count/seed/duration_s`、完整 Git commit、
clean/dirty、证据层级、配置 SHA-256 和 world/bus/scenario/observation/D1/D2 schema。
在线审计覆盖 D1 OOSM 缓冲、重排、拒绝、过旧、溢出、淘汰和内存估算，以及 D2 当前/峰值
claim、淘汰、过旧、溢出、重放隔离、时间戳冲突、合并事件和内存估算。

所有计数均采用 `{availability,value,reason}`。`unavailable` 必须使用 `value=null`，不能以
零代替。近邻召回、错误抑制、错误合并和确认时延只接受
`scalable3d-observation-governance-evaluator-sidecar-v1`；侧车必须声明
`evaluator_only=true`、`online_consumed=false`，并用 SHA-256 同时绑定 manifest、在线审计
和离线真值摘要。D6 不读取原始真值。

报告固定输出逐 seed CSV、聚合 JSON 和中文 Markdown。规模聚合对在线计数给出均值、P95
和最大值；比例指标给出 evaluator 样本数、汇总比例和 episode 重采样自助法 95% 置信区间。
schema/hash/provenance 缺失、不一致规模、重复 seed、脏正式来源或在线真值泄漏会拒绝整批
输入。完整 producer 字段和调用示例见
`docs/OBSERVATION_GOVERNANCE_CALIBRATION_CONTRACT_CN.md`。

2026-07-22 的 14 项合成合同测试覆盖 available/unavailable、显式零、制品篡改、动态规模、
20/50/100/200、7/37 非基线规模和真值隔离；D6 全量为 `521 passed`，另有一条既有
Matplotlib `Axes3D` 环境 warning。

同日 D6 独立核验 clean/formal 制品
`observation_governance_calibration_20260722_formal_e4d66db`。输入策略为 `formal_only`，绑定
提交 `e4d66db02a0b8f1b867a0e81b4a73de84588426b`，工作树 clean。20、50、100、200 四档
各 5 个互异 seed，共 20 个 episode；每个 episode 为 33.75 s，在线真值使用数为 0。D6
评估模式为只读失败关闭，`runtime_modules_imported=false`，D1/D2 控制修改标志均为 false。

四档 D1 重排均为 12，拒绝/过旧/溢出均为 0，峰值扫描缓冲均为 3。D2 峰值 claim/容量
依次为 2390/4800、6020/12000、12070/24000、24170/48000；安全淘汰依次为 285、735、
1485、2985，溢出均为 0。evaluator-only 近邻召回率均为 1.0，95% episode bootstrap 区间
均为 [1.0, 1.0]；错误抑制率和错误合并率均为 0，区间均为 [0, 0]；确认时延均值、P95 和
最大值均为 0.25 s。所有上述指标均为 5/5 available。

聚合 JSON SHA-256 为
`6fb64252292aaedd3c68d1bfea64b76496136ce6edb32add61a281d511c4ed22`，中文报告 SHA-256
为 `6198854b867d39fb2f1300cddeb1f75972ba8b7952361622213050115feb0827`。该批关闭治理合同
在既定快速基准上的 clean/formal 证据缺口，不证明位置或速度精度、AirSim 接线、实时运行能力、
完整 D1-D7 控制效果或物理拦截成功。

同日 D6 只读核验 development 制品
`observation_governance_calibration_20260722_development`。该批在脏工作树上生成，20、50、
100、200 四档各 5 个互异 seed，共 20 个 episode；每个 episode 世界时长 33.75 s，在线
真值使用数为 0。各档 D1 重排数均为 12，拒绝、过旧和溢出均为 0，峰值扫描缓冲为 3。
D2 峰值 claim/容量依次为 2390/4800、6020/12000、12070/24000、24170/48000；安全淘汰数
依次为 285、735、1485、2985，溢出为 0。evaluator-only 的近邻召回率为 1.0，错误抑制率和
错误合并率为 0，确认时延为 0.25 s；上述指标均为 available，并保留 95% episode bootstrap
区间。200 规模的 D1+D2 tracemalloc 口径峰值约为 58.99 MB。上述数值仅说明这组快速治理
基准在给定输入下的表现，不等同于全系统精度、物理闭环或正式容量验收。

另一份 development 制品
`point_mass_integrated_observation_smoke_20260722_development_coalesced` 是实际 D1-D7 集成质点
栈的单 seed 冒烟。200 对 200 场景推进 2.2 s 世界时间，墙钟耗时 60.21 s，实时因子 0.0365，
在线真值使用数为 0。该制品用于确认全栈可以运行和写出治理审计，不与快速治理基准合并统计，
也不能作为长时性能或拦截效果结论。仍需在 clean commit 上正式复跑、扩大 seed 和场景覆盖，
并补齐完整系统精度与物理闭环验收。

## 2026-07-22 active_risk D2 修复后开发期复跑

main 在脏工作树上生成了开发期结果集
`/tmp/msm_active_risk_d2_fix_20260722/`。D6 使用既有只读消费者复核 seed `1000-1019`；根结果集
`SHA256SUMS` 的 447 个成员和 D6 输出目录的 3 个成员均通过摘要校验。该结果没有复制进模块输出目录，
也没有作为 clean formal 制品发布。

20/20 对的 `plan_consumption`、`guidance_lineage`、`physical_window`、`d4_degraded_adoption`、
`paired_physical_effect`、`paired_non_degradation` 和 `degraded_paired_physical_comparison` 均可用。
D4 区域采用在 control/treatment 两臂分别为 `94/94`，合计 `188/188`；两臂各有 `1960` 条实际写入
隔离 world 的控制命令。seed 1005 的 control 离线身份文件包含 5 条一对一映射：
`GT3D-000001` 至 `GT3D-000005` 分别映射到 `TGT-0001` 至 `TGT-0005`，状态均为
`unique_lineage_verified`；该 seed 和整批审计的 online truth use 均为 0。

两臂在 1 s 物理窗内的 5 m 成功数均为 0，物理差值为 0，20/20 对通过描述性非退化判定。
`paired_physical_effect` 可用表示差值可计算，不表示拦截或降级有效。隔离计划消费仍不是 production
runtime ACK；counterfactual/causal 均为 `0/20 available`，降级有效性声明仍禁止。本段只补充 D2 重复
航迹治理后的 development evidence，不改写下方此前 `19/20` 的 clean formal 历史记录，也不改变
PPO、assist、authority 或规则回退状态。

本轮仅改文档，D6 全量回归为 `507 passed, 1 warning`；warning 是既有 Matplotlib `Axes3D` 环境问题，
不影响 JSON、JSONL、Markdown 或摘要核验。

## 2026-07-22 隔离双臂多周期物理结果评估合同

`paired_isolated_physical.py` 新增 D6 只读、失败关闭的 control/treatment 多周期物理结果消费者。输入
清单 schema 为 `d6.paired-isolated-physical-inputs.v1`，按 seed 显式列出共享初始状态、传感器日程、
通信日程、故障日程，以及两套 arm 各自独立的 episode manifest、D3 计划、隔离计划消费确认、D7 命令
血缘、世界应用记录、离线身份映射和离线真值状态。每个文件均由调用方提供带外 SHA-256；输入清单
本身也必须通过 `--inputs-sha256` 绑定。control 与 treatment 的 episode ID、world ID 和全部 arm 文件
路径必须不同；共享初态和三类外生日程摘要必须相同。

每个 arm 可显式声明 `d4_adoption_evidence.jsonl`。声明后，该文件必须同时出现在 arm manifest 的
`arm_artifact_sha256` 中，路径与 SHA-256 均进入评估前后只读快照；spec 与 manifest 少一侧声明、文件
缺失或摘要漂移均失败关闭。旧输入不声明该文件时继续兼容，状态记为 `not_declared`，D6 不搜索邻近
文件。名义场景显式声明的空文件记为 `not_applicable`，不计作缺失或降级采用失败。

消费者逐条复算 D3 计划 `plan_id/plan_version/payload SHA-256`、消费绑定摘要、D7 命令载荷摘要和世界
应用血缘。隔离确认固定使用 `paired_isolated_simulation_only` 语义，并要求
`production_runtime_ack=false`；它不得称为 `runtime.assignment_plan_ack` 或生产运行时确认。每个已接受
绑定至少有两个控制周期，且至少一条 D7 命令由独立世界应用记录证明
`control_applied_to_world=true`，才能开放 guidance lineage。D3、消费确认、D7 和世界应用文件均执行
truth-like 字段扫描；目标真值只从 D6 离线身份映射和独立真值轨迹读取。

物理窗口从一个绑定首次实际写入隔离 world 开始，到该资源下一次已接受计划消费或 episode 终点结束。
成功判据固定为北东地坐标三维欧氏距离不大于 5 m。逐 seed 输出目标成功数、成功绑定数、最近距离、
到达 5 m 时间、硬约束次数、错误目标进入 5 m 的错误绑定次数和 treatment-control 差值。availability
严格分为 `plan_consumption`、`guidance_lineage`、`physical_window`、`paired_physical_effect`、
`paired_non_degradation`、`d4_degraded_adoption`、`degraded_paired_physical_comparison`、
`counterfactual` 和 `causal`。D4 层逐区域核对 schema、arm、region、seed、计划/场景血缘、候选门、
隔离计划消费确认和 adoption verdict，并汇总 `region_count/available_count/reason_counts/
intervention_kind`。只有两臂全部区域采用以及既有计划、导引和物理窗均完整，才输出描述性的降级配对
物理比较。任一必要证据缺失时，对应值为 `null` 并给出
原因；不以零补值。全部适用证据完整时，效果仍只称为
`paired_isolated_simulation_comparison`。本合同不会因为共享外生日程自动开放 counterfactual 或 causal。

D4 可以保留一条结构和血缘均合法的隔离计划消费确认，同时在 verdict 中声明
`isolated_plan_consumption_ack_available=false`。这表示该确认可供审计，但未被 D4 准入为 adoption
证据。D6 仍完整校验确认中的计划、血缘、执行绑定和非生产声明；只有 verdict 将确认标为 available
时，才要求 verdict `ack_id` 与确认编号一致。未准入时 verdict `ack_id` 可为 `null`，对应区域和顶层
D4 adoption 继续 unavailable，不能开放降级配对比较。

公开入口为 `PairedIsolatedPhysicalInputs`、`load_paired_isolated_physical_inputs()`、
`evaluate_paired_isolated_physical()` 和 `write_paired_isolated_physical_report()`；CLI 为
`scripts/run_paired_isolated_physical_evaluation.py`；D4 顶层记录 schema 由公开常量
`D4_ISOLATED_PHYSICAL_ADOPTION_SCHEMA` 固定。写盘入口生成 JSON sidecar、中文 Markdown、
provenance manifest 和 `SHA256SUMS`，并在评估前后复算全部输入摘要。2026-07-22 合成合同专项
`24 passed`，D6 全量 `507 passed`；覆盖旧输入、名义空文件、有效/部分区域 D4 采用、保留但未准入的
ACK、文件缺失、SHA 篡改、spec/manifest 声明不一致、arm/region/seed/plan/ACK 篡改、available 状态
矛盾、隔离确认冒充生产 ACK 和 D7 命令血缘错配。main 20 seed producer 集成专项另有 `1 passed`。
同日只读复跑 `active_risk` seed `1000-1019` 后，20/20 对计划消费和导引血缘可用，物理窗 19/20；
control/treatment 各 98 条区域记录的 adoption 可用数均为 0。两臂合计原因是
`isolated_execution_plan_not_strictly_new=188`、`degraded_scenario_evidence_invalid=8`，因此 D4 adoption、
降级配对比较、聚合物理差值、聚合非退化、反事实和因果均保持 unavailable。上述结果是兼容性和证据
边界验证，不是 D3/D4 降级策略的物理收益结论。

## 2026-07-22 D3/D4 保留 seed v1/v2 独立审计

`reserved_seed_intervention_audit.py` 现按顶层 manifest schema 严格分派历史 v1 与新 v2；v1 常量、旧
输入和 `pass_fail_closed_only` sidecar 结构保持兼容，CLI 用 `--profile v1|v2` 选择对应带外 commit、
源 manifest schema、`SHA256SUMS`、manifest 摘要与默认路径，当前默认是 v2。同 schema 的路径和摘要
允许带外覆盖；profile 与源 schema 不一致时失败关闭。Python API 的既有位置参数顺序和默认 v1 语义
保持不变。两版都只读校验六文件 inventory、checksum 链、
20 条 seed `1000-1019` lineage、dirty/nonfinite/online-truth 零值、四类配对共享标志、D3/D4 各
40 arm、pair input/bundle identity 和审计前后输入集合摘要。

新权威 v2 输入为
`../scalable_3d_simulation/outputs/reserved_seed_interventions_nominal_5v5_1000_1019_formal_7891296/`，
源提交 `78912963b67fe86ee9a8d29186b18a9dd60c460c`，`SHA256SUMS`/manifest SHA-256 为
`821f15035e628d8db86f13c22d93f8e05142c5f00aae9118974a74bdc98b72bc` /
`d6ef23b28add92e9a24a185ea72a7275e341bd796a2e11930c4d5f46b19a883c`。D3 的 40 个 arm 均绑定
`d3-offline-intervention-safety-shell-v2` 与配置 SHA
`d95fff61d31d80dc799ca6a9fcbf1c6e7adbed5a3f3cdd08b2ab38f9365f75b8`；20/20 treatment applied、
0 fallback。同帧规则基准 assignment cost 均值为 `17.0560260319065/17.0560260319065`，high-threat
unmet、duplicate、hard violation 和 churn 均为 0，inference P95(linear) 为 `0.310801 ms`。

D4 的 20 个 treatment candidate 均使用 `d4-region-resource-paired-arm-evidence-v2`：considered
20/20，confidence pass 0/20，OOD/latency/finite/failure pass 均为 20/20，aggregate pass 0/20；
20/20 因 low confidence 进入规则回退，safe-adopted 为 0。该 nominal 5v5 结果不是降级策略评估。
同一组 20 条 D4 时延样本有两个明确口径：`treatment_candidate_latency_ms` 的最近秩 P95 为
`2.241315 ms`，`candidate_gate_summary.candidate_latency_ms` 的线性插值 P95 为 `2.264415 ms`。
sidecar 只新增 `offline_assignment_comparison=true`；runtime ACK、physical outcome、counterfactual、
causal 以及 paired physical outcome/effect/non-degradation 继续为 unavailable/null，不能把 D4 零采用
写成效果 0，也不能据 D3 同帧比较声明候选策略有效。

当前 profile-bound canonical 输出位于
`outputs/reserved_seed_interventions_nominal_5v5_1000_1019_formal_7891296_d6_profile_bound_v2_audit_20260722/`，
固定审计时间为 `2026-07-22T04:56:47Z`。producer source commit、`SHA256SUMS` 和 manifest 摘要保持
`78912963...c460c`、`821f1503...72bc` 和 `d6ef23b2...883c`，未修改 source bundle。
sidecar/中文报告/provenance/`SHA256SUMS` 文件 SHA-256 分别为
`f3852251daf02ec87fe878e7fb80aad6f381d8c0756a5c956a32e737a3871c3b`、
`bd80c1dda496d7d43e2b274628fdbe3a5ef8a4b99c8c354562ba2149b70f9949`、
`0d50a95daf098bdc732a7d3344ef8340d7fc1828a2df7b971b40313db23f7dc6`、
`db4af357cbf087b20b28f5c3bcc775b98d711f996bb3040aac0b45ca5ae7b87c`；sidecar 内容 SHA 为
`c02a345c46ddc642dea7fb6bfcfb24184e7dc2a9f35b754c90324d074b445d2d`。同时间戳 CLI 临时复生与四文件
逐字节一致，`sha256sum -c` 通过。专项 `18 passed`，D6 全量 `483 passed`，仅有既有 Matplotlib
`Axes3D` warning。无 ignored output 时仍运行 16 个合成/篡改/
兼容测试，仅两个正式 v1/v2 bundle 复算按权威输入存在性跳过。

## 2026-07-21 D3/D4 保留 seed 隔离执行独立审计（历史 v1）

`reserved_seed_intervention_audit.py` 是 D6 对 main 生成的 D3/D4 保留 seed 隔离执行制品的独立只读
consumer。当前权威输入为
`../scalable_3d_simulation/outputs/reserved_seed_interventions_nominal_5v5_1000_1019_formal_6d5bfea/`，
源提交固定为 `6d5bfead31d53258b020a5f157b2ad5e7f25ee35`。入口先用带外摘要绑定
`SHA256SUMS` 和顶层 manifest，再复算五个成员文件、manifest 内全部 artifact SHA、D3 规范内容摘要/
arm spec/plan payload、D4 specification/arm identity，以及审计前后六个输入文件集合摘要。它不导入
D3/D4 producer 代码，也拒绝把输出写到输入目录内。

20 条 source lineage 精确覆盖 seed `1000-1019`，dirty、非有限 source 和 online truth use 均为 0；
control/treatment 同源 episode、传感器随机流、通信日程和故障日程均为 `20/20`。D3 和 D4 各有 40
个 arm，均为 20 control + 20 treatment；每对输入摘要、lineage、specification 和 bundle digest
身份全部闭合。D3 bundle manifest/state 绑定为
`a9213d65606a9e2f921040e153488c0f4cdebb10882fa16013fce5b59f9314c0` /
`e3da9fd5b54451da83358405b6051991e0c78bcf9f538b350d459b05faf8e0b2`，D4 为
`dad2adbe9c36dd9ff8ee8bb3c11b1e07e66743c6f80dd8e956799208a10c05c9` /
`3da0360be8788f3ffeb8e9f9eba3e0d5369ec0bdf9e05729dfb1db07d71d5f62`。模型文件不在输入目录内，
因此 D6 证明的是给定 digest 的严格身份绑定，不声称重新哈希了 bundle 文件。

D3 treatment 实际应用为 `0/20`，`20/20` 因 `out_of_distribution` 使用规则回退；control 状态为
`unchanged=15`、`held_by_hysteresis=3`、`replan_ack_no_change=2`。D4 treatment 安全采用为 `0/20`，
`20/20` 因 `candidate_threshold_or_finite_gate_rejected` 使用规则回退。D3 treatment receipt latency
为 20 个可用的 `0 ms` 记录；D4 candidate latency 为 n=20、mean `8.291408 ms`、median
`1.196097 ms`、nearest-rank P95 `35.255481 ms`、max `42.301505 ms`。时延为可用执行诊断，不是效果。

sidecar 显式输出 `execution_receipts=true`，`runtime_ack/physical_outcome/counterfactual/causal=false`。
由于两类 treatment 实际采用数都是 0，paired outcome、paired effect 和 non-degradation 均为
`available=false,status=unavailable,value=null`，不能填数值 0。该结果只证明失败关闭与证据完整性，
不证明 D3/D4 候选策略有效、非退化或具有因果收益。

公开入口为 `ReservedSeedInterventionAuditInputs`、`audit_reserved_seed_interventions()`、
`write_reserved_seed_intervention_audit()` 和 `render_reserved_seed_intervention_audit_markdown()`；CLI 为
`scripts/run_reserved_seed_intervention_audit.py`。下列目录是 schema binding 加入序列化 provenance
之前发布的历史 v1 输出。当前 consumer 重新生成 v1 时会包含 source schema binding，属于新的
profile-bound provenance，不承诺复现历史四文件哈希。历史输出位于
`outputs/reserved_seed_interventions_nominal_5v5_1000_1019_d6_audit_20260721/`，包含 JSON sidecar、
中文 Markdown、provenance manifest 和 `SHA256SUMS`。审计时间为 `2026-07-22T04:06:26Z`
（America/Los_Angeles 日期 2026-07-21）；专项 `7 passed`，D6 全量 `472 passed`，仅有既有
Matplotlib `Axes3D` warning。

## 2026-07-22 D5 paired-shadow 权威 v2 独立审计

`d5_paired_shadow_audit.py` 是 D6 对 D5 权威 v2 配对影子制品的独立只读消费者。调用方必须显式提供
v2 report、v2 lineage、held-out corpus、held-out evaluation、冻结模型包、D5 源实现以及已保留的旧
report/lineage，并逐项提供带外 SHA-256。审计重新计算 producer content SHA、2702 项 corpus inventory、
源码实现绑定和审计前后共 2718 项输入集合哈希，不搜索相邻目录，也不修改 D5 制品。

正式证据覆盖 seed `1000-1019`、45 个场景规模单元、900 帧和 74024 条已标注候选边。D6 从 lineage
重新核对每帧只加载一个图，规则臂与模型臂的 graph/candidate/label SHA 完全相同，模型没有增删候选边；
随后重算逐 seed、逐 cell 和总体边级/簇级混淆计数及延时。45/45 cell 无质量退化，模型边级和簇级
precision/recall/F1 均为 1.0，模型打分 P95 为 3.292009 ms。同相机边、未标注边、在线真值特征、
`global_track_id` 改写和输入改写均为 0。

独立合成可分性检查限制了该结论。`shared_global_track_count` 在 74024 条边上恒为 0；
`global_projection_mahalanobis` 单特征 F1 为 0.370482，因此没有证据表明满分由中心身份线索直接驱动。
但 `bbox_scale_rate_delta_s`、`bbox_log_scale_delta` 和 `angular_velocity_delta_rad_s` 均达到近确定性
单变量可分，最强特征在 35/45 cell 达到门限。paired-shadow 层可标记 `complete`，研究影子只获得
`qualified_with_synthetic_separability_caveat`；外部泛化证据仍不足。`G1=false`、`PPO=false`、
`assist=false`、`authority=false`、`rule_fallback=true`，线上准入和默认路径均未改变。

公开接口为 `D5PairedShadowAuditInputs`、`audit_d5_paired_shadow_evidence()`、
`write_d5_paired_shadow_audit()` 和 `screen_single_feature_separability()`。CLI 为
`scripts/run_d5_paired_shadow_audit.py`。独立输出位于
`outputs/d5_paired_shadow_e39a54d/`，包含 JSON、中文 Markdown、manifest 和 `SHA256SUMS`。
2026-07-22 专项测试 `8 passed`，D6 全量测试 `465 passed`；唯一警告为既有 Matplotlib
`Axes3D` 导入问题，不影响本次离线 JSON、Markdown 或摘要校验。

## 2026-07-21 D5 干净跨视角图数据分层审计（v2 前置阶段）

`d5_clean_graph_evidence.py` 是 D6 对 D5 tracked clean 数据的只读入口。调用方必须显式提供补充数据
summary、composite admission/view、两份 canonical subview、补充 manifest/dataset manifest 和正式源
manifest，并为每个文件提供带外 SHA-256。实现不搜索 D5 ignored output，不修改来源文件；60/20/20
seed、保留 seed `1000-1019` 零重叠、正负边、未标注边为 0、45 个场景规模单元、dirty 状态和来源未
改写任一不满足时均失败关闭。

输入清单已升级为 `d6.d5-clean-graph-inputs.v2`，可选的
`heldout_evaluation_report` 与 `heldout_manifest` 必须成对显式提供；旧
`d6.d5-clean-graph-inputs.v1` 仅兼容原三段结构，不能携带 held-out 字段。D6 不发现 corpus 邻近路径，
而是独立核对调用方文件 SHA、D5 newline-canonical `content_sha256`、
`d5.tracklet-heldout-model-evaluation.v1`、`d5.tracklet-heldout-corpus.v1`、精确 seed
`1000-1019`、45 个冻结场景规模单元和 900 个 episode。报告中的权重、bundle manifest、held-out
manifest、validation 温度和阈值必须与已提供内部 model bundle 一致；调温、重选阈值、更新权重、
online truth、同相机边、未标注边、`global_track_id` 创建/换绑或权限伪造均失败关闭。

输出分为数据支持、训练数据来源、模型内部测试、保留 seed、同 seed 配对影子五层。2026-07-21 对
当前 D5 clean 制品的核验结果为：composite 4,972 episode、245,040 条候选边，其中正边 57,298、
负边 187,742、未标注 0；前两层为 `complete`，后三层为 `unavailable`。G1、assist、authority 和
正式 PPO reward 均为 false，规则回退保持启用。完整模型 bundle 即使通过内部测试合同，也不能替代
保留 seed 和 paired shadow。

结构合法且 held-out 指标通过时，D6 只把 `evidence_layers.held_out_seed` 标为 `complete`；指标未达
冻结门限时标为 `failed` 并保留 producer `fail_closed`；缺成对制品时为 `unavailable`。无论该层结果
如何，未提供 paired shadow 时 G1、assist、authority 均为 false，`rule_fallback_required=true`。
该段记录 paired-shadow v2 生成前的前置状态。当时正式 900 帧制品尚未提供；当前 held-out 与
paired-shadow 状态以上一节的 2026-07-22 独立审计为准。原 34 项专项合成测试只证明接口合同。

公开接口为 `D5CleanGraphEvidenceInputs`、`load_d5_clean_graph_evidence_inputs()`、
`audit_d5_clean_graph_evidence()` 和 `write_d5_clean_graph_evidence_report()`。CLI 为
`scripts/run_d5_clean_graph_evidence.py`，其输入清单自身也必须提供带外 SHA-256。

## 2026-07-21 运行时计划确认与离线观测结果联接

`runtime_plan_outcome_join.py` 提供 D6 只读严格消费者。调用方必须显式给出 11 类输入文件及各自
SHA-256：完整 `online_observations.jsonl`、D2 离线身份评估及 manifest、D2 的 D1/D2 在线源记录、
观测真值标签和身份 evidence、离线真值状态、5 米接近事件、episode manifest 与场景配置。D6 先校验
文件哈希，再校验 D2 manifest/evaluation 内部来源哈希及其与完整在线日志的 sequence/payload 一致性。

每条 `runtime.assignment_plan_ack` 都重新绑定 D3 计划和可选 D7 导引批次的总线 sequence 与规范载荷
SHA-256，并以 ACK envelope sequence 与时间戳形成唯一 occurrence。同一 plan id/version 的
`evaluation_refresh_only` 或 `plan_refresh_only` 可以形成新窗口，但绑定、联盟、未分配目标清单和
authority 的规范执行签名必须保持不变。重复 sequence、同版本执行签名漂移、旧或错误计划版本、额外
绑定、载荷摘要错配以及 ACK 自报物理结果或奖励都会失败关闭。D2 真值映射只接受
`source_observation_lineage` 形成的唯一 available 映射，该映射仅进入离线结果，不返回在线路径。

同一资源按 ACK 时间切成 `[本次 ACK, 下一次 ACK)`，最后一窗闭合到 episode 终点。每个绑定输出身份
映射可用性、首末/最小三维距离、距离进展、正确目标 5 米事件、同资源对其他目标的 5 米事件、D3
learning evidence 与 D4 regional evidence。`bounded_assigned_pair_best_distance_progress_v1` 的范围为
`[-1,1]`，只在 ACK 接受、D7 非 hold 控制确实进入世界、D2 映射唯一和状态窗完整时可用。它是独立
诊断值，不是 D3 近端策略优化奖励；正式 reward、counterfactual 和 causal attribution 均保持不可用。

公开入口为 `RuntimePlanOutcomeJoinInputs`、`evaluate_runtime_plan_outcomes()`、
`load_runtime_plan_outcome_join_inputs()` 和 `write_runtime_plan_outcome_join_report()`。CLI 使用带外
哈希校验输入清单：

```bash
python3 research_modules/d6_evaluation_metrics/scripts/run_runtime_plan_outcome_join.py \
  --inputs-json /path/to/runtime_outcome_inputs.json \
  --inputs-sha256 <sha256> \
  --output-dir /path/to/independent_output
```

2026-07-21 专项 `22 passed`，D6 全量 `423 passed`，仅有既有 Matplotlib `Axes3D` 环境 warning。
真实 main 3 目标/3 资源、recon=1、seed=70、1.2 秒集成回归通过：同一 plan identity 的两条 ACK
分别形成 occurrence，累计 6 个绑定窗口，在线真值使用为 0，PPO/assist/authority 均为 false。对同
版本刷新修改 coalition binding 的负例返回 `same_plan_execution_signature_changed`。该结果只证明
接口、刷新语义和失败关闭行为，尚未形成正式多 seed、同 seed paired shadow、保留 seed 或学习采用
收益证据。

## 2026-07-21 跨模块学习数据联合准入审计

`cross_module_learning_admission.py` 和对应 CLI 现在显式要求 D3、D4、D5 三份 producer 全样本审计
路径及调用方提供的文件 SHA-256。D6 对三份文件重新计算文件哈希和去除 `content_sha256` 后的规范
内容哈希，并将 producer 的 expected/actual binding、binding checks、正式 manifest、补充 summary、
training/shared registry 和源提交绑定到本次联合准入输入。报告只保存哈希和计数，不保存输入绝对路径。

2026-07-21 真实复跑确认三模块结构性全样本审计均为 `complete`。D3 覆盖 900 episode、1604 个决策
帧、3,658,815 条候选边和 117,304 个规则选中动作，43,905,780 个特征值均有限。D4 正式语料覆盖
900 episode/1798 sample/14384 action，补充课程覆盖 100 episode/300 sample/1200 action；补充动作
包含 hold 100、request-replan 200、非零配额 200 和 transfer 100。D5 supplemental BC 覆盖 100
episode/1200 sample，`302/302` 个登记制品通过 SHA-256，有限特征为 `1200/1200`。三模块 online
truth、保留 seed 泄漏、dirty episode、身份和结构约束违规均为 0。

D3 审计文件/内容 SHA-256 为 `62a47df8...17fb` / `954f3e96...1867`，D4 为
`4245f1db...9e46` / `94f4f4bf...3e7f`，D5 为 `9a036535...2d3` / `a11b6559...50dd`。D3
`reward_components` 只是规则教师诊断，不是运行时奖励。D4 `target.kind=rule` 不是 truth，
`recommendation.projected=true` 不是运行确认。D5 applied/rejected/missing 各 400 仍只表示确定性
故障注入覆盖。

联合准入分层发布：D3、D4、D5 full-sample 和跨模块 structural full-sample 均为 `complete`；overall
admission 仍为 `partial`。规范 seed 视图和结构证据可用于行为克隆准备。PPO、在线 assist、控制
authority 均为 false，规则回退保持强制。真实 runtime applied ACK、observed outcome、可归因 reward、
counterfactual/causal、同 seed paired shadow、保留 seed 性能和 D5 tracklet 完整训练准入仍是 blocker。

报告写入 `outputs/cross_module_learning_admission_20260721/`，没有进入正式 900-episode generation
根。JSON 和中文 Markdown SHA-256 分别为 `6593ee8a...87f5` 和 `7b6480d0...a4ba`。专项测试增至
`37 passed`，覆盖 D3/D4 file/content SHA、schema、计数、binding、status、availability 和 admission
篡改的失败关闭。D6 全量 `401 passed`，仅有既有 Matplotlib `Axes3D` 环境 warning。本轮未训练模型、
未修改正式数据，也未开放 PPO、assist 或 authority。

## 2026-07-21 历史 manifest 共享种子划分审计

本节记录 detached canonical views 形成前，对原始 manifest 直接比较得到的历史结果。当前联合准入
状态以上一节为准；原始 manifest 没有被回写。

新增 `canonical_seed_split_readiness.py`，并在正式学习标签 readiness 中接入可选的 detached
`scalable3d-shared-seed-split-registry-v1`。D6 独立复算注册表 schema、policy、规范 JSON 内容哈希、
assignment 哈希和 `d3_numeric_seed_atomic_split_v2` 数值种子分配，不导入 main runtime。审计同时核对
源 `training_seed_registry.json` 的 SHA-256、100 个训练 seed 完整覆盖、保留 seed `1000-1019` 隔离
以及 60/20/20 的 train/validation/test 划分。

可选注册表启用后，D6 分别读取 D3 assignment、D4 region、D5 tracklet graph 和 D5 active-vision
manifest。每个模块报告原 split hash、canonical registry/assignment hash、三类 seed 数、missing、
extra、reserved、内部冲突和 canonical mismatch seed。D4 与 D5 manifest 有逐记录计数时，继续报告
mismatch episode 和 frame/sample；D3 只有聚合 manifest，发生 mismatch 时下钻计数保持
`null+reason`，不能填 0。四个 required module 全部 exact match 时，跨模块联合训练 readiness 才为
available。未提供注册表时，原有 D4/D5 单模块标签与 legacy split 比较保持不变。

正式 900 episode 只读审计结果如下。D3 为 exact，seed 为 `60/20/20`，mismatch 为 0。D4 seed 为
`70/15/15`，有 51 个 mismatch seed、459 个 episode、917 帧。D5 tracklet graph seed 为
`60/20/20`，有 65 个 mismatch seed、8350 个图记录、284 条候选边。D5 active vision seed 为
`60/20/20`，有 62 个 mismatch seed、558 个 episode、713298 条样本。四模块 missing、extra、reserved
seed 均为 0，但联合训练仍为 unavailable，原因是 D4 和两类 D5 数据没有精确遵守 canonical assignment。
旧 D4/D5 直接比较的 423/900 episode、47/100 seed 不一致继续作为历史诊断保留。

验收门限是注册表八项 validation 全部为 true，且四个 required module 均为 `exact_match=true` 后才开放
联合训练。本次前半项通过，后半项未通过。2026-07-21 D6 全量回归为 `364 passed`，仅有既有
Matplotlib `Axes3D` 环境 warning。

注册表文件 SHA-256 为 `68608d29d1f733beea87f1faf06464fededb68a9c2972c51c10cd4c2160f032f`，
内容哈希为 `29eb6895c4aa570b068f15141cbbbfede3041519117852d1ad48e848a25af146`，assignment
哈希为 `31c6a3fc265d088d9958f44d579d8098e2aeab06b0daa60c68452ae4c6d46ab5`。正式审计写入
`/tmp/d6_learning_label_readiness_shared_split_20260721.json`，文件 SHA-256 为
`a0469fa0bf4f1fc80d5e5dc9afac74d4638e782161c0c3f5ebc6befd93f405d1`；源 900 episode 数据未修改。

```bash
python3 research_modules/d6_evaluation_metrics/scripts/run_learning_label_backfill.py \
  <learning_dataset> <readiness.json> --audit-only \
  --shared-seed-split-registry <detached_registry.json>
```

该历史审计只给出数据治理和联合训练准入结论，不评价模型精度。D4、D5 后续已生成 detached
canonical views，并由本页顶部的联合审计复核；D6 仍未改写已有 manifest。

## 2026-07-20 正式学习数据标签审计

新增 `learning_label_backfill.py` 和 `run_learning_label_backfill.py`。入口只读冻结的 scalable 3D
学习导出，校验生成计划、检查点、训练 seed 注册表、episode 索引、D4 manifest/逐帧哈希，以及 D5
`SHA256SUMS`、descriptor、online/offline 文件和共享对象键。D4 与 D5 各自的 episode identity、seed、
split 和 Git identity 必须自洽；跨模块 split 另行比较。保留评估 seed `1000-1019` 不能进入训练标签。在线 D5 记录递归拒绝
truth/object/actor 类字段，生成物只能写到源数据集之外。

标签固定分为 `outcome`、`reward`、`counterfactual` 和 `causal_label` 四层，每层都有独立的
`available/value/reason/provenance`。相邻 D4 区域状态或 D5 相机观测可形成“纯观测转移结果”，但不能
证明某条建议或相机动作造成了变化。D5 动作奖励要求同 sample、camera、计划版本、联盟版本和通信版本
的运行确认；接受确认还要求后续反馈中的 `last_accepted_command_version` 与命令版本相同，且反馈时间
不早于确认时间。相邻姿态变化不替代运行确认。单事实轨迹没有同初态配对重放或干预证据时，反事实和
因果标签保持 unavailable，不能填 `0`。

正式 900 episode 只读审计覆盖 100 个训练 seed 和 `1000-1019` 共 20 个保留 seed，交集为 0。D4
共有 1798 帧，898 帧具备相邻纯观测转移，奖励为 `0/1798`；14384 个规则动作中，非零 quota、hold、
request-replan 和 transfer 均为 0。D4 行为克隆合同可用，但动作多样性不足，PPO 不可用。D5 共有
1,153,242 条样本，1,063,214 条具备纯观测转移；`runtime_ack=0`、
`last_accepted_command_version` 未形成可用执行链，奖励为 `0/1,153,242`。D5 规则示范可用于行为克隆，
不能据此声称因果最优或用于 PPO。D4/D5 有 `423/900` 个 episode、`47/100` 个 seed 的 split 不同，
所以单模块训练仍可使用各自 split，跨模块联合训练 fail closed。正式源数据未改写，也没有把保留 seed
用于训练标签。

```bash
python3 research_modules/d6_evaluation_metrics/scripts/run_learning_label_backfill.py \
  <learning_dataset> <readiness.json> --audit-only

python3 research_modules/d6_evaluation_metrics/scripts/run_learning_label_backfill.py \
  <learning_dataset> <detached_sidecar_directory>
```

完整 sidecar 采用临时目录写入后原子发布，JSON 规范化、gzip `mtime=0`，并生成独立 manifest 和
`SHA256SUMS`。同一冻结输入重复运行得到一致内容；已有输出只有通过自审计且源摘要哈希一致时才复用。
审计证据日期固定为 2026-07-20；2026-07-21 代码验收为专项 `17 passed`、D6 全量 `351 passed`，
仅有既有 Matplotlib `Axes3D` warning。正式审计结果文件由 main 在独立输出目录生成，本模块不修改或
回填正式学习数据源。

## 2026-07-20 scalable 3D 算法实验矩阵离线审计

`d6-scalable3d-offline-evaluation-v5` 新增 D6-owned
`scalable3d-experiment-matrix-v1` 审计，不导入 main 的矩阵生成器或控制代码。评估器只从
`scenario_config.metadata` 读取 `experiment_matrix_schema`、`algorithm_variant`、
`comparison_key` 和 `full_system_validation`。历史 episode 仍按原指标评估，但矩阵字段保持
null/unavailable；目录名不参与变体、规模或配对身份判断。

R0、G1、A1、A2、A3、C1、F1 分别对应纯规则、D5 跨视角图模型、D3 学习分配、D4 区域策略、D5
主动视觉以及四项组合。变体执行同时核对 config/summary 中一致的 learning runtime、bundle loaded、
requested/effective assist、fallback 和实际采用证据。D3 要求 `learning_applied`，D5 图模型要求
`loaded_edge_model` 且无规则回退，D5 主动视觉要求 assist adopted。D4 advice 本身仍不证明采用；只有
main 发布的消费合同通过 schema、来源、先前建议引用和 summary 一致性审计，且
`consumable=true`、`d3_hint_applied=true`，A2/C1/F1 才能取得 D4 实际采用证据。

完整性按每个显式 comparison identity 固定要求 R0/G1/A1/A2/A3/C1；F1 只在中心失效、二级失效和
高威胁 M-to-N 场景进入分母。按变体输出 availability-aware 指标和阶段耗时；有完整 R0 配对时计算
变体减 R0 的 paired delta，至少两个配对键才生成 bootstrap 置信区间。clean/formal、dirty development
和其他 descriptive evidence 分开统计，配对差值不自动解释为因果效果。

2026-07-20 的 producer 风格 fixture 覆盖 R0 正例、三个矩阵标识缺失、伪变体、bundle 回退、F1 场景
限制、固定 cell 分母、双 seed 配对、dirty 分层及 D4 消费正反例。scalable 专项 `40 passed`，D6 全量
`320 passed`，仅有既有 Matplotlib `Axes3D` warning。真实 producer 的
R0/nominal/2v2/seed101 开发 smoke 复读结果为 metadata/execution valid=true、present/expected=1/6；
该 episode `repository_dirty=true`，不属于正式矩阵。另一个临时 5v5 producer smoke 的 D4 消费为
1 条合法、1 次 D3 hint applied、1 次 control adoption。正式全矩阵尚未运行。

## 2026-07-20 scalable 3D 历史 schema 合同准入

该阶段的 `d6-scalable3d-offline-evaluation-v5` 使用 D6 内维护的
`d6-scalable3d-schema-registry-v1`，不导入 main 控制或仿真运行逻辑。当时合同固定为 world
`scalable3d-world-v1`、bus `scalable3d-episode-bus-v1`、scenario
`scalable3d-scenario-v1`、online observation `scalable3d-observation-v1`、offline truth
`scalable3d-offline-truth-v1`，并要求 scenario config 自身 schema 同为
`scalable3d-scenario-v1`。

该段保留 2026-07-20 的历史证据。2026-07-23 起当前 registry 和 offline truth 合同分别为 v2，
见本文顶部“离线观测三态处置”。

manifest 和 config 的原始 schema 字段继续原样输出，便于读取历史数据。每项另输出 expected、match、
status 和 failure reason；旧值、未知值、篡改值或缺字段只能作为 descriptive evidence，不能通过 clean
formal acceptance。此前 fixture 使用的 `scalable3d-online-observation-v1` 已改为真实 producer 的
`scalable3d-observation-v1`。

验证覆盖当前合同匹配、五个 manifest schema 分别不匹配和缺失 bus schema。scalable/active-vision
专项 `32 passed`，D6 全量 `304 passed`，仅有既有 Matplotlib `Axes3D` warning。既有 6v6、seed 37
producer smoke 复读得到 schema match=true；formal=false 的唯一原因仍是 worktree dirty。

## 2026-07-20 scalable 3D 主动视觉命令与 ACK 离线评估

`d6-scalable3d-offline-evaluation-v3` 已接入 D5 主动视觉运行证据。D6 仍只读取 main 写盘的
`online_observations.jsonl` 和 `summary.json`，不导入运行时、不控制相机，也不读取在线真值。consumer
只接受 `modules.d5.active_vision` 的 `d5.active-vision-runtime.v1` 和
`runtime.camera_command_ack` 的 `scalable3d-camera-command-ack-v1`。

评估把五层证据分开记录：规则命令、影子建议、D5 辅助动作采用、main ACK applied/rejected、物理
结果。shadow 模式发布的实际命令仍归入规则命令；只有有效模型建议且没有 fallback 的记录才计 shadow
suggestion。`effective_mode=assist` 只说明 D5 经安全外壳选用了模型动作，必须再与同 camera/resource、
issued timestamp、plan/coalition/communication version、intent 和 mode 的 ACK 关联，才能计为运行时
applied。命令与 ACK 缺失、schema 非法、数量冲突或关联不完整时，对应指标为 null/unavailable，不能
补零。

新增指标包括 issued/ACK/applied/rejected、ACK 完成率与 P50/P95/max 延迟、过期/过时版本/相机不可用/
其他拒绝原因，以及 rule/assist 实际 applied 数。summary 的 issued/applied/rejected/ACK 和拒绝原因
计数必须与在线日志一致。目标航迹编号只与命令之前最近的 D2 `associated_tracks` 中心航迹集合核对，
ACK 也必须原样返回同一 `target_global_track_id`；D6 不创建、重绑定或修正该编号。主动视觉相关在线
记录另做递归 truth-like 字段审计。

物理归因继续 fail closed。即使 assist 命令获得 applied ACK，且同一 episode 存在五米接近事件，缺少
同 seed、同场景的规则控制组和实际采用证据时，`d5_active_vision_physical_outcome_attribution` 仍为
null/unavailable。聚合使用显式 target/resource/recon/camera 数量，不从 2v2/5v5 名称推断规模。

2026-07-20 的 8 项主动视觉确定性测试覆盖 rule/shadow/assist 分层、ACK 延迟、四类拒绝、未知中心
航迹、ACK 身份改写、在线 truth 污染、缺日志、summary 冲突、五米非归因和双 seed 报告。主动视觉与
既有 scalable 专项共 `25 passed`；D6 全量 `297 passed`，仅有既有 Matplotlib `Axes3D` warning。
同日使用当前 main runtime 做了一个临时接线 smoke：6v6、recon=1、camera=7、seed=37、duration=2.2 s，
共 133 条 disabled/rule command、133 条 matched/applied ACK、0 rejected、0 target-reference violation、
0 online truth field violation，summary counters 一致，RTF=4.740。该 episode 来自 dirty worktree，只有
1 个 seed，bootstrap 不可用，正式 acceptance 因 `repository_dirty_not_formal_evidence` 为 false；未
运行 AirSim。main 仍需提供 clean、多规模、多 seed 运行数据和配对控制/处理实验，才能评估主动视觉
对物理结果的贡献。

## 2026-07-20 scalable 3D 学习运行时与 D4 advice 离线评估

`d6-scalable3d-offline-evaluation-v2` 继续只读 main-owned episode 文件，不导入 scalable runtime，
不发布总线消息，也不参与控制。除既有 provenance、D1-D7、阶段 timing 和五米离线物理诊断外，
现在交叉消费 `scenario_config.metadata.learning_runtime` 与
`summary.module_final_diagnostics.learning_runtime`，并读取 manifest/config 中 D3/D4/D5 的 runtime
version。三模块分别报告 requested/effective mode、bundle requested/loaded、fallback reason、模型
fingerprint 和模型 version availability；bundle 未加载或字段缺失时，学习模型 fingerprint/version
均为 `null/unavailable+reason`，规则 runtime version 不冒充学习模型版本。

D4 新增只读消费 `modules.d4.region_resource_advice`，只接受
`d4-region-resource-advisory-runtime-v1` 与 `d4-region-resource-recommendation-v1`。逐 episode 输出
advice 发布/合法/非法数、requested/effective mode 分布、recommendation/shadow 输出数、assist
eligible 数、fallback 数与原因、推理延迟 P50/P95、quota delta 守恒违规、projection rejection、
正式裁决 unchanged/mutation，以及过期或缺失 schema/scenario/seed/authority/plan/epoch/lease evidence。
旧 schema、字段非法、digest flag 篡改、非守恒 projected payload 或版本栅栏不一致均 fail closed；
不会用合法记录子集缩小分母。

报告严格区分五层：bundle 能加载、shadow 有输出、assist 获准、控制实际采用、物理结果。D4 advice
只提供建议并保持正式 D4 裁决不变；`assist_eligible` 不是控制生效。当前 producer 另行发布
`d4-region-resource-consumption-v1`。D6 只有在消费合同引用先前已发布的完整 advice、main 来源和
summary 重复证据一致，且 D3 明确应用 hint 时才记录 control adoption；缺消费证据仍为
`null/unavailable`。五米接近仍只是一层离线物理诊断，不归因于 advice，也不生成 `mission_success`。

聚合仍按 scenario/version 和显式 target/resource/recon/camera 数量分组，以不同 seed 的 episode
均值做固定 RNG percentile bootstrap；单 seed 仅 descriptive，不产生 CI 或推断结论。正式 evidence
继续强制 `repository_dirty=false`，并校验配置 hash、D4 policy version、finite 和 online truth 隔离。

2026-07-20 确定性 fixture 覆盖既有规模/缺值边界，以及 learning disabled、D3/D4/D5 missing-bundle
fallback、loaded bundle 的 assist-to-shadow、assist gate、守恒与非守恒 quota、projection rejection、
正式裁决 unchanged/mutation、digest 篡改、旧 advice schema、缺 plan version、缺 advice 和 seeds 1/2
聚合。接受门限为全部字段 availability、五层语义、fail-closed、四类报告和 single-seed 规则通过；
结果为 scalable 专项 `17 passed`、D6 全量 `289 passed`，仅有既有 Matplotlib `Axes3D` warning。本轮
未运行真实 scalable 3D 或 AirSim episode，也没有形成学习模型验收结论。

```bash
python3 research_modules/d6_evaluation_metrics/scripts/run_scalable_3d_offline_evaluation.py \
  --episode-root <scalable_3d_batch_root> --output-dir <d6_report_dir>
```

当前限制：现有 `offline_truth_labels.jsonl` 只有 observation-to-truth 标签，没有显式
`global_track_id -> truth_target_id` 映射时，五米身份正确性保持 unavailable；D2 producer 明确声明
IDSW unavailable 时也不离线补算；D4 消费接口已有单 episode 接线证据，但真实 clean、多规模、多 seed
学习 bundle、完整矩阵与物理结果仍需 main 调用本入口验证。

## 2026-07-15 legacy ClockSpeed provenance 兼容与三档实测

ClockSpeed comparator v2 现兼容旧 1.0 suite 的持久化 settings provenance：仅当调用输入是 suite
root/summary 路径且 summary、20 个 case、20 个 result row 完全没有显式 ClockSpeed 时，才按每个
`case_id` 定位 sibling case 的
`generated_settings/blocks_actor_m5_n2_settings.json`。20/20 文件必须存在、顶层显式包含有限正数
`ClockSpeed` 且全量一致；缺文件、缺键、冲突、非有限值和字符串均 fail closed。mapping 输入不搜索
文件系统，目录名仍不参与推断，也不默认填 1.0。报告 manifest 保存 20 个绝对 evidence path。

真实 1.0/0.2/0.1 三档 comparator 已只读运行，输出在
`../airsim_runtime/outputs/m5n2_clock_speed_comparison_20260715/`。三档各 20 case、20 个跨档配对、truth
identity/state 在线使用均为 0；1.0 provenance scope 为
`sibling_case_generated_settings`，0.2/0.1 为 `case_result`。冻结机会合同在 60 case 中 56 match、4
mismatch；0.1 candidate seed007/009 和 0.2 candidate seed006/009 的受影响 aggregate 为
unavailable，不使用缩小分母。baseline pair/target/coalition 分别为 0.1 `4/30,4/20,0/10`、0.2
`9/30,9/20,0/10`、1.0 `6/30,6/20,0/10`。case wall timing 三档均缺源字段，保持 unavailable；
candidate 0.1/0.2 因合同不完整不形成成功率结论。三档 summary 加 20 个 legacy settings 的“绝对
路径+内容”组合 SHA-256 前后均为
`fdb745ee54f0c5ff414a812bf8e75eacd56fa5ea91ff02f64008fb6ee1759cd1`。

## 2026-07-15 ClockSpeed=0.1 NameError 紧急回归修复

`stage_timing.py` 的输入模式规范化函数现统一命名为
`_normalize_stage_timing_input_mode`，并前置定义在 loader、summarizer 和
`evaluate_stage_timing_inputs()` 三个调用点之前；旧 `_timing_input_mode` 名称已删除，避免实际批次
加载到缺失私有名称。新增回归按真实 suite 形态构造 baseline/candidate 各 seed 1-10 的 20-case
双层 merged JSONL，每 case 从 frame/timestamp 0 重置，直接调用 evaluator。

真实 ClockSpeed=0.1 M5N2 20/20 case 已用 P1 v6 只读复测：main bus/control tick 各 4036 records、
20 case，manifest match=true，两层 available，跨 case/跨层 total 均为 null。summary 与两份 timing
输入 SHA-256 前后不变。报告位于
`outputs/p1_clockspeed_0p1_m5n2_20case_20260715_case_aware_validation/`。本轮 timing 专项
`28 passed`、D6 全量 `264 passed`、`py_compile` 与 `diff --check` 通过。该句记录紧急修复当时状态；
三档 comparator 随后已完成，见本页顶部。

## 2026-07-15 ClockSpeed=0.2 case-aware 真实证据复核

`stage_timing.py` 现显式区分默认严格 `single_episode` 与 `case_aware_suite`。suite 模式要求每条记录
除原 schema 外恰好携带 `case_id/family/profile/seed`，拒绝其他 extra field；每个 case 内
frame/timestamp 严格递增，case 切换可重置且已离开的 case 不得再次出现。main bus/control tick 的
ordered case manifest 必须一致，只允许按 scope 池化分布；跨 case 首尾/总时长和跨层总时长均为
null。单 episode 的字段白名单和全流单调规则未放宽。P1 acceptance 升级为 v6，并以显式
`--stage-timing-input-mode case_aware_suite` 启用该 envelope。

真实 ClockSpeed=0.2 M5N2 suite 已完成 20/20 case。D6 对两份 merged timing 做只读复测：main bus
与 control tick 各 6567 records、20 个连续 case envelope，双层 manifest 一致，P1 报告生成成功，
输入文件复测前后 SHA-256 不变。输出位于
`outputs/p1_clockspeed_0p2_m5n2_20case_20260715_v2_case_aware_validation/`。

ClockSpeed comparator v2 冻结每 case opportunities 为 active-primary pair/target/coalition=`3/2/1`。
actual-execution unavailable 或 suite/intercept 机会数不符时，该 case 的物理与末端派生指标整体为
unavailable，不缩小分母、不补零。standby reserve 只进入排除审计，不计 active-primary success。
真实 0.2 审计为 18 match/2 mismatch：candidate seed006 为 D7 actual-execution unavailable，三类
physical/command/main conflict，实际机会 `2/1/1`；其 reserve physical success=true，但 active-primary
success=1、raw top-level success=2。candidate seed009 的 actual-execution available，但实际机会也为
`2/1/1`，因此同样是 contract mismatch。该段记录 0.2 审计；0.1 真实 P1 复测状态见顶部，不在此
混写三档性能结论。

2026-07-15 验证：timing 专项 `27 passed`、ClockSpeed 专项 `10 passed`、D6 全量 `263 passed`；仅有
既有 Matplotlib `Axes3D` warning。

## 2026-07-15 M5N2 ClockSpeed 三档离线对比接口

新增 `clock_speed_comparison.py` 和 `run_clock_speed_comparison.py`，输入同一套 M5N2
ClockSpeed=`1.0/0.2/0.1` 的三个 suite root 或 summary。入口强制每档恰有 20 个 case：baseline 与
candidate 各 seed 1-10；suite 内按 `case_id/profile/seed` 连接 case/result，三档之间再按同一键完整
配对。main 既有 `comparison_role=enhanced` 规范归一化为 candidate；family/resource/target 必须显式
为 `m5n2_paired/5/2`，不从目录名或场景简称推断规模。

ClockSpeed 只接受 suite/case `provenance`，或 20 个 result row 全量一致的显式 case-level
`clock_speed`；summary 根部裸字段和目录名都不作为来源。若 suite、case、result row 或注册的
`intercept_summary.parameters.clock_speed` 同时存在，值必须一致。输出包括 case CSV、profile
aggregate CSV、JSON、中文 Markdown 和 PNG 曲线。

指标覆盖 active-primary pair、target、coalition 三个独立物理分母，第二 primary 五米成功与最小
距离，required active-primary 最终锁、coalition 最终锁共识、`collision_stop`，case wall、main-bus
和 control-tick wall timing，以及
`simulated_time_per_tick_s = control_tick_wall_mean_ms / 1000 * ClockSpeed`。main bus 是 control tick
内层，两层禁止相加，cross-layer total 固定为 null。truth identity/state 在线使用继续逐 case 审计；
任一缺字段或坏 artifact 均为 `availability=unavailable`，不补零。

2026-07-15 确定性验收使用三档各 20 case、总计 60 case，baseline/candidate 各 seed 1-10；接受
门限为三档和 60 case 完整、20 个三档配对键完整、provenance 一致、缺失指标不补零及嵌套 timing
不相加。专项 `8 passed`，D6 当时全量 `254 passed`，仅有既有 Matplotlib `Axes3D` warning。该段是
运行前接口记录；真实三档调用与 availability-aware 结果已由本页顶部更新。

```bash
python3 research_modules/d6_evaluation_metrics/scripts/run_clock_speed_comparison.py \
  --suite <clock_1_0_suite_root_or_summary> \
  --suite <clock_0_2_suite_root_or_summary> \
  --suite <clock_0_1_suite_root_or_summary> \
  --output-dir <comparison_report_dir>
```

## 2026-07-15 真实 AirSim M5N2 20-case 复核

本轮只复核 `p1_terminal_timing_funnel_10seed_20260715_m5n2_*` 下 20 个已完成的
SimpleFlight case：baseline 与 `candidate_soft_prediction_trend_coast` 各 10 seed。M5N2 20/20
完成后、`TERM` 生效前额外完成了 `p1_terminal_timing_funnel_10seed_20260715_png_ttc_2v2_seed001`；
该 `png_ttc` seed001 明确排除在 M5N2 20-case 聚合与验收之外。其余 tuned 2v2 和全部 dropout case
未执行；缺失 case 保持 unavailable，不补零，也不能拼成完整 terminal-closure suite。

canonical `d7-actual-execution-metrics-v2` 的 required/available/unavailable 为 `20/20/0`，20 个
case 均通过 source/schema/hash/case/seed 校验。最终物理结果按独立分母为 pair `12/60`、target
`12/40`、coalition `0/20`；baseline 与 candidate 各为 `6/30`、`6/20`、`0/10`。两配置总量相同，
但逐 seed non-degradation 为 false，candidate 不能据此进入默认路径。10389 条实际命令目标状态
均来自 `d2_estimated_global_track`，stale 为 0；在线 truth identity/state 使用计数均为 0。

术语固定为：canonical target physical success（规范目标物理成功）表示“至少一个 participating
pair 进入 5 m”，本批为 `12/40`；cooperative target-stage diagnostic（协同目标阶段诊断）表示
“该目标全部 required member 通过指定阶段”。后者不能覆盖或替代
`target_intercept_success`，coalition completion 仍只由全部 required primary 的物理结果判定。

第二 primary 的七阶段证据为 assigned/visible/associated/contract `20/20`，control/mode
`17/20`，5 m physical `0/20`，所有阶段分母和 20 个失败原因均 available。首失败分布为：预测窗
过期 10、视觉获取未稳定 6、未形成稳定 D5 锁定 2、bbox 面积过小 1、bbox 靠近图像边缘 1。第二
primary 最近距离 mean/min/max=`12.654/8.843/14.740 m`，因此 coalition 零是完整证据下的失败，
不是 unavailable，也不能由 target 成功回填。

20 个第二 primary 的最终执行状态均为 `collision_stop`，但本批持久化产物未记录 collision object。
因此 D6 只能报告“碰撞停止原因对象 unavailable”，不能把它归因为联盟成员冲突、环境碰撞或
AirSim 状态问题，也不能从该终态反推五米成功。补齐 collision object/actor、时间戳和来源字段是
开放 P1 producer/接线缺口。

20 个 case 的 main-bus 与 control-tick 原始流分别有 3805 条，逐 case 严格校验均通过。离线按
scope 汇总：main bus mean/P95/max=`349.34/487.40/1305.99 ms`，预算违例 `3649/3805`，主导阶段
是 D1 fusion（mean `320.00 ms`）；control tick mean/P95/max=
`1069.45/1254.06/2072.51 ms`，预算违例 `3805/3805`，主导阶段是 AirSim frame sample（mean
`432.29 ms`）。control tick 的 `bus_processing` 已包含 main bus，两层禁止相加。

当前 partial acceptance bundle 未注册 timing 路径，显示 `unavailable`；现有 suite 合并 JSONL
又在 case 边界重置 frame/timestamp，不能作为单一严格递增流直接导入。所以上述 timing 是基于 20
个显式 case 路径的离线复核结果，正式 suite timing 接线仍是 P1。D6 指标口径和 consumer 已实现；
剩余 P1 是第二 primary 物理闭环、100 ms 性能预算、case-aware timing 汇总和后续独立批次验证。

## 2026-07-15 第二 primary 漏斗与独立分母 P1 报告口径关闭

`CooperativeClosureReportGenerator` 输出 schema 升级为 `d6-cooperative-closure-v3`。第二
primary 现按 `assigned -> visible -> associated -> contract_allowed -> control_allowed ->
mode_switched -> physical_intercept` 逐阶段报告通过数、有效分母、不可用数和比例；pair、target、
coalition 的物理结果另以各自写盘机会数统计，禁止跨层回填。coalition completion 单独保留有效/
不可用机会、完成数、失败数和完成率。

首失败原因只统计 producer 明确写出的 `first_failure_reason`。失败结果缺原因时输出
`unavailable/partial` 和缺失数，不再补 `unspecified`；缺物理结果时成功/失败为 null，不把
unavailable 当零。2026-07-15 确定性 fixture 专项 `11 passed`，D6 全量 `246 passed`，仅有既有
Matplotlib `Axes3D` warning；该代码批次未启动 AirSim。其后真实 M5N2 20-case 已按本页顶部回填，
第二 primary 与联盟性能仍为 P1；额外 `png_ttc` seed001 排除在本批聚合外，其余 tuned 2v2 和全部
dropout 未执行。

## 2026-07-15 分阶段延迟可观测性 P1 代码缺口关闭

D6 新增 `stage_timing.py`，严格离线消费 `main-stage-timing-v1` 与
`control-tick-stage-timing-v1` JSONL。schema/scope、frame/timestamp、预算、阶段值与状态、阶段
和、总耗时、未归因耗时、预算标志和错误状态均受校验；负数、NaN/Inf、状态冲突、重复/倒序帧
及和式冲突全部 fail closed。旧产物缺 timing 显示 `unavailable`，不补零。

每层独立输出阶段 sample、mean/P95/max、N/A/error、总 tick、预算违例和 dominant stage，并生成
CSV、JSON、中文 Markdown 与 PNG；嵌套的 main bus 与 control tick 禁止相加。P1 acceptance 当时
升级为 v5，当前已由顶部 case-aware 工作升级为 v6。2026-07-15 确定性动态规模无关 fixture（合法两层各
2 帧及完整负例矩阵）专项 `20 passed`、D6 全量 `236 passed`，未启动 AirSim。真实多 seed
M5N2 20-case 随后已实测并确认 `100 ms` 未达标；case-aware 正式接线现已关闭，瓶颈优化和跨提交
复验仍为开放 P1。

```bash
python3 research_modules/d6_evaluation_metrics/scripts/run_stage_timing_report.py \
  --output-dir <report_dir> --main-stage-timings <stage_timings.jsonl> \
  --control-tick-stage-timings <control_tick_timings.jsonl>
```

## 2026-07-14 actual target-state freshness/stale P1 指标链关闭

`d7-actual-execution-metrics-v2` 现从最终 `control_commands.csv` 强制消费
`timestamp_s`、`target_measurement_timestamp_s`、`target_arrival_timestamp_s`、
`target_measurement_age_s`、`target_state_stale` 和 `target_state_source`。缺列、空值、非有限值、
负值、measurement 晚于 arrival、arrival 晚于 control、age 与 `control-measurement` 冲突、非法
stale 布尔或空 source 都使整份 canonical evidence fail closed；不补零。合法显式 `False` 会形成
available stale `0`，合法 `True` 会形成 available 正计数，不会被误判为 unavailable。

每个 canonical case 的 `metrics.target_state_freshness` 输出 `sample_count`、mean/p95/max age、
stale count/rate 和 source distribution，并由独立 `metric_availability/source/semantics` 描述来源。
formal validator 仅在 source path 与 SHA256 通过后重读 CSV，使用同一严格算法复算并逐项对照
payload。case suite、pooled aggregate、aggregate CSV/JSON 和中文 Markdown 已接入该指标；physical、
末端五层、truth identity/state 隔离和 availability 三态未改变。

2026-07-14 使用最新持久化真实源复建：tuned 2v2 seed-1 为 48 samples，mean/p95/max=
`0.0375/0.2/0.2 s`；M5N2 seed-1 为 608 samples，`0.091118/0.2/0.2 s`。两例 stale 均为
`0/0%`，source distribution 分别为 `d2_estimated_global_track:48/608`；pooled 为 656 samples，
mean/p95/max=`0.087195/0.2/0.2 s`。关闭门限是两 case 均通过列、数值、时间、age、source hash 与
payload 精确复算检查；stale 零是本批观测结果，不是 availability 的通用定义。正式产物位于
`outputs/p1_actual_target_state_freshness_20260714/`。D6 全量 `216 passed`，仅保留既有
Matplotlib `Axes3D` warning。单 seed 正式 freshness/stale 指标链关闭；同配置 multi-seed、跨提交
趋势和 failure taxonomy 当时仍为 P1。其后本页顶部 20-case 已提供 10389 条同配置样本；现在只保留
跨提交趋势、failure taxonomy 和独立批次复验，不再把“缺同配置 multi-seed”列为当前缺口。

## 2026-07-14 actual v2 真实 AirSim 证据同步

main 于 2026-07-14 完成 tuned 2v2 seed-1 与 M5N2 seed-1 两次真实 AirSim/SimpleFlight
重跑。D6 统一报告对 canonical `d7-actual-execution-metrics-v2` 的
required/available/unavailable 判定为 `2/2/0`；本轮 actual execution 的接受门限是所有 required
case 均 available 且 unavailable 为 0，因此该 P0 证据门已通过。两场景的
`intercept_summary.json`、`control_commands.csv` 离线 scorer 和 actual artifact 物理成功计数均
为 `2/2/2`，旧 `d7_actual_execution_command_physical_count_conflict` 未复现并关闭。

M5N2 的 active pair、target、coalition 结果分别为 `2/3`、`2/2`、available `0/1`。coalition
是有完整分母和成员证据的显式失败，不是 unavailable；target `2/2` 不能替代第二 required
primary 未进入 5 m 的 coalition 结论。统一报告的 `overall_acceptance_passed=false` 也不否定
上述 actual gate：本批只有 2 个 seed-1 case，没有 baseline/candidate 成对比较、1-5 帧 dropout
全矩阵和多 seed，不能构成完整 P1 terminal-closure suite。

性能仍为开放 P1：2v2/M5N2 loop latency 分别为 `123.3 ms`、`384.6 ms`，性能预算违例分别为
`19`、`212`，合计 `231`。真实证据见
`../airsim_runtime/outputs/p0_actual_v2_validation_20260714/d6_acceptance/P1_UNIFIED_ACCEPTANCE_REPORT.md`
和 `../../subagent_reviews/MAIN_P0_ACTUAL_EXECUTION_AIRSIM_VALIDATION_REPORT_20260714.md`。本次仅同步
D6 文档，没有改变代码或指标算法。

## 2026-07-14 actual-execution 验收门与独立到达口径复核（真实重跑前历史）

正式 suite 只把通过校验的 canonical `d7-actual-execution-metrics-v2` 作为 actual execution
envelope。任一 required case 缺少该 artifact，或显式登记
`d7-actual-execution-unavailable-v1`，`actual_execution_all_available` 即为 false，suite 总验收
fail closed。legacy main row 和离线五米物理结果只保留 diagnostics；它们可独立说明离线物理
评分，但不能替代、补齐或晋升为 actual envelope。

当 `arrival_coordination_required=false` 时，coalition completion 不再要求共同到达窗口，而是对
每个 required active primary 的独立五米物理成功逐一评分：全部 required primary 成功才完成该
target coalition。required-primary denominator/member、physical result 或该开关缺失，以及 summary
与 pair 间冲突时，结果仍为 `null/unavailable`，不得补零。

本轮只完成代码级回归，没有启动 AirSim。四个历史真实 seed-1 case（M5N2 baseline、M5N2
candidate、2v2 PNG-TTC、1-frame dropout）的 actual artifact 仍为 `unavailable`，现有原因均为
`d7_actual_execution_command_physical_count_conflict`；main 必须真实重跑并注册有效 v2 artifact，
旧 main acceptance 与离线五米结果不能关闭该缺口。2026-07-14 实际验证结果为专项
`14 passed, 24 deselected`、D6 全量 `190 passed`。唯一 warning 来自 Matplotlib
`projections/__init__.py:63` 无法导入 `Axes3D`，边界仅为 3D projection 不可用，不影响本轮
JSON/CSV/Markdown 口径、二维报告或测试结论。

## 2026-07-14 actual plan identity provenance P0 关闭

`d7-actual-execution-metrics-v2` 现在把最终 `control_commands.csv` 中的 `plan_id`、
`plan_version` 和 `d4_target_node_id` 严格提取为 envelope `metadata.plan_ids`、
`metadata.plan_versions` 与 `metadata.owner_node_ids`。plan ID 和正整数 version 在每行都必填；
`d4_target_node_id` 列必需，但值只在“effective control 已授权且该行处于 secondary/distributed
active、execution、reassignment，或显式 execute secondary/distributed action”时必填。中心授权
行和未授权的 pre-transition/pending 行可为空；若没有观测到 authoritative owner，owner 集合为
空且 provenance 明确为 `unavailable`。secondary/distributed effective-authorized 行缺 owner 仍使
整个 actual envelope fail closed。三个数组均去重排序，合法多计划可形成多版本历史，但同一
`plan_id` 绑定多个 version、plan/version 缺失或非法 version 都 fail closed。

validator 除结构和 provenance 校验外，在 merge 的 SHA256 校验路径上重读 command CSV，并把
提取结果与 envelope metadata 逐项对照。`d6.execution-metrics-merge.v3` 会先删除 replay 中的
同名计划 metadata，再只复制 validator 返回的 actual metadata；因此最终
`metrics.metadata.plan_ids` 不再为空，也不会从 replay 推断。contract/control/mode、physical、
performance 和 truth safety 的既有来源及计数语义未改变。

验证日期为 2026-07-14：确定性离线测试（seed N/A）覆盖中心授权空 owner 正例、未授权 pending
空 owner 正例、secondary effective-authorized 空 owner 负例、plan/version 缺失、合法多版本、
同 plan 混合版本冲突、provenance/来源篡改和 merge 隔离；execution-evidence focused
`20 passed`，D6 全量 `184 passed`，仅有 1 条既有 matplotlib `Axes3D` warning。没有启动或
运行真实 AirSim。该阶段关闭 D6-owned P0；其后 main/runtime 已完成本页顶部两条真实 seed-1
v2 artifact 的生成和注册。同条件 multi-seed provenance 与趋势验收仍保持 P1。

D6 是 MSM 的离线评估与报告模块。它只消费已经写盘的日志、CSV、JSON/JSONL 和仿真真值，输出 `EpisodeMetrics`、CSV、Markdown 报告和 PNG 图表；不参与 D1-D7 的实时控制链路，不生成任务、分配、导引、授权、火控、毁伤或自动处置动作。

## 2026-07-14 actual SimpleFlight execution evidence P0 收尾（真实重跑前实现记录）

D6 不再接受 `integrated_replay/d7_execution_metrics.json` 作为执行后规范证据。该文件可以保留
合同、模式和性能的离线诊断值，但只能作为 audit-only replay；当 actual execution 缺失时，
`merge_replay_with_execution_metrics()` 会把 execution-only 指标保持为
`null/unavailable`，不会回退 replay 数值。

main 应在 SimpleFlight 控制结束且三个输入文件均已最终写盘后调用：

```python
from d6_evaluation_metrics import write_d7_actual_execution_evidence

actual_path = write_d7_actual_execution_evidence(
    output_path=episode_dir / "d7_actual_execution_metrics.json",
    control_commands_path=episode_dir / "control_commands.csv",
    intercept_summary_path=episode_dir / "intercept_summary.json",
    main_episode_bus_metrics_path=(
        episode_dir / "main_episode_bus" / "main_episode_bus_metrics.json"
    ),
)
```

writer 输出 `d7-actual-execution-metrics-v2`，包含固定 producer
`main_airsim_runtime`、阶段 `post_simpleflight_control`、scope `actual_execution`、case/seed/
规模、三份来源的绝对路径和 SHA256。合同与控制计数取最终 command CSV，物理结果取 intercept
summary，性能样本与时延取最终 main bus clock。规范模式切换只统计
`mode_switched=true AND effective_control_authorized=true`，并强制
`mode_switched_count <= control_allowed_count`。无正性能样本、来源计数冲突、控制字段冲突、
文件缺失或 hash 不一致时不发布 canonical artifact。

同一 envelope 还从 command CSV 严格计算主动降级、二级重分配、重分配 pending、终端锁定获取、
视觉 PNG 切换和拒绝原因等 actual diagnostic count。`visual_png_switch_count` 是“获得控制授权后
进入视觉 PNG”的状态迁移数，`visual_png_control_allowed_sample_count` 是持续授权样本数，后者只作
supplemental，不得冒充切换次数。安全计数并列发布：`truth_identity_online_use_count` 来自
`control_commands.csv.truth_identity_online_use` 的显式布尔样本，
`truth_state_online_use_count` 来自 `intercept_summary.json` 的显式计数；二者均有独立 source、
semantics 和 availability，缺列、缺字段或来源错误时整个 actual envelope fail closed。

main 随后只能把该独立文件注册为 `d7_execution_metrics`；不得注册 integrated replay 或把旧文件
改名。`terminal_closure_evidence` 会再次核对 schema、case/seed、来源文件存在性和 SHA256。

本批复核 2026-07-14 两个既有 M5N2 seed-1 episode，未重新运行 AirSim：baseline 的 raw replay
为 mode `17`、loop `0 ms`，actual builder 为 mode `0`、`142` samples、`386.519 ms`；candidate
raw replay 为 mode `13`、loop `0 ms`，actual builder 为 mode `0`、`141` samples、`398.333 ms`。
两组 effective control 和 physical 均为 0。2026-07-14 main runtime 在 state 字段接入后暴露
identity 字段缺失；本次已在 D6 canonical schema/builder/validator 中补齐。D6 全量回归
`173 passed`，仅有 1 条既有
Matplotlib `Axes3D` 环境 warning。

## 2026-07-14 terminal closure 多案例证据接线（先前四案例状态）

`P1AcceptanceReportGenerator` 现在会安全消费
`main_terminal_closure.rows[*].d3_plan_history`，输出
`d6-d3-case-history-suite-v1` 的逐 `case_id/seed`、逐 seed 和 suite 汇总。每个文件独立检查路径、
JSON root、D3 wrapper/record schema、记录顺序和 seed 绑定；坏文件只使对应 case
`unavailable`，不会中断整个 suite，也不会补零。显式传入单个
`P1AcceptanceInputs.d3_plan_history` 的兼容入口保留。

D7 使用相同的逐 case fail-closed 接线。main 行没有显式
`d7_execution_metrics` 时，报告给出
`d7_execution_metrics_path_not_registered_by_main`；D6 不扫描相邻目录。已注册文件按
`d6-episode-metrics-structural-v1` 检查 episode、seed、availability、metadata 和核心执行计数。
raw `EpisodeMetrics` 不带 terminal metric envelope 的 producer/scope/lifecycle，因此只进入
`d7_execution_evidence`，不被二次导入四层指标。

main 可在文件写盘后调用纯函数合同：

```python
from d6_evaluation_metrics import register_terminal_closure_case_evidence

row = register_terminal_closure_case_evidence(
    row,
    d3_plan_history_path=d3_history_path,
    d7_execution_metrics_path=d7_metrics_path,
)
```

对现有
`p1_terminal_closure_semantics_v2_seed1_20260714` 的离线复核中，4/4 case 的 D3 history
可用，共 543 records；原 summary 的 4 个 D7 路径均未注册，均按上述原因 unavailable。使用
helper 在临时 summary 中显式注册现有 D7 文件后，4/4 case 通过结构校验，执行侧
`control_allowed_count` 合计 51；main 四层同名指标仍独立为 51，没有重复聚合。测试结果为
`159 passed`，仅有 1 条既有 matplotlib `Axes3D` 环境 warning。未启动 AirSim，也未修改
AirSim runtime；main 注册 D7 路径并重生成正式 suite 仍是跨模块 P1。

## 2026-07-14 terminal suite P1 评估口径关闭

`P1AcceptanceReportGenerator` 已升级为 `d6-p1-unified-acceptance-v2`。terminal count 使用
`d6-terminal-metric-envelope-v1` 长表，每条 `contract_allowed_count`、
`control_allowed_count`、`terminal_switch_allowed_count`、`mode_switched_count` 和
`physical_intercept_count` 必须带：

```json
{
  "metric_name": "contract_allowed_count",
  "value": 1,
  "producer": "d7_runtime_bus",
  "metric_scope": "execution",
  "denominator": 3,
  "lifecycle": "terminal_execution"
}
```

`denominator` 必须为正样本数；缺 producer/scope/lifecycle、无样本 `0/0`、值越过分母或层级
不匹配均输出 unavailable。聚合键包含 `source + producer + metric_scope + lifecycle`。因此
main-bus `planned_lock/plan_generation` 与 D7 `execution/terminal_execution` 即使指标同名，也只
逐组报告，顶层 `sum` 为 `null`，不会比较、求和或覆盖。`terminal_switch_allowed_count` 保留为
control 层 gate，`mode_switched_count` 保留为 mode 层执行结果；contract/control/mode/physical
四层不互推。

pair/target/coalition physical outcome 还要求 `physical_metric_context` 提供 producer、scope、
lifecycle，并分别使用各自 opportunity count。`loop_latency_ms` 和
`performance_budget_violation_count` 只有在 `performance_metrics.sample_count > 0` 时可用；
无样本的显式零保持 unavailable。candidate non-degradation 另带 `effectiveness_evidence`：
baseline/candidate 效果均为 0 且 candidate trigger 为 0 时固定为 `inconclusive`，promotion 为
false。

terminal suite 可直接读取 D3 canonical 文件：Python API 使用
`P1AcceptanceInputs(d3_plan_history=Path(...))`，CLI 使用 `--d3-plan-history`。校验通过后输出最新
plan ID/version、primary/reserve membership、owner 及 plan/coalition/membership/owner/feedback
churn；缺文件或坏 history 保持 unavailable。报告产物为：

- `p1_acceptance_per_seed.csv` / `p1_acceptance_per_seed.json`；
- `p1_acceptance_terminal_metrics.csv`；
- `p1_acceptance_aggregate.json` / `p1_acceptance_aggregate.csv`；
- 中文 `P1_UNIFIED_ACCEPTANCE_REPORT.md` 与 PNG。

```bash
python3 research_modules/d6_evaluation_metrics/scripts/run_p1_acceptance_report.py \
  --output-dir /tmp/msm_p1_acceptance \
  --main-summary /path/to/p1_terminal_closure_summary.json \
  --d3-plan-history /path/to/d3_plan_history.json \
  --d7-execution-summary /path/to/d7_terminal_execution.json
```

2026-07-14 使用 planned-lock/execution 同名隔离、零样本性能、零效果零触发、canonical 两 tick
history 四类确定性离线场景验收；专项 `8 passed`，D6 全量 `154 passed`，1 条既有 matplotlib
warning，未运行 AirSim。关闭的是 D6 schema/consumer/report P1；main `p1_terminal_closure` 仍需
写出上述 envelope、physical context、performance sample count、candidate trigger/effect，并把
`d3_plan_history.json` 传给 D6，之后才可形成真实 multi-seed 结论。

## 2026-07-14 physical provenance gate P0 关闭

D6 现将真值身份和真值状态分为两个 availability-aware 指标：既有
`truth_identity_online_use_count` 保持兼容；新增 `truth_state_online_use_count` 从
`intercept_summary.json`、pair summary 和 `control_commands.csv` 的实际布尔值与
`target_state_source` 聚合。严格 D2 estimated-state 路径为 available `0`；显式
`airsim_actor_truth_fixture` 必须为正数，summary 的假零不能覆盖 pair/command 正证据。

当前 physical layer 只在 summary 显式 `physical_intercept_available=true`、source 合法、
summary online control source 属于对应 class，且至少一个 active assigned pair summary 存在时
available。`offline_truth_distance_scorer` 只接受 `d2_estimated_global_track`；
`online_truth_state_fixture` 只接受显式 truth fixture class。每个 active pair 必须同时声明
`physical_evidence_available=true`，且 `target_state_source` 必须与 summary online source 完全
一致；此外每个参与 pair 必须有显式 `physical_success/physical_intercept`，或 D7 scorer 规范终态
`collision_intercept/range_intercept/timeout/aborted`。仅声明 evidence available 不构成结果。
command-only、summary-only、缺 pair result/evidence 或 pair source mismatch 时，pair/target/
coalition physical count/rate 与 `physical_intercept_count` 全部为 `None/unavailable`，并带明确
reason。command CSV loader 保留 `physical_evidence_available` 供审计，但 command rows 不再生成
physical pair。coalition 还要求显式机会分母、完整 persisted required-primary 成员、arrival
window，以及 summary 有机会时的显式 completion count；缺任一项均为 unavailable。证据完整的
显式失败仍保留 available `0`。`physical_min_range_m` 与在线估计距离分开消费；无 scorer
provenance 的旧 status 只保留 `legacy_physical_status_present`，不晋升为 physical success。

2026-07-14 以 7 类确定性离线 provenance 场景验收，seed N/A：严格 estimated-state、显式
truth fixture、合法 offline scorer、缺 source legacy、command 缺 pair evidence、summary-only
aggregate、active pair source mismatch；接受标准为两个合法 source 正例 available，其余缺证据
负例全层 `None/unavailable`。新增 7 项 result/denominator/window 正负例覆盖缺 pair result、
缺 required member、缺 window、缺 denominator、summary 缺 completion、规范终态和完整显式零；
结果全部满足，D6 全量 `150 passed`，1 条既有 matplotlib
`Axes3D` 环境 warning，未运行 AirSim。本次只关闭 D6 consumer/metric/test 的 P0，不等于
真实 AirSim P1 物理证据完成。2026-07-11 至 07-13 缺新 provenance 的 physical 数值仍是
迁移前历史口径；target-state age/stale 单 seed 正式分布已由本文顶部关闭，真实同条件
multi-seed AirSim 重跑和跨批 freshness 趋势仍为 P1。

## 2026-07-14 truthless tracking 假零 P0 关闭

`EpisodeMetrics.track_rmse`、`track_continuity` 和显式保留的 `id_switch_count` 现支持
`None/unavailable`。空输入、只有匿名 `TrackRecord`，或没有 evaluator-side truth-to-track
配对时不再输出默认零。RMSE 需要同一记录的 track/truth position；continuity 需要非空且覆盖
已配对 track timestamp 的 truth sidecar；ID switch 需要显式 truth ID 与 global track ID 历史。
因此完整 identity history 中“没有切换”是 available `0`，没有 identity pair 则是 unavailable。

availability 进入 `EpisodeMetrics.to_dict()` JSON、episode CSV 的三项独立 status 列、统一
`metric_availability`、batch summary/Markdown。main-bus loader 会把“值为零但声明 unavailable”
归一为 `None`；replay/execution merge 保留 `id_switch_count` 字段但不会把旧默认零升级为证据；
reporting 也不再把显式 unavailable 的非空旧值计入统计。

2026-07-14 使用 5 个确定性场景验收：空输入、仅匿名 track、不完整 truth sidecar、完整
truth 且零切换、完整 truth 且有切换。seed 不适用；接受标准为前两类三项全 unavailable，
不完整 sidecar 不产生 RMSE/continuity 假零但已配对 identity 的 IDSW 为 available `0`，完整
稳定/切换场景的 IDSW 分别为 available `0/1`，且 JSON/CSV/Markdown/merge 状态一致。实际
结果全部通过；D6 全量 `137 passed`，1 条既有 matplotlib `Axes3D` 环境 warning。本轮未运行
AirSim。真实 multi-seed 的 seed/config/schema/hash provenance 完整性，以及按 episode clock、
`global_track_id`、plan/version 连接 D2 lifecycle 与 D3 churn 的 join，仍是 P1。

## 2026-07-14 第二批 D3 canonical ordered history

`P1SystemEvidenceReportGenerator` 已正式消费 main 写盘的 `d3_plan_history.json`：wrapper
schema 为 `d3_plan_history_v1`，每条 record schema 为
`d3_plan_history_record_v1`。D6 不导入 D3 或 main，只读取该 JSON 文件。

canonical history 只有在以下校验全部通过时才进入计算：至少 2 条记录；顶层
`record_count` 与实际长度一致；`sequence_index` 为非负整数、唯一且严格递增；
`ordering_key=[sequence_index,timestamp]` 一致、唯一且严格递增；timestamp 有限且不倒退；
每条 record 的 schema/version、plan、assignment、coalition、hysteresis、feedback 和 owner
字段满足冻结结构；record 不含 truth 字段。失败时所有 history-derived 指标保持
`unavailable`，原因写入 `d3_history_validation_reasons`，不会输出假零。

新增或正式接入的字段包括：

- `d3_history_record_count`、`d3_history_validation_status/reasons`；
- `plan_version_churn_count`、`coalition_version_churn_count`、
  `coalition_epoch_churn_count`；
- `membership_change_count`、`primary_membership_change_count`、
  `reserve_membership_change_count`；
- `owner_change_count`、`soft_feedback_count`、`hard_feedback_count`。

membership 按相邻 tick 的 `(target_id, resource_id) -> (role, activation_state, active)` 状态
变化计数，不累加 `membership_change_records` 审计事件。primary/reserve 分项按变化前后涉及的
角色归类；同一成员从 primary 改为 reserve 会同时进入两个分项，但总体只计一次。owner 按
`(active_plan_owner, owner_node_id)` 相邻变化计数；feedback 汇总各 tick 显式
`soft_count/hard_count`。coalition version/epoch 对相邻 coalition ID 映射的变化、出现或消失
计数。

CLI 调用可使用：

```bash
python3 research_modules/d6_evaluation_metrics/scripts/run_p1_system_evidence_report.py \
  --d3-plan-history /path/to/episode/d3_plan_history.json \
  --output-dir /path/to/d6_p1_system_evidence
```

Python API 继续使用
`P1SystemEvidenceInputs(d3_assignment_churn=Path(".../d3_plan_history.json"))`。旧
`--d3-churn-summary` 参数仍兼容。旧 snapshot/cooperative-role 输入也保持兼容；证据不足时
churn 仍为 unavailable。

2026-07-14 验证覆盖稳定零、版本变化、primary/reserve 与 activation 变化、owner 切换、
soft/hard feedback、乱序、重复索引、timestamp 倒退、单记录、schema/record_count/order key
错误、缺少 required field 和无 truth 字段。专项 `24 passed`，D6 全量 `132 passed`，另有 1 条本机 matplotlib
`Axes3D` 环境 warning。本轮未启动 AirSim、未形成新的物理性能结论。剩余 P1 是用真实
multi-seed episode 持续形成跨提交趋势和稳定 failure taxonomy；P2 optional benchmark
状态不变。

以下第一批 P0 修复及 2026-07-13 更早章节均为历史记录，不覆盖本节当前状态和测试计数。

## 2026-07-14 第一批 D3 churn availability P0 修复（历史）

`P1SystemEvidenceReportGenerator` 不再把 D3 最终快照、空 mapping 或单条无序记录解释为
“没有发生变化”。`plan_version_churn_count`、`coalition_version_churn_count`、
`coalition_epoch_churn_count` 和 `membership_change_count` 仅在以下条件之一成立时可用：

- producer 显式写出对应 count；显式 `0` 是 available 的有效证据；
- 至少两条记录具有顺序语义，且该指标所需的 version/epoch 或 membership change 证据完整。

有序历史中的稳定同值才计算为 available `0`。`plans/history` 序列保留其历史顺序；通用
`rows/records` 必须具有统一且唯一的 sequence/index/timestamp 字段。coalition 指标还要求
每条历史记录提供同一 coalition 的 version/epoch，membership 指标要求每条记录显式提供
`membership_change_records` 或 `membership_change_count`。证据不完整时 CSV 留空，JSON 和
availability 为 `unavailable`。

2026-07-14 回归覆盖 5 类输入：最终快照、空 mapping、单条无序记录、两条稳定有序历史、
顶层显式零。前三类四项 churn 均为 unavailable；后两类四项均为 available `0`。正式
40-case cooperative-role fixture 仍只统计 `active_primary/member_role`，四项 churn 保持
unavailable。验收结果为专项 `12 passed`、D6 全量 `120 passed`，另有 1 条本机 matplotlib
`Axes3D` 环境 warning。当前 P0 已闭合；剩余 P1 是上游 D3 真实有序 plan history/provenance、
长期 multi-seed 趋势和跨批次失败原因治理。P2 optional benchmark 状态不变。

以下 2026-07-13 及更早章节是历史实现与实验快照，不覆盖本节当前结论和测试计数。

## 2026-07-13 M5N2 cooperative closure 统一入口适配

`P1SystemEvidenceReportGenerator` 可直接被动消费 main 写出的原始
`p1_cooperative_closure_summary.json`，包括顶层 `cases/pair_rows/aggregates`；也可消费
`CooperativeClosureReportGenerator` 修正后的
`d6-cooperative-closure-v2/cooperative_closure_aggregate.json`。两种输入不需要改写为
`summaries/rows/records`，缺失值继续保持 `unavailable`。

- D3：原始 schema 仅从 40 个 case 的显式 `active_primary/member_role` 统计角色，计划与联盟 churn 没有时序证据时不推断。
- D5：active-primary 的 `visible/associated/common_lock` 分开统计。该 AirSim schema 的 `associated` 由 `d5_decision_state=locked` 生成，因此可同时进入独立锁定计数；reserve 行只进入安全审计。
- D7：active-primary 的 contract/control/mode/physical 四层逐层消费，profile aggregate 单独提供 case、pair、coalition opportunity/completion；reserve unauthorized 和 online truth 使用单独审计。
- 修正 aggregate 没有逐 pair 行时，报告从 `funnels.pair`、`common_lock`、`primary_source.aggregates` 和 `acceptance.checks` 恢复聚合证据，不伪造 seed、资源规模或逐 pair 明细。

固定 40-case fixture 的结果为：4 个 profile、每 profile 10 seed，最佳 profile
`d3-p1-h020.0-w03.0-s040.0` 完成 `5/10`，总体 coalition 完成 `8/40`；reserve
unauthorized、global ID rewrite、online truth use 均为 0。D7 四层 active-primary 合计为
contract 35、control 7、mode 9、physical 62。完整 D6 回归为 `115 passed`。

## 2026-07-12 D1/D2 dense-crossing 离线评估

新增 `DenseCrossingEvaluationReportGenerator`，离线消费 D1 governed replay manifest、独立 offline truth summary，以及 D2 的 10-seed screening 和 20-seed confirmation。报告固定分开 `gnn_baseline`、最佳 `gnn_candidate` 和 `lightweight_jpda`；FilterPy/Stone Soup object adapter smoke 只进入排除审计，不进入身份指标排名或晋级结论。

逐 seed CSV 和聚合 JSON/中文 Markdown/PNG 覆盖显式 availability-aware 的 IDSW、identity/coverage continuity、false track、RMSE、NIS/NEES、初始化延迟、p95 loop latency 和 truth leakage。D2 当前 calibration 行只提供 NIS/NEES availability 时，D6 将均值标为 unavailable，不从 RMSE 或 availability count 推导数值。

该独立 `d6-dense-crossing-evaluation/v1` 报告器历史上使用至少 20 seeds 的 confirmation，并检查 IDSW 相对下降 30%、identity continuity 绝对提高 0.10、false track 不超过基线 110%、p95 loop latency 预算和 truth leakage。该 `+0.10` 只属于历史 D6 v1 对照，已弃用作 D2 v2 准入判决。当前 `P1SystemEvidenceReportGenerator` 不重新计算或覆盖 D2 判决，而是兼容读取 D2 v2 的 ceiling-aware headroom/error-reduction gate 和 legacy checks；轻量 JPDA 的任何通过结果仍只是隔离候选评审，不直接替换默认 GNN。

```bash
python3 research_modules/d6_evaluation_metrics/scripts/run_dense_crossing_evaluation.py \
  --d1-manifest /path/to/manifest.json \
  --d1-offline-truth-summary /path/to/summary.json \
  --d2-screening /path/to/d2_identity_calibration.json \
  --d2-confirmation /path/to/d2_identity_calibration.json \
  --output-dir /path/to/d6_dense_crossing
```

当 screening/confirmation 位于同一个 D2 calibration 文件时，两个参数可指向同一路径；历史 dense-crossing v1 报告器仍读取原 stage/JPDA comparison。统一 system-evidence v2 另行兼容 `d2-p1-identity-calibration/v2` 的 `gates`、structured checks 和 bool checks，并保留缺字段的 unavailable 状态。

## 2026-07-12 cooperative-closure-v2 离线报告

D6 新增 `CooperativeClosureReportGenerator`，用于消费 main 的通用资源-目标行记录，并可选叠加 D3 candidate、D4 communication、D5 visibility、D7 guidance summary。该报告器只读写盘证据，不导入在线控制模块，不向分配、降级、视觉关联或导引回写结果。

输入支持 JSON、JSONL、CSV、mapping/dataclass 序列。输出固定为逐 seed CSV、聚合 JSON、中文 Markdown 和 PNG。pair/target/coalition 使用独立分母；target/coalition 只有在全部 active primary 具备显式证据时才进入相应阶段分母，reserve 不进入预期完成分母。共同锁定必须由 D5/main 提供 `common_lock` 同窗证据，不能用普通 `associated` 代替。

验收检查为 coalition 至少 10 个有效 seed 且完成率不低于 0.8、reserve unauthorized 为 0、global track ID rewrite 为 0、online truth use 为 0。任一证据缺失时结论为 unavailable；结果始终为 advisory-only。

D4 communication 输入兼容真实 `CommunicationFaultReplayReport` dataclass/`to_dict()` JSON：顶层优先读取 `cases` 而不是整数 `seeds`，并在 D4 专用归一化层映射 `scenario_id -> communication_fault`、`passed -> communication_passed`。`fail_closed` 保持原字段独立统计，不由 `passed` 推断。

2026-07-13 使用真实 M5N2 40-case summary 复核后，验收聚合固定为“按 `profile` 分组、每个 profile 按唯一 `seed` 计数”。`case_id` 只保留逐 case/seed 审计，不能进入验收分组键。联盟成员按稳定 `coalition_id` 合并；滚动计划中的 coalition version/epoch 仅作 provenance，不能把同一联盟拆成多个单成员单位。只有至少两个 active primary 的目标才进入 coalition 分母，普通单 primary 目标不计为联盟。

profile 选择优先采用 source summary 的 `best_candidate_profile`；缺少该声明时，才按“通过 seed 数、完成率、available seed 数、profile 名稳定排序”选择。真实 40-case fixture 的 source 最佳 profile 为 `d3-p1-h020.0-w03.0-s040.0`，D6 修正后得到 `5/10`，验收状态为 available 且 failed；四个 profile 的完成数依次为 `0/10、5/10、2/10、1/10`，与 source aggregates 一致。`unavailable` seed 单独报告，绝不按 0 或失败补入。

```bash
python3 research_modules/d6_evaluation_metrics/scripts/run_cooperative_closure_report.py \
  --rows /path/to/cooperative_rows.jsonl \
  --d3-candidate /path/to/d3_summary.json \
  --d4-communication /path/to/d4_summary.json \
  --d5-visibility /path/to/d5_summary.json \
  --d7-guidance /path/to/d7_summary.json \
  --output-dir /path/to/d6_cooperative_closure
```

## 2026-07-12 P1 第二批统一验收

新增 `P1AcceptanceReportGenerator` 和命令行入口 `scripts/run_p1_acceptance_report.py`。该入口可离线消费 main 的 `p1_terminal_closure_summary.json`，以及 D1 长 replay、D2 多 seed 关联、D3 分配矩阵、D4 failover matrix、D5 visual readiness 和 D7 dropout/`png_ttc`/trend coast summary。输入既可为 JSON 路径，也可由 Python API 直接传入 mapping 或各模块 dataclass/report 对象。

输出固定为逐 seed/source CSV、聚合 JSON、中文 Markdown 和 PNG 概览图。四层 `contract_allowed/control_allowed/mode_switched/physical_intercept` 只接受同名证据；pair/target/coalition 使用独立分母。旧输出缺字段时 CSV 留空、JSON 为 `null/unavailable`，不会从 terminal switch、pair success 或其他近似字段回填。

```bash
python3 research_modules/d6_evaluation_metrics/scripts/run_p1_acceptance_report.py \
  --output-dir /tmp/msm_p1_acceptance \
  --main-summary <p1_terminal_closure_summary.json> \
  --d1-summary <d1_long_replay_summary.json> \
  --d2-summary <d2_long_replay_calibration.json> \
  --d3-summary <d3_assignment_calibration.json> \
  --d4-summary <d4_failover_matrix.json>
```

D5 和 D7 三类 summary 可通过对应可选参数继续加入。未提供来源会保留在 `source_manifest` 并标为 unavailable。D6 不运行这些 producer，也不控制 AirSim。

独立 D7 summary 未提供时，D6 会从版本化 main terminal-closure summary 做保守回退：`acceptance.dropout_matrix` 转为 1-5 帧矩阵，`rows[family=png_ttc]` 汇总四类显式拒绝计数，M5N2 candidate 行的 `terminal_trend_coast_count` 汇总实际触发。独立 D7 summary 始终优先；回退结果带 `derived_from=main_terminal_closure`。四层执行指标仍只读取每行同名字段，不从这些专项字段推断。

真实 smoke `p1_terminal_closure_smoke_v2_20260712` 已重跑：dropout 1-5 帧 matrix complete/all compliant 均为 true；`png_ttc` 有 1 个 seed，not-expanding 拒绝 1 次，其余三类为 0；trend coast 实际触发 0，保持不建议晋级。当前 main 文件尚未包含四层同名字段，因此四层正确显示 unavailable。

## 2026-07-12 D7 PNG Delivery 被动评估

D6 已增加 availability-aware 的 D7 终端 delivery 评估。离线 loader 可消费 `terminal_filter_state/reason`、innovation reject/reset、TTC area jump/bbox clipping/not-expanding/out-of-range、soft prediction/coast 状态与 elapsed time、terminal lock、visual mode、速度命令和显式 `terminal_delivery_profile/comparison_role`。旧日志缺少字段时对应指标为 `None/unavailable`，不会记为零。

新增指标覆盖滤波 measured/predicted/innovation-rejected/reset/expired，TTC 四类拒绝，soft prediction/coast 次数、持续时间和到期，terminal lock continuity、visual mode duration 以及 command discontinuity mean/max。既有 `contract_allowed/control_allowed/mode_switched/physical_intercept` 四层和 pair/target/coalition 三层物理结果保持独立。

`ReportGenerator.write_terminal_delivery_comparison_bundle()` 输出逐 episode CSV、聚合 JSON 和中文 Markdown，按显式 profile、scope、scenario 和实际 `resource_count/target_count/camera_count` 分组；2v2 与 M5N2 不合并，M5N2 的 target success、active-primary pair success 和 coalition completion 不互相回填。D6 仍只读日志，不参与 D7 控制。

2026-07-12 实际对照包包含 26 个 episode、4 个独立分组：2v2 baseline/candidate 各 10 seeds，pair/target success 分别为 `19/20`、`20/20`；M5N2 35 s baseline 为 target `6/6`、active-primary pair `6/9`、coalition `0/3`，8 s candidate 为 active pair `0/9`。M5N2 两批几何和窗口不等价，仍需同条件 paired 验收。四层 logging smoke 为 `contract_allowed=4/36`、`control_allowed=2/36`、`mode_switched=5`、`physical_intercept=2/2`；旧日志缺列时保持 NA。该 D7 专项当时回归为 `84 passed`；加入本轮 P1 统一验收和 main-summary fallback 后，D6 当前回归为 `88 passed`，仍有 1 条本机 matplotlib `Axes3D` warning。

## 2026-07-11 P1 统一验收与 P2 adapter

D6 已消费 main episode bus 的 `d4_coalition_commit_state`，并从事件或扩展 `CoalitionRecord` 聚合 epoch、plan/coalition version、lease、required/acked members、commit state/reason、ACK latency、timeout、aborted/reconfiguring 以及 secondary/distributed commit。相同 generation 的 `committed -> executing` 转换只计一次有效 commit，状态与原因保留在 metadata audit。

终端验收现显式分为 `contract_allowed`、`control_allowed`、`mode_switched` 和 `physical_intercept`。`physical_intercept_count` 只接受通过 provenance gate 的 persisted pair scorer result；intercept summary、command/status 或 ComputerVision `d7_guidance_record` 均不能单独晋升 physical availability。physical 层进一步拆成 `pair_physical_success_count/rate`、`target_intercept_success_count/rate` 和 `coalition_completion_count/rate`：pair 分母只含 active assigned pair，target 以任一 participating pair 成功为准，coalition 必须有显式分母、全部 persisted required primary、arrival window 与可判定 completion，三者不共用分母。`collision_intercept/range_intercept` 是规范成功终态，`timeout/aborted` 是规范失败终态；证据完整的失败输出 available `0`。

`intercept_summary.json` 的物理判据审计保留 `intercept_radius_m`、`intercept_distance_frame`、`intercept_distance_dimension` 和 `intercept_success_criteria_version`；当前 5 m 验收要求 NED 3D Euclidean。缺 required-primary arrival window 时 coalition 指标为 unavailable，不用 pair/target 成功回填。detect/coast 诊断新增 `detection_acquisition_timeout_count`、`image_kf_predict_count`、`blind_push_count`、`visual_reacquisition_count`、`terminal_visual_lost_after_coast_count`、`truth_identity_online_use_count`，只读取 summary/control record 或从带明确 detect/coast 状态的逐 pair 时序离线推导。

隔离式 P2 `py-motmetrics` adapter 已实现冻结 `msm-offline-mot-v1` schema，输出 IDF1/MOTA/MOTP。HOTA 在 `motmetrics 1.4.0` 中不受支持，固定输出 `None/unavailable`；可选依赖缺失时同时输出兼容 `reason` 和显式 `unavailable_reason`。依赖只在 `/home/linux/.cache/msm-p2-venv` 验证，默认 requirements 和默认测试依赖不变；offline truth 禁止回流在线链路。

## 2026-07-11 M 对 N 离线指标合同

当日实测基线来自 `p1_p2_validation_20260711`：CV 10 seeds 中 8/10 形成 T001 双 primary 同帧共识与授权证据，全部 seed 的 IDSW 和错误重复锁为 0；secondary 与 distributed 正例均为 executing 3/3，missing-ACK 负例为 aborted 2/3。CV 的 `control_allowed_count=0`、`physical_intercept_count=None` 正确表示未执行物理控制。SimpleFlight 10 seeds 均保持 4 bindings、3 active + 1 standby，但 30 个 active pair 中 0 命中，包含 24 detection timeout 和 6 timeout；15 s、`control_dt=0.5 s` 仅为诊断配置。

D6 已实现中心化 M 对 N 的兼容日志与离线聚合。新增 `TargetDemandRecord`、`CoalitionRecord`、`ArrivalRecord`，并在 `AssignmentRecord`、`TerminalRecord` 保留 `coordination_mode`、`coalition_id/version/state`、`member_role`、`wave_id`、`required_resource_count`、`demand_assigned/shortfall/complete`、arrival window 和 `minimum_member_separation`。标准 JSONL 支持 `target_demand/coalition/arrival`，collector writer 可 round-trip；旧日志缺少这些字段时只对 duplicate 判定使用明确的 legacy `k=1`，其余新增指标保持 `null/unavailable`。

`EpisodeMetrics` 已接入 demand micro/macro、unmet slots、over-support、formation/reconfiguration、simultaneous arrival/common-window、sequential wave、hybrid primary/reserve、planned/authorized/erroneous lock、same-resource lock continuity、member lifecycle/digest/stale、messages/bytes/rounds/latency、minimum separation/collision exposure、geometry rejection、canonical duplicate/cross-node IDSW/common-information rejection。`duplicate_terminal_lock_count` 保留通用“同一 timestamp+target 出现多个 resource”计数，不再由 `erroneous_duplicate_lock_count` 覆盖；后者仅计 legacy `k=1`、当前 coalition/assignment 版本冲突或超过 `required_resource_count`。同一 resource 跨帧持续锁定只进入 `same_resource_lock_continuity_count`，授权 coalition 内同帧多资源锁进入 `authorized_cooperative_lock_count`。

探测三项要求同时存在 `truth_timestamps` 机会集合与检测/航迹到 truth 的离线配对裁决。配对证据可以是落入 truth pair 集合的 `TrackRecord.truth_id`，也可以是显式 `offline_detection_match/offline_track_truth_match/offline_detection_miss/offline_missed_detection` 事件。仅有 truth opportunity 列表、所有 track 均为 `truth_id=None` 且无显式 match/miss 时，`detection_probability/missed_detection_rate/false_alarm_rate=None` 且 `metric_availability.status=unavailable`。可用时按 pair 集合求命中和漏检；`truth_id=None` 的 center track 不自动计虚警。

`center_replan_request_created/deduplicated/ack_no_change/applied/expired` 已接入请求、去重、no-change、applied、expired、pending dwell 总时长和 no-change/applied 收敛均值。D6 优先消费 `request_id/requested_at/resolved_at/pending_dwell_s`，并在 metadata 审计保留 target、coalition/version、risk signature 和 resolved plan/version。无这些事件时所有 replan 指标为 `None/unavailable`。

每个新增指标在通用 `metric_availability` 中记录 `status/reason/numerator/denominator`，M 对 N 子集继续保留兼容的 `m_to_n_metric_availability`。数值 `0` 仅表示证据完整且事件确为零；缺证据为 JSON/CSV 空值和 `unavailable`；路线无此概念为 `not_applicable`。batch summary 分别输出可用、unavailable 和 not-applicable 样本数，并继续按实际 `drone_count/resource_count/target_count/camera_count` 分组。

## 2026-07-10 P1 扩展

本轮已补齐以下离线评估接口，不运行 AirSim：

- 二级接管生命周期：统计 `registration_usable`、`takeover_ready`、`pending_secondary_plan`、`secondary_plan_active` 驻留时间、ready-to-active latency、fallback、lease expiry 和 stale-plan reject。没有显式 lifecycle event 时字段为 `None/unavailable`，不写成 0。
- D5 YOLO/MOT：统计 detection recall、local-ID continuity、cross-view registration rate、pipeline latency、CPU/GPU budget utilization 和 budget violation。recall/continuity 只读取事件中嵌套的 `offline_truth`；在线顶层出现 `truth_id/actor_name/object_name/segmentation_id` 会计入 `online_truth_field_violation_count`。
- 四导引律同 seed 对照：`GuidanceLawComparisonReportGenerator` 对 `pure_pursuit/radar_pn/png_vm/png_ttc` 按相同 `scenario_group/version/seed/actual scale` 配对，输出 CSV、JSON、中文 Markdown 和差值曲线。D6 不选择导引律。
- 场景库：`ScenarioLibrary` 输出带 tags、difficulty、expected failure modes、parameters 和 seed matrix 的 JSON/CSV/Markdown；`scenario_group` 保持跨 seed 稳定，在线 truth policy 固定为 `forbidden`。
- `ReportGenerator.write_plots()` 新增 `visual_perception_metrics.png`；AirSim calibration record/cross-seed 表同步携带 lifecycle、视觉预算、tracker backend 和 experiment guidance law。

main 需要按事件写盘以下字段：

```text
d4_secondary_readiness:
  timestamp, readiness_state
d4_secondary_plan_state:
  timestamp, plan_state, plan_id, plan_version, owner, lease_id, lease_expiry_timestamp
secondary_takeover_fallback / secondary_lease_expired / stale_plan_reject:
  timestamp, reason, plan_id, plan_version, owner
d5_yolo_mot_frame:
  timestamp, camera_id, detection_backend, tracker_backend,
  cross_view_candidate_count, cross_view_registered_count,
  detector_latency_ms, tracker_latency_ms, pipeline_latency_ms,
  cpu_budget_utilization, gpu_budget_utilization,
  latency_budget_ms, cpu_budget_utilization_limit, gpu_budget_utilization_limit,
  offline_truth.{visible_truth_count,matched_truth_count,truth_to_local_track_id}
episode metadata:
  experiment_guidance_law, scenario_group, scenario_version, seed,
  drone_count, resource_count, target_count, camera_count
```

## 当前能力

已实现的核心数据模型：

- `EpisodeMetrics`：单 episode 标量指标对象，包含 `mission_outcome`、`success_reason`、`failure_reason`、`eval_priority`、`implementation_status`、`evidence_path`、`scenario_version`、`standard_mapping_version`、`standard_metric_family_summary`、`metric_scope` 和规模字段 `drone_count/resource_count/target_count/camera_count`。
- `TrackRecord`：探测和跟踪记录，保留 `global_track_id`、`truth_id`、位置、真值位置、协方差摘要和来源。
- `AssignmentRecord`：分配快照，保留 `plan_id`、`version`、资源、目标、授权状态和评估侧真值标签。
- `EventRecord`：通用事件记录，用于降级、安全、D5/D7 gate、通信元数据等。
- `LinkRecord`：跨节点通信记录，支持 latency/drop/out-of-order/stale/video metadata/bbox delivery。
- `TerminalRecord`：末端配准记录，支持局部视觉 ID、锁定、歧义、友方 overlap hold 和正确性标签。

已实现的指标族：

- 探测：`detection_probability`、`false_alarm_rate`、`missed_detection_rate`。
- 跟踪：`track_rmse`、`track_continuity`、强制显式保留的 `id_switch_count`。
- 分配：`duplicate_assignment_count`、`unassigned_high_threat_count`。
- 降级：`failover_time`、`consensus_rounds`、`degraded_completion_rate`、`active_degradation_count`、`active_degradation_precision`、`active_degradation_label_count`、`unnecessary_active_degradation_count`、`passive_failover_count`、`secondary_node_takeover_count`、`secondary_reassignment_count`、`d4_reassign_pending_count`、`distributed_fallback_count`、`failover_active_window_delta_s`。precision 只以可分类 review label 样本为分母；`active_degradation_label_count=0` 时输出 unavailable/JSON `null`，不伪装成 0 精度。
- 末端：`terminal_association_accuracy`、`terminal_id_switch_count`、`ambiguous_fov_event_count`、`friend_overlap_hold_count`、`time_to_terminal_lock`、`terminal_lock_count`、`multi_view_consensus_rate`、`cross_view_conflict_count`、`duplicate_terminal_lock_count`。
- 二级视角/侦察：`secondary_network_joint_full_view_frame_rate`、`secondary_network_mean_coverage_ratio`、`secondary_visible_target_union_ratio`、`secondary_single_camera_full_view_frame_rate`、`secondary_detect_count`、`projection_valid_rate`、`geometry_gate_pass_rate`、`registered_candidate_count`、`stable_cross_view_registration_count`、`not_registered_count`、`cross_view_association_count`、`secondary_detect_available_but_not_registered_count`、`cue_pointing_error_*`、`gimbal_pointing_error_*`。
- 通信：`cross_node_latency_ms`、`message_drop_rate`、`out_of_order_count`、`stale_track_update_count`、`video_metadata_delivery_rate`、`bbox_delivery_rate`、`consensus_latency_s`。
- D7 gate 与拦截统计：`camera_quality_gate_pass_rate`、`los_quality_gate_pass_rate`、`maneuver_margin_gate_pass_rate`、`terminal_switch_allowed_rate`、`visual_png_switch_count`、`terminal_takeover_rate`、`terminal_switch_reject_count`、`mode_switch_count`、`terminal_contract_reject_count`、四层 execution funnel、pair/target/coalition 三层 physical success、detect/coast 六项诊断、`collision_intercept_count`、`range_intercept_count`、`time_to_intercept_s`、`min_range_m`、`gate_reject_count`。
- 安全：`constraint_violation_count`、`human_override_count`。
- 任务结果/root cause：每个 episode 输出 `mission_outcome=success/partial/failed/aborted`、`success_reason`、`failure_reason`，metadata 保留 `root_cause`、`top_failure_causes`、`failure_cause_scores` 和 `failure_cause_details`；根因只从已写盘 records/metadata 和 D6 指标被动派生，覆盖 tracking、assignment、terminal_gate、guidance、coverage、runtime_exception、communication、safety、performance 等类别。
- 性能监测：`module_duration_ms`、`loop_latency_ms`、`record_latency_ms`、`cpu_budget_utilization`、`gpu_budget_utilization`、`performance_budget_violation_count` 进入 summary；metadata 保留 module/loop/record latency 分布和 CPU/GPU budget 占位状态。
- 标准化评估映射最小版：`cuas-standard-map-v1` 已把 `COURAGEOUS/MDPI/OCEF -> EpisodeMetrics` 映射落到 D6。映射字段为 `engineering_metric`、`standard_metric_family`、`standard_sources`、`implementation_status`、`evidence_requirement`，覆盖 mission/root cause、detection、tracking、assignment、degradation、terminal、communication、guidance/intercept、safety、performance、reproducibility/evidence。`MetricsCollector.compute_episode()` 在 metadata 中写入 `standard_mapping_version`、`standard_metric_families`、`scenario_version` 和 `standard_mapping` 摘要；`ReportGenerator.write_standard_mapping_csv()` 可输出 `standard_metric_mapping.csv`，Markdown 报告在 `EVAL Tracking` 后输出 `Standard C-UAS Mapping` 表。

D2/D6 的硬规则仍然保留：`id_switch_count` 必须显式输出，不能被综合准确率隐藏。

## 规模归一化

D6 按实际 `drone_count/resource_count/target_count/camera_count` 归一化和分组。规模优先来自 `truth_summary` 或 Blocks replay 的资源、目标和相机字段；缺失时才从已记录的资源、目标、终端和相机元数据推断。`2v2`、`5v5` 只作为 baseline 场景名，不能用于推断算法规模或报告分母。二级网络 full-view/coverage 和单相机 full-view 指标使用实际 target/camera count 或日志中显式记录的实际计数作为分母。报告会按 `metric_scope`、`seed`、`scenario_group` 和实际规模字段分组，区分 execution metrics 与 contract metrics。

## AirSim 与 Runtime 输入

D6 已有离线 loader，但不直接连接 AirSim：

- `load_blocks_replay_jsonl()` 读取 main runtime 写出的 `blocks_frames.jsonl` 和可选 `blocks_sensor_observations.jsonl`。
- `load_main_episode_bus_metrics()` / `load_main_episode_bus_metric_files()` 读取 main runtime 写出的 `main_episode_bus_metrics.json` 与 `main_episode_bus_contract_metrics.json`，还原为 `EpisodeMetrics`，保留 execution/contract 口径、seed/scenario/实际规模字段和 metadata 分布。
- `load_d4_active_degradation_decisions()` 读取 D4 主动降级 CSV，并离线消费 `review_label`、trigger/decision timestamp、selected coordinator、coverage cell 和 pre/post window 字段。
- `load_d7_intercept_outputs()` / `load_d7_guidance_timeseries()` 读取 D7 `control_commands.csv`、`intercept_summary.json`、`guidance_records.csv`、`guidance_summaries.json`。
- `load_episode_log_jsonl()` 读取 D6 标准化 dry-run JSONL。
- `load_airsim_calibration_records()` / `AirSimCalibrationReportGenerator` 自动扫描 main runtime 已写盘的 `d4d5_stress_metrics.json`、`airsim_blocks_summary.json` 和 `main_episode_bus/*.json`，保留旧的逐 seed `GROUP_FIELDS`/CSV，并新增去 seed、包含实际规模的 cross-seed aggregate。records 保留原始 `scenario_version`，统计键只移除其中 `seed1/seed2/...` 这类运行参数，防止真实多 seed 被拆成单样本组；baseline/enhanced 仍要求相同稳定 `scenario_group`、规范化版本、实际 `drone_count/resource_count/target_count/camera_count`、几何、detection backend 和 seed。case-specific `scenario/case_name` 只保留审计。active-degradation 显式标注优先读取 d4d5 stress metrics，再 fallback main `EpisodeMetrics`。

这些 loader 都是 file/offline-only。D6 已能消费 D4/D5/D7 写盘产物；D6 不拥有 live bus 订阅、AirSim 原生 recording 通用解析器或自动跨目录 episode 聚合调度。

截至 2026-07-10，main runtime 的 `--p1-calibration-sweep` 仍由 main 负责 AirSim 启动、settings 组合、reset-separated seeds/cases 和日志落盘。D6 bundle 保留 `airsim_calibration_records.csv`、`airsim_calibration_summary.csv`、`airsim_calibration_summary.json`、`airsim_calibration_report.md`，并新增 `airsim_calibration_cross_seed_aggregate.csv`、`airsim_calibration_paired_comparison.csv`、`airsim_calibration_aggregate.json`、`airsim_calibration_aggregate_report.md`。D6 只读取 main 已写盘目录，不参与 sweep 调度或场景控制。

配对统计中，`pair_count=1` 只标记为 `descriptive_only`，保留单次差值但不输出 bootstrap CI 或 Cohen's dz；至少两个有效 seed 对才标记 `available` 并运行固定 RNG 的 percentile bootstrap。缺 baseline/enhanced seed、指标不可用和零 review-label precision 都显式保留，不会按 0 或成功样本处理。

AirSim calibration record 和 cross-seed aggregate 现直接消费 execution/contract `EpisodeMetrics` 中的 `intercept_success_count`、`collision_intercept_count`、`range_intercept_count`、`min_range_m`、`time_to_intercept_s`、`visual_png_switch_count`、`terminal_switch_allowed_rate`、`terminal_takeover_rate`、`gate_reject_count`；`intercept_abort_count` 从各 scope 自己的 `metadata.intercept_status_counts` 派生。只有 episode 存在 `intercept_summary.json`、`control_commands.csv`、显式 intercept summary/pair/status，或正数 D7 control execution event count 时这些字段才可用；read-only episode 的 dataclass 默认零会转换为 `None/unavailable`。execution 与 contract 不合并。cross-seed 对计数指标输出 `sum`，对四类拦截 outcome 额外输出实际 `target_count` 累计得到的 `opportunity_count` 和 `rate`；距离、时间和比例只使用 mean/std/min/max，不把它们的跨 seed 求和解释为工程指标。`Interception Outcome` 只列有执行证据且 opportunity 可计算的行，scope 列明确区分 execution 与 contract。

截至 2026-07-07，main/orchestrator 已在真实 D7 AirSim 执行后把 `control_commands.csv` 与 `intercept_summary.json` 中的执行结果合并进正式 `main_episode_bus_metrics.json`，同时把执行前的合同检查口径保留为 `main_episode_bus_contract_metrics.json`。因此正式 episode 指标中的 `intercept_success_count`、`collision_intercept_count`、`range_intercept_count`、`terminal_contract_reject_count`、`guidance_law_counts` 等字段以执行后结果为准；raw contract metrics 只用于诊断 D3/D4/D5/D7 gate 合同。D6 通过 `metric_scope=execution/contract` 保留这两个口径，并在 CSV/Markdown 中分组展示。episode CSV 保留 metadata JSON；Markdown 在存在数据时输出 terminal switch/contract reject reason 分布。D6 仍只读取这些文件或由 main 写出的 metrics，不参与控制或重规划。

2026-07-10 对 `outputs/p1_gap_closure_2v2_smoke_20260710/episode_006_full_flow` 的复核表明：正式 execution 文件记录实际规模 `2/2/2/2`、`intercept_success_count=2`、`visual_png_switch_count=3`；contract 文件保持独立诊断口径。该 episode 的 `airsim_blocks_summary.integrated_result.metrics` 仍含执行前旧快照（规模 `3/3/2/0`）。D6 loader 明确以两个 `main_episode_bus` metrics 文件为准并忽略旧快照，且每个 calibration record 的 evidence path 指向其实际 execution/contract 文件；旧快照一致性需要 main runtime 单独修复，D6 不回写运行时文件。

同日使用 `p1_gap_closure_2v2_multiseed_20260710_seed001..010/blocks_sequence_summary.json` 验收：full-flow execution 聚合为 10 seeds、成功 `18/20`（0.9）、碰撞拦截 18、距离拦截 0、abort 2；`min_range_m` 均值约 1.812 m，`time_to_intercept_s` 均值约 3.66 s，visual PNG switch 合计 88，terminal switch allowed rate 均值约 0.0822，terminal takeover rate 均值 1.0，gate reject 合计 881。该结果证明 D6 可以直接从现有 summaries 生成多 seed 拦截结果，D6 未参与任何控制。

D6 现在也能离线汇总 main/D4/D5 已写盘的二级视角 metadata，并在报告中明确对比 `fixed_downlook_secondary` 与 `mobile_recon_gimbal`。该口径只消费覆盖、FOV、分辨率、cue source、cross-view association、D5 registration 和 cue/gimbal pointing error 字段；D6 不下发 cue、不控制云台、不参与接管或重分配。

P1 二级侦察 detect-to-registration 校准报告已经补齐分层漏斗字段：`secondary_detect_count`、`secondary_visible_target_union_ratio`、`secondary_network_joint_full_view_frame_rate`、`projection_valid_rate`、`geometry_gate_pass_rate`、`registered_candidate_count`、`stable_cross_view_registration_count` 和 `not_registered_count`。reject/outcome reason 统一保留 `not_all_targets_visible`、`network_union_incomplete`、`projection_invalid`、`geometry_gate_rejected`、`stability_window_failed`、`no_global_binding`、`stale_or_missing_recon_cue`、`registered_to_global_track`，缺失时按 0 输出，便于跨 seed 比较。

截至 2026-07-09，P1 AirSim calibration Markdown 进一步输出 50m vs 200m 二级覆盖对比、coverage funnel、Detect-to-registration funnel、baseline vs enhanced 对照、D7 guidance reject reason 和 Standard C-UAS Mapping。baseline/enhanced 只使用日志显式写出的 comparison role；D6 不从 `2v2/5v5` 场景名推断规模或对照组，不接 TrackEval、Stone Soup、SCRIMMAGE 等外部 evaluator。

截至 2026-07-08，`research_modules/airsim_runtime/outputs/p1_d4d5_mobile_recon_20260708_055948*` 是历史 mobile recon stress 批次，可作为 D6 已能消费 `mobile_recon_gimbal`、coverage、bbox、gimbal 和 funnel 字段的旧证据。

2026-07-08 registration calibration v2 历史基线位于 `research_modules/airsim_runtime/outputs/p1_d4d5_registration_calibration_runtime_v2_20260708*`。D6 bundle 已生成 `d6_airsim_calibration/airsim_calibration_records.csv`、`airsim_calibration_summary.csv`、`airsim_calibration_summary.json` 和 `airsim_calibration_report.md`。该 v2 批次为 single seed、3 case，height 200 m、FOV 110 deg、secondary_count 3；当时指标为 `projection_valid_rate=1.0`、`geometry_gate_pass_rate≈0.474`、stable cross-view registration 51/55/53、cross-view association 4/4/5、degradation case `not_registered_count=35/35`、full-view mean≈0.048、best≈0.143、coverage mean≈0.771。该历史批次证明 D6 报告链路能够输出 projection/gate/stable registration/not-registered/funnel/D7 reject，但不作为 2026-07-11 P1 当前结论。D6 仍只消费日志，不参与控制，也不从 `2v2/5v5` 场景名推断规模。

## 当前 P0/P1 状态（2026-07-12）

### 2026-07-11 四导引律短窗口实测证据

main 已修复 experiment-level guidance law 的执行后回灌，并从
`research_modules/airsim_runtime/outputs/p1_guidance_four_law_smoke_20260711/`
生成 D6 同 seed 对照产物。`guidance_same_seed_pairs.csv` 包含 21 条“候选导引律 x
指标”配对记录，但每条记录的 `pair_count=1`，实际只有 seed 7 一个独立 seed；不能把
21 条指标行解释为 21 次独立实验。

该 smoke 使用 2 秒短窗口，Pure Pursuit、Radar PN、PNG VM 和 PNG TTC 均 timeout，
拦截成功率均为 0。PNG VM/TTC 的 `terminal_switch_allowed_rate` 分别约为 0.762 和
0.810，最小距离分别约为 2.812 m 和 2.798 m。这些结果证明四律标签回灌、同 seed
配对、末端切换事件和距离指标能够被 D6 正确消费；它们不构成最终命中率、导引律优劣
或统计显著性结论。延长运行窗口并开展真实多 seed、同几何、同规模对照仍为 P1。

- P0：P0-A/P0-C 字段已补齐，当前没有新增运行级 P0 blocker。D6 输出 mission outcome、success/failure reason、top failure causes/root cause、性能监测字段、EVAL tracking schema 和 `cuas-standard-map-v1` 标准化评估映射最小版；仍保持离线消费日志，不参与控制；指标继续按实际规模归一化，不从 `5v5` 名称推断分母。
- P1 已闭合：coalition commit、`contract/control/switch/physical` 四层验收、pair/target/coalition 分层 physical success、detect/coast 和 PNG delivery availability-aware 指标及对照 bundle。CV T001 8/10、二级/分布式 commit、missing-ACK fail-closed 和 2v2 candidate `20/20` 非退化均有 evidence；自然 2v2 未触发 soft/trend，不宣称增强算法贡献。
- P1 仍开放：同一 z=-30 m、35 s 几何与同 seed 的 M5N2 paired baseline/candidate，独立 `png_ttc` 多 seed，1-5 帧 dropout 与 0.25 s fail-closed，trend coast 默认 profile 判定，以及既有完整标准化报告、场景库/CI 接线和长期真实 replay/review/window/阈值趋势。缺失字段继续为 unavailable，不得补 0。
- P2：py-motmetrics IDF1/MOTA/MOTP adapter 已作为冻结 replay 上的 optional benchmark 实现；TrackEval、Stone Soup、OSPA/GOSPA、HOTA 和非参数统计仍待实现。所有 P2 能力均不进入在线链路、默认依赖或控制决策。

## PNG 策略

PNG 截图不是 D6 计算指标的必需输入。D6 可用 bbox、相机内外参、timestamp、资源/相机 ID、`assigned_global_track_id`、object label、truth/validation label 和 D7 gate 结果计算多视角、末端和 visual PNG switch 指标。`--save-images` 只应在调试视角时启用；指标主线依赖 metadata。

## 文档

- 模块计划：`PLAN.md`
- AirSim 离线集成计划：`AIRSIM_INTEGRATION_PLAN.md`
- 详细算法与实施说明：`docs/ALGORITHM_AND_IMPLEMENTATION.md`
- 文档索引：`docs/README.md`
- 示例实验报告：`EXPERIMENT_REPORT.md`

## 运行测试

从仓库根目录运行：

```bash
pytest -q research_modules/d6_evaluation_metrics/tests
```

## 运行 100 Seed 示例

```bash
python3 research_modules/d6_evaluation_metrics/scripts/run_batch_example.py --seeds 100
```

默认输出：

```text
research_modules/d6_evaluation_metrics/outputs/example_batch/
  episode_metrics.csv
  summary_metrics.csv
  batch_report.md
  logs/*.jsonl
  plots/*.png
```

## 核心 API 示例

```python
from d6_evaluation_metrics import (
    AssignmentRecord,
    EventRecord,
    LinkRecord,
    MetricsCollector,
    ReportGenerator,
    TerminalRecord,
    TrackRecord,
)

collector = MetricsCollector()
collector.add_track(
    TrackRecord(
        timestamp=0.0,
        global_track_id="G0",
        truth_id="T0",
        position=(0.0, 0.0, -10.0),
        truth_position=(0.0, 0.0, -10.0),
    )
)
collector.add_event(EventRecord(timestamp=1.0, event_type="terminal_lock"))
collector.add_link(
    LinkRecord(
        timestamp=1.0,
        source_node_id="interceptor_01",
        target_node_id="center",
        payload_kind="track",
        sent_timestamp=0.9,
        received_timestamp=1.0,
    )
)
metrics = collector.compute_episode(episode_id="example", duration=10.0)
ReportGenerator().write_standard_mapping_csv("standard_metric_mapping.csv")
```

## 外部项状态

py-motmetrics 已有隔离 adapter、冻结 schema、available/unavailable 测试及 `motmetrics 1.4.0` 实际环境验证。Stone Soup metrics、TrackEval、OSPA/GOSPA/HOTA、AirSim 原生 recording replay 和 SCRIMMAGE metrics bridge仍没有实际 adapter；它们继续作为 P2/P3 可选项，不替代当前本地离线指标主线。

## P1 系统证据统一汇总（2026-07-13）

`P1SystemEvidenceReportGenerator` 新增一套不影响旧 `P1AcceptanceReportGenerator` 的版本化离线接口，统一消费以下已写盘证据：

- D1 dense crossing：冻结 replay 的 spacing/seed provenance、双时间戳、协方差、source lineage、观测接收/拒绝和在线 truth 隔离。
- D2 六难度 profile：逐 seed IDSW、continuity、false track、RMSE、P95 loop latency、admission 与 `scenario_still_non_discriminative`。
- D3：membership change/hold、plan version、coalition version/epoch churn，以及 `terminal_authorization_scope` 和 `arrival_coordination_required`。
- D4：逐 tick 或 fault-case 的 ACK、missing/rejected ACK、lease、epoch、owner、commit state、execution allowed、fail-closed 和失败原因。
- D5：per-primary 独立锁定/拒绝原因与 ByteTrack/BoT-SORT native active rate、IoU fallback、precision/recall、continuity、local IDSW、P95 latency、admitted/reasons。
- D7：兼容 per-seed summary 与 pair diagnostics，严格分离 `contract_allowed`、`control_allowed`、`mode_switched`、`physical_intercept`，并保留物理最近距离和失败漏斗。

所有指标都有独立 `*_availability`，缺字段不补零；每个文件保留 schema、路径、SHA256、producer/run 和 provenance。聚合数值按显式 seed 计算固定 RNG、2000 次 percentile bootstrap 95% CI，不足两个 seed 时 CI 为 unavailable。失败原因按来源和全局输出分布。D2/D5 的 truth 指标只消费离线聚合值，报告不导出 truth identity。D6 仍不启动 AirSim、不加载 YOLO/MOT 权重、不参与分配、接管或导引。

```bash
python3 research_modules/d6_evaluation_metrics/scripts/run_p1_system_evidence_report.py \
  --output-dir /tmp/d6-p1-system \
  --d1-dense-crossing-summary /path/to/d1.json \
  --d2-difficulty-summary /path/to/d2.json \
  --d3-churn-summary /path/to/d3.json \
  --d4-communication-summary /path/to/d4.json \
  --d5-per-primary-summary /path/to/d5_per_primary.json \
  --d5-native-mot-summary /path/to/d5.json \
  --d7-per-primary-summary /path/to/d7.json
```

输出固定为 `p1_system_evidence_rows.csv`、`p1_system_evidence_aggregate.json`、中文 `P1_SYSTEM_EVIDENCE_REPORT.md` 和 `p1_system_evidence_overview.png`。

## Replay 与执行指标合并（2026-07-13）

`merge_replay_with_execution_metrics()` 为 main 提供纯函数接口，用于合并
`integrated_replay/metrics.json` 与 `main_episode_bus_metrics.json`。终端配准、
cross-view、在线 truth 审计、合同/控制许可和物理拦截等执行指标，在 main bus 有明确
值时以 main bus 为规范值；被覆盖的 replay 原值和两侧 evidence availability 保留在
`execution_metric_provenance` 中。

```python
from d6_evaluation_metrics import merge_replay_with_execution_metrics

bundle = merge_replay_with_execution_metrics(
    replay_metrics,
    main_bus_execution_metrics,
    persisted_frame_count=11,
    warmup_inclusive_frame_count=12,
)
assert bundle["execution_metrics_merged"] is True
```

接口不把缺失值补成 `0`。`persisted_frame_count` 与
`warmup_inclusive_frame_count` 是独立证据，分别携带 availability 和 source；不能由
其中一个推导另一个。D6 只返回合并 bundle，写盘位置和 episode 调度仍由 main 负责。

## D2 准入 Schema 兼容（2026-07-15）

`P1SystemEvidenceReportGenerator` 输出升级为 `d6-p1-system-evidence-v2`，同时接受三类
D2 准入证据：v2 `gates`、legacy structured `checks` 和 legacy bool `checks`。失败解析
优先读取 v2 gate 自身的 `reason`，其次读取 `gate_reasons`；失败项始终保留 gate 名，
reason 缺失时写为 `gate_name:reason_unavailable`，不会生成空失败原因。

逐行 CSV、aggregate JSON 和中文 Markdown 现在保留 source-level decision、逐 difficulty
assessment、五项 gate outcome/reason、IDSW、连续率 baseline/headroom/actual/required/error
reduction、false-track、P95、truth leakage、promotion recommendation、默认路径状态和 truth
alignment。历史 artifact 缺字段时值为 `None`/CSV 空值且状态为 `unavailable`，绝不补 `0`。

2026-07-15 已消费正式冻结 replay
`../d2_data_association/outputs/p1_identity_ceiling_aware_v2_20260715/d2_identity_calibration_v2.json`，
在 `outputs/p1_identity_ceiling_aware_v2_20260715/` 生成 D2-only CSV、JSON、中文 Markdown 和 PNG。
总体 GNN 候选五 gate 全部通过，IDSW baseline/candidate=`1.3583/0.6167`，continuity
headroom/actual/required/error reduction=`0.018954/0.002908/0.001895/0.153448`；这只形成
`promotion_recommended=true` 的评审建议。分档仅 clutter/combined 通过，delayed_noisy、dropout、
nominal、tight_crossing 因 baseline IDSW=0 fail-closed。dropout truth alignment 在
screening/confirmation 为 `10/10`、`20/20` partial；JPDA research adapter 不准入；
`default_online_path_changed=false`，默认 GNN/Hungarian 未改变。其他六源均为 unavailable，
因此 `full_system_decision=not_evaluated`，不得宣称全系统通过。D6 不重算 D2 判决，不参与控制。

验证日期 2026-07-15：system-evidence 专项 `31 passed`，D6 全量 `243 passed`；本批未启动
AirSim，另有一条既有 Matplotlib `Axes3D` 环境 warning。

## 三维规模化 D1/D2 真值隔离制品（2026-07-20）

`truth_isolated_offline.py` 已实现 D1、D2 公共离线评估制品的 D6 适配入口。D6 只调用
公开 DTO 的 `to_dict()`、D1 的 `aggregation_records()`，或读取由 main 提供期望
SHA-256 的持久化制品。该路径不导入 D1/D2 在线 tracker，不读取私有滤波状态，也不根据
距离、名称或后验结果重建 `global_track_id` 与真值的对应关系。

公开入口包括：

- `adapt_d1_offline_consistency()`：保留 D1 总体 RMSE、NEES、NIS、sample count、
  availability、不可用原因、结果摘要和 `online_evidence/truth_sidecar/d2_lineage_mapping`
  三类输入摘要，并按显式 scenario/sensor/range 重新汇总公开逐观测记录；当前 D1 字段
  `d2_lineage_mapping` 是规范名称，旧 `canonical_mapping` 只在输入侧兼容，双字段摘要不一致
  时 fail-closed；
- `adapt_d2_scalable_3d_identity()`：保留显式 `id_switch_count`、三类 continuity、
  duplicate、confusion matrix、coverage counts、来源摘要和审计字段；D2 未同时证明原始
  来源摘要/record sequence 已验证、在线真值隔离已验证且未使用身份启发式时，全部身份
  指标保持 `None/unavailable`，truth coverage/count 也不进入聚合；文件输入必须同时提供
  制品 SHA-256 和完整四类 expected source hash；
- `build_truth_isolated_episode_record()`、
  `aggregate_truth_isolated_episode_records()` 和
  `TruthIsolatedOfflineReportGenerator`：按实际目标/资源/侦察节点/相机数量与 seed 输出
  逐 seed CSV、D1 sensor-range CSV、聚合 JSON 和中文 Markdown。

验证日期为 2026-07-20。专项测试 `14 passed`，D6 全量测试 `334 passed`；另有一条既有
Matplotlib `Axes3D` 环境 warning。结构回归覆盖 5、20、50、100、200 五档规模、DTO、
文件及四类来源 SHA-256、内容篡改、跨 episode 混用、缺制品、D1 availability 冲突、
D1 新旧 lineage 字段兼容/冲突/缺失、D2 零帧假零和未验证真值隔离。逐 seed CSV、聚合
JSON 和中文 Markdown 均使用稳定的 `input_digests.d2_lineage_mapping` 来源名称。
该验证使用最小
离线 fixture，没有启动 AirSim，没有运行正式多 seed，也没有形成 D1 精度或 D2 身份连续
性能结论。

main-owned scalable 3D reporting 已写出 D1/D2 制品、校验 manifest/source hash 并调用本接口
生成 episode/batch bundle；该接线不属于 D6 owned path，本轮未代改。D6 侧公共合同已实现。
2026-07-23 已补充 clean 200 对 200、20 seed 的描述性批量复核；正式多规模矩阵、严格身份指标
和工程阈值仍开放。

## D2 evaluator-only 部分身份诊断（2026-07-23）

`adapt_d2_scalable_3d_identity()` 现接入
`d2.scalable3d_partial_identity_diagnostics.v1`。该块与 strict
`id_switch_count`/continuity/duplicate/confusion 完全分离：strict 不可用时，D6 仍可独立
保留 mapping、完整 frame、adjacent-transition 三类 coverage、保守 IDSW lower bound、
anchor interval count 和排除原因；lower bound 永不回填 strict `id_switch_count`，D6 不输出
IDSW upper bound，也不让该离线块参与控制。

partial 只有在以下条件全部满足时才为 available：

- block schema、scope、固定 denominator definitions、availability/reason 和计数守恒通过；
- coverage 为有限数且与分子/分母一致，lower bound 不超过 anchor interval；strict 可用时
  lower bound 还不得超过 strict IDSW；
- D2 audit/config 明确绑定同一 partial schema，在线 truth 隔离和无 identity heuristic 已验证；
- `scalable3d-offline-identity-evaluation-manifest-v1` 的 episode、availability、strict metric
  availability、evaluation SHA-256 以及 D1/D2/truth/evidence 四类来源摘要与 evaluation 一致。

文件输入默认查找 evaluation 同目录的 `manifest.json`；调用方也可显式传
`identity_manifest` 和 `expected_identity_manifest_sha256`。旧 evaluation v1 不含 partial
块时继续读取，strict 字段保持原值，partial 单独写为
`unavailable/partial_identity_diagnostics_missing`。错版本、manifest 缺失、evaluation/source
hash 不符、非有限 coverage、计数不守恒等情况也只关闭 partial，并在 DTO、逐 seed CSV、
aggregate JSON 和中文 Markdown 中保留稳定 reason。

2026-07-23 的确定性合同 fixture 使用 10 帧汇总和 12 条 mapping 计数，验证 coverage
`8/10`、`4/10`、`3/5`、4 个 anchor interval、lower bound 2 和 1 个重复映射 anchor 排除。
另一正例同时保留 strict IDSW 3 与 lower bound 2，证明两列不互相覆盖。专项测试
`26 passed`，D6 全量 `567 passed, 1 warning in 22.96s`，验收门限为零失败；warning 是既有
Matplotlib `Axes3D` 环境提示。全量从 555 增至 567 的 12 项均来自本专项新增的 3 项独立测试和
9 项篡改参数化用例。

同日 D6 只读消费 clean `4ac3bb2` 的 nominal 200 对 200、seed 1000、10 秒真实 producer
episode。manifest/evaluation 文件 SHA-256 分别为 `5b9238fe...e3463` 和
`b743cd7f...f83a1`，online D1、online D2、observation truth labels、identity evidence
四项源文件 SHA-256 均经独立复算并与两份制品一致。输出确认
`truth_isolation_verified=true`，但 strict `id_switch_count` 因
`multiple_truth_targets_for_global_track` 保持 `None/unavailable`，没有被 partial 回填。
partial provenance 可用，mapping coverage 为 `8906/9038=0.985395`，完整 frame coverage 为
`3/48=0.0625`，adjacent-transition coverage 为 `0/9400=0`，385 个 anchor interval 上的
保守 IDSW lower bound 为 7；upper bound 未生成，`control_consumed=false`。

该真实制品只有一个 seed，且不是 AirSim 或正式困难场景矩阵。它关闭“consumer 尚未读取真实
producer 制品”的接口子项，不形成 strict IDSW、coverage 稳定性、算法优劣或多 seed 性能结论。

### 20 seed 批量复核

2026-07-23 对 clean commit `5263e2b` 的 nominal 200 对 200、10 秒、seed `1000-1019`
执行持久化批量复核。每个 episode 均复算 D1 consistency、D2 identity 和 D6 truth-isolated
三层 manifest 的来源/输出 SHA-256，再从 producer 制品重新构建 D6 episode record。20/20
manifest 链通过，20/20 重建记录与已持久化 `episode_record.json` 完全一致，20/20
`online_truth_isolation_verified=true`。批量产物写入同批输出根下
`d6_truth_isolated_20seed/`。

D1 的 20 个 episode 均为 `partial`。NIS、归一化 NIS 和 NIS 门覆盖率可用，跨 seed 均值分别为
`3.385237`、`1.146517` 和 `0.991315`；RMSE、NEES 和归一化 NEES 因
`d2_lineage_mapping_missing` 保持 unavailable。D2 strict `id_switch_count`、
continuity 和 duplicate 为 0/20 可用，逐 episode 原因均为
`multiple_truth_targets_for_global_track`。

partial 证据为 20/20 可用。micro mapping coverage 为
`178531/181110=0.985760`，完整 frame coverage 为 `103/959=0.107404`，
adjacent-transition coverage 为 `1149/187800=0.006118`。19 个 episode 的 lower bound
可用，合计为 199；另 1 个 episode 因 `no_evaluable_identity_transitions` 不可用。汇总包含
15215 个 anchor interval、9 个重复 anchor 排除，并保持
`strict_id_switch_count_backfilled=false`、`id_switch_upper_bound_reported=false` 和
`control_consumed=false`。

该批量复核证明 D6 可以在不信任持久化汇总值的前提下重新验证 producer 制品并聚合 20 个 seed。
它仍是单一 nominal 规模和短时质点场景。frame/transition coverage 较低，strict 身份指标仍缺失，
因此不能作为算法晋级、控制切换或正式 200 对 200 性能结论。

## D2 identity commitment v2 消费与聚合（2026-07-23）

D6 已实现对 `d2.scalable3d_identity_evaluation.v1/v2` 的严格分流。v1 保持原有 strict
身份指标行为，新增 commitment 子记录固定为 `unavailable`；即使 producer 提供兼容
`identity_commitment_record_count=0`，D6 也不会把 commitment coverage 或 count 伪造为
可用零值。v2 必须同时满足 evaluation/evidence/commitment/audit schema 与 policy、四类
source SHA-256、嵌入 evidence bundle 规范哈希、全部与 `created/matched` 两组分母守恒、
coverage 与 count 一致、reason counts 可复算、水位线年龄有限且非负、overflow
record/track 边界一致，以及 candidate/source binding violation 均为 0；缺字段或篡改直接
失败关闭。

新增 `D2IdentityCommitmentEvidenceRecord` 以 availability-aware metrics 输出并聚合：

- all/observed commitment coverage、denominator、committed/uncommitted count；
- uncommitted mapping count、commitment state/reason 和 recovery-blocked reason counts；
- blocker count record/positive/sum/min/mean/max 与 watermark age count/min/mean/max；
- overflow record/track count、兼容 binding count 和两个 binding violation count。

上述字段已进入逐 seed CSV、aggregate JSON 和中文 Markdown。strict `id_switch_count`、
commitment coverage 与 partial diagnostics 始终分栏；未提交空档降低 coverage，但 D6 不把它
当作 `IDSW=0`，也不回算或覆盖 D2 已发布的 strict 值。`runtime_plan_outcome_join.py` 同时接受
evaluation v2：assignment window 命中 `status=uncommitted` 时，仅该 binding 的
`identity_mapping` 变为 unavailable，并保留 frame timestamp、reason、track 和 policy
details；truth/state/距离诊断不回填，其他合法 binding 和 episode 继续评估。普通缺失仍保持
原 fail-closed unavailable，SHA 或 audit 篡改仍拒绝整个输入。

2026-07-23 D6 全量回归为 `598 passed, 1 warning in 21.44s`，验收门限为零失败；warning
是既有 Matplotlib `Axes3D` 环境提示。该结果证明 D6-owned consumer、报告和 runtime join
合同已实现并测试。

同日 main 在 clean commit `909669b2eefeab2ce30c8ac389d6bf9c0a8cbabc` 上完成 seed 1100、
nominal 200 对 200、2 个侦察节点、2.2 秒的 baseline/candidate A/B。两组均实际持久化
`d2.scalable3d_identity_evaluation.v2` 和
`d2.scalable3d_identity_commitment_audit.v2`，在线真值使用为 0。baseline strict
`IDSW=9`、track continuity `0.865`、coverage continuity `0.870`，commitment coverage
为 `1.0`。candidate commitment coverage 为 `1714/1787=0.9591494124`，其中 69 条
`identity_uncommitted_ambiguity_hold`、4 条 `identity_uncommitted_after_hold`；未提交
source/candidate binding violation 均为 0，在线真值隔离通过。

candidate 的 `GT3D-000185`、`GT3D-000186`、`GT3D-000202` 在评分帧
`2.1308153039 s` 使用 `measurement_timestamp=1.2 s` 的恢复证据，时间差
`0.9308153039 s` 超过固定 `0.9 s` lineage window。D6 因此按合同将 strict IDSW、
continuity 和 coverage 标为 unavailable，原因是
`source_observation_outside_lineage_window`，没有扩大窗口或回填 strict IDSW。D2/D3 数量
由 baseline 的 `203/200` 降至 candidate 的 `201/197`。本次只证明 v2 显式未承诺覆盖、
独立审计和安全绑定在真实 producer episode 中可工作；结构歧义候选未通过准入，seed
1101/1102 未继续执行。该 episode 属于 clean 三维质点验证，不是 AirSim 实验。

## 发布新鲜度 A/B 与部分身份计数修正（2026-07-23）

main 在 clean commit `65568579c99e4ef9939f0519f66c46d3076ef035` 上重新执行 seed 1100
A/B。场景仍为 nominal 200 对 200、2 个侦察节点、2.2 秒三维质点 episode。baseline 和
candidate 的 root manifest 均为 clean，episode ID 在 summary、identity evaluation、
identity manifest、D6 episode record 和 D6 manifest 之间一致；identity evaluation 与
identity manifest 的 SHA-256 绑定、D6 manifest 对两者的来源摘要均通过独立复算。两组
`online_truth_use_count=0`。

发布新鲜度候选已关闭上一轮 strict-unavailable 阻断。D6 从 D2 evaluation 原样消费到：

- baseline：strict IDSW `9`、track continuity `0.865`、coverage continuity `0.870`、
  duplicate assignment `0`、D2/D3 数量 `203/200`；
- candidate：strict IDSW `3`、track continuity `0.8266667`、coverage continuity
  `0.8283333`、duplicate assignment `0`、D2/D3 数量 `201/197`；
- candidate 的 1787 条 commitment records 包含 1711 条 committed、69 条 active hold 和
  7 条 after hold，all-record coverage 为 `0.9574706212`；
- 3 条 after-hold 恢复以
  `identity_recovery_blocked_source_observation_outside_recovery_publication_freshness_window`
  失败关闭，source/candidate binding violation 为 `0/0`。

本轮同时修复了一个 D6-owned partial consumer 回归。D2 audit 将 mapping 分为
`available/ambiguous/unavailable/excluded/uncommitted`，partial v1 则把后三类合并为
`unavailable_mapping_count`。旧 D6 错误地把 audit 的单独 `unavailable` 与 partial 合并值
直接比较，导致 baseline 的 `230+4+0=234` 和 candidate 的 `218+2+76=296` 被误报为
`partial_identity_audit_binding_mismatch`。现在按分类和校验：

```text
partial unavailable
  = audit unavailable + audit excluded + audit uncommitted
```

并继续要求全部分类覆盖 `total_mapping_count`。修复后直接重读原始 producer 制品，baseline
和 candidate 的 partial provenance 均通过，IDSW lower bound 分别为 `9` 和 `3`。lower bound
仍不回填 strict，也不参与控制。原 A/B 目录内既有
`d6_truth_isolated/episode_record.json` 是修复前输出，其 partial mismatch 仅记录旧 consumer
状态；main 集成本修复后应从未改动的 producer 制品生成新的 D6 派生 bundle，不覆盖原始 A/B
证据目录。

当前制品没有持久化 `identity_commitment_recovery_config` 完整快照。D6 可以验证 v2
commitment/audit schema、新阻断原因和实际 fail-closed 计数，但不能仅凭该制品独立证明运行时
使用了 `d2.identity-commitment-recovery-config.v2`、门控开启状态和 `0.9 s` 预算。这是
main/D2 producer 到 D6 provenance 的跨模块 P1，不影响本轮 strict 数值和零绑定违规结论。

候选保持默认关闭。strict availability 门已通过，算法准入仍失败：D2 航迹少 2 条、D3 分配少
3 条，track continuity 下降 `0.0383333`，coverage continuity 下降 `0.0416667`。按冻结的
非退化门槛停止 seeds 1101/1102。新增两项分类守恒回归后，D6 全量为
`600 passed, 1 warning in 21.55s`；warning 是既有 Matplotlib `Axes3D` 环境提示。

## 身份恢复配置谱系 v2（2026-07-23）

D6 已实现 `scalable3d-offline-identity-evaluation-manifest-v2` 的独立消费。新增
`D2IdentityRecoveryConfigProvenanceRecord`，只在以下条件全部成立时标记配置谱系可用：

1. manifest 声明非空 `d2.identity-commitment-recovery-config.v2` 配置，并给出规范 JSON
   SHA-256；
2. `identity_commitment_recovery_config_record_count` 与 `d2_record_count` 相等；
3. consistency 标志为真，source 严格等于
   `payload.association.identity_commitment.recovery_config`；
4. D2 在线 JSONL 的文件 SHA 同时匹配调用方期望值、identity evaluation 和 manifest；
5. JSONL 每条 `modules.d2.associated_tracks` 记录携带完全相同的配置，实际行数与清单计数
   相等。

`adapt_d2_scalable_3d_identity()` 和 `build_truth_isolated_episode_record()` 新增可选参数
`d2_online_d2_records` 与 `d2_expected_online_d2_records_sha256`。文件未显式传入时，可从
identity evaluation 或 manifest 同目录发现 `online_d2_records.jsonl`。episode JSON、
逐 seed CSV、batch provenance 和运行时计划结果均暴露配置快照、配置 SHA、manifest
schema/SHA、在线记录 SHA、记录数、验证状态和失败原因。

历史 manifest v1 路径保持兼容。strict IDSW、continuity 和 partial lower bound 继续按原合同
计算；新增谱系单独显示
`identity_recovery_config_not_manifest_bound_v1`。运行时计划结果接受 v1/v2；v2 的配置
篡改、缺字段、错误摘要、帧间漂移或计数不符均拒绝整个联接。该验证不读取 truth ID，不回填
strict IDSW。

2026-07-23 完成专项与全量回归：身份离线/运行时专项 `83 passed`，D6 全量
`611 passed, 1 warning in 21.55s`，验收门限为零失败。warning 仍是既有 Matplotlib
`Axes3D` 环境提示。真实 main 三维质点 3 对 3、seed 70、1.2 秒接线用例也通过，manifest v2
绑定 3 条 D2 发布。本轮没有重跑 seed 1100 最终 A/B，也没有启动 AirSim。旧 A/B 制品仍缺
v2 配置快照；该实现阶段的待办已由下一节最终 A/B 复核关闭。

## 身份恢复配置谱系最终 A/B 证据（2026-07-23）

main 在 detached clean commit `ff881316243ff5a2991a4659ab78637ed625d123` 上重跑同一
seed 1100 baseline/candidate。两组均为 nominal 200 对 200、2 个侦察节点、2.2 秒三维质点
episode，场景配置 SHA-256 为
`34f5563579d9d2e7d1ea2b57cf353d2465b3bd16c5310570d40e72fc7aeac461`。baseline/candidate
runtime profile SHA-256 分别为
`5cd76663352d169a96e5a8b9ef6843c51bbff1dc89fe2f9673f2365d133d3c53` 和
`f23a1fe91f87e23b4644d8909683d4fd61c6785ca1242396e6b521eef782cf85`。

两组 identity manifest 均为
`scalable3d-offline-identity-evaluation-manifest-v2`。D6 episode adapter 和 runtime
outcome join 均独立验证：

- recovery config schema 为 `d2.identity-commitment-recovery-config.v2`；
- 规范配置 SHA-256 为
  `sha256:bd8e362ec4ca128ed902826750b26d862286770d3c0c4d0b75960a50911a201a`；
- 配置记录数、`d2_record_count` 和在线 D2 JSONL 实际记录数均为 9；
- consistency/source 声明、manifest SHA、在线文件 SHA 和逐条配置均通过，
  episode/runtime provenance 均为 `verified=true`。

最终 baseline/candidate 的 D1 航迹为 `202/202`，D2 航迹为 `203/201`，D3 分配为
`200/197`，runtime binding windows 为 `593/587`。strict IDSW 为 `9/3`，track continuity
为 `0.865/0.8266667`，coverage continuity 为 `0.870/0.8283333`，duplicate assignment
为 `0/0`。partial IDSW lower bound 为 `9/3`，partial unavailable mappings 为
`234/296`，并保持 `strict_id_switch_count_backfilled=false`。

candidate 有 1711 条 committed、69 条 ambiguity hold 和 7 条 after hold，all-record
commitment coverage 为 `0.9574706212`。其中 3 条 stale recovery 被
`source_observation_outside_recovery_publication_freshness_window` 阻断；两类 binding
violation 仍为 `0/0`。两组在线真值使用均为 0。

配置谱系 P1 至此完成生产端到 D6 episode/runtime 两条链的端到端闭合。结构歧义保活候选仍因
D2/D3 可用性和两类 continuity 退化而拒绝，保持默认关闭。按冻结门限不运行 seeds
1101/1102、10 秒或 20-seed 矩阵。本次证据不是 AirSim。

## 身份承诺执行门 clean 单种子审计（2026-07-23）

D6 已只读审计 clean commit `7e15dac9cdaf6743999dfe045a70676fd31a17d6` 的
`hold_only` 与 `hold_plus_centroid` 制品。两组均为 nominal 200 对 200、2 个侦察节点、
2.2 秒、seed 1100，场景配置和离线真值相同，runtime profile 只差
`d1_identity_neutral_centroid_correction_enabled`。

两臂 strict IDSW、track continuity、coverage continuity 均为
`3/0.8266666667/0.8283333333`。available/unavailable/uncommitted mapping 为
`1491/218/76`，另有 2 条 excluded；commitment coverage 为 `0.9574706212`。重复分配、
在线真值使用、未承诺来源/候选绑定违规均为 0。

`t=1.0 s` 时 D3 从计划版本 1 强制升为版本 2，绕过迟滞并拒绝 11 个未承诺旧绑定。版本 2
和版本 3 中这些目标的分配为 0；D5 主动视觉/终端绑定、D7 导引和 runtime control 的后续
继续执行也均为 0。D6 使用当前代码重新构造 truth-isolated episode 和 runtime outcome，
派生 JSON、CSV 与 Markdown 均与原制品逐字节一致。

候选组产生 46 个质心候选，30 个因 `oosm_scan`、16 个因 `unbalanced_component` 被拒绝，
实际应用数为 0。该结果是 clean 单 seed 安全合同证据，不是有效 treatment、算法收益、
多 seed 或正式晋级证据。完整审计见
[`docs/IDENTITY_GATE_CLEAN_SEED_1100_AUDIT_CN.md`](docs/IDENTITY_GATE_CLEAN_SEED_1100_AUDIT_CN.md)。

## 正式 R0 后验跳过审计（2026-07-25）

D6 审核了 clean 提交 `2c7b425d...` 的 900 个 R0 episode。执行范围为 900/900，
其中 895 个为 `clean_formal_experiment_matrix`，5 个 delayed-noisy 小规模 episode 为
`descriptive_or_incomplete_evidence`。5 项均声明一次 finalization no-op skip，但最终 D1
后验相对 D2 最后消费后验的状态、协方差和有效时刻已经变化。

离线评估升级为 `d6-scalable3d-offline-evaluation-v10`。D6 会核对尾部新证据、结构歧义和
逐轨完整公开后验；这些字段仍不足以证明完整 D2 输入等价。上游发布版本化完整输入摘要前，
declared skip 不进入 formal 守恒。当前 5 项继续失败关闭，不能用
`consumption + merge + declared skip == d1` 晋级。详细清单、差值和正式重跑边界见
[`docs/FORMAL_R0_POSTERIOR_SKIP_AUDIT_CN.md`](docs/FORMAL_R0_POSTERIOR_SKIP_AUDIT_CN.md)。
D6 v10 已提交为 `8e955f3d920df36818ff1961aae5484192995dba`。

### 运行时修复定向复核

本小节及其后的 177/900 增量小节保留全量执行完成前的阶段证据。当前结论见本文件末尾
“正式 R0 全量后验独立审计”。

main 修复 finalization 后，在 dirty 工作树中按原配置重跑上述 5 个异常 cell。D6 v10
读取 `/tmp/msm-r0-finalize-fix-20260725/combined_d6` 后确认，五项均满足：

- D1 最终代次等于 D2 最终消费代次；
- D2 消费次数等于 D2 发布次数；
- `consumption + pre_tick_merge == d1_generation`；
- `d2_finalize_unchanged_posterior_skip_count=0`；
- pending 为空，generation contract 状态为 `verified`。

该结果证明运行时修复在五项定向开发回归中生效。五个 episode 的
`repository_dirty=true`，因此 D6 将其全部保留为
`descriptive_or_incomplete_evidence`，正式验收资格为 0/5。它们不能与旧 clean 提交的
895 个正式 episode 拼接成 900/900 正式结果。runtime 修复已形成 clean source commit
`98d01bfa2daa0bbd279dfbde27f0dfa669150bf6`。完整 R0 formal rerun 已在其后继 clean source
`1e5ed8ddcf27f375e922a447decfbd875d21bfdf` 上启动；在该阶段尚未完成，D6 当时仍保留旧
正式结论 895/900。D6 对 declared skip 的失败关闭规则没有变化：没有版本化完整 D2 输入摘要时，
`skip=1` 仍不能进入正式守恒式。

### R0 正式增量复核（全量完成前阶段记录，2026-07-30）

新执行计划 SHA-256 为
`8804ecb4dd0513db55906905f031832711012974fc911546df40e09fb297d373`。shard 0、5、9
各完成 45 个 cell；shard 8、18 各完成 21 个 cell，当时执行进度为 177/900。

D6 新专项不读取 `targeted_formal_d6` 聚合，直接从 execution plan、shard ledger、
cell result、episode artifact tree、在线总线和 summary 重算五个原失败 cell。5v5
seed 1000、1005、1008、1018 和 20v20 seed 1009 均为
`clean_formal_experiment_matrix`，基础与矩阵 formal eligibility 均为 true，generation
contract 为 `verified`，三类 failure reason 均为空，skip 为 0，pending 为空。

该结果关闭五个目标 cell 在新批次中的后验代次疑点，不代表 177 个已执行 cell 已全部由
D6 完成正式准入，也不改变旧批次 895/900 的整体结论。其余 172 个已执行 cell 未由本专项
逐项审计，该阶段仍有 723 个 cell 未执行。完整结果和哈希见
`docs/FORMAL_R0_TARGETED_POSTERIOR_AUDIT_1E5ED8D_CN.md`。

专项测试为 `9 passed, 1 warning in 2.37s`，D6 全量回归为
`1243 passed, 1 warning in 150.38s`。warning 为既有 Matplotlib `Axes3D` 环境提示；
本专项不生成三维图。

## 学习作用域正式证据审计（2026-07-26）

D6 新增可选、只读的学习作用域审计器。它消费 main 持久化的 execution plan、作用域 merge
目录和显式 R0 对照，不导入控制器，也不改变默认规则路径。公开入口为
`audit_learning_scope_formal_evidence()`；命令行入口为
`scripts/run_learning_scope_formal_audit.py`。

审计逐层验证模型 bundle 绑定、预检设备、执行计划和父计划摘要、分片计划/进度/checkpoint、
逐 cell 结果、episode 制品树、来源提交、在线真值使用、版本与运行诊断。学习变体还必须提供
逐 episode 的实际 assist 采用证据。D5 图模型还要求候选边计数可用且大于 0，避免把零边空
调用记为采用。shadow、fallback 和仅加载 bundle 均不计采用。

同 `comparison_key` 的 R0 必须唯一、来源一致且物理指标可用。当前两个必选非退化指标为
`intercepted_target_count` 和 `offline_proximity_unique_target_count`。缺 R0、缺实际采用、
缺物理结果或 scope 不完整时，输出保持 `unavailable`，总判定为 `fail_closed`，不补零。
审计通过也不授予模型晋级。

输入由 main 显式提供：

```text
learned execution plan + learned scope merge directory
zero or more R0 execution plan + scope merge directory pairs
actual model bundle directories
optional expected preflight device
```

输出包括审计 JSON、逐 cell CSV、中文 Markdown 和 `SHA256SUMS`。主审负例补充后，定向测试
为 `36 passed, 1 warning in 2.35s`，其中新增 29 项；D6 全量回归为
`930 passed, 1 warning in 78.98s`。新增覆盖计划/摘要、merge/checkpoint/progress/episode
tree 篡改，重复或错配 R0，D3/D4/D5 主动视觉空采用，C1/F1 缺必要组件，以及 D5 零候选边。
warning 为既有 Matplotlib `Axes3D` 导入提示。正式 d59352b 学习作用域及其 R0 制品尚未在
本任务中提供，因此当前只有审计能力证据，没有模型非退化或晋级结论。

## D4 区域规划链审计（2026-07-29）

D6 新增独立只读接口 `audit_regional_planning_chain()`。接口消费 episode 在线消息或同结构
记录，连接以下四段证据：

```text
D3 source plan
  -> D4 advisory-v2
  -> main consumption
  -> D3 strict successor
```

绑定集合沿用运行时结果连接器的严格口径：资源只能出现在一个绑定中，同一
`global_track_id` 可以由多个资源合法引用。后继计划必须具有新计划编号、递增版本，并由
metadata 同时指向源计划、建议编号和自身后继编号。规划专用消费允许
`consumable=true` 和 `planning_replan_eligible=true`，五类执行权限必须全部为 false。

审计结果分别给出合同链、真实绑定干预、独立同键 R0、非退化和模型收益的 availability。
绑定或目标覆盖发生变化才算真实干预。source/successor 的分配数和未分配数只形成描述性
非退化；它不替代独立同键 R0。规则建议器即使形成正例也不会被记为学习模型收益。

main 的 20 对 20、8 区域、seed 29、3.2 秒只读探针得到 source v1
`17 assignments / 3 unassigned`，D4 建议从 `region-000` 向 `region-001` 转移 1 个资源，
successor v2 为 `18 assignments / 2 unassigned`。合同链、规划权限封闭和真实绑定变化均
通过，在线真值使用为 0。独立同键 R0 未提供，建议来源为 rule，因此模型收益保持
unavailable。

同一 seed 的 2.2 秒故障探针在 `t=2.0 s` 注入中心故障。最新建议无 transfer、无 consumption
和无后继，显式 `fault_fence_active/formal_d4_execution_fenced` 拒绝码通过安全审计。该结果
计为故障代际围栏通过，不计模型性能失败。

离线评估 schema 升级为 `d6-scalable3d-offline-evaluation-v11`，逐 episode CSV、聚合输入和
中文报告均携带上述分层字段。专项测试 `6 passed`；D6 全量回归
`1202 passed, 1 warning in 106.92s`。warning 为既有 Matplotlib `Axes3D` 环境提示。本轮
没有启动 AirSim，也没有形成多 seed、同键 R0 或学习模型收益证据。

## 正式 R0 全量后验独立审计（2026-07-30）

D6 已完成 clean source
`1e5ed8ddcf27f375e922a447decfbd875d21bfdf` 的完整 R0 单臂审计。执行计划逻辑
SHA-256 为
`8804ecb4dd0513db55906905f031832711012974fc911546df40e09fb297d373`。
审计不读取 `merged_scope/d6_evaluation`、旧 `targeted_formal_d6` 或 episode 内
producer 生成的 `observation_governance_audit.json`。merged manifest、episode index
和 CSV 只作为待复核索引。

全量入口 `formal_r0_full_posterior_audit.py` 从冻结执行计划生成 900 个规范 cell，复用五项
定向审计的逐 episode 低层 evaluator。它独立核对 20 个 shard 的 plan、checkpoint、
progress、900 个 cell result 和每个 episode artifact tree，再从
`online_observations.jsonl` 与 `summary.json` 重算 D1/D2 后验代次。

本次结果如下：

- 执行范围、规范 cell、merged index 和 artifact tree：`900/900`；
- 20 个分片哈希：`20/20`；
- clean formal、实验矩阵资格、generation integrity：均为 `900/900`；
- D1 最终代次与完整发布合计均为 `28777`，D2 最终消费代次合计为 `28777`；
- D2 消费与发布均为 `6411`，节拍前合并为 `22366`，满足
  `6411 + 22366 = 28777`；
- finalization skip 总量为 0，pending 排空 `900/900`；
- 在线真值使用与禁用真值字段违规总量均为 0。

严格总门为 `872/900`。28 个失败项全部位于 `high_threat_m_to_n` 场景，episode 结束时
D4 仍为 `collecting_member_acks`，低层 evaluator 因此保留
`d4_fail_closed:collecting_member_acks`。这些项的 clean formal、实验矩阵资格和 D1/D2
generation 仍通过，但不能计为完整系统 episode 通过。D6 未改写 evaluator 或源制品。

身份交换计数在 900 项中均由 producer 显式声明不可用，聚合总量保持 `null`。D4 建议和
D5 主动视觉四个安全计数在 700 项可用且均为 0，另 200 项因对应 runtime 未发布而保持
不可用，未补零。

完整报告见
[`docs/FORMAL_R0_FULL_POSTERIOR_AUDIT_CN.md`](docs/FORMAL_R0_FULL_POSTERIOR_AUDIT_CN.md)。
输出目录包含完整 JSON、逐 cell CSV、中文报告和 `SHA256SUMS`；tracked docs 只保留中文
报告和紧凑 JSON。专项与五项兼容测试为 `19 passed, 1 warning in 2.31s`，D6 全量为
`1253 passed, 1 warning in 132.38s`。

该结果只关闭 R0 单臂的执行和 D1/D2 后验完整性。完整父矩阵仍为 `900/5700`，没有
G1、A1、A2、A3 同范围对照，不能声明学习收益或因果改进。
