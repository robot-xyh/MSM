# D5 当前证据状态

<!-- evidence-status-sync:20260926:begin -->
资料同步日期：2026-09-26。本页是 D5 唯一集中“当前证据状态”说明；该日期不是新的实验日期。
本轮仅衔接已有档案，不改算法、参数、历史日期、任务勾选、GAP 或能力分类，不授予任何运行权限。
原 Goal 状态不因文档同步而改变，统一验收仍未完成；不新增研究实施计划。

## 来源与时间

依据[上一批 D5 逐项复核](../../../deliverables/project_audits/goal_owner_review_sync_20260926_v1/owners/D5_review.json)、
[原完成度审计](../../scalable_3d_simulation/docs/SCALABLE_3D_GOAL_COMPLETION_AUDIT_20260803_CN.md)及
[2026-08-07 主级进展](../../scalable_3d_simulation/docs/SCALABLE_3D_GOAL_PROGRESS_AND_NEXT_PLAN_20260807_CN.md)。
D6 来源审计采用 20260803 批次标识，文件未给出单独完成时刻；不将批次日期或本轮日期补写为实验完成时间。
现存审计结果的路径及字节核对记录见[来源证据索引](../../../deliverables/project_audits/goal_resume_audit_20260926_v1/SOURCE_INTEGRITY_CHECKS.csv)。

## A3 v3 来源

- 来源提交为 `64dfc088cf4990304a95b2a362b905136092c70a`；104/104 episode、280968 条语义记录，seed 为 24000-24103。
- development 72 / future-held-out 32；development 内 train 48 / validation 24。
- audit-only 来源完整性审计已通过：`source_integrity_audit_passed_not_training_authorized`。
- 审计允许的完整性载荷读取不等于训练、选模、推理或保留集模型消费；已有审计记录模型消费为 false，不授予上述权限。
- 来源缺显式 bbox/local-track geometry 的合同限制仍保留；完整性通过不证明该能力已补齐。
- 当前代际 A3 v3 训练、模型、校准阈值、独立评价及准入仍未完成，旧候选和独立实验均不能替代。
- 旧文中的 `source_generated_not_trained` 和“D6 未授权、未执行”保留为来源生成阶段记录，不再作为当前来源审计状态。

## G1 历史与当前保存状况

- [2026-07-27 G1 v5 正式证据结果](EXPERIMENT_REPORT.md)记录 clean commit `8d5e02ec989259ce3d39e1e4ad6a90dd0d8d5b54` 下的装配。
- 历史权重 SHA-256：`7fb5db8b6099ca4da5706a3bec53ff7cd634e8bd267c036ce3ee4ee4bf71ca71`。
- 历史 v5 manifest SHA-256：`b431d066362005868374d038eb93a83b773c03715a53d8a9dfd0da21784f317d`。
- 冻结合成范围为 20 未见 seed、900 episode、45 单元；历史两级 D6 审计和 strict/shadow loader 通过，见[装配与验证记录](ALGORITHM_AND_IMPLEMENTATION.md)。
- 历史 F1=1、false merge=0 仅属于该合成范围，不能证明代表相机域重新构图、中心身份绑定或物理结果；这些项仍 unavailable。
- 当时状态为 `g1_evidence_eligible_not_authorized`，六项在线权限关闭；不能把加载通过写成在线 G1 已采用。
- 2026-09-26 上一批定点检查发现旧根 `/tmp/MSM-d5-g1-formal-evidence-8d5e02e-20260727` 不存在；当前完整制品副本未定位。
- “历史曾装配及加载通过”与“当前完整制品不可定位”分别登记；本轮没有复载、验证权重或断言所有副本丢失。旧 `99fa4428` 候选不等于该 v5。

## AirSim 代际边界

- [冻结基线清单](../../airsim_runtime/baselines/d5_long_range_20target_20260810/baseline_manifest.json)属于 2026-08-10 旧 v2、20 目标、seed 20260810。
- 1934 条可评分关系、4 条错误，准确率约 0.9979317477；短缺口 3、绑定切换 7、交叉窗口可评价 3/31。
- 准确率超过历史 0.95 子门，但短缺口要求为 0，实测为 3，专项总门仍 `fail_closed`；不能忽略不可评价窗口。
- 新时序 v3 的接口和 runtime 接线有历史软件测试记录，见[AirSim 集成记录](AIRSIM_INTEGRATION_PLAN.md)；旧 v2 数值不是新 v3 真实复跑。
- 新 v3 真实单 seed 及多 seed 性能证据仍未完成；本轮未运行 AirSim、配准、控制或重新评分。

## 旧章节对应关系

| 历史入口或章节 | 当前阅读口径 |
| --- | --- |
| [README](../README.md)、[PLAN](../PLAN.md)的 2026-08-03 来源生成及重绑定章节 | 保留生成阶段状态与原勾选；来源审计当前口径以上文为准，未训练结论不变。 |
| [原理](MODULE_PRINCIPLES_CN.md)、[算法](ALGORITHM_AND_IMPLEMENTATION.md)、[实验报告](EXPERIMENT_REPORT.md)的来源生成章节 | “未执行 D6 审计”只说明当时阶段；后续 audit-only 已通过，不是模型消费。 |
| [GAP 审计](../../../subagent_reviews/D5_IMPLEMENTATION_GAP_AUDIT.md)、[模块 review](../../../subagent_reviews/D5_TERMINAL_ASSOCIATION_REVIEW_AND_PLAN.md)、[M 对 N review](../../../subagent_reviews/D5_M_TO_N_TERMINAL_MULTIVIEW_REVIEW.md) | 旧日期和 GAP 判断原样保留，不由本轮重新关闭、勾选或升级。 |
| 实验报告及算法文档的 2026-07-27 G1 v5 章节 | 历史装配、加载证据仍成立于记录范围；不保证当前文件齐全或最终统一验收。 |
| README、PLAN、[AirSim 计划](AIRSIM_INTEGRATION_PLAN.md)及实验报告的 2026-08-10 章节 | 分开阅读旧 v2 保存实测、新 v3 接线测试和理想独立演示。 |

## 总体验收限制

正式 450 组仍为“摘要可查、完整记录未定位”，见[历史定位记录](../../../deliverables/project_audits/goal_resume_audit_20260926_v1/历史结果定位与完整性核对_CN.md)。
来源 728 组、其中 D5 的 104 组、G1 合成 900 episode 及各独立演示均为不同证据域，不能相加或互替。
200 目标、4 相机、800 节点的历史软件测试不等于 200 资源相机完整 episode 验收。
本页不新增实验结果，不以当前测试冒充历史结果；既有模型与完整体系的未完成范围不变。
<!-- evidence-status-sync:20260926:end -->

