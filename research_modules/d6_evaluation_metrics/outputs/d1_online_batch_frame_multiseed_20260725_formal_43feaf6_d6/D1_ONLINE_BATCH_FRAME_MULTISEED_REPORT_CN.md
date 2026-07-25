# D1 在线批帧交接同提交多种子正式评估

## 结论

候选优化准入结论：`admit`。全部预注册 gate 通过。
200v200 系统实时结论：`仍不足`；候选最低实时因子 `0.20449`，门限 `>=1.0`。候选优化准入不等于系统实时达标。
本报告只使用 2026-07-25 的三维质点仿真证据，不是 AirSim、实机或实飞证据。

## 证据范围

- source commit：`43feaf600f288a85ce76a76862334256f0d0d352`，producer clean。
- matrix SHA-256：`4afbf9ac273763a16aa01cc744fd67b52e437099460b33377a128f986ac5719b`。
- short 10 对、long 3 对，共 13 对/26 episode；200 目标、200 资源、2 侦察节点。
- 参考 `convert_then_frame_v1`；候选 `closed_immutable_batch_to_frame_v1`。

## 批帧审计

| 指标 | 实测 |
|---|---:|
| 重复检查减少率 | 100% |
| closed handoff ratio | 100% |
| candidate fallback count | 0 |
| candidate request/closed | 2665/2665 |

每个 episode 均从四份最终诊断重算 request/path/result、raw batch check、snapshot structure、snapshot success/failure、final frame check 和量测输出守恒；selector 及 execution config 在 runtime profile、summary、module final、nested governance 和 governance audit 表面逐层绑定。

## 分组性能

| 组 | 指标 | 参考均值 | 候选均值 | 变化 | 候选更快 | 95% bootstrap CI |
|---|---|---:|---:|---:|---:|---:|
| 短时 | scan input | 1.150202 | 0.708014 | 38.289241% | 10/10 | [-40.065664, -36.838329]% |
| 短时 | core wall | 8.925269 | 8.545301 | 4.252745% | 10/10 | [-4.812433, -3.74245]% |
| 短时 | D2 association | 0.479581 | 0.489715 | 2.113047% | 3/10 | [0.148848, 5.375192]% |
| 短时 | maximum RSS | 875499.6 | 874961.2 | -0.061496% | 2/10 | [-0.296885, 0.073568]% |
| 短时 | real-time factor | 0.246588 | 0.257549 | 4.450125% | 10/10 | [3.892795, 5.065877]% |
| 长时 | scan input | 6.432796 | 4.096672 | 36.275282% | 3/3 | [-39.243109, -32.680019]% |
| 长时 | core wall | 51.418661 | 48.889222 | 4.916501% | 3/3 | [-5.356677, -4.178069]% |
| 长时 | D2 association | 3.370853 | 3.466269 | 2.830616% | 1/3 | [-6.060309, 14.40851]% |
| 长时 | maximum RSS | 1624810.666667 | 1629390.666667 | 0.281879% | 1/3 | [-0.019706, 0.856727]% |
| 长时 | real-time factor | 0.194487 | 0.204544 | 5.173918% | 3/3 | [4.360243, 5.659857]% |

## 预注册 Gate

