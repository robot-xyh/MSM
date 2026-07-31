# D6 文档索引

2026-07-31 完成 clean commit `b063535` 的高威胁 6-cell 修复后复核。核心合同均为
`6/6`，12 条 D4 建议全部匹配发布时最新代次，旧代发布为 0；四个重规划 cell 均有
最终 v2 建议。clean formal 为 `6/6`，D4 建议代次预准入通过。该 smoke 不含正式矩阵
metadata，不能替代 900-cell targeted/full posterior。详细报告见
`../reports/HIGH_THREAT_CLEAN_SMOKE_B063535_REVALIDATION_20260731_CN.md`；修复前
`49e43ea` 报告保留作对照。原理、审计方法和结果分别见 `MODULE_PRINCIPLES_CN.md`、
`ALGORITHM_AND_IMPLEMENTATION.md` 和 `EXPERIMENT_REPORT.md`。

2026-07-31 完成 v5 高威胁 M 对 N 时期租约复验。100 个开发态 episode 的最终
计划标识、版本、时期、租约和当前联盟闭合均为 `100/100`。151 次权威发布没有同身份
重复，48 次评价刷新不续租。详细报告见
`../reports/HIGH_THREAT_PRECHECK_V5_REVALIDATION_20260730_CN.md`。v4 的时期/租约
availability P1 已在开发证据层关闭。51 项旧建议是 v5 历史批次证据，其运行时断点已由
`b063535` clean smoke 关闭。当前 P1 为正式 900 项重跑、12 项身份指标不可用和大规模
实时性。

2026-07-30 完成高威胁 M 对 N v4 开发态 100 项修复复验。最终计划标识/版本、当前联盟
闭合、有限状态和在线真值零使用均为 `100/100`。151 次权威 D3 发布没有同计划身份重复，
两个摘要错绑原因均为 0。区域时期编号和租约因 D3 缺少对照字段保持
`0/100 available`。结果见 `EXPERIMENT_REPORT.md` 和
`../reports/HIGH_THREAT_PRECHECK_V4_REVALIDATION_20260730_CN.md`，算法见
`ALGORITHM_AND_IMPLEMENTATION.md`，GAP 见
`../../../subagent_reviews/D6_IMPLEMENTATION_GAP_AUDIT.md`。该批次来自 dirty source，
不是 formal 证据。

2026-07-30 新增正式 R0 当前计划绑定审计。D6 以最后 D3 计划为当前代次，逐区域核对
最后 D4 的计划标识、版本及可用的权威 epoch/lease，并对当前多成员联盟执行 ACK 闭合、
原子提交、执行授权和租约检查。旧代 committed、`collecting_acks` 和 `proposed` 均不能
通过。必需联盟由 D3 同目标多资源分配或同代 D4 `commit_required=true` 确定，单成员
`coalition_id` 不触发提交要求。原理、实现和代码就绪记录分别见 `MODULE_PRINCIPLES_CN.md`、
`ALGORITHM_AND_IMPLEMENTATION.md` 和 `EXPERIMENT_REPORT.md`。main runtime 的同代
租约冻结、ACK 重评、有限重发、尾部排空和逐消息处置落盘已经代码就绪，D6 消费合同已
核对。本轮未重跑正式 900 项。

2026-07-29 新增 D4 v5 置信校准候选独立审计。D6 固定 manifest file/content、state、
summary、gate、builder source 和 v4/v3 外部锚，独立重建实际 24 维 latent、TRAIN
标准化状态和 k=11 逆距离评分。固定开发门复算通过；TRAIN self-match 为 350/350，
VALIDATION exact overlap 为 42/75，最近邻标签 75/75 一致。去 exact 后仅余 1 个正类，
独立泛化不可用。D4 报告中的 64 维口径与冻结模型/候选 state 的 24 维不一致。

原理见 `MODULE_PRINCIPLES_CN.md`，算法见 `ALGORITHM_AND_IMPLEMENTATION.md`，结果见
`EXPERIMENT_REPORT.md`，GAP 见
`../../../subagent_reviews/D6_IMPLEMENTATION_GAP_AUDIT.md`。机器可读结果、中文报告和
校验和位于 `../outputs/d4_v5_confidence_candidate_independent_audit_20260729/`。
候选保持 development memorization baseline、未注册、准入关闭和规则回退；未运行 formal
holdout/runtime preflight，未授予 D3/D7 权限。

2026-07-29 新增 D4 v4 未注册候选独立只读审计。固定外部锚为 clean commit
`fd857457bb27a4a709a7c4937e22ebe1cbd7f848`、manifest content
`4f3e973597469d394a594bec3dd7d2c16b24e80d2e97ba45f718d9ef8397e116`、model state
`33a28060f11277a549b90d2f2f365962fec057b2bfb50a70ab5a422059cb9fe5` 和 dataset
`b31fc43f3d3cff34ee53f2b2c33ece0b06d7624e46e26a36c4aa834135e7fb8c`。
候选 180 文件、179 项 artifact SHA、source commit blob、外部 evidence、dataset/split 和
170 个 train/validation episode 均独立复核。test payload read/fit/weight fit、truth
identifier 和 future outcome use 均为 0。

固定 0.60 门的 train/validation 正类召回为 `0.206897/0.307692`，负类特异度均为
`1.0`，Brier 为 `0.186847275/0.186468779`；最小越门裕量
`0.000504935`，保留薄裕量告警。development fixture 仅为
`training_domain_smoke_only`。v3 registry 8 文件树未变，v4 未注册，全部权限 false，
formal holdout/preflight 未完成，admission closed。算法、结果和 GAP 分别见
`ALGORITHM_AND_IMPLEMENTATION.md`、`EXPERIMENT_REPORT.md` 与
`../../../subagent_reviews/D6_IMPLEMENTATION_GAP_AUDIT.md`；机器可读结果位于
`../outputs/d4_v4_candidate_independent_audit_20260729/`。最终 JSON 显式保留未注册、
holdout、preflight、TRAIN-domain fixture、低正类召回、薄越门裕量和 runtime
outcome/benefit unavailable 七项 blocker，状态仍为开发完整性通过、正式准入关闭。
JSON content/file SHA-256 为
`3a4ed311c55e6419d3db1b3ba830f0ea6ce22c638eb363aa03c3f4510fdcd7c2` /
`e225a1a16ae2b1988ce5ea34b3cceaa30d7c829004663368ecc6514de3eb3887`；
Markdown/`SHA256SUMS` 文件 SHA-256 为
`16a2e5a4efacd4b58b22b7b9dd9d0d632cedb3e7b8d6cc6d55a0dce954870fe0` /
`6ee4e7822800401b531acc93f03f105fc1ff02a77c1842fe1d36546bc9500af6`。
专项测试 `3 passed, 1 warning in 4.97s`，
D6 全量 `1205 passed, 1 warning in 112.59s`。

2026-07-28 新增 D4 A2 current-lineage 可信来源、运行分布和严格配对审计。readiness v3
分别输出模型来源验证与运行分布兼容。分布门只检查受审样本、有限记录、feature OOD 和分母
一致性；模型动作、no-op 和规则 fallback 作为独立 rollout 诊断，实际 treatment 继续由严格
采用、ACK、物理窗口和 R0 建立。候选原始字节从受版本控制的 D4 `model_registry` 读取，
不依赖 ignored `outputs/`。D6 确定性合同 fixture 的 5 资源/5 目标、2 区域、6 帧为
6/6 OOD，只用于合同回归。main 真实预检另为 5v5/2 区域 seed 2000 的 3/3 OOD 和
200v200/8 区域 seed 2001 的 2/2 OOD。分布内 no-op 回归通过分布门，但采用和配对收益
unavailable。算法、结果和 GAP 分别见 `ALGORITHM_AND_IMPLEMENTATION.md`、
`EXPERIMENT_REPORT.md` 与 `../../../subagent_reviews/D6_IMPLEMENTATION_GAP_AUDIT.md`。
定向测试 `38 passed`，D6 全量 `1144 passed`，全部权限为 false。

2026-07-28 新增 G1 `model_source` 可信适配器。reference 只列 13 项正式 D5 v5、external
audit v2、post-assembly audit v2、held-out、paired-shadow、lineage 和校验清单的相对路径
与 SHA-256；D6 复哈希原制品并重跑两级严格审计。显式外部根
`/tmp/MSM-d5-g1-formal-evidence-8d5e02e-20260727` 的只读正例通过，仓库根因原制品缺失
继续 unavailable，且不会自动发现 `/tmp`。该段形成 frozen seed 与 G1 model-source 两类
adapter；本次顶部新增 A2 固定来源 adapter。G1 其余八门和 A1/A3 来源仍不可用，所有权限
保持 false。算法、结果和
GAP 分别见 `ALGORITHM_AND_IMPLEMENTATION.md`、`EXPERIMENT_REPORT.md` 与
`../../../subagent_reviews/D6_IMPLEMENTATION_GAP_AUDIT.md`。D6 全量回归为
`1138 passed, 1 warning in 126.65s`。

