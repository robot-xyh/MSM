# D1 非雷达创新批处理性能基准

## 结论

逐候选路径 P50 为 `12.242 s`，批处理路径 P50 为 `10.238 s`，加速 `1.196x`。规范输出等价验收：`通过`。

## 输入与口径

- 源文件：`/tmp/MSM-scalable3d-candidate-0d2da25/research_modules/scalable_3d_simulation/outputs/scalable_3d_unseen_20seed_clean_0d2da25_20260722/10p0s_seed_1000/online_observations.jsonl`
- SHA-256：`0bcbfb1e64d19a687682105db763c0575377c7d1c6ba583c1276d1aa191af3cd`
- 选取扫描/观测：256 / 4087
- 同进程预热：每个变体 1 次，每次 128 个扫描
- 正式重复：每个变体 7 次，交错执行
- 机器：Intel(R) Core(TM) Ultra 9 185H，逻辑处理器 22，Python 3.12.3，NumPy 2.5.0

## 墙钟统计

| 路径 | 均值 / s | P50 / s | P95 / s | 最小 / s | 最大 / s |
| --- | ---: | ---: | ---: | ---: | ---: |
| 逐候选伪逆 | 12.506 | 12.242 | 13.340 | 12.004 | 13.357 |
| 矩阵栈批处理 | 10.385 | 10.238 | 11.248 | 9.960 | 11.620 |

## 完整时长交叉验证

同一未见 seed 的完整 10 秒输入含 771 个扫描、11,889 条观测，终态 201 条航迹。无 profiler 的纯融合墙钟由 `50.458 s` 降至 `39.994 s`，加速 `1.262x`。

cProfile 中，`process_scan_batch` 累计时间由 `80.035 s` 降至 `67.305 s`，非雷达代价矩阵由 `34.307 s` 降至 `17.320 s`。`numpy.linalg.pinv` 调用由 496,625 次降至 1,018 次，累计时间由 `14.837 s` 降至 `0.589 s`。cProfile 会放大绝对墙钟，本组只用它解释调用链变化。

完整输入的逐扫描摘要哈希为 `sha256:e5d4ec2ee902b1fa9e423f7b08380e14a08efec254cea193fad4611a022f4244`，终态航迹哈希为 `sha256:b53d506ee3bd4d9a50a3635387832db0c5321f74ccf3f77c18993e3892763d98`，一致性证据哈希为 `sha256:fc2e56948c68c614cebe685a3494be28067b554dd1a652b57b34ff71a93fa2ac`。两条路径的操作计数和累计诊断相同。

## 等价性

- 通过：`per_scan_semantic_digests_sha256`
- 通过：`final_tracks_sha256`
- 通过：`consistency_evidence_sha256`
- 通过：`operation_totals`
- 通过：`cumulative_diagnostics`
- 通过：`track_count`
- 通过：`materialized_snapshot_count`
- 通过：`state_only_scan_count`

## 边界

本基准只证明冻结输入上的 D1 模块性能和规范输出等价性。它不代表完整 D1-D7 闭环实时倍率，也不代表 AirSim 或实装传感器性能。
