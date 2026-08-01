# D3 A1 来源独立只读评价报告

## 结论

评价合同为 `d3-a1-assignment-aware-source-independent-evaluation-v2-20260730`。机器门结果为`true`，输出状态为`source_independent_evaluation_v2_gate_passed_not_admitted`。本报告不授予运行、分配、计划发布、控制、物理执行或正式准入权限。

输入中的 train、validation 和 test 仅保留为来源子组标签。三组均按`source_independent_evaluation` 处理，没有训练、选模、归一化重拟合或阈值调整。

## 数据与模型

- 评价帧数：292
- 数据帧摘要：`1568a69e8d93d3357c6cf53f4a416f5083b7cf1f90a33fa0ccc0d0a7ed47d972`
- 模型清单摘要：`ec9f93d668e1aa319f65fcda0d73adb0527f316a2d1880e93e88697b6468ad3d`
- 模型状态摘要：`c185823bd9a4cf5363d17854385aeb74c340c8ac384327281d224a1097eb8206`
- bundle 树摘要：`de7b627df9782d7d2577687f30d02d4faeeaf577ecc557c2b8d91dd6e7115dd9`
- 评价源码摘要：`b31d0b86f53ff4dc32a01dc9ecc7988539a5635cbc31b674cd74b55a69de2438`
- 在线真值使用：0

## 核心指标

| 指标 | 分子 | 分母 | 比例 |
| --- | ---: | ---: | ---: |
| 正类安全换绑 | 13 | 110 | 11.82% |
| 正类教师完全匹配 | 8 | 110 | 7.27% |
| 负类 exact-R0 | 182 | 182 | 100.00% |

失败关闭帧为 94，其中矩阵 exact-R0 为 94，绑定 exact-R0 为 94。重复资源、硬禁边、多机需求完整性和版本违规分别为 0、0、0、0。

## 拒绝分布

| 原因 | 帧次 |
| --- | ---: |
| binding_change_limit_exceeded | 65 |
| feature_ood | 27 |
| relative_rule_cost_difference_exceeded | 6 |
| rule_cost_difference_exceeded | 53 |

## 机器门

| 检查 | 结果 |
| --- | --- |
| input_frame_count_matches_manifest | 通过 |
| all_input_values_finite | 通过 |
| generation_complete_and_finite | 通过 |
| online_truth_use_zero | 通过 |
| source_seed_universe_exact | 通过 |
| source_split_seed_counts_exact | 通过 |
| training_seed_overlap_zero | 通过 |
| formal_holdout_seed_overlap_zero | 通过 |
| bundle_manifest_tree_state_exact | 通过 |
| model_weights_unchanged | 通过 |
| normalization_not_refit | 通过 |
| all_permissions_false | 通过 |
| zero_duplicate_resource | 通过 |
| zero_hard_edge_violation | 通过 |
| zero_m_to_n_atomicity_violation | 通过 |
| zero_version_violation | 通过 |
| zero_model_assignment_output | 通过 |
| zero_model_plan_output | 通过 |
| zero_model_runtime_output | 通过 |
| zero_rule_matrix_mutation | 通过 |
| fallback_matrix_exact_r0 | 通过 |
| fallback_binding_exact_r0 | 通过 |
| positive_denominator_nonzero | 通过 |
| positive_safe_binding_change_passed | 通过 |
| positive_teacher_exact_match_passed | 通过 |
| negative_denominator_nonzero | 通过 |
| negative_exact_r0_passed | 通过 |
| ood_distribution_complete | 通过 |
| rejection_distribution_complete | 通过 |
| all_source_subgroups_present | 通过 |

## 边界

该结果只允许作为一次来源独立离线评价证据。正式保留种子仍未读取，模型权重和阈值未修改。后续是否进入正式保留集评价，需要 main 和 D6依据本报告及校验和另行审查。
