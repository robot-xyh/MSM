# D1 多传感器融合与目标配准综述及子方案

**定位**: 雷达、声学、光电异构观测进入统一融合链路，输出带协方差、时间戳和状态机的 `GlobalTrack`。  
**边界**: 本文仅用于科研仿真、态势感知和人工复核接口设计，不包含真实火控参数、毁伤参数、自动处置控制律或绕过人工授权的流程。

---

## 正式 R0 收尾代次复核（2026-07-25）

正式来源提交 `2c7b425` 已完成 900 个 R0 episode。D6 标出的五个
`delayed_noisy` 非 clean-formal 项没有发现 D1 漏发、重复代次或尾部扫描丢失。五项
`posterior_generation` 均连续，完整物化与 state-only 计数对全部释放扫描守恒，扫描关闭后
缓冲为 0；最终 D1 批次均未接受新观测。

五项都进入 main 的 `finalize_unchanged_posterior_skip` 分支。该分支在 D2 source-evidence
签名相同且无待消费歧义侧车时跳过 D2。跨模块内容复核确认，来源观测签名相同不能证明完整
后验等价；五项最终状态、协方差或有效时刻仍发生变化，因此原 no-op 候选不满足正式验收。

main 已取消 finalize 的相同来源签名跳过，最终 pending D1 后验必须实际进入 D2；失败时不能
清空 pending。D2 replay-coast 隔离重复来源证据，不重复增加 hit、建轨或刷新来源证据时钟。
原五个 cell 的开发态定向重放均由 D6 验证：D1 final 等于 D2 consumed、skip 为 0、pending
为空。D1 默认算法、双时间戳、协方差、OOSM 和真值隔离不变。

修复已形成 clean source commit `98d01bf`，代码和五项定向验证已关闭。完整 900-cell
formal rerun 仍待存储条件和新最终 plan。旧 `2c7b425` 的正式制品保持原判定，不能由五项
定向结果原地改写。数据和验收边界见
`D1_FORMAL_R0_GENERATION_FINALIZATION_DIAGNOSIS_20260725_CN.md`。

## 最新增量：在线发布证据子集快照正式拒绝（2026-07-25）

- D1 已复核现有
  `FusionAdapter.consistency_evidence_snapshot(observation_ids)`。传入 ID iterable 时，
  接口先校验全部 ID，再按集合语义去重并返回精确子集；未知 ID 抛出 `KeyError`，空字符串
  或非字符串抛出 `ValueError`。校验在 ledger 投影之前完成。
- 子集快照使用 detached replay-counter overlay，不修改内部 evidence，不消费 pending
  ledger。重复读取保持业务内容稳定；内部 ledger 的 evidence 所有权异常继续失败关闭。
  最终 `consistency_evidence_records()`/`export_consistency_evidence()` 仍全量物化并清空
  pending。
- D1 API 对空 iterable 返回空快照。它无法知道 main 是否漏建 required ID。main 已按
  同一 release cycle 来源合同构造集合，并把空集合、未知/非法 ID 或返回子集缺项统一回退
  `full_consistency_snapshot_v1`，记录 fallback 原因。
- 新候选的 required ID 只允许来自同一 release cycle 的当前 source observations 和
  materialized tracks 的 `latest_observation_id`。D1 不读取 truth、目标真实编号或 D6
  标签，不改变 `global_track_id`、双时间戳、协方差、NED、来源谱系或业务 payload。
- 第一轮 A/B 只改变 publication snapshot selector，两臂均固定 replay-prefix reference
  `per_checkpoint_prefix_rebuild_v1`。reference/candidate 分别为
  `full_consistency_snapshot_v1` 和 `required_observation_subset_v1`。
- 2026-07-25 定向运行 replay-prefix 与 consistency evidence 测试，结果为
  `22 passed in 0.49s`。现有 D1 合同足以支持 main 候选，本次未修改 D1 源码或测试。
- main 已在 `IntegratedStackConfig` 和 CLI 接入 selector，默认保持
  `full_consistency_snapshot_v1`。source observations 与 materialized tracks
  `latest_observation_id` 在同一 release cycle 内收集、去重、排序；空集、未知/非法 ID
  或返回子集缺项回退 full snapshot 并记录原因。
- selector、execution config 和 diagnostics 已进入 runtime profile、observation
  governance、module final 与 episode summary。3/3/1、1.4 秒、seed 34 的确定性 episode
  中，candidate fallback 与 lookup miss 均为 0，D1 fused-tracks payload 与 reference
  完全一致；unknown-ID 与空 required 集合专项均回退 full 并形成固定 reason。
- D1 owner 复跑 module-stack 为 `62 passed, 1 warning`，scalable 全量为
  `263 passed, 1 warning`。警告是既有 Matplotlib `Axes3D` 环境提示；D1 定向
  consistency snapshot/replay-prefix 证据仍为 `22 passed in 0.49s`。D1 源码和测试未变。
- detached clean commit
  `028ac34debcfc5ca6ed2f6f88a5868d7b5f0f67b` 上的一对 200/200/2 smoke 先确认语义与
  失败关闭边界。该单 pair 结果只作为候选形成历史。
- D6 随后对 producer clean commit
  `d0219eb14c529a4fb9bf7d6610a9f32055a09206`、matrix SHA-256
  `6c808c4df8759fd893c6d37ff9dce4a1efa07f9867fc71aff47a55c5f8517338`
  完成独立评估。short seeds 1151-1160 各 2.2 秒，long seeds 1151-1153 各 10 秒，
  共 13 pair/26 个 fresh episode，0 reused、0 failed。
- 13/13 pair 的业务语义、有限状态、在线真值隔离、实现身份、D1/D2 在线记录、
  consistency digest/count、原 D1 operation counts 和诊断审计通过。candidate
  429/429 次子集成功，fallback、lookup miss、非法 ID 和空 required 集合均为 0。
  返回记录由 `1602170` 降为 `133917`，削减 `91.641524%`。
- 正式 verdict 为 `reject`，`main_default_promotion_allowed=false`。失败门为 short
  candidate 更快 `4/10 < 8/10`、short D1 fusion 改善 `-0.147877% < 1%`、short
  bootstrap 95% 上界 `1.374681% > 0%`。
- long candidate 更快 `2/3`、long D1 改善 `1.047143%`、short/long core 改善
  `0.330057%/0.837777%`、D2/RSS 守门和返回记录削减门通过，不能覆盖短时失败门。
  candidate 最低 RTF 为 `0.203423 < 1`。
- 内部返回对象工作量削减已经证实，短时端到端收益不稳定。candidate 不晋升，
  `full_consistency_snapshot_v1` 保持默认；系统实时 P1 继续开放。本结果不覆盖 AirSim、
  目标硬件、实机、实飞或正式 RMSE/NEES/NIS。

## 最新增量：固定滞后回放前缀累计摘要正式拒绝（2026-07-25）

- D6 已对 producer clean commit
  `7d2e987471b521a1e531bf03a5c99af5096f676a`、matrix SHA-256
  `85432d729877eff97e6f3dd517d4baa7a47f44a4fa42e6bfdc7ce85b8d9ec74b`
  完成独立评估。场景为 200 个目标、200 个资源和 2 个侦察节点；short seeds
  1151-1160 各 2.2 秒，long seeds 1151-1153 各 10 秒，共 13 pair/26 个 fresh
  episode，0 reused、0 failed。
- 正式 verdict 为 `reject`，`main_default_promotion_allowed=false`，
  `system_realtime_gap_closed=false`。失败门为 short 更快 `5/10 < 8/10`、short D1
  改善 `0.959611% < 1%`、short bootstrap 95% 上界 `0.619827% > 0%`、short core
  改善 `-0.256641% < 0.25%`、long core 改善 `-1.930083% < 0.25%`。
- 13/13 pair 的业务语义、consistency evidence digest/count、原 D1 operation counts、
  实现身份、诊断守恒和在线真值隔离通过。long D1 改善 `2.361778%`，内部物化记录减少
  `52.150746%`，RSS 和 D2 均值门通过。候选最低 RTF 为 `0.197441`，系统实时未闭合。
- 在线 snapshot 投影构造 `656481` 条记录。该计数说明内部物化削减没有消除全量快照
  返回对象的构造成本，是下一研究候选的直接依据。

- D1 已实现默认关闭的 `fixed_lag_checkpoint_prefix_cumulative_summary_v1`。reference
  `per_checkpoint_prefix_rebuild_v1` 仍是 `FusionAdapter` 和
  `Scalable3DFusionAdapter` 及 main 的默认。candidate 仅作显式研究入口，不得声称晋升。
- 候选只复用现有 checkpoint 已经证明过的完整前缀结果。命中前检查前缀完整性、首尾
  observation 身份与排序、checkpoint 修订、summary schema、consistency evidence 结构修订
  和当前回放上下文。任何条件不满足都回到原逐条路径。
- summary schema 为 `d1.fixed_lag_replay_prefix_summary.v1`，execution config 和
  diagnostics 分别为 `d1.fixed_lag_replay_prefix_summary_execution_config.v1` 和
  `d1.fixed_lag_replay_prefix_summary_diagnostics.v1`。selector、实现 ID、schema、
  诊断和实验制品均与已正式否决的
  `modality_conservative_quadratic_bound_v1` 分离。
- summary 只保存不可变 tuple 和标量，不引用可变 checkpoint 列表。一致性证据的逻辑刷新
  写入独立的前缀长度区间账本；证据写入、失效、前缀变化、fixed-lag 重基准、回退和最终
  导出前按后缀累计精确物化。因此候选没有跳过 `replay_revision/replay_count` 刷新。
- `replay_checkpoint_revision` 是完整中间 checkpoint 前缀的 O(1) 确定性完整性边界。
  D1 内部清空、后缀截断、重排和 fixed-lag 后缀替换统一先物化未决 evidence，再推进
  revision 并清除旧 summary。正常 append-only 在旧 summary 已验证、pending tuple
  对象绑定一致、新 ID 不重叠且排序严格后移时保留旧 ledger；revision 仍推进，summary
  仍失效。中间迟到观测先失效受影响后缀；命中路径不执行 O(n) 中间 checkpoint 全量核对。
- D1 保留 `consistency_evidence_records()` 的全量精确物化兼容语义，最终
  `export_consistency_evidence()` 继续通过该接口清空 pending。新增
  `consistency_evidence_snapshot(observation_ids=None)` 供在线 publication 使用；它对
  replay counter 做非破坏性精确 overlay，可按请求 ID 构造不可变记录，未知 ID 失败关闭。
- main 第一轮 dirty smoke（200v200、2 recon、seed 1151、2.2 s）暴露旧 append 路径：
  1,584 次 append 触发 1,584 次物化，逻辑和物化记录均为 8,687，压缩率 0。append 修复后
  main 独立复跑得到 `summary_hit/reused/logical/materialized=1584/7103/8687/7013`，
  append 物化为 0，压缩 `19.27017%`；1,372 个剩余物化原因全部是
  `public_evidence_snapshot`。两臂 consistency digest 均为
  `sha256:b579e62b65169791a1c9526eb5310ba7016149ddd501efe34e82a732c8bbda3a`，
  D1 fusion 为 `2.40147/2.30535 s`。
- 上述 19.27% 是正式矩阵前的历史 dirty smoke。正式三维质点矩阵已使用非破坏性
  snapshot，但调用仍请求全量 evidence；最终 offline export 保持 records/export。
- diagnostics 可区分 attempt、hit、fallback、fallback 原因、summary 构建、
  checkpoint/NIS/门控 ID 复用、逻辑 evidence 刷新、snapshot 投影和物化原因。既有
  `history_replay_count`、`replay_checkpoint_reuse_count` 和
  `cached_consistency_refresh_count` 等 operation counts 保持原语义。
- 冻结 fixture `d1-replay-prefix-summary-200v200-20260725` 含 200 个目标、200 个资源、
  2 个侦察节点、8 个扫描和 1,600 条匿名在线观测。fixture SHA-256 为
  `sha256:4e7fcb00432fc4c6736b5ba301d06363e73357fc91689618b6ddab0b1307490e`，
  生成观测 SHA-256 为
  `sha256:b44f971c2c6ac9b519cb7aba3f8df455727382132b2c5ec127280c97806dbae9`，
  online truth use 为 0。
- 每个 arm 建立独立新鲜 adapter，建轨阶段每扫描读取一次非破坏性 snapshot，执行 5 轮
  完整固定滞后回放并在末尾全量物化；预热 1 对后交替执行 7 对。
  reference/candidate 中位墙钟为 `0.039559965/0.025518551 s`，改善 `35.494%`，
  candidate `7/7` 更快。配对均值差 bootstrap 95% 区间为
  `[-0.014732573, -0.013135232] s`。性能 schema 为
  `d1.replay_prefix_summary_performance.v3`。
- 冻结 append 建轨阶段每 arm 的 revision/preserve/logical/materialized 为
  `1400/1200/5200/2400`，物化记录压缩 `53.846%`；正常 append 物化为 0，
  fixed-lag rebase 和后续 summary fallback 各 200 次。8 次 snapshot 中 4 次投影 pending，
  累计 800 个 ledger、2,000 个事件和 2,800 条返回记录，在线内部物化为 0。
- 冻结 fixture 前 3 个扫描派生的 0-2 秒 200v200 workload 得到 logical/materialized
  `400/0`、内部压缩 100%；一次有效 snapshot 投影 200 个 ledger 和 400 条记录，最终
  records 后 pending 为 0。该模块测试保持原 `>=20%` 门。
- 7/7 对的后验、协方差、NIS、门控 ID、consistency evidence、既有 operation counts、
  逐扫描 snapshot 序列、双时间戳、gate metadata、checkpoint 语义和公开 `GlobalTrack`
  精确一致。candidate 每个计时 arm 有 1,000 次 summary hit、6,000 个 checkpoint/NIS
  复用、6,000 条逻辑 evidence 刷新、1,200 条最终物化记录和 0 次 timed fallback。
- 专项回归覆盖迟到量测、门控拒绝、部分前缀、前缀变化、无 checkpoint、
  summary schema/version 失配和 consistency 配置不兼容。失败条件均有可审计 fallback，
  不通过减少观测、缩短 6 秒窗口、放宽门控或跳过 evidence 刷新获得性能收益。
- 中间顺序专项在四个 checkpoint 之间插入迟到观测，确认旧后缀先失效、revision 至少随
  截断和重建推进、摘要按新顺序建立，并与 reference 的内部状态和公开输出一致。
- 连续 append 和频繁 snapshot 专项确认 pending ledger 跨多次读取与追加保留，每次返回
  精确 replay counter；append 后再插入中间迟到量测会先物化再截断，最终 records/export
  清空 pending。
- 最后源码状态的 D1 全量回归为 `488 passed in 30.96s`；新增和修改的 Python 入口均通过
  `py_compile`。
- 模块微基准通过只作为候选形成历史。正式准入已经以 `reject` 审结，reference 保持默认，
  candidate 保持默认关闭。本次 source commit、matrix SHA、门限、失败 pair 和 D6 verdict
  不得调整或覆盖。
- 后续独立候选已完成 main selector、调用点、配置、诊断、CLI、模块栈回归、一对 clean
  200/200/2 smoke 和独立正式评估；默认仍为 reference。它使用新的 implementation ID 和
  schema，不复用本候选身份，也不改写任一拒绝结论。
- 本轮没有改变 AirSim producer、DTO、episode、坐标或双时间戳合同；新增了 D1 runtime
  publication 只读接口。`docs/AIRSIM_INTEGRATION_PLAN.md` 已同步正式默认状态和接线边界。当前结果
  不是 AirSim、目标硬件、实机、实飞、系统实时、RMSE、NEES 或 NIS 证据。

## 最新增量：模态感知保守稀疏预筛正式拒绝（2026-07-25）

- D1 已实现默认关闭的 `modality_conservative_quadratic_bound_v1`；reference
  `disabled_v1` 保留原四维非雷达批量伪逆和原操作顺序。
- 预筛只使用现有量测空间的严格下界。雷达/LiDAR 使用位置残差，声学使用环绕角残差，
  光电使用投影像素残差；未认证、奇异、非有限和未知模态全部 fail-open。
- execution config v1 记录默认、实现 ID、rollback 和逐模态策略；diagnostics v2 按
  `radar/lidar/acoustic/acoustic_3d/eo/other` 六个固定桶记录候选 pair、剔除、精确
  求解、精确门内通过和 fallback，不读取真值。
- D6 schema `d6.d1_association_sparse_prefilter_multiseed_evaluation.v1` 绑定 clean source
  commit `9302ccede2ca513c2235370e1a464fc88bc41150` 和 matrix SHA-256
  `a7162d014d1c3c0f207355b24a5d7159bf3486d134ca21876f7469d1e915b71d`。
- 冻结场景为 200 个目标、200 个资源、2 个侦察节点，short seeds 1131-1140、long seeds
  1131-1133，共 13 pair/26 个 fresh episode。13/13 业务语义、有限状态、online truth
  use=0、实现身份和逐模态 exact gate-pass 相等均通过。
- 非雷达精确求解由 `298109` 降至 `39837`，削减 `86.636767%`；该结果只说明局部操作数
  下降，不构成主线准入。
- 五个冻结性能门失败：short 更快 `7/10 < 8/10`；short D1 fusion 改善
  `0.228437% < 1%`；short paired bootstrap 原始变化 95% 上界
  `0.443531% > 0%`；short core 改善 `0.091096% < 0.25%`；long D1 fusion 改善
  `0.713776% < 1%`。
- D6 verdict 为 `reject`，`main_default_promotion_allowed=false`。`disabled_v1` 继续作为
  默认；candidate 只保留为显式研究入口。冻结矩阵、门限和失败 pair 不得修改或重解释。
- 120 航迹、14,400 pair/模态、7 次交错微基准及其四类非雷达合计 P50 改善 `9.436%`
  作为历史候选形成证据保留，不覆盖正式拒绝结论。
- 候选最低 RTF 为 `0.206273 < 1`，系统实时未闭合。AirSim、目标硬件、实机、实飞和正式
  融合精度均未由本三维质点矩阵覆盖。
- AirSim producer、DTO、runtime bus 和坐标时间接口未改变；AirSim 集成文档已检查，无需
  更新。本轮实验文档已同步正式 reject，并保留历史微基准。

## 最新增量：在线批次到扫描帧正式准入与默认提升（2026-07-25）

- D6 schema `d6.d1_online_batch_frame_multiseed_evaluation.v1` 绑定 source commit
  `43feaf600f288a85ce76a76862334256f0d0d352` 和 matrix SHA-256
  `4afbf9ac273763a16aa01cc744fd67b52e437099460b33377a128f986ac5719b`。
- short 10 pair、long 3 pair 共 13 pair/26 episode，全部 gate 通过。short/long
  scan-input 改善 `38.289241%/36.275282%`，core wall 改善
  `4.252745%/4.916501%`。
- candidate request/closed 为 `2665/2665`，fallback 0，online truth use 0；业务语义、
  实现身份、有限状态、守恒、RSS 和 D2 均值门通过，D6 结论为 `admit`。
- `ONLINE_BATCH_FRAME_DEFAULT_IMPLEMENTATION` 现选择
  `closed_immutable_batch_to_frame_v1`。builder/helper 的未显式 selector 路径使用
  candidate；单个 `implementation=ONLINE_BATCH_FRAME_REFERENCE_IMPLEMENTATION` 参数可
  回退 `convert_then_frame_v1`。
- diagnostics 的 `candidate_default_enabled=true` 反映当前声明默认值。显式 reference
  仍记录 selector、实现 ID、reference request/path 和守恒，不影响回退审计。
- 默认提升不改变候选核心算法、完整 raw batch 检查、最终只读帧检查、普通异常 fallback、
  `MemoryError` 失败关闭、协方差、双时间戳、NED、谱系或融合门控。
- D2 均值门通过，但 short/long 单 pair 最大增幅为
  `15.778858%/14.408510%`，仍需长时容量观察。candidate 最低 RTF 为
  `0.204490 < 1.0`，系统实时未闭合。
- 证据只覆盖 2026-07-25 三维质点仿真，不是 AirSim、目标硬件、实机、实飞或正式融合
  精度结论。冻结 matrix/config 和正式 D6 制品保持不变。

## 历史增量：默认 R0 在线批次到扫描帧封闭交接候选（2026-07-25）

- main 的默认无 source-key R0、200v200、2.2 s、seed 1112 开发 cProfile 含 95 个 batch
  和 2,044 条观测。converter/frame 集合检查各 95 次，累计
  `1.120932/1.115831 s`；逐 measurement raw 检查 2,044 次、`0.206688 s`。
- D1 新增 `OnlineBatchFrameBuilder` 和 `sensor_scan_frame_from_online_batch()`。
  reference ID 为 `d1.online_batch_frame.convert_then_frame.v1`，保持默认；candidate ID
  为 `d1.online_batch_frame.closed_immutable_batch_final_frame_validation.v1`，默认关闭。
- candidate 先完整检查 raw batch，再对冻结数据类、独立只读数组和受支持元数据执行结构
  合格检查并建立内部深快照。该检查不声称 frozen dataclass 或 `MappingProxyType` 绝对
  不可变。私有转换完成后，`SensorScanFrame` 对最终只读快照执行完整身份、协方差、双
  时间戳、NED、扫描一致性、重复 observation ID 和重复 lineage 检查。