2026-07-27 正式学习运行准备度聚合器见 `MODULE_PRINCIPLES_CN.md` 和
`ALGORITHM_AND_IMPLEMENTATION.md`。该入口统一审计 G1/A1/A2/A3/C1/F1 的模型来源、冻结未见
seed、可辨识采用、运行 ACK、物理窗口、唯一同键 R0、成对非退化、truth-use、有限状态和外部
权限。v2 manifest 的每个 gate 只引用相对源制品路径和文件 SHA-256；D6 校验路径、实际文件
摘要后，只把已登记 adapter 的既有 producer schema 送入原严格 auditor。该日仅接入
canonical seed gate，其余九类 gate unavailable；十类旧通用 wrapper 均不再受信。
18 个临时 producer/攻击/命令行测试已通过，没有启动正式矩阵或 AirSim。六个变体的 formal
readiness 当前全部 unavailable。证据和 blocker 见 `EXPERIMENT_REPORT.md`。

2026-07-27 A1/A2/A3 实际采用与同键配对审计的证据阶段、可用性和权限边界见
`MODULE_PRINCIPLES_CN.md`，输入 v1/v2 迁移、旧记录/新 pair 分派、四级重算、A3 disposition
完整分母和跨 episode 日志绑定见 `ALGORITHM_AND_IMPLEMENTATION.md`。A2 已兼容真实 D4
input/batch/public validator；A3 同时调用 D5 paired-evidence 与 pairing-disposition 公共
validator。当前 v4 输出在 v3 候选阶段细分基础上增加候选观测结果清单，分别记录普通轨迹帧、
已处理零检测帧、locked/ambiguous/hold/reacquire 和分配目标覆盖率。合法 unpairable 保留原因，但 A3
执行/收益计数 unavailable，完整模型证据声明及全部权限为 false。D5 disposition v1 只保留
顶层原因，细分计入 unresolved；旧 strict input v1 的 disposition inventory 明确
unavailable。零检测帧有中心分配目标时只能形成 reacquire 和 0 覆盖，无分配目标时结果保持
unavailable；两种情况都不能产生 locked/ambiguous 或运行权限。当前 strict audit 专项为
`64 passed, 1 warning in 11.79s`，纯导入及干净
子进程输出复载通过，main A3 paired smoke 为 `1 passed, 1 warning in 3.29s`。当前 D6 全量
回归为 `1106 passed, 1 warning in 100.94s`。此前
`paired_learning_adoption 5 passed`、scalable `345 passed, 1 warning`、cross-module
`8 passed` 和 D6 全量 `1093 passed, 1 warning in 98.33s` 均为 v3 修改前的冻结历史证据。
本次没有新增 AirSim 或性能实验结论。

main 的 seeds 1000-1019 开发批次已由当前 v2 consumer 消费。A2 为 20/20 候选评估、0 个
可识别区域干预、0 个实际采用和 0 个 A2/R0 收益审计，原因均为
`identifiable_regional_intervention_missing`；批次 SHA-256 为
`ff3c10a089b6a94582451ae05d8a884af3a2bd7485acd4df0496442ea7e0ec55`。A3 为 536 条
disposition，其中 152 条 pairable、384 条 unpairable，覆盖率 28.36%，不可配对原因均为
`candidate_physical_window_missing`；批次 SHA-256 为
`455d181076553a485ff824618abc6d037a4477bb6342877d1d1e427fd28583a9`。完整清单下
`a3_auditable_pair_count=0`，四级计数 unavailable，pairable 子集不构成完整模型证据。该
冻结批次没有 D5 v2 候选阶段证据，其自身仍保留粗粒度原因。

main 后续完成同配置 seeds 1000-1019 的不落盘开发探针。536/536 个候选有 stage evidence，
细分为匿名观测缺失 `344` 和物理窗口确认缺失 `344`。另 40 条 observation inventory 不完整，
但 stage reason 为空；D6 将其保留为 unresolved，不记录
`candidate_physical_window_incomplete`。物理窗口缺失细分 scope/evidenced/unresolved 为
`384/344/40`，completeness 为 `false`。ACK、运行确认、命令过期、时序错配和相机反馈缺失均为
`0`。152 条 pairable、384 条 unpairable，完整可审计 seed 仍为 `0`。非正式摘要 SHA-256 为
`1ba6040e7c3e7e3b9e7d5506dfd20cf3539ce12c5aac13cca7f02799f0cd99ef`。该摘要保持
`source_worktree_clean=false`、`formal_evidence=false`、
`persisted_full_pair_inventory=false`，只用于开发诊断，不替换冻结批次或开放指标和权限。

同配置第二次开发复跑在 D5 v2 零检测帧和 main truth-free 帧事件接线后得到 492 个候选、
488 个可配对、4 个不可配对，覆盖率 99.18699%。329 个零检测帧全部计为 reacquire，159 个
v1 帧计为 locked；零检测帧 locked/ambiguous 为 0。4 个缺失来自默认 1% 通信丢包，对应
4 个 seed 关闭丢包后全部配对。该批次未持久化完整逐候选清单、来源工作树不干净，不能替换
旧 536/152/384 冻结结果，也不能证明未见 seed、正收益或运行授权。

A2 旧记录还区分投影前候选拒绝和投影后安全采用拒绝。合法
`safe_adoption_rejected` 只确认实际采用数为 0；拒绝原因缺失、投影字段篡改或携带后继计划、
运行确认、联盟执行证据和物理窗口时失败关闭。该状态不生成物理窗口、R0 或收益计数。

2026-07-27 D5 G1 正式 v5 证据链已同步到 `MODULE_PRINCIPLES_CN.md`、
`ALGORITHM_AND_IMPLEMENTATION.md` 和 `EXPERIMENT_REPORT.md`。clean commit
`8d5e02ec...b54` 上的 external audit v2 与 post-assembly v2 均为 `pass`、blocker 为空；
生产 v5 manifest SHA-256 为 `b431d066...f317d`，paired lineage 为 900 条记录和 900 个
唯一 UID。六项权限保持 false，真实相机、中心 binding 和物理闭环证据继续 unavailable。

2026-07-26 D5 v5 生产装配正向复核已同步到 `MODULE_PRINCIPLES_CN.md`、
`ALGORITHM_AND_IMPLEMENTATION.md` 和 `EXPERIMENT_REPORT.md`。D6 测试直接调用 D5 公共
`assemble_tracklet_g1_bundle()` 生成 v5，再由 D5 严格加载器和 D6 post-assembly v2
连续验证。实际七文件布局、900/900 lineage、准入报告 lineage 三字段、六权限、external
audit 双哈希和运行实现摘要全部通过；生产产物 lineage 篡改和缺失均失败关闭。最新回归为
external `14 passed`、post-assembly `55 passed`、D6 全量 `1042 passed`。

2026-07-26 D5 G1 审计版本治理修正见 `MODULE_PRINCIPLES_CN.md`、
`ALGORITHM_AND_IMPLEMENTATION.md` 和 `EXPERIMENT_REPORT.md`。external audit 主输出已升为
`d6.d5-g1-external-audit.v2`；post-assembly 的 input/output/consumer/profile 均升为 v2，
只接受 `d5.tracklet-model-bundle.v5`、admission report v2、authority contract v2 和
external audit v2。旧 `/tmp/...-v2` 目录内部仍是 audit v1，已标记为版本审查否决的过渡制品
`rejected_transition_schema_v1`，不得用于新装配。该段所列待运行项已由上方 2026-07-27
正式证据链关闭。

2026-07-26 D5 跨视角候选图几何校准见 `MODULE_PRINCIPLES_CN.md`、
`ALGORITHM_AND_IMPLEMENTATION.md` 和 `EXPERIMENT_REPORT.md`。该工具只评价 finalized
dataset 中的几何候选边，不评价 G1 边概率、阈值或聚类收益。R0/G1 配对要求 manifest 绑定的
显式 frame-index sidecar，禁止使用 `episode_id`。当前完成合成合同验证，专项 `12 passed`、
D6 全量 `1022 passed`；真实校准 dataset 尚未生成。

2026-07-26 D5 G1 预准入外部审计及装配器后软件谱系复核见
`MODULE_PRINCIPLES_CN.md`、`ALGORITHM_AND_IMPLEMENTATION.md` 和 `EXPERIMENT_REPORT.md`。
D6 与 D5 当前运行时摘要均为十文件规范摘要 `41381db3...4b07`。同一 99fa 历史证据复核仍为
`fail_closed`：旧证据缺 assembler 哈希，`tracklet_model_bundle.py` 不一致，原鲁棒性和单特征
阻断保持不变。该复核没有运行新 episode；新旧审计分别保存在独立输出目录。

