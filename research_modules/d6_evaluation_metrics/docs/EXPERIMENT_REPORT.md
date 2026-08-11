# D6 正式实验矩阵准入预检报告

## D5长距离视觉配准离线复核（2026-08-10）

本次没有启动 AirSim。D6 只读消费 main 已冻结的原始尺度单 seed episode。场景包含 20 个以
50 m/s 运动的目标、中心相机和拦截相机，逻辑时长 20 s，seed 为 `20260810`。输入为 v2
`metrics.json`、`mot_continuity.json` 和 `associations.csv`；该 episode 没有 v3 时序绑定和
掉检事件文件。

离线结果为可评分关联 `1934` 条，其中正确 `1930`、错误 `4`，准确率
`0.9979317476732161`。连续可见身份切换为 `0`，实测短缺口为 `3`，长期重发现为 `48`，几何
绑定切换为 `7`。实际交叉窗口总数 `31`，可评分 `3`，比例 `0.096774`；交叉窗口内身份切换为
`0`，已有可评分窗口的纯度和连续性均为 `1.0`。重复分配、在线真值使用和全局航迹编号改写均为
`0`。

结构门失败。v2 没有有界保持事件，3 个实测短缺口均按有效中断处理；绑定振荡缺时序证据，标为
不可用。实际交叉门也失败，其阈值为可评分窗口至少 10 个、比例不低于 0.30，当前只有 `3/31`。
较高平均准确率不能替代短缺口和交叉窗口证据。

软件验证覆盖冻结 v2、online replay 与离线真值 sidecar、真实 main v3 行结构、字段缺失、无
表头空 CSV、只有几何预检以及门控通过/失败。专项结果为 `7 passed, 1 warning`，D6 全量为
`1425 passed, 16 skipped, 1 warning in 129.29s`。v3 通过门仅属于合成接口测试，不是新的 AirSim
实验。当前结果不关闭 P1，也不形成在线关联、任务分配或控制许可。下一步需要 main 写出真实
v3 事件并运行至少 10 个原始尺度 seeds。

## D3/D4/D5 授权来源载荷审计（2026-08-03）

真实审计使用冻结 input contract、metadata preflight 和 main audit-only authorization。输入合同、
预检和授权 SHA-256 分别为 `341afff736127b8624c0c730f56c6a0cea90bb2505988ae0e6b9cd78aca60092`、
`2c051c5d653a56a33a4036464c7c76784b60615b4f90a768962614a04b31205f` 和
`ec6ab29d0db30a03ad72594f008d1e9e88348d3e2d64eb9dbf046510d3a10f0f`。D6 只按绑定 inventory
读取文件，没有执行训练、推理、阈值调整、任务分配、降级、相机或控制流程。

- D3：300 episode、3086 frame，打开 308 个文件，读取 1375907650 字节。
- D4：324 episode、921 frame，打开 654 个文件，读取 30988677 字节。
- D5：104 episode、280968 sample，打开 319 个文件，读取 355512715 字节。train、validation、
  future-held-out 为 `48/24/32` episode 和 `126138/66782/88048` sample。

三模块 hash、path、schema、count、timestamp、finite numeric、truth leakage 和 split leakage 门
全部通过；truth leakage 与 split leakage 均为 0。D5 future-held-out 只用于哈希、结构、计数和
隔离核验，`future_held_out_model_consumption_performed=false`。D5 descriptor 自哈希采用 producer
的 ASCII 转义与行尾换行规范后，v3 不再出现合同建模误报。

结果目录为 `/home/linux/Documents/MSM-source-audit-result-20260803-v3`。`source_audit.json`、
`SOURCE_AUDIT_REPORT_CN.md`、`SHA256SUMS` 的 SHA-256 分别为
`8fa4f39c4c63a30362a421cd1cd7904554873ebaccfc1fdb0040a31416043bc7`、
`642e6500a827d7fe0fc6e786dd525388145d92433be9732b07c12610b64e12e6`、
`8ed97b186603c0e8977d03e32107a412a3748c1286eb9e16fb1867822a7feb25`。状态为
`source_integrity_audit_passed_not_training_authorized`，阻断项为空，全部非审计权限为 false。

warning 记录实际 producer 合同边界：D3 不含显式六维状态/协方差，D4 不含协方差，D5 使用
opaque feature fingerprint 而非显式 bbox/local-track geometry。它们不影响本次按现有 schema 的
完整性结论，也不能被解释为这些字段已经可用。专项测试为 `37 passed, 1 warning in 2.67s`，
D6 全量为 `1418 passed, 16 skipped, 1 warning in 126.18s`。

## 真实 AirSim 末端受控扰动（2026-08-01）

本次只读评估覆盖 seed `1`、`ClockSpeed=0.2` 的两个真实 AirSim SimpleFlight 2 对 2 case。
目标为 actor，检测为 AirSim detect。面积突跳和边框裁切各注入 1 次并各取得 1 条合规证据；
有效视觉控制均被阻断，实际执行保持 `radar_pn`，预期和分配的全局航迹一致。每例资源对和
目标物理结果均为 `2/2`，在线 truth identity/state 使用为 0。

D6 actual-execution 输入可用性为 `2/2`。四类控制层样本分母合计 82，合同/控制/末端切换许可/
模式切换计数为 `41/22/22/4`；物理正式计数为 4 且无统一控制样本分母。control tick 两例均值
为 `1074.4/1044.4 ms`，49 条全部超 100 ms；main bus 均值为 `46.0/42.4 ms`，仅 1/49 超预算。
本批未覆盖 dropout、多 seed 和完整输入矩阵，full-suite false 不代表两个受控 case 失败。

main bus 诊断的 `terminal_id_switch_count=2` 在两例中均由两个独立资源/相机流各自的一次本地
号变化形成，本批不存在跨流合法本地号误计。计数器只按全局航迹分组，对多资源共拦和多相机
场景仍有 P1 语义风险。最终合并指标保持 unavailable，未将诊断值用于正式验收。

## D5 A3 v2 BC model 独立审计（2026-08-01）

D6 对开发三维质点候选执行低层独立审计，没有调用 D5 evaluator、corpus gate、precheck 或
模型类。输入绑定 frozen config、generation plan/summary/registry、feature cache、bundle、
weights 和 tracked D5 文件。33 个 cache 文件、7 个 tracked source 文件、bundle
`SHA256SUMS`、weights、tracked summary/report 摘要通过；单配置、test 未用于训练/选择和
全部 authority false 的声明一致。只检查开发 seed `22100-22199` 与保留 `1000-1019` 的数值
交集为 0，未读取或运行保留 episode 或 R0 shard 10-19。

按 state_dict 形状重建 35-64-64-1 tanh actor 后，对 40133 个 test 样本、276437 个候选逐样本
生成 prediction、confidence 和 OOD。exact action accuracy 为 `0.9599581391872025`；
observe_target/search_sector/hold/reacquire recall 为
`0/0/0.9850199203187251/0.9970064361622512`；macro recall
`0.49550658912024403`；interceptor/recon exact accuracy
`0.9723771235896771/0.6565272496831432`；ECE `0.3682385335452162`；feature-boundary OOD
fraction `0`。核心指标与 D5 声明匹配，ECE 绝对差为 `2.47e-10`。

验收阈值为每 intent recall 至少 0.25、macro recall 至少 0.5、ECE 至多 0.25、OOD 至多 0.1、
interceptor/recon accuracy 至少 0.5。候选因两个少数动作零召回、macro recall 和 ECE 失败，
状态为 `completed_fail_closed_quality_gate`。总体准确率不能覆盖少数类失败；所有 authority false，
`paired_shadow_allowed=false`。机器证据、中文报告和校验和位于
`reports/D5_A3_V2_BC_MODEL_INDEPENDENT_AUDIT_20260801/`；专项测试
`18 passed, 1 warning in 2.85s`，D6 全量 `1384 passed, 1 warning in 135.21s`。warning
为既有 Matplotlib `Axes3D` 环境提示。

重生成证据中的全部 input 均为 repo-relative POSIX 路径，`repo_root="."`，不含本地主目录。
auditor/integrity 记录 schema、实现版本及当前审计器 Python 源码 SHA-256；未写入未经核验的
clean Git 声明。专项测试同时重验报告目录 `SHA256SUMS`。

该结果只证明开发 cache 和模型字节可独立复现，不形成正式 R0、AirSim、真实相机、applied
action outcome、物理配对非退化、assist、运行或控制准入证据。规则回退继续生效。

## D5 A3 v2 候选语料独立审计（2026-08-01）

本次对象为 main 最终封装的 A3 v2 三维质点主动视觉候选语料。D6 只读输入数据集根目录，
没有调用 D5 validator、corpus gate 或高层 loader，也没有读取、运行或修改保留 seed 的正式
制品。生产提交为 `d7bf89060e88a5b1324f2d8d1de36b005ebe5e4d`，100 个 episode 均为
clean source，来源域为 `scalable_3d_point_mass_runtime`，证据等级为
`simulation_research`。

审计实际解析 100 个 descriptor、100 个 gzip 在线流和 100 个离线文件。样本与离线标签均为
159502，在线记录为 321215，其中 snapshot 2011、camera-feedback 159502。302 个
`SHA256SUMS` 登记工件与实际集合一致；连同摘要清单共 303 个文件在审计期保持只读和元数据
不变。100 个 header、100 个 footer 样本索引摘要和 100 个离线 episode 绑定全部通过。

seed 为 `22100-22199`。train/validation/test 的 episode 与 seed 均为 60/20/20，三组互斥；
与保留范围 `1000-1019` 的交集为 0。在线 truth、actor、object 标识计数分别为 0、0、0。
拆分 SHA-256 为
`fb4f6c0ce6566e05113c052af52f45b1ecfbdb3d77727b6c038010777477da7b`，训练集 SHA-256 为
`3cc6ea166adc74e8cf89e9a5a6b44952b9e4f51d08c83678db39b7b9d1761776`。

来源层 16 项和候选锚点层 13 项共 29/29 通过，状态为
`simulation_research_integrity_confirmed`。manifest SHA-256 为
`9b80e47aed8f4c7a416694220d63d9156010911951cbbf271905ce5c0d6f31d4`，摘要清单文件
SHA-256 为 `38ea7d89d57f6b56bdceb70efd534872b37250ef59aceafb11ff3e55401fd216`。
机器证据、中文报告和报告校验和位于
`reports/D5_A3_SOURCE_INDEPENDENT_POINT_MASS_V2_AUDIT_20260801/`。

main 提供的 generation plan SHA-256 作为外部冻结锚点登记。计划文件不在受审目录，D6 未
从数据集重算计划内容。该限制不影响 manifest、descriptor、online/offline 和 split 的低层
完整性结论，但 plan-content 独立证明仍需另行提供计划文件。