- 普通映射和结构不合格载荷执行完整 reference 回退；结构检查或快照普通异常有明确计数并
  回退 reference。`MemoryError` 计为 resource rejection 后原样抛出。变异载荷拒绝；公开
  裸 measurement、裸 observation 和 frame 路径没有验证绕过参数。
- 冻结 200-measurement 微基准预热后交错 7 次。reference/candidate 中位墙钟为
  `0.089842/0.050648 s`，改善 `43.625675%`、加速 `1.773857x`，candidate `7/7`
  更快。两臂规范帧 SHA-256 均为
  `7b46fdc8beecb130914c1026fdc3d476ab6f94b53a33e76db3edcc188fdff83b`。
- reference 的整批 raw、逐 measurement raw、转换后集合和最终 frame 检查为
  `7/1400/7/7`；candidate 为 `7/0/0/7`。全部异常摘要、实现身份和计数守恒通过。
- 新增字段传播锁定确认 5 个 batch 字段和 11 个 measurement 字段全部进入快照；异常注入
  确认快照 `RuntimeError` 回退 reference、`MemoryError` 不回退，所有 diagnostics 守恒。
  专项 `19 passed`，main 当时复跑 D1 全量 `443 passed in 24.02s`。该历史阶段只达到 D1
  模块门槛，必须显式接入 selector 并等待 D6 判定；当前正式准入和默认值以上一节为准。
- 本结果不覆盖完整默认 R0、AirSim、目标硬件、实飞、系统实时、RMSE、NEES 或 NIS，也不
  改变不透明来源缓存的正式拒绝结论。

## 最新增量：不透明来源标识有界代际缓存（2026-07-25）

- main 的 clean `cd9c60c` profile 显示，无 source-key/hold 时
  `process_scan_batch/global_tracks=4.852/0.633 s`；显式 source-only 时为
  `5.796/1.501 s`，`_to_global_track=1.314 s`。成员 token、source track ID 和 source
  key 为 `0.245/0.294/0.337 s`。这些数据用于选题，不参与模块准入。
- 本轮只缓存由 `(publisher_node_id, publisher_epoch, track_id)` 唯一决定的三个不透明
  来源字符串。candidate/reference ID 分别为
  `d1.publication.opaque_source_identity.bounded_generation_lru.v1` 和
  `d1.publication.opaque_source_identity.per_publication_build.v1`。
- `cached_opaque_source_identity` 默认 `False`。缓存默认容量 1,024、上限 4,096，按最近
  最少使用淘汰。node 或 epoch 变化自动失效，episode reset 可显式清空；不能证明键合同的
  路径执行 reference。
- 缓存项是冻结对象中的字符串，不包含 dict 或 ndarray。state、covariance、timestamp、
  A95、track level、last NIS、record metadata、source support、identity likelihood、
  association diagnostics 和 operation summary 每次重新生成。
- 2026-07-25 模块微基准显式开启 source-only、关闭 hold。200 航迹每个样本发布 56 次，
  即 11,200 次物化；每臂预热后交错 7 轮。中位墙钟
  `0.348622 -> 0.127734 s`，改善 `63.360%`，加速 `2.729x`，candidate `7/7` 更快。
- reference/candidate 请求均为 78,800 次。构造由 `78,800 -> 200`；candidate 命中/未命中
  为 `78,600/200`。完整 `GlobalTrack.to_dict()`、数量和业务字段相同，在线 truth 使用为
  0，固定大小计数守恒。
- 测试覆盖默认关闭、无 source-key 惰性、别名隔离、动态字段新鲜性、代际/reset、容量、
  OOSM、重放、新生和航迹移除。D1 全量为 `424 passed in 21.81s`。
- 模块预注册门槛为中位改善至少 `2%`、candidate 更快比例至少 `70%`，当前通过。随后
  main 在 clean source commit `d8fc76c066f21b077154f7be33c0b43558d237e5` 上完成
  source-only、hold=false 的同提交正式矩阵。short 10 pair、long 3 pair 共 26 个 fresh
  arm，`0 reused/0 failed`。
- short/long D1 融合改善为 `9.465972%/6.437432%`，核心墙钟改善为
  `2.845610%/2.728043%`，candidate 分别 `10/10`、`3/3` 更快。标识构造由
  `312,317 -> 2,612`，构造减少率与缓存命中率均为 `99.163670%`。
- 19 个冻结准入门中 18 个通过。short D2 关联耗时增幅为 `4.677567%`，long 为
  `5.605213%`，后者超过 `5%` 上限；`long_seed_1101` 增幅 `19.069868%`，完整保留。
- D6 正式判定 `optimization_admitted=false`、`system_realtime_gap_closed=false`；
  最低实时因子为 `0.193887`。候选不晋级，D1 默认继续
  `cached_opaque_source_identity=False`，main 默认继续 `per_publication_build_v1`。
- 本轮准入已经审结，不能删除 seed、调整门限或用语义等价豁免性能门。结果只覆盖显式
  source-only、hold=false 的三维质点运行面，不外推到默认无 source-key R0、AirSim、
  目标硬件、实飞、RMSE、NEES 或 NIS。

## 最新增量：结构稀疏数值雅可比正式准入（2026-07-25）

- 正式矩阵绑定 clean commit
  `9d1f54f8540fdc4a7a1011121aafac5718290122`。场景为 200 目标、200 资源和 2 个侦察
  节点；short 10 pair 每臂 2.2 s，long 3 pair 每臂 10 s，共 26 个 fresh arm。
- `26/26 complete`、`0 reused`、`0 failed`。13/13 pair 的制品来源、业务语义、有限状态、
  在线真值隔离、显式实现身份和结构雅可比操作数全部通过。
- short 的 D1 融合与核心墙钟改善为 `6.084778%/1.897370%`，candidate `10/10` 更快；
  long 为 `4.676061%/1.786530%`，candidate `3/3` 更快。量测函数求值减少
  `53.846154%`。
- D6 判定 `availability=true`、`optimization_admitted=true`。结构稀疏数值雅可比在
  scalable 3D main 集成中的候选准入 P1 关闭，reference 保留为回退。
- 2026-07-25 D1 全量回归为 `414 passed in 21.52s`。
- main 已把 scalable 3D 的 `IntegratedStackConfig` 和 `run_episode` 命令行默认晋级为
  `known_dimension_structural_columns_v1`，`dense_output_probe_v1` 保留显式回退。
- 2v2 默认 smoke 的 observation governance、episode summary 和 module final diagnostics
  三个表面均记录候选，状态有限且在线真值使用为 0。该 smoke 只验证默认接线和安全边界。
- D1 独立 `FusionAdapter(structured_numerical_jacobian=False)` 构造默认仍然不变，显式
  `True` 可用。scalable 3D main 默认晋级不等于 D1 独立 API 默认切换。
- 候选最低实时因子为 `0.180726`，`system_realtime_gap_closed=false`。本轮不包含
  AirSim、目标硬件、实飞、RMSE、NEES 或 NIS 证据。

## 结构稀疏数值雅可比模块候选基线（2026-07-24）

- main 的 200v200、2.2 s、seed 1111 默认路径 cProfile 中，`numerical_jacobian` 累计
  `0.712 s`。扫描模型缓存和非雷达创新批处理已经关闭对应重复工作，本轮没有重复这些候选。
- 声学、光电、激光雷达和无径向速度雷达观测方程只依赖位置三维。候选直接使用已知输出维数，
  只对结构活动列执行原中心差分；含径向速度雷达保留全部六列。
- reference/candidate 实现 ID 分别为
  `d1.ekf.numerical_jacobian.dense_output_probe.v1` 和
  `d1.ekf.numerical_jacobian.known_dimension_structural_columns.v1`。
  D1 独立 `FusionAdapter` 的 `structured_numerical_jacobian` 构造默认为 `False`。
- 冻结 480 个混合量测模型、每样本 20 轮、9 次交错采样。中位墙钟
  `0.444645 -> 0.319552 s`，改善 `28.13%`，candidate `9/9` 更快；量测函数求值
  `124,800 -> 72,000`，减少 `42.31%`。
- 雅可比、归一化创新平方和门控决策摘要严格一致。扫描级回归覆盖关联结果、航迹 ID、状态、
  协方差、双时间戳和乱序重放。D1 全量 `414 passed in 21.31s`。
- 候选达到模块门槛后进入 main 同提交准入流程。short 10 seed、long 3 seed 的 200v200
  配对矩阵及 D6 独立判定已经完成，当前结论见上一节。
- 本轮没有 AirSim、目标硬件、RMSE、NEES、NIS 或系统实时证据。PSD/协方差安全门、
  fixed-lag、门限和量测频率未改。

## 最新增量：六维协方差 PSD 检查候选（2026-07-24）

- profile 显示 200v200、2.2 s 的 D1 `process_scan_batch` 累计 `5.029 s`，
  `_limit_covariance_diagonal` 累计 `0.822 s`，`eigvalsh` 调用 70,183 次。
- 新候选只对有限 `6x6` 矩阵先做 Cholesky。成功后还需通过
  `9.094947017729282e-13` 的归一化行列式安全门；失败或安全门拒绝时完整回到现有
  `eigvalsh`、相关矩阵投影、相关收缩和对角回退。半正定、近奇异、机器精度附近不定、
  一般不定和非有限边界未放宽。
- 开关 `cholesky_covariance_psd_fast_path` 默认 `False`。实现 ID 和独立诊断明确区分
  reference/candidate；当前 candidate 为
  `d1.fusion.covariance_psd_check.cholesky_6x6_relative_determinant_guard_then_eigvalsh.v2`。
  `attempt = success + fallback` 可审计，计数不改变业务 metadata。
- 合成输入 SHA-256 为
  `f26445ee25cd87ec52a993672d9900baba3b41f7999155de35b0c7bd3424a525`。2,000 个矩阵、
  每样本 10 轮、9 次交替的中位墙钟为 `0.558490 -> 0.588263 s`，candidate 慢
  `5.33%`，`0/9` 更快。
- 20,000 次候选检查为 19,800 次成功和 200 次回退。cProfile 中 `eigvalsh` 调用
  `20,400 -> 600`，同时新增 20,000 次 Cholesky。covariance 和 reason 摘要严格一致。
- D1 全量 `404 passed in 21.39s`。当前 v2 没有性能收益，安全门前旧计时已被正式重跑
  替代；候选只保留为默认关闭的研究对照，不建议 main 接入。系统实时、AirSim、目标硬件、
  RMSE、NEES 和 NIS 继续开放。

## 最新增量：匀速模型矩阵复用正式准入（2026-07-24）

- 剖析调用链为 `process_scan_batch -> _predict_all_to/
  _state_from_complete_replay_checkpoints/_replay_record -> predict_to`。代表 profile 中
  `predict_to` 32,345 次，匀速矩阵构造 32,217 次。
- D1 只实现一个显式候选
  `d1.fusion.cv_motion_model.bounded_exact_lru.v1`。开关
  `cached_cv_motion_model` 默认 `False`，reference ID 为
  `d1.fusion.cv_motion_model.per_prediction_build.v1`。
- 候选按精确 `(dt, process_noise)` 缓存写保护矩阵，默认容量 128、最大 4,096，并记录构造、
  命中、未命中、淘汰、峰值和绕过。非有限值和非正时间差回到 reference，过程噪声变化不会
  复用旧配置。
- 200 状态、100 步、7 次交替专项中，中位墙钟
  `0.220679 -> 0.103950 s`，热点内 `2.123x`；模型构造 `20,000 -> 8`，最终状态摘要严格
  一致。专项 `6 passed`，D1 全量 `395 passed in 21.41s`。
- 本项没有删减发布、降频、缩短 fixed-lag、放宽门控、跳过协方差治理或使用在线真值。
  D1-owned 候选和模块证据完成。
- 正式证据绑定 source commit
  `44223566439a446fc49f2a3fd861d1d51bd676b9` 和矩阵 SHA-256
  `9898656598f0fa282620afe2384a3d656b7496f8957109c413bcb62069fd2e9a`。场景为
  200 目标、200 资源和 2 个侦察节点；short 10 pair、long 3 pair，共 26 个全新 arm。
- 13/13 业务语义、有限状态、在线真值隔离、实现身份和缓存审计通过。short D1 fusion
  `3.289739 -> 3.061518 s`，改善 `6.9271%`、10/10 更快，bootstrap 95% 区间
  `[-7.7968%, -6.0841%]`；long 为 `23.304548 -> 21.776847 s`，改善 `6.6103%`、
  3/3 更快。
- 核心墙钟 short/long 改善 `2.4060%/2.4537%`；D2 association 变化
  `-0.1082%/-2.6729%`；RSS 均值增幅 `0.0145%/0.2959%`，任一 pair 最大
  `0.8629%`。
- 896,820 次预测请求中，reference 构造 875,031 次；candidate 构造 3,535 次、命中
  871,496 次，构造减少率和命中率均为 `99.5960%`。D6 判定
  `d1_optimization_admitted=true`。
- D1 `FusionAdapter` 默认 `cached_cv_motion_model=False` 保持兼容；main 集成默认已晋级为
  `bounded_exact_lru_v1`，scalable 3D 全量 `212 tests` 已通过。最低实时因子
  `0.1739499`，系统实时、AirSim、目标硬件、RMSE、NEES 和 NIS P1 继续开放。

## 最新增量：GlobalTrack 发布元数据 v2 正式准入（2026-07-24）

- clean source commit `be399e138762f5e660f553c8caa812d52ab38c61` 已完成 200 目标、
  200 资源、2 个侦察节点的 short 10 seed 和 long 3 seed 正式矩阵，共 13 对、26 个 arm，
  0 reused、0 failed。
- D1 fusion short/long 改善 13.5447%/26.8298%，核心墙钟改善
  6.5677%/18.2438%，D2 association 耗时降低 16.1939%/35.6213%；13/13 业务语义、
  有限状态、在线真值隔离、实现身份、D2 审计和 RSS 门通过。
- 候选 `d1.publication_metadata.immutable_shared_audit.v2`、合同
  `d1.publication_audit_tree.v2` 已准入。累计 702 次合同验证、702 次内容审计、
  139,920 次身份复用，合同拒绝为 0。D6 判定 `d1_optimization_admitted=true`。
- main promotion `f5b350b` 默认选择 `immutable_shared_v2`；D1 构造器默认仍为 `False`，
  reference 可显式对照。系统最低实时因子 `0.1730801`，逐批 D2 审计明细、AirSim、硬件和
  正式 RMSE/NEES/NIS 仍开放。

## 最新增量：扫描输入正式同提交准入（2026-07-24）

- 正式证据来自 clean commit
  `d14285e4fdeb2f2e2cd32fad2f6d42e30f9e73a7`。short 使用 seeds 1101-1110、
  2.2 s，long 使用 seeds 1101-1103、10 s；13 pair 的 reference 与 candidate 来自同一
  提交，唯一运行差异是 `d1_scan_input_implementation`。
- short scan-input 墙钟 `1.2124522798461839 -> 1.145650333847152 s`，逐 pair
  平均改善 `5.360121886647966%`，9/10 更快，原始相对变化 bootstrap 95% CI 为
  `[-8.208165356448217%, -3.0841406102053194%]`。
- long scan-input 墙钟 `6.687633245543111 -> 6.3406803108907 s`，逐 pair
  平均改善 `5.142481684491682%`，3/3 更快，95% CI 为
  `[-8.837128529506151%, -1.6693612946922343%]`。
- 13/13 业务语义、有限状态、在线真值隔离和实现身份检查通过；核心墙钟 short/long
  仅改善约 `0.7187%/0.5792%`，RSS 门通过。D6 判定
  `d1_optimization_admitted=true`，`candidate_v2` 正式准入，扫描输入优化正式矩阵 P1
  关闭。
- 系统实时缺口未关闭：`system_realtime_gap_closed=false`，候选最低实时因子为
  `0.14342687633969603`。本批是三维质点证据，不是 AirSim、实机或目标硬件结果；
  RMSE/NEES/NIS 和更长时容量仍开放。

## 最新增量：扫描输入剩余热点（2026-07-24）

- 正式 v3 candidate 的 short/long scan-input 累计均值为 `1.220624/6.572076 s`；
  long D2 association 为 `5.815163 s`。570 帧、10,810 条匿名观测的 D1-only cProfile
  总计 `2.195 s`，`_claim_for_frame/_json_safe/lineage` 分别为
  `2.085/1.136/0.379 s`。
- 当前保留 `reference_v1`，默认使用 `candidate_v2`。candidate 复用已验证谱系，数值
  ndarray 批量 finite 检查后一次 `tolist()`，每条谱系的 canonical JSON 同时用于摘要和
  排序，缓冲只做一次 ready/remaining 分区，并缓存 observation 数。谱系缓存身份和不可变
  内容已进入帧完整性封印；异常替换时从 observations 重建。
- `execution_config()` 和 `d1.scan_input.performance_diagnostics.v2` 明确记录实际路径。
  event-time config、业务事件/audit schema、双时间戳、NED、covariance、truth fail-closed、
  来源谱系、6 s fixed-lag、量测频率、门限和 `global_track_id` 不变。
- 冻结输入 SHA-256 为
  `5b47f3cf43a9bf78bfca0db249bbefeb709a10c1a7aa6bb4277226fc2144e2d6`。7 轮交错
  P50/P95 为 `1.078281/1.084012 -> 0.756634/0.766820 s`，P50 下降
  `29.830%`。claim/content/frame digest、事件字段、发布顺序和 audit 严格一致。
- 谱系重建 `10,810 -> 0`、排序键规范化 `21,620 -> 10,810`、缓冲分区 item 访问
  `35,406 -> 17,703`、缓冲观测数重扫 item `67,876 -> 0`。新增谱系缓存篡改严格 A/B
  回归后，专项 `26 passed in 0.29s`，D1 全量 `361 passed in 20.67s`。
- Python 普通数值序列快路因 profile 退化已撤销；expiry 保持逐项删除，避免改变事件中间
  计数。本段 D1-only 证据不含融合、D2、AirSim 或目标硬件；其后的正式 13-pair
  scan-input 矩阵已按上节完成并准入。系统实时 P1 仍开放。

## 最新增量：正式多 seed/长时准入（2026-07-24）

- v3 矩阵包含 short seeds 1101-1110、2.2 s 和 long seeds 1101-1103、10 s，共
  13 组配对、26 个三维质点集成 episode。26/26 正常退出，13/13 跨构建语义检查通过。
- 标量 reference 为 `a5a472cf81496d94a98db3deb88a3d5c6951f0ce`，向量化 candidate
  为 `064cbb979d3bab68fee995e476df25709eb666db`。两臂共同带有该 candidate 提交中的
  D1 PSD 修复和 `e4147b8` 的 D2 误警审计修复，性能差异只对应协方差成对限制实现。
- short 的 D1 融合累计墙钟由 `4.029165 s` 降至 `3.652252 s`，改善 `9.35462%`，
  10/10 更快，配对原始变化 95% CI 为 `[-10.914359,-8.113134]%`；单次融合 P95 改善
  `6.652902%`。
- long 的 D1 融合累计墙钟由 `32.954357 s` 降至 `30.768826 s`，改善 `6.631993%`，
  3/3 更快，配对原始变化 95% CI 为 `[-7.279095,-5.406805]%`；单次融合 P95 改善
  `6.655511%`。
- D6 判定 `d1_optimization_admitted=true`。P0 PSD 输出和 P1 向量化准入关闭。
  `system_realtime_gap_closed=false`，candidate 最低实时因子为 `0.143397`。
- 正式 manifest SHA-256 为
  `40669d10fff8367aa31e24624bab802d8bc3de6b01aaa1e5c92d054753ed93ec`。矩阵不含
  RMSE、NEES、NIS、AirSim 或目标硬件证据；融合质量和系统实时性仍开放。

## 最新增量：全维协方差正半定治理（2026-07-24）

- seed 1103、200v200、10 s 候选在发布时刻 `7.85180018473111 s` 暴露
  `global_track_031` 非正定 covariance。输入最小特征值为 `+7.506060086e-04`；一个交叉项
  经过 `0.999` pairwise 裁剪后，输出最小特征值为 `-9.247657800e-04`。
- 逐对约束只能保证每个二维主子式，不能保证六维整体正半定。故障前 58,776 次
  scalar/vectorized 同输入双算没有任何 reason 或数组差异；单独标量复跑也完全复现，向量化
  不是根因。
- 当前统一路径在对角和逐对限制后执行相关矩阵特征值投影、单位对角归一化和与单位阵的凸组合，
  再恢复原治理对角。最多 3 次严格复核；极端浮点情形对角回退。输出记录 projection reason、
  迭代数、特征值 floor 数、相关收缩数和 fallback 数。
- 固定失败、1-6 维随机/极端性质、隐藏非正定、审计、scalar/vectorized 等价和
  双时间戳/谱系/6 s fixed-lag 回归通过。专项合计 `28 passed`，D1 全量
  `352 passed in 20.52s`。
- 修复后同配置 seed 1103、10 s 集成运行处理 10,554 条匿名在线观测并完成，
  `finite_state=True`、online truth 0，原 D2 拒绝消失。RTF `0.157583` 仅作断点闭合证据。
  上节正式矩阵已完成；AirSim、目标硬件、系统实时和 RMSE/NEES/NIS 保持开放。

## 最新增量：协方差成对限制热点（2026-07-24）

