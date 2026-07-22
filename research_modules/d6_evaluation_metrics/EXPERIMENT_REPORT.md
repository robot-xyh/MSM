# D6 系统级评估指标实验报告

## 2.14 2026-07-22 D2 修复后 active_risk 开发期复跑

### 输入与完整性

本批读取 main 在脏工作树生成的临时结果目录 `/tmp/msm_active_risk_d2_fix_20260722/`，覆盖 seed
`1000-1019` 共 20 对 control/treatment 隔离续跑。结果目录没有复制到仓库。根 `SHA256SUMS` 的 447
个成员全部通过，D6 输出目录中的 sidecar、中文报告和 provenance manifest 三项摘要也全部通过。
manifest 声明 `production_runtime_ack=false`、`counterfactual_available=false`、
`causal_available=false`。

文档同步后运行 D6 全量测试，结果为 `507 passed, 1 warning`。warning 是既有 Matplotlib `Axes3D`
环境问题，不影响本次 JSON、JSONL、Markdown 和 SHA-256 核验。

### 证据覆盖

| 证据层 | 可用 seed | 总 seed | 结论边界 |
| --- | ---: | ---: | --- |
| 计划消费 | 20 | 20 | 隔离仿真消费，不是生产确认 |
| 导引血缘 | 20 | 20 | 命令与计划、资源、航迹和 world application 闭合 |
| 物理窗 | 20 | 20 | 1 s 窗口可计算 |
| D4 区域采用 | 20 | 20 | 两臂区域证据完整 |
| 配对物理差值 | 20 | 20 | 描述性差值可计算 |
| 配对非退化 | 20 | 20 | 20/20 通过，不表示拦截成功 |
| 降级配对比较 | 20 | 20 | 描述性隔离比较 |
| 反事实 | 0 | 20 | unavailable/null |
| 因果 | 0 | 20 | unavailable/null |

D4 adoption 在 control 和 treatment 中分别为 `94/94`，合计 `188/188`。两臂分别生成并实际写入
`1960` 条控制命令。20 个 seed 共形成 100 条离线身份映射。seed 1005 的 control 文件包含
`GT3D-000001...GT3D-000005` 到 `TGT-0001...TGT-0005` 的 5 条唯一映射，状态均为
`unique_lineage_verified`；`online_truth_isolation_verified=true`，online truth use 为 0。

### 结果解释

control 和 treatment 的 5 m 成功数均为 0，成功绑定数均为 0，平均最近距离相同；成功数、最近距离、
硬约束和错误绑定的 treatment-control 差值均为 0。20/20 对通过非退化判据，表示 treatment 在当前
1 s 描述性窗口内未比 control 更差。由于两臂都没有 5 m 成功，time-to-5m 及其差值不可用。

本批关闭的是 D2 重复航迹修复后的开发期证据完整性断点。它没有给出拦截性能提升，也不支持降级策略
有效性、生产运行确认、反事实或因果结论。该结果不得覆盖本报告下方此前 clean formal `19/20` 的历史
证据。后续正式发布仍需在冻结提交和 clean worktree 上复跑并保存可保留制品。

## 2.13 2026-07-22 隔离双臂物理评估接口验证

本轮完成 D6 消费合同和 main 生产路径接线验证，没有发布正式降级策略性能实验。基础合成 fixture 使用
1 个 seed、1 个资源、2 个目标和两套隔离 world，包含两个 D7 控制周期。完整路径中 control 与
treatment 均有 1 个唯一目标进入 5 m；treatment 的平均最近距离相对 control 减少 1 m，到达 5 m 时间
差为 -0.5 s，硬约束和错误绑定差值均为 0。这些数值只用于断言计算公式和序列化结果。

D4 扩展把每臂可选 `d4_adoption_evidence.jsonl` 纳入输入清单、arm manifest 和只读摘要链。有效降级
记录按区域核对 source/applied plan、场景血缘、候选门、隔离计划消费确认和 adoption verdict。部分
区域不可用时仍输出 region count、available count、原因分布和 intervention kind，但
`degraded_paired_physical_comparison` 为 null。名义空文件标记为 not applicable；旧输入未声明该文件
时继续兼容，且不会从相邻目录自动发现证据。

专项共 24 项并全部通过。新增覆盖有效 D4 记录、部分区域不可用、名义空文件、旧输入、保留但未被
verdict 准入的 ACK、声明文件缺失、SHA 篡改、spec/manifest 声明不一致、arm/region/seed/plan/ACK
篡改、available 状态矛盾和 production runtime ACK 冒充；既有缺 D7 证据、跨臂初态和命令血缘测试
继续通过。D6 全量为 `507 passed`，仅有既有 Matplotlib `Axes3D` warning。main 20 seed producer 的
集成专项另为 `1 passed`。

同日使用 main 生成的 `active_risk` seed `1000-1019` 输入做只读复跑。输入清单带外 SHA-256 为
`f13a35ac732353cd037ea0daf45d5c4946feba2a23520b6426471387dd9c1f19`。20/20 对计划消费和导引血缘
可用，物理窗及一般配对物理差值为 19/20，故聚合物理
差值和聚合非退化不可用。control 与 treatment 各有 98 条区域记录，可用 adoption 均为 0；两臂合计
`isolated_execution_plan_not_strictly_new` 188 条，`degraded_scenario_evidence_invalid` 8 条。D6 正常
生成报告，没有再因未准入 ACK 的 verdict `ack_id=null` 异常退出。20/20 对的 D4 adoption 与降级配对
比较均 unavailable，counterfactual 和 causal 仍为 null/unavailable。该复跑关闭消费者兼容缺口，未
关闭上游新计划身份、完整物理窗或降级效果证据缺口。

`d4_degraded_adoption` 只表示隔离世界采用证据完整。两臂 D4、计划消费、导引血缘和物理窗全部可用时，
D6 才输出描述性的 `degraded_paired_physical_comparison`。该结果仍属于 paired isolated simulation
comparison。counterfactual 和 causal 始终为 null/unavailable，隔离 ACK 不称为生产运行确认。正式
验收仍需 clean、冻结、可保留的多 seed 降级场景和预先定义的识别假设；当前结果不能用于模型 promotion、
PPO、assist、authority、物理非退化或降级因果收益声明。

## 2.12 2026-07-22 D3/D4 保留 seed v2 独立审计

### 输入、合同与独立重算

权威输入为
`research_modules/scalable_3d_simulation/outputs/reserved_seed_interventions_nominal_5v5_1000_1019_formal_7891296/`，
场景为 nominal 5 资源/5 目标、seed `1000-1019`。源提交必须为
`78912963b67fe86ee9a8d29186b18a9dd60c460c`；`SHA256SUMS`/manifest SHA-256 必须为
`821f15035e628d8db86f13c22d93f8e05142c5f00aae9118974a74bdc98b72bc` /
`d6ef23b28add92e9a24a185ea72a7275e341bd796a2e11930c4d5f46b19a883c`。D6 从底层 lineage、arm、
receipt 和 gate evidence 重算汇总，不信任 producer 聚合替代明细；六个输入文件审计前后 SHA 不变。

20 条 lineage 精确覆盖 seed `1000-1019`，dirty、nonfinite、online truth use 均为 0；同源 episode、
传感器随机流、通信日程和故障日程均为 20/20。D3/D4 各 40 arm，control/treatment 均为 20/20，
pair input、lineage 和 bundle identity 均通过。D3/D4 bundle manifest/state 延续冻结绑定：D3 为
`a9213d65...14c0` / `e3da9fd5...e0b2`，D4 为 `dad2adbe...05c9` / `3da0360b...5f62`。

### 结果与 availability

| 模块/指标 | 独立重算结果 | 解释 |
| --- | --- | --- |
| D3 safety shell | v2/config SHA，40/40 arm | 严格绑定 |
| D3 treatment | applied 20/20；fallback 0/20 | 隔离 assignment 层应用 |
| D3 control 状态 | unchanged 15；held 3；replan ACK no change 2 | receipt available |
| D3 assignment cost | rule/treatment=`17.0560260319065/17.0560260319065` | 同帧规则 cost 基准 |
| D3 safety/churn | high-threat unmet、duplicate、hard、churn 均 0/0 | offline comparison available |
| D3 inference | P95(linear)=`0.3108014891040515 ms` | 执行诊断，不是物理效果 |
| D4 considered | 20/20 | arm evidence v2 |
| D4 confidence gate | 0/20 pass | low-confidence 20/20 |
| D4 OOD/latency/finite/failure | 各 20/20 pass | 分门明细与 manifest 一致 |
| D4 aggregate/adoption/fallback | 0/20；0/20；20/20 | 全部规则回退 |
| D4 treatment latency P95 | nearest-rank=`2.241314999992028 ms` | `treatment_candidate_latency_ms` |
| D4 gate latency P95 | linear interpolation=`2.264414849923924 ms` | `candidate_gate_summary.candidate_latency_ms` |
| runtime ACK / physical outcome | 无 | unavailable/null |
| counterfactual / causal | 无 | unavailable/null |
| paired physical outcome/effect/non-degradation | 无 | unavailable/null，不填 0 |

sidecar 状态为 `pass_offline_assignment_comparison_only`。D3 的同帧 assignment comparison 可用，只说明
在冻结规则 cost/safety/churn 口径下未观察到退化；没有 runtime ACK 或采用后的物理状态窗，不能据此
声明候选策略有效、物理非退化、反事实或因果收益。D4 的零采用也不等于效果为 0。本次 nominal 5v5
只验证门控和回退，不是通信、节点或资源降级下的策略评估。

### 输出与验收

profile-bound canonical 输出目录为
`research_modules/d6_evaluation_metrics/outputs/reserved_seed_interventions_nominal_5v5_1000_1019_formal_7891296_d6_profile_bound_v2_audit_20260722/`，
审计时间 `2026-07-22T04:56:47Z`。

| 文件 | SHA-256 |
| --- | --- |
| `outcome_availability_sidecar.json` | `f3852251daf02ec87fe878e7fb80aad6f381d8c0756a5c956a32e737a3871c3b` |
| `RESERVED_SEED_INTERVENTION_AUDIT_CN.md` | `bd80c1dda496d7d43e2b274628fdbe3a5ef8a4b99c8c354562ba2149b70f9949` |
| `provenance_manifest.json` | `0d50a95daf098bdc732a7d3344ef8340d7fc1828a2df7b971b40313db23f7dc6` |
| `SHA256SUMS` | `db4af357cbf087b20b28f5c3bcc775b98d711f996bb3040aac0b45ca5ae7b87c` |

