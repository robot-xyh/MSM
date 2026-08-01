# D1 多传感器融合与目标配准实施计划

## P1 在线发布证据子集快照正式拒绝与后续治理（2026-07-25）

### D1-owned 合同结论

现有 `FusionAdapter.consistency_evidence_snapshot(observation_ids)` 已由 main 接入
`required_observation_subset_v1`。本次二次复核确认接法符合 D1 合同，不修改 D1 源码或
测试。

1. `observation_ids=None` 保持全量在线快照；传入 iterable 时先校验全部 ID，再按集合语义
   去重并返回精确子集。未知 ID 抛出 `KeyError`，空字符串或非字符串抛出
   `ValueError`，异常发生在 pending ledger 投影之前。
2. 传入空 iterable 的 D1 语义是返回空快照。它不能判断“当前 publication 确实不需要证据”
   还是“main 漏建 required ID 集合”，因此空集合回退必须由 main selector 负责。
3. 子集快照只构造 detached replay-counter overlay，不写回
   `_consistency_evidence`，不删除 pending ledger。内部 ledger 的 observation ID 与来源航迹
   不一致时继续以 `RuntimeError` 失败关闭。
4. `consistency_evidence_records()` 继续全量精确物化 pending ledger；
   `export_consistency_evidence()` 继续调用该接口。最终离线导出的记录范围、排序和
   pending ledger 清零语义不变。
5. 2026-07-25 定向运行
   `test_replay_prefix_summary.py` 与 `test_consistency_evidence.py`，结果为
   `22 passed in 0.49s`。现有用例覆盖精确子集、未知 ID、非法空字符串、重复快照非破坏、
   append/迟到量测后的账本一致性和最终全量导出。空 required 集合、重复来源 ID、main
   fallback 与四表面诊断属于新 selector 的集成测试，不作为 D1 API 改动。

### 独立候选边界

1. treatment 名称保持
   `d1_publication_evidence_snapshot_implementation`。reference 为
   `full_consistency_snapshot_v1`，candidate 为
   `required_observation_subset_v1`。第一轮两臂均固定使用 replay-prefix reference
   `per_checkpoint_prefix_rebuild_v1`，不能同时改变两个 selector。
2. required ID 只由 main 在同一 release cycle 内从当前 source observations 的
   observation ID，以及已物化公开航迹的 `latest_observation_id` 形成。main 负责去重、
   排序、完整性和 publication 所有权治理；D1 不读取真值、目标真实编号或 D6 标签，也不
   反向推导该集合。
3. required 集合为空、含未知 ID 或未通过 main 完整性/所有权检查时，main 必须回退
   `full_consistency_snapshot_v1` 并记录原因。D1 的 `KeyError`/`ValueError` 为回退提供
   明确信号；正式矩阵要求 candidate fallback 和 lookup miss 均为 0。
4. 最终 offline export 仍全量调用 `consistency_evidence_records()` 或
   `export_consistency_evidence()`。候选不改 `global_track_id`、双时间戳、协方差、NED、
   fixed-lag、门控、来源谱系或业务 payload hash。

### 实现与候选形成证据

main 集成实现与回归已经完成：

1. `IntegratedStackConfig` 和 CLI 已接入 selector，默认保持
   `full_consistency_snapshot_v1`；非法 selector 在配置入口拒绝。
2. main 从同一 release cycle 的 source observations 和 materialized tracks 的
   `latest_observation_id` 收集 ID，完成去重与字符串排序。candidate 对空集、未知/非法 ID
   或返回子集缺项回退 full snapshot，并记录固定原因。
3. selector、execution config 和 diagnostics 已进入 runtime profile、observation
   governance、module final 与 episode summary。诊断记录 selection、publication、两类
   引用、去重、required ID、adapter 调用、返回记录、fallback、lookup miss 和守恒。
4. `3 target/3 resource/1 recon`、1.4 秒、seed 34 的确定性模块栈 episode 中，
   candidate `fallback=0`、`lookup miss=0`，`modules.d1.fused_tracks` payload 与 reference
   完全一致；unknown-ID 与空 required 集合专项均确认回退 full 并记录原因。
5. D1 owner 复跑 `test_module_stack.py` 得到 `62 passed, 1 warning`，复跑 scalable
   全量得到 `263 passed, 1 warning`；警告是既有 Matplotlib `Axes3D` 环境提示。此前 D1
   snapshot/replay-prefix 定向测试仍为 `22 passed in 0.49s`。
6. 2026-07-25 在 detached clean commit
   `028ac34debcfc5ca6ed2f6f88a5868d7b5f0f67b` 上完成一对 200/200/2、seed 1151、
   2.2 秒、2028 条在线观测的 smoke。两臂均为有限状态，在线真值使用为 0；D1/D2 在线
   记录 SHA-256、consistency count/digest 和原 D1 operation counts 严格一致。
7. candidate 14/14 次选择命中子集快照，fallback、lookup miss、非法 ID 和空 required
   集合均为 0。累计返回记录由 `13679` 降为 `4429`，削减 `67.621902%`；最终离线
   consistency 仍全量导出 2028 条。
8. 单 pair 的 D1、module stack、episode 和外部命令计时方向混合，实时因子约
   `0.265 < 1`。该数据只证明 clean smoke 语义与工作量边界，不用于性能晋升。

### 正式判定

D6 已对 producer clean commit
`d0219eb14c529a4fb9bf7d6610a9f32055a09206` 和 matrix SHA-256
`6c808c4df8759fd893c6d37ff9dce4a1efa07f9867fc71aff47a55c5f8517338`
完成独立评估。冻结矩阵包含 200 个目标、200 个资源和 2 个侦察节点；short seeds
1151-1160 各 2.2 秒，long seeds 1151-1153 各 10 秒，共 13 pair/26 个 fresh
episode，0 reused、0 failed。

13/13 pair 的业务语义、有限状态、在线真值使用为 0、实现身份、D1/D2 在线记录、
consistency digest/count、原 D1 operation counts 和诊断审计全部通过。candidate
429/429 次子集选择成功，fallback、lookup miss、非法 ID 和空 required 集合均为 0。
累计返回记录由 `1602170` 降为 `133917`，削减 `91.641524%`，超过 `>=50%` 冻结门。

正式 verdict 为 `reject`，`main_default_promotion_allowed=false`。失败门如下。

| 冻结性能门 | 正式结果 | 阈值 | 判定 |
| --- | ---: | ---: | --- |
| Short candidate 更快数 | `4/10` | `>=8/10` | 失败 |
| Short D1 fusion 改善 | `-0.147877%` | `>=1%` | 失败 |
| Short paired bootstrap 相对变化 95% 上界 | `1.374681%` | `<=0%` | 失败 |

long candidate 更快 `2/3`，long D1 改善 `1.047143%`，short/long core 改善
`0.330057%/0.837777%`，D2/RSS 守门通过。这些通过项不能覆盖短时失败门。candidate
最低 RTF 为 `0.203423 < 1`，系统实时 P1 独立保持开放。

### 后续状态

本候选准入流程已审结。candidate `required_observation_subset_v1` 保留为默认关闭的研究
入口，reference `full_consistency_snapshot_v1` 保持默认，最终 offline export 继续全量。
内部返回对象工作量削减已经证实，短时端到端收益不稳定。未来若继续治理该热点，必须使用
新的实现身份、预注册矩阵和 D6 独立判定，不得调低本轮门限、删除失败 pair 或覆盖
`reject`。系统实时、AirSim、目标硬件、实机、实飞、RMSE、NEES 和 NIS 继续作为开放 P1。

## P1 固定滞后回放前缀累计摘要正式拒绝与后续计划（2026-07-25）

### 正式判定

D6 已对 producer clean commit
`7d2e987471b521a1e531bf03a5c99af5096f676a` 和 matrix SHA-256
`85432d729877eff97e6f3dd517d4baa7a47f44a4fa42e6bfdc7ce85b8d9ec74b`
完成独立评估。冻结场景为 200 个目标、200 个资源和 2 个侦察节点；short seeds
1151-1160 各 2.2 秒，long seeds 1151-1153 各 10 秒，共 13 pair/26 个 fresh
episode，0 reused、0 failed。

正式 verdict 为 `reject`，`main_default_promotion_allowed=false`，
`system_realtime_gap_closed=false`。失败门如下。

| 冻结性能门 | 正式结果 | 阈值 | 判定 |
| --- | ---: | ---: | --- |
| Short candidate 更快数 | `5/10` | `>=8/10` | 失败 |
| Short D1 fusion 改善 | `0.959611%` | `>=1%` | 失败 |
| Short paired bootstrap 相对变化 95% 上界 | `0.619827%` | `<=0%` | 失败 |
| Short core 改善 | `-0.256641%` | `>=0.25%` | 失败 |
| Long core 改善 | `-1.930083%` | `>=0.25%` | 失败 |

13/13 业务语义、consistency evidence digest/count、原 D1 operation counts、实现身份、
诊断守恒和在线真值隔离通过。long D1 fusion 改善 `2.361778%`，内部物化记录减少
`52.150746%`，RSS 与 D2 均值门通过。候选最低 RTF 为 `0.197441`；在线 snapshot
投影构造 `656481` 条记录。局部语义和工作量门通过不能覆盖端到端性能门失败。

reference `per_checkpoint_prefix_rebuild_v1` 继续作为 D1 和 main 默认。
candidate `fixed_lag_checkpoint_prefix_cumulative_summary_v1` 保留为默认关闭的研究入口，
不得删除，也不得声称已晋升。本正式结论只覆盖三维质点仿真，不覆盖 AirSim、目标硬件、
实机、实飞或正式 RMSE/NEES/NIS。

### 目标与边界

当前 `_replay_record()` 已复用 checkpoint 后验，但会对可信前缀逐条重建 NIS、门控
observation ID，并逐条刷新 consistency evidence 的回放计数。本阶段只减少该重复工作，
不改变 6 秒固定滞后窗口、观测集合、预测/更新公式、协方差、双时间戳、门控、NED、
`global_track_id`、传感器频率或任何 PN/PNG 控制。

声明默认保持 `per_checkpoint_prefix_rebuild_v1`。研究候选为
`fixed_lag_checkpoint_prefix_cumulative_summary_v1`，必须显式选择。候选 schema、
实现 ID、诊断和报告均独立于已否决的关联稀疏预筛候选。

### 已完成实现

1. 每条航迹维护冻结 `_ReplayPrefixSummary`。摘要包含 checkpoint 修订、顺序身份、
   累计 NIS、门控 ID、一致性 observation 顺序和证据结构修订；字段均为标量或 tuple。
2. 只有完整 checkpoint 前缀、首尾身份/顺序、checkpoint 修订、summary schema、
   consistency 结构修订和当前 replay context 全部一致时才命中。
3. `replay_checkpoint_revision` 作为完整中间 checkpoint 前缀的 O(1) 确定性完整性边界。
   内部清空、截断、重排或 fixed-lag 后缀替换通过破坏性变更门，先物化未决 evidence，
   再递增 revision 并清除旧 summary。正常 append-only 后缀追加走安全特例：revision 仍
   推进、summary 仍失效，但只覆盖旧前缀且对象绑定一致的 ledger 保留。新 ID 重叠、排序
   非严格后移或绑定不一致均立即物化。中间插入观测先按排序键失效受影响后缀。
4. 一致性回放计数采用独立的前缀长度区间账本。每次命中记录覆盖长度和 replay revision，
   evidence 写入、前缀失配、失效、fixed-lag 重基准或最终导出前精确物化。该账本不与
   冻结 summary 共享可变对象。
5. 部分前缀、无 checkpoint、schema/version 失配、修订或身份变化、禁用 consistency
   cache 等条件均回退原逐条路径。回退前先物化未决 evidence 计数。
6. 新 diagnostics v1 记录 attempt/hit/fallback、fallback 原因、摘要构建、复用
   checkpoint/NIS、逻辑 consistency 刷新、append-only 保留、在线投影和物化原因。既有
   operation counts 保持原数值。
7. `consistency_evidence_records()` 保留全量精确物化兼容语义；
   `export_consistency_evidence()` 继续用它完成最终离线导出。新增
   `consistency_evidence_snapshot(observation_ids=None)`，对 pending ledger 做非破坏性
   counter overlay，每次返回精确不可变记录。可选 ID 只限制返回记录构造；未知 ID
   失败关闭。

### Integrated smoke 暴露问题与修复

main 第一次 dirty smoke（200v200、2 个侦察节点、seed 1151、2.2 s）中，candidate 有
1,584 次 summary hit 和 7,103 次 checkpoint 复用，但 1,584 次正常 append 全部触发
pending ledger 物化。逻辑刷新与物化记录均为 8,687，压缩率为 0；两臂 consistency
digest 相同。根因是 append 与截断共用破坏性变更门。

修复后，append-only 只在旧 summary 已命中、pending IDs 与 summary tuple 对象绑定一致、
新 ID 不重叠且排序严格后移时保留 ledger。下一次 summary 命中通过既有兼容前缀扩展规则
扩展 ledger。

main 独立复跑得到 `summary_hit=1584`、`reused=7103`、`logical=8687`、
`materialized=7013`，append 物化为 0，压缩率 `19.27017%`。剩余物化原因全为
`public_evidence_snapshot`，共 1,372 个 ledger。两臂 consistency digest 均为
`sha256:b579e62b65169791a1c9526eb5310ba7016149ddd501efe34e82a732c8bbda3a`，
reference/candidate D1 fusion 为 `2.40147/2.30535 s`。该历史 smoke 证明 append 修复
有效，也记录了当时 main 在线 publication 仍调用兼容全量 records 接口。后续正式矩阵
已经改用非破坏性 snapshot，但仍请求全量 evidence。

### 冻结模块微基准

fixture 为 `d1-replay-prefix-summary-200v200-20260725`，SHA-256
`sha256:4e7fcb00432fc4c6736b5ba301d06363e73357fc91689618b6ddab0b1307490e`；
派生的 1,600 条观测 SHA-256 为
`sha256:b44f971c2c6ac9b519cb7aba3f8df455727382132b2c5ec127280c97806dbae9`。
规模为 200 目标、200 资源、2 侦察节点、8 个扫描。每个新鲜 arm 在建轨后执行 5 轮完整
回放和一次 evidence 公开物化；建轨阶段每个扫描后读取一次精确非破坏性 snapshot。
online truth use=0。reference/candidate 同输入、同导入源码状态，7 对交替运行。

| 模块门 | 结果 | 阈值 | 判定 |
| --- | ---: | ---: | --- |
| Candidate 更快 | `7/7` | `>=80%`，且至少 5 对 | 通过 |
| 中位墙钟 | `0.039559965 -> 0.025518551 s` | 改善 `>=5%` | `35.494%`，通过 |
| 配对均值差 bootstrap 95% 上界 | `-0.013135232 s` | `<0 s` | 通过 |
| Append 物化记录压缩率 | `53.846%` | `>=20%` | 通过 |
| 在线 snapshot 内部物化 | `0` | `0` | 通过 |
| 精确语义门 | `7/7` | `7/7` | 通过 |

精确语义门覆盖后验、协方差、NIS、门控 ID、consistency evidence、既有操作计数、
逐扫描 snapshot 序列、双时间戳与 gate metadata、checkpoint 和公开 `GlobalTrack`。
candidate 每个 arm 有
1,000 次 summary hit、6,000 个 checkpoint/NIS 复用、6,000 条逻辑 evidence 刷新；
最终物化 1,200 条 evidence，计时段 fallback 为 0。D1 全量回归
`488 passed in 30.96s`。

冻结 append 建轨阶段每个 arm 的 revision 推进、pending 保留、逻辑刷新和物化记录分别为
`1400/1200/5200/2400`。正常 append 物化为 0，fixed-lag rebase 与 summary fallback
各 200 次；全部 summary 绑定最新 revision。8 次在线 snapshot 中 4 次投影 pending，
累计涉及 800 个 ledger、2,000 个事件和 2,800 条返回记录，内部物化为 0。投影记录数作为
实际工作量单列，不计入内部物化压缩。

冻结 fixture 前 3 个扫描派生的 0-2 秒 200v200 负载中，逻辑刷新 400 条、内部物化 0，
压缩率 100%；一次有效 snapshot 投影 200 个 ledger、400 条返回记录。最终 records 调用后
pending 为 0。该短时模块结果通过 `>=20%` 门，但不能替代 main 改接后的同配置复跑。

专项新增中间顺序破坏回归：在四个 checkpoint 的中间插入迟到观测，验证失效路径先截断
受影响后缀并推进 revision，随后按新顺序重建 summary；reference/candidate 的内部状态、
公开输出和既有操作计数保持一致。

### 当前判定与下一候选

模块微基准通过是历史候选形成证据，正式准入已经以 `reject` 审结。正式矩阵中的 main
在线 publication 已调用非破坏性 snapshot，最终 offline export 继续使用
`consistency_evidence_records()` 或 `export_consistency_evidence()`；最终 pending
ledger 为 0。当前在线 snapshot 仍请求全量 evidence，累计投影构造 `656481` 条记录，
是后续性能工作的直接线索。

该独立候选已完成 main 集成实现和正式评估，继续保持以下边界：

1. 冻结 publication 到 observation ID 集合的来源和所有权合同，未知 ID、空 ID、
   跨航迹 ID 或证据所有权不一致继续失败关闭；
2. 只构造本次 publication 消费的不可变 evidence 记录，最终 offline export 仍保持
   全量 records/export 和 pending ledger 清零语义；
3. 不改变 fixed-lag 窗口、观测顺序、NIS、门控、协方差、双时间戳、NED、
   `global_track_id`、既有 operation counts 或在线真值隔离；
4. 使用新的 selector、implementation ID、execution config、diagnostics 和报告 schema，
   与本次被拒候选完全分离；
5. 正式 short/long 矩阵和 D6 独立判定已经完成。不得复用任一历史 matrix SHA、调低门限、
   删除失败 pair 或覆盖冻结结论。

main selector、调用点、执行配置、诊断、CLI、模块栈回归、clean 200/200/2 smoke 和正式
矩阵均已完成。D6 对本候选给出 `reject`；reference 保持默认。系统实时因子、AirSim、
目标硬件、实机、实飞、RMSE、NEES 和 NIS 继续作为开放 P1，本候选最低 RTF
`0.203423 < 1`，不能写成实时闭合。

## P1 模态感知保守稀疏预筛正式拒绝与研究入口治理（2026-07-25）

### 正式判定（已完成）

D6 schema `d6.d1_association_sparse_prefilter_multiseed_evaluation.v1` 绑定 clean source
commit `9302ccede2ca513c2235370e1a464fc88bc41150` 和 matrix SHA-256
`a7162d014d1c3c0f207355b24a5d7159bf3486d134ca21876f7469d1e915b71d`。冻结矩阵为
200 个目标、200 个资源、2 个侦察节点，short seeds 1131-1140、long seeds 1131-1133，
共 13 pair/26 个 fresh episode。13/13 业务语义、有限状态、online truth use=0、实现身份
和逐模态 exact gate-pass 相等均通过。

| 冻结性能门 | 正式结果 | 阈值 | 判定 |
| --- | ---: | ---: | --- |
| Short candidate 更快数 | `7/10` | `>=8/10` | 失败 |
| Short D1 fusion 改善 | `0.228437%` | `>=1%` | 失败 |
| Short paired bootstrap 原始变化 95% 上界 | `0.443531%` | `<=0%` | 失败 |
| Short core 改善 | `0.091096%` | `>=0.25%` | 失败 |
| Long D1 fusion 改善 | `0.713776%` | `>=1%` | 失败 |

非雷达精确求解由 `298109` 降至 `39837`，削减 `86.636767%`；这只证明候选减少局部精确
求解，不能覆盖五个端到端性能门失败。正式 verdict 为 `reject`，
`optimization_admitted=false`、`main_default_promotion_allowed=false`。

### 默认与冻结治理

1. `disabled_v1` 继续作为声明默认和 main 默认；不修改 selector 默认值。
2. `modality_conservative_quadratic_bound_v1` 只保留为显式研究入口，不进入默认生产路径。
3. source commit、matrix SHA、13 pair/26 episode、门限和正式制品保持冻结，不删除失败
   pair、不重解释 bootstrap，也不以局部精确求解削减替代准入。
4. 本候选的正式准入流程已以 `reject` 审结。未来若提出不同候选或重新准入，必须建立新的
   预注册矩阵并保留本轮拒绝记录，不能覆盖或追溯修改本轮 verdict。

### 已完成模块工作（历史）

1. 新增 reference `disabled_v1` 和默认关闭 candidate
   `modality_conservative_quadratic_bound_v1`；未显式选择时保持 reference。
2. reference 恢复并锁定原四维非雷达批量伪逆和操作顺序。候选路径可单参数启用和回滚，
   不改精确门限、匈牙利分配、航迹状态、协方差、双时间戳、NED、谱系或
   `global_track_id`。
3. 雷达/LiDAR 使用笛卡尔残差，声学使用精确角度环绕残差，光电使用精确投影像素残差。
   只在创新协方差有限、严格对称、严格正定且不会触发旧 `pinv` 截断时使用谱上界下界。
4. 无法证明的 pair fail-open 到原精确求解。奇异、近奇异、非有限和未知模态不作启发式
   删除。
5. execution config schema 为
   `d1.association_sparse_prefilter_execution_config.v1`；固定诊断 schema
   `d1.association_sparse_prefilter_diagnostics.v2` 按
   `radar/lidar/acoustic/acoustic_3d/eo/other` 输出候选对、预筛剔除、精确求解、
   精确门内通过和 fallback，不含真值。

### 历史模块微基准

120 航迹微基准每模态含 14,400 个 pair，每变体预热 1 次并交错 7 次。LiDAR、二维声学、
三维声学和光电合计 P50 `0.538083 -> 0.487310 s`，改善 `9.436%`。精确求解减少率分别为
`78.292%/56.208%/56.208%/77.118%`；LiDAR/二维声学/三维声学/光电分别
`7/7、6/7、7/7、7/7` 更快。雷达保留已准入旧下界，selector 不增加雷达求解削减且本轮
P50 慢 `0.221%`。五类规范输出和精确门内 pair 完全一致，正常输入 fallback 为 0；
D1 全量 `473 passed in 24.45s`。

该微基准只记录候选形成时的模块级结果，不是主线准入证据；正式状态以上述 D6
`reject` 为准。

### 剩余开放项

1. 候选最低 RTF 为 `0.206273 < 1`，`system_realtime_gap_closed=false`；完整 200v200
   系统实时 P1 未关闭。
2. 当前证据仅覆盖三维质点仿真。AirSim、目标处理器、硬件、实机、实飞、RMSE、NEES 和
   NIS 继续独立开放。
3. 保持 candidate-on/off 安全等价、诊断守恒和 explicit-only 入口回归，但不安排本候选的
   默认提升。

## P1 默认 R0 在线批次到扫描帧正式准入与默认提升（2026-07-25）

### 正式证据与决策

D6 schema `d6.d1_online_batch_frame_multiseed_evaluation.v1` 绑定 source commit
`43feaf600f288a85ce76a76862334256f0d0d352` 和 matrix SHA-256
`4afbf9ac273763a16aa01cc744fd67b52e437099460b33377a128f986ac5719b`。冻结矩阵包含
short 10 pair、long 3 pair，共 13 pair/26 episode；全部预注册 gate 通过。

| 指标 | Short | Long |
| --- | ---: | ---: |
| scan-input 改善 | `38.289241%` | `36.275282%` |
| core wall 改善 | `4.252745%` | `4.916501%` |
| candidate 更快 | `10/10` | `3/3` |

candidate closed handoff 为 `2665/2665`，fallback 为 0，online truth use 为 0。业务
语义、实现身份、有限状态、审计守恒、RSS 和 D2 均值门全部通过，D6 结论为 `admit`。

### 默认与回退治理

1. `ONLINE_BATCH_FRAME_DEFAULT_IMPLEMENTATION` 设为
   `closed_immutable_batch_to_frame_v1`。
2. `OnlineBatchFrameBuilder()` 和 `sensor_scan_frame_from_online_batch()` 的未显式
   selector 路径统一使用 candidate。
3. `implementation=ONLINE_BATCH_FRAME_REFERENCE_IMPLEMENTATION` 是单参数 reference
   回退，稳定实现 ID 仍为 `d1.online_batch_frame.convert_then_frame.v1`。
4. `candidate_default_enabled` 按当前声明默认值记录为 true；显式 reference 仍记录其
   selector、实现 ID、reference 路径计数和守恒。
5. 不改变候选核心算法、raw batch 与最终帧完整检查、普通异常 fallback、`MemoryError`
   失败关闭、协方差、双时间戳、NED、谱系或融合门控。

### 剩余工作

1. 系统实时 P1 保持开放：candidate 最低 RTF 为 `0.204490 < 1.0`，不能写成 200v200
   实时已闭合。
2. D2 均值门通过，但单 pair 尾部需要长时容量观察：`short_seed_1125` 增幅
   `15.778858%`，`long_seed_1121` 增幅 `14.408510%`。
3. AirSim、目标硬件、实机、实飞、RMSE、NEES 和 NIS 继续独立验收。本轮没有改变 AirSim
   producer、DTO、runtime bus、坐标、时间或 episode 接口。
4. 冻结 matrix/config、正式 D6 制品和下述准入前微基准历史解释保持不变。

## 历史：默认 R0 在线批次到扫描帧封闭交接候选（2026-07-25）

### 选题与范围

main 的默认无 source-key R0、200v200、2.2 s、seed 1112 开发 cProfile 含 95 个 batch
和 2,044 条 observation。在线观测集合检查共 190 次、累计 `2.236763 s`，其中 converter
和 `SensorScanFrame` 各 95 次、分别累计 `1.120932/1.115831 s`。
`SensorScanFrame.__post_init__` 累计 `1.397623 s`。raw payload 检查共 2,139 次、
`0.403673 s`，其中逐 measurement 2,044 次、`0.206688 s`，整 batch 95 次、
`0.196985 s`。

本轮只合并已经由整批递归检查和最终帧检查覆盖的重复遍历，不改观测数学、协方差、双时间戳、
NED、谱系、扫描一致性、门控或融合器。公开转换 API 保持原行为。

### 已实现候选

1. reference 选择器为 `convert_then_frame_v1`，实现 ID
   `d1.online_batch_frame.convert_then_frame.v1`，在该准入前阶段保持默认。
2. candidate 选择器为 `closed_immutable_batch_to_frame_v1`，实现 ID
   `d1.online_batch_frame.closed_immutable_batch_final_frame_validation.v1`，在该
   准入前阶段默认关闭。
3. 候选入口先完整检查 raw batch；冻结数据类、独立只读数组和受支持元数据通过结构合格
   检查后，才进入模块内部深快照和私有转换链。该检查不声明 raw 来源绝对不可变。
4. `SensorScanFrame` 对最终只读快照执行完整检查。普通映射和结构不合格载荷回退 reference；
   结构检查或快照中的普通异常明确记账并回退 reference，`MemoryError` 记账后原样拒绝。
5. `OnlineBatchFrameBuilder` 发布稳定实现 ID、固定操作计数和守恒诊断。调用者不能传入
   已验证状态，也没有公开跳过检查参数。

### 模块验收

冻结微基准使用 200 条 measurement、7 次交错采样。预注册门槛为中位墙钟改善
`>=20%`、candidate 更快比例 `>=70%`，并要求规范帧 SHA-256、正负异常摘要和操作计数
守恒全部一致。

| 指标 | Reference | Candidate |
| --- | ---: | ---: |
| 中位墙钟 | `0.089842 s` | `0.050648 s` |
| 中位改善 | - | `43.625675%` |
| 中位加速比 | - | `1.773857x` |
| 配对更快 | - | `7/7` |
| 整批 raw 检查 | 7 | 7 |
| 逐 measurement 重复 raw 检查 | 1,400 | 0 |
| 转换后集合重复检查 | 7 | 0 |
| 最终 frame 检查 | 7 | 7 |