专项测试 `18 passed, 1 warning in 2.32s`，D6 全量
`1366 passed, 1 warning in 135.82s`。告警来自既有 Matplotlib `Axes3D` 导入环境。报告不
评价 D5 动作角色覆盖、训练门或模型效果；行为克隆、近端策略优化、assist、assignment、
degradation、runtime、production、control 和 `global_track_id` 写权限全部为 false。

## D5 A3 三维质点数据集来源审计（2026-07-31）

本次验证对象是 main exporter 已完成最终封装的 D5 A3 独立来源三维质点数据集。生产提交为
`4a8c1173179b4058d4aee38178e0fb40ecd222b3`。D6 直接读取数据集根目录并运行自身低层来源
审计器，没有调用 D5 的来源、数据集或语料高层 validator，也没有启动控制流程或读取正式
R0 seed。

数据集覆盖 seed `21000-21099`、45 个场景-规模单元、100 个 episode 和 159487 个样本。
302 个摘要清单工件全部闭合；clean/dirty episode 为 100/0；train/validation/test episode
与 seed 均为 60/20/20 且互斥；在线 truth/actor/object 标识计数为 0/0/0。12/12 检查通过，
状态为 `simulation_research_integrity_confirmed`，阻断码为空。

manifest SHA-256 为
`bccbdad42a71b130720469bb4e99dd1dd99e29a9b33af036679b9d64b0fe35a4`，`SHA256SUMS`
SHA-256 为 `19f41d1941134dcd11d3019bbc0e2cef7224860c80545ba4f37f348b499201be`。
紧凑机器证据和中文报告保存在
`reports/D5_A3_SOURCE_INDEPENDENT_POINT_MASS_AUDIT_20260731/`。

验收口径要求 12/12 检查通过、阻断码为空且全部 authority 为 false，本批次满足该口径。
专项测试为 `12 passed, 1 warning in 2.68s`，D6 全量回归为
`1360 passed, 1 warning in 176.00s`。唯一 warning 是既有 Matplotlib `Axes3D` 导入环境
提示，与来源审计无关。

该结果确认质点仿真来源完整性。D6 后续接收的 D5 corpus gate 公共结果显示：严格数据集
检查有效，研究来源门通过，训练结构门按 13 项原因失败关闭；训练集 `hold=0`，
`search_sector + recon=0`。ACK 接受和匿名观测键覆盖均为 159487/159487，物理匿名观测帧
与离线 outcome 不可用。D6 只绑定并交叉核对 D5 报告和 JSON，没有重新计算训练门。

该接收结果不修改本节原来源审计证据。AirSim 和真实相机外部证明、模型准入、assist、
assignment、degradation、runtime、production、control 和 `global_track_id` 写权限均为
false，不能从来源完整性或 ACK 完整性推断模型可训练性、策略收益或物理效果。

## 学习作用域归档审计开发验证（2026-07-31）

本次验证对象为 `learning_scope_formal_audit` 的归档原生入口。第一类夹具由 D6 独立构造，
用于覆盖六种学习变体和篡改负例。第二类耐久夹具只在测试代码中导入
`scalable_3d_simulation`，调用真实计划写入/加载、分片运行、正式归档创建和归档 merge API。
该夹具保留满足 producer 正式约束的父矩阵声明，在测试中把 cell 枚举和执行缩为一对同键
G1/R0。它验证 producer 与 D6 的持久化合同，不是正式学习实验。

正例覆盖 G1、A1、A2、A3、C1、F1 六种学习变体及各自显式 R0。归档 learned 与归档 R0
通过，归档 learned 与目录 R0 混合通过，普通 sidecar 被接受。每个通过 scope 的
`verified_archive_count=1`、`peak_staged_shard_count=1`，源删除和归档删除均为 false。
目录 R0 明确报告未执行归档验证、计数 0 和峰值 0。

失败关闭测试覆盖：缺 archive、额外目录、archive root symlink、payload 篡改、execution
plan 绑定错配、merge plan/cell 摘要篡改、重复 cell 和缺失 cell。CLI 帮助文本包含 learned
和 R0 archive 参数，同一 learned scope 同时提交目录与归档参数时返回参数错误。原目录模式
的 bundle、采用、物理结果、R0 配对和报告写出回归保持通过。

通用 archive-set 入口另有直接负例，覆盖 `sharding` 非映射、`shard_count` 缺失、布尔值、
零、浮点数、字符串、descriptor 非列表、声明总数与 descriptor 数量不一致、索引错误和
`shard_id` 中索引/总数错误。所有负例均在归档恢复回调前失败关闭。

真实 producer 兼容正例明确使用 `write_d6_report=True`。两个 archive-native merge 均声明
`d6_evaluation_generated=true`，包含 D6 binding；原始 shard 移走后，D6 未打补丁的归档验证
器得到 G1/R0 各 1 个 verified archive、峰值暂存 1、同键配对 1/1 且非退化 1/1。该报告
binding 只用于来源和制品对账，producer 评价结论没有进入 D6 verdict。

实际结果为：

- `test_learning_scope_formal_audit.py`：`68 passed, 1 warning in 8.35s`；
- learning scope、formal shard archive 和 producer 兼容测试合计：
  `89 passed, 1 warning in 9.61s`；
- D6 全量：`1330 passed, 1 warning in 120.34s`；
- 修改 Python 入口 `py_compile`：通过。

warning 为既有 Matplotlib `Axes3D` 环境提示，与本次归档审计无关。本轮没有运行 AirSim，
没有启动正式 shard，没有读取或修改 `/tmp` 正式证据。正式 G1/A1/A2/A3/C1/F1 scope 尚未
生成，因此本节不报告模型效果、非退化结论、模型晋级或控制许可。

## 正式归档审计开发验证（2026-07-31）

开发夹具覆盖 v1 配置归档分派、有效 archive 独立恢复、普通 sidecar、额外目录、归档根
symlink、payload 损坏、执行计划绑定错配、inventory 路径穿越、merge 分片重复/缺失/乱序、
cell_count 错配、core/artifact/父目录 symlink、evaluator provenance 和报告文件篡改。
来源树摘要正例采用 evaluator 实际格式 `sha256:<64位小写十六进制>`；空列表、空字符串、
裸 64 位摘要、错误算法前缀和非十六进制载荷均返回
`archive_d6_binding_evaluator_source_tree_sha256s_invalid`。
full posterior 原目录测试与新增
专项合计 `32 passed, 1 warning`，D6 全量为
`1297 passed, 1 warning in 114.12s`；warning 为既有 Matplotlib `Axes3D` 环境提示。

随后对 clean producer `80e55eb43bc4a5feeac9c9af0d718d461a46401f` 的现有正式归档
执行非破坏预检。执行计划期望 20 片，归档根当前只有 shard 0-9；20 个 pack/verify 结果
sidecar 均作为普通文件接受。D6 只报告缺 shard 10-19，返回 `fail_closed`、verified archive
`0`、低层完成 `0`、父矩阵完成 `0`，没有恢复 shard，也没有创建
`merged_scope_from_archives`。该结果不是正式 900-cell 审计结果。

正式验证仍需 shard 10-19 和 main 生成的 archive-native merge；现有普通 sidecar 不需要
移动。完成后再记录 900 项低层通过数、严格身份可用性、归档报告
绑定和全量 verdict。`learning_scope_formal_audit` archive 模式已在同日后续开发验证中完成，
见本页顶部；该结果不替代正式 900-cell R0 审计。

## 预评估行接口验证（2026-07-31）

验证使用两个不同 seed 的可扩展三维 episode，并附加同一份 D1 描述性性能 JSON。第一组
通过目录入口生成报告，第二组先逐 episode 调用评估函数，再通过预评估行入口生成报告。
两组使用相同标题、bootstrap 重采样次数和随机种子。调用预评估行入口前已删除两个
episode 目录，用于确认最终写包不再读取已释放归档。

两组 aggregate JSON 和模块性能证据 JSON 逐对象相等，逐 episode CSV 与中文 Markdown
文本相等，阶段耗时曲线文件 SHA-256 相等。输出 CSV 保留严格身份 availability、真值隔离、
在线 truth 审计、episode source 和 evaluator source 字段。预评估行调用前后的深层对象
相等，没有发生原地修改。

空行集合在输出目录创建前返回 ValueError。删除严格身份 availability 字段的行返回
`Scalable3DOfflineEvaluationError`，同样没有创建输出目录。聚焦测试为 `3 passed`，
可扩展三维离线文件为 `77 passed`，D6 全量为
`1277 passed, 1 warning in 116.32s`。warning 为既有 Matplotlib `Axes3D` 环境提示。
本轮没有运行 AirSim、正式 900-cell 后验审计或新的控制实验。

## D4 历史候选源漂移复核（2026-07-31）

D6 复核了 2026-07-29 的 D4 v4/v5 候选。两份候选均绑定 clean commit `fd85745`，
其 v4 主实现文件锚点为 `1b534b4...`。D4 在 `20895c7` 增加建议发布代次安全门后，
当前主实现文件摘要为 `1f47de6...`。D4 全量测试已由模块 owner 验证为
`913 passed, 1 warning`，没有证据表明当前 D4 存在回归。

真实 v4 候选面对当前源返回
`source_current_file_differs_from_audited_commit`；真实 v5 候选返回
`v4_source_external_anchor_mismatch`。两项均属于预期失败关闭。历史配置和制品未改动，
当前文件摘要没有写入历史候选锚点。

原重叠诊断负例此前被源锚点提前终止。复核后采用独立受控夹具，实际重叠计数为 0，预期
计数故意设为 1，审计器返回
`validation_overlap_expected_crosscheck_mismatch`。三项专项测试为 `3 passed`，D6
全量为 `1274 passed, 1 warning in 113.95s`。本轮未运行新候选训练、holdout 或运行时
预检，也未形成新的候选准入结果。

当前 D4 候选仍缺新版本候选树、clean 源身份和文件清单、冻结数据及划分、模型与校准
制品、调用方外部锚点、独立 holdout 和运行时预检。上述制品齐备后再建立新的 D6 审计
配置。历史 v4/v5 继续保留，当前准入状态保持关闭。

## 正式 R0 前 450 项严格身份重聚合（2026-07-31）

D6 已修复可扩展三维汇总的身份交换来源。修复前公共字段读取在线 D2 声明，因此正式
R0 前 90 项被错误汇总为 `0/90 available`。修复后在线声明保留在诊断字段，公共字段
读取经哈希和合同复核的真值隔离 episode record。