| gate | 实测 | 判据 | 结果 |
|---|---:|---:|---:|
| `all_pairs_business_semantics_equal` | 13 | `== 13` | 通过 |
| `all_pairs_explicit_implementation_identity` | 13 | `== 13` | 通过 |
| `all_pairs_finite_state` | 13 | `== 13` | 通过 |
| `all_pairs_online_batch_frame_audit_valid` | 13 | `== 13` | 通过 |
| `all_pairs_online_truth_use_count` | 0 | `== 0` | 通过 |
| `long_minimum_candidate_faster_count` | 3 | `>= 2` | 通过 |
| `long_minimum_core_wall_improvement_pct` | 4.916501% | `>= 2%` | 通过 |
| `long_minimum_scan_input_improvement_pct` | 36.275282% | `>= 20%` | 通过 |
| `maximum_any_pair_rss_increase_pct` | 0.856727% | `<= 5%` | 通过 |
| `maximum_candidate_reference_fallback_count` | 0 | `<= 0` | 通过 |
| `maximum_long_d2_association_mean_increase_pct` | 2.830616% | `<= 5%` | 通过 |
| `maximum_rss_mean_increase_pct` | 0.281879% | `<= 5%` | 通过 |
| `maximum_short_d2_association_mean_increase_pct` | 2.113047% | `<= 5%` | 通过 |
| `minimum_candidate_closed_handoff_ratio_pct` | 100% | `>= 99%` | 通过 |
| `minimum_candidate_duplicate_check_reduction_pct` | 100% | `>= 95%` | 通过 |
| `required_performance_metrics_available` | 13 | `== 13` | 通过 |
| `short_bootstrap_relative_change_upper_bound_pct` | -36.838329% | `<= 0%` | 通过 |
| `short_minimum_candidate_faster_count` | 10 | `>= 8` | 通过 |
| `short_minimum_core_wall_improvement_pct` | 4.252745% | `>= 2%` | 通过 |
| `short_minimum_scan_input_improvement_pct` | 38.289241% | `>= 20%` | 通过 |

## 逐对结果

| case | scan 改善 | core 改善 | D2 增幅 | RSS 增幅 | 重复检查减少 | closed ratio | 语义 |
|---|---:|---:|---:|---:|---:|---:|---:|
| short_seed_1121 | 36.61677% | 4.750368% | -0.172625% | -1.074051% | 100% | 100% | 通过 |
| short_seed_1122 | 36.515178% | 4.428449% | 0.669825% | 0.022154% | 100% | 100% | 通过 |
| short_seed_1123 | 36.594368% | 4.371525% | -1.107975% | 0.050504% | 100% | 100% | 通过 |
| short_seed_1124 | 41.249467% | 4.176774% | 0.313368% | 0.141273% | 100% | 100% | 通过 |
| short_seed_1125 | 36.354088% | 3.314733% | 15.778858% | -0.012188% | 100% | 100% | 通过 |
| short_seed_1126 | 37.733761% | 3.116574% | 2.589902% | 0.015586% | 100% | 100% | 通过 |
| short_seed_1127 | 44.63039% | 4.308021% | 0.489948% | 0.079927% | 100% | 100% | 通过 |
| short_seed_1128 | 36.019859% | 3.26609% | 1.678737% | 0.085856% | 100% | 100% | 通过 |
| short_seed_1129 | 39.779523% | 4.580275% | 1.461143% | 0.013863% | 100% | 100% | 通过 |
| short_seed_1130 | 37.399006% | 6.214645% | -0.270625% | 0.072577% | 100% | 100% | 通过 |
| long_seed_1121 | 32.680019% | 5.356677% | 14.40851% | 0.856727% | 100% | 100% | 通过 |
| long_seed_1122 | 39.243109% | 5.214757% | -6.060309% | 0.009342% | 100% | 100% | 通过 |
| long_seed_1123 | 36.902719% | 4.178069% | 1.136992% | -0.019706% | 100% | 100% | 通过 |

## 语义归一化边界

D6 只归一化预注册 treatment selector、execution config、批帧诊断计数及其派生字段、treatment 派生 episode_id 和性能字段。assignment plan 的真实业务内容不被忽略。
独立运行产生的 opaque plan ID 按首次出现的连续谱系映射为 token；源 plan/guidance 哈希、ACK 和 D4 authority 内容地址先在原始流内验证。映射后仍逐条比较 plan version/前序关系、分配关系、授权状态、目标-资源绑定、owner/coalition 业务字段、状态机结果、计数、安全结果及所有下游引用。任一真实 assignment 差异都会关闭业务语义 gate。

## 制品

- `d1_online_batch_frame_multiseed_evaluation.json`：完整 JSON。
- `d1_online_batch_frame_multiseed_compact.json`：紧凑 JSON。
- `d1_online_batch_frame_multiseed_pairs.csv`：逐 pair 数据。
- `d1_online_batch_frame_multiseed_curves.png`：性能、审计和实时曲线。
- `SHA256SUMS`：制品校验值。