- 最新 seed 1100 冻结输入含 89 个扫描、2,035 条匿名观测和 202 条终态航迹，输入
  SHA-256 为 `54bed9d7f03497967c3f8478a9e0cf1385e85bcc512bf769df849b7b1ab3e0ec`，
  在线 truth 使用为 0。
- 调用审计没有发现可删除的同一后验重复治理。10,832 次 `_predict_all_to()` 限制都发生在
  状态协方差已由时间推进改变之后；另有 1,789 次更新后重放和 202 次新生限制。现有
  `current_state_covariance_limited` 已阻止同一当前状态在物化时重复处理。
- 单一优化保留旧上三角标量循环作为
  `vectorized_covariance_limit=False` reference，并默认使用批量上三角裁剪。1 至 6 维
  只复用不可写的索引拓扑，不缓存状态或协方差。每一对
  \(P_{ij}\) 仍按 \(0.999\sqrt{\max(P_{ii},0)\max(P_{jj},0)}\) 限幅；对角上下界、
  对称化、reason、非法状态重置和在线观测 covariance fail-closed 不变。
- 同一 release-group 和物化调度先预热，再交错运行 5 轮。reference/optimized 纯融合
  均值为 `3.001196/2.610975 s`，P50 为 `3.011440/2.614061 s`，P95 为
  `3.023308/2.660813 s`；P50/P95 加速 `1.152x/1.136x`，5/5 轮优化更快。
  cProfile 中 limiter 累计为 `1.047145/0.426826 s`。
- 预热、5 轮和 profile 均保持逐扫描状态、协方差、双时间戳、来源谱系、分级、操作计数、
  累计诊断、延迟审计、终态 `GlobalTrack` 和 consistency evidence 严格等价。6 s
  fixed-lag、观测数、门限、NED 和 `global_track_id` 未改变。
- 10 s 长夹具另只执行一对语义对照。771 扫描、11,889 观测、4,009 次 fixed-lag rebase
  和 11,888 条 OOSM 在两臂一致。专项 `18 passed`，D1 全量
  `342 passed in 19.73s`。该结果是正式矩阵前的冻结质点基线；上节已关闭 clean
  full-stack 多 seed 准入。AirSim、目标硬件、实时和精度验收仍由后续任务执行。

## 最新增量：A2 原子 shadow clean 成对复核（2026-07-24）

- main clean commit `7cc2d0cfd598a72d60c6ba8c7d4a283f4e5a897d` 已用原子入口完成
  seed 1100、200v200、2.2 s、`recon_count=2` 的 control/atomic-shadow 成对运行；两份
  manifest 均为 `repository_dirty=false`。
- control/shadow 墙钟为 `10.735151270986535/19.449935468961485 s`，开销
  `+81.1799%`；实时倍率为 `0.204934/0.113111`。shadow P50/P95/max 为
  `1024.838/1536.429/1549.436 ms`。
- shadow 共 9 条发布、46 条决策，0 accepted、46 `oosm_scan` rejected、0 error。9/9 次
  post-integrity 通过，atomic failure 和 materialized shadow 均为 0。
- D1/D2/D3 终态在两臂均为 `202/201/186`；在线 truth、禁止写入、D2/D3 shadow 消费和
  `global_track_id` 变化均为 0。安全隔离和业务非干预子门闭合。
- 性能门和有效 treatment 门失败，A2 不准入。全拒绝场景中旧 prepared-handle 路径本来就
  跳过 assemble，原子入口没有第二次装配复核可消除；主要成本仍是前后完整摘要、规范准备和
  post-integrity。A3/A4 与 seeds 1101/1102 继续停止。

## A1 原子 publication overlay（2026-07-24）

- D1 新增
  `run_experimental_centroid_publication_overlay_atomically()`，状态为
  `IMPLEMENTED_UNIT_TESTED_OFFLINE_ATOMIC_OPTIMIZATION`。它在一个同步调用内内部完成
  prepare、evaluate、detached assemble 和 post-integrity verify，不向调用方公开 prepared
  descriptor。
- 公共 prepare/evaluate/assemble API 未改变。显式 prepared handle 每次跨公共调用边界仍
  重算完整规范载荷摘要。原子入口只减少同一次内部流水线的重复复核，不裁剪 metadata、
  lineage/source support、identity、`last_nis`、全局编号、时间戳、分级、state/covariance、
  NED 或禁止身份字段检查。
- 200 航迹正常 accepted 工作量为 1 次完整描述、200 条描述摘要、1 次后置完整性复核、200 条
  规范复核摘要；另对 200 条 detached shadow 生成发布摘要。rejected 路径不物化 shadow。
- 公开结果可由标准 JSON 编码并提供确定性字节形式。canonical/shadow 发布摘要使用相同的
  完整航迹摘要清单语义；装配异常与后置完整性失败均恢复输入 generation 状态。
- post-integrity 失败时不公开 provisional accepted shadow，decision 转为
  `prepared_canonical_publication_mismatch`，generation 状态恢复到输入。数组、嵌套
  metadata、source support、identity、`last_nis`、全局编号、时间戳和分级的调用内变化均有
  fail-closed 测试。
- 2026-07-24 聚焦 `36 passed`，D1 全量
  `324 passed`。2/3/5 成员决策与 `de73cb2` 基线逐字节一致，只读嵌套 metadata、
  ID/速度/相对位置保持、协方差不收缩和规范引用隔离均通过。
- main 已完成上节 clean 原子成对复核；安全子门闭合，A2 性能门和有效 treatment 门未关闭。
  A3/A4 与 seeds 1101/1102 继续停止。AirSim 接口不受影响。

## 0. A1 准备对象优化状态（2026-07-23）

- D1 已实现 `prepare_experimental_centroid_canonical_publication()`。它对完整规范
  `GlobalTrack` 序列执行一次校验和摘要，供 evaluation 与 shadow assembly 只读复用。
- 准备对象不持有可变航迹、metadata 或 NumPy 引用。每个复用边界核对对象绑定并重算每条
  航迹完整规范载荷 SHA-256；显式对象与输入序列、成员对象或内容不一致时 fail closed。
  工作量计数报告完整描述轮次、完整性复核轮次和摘要数。
- 完整 metadata、lineage、source support、identity、双时间戳、state/covariance 和
  `global_track_id` 仍进入强摘要。优化没有裁剪成员、弱化哈希或使用 truth。
- accepted shadow 可按值复制嵌套只读 `Mapping`、tuple、frozenset 和 NumPy 值，避免
  `deepcopy(MappingProxyType)` 失败。拒绝仍返回原序列对象。
- 聚焦 `21 passed`，D1 全量 `308 passed in 19.69s`。2/3/5 成员决策与 A1 基线逐字节一致；
  200 航迹只读 metadata 固定夹具完成一次描述、两次完整载荷复核和 accepted 装配。state、
  covariance、嵌套 metadata、source support、identity、全局编号、时间戳和分级修改均阻断
  复用。
- main 已在提交 `2b976a7` 显式接入准备对象，并完成 seed 1100、200v200、2.2 s、
  `recon_count=2` 成对开发复跑。9/9 次评估均使用 prepared handle 且完整性校验通过；
  46 evidence 全部以 `oosm_scan` 拒绝。过滤 9 条专属审计记录并归一化不透明计划编号和总线
  序号后，3294/3294 条业务记录逐条一致，归一化 SHA-256 同为
  `bb7eabca...c3855a2`；真值 NPZ、离线 truth labels 和 proximity 文件也一致。
- control/shadow 墙钟 `10.712171729/19.376483415 s`，开销 `+80.8829%`，RTF
  `0.205374/0.113540`，shadow 总 P95 `1532.999 ms`。阶段均值
  before/prepare/evaluate/after/assemble/log 为
  `224.461/345.095/195.421/207.312/0.00247/0.0973 ms`。最大载荷
  `11,275,939 bytes`，水位 `8/1024`；错误、禁止写入、D2/D3 消费和在线 truth 均为 0。
  业务非干预通过，但性能门和有效 treatment 门失败；manifest 为 dirty 开发口径。A2
  不准入，A3/A4 与 seeds 1101/1102 继续停止。

## 0.1 结构歧义 A1 原型状态（2026-07-23）

- 新设计文档为
  `research_modules/d1_sensor_fusion/docs/STRUCTURAL_AMBIGUITY_NEXT_CANDIDATE_DESIGN_CN.md`；
  A1 状态是 `IMPLEMENTED_UNIT_TESTED_OFFLINE_PROTOTYPE`，实现提交为 `de73cb2`。
- A1 是独立纯函数模块：规范滤波 state/covariance、历史、checkpoint 和 replay cache 不动；
  共同质心只在 detached 发布 DTO 上形成一次性 overlay；拒绝决策 overlays 为空，装配直接
  返回原规范业务序列。接受只复制 DTO，速度、相对位置、`global_track_id`、lineage/source
  support、identity、质量和 metadata 不变。
- 聚焦测试 `7 passed`，覆盖同步平衡 2/3/5 成员、拒绝透传、成员/观测/边/组件全排列、
  generation 幂等/倒退/摘要冲突、冲突组件、硬容量、非有限/身份输入和输入不变；D1 全量
  `294 passed`。
- A1 未接 `FusionAdapter.process()`/`process_scan_batch()`，没有修改 `fusion.py`；其
  experimental decision 不是当前在线 schema。main 已通过独立、默认关闭审计 shadow 接入
  A2，但性能门和有效 treatment 门均未通过，A3/A4 未实现。
- B 路线暂缓。当前 `Q(h)=G(h)qG(h)^T` 不满足单段/分段传播半群等价，插入零更新事件也会
  改变协方差分段。事件排序、过程噪声分段、NEES/NIS/RMSE oracle 未冻结前不得接在线路径。
- C 路线保留为主要系统研究方向：D1 只发布既有结构 evidence，D2 后续在有界窗口中规划概率
  或多假设消费。D1 不越界修改 D2，source key 不升级为 `global_track_id`。
- 双时间戳、平衡满基数 treatment 门、generation 有界幂等、lineage/source support、质量、
  identity 和无交叉协方差声明均不改变。seeds 1101/1102 继续停止。

## 0.2 身份中性共同质心候选状态（2026-07-23）

- D1 已实现默认关闭的
  `radar_assignment_ambiguity_neutral_centroid_correction=False`，要求结构歧义 hold 已启用，
  并与在线 truth hint 模式互斥。该路径只保留集合级共同状态信息，不提交成员身份。
- 候选只接受平衡满基数、free row/column 为 0、纯交替环、同 radar sensor/scan、双时间戳、
  NED、非过期、非 OOSM、无重复/冲突来源和无在线身份字段的分量。规模超过 `K_max`、质心
  马氏门或集合形状门失败时继续 prediction-only。
- 所有成员只增加同一有界位置平移。速度逐元素不变，成员相对位置不变；hit、观测历史、
  source support、identity likelihood、身份 freshness、质量分级、birth/delete 和
  `global_track_id` 均不改变。
- 位置边缘协方差只增加共同质心、形状失配和最小位置方差项。候选在整个分量上原子检查有限、
  对称半正定、非收缩、协方差上限和质量分级不变。成员交叉协方差未维护，继续标记
  `cross_covariance_available=false`。
- 新 generation 从该帧正式观测历史精确重放到发布时间，再只施加本帧一次共同修正。旧临时
  修正不进入下一帧基线；新帧校验失败时恢复 prediction-only 基线。正常身份明确量测接受后，
  标准重放替代临时修正，candidate 不重复计入 hit、lineage 或 source support。
- generation 注册按组件只保存最大已见代、最大已应用代和最近量测时刻，默认硬容量为 1024。
  fixed-lag 窗口内条目不淘汰；容量满时拒绝新组件；窗口外清理后旧证据仍因超窗拒绝。同代和
  倒退代拒绝且不改变当前状态。
- 审计输出请求/生效状态、参数、候选/成功/拒绝分量、成员数、重复/倒退 generation、水位表
  当前/峰值条目、淘汰、容量拒绝、线性操作数、最大质心 NIS/形状差/平移和拒绝原因。
- 结构歧义专项 `62 passed`，D1 全量 `282 passed in 17.81s`。修复前已用三帧测试复现固定
  创新下 `15 m -> 30 m` 的跨代累加，修复后三帧保持单帧修正；24 代同组件仅占一个水位条目。
  这是已实现模块候选和合同证据，不是系统效果结论。
- main 先在未提交工作树完成 seed 1100 dirty 诊断，随后在固定提交
  `7e15dac9cdaf6743999dfe045a70676fd31a17d6` 完成 clean 同输入复跑。两臂均为
  `repository_dirty=false`、200v200、2.2 s、`recon_count=2`、配置哈希
  `20ef5248...b840`。场景文件、离线真值及 89 批传感器主题一致，传感器主题 SHA-256 均为
  `bc064834...51518`，D2 在线记录 SHA-256 均为 `da7089fa...f8d2f`。
- 两臂 D1/D2/D3 都是 `202/201/186`，strict IDSW 都是 3，track/coverage continuity
  都是 `0.8266666667/0.8283333333`。可用/不可用/未承诺映射均为 `1491/218/76`，
  commitment coverage 均为 `0.9574706212`；重复分配、在线 truth 使用和未承诺来源/候选
  绑定违规均为 0。D3 安全门拒绝 11 个目标；main 在一次 hold 事件中累计撤回或清除
  13 条运行时绑定，两者统计口径不同。
- candidate 检查 46 个组件，实际施加 0 个，拒绝
  `oosm_scan=30`、`unbalanced_component=16`；generation 水位当前/峰值为 `8/8`，
  淘汰/容量拒绝为 0，finite=true。早期 `/tmp/MSM-neutral-centroid-gate-20260723` 保留为
  dirty 开发诊断；clean 制品为
  `/tmp/MSM-identity-gate-results-7e15dac/{hold_only,hold_plus_centroid}`。
- clean 复跑确认 D3 未承诺执行路径已 fail closed，但候选仍为零 treatment。该证据不能证明
  共同质心有效，也没有恢复 hold 的可用性退化。seeds 1101/1102 停止，默认关闭，P1 开放。
- D1 随后复用 governed replay、`SensorScanFrame`、`ScanInputOrganizer` 和在线批融合入口，
  完成三类冻结扫描边界诊断。控制臂和候选臂按扫描编号、双时间戳和观测数确认消费同一输入。
  同步平衡纯交替环 `2x2` 分量形成一次模长 `15.000000 m` 的共同平移，速度、相对位置、
  hit、lineage、identity、`global_track_id` 不变，协方差差最小特征值为 `0.4797678`；
  乱序平衡分量以 `oosm_scan` 拒绝；成员/观测 `2/1`、free row/column `1/0` 的分量以
  `unbalanced_component` 拒绝。
- 两个拒绝场景均为 `applied_component_count=0`，共同质心 correction 未施加；候选臂仍在
  拒绝后各执行一次 publication-base replay + replace 清除旧临时修正。当前离散 CV 过程
  噪声在控制臂分段预测与候选臂单段历史重放间不满足半群等价，候选减控制协方差差最小特征值
  分别为 `-0.0071928353214153066`、`-0.004617076466238031`。差值已 bitwise 归因到
  replacement，只作诊断，不能声称拒绝路径对状态和协方差严格无副作用；两项均为
  `candidate_not_promoted`。
- 冻结诊断专项 `5 passed`，D1 全量 `287 passed in 18.03s`，结果位于
  `research_modules/d1_sensor_fusion/reports/structural_ambiguity_centroid_replay_20260723/`。
  该证据关闭受控输入的“有效施加窗口是否存在”子项，不证明真实匿名输入收益，不改变默认关闭
  和停止 seeds 1101/1102 的决定。
- main 已完成 seed 1100 baseline/source-only/hold 闭环三臂。D1/D2/D3 分别为
  `202/203/200`、`202/201/198`、`202/201/186`；IDSW `9/7/3`；track continuity
  `.865/.865/.826667`；coverage `.870/.868889/.828333`。hold 有 76 条未承诺记录，D3
  拒绝 11 个目标，未承诺绑定违规为 0。
- source-only 终态映射 200 个真实目标并有 1 条未映射航迹；hold 映射 191 个真实目标并有
  10 条未映射航迹。首个计划后控制反馈使传感器流分叉，因此该结果是单 seed 闭环系统效果
  对照，不是完全冻结输入的上游因果证明。
- 下一步不直接恢复现有 replay/replace 候选的系统 A/B。A1 纯函数原型和 D1 准备对象优化已
  完成；main 的 A2 默认关闭审计 shadow 已使用新接口复跑，业务非干预通过，但性能门和有效
  treatment 门失败。当前按停止条件不进入 A3 新匿名 treatment 发现和 A4 预注册确认。
  不得通过忽略 OOSM 或放宽数量门制造 treatment；seeds 1101/1102 继续停止。

## 0.3 结构歧义侧车基础阶段状态（2026-07-23）

- D1 已实现默认关闭的第三条候选
  `prediction_only_maximum_matching_component_evidence_v3`。新开关
  `radar_assignment_ambiguity_hold_evidence=False` 与 v1/v2 互斥；关闭时结果和序列化保持
  基线。候选复用 v2 最大匹配允许边图，不再把整个分量计入旧 suppression。
- 歧义分量内不提交 observation-to-track 身份，不增加 hit，不做量测更新或 birth，也不把
  observation lineage 写入任一单航迹。成员继续 prediction-only；边缘 covariance 不收缩，
  `cross_covariance_available=false`。
- 公开侧车 schema 为 `d1.structural-ambiguity-evidence.v1`。它保存 publisher node/epoch、
  双时间戳、NED 成员状态和协方差、观测位置和协方差、候选边 NIS/门限、分量结构、匹配基数及
  固定 update/birth 状态。DTO 精确拒绝额外 truth/actor/target identity 字段。
- 默认发布者为 `D1_FUSION`，epoch 为 `d1-default-epoch-v1`。成员 token 由
  publisher node、epoch 和 D1 local track id 做 SHA-256；D2 source key 为
  `publisher_node_id::publisher_epoch::opaque_member_track_token`。该键可与 D1 snapshot
  一一对应，但不声明为 D2 canonical `global_track_id`。正式 episode 需由 main 注入可审计
  epoch。
- main 复核的两项审计语义已修正并加入断言。`structural_ambiguity_deferred_birth_count`
  只累计 free-column observation，`2x2/3x2/2x3` 分别为 `0/0/1`。candidate edge 只保留
  自身角色：reference matched edge 为
  `maximum_matching_allowed + matched_reference`，替代边才携带实际成立的 cycle/free-row/
  free-column 标签；component kinds 不复制给每条边。
- observation evidence key 已与通用 source lineage 解耦，只由数值量测证据和双时间戳生成。
  修改 observation 名称或 truth/actor/D6 离线元数据不会改变参考匹配或完整侧车。
- 该基础阶段专项 `25 passed`，当时 D1 全量 `245 passed in 17.48s`，语法检查通过。该证据确认默认关闭
  兼容、排列稳定、名称/离线 identity metadata 不变、lineage/identity 隔离、双时间戳、
  协方差和 DTO roundtrip；并确认 source-only 只增加发布来源字段，不改变状态、协方差、
  hit/birth、关联计数或 OOSM 重放。不单独确认系统收益。
- D1 已增加 `publish_opaque_source_key=False` 独立控制臂。hold 关闭、source key 开启时不
  生成结构歧义 evidence 或 prediction-only；hold 开启时继续逐字段发布原有来源合同。
  association audit 记录 requested/effective/mode 和 publisher 配置。main 后续闭环三臂
  结果及输入分叉限制见第 0 节；冻结输入因果分离仍未完成。
- 首次 A/B 后，main 已在固定提交 `ff88131` 完成身份指标可评估的最终干净复核。场景仍为
  `nominal_200v200`、seed 1100、2.2 s、`recon_count=2`，候选仅显式增加
  `--d1-d2-structural-ambiguity-hold`，在线 truth use 保持 0。

| 指标 | baseline | 候选 |
| --- | ---: | ---: |
| D1 tracks | 202 | 202 |
| D1 evidence received / consumed | 0 / 0 | 46 / 46 |
| D2 prevented hit / miss / birth | 0 / 0 / 0 | 69 / 69 / 4 |
| D2 tracks | 203 | 201 |
| D3 assignments | 200 | 197 |
| strict ID switch | 9 | 3 |
| track / coverage continuity | 0.865 / 0.870 | 0.826667 / 0.828333 |
| available / partial unavailable mappings | 1,566 / 234 | 1,491 / 296 |
| identity commitment coverage | 1.000000 | 0.957471 |
| 实时倍率 | 0.220352 | 0.207642 |

- D1 对冻结在线记录重放 89 个发布批次，逐批 observation、accepted、update、birth 和
  track count 与候选一致。46 个分量阻断 77 条观测并产生 91 次成员 prediction-only。
  76 次参考更新中，离线 truth 审计判定 69 次正确、7 次错误；另有一个真实目标 birth 延迟
  0.2 s。四次 D2 prevented birth 都来自 `TGT-0171` 的两条重复 D1 航迹，不是四个目标损失。
- strict ID switch 的改善已经成立，但连续性、D2/D3 数量、映射可用性及运行倍率均未达到
  晋级条件。最可能的 D1 根因是整分量 prediction-only 同时冻结正确和错误边。候选保持默认
  关闭。身份不提交、置换不变共同平移且协方差不收缩的新候选已完成 D1-owned 模块实现，
  当前接线和晋级状态见第 0 节。