规范帧 SHA-256 为
`7b46fdc8beecb130914c1026fdc3d476ab6f94b53a33e76db3edcc188fdff83b`。
合法输出、5 个 batch 字段和 11 个 measurement 字段传播、身份泄漏、坏协方差、双时间戳
冲突、sensor/batch/模态不一致、重复 observation ID、重复 lineage、普通映射回退、变异
自定义载荷拒绝、快照 `RuntimeError` 回退、`MemoryError` 拒绝和快照突变隔离均已回归。
专项 `19 passed`，main 当时复跑 D1 全量为 `443 passed in 24.02s`。该历史阶段只能标记
“D1 模块门槛通过”，不能标记 main 全栈准入；当前正式结论以上一节为准。

### 后续边界

1. 该准入前阶段要求 main 只能显式选择 candidate，并持久化同一 builder 的实现配置、
   操作计数和守恒诊断；它不描述当前默认值。
2. main 应在 clean 同提交的默认无 source-key R0 short/long 多 seed 矩阵中比较 D1、
   scan-input、D2、核心墙钟、内存和业务语义，再由 D6 独立判定。
3. malformed/custom/mutating 输入若不能通过当前结构检查和完整校验，继续回退或拒绝，
   不扩大候选载荷范围；不把 frozen 或 mapping proxy 解释为绝对不可变。
4. 系统实时、AirSim、目标硬件、实飞、RMSE、NEES 和 NIS 保持开放，模块微基准不能替代。

## P1 不透明来源标识缓存正式拒绝与后续治理（2026-07-25）

### 候选范围

main 的 clean `cd9c60c` profile 表明，关闭 source-key/hold 时
`process_scan_batch/global_tracks` 为 `4.852/0.633 s`；显式 source-only 时为
`5.796/1.501 s`，`_to_global_track` 为 `1.314 s`。成员 token、source track ID 和 source
key 的累计耗时为 `0.245/0.294/0.337 s`。本轮只处理这组三字符串，不扩展为整棵 metadata
缓存，也不改 A95、状态、协方差、重放或共享审计树。

候选实现 ID 为
`d1.publication.opaque_source_identity.bounded_generation_lru.v1`，reference 为
`d1.publication.opaque_source_identity.per_publication_build.v1`。显式选择器
`cached_opaque_source_identity` 默认关闭。键包含 publisher node、publisher epoch 和 D1
track ID；容量默认 1,024、最大 4,096。节点/epoch 变化自动清空旧代际，episode reset 可
显式清空。未满足精确字符串键合同的调用回到 reference。缓存项只含不可变字符串。

### 已完成验收

2026-07-25 模块基准显式开启 source-only、关闭 hold，采用 200 条航迹、每样本 56 次发布、
每轮 11,200 次物化，预热后交错 7 轮。reference/candidate 中位墙钟为
`0.348622/0.127734 s`，改善 `63.360%`、加速 `2.729x`，candidate `7/7` 更快。
标识构造由 `78,800` 降至 `200`，候选命中/未命中为 `78,600/200`。预注册的中位改善
`>=2%` 和更快比例 `>=70%` 均通过。

逐发布 `GlobalTrack.to_dict()`、state、covariance、metadata、来源、身份和诊断语义相同。
状态、协方差、timestamp、A95、分级、last NIS 和全部本轮变化字段仍重新生成。别名隔离、
节点/epoch/reset 失效、容量驱逐、OOSM/重放/新生/移除和固定大小计数守恒已覆盖。D1 全量
回归为 `424 passed in 21.81s`。

### 正式矩阵与拒绝结论

main 已在 clean source commit
`d8fc76c066f21b077154f7be33c0b43558d237e5` 上接入 reference/candidate selector、实现
ID 和固定大小诊断。正式矩阵只启用 source-only 发布并保持 structural ambiguity
hold=false。short 10 pair 和 long 3 pair 共形成 26 个 fresh arm，`0 reused/0 failed`。
D6 已完成独立失败关闭评估。

| 组别 | D1 融合改善 | 核心墙钟改善 | Candidate 更快 | D2 关联耗时增幅 |
| --- | ---: | ---: | ---: | ---: |
| short | `9.465972%` | `2.845610%` | `10/10` | `4.677567%` |
| long | `6.437432%` | `2.728043%` | `3/3` | `5.605213%` |

全矩阵标识构造由 `312,317` 次降至 `2,612` 次，构造减少率和缓存命中率均为
`99.163670%`。19 个准入门通过 18 个。long D2 关联耗时增幅要求 `<=5%`，实际为
`5.605213%`；`long_seed_1101` 增幅为 `19.069868%`。该 seed 保留在正式统计中，冻结门限
不调整。

D6 判定 `optimization_admitted=false`。本候选的集成准入已经审结，不再处于等待状态。
`bounded_generation_lru_v1` 不晋级；D1 独立构造默认继续为
`cached_opaque_source_identity=False`，main 默认继续选择 `per_publication_build_v1`。

### 后续治理

1. 保留 candidate 作为显式、默认关闭的研究对照，保持 reference、selector、实现身份、
   缓存守恒、业务语义和在线真值隔离回归。
2. 不删除 `long_seed_1101`，不放宽 `5%` D2 门，不以局部 D1 收益覆盖下游回归。
3. 若后续复核 D2 长时波动，必须建立新的预注册确认矩阵；本轮拒绝结论保持不变。
4. 系统实时 P1 继续开放。候选最低实时因子为 `0.193887`，未达到 `>=1.0`。
5. 正式证据只覆盖显式 source-only、hold=false 的三维质点运行面，不能外推到默认无
   source-key R0、AirSim、目标硬件、实飞、RMSE、NEES 或 NIS。

## P1 结构稀疏数值雅可比正式准入结果（2026-07-25）

### 正式矩阵

main 已在 clean commit
`9d1f54f8540fdc4a7a1011121aafac5718290122` 完成 reference/candidate 同提交接线。
D6 对冻结矩阵执行独立失败关闭评估。矩阵含 200 个目标、200 个资源和 2 个侦察节点；
short 10 pair 每臂 2.2 s，long 3 pair 每臂 10 s，共 26 个 fresh arm。
`26/26 complete`、`0 reused`、`0 failed`，全部来源、业务语义、有限状态、在线真值隔离、
实现身份和结构操作数准入门通过。

short 的 D1 融合与核心墙钟改善为 `6.084778%/1.897370%`，candidate `10/10` 更快；
long 为 `4.676061%/1.786530%`，candidate `3/3` 更快。量测函数求值减少
`53.846154%`。D6 输出 `availability=true`、`optimization_admitted=true`。
2026-07-25 D1 全量回归为 `414 passed in 21.52s`。

### 准入与默认边界

结构稀疏数值雅可比在 scalable 3D main 集成中的候选准入 P1 已关闭。reference 必须继续
保留为显式回退和同输入对照。D1 独立
`FusionAdapter(structured_numerical_jacobian=False)` 默认不变，显式 `True` 可用。
main 已完成后续版本治理：scalable 3D 的 `IntegratedStackConfig` 与 `run_episode` 命令行
默认均晋级为 `known_dimension_structural_columns_v1`，`dense_output_probe_v1` 可显式
回退。2v2 默认 smoke 的 observation governance、episode summary 和 module final
diagnostics 三个表面均记录候选，状态有限且在线真值使用为 0。

上述默认晋级只属于 scalable 3D main 集成。D1 独立 `FusionAdapter` 的构造默认仍为
`structured_numerical_jacobian=False`，没有随 main 默认一起改变。2v2 smoke 只关闭默认
接线回归，不形成 AirSim、目标硬件或实飞证据。

### 后续 P1

1. 系统实时 P1 保持开放。当前最低实时因子为 `0.180726`，未达到 `>=1.0`。
2. 使用冻结 AirSim 输入执行同实现 A/B，并在目标处理器上测量周期、尾延时和内存。
3. 补充 RMSE、NEES、NIS 和长时容量证据；质点性能不得替代融合质量验收。
4. 保持双时间戳、NED、协方差、fixed-lag/OOSM、在线真值隔离和实现身份回归。

## P1 结构稀疏数值雅可比模块候选基线（2026-07-24）

### 问题与选型

main 的 200v200、2.2 s、seed 1111 默认路径 cProfile 显示
`numerical_jacobian` 累计 `0.712 s`。同轮 `_scan_one_to_one_assignments` 和
`_cached_non_radar_scan_cost_matrix` 为 `1.194/0.918 s`。现有扫描模型缓存已将同一扫描
几何的投影和雅可比压到每航迹一次，非雷达创新伪逆也已批处理，继续做相同缓存会重复既有
工作。观测模型定义进一步表明，声学、光电、激光雷达和无径向速度雷达的雅可比后三列恒为
零，通用六列中心差分仍在重复调用观测方程。

本轮只实现一个候选：

1. reference 保留现有输出探测和六列中心差分，ID 为
   `d1.ekf.numerical_jacobian.dense_output_probe.v1`；
2. candidate 使用已知输出维数和模型声明的活动列，ID 为
   `d1.ekf.numerical_jacobian.known_dimension_structural_columns.v1`；
3. 活动列继续使用原 `eps=1e-5`、相对步长、正负扰动和除法顺序；非活动列为精确零；
4. 四维含径向速度雷达保留全部六列，其他当前模型使用位置三列；
5. `structured_numerical_jacobian=False` 保持 D1 独立默认，不改变双时间戳、NED、
   covariance、fixed-lag/OOSM、门限、量测频率或 `global_track_id`。

### 模块验证

冻结输入 SHA-256 为
`98629f103d3e208bc36cf2b706573197b64c9922e35c74377ef2a3baab7fc470`，配置 SHA-256 为
`711b799b9a36e0d9518574f027f666cb583c355f699202408d45eb083a87166e`。480 个混合量测模型、
每样本 20 轮、9 次交错采样得到：

| 指标 | Reference | Candidate |
| --- | ---: | ---: |
| 中位墙钟 | `0.444645 s` | `0.319552 s` |
| 配对更快 | - | `9/9` |
| 量测函数求值 | `124,800` | `72,000` |
| 输出维数探测/省略 | `9,600/0` | `0/9,600` |
| 结构零列省略 | `0` | `21,600` |

中位改善为 `28.13%`，量测函数求值减少 `42.31%`。雅可比、归一化创新平方、门控决策摘要
一致。端到端扫描测试还验证了关联结果、航迹 ID、状态、协方差、量测时刻、到达时刻和乱序
重放逐项一致。D1 全量 `414 passed in 21.31s`。

### 已完成的 main 准入步骤

候选达到模块门槛后按以下步骤进入正式矩阵；这些步骤已于 2026-07-25 完成：

1. 在同一 clean commit 为 scalable 3D 增加 reference/candidate selector，并在 manifest、
   summary 和 final diagnostics 记录实际实现 ID 与 D1 操作数；
2. 固定 200v200 short 10 seed 和 long 3 seed 的配对顺序、配置哈希与输入摘要，不复用旧 arm；
3. 由 D6 独立核验业务语义、有限状态、在线真值隔离、D1/D2 时延、RSS 和实现身份；
4. 只有预注册的 D1、核心墙钟、D2 回归和内存门全部通过，才允许形成集成候选准入结论。

正式矩阵满足上述准入门，结果见本文件首节。AirSim 集成计划已再次检查。候选不改变
observation schema、相机/雷达适配器、topic、settings、时间戳或 episode 编排，因此当前
无需修改该文档。系统实时、AirSim、目标硬件、RMSE、NEES、NIS 和长时容量缺口保持开放。

## P1 六维协方差 PSD 检查快路径候选结论（2026-07-24）

### 实施范围

1. 保留现有 `eigvalsh + 正半定投影 + 对角回退` 为 reference，不修改门限、投影公式、
   对角边界或业务原因。
2. 增加显式开关 `cholesky_covariance_psd_fast_path`，D1 独立构造默认 `False`。候选仅对
   有限 `6x6` 矩阵先尝试 Cholesky；分解成功且归一化行列式通过机器精度安全门后才直接
   返回，其余情况完整回到 reference。其他维度始终使用 reference。
3. reference/candidate 实现 ID 分别为
   `d1.fusion.covariance_psd_check.eigvalsh.v1` 和
   `d1.fusion.covariance_psd_check.cholesky_6x6_relative_determinant_guard_then_eigvalsh.v2`。
4. 新增固定大小诊断，记录 `attempt/success/fallback` 并检查
   `attempt = success + fallback`，同时发布安全门限 `9.094947017729282e-13`。诊断与
   已有 covariance 业务操作数分离。

### 验证结果

确定种子合成输入含 2,000 个六维协方差，其中 20 个为不定矩阵；每个样本执行 10 轮，共
20,000 次检查，reference/candidate 交替采样 9 次。输入 SHA-256 为
`f26445ee25cd87ec52a993672d9900baba3b41f7999155de35b0c7bd3424a525`。

| 指标 | Reference | Candidate |
| --- | ---: | ---: |
| 中位墙钟 | `0.558490 s` | `0.588263 s` |
| 配对更快 | - | `0/9` |
| `eigvalsh` cProfile 调用 | `20,400` | `600` |
| Cholesky attempt/success/fallback | `0/0/0` | `20,000/19,800/200` |

candidate 中位墙钟比 reference 高 `5.33%`。逐字节 covariance、reason 摘要、有限性和
对称性检查全部通过；严格正定、近奇异、半正定、机器精度附近不定、一般不定、非有限、
默认关闭、非别名和操作数守恒均有回归。D1 全量为 `404 passed in 21.39s`。

### 处置与后续

模块建议门槛预设为中位改善至少 `2%` 且候选更快配对不少于 `70%`。当前 v2 两项均未达到，
因此仅保留默认关闭的研究对照，明确不建议 main 接入或开展完整多 seed 准入。安全门前旧
计时已由当前代码的正式重跑替代，不再作为性能证据。只有 NumPy/BLAS、目标处理器或真实
冻结融合输入改变成本关系时，才重新运行同一 A/B 工具。本项不关闭系统实时、AirSim、
目标硬件、RMSE、NEES 或 NIS 缺口。

## P1 匀速模型矩阵复用正式准入结果（2026-07-24）

### D1-owned 实施

1. 依据 `process_scan_batch -> _predict_all_to/_state_from_complete_replay_checkpoints/
   _replay_record -> predict_to` 调用链，选择匀速模型矩阵重复构造作为单一候选。未同时修改
   GlobalTrack 物化、关联代价、重放或协方差治理。
2. 增加显式开关 `cached_cv_motion_model`，默认 `False`。reference 实现 ID 为
   `d1.fusion.cv_motion_model.per_prediction_build.v1`，candidate 为
   `d1.fusion.cv_motion_model.bounded_exact_lru.v1`。
3. candidate 使用精确 `(dt, process_noise)` 键和有界最近最少使用缓存；默认容量 128，
   最大 4,096。缓存矩阵只读，输出状态/协方差不与缓存别名。非有限键和非正时间差走原路径。
4. 新增固定大小诊断，记录请求、构造、命中、未命中、淘汰、峰值条目和绕过次数。过程噪声
   运行时变化会形成新键，不会复用旧配置。
5. 延迟乱序量测、结构歧义证据、发布载荷、协方差、双时间戳、NED、来源谱系和一致性证据
   已通过精确 A/B；专项 `6 passed`，D1 全量 `395 passed in 21.41s`。

### 模块基准

200 个状态、100 个传播步、`dt=0.05 s`、7 次交替运行的中位墙钟为
`0.220679 -> 0.103950 s`，模型构造为 `20,000 -> 8`，最终状态 SHA-256 一致。报告位于
`reports/D1_CV_MOTION_MODEL_CACHE_PERFORMANCE_20260724_CN.md` 和对应 JSON。该基准只覆盖
匀速传播热点，不是 200v200 全栈准入。

### 正式系统准入

main 已将 reference/candidate selector 和
`cv_motion_model_cache_diagnostics()` 接入 manifest、governance、运行摘要和最终诊断。
正式矩阵绑定 clean source commit
`44223566439a446fc49f2a3fd861d1d51bd676b9`，矩阵 SHA-256 为
`9898656598f0fa282620afe2384a3d656b7496f8957109c413bcb62069fd2e9a`。short 使用
seeds 1101-1110、每组 2.2 s；long 使用 seeds 1101-1103、每组 10 s。场景为 200 个目标、
200 个资源和 2 个侦察节点，共 13 pair、26 个全新 arm。

| 组别 | D1 fusion reference -> candidate | 逐 pair 改善 | 更快 pair | 核心墙钟改善 |
| --- | ---: | ---: | ---: | ---: |
| short | `3.289739 -> 3.061518 s` | `6.9271%` | `10/10` | `2.4060%` |
| long | `23.304548 -> 21.776847 s` | `6.6103%` | `3/3` | `2.4537%` |

short 的配对原始相对变化 bootstrap 95% 区间为
`[-7.7968%, -6.0841%]`。D2 association 的 short/long 变化为
`-0.1082%/-2.6729%`；RSS 均值增幅为 `0.0145%/0.2959%`，任一 pair 最大
`0.8629%`。全部 13 pair 的业务语义、有限状态、在线真值隔离、显式实现身份和缓存审计
通过。

896,820 次预测请求中，reference 模型构造 875,031 次；candidate 构造 3,535 次、命中
871,496 次，模型构造减少率和命中率均为 `99.5960%`。D6 判定
`d1_optimization_admitted=true`，因此匀速模型缓存正式准入 P1 关闭。

### 默认边界与后续计划

1. D1 `FusionAdapter` 的 `cached_cv_motion_model=False` 默认保持不变，兼容直接调用和
   reference 回归。main 集成默认已晋级为 `bounded_exact_lru_v1`，并保留
   `per_prediction_build_v1` 对照；scalable 3D 全量 `212 tests` 已通过。
2. 候选最低实时因子为 `0.1739499`，`system_realtime_gap_closed=false`。继续在目标处理器、
   AirSim 和更长时场景验证周期、尾延时、资源占用及容量。
3. 本矩阵没有提供 RMSE、NEES、NIS、AirSim 或目标硬件证据。融合精度、统计一致性、平台
   集成和系统实时 P1 均保持开放。
4. 正式 D6 报告只读引用
   `research_modules/d6_evaluation_metrics/outputs/`
   `d1_cv_motion_model_cache_multiseed_20260724_formal_4422356/`；后续回归必须继续绑定
   source commit、冻结矩阵哈希、实现身份和缓存诊断。

## P1 GlobalTrack 发布元数据 v2 正式准入结果（2026-07-24）

clean source commit `be399e138762f5e660f553c8caa812d52ab38c61` 已完成
200 目标、200 资源、2 个侦察节点的 short 10 seed 和 long 3 seed 正式矩阵，共 13 对、
26 个 arm，0 reused、0 failed。D1 fusion 改善 13.5447%/26.8298%，核心墙钟改善
6.5677%/18.2438%，D2 association 耗时降低 16.1939%/35.6213%。D1 >=10%、核心墙钟
>=5%、D2 回归 <=5% 及 13/13 业务语义、有限状态、在线真值隔离、身份、D2 审计和 RSS 门
均通过。

`d1.publication_metadata.immutable_shared_audit.v2` 与
`d1.publication_audit_tree.v2` 已正式准入，D6 判定
`d1_optimization_admitted=true`。main promotion `f5b350b` 默认选择
`immutable_shared_v2`；D1 构造器仍以 `False` 保留 reference。下一步只保持合同回归，
补逐批 D2 审计明细，并继续关闭最低实时因子 `0.1730801` 对应的系统容量 P1。AirSim、
目标硬件和正式 RMSE/NEES/NIS 继续独立验收。

## P1 扫描输入正式同提交准入结果（2026-07-24）

main 已从 clean commit
`d14285e4fdeb2f2e2cd32fad2f6d42e30f9e73a7` 完成 13-pair 三维质点 A/B 矩阵，D6
独立读取证据并给出 `d1_optimization_admitted=true`。short 为 seeds 1101-1110、
2.2 s；long 为 seeds 1101-1103、10 s。两臂来自同一提交，唯一 treatment 是
`reference_v1/candidate_v2` 扫描输入实现。

| 组别 | reference -> candidate | 逐 pair 平均改善 | 更快 pair | 原始相对变化 bootstrap 95% CI |
| --- | ---: | ---: | ---: | ---: |
| short | `1.2124522798461839 -> 1.145650333847152 s` | `5.360121886647966%` | `9/10` | `[-8.208165356448217%, -3.0841406102053194%]` |
| long | `6.687633245543111 -> 6.3406803108907 s` | `5.142481684491682%` | `3/3` | `[-8.837128529506151%, -1.6693612946922343%]` |

13/13 pair 的业务语义、有限状态、在线真值隔离和显式实现身份全部通过。核心墙钟改善仅约
short `0.7187%`、long `0.5792%`，RSS 准入门通过。扫描输入优化正式矩阵 P1 据此关闭，
`candidate_v2` 保持默认，`reference_v1` 只保留为回归路径。

开放项不变：`system_realtime_gap_closed=false`，候选最低实时因子
`0.14342687633969603`；继续由后续任务验收系统实时、AirSim、目标硬件、RMSE/NEES/NIS
和长于 10 s 的容量及增长率。本次三维质点矩阵不得写成 AirSim、实机或目标硬件结论。

## P1 扫描输入剩余热点候选（2026-07-24）

### 已实施

1. 以正式 v3 阶段计时确认热点：candidate 的 short/long scan-input 均值为
   `1.220624/6.572076 s`，long D2 association 为 `5.815163 s`。long seed 1101 冻结输入
   cProfile 进一步把 organizer 成本定位到 claim、JSON 规范化、谱系派生和缓冲重复扫描。
2. 保留 `reference_v1` 为本任务开始前的完整可执行参考；`candidate_v2` 为默认路径。
   constructor 参数、`execution_config()` 和 performance diagnostics 都能标明实际路径。
3. candidate 复用帧构造阶段已经验证的谱系键；对数值数组批量执行有限性检查并一次
   `tolist()`；每条谱系只构造一次规范 JSON，同时用于摘要和排序。谱系缓存的对象身份和
   不可变内容已纳入帧完整性封印；缓存被非常规替换时，从 observations 重建帧。
4. candidate 对 ready/remaining 做一次稳定分区，并缓存当前缓冲观测数。reference 继续执行
   原两次扫描和逐次求和，便于同进程 A/B。
5. 业务配置和事件合同不变。双时间戳、NED、covariance、在线 truth fail-closed、来源谱系、
   6 s fixed-lag、量测频率、缓冲门限和 `global_track_id` 均未修改。

### D1-owned 验收

输入为 570 帧、10,810 条匿名观测，SHA-256
`5b47f3cf43a9bf78bfca0db249bbefeb709a10c1a7aa6bb4277226fc2144e2d6`。7 轮交错
P50/P95 为 `1.078281/1.084012 s -> 0.756634/0.766820 s`，P50 下降
`29.830%`。claim/content/frame digest、结果事件、发布顺序和最终 audit 全部严格一致；
墙钟不参与语义通过判定。新增缓存篡改回归后，专项 `26 passed in 0.29s`，D1 全量
`361 passed in 20.67s`。

普通 Python 数值序列快路因 cProfile 退化被撤销。expiry 单次整体分区没有实施，因为现有
逐项过期事件要求保留每一步的缓冲计数。两项均不留在默认路径。

### 已完成的正式验收

1. main 已在固定 clean commit 上完成 short 10 pair 与 long 3 pair 的同提交矩阵。
2. manifest、summary 和最终 diagnostics 均记录实际实现身份，D6 未按提交号推断路径。
3. scan-input、核心墙钟、实时因子和 RSS 已分层评估，业务语义、有限状态、在线真值隔离与
   实现身份 13/13 通过。
4. `candidate_v2` 已正式准入。系统实时、AirSim、RMSE/NEES/NIS、目标硬件和更长时容量
   仍按独立计划验收。

## P0/P1 正式多 seed 准入结果（2026-07-24）

main 已完成预注册 v3 矩阵，D6 已完成只读评估。矩阵包含 short seeds 1101-1110
（2.2 s）和 long seeds 1101-1103（10 s），共 13 组配对、26 个三维质点集成 episode；
26/26 正常退出，13/13 跨构建语义检查通过。正式 manifest SHA-256 为
`40669d10fff8367aa31e24624bab802d8bc3de6b01aaa1e5c92d054753ed93ec`。

reference 为标量路径提交 `a5a472cf81496d94a98db3deb88a3d5c6951f0ce`，candidate 为
向量化路径提交 `064cbb979d3bab68fee995e476df25709eb666db`。两者共同包含
`064cbb979d3bab68fee995e476df25709eb666db` 的 D1 完整正半定修复和 `e4147b8` 的
D2 误警审计修复，避免把 P0/D2 修复混入性能 treatment。

| 组别 | reference 融合墙钟 | candidate 融合墙钟 | 改善 | 更快 seed | 配对原始变化 95% CI | P95 改善 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| short | `4.029165 s` | `3.652252 s` | `9.35462%` | `10/10` | `[-10.914359, -8.113134]%` | `6.652902%` |
| long | `32.954357 s` | `30.768826 s` | `6.631993%` | `3/3` | `[-7.279095, -5.406805]%` | `6.655511%` |

D6 判定 `d1_optimization_admitted=true`。P0 发布协方差正半定输出缺口关闭，P1
`vectorized_covariance_limit` 正式准入缺口关闭。系统实时性仍开放：
`system_realtime_gap_closed=false`，candidate 最低实时因子为 `0.143397`。下一阶段只继续：

1. 在目标运行环境和 AirSim 上形成可追溯周期、尾延时与资源证据；
2. 使用独立离线真值侧车形成 RMSE、NEES、NIS 及置信区间；
3. 保持 D2 PSD 门、全部观测、6 s fixed-lag、双时间戳、谱系和在线 truth 隔离不变。

本矩阵不包含 AirSim、实机或目标硬件，也没有计算 RMSE、NEES、NIS。不得把优化准入解释为
系统实时或融合精度验收。

## P0 输出协方差正半定修复（2026-07-24）

### 根因

seed 1103 的 200v200、10 s 长时运行在仿真发布时刻 `7.85180018473111 s` 将
`global_track_031` 交给 D2 时失败。D1 限制前矩阵最小特征值为
`+7.506060086e-04`。旧 pairwise limiter 只把一个交叉项从 `1087.599461434918` 改为
`1086.6821912486967`，输出最小特征值降为 `-9.247657800e-04`。局部二维相关上界不蕴含
六维正半定，且独立裁剪一个交叉项会破坏整体相关结构。

标量和向量化路径不是分歧源。同一冻结运行逐调用双算 58,776 次，2/4/6 维调用数为
851/7,443/50,482，reason 和数组逐元素完全一致；单独标量运行也在同一时刻失败。

### 已实施算法

1. 保留既有对称化、对角 floor/ceiling 和 `0.999` 成对相关裁剪。
2. 对完整治理后矩阵做严格特征值检查。若无负特征值，保持数组不变。
3. 若为非正定矩阵，以治理后对角构造标准差矩阵，将 covariance 转成相关矩阵。
4. 对相关矩阵执行特征值 floor，再通过合同缩放恢复单位对角。
5. 与单位阵做确定性凸组合，同时保持正半定并重新满足 `0.999` 相关上界。
6. 恢复原治理对角并复核有限、精确对称、对角范围、完整正半定和相关上界。最多 3 次；
   仍不能通过时回退到保留治理对角的对角矩阵。

治理记录相关裁剪 pair 数、正半定投影迭代数、特征值 floor 数、相关收缩数和对角 fallback
数，并向航迹 metadata 发布总操作数及分项。标量 reference 和向量化 optimized 共用投影，
旧开关继续用于计时。D2 PSD 门限、观测数量、双时间戳、谱系、NED、6 s fixed-lag 和在线
truth 边界不变。

### 验收状态

