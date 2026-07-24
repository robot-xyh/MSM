# 身份承诺执行门单种子审计

## 审计结论

2026-07-23，D6 对提交
`7e15dac9cdaf6743999dfe045a70676fd31a17d6` 生成的两组 clean 制品完成只读复核。
两组均为 nominal 200 对 200、2 个侦察节点、2.2 秒、seed 1100，root manifest 均声明
`repository_dirty=false`。场景配置、离线真值状态和离线观测真值标签逐字节相同。
运行配置只在
`d1_identity_neutral_centroid_correction_enabled` 一项上不同。

身份承诺执行门通过本轮安全合同检查。D3 在 `t=1.0 s` 将计划从版本 1 强制升为版本 2，
绕过迟滞并撤销 11 个未承诺目标的既有绑定。此后 D3 分配、D5 主动视觉命令、D5 终端绑定、
D7 导引命令和 main 运行时控制确认中，这 11 个目标的继续执行次数均为 0。

质心候选没有形成有效处理量。候选组发现 46 个候选分量，30 个因 `oosm_scan` 被拒绝，
16 个因 `unbalanced_component` 被拒绝，实际应用数为 0。两组身份、连续率和计划结果完全
相同。本轮只能证明启用候选后仍保持失败关闭和执行门安全，不能证明质心修正改善或损害了
关联算法。

## 证据范围

| 项目 | hold_only | hold_plus_centroid |
| --- | --- | --- |
| episode ID 后缀 | `reb1e534686bc` | `rc40e387dfa42` |
| runtime profile SHA-256 | `eb1e534686bc...` | `c40e387dfa42...` |
| 资源/目标/侦察节点 | 200/200/2 | 200/200/2 |
| seed/时长 | 1100/2.2 s | 1100/2.2 s |
| repository dirty | false | false |
| 在线真值使用 | 0 | 0 |
| 质心候选/应用/拒绝 | disabled/unavailable | 46/0/46 |

两组 scenario config、`offline_truth_state.npz` 和
`offline_identity/observation_truth_labels.jsonl` 的文件比较结果均为相同。runtime profile
规范化差异只有质心候选开关。这满足同输入安全合同 A/B 的配置要求。

审计消费以下制品：

1. root `manifest.json` 与 `summary.json`；
2. `offline_identity/identity_evaluation.json`、identity evidence 和 manifest v2；
3. `d6_truth_isolated/episode_record.json`、逐 seed CSV、聚合 JSON 和中文报告；
4. `d6_runtime_plan_outcomes/runtime_plan_outcome_join.json` 与输入哈希清单；
5. `online_observations.jsonl` 中的 D2、D3、D5、D7 和 main runtime 发布。

## 身份指标

两组结果完全一致。

| 指标 | 数值 | 可用性 |
| --- | ---: | --- |
| 严格身份交换次数 | 3 | available |
| 航迹连续率 | 0.8266666667 | available |
| 覆盖连续率 | 0.8283333333 | available |
| 重复分配次数 | 0 | available |
| available mapping | 1491 | available |
| unavailable mapping | 218 | available |
| uncommitted mapping | 76 | available |
| excluded mapping | 2 | available |
| 承诺覆盖率 | 0.9574706212 | available |
| 未承诺来源绑定违规 | 0 | available |
| 未承诺候选绑定违规 | 0 | available |

1787 条承诺记录由 1711 条 `committed`、69 条
`identity_uncommitted_ambiguity_hold` 和 7 条
`identity_uncommitted_after_hold` 组成。状态计数与覆盖率满足

```text
commitment coverage = 1711 / 1787 = 0.9574706212
```

映射分类还包含 2 条 excluded 记录。`1491/218/76` 分别表示 available、普通 unavailable
和 uncommitted，不能省略 excluded 后直接解释为完整分母。

D6 重新构造 truth-isolated episode record，结果与随 episode 持久化的 JSON 完全相同。
重新生成的逐 seed CSV、D1 距离分组 CSV、聚合 JSON 和中文报告均逐字节相同。strict IDSW
由隔离真值侧车和 D2 identity evaluation 提供，没有用 partial lower bound 或 commitment
coverage 回填。

## 计划升版

`t=0.75 s` 的 D3 计划版本为 1，包含 193 个分配。`t=1.0 s` 的 D2 发布中有 11 个航迹处于
未承诺歧义保活状态：

```text
GT3D-000034  GT3D-000035  GT3D-000057  GT3D-000058
GT3D-000060  GT3D-000079  GT3D-000080  GT3D-000112
GT3D-000113  GT3D-000185  GT3D-000186
```

同一时刻 D3 发布版本 2。计划元数据给出：

```text
identity_commitment_forced_replan = true
identity_commitment_hysteresis_bypassed = true
identity_commitment_noncommitted_rejected_count = 11
identity_commitment_replan_reason = previous_target_identity_uncommitted
replan_response_state = replan_applied
```