- Radar-only 开发专项已把 seed 1000/1002 定位为 scan Hungarian
  swap/保持/swap-back；零延迟对照排除 OOSM，20:1 likelihood margin 也已证明不能在 coast
  后建立身份确定性。开发冻结回放只用于复现根因和验证候选机制。
- main 对 baseline `488dc39` 与 v1 candidate `d967c96` 运行了同配置 A/B：200v200、
  2.2 s、`recon_count=2`、seeds 1000/1001/1002；逐 seed 配置哈希在两端相同。

| Seed | ambiguous | strict identity | D1 | D2 | D3 | suppression |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| 1000 | `2 -> 0` | unavailable -> available；候选 IDSW `3`、continuity `.8600` | `203 -> 203` | `201 -> 200` | `200 -> 198` | `22/1962 = 1.12%` |
| 1001 | `0 -> 0` | available 保持；IDSW `9 -> 7`、continuity `.869444 -> .814444` | `201 -> 201` | `202 -> 194` | `200 -> 190` | `130/1966 = 6.61%` |
| 1002 | `2 -> 0` | unavailable -> available；候选 IDSW `4`、continuity `.8350` | `201 -> 201` | `200 -> 197` | `200 -> 193` | `78/1958 = 3.98%` |

- strict availability 从 `1/3` 提升到 `3/3`，但 D2 航迹和 D3 分配明显下降，seed1001
  continuity 下降约 `0.055`，信息抑制率为 `1.12%/6.61%/3.98%`。三组 finite=true、
  `repository_dirty=false`、online truth=0、missing identity evidence=0，
  target/known-false-alarm 标签数相同。因此 v1 不晋级。
- 早先 `/tmp/msm-clean-radar-d967c96` 遗漏 `--recon-count 2`，实际是 `recon_count=8`
  stress，配置哈希 `cc6/cbb/9f45`，不能与 recon=2 baseline 比较。该 stress 中 seed1001 的
  `GT3D-000210` 不是 D1 birth，而是 D1 既有 `global_track_187` 接受 scan 8 错误 radar update
  后由 D2 在末帧重建。scan 8 的 `200x199` 门内图有 209 条合法边、
  198 个匹配、2 个 free row 和 1 个 free column；当前边代价 `0.80058`，同 observation 对
  free row 的代价 `1.58216`，存在等基数 free-row alternating path。v1 的已匹配行 SCC
  无法检测该路径。
- 同一 recon=8 stress seed1001 的 1,966 条 radar 原始量测均为三维
  range/azimuth/elevation 和 `3x3`
  covariance。零 radial velocity 由 D1 标为未观测 placeholder，不能用于候选缩图。
- 生产默认已恢复基线 Hungarian。严格布尔参数
  `radar_assignment_ambiguity_governance=False` 时不运行 v1；仅显式 True 才运行
  `fail_closed_gate_feasible_alternating_cycle_v1`。审计输出 enabled、policy version 和
  `disabled/experimental_enabled` 状态。
- 默认关闭提交 `8f17c5d` 按 recon=2 同配置重跑后，三 seed 全部业务指标恢复 baseline。
  main 跨构建审计 `3/3 passed=True` 且 `normalized_online_payloads_equal=True`，输出位于
  `/tmp/msm-default-off-cross-build-8f17c5d-r2`；这证明回退无业务回归，不证明 v1 可晋级。
- D1 已实现默认关闭的
  `fail_closed_maximum_matching_allowed_edge_component_v2`。它从最大匹配构造交替有向图，
  以强连通分量、free-row 正向可达和 free-column 反向可达识别所有可进入某个最大匹配的门内
  边。含替代边的允许边分量统一抑制 matched/unmatched observations、阻断 birth，并让相关
  tracks coast。
- v2 不解析 observation 名称，不读取 truth/actor/D6，不使用未观测零径向速度。SciPy 缺失时
  先以增广路径把 greedy 结果补成最大匹配。严格布尔开关
  `radar_assignment_ambiguity_governance_v2=False` 与 v1 互斥；显式启用时审计状态为
  `experimental_v2_enabled_rejected_candidate`，表示运行的是已被系统门槛拒绝、默认关闭的
  研究候选。
- 审计保留历史 `policy_version` 字段和值。新增 `selected_policy_version` 和
  `candidate_policy_versions`；两种开关均关闭时 selected 明确为 `None`。main 应以 selected、
  enabled 和 status 判定实际策略，不能把兼容字段的 v1 值解释为基线正在运行 v1。
- v1/v2 专项 `29 passed`，覆盖 `2x2` cycle、`3x2` free-row、`2x3` free-column、唯一匹配、
  门外 birth、首扫、greedy fallback、OOSM、双时间戳、协方差、ID 所有权和 200 稀疏图；
  D1 全量 `220 passed`。main 独立穷举 2,666 个小图 oracle 通过，scalable 模块
  `142 passed`。这组证据只确认允许边图论边界和模块合同。
- main 在 clean commit `c928727` 完成 v2 首个未见 seed 1100 A/B。两组均为 200v200、
  2.2 s、`recon_count=2`，同 commit、dirty=false、配置哈希 `20ef5248...b840`；runtime
  profile `b508f675...12a8 / 9680c45b...f9f4` 只差 v2 treatment。两组 finite、online
  truth=0，online/radar observations、target labels、known false alarms 均为
  `2035/1954/2352/90`。

| 指标 | baseline | v2 |
| --- | ---: | ---: |
| ambiguous mapping | 0 | 0 |
| D1 / D2 tracks | 202 / 203 | 202 / 199 |
| D3 assignments | 200 | 196 |
| ID switch | 9 | 9 |
| track / coverage continuity | .865 / .870 | .830 / .835 |
| available / unavailable mappings | 1,566 / 230 | 1,503 / 266 |

- v2 suppression 为 `77/1954=3.94%`，发生于 9 个 ambiguity scans，track coast=91。身份
  指标没有收益，下游航迹、分配、连续性和映射可用性下降。整 allowed-edge 分量 fail-closed
  抑制过保守；图论边界正确不能推出当前 intervention 合适。
- 评审结论：v1 和 v2 系统候选均不晋级，v2 保持默认关闭，P1 blocker 开放。预注册停止条件已
  触发，不运行 seeds 1101/1102、10 s 或 20-seed。后续候选可复用允许边识别，但必须重新设计
  信息保留策略并从新的未见 seed 验收。

- D2 nominal 200v200 身份阻断审计在 seed 1000 给出 17 条可复核的雷达/视觉混轨观测。D1 在
  clean `5263e2b` 的 771 scans/11,889 anonymous observations 冻结回放中复现。
- 根因是扫描帧冻结后的嵌套相机模型为只读 `Mapping`，旧解析器只接受普通 `dict`。相机位置
  仍保留，旋转和内参退回默认值，导致错误投影进入原创新门与匈牙利分配。
- 当前修复接受冻结 mapping 和现有相机字段，校验内外参，并拒绝非法几何、相机后方点和非有限
  投影。门限、6 s fixed-lag、观测频率、协方差治理和 EKF 公式不变。
- 17/17 已知污染视觉观测离开原错误航迹并进入离线标签单一谱系；离线标签只在回放完成后评分。
  在线 truth、Actor/Object 名称、真值距离和 D6 结果使用均为 0。
- 终态航迹 `201 -> 202`，额外出生由 `radar-s000030-d0116` 形成。规范状态/谱系摘要变化有
  明确的投影、后验和后续雷达关联因果，不属于非确定性 ID 变化。
- 评审结论：已复现的 D1 解析缺陷关闭；nominal 20-seed 候选复跑、D2 118 个历史多真值帧和
  严格身份可用性继续为 P1。D1 全量 `191 passed in 16.88s`。

- clean `5263e2b` nominal 200v200、10 s、seed 1000 冻结输入含 771 scans、
  11,889 observations，源 SHA-256 为 `5d033a04...67ce8f`。原 clean 20-seed 基线的
  scan-input/fusion 累计均值为 `9.671/43.774 s`，episode P95 均值为
  `135.454/233.488 ms`，两项仍约占核心 wall 的 62%。
- 本轮关闭 `_claim_for_frame()` 对同一量测、协方差、元数据和谱系的重复 JSON 安全转换。
  新路径只物化一次规范内容记录，继续使用原 SHA-256 字节格式、键排序、内容排除字段和
  `allow_nan=False`。claim registry 与重复、重放、冲突拒绝规则没有变化。
- 旧/新完整流水的 claim registry、逐输入事件、发布顺序、逐 fusion
  状态/协方差/双时间戳/谱系/分级、操作计数、累计诊断、终态和一致性证据均严格一致。
  771 scans 交错 5 轮 P50/P95 `3.618/4.049 -> 1.905/2.038 s`，P50 1.899x；
  `_json_safe` cProfile `5.781 -> 1.992 s`。墙钟不参与等价通过判定。
- 评审结论：scan-input claim 重复规范化从 P1 实现缺口转为持续回归项。候选尚未完成 clean
  多 seed 全栈重跑；冻结 fusion 仍约 43.148 s，GlobalTrack 物化、非雷达扫描关联、
  fixed-lag replay、正式效果指标和系统实时继续为 P1。D1 全量回归为
  `185 passed in 19.69s`。

- clean `4ac3bb2` nominal 200v200、10 s、seed 1000 冻结输入含 771 scans、11,889 anonymous
  observations，源 SHA-256 为 `c1dda852...66f77a`。当前未提交 D1 工作区复放不使用在线
  truth，也没有改变固定滞后窗口、观测保留、扫描频率或门控。
- profiler 将 scan-input 尾部归因到 organizer 对已验证 `SensorScanFrame` 的二次深快照。
  完整帧复用后，帧重建 `771 -> 0`、observation 再快照 `11,889 -> 0`；
  `ScanInputOrganizer.ingest` cProfile 累计 `15.545 -> 5.754 s`。
- 前 256 scans 交错 5 轮 P50/P95 为
  `1.942/1.968 -> 0.881/0.894 s`，P50 比 2.204x，墙钟不参与验收。逐输入/audit/release、
  逐 fusion posterior/物化航迹、终态/一致性证据、逐 fusion 操作数和累计诊断严格一致；
  operation/diagnostic snapshot hashes 分别为 `82728a8e...bfb5bf` /
  `b28df84d...521766`。
- fusion 数学路径未改。cProfile 累计主要为 `global_tracks 17.559 s`、扫描关联
  `17.027 s`、`_to_global_track 16.930 s`、非雷达代价矩阵 `14.971 s` 和 replay
  `8.601 s`；峰值扫描有 40,000 candidate pairs，fixed-lag rebase 峰值 197。
- 评审结论：该阶段只关闭重复深快照；后续 claim 重复 JSON 规范化已由本节最新增量关闭。
  clean 多 seed 候选复跑、fusion 尾延时、非 claim audit/event、GlobalTrack 物化及
  radar/rebase 继续为 P1。本轮是当前
  工作区的单 seed 三维质点 replay，不是 AirSim、正式矩阵或实时放行。
- main 实测当前 D1 全量回归为 `185 passed`；这是当前工作区权威测试计数。

- main 已完成 detached clean `4ac3bb2c12cc6af6ebd372107ced00bcdc5adf6a` 的
  `200v200-nominal-v1`、10 s、seed 1000 全栈校准，并与 clean
  `0d2da25c14e50f8f9a10ad47a7bd74e5c5e577fb` 同 seed 对照。两端各有 771 个 D1 扫描、
  11,889 条匿名在线观测；候选状态有限，在线 truth 使用为 0。
- 核心 wall `94.104939744 -> 85.002427712 s`，下降 9.6727%、加速 1.1071x；D1 fusion
  `49.697406826 -> 40.272795088 s`，下降 18.9640%、加速 1.2340x；scan input
  `12.315225105 -> 12.560936034 s`，增加 1.9952%。候选核心 RTF 为 `0.1176437`。
- 候选 771 次 fusion 调用的 P50/P95/max 为
  `33.25249/224.76351/592.95713 ms`。规范在线载荷、离线 truth state、计划谱系模式和两端
  谱系有效性跨构建检查全部通过。
- 外部总进程 elapsed `1:55.95`、峰值 RSS `2,468,928 KiB` 包含启动、离线后处理和落盘，
  与 85.002427712 s 核心 wall 分属不同口径，不能混写。
- 评审结论：本批仅为单 seed 描述性 clean 校准，不是 20-seed 或正式矩阵，且未实时。
  D1 fusion P95/max 尾延时和 scan-input 继续为 P1；本批不增加 AirSim 或正式精度结论。

- 当前最新 D1-owned 优化处理非雷达扫描的逐候选伪逆。未见 seed 1000 的完整冻结输入含
  771 个扫描、11,889 条匿名观测和 201 条终态航迹。旧 cProfile 中非雷达代价矩阵累计
  34.307 s，496,625 次 `pinv` 累计 14.837 s。
- 新路径按严格量测几何和矩阵形状把创新协方差组成矩阵栈。观测协方差、航迹状态、残差、
  马氏二次型、门限和 Hungarian 分配仍逐候选保真；批处理异常回退旧路径。双时间戳、NED、
  固定滞后、后验 generation、在线 truth 隔离和规范 `global_track_id` 所有权不变。
- 前 256 个扫描/4,087 条观测在同进程预热后交错 7 次，逐候选/批处理 P50
  `12.242/10.238 s`、P95 `13.340/11.248 s`。完整 771 扫描墙钟
  `50.458/39.994 s`；三类语义哈希、操作计数和累计诊断相同。`pinv` 调用
  `496,625 -> 1,018`。该 2026-07-22 非雷达专项当次历史回归为
  `182 passed in 15.92s`，不是当前权威计数。
- 本项关闭 D1 非雷达逐候选伪逆热点。main 尚未在候选上复跑 20-seed 全栈，因此实时倍率、
  RSS、航迹物化、scan input、AirSim 和正式精度继续作为 P1，不从模块基准外推。

- D1 已完成已缓存一致性证据计数刷新优化。旧路径对未变化证据使用
  `dataclasses.replace()` 重跑完整构造校验；新路径只从已验证冻结记录复制不可变字段，并校验
  新的非负 `replay_revision/replay_count`。新证据、真实更新、重复、OOSM 和 unavailable 仍完整
  校验。
- clean `f80b5bd` 10 s seeds 42000-42002 的完整重验/受限复制纯融合均值为
  `64.844/52.657 s`，3/3 更快，加速 `1.231x`。逐扫描状态、协方差、双时间戳、来源谱系、
  航迹分级、终态航迹、逐观测一致性证据和全部操作计数严格一致，在线 truth 使用 0。
- 代表 seed 的一致性刷新累计 `27.122 -> 1.664 s`，`_replay_record`
  `35.348 -> 9.410 s`。D1 全量 `178 passed in 14.80s`。本项 D1-owned 热点关闭；其后
  非雷达逐候选伪逆也已关闭，当前剩余主导项为航迹物化和 scan input，系统实时与长时超线性
  P1 保持开放。

- main 已完成 clean `8f86192 -> f80b5bd` 的最终 integrated 三 seed 跨提交复核。10 s、
  200v200 nominal seeds 42000-42002 均 finite、在线 truth 0，D1 终态航迹数逐例保持
  `202/207/203`。
- D1 fusion 三 seed 累计耗时均值 `92.991088 -> 88.330438 s`，约下降 5.01%；scan input
  `16.902643 -> 17.524242 s`，约增加 3.68%；精确创新求解总计
  `7,130,228 -> 1,578,677`，约下降 77.86%。求解次数仅为性能诊断。
- 三 seed 逐条在线业务语义审计全部通过。只按规划 occurrence/version 归一化 D3 opaque
  `plan_id`，ACK 原始载荷 SHA 在归一化前校验；owner/version/coalition/`global_track_id`/command
  等业务字段仍参与比较。该结果不关闭系统实时或长时归一化超线性 P1。

- D1 已完成同一 fusion timestamp 内的延迟物化接口。`process_scan_batch()` 默认完整返回不变；显式
  state-only 仍完成扫描关联、fixed-lag/OOSM、双时间戳、covariance、门控、health、consistency
  evidence、lineage 和累计诊断，只不构造中间 `GlobalTrack`。
- `FusionStateUpdateResult` 提供 `tracks_materialized=false`、准确 `current_track_count`、
  `track_count=0` 和空 `tracks` 数组；直接访问 `tracks` 抛错。末尾
  `materialize_global_tracks()` 返回完整 `FusionTrackSnapshot`，其中 `track_count` 与
  `current_track_count` 相等。
- 三目标四扫描回归覆盖默认 6 s fixed-lag 和检查点前 OOSM。逐扫描完整发布与中间 state-only、
  末尾一次物化的终态航迹、协方差、元数据、时延、健康和 consistency evidence 相同；物化数
  `12 -> 3`。定向 `30 passed`，D1 全量 `168 passed in 29.43s`。
- publication audit 已升级为 v2，区分总发布、完整快照、state-only 和完整航迹记录数。旧 v1
  日志继续按完整快照处理；state-only 的 `track_count=0` 不代表当前总航迹数，当前数量只读取
  `current_track_count`。main 已在 clean `8f86192` 三 seed 质点全栈接线；AirSim 和实时预算仍开放。
- 10 s seeds 42000-42002 的 state-only/完整快照分别为 `310/454`、`328/516`、`278/504`，
  逐例合计全部 `764/844/782` 个扫描。事件、scan input、共享摘要和世界真值与旧 clean
  `3bac3ff` 相同。
- D1 fusion 三 seed 均值 `103.339 -> 92.991 s`，下降 10.0%；2.2 s seed 42000 全栈墙钟
  `18.611 -> 18.302 s`。3/3 clean、finite、在线 truth 0，D1/D2 overflow 和安全合同均通过；
  该结果不关闭实时、AirSim 或正式精度。

- 长时专项使用 10 s 冻结输入，包含 764 个扫描、12,107 条匿名观测和 202 条终态航迹；重排
  49 次，峰值缓冲 64 个扫描/825 条观测，在线 truth 使用为 0。
- 完整检查点二分查询、固定滞后后缀复用、可信前缀快路径和缓存一致性证据刷新已进入默认路径。
  6 s fixed-lag、观测数量/顺序、双时间戳、covariance、关联/创新 gate 和 `GlobalTrack` 未改变。
- 旧路径与优化路径逐扫描、终态和 consistency evidence 哈希一致；history replay
  `170,106 -> 13,397`，filter update `120,440 -> 9,549`，墙钟
  `157.237 s -> 107.449 s`，本机单次 1.463 倍。
- `fusion_performance_diagnostics()` 已提供固定大小的 episode 累计计数，包括 filter update、
  checkpoint reuse、状态查询、重基和物化次数。当前优化路径的状态查询、固定滞后后缀复用、
  合法前缀快路径和缓存一致性刷新计数分别为 152,861、110,891、300,024 和 194,916。main
  final diagnostics 已采样固定大小的 D1 fusion performance 快照，不保存逐扫描历史。
- 764 条 D1 全量快照约 186.2 MiB，其中 357 条同融合时刻可合并，294 条连续未变化。这是延迟
  物化接口前的历史基线；D1 已实现同一 fusion timestamp 末尾快照能力，main 已完成质点全栈
  接线。跨 tick 合并仍是
  main 调度建议。
- D1-owned 长时重复计算和 main 质点接线缺口据此关闭。更多长时 seed、系统 P95/实时倍率、
  跨 tick 发布节流、AirSim 和正式 RMSE/NEES/NIS 仍是独立 P1 验收项。

- 第二阶段以 clean `492979e` 的 200 规模五 seed 为起点；第一阶段默认路径 D1 fusion 分别为
  10.096、13.693、12.895、11.973、11.856 s，均值 12.103 s。冻结 seed 42000 输入的
  SHA-256 为 `bc539686b130d96c63b76b9161fadbae2dba59de44cb61ac80d92f2ea1018406`。
- 当前默认关联路径为非雷达扫描建立工作区：量测模型按观测构造，航迹状态按共同量测时刻取得，
  仅在传感器位置、相机位置、旋转和内参完全一致时复用预测量测与数值雅可比。残差、创新协方差、
  伪逆、门控及 Hungarian 一对一分配仍逐候选对执行。
- current-default 与优化路径的 86 个逐扫描语义哈希、最终 201 条航迹和 consistency evidence
  哈希一致。candidate pair/innovation solve 均为 371,054；model build `16,457 -> 82`，
  projection build `16,457 -> 14,648`，`GlobalTrack` 物化保持 16,653。
- 模块级墙钟 `10.792 s -> 8.635 s`，本机单次 1.25 倍；专项 `10 passed in 10.33s`，D1
  全量 `161 passed in 38.02s`。墙钟只作说明，正式验收使用语义哈希和操作计数。
- 第二阶段没有丢弃观测、缩短 fixed-lag、压低 covariance、放宽 gate、使用 truth 或降低发布
  内容。后续 clean 三 seed 全栈已经复跑；系统 P95、AirSim 和完整 200v200 实时性仍开放。

- D1 已在冻结的 seed 42000/200v200 输入上完成函数级 profiler。未缓存路径的主要热点为
  `_state_at` 38.120 s、`_replay_record` 46.097 s、`_filter_update` 37.615 s/93,234 次，以及
  每航迹重复生成 sensor-health 快照 16,653 次。
