# D2 正式 R0 代次守恒审计

## 结论

正式 R0 在 source commit `2c7b425` 上完成 900 个 episode。D6 将其中 5 个
`delayed_noisy` episode 判为非 clean-formal。审计确认，D2 在线关联器没有漏收内部
pending，也没有拒绝已经送达的合法后验。断点位于 main 的 D1-D2 finalize 适配层：
最后一个 D1 后验在进入 D2 前被“输入签名未变化”分支跳过，随后 main 清空 pending
generation。

900 个 summary 的计数分布为：

- `d2_finalize_unchanged_posterior_skip_count=0`：895 个；
- `d2_finalize_unchanged_posterior_skip_count=1`：5 个。

旧守恒式
`consumption + pre_tick_merge = d1_generation` 恰好失败 5 项。扩展式
`consumption + pre_tick_merge + finalize_skip = d1_generation` 在 900/900 上成立。
扩展式证明每个 D1 generation 都被计入一个 runtime 分支，但不能证明 skip 是合法
no-op。五个 skip 的最终后验均相对 D2 最后实际消费后验发生状态和协方差变化。

本轮不修改 D2 算法，不伪造 `id_switch_count`，不通过调整统计公式放宽正式准入。
D2 replay-coast 复核已提交为 `dc5821f`，D6 准入修复已提交为 `8e955f3`，main 调用
路径修复已形成 clean source commit `98d01bf`。五个原失败 cell 的开发态定向回归通过。
旧 `2c7b425` 正式 R0 仍是 P0 失败基线。修复后 source `1e5ed8dd` 已完成 135/900，
其中 3/5 原失败项正式闭合；seeds 1008/1018 尚未运行。当前因磁盘仅比 20 GiB 下限多
约 65 MB 而停止，因此完整正式证据缺口保持开放。

## 失败范围

| 场景 | 规模 | seed | D1 最终代次 | D2 最终消费代次 | 实际消费 | pre-tick 合并 | finalize skip |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| delayed_noisy | 5v5 | 1000 | 13 | 11 | 5 | 7 | 1 |
| delayed_noisy | 5v5 | 1005 | 9 | 7 | 4 | 4 | 1 |
| delayed_noisy | 5v5 | 1008 | 13 | 10 | 4 | 8 | 1 |
| delayed_noisy | 5v5 | 1018 | 14 | 11 | 5 | 8 | 1 |
| delayed_noisy | 20v20 | 1009 | 27 | 17 | 6 | 20 | 1 |

五个 episode 的共同事实如下：

1. `d2_pending_d1_posterior_generation=None`，表面上 pending 已排空。
2. `d2_finalize_unchanged_posterior_skip_count=1`。
3. `D2 consumption + pre-tick merge = D1 generation - 1`。
4. D2 publication 序列停在 finalize 之前，没有最终 generation 的 D2 publication。
5. `d2_timestamp_conflict_count=0`，不是 D2 observation timestamp 冲突。

缺失量固定为 1，来自 finalize 被跳过的最新后验。D2 最终消费代次与 D1 最终代次之间
可能相差多代，是因为 finalize 前已有若干后验被正常合并到同一个 pending；最后一个
pending 又被跳过并清空。

## 内容核对

对每个失败 episode，审计读取 D1 完整后验 publication，比较 D2 最后实际消费 generation
与 D1 最终 generation。结果如下：

| 规模和 seed | 比较代次 | 变化航迹 | 有效时刻变化 | 状态最大绝对变化 | 协方差最大绝对变化 |
| --- | --- | ---: | --- | ---: | ---: |
| 5v5 seed 1000 | 11 -> 13 | 5/5 | 1.857160050 -> 1.888435746 s | 0.054740 | 2.334662 |
| 5v5 seed 1005 | 7 -> 9 | 5/5 | 1.867012060 -> 1.885621084 s | 0.044125 | 1.515708 |
| 5v5 seed 1008 | 10 -> 13 | 5/5 | 1.851710754 -> 1.877998822 s | 0.043312 | 1.954943 |
| 5v5 seed 1018 | 11 -> 14 | 5/5 | 1.855124232 -> 1.889256175 s | 0.065072 | 2.759925 |
| 20v20 seed 1009 | 17 -> 27 | 20/20 | 1.648471199 -> 1.903517306 s | 0.415096 | 22.623443 |

五例的目标数量和 D1 航迹数量保持一致，质量分级未变化，但全部航迹的状态均值和协方差
都发生变化。它们是合法的状态传播后验，不能仅因最新来源观测未变化而归类为 no-op。

## 调用链

main 在 D1 物化完整后验时执行以下操作：

1. D1 posterior generation 加一。
2. 若已有 pending，则 pre-tick merge count 加一。
3. pending generation 更新为最新 generation。

常规节拍到期后，main 调用 D2，并在成功后更新 consumed generation、消费次数和 D2
publication。该路径满足守恒。

episode finalize 先关闭 D1 scan input，释放尾部扫描并生成最终完整后验。随后 main
以 `skip_unchanged_posterior=True` 调用 D2 适配层。当前输入签名只包含每条航迹的
最新传感器、最新观测编号、最新量测时间、命中数和回放更新次数，不包含：

