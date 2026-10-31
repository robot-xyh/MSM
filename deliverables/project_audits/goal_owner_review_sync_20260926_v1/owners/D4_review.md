# D4 原 Goal 历史证据复核

核查日期：2026-09-26。历史日期逐项另列。本文件与同目录 `D4_review.json` 是本轮仅有的写入文件。

## 结论

按主表 owner 显式 D4 及范围式 Dn至Dm 闭区间筛选，共 15 项，覆盖 G04、G16、G20、G30、G32、G36、G38、G40、G44、G47、G49、G51、G55、G57、G59。共享要求仅复核 D4 相关证据，不代替其他模块所有者判断。

意见：认可 4 项、限定认可 9 项、需修订 1 项、证据不足 1 项。建议状态维持原表：部分完成 10 项、未完成 4 项、证据不足 1 项；没有建议升级为已完成。`suggested_status` 是审计意见，不是模块状态变更。

主要异议为 G55：D4 模块文档顶部仍停在来源 0/324、等待授权或生成待办；主级后续审计及保存元数据已到 324/324、921 条记录。主级“原断点进展文档已同步保存”须限定为主级进展已保存，不能理解为 D4 文档全部同步。该不一致已登记，本轮不修改原文。

## 证据层级

- 已实现：只认可已有规则路径、版本/租约/联盟 ACK 合同及历史软件记录，不外推自主成员形成、真实网络或最终闭环效果。
- 历史验证：2026-07-13 episode-clock 60-case 安全矩阵、旧小规模正负例只覆盖各自场景；本文所有历史通过数都不是本轮测试。
- 独立评价：2026-07-30 旧 v7 的 M16N24、64 episode/128 帧记录中，validation/test 精确正动作均为 0/9，保持失败关闭；不能替代当前 v8。
- 原 Goal 统一验收：当前 v8 未训练，validation/test 来源未冻结，完整统一故障矩阵和最终比较未完成。独立演示或后续报告不能填补。

正式 450 组继续登记为“摘要可查、完整记录未定位”。其来源为 `80e55eb`、shard 0-9、seed 1000-1009；旧 D4 900 组诊断绑定 `1e5ed8d`，不是同一批次。728 组是 D3/D4/D5 的来源生成总量，不能替代 450 组，也不能相加。

D4 v8 正式来源为 324 个 TRAIN episode、seed 28100-28423、921 条来源记录。预生成 viability 的 972 帧是另一个口径；模块文档另有历史 `921/921` 测试计数，也不是来源记录数。

除仓库内审计、模块文档和保存报告外，仅定点读取已知 `6737b44` D4 来源目录的 `generation_session.json` 与 `generation_checkpoint.json`。保存 checkpoint 为 `finalized`、324/324、remaining=0、`training_started=false`；仓库内定位入口为 [D05]。未读取样本载荷或原始真值。

## 逐项意见

### G04

原状态：部分完成；意见：限定认可；建议状态：部分完成。历史日期：2026-07-31、2026-08-03。

认可 D4 在线输入真值隔离的合同与历史来源审计证据。450 组的在线真值使用为零仅是 2026-07-31 保存摘要；728 组来源审计中的 D4 为 324 组 TRAIN 来源，不能替代正式 450 组。D4 对 D2 不可用身份指标的门控也不能证明完整系统每组均无泄漏。

缺证据：正式 450 组完整在线记录、清单及可绑定的逐组隔离证据未定位。 原 Goal 最终同版本全矩阵的真值隔离验收未完成。

依据：[D01]、[D03]、[D04]、[D05]、[D14]。

### G16

原状态：部分完成；意见：限定认可；建议状态：部分完成。历史日期：2026-07-31、2026-08-03。

D4 文档支持匿名摘要消费、版本及租约约束和已有区域接口；不等于统一总线订阅闭环。原审计明确 D1 总线摘要双时间戳不全、D1-D3 仍有对象直传；另须区分 D4 风险摘要可读取协方差与 A2 v8 TRAIN 来源不含协方差，不能把前者外推为后者字段完整。

