# D3 当前证据状态

资料同步日期：2026-09-26。此日期不是新的实验日期。本页是D3唯一集中“当前证据状态”说明，其他入口仅链接本页；既有正文、日期、勾选和GAP结论原样保留。

## 已有证据与有限结论

| 历史阶段 | 保存记录 | 可支持的结论 |
| --- | --- | --- |
| 2026-08-02 dirty开发探针 | 15 cells、300/300，`exploratory_dirty_pass` | 请求级配额可行性证据；不是正式来源数据集，不授予训练或运行权限。 |
| 20260802批次正式来源（A1 v3） | 300/300 episode、3086帧、300个唯一seed | 来源已生成；不是模型训练、选模或准入完成。 |
| 20260803批次来源完整性审计 | `source_integrity_audit_passed_not_training_authorized` | 已有来源完整性审计通过；不授予训练、模型消费或运行权限。 |
| 2026-08-07 原Goal保存断点 | 来源完成、当前代际模型未训练 | 保持原Goal尚未完成的判断。 |
| 2026-09-26 既有证据复核 | 保存的D3清单307项字节核验匹配，owner复核17项 | 文件保存与状态解释证据；本次同步未重新核验大载荷或运行实验。 |

日期口径：正式来源的20260802和审计的20260803仅作为批次/记录日期标签。本次查阅生成session、checkpoint、result、dataset manifest及source audit五份小型元数据，未定位明确的日历执行/完成时间；`last_invocation_wall_s`是耗时，不能据此确定实际完成日。批次标签和报告日期均不作为执行时间证明。

正式来源绑定生成提交`e7c438ca0e480f9f56dc426dc20a3f8f83d7d6a6`，不能用当前HEAD替代。dirty探针和正式来源即使组数相同，也是不同阶段、不同证据，不能互相替代。

来源合同**不显式包含六维状态和协方差**。来源审计通过只适用于实际保存合同，不能外推为完整六维学习输入、模型质量或统一消息闭环已经验收。已有规则软件和接口的历史实现结论不因本页改变。

## 未完成与不可外推范围

- 当前A1 v3未训练、未选模、未完成独立模型评价或准入；缺当前代际冻结模型及完整交付证据。
- 旧BC训练、旧v2来源独立评价、局部安全测试和后续独立演示不能替代当前A1 v3或原Goal统一验收。旧`d3_learning_model_bundle_v3`是bundle schema，不代表当前A1 v3代际完成。
- 正式R0的450组仍是“摘要可查、完整记录未定位”。另有D3/D4/D5来源300/324/104组，合计728组，不是正式450组，也不能补齐原R0矩阵。
- 原Goal统一正式比较、完整体系验收、最终模型与报告交付没有因本次资料同步完成。需求满足率95%、安全非退化和显存等原验收项不升级。
- 本次不关闭或重分类GAP，不改变算法、参数、合同、权限或历史任务勾选，不制定研究系统增强计划。

## 旧章节对应关系

| 原入口与章节 | 现在的阅读方式 |
| --- | --- |
| [README](../README.md)、[PLAN](../PLAN.md)顶部8月2日“当前”探针状态 | 带日期的请求阶段历史；正式来源和审计阶段以本页所列出处衔接，不勾选旧待办。 |
| [GAP](../../../subagent_reviews/D3_IMPLEMENTATION_GAP_AUDIT.md)、[review](../../../subagent_reviews/D3_ASSIGNMENT_PLANNER_REVIEW_AND_PLAN.md)的request-level结论 | 仅保留其当时证据范围，不把来源审计通过解读为新GAP关闭或模型准入。 |
| [M-to-N review](../../../subagent_reviews/D3_M_TO_N_ASSIGNMENT_AND_SCHEDULING_REVIEW.md)的8月1日无seed/数据 | 历史请求快照，不能覆盖后续正式来源完成记录；旧M-to-N试验范围不变。 |
| [原理](MODULE_PRINCIPLES_CN.md)、[算法说明](ALGORITHM_AND_IMPLEMENTATION.md)、[文档索引](README.md)、[主接口要求](../reports/D3_MAIN_INTERFACE_REQUIREMENTS_A1_V3_CN.md)的8月2日状态 | 算法与合同正文原样保留，其中“当前”状态按原日期阅读，不当作最后断点。 |
| [实验报告](EXPERIMENT_REPORT.md)的dirty探针及旧v2结果 | 保留原数字和分母；不把探针改名为正式数据，不把历史测试数当成本轮结果。 |
| [AirSim集成计划](AIRSIM_INTEGRATION_PLAN.md)的质点局部验证 | 仍不是新增AirSim结果或原Goal统一验收；本次只补阅读入口。 |

## 证据出处

- [8月3日原完成审计](../../scalable_3d_simulation/docs/SCALABLE_3D_GOAL_COMPLETION_AUDIT_20260803_CN.md)：A1 v3来源数量、审计状态、字段边界和未训练结论。
- [8月7日保存进展](../../scalable_3d_simulation/docs/SCALABLE_3D_GOAL_PROGRESS_AND_NEXT_PLAN_20260807_CN.md)：最后断点和原Goal未完成范围；本页不重新发布其中的实施计划。
- [来源目录登记](../../../deliverables/project_audits/goal_resume_audit_20260926_v1/SOURCE_DIRECTORY_STATUS.json)与[后续补充核验](../../../deliverables/project_audits/goal_resume_audit_20260926_v1/SUPPLEMENTAL_CHECKS.json)：生成来源身份及先后两个文件核查阶段；不是本次新增载荷审计。
- [正式450组定位记录](../../../deliverables/project_audits/goal_resume_audit_20260926_v1/历史结果定位与完整性核对_CN.md)：摘要与完整记录的保存边界。
- [D3上一批owner复核](../../../deliverables/project_audits/goal_owner_review_sync_20260926_v1/owners/D3_review.json)：17项意见，特别是G19来源字段边界与G55文档阶段衔接。

本轮只进行普通文档检查，不运行pytest、模型、训练、GPU、仿真、配准、控制或重新评分。原Goal状态不因文档同步而改变。
