# 200 对 200 三维质点仿真实施计划

## 正式输出无损迁移准备（2026-07-26）

1. [x] 新增 `artifact_archive.py`，提供 `inventory`、`copy` 和 `verify` 三个命令。
   工具逐文件计算 SHA-256、文件数、总字节和树摘要，拒绝符号链接、特殊文件、源内目标、
   已存在目标和根目录额外文件。
2. [x] `copy` 先冻结源清单，经临时目录复制后复核 payload，并再次复核源在复制期间
   未变化；全部通过后才原子发布归档目录。
3. [x] 归档 manifest 固定声明 `source_preserved=true` 和
   `deletion_performed=false`。工具不提供删除命令。只有 `verify --source` 再次证明源与
   归档逐文件一致时，报告才给出 `source_deletion_eligible=true`。
4. [x] 专项测试覆盖确定性清单、原子复制、payload/manifest/source 篡改、源内目标、
   已存在目标、根目录额外文件和符号链接拒绝，结果为 `12 passed`。
5. [ ] 用户提供外部归档目录或扩容文件系统后，对现有正式 R0 和必要训练证据执行复制及
   双端复核。当前不移动、不压缩、不删除任何既有输出。
6. [ ] 只有归档报告、源清单和带外 SHA-256 均保存后，才单独申请删除可重建开发输出或
   已迁移源目录的授权。未经授权不得降低 20 GiB 正式运行保护下限。

## 证据装配实施收尾（2026-07-26）

1. [x] D3 已关闭 production 自我准入。调用方构造的 qualified admission 在写文件前
   被拒绝；手工正向 v3 manifest 返回
   `bundle_assist_evidence_assembler_unavailable`。现有 development/shadow bundle
   未修改。
2. [x] D4 复核未发现新的自我晋级 P0。A2 模块专用 evidence assembler 仍等待实际采用、
   物理窗口、同键 R0 和成对非退化证据，保持 P1。
3. [x] D6 已实现 D5 G1 外部预准入审计，并将 G1 assembler 纳入当前实现摘要
   `41381db3...94b07`。审计只给出证据结论，不授予模型晋级、默认路径或控制权限。
4. [x] D5 已实现 G1 evidence assembler。正向 fixture 可以原子生成并由 strict
   loader/runtime 加载 v4；该 fixture 只验收合同。A3 assembler 仍未实现。
5. [x] 使用当前 `99fa4428...d4cd` 模型执行 post-assembler 审计。结果为
   `fail_closed`，assembler 退出码为 2，未创建目标 bundle。五项 blocker 为实现证据
   不可用、实现谱系不一致、困难扰动 cluster/edge F1 未达到 `0.9`，以及单特征曲线下面积
   `0.997340` 超过 `0.98` 上限。
6. [x] 没有调整阈值、兼容白名单、旧 bundle、manifest 或权重；没有运行正式学习
   episode。G1、A1、A2、A3、C1、F1 继续失败关闭。
7. [ ] D3 在实际 A1 采用确认、物理结果和同键 R0 非退化证据齐备后实现模块专用
   assembler，形成新的 immutable bundle。
8. [ ] D4 在实际 A2 隔离采用与成对非退化证据齐备后实现模块专用 assembler。
9. [ ] D5 使用当前实现重新形成无单特征捷径、困难扰动达标的 G1 模型证据并通过 D6
   外部审计；另行实现 A3 assembler。
10. [ ] 只有模块预准入通过后，main 才按 G1、A1、A2、A3、C1、F1 启动正式 scope，
    D6 再审计逐 cell 实际采用、物理结果和唯一同键 R0 非退化。

## 学习变体 assist 准入预检（2026-07-26）

1. [x] D3 关闭旧 `d3_learning_model_bundle_v2` 仅凭 promotion 字段进入 assist 的
   兼容缺口。v2 继续可用于 development shadow，assist 固定返回
   `bundle_assist_admission_missing`；只有带独立正向准入和哈希绑定 promotion 的新 v3
   才可能进入 assist。
2. [x] D4 将现有 `d4-region-resource-model-bundle-v2` 固定为
   development/shadow-only。writer 在创建目录和写权重前拒绝自声明
   `qualified/assist`，无 manifest 的注入策略也不能取得 assist 权限。
3. [x] D5 将模型完整性、解析能力和 G1/A3 使用权限分离。main 加载图模型时固定要求
   `require_g1_assist_eligible=True`；development scorer 即使可读也不能影响集成在线
   关联。
4. [x] D5 主审进一步关闭裸报告自声明。G1 和 A3 的 production writer 均拒绝调用方
   直接提供正向 admission report；公开 loader/runtime 也拒绝手工拼装的 admitted
   manifest。此后 G1 已增加独立装配器；A3 仍只有私有合同测试和失败关闭边界。
5. [x] 旧 D3、D4、D5 图模型和 D5 主动视觉 bundle、manifest、权重均未修改或重算。
   旧冻结 D5 bundle 因实现文件集合变化继续返回
   `bundle_implementation_runtime_mismatch`，不得设置兼容白名单。
6. [x] 使用当前实际 bundle 进行无 episode 写盘预检。G1、A1、A2、A3、C1、F1 全部
   fail-closed；R0 不加载模型，现有正式 R0 execution plan 和 135/900 进度未被读取、
   改写或重新生成。
7. [x] main 已为 G1/A1/A2/A3/C1/F1 增加与 R0 同级的可恢复分片基础设施。
   `init-scope` 绑定完整 bundle 文件树、manifest、预检设备、准入诊断和模型版本；
   `run-shard` 在写 shard 前、每个学习单元开始前和发布前复核绑定，单元发布后再次核对
   episode 诊断与版本；
   `merge-scope` 复用确定性合并合同。旧 R0 计划保持可读。
8. [x] G1 开发伪 bundle 已完成缺失/未准入拒绝、设备不一致、文件篡改、暂停恢复和合并
   回归。矩阵/分片/学习运行时定向测试为 `26 passed, 1 warning`，scalable 全量为
   `292 passed, 1 warning`。
9. [x] D6 已实现可选、只读的
   `d6.learning-scope-formal-evidence-audit.v1`。审计重新校验 execution plan、bundle
   文件树、merge、shard plan、progress、checkpoint、cell result 和 episode 文件树；
   shadow、规则回退、仅加载模型、零候选边、缺物理结果或缺唯一 R0 配对均失败关闭。
10. [x] D6 审计要求每个必要组件有正实际采用证据：D3 学习修正应用计数、D4 建议进入
    控制计数、D5 图模型正候选边评分、D5 主动视觉采用及运行确认。审计输出 JSON、逐
    cell CSV、中文 Markdown 和 SHA256SUMS，但始终保持
    `model_promotion.allowed=false`。
11. [x] 最新 owner 全量回归为 D3 `465 passed, 1 skipped`、D4 `569 passed`、D5
    `571 passed`、D6 `944 passed, 1 warning`。D3 跳过项为未安装的可选 OR-Tools；
    warning 为既有 Matplotlib `Axes3D` 环境提示。
12. [ ] 预准入阶段仍需为 D3、D4、D5 图模型和 D5 主动视觉分别形成新的、可验证的
    holdout/paired-shadow/隔离采用证据。D5 G1 装配器软件已完成，但当前模型因五项
    blocker 失败关闭；D3、D4 和 A3 装配器仍未实现。生产路径不能生成或执行未经外部
    证据约束的 admitted bundle。
13. [ ] 各 owner 形成新 admitted bundle 后，main 才能冻结学习 scope。预准入证据与
    scope 后验审计不得混用：前者只决定是否允许启动，后者只评价实际采用和相对 R0
    非退化，不反向授予模型权限。
14. [ ] R0 完整闭合、存储条件满足且模型获准后，按 G1、A1、A2、A3、C1、F1 顺序运行
    正式 scope。当前实际模型全部未获 assist 准入，正式学习 episode 仍为 0。

## 正式 R0 后验收尾 P0（2026-07-25）

1. [x] clean commit `2c7b425` 的 20 个 R0 分片全部完成，900/900 单元写盘并确定性合并；
   scope 完成，完整 5700 单元矩阵未完成。
2. [x] D6 首轮评估给出 895 个 clean-formal 单元和 5 个后验代次失败单元。失败集中在
   `delayed_noisy` 5v5 seeds 1000/1005/1008/1018 与 20v20 seed 1009。
3. [x] main 确认根因是 finalize 简化签名遗漏状态有效时刻、状态和协方差，并在签名相同
   时跳过 D2 调用后清空 pending generation。
4. [x] main 改为最后 D1 后验必须实际进入 D2，且仅在 D2 成功发布后清空 pending；
   D2 replay-coast 负责隔离重复来源证据，D7 控制公式不变。
5. [x] 五个原失败单元完成开发态定向复跑。D6 generation contract 为 5/5 verified，
   skip=0、pending empty、在线真值使用为 0；scalable/D2/D6 全量分别为
   `285/305/894 passed`。
6. [x] main runtime、D1/D2 审计和 D6 v10 已按子系统分批提交：
   `4b018e4`、`dc5821f`、`8e955f3`、`98d01bf`。提交历史未改写；最终文档同步完成后，
   再以新的 HEAD 冻结完整父计划与 R0 execution plan。
7. [ ] 在不删除或改写现有正式证据的前提下解决存储容量。当前可用约 24 GiB，现有正式
   R0 约 22 GiB，旧失败现场约 1.2 GiB；新一轮仍需约 22 GiB，并保留 20 GiB 运行下限。
8. [ ] 使用新 clean source 从零重跑 900 个 R0 单元，由 D6 v10 验证 900/900
   clean-formal。不得将修复后的 5 项与旧提交的 895 项拼接。
9. [x] 最终正式 source 已冻结为 `1e5ed8d`，execution plan SHA-256 为
   `8804ecb4dd0513db55906905f031832711012974fc911546df40e09fb297d373`。
   shards 0、5、9 已完成，共 135/900 单元。
10. [x] D6 v10 对新批次中三个原失败 cell 给出 3/3 clean-formal、formal eligible 和
    generation verified；seeds 1008/1018 尚未重跑。可用空间只比 20 GiB 下限多约
    65 MB，后续分片等待证据迁移、扩容或明确清理授权。

## D4 因果通信与正式矩阵准入状态（2026-07-25）

1. [x] main 新增 D4 点对点通信意图，将二级就绪、区域计划广播和联盟成员确认通过
   `DeterministicCommunicationNetwork` 传输，不再使用同 tick 合成送达。
2. [x] D4 收据校验绑定 source/destination、plan version、epoch、lease、分区代次、
   payload digest 和 message ID；关闭通信时中心失效场景保持失败关闭。
3. [x] D4 owner 将无确认和部分确认保持为 `collecting_acks`，完整确认原子提交；分区、
   摘要冲突、租约到期、成员不可执行和显式终结仍失败关闭。
4. [x] main 完成 2 目标、4 资源、单目标 3 成员的异步网络集成回归；二级计划发布后，
   `2.05 s` 未确认时 D7 保持，`2.10 s` 三个确认到达后仅两架主机执行，备用机待命。
5. [x] main 修复区域内不同任务提交租约未统一收紧的问题，下一规划周期不再产生
   `regional_coalition_lease_exceeds_authority` 虚假拒绝。
6. [x] 保留种子干预框架区分故障代次栅栏、前一计划 D4 裁决和下一版本 D3 采用；连续
   中心/二级失效窗口延长到足以覆盖广播和确认往返。
7. [x] D4 全量 `569 passed`，scalable 模块栈 `66 passed, 1 warning`，scalable 全量
   `272 passed, 1 warning`；warning 为既有 Matplotlib 三维投影导入提示。
8. [x] D6 使用实际 formal 计划完成静态 `post_run` 预检：expected=`5700`、
   accepted=`0`、verdict=`fail_closed`。
9. [x] clean commit `2c7b425` 已完成 20 个各 45 单元的可恢复 R0 分片，并形成 scope
   manifest、逐 cell 清单和 D6 报告。首轮 D6 为 895/900 clean-formal；该批次保留为
   后验收尾 P0 的正式失败证据，不能作为最终 R0 acceptance。
10. [ ] D3、D4、D5 图模型和 D5 主动视觉模型保持 development/shadow；未通过独立非退化
    门前，不允许以模型哈希有效代替 assist 准入。
11. [ ] 完成 R0 后再决定 G1/A1/A2/A3/C1/F1 的运行顺序；每一学习变体缺正式模型权限时
    必须失败关闭，不用规则静默补齐 formal 单元。
12. [ ] 200 对 200 系统实时、完整 20 个未见 seed、AirSim 代表子场景和冻结目标处理器
    容量仍为开放 P1。
13. [x] D1、D3-D7 owner 完成收尾复核和文档同步。D1 修正唯一观测谱系统计，D3 修正
    `cost_weights` 对称接线，D6 修正非法 D4 保留种子字段失败关闭，D7 修正 pair 状态
    回收顺序和重复资源输入检查。
14. [x] 最新模块回归为 D1 `496 passed`、D3 `464 passed, 1 skipped`、D4
    `569 passed`、D5 `552 passed`、D6 `889 passed, 1 warning`、D7 `220 passed`；
    修正后的统一模块栈为 `66 passed, 1 warning`。
