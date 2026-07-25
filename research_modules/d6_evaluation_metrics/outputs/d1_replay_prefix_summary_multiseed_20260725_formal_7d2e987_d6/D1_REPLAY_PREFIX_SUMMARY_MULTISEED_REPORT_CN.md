# D1 回放前缀摘要同提交多种子正式评估

## 结论

候选准入结论为 **reject**。失败门限：`short_minimum_candidate_faster_count`、`short_minimum_d1_fusion_improvement_pct`、`short_bootstrap_relative_change_upper_bound_pct`、`short_minimum_core_wall_improvement_pct`、`long_minimum_core_wall_improvement_pct`。
候选最低实时因子为 `0.197441`；候选准入不等于系统达到实时运行要求。
本结论只覆盖冻结的三维质点 200 对 200 矩阵，不包含 AirSim、硬件、实机或实飞证据。
D1 模块微基准和 clean seed-1151 预检未写入本次正式结论。

## 证据

- producer clean commit：`7d2e987471b521a1e531bf03a5c99af5096f676a`。
- matrix SHA-256：`85432d729877eff97e6f3dd517d4baa7a47f44a4fa42e6bfdc7ce85b8d9ec74b`。
- short 10 对、long 3 对，共 13 对和 26 个全新 episode；复用 0、失败 0。
- 每对只有回放前缀摘要 selector 不同，在线真值使用次数为 0。

## 语义审计

D6 对每对 episode 独立比较业务输出、在线消息、离线真值、任务计划谱系和安全结果。两臂 `offline_consistency/online_evidence.json` 的记录数量与记录摘要必须完全一致。`module_final_diagnostics.d1_fusion_performance` 的原有操作计数也必须完全一致。

候选诊断分别检查导出前 module-final 和导出后 summary。导出后 pending ledger 必须为 0，正常追加和不兼容追加不得触发物化。摘要命中、checkpoint 复用、revision 推进、pending 保留和在线快照投影均需实际出现。

## 工作量

| 项目 | 数量 |
|---|---:|
| 逻辑刷新记录 | 811858 |
| 实际内部物化记录 | 388468 |
| 内部物化减少率 | 52.150746% |
| 在线快照投影构造记录 | 656481 |
| 已披露记录构造总量 | 1044949 |

内部物化减少率只用于预注册压缩门。在线快照仍会构造不可变返回记录，该工作量单独列示，没有计为已经消失的成本。

## 性能

| 分组 | 指标 | 参考均值 | 候选均值 | 改善或增幅 | 候选更快 |
|---|---|---:|---:|---:|---:|
| 短时 | D1 融合耗时 | 2.485541 | 2.460735 | 0.959611% | 5/10 |
| 短时 | 核心流程耗时 | 8.562172 | 8.583612 | -0.256641% | 4/10 |
| 短时 | D1 扫描输入增幅 | 0.744953 | 0.724599 | -2.569539% | 6/10 |
| 短时 | D2 关联增幅 | 0.501726 | 0.484404 | -3.192488% | 6/10 |
| 短时 | 最大驻留内存增幅 | 876111.2 | 876233.2 | 0.013714% | 3/10 |
| 长时 | D1 融合耗时 | 17.699231 | 17.27713 | 2.361778% | 2/3 |
| 长时 | 核心流程耗时 | 48.703409 | 49.645931 | -1.930083% | 0/3 |
| 长时 | D1 扫描输入增幅 | 4.277187 | 4.059489 | -4.884376% | 2/3 |
| 长时 | D2 关联增幅 | 3.376049 | 3.500212 | 3.610722% | 0/3 |
| 长时 | 最大驻留内存增幅 | 1630584 | 1624572 | -0.365212% | 2/3 |

## 门限

| 门限 | 实测 | 判据 | 结果 |
|---|---:|---:|---:|
| `all_pairs_business_semantics_equal` | 13 | `== 13` | 通过 |
| `all_pairs_consistency_evidence_records_digest_equal` | 13 | `== 13` | 通过 |
| `all_pairs_existing_operation_counts_equal` | 13 | `== 13` | 通过 |
| `all_pairs_explicit_implementation_identity` | 13 | `== 13` | 通过 |
| `all_pairs_finite_state` | 13 | `== 13` | 通过 |
| `all_pairs_online_truth_use_count` | 0 | `== 0` | 通过 |
| `all_pairs_replay_prefix_summary_audit_valid` | 13 | `== 13` | 通过 |
| `long_minimum_candidate_faster_count` | 2 | `>= 2` | 通过 |
| `long_minimum_core_wall_improvement_pct` | -1.930083% | `>= 0.25%` | 失败 |
| `long_minimum_d1_fusion_improvement_pct` | 2.361778% | `>= 1%` | 通过 |
| `maximum_any_pair_rss_increase_pct` | 0.081079% | `<= 5%` | 通过 |
| `maximum_long_d1_scan_input_mean_increase_pct` | -4.884376% | `<= 5%` | 通过 |
| `maximum_long_d2_association_mean_increase_pct` | 3.610722% | `<= 5%` | 通过 |
| `maximum_rss_mean_increase_pct` | 0.013714% | `<= 5%` | 通过 |
| `maximum_short_d1_scan_input_mean_increase_pct` | -2.569539% | `<= 5%` | 通过 |
| `maximum_short_d2_association_mean_increase_pct` | -3.192488% | `<= 5%` | 通过 |
| `minimum_candidate_lazy_materialization_reduction_pct` | 52.150746% | `>= 20%` | 通过 |
| `short_bootstrap_relative_change_upper_bound_pct` | 0.619827% | `<= 0%` | 失败 |
| `short_minimum_candidate_faster_count` | 5 | `>= 8` | 失败 |
| `short_minimum_core_wall_improvement_pct` | -0.256641% | `>= 0.25%` | 失败 |
| `short_minimum_d1_fusion_improvement_pct` | 0.959611% | `>= 1%` | 失败 |

## 证据边界

评估器不会因模块微基准结果直接准入候选。任何 matrix SHA、producer commit、schema、路径、arm 状态、实现标识、双臂唯一 treatment、时间与规模参数不一致都会失败关闭。

输出包括完整 JSON、紧凑 JSON、逐对 CSV、性能曲线、中文报告和制品校验值。