- seed 1103 失败矩阵固定回归通过；
- 1 至 6 维各 96 组随机/极端矩阵满足全部约束；
- pairwise 上界内仍非正定的三维矩阵可被识别和修复；
- 标量/向量化输出、reason 和操作计数严格相同；
- 双时间戳、opaque 来源谱系、OOSM 和默认 6 s fixed-lag 回归通过；
- 协方差专项与旧性能专项合计 `28 passed`；
- D1 全量 `352 passed in 20.52s`；
- 修复后 200v200、seed 1103、10 s 集成运行完成，10,554 条在线观测、有限状态、在线 truth
  使用 0，实时倍率 `0.157583`。

本 P0 的 D1 输出断点已关闭。其后的 13-pair clean 多 seed/长时矩阵已按上节完成并通过；
系统实时、AirSim、目标硬件和正式 RMSE/NEES/NIS 仍是开放 P1。

## P1 协方差成对限制热点治理（2026-07-24）

### 根因与选择

main 提供的最新 cProfile 来自 seed 1100、200v200、2.2 s 冻结输入。输入含 89 个扫描、
2,035 条匿名观测，在线 truth 使用为 0。`_limit_covariance_diagonal()` 共调用
14,868 次、累计 `1.076 s`；其中 `_limit_state_covariance()` 调用 12,833 次，
`_predict_all_to()` 调用 178 次、累计 `1.130 s`。

调用方复核没有发现可安全删除的“同一已限制后验重复完整治理”：

1. `_predict_all_to()` 中 10,832 次限制都发生在 `predict_to()` 改变状态协方差之后；
2. 1,789 次更新后重放和 202 次航迹新生也都生成新的当前协方差；
3. `current_state_covariance_limited` 已阻止同一当前状态在 `GlobalTrack` 物化时重复治理；
4. profile 中的 `eigvalsh` 主要来自观测 covariance 在线合同校验和 A95 计算，不能与状态
   成对限制合并或缓存。

因此不跳过预测、重放、观测验证或上下界治理。本轮只把既有上三角双循环的 15 次标量
`np.clip` 改为一次 NumPy 上三角裁剪并镜像下三角。1 至 6 维只缓存不可写的三角索引拓扑，
不缓存状态、协方差或校验结果。原标量循环通过
`vectorized_covariance_limit=False` 保留为 reference，默认优化路径为 `True`。对角
floor/ceiling、reason、对称化、非法状态重置和在线观测有限/对称/半正定 fail-closed 行为
保持不变。

### 冻结输入验收

冻结源 SHA-256 为
`54bed9d7f03497967c3f8478a9e0cf1385e85bcc512bf769df849b7b1ab3e0ec`。使用相同
release-group 和同一物化调度先预热一对，再交错运行 5 轮，并对两臂各做一次 cProfile。

| 指标 | 标量 reference | 向量化 optimized | 变化 |
| --- | ---: | ---: | ---: |
| 纯融合均值 | 3.001196 s | 2.610975 s | -13.00% |
| 纯融合 P50 | 3.011440 s | 2.614061 s | 1.152x |
| 纯融合 P95 | 3.023308 s | 2.660813 s | 1.136x |
| `_limit_covariance_diagonal` 累计 | 1.047145 s | 0.426826 s | -59.24% |
| `_limit_state_covariance` 累计 | 1.021350 s | 0.427235 s | -58.17% |
| `_predict_all_to` 累计 | 1.098530 s | 0.584526 s | -46.79% |

优化路径 5/5 轮更快。预热、全部交错轮次和 profile 运行均满足：

- 每一扫描的内部后验、物化航迹、状态、协方差、双时间戳、来源谱系和分级等价；
- 最终 `GlobalTrack` 和 consistency evidence 哈希等价；
- 全部批操作计数、累计性能诊断、扫描/观测/航迹数和物化调度等价；
- 观测丢弃、扫描降频、6 s fixed-lag、门限、NED 和 `global_track_id` 均未改变；
- 在线 truth 使用为 0。

长夹具只执行一次 reference/optimized，不预热、不重复、不剖析，也不设置计时准入。seed
1000 的 10 s 冻结输入含 771 扫描、11,889 匿名观测，量测/到达跨度为
`9.8/9.827020 s`。两臂均触发 4,009 次 fixed-lag rebase 和 11,888 条 OOSM，逐扫描语义、
操作计数、累计诊断、延迟审计、463 次完整物化、308 次 state-only、202 条终态航迹及
consistency evidence 严格一致，在线 truth 为 0。

专项测试 `18 passed`，D1 全量 `342 passed in 19.73s`。边界测试覆盖正常、floor/ceiling、
负/零对角、极大相关项、非有限上层重置、非对称、有限非正定及在线非法观测 covariance，
并验证 reference/optimized 的逐扫描结果和审计合同。

### 当前状态

D1-owned 标量裁剪热点已关闭并保留显式 A/B。本节记录的是正式矩阵之前的单 seed
冻结回放；上节已在固定提交上完成 clean 多 seed 全栈复核并准入向量化路径。AirSim、目标
硬件、系统实时性和正式 RMSE/NEES/NIS 仍按既有 P1 保持开放。

## A2 原子 shadow clean 成对复核（2026-07-24）

main 已在 clean commit
`7cc2d0cfd598a72d60c6ba8c7d4a283f4e5a897d` 使用原子入口完成 seed 1100、200v200、
2.2 s、`recon_count=2` 的 control/atomic-shadow 成对运行。两份 manifest 均为
`repository_dirty=false`。control/shadow 墙钟为
`10.735151270986535/19.449935468961485 s`，开销比 `0.8117989190825889`；实时倍率为
`0.20493423375838704/0.1131109151241553`。

shadow 共 9 条发布、46 条决策，0 accepted、46 `oosm_scan` rejected、0 error。9/9 次
post-integrity 通过，atomic failure 和 materialized shadow 均为 0。单次审计总时延
P50/P95/max 为 `1024.838/1536.429/1549.436 ms`。D1/D2/D3 终态在两臂均为
`202/201/186`；在线 truth、禁止写入、D2/D3 shadow 消费和全局编号变化均为 0。

结论保持停止：安全隔离和业务非干预子门闭合，性能门和有效 treatment 门失败，A2 不准入。
全拒绝输入下，旧 prepared-handle 路径本来就跳过 assemble，原子入口没有装配边界复核可省。
后续若继续研究 A2，应先获得不放宽 OOSM/结构门限的真实 accepted treatment，再单独处理
前/后完整摘要和规范复核成本；在此之前不启动 A3/A4 或 seeds 1101/1102。

## A1 原子接口优化状态（2026-07-24）

D1 已实现
`run_experimental_centroid_publication_overlay_atomically()`，状态为
`IMPLEMENTED_UNIT_TESTED_OFFLINE_ATOMIC_OPTIMIZATION`。该显式 experimental/offline
入口在一次同步调用中内部持有 prepared handle，依次完成 prepare、evaluate、detached
assemble 和 post-integrity verify。调用方不能在准备与内部消费之间取得描述符。返回冻结
结果只包含安全准备摘要、evaluation、可选 detached shadow、规范与 shadow 摘要、后置
完整性检查和工作量计数。

公共 prepare/evaluate/assemble API 不变，显式 prepared handle 在每次公共复用边界继续重算
完整规范载荷摘要。原子入口的正常 200 航迹路径只执行 1 次完整 `_describe_tracks` 和 1 次
操作后完整规范复核，共 200 条后置摘要。accepted 路径另生成 200 条 detached shadow 摘要；
rejected 路径不装配或序列化 shadow。完整 metadata、lineage/source support、identity、
`last_nis`、全局编号、双时间戳、分级、state/covariance、NED 和禁止身份字段覆盖均未裁剪。

后置复核失败时，原子入口不公开 provisional accepted shadow，并把 generation 状态恢复到
调用输入。state/covariance 数组、嵌套 metadata、source support、identity、`last_nis`、
全局编号、时间戳或分级在调用内发生修改都会 fail closed。接受输出继续保持 ID、速度、成员
相对位置、metadata 值语义和协方差不收缩；只读嵌套 Mapping/tuple/frozenset/NumPy 值可安全
脱离复制。

公开结果的 `to_dict()` 使用标准 JSON 可表示值，`canonical_bytes()` 固定确定性编码。
canonical 与 shadow 发布摘要使用相同的完整航迹摘要清单语义；装配异常和后置完整性失败
均丢弃 shadow 并恢复输入 generation 状态。

2026-07-24 聚焦测试 `36 passed`，D1 全量
`324 passed`。2/3/5 成员决策与 `de73cb2` 基线逐字节一致；200 航迹工作量、正常
接受、OOSM/数量不平衡/重复代/倒退代拒绝、调用内篡改和引用隔离均有固定测试。

main 已在默认关闭审计路径采用原子入口并完成上节 clean 成对复核。性能门仍失败，且没有
accepted treatment；不得声明 A2 已关闭。A3/A4 和 seeds 1101/1102 继续停止。该优化不影响
`fusion.py`、默认开关、在线 schema 或 AirSim 集成方案。

## A1 准备对象优化状态（2026-07-23）

D1 已完成 A1 原型的最小安全性能改进，状态为
`IMPLEMENTED_UNIT_TESTED_OFFLINE_OPTIMIZATION`。新增实验接口
`prepare_experimental_centroid_canonical_publication()` 对一个规范发布快照执行一次完整
校验、身份字段审计和 SHA-256 描述，并返回不可变准备对象。evaluation 和 shadow assembly
可只读复用该对象。每次复用先核对序列及成员对象绑定，再对每条航迹的完整规范载荷重算
SHA-256；显式准备对象与输入序列、成员对象或任何载荷内容不匹配时 fail closed。旧 API 保持
可用，提交 `de73cb2` 的 2/3/5 成员 canonical decision bytes 保持不变。

本次没有修改共同质心数学、拒绝优先级、generation 水位、安全门、decision schema、
`fusion.py` 或默认开关。完整 metadata、lineage、source support、identity、
`global_track_id`、双时间戳和 state/covariance 仍进入校验与强摘要。准备对象的工作量计数明确
报告完整描述轮次、轨迹校验和摘要数量，不能通过跳过 metadata、仅描述分量成员或弱哈希减少
成本。

接受路径已用递归值语义复制替代通用 `deepcopy`，可处理真实发布中嵌套只读 `Mapping`、
`tuple`、`frozenset` 和 NumPy 值。拒绝仍返回原序列对象；接受仍保持 ID、速度、成员相对
位置和协方差不收缩。2026-07-23 聚焦测试 `21 passed`，D1 全量
`308 passed in 19.69s`。200 航迹固定夹具验证 evaluate/assemble 合计只发生一次完整描述；
evaluate 和 assemble 各执行一次完整载荷强摘要复核，合计 400 条航迹摘要。性能断言使用工作
次数，不使用机器相关墙钟阈值。数组原地变化、嵌套 metadata 原地变化及 covariance、
source support、identity、全局编号、时间戳和分级变化均拒绝复用。

main 已在提交 `2b976a7` 完成 A2 默认关闭审计 shadow 的显式准备对象接线和 seed 1100
成对开发复跑。场景为 200v200、2.2 s、`recon_count=2`；9/9 次评估使用准备对象且完整性
校验通过。46 条 evidence 全部以 `oosm_scan` 拒绝，0 accepted/46 rejected。过滤审计旁路并
归一化不透明编号和总线序号后，3294/3294 条业务记录逐条一致；真值 NPZ 与两份离线 truth
文件一致，D1/D2/D3 终态均为 `202/201/186`，错误、禁止写入、下游消费和在线 truth 使用为 0。

性能门未通过：control/shadow 墙钟 `10.712171729/19.376483415 s`，增加 `80.8829%`；
RTF `0.205374/0.113540`，shadow 总阶段 P95 `1532.999 ms`。禁止写入前摘要、prepare、
evaluate、禁止写入后摘要的均值分别为 `224.461/345.095/195.421/207.312 ms`。最大载荷
`11,275,939 bytes`，水位 `8/1024`；装配均值仅 `0.00247 ms`，反映本批全拒绝并直接返回原
序列。两份 manifest 为 `repository_dirty=true`。A2 的安全和业务非干预子门通过，但性能门
与有效 treatment 门均失败，因此 A2 不准入。下一步不是继续扩大 seed，而是保留停止结论；
A3/A4 和 seeds 1101/1102 继续停止。

## 结构歧义 A1 原型完成状态（2026-07-23）

D1 已在提交 `de73cb2` 完成 A1，状态为
`IMPLEMENTED_UNIT_TESTED_OFFLINE_PROTOTYPE`。实现位于独立实验模块
`src/d1_sensor_fusion/structural_ambiguity_publication_overlay_prototype.py`：它以只读规范
`GlobalTrack` 发布快照和 `StructuralAmbiguityEvidence` 为输入，纯函数返回 detached
decision/member overlays 与新的有界 generation 状态，并可纯函数装配 shadow tracks。
该原型未接 `FusionAdapter.process()`、`process_scan_batch()` 或默认发布路径，未修改
`fusion.py`，没有运行开关；实验 decision 结构不是当前在线 schema。

设计比较三条路线：

1. A1 已把共同质心处理实现为一次性 publication overlay 纯函数原型。规范滤波
   state/covariance、观测历史、fixed-lag checkpoint 和 replay cache 均不修改；候选拒绝时
   overlays 为空，装配函数直接返回规范业务序列，不执行 publication-base replay + replace；
2. B 把共同质心作为 measurement-time OOSM 历史事件。当前
   `Q(h)=G(h)qG(h)^T` 不满足单段/分段传播半群等价，插入零更新事件也会因增加传播分段而
   改变协方差；在事件排序、过程噪声分段和 RMSE/NEES/NIS 一致性门槛冻结前，不进入在线实现；
3. C 保持 D1 只发布结构证据，由 D2 在有界窗口内研究概率关联或多假设消费。该路线是主要
   系统研究方向，后续由 D2 owner 单独规划，本轮不修改 D2。

三条路线均保持双时间戳、NED/covariance、平衡满基数 treatment 门、generation 有界幂等、
lineage/source support、质量和 identity 状态不变。overlay/event 不生成、改写或局部重绑
`global_track_id`；无成员交叉协方差的事实继续显式发布。

2026-07-23 的 A1 聚焦测试为 `7 passed`，覆盖 2/3/5 成员接受、拒绝透传、全排列确定性、
generation 幂等/倒退/摘要冲突、冲突组件、硬容量、状态有界、truth/非有限输入隔离及输入不变；
D1 全量为 `294 passed`。后续状态由上一节 2026-07-23 增量更新：A2 main-owned 显式准备
对象接线、规范快照和禁止写入摘要审计已经完成，业务输出等价，但性能与有效 treatment 门
失败，A2 不准入。A3 新匿名冻结扫描 treatment 发现和 A4 预注册未见 seed 确认不启动。
seeds 1101/1102 继续停止，不得以放宽 OOSM、满基数、形状或身份门制造 treatment。

## 共同质心冻结扫描边界诊断完成状态（2026-07-23）

D1 已完成共同质心候选的受控冻结扫描边界诊断。诊断复用 governed replay、
`SensorScanFrame`、`ScanInputOrganizer`、固定滞后重放和在线
`FusionAdapter.process_scan_batch()`，没有增加平行融合框架。控制臂和候选臂消费相同的扫描
编号、双时间戳和观测数量；候选只在诊断实例中显式开启，生产默认仍为 `False`。

已完成的三类确定性输入如下：

1. 同步、平衡、纯交替环 `2x2` 分量实际施加一次共同平移，模长
   `15.000000 m <= 30 m`；速度、成员相对位置、hit、lineage、identity 和
   `global_track_id` 不变，协方差差最小特征值 `0.4797678`，满足不收缩；
2. 乱序但平衡的 `2x2` 分量保留量测/到达时刻 `0.300/0.650 s`，进入融合前时刻为
   `0.400 s`。扫描组织器记录重排，候选以 `oosm_scan` 拒绝，`applied_component_count=0`；
3. 数量不平衡分量记录成员/观测 `2/1`、最大匹配基数 1、free row/column `1/0`，以
   `unbalanced_component` 拒绝，`applied_component_count=0`。

两个拒绝场景的共同质心 correction 均未施加，但拒绝后各有一次 publication-base replay +
replace 清除旧临时修正。该替换把控制臂的分段预测发布态换成候选臂从观测历史单段重放得到的
发布基准；当前离散 CV 过程噪声不满足分段半群等价，因此候选减控制协方差差最小特征值分别为
`-0.0071928353214153066` 和 `-0.004617076466238031`。差值已 bitwise 归因到 replacement，
只作诊断，不能声称拒绝路径对状态和协方差严格无副作用，也不能作为晋级证据。

专项 `5 passed`，D1 全量 `287 passed in 18.03s`。JSON 与中文 Markdown 位于
`reports/structural_ambiguity_centroid_replay_20260723/`。该阶段关闭“受控冻结输入中是否
存在合法非零施加窗口”的 D1 边界诊断子项，不关闭现实匿名输入的算法收益 P1；晋级边界为
`candidate_not_promoted`。

该诊断之后的执行顺序已由上节下一候选设计收紧：不直接恢复 hold+现有历史替换候选的系统
A/B。A1 已在纯函数单元范围验证 publication overlay 的拒绝路径 bitwise 隔离；main 已执行
A2 冻结扫描 shadow，但性能门和有效 treatment 门失败，因此停止新的匿名冻结扫描、未见
seed 和多 seed 扩展。若未来提出新候选，均方根误差、归一化估计误差平方、归一化创新平方、
D2/D3 可用性、P95 和长时内存/吞吐必须重新预注册。不得放宽 OOSM 或数量门制造处理。

## 结构歧义证据侧车候选验收结论（2026-07-23）

D1 已完成默认关闭的
`prediction_only_maximum_matching_component_evidence_v3` 模块实现。配置
`radar_assignment_ambiguity_hold_evidence=False` 与 v1/v2 互斥。候选复用 v2 已验证的最大
匹配允许边分解，在歧义分量内停止单航迹身份提交和量测更新，保留 prediction-only 成员状态，
并发布 `d1.structural-ambiguity-evidence.v1` 侧车。

当前完成项：

1. `FusionBatchResult` 与 `FusionStateUpdateResult` 均可携带 evidence tuple；默认关闭且 tuple
   为空时，既有序列化不增加字段；
2. 侧车完整保存双时间戳、NED 状态、成员/观测协方差、候选边、分量结构、匹配基数和
   prediction-only/birth/cross-covariance 审计状态；observation key 只由数值量测证据和双
   时间戳生成，不复用可能携带离线标签的通用 source lineage；
3. 歧义 observation 不写入单航迹 lineage，不增加 hit，不 update，不 birth；唯一匹配和门外
   独立 observation 保持原路径；
4. `publisher_node_id/publisher_epoch` 显式配置；成员不透明令牌由发布者、epoch 和 D1 本地
   track id 哈希生成，D1 快照发布可供 D2 一一映射的 source key，但不宣称该键是规范
   `global_track_id`；
5. `component_kinds` 与逐边 `edge_roles` 分离。参考匹配边只携带
   `maximum_matching_allowed/matched_reference`；替代边只增加自身成立的 cycle/free-row/
   free-column 角色；
6. 延迟新生计数只累计自由列。平衡 `2x2` 和 free-row `3x2` 为 0，free-column `2x3` 为 1；
7. 该阶段专项 `25 passed`，当时 D1 全量 `245 passed in 17.48s`，语法检查通过；改变 observation 名称
   及 truth/actor/D6 离线元数据时，侧车保持完全一致；
8. 已增加独立严格布尔参数 `publish_opaque_source_key=False`。`False/False` 保持默认不发布
   不透明来源字段；`hold=False/source=True` 只增加发布元数据；hold 开启时继续发布原五个
   字段。source-only 不产生 evidence、不 prediction-only、不抑制 hit/miss/birth，专项已
   验证普通扫描和 OOSM 重放的状态、协方差、轨迹数及诊断计数与基线一致。

main 和 D2 已完成接入，并在最终干净证据上完成因果复核：

1. D2 有界保活只消费 `source_node_id/source_track_id/source_key`，没有把 D1 source token
   重写为规范 `global_track_id`；
2. main 在固定提交 `ff88131` 运行同配置 baseline/candidate。场景为
   `nominal_200v200`、seed 1100、2.2 s、`recon_count=2`，候选只增加
   `--d1-d2-structural-ambiguity-hold`；
3. D1 航迹数均为 202。候选侧车 received/consumed 为 `46/46`，D2 阻止
   hit/miss/birth `69/69/4`，证明 D1 结构证据生成和一次消费链路正常；
4. D2 航迹 `203 -> 201`，D3 分配 `200 -> 197`，available/partial-unavailable mappings 从
   `1566/234` 变为 `1491/296`，实时倍率从 `0.220352` 降至 `0.207642`；
5. strict ID switch 从 9 降到 3，但 track continuity 从 0.865 降到 0.826667，coverage
   continuity 从 0.870 降到 0.828333，identity commitment coverage 从 1.0 降到
   0.957471；两组在线 truth use 均为 0；
6. 候选未达到“身份指标可评估且改善、下游可用性不退化”的预注册门槛。seeds 1101/1102
   已停止，默认开关继续关闭。

main 后续完成 seed 1100 baseline/source-only/hold 闭环三臂。D1/D2/D3 数量为
`202/203/200`、`202/201/198`、`202/201/186`，strict IDSW 为 `9/7/3`，track continuity
为 `.865/.865/.826667`，coverage continuity 为 `.870/.868889/.828333`。hold 端有
69/69/4 次 prevented hit/miss/birth、76 条未承诺记录，D3 门控拒绝 11 个目标，未承诺绑定
违规为 0。source-only 终态映射 200 个真实目标并有 1 条未映射航迹；hold 映射 191 个真实
目标并有 10 条未映射航迹。首个计划后控制反馈使传感器流分叉，因此该结果只作为闭环系统效果
对照，不替代冻结输入因果重放。

冻结发布记录的 D1 因果重放表明：76 次参考更新被阻断，其中 69 次与离线真值一致、7 次为
错误更新；另有一个真实新生延迟 0.2 s。D2 的四次 prevented birth 均来自同一真实目标的两条
重复 D1 航迹，不能据此放宽 D1 自由列新生。现有整分量 prediction-only 仍不扩大 seed 矩阵。

身份中性共同质心修正已作为默认关闭的 D1 模块候选实现。它只处理平衡、无自由行列、纯交替
环分量：

1. 成员保持未提交身份，不选择 observation-to-member 边；
2. 全部成员只施加相同有界位置平移，速度和相对几何不变；
3. hit、lineage、source support、质量分级和身份 freshness 不变；
4. 协方差满足 `P_after - P_before` 半正定，并记录共同模式误差和
   `cross_covariance_available=false`；
5. free-row、free-column、过期/OOSM、重复证据、形状不一致或大分量继续 prediction-only；
6. 每个新 generation 从该帧观测历史精确重放到发布时间，再替换上一帧临时修正；正常身份
   明确量测通过标准重放替代临时修正；
7. 每组件 generation 水位只保存最大已见/已应用代和最近量测时刻，固定滞后窗口外才淘汰，
   容量满时 fail closed；
8. 默认关闭逐字段兼容，在线继续拒绝 truth/actor/target 字段。

实现新增严格参数校验、质心马氏门限、集合形状门限、相同有界平移、位置边缘协方差膨胀、
质量分级不变门控、原子提交、帧替换、固定滞后有界 generation 水位和拒绝原因审计。修复前
连续同创新扫描会把约 15 m 的首帧修正累加为约 30 m；修复后连续三帧保持单帧修正。24 代
同组件只占一个水位条目，窗口内条目不驱逐，窗口外旧证据仍拒绝。专项 `62 passed`，D1 全量
`282 passed in 17.81s`。该结果只关闭 D1-owned 模块实现与合同测试，不关闭系统效果 P1。

main 先在未提交工作树完成 seed 1100 dirty 开发诊断，随后在固定提交
`7e15dac9cdaf6743999dfe045a70676fd31a17d6` 完成 clean 同输入复跑。两臂均为
`repository_dirty=false`、200v200、`recon_count=2`、2.2 s、seed 1100，
`config_sha256=20ef5248...b840`；控制臂为 source-key 加结构歧义 hold，候选臂只增加身份
中性共同质心。场景文件、离线真值和 89 批传感器输入一致，规范化传感器主题 SHA-256 均为
`bc064834...51518`，D2 在线记录 SHA-256 均为 `da7089fa...f8d2f`。

两臂 D1/D2/D3 均为 `202/201/186`，strict IDSW、track continuity、coverage continuity
分别均为 `3/0.8266666667/0.8283333333`。可用/不可用/未承诺映射均为 `1491/218/76`，
identity commitment coverage 均为 `0.9574706212`；重复分配、在线 truth 使用、未承诺来源
绑定违规和未承诺候选绑定违规均为 0。D3 安全门拒绝 11 个目标；main 在一次 hold 事件中
累计撤回或清除 13 条运行时绑定，两者统计口径不同。该处理关闭下游未承诺执行路径。
candidate 的 46 个组件全部拒绝，原因是 `oosm_scan=30` 和
`unbalanced_component=16`，实际施加数为 0。水位表当前/峰值为 `8/8`，无淘汰或容量拒绝。

早期 `/tmp/MSM-neutral-centroid-gate-20260723` 结果继续作为 dirty 诊断保留；clean 制品位于
`/tmp/MSM-identity-gate-results-7e15dac/{hold_only,hold_plus_centroid}`。clean 复跑确认了
零 treatment 和 D3 fail-closed 合同，没有证明共同质心修正收益，也没有恢复 hold 可用性。
停止 seeds 1101/1102，候选保持默认关闭，P1 开放。

受控冻结扫描诊断现已解释两类拒绝边界，并在同步平衡纯交替环中证明非零施加窗口。下一阶段
转为新的真实匿名冻结扫描 A/B，不再以构造输入替代系统收益。strict IDSW 不得劣于
hold-only，连续性至少恢复当前损失的 75%，
多 seed 相对基线差值置信区间下界不得低于 -0.005，D2 航迹和 D3 分配不得低于 hold-only，
D1 P95 增幅不得超过 5%。详见
`../../subagent_reviews/D1_STRUCTURAL_AMBIGUITY_HOLD_CAUSAL_AUDIT_CN.md`。

本候选不实现联合概率数据关联、多假设跟踪或分量联合协方差更新。
`cross_covariance_available=false` 明确表示下游不得把成员边缘协方差当作相互独立。当前
`birth_disposition` 是分量策略名称；实际延迟新生的观测必须以逐观测 `birth_deferred=true`
和对应计数判断。下一阶段仍需由 main 完成冻结扫描流、多 seed、P95 和长时内存验收；本轮
只同步 D1 文档，没有修改 main 接线或 AirSim 适配。

## 最大匹配允许边分量 v2 验收结论与后续计划（2026-07-23）

D1 已完成
`fail_closed_maximum_matching_allowed_edge_component_v2` 的模块实现。配置
`radar_assignment_ambiguity_governance_v2=False` 保持默认关闭，并与历史 v1 开关互斥。显式
启用时，v2 从一个最大匹配构造有向交替图，识别交替环、从 free row 出发的交替路径和通向
free column 的交替路径。含替代允许边的连通分量整体执行 observation suppression、birth
阻断和相关 track coast。

当前完成项：

1. 保留 SciPy Hungarian 结果；无 SciPy 且 greedy 基数不足时，用增广路径恢复最大匹配；
2. 仅消费门内边、匹配结构、在线状态、协方差和双时间戳，不读取名称、truth、actor 或 D6；
3. 不把 `radial_velocity_observed=False` 的零占位值作为消歧证据；
4. 完成 `2x2`、`3x2`、`2x3`、唯一匹配、门外边、首扫、fallback、OOSM 和 200 稀疏图回归；
5. 增加显式审计选择字段：关闭时 selected 为 `None`，启用时为 v1 或 v2；历史
   `policy_version` 仅为兼容字段，不能单独用于判断运行策略；
6. 显式启用 v2 时，稳定审计状态为
   `experimental_v2_enabled_rejected_candidate`；它表示运行的是已被系统门槛拒绝的研究候选，
   不表示候选重新进入验收；
7. v1/v2 专项 `29 passed`，D1 全量 `220 passed`；main 独立穷举 2,666 个小图 oracle
   通过，scalable 模块 `142 passed`。