sidecar 内容 SHA-256 为
`c02a345c46ddc642dea7fb6bfcfb24184e7dc2a9f35b754c90324d074b445d2d`。sidecar 与 provenance 均记录
`source_manifest_schema_version=scalable3d-reserved-seed-interventions-v2`。同一 source 和时间戳经 CLI
写入临时目录后，四文件与 canonical 逐字节一致，两个目录的 `sha256sum -c` 均通过。专项
`18 passed`、无权威输出路径 `16 passed`、D6 全量 `483 passed`；仅有既有 Matplotlib `Axes3D`
warning。

## 2.11 2026-07-21 D3/D4 保留 seed 隔离执行独立审计

### 场景、输入与接受门限

本次 D6 审计时间为 `2026-07-22T04:06:26Z`（America/Los_Angeles 日期 2026-07-21）。权威输入是
`nominal` 5 资源/5 目标、每个 source episode 2.2 秒、seed `1000-1019` 的 scalable 3D 隔离执行
制品，源提交必须精确等于 `6d5bfead31d53258b020a5f157b2ad5e7f25ee35`。输入
`SHA256SUMS`/manifest SHA-256 分别为
`931f68855df3e9f8c2a1f718249cf33c4ba6899d907ad0032af5b9588e90f08f` 和
`c393f26042f048a8614c81d9ffaef1a58d2b2df1dc32740eae8f10246833e691`。

接受门限是五个 checksum 成员和 manifest 内全部 artifact SHA 匹配；20 条 lineage 无缺失、重复或
额外 seed；dirty、nonfinite、online truth use 均为 0；同源/随机/通信/故障标志均为 20/20；D3/D4
各 40 arm 且每类 control/treatment 为 20/20；20 对输入、lineage 和 bundle identity 全部通过。
审计前后六个输入文件摘要必须一致。任一条件失败即不生成报告包。

D3 bundle manifest/state 绑定为
`a9213d65606a9e2f921040e153488c0f4cdebb10882fa16013fce5b59f9314c0` /
`e3da9fd5b54451da83358405b6051991e0c78bcf9f538b350d459b05faf8e0b2`，D4 为
`dad2adbe9c36dd9ff8ee8bb3c11b1e07e66743c6f80dd8e956799208a10c05c9` /
`3da0360be8788f3ffeb8e9f9eba3e0d5369ec0bdf9e05729dfb1db07d71d5f62`。这些是对任务给定 digest 的
身份绑定；bundle 文件未包含在输入中，D6 未声称重新哈希模型文件。

### 独立重算结果

| 模块/指标 | 结果 | availability/解释 |
| --- | --- | --- |
| source lineage | 20 条，seed 1000-1019 | 完整；dirty/truth/nonfinite=0 |
| D3 arm | 40，control/treatment=20/20 | receipt available |
| D3 treatment applied | 0/20 | 20/20 `out_of_distribution` 回退 |
| D3 control 状态 | unchanged 15；held 3；replan ACK no change 2 | receipt available |
| D3 treatment latency | n=20，mean/P95=0/0 ms | 失败关闭路径时延，不是效果 |
| D4 arm | 40，control/treatment=20/20 | execution evidence available |
| D4 treatment safe-adopted | 0/20 | 20/20 门限/有限性拒绝并回退 |
| D4 candidate latency | n=20，mean 8.291408；median 1.196097；P95 35.255481；max 42.301505 ms | available |
| runtime ACK | 无 | unavailable/null |
| physical outcome | 无 | unavailable/null |
| counterfactual / causal | 无 | unavailable/null |
| paired outcome/effect/non-degradation | 无 | 零采用且无物理结果，unavailable/null |

`execution_receipts=true` 只表明隔离执行与回退证据存在。D3 与 D4 的 treatment 实际采用均为 0，故
回退后 control/treatment 的相同输出不能形成 effect=0 或 non-degradation 结论。没有物理 outcome
数值可画，因而本报告不生成效果曲线；用空图或零线会错误表达不可用证据。

### 输出、SHA 与结论

以下目录及哈希是 schema binding 序列化之前发布的历史 v1 证据，不是当前 consumer 的可复生哈希。
当前代码重新生成 v1 时仍保持算法/API v1 语义，但 provenance 会增加 source schema binding。历史输出目录为
`research_modules/d6_evaluation_metrics/outputs/reserved_seed_interventions_nominal_5v5_1000_1019_d6_audit_20260721/`。

| 文件 | SHA-256 |
| --- | --- |
| `outcome_availability_sidecar.json` | `bfca0fffd343d8aa95c049239631b2de04d261126fb9bb7b6937db3c6f5507f4` |
| `RESERVED_SEED_INTERVENTION_AUDIT_CN.md` | `b60eccda9b799000edb1e6dc99ab7798bf9bedd26af81e2d4daf4e463334ee6f` |
| `provenance_manifest.json` | `9ca69b06a4c8e1dd1eb23fa027cb7da63805731e8441a7ec6f882e65d7544590` |
| `SHA256SUMS` | `0acf4dd3463565dc1d2f596e6226ddbb4a874cd1ec088afee5c74ba2d14fc078` |

sidecar 规范内容 SHA-256 为
`5d789bf77dac3e6545b5a4b1f27693d35de1659c98e03489fe65fc0f38e5a202`。专项测试 `7 passed`，D6
全量 `472 passed`，输出 `sha256sum -c` 全部通过；仅有既有 Matplotlib `Axes3D` warning。

本次结果只证明失败关闭和证据完整性，不证明 D3/D4 候选策略有效、非退化、外部泛化或具有因果
收益。下一步必须先取得严格绑定的非零实际采用 ACK 和采用后物理状态窗，再生成新的 paired outcome/
effect sidecar。

## 2.10 2026-07-22 D5 配对影子权威 v2 独立审计

本次审计只读消费 D5 权威 v2 报告、逐帧来源记录、保留种子图语料、保留种子评估报告、冻结模型包和
实现源码。所有路径由调用方显式给出，并附带独立于报告的 SHA-256。D6 同时核对已替代 v1 报告及
来源记录，防止将旧报告与新源码混用。审计前后共 2718 项输入制品的集合摘要一致，D5 报告、语料、
模型和源码均未被修改。

权威样本覆盖 seed `1000-1019`、9 类场景、5 档规模，共 45 个场景规模单元、900 帧和 74024 条已
标注候选边。逐帧来源记录恰好 900 条，无重复、缺失或额外帧；每条记录只加载一个图实例。规则臂与
模型臂的图、候选边和标签 SHA 完全相同，三项身份比例均为 1.0，模型增删候选边为 0。D6 重新汇总
逐 seed、逐场景规模单元和总体边级、簇级计数及延时，结果均与来源明细闭合。45/45 个单元无质量
退化；模型边级和簇级精确率、召回率、F1 值均为 1.0，模型打分 P95 为 3.292009 毫秒。规则边级
F1 为 0.367980，规则簇级 F1 为 0.239234。

安全审计确认同相机候选边、未标注候选边、在线真值特征和 `global_track_id` 改写均为 0。独立
单变量筛查同时发现合成数据捷径。`shared_global_track_count` 在全部候选边上恒为 0，中心投影
马氏距离的最佳单特征 F1 为 0.370482，当前满分并非由这两项中心身份线索直接解释。包围框尺度变化率、
包围框对数尺度差和角速度差接近确定性分离标签；最强特征在 35/45 个单元达到预设门限。该现象将
外部泛化证据降为“仅合成数据，不足以证明外部泛化”。

审计结论为 `pass_with_synthetic_separability_caveat`。配对影子层记为 `complete`，研究影子仅记为
`qualified_with_synthetic_separability_caveat`。该结论不开放线上路径：G1、近端策略优化、辅助模式
和控制权限均为 false，规则回退为 true。后续需在独立相机几何、外参和时间扰动下移除或随机化上述
近确定性特征，再运行无中心绑定特征的同 seed 配对复验。

专项测试 `8 passed`，D6 全量回归 `465 passed`。`SHA256SUMS`、审计 JSON 内容摘要、manifest 内容摘要
和审计前后输入集合摘要均通过复算。唯一警告为既有 Matplotlib `Axes3D` 导入问题，不影响本次离线
图证据审计。

## 2.9 2026-07-21 D5 保留种子报告合同接入验证（v2 前置阶段）

本次只验证 D6 对已提交 D5 held-out schema 的严格消费接口，没有生成或运行 D5 正式 900 帧语料。
输入 schema 升级为 `d6.d5-clean-graph-inputs.v2`，held-out evaluation report 与 corpus manifest 必须
成对显式提供并携带调用方 SHA-256；旧 v1 清单仍可表示两项均缺失，此时
`held_out_seed=unavailable`。消费器不搜索 D5 输出目录，也不加载模型执行推理。

合成正例严格构造 20 个 seed `1000-1019`、45 个场景规模单元、900 个 episode descriptor，并使用
`d5.tracklet-heldout-model-evaluation.v1`、`d5.tracklet-heldout-corpus.v1` 和 D5 newline-canonical
`content_sha256`。D6 独立核对 held-out manifest、内部 model weights/bundle manifest、validation-only
温度/阈值、各 cell 20 episode 和边计数，再重算 overall/cell 冻结指标门。正例只验证
`held_out_seed=complete` 分支；它是 synthetic contract fixture，不是正式性能结果。

负例覆盖部分 held-out pair、无内部 model bundle、seed/cell/episode 缺失、weights/config/manifest
错配、温度或阈值重选、权重更新、伪造 authority、online truth、同相机边、未标注边、
`global_track_id` 创建/换绑、未知字段、调用方 SHA 和 JSON 内容 SHA 篡改。结构合法但指标不达标的
样例不抛成“缺制品”，而是得到 `held_out_seed=failed`、producer `fail_closed`。所有样例中 paired
shadow 均未提供，G1/assist/authority 均为 false，`rule_fallback_required=true`。

专项结果为 `34 passed`，D6 全量为 `457 passed`，仅有既有 Matplotlib `Axes3D` warning。当时没有
正式 D5 900 帧 held-out corpus/report，因此该阶段 `held_out_seed=unavailable`。当前保留种子和配对
影子结论以 2.10 节权威 v2 审计为准；G1、assist 和控制 authority 仍未开放。

## 2.8 2026-07-21 D5 clean 图数据分层验收（v2 前置阶段）

本次验收只读消费 D5 显式登记的 clean summary、composite admission/view、canonical subview 和正式/
补充 manifest。八项文件及输入清单均由调用方提供 SHA-256。实际 composite 包含 4,972 episode、
245,040 条候选边，其中正边 57,298、负边 187,742、未标注 0；100 个 seed 按 60/20/20 划分，
`1000-1019` 重叠为 0，场景规模单元为 45，来源 dirty 和改写标志均为 false。