- 当前实现为每航迹增量后验检查点。顺序扫描复用缓存；窗口内 OOSM 只失效插入点后的后缀；
  固定滞后重基、起始观测变化和检查点前 OOSM 触发完整相关失效。缓存命中仍重建 consistency
  evidence revision，不改变扫描级一对一关联。
- 每扫描公共构造 association、latency 和 sensor-health 发布快照，所有 `GlobalTrack` 继续携带
  完整审计字段。发布 state/covariance 已与内部后验数组解耦。
- 相同 86 个扫描/2,051 条观测上，逐扫描语义、最终 201 条航迹和 consistency evidence 哈希
  均与未缓存参考一致。filter update `93,234 -> 1,797`，health snapshot `16,653 -> 86`；
  34.701 s -> 9.073 s，本机单次 3.82 倍。D1-owned 冻结输入热点据此关闭。

- main 已从 clean 提交 `e4d66db02a0b8f1b867a0e81b4a73de84588426b` 完成 D1 扫描输入
  治理正式复跑。20/50/100/200 各 5 个互异 seed，共 20/20 formal episode；每例
  136 帧/33.75 s，D1 重排 12、拒绝/过旧/溢出 0、峰值/结束缓冲 3/0，在线 truth 使用 0。
- 20/20 manifest 均为 `repository_dirty=false`、`evidence_tier=formal`。200 规模峰值内存均值
  约 40.91 MB，最大 40,926,870 B；输入文件和 60 个引用制品 SHA-256 全部匹配。
- 该快速治理层仍显式标记 `full_system_evidence=false`，且未导入完整运行时模块。它关闭 clean/
  formal 治理复跑缺口，不运行完整 EKF/fixed-lag 融合，不能说明定位精度或实时性。
- 单次 200v200 三维质点全栈 smoke 使用 seed 42000、2.2 s。D1 处理 86 个扫描/2,051 条观测，
  重排 10、拒绝 0，峰值缓冲 33 个扫描/623 条观测；fusion 累计 35.115 s，平均 408.313 ms，
  扫描输入累计 2.682 s。全栈墙钟 60.210 s，实时倍率 0.037；该批仍是 dirty development。
- clean `8f86192` 已补充三 seed 完整全栈验收，D1 fusion 均值下降 10.0%，但处理 10 s 输入仍需
  92.991 s。剩余性能 P1 是冻结硬件、发布频率、场景配置和周期预算，扩展时长/seed 并记录
  P50/P95/max、长历史峰值内存与端到端实时倍率；不得把 D1-only 3.82 倍或本次 10.0% 写成实时。
- 两批均未启动 AirSim，也没有正式多 seed RMSE、NEES、NIS coverage 或 200v200 任务效果。
  D1 当前无新增 P0 blocker；clean 治理、D1-owned 冻结输入热点和三 seed 质点接线已关闭，
  更多长时 seed、固定硬件配置和预注册周期预算仍开放。

## 0.3 历史 D1-owned 状态（2026-07-16）

- D1 已实现 `sensor_observation_from_local_image_track()`：只把 `measured` 本地图像航迹转换为
  EO/pixel `SensorObservation`；`lost` 返回 `None`，不复用旧 center/bbox/covariance。
- 适配边界保真双时间戳、2×2 pixel covariance、confidence、quality flags 和 visible/
  infrared 波段；缺失、非法或非半正定 covariance 以及 global/truth identity 均 fail closed。
- sensor/stream/local epoch/local ID 组成 namespaced `source_track_key`。它与量测时刻共同形成
  可去重 lineage；被接受视觉来源仅累积到 `GlobalTrack.metadata.source_track_ids`，绝不作为
  `global_track_id`。
- 2026-07-16 构造合同场景无随机 seed；专项 `13/13`、D1 全量 `111/111`。验收阈值为合法
  字段逐项保真、非法 covariance/identity 100% 拒绝、lost 0 输出、来源累积且 global ID
  不变。本轮未运行 AirSim，不提供新的 RMSE/NIS/NEES 或 runtime timing 结论。
- main 后续负责把真实 producer 接到该 API，并验证 backend/batch audit、相机模型和重复投递
  行为；D1 的适配器完成不等价于跨模块运行时接线已完成。

### 0.2 历史系统状态（2026-07-15）

本节覆盖后文按日期保留的历史阶段结论；历史内容用于说明实现演进，不代表当前 GAP 状态。

- main 已完成真实 AirSim M5N2 baseline 10 case 与 candidate 10 case，共 20 case。在线
  identity/state truth use 均为 0，既有 truth 隔离 P0 保持通过。
- 20 case 共记录 3,805 个 main-bus tick。D1 fusion mean/P95/max 为
  `320.00/451.46/1234.88 ms`，是 main-bus 内层主导阶段；main-bus 整体 mean/P95/max 为
  `349.34/487.40/1305.99 ms`。100 ms 预算仍是开放 P1。
- 双时间戳、观测/航迹 covariance、NED 与 source lineage 继续作为硬合同。此前 D1-only
  batch replay 等价性成立，但不能据此声称真实 AirSim 循环已达标。
- 本批面向终端闭环和时序，不提供可用 NIS、NEES 或 RMSE，不能关闭真实 sensor-specific
  covariance、滤波一致性和定位精度标定。
- M5N2 20/20 后已停止；TERM 前额外完成 1 个 `png_ttc_2v2_seed001`，明确排除；dropout
  完成数为 0。
- 当前计划优先级为：先在冻结输入下定位 D1 fusion 的 fixed-lag/batch/history 成本并由 main
  复跑多 seed 预算，再单独建设带 availability 的 NIS/NEES/RMSE 标定；不得通过放宽时间或
  covariance 合同换性能。

### 0.3 历史 Dense Crossing 权威状态（2026-07-13）

- main 已完成 strict dense crossing 的真实 AirSim 采集：nominal 4 m 与 tight 2 m 各
  20 seeds，共 40 个 episode，每个 episode 51 帧、5 个目标。
- D1 governed replay 保留双时间戳、covariance、NED、source lineage、scenario/config
  version、seed、目标间距和 evidence path。evaluator-only truth sidecar 共 10,200 个样本，
  `online_truth_leak_count=0`。
- D6 统一证据报告将 `d1_dense_crossing` 标记为 `available`，并保留 schema、digest 和
  evidence path；缺失指标继续显式为 `unavailable`。
- D1 全量回归为 `79 passed`。当前无 D1 P0 blocker；governed replay、truth 隔离和证据可
  消费性不再作为未实现项。
- 仍开放的 P1 聚焦真实 radar/acoustic/EO 漏检、匿名虚警、部分/完全遮挡、异步采样率、
  sensor-specific latency/故障 fixture，以及区域时间窗、covariance growth、health、NIS/NEES
  和场景自适应 covariance 的长期治理。D1/D2-confirmed 协同融合和节点退出 replay 仍需实证。
- FilterPy、Stone Soup、OpenCV/GTSAM 和 ROS 2 `tf2`/`message_filters` 仍为 P2/P3 可选
  benchmark 或后续工程适配，不是当前已实现的在线能力，也不替换 NumPy EKF/fixed-lag 主线。

## 1. 研究问题

当前难点不是单个传感器能否发现目标，而是不同传感器的观测时间、坐标系、误差模型和语义不同：

- 雷达输出距离、方位、俯仰、径向速度或三维点迹，但存在扫描周期、链路延迟和距离相关误差。
- 声学输出粗方位、声纹或类别提示，定位精度受阵列孔径、风噪、混响和遮挡影响较大。
- 光电输出像素框、类别和置信度，本质上是图像平面约束，不能直接当作三维位置真值。
- 每类观测都有 `measurement_timestamp` 和 `arrival_timestamp`，融合必须按测量时刻处理，不能按到达时刻简单更新。

目标是把所有观测标准化为 `SensorObservation`，经过时间对齐、坐标转换、协方差建模和延迟补偿后，形成统一的 `GlobalTrack`。
运行时目标数量由 main 的 `--drone-count N` 统一控制；D1 接收 main 提供的 N 个 target truth/观测源，并按输入数组长度处理，不在算法路径写死 2 或 5。

---

## 2. 文献综述要点

2015-2026 年异构传感器融合的共识可以概括为四点。

第一，时间基准应以测量时刻为准。雷达扫描、光电曝光、声学采样和网络传输可能相差数十到数百毫秒。滤波更新使用 `measurement_timestamp`，`arrival_timestamp`只用于记录通信延迟、乱序检测和缓存管理。乱序观测通常按 OOSM 处理，可采用 fixed-lag buffer、重传播、平滑更新或信息滤波。

第二，融合状态应在局部米制坐标系中维护。WGS84 适合记录地理元数据，不适合直接线性滤波。推荐在局部 ENU/NED 中估计位置和速度，同时保留原始 `sensor_frame`、`body_frame`、`map_frame` 和外参版本。协方差转换使用近似雅可比：

```text
P_out = J * P_in * J^T + P_calib
```

第三，协方差必须随距离、遮挡、SNR 和杂波动态变化。雷达横向误差会随距离放大；声学 DOA 是粗方位，声纹只应作为身份似然；光电像素框在小目标、截断、遮挡和逆光时应显著放大测量协方差。

第四，融合系统不应把传感器检测直接升级为可处置目标。`GlobalTrack`只表达位置、速度、协方差、置信度和状态，授权逻辑由上层系统单独处理。

---

## 3. 开源代码选型

| 工具 | 用途 | 优点 | 限制 | 估算工作量 |
|------|------|------|------|------------|
| Stone Soup | 多目标跟踪、OOSM、轨迹融合、JPDA/MHT实验 | 组件化强，适合科研验证 | 需要封装ROS/仿真接口 | 5-10人日 |
| FilterPy | EKF/UKF/IMM原型 | 简洁，便于快速验证 | 不含完整航迹管理 | 3-6人日 |
| ROS 2 tf2 | 坐标树、外参、时间化变换 | 工程通用 | 不处理协方差建模 | 3-5人日 |
| message_filters | 多传感器时间同步 | 易集成 | 不能替代OOSM补偿 | 1-3人日 |

当前代码状态：D1 主线采用 NumPy EKF fallback，不依赖 Stone Soup、FilterPy、ROS 2 或 AirSim Python 包即可运行测试。Stone Soup 和 FilterPy 只保留占位/可用性探测边界；ROS 2 `tf2`、`message_filters` 是运行环境稳定后的 P2 后置选项。当前不应把这些开源库写成已接入能力。

---

## 4. 子系统方案

### 4.1 统一数据结构

```text
SensorObservation
- observation_id
- sensor_id
- modality: radar | acoustic | eo | lidar(optional dry-run)
- measurement_timestamp
- arrival_timestamp
- frame_id
- measurement
- covariance
- classification_hint
- confidence
- quality_flags

CanonicalDetection
- detection_id
- source_observation_id
- timestamp
- frame_id: ned | enu
- z
- R
- modality
- confidence

GlobalTrack
- global_track_id
- state: position + velocity
- covariance
- timestamp / valid_at
- measurement_timestamp
- arrival_timestamp / published_at
- track_level: coarse | stable | handover
- source_support
- identity_likelihood
```

### 4.2 融合链路

```text
SensorObservation
-> timestamp normalization
-> sensor_frame to body/map/NED
-> adaptive covariance model
-> OOSM delay compensation
-> track filter update
-> GlobalTrack publish
```

### 4.3 延迟补偿

如果观测到达时刻晚于测量时刻，不能直接用当前状态修正。推荐维护短时状态缓存：

```python
class DelayCompensator:
    def update(self, track, detection):
        if detection.timestamp < track.timestamp:
            past = self.rewind(track, detection.timestamp)
            past.correct(detection)
            return self.replay_to_now(past)

        track.predict_to(detection.timestamp)
        track.correct(detection)
        return track
```

### 4.4 协方差自适应

```text
radar_R = base_R(distance, snr, beam_width)
        + clutter_penalty
        + occlusion_penalty
        + timestamp_latency_penalty

acoustic_R = doa_uncertainty(array_aperture, snr, peak_width)
           + wind_noise_penalty
           + reverberation_penalty

eo_R = projection_uncertainty(bbox_size, detector_confidence)
     + truncation_penalty
     + calibration_penalty
```

---

## 5. 雷达定位误差分档规则

使用水平 95% 误差椭圆长轴作为统一质量指标：

```text
a95 = sqrt(chi2_2_0.95 * lambda_max(P_xy))
```

阈值由仿真或标定数据确定，设 `T_h < T_s < T_c`。

| 档位 | 判据 | 允许用途 |
|------|------|----------|
| `coarse` | `a95 > T_s` 或仅短时单源支持 | 告警、继续观测、请求补充传感器 |
| `stable` | 连续多帧 NIS 通过，`a95 <= T_s` | 进入中心关联和资源分配候选 |
| `handover` | `a95 <= T_h` 且多源一致 | 可交给末端配准或显示，不等价于处置授权 |

---

## 6. 与主动降级/D5/D7 的接口改进

本节补充 D1 在当前主线架构中的接口责任。D4 已引入主动降级，D5 需要多视角目标关联，D7 使用比例导引作为离线仿真中的中段导引模块。D1 不输出控制指令，也不参与处置决策，只输出带时间、坐标和不确定度的数据合同。

### 6.0 2026-07-07 P1 复核更新

main runtime bus 已把 D1-D7 DTO/summary/record 接入真实 AirSim episode 状态机，并将 D7 执行结果回灌到正式 episode metrics；D3 已补充中心重规划后的 plan owner/version；D4 已把主动降级硬风险与软质量风险拆分；D5 已修正终端一致性窗口。对 D1 的影响是接口语义收紧，而不是新增算法职责：

- D1 的 `TrackUncertaintySummary` 是 D3/D4/D5/D6 的质量证据，不是降级动作或授权状态。
- D1 的高协方差、低 freshness、source gap 或 handover readiness 下降，需要由 D4 结合 C2 health、D3 plan freshness、D5 terminal evidence 和持续窗口仲裁；不应由单帧软风险直接触发主动降级。
- D1 不生成 D3 `AssignmentPlan` 版本，不决定二级/分布式接管，也不修改 D7 PN/PNG 控制律。
- 严格 subagent 流程下，D1 owned README/PLAN/GAP/review 状态由 D1 子智能体自行维护和测试；main 只做集成汇总。

### 6.1 面向 D4 主动降级的不确定度信号

D4 的主动降级需要判断“中心节点仍在线，但中心态势质量不足”。当前 D1 已把单航迹质量指标随 `GlobalTrack.metadata` 或 `TrackUncertaintySummary` 输出给 D3/D4，并提供轻量 `FusionQualityRegionSummary` 按 `coverage_cell` 聚合区域质量；主动降级 hint 和最终降级仲裁仍不在 D1 当前实现内。

```text
TrackUncertaintySummary
- global_track_id
- measurement_timestamp
- arrival_timestamp
- valid_at
- published_at
- track_bucket
- track_level
- position_cov_trace
- velocity_cov_trace
- a95_xy_m
- latest_observation_latency_s
- measurement_age_s / observation_freshness_s
- source_support
- source_diversity_count
- last_nis
- handover_readiness
- quality_flags
```

主动降级候选条件：

- 雷达协方差迹或 `a95_xy_m` 短窗口内突增，说明中心定位分辨率下降。
- `latest_observation_latency_s` 或 `measurement_age_s` 超过 D3 分配周期，说明分配使用的是过期观测。
- `observation_freshness_s = published_at - latest_measurement_timestamp` 持续变大，说明航迹主要靠外推维持。
- `source_support` 从雷达+EO等多源退化为单源，或后续区域摘要显示关键区域出现 coverage gap。
- `handover` 不能稳定维持，频繁回退到 `stable/coarse`。
- 雷达与 EO 的 NIS 长时间偏高，说明多源观测不一致。

当前区域摘要只能作为质量证据。若后续需要 D1 给出显式质量建议，也只能是建议字段，例如：

```text
active_degrade_hint = none | regional_secondary_node | distributed_review
reason = high_covariance | stale_observation | sensor_gap | handover_unstable | sensor_disagreement
```

最终是否切换到二级节点或分布式协同，应由 D4 结合 `C2Health`、D3 分配版本、D5 末端反馈和人工授权状态决定。

### 6.2 对 D7 中段雷达比例导引的支撑

D7 的比例导引模块不应直接读取原始雷达点迹，而应使用 D1 发布的融合航迹。D1 需要保证 `GlobalTrack` 至少携带：

```text
position: [px, py, pz] in NED
velocity: [vx, vy, vz] in NED
covariance: 6x6 state covariance
measurement_timestamp: latest contributing measurement time
arrival_timestamp / published_at: fusion output arrival/publish time
track_level: coarse | stable | handover
source_support: radar/acoustic/eo/lidar support counts
```

工程规则：

- D7 只能把 `stable` 或 `handover` 作为中段仿真输入；`coarse` 应只用于继续观测或保持原计划。
- D7 应根据 `covariance` 和 `track_level` 决定是否扩大预测门限或保持保守状态。
- 若 `latest_observation_latency_s` 或 `measurement_age_s` 过大，D7 应使用 D1 的速度和协方差做外推，并把新鲜度不足反馈给 D4/D3。
- D1 不向 D7 提供真实飞控、硬件、毁伤或自动处置接口；这里只定义离线仿真的航迹状态输入。

### 6.3 对 D5 视觉交接与多视角关联的支撑

AirSim Blocks 运行时默认不再保留截图，只保留相机元数据、检测框和检测置信度。D1 的 EO 接口应适配这种模式：

- EO 输入使用 `bbox_xyxy`、`center_px`、`camera_id`、相机内参、相机外参和 `measurement_timestamp` 构造 `SensorObservation(modality="eo")`。
- D1 不依赖保存 PNG；图像文件不是融合合同的一部分。
- D1 只把位置航迹、速度、协方差和时间戳传给 D5，D5 再将 `GlobalTrack` 投影到对应相机平面做门控。
- 多视角同一目标关联时，D1 应保留 `sensor_id/camera_id`、`frame_id`、外参版本和 `source_support`，便于 D5 判断不同视场观测是否支持同一 `global_track_id`。
- 如果相机检测框很小、截断、遮挡或置信度低，D1 应放大 EO 测量协方差，避免单次视觉框强行拉偏全局航迹。

D5 的末端关联结果可作为 D1/D4 的反馈信号，但不得由 D5 本地直接改写 D1 的 `global_track_id`。

### 6.4 工程改进记录（含 2026-07-10 历史基线）

已完成：

1. **最新量测时间显式化**：`GlobalTrack.metadata` 已记录 `latest_measurement_timestamp`、`latest_arrival_timestamp` 和 `latest_observation_latency_s`；`TrackUncertaintySummary` 已导出 `measurement_timestamp`、`arrival_timestamp`、`valid_at` 和 `published_at`。
2. **距离相关协方差参数化**：`RadarCovarianceConfig` 已支持 range/angle/radial velocity 噪声随距离增长的参数配置，默认参数保持现有测试行为。
3. **声学弱约束边界**：当前代码只允许 radar 初始化新航迹；声学作为方位/类别弱约束参与更新，不会单独生成三维 `GlobalTrack`。
4. **EO 无截图合同**：D1 EO 观测只需要 bbox、中心像素、相机元数据、时间戳和协方差；dry-run 与 JSONL replay 测试不依赖 PNG。
5. **source lineage 去重**：相同 source/sequence/payload 经 relay 重复投递时不会重复更新航迹，`duplicate_observation_count` 会进入 metadata。
6. **replay schema v1/legacy 兼容**：`sensor_observations.jsonl` 使用 `d1.sensor_observation.v1`，既有无版本 `blocks_sensor_observations.jsonl` 作为 legacy 兼容输入。
7. **CSV replay 最小支持**：已提供 `read_sensor_observations_csv()`/`replay_sensor_observations_csv()`，CSV 中 measurement/covariance 使用 JSON array，metadata/communication/source_support 使用 JSON object。
8. **延迟补偿审计字段**：已提供 `LatencyAuditSummary`，记录 max/mean delay、OOSM replay 次数、stale/OOSM count、duplicate count 和最大 replay 历史长度。
9. **区域质量摘要**：已提供轻量 `FusionQualityRegionSummary`，在单航迹 `TrackUncertaintySummary` 之上按 `coverage_cell` 聚合 source gap、freshness、a95、handover readiness、stale track count 和可选协方差增长率。
10. **2026-07-08 AirSim 多 seed 校准准备**：CSV replay 缺省 `schema_version` 时按 `d1.sensor_observation.v1` 验证并要求 `covariance`；Blocks calibration CSV 回归已覆盖 measurement/arrival timestamps、covariance、NED state、source support、latency/OOSM audit 和区域质量摘要。
11. **嵌套 EO camera metadata replay**：JSONL/CSV metadata 中的 `camera_model` 字典可恢复相机内外参并参与 EO 投影模型，避免真实 Blocks/CV replay 使用默认相机。
12. **雷达 cue 侦察粗指向摘要**：已提供 `ReconCueSummary` 和 `summarize_recon_cue_from_tracks()`，可从 `GlobalTrack[]` 或 track-like dict 生成全部目标/指定 `coverage_cell` 子群的协方差加权 `cue_position_ned`、`cue_covariance`、`active_target_ids`、时间戳和基础诊断；可选 `metadata` 保留二级/移动高空侦察节点、cue 来源和模式，供 main/AirSim runtime 控制二级侦察相机指向。
13. **真实 Blocks/CV 字段保真**：JSONL/CSV replay 已将顶层 `bbox_xyxy`、`center_px`、`camera_metadata`、`detection_metadata`、`source_support`、`coverage_cell`、`covariance_scale_reason` 和 secondary/mobile recon cue metadata 规范化进 `SensorObservation.metadata`，并把最新 EO/camera/bbox/recon lineage 带入 `GlobalTrack.metadata`。
14. **区域窗口与协方差增长 helper**：已提供 `annotate_covariance_growth_rates()` 和 `summarize_region_quality_windows()`，输出 `FusionQualityRegionWindowSummary`，可把区域质量下降、freshness 下降、source gap 与 latency/OOSM flags 分开给 D4/D6 消费。
15. **2026-07-09 P1 输入支撑补强**：dry-run fixture 已增加 schema version 检查，JSONL replay 已回归 unsupported schema version 拒绝，`summarize_sensor_observation_latency_audit()` 可在不运行融合器时统计 observation latency/OOSM/stale/duplicate lineage，Blocks/CV JSONL/CSV 回归已覆盖 `covariance_scale_reason`、`mobile_recon`、`recon_cue_summary`、`cue_position_ned` 和 `cue_covariance` 保真。
16. **D6 bundle 消费口径**：main/D6 可把 raw/fusion latency audit、`TrackUncertaintySummary`、区域质量/窗口摘要、`SensorHealthSummary`、covariance limit reason、`covariance_scale_reason` 和 `timestamp_uncertainty_s` 作为观测延迟与质量证据汇总；D1 不把这些字段解释为主动降级动作。
17. **2026-07-10 真实 2v2 合同复核**：六个 reset-separated episode 共 1,528 条
    radar/acoustic/EO/synthetic-lidar 观测均可由 D1 reader 解析，双时间戳完整，covariance
    有限、对称、半正定；full-flow 36 个 main bus tick 的 D1 观测摘要和
    `TrackUncertaintySummary` 也持续保留 timing/covariance 字段，未发现 D1 合同回归。
