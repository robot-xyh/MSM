# D6 当前证据状态

<!-- evidence-status-sync:20260926:begin -->
同步日期：2026-09-26。本页是 D6 唯一集中的当前证据状态说明；其他入口只提供链接。
本轮仅做资料同步，不是新的实验日期，不新增结果、修改阈值、勾选任务或关闭 GAP。
原 Goal 仍未完成；模块能力与原 Goal 状态不因文档同步而改变。旧章节仅按其原日期、来源及范围作为历史阶段记录阅读。

## 来源与历史日期

- [D6 所有者复核](../../../deliverables/project_audits/goal_owner_review_sync_20260926_v1/owners/D6_review.json)：2026-09-26 审读 24 项，未运行实验。
- [原 Goal 完成审计](../../scalable_3d_simulation/docs/SCALABLE_3D_GOAL_COMPLETION_AUDIT_20260803_CN.md)与[8 月 7 日进展](../../scalable_3d_simulation/docs/SCALABLE_3D_GOAL_PROGRESS_AND_NEXT_PLAN_20260807_CN.md)：原统一验收边界。
- [正式 R0 前十分片报告](../../scalable_3d_simulation/docs/SCALABLE_3D_FORMAL_R0_80E55EB_SHARDS0_9_20260731_CN.md)：2026-07-31 历史摘要，不是本轮重算。
- [历史结果定位](../../../deliverables/project_audits/goal_resume_audit_20260926_v1/历史结果定位与完整性核对_CN.md)与[保存校验记录](../../../deliverables/project_audits/goal_resume_audit_20260926_v1/SUPPLEMENTAL_CHECKS.json)：9 月主级文件核对；本轮不重复载荷或语义审计。
- [专项冻结清单](../../airsim_runtime/baselines/d5_long_range_20target_20260810/baseline_manifest.json)与[docs 实验报告](EXPERIMENT_REPORT.md)：2026-08-10 独立 v2 结果和 v3 软件接口边界。

## 已完成的有限范围

- D6 指标、逐 seed CSV、聚合 JSON、bootstrap 区间、三维图及中文 Markdown 代码有历史实现与验证记录；不等于最终结果已经交付。
- 2026-08-03 来源载荷审计覆盖 D3/D4/D5 的 300/324/104 组，分别为 3086/921/280968 条不同类型记录。
  状态仅为 `source_integrity_audit_passed_not_training_authorized`；来源真值及切分泄漏历史计数为 0，非审计权限保持关闭。
  D5 的 train/validation/future-held-out 为 48/24/32 组，future-held-out 只做完整性审计，没有模型消费。
  728 组来源不等于正式 450 组；来源字节完整性不证明模型质量或原 Goal 统一验收。
- 正式 R0 历史完成 450/900，producer `80e55eb`、evaluator `b6289c5`、执行计划逻辑哈希前缀 `b922ff5f`。
  shard 0-9、seed 1000-1009 覆盖五规模与九类场景；不是 450 个独立 seed。
  当前仍为“摘要可查、完整记录未定位”，不能宣称载荷恢复、可原样复现或本轮哈希通过。
- 2026-08-10 独立 v2 专项为 20 目标、2 相机、seed `20260810`、20 s；正确关联 1930/1934，准确率 0.9979317476732161。
  该高精度结果仍专项失败关闭：有效短缺口 3 未归零，绑定振荡不可用，实际交叉可评分 3/31，低于至少 10 个及比例 0.30 两项门限。
  新 v3 的字段、空文件处理和通过门只具备接口/合成记录，不能写成真实 v3 AirSim 验收。

## 未完成与不可外推范围

- A1 v3、A2 v8、A3 v3 当前代际训练、选模及统一独立评价未完成；旧模型和独立实验不能替代。
- 真实 v3 专项及其至少 10 seeds 完成证据不足；这一专项分母不等于原 Goal 至少 20 个未见 seeds。
- 原 Goal 七变体同版本、同 seed、同外生输入比较、完整时长物理结果、最终动画及验收 Word 未交付。
- 正式 450 组的完整载荷、原 manifest、D6 逐组 CSV 与聚合 JSON 未定位；后半 450 组没有本批完成证据。
- 严格 `id_switch_count` 的历史摘要为 414/450 可用、36 不可用，可用项合计 893 次；36 项不能补零。
  旧 900-cell 审计的部分安全指标也不可用，不能由局部零值推出统一矩阵违规全为零。
- 旧 900-cell 后验、其他执行计划归档、来源 728 组与当前 450 组分别登记，不累加或相互替代。
  D2 旧报告哈希对象标签错配已查明：`c9bf5e...` 对应 `ARTIFACT_SHA256SUMS`，`590514...` 对应 `artifact_inventory.json`，见[上一批主级复核](../../../deliverables/project_audits/goal_owner_review_sync_20260926_v1/MAIN_REVIEW.json)；这不等于正式 450 组载荷恢复，历史正文保持不变。

## 旧章节与入口对应

| 入口 | 历史更新范围与阅读方式 |
| --- | --- |
| [模块 README](../README.md)、[PLAN](../PLAN.md)、[文档索引](README.md) | 保留各日期实现、验证及旧待办；当前边界集中到本页，不改历史勾选。 |
| [根实验报告](../EXPERIMENT_REPORT.md) | 顶部为 2026-08-01 两个 2v2 受控 case，另保留更早实验；不包含 docs 报告的两项较新章节。 |
| [docs 实验报告](EXPERIMENT_REPORT.md) | 包含 2026-08-03 来源审计及 2026-08-10 长距离专项；与根报告互补，不是同一更新范围或最终统一报告。 |
| [实际 AirSim 计划](../AIRSIM_INTEGRATION_PLAN.md) | 位于模块根，保留 8 月 10 日专项及旧接入记录；`docs/AIRSIM_INTEGRATION_PLAN.md` 不存在，不建空壳。 |
| [模块原理](MODULE_PRINCIPLES_CN.md)、[算法说明](ALGORITHM_AND_IMPLEMENTATION.md) | 软件口径与接口证据；历史测试数量不是本轮测试结果。 |
| [GAP](../../../subagent_reviews/D6_IMPLEMENTATION_GAP_AUDIT.md)、[模块评审](../../../subagent_reviews/D6_EVALUATION_METRICS_REVIEW_AND_PLAN.md)、[M 对 N 评审](../../../subagent_reviews/D6_M_TO_N_EVALUATION_FRAMEWORK_REVIEW.md) | 旧关闭仅限原日期子项，保留失败与不可用项；本轮不关闭或重分类 GAP。 |

本页只整理已保存事实，不制定研究系统增强计划，不运行 pytest、模型、训练、GPU、仿真、配准、控制或重评分。
<!-- evidence-status-sync:20260926:end -->

[返回 D6 文档索引](README.md)