15. [x] 已冻结可恢复分片与确定性合并合同。完整父 inventory 保持 5700 个
    R0-G1-A1-A2-A3-C1-F1 单元，R0 scope 为 900 个；默认 20 片，每片覆盖一个保留 seed
    的 9 场景 × 5 规模。单元原子发布、进度追加、checkpoint 滞后恢复、文件树摘要和篡改
    拒绝均已测试。
16. [x] R0 scope 合并产物明确记录 `formal_scope_complete` 与
    `formal_matrix_complete=false`。只有 scope 等于完整父 inventory 时才生成完整矩阵
    manifest，多个非正式子计划不能拼成正式证据。
17. [x] 分片专项现有 8 项，scalable 全量 `280 passed, 1 warning`；真实单 episode
    分片写盘确认有限状态、在线真值使用为 0 和 D6 truth-isolated 子目录存在。新增低磁盘
    暂停与恢复测试，不改变单元内容和顺序。
18. [x] 在 clean detached worktree 初始化绑定 `32b3b40` 的正式 R0 execution plan。
    shard 0 已完成 44/45 单元，最后一个 high-threat 200v200 单元暴露 D3 旧联盟需求与
    当前需求不一致异常。该执行目录固定保留为失败证据，修复后不得续跑或混合产物。
19. [x] 分片运行器增加 20 GiB 默认可用磁盘下限。每个新单元启动前检查空间，低于下限
    时在完整单元边界暂停并写 checkpoint；恢复后继续使用同一追加式进度账本。
20. [x] D3 owner 已关闭联盟需求变化代码 P0：不兼容旧需求库存不再进入迟滞保持，同需求
    保留和过分配失败关闭不变；D3 全量为 `464 passed, 1 skipped`，同配置开发复验通过。
21. [x] main 绑定 clean commit `2c7b425` 生成新 execution plan，从 shard 0 零开始运行；
    原 high-threat 200v200 单元通过。
22. [x] 20/20 分片和 900/900 R0 scope 已完成并执行
    `merge-r0 --write-d6-report`；D6 随后发现五项 finalize 后验未消费，故 formal
    acceptance 仍失败关闭。
23. [ ] 完成上节后验收尾修复的分批提交和存储安排后，使用新 clean commit 与新 execution
    plan 整体重跑 900 单元。

## D1 在线发布证据子集快照候选（2026-07-25）

### 问题与隔离边界

1. [x] 前一候选
   `fixed_lag_checkpoint_prefix_cumulative_summary_v1` 已由 D6 正式判定
   `reject`，本候选不得修改其 clean commit、matrix SHA、门限或正式制品。
2. [x] 新 treatment 独立命名为
   `d1_publication_evidence_snapshot_implementation`。参考路径为
   `full_consistency_snapshot_v1`，候选为
   `required_observation_subset_v1`；第一轮 A/B 的两臂均保持 D1 回放
   `per_checkpoint_prefix_rebuild_v1` 默认，禁止一次改变两个 selector。
3. [x] publication 所需 observation ID 仅来自同一 release cycle 内：
   当前源扫描的全部观测 ID，以及每个已物化公开航迹的
   `latest_observation_id`。集合去重后按字符串排序，不读取真值、目标真实编号或
   D6 标签。
4. [x] 候选只把上述 ID 集合传给 D1 已有的精确非破坏性
   `consistency_evidence_snapshot(observation_ids)`；最终离线导出继续使用全量
   `consistency_evidence_records()`/`export_consistency_evidence()`。
5. [x] 未知、空、跨所有权或不完整 ID 不得静默丢弃。集成路径回退
   `full_consistency_snapshot_v1` 并记录 fallback 原因；正式准入要求 fallback 为 0。

### 实现与诊断

6. [x] main 增加显式 selector、实现 ID、执行配置和诊断 schema，并贯通 runtime
   profile、observation governance、module final 和 episode summary。
7. [x] 诊断记录 snapshot 调用数、release/publication 数、源观测引用数、航迹最新
   观测引用数、去重后的 required ID 数、返回记录数、lookup miss、fallback 及原因。
8. [x] 3 对 3 定向 episode 中，`_d1_publication()` 的 fused track、summary、lineage、
   双时间戳、协方差、`global_track_id` 和完整 payload 与参考路径一致；新诊断未进入
   业务 payload。
9. [x] `run_episode.py` 提供显式 CLI；默认保持
   `full_consistency_snapshot_v1`，不能在正式准入前静默启用候选。
10. [x] 单元测试覆盖默认值、非法 selector、CLI、重复 ID、未知 ID 回退、正常 episode
    业务语义和四表面诊断；`test_module_stack.py` 为 `62 passed`，scalable 全量为
    `263 passed, 1 warning`。空集合回退 full 的 main 专项已覆盖，clean smoke 前不声称
    该边界已有 200/200/2 证据。

### 预注册准入

11. [x] clean `028ac34`、seed 1151 的 200/200/2 单 pair smoke 确认 D1/D2 在线记录
    SHA、consistency digest/count 和原 D1 操作计数一致；candidate 14/14 子集成功，
    fallback/lookup miss/非法或空 required 均为 0，返回记录由 `13679` 降至 `4429`，
    减少 `67.621902%`。性能方向混合，只允许进入矩阵预注册。
12. [x] 已冻结
    `configs/d1_publication_evidence_snapshot_multiseed_v1.json` 及新的
    matrix/evidence/evaluator schema。short seeds 1151-1160、long seeds
    1151-1153、200/200/2；两臂唯一 treatment 为发布证据快照 selector，回放前缀保持
    reference。运行器定向测试为 `63 passed`，并能重新校验 clean smoke 两臂。
13. [x] 正式门预注册为：13/13 业务语义及原 D1 操作计数一致；候选 fallback 和 lookup
    miss 均为 0；返回记录数减少至少 50%；short/long 候选更快数至少 8/10 和 2/3；
    D1 fusion 改善至少 1%；core wall 改善至少 0.25%；D2 和 RSS 均值增幅不超过 5%。
14. [x] clean `d0219eb` 上完成 13 对/26 个 fresh episode，0 reused、0 failed。D6 独立
    确认 13/13 语义与原操作计数一致、429/429 子集成功、0 fallback/lookup miss，返回记录
    削减 `91.641524%`；但 short 仅 `4/10` 更快、D1 改善 `-0.147877%`、bootstrap
    上界 `1.374681%`，正式判定 `reject`。reference 保持默认。候选最低实时因子
    `0.203423 < 1`，系统实时以及 AirSim、目标硬件和实飞证据继续独立开放。

## D1 固定滞后回放前缀摘要准入（2026-07-25）

1. [x] D1 owner 提供 `per_checkpoint_prefix_rebuild_v1` 参考实现和默认关闭的
   `fixed_lag_checkpoint_prefix_cumulative_summary_v1` 候选。
2. [x] 候选仅对完整、可信且 revision 一致的 checkpoint 前缀复用不可变摘要；任何
   schema、身份、顺序、配置或前缀不一致均回退参考路径。
3. [x] consistency evidence 使用延迟区间账本；在线 publication 通过精确非破坏性
   snapshot 读取，写前、失效、fixed-lag 重基准和 episode 最终导出前精确物化，不省略
   replay count 或 revision。
4. [x] D1 全量 `488 passed`；D1 owner 的冻结 7-pair 微基准为 7/7 更快，中位改善
   `35.494%`，全部语义等价门通过。
5. [x] main 接入 selector、完整实现 ID、执行配置和诊断，并贯通 runtime profile、
   observation governance、module final 和 episode summary。
6. [x] 冻结 `configs/d1_replay_prefix_summary_multiseed_v1.json`：short seeds
   1151-1160、long seeds 1151-1153、200 个目标、200 个资源、2 个侦察节点。
7. [x] 预注册 consistency evidence records digest、原有操作计数、D1/core/D2/RSS、
   bootstrap、实现身份和延迟物化压缩率门。
8. [x] dirty seed 1151、2.2 s 集成预检确认 consistency digest 与原有操作计数相同，
   最终 pending 为 0，append 物化为 0，内部记录物化压缩率 `79.452%`；该结果只用于
   提交前排错。
9. [x] 在 clean `7d2e987` 上完成单 pair smoke 和 13 对/26 episode 正式矩阵；
   200/200/2 两臂均为 fresh，0 reused、0 failed，matrix SHA-256 为
   `85432d729877eff97e6f3dd517d4baa7a47f44a4fa42e6bfdc7ce85b8d9ec74b`。
10. [x] D6 owner 独立读取原始 episode 并完成失败关闭评估；13/13 业务语义、
    consistency digest/count、原 D1 操作计数、实现身份、诊断守恒和真值隔离通过。
11. [x] D6 正式判定 `reject`：short 更快 `5/10 < 8/10`、D1 fusion 改善
    `0.959611% < 1%`、bootstrap 上界 `0.619827% > 0%`、core 改善
    `-0.256641% < 0.25%`，long core 改善 `-1.930083% < 0.25%`。
12. [x] main 保持 `per_checkpoint_prefix_rebuild_v1` 为默认；候选只保留为显式研究
    路径，不修改冻结矩阵、门限或正式制品。重复 D6 评估与正式 bundle 全文件摘要一致。
13. [ ] 系统实时 P1 保持开放：候选最低实时因子 `0.197441 < 1`，在线 snapshot 仍投影
    构造 `656481` 条记录；本证据不覆盖 AirSim、冻结目标处理器、硬件、实机或实飞。
14. [ ] 如继续优化，只评估按 publication 所需观测标识投影 snapshot 的新候选；必须使用
    新 implementation ID 和新预注册矩阵，不能改写本次 `reject` 证据。

## D1 关联稀疏预筛正式拒绝（2026-07-25）

1. [x] D1 owner 提供 `disabled_v1` 参考路径和默认关闭的
   `modality_conservative_quadratic_bound_v1` 候选；无法认证、奇异或非有限输入继续
   fail-open 到原精确求解。
2. [x] main 将 selector、完整实现标识、执行配置和
   `d1.association_sparse_prefilter_diagnostics.v2` 接入 runtime profile、summary、
   module final 和 observation governance。
3. [x] 冻结 10 对 short、3 对 long 的同提交 200/200/2 矩阵；两臂只改变预筛
   selector，matrix SHA-256 为
   `a7162d014d1c3c0f207355b24a5d7159bf3486d134ca21876f7469d1e915b71d`。
4. [x] clean `9302cce` 上完成 13 对/26 个 fresh episode，0 reused、0 failed；
   D6 独立重算业务语义、逐模态精确门内计数、性能、D2、RSS 和真值隔离。
5. [x] 13/13 对业务语义、有限状态、实现身份、预筛审计、在线真值使用为 0，以及逐
   pair/逐模态 exact gate-pass 相等全部通过。
6. [x] 候选将非雷达精确求解由 `298109` 降至 `39837`，削减
   `86.636767%`；该结果只证明局部计算被消除，不等同于全栈收益。
7. [x] D6 正式判定 `reject`：short 更快 `7/10 < 8/10`、D1 fusion 改善
   `0.228437% < 1%`、bootstrap 上界 `0.443531% > 0%`、core 改善
   `0.091096% < 0.25%`，long D1 fusion 改善 `0.713776% < 1%`。
8. [x] main 默认保持 `disabled_v1`；候选只保留为显式研究和诊断路径，不修改冻结
   矩阵、门限或历史正式制品。
9. [ ] 系统实时 P1 保持开放：候选最低实时因子 `0.206273 < 1`；本证据不覆盖
   AirSim、冻结目标处理器、硬件、实机或实飞。
10. [ ] 如继续优化，应先画像逐 pair 下界计算、EO fail-open 和 D1 其余阶段的实际占比，
    再判断是否把保守下界前移到更粗粒度候选生成；任何重新准入必须使用新预注册矩阵。

## D1 在线批帧交接准入（2026-07-25）

1. [x] D1 owner 提供 `convert_then_frame_v1` 参考实现和
   `closed_immutable_batch_to_frame_v1` 封闭不可变批帧候选。
2. [x] main 冻结 10 对 short、3 对 long 的同提交 200/200/2 矩阵；两臂只改变批帧
   selector，并保留完整在线身份检查和最终只读帧检查。
3. [x] clean `43feaf6` 上完成 13 对/26 个 fresh episode，0 failed；D6 独立读取原始
   episode 重算业务语义、守恒、性能、D2 和 RSS 门。
4. [x] 13/13 对业务语义、有限状态、在线真值隔离、实现身份和批帧审计通过；候选
   2665/2665 次请求均闭合交接，fallback 为 0。
5. [x] short/long scan input 改善 `38.289241%/36.275282%`，核心墙钟改善
   `4.252745%/4.916501%`，全部预注册 gate 通过。
6. [x] main 默认晋级为 `closed_immutable_batch_to_frame_v1`；
   `convert_then_frame_v1` 保留为显式回退，不修改冻结矩阵和历史证据。
7. [ ] 系统实时 P1：候选最低实时因子 `0.204490 < 1`，不能将局部准入写成 200 对
   200 实时达标。
