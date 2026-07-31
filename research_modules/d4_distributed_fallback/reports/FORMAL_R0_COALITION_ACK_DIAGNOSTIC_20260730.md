# 正式 R0 联盟确认后验诊断

评估日期：2026-07-30

## 结论

D6 对正式 R0 的独立审计确认 900/900 个 episode 制品、clean-formal 和代次完整性
有效，严格业务通过 872/900。28 个失败都位于 `high_threat_m_to_n`，最后可见原因为
`d4_fail_closed:collecting_member_acks`。

D4 对这 28 个失败和同场景 72 个通过样本重新检查后，结论如下。

1. D4 核心联盟状态机没有发现确定性转移缺口。缺少必要成员确认时，
   `execution_allowed=false`、`atomic_committed=false`，没有把部分确认当成提交。
2. 16/28 个失败存在 D3-D4 计划代次错位。D3 在 `t=1.0 s` 发布版本 2，D4 同一时刻
   仍发布版本 1 的预规划决策。这是 main 运行时编排问题。
3. 其余 12/28 个失败的 D3-D4 计划身份一致。其中 11 个 episode 的当前代次 ACK 在
   最后一次 D4 决策后到达，但中心正常时没有触发 D4 重评；1 个 episode 在时域内没有
   形成可消费 ACK，现有重发和终止尾窗不足。
4. 同场景 72 个 D6 通过样本中，还有 35 个样本存在 D3 版本 2、D4 版本 1 的代次
   错位。旧 D4 联盟即使已经提交，也不能证明当前 D3 计划已经完成 D4 仲裁。D6 需要
   增加当前计划身份一致性检查。
5. 修复会改变 D3-D4 发布顺序、D4 最终状态和后续 D7 门控。必须基于新的 clean
   source 整体重跑 900 项 R0，不能只重跑 28 项，也不能与当前结果拼接。

本轮完成诊断和文档同步。D4 代码未变，正式 R0 未重跑。

## 审计范围

冻结来源提交：

`1e5ed8ddcf27f375e922a447decfbd875d21bfdf`

冻结执行根：

`/tmp/msm-formal-r0-shard-1e5ed8d/research_modules/scalable_3d_simulation/outputs/formal_r0_20260725_1e5ed8d`

审计读取每个 episode 的：

- `online_observations.jsonl`；
- `summary.json`；
- `scenario_config.json`；
- D6 全量逐 cell 审计表。

逐 episode 比较以下证据：

- 最后一个 D3 `AssignmentPlan` 的 `plan_id` 和 `plan_version`；
- 最后一个 D4 区域决策的 owner、plan、version、epoch 和 lease；
- 每个多成员联盟的 required、acked 和 missing 成员集合；
- 区域计划广播和联盟成员 ACK 的总线序号、到达时间及绑定计划；
- 通信拒绝原因、丢弃数、pending 数和 episode 终止时刻。

本审计没有修改冻结制品，没有读取学习候选作为正式策略，也没有将旧来源结果拼入当前
范围。

## 场景时序

`high_threat_m_to_n` 的正式 R0 配置为：

| 参数 | 值 |
| --- | ---: |
| episode 时长 | 2.0 s |
| 质点步长 | 0.05 s |
| D3 分配周期 | 1.0 s |
| 通信固定延迟 | 0.04 s |
| 通信抖动 | 0.01 s |
| 通信丢包率 | 0.01 |
| D4 计划广播周期 | 0.10 s |
| D4 通信陈旧阈值 | 1.10 s |

最后一个已发布 D4 决策均位于 `t=1.0 s`。仿真在 `t=2.0 s` 仍投递到期通信消息，
但该终止采样点不再调用模块栈。到达终止点的 ACK 因此不会形成新的 D4 决策。

## 规模结果

下表只统计 `high_threat_m_to_n` 的 100 个 R0 样本。“代次错位”表示最后 D3 计划与
最后 D4 决策的 `(plan_id, plan_version)` 不一致。