缺证据：缺原 Goal 同版本逐消息双时间戳、协方差及订阅消费链的完整记录。 当前来源字段边界未被最终统一消息验收覆盖。

依据：[D01]、[D10]、[D12]。

### G20

原状态：部分完成；意见：限定认可；建议状态：部分完成。历史日期：2026-08-03、2026-08-07。

规则层 epoch、lease、计划版本、过期拒绝和联盟完整 ACK 合同有历史实现依据。D4 GAP 仍列自主成员形成、真实通信、恢复双轨日志及多种子完整故障验证缺口，不能概括为所有联盟能力完成。主级后续临时中心机表述属方案，现有完全分布式路径未因此替换；A2 v8 来源完成也不是降级性能验收。

缺证据：缺冻结完整故障矩阵及真实通信、恢复、主动降级准确率的统一验收记录。 后续临时中心机方案没有对应正式实现与统一验证证据。

依据：[D01]、[D02]、[D14]、[D16]、[D05]。

### G30

原状态：部分完成；意见：限定认可；建议状态：部分完成。历史日期：2026-07-30、2026-08-03、2026-08-07。

A2 v8 的 324 个 TRAIN episode、921 条来源记录有主级审计及保存元数据支持；已只读核对既知 generation_session/checkpoint，状态 finalized、324/324，training_started=false。旧 v7 的来源独立 validation/test 精确正动作均为 0/9，不能当作 v8 成果；预生成 viability 的 972 帧也不是正式 921 条记录。模块顶部 0/324 为滞后阶段快照，不能否定后续来源完成，见 G55。

缺证据：v8 冻结模型、模型卡、训练结果及独立 validation/test 来源与评价未完成。 D4 模块文档缺后续来源完成和独立审计状态的明确衔接。

依据：[D01]、[D02]、[D05]、[D06]、[D17]、[D08]。

### G32

原状态：部分完成；意见：限定认可；建议状态：部分完成。历史日期：2026-07-22、2026-07-30、2026-08-03。

可认可确定性投影、异常拒绝和规则回退的软件及历史局部证据。旧 v7 的不变量失败为零与独立正动作 0/9 同时成立，说明安全外层通过并不代表学习有效。旧 nominal 5v5 的 20-seed 隔离记录仅是门控/回退证据，既不授予线上权限，也不证明当前 v8 和全变体非退化。

缺证据：缺当前冻结 v8 的独立安全评价及同键全变体非退化结果。 缺最终统一矩阵逐组异常与回退记录。

依据：[D01]、[D14]、[D17]、[D12]。

### G36

原状态：未完成；意见：认可；建议状态：未完成。历史日期：2026-08-03、2026-08-07。

D4 责任范围内，当前 v8 只完成来源生成和来源完整性审计，未训练、未形成正式 A2 对照。主级记录同样区分 A1 v3、A3 v3 的来源与模型。旧候选或后续独立实验都不能替代当前代际学习方案的正式比较；本意见不替代 D3/D5 对其制品的所有者复核。

缺证据：缺当前代际冻结模型及原 Goal 同版本、同种子、同外生输入的独立正式对照。

依据：[D01]、[D02]、[D05]。

### G38

原状态：未完成；意见：认可；建议状态：未完成。历史日期：2026-07-13、2026-08-03、2026-08-07。

D4 规则接口、历史 episode-clock 安全矩阵及小规模接管正负例只能证明各自范围。文档明确真实网络、成员重构及恢复统计开放，原 Goal F1 完整体系尚无统一验收。独立视觉或中心交接演示不能补成 F1 结果。

缺证据：缺 F1 同一冻结体系的完整故障矩阵、至少 20 个未见种子完整时长结果与统一评估。

依据：[D01]、[D02]、[D14]、[D12]。

### G40

原状态：部分完成；意见：限定认可；建议状态：部分完成。历史日期：2026-07-30、2026-07-31、2026-08-03。

局部旧 epoch/过期 lease/不完整 ACK 拒绝合同支持部分完成，不能外推全部实验零违规。2026-07-30 D4 联盟诊断引用的是 1e5ed8d 的旧 900 组，且记录计划代次错位；本批正式 450 组绑定 80e55eb，两者不能混合，也不能用旧批错误直接断言新批仍有同样错误。

