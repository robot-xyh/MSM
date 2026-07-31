# 高威胁 M 对 N 干净来源冒烟审计

## 结论

D6 于 2026-07-31 对
`/dev/shm/msm-high-threat-clean-smoke-49e43ea-20260731` 完成只读审计。批次由干净的
detached worktree 提交
`49e43eacf627315a75093a3b381c9f810b11905e` 生成，包含 5 对 5、100 对 100 和
200 对 200 三档规模，每档使用 seed `7/17`，共 6 个 episode。每项仿真 2 秒，运行
集成为规则栈。

干净来源和核心运行合同通过：

- 6 个 manifest 均声明 `repository_dirty=false`，来源提交一致；
- 42 个核心制品全部存在，五类 D6 消费 sidecar 均为 `6/6`；
- 配置哈希、有限状态、在线真值零使用均为 `6/6`；
- D3-D4 当前计划标识、版本、权威时期和租约均为 `6/6 available/matched`；
- 10 次 D3 权威发布对应 10 个不同计划身份和 10 次运行时计划确认；
- 49 个当前多成员联盟目标全部闭合；
- 16101 条通信处置在 6 个 episode 中全部通过逐记录验证。

本批次同时复现了 `d4_advice_version_evidence_issue`。100 对 100 和 200 对 200 的
4 个 episode 均发生一次重规划。新 D3/D4 计划发布后，D4 又发布了一条仍绑定旧计划
标识、版本、时期和租约的区域资源建议。该建议在发布时已经过时，不只是最终聚合时被新
计划取代。4 个受影响 episode 都没有一条匹配最终计划的区域资源建议。

区域资源建议运行在 `shadow` 模式，来源为规则算法，四条过时建议均声明正式决策未改变。
因此，本问题没有破坏最终 D3-D4 绑定、联盟闭合或控制状态。但现有 D6 低层正式门会将
每个受影响 episode 的 `formal_acceptance_eligible` 置为 false。正式 targeted
posterior 直接使用该低层门；full posterior 又要求每个 cell 的该证据可用且为真。
若正式 900-cell 中出现相同记录，对应 cell 和全量结论都会失败关闭。

**900-cell 准入建议：需先修复。** 6-cell smoke 不是正式结果，也不能用于推算正式
通过率。当前不建议先消耗完整 900-cell 运行成本。main/D4 应先阻断重规划后的旧快照建议
发布，或将其显式标记为不可采用的 superseded 诊断，并为当前计划生成可核验建议。修复后
先复跑同一 6-cell smoke，要求建议错代为 0、当前计划建议覆盖 `6/6`，同时保持本报告
其余合同不退化，再启动冻结的正式 900-cell。

## 审计范围

| 项 | 值 |
| --- | --- |
| 场景 | `high_threat_m_to_n` |
| 规模 | 5、100、200 |
| seed | 每档 `7/17` |
| episode 数 | 6 |
| 单项仿真时长 | 2.0 秒 |
| 运行路径 | integrated rule stack |
| 来源提交 | `49e43eacf627315a75093a3b381c9f810b11905e` |
| 工作树状态 | `repository_dirty=false`，6/6 |
| 证据级别 | clean-source smoke，不是正式 900-cell |

D6 没有导入或调用 main、D3、D4 控制逻辑，也没有修改 episode。独立审计输出写入
`/dev/shm/msm-d6-clean-smoke-audit-49e43ea-20260731`。

## 制品与来源

每个 episode 均存在以下七个核心制品：

- `manifest.json`；
- `scenario_config.json`；
- `summary.json`；
- `stage_timings.csv`；
- `online_observations.jsonl`；
- `offline_proximity_intercepts.jsonl`；
- `offline_truth_labels.jsonl`。

核心制品完整率为 `42/42`。以下五类离线消费目录均为 `6/6`：

- `d6_runtime_plan_outcomes`；
- `d6_truth_isolated`；
- `observation_governance`；
- `offline_consistency`；
- `offline_identity`。

配置正文重算 SHA-256 后与 manifest 的 `config_sha256` 一致 `6/6`。六个 manifest
的 `git_commit` 均为受审提交，`repository_dirty` 均为 false。有限状态为 `6/6`，
在线真值使用和禁用真值字段违规均为 0。

## 当前计划绑定

| 规模/seed | 计划标识 | 计划版本 | 时期 | 租约 | 当前联盟目标 | 联盟闭合 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 5/7 | 通过 | 通过 | available/match | available/match | 1 | 通过 |
| 5/17 | 通过 | 通过 | available/match | available/match | 1 | 通过 |
| 100/7 | 通过 | 通过 | available/match | available/match | 11 | 通过 |
| 100/17 | 通过 | 通过 | available/match | available/match | 10 | 通过 |
| 200/7 | 通过 | 通过 | available/match | available/match | 13 | 通过 |
| 200/17 | 通过 | 通过 | available/match | available/match | 13 | 通过 |
| 合计 | 6/6 | 6/6 | 6/6 | 6/6 | 49 | 6/6 |