| 规模 | D6 通过且对齐 | D6 通过但代次错位 | D6 失败且对齐 | D6 失败且代次错位 |
| ---: | ---: | ---: | ---: | ---: |
| 5 | 15 | 0 | 5 | 0 |
| 20 | 13 | 3 | 3 | 1 |
| 50 | 5 | 10 | 4 | 1 |
| 100 | 4 | 10 | 0 | 6 |
| 200 | 0 | 12 | 0 | 8 |
| 合计 | 37 | 35 | 12 | 16 |

200 对 200 的 20 个样本全部存在 D3-D4 代次错位。12 个样本虽然通过现有 D6 规则，
其 D4 提交状态仍属于旧计划，不能作为当前计划已提交的证据。

## ACK 结果

28 个失败中共有 38 个未提交联盟：

- 23 个位于 D3-D4 代次错位的 16 个 episode；
- 15 个位于计划身份一致的 12 个 episode。

在 12 个计划身份一致的失败 episode 中：

- 14 个当前代次必要成员 ACK 在 `t=1.0 s` 以后到达；
- 到达偏移最小值、中位数和最大值分别为 0.000067 s、0.011493 s 和 0.082041 s；
- 这些 ACK 没有触发中心正常状态下的 D4 重评；
- 1 个必要 ACK 在 episode 内没有形成可消费交付证据。

唯一的“当前代次 ACK 未交付”样本是
`00815__r0__high_threat_m_to_n__5v5__seed_1015`。`INT-0005` 在
0.888407 s 和 1.939900 s 两次收到当前计划广播，但 episode 内没有对应 ACK 交付。
该 episode 记录 2 个通信丢弃、2 个通信 pending 和 1 个控制意图丢弃。现有制品没有
逐消息的 dropped/pending 处置日志，不能把具体 ACK 唯一归因到丢包或终止点 pending。
现象与“首个 ACK 丢失，计划陈旧后才触发重发，第二个 ACK 越过终止尾窗”一致。

所有 38 个未提交联盟的 required 成员集合在两次 D4 决策间保持一致。联盟 lease
到期时间位于 5.7-5.9 s，明显晚于 2.0 s 终止时刻。没有发现成员集合变化或 lease
过期造成的失败。

4 个代次错位 episode 记录了 14 次
`plan_id_mismatch/plan_version_stale/epoch_stale`。这些拒绝发生在旧计划消息晚到、
D3 已进入新代次之后，属于正确的陈旧消息拒绝。它们进一步说明 main 在同一时刻发布了
新 D3 计划和旧 D4 决策。

## 通过样本对照

计划身份一致的 37 个通过样本包含 106 个需要原子提交的联盟。所有必要 ACK 都在最后
D4 决策前到达，106 个联盟全部为 `committed`。

代表性样本如下。

| 样本 | 结果 | 关键证据 |
| --- | --- | --- |
| `00800...5v5...seed_1000` | 对齐并通过 | D3/D4 均为同一 v1；1 个联盟已提交 |
| `00802...5v5...seed_1002` | 对齐但失败 | `INT-0005` ACK 在 1.000352 s 到达，晚于最后 D4 决策 |
| `00815...5v5...seed_1015` | 对齐但失败 | 两次计划广播可见，`INT-0005` ACK 在时域内不可见 |
| `00827...20v20...seed_1007` | 代次错位且失败 | D3 为 v2，D4 仍为 v1；旧消息陈旧拒绝可见 |
| `00881...200v200...seed_1001` | D6 通过但代次错位 | D3 为 v2，D4 13 个已提交联盟均属于旧 v1 |

## 28 个失败的分类

