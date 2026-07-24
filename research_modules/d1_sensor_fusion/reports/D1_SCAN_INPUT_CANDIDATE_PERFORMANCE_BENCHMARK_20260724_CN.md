# D1 扫描输入 reference/candidate 专项基准

## 结论

严格等价验收：`True`。candidate 是默认路径，reference 保留为显式可选路径。墙钟只作专项性能描述，不参与等价放行。

本次输入为 `570` 帧、`10,810` 条匿名观测；冻结文件 SHA-256 为 `5b47f3cf43a9bf78bfca0db249bbefeb709a10c1a7aa6bb4277226fc2144e2d6`。计时前已完成帧构造，结果不包含传感器 payload 转换、融合、D2 关联或 AirSim。

## 严格等价

- `claim_content_frame_digest_equivalence`：`True`
- `result_event_field_equivalence`：`True`
- `release_order_equivalence`：`True`
- `audit_summary_equivalence`：`True`
- `default_candidate_selected`：`True`

## 操作计数

| 操作 | reference | candidate |
| --- | ---: | ---: |
| `claim_build_count` | 570 | 570 |
| `claim_observation_count` | 10,810 | 10,810 |
| `source_lineage_reconstruction_count` | 10,810 | 0 |
| `cached_source_lineage_reuse_count` | 0 | 10,810 |
| `lineage_sort_key_construction_count` | 21,620 | 10,810 |
| `buffer_partition_pass_count` | 1,140 | 570 |
| `buffer_partition_item_visit_count` | 35,406 | 17,703 |
| `buffered_observation_count_rescan_count` | 2,281 | 0 |
| `buffered_observation_count_rescan_item_visit_count` | 67,876 | 0 |
| `buffered_observation_count_cache_read_count` | 0 | 2,281 |

## 交错墙钟

交错运行 `7` 轮。reference P50/P95 为 `1.078281/1.084012 s`；candidate P50/P95 为 `0.756634/0.766820 s`。P50 加速比为 `1.425x`，P50 墙钟下降 `29.830%`。

## 证据边界

- 本结果属于 D1 实现与冻结回放专项证据。
- main 正式 13-pair 矩阵尚未运行，不能据此关闭系统实时 P1。
- 本轮没有改变双时间戳、NED、协方差、真值隔离、6 秒 fixed-lag、量测频率、缓冲门限或 global_track_id 合同。
