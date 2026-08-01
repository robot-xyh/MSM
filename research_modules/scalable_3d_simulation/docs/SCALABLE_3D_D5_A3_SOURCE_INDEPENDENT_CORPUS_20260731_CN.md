# D5 A3 独立来源主动视觉语料验收

验证日期：2026-07-31

## 结论

本轮完成 100 个三维质点 episode 的主动视觉语料生成和最终封装。数据来源、文件完整性、
种子隔离和在线真值隔离均通过 D5/D6 检查，语料可用于后续仿真研究评价。D5 训练覆盖门
未通过，当前不能启动新的行为克隆训练，也不能晋级 A3 候选。

阻断原因集中在两类动作覆盖。训练集中没有 `hold` 示范，侦察相机没有
`search_sector` 示范。其余样本数量不能通过重采样、复制或权重调整替代这两个缺口。

## 数据生成

| 项目 | 结果 |
| --- | --- |
| 生产提交 | `4a8c1173179b4058d4aee38178e0fb40ecd222b3` |
| 生产工作树 | clean，`repository_dirty=false` |
| seed | `21000-21099`，共 100 个 |
| 正式保留 seed | `1000-1019`，重叠 0 |
| 场景 | 9 类 |
| 规模 | 5、20、50、100、200 |
| 场景-规模单元 | 45，每单元至少 2 个 episode |
| episode | 100/100，断点恢复 0 |
| 仿真时长 | 每 episode 3 秒 |
| 学习导出 | 仅 `d5_active_vision` |
| 在线真值使用 | 0 |
| 数据集 | 100 个 episode、159487 个样本、2001 个主动视觉帧 |
| 运行确认 | 159487/159487 接受 |
| 匿名观测键 | 159487/159487，重复 0 |
| 数据集大小 | 141555753 字节 |

生成总墙钟时间为 1033.661 秒。其中 episode 运行为 799.988 秒，制品暂存为
151.091 秒，最终封装为 80.922 秒。最终 checkpoint 状态为 `finalized`，没有 checkpoint
恢复或进度行恢复。

数据集 manifest SHA-256 为
`bccbdad42a71b130720469bb4e99dd1dd99e29a9b33af036679b9d64b0fe35a4`；split SHA-256 为
`aaad1f7d12f3d383e1d1a6d9160c534ad6a76c3281397cc421e893369cb761cd`；训练集 SHA-256 为
`4d2056c8e66f335a8a8ebf6843840ac9c9a60899263349aad222676301f15f35`。

## D5 语料门

D5 使用严格流式 loader 读取最终封装数据，并显式排除正式保留 seed `1000-1019`。
训练、验证和测试分别为 60、20、20 个 episode，样本分别为 102610、23458、33419。
三组 seed 互斥，159487 个样本全部通过结构校验，没有重复或排除样本。

训练集动作分布如下。

| 动作 | 样本 | episode | seed |
| --- | ---: | ---: | ---: |
| 观察目标 | 1795 | 31 | 31 |
| 重新捕获 | 98094 | 60 | 60 |
| 扇区搜索 | 2721 | 42 | 42 |
| 保持 | 0 | 0 | 0 |

训练集相机角色分布为拦截相机 98395 个样本、侦察相机 4215 个样本。侦察相机中，观察
目标为 68 个，重新捕获为 4147 个，扇区搜索和保持均为 0。拦截相机也没有保持示范。

D5 研究来源门状态为 `point_mass_simulation_research_eligible`，九项合同检查全部通过。
训练门状态为 `fail_closed_training_corpus`，语料审计内容 SHA-256 为
`85db29f86d924a437259a478e2fb182c220d3469c8f8a0c4374820e61e6ef74e`。
完整 D5 机器结果和中文报告见
[`../../d5_terminal_association/results/a3_source_independent_corpus_acceptance_20260731.json`](../../d5_terminal_association/results/a3_source_independent_corpus_acceptance_20260731.json)
和
[`../../d5_terminal_association/reports/D5_A3_SOURCE_INDEPENDENT_CORPUS_ACCEPTANCE_20260731_CN.md`](../../d5_terminal_association/reports/D5_A3_SOURCE_INDEPENDENT_CORPUS_ACCEPTANCE_20260731_CN.md)。

确定性补采计划包含三项：

1. 拦截相机的保持动作，至少使用 2 个新的训练 seed，形成 2 个 episode 和 2 个样本；
2. 侦察相机的保持动作，最低数量相同；
3. 侦察相机的扇区搜索动作，最低数量相同。

补采必须使用新的非正式训练 seed，继续排除验证、测试和正式保留 seed。必须采集完整新
episode，不能通过复制样本、过采样或重加权声称覆盖达标。

## D6 独立审计

D6 不调用 D5 validator，直接从 `SHA256SUMS`、manifest、episode descriptor 和 gzip
在线流复算来源证据。302 个制品、100 个来源身份和 whole-seed split 均通过审计；100 个
episode 全部来自 clean `4a8c117`，来源域均为
`scalable_3d_point_mass_runtime`，`synthetic_fixture` 数量为 0。

12 项检查全部通过，在线 truth、Actor 和 Object 标识计数均为 0。D6 状态为
`simulation_research_integrity_confirmed`。详细机器证据和中文报告见
[`../../d6_evaluation_metrics/reports/D5_A3_SOURCE_INDEPENDENT_POINT_MASS_AUDIT_20260731/`](../../d6_evaluation_metrics/reports/D5_A3_SOURCE_INDEPENDENT_POINT_MASS_AUDIT_20260731/)。

## 权限边界

本轮只确认质点仿真语料的来源和结构。AirSim 外部来源、真实相机来源、模型准入、在线
辅助、分配、降级、运行、生产、相机控制和 `global_track_id` 写权限全部保持关闭。四类
离线结果、反事实、因果和奖励标签均不可用。运行确认和匿名观测键完整，只能证明命令与
观测记录链存在；物理匿名观测帧仍不可用，不能据此计算主动视觉收益。

下一步只执行上述三类定向补采和重新审计。训练门通过后仍需来源独立评价、实际命令确认、
同键规则基线和物理非退化证据，才能讨论 A3 的影子运行资格。
