# D4 当前证据状态

<!-- evidence-status-sync:20260926:begin -->

资料同步日期：2026-09-26。本页是 D4 唯一集中“当前证据状态”说明，依据已保存记录整理，不是新的实验日期或重新验收。
原 Goal 状态不因文档同步而改变；本轮不改算法、参数、模型、方案、历史任务勾选、GAP 或运行权限。

## 已完成的有限范围

- 2026-08-03 的 A2 v8 来源生成已完成 **324/324 个 episode、921 条来源记录**，来源提交为 `6737b44515526b5269ae98faad39e1f92716f423`。
- 来源为 **TRAIN-only**，seed `28100-28423`；保存 checkpoint 为 `finalized`、剩余 0、`training_started=false`。
- D6 来源完整性审计已通过，准确状态为 `source_integrity_audit_passed_not_training_authorized`。历史审计记录阻断项、真值泄漏、切分泄漏均为 0；这是来源审计，不是训练、选模或运行准入。
- 2026-08-07 主级进展保存了上述断点；2026-09-26 上一批 D4 复核核对了来源元数据及文档差异，没有重跑历史试验。
- 既有规则路径、版本、epoch、lease 和联盟 ACK 合同仍按原有实现及历史验证范围解释，来源审计不扩大其验收范围。

## 未完成及证据限制

- **v8 未训练，validation/test 来源未冻结**；当前代际模型、独立评价、冻结模型交付和准入未完成。TRAIN 来源不含协方差的边界保留。
- 旧候选、独立演示和旧模型评价不能代替当前 v8；来源生成 checkpoint 不是模型 checkpoint。
- 完整故障矩阵、真实通信、恢复及多种子统一闭环仍没有原 Goal 最终验收。局部合同或 episode-clock 安全结果不外推到上述范围。
- 正式 R0 450 组仍为“**摘要可查、完整记录未定位**”；728 组是另批来源生成，不能替代或补齐 450 组。
- 本页不声明可重跑、可重评分、学习非退化或原 Goal 已完成，也不制定研究系统增强计划。

## 方案与实现

2026-08-07 主级进展记载的“二级节点失效后推举临时中心机”属于领导方案，未同步为 D4 正式实现或规模化验证结果。
既有实现仍保留中心、二级节点与完全分布式联盟路径。两者分别登记，不以文档引用视为接入，本次均不修改。

## 旧章节对应关系

| 旧章节或数值 | 当前阅读边界 |
| --- | --- |
| 2026-08-03 实现绑定重冻结、`fcf8525` clean preflight、0/324、等待新授权 | 当时的请求与预检阶段；后续 `6737b44` 来源已完成。保留旧正文及历史勾选。 |
| 预生成 viability 的 324/324、972 帧 | 可生成性检查口径，不是正式来源 921 条记录，也不是模型结果。 |
| 历史 `921/921`、`974 passed`、`986 passed` 等测试文字 | 对应各自日期和制品条件的测试记录；不替代来源计数，不删去原失败、错误或跳过项。 |
| 旧 v7 来源独立评价、旧 BC 或影子候选 | 各自冻结代际的历史记录，不是 v8 模型；原权限限制保留。 |
| 旧 `1e5ed8d` 的 900 组联盟诊断 | 不属于 `80e55eb` 的正式 450 组，不混合批次或结论。 |
| 旧章节“当前”、待办及 GAP 状态 | 按章节日期读取为历史阶段；本次只补资料衔接，不重做验收或关闭 GAP。 |

入口：[模块 README](../README.md)、[PLAN](../PLAN.md)、[文档索引](README.md)、[原理](MODULE_PRINCIPLES_CN.md)、[算法说明](ALGORITHM_AND_IMPLEMENTATION.md)。
报告实际位置：[AirSim 集成计划](../reports/AIRSIM_INTEGRATION_PLAN.md)、[实验报告](../reports/EXPERIMENT_REPORT.md)；不在 docs 下建立同名空壳。
审查入口：[GAP](../../../subagent_reviews/D4_IMPLEMENTATION_GAP_AUDIT.md)、[综述及评审](../../../subagent_reviews/D4_DISTRIBUTED_FALLBACK_REVIEW_AND_PLAN.md)、[M 对 N 联盟评审](../../../subagent_reviews/D4_M_TO_N_DISTRIBUTED_COALITION_REVIEW.md)。

## 依据

- [2026-08-03 原 Goal 完成度审计](../../scalable_3d_simulation/docs/SCALABLE_3D_GOAL_COMPLETION_AUDIT_20260803_CN.md)：D4 来源审计状态、未训练及输入边界。
- [2026-08-07 保存进展](../../scalable_3d_simulation/docs/SCALABLE_3D_GOAL_PROGRESS_AND_NEXT_PLAN_20260807_CN.md)：324/324、921 条记录及方案/实现差异。
- [来源目录状态](../../../deliverables/project_audits/goal_resume_audit_20260926_v1/SOURCE_DIRECTORY_STATUS.json)：D4 来源路径、提交、计数与元数据摘要；其仓库外目录不是本轮新生成。
- [先前补充校验记录](../../../deliverables/project_audits/goal_resume_audit_20260926_v1/SUPPLEMENTAL_CHECKS.json)：D4 653 个清单文件匹配的既有字节检查，不是本轮重复校验。
- [正式批次定位结论](../../../deliverables/project_audits/goal_resume_audit_20260926_v1/历史结果定位与完整性核对_CN.md)：450 组完整记录未定位与来源批次边界。
- [上一批 D4 所有者复核](../../../deliverables/project_audits/goal_owner_review_sync_20260926_v1/owners/D4_review.json)：15 条要求，G55 的文档进展滞后；建议状态不是能力状态变更。

<!-- evidence-status-sync:20260926:end -->

