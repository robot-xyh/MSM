# 高威胁 M 对 N 修复后干净来源复核

## 结论

D6 于 2026-07-31 对
`/dev/shm/msm-high-threat-clean-smoke-b063535-20260731` 完成独立只读复核。批次由
clean commit `b063535c5473b67e41683f84c33c088ce5c7d41a` 生成，来源 worktree
`/dev/shm/msm-clean-smoke-b063535` 在复核时保持干净。范围为 5 对 5、100 对 100 和
200 对 200 三档规模，每档 seed `7/17`，共 6 个 episode。每项仿真 2 秒，运行路径为
集成规则栈。

修复后的 6-cell smoke 达到 D4 建议代次预准入要求：

- 6 个 episode 的 42 个核心制品全部存在，五类离线消费 sidecar 均为 `6/6`；
- 来源提交、`repository_dirty=false`、配置哈希、有限状态和在线真值隔离均为 `6/6`；
- 最终 D3-D4 计划标识、版本、权威时期、租约和当前联盟均为 `6/6`；
- 10 次 D3 权威发布对应 10 个不同计划身份和 10 次运行时确认；
- 49 个当前多成员联盟目标全部闭合；
- 16101 条通信处置在 6 个 episode 中全部通过逐记录验证；
- 12 条 D4 区域资源建议全部匹配各自发布时刻的最新 D3-D4 代次，发布时旧代为 0；
- 每个 episode 均有至少一条建议匹配最终计划，当前建议覆盖为 `6/6`；
- 低层 `formal_acceptance_eligible` 从旧批次的 `2/6` 恢复为 `6/6`。

旧报告
`HIGH_THREAT_CLEAN_SMOKE_49E43EA_20260731_CN.md` 识别的
`d4_advice_version_evidence_issue` 已在同范围 clean smoke 中消失。D6 没有过滤旧记录、
没有放宽低层门，也没有修改原始 episode。

**准入判断：D4 建议代次的 6-cell 预准入通过。** main 可以在冻结 execution plan、
规范分片和存储保护线满足后启动正式 900-cell R0。该 smoke 不含正式实验矩阵 metadata，
因此不能写成 targeted/full posterior 正式通过，更不能替代 900-cell 结果。

完整身份交换计数仍只有 `3/6 available`，可用部分合计 0。其余 3 项保持 unavailable，
部分身份下界合计 9，不能替代完整计数。100 对 100 和 200 对 200 仍未达到实时倍率 1。

## 审计范围

| 项 | 值 |
| --- | --- |
| 场景 | `high_threat_m_to_n` |
| 规模 | 5、100、200 |
| seed | 每档 `7/17` |
| episode 数 | 6 |
| 单项仿真时长 | 2.0 秒 |
| 运行路径 | integrated rule stack |
| 来源提交 | `b063535c5473b67e41683f84c33c088ce5c7d41a` |
| 来源状态 | `repository_dirty=false`，6/6 |
| 证据级别 | clean-source smoke，正式矩阵前置复核 |

D6 只消费持久化制品。独立重算输出写入
`/dev/shm/msm-d6-clean-smoke-audit-b063535-20260731`。原始输出目录未修改。

## 制品与来源

每个 episode 均包含以下七个核心制品：

- `manifest.json`；
- `scenario_config.json`；
- `summary.json`；
- `stage_timings.csv`；
- `online_observations.jsonl`；
- `offline_proximity_intercepts.jsonl`；
- `offline_truth_labels.jsonl`。

核心制品完整率为 `42/42`。以下离线消费目录均为 `6/6`：

- `d6_runtime_plan_outcomes`；
- `d6_truth_isolated`；
- `observation_governance`；
- `offline_consistency`；
- `offline_identity`。

D6 对 `scenario_config.json` 使用键排序、无空白分隔的规范 JSON 重算 SHA-256，6 项均与
manifest 的 `config_sha256` 一致。六个 manifest 的 `git_commit` 均为受审提交，
`repository_dirty` 均为 false。有限状态为 `6/6`，在线真值使用和禁用真值字段违规均为 0。

## 当前计划绑定

| 规模/seed | 最终计划 | 版本 | 时期匹配 | 租约匹配 | 当前联盟目标 | 联盟闭合 |
| --- | --- | ---: | --- | --- | ---: | --- |
| 5/7 | `d3-plan-705b44c93b21` | 1 | 通过 | 通过 | 1 | 通过 |
| 5/17 | `d3-plan-7c1d827ddac6` | 1 | 通过 | 通过 | 1 | 通过 |
| 100/7 | `d3-plan-d64dc63afa55` | 2 | 通过 | 通过 | 11 | 通过 |
| 100/17 | `d3-plan-35896905e541` | 2 | 通过 | 通过 | 10 | 通过 |
| 200/7 | `d3-plan-072f772d891c` | 2 | 通过 | 通过 | 13 | 通过 |
| 200/17 | `d3-plan-b9dafabcdaa3` | 2 | 通过 | 通过 | 13 | 通过 |
| 合计 | - | - | 6/6 | 6/6 | 49 | 6/6 |