2026-07-25 正式 R0/G1/A1/A2/A3/C1/F1 矩阵准入预检原理见
`MODULE_PRINCIPLES_CN.md`，expected inventory、模型 SHA、逐 cell 证据、压缩缺失范围和
`pre_run/post_run` 实现见 `ALGORITHM_AND_IMPLEMENTATION.md`。当前实际 formal 计划动态得到
5700 个 cell。静态 `post_run` 结果为 `fail_closed`：矩阵 manifest 缺失，四个现有学习模型
哈希有效但 assist 均未准入。专门实验记录见 `EXPERIMENT_REPORT.md`，机器制品见
`../outputs/formal_matrix_admission_precheck_20260725_current/`。本入口未运行大矩阵。
不带 `--inventory` 的 CLI 结果 expected=0 只表示缺输入，不能替代上述 5700-cell 结果。

2026-07-25 D1 在线发布证据子集快照评估原理见 `MODULE_PRINCIPLES_CN.md`，严格来源绑定、
五表面实现身份、D1/D2 在线记录比较、快照计数守恒、配对统计和失败关闭实现见
`ALGORITHM_AND_IMPLEMENTATION.md`。入口绑定 matrix SHA
`6c808c4df8759fd893c6d37ff9dce4a1efa07f9867fc71aff47a55c5f8517338` 与 clean commit
`d0219eb14c529a4fb9bf7d6610a9f32055a09206`。正式 13 pair/26 fresh arm 已完成，0 reused、
0 failed；13/13 语义和诊断合同通过，返回记录削减 `91.641524%`。short 更快数、D1 改善和
bootstrap 上界三个门失败，正式 verdict 为 `reject`；最低实时因子 `0.203423`。正式结果见
`../EXPERIMENT_REPORT.md` 2.39 节和
`../outputs/d1_publication_evidence_snapshot_multiseed_20260725_formal_d0219eb_d6/`。
同一 manifest 重复评估逐文件一致；聚焦测试 `14 passed`，D6 全量 `880 passed, 1 warning`。

2026-07-25 D1 固定滞后回放前缀摘要独立评估原理见 `MODULE_PRINCIPLES_CN.md`，严格
manifest/matrix/commit 绑定、导出前后 ledger 守恒、在线 consistency digest、原操作计数、
性能门和投影工作量披露见 `ALGORITHM_AND_IMPLEMENTATION.md`。入口 schema 为
`d6.d1_replay_prefix_summary_multiseed_evaluation.v1`，冻结 matrix SHA
`85432d729877eff97e6f3dd517d4baa7a47f44a4fa42e6bfdc7ce85b8d9ec74b` 与 producer commit
`7d2e987471b521a1e531bf03a5c99af5096f676a`。正式 13 pair/26 fresh episode 已完成，
0 reused、0 failed；规模为 200 个目标、200 个资源和 2 个侦察节点。13/13 业务语义、
consistency digest/count、D1 原操作计数、实现身份、诊断守恒和真值隔离通过。内部物化减少
`52.150746%`，但 short 更快数、short D1、short bootstrap、short core 和 long core 五个门
失败，正式 verdict 为 `reject`。候选保持默认关闭；最低实时因子 `0.197441`，系统实时缺口
未关闭。正式结果见 `../EXPERIMENT_REPORT.md` 2.38 节和
`../outputs/d1_replay_prefix_summary_multiseed_20260725_formal_7d2e987_d6/`。校验和通过，
同 manifest 重跑输出 SHA-256 一致。结果仅为三维质点证据。

2026-07-25 D1 在线批帧交接同提交多 seed 正式评估原理见
`MODULE_PRINCIPLES_CN.md`，严格 manifest/matrix/provenance 绑定、四层 selector/诊断谱系、
批帧守恒、计划语义归一化和冻结门实现见 `ALGORITHM_AND_IMPLEMENTATION.md`。入口 schema 为
`d6.d1_online_batch_frame_multiseed_evaluation.v1`，固定 matrix SHA
`4afbf9ac273763a16aa01cc744fd67b52e437099460b33377a128f986ac5719b` 与 clean commit
`43feaf600f288a85ce76a76862334256f0d0d352`。正式 13 对/26 episode 全部可用；
scan input short/long 改善 `38.289241%/36.275282%`，core wall 改善
`4.252745%/4.916501%`，D2 增幅 `2.113047%/2.830616%`，重复检查减少率和 closed ratio
均为 `100%`，fallback 为 0，结论 `admit`。候选最低实时因子 `0.204490`，系统实时仍不足。
结果仅为三维质点，不是 AirSim、实机或实飞证据。正式结果见 `../EXPERIMENT_REPORT.md`
2.36 节和 `../outputs/d1_online_batch_frame_multiseed_20260725_formal_43feaf6_d6/`。

2026-07-25 D1 不透明来源标识缓存多 seed 评估原理见
`MODULE_PRINCIPLES_CN.md`，严格证据绑定、诊断守恒、语义比较和冻结门实现见
`ALGORITHM_AND_IMPLEMENTATION.md`。入口绑定 matrix SHA
`218d04f3fc4a764fef82de612c78c8fbb5490380ae5d20aff6b9089635f2060d` 与 clean producer
commit `d8fc76c066f21b077154f7be33c0b43558d237e5`，固定 13 pair、26 fresh arm 和
200/200/2。正式 26 arm 全部 fresh complete，0 reused、0 failed；13/13 业务语义、真值隔离、
实现身份和缓存审计通过。short/long D1 融合改善 `9.465972%/6.437432%`，标识构造减少率和
命中率均为 `99.163670%`。long D2 组均值增幅 `5.605213%` 超过 5% 门，
`optimization_admitted=false`；最低实时因子 `0.193887`，
`system_realtime_gap_closed=false`。结果仅适用于显式来源键、hold=false 的三维质点矩阵。
正式结果见 `../EXPERIMENT_REPORT.md` 2.35 节和
`../outputs/d1_opaque_source_identity_cache_multiseed_20260725_formal_d8fc76c_d6/`。聚焦测试
`16 passed, 1 warning`，D6 全量 `834 passed, 1 warning`。

2026-07-25 D1 结构化数值雅可比多 seed 评估原理见
`MODULE_PRINCIPLES_CN.md`，证据绑定、四表面诊断、操作数守恒、统计门和不可用处理见
`ALGORITHM_AND_IMPLEMENTATION.md`。入口绑定 matrix SHA
`c6c3cf53c89dfb3155a29ba49bb77a12c8bdf1a5d433c4f645de0d00c506d478` 与 clean producer
commit `9d1f54f8540fdc4a7a1011121aafac5718290122`，固定 13 pair、26 fresh arm 和
200/200/2。evaluator、CLI、完整 JSON、compact JSON、逐 pair CSV、中文 Markdown 和
`SHA256SUMS` 已实现。main 已完成正式评估：26/26 fresh complete、0 reused、0 failed，
`availability=true`、`optimization_admitted=true`、`system_realtime_gap_closed=false`。
短时 D1 融合/核心改善 `6.084778%/1.897370%`，长时改善
`4.676061%/1.786530%`，量测函数求值减少 `53.846154%`。main 已将 scalable 3D 默认晋级为
`known_dimension_structural_columns_v1`，并保留 `dense_output_probe_v1` 显式回退；D6 评估
保持独立，D1 独立 `FusionAdapter` 默认不变。scalable 测试及 2v2 默认 smoke 已通过，三处表面
记录候选、有限状态为 true、在线真值使用为 0。结果只覆盖三维质点冻结矩阵，系统实时 P1 继续开放。
专项为 `20 passed, 1 warning in 6.05s`，D6 全量为
`818 passed, 1 warning in 55.42s`。工具状态见 `../EXPERIMENT_REPORT.md` 2.34 节。

2026-07-24 在线真值递归检查多 seed 评估原理见 `MODULE_PRINCIPLES_CN.md`，严格 evidence
绑定、消息检查数守恒、语义比较、统计和准入实现见 `ALGORITHM_AND_IMPLEMENTATION.md`。入口
绑定 matrix SHA
`764574b9897d00101c26c555de2f407e1736c7e6ff50420eebf131e154618dc8` 与 clean source
`8d8bb6ed7a417705236835f235361f45a021bb2b`，固定 13 pair、26 fresh arm 和
200/200/2。正式 26 arm 已全部完成，0 reused、0 failed；13/13 pair 业务语义、真值隔离、
实现身份和检查数守恒通过。short/long 发布总线及收尾改善 `22.58%/25.63%`，但 long 核心墙钟
回退 `3.47%`，long D1/D2 分别增加 `5.29%/7.34%`。因此
`optimization_admitted=false`，默认仍为 `generic_recursive_v1`；最低实时因子
`0.165369`，`system_realtime_gap_closed=false`。结果见 `../EXPERIMENT_REPORT.md` 2.33 节和
`../outputs/online_truth_guard_multiseed_20260724_formal_8d8bb6e/`。balanced-order v2
仅保留为可选诊断，不覆盖正式 v1 结论。本次同步后 D6 全量为
`798 passed, 1 warning in 52.01s`。

