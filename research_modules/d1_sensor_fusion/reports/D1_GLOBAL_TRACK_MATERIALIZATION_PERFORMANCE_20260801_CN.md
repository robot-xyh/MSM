# D1 GlobalTrack 完整物化批量质量摘要候选报告

## 结论

候选 `d1.publication.global_track_materialization.batched_a95_summary.v1` 的模块门结果为 `通过`。候选保持默认关闭，本报告不构成 main 接线或系统实时闭合证据。

冻结输入含 86 个扫描和 2,051 条匿名观测，SHA-256 为 `c6dcc69d58b0fc9a51e9cfcf2368b4faeb882d5a90991ffcdf1f7605bba55e53`。未运行正式 seeds 1000--1019，未运行正式 R0。

## 热点选择

当前 reference 剖析中，`global_tracks` 累计 `0.443068 s`，`_to_global_track` 累计 `0.290990 s`，scan-input 墙钟为 `0.138621 s`。完整航迹物化是本轮两个允许方向中较大的热点，因此只推进这一身份。

未剖析的 7 次 reference 中，完整航迹物化和 scan-input 墙钟中位数分别为 `0.228742` 和 `0.158849 s`。

候选把同一发布帧内逐航迹执行的二维位置协方差特征值分解合并为一个批量调用。状态和协方差仍逐航迹复制，完整元数据、双时间戳、谱系、质量分档和编号均保持原格式。

## 预注册门

- `paired_run_count_at_least_seven`：`True`
- `candidate_faster_fraction_at_least_80_percent`：`True`
- `median_module_wall_improvement_at_least_10_percent`：`True`
- `paired_bootstrap_difference_95_percent_upper_below_zero`：`True`
- `semantic_equivalence_all_pairs`：`True`
- `operation_conservation_all_pairs`：`True`
- `candidate_default_off_all_pairs`：`True`
- `online_truth_isolated_all_pairs`：`True`
- `implementation_identity_exact_all_pairs`：`True`

## 性能

交替 fresh-process 共 7 对。候选更快比例为 `1.000000`，reference/candidate 模块墙钟中位数为 `0.228742/0.190582 s`，中位改善 `16.682%`。

配对模块墙钟差的 bootstrap 95% 区间为 `[-0.044637, -0.031457] s`。

| 指标 | Reference | Candidate |
| --- | ---: | ---: |
| 模块 run P50 / s | 0.228742 | 0.190582 |
| 模块 run P95 / s | 0.229523 | 0.194719 |
| 模块 run max / s | 0.229629 | 0.195816 |
| 单次发布 P50 / ms | 3.168315 | 2.519885 |
| 单次发布 P95 / ms | 4.999508 | 4.184879 |
| 单次发布 max / ms | 24.928044 | 27.490811 |
| 全融合 run P50 / s | 2.977062 | 2.928923 |
| 全融合 run P95 / s | 2.990879 | 2.946391 |
| 全融合 run max / s | 2.993028 | 2.946844 |
| 峰值 RSS P50 / KiB | 165528 | 165312 |
| 峰值 RSS P95 / KiB | 165853 | 165987 |
| 峰值 RSS max / KiB | 165908 | 166000 |

全融合与 scan-input 墙钟也已记录，但不用于本候选的 10% 模块门。局部物化收益不能外推为 200 对 200 实时闭合。

## 语义与工作量

逐扫描语义通过 `7/7`，工作量守恒通过 `7/7`。比较范围包含后验、协方差、NIS、门控观测编号、完整 publication payload、一致性证据、业务操作计数和最终离线导出。

逐航迹标量质量摘要从每臂 `11,188` 次改为每发布帧一次批量特征值调用；候选仍对每条物化航迹记录一次质量摘要请求和一次结果复用。在线真值使用和 `global_track_id` 写权限均为 0。

每个 fresh arm 执行 `59` 次完整发布，物化 `11,188` 条航迹。reference 标量摘要 `11,188` 次；candidate 批量矩阵 `11,188` 个、批量特征值调用 `56` 次。

## 边界

- 候选默认关闭，reference 构造行为保持不变。
- 没有改变融合数学、扩展卡尔曼滤波、乱序量测处理、固定滞后、门控或质量门限。
- 没有运行 AirSim、正式 R0、目标硬件或正式 seeds 1000--1019。
- main 是否接线需要独立集成审查和系统级多 seed 验收。
