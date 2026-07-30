# 正式 R0 全量后验独立审计

评估日期：2026-07-30

## 结论

审计结论为 **fail_closed**。D6 逐项复算 900/900 个正式 R0 episode，通过 872/900。
来源提交为 `1e5ed8ddcf27f375e922a447decfbd875d21bfdf`，执行计划逻辑摘要为 `8804ecb4dd0513db55906905f031832711012974fc911546df40e09fb297d373`。
该结论只覆盖单臂 R0 的 900 项。完整父矩阵仍为 900/5700，G1、A1、A2、A3 尚无同范围对照，不能给出因果收益结论。

## 审计方法

1. 重新计算执行计划文件摘要和逻辑摘要，核对 clean source 提交。
2. 独立核对 20 个 shard plan、checkpoint、progress 和 900 个 cell result。
3. 将 merged scope 的 manifest、episode index 和 CSV 仅作为待复核索引，逐项核对其 SHA-256、路径和身份。
4. 逐 episode 重算 artifact tree，并从在线观测总线和 summary 重新评估真值隔离、有限状态、clean formal 和实验矩阵资格。
5. 重算 D1 发布代次、D2 消费代次、节拍前合并、末尾跳过、pending 和 generation integrity。缺值不补零，矛盾项失败关闭。

未读取 `merged_scope/d6_evaluation`、旧 `targeted_formal_d6` 或 episode 内 producer 生成的 `observation_governance_audit.json`。

## 范围完整性

| 项目 | 结果 |
| --- | ---: |
| 正式 R0 scope | 900/900 |
| 通过 | 872/900 |
| clean formal | 900/900 |
| 实验矩阵资格 | 900/900 |
| generation verified | 900/900 |
| 20 分片哈希通过 | 20/20 |

## 后验守恒

| 指标 | 可用项 | 总量 | 零值项 | 非零项 |
| --- | ---: | ---: | ---: | ---: |
| D2 末尾跳过 | 900/900 | 0 | 900 | 0 |
| D2 身份交换 | 0/900 | 不可用 | 0 | 0 |

D2 pending 证据可用 900/900，排空 900/900。

## 安全计数

| 指标 | 可用项 | 总量 | 零计数通过 |
| --- | ---: | ---: | --- |
| `online_truth_use_count` | 900/900 | 0 | 是 |
| `online_truth_field_violation_count` | 900/900 | 0 | 是 |
| `d4_advice_resource_quota_conservation_violation_count` | 700/900 | 不可用 | 不可用 |
| `d4_advice_formal_decision_mutation_count` | 700/900 | 不可用 | 不可用 |
| `d5_active_vision_target_reference_violation_count` | 700/900 | 不可用 | 不可用 |
| `d5_active_vision_ack_target_mismatch_count` | 700/900 | 不可用 | 不可用 |

## 场景结果

| 场景 | cell | 通过 | clean formal | generation verified | skip 总量 |
| --- | ---: | ---: | ---: | ---: | ---: |
| center_failure | 100 | 100 | 100 | 100 | 0 |
| communication_degraded | 100 | 100 | 100 | 100 | 0 |
| delayed_noisy | 100 | 100 | 100 | 100 | 0 |
| dense_crossing | 100 | 100 | 100 | 100 | 0 |
| evasive_multilevel | 100 | 100 | 100 | 100 | 0 |
| formation_split | 100 | 100 | 100 | 100 | 0 |
| high_threat_m_to_n | 100 | 72 | 100 | 100 | 0 |
| nominal | 100 | 100 | 100 | 100 | 0 |
| secondary_failure | 100 | 100 | 100 | 100 | 0 |

## 规模结果

| 规模 | cell | 通过 | clean formal | generation verified | skip 总量 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 5 | 180 | 175 | 180 | 180 | 0 |
| 20 | 180 | 176 | 180 | 180 | 0 |
| 50 | 180 | 175 | 180 | 180 | 0 |
| 100 | 180 | 174 | 180 | 180 | 0 |
| 200 | 180 | 172 | 180 | 180 | 0 |

