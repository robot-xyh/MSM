# D4 A2 v8 来源可生成性复核

## 结论

第二个冻结 episode 的阻塞已关闭。修正后，真实 scalable runtime producer 连续生成
`sequence=0` 和 `sequence=1` 均成功，每项写入 3 帧，在线真值使用计数为 0。冻结日程的
低成本内存审计覆盖全部 324 个 episode、972 帧，未发现不可生成单元。

本次只修正 v8 来源证据合同与现行确定性资源投影器之间的预算口径。运行时投影器、
租约、版本、epoch、联盟确认、故障围栏和权限门没有放宽。数据生成、训练、验证集选择、
影子运行、接管、联盟、物理执行和控制权限仍未授予。

## 阻塞复现

冻结日程 `sequence=1` 条件如下：

- seed：`28101`；
- topology：`directed_ring_8`；
- supply/demand：`source_surplus_target_deficit`；
- communication：`nominal`；
- target class：`safe_forward_transfer`；
- requested transfer resource count：`2`。

真实 producer 产生 3 个区域帧。三个帧的匿名候选均可完成 `_d4_runtime_frame_evidence`
构造，候选边存在，候选转移 2 个资源也通过确定性投影。进入
`V8RuntimeEpisodeEvidenceBuilder.stage_frame` 后，三个帧分别在约 `0.75 s`、`1.0 s`、
`2.0 s` 被同一错误拒绝：`v8_r0_transfer_insufficient_source_surplus`。main 适配器对帧级
异常执行跳过，最终汇总为 `d4_no_qualifying_runtime_frames`。

`sequence=0` 请求 1 个资源并可通过，因此问题在第二个 episode 首次暴露。

## 根因

确定性资源投影器的硬预算为：

`可转移预算 = 可用资源 - 已承诺资源 - 储备资源`。

区域需求用于规则策略的压力、赤字和优化计算，不属于当前运行投影器的硬资源围栏。旧 v8
证据合同又从上述预算中扣除了区域需求，并用该净供需差校验规则基线和匿名候选。两套口径
不一致。`sequence=1` 中规则基线从另一区域转移 3 个资源，该区受保护预算为 3，净供需差为
2，因此实际投影器接受、v8 来源合同拒绝。

同一审计还发现，`balanced_boundary` 和
`global_shortage_with_local_candidate_edge` 单元会触发相同口径冲突。只修第二项无法保证
后续 322 个 episode 连续生成。

## 修正

v8 严格合同和运行证据构造器现按确定性投影器的受保护预算校验转移。供需差仍作为在线特征
保留，用于供需场景判定和学习输入。储备资源、已承诺资源、边容量、通信可用性、机动可用性、
owner、plan version、epoch、lease、联盟确认和故障围栏继续逐项检查。

readiness 新增全冻结单元可生成性审计。审计在内存中执行 D4 规则策略、确定性投影器、实际
证据 builder 和严格 DTO round-trip，不生成数据文件。任何单元失败都会使
`source_generation_request_ready` 失败关闭。生产者核心文件路径及 SHA-256 也写入请求
artifact，字节漂移会在生成前被拒绝。

收尾全量回归为 `1013 passed, 1 warning`，耗时 `112.25 s`；全目录 Python 语法编译通过。
唯一警告为既有 Matplotlib `Axes3D` 环境问题。

## 验证

| 项目 | 结果 |
| --- | --- |
| 冻结 episode | 324/324 可生成 |
| 审计帧 | 972 |
| 完整组合 | 324/324 |
| topology × target class × communication × count | 108/108 |
| 在线真值使用 | 0 |
| 单元证据 SHA-256 | `1cdb83e6...71dc2` |
| 审计内容 SHA-256 | `77e79e3c...ea7a6` |
| source request 文件 SHA-256 | `be5773fd...c4688` |

真实连续前缀复核使用相同 writer staging：第一次已有 `sequence=0`；修正后恢复 writer 并
生成 `sequence=1`。结果为 `completed_episode_count=2`，第二项 3 帧，在线/离线文件均写入
暂存目录，`online_truth_use_count=0`。该运行是 `/tmp` 下的诊断性 smoke，不属于正式 324
episode 来源，也不表示数据生成已获授权。

## 剩余限制

内存审计证明冻结聚合处理合同与 D4 builder 的 324 单元可生成性；真实 scalable runtime
连续前缀目前只覆盖 `sequence=0` 和 `sequence=1`。正式来源生成前仍需 main 在干净、固定
commit 的工作树重新执行统一 preflight 和 generation-only authorization。正式生成应继续
按小批次恢复，并由 D6 在训练前独立审计完整来源。
