# D5 正式图未标注边溯源审计

## 结论

正式语料包含 `99` 条未标注候选边，涉及 `194` 个缺失端点。可由同帧离线观测来源链直接证明的边为 `0` 条，仍不可用的边为 `99` 条。

未使用最近邻、跨帧轨迹编号沿用或几何相似度生成标签。正式图、标签和 manifest 均未修改。标签不完整帧只在后续分离式准入视图中排除。

## 来源证据

- 正式 manifest SHA-256：`d9a84007995fe94918483bd5cb5ddc38f60f61d819bea27137dfa2619bf75426`
- 独立观测来源链：`not_preserved_in_frozen_formal_export`
- 来源链记录数：`0`
- 精确来源链端点数：`0`

## 缺失类型

- `both_endpoints_missing`：`95` 条。
- `source_endpoint_missing`：`4` 条。

## 分割

- `test`：`15` 条。
- `train`：`65` 条。
- `validation`：`19` 条。

## 场景

- `center_failure-100v100-v1`：`1` 条。
- `communication_degraded-200v200-v1`：`1` 条。
- `delayed_noisy-100v100-v1`：`16` 条。
- `delayed_noisy-200v200-v1`：`61` 条。
- `delayed_noisy-50v50-v1`：`6` 条。
- `dense_crossing-100v100-v1`：`2` 条。
- `dense_crossing-200v200-v1`：`4` 条。
- `evasive_multilevel-200v200-v1`：`1` 条。
- `evasive_multilevel-50v50-v1`：`1` 条。
- `formation_split-200v200-v1`：`2` 条。
- `high_threat_m_to_n-200v200-v1`：`1` 条。
- `high_threat_m_to_n-50v50-v1`：`1` 条。
- `nominal-200v200-v1`：`1` 条。
- `secondary_failure-200v200-v1`：`1` 条。

## 处置

不可证明的端点继续标记为 `unavailable`。补充课程使用独立物理投影和独立 evaluator 标签生成新样本，不回填冻结正式语料。