10 次 D3 权威发布的 metadata 均携带：

- `authority_epoch`；
- `lease_expires_at_s`；
- `regional_max_epoch`；
- `regional_min_lease_expires_at_s`。

四字段完整率为 `10/10`。通用时期与区域最大时期一致，通用租约与区域最小租约一致。
D4 最终 ownership 与 D3 当前计划逐区域匹配。

## 发布守恒

| 规模 | 权威发布 | 不同计划身份 | 运行时确认 | 评价刷新抑制 | 摘要冲突 | 传输引用冲突 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 5 | 2 | 2 | 2 | 2 | 0 | 0 |
| 100 | 4 | 4 | 4 | 0 | 0 | 0 |
| 200 | 4 | 4 | 4 | 0 | 0 | 0 |
| 合计 | 10 | 10 | 10 | 2 | 0 | 0 |

每个 episode 均满足权威发布数、不同 `(plan_id, plan_version)` 数和
`assignment_plan_ack_count` 三方相等。同身份重复权威发布为 0。5 对 5 的两次评价刷新
只保留诊断，没有形成第二次权威发布。

## 建议代次

区域资源建议共 12 条。D6 按建议发布时刻之前最后一条
`modules.d4.regional_failover` 逐区域比较计划标识、版本、时期和租约。

| 规模/seed | 最终计划 | 建议总数 | 发布时有效 | 发布时过时 | 匹配最终计划 |
| --- | --- | ---: | ---: | ---: | ---: |
| 5/7 | v1 | 2 | 2 | 0 | 2 |
| 5/17 | v1 | 2 | 2 | 0 | 2 |
| 100/7 | v2 | 2 | 1 | 1 | 0 |
| 100/17 | v2 | 2 | 1 | 1 | 0 |
| 200/7 | v2 | 2 | 1 | 1 | 0 |
| 200/17 | v2 | 2 | 1 | 1 | 0 |
| 合计 | - | 12 | 8 | 4 | 4 |

三类记录必须分开解释：

1. **当前计划建议。** 5 对 5 没有产生新计划，两项各两条建议均绑定最终 v1。
2. **已被取代的历史有效建议。** 四个重规划 episode 的第一条建议在 v1 有效期内发布，
   随后因 v2 成为历史记录。该记录本身不是发布时错代。
3. **发布时已过时的建议。** 四个重规划 episode 的第二条建议紧跟 v2 D3/D4 发布，
   仍携带 v1 的计划标识、版本、时期和租约。每项在 8 个区域形成四类错代：
   `plan_id`、`plan_version`、`epoch` 和 `lease`。

代表性顺序如下：

| cell | v1 建议序号 | v2 D4 序号 | 过时建议序号 | 过时建议绑定 |
| --- | ---: | ---: | ---: | --- |
| 100/7 | 640 | 1564 | 1565 | v1 |
| 100/17 | 842 | 1430 | 1431 | v1 |
| 200/7 | 1464 | 3032 | 3033 | v1 |
| 200/17 | 1465 | 3043 | 3044 | v1 |

四条过时建议均为规则来源的 `shadow` 输出，`formal_decision_unchanged=true`，资源守恒
违规和正式决策改写均为 0。这个事实说明控制结果未被改写，不能把错代建议改记为有效。
仅在离线聚合器中过滤全部旧计划记录也不充分，因为第二条建议在发布时已经与当前正式
计划不一致。

## 正式门影响

clean smoke 的低层 `formal_acceptance_eligible` 为 `2/6`：

- 5 对 5 两项为 true；
- 100 对 100 和 200 对 200 四项均仅因
  `d4_advice_version_evidence_issue` 为 false。

现有正式门的影响如下：

1. `scalable_3d_offline` 将建议版本错代写入 episode 失败原因，并使 clean formal
   资格失败关闭；
2. targeted posterior 的 `_low_level_gate_reasons` 要求
   `formal_acceptance_eligible=true`，受影响目标 cell 会失败；
3. full posterior 把 `formal_acceptance_eligible` 列为必需证据，并要求 900 个 cell
   全部通过；任一受影响 cell 都会使全量 verdict 为 `fail_closed`；
4. 当前计划绑定、联盟闭合和通信处置门在 6 项中均通过。建议错代是独立失败原因；
5. D2 身份切换 availability 不属于当前 formal pass 的强制零填字段，缺值保持
   unavailable，不应与本建议错代合并解释。