8. [ ] D2 尾部容量观察：`long_seed_1121` 单对 association 增幅
   `14.408510%`，虽未使预注册组均值门失败，后续长时容量矩阵继续保留该风险。
9. [ ] AirSim、冻结目标处理器和实飞证据另行验收，不从本次三维质点结果继承。

## D1 不透明来源标识缓存准入（2026-07-25）

1. [x] D1 owner 提供 `per_publication_build_v1` 参考实现和默认关闭的
   `bounded_generation_lru_v1` 候选。
2. [x] 候选仅按 `publisher_node_id + publisher_epoch + track_id` 复用不可变字符串；
   容量有界，节点或 epoch 变化时失效，不改变来源键业务值和 GlobalTrack。
3. [x] D1 冻结微基准得到 `0.348622 -> 0.127734 s`、改善 `63.360%`、`7/7`
   配对更快和标识构造 `78,800 -> 200`。
4. [x] main 增加 selector、容量和 CLI，默认保持 `per_publication_build_v1`；selector、
   实现 ID 和缓存诊断进入 runtime profile、summary、module final 与治理审计。
5. [x] 冻结
   `configs/d1_opaque_source_identity_cache_multiseed_v1.json`：short seeds
   1101-1110、long seeds 1101-1103、200 个目标、200 个资源、2 个侦察节点。
6. [x] 两臂显式启用 `--d1-publish-opaque-source-key`，结构歧义 hold 保持关闭；同一
   pair 只允许缓存实现不同。
7. [x] 在 clean `d8fc76c` 上完成 13 组 pair、26 个 fresh arm，0 reused、0 failed；
   13/13 业务语义、有限状态、在线真值隔离、实现身份和缓存守恒通过。
8. [x] D6 owner 完成独立、只读、失败关闭 evaluator、CLI、16 项聚焦测试、中文报告和
   曲线；D6 全量 `834 passed`。
9. [x] short/long D1 fusion 改善 `9.465972%/6.437432%`，核心墙钟改善
   `2.845610%/2.728043%`；构造减少率和命中率均为 `99.163670%`。
10. [ ] long D2 association 非退化：实际组均值增加 `5.605213%`，超过冻结上限
    `5%`；`long_seed_1101` 增加 `19.069868%`，按原矩阵保留。
11. [x] D6 判定 `optimization_admitted=false`；main 默认保持
    `per_publication_build_v1`，候选不得晋级。
12. [ ] 系统实时 P1：候选最低实时因子 `0.193887`，尚未达到 1。
13. [ ] 若继续复核，先冻结新的确认矩阵并增加长时重复或 seed；不得修改本次门限、删除
    pair 或覆盖正式拒绝结论。
14. [ ] 默认无来源键 R0 的后续优化转向重复在线身份检查等实际热点；AirSim、冻结目标
    处理器和实飞容量另行验收。

该专项不改变量测频率、双时间戳、协方差、固定滞后窗口、关联门限或身份所有权。结果只覆盖
source-only、hold=false 的三维质点运行面。正式 D6 报告位于
`../d6_evaluation_metrics/outputs/d1_opaque_source_identity_cache_multiseed_20260725_formal_d8fc76c_d6/`。

## D1 结构稀疏数值雅可比准入（2026-07-25）

1. [x] D1 owner 提供参考
   `d1.ekf.numerical_jacobian.dense_output_probe.v1` 和默认关闭的候选
   `d1.ekf.numerical_jacobian.known_dimension_structural_columns.v1`。
2. [x] 候选只省略已知输出维数探测和观测方程不依赖的状态列；含径向速度雷达保留六列
   中心差分，其他当前量测模型使用三个位置列。
3. [x] D1 冻结微基准得到 `0.444645 -> 0.319552 s`、改善 `28.13%`、`9/9`
   配对更快和量测函数求值减少 `42.31%`；雅可比、归一化创新平方和门控摘要一致。
4. [x] main 增加
   `--d1-structured-numerical-jacobian-implementation`；正式准入前默认保持
   `dense_output_probe_v1`。
5. [x] selector、完整实现 ID、操作数和守恒检查进入 runtime profile、observation
   governance、module final diagnostics 和 episode summary。
6. [x] main 增加默认值、非法选择、CLI、manifest 哈希、四表面诊断和操作数回归。
7. [x] 冻结 `configs/d1_structured_numerical_jacobian_multiseed_v1.json`：short
   seeds 1101-1110、long seeds 1101-1103、200 个目标、200 个资源和 2 个侦察节点。
8. [x] 预注册 D1 fusion、核心墙钟、D1 scan input、D2 association、RSS、逐 pair、
   bootstrap、实现身份和量测求值减少门。
9. [x] 在 clean `9d1f54f` 上完成 reference/candidate 单 seed smoke，确认规范业务载荷、
   真值制品、计划谱系和四处诊断除预注册 treatment 外一致。
10. [x] D6 owner 实现只读、失败关闭的独立 evaluator 和 20 项合成合同正负测试；
    D6 全量 `818 passed`。
11. [x] 运行 13 组 pair、26 个 fresh arm；0 reused、0 failed。
12. [x] D6 全部预注册门通过，`optimization_admitted=true`；main 默认晋级为
    `known_dimension_structural_columns_v1`，参考实现继续可选。
13. [ ] 候选最低实时因子为 `0.180726`，低于 1；系统实时 P1 保持开放。
14. [ ] AirSim、冻结目标处理器、RMSE、NEES、NIS 和实飞容量分别验收，不从本次质点
    准入推断。

候选不修改量测频率、双时间戳、协方差、fixed-lag/OOSM、关联门限或身份所有权。局部
`28.13%` 未单独用于默认切换；默认晋级依据是 clean 同提交 13-pair 矩阵和 D6 独立
失败关闭评估。D1 独立 `FusionAdapter` 默认保持 reference。

## 在线真值守卫候选准入（2026-07-24）

1. [x] main 保留 `generic_recursive_v1` 参考实现，并增加默认关闭的
   `builtin_specialized_recursive_v2` 候选和 `--online-truth-guard-implementation`
   选择器。
2. [x] 两条路径保持相同的禁止字段、键值递归、循环保护、非有限状态和在线真值隔离语义；
   选择器、实现 ID 和检查计数进入 manifest 与 summary。
3. [x] 冻结 10 组 short pair 和 3 组 long pair；每组为 200 个目标、200 个资源和
   2 个侦察节点，共运行 26 个全新 arm。
4. [x] 13/13 pair 的业务语义、有限状态、在线真值隔离、实现身份和检查数守恒通过；
   0 reused、0 failed。
5. [x] short/long 发布总线及收尾墙钟改善 `22.58%/25.63%`，候选分别
   `10/10`、`3/3` 更快。
6. [ ] long 核心墙钟非退化：实际回退 `3.47%`，未达到至少改善 `0.5%` 的门限。
7. [ ] long D1/D2 阶段非退化：分别增加 `5.29%/7.34%`，超过 `5%` 上限。
8. [x] D6 独立判定 `optimization_admitted=false`；
   `system_realtime_gap_closed=false`，候选最低实时因子为 `0.165369`。
9. [x] 默认保持 `generic_recursive_v1`，候选只保留作复核和后续诊断，不进入默认在线路径。
10. [ ] 在不改写 v1 正式结论的前提下，可用 balanced-order v2 复核 long seed 1102 的
    主机热状态和顺序效应。
11. [x] 对未改动默认路径重新采集阶段画像，再选择可分离热点；不得降低真值审计强度、
    删除业务消息、改变传感器频率或放宽安全门控。
12. [ ] D1 owner 根据画像选择一个未重复、默认关闭的模块内候选，先完成冻结微基准和
    语义等价回归，再由 main 决定是否接入新的全栈 A/B。

冻结矩阵为 `configs/online_truth_guard_multiseed_v1.json`，SHA-256 为
`764574b9897d00101c26c555de2f407e1736c7e6ff50420eebf131e154618dc8`，producer commit
为 `8d8bb6ed7a417705236835f235361f45a021bb2b`。正式 D6 报告位于
`../d6_evaluation_metrics/outputs/online_truth_guard_multiseed_20260724_formal_8d8bb6e/`。

main 随后在同一 clean runtime commit、默认 `generic_recursive_v1`、200 对 200、
2.2 秒、seed 1111 上完成一次非准入 cProfile。未插桩正式 reference 的 long 三 seed阶段均值
仍以 D1 fusion `18.495864 s`、D1 scan input `6.612982 s` 为首要核心热点；诊断运行进一步
把 D1 累计时间定位到扫描批处理、记录重放收尾、扫描一对一匹配和协方差治理。报告写盘和
离线评分不纳入在线候选选择。该画像只用于选题，不替代冻结矩阵或性能准入。

## D1 常速度模型缓存准入（2026-07-24）

1. [x] D1 owner 提供 `per_prediction_build_v1` 参考实现和
   `bounded_exact_lru_v1` 候选；候选只缓存精确 `(dt, process_noise)` 对应的只读状态
   转移矩阵与过程噪声矩阵。
2. [x] D1 模块 benchmark 得到约 `2.12x` 局部加速、`20,000 -> 8` 次模型构造和相同终态
   SHA-256；D1 全量模块测试通过。
3. [x] main 增加显式实现选择器和 1 至 4,096 的容量校验；正式矩阵前保持参考默认，
   正式准入后晋级为 `bounded_exact_lru_v1`。
4. [x] selector、capacity、实现 ID 和缓存操作计数进入 runtime profile 哈希、
   observation governance、final diagnostics 和 episode summary。
5. [x] main 增加默认值、显式选择、运行清单哈希、诊断持久化和非法配置回归；D1、
   scalable 3D、D6 全量回归分别为 `395/205/771 passed`。
6. [x] 从 clean `4422356` 完成 seed 1101 reference/candidate smoke；除预注册运行配置
   差异外，业务载荷、真值制品和计划谱系一致，有限状态与在线真值隔离通过。
7. [x] 预注册 10 组 2.2 秒 short pair 与 3 组 10 秒 long pair；每组固定 200 个目标、
   200 个资源、2 个侦察节点，并交替实验臂先后顺序。
8. [x] 每个 pair 只允许常速度模型构造实现不同；扫描输入继续使用已准入
   `candidate_v2`，发布元数据继续使用已准入 `immutable_shared_v2`。
9. [x] D6 独立校验业务等价、D1 缓存诊断、D1 fusion、D2 association、核心墙钟、
   最大常驻内存、实时因子及逐 pair 稳定性。
10. [x] 运行 13 组正式 pair、26 个全新 arm，0 reused、0 failed。
11. [x] 全部预注册门通过，main 默认晋级为 `bounded_exact_lru_v1`；参考实现继续可选。

该专项不改变量测频率、状态模型公式、固定滞后窗口、协方差合同、关联门限或身份所有权。
局部 `2.12x` 结果不单独作为准入依据。正式 short/long D1 fusion 改善
`6.9271%/6.6103%`，核心墙钟改善 `2.4060%/2.4537%`，构造减少率和命中率均为
`99.5960%`，D6 判定局部优化准入。候选最低实时因子 `0.1739499`，系统实时、AirSim、
冻结目标处理器和精度证据仍待补充。

预注册矩阵为 `configs/d1_cv_motion_model_cache_multiseed_v1.json`，SHA-256 为
`9898656598f0fa282620afe2384a3d656b7496f8957109c413bcb62069fd2e9a`。运行器复用现有
clean-source、GNU time、断点状态和实现身份校验框架，已完成 26 项专项测试与 dry-run。
正式 D6 报告位于
`../d6_evaluation_metrics/outputs/d1_cv_motion_model_cache_multiseed_20260724_formal_4422356/`。

## D1 发布元数据多 seed 准入（2026-07-24）

### v1 正式结论

- [x] `per_track_copy_v1/immutable_shared_v1` 在同一 clean 提交完成 10 组 short 和
  3 组 long pair，共 26 个 200 对 200 episode；
- [x] 业务语义、有限状态、在线真值隔离、实现身份和内存门通过；
- [x] D1 fusion short/long 分别改善 `16.29%/31.05%`；
- [ ] D2 association 非退化：short/long 分别增加 `53.44%/169.89%`；
- [ ] 核心墙钟至少改善 `5%`：实际只改善 `1.65%/1.21%`；
- [x] D6 判定 `d1_optimization_admitted=false`，默认保持
  `per_track_copy_v1`。

v1 的自定义 `dict/list` 子类使 D2 无法使用可信快速路径，必须对每条航迹递归审计。该结果
只保留为失败定位和历史对照，不通过降低真值审计强度补性能。

### v2 执行计划

1. 以 `per_track_copy_v1` 为 reference，以 `immutable_shared_v2` 为 candidate。v2 使用
   D1 冻结的 `d1.publication_audit_tree.v2` 合同，不保留可变容器底层存储。
2. D2 对每个新审计根执行一次精确类型验证和一次真值内容审计；只有同一对象的后续引用允许
   身份复用。main 汇总 batch、latest 和 totals 计数并写入 governance 与 summary。
3. [x] main selector、runtime profile、D2 审计汇总、v2 evidence schema、预注册矩阵和
   v1 兼容运行器完成接线；历史 `immutable_shared_v1` 在当前运行时失败关闭。
