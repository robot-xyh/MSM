# 正式 R0 五项后验定向复核

评估日期：2026-07-30

## 结论

clean source `1e5ed8ddcf27f375e922a447decfbd875d21bfdf` 下，原五个后验失败
cell 均通过新的 D6 独立定向复核。五项的 source、execution plan、shard、cell result
和 episode artifact tree 完整性均通过；在线真值使用为 0，有限状态为 true，基础
clean-formal 与实验矩阵 formal eligibility 均为 true。

五项后验代次合同全部为 `verified`。D1 最终代次等于完整后验发布数，D2 最终消费代次
等于 D1 最终代次，D2 消费数等于 D2 发布数。`consumption + pre_tick_merge` 等于
D1 最终代次，skip 为 0，pending 为空。

当前总执行进度为 177/900，其中原 135 项来自 shard 0、5、9，新增 42 项来自 shard 8
和 18 各 21 项。本专项只审计下列五个目标 cell，不能写成 177/177、900/900 或完整
R0 scope 已完成。

## 输入与隔离

- source worktree：`/tmp/msm-formal-r0-shard-1e5ed8d`
- source commit：`1e5ed8ddcf27f375e922a447decfbd875d21bfdf`
- source dirty：false
- formal R0 执行根目录：
  `/tmp/msm-formal-r0-shard-1e5ed8d/research_modules/scalable_3d_simulation/outputs/formal_r0_20260725_1e5ed8d`
- execution plan 逻辑摘要：
  `8804ecb4dd0513db55906905f031832711012974fc911546df40e09fb297d373`
- execution plan 文件摘要：
  `549f67b16b02c7a82cdb0eb9a275a37dfb3b74cf6e73fb49cdaee3850eb4e71d`

复核不读取 `targeted_formal_d6` 聚合，也不采用 producer 生成的
`episode/observation_governance_audit.json`。D1/D2 后验代次由
`online_observations.jsonl` 和 `summary.json` 重新计算。真值 sidecar 只供 D6 离线指标，
不进入在线链路。

## 方法

### 来源

D6 在 source worktree 中独立执行 Git HEAD 与 dirty 检查。执行计划中的 source commit、
repository dirty、formal parent、R0-only scope、900 个作用域 cell 和 20 个 shard
必须与冻结输入一致。执行计划逻辑摘要通过“移除自摘要字段后再做规范 JSON 摘要”重新计算，
文件摘要另与 `EXECUTION_PLAN_SHA256` 核对。

### 进度

D6 读取 shard 0、5、8、9、18 的 shard plan、checkpoint 和 progress。每个 progress
序列必须从 0 连续递增并与执行计划中的 shard sequence 对应。checkpoint 的 source、
execution plan、完成数、下一序号、状态和 progress 摘要必须一致。

| shard | checkpoint | 已完成 | 计划 |
| ---: | --- | ---: | ---: |
| 0 | complete | 45 | 45 |
| 5 | complete | 45 | 45 |
| 8 | paused | 21 | 45 |
| 9 | complete | 45 | 45 |
| 18 | paused | 21 | 45 |

五个分片累计 177 个 progress row。这里只验证进度账本，没有把 177 个 cell 全部当成本专项
D6 审计对象。

### Cell

每个目标 cell 均核对以下内容：

1. cell id、global index、scope index、shard index 和 shard sequence 与计划相同；
2. cell result 文件摘要与 progress row 相同；
3. source commit、execution plan、parent plan 和 episode relative path 相同；
4. 六个必要 episode 制品存在；
5. episode 目录内全部文件重新计算 artifact tree 摘要；
6. manifest、配置、summary 和在线总线由 D6 低层评估合同重新读取；
7. clean formal、实验矩阵、在线真值、有限状态和 generation integrity 同时通过。

任一项不可用、矛盾或失败都会关闭该 cell。不可用值不补零。

## 结果

| cell | shard | 规模 | seed | D1 final/pub | D2 final/consume/pub | merge | skip | pending | formal/matrix | generation |
| --- | ---: | ---: | ---: | --- | --- | ---: | ---: | :---: | :---: | --- |
| 00400__r0__delayed_noisy__5v5__seed_1000 | 0 | 5 | 1000 | 13/13 | 13/6/6 | 7 | 0 | 空 | 是/是 | verified |
| 00405__r0__delayed_noisy__5v5__seed_1005 | 5 | 5 | 1005 | 9/9 | 9/5/5 | 4 | 0 | 空 | 是/是 | verified |
| 00408__r0__delayed_noisy__5v5__seed_1008 | 8 | 5 | 1008 | 13/13 | 13/5/5 | 8 | 0 | 空 | 是/是 | verified |
| 00418__r0__delayed_noisy__5v5__seed_1018 | 18 | 5 | 1018 | 14/14 | 14/6/6 | 8 | 0 | 空 | 是/是 | verified |
| 00429__r0__delayed_noisy__20v20__seed_1009 | 9 | 20 | 1009 | 27/27 | 27/7/7 | 20 | 0 | 空 | 是/是 | verified |

五项均为 `clean_formal_experiment_matrix`。episode、实验矩阵、变体执行和 generation
failure reason 均为空。cell result 与 artifact tree 摘要均逐项匹配。

## 输出

完整输出位于忽略目录：

`research_modules/d6_evaluation_metrics/outputs/formal_r0_targeted_posterior_audit_1e5ed8d_20260730/`

| 文件 | SHA-256 |
| --- | --- |
| `FORMAL_R0_TARGETED_POSTERIOR_AUDIT_CN.md` | `b0905633177fa937d3fa081d84ff2962cf75d2cdb5821ae3c24ce3ddba13f3bc` |
| `formal_r0_targeted_posterior_audit.json` | `84ffc8c87178df7c1de39fef4bfdcfad36319d6b4f47a20f9ec3c439e43a5dee` |
| `formal_r0_targeted_posterior_cells.csv` | `3987a74a438cb969b54019202baf8dc4573603771b2e6fed1fa8ead6df6aff0d` |
| `SHA256SUMS` | `097eea84a35614d7ddbb8c8507806be9b00cbbaa3a8edb454b254c1ba50602b9` |

## 边界

1. 五项通过只关闭这五项在新 source 下的后验代次疑点。
2. 其余 172 个已执行 cell 未由本专项逐项审计。
3. 正式 R0 尚有 723 个 cell 未执行，完整批次验收继续开放。
4. 旧 source 的 895 项不能与新 source 的五项相加。
5. 未来若出现 skip，仍需版本化完整 D2 输入摘要。缺少摘要时继续失败关闭。
6. 本专项没有修改、补零、覆盖或删除 source episode，也没有启动 AirSim。

## 验证

- 专项测试：`9 passed, 1 warning in 2.37s`
- D6 全量测试：`1243 passed, 1 warning in 150.38s`
- 输出校验：`sha256sum -c SHA256SUMS` 全部通过
- Python 语法检查：专项模块和命令行入口通过
- D6 owned-path `git diff --check`：通过

warning 来自本机 Matplotlib `Axes3D` 依赖冲突。本专项不生成三维图，该 warning 不改变
JSON、CSV、Markdown 或后验代次判定。