| cell | 规模 | seed | 根因分类 | 未提交联盟 | 证据 |
| --- | ---: | ---: | --- | ---: | --- |
| `00802__r0__high_threat_m_to_n__5v5__seed_1002` | 5 | 1002 | ACK 晚到未重评 | 1 | 晚到 1，未送达 0 |
| `00806__r0__high_threat_m_to_n__5v5__seed_1006` | 5 | 1006 | ACK 晚到未重评 | 1 | 晚到 1，未送达 0 |
| `00809__r0__high_threat_m_to_n__5v5__seed_1009` | 5 | 1009 | ACK 晚到未重评 | 1 | 晚到 1，未送达 0 |
| `00815__r0__high_threat_m_to_n__5v5__seed_1015` | 5 | 1015 | 重发和时域不足 | 1 | 晚到 0，未送达 1 |
| `00817__r0__high_threat_m_to_n__5v5__seed_1017` | 5 | 1017 | ACK 晚到未重评 | 1 | 晚到 1，未送达 0 |
| `00826__r0__high_threat_m_to_n__20v20__seed_1006` | 20 | 1006 | ACK 晚到未重评 | 1 | 晚到 1，未送达 0 |
| `00827__r0__high_threat_m_to_n__20v20__seed_1007` | 20 | 1007 | 计划代次错位 | 1 | D3 v2，D4 v1 |
| `00834__r0__high_threat_m_to_n__20v20__seed_1014` | 20 | 1014 | ACK 晚到未重评 | 2 | 晚到 3，未送达 0 |
| `00838__r0__high_threat_m_to_n__20v20__seed_1018` | 20 | 1018 | ACK 晚到未重评 | 1 | 晚到 1，未送达 0 |
| `00842__r0__high_threat_m_to_n__50v50__seed_1002` | 50 | 1002 | 计划代次错位 | 1 | D3 v2，D4 v1 |
| `00843__r0__high_threat_m_to_n__50v50__seed_1003` | 50 | 1003 | ACK 晚到未重评 | 2 | 晚到 2，未送达 0 |
| `00848__r0__high_threat_m_to_n__50v50__seed_1008` | 50 | 1008 | ACK 晚到未重评 | 1 | 晚到 1，未送达 0 |
| `00855__r0__high_threat_m_to_n__50v50__seed_1015` | 50 | 1015 | ACK 晚到未重评 | 1 | 晚到 1，未送达 0 |
| `00857__r0__high_threat_m_to_n__50v50__seed_1017` | 50 | 1017 | ACK 晚到未重评 | 1 | 晚到 1，未送达 0 |
| `00863__r0__high_threat_m_to_n__100v100__seed_1003` | 100 | 1003 | 计划代次错位 | 1 | D3 v2，D4 v1 |
| `00870__r0__high_threat_m_to_n__100v100__seed_1010` | 100 | 1010 | 计划代次错位 | 1 | D3 v2，D4 v1 |
| `00872__r0__high_threat_m_to_n__100v100__seed_1012` | 100 | 1012 | 计划代次错位 | 2 | D3 v2，D4 v1 |
| `00873__r0__high_threat_m_to_n__100v100__seed_1013` | 100 | 1013 | 计划代次错位 | 1 | D3 v2，D4 v1 |
| `00875__r0__high_threat_m_to_n__100v100__seed_1015` | 100 | 1015 | 计划代次错位 | 1 | D3 v2，D4 v1 |
| `00877__r0__high_threat_m_to_n__100v100__seed_1017` | 100 | 1017 | 计划代次错位 | 6 | D3 v2，D4 v1 |
| `00880__r0__high_threat_m_to_n__200v200__seed_1000` | 200 | 1000 | 计划代次错位 | 2 | D3 v2，D4 v1 |
| `00884__r0__high_threat_m_to_n__200v200__seed_1004` | 200 | 1004 | 计划代次错位 | 1 | D3 v2，D4 v1 |
| `00886__r0__high_threat_m_to_n__200v200__seed_1006` | 200 | 1006 | 计划代次错位 | 1 | D3 v2，D4 v1 |
| `00892__r0__high_threat_m_to_n__200v200__seed_1012` | 200 | 1012 | 计划代次错位 | 1 | D3 v2，D4 v1 |
| `00894__r0__high_threat_m_to_n__200v200__seed_1014` | 200 | 1014 | 计划代次错位 | 1 | D3 v2，D4 v1 |
| `00895__r0__high_threat_m_to_n__200v200__seed_1015` | 200 | 1015 | 计划代次错位 | 1 | D3 v2，D4 v1 |
| `00896__r0__high_threat_m_to_n__200v200__seed_1016` | 200 | 1016 | 计划代次错位 | 1 | D3 v2，D4 v1 |
| `00897__r0__high_threat_m_to_n__200v200__seed_1017` | 200 | 1017 | 计划代次错位 | 2 | D3 v2，D4 v1 |