main 已使用 D6 v12 evaluator `b6289c5`，重聚合 clean producer `80e55eb` 的 shard 0-9。
本批共 450 个 episode，有限状态和严格制品哈希/合同均为 `450/450`。严格身份交换为
`414/450 available`；可用项合计 893，169 个 episode 为非零。36 项失败关闭，其中
27 项为一条全局航迹对应多个真值目标，9 项为源观测超出谱系窗口。在线 producer 指标
仍为 `0/450 available`，450 项均声明
`producer_declared_id_switch_count_unavailable`。

派生结果位于
`/tmp/msm-formal-r0-20260731-80e55eb/d6_strict_partial_450_b6289c5`，包含逐 episode
CSV、聚合 JSON、中文报告、阶段耗时曲线和模块性能证据。该目录是本轮评估输出位置，
不是 900-cell 正式归档。

producer 来源提交和 evaluator 来源提交分别记录。重聚合只生成派生 CSV、JSON、中文
报告和性能证据，没有修改原始 episode 或执行计划。原 90-cell 的严格离线结果
`73/90 available`、17 项失败关闭继续保留为修复前诊断，其中可用部分合计 143、16 项
非零；它不再代表当前汇总范围。原计划中的 135 项待重聚合已由本次 450 项结果覆盖。

当前结果只覆盖正式 R0 的一半范围。full posterior 和 post-run experiment matrix
admission 仍未执行，必须等待 shard 0-19 共 900 个 cell 完整后再生成正式结论。

## 高威胁 clean smoke 修复后复核（2026-07-31）

D6 对 clean commit `b063535` 的 6 个 episode 完成只读准入复核。范围为 5、100、200
三档规模，每档 seed `7/17`。核心制品、配置哈希、有限状态、在线真值隔离、当前计划
标识/版本/时期/租约和联盟闭合均为 `6/6`。权威发布、不同计划身份和计划确认均为 10；
49 个当前联盟目标闭合，16101 条通信处置通过验证。

12 条 D4 建议全部匹配发布时最新代次，发布时旧代为 0。100/200 规模的 4 个重规划
episode 均补齐最终 v2 建议，最终计划建议覆盖为 `6/6`。低层 clean formal 为 `6/6`。
10 条故障诊断建议均为规则 shadow 输出、非 assist，正式决策改写为 0；没有消费记录，
采用指标保持 unavailable。

D4 建议代次的 6-cell 预准入通过。该 smoke 没有冻结 execution plan 和正式矩阵
metadata，不更新正式 R0 结果。完整 ID Switch 仍为 `3/6 available`，100/200 规模
低于实时。完整报告见
`../reports/HIGH_THREAT_CLEAN_SMOKE_B063535_REVALIDATION_20260731_CN.md`；修复前报告
继续保留作对照。

## 高威胁 M 对 N 时期租约复验（2026-07-31）

D6 对 v5 五档规模、每档 20 seeds 的 100 个 episode 进行只读复核。制品完整、配置哈希、
有限状态、在线真值隔离、最终计划标识/版本、时期、租约和当前联盟闭合均为 `100/100`。
151 次权威发布对应 151 个不同身份和 151 次计划确认；同身份重复为 0，48 次评价刷新
没有续租。

通信处置 195838 条，100 个文件均 available/verified。离线身份指标为
`88/100 available`、可用部分合计 52。200 对 200 墙钟均值/P95 为
`14.209/15.566` 秒。51 个重规划 episode 的旧计划区域建议保留为 v5 历史证据；该断点
已在后续 `b063535` clean smoke 中关闭。

时期/租约 availability P1 已在开发证据层关闭。100 个 manifest 均为
`repository_dirty=true`，正式 R0 仍需 clean source 的完整 900 项。完整复验见
`../reports/HIGH_THREAT_PRECHECK_V5_REVALIDATION_20260730_CN.md`。

## 高威胁 M 对 N 开发态 100 项修复复验（2026-07-30）

### 结论

D6 对 v4 五个规模、每规模 20 seeds 的 100 个 episode 逐项重算。最终 D3-D4 计划
标识/版本、当前联盟闭合、有限状态和在线真值零使用均为 `100/100`。v3 三个当前计划
联盟断点已关闭。该批次来自 dirty source，不具备正式 R0 资格。

| 规模 | 计划标识/版本通过 | 当前联盟闭合 | D3 权威发布 | 同身份重复 |
| ---: | ---: | ---: | ---: | ---: |
| 5 | 20/20 | 20/20 | 20 | 0 |
| 20 | 20/20 | 20/20 | 22 | 0 |
| 50 | 20/20 | 20/20 | 32 | 0 |
| 100 | 20/20 | 20/20 | 38 | 0 |
| 200 | 20/20 | 20/20 | 39 | 0 |

151 次权威 D3 发布对应 151 个不同的 `(plan_id, plan_version)`。51 个 episode 发生一次
真实重规划，前后计划身份不同。`payload_digest_mismatch` 和
`cross_binding_invalid` 均为 0。

### 证据可用性

- 有限状态、在线真值使用和禁用真值字段：`100/100 available`，违规均为 0；
- 逐消息通信处置：`100/100 available/verified`，共 195838 条，其中 delivered
  186213、dropped 1950、pending 7675；
- 区域 epoch/lease 的 D3 对照：`0/100 available`；
- 离线身份 ID switch：`88/100 available`，可用部分合计 52；12 项保持 unavailable。

### 200 对 200 性能

20 项 wall time 均值为 12.928 秒，P95 为 14.296 秒；实时因子均值为 0.156，最小值
0.136。该性能来自 2 秒开发态质点仿真，不代表实时部署能力。

### 正式边界

100 项全部来自 dirty source，formal acceptance 为 false；实验矩阵正式资格为
unavailable。区域时期和租约对照仍需补齐，随后在 clean source 上完整执行 900 项。
历史和本轮结果不得拼接。完整复验见
`../reports/HIGH_THREAT_PRECHECK_V4_REVALIDATION_20260730_CN.md`。

## 正式 R0 当前计划绑定审计器（2026-07-30）

### 结论

D6 已完成当前计划绑定审计器和正式 R0 v2 门禁。单元测试证明：D3 与 D4 同代且当前计划
ACK 闭合时通过；D3 v2 对 D4 v1 时，即使旧 D4 为 committed 仍拒绝；当前计划处于
`collecting_acks` 或 `proposed` 时失败关闭；可用的 epoch 或 lease 错代时同样拒绝；
逐消息处置文件缺失时明确记录 unavailable。

真实 20 对 20 runtime 合同 smoke 中，普通一对一 assignment 也携带 `coalition_id`。
修正前审计误报 16 个必需联盟而 D4 仅有 2 个提交；修正后只保留两个多资源目标，
期望数和已审计数均为 2，状态为 pass。该结果属于合同集成复验，不进入正式 900 项分母。

本轮只验证审计器代码，没有读取或运行新的正式保留集，没有重写既有正式制品。历史
`872/900` 仍是旧门禁结果，不能作为新审计器的实验结果。main runtime 的同代租约冻结、
ACK 重评、有限重发、重发耗尽失败关闭、尾部排空和逐消息处置落盘已经代码就绪；仍需在
新的 clean source 上整体重跑 900 项，再形成新的逐 cell 与聚合结论。

### 验证

- 语法检查：通过；
- 正式计划绑定、full audit 和 targeted audit 专项组合：`27 passed`；
- D6 全量：`1261 passed, 1 warning in 128.21s`；
- warning：既有 Matplotlib `Axes3D` 环境提示，与本次逻辑无关。

逐消息处置文件尚未由当前正式 episode 提供。审计器会将其记录为 unavailable，不会将
缺文件解释为零丢包、零 pending 或 ACK 全部送达。

## D4 v7 来源独立外部评价盲审（2026-07-30）

### 结论

D6 对冻结候选 `region_resource_a2_rule_node_transfer_residual_shadow_v7` 完成来源独立
只读盲审。输入为 M16N24、8 区域、64 episode、128 帧，seed 为 `5216-5279`。D6
从冻结低层模型、同快照 R0、标签动作和投影约束逐帧重建；D4 高层 evaluator 调用数为
0，D4 summary 未作为事实来源。

规则正类精确动作命中为 `0/42`。train 的 10 次原始边激活只形成 3 次转移变化，三次
都位于负类，均为错误边和虚假转移。validation 和 test 没有形成转移变化。聚合
actor-derived positive 为 `0/3`，候选没有建立来源独立转移能力。

评价结论为 `failed_closed`。candidate unregistered、admission closed、rule fallback
required；置信校准、正式留出、运行预检、D3、D7、降级、接管、联盟、控制和物理权限
全部关闭。

### 独立指标

| split | 样本 | 正/负 | 原始激活 | 转移变化 | 精确正动作 | 负类精确 R0 | 错误边 | 虚假转移 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| train | 90 | 24/66 | 10 | 3 | 0 | 63 | 3 | 3 |
| validation | 20 | 9/11 | 0 | 0 | 0 | 11 | 0 | 0 |
| test | 18 | 9/9 | 0 | 0 | 0 | 9 | 0 | 0 |

聚合负类精确 R0 为 `83/86=0.965116`。错误方向、错误数量、投影拒绝、干预不变量失败
和原始 R0 完整动作元组偏差均为 0。投影后动作元组变化 3 帧，由三次错误转移触发配额
联动。

### 数据与完整性

训练 `0-99`、正式留出 `1000-1019`、既有设计与评价
`3000-3039,4000-4079`、pilot `5200-5215` 和本次独立评价 `5216-5279` 两两
无交集。模型拟合、检查点更新、阈值调整、置信校准、mutation、registration、admission、
正式留出读取和 prior evaluation payload read 均为 0。

冻结 v4 train+validation 为 425 帧/251 个唯一可观测键，外部数据为
128 帧/92 个唯一键，exact overlap 为 0。raw source、labeled export、labeled
dataset、冻结 v4 和 v7 候选五棵输入树前后不变；D4 评价树也未变化。

D4/D6 JSONL 逐字节 SHA-256 均为
`7785ded96360869edfb694c425321fa3323450cf1624607b53edf5d3eca6a5cd`。
D4 CSV、summary、input integrity、observable overlap 和 artifact manifest 的摘要及
绑定核对通过，mismatch 为 0。

### 输出与验证

| 输出 | SHA-256 |
| --- | --- |
| 完整 JSON | `064002af52617a8cbe35f55acf3c82c8c26b0ef0a9fbe9a5b608eae44e6ca176` |
| split CSV | `3210d4dc7d66196aebdb1ac9762f7ba0f939ddab708b5bc8efdd31a478b89907` |
| 逐帧 JSONL | `7785ded96360869edfb694c425321fa3323450cf1624607b53edf5d3eca6a5cd` |
| 中文报告 | `ba5430744f600d2e817112cb965aca33c84c6741416a482228df67216aa291eb` |