2026-07-24 D1 常速度模型缓存多 seed 评估原理和边界见
`MODULE_PRINCIPLES_CN.md`，严格消费、守恒公式、统计和报告实现见
`ALGORITHM_AND_IMPLEMENTATION.md`。入口绑定 matrix SHA
`9898656598f0fa282620afe2384a3d656b7496f8957109c413bcb62069fd2e9a` 与 clean source
`44223566439a446fc49f2a3fd861d1d51bd676b9`，固定 short 10 pair、long 3 pair、
200/200/2 和容量 128。D6 内部生成跨 episode 语义比较，不依赖 producer 预写 pair report。
正式 26-arm evidence 已全部 fresh complete，0 reused、0 failed；13/13 pair 合同与 19/19
准入门通过。short/long D1 融合改善 `6.9271%/6.6103%`，核心墙钟改善
`2.4060%/2.4537%`，构造减少率和命中率均为 `99.5960%`，
`d1_optimization_admitted=true`。最低实时因子为 `0.17394990897894075`，
`system_realtime_gap_closed=false`。正式结果见 `../EXPERIMENT_REPORT.md` 2.32 节和
`../outputs/d1_cv_motion_model_cache_multiseed_20260724_formal_4422356/`。结论只覆盖三维质点
矩阵，不覆盖 AirSim、目标硬件、传感器精度或实飞。本次同步后 D6 全量回归为
`784 passed, 1 warning in 55.02s`。

2026-07-24 D1 协方差优化多 seed 与长时入口见 `MODULE_PRINCIPLES_CN.md` 和
`ALGORITHM_AND_IMPLEMENTATION.md`，fixture 验证见根目录 `../EXPERIMENT_REPORT.md` 2.28 节。
入口预注册 short `1101-1110 @ 2.2 s` 和 long `1101-1103 @ 10.0 s`，显式绑定 13 个 A/B pair，
输出分组统计、10000 次确定性 paired bootstrap 和同 seed 单位时间增长率。completed
`evidence_manifest.json` loader 会精确核对内嵌矩阵、13 个 case、arm 状态/提交/返回码、固定
runtime profile 和证据路径，并与 `--pair` 输入互斥。loader 按 experiment ID 严格支持已登记的
v1/v2/v3：v2 绑定 effective/base commits、公共 D2 修复和 v1 输出复用边界；v3 再绑定共同 D1
半正定修复、reference 标量 treatment、v2 输出复用边界和两臂向量化标志。旧 `14/11` 已知虚警
映射计数仍被 D6 失败关闭。main 已完成正式 v3 manifest。分组统计现显式区分越低越好和越高越好，
保留原始相对变化、`candidate_lower_count` 和 bootstrap，新增方向、候选更优数及正向改善值。
实时因子 short/long 修正为 `10/10`、`3/3` 候选更优；该展示修复不改变正式 evidence 或准入判定。
固定 bundle 现新增 `d1_covariance_limit_multiseed_long_improvements.png`：上半图为 13 个显式
seed 的 D1 融合配对改善，下半图为 short/long 五项方向化均值改善。实时因子按越高越好，其余
绘制指标按越低越好；RSS 只保留在图外审计。缺 pair、缺指标、方向不一致或非有限值时不生成图，
CLI `outputs` 返回 `png` 路径。专项 `69 passed`，D6 全量 `719 passed, 1 warning`。

2026-07-24 D1 协方差成对限制向量化准入原则和门控公式见
`MODULE_PRINCIPLES_CN.md`、`ALGORITHM_AND_IMPLEMENTATION.md`，三轮 clean 结果见根目录
`../EXPERIMENT_REPORT.md` 2.27 节。显式 pair 入口复用 scalable 3D reader，并独立读取 GNU
`time -v` 资源层；机器 JSON、逐轮 CSV 和中文报告位于
`../outputs/d1_covariance_limit_clean_pair_20260724/`。D1 fusion wall 均值下降 `10.4411%`，
P95 均值下降 `5.9154%`，优化准入通过；候选实时因子均值 `0.215065`，系统实时、多 seed、
AirSim 和精度 P1 保持开放。CSV 固定使用 LF 且无 CR；专项 `9 passed`，D6 全量为
`646 passed, 1 warning`。

2026-07-24 D1 原子影子旁路兼容原理与字段约束见
`MODULE_PRINCIPLES_CN.md`、`ALGORITHM_AND_IMPLEMENTATION.md`，确定性结果见根目录
`../EXPERIMENT_REPORT.md` 2.26 节。D6 保留历史 uninstrumented/prepared-handle v1，同时仅在
显式 atomic mode 下解释准备、操作后完整性、物化、工作量和失败摘要。专项 `25 passed`，D6 全量
`637 passed, 1 warning`。clean commit `7cc2d0c` 的 seed 1100 atomic rejected-only pair 已只读
复核：9/9 integrity 通过、46/46 rejected、atomic failure/materialized 为 `0/0`，业务非干预
通过；相对墙钟开销为 `0.8117989190825889`，性能门和 overall admission 仍为 false。真实
accepted 和 atomic failure episode 尚未提供。

2026-07-23 D1 质心发布影子旁路的评估原则和实现见
`MODULE_PRINCIPLES_CN.md`、`ALGORITHM_AND_IMPLEMENTATION.md`，真实 seed 1100 开发期复核见根目录
`../EXPERIMENT_REPORT.md` 2.25 节。D6 只读消费 A2 sidecar、最终诊断和阶段时序，分别报告业务
非干预、`+5%` 性能门和处理效果。prepared seed 1100 的业务非干预通过，性能相对开销比为
`0.808828677`，accepted treatment 为 0，`overall_admitted=false`。该证据为 dirty 单 seed
描述性结果。本轮 D6 全量为
`623 passed, 1 warning in 21.67s`。

2026-07-23 observation truth v2 消费见 `MODULE_PRINCIPLES_CN.md` 和
`ALGORITHM_AND_IMPLEMENTATION.md`，验证见根目录 `../EXPERIMENT_REPORT.md` 2.24 节。D6 接受
external/D2 normalized v1/v2，v2 分别报告 target、known false alarm、unknown 和 missing
disposition；v1 的非目标计数保持 unavailable。known false alarm 不进入目标身份，unknown 关闭
strict IDSW，D6 不执行推断或回填。本轮 D6 全量为 `586 passed, 1 warning`，scalable
learning export 为 `5 passed, 1 warning`。

2026-07-22 的 `scalable3d-stage-timings-v2` 离线消费见
`MODULE_PRINCIPLES_CN.md` 和 `ALGORITHM_AND_IMPLEMENTATION.md`，接口验证见根目录
`../EXPERIMENT_REPORT.md` 2.23 节。D6 v7 严格核对分位值与显式 availability，legacy 缺失保持
null，跨 seed 只统计各 episode 内调用分位，不生成 pooled quantile。2026-07-23 当前权威全量回归
为 `567 passed, 1 warning in 22.96s`；相较 555 项新增的 12 项来自部分身份合同的 3 项独立测试
和 9 项篡改参数化用例。当前仍需 main 生成带 v2 分位和冻结稳定窗口定义的 clean 200 对 200
多 seed 输入；本次不改变 AirSim 接线。

2026-07-22 clean commit `0d2da25` 的 nominal 200 对 200、10.0 s、seed `1000-1019`
runtime v2 复核见 `MODULE_PRINCIPLES_CN.md`、`ALGORITHM_AND_IMPLEMENTATION.md` 和根目录
`../EXPERIMENT_REPORT.md` 2.22 节。20/20 episode 的后验代次合同、pending 排空、基础来源门和
在线真值隔离通过；D3 覆盖率均值为 `0.989606`，D5 绑定数均值为 `25.95`，5 m 接近为 0。全部证据
仍是 `descriptive_clean_source_calibration`，实验矩阵 episode 为 0。本批关闭 clean 未见
20-seed 代次合同输入缺口，不形成正式算法矩阵或物理拦截结论。

2026-07-22 的 D1-D2 后验代次被动审计见 `MODULE_PRINCIPLES_CN.md` 和
`ALGORITHM_AND_IMPLEMENTATION.md`，接口验证见根目录 `../EXPERIMENT_REPORT.md` 2.21 节。
runtime v2 核对 D1 完整后验连续代次、D2 来源代次唯一递增、先发布后引用、最终 pending 排空、
consumed 等于 D1，以及消费数加合并数等于 D1；runtime v1 保持 unavailable。D1/D5 独立性能 JSON
只登记为描述性证据，不升级为全栈实时能力。专项 `58 passed`，D6 全量
`542 passed, 1 warning`。AirSim 接口未改变。