D6 以最后一次 `modules.d3.assignment_plan` 为当前 D3 计划，以最后一次
`modules.d4.regional_failover` 为当前 D4 决策。每个区域均核对 `plan_id`、
`plan_version`、`epoch`、`lease_expires_at_s`、owner 和联盟提交。旧代 committed 状态
不能替代当前计划。

## 发布守恒

| 规模 | 权威发布 | 不同计划身份 | 运行时确认 | 评价刷新抑制 | 摘要冲突 | 传输引用冲突 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 5 | 2 | 2 | 2 | 2 | 0 | 0 |
| 100 | 4 | 4 | 4 | 0 | 0 | 0 |
| 200 | 4 | 4 | 4 | 0 | 0 | 0 |
| 合计 | 10 | 10 | 10 | 2 | 0 | 0 |

10 次权威发布均携带 `authority_epoch`、`lease_expires_at_s`、
`regional_max_epoch` 和 `regional_min_lease_expires_at_s`。通用时期与区域最大时期一致，
通用租约与区域最小租约一致。5 对 5 的两次评价刷新只保留诊断，没有形成重复权威发布。

## 建议代次

D6 按事件序列处理建议。每遇到一条 `modules.d4.region_resource_advice`，只与该记录之前
最后一条 `modules.d4.regional_failover` 比较，不使用 episode 最终快照追溯改判历史记录。
比较字段包括计划标识、版本、时期、租约、owner 和 owner layer。

| 规模/seed | 最终计划版本 | 建议总数 | 发布时当前代 | 发布时旧代 | 匹配最终计划 | 最终计划覆盖 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 5/7 | 1 | 2 | 2 | 0 | 2 | 是 |
| 5/17 | 1 | 2 | 2 | 0 | 2 | 是 |
| 100/7 | 2 | 2 | 2 | 0 | 1 | 是 |
| 100/17 | 2 | 2 | 2 | 0 | 1 | 是 |
| 200/7 | 2 | 2 | 2 | 0 | 1 | 是 |
| 200/17 | 2 | 2 | 2 | 0 | 1 | 是 |
| 合计 | - | 12 | 12 | 0 | 8 | 6/6 |

100 对 100 和 200 对 200 的四项均先发布一条当时有效的 v1 建议，随后发布 v2 计划及
对应的 v2 建议。v1 建议在发布时有效，之后成为历史记录；它不计为发布时旧代。v2 建议
均紧跟当前 v2 D3/D4 发布，计划标识、版本、时期和租约完整匹配。

本批共有 10 条故障诊断建议。它们包含投影拒绝、hold 或 request-replan 条件，但仍绑定
发布时当前代次。10 条记录均为 `shadow`，`assist_eligible=false`，正式决策摘要保持不变。
因此这些记录计为“当前代可发布的只读诊断”，不计为旧代，也不计为规划采用。

原始 episode 没有 `modules.d4.region_resource_consumption` 记录，D6 将控制采用保持为
unavailable，不补写为 0。运行制品同时没有单独持久化 `planning_consumable` 布尔字段。
本报告只能确认 shadow、非 assist、无消费记录和正式决策未改变；不能把“未观测到采用”
扩写为独立的控制效果结论。

## 正式门

低层 `scalable_3d_offline` 对六项重算结果如下：

- `formal_acceptance_eligible=6/6`；
- `failure_reason_distribution={}`；
- D4 advice publication 为 12，valid 为 12，invalid/stale/version issue 均为 0；
- 当前 D3-D4 计划绑定和联盟闭合的独立审计为 `6/6`。

该结果关闭了旧批次的 D4 advice 低层失败原因。D6 没有从记录中删除 v1 历史建议；v1 在
发布时有效，因此保留并通过事件时序审计。

targeted/full posterior 正式入口还有矩阵级前提：冻结 execution plan、规范 20 shard、
cell result 和 artifact-tree 摘要、`experiment_matrix_formal_acceptance_eligible=true`，
以及 `episode_evidence_status=clean_formal_experiment_matrix`。本 6-cell smoke 没有这些
正式矩阵 metadata，证据状态为 `descriptive_clean_source_calibration`。直接运行矩阵级
适用门会按范围缺失失败关闭，原因是：

- `experiment_matrix_formal_not_eligible`；
- `matrix_failures_nonempty`；
- `variant_failures_nonempty`；
- `episode_evidence_status_not_clean_formal_matrix`。

这些原因说明 smoke 不能冒充正式矩阵，不表示 D4 建议代次仍失败。正式 900-cell 生成后，
targeted/full posterior 必须对每个 cell 重新执行相同低层门、计划绑定门和矩阵完整性门。
full posterior 的 required-evidence 适用门在六项中均只报告
`required_evidence_unavailable:experiment_matrix_formal_acceptance_eligible`；计划绑定、
联盟和其他必需低层字段在合并独立计划审计结果后均可用。

## 通信处置

| 规模 | 记录 | delivered | dropped | pending | 文件验证 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 5 | 316 | 301 | 3 | 12 | 2/2 |
| 100 | 5324 | 5069 | 57 | 198 | 2/2 |
| 200 | 10461 | 9949 | 106 | 406 | 2/2 |
| 合计 | 16101 | 15319 | 166 | 616 | 6/6 |

