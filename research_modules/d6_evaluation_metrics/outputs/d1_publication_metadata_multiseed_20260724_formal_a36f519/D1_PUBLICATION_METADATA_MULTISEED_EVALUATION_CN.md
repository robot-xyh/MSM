# D1 航迹发布元数据多种子评估

## 结论

不可变共享审计元数据候选的正式准入结论为 **不通过**。D6 只读取同一干净提交产生的 13 对三维质点 episode，不参与运行和控制。
系统实时性缺口 **未关闭**。候选臂最低实时因子为 0.146959；该判定与 D1 局部优化结论分离。

## 证据条件

| 项目 | 内容 |
| --- | --- |
| 源提交 | `a36f519ed954a9ba8bdc3fe149ba2835da290c39` |
| 矩阵 SHA256 | `2517b2ac22b8e2b39e5642b0b510419e1e7f9fa18d26f1f682b8330086ee5f2f` |
| 规模 | 200 个目标、200 个资源、2 个侦察节点 |
| 短时组 | seeds 1101-1110，每组 2.2 秒 |
| 长时组 | seeds 1101-1103，每组 10 秒 |
| 参考实现 | `per_track_copy_v1` |
| 候选实现 | `immutable_shared_v1` |
| bootstrap | 10000 次，随机种子 20260724 |

## 实现操作数

| 指标 | 参考 | 候选 |
| --- | ---: | ---: |
| 完整元数据物化 | 317055 | 317055 |
| 逐航迹共享审计映射复制 | 30860886 | 0 |
| 共享审计值复用 | 0 | 951165 |

## D1 融合结果

| 组别 | 参考均值/s | 候选均值/s | 均值比改善 | 逐对平均改善 | 候选更快 | 原始相对变化 95% 区间 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 短时 | 3.688192 | 3.087261 | 16.293368% | 16.238098% | 10/10 | [-17.571759, -14.510493]% |
| 长时 | 30.639399 | 21.126366 | 31.048366% | 31.010194% | 3/3 | [-32.926984, -28.472639]% |

逐 pair 原始相对变化按 `(候选-参考)/参考` 计算。耗时和内存指标的正向改善为原始变化取负值。组均值采用逐 pair 相对变化的算术均值，置信区间以 seed pair 为重采样单位。

## 系统阶段归因

| 组别 | D1 融合改善 | D2 关联改善 | 核心墙钟改善 |
| --- | ---: | ---: | ---: |
| 短时 | 16.293368% | -53.436714% | 1.645459% |
| 长时 | 31.048366% | -169.88836% | 1.205393% |

D1 融合阶段明显缩短，但 D2 关联阶段出现反向增长。只读源码核对确认，D2 的批量真值隔离审计只对精确的 Python 内建容器启用等值代表复用；候选的只读映射和序列包装未通过该类型门，因此共享诊断树仍按每条 GlobalTrack 递归扫描。该跨模块代价已由短时和长时核心墙钟至少改善 5% 的预注册门反映，不能用 D1 局部收益绕过。

## 语义审计

| 组别 | 业务语义通过 | 有限状态 | 在线真值隔离 | 实现身份一致 |
| --- | ---: | ---: | ---: | ---: |
| 短时 | 10/10 | 10/10 | 10/10 | 10/10 |
| 长时 | 3/3 | 3/3 | 3/3 | 3/3 |

在线总线逐条比较保留 D3 计划版本和前序关系，并校验 D4 内容地址与确认消息来源。D2 身份连续性、ID switch、D5 终端输出和 D7 导引输出均保持比较。离线真值状态、真值标签和距离事件只用于等价审计，在线真值使用计数必须为零。

## 准入门

| 判据 | 结果 | 原因 |
| --- | :---: | --- |
| `all_pairs_business_semantics_equal` | 通过 | - |
| `all_pairs_explicit_implementation_identity` | 通过 | - |
| `all_pairs_finite_state` | 通过 | - |
| `all_pairs_online_truth_use_count_zero` | 通过 | - |
| `every_pair_rss_degradation_within_5_pct` | 通过 | - |
| `long_candidate_faster_at_least_2_of_3` | 通过 | - |
| `long_core_wall_mean_improvement_at_least_5_pct` | 失败 | long_core_wall_mean_improvement_below_5_pct |
| `long_d1_fusion_mean_improvement_at_least_10_pct` | 通过 | - |
| `required_performance_metrics_available` | 通过 | - |
| `rss_mean_degradation_within_5_pct` | 通过 | - |
| `short_candidate_faster_at_least_8_of_10` | 通过 | - |
| `short_core_wall_mean_improvement_at_least_5_pct` | 失败 | short_core_wall_mean_improvement_below_5_pct |
| `short_d1_fusion_bootstrap_raw_ci_upper_below_zero` | 通过 | - |
| `short_d1_fusion_mean_improvement_at_least_10_pct` | 通过 | - |

## 证据边界

- 当前证据来自三维质点环境，不是 AirSim 或实机测试。
- 候选实现未通过正式准入时，不能写成默认路径已获性能准入。
- 墙钟、外部进程耗时、常驻内存和实时因子分层报告，未相加为单一指标。
- 运行配置、性能诊断和所有已读取输入文件 SHA256 保留在完整评估 JSON 中。

## 文件

- `d1_publication_metadata_multiseed_evaluation.json`：完整逐 pair 证据和门限。
- `d1_publication_metadata_multiseed_aggregate.json`：聚合结论。
- `d1_publication_metadata_multiseed_pairs.csv`：逐 pair 指标。
- `d1_publication_metadata_multiseed_improvement_curve.png`：短时和长时改善曲线。