4. [x] v2 配置固定 10 个 short seed 和 3 个 long seed；同一 pair 只允许发布元数据实现
   不同，扫描输入继续使用已准入的 `candidate_v2`。
5. [x] 续跑校验要求 D1 合同版本正确，D2 合同验证数等于内容审计数，候选存在身份复用且
   拒绝数为 0；参考臂不得出现 v2 复用计数。
6. [x] 从 main 集成提交 `be399e1` 创建 clean detached worktree，完成 short pair smoke；
   参考臂走内置等价复用，候选走首次内容审计后的身份复用。
7. [x] 完成 13 组正式 pair、26 个全新 arm。short/long D2 association 分别下降
   `16.19%/35.62%`，满足增幅不超过 `5%` 的门。
8. [x] D6 独立读取 episode、GNU time 和预注册矩阵，归一化两臂预期不同的 D2 审计诊断，
   输出逐 pair CSV、完整与紧凑 JSON、中文报告和曲线。
9. [x] D1 fusion short/long 改善 `13.54%/26.83%`，核心墙钟改善
   `6.57%/18.24%`，业务语义、审计合同和内存门全部通过。
10. [x] D6 判定 `d1_optimization_admitted=true`；main 默认晋级为
    `immutable_shared_v2`，参考实现继续可显式选择。
11. [ ] 系统实时 P1：候选最低实时因子 `0.1730801`，尚未达到 `1.0`。
12. [ ] 逐批审计明细、严格精度、AirSim 和冻结目标处理器证据仍待补充。

## 当前执行状态（2026-07-24）

### D1 扫描输入同提交矩阵

- [x] 同一 clean 提交保留 `reference_v1`，默认使用 `candidate_v2`；
- [x] short seeds `1101-1110`、2.2 秒、10 组 pair；
- [x] long seeds `1101-1103`、10 秒、3 组 pair；
- [x] 固定 200 个目标、200 个资源、2 个侦察节点并交替 arm 顺序；
- [x] 26/26 arm 正常退出，13/13 业务语义、有限状态、真值隔离和实现身份检查通过；
- [x] short 扫描输入改善 `5.360122%`，9/10 更快，配对区间上界低于 0；
- [x] long 扫描输入改善 `5.142482%`，3/3 更快；
- [x] 核心墙钟和内存非退化门通过；
- [x] D6 判定 `d1_optimization_admitted=true`，候选实现保留为默认路径；
- [ ] 系统实时 P1：候选最低实时因子 `0.143427`，尚未达到 `1.0`；
- [ ] 精度 P1：RMSE、NEES、NIS 和严格身份指标未进入该矩阵；
- [ ] 环境 P1：AirSim 与冻结目标处理器容量尚未验证。

扫描输入数据组织优化的正式 P1 准入项关闭。下一轮根据候选阶段墙钟重新排序 D1 融合、
D2 关联、发布总线及其他模块热点，不通过降低量测频率、缩短固定滞后窗口或删减协方差合同
换取速度。结果见 `docs/SCALABLE_3D_D1_SCAN_INPUT_MULTISEED_REVIEW_CN.md`。

### D1 多 seed 与长时矩阵

- [x] V1/V2 失败定位完成，D2 仅虚警排除计数由 `14` 修正为持久化 frame mapping 的 `11`；
- [x] D1 修复逐项相关裁剪可能破坏六维协方差正半定性的缺陷；
- [x] V3 reference `a5a472c` 与 candidate `064cbb9` 共同包含 D1 正半定修复和 D2 审计修复；
- [x] 预注册 short seeds `1101-1110`、2.2 秒、10 组 pair；
- [x] 预注册 long seeds `1101-1103`、10 秒、3 组 pair；
- [x] 固定 200 个目标、200 个资源、2 个侦察节点和结构歧义 hold 运行配置；
- [x] 交替 arm 先后顺序，避免把主机热状态固定偏向同一实验臂；
- [x] 运行器显式记录命令、提交、episode、资源记录和 cross-build 路径；
- [x] `--resume` 只接受 clean、有限、真值隔离且配置匹配的既有 episode；
- [x] D6 exact-match consumer 完成 10,000 次 paired bootstrap 和 manifest 入口；
- [x] 从头完成 10 组 short 与 3 组 long clean pair，共 26 个 episode；
- [x] 13/13 跨构建业务语义审计通过，在线真值使用、非有限状态和非零退出均为 0；
- [x] short D1 fusion 改善 `9.35462%`，10/10 seed 更快，bootstrap 区间上界低于 0；
- [x] long D1 fusion 改善 `6.631993%`，3/3 seed 更快；
- [x] 长短单位时间增长、核心墙钟和内存门全部通过；
- [x] D6 判定 `d1_optimization_admitted=true`，紧凑摘要、中文报告和曲线已登记；
- [ ] 系统实时 P1：candidate 最低实时因子 `0.143397`，尚未达到 `1.0`；
- [ ] 精度 P1：RMSE、NEES、NIS 和严格身份指标尚未进入本性能矩阵；
- [ ] 环境 P1：AirSim 与冻结目标硬件容量尚未验证。

V1/V2 只作失败定位，正式结论使用 V3 证据。V3 不复用旧 episode，reference 与 candidate
共同包含正半定修复，唯一 treatment 是标量/向量化协方差限制路径。结果见
`docs/SCALABLE_3D_D1_COVARIANCE_MULTISEED_V3_REVIEW_CN.md`。

后续扫描输入专项已完成，short/long 累计墙钟平均改善 `5.360122%/5.142482%` 并正式准入。
系统实时仍未关闭。下一项性能工作先复核最新候选阶段占比，再在 D1 融合、D2 关联和发布链
之间选择可分离热点。任何优化均继续使用同一冻结矩阵，不改变量测频率、双时间戳、协方差、
固定滞后窗口或身份合同。

### D1 协方差成对限制 clean 准入

- [x] D1 保留标量 reference，并默认使用六维协方差上三角批量裁剪；
- [x] floor/ceiling、相关上界、对称化、异常重置、双时间戳、NED、六秒 fixed-lag、谱系和
  `global_track_id` 合同保持不变；
- [x] main 固定 reference `7cc2d0c`、candidate `95bf46e`、seed 1100、200 对 200、
  2 个侦察节点、2.2 秒和 2,035 条观测，完成三轮交错 clean A/B；
- [x] 3/3 跨构建审计通过，规范在线载荷、真值制品、计划谱系、ACK 来源和 D4 内容地址一致；
- [x] D1 fusion wall `4.014714 -> 3.595533 s`，下降 `10.4411%`，3/3 更快；
- [x] D1 fusion P95 `184.228658 -> 173.330868 ms`，下降 `5.9154%`；
- [x] 核心墙钟、外部 elapsed 和 RSS 分别下降 `3.1417%/3.6310%/0.1429%`；
- [x] D6 独立准入门全部通过，`d1_optimization_admitted=true`；
- [x] 多个独立 seed 与长稳定窗口：V3 完成 short 10 seed 和 long 3 seed；
- [ ] D1 均方根误差、归一化估计误差平方、归一化创新平方和 D2 严格身份指标；
- [ ] AirSim 或冻结目标硬件容量验证；
- [ ] 200 对 200 系统实时闭合。V3 candidate 最低实时因子为 `0.143397`，
  `system_realtime_gap_closed=false`。

该项关闭 D1 标量协方差裁剪热点的 clean 全栈准入，不关闭系统实时、精度、AirSim 或物理
拦截 P1。V3 已补齐多个独立 seed 和长时回放，后续扫描输入专项也已正式准入。下一轮保持
传感器频率、量测门限和 fixed-lag 窗口不变，先补严格离线精度，并按最新阶段墙钟处理
D1 融合、D2 关联和发布链。
早期结果见 `docs/SCALABLE_3D_D1_COVARIANCE_LIMIT_CLEAN_AB_REVIEW_CN.md`，正式结果见
`docs/SCALABLE_3D_D1_COVARIANCE_MULTISEED_V3_REVIEW_CN.md`。

### D1 共同质心原子影子复核

- [x] D1 提供单次同步原子入口，内部 prepared handle 不跨调用方边界；
- [x] main 默认关闭的审计旁路改用原子入口，D2/D3 消费仍为 0；
- [x] D6 同时兼容历史 prepared-handle 和新 atomic 记录，缺失字段不补零；
- [x] clean `7cc2d0c` 完成 seed 1100、200 对 200、2.2 秒同输入 pair；
- [x] 9/9 post-integrity 通过，原子失败、禁止表面修改、在线真值使用和全局编号变化均为 0；
- [x] 去除 9 条审计记录后，3294/3294 条业务总线记录和逐主题摘要一致；
- [ ] 性能门：核心墙钟 `10.735/19.450 s`，增量 `81.1799%`，未达到 `<=5%`；
- [ ] 有效 treatment：46 条决策全部以 `oosm_scan` 拒绝，accepted 为 0；
- [ ] 结果效果：无 accepted treatment，仍不可评估。

状态保持 `A2_NOT_ADMITTED`。全拒绝路径下，旧 prepared-handle 实现本来就跳过 shadow
assembly；原子入口收紧安全边界，但没有减少完整规范描述、后置完整性复核和 main 禁止表面
前后摘要。因此停止 seeds `1101/1102` 和 A3/A4，不再把在线 shadow 微调作为当前性能主线。
后续优先离线化该审计，并将 D1 性能工作转回批量融合、空间预筛选、合并固定滞后重放和延迟
序列化。结果见
`docs/SCALABLE_3D_CENTROID_OVERLAY_A2_ATOMIC_REVIEW_CN.md` 和同名 JSON。

## 历史执行状态（2026-07-23）

### D1 共同质心发布影子 A2

- [x] main 以默认关闭开关接入 detached 审计旁路，显式复用 D1 prepared handle；
- [x] 旁路不替换规范 D1 航迹，不被 D2/D3 消费，不使用在线真值；
- [x] 记录规范表面前后摘要、prepare、evaluate、assemble、影子摘要和日志物化分段耗时；
- [x] seed 1100、200 对 200、2.2 秒、2 个侦察节点完成 control/shadow pair；
- [x] 过滤 9 条审计记录后，3294/3294 条业务总线记录经谱系和序号规范化逐条一致，真值
  状态与离线标签一致；
- [x] D6 独立确认业务非干预通过；
- [ ] 性能门：墙钟增量为 `80.88%`，未达到 `<=5%`；
- [ ] 有效处理门：46 条证据全部以 `oosm_scan` 拒绝，accepted 为 0；
- [ ] 结果效果门：没有 accepted treatment，结果效果不可评估；
- [ ] clean 来源门：本轮 manifest 为 `repository_dirty=true`，只作开发证据。

当前状态为 `A2_NOT_ADMITTED`。下一轮只能减少完整规范载荷的重复处理，不得省略 metadata、
状态、协方差、来源、身份、双时间戳或全局编号，也不得放宽 OOSM 和结构门制造 treatment。
先从 seed 1100 重跑 `<=5%` 性能门；性能通过后，再用新的匿名冻结扫描寻找自然的同步平衡
窗口。A2 通过前不启动 A3/A4，不运行 seeds `1101/1102`。机器证据和中文复核位于
`docs/SCALABLE_3D_CENTROID_OVERLAY_A2_PREPARED_REVIEW_20260723.json` 和
`docs/SCALABLE_3D_CENTROID_OVERLAY_A2_PREPARED_REVIEW_CN.md`。

### 身份承诺下游准入

- [x] D2 身份承诺 v2 按 `global_track_id` 显式进入 D3；缺失、未知和两类未承诺状态均
  失败关闭。
- [x] 已绑定目标撤销承诺时，同周期清除旧 binding 并设置强制重规划；新计划继续执行
  原有版本、迟滞、M 对 N 和过时计划拒绝合同。
- [x] D5 主动视觉和 D7 导引独立复核 committed 集合，不允许重规划间隙沿用旧目标。
- [x] AirSim 经典 D2 兼容桥改为调用方提供逐航迹显式承诺清单；适配器缺清单时不再
  隐式放行。
- [x] D3、AirSim runtime、scalable 3D、integrated point-mass 和跨模块合同软件回归通过。
- [x] detached clean `7e15dac` 的同输入 seed 1100 已验证 11 个旧绑定在同一周期退出
  v2 计划，D3/D5/D7 后续越权均为 0；质心候选仍为 46/0/46 零 treatment。
- [x] 新增可复用 clean A/B 审计器，固定提交、配置、真值哈希、计划升版和下游继续执行
  检查；episode 未注入 stale plan，旧版本拒绝只引用实际软件回归。
- [ ] 在真实 AirSim 多 seed 中接入真实 D2 承诺侧车，验证撤销时序、严格升版、stale
  plan 注入拒绝及 D5/D7 零越权。完成前不晋级结构歧义候选。

第四轮规则全栈性能收敛已完成三 seed 长时复测。D1 在保持逐扫描融合和逐扫描发布的前提下，
把同一融合时刻的中间发布改为 state-only，并只为最后一个后验构造完整航迹数组；D3 已建立
冻结 200×200 输入的成本归因和规划器内部可信执行签名缓存；D5 已建立定长操作数诊断并复用
同批相机模板。模块内 A/B 和 main 集成回归均保持确定性业务语义。

