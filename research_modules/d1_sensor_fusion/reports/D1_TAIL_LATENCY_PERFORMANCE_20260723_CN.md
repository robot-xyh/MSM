# D1 nominal 200v200 尾延时归因与扫描输入复用验证

## 证据边界

- 冻结输入：`/tmp/MSM-scalable3d-candidate-4ac3bb2/research_modules/scalable_3d_simulation/outputs/scalable_3d_timing_v2_clean_4ac3bb2_20260722/10p0s_seed_1000_nominal/online_observations.jsonl`
- SHA-256：`c1dda8523e48c255bbeef48d9516b05863eb1bbb3a3ae2e09733259e6a66f77a`
- commit：`4ac3bb2c12cc6af6ebd372107ced00bcdc5adf6a`；clean：`True`
- 场景：`200v200-nominal-v1`，seed `1000`，771 scans / 11,889 observations。
- 复现入口：`scripts/run_tail_latency_performance.py`；JSON 内记录输入哈希、交错轮数、扫描数、操作计数、profile 选择项与证据路径。
- 本报告使用冻结三维质点 replay，不是 AirSim、正式多 seed 或实时放行证据。
- clean/commit 只描述冻结输入来源；优化与等价复放运行在当前未提交 D1 工作区，不是新的 clean full-stack 放行。

clean episode 原始阶段分位为：D1 fusion P50/P95/max `33.252/224.764/592.957 ms`；scan-input P50/P95/max `1.747/177.084/361.536 ms`。

## Scan-input 低风险优化

旧路径在 `SensorScanFrame` 已完成只读深快照、truth/covariance/时间戳/lineage 校验后，organizer 又重建同一帧。新路径先核对轻量完整性封印；帧内对象或标量被替换、数组恢复可写时回退原完整重建和 fail-closed 校验。

| 操作数 | 旧路径 | 新路径 |
| --- | ---: | ---: |
| 已验证帧直接复用 | 0 | 771 |
| organizer 内帧重建 | 771 | 0 |
| organizer 内 observation 再快照 | 11,889 | 0 |

严格等价验收：`True`。逐输入 organizer 结果、逐 fusion posterior、物化 GlobalTrack、终态、一致性证据、完整 operation totals 和累计诊断均逐项一致。

前 256 scans 交错 5 轮的总耗时 P50/P95：旧路径 `1.942/1.968 s`，新路径 `0.881/0.894 s`。墙钟不参与通过判定。

| Scan-input 调用链 | 旧路径 cProfile 累计 / s | 新路径 cProfile 累计 / s |
| --- | ---: | ---: |
| `assert_online_observations_identity_free` | 7.717 | 0.000 |
| `SensorScanFrame.__post_init__` | 9.710 | 0.000 |
| `SensorObservation.__post_init__` | 0.207 | 0.000 |
| `ScanInputOrganizer.ingest` | 15.545 | 5.754 |
| `_snapshot_observation` | 1.391 | 0.000 |
| `_frame_snapshot_is_intact` | 0.000 | 0.051 |
| `_claim_for_frame` | 5.681 | 5.580 |
| `_digest` | 3.548 | 3.507 |
| `_json_safe` | 3.954 | 3.910 |

## Fusion 归因

工作区复放分位 P50/P95/max 为 `34.108/178.420/354.413 ms`。该绝对值受当次主机负载影响，只用于与同轮操作数和调用链配对。

| 路径 | cProfile 累计 / s | 调用数 |
| --- | ---: | ---: |
| `_scan_one_to_one_assignments` | 17.027 | 771 |
| `_cached_non_radar_scan_cost_matrix` | 14.971 | 714 |
| `global_tracks` | 17.559 | 463 |
| `_to_global_track` | 16.930 | 91,151 |
| `_replay_record` | 8.601 | 13,185 |
| `_state_at` | 5.023 | 153,056 |
| `_state_from_complete_replay_checkpoints` | 3.735 | 156,636 |
| `_prune_record` | 0.829 | 9,348 |

radar scans 共 48 次，P95 `343.059 ms`；物化扫描共 463 次，P95 `216.991 ms`。候选对峰值扫描含 200 条 radar observation、200 条航迹与 40,000 个 candidate pairs；rebase 峰值为单扫描 197 次。若同一扫描还物化 GlobalTrack，成本进一步叠加。

本轮不修改 fusion 数学路径。检查点状态查询已使用完整 replay checkpoint 直接查询，同 fusion timestamp 已保持 308 次 state-only / 463 次完整物化。继续压缩 GlobalTrack 共享 audit metadata 或 radar/rebase 路径需要独立合同设计，不能以缩短窗口、丢观测、降频、放宽门控或 truth 换取性能。
