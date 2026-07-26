# D1 在线发布证据子集快照 Clean Smoke

## 结论

2026-07-25 在 detached clean commit
`028ac34debcfc5ca6ed2f6f88a5868d7b5f0f67b` 上完成一对 200/200/2 三维质点
episode。reference 和 candidate 均为 fresh 输出，唯一运行时差异是
`d1_publication_evidence_snapshot_implementation`。

业务语义、最终一致性证据和原 D1 操作计数一致。candidate 14 次选择全部走子集快照，
fallback、lookup miss、非法 ID 和空 required 集合均为 0。返回记录由 reference 的
`13679` 条降至 `4429` 条，减少 `67.621902%`。该结果允许进入新矩阵预注册，不构成
多 seed 性能准入。

## 输入

| 项目 | 值 |
| --- | --- |
| 仿真模式 | 三维质点 |
| 目标/资源/侦察节点 | 200 / 200 / 2 |
| seed | 1151 |
| 仿真时长 | 2.2 秒 |
| 在线观测 | 2028 |
| replay-prefix selector | `per_checkpoint_prefix_rebuild_v1`（两臂相同） |
| reference | `full_consistency_snapshot_v1` |
| candidate | `required_observation_subset_v1` |
| 原始证据目录 | `/tmp/msm_d1_publication_evidence_smoke_028ac34/` |

两条命令均从 `/tmp/msm-publication-evidence-clean-028ac34` 执行：

```bash
python3 research_modules/scalable_3d_simulation/run_episode.py \
  --integrated-stack --drone-count 200 --target-count 200 \
  --recon-count 2 --duration 2.2 --seed 1151 \
  --d1-publication-evidence-snapshot-implementation \
  full_consistency_snapshot_v1 \
  --output /tmp/msm_d1_publication_evidence_smoke_028ac34/reference
```

```bash
python3 research_modules/scalable_3d_simulation/run_episode.py \
  --integrated-stack --drone-count 200 --target-count 200 \
  --recon-count 2 --duration 2.2 --seed 1151 \
  --d1-publication-evidence-snapshot-implementation \
  required_observation_subset_v1 \
  --output /tmp/msm_d1_publication_evidence_smoke_028ac34/candidate
```

## 语义核验

| 核验项 | 结果 |
| --- | --- |
| `finite_state` | 两臂均为 `true` |
| `online_truth_use_count` | 两臂均为 0 |
| D1 在线记录 SHA-256 | 两臂均为 `d89c17baa598f9fd58f95013a3e5bdb077f7e82f66cfbcdde6920669ade56bbc` |
| D2 在线记录 SHA-256 | 两臂均为 `0e75586d2b195db1fa3b6a3591a3b06d761e55e9b34892cbda5f87a57dbb4f43` |
| consistency record count | 两臂均为 2028 |
| consistency records digest | 两臂均为 `sha256:b579e62b65169791a1c9526eb5310ba7016149ddd501efe34e82a732c8bbda3a` |
| 原 D1 fusion operation counts | 完全一致 |
| 最终 candidate fallback | 0 |
| 最终 candidate lookup miss | 0 |
| 最终 candidate invalid/empty required | 0 / 0 |

reference/candidate 的 episode ID 和 runtime profile SHA 不同，这是 selector 进入 manifest
哈希后的预期结果。比较时未删除业务记录，也未使用在线真值。

## 工作量

| 指标 | Reference | Candidate |
| --- | ---: | ---: |
| selection count | 14 | 14 |
| publication count | 86 | 86 |
| full snapshot call | 14 | 0 |
| subset snapshot call | 0 | 14 |
| subset success | 0 | 14 |
| source observation reference | 未在默认路径额外扫描 | 2028 |
| track latest-observation reference | 未在默认路径额外扫描 | 11010 |
| required ID | 未在默认路径额外扫描 | 4429 |
| duplicate reference | 未在默认路径额外扫描 | 8609 |
| returned record | 13679 | 4429 |

默认 reference 不构造 required ID 集合，避免默认关闭候选给现有路径增加线性扫描。候选承担
ID 收集、去重和排序开销，正式 A/B 将这一成本计入 candidate。

## 性能观察

| 指标 | Reference | Candidate | Candidate 改善 |
| --- | ---: | ---: | ---: |
| episode `wall_time_s` | 8.309393 | 8.313443 | -0.048740% |
| 外部命令耗时 | 16.11 秒 | 15.31 秒 | 4.965860% |
| D1 fusion 累计墙钟 | 2.299589 秒 | 2.373660 秒 | -3.221037% |
| module stack 累计墙钟 | 6.156322 秒 | 6.064366 秒 | 1.493688% |
| 最大驻留内存 | 872736 KiB | 867296 KiB | 0.623322% |
| 实时因子 | 0.264761 | 0.264632 | 未达到 1 |

单 pair 的 D1、module stack、episode 和外部命令计时方向不一致。该差异可能包含缓存、
调度和后处理波动，不能据此晋升或拒绝 candidate。正式判断需要 balanced arm order 的
short/long 多 seed 矩阵、配对置信区间和 D6 独立评估。

## 边界

本次 smoke 仅覆盖三维质点仿真。它不证明系统实时，不覆盖 AirSim、冻结目标处理器、硬件、
实机或实飞。后续矩阵必须使用新的 matrix/evidence/evaluator schema，不得复用或覆盖
回放前缀摘要候选的正式 `reject` 证据。

后续 13 对正式矩阵已经完成，D6 判定为 `reject`。正式结果见
`D1_PUBLICATION_EVIDENCE_SNAPSHOT_FORMAL_EVALUATION_20260725_CN.md`；本文件继续保留为
矩阵预注册前的单 pair 证据，不追溯改写其观察值。