main 已从 detached clean 提交 `3310165` 运行 20/50/100/200 四档、每档 5 seed 的 2.2 秒
规则全栈。20/20 状态有限，在线真值使用为 0；平均实时倍率为
`1.504/0.540/0.240/0.092`。200 规模 D1 融合、D2 常规关联和 D3 分配平均累计时间为
`10.275/2.037/0.665 s`；D2 尾部收束为 `0.640 s`。平均墙钟相对上一轮 clean 批次下降
26.7%，系统实时 P1 仍未关闭。

detached clean 提交 `8f86192` 的 seed 42000 长时对照已完成。2.2 秒和 10 秒核心墙钟为
`18.302/152.254 s`，实时倍率为 `0.120/0.066`，峰值驻留内存为 `1.015/2.902 GiB`。
长短单位时间成本增长由上一候选的 2.036 倍降至 1.830 倍，仍未达到实时或线性增长。
seed 42000-42002 的三组 10 秒运行也已完成，核心墙钟均值 155.895 秒、峰值内存均值
2.889 GiB；相对上一候选下降 9.4% 和 5.4%。在线真值和 D1/D2 overflow 均为 0。

第五轮 clean 候选 `f80b5bd` 已完成同一三 seed 的 10 秒复测及独立 build 语义审计。核心
墙钟、进程总耗时和峰值驻留内存均值为 `150.875 s/195.363 s/2.359 GiB`，相对
`8f86192` 分别变化 `-3.22%/-12.31%/-18.33%`。D1 实际创新求解次数下降 77.86%。三个
seed 的真值制品、终态模块数量和规范在线载荷相同；D4 内容地址在原始载荷校验后按规范计划
谱系重算，不删除 advisory identity。实时倍率均值仍只有 `0.0663`，实时和长时超线性 P1
继续开放。

main-owned D1→D2 待处理 posterior 锁存已在 clean `12c5073` 建立新的调度行为基线。
锁存只跨调度 tick 保存真实后验，在 D2 消费后清除；D7 继续使用后验真实有效时刻执行
0.75 秒过期门。seed 42000 两次 clean 10 秒运行逐主题、真值和合同完全一致；核心墙钟
`107.853/122.032 s` 表明单机计时仍有约 13% 波动。该行为相对 `f80b5bd` 有意提前消费
待处理后验，因此不能沿用旧提交的业务哈希或性能归因。

提交 `b681c8f` 已补充 D1 完整后验代次、D2 最后消费代次、消费次数和节拍前合并次数。
同一代次不能重复产生 D2 发布，没有新后验时不得调用 D2，发布时刻不能改写状态有效时刻；
episode 在下一关联 tick 前结束时，finalize 只排空最后后验，不产生相机或控制命令。下一
clean candidate 已以该审计合同建立三 seed 基线和 20 个保留 seed 描述性校准。

detached clean `0d2da25` 的 seeds `42000-42002` 已完成 10 秒运行。三 seed 核心墙钟均值
`101.298 s`，实时倍率均值 `0.0988`，D1 融合均值 `55.275 s`，D5 终端配准均值
`1.247 s`。3/3 状态有限、在线真值为 0、分配保持为 0。D1 最终/完整发布代次为
`453/453`、`516/516`、`505/505`；D2 最终消费均追平 D1，消费/发布均为 48 次，节拍前
合并数为 `405/468/457`，pending 均为空。D6 v6 对三个真实 runtime v2 episode 的审计
全部通过，证据级别仍为 `descriptive_clean_source_calibration`。

seed 42000 同提交重复运行核心墙钟为 `96.787/96.704 s`，全量在线载荷、真值和计划谱系
语义等价。`12c5073` 与 `0d2da25` 的跨提交审计只有 811 个新增字段差异：763 个 D1
`posterior_generation` 和 48 个 D2 `source_d1_posterior_generation`；其余业务合同和真值
一致。D1/D5 独立 A/B 支持各自优化有效，但集成墙钟仍受主机波动影响，不能把全部下降归因
于单一模块。

同一 detached clean `0d2da25` 已顺序完成 seed `1000-1019` 的 20 组 nominal 200 对 200、
10 秒规则全栈。20/20 进程退出为 0、状态有限、在线真值使用为 0、分配保持为 0，D1-D2
后验代次守恒且 pending 为空。核心墙钟均值 `96.391 s`，实时倍率均值 `0.1039`；D1 融合、
D1 扫描输入、D2 关联、D3 分配、D5 终端配准和 D7 导引均值为
`51.649/12.418/5.492/2.448/1.185/3.638 s`。D6 v6 将 20/20 归类为
`descriptive_clean_source_calibration`，正式实验矩阵 episode 仍为 0。这关闭规则基线的
20-seed 描述性稳定性和代次审计子项，不关闭实时、学习算法比较或物理拦截验收。

detached clean `4ac3bb2` 已使用新的阶段分位合同完成 seed 1000 的 2.2 秒与 10 秒
200 对 200 同源校准。10 秒核心墙钟 `85.002 s`，相对 `0d2da25` 同 seed 下降 `9.67%`；
D1 融合从 `49.697 s` 降到 `40.273 s`。跨构建审计确认规范在线载荷、真值状态和计划
谱系完全一致。D1 融合 `P50/P95/max` 为 `33.252/224.764/592.957 ms`，D2 关联为
`121.972/137.335/145.966 ms`。这关闭 stage-timing-v2 的 clean 200 对 200 producer/
consumer 接线，不关闭多 seed 分位、超线性增长或实时性。
原始制品不提交；版本化紧凑摘要位于
`docs/SCALABLE_3D_STAGE_TIMING_CALIBRATION_20260722.json`。

D1 在同一 seed 1000 冻结输入上完成 scan-input profiler 和完整帧复用。输入包含
771 个扫描、11,889 条匿名观测；已校验且快照完整的 `SensorScanFrame` 直接进入
organizer，发生对象、标量或数组可写状态变化时仍回退完整快照和 fail-closed 校验。
帧重建由 771 次降至 0，organizer 内 observation 再快照由 11,889 次降至 0。
前 256 个扫描交错 5 轮的 P50/P95 由 `1.942/1.968 s` 降至
`0.881/0.894 s`，P50 描述性加速 `2.204x`。14 项逐输入、审计、融合状态、协方差、
双时间戳、谱系、分级和终态等价验收全部通过。该运行来自当前 D1 工作区，不是 clean
full-stack、AirSim 或正式多 seed 证据；全栈尾延时 P1 不关闭。

D6 新的真值隔离入口已对同一 seed 1000 制品完成实际消费。严格 `id_switch_count` 继续因
`multiple_truth_targets_for_global_track` 为 unavailable；部分诊断独立报告映射覆盖率
`0.985395`、帧覆盖率 `0.0625`、相邻转移覆盖率 `0`、385 个锚点区间和保守 ID Switch
下界 7。来源 manifest、evaluation 和四项 source SHA 均通过，严格值未回填，也未生成上界。
本项关闭 D2 partial block 到 D6 truth-isolated 报告的单 seed 接线，不关闭严格身份指标或
多 seed P1。

D2 已在同一冻结在线总线上完成 profiler v2 与三项语义等价优化：按周期内唯一 `dt`
复用常速度模型矩阵、对已治理的 D1 六维协方差跳过重复 marginal 比较、增量维护 claim
ledger 计数并每帧汇总一次。48/48 周期公开输出和 tracker 状态严格相等，D2 core
中位数由 `2.928830 s` 降至 `2.204672 s`，描述性加速 `1.328465x`。常速度矩阵构造
由 9,246 次降至 46 次，冗余 marginal `allclose` 由 19,252 次降至 0，ledger summary
由 96 次降至 48 次。候选早晚窗口成本比为 `1.123036x`，没有改善原有长窗口增长，
因此只关闭三个固定操作数热点，不关闭完整阶段实时性或多 seed 性能 P1。

D5 已在同一 seed 1000 的 25 帧短序列和 114 帧长序列上完成操作数归因及局部等价优化。
历史 gauge 改为增量维护，长序列 723 次刷新避免扫描 91,871 个 tracker 引用；2,289 个
singleton cluster 直接复用投影距离行，79 个多节点 cluster 仍执行完整聚合；匿名 payload
叶子快路径和 8,192 项有界 local-ID 正则缓存保持 truth fail-closed。最终源码在修复
`-0.0` 符号位边界后重新复放，短/长业务、binding 和冻结 v1 操作数哈希分别相等，
在线 truth 使用与 `global_track_id` 改写均为 0。pre-fix profiler 只能作方向归因；
当前全量为 `551 passed`，完整集成、多 seed 和长窗口实时性 P1 不关闭。

detached clean `5263e2b343dc4b96d239f77ef09437eb132f9efb` 已完成当前优化后的
seed `1000-1019`、nominal 200 对 200、10 秒规则全栈复测。20/20 状态有限，在线真值使用
总数为 0，D1-D2 后验代次完整，D6 failure reason 为空。核心墙钟均值由 `0d2da25` 同 seed
参考的 `96.391 s` 降至 `86.099 s`，20/20 seed 均改善；配对变化均值为 `-10.63%`，
95% seed bootstrap 区间为 `[-11.71%, -9.61%]`。实时倍率均值由 `0.1039` 提升到
`0.1163`，仍约需 8.6 倍吞吐提升才能达到 1.0。

当前候选的 D1 扫描输入、D1 融合和 D2 关联累计均值为
`9.671/43.774/5.139 s`，相对参考分别变化 `-22.06%/-15.15%/-6.41%`，且三项均为
20/20 seed 改善。D3 分配和 D5 主动视觉变化区间跨过零，尚不能认定稳定退化；D7 导引累计
均值由 `3.638 s` 增至 `3.859 s`，配对变化 `+6.24%`，但规范控制输出保持一致，需作为
性能回归单独归因。main publication bus 增加 `4.44%`，在线日志均值仍为
222,974,342 字节，没有因优化减小。

`0d2da25 -> 5263e2b` 的 20/20 直接跨构建审计全部通过。规范在线载荷、真值状态与标签、
D3 计划谱系、D4 内容地址和 ACK 来源一致。D6 对 20 个候选 episode 的 clean provenance、
generation integrity 和 schema 审计均为 20/20，通过后仍将其归类为
`descriptive_clean_source_calibration`；正式实验矩阵 episode 数为 0。严格
`id_switch_count` 在 20/20 seed 上仍为 unavailable，不能用部分身份下界代替。D6 复算的
partial mapping/frame/adjacent-transition coverage 为
`178531/181110`、`103/959`、`1149/187800`；19 个 episode 的保守下界合计 199，
但不回填 strict。D1 RMSE/NEES 同样因 `d2_lineage_mapping_missing` 不可用。紧凑证据见
`docs/SCALABLE_3D_20SEED_PERFORMANCE_CALIBRATION_20260723.json`。

同日后续完成三项归因。D1 的 claim JSON 单次物化在 771 个扫描、11,889 条观测
冻结输入上保持 claim registry、融合状态、协方差、双时间戳和最终航迹严格一致，
五轮交错 P50 由 `3.618 s` 降至 `1.905 s`。D7 的固定 200-pair/185-frame replay
中，两个历史构建各 6 次的内核变化为 `+0.626%`，95% 区间
`[-1.828%, +3.178%]`，未确认模块回归，不修改导引算法。

D2 对 20 个 episode 的离线身份 producer 完成重放和来源校验。严格 ID Switch
仍为 `0/20` 可用；118 个多真值航迹帧、2,464 个缺标签受评分映射和 2,474 条
D1 未解析估计证明阻断来自上游混轨与标签合同，不是 evaluator 分母。partial lower
bound 继续只作诊断。下一轮身份主线改为：先由 D1 治理雷达/视觉跨模态混轨，再由
main/sensor truth sidecar 明确标注目标、已知虚警或未知标签，最后重新运行 D2/D6
严格指标。

上述第一轮实现已经落地。D1 修复冻结只读相机元数据、旋转字段和嵌套内参解析后，seed 1000
冻结回放中的 17 条已知视觉污染观测全部离开原错误航迹。main producer、D2 和 D6 已共同
采用三态离线标签，D5 学习导出和保留 seed 身份桥只消费目标标签。D1、D2、D6 和 scalable
回归分别为 `191/249/586/134 passed`。

detached clean 提交 `488dc39` 中，三个 2.2 秒 seed 的已知虚警标签为 `100/103/109`，缺失身份
证据均为 0，严格 ID Switch 可用率为 `1/3`；10 秒 seed 1000 的 402 条已知虚警均通过 D6
排除审计，但仍有 7 个雷达多真值映射。四组 manifest 均为 clean；这批仍是描述性校准，
不是 formal acceptance。

D1 雷达交替环 v1 已完成 main 同配置 clean 阻断评审。baseline `488dc39` 与 candidate
`d967c96` 均使用 200 对 200、2.2 秒、`recon_count=2` 和 seeds 1000/1001/1002，逐 seed
配置哈希相同。候选把严格身份可用率从 `1/3` 提高到 `3/3`，但 D2 航迹分别减少
`1/8/3`，D3 分配分别减少 `2/10/7`，seed 1001 continuity 下降 `0.055`，并抑制
`1.12%/6.61%/3.98%` 的雷达量测。因此 v1 不晋级。