同日 main 已提供 clean commit `0d2da25` 的 nominal 200 对 200、10.0 s、三 seed runtime v2
episode。三次后验代次完整性、基础 formal provenance gate、pending 排空和在线真值隔离均通过，
失败原因空。输出见 `../outputs/scalable3d_posterior_v2_clean_0d2da25_20260722/`。该证据是三 seed
描述性 clean 校准，是后续 20-seed 复核前的首批正例；该目录本身没有实验矩阵 metadata。v6
报告日期已修正并重生成为 `2026-07-22`。

2026-07-22 nominal 200 对 200、10.0 s、seed `42000/42001/42002` 的 clean 长时集成校准见
`MODULE_PRINCIPLES_CN.md`、`ALGORITHM_AND_IMPLEMENTATION.md` 和根目录 `../EXPERIMENT_REPORT.md`
2.20 节。reference 为 `8f86192`，candidate 为 `f80b5bd`。三 seed 的有限状态、在线真值隔离和跨提交
业务语义审计均通过；进程总墙钟均值下降 12.31%，峰值常驻内存下降 18.33%。candidate 写盘后处理
均值为 `40.639988 s`，但 reference 缺相同计时制品，不能做单阶段归因。该批仍是三 seed 描述性
clean-source calibration，不关闭 20 未见 seed、实时性、实验矩阵或物理拦截 P1。文档同步后 D6
全量回归为 `530 passed, 1 warning`；warning 为既有 Matplotlib `Axes3D` 环境问题。

2026-07-22 runtime plan outcome join 的严格等价性能优化见
`MODULE_PRINCIPLES_CN.md` 和 `ALGORITHM_AND_IMPLEMENTATION.md`，固定 3380 条 development A/B 结果见
`../EXPERIMENT_REPORT.md` 2.19 节。实现对全部在线记录继续执行真值键审计，只在审计后最小化留存，
并对 D2 identity 建立一次只读索引。baseline/candidate 报告、业务 JSON 和写盘摘要不变；独立入口
没有跳过真值检查的布尔参数。该结果不改变 AirSim 接线、admission 或物理证据层级。

`OBSERVATION_GOVERNANCE_CALIBRATION_CONTRACT_CN.md` 定义长 episode D1 扫描 OOSM、D2
claim ledger、evaluator-only sidecar、哈希链和 main required fields 的公共合同。
2026-07-22 clean/formal 快速治理结果见 `../EXPERIMENT_REPORT.md` 2.17 节。该批采用
`formal_only`，覆盖 20 episode/20 seed，绑定 clean 提交
`e4d66db02a0b8f1b867a0e81b4a73de84588426b`，online truth use 为 0。正式证据只覆盖治理
合同，不包含精度、AirSim、实时性或物理拦截验收。
2026-07-22 的 development 快速治理基准与 200 对 200 全栈单 seed 冒烟见
`../EXPERIMENT_REPORT.md` 2.16 节；两类证据的隔离原则见 `MODULE_PRINCIPLES_CN.md`，读取和
availability 算法见 `ALGORITHM_AND_IMPLEMENTATION.md`。快速基准覆盖四档各 5 seed，全栈冒烟
仅覆盖 2.2 s 单 seed；两者均不能替代 clean formal 多 seed 精度与物理闭环验收。

2026-07-22 D2 重复航迹治理后的 `active_risk` 开发期复跑证据见
`MODULE_PRINCIPLES_CN.md`、`ALGORITHM_AND_IMPLEMENTATION.md` 和 `../EXPERIMENT_REPORT.md` 2.14 节。
20 个 seed 的计划消费、导引血缘、物理窗、D4 adoption、配对差值、非退化和降级配对比较均为
20/20 可用；D4 区域采用合计 `188/188`，两臂各有 `1960` 条实际 world 命令，seed 1005 的 5 条
D2 航迹离线映射完整且 online truth use 为 0。该批为脏工作树 development rerun；两臂 5 m 成功均
为 0，production runtime ACK、counterfactual 和 causal 仍不可用，不替换下方此前 clean formal
19/20 历史证据。

2026-07-22 新增隔离双臂多周期物理评估合同。证据分层、真值隔离和结论边界见
`MODULE_PRINCIPLES_CN.md`；D3 计划消费、D7 world application、5 m 物理窗、差值和非退化算法见
`ALGORITHM_AND_IMPLEMENTATION.md`。同一合同现支持显式、可选且经 spec/manifest 双重 SHA-256 绑定的
D4 区域采用文件，区分 `not_declared`、名义 `not_applicable`、完整采用和部分区域不可用，并仅在全部
必要证据完整时输出描述性降级配对物理比较。已写入但未被 verdict 准入的 ACK 仍独立审计；其存在不
提升 adoption availability。接口验证见 `../EXPERIMENT_REPORT.md` 2.13 节；专项 `24 passed`、D6 全量
`507 passed`，main 20 seed producer 集成专项 `1 passed`。`active_risk` 20-seed 只读复跑已通过，但
D4 adoption/降级比较为 0/20 available，物理窗为 19/20。当前结果不能解释为正式降级收益、反事实或
因果结论。

2026-07-22 已将 D3/D4 保留 seed consumer 升级为 v1/v2 严格分派。历史 v1 保持兼容；新 v2 独立
复核 D3 safety-shell 40 arm、20/20 treatment application、同帧 assignment cost/safety/churn，以及
D4 arm-evidence-v2 的 confidence/OOD/latency/finite/failure 分门和 manifest 汇总。仅 offline
assignment comparison 可用；runtime ACK、physical outcome/effect、counterfactual 和 causal 仍为
null/unavailable。算法见 `ALGORITHM_AND_IMPLEMENTATION.md`，边界见 `MODULE_PRINCIPLES_CN.md`，
结果见 `../EXPERIMENT_REPORT.md` 2.12 节。CLI profile 已绑定预期源 schema；测试内 v2 fixture 使
clean clone 仍覆盖成功与关键篡改路径。当前 canonical 使用独立 profile-bound v2 目录；固定时间戳
四文件可逐字节复生，sidecar/provenance 均记录 source schema。专项 `18 passed`、无权威输出路径
`16 passed`、D6 全量 `483 passed`。历史 v1 文件保留为旧 provenance，不把旧哈希写成当前可复生
哈希。已检查 `../AIRSIM_INTEGRATION_PLAN.md`；本次无 AirSim 接线变化，因此未修改。

2026-07-22 已完成 D5 paired-shadow 权威 v2 独立审计。D6 显式绑定 v2 report/lineage、held-out
corpus/evaluation、模型包、D5 实现源码和保留的 superseded 证据，复核 2718 项输入且审计前后哈希
一致。900 条 lineage、20 seed、45 cell、74024 条候选边、graph/candidate/label identity、逐 seed/cell
汇总和零安全违规均闭合。paired-shadow=`complete`，但三类运动/尺度特征近确定性可分，最强特征只在
35/45 cell 达到门限；外部泛化证据为 `synthetic_only_insufficient_for_external_generalization`。
G1/PPO/assist/authority 均为 false，规则回退保持 true。算法见 `ALGORITHM_AND_IMPLEMENTATION.md`，
证据边界见 `MODULE_PRINCIPLES_CN.md`，实测结果见 `../EXPERIMENT_REPORT.md` 顶部。
专项测试 `8 passed`，D6 全量测试 `465 passed`；仅有既有 Matplotlib `Axes3D` 导入警告。

2026-07-21 已接入 D5 held-out report/corpus 的严格只读消费者。输入 v2 要求两项制品成对显式提供，
v1 只兼容无 held-out；D6 校验文件/内容 SHA、20 seed×45 cell×1 帧、model weights/config、冻结
validation 温度/阈值和身份/真值/权限零违规。指标通过只完成 held-out 层，paired shadow 仍独立阻断
G1/assist/authority。该段是权威 v2 生成前的接口状态，专项合成合同测试不代表正式结果；当前状态
以上一段独立审计为准。本次不修改 AirSim 接线。原理、实现和证据边界分别见
`MODULE_PRINCIPLES_CN.md`、`ALGORITHM_AND_IMPLEMENTATION.md` 和 `../EXPERIMENT_REPORT.md` 2.9 节。

2026-07-21 已新增运行时计划确认到离线观测结果的严格联接。D6 显式校验 11 类输入及 SHA-256，复核
D3/D7 source sequence 与 payload SHA，只使用 D2 source-observation lineage 映射身份，并按同资源相邻
ACK 建立非重叠三维状态窗。有界配对进展仅作诊断，正式 reward、因果/反事实和三类学习权限保持
unavailable/false。合法同版本评估刷新按 ACK sequence/时间戳形成独立 occurrence；同版本执行签名
漂移失败关闭。专项 `22 passed`、D6 全量 `423 passed`；真实 main 3v3 回归形成 2 个 occurrence、6 个
绑定窗口。原理见 `MODULE_PRINCIPLES_CN.md`，实现见 `ALGORITHM_AND_IMPLEMENTATION.md`，接口证据见
`../EXPERIMENT_REPORT.md` 2.7 节。该改动不修改 AirSim 接线和冻结训练数据。