main 已在 clean commit `c928727` 执行首个未见 seed A/B：

1. 场景为 200v200、2.2 s、`recon_count=2`、seed 1100；baseline/v2 使用同一 commit，
   `repository_dirty=false`、`config_sha256=20ef5248...b840`，runtime profile 分别为
   `b508f675...12a8` 和 `9680c45b...f9f4`，仅 v2 treatment 不同；
2. 两组 finite=true、online truth=0，online observations=2,035、radar observations=1,954、
   target labels=2,352、known false alarms=90；
3. ambiguous mappings `0 -> 0`、D1 tracks `202 -> 202`、ID switch `9 -> 9`，没有身份收益；
4. D2 tracks `203 -> 199`、D3 assignments `200 -> 196`、track continuity
   `.865 -> .830`、coverage continuity `.870 -> .835`、available mappings
   `1566 -> 1503`、unavailable mappings `230 -> 266`；
5. v2 在 9 个 ambiguity scans 中 suppression `77/1954=3.94%`，track coast=91。

预注册门槛要求身份收益和下游可用性同时成立。seed 1100 没有改善 ambiguous mapping 或
ID switch，却降低 D2/D3、continuity 和映射可用性，因此已停止 seeds 1101/1102、10 s 和
20-seed。v2 系统候选被拒绝，保持默认关闭；图论模块验证仍有效，不能据此推导 intervention
有效。P1 身份连续性继续开放。

后续计划不再调 v2 阈值或扩大该候选样本。若提出新候选，应复用已验证的最大匹配允许边边界，
重新设计比整分量 fail-closed 更节制的证据积累、局部延迟提交或分级 suppression，并从新的
未见 seed 开始预注册验收。默认行为继续使用基线 Hungarian；D1 不改写 `global_track_id`，
不改变固定滞后、协方差、NED 或双时间戳合同。

## 匿名雷达交替环 v1 阻断与后续计划（2026-07-23）

开发冻结和零延迟 A/B 已确认 seed 1000/1002 的 radar-only 问题是 scan Hungarian
swap/保持/swap-back；20:1 likelihood margin 不能在 coast 后证明身份。开发回放只用于复现
根因和候选机制，不作为晋级验收。

main 对 baseline `488dc39` 和 v1 candidate `d967c96` 完成同配置 A/B：200v200、2.2 s、
`recon_count=2`、seeds 1000/1001/1002，三 seed 的两端配置哈希完全一致：

| Seed | D2 ambiguous | strict identity | D1 | D2 | D3 | suppression |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| 1000 | `2 -> 0` | unavailable -> available；候选 IDSW `3`、continuity `.8600` | `203 -> 203` | `201 -> 200` | `200 -> 198` | `22/1962 = 1.12%` |
| 1001 | `0 -> 0` | available 保持；IDSW `9 -> 7`、continuity `.869444 -> .814444` | `201 -> 201` | `202 -> 194` | `200 -> 190` | `130/1966 = 6.61%` |
| 1002 | `2 -> 0` | unavailable -> available；候选 IDSW `4`、continuity `.8350` | `201 -> 201` | `200 -> 197` | `200 -> 193` | `78/1958 = 3.98%` |

strict availability 虽由 `1/3` 提升到 `3/3`，但 D2/D3 数量明显下降，seed 1001 continuity
下降约 `0.055`，信息抑制率为 `1.12%/6.61%/3.98%`。三组 finite=true、
`repository_dirty=false`、online truth=0、missing identity evidence=0，target/known-false-alarm
标签数相同。该代价使 v1 不能晋级。

早先 `/tmp/msm-clean-radar-d967c96` 实际使用 `recon_count=8`，三 seed 配置哈希为
`cc6/cbb/9f45`，不能与 recon=2 baseline 比较，只作为 stress 诊断。该 stress 的 seed 1001
`GT3D-000210` 来自既有 D1 `global_track_187`，不是 D1 birth。scan 8 的 `200x199` 门内图有
209 条合法边、198 个匹配、2 个 free row 和 1 个 free column；当前边代价 `0.80058`，同一
observation 对 free row 的代价 `1.58216`，可通过 free-row alternating path 保持匹配基数。
v1 只检查已匹配行 SCC，因此数学边界不完整。该 stress 的 1,966 条 radar 原始量测均为三维
range/azimuth/elevation；零 radial velocity 是未观测 placeholder，不能作为运动一致性证据。

当前生产计划为：

1. `radar_assignment_ambiguity_governance=False` 保持生产默认，执行基线 Hungarian；
2. 仅在显式实验中设为 `True`，运行
   `fail_closed_gate_feasible_alternating_cycle_v1` 并读取 enabled/status/version 审计；
3. v2 已作为独立、默认关闭的模块候选实现，已证明最大基数匹配上的 cycle、free-row 和
   free-column allowed-edge 边界；seed 1100 clean A/B 已因无身份收益且下游退化拒绝该
   suppression intervention；
4. 新候选必须在未用于调参的 detached clean 输入上同时通过 ambiguous、strict identity、
   D1/D2 track continuity、D3 availability、birth/recall 和长期跨模态后果；
5. 10 s radar+vision ambiguous 不能证明纯 radar 根因，但属于长期 coast 的集成验收范围；
6. 身份连续性 P1 保持开放，不再用 seeds 1000--1002 调代价阈值。

默认关闭提交 `8f17c5d` 的同配置三 seed 已恢复 baseline 全部业务指标；main 跨构建审计
`3/3 passed=True` 且 `normalized_online_payloads_equal=True`，证据位于
`/tmp/msm-default-off-cross-build-8f17c5d-r2`。该结果关闭默认回退的业务回归风险，不关闭
v1 的数学与信息利用 blocker。

专项 `13 passed`，D1 全量 `204 passed in 16.70s`。本 follow-up 不改变 6 s fixed-lag、
扫描频率、关联门限、协方差治理、`global_track_id`、D7/PNG 或 AirSim producer/runtime 合同。

## 匿名跨模态几何门控收口与后续计划（2026-07-23）

D1 已使用 clean `5263e2b` nominal 200v200、10 s、seed 1000 的冻结在线输入复现 D2 报告中的
雷达/视觉跨目标混轨。输入包含 771 scans/11,889 observations，在线 truth 使用为 0。根因是
扫描帧冻结后的嵌套 `camera_model` 为只读 `Mapping`，旧解析器未读取其中的旋转和内参。

当前最小修复恢复真实相机几何，并保留原投影创新、协方差和匈牙利一对一分配。非法外参、相机
后方点和不可计算投影 fail closed。没有缩短 6 s fixed-lag，没有丢观测、降频、放宽门限、
改变滤波公式或改写 `global_track_id`。

验收包括匿名合法雷达+视觉正例、错误交叉负例、非法/后方相机几何、协方差边界、6 s OOSM
边界、双时间戳保真和拒绝分支状态摘要。D1 全量为 `191 passed in 16.88s`。单 seed 冻结 A/B
中，D2 标出的 17 条视觉污染观测全部离开原错误航迹，17/17 进入离线标签单一谱系。

后续按以下顺序执行：

1. main 在 clean 候选提交重跑 nominal 200v200 seeds 1000-1019，保存新增的 EO 投影门诊断、
   输入摘要和 SHA-256；
2. D2 使用新制品重新生成严格身份阻断审计，确认历史 118 个多真值航迹帧的剩余分布；
3. 若仍存在跨模态混轨，D1 只根据在线创新、协方差、时间与传感器状态定位新的可解释门控原因，
   不读取离线标签参与关联；
4. D2 sidecar 覆盖完整前，严格身份指标继续 unavailable；AirSim 和真实相机标定另行验收。

本轮输入接口和 AirSim producer/runtime 合同无变化。

## 扫描 claim 重复规范化关闭与后续计划（2026-07-23）

clean `5263e2b343dc4b96d239f77ef09437eb132f9efb` 的 nominal 200v200、10 s、seed 1000
冻结输入包含 771 scans/11,889 observations。D1 已完成旧重复 JSON 安全转换与单次物化路径的
全流水 A/B。两条路径均复用已验证 `SensorScanFrame`，只改变 claim 内部临时对象构造，不改变
摘要字节格式、claim registry、扫描发布、重复/重放/冲突拒绝或下游融合。

验收覆盖 claim registry、逐输入事件、release schedule、逐扫描状态、协方差、双时间戳、
来源谱系、航迹分级、操作计数、累计诊断、终态 `GlobalTrack` 和一致性证据。全部通过。
771 scans 交错 5 轮 P50/P95 为
`3.618/4.049 s -> 1.905/2.038 s`；cProfile 的 `_json_safe` 累计
`5.781 -> 1.992 s`。D1 全量回归为 `185 passed in 19.69s`。

当前计划按以下顺序继续：

1. main 用当前提交运行预注册 clean 多 seed 全栈矩阵，确认 scan-input 的 episode
   P50/P95/max、核心实时倍率和常驻内存收益；本轮单 seed函数级墙钟不替代该验收；
2. D1 单独设计 `GlobalTrack` 发布级 audit/health 元数据合同，先证明消费者不依赖每航迹可变
   深副本，再决定能否降低 `_to_global_track` 物化成本；
3. 对非雷达扫描关联和 fixed-lag replay 继续做冻结输入 profiler，只接受保持 6 s 窗口、
   全部观测、原门限、原协方差治理及逐扫描严格等价的局部优化；
4. 正式 RMSE、NEES、NIS 仍等待 D2 canonical mapping；AirSim 和真实传感器标定继续按独立
   计划执行。

本轮不缩短 fixed-lag 窗口，不丢观测，不降频，不改变 EKF、门控、协方差、NED、双时间戳或
`global_track_id` 合同。AirSim producer/runtime 接口无变化。

## 冻结 replay 尾延时归因与剩余计划（2026-07-23）

clean `4ac3bb2c12cc6af6ebd372107ced00bcdc5adf6a` 的
`200v200-nominal-v1`、10 s、seed 1000 冻结输入含 771 scans/11,889 observations。当前 D1
工作区完成旧 organizer 再快照路径与完整帧复用路径对照：帧重建 `771 -> 0`、organizer 内
observation 再快照 `11,889 -> 0`。前 256 scans 交错 5 轮 P50/P95
`1.942/1.968 s -> 0.881/0.894 s`；该墙钟只作分布旁证，不参与通过判定。

严格验收覆盖逐输入 organizer/close/audit/release schedule、逐 fusion 状态/协方差/双时间戳/
谱系/分级/物化航迹、终态、一致性证据、逐 fusion operation snapshot 和逐 fusion 累计诊断。
所有检查通过，操作快照哈希和累计诊断快照哈希在旧/新路径分别相同：

- operation：`sha256:82728a8e0fed0adedd0254368e29a3c117157b066158595d7ca6dac558bfb5bf`
- diagnostics：`sha256:b28df84d6664ba17d097990f7186a2a611f2e3469394e3d2a12122dbec521766`

main 实测当前 D1 全量回归为 `185 passed`；该计数是本工作区当前权威状态。

fusion 路径未修改。当前 cProfile 的主要累计路径为 GlobalTrack 物化、扫描一对一关联、非雷达
代价矩阵和 replay；radar 扫描 P95 为 `343.059 ms`，候选对峰值为 40,000，单扫描
fixed-lag rebase 峰值为 197。剩余 P1 为：

1. main 在冻结硬件、依赖和配置上运行预注册 20-seed clean full-stack 正式矩阵，重测
   scan-input/fusion P50/P95/max、核心 RTF 和 RSS；
2. D1 继续评估 GlobalTrack 共享 audit metadata、radar candidate/rebase 路径的合同级优化，
   必须保持逐扫描严格等价；不得缩短窗口、丢观测、降频、放宽门控或使用 truth；
3. 本节识别的 `_claim_for_frame` 重复 JSON 规范化已由上一节关闭；scan-input 后续只继续评估
   非 claim 的 audit/event 持久化和长期 claim registry 内存，仍须保持 lineage/JSON 合同；
4. AirSim、正式 RMSE/NEES/NIS 和物理拦截效果继续独立验收。

本轮优化验证来自当前未提交 D1 工作区，不是新的 clean full-stack。它是单 seed 三维质点
replay，不是 AirSim、正式多 seed 或实时放行证据。

## Nominal 200v200 clean 单 seed 校准与剩余计划（2026-07-22）

main 已在 detached clean
`4ac3bb2c12cc6af6ebd372107ced00bcdc5adf6a` 上完成 10 s、seed 1000、
`200v200-nominal-v1` 全栈校准，并以 clean
`0d2da25c14e50f8f9a10ad47a7bd74e5c5e577fb` 的同 seed 结果为基线。候选处理 11,889 条
匿名在线观测，世界状态有限，在线 truth 使用为 0。核心 wall
`94.104939744 -> 85.002427712 s`，下降 9.6727%、加速 1.1071x；D1 fusion
`49.697406826 -> 40.272795088 s`，下降 18.9640%、加速 1.2340x；D1 scan input
`12.315225105 -> 12.560936034 s`，增加 1.9952%。候选核心 RTF 为 `0.1176437`。

候选 771 次 D1 fusion 调用的 P50/P95/max 为
`33.25249/224.76351/592.95713 ms`。跨构建规范在线载荷、离线 truth state 和计划谱系均
通过，候选与参考谱系各自有效。外部总进程 elapsed 为 `1:55.95`，峰值 RSS
`2,468,928 KiB`；该外部 elapsed 包含离线后处理和落盘，必须与核心 wall 分列。

这组证据只接受 clean 来源、同 seed/配置、有限状态、在线 truth 0 和跨构建语义审计，不设置
正式性能放行结论。它是单 seed 描述性 clean 校准，不是 20-seed，也不是正式矩阵；RTF 仍小于
1。后续 P1 保持为：

1. main 在冻结硬件、依赖和配置后执行预注册 20-seed 正式矩阵，继续分别报告核心 wall 与外部
   总进程 elapsed；
2. D1 继续以 profiler 和逐调用分位数治理 fusion P95/max 尾延时，不以均值或累计改善替代；
3. 单独剖析 scan-input 的 frame/audit/lineage/JSON 成本，候选累计增加 1.9952%，本项不关闭；
4. 正式 RMSE/NEES/NIS、AirSim 和物理拦截效果继续独立验收。

## 非雷达创新批处理验收与剩余计划（2026-07-22）

当前未见 seed 1000 的完整 10 s 冻结回放包含 771 个扫描、11,889 条观测和 201 条终态航迹。
函数剖析确认最大融合热点为非雷达扫描代价矩阵：旧路径累计 34.307 s，逐候选
`numpy.linalg.pinv()` 496,625 次、累计 14.837 s。扫描输入整理的 frame 重建、buffer audit
和 JSON 摘要属于独立的 `d1_scan_input` 阶段，没有混入本轮融合优化。

已实现扫描内创新协方差矩阵栈。分组键包含实际量测几何、量测/协方差形状和角度残差维度；
观测量测、观测协方差、航迹状态、投影和雅可比不合并。矩阵栈只减少 Python 到
`numpy.linalg.pinv()` 的重复调用，残差包角和每个候选的二次型仍保持旧顺序。批处理异常时
回退逐候选求解。旧路径由显式开关保留用于 A/B。候选对、创新求解诊断计数、门限和 Hungarian
分配不变，不读取在线 truth。

同进程 7 次交错稳定性基准使用前 256 个扫描和 4,087 条观测，每个变体先预热 128 个扫描一次。
P50 `12.242 -> 10.238 s`，P95 `13.340 -> 11.248 s`，均值
`12.506 -> 10.385 s`。完整 771 扫描交叉验证为 `50.458 -> 39.994 s`。逐扫描摘要、
终态航迹和一致性证据三类哈希一致，操作计数、累计诊断和物化计划相同；在线 truth 使用为 0。
cProfile 中 `pinv` 调用 `496,625 -> 1,018`，非雷达代价矩阵
`34.307 -> 17.320 s`。该 2026-07-22 非雷达专项当次历史回归为
`182 passed in 15.92s`，不代表当前权威计数。

本项达到稳定提升超过 10% 且严格语义等价的保留条件。下一阶段由 main 在当前候选上复跑 clean
20-seed 全栈，重新统计 D1 fusion、scan input、核心墙钟、实时倍率和 RSS。D1 后续只继续处理
经 profiler 证明的热点：完整航迹物化，以及 scan input 的重复 frame/audit/lineage 摘要。
不得降低扫描频率、观测数量、固定滞后长度或门限。正式 RMSE/NEES/NIS 和 AirSim 仍独立验收。

## 一致性证据刷新验收与剩余计划（2026-07-22）

本轮按 clean `f80b5bd` 三 seed 10 s 冻结输入继续治理 D1 长时性能。代表 seed profiler 将下一
主导热点定位为合法缓存前缀的一致性证据刷新：旧实现使用 `dataclasses.replace()` 重跑整个
记录的时间、状态、协方差、可用性和谱系校验，即使实际只改变两个 replay 计数。

已实现受限复制路径。它只从一个已经完整验证的冻结记录出发，校验新的非负
`replay_revision/replay_count`，并复用其余不可变槽位。参考开关继续执行旧完整重验。新建证据、
滤波更新、重复观测、OOSM 和不可用证据不走受限路径。该实现没有缩短 6 s fixed-lag、降采样、
跳观测、改变 gate/covariance，或读取 truth。

三 seed 严格 A/B 已完成：扫描数 `764/844/782`，匿名观测数
`12,107/11,922/11,825`，终态航迹 `202/207/203`。参考/候选纯融合墙钟均值
`64.844/52.657 s`，3/3 候选更快，聚合加速 `1.231x`。逐扫描状态、协方差、时间戳、谱系和
航迹分级，终态输出、最终一致性证据、全部操作计数与物化计划均相同，在线 truth 使用为 0。
代表 seed cProfile 的证据刷新累计 `27.122 -> 1.664 s`，历史重放累计
`35.348 -> 9.410 s`。D1 全量 `178 passed in 14.80s`。

本项 D1-owned 热点据此关闭，系统实时与超线性 P1 不关闭。随后非雷达扫描代价矩阵已按本文首节
完成矩阵栈批处理验收；当前下一热点转为航迹物化和 scan input。任何后续优化仍须保持逐扫描
语义、固定滞后窗、双时间戳、协方差、来源谱系和终态输出严格一致。另行由 main 统计进程常驻
集、长于 10 s 的增长率和端到端实时倍率。

## 最终 integrated 三 seed 证据与剩余计划（2026-07-22）

main 已完成 clean 参考提交 `8f86192` 与 clean 候选提交 `f80b5bd` 的同配置跨提交复跑。
`200v200-nominal-v1`、10 s、seeds 42000/42001/42002 均为有限状态，在线 truth 使用为 0；D1
终态航迹数逐例保持 `202/207/203`。D1 fusion 累计耗时三 seed 均值
`92.991088 -> 88.330438 s`，下降约 5.01%；scan input
`16.902643 -> 17.524242 s`，增加约 3.68%。精确创新求解合计
`7,130,228 -> 1,578,677`，下降约 77.86%。求解次数只进入性能诊断，不参与业务等价判定。

三个 seed 的逐条跨提交业务语义审计全部通过。审计按规划 occurrence/version 归一化 D3 的不透明
`plan_id`，但先验证 ACK 原始载荷 SHA，并继续比较 owner/version/coalition/`global_track_id`/
command 等业务字段。D1 fused-track 主题的规范哈希逐 seed 一致。该证据把 certified radar
pre-gating 从冻结纯融合回放扩展到当前 integrated D1-D7 总线；未认证创新协方差仍使用原精确
`pinv` fallback。

当前关闭的是三 seed 集成语义复核，不是吞吐预算。后续 P1 保持为：在冻结硬件和预注册预算下
扩展时长及未见 seed，分别报告 D1 fusion、scan input、进程常驻集和端到端实时倍率；继续核验
真实异常协方差的认证/回退比例，并通过独立 truth sidecar 与正确 D2 canonical mapping 形成
RMSE/NEES/NIS。系统长时归一化超线性和实时性仍开放，不调整预门控数学边界。

## 雷达关联预门控验收与剩余计划（2026-07-22）

D1 已在不改变默认完整 API 和 state-only/full 合同的前提下加入雷达候选预门控。适用性认证要求
创新协方差有限、逐元素严格对称，Gershgorin 严格正定下界在数值安全裕量后仍大于零，并高于
`np.linalg.pinv` 默认 `rcond=1e-15` 对应的奇异值 cutoff 上界。只有通过认证的矩阵才使用
`||d||^2 / U` 马氏距离下界，其中 `U` 是对称矩阵谱范数的保守行和上界；未认证矩阵全部走旧
精确 `pinv`，不得预拒绝。

不定交叉协方差与近奇异截断两类负例已构造为“旧 `pinv` 代价在门内、朴素 trace 下界在门外”。
两类 rejection mask 均为 false，扫描级参考/候选结果和全部创新求解计数一致。10 s 冻结 seeds
42000-42002 的逐扫描、终态航迹和一致性证据哈希全部相同；精确创新求解合计
`7,130,228 -> 1,578,677`，旧/新墙钟均值 `91.313 -> 88.619 s`，3/3 candidate 更快，聚合
加速 `1.030x`。A95 单次复用保持分级和 metadata 数值不变。专项 `6 passed`，D1 全量
`175 passed in 26.69s`。

该 D1-owned 优化已通过当前冻结输入验收。后续 P1 不再改动预门控数学条件，工作转向固定硬件
周期预算、更多未见 seed/更长时长、正式 RMSE/NEES/NIS、真实传感器异常协方差比例及回退率。
优化后 10 s 输入仍平均需要 88.619 s，系统实时性保持开放。AirSim 输入输出和运行时编排未受
影响，因此 `docs/AIRSIM_INTEGRATION_PLAN.md` 本轮无需修改。

## Clean 200v200 全栈证据与剩余计划（2026-07-22）

main 已在 clean 候选提交 `8f86192` 接入 D1 的 state-only/末尾快照合同。同一 fusion timestamp
内的扫描逐个更新，只有末次后验物化完整快照。200v200 三维质点 10 s
场景使用 seeds 42000、42001、42002，3/3 clean、finite，在线 truth 使用 0，D1/D2 overflow
和安全合同全部通过。相对旧 clean 提交 `3bac3ff`，D1 fusion 三 seed 均值
`103.339 -> 92.991 s`，下降 10.0%；seed 42000 的 2.2 s 全栈墙钟
`18.611 -> 18.302 s`。

三例 state-only 扫描数为 `310/328/278`，完整快照数为 `454/516/504`，分别合计
`764/844/782` 个已接收并释放的扫描。所有扫描仍逐个融合和发布，事件、scan input、共享摘要及
世界真值与旧提交同 seed 一致。main-owned 质点全栈接线和 clean 三 seed 语义复跑项据此关闭。

下一阶段不再重复实现延迟物化。开放 P1 是更长时和更多未见 seed 的固定硬件周期统计、
P50/P95/max 与峰值内存、正式 RMSE/NEES/NIS consistency、真实 sensor-specific latency 以及
AirSim 接线。D1 fusion 在 10 s 仿真中仍需 92.991 s，不能宣称实时闭合。

## 同一运行时刻延迟物化状态（2026-07-22）

D1-owned 接口已完成。`process_scan_batch()` 默认行为保持不变；显式
`materialize_tracks=False` 时返回 `FusionStateUpdateResult`，其中
`tracks_materialized=False`、`tracks=[]`、`track_count=0`、准确的 `current_track_count`、
`state_updated_at` 和扫描摘要可用于轻量审计。对象属性 `tracks` 访问会失败，不会把未物化误写
成零航迹。main 在同一 runtime tick 内处理完
全部已释放扫描后，调用 `materialize_global_tracks()` 一次，取得完整 `FusionTrackSnapshot`。

状态-only 路径不得跳过扫描级关联、fixed-lag/OOSM、双时间戳、covariance、门控、health、
consistency evidence、lineage 或累计诊断。4 扫描、3 目标、检查点前 OOSM 构造回归中，参考路径
和延迟物化路径终态完全一致，物化数 `12 -> 3`。混合发布 audit 使用
`d1.fused_track_publication_audit.v2` 区分总发布、完整快照、状态更新和航迹记录数，并兼容缺少
新字段的 v1 日志。定向测试 `30 passed`，D1 全量 `168 passed in 29.43s`。

main-owned scalable 三维质点集成已按 released scan 顺序调用 state-only 接口，同一
fusion timestamp 的中间扫描保存轻量 audit，末次扫描的 summary 与一次完整快照合并后交给
D2，并完成 clean 三 seed 对照。
D1 不在本任务中修改 main/scalable runtime。尚未关闭的是系统实时预算、长历史资源增长、
AirSim 和正式融合精度。

## 当前性能治理状态与后续计划（2026-07-22）

长时固定滞后专项已经完成 D1-owned 等价优化。冻结输入 SHA-256 为
`3efa561a07bf0cdcd74d23570ee23ca173f56ddaf632c89258d02c20c299a51a`，包含 764 个扫描和
12,107 条匿名观测，在线 truth 使用为 0。实施和验收状态如下：

1. **增长来源已定位并治理**：完整后验检查点支持二分状态查询；固定滞后重基保留仍有效的检查点
   后缀；失效逻辑维护合法缓存前缀；未变化一致性证据只刷新 revision/replay count。算法主线和
   6 s 固定滞后窗未改变。
2. **长时语义验收通过**：旧路径与优化路径的 764 个逐扫描摘要、202 条终态航迹和一致性证据
   哈希一致，candidate pair/innovation solve 均保持 2,393,969，在线 truth 使用为 0。
3. **确定性操作数下降**：history replay `170,106 -> 13,397`，replay filter update
   `120,440 -> 9,549`；纯融合墙钟 `157.237 s -> 107.449 s`，本机单次 1.463 倍。
4. **有界诊断已落地**：`fusion_performance_diagnostics()` 以固定大小累计标量暴露 filter update、
   checkpoint reuse、状态查询、重基和物化计数，供 episode profiler 采样，不携带航迹历史。当前
   冻结输入实际记录状态查询 152,861、后缀复用 110,891、合法前缀快路径 300,024 和缓存一致性
   刷新 194,916 次。
5. **发布边界明确**：764 条全量快照约 186.2 MiB，407 个唯一融合时刻，357 条同融合时刻可合并，
   294 条连续未变化。D1 已提供同一 tick 延迟物化接口；跨 tick 合并和 heartbeat/lineage sidecar
   仍只是 main 调度建议。
6. **剩余系统 P1**：main 已接入 state-only/末尾快照合同并完成 clean 三 seed 全栈复跑；下一步
   扩展时长和 seed，冻结周期与内存预算并补正式精度。D1-only 1.463 倍、构造回归中的
   `12 -> 3` 和全栈 D1 分项下降 10.0% 都不能写成 200v200 系统实时。

专项报告为 `reports/D1_LONG_DURATION_PERFORMANCE_BENCHMARK_CN.md` 及对应 JSON。延迟物化接口
改变 main 的推荐调用方式，因此 `docs/AIRSIM_INTEGRATION_PLAN.md` 已同步；没有改变 AirSim
producer、topic、reset/episode、相机接口或已有实验结果。

第二阶段扫描关联优化已经完成。clean 提交 `492979e` 的 200 规模五 seed 第一阶段默认路径
D1 fusion 为 10.096/13.693/12.895/11.973/11.856 s，均值 12.103 s。seed 42000 冻结输入
SHA-256 为 `bc539686b130d96c63b76b9161fadbae2dba59de44cb61ac80d92f2ea1018406`；输入仍为
86 个扫描、2,051 条匿名观测，在线 truth 使用为 0。

本阶段的实施和验收状态如下：

1. **扫描内模型缓存已实现**：非雷达量测模型按观测构造一次，航迹状态按共同量测时刻取得一次；
   传感器/相机几何键严格相同时复用预测量测和数值雅可比。每个候选对仍独立执行创新求解和门控。