## 根因定位

### D4 核心状态机

`RegionalFailoverCoordinator` 会在每次快照中将有效 ACK 交给
`CoalitionCommitCoordinator.record_ack()`。第三个必要成员 ACK 到达后，状态从
`collecting_acks` 转为 `committed`。冻结来源和当前源码的正常中心、多成员逐 ACK
回归均通过。

没有发现以下 D4 本地缺口：

- 必要成员集合变化；
- 部分 ACK 被误判为完整提交；
- 当前代次有效 ACK 被 D4 核心状态机拒绝；
- lease 提前过期；
- `collecting_acks` 在再次执行 `evaluate()` 后仍无法转移。

### main 运行时编排

根因位于以下三个时序。

1. `_run_assignment_and_failover()` 在已有计划且故障代次未变时，先用旧计划构造
   `preplanning_snapshot` 并运行 D4，随后才运行 D3。D3 产生新计划后，代码因
   `preplanning_snapshot` 已存在而不再对新计划运行 D4。
2. `step()` 只在 `center_health == FAILED` 时，因 D4 通信证据变化触发非分配周期的
   D4 重评。中心正常的多成员联盟收到最后 ACK 后，要等下一个 D3 分配周期才能更新。
3. orchestrator 在最后一个时间点只投递通信，不再调用模块栈。终止点 ACK 能写入总线，
   但不能更新 D4 状态。

ACK 没有独立重发状态机。当前实现依赖计划广播变陈旧后再次广播，接收方再生成 ACK。
1.10 s 陈旧阈值和 2.0 s episode 使第二次往返靠近终止点。

## main 修复要求

1. **同代次发布。** D3 产生新 `AssignmentPlan` 后，main 必须基于该计划重新构造 D4
   快照。发布的 D3 和 D4 必须具有相同 `plan_id/plan_version/epoch`。旧预规划 D4
   结果只能作为内部输入，不能作为新计划的最终仲裁结果。
2. **ACK 事件重评。** 当前计划存在 `proposed/collecting_acks` 联盟时，收到当前代次
   有效 ACK 应触发 D4 重评，不以中心是否失效为前提。重评仍需校验全部必要成员、
   plan、epoch、lease、成员身份和原子提交条件。
3. **定向可靠重发。** 为未确认成员维护有界 ACK 超时和重发计数。只重发同一代次的
   计划或 ACK 请求，不改变 required 成员集合，不延长既有 lease，不把超时视为成功。
4. **终止尾窗。** 正式短 episode 需要一个不推进物理状态的通信/模块排空阶段，或在
   终止采样点至少再执行一次模块栈。排空应有固定上限，并在未收齐时明确
   `missing_required_acks`。
5. **逐消息处置。** 日志增加 message ID、topic、source、destination、queued、
   dropped、delivered、pending 和 retry generation。D6 才能区分 ACK 丢包、带宽排队
   和终止点未消费。
6. **D6 当前计划检查。** 每个 episode 应验证最后 D4 owner 和所有联盟状态绑定最后
   D3 计划。代次不一致时严格失败，不得用旧计划的 committed 状态通过。

## 回归与重跑

main 修复后建议按以下顺序验证：

1. 复现 `00802`，确认 1.000352 s 的 ACK 在下一物理 tick 触发当前计划提交；
2. 复现 `00815`，确认首个 ACK 丢失后在固定重试预算内恢复，或以明确 transport
   timeout 失败关闭；
3. 复现 `00827` 和 `00881`，确认 D3 v2 与 D4 v2 同代次发布；
4. 先重跑本报告识别的 63 个受影响样本，再重跑 100 个
   `high_threat_m_to_n`；