2026-07-21 已完成 D3、D4、D5 producer 全样本联合准入。D6 显式接收三份审计路径和带外文件 SHA-256，
独立复算 file/content SHA，核对 schema、完整计数、expected/actual binding、canonical 60/20/20、零
违规、availability 和 admission。三模块及跨模块 structural full-sample=`complete`，overall
admission=`partial`；PPO、assist、authority 均为 false，规则回退为 true。专项 `37 passed`，正式
输出及哈希见 `../EXPERIMENT_REPORT.md` 2.6 节。本次未修改 AirSim 接线。

2026-07-21 已接入 detached canonical numeric-seed split 只读审计。D6 独立校验共享 registry 的 schema、
policy、内容/assignment/source SHA-256、100 个训练 seed 和 `1000-1019` 保留 seed 隔离，并比较 D3、
D4、D5 图数据和 D5 主动视觉 manifest。正式结果为 D3 exact；D4、D5 graph、D5 active 分别有
51、65、62 个 mismatch seed，联合训练 unavailable。算法和空值口径见
`ALGORITHM_AND_IMPLEMENTATION.md`，治理原则见 `MODULE_PRINCIPLES_CN.md`，正式统计见
`../EXPERIMENT_REPORT.md`。2026-07-21 D6 全量 `364 passed`；本次不改变 AirSim 接线。

2026-07-20 已接入正式学习数据标签只读审计和 detached sidecar 合同。D4/D5 的 outcome、reward、
counterfactual、causal label 分层、运行确认硬门、保留 seed `1000-1019`、全量 SHA-256、原子发布和
确定性复用见 `MODULE_PRINCIPLES_CN.md` 与 `ALGORITHM_AND_IMPLEMENTATION.md`。正式 900 episode
审计确认 D4/D5 reward 均为 0 条可用，D5 runtime ACK 为 0；行为克隆只在模块内可准备，PPO 不可用。
D4/D5 split 有 423/900 个 episode 不一致，联合训练保持 unavailable。2026-07-21 标签专项
`17 passed`、D6 全量 `351 passed`；本轮未启动 AirSim，未修改 AirSim 计划或实验报告。

2026-07-20 已接入 scalable 3D 算法实验矩阵离线审计。D6 v5 从配置 metadata 读取
R0/G1/A1/A2/A3/C1/F1，核对 learning runtime 与实际采用证据，按固定 cell 分母和 variant 汇总，并在
完整 R0 配对上输出 delta/bootstrap CI。专项 `34 passed`、D6 全量 `314 passed`；clean/formal 与
dirty development 分开，正式矩阵尚未运行。
原理见 `MODULE_PRINCIPLES_CN.md`，实现见 `ALGORITHM_AND_IMPLEMENTATION.md`，接口验收见
`../EXPERIMENT_REPORT.md` 2.4 节。

2026-07-20 已同步 scalable 3D schema registry 窄修复。D6 offline v4 固定核对当前 world/bus/scenario/
online observation/offline truth 和 config schema；真实 online observation 名称为
`scalable3d-observation-v1`。原始值继续展示，旧、未知、篡改或缺失值不能进入 formal acceptance。
专项 `32 passed`、D6 全量 `304 passed`。原理见 `MODULE_PRINCIPLES_CN.md`，实现见
`ALGORITHM_AND_IMPLEMENTATION.md`，验证见 `../EXPERIMENT_REPORT.md` 2.3 节。

2026-07-20 已同步 scalable 3D 主动视觉离线 consumer v3。新增
`modules.d5.active_vision` 与 `runtime.camera_command_ack` 的规则/影子/辅助采用、issued/applied/
rejected、复合版本键关联、ACK latency、拒绝原因、D2 中心航迹只读引用和 truth-like 字段审计。缺
日志保持 null/unavailable；同 episode 的 assist applied 与五米接近不形成物理归因。主动视觉专项
8 项、合并 scalable 专项 `25 passed`、D6 全量 `297 passed`；上述 fixture 未启动 runtime/AirSim。
原理见 `MODULE_PRINCIPLES_CN.md`，字段与算法见 `ALGORITHM_AND_IMPLEMENTATION.md`，测试证据见
`../EXPERIMENT_REPORT.md` 2.2 节。

同日另以当前 main runtime 运行 6v6/recon1/camera7、seed 37、2.2 s 临时 smoke。D6 读取 133 条规则
命令和 133 条 applied ACK，零拒绝、零中心航迹引用违规、零 truth 字段违规；summary 一致。该输入为
dirty 单 seed，只用于接线检查。

2026-07-20 已同步 scalable 3D 学习运行时离线 consumer v2。稳定入口仍是
`../scripts/run_scalable_3d_offline_evaluation.py`；新增 D3/D4/D5 bundle/fallback/fingerprint/version
availability 与 `modules.d4.region_resource_advice` 的 mode、assist、fallback、latency、quota 守恒、
projection、formal mutation 和 stale/missing version 审计。报告严格区分 bundle loaded、shadow
output、assist gate、control adoption 和 physical outcome；advice 不改变正式 D4 裁决，独立 main
消费合同和 D3 hint applied 才能证明控制采用。聚合按显式规模和不同 seed，单 seed 仅 descriptive；
正式 evidence 要求 `repository_dirty=false`。deterministic scalable 专项 `17 passed`、D6 全量
`289 passed`；未运行真实 scalable 3D/AirSim，也未形成模型验收。算法见
`ALGORITHM_AND_IMPLEMENTATION.md`，原则见 `MODULE_PRINCIPLES_CN.md`，验证边界见
`../EXPERIMENT_REPORT.md` 顶部。

2026-07-15 已同步 legacy 1.0 provenance 兼容与真实三档报告。fallback 只在路径输入且 suite/cases/
rows 全无显式 ClockSpeed 时读取 20/20 sibling generated settings；不猜目录名、不默认 1.0，缺文件/
缺键/冲突/非法值 fail closed。真实 1.0/0.2/0.1 共 60 case、20 个跨档配对，合同 56 match/4
mismatch，truth identity/state 全 0；candidate 0.1/0.2 的受影响 aggregate unavailable。输出见
`../../airsim_runtime/outputs/m5n2_clock_speed_comparison_20260715/`。ClockSpeed 专项 `18 passed`、D6
全量 `272 passed`，源组合 hash 前后不变。

2026-07-15 已同步 0.1 P1 NameError 紧急回归：timing mode helper 前置并统一命名；新增 20-case 双层
case-aware evaluator 测试。真实 0.1 两层各 4036 records/20 case 的 P1 v6 只读报告生成成功，输入
hash 不变。timing 专项 `28 passed`、D6 全量 `264 passed`。该段记录紧急修复当时状态；真实三档
comparator 随后已完成，见顶部同步项。

2026-07-15 已同步 case-aware merged suite timing 与真实 ClockSpeed=0.2 证据。P1 v6 显式区分
`single_episode/case_aware_suite`，后者只接受四个 case metadata、逐 case 单调并允许边界重置；两层
各 6567 records/20 case 的只读复测通过，禁止跨 case 伪连续和 main/control 相加。ClockSpeed
comparator v2 冻结 M5N2 每 case `3/2/1`，真实 0.2 审计为 18 match/2 mismatch（candidate seed006/
seed009）；reserve 成功不计 active-primary。该 0.2 阶段专项 `27/10 passed`、当时全量
`263 passed`。真实 0.1 P1 状态见顶部，不预写三档结论。

2026-07-15 已同步 M5N2 ClockSpeed=`1.0/0.2/0.1` 三档离线比较接口。每档强制
baseline/candidate 各 seed 1-10，并按 `case_id/profile/seed` 跨档配对；ClockSpeed 来自 suite/case
persisted provenance，不从目录名推断。报告覆盖三层物理结果、第二 primary、最终锁/共识、
collision stop、独立 wall timing、归一化 simulated time/tick 和 truth identity/state availability。
确定性 fixture 为三档各 20 case、总计 60 case，专项 `8 passed`、D6 全量 `254 passed`。
运行前接口记录已由本页顶部更新：真实 0.2/0.1 均已完成 P1 复核；算法见 `ALGORITHM_AND_IMPLEMENTATION.md`，
接线见 `../AIRSIM_INTEGRATION_PLAN.md`，测试证据见 `../EXPERIMENT_REPORT.md` 1.7 节。

