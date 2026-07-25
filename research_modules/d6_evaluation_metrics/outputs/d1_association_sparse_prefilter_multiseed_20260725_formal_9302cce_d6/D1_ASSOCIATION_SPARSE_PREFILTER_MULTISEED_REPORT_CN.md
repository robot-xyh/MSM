# D1 关联稀疏预筛同提交多种子评估

## 结论

正式 verdict 为 **reject**；main 默认晋升不允许。
系统实时缺口仍开放；候选最低实时因子为 `0.206273`，门限为 `>=1.0`，该判定与局部优化准入分离。
失败门为 `short_minimum_candidate_faster_count`、`short_minimum_d1_fusion_improvement_pct`、`short_bootstrap_relative_change_upper_bound_pct`、`long_minimum_d1_fusion_improvement_pct`、`short_minimum_core_wall_improvement_pct`。本轮不改门、不删 pair，结论为 reject。
本报告仅使用三维质点仿真证据，不代表 AirSim、目标硬件、实机或实飞结论。

## 证据范围

- 评估日期：`2026-07-25`。
- clean source commit：`9302ccede2ca513c2235370e1a464fc88bc41150`。
- evidence manifest SHA-256：`43b0aeb41ff9abb243e86b559a6ec2d2e2e2cf94f50c4e45ff5c95d915268eb2`。
- 冻结 matrix SHA-256：`a7162d014d1c3c0f207355b24a5d7159bf3486d134ca21876f7469d1e915b71d`。
- 规模：200 个目标、200 个资源、2 个侦察节点。
- short 10 pair、long 3 pair，共 13 pair/26 fresh episode；26 complete、0 reused、0 failed。
- reference `disabled_v1`；candidate `modality_conservative_quadratic_bound_v1`；paired bootstrap 10000 次。

## 逐模态诊断

| 模态 | Candidate pair | Rejection | Exact solve | Gate pass | Fallback |
|---|---:|---:|---:|---:|---:|
| `radar` | 9199071 | 9145313 | 53758 | 48321 | 3773 |
| `lidar` | 0 | 0 | 0 | 0 | 0 |
| `acoustic` | 0 | 0 | 0 | 0 | 0 |
| `acoustic_3d` | 0 | 0 | 0 | 0 | 0 |
| `eo` | 801650 | 258272 | 39837 | 3979 | 37571 |
| `other` | 0 | 0 | 0 | 0 | 0 |

非雷达精确求解由 `298109` 降至 `39837`，减少 `86.636767%`。
每个 pair、每个固定模态桶的 exact gate-pass 计数必须完全相等；六桶计数、总计和上界守恒均由 D6 重算。

## 分组性能

| 组别 | 指标 | Reference 均值 | Candidate 均值 | 配对变化 | Candidate 更优 |
|---|---|---:|---:|---:|---:|
| short | D1 fusion | 2.473915 | 2.467389 | 0.228437% | 7/10 |
| short | 核心墙钟 | 8.59917 | 8.590696 | 0.091096% | 5/10 |
| short | scan input | 0.756319 | 0.752791 | -0.452226% | 7/10 |
| short | D2 association | 0.502191 | 0.504759 | 0.55948% | 1/10 |
| short | RSS | 877912.4 | 877882 | -0.003738% | 6/10 |
| short | RTF | 0.255962 | 0.256189 | 0.096142% | 5/10 |
| long | D1 fusion | 16.961857 | 16.840919 | 0.713776% | 3/3 |
| long | 核心墙钟 | 47.965475 | 47.729461 | 0.49065% | 3/3 |
| long | scan input | 3.989834 | 3.971143 | -0.47011% | 3/3 |
| long | D2 association | 3.344833 | 3.328621 | -0.453717% | 2/3 |
| long | RSS | 1610262.666667 | 1610693.333333 | 0.02685% | 0/3 |
| long | RTF | 0.20852 | 0.20955 | 0.495628% | 3/3 |

D1 fusion 配对原始变化 95% bootstrap CI：short `[-0.946192, 0.443531]%`，long `[-1.286611, -0.357903]%`。
D1/core/RTF 使用正向改善口径；scan、D2、RSS 使用 `(candidate-reference)/reference`，负值表示下降。

## 准入门

| Gate | 实际值 | 判据 | 结果 |
|---|---:|---:|---:|
| `all_pairs_association_sparse_prefilter_audit_valid` | 13 | `== 13` | 通过 |
| `all_pairs_business_semantics_equal` | 13 | `== 13` | 通过 |
| `all_pairs_exact_gate_pass_counts_equal` | 13 | `== 13` | 通过 |
| `all_pairs_explicit_implementation_identity` | 13 | `== 13` | 通过 |
| `all_pairs_finite_state` | 13 | `== 13` | 通过 |
| `all_pairs_online_truth_use_count` | 0 | `== 0` | 通过 |
| `long_minimum_candidate_faster_count` | 3 | `>= 2` | 通过 |
| `long_minimum_core_wall_improvement_pct` | 0.49065% | `>= 0.25%` | 通过 |
| `long_minimum_d1_fusion_improvement_pct` | 0.713776% | `>= 1%` | 失败 |
| `maximum_any_pair_rss_increase_pct` | 0.077909% | `<= 5%` | 通过 |
| `maximum_long_d1_scan_input_mean_increase_pct` | -0.47011% | `<= 5%` | 通过 |
| `maximum_long_d2_association_mean_increase_pct` | -0.453717% | `<= 5%` | 通过 |
| `maximum_rss_mean_increase_pct` | 0.02685% | `<= 5%` | 通过 |
| `maximum_short_d1_scan_input_mean_increase_pct` | -0.452226% | `<= 5%` | 通过 |
| `maximum_short_d2_association_mean_increase_pct` | 0.55948% | `<= 5%` | 通过 |
| `minimum_candidate_non_radar_exact_solve_reduction_pct` | 86.636767% | `>= 20%` | 通过 |
| `short_bootstrap_relative_change_upper_bound_pct` | 0.443531% | `<= 0%` | 失败 |
| `short_minimum_candidate_faster_count` | 7 | `>= 8` | 失败 |
| `short_minimum_core_wall_improvement_pct` | 0.091096% | `>= 0.25%` | 失败 |
| `short_minimum_d1_fusion_improvement_pct` | 0.228437% | `>= 1%` | 失败 |

## 业务等价与边界

13 个 pair 均由 D6 重新执行规范跨 episode 比较。只排除预注册的 `same_runtime_profile`，并只归一化 selector、对应 execution config/diagnostics、关联精确求解诊断、运行时哈希派生 episode ID 和性能字段。
其他 summary、governance、在线消息、D3 计划谱系、D4 内容地址与 ACK、离线 truth state/labels/proximity 制品均继续比较；online truth use 必须为 0。
selector、完整 implementation ID、execution config 和 diagnostics 在 runtime profile、summary、module final 与 governance 四个主表面逐臂校验；runtime configuration 和 nested governance 另作冗余核对。
局部热点通过不能关闭系统实时、AirSim、目标硬件、RMSE、NEES、NIS 或实飞验证。

## 制品

- `d1_association_sparse_prefilter_multiseed_evaluation.json`：完整评估。
- `d1_association_sparse_prefilter_multiseed_compact.json`：紧凑汇总。
- `d1_association_sparse_prefilter_multiseed_pairs.csv`：逐 pair 数据。
- `d1_association_sparse_prefilter_multiseed_curves.png`：性能、求解削减与 RTF 曲线。
- `SHA256SUMS`：报告制品校验值。