## Seed 结果

| Seed | cell | 通过 | clean formal | generation verified |
| ---: | ---: | ---: | ---: | ---: |
| 1000 | 45 | 44 | 45 | 45 |
| 1001 | 45 | 45 | 45 | 45 |
| 1002 | 45 | 43 | 45 | 45 |
| 1003 | 45 | 43 | 45 | 45 |
| 1004 | 45 | 44 | 45 | 45 |
| 1005 | 45 | 45 | 45 | 45 |
| 1006 | 45 | 42 | 45 | 45 |
| 1007 | 45 | 44 | 45 | 45 |
| 1008 | 45 | 44 | 45 | 45 |
| 1009 | 45 | 44 | 45 | 45 |
| 1010 | 45 | 44 | 45 | 45 |
| 1011 | 45 | 45 | 45 | 45 |
| 1012 | 45 | 43 | 45 | 45 |
| 1013 | 45 | 44 | 45 | 45 |
| 1014 | 45 | 43 | 45 | 45 |
| 1015 | 45 | 41 | 45 | 45 |
| 1016 | 45 | 44 | 45 | 45 |
| 1017 | 45 | 41 | 45 | 45 |
| 1018 | 45 | 44 | 45 | 45 |
| 1019 | 45 | 45 | 45 | 45 |

## 失败项