5. 在新的 clean commit 下重新执行完整 900 项 R0，由 D6 独立复核。

63 个受影响样本由 51 个 D3-D4 代次错位样本和 12 个计划对齐但 ACK 未闭合样本组成。
定向复现只能作为预检，不能替代正式 900 项重跑。

## D4 验证

- 冻结来源定向状态机回归：4 passed；
- 当前源码定向状态机回归：4 passed；
- 当前 D4 全量回归：903 passed；
- 环境警告：Matplotlib `Axes3D` 导入警告 1 项，与本次联盟逻辑无关；
- D4 代码修改：无；
- 正式 R0 制品修改：无；
- 正式 R0 重跑：未执行。

## Owner 复核

复核日期：2026-07-30

复核结论：**未通过。**

main-owned 编排修复已经覆盖原诊断中的同代重评、正常中心 ACK 事件重评、有界重发、
终止通信排空、逐消息处置和冻结 lease。专项回归与 D4 全量回归均通过。当前仍存在一项
运行时授权缺口和一项代次审计缺口，因此不能据此启动新的正式 R0 全量评价。

### 已满足要求

1. D3 完成规划后，main 会基于 `latest_plan` 重新构造 D4 快照并执行
   `RegionalFailoverCoordinator.evaluate()`。预规划结果不再作为新 D3 计划的最终
   D4 决策。
2. 当前代次有效通信证据到达时，只要本轮不是 D3 分配时刻，中心处于 `normal` 也会
   触发 D4 重评。若恰逢分配时刻，则由规划后的当前计划 D4 评价覆盖。
3. 计划重发按计划、版本、epoch、通信分区代次和成员分别计数。默认最多一次初发和
   两次重发。重试耗尽不会形成提交，缺少必要 ACK 时继续失败关闭。
4. episode 尾部使用固定上限的 D4 通信排空。排空输出的拦截资源和侦察资源加速度均
   为零，不发布相机命令，也不推进质点动力学。
5. 同一 `(plan_id, plan_version, epoch)` 的计划 lease 在首次快照时冻结。D4 快照、
   计划广播和由该广播生成的成员 ACK 使用同一期限。ACK 重评、重发和尾部排空不会
   延长该期限，reset 会清空冻结缓存。
6. 通信制品已增加逐消息 `delivered/dropped/pending`、消息标识、主题、源、目的节点
   和 `retry_generation`。

### 阻断问题

#### 中心路径可复用旧 D4 提交

`research_modules/scalable_3d_simulation/module_stack.py` 的
`_d4_permission()` 只在二级和分布式路径调用计划代次核对。中心路径在
`decision.execution_allowed=true` 且旧 `task_commit.execution_authorized=true`
时，没有比较 D4 ownership 与当前 D3 的 `plan_id/plan_version/epoch`。
`_guidance_commit_fields()` 随后使用 `latest_plan` 填写 `commit_plan_id` 和
`commit_plan_version`，会把旧 D4 提交标记成新 D3 计划的提交。

负向注入保留已提交的 D4 v1 决策，仅把 `latest_plan` 推进到 v2。实际结果为：

- `d4_current_plan_alignment.aligned=false`；
- `_d4_permission()` 仍返回 `action=continue_center`；
- 返回的 `new_plan_version=2`，而实际 D4 ownership 仍为 v1。

该行为违反“旧代 committed 不得为新 D3 计划授权”。main 需要在所有 authority layer
进入授权逻辑前执行统一的 `(plan_id, plan_version, epoch)` 核对。任一字段不一致时应
返回 hold，且不得用当前 D3 字段重写旧 D4 commit 的来源代次。

#### 对齐诊断未包含 epoch

`d4_current_plan_alignment()` 当前只比较 `plan_id` 和 `plan_version`。它虽然输出
`d4_epoch_values`，但没有计算并输出 D3 当前 authority epoch，也没有把 epoch 纳入
`aligned`。

第二次负向注入保持相同 `plan_id/version`，将 D3 authority epoch 从 1 推进到 11，
同时保留 D4 epoch 1。实际结果为：