- D1 posterior generation；
- 航迹状态有效时刻；
- 六维状态均值；
- 六维协方差；
- 航迹质量状态；
- D2 可见完整后验的规范摘要。

签名相等时，main 在调用 D2 tracker 前直接返回 `False`。finalize 随后仍把 pending
标志和 pending generation 清空。该分支没有实际消费、没有 D2 publication，也没有
经过 D2 的重复证据治理。

## D2 行为

D2 已有 replay-coast 合同用于处理“来源观测证据重复、后验有效时刻前移”的完整后验：

- 重复来源证据不会增加 hit；
- 不会从重复后验创建新航迹；
- 不会刷新 original-observation freshness；
- 航迹按合法后验时刻执行有界 coast；
- observation claim ledger 继续阻止重复证据产生测量更新副作用；
- `global_track_id` 和 `id_switch_count` 语义不变。

D2 单元测试已经验证，即使重复后验携带大幅变化的位置输入，replay-coast 也保持
`hits=1`、`misses=0`、不建轨、不匹配，并把航迹预测到新的 frame timestamp。finalize
应把最后一个合法 D1 完整后验送入 D2，不能用 runtime 的简化签名替代该算法路径。

## No-op 准入

扩展守恒式可保留为诊断分区：

```text
D1 generation
  = actual D2 consumption
  + pre-tick merge
  + finalize skip disposition
```

它不能直接作为 clean-formal 通过条件。`finalize skip disposition` 只有同时满足以下
条件才可晋级为规范 no-op：

1. 使用 D2 实际可见的 Detection3D 批次计算规范内容摘要；
2. 摘要覆盖 measurement/arrival timestamp、状态、协方差、速度、分类、置信度、
   observation claim 与 replay/identity 相关元数据；
3. pending structural ambiguity evidence 为空；
4. 与 D2 上次实际消费输入逐字段语义等价；
5. 输出独立的 resolved generation watermark，不把 no-op 伪装成实际 consumption；
6. D6 分别校验 actual consumption、coalescence 和 admitted no-op 的数量与摘要证据。

当前五例不满足第 2、4 项。直接把 `finalize_skip` 加到正式守恒式会掩盖合法后验丢失。

## Main 所需动作

1. 当前最稳妥的修复是：只要存在 pending D1 generation 和非空完整后验，finalize 就
   实际调用 D2，不使用现有 `skip_unchanged_posterior` 快捷分支。
2. D2 成功返回后再清空 pending，并令 consumed generation 等于实际传入的 source
   generation。
3. D2 返回 `False` 时不得无条件清空 pending。runtime 需记录明确原因，并失败关闭。
4. 若未来恢复 no-op 优化，先实现上述强内容摘要和独立 resolved watermark，再单独
   申请 D6 准入；不得只修改守恒公式。
5. 增加 delayed/OOSM 尾部定向回归，至少覆盖正式失败的
   `5v5 seeds 1000/1005/1008/1018` 和 `20v20 seed 1009`。
6. 回归必须同时验证 pending 排空、最终代次相等、消费与 publication 相等、late batch
   未丢弃、重复证据未增加 hit、`id_switch_count` 未伪造。
7. 使用新 clean source commit 重跑正式 R0。旧 `2c7b425` 的 900-episode 产物继续作为
   失败证据，不能与修复后制品混合。

## D1 所需动作

D1 已按顺序发布最终 posterior generation，并保留双时间戳、协方差和尾部 OOSM 结果。
没有证据表明本次守恒失败由 D1 漏发布引起。

D1 可在后续性能工作中审查“未接受视觉观测但仍物化完整后验”的必要性，但不能为了让
计数通过而停止发布发生状态传播或协方差变化的合法后验。若 D1 提供规范 posterior
content digest，该摘要应由 D1 定义语义并由 main 验证，D2 不从 track ID 或少量元数据
字段推断等价性。

## 验证边界

本审计使用正式 R0 的持久化 D1/D2 publication、observation governance audit、
episode summary 和 D6 per-episode 结果。未修改正式输出，未使用在线 truth 修复业务
状态，未重算或覆盖 `id_switch_count`。

本轮结论是跨模块运行时断点诊断，不构成 D2 关联性能晋级，也不关闭真实 AirSim、
困难场景身份连续性或 200v200 实时性缺口。

## D2 验证

2026-07-25 在当前工作树运行 D2 全量测试，结果为 `305 passed, 1 warning in 29.45s`，
验收阈值为零失败。warning 是本机 Matplotlib `Axes3D` 版本冲突提示，与本次审计无关。
replay-coast 专项为 `5 passed in 0.95s`；main-owned hotfix 五 seed 定向测试为
`5 passed, 66 deselected in 3.51s`。`py_compile` 和 scoped `git diff --check` 通过。

全量 `pyflakes` 仍报告
`d2_data_association/calibration.py:6` 的既有 `dataclasses.field` 未使用导入。该行自
提交 `d0cd548f` 起已存在，source commit `2c7b425` 也包含它；本轮只提交运行时根因
诊断，没有为清理无关 lint 修改 D2 代码。