提交 `8f17c5d` 已把 v1 设为默认关闭；同配置三 seed 全部恢复 baseline，跨构建
`3/3 passed=True` 且规范在线载荷相同。严格身份 P1 保持开放。下一候选须证明最大匹配
allowed-edge 图中的 cycle、free-row 和 free-column 路径，并在未用于开发的 clean seed 上
同时验收身份、航迹、分配、连续性、抑制、birth 和 recall。当前不运行被拒绝 v1 的 10 秒
或 20-seed；10 秒 baseline 中的 7 个歧义映射继续作为长期跨模态验收目标。机器摘要见
`docs/SCALABLE_3D_RADAR_ASSIGNMENT_CANDIDATE_REVIEW_20260723.json`。

main 验收入口使用显式
`--d1-radar-assignment-ambiguity-governance-v2`，默认关闭。每个 episode 的 summary 和
observation-governance audit 必须写出 D1 实际 selected policy version、enabled/status 与
抑制计数；兼容 policy version 字段不能单独判定实际启用策略。
manifest 必须写入完整 runtime profile 和独立 SHA-256，episode ID 绑定该哈希。基线和候选
应从同一 clean 提交、相同场景配置和相同 seed 启动；除该实验开关外不得改变输入。

上述 v2 门槛已在 detached clean `c928727` 的未见 seed 1100 执行。候选 ID Switch
`9 -> 9`，continuity `0.865 -> 0.830`，D2 航迹 `203 -> 199`，D3 分配
`200 -> 196`，并抑制 `77/1954=3.94%` 的雷达观测。该结果未达到身份改善和业务可用性
不退化门槛，v2 不晋级；剩余短 seed、10 秒和 20-seed 不执行。下一方案应分离结构歧义检测
与状态量测利用，避免把允许边分量直接转换为整分量全抑制。

D1-D2 结构歧义侧车、有界保活和身份承诺 v2 已完成原子接线，默认关闭。恢复承诺现在同时
要求量测晚于 hold 水位并满足发布新鲜度。超过 `0.9 s` 的证据保持未承诺，不进入严格
身份映射。离线身份清单 v2 绑定完整恢复配置、配置摘要和逐发布记录数；D6 对清单和在线
D2 JSONL 做独立复核，历史清单 v1 保持兼容。D2、D6、scalable 3D 当前回归分别为
`291/611/146 passed`。

detached clean `ff88131` 的 seed 1100 最终同构建门槛仍未通过。候选形成
`1711/69/7` 条 committed/hold/after-hold 记录，3 条超龄恢复证据被失败关闭。严格
ID Switch `9 -> 3`，重复分配保持 0，未承诺来源和候选绑定违规为 0；D2 航迹仍
`203 -> 201`、D3 分配 `200 -> 197`、可用映射 `1566 -> 1491`，track continuity
`0.865 -> 0.826667`，coverage continuity `0.870 -> 0.828333`。两组 v2 清单均绑定
9 条一致配置记录，D6 episode/runtime provenance 通过。

配置谱系和发布新鲜度合同已关闭。结构歧义保活的算法准入仍开放。下一轮不调整默认规则
路径，也不扩大 `0.9 s` 窗口；先标定 gap/hard lease、birth 抑制和恢复等待对
track availability、D3 分配与 recall 的影响，再以新候选从 seed 1100 开始。当前
seeds 1101/1102、10 秒和 20-seed 矩阵停止。

身份中性质心校正已完成 main 显式接线、严格配置校验和 runtime profile 哈希绑定。
D1 连续 generation 改为正式历史重放后的单帧替换修正，并用固定滞后水位限制代际登记。
当前 dirty 开发门槛在 seed 1100 上比较 source-key + hold 与
source-key + hold + centroid。两臂 D1/D2/D3、ID Switch、连续性、最终映射和绑定违规
完全相同；候选的 46 个组件全部失败关闭，原因为 `oosm_scan=30` 和
`unbalanced_component=16`，实际施加数为 0。

该结果不满足“产生可审计 treatment 后恢复下游可用性”的前置条件。seeds 1101/1102
继续停止，候选不晋级且保持默认关闭。

D1 后续已完成冻结扫描边界诊断：

- [x] 同步平衡纯交替环 `2x2` 分量形成一次 `15.000000 m` 共同平移，速度、相对位置、
  hit、lineage、source support、身份和规范航迹编号不变，协方差不收缩；
- [x] 乱序平衡分量保留量测/到达时刻并以 `oosm_scan` 拒绝；
- [x] 数量不平衡分量记录成员/观测 `2/1`、free row/column `1/0`，并以
  `unbalanced_component` 拒绝；
- [x] 拒绝分量没有共同质心公式输出，但 publication-base replay + replace 仍改变协方差
  数值。该差异已归因到离散匀速过程噪声的单段/分段传播不等价，不能作为门控放宽或收益
  证据。

下一候选设计已经冻结，实施 P1 仍开放：

1. D1 先完成 A1 纯函数 publication overlay 原型和 A2 离线 shadow。规范滤波历史不变，
   所有拒绝原因下业务发布必须与 control byte-identical；
2. 固定滞后 OOSM 共同质心事件保持设计暂停，不与 A 候选混合实现；
3. D1 证据交由 D2 概率或多假设层消费的路线由 D2 owner 单独制定 C0 计划。

方案不得利用在线真值，不得改变 hit/lineage/source support，不得放宽身份承诺、版本、
时间戳或绑定门。只有 A1/A2 通过，新的真实匿名冻结扫描产生自然、非零且可审计 treatment，
并通过状态一致性和下游可用性门，才进入确认性未见 seed；seeds 1101/1102 继续停止。

main 真值守卫键布局缓存已通过完整测试、嵌套可变负例和跨构建语义审计。四组交错
clean 2.2 秒复测的 publication bus 中位数下降 12.69%，核心墙钟中位数只下降
0.44%。该项关闭局部重复键规范化，不关闭 200 对 200 实时 P1。组合 clean
`d79aba3` smoke 的实时倍率为 `0.204`，状态有限且在线真值使用为 0。

当前执行顺序调整为：

1. 正式扫描输入候选的 long 三 seed 中，D1 融合累计墙钟均值为 `30.410886 s`，约占
   `66.771564 s` 核心墙钟的 45.5%，仍是首要热点。下一轮分离 `GlobalTrack` 物化、
   非雷达扫描关联、固定滞后回放和检查点查询；不得缩短 6 秒窗口、丢观测或放宽协方差治理。
2. D2 关联 long 累计墙钟均值为 `5.717809 s`，扫描输入为 `6.340680 s`。扫描输入本轮
   已正式准入，不立即叠加第二次改造；D2 继续分离 covariance
   governance、重复航迹合并和 publication 成本。三态 truth sidecar 与视觉几何解析已完成，
   严格身份仍由 D1 雷达扫描间多真值谱系阻断；v1 已拒绝，下一候选必须覆盖完整交替路径，
   不得从距离、名称或零径向速度占位补算身份。
3. main publication bus、D7 导引、D5 主动视觉和 D3 分配的 long 累计墙钟均值分别为
   `3.863808/3.634627/3.024112/2.374378 s`。D7 固定输入没有确认内核回归，核心公式保持
   不变。main publication bus 已关闭重复键
   规范化，后续只在新的 clean 多 seed 中复核阶段分位和总墙钟。
4. D5 已关闭 history gauge、匿名审计和 singleton binding 的局部重复成本。下一步用正交
   多 seed 控制检测数、活跃相机数、中心候选数和时长，分离 tracker pair 与投影/绑定矩阵
   增长，不减少视觉帧、不放宽投影与身份门限。
5. D3 冻结输入归因和 20-seed 分位已完成。当前不修改规则代价、迟滞或 Hungarian 主线；
   先处理 D1、D2、D7 和 publication bus 的明确热点。
6. 完成下一轮吞吐和严格身份治理后，再扩展 D4 故障、D5 跨视角和 D7 五米接近的长时多
   seed 验收。
7. 学习策略继续保持 disabled/shadow；性能优化不得用学习模型、降采样或放宽安全门控替代。
8. 20 个保留 seed 的规则参考和当前候选均已完成。下一批必须由正式矩阵 runner 冻结 variant、scenario、
   scale、comparison key、训练 seed registry 和学习 bundle；D4 内容地址、D3 计划谱系、来源
   ACK、generation 守恒或 assist adoption 任一不可回算时必须判为不可比较。

本批属于干净来源的描述性校准，未声明正式实验矩阵。详细结果见
`docs/SCALABLE_3D_LONG_DURATION_PERFORMANCE_CALIBRATION_CN.md`。

### 长时性能收敛门槛

main 已新增只读长时 episode 对照工具。比较对象必须来自同一 clean Git 提交、同一 seed、
相同规模和相同场景配置，唯一允许变化的是 `duration_s`。输出必须同时报告：

1. 单位仿真时间总墙钟和在线日志量；
2. 峰值驻留内存及 episode 结束后的写出开销；
3. D1 扫描缓冲、D2 claim ledger、计划确认和在线真值使用；
4. D1、D2、D3、D5、D7 及 main 总线的调用密度和单次调用成本增长；
5. 状态有限、在线真值为零、无治理 overflow 等合同检查。

提交 `c0460e0` 的 seed 42000 基线为 2.2 秒 `21.709 s/1.054 GiB`，10 秒
`263.289 s/3.154 GiB`。单位仿真时间成本增长 `2.668x`，D1 fusion、D2 association、
D5 terminal association 的单次调用成本分别增长约 `2.107x/3.467x/2.444x`。该 pair
只证明长时性能缺口存在。

提交 `3bac3ff` 的候选 pair 已通过真值隔离、计划版本、中心身份所有权、D1/D2 overflow 和
输出语义检查。D1/D2/D3/D5/D7 最终规范输出哈希与旧基线一致，三类飞行实体的 201 个三维
状态帧逐元素相同。10 秒核心墙钟下降 34.6%，峰值内存只下降 5.5%，单位仿真时间成本仍增长
2.036 倍。三组 10 秒稳定性校准的核心墙钟均值为 172.097 秒，峰值内存均值 3.055 GiB。
该批作为上一候选保留。

提交 `8f86192` 的当前 pair 继续通过全部安全合同。seed 42000 的 10 秒核心墙钟为
152.254 秒，单位仿真时间成本增长 1.830 倍，在线日志为 221.338 MiB。三 seed 核心墙钟、
峰值内存、D1 融合和 D5 终端配准均值为 155.895 秒、2.889 GiB、92.991 秒和 2.546 秒。
状态更新发布与完整快照发布分离后，逐扫描摘要、谱系、扫描事件和最终业务摘要保持一致。
该项关闭发布物化实现缺口，但系统实时性和超线性增长仍为 P1。详细结果
见 `docs/SCALABLE_3D_LONG_DURATION_PERFORMANCE_CALIBRATION_CN.md`。

## 1. 工程问题与科学问题

本模块为 main-owned 集成环境，目标是在统一北东地坐标系和统一仿真时钟下，承载最多
200 架拦截无人机与 200 个来袭目标的三维质点闭环。环境只负责世界状态、传感器场景、
通信、总线、真值隔离和 episode 编排，不替代 D1-D7 的模块算法。

工程问题包括大规模状态传播、异步观测、跨模块版本一致性、可复现实验、运行时开销和
高频日志体量。科学问题包括密集目标下的航迹起始与身份连续、跨视角稀疏图关联、学习
辅助分配、多时间尺度资源调度，以及学习策略在确定性安全约束下的可回退运行。

## 2. 数学模型

单个质点状态为：

```text
x = [p_N, p_E, p_D, v_N, v_E, v_D]
```

采用北东地坐标系，高度等于 `-p_D`。离散动力学为：

```text
p(k+1) = p(k) + 0.5 * (v(k) + v(k+1)) * dt
v(k+1) = clip(v(k) + a(k) * dt)
```

更新过程限制加速度模、速度模、三维转向率和垂向速度。传感器观测同时携带
`measurement_timestamp`、`arrival_timestamp` 和 covariance。

相机采用 `P_c = R_c_n @ (P_n - C_n)`，并通过针孔模型生成像素中心和 bbox。像素协方差
按投影雅可比传播。视觉检测还需满足按相机类型配置的最小 bbox 面积，远距亚像素目标由
雷达链路承担。在线观测使用匿名局部编号，目标真值编号只写入独立离线标签流。

主动视觉把 D2 航迹按常速度外推到当前相机时刻，并将位置协方差通过方位/俯仰雅可比传播
为角度协方差。D5 规则或学习策略只输出有界云台增量和广角/变焦模式。main 将其转换为
绝对北东地指向，核对 `plan_version`、联盟版本、通信版本和有效期后，在下一视觉帧应用并
发布确认记录。未准入学习建议不能覆盖规则动作。

声学阵列输出方位角、俯仰角及类别级声纹概率。声纹只作为分类提示，不能生成稳定目标
身份；其在线观测同样使用匿名编号并与离线真值标签分流。