18. **2026-07-10 十 seed/在线身份隔离边界复核**：2v2 十 seed 系统运行证明 D1 DTO 可被
    多 episode 重复消费；5v5 truth-isolation smoke 证明 D5 在线 local detection/MOT ID 已
    与 actor/object 名称隔离。该证据不等于 D1 truth-free replay 闭合，`truth_id` 仍仅可
    作为离线评分标签，main truth-hint 配置仍需 provenance 和无真值对照。

当前 P0 状态：无 P0 blocker。D1 已实现并回归 measurement/arrival timestamp、协方差、NED `GlobalTrack`、N-target 输入和 `ReconCueSummary` 侦察 cue 合同；剩余工作均为 P1/P2 增强或外部 fixture/schema 对齐。

2026-07-10 main/D6 集成状态：main runtime 已新增 P1 D4/D5 calibration sweep，并在 sweep 后自动生成 D6 标准报告 bundle。D1 不负责启动 AirSim sweep、episode reset 或报告 bundle，只负责保证 `SensorObservation` replay、`GlobalTrack`、`TrackUncertaintySummary`、`LatencyAuditSummary`、`FusionQualityRegionSummary[]`、`FusionQualityRegionWindowSummary[]`、`SensorHealthSummary[]`、covariance reason 和 timestamp uncertainty 字段可被 main/D6 稳定消费。真实 2v2 产物确认 main tick 已发布 per-track uncertainty，但 main writer 尚未写显式 `schema_version`/`coverage_cell`，main tick 也未发布 region/window、latency audit 和 sensor health 摘要；main bus 依赖 simulation-only truth hint 保持 2 条航迹，而默认 truth-free replay 会产生 3 条航迹。因此这些仍是 P1 集成/校准项，truth metadata 只能作为离线评估标签。

剩余 P1：

1. **显式 replay schema 与区域字段**：当前真实 Blocks JSONL 未写 `schema_version` 和 `coverage_cell`，只能通过 legacy schema 兼容并归入 `unassigned`；main/shared writer 需采用 `d1.sensor_observation.v1` 并传递 coverage cell，D1 不跨边界修改 runtime。
2. **D6 长期批量 schema**：main tick 已发布 `TrackUncertaintySummary[]`，仍需发布并对齐 `LatencyAuditSummary`、`FusionQualityRegionSummary[]`、`FusionQualityRegionWindowSummary[]`、`SensorHealthSummary[]`、covariance reason 和 timestamp uncertainty 的长期 JSONL/CSV 字段。
3. **expected-latency/OOSM 健康阈值**：D1 已实现扫描级水位线、整帧 too-late 和有限缓冲合同；固定 0.2 s 延迟的正常多传感器流仍需 main 接线后用传感器预算和滑动比率校准，避免 FDIR-light 把正常流误标为 `isolated`。标定前不得把该摘要直接作为 D4 降级证据。
4. **truth-free replay 一致性**：把 fusion/association 配置写入 replay provenance，并修正无 truth-hint 时的重复初始化，使同一日志的离线 replay 与在线约束一致；truth metadata 不得成为真实在线身份证据。
5. **真实 Blocks/CV fixture**：2v2 十 seed 系统运行已完成，但尚未固化为 D1 长期回归 fixture；仍需 N actor、CV detection JSONL/CSV 样本覆盖 camera metadata、bbox covariance、`coverage_cell` 和 secondary/mobile recon metadata，并保证 actor label 只作离线评估标签。
6. **真实样本阈值**：区域窗口、freshness/source-gap、协方差增长率和 handover readiness 的持续阈值仍需带 `coverage_cell` 的多 seed fixture 与 D6 统计共同校准。

P2/后置：

1. **开源对照后端**：FilterPy、Stone Soup、OpenCV、ROS 2 仍未接入；只有在对照场景、依赖环境和收益指标明确后再作为 P2 或 P2 后置扩展。
2. **D1 直连 AirSim runtime**：D1 当前不直接调用 `simGetDetections` 或 AirSim API；P1 只要求消费 main/shared runtime 写出的 JSONL/CSV fixture。

---

## 7. 测试矩阵

| 测试 | 输入 | 期望结果 |
|------|------|----------|
| 雷达延迟 | 固定延迟点迹 | OOSM补偿后RMSE下降 |
| 距离变化 | 近中远三档雷达点迹 | 协方差随距离合理放大 |
| 声学粗方位 | 大角度不确定观测 | 只收窄方位，不强行定位 |
| 光电像素框 | 小框、遮挡、低置信度 | `R`放大，避免误配准 |
| 坐标错误 | 错误外参版本 | 触发质量告警，不发布高置信航迹 |
| 主动降级信号 | 协方差突增、观测延迟、传感器缺口 | 当前输出单航迹质量摘要、latency/OOSM audit、轻量区域质量摘要和区域窗口趋势；Blocks/CV replay 回归已固定这些字段的字段保真；`active_degrade_hint` 与最终区域仲裁仍由后续 D4/系统规则处理 |
| 侦察相机粗指向 | `GlobalTrack[]` 或 track-like dict，可选 `coverage_cell`/cue metadata | 输出 `ReconCueSummary`，按协方差 trace 反比加权 centroid，缺协方差使用保守默认并记录诊断；metadata 可携带二级/移动侦察节点与 cue 来源 |
| D5无截图交接 | 仅相机元数据和检测框 | 已支持不依赖PNG，输出可投影航迹和EO协方差 |
| D7航迹输入 | `stable/handover` 航迹和6x6协方差 | D7可读取位置、速度、时间戳和质量状态 |

---

## 8. 交付物

1. 文献综述：时间同步、坐标转换、协方差自适应建模。
2. 开源选型表：Stone Soup、FilterPy、ROS 2 tf2、message_filters。
3. 数据结构：`SensorObservation`、`CanonicalDetection`、`GlobalTrack`。
4. 接口伪代码：`FusionAdapter`、`DelayCompensator`、`TrackFilter`。
5. 雷达误差分档：`coarse`、`stable`、`handover`。
6. 主动降级/侦察 cue 接口：`TrackUncertaintySummary`、`LatencyAuditSummary`、轻量 `FusionQualityRegionSummary`、`FusionQualityRegionWindowSummary` 和 `ReconCueSummary` 已落地；D4 降级建议字段和最终仲裁仍为后续工作。
7. D5/D7接口合同：无截图 EO 输入、投影所需状态协方差、中段航迹质量门控。

---

## 9. 参考资料

- Stone Soup: <https://github.com/dstl/Stone-Soup>
- Stone Soup documentation: <https://stonesoup.readthedocs.io/>
- FilterPy: <https://filterpy.readthedocs.io/>
- ROS 2 tf2: <https://docs.ros.org/en/rolling/Concepts/Intermediate/About-Tf2.html>
- ROS 2 message_filters: <https://docs.ros.org/en/humble/p/message_filters/doc/Tutorials/Approximate-Synchronizer-Cpp.html>
- REP-103 coordinate conventions: <https://www.ros.org/reps/rep-0103.html>
- REP-105 coordinate frames: <https://www.ros.org/reps/rep-0105.html>

---

## 10. 历史基线：2026-07-11 Replay/Schema 专项评审

本轮将此前“reader 能读真实日志”推进为“D1 能定义并验证新 writer 合同”。

- `ReplayProvenance` 把 scenario/config/run/seed 与每条观测绑定，避免同一 JSONL 无法复现融合参数来源。
- governed writer 强制 schema 与 covariance，默认不写在线 truth/actor/object ID；离线评分标签只能放在 `offline_truth`。
- `SensorTimingExpectation` 明确“固定链路延迟导致的 OOSM 可以是正常现象”。D1 仍统计所有 OOSM，但只有未预期 OOSM、stale 或延迟预算超限才进入对应故障证据。
- 区域质量从任意长度聚合扩展为固定时长 `coverage_cell` 窗口，协方差增长、freshness、source gap 和窗口化 latency/OOSM 分开输出。
- 固化的 Blocks/CV 形态 JSONL/CSV fixture 不依赖 AirSim SDK；无在线 truth hint 的两目标 replay 可保持两条 NED 航迹及其 6x6 协方差。

测试结果为 D1 全量 `38 passed`。该结果关闭 D1-owned 的 schema/provenance、健康字段和窗口 helper 缺口，但不等于真实 AirSim 多 seed 标定完成。main 仍需接入新 writer、提供真实配置摘要、关闭 simulation-only truth hint，并把 D1 region/window/health 输出送入 episode bus 和 D6。

## 11. 历史基线：2026-07-11 5v5 Truth-Isolated Runtime 复核

main 在
`research_modules/airsim_runtime/outputs/p1_runtime_truth_isolated_d4d5_smoke_20260711/`
完成三个 5v5 case：不降级、二级节点接管、完全分布式。在线 truth hint 隔离后，每个 case
均运行 5 帧，D1/D2/D3 health 为 `ok`，D1 每组产生 15 条记录，D3 assignment coverage
保持 1.0。这是 D1 状态/协方差经过 D2 中心航迹进入 D3 的首个 truth-isolated 真实
main-bus 正向证据，旧的“main 仍依赖 simulation-only truth hint”状态应视为历史审计结论。

D1 governance 也已进入 `main_episode_bus_metrics.json`：三组均记录一次
`d1_latency_audit` 和一次 `d1_region_quality_window`，region quality coverage 为 1.0，
mean/max delay 约 0.2 s。`d1_oosm_observation_rate` 三组均约为 0.9867，但 stale rate 为
0。这个高 raw OOSM rate 符合当前固定延迟、多传感器逐条异步 replay 的统计定义，不代表
传感器故障，也不得直接触发 D4 降级；后续应使用 sensor-specific expected latency、
unexpected OOSM、stale、预算超限和持续窗口联合判定。

本轮只有 seed 7、5 帧、0.4 s，故不能关闭 multi-seed P1。仍需完成：

1. truth-isolated 多 seed 与长时 episode，覆盖正常、时钟异常、延迟突增和 stale 故障对照；
2. batch/watermark 与逐条 replay 两种 OOSM 口径对照，校准 expected-latency budget；
3. D6 长期 schema 对 `SensorHealthSummary`、covariance reason、timestamp uncertainty 和
   region window 的完整性审计；
4. 将真实 Blocks/CV camera/bbox/遮挡与二级侦察 metadata 固化为长期 fixture。

因此当前仍为“无 D1 P0 blocker，truth-isolated 单 seed 接线通过，multi-seed P1 未关闭”。

## 12. M 对 N 协同定位调研同步（2026-07-11）

专项调研见 `subagent_reviews/D1_M_TO_N_COOPERATIVE_LOCALIZATION_REVIEW.md`，覆盖 12 篇主要论文和 Stone Soup、FilterPy、GTSAM、OpenCV 四个官方开源候选。

对于一个高威胁目标由 3 架无人机共同观测的情况，D1 的默认思路是“共同估计时刻上的异步观测融合”，而不是强制三架严格同帧：

```text
各平台 measurement-time pose + bearing/range/bbox covariance
-> NED/time normalization and OOSM propagation
-> D2 confirms same canonical global_track_id
-> D1 joint observation update or conservative CI track fusion
-> GlobalTrack + covariance + geometric quality
```

两条标定良好且不平行的视线在理想条件下即可三角定位，第三架主要增加冗余、改善几何和抗遮挡能力。三条近似平行视线、过短基线或共享偏置仍会退化，因此必须使用 LOS 交会角、联合信息矩阵秩/条件数、重投影残差和平台位姿 covariance 判断质量。

模块边界明确为：D1 负责观测时空标准化、位姿/观测不确定性传播及已关联状态的数值融合；D2 负责跨平台观测/局部航迹关联、canonical `global_track_id` 和 ID continuity。若 D2 不能唯一确认同一目标，D1 必须保持不融合，不能自行重绑定身份。同步到达或分波次拦截属于 D3/D7，D1 只发布预测状态、协方差和几何质量。

调研阶段未新增 P0；其 P1 建议中的协同几何合同和最小 CI 数值原型已按下一节落地，真实三机 replay、D1/D2 双阶段 runtime 合同和离线开源 benchmark 仍保留，不改变既有 P2/P3 外部依赖安排。

## 13. 中心化协同定位 P1 数值基础实现（2026-07-11）

调研后的 D1-owned 最小基础已在独立 `cooperative.py` 路径实现，未改动
`FusionAdapter.process()` 默认行为：

- `ObserverLineage`、`CooperativeBearingObservation`、`CooperativeObservationGroup` 和
  `CooperativeLocalizationSummary` 保留 center-owned canonical `global_track_id`、observer
  lineage、平台位姿/传感器外参 covariance、measurement/arrival timestamp 和共同估计时刻。
- `localize_bearing_observation_group()` 支持任意 observer 数量且至少两条有效 LOS，使用
  NumPy bearing-ray weighted least squares，输出 pairwise 交会角、information rank/condition、
  perpendicular/angular/weighted residual 和 geometry accept/reject reason。
- 几何 helper 对重复 lineage、短基线、近共线、过大 measurement skew、缺失/非法
  covariance、rank/condition 退化和残差超限保守拒绝；显式配置时可对缺失 covariance 使用
  保守默认并标记 inflation。异步 bearing 按目标速度传播到共同估计时刻，并加入
  process/timestamp covariance。
- `covariance_intersection()` 支持 1/2/3/N 个 6-state NED estimate，先做共同时间 CV 传播，
  再以最小 log-det CI 处理未知交叉相关；相同 message UUID 或完整 source lineage 不重复计数，
  输出始终保留输入 canonical ID，不创建或重绑定 ID。

构造性测试已覆盖良好三视角不劣于最佳双视角、退化拒绝、0.4 s 异步传播、1/2/3/N
observer/source、duplicate 不重复收敛、CI 不比错误独立融合更自信及 mixed canonical ID
拒绝。该结论仅是中心化 P1 数值基础，不表示 D2 跨平台关联、main/AirSim runtime、真实
多 seed、部分共享 lineage、成员退出或分布式协同定位全链路已经完成。

## 14. 历史证据、缺口分层与执行次序（2026-07-11 三 seed）

最新 M-to-N AirSim 报告覆盖 seeds 7/17/27：每组均有 6 次重规划请求和 6 次 no-change
ACK，无 applied/expired，需求满足率为 1.0，错误重复锁定为 0；T002 形成 4/5/4 帧共识并
使 D7 每 seed 获得 2 次终端合同许可，T001 双 primary 共识仍为 0。该 ComputerVision
结果只验证 D1 合同能够进入收敛的 M-to-N 状态链，不是物理拦截或真实传感器精度证据。

- P0 无 blocker，当前 D1 回归为 `62 passed`；双时间戳、NED、协方差、质量治理和身份
  lineage 继续作为硬合同。
- P1 已完成的是接口和中心化数值基础；未完成的是 main/D2 runtime 接线、真实 AirSim
  多 seed 协同 replay、故障/遮挡/节点退出、RMSE/NIS/NEES 与持续阈值、模型集和场景
  自适应 covariance 标定、D6 长期 schema。
- T001 双 primary 视觉共识是 D5/D7 的系统 P1；D1 不能通过放宽 covariance 或身份门控
  代替下游闭合。
- FilterPy、Stone Soup、OpenCV/GTSAM 和 ROS 2 均属于 P2 optional benchmark 或后置
  集成，不进入默认路径。

后续先让 main/shared 采用 governed writer 并分离离线 truth，再由 D1/D2 接通 canonical
ID 已确认的 cooperative adapter；随后采集真实多 seed 数据完成统计标定；最后运行第三方
离线对照。实现阶段验收命令保持为
`PYTHONPATH=research_modules/d1_sensor_fusion/src pytest -q research_modules/d1_sensor_fusion/tests`。

## 15. Governed Replay 合同实施复核

D1 已在现有 `ReplayProvenance` 和 record writer 上增加严格批量入口，而没有再造平行观测
类型。`serialize_governed_replay()` 输出 manifest/records，要求 scenario/config ID、version、
digest、seed、coverage cell、双时间戳、NED fusion working frame、covariance 和 source
lineage 完整且可 JSON 序列化。covariance 同时检查维度、有限性、对称性和半正定性。

在线 metadata 的 truth/actor/object 标识会被递归剥离，lineage 改用不暴露真值的观测摘要。
离线评分只能显式调用 `serialize_offline_governed_replay()`，标签固定放在 `offline_truth`。
旧无版本 Blocks JSONL reader 保持兼容，以免破坏历史回放；它不具备 governed manifest 的
完整性保证。

多目标、字段缺失、legacy、truth stripping、双时间戳、covariance 和 lineage 测试均已
通过。该项关闭 D1-owned P1 实现；最新 main episode bus 已采用
serializer，并把在线记录与离线 truth 标签分离。真实 AirSim 传感器精度和长时统计标定仍
需后续验证，但不影响 P1 合同层闭合。

## 16. 当前结论与真实 Replay 后续项（2026-07-11 最终验证）

最终依据为
`research_modules/airsim_runtime/outputs/p1_p2_validation_20260711/P1_P2_VALIDATION_SUMMARY_CN.md`。

1. **P1 合同层闭合**：D1 governed replay、双时间戳、covariance、coverage/lineage 和
   scenario/config provenance 已由 main episode bus 写出；在线记录递归剥离 truth/actor/object
   identity，truth 只写入独立离线标签供评分。
2. **CV 合同验收通过**：10 seeds 中 8/10 达到 T001 双 primary 合同阈值。二级和完全分布式
   3/3 ACK commit 正例通过，缺 ACK 的 2/3 case abort 并 fail-closed。D1 只把这些结果作为
   状态、协方差、时间和 lineage 成功进入下游链路的证据，不承担联盟仲裁或控制职责。
3. **物理拦截未闭合**：SimpleFlight 15 s 仅为诊断，30 个 active pair 均未命中；该结果既
   不是 D1 融合精度验收，也不能替代真实传感器或长时 replay 标定。
4. **P2 仅隔离 benchmark**：可选第三方 adapter/模型不进入默认依赖，不升级或替换 NumPy
   EKF/fixed-lag 主线。

真实 replay 后续项应准确表述为：D1/D2-confirmed cooperative runtime adapter，以及机动、
遮挡、节点退出、camera/bbox、sensor-delay/fault 的更长多 seed 数据；在这些数据上完成
RMSE/NIS/NEES consistency、sensor-specific expected latency、health/region window、模型集
和场景自适应 covariance 标定。governed writer 接入、在线 truth 隔离和 CV 双 primary 合同
验收已完成，不再作为当前缺口。

## 17. P2 隔离滤波对照复核

本轮没有把 FilterPy 或 Stone Soup 接入在线 D1，也没有增加默认依赖。新增的隔离 runner
只读取冻结 governed replay：online records 保持 truth-stripped，双时间戳、covariance、NED
和 lineage 先通过校验，独立 offline truth sidecar 仅用于滤波后的 RMSE/NEES 评分。

当前 NumPy EKF/fixed-lag 路径在六条固定 radar 观测上输出 RMSE `0.2335 m`、mean NIS
`0.0426`、mean NEES `0.0651` 和两次 `6.9-10.1 ms` 主机耗时。该合成样本显示 covariance 偏保守，
只证明 RMSE/NIS/NEES/time 证据链可运行，不构成真实传感器 consistency 验收。当前环境中
`filterpy` 与 `stonesoup` 均不可用；两项结果固定为 `unavailable`，第三方指标为空且包含
`unavailable_reason`，不存在静默回退或伪对照。