实际输出中，数据支持和训练来源为 `complete`；模型内部测试、保留 seed 和同 seed 配对影子为
`unavailable`。G1、assist、authority、模型 promotion 和正式 PPO reward 均为 false，规则回退为
true。测试中的完整模型报告仅用于验证未来输入合同，不构成当前模型证据。

专项 14 项全部通过，覆盖正常审计与 CLI、清单/文件哈希篡改、dirty source、来源改写、保留 seed
泄漏、未标注边、门限降低、部分 bundle、缺少 45 cell 的模型报告、伪造权限字段，以及“内部测试通过
仍不开放外部门”的边界。D6 全量为 `437 passed`；仅有既有 Matplotlib `Axes3D` 环境 warning。

## 2.7 2026-07-21 运行时计划确认与离线结果联接验收

本次验收面向 D6 新增的严格离线消费者。输入按 11 类文件拆分，全部由调用方提供 SHA-256。测试同时
检查 D3 plan、D7 guidance 和 main ACK 的来源 sequence 与规范 payload SHA，D2 identity 的
source-observation lineage，以及独立 truth-state NPZ 和 5 米 proximity JSONL。D6 未修改正式
900-episode 数据，也未训练或生成模型。

确定性专项共 22 项，结果全部通过。正常双 ACK fixture 形成两个同资源非重叠窗口。第一个窗口为
`[1.0,2.0)`，状态样本终止在 1.5 秒；第二个窗口为 `[2.0,3.0]`。首窗 assigned target 的起始/最小
距离为 10/4 米，距离进展 6 米，正确目标 5 米事件为 true，有界诊断为 1.0。错误目标 5 米事件在独立
负例中只进入 `other_target_proximity_events`，不计 assigned-pair outcome。

| 检查类别 | 覆盖结果 |
|---|---|
| 正常 join 与 CLI | 双窗口、D2 唯一映射、距离/事件、D3/D4 证据和中文报告通过 |
| 文件完整性 | online、truth-state、proximity 和 D2 各源使用显式 SHA-256 |
| 内部归因 | plan/guidance sequence、payload SHA、plan version 和 binding 集合重新核对 |
| 身份失败关闭 | D2 mapping 缺失或歧义时距离和 score 为 null，不使用 proximity 反推身份 |
| 控制失败关闭 | hold 或缺 D7 时 score unavailable；ACK 自报 outcome/reward 被拒绝 |
| 版本与刷新 | 同身份合法 refresh 形成独立 occurrence；同版本执行签名漂移、重复 bus sequence、陈旧/错误 version 和额外 binding 均被拒绝 |

D6 全量为 `423 passed`，仅有既有 Matplotlib `Axes3D` 环境 warning。真实 main 3v3、recon=1、
seed=70、1.2 秒集成回归生成两条同 plan identity ACK。序号 13、时间 0.25 秒为新执行计划；序号 81、
时间 1.0 秒为 `evaluation_refresh_only`。两条 ACK 分别形成 occurrence，3 个资源累计得到 6 个非重叠
窗口。两次 occurrence 的绑定、联盟、未分配清单和 authority 执行签名一致，online truth 使用为 0，
PPO、assist 和 authority 均为 false。

篡改负例在第二次同版本刷新中修改 coalition version，并同步更新 D3、D7、ACK 的引用摘要，使单条
消息完整性检查仍可通过。D6 随后在跨 occurrence 执行签名比较处返回
`same_plan_execution_signature_changed`。消费者没有跳过第二条 ACK，也没有把同版本执行变化当作
评估刷新。

本次结果证明 API、哈希边界、身份隔离、状态切窗和失败关闭逻辑可运行。它不构成正式多 seed 或学习
策略性能结论。当前尚无同 seed paired formal shadow、学习实际采用的归因结果、保留 seed 性能、
counterfactual/causal evidence 或正式 PPO reward，因此总体准入保持关闭。

## 2.6 2026-07-21 跨模块学习数据联合准入审计

本次实验使用冻结的 training seed registry、shared registry、D3 formal manifest、D4 formal
manifest 与独立 canonical view、D5 tracklet/active-vision formal manifest、canonical view、readiness，
以及 D4/D5 2026-07-21 supplemental summary。D3、D4、D5 另提供 producer 全样本审计和调用方带外
文件 SHA-256。审计通过显式路径读取，不搜索邻近目录，不修改正式 producer artifact。D4 formal
view 文件 SHA-256 为
`73a365d32b0439fbf805f40ea7941b8e992fe4c68687cbc5496704f230440b11`，内部
`binding.view_sha256` 为
`e6a84861de6e7f0ef8fcf787ec3e28a59c2e7b5504faaaa4c75344db21f6128d`。

正式语料覆盖 900 episode 和 100 个训练 seed。规范 train/validation/test 为 60/20/20，保留 seed
`1000-1019` 泄漏为 0，online truth 使用为 0。D3 为 900 episode/1604 frame，D4 为 900
episode/1798 frame，D5 active vision 为 900 episode/1,153,242 sample。D5 tracklet 为 12,851 graph
episode 和 480 candidate edge。

| 证据 | 规模或计数 | 审计结论 |
|---|---:|---|
| D4 supplemental | 100 episode，300 frame | canonical episode 60/20/20，frame 180/60/60 |
| D4 动作 | hold 100；request-replan 200；nonzero quota 200；transfer 100 | 规则教师覆盖，不是运行时执行证据 |
| D5 supplemental | 100 episode，800 segment，1200 sample | canonical sample 720/240/240 |
| D5 intent | hold 200；observe-target 600；reacquire 200；search-sector 200 | 规则教师覆盖 |
| D5 视场与角色 | wide/zoom 1000/200；interceptor/recon 600/600 | 覆盖计数通过 |
| D5 tracklet 标签 | positive 362；negative 19；unlabeled 99 | labeled 381，complete=false，status=partial |
| D5 synthetic ACK | applied/rejected/missing 各 400 | 仅故障注入覆盖，不计 runtime ACK attribution |
| D3 分配全样本 | 900 episode；1604 frame；3,658,815 candidate edge | 117,304 selected action；43,905,780 个特征值有限；complete |
| D4 区域全样本 | formal 900/1798/14384；supplemental 100/300/1200 | 文件、计数、版本、真值隔离和安全合同通过；complete |
| D5 supplemental 全样本 | 100 episode；1200 sample；online/offline/descriptor 各 100 | 302/302 制品校验，有限特征 1200/1200，complete |

证据层被分为正式观测语料、补充规则教师课程、离线评估标签和 runtime ACK。D5 tracklet 有 381 条已
标注边，但 99 条边未标注，因此不能报告为完整监督标签集。D5 synthetic ACK 没有实际运行时来源，
不能用于动作归因、奖励计算或在线准入。

D3/D4/D5 全样本审计均确认 canonical seed=`60/20/20`，online truth、保留 seed 泄漏、dirty episode、
非有限值和结构约束违规为 0。D5 另确认 D5 创建、改写或换绑 `global_track_id` 为 0，四类离线标签
保持 unavailable，没有以零补成可用标签。三份审计文件 SHA-256 为 `62a47df8...17fb`、
`4245f1db...9e46`、`9a036535...2d3`，内容 SHA-256 为 `954f3e96...1867`、`94f4f4bf...3e7f`、
`a11b6559...50dd`。

当前准入矩阵为：BC canonical view available=true；D3/D4/D5 full-sample=complete；跨模块 structural
full-sample=complete；overall admission=partial；PPO=false；assist=false；authority=false；rule
fallback required=true。D3 `reward_components` 只作规则教师诊断，D4 projected recommendation 和
`target.kind=rule` 不属于 runtime ACK 或 truth。reward、outcome、counterfactual、causal、runtime
ACK、paired shadow 和保留 seed 性能均 unavailable。本次没有训练模型，也没有模型收益结论。

报告输出位于 D6 自有的
`outputs/cross_module_learning_admission_20260721/`，JSON 和中文 Markdown SHA-256 分别为
`6593ee8a11d33b7c75d633f87e0fbd84cea421798bab0920ef4117cb044a87f5` 和
`7b6480d08870cbf21f532235ddfdbe9ca7f23ce05f681f2d18846f988355a4ba`。写盘入口会在创建目录前拒绝
正式 generation 根及其子目录。专项测试 `37 passed`，覆盖 D3/D4 file/content SHA、schema、计数、
binding、status、availability/admission 篡改；D6 全量 `401 passed`，仅有既有 Matplotlib `Axes3D`
环境 warning。

后续由 producer 持久化真实 action adoption、版本绑定、runtime ACK、可归因 reward/outcome 和终局
结果；形成因果/反事实证据和同 seed paired shadow；最后使用保留 seed
`1000-1019` 做独立验收。上述条件未满足前，PPO、在线 assist 和 authority 保持关闭。

## 2.5 2026-07-21 历史正式共享 seed 划分审计

本节记录 detached canonical views 生成前对原始 manifest 的直接比较。当前联合准入结论以 2.6 节为
准；历史 mismatch 用于保留原始数据治理过程，正式源没有被改写。

本次对 `learning_generation_v1_multibatchfix` 的 900 episode 学习导出执行全量只读 readiness。输入为
100 个训练 seed 和 20 个保留评估 seed。训练/保留交集为 0，全部已注册源文件哈希验证通过，正式源
数据未修改。输出位于临时目录
`/tmp/d6_learning_label_readiness_shared_split_20260721.json`，SHA-256 为
`a0469fa0bf4f1fc80d5e5dc9afac74d4638e782161c0c3f5ebc6befd93f405d1`。

| 模块 | train/validation/test seed | mismatch seed | mismatch episode/记录 | mismatch sample | 结论 |
|---|---:|---:|---:|---:|---|
| D3 assignment | 60/20/20 | 0 | 0 | 0 frame | exact |
| D4 region | 70/15/15 | 51 | 459 | 917 frame | mismatch |
| D5 tracklet graph | 60/20/20 | 65 | 8350 | 284 candidate edge | mismatch |
| D5 active vision | 60/20/20 | 62 | 558 | 713298 sample | mismatch |

四模块 missing、extra、reserved seed 均为 0。D3 与 canonical assignment 完全一致，D4 和两类 D5
manifest 不一致，因此联合训练 readiness 为 unavailable。旧 D4/D5 两模块直接比较仍为 423/900 个
episode、47/100 个 seed 不一致。两种统计使用不同参照，不应混为同一个数。

注册表 schema、policy、内容哈希、assignment 哈希和源 training registry SHA-256 均通过独立复算。
该结果只验证数据划分治理。模型性能、奖励可用性、PPO 准入和联合策略效果未在本次实验中评估。
接受门限为注册表八项 validation 全真且 D3/D4/D5 graph/D5 active 全部 exact。本次注册表通过，模块
联合门未通过。2026-07-21 D6 全量回归为 `364 passed`，仅有既有 Matplotlib `Axes3D` warning。

