# D1 在线发布证据子集快照同提交多种子评估

## 结论

候选准入结论为 **reject**。失败门限：`short_minimum_candidate_faster_count`、`short_minimum_d1_fusion_improvement_pct`、`short_bootstrap_relative_change_upper_bound_pct`。
候选最低实时因子为 `0.203423`。实时门独立列示，不并入本次优化准入结论。
本结论只覆盖冻结的三维质点 200 对 200 矩阵，不包含 AirSim、硬件、实机或实飞证据。

## 证据

- producer clean commit：`d0219eb14c529a4fb9bf7d6610a9f32055a09206`。
- matrix SHA-256：`6c808c4df8759fd893c6d37ff9dce4a1efa07f9867fc71aff47a55c5f8517338`。
- short 10 对、long 3 对，共 13 对和 26 个全新 episode；复用 0、失败 0。
- 两臂仅允许在线发布证据快照 selector 不同，回放前缀均固定为参考实现。
- 在线真值使用次数为 0；真值制品只参与离线一致性评分。

## 语义审计

D6 独立比较在线总线、D1 和 D2 在线记录、业务计数、离线一致性记录及安全结果。两臂离线一致性记录数量和摘要必须完全相同，原 D1 融合操作计数也必须完全相同。

执行配置和诊断分别在运行配置、汇总、模块结束诊断、观测治理及嵌套治理表面核验。候选不得发生回退、查询缺失、非法标识或空集合选择。参考臂必须全程走完整快照路径。

## 记录工作量

| 项目 | 数量 |
|---|---:|
| 参考返回记录 | 1602170 |
| 候选返回记录 | 133917 |
| 候选削减率 | 91.641524% |
| 候选选择次数 | 429 |
| 候选子集成功次数 | 429 |
| 候选回退次数 | 0 |

## 性能

| 分组 | 指标 | 参考均值 | 候选均值 | 改善或增幅 | 候选更快 |
|---|---|---:|---:|---:|---:|
| 短时 | D1 融合耗时 | 2.47958 | 2.482785 | -0.147877% | 4/10 |
| 短时 | 核心流程耗时 | 8.595556 | 8.566789 | 0.330057% | 7/10 |
| 短时 | D2 关联增幅 | 0.504043 | 0.51398 | 1.963565% | 6/10 |
| 短时 | 最大驻留内存增幅 | 876920.8 | 876145.6 | -0.088749% | 8/10 |
| 长时 | D1 融合耗时 | 17.616719 | 17.430862 | 1.047143% | 2/3 |
| 长时 | 核心流程耗时 | 48.734323 | 48.325878 | 0.837777% | 3/3 |
| 长时 | D2 关联增幅 | 3.508502 | 3.458793 | -1.14958% | 1/3 |
| 长时 | 最大驻留内存增幅 | 1630798.666667 | 1624476 | -0.38415% | 1/3 |

## 门限

| 门限 | 实测 | 判据 | 结果 |
|---|---:|---:|---:|
| `all_pairs_business_semantics_equal` | 13 | `== 13` | 通过 |
| `all_pairs_consistency_evidence_records_digest_equal` | 13 | `== 13` | 通过 |
| `all_pairs_existing_operation_counts_equal` | 13 | `== 13` | 通过 |
| `all_pairs_explicit_implementation_identity` | 13 | `== 13` | 通过 |
| `all_pairs_finite_state` | 13 | `== 13` | 通过 |
| `all_pairs_online_truth_use_count` | 0 | `== 0` | 通过 |
| `all_pairs_publication_evidence_snapshot_audit_valid` | 13 | `== 13` | 通过 |
| `long_minimum_candidate_faster_count` | 2 | `>= 2` | 通过 |
| `long_minimum_core_wall_improvement_pct` | 0.837777% | `>= 0.25%` | 通过 |
| `long_minimum_d1_fusion_improvement_pct` | 1.047143% | `>= 1%` | 通过 |
| `maximum_any_pair_rss_increase_pct` | 0.092389% | `<= 5%` | 通过 |
| `maximum_long_d2_association_mean_increase_pct` | -1.14958% | `<= 5%` | 通过 |
| `maximum_rss_mean_increase_pct` | -0.088749% | `<= 5%` | 通过 |
| `maximum_short_d2_association_mean_increase_pct` | 1.963565% | `<= 5%` | 通过 |
| `minimum_candidate_returned_record_reduction_pct` | 91.641524% | `>= 50%` | 通过 |
| `short_bootstrap_relative_change_upper_bound_pct` | 1.374681% | `<= 0%` | 失败 |
| `short_minimum_candidate_faster_count` | 4 | `>= 8` | 失败 |
| `short_minimum_core_wall_improvement_pct` | 0.330057% | `>= 0.25%` | 通过 |
| `short_minimum_d1_fusion_improvement_pct` | -0.147877% | `>= 1%` | 失败 |

## 证据边界

任何 matrix SHA、producer commit、schema、路径、arm 状态、实现标识、唯一 treatment、规模或时间参数不一致均失败关闭。评估器不写入原始证据，也不向在线控制路径发布消息。

输出包括完整 JSON、紧凑 JSON、逐对 CSV、中文报告和制品校验值。