- `d4_current_plan_alignment.aligned=true`；
- `_d4_permission()` 仍返回 `continue_center`；
- D3 期望 epoch 为 11，D4 ownership epoch 为 1。

main 的运行时对齐合同和 D6 最终审计都应比较完整三元组。终止排空完成判定还应同时
要求当前计划对齐；现有缺 ACK 计算会跳过错位的 D4 region，可能把错位状态计为
`missing_required_ack_count=0`。

### 修复验收条件

1. 为中心、二级和分布式三条授权路径增加统一的当前代次门控。
2. `d4_current_plan_alignment` 增加 D3 authority epoch，并把 epoch 纳入
   `aligned`。
3. 终止排空只在当前 D3/D4 三元组对齐且必要 ACK 为零时标记完成。
4. 增加两个负向回归：旧版本 committed 不得授权新版本；相同版本但旧 epoch 不得
   授权当前 epoch。
5. 修复后由 D4 owner 重新复核，再执行代表样本、100 个
   `high_threat_m_to_n` 和新的 clean commit 完整 900 项 R0。

### 本次测试

- `test_regional_failover.py`：25 passed；
- D4 全量：903 passed；
- scalable 同代重评、终止排空、重试耗尽、M-to-N ACK 专项：4 passed；
- 通信逐消息处置专项：1 passed；
- 负向计划版本注入：复现旧 D4 v1 对新 D3 v2 返回 `continue_center`；
- 负向 epoch 注入：复现 D3 epoch 11、D4 epoch 1 时对齐诊断仍为 true，且返回
  `continue_center`；
- Matplotlib `Axes3D` 导入警告 1 项，与本次 D4 复核无关；
- main-owned 文件修改：无；
- 正式 R0 预留 seed 1000-1019 新评价结果：未读取、未生成。

## Owner 二次复核

复核日期：2026-07-30

复核结论：**未通过。**

最新 main P0 补丁已经关闭上一次复核发现的直接授权和对齐问题：

1. `d4_current_plan_alignment-v2` 比较 plan ID、plan version、D3 authority epoch
   和该代次冻结 lease；任一字段不一致时 `aligned=false`。
2. `_d4_permission()` 在中心、二级和分布式分支前统一要求当前代次对齐。旧
   committed 不能直接授权新 D3 版本或旧 authority epoch。
3. `_d4_missing_required_member_ids()` 在错代时不再返回成功空集；terminal drain
   只有在当前计划对齐且缺 ACK 数为零时才标记完成。
4. 错冻结 lease 的 owner 注入得到 `hold_for_review` 和
   `d4_current_plan_generation_mismatch`。

### 剩余 P0

main 的 ACK 缓存仍未绑定完整 plan identity。

- `_d4_ack_deliveries` 的键为 resource、global track、plan version、epoch 和
  partition generation，不含 plan ID。
- `_d4_acks()` 按上述键读取缓存后，只核对 lease 时效、coalition ID/version；
  没有核对缓存 payload 的 plan ID。
- 输出 `CoalitionMemberAck` 的 plan ID 取自当前 task，而非缓存 payload，导致旧
  ACK 被改写成当前计划 ACK。

只读负向注入先形成一个 3/3 ACK 的已提交联盟，随后仅修改 D3 `plan_id`，保持
version、epoch、coalition 和缓存不变。新快照重新暴露 3 个 ACK，三个 ACK 的 plan ID
均被改写为新计划 ID。现有有状态协调器以 `authority_plan_digest_conflict` 失败关闭；
将同一快照交给 fresh `RegionalFailoverCoordinator` 后，联盟直接转为
`committed/execution_authorized=true`。

该结果说明当前安全性依赖协调器进程内历史。ACK 因果证据本身没有完成 plan ID 绑定，
仍不满足“旧 committed 绝不授权新 D3 计划”。

#### Terminal drain 可误报完成

上述 plan-id-only 注入在现有有状态协调器中触发
`authority_plan_digest_conflict`。该状态没有放行控制，但终止排空的完成记录不正确：