后续 P2 只在隔离依赖环境中实现并评估真实 adapter；收益未证明前不得替换默认 NumPy
路径。真实多 seed 的机动、遮挡、节点退出和延迟/故障 consistency 仍是 P1 标定项。本轮
D1 全量回归为 `62 passed`。

## 18. P1 长 Replay 场景与汇总接口（2026-07-12）

D1 已在现有 governed replay 合同上增加独立 `long_replay.py`，供 main 构造长时、确定性的
crossing/遮挡/延迟/OOSM 科研场景。实现没有直连 AirSim，也没有引入新的滤波后端：

```text
LongReplayConfig
  -> build_long_replay_scenario()
  -> truth-free SensorObservation[] + ReplayProvenance
  -> existing governed writer / FusionAdapter
  -> summarize_long_replay()
  -> latency + health + region windows + metric availability

offline truth trajectory/labels
  -> separate d1.long_replay_offline_truth.v1 sidecar
  -> D2/D6 offline scoring only
```

默认场景 60 s、3 个目标在 NED 中交叉，雷达 covariance 随距离增长并在 crossing clutter 窗口
放大；声学只给粗方位和通用 `small_uas` hint；EO 输出像素/camera metadata，并在交叉区间生成
完全和部分遮挡。延迟分布、显式 radar OOSM 与 relay 重发均可按配置调整。

在线 observation ID/source lineage 使用不透明 payload 序号，不编码稳定目标 slot。真值只在
独立 sidecar，`FusionAdapter` 固定 `use_truth_hints_for_association=False`。没有 D2
canonical-ID 离线映射时，RMSE/NEES 以 unavailable reason 输出，避免把无法计算的指标写成
0 或让 truth 反向进入在线航迹。

默认 smoke 输出 843 条观测、21 次显式 OOSM、6 次被去重 relay copy、29 个区域窗口，在线
truth leak 为 0，耗时约 8.8 s。新增测试覆盖版本冻结、covariance/双时间戳/NED/lineage、
在线 truth 隔离、事件触发、汇总 JSON-safe 与同 seed 确定性；加入 CLI 子进程测试后 D1
全量更新为 `66 passed`。

官方 `scripts/run_long_replay.py` 仅封装上述公共 API，支持 seed、duration、target count 和
JSON output path。CLI 输出与 `LongReplaySummary.to_dict()` 完全一致，不读取 offline truth、
不新增关联旁路，并通过真实子进程测试验证参数和输出 schema。

该能力关闭 D1-owned 合成长 replay 与汇总入口，不关闭真实 Blocks/CV multi-seed、
D2-confirmed mapping、真实 RMSE/NIS/NEES、sensor health/window 阈值、camera/bbox/节点退出、
模型集或场景自适应 covariance 缺口。后续 main 应将真实数据按同一 governed schema 写入，
而不是把合成结论当成真实传感器验收。

## 19. 真实 AirSim dense/crossing Replay 冻结复核（2026-07-12）

D1 已补齐不依赖 AirSim SDK 的持久化输入冻结边界。main 可提供 JSON/JSONL 的直接 observation
或包含 observation list 的 frame；D1 按输入长度转换到既有 governed replay，不限制 5-target。
输出包括 manifest、在线 records、evaluator-only truth sidecar 和诊断 summary。

本轮重点强化旧 Blocks 数据的身份隔离：不仅清理 metadata identity key，还将在线
observation ID 不透明化，并清除嵌套字符串中的已知 truth token。processing/publish 时间、
sensor health、scene/profile/source schema 缺失时显式 unavailable；measurement/arrival、
covariance、coverage 和 canonical frame 缺失则拒绝该 observation。遮挡、漏检和节点退出等
无量测事件不生成观测，避免把场景标签伪装成传感器信息。

该接口可作为第二批 D1 -> D2/D6 输入冻结入口。下一步由 main 用真实 AirSim 多 seed 产物调用，
由 D2 使用独立 truth sidecar 离线评分，由 D6 聚合 consistency 和阈值；D1 不承担 AirSim 连接、
目标身份关联或报告评分职责。本轮 D1 全量回归在 sidecar follow-up 后为 `74 passed`。

### 19.1 D2 strict adapter follow-up

sidecar 现以 `(truth_id, timestamp)` 为唯一键。frame truth 的 available position 会覆盖同键
observation metadata identity-only 样本；两个 available 不一致时 freeze 直接失败并给出 key 和
两组位置。不同时间的样本保持独立，仅有 unavailable 的样本保留并计入 summary，绝不生成
估计位置。专项回归覆盖 available-first/unavailable-first、available 冲突和不同时间三类情况。

### 19.2 4 m/2 m 捕获证据治理

AirSim persisted-input freezer 已增加捕获 provenance 强门控。输入必须声明 scenario/config
version、seed、目标间距和 evidence path；D1 将捕获值写入 governed manifest/record provenance
并发布字段 availability。`target_spacing_m` 不从离线 truth 位置估算，调用方声明或多个 payload
声明冲突时直接拒绝。truth 继续只写 evaluator sidecar，sidecar 与在线 manifest 共享 capture
digest。专项测试覆盖 4 m/2 m 各 20 seeds，完整 D1 测试为 `79 passed`。截至本节记录的
2026-07-12 阶段，下一步是由 main 提供符合该合同的真实多 seed 采集，并由 D2/D6 按职责
完成关联与统计；该阶段计划已由下一节的 2026-07-13 证据更新。

### 19.3 真实 40-Episode 收敛结果（2026-07-13）

上一节所述采集已经由 main 完成：4 m/2 m 各 20 seeds，共 40 个真实 AirSim episode；D1
冻结产物对应 10,200 条 evaluator-only truth，在线 truth 泄漏为 0。D2 已进行离线关联标定，
D6 已将 D1 source 标为 `available`。因此当前下一步不再是“补齐 dense crossing 采集”，而是：

1. 采集带真实漏检、匿名虚警、部分/完全遮挡、异步采样率、sensor-specific latency 和节点
   退出的版本化多 seed 长 replay；D1 对无量测事件只记事件，不伪造观测。
2. 用正常/故障对照校准区域时间窗、covariance growth、expected-latency/OOSM、sensor health、
   handover readiness、NIS/NEES 和 `covariance_scale_reason` 的持续阈值。
3. 由 D6 对跨场景、跨 seed、长时运行的 availability、evidence path、health/region window 和
   consistency 指标做长期汇总；缺失指标保持 `unavailable`。

上述事项仍是 P1。Stone Soup、FilterPy、ROS 2、OpenCV/GTSAM 等第三方路径继续保持
P2/P3 可选状态，不能因本次 AirSim 证据写成已经接入。

## 20. 在线 Scene Observation 身份边界评审（2026-07-14）

本轮定位到的 P0 不是“仿真 scene truth 完全不能参与传感器仿真”，而是 scene state 生成
`SensorObservation` 后，原 `observation_id`、source lineage、classification 和嵌套 metadata
仍可能携带目标/actor/object/segmentation 身份。D1 现从包顶层提供：

- `anonymize_online_observations(observations, *, identity_tokens=(), stream_id="online")`；
- `assert_online_observations_identity_free(observations, *, identity_tokens=())`。

前者返回深拷贝匿名观测，按 frame/帧内顺序生成不透明 observation ID，并把原 source lineage
映射为匿名 lineage；同一原 lineage 的 relay duplicate 仍保持同一映射。递归身份键、嵌套
token 和 classification target token 被清理。measurement、covariance、measurement/arrival
双时间戳、sensor/camera geometry 和通信时间不变。后者遍历在线对象并在任何残留身份键或
已知 token 时 fail closed；匿名化函数返回前必经该 validator。

2026-07-14 专项回归用两组各 2 条 EO 观测，仅替换 target/actor/truth 名字，要求匿名结果所有
字段严格相等、数值/相机几何逐元素一致、在线泄漏为 0、注入泄漏全部拒绝，并确认原 observation
和 evaluator-only sidecar 不变。结果专项 `4 passed`，D1 全量 `83 passed`。因此 D1-owned P0
API 缺口关闭；main/runtime 仍须在每个 scene-state 在线入口接线，并通过 `identity_tokens`
补充无法从身份键推断的别名。本轮没有修改 dry-run/offline evaluator、AirSim episode 编排、
D2 身份关联或 D6 评分。

剩余 P1 仍是：真实 sensor-specific challenge 长 replay 和 latency/health 分布、区域/
covariance/NIS/NEES 持续阈值、D1/D2-confirmed 协同融合与 3->2->1 节点退出、D6 跨场景长期
一致性，以及 CV/CA/CT/IMM 和场景自适应 covariance 对照。第三方库继续保持 P2/P3 可选。

## 21. 真实 Episode 重复 Birth/Teleport 专项评审（2026-07-14）

对 `p1_terminal_closure_truthisolated_preflight_v2_20260714_m5n2_baseline_seed001` 的持久化
观测和 main bus 进行只读审计后，D1 侧确认三个相互叠加的问题：同一物理 observer scan 可
重复更新同一航迹；严格雷达门限失败可直接生成重复 birth；fixed-lag 裁剪丢弃了中间滤波后验，
后续回放可能从过旧锚点长时间外推。source lineage 能识别重复 payload，但不能替代匿名目标
关联，因此修复不能依赖 actor/truth ID。

当前实现增加扫描唯一性、唯一近期成熟雷达重捕、模糊 birth 抑制、非测距状态修正审计和
`d1.association_audit.v1`。fixed-lag 检查点放在滞后边界之前最近的已接受量测后验，避免任意
拆分当前过程噪声区间；更早的合法 OOSM 通过 origin/archive 回放。回归明确覆盖同 scan 编号
的跨模态 acoustic 融合，防止 observer-scan 规则误伤。

2026-07-14 验证：专项 `5/5`、D1 全量 `87/87`；main 报告 AirSim runtime `134/134`。
修复后同 M5N2 seed 尚未复跑，所以评审结论是“D1 根因与代码回归已闭合，真实 episode P1
证据仍开放”。下一步仅由 main 复跑并检查航迹数、状态步长和审计原因；D1 后续再基于多 seed
统计校准门限和回放资源预算。

## 22. Covariance 输入合同复核（2026-07-14）

复核确认历史风险来自两条旁路：普通 legacy reader 可产生 `covariance=None`，而
`FusionAdapter` 会用 modality default 替换缺失/非法矩阵。现已统一为正式路径 fail closed：
radar/legacy acoustic/`acoustic_3d`/EO/lidar 分别要求
`4x4/1x1/2x2/2x2/3x3`，并校验有限、对称和半正定；测量模型、
在线融合、governed replay 和 AirSim freeze 不再修复坏输入。

历史兼容被隔离到显式 `migrate_offline_legacy_sensor_observation()`。provenance 固定记录
`explicit_offline_legacy_migration`、原始缺失原因、model/default ID、参数来源和生成输入；
带该标记的 observation 只能供 evaluator 使用，进入在线融合、在线 serializer 或 freezer 会
被拒绝。2026-07-14 无随机 seed 的构造合同用例与既有 replay/OOSM/AirSim freeze 回归全部
通过，D1 全量 `92/92`。

评审结论是 D1-owned covariance 合同硬化缺口已关闭。仍开放的是用真实多 seed 传感器数据
标定 covariance、NIS/NEES consistency、故障/遮挡 scale 和长期阈值；offline migration default
不得作为上述证据。

## 23. 同帧批量 OOSM/Fused Replay 评审（2026-07-14）

main 对最新 M5N2 seed-001 前 40 帧的只读 profile 显示，同一 tick 多模态观测逐条处理会反复
计算同一航迹、同一 measurement time 的历史状态，并在每次接受后重放到 current time。D1
新增正式 `process_batch()`，仍按输入顺序逐条执行 covariance、双时间戳、NED/pixel、source
lineage、scan uniqueness、关联和 OOSM 规则，仅复用相同 history revision 的 state-at-time，
并把发布重放合并到每个 changed track 一次。

批量结果明确区分 `tracks` 批末快照和 `summary` 审计。后者提供 observation/accept/duplicate、
created/updated、affected tracks、history/origin replay、cache hit/miss、finalization replay 和
deferred replay avoidance。`ingest_many()` 保持 arrival 排序兼容并使用该实现；需要每条中间
快照的调用方仍使用 streaming `process()`。

验证日期 2026-07-14。构造场景为 5 航迹/15 条 radar-lidar-acoustic 同帧 observation，
replay 95 -> 24、下降 74.7%，state/covariance 在 `1e-9` 容差内等价。已有 M5N2 baseline
seed-001 前 40 帧共 786 条持久化 observation，逐条 18.05 s/1267 replay，batch
5.70 s/351 replay，3.17 倍加速，state/covariance 最大差 0。专项 `6/6`，D1 全量
`98/98`。

评审结论：D1-owned 批量接口和最少 replay P1 已闭合；main/runtime call site、完整 245/248
帧及多 seed 100 ms loop 验收仍开放。不得将 D1-only persisted replay 的 3.17 倍加速写成系统
实时预算已经达成。Stone Soup、FilterPy、ROS 2 等 P2/P3 状态不变。

## 24. Scalable 3D 扫描级融合评审（2026-07-20）

旧 `process_batch()` 的目标是与逐条流式处理等价，因此同一雷达 scan 仍逐条关联。密集首扫中，
第一条点迹 birth 后，其他近邻点迹可能先命中同航迹的固定门限，再被 observer-scan uniqueness
判为重复；航迹数于是由门限空间 packing 决定，而不是由可分点迹数量决定。该语义必须保留给
历史回归，但不适合作为新三维总线的扫描级起始器。

本轮增加独立 `process_scan_batch()`：所有点迹只与 scan 前航迹比较，使用三维马氏代价和
Hungarian 做一对一匹配，随后让每个未匹配 radar 点迹独立 birth。main 的三维球坐标 covariance
通过解析 Jacobian 传播到 NED 六状态；无径向速度时显式保留未观测速度不确定性。适配器不导入
main 模块，且在读取业务字段前拒绝任何 truth/actor/object/entity/target ID。输出继续使用 D1
六维 `GlobalTrack`，数量不含 2/5/200 常量。

新增 `acoustic_3d` 处理 `[azimuth,elevation]` 与 `2x2` covariance。它是 bearing-only 弱约束，
不能起始三维航迹；soundprint 只保留归一化类别概率，`soundprint_is_identity=False` 被转换为
category-only 治理证据，不参与匹配或稳定 ID。该边界与 cooperative bearing WLS/CI 不同：
本轮没有把单节点声学方位伪装成三维定位，也没有实现跨节点身份确认。

2026-07-20 模块验证使用 seed 7：5/20/50/100/200 各两次扫描，共 750 条匿名 radar
measurement，首扫和次扫均 100% birth/update，200 档保持 200 个 ID；另验证 2 条 delayed
OOSM、5 条 acoustic 无先验 0 birth/有先验 5 update，以及注入 truth/actor/object ID 100%
拒绝。专项 `9/9`、全量 `120/120`。评审结论为 D1-owned scalable scan path 已实现；main bus
接线、D2 六维 continuity、D6 至少 20 个未见 seed 的召回/IDSW/一致性和复杂生命周期仍开放。

## 25. Scalable 3D 六维速度稳定性评审（2026-07-20）

### 25.1 根因与设计判定

main 在 radar-only、seed 17 的 50/200 条链路中观察到 D1/D2 航迹数量完整，但速度均值明显
高于短 episode 的物理运动尺度。D1 复核确认没有显式位置差分代码；放大来自两个统计环节：

1. scalable producer 只提供 `[range, azimuth, elevation]`，旧适配器却把 canonical 补零的
   radial velocity 继续送入四维 EKF，等价于反复声明径向速度为 0；
2. 0.2 s 内真实位移小于单帧球坐标位置噪声，CV 的位置-速度交叉协方差会把短基线噪声写入
   速度后验。速度 covariance 很大，因此这不是“假装高精度”，但下游直接使用均值仍会受影响。

本轮采用统计先验而非硬限速。canonical observation 继续保持 4 维/`4x4` 兼容合同，但
`radial_velocity_observed=False` 时滤波只消费前三维；起始状态使用 `v0=0`、
`Pvv=25I m2/s2`、`Ppv=0`。该方差与 3 自由度 99.9% NIS 门限均公开可配置，不读取 truth、
actor/object ID、`target_speed_max_mps` 或 4.7 m/s 上界。

### 25.2 门控、OOSM 与审计

位置-only radar 的更新门限为 `chi2_3(0.999)=16.26623619623813`。超门限量测不修改预测状态，
但仍保留 observation history 和原始双时间戳，使后续 replay 在相同 measurement-time 顺序下
确定地得到同一拒绝结果。航迹 metadata 显式记录 `latest_replay_innovation_count`、实际 filter
update 数、gate rejection 数和匿名 observation IDs。构造用例让离群点仍在扫描关联门限 40
之内，以证明拒绝发生在滤波创新层，而不是通过新建/丢失航迹绕开。

### 25.3 证据与边界

2026-07-20 自动化场景如下：

- 一个无多普勒 radar 样本验证 3 维滤波模型、零均值速度和 `25I` 方差；
- 一个 3 scan 离群序列验证 1 次创新拒绝及全部审计字段；
- 两条航迹的顺序/乱序 3 scan 对照验证 2 条 OOSM，state/covariance 容差 `1e-9`、双时间戳和
  `6x6` covariance；
- seed 17、200 条、10 scan、2,000 条匿名 radar measurement，数量和 ID 全程为 200，末帧
  速度 median/P90/max=`3.87/6.43/8.54 m/s`，速度 covariance trace=
  `57.97/60.69/61.19`。

专项 `13/13`，D1 全量 `124/124`。50 条开发探针从 `6.28/12.16/21.03` 改善为
`3.99/6.12/9.69 m/s`，但 trace 仍为 `58.22/60.43/60.90`，所以评审结论是 D1-owned
噪声放大缺口已关闭、短基线速度仍是高不确定度估计。至少 20 个未见 seed 的 NIS/NEES 和
coverage、机动/漏检/虚警、D2 二次滤波与 D3 分配正式复验仍开放。本轮不影响 AirSim 文档。

## 26. Consistency evidence 与离线 evaluator 评审（2026-07-20）

此前 scalable path 的 NIS 只以 `last_nis` 和 replay metadata 摘要存在，无法让 main/D6 按
observation、sensor、range 和 scenario 复算；RMSE/NEES 又必须等待 D2 canonical identity，
把二者混在 episode producer 会破坏 truth 隔离。本轮评审采用两个物理 artifact：在线 D1
evidence bundle 与离线 D1 result，中间仅由独立 truth sidecar 和 D2 evaluator-only
observation-lineage mapping adapter 连接。

在线采集挂在已有 track birth 和正式 replay 结果后，不参与候选 association，也不改变 EKF、
measurement model、gate 或 ID。每条 record 给出 metric-specific availability；初始化没有 NIS，
acoustic/EO 无 track 时不补 estimate，未配置 innovation gate 的已接受模态可有 NIS 但 coverage
不可用。OOSM 以最终 replay revision 为准，从而避免把到达时的临时后验当正式证据。

离线 evaluator 对所有 available estimate 要求按 `observation_id + measurement_timestamp` 获得
唯一 D2 canonical mapping 和同 measurement time 唯一六维 truth sample。D1 evidence 仅输出
`source_global_track_id`，不会被当作 D2 `global_track_id`。任何 mapping coverage、truth ID、timestamp、schema、hash、
scenario/run/seed/config provenance 不一致都会停止 truth-dependent aggregation；没有 proximity 或
名称 fallback。NEES 要求正定 covariance，奇异时 episode NEES unavailable，但不影响独立 RMSE
和 NIS。flat rows 带全部输入 digest，D6 可追溯每个聚合值的来源。

2026-07-20 新增 `12` 个构造合同测试，包含在线额外 truth 字段拒绝；main 复跑 D1 全量
`136 passed`。评审结论是 D1-owned
评估合同已关闭，正式效果证据仍开放：至少 20 个未见 seed、复杂 crossing/漏检/虚警/机动、
按 sensor/range/scenario 的 RMSE/NEES/NIS coverage 与置信区间、D2 canonical mapping 完整率和
D6 阈值均未验收。AirSim runtime 未改也未运行，历史 AirSim 指标 availability 不变。

## 27. 扫描输入水位线评审（2026-07-22）

### 27.1 评审结论

此前 scalable adapter 会在 `process_online_sensor_batch()` 中立即把到达扫描交给融合器。滤波器
能回放已经接受的 OOSM，但上游没有“这一整帧是否仍允许进入在线链路”的独立裁决，也没有对
迟到窗口、缓冲数量和驻留时间给出可执行上限。新 `ScanInputOrganizer` 把这两个问题分开：

```text
OnlineSensorBatch
  -> sensor_observations_from_online_batch()
  -> SensorScanFrame
  -> ScanInputOrganizer.ingest()
  -> released_scans only
  -> FusionAdapter.process_scan_batch()
  -> D2
```

扫描整理层不读取 target/truth/actor/object identity，也不访问或改写 `global_track_id`。它以
source namespace、scan ID、immutable observation lineage 和数值 payload digest 治理重复与
冲突。等于当前水位线的量测时刻仍开放，因而同一时刻的不同来源扫描可以共同进入窗口；严格
早于既有水位线的扫描整帧拒绝，不会把部分点迹送入 D1 或 D2。

