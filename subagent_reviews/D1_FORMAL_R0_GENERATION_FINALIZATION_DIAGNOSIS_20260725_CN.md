# D1 正式 R0 代次收尾诊断

**日期**：2026-07-25

**正式来源提交**：`2c7b425d076899e1c54a3d87d6ef23a613ba6e3a`

**范围**：正式 R0 的 900 个 episode，重点复核 5 个 `delayed_noisy` 非 clean-formal episode

**边界**：本报告只诊断 D1 发布、乱序量测回放和 episode 尾部释放，不修改 main、D2 或 D6

## 结论

五个失败 episode 没有发现 D1 漏发、重复代次或尾部扫描丢失。D1 完整后验代次均从 1 连续递增
到最终值，完整后验数与 D1 物化快照数相等，完整后验与 state-only 扫描数之和等于全部释放
扫描数。扫描输入关闭后缓冲为 0，接收数与释放数相等，拒绝数为 0。

后续跨模块复核确认，五个最终批次虽然均为 1 条未接受视觉观测且
`accepted_observation_count=0`，最终完整后验的状态、协方差或状态有效时刻仍发生变化。原
`finalize_unchanged_posterior_skip` 使用的来源观测简化签名不能证明 D2 可见完整输入等价，
因此不能作为合法 no-op 的正式证据。

main 已取消 finalize 的相同来源签名跳过，最终 pending D1 后验必须实际进入 D2；消费失败时
先报错，不能清空 pending。D2 使用 replay-coast 隔离已经处理过的来源观测，不增加重复 hit、
不重复建轨，也不刷新原始来源证据时钟。五个原失败 cell 的开发态定向重放现已全部通过 D6
generation contract：D1 最终代次等于 D2 实际消费代次，skip 为 0，pending 为空。

当前状态为：**D1 本身从未漏发；跨模块 P0 已完成代码修复和五项定向回归，formal acceptance
仍待新 clean commit 下完整 900-cell R0 正式重跑。**

## 原正式证据

main 对 900 个 `summary.json` 的独立统计为：

- `d2_finalize_unchanged_posterior_skip_count` 分布：`0: 895`，`1: 5`；
- 旧守恒式
  `D2 consumption + pre-tick merge = D1 full posterior generation`
  恰好失败 5 项；
- 加入 finalize unchanged skip 后，扩展计数式在 `900/900` episode 成立；
- 五个失败项的 pending generation 均为空，skip 均为 1。

五个 episode 的逐项数据如下。

| 场景 | Seed | D1 最终代次 | D1 完整/State-only/释放 | D2 已消费代次 | D2 消费 | Tick 前合并 | Final no-op | 扩展守恒 | 最终批接受/未接受 |
| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | --- | --- |
| delayed_noisy 5v5 | 1000 | 13 | 13/11/24 | 11 | 5 | 7 | 1 | 13=13 | 0/1 |
| delayed_noisy 5v5 | 1005 | 9 | 9/3/12 | 7 | 4 | 4 | 1 | 9=9 | 0/1 |
| delayed_noisy 5v5 | 1008 | 13 | 13/9/22 | 10 | 4 | 8 | 1 | 13=13 | 0/1 |
| delayed_noisy 5v5 | 1018 | 14 | 14/6/20 | 11 | 5 | 8 | 1 | 14=14 | 0/1 |
| delayed_noisy 20v20 | 1009 | 27 | 27/23/50 | 17 | 6 | 20 | 1 | 27=27 | 0/1 |

五项还满足：

1. 完整后验中的 `posterior_generation` 均严格等于 `1..G`，没有缺号和重复；
2. `d1_materialized_snapshot_count=G`；
3. `d1_materialized_snapshot_count + d1_state_only_scan_count =
   d1_scan_input.released_scan_count`；
4. `received_scan_count=released_scan_count`，`rejected_scan_count=0`；
5. `current_buffered_scan_count=0`，`d1_scan_input.closed=true`；
6. 双时间戳、六维 NED 状态和 `6x6` 协方差仍由完整后验携带，在线真值没有进入 D1。

## 修复后定向证据

main 在当前开发工作树使用原正式构造参数重放以下五个 cell：