2026-07-15 已同步真实 AirSim M5N2 20-case 复核。baseline/candidate 各 10 seed；actual execution
为 `20/20` available，正式物理 pair/target/coalition=`12/60`、`12/40`、`0/20`，在线 truth
identity/state 均为 0。第二 primary 七阶段分母全部 available，但 5 m physical=`0/20`。两层
timing 各 3805 samples，main-bus/control-tick mean=`349.34/1069.45 ms`，禁止相加。partial
acceptance 的正式 timing 接线仍 unavailable。M5N2 完成后、`TERM` 生效前额外完成的 `png_ttc`
seed001 明确排除在 20-case 聚合与验收之外；其余 tuned 2v2 和全部 dropout 未执行，缺失 case 不补零。
`12/40` 固定表示“至少一个 participating pair 成功”的 canonical target physical success；全部
required member 通过阶段只称 cooperative target-stage diagnostic。第二 primary `20/20` 最终为
`collision_stop`，但 collision object 未写盘，原因对象保持 unavailable。
详细结果见 `../EXPERIMENT_REPORT.md`，接线缺口见 `../AIRSIM_INTEGRATION_PLAN.md`，算法和证据边界
见 `ALGORITHM_AND_IMPLEMENTATION.md` 与 `MODULE_PRINCIPLES_CN.md`。

2026-07-15 已同步 `d6-cooperative-closure-v3`：第二 primary 七阶段漏斗、pair/target/coalition 独立
物理分母、coalition completion 和首失败原因 availability 已写入模块原理、算法、AirSim 计划与
实验报告。确定性专项 `11 passed`、D6 全量 `246 passed`；该代码批次未启动 AirSim，后续 M5N2
20-case 结果以本页首段和实验报告 1.6 节为准。

2026-07-15 已同步两层分阶段延迟能力：模块原理说明嵌套域与 availability，算法文档说明严格
校验、P95、预算和 dominant stage；模块根目录 AirSim 计划与实验报告记录接入和测试证据。代码
可观测性已闭合；M5N2 20-case 已确认预算不达标，正式 case-aware 接线已关闭，优化复验仍为 P1。

2026-07-14 actual target-state freshness/stale 正式指标链已关闭：canonical v2 强制消费最终
command 的六个 freshness 字段，formal validator 从 SHA256 已验证 CSV 复算，case/pooled
aggregate/CSV/JSON/中文 Markdown 均已接入。最新真实 2v2/M5N2 为 48/608 samples，stale 均 0，
source 均为 `d2_estimated_global_track`；pooled 656 samples。D6 全量 `216 passed`。详细算法见
`ALGORITHM_AND_IMPLEMENTATION.md`，AirSim 生产约束见 `../AIRSIM_INTEGRATION_PLAN.md`，真实数值见
`../EXPERIMENT_REPORT.md`。随后 20-case 已补齐 10389 条同配置 freshness 样本；跨提交趋势和
failure taxonomy 仍为 P1。

2026-07-14 最新真实证据状态：tuned 2v2 seed-1 与 M5N2 seed-1 的 canonical
`d7-actual-execution-metrics-v2` 均可用，required/available/unavailable=`2/2/0`；旧
physical-count conflict 未复现并关闭。M5N2 pair/target/coalition=`2/3`、`2/2`、available
`0/1`，显式 coalition 失败不能由 target 成功替代。统一报告 overall=false 是因为 2 个 seed-1
case 不构成 baseline/candidate、1-5 帧 dropout 和 multi-seed 的完整 P1 矩阵。2v2/M5N2 loop
latency=`123.3/384.6 ms`，budget violations=`19/212`、合计 `231`，保持 P1。此次只同步文档，
未改 D6 代码。

2026-07-14 actual SimpleFlight execution evidence 已形成 v2 builder/writer、计划身份 provenance
和 fail-closed validator；plan/version 逐行必填，owner 只对 effective-authorized 的
secondary/distributed active/execution/reassignment 或显式 execute action 行必填。中心授权或
未授权 pending 可无 owner；整集没有 authoritative owner 时 provenance 为 `unavailable`。merge
v3 只发布 validated actual metadata，不从 replay 推断。接口见
模块 `README.md`，证据分层原理见 `MODULE_PRINCIPLES_CN.md`，字段来源和实现见
`ALGORITHM_AND_IMPLEMENTATION.md`，AirSim 生产顺序见根目录 `AIRSIM_INTEGRATION_PLAN.md`，最新
两组 M5N2 审计见根目录 `EXPERIMENT_REPORT.md`。此前 owner-provenance 专项为
execution-evidence focused `20 passed`、当时 D6 全量 `184 passed`；该代码级阶段没有运行真实
AirSim，随后完成的两条真实 seed-1 证据以本页首段为准。
代码级 P0 与本批 actual seed-1 写盘注册门均已关闭；完整 P1 矩阵和性能门仍开放。

本目录保存 D6 的详细设计和实现状态文档。D6 的长期边界是离线评估：只消费日志，不参与 D1-D7 控制链路。

2026-07-15 D2 准入 schema 兼容与正式证据均已同步：统一 system-evidence v2 支持 D2 v2 gates、
legacy structured/bool checks，并结构化保留 source promotion/path、逐 difficulty、truth alignment
和 JPDA research-only 状态。正式 D2-only bundle 位于
`../outputs/p1_identity_ceiling_aware_v2_20260715/`；其他六源 unavailable、全系统判决未评估。
实验文档记录专项 `31 passed`、D6 全量 `243 passed`；本批未启动 AirSim。

先前 case-wiring 状态（2026-07-14）：terminal suite `d6-p1-unified-acceptance-v2`、
`d6-terminal-metric-envelope-v1` 和逐 case evidence aggregation 已实现并通过 D6 全量
`159 passed`。现有 seed-1 suite 的 D3 为 4/4 case、543 records；D7 原 main row 路径仍全部
未注册并明确 fail-closed。公开 registration helper、逐 case/seed JSON/CSV/Markdown 和缺文件/
schema mismatch 回归已同步到下列文档；main runtime 的 D7 路径登记与正式 suite 重生成仍开放。

| 文档 | 位置 | 说明 |
|---|---|---|
| 模块 README | `../README.md` | 当前能力、规模归一化、AirSim/D4/D5/D7 离线入口、测试命令和 API 示例 |
| 模块计划 | `../PLAN.md` | 已实现、部分实现、未实现、main runtime 接线缺口、P1/P2 下一步 |
| AirSim 离线集成计划 | `../AIRSIM_INTEGRATION_PLAN.md` | Blocks JSONL、D4/D5/D7 AirSim 产物回灌、PNG 策略和未实现 replay 项 |
| 算法原理与当前实现 | `ALGORITHM_AND_IMPLEMENTATION.md` | 指标公式、数据模型、`EpisodeMetrics` 字段、D4/D5/D7 gate、开源 benchmark 缺口 |
| 示例实验报告 | `../EXPERIMENT_REPORT.md` | 批量示例报告和图表引用；不是代码或在线控制输出 |

核心规则：

- `id_switch_count` 是 D2/D6 强制显式指标。
- truth-to-track pair 缺失时 `track_rmse/track_continuity/id_switch_count` 为
  `None/unavailable`；完整 identity history 的零切换是 available `0`。JSON/CSV/Markdown、
  loader、merge 和 batch reporting 必须保留该区别。
- 2026-07-14 五场景 truth tracking 回归已关闭假零 P0，D6 全量 `137 passed`；真实
  seed/provenance 完整性和 D2 lifecycle-D3 churn join 仍为 P1。
- 指标按实际 `drone_count/resource_count/target_count/camera_count` 分组和归一化，不从 `2v2/5v5` 场景名推断。
- D7 guidance records 通过 `guidance_records.csv` / `guidance_summaries.json` loader 转为 `EventRecord` metadata；D6 只做离线 gate/intercept 统计，不提供在线导引控制通道。
- 2026-07-07 起，main/orchestrator 已把 D7 真实执行指标合并进正式 `main_episode_bus_metrics.json`，并把执行前合同检查保留为 `main_episode_bus_contract_metrics.json`；D6 仍只消费这些写盘产物。
- 2026-07-08 起，main runtime P1 calibration sweep 已自动调用 D6 `AirSimCalibrationReportGenerator.write_report_bundle()`，输出 AirSim calibration records/summary/Markdown；报告字段覆盖 coverage、projection/gate、stable registration、`not_registered_count`、active degradation review label 和 D7 guidance reject reason。
- PNG 截图不是默认指标输入；bbox、相机参数、timestamp、ID 和 gate metadata 才是指标主线。
- py-motmetrics 已作为隔离式 P2 benchmark 输出 IDF1/MOTA/MOTP，HOTA unavailable；Stone Soup、OSPA/GOSPA、TrackEval、AirSim 原生 recording replay 和 SCRIMMAGE bridge 仍是未实现的可选项，live AirSim replay/API 仍是禁止在线控制项。