## 2.4 2026-07-20 scalable 3D 算法实验矩阵接口验收

本节验证 D6 对 `scalable3d-experiment-matrix-v1` 持久化 episode 的只读审计。输入是确定性 fixture 和
一个既有 producer 开发 smoke，不包含 AirSim、正式训练结果或算法性能实验。

fixture 按真实 producer 结构在 scenario metadata 写入 schema、R0/G1/A1/A2/A3/C1/F1、comparison
key、full-system flag 和四项 learning runtime diagnostics。负例删除三个矩阵标识字段，注入 X9 伪
变体和 G1 bundle 回退。完整性用 nominal 同键 R0/G1/A1 三个 cell 验证固定 6-cell 分母；另用两个
seed 的 R0/G1 配对验证 variant-minus-R0 delta 和 bootstrap CI。一个 seed 标为 dirty，用于检查
clean/formal 与开发证据分层。F1 在 nominal 中被列为 unexpected，在高威胁 M-to-N 中进入第七个
期望 cell。

接受门限为：历史 episode 不因缺矩阵字段失去原有可评估性；当前矩阵字段缺失或未知时不得补目录名；
runtime 双来源必须一致；bundle、assist effective mode、无 fallback 和模块实际采用证据同时成立；缺
cell 不缩小分母；无 R0 配对不计算差值；单配对不生成置信区间；dirty 数据不进入 clean/formal 统计；
任何 paired delta 不直接写成因果效果。加入 D4 消费合同正反例后，上述接口门限均通过，scalable 专项
`40 passed`，D6 全量 `320 passed`，仅有既有 Matplotlib `Axes3D` warning。

既有 `/tmp` producer smoke 为 R0、nominal、2v2、seed101。D6 复读得到 metadata valid=true、execution
valid=true，完整性为 present/expected=`1/6`。该运行来自 dirty worktree，matrix formal=false，只能
证明 producer/consumer 接口接通。另一个临时 5v5 producer smoke 中，D4 合法消费、D3 hint applied
和 control adoption 均为 1。main 尚未运行 clean 的完整矩阵，本节没有变体性能排序、提升率或主线
准入结论。D4 advice 单独仍不证明采用；只有合法消费且 D3 明确应用 hint 才形成 adoption evidence。

## 2.3 2026-07-20 scalable 3D schema 合同回归

本节修正 D6 fixture 与真实 producer 的 online observation schema 偏差。真实值是
`scalable3d-observation-v1`；旧 fixture 值 `scalable3d-online-observation-v1` 已删除。评估器 v4 新增
本地 schema registry，不依赖 main runtime import。

正例同时匹配 world、bus、scenario、online observation、offline truth 和 config schema。负例分别
替换五项 manifest schema，并删除 bus schema。接受门限为：raw 字段仍原样可见；匹配值为 true；旧、
未知和篡改值为 false 且带明确 reason；缺字段为 unavailable；任一负例 formal acceptance=false；
Markdown 显示 registry 和 schema current 状态。全部满足。

scalable 与 active-vision 专项 `32 passed`，D6 全量 `304 passed`，仅有既有 Matplotlib `Axes3D`
warning。复读当前 6v6、seed 37 dirty producer smoke 时，schema match=true；formal=false 的唯一原因是
repository dirty。该复读不构成新的性能实验。

## 2.2 2026-07-20 scalable 3D 主动视觉证据验收

本节验证 D6 对 D5 主动视觉命令和 main runtime ACK 的离线消费，不记录真实飞行、AirSim 或模型性能。
8 项测试共创建 9 个 deterministic episode fixture。单 episode 显式规模为 target/resource/recon/
camera=`6/4/1/5`；聚合测试使用 seed 1 和 seed 2，不从场景名推断规模。

验证矩阵包括 rule、shadow 和 assist 三类命令；applied/rejected ACK；10、20、30 ms 延迟；command
expired、stale coalition version、camera/resource unavailable 和 degenerate aim point 四类拒绝；
未知 D2 中心航迹引用、ACK target 改写、在线 truth 字段、active log 缺失和 summary count conflict。
另设 assist applied 加五米 proximity 的正例，确认 attribution 仍因缺少配对控制组而 unavailable。

接受门限为：三种模式不互相回填；命令和 ACK 按完整版本键关联；拒绝分类及 summary counters 一致；
未知 ID、ACK 改写和 truth 污染使正式证据 fail closed；缺日志不写 0；双 seed 报告保留显式规模；同一
episode 物理事件不产生因果归因。上述门限全部满足。主动视觉与既有 scalable 专项共 `25 passed`，
D6 全量 `297 passed`，仅有既有 Matplotlib `Axes3D` warning。

当前结果关闭 D6 consumer 和报告口径缺口。main 尚未提供 clean worktree 下至少 20 个未见 seed 的
rule/shadow/assist 正式 episode；assist 也没有同 seed 配对规则控制组。因此本节没有主动视觉提升率、
物理效果或默认路径准入结论。

接口测试后又运行了一个当前 main-runtime 临时 smoke。参数为 6 个 target、6 个 interceptor、1 个
recon、7 台 camera、seed 37、duration 2.2 s；finite=true、RTF=4.740。D6 v3 读取 133 条 disabled/rule
command、133 条 matched ACK，全部 applied；rejected、target-reference violation 和 online truth
field violation 均为 0，summary counter match=true。该 worktree 为 dirty，且只有一个 seed，所以
formal acceptance=false、bootstrap unavailable。本条只说明实际 producer 文件能够被 consumer 解析，
不构成 AirSim、模型或物理性能证据。

## 2.1 2026-07-20 scalable 3D 学习运行时确定性验收

本节只记录 D6 consumer/report 的接口与口径测试，不记录真实飞行、质点仿真或学习模型性能。输入均为
测试创建的 deterministic fixture。既有规模样本包括显式 target/resource/recon/camera=
`50/50/4/54` seed 7 和 `200/200/8/208` seed 8；后者保持 195->200 min-dwell backlog=`5`。场景名
故意含 `2v2`，分组仍来自显式数量。

学习运行时矩阵覆盖：

| Fixture | 预期证据边界 |
| --- | --- |
| disabled | bundle loaded=false；model fingerprint/version unavailable；无 advice 属于 not expected |
| D3/D4/D5 missing bundle | 三模块 fallback 原因保留；模型 fingerprint/version 不补值 |
| D4 assist-to-shadow | loaded bundle 与合法 shadow recommendation 可用；assist eligible=0 |
| D4 assist gate | assist eligible=1，但 formal decision unchanged；advice 单独不计 control adoption |
| D4 consumption | 合法消费计 adoption；拒绝消费计 0；旧 schema、未知或篡改合同及 summary 冲突 fail closed |
| quota/projection | 守恒零、非守恒违规和 projection rejection 分别可审计 |
| mutation/tamper | mutation/unchanged 分开；digest flag 篡改使 payload invalid |
| old/missing evidence | 旧 advice schema、缺 plan version、缺 advice 均 fail closed，不补零 |
| seeds 1/2 | 按实际规模形成 distinct-seed bootstrap；单 seed CI 仍为 null |

逐 episode 接受门限为：learning runtime 双来源一致；loaded bundle 的 64 位 fingerprint 与 runtime
version 后缀一致；advice schema/mode/action/transfer/authority/plan/version/epoch/lease 合法；projected
quota 总和为零；formal digest flag 一致；控制采用不由 `assist_eligible` 回填。正式 evidence 另要求
`repository_dirty=false`、配置 hash、D4 policy version、finite 和 online truth isolation 可用。

结果为 scalable 专项 `17 passed`、D6 全量 `289 passed`，仅有既有 Matplotlib `Axes3D` warning。
四类报告均生成，旧/非法/缺失字段均保持 null/unavailable+reason，single-seed 不产生推断结论。本轮
没有运行真实 scalable 3D 或 AirSim episode，也没有模型 acceptance 样本；任何 dirty smoke 只可做
人工兼容检查，不进入本节验收结果。

剩余限制：main 尚需提供 clean、多规模、多 seed 正式学习 bundle和完整实验矩阵；当前只有单 episode
D4 消费接线证据，尚无模型效果结论；global-track-to-truth evaluator mapping 仍缺失，D2 IDSW 继续由
producer availability 决定。

## 2.0 2026-07-15 真实 M5N2 三档 ClockSpeed 对比

输入为 1.0 `p1_terminal_timing_funnel_10seed_20260715_m5n2`、0.2
`p1_clockspeed_0p2_m5n2_20case_20260715_v2`、0.1
`p1_clockspeed_0p1_m5n2_20case_20260715`。每档 baseline/candidate 各 seed 1-10，总计 60 case，按
`case_id/profile/seed` 形成 20 个完整跨档配对。0.2/0.1 ClockSpeed 来自 case result；旧 1.0 summary
无该字段，D6 从 20/20 sibling case generated settings 的显式一致 `ClockSpeed=1.0` 建立 provenance，
没有按目录名推断或默认补值。三份 summary 加 20 份 legacy settings 的“绝对路径+内容”组合
SHA-256 前后同为 `fdb745ee54f0c5ff414a812bf8e75eacd56fa5ea91ff02f64008fb6ee1759cd1`。

| ClockSpeed | Profile | Pair | Target | Coalition | Simulated time/tick |
| ---: | --- | ---: | ---: | ---: | ---: |
| 0.1 | baseline | 4/30 | 4/20 | 0/10 | 0.345297 s |
| 0.1 | candidate | unavailable | unavailable | unavailable | 0.362730 s |
| 0.2 | baseline | 9/30 | 9/20 | 0/10 | 0.441508 s |
| 0.2 | candidate | unavailable | unavailable | unavailable | 0.469176 s |
| 1.0 | baseline | 6/30 | 6/20 | 0/10 | 1.069535 s |
| 1.0 | candidate | 6/30 | 6/20 | 0/10 | 1.066734 s |

M5N2 冻结机会合同在 60 case 中 56 match、4 mismatch：0.1 candidate seed007 实际 `1/1/0`、
seed009 `2/1/1`；0.2 candidate seed006/009 均为 `2/1/1`，其中 seed006 另有 D7 actual execution
unavailable 及三类 count conflict。四个 case 的受影响物理、第二 primary、最终锁/共识和 collision
指标均为 unavailable，不用 8-case 或缩小机会数发布完整 candidate aggregate。standby reserve
成功不计 active-primary。truth identity/state 在线使用审计为 60 case 全 0。case wall elapsed 因源
row 没有该字段，六个 profile/speed aggregate 均 unavailable。