`SensorScanFrame` 使用字段级只读快照兼容 main 的嵌套 `mappingproxy` 视觉元数据。measurement、
covariance 和元数据数组均独立复制，嵌套映射递归冻结；快照后继续执行 covariance 与 truth
隔离，因此只读输入不会绕过在线身份边界。

### 27.2 main 调用责任

main 对每个到达批次转换一次并调用一次 `ingest()`。调度时钟前进但没有扫描时调用
`advance_arrival_time(now)`，只让驻留超时可被审计；episode 输入结束调用 `close()`，处理最后
一批 `released_scans` 后再关闭链路。每次结果中的 `events` 是逐帧证据，`audit` 是累计快照；二者
应由 main 持久化并交给 D6。buffered/rejected 帧不能直接调用 `process_scan_batch()`，D2 只接收
释放帧融合后产生的 tracks。本轮严格没有修改 main-owned 文件。

### 27.3 验证与限制

确定性专项为 15 项，无随机 seed、无 AirSim：有序、窗口内乱序、超窗 too-late、同时间多源、
duplicate/replay/conflict、到达时间回退、扫描/观测容量、驻留超时、1/7/200 动态数量、在线
truth 拒绝、main 批次转换组合和嵌套 `mappingproxy` 快照均通过；D1 全量 `151 passed`。该证据
关闭 D1-owned 的扫描输入 P1，不证明 20/50/100/200 长 episode 参数已经合适，也不证明 D1-D2
吞吐达标。

`ScanInputOrganizer` 不是固定滞后 Kalman smoother。它只决定完整扫描何时释放或拒绝；释放后
仍由现有 fixed-lag replay 做 measurement-time 状态重建。main 后续必须记录配置/schema、
watermark、缓冲峰值、too-late/overflow/expiry、close tail 和误拒率，再冻结场景级阈值。

## 28. Main 正式治理接线证据评审（2026-07-22）

### 28.1 治理层结果

快速治理 benchmark 的价值是把接口接线和算法吞吐分开。四档规模各 5 个 seed 的扫描数、
时长和预置乱序方式相同；每 episode 的 12 个乱序扫描均被重排，拒绝、过旧、溢出和淘汰均为
0，结束缓冲为 0。20/20 均来自同一 clean 提交且标记 formal。200 规模峰值内存均值约
40.91 MB、最大 40,926,870 B。结果说明当前正式配置在这一构造流上没有误拒或尾部泄漏，并不
说明真实传感器时延分布下仍保持相同结果。

输入 SHA-256 和清单引用的 60 个制品均已核验。该 runner 没有导入完整运行时控制模块，近邻
召回等 evaluator-only 数值只能解释快速 benchmark 自身，不能提升为 D1 EKF 精度、D2 身份
连续或 200v200 全系统效果。

### 28.2 全栈结果

旧 dirty development 单 seed 全栈运行确认 D1 organizer 在 2,051 条匿名观测上完成 86 个扫描的接收、重排和关闭，
没有在线 truth 使用。它同时说明扫描治理成本并非当前主导项：输入整理平均 31.186 ms，而完整
融合平均 408.313 ms。总仿真只推进 2.2 s，墙钟用时 60.210 s，无法满足实时执行。

当前尾部合并只减少 D2 对中间快照的重复消费。D1 为保持每个释放 scan 的滤波顺序，仍逐帧调用
完整扫描处理。后续不能简单把多个来源观测拼成一个伪扫描，否则会破坏 observer scan uniqueness
和一对一关联语义。可行方向是保持每帧关联和审计，延迟共同量测时刻内的全局发布传播，并仅
对 dirty tracks 进行重放和快照。

### 28.3 评审结论

D1 扫描输入合同及 main clean/formal 治理接线已经验收，相关复跑 GAP 关闭。截至该次治理
评审，融合吞吐尚未闭合，要求先补函数级 profile 和同输入语义等价证据。该要求已由下节的
D1-owned 优化完成；clean 全栈多 seed 周期预算、AirSim、传感器精度和正式 200v200 完整拦截
验收继续独立开放。

## 29. D1 逐扫描融合性能治理评审（2026-07-22）

### 29.1 方案取舍

本轮没有合并不同 observer scan，也没有延迟或省略扫描级关联。优化只复用已经计算且输入前缀
未变化的滤波后验。每个检查点绑定 observation ID、量测/到达排序键、后验、NIS 和 gate 结果；
新观测插入后仅删除排序位置及之后的检查点。固定滞后锚点改变时全部重建，避免旧锚点污染。

公共发布审计快照只消除同一扫描内对相同全局状态的重复序列化准备。每条 `GlobalTrack` 仍独立
复制 metadata、state 和 covariance。observer-scan conflict、双时间戳、fixed-lag OOSM、
covariance 限幅、航迹分级和 consistency evidence 均保留。

### 29.2 验收判断

冻结输入 SHA-256 为
`38d24429711b67d612f2f398478386ebf0df690fae55cd9dcc36434aac4fb078`。未缓存参考和优化路径
均处理 86 个扫描、2,051 条观测并输出 201 条终态航迹。逐扫描语义摘要、终态和 evidence 哈希
完全一致；在线 truth 使用为 0。确定性操作计数显示滤波更新下降 98.07%，该指标比墙钟更适合
持续回归。

评审结论为：D1-owned 冻结输入逐扫描热点已关闭；系统实时预算仍开放。下一步由 main 在 clean
commit 上运行完整未见多 seed，验证长历史、内存、D2-D7 下游和端到端周期。正式融合精度、
AirSim 与物理拦截不属于本次证据。性能专项 `6 passed`，main 复跑 D1 全量
`157 passed in 28.77s`。

## 30. Clean 200v200 延迟物化接线评审（2026-07-22）

### 30.1 接线判定

clean 候选提交 `8f86192` 已按 D1 合同处理同一 runtime tick 释放的多个扫描。每个扫描仍独立
执行状态更新并产生发布记录；同一 fusion timestamp 只有中间记录采用
`tracks_materialized=false`、空 tracks 数组和
准确 `current_track_count`，最后后验才生成完整快照。三个 10 s seed 的 state-only/完整快照为
`310/454`、`328/516`、`278/504`，逐例合计等于 `764/844/782` 个接收和释放扫描。

评审认为该实现遵守扫描原子性。它没有把不同 observer scan 合并，也没有改变双时间戳、
covariance、fixed-lag/OOSM、门控、来源谱系或 `global_track_id`。事件、scan input、共享摘要和
世界真值与旧 clean `3bac3ff` 对应 seed 相同。

### 30.2 性能与安全判定

seeds 42000、42001、42002 的 D1 fusion 分别从
`103.176/106.447/100.394 s` 降至 `89.796/96.599/92.578 s`，均值
`103.339 -> 92.991 s`，下降 10.0%。2.2 s seed 42000 全栈墙钟
`18.611 -> 18.302 s`。3/3 episode 均 clean、finite，在线 truth 使用 0，D1/D2 overflow 和
安全合同全部通过。

该数据支持“延迟物化已接线且没有破坏当前语义”，不支持“200v200 已实时”。D1 单项处理 10 s
输入仍平均耗时 92.991 s。正式 RMSE/NEES/NIS、真实传感器时延、AirSim 和物理拦截不在本次
证据范围。

### 30.3 后续计划

1. 在固定硬件和预注册周期预算下扩展时长与未见 seed，报告 P50/P95/max、峰值内存和日志增长。
2. 通过独立 truth sidecar 与 D2 canonical mapping 形成按传感器、距离和场景分组的
   RMSE/NEES/NIS consistency 证据。
3. AirSim 若采用相同 state-only writer，再单独验证时间基准、传感器桥接、episode reset 和
   持久化 schema；本轮质点结果不能直接迁移为 AirSim 结论。

## 31. 雷达预门控数学复核（2026-07-22）

### 31.1 适用性判定

评审不接受直接用协方差迹构造下界。创新协方差可能含非正定交叉项，`np.linalg.pinv` 也会截断
近零奇异值；这两种情况下，欧氏距离除以 trace 可能预拒绝旧路径仍会保留的候选。当前实现先
要求矩阵有限、逐元素严格对称，再以 Gershgorin 下界证明严格正定，并要求该下界高于
`rcond=1e-15` 与谱范数保守上界的乘积。未认证矩阵不做任何预拒绝，全部进入旧精确 `pinv`。

已认证矩阵的所有奇异方向均不会被截断，伪逆等于通常逆。最大绝对行和给出谱范数上界，因此
`||d||^2/U` 是原马氏距离的保守下界。只有该下界在数值安全裕量后严格超过原门限，候选才可
跳过伪逆。该过程没有放宽门限，也没有改变 Hungarian 分配。

### 31.2 反例与业务等价

第一类反例为带负特征值的交叉协方差，差向量沿负特征方向；第二类为
`diag(1e12, 1, 1e-20)`，差向量沿被 `pinv` 截断的近零方向。两例的旧伪逆代价均不超过关联
门限，而朴素 trace 比值超过门限。新认证均返回 false，rejection mask 全 false。扫描级回归
进一步确认参考和候选对全部候选执行同数目的精确求解，后验、协方差和摘要完全一致。

### 31.3 基准结论与开放项

clean `8f86192` 的 10 s seeds 42000-42002 中，参考/候选纯融合墙钟均值
`91.313/88.619 s`，3/3 candidate 更快，聚合加速 `1.030x`。精确创新求解合计
`7,130,228 -> 1,578,677`；逐扫描后验、终态航迹和一致性证据哈希全部相同，完整/状态快照
计划及 fixed-lag 操作数保持。专项 `6 passed`，D1 全量 `175 passed in 26.69s`。

评审结论为 D1-owned 数学等价边界和当前冻结输入优化均通过。10 s 输入仍平均耗时 88.619 s，
实时预算未关闭。后续 P1 是固定硬件多 seed/长时周期、真实异常协方差认证/回退比例、正式
RMSE/NEES/NIS 和 AirSim 独立验收；不继续放宽预门控条件。

## 32. 最终 integrated 三 seed 评审（2026-07-22）

### 32.1 证据范围

参考提交 `8f86192` 与候选提交 `f80b5bd` 分别从 clean 工作区运行相同的
`200v200-nominal-v1` 10 s 场景。seeds 42000、42001、42002 的 D1 终态航迹数在两条路径均为
`202/207/203`，所有状态有限，在线 truth 使用为 0。

逐条语义审计同时覆盖 D1-D7 和运行时 ACK。D3 独立运行产生的不透明 `plan_id` 按 occurrence/
version 归一化；ACK 原始载荷 SHA 在归一化前独立验证。计划 owner/version/coalition、规范
`global_track_id`、command 及其余业务字段没有被移出比较。三组审计全部通过，D1 fused-track
主题规范哈希逐 seed 一致。

### 32.2 性能判断

| 指标 | 参考 `8f86192` | 候选 `f80b5bd` | 变化 |
| --- | ---: | ---: | ---: |
| D1 fusion 三 seed 累计耗时均值 | 92.991088 s | 88.330438 s | -5.01% |
| D1 scan input 三 seed 累计耗时均值 | 16.902643 s | 17.524242 s | +3.68% |
| 精确创新求解总数 | 7,130,228 | 1,578,677 | -77.86% |

精确创新求解次数只反映 certified radar pre-gating 跳过的伪逆工作量，不代表定位精度或业务
质量。未通过有限性、严格对称、Gershgorin 正定和 `pinv` cutoff 认证的矩阵仍走原精确 fallback。
scan input 没有改善，当前系统也未达到实时，长时归一化比较仍把 D1 scan input、D1 fusion 和
module stack 列为超线性项。

### 32.3 评审结论

当前三 seed 的 D1 集成业务等价项关闭。系统实时、长时归一化超线性、真实异常 covariance
认证/回退分布、AirSim 和正式 RMSE/NEES/NIS 保持 P1 开放。下一轮不得通过放宽预门控认证、
缩短固定时滞、丢弃观测或改变双时间戳语义换取吞吐。

## 33. GlobalTrack 共享审计元数据准入评审（2026-07-24）

### 33.1 评审判断

当前热点来自 `_to_global_track()` 对扫描级公共审计树的逐航迹复制。候选将 association、
latency 和 sensor-health 递归冻结后按扫描共享。轨迹顶层 metadata、state、covariance、
source support、association diagnostics 和 identity likelihood 仍独立。该边界没有进入雷达
关联、固定滞后重放、航迹分级或观测处理。

首个 v1 使用 `dict/list` 只读子类。常规写入虽然失败，调用者仍可用基类方法直接修改底层
容器；D2 也无法把该表示与任意自定义 Mapping 严格区分。v2 改用无实例存储的
`frozenset` 键值对和 tuple 序列精确类型，并提供递归验证 API。验证器不接受 marker、自定义
Mapping、可变代理、容器子类、循环树和
不支持叶值。下游仍需对每个新对象执行一次内容级 truth-free 审计，合同本身不声明内容可信。

### 33.2 证据

冻结 seed 1101 输入 SHA-256 为
`8ece10afc86eb426ac1810f4fff9a22860cdceea1ae2a71d0b30413f20c09fed`。570 扫描、
10,810 条匿名观测、361 次完整发布和 71,515 条航迹物化均保留。reference/candidate 的完整
逐发布字典摘要、逐扫描融合语义、操作数、累计诊断、终态和 consistency evidence 全部一致。
共享审计映射复制 `8,832,271 -> 0`；`_to_global_track` 累计
`10.700 -> 2.198 s`，fusion 总墙钟 `42.282 -> 34.792 s`。

### 33.3 v1 决策

v1 后续已完成同一 clean 提交的 frozen short 10 seed、long 3 seed 正式矩阵。D1 fusion wall
改善 16.29%/31.05%，D2 association 增加 53.44%/169.89%，核心墙钟只改善
1.65%/1.21%，低于预注册 5% 门。v1 判定不准入。回退来自 D2 对 v1 自定义容器逐航迹重复
递归审计，不是 D1 数值或业务语义变化。

当前模块候选 ID 已升级为 `d1.publication_metadata.immutable_shared_audit.v2`，默认值继续为
`False`。D1 新增合同
专项覆盖公开变异方法、基类绕过、伪造/非法树、共享身份、JSON、pickle 和深拷贝；全量
`389 passed in 20.84s`。旧 v1 证据和输出目录未复用为 v2 准入。

### 33.4 v2 正式准入

正式矩阵从 clean source commit
`be399e138762f5e660f553c8caa812d52ab38c61` 运行。场景为 200 目标、200 资源和 2 个侦察
节点；short 使用 seeds 1101-1110、2.2 s，long 使用 seeds 1101-1103、10 s。13 对
reference/candidate 共 26 个 arm 全部重新执行，`0 reused/0 failed`。13/13 业务语义、有限
状态、在线真值隔离、实际实现身份、D2 审计和 RSS 门通过。

| 指标 | Short | Long | 预注册门限 | 评审 |
| --- | ---: | ---: | ---: | --- |
| D1 fusion 改善 | 13.5447% | 26.8298% | >=10% | 通过 |
| 核心墙钟改善 | 6.5677% | 18.2438% | >=5% | 通过 |
| D2 association 耗时变化 | -16.1939% | -35.6213% | 回归 <=5% | 通过 |

D2 对候选累计执行 702 次 v2 合同验证、702 次 truth-free 内容审计和 139,920 次同一强引用
对象身份复用，合同拒绝为 0。D6 结论为 `d1_optimization_admitted=true`。正式报告目录为
`research_modules/d6_evaluation_metrics/outputs/`
`d1_publication_metadata_v2_multiseed_20260724_formal_be399e1/`。

### 33.5 当前默认与剩余项

D1 模块自身布尔构造默认仍为 `False`，供独立调用方保持 reference。main promotion commit
`f5b350b` 已把可扩展三维仿真的默认 selector 晋级为 `immutable_shared_v2`，并保留
`per_track_copy_v1` 显式对照。因此“模块构造默认 reference”和“系统集成默认 v2”同时成立。

候选最低实时因子为 `0.1730801`，`system_realtime_gap_closed=false`。后续 P1 包括系统实时
容量和逐批 D2 审计明细。本次正式证据不含 AirSim、目标硬件、RMSE、NEES、NIS 或物理拦截，
不得外推为相应验收结论。

## 34. 匀速模型精确有界缓存准入评审（2026-07-24）

### 34.1 评审边界

候选只复用由精确 `(dt, process_noise)` 决定的状态转移矩阵与过程噪声矩阵。缓存采用有界
最近最少使用淘汰，容量固定为 128；矩阵只读。每条航迹的状态和协方差传播、固定滞后重放、
量测更新、关联、发布、正半定治理、双时间戳、NED 和来源谱系继续逐次执行。

正式 reference/candidate 为 `per_prediction_build_v1/bounded_exact_lru_v1`，实现 ID 分别为
`d1.fusion.cv_motion_model.per_prediction_build.v1` 和
`d1.fusion.cv_motion_model.bounded_exact_lru.v1`。D1 `FusionAdapter` 的布尔默认保持
`cached_cv_motion_model=False`。该默认服务独立调用兼容；main 集成默认已晋级为
`bounded_exact_lru_v1`，并通过 scalable 3D 全量 `212 tests`。

### 34.2 正式证据

正式矩阵绑定 clean source commit
`44223566439a446fc49f2a3fd861d1d51bd676b9`，矩阵 SHA-256 为
`9898656598f0fa282620afe2384a3d656b7496f8957109c413bcb62069fd2e9a`。场景为 200 个目标、
200 个资源和 2 个侦察节点。short 使用 seeds 1101-1110、每组 2.2 s；long 使用 seeds
1101-1103、每组 10 s。13 pair 对应 26 个全新 arm。

13/13 pair 的业务语义、有限状态、在线真值隔离、显式实现身份和缓存审计全部通过。正式
D6 报告目录为
`research_modules/d6_evaluation_metrics/outputs/`
`d1_cv_motion_model_cache_multiseed_20260724_formal_4422356/`。

| 指标 | Short | Long |
| --- | ---: | ---: |
| D1 fusion reference | `3.289739 s` | `23.304548 s` |
| D1 fusion candidate | `3.061518 s` | `21.776847 s` |
| 逐 pair 改善 | `6.9271%` | `6.6103%` |
| candidate 更快 | `10/10` | `3/3` |
| 核心墙钟改善 | `2.4060%` | `2.4537%` |
| D2 association 变化 | `-0.1082%` | `-2.6729%` |
| RSS 均值增幅 | `0.0145%` | `0.2959%` |

short D1 fusion 配对原始相对变化的 bootstrap 95% 区间为
`[-7.7968%, -6.0841%]`。全部 pair 的 RSS 最大增幅为 `0.8629%`。

### 34.3 缓存守恒

两臂均记录 896,820 次预测请求和 21,789 次非正时间差 reference bypass。reference 在
875,031 次正时间传播中构造模型。candidate 构造 3,535 次、命中 871,496 次；miss 与构造
均为 3,535，模型构造减少率和命中率均为 `99.5960%`。每个 arm 的当前条目和峰值条目均不
超过 128。

这些计数证明候选只消除了相同精确键的重复矩阵构造。它没有减少预测请求，没有把非正时间差
改成传播，也没有通过量化时间差提高命中率。

### 34.4 结论与开放项

D6 判定 `d1_optimization_admitted=true`。D1 匀速模型缓存的模块实现与正式全栈准入 P1
关闭。候选最低实时因子为 `0.1739499`，未达到系统实时门限 1.0，因此
`system_realtime_gap_closed=false`。

继续开放的 P1 为 AirSim 运行证据、目标硬件周期与内存、长时容量、融合均方根误差
（RMSE）、归一化估计误差平方（NEES）、归一化创新平方（NIS）和系统实时性。本次正式准入
不得被表述为这些项目已经验收。

## 35. 真值隔离质量基准

### 35.1 本轮完成

D1 已实现独立的 200 目标质量基准。在线扫描覆盖漏检、虚警、密集交叉、遮挡和 OOSM，
只携带匿名源谱系。离线 sidecar 保存真值轨迹和谱系映射，不进入融合器。评分器以融合器实际
接受的源观测谱系对齐真值，不用真值位置辅助在线关联。

输出指标覆盖暖机召回率、重复航迹率、混合谱系率、虚假航迹数量和寿命、位置 RMSE、NEES、
NIS、航迹数量增长、单扫描 P50/P95 和谱系覆盖率。不可用指标不能补 0。该基准没有修改
`FusionAdapter`、关联门限、滤波器、生命周期或 D2 规范身份。

### 35.2 验证

- 5 目标快速夹具：seeds 2000-2019，20/20 完成，共评分 248 条唯一接受观测，谱系覆盖率
  1.0；
- 200 目标短时冒烟：seed 1000，3 个发布帧，201 条终态航迹，164 条 OOSM 观测，暖机召回
  0.8183，共评分 532 条唯一接受观测，谱系覆盖率 1.0；同日重复开发运行的处理 P95 为
  166.41--310.96 ms，不作为门限；
- 专项 `8 passed`，D1 全量 `496 passed in 33.19s`；
- 在线真值使用和 D2 规范身份写入均为 0。

### 35.3 后续

最高优先级仍是 200 目标、20 个未见 seed 的长时正式矩阵。先测清漏检、虚警和交叉条件下的
召回、重复、混轨、虚假航迹寿命、RMSE、NEES、NIS 和尾延迟，再决定是否增加航迹生命周期。
当前短时结果不能关闭该 P1，也不能作为 AirSim 或目标硬件能力结论。
