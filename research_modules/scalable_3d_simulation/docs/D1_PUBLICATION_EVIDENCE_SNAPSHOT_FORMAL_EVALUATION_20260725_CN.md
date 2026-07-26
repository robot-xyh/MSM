# D1 在线发布证据子集快照正式评估

## 结论

`required_observation_subset_v1` 未通过正式准入，默认继续使用
`full_consistency_snapshot_v1`。候选显著减少了在线发布阶段返回的证据对象，但短时
200 对 200 场景没有形成稳定的 D1 融合耗时收益。

D6 正式 verdict 为 `reject`，`main_default_promotion_allowed=false`。冻结矩阵、门限和
原始判定不得因后续调优而改写。

## 证据范围

| 项目 | 值 |
| --- | --- |
| 仿真模式 | 三维质点 |
| 目标/资源/侦察节点 | 200 / 200 / 2 |
| short | seeds 1151-1160，2.2 秒 |
| long | seeds 1151-1153，10 秒 |
| episode | 13 对 / 26 个 fresh arm |
| reused / failed | 0 / 0 |
| producer clean commit | `d0219eb14c529a4fb9bf7d6610a9f32055a09206` |
| matrix SHA-256 | `6c808c4df8759fd893c6d37ff9dce4a1efa07f9867fc71aff47a55c5f8517338` |

两臂唯一差异是 `d1_publication_evidence_snapshot_implementation`。回放前缀均保持
`per_checkpoint_prefix_rebuild_v1`，没有把此前正式拒绝的回放摘要候选混入本次比较。

## 语义与工作量

D6 独立确认 13/13 对业务语义、有限状态、在线真值隔离、实现身份、D1/D2 在线记录、
一致性证据记录数量与摘要、原 D1 融合操作计数和四表面诊断审计通过。

候选 429/429 次选择成功使用子集快照。fallback、lookup miss、非法 required ID 和空集合
均为 0。累计返回记录由 `1602170` 降至 `133917`，削减 `91.641524%`。episode 最终
离线一致性证据仍为全量精确导出。

## 性能

| 指标 | short | long | 门限 |
| --- | ---: | ---: | ---: |
| candidate faster | 4/10 | 2/3 | >=8/10，>=2/3 |
| D1 fusion 改善 | -0.147877% | 1.047143% | >=1% |
| core wall 改善 | 0.330057% | 0.837777% | >=0.25% |
| short bootstrap 上界 | 1.374681% | 不作为失败门 | <=0% |

正式失败门为 short candidate faster、short D1 fusion improvement 和 short bootstrap
upper bound。D2 与驻留内存守门均通过，返回记录削减门也通过。这说明子集读取在长时累计
工作量较大时有收益，但短时路径中的 required ID 收集、去重和 Python 对象处理抵消了
证据读取减少量。

候选最低实时因子为 `0.203423 < 1`。实时门独立失败，不参与本次局部优化 verdict。

## 集成决策

1. main 和 D1 保持 `full_consistency_snapshot_v1` 为默认。
2. candidate 保留为默认关闭的研究入口，用于后续分析批量索引或更粗粒度发布数据结构。
3. 不再对本候选调低门限或删除 seed；后续新方案必须使用新的实现标识、矩阵和 D6 判定。
4. 本结果只覆盖三维质点仿真，不外推到 AirSim、冻结目标处理器、硬件、实机或实飞。

正式 D6 bundle 位于：

`research_modules/d6_evaluation_metrics/outputs/`
`d1_publication_evidence_snapshot_multiseed_20260725_formal_d0219eb_d6/`