2026-07-20 新增 `../d6_evaluation_metrics/truth_isolated_offline.py`。该文件是三维规模化
D1/D2 公共离线制品入口，提供 DTO/哈希文件适配、episode/batch 记录和逐 seed CSV、聚合
JSON、中文 Markdown 输出。算法边界见 `ALGORITHM_AND_IMPLEMENTATION.md` 第 17 节，原则
与证据边界见 `MODULE_PRINCIPLES_CN.md` 第 11 节，AirSim/main 写盘要求见
`../AIRSIM_INTEGRATION_PLAN.md` 第 11 节。文件模式强制校验制品 SHA-256 和 D2 四类来源
摘要，零帧/无 truth-frame 不得产生 available IDSW=0。D1 规范字段为
`d2_lineage_mapping`，旧 `canonical_mapping` 仅输入兼容且冲突 fail-closed。专项
`14 passed`、D6 全量 `334 passed`；本轮只验证合同和报告，不代表正式多 seed 性能达标。

2026-07-23 已同步 D2 evaluator-only partial identity diagnostics。实现位于
`../d6_evaluation_metrics/truth_isolated_offline.py`；原则见
`MODULE_PRINCIPLES_CN.md` 第 12 节，字段校验和聚合公式见
`ALGORITHM_AND_IMPLEMENTATION.md` 第 18 节，合同测试结果见
`../EXPERIMENT_REPORT.md` 第 10 节。D6 现在把 mapping/frame/adjacent-transition coverage、
conservative IDSW lower bound、anchor interval 和 exclusion reasons 与 strict IDSW 分栏输出，
并校验 identity manifest、evaluation SHA、四类 source hash、audit/config、有限值和计数守恒。
旧 evaluation 缺块保持兼容；partial 失败只标 unavailable，不回填 strict、不构造 upper bound、
不参与控制。专项 `26 passed`、D6 全量 `567 passed, 1 warning in 22.96s`。D6 已补充读取 clean
`4ac3bb2` 的 200 对 200、seed 1000、10 秒真实 producer episode：manifest/evaluation 和四项
来源 SHA 全部匹配；strict IDSW 因 `multiple_truth_targets_for_global_track` 保持 unavailable，
partial mapping/frame/transition coverage 为 `8906/9038`、`3/48`、`0/9400`，lower bound 为
7/385 anchor intervals。该单 seed 结果只证明真实制品接入；本批无 AirSim 或正式多 seed
性能证据。

2026-07-23 已同步 D2 identity commitment evaluation v2。实现仍位于
`../d6_evaluation_metrics/truth_isolated_offline.py`，原则见
`MODULE_PRINCIPLES_CN.md` 第 13 节，校验与聚合公式见
`ALGORITHM_AND_IMPLEMENTATION.md` 第 19 节，main/AirSim 写盘要求见
`../AIRSIM_INTEGRATION_PLAN.md` 第 12 节，合同测试结果见
`../EXPERIMENT_REPORT.md` 第 11～12 节。D6 对 v2 内嵌 evidence bundle 做 SHA-256 复算并验证
commitment denominator、coverage、reason、watermark、overflow 和零 binding violation；
v1 commitment 保持 unavailable。逐 seed CSV、aggregate JSON 和中文报告把 strict IDSW、
commitment coverage、partial diagnostics 分栏。runtime join 命中显式 uncommitted 时只关闭
对应 binding，不回填 truth。D6 全量为 `598 passed, 1 warning in 21.44s`。

clean commit `909669b2…` 的 seed 1100 A/B 已实际持久化 v2 evaluation/audit。baseline
strict IDSW/track continuity/coverage continuity 为 `9/0.865/0.870`。candidate
commitment coverage 为 `1714/1787=0.9591494124`，69 条 hold、4 条 after hold，两个
binding violation 为 0；但三个恢复航迹超出固定 `0.9 s` lineage window，strict identity
metrics unavailable，D2/D3 数量由 `203/200` 降至 `201/197`。候选准入失败，seed
1101/1102 停止。该验证不是 AirSim，真实 AirSim 仍未执行。

2026-07-23 已完成 clean commit `65568579...` 的发布新鲜度 A/B 独立复核。最新算法说明见
`ALGORITHM_AND_IMPLEMENTATION.md` 第 20 节，原则见 `MODULE_PRINCIPLES_CN.md` 第 14 节，
实验数值见 `../EXPERIMENT_REPORT.md` 第 13 节，后续写盘要求见
`../AIRSIM_INTEGRATION_PLAN.md` 第 13 节。baseline/candidate strict IDSW 均 available，
为 `9/3`；candidate 的 3 条 publication-stale recovery 被失败关闭，零绑定违规。

本轮修复 D6 对 partial unavailable 分类的绑定：producer audit 的
`unavailable+excluded+uncommitted` 对应 partial 的合并 unavailable。修复后两组 partial
provenance 均可用，lower bound 为 `9/3`，未回填 strict。D6 全量为
`600 passed, 1 warning in 21.55s`。候选因 D2/D3 数量和 continuity 退化仍不准入；该轮旧
制品未持久化 recovery config v2 完整快照。consumer 的关闭状态见下段。

2026-07-23 已完成 manifest v2 配置谱系 consumer。算法说明见
`ALGORITHM_AND_IMPLEMENTATION.md` 第 21 节，原则见 `MODULE_PRINCIPLES_CN.md` 第 15 节，
接口与状态见 `../README.md` 和 `../PLAN.md`。D6 现验证配置规范 SHA、manifest/online
records 来源摘要、逐帧配置一致性和记录数，并在 episode JSON、CSV、batch provenance 与
runtime admission 中暴露结果。

历史 manifest v1 的 strict/partial 指标保持兼容，配置谱系单独显示不可用。manifest v2
异常在 runtime join 中 fail closed。专项 `83 passed`，全量
`611 passed, 1 warning in 21.55s`。随后 detached clean `ff881316...` 的 seed 1100
baseline/candidate 已完成最终三维质点 A/B。两组 manifest v2 均绑定相同配置 SHA，9 条
在线 D2 发布逐条一致；D6 episode/runtime provenance 均验证通过。配置谱系 P1 已关闭。
旧制品缺配置快照的记录不改写，AirSim 尚未执行。候选因 D2/D3 数量与 continuity 退化保持
默认关闭，结构歧义保活算法准入 P1 仍开放。

2026-07-23 新增
[`IDENTITY_GATE_CLEAN_SEED_1100_AUDIT_CN.md`](IDENTITY_GATE_CLEAN_SEED_1100_AUDIT_CN.md)。
该报告审计 clean `7e15dac9...` 的 hold-only/hold-plus-centroid 同输入单 seed 制品，记录
truth-isolated 与 runtime-plan-outcome 确定性重建、D3 计划强制升版、11 个未承诺目标的
D3/D5/D7 零继续执行，以及质心候选 `46/0/46` 的零 treatment 边界。本轮不是 AirSim、
多 seed 或算法晋级证据。

2026-07-25 新增
[`FORMAL_R0_POSTERIOR_SKIP_AUDIT_CN.md`](FORMAL_R0_POSTERIOR_SKIP_AUDIT_CN.md)。
该报告复核正式 R0 的 900 个 episode，确认 895 个 clean-formal、5 个 delayed-noisy
后验未消费。D6 v10 核对逐轨状态、协方差、有效时刻和航迹状态，并要求上游提供版本化完整
D2 输入摘要；公开载荷相等本身不足以认可 no-op skip。当前 5 项继续失败关闭，并登记 main
运行时输入签名遗漏为 P0。本次没有修改 AirSim 接口或控制模块。

同日 main 修复 finalization 后完成五项定向重跑。D6 v10 确认五项 skip 均为 0，D1/D2 最终
代次一致，消费与发布一致，消费加节拍前合并等于 D1 代次，pending 为空。该批工作树 dirty，
因此只形成开发态修复证据。D6 v10 已提交为 `8e955f3`，runtime 修复已形成 clean source
commit `98d01bf`。正式 R0 在全量完成前阶段执行至 177/900。2026-07-30
新增
[`FORMAL_R0_TARGETED_POSTERIOR_AUDIT_1E5ED8D_CN.md`](FORMAL_R0_TARGETED_POSTERIOR_AUDIT_1E5ED8D_CN.md)，
不读取原定向聚合，独立复核五个原失败 cell。五项均为 clean-formal、实验矩阵 formal 和
generation verified。该段保留增量阶段结论；当前完整结论见下一段全量审计报告。

2026-07-30 新增
[`FORMAL_R0_FULL_POSTERIOR_AUDIT_CN.md`](FORMAL_R0_FULL_POSTERIOR_AUDIT_CN.md)。
该报告覆盖 clean source `1e5ed8d` 的完整 900-cell R0 单臂，独立核对 20 个分片、900 个
cell result 和 artifact tree，并逐项重算 D1/D2 后验代次。clean formal、实验矩阵资格和
generation verified 均为 900/900；严格总门为 872/900。28 项均为高威胁 M 对 N 场景在
episode 结束时仍处于 D4 成员 ACK 收集状态。完整父矩阵和学习变体对照尚未完成。