`pending` 是 episode 结束时的显式最终处置，不改记为 delivered。49 个当前联盟目标仍全部
闭合，说明 pending 记录没有留下最终当前联盟成员缺口。

## 离线身份

| 规模/seed | 完整 ID Switch | 可用值 | 部分证据下界 | 不可用原因 |
| --- | --- | ---: | ---: | --- |
| 5/7 | available | 0 | 0 | 无 |
| 5/17 | available | 0 | 0 | 无 |
| 100/7 | available | 0 | 0 | 无 |
| 100/17 | unavailable | - | 0 | `source_observation_outside_lineage_window` |
| 200/7 | unavailable | - | 2 | `multiple_truth_targets_for_global_track` |
| 200/17 | unavailable | - | 7 | `multiple_truth_targets_for_global_track` |

完整 ID Switch 为 `3/6 available`，可用部分合计 0。部分下界六项均可用，合计 9，但只
表示可证明的最小切换数，不能替代完整指标，也不能加入完整可用部分合计。

## 运行性能

| 规模 | 实时倍率均值 | 实时倍率最小值 | 墙钟均值/秒 | 墙钟最大值/秒 |
| ---: | ---: | ---: | ---: | ---: |
| 5 | 6.778 | 6.498 | 0.296 | 0.308 |
| 100 | 0.357 | 0.351 | 5.597 | 5.705 |
| 200 | 0.144 | 0.143 | 13.897 | 13.950 |
| 全部 | 2.426 | 0.143 | 6.596 | 13.950 |

5 对 5 快于实时。100 对 100 和 200 对 200 未达到实时倍率 1。每档只有两个 seed，且未
冻结主机负载；这些数据用于 smoke 成本边界，不构成部署性能结论。

## 与旧批次对照

| 指标 | `49e43ea` | `b063535` | 变化 |
| --- | ---: | ---: | --- |
| 发布时旧代 advice | 4 | 0 | 断点关闭 |
| 发布时有效 advice | 8/12 | 12/12 | 全部有效 |
| 最终计划建议覆盖 | 2/6 | 6/6 | 四个重规划项补齐 |
| `formal_acceptance_eligible` | 2/6 | 6/6 | 低层门恢复 |
| 当前计划绑定 | 6/6 | 6/6 | 无退化 |
| 当前联盟目标闭合 | 49/49 | 49/49 | 无退化 |
| 在线真值使用 | 0 | 0 | 无退化 |
| 完整 ID Switch 可用 | 3/6 | 3/6 | 未改善 |

## 后续条件

正式 900-cell 启动前，main 仍需完成以下工作：

1. 冻结 clean source、execution plan 逻辑 SHA-256、20 个 shard 和 900-cell 分母；
2. 确认输出存储空间和保护线，避免运行中断或覆盖既有证据；
3. 每个 cell 保留当前计划建议、计划确认、联盟和通信处置证据；
4. D6 对完整范围运行 targeted/full posterior，不接受抽样外推；
5. 完整 ID Switch 缺值继续保持 unavailable，并由 D2/main 另行关闭谱系缺口；
6. 性能报告继续按规模分组，不把 2 秒 smoke 的实时倍率写成部署能力。

## 文件摘要

- 原始 `aggregate.json`：
  `0f6eba1e02c263f6f54177115df3cf0af165e92246098c0eeb08fe5e24302422`；
- 原始 `episode_summary.csv`：
  `2c51e25aa3bd44ac1b6d599f114c295571900bdd3e3630bd1a09c5c338303fe3`；
- 原始 `truth_isolated_aggregate.json`：
  `67891dfbc79b38e3713c15c1d4d6a8e3e5559199b81d03c580ebbc64a67898c9`；
- D6 独立重算 `scalable_3d_offline_aggregate.json`：
  `f1e2c87c0b5d46aa28ba24cbb78a3a479087faccd78e491c27679415f1db7fc9`；
- D6 独立重算 `scalable_3d_offline_per_episode_seed.csv`：
  `b8d5dadd2bca88b1ffa8a3d6691e01b57df5c509bee02b201210ceddf6a5e7e5`。

## 验证边界

本轮没有修改 D6 算法代码，没有修改 main/runtime、D4 或原始输出。独立制品断言覆盖
来源、核心制品、配置哈希、真值隔离、计划绑定、权威发布唯一性、运行时确认、联盟、
通信、建议代次和身份 availability。

正式 targeted/full posterior 的生产入口未在 6-cell smoke 上伪造 execution plan；其
矩阵级完整性由现有专项测试验证，正式结论等待 900-cell 原生分片输入。Matplotlib
`Axes3D` 环境警告不影响 JSONL、哈希、计划绑定或建议代次审计。

- 6-cell 独立制品和建议时序断言：通过；
- `test_scalable_3d_offline.py`、`test_formal_r0_plan_binding_audit.py`、
  `test_formal_r0_targeted_posterior_audit.py`、
  `test_formal_r0_full_posterior_audit.py`：`95 passed, 1 warning in 9.51s`；
- warning 为既有 Matplotlib `Axes3D` 导入提示。