## 3. 算法选型

- 世界状态传播采用 NumPy 向量化实现，保证 400 个实体可以按固定步长稳定推进。
- D1-D4 和 D7 的规则路径是所有学习实验的基线与回退路径。
- D5 图神经网络只输出候选边同一身份概率，匈牙利和约束聚类负责最终假设。
- D3 强化学习只修正规则代价和重规划建议，最终分配继续由确定性求解器生成。
- 全局强化学习只调整区域配额和邻区转移；主动视觉强化学习只调整观察任务和云台动作。
- D7 使用确定性三维比例导引，不使用端到端强化学习飞行控制。

## 4. 场景设计

课程规模为 5、20、50、100、200。基础场景包括均匀来袭、密集交叉、编队分裂、多高度
层、部分遮挡、漏检与虚警、传感器延迟、通信丢包、资源失效、中心失效、二级节点失效
和高威胁 M 对 N 需求。200 对 200 名义基线保持一对一；多机协同作为独立资源稀缺场景。

默认物理步长为 0.05 秒。D7 控制、视觉、融合关联、分配和全局区域调度按独立周期执行。
所有场景由版本化 JSON 配置、`scalable3d-catalog-v1` 场景目录和固定 seed 驱动。中心、
多二级和完全分布式故障计划已经接入 D3/D4 运行时端口，执行时必须通过 owner、epoch、
lease、提交模式和计划版本检查。

## 5. 模块和接口

```text
VectorizedPointMassWorld
  -> SensorScene
  -> VersionedEpisodeBus
  -> ScalableModuleStack(D1 -> D2 -> D3 -> D4 -> D5 -> D7)
  -> world state feedback
  -> D6 offline evaluation
```

模块栈输入只含匿名传感器批次和资源自身导航状态，不能读取目标世界状态。D7 返回的 NED
三维加速度由 main 回写统一世界；模块发布记录再次经过在线真值字段拦截。

物理拦截采用离线三维接近判据。每个物理步将距离不超过 5 米的资源-目标候选按最近距离
一一消解并登记事件，真值目标号仅供 D6 评分；在线模块不接收该映射。

main 维护本目录。D1-D7 的算法实现、README、PLAN、GAP 和 review 仍由对应 subagent
维护。共享合同包含世界/总线/场景/模型/阈值版本，以及每次运行的配置 SHA256 和 Git
commit。

## 6. 实施阶段

1. 冻结世界、场景、总线、真值和 manifest 合同。
2. 实现向量化三维世界、相机投影、传感器场景和通信模型。
3. 完成 5/20/50/100/200 纯环境传播和性能基线。
4. 由 D1/D2 修复密集目标六维跟踪并接入总线。
5. 由 D7 完成三维导引与统一世界状态回写。
6. 由 D5 建设匿名视觉图数据集和稀疏图神经网络。
7. 由 D3 实现行为克隆预热和强化学习代价修正。
8. 由 D4 接入区域二级节点和完全分布式故障场景。
9. 由 D6 完成多 seed 统计、图表、动画和中文报告。
10. 完成 20 个未见 seed 的最终验收及全部文档同步。

### 2026-07-21 当前状态

- 正式学习数据已完成 900/900 episode，覆盖 9 类场景、5 档规模、100 个训练 seed；每个
  场景/规模 cell 为 20 episode。来源提交干净，在线真值使用为 0，保留 seed
  `1000-1019` 未进入数据集。此前 209/900 的失败目录不参与训练。
- D3 已完成完整数据行为克隆，当前为 development/shadow-only。D4 已完成行为克隆，但
  正式规则动作缺少 quota、hold、replan 和 transfer 正样本。D4 已用独立 clean 课程补齐
  四类规则示范覆盖并形成 canonical 行为克隆只读视图；该课程没有 reward，不能用于 PPO
  或 assist。D5 正式跨视角图的 97.52% 图帧无候选边且困难负样本不足，原开发模型不能
  晋级；独立 clean 困难样本课程已补充 4500 帧、245032 条默认几何门候选边，正/负/
  未标注为 `57292/187740/0`，数据支持与训练数据来源门已通过。D5 后续已完成 clean
  composite 模型训练，以及 seed `1000-1019`、45 个场景规模单元、900 帧的 paired shadow
  v2。模型边/簇 F1 为 1.0，但尺度与运动特征的单特征最佳方向曲线下面积约为 0.9973，
  合成集接近确定性可分；G1、assist 和 authority 继续关闭，下一步是 D6 独立审计和更困难的
  真实误差扰动集，不重复训练同一语料。
- D5 主动视觉已完成 1,153,242 样本的完整行为克隆。总体测试精确动作准确率为
  `0.955978`，但 `observe_target` 测试召回率为 0、hold 无正样本、侦察相机精确动作
  准确率为 `0.621823`，因此 bundle 仅允许 development shadow。
- D6 已完成正式数据 outcome/reward 分层和 detached sidecar。D4、D5 有相邻观测结果，
  但缺版本化动作采用/运行 ACK，reward 均为 0 条可用；PPO、反事实和因果训练保持关闭。
- main 已新增真值隔离的 `scalable3d-assignment-plan-runtime-ack-v1`。每次 D3 新计划或明确
  refresh 发布时，main 校验同周期 D7 命令引用的 plan id/version，并逐分配记录命令存在、
  导引模式、门控原因、世界控制回写和保持状态；记录绑定 D3/D7 来源总线序号及规范载荷
  SHA-256。错版本、额外绑定和同版本执行签名变化均失败关闭。D4 v2 消费端已用真实 main
  5v5 seed 41 验证 `evaluation_refresh_applied`，不把刷新误报为新执行计划。
- D6 已实现确认到离线物理状态的只读联接，main 会为有确认的 episode 自动登记 11 项输入和
  SHA-256，写出可复载 input specification、逐 binding 非重叠窗口、JSON、中文报告和 provenance
  manifest。真实 main 3v3 episode 的 2 条确认形成 6 个窗口，在线真值使用为 0；同版本刷新
  由 ACK sequence/timestamp 唯一化，binding/coalition/authority 篡改失败关闭。当前只提供
  有界距离进展诊断，不提供正式 reward、counterfactual 或 causal label。冻结 900 episode
  仍没有该 runtime 证据；paired shadow、保留 seed 和学习实际采用多 seed 证据未完成，PPO、
  assist 和 authority 继续关闭。
- main 已新增 `scalable3d-shared-seed-split-registry-v1`。100 个训练 seed 使用与 D3 v2
  一致的确定性 `60/20/20` 映射，并绑定原训练 seed 注册表 SHA。D4/D5 源外 canonical
  views 已建立，原数据不改写；D6 联合审计已通过 manifest/view/readiness/summary 层的
  seed 身份与哈希检查。D5 补充主动视觉的 100 episode/1200 sample 全样本审计已通过，
  302/302 个制品和 1200/1200 个有限特征满足门限；D3、D4 的正式/补充全样本结构审计也
  已完成。三类 producer 状态均为 complete，但总体准入仍因真实 outcome、reward、paired
  shadow 和保留 seed 证据缺失而保持 partial。
- D4 clean 补充课程已覆盖 hold/replan/quota/transfer=`100/200/200/100`。D5 clean 补充
  课程为 100 episode/1200 sample，覆盖四类观察 intent、wide/zoom 和拦截/侦察角色；
  synthetic ACK 三类各 400 只作故障注入。两套课程均没有可归因结果或 reward。
- D6 联合审计确认原 D5 tracklet 的 99 条未标注边没有可核验 source-observation lineage，
  因此保持 unavailable，没有伪标签回填。clean 补充图 manifest/dataset/composite-view
  SHA-256 分别为 `4b9875fee86b5c425f683a6da23e6af1308bcf2383d3633d4fd6207fe2f25a32`、
  `4c49aebae8040f8a7dace329b5d1769739e2e40d811c3ad5eb733f302ebd8f6f` 和
  `11e8acbdbe268574ead402f2be5c9aa8e3459a7e4147a18e0570df3402892415`。D6 当前
  全量 `423 passed`；PPO、assist 和 authority 均关闭，规则回退强制。
- main scalable 测试当前为 `90 passed`。shared split、全样本 producer 审计、D4 runtime
  adoption、D6 observed-outcome 联接和 D5 clean 困难样本数据门已闭合。下一阶段先训练新的
  D5 图模型并完成内部独立测试，再运行 seed `1000-1019` 保留集和同 seed paired shadow；
  D3/D4 还需冻结正式 reward 口径。只有学习实际采用、运行 ACK、物理结果和非退化证据形成
  多 seed 闭环后，才评审 R0/G1/A1/A2/A3/C1/F1 或 PPO/assist 晋级。
- main 已增加默认关闭的侦察观察线索开关。5v5、3 秒、5 seed 对照中，线索使视觉观测
  增加，但候选边由 128 降至 64；在 D5 完成宽视场保持和跨视角稳定门控前，不进入默认
  生成路径或正式实验矩阵。

### 2026-07-20 阶段状态

- 阶段 1-3 已完成，世界、传感器、真值隔离和集成合同由当前 72 项测试覆盖。
- D1、D2、D3、D4、D5、D7 的 scalable 3D 模块入口已接入 main-owned
  `IntegratedScalableModuleStack`；当前 main 集成测试总计 72 项通过。
- 5v5 规则闭环和 200v200 的 0.25 秒雷达烟测已通过。后者形成 200 条中心航迹、200 项
  分配和 200 路三维导引命令，候选边为 6400/40000；该短时结果不能替代长时多 seed。
- 单一二级、多二级区域 owner 和二级再次失效后的完全分布式 D3 计划已在质点模块栈闭合。
  D7 按区域核对 owner layer、owner node、epoch、lease 和提交模式；缺失或过期证据继续
  fail closed。
- D3、D4 和 D5 的可选学习 bundle 已由 main 显式装配。默认模式仍为 disabled；D3 未通过
  promotion manifest 时精确回退规则代价。D4 后投影建议只有在实际 `assist`、来源
  snapshot/formal decision、有效期、故障代际和一次性 gate 均通过时，才转换为下一周期
  D3 区域提示；D3 再校验当前计划、资源、commit/reserve 和候选边。shadow、重放、严格
  到期和故障代际变化均不生效。D5 bundle 异常时回退几何规则。当前没有通过正式准入的
  checkpoint。
- 5/20/50/100/200 的 0.25 秒雷达短测实时因子依次约为 8.54、2.32、0.61、0.28、
  0.09。200v200 的 D3 分配累计耗时约 1.97 秒，明显高于 D1、D2 和 D7，是当前首要
  性能瓶颈。分阶段耗时已进入 episode 诊断和 `stage_timings.csv`；在线发布总线单列
  计时，递归真值隔离扫描已经过循环安全和重复字段缓存优化。
- D1 无多普勒雷达速度先验和 D2 相关六维后验重复融合问题已经修复。radar-only、seed 17、
  2.2 秒复测中，50v50 为 50 条航迹/50 项分配、实时因子 1.055；200v200 为 200 条航迹/
  195 项分配、实时因子 0.254。短时差额来自首周期漏检后 D3 驻留保持，不是可达性拒绝；
  3.2 秒运行在 `t=3.0 s` 发布版本 2，恢复 200 项分配。
- D3 稀疏代价构造、D5 候选相机对预算、D4 区域建议和 D6 离线规模评估主链已经接入。
  下一阶段需要由 main 从真实 episode 导出整 seed 数据，完成 D5 图网络、D3 代价修正和
  D4 区域策略的训练与 paired shadow。D5 主动视觉规则、学习合同、行为克隆/近端策略
  优化、bundle 和运行时相机 ACK 已接线，但尚无正式训练数据、checkpoint 或至少 20 个
  未见 seed 准入证据。正式结论至少使用 20 个未见 seed。D1/D2 仍需在同批次完成
  NIS/NEES、门控率和高机动 coverage 标定。
- D1/D2/D6 公共评估制品已经接入每个持久化 episode。D1 在线证据、离线真值状态和
  D2 规范映射分别绑定来源 SHA256；D2 身份评估保持显式 `id_switch_count` 和 availability；
  D6 自动生成单 episode 与批量逐 seed/聚合/中文报告。当前 5v5 和双 seed 3v3 回归通过，
  D1 证据通过 `observation_id + measurement_timestamp` 与 D2 规范身份精确联接，不按
  航迹时间区间前向填充。上述回归只证明证据链、真值隔离和聚合合同，尚未完成五档规模
  各 20 个未见 seed 的正式统计。
- 传感器到融合中心的实际批次已经接入确定性通信队列。传感器处理完成时间与网络到达
  时间分离，通信时延、抖动、带宽序列化和丢包会改变 D1 实际收到的批次及
  `arrival_timestamp`，episode 同步输出通信计数和字节统计。D1-D7 组合栈仍为进程内
  调用，尚不能据此宣称模块间分布式网络已经闭合。