命令行复跑得到相同 content SHA 和逐帧 JSONL，输出
`sha256sum -c SHA256SUMS` 全部通过。专项测试为
`11 passed, 1 warning in 4.65s`，D6 全量回归为
`1234 passed, 1 warning in 126.73s`。本轮不包含 AirSim、运行时或物理收益实验。

## D4 v6 来源独立盲审（2026-07-30）

### 结论

D6 对冻结候选 `region_resource_a2_edge_transfer_shadow_v6` 完成只读盲审。输入为
M16N24、8 区域、64 episode、126 帧，seed 为 `4016-4079`。D6 从冻结模型和标签
dataset 重建全部逐帧动作，不采用 D4 summary 指标。

规则正类精确动作召回为 `0/42`。actor-derived positive 分母为 0，对应比率为
`unavailable/null`。负类精确保持 R0 为 `77/84=0.916667`。该结果不支持 actor 冻结或
置信校准，候选继续 unregistered、admission closed、rule fallback required。

### 指标

| split | 样本 | 规则正/负 | raw/projected transfer | 精确正动作 | 负类精确 R0 | 约束失败 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| train | 89 | 24/65 | 0/0 | 0 | 61 | 6 |
| validation | 20 | 9/11 | 0/0 | 0 | 9 | 6 |
| test | 17 | 9/8 | 0/0 | 0 | 7 | 3 |

错误方向、错误数量、错误边、虚假转移和投影拒绝均为 0。15 帧出现节点动作差异但缺少
对应 transfer，干预不变量判为失败。126 帧均保持规则回退。

### 数据治理

source clean commit 为
`ed9e086ea8cf5c2138035f710cf4deb3e4a2801e`，exporter clean commit 为
`9bdbe31dee34907525eabc9cf278e0d11f7dd88a`。训练、正式 holdout、旧设计/评价、pilot
和本次独立评价 seed 两两无交集。正式 holdout `1000-1019`、旧评价 `3008-3039`、
在线 truth、模型拟合、检查点更新、阈值调整和置信门应用数均为 0。

冻结 v4 train+validation 的 425 帧形成 251 个唯一在线可观测键，外部 126 帧形成
94 个，精确重合为 0。可观测键不含 seed、episode、目标标签或 truth。

### 完整性

D6 固定并复核 source、标签导出、标签 dataset、冻结 v4、v6 候选和 D4 评价树。
审计前后六棵树摘要相同，`input_mutation_count=0`。D4 artifact manifest 文件与内容
SHA-256 为
`1b85e8667e211bf4f01264bd7c7eac4dbaeee20f1002a446f7462b52129fb7fc` /
`030ee163db60b8257c919af56b8e53e3dc36dac17e62f5d687e9f95be0e88117`。
D6 重算 JSONL 与 D4 JSONL 的文件 SHA-256 完全相同：
`771826bff66d3ba601d0ffecc95f7ab9faf416826898319de7b9f1669020c7c5`。

输出目录为
`outputs/d4_v6_source_independent_external_audit_m16n24_20260730/`。

| 输出 | SHA-256 |
| --- | --- |
| JSON content | `771ed844ab3364fde4ed25217ffd45b7fe04f300ffb8fe4bd2df5ec99d1f25e1` |
| JSON file | `d7c611d2cd7071d98663b62da451ebeecdeb4d327bcbe2bff95277d8041d39dc` |
| split CSV | `db1b3973e6ff50681caff20695649064f6a10345ffc68ad5e28ebf651405a379` |
| recomputed JSONL | `771826bff66d3ba601d0ffecc95f7ab9faf416826898319de7b9f1669020c7c5` |
| 中文报告 | `b123db5c02dd8d196cefab138d9afb67968f915fa6ec05544c97708e984134b7` |
| `SHA256SUMS` | `aa58c178cf947eb3957a54ba43fa6dc4f2ac9991fd03907b7867a3064e94369c` |

专项测试为 `8 passed, 1 warning in 5.20s`，D6 全量为
`1223 passed, 1 warning in 139.78s`。唯一 warning 是既有 Matplotlib `Axes3D`
环境提示。本轮不是 AirSim、运行时或物理收益实验，不产生任何权限。

## D4 v5 来源独立外部评价（2026-07-29）

### 结论

D6 对 clean commit
`63987592c216fbdb7e03d77183afc6e9f15748a2` 生成的 M16N20 数据完成独立只读评价。
输入为 32 个 episode、63 帧，seed 为 `3008-3039`。候选没有形成来源独立正类分母，
正式准入继续关闭。

旧 v4 TRAIN+VALIDATION 为 425 帧、251 个唯一 observable key。新外部数据为 63 帧、
41 个唯一键，exact 重合为 0。train、validation、test 的唯一键分别为 30、6、5，三个
split 之间也没有 exact key 重合。

### 哈希

| 制品 | SHA-256 |
| --- | --- |
| source manifest 文件 | `af12051917cfe9eedfc8587c953599112db62858e4b01820a16ddd5b0a10231d` |
| labeled dataset | `ed2fd4b1a4d50ec80e5abdaa35a1470cec03d419665ae0e08b7c4339e9b8887e` |
| labeled split | `cdaa40241195516eb1679f6ed0a8179f3d2365c9768f9ef9a44b6f85fabcefb6` |
| source artifact 文件 | `ccf327717a293f63b5655e978202ff720f20c74bfd8ae401f2233cc590bb753a` |
| external evidence 内容 | `1d9cfa165f4fe24fa3881d66b73c0ed14f3902dd9f901c29d29fa7d6dae60191` |
| label audit 内容 | `8798bd28037a7c52abc972e9a13551525e68eeb590d49e497b0db6cd31800336` |
| v4 tree | `2afd692874b91a23a5525448a0c5af98f3c2d96f0b12cebbf81a570d58d500d0` |
| v4 actor state | `33a28060f11277a549b90d2f2f365962fec057b2bfb50a70ab5a422059cb9fe5` |
| v5 tree | `632f066fcad363531762e6b7a1ef0f21c03b7b0d0aa3b4cd39a16e4fbbf7c273` |
| v5 state 文件 | `d8bd543759f6e52eb62585c1bd8aa67e59e718e7b548d38cc9dd5c690a5612a3` |

实际摘要与冻结预期全部一致。训练、正式 holdout、pilot 和独立评价 seed 两两无交集。
审计开始前和全部加载、评分、observable key 重合计算结束后，source、labeled export、
labeled dataset、v4 actor、v5 calibrator 五个完整输入树摘要逐项相同；
`input_mutation_count=0`。专项负向测试确认审计阶段候选树发生变化时稳定失败关闭。

### 分片指标

| split | 样本 | 规则安全正动作 | actor-derived positive | score 范围 | 0.60 通过 | 负类误接收 | 回退 |
| --- | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| train | 43 | 1 | 0 | 0-0 | 0 | 0 | 43 |
| validation | 10 | 1 | 0 | 0-0 | 0 | 0 | 10 |
| test | 10 | 0 | 0 | 0-0 | 0 | 0 | 10 |

两个规则安全正动作均未被冻结 actor 以同一可执行签名输出。actor-derived positive 分母为
0，正类召回不可评价。63 个 actor-derived negative 全部被 0.60 门拒绝，负类特异度为
1.0。该结果只证明负类拒绝，不证明正类泛化。

D6 本轮读取 external test 10 帧；main 此前也读取该 10 帧。两次读取均属于非正式外部
test。正式 holdout `1000-1019` 的读取数为 0。模型拟合、门限调整、split 修改、正类生成、
runtime preflight、D3 successor、D7 权限和在线控制运行数均为 0。

### 输出

输出目录为
`outputs/d4_v5_source_independent_external_audit_m16n20_20260729/`。

| 输出 | SHA-256 |
| --- | --- |
| JSON content | `cb9b9e2dc9481c9ac83c55158279f5d5b3f2c5ae2d7f12043ba851ed6fbc7a06` |
| JSON file | `f1f8047b2b858594425dd2e7e5e216025623e49d6e34bfe0f4aaa4790624aa6e` |
| split CSV file | `8e74ed1d35f75d7f7e30585a6609ed35398300d353bbcea8fd59f703eec4a7e2` |
| 中文报告 file | `7fabd3a0602a245aa644fdcc9f1582d94db5d1b81c20d954e7d379b38767426f` |
| `SHA256SUMS` file | `33d4e867390d986ac359ae5f90981a894cdaf17a4f91773cef9d90889fd6ac82` |

逐 split CSV 固定使用 LF，实测为 4 个 LF、0 个 CR，各行没有空格或制表符行尾。JSON
因 `audit_repository_head` 更新为
`b3147fcae56cb1ff1e67cdd1bd8dad353d567460` 而更换摘要；冻结来源提交仍为
`63987592c216fbdb7e03d77183afc6e9f15748a2`。除该审计实现 provenance 外，JSON 评价内容
与上一轮一致。

候选保持 unregistered、admission closed、rule fallback required。生产、D3 和 D7 权限
均为 false。本轮不是 AirSim、实飞或生产性能实验。专项测试
`5 passed, 1 warning in 2.33s`，D6 全量回归
`1215 passed, 1 warning in 123.70s`。warning 为既有 Matplotlib `Axes3D` 环境提示。

## D4 v5 置信校准候选审计（2026-07-29）

### 结论

D6 对固定 v5 候选完成只读审计。候选四个文件、外部锚、v4/v3 绑定、数据用途和权限完整；
实际 24 维 latent、TRAIN 标准化状态和 k=11 评分可独立复现。固定 0.60 开发门通过。

VALIDATION 与 TRAIN 高度重合，去重后正类分母不足。候选不能提供独立验证或泛化证据。
最终状态为 `development memorization baseline`、candidate unregistered、admission
closed、rule fallback required。未运行 formal holdout/runtime preflight，未授予 D3/D7
权限。

### 固定锚

| 制品 | SHA-256 |
| --- | --- |
| manifest file | `caa774143db4a9c797e2a4ddff42d8f4cbc437471fe95926270f9bdec93b9459` |
| manifest content | `83192d4f96d7dd2c64ffd8f9b5c7c11a70c8c24a90934a0dfea12fe397c12c52` |
| calibration state | `d8bd543759f6e52eb62585c1bd8aa67e59e718e7b548d38cc9dd5c690a5612a3` |
| calibration summary | `7f0047f72ebeea0358c127af5fe3dabe0c7f886bee48ff94b7d92b12b3259c60` |
| development gate | `e88c9480765369e34a03dd417e4b483143188da40c3403ff35918f9cfd605b3c` |
| builder source | `77e91e06712013e6c1195c40f72b9a941d8396aa4594b52bd7d839276b57e1e0` |
| v4 tree | `2afd692874b91a23a5525448a0c5af98f3c2d96f0b12cebbf81a570d58d500d0` |
| v3 registry tree | `07c770b05ffc70f190cd8b45d762d579857747e0efb12b472a2354ee5aeaa93a` |

