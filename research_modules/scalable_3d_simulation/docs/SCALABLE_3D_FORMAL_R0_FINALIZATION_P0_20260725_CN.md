# 正式 R0 后验收尾审计

## 结论

绑定 clean commit `2c7b425d076899e1c54a3d87d6ef23a613ba6e3a` 的正式 R0 已完成
20 个分片和 900 个单元。该批次证明 R0 执行范围完整，不能证明 900 个单元全部通过正式
准入。D6 确认 895 个单元满足 clean-formal 条件，另有 5 个单元发生最后一代 D1 后验未被
D2 实际消费的问题。

main 已修复运行时收尾链路。五个原失败单元的开发态定向复跑均通过后验代次合同。正式
关闭仍需在新 clean commit 和新 execution plan 下整体重跑 900 个单元。

## 正式批次

| 项目 | 结果 |
| --- | --- |
| source commit | `2c7b425d076899e1c54a3d87d6ef23a613ba6e3a` |
| execution plan SHA-256 | `3e96e434c485e84aa85b654d93f9a022bd0216272390d852c73763d961ae4fb8` |
| 完整父清单 | 5700 单元 |
| R0 scope | 900 单元 |
| 分片 | 20/20 完成，每片 45 单元 |
| scope 状态 | `formal_scope_complete=true` |
| 完整矩阵状态 | `formal_matrix_complete=false` |
| D6 clean-formal | 895/900 |
| D6 失败 | 5/900 |

失败单元为：

1. `delayed_noisy` 5v5 seed 1000；
2. `delayed_noisy` 5v5 seed 1005；
3. `delayed_noisy` 5v5 seed 1008；
4. `delayed_noisy` 5v5 seed 1018；
5. `delayed_noisy` 20v20 seed 1009。

## 失效机理

D1 在 episode 结束时排空按到达时刻排序的有限扫描尾部，并发布最后一代完整融合后验。
这五个单元的最后一个扫描没有新增可接受源证据，但 D1 仍根据新状态有效时刻完成了运动
传播和协方差传播。后验的来源观测编号保持不变，状态、协方差和有效时刻发生变化。

原 main finalize 使用简化签名判断 D2 输入是否变化。签名只包含最新观测编号、观测时刻、
命中数和重放计数，没有包含以下内容：

- D1 posterior generation；
- 状态有效时刻；
- 六维位置速度状态；
- 六维协方差；
- 航迹状态和完整输入内容摘要。

签名相同时，main 在调用 D2 Tracker 前跳过该后验，随后仍清空 pending generation。D2
没有产生对应 publication，D6 因此发现最终代次未追平。五项逐轨最大差值如下。

| 场景 | seed | 最大状态差 | 最大协方差元素差 | 时刻差 |
| --- | ---: | ---: | ---: | ---: |
| delayed_noisy 5v5 | 1000 | 0.054740 | 2.334662 | 0.031276 s |
| delayed_noisy 5v5 | 1005 | 0.044125 | 1.515708 | 0.018609 s |
| delayed_noisy 5v5 | 1008 | 0.043312 | 1.954943 | 0.026288 s |
| delayed_noisy 5v5 | 1018 | 0.065072 | 2.759925 | 0.034132 s |
| delayed_noisy 20v20 | 1009 | 0.415096 | 22.623443 | 0.255046 s |

`consumption + pre_tick_merge + finalize_skip = generation` 在旧 900 项中数值成立，只能
说明分支计数完整。它不能证明被跳过后验与 D2 最后消费输入等价。

## 修复

main runtime 采用以下处理：

1. finalize 不再根据简化签名跳过最后 D1 后验；
2. 最后一代 pending 后验必须实际调用 D2 Tracker；
3. 只有 D2 成功返回并发布关联航迹后，main 才清除 pending generation；
4. D2 无法消费时，finalize 抛出运行错误，episode 失败关闭；
5. 重复来源证据继续由 D2 observation claim ledger 和 replay-coast 处理。

