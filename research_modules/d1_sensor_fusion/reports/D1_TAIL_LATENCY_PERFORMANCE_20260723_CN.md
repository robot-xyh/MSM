# D1 nominal 200v200 尾延时归因与扫描输入复用验证

## 证据边界

- 冻结输入：`/tmp/MSM-scalable3d-clean-5263e2b/research_modules/scalable_3d_simulation/outputs/scalable_3d_optimized_clean_5263e2b_20260723/10p0s_seed_1000_nominal/online_observations.jsonl`
- SHA-256：`5d033a049c2b4e09fb13d7c36e1117055b5b596d9e31f058ad2bf7cbd267ce8f`
- commit：`5263e2b343dc4b96d239f77ef09437eb132f9efb`；clean：`True`
- 场景：`200v200-nominal-v1`，seed `1000`，771 scans / 11,889 observations。
- 复现入口：`scripts/run_tail_latency_performance.py`；JSON 内记录输入哈希、交错轮数、扫描数、操作计数、profile 选择项与证据路径。
- 本报告使用冻结三维质点 replay，不是 AirSim、正式多 seed 或实时放行证据。
- clean/commit 只描述冻结输入来源；优化与等价复放运行在当前未提交 D1 工作区，不是新的 clean full-stack 放行。

clean episode 原始阶段分位为：D1 fusion P50/P95/max `33.285/223.447/630.727 ms`；scan-input P50/P95/max `1.397/131.918/315.661 ms`。

## Scan-input 低风险优化

旧路径在 `SensorScanFrame` 已完成只读深快照、truth/covariance/时间戳/lineage 校验后，organizer 又重建同一帧。新路径先核对轻量完整性封印；帧内对象或标量被替换、数组恢复可写时回退原完整重建和 fail-closed 校验。

| 操作数 | 旧路径 | 新路径 |
| --- | ---: | ---: |
| 已验证帧直接复用 | 0 | 771 |
| organizer 内帧重建 | 771 | 0 |
| organizer 内 observation 再快照 | 11,889 | 0 |

严格等价验收：`True`。逐输入 organizer 结果、逐 fusion posterior、物化 GlobalTrack、终态、一致性证据、完整 operation totals 和累计诊断均逐项一致。

前 256 scans 交错 5 轮的总耗时 P50/P95：旧路径 `1.629/1.988 s`，新路径 `0.467/0.557 s`。墙钟不参与通过判定。

| Scan-input 调用链 | 旧路径 cProfile 累计 / s | 新路径 cProfile 累计 / s |
| --- | ---: | ---: |
| `assert_online_observations_identity_free` | 9.215 | 0.000 |
| `SensorScanFrame.__post_init__` | 11.615 | 0.000 |
| `SensorObservation.__post_init__` | 0.250 | 0.000 |
| `ScanInputOrganizer.ingest` | 15.023 | 3.384 |
| `_snapshot_observation` | 1.651 | 0.000 |
| `_frame_snapshot_is_intact` | 0.000 | 0.061 |
| `_claim_for_frame` | 3.212 | 3.167 |
| `_digest` | 0.000 | 0.000 |
| `_json_safe` | 1.730 | 1.689 |

## Claim JSON 单次物化

旧 claim 路径分别为内容摘要和完整帧摘要递归转换相同的量测、协方差、元数据与谱系。新路径先生成一份 JSON 安全内容记录，再由该记录生成两个原格式 SHA-256；`allow_nan=False`、键排序和异常拒绝保持不变。

全流水严格等价验收：`True`。claim registry 摘要、逐输入事件、发布顺序、逐 fusion 状态/协方差/双时间戳/谱系/分级、操作计数、累计诊断、终态 GlobalTrack 和一致性证据均一致。

- 旧 claim registry：`sha256:22a713367482532d45e131e2aa9b0e6913d75cc6a7becffa85bf82f0b6eb8fd7`
- 新 claim registry：`sha256:22a713367482532d45e131e2aa9b0e6913d75cc6a7becffa85bf82f0b6eb8fd7`
- 771 scans / 11,889 observations，交错 5 轮 P50/P95：旧路径 `3.618/4.049 s`，新路径 `1.905/2.038 s`，P50 加速 `1.899x`。墙钟不参与等价通过判定。

| Claim 调用链 | 旧路径 cProfile 累计 / s | 新路径 cProfile 累计 / s |
| --- | ---: | ---: |
| `_legacy_claim_for_frame` | 8.358 | 0.000 |
| `_claim_for_frame` | 0.000 | 3.758 |
| `_digest` | 5.199 | 0.000 |
| `_digest_json_safe` | 0.780 | 0.740 |
| `_json_safe` | 5.781 | 1.992 |

## Fusion 归因

工作区复放分位 P50/P95/max 为 `38.731/210.797/329.116 ms`。该绝对值受当次主机负载影响，只用于与同轮操作数和调用链配对。

| 路径 | cProfile 累计 / s | 调用数 |
| --- | ---: | ---: |
| `_scan_one_to_one_assignments` | 18.246 | 771 |
| `_cached_non_radar_scan_cost_matrix` | 15.999 | 714 |
| `global_tracks` | 18.540 | 463 |
| `_to_global_track` | 17.775 | 91,151 |
| `_replay_record` | 9.217 | 13,185 |
| `_state_at` | 5.445 | 153,056 |
| `_state_from_complete_replay_checkpoints` | 4.026 | 156,636 |
| `_prune_record` | 0.891 | 9,348 |

radar scans 共 48 次，P95 `307.885 ms`；物化扫描共 463 次，P95 `238.166 ms`。候选对峰值扫描含 200 条 radar observation、200 条航迹与 40,000 个 candidate pairs；rebase 峰值为单扫描 197 次。若同一扫描还物化 GlobalTrack，成本进一步叠加。

本轮不修改 fusion 数学路径。检查点状态查询已使用完整 replay checkpoint 直接查询，同 fusion timestamp 已保持 308 次 state-only / 463 次完整物化。继续压缩 GlobalTrack 共享 audit metadata 或 radar/rebase 路径需要独立合同设计，不能以缩短窗口、丢观测、降频、放宽门控或 truth 换取性能。
