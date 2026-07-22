# D1逐扫描融合性能基准

## 结论

冻结输入上的逐扫描航迹、批次摘要和一致性证据保持等价。历史滤波更新由 93,234 次降至 1,797 次，操作数下降 98.1%。
纯融合墙钟由 34.701 秒降至 9.073 秒，本机单次对照加速 3.82 倍。墙钟只用于说明，验收依据是确定性操作数和语义哈希。

## 输入

- 输入文件：`research_modules/scalable_3d_simulation/outputs/point_mass_integrated_observation_smoke_20260722_development_coalesced/nominal/200v200/seed_42000/online_observations.jsonl`
- SHA-256：`38d24429711b67d612f2f398478386ebf0df690fae55cd9dcc36434aac4fb078`
- 扫描/观测：86 / 2051
- 重排扫描：10
- 峰值缓冲：33 扫描 / 623 观测
- 在线真值使用：0

## 操作计数

| 指标 | 未缓存参考 | 增量检查点 |
| --- | ---: | ---: |
| `history_replay_count` | 18,249 | 18,249 |
| `finalization_replay_count` | 1,797 | 1,797 |
| `state_cache_hit_count` | 1,847 | 1,847 |
| `state_cache_miss_count` | 16,452 | 16,452 |
| `replay_filter_update_count` | 93,234 | 1,797 |
| `replay_checkpoint_reuse_count` | 0 | 91,437 |
| `global_track_materialization_count` | 16,653 | 16,653 |
| `sensor_health_snapshot_build_count` | 16,653 | 86 |

## 函数剖析

下表为 cProfile 累计时间。profiler 会放大墙钟，只用于定位函数占比。

| 函数 | 未缓存调用 | 未缓存累计秒 | 优化调用 | 优化累计秒 |
| --- | ---: | ---: | ---: | ---: |
| `process_scan_batch` | 86 | 64.744 | 86 | 17.657 |
| `_replay_record` | 18,249 | 46.097 | 18,249 | 6.837 |
| `_state_at` | 18,299 | 38.120 | 18,299 | 1.722 |
| `_filter_update` | 93,234 | 37.615 | 1,797 | 0.826 |
| `global_tracks` | 86 | 9.856 | 86 | 1.595 |
| `sensor_health_summaries` | 16,653 | 7.291 | 86 | 0.040 |

## 验收

- 通过：`consistency_evidence_equivalence`
- 通过：`final_track_equivalence`
- 通过：`one_health_snapshot_per_scan`
- 通过：`online_truth_use_count_zero`
- 通过：`per_scan_semantic_equivalence`
- 通过：`replay_filter_update_reduction_at_least_90_percent`

## 边界

本基准证明冻结质点输入上的 D1 逐扫描语义等价和操作数下降。
不证明真实传感器精度、AirSim 性能、200对200完整闭环实时性或物理拦截效果。