普通 artifact 字节篡改由 `candidate_artifact_external_anchor_mismatch` 拒绝。同步修改
payload、候选 artifact hash、content hash 和 manifest 的自重签攻击由
`candidate_manifest_file_external_anchor_mismatch` 拒绝。

### 数据与维数

| split | 语义读取 | 正类 | 负类 | fit |
| --- | ---: | ---: | ---: | ---: |
| TRAIN | 350 | 58 | 292 | 候选声明 350，D6 0 |
| VALIDATION | 75 | 13 | 62 | 0 |
| TEST | 0 | unavailable | unavailable | 0 |
| formal holdout | 0 | unavailable | unavailable | 0 |

v4 树完整性检查对 TEST 文件只做字节哈希，不解析 payload。truth identifier、future outcome
和 reward 使用均为 0。候选所有权限为 false。

冻结 v4 actor 的 `hidden_dim`、权重形状和 v5 state 的 `feature_dimension` 均为 24。
重建均值、标准差和归一化特征与 state 的最大差均为 0（容差 `1e-12`）。D4 报告和任务
口径写为 64 维，与制品不一致。严格审计保留
`documented_latent_dimension_mismatch`。

### 固定开发门

| split | 正类召回 | 负类特异度 | 最小正裕量 | Brier |
| --- | ---: | ---: | ---: | ---: |
| TRAIN | 1.000000 | 1.000000 | 0.400000 | 0.000000000 |
| VALIDATION | 1.000000 | 1.000000 | 0.209319 | 0.000484791 |

候选 summary 中的数值没有作为审计输入。D6 先独立计算，再逐字段比对；结果一致。

### TRAIN 记忆审计

| 评分方式 | 正类召回 | 负类特异度 | 最小正裕量 | Brier |
| --- | ---: | ---: | ---: | ---: |
| 全库存，含自身 | 1.000000 | 1.000000 | 0.400000 | 0.000000000 |
| 逐样本留一 | 1.000000 | 0.993151 | 0.066283 | 0.006652708 |
| raw observable key 留组 | 0.965517 | 0.958904 | 0.054604 | 0.037610440 |
| latent exact key 留组 | 0.965517 | 0.958904 | 0.054604 | 0.037610440 |

全库存评分的 self-match 为 350/350。raw 和 latent 均形成 229 组，115 组含副本，最大组
大小为 3。按同键整组移除后出现 2 个正类未越门和 12 个负类越门。

### VALIDATION 重合

| 项目 | 数量 |
| --- | ---: |
| raw graph exact overlap | 42 |
| latent exact overlap | 42 |
| 非 exact 且距离 `<1e-3` | 20 |
| 距离 `[1e-3,0.1)` | 10 |
| 距离 `>=0.1` | 3 |
| 最近邻标签一致 | 75/75 |
| 正类 exact overlap | 12/13 |

最近距离最小值、P50、P90、P95 和最大值分别为
`0/0/0.0123058/0.0940144/2.4766768`。VALIDATION 的 72/75 条记录距离小于 0.1。

### 去重与距离分层

| 子集 | 样本 | 正/负 | recall | specificity | margin | Brier |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 全 VALIDATION | 75 | 13/62 | 1.000000 | 1.000000 | 0.209319 | 0.000485 |
| 去 exact | 33 | 1/32 | unavailable | 1.000000 | unavailable | 0.001102 |
| 距离 `>=1e-3` | 13 | 1/12 | unavailable | 1.000000 | unavailable | 0.002797 |
| 距离 `>=0.1` | 3 | 0/3 | unavailable | unavailable | unavailable | unavailable |

最小指标分母为 5。分母不足时 JSON 使用 `availability=unavailable` 和 `value=null`，没有
以 0 或单样本比率补值。

### 输出与验证

输出目录为
`outputs/d4_v5_confidence_candidate_independent_audit_20260729/`。

| 输出 | SHA-256 |
| --- | --- |
| JSON content | `7317fc0c19a8c2f149c3f7193e725db9470851526d329c6f897ee2da8762b1d9` |
| JSON file | `c12fdd740120193e071452abdce487b05d79f230ac907ebc7ad7c15bcbeb2bac` |
| 中文 Markdown file | `e56faa01c04e2010c577d7f1c810ce0b8d9f5eed3b42b17d0cd35c8638700abf` |
| `SHA256SUMS` file | `0aa7921cb2643b1acf792377b37dbee5e7283de6b29eba8a77aca4e7288f3cab` |

专项测试 `5 passed, 1 warning in 12.56s`。warning 为环境中的 Matplotlib `Axes3D`
多版本提示，与本次 JSON、Torch 模型或近邻审计无关。D6 全量回归为
`1210 passed, 1 warning in 119.78s`。

## D4 v4 未注册候选独立审计（2026-07-29）

### 输入与结论

D6 对以下固定候选执行独立、只读审计：

```text
research_modules/d4_distributed_fallback/outputs/
  d4_v4_candidate_observable_calibrated_20260729/
  region_resource_a2_executable_transfer_shadow_v4
```

来源外部数据为
`d4_v4_external_composite_observable_20v20_8region_curriculum_seed9_20260729`。候选由
clean commit `fd857457bb27a4a709a7c4937e22ebe1cbd7f848` 构建。结论状态为
`pass_development_integrity_only_admission_closed`：候选完整性、来源绑定和开发指标重算
通过；候选仍未注册，formal holdout 和 runtime preflight 未完成，正式准入关闭。

| 固定锚 | SHA-256 |
| --- | --- |
| manifest content | `4f3e973597469d394a594bec3dd7d2c16b24e80d2e97ba45f718d9ef8397e116` |
| manifest file | `2986d166ad6de231896e46f78aa2d9304c21b6d68714eaf34dfe21439220bebe` |
| model state | `33a28060f11277a549b90d2f2f365962fec057b2bfb50a70ab5a422059cb9fe5` |
| dataset | `b31fc43f3d3cff34ee53f2b2c33ece0b06d7624e46e26a36c4aa834135e7fb8c` |
| split | `c212fe9b48e9908fd4d47488711724ed361429cf9df29667ac32c3e88d094619` |

候选树共 180 个文件、4 个目录。除 manifest 自身外的 179 个 artifact 全部在清单中且逐项
SHA-256 一致，没有 symlink 或特殊文件。4 个 source implementation 与 clean commit blob
及当前只读文件一致。外部 evidence、source derivation、export summary、bundle dataset
manifest 和候选 development manifest 逐字节交叉一致。

### 数据库存与隔离

| split | seeds | episodes | frames/samples | actor 正/负 | confidence 正/负 |
| --- | ---: | ---: | ---: | ---: | ---: |
| train | 70 | 140 | 350 | 60/290 | 58/292 |
| validation | 15 | 30 | 75 | 15/60 | 13/62 |
| test manifest only | 15 | 30 | 74 | unavailable | unavailable |

候选内 test payload 文件数为 0。builder test payload read、D6 audit payload read、fit 和
weight fit 均为 0。truth identifier use、future outcome available/use、reward available
和 formal holdout seed use 均为 0。训练数据源为两个 clean dataset，合计 200 episodes、
499 frames；候选只选择其中 170 个 train/validation episode。

### Actor 与 confidence 重算

actor 只用 train 库存推导正类样本权重 `4.833333`，非零边权重按上限截断为 `32`。
actor checkpoint 独立选择 epoch 107。结果如下：

| split | 正类召回 | 负类召回/特异度 | balanced recall |
| --- | ---: | ---: | ---: |
| train | 58/60 = 0.966667 | 276/290 = 0.951724 | 0.959195 |
| validation | 13/15 = 0.866667 | 58/60 = 0.966667 | 0.916667 |

confidence checkpoint 独立选择 epoch 66；固定门限为 0.60。180 个历史 epoch 中有 8 个
checkpoint 通过固定门，最长连续 7 个。开发样本结果为：

| split | 正类召回 | 负类特异度 | Brier | 最小越门裕量 | 最大负类裕量 |
| --- | ---: | ---: | ---: | ---: | ---: |
| train | 12/58 = 0.206897 | 292/292 = 1.000000 | 0.186847275 | 0.000504935 | -0.000029838 |
| validation | 4/13 = 0.307692 | 62/62 = 1.000000 | 0.186468779 | 0.000504935 | -0.000602221 |

固定门在已读 train/validation 上没有负类越门。正类召回较低，且门限两侧均存在薄裕量，
所以报告固定 `thin_margin_warning=true`。这些数字是开发数据重算结果，不构成独立
holdout 或泛化证据。

### Fixture、注册和权限

development fixture 的有效 confidence 为 `0.602367163`，门上裕量
`0.002367163`，产生一个经投影的可执行 transfer。该 fixture 由 train-domain 冻结可观测
定义选择，分类为 `training_domain_smoke_only`；generalization、formal validation 和
production permission 均为 false。

v3 registry 的 8 个文件逐项摘要不变，树摘要为
`07c770b05ffc70f190cd8b45d762d579857747e0efb12b472a2354ee5aeaa93a`。
v4 五个注册常量全为 null，registry 目标路径不存在。assist、authority、assignment、
takeover、coalition commit、control、production ACK、formal evaluation、physical
permission、actual adoption 和 benefit 等逻辑权限全部为 false。候选状态保持
development/shadow、unregistered、rule fallback required、admission closed。

### Admission blocker 与输出摘要

最终 JSON 的 blocker 为：

```text
candidate_unregistered
formal_holdout_not_completed
runtime_preflight_not_completed
development_fixture_train_domain_smoke_only
confidence_positive_recall_low
confidence_threshold_passing_margin_too_thin
runtime_outcome_and_benefit_unavailable
```

最终审计时间为 `2026-07-29T23:15:40Z`。输出摘要如下：

| 输出 | SHA-256 |
| --- | --- |
| JSON content | `3a4ed311c55e6419d3db1b3ba830f0ea6ce22c638eb363aa03c3f4510fdcd7c2` |
| JSON file | `e225a1a16ae2b1988ce5ea34b3cceaa30d7c829004663368ecc6514de3eb3887` |
| 中文 Markdown file | `16a2e5a4efacd4b58b22b7b9dd9d0d632cedb3e7b8d6cc6d55a0dce954870fe0` |
| `SHA256SUMS` file | `6ee4e7822800401b531acc93f03f105fc1ff02a77c1842fe1d36546bc9500af6` |