修复不能只放宽 D6 门。运行时应在建议发布前重新核对当前正式快照，发现计划代次变化时
取消旧快照结果，或发布带明确 superseded 状态且不可采用的诊断记录。`shadow/assist`
模式期望建议时，还需要为当前计划形成一条版本完整的建议。

## 通信处置

| 规模 | 记录 | delivered | dropped | pending | 文件验证 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 5 | 316 | 301 | 3 | 12 | 2/2 |
| 100 | 5324 | 5069 | 57 | 198 | 2/2 |
| 200 | 10461 | 9949 | 106 | 406 | 2/2 |
| 合计 | 16101 | 15319 | 166 | 616 | 6/6 |

`pending` 是 episode 结束时的显式最终处置，不补写为 delivered。49 个当前联盟目标仍全部
闭合，说明这些 pending 记录没有留下最终当前联盟成员缺口。

## 离线身份

| 规模/seed | ID Switch 可用性 | 可用值 | 部分证据下界 | 不可用原因 |
| --- | --- | ---: | ---: | --- |
| 5/7 | available | 0 | 0 | 无 |
| 5/17 | available | 0 | 0 | 无 |
| 100/7 | available | 0 | 0 | 无 |
| 100/17 | unavailable | - | 0 | `source_observation_outside_lineage_window` |
| 200/7 | unavailable | - | 2 | `multiple_truth_targets_for_global_track` |
| 200/17 | unavailable | - | 7 | `multiple_truth_targets_for_global_track` |

完整 ID Switch 指标为 `3/6 available`，可用部分合计 0。两项 200 对 200 的部分证据下界
不能替代完整指标，也不能加入可用部分合计。

## 运行性能

| 规模 | 实时倍率均值 | 实时倍率最小值 | 墙钟均值/秒 | 墙钟最大值/秒 |
| ---: | ---: | ---: | ---: | ---: |
| 5 | 5.652 | 5.385 | 0.355 | 0.371 |
| 100 | 0.347 | 0.340 | 5.771 | 5.881 |
| 200 | 0.141 | 0.139 | 14.220 | 14.416 |
| 全部 | 2.046 | 0.139 | 6.782 | 14.416 |

5 对 5 快于实时。100 对 100 和 200 对 200 未达到实时倍率 1。样本量每档仅为 2，
没有冻结主机负载，不能据此形成部署性能或置信区间结论。

## 准入条件

启动正式 900-cell 前，建议满足以下 smoke 门：

1. 同一 clean commit、相同 6-cell 范围复跑；
2. 发布时过时的 D4 建议为 0；
3. 需要建议的当前计划均有版本、时期和租约完整的建议，覆盖 `6/6`；
4. `formal_acceptance_eligible` 为 `6/6`；
5. 当前计划标识、版本、时期、租约和联盟闭合继续为 `6/6`；
6. 权威发布、计划身份和运行时确认继续守恒；
7. 在线真值使用、摘要冲突、传输引用冲突和正式决策改写继续为 0。

满足上述条件后，main 再冻结 execution plan 和 shard 布局，运行完整 900-cell。D6 应对
900 个 cell 独立执行 targeted/full posterior 门禁。本报告不构成正式 R0 结果。

## 文件摘要

- `aggregate.json`：
  `69a2bd75ccd9a033304b0bf994ebf057401d997d574912f9c997e2407dcccc99`
- `episode_summary.csv`：
  `267d74438d5a6fb70988bd4ee5d1613f1308a1350382131de8645f6c0dc6f471`
- `d6_truth_isolated_batch/truth_isolated_aggregate.json`：
  `28aab6a1e192f7101d1ae1a13d4a6ad6a24721e8377efa7177e21e236db67f8f`
- D6 独立重算 `scalable_3d_offline_aggregate.json`：
  `8f3bfe2247003fcbcbafec45fd919b4e6a7dee0ee402771b690e6f43f6bbed05`
- D6 独立重算 `scalable_3d_offline_per_episode_seed.csv`：
  `f218062e129ecdf34e4ecc367393f48c758ed8b82ff06d7587238bda5378f443`

## 验证边界

本轮没有修改 D6 算法代码，也没有修改 main/runtime 或 D1-D5/D7。专项测试和文档格式
检查结果如下：

- 6-cell 独立重算断言：通过；
- `test_formal_r0_plan_binding_audit.py`、
  `test_formal_r0_targeted_posterior_audit.py`、
  `test_formal_r0_full_posterior_audit.py` 和 `test_scalable_3d_offline.py`：
  `95 passed, 1 warning in 9.43s`；
- warning 为既有 Matplotlib `Axes3D` 环境提示，不影响 JSONL、哈希、计划绑定或建议
  代次审计。