2. **扫描语义保持**：current-default 与优化路径的 86 个逐扫描语义哈希、最终 201 条航迹哈希
   和 consistency evidence 哈希一致；OOSM、fixed-lag、双时间戳、covariance、航迹起始/分级、
   observer-scan conflict 和 `global_track_id` 均未改变。
3. **操作数验收通过**：candidate pair 与 innovation solve 均为 371,054；量测模型构造
   `16,457 -> 82`，投影构造 `16,457 -> 14,648`；radar 状态构造和 16,653 次
   `GlobalTrack` 物化保持不变。
4. **模块级结果**：纯融合墙钟 `10.792 s -> 8.635 s`，本机单次 1.25 倍。专项
   `10 passed in 10.33s`，D1 全量 `161 passed in 38.02s`。墙钟不作为脆弱单测阈值。
5. **下一验收**：由 main 在当前代码上复跑 clean 200 规模五 seed 和其他预注册规模，冻结硬件、
   发布频率与配置，比较 P50/P95/max、实时倍率和峰值内存。正式 RMSE/NEES/NIS、AirSim 和
   物理闭环仍独立验收。

第二阶段报告为 `reports/D1_SCAN_ASSOCIATION_PERFORMANCE_BENCHMARK_CN.md` 及对应 JSON。
本轮不改变 AirSim producer、Blocks/ComputerVision/SimpleFlight、reset/episode 编排或持久化
schema，因此 `docs/AIRSIM_INTEGRATION_PLAN.md` 已检查，无需修改。

clean 治理复跑已经完成。提交为 `e4d66db02a0b8f1b867a0e81b4a73de84588426b`；
20/50/100/200 各 5 个 seed，共 20 个 formal episode，每例 136 帧、33.75 s。20/20
`repository_dirty=false`，D1 每例重排 12、拒绝/过旧/溢出 0、峰值缓冲 3、结束缓冲 0、在线
truth 使用 0。200 规模峰值内存五例均值约 40.91 MB，最大 40,926,870 B。输入文件和清单引用
的 60 个制品 SHA-256 均匹配。

该结果关闭 clean/formal 观测治理复跑缺口。快速治理层没有导入完整运行时模块，不计算 EKF
融合精度，也不关闭融合吞吐、AirSim 或拦截效果。

单次 200v200 三维质点全栈 smoke 使用 seed 42000，仿真时长 2.2 s。D1 接收/释放 86 个扫描、
2,051 条观测，重排 10、拒绝 0，峰值缓冲 33 个扫描/623 条观测，尾部缓冲归零。D1 fusion
累计 35.115 s/86 次，平均 408.313 ms；扫描输入整理累计 2.682 s。全栈墙钟 60.210 s，尚未
达到实时运行。该结果没有 AirSim、clean 全栈多 seed 或融合精度验收，继续作为 development
性能基线。

上述单 seed 输入已完成函数级 profile 和语义等价优化：

1. **根因已定位**：未缓存路径中 `_state_at()` 累计 38.120 s、`_replay_record()` 46.097 s，
   `_filter_update()` 被调用 93,234 次；`global_tracks()` 累计 9.856 s，其中传感器健康摘要被
   构造 16,653 次。
2. **增量后验已实现**：每条航迹保存按观测排序的后验检查点。顺序更新复用前缀；窗口内 OOSM
   只失效插入点后的后缀；固定滞后重基、起始观测变化和检查点前 OOSM 清空相关缓存。缓存命中
   仍重建一致性 evidence，不改变每扫描一对一关联。
3. **发布重复工作已消除**：每扫描只生成一次 association、latency 和 sensor-health 公共审计
   快照，再复制到全部 `GlobalTrack`。输出 state/covariance 使用独立副本，外部修改不能污染
   内部检查点或绕过 covariance 限幅。
4. **确定性验收已通过**：相同 86 扫描/2,051 观测上，逐扫描语义、最终航迹和 consistency
   evidence 哈希完全一致；replay filter update 为 `93,234 -> 1,797`，health snapshot 为
   `16,653 -> 86`。未缓存参考 34.701 s，优化路径 9.073 s，加速 3.82 倍。
5. **剩余 P1**：由 main 从 clean commit 运行 20/50/100/200 未见多 seed 的完整全栈基准，冻结
   硬件、发布频率和周期预算，记录 P50/P95/max、峰值内存与实时倍率。正式 RMSE/NEES/NIS、
   AirSim 和物理拦截继续独立验收，不能由本次 D1-only 加速替代。

## 历史 D1-owned 增量与后续计划（2026-07-16）

`LocalImageTrackObservation -> SensorObservation | None` 的 D1-owned 合同适配已完成：
`measured` 严格转换为 EO/pixel，`lost` 不产生量测；双时间戳、2×2 covariance、confidence、
quality flags、visible/infrared 波段和在线安全审计 metadata 均保真。默认 observation ID 与
source lineage 由 sensor/stream/epoch/local ID/量测时刻确定，重复投递可去重。视觉来源只以
namespaced `source_track_key` 累积到 `GlobalTrack.metadata.source_track_ids`，不参与
`global_track_id` 生成或重绑定。

本轮后续计划状态：

1. **D1 合同项已关闭**：适配器对缺失/非法/非半正定 covariance 和 global/truth identity
   fail closed；lost 即使被外部错误附上旧像素也返回 `None`。
2. **验证已完成**：2026-07-16，无随机 seed，专项 13 项、D1 全量 111 项全部通过；接受阈值
   是合法可见光/红外字段逐项保真、非法 covariance/identity 100% 拒绝、lost 0 输出、来源
   集合累积且 global ID 不变。
3. **仍属 main 的集成项**：把 producer 输出接到该 API、验证真实运行时 batch/backend
   metadata 和相机模型，并在 AirSim episode 中确认重复投递计数；这些尚未由本轮 D1 单测
   证明。
4. **AirSim 默认路径不变**：本轮不改变 `simGetDetections`/detector box 来源、launch/reset、
   episode 编排或截图策略，也不新增精度/性能证据。

## 历史权威增量与后续计划（2026-07-15）

真实 AirSim M5N2 已完成 baseline/candidate 各 10 case，共 20 case。在线 identity/state truth
使用均为 0；3,805 个 main-bus tick 中 D1 fusion mean/P95/max 为
`320.00/451.46/1234.88 ms`，是 main-bus 内层主导阶段。现有双时间戳、covariance 和 NED
合同必须保持，不能通过丢弃观测、改写量测时刻或人为收紧 covariance 来换取耗时下降。

本轮计划状态更新如下：

1. **已获得的系统证据**：D1 已进入真实 M5N2 20-case 在线链路，truth identity/state use 为
   0；M5N2 case 与实际执行产物完整。
2. **仍开放的 P1 性能项**：100 ms 系统预算未闭合。后续必须在相同冻结输入上继续拆分
   observation 数量、航迹数量、fixed-lag replay、batch cache、历史窗口和日志开销，再由 main
   复跑多 seed 验收；不得仅以单元基准关闭该项。
3. **仍开放的 P1 精度项**：本批没有提供可用 NIS、NEES、RMSE、sensor-specific latency/
   dropout 或 covariance consistency 证据。需另设带离线 truth sidecar、明确 availability 和
   正确身份映射的传感器标定实验。
4. **停止边界**：统计只含 M5N2 20 case；TERM 前额外完成的 1 个 `png_ttc_2v2_seed001`
   排除，dropout 完成数为 0，均不得补零或并入本计划验收。

后文历史计划继续保留；与上述状态冲突时，以本节和 2026-07-15 main 报告为准。

## 0. 边界与用途

本模块仅用于科研仿真、离线评估和算法可复现实验。输出为带协方差的 `GlobalTrack`，用于态势估计、误差分析和人工复核接口设计。模块不包含真实火控参数、毁伤逻辑、实机飞控或硬件驱动、自动处置流程，也不包含绕过人工授权的控制接口。

## 1. 工程问题与科学问题

工程问题：

- 将雷达、声学、光电三类异构观测标准化为统一 `SensorObservation`。
- 以 `measurement_timestamp` 为滤波更新时间，以 `arrival_timestamp` 记录链路延迟和乱序到达。
- 保留跨节点通信元数据，如 `source_node_id`、`target_node_id`、`relay_node_id`、`link_type`、`sent_timestamp`、`received_timestamp`、`payload_kind`、`stale_after_s` 和 `source_support`。
- 在统一 NED 坐标下维护 `GlobalTrack`，输出状态、协方差、质量等级和传感器支持。
- 对延迟雷达观测进行 fixed-lag 缓存、测量时刻更新和重传播，比较补偿前后误差。
- 在没有 FilterPy、Stone Soup 依赖时，提供可运行的 NumPy/SciPy fallback。

科学问题：

- 距离相关雷达噪声、粗方位声学观测、二维 EO 像素框约束如何共同约束三维运动状态。
- 延迟观测按到达时刻更新与按测量时刻更新并重传播之间的误差差异。
- 协方差传播、NIS 门限、连续性和多源支持如何形成 `coarse`、`stable`、`handover` 分级判据。

## 2. 状态与运动模型

统一滤波状态为：

```text
x = [px, py, pz, vx, vy, vz]^T
```

其中位置和速度均在 NED 坐标系中表达，单位为米和米每秒。

CV 常速度模型作为默认可运行基线：

```text
x_k = F_cv(dt) x_{k-1} + w
F_cv = [[I3, dt I3],
        [03, I3]]
Q_cv = q * [[dt^4/4 I3, dt^3/2 I3],
            [dt^3/2 I3, dt^2 I3]]
```

CA 常加速度模型用于仿真目标生成或后续模型扩展。当前六维状态中不显式估计加速度，CA 通过已知或采样加速度驱动真值轨迹；若后续切换到九维状态，可扩展为 `[p, v, a]`。

转弯模型用于二维水平面协调转弯真值生成或 IMM 扩展。六维滤波 fallback 仍以 CV 预测吸收机动误差；转弯强度通过过程噪声放大表达。

## 3. 观测模型

雷达观测：

```text
z_radar = [range, azimuth, elevation, radial_velocity]^T
```

从雷达位置 `s` 指向目标相对向量 `r = p - s`：

```text
range = ||r||
azimuth = atan2(ry, rx)
elevation = atan2(-rz, sqrt(rx^2 + ry^2))
radial_velocity = dot(v, r / ||r||)
```

雷达协方差随距离增大：

```text
sigma_range = a0 + a1 * range
sigma_angle = b0 + b1 * range / reference_range
sigma_radial_velocity = c0 + c1 * range / reference_range
```

声学观测：

```text
z_acoustic = [azimuth]^T + optional voiceprint/classification_hint
```

声学只作为粗方位约束和身份似然提示，不强制恢复三维位置。观测模型为 `atan2(ry, rx)`，协方差由阵列条件、信噪比和置信度控制。

光电 EO 观测：

```text
z_eo = [u_center, v_center]^T
```

像素框中心经相机内参和外参对应到成像投影：

```text
p_camera = R_world_to_camera * (p_world - camera_position)
u = fx * x/z + cx
v = fy * y/z + cy
```

EO 用作方向/投影约束。小框、低置信度或遮挡时增大像素协方差，避免把二维检测误当三维真值。

## 4. 协方差传播与延迟补偿

预测传播：

```text
x^- = F x
P^- = F P F^T + Q
```

EKF 更新：

```text
y = wrap(z - h(x^-))
S = H P^- H^T + R
K = P^- H^T S^-1
x^+ = x^- + K y
P^+ = (I - K H) P^- (I - K H)^T + K R K^T
```

延迟补偿使用 fixed-lag 状态缓存：

1. 观测到达后按 `measurement_timestamp` 找到对应或最近早于该时刻的缓存状态。
2. 从缓存状态预测到测量时刻并更新。
3. 将更新后的状态按缓存中的后续时间步逐段重传播到当前融合时间。
4. 与未补偿基线对比，后者直接在 `arrival_timestamp` 对当前状态更新。

## 5. 分级判据

基于水平 95% 误差椭圆长轴：

```text
a95 = sqrt(chi2_2_0.95 * max_eigenvalue(P_xy))
```

默认判据：

- `coarse`: `a95 > stable_threshold`，或观测支持不足，或连续性不足。
- `stable`: `a95 <= stable_threshold`，最近窗口内 NIS 通过率达标，且 track continuity 达标。
- `handover`: `a95 <= handover_threshold`，多源一致，连续稳定帧数达到要求。

`handover` 仅表示科研仿真中的高质量配准状态，不代表处置授权。

## 6. 仿真场景

- 时长 60 s，基准频率 10 Hz。
- `--drone-count 3` 保留为历史 baseline；集成运行由 main 的 `--drone-count N` 统一控制目标数量。
- D1 接收 main 提供的 N 个 target truth/观测源，并按输入数组长度处理，不在算法路径写死 2 或 5。
- 目标数为 N，循环覆盖 CV、CA 和水平转弯轨迹。
- 雷达：0.5-2.0 s 随机延迟，10 Hz 或降采样观测，噪声方差随距离增大。
- 声学：粗方位观测，低频率，带声纹/类别提示。
- EO：像素框中心观测，带相机内参、外参、置信度和遮挡/小框噪声放大。
- 输出 RMSE、航迹连续性、分级准确性、延迟补偿前后对比图和 Markdown 报告。

## 7. 模块接口与当前落地状态

核心数据结构：

- `SensorObservation`: 已实现统一观测合同，包含 `measurement_timestamp`、`arrival_timestamp`、`frame_id`、`measurement`、`covariance`、`confidence`、`quality_flags`、`classification_hint` 和通信元数据。当前允许帧为 radar/acoustic/lidar 的 `ned` 与 EO 的 `pixel`；外部 WGS84/ENU/body/camera 坐标必须先转换或带齐外参元数据，不由融合器静默猜测。
- `GlobalTrack`: 已实现全局航迹输出，包含六维 NED 状态、6x6 协方差、`timestamp`、`track_level`、`source_support`、`identity_likelihood`、`last_nis` 和 `metadata`。`metadata` 已写入 `frame_id="ned"`、`valid_at`、`published_at`、`latest_measurement_timestamp`、`latest_arrival_timestamp`、`latest_observation_latency_s`、通信字段和 `a95_m`。
- `TrackUncertaintySummary`: 已实现 D1 下游单航迹质量摘要，包含 `track_id/global_track_id`、`valid_at`、`published_at`、`track_bucket`、`track_level`、位置/速度协方差迹、`a95_m`、`measurement_age_s`、`source_support`、`coverage_cell`、`measurement_timestamp`、`arrival_timestamp`、`covariance_growth_rate`、`source_diversity_count`、`last_nis`、`handover_readiness` 和 `quality_flags`。
- `LatencyAuditSummary`: 已实现 D1 延迟/OOSM 审计摘要，导出 `observation_count`、`max_delay_s`、`mean_delay_s`、`replay_count`、`oosm_observation_count`、`stale_observation_count`、`stale_or_oosm_observation_count`、重复观测数和最大 replay 历史长度。
- `FusionQualityRegionSummary`: 已实现轻量区域质量摘要，按 `coverage_cell` 聚合 `TrackUncertaintySummary[]` 的 track 数、a95、measurement age、handover readiness、source support、source gap、stale track 数和可选协方差增长率，供 D4/D6 做不确定度质量消费。
- `FusionQualityRegionWindowSummary`: 已实现轻量窗口摘要，由 `summarize_region_quality_windows()` 从区域摘要序列和可选 `LatencyAuditSummary` 序列生成，用于区分区域协方差增长、freshness 下降、source gap 和 OOSM/latency。
- `ReconCueSummary`: 已实现面向二级侦察相机粗指向的轻量摘要，由 `summarize_recon_cue_from_tracks()` 从 `GlobalTrack[]` 或 track-like dict 生成；支持按 `coverage_cell` 过滤，并按位置协方差 trace 的倒数加权求 `cue_position_ned`/centroid；可选 metadata 保留二级/移动侦察节点、cue 来源和模式。
- `FusionAdapter`: 已实现融合入口，提供 `process()`、`ingest_many()`、`predict_track()`、`update_at_measurement_time()`、`compensate_latency()`、`global_tracks()`、`track_uncertainty_summaries()`、`latency_audit_summary()`、`region_quality_summaries()` 和 `_bucket()`。
- `RadarCovarianceConfig`: 已实现可配置距离相关雷达协方差，默认参数保持既有测试行为，可用于近/中/远距离消融。

运行入口：

- `src/d1_sensor_fusion/simulation.py`: 离线仿真与指标生成。
- `scripts/run_simulation.py`: 命令行仿真脚本。
- `tests/`: 单元测试和回归测试。
- `src/d1_sensor_fusion/airsim_dry_run.py`: AirSim-like fake fixture 到 `SensorObservation[]` 的 dry-run adapter，不导入 AirSim。
- `src/d1_sensor_fusion/replay.py`: versioned `sensor_observations.jsonl`/legacy `blocks_sensor_observations.jsonl` reader/replay，以及最小 CSV reader/replay；可将 main/AirSim runtime 或人工审计观测记录读回并喂给 `FusionAdapter`。
- `src/d1_sensor_fusion/recon_cue.py`: 从 `GlobalTrack[]`/track-like dict 生成雷达 cue 粗指向摘要，供 main/AirSim runtime 选择目标群或 coverage cell 子群。

兼容接口：

- FilterPy: 仅有 `FilterPyBackendPlaceholder` 可用性探测，不调用 FilterPy EKF/UKF/IMM，不作为当前运行依赖。
- Stone Soup: 仅有 `StoneSoupAdapterPlaceholder` 和 observation 到 detection dict 的转换边界，不导入 Stone Soup，也未接入真实 tracker/fuser/OOSM 后端。
- AirSim: D1 已提供 dry-run fixture adapter 和 Blocks JSONL replay reader；真实 AirSim 连接、Blocks 启停、`simGetDetections` 调用、frame capture、JSONL 写出和 runtime bus 编排属于 main/shared runtime，不是 D1 包内已完成能力。
- ROS 2: 当前未接入 `tf2` 或 `message_filters`。D1 依赖上游完成坐标转换/时间戳填写，并在离线 replay 内用 `arrival_timestamp` 排序和 fixed-lag replay 处理乱序观测。

## 7.1 2026-07-07 运行时与降级接口复核

本轮复核发生在 main runtime bus、D3/D4/D5 P1 修复之后。D1 已补齐本轮数据合同收敛项，但仍需明确下游解释边界：

- main runtime bus 负责把 D1/D2/D3/D4/D5/D7 DTO、summary 和 record 接入真实 AirSim episode 状态机；D1 仍只负责本模块 `SensorObservation[]` replay 和 `GlobalTrack[]`/`TrackUncertaintySummary[]` 输出。
- D3 中心重规划的新 plan owner/version 不由 D1 生成。D1 只提供 `track_level`、`a95_m`、`measurement_age_s`、source support 和 timing metadata，供 D3 计算代价和判断候选质量。
- D4 主动降级已经区分硬风险与软质量风险。D1 的高协方差、低 freshness、source gap 或 handover readiness 下降是质量证据；单帧或短窗口软风险不应直接触发降级，必须由 D4 结合 C2 health、D3 plan freshness、D5 terminal evidence 和持续窗口仲裁。
- D5 终端一致性窗口修复后，D1 继续提供可投影 NED 状态、6x6 协方差、EO bbox/camera metadata lineage 和时间戳；D5 反馈不能改写 D1 的 `global_track_id`。
- 严格模块流程下，D1 owned 文件的 README/PLAN/GAP/review 状态由 D1 子智能体自行维护并运行本模块测试；main 只做跨模块汇总和集成验证。

## 7.2 2026-07-07 P1 数据合同收敛

本轮新增实现保持轻依赖，不接入新的外部包：

- replay schema v1 固化为 `d1.sensor_observation.v1`；未来 `sensor_observations.jsonl` 与 Blocks replay 共用同一 reader。无 `schema_version` 的既有 `blocks_sensor_observations.jsonl` 作为 legacy 兼容输入保留。
- CSV replay 最小实现已落地，要求 `measurement`/`covariance` 以 JSON array 写入单元格，`metadata`/`communication`/`source_support` 以 JSON object 写入单元格。
- latency/OOSM 审计以累计摘要导出；OOSM 口径为到达观测的测量时刻早于已处理融合时间，stale 口径为处理时已超过 `stale_after_s` 或 arrival delay 超过该 stale budget。
- 区域质量摘要已按 `coverage_cell` 轻量聚合，作为 D4/D6 的区域态势质量证据；最终主动降级仲裁仍属于 D4。
- 这些项不再作为未完成 P1 追踪。剩余 P1 聚焦更多 main/shared 真实 Blocks/CV multi-seed fixture、D6 长期批量 schema、持续窗口阈值和真实样本回归。

## 7.3 2026-07-08 P1 AirSim 多 seed 校准准备

本轮 D1 侧复核聚焦 main/shared runtime 写出的真实 Blocks replay 与 D1 reader/test/GAP 状态，不修改 main runtime。结论如下：

- main runtime 已新增 P1 D4/D5 calibration sweep，并在 sweep 结束后自动调用 D6 标准报告 bundle；D1 不生成 sweep、不写 AirSim runtime，只保证自身 replay/schema/latency/OOSM/region quality 字段可被这些报告消费。
- D6 bundle 对 D1 字段的消费口径限定为报告证据：raw/fusion `LatencyAuditSummary`、`TrackUncertaintySummary`、`FusionQualityRegionSummary[]`、`FusionQualityRegionWindowSummary[]`、`SensorHealthSummary[]`、covariance limit reason、`covariance_scale_reason` 和 `timestamp_uncertainty_s`；这些字段不代表 D1 触发主动降级或生成控制决策。
- JSONL replay 与真实 Blocks writer 的顶层字段保持一致：`measurement_timestamp`、`arrival_timestamp`、`frame_id`、`measurement`、`covariance`、`metadata` 和 `communication` 均会进入 `SensorObservation`，并回放成 NED `GlobalTrack`。
- CSV replay 对缺省 `schema_version` 的行按 `d1.sensor_observation.v1` 处理，因此校准 CSV 必须携带 `covariance`；不再通过 legacy 路径静默接收缺协方差 CSV 行。
- EO replay 可使用嵌套 `metadata.camera_model` 字典恢复相机内外参，避免真实 Blocks/CV JSONL 只保留 camera metadata 但投影模型仍使用默认相机。
- 新增 Blocks calibration CSV 回归，覆盖 measurement/arrival timestamps、covariance、NED state、source support、coverage cell、latency/OOSM audit 和 `FusionQualityRegionSummary`。
- 新增 `ReconCueSummary`/`summarize_recon_cue_from_tracks()` 回归，覆盖全部目标 cue、按 `coverage_cell` cue、缺省协方差保守降权和 measurement/arrival timestamp 保留。
- 当前 D1 状态为无 P0 blocker；时间戳、协方差、NED `GlobalTrack`、N-target 输入和侦察 cue 合同均已进入当前回归基线。
- 轻量区域时间窗口和协方差增长率 helper 已落地；剩余 P1 转为继续收集 main/shared runtime 的真实 Blocks/CV multi-seed detection JSONL/CSV 样本、与 D6 对齐长期批量 schema，并基于真实样本确定持续窗口阈值。

## 7.4 2026-07-09 P1 输入支撑补强

本轮不改 D1 主滤波算法，也不接入 Stone Soup、FilterPy、UKF 或 IMM。补强范围限定为 replay/schema/metadata 回归：

- dry-run fixture 增加 `d1.airsim_dry_run_fixture.v1` schema version，生成的 observation metadata 保留 `d1_fixture_schema_version`，并拒绝不支持的 fixture schema version。
- replay 增加 `summarize_sensor_observation_latency_audit()`，可在不运行融合器时从 `SensorObservation[]` 统计 observation latency、OOSM、stale 和重复 lineage，供 main/D6 在长期批处理前做输入审计。
- Blocks/CV JSONL 与 CSV 回归补充 `covariance_scale_reason`、`mobile_recon`、`recon_cue_summary`、`cue_position_ned` 和 `cue_covariance` 保真检查，并验证这些字段能随最新观测进入 `GlobalTrack.metadata`。
- JSONL replay 已补显式 unsupported schema version 回归；CSV 缺省 schema 仍按 `d1.sensor_observation.v1` 处理并要求 covariance。
- 本轮未重新打开 P0-A：`SensorHealthSummary`、观测/航迹 covariance floor/ceiling reason 和 `timestamp_uncertainty_s` 已作为 D1 质量字段保持回归，并纳入 main/D6 消费口径。

## 7.5 历史基线：2026-07-10 main episode bus / AirSim 2v2 合同复核

本轮只读取 main/shared runtime 代码和
`research_modules/airsim_runtime/outputs/p1_gap_closure_2v2_smoke_20260710/` 产物，不修改
main/runtime。六个 reset-separated episode 共 1,528 条 radar/acoustic/EO/synthetic-lidar
观测均可由 D1 reader 解析；所有观测保留 `measurement_timestamp`、
`arrival_timestamp` 和有限、对称、半正定 covariance，未发现到达时刻早于量测时刻的
记录。full-flow 的 36 个 main bus tick 均保留 D1 观测双时间戳和 covariance trace，
`TrackUncertaintySummary` 继续保留 timing/covariance 字段，运行时按 truth-hint 仿真配置
维持 2 条 D1 航迹。因此本轮未发现 D1 双时间戳、协方差或 NED 航迹合同回归。

真实产物同时确认以下 P1 尚未闭合：

- main Blocks writer 尚未写 `schema_version`，新产物当前仍通过
  `legacy.blocks_sensor_observations` 兼容路径读取；D1 v1 reader 已就绪，但 writer 采用
  显式 `d1.sensor_observation.v1` 仍属于 main/shared 集成工作。
- 观测未携带 `coverage_cell`，D1 区域摘要只能输出 `unassigned`；main tick 目前只发布
  `TrackUncertaintySummary[]`，尚未发布区域/窗口、latency audit 和 sensor health 摘要，
  因而真实 smoke 尚未完成区域质量闭环验收。
- 固定 0.2 s 延迟、多传感器同帧顺序处理会产生大量合法 OOSM 计数；当前 advisory
  sensor-health 阈值若直接查询会把正常固定延迟流标为 `isolated`。后续需区分 expected
  latency/OOSM 与异常 clock/stale evidence，并用多 seed 正常/故障样本标定；在此之前
  D4/D6 不得把该状态直接当作降级动作依据。
- main bus 当前以 `use_truth_hints_for_association=True` 的仿真配置维持 2 条航迹；同一
  JSONL 用 D1 默认无 truth-hint replay 会产生 3 条航迹，其中 TGT-002 出现重复初始化。
  后续需把关联配置写入 replay provenance，并用无真值门控/关联校准实现运行时与离线
  replay 一致；truth metadata 只能用于离线评估，不能成为真实在线身份依据。
- 单次 2v2 smoke 已从“只有 dry-run/手工 fixture”推进到真实产物审计，但仍不足以关闭
  N actor、多 seed、CV detection、区域窗口和长期 D6 schema 的 P1 校准项。

## 7.6 历史基线：2026-07-10 十 seed 与 truth-isolation 证据同步

main 随后完成了
`research_modules/airsim_runtime/outputs/p1_gap_closure_2v2_multiseed_20260710/` 的 10-seed
2v2 系统运行，以及
`research_modules/airsim_runtime/outputs/p0_truth_isolation_smoke_20260710/` 的在线身份隔离
smoke。前者证明 D1 合同已被连续用于多 seed episode 编排；后者证明 D5 在线局部检测/
MOT 标识不再依赖 actor/object 名称。两项均是 main/shared 集成证据，不替代 7.5 节对
1,528 条 D1 观测的逐条时间戳/协方差审计，也不代表 D1 无真值关联已经闭合。

truth-isolation smoke 的 D1 合成观测仍可携带 `truth_id` 作为离线评分标签，main bus 的
融合配置仍可启用 simulation-only truth hint。D1 的验收边界保持不变：在线算法不得把
该标签作为身份依据；下一阶段仍需把 fusion/association 配置写入 replay provenance，
并用无 truth-hint 的多 seed replay 校准重复初始化与关联一致性。10-seed 运行产物尚未被
固化为覆盖 schema version、coverage cell、CV bbox covariance 和二级侦察 metadata 的
D1 长期 fixture，因此这些 P1 不能仅凭系统运行次数关闭。

