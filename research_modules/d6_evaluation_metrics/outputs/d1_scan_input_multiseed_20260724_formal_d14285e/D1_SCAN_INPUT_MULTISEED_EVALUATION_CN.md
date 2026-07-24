# D1 扫描输入多种子评估

## 结论

D1 扫描输入候选实现准入结论为 **通过**。评估只读取同一干净提交产生的 13 组参考/候选 episode，未参与仿真运行和控制决策。
系统实时性缺口 **未关闭**。该结论单独依据候选臂实时因子判断，不由优化准入结论推导。

## 证据条件

| 项目 | 内容 |
| --- | --- |
| 源提交 | `d14285e4fdeb2f2e2cd32fad2f6d42e30f9e73a7` |
| 矩阵 SHA256 | `3e852e4036d17d4da7c80dbb4ddea75b6ed7e27ee9d0be3195c2d1b5e30a531d` |
| 规模 | 200 个目标、200 个资源、2 个侦察节点 |
| 短时组 | seeds 1101-1110，每组 2.2 秒 |
| 长时组 | seeds 1101-1103，每组 10 秒 |
| 参考实现 | `reference_v1` |
| 候选实现 | `candidate_v2` |
| bootstrap | 10000 次，随机种子 20260724 |

## 扫描输入结果

| 组别 | 参考均值/s | 候选均值/s | 平均改善 | 候选更快 | 原始相对变化 95% 区间 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 短时 | 1.212452 | 1.14565 | 5.360122% | 9/10 | [-8.208165, -3.084141]% |
| 长时 | 6.687633 | 6.34068 | 5.142482% | 3/3 | [-8.837129, -1.669361]% |

逐 pair 原始相对变化按 `(候选-参考)/参考` 计算。耗时和内存指标的正向改善为原始变化取负值。组均值采用逐 pair 相对变化的算术均值，置信区间以 seed pair 为重采样单位。

## 语义审计

| 组别 | 业务语义通过 | 有限状态 | 在线真值隔离 | 实现身份一致 |
| --- | ---: | ---: | ---: | ---: |
| 短时 | 10/10 | 10/10 | 10/10 | 10/10 |
| 长时 | 3/3 | 3/3 | 3/3 | 3/3 |

在线总线逐条比较保留 D3 计划版本和前序关系，并校验 D4 内容地址及确认消息来源引用。离线真值状态、真值标签和距离事件只用于等价审计，在线真值使用计数必须为零。

## 准入门

| 判据 | 结果 | 原因 |
| --- | :---: | --- |
| `all_pairs_business_semantics_equal` | 通过 | - |
| `all_pairs_finite_state` | 通过 | - |
| `all_pairs_online_truth_use_count_zero` | 通过 | - |
| `all_pairs_explicit_implementation_identity` | 通过 | - |
| `required_performance_metrics_available` | 通过 | - |
| `short_candidate_faster_at_least_8_of_10` | 通过 | - |
| `short_scan_input_mean_improvement_at_least_5_pct` | 通过 | - |
| `short_scan_input_bootstrap_raw_ci_upper_below_zero` | 通过 | - |
| `long_candidate_faster_at_least_2_of_3` | 通过 | - |
| `long_scan_input_mean_improvement_at_least_5_pct` | 通过 | - |
| `core_wall_mean_degradation_within_5_pct` | 通过 | - |
| `rss_mean_degradation_within_5_pct` | 通过 | - |
| `every_pair_rss_degradation_within_5_pct` | 通过 | - |

## 证据边界

- 当前证据来自三维质点环境，不是 AirSim 或实机测试。
- 候选实现准入只说明扫描输入阶段在冻结场景中的语义与性能条件。
- 墙钟、外部进程耗时、常驻内存和实时因子分层报告，未相加为单一指标。
- 运行配置、性能诊断和所有已读取输入文件 SHA256 保留在完整评估 JSON 中。

## 文件

- `d1_scan_input_multiseed_evaluation.json`：完整逐 pair 证据和门限。
- `d1_scan_input_multiseed_aggregate.json`：聚合结论。
- `d1_scan_input_multiseed_pairs.csv`：逐 pair 指标。
- `d1_scan_input_multiseed_improvement_curve.png`：短时和长时改善曲线。