| 场景 | Seed | D6 generation contract | D1 final 与 D2 consumed | Final skip | Pending |
| --- | ---: | --- | --- | ---: | --- |
| delayed_noisy 5v5 | 1000 | verified | 相等 | 0 | 空 |
| delayed_noisy 5v5 | 1005 | verified | 相等 | 0 | 空 |
| delayed_noisy 5v5 | 1008 | verified | 相等 | 0 | 空 |
| delayed_noisy 5v5 | 1018 | verified | 相等 | 0 | 空 |
| delayed_noisy 20v20 | 1009 | verified | 相等 | 0 | 空 |

定向测试还确认最终 D2 处理属于 replay-coast：新鲜检测数为 0，隔离的重复来源检测数和
coast 数均大于 0，没有按重复检测新建航迹，重复合并计数为 0，`global_track_id` 仍由中心
D2 所有。该结果证明原五项运行时断点已被修复，不代表 900 个 cell 的 clean-formal 矩阵已经
重新生成。

## 代码边界

D1 模块不分配 main runtime 的 `posterior_generation`。D1 的职责是：

1. `ScanInputOrganizer.close()` 按量测时间顺序释放仍有效的有限尾部；
2. `process_scan_batch(..., materialize_tracks=False)` 完成逐扫描状态更新和审计；
3. 每个融合时刻的最后一次调用生成完整 `FusionBatchResult`，或由调用方显式调用
   `materialize_global_tracks()`；
4. OOSM 按固定滞后历史重放，继续保留 `measurement_timestamp`、`arrival_timestamp`
   和协方差。

main 在完整快照出现时递增 `_d1_posterior_generation`。同一 D2 调度周期内若已有待消费后验，
main 增加 pre-tick merge 计数并保留最新代次。episode 收尾调用 D2 时，
现在直接调用 D2 消费最终后验，不再传入 `skip_unchanged_posterior=True`。若 D2 未成功处理，
finalize 抛出异常并保留失败可见性；只有实际处理成功后才清空 pending generation。

该修复没有改变 D1 的发布、OOSM、时间戳、协方差、真值隔离或航迹编号语义。D1 不需要把相同
来源观测伪装成新证据；重复来源证据治理位于 D2 replay-coast。

## 原 no-op 判定复核

旧扩展式
`consumption + pre_tick_merge + finalize_unchanged_skip = D1 generation`
在 `900/900` 上成立，只证明每个 D1 generation 都被某个运行时分支计数。它不能证明被 skip 的
完整后验与上次 D2 输入等价。

`accepted_observation_count=0` 也不能建立等价性。状态传播、延迟量测回放和协方差传播可以在
最新来源观测标识不变时改变 D2 输入。原五项的 no-op 候选因此被否决。当前修复选择实际消费
最终后验，并由 D2 replay-coast 处理来源重复；不再依赖扩展式放宽 D6 正式门。

## 修复结果与剩余验收

已完成：

1. main finalize 不再按相同来源简化签名跳过最终 D1 后验；
2. 未实际处理最终 pending 后验时失败关闭，不能静默清空 pending；
3. D2 replay-coast 隔离重复来源观测，不重复增加 hit、建轨或刷新来源证据；
4. 五个原失败 cell 定向回归全部满足 D1 final 等于 D2 consumed、skip 为 0、pending 为空；
5. D6 对五项的 generation contract 均给出 `verified`。

仍需 main、D2 和 D6 完成：

1. 将当前修复固化为新的 clean source commit；
2. 在该提交上重新运行完整 900-cell R0，不复用或原地改写 `2c7b425` 的旧制品；
3. 由 D6 重新聚合 900 项 generation、pending、在线真值隔离和业务指标，确认没有新增失败；
4. 只有完整矩阵满足冻结验收口径后，才能把 formal acceptance 标记为关闭。

## D1 验证

D1 不需要修改融合算法、扫描输入、双时间戳、协方差、真值隔离或发布接口。2026-07-25
使用当前工作树运行 D1 全量回归，结果为 `496 passed in 35.26s`；D1 全部 Python 文件
`py_compile` 通过。

README、PLAN、`docs/MODULE_PRINCIPLES_CN.md`、`docs/ALGORITHM_AND_IMPLEMENTATION.md`、
`docs/AIRSIM_INTEGRATION_PLAN.md` 和 `docs/EXPERIMENT_REPORT.md` 已逐项检查。本次变化只更新
跨模块 P0 的处置状态，没有改变 D1 能力、接口、默认算法、AirSim 接线或 D1 实验结果，因此
不对这些文件制造无关改动。