main-bus/control-tick wall mean 继续分别报告，禁止相加；上表归一化值只使用
`control_tick_wall_mean_ms / 1000 * ClockSpeed`。基于可用 baseline 可陈述观测值，但 candidate 0.1/
0.2 的物理 aggregate 不完整，因此本报告不据此判定 ClockSpeed 性能优劣或 candidate 准入。完整
产物位于 `../airsim_runtime/outputs/m5n2_clock_speed_comparison_20260715/`。

## 1.9 2026-07-15 真实 ClockSpeed=0.1 P1 紧急回归

故障表现是 `evaluate_stage_timing_inputs()` 调用缺失的 `_timing_input_mode`。修复将唯一模式规范化
函数前置并统一命名，新增 baseline/candidate 各 seed 1-10 的 20-case 双层 merged evaluator 回归。

真实输入为 `p1_clockspeed_0p1_m5n2_20case_20260715`，验收门限为 P1 v6 无异常生成、两层 available、
records=`4036/4036`、case=`20/20`、manifest match、跨 case/跨层 total 为 null、输入 hash 不变；
全部满足。报告位于
`outputs/p1_clockspeed_0p1_m5n2_20case_20260715_case_aware_validation/`。timing 专项
`28 passed`、D6 全量 `264 passed`，仅既有 Matplotlib warning。该报告验证 P1 接线，不替代三档
ClockSpeed comparator，不发布三档性能结论。

## 1.8 2026-07-15 真实 ClockSpeed=0.2 case-aware 复测

输入是 main 已完成的 M5N2 20/20 case summary 及 merged timing。D6 以只读方式运行 P1 v6；main bus/
control tick 各 6567 records、20 个 case envelope，ordered manifest 一致。每个 case 内 frame/time
严格递增，case 切换从 0 重置；顶层 `frame_index_first/last`、`timestamp_first/last` 与
`cross_case_total_ms` 不发布，`cross_layer_total_ms` 也为 null。三份 runtime 输入 SHA-256 前后不变。

冻结机会合同审计要求每 case pair/target/coalition=`3/2/1`，不采用实际产物缩小后的分母。20 case
中 18 match、2 mismatch：candidate seed006 的 D7 actual-execution unavailable，reasons 为
physical-pair、command-physical、main-physical-intercept count conflict，suite/intercept 均为
`2/1/1`；其 standby reserve physical success=true，raw top-level success=2，但 active-primary 与
`success_semantics` 均为 1。candidate seed009 的 D7 actual-execution available，但机会同为 `2/1/1`，
也按 contract mismatch 处理。两例受影响指标均为 unavailable，不形成 28 或其他缩分母结果。

验收门限为 loader 不抛异常、两层 available、records=`6567/6567`、case=`20/20`、manifest match、
跨 case/跨层 total 为 null、输入 hash 不变；全部满足。timing 专项 `27 passed`、ClockSpeed 专项
`10 passed`、D6 当时全量 `263 passed`。0.1 后续 P1 复测见 1.9 节；本节仍不提供三档结论。

## 1.7 2026-07-15 ClockSpeed 三档离线接口回归

本批是确定性 consumer/report 回归，不是真实 AirSim 实验。fixture 构造 ClockSpeed=`1.0/0.2/0.1`
三档 M5N2 summary，每档 baseline/candidate 各 seed 1-10、20 case，总计 60 case；三档共享同一
`case_id/profile/seed` 键。每 case 提供显式 suite provenance、三层物理分母、required
active-primary 终态、truth identity/state、case wall 和两层合法 timing。

接受门限为：恰好三档且 provenance 值集合为 `0.1/0.2/1.0`；每档 baseline/candidate 均完整覆盖
seed 1-10；20 个 case key 全部形成三档配对；M5N2 规模来自显式 family/resource/target；main bus
与 control tick 不相加；缺 truth 或第二 primary 距离时为 unavailable 而不是 0；显式非零 truth
使 `all_zero=false`；输出 JSON、两份 CSV、中文 Markdown 和非空 PNG。

结果为专项 `8 passed`、D6 全量 `254 passed`，`py_compile` 通过；唯一 warning 是既有 Matplotlib
`Axes3D` 环境问题，不影响二维曲线。归一化 fixture 验证 control tick wall mean=`100 ms` 时，
ClockSpeed=`0.1` 的 `simulated_time_per_tick_s=0.01`；main bus=`10 ms` 保持独立，未与 control tick
相加。负例覆盖缺 seed、跨档 case key 不一致、目录/根字段冒充 ClockSpeed、缺指标和非零 truth。

该节是运行前接口记录；真实三档 comparator 随后已由三个完整 suite 生成，见 2.0 节。2.0 对合同
mismatch 和缺 wall timing 继续保持 unavailable，不用部分值补写结论。

## 1.6 2026-07-15 真实 AirSim M5N2 20-case 结果

本次实验只纳入 M5N2 baseline/candidate 各 10 seed，共 20 个 SimpleFlight case。M5N2 完成后、
`TERM` 生效前额外完成了 `p1_terminal_timing_funnel_10seed_20260715_png_ttc_2v2_seed001`，但该
`png_ttc` seed001 明确排除在 M5N2 20-case 聚合与验收之外。其余 tuned 2v2 和全部 dropout case
未执行；缺失 case 保持 unavailable，不按失败或零值处理。本批不能代表完整 terminal-closure suite。

### 证据可用性与物理结果

| Profile | Actual available | Pair | Target | Coalition | Truth identity/state |
| --- | ---: | ---: | ---: | ---: | ---: |
| baseline | 10/10 | 6/30 | 6/20 | 0/10 | 0 / 0 |
| candidate soft prediction + trend coast | 10/10 | 6/30 | 6/20 | 0/10 | 0 / 0 |
| 合计 | 20/20 | 12/60 (20%) | 12/40 (30%) | 0/20 (0%) | 0 / 0 |

20 个 actual artifact 均通过 source/schema/hash/case/seed 校验，validation reason 为 0。10389 条
目标状态样本来源均为 `d2_estimated_global_track`，stale 为 0。pair、target、coalition 的成功数
和分母独立发布，target 成功不用于回填 coalition。

本报告统一使用以下术语：`12/40` 是 canonical target physical success，即至少一个 participating
pair 进入 5 m；“全部 required member 通过某阶段”是 cooperative target-stage diagnostic。后者
只用于定位协同证据在哪一阶段收缩，不等同于正式 `target_intercept_success`。

两 profile 汇总成功数相同，但逐 seed 并不非退化：candidate 在 seed 1、7 由 2 降为 0，在 seed
3、10 由 0 升为 2，其余相同。因此 paired non-degradation=false，soft prediction/trend coast
不能凭总量持平获得主线晋升。

### 第二 primary 首失败漏斗

| 阶段 | Baseline | Candidate | 合计 availability | 合计通过 |
| --- | ---: | ---: | ---: | ---: |
| assigned | 10/10 | 10/10 | 20/20 | 20 |
| visible | 10/10 | 10/10 | 20/20 | 20 |
| associated | 10/10 | 10/10 | 20/20 | 20 |
| contract allowed | 10/10 | 10/10 | 20/20 | 20 |
| control allowed | 8/10 | 9/10 | 20/20 | 17 |
| mode switched | 8/10 | 9/10 | 20/20 | 17 |
| 5 m physical intercept | 0/10 | 0/10 | 20/20 | 0 |

20 个失败单元的首失败原因均 available：`terminal_visual_prediction_window_expired=10`、
`terminal_visual_acquiring=6`、`d5_not_locked=2`、`bbox_area_too_small=1`、
`bbox_near_image_edge=1`。第二 primary 最近距离 baseline/candidate mean=
`12.736/12.573 m`，合计 mean/min/max=`12.654/8.843/14.740 m`，没有一次进入 5 m。这里的
associated 表示 episode 内曾获得锁定证据，不代表锁定一直保持到物理闭环。

第二 primary 的最终状态 `20/20` 为 `collision_stop`。本批产物没有记录 collision object，因而
无法区分联盟成员冲突、环境碰撞和 AirSim 状态问题。该字段缺失保持 unavailable，不补成某个
失败类别，也不把 `collision_stop` 解释为五米物理成功；它是下一轮 producer 接线的 P1 项。

### 两层时序

| 测量域 | Samples | Mean ms | P95 ms | Max ms | 100 ms 违例 | 主导阶段 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| main episode bus | 3805 | 349.34 | 487.40 | 1305.99 | 3649 (95.90%) | D1 fusion, mean 320.00 ms |
| SimpleFlight control tick | 3805 | 1069.45 | 1254.06 | 2072.51 | 3805 (100%) | AirSim frame sample, mean 432.29 ms |

control tick 内的 `bus_processing` mean=`351.80 ms`，已经包住 main bus；
`guidance_and_control_rpc` mean=`290.85 ms`。所以两行总时延不得相加。20 个 case 的原始流逐 case
严格校验均通过且 error record 为 0，但 partial acceptance bundle 没有注册 timing 路径；现有合并
流在 case 边界重置 frame/timestamp，也不能作为单一严格递增流直接导入。正式 suite timing 因而
仍是 unavailable，本表属于按显式 case 路径完成的离线池化审计。

### 结论

actual evidence、truth 隔离和独立分母已经闭合；第二 primary/coalition 和 100 ms 性能门未闭合。
candidate 未证明逐 seed 非退化。后续优先处理 case-aware timing 接线、D1 fusion/AirSim 采样/RPC
瓶颈和第二 primary 末端稳定性；聚合外已完成的 `png_ttc` seed001 不追加到本批，其余 tuned 2v2
和全部 dropout 应作为新的独立批次运行。

## 1.5 2026-07-15 第二 primary/独立分母报告回归

本批是确定性离线 consumer/report 回归，不是 AirSim 实验。fixture 覆盖：两个 primary 加一个
单 primary 目标形成不同 pair/target/coalition 分母；第二 primary 在关联阶段和物理阶段失败；失败
但原因缺失；第二 primary 物理结果缺失。接受标准是七阶段漏斗正确、三层机会数独立、coalition
completion 不回填、缺原因不生成 `unspecified`、unavailable 不按零报告或绘图。

结果为 cooperative closure 专项 `11 passed`、D6 全量 `246 passed`，`py_compile` 通过；仅有
既有 Matplotlib `Axes3D` 环境 warning。没有启动 AirSim，也没有产生新的 2v2/M5N2 实测成功率。
因此该阶段只关闭 D6 consumer/report 代码缺口；随后 1.6 节已取得同配置 20-case 的第二 primary
漏斗、联盟完成和首失败原因分布。物理门限未达标，不等同于缺 multi-seed 证据。