版本 2 包含 186 个分配，11 个未承诺目标均不在分配中。全量滚动重算同时发生其他目标退出和
新航迹加入，因此计划总数变化不能简单解释为 `193-11`。身份专项判定只使用 D3 明确发布的
11 个 previous binding/rejected target ID，并逐个核对新计划。

`t=2.0 s` 的版本 3 仍有 186 个分配，上述 11 个目标继续保持无分配。两臂的计划版本、计数和
阻断目标集合一致。

## 下游执行

以 `t=1.0 s` 的 11 个未承诺目标为冻结集合，逐条扫描后续在线发布，结果如下。

| 检查项 | hold_only | hold_plus_centroid |
| --- | ---: | ---: |
| D3 版本 2 对冻结目标的分配 | 0 | 0 |
| D3 版本 3 对冻结目标的分配 | 0 | 0 |
| D5 主动视觉对冻结目标的命令 | 0 | 0 |
| D5 终端绑定到冻结目标 | 0 | 0 |
| D7 对冻结目标的导引命令 | 0 | 0 |
| runtime ACK 对冻结目标的绑定 | 0 | 0 |
| runtime ACK 对冻结目标施加控制 | 0 | 0 |

两组 runtime plan outcome 均包含 3 个有效计划确认和 565 个绑定窗口，在线真值使用为 0，
来源序列和 payload SHA 验证通过。审计结果为 `passed=true`、`violation_count=0`。
当前 D6 代码从原哈希输入清单重新生成 runtime outcome JSON 后，与原文件逐字节相同。

## 候选处理量

控制组关闭质心修正。候选组开启实验开关，运行时诊断为：

```text
candidate component count = 46
applied component count = 0
rejected component count = 46
rejection reasons = oosm_scan: 30, unbalanced_component: 16
status = experimental_identity_neutral_centroid_candidate_not_promoted
```

因此处理组实际接受的修正数为 0。两臂严格 IDSW、连续率、映射分类、承诺状态、D3 计划和
下游命令一致是预期结果，不能被写成候选算法的零效应估计。当前数据也不能用于非劣效检验、
置信区间或晋级判断。

## 来源哈希

| 制品 | hold_only | hold_plus_centroid |
| --- | --- | --- |
| root manifest | `4652493af630...` | `a5e4c7669da1...` |
| summary | `64fcead03119...` | `b61f02ad114f...` |
| online observations | `d55e85656695...` | `380b52eaa048...` |
| identity evaluation | `967ae1ce9b4d...` | `6e007353c376...` |
| identity manifest | `3c1f89291c5d...` | `d57fc0708cd5...` |
| D6 episode record | `43c122a4cc28...` | `a2d20c637ec1...` |
| D6 runtime outcome | `61fded2a04f6...` | `6e7edd0aa98b...` |

identity manifest 均为 `scalable3d-offline-identity-evaluation-manifest-v2`。两组恢复配置
规范 SHA-256 均为
`bd8e362ec4ca128ed902826750b26d862286770d3c0c4d0b75960a50911a201a`，
配置记录数、D2 记录数和在线 D2 发布数均为 9。episode 和 runtime 两条 D6 链均报告
配置一致、在线文件已验证和 provenance 已验证。

## 证据边界

本轮已确认：

1. clean 单 seed 制品来源可复核；
2. 未承诺目标会触发严格升版和旧绑定撤销；
3. D3、D5、D7 与运行时控制不会继续处理这 11 个目标；
4. truth-isolated 和 runtime-plan-outcome 制品可由当前 D6 代码确定性重建；
5. 候选组在无合法处理量时保持失败关闭。

本轮没有确认：

1. 质心修正的算法收益或非劣性；
2. 多 seed、长时、困难谱系或 AirSim 性能；
3. 候选被实际应用后的连续率、IDSW 和下游计划影响；
4. 200 对 200 工程实时性或物理拦截效果。

## 开放项

1. 生成至少一组 `applied component count > 0` 的同输入 A/B，再评估 IDSW、连续率、D2
   航迹可用性、D3 分配可用性和安全门非退化。
2. 单 seed 处理量门通过后，再执行冻结的多 seed、长时和困难谱系矩阵，并报告置信区间。
3. 将本次按 online observations 复算的 D3/D5/D7 未承诺继续执行计数纳入 D6 标准派生
   JSON/CSV，而不是长期依赖专项只读脚本。
4. 通用 scalable 3D 汇总仍读取在线 summary 的 IDSW availability；专项 truth-isolated
   严格 IDSW 位于独立制品。后续统一报告应做显式联接并保留来源层级，禁止覆盖在线字段。

当前无 D6-owned P0。以上为 P1 评估自动化和正式证据缺口。