新增 blocker 只收紧准入治理；状态继续为
`pass_development_integrity_only_admission_closed`。

### 负例与验证

测试对临时副本分别篡改普通 artifact，以及把 `assist_enabled` 改为 true 后同步重算候选
自有 manifest content hash。前者由 artifact SHA 门拒绝，后者由 D6 固定外部 content anchor
拒绝。专项测试为 `3 passed, 1 warning in 4.97s`；D6 全量为
`1205 passed, 1 warning in 112.59s`。warning 是既有 Matplotlib `Axes3D` 环境提示。

机器可读 JSON、中文 Markdown 和 `SHA256SUMS` 位于
`outputs/d4_v4_candidate_independent_audit_20260729/`。本轮没有运行正式 holdout、
runtime preflight 或候选登记，也没有改变或建议开放权限。

## D4 readiness-v3 v2b 隔离双臂审计（2026-07-29）

输入为 20 目标/20 资源、2 个侦察节点、8 区域、seeds 2003-2012、3.2 秒的开发隔离批次。
最终 compact `SHA256SUMS` 外部摘要为
`4077379face18c036b1cec3fe62e158c9cedb2e42da0d4e5c1573090b2da7745`，
full seed 2007 摘要为
`a061b2d69c98e07d506c28ce322761c5968417ac08ef607c1775a34f90c3d72c`。
重生 D6 full-chain 输出的 `SHA256SUMS` 摘要为
`6201eed6f7bcb6396c33631fe484d452cc050c630b5fb9783c11fde0ecf00199`。
两份 v2b manifest 的 11 个关键实现文件集合摘要均为
`893918a8b1b76df3fe7bf1efc75a3c81f76b97d3cc8633a1e2bf6568c01cc77c`。
compact 13 个源文件和 full 92 个源文件全部受根清单约束。重复/缺失 seed、在线真值、
非有限值和权限冒充均为 0。

| 指标 | 结果 |
| --- | ---: |
| 原始推理/运行门/投影/隔离采用 | 10/10 |
| D3 后继 | 1/10 |
| 接受的开发 ACK | 1/10 |
| producer 物理窗口摘要 | 1/10 |
| compact 摘要内严格 successor→ACK→D7 同链重放 | 0/1 |
| 无可执行后继 | 9/10 |
| 拦截数 R0/treatment | 全部 0/0 |
| 最小距离差值最大绝对值 | 0.0 米 |

拦截数和最小距离在 10 个 seed 上覆盖完整，因此这两项的有界非退化可用并通过。10/10
双臂均无拦截，最小距离逐 seed 完全相同，正收益 unavailable/false。候选与规则臂没有
D3 可执行字段差异。

seed 2007 full runtime join 的独立重算结果如下。

| 指标 | control | treatment |
| --- | ---: | ---: |
| ACK | 4 | 4 |
| bindings | 77 | 77 |
| D4 regional applied ACK | 0 | 1 |
| 同身份 refresh | 1 | 1 |
| 在线真值使用 | 0 | 0 |
| admission | closed | closed |

treatment 的 advisory、source plan、P2/v2 successor、ACK 和 19 条 D7 非 hold 指令形成
同链。首次发布与 refresh 的严格执行签名均为
`sha256:00f71e0f06063c042e224af82faf19ec59d5319ac0c5cfb5ced3afe85576b4ad`，
authority epoch 1 和 lease 5.85 秒保持不变。D3 refresh 修复通过 D6 失败关闭合同。

默认 runtime join 与冻结 persisted 结果语义完全一致，19 条 D7 绑定中原生 18 条形成
物理状态窗口。full-chain audit 对 `INT-0004/GT3D-000004` 的单帧空档显式应用
evaluator-only bounded coast bridge：前锚 `0.833472220197s`、空档
`1.035192721089s`、后锚 `1.236148794089s`，前后均唯一映射 `TGT-0004`，锚间隔
`0.402676573892s <= 0.9s`。最终为原生 18 + bridge 1 = effective 19/19。

bridge policy 为 `offline_confirmed_unmatched_double_anchor_v1`，只读 D2 v2 和离线 truth
state，不回写 D2、不重绑 `global_track_id`，在线暴露为 false。source 与 successor 的
资源—目标及联盟绑定仍完全相同，实际候选动作不可辨识。正收益保持 unavailable/false；
该结果不能支持因果收益或生产准入，admission closed、规则回退和全部 false 权限保持。
验收日期为 2026-07-29；样本为 seed 2007 的 1 个完整双臂 episode 和 19 条 applied-chain
D7 绑定，bridge 接受门限为
`<=min(configuration.lineage_time_window_s, 0.9s hard cap)`。D6 全量回归为
`1196 passed`。

## D4 A2 来源与运行分布验证（2026-07-28）

### 结论

D4 current-lineage A2 固定候选的来源验证通过。D6 确定性合同 fixture 使用 5 资源/5 目标、
2 区域和 6 帧，6/6 均触发特征 OOD。该 fixture 没有模型动作，运行链回退到确定性规则。
规则回退没有计为 treatment，也没有形成成对非退化结论。该 fixture 只验证合同，不是 main
运行证据。

| 项目 | D6 合同 fixture | 分布内 no-op 回归 |
| --- | ---: | ---: |
| `model_source_verified` | true | true |
| `runtime_distribution_compatible` | false | true |
| 受审快照 | 6 | 1 |
| 有限记录 | 6 | 1 |
| OOD 快照 | 6 | 0 |
| 模型动作 | 0 | 0 |
| 动作缺失 | 6 | 1 |
| 规则回退 | 6 | 1 |
| rollout 前置条件 | false | false |
| treatment | 0 | 0 |
| 成对非退化 | unavailable | unavailable |

“分布内 no-op 回归”列是软件回归，不是新的 AirSim 物理实验。它使用落在冻结特征边界内
的 D4 原始快照，将模型输出构造成合法 no-op，再由 D4 正式 shadow DTO 落盘和复载。结果
证明动作缺失与规则回退不会把分布内输入误判为 OOD；实际采用仍因无非零干预而不可用。

main 的真实预检与上述 fixture 分开记录：

| main 预检 | seed | 帧数 | OOD |
| --- | ---: | ---: | ---: |
| 5 资源/5 目标、2 区域 | 2000 | 3 | 3/3 |
| 200 资源/200 目标、8 区域 | 2001 | 2 | 2/2 |

两组 main 预检均不满足运行分布兼容门。其帧数、动作和回退统计不得由 D6 fixture 推断。

### 来源审计

```text
clean commit:
b0d498d9e76e19e9045e127b6dae26ea164b3fa4

candidate manifest file SHA-256:
7cc10ad770bd95fcb813dbf3d16b17040ec5f41f80fe0dc53e3e291a32f4de64

model state SHA-256:
fd1b9c4cf7580083fadc04a70b87aa6439930eba764a970279611ccc57f30047
```

D6 从受版本控制的 D4
`model_registry/region_resource_a2_current_lineage_development_v1/` 复算清单和七项制品
摘要，检查 clean source、数据划分、模型加载、参数有限性、development/shadow 边界和全部
false 权限。权重篡改负例失败关闭；clean clone 不依赖被忽略的 `outputs/`。

### 配对边界

严格 A2/R0 consumer 已实现。正式评价仍需至少 20 个执行前预注册未见 seed、兼容运行分布
上的可辨识非零模型动作、D3 严格后继、runtime/owner/coalition ACK、确认后的物理窗口、
独立 R0、truth-use=0、有限状态和完整指标分母。当前两类回归均不满足 treatment 条件。

### 软件验证

| 范围 | 结果 |
| --- | --- |
| A2 来源、分布、动作和配对定向测试 | `38 passed, 1 warning in 6.10s` |
| D6 全量测试 | `1144 passed, 1 warning in 108.47s` |

warning 为既有 Matplotlib `Axes3D` 环境提示。本次未启动 AirSim，未生成模型收益数据，也未
授予 admission、assist、authority、assignment、failover 或 control 权限。

## G1 模型来源只读验证（2026-07-28）

### 结论

G1 `model_source` 的 D6 软件适配缺口已关闭。适配器只接受正式 D5 v5 候选的固定模型身份和
实现谱系，并从原 external audit v2、post-assembly audit v2、v5 包、held-out、
paired-shadow、lineage 和校验清单重算来源事实。reference 自身不能声明通过或权限。

当前正式 readiness 仍未就绪。该结论只覆盖 G1 模型来源。实际采用、运行确认、物理窗口、
唯一同键 R0、成对非退化、同运行真值使用审计、有限状态审计和外部权限八门仍
unavailable。C1/F1 缺其余三个模型组件来源。全部模型晋级、分配、接管、相机和控制权限为
false。

### 实物验证

验证显式使用只读外部根：

```text
/tmp/MSM-d5-g1-formal-evidence-8d5e02e-20260727
```

clean source worktree 为：

```text
/tmp/MSM-d5-g1-formal-8d5e02e
```

单条真实证据链得到
`source_class=formal_post_assembly_audit`、`formal=true`、
`component_ids=[d5_graph]` 和 `audit_passed=true`。模型指纹为
`sha256:7fb5db8b6099ca4da5706a3bec53ff7cd634e8bd267c036ce3ee4ee4bf71ca71`。
验证未改动外部证据树。

仓库根没有 reference 指向的 13 项原制品。以仓库根作为 `artifact_root` 时专项用例返回
`gate_source_original_file_missing`，不会搜索 `/tmp`，也不会使用仓库中的 audit JSON
补足原始链。

### 软件测试

验收门限为全部正例通过、全部攻击例失败关闭、权限始终为 false。结果如下：

| 范围 | 结果 |
| --- | --- |
| G1 model-source 专项 | `14 passed, 1 warning in 3.07s` |
| readiness v2 与 model-source 联合 | `32 passed, 1 warning in 8.16s` |
| D6 全量 | `1138 passed, 1 warning in 126.65s` |

负例覆盖未登记替代模型、sidecar 自报 facts/权限、嵌套原制品篡改、路径逃逸、符号链接、
摘要错配、schema 错配、模型身份错配、组合变体缺组件、重签权限升级和仓库根自动发现攻击。
warning 是既有 Matplotlib `Axes3D` 环境提示。本次没有运行 AirSim，也没有产生性能或物理
拦截结论。

## 正式学习运行准备度软件验证（2026-07-27）

### 结论