## 1.4 2026-07-15 D2 ceiling-aware v2 正式联合证据

本批使用 D2 冻结 replay artifact
`../d2_data_association/outputs/p1_identity_ceiling_aware_v2_20260715/d2_identity_calibration_v2.json`，
通过 `run_p1_system_evidence_report.py` 生成 D2-only 的 CSV、aggregate JSON、中文 Markdown 和 PNG，
输出目录为 `outputs/p1_identity_ceiling_aware_v2_20260715/`。D6 只消费 producer decision，不重算
gate，也不参与在线控制；本批未启动 AirSim。

confirmation 覆盖六 difficulty、每档 20 seed。总体 GNN candidate
`gnn-g5.99-qa1-ld3_7-mw0.5x` 的五 gate 全部通过：IDSW baseline/candidate/reduction=
`1.3583/0.6167/0.5460`；continuity baseline/headroom/actual/required/error reduction=
`0.981046/0.018954/0.002908/0.001895/0.153448`；false-track baseline/candidate=`0/0`，
P95=`0.015470 s < 0.1 s`，online truth leakage=`0`。该结果仅为
`promotion_recommended=true` 的评审建议，`default_online_path_changed=false`。

| Difficulty | Baseline/Candidate IDSW | 五 gate | Producer reason |
| --- | ---: | --- | --- |
| clutter | 1.25 / 0.8 | pass | required IDSW reduction met |
| combined | 6.9 / 2.9 | pass | required IDSW reduction met |
| delayed_noisy | 0 / 0 | fail-closed | baseline zero, no measurable reduction evidence |
| dropout | 0 / 0 | fail-closed | baseline zero, no measurable reduction evidence |
| nominal | 0 / 0 | fail-closed | baseline zero, no measurable reduction evidence |
| tight_crossing | 0 / 0 | fail-closed | baseline zero, no measurable reduction evidence |

dropout truth alignment 在 screening 为 `0/10/0` complete/partial/unavailable、matched/unmatched=
`2330/220`；confirmation 为 `0/20/0`、`4660/440`。JPDA 标记
`research_adapter_only=true` 且总体 gate 不通过，不准入默认在线路径。D1/D3/D4/D5/D7 未提供同批
case/seed 证据，全部明确 unavailable，故 `full_system_decision=not_evaluated`，不宣称全系统通过。

代码验收为 system-evidence 专项 `31 passed`、D6 全量 `243 passed`，仅有既有 Matplotlib
`Axes3D` 环境 warning。该证据关闭“D6 尚无 D2 v2 正式证据”的 P1 报告缺口；promotion 评审决定、
默认在线路径变更和完整同批多源系统判决仍未发生。

## 1.3 2026-07-15 分阶段延迟消费与报告回归

本批验证 D6 离线 consumer，不是 AirSim 性能实验。确定性输入含合法 main bus/control tick 各
2 帧，以及 N/A、error、旧产物、坏 schema/scope、负数/NaN/Inf、总和/状态/预算冲突和重复/倒序
帧。门限是合法流统计正确、两层不求和、旧证据 unavailable、全部非法流 fail closed。

结果为专项 `20 passed`、D6 全量 `236 passed`；CSV、JSON、中文 Markdown 与 PNG 均生成成功。
fixture 的 dominant stage 只验证算法，不代表真实瓶颈。该代码批次未启动 AirSim、无真实 seed，
不能据此宣称 `100 ms` 达标；其后的真实 M5N2 20-case 结果以 1.6 节为准。

## 1.2 2026-07-14 actual target-state freshness/stale 正式验收

本批离线重建只读取最新两例真实 AirSim/SimpleFlight 最终产物，不重新控制 AirSim。接受标准是：
六个 freshness 字段逐行存在且合法，满足 measurement/arrival/control 顺序与 age 等式，source
非空，canonical payload 与已验证 SHA256 的 CSV 复算结果完全一致。正 stale 是合法观测；本批
另要求记录实际 stale 结果，不以缺字段补零。

| Case | Samples | Mean age | P95 age | Max age | Stale | Source distribution | 结果 |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| tuned 2v2 seed-1 | 48 | 0.0375 s | 0.2 s | 0.2 s | 0 (0%) | `d2_estimated_global_track:48` | available |
| M5N2 seed-1 | 608 | 0.091118 s | 0.2 s | 0.2 s | 0 (0%) | `d2_estimated_global_track:608` | available |
| pooled | 656 | 0.087195 s | 0.2 s | 0.2 s | 0 (0%) | `d2_estimated_global_track:656` | available |

canonical case、aggregate JSON/CSV 和中文报告保存在
`outputs/p1_actual_target_state_freshness_20260714/`。代码验收覆盖缺字段、空/非有限/负值、两类时间
冲突、age 冲突、非法布尔、空 source、显式零 stale、真实正 stale、source 分布和 payload 伪造；
D6 全量 `216 passed`，1 条既有 Matplotlib warning。结果关闭单 seed 正式 freshness/stale 指标链，
不形成 multi-seed 稳健性或跨提交趋势结论。

## 1.1 2026-07-14 actual v2 真实 AirSim 验收

本批真实运行包含 tuned 2v2 seed-1 与 M5N2 seed-1，共 2 case、每配置 1 seed。actual execution
接受门限为 required case 全部提供并通过 canonical v2 校验；结果
required/available/unavailable=`2/2/0`，门限通过。两场景 summary、CSV 离线 scorer、actual
artifact 的物理成功计数均为 `2/2/2`，旧 physical-count conflict 未复现并关闭。

| 场景 | Pair | Target | Coalition | Loop latency | Budget violations |
| --- | ---: | ---: | --- | ---: | ---: |
| tuned 2v2 seed-1 | 2/2 | 2/2 | 不适用 | 123.3 ms | 19 |
| M5N2 seed-1 | 2/3 | 2/2 | available 0/1 | 384.6 ms | 212 |

M5N2 coalition `0/1` 是显式可用失败；第二 required primary 最近约 `11.02 m`，target `2/2`
不能替代 coalition 完成。统一报告 `overall_acceptance_passed=false` 是因为两个 seed-1 case
不构成 baseline/candidate、1-5 帧 dropout 和 multi-seed 的完整 P1 矩阵，不是 actual evidence
unavailable。loop latency 均超过 `100 ms` 预算，违例合计 `231`，保持 P1。该批没有改 D6 代码。

## 1.0 2026-07-14 actual-execution 与独立到达口径最终复核（真实重跑前历史）

本轮没有运行 AirSim，只复核已实现的 D6 consumer/gate 与确定性 fixture。接受标准是：每个
required case 必须提供并通过校验的 canonical `d7-actual-execution-metrics-v2`；缺失或 explicit
unavailable 时 `actual_execution_all_available=false`，suite 总验收 fail closed。legacy main row
和离线五米结果只作 diagnostics，不能替代 actual envelope。

`arrival_coordination_required=false` 的 coalition completion 按每个 required active primary 的
独立五米成功计算；全部 required primary 成功才记该 target coalition 完成。required-primary
denominator/member、physical result 或开关缺失，以及 summary/pair 冲突，均保持
`null/unavailable`。专项正负例达到该门限。

四个历史真实 seed-1 case 的 actual artifact 仍为 `unavailable`：M5N2 baseline、M5N2
candidate、2v2 PNG-TTC 和 1-frame dropout；四者原因均为
`d7_actual_execution_command_physical_count_conflict`。因此历史 main acceptance 和离线五米
结果不构成正式 actual-execution 通过，必须由 main 真实重跑并注册有效 v2 artifact。

验证日期为 2026-07-14；专项结果 `14 passed, 24 deselected`，D6 全量结果 `190 passed`。唯一
warning 为 Matplotlib `projections/__init__.py:63` 无法导入 `Axes3D`，仅表示 3D projection
不可用；本轮不使用该能力，JSON/CSV/Markdown、二维报告和口径结论不受影响。

## 0.9 2026-07-14 owner provenance 最终语义回归

本轮未运行 AirSim，seed 不适用，仅使用确定性临时 command/summary/main-bus fixture。接受门限为：
plan ID 与正整数 version 在每个 command row 仍必填；中心 effective-authorized 行可以没有
`d4_target_node_id`；未授权的 pre-transition/pending 行可以没有 owner；secondary/distributed
active/execution/reassignment 或显式 execute action 行在 effective-authorized 时缺 owner 必须
fail closed；整集没有 authoritative owner 时 `owner_node_ids=[]` 且 provenance 为 unavailable。

结果为 execution-evidence focused `20 passed`、D6 全量 `184 passed`，1 条既有 matplotlib
`Axes3D` 环境 warning。中心授权空 owner 正例与 secondary effective-authorized 空 owner 负例均
达到门限。该结果只验证 D6 builder/validator 语义，不形成新的飞行、拦截或多 seed 性能证据。

## 0.8 2026-07-14 actual plan identity 离线验收（真实重跑前代码验收）

本次没有运行真实 AirSim，仅使用临时持久化 CSV/JSON fixture 验证 actual envelope 和 merge。
接受门限为：合法单版本与合法多版本提取结果精确去重；缺列、非法 version、同 plan 混合 version、
provenance 篡改和 hashed CSV 不一致全部 fail closed；replay 中伪造的 plan/owner 不得进入最终
`metrics.metadata`；safety count、physical 和 effective-control mode 语义保持原回归结果。

结果为 focused `24 passed`、D6 全量 `180 passed`，1 条既有 matplotlib `Axes3D` 环境 warning；
`py_compile` 通过。该结果关闭 D6 P0 实现与离线验证，不形成新的飞行性能、拦截成功率或实时性
结论。真实 SimpleFlight seed-1 v2 artifact 生成/注册已由 1.1 节关闭；同条件 multi-seed 验收
仍为 P1。

## 0.7 2026-07-14 actual execution evidence 审计（真实重跑前离线审计）

本次使用最新两个既有 M5N2 seed-1 episode 的四类文件进行离线审计，没有重新启动 AirSim。

| profile | command rows | raw replay mode | actual effective control | actual mode | physical pair/target | performance samples | loop latency |
| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| baseline | 330 | 17 | 0 | 0 | 0/3，0/2 | 142 | 386.519 ms |
| candidate | 311 | 13 | 0 | 0 | 0/3，0/2 | 141 | 398.333 ms |

raw replay 同时给出 `loop_latency_ms=0`，但其 performance distribution sample count 为 0；该零值
不能证明实际循环零时延。command CSV 中 17/13 次 `mode_switched=true` 是命令模式变化，其中
没有一条同时满足 `effective_control_authorized=true`，因此 actual mode count 必须为 0。最终
main bus 的 mode count 也是 0，循环时延分别为 386.519/398.333 ms。