## 7.7 历史基线：2026-07-11 5v5 在线 truth 隔离与 governance 证据

main 完成
`research_modules/airsim_runtime/outputs/p1_runtime_truth_isolated_d4d5_smoke_20260711/`
三个 reset-separated 5v5 episode，分别覆盖不降级、降级到二级节点和降级到完全分布式。
每个 episode 为 seed 7、5 帧、0.4 s 短时 smoke。三组运行中 D1/D2/D3 模块健康均为
`ok`，D1 每组发布 15 条模块记录，D3 assignment coverage 为 1.0，证明 main 在线隔离
truth hint 后，D1 -> D2 -> D3 仍能以中心 `global_track_id` 和状态/协方差继续工作。

`main_episode_bus_metrics.json` 已消费 D1 governance：每组均生成
`d1_latency_audit` 和 `d1_region_quality_window` 事件，并报告
`d1_max_delay_s` 约 0.2 s、`d1_region_quality_coverage_rate=1.0`。因此此前“main bus 尚未
发布任何 D1 region/window/latency governance”的状态已被这次短时接线证据部分关闭。
是否长期保留完整 `SensorHealthSummary`、covariance reason、timestamp uncertainty 及
schema/version 字段，仍需更长 episode 和 D6 批量 schema 审计。

三组运行的 `d1_oosm_observation_rate` 均约为 0.9867。该值来自固定延迟、多模态观测按
到达顺序逐条进入 fixed-lag replay 的当前累计口径，表示绝大多数后续到达的量测时刻早于
已推进融合时刻，不表示约 98.7% 的传感器发生故障。D4 只能消费 unexpected OOSM、stale、
延迟预算超限和持续窗口等已校准证据，不能直接按 raw OOSM rate 降级。

本证据只关闭 truth-isolated 运行时接线的单 seed smoke 风险，不关闭 P1 multi-seed 校准。
扫描级水位线 API 已于 2026-07-22 形成独立、版本化、有限缓冲的 fail-closed 合同。下一步仍需
main 正式接线，并用多 seed、长时窗口、不同传感器延迟分布和正常/故障对照校准 lateness、
驻留时间、OOSM、区域质量和 handover readiness 告警阈值。

## 8. 交付物

- `PLAN.md`: 本实施计划。
- Python 源码：数据结构、运动模型、观测模型、NumPy EKF、融合适配器、dry-run adapter、JSONL replay、仿真和指标。
- 单元测试：RMSE、track continuity、分级准确性、延迟补偿前后对比、接口行为、通信元数据、source lineage 去重、TrackUncertaintySummary、LatencyAuditSummary、FusionQualityRegionSummary、ReconCueSummary、协同 bearing 1/2/3/N 几何、CI 保守性、AirSim dry-run、Blocks JSONL/CSV replay 和 N actor 合同。
- 仿真脚本：按 `--drone-count N` 生成 N 个目标、60 s、10 Hz 的雷达/声学/EO 观测；历史 3 目标输出仅作为 baseline。
- 图表和 Markdown 实验报告：输出到 `reports/`。
- AirSim 集成计划：统一时间轴、坐标、传感器桥接和离线评估流程；不宣称真实雷达/声学/LiDAR 硬件仿真已接入。

## 9. 已实现、部分实现、未实现对照

### 9.1 已实现能力

- **时间戳合同**: `SensorObservation` 强制保留 `measurement_timestamp` 和 `arrival_timestamp`；`FusionAdapter` 用测量时刻做滤波更新，用到达时刻推进当前时间、记录延迟和排序 replay。`GlobalTrack.metadata` 与 `TrackUncertaintySummary` 已暴露最新测量/到达时间。
- **协方差合同**: 观测侧支持 radar 4x4、legacy acoustic 1x1、scalable `acoustic_3d` 2x2、EO 2x2、synthetic lidar 3x3 协方差；航迹侧输出 6x6 状态协方差；分级与摘要使用水平 95% 误差椭圆 `a95_m`、协方差迹和 NIS。
- **NED 工作帧**: 雷达、声学和 lidar 观测在 `frame_id="ned"` 下进入融合；EO 以 `frame_id="pixel"` 和相机模型元数据作为投影约束；`GlobalTrack` 固定输出 NED 六维状态。WGS84/ENU 仅作为上游外部参考，不在 D1 内直接滤波。
- **雷达观测适配**: 已实现 `[range, azimuth, elevation, radial_velocity]` 观测模型、角度 wrap、雷达初始化航迹、距离相关测量协方差和 radar observation 到六维初始状态/协方差转换。
- **声学观测适配**: 已实现粗方位角观测、置信度相关角度协方差和 `classification_hint` 累计；声学不会单独初始化三维航迹，也不会单独把航迹提升为 `handover`。
- **视觉/EO 观测适配**: 已实现 pinhole 像素投影约束、bbox/置信度/遮挡/小框驱动的像素协方差放大；D1 只消费 bbox、中心像素、相机元数据、时间戳和协方差，不要求 PNG 截图。
- **GlobalTrack 输出**: 已实现 `global_track_id`、位置、速度、协方差、质量等级、source support、身份似然、NIS 和元数据输出。`global_track_id` 由 D1/FusionAdapter 创建并作为下游中心化 track ID 使用；D5/D7 不应本地改写。
- **侦察粗指向摘要**: 已实现 `ReconCueSummary` 和 `summarize_recon_cue_from_tracks()`，从 `GlobalTrack[]`/track-like dict 按输入数组长度生成目标群或 `coverage_cell` 子群的 `cue_position_ned`、`cue_covariance`、`active_target_ids`、时间戳和基础诊断；缺协方差时使用保守默认并显式计数。
- **延迟补偿**: 已实现 fixed-lag/OOSM replay。延迟观测按 `measurement_timestamp` 插入历史观测序列，重放到当前 `arrival_timestamp`；测试覆盖延迟观测关联和补偿 RMSE 优于未补偿基线，并导出 max/mean delay、replay count、OOSM/stale count 审计摘要。
- **AirSim adapter/dry-run 支持**: 已实现无 AirSim 依赖的 fake fixture adapter，可生成 radar/acoustic/EO/synthetic lidar `SensorObservation[]` 并喂给 `FusionAdapter`；已实现 Blocks JSONL reader/replay、schema v1/legacy 兼容、CSV replay 和 N actor JSONL 合同测试。
- **输入规模**: `generate_truth(target_count=N)` 与 CLI `--drone-count N` 按输入数量运行，不裁剪到 2v2/5v5；2v2、5v5、3-target 只作为 baseline 名称或样例。

### 9.2 部分实现能力

- **AirSim/Blocks 集成**: D1 包内只完成 dry-run adapter 与 JSONL replay；真实 AirSim Blocks episode 启停、`simGetDetections`、frame capture、actor target 移动、runtime bus 和 JSONL 写出由 main/shared runtime 负责。D1 当前可消费这些输出，但不直接连接 AirSim。
- **EO/视觉几何**: D1 有简单 pinhole 投影和 camera metadata 约定；未接入 OpenCV 标定、畸变校正、`solvePnP`、`projectPoints` 或 D5 级跨视角几何一致性。
- **合成 LiDAR**: synthetic lidar 只是 dry-run/replay 里的 NED 三维位置测量模型，用于测试融合合同；不是 AirSim LiDAR plugin，也不是硬件驱动。
- **质量摘要**: `TrackUncertaintySummary` 已是单航迹摘要；`FusionQualityRegionSummary` 已提供按 `coverage_cell` 聚合的轻量区域质量摘要；`FusionQualityRegionWindowSummary`/`summarize_region_quality_windows()` 已提供区域时间窗口趋势；`annotate_covariance_growth_rates()` 已提供协方差增长率差分；`ReconCueSummary` 已提供面向二级侦察相机的目标群/coverage cell 粗指向摘要；latency/OOSM replay 计数已可导出。D6 长期批量日志 schema、真实样本阈值和更多 NIS 统计仍需后续对齐。
- **source lineage 去重与 CI**: 观测主线已能抑制同一 source/sequence/payload 经 relay 重复投递；独立 `cooperative.py` 也已实现 message UUID/完整 source-lineage 去重和未知交叉相关下的最小 CI。多节点 runtime 接线、部分共享 lineage 建模和分布式共识仍未实现。
- **replay 合同**: versioned `sensor_observations.jsonl` reader、legacy `blocks_sensor_observations.jsonl` 兼容、真实 CV bbox/camera/detection/recon metadata 字段保真和最小 CSV reader 已实现；长期 main/shared 真实 Blocks/CV multi-seed fixture 回归仍未完成。

### 9.3 未实现能力

- **Stone Soup**: 未接入真实 Stone Soup tracker、updater、initiator、JPDA/MHT、OOSM 或 Track Fusion；当前只有不导入依赖的占位类。原因是当前阶段需要轻依赖、可复现、离线测试稳定，且尚未定义 Stone Soup 与 D1 dataclass 的完整转换和对照指标。
- **FilterPy**: 未调用 FilterPy EKF/UKF/IMM；当前只有可用性探测占位。原因是 D1 已有 NumPy EKF fallback，新增后端需要测试容差、版本约束和 UKF/IMM 对照场景。
- **ROS 2 `tf2`**: 未实现坐标树、外参版本化 tf buffer 或时间化 transform。原因是仓库当前没有 ROS 2 runtime/topic/bag 条件，D1 只规定 NED 输入和 camera metadata 边界。
- **ROS 2 `message_filters`**: 未实现 ROS topic ApproximateTime/ExactTime 同步。原因是当前 D1 运行在离线 `SensorObservation[]`/JSONL replay 层，已用 `measurement_timestamp`、`arrival_timestamp` 和 fixed-lag replay 处理乱序；ROS 同步要等 topic schema 稳定。
- **UKF/IMM 与完整 Track-to-Track runtime**: 强非线性 UKF、多模型 IMM、跨 D2/runtime 的多节点 track-fusion 流程尚未实现；NumPy CI 数值 helper 已完成，不等于 Stone Soup 后端或分布式全链路。
- **真实传感器硬件仿真**: 未实现真实雷达、声学阵列、LiDAR 硬件仿真或 AirSim sensor plugin 级接入；当前雷达/声学/lidar 为科研合成观测，EO 依赖上游检测框/metadata。

## 10. 对后续模块的影响

- **对 D2 数据关联**: D1 已提供 NED `GlobalTrack[]`、协方差、`global_track_id`、source support、latest measurement/arrival timestamp 和可选 truth metadata。D2 应使用这些字段进行中心关联和 `id_switch_count` 统计，不应把 2v2/5v5 当作算法规模限制；真实 AirSim truth ID 只能作为离线评估标签。
- **对 D3 分配规划**: D3 可用 `track_level`、`a95_m`、协方差、`measurement_age_s` 和 `source_support` 判断分配候选质量。D1 不生成 `AssignmentPlan`，也不处理 stale plan；D3 仍需按版本化计划拒绝过期输入。
- **对 D4 主动/被动降级**: `TrackUncertaintySummary`、`LatencyAuditSummary` 和轻量 `FusionQualityRegionSummary` 可作为中心态势质量信号；`ReconCueSummary` 只给 main/runtime 粗指向目标群或 coverage cell 子群，不给出最终主动降级建议。D4 应结合 C2 health、D3 版本、D5 反馈和链路状态做最终降级仲裁。
- **对 D5 末端关联**: D1 输出的 `global_track_id`、NED 状态、6x6 协方差、EO bbox/camera metadata lineage、时间戳和可选 `ReconCueSummary` 粗指向可供 D5/main 做相机指向与投影门控。D5 不得改写或本地重绑定 `global_track_id`；终端 truth ID 只能离线评估使用。
- **对 D6 评估指标**: D6 可消费 RMSE、连续性、分级准确性、延迟补偿消融、`TrackUncertaintySummary`、`FusionQualityRegionSummary`、`FusionQualityRegionWindowSummary`、`LatencyAuditSummary` 和 source diversity；后续需要 D1/D6 共同稳定长期批量日志 schema 和真实多 seed 持续阈值。
- **对 D7 导引**: D7 应只把 `stable` 或 `handover` 级 `GlobalTrack` 作为离线中段导引输入，并按协方差/新鲜度扩大门限或请求重规划。D1 不提供飞控、毁伤或自动处置接口。

## 11. 历史计划基线：2026-07-10 下一步优先级

### P1: 当前主线补强

已完成的 P1 基线：

1. D1 replay schema v1 已固化，`blocks_sensor_observations.jsonl` 与未来 `sensor_observations.jsonl` 已共用 reader，legacy 无版本 Blocks JSONL 已兼容。
2. 最小 CSV reader/replay 已落地，D6/人工审计可复用同一批观测记录；缺省 `schema_version` 的 CSV 行按 v1 验证并要求 `covariance`。
3. `LatencyAuditSummary` 已导出 max/mean latency、OOSM replay、stale、duplicate 和 replay history 计数。
4. `FusionQualityRegionSummary` 已在 `TrackUncertaintySummary` 基线之上按 `coverage_cell` 聚合 source gap、freshness、a95、handover readiness 和 stale track count。
5. source lineage de-dup、Blocks JSONL replay、N actor 合同、嵌套 EO camera metadata replay、ReconCueSummary 和 Blocks calibration CSV 字段保真已进入测试基线。
6. 真实 Blocks/CV 风格 JSONL 字段保真、`annotate_covariance_growth_rates()` 和 `summarize_region_quality_windows()` 已进入轻量测试基线，覆盖 bbox/camera/detection/secondary recon metadata、source gap、freshness、协方差增长和 OOSM/latency flags。
7. dry-run fixture schema 检查、raw replay latency/OOSM audit helper、`covariance_scale_reason` 和 secondary/mobile recon cue metadata 保真已进入 P1 输入支撑回归。
8. 中心化协同定位 P1 数值基础已完成：typed DTO、2..N bearing-ray WLS、几何/时间/covariance 保守门控、共同估计时刻传播和 source-aware CI 均保持为独立 helper，不改变 `FusionAdapter` 默认路径。

剩余 P1：

1. main/shared Blocks writer 显式写入 `schema_version="d1.sensor_observation.v1"` 和 `coverage_cell`；D1 保持 legacy 读取兼容，不跨边界修改 runtime。
2. main episode bus 与 D6 长期 JSONL/CSV schema 发布并对齐 `LatencyAuditSummary`、`FusionQualityRegionSummary[]`、`FusionQualityRegionWindowSummary[]`、`SensorHealthSummary[]`、covariance reason 和 timestamp uncertainty；已发布的 `TrackUncertaintySummary[]` 不再列为缺口。
3. 使用正常延迟和故障注入多 seed 样本校准 expected-latency/OOSM 健康阈值，避免固定 0.2 s 合法延迟触发错误隔离建议。
4. 将 fusion/association 配置写入 replay provenance，完成无 truth-hint 多 seed replay，校准重复初始化和在线/离线关联一致性；truth metadata 仅保留为离线评分标签。
5. 将现有十 seed 运行扩展并固化为 D1 Blocks/CV fixture，覆盖 N actor、camera metadata、bbox covariance、`coverage_cell` 和 secondary/mobile recon cue metadata。
6. 基于上述真实 fixture 校准区域窗口、freshness/source-gap、协方差增长率和 handover readiness 的持续阈值，并保持 NumPy EKF、fixed-lag replay、NED、双时间戳和协方差合同不退化。

### P2: 可选算法和开源对照

1. 以可选后端方式接入 FilterPy EKF/UKF 对照，不替换现有 NumPy fallback；先定义同一观测序列下的误差、协方差和运行时间容差。
2. 以离线实验方式接入 Stone Soup，优先验证 OOSM、JPDA/MHT 或 Track Fusion 的指标收益，不把 Stone Soup 作为主运行依赖。
3. 增加 UKF/IMM 高机动目标基准，明确何时值得从六维 CV/EKF 升级到多模型或非线性滤波。
4. 与 D5 对齐 OpenCV calibration/projectPoints/solvePnP 的责任边界：D1 保持融合合同，D5 负责精细视觉几何时，双方通过相机元数据和投影残差测试对齐。
5. 等 ROS 2 runtime、topic schema、tf tree 和 bag/replay 工具稳定后，再评估 `tf2` 与 `message_filters` 接入；接入前 D1 继续要求上游提供 NED 或完整外参元数据。

## 12. 2026-07-11 P1 Replay/Schema 治理执行结果

本轮在 D1 边界内完成以下工作，不连接 AirSim SDK，也不引入 Stone Soup/FilterPy：

1. 新增 JSONL/CSV governed writer，强制写 `d1.sensor_observation.v1` 和场景/配置 provenance；旧无版本 Blocks reader 继续兼容。
2. writer 默认剥离在线 `truth_id`、actor/object ID；离线标签只有显式启用后才进入 `offline_truth`。
3. `SensorTimingExpectation` 和 `SensorHealthSummary` 已区分预期延迟、延迟预算超限、总 OOSM 与 unexpected OOSM，避免固定延迟流仅因合法 OOSM 被误判隔离。
4. `summarize_region_quality_windows(window_size_s=...)` 已按 `coverage_cell` 和固定时间桶输出窗口，并按 `LatencyAuditSummary.published_at` 对齐延迟/OOSM 证据。
5. 固化真实 Blocks/CV 字段形态的 JSONL/CSV fixture；无 truth-hint 两目标 replay 输出两条带 6x6 协方差的 NED 航迹。

本轮已关闭的 D1-owned P1：writer schema/provenance、expected-latency/OOSM 字段、区域固定窗口、协方差增长窗口、基础 truth-free replay fixture。最新验证中 main episode bus 已接入 governed writer，并把在线 truth 与离线评分标签分离；真实多 seed 延迟门限、视觉 bbox/camera fixture 和关联门限继续由后续 AirSim 校准闭合。

## 13. M 对 N 协同定位调研后的 P1 计划补充

专项证据见 `subagent_reviews/D1_M_TO_N_COOPERATIVE_LOCALIZATION_REVIEW.md`。当高威胁目标由 3 架无人机共同观测时，D1 不要求严格同帧或同时到达，而要求所有观测按 `measurement_timestamp`、平台测量时刻位姿和运动模型传播到共同估计时刻。三机数量本身不保证可观测性，必须检查视线交会角、联合信息矩阵秩/条件数、重投影残差和传播后 covariance。

本项不新增 P0 blocker。2026-07-11 实施后的状态拆解为：

1. **D1-owned 基础已完成**：`CooperativeBearingObservation`、`CooperativeObservationGroup` 和 `CooperativeLocalizationSummary` 覆盖共同估计时刻、observer/source lineage、平台位姿/外参 covariance、measurement skew、LOS 交会角、信息矩阵 rank/condition、残差和拒绝原因。
2. **构造性基准已完成，真实 replay 待补**：单元测试覆盖 1/2/3/N observer、良好三视角不劣于最佳双视角、近共线拒绝、0.4 s 异步传播和 covariance 膨胀；near-synchronous/range、机动、遮挡、节点退出、AirSim 多 seed 及 RMSE/NIS/NEES 仍需 replay。
3. 与 D2 固化边界：D1 负责时间/坐标/协方差和已关联状态的数值融合；D2 负责 local-track-to-`global_track_id` 关联、身份连续性与 IDSW。D2 未确认同一目标时 D1 不做跨平台 Track-to-Track 融合。
4. **最小 CI helper 已完成**：支持 1/2/3/N 个同 canonical ID 的 6-state NED estimate、共同时间 CV 传播、process/timing noise、message UUID/完整 lineage 去重；已验证 CI covariance 不比错误独立融合更自信。部分 lineage 相关性模型、D2/runtime 接线和成员退出 replay 仍待补。
5. Stone Soup CI、GTSAM/OpenCV triangulation 仅作离线 benchmark；外部库正式接入、ROS 2 和主运行时替换仍保持既有后置优先级，不改当前 NumPy EKF 主线。

物理拦截的同时到达、分波次到达和三机任务联盟属于 D3/D7；D1 只提供共同估计时刻的目标状态、协方差和协同几何质量。

## 14. 历史基线：2026-07-11 M-to-N 三 seed 证据与后续实施顺序

最新系统证据为
`research_modules/airsim_runtime/outputs/blocks_cv_m5_n2_liveness_batch_20260711/M_TO_N_AIRSIM_CONVERGENCE_REPORT_CN.md`。
seeds 7/17/27 均记录 6 次中心重规划请求、6 次 no-change ACK、0 次 applied、0 次 expired；
需求满足率均为 1.0，错误重复锁定均为 0。T002 视觉共识帧为 4/5/4，D7 每个 seed
获得 2 次终端合同许可；T001 双 primary 共识三组均为 0，仍是系统 P1。该试验运行于
ComputerVision 模式，只证明 D1 数据合同被 M-to-N 状态链消费，不证明 D1 已完成真实
传感器标定，也不表示完成物理拦截。

当前状态分层如下：

- **P0 已闭合并保持回归**：双时间戳、NED、观测/航迹 covariance、FDIR-light、
  covariance floor/ceiling、timestamp uncertainty、source lineage 去重和 N-target 输入无
  运行级 blocker。当前 D1 回归基线为 `62 passed`。
- **P1 接口已完成**：governed replay/schema/provenance、truth-label 默认剥离、区域/窗口
  质量摘要、expected-latency/OOSM 字段、侦察 cue、协同定位 typed DTO、2..N bearing WLS
  和保守 CI 数值 helper 已落地。
- **P1 待实现或真实标定**：main/shared 采用 governed writer；D1/D2-confirmed
  association-to-fusion runtime 接线；真实多 seed 的机动、遮挡、节点退出、相机 bbox、
  传感器延迟和故障注入 replay；RMSE/NIS/NEES consistency、区域/健康持续阈值、
  IMM/CV-CA-CT 和场景自适应 covariance 标定；D6 长期 schema 对齐。T001 双 primary
  共识由 D5/D7 主责，D1 仅提供其所需的时间化状态、协方差和几何质量。
- **P2 optional benchmark**：FilterPy、Stone Soup、OpenCV/GTSAM 和 ROS 2 只在隔离环境
  做对照或后置评估，不替换当前 NumPy EKF/fixed-lag 默认路径。

后续实施顺序固定为：

1. main/shared 接入 D1 governed replay writer，并把场景配置、seed、coverage cell 和离线
   truth 分离规则写入 replay manifest。
2. D1 与 D2 固化 local-track-to-canonical-ID 确认合同，再把 cooperative WLS/CI 接入可选
   runtime adapter；关联不唯一时保持不融合。
3. main 采集 ComputerVision/AirSim 多 seed replay，覆盖 crossing、机动、遮挡、漏检、
   传感器延迟和节点退出；D1 校准 covariance、OOSM/health、区域窗口及 RMSE/NIS/NEES。
4. 在 P1 数据和验收口径稳定后，启动 FilterPy/Stone Soup 等离线 P2 benchmark；第三方
   后端不可用时必须报告 `unavailable`，不得静默替代为当前实现。
5. 每轮实现后运行
   `PYTHONPATH=research_modules/d1_sensor_fusion/src pytest -q research_modules/d1_sensor_fusion/tests`，
   并由 D1 owner 更新 README、PLAN、GAP 和 review。

## 15. Governed Replay Manifest/Serializer P1 实施结果

D1-owned 严格回放合同已经实现，不直连 AirSim，也未修改 main/runtime：

- `ReplayProvenance` 在原有 scenario/config ID、scenario version 和 config digest 基础上增加
  `scenario_digest` 与 `config_version`；严格 governed 路径同时要求非空 seed。
- `serialize_governed_replay()` 一次性生成 JSON-safe manifest 与在线 records。manifest 固定为
  `d1.governed_replay_manifest.v1`，包含 observation schema、NED fusion working frame、双时间
  范围、coverage cells 和逐观测 opaque source lineage。
- 严格校验拒绝缺失 coverage cell/covariance、非有限或倒序时间戳、维度不匹配/非对称/非
  半正定 covariance，以及缺失 scenario/config identity/version/digest/seed 的 provenance。
- 默认在线序列化递归剥离 truth/actor/object ID；source lineage 使用观测内容摘要，不能通过
  fallback fingerprint 泄漏 truth。`serialize_offline_governed_replay()` 是显式 offline-only
  标签出口，标签只进入 `offline_truth`。
- 旧无版本 Blocks JSONL 继续由 legacy reader 兼容；兼容读取不等于满足严格 governed 合同。

单元测试覆盖多目标批次、manifest JSON 序列化、字段缺失拒绝、legacy 兼容、深层 truth
剥离、显式离线标签、双时间戳、NED working frame、covariance 和 source lineage 往返保真。
当前全量结果为 `62 passed`。最新 main episode bus 已采用该 API，并在 governed manifest
中提供 scenario/config provenance、seed 和 coverage cell；下一步不再重复实现 serializer，
而是用更长的真实 multi-seed replay 校准 D1 统计与阈值。

## 16. 当前状态与后续项（2026-07-11 最终验证）

最终依据为
`research_modules/airsim_runtime/outputs/p1_p2_validation_20260711/P1_P2_VALIDATION_SUMMARY_CN.md`。

- **P1 合同层已闭合**：main episode bus 已携带 D1 governed replay、双时间戳、covariance
  和 lineage；在线记录剥离 truth/actor/object identity，truth 只进入独立离线评分标签。
- **ComputerVision 合同验收已通过**：10 seeds 中 8/10 达到 T001 双 primary 合同阈值。
  二级和完全分布式 3/3 ACK commit 正例通过，缺 ACK 的 2/3 case abort 并 fail-closed。
  这些是 D1 数据合同进入下游链路的系统证据，不扩大 D1 的分配、联盟或控制职责。
- **P1 物理/长期标定仍开放**：SimpleFlight 15 s 仅作断点诊断，30 个 active pair 均未命中；
  该结果不能解释为 D1 融合精度验收，也不能用于关闭真实传感器、多 seed 长 replay、
  sensor-specific latency/health/window 或 RMSE/NIS/NEES 标定。物理拦截闭环由 main/D7 等
  系统链路负责，D1 只对状态、协方差、时间和质量证据负责。
- **P2 隔离 benchmark 已收敛到可审计状态**：D1 冻结 governed replay 已对当前 NumPy
  EKF/fixed-lag 路径输出 RMSE/NIS/NEES/耗时。当前环境未安装 FilterPy 或 Stone Soup，两个
  adapter 均输出 `status=unavailable`、空指标和 `unavailable_reason`；未伪装为当前实现，也未
  加入默认 requirements。UKF/IMM 和第三方可执行 tracker/fuser 仍未实现。
- **adapter/smoke/研究近似边界**：D1 AirSim dry-run adapter、静态 JSONL/CSV fixture 与
  ComputerVision 合同验收只证明接口和 truth policy 可运行；当前合成 radar/acoustic/EO
  观测、CV/EKF 机动吸收及 WLS/CI 数值 helper 属科研仿真基线，不能替代真实传感器标定、
  长时 AirSim replay 或完整分布式 Track-to-Track 后端。

当前 D1 后续项不再包含 governed writer 接入、在线 truth 隔离或 CV 双 primary 合同闭合。
保留的工作是 D1/D2-confirmed cooperative runtime 验证，以及真实多 seed 的机动、遮挡、
节点退出、camera/bbox 和 sensor-delay replay；据此完成 RMSE/NIS/NEES、sensor-specific
expected latency、health/region window、模型集和场景自适应 covariance 标定。15 s
SimpleFlight 诊断不能替代这些更长时、带故障对照的 replay。

## 17. P2 隔离滤波基准收敛结果

本轮复用现有 governed replay 和 `FusionAdapter`，没有重复实现在线观测类型、serializer 或
滤波主线。静态 fixture 固定 scenario/config digest、seed、双时间戳、NED frame、观测
covariance 和 source lineage；在线 records 不含 truth，六状态 truth 只位于独立
`offline_truth` sidecar 并在滤波完成后用于 RMSE/NEES 评分。