- `d4_current_plan_alignment.aligned=true`；
- region 为 `fail_closed=true/execution_allowed=false`；
- region reason 为 `authority_plan_digest_conflict`；
- coalition commit 数为 0；
- `_d4_missing_required_member_ids()` 返回空集；
- orchestrator 的 `missing_ack_count == 0 && current_plan_aligned` 判据成立。

`_d4_missing_required_member_ids()` 当前只遍历已有 coalition commit。当前 D3
assignment 明确要求多个成员，但 region 因 digest 冲突没有生成 commit 时，函数没有从
assignment 的 required 成员集合识别缺口。region ownership 又已经使用当前
plan ID/version/epoch/lease，因此 alignment 不能识别该语义失败。

这会把“当前联盟失败关闭且未形成提交”记为“D4 通信排空完成”。它不会直接绕过
`_d4_permission()` 的 region execution 门，但会污染 episode 完成状态、D6 审计和正式
R0 是否已闭合的判断，属于正式评价前必须关闭的 P0。

### main 修复要求

1. 将 plan ID 纳入 `_d4_ack_deliveries` 和 `_d4_plan_deliveries` 的缓存键及全部查找
   路径。
2. `_d4_acks()` 必须核对 payload/receipt 的 plan ID、version、epoch、冻结 lease、
   coalition ID/version 和 partition generation；不得用当前 task 字段重写来源代次。
3. `_d4_missing_required_member_ids()` 应以当前 D3 多成员 assignment 为基准。缺少
   同代 region、缺少对应 commit、region 失败关闭、commit 未授权或成员 ACK 不完整时，
   均不得返回成功空集。
4. terminal drain 完成除当前代次对齐和缺 ACK 为零外，还应要求所有当前多成员
   assignment 均有同代 commit，region 可执行且 commit 已授权。
5. 增加 plan-id-only 负向回归，要求新快照 ACK 数为零、联盟保持未提交。
6. 增加独立错 lease pytest。现有正向测试验证 lease 稳定，未覆盖错误 lease 的拒绝。
7. 增加真实旧 ACK/digest conflict 排空负例。现有测试通过 subclass 改写 diagnostics，
   只验证 orchestrator 最终 alignment 门，不覆盖 ACK 缓存、
   `_d4_missing_required_member_ids()` 和无 commit region 的真实输入。

### 本次测试

- `test_regional_failover.py`：25 passed；
- D4 全量：903 passed；
- scalable 当前计划重评、旧 plan、旧 epoch、正常排空、错代排空、重试耗尽、
  M-to-N ACK 和逐消息处置专项：8 passed；
- 错冻结 lease owner 注入：正确失败关闭；
- plan-id-only ACK 注入：复现旧 ACK 被新 plan ID 重绑定；fresh coordinator 错误
  提交；
- 真实 plan-id-only 历史 digest 冲突注入：region 失败关闭且无 commit，但缺 ACK
  计数为 0，现有 terminal drain 完成谓词为 true；
- Matplotlib `Axes3D` 导入警告 1 项，与本次复核无关；
- main-owned 文件修改：无；
- 正式 R0 预留 seed 1000-1019 新评价结果：未读取、未生成。

## Owner 第三轮最终复核

复核日期：2026-07-30

复核结论：**通过。当前 main-owned P0 全部关闭。**

本轮只读复核确认以下闭环：

1. plan delivery 和 ACK 缓存键、写入及查询均包含 plan ID。ACK 从原始 payload
   恢复 plan ID、version 和 epoch，不再用当前 task 改写来源代次。
2. 正常成员就绪要求 delivery payload 的 plan ID 与当前计划一致。旧 plan
   delivery 不能在 plan-id-only 变化后继承 `communication_ready`。
3. 二次失效桥接只接受显式 `previous_plan_id` 对应的上一版本，同时核对目标集合、
   partition generation 和 lease；任意旧计划不能进入桥接路径。
4. plan delivery receipt 和 ACK receipt/payload 的原始 lease 均必须覆盖当前冻结
   lease。fresh coordinator 不能把旧 ACK 提交到更晚的新期限。