新增 builder 对两组现有输入均可生成结构有效的 actual envelope，但本批没有将生成文件写入
AirSim output 目录，也没有替 main 注册。代码验收门限为：raw replay 被拒绝；有效三源写盘通过；
零性能样本、控制来源冲突、mode 超过 control、hash 篡改均 unavailable。实际 D6 全量结果为
`173 passed`，1 条既有 Matplotlib `Axes3D` warning。新增回归证明 identity 正样本与 state
显式零值可同时发布且来源互不替代；视觉 PNG 持续授权样本不会被累计为重复切换。代码级 P0
已关闭。main 报告的 runtime 回归曾为 `2 failed, 140 passed`：state 已进入正式指标，两个失败
转为 identity KeyError，确认缺口位于 D6 actual schema 而非 main 应补零；本次已修复，仍需 main
复跑确认集成结果。

## 0.6 2026-07-14 terminal closure case evidence 回归（先前四案例）

本轮不启动 AirSim，只读取现有 seed-1 terminal closure summary 和 producer 已写盘文件。正式
summary 包含 4 个 case：M5N2 baseline、M5N2 soft-prediction/trend-coast candidate、2v2
`png_ttc` 和 1-frame dropout。

| 检查项 | 接受标准 | 实际结果 |
|---|---|---|
| D3 suite 路径消费 | 每行独立校验，按 case/seed 聚合 | 4/4 available，543 records |
| D7 原 summary wiring | null path 必须 unavailable 且不得猜目录 | 0/4 registered，4 次明确 wiring reason |
| D7 显式 registration 临时副本 | 现有文件结构可用、seed 匹配 | 4/4 available，control allowed sum=51 |
| 四层防重复 | raw D7 不覆盖或二次累计 main envelope | main control layer 仍为 51 |
| 缺文件/schema mismatch | case 隔离、sum=null、不补零 | 通过 |

新增 5 项专项回归，加上既有 D6 测试后为 `159 passed`，1 条既有 matplotlib `Axes3D` warning。
当前正式 AirSim suite 未重写，所以报告应继续把 D7 wiring 判为 unavailable；临时显式注册只证明
D6 consumer 和现有 producer 文件兼容，不替代 main runtime 接线，也不构成新的物理拦截实验。

## 0.5 2026-07-14 terminal suite P1 schema 回归

本轮是 file-only 确定性回归，未启动 AirSim。新增场景覆盖：main planned-lock 与 D7 execution
同名 contract 指标必须形成两个语义组且顶层不求和；physical `0/0` 必须 unavailable；10 个
性能样本下 budget violation 显式 0 可用，而零样本同名零不可用；baseline/candidate 效果均为
0 且 candidate trigger=0 时 effectiveness 为 `inconclusive`、promotion=false；两 tick D3
canonical history 输出 plan-2、primary/reserve membership、secondary owner 和 feedback churn。

接受门限全部满足。2026-07-14 terminal-suite 专项 `8 passed`、canonical 专项 `24 passed`、
D6 全量 `154 passed`，1 条既有 matplotlib `Axes3D` warning。该证据只验证
`d6-p1-unified-acceptance-v2` / `d6-terminal-metric-envelope-v1` 的 schema、availability 与报告
逻辑，不构成真实 AirSim 性能结论。main `p1_terminal_closure` 尚需写入 producer/scope/
denominator/lifecycle、physical context、performance sample count、candidate trigger/effect，并传入
真实 `d3_plan_history.json`。

## 0.4 2026-07-14 physical result/coalition availability P0 回归

本轮未启动 AirSim，seed 不适用。新增 7 项确定性回归分别验证：evidence=true 但缺 pair
result 时三层全 unavailable；规范 success/failure scorer status 可判定；required-primary
实际写盘成员不足、缺 arrival window、缺 coalition denominator、summary 有 opportunity 但缺
completion 时 coalition unavailable；证据完整的显式零保持 available `0`。既有 explicit success、
command-only、summary-only、source mismatch 和 standby reserve 回归均未退化。

接受门限全部满足。`metric_availability`、coalition metadata、episode CSV、aggregate JSON 和
Markdown 使用相同 unavailable reason。D6 全量结果为 `150 passed`，另有 1 条既有 matplotlib
`Axes3D` 环境 warning。该结果关闭 D6 consumer/reporting P0，不构成新 AirSim 性能证据；真实
同条件 multi-seed physical 重跑和 freshness 趋势仍为 P1。

## 0.3 2026-07-14 truth-state provenance 与 offline scorer 回归（历史）

本轮未启动 AirSim，使用 7 类确定性离线 provenance 场景，seed 不适用：

| 场景 | 接受标准 | 实际结果 |
|---|---|---|
| D2 estimated-state 严格路径 | state-use available `0`，合法 offline physical available | 通过 |
| 显式 actor-truth fixture | state-use 为正，identity 独立，合法 fixture physical available | 通过 |
| 缺 source legacy status | 所有 physical 层 unavailable，raw status 仅审计 | 通过 |
| summary + command，command 缺 pair evidence | command 不生成 physical pair，所有 physical 层 unavailable | 通过 |
| summary-only aggregate | summary count 不回填 pair/target/coalition，全部 unavailable | 通过 |
| active pair source mismatch | 即使 evidence=true，所有 physical 层 unavailable 并给出 mismatch reason | 通过 |
| command CSV evidence 字段 | 布尔值由 loader 保留，但不能单独发布 physical success | 通过 |

实际 D6 全量为 `143 passed`，另有 1 条既有 matplotlib `Axes3D` 环境 warning。接受门限保持
availability/zero 分离：证据缺失输出 `None/unavailable`，不输出 false success 或 0。

这只关闭 D6 consumer/metric/loader/test 的 physical provenance P0，不是新物理性能证据，
也不表示真实 AirSim P1 完成。2026-07-11 至 07-13 历史报告中的 physical 数值若没有合法
`physical_intercept_source`、逐 active pair `physical_evidence_available=true` 和匹配的
`target_state_source`，只保留迁移前 raw status 含义。真实新 schema 的同条件 multi-seed
AirSim 重跑、逐 pair provenance 和 target-state freshness 趋势仍为 P1。

## 0.2 2026-07-14 truthless tracking 假零回归

本轮未启动 AirSim，使用 5 个确定性离线场景，seed 不适用：

| 场景 | 接受标准 | 实际结果 |
|---|---|---|
| 空输入 | RMSE/continuity/IDSW 均 null/unavailable | 通过 |
| 仅匿名 `TrackRecord` | 三项均 null/unavailable，JSON/CSV/Markdown 一致 | 通过 |
| truth sidecar 不完整 | RMSE/continuity 不补零；已有 identity pair 的 IDSW 为 available 0 | 通过 |
| 完整 truth、稳定 global ID | RMSE/continuity available，IDSW available 0 | 通过 |
| 完整 truth、global ID 切换 | IDSW available 1 | 通过 |

另用遗留 replay 中“数值 0 + availability unavailable”验证 merge：三项输出保留显式字段但值
为 null，状态仍 unavailable。2026-07-14 D6 全量结果为 `137 passed`，1 条既有 matplotlib
`Axes3D` 环境 warning。该结果关闭 truthless 假零的评估级 P0，不是物理性能实验；真实
multi-seed seed/provenance 与 D2 lifecycle-D3 churn join 仍为 P1。

## 0.1 2026-07-14 第二批 canonical history 回归

本轮使用与 D3 `d3_plan_history_record_v1`、main `d3_plan_history_v1` wrapper 同形的离线 JSON
fixture，不启动 AirSim。验收矩阵包括：

| 场景 | 验收结果 |
|---|---|
| 两 tick 稳定历史，重复携带同一 membership audit | 三项 version/epoch churn、总体/primary/reserve membership、owner、soft/hard feedback 均为 available 0 |
| plan、coalition version 与 epoch 变化 | 三项 churn 分别为 1 |
| primary 移除/新增、reserve activation 变化 | 总体 membership=3、primary=2、reserve=1 |
| center 到 secondary owner 切换 | owner change=1 |
| 两 tick soft/hard feedback | soft=3、hard=1 |
| sequence 乱序、重复 index、timestamp 倒退 | history 指标 unavailable，并写出对应原因码 |
| 单记录、record schema/count/order key 错误 | history 指标 unavailable，不输出假零 |
| canonical record 无 truth 字段 | 正常计算；不要求 online truth |

验收日期为 2026-07-14，专项结果 `24 passed`，D6 全量 `132 passed`，另有 1 条本机
matplotlib `Axes3D` 环境 warning。CSV 输出 validation status/reasons，aggregate JSON 含
`d3_history_validation`，Markdown 含 D3 canonical history 专节。

该结果关闭 D6 canonical schema/metric/report 接线，不代表新的 AirSim 物理性能结论。真实
multi-seed episode 趋势和跨批次 failure taxonomy 仍是 P1；P2 external benchmark 状态不变。
以下第一批回归与更早实验均为历史内容。

## 0. 2026-07-14 第一批 D3 churn availability 回归（历史）

本轮是离线评估语义回归，没有启动 AirSim，也没有修改 D3 或任何控制模块。测试输入为 5 类：
最终快照、空 mapping、单条无序记录、两条稳定有序历史、顶层显式零。四项验收指标为
`plan_version_churn_count`、`coalition_version_churn_count`、
`coalition_epoch_churn_count` 和 `membership_change_count`。

验收门限是：前三类四项必须全部 `unavailable`；两条字段完整且稳定的有序历史必须全部为
available `0`；顶层显式零必须全部为 available `0`。正式 40-case cooperative-role fixture
还必须维持角色统计并让四项 churn 全部 unavailable。2026-07-14 实际结果满足全部门限：
专项 `12 passed`、D6 全量 `120 passed`，另有 1 条本机 matplotlib `Axes3D` 环境 warning。

该评估级 P0 已闭合。剩余 P1 不是从历史快照推断，而是由 main/D3 生产真实有序 plan
history、统一时钟、version/epoch、provenance 和 availability，并持续形成长期 multi-seed
趋势及稳定 failure reason taxonomy。P2 外部指标工具继续保持 optional/offline。以下合成
批量示例和 2026-07-13 及更早实验结果均为历史内容，不覆盖本节当前结论。

## 1. 实验边界

D6 是离线评估模块，只消费记录、仿真日志或脱敏数据，输出指标、表格和图表。它不参与实时任务决策，不提供火控参数，不建模毁伤，不自动处置目标，也不绕过人工授权。

## 2. 实验目的

D6 的目标是避免只用“命中率”评价系统，而是同时覆盖探测、跟踪、分配、降级、末端配准、二级视角/侦察、通信、D7 gate/intercept 和安全约束。本轮示例实验验证：