当前路径在六条 radar 观测上的一次验证结果为 RMSE `0.2335 m`、mean NIS `0.0426`、mean
NEES `0.0651`、两次 wall time 为 `6.9-10.1 ms`。耗时是主机相关观测值；低 NIS/NEES 表明该小型合成
fixture 下 covariance 偏保守，不能用于关闭真实多 seed consistency 标定。FilterPy 与 Stone
Soup 在当前环境均不可导入，因此只记录 unavailable 状态和原因，不生成第三方指标。

P2 当前关闭的是“无审计输出的可用性探测”缺口；仍开放的是安装于隔离环境后的真实可执行
adapter 对照，以及 UKF/IMM/OOSM/JPDA/MHT 等收益评估。默认 requirements、在线 D1 和
NumPy EKF/fixed-lag 路径均未改变。全量回归为 `62 passed`。

## 18. 2026-07-12 P0/P1 文档状态同步

本节依据当前 `HEAD=33e6fa0` 的 D1 源码与测试、
`subagent_reviews/MAIN_IMPLEMENTATION_GAP_AUDIT.md` 和
`research_modules/airsim_runtime/outputs/PNG_DELIVERY_ENHANCEMENT_AIRSIM_VALIDATION_REPORT_20260712.md`
同步当前状态。`33e6fa0` 未修改 D1 源码、测试或既有能力；本轮 PNG delivery 实现与实测属于
D5/D6/D7 和 main/runtime。D1 在该轮没有行为变化，P0/P1 保持原状态，不因 2v2 `20/20`、
锁定后两帧 dropout 或 M5N2 `0/9` 新增或关闭融合能力。2026-07-12 重新执行 D1 指定测试，
结果为 `62 passed in 11.60s`。

### 18.1 P0 当前状态

| P0 项 | 当前状态 | 2026-07-12 证据与下一验收 |
| --- | --- | --- |
| 双时间戳、NED 与 covariance 合同 | 已实现，保持回归 | `SensorObservation`、`GlobalTrack`、governed replay 和现有接口测试继续覆盖；下一验收仍要求观测/航迹双时间戳、NED 六状态和有限、对称、半正定 covariance 不退化 |
| fixed-lag/OOSM、source lineage 去重与 N-target 输入 | 已实现，保持回归 | 当前 62 项回归通过；下一验收要求乱序补偿、relay 重发去重和按输入数组长度处理继续通过，且 online path 不使用 truth/actor/object ID |
| FDIR-light、covariance 上下界和 timestamp uncertainty | 已实现，保持回归 | `SensorHealthSummary`、limit reason 和 timing uncertainty 字段无变化；下一验收要求正常预期延迟不被误判为故障，故障注入仍输出可解释 reason/recovery evidence |

当前没有 D1 运行级 P0 blocker。PNG delivery 报告没有修改或重新验收 D1 滤波精度，因此其
物理成功/失败数字只作为下游系统证据，不作为 D1 P0 状态变化依据。

### 18.2 P1 当前状态与下一验收

| P1 项 | 当前状态 | 开放缺口 | 下一验收条件 |
| --- | --- | --- | --- |
| governed replay/schema/provenance 与 online truth 隔离 | 已实现并已被 main episode bus 采用；本轮无行为变化 | 需要更长真实 replay 持续验证，而不是重复实现 serializer | 冻结 scenario/config version、digest、seed、coverage/lineage；多 seed online records 保持 truth-free，offline label 只用于评分 |
| 区域/窗口质量、expected-latency/OOSM、sensor health 与 recon cue | 接口和构造回归已实现；真实阈值部分实现 | 缺 sensor-specific 正常/故障对照、长窗口和 D6 长期趋势校准 | 在多 seed radar/acoustic/EO 延迟及 fault injection replay 中量化误报/漏报，稳定发布 health/region/window/covariance reason/timing uncertainty |
| 协同 bearing WLS 与保守 CI | D1-owned typed DTO 和数值 helper 已实现；runtime 全链路部分实现 | 缺 D2-confirmed canonical-ID adapter、真实多节点 replay、部分共享 lineage 和节点退出验证 | 关联不唯一时拒绝融合；良好三视角不劣于最佳双视角；退化几何增大 covariance 或拒绝；3 -> 2 -> 1 节点退出时航迹连续且质量显式下降；relay 重发不改变 posterior |
| 真实 AirSim/ComputerVision 长 replay 与统计一致性 | 未闭合 | 缺 crossing、机动、遮挡、漏检、camera/bbox、节点退出、sensor delay/fault 的长期多 seed fixture | 用版本化 governed replay 输出并审计 RMSE/NIS/NEES、continuity、expected latency/OOSM 和 handover/region window；不得用短时 SimpleFlight 命中率替代 D1 精度验收 |
| CV/CA/CT 模型集与场景自适应 covariance | 未实现/待标定 | 当前仍为 NumPy CV/EKF 主线；缺机动模型对照及杂波、SNR、来源差异、遮挡和延迟 scale rule | 同一真实/冻结 replay 下给出 CV-only 对照、RMSE/NIS/连续性和运行成本，并稳定输出可解释 `covariance_scale_reason`；未达到收益门槛时不替换默认路径 |
| D6 长期批量 schema 与趋势 | 部分实现 | 当前字段可被消费，但缺长时跨 seed 统计一致性和冻结阈值 | D6 对同一 governed replay 可稳定聚合 latency、health、region/window、RMSE/NIS/NEES 与 evidence path，字段缺失必须显式 unavailable |

P2/P3 内容保持原有规划；本轮不删除、不移动，也不新增完成声明。

## 19. 2026-07-12 P1 长 Replay 构造与汇总实施结果

本轮由 D1 owner 在既有 governed replay、Blocks/CV reader、`FusionAdapter`、latency/OOSM、
sensor health 和 region window 接口上增量实现，没有引入 Stone Soup/FilterPy，也没有修改
main/runtime 或其他模块：

- 新增 `LongReplayConfig`、`LongReplayScenario`、`LongReplaySummary`、
  `build_long_replay_scenario()` 和 `summarize_long_replay()` 公共入口。默认场景为 60 s、3
  目标 crossing，输入目标数来自配置，不写死 2v2/5v5。
- 场景同时覆盖距离相关雷达 covariance、crossing clutter、声学粗方位、EO 像素投影、完全/
  部分遮挡、传感器延迟、显式 OOSM 和 relay 重发；所有观测保留 measurement/arrival 双时间
  戳、covariance、NED 工作空间、coverage cell 和 source lineage。
- 冻结 `d1.long_replay_scenario.v1`、`d1.long_replay_config.v1`、
  `d1.long_replay_summary.v1`、`d1.long_replay_thresholds.v1` 和既有
  `d1.sensor_observation.v1`。provenance 继续携带 scenario/config digest、seed 和 run ID。
- online observation ID 与 lineage 只使用传感器本地不透明 payload 序号，不携带持久目标
  slot；六状态真值和 observation-to-truth 标签只进入独立
  `d1.long_replay_offline_truth.v1` sidecar，不能进入在线 `GlobalTrack`。
- 汇总复用 raw/fusion latency audit、sensor health 和固定区域窗口，导出 modality/event、track
  level、source support、truth leak 和 metric availability。没有 D2 canonical-ID 离线映射时，
  RMSE/NEES 明确输出 unavailable reason，不填 0、不使用 truth 辅助在线关联。
- 新增官方 `scripts/run_long_replay.py` 薄 CLI，支持 `--seed`、`--duration`、
  `--target-count` 和 `--output`；输出严格为 `LongReplaySummary.to_dict()` JSON，CLI 不复制
  场景、融合或汇总算法。

默认 smoke 为 843 条观测、21 次显式雷达 OOSM、6 次 relay 重复、29 个区域窗口、0 个在线
truth leak，验证主机耗时约 8.8 s。CLI 子进程测试覆盖参数透传、输出目录创建、JSON schema
和 truth 隔离；本轮 D1 全量为 `66 passed`。

因此本轮关闭 D1-owned 的“可由 main 调用的合成长 crossing/遮挡/延迟/OOSM replay 与汇总”
缺口。仍开放的 P1 是：main 采集真实 Blocks/CV 多 seed 长 replay；D2-confirmed canonical-ID
映射后计算 RMSE/NEES；真实 sensor-specific latency/health/window、camera/bbox、节点退出和
covariance 阈值标定；CV/CA/CT/IMM 及场景自适应 covariance 对照。P2 外部库安排不变。

## 20. P1 真实 AirSim dense/crossing 输入冻结落实（2026-07-12）

本轮在既有 governed replay 上增加不连接 AirSim SDK 的真实持久化输入边界：

1. loader 接受 JSON/JSONL 直接观测和 frame 内嵌观测，按输入长度处理。
2. freezer 只转换实际存在且满足 covariance、coverage 和 canonical frame 合同的观测；缺
   measurement 的遮挡、漏检或节点退出 frame 只记事件，不伪造量测。
3. online observation ID 改为不透明序号，递归剥离 actor/object/truth identity；truth ID 和
   NED position 只进入 evaluator-only sidecar。
4. measurement/arrival 严格必填；processing/publish、sensor health、scene/profile/source
   schema 缺失时显式 `unavailable`。事件覆盖 crossing、遮挡、漏检、虚警、OOSM 和节点退出。
5. writer 输出 governed manifest、records、offline truth 和 summary；CLI 只负责参数、digest
   和文件写出，不复制转换逻辑。

本阶段验收为 online truth leak 0、缺失量测伪造 0、5-target fixture 和任意长度输入可运行、
四类文件可被现有 reader 消费。后续仍需 main 提供真实 multi-seed payload，D2 提供离线
canonical mapping，D6 汇总 RMSE/NIS/NEES、latency、health 和区域窗口统计。本轮 D1 全量
回归在 sidecar follow-up 后为 `74 passed`。

### 20.1 Truth sidecar 唯一键修复

main + D2 端到端验证发现同一 `(truth_id, timestamp)` 可能同时来自 frame truth 和 observation
metadata。D1 在 sidecar 构造阶段按该二元组确定性归并：available position 覆盖 unavailable；
两个 available 在 `1e-6 m` 内视为同一值，超过容差直接拒绝冻结；不同 timestamp 独立保留。
仅有 identity 的样本继续保留为 unavailable，summary 显式输出 unavailable 数量，不插值、不
外推、不借用相邻帧位置。该规则保证 D2 strict adapter 不再因同键 available/unavailable 重复
拒绝整个 sidecar，同时不会掩盖真实 truth 冲突。

### 20.2 捕获 Provenance 强校验（2026-07-13）

D1 AirSim freeze 现在要求捕获文件显式携带 scenario/config version、seed、
`target_spacing_m` 和 `evidence_path`。目标间距只以捕获 provenance 为权威来源，不从 truth
几何反推；API/CLI 声明、跨 payload 声明与捕获值不一致时 fail closed。manifest/summary
输出字段 availability，在线 records 与 evaluator-only truth sidecar 通过 provenance digest
绑定。专项测试覆盖 4 m/2 m 各 20 seeds，D1 全量回归为 `79 passed`。截至 2026-07-13，main
已经完成对应的 40 个真实 AirSim episode，D2/D6 已分别消费冻结产物做离线关联标定和统一
汇总；该结果关闭的是输入冻结与证据可消费性，不代表真实传感器误差和长期融合精度已标定。

## 21. 2026-07-13 真实 Dense Crossing 证据与后续计划

### 21.1 已完成并作为当前基线

- main 在 ComputerVision 模式完成 nominal 4 m 与 tight 2 m 两组严格几何，各 20 seeds，共
  40 个真实 AirSim episode；每个 episode 51 帧，目标数为 5，默认不保存截图。
- D1 governed replay 在全部 episode 保留 `measurement_timestamp`、`arrival_timestamp`、
  covariance、NED 工作空间、source lineage、scenario/config version、seed、
  `target_spacing_m` 和 `evidence_path`。捕获声明与 API/CLI 或跨 payload 不一致时继续
  fail closed。
- evaluator-only truth sidecar 共 10,200 个样本，`online_truth_leak_count=0`。truth 只用于
  D2/D6 离线评分，不进入在线 D1 观测、`GlobalTrack` 或下游控制链。
- D6 统一报告把 `d1_dense_crossing` 标记为 `available`，并携带 schema、digest 与 evidence
  path；缺失指标仍保持 `unavailable`，不由 D1 或 D6 补零。
- D1 全量回归为 `79 passed`。双时间戳、协方差、NED、source lineage、governed replay、
  capture provenance 和 truth 隔离均属于已闭合且必须保持的回归合同。

### 21.2 仍开放的 P1

1. **真实传感器 challenge fixture**：现有 4 m/2 m 数据主要验证几何、冻结合同和离线身份
   评估输入，尚未覆盖可代表工程传感器的雷达/声学/EO 漏检率、虚警率、遮挡过程、异步采样
   率、sensor-specific latency 和故障注入分布。后续由 main 采集版本化长 replay，D1 只冻结
   实际观测，不为缺失帧伪造量测。
2. **长期质量与协方差治理**：需要在正常/故障多 seed 长 replay 上标定区域时间窗口、
   covariance growth、expected-latency/OOSM、sensor health、NIS/NEES 和
   `covariance_scale_reason` 的持续阈值；raw OOSM 或短窗口高协方差不得直接触发 D4 降级。
3. **协同融合运行时验证**：D1/D2-confirmed canonical-ID adapter、部分共享 lineage、节点
   退出和 3 -> 2 -> 1 质量退化仍需真实 replay。D2 未确认同一 `global_track_id` 时，D1
   继续拒绝跨平台 Track-to-Track 融合。
4. **D6 长期统计一致性**：当前 D1 summary 已可用，但仍需验证跨场景、跨 seed、长时运行
   时 schema、availability、evidence path、区域窗口和 RMSE/NIS/NEES 汇总的一致性。

### 21.3 P2 可选项

FilterPy、Stone Soup、UKF/IMM、OpenCV/GTSAM 协同几何后端和 ROS 2 `tf2`/
`message_filters` 继续作为隔离 benchmark 或后续工程适配项。当前未安装或未接入的后端必须
显式报告 `unavailable`，不得写成已实现，也不得替换 NumPy EKF/fixed-lag 默认路径。

## 22. 2026-07-14 P0 在线 Scene Truth 身份边界

### 22.1 D1-owned 实施结果

- 包顶层新增稳定 API：`anonymize_online_observations(observations, *, identity_tokens=(),
  stream_id="online")` 和 `assert_online_observations_identity_free(observations, *,
  identity_tokens=())`。
- 仿真器允许用 scene truth 生成噪声量测；生成完成后，main/runtime 必须先调用匿名化 API，
  才能把 `SensorObservation[]` 交给在线融合/关联。scene actor/object/truth/segmentation 身份不
  是在线算法输入。
- 匿名化递归删除身份键，清理嵌套身份值和 `classification_hint` 中的目标 token，并按 frame
  及帧内顺序重写 `observation_id`。source lineage 同样映射为不含目标名字的不透明 ID；原始
  lineage 相同的 relay 重复仍映射到同一匿名 lineage。
- 返回新对象并保持 measurement、covariance、`measurement_timestamp`、
  `arrival_timestamp`、sensor/camera geometry 及通信时间字段。返回前强制执行 fail-closed
  validator，任何残留身份键或已知 token 都会抛出 `ValueError`。
- dry-run、governed/offline evaluator 和 truth sidecar 原路径不改；offline evaluator 必须继续
  消费原 scene observation 对应的独立 sidecar，不得从匿名在线副本反推身份。

### 22.2 验收证据与边界

2026-07-14 专项场景包含两组各 2 条 EO 观测，仅替换 target/actor/truth 名字，measurement、
covariance、双时间戳、bbox、相机内外参和其余字段完全相同。验收阈值为匿名结果逐字段严格
相等、数值/相机几何逐元素不变、身份泄漏数为 0、人工注入泄漏必须拒绝、原离线 sidecar 标签
保持。专项 `4 passed`，D1 全量 `83 passed`，全部满足。

D1-owned P0 API 缺口关闭；main-owned 系统接线仍必须把该 API 和 validator 放在每个 scene
state 在线入口。若身份值没有出现在可识别身份键下，main 必须通过 `identity_tokens` 提供完整
token 集。该集成条件不改变以下开放 P1：真实 radar/acoustic/EO challenge 长 replay、区域/
协方差/健康持续阈值、D1/D2-confirmed 协同融合、D6 长期一致性，以及 CV/CA/CT/IMM 和场景
自适应 covariance 对照。

## 23. 2026-07-14 关联治理与固定滞后回放修复

### 23.1 已完成

- 同一物理观测者的一次扫描对同一航迹最多更新一次；扫描键包含 modality，合法雷达/声学/
  光电跨模态融合不互相阻断。
- 近期成熟航迹可在唯一候选条件下使用独立雷达重捕门限；多候选时抑制新 birth 并保留审计，
  不使用 truth/actor ID。
- 非测距观测增加笛卡尔状态修正审计；超门限观测拒绝更新，不通过伪造协方差提高确定性。
- fixed-lag 检查点改为滞后边界之前最近的已接受量测后验，保持原预测区间的过程噪声语义；
  更早到达的合法 OOSM 通过 origin/archive 重建检查点后继续传播。
- 新增 `d1.association_audit.v1` 计数和回归测试。2026-07-14 D1 全量 `87 passed`；main
  报告 AirSim runtime 全量 `134 passed`。

### 23.2 剩余 P1 与验收

1. 由 main 对同一 M5N2 seed-001 真实 episode 复跑或冻结输入重放，验证 D1 航迹数保持 2、
   不再生成历史 `global_track_003`，且 31.8 s 不再出现状态 teleport。
2. 在多 seed、交叉、遮挡、虚警和漏检场景标定雷达重捕门限、非测距修正门限及模糊 birth
   拒绝率；不得用离线 truth 参与在线关联。
3. 记录 fixed-lag 检查点边界滞后、回放长度和循环耗时，确认历史 archive 只服务迟到量测，
   不造成在线时间或内存无界增长。

## 24. 2026-07-14 Covariance 合同硬化批次计划

本批先收紧观测入口合同，不改变 NED 状态、双时间戳或 fixed-lag/OOSM 数值流程：

1. 为 `SensorObservation` 定义按 modality/measurement 的 covariance 维度，并统一校验有限、
   对称、半正定和维度正确；正式 online、versioned governed replay 与 AirSim freeze 路径对
   缺失或非法 covariance 一律 fail-closed。
2. 删除正式融合入口对缺失/非法 observation covariance 的静默 default/reset；保留合法
   covariance 的既有质量缩放和上下界治理行为。
3. 历史缺失 covariance 仅通过显式 offline legacy migration API 补齐，并在 observation
   metadata 中记录 migration mode、原始缺失原因、sensor model/default 标识及其参数来源；
   普通 legacy reader 不得无标记放行缺失 covariance。
4. 补充回归，覆盖 governed/online 缺失拒绝、非有限/非对称/非半正定/维度错误拒绝、显式
   offline migration provenance，以及当前合法正式 observation、NED、双时间戳和 OOSM 行为
   不变。

验收口径：D1 全量测试通过；非法 covariance 在进入滤波更新或 governed bus 前抛出明确
`ValueError`；迁移观测携带完整且可序列化的 imputation provenance；`git diff --check` 无
格式问题。完成后同步 README、PLAN、D1 GAP audit 和受影响 review，并把真实传感器 covariance
标定继续保留为开放项。

### 24.1 执行结果

2026-07-14 已完成统一 covariance validator、在线/序列化/AirSim freeze fail-closed 接线和
`migrate_offline_legacy_sensor_observation()`。正式入口拒绝缺失、非有限、非对称、非半正定及
modality 维度错误 covariance；显式迁移记录 mode、原始缺失原因、sensor model/default、参数
来源和生成输入，并被所有在线入口拒绝。合法 covariance 后续质量缩放、上下界、双时间戳、
NED 和 OOSM/fixed-lag 流程保持原行为。

验收日期为 2026-07-14；构造性合同测试无随机 seed，覆盖 radar 五类非法/缺失拒绝与一条
legacy migration，并保持 governed replay、现有合法 OOSM 和七条 AirSim freeze observation
回归。D1 全量结果 `92 passed`。本批关闭 covariance 合同硬化实现缺口；真实 radar/acoustic/
EO/lidar sensor-specific covariance 标定与长期 NIS/NEES consistency 仍为开放 P1。

## 25. P1 同帧批处理与 fixed-lag 重放预算（2026-07-14）

### 25.1 问题与约束

main 对最新 M5N2 seed-001 前 40 帧剖析显示 D1 占 episode bus 绝大部分时间。根因是同一
main tick 内 radar、EO、acoustic/lidar 等观测逐条调用 `process()`：每次关联都从活动历史
重建 measurement-time 状态，每次接受后又重放到发布时刻。同一/近同测量时刻因此重复遍历
同一 fixed-lag 历史。

本批必须保持：

1. 每条观测原始 `measurement_timestamp`、`arrival_timestamp`、covariance、frame、modality
   和 source lineage 不变；
2. 关联与 observer scan/source duplicate 门控逐条执行，不能用聚合均值替换量测；
3. 乱序和检查点前 OOSM 仍从合法 origin/archive 重建；
4. 输出在相同输入顺序下与逐条处理数值等价且确定；
5. 性能收益来自消除重复 replay，而非丢观测、改时间或缩短证据。

### 25.2 接口与实现

已实现 `FusionAdapter.process_batch(observations) -> FusionBatchResult`。处理顺序是调用方输入
顺序；每条观测仍做正式校验、延迟/健康审计和关联。批内状态缓存键为
`(global_track_id, history_revision, measurement_timestamp)`：未改变的航迹可复用同测量时刻
状态；某航迹接受新观测后仅该航迹 revision 失效。接受更新先写入权威 observation history，
批次末按 track ID 确定性排序，每个 dirty track 只做一次发布时刻重放。

检查点之前的新 OOSM 会标记 checkpoint dirty。若后续关联只查询检查点之前的时刻，直接从
origin/archive 计算；首次查询检查点之后状态或批次终结时才重建检查点，因此同批旧 OOSM 不会
无条件重复重建。`FusionBatchSummary` 记录实际 history/origin replay、cache hit/miss、每航迹
终结重放和 deferred update replay avoidance，供 main/D6 做性能审计。

main 接线方式：

```python
result = fusion_adapter.process_batch(observations_received_this_tick)
tracks = list(result.tracks)
batch_summary = result.summary.to_dict()
```

一个 batch 应对应 main 已收齐的同一 episode tick 输入，不应跨未来 tick 等待水位线，也不应
改写观测时间。`tracks` 只表示批末快照；若调用方需要每条观测中间状态，继续使用 `process()`。

### 25.3 验收结果与后续

- 构造验收：5 航迹、15 条 radar/lidar/acoustic 同帧观测；逐条 95 次 history replay，batch
  24 次，减少 74.7%；最终 state/covariance 在 `1e-9` 绝对容差内等价。
- fixed-lag 验收：先接收窗口内观测、再接收 checkpoint 前 OOSM，逐条与 batch 的 checkpoint
  timestamp/count、pre-checkpoint replay count、state/covariance 一致。
- 真实持久化输入：M5N2 seed-001 baseline 前 40 帧、786 条观测；逐条 18.05 s/1267 次，
  batch 5.70 s/351 次，3.17 倍加速，state/covariance 最大差为 0。
- 2026-07-14 D1 全量：`98 passed`；`git diff --check` 通过。

D1-owned P1 实现已完成。剩余系统 P1 由 main 把逐条调用替换为每 tick 一次 batch，复测完整
245/248 帧、记录 D1 与总 loop 分项耗时并做多 seed；在该证据完成前不能宣称 100 ms 实时预算
闭合。

## 26. 可扩展三维扫描级融合（2026-07-20）

### 26.1 已实现合同

1. `Scalable3DFusionAdapter.process_online_sensor_batch()` 以鸭子类型消费 main bus 的匿名
   `OnlineSensorBatch`，`process_measurement_scan()` 接受等价量测序列；D1 不导入或修改
   `scalable_3d_simulation`。
2. 输入在字段解引用前递归审计，truth/actor/object/entity/target ID、world snapshot 和
   offline truth label fail closed；`use_truth_hints_for_association=True` 被显式拒绝。
3. `radar_spherical` 的三维球坐标及原始 covariance 转为 D1 radar 规范量测；缺少径向速度时
   仅在 canonical `4x4` 合同中补零并标为未观测，滤波只消费 range/azimuth/elevation 三维；
   位置解析 Jacobian 与零均值、各轴 `25 m2/s2` 的独立速度先验共同形成
   `[pN,pE,pD,vN,vE,vD]` 和 `6x6` covariance。
4. `process_scan_batch()` 对扫描前航迹和整扫描点迹一次性构造三维马氏代价矩阵，执行一对一
   匈牙利匹配；未匹配 radar 点迹批量起始，非测距点迹不单独起始。旧 `process_batch()` 的
   逐条等价语义保持不变。
5. 二维 `acoustic_bearing=[azimuth,elevation]` 转为 `acoustic_3d` 弱约束。声纹向量必须带
   `soundprint_is_identity=False`，转换后仅以 `soundprint_category_only` 类别证据保留，不参与
   关联、birth、`global_track_id` 或 truth hint。
6. `GlobalTrack.metadata` 同时发布 `measurement_timestamp`/`arrival_timestamp` 及既有
   `latest_*` 别名，状态固定六维、covariance 固定 `6x6`，可供 D2 adapter 消费。

### 26.2 2026-07-20 验收

测试使用新主环境默认 seed 7，并把雷达探测率设为 1.0。五档规模各运行首扫和 0.2 s 后次扫：

| 目标数 | 首扫量测/birth/航迹 | 次扫量测/update/航迹 | ID 集 |
| ---: | ---: | ---: | --- |
| 5 | 5/5/5 | 5/5/5 | 保持 |
| 20 | 20/20/20 | 20/20/20 | 保持 |
| 50 | 50/50/50 | 50/50/50 | 保持 |
| 100 | 100/100/100 | 100/100/100 | 保持 |
| 200 | 200/200/200 | 200/200/200 | 保持 |

合计 10 个 scan batch、750 条匿名雷达量测，接受阈值为每档首扫 100% birth、次扫 100%
一对一 update、0 个未接受量测、有限状态和半正定 `6x6` covariance，全部满足。另以 2 目标
3 个 scan/6 条量测验证延迟到达：2 条历史量测均计为 OOSM 并按 measurement time 重放，
航迹数和 ID 集不变。声学测试验证无雷达先验时 5 条二维 bearing 产生 0 birth，有雷达先验时
5/5 只更新既有航迹。专项 `9 passed`、D1 全量 `120 passed`。

### 26.3 开放项

1. main 将真实 episode bus topic 接入 adapter，并冻结 bus/model/schema version 与 batch audit；
2. D2 完成原生六维稀疏关联后，联合验证 5/20/50/100/200 多 seed recall、ID switch 和连续性；
3. 在漏检、虚警、交叉、分裂和长时 OOSM 下增加 tentative/confirmed/deletion 生命周期证据，
   避免把“首扫 200/200 birth”误写成复杂场景长期 95% recall 已关闭；
4. 由 D6 至少汇总 20 个未见 seed 的 RMSE/NIS/NEES、recall、耗时和置信区间；单次本机
   0.108 s 首扫/0.392 s 次扫仅是开发探针，不是实时验收；
5. main-owned 系统文档和跨模块状态由 main 在接线后同步。本批不修改 AirSim 计划，因为新
   能力只面向三维质点总线，未改变 AirSim producer/runtime。

## 27. 无多普勒六维速度稳定性（2026-07-20）

### 27.1 已完成

1. 无多普勒 radar observation 保持 canonical `4` 维与 `4x4` covariance，兼容现有在线合同；
   `radial_velocity_observed=False` 时 `measurement_model_for()` 只构造三维 `z/R/h/H`，补零
   径向速度不参与滤波。
2. 起始状态使用 `v0=0`、`Pvv=25I m2/s2`、`Ppv=0` 的显式高斯先验。该参数不来自场景
   `target_speed_max_mps`，不是 4.7 m/s 或任何其他速度上界。