5. `d4_current_plan_execution_closure` 要求当前多成员 assignment 存在同代、可执行且
   完整授权的 commit。terminal drain 仅在 alignment、execution closure 和
   missing ACK 三项闭合时完成。

未发现新的 P0 或独立 P1。当前剩余事项是验证状态而非代码缺口：main 需在新的 clean
source 下完整重跑正式 R0，D6 独立审计 900 项制品。旧 872/900 业务结果不能用于证明
修复后结果，也不得与新结果拼接。

### 最终定向测试

- scalable 定向测试：11 passed；
- 覆盖当前计划重评、plan-id-only、旧 plan delivery、旧 ACK、错 epoch、错 lease、
  fresh coordinator lease 扩展、真实 authority digest conflict 排空和二次失效显式
  桥接；
- main 报告 scalable 全量：411 passed；
- 上一轮 D4 全量：903 passed；本轮按要求未重复运行；
- Matplotlib `Axes3D` 导入警告 1 项，与本次复核无关；
- main-owned 文件修改：无；
- 正式 R0 预留 seed 1000-1019 新评价结果：未读取、未生成。

## 高威胁开发批次追加复核

复核日期：2026-07-30

第三轮复核之后，main 运行了新的开发态 100 项高威胁预检。当前计划联盟执行闭合为
97/100。该证据重新打开两个 main/D3-owned 集成问题，但没有重新打开 D4 核心协议
P0：

1. 当前 D3 plan 的目标从 D2 当前输出消失后，main `_d4_snapshot()` 静默删除对应
   task。两个失败样本删除前已 3/3 committed，终态因缺少整个 commit 呈现为三个
   成员均缺。
2. 同一 `plan_id/version/epoch` 可以对应不同规范摘要。旧摘要 ACK 被 D4 正确拒绝，
   表明内容寻址门控有效；计划身份不可变性仍需由 D3/main 关闭。

详细逐消息时间线、lease、terminal drain 和修复归属见
`HIGH_THREAT_PRECHECK_V3_COALITION_DIAGNOSTIC_20260730.md`。在 main-owned P0/P1
修复并完成新批次复跑前，“当前 P0 全部关闭”仅保留为第三轮源码专项的历史结论，不能
外推到最新集成运行。

## 高威胁开发批次 v4 最终复核

复核日期：2026-07-30

复核结论：**main-owned 集成缺口已完成 development/dirty 批次验证；formal R0 仍待。**

main 已为当前 D3 assignment target 保留最后可信、真值隔离的 D2 航迹证据，并冻结
同一计划身份的首次权威载荷。D2 临时缺轨不再静默删除 D4 task/coalition；
evaluation refresh 不再覆盖 transport reference。D4 的 plan ID、version、epoch、
冻结 lease、分区、成员和 SHA 校验没有修改。

`msm-high-threat-r0-p0-precheck-v4-20260730` 共 100 个 episode。D3-D4 当前计划对齐
100/100，当前计划联盟执行闭合 100/100，在线真值使用为零，权威计划摘要冲突为零。
28 个 episode 使用过 plan-track fallback，三个 v3 原失败样本均闭合。D7 对缺少
当前 D2 航迹或身份承诺的目标仍保持失败关闭。

D6 已完成 v4 独立审计：计划 ID/版本对齐 100/100，644 个当前多成员联盟目标全部
闭合，195838 条通信处置在 100/100 episode 中均为 available/verified。D3 区域
epoch 与 lease 对照字段均为 0/100 available，属于开放 P1。

该结果来自 dirty development source、2 秒时长的 100-cell 高威胁预检，只关闭此前
main-owned P1 的开发态验证。它不得称为 formal R0，也不得与旧 900 项制品拼接。正式
结论仍要求从 clean source 完整重跑 900 项，并补齐区域 epoch/lease 对照字段。D4
全量回归为 903/903；一个 no-op 集成测试已同步“诊断重评不重复权威发布”的新合同，
D4 算法未改。