- main 已接入真实 episode 学习制品导出。D3 使用模块公开的单帧只读规划证据生成匿名
  代价帧；D4 保存区域图和可选建议；D5 数值图与 `observation_id -> truth label` 离线
  连接结果分文件保存。`run_learning_dataset.py` 在每个 episode 结束后立即写 staging，不保留
  完整 episode 状态；生成计划检查重复 cell、训练/保留评估 seed 交集、干净工作树、输出目录
  和剩余磁盘。批次成功最终化后将 episode 索引固化到根目录，并删除已消费的 D3 重复
  staging；finalizer 失败时保留暂存供恢复。正式模式还会在运行前计算 D5 主动视觉测试 seed
  数，少于 20 时直接拒绝。nominal 2v2/5v5、3 seed、6 episode 开发 smoke 已通过，在线
  真值使用为 0。
- D5 主动视觉已新增整 episode 数据导出。每个决策保存真值隔离快照、规则示范、请求/
  实际动作和同帧相机反馈；在线记录与离线 outcome/reward/counterfactual 文件物理分离。
  main 当前只写显式 unavailable/null 标签，不伪造 reward、反事实或 ACK。D5 已将
  learning/episode dataset 升为 v2、bundle 升为 v3；完整 `(scenario_version, seed)` group
  不可分，同一数值 seed 跨所有场景和规模保持同一 split。三 seed smoke 的主动视觉 107 帧
  因测试 seed 仅 1 个而拒绝最终化，符合失败关闭；正式 D6 标签回填、行为克隆、近端策略
  优化和 checkpoint 准入仍待完成。
- 九类 200v200、每例 2 秒的干净工作树容量探针已完成。9/9 状态有限、在线真值使用为 0，
  最终学习目录 55.36 MB；全部 900 例均按该平均值计算的存储保守上界为 5.54 GB。
  D3、D4 和 D5 跨视角图正常最终化，D5 主动视觉因不足 20 个未见测试 seed 保留 staging。
  存储门已通过，5 GB 运行中停止门继续保留。
- nominal seed 930-932 的第二轮 clean-tree 复测中，总耗时进一步达到 `467.8→144.6 s`，
  staging `225.9→12.4 s`，批次 finalization `116.6→7.3 s`；episode run
  `125.2→124.7 s`。D5 主动视觉三 seed staging 为 `4.05/3.99/4.00 s`，合计 12.04 秒。
  它仍占 staging 96.8%，但制品写入与最终化合计 19.7 秒，低于 episode 计算 124.7 秒，
  D5 writer 系统级阻塞已关闭。不得通过降低采样、删除特征或放松真值隔离继续换取速度。
  runner 已实现 episode 边界暂停、同计划/同提交恢复、连续 progress 与 staging index 复核。
  checkpoint v2 在每个完整 episode 后原子推进；旧 checkpoint 落后时，只有 progress 与
  staging 全部通过计划、顺序和安全校验才允许恢复，并记录恢复次数和行数。开发回归覆盖
  `1+2` 分块、单 episode 后异常续跑、旧 v1 checkpoint 滞后恢复以及计划/重复 index 篡改拒绝。
  2026-07-20 两个正式 45-episode 分块完成，90/90 状态有限、工作树干净、在线真值使用为 0；
  连续生成完成到 209/900 后在第 210 项 `communication_degraded 200v200 seed 64` 触发
  D5 同流多批次边界异常。该未最终化目录保留作故障证据；D5 修复形成新提交后从零重跑，
  不跨提交拼接正式数据。修复后的脏工作树开发回归已让同一失败 cell 完整通过，状态有限、
  在线真值使用为 0，并在 checkpoint v2 的 1/3 边界正常暂停；它不是正式 clean-tree 证据。
  完整 900 episode 与实时性目标仍开放。
- 首版正式训练 schedule 已冻结为 `learning_generation_balanced_v1.json`：100 个生成 seed
  通过五个分块按场景/规模均衡轮换，每个 45 个 cell 各有 20 个 seed，共 900 episode；
  seed 1000-1019 保留为最终评估集。runner 在开始前核对完整笛卡尔目录、逐 cell 分母、
  全局 seed 隔离和 schedule SHA256。执行顺序采用 `round_robin_cells_v1`，每连续 45 个
  episode 各覆盖一次完整场景/规模目录，便于代表性分块检查。该 schedule 只冻结实验设计，
  不表示容量门或训练已完成。
- main 已持久化相机指向和视场，D5 每个视觉周期输出带计划、联盟、通信版本和有效期的
  相机命令。相机执行器只接受非过时命令并发布 ACK；学习 disabled/shadow/assist 均保留
  确定性规则安全外壳。5v5 开发冒烟的 84 条命令及 200v200 单 seed 开发诊断的 1872 条
  命令均被接受，尚未形成配对学习准入和多 seed 可见性收益结论。
- main 已新增 `scalable3d-experiment-matrix-v1` 编排入口。R0/G1/A1/A2/A3/C1 使用同一
  场景/规模/seed 键，F1 限定中心失效、二级失效和高威胁 M 对 N 场景；声明为学习组时
  必须证明对应 bundle 已加载且 assist 实际生效。正式运行强制完整场景目录、五档规模、
  至少 20 个未见 seed、独立训练 seed 注册表、干净工作树和 D6 回灌。当前只完成 2v2
  单 seed 编排冒烟，尚无正式 bundle 和消融结果。
- 实验矩阵现强制使用 `entity_fixed_v1` 传感器随机序列，并按 `comparison_key` 固化剔除
  算法版本后的外生配置 SHA-256。雷达、声学和视觉均按固定目标槽位消耗检测/噪声随机量，
  先前视场或 active mask 不再改变后续噪声位置；普通 episode 仍默认 `sequential_v1`。
  该能力保证传感器随机源可配对，不代表候选策略已获 assist，也不替代 outcome/reward 审计。

## 7. 验收标准

- 200 个目标和 200 个资源无硬编码、数组越界和非有限状态。
- 在线真值字段、`global_track_id` 非法改写、过时计划接受和硬约束违规均为零。
- 名义场景预热后航迹召回率目标不低于 95%。
- D5 压力场景跨视角边分类 F1 目标不低于 90%，错误合并率目标不高于 1%。
- 名义资源充分场景高威胁需求满足率目标不低于 95%。
- 强化学习不得增加重复分配、ID Switch 或安全外壳违规。
- 三维距离不超过 5 米计为物理拦截成功，不要求多个资源同时到达。
- 最终报告至少覆盖 20 个未见 seed，并给出均值、标准差和置信区间。
- 当前 RTX 4050 6GB 环境下模型显存目标不超过 5GB。
- 200 对 200 名义场景争取达到实时速度；未达到时必须输出阶段耗时归因。

## 8. 交付物

交付三维仿真代码、D1-D7 适配器、单元和集成测试、图神经网络与强化学习训练产物、
5/20/50/100/200 实验、多 seed 报告、三维图和 GIF/MP4，以及同步后的 README、PLAN、
GAP、算法文档和系统总报告。

## 9. 保留种子隔离执行（2026-07-21）

### 已完成

1. main 新增 seed `1000-1019` 的 D3/D4 同源双臂运行器。每个 seed 只生成一个规则源
   episode，control/treatment 共享 D1/D2 输入、规划帧、D4 区域快照、通信和故障日程。
2. D3 冻结 bundle 默认绑定已登记的策略版本、manifest SHA-256 和权重身份；D4 使用模块
   冻结的 development binding。身份变化、文件缺失或加载异常均失败关闭。
3. 输出按临时目录完成后原子发布，包含来源谱系、D3/D4 执行收据、顶层 manifest、中文
   报告和 `SHA256SUMS`。manifest 显式记录源提交、脏工作树数量、模型身份、回退原因和
   `PPO/assist/authority=false`。
4. 5v5 专项回归覆盖 20 个 seed、D3/D4 各 40 个 arm、缺 bundle 回退、原子写盘和重复输出
   拒绝。D3 的控制臂精确重放由模块全量测试另行覆盖。
5. detached clean 提交 `6d5bfea` 的 v1 正式证据已完成。20 个源 episode 均为干净、有限状态，
   在线真值使用为 0；D6 已独立校验制品和收据。D3 treatment 为 0/20 applied、20/20 OOD
   fallback；D4 treatment 为 0/20 safe adopted、20/20 aggregate threshold fallback。
6. D3 已确认旧 OOD 拒绝来自把二元 `previous_binding=1` 当作连续高斯特征。合法 0/1 现按端点
   检查，其余 11 个连续特征仍使用原 6σ 门；不写盘复验为 20/20 applied、0 fallback。
7. D4 evidence 已升级为 v2。v1 正式记录的只读分解结果为 OOD、finite、50 ms latency 各
   20/20 通过，confidence 0/20 通过冻结门限 0.6；不降低门限，继续规则回退。
8. main 运行器升级为 `scalable3d-reserved-seed-interventions-v2` 和 D3 safety shell v2，
   manifest/report 增加 D4 分门统计。学习权限和规则回退边界不变。
9. clean 源提交 `78912963b67fe86ee9a8d29186b18a9dd60c460c` 已完成同配置 v2 正式重跑。
   D3 treatment applied/fallback=`20/0`，有效矩阵变化 `20/20`、最终 binding 变化 `0/20`；
   D4 confidence 通过 `0/20`，其余四门各 `20/20`，safe adopted/fallback=`0/20`/`20/20`。
10. D6 提交 `d4e8562` 已完成 v1/v2 consumer、profile/schema 绑定和自包含 v2 篡改测试，并
    生成 profile-bound availability sidecar。D3 同帧 assignment comparison 可用；runtime ACK、
    physical outcome/effect、counterfactual 和 causal 继续为 unavailable。

### 下一步

1. 为实际采用的候选计划取得严格绑定的 runtime ACK 和采用后物理状态窗口，再由 D6 计算
   paired physical outcome/effect；不得用同帧 assignment cost 或零采用回退替代物理证据。
2. D4 后续在独立 calibration split 校准或重训 confidence head，不使用保留 seed 下调 0.6 门限；
   降级策略效果另用中心失效/二级失效快照和独立干预时刻评估。
3. 在保留 5v5 v2 证据的同时扩展 5/20/50/100/200 规模。PPO、assist 和 authority 在独立
   非退化评审前保持关闭。

## 10. D1/D2 有界观测治理（2026-07-22）

### 已完成

1. D1 `ScanInputOrganizer` 已在融合前按量测时间水位线管理完整扫描。量测时刻和到达时刻
   分离，扫描缓冲、声明表和事件历史有上限；重复、冲突、过晚、过期和容量溢出均失败关闭。
2. D2 已接入版本化观测声明账本和 replay coast。新证据按源命名空间、不透明观测标识和
   量测时刻声明；安全水位线之外才允许淘汰。重放不做量测更新、不增加命中、不刷新宽限
   起点，也不生成新航迹。
3. main 将 D1/D2 公开治理字段写入 episode 输出，D6 通过 SHA-256 绑定的在线审计和离线
   侧车读取。在线真值使用、`global_track_id` 本地改写和过时计划接受仍为 0。
4. active-risk 5v5 seed 1005 的 1.1 秒当前路径始终保持 5 条中心航迹，起始 5、重复出生
   0、暂定删除 0、错误合并 0。结束排空把全部 D1 尾部扫描依次融合并留档，只将最终融合
   后验送 D2 一次；待发布的 D1 源观测谱系随该次中心关联批量归档，离线一致性映射保持
   完整。该阶段不发布相机或运动命令。
5. development 快速治理基准已覆盖 20/50/100/200 四档、每档 5 seed、每例 136 帧。
   每例 D1 重排 12、拒绝/过旧/溢出 0、峰值缓冲 3；200 规模 D2 峰值声明
   24170/48000、安全淘汰 2985、溢出 0。离线近邻召回 1.0、错误抑制和错误合并 0、确认
   时延 0.25 秒，在线真值使用 0。
6. 同配置已在 detached clean 提交 `e4d66db02a0b8f1b867a0e81b4a73de84588426b` 完成正式
   复跑。20 个 episode 均为 `formal/clean`，输入策略为 `formal_only`，在线真值使用为 0，
   四档容量、淘汰、召回、错误抑制和确认时延结果与 development 基准一致。200 规模 D1+D2
   峰值内存均值约 58.997 MB，最大 59007120 B。
7. 单 seed、2.2 秒全栈质点烟测在尾部合并前后分别用时 95.41 秒和 60.21 秒，200 规模
   实时倍率由 0.0231 提高到 0.0365。D2 尾部调用由 31 次降为 1 次；当前主要瓶颈为 D1
   融合 35.12 秒和 D3 三次分配 7.33 秒。
8. 当前权威回归为 D1 `163`、D2 `215`、D6 `521`、scalable main `115` 项通过；其余模块
   沿用上一轮已记录回归，未因本批治理改动调整算法。

### 边界与后续

快速治理基准和 clean/formal 复跑关闭了“账本无上限”“没有四档多 seed 容量证据”和
“正式来源未复验”三个治理缺口。该 fixture 不能代替完整传感器融合精度、身份连续性、物理
拦截或 AirSim 证据。后续仍需增加完整质点多 seed 长 episode、真实时钟偏差、遮挡、杂波和
通信退化。D1 小扫描触发全后验重算、D3 200 规模分配时延和 D5/D7 完整闭环仍是 P1。学习
策略在独立非退化评审前继续保持 shadow/fail-closed。