缺证据：缺 80e55eb 正式 450 组完整逐组版本、重复授权和硬约束记录。 缺最终统一验收范围下各项零违规的完整分母与可追溯证据。

依据：[D01]、[D14]、[D18]、[D03]、[D04]。

### G44

原状态：未完成；意见：认可；建议状态：未完成。历史日期：2026-07-22、2026-07-30、2026-08-03、2026-08-07。

配对比较框架及旧候选规则回退记录不等于当前代际学习非退化验收。旧 v7 来源独立正类行为失败，旧 20-seed nominal 记录无物理 outcome/paired non-degradation；v8 未训练，因此没有可据以认可当前模型不增加身份交换、重复分配和违规的统一结果。

缺证据：缺当前冻结 A2 与同键 R0 的完整独立配对记录、指标可用性及统一非退化判定。

依据：[D01]、[D02]、[D17]、[D12]。

### G47

原状态：未完成；意见：认可；建议状态：未完成。历史日期：2026-08-03、2026-08-07。

原审计明确当前代际最终显存验收未形成，v8 checkpoint 只证明来源完成且训练未启动。旧候选、其他模块或独立实验的单模型显存不能代表原 Goal 冻结体系在 RTX4050 上达到 5GB 目标；本轮未查询或使用 GPU。

缺证据：缺绑定 v8 冻结模型、执行环境、运行配置和峰值显存口径的历史验收记录。

依据：[D01]、[D02]、[D05]。

### G49

原状态：部分完成；意见：限定认可；建议状态：部分完成。历史日期：2026-08-03。

522 passed 是原主模块历史摘要，不是本轮验证。D4 2026-08-03 文档另记自包含回归 974 passed/12 skipped/1 deselected，全量命令 986 passed/12 skipped/5 failed/15 errors，并将问题归因于 clean worktree 缺历史制品；不得省略这些限定后宣称最终全模块回归全绿。本轮既未复跑也未重新裁定该历史归因。

缺证据：缺最终同冻结版本全模块回归交付和依赖制品可用性记录。 历史缺制品全量命令不能作为全部测试通过的证明。

依据：[D01]、[D08]、[D13]、[D07]。

### G51

原状态：部分完成；意见：限定认可；建议状态：部分完成。历史日期：2026-08-03、2026-08-07。

代码、旧候选及来源生成保存记录只支持交付的一部分。D4 v8 的 finalized 是数据生成状态，training_started=false；不得把 generation_checkpoint 当模型 checkpoint，也不得把旧 BC/v7 权重当当前 v8 模型交付。

缺证据：缺 v8 模型检查点、冻结配置、模型卡及绑定独立评价的最终交付校验清单。

依据：[D01]、[D02]、[D05]、[D08]。

### G55

原状态：部分完成；意见：需修订；建议状态：部分完成。历史日期：2026-08-03、2026-08-07。

建议保留部分完成，但修订主级理由中笼统的“原断点进展文档已同步保存”：D4 README、PLAN、原理、算法、GAP、两份 review 和实验报告的最新相关段落仍停在 fcf8525 preflight、来源 0/324 或生成待办；保存 session/checkpoint 与主级后续审计已到 6737b44、324/324、921 条来源记录。应明确这是阶段快照未衔接的现成文档不一致，而非来源未完成。临时中心机方案与现有实现仍需分别登记，分支继承也不是 main 验收合并。

缺证据：缺 D4 模块文档对后续来源完成及审计断点的同步说明。 缺原 Goal 最终验收、满足条件后合并与交付完成记录。

依据：[D08]、[D09]、[D10]、[D11]、[D14]、[D15]、[D16]、[D13]、[D02]、[D05]。

### G57

原状态：部分完成；意见：限定认可；建议状态：部分完成。历史日期：2026-07-31、2026-08-01、2026-08-03。