D6 已具备 G1、A1、A2、A3、C1 和 F1 的统一正式运行准备度框架。当前受信 adapter 仅覆盖
冻结 seed gate。它通过 reference sidecar 绑定六项既有 producer 制品，并调用现有 canonical
seed auditor 重算；其余九类 gate unavailable。

专项 18 项全部通过。正例由已有训练 seed、共享 split 和四个模块数据集 schema 构造，再经过
`audit_canonical_seed_split_readiness()`；只通过冻结 seed 单门。攻击例为每个变体构造十个
文件 SHA-256 和内部摘要均正确的旧通用 wrapper，六个变体的 formal readiness 仍全部
unavailable。负例还覆盖原 producer 文件和 sidecar 篡改、摘要错配、未知 schema、缺文件、
内外层路径逃逸、目录和缺制品根。测试没有启动 900-cell、多 seed、AirSim 或大写盘实验。

### 当前观测

当前根文件系统可用 `14139191296` 字节，约 `13.168 GiB`，低于固定 `20 GiB` 保护线。系统
没有第二个可用于正式输出的大容量挂载点。存储门输出：

```text
formal_runtime_disk_below_20_gib_threshold
alternate_large_capacity_mount_unavailable
```

因此正式运行当前不能启动。六个变体在 readiness 中也都因非 seed gate 缺受信 adapter 而
保持 formal unavailable。该判断没有改写其他独立审计报告中的 G1 模型结果，也没有将
A1/A2/A3 的开发证据重新分类。

### 当前变体状态

| 变体 | 当前最强证据 | 主要缺项 |
| --- | --- | --- |
| G1 | 独立报告中的正式 v5、20-seed held-out 和 paired-shadow | model-source adapter；实际采用、ACK、物理窗口、运行 R0、运行非退化、外部权限 |
| A1 | 保留 seed 代价矩阵 20/20 变化 | 模型准入；final binding 0/20；运行 ACK、物理和非退化 |
| A2 | 20-seed no-op 拒绝；单 seed 开发适配器链路 | 可辨识非零正式干预、正式采用、同键 R0 和非退化 |
| A3 | 开发复跑 492/488/4 | clean/frozen 全清单、未见 seed、完整物理配对和非退化 |
| C1 | 四组件组合接口 | 四组件模型与运行证据同时闭合 |
| F1 | 四组件全流程接口 | 四组件模型与运行证据、外部权限和执行资源同时闭合 |

paired-shadow、20 个开发 seed、软件测试夹具和零丢包对照均未进入正式运行证据分母。当前没有
模型晋级、分配、降级、相机或控制权限。

## A3 零检测帧开发审计（2026-07-27）

### 结论

D5 v2 将“图像已处理但零检测”记录为显式负观测。D6 v4 可以将该记录作为可审计物理窗口，
同时把关联状态记为重新捕获、分配目标覆盖率记为 0。该状态不计入锁定、模糊或保持，也不
声明主动视觉收益。

main 提供的同配置 seeds 1000-1019 开发复跑包含 492 个候选。488 个可配对，4 个不可配对，
配对覆盖率为 99.18699%。窗口消费 329 个零检测帧，拒绝 0 个；159 个 v1 帧为 locked，
329 个 v2 帧为 reacquire。零检测帧 locked/ambiguous 计数为 0。4 个未配对记录均出现在默认
1% 通信丢包条件，相应 4 个 seed 关闭丢包后全部配对。

### 证据边界

该复跑来自未提交工作树，没有持久化完整逐候选 pair inventory，也没有独立未见 seed。D6
没有把开发汇总升级为正式批次，没有计算正收益或非退化。模型晋级、分配、降级、相机和控制
权限均为 false。旧 536/152/384 冻结批次和 SHA-256
`455d181076553a485ff824618abc6d037a4477bb6342877d1d1e427fd28583a9` 保持不变。

### 软件验证

D6 专项增加零检测帧 0 覆盖正例，并覆盖 locked、ambiguous 和覆盖率篡改。专项结果为
`64 passed, 1 warning in 11.79s`，D6 全量结果为
`1106 passed, 1 warning in 100.94s`。warning 是既有 Matplotlib `Axes3D` 环境提示。正式
证据仍需 clean source 下的逐候选 disposition、paired evidence、通信丢包处置和候选/R0
双 episode 文件。

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

## D5 G1 v5 正式审计（2026-07-27）

### 条件

正式执行使用 clean commit `8d5e02ec989259ce3d39e1e4ad6a90dd0d8d5b54`。证据根目录为
`/tmp/MSM-d5-g1-formal-evidence-8d5e02e-20260727`。该批覆盖 20 个未见 seed、900 个
episode 和 45 个场景规模单元。candidate lineage 有 900 条记录和 900 个唯一
`episode_uid`，文件 SHA-256 为
`83e105290f3e624f267d92ceaf050d32291bd5bbbabf98580846cd31498b1af1`。

外部门限沿用冻结配置：held-out F1 不低于 0.92、错误合并率不高于 0.01、候选召回不低于
0.95、P95 推理时延不高于 100 毫秒、单特征最高 AUC 不高于 0.98、扰动 profile 不少于 5，
扰动最低边 F1 和簇 F1 均不低于 0.9。形式化目录至少包含 20 个未见 seed、900 个 episode
和 45 个场景规模单元。

### 外审结果

external audit 输出 schema 为 `d6.d5-g1-external-audit.v2`。结果为 `status=pass`、
`audit_passed=true`、`blocker_codes=[]`。主 JSON 文件 SHA-256 为
`cbd6c72b2d9e7b78bf3aa36f975e6627250d2bf18de5a0b0ebc2c8f6cf760cd6`，内容
SHA-256 为 `334cf662e49c735931019ff358be1894d1358f1b4a5a868759eee41d3d282d15`。

模型晋级、G1 辅助、默认路径变更、分配、故障接管和控制六项权限全部为 false。真实相机
泛化、中心 `global_track_id` binding 正确性和物理闭环结果均带原因声明为 unavailable。

### 装配结果

D5 生产 assembler 随后生成 `d5.tracklet-model-bundle.v5`。manifest 文件 SHA-256 为
`b431d066362005868374d038eb93a83b773c03715a53d8a9dfd0da21784f317d`。D5 strict loader
和 shadow loader 均通过。

D6 post-assembly 输出 schema 为 `d6.d5-g1-post-assembly-audit.v2`。结果为
`status=pass`、`audit_passed=true`、`blocker_codes=[]`，内容 SHA-256 为
`17dda42d06b4be1d21ff8f1f8baecc320fd49b532be06a9f9f6b304341763e1`。consumer schema
为 `d6.d5-g1-post-assembly-audit-consumer.v2`。六项权限仍全部为 false。

D5 assist 请求没有获得 authority contract 授权，以
`bundle_g1_assist_authority_not_granted` 失败关闭。该结果关闭正式 external audit v2、
正式 v5 和正式 post-assembly v2 待运行项。它没有启动在线 G1、AirSim 控制或物理拦截，
三类 unavailable 工程证据继续保留。

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

本节记录 2026-07-27 正式执行前的版本修正状态。当时没有执行正式 external audit 或
post-assembly audit，也没有组装 v5。目录
`/tmp/MSM-d5-g1-current-runtime-d6-external-audit-64cb865-20260726-v2/`
内部仍是 external audit v1，现标记为 `rejected_transition_schema_v1`。下文保留其指标和哈希
用于追溯，但它不得进入新装配。正式 v2 证据已在上节所列新目录生成。

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
   `81968e0d...066e7f`，当次 D5 运行实现摘要为 `ff8c744e...8a1b7`。
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

D6 没有授予模型晋级、G1 辅助、控制权或默认路径变更。该 99fa 证据不能被 D5 装配为正向
admission。该候选如需复核，必须在同一候选实现上生成新的 held-out/paired 实物，并处理合成
单特征捷径和扰动最低性能。

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
`18d2cd11...dc12`，均由 D6 去除摘要字段后按规范 JSON 复算。十个 D5 运行时源文件当次实现摘要
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
达到现有门限。该结果生成时 D5 准入装配、main 显式启用和运行作用域审计均未完成。
2026-07-27 已完成 v5 正式装配和两级审计；D6 之外的独立运行授权与实际运行作用域审计仍未
发生。

五类扰动使用固定 post-gate 候选图，没有在扰动后重新执行相机投影、门控和候选图构建。当前
样本来自合成三维质点投影和离线 truth evaluator，不代表真实相机、真实外参漂移、真实遮挡、
在线检测误差或实机时延。专项测试为 `14 passed, 1 warning in 4.54s`；D6 全量为
`975 passed, 1 warning in 86.70s`。warning 来自既有 Matplotlib `Axes3D` 导入环境，不影响本次
文件、内容哈希和二维报告。

### 64cb865 历史运行实现外审

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
3 项，全部通过。当次十文件 runtime implementation SHA-256 为
`5506638201623048fb53c8e15493a2dc367d5682abbee3b7235704721586b8ea`，与输入期望、
manifest 和 held-out/paired 联合证据相同。九个 artifact 均来自当次批次，paired 没有
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

本节和下一节保留完整 R0 执行结束前的定向与增量记录。当前 900-cell 结论见文末
“正式 R0 全量后验审计”。

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
`98d01bf`。完整 R0 formal rerun 已在后继 clean source `1e5ed8d` 上启动；该增量阶段完成
177/900，尚未形成整体结果，D6 当时仍保持旧正式结论 895/900。
详细清单和判定边界见 `FORMAL_R0_POSTERIOR_SKIP_AUDIT_CN.md`。

## Clean-source 正式增量复核（全量完成前阶段记录）

执行计划 SHA-256 为
`8804ecb4dd0513db55906905f031832711012974fc911546df40e09fb297d373`。shard 0、5、9
均完成 45/45；shard 8、18 各完成 21/45。D6 新专项不读取原定向聚合，覆盖五个原失败
cell，5/5 均为
`clean_formal_experiment_matrix`，基础与矩阵 formal eligibility 均为 true，generation
contract 为 `verified`，episode/matrix/variant failure reasons 全为空。

五个 cell 分别为 5v5 seed 1000、1005、1008、1018 和 20v20 seed 1009。D1/D2
最终代次分别为 13/13、9/9、13/13、14/14、27/27；skip 均为 0，pending 均为空。
该证据不能外推到其余 172 个已执行 cell。该阶段剩余 723 个 cell，旧正式结论保持
895/900。

新专项测试为 `9 passed, 1 warning in 2.37s`，D6 全量回归为
`1243 passed, 1 warning in 150.38s`。完整输出的 JSON、CSV 和中文报告通过
`SHA256SUMS` 校验。

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

## D4 区域规划链专项（2026-07-29）

### 场景

