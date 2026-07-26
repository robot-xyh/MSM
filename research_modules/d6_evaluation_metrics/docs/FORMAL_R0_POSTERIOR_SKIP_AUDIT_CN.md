# 正式 R0 后验跳过审计

## 结论

正式 R0 的 900 个计划单元均已执行并完成哈希合并，结构性状态可以保留为
`formal_scope_complete=true`。D6 只能接受其中 895 个 clean-formal episode。其余 5 个
episode 存在 D1 最终后验未被 D2 消费的问题，继续归入
`descriptive_or_incomplete_evidence`。

这 5 项不是 D6 误判。运行时声明了一次
`d2_finalize_unchanged_posterior_skip`，但最后已消费后验与最终 D1 后验的逐轨状态、
协方差和有效时刻均不相同。计数式增加一次 skip 后虽然数值守恒，不能证明后验内容等价。

main 后续修复了 finalization，并定向重跑这 5 项。修复后五项 generation contract 全部
verified，且不再声明 skip。该批次来自 dirty 工作树，只能证明修复在定向开发回归中生效，
不改变旧 clean 提交的 895/900 正式结论。

## 输入

- 源提交：`2c7b425d076899e1c54a3d87d6ef23a613ba6e3a`
- 场景范围：R0，9 类场景，5 个规模，20 个 seed
- 计划单元：900
- clean-formal：895
- descriptive/incomplete：5
- 在线真值使用：0
- 原始合并目录保持只读，没有用新评估器覆盖

## 异常清单

| cell | episode | D1 final | D2 consumed | consume | merge | declared skip | 最大状态差 | 最大协方差差 | 时刻差 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 00400 | delayed_noisy 5v5 seed 1000 | 13 | 11 | 5 | 7 | 1 | 0.054740 | 2.334662 | 0.031276 s |
| 00405 | delayed_noisy 5v5 seed 1005 | 9 | 7 | 4 | 4 | 1 | 0.044125 | 1.515708 | 0.018609 s |
| 00408 | delayed_noisy 5v5 seed 1008 | 13 | 10 | 4 | 8 | 1 | 0.043312 | 1.954943 | 0.026288 s |
| 00418 | delayed_noisy 5v5 seed 1018 | 14 | 11 | 5 | 8 | 1 | 0.065072 | 2.759925 | 0.034132 s |
| 00429 | delayed_noisy 20v20 seed 1009 | 27 | 17 | 6 | 20 | 1 | 0.415096 | 22.623443 | 0.255046 s |

五项的 pending 字段均为空，D1 代次连续，D2 来源代次严格递增且只引用已发布代次。失败集中在
episode 末尾。`consumption + pre_tick_merge` 比 D1 最终代次少 1；把声明的 skip 加入后
等式成立，但该 skip 没有通过内容等价检查。

## 根因

main 运行时的 D2 输入签名只使用最近观测标识、传感器标识、量测时刻、命中数和重放计数。
签名没有覆盖轨迹状态、协方差和后验有效时刻。delayed-noisy 场景在 finalization 阶段没有新
accepted observation，但 D1 仍传播了状态和协方差。运行时把变化后的后验误认为重复输入，
跳过 D2 最后一次消费并清空 pending。

该问题在原提交中属于 main 运行时的 P0 完整性阻塞。D6 不修改控制链，也不能用扩展计数式
将其降级为可用或 clean-formal。

## D6 判定

D6 离线评估 schema 升级为 `d6-scalable3d-offline-evaluation-v10`。声明 skip 时同时检查：

1. skip 计数只能为 1，且已有 D2 消费代次；
2. 尾部没有新接受观测、航迹更新、航迹创建或结构歧义；
3. 最后已消费后验与最终后验的航迹集合相同；
4. 每条航迹的完整公开载荷完全相同，包括状态、协方差、有效时刻和航迹状态；
5. 现有公共 payload 不包含完整 D2 输入元数据。即使前四项相等，也需要上游发布版本化完整
   D2 输入摘要并由 D6 独立复核，skip 才能进入正式守恒式。

当前 5 项均在第 4 项失败。D6 保留
`d2_final_consumed_generation_not_equal_d1_when_pending_empty`，并新增带最大差值的
`d2_finalize_unchanged_skip_full_posterior_not_equivalent`。正式资格继续为 false。