版本、来源请求和哈希绑定合同存在，保存 D4 session/checkpoint 能区分 fcf8525 preflight 与 6737b44 实际生成身份。VERSIONING 的 2026-08-01 请求阶段表述是历史快照，不是后续生成否定证据。正式 450 组只剩摘要身份，当前模型版本也未冻结，不能从 manifest 代码存在推断全批制品齐全。

缺证据：正式 450 组原始运行 manifest 及完整载荷未定位。 缺当前 v8 冻结模型版本与最终统一运行配置绑定。

依据：[D19]、[D10]、[D05]、[D03]、[D04]。

### G59

原状态：证据不足；意见：证据不足；建议状态：证据不足。历史日期：2026-07-30、2026-08-03、2026-08-07。

保存要求和旧 v7 state/model 摘要只证明历史模型身份曾有记录，不能证明当前 v8 模型已经交付或 LFS 远端可取。v8 尚未训练；主表关于长期保存的证据不足判断合理。本轮不查询远端或逐个验证 LFS 对象，也不把有 SHA256 等同于可复载或长期可达。

缺证据：缺当前 v8 最终权重及模型说明、配置和 SHA256 绑定。 缺相应长期制品或 LFS 对象与远端可达性的实际核验记录。

依据：[D19]、[D01]、[D02]、[D17]。

## 文档核对

检查方式为相关日期段落、状态表与边界定点审读，不宣称逐行复审全部长文档。9 份现有文件已核对，另确认 2 个指定 docs 路径不存在；对应文件实际位于 reports。所有原文件均未修改。

| 文件 | 存在 | 核对结果 |
| --- | --- | --- |
| `research_modules/d4_distributed_fallback/README.md` | 是 | 顶部 2026-08-03 仍写来源 0/324、待 generation-only 授权；与后续保存 finalized 324/324 记录未衔接，登记 G55。 |
| `research_modules/d4_distributed_fallback/PLAN.md` | 是 | 生成与审计仍为未勾选后续门；主级后续来源完成断点未回写。属于既存进展同步缺口，不在本轮勾选。 |
| `subagent_reviews/D4_IMPLEMENTATION_GAP_AUDIT.md` | 是 | 顶部仍写来源 0/324；后续来源审计进展未衔接。已实现合同与真实网络、恢复、M 对 N 完整验证开放边界仍需保留；本轮不改变任何 GAP。 |
| `subagent_reviews/D4_DISTRIBUTED_FALLBACK_REVIEW_AND_PLAN.md` | 是 | 顶部停在重冻结/preflight 和 0/324；主级后续 324/324 未衔接，登记 G55。 |
| `subagent_reviews/D4_M_TO_N_DISTRIBUTED_COALITION_REVIEW.md` | 是 | 顶部 0/324 与后续来源完成不一致；原子 ACK、联盟权限及来源不等于执行的限定仍有效。 |
| `research_modules/d4_distributed_fallback/docs/MODULE_PRINCIPLES_CN.md` | 是 | 来源绑定原则仍写 0/324；需区分原则合同与当时进展快照，登记 G55，原则本身未变化。 |
| `research_modules/d4_distributed_fallback/docs/ALGORITHM_AND_IMPLEMENTATION.md` | 是 | 顶部仍称尚未生成 324 项；版本绑定/任务基数合同是已有实现，不能据该旧进展否定后续来源完成。 |
| `research_modules/d4_distributed_fallback/docs/AIRSIM_INTEGRATION_PLAN.md` | 否 | 指定 docs 路径不存在；对应现有文件位于 reports/AIRSIM_INTEGRATION_PLAN.md，已核对，不新建重复文档。 |
| `research_modules/d4_distributed_fallback/reports/AIRSIM_INTEGRATION_PLAN.md` | 是 | 实际位于 reports。2026-07-31 明确无新 AirSim episode，旧质点/episode-clock 安全结果不等于真实链路或当前 v8/F1 验收；没有本轮 AirSim 能力或证据变化需要回写。 |
| `research_modules/d4_distributed_fallback/docs/EXPERIMENT_REPORT.md` | 否 | 指定 docs 路径不存在；对应现有文件位于 reports/EXPERIMENT_REPORT.md，已核对，不新建重复文档。 |
| `research_modules/d4_distributed_fallback/reports/EXPERIMENT_REPORT.md` | 是 | 实际位于 reports。顶部仍为正式来源 0/324；另保留历史全量测试 5 failed/15 errors，不能只摘通过数；预生成 viability 972 帧不等于正式来源 921 条。 |