D2 replay-coast 先将已经声明过的来源观测隔离，再把关联航迹仅预测到新的状态有效时刻。
该分支不执行量测更新，不增加 hit，不增加 miss，不创建航迹，不刷新原始证据时钟。D2
仍发布一次带来源 D1 generation 的结果，表明该完整后验已被运行时处理。超过 coast
宽限期的重复证据仍被隔离，相应航迹按既有生命周期增加 miss，不会重复命中或新建航迹。

本修复没有修改 D1 融合算法、D2 关联代价、D3 分配、D4 降级、D5 配准或 D7 的比例导引
和视觉比例导引公式。

## 定向验证

五个原失败单元按正式批次相同的场景、规模、seed、2.0 秒时长和
`entity_fixed_v1` 随机调度复跑。输出位于
`/tmp/msm-r0-finalize-fix-20260725`，用于本地开发审计，不作为长期正式制品。

| 场景 | seed | D1 final | D2 consumed | consumption | publication | merge | skip | pending |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| delayed_noisy 5v5 | 1000 | 13 | 13 | 6 | 6 | 7 | 0 | empty |
| delayed_noisy 5v5 | 1005 | 9 | 9 | 5 | 5 | 4 | 0 | empty |
| delayed_noisy 5v5 | 1008 | 13 | 13 | 5 | 5 | 8 | 0 | empty |
| delayed_noisy 5v5 | 1018 | 14 | 14 | 6 | 6 | 8 | 0 | empty |
| delayed_noisy 20v20 | 1009 | 27 | 27 | 7 | 7 | 20 | 0 | empty |

D6 v10 将五项 `observation_governance_generation_contract_status` 全部判为
`verified`。最终 D2 帧均满足：

- `fresh_detection_count=0`；
- `replay_quarantined_detection_count>0`；
- `replay_coast_count>0`；
- `created_track_ids_by_detection={}`；
- `duplicate_coalescence_count=0`；
- `global_track_id_owner=D2_center`；
- 在线真值使用为 0。

四个 5v5 尾帧均为 5/5 replay-coast。20v20 seed 1009 隔离了 20 条重复证据，其中
19 条 coast，1 条超过宽限期并增加一次 miss；累计 hit、原始证据更新时间、birth count
和规范 `global_track_id` 集合保持不变。

测试结果：

- 五个失败 seed 加既有 finalize 定向测试：`6 passed`；
- scalable 3D 全量：`285 passed, 1 warning`；
- D2 全量：`305 passed, 1 warning`；
- D6 全量：`894 passed, 1 warning`。

warning 来自本机 Matplotlib `Axes3D` 导入冲突，不影响本次 JSON、代次和状态机验证。

## 验收边界

当前可以声明：

- 旧 source commit 的 R0 scope 已运行完成；
- 旧批次正式准入为 895/900；
- 后验收尾 P0 的代码修复和五项开发态定向回归通过；
- D6 保持失败关闭，不接受未验证的 finalize skip。

当前不能声明：

- 旧批次 900/900 clean-formal；
- 修复后的 5 项可以与旧 895 项拼接；
- 修复后的完整 R0 已正式验收；
- 5700 单元七变体矩阵完成；
- 200 对 200 已达到实时运行目标。

## 后续工作

1. D1 审计、D2 复核、D6 v10 和 main runtime 已分批提交为
   `4b018e4`、`dc5821f`、`8e955f3`、`98d01bf`；
2. 完成最终文档同步后，在 clean HEAD 上重新生成完整父计划和 R0 execution plan；
3. 从零运行 20 个分片和 900 个 R0 单元；
4. 由 D6 v10 重新生成逐 seed CSV、聚合 JSON 和中文报告；
5. 只有 900/900 clean-formal 后，才关闭本 P0 的正式证据项。

当前文件系统可用空间约 24 GiB。现有正式批次约 22 GiB，旧失败现场约 1.2 GiB。新正式
批次预计仍需约 22 GiB，运行器还要求保留 20 GiB 可用空间。现有证据不得在没有明确授权
的情况下删除。下一轮正式运行需要迁移旧证据、扩展存储或获得经过确认的清理方案。
