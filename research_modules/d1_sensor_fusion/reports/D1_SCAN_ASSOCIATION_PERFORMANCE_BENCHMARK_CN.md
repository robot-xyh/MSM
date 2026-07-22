# D1扫描关联工作区性能基准

## 结论

当前默认路径与扫描内模型缓存路径的逐扫描航迹、批次语义、最终航迹和一致性证据保持等价。
量测模型构造由 16,457 次降至 82 次，下降 99.50%。
纯融合墙钟由 10.792 秒降至 8.635 秒，本机单次对照加速 1.25 倍。墙钟只作说明，验收依据是语义哈希和确定性操作计数。

## 输入

- 输入文件：`research_modules/scalable_3d_simulation/outputs/scalable_3d_rule_performance_calibration_20260722_clean_492979e/nominal/200v200/seed_42000/online_observations.jsonl`
- SHA-256：`bc539686b130d96c63b76b9161fadbae2dba59de44cb61ac80d92f2ea1018406`
- 扫描/观测：86 / 2051
- 重排扫描：10
- 峰值缓冲：33 扫描 / 623 观测
- 在线真值使用：0

## 操作计数

| 指标 | 当前默认 | 扫描内缓存 |
| --- | ---: | ---: |
| `association_candidate_pair_count` | 371,054 | 371,054 |
| `association_measurement_model_build_count` | 16,457 | 82 |
| `association_projection_build_count` | 16,457 | 14,648 |
| `association_innovation_solve_count` | 371,054 | 371,054 |
| `association_radar_track_state_build_count` | 1,804 | 1,804 |
| `association_radar_observation_state_build_count` | 1,769 | 1,769 |
| `global_track_materialization_count` | 16,653 | 16,653 |

## 函数剖析

cProfile 会放大绝对墙钟，本表只用于解释剩余热点。

| 函数 | 当前调用 | 当前累计秒 | 优化调用 | 优化累计秒 |
| --- | ---: | ---: | ---: | ---: |
| `process_scan_batch` | 86 | 16.743 | 86 | 15.585 |
| `_scan_one_to_one_assignments` | 86 | 6.876 | 86 | 4.886 |
| `_association_score` | 16,457 | 5.733 | 0 | 0.000 |
| `_cached_non_radar_scan_cost_matrix` | 0 | 0.000 | 73 | 3.651 |
| `measurement_model_for` | 27,287 | 2.453 | 10,912 | 1.004 |
| `numerical_jacobian` | 18,292 | 1.685 | 16,483 | 1.586 |
| `global_tracks` | 86 | 1.387 | 86 | 1.496 |

## 验收

- 通过：`per_scan_semantic_equivalence`
- 通过：`final_track_equivalence`
- 通过：`consistency_evidence_equivalence`
- 通过：`candidate_pair_count_preserved`
- 通过：`innovation_solve_count_preserved`
- 通过：`measurement_model_build_reduction_at_least_95_percent`
- 通过：`projection_build_count_not_increased`
- 通过：`online_truth_use_count_zero`

## 边界

本基准只证明冻结输入上的扫描内模型复用保持 D1 输出语义并减少重复构造。
候选对数量、每对创新协方差求解、扫描原子性和 Hungarian 分配均未减少。
结果不证明 AirSim、传感器精度或200对200完整系统已经实时。