当前 producer 没有完整输入摘要。D6 对公开后验相等的合成用例也返回
`d2_finalize_unchanged_skip_complete_input_equivalence_unproven`，不会提前建立放行路径。

## 修复后定向复核

证据目录为 `/tmp/msm-r0-finalize-fix-20260725`，D6 合并结果位于其 `combined_d6` 子目录。
五项结果如下。

| 场景 | seed | D1 final | D2 consumed | consume | publication | merge | skip | pending | contract |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: | --- |
| delayed_noisy 20v20 | 1009 | 27 | 27 | 7 | 7 | 20 | 0 | empty | verified |
| delayed_noisy 5v5 | 1000 | 13 | 13 | 6 | 6 | 7 | 0 | empty | verified |
| delayed_noisy 5v5 | 1005 | 9 | 9 | 5 | 5 | 4 | 0 | empty | verified |
| delayed_noisy 5v5 | 1008 | 13 | 13 | 5 | 5 | 8 | 0 | empty | verified |
| delayed_noisy 5v5 | 1018 | 14 | 14 | 6 | 6 | 8 | 0 | empty | verified |

五项均满足 D1 final 等于 D2 consumed、consumption 等于 publication，以及
`consumption + merge == generation`。所有 generation integrity reasons 均为空。
本次通过来自 D2 实际消费最终后验，未使用 skip 特例，也没有放宽 D6 的完整输入等价要求。

D6 聚合仍给出：

- `episode_count=5`；
- `repository_dirty_episode_count=5`；
- `formal_acceptance_eligible_episode_count=0`；
- `episode_evidence_status_distribution={"descriptive_or_incomplete_evidence": 5}`；
- formal 失败原因仅为 `repository_dirty_not_formal_evidence` 和
  `episode_not_clean_formal_evidence`。

据此可确认 runtime P0 的错误跳过现象已在五项定向开发回归中消失。该结论不等同于正式关闭
R0 验收。旧 clean 提交的 895 项与新 dirty 工作树的 5 项不能组合成同一正式批次。

## 验收边界

`formal_scope_complete` 表示 900 个预登记单元全部执行、分片完整并通过文件级合并，不表示每个
episode 的算法证据均 clean。当前可以声明：

- R0 预登记范围执行完成：900/900；
- clean-formal episode：895/900；
- 异常 episode：5/900；
- 完整 5700-cell 实验矩阵：未执行，`formal_matrix_complete=false`。

当前不能声明 R0 的 900/900 clean formal acceptance，也不能把 895 个通过项外推为完整矩阵通过。

## 重跑范围

main 已完成上述 5 个 cell 的定向修复确认，D2 最终消费代次全部追平 D1，且 D6 未发现
generation contract 失败。该步骤只形成开发态修复证据。

正式替换结果需要在新的 clean 提交和新的执行计划下重跑全部 900 个 R0 cell。运行时修复会改变
D2 末尾状态，并可能传播到 D3、D4、D5 和 D7，不能把新提交的 5 个 cell 拼接到旧提交的 895 个
cell 中形成新的正式范围。新批次完成后由 D6 重新生成逐 episode CSV、聚合 JSON、中文报告和
曲线，验收目标为 900/900 clean-formal 且 generation-integrity 失败原因为空。

## 验证

2026-07-25 使用 D6 v10 逐条重读上述 5 个原始 episode。五项的 generation integrity、
基础 formal eligibility 和矩阵 formal eligibility 均为 false；最终代次不一致、完整后验
不等价和未验证处置守恒三类原因同时存在。

同日读取修复后的 5 个定向 episode。五项 generation integrity 均为 true，contract 状态均为
verified；基础和矩阵 formal eligibility 仍为 false，原因仅为 dirty/non-clean provenance。
这一区分证明 D6 同时保持了语义完整性门和正式来源门。

D6 全量回归为 `894 passed, 1 warning in 85.66s`。全量 `py_compile`、本次四个 Python
变更文件的 `pyflakes` 和限定路径 `git diff --check` 通过。全 D6 树的 `pyflakes` 仍报告
若干既有未使用导入、变量和重复定义，本轮未做无关清理。pytest warning 为本机 Matplotlib
`Axes3D` 包冲突，不影响本次二维报告或后验审计。