| cell | 场景 | 规模 | seed | 原因 |
| --- | --- | ---: | ---: | --- |
| 00802__r0__high_threat_m_to_n__5v5__seed_1002 | high_threat_m_to_n | 5 | 1002 | `["d6_low_level:d4_fail_closed:collecting_member_acks"]` |
| 00806__r0__high_threat_m_to_n__5v5__seed_1006 | high_threat_m_to_n | 5 | 1006 | `["d6_low_level:d4_fail_closed:collecting_member_acks"]` |
| 00809__r0__high_threat_m_to_n__5v5__seed_1009 | high_threat_m_to_n | 5 | 1009 | `["d6_low_level:d4_fail_closed:collecting_member_acks"]` |
| 00815__r0__high_threat_m_to_n__5v5__seed_1015 | high_threat_m_to_n | 5 | 1015 | `["d6_low_level:d4_fail_closed:collecting_member_acks"]` |
| 00817__r0__high_threat_m_to_n__5v5__seed_1017 | high_threat_m_to_n | 5 | 1017 | `["d6_low_level:d4_fail_closed:collecting_member_acks"]` |
| 00826__r0__high_threat_m_to_n__20v20__seed_1006 | high_threat_m_to_n | 20 | 1006 | `["d6_low_level:d4_fail_closed:collecting_member_acks"]` |
| 00827__r0__high_threat_m_to_n__20v20__seed_1007 | high_threat_m_to_n | 20 | 1007 | `["d6_low_level:d4_fail_closed:collecting_member_acks"]` |
| 00834__r0__high_threat_m_to_n__20v20__seed_1014 | high_threat_m_to_n | 20 | 1014 | `["d6_low_level:d4_fail_closed:collecting_member_acks"]` |
| 00838__r0__high_threat_m_to_n__20v20__seed_1018 | high_threat_m_to_n | 20 | 1018 | `["d6_low_level:d4_fail_closed:collecting_member_acks"]` |
| 00842__r0__high_threat_m_to_n__50v50__seed_1002 | high_threat_m_to_n | 50 | 1002 | `["d6_low_level:d4_fail_closed:collecting_member_acks"]` |
| 00843__r0__high_threat_m_to_n__50v50__seed_1003 | high_threat_m_to_n | 50 | 1003 | `["d6_low_level:d4_fail_closed:collecting_member_acks"]` |
| 00848__r0__high_threat_m_to_n__50v50__seed_1008 | high_threat_m_to_n | 50 | 1008 | `["d6_low_level:d4_fail_closed:collecting_member_acks"]` |
| 00855__r0__high_threat_m_to_n__50v50__seed_1015 | high_threat_m_to_n | 50 | 1015 | `["d6_low_level:d4_fail_closed:collecting_member_acks"]` |
| 00857__r0__high_threat_m_to_n__50v50__seed_1017 | high_threat_m_to_n | 50 | 1017 | `["d6_low_level:d4_fail_closed:collecting_member_acks"]` |
| 00863__r0__high_threat_m_to_n__100v100__seed_1003 | high_threat_m_to_n | 100 | 1003 | `["d6_low_level:d4_fail_closed:collecting_member_acks"]` |
| 00870__r0__high_threat_m_to_n__100v100__seed_1010 | high_threat_m_to_n | 100 | 1010 | `["d6_low_level:d4_fail_closed:collecting_member_acks"]` |
| 00872__r0__high_threat_m_to_n__100v100__seed_1012 | high_threat_m_to_n | 100 | 1012 | `["d6_low_level:d4_fail_closed:collecting_member_acks"]` |
| 00873__r0__high_threat_m_to_n__100v100__seed_1013 | high_threat_m_to_n | 100 | 1013 | `["d6_low_level:d4_fail_closed:collecting_member_acks"]` |
| 00875__r0__high_threat_m_to_n__100v100__seed_1015 | high_threat_m_to_n | 100 | 1015 | `["d6_low_level:d4_fail_closed:collecting_member_acks"]` |
| 00877__r0__high_threat_m_to_n__100v100__seed_1017 | high_threat_m_to_n | 100 | 1017 | `["d6_low_level:d4_fail_closed:collecting_member_acks"]` |
| 00880__r0__high_threat_m_to_n__200v200__seed_1000 | high_threat_m_to_n | 200 | 1000 | `["d6_low_level:d4_fail_closed:collecting_member_acks"]` |
| 00884__r0__high_threat_m_to_n__200v200__seed_1004 | high_threat_m_to_n | 200 | 1004 | `["d6_low_level:d4_fail_closed:collecting_member_acks"]` |
| 00886__r0__high_threat_m_to_n__200v200__seed_1006 | high_threat_m_to_n | 200 | 1006 | `["d6_low_level:d4_fail_closed:collecting_member_acks"]` |
| 00892__r0__high_threat_m_to_n__200v200__seed_1012 | high_threat_m_to_n | 200 | 1012 | `["d6_low_level:d4_fail_closed:collecting_member_acks"]` |
| 00894__r0__high_threat_m_to_n__200v200__seed_1014 | high_threat_m_to_n | 200 | 1014 | `["d6_low_level:d4_fail_closed:collecting_member_acks"]` |
| 00895__r0__high_threat_m_to_n__200v200__seed_1015 | high_threat_m_to_n | 200 | 1015 | `["d6_low_level:d4_fail_closed:collecting_member_acks"]` |
| 00896__r0__high_threat_m_to_n__200v200__seed_1016 | high_threat_m_to_n | 200 | 1016 | `["d6_low_level:d4_fail_closed:collecting_member_acks"]` |
| 00897__r0__high_threat_m_to_n__200v200__seed_1017 | high_threat_m_to_n | 200 | 1017 | `["d6_low_level:d4_fail_closed:collecting_member_acks"]` |

## 失败原因汇总

- `d6_low_level:d4_fail_closed:collecting_member_acks`

## 证据边界

- 900/900 表示 clean source `1e5ed8d` 的正式 R0 单臂已完成并由 D6 逐项复核。
- 旧 source 的 895/900 结果没有与本批次拼接。
- 身份交换等依赖离线真值配对的指标若不可用，保留 `null` 和不可用原因，不写成 0。
- 完整 5700-cell 父矩阵尚未完成，学习变体也未形成同范围结果。
- 本报告不能用于声明 G1、A1、A2、A3 的收益、因果改进或生产准入。