不回写原因：本轮无能力变更、GAP 关闭或新实验验证，且 main 仅授权本批两份 D4 审阅文件。发现的来源进展滞后、历史批次差异及方案/实现差异只在审计中登记；不把审计意见用于变更既有能力状态，也不制定新的实施路径。

## 文件检查

普通文件检查已通过：JSON 解析及重复键检查、规定字段和枚举、owner 范围筛选、15/15 编号覆盖、15/15 原状态一致、意见与状态计数一致；19/19 唯一证据路径及 Markdown 引用路径存在，且均指向仓库内文件。两文件均有末尾换行且无行尾空白。

documentation_checked 共 11 项：9 份现有文件、2 个预期不存在的 docs 路径，实际 reports 文件已核对。D4 九份原文、原 CSV、逐项明细及两份原 Goal 审计/进展报告共 13 份文件，在本轮审阅文件写入前后 SHA256 一致。这是普通文件完整性检查，不是历史实验重验。

本轮没有运行模块 pytest、训练、GPU、AirSim、控制或重新评分，没有全盘扫描，没有委托子智能体。复现结论仅为证据审读，不认证可重跑或可重新评分。

## 证据索引

[D01]: ../../../../research_modules/scalable_3d_simulation/docs/SCALABLE_3D_GOAL_COMPLETION_AUDIT_20260803_CN.md
[D02]: ../../../../research_modules/scalable_3d_simulation/docs/SCALABLE_3D_GOAL_PROGRESS_AND_NEXT_PLAN_20260807_CN.md
[D03]: ../../../../research_modules/scalable_3d_simulation/docs/SCALABLE_3D_FORMAL_R0_80E55EB_SHARDS0_9_20260731_CN.md
[D04]: ../../../../deliverables/project_audits/goal_resume_audit_20260926_v1/历史结果定位与完整性核对_CN.md
[D05]: ../../../../deliverables/project_audits/goal_resume_audit_20260926_v1/SOURCE_DIRECTORY_STATUS.json
[D06]: ../../../../deliverables/project_audits/goal_resume_audit_20260926_v1/SUPPLEMENTAL_CHECKS.json
[D07]: ../../../../deliverables/project_audits/goal_resume_audit_20260926_v1/VERSION_DIFFS.json
[D08]: ../../../../research_modules/d4_distributed_fallback/README.md
[D09]: ../../../../research_modules/d4_distributed_fallback/PLAN.md
[D10]: ../../../../research_modules/d4_distributed_fallback/docs/MODULE_PRINCIPLES_CN.md
[D11]: ../../../../research_modules/d4_distributed_fallback/docs/ALGORITHM_AND_IMPLEMENTATION.md
[D12]: ../../../../research_modules/d4_distributed_fallback/reports/AIRSIM_INTEGRATION_PLAN.md
[D13]: ../../../../research_modules/d4_distributed_fallback/reports/EXPERIMENT_REPORT.md
[D14]: ../../../../subagent_reviews/D4_IMPLEMENTATION_GAP_AUDIT.md
[D15]: ../../../../subagent_reviews/D4_DISTRIBUTED_FALLBACK_REVIEW_AND_PLAN.md
[D16]: ../../../../subagent_reviews/D4_M_TO_N_DISTRIBUTED_COALITION_REVIEW.md
[D17]: ../../../../research_modules/d4_distributed_fallback/reports/D4_V7_SOURCE_INDEPENDENT_EVALUATION_20260730.md
[D18]: ../../../../research_modules/d4_distributed_fallback/reports/FORMAL_R0_COALITION_ACK_DIAGNOSTIC_20260730.md
[D19]: ../../../../research_modules/scalable_3d_simulation/VERSIONING.md