- `EpisodeMetrics` 能否统一记录所有关键指标。
- D3 未授权候选分配是否不会被算作有效分配。
- 高威胁目标在无有效分配时是否被正确计为未分配。
- D5 的 `TerminalRecord` 与 `EventRecord` 是否不会对同一歧义/友方 hold 事件双计数。
- 报告是否按实际 `drone_count/resource_count/target_count/camera_count` 分组，而不是从 `2v2/5v5` baseline 名称推断规模。
- D6 是否只消费已写盘日志和 metrics，不参与控制、重规划、云台指向或 D7 导引。

详细算法原理、公式、日志来源和 D4/D5 后续扩展字段见 `docs/ALGORITHM_AND_IMPLEMENTATION.md`。

## 3. 批量实验配置

运行命令：

```bash
python3 research_modules/d6_evaluation_metrics/scripts/run_batch_example.py --seeds 100
```

| 项目 | 设置 |
|---|---:|
| 数据来源 | 合成离线日志 |
| episode 数 | 100 |
| 单 episode 时长 | 60 s |
| 输出目录 | `outputs/example_batch/` |

## 4. 指标体系

| 类别 | 指标 |
|---|---|
| 探测 | `detection_probability`, `false_alarm_rate`, `missed_detection_rate` |
| 跟踪 | `track_rmse`, `track_continuity`, `id_switch_count` |
| 分配 | `duplicate_assignment_count`, `unassigned_high_threat_count` |
| 降级 | `failover_time`, `consensus_rounds`, `degraded_completion_rate`, `passive_failover_count`, `active_degradation_count`, `active_degradation_precision`, `unnecessary_active_degradation_count`, `secondary_node_takeover_count`, `secondary_reassignment_count`, `d4_reassign_pending_count`, `distributed_fallback_count`, `failover_active_window_delta_s` |
| 末端 | `terminal_association_accuracy`, `terminal_id_switch_count`, `ambiguous_fov_event_count`, `friend_overlap_hold_count`, `time_to_terminal_lock`, `multi_view_consensus_rate`, `cross_view_conflict_count`, `duplicate_terminal_lock_count` |
| 二级视角/侦察 | `secondary_network_joint_full_view_frame_rate`, `secondary_network_mean_coverage_ratio`, `secondary_visible_target_union_ratio`, `secondary_detect_count`, `projection_valid_rate`, `geometry_gate_pass_rate`, `registered_candidate_count`, `stable_cross_view_registration_count`, `not_registered_count`, `cue_pointing_error_*`, `gimbal_pointing_error_*` |
| 通信 | `cross_node_latency_ms`, `message_drop_rate`, `out_of_order_count`, `stale_track_update_count`, `video_metadata_delivery_rate`, `bbox_delivery_rate`, `consensus_latency_s` |
| D7 gate/intercept | `camera_quality_gate_pass_rate`, `los_quality_gate_pass_rate`, `maneuver_margin_gate_pass_rate`, `terminal_switch_allowed_rate`, `visual_png_switch_count`, `terminal_takeover_rate`, `terminal_switch_reject_count`, `mode_switch_count`, `terminal_contract_reject_count`, `intercept_success_count`, `collision_intercept_count`, `range_intercept_count`, `time_to_intercept_s`, `min_range_m`, `gate_reject_count` |
| 安全 | `constraint_violation_count`, `human_override_count` |

`active_degradation_precision` 和 `unnecessary_active_degradation_count` 已进入 D6 P1 最小实现。它们只消费 D4/main 写出的 `review_label`、`active_degradation_necessary`、`post_window_outcome` 或 pre/post risk/window 后验字段；缺 label 的主动降级不进入 precision 分母。`terminal_center_disagreement_count`、`time_to_active_degradation_decision`、`post_degradation_id_switch_delta` 和 `post_degradation_assignment_conflict_delta` 仍是后续扩展质量指标。

## 5. 图表与曲线

### 5.1 探测指标统计图

![D6 探测指标统计图](outputs/example_batch/plots/detection_metrics.png)

该图展示探测概率、虚警率和漏检率的批量均值及置信区间，用于评估前端探测网是否稳定。

### 5.2 跟踪指标统计图

![D6 跟踪指标统计图](outputs/example_batch/plots/tracking_metrics.png)

该图展示 RMSE、航迹连续性和 ID Switch。ID Switch 应与 D2 的身份连续性结果一起分析，避免只看覆盖率。

### 5.3 分配与降级指标图

![D6 分配指标统计图](outputs/example_batch/plots/assignment_metrics.png)

![D6 降级指标统计图](outputs/example_batch/plots/degradation_metrics.png)

分配图用于检查重复分配和高威胁未分配。降级图用于分析中心节点失效后的接管耗时、共识轮数和任务完成率。

### 5.4 末端与安全指标图

![D6 末端指标统计图](outputs/example_batch/plots/terminal_metrics.png)

![D6 安全指标统计图](outputs/example_batch/plots/safety_metrics.png)

末端图反映终端锁定准确率、终端 ID Switch、视场歧义和友方 hold。安全图用于记录约束违反和人工覆盖事件。

### 5.5 关键指标分布曲线

![D6 关键指标分布曲线](outputs/example_batch/plots/selected_metric_distributions.png)

分布图用于发现均值掩盖的长尾问题。例如少数 episode 的 ID Switch 或 safety violation 可能比平均值更值得关注。

## 6. 输出文件

| 文件 | 用途 |
|---|---|
| `episode_metrics.csv` | 每个 episode 一行 |
| `summary_metrics.csv` | 每个指标的均值、标准差、置信区间和分位数 |
| `batch_report.md` | 自动生成的批量摘要 |
| `plots/*.png` | 指标族图和分布图 |
| `logs/*.jsonl` | 原始离线记录 |
| `d6_airsim_calibration/airsim_calibration_records.csv` | P1 AirSim calibration episode/scope 记录 |
| `d6_airsim_calibration/airsim_calibration_summary.csv` | 按 `metric_scope/seed/scenario/secondary_height/FOV/secondary_count/detection_backend` 汇总 |
| `d6_airsim_calibration/airsim_calibration_summary.json` | calibration summary 机器可读版本 |
| `d6_airsim_calibration/airsim_calibration_report.md` | 中文 P1 AirSim calibration 报告 |

## 7. 结论

D6 已能覆盖探测、跟踪、分配、降级、末端、二级视角/侦察、通信、D7 gate/intercept 和安全指标。当前 P1 AirSim calibration report generator 已能输出 coverage、projection/gate、stable registration、`not_registered_count`、active degradation review label 和 D7 guidance reject reason；剩余工作是让 main/D4/D5/D7 在更多多 seed、5v5/N-v-N 和非默认 episode 中持续写出同一时间轴、actual scale 和 execution/contract 双口径数据，用于长期趋势而不是单次结论。

## 8. D2 准入 Schema 兼容回归（2026-07-15）

本批为离线 parser/report 回归，没有启动 AirSim，也没有新增真实 episode、seed 或物理拦截
结果。验证样本是最小 JSON-like fixture：

| 案例 | 预期 | 结果 |
|---|---|---|
| v2 failed gate | 优先输出 `gate_name:具体 reason` | 通过 |
| v2 all gates passed | 空失败列表为 available，不制造失败 | 通过 |
| legacy structured checks | 读取 `passed/reason` | 通过 |
| legacy bool checks | 失败时至少保留 check name | 通过 |
| 历史缺字段 | 数值为 `None`/CSV 空值，availability 为 unavailable | 通过 |
| promotion 语义 | recommendation-only，不改变控制或默认在线路径 | 通过 |

示例 `0.9810 -> 0.9840` 可原样保留为 headroom `0.0190`、actual increase `0.0030`、
required increase `0.0019`、error reduction 约 `0.1579`。该示例只证明字段兼容，不代表
D6 独立批准候选；历史 artifact 若缺 false-track 或完整 gate evidence，整体评审仍不能
由 D6 推断。

测试结果：`test_p1_system_evidence.py` 为 `29 passed`；D6 全量为 `241 passed`，另有一条
Matplotlib `Axes3D` 本机环境 warning。本批没有 AirSim 图像或曲线，因为能力变化仅涉及
离线 schema 兼容，不应伪造新的仿真证据。

## 9. 三维规模化真值隔离接口验证（2026-07-20）

本批是 D6 公共合同测试，不是算法性能实验。输入为最小 D1/D2 公开制品 fixture，覆盖
5、20、50、100、200 五档实际目标/资源数量。测试没有启动 AirSim，没有生成三维运动
样本，也没有使用正式训练或未见 seed。

验证项目和结果如下：

| 验证项 | 样本 | 结果 |
| --- | ---: | --- |
| D1 公共 DTO 与 sensor/range 聚合 | 2 条逐观测记录 | RMSE、NEES、NIS、样本数和摘要保留正确 |
| D1 `d2_lineage_mapping` | 1 个规范字段正例 | result、aggregation、CSV/JSON/中文报告均成功且名称稳定 |
| D1 legacy `canonical_mapping` | 1 个兼容正例 | 输入成功，输出规范化为 `d2_lineage_mapping` |
| D1 新旧字段冲突 | 1 个负例 | 摘要不同时制品被拒绝 |
| D1 映射摘要缺失 | 1 个负例 | truth metrics 可用时制品被拒绝 |
| D2 公共 DTO | 10 帧汇总 fixture | IDSW、连续率、重复和混淆矩阵保留正确 |
| D2 真值隔离未验证 | 1 个负例 | 身份指标全部 `None/unavailable` |
| unavailable IDSW 携带零值 | 1 个负例 | 制品被拒绝 |
| D2 零帧且 IDSW=0 | 1 个负例 | IDSW 为 `None/unavailable`，truth counts 不聚合 |
| D1 availability=false 但残留数值 | 1 个负例 | 制品被拒绝 |
| 外部文件 SHA-256 篡改 | 1 个负例 | 制品被拒绝 |
| D1 内部 content digest 篡改 | 1 个负例 | 制品被拒绝 |
| 跨 episode 混用 | 1 个负例 | context 校验拒绝 |
| 五档动态规模 | 5 个 episode fixture | 均按实际规模独立分组 |
| CSV/JSON/中文 Markdown | 2 个 episode fixture | 空值、显式零、原因和来源摘要保持分离 |

专项测试为 `14 passed`，D6 全量为 `334 passed`，另有一条既有 Matplotlib `Axes3D` 环境
warning。验收门限是全部合同测试通过，当前已经满足。正式 D1 RMSE/NEES/NIS、D2 IDSW/
continuity 和 200 对 200 运行性能没有证据，仍待 main 按至少 20 个未见 seed 评估。