## Runtime Hotfix 复核

### 代码路径

2026-07-25 复核 main finalize 修复。main 已删除 finalize 调用中的
`skip_unchanged_posterior=True`，因此最后一个 pending D1 后验实际进入
`Scalable3DTracker.step()`。若 D2 返回未消费，finalize 现在抛出异常，不再清空 pending
后继续运行。

该改动符合上文“Main 所需动作”中的首选修复，不修改 D2 replay-coast、claim ledger、
`global_track_id` 或 `id_switch_count`。D2 复核、D6 准入修复和 main 修复分别提交为
`dc5821f`、`8e955f3`、`98d01bf`；`98d01bf` 是完整修复链的 clean source commit。

### 五个定向 Cell

开发态输出位于 `/tmp/msm-r0-finalize-fix-20260725`。五个 cell 均使用
`git_commit=2c7b425d076899e1c54a3d87d6ef23a613ba6e3a` 加未提交 hotfix，
`repository_dirty=true`。

| 规模和 seed | D1/D2 最终代次 | consumption/merge | quarantine/coast | skip | pending |
| --- | --- | --- | --- | ---: | --- |
| 5v5 seed 1000 | 13/13 | 6/7 | 5/5 | 0 | empty |
| 5v5 seed 1005 | 9/9 | 5/4 | 5/5 | 0 | empty |
| 5v5 seed 1008 | 13/13 | 5/8 | 5/5 | 0 | empty |
| 5v5 seed 1018 | 14/14 | 6/8 | 5/5 | 0 | empty |
| 20v20 seed 1009 | 27/27 | 7/20 | 20/19 | 0 | empty |

五例 `fresh_detection_count=0`、`created_track_ids_by_detection={}`、
`duplicate_coalescence_count=0`、`online_truth_use_count=0`。D2 最终 publication 的
source generation 均等于 D1 final generation。

### Replay-Coast 不变量

D2 owner 使用同一五组配置在当前工作树直接快照 finalize 前后的 Tracker：

- 五例全部航迹的累计 `hits` 保持不变；
- 五例全部航迹的 `last_update_time` 保持不变；
- Tracker 内部 track key 集合和规范 `global_track_id` 集合保持不变；
- finalize 没有创建新轨，也没有 duplicate coalescence；
- 四个 5v5 cell 的 5/5 replay 全部在宽限期内 coast，`misses` 不变；
- 20v20 seed 1009 的 20 条 detection 全部进入 replay quarantine，其中 19 条满足
  coast 宽限；`GT3D-000012` 超出宽限，按既有生命周期增加一次 miss，并把
  consecutive hits 从 3 清零。其累计 hits、last update time 和 canonical ID 不变。

最后一项是预期的 fail-safe 生命周期行为，不能写成 20/20 全部 coast。它不构成重复
命中、重复 birth 或身份改写。

### 开发态状态

代码路径和五个开发态定向回归通过。D6 对五例的 generation integrity 判定均为 true，
但五个 manifest 全部是 dirty working tree，正式准入数为 `0/5`，失败原因仅为
`repository_dirty_not_formal_evidence` 和 `episode_not_clean_formal_evidence`。

因此本 hotfix 已关闭可复现的代码路径缺陷，但五个开发态 cell 本身不关闭正式 R0。
后续正式批次必须使用冻结 source 和 execution plan，不能跨提交拼接证据。

旧 `2c7b425` 正式 900-cell 结果继续保留为失败基线；本次 5-cell dirty 输出只能作为
开发态定向回归，二者都不能改写为修复后的正式 R0。

## 修复后正式重跑进度

正式 source 为 `1e5ed8ddcf27f375e922a447decfbd875d21bfdf`，execution plan SHA-256
为 `8804ecb4dd0513db55906905f031832711012974fc911546df40e09fb297d373`。
shards 0、5、9 已完成，各 45 个单元，合计 135/900。

| 原失败 cell | D6 clean-formal | formal eligible | generation contract | skip | pending | failure reason |
| --- | --- | --- | --- | ---: | --- | --- |
| delayed_noisy 5v5 seed 1000 | pass | pass | verified | 0 | empty | empty |
| delayed_noisy 5v5 seed 1005 | pass | pass | verified | 0 | empty | empty |
| delayed_noisy 20v20 seed 1009 | pass | pass | verified | 0 | empty | empty |

D6 v10 对三项的正式准入为 3/3。D1 final generation 等于 D2 consumed generation，
D2 consumption 等于 publication。原失败 5v5 seeds 1008/1018 尚未正式重跑，故当前
只能声明 3/5 原失败项闭合，不能声明完整 R0 scope 或 900/900 正式验收。

当前可用空间只比 20 GiB 运行下限多约 65 MB，main 已在完整单元边界停止启动新单元。
存储迁移、扩容或明确清理后，应沿同一 source、plan 和分片合同继续其余 765 个单元，
最后由 D6 对 900/900 generation integrity、clean-formal 和 formal admission 统一验收。