3. 位置-only radar 默认使用 `chi2_3(0.999)=16.26623619623813` 创新门控。门控拒绝不会更新
   后验，但 observation history、measurement/arrival timestamp 和 OOSM replay 顺序继续保留；
   metadata 输出 replay innovation/update/rejection 审计。
4. 新增四个自动化回归：量测维数和先验块、门内关联但超 NIS 阈值的离群点、顺序/乱序 OOSM
   数值等价，以及 seed 17 的 200 航迹/10 scan/2,000 条匿名雷达量测。

### 27.2 验收结果

- 专项 `test_scalable_3d_fusion.py`：`13 passed in 7.82s`；D1 全量：
  `124 passed in 29.88s`。
- 200 条多帧回归在 10 scan 内始终保持 200 个 ID，状态和 `6x6` covariance 全部有限；末帧
  速度 median/P90/max=`3.87/6.43/8.54 m/s`，速度 covariance trace=
  `57.97/60.69/61.19`。
- 50 条、seed 17 开发探针的速度由修复前 `6.28/12.16/21.03` 降为
  `3.99/6.12/9.69 m/s`；修复后 covariance trace 仍为 `58.22/60.43/60.90`，不把短基线
  估计写成高精度速度。
- 2 航迹 OOSM 回归中，2 条迟到量测被合法重放；与顺序输入在共同发布时刻的 state/covariance
  绝对差不超过 `1e-9`，输出仍为双时间戳和 `6x6` covariance。

### 27.3 仍开放

1. 至少 20 个未见 seed 的速度误差、NIS/NEES、门控误拒/漏拒和 covariance coverage 标定；
2. 漏检、虚警、交叉、机动和更长 OOSM 下的生命周期与速度稳定性；
3. main 用当前实现正式复测 D1 -> D2 -> D3，确认 D2 二次滤波不会重新放大速度均值，并记录
   第二轮分配数量；开发原型结果不得替代该验收；
4. CV 过程噪声和速度先验仍是固定研究参数，尚未实现 IMM/自适应噪声或真实传感器标定。

已检查 `docs/AIRSIM_INTEGRATION_PLAN.md`：本轮仅修改 scalable 3D 质点总线内的 D1 量测模型，
未改变 AirSim producer、Blocks 启停、reset、episode 顺序或持久化 schema，因此无需修改。

## 28. Scalable 3D consistency evidence 与离线评估合同（2026-07-20）

### 28.1 D1-owned 已完成项

1. `FusionAdapter` 对每条已见观测保留 versioned、truth-free DTO；track initialization、正式
   replay update、innovation gate rejection、OOSM、duplicate、association/initializer rejection
   均有明确 disposition 和 metric availability。
2. `OnlineConsistencyEvidenceBundle` 冻结 scenario/run/seed、producer/source/config provenance、
   records hash 与 content hash；online aggregation rows 可按 scenario/sensor/range 聚合。
3. `OfflineTruthStateSidecar` 与 `D2LineageMappingSidecar` 是独立 artifact。D2 必须先用
   observation lineage 形成 evaluator-only canonical 决策；adapter 绑定在线 evidence digest
   和 truth digest，并严格区分 D1 `source_global_track_id` 与 D2 `global_track_id`。
4. `evaluate_offline_consistency()` 只做离线精确对齐；不使用 proximity、名称、数组索引或
   observation ID 猜 truth identity。输出 position/velocity RMSE、NEES、NIS gate coverage 和
   每更新 aggregation rows。
5. 时间、维数、hash、provenance、mapping coverage 或 finite 检查失败时 fail closed；奇异
   covariance 不使用 pseudo-inverse 伪造 NEES。

### 28.2 验收状态

2026-07-20 的构造合同测试使用 provenance seed 19，但不是随机多 seed 精度实验。专项新增
`12 passed`，覆盖 3 条 radar 接受/拒绝序列、顺序与一条迟到 OOSM、四个 range bin、acoustic/
EO available/unavailable、1/4/7 输入规模、缺失和错误 D2 lineage mapping、在线额外 truth 字段
拒绝、truth/hash 篡改、六维和时间错位、奇异 covariance 与 NaN。OOSM 最终
state/covariance 与顺序路径容差 `1e-9`；已知误差
夹具的 RMSE 为 `5 m` 和 `12 m/s`，两条 gated innovation 中一条通过，coverage 为 `0.5`。
main 复跑 D1 全量 `136 passed`。接受阈值是合同、hash、availability 和 fail-closed 行为全部
满足，不以这些构造数值判定算法精度达标。

### 28.3 Main/D2/D6 接线与仍开放项

1. main 在每个 episode 结束后用真实 source/config digest 调用
   `adapter.export_consistency_evidence(provenance)`，分别持久化 bundle 与
   `aggregation_records()`；在线控制循环不得读取 truth sidecar。
2. D2 离线 evaluator 以 `source_observation_ids` 谱系生成 canonical identity；main/D2 再形成
   `d1.consistency.d2_lineage_mapping_sidecar.v1` adapter，覆盖所有带 estimate 的
   `observation_id + measurement_timestamp`。不得把 D1 source track ID 当作 D2 canonical ID，
   也不得从距离或名称补映射。
3. main 将独立 truth sidecar、D2 mapping 和 online bundle 交给
   `evaluate_offline_consistency()`；D6 仅消费 result/aggregation rows，并严格尊重 availability。
4. 正式多 seed sensor/range/scenario RMSE、NEES、NIS coverage、置信区间和验收阈值仍开放；
   至少 20 个未见 seed、复杂 crossing/漏检/虚警/机动及真实 covariance 标定尚未执行。
5. AirSim producer/runtime 未接线该 artifact，本轮未运行 AirSim；现有 AirSim episode 不能因
   API 存在而改写为 consistency metrics available。

## 29. P1 整帧 OOSM/迟到扫描输入合同（2026-07-22）

### 29.1 工程边界

现有 `process_scan_batch()` 负责一个已确定扫描内的点迹关联和 fixed-lag 数值更新，不负责等待
未来扫描或关闭 event-time 水位线。新增 `ScanInputOrganizer` 专门负责该上游边界：按 arrival
顺序接收完整扫描，在有限迟到窗口内按 measurement time 重排，只将完整
`SensorScanFrame` 放入 `released_scans`。D1 不在该层生成航迹、不调用 D2、不创建或改写
`global_track_id`。

设第 `k` 次成功接收后的最大量测时刻为 `M_k`，配置最大迟到量为 `L`：

```text
W_k = M_k - L
```

新扫描量测时刻严格小于接收前水位线 `W_(k-1)` 时整帧 too-late。缓冲中量测时刻严格小于
`W_k` 的扫描按 `(measurement_timestamp, received_sequence)` 释放；等于水位线的边界仍开放，
保证同一量测时刻的不同来源可在窗口内共同到达。episode 结束由 main 显式 `close()`，释放未
过期尾部。没有新扫描但 episode 时钟推进时调用 `advance_arrival_time()`，只执行驻留期限，不
伪造事件时间。

### 29.2 已实现合同

1. `SensorScanFrame` 保留每条观测的双时间戳、covariance、canonical/NED source frame、sensor
   namespace 和 immutable source lineage；字段级快照递归接受并冻结嵌套 `Mapping`/`mappingproxy`，
   数组使用独立只读副本，随后执行在线 covariance 与 truth 隔离。
2. config/frame/event/summary/result 五类 schema 均为 v1，`to_dict()` 可有限 JSON 序列化。
3. 同 scan 精确重发记 duplicate；相同 source payload 经不同 transport envelope 重发记 replay；
   scan ID、lineage、量测时间或 payload 内容不一致记 timestamp conflict。分类不使用仿真 truth。
4. 所有拒绝均以扫描为原子单位。too-late、buffer overflow、buffer residence expiry、claim
   capacity、结构非法均不会产生部分 `released_scans`。
5. 缓冲由时间、扫描数量和观测数量三项确定性上限约束；claim registry 另有扫描/lineage 数量
   上限，达到上限后 fail closed。
6. `ScanInputAuditEvent` 给出逐帧 lifecycle，`ScanInputAuditSummary` 给出累计 received/buffered/
   reordered/released/rejected 及各拒绝原因、当前/最大缓冲和水位线。

### 29.3 main 推荐接入

```python
observations = sensor_observations_from_online_batch(batch)
frame = SensorScanFrame.from_observations(observations, scan_id=batch.batch_id)
decision = organizer.ingest(frame)

for fusion_time, scans_at_time in group_by_fusion_timestamp(decision.released_scans):
    latest_state = None
    for scan_index, released in enumerate(scans_at_time):
        latest_state = fusion.process_scan_batch(
            released.observations,
            materialize_tracks=False,
        )
        if scan_index + 1 < len(scans_at_time):
            publish_state_update(latest_state)
    if latest_state is not None:
        snapshot = fusion.materialize_global_tracks()
        publish_full_snapshot(latest_state, snapshot)
        publish_to_d2(snapshot.tracks)

publish_scan_audit(decision.events, decision.audit)
```

- 一个到达的 `OnlineSensorBatch` 对应一次 `ingest()`，main 不拆帧，也不直接把 buffered/rejected
  帧交给 D1 fusion 或 D2；
- `group_by_fusion_timestamp()` 表示 main 调度侧按融合时刻分组的伪代码，不是新增 D1 API；
  组内每个扫描仍调用一次 `process_scan_batch(..., materialize_tracks=False)` 并各自产生发布记录，
  只有该 fusion timestamp 的末次后验物化完整快照；
- 所有输入必须先统一到 episode 时钟和 D1 canonical frame；organizer 不估计 clock offset，也不
  执行外部坐标变换；
- 没有扫描的调度 tick 调 `advance_arrival_time(now)`，episode 输入结束调一次 `close()`，并处理
  `close().released_scans`；
- manifest 记录 scan input schema、完整 config、episode 时钟来源和调用计数；
- audit 进入 main/D6 日志，不阻塞实时控制，不作为未经标定的 D4 降级命令。

### 29.4 验收与开放项

2026-07-22 采用确定性构造输入，无随机 seed、无 AirSim。新增 15 项测试，覆盖有序、窗口内
乱序、超窗整帧拒绝、同时间多源、duplicate/replay/timestamp conflict、arrival regression、
扫描/观测数量上限、驻留超时、动态 1/7/200 点、truth 注入拒绝、main 批次转换/融合组合及
嵌套只读视觉元数据快照；D1 全量 `151 passed`。

D1-owned 的可执行输入合同和 main scalable 三维质点 runtime 接线已经关闭。仍开放的系统 P1
是：按 20/50/100/200 规模和更长 episode 冻结 `max_lateness_s`、驻留/容量/claim 上限；统计
too-late 误拒、buffer 峰值、吞吐和 tail close；与 D2/D6 长期 schema 对齐。该 organizer 不替代
现有 fixed-lag Kalman OOSM replay，也没有关闭真实传感器长期延迟与一致性标定。

## 30. P1 逐扫描融合热点治理结果（2026-07-22）

### 30.1 实现

1. `TrackRecord.replay_checkpoints` 按观测排序保存滤波后验、NIS 和 gate 结果。正常顺序调用复用
   已有后验；OOSM 只删除插入排序键及之后的检查点。
2. 固定滞后重基、起始观测变化和检查点前合法 OOSM 会清空相关缓存并从正确锚点重建，不缩短
   `buffer_horizon`。命中检查点时仍调用 consistency evidence 捕获，保持 revision 与未缓存路径
   一致。
3. `global_tracks()` 每扫描生成一次 association/latency/sensor-health 审计快照。每条航迹仍
   物化并携带完整 metadata；发布 state/covariance 复制后交给调用方，不暴露内部缓存数组。
4. `FusionBatchSummary` 新增 replay filter update、checkpoint reuse、track materialization 和
   health snapshot build 四项操作计数。`incremental_replay_cache` 与
   `shared_publication_audit_snapshot` 开关只用于建立未缓存参考对照。

### 30.2 验收

冻结输入为 seed 42000 的 200v200 在线观测 JSONL，SHA-256 为
`38d24429711b67d612f2f398478386ebf0df690fae55cd9dcc36434aac4fb078`。输入含 86 个扫描、
2,051 条观测、10 次重排，峰值 33 扫描/623 观测。未缓存与优化路径的逐扫描语义摘要、最终
201 条航迹和 consistency evidence 哈希相同，在线 truth 使用为 0。

replay filter update 从 93,234 降至 1,797，下降 98.07%；checkpoint reuse 为 91,437；health
snapshot 从 16,653 降至 86。未缓存参考墙钟 34.701 s，优化路径 9.073 s，本机单次 3.82 倍。
墙钟不是单元测试阈值，正式验收依赖操作计数、语义哈希、1/7/200 动态规模、乱序后缀失效、
检查点前 OOSM 和发布数组隔离回归。性能专项 `6 passed`；main 复跑 D1 全量
`157 passed in 28.77s`。

### 30.3 开放项

1. main 已在 clean `8f86192` 完成 200v200 三 seed 全栈复跑；下一步扩展更多 seed 和更长历史，
   冻结周期与峰值内存预算。当前 D1 fusion 均值 92.991 s，不关闭系统实时预算。
2. 正式融合效果仍需独立 truth sidecar、D2 canonical mapping 和多 seed RMSE/NEES/NIS
   coverage。该性能优化不提供精度证据。
3. AirSim producer、Blocks/CV/SimpleFlight、episode 编排和持久化 schema 均未改变。本轮已检查
   `docs/AIRSIM_INTEGRATION_PLAN.md`，无需修改。

## 31. GlobalTrack 共享审计物化候选（2026-07-24）

### 31.1 目标与边界

冻结 profile 显示 570 扫描中 `global_tracks()` 调用 361 次、`_to_global_track()` 调用
71,515 次，累计分别为 `11.530/10.977 s`。本候选只压缩完整发布扫描内重复复制的 association、
latency 和 sensor-health 共享审计树。不修改雷达数学、fixed-lag/OOSM、扫描与发布频率、关联
门限、输入观测、航迹数量或 `GlobalTrack` 字段。

### 31.2 实施

1. `immutable_shared_publication_metadata=False` 保留 reference；`True` 启用候选，且强制要求
   `shared_publication_audit_snapshot=True`。
2. 候选在 `_track_publication_context()` 中递归复制并冻结三棵共享审计树。冻结容器保持
   映射/序列读取语义；当前 v2 使用 `frozenset` 键值对和 tuple 序列承载精确类型，不继承可
   由基类方法绕过的 `dict/list`。所有常规写入、删除、排序和扩展操作均 fail closed，
   `GlobalTrack.to_dict()` 在持久化边界转回内建 JSON 容器。
3. `_to_global_track()` 仍为每条航迹建立独立顶层 metadata 和状态/协方差副本，只复用三个
   不可变审计值。`publication_materialization_diagnostics()` 输出实际实现标识、逐航迹复制、
   合同版本、不可变容器构造、合同验证节点、共享值复用和完整物化计数。
4. 专用冻结回放 A/B 逐发布计算完整 `GlobalTrack.to_dict()` SHA-256，并比较逐扫描融合语义、
   业务操作数、累计诊断、终态和 consistency evidence。墙钟和 profile 不参与通过判定。
5. 下游只可对精确 `d1.publication_audit_tree.v2` 调用
   `validate_immutable_publication_audit_tree()`。认证后仍需执行一次内容级 truth-free 审计，
   只对同一强引用对象身份复用结果；任意 marker、`Mapping` 或可变代理不得进入快路。

### 31.3 当前证据与正式验收

2026-07-24 单 seed 1101、570 扫描、10,810 观测的 v1 reference/candidate 全部门控通过。完整物化
均为 71,515；reference 复制共享审计映射 8,832,271 次，candidate 为 0。profile 中
`_to_global_track` 为 `10.700 -> 2.198 s`，fusion 总墙钟为 `42.282 -> 34.792 s`。专项
4 项和当时 D1 全量 `365 passed in 20.91s`。

同提交 v1 正式矩阵随后完成 short 10 seed 和 long 3 seed。D1 fusion wall 改善
16.29%/31.05%，但 D2 association 增加 53.44%/169.89%；核心墙钟只改善 1.65%/1.21%，未
达到 5% 门，因此 v1 未准入。根因是 D2 只复用精确内建容器审计，无法验证 v1 自定义
`dict/list` 子类。

当前代码候选已升级为 `d1.publication_metadata.immutable_shared_audit.v2`，合同为
`d1.publication_audit_tree.v2`。D1 已完成 389 项全量单元回归，包括 base-class 绕过、可变
backing store、循环树、不支持叶值、序列化和共享身份。

正式 v2 矩阵已于 2026-07-24 从 clean source commit
`be399e138762f5e660f553c8caa812d52ab38c61` 完成。场景包含 200 目标、200 资源和 2 个侦察
节点；short 为 seeds 1101-1110、2.2 s，long 为 seeds 1101-1103、10 s。13 对、26 个 arm
全部重新执行，`0 reused/0 failed`。13/13 业务语义、有限状态、在线真值隔离、实现身份、
D2 审计和 RSS 门通过。

| 指标 | Short | Long | 门限 |
| --- | ---: | ---: | ---: |
| D1 fusion 改善 | 13.5447% | 26.8298% | >=10% |
| 核心墙钟改善 | 6.5677% | 18.2438% | >=5% |
| D2 association 耗时变化 | -16.1939% | -35.6213% | 回归 <=5% |

候选累计 702 次 v2 合同验证、702 次内容审计、139,920 次身份复用和 0 次合同拒绝。D6 判定
`d1_optimization_admitted=true`。main promotion commit `f5b350b` 已将可扩展三维仿真的默认
selector 晋级为 `immutable_shared_v2`，同时保留 `per_track_copy_v1` 显式对照。D1 模块自身
`immutable_shared_publication_metadata=False` 的构造默认保持不变，这是独立调用兼容策略，
不表示 main 仍使用 reference。

### 31.4 剩余计划

1. 保持 v2 精确类型、truth-free 内容审计、强引用身份复用和 v1 fail-closed 的合同回归。
2. 补充逐批 D2 审计明细，使每个发布批次的合同验证、内容审计、身份复用和拒绝原因可独立追溯。
3. 在固定目标运行环境继续关闭系统实时容量。当前最低实时因子为 `0.1730801`，
   `system_realtime_gap_closed=false`。
4. AirSim、目标硬件、正式 RMSE/NEES/NIS 和物理拦截继续按独立证据验收，不能由本次质点性能
   矩阵外推。

## 32. P1 真值隔离质量基准

### 32.1 已完成

1. 建立 `D1AnonymousQualityScenario`，按输入数量生成 5/20/50/100/200 及任意正整数规模的
   匀速三维密集交叉扫描；场景包含漏检、虚警、遮挡协方差放大、固定延迟和强制乱序扫描。
2. 建立 `D1QualityEvaluatorSidecar`。在线侧只持有匿名源谱系；离线 sidecar 单独保存轨迹
   真值和谱系映射，并以内容摘要约束。sidecar 不传给 `FusionAdapter`。
3. 建立带 `available/value/sample_count/reason/unit` 的指标合同。不可用指标必须返回
   `value=None` 和原因，不能用 0 代替缺失数据。
4. 实现 20-seed 批量入口、逐 seed JSON、中文 Markdown 报告和分规模聚合。基准不修改
   D2 规范身份，不改变 D1 默认算法和生命周期。

### 32.2 开发验收

- 2026-07-25，5 目标、0.61 s、seeds 2000-2019：20/20 运行完成，共评分 248 条唯一接受
  观测，谱系映射覆盖率 1.0；
- 2026-07-25，200 目标、0.61 s、seed 1000：3 个发布帧，终态 201 条航迹，164 条 OOSM
  观测，共评分 532 条唯一接受观测，暖机召回率 0.8183，谱系覆盖率 1.0；同日重复开发运行
  的处理 P95 为 166.41--310.96 ms，不作为门限；
- 专项 `8 passed`，D1 全量 `496 passed in 33.19s`；
- 通过门限：在线真值暴露为 0、D2 规范身份写入为 0、快速 20-seed 完成率 20/20、谱系
  覆盖率 100%、不可用指标均带原因。

### 32.3 下一步

1. 在 clean 工作树运行 200 目标、seeds 1000-1019 的正式长时质量矩阵，固定持续时间、漏检、
   虚警、遮挡和延迟参数；
2. 先确认 20/20 seeds 的 RMSE、NEES、NIS、召回、重复航迹和虚假航迹寿命均可用，再冻结
   验收门限；
3. 依据测量结果单独设计 tentative/confirmed/expiry 候选，不在基准代码内修改生命周期；
4. main/D6 后续可读取结果 JSON，但 D1 sidecar 不进入在线 episode bus。

`docs/AIRSIM_INTEGRATION_PLAN.md` 已检查。本项是 D1-owned 质点离线基准，不改变 AirSim
topic、相机/雷达 adapter、settings、reset 顺序或日志接口，因此该文档无需修改。

## 33. EO 关联风险 Shadow Evidence（2026-07-31）

### 33.1 已实现

1. 新增严格、exact-key、truth-free 的 `d1.association-risk-evidence.v1` 与有界候选边 DTO；
   含双时间戳、发布时刻、publisher node/epoch、扫描/观测键、selected edge、top-K 和候选代价
   margin。DTO/字段独立，但复用已冻结 opaque source identity contract 的 member token/source key。
2. 对 EO 关联在 one-to-one 矩阵完成后、更新前检测图像外投影、近投影奇异、病态创新协方差、
   弱 margin 和多个门内候选。sidecar 保留 NIS、像素残差、预测像素、深度、图像尺寸、创新协方差
   谱、bbox 面积和置信度。
3. `association_risk_evidence_shadow=False` 保持默认；开启只通过
   `FusionBatchResult`/`FusionStateUpdateResult` 侧车发布，且 top-K 默认 3、每扫描默认最多 32
   条（硬上限 16/256）。

### 33.2 版本化影子分类

1. 新增独立 `AssociationRiskClassificationEvidence`，schema 固定为
   `d1.association-risk-shadow-classification.v1`，profile 固定为
   `d1-eo-pathological-projection-composite-development-v2`；不修改
   `d1.association-risk-evidence.v1` 的字段和 exact-key 合同。
2. profile 同时要求 `valid_candidate_count>=2`、已选投影在图像外、至少一个保留替代投影在
   图像内、`bbox_area_px2<=4.0` 和 `confidence<=0.10`。分类输出保存每项命中/未命中状态，
   `positive/negative` 均发布，数量一一对应已发布 raw evidence，因此复用每扫描 32 条默认上界。
3. `association_risk_evidence_shadow=False` 仍是唯一开关。开启时分类固定
   `mode=shadow`、`decision=evidence_only`、`online_truth_used=false`、
   `posterior_update_applied=false`。分类不读取 actor/target/truth 标识，不参与关联、滤波、
   `GlobalTrack` 或 D2 门控。
4. `FusionBatchResult`、`FusionStateUpdateResult` 和显式 `FusionTrackSnapshot` 通过
   `association_risk_classifications` 携带结果；
   `association_risk_classification_audit()` 单独报告已评估 raw evidence、正负分类和 profile。

### 33.3 开发证据

2026-07-31 同源开发校准使用 37 个 episode、1,536 条 raw evidence。纯影子配置与冻结 R0
严格身份结果 `37/37` 一致，在线真值使用为 0；复合条件覆盖 17 个已知相机致错事件中的
`17/17`，20 个严格身份可用对照中 `1/20` 触发。该 1 个对照也是潜在错绑，但没有进入最终
严格身份帧。数据没有独立留出，profile 名称保留 `development-v2`，不得据此实现 D2
enforcement。

定向测试 `18 passed`，D1 全量 `514 passed, 1 warning in 33.43s`。

### 33.4 留出执行与判定

1. main 使用 seeds 2000--2019 运行 nominal 100v100 与 200v200，共 40 个 2.0 s episode；正式
   shards 10--19 未使用。D2 只读因果重放完成 `40/40`。
2. 排除 4 个非相机阻断样本后，36 个分类评估 case 包含 11 个相机因果正例、13 个标注故障事件
   和 25 个严格身份可用对照。1,015 条在线分类与离线 v2 复算 `1015/1015` 一致，共 12 次正分类。
3. 故障事件命中 `11/13`，召回率 `0.8461538462`；通过对照告警 `0/25`。样本量门通过，性能门
   因召回低于冻结门限 `0.90` 而失败。seed 2003 漏检未满足已选投影在画面外，seed 2012 漏检
   未满足存在可信画面内替代候选。
4. 100v100 seed 2006 与 200v200 seed 2001 的业务等价复核在剔除四个风险旁路字段后，D1 总线、
   D2 总线、严格身份评估语义与 truth NPZ 的 SHA 均完全相同。

### 33.5 后续约束

1. v2 保持 default-off、shadow、`evidence_only`，不增加 D2 adapter 或任何 enforcement；
2. 本留出集只保留为冻结评估证据，不得用于修改 v2 判据或阈值；
3. 若提出下一候选，必须先用新的 development 数据形成新 profile，再使用新的独立留出集验收；
4. 正式 shards 10--19 未参与本轮，当前没有由该候选形成的正式准入证据；跨扫描稳定性、AirSim
   和目标平台性能仍需独立验证。

`docs/AIRSIM_INTEGRATION_PLAN.md` 已检查。本项不改变 AirSim 观测适配器、settings、相机外参、
episode/reset、topic 或运行时接口，因此无需修改该文档。

## 34. GlobalTrack 批量质量摘要候选（2026-08-01）

### 34.1 热点与单一身份

1. 使用 seed 42000、2.2 s 的非正式 200v200 冻结回放重新剖析当前不可变共享审计路径。
2. reference 的 `global_tracks/_to_global_track/covariance_a95` 累计为
   `0.443068/0.290990/0.137480 s`；同轮 scan-input 墙钟为 `0.138621 s`。
3. 只推进 `d1.publication.global_track_materialization.batched_a95_summary.v1`，不并行研究
   scan-input，也不复用三个明确排除的历史候选。

### 34.2 实现边界

1. `batched_global_track_a95_summary=False` 保持默认 reference；候选必须显式开启，且要求
   `reuse_track_classification_a95=True`。
2. 候选只把同一发布帧的二维位置协方差特征值计算批量化。协方差限制仍先执行，A95 公式、
   分级门限和输出浮点值不变。
3. 状态、协方差、source support、identity likelihood、轨迹 metadata 和完整
   `GlobalTrack` 仍逐条构造并与内部状态隔离。
4. 诊断分别记录标量摘要次数、批量构建次数、矩阵数、特征值调用数和逐航迹复用数。

### 34.3 模块门结果

冻结输入 SHA-256 为
`c6dcc69d58b0fc9a51e9cfcf2368b4faeb882d5a90991ffcdf1f7605bba55e53`，含 86 个扫描、
2,051 条观测。7 对交替 fresh-process 全部完成：candidate 7/7 更快；模块墙钟中位数
`0.228742 -> 0.190582 s`，改善 `16.6824%`；配对差 bootstrap 95% 区间
`[-0.044637, -0.031457] s`。模块墙钟 P95/max 从 `0.229523/0.229629 s` 降至
`0.194719/0.195816 s`。峰值 RSS 中位数 `165528 -> 165312 KiB`。

7/7 pair 的逐扫描后验、协方差、NIS、门控编号、完整发布载荷、业务操作数和最终离线导出
严格一致。每臂物化 11,188 条航迹；标量特征值摘要 11,188 次变为 56 次非空批量调用。

### 34.4 后续状态

1. D1 模块门通过，候选保持 default-off，不直接接入 main/scalable。
2. main 若决定集成，必须另行运行 clean、同提交、多 seed 的核心墙钟、D2 消费和 RSS 门；
   不得使用正式 seeds 1000--1019 做开发调参。
3. 当前没有系统实时、AirSim、目标硬件、RMSE、NEES 或正式 R0 证据。
4. `docs/AIRSIM_INTEGRATION_PLAN.md` 已检查；候选不改变 AirSim 输入、topic、外参、时钟或
   episode 编排，因此无需修改。
