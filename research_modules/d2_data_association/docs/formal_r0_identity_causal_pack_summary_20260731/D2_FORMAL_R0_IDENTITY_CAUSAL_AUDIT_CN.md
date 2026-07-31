# D2 正式 R0 严格身份不可用因果诊断

## 结论

本次只读检查覆盖正式 R0 已完成的 450/900 个 episode。严格身份指标在 36 个 episode 不可用。这里的 episode 数与阻断映射事件数分开统计。

一航迹多真值涉及 27 个 episode、38 个映射事件。来源观测超出谱系窗口涉及 9 个 episode、518 个映射事件。不可用值保持为空，没有补写为零。

## 证据边界

输入根为 `/tmp/msm-formal-r0-20260731-80e55eb`。producer commit 为 `80e55eb43bc4a5feeac9c9af0d718d461a46401f`，execution-plan 逻辑哈希为 `sha256:b922ff5f95864345efa583da7256935694e5c675529989a659716522a0d7590e`。

发现过程校验 execution plan、shard plan、checkpoint、progress、cell result、episode identity、D6 manifest、D2 identity manifest 及其来源文件哈希。每个入选 episode 随后重放既有 D2 离线 evaluator，重放结果必须与持久化结果逐字段一致。

诊断读取独立真值 sidecar 解释既有结果，只能离线使用。它不修改在线 D2，不拆分航迹，不重写全局航迹号，不用位置最近邻推断身份，也不改变冻结的 0.9 秒身份承诺新鲜度门控。

## 一航迹多真值

全部一航迹多真值事件均记录历史真值簇、最新观测真值、来源传感器转换、身份承诺证据键和承诺原因。最新量测引入历史中尚未出现真值的事件为 36；历史谱系在最新量测前已经同时含多个真值的事件为 2。

该子集的身份承诺原因计数为：fresh_original_observation_accepted=38。

来源模态转换计数为：camera+radar->radar=2；radar->camera=17；radar->radar=19。最新相机来源分别为：`CAM-RECON-001` 5、`CAM-RECON-002` 1、`CAM-RECON-004` 6、`CAM-RECON-008` 5。

这些计数说明多真值合并与高密度、高规模证据相关，但不足以确认单一算法根因。后续在线候选只能使用几何、协方差、运动一致性、来源一致性、候选边和身份承诺状态等不含真值的信号。

## 谱系超窗

历史谱系旧、当前承诺来源仍在 0.9 秒内的事件为 517；当前承诺来源本身也超过 0.9 秒的事件为 1。

最老来源年龄范围为 0.9295 至 1.2552 秒，最新来源年龄范围为 0.2295 至 1.0670 秒，当前承诺来源年龄范围为 0.2295 至 1.0670 秒。每个映射事件均保留逐来源量测时刻、帧时刻、年龄、关联状态、传感器和承诺更新时间轴。

该分类不重算既有严格判定。历史来源超窗仍是证据完整性问题；当前承诺来源超窗则同时暴露发布新鲜度问题。两类问题都不能通过放宽窗口直接关闭。

## 规模分布

| 规模 | 不可用 episode | 阻断映射事件 | episode 原因 | 事件原因 |
| ---: | ---: | ---: | --- | --- |
| 5 | 4 | 23 | source_observation_outside_lineage_window=4 | source_observation_outside_lineage_window=23 |
| 100 | 9 | 499 | multiple_truth_targets_for_global_track=4；source_observation_outside_lineage_window=5 | multiple_truth_targets_for_global_track=4；source_observation_outside_lineage_window=495 |
| 200 | 23 | 34 | multiple_truth_targets_for_global_track=23 | multiple_truth_targets_for_global_track=34 |

一航迹多真值在 100 和 200 规模出现，5、20、50 规模未出现。该分布作为密度与规模相关证据保留，不能单独证明门控、匈牙利匹配、航迹起始或某一传感器是唯一原因。

## 制品

- `cases/<cell_id>.json`：逐案例完整因果证据和正式来源绑定。
- `cases/<cell_id>.csv`：逐案例阻断映射事件。
- `identity_blocker_cases.csv`：36 个 episode 摘要。
- `identity_blocker_mapping_events.csv`：全部阻断映射事件。
- `identity_blocker_causal_pack.json`：聚合计数、年龄和规模归因。
- `artifact_inventory.json` 与 `ARTIFACT_SHA256SUMS`：制品大小和 SHA-256。

## 后续工作

D2 P1 下一步使用这 36 个失败样本及同规模、同场景相邻通过样本设计不含真值的候选门控和承诺策略。任何在线算法变化都必须冻结新 producer commit 和 execution plan，并从 shard 0 重新运行。旧 450 个 episode 保持原判定，不重标注，也不与新候选结果拼接。