main 已固化的三维质点规划探针采用 20 个目标、20 个资源和 8 个区域，seed 为 29，时长
3.2 秒。雷达检测概率设为 1.0，声学和视觉关闭。D4 使用测试专用规则建议器；该建议器不是
训练模型。D6 直接读取运行时在线消息，未读取离线真值，episode 的
`online_truth_use_count=0`。

### 正例

source plan v1 有 17 条 assignment 和 3 个未分配目标。D4 advisory-v2 给出
`region-000 -> region-001`、资源数 1 的规划专用 transfer。main 消费记录满足
`consumable=true`、`planning_replan_eligible=true`，execution、assignment、coalition、
takeover 和 control authority 均为 false。

D3 发布不同计划编号的 successor v2。其 assignment 为 18，未分配目标为 2。绑定集合新增
一个真实资源目标关系，并增加一个目标覆盖。审计结果如下：

| 项目 | 结果 |
| --- | --- |
| contract chain available | true |
| planning-only authority safe | true |
| real binding intervention available | true |
| non-degradation | true，描述性 source/successor |
| same-key R0 available | false |
| model benefit available | false |
| safety violations | 0 |

验收门限为合同链无违规、五类执行权限全部关闭、绑定或目标覆盖真实变化、在线真值使用为 0。
本次全部满足。`17 -> 18` 和 `3 -> 2` 只能说明该 episode 的描述性变化。独立同键 R0 未
持久化，建议来源为 rule，不能据此评价 D4 v4 或任何学习模型收益。

### 故障负例

第二个探针使用相同 seed，时长 2.2 秒，在 `t=2.0 s` 注入中心故障。故障帧建议为
advisory-v1，无 transfer、无 planning-only region、无同编号 consumption、无 D3 successor。
在线 payload 通过 `fault_fence_active` 和 `formal_d4_execution_fenced` 拒绝码保留围栏
证据。

D6 输出 `fault_generation_fence_verified`，安全违规为 0。该负例计为安全围栏通过，不进入
模型失败率。它没有形成 assignment 或物理拦截结果。

### 测试与限制

区域规划链定向测试为 `6 passed`，覆盖正例、独立 R0 availability、仅升版伪干预、控制权限
越界、纯故障围栏和“旧未采用尝试后发生故障”时序。D6 全量回归为
`1202 passed, 1 warning in 106.92s`。warning 是既有 Matplotlib `Axes3D` 环境提示。

本次没有运行 AirSim，没有独立同键 R0 episode，没有多 seed 统计，没有注册或执行 D4 v4，
也没有物理拦截结果。下一阶段需要 main 持久化同键 R0 与 learned treatment 的独立 episode，
再交给现有严格学习采纳审计。

## 正式 R0 全量后验审计（2026-07-30）

### 实验范围

本次输入为 clean source `1e5ed8d` 的完整 R0 单臂。执行计划包含 9 个场景、5 个规模、
20 个 seed，共 900 个 cell。每个分片 45 项，20 个分片全部完成。完整父矩阵为 5700 项，
本轮没有执行 G1、A1、A2 或 A3。

### 完整性结果

| 指标 | 结果 |
| --- | ---: |
| canonical cell / episode | 900/900 |
| shard hash | 20/20 |
| cell result / artifact tree | 900/900 |
| clean formal | 900/900 |
| experiment-matrix formal | 900/900 |
| generation verified | 900/900 |
| strict verified | 872/900 |

merged scope 的三项 SHA、900 条 episode index 和 900 行 CSV 均与 execution plan、shard
ledger 和重新计算结果一致。未发现 source、plan、progress、cell result 或 artifact tree
篡改。

### 后验结果

| 指标 | 合计 | 可用项 |
| --- | ---: | ---: |
| D1 generation | 28777 | 900/900 |
| D1 full publication | 28777 | 900/900 |
| D2 final consumed generation | 28777 | 900/900 |
| D2 consumption | 6411 | 900/900 |
| D2 publication | 6411 | 900/900 |
| D2 pre-tick merge | 22366 | 900/900 |
| D2 finalization skip | 0 | 900/900 |
| D2 pending empty | 900 | 900/900 |
| online truth use | 0 | 900/900 |
| forbidden truth field violation | 0 | 900/900 |
| D2 ID switch | 不可用 | 0/900 |

`6411 + 22366 = 28777`，最终代次、发布、消费和节拍前合并闭合。900 项均未使用末尾 skip，
没有 pending 遗留。ID switch 缺少 producer 离线身份配对声明，结果保持不可用。

### 失败分布

28 个失败项全部属于 `high_threat_m_to_n`，原因均为
`d4_fail_closed:collecting_member_acks`。各规模失败数为：

| 规模 | 失败 / 该场景 20 seeds |
| ---: | ---: |
| 5 | 5/20 |
| 20 | 4/20 |
| 50 | 5/20 |
| 100 | 6/20 |
| 200 | 8/20 |

其余 8 个场景均为 `100/100` 严格通过。28 项的 clean formal、实验矩阵资格和 generation
均通过，失败仅表示 D4 联盟在 episode 终点仍等待成员确认。D6 没有更改低层 evaluator。

完整失败 cell、seed 和原因见
[`FORMAL_R0_FULL_POSTERIOR_AUDIT_CN.md`](FORMAL_R0_FULL_POSTERIOR_AUDIT_CN.md)。
专项测试 `19 passed, 1 warning in 2.31s`，全量回归
`1253 passed, 1 warning in 132.38s`。本结果不是 AirSim 或实飞证据，也不支持学习变体收益
结论。

## D3 A1 来源独立 v2 外部审计（2026-07-31）

### 实验范围

D6 对 D3 已完成的来源独立 v2 输出执行一次只读外部审计。输入包含 100 个三维质点 episode、
seed 20000-20099、292 帧匿名 D3 数据和冻结 A1 bundle。数据覆盖 5、20、50、100、200
规模，以及 nominal、密集交叉、编队分裂、机动、延迟噪声、通信退化、中心故障、二级故障
和高威胁 M 对 N 场景。正式 seed 1000-1019 未读取。

审计器未调用 D3 评价器，也未训练、选模、拟合归一化或调整阈值。D3 aggregate 仅用于与
独立复算结果闭合。输入文件在审计前后摘要一致。

### 完整性结果

- 结果目录 5 个合同文件均为普通文件，`SHA256SUMS` 覆盖完整；
- 数据集为 100 个 episode、292 帧，episode 分组 `60/20/20`，帧分组
  `178/57/57`；
- generation source commit 为 `fc7a1c2ec562cdd3ae33ee6e2d6cb2eacc9ab46d`，记录为 clean；
- schedule SHA-256 为
  `468bddc8ccd5932114a1f779e093817a136a67f3c7df07fc458e1e1d5aca1009`；
- 数据集帧 SHA-256 为
  `1568a69e8d93d3357c6cf53f4a416f5083b7cf1f90a33fa0ccc0d0a7ed47d972`；
- 数据集 split SHA-256 独立复算为
  `f1380dd60fded50b2550e5ce63d6d41bb6066022f9e4b201925978acfa025ca5`；
- 数据集路径与 generation root 固定子目录一致；
- CSV 固定 21 列、292 行，与 JSONL 逐行 mismatch 为 0；
- 数据集和评价 JSONL 的禁止真值/实体身份字段、在线真值使用、训练与正式 seed 重叠均为 0；
- 292 个数据集规则矩阵摘要均由 D6 按连续小端双精度字节独立重算并与评价记录闭合。

### 指标结果

| 指标 | 总体 | train | validation | test |
| --- | ---: | ---: | ---: | ---: |
| 帧数 | 292 | 178 | 57 | 57 |
| 正类安全换绑 | 13/110 | 8/65 | 3/20 | 2/25 |
| 正类教师完全匹配 | 8/110 | 5/65 | 3/20 | 0/25 |
| 负类 exact-R0 | 182/182 | 113/113 | 37/37 | 32/32 |
| fallback exact-R0 矩阵/绑定 | 94/94 | 55/55 | 17/17 | 22/22 |

总体安全换绑率为 `11.82%`，教师完全匹配率为 `7.27%`，负类规则保持率为 `100%`。
非零代价修正为 98 帧，投影拒绝为 94 帧，OOD 为 27 帧。拒绝原因可重叠：绑定变化超限
65、规则成本差超限 53、相对成本差超限 6、特征分布外 27。

D6 对 R0、candidate、effective 各独立复算 21637 条选择边。三组的索引越界、资源容量
超额、硬禁边和 M 对 N 原子性违规均为 0，且与逐帧自报计数闭合。版本和规则矩阵突变违规
均为 0。模型 assignment、plan 和 runtime 输出均为 0。预注册总体机器门使用 independent
effective 安全计数并通过。

### 结果边界

test 子组教师完全匹配为 `0/25`，说明该子组没有出现与教师完全一致的有效换绑。合同门限
预注册为总体 292 帧聚合门，本次不增加结果后门限。总体门通过只确认离线输出完整并满足既定
机器门，不确认运行采用、计划效果、控制效果、物理拦截或生产可用性。

正式产物位于
`reports/D3_A1_SOURCE_INDEPENDENT_V2_EXTERNAL_AUDIT_20260731/`。专项测试
`18 passed`，新增 9 个失败关闭负例；D6 全量为
`1348 passed, 1 warning in 139.42s`。本实验不是 AirSim 或实飞证据。

## D1 GlobalTrack A95 物化开发批次（2026-08-01）

输入为 clean source `4166fe8` 的 200 对 200 三维质点 episode，seed 43000-43009，每个
2.0 秒。两臂固定哈希种子和单线程数学库环境，运行顺序按 seed 交替。D6 未运行 episode，
只读取 main 已生成的 reference/candidate 目录。

10 对场景配置、离线真值和传感器观测均等价。运行时总线时序/传输面 10 对均存在差异，主要
包括计划/导引来源摘要和 D4 计划广播传输摘要；D1 GlobalTrack、双时间戳、D2 输入输出和
身份谱系仍为 10/10 精确等价，未出现时序漂移伴随业务分歧。在线真值使用为 0。

reference 标量 A95 为 103609 次。candidate 处理相同 103609 个矩阵，执行 549 次批量构建和
518 次批量特征值调用。候选在 6/10 seeds 墙钟更快；墙钟中位改善为 `1.05%`，D1
`module.d1_fusion` 包含式计时中位改善为 `2.04%`。该阶段还包含扫描更新，不能解释为纯物化
耗时。批次属于开发证据，不支持正式晋级、默认启用、AirSim 性能或实飞结论。
专项测试 `13 passed`，D6 全量回归 `1397 passed, 1 warning in 136.01s`。
