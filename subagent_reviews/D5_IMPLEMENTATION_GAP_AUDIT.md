# D5 实现差距审计

## 2026-07-22 clean 三种子集成状态

| 缺口 | 当前状态 | 权威证据与剩余边界 |
| --- | --- | --- |
| 性能快照接入 main | **已关闭** | 提交 `8f86192` 的 3 个 clean episode 均持久化 `d5_terminal_performance`，业务 DTO 未增加性能字段。 |
| 性能快照接入 D6 | **P1 开放** | D6 已把三种子标记为 clean descriptive，但当前聚合文件不含 D5 操作数。需按 seed 汇总快照并与阶段耗时联合展示。 |
| 200v200 10 秒终端阶段回归 | **通过当前描述性门** | seeds `42000-42002` 调用次数保持 `116/119/118`，均值 `2.6985 -> 2.5459 s`，下降 `5.7%`；在线 truth 和 `global_track_id` 改写为 0。 |
| 短长序列单次成本 | **P1 开放** | seed 42000 的增长由 `2.696x` 降至 `2.423x`，仍为超线性；116 次调用对应 2493 个图节点和 33315 次局部匹配对比较。需做输入规模正交、多 seed 和更长时段验收。 |
| 正式性能准入 | **P1 开放** | 当前 D6 状态为 3-seed clean descriptive calibration，不是预注册正式实验，也不是 AirSim/硬件实时性或单项优化因果证据。 |

本轮没有新增 P0。权威集成目录为 `research_modules/scalable_3d_simulation/outputs/scalable_3d_long_duration_candidate_20260722_clean_8f86192/`。冻结日志操作数 benchmark 继续作为独立 D5 证据，不与本节系统墙钟结果混算。

## 2026-07-22 三维操作数诊断状态

| 缺口 | 当前状态 | 权威证据与剩余边界 |
| --- | --- | --- |
| 长短序列成本缺少阶段操作数 | **D5-owned 已关闭** | 固定大小快照已覆盖检测转 tracklet、历史更新、候选/几何门、图、评分/聚类、投影、绑定、匈牙利和输出；诊断不进入业务 DTO，不保存逐帧历史。 |
| 单次调用成本增长归因 | **已关闭到 10 秒冻结日志范围** | 23/116 次调用的密度增长仅 `1.090x`，单次成本增长 `2.135x`；每调用节点、投影矩阵单元、绑定矩阵单元增长 `5.815x/7.274x/6.980x`。根因是可见检测、局部历史和中心候选规模增加。 |
| 同批次相机元数据重复校验 | **已关闭** | 完整模板构建 `2493 -> 715`，模板准备剖析耗时 `1.012200 -> 0.532869 s`；只复用全部消费字段相同的模板，变化外参继续失败关闭。 |
| 业务非退化与身份边界 | **关闭并保持回归** | 短/长逐帧业务哈希和最终 binding 哈希均与各自冻结记录一致；在线 truth=0，`global_track_id` 改写=0，所有保守门控未放宽。 |
| 性能旁路接入 main/D6 | **main 已关闭，D6 聚合 P1 开放** | main 已在 clean episode 结束时读取固定大小快照并写入最终诊断；D6 已消费三种子阶段证据，但未聚合 D5 操作数。reset 回归保持计数归零，`TerminalAssociation` 和发布频率未改变。 |
| 超过 10 秒的审计历史与矩阵规模 | **P1 开放** | 局部航迹历史受 missed-frame 生命周期约束；已接收时间戳集合随接受批次由 76 增至 715，用于精确 duplicate/OOSM 拒绝。更长 episode 的窗口化需先定义语义，投影/绑定矩阵还需受控规模多 seed 复核。 |

本次没有新增 P0。权威证据为 `results/scalable_3d_duration_operation_benchmark_20260722.json` 和 `reports/D5_SCALABLE_3D_DURATION_OPERATION_BENCHMARK_20260722.md`。

## 2026-07-22 三维长时性能状态

| 缺口 | 当前状态 | 权威证据与剩余边界 |
| --- | --- | --- |
| 200v200 D5 长时内部超线性成本 | **局部优化已关闭，规模 P1 保持开放** | 固定日志重放已关闭重复物化热点；最终 clean 集成均值为 `2.5459 s`。短长单次成本增长仍为 `2.423x`，需在受控输入规模和更长时段下继续验收。 |
| 语义非退化 | **关闭** | `bound/ambiguous/unbound=1938/36/384`，在线 truth=0，`global_track_id` 改写=0；相机/关联频率、几何/友方/版本门控和决策状态均未放宽。 |
| D5 发布载荷 | **模块内根因排除，main 边界保留** | 10 秒 active vision 93 条约 8.273 MB，terminal association 116 条约 0.779 MB。阶段计时在发布载荷构造和总线序列化前结束；压缩、摘要或降采样涉及 main 消息合同，本轮不修改。 |
| AirSim 和 M 对 N 接口 | **无变化** | 本轮只优化内部索引、投影复用和 DTO 物化；不改变 AirSim 编排、M 对 N 联盟或在线学习准入。 |

## 2026-07-22 正式 paired shadow v2 状态

| 缺口 | 当前状态 | 权威证据与剩余边界 |
| --- | --- | --- |
| 20 seed × 45 cell 正式 paired shadow | **D5-owned 实现与执行已关闭** | v2 覆盖 900 帧、13,344 节点、74,024 边；目录完整，45/45 cell 非退化。report/lineage SHA 为 `b1528af8...40e1` / `03f92ad1...4c1d`。 |
| 同图、同候选、同标签 identity | **关闭** | 900/900 帧图数组在规则、模型和聚类 checkpoint 一致；两臂候选边与 evaluator 标签哈希一致。 |
| 真值隔离与 ID 所有权 | **关闭并保持回归** | 标签评分在两臂推理后执行；同相机边、未标注边、在线真值特征、`global_track_id` 改写均为 0。 |
| 旧/新证据版本一致性 | **关闭** | v2 `authoritative`；旧目录 `superseded_preserved`，旧 report/lineage 哈希保持 `71de83fe...e9a` / `d71bd144...0eb`，未覆盖或删除。 |
| D6 独立审计 | **P1 开放** | v2 仍标记 `pending_d6_external_audit`。D6 必须独立复算输入、report、lineage、实现和 45 cell 门控，不能由 D5 自评自动开放 G1。 |
| 合成保留集难度与真实泛化 | **P1 开放** | 图模型边/簇 F1 为 1.0，但尺度差、尺度率差、角速度差的单特征最佳方向 AUC 约 0.9973；结果可能受合成器近确定性线索驱动。 |
| `shared_global_track_count=1` 覆盖 | **P1 开放** | 当前 74,024 条边全部为 0，互信息 0 bit；取值 1 分层不可用。需新增独立生成机制和该分层样本。 |
| 真实多相机与 M 对 N 运行时准入 | **P1 开放** | 本次是离线合成图评估，不证明真实外观/时钟/外参漂移下的跨视角泛化，也不证明联盟锁定、视觉接管或物理拦截。 |

冻结模型相对规则基线的边 F1 为 `1.000000 vs 0.367980`，簇对 F1 为
`1.000000 vs 0.239234`，模型错误合并对和同目标拆分对均为 0。规则基线错误合并很高，说明该
对照能证明冻结模型在同一合成候选图上优于当前简单规则评分，但不能证明绝对工程性能。特征标签
审查只反映保留集可分性，不是模型归因。后续不得把满分写成真实跨视角泛化或线上准入。

当前没有新增 P0。运行权限保持 `G1=false`、`assist=false`、`authority=false`、
`rule_fallback=true`。D6 独立审计完成也只形成研究影子资格；真实多相机困难数据与失效回退门仍需
单独验收。

当前最终源码已通过 paired-shadow 专项 `5 passed in 3.21s` 和 D5 全量
`534 passed in 141.66s`。后续历史章节按其标题日期保留，不代表 v2 之后的当前缺口状态。

## 2026-07-21 候选召回 P1 状态（历史，已由 v2 更新）

**代码根因已关闭，clean 数据与模型证据重新开放。** 修复前 4,500 帧 clean supplemental 的
370,211 个可能跨相机 pair 中，几何门只拒绝 21 个；最终 8 邻居 cap 从 370,190 条门后边删除
125,158 条。canonical test 候选召回为 `11409/16698=0.683255`。根因是最终 cap 与前置 24 邻居
预算不一致，不是图神经网络分类器或几何安全门。

默认最终 cap 已对齐为 24，并保留每节点最大度数 24、边数 `<=12V` 和确定性几何评分排序。新增
诊断可分别统计几何拒绝与最终 cap 删除。seed 5、`delayed_noisy`、scale 200 的四相机软件回归得到
15/15 同目标 pair、候选召回 1.0、实际最大度数 12；cap=2 的失败压力用例保持确定性、严格上界和
几何门不变。专项 `20+13 passed`，D5 全量 `529 passed in 122.96s`。

P1 仍开放：main 需在 clean commit 上重建 4,500 帧 supplemental，重生成 composite admission view
并确认三个 split 候选召回均不低于 0.95；随后重新执行内部训练、保留 seed `1000-1019` 评估和
paired shadow。旧 245,032 边、旧 manifest/view SHA 和 `training_readiness=pass` 是修复前证据，
不能晋级当前实现。G1、assist、authority 保持关闭。

## 2026-07-21 保留 seed 评估管线状态（历史，已由 v2 更新）

| 项目 | 状态 | 证据与边界 |
| --- | --- | --- |
| `1000-1019` 独立 producer | 代码与 smoke 已闭合 | 正式 profile 固定 20 seed×45 cell=900 帧；不调用训练 registry，不写 formal/supplemental，目标不存在且原子发布。1 seed×2 cell smoke 已复载。 |
| 数据与真值安全 | 代码与测试已闭合 | 在线图匿名；truth 只在 label/lineage；默认几何候选门不变；同相机边、未标注边、训练 seed、hash/lineage 篡改和路径重叠失败关闭；不创建或换绑 `global_track_id`。 |
| development bundle 评估 | 代码与 smoke 已闭合 | 固定使用 bundle validation 温度/阈值，输出整体和逐 cell 指标及延迟；评估前后复核权重、配置和 corpus 哈希。随机 bundle 保持 `fail_closed`。 |
| 正式 900 帧 held-out | P1 开放 | 尚未实际生成，也没有正式 manifest SHA、全样本计数、指标和成本。须等待 clean 内部训练 bundle 后由 main 在 detached clean worktree 运行。 |
| paired shadow | P1 开放 | 尚未在相同 `1000-1019` seed 上比较规则路径和开发模型。held-out 即使通过也不能替代该证据。 |
| G1/assist/authority | 关闭 | 报告固定为 false；正式 held-out 与 paired shadow 未完成前不得晋级。 |

新增专项为 `17 passed in 1.09s`，D5 全量回归为 `527 passed in 120.93s`。该变化是离线图数据与
评估能力，不改变 AirSim、实时关联、相机命令或 D7 交接合同。45 帧成本 smoke 得到生成与复载
0.686 s、613,567 bytes；正式 900 帧仅有约 14 s/12.3 MB 的线性估算，仍缺实际制品和全量指标。

## 2026-07-21 Composite 训练适配器 GAP 状态（历史预检）

**只读训练入口与预检子项已关闭，模型证据仍是 P1。** D5 已实现 formal + supplemental strict
loader、固定训练 profile、完整 seed/cell/标签/同相机互斥审计和脏工作树正式训练阻断。实际
preflight 复载 4,972 帧、245,040 边，`60/20/20` 与每 split 45 cell 均通过，未训练模型。

**D6 内部模型报告生产接口已闭合，实际三件套仍不可用。** clean 全量训练完成后，D5 可从实际
training report、`weights.pt` 和 bundle `manifest.json` 生成精确
`d5.tracklet-graph-model-evaluation.v1`。cell `sample_count` 使用已标注候选边数。专项正负测试已
覆盖哈希、指标 availability、cell 完整性和保留 seed；报告不包含权限字段。由于本轮没有正式训练，
D6 当前仍只能消费 data support，不能取得实际 internal model test 三件套。

开放 P1 为：main 在提交后的 detached clean worktree 执行固定训练；D6 复核实际三件套；保留 seed
`1000-1019` 独立评估；同 seed paired shadow。全部完成前 G1、assist、在线与相机控制权限保持关闭。
本轮专项 `12 passed in 1.05s`，D5 全量 `510 passed in 121.82s`。

## 2026-07-21 Tracklet 困难样本 GAP 状态（历史首轮语料）

**困难样本 producer、clean 数据来源和训练数据支持子项已闭合；模型与 G1 未闭合。** 冻结正式语料 99 条未标注边的
194 个缺失端点均没有可精确证明的 offline observation lineage，可靠回填为 0，全部继续
`unavailable`。独立 supplemental producer 实际生成 4,500 帧、66,726 节点和 245,032 条默认几何门
候选边，正/负/未标注为 `57292/187740/0`，标签可用率 100%，正式源重复违规和保留 seed 泄漏均为
0。该结果关闭“缺少独立困难负边、完整标签和 candidate-recall 分母”的数据支持子项。

detached 组合视图选入 472 个完整正式帧和 4,500 个补充帧。train/validation/test 的无边比例为
`8.68%/10.34%/10.45%`，负边为 `112314/37694/37734`，可评价同目标 pair 为
`50103/16683/16698`，标签可用率和双类 cell 比例均为 100%。既有数据门全部通过，未降低时间、
视场、极线、射线、重投影、协方差或度数门。

main 已基于 clean commit `79b2550ce2ef407c7cfcc653ce04a80fe2226c06` 在 detached worktree 完成
同配置复生。补充 manifest/view SHA 为
`4b9875fee86b5c425f683a6da23e6af1308bcf2383d3633d4fd6207fe2f25a32` 和
`11e8acbdbe268574ead402f2be5c9aa8e3459a7e4147a18e0570df3402892415`；dirty=false，数据支持与
`training_readiness` 均 pass，原 provenance blocker 关闭。

该 pass 只表示数据可进入后续训练，不表示模型已经存在。模型训练、`.pt` 生成、保留 seed 独立
评估、同 seed 影子对照和 promotion 尚未开始，仍是开放 P1；G1/assist/在线与相机控制权限继续
关闭。clean 制品和组合视图已严格复载，专项 `12 passed in 5.40s`；此前 D5 全量
`498 passed in 124.90s`。正式源全树指纹复载前后不变。

## 2026-07-21 Supplemental BC 全样本 GAP 关闭证据

**supplemental behavior-cloning full-sample audit 子项已关闭，D6 跨模块准入仍开放。** D5 新增只读
fail-closed 审计入口并对 clean commit `13e37286d2996a227924bb1a8e2766e52116a534` 的实际 100-episode
制品完成验证。接受阈值为 100 episode、1200 sample、canonical episode `60/20/20` 与 sample
`720/240/240`、dataset 302/302 个 checksummed 文件一致、online/offline/descriptor 各 100 个、全部
35 维候选特征有限、版本与 caller-owned `global_track_id` 一致，以及 truth/reserved/dirty/audit
violation 均为 0。实测 1200/1200 样本通过，形成 7800 个候选特征行，规则示范 1200/1200 在候选集
唯一，intent/FOV/role 为 `200/600/200/200`、`1000/200`、`600/600`，违规为 0。

tracked 证据为 `results/active_vision_supplemental_bc_full_sample_audit_20260721.json` 和
`reports/D5_ACTIVE_VISION_SUPPLEMENTAL_BC_FULL_SAMPLE_AUDIT_20260721.md`，内容 SHA256 为
`a11b65596a4c416deba6d0cb35dcc0c32342a5bae0481291d43e8de0e26550dd`。dataset/view/config/training-
registry/shared-registry/producer-summary-content SHA 仍为
`0c474ee1b0bab34a46c2ebce328761983cf2ecc757da30c2d3d2e03a06cd1acf`、
`0ab1a4a6bdd439f6c8a74df5059de3c4950791fba35a1b9514942e83779f72a8`、
`e93ca6310338be5db4539fac195f5257e28d16a64b78b1a0351bf6aeca01fcee`、
`2ab928a476a4430b99326f245222f058bc5be5025158134ba89b01b3dec7815f`、
`68608d29d1f733beea87f1faf06464fededb68a9c2972c51c10cd4c2160f032f`、
`0577c73810413ced6277e679477422f467cb2db094f1d376e39e4cbb2a3abd65`。supplemental 树仍为
308 files/约 2.2 MiB，正式 900-episode 树仍为 43973 files、SHA256
`8ffbe5cf044d121163c8acc3dce1bbd54e14bb6b211b8e1cf440f24c93294fca`。

该关闭项只证明补充规则教师数据可供 D6 继续做跨模块学习准入审计，不追认旧模型或开放 runtime。
synthetic `applied/rejected/missing=400/400/400` 不是实际 ACK；reward/outcome/counterfactual/causal
仍为 `0/1200 available` 且未补零。main/D6 准入、真实 ACK/outcome attribution、paired shadow 和
上述离线标签仍是开放 P1；PPO/assist/online/camera authority=false，规则回退必需。本轮未训练、
未运行 AirSim、未生成 `.pt`，未修改 supplemental 或正式 900-episode 数据树。新增专项
`4 passed in 35.72s`，D5 全量 `486 passed in 119.63s`，零失败阈值通过。

## 2026-07-21 B1b2 clean evidence

main 已在 detached clean worktree `13e37286d2996a227924bb1a8e2766e52116a534` 完成 100 episode/800 segment/1200 sample 与 canonical seed/episode `60/20/20`、sample `720/240/240` 的实际生成；intent/FOV/role/故障注入 ACK 分别为 `200/600/200/200`、`1000/200`、`600/600`、`400/400/400`，truth/reserved/dirty/audit 均零违规。dataset/view/config/training-registry/shared-registry/summary-content SHA 依次为 `0c474ee1b0bab34a46c2ebce328761983cf2ecc757da30c2d3d2e03a06cd1acf`、`0ab1a4a6bdd439f6c8a74df5059de3c4950791fba35a1b9514942e83779f72a8`、`e93ca6310338be5db4539fac195f5257e28d16a64b78b1a0351bf6aeca01fcee`、`2ab928a476a4430b99326f245222f058bc5be5025158134ba89b01b3dec7815f`、`68608d29d1f733beea87f1faf06464fededb68a9c2972c51c10cd4c2160f032f`、`0577c73810413ced6277e679477422f467cb2db094f1d376e39e4cbb2a3abd65`，正式 900-episode 输入树前后 SHA 同为 `8ffbe5cf044d121163c8acc3dce1bbd54e14bb6b211b8e1cf440f24c93294fca`。clean supplemental producer/canonical evidence 子项据此关闭；后续 supplemental BC 全样本子项也已由上节关闭。synthetic ACK 不是真实 ACK，四类 label 仍为 `0/1200 available`，PPO/assist/authority 继续关闭，下一步为 main/D6 跨模块准入审计，本次未训练、未运行 AirSim。

## 2026-07-21 主动视觉课程 B1b2 GAP 状态

**100-seed producer 软件及 clean supplemental producer/canonical evidence 子项均已关闭。** D5 新增
`active_vision_curriculum_dataset.py` 与 CLI。调用方必须显式给出中心拥有的 `global_track_id`；
producer 不生成或换绑身份。它严格读取 100 个 training seed，拒绝 seed 漏/多、与
`1000-1019` 重叠、registry schema/content/source/assignment 不一致，并绑定 training/shared 文件
SHA、dataset config/manifest 和 canonical view/readiness SHA。输出必须不存在；全部制品先在 sibling
临时目录通过 finalize、lazy loader、canonical `60/20/20` 和逐样本审计，再由 `os.replace()` 发布。
两个 registry 各自的父目录均视为受保护 source root；嵌套正式布局由外层 training root 覆盖，分离
布局分别保护。output 与两类 tracked 报告等于或位于任一根下时，在创建任何制品目录前失败关闭，
registry 哈希保持不变。

**覆盖与不可用边界已固化。** 100 seed 各调用一次 B1b1 builder，形成 100 episode、800 segment、
1200 sample；canonical episode 为 `60/20/20`、sample 为 `720/240/240`。四类 intent、wide/zoom、
interceptor/recon、版本单调和 caller-owned ID 均逐 episode 复核。applied/rejected/missing 各 400，
仅代表每 seed `4/4/4` 的确定性故障覆盖，不代表真实 ACK 分布、outcome 或 reward。全部 offline
reward/outcome/counterfactual/causal label 显式 unavailable；synthetic 与 dirty provenance 明示，
dirty 只能得到 `fail_closed_dirty_source`。PPO、assist、online authority、camera command authority
全部 false，规则回退必需。

curriculum Markdown 的标题、说明和约束现均为中文，并继续声明 `4/4/4` 只是故障注入覆盖。
2026-07-21 新增专项 `15 passed in 71.87s`，D5 全量 `482 passed in 83.05s`。tmp_path fixture 是软件
阶段历史验收；其后 main 已在 clean revision `13e3728` 生成并归档实际 supplemental output，关闭
clean producer/canonical evidence，且正式 900 episode 未修改。后续 supplemental BC 全样本审计已
由本文顶部证据关闭。本轮未训练、未运行 AirSim。开放项只剩 main/D6 跨模块准入、真实 runtime
ACK/outcome、reward/counterfactual/causal、paired shadow 及
PPO/assist/authority 准入。README、PLAN、三份 D5 review 及模块内原理、算法、AirSim、实验文档已同步。

## 2026-07-21 主动视觉课程 B1b1 GAP 状态

**单-seed 内存 producer 软件子项已关闭。** D5 新增配置化
`build_active_vision_curriculum_episode()`。调用方提供 source identity、角色相机/资源 ID、版本起点
和中心拥有的 `global_track_id`；producer 只读复用中心 ID。任意非负整数 seed 生成 1 个
`ActiveVisionEpisodeRecordV2`，负 seed 失败关闭。构造过程没有文件 I/O，也没有 canonical、CLI、
报告或 AirSim 入口。

**固定覆盖不绕过规则和安全执行。** 8 个片段共 12 个连续样本，精确包含
`hold=2 / observe_target=6 / reacquire=2 / search_sector=2`、`wide=10 / zoom=2`、
`interceptor=6 / recon=6`。两个角色都覆盖四类 intent、两类 FOV 和 applied/rejected/missing。
动作全部由 `DeterministicLookAtScanPolicy + ActiveVisionControllerV1` 产生，三帧 observe 片段通过现有
稳定门得到 `WIDE/WIDE/ZOOM`，随后才调用 `DeterministicCameraCommandExecutor`；没有手工拼装
decision/effective action 补类别。

**版本、ACK 和在线隔离合同通过。** 时间严格递增、序号为 `0..11`，plan/coalition 单调且同片段
稳定，communication 每样本递增；snapshot、action、sample 和 ACK 版本一致。执行器调用始终满足
`command_version == action.communication_version`。ACK 精确为 `applied=4 / rejected=4 / missing=4`；
accepted 与 feedback 最近接受版本一致，rejected/missing 不修改执行输入反馈或推进版本。在线 record
不含 truth/actor/object identity，不创建或改写 `global_track_id`；未生成 reward、outcome、
counterfactual 或 causal label。同 seed 对象和规范序列化确定，调用方输入保持不变。

2026-07-21 新定向测试 `12 passed`，主动视觉关联回归 `56 passed`，D5 全量
`467 passed in 10.40s`，`py_compile` 通过。本子项只证明确定性内存课程及故障注入 ACK 语义，不把
`4/4/4` 解释为真实 runtime 分布或动作收益。B1b2 的多 seed staging/finalization、canonical、CLI
和统计软件、clean producer/canonical evidence 及 supplemental BC 全样本审计现均已关闭；main/D6
跨模块准入、真实 runtime ACK/outcome、reward/counterfactual/causal、paired shadow 仍开放，
assist/PPO/authority 继续关闭。

## 2026-07-21 主动视觉相机执行器 B1a GAP 状态

**模块内执行与 ACK 语义的软件缺口已关闭。** D5 新增确定性 camera command executor。执行器以
现有 `ActiveVisionSnapshotV1`、`ActiveVisionActionV1` 和 `ActiveVisionCameraFeedbackV1` 为输入，
先调用既有安全 validator，再检查反馈态、命令版本和可选运行时故障。成功执行才更新相机姿态、FOV
与 `last_accepted_command_version`，并生成 `accepted=true/status=applied` 的现有 ACK DTO。拒绝时
返回 `accepted=false/rejected_<reason>`，输入反馈保持不变。ACK 缺失单独标为 `missing`，不更新
反馈，也不计作 applied。

拒绝覆盖动作过期、计划/联盟/通信版本不一致、相机忙、相机不可用、运行时 FOV 不支持、既有
validator 判定的非法动作以及非递增 command version。ACK 始终携带 action 的当前计划、联盟和通信
版本；成功 command version 与反馈最近接受版本一致。applied、rejected 和 missing 均已通过现有
episode sample 构造合同，其中 missing 保持 `runtime_ack=None`。执行器不创建或改写
`global_track_id`，truth-like action payload 在执行前失败关闭。

2026-07-21 定向结果为 `18 passed`，D5 全量为 `455 passed in 12.18s`。B1a 阶段当时未运行 AirSim、
未生成课程数据、未接真实相机 runtime，也未训练或晋级模型。其后 B1b2 已关闭 producer、canonical
软件及 clean evidence，supplemental BC 全样本审计也已关闭；main/D6 跨模块准入、真实
applied/rejected/missing 与 outcome、
reward/counterfactual/causal、paired shadow 仍为 P1，assist、PPO 和 authority 继续关闭。

## 2026-07-21 主动视觉宽视场门 GAP 状态

**规则缩放抖动的软件缺口已关闭。** `DeterministicLookAtScanPolicy` 现在按
`camera_id + global_track_id + plan_version + coalition_version` 维护连续帧计数。默认窗口为 3 帧，
达到窗口前保持 `OBSERVE_TARGET + WIDE`；达到窗口后仍需通过原有投影不确定度门才允许 `ZOOM`。
重复帧不累计，`N=1` 可恢复旧即时缩放行为，旧调用不需要增加参数。

**失败关闭边界保持。** 计划、联盟、目标、时间或证据回退会重置状态。低置信、遮挡/可见性不合格、
投影不在视场、通信异常、版本不一致、友方保留冲突和相机忙均不能积累缩放资格。多个当前分配投影
的质量差小于默认 `0.05` 时按歧义处理并重捕获。状态只在本相机内维护，中心
`global_track_id`、几何门、同相机互斥和友方门均未变化。

**clean producer evidence 已关闭，真实 ACK 仍开放。** 当前主动视觉 snapshot 不携带 runtime ACK 或相机反馈中的
最近接受命令版本。阶段 A 只读取已有 busy 字段，没有伪造 ACK，也没有扩 DTO。B1b2 已实现 synthetic
supplemental producer，clean 制品及 supplemental BC 全样本审计已由 `13e3728` 绑定证据关闭；正式
900-episode 数据仍为 `hold=0`、`reacquire` 主导且无 applied-action 归因。因此 main/D6 跨模块准入、
真实 ACK/outcome、
reward/counterfactual/causal、paired shadow、assist、PPO 和 authority
状态均未关闭。定向组合测试 `47 passed`，D5 全量
`437 passed in 10.28s`；未运行新 AirSim 或模型实验。旧 v5 bundle 的 code provenance 对应修改前
实现，严格 loader 应拒绝加载；该失败关闭不等于完成模型重训或准入。

## 2026-07-21 canonical split GAP 状态

**D4/D5 split 身份不一致已关闭。** D5 新增两个 detached canonical view，严格绑定原 dataset
manifest/content、training seed registry、shared registry file/content/assignment hash 及 source/
consumer schema。两类数据均按完整 episode 使用同一数值 seed `60/20/20`，保留 seed
`1000-1019` 泄漏为 0。源数据树内容哈希前后不变，原 manifest 未改。默认旧加载路径也未改变。

**模型准入 GAP 未随 split 对齐关闭。** 图数据 canonical 分桶后仍有 `12532/12851 (97.52%)`
无边帧，train/validation/test 负边为 `13/4/2`，candidate recall 仍不可完整评价。训练与 promotion
维持 `fail_closed`。主动视觉 canonical 样本为 `695705/229651/227886`；已绑定的全量审计仍显示
`hold=0`、`observe_target` 占比低且召回为 0、`reacquire` 主导、所有运行动作 disabled、无 applied
action ACK/reward/counterfactual/causal attribution。状态维持 development shadow-only，assist=false，
PPO=false，规则回退必需。

本轮只关闭“跨模块训练 split 身份无法对齐”这一数据治理 P1。旧图开发模型和主动视觉 v5 bundle
仍绑定原 split，本轮未重训，不得用 canonical view 追认旧指标。剩余正式 producer 证据缺口保持：
增加真实困难负边与候选召回分母；在非 synthetic 数据中补主动视觉少数意图、侦察相机动作、ACK 和
因果标签；完成独立 seed 的 paired shadow。main 需同步 VERSIONING 中的 view schema 与正式哈希。

## 2026-07-20 主动视觉行为克隆 P1 状态

**全量行为克隆训练管线已关闭，运行准入 P1 仍开放。** 正式数据的完整性、整 seed 分割、保留 seed
隔离和规则示范可用性通过。900 个 episode、1,153,242 个样本中，train/validation/test 为
`685005/238354/229883` 样本和 `60/20/20` 个唯一 seed。固定 seed 在完整 train split 上完成
5 epoch，未使用子样本替代正式训练。

test 损失为 `0.109311`，精确动作准确率为 `0.955978`，但该数值不能支持准入。数据中
`reacquire=1,062,876 (92.16%)`、`observe_target=19,838 (1.72%)`、`hold=0`。test 的
`observe_target` 4,051 个样本全部被判为 `reacquire`，召回率和 F1 为 0；侦察相机精确动作准确率
为 `0.621823`，明显低于拦截相机的 `0.970229`。模型尚未覆盖关键观察和保持行为。

校准 P1 也未关闭。验证集温度缩放 `T=0.906731` 后，test NLL 从 `0.109311` 降至 `0.108656`，
15-bin ECE 从 `0.020389` 升至 `0.020856`，不满足写回 bundle 的理由。当前 bundle 固定
`development_shadow_only`、assist=false、PPO=false、rule fallback required；assist 加载失败关闭。

剩余 producer 缺口为：增加独立 seed 的 hold/observe/recon/FOV/边界动作示范；实际请求 shadow
动作并记录 runtime ACK 与执行后 outcome；建立独立 reward/counterfactual/causal label；完成至少
20 个未见 seed 的 paired shadow 非退化验收。D6 给出的 1,063,214 条 observed outcome 没有动作执行
归因，不能用作 reward。该段是 2026-07-20 原 split 状态；2026-07-21 已用 canonical 只读视图关闭
split 身份不一致，但联合模型仍因标签和准入门关闭。该状态没有新增 P0；规则主动视觉、版本
门、友方冲突门、中心 `global_track_id` 只读和相机命令安全门保持不变。

开发权重 SHA256 为
`829d016611967d7f7adddcb58c99a96e418486e33a7fc987042a16d294c2b77b`，只位于 ignored outputs。
正式统计见 `results/active_vision_bc_formal_20260720.json` 和
`reports/D5_ACTIVE_VISION_BC_FORMAL_20260720.md`。D5 全量 `414 passed`。main 仍需在 VERSIONING
登记 active-vision bundle v5 和本地权重规则。

## 2026-07-20 正式图数据训练准入 P1 状态

**数据生成子项已关闭。** main 在新修复链上完成 900 episode 正式生成，D5 图数据包含 12851 个
图帧。D5 strict loader 已复算全部 graph/label SHA256，并校验 schema、feature order、整 seed
split、split/training-set hash。train/validation/test 为 `60/20/20` 个唯一 seed，互不泄漏；
`1000-1019` 保留评估 seed 未进入训练。

**图模型准入 P1 仍开放。** `12532/12851` 帧无候选边，edge-free 为 `97.52%`；仅 319 帧含边，
总边 480。train/validation/test 负边为 `11/4/4`，且 19 条负边全部集中在 `200v200` 的 5 类
场景。partial candidate recall 为 `4/4、1/1、1/1`，分母过小且标签可用率仅约
`3.96%/3.06%/3.42%`。训练门共有 15 项失败，不能把局部 recall=1.0 解释为候选召回已验证。

**软件门已关闭。** 新增只读 readiness audit CLI，冻结 edge-free、类别支持、candidate recall
availability/pair 分母、场景规模覆盖和测试 seed 门。正式训练仍拒绝不完整验证真值；显式
development-only 模式只计算已标注边指标，误合并率和完整候选召回保持 unavailable。bundle v3
绑定数据、split、配置、特征、readiness audit 和实现代码哈希，并固定不具备 G1/assist 权限。

**开发训练证据不关闭 P1。** 固定 seed `20260720`、40 epoch、CPU 训练得到验证/测试 F1
`0.9804/1.0`，但每个分割只有 4 条验证/测试负边，完整误合并率和 candidate recall 不可计算。
权重 SHA256 `9bbe53d6...35cbf2d` 两次一致，只保存在 ignored outputs；promotion 仍为 `fail_closed`。
2026-07-20 图训练专项 `16 passed`、D5 全量 `412 passed`。

**下一 producer GAP：** 增加独立 seed 下的多相机共同可见窗口、密集交叉/遮挡/重捕获和在现有
几何门内可混淆的异目标，补齐候选裁剪前 pair 分母与全部评价 tracklet 离线标签。不得复制样本、
降低身份/几何门或把开发模型接入 G1。main 另需同步 main-owned `VERSIONING.md` 的 bundle v3 和
无 git-lfs 权重策略。

## 2026-07-20 同相机多批次 P1 状态

**正式证据：** `learning_generation_v1_oosmfix` 已写入 209 条进度（sequence 0-208），随后在
`communication_degraded` 200v200 因一次 D5 调用出现同相机多个 batch 而失败。运行周期排空通信
积压时该输入合法；“每次调用每流一批”是适配器假设，不是传输合同。

**D5 代码级 P1 已关闭：** 全部输入先做结构、真值隔离、有限性和时序事务预检，再按 arrival 主键
规范顺序逐批更新各自 tracker。重复 arrival、已提交 arrival 回退和重复 measurement 在任何状态
变化前拒绝。OOSM 仍保留双时间戳且不倒写状态。`process()` 保留全部批次审计，图只取每流最后一次
有效状态更新，避免相同稳定 tracklet key 的多个时间版本和重复相机几何进入同一快照。

**回归证据：** 同流两正常批次、正常/OOSM 混合、历史正常/OOSM measurement 重传、三类原子失败、
多相机多批次正反输入均通过。2026-07-20 定向 `31 passed`、D5 全量
`410 passed in 11.68s`，语法和格式检查通过。实现没有 truth/
actor/object ID 入口，没有中心 ID 写接口，也没有固定规模。

**系统级 P1 仍开放：** 绑定 `c5a9f6d` 的 209 条历史进度只保留为故障证据。main 必须依据
`VERSIONING.md`，在同时包含 D5 与 runner 修复的新干净提交上使用新输出目录，从 sequence 0 重建
正式 900 episode；不得恢复、续写旧目录或跨提交拼接。新数据集还需验证 900 条进度、45 个场景/
规模 cell 各 20 seed、finite、clean、online truth use=0、checkpoint、manifest 及 D5 graph/
active-vision 最终化。OOSM 信息利用率和固定时滞重放仍是后续研究项，不属于本次阻塞修复。

## 2026-07-20 通信退化 OOSM P1 状态

**根因：** 正式 45-episode 分块在 sequence 29 的 `communication_degraded` 200v200 进入
`Scalable3DTerminalAdapter` 后，camera-local tracker 对 measurement 时间执行单调检查。main 的
批次已按 arrival 时间释放；通信抖动造成旧 measurement 后到属于合法 OOSM。原合同混淆了量测
时钟与接收时钟，直接抛出 `camera scan timestamps must be monotonic within an episode`。

**D5 代码级 P1 已关闭：** tracker 以 arrival 为接收顺序，以 measurement 高水位保护当前状态。
合法 OOSM 不再抛错，也不回退运动学、框、命中、漏帧或 ID 状态；批次保留双时间戳并以
`oosm_ignored`、累计计数和高水位诊断显式输出。重复 measurement、重复 arrival 和 arrival 回退均
在提交前失败关闭。不按 measurement 改写接收语义，也不改写时间戳；同调用多批次的 arrival 规范
顺序见上节。没有 truth ID 输入，没有 `global_track_id` 创建或换绑。

**代码证据：** arrival 单调/measurement 乱序正例验证 OOSM 不更新状态且下一正常帧保持局部 ID、
命中数和速度基准；三个负例验证 arrival 回退、原样重复及同 measurement 重传不污染 tracker。
2026-07-20 定向 `24 passed`，D5 全量 `403 passed in 9.74s`，接受阈值为零失败。

**OOSM 系统阻塞已关闭，信息利用 P1 仍开放：** main 后续在修复提交的新目录完成首个 45-cell和
一次 checkpoint resume，累计 209 条完成进度，原 sequence 29 OOSM 异常未复现。后续中断属于上节
同相机多批次限制。当前策略仍保守丢弃 OOSM 对 MOT 状态的更新；正式 900 episode 完成后应统计
占比和关联影响，必要时再研究有界固定时滞重放。

## 2026-07-20 clean-tree 200v200 postopt2 后的 P1 判定

main 使用 nominal 200v200、2 s、seed 930-932，在提交
`45b36500dc3c6935b1f116614993e291041eb12d` 上完成 clean-tree postopt2 复测。证据目录为
`capacity_probe_v2/nominal_timed_postopt2/`。三场均为有限状态，
`repository_dirty=false`、online truth use=0；D5 graph dataset 正常最终化。

**D5 writer P1 已系统级关闭。** active-vision staging 从 postopt1 的
`41.5623/43.2639/41.2271 s` 降至 `4.0494/3.9898/3.9995 s`。每场 artifact staging 为
`4.1704/4.1311/4.1357 s`，三场合计由 `126.4682 s` 降至 `12.4372 s`。同配置、同 seed、干净
工作树和真值隔离均保持，D5 微基准结论已经得到真实 episode 端到端计时确认。

**历史两个子项均保持关闭。** postopt1 已把总 finalization 从 `116.5624 s` 降至 `7.7377 s`；
postopt2 为 `7.2777 s`。D5-owned writer 修复此前已证明 200-camera/400-track fixture 构造
`2.3597→0.1097 s`、materialized load `2.3948→0.1802 s`，且 3,536-sample 制品 writer
`3.5529→0.7313 s`、输出字节完全相同。postopt2 将该软件证据提升为系统级关闭证据。schema、
采样、snapshot/action/feedback/ACK、truth-free、离线标签分离、SHA256、只读和 whole-seed split
均未改变。

**仍开放的正式数据与准入 P1：** postopt1 到 postopt2 的总生成由 `262.2866 s` 降至
`144.5513 s`，episode run 为 `127.9871→124.7415 s`。这不是在线仿真实时性证据。三 seed 只能
形成 1 个测试 seed，active-vision finalizer 以 `insufficient_unseen_test_seeds` 失败关闭并保留
staging。正式 900-episode corpus、BC/PPO、至少 20 个未见测试 seed、checkpoint、paired shadow
和 assist 准入均保持开放 P1。

## 2026-07-20 主动视觉 staging/finalization 开销 GAP 状态

**D5-owned 重复工作子项已关闭：** 非物化 stream audit 不再为每条 sample 构造并递归扫描共享
snapshot，只保留完成动作、版本、反馈、ACK、中心引用和顺序校验所需的摘要。同一次 finalize 对
每个 episode 只做一次 online/offline 内容审计，并在文件设备号、inode、大小和修改时间未变化时
复用实际 SHA256 与 episode 审计证据。公开 audit 不接受内部证据，仍从磁盘独立完整复核。

**确定性证据：** 6 episode × 48 camera × 96 track 的计数回归中，finalize online/offline parse
由 `12/12` 降至 `6/6`，SHA256 调用由 `67` 降至 `20`，20 个实际制品各一次；独立 public audit
另执行 `6/6` 次 parse 和每制品一次哈希。200-camera/400-track 合成 stream audit 辅助墙钟约
`9.81→0.37 s`，已有 nominal/dense 200v200 gzip 独立 audit 约 `2.08/2.21 s`。数据专项
原阶段为 `16 passed`、D5 全量 `398 passed in 15.75s`；本次新增 writer 等价性与篡改回归后为
数据专项 `18 passed`、D5 全量 `400 passed in 9.74s`。墙钟不是单元测试硬门。

**合同状态：** schema/version、采样频率、训练特征、online truth-free、离线标签物理隔离、
SHA256SUMS、只读制品、whole-seed split 和 fail-closed 均未改变。缓存期间文件变化新增稳定
`artifact_changed_during_audit` 拒绝。正式约 900 episode clean-tree staging/finalize 峰值、吞吐、
故障恢复及跨模块归因仍是 P1；用户提供的整 staging 时间不能全部归因于 D5。

## 2026-07-20 主动视觉整 episode 容量与流式训练 GAP 状态

**D5-owned 软件阻塞已关闭：** `active_vision_episode_dataset.py` 的 online record v2 使用确定性
gzip JSONL。每个 episode/cycle 的相同 snapshot 与 camera feedback 按 SHA256 key 只保存一次，
sample 保存引用以及完整规则示范、requested/effective action、三个版本和可选 ACK；没有删字段。
合同按输入 camera/target/resource 数量运行，不写死 2v2、5v5 或 200v200。

**在线/离线隔离保持：** online writer/stream audit 递归拒绝 truth/actor/object identity，只允许
中心 `global_track_id` 只读引用。offline reward/outcome/counterfactual/causal label 在 episode
结束后按 `sample_key + observation_key` 写入独立目录。offline staging 核验文件 SHA、episode UID、
source identity、对象 key/引用、完整 sample 合同和 join key，使用 `materialize=False`，不重建完整
record。未知中心引用、局部换绑、中心版本/时间回退和篡改均失败关闭。

**跨 episode 内存阻塞已关闭：** finalizer 的 staged 内容审计逐 episode 调用流式 reader，最终
结构复核复用同一次调用内仍有效的审计证据；不调用兼容全量 dataset loader，也不跨 episode 累积
record/sample。新增
`load_active_vision_episode_dataset_lazy()` 与 `LazyActiveVisionEpisodeDataset`；BC/PPO/完整 episode
均可按 split 迭代，每次只物化当前 episode。BC 不读取 offline label，PPO 每 episode 对任一 reward
unavailable/null 立即拒绝。旧 `load_active_vision_episode_dataset()` 仅保留小数据兼容。

**split、availability 与制品审计：** 完整 `(scenario_version, seed)` group 保持不可分，同一数值
seed 的所有 scenario/scale group 原子分配；test seed 对 train/validation 完全未见。少于三个唯一
seed 或少于声明 unseen test seed 失败关闭，正式默认门为 20。manifest、`SHA256SUMS`、source
Git/config、split/training-set SHA、只读与 reward null 语义均未削弱。复核 `tracklet_dataset.py` 后
同样改为共享 seed 原子 split，tracklet dataset/bundle 均为 v2。

**schema 与 bundle：** learning dataset 保持 v2；去重落盘不兼容旧文件，故 episode dataset 为
v3、descriptor/record/sample 为 v2，主动视觉 bundle 为 v4 并绑定 episode dataset v3。
snapshot/action/feedback/ACK/offline-label 保持 v1；V1 Python record/sample 名称只是源码兼容别名，
旧 v1 文件稳定失败关闭。lazy/final-audit 只改变读取策略，不改变磁盘合同，因此无需再升版。

**最终复核修正：** dataset root 正规化后相对目录不再被包含检查误拒；record/sample 加入
controller mode/action 状态矩阵，任何非 assist effective action 都必须是规则动作；匿名 tracklet
的 resource、camera、local ID 均执行 truth-like guard。三项均是既有安全声明的缺陷修复，不改变
GAP 分级、磁盘 schema 或默认规则主线。

**实测与回归：** main 的 nominal seed 91、每档 2 s 新格式总制品为
5/20/50/100/200v200 `0.086/0.295/0.733/1.543/2.884 MB`；200v200 online/offline
`1.064/1.818 MB`、`3536` samples、RSS约 `1.04 GB`、online truth=0，单 episode 去重容量门通过。
D5 数据管线 `14 passed in 20.56s`，匿名稀疏图 `19 passed in 5.41s`，全量
`396 passed in 30.02s`。12 episode × 48 camera ×
96 track（576 samples）回归把完整 record、staged materialize 和全量 dataset loader 设为一调用即
失败，finalize/audit 全程只出现 `materialize=False`；lazy iterator 创建时 episode load=0，之后每次
推进只加载一个。

**剩余数据/准入 GAP：** 尚未用约 900 episode 正式 corpus 实测 finalize/lazy 训练峰值 RSS、吞吐
与恢复；也没有正式 BC/PPO、至少 20 个未见 seed 的性能、paired shadow、checkpoint 或 assist
准入。main 仍需提供实际 source Git/config identity、独立 outcome/counterfactual 和代表性困难场景。
D5 本轮未修改 main/runtime；模块 README/PLAN、三份 D5 review/GAP 及模块内四份 `docs/*` 已同步。

## 2026-07-20 主动视觉 RL 与量测标签连接 GAP 状态

**已关闭的软件缺口：** D5 现有版本化 truth-free 主动视觉 snapshot/action、确定性
look-at/reacquire/scan、有限动作候选、安全投影、`disabled/shadow/assist` 仲裁、完整
`(scenario_version, seed)` group 与共享 seed 跨场景原子 split、行为克隆、原生 PyTorch clipped
PPO、严格 bundle 和 paired shadow evaluator。策略权限仅为相机观察意图；没有飞控、D3 分配或
ID 生成接口。library 默认
disabled，CLI 默认 shadow，shadow 的 effective action 固定为规则动作。

**安全与准入门：** plan/coalition/communication version、候选成员、projection freshness、FOV、
云台角/当前及请求速率、slew、友方 exclusive reservation、action timeout、低置信、OOD、非有限
输出、模型异常和 bundle SHA/schema/state 错误全部 fail closed。assist report 必须绑定模型指纹、
dataset manifest、split 和 training-set SHA，并具有至少 20 个完全未见 seed、正式非合成来源、
逐 episode/总体 safety/visibility/reacquisition-delay 非退化。合成 fixture 不能授予准入。

**scalable label join 已关闭：** `SensorMeasurement.observation_id` 现在只读成为
`CameraLocalTracklet.source_observation_id`，在线 tracker 仍独立分配 `trk-*`。source key 不进入
匹配、`tracklet_key`、图特征、cluster 或 `global_track_id` binding；同帧重复 key 在状态更新前
拒绝。在线图冻结后，`join_offline_observation_labels()` 才把 evaluator-only observation label
连接到匿名 tracklet。无离线标签的假目标使 `labels_complete=false`，不补 truth。

**验证与边界：** 2026-07-20 主动视觉专项 `17 passed`，D5 全量
`376 passed in 9.94s`，零失败。训练 smoke 只有 8 个合成 seed group、BC/PPO 各 1 epoch；
20-seed 数据只测试 admission gate 的正/反分支，没有正式数据报告。仓库未新增主动视觉
checkpoint，本轮未运行 AirSim。随后 main 已把 truth-free snapshot、规则 look-at/reacquire/scan、
版本化相机/FOV 命令、下一视觉帧应用和 `runtime.camera_command_ack` 接到统一三维 episode。
5v5 开发冒烟为 `84/84` applied，200v200 seed 17、1.2 s 为 `1872/1872` applied；两者都是单
seed、脏工作树接口证据。故“主动视觉软件研究管线不可用”“observation label 无法稳定连接
tracklet”和“统一三维 episode 尚未接线”三个子项关闭。

开放 P1/P2 仍包括：正式训练数据/checkpoint、至少 20 个未见 seed 的 paired non-degradation、
assist 准入、主动视觉对可见率/重捕获/物理拦截的因果收益，以及真实 AirSim 云台和实机命令/
ACK。模拟 runtime ACK 不能替代真实执行证据。

`docs/MODULE_PRINCIPLES_CN.md`、`docs/ALGORITHM_AND_IMPLEMENTATION.md`、
`docs/AIRSIM_INTEGRATION_PLAN.md` 和 `docs/EXPERIMENT_REPORT.md` 已同步。文档明确区分已完成的
统一三维模拟接线和仍未完成的真实 AirSim/实机接线，没有新增 AirSim 性能结论。

## 2026-07-20 训练与模型制品管线 GAP 状态

**本轮关闭范围：** D5 已实现从匿名在线 `SparseTrackletGraph` 到版本化离线数据集、正式
多图训练、validation-only calibration/threshold、test 评估、校验 bundle 和在线安全回退的
完整代码管线。graph NPZ 与 evaluator label JSON 物理分离；`truth_entity_id` 只存在于 label
文件，图归档不持久化 truth 或 `shared_global_track_ids`。manifest 固化 graph schema、节点/边
feature names/version、candidate-recall availability、class balance、hard-negative provenance、
generation config SHA256、split SHA256 和 training-set SHA256。

**切分与评估合同：** split 单元为完整 `(scenario_version, seed)` group，同 group 的多个
episode 不得跨 train/validation/test，edge-level random split 固定为 false。训练使用固定随机
seed、按 geometry gate score 的困难负样本和不平衡 BCE；模型选择、temperature 和 F1
threshold 只读取 validation。test 输出 precision/recall/F1、false-merge rate、candidate recall、
Brier/ECE、P50/P95 inference latency 和 model size。真值不完整时身份/校准指标明确 unavailable
且 value 为 null，不补零。

**制品与在线边界：** bundle 为 `manifest.json + weights.pt + SHA256SUMS`，权重只通过
`torch.load(..., weights_only=True)` 加载。SHA、模型/图/feature 版本与顺序、state_dict shape、
权重有限值任一不符均 fail closed。安全 runtime loader 将缺失/损坏 bundle 转为显式不可用
scorer；在线 adapter 对缺模型、bundle 无效、异常、错误 shape、非有限/越界概率、超时、低
certainty 和无效 threshold 均回退原 deterministic geometry rule。模型只给 candidate edge
same-target probability；受约束聚类、同相机唯一、中心 Hungarian 及 `global_track_id` 所有权
未改变。

**验证：** 2026-07-20 新增专项 `12 passed`，稀疏图/adapter/新管线组合 `46 passed`，D5
全量 `355 passed in 9.48s`，接受阈值为零失败。覆盖整 seed 无泄漏、图/真值分流、正式训练到
评估、checkpoint round-trip、SHA/schema/feature/version mismatch、bundle 缺失、非有限概率、
超时、无模型、同相机唯一和中心 ID 不变。checkpoint 全部在 `tmp_path` 生成，没有提交正式
checkpoint；本轮没有运行 AirSim。

**GAP 判定：** 仅“训练/校准/评估/制品软件管线不可用”这一 D5-owned 子项关闭。代表性正式
数据、近邻交叉/遮挡/时延/外参漂移覆盖、至少 20 个未见 seed 的独立 test、冻结准入门限和
默认 checkpoint 均继续作为开放 P1。没有这些证据时不得声明模型准入，几何规则继续默认。
该阶段 AirSim/runtime 未变化；本轮主动视觉合同已另同步到 AirSim 集成计划，仍无实际运行证据。

## 2026-07-20 匿名稀疏图 GAP 状态

**代码级已完成：** camera-local tracklet 匿名节点、truth/global identity 递归隔离、相机
overlap/index、相机对预算、tracklet 候选度预算、时间/视场/极线/射线/重投影/GlobalTrack
投影/协方差门、确定性最终 degree cap、14 维边特征、原生 PyTorch
`index_add_` 消息传递、独立离线标签、困难负样本、正类权重、同相机互斥聚类、中心
Hungarian binding 及主动视觉规则 fallback 已进入 D5-owned 代码和回归。D5 输出中心 ID 的
集合被限制为输入中心 ID 集合的子集。P0 复审发现的 local-ID 漏项已修复：构造器及递归
payload guard 现在除 `truth/actor/object` 外，还拒绝 `TGT-0001`、嵌入式
`camera:TGT-002`、`TargetDrone_1`、`Target_UAV_7`、`intruder-003` 等 truth-like 编号；
`cam01-track-0001` 等正常 camera-local sequence 有正向回归。

**scalable 3D 模块入口已完成：** `scalable_3d_adapter.py` 以 duck typing 消费在线
camera batch 和 `vision_bbox`，不导入 main/D2/evaluator 类型。所有 payload 在 tracker 更新前
完成字段及 truth-like 值审计；local ID 只由 per-resource/camera tracker 分配，`observation_id`
仅只读复制到 `source_observation_id` 作离线审计，不作为身份。输出包含双时间戳、中心与 bbox covariance、角速度、尺度变化和完整
`TrackletCameraGeometry`。metadata 缺少独立 pose covariance 时使用带来源标记的配置 fallback。
六维 D2 状态只读转换保留中心 ID；端到端路径显式区分注入模型与 missing/error/low-confidence
规则 fallback。

**代码证据：** 2026-07-20 训练/制品同步后 D5 全量 `355 passed in 9.48s`。adapter 专项
`17 passed in 2.27s`，覆盖 2/3/4 相机部分可见、跨帧 ID、假目标/漏检、7 类污染、中心 ID
不变、episode reset、空扫描、真实 DTO 字段形状和模型回退状态。seed 200 的 200 目标/4 相机
场景为 800 节点、240000 可能跨相机 pair、3050 个索引后 tracklet 候选、2953 个最终 cap
前候选、1923 条最终边、密度 `0.006017`、最大度 6，本次实测 `0.442 s`，通过密度
`<0.01`、度数 `<=6` 和 `<15 s` 门。
seed 4 的 8 目标/3 相机训练 smoke 为 24 节点/192 边、24 正边/72 困难负边、正类权重
3.0，60 epoch loss `1.038521 -> 0.011535`、训练准确率 1.0。truth-like ID 专项新增
5 个构造拒绝、3 个递归拒绝和 4 个正常 ID 正例，接受门为拒绝/放行均无误判，12/12 通过。

新增 5/20/50/100/200 相机结构矩阵，每相机 1 个匿名 tracklet、相机对预算为 `2C`。200 相机
总对数 19900，只检查/保留 400，对预算丢弃 19500，tracklet 候选 397；全部相机至少进入一个
候选对。非重叠、重叠、预算截断、输入顺序确定性、预算耗尽 unbound、truth 隔离和中心 ID
不变均有回归。结构测试不设窄绝对时延门；单次 200 相机诊断约 59.2 ms 只作记录。

**GAP 判定：** truth-like local ID 的 P0 防线已在 D5 构造与递归入口关闭并保持回归。
原来的“全部非空 camera pair + 每对 `n_left x n_right` 矩阵”P1 已由 D5-owned 两级索引关闭。
`all_possible_camera_pairs` 只算术计数；视锥/时间/空间桶给出索引相机对，预算耗尽后不再检查；
中心投影支持/时间近邻给出有界 tracklet 候选。几何规则默认路径、可选模型、Hungarian、约束
聚类和模型缺失回退未改变。预算不足只增加 unbound，不产生身份猜测。

尚未关闭的是 200-camera 真实 episode 的内存峰值、P50/P95、预算召回损失、跨场景准确率和
多随机种子证据。训练、validation 校准、test 指标与 bundle 代码现已可用，但尚无代表性正式
数据、至少 20 个未见 seed 的 test、已验收跨视角模型或默认 checkpoint；真实 AirSim 多 seed
性能和学习型主动视觉闭环仍为开放 P1/P2。D5-owned DTO/tracker/association 与训练制品管线
缺口已关闭；既有几何 Hungarian/`TerminalAssociator` 继续默认。

**跨模块待办：** main scalable module stack 已调用本 adapter；main 需把新增
`association.diagnostics` 原样持久化，把 camera pose covariance 放入在线 metadata，并继续
确保 evaluator truth 只进入 evaluator。D5 已提供 candidate recall、边 precision/recall、
Brier/ECE 和时延的模块级输出；D6 后续仍需做 PR/ROC、IDSW 和至少 20 个未见 seed 的跨场景
汇总。D5 本轮未修改 main-owned runtime 或其他模块。

## 2026-07-16 ComputerVision 5+1 最终证据与 GAP 状态

**真实样本：** main 的独立专项分支使用 5 个 `1920x1080`/60 度局部相机、
1 个 `3840x2160`/75 度侦察相机和 5 个 `Quadrotor1` actor；两个 episode 均为
12 秒、49 帧、seed 7。D5 按每个相机 batch 的 `measurement_timestamp` 投影。

**结果：** detect 的召回/配准/稳定/联合覆盖/侦察全覆盖/IDSW =
`1.000/1.000/0.975/1.000/0.918/0`；YOLOv8 + 原生 ByteTrack =
`0.622/0.996（严格 0.966）/0.955/1.000/0.878/25`，P50/P95 约
`10.42/12.37 ms`。两路 online truth use 和 `global_track_id` rewrite 均为 0。

**truth/fixture 边界：** 本隔离专项没有运行 D1/D2。main 使用 actor truth
运动学合成带中心 `global_track_id` 的 `GlobalTrack` fixture，truth 同时用于
离线评分。`online_truth_identity_use=0` 仅说明 D5 的 local bbox 到 fixture
关联代价、Hungarian 选择和稳定窗口不读取 actor/object/truth identity，不代表
整个专项完全不读取 truth。

**门限与判定：** detect/YOLO 召回门限为 `>=0.95/>=0.90`，严格配准
`>=0.95`、稳定 `>=0.90`、联合覆盖 `>=0.95`、侦察全覆盖 `>=0.90`、IDSW
`<=0/<=5`，truth use/rewrite=0。detect 几何基线已通过该单 seed 专项；不等于
关闭多 seed P1，也不改变默认 D1-D7 主线。

**仍开放 P1：** YOLO+ByteTrack 的召回、IDSW、侦察全覆盖和多 seed confirmation
均未闭合，故继续标记 optional。单 seed 不得写为主线晋级；M5N2 第二 primary、
真实几何 drift、二级同 tick freshness 等既有 GAP 状态亦不因本专项自动关闭。
本轮只同步证据，不修改 D5 算法、默认 backend 或安全门限。

## 2026-07-16 人工轨迹局部观测合同 GAP 状态

**已关闭的 D5-owned 接口缺口：** 离线
`manual_records_to_local_image_observations()` 已把
`ManualTrackFrameRecord[]` 规范化为 main 的 `LocalImageTrackObservation[]`。
measured 记录提供双时间戳、`xyxy`、`2x2` 自适应像素协方差、camera-local ID、
backend、frame index 和连续 measured history；lost 不保留 stale 量测且
confidence 为 0。IR 使用合同值 `infrared`。整批转换先运行 identity audit，
发现任一重复量测即 fail closed。

**依赖与身份边界：** D5 包根不再导入 manual tracker，默认包导入不强制加载该离线
OpenCV/SciPy 支线。适配器 metadata 不含 global/truth identity，不创建、改写或换绑
`global_track_id`；没有接入 AirSim detect、TerminalAssociation 或 D7 handoff。

**验证：** 2026-07-16，既有真实视频记录 1 组、95 帧、5 个 local ID、475 条记录，
转换得到 `470 measured / 5 lost`，identity audit 重复量测为 0。确定性回归覆盖
协方差、双时间戳、infrared、`xyxy`、连续历史重置、重复坍缩拒绝和根包在屏蔽
OpenCV/SciPy 时的导入边界；D5 全量 `288 passed`。接受阈值为零测试失败、
重复坍缩零容忍、lost 零 stale 量测。

**仍开放的 GAP：** 该接口只关闭“人工离线记录无法进入模块中立局部图像观测合同”
这一 D5-owned 子项。人工初始化、单相机和亮目标数据局限仍在；真实 AirSim 默认路径、
通用 detector/MOT、多视角身份、M5N2 第二 primary 与物理闭环 P1 均未关闭。

## 2026-07-15 人工初始化视频 local MOT GAP 状态

**已实现：** D5 新增普通视频人工多 ROI 初始化工具。每个 ROI 获得不可自动换绑的 `local-xxx`，默认独立 CSRT、可选 KCF，并输出 MP4、逐帧 CSV 和 JSON summary。纯 tracker 的重叠重复量测失败关闭；亮目标专项可使用正对比峰候选、常速度预测和 Hungarian 一对一分配。丢失帧不携带旧 bbox/center。

**真实证据：** 2026-07-15 对 `research_modules/b.mp4` 运行 95 帧、5 个 `12x12` 人工框。最终五 ID 有效/丢失为 `92/3`、`95/0`、`93/2`、`95/0`、`95/0`；最小有效中心间距 `5 px`、最大 bbox IoU `0.4118`、`duplicate_measurement_count=0`。纯 CSRT 12/16 px 对照会在第 38/28 帧出现框合并，KCF 只保持 2-3 个有效帧，因此不能把独立 tracker 的 success 标志等同 ID 连续性。

**不关闭的 GAP：** 该工具只验证人工初始化单相机 local ID。它不关闭 detect/YOLO/ByteTrack/BoT-SORT 多 seed 准入、GlobalTrack 几何注册、跨相机关联、敌我识别、M5N2 第二 primary 或物理拦截 P1。亮点候选依赖目标相对背景为正对比，尚未证明适用于普通纹理无人机、遮挡、交叉或相机剧烈运动。

**优先级判定：** 本任务没有新增 P0。人工视频复现工具作为 D5 诊断能力已闭合；通用 detector/MOT 准入和真实 AirSim 多 seed 仍按原 P1 保持开放。

**验证：** 2026-07-15，真实视频 1 个、95 帧、5 个 local ID，逐帧记录 475 行；D5 全量 `284 passed`，`py_compile` 与 owned-path `git diff --check` 通过，接受阈值为零测试失败且 `duplicate_measurement_count=0`。

## 2026-07-15 M5N2 20-case GAP 更新

**已闭合/有真实证据：** baseline/candidate 各 10 seeds 共 20 个 M5N2 case 已形成 `3725/3725` 条适用的第二 primary D5 runtime record，decision state 与 live first-failure stage/reason 全部 available；actual execution 和离线 5 m 物理证据 `20/20` available；online identity/state truth use、global-ID mismatch、friend/duplicate conflict 均为 0。第二 primary 按 current active membership 动态选择，未把 standby reserve 错计为 primary。

**仍开放 P1：** 第二 primary 5 m 为 `0/20`，T001 coalition completion `0/20`。首断点主要为 bbox stability `1283/3725`、live detection/freshness `1209/3725` 和 visual association `764/3725`；bbox stable/handoff-ready 只有 `161/3725`，strict complete 只有 `52/3725`。因此“已有 locked/consensus 快照”不能关闭末端闭环缺口。

**责任边界：** 20 个第二 primary 最终均记录为 `collision_stop`，但该字段只是 D7 停控证据；碰撞对象未持久化，尚不能区分成员碰撞、环境碰撞或 AirSim 状态问题。因此不能把该状态或 `0/20` 单独归因于 D5，碰撞对象/类别的离线落盘仍是跨模块 P1 诊断缺口。

**报告可用性 P1：** 新代码支持 `failure_category`，但这 20 个 runtime artifact 没有直接持久化该 envelope；真实可用字段只有 stage/reason。main/D6 后续必须原样落盘分类及 availability，不能把缺失补为 unknown/zero。

**候选状态：** candidate 的 handoff-ready 为 `103/1856 (5.55%)`，高于 baseline 的 `58/1869 (3.10%)`，但 second-primary physical 均为 `0/10`，locked/freshness/consensus 无一致提升。candidate 不晋级默认路径。candidate seed 002 的 active membership 与 baseline 不同，后续应冻结或分层合同后再比较。

本批只复核 M5N2。TERM 生效前额外完成一个 `png_ttc_2v2_seed001`，但未并入 M5N2 数字；其余 tuned case 与 dropout case 均未执行，不得写成本轮完成。D5 无新增 P0 blocker，P1 继续聚焦当前 measured bbox 连续性、visual freshness、候选唯一性、几何重获取和分类 envelope 接线。

## 2026-07-15 第二 primary 失败漏斗状态

**已关闭的 D5-owned P1 诊断缺口：** cooperative summary 现在复用既有在线字段，按 active primary 和第二 primary 输出互斥的被动 `failure_category` 计数。不可见、投影无效、几何门拒绝、bbox 不稳定/裁切、候选不唯一、量测陈旧、计划/版本/assigned-global-ID 不一致、友方/重复锁定冲突及稳定锁定未完成均可独立统计。错误全局 ID 不再被误报为不可见，且不会成为本地换绑依据。

**验证：** 2026-07-15，11 个确定性专项 case，D5 全量 `272 passed`，阈值为零失败；online truth use 与 global ID rewrite 均要求为 0。没有启动 AirSim，没有放宽任何决策或安全门。

**仍开放 P1：** 真实 2v2/M5N2 至少 10 seeds 的分类覆盖率和主因排序；第二 primary 5 m/联盟闭环；真实外参/时序 drift；detect/YOLO/native-MOT 多 seed；二级证据同 decision tick freshness。分类能力已实现不等于这些性能项通过。

## 2026-07-14 actual-v2 真实 AirSim GAP 判定

**新增证据，不关闭 D5 P1：** tuned 2v2 和 M5N2 各 1 个 seed 的 canonical actual-execution artifact 与五层 schema 均 available。contract/control/terminal-switch/mode/physical 总计为 `102/26/26/2/4`；`terminal_switch_allowed_count` 从最终 `control_commands.csv` 独立统计，2v2/M5N2 为 `26/0`，不由 control 层推断。2v2 的 `terminal_lock_count=3`、visual/mode switch `2/2` 给出单 seed terminal switch 正证据；M5N2 的 `terminal_lock_count=24`、visual/mode switch `0/0` 仍只有 lock acquisition，不能重分类为视觉控制闭合。

**物理层边界：** M5N2 active pair `2/3`、target `2/2`、coalition `0/1`，T001 第二 primary 最近约 `11.02 m`。目标级成功不能覆盖 required-primary 或 coalition 失败。D6 formal overall status=`fail`，因为每场景仅 1 seed，且 baseline/candidate、1-5 帧 dropout 全矩阵和完整多 seed suite 缺失。

**安全合同保持：** 两 case identity/state online truth use 为 `0/0`；默认仍为 AirSim detect。D5 不得使用 actor/object truth 做在线 acquisition/registration/gate，不得创建、改写或换绑 center-owned `global_track_id`。本任务没有代码、算法、阈值或 backend 变化。

**开放 P1：** 当前收敛为 M5N2 第二 primary、真实 AirSim/replay 几何 drift、detect/YOLO/MOT 多 seed，以及二级证据同一 decision tick freshness；不是 canonical 五层 schema 或 main 接线缺口。IBVS、真实身份源、完整在线 PnP/ROS 2 保持 P2/P3。M5N2 既有视觉完成接受阈值仍至少 `8/10`，与 physical coalition `0/1` 分母独立。

## 2026-07-14 postbatch DTO/执行锁定 P1 收尾

**已关闭的 D5-owned P1：** `local_visual_evidence` 与 `d7_handoff_input` 已完整携带 bbox、中心、resource/camera/stream/backend、双时间戳和 measured/stability 状态；几何 `locked` 不再被 `execution_lock_allowed` 直接等同。执行锁定必须额外满足 own-camera measured bbox、scope、membership/version 合同、连续 measured lock、bbox stability/scale 及全部既有安全门。scope 冲突直接 `hold`。没有降低 identity/friend/duplicate/version/calibration/bbox gate，没有 online truth 或 `global_track_id` rewrite。

**直接证据：** 最新 postbatch baseline/candidate 为 `330/311` 条控制记录、`151/120` 条 D5 几何 locked；两组均仅 INT-03 有 `40` 条控制 bbox 非零，active pair 在约 `23-29 m` acquisition timeout。baseline INT-03 最大面积比约 `2.4943e-4`，低于 `8e-4` 门。producer camera scope 均为对应 `InterceptorN:0`，因此未确认相机串线 P0。

**仍开放 P1：** 真实多相机持续 detection；进入末端范围后的当前 bbox；当前 `640x480` 口径下的小框尺度；candidate 中约 `0.64-0.70` 的单帧异常大框；至少 10 seeds 的 detection/lock/handoff 分布。验证日期 2026-07-14，`py_compile` 通过、D5 全量 `261 passed`，接受阈值零失败；本批未运行新 AirSim。当前无新增 D5 P0。

## 2026-07-14 semantics_v2 第二 primary 历史 live funnel 复核

该批真实 M5N2 seed-1 已推翻“第二 primary 没有 live detect”这一笼统假设。baseline/candidate 中，INT-02 分别有 `195/193` 帧 measured detection、`140/142` 帧 raw visual lock、`18/18` 帧 final execution lock；T001 两组均有 `14` 帧 coalition consensus，稳定锁定最大连续计数为 `17`。开放问题不是 D5 无法形成视觉候选，而是旧 D3/main 到达窗口只在 `0.4-2.2 s` 有效，INT-02 bbox 到 `19.0/18.6 s` 才满足稳定门限。顶部 postbatch 复核已进一步确认 main 可消费当前 local track，其他资源末端 bbox 为零主要源于当前 measured detection 消失，而非已确认的跨相机路由错误。

本轮关闭 D5-owned 的 P1 可观测性缺口：新增 truth-free `d5_live_visual_funnel_v1`，按 `live_detection -> projection -> geometry_gate -> visual_association -> evidence/execution_contract -> measured_stable_lock -> bbox_stability -> handoff` 输出首断点；连续 measured execution lock 严格按 resource/target/camera/local track、时间和既有安全合同累计，任何非 measured、identity/friend/duplicate、membership/stream 或 execution gate 失败都会清零。runtime record 顶层输出关键字段，handoff 输出完整 `d7_handoff_input`，不授予控制权且不改变任何门限。

该阶段验证日期 `2026-07-14`；新增 3 个专项测试，D5 全量 `258 passed`，接受阈值为零失败。当前无新增 D5 运行级 P0。postbatch 已关闭非协调场景 arrival-window 与 current local-track 路由疑点；当前开放 P1 以顶部 DTO/执行锁定章节为准。

## 2026-07-14 bbox 稳定历史/共同视觉证据 P1 闭合

postfix seed-1 的只读审计结果为：M5N2 baseline/candidate `bbox_stable=true` 均为 `0/1388`，T001 consensus 分别为 `13/347`、`12/347`；2v2 PNG/TTC 为 `0/52`，且全部 runtime association 的 `visible_frame_count <= 1`。根因不是四帧/CV 门限过严，而是 main 每 tick 只向 `annotate_visual_png_handoff()` 传当前 `scoped_local_tracks`，旧 handoff 没有跨调用历史。T001 同时存在 `326/347` tick 的真实 primary membership transition；这类变化必须保留安全重置，不能用跨成员历史补足共识。

D5-owned 修复已完成：`TerminalAssociator` 按 resource-target-local track-camera-stream-detector/tracker backend 与 committed/current membership 累计 measured bbox/MOT 历史；普通 plan/coalition version 更新被排除出 continuity signature。resource-target 换绑、membership 缺失/变化、local track、camera/backend/stream、producer reset、predicted/lost、identity/friend/duplicate conflict 均清空历史。输出增加 history length、area CV、reset reason、key/signature、measured/predicted source、source plan versions、raw/effective MOT history 和合同完整性。handoff 可直接消费该审计历史；共同视觉只使用 current committed active primary。锁定门限、`global_track_id`、YOLO/native-MOT 准入结论均未改变。

验证日期 `2026-07-14`；确定性合同覆盖 plan refresh 保留、全部安全重置、M-to-N 缺 membership fail closed、成员变更、单 tick handoff、YOLO backend 缺失和 committed/current coalition 汇总；D5 全量 `255 passed`，接受阈值为零失败，owned-path `git diff --check` 通过。本轮未启动 AirSim，故只关闭 D5-owned 历史与 fail-closed 合同 P1，不声明 M5N2 物理闭环完成。

后续 canonical actual 已消费当前 executable/committed coalition、pre-decision `duplicate_terminal_lock_risk` 以及稳定的 camera/stream/backend/local-track transition/MOT 字段，并独立持久化五层 envelope；该 main 接线项已关闭。真实 M5N2 第二 primary、几何 drift、30/50 m recall、detect/YOLO/MOT 多 seed 和二级同 tick freshness 继续开放。

## 2026-07-14 原生 MOT 连续历史 P1 子缺口闭合

旧实现虽然已按 `(resource_id, camera_id)` 隔离 Ultralytics native model，并调用 `model.track(..., persist=True)`，但 `_detections_from_result_object()` 把每帧 `mot_history_length` 固定为 1。由于 `TerminalAssociator` 默认要求 `min_mot_history=2`，真实 `Results.boxes.id` 即使连续稳定也可能无法进入 `locked`。

现已在 `YoloMotAdapter` 内按 `(resource_id, camera_id, tracker_backend, native tracker id)` 累计连续 measured hit。ID 连续出现时历史递增；ID 切换、空帧后恢复、backend 切换、stream/episode reset、原生失败模型重建均从 1 重计。状态使用现有 `max_track_age_frames` 做有界保存，但任何 coast 都不计连续实测历史，长期 ID 复用不能继承锁定证据。native failure 释放失败模型并清理原生历史，IoU fallback 使用独立状态；truth/global 字段隔离和 `global_track_id` 不变式保持。

验证日期 `2026-07-14`；场景为 Ultralytics `Results`-like 连续帧、ByteTrack/BoT-SORT、跨资源/相机隔离、ID 切换、空帧/短长遮挡、stream/episode reset 和 native-fallback-native；D5 全量 `241 passed`，接受阈值为零失败。该代码级 P1 子缺口已关闭，但真实 AirSim/真实图像多 seed 原生 MOT 准入仍开放：必须继续验证 precision/recall、IDSW/continuity、P95、bbox/时间对齐、30/50 m 召回和失败回退率，默认 detect 路径不变。

## 2026-07-14 D3 feedback 分级 P1 子缺口闭合

审计发现旧 `TerminalConsistencyTracker` 会把任意连续普通 `hold` 升级为 `conflict/report_conflict`，把连续普通 `reacquire` 升级为 `arbitrate`，且只读取 cross-view duplicate、未读取 `TerminalAssociation.duplicate_terminal_lock_risk`。这会把 pair 级视觉不确定性误解为资源/分配 hard conflict。

现已在 D5 owned path 内修正，保持公共 DTO 和函数签名兼容：普通 ambiguity、geometry gate、bbox/时序不稳定及一般 hold/reacquire 仅输出 `unknown + observe/request_secondary_cue`；verified friend、spoof suspected、direct/cross-view duplicate、授权/版本与持续 assignment/ID conflict 输出 `conflict/inconsistent + report_conflict/arbitrate`。stale/unverified identity 和 unknown category 不推断 hostile，`assigned_global_track_id` 原样保留，online truth use 为 0。

验证日期 `2026-07-14`；场景为 TerminalAssociation、连续一致性与 metadata-only distributed cross-view 确定性回归；专项 `52 passed`、当时 D5 全量 `235 passed`。接受阈值为零失败、普通不确定性不得产生 hard action/resource-unavailable 语义、hard conflict 必须 fail closed。本项关闭 D5 状态分级子缺口，不代表新增 AirSim 资源健康或物理拦截证据。当前 P1 为 M5N2 第二 primary、几何 drift、detect/YOLO/MOT 多 seed 和二级同 tick freshness；ReID、真实身份和完整在线标定链保持 P2，IBVS/ROS 2 保持 P3。

## 2026-07-13 M5N2/per-primary/MOT 实测结论

D5 模块内 per-primary 合同和诊断接口已经闭合，但系统级协同视觉 P1 尚未闭合。M5N2 实测形成 `120` 条 active-primary 证据，`visible=120`，其中 D5 关联/锁定证据为 `74`；最佳 profile 的 coalition completion 仅为 `5/10`，低于 `8/10` 验收线。主要失败原因是 `d5_not_locked` 和 `terminal_detection_acquisition_timeout`，下一步应优先解决第二 primary 的持续检测、稳定 bbox 和连续 measured lock，而不是放宽共同身份、版本或安全门控。

`per_primary + arrival_coordination_required=false` 只表示两个 active primary 可顺序取得视觉证据，不要求同帧或同时到达；plan/owner/version、coalition commit、friend/duplicate、measured local track、reserve standby 和 D7 独立控制门控仍然有效。当前实测 `global_track_id` rewrite 为 `0`、online truth use 为 `0`，没有新增 P0。

原生 MOT 严格 screening 已运行 `18` 个 case：`1920x1080`、FOV `90`、距离 `20/30/50 m`、confidence `0.1/0.2/0.3`、ByteTrack/BoT-SORT。20 m 两后端 native active rate/continuity 均为 `1.0`、IDSW 为 `0`，P95 约为 `7.4/16.2 ms`；但 detector precision/recall 仅约 `0.26-0.33`，30/50 m 均无检测。准入候选为 `0`，因此 confirmation 执行数为 `0`，ByteTrack 和 BoT-SORT 均未晋级，默认 AirSim `simGetDetections` 路径不变。

2026-07-13 detector 子项当时收敛为四个动作：第二 primary 稳定获取、bbox 定义/尺度/时间对齐、30/50 m 远距召回、候选至少 10 seeds 准入确认。当前 D5 P1 的四类边界以本文顶部为准。D5 的 DTO、准入 summary 和 post-online truth 隔离已具备。2026-07-13 当日全量回归为 `232 passed`，2026-07-14 最新全量为 `241 passed`；本文中的 `235 passed`、`229 passed` 及更早数字均为对应实现阶段的历史基线，不代表当前测试总数。不得把 20 m tracker 连续性写成原生 MOT 已准入。

## 2026-07-13 类别 taxonomy 与推理尺寸子缺口

D5 已关闭运行时错误类别惩罚子缺口：`uav`、`drone`、`intruder` 以及常见大小写/分隔变体统一按对象类别 `uav` 比较，单相机和完全分布式跨视角代价均使用相同 taxonomy。原始 detector 类别保留在 track/frame metadata，且显式记录类别没有推断 affiliation；真实类别差异仍保留惩罚，友方身份门控不变。

`YoloMotAdapterConfig.inference_imgsz` 已支持正整数和 `(height, width)`，并透传到 Ultralytics `track/predict`；`None` 保持旧调用。测试覆盖同义类别零惩罚、真实类别不匹配、原始类别保留、native track/predict 透传、非法尺寸拒绝和默认兼容；该实现阶段的历史回归基线为 `229 passed`，2026-07-13 当日全量为 `232 passed`，2026-07-14 最新全量为 `241 passed`。开放 P1 仍是由 main/runtime 对 1080p/4K 每相机配置进行真实 AirSim 多 seed 的 GPU/CPU 延迟、显存、远距召回和 fallback 标定；本轮没有用高 `imgsz` 替代几何、身份、版本或稳定窗口门控。

## 2026-07-13 YOLO + simGetDetections 双路复核

D5 已确认并补齐 post-online 双路评价合同：在线 YOLO/ByteTrack 或 BoT-SORT result 先形成，AirSim `simGetDetections` 后到数据只进入 `NativeMotAdmissionMonitor` 的离线 evaluator。汇总现单列在线 detector bbox 数、本地 MOT track 数、离线参考框 matched/missed/unmatched-online 数以及 native/fallback 帧，避免把不同层级的 detection count 混用。1080p/4K `image_size` 和 truth identity 隔离均有参数化回归；该项没有改变 detect-first 默认主线，也没有关闭真实 AirSim 多 seed 检测距离与跨视角注册 P1。

**审计范围**：commit `33e6fa0` 后当前代码与测试、`subagent_reviews/MAIN_IMPLEMENTATION_GAP_AUDIT.md`、`research_modules/airsim_runtime/outputs/PNG_DELIVERY_ENHANCEMENT_AIRSIM_VALIDATION_REPORT_20260712.md`、`subagent_reviews/D5_TERMINAL_ASSOCIATION_REVIEW_AND_PLAN.md`、`C_UAS_MAINSTREAM_SOLUTIONS_AND_DIFFICULTIES.md`、`research_modules/d5_terminal_association/README.md`、`PLAN.md`、`docs/ALGORITHM_AND_IMPLEMENTATION.md`、`src/d5_terminal_association/` 和 `tests/`。

**边界**：本文只审计 D5 末端视觉配准、协同身份声明、二级节点 cue、跨视角摘要和 AirSim ComputerVision 检测框适配现状。D5 不重新分配目标，不创建、不改写、不换绑 `global_track_id`；在线几何配准不得使用 AirSim `object_id`、`actor_name` 或 truth ID，truth 只能作为离线评估标签。

## 总体结论

2026-07-13 混合分辨率审计关闭一个 D5 P1 子缺口：单相机 `CameraModel` 与 YOLO/MOT 原本已读取实际尺寸，但 friend/recon/reacquire/rate 固定像素项、二级 adaptive covariance 上限，以及完全无中心跨视角的 raw pixel/bbox-area 比较仍隐含同尺度假设。现统一以 `640x480` 为参考像素尺度，并显式保留每流 `image_size`；1080p 拦截相机和 4K 高空侦察相机可在同一 episode 中独立投影、门控和跨视角比较。truth 隔离、版本门控与 `global_track_id` 不变式未改变，D5 全量 `204 passed`。开放项是 main 写入真实 AirSim settings、Actor 线性尺寸扩大 2 倍后重跑并由 D6 比较 detection/registration 指标，不属于 D5 owned path。

2026-07-13 真实 AirSim 原生 MOT 证据更新：严格 `18`-case screening 中，20 m 的 ByteTrack/BoT-SORT 均达到 native rate/continuity `1.0`、local IDSW `0`，P95 约为 `7.4/16.2 ms`。由此只关闭“20 m 受控流无法形成原生 MOT ID 或延迟超预算”的 P1 子缺口。ByteTrack 延迟更低，但不存在 backend 晋级结论。

开放 P1 转为 detector range 与离线 bbox agreement：本轮各 20 m 配置的 precision/recall 约为 `0.26-0.33`，30/50 m 两后端均零检测。前者可能来自 YOLO 可见目标框与 AirSim detect 框的定义、尺度或时序差异，后者更直接指向模型尺度、视角或渲染域上限。当前候选准入数为 `0`，未进入 two-camera confirmation；不能用直接降低 IoU、confidence 或在线门限关闭缺口。

P1 验收动作固定为：持久化 post-online AirSim bbox/timestamp/status；做 IoU `0.1-0.5`、中心归一化误差、宽高/面积比、containment 和 `-1/0/+1` 帧对齐诊断；运行距离 `20/25/30/40/50 m`、confidence 主网格 `0.1/0.2/0.3` 加 `0.05` 诊断点、ByteTrack/BoT-SORT 矩阵；候选配置至少 10 seeds x 100 帧。准入要求 native rate >=0.95、fallback=0、continuity >=0.90、IDSW <=1、P95 <=100 ms、truth 覆盖 >=0.99，并在验证后的 bbox 约定下达到 20 m precision >=0.90、recall >=0.80。30/50 m 当前保持未准入。truth 只在 online result 后评分，在线几何、友方、版本、duplicate、授权和 `global_track_id` 不变式不变。

2026-07-12 原生 MOT 准入能力已在 D5-owned 路径闭合：`YoloMotAdapter` 的 ByteTrack/BoT-SORT 实际选择、confidence 和 20/30/50 m 场景 metadata 可被 `NativeMotAdmissionMonitor` 按 stream 汇总。准入指标包含 `native_active_frame_rate`、`fallback_frame_count`、accepted detections、去除前 5 帧预热的 P95 latency、local continuity、terminal local IDSW 和 offline detector TP/FP/FN、precision/recall。IoU fallback 明确不算 native，默认要求 fallback=0。严格时序已改为 online result 先形成，main 后取 truth，再由 monitor/public evaluator 评分；result 只携带无身份 detector bbox，评分不回写。legacy metadata 路径保留，但 post-online truth 优先且不双计数。truth identity 只进入私有评分状态，不写入 summary、local track 或 global binding。新增 per-stream reset 与 scenario-change-without-reset 拒绝。

同轮新增 `terminal_authorization_scope=per_primary` 的只读 evidence helper。D5 `Assignment -> GlobalTrackBinding -> TerminalAssociation -> runtime record` 已无损携带 `terminal_authorization_scope` 和 `arrival_coordination_required`；旧输入默认 `coalition + true`。只有显式 `per_primary + false` 的两个 active primary 可以分别报告 locked，不再由 D5 强制共同同帧锁定；调用参数不能覆盖 DTO 合同。缺 plan/coalition 版本、当前 resource/global-track/plan/coalition binding 不匹配、reserve/standby、friend conflict、duplicate risk、非 measured local track 和 execution gate 失败仍 fail closed。helper 不授予控制权限，不创建/改写/换绑 `global_track_id`。D5 全量 `200 passed`。

剩余 P1 是检测质量和多 seed confirmation，不是 D5 统计接口缺口：main 已用连续 AirSim RGB 完成 ByteTrack/BoT-SORT、confidence `0.1/0.2/0.3`、20/30/50 m 的 18-case screening。结果没有产生准入候选；后续应先闭合 bbox 定义/尺度/时间对齐和远距召回，只有候选通过 screening 后再运行至少 10 seeds confirmation。未满足准入前 detect 继续默认，IoU fallback 只能作为失败对照。

2026-07-12 P1 M5N2 双 primary 视觉诊断的 D5 模块缺口已闭合。新增动态资源/目标 summary，逐资源记录 current-contract、visible、projected、gate accepted、locked、stable frames、共同窗口、confidence、ambiguity 和 reject reason，逐目标显式给出第二 primary 首个失败阶段。当前 plan/coalition 版本不一致、friend conflict、共同窗口不足和 D4 fallback 缺 ACK 均 fail closed；standby reserve 不进入 active-primary completion。输出不消费/传播 AirSim actor/object/truth ID，不创建、不改写、不换绑 `global_track_id`。本轮进一步修复共同窗口未复用安全跨版本连续尾段的问题，并新增 primary membership transition 与 current failure diagnostics；D5 全量 `181 passed`。

该项只关闭 D5 诊断 DTO/纯函数/回归测试，不关闭系统级 M5N2 物理协同。main/D6 已把 summary 接入真实 paired episode 和统一漏斗；2026-07-13 结果为 120 条 active-primary/visible、74 条 D5 关联/锁定证据，最佳 coalition completion `5/10`。主要断点是 `d5_not_locked` 和 `terminal_detection_acquisition_timeout`，这仍是跨模块 P1。

2026-07-12 pose-fix smoke 专项复核：四组真实输出中 T001 primary 集合变化 48-87 次。当前视觉证据最好的是 `h020/w05/s040` 单 seed：183 帧中双 current lock 25 帧、双 stable lock 18 帧，但 no-lock 仍有 133 帧；主要拒绝为 `insufficient_best_second_margin` 和 `terminal_visual_evidence_expired`。D5 已关闭一个确定的模块缺陷：共同窗口此前只认当前 plan version，和已经实现的安全跨版本稳定计数不一致。修复后只复用稳定逻辑认可的 source versions 与连续尾段，primary 换员和所有安全冲突仍阻断。尚未闭合的 P1 是：main 重放/重跑验证实际提升、D3 primary/plan 抖动治理，以及 runtime 将真实 `CameraGeometryEvidence` 传入 D5；现有记录的强类型 geometry 全部 unavailable，D5 不得用 actor/object truth pose 补齐。

D5 当前已经实现离线科研主线：

```text
GlobalTrack -> CameraModel -> OpenCV/projected image point
-> LocalVisualTrack -> TerminalAssociator -> TerminalAssociation
-> TerminalObservationBus / TerminalConsistencySummary
```

已落地的能力包括：单相机 `cv2.projectPoints`/针孔投影 fallback、像素协方差传播、马氏几何门控、保守 `locked/ambiguous/hold/reacquire` 决策、`LocalVisualTrack`/`TerminalAssociation`/`IdentityClaim`/`ReconImageCue` 数据结构、二级 cue 作用域和重投影校验、跨视角摘要层、完全分布式 metadata-only 跨 peer 视觉假设生成、重复锁定风险、一致性摘要、AirSim `simGetDetections` 风格 bbox adapter、YOLO/ByteTrack 离线 schema adapter、YOLOv8 + ByteTrack/BoT-SORT frame adapter、确定性 IoU fallback tracker、AirSim 相机内外参转换、离线几何配准验证、可写盘 geometry/consistency/handoff metadata、P1 multi-seed calibration readiness 字段覆盖审计 helper、二级视觉覆盖 + detect 到 cross-view 转换漏斗诊断 helper、AirSim settings 驱动 detect-to-global-track registration helper，以及机动高空侦察云台 cue evidence。registration helper 消费 `GlobalTrack`、D2/D3 binding/`Assignment`、per-camera `CameraModel(K/R/t)`、timestamp、协方差和 `LocalVisualTrack`，用像素马氏距离 + Hungarian/JPDA-compatible candidates 输出既有 `global_track_id` 支持，记录 `DetectToGlobalTrackCandidate.outcome`、projection/reject reason、timestamp、measurement age、covariance summary 和稳定窗口结果，不使用 AirSim truth/actor ID。YOLO/MOT adapter 记录 confidence、class id、bbox scale、tracker backend 和请求的 CPU/GPU budget，tracker ID 仍只作为 `LocalVisualTrack.local_track_id`。机动云台 evidence 可区分 `fixed_downlook_secondary` 与 `mobile_recon_gimbal`，并携带 GlobalTrack/radar cue 的 NED look-at、云台元数据、pointing error 和 gimbal track error。

未落地的是完整 runtime 工程质量闭环：AirSim 图像链已从最小 smoke 推进到 18-case 原生 MOT screening，20 m native tracker 可持续运行且延迟达标；但检测 precision/recall 低、30/50 m 无检测，候选数和 confirmation 数均为 0，GPU/CPU 多 seed 阈值/预算标定尚未闭合。Deep SORT/ReID、OpenDroneID Core、MAVLink signing、DDS Security、AprilTag、真实标定图像/PnP RANSAC/在线外参更新、ROS 2 `tf2/message_filters`、真实二级侦察图像反投影再重投影链路和跨相机几何联合优化器也未落地。OpenCV calibration/`solvePnP` 仅以隔离式合成 P2 benchmark 落地，不属于在线 runtime，也未替换默认在线几何门控路径。

2026-07-07 复核状态：`TerminalConsistencyTracker` 连续窗口已按 `resource_id + assigned_global_track_id` 维护，D3 对同一资源/目标滚动发布新的 `assignment_version` 不会清空连续视觉状态。该能力已由 `test_consistency_streak_survives_plan_version_updates_for_same_assignment_pair` 覆盖。D5 已补充 projected pixel、pixel error、Mahalanobis、gate pass、friend conflict、measurement age、duplicate-risk advisory、LOS/measurement-age handoff blockers 和离线 YOLO/ByteTrack truth 隔离测试。D5 的一致性输出仍是 advisory summary，只供 D4/D6/D7 作为证据消费，不触发降级、不生成 `AssignmentPlan`、不改写 `global_track_id`。

2026-07-08 AirSim 机动高空侦察节点复测只保留为历史基线：`p1_d4d5_mobile_recon_20260708_055948*` 证明 D5 能识别机动云台/cue metadata，`p1_d4d5_registration_calibration_runtime_v2_20260708*` 的单 seed 结果证明投影和 cross-view 不再全为 0；其中降级 case not-registered 35/35 已被后续 60-case sweep 改写，不能作为当前缺口。

2026-07-10 60-case registration 结论：`research_modules/airsim_runtime/outputs/p1_gap_closure_calibration_20260710` 覆盖 5v5、10 seeds、50/200 m、三类 case，共 60 个 case。D6 `not_registered_count=0`，sweep 的 `secondary_detect_available_but_not_registered` 均值/最大值均为 0；平均 `projection_valid_rate=1.0`、stable registration `92.233`、cross-view association `4.417`。基础 detect-to-global registration 缺口已闭合。剩余瓶颈是网络同帧全目标覆盖率均值 `0.0231`、平均覆盖率 `0.7059` 和稳定窗口失败。D5 侧逐决策证据与 episode 聚合的接口分离已由 `SecondaryFrameAssociationEvidence` 闭合；main/D4 是否在真实 decision tick 使用它仍是跨模块 P1。registration 成功不能替代唯一性、友方冲突、时效、版本或 D7 安全门控。

2026-07-10 本轮 D5 P1 补齐：`build_secondary_frame_association_evidence()` 仅消费单个同步 frame 的 camera/network coverage 与 registration candidate，输出 D4 `TerminalAssociationSummary` 同名字段，并保留 frame、measurement/arrival timestamp、detector/tracker backend、calibration health、ignored historical candidate count。混合 frame/timestamp fixture 会拒绝，在线 metadata 不传播 AirSim actor/truth 字段。`YoloMotAdapter` 已补实际 tracker selection、native/fallback/unavailable 状态、wall latency、预算比较、observed device、camera-local continuity 和离线 detector recall/precision/FN/FP；离线 bbox 不影响在线跟踪。单测覆盖 5v5 多相机、交叉、短时遮挡和跨 frame 防回填，D5 全量为 `101 passed`。本机 `best.pt` 与 Ultralytics 8.4.71 可加载推理；黑帧无目标时 ByteTrack/BoT-SORT 无 ID 并明确回退，该烟测只验证部署入口，不代表真实目标质量。

2026-07-11 M-to-N 联盟视觉完成汇总已闭合：新增 `CoalitionVisualSummary`、纯函数 `summarize_coalition_visual_completion()` 和 bus 便捷接口。hybrid 默认要求全部 active primary 当前锁定并各自连续至少 2 帧，standby reserve 的本资源/本相机几何匹配只输出 `reserve_ready_resource_ids`，不授权视觉 PNG，也不补足缺失 primary。接口继续阻断 plan/coalition version conflict、联盟外 lock、over-demand、单资源多 local lock 和跨 resource/camera bbox 借用，且只回显 D3/D2 已有 `assigned_global_track_id`。该段记录模块实现完成时的状态；后续真实 AirSim 验收见下文当前结论。

2026-07-11 AirSim full-flow 历史污染缺口已在 D5 闭合：`cross_view_associations()` 新增可选 `as_of_timestamp/max_age_s/plan_id/plan_version`。scope 模式只消费 freshness window 内当前 plan/version 的 observation，并按 resource 选择最新 timestamp，避免旧帧 local lock、旧 plan 多资源 lock 累积为当前 duplicate；同帧当前 plan 的未授权多资源 lock 仍保持 duplicate，合法 coalition 仍输出 `planned_cooperative_lock`。无参数调用保持旧离线行为。四类专项回归及当时全量 `127 passed`；这是实现时测试基线，后续 runtime 已完成当前计划作用域接线和验证。

2026-07-11 实施前三 seed 基线来自 `research_modules/airsim_runtime/outputs/blocks_cv_m5_n2_liveness_batch_20260711/M_TO_N_AIRSIM_CONVERGENCE_REPORT_CN.md`。seeds 7/17/27 均为 6 次 replan request、6 次 `no-change` ACK、0 applied、0 expired，需求满足率 1.0，错误重复锁定 0；T002 共识为 4/5/4，D7 每个 seed 产生 2 次终端合同许可。该结果证明 D5 快照作用域、合法协同锁解释和普通目标状态链已接入 main runtime；当时 T001 双 active-primary 共识三组均为 0。该历史基线不再代表当前 T001 验收状态。

以下是 2026-07-11 历史状态，当前状态以本文后续“2026-07-12 commit 33e6fa0 后状态同步”为准：

- **P0 已闭合，保持回归**：在线 truth/actor ID 隔离、相机作用域本地 ID、友方冲突、版本/时效、主动重捕获和 `global_track_id` 不变式。
- **P1 合同层已闭合**：ComputerVision 10 seeds 中 T001 双 active-primary 当前计划授权与视觉共识为 `8/10`；错误 duplicate 为 `0/10`，合法 `planned_cooperative_lock` 与错误重复锁分离。二级和完全分布式完整 ACK commit 正例均通过，缺 ACK 保守阻断 consensus/visual PNG authority 并 fail closed。
- **P1 物理/长期标定仍开放**：ComputerVision 的 `control_allowed_count=0`；SimpleFlight 15 s 仅为诊断，30 个 active pair 均未命中，其中 24 个为 `terminal_detection_timeout`。仍需持续检测、D5 lock、D7 gate、闭合速度和长时真实多 seed 物理闭环的分层验收。
- **Adapter/smoke/研究近似边界**：`YoloMotAdapter` 是 adapter，6 episode x 2 帧只证明最小图像链可运行且 accepted detection 仍为 0；IoU fallback 不代表 native MOT 质量；`TerminalCrossViewFusion` 是 metadata-only 研究近似，不代表三维多相机几何融合。
- **P2 仅隔离 optional benchmark**：OpenCV calibration/`solvePnP` 合成扰动 benchmark 已完成到可复现 CLI、48 个默认合成样本及投影/门控前后指标，但不进入在线 D5；Deep SORT/ReID、真实身份源和 ROS 2 `tf2/message_filters` 仍是 optional。P2 不进入默认依赖，不写回在线 `CameraModel`，默认在线路径仍是中心航迹投影、像素马氏门控、本地视觉轨迹和保守关联。

后续顺序调整为：保留 seed 7/27 合同回归，先定位 SimpleFlight 的持续 detection、D5 lock 和 D7 control gate 断点，再做长时多 seed 物理验收；P2 始终保持离线隔离。D5 模块验收命令保持为 `pytest -q research_modules/d5_terminal_association/tests`。

2026-07-11 本轮 detect-first/truth-isolated P1 已在 D5 模块闭合：默认在线输入仍是 `simGetDetections` bbox；actor/object/truth/global 字段置换不影响 camera-local ID 与几何关联，`association_source=geometric_detect`、`truth_identity_used=false` 成为强类型合同。`LocalVisualTrack` 和 `TerminalAssociation` 显式携带 `measured/predicted/lost`、measurement/arrival 双时间戳、measurement/prediction age、置信度和拒绝原因；bus 提供 JSON-friendly `runtime_records()`。predicted 不进入 assignment/stable count，不得伪装 `locked/registered`；重捕无论 local ID 是否相同都需要新的 measured geometry gate 与稳定帧。专项测试覆盖 actor/object ID 置换、predicted 禁锁、稳定重捕和 runtime/D6 字段消费，D5 全量为 `155 passed`。本轮 P2 YOLO/ByteTrack 数据集标定保持 deferred；已有 OpenCV geometry benchmark 只复核隔离状态，不进入默认在线路径。

2026-07-12 2v2 pilot 专项复核：`p1_5m_2v2_pilot_fix2_20260712/episode_006_full_flow` 的 36 个 D5 lock 经离线 truth 审计全部正确；48 个 ambiguous 主要由多候选 margin 不足产生，12 个 reacquire 均为预测投影出画面/到相机后方，无 friend/duplicate 硬冲突，且保持 truth-free 匿名 local continuity 和 `prediction_age_s=0.1-0.7 s`。发现并修复 D5 handoff evidence scope 缺陷：lost association 的 `local_track_id=None` 不再从同相机其他 actor 检测推导 measurement age、LOS 或 bbox stability，而是沿用自身最后 measurement/prediction age。新增两项回归后全量为 `157 passed`。该修复使 D4/D7 能区分短时预测 grace 与新鲜 measured 视觉，但不授权 D5 自行 coast、切换导引或降低 D7 独立门控。

2026-07-12 D7 视觉证据接口专项：D5 已新增 `CameraGeometryEvidence`，并把稳定 camera-local ID、MOT history、轨迹迁移/reset、measurement/arrival 双时间戳、detect source、bbox edge clipping、K、camera-to-NED 外参和姿态时效通过 detect/YOLO adapter、`TerminalAssociation` 与 runtime record 一致输出。完整几何才设置 `geometry_valid=true`；缺失项明确列入 unavailable reasons。在线 actor/object truth ID 仍被隔离，predicted/MOT coast 仍不能授权，`global_track_id` 不可改写。专项测试后全量为 `161 passed`。

该项关闭“D5 缺少供 D7 使用的稳定 truth-free 视觉证据 schema”。canonical actual 路径现已提供 measurement/arrival timestamp、camera pose、安装外参、同步姿态 timestamp/age，并把 `camera_geometry` 路由至 D5 adapter/D7 pair；该 main 接线不再开放。任一 case 字段未齐时 6D LOS 仍必须 fail closed 为 unavailable；真实几何 drift 和 YOLO/ByteTrack 多 seed 是 P1，完整在线 PnP 保持 P2。

### 2026-07-12 commit 33e6fa0 后历史状态同步

本节保留 commit `33e6fa0` 时的历史状态，不制造新完成项。当前判定以本文顶部 2026-07-13 实测结论为准。

| P0/P1 核查项 | 当前判定 | 实际证据 | 开放缺口/下一验收 |
|---|---|---|---|
| P0 truth 隔离、ID 不变式、friend/duplicate/predicted 门控 | 已闭合，保持回归；无新增 P0。 | D5 161 项测试；2v2 candidate、post-lock dropout 和 M5N2 短窗口均记录在线 truth 使用为 0。 | 任一 truth/local ID 参与 global binding、predicted/lost 获得 lock/authority、friend/duplicate 被绕过或 `global_track_id` 改写即重开 P0。 |
| P1 D5 truth-free 视觉证据 schema | D5 侧已闭合，保持原状态。 | `CameraGeometryEvidence` 及 adapter/association/runtime record 已携带 exposure/measurement/arrival timestamp、local transition/reset、MOT history、bbox clip、K、camera-to-NED 外参和姿态时效；缺失几何显式 unavailable。 | main/runtime 的真实 per-camera 曝光、安装外参、姿态同步、时延/漂移多 seed 标定仍开放；D5 不实现 D7 KF/TTC/LOS 滤波。 |
| P1 2v2 主线非退化 | 系统级通过，不等于新增 D5 算法完成。 | candidate 10 seeds 为 20/20 pair 在 5 m 内成功，旧基线 19/20，平均最小距离 4.844 m；自然 soft prediction/trend coast 均未触发。 | 继续分层审计 D5 lock/hold/reacquire、D7 gate、控制与物理结果，保持 wrong binding、ID rewrite 和在线 truth 使用为 0；不得归因于 D5 或新增外推。 |
| P1 锁定后短时丢检 | 两帧真实链路已验证，长窗口开放。 | 1.5-1.7 s 两帧 dropout 由 D7 在原 global/local track 与计划上下文内执行有界预测并达到 2/2；D5 仅提供身份、时序和 unavailable evidence。 | 运行 1-5 帧固定时刻矩阵；超过 0.25 s fail closed，重捕后重新满足 D5 measured geometry/stability，错误绑定为 0。 |
| P1 M5N2 视觉/联盟鲁棒性 | 开放。 | 最新实测为 120 条 active-primary/visible、74 条 D5 关联/锁定证据，最佳 coalition completion 5/10；ID rewrite 和 online truth use 均为 0。 | 第二 primary 稳定获取、bbox 稳定和连续 measured lock；目标至少 8/10，安全门控不变。 |
| P1 YOLO/native MOT | screening 已完成，准入开放。 | 18 case 中 20 m tracker 连续性/延迟达标，但 precision/recall 仅约 0.26-0.33；30/50 m 无检测，0 候选进入 confirmation。 | bbox 定义/尺度/时间对齐、远距召回和候选多 seed confirmation；默认 detect 不变。 |
| P1 二级同 tick freshness；P2 真实友方来源 | 分级开放。 | 60-case 基础 registration 已闭合但完整同帧覆盖不足；D5 frame-scoped DTO 已实现；真实身份源未接入且不属于 P1。 | P1 验收 main/D4 同 tick freshness/threshold version/状态迁移；P2 再接入真实 `IdentityClaim` adapter。 |

因此当前开放 P1 不是 D5 schema 缺失，而是 M5N2 第二 primary、真实几何 drift、detect/YOLO/MOT 多 seed 和二级同 tick freshness；遮挡/交叉归入多 seed 矩阵。真实友方身份源保持 P2。2v2 20/20 只关闭该场景的主线非退化门槛，不能提前关闭这些 P1。

2026-07-11 D5 coalition commit gate 已完成模块内 P1：纯函数和 bus 薄封装均接受 duck-typed `coalition_commit` 及显式评估时刻/center-failed/fallback 标记。`CoalitionVisualSummary` 新增 `coalition_commit_required/valid/state/epoch/lease`、required/acked member 和 conflict reason 字段。中心正常且不提供 commit 时旧中心合同不变；`k>1` fallback 只有 `committed|executing`、有效 lease、epoch/双版本一致、required member 完整且全部 ACK 才能形成 consensus/visual PNG authorization。单 primary、reserve-only、旧 epoch、过期 lease、缺 ACK、版本冲突、未提交和 center-failed 缺 commit 均 fail closed；reserve readiness 与视觉 cue 仍保留。truth/actor metadata 不参与 commit 或目标绑定。当前 runtime 验证已覆盖二级/完全分布式完整 ACK 正例和缺 ACK fail-closed；这仍只证明合同执行语义，不证明物理拦截。

2026-07-11 D5 P2 OpenCV 几何扰动 benchmark 已完成。新增模块和 CLI 使用既有 `CameraModel`/`GlobalTrack` 合同生成可复现合成标定/运动目标，执行 `cv2.calibrateCamera`、带漂移初值的 `cv2.solvePnP`，注入外参平移/旋转和 measurement/arrival 时间偏差，统计 calibration/PnP 重投影误差、pre/post/arrival 投影 RMSE、真门控接受率和离线假候选错误接受率。默认 seed 7 为 48 样本，约 24.0 px -> 1.63 px、true accept 0.0 -> 1.0、false accept 1.0 -> 0.0。OpenCV 不可用明确返回 unavailable；truth label 只在 gate 后附加，标签变化不改变几何指标。增加该 benchmark 时 D5 全量为 `143 passed`。该项关闭的是“缺隔离式 P2 对照”，不关闭真实图像标定、PnP RANSAC、在线漂移估计或 AirSim 物理闭环。

2026-07-11 D5 受控跨版本稳定延续 P1 已在模块内闭合并按真实复验二次修正。根因是 T001 primary INT-02/INT-03 保持不变、reserve INT-01 -> INT-04，但 plan/coalition version 同时 1 -> 2，旧逻辑把 `coalition_version` 当不可变 identity。新逻辑由 bus 保存 immutable binding snapshot；当前帧必须严格匹配当前双版本，历史只在 plan/coalition version 同时严格升高且 owner/node、`coalition_id`、target/global ID、primary resource-target binding 集合、role、epoch、demand 和 authorization 不变时贡献计数。plan ID 和 reserve 可变化，输出始终是当前新版本。primary 换员、target rebind、owner/epoch/coalition ID 变化、相同/下降 coalition version、stale plan、friend/duplicate/wrong-binding、过期证据及历史 commit conflict 均清零或 fail closed。当前 10-seed ComputerVision 结果已形成 `8/10` 双 primary 合同验收；剩余缺口是 control gate 和物理闭环，不是 D5 stability state。

2026-07-08 P1 calibration sweep 集成复核：main runtime 已新增 P1 D4/D5 calibration sweep，可扫描二级高度、FOV、二级节点数量和 standoff，并在每个组合内运行多 seed D4/D5 stress。D4/D5 stress 链路已可把 D5 detect-to-global-track registration 产生的 `TerminalObservation`、`CrossViewAssociation`、registration reason、secondary coverage funnel 和 mobile gimbal metadata 写入统一 observation/report 流；D6 标准报告 bundle 已由 main runtime 自动生成，包含 `d6_airsim_calibration/airsim_calibration_records.csv`、`airsim_calibration_summary.csv`、`airsim_calibration_summary.json` 和 `airsim_calibration_report.md`。因此 D5 当前没有“缺 registration helper 或缺标准报告输入合同”的 P1 接口缺口；当前 P1 仍按顶部四类状态执行。

2026-07-10 2v2 smoke 复核：`outputs/p1_gap_closure_2v2_smoke_20260710` 中 2/2 资源对完成 `collision_intercept`，pair summary 的 D5 状态均为 `locked`；D7/main 因 `bbox_near_image_edge` 拒绝视觉接管 9 次、覆盖 2 个资源对，仅 2 个控制记录允许 terminal switch。安全上该结果正确，因为 D5 lock 没有绕过 D7 独立 camera/LOS/maneuver gate；工程上仍需 P1 标定边缘裕量、连续边缘帧、相机指向和 handoff 抖动。

P0 状态：无 blocker，端到端 AirSim runtime truth 隔离 P0 已闭合。D5 已闭合主动重捕获、时序/稳定窗口、calibration health、active reacquire 友方声明复检和 detection category/truth 隔离。main hotfix 为 builtin detect 增加按 camera 分区的匿名 bbox tracker，ID 不含 actor 名、仅由 bbox IoU/中心距离维持连续性并在 episode setup reset；actor 名只留在 offline truth metadata。episode bus 在线 D5 路径不读取 `object_id`，truth map 只用于决策后的离线评分；intercept 注入及 D4/D5 fallback 的 actor-name local ID 也已清理。验收证据为 `research_modules/airsim_runtime/outputs/p0_truth_isolation_smoke_20260710`：三类 case 均 connected、各 5 帧，local/detection ID actor 泄漏为 0，匿名 ID history 达 5，所有 actor 名记录均为 `offline_truth_only=True`，每类 cross-view association 均为 4。D5 安全合同保持为不分配、不授权、不改写 `global_track_id`，且不对任意既有 tracker ID 做猜测式重写。

| EVAL P0-B 项 | 当前状态 | 已闭合实现 | 验收口径 |
|---|---|---|---|
| 主动重捕获 | 已闭合，保持回归。 | `TerminalAssociator` 保留 per `resource_id + assigned_global_track_id` 历史；predicted 仅输出匿名 `reacquire` 证据并打断稳定窗口。检测恢复后无论 local ID 是否相同，都需重新通过 measured geometry gate 与 stable window。 | `test_active_reacquire_recovers_assigned_track_from_search_window`、`test_reacquire_with_new_mot_id_requires_stable_bbox_history` 和 `test_predicted_track_never_locks_and_reacquire_requires_fresh_stable_measurements` 覆盖；恢复仍只输出当前 `assigned_global_track_id`，不创建、不改写、不换绑 `global_track_id`。 |
| Active reacquire 友方声明复检 | 已闭合，保持回归。 | active reacquire candidate 复用 `IdentityChecker.friend_conflict_state()`；verified/stale/unverified/spoof-suspected 重叠均强制 `hold`，输出顶层与 candidate/search-window `friend_conflict_state` 和 reason。 | `test_active_reacquire_friend_claims_force_auditable_hold` 覆盖同一/新 MOT ID 和四类 auth state；任何冲突不得 `locked`，不得改写 `global_track_id`。 |
| Detection category/truth 隔离 | 已闭合，保持回归。 | AirSim、offline YOLO 和 frame YOLO record 只从显式 detector 类别字段得到在线类别；D5 adapter 过滤 actor/truth alias。main builtin detect 使用匿名 camera-local bbox tracker，intercept/fallback local ID 不嵌 actor 名。 | D5 回归、targeted runtime test 和 `outputs/p0_truth_isolation_smoke_20260710` 真实三 case 验收均通过；持续要求 offline truth 不进入 D5 cost/binding。 |
| 时序一致性和稳定窗口 | 已闭合，保持回归。 | 重捕获后加强 `candidate_cost_margin`、stable window、bbox area ratio、MOT history、measurement stale/OOSM 和 friend/version/authorization 阻断；`TerminalConsistencyTracker` 的 stable 判定使用明确 margin、稳定帧和 lock age/inf margin。 | `pytest -q research_modules/d5_terminal_association/tests` 覆盖；stale、assignment mismatch、friend conflict、duplicate risk 仍不得升级为 `locked`。 |
| 相机校准健康监测 | 已闭合，保持回归。 | `TerminalAssociation.metadata`、`TerminalConsistencySummary.to_metadata()`、registration candidate/observation/result summary 输出 `projection_valid`、`reprojection_error`/`reprojection_error_px`、`camera_pose_source`、`camera_pose_source_trusted`、`calibration_health`、`calibration_health_reason`、`drift_warning`、health/source counts 和重投影误差摘要。 | `test_decision_metadata_records_geometry_gate_and_measurement_age_fields` 与 `test_registration_logs_pose_source_bbox_area_and_offline_truth_without_using_truth_for_binding` 覆盖；P0-B 只监测/告警，不做在线标定。 |

P1 状态：以下是 EVAL 确认的 D5 P1 能力增强项。它们不覆盖上表 P0-B 的最小硬化范围，也不得改变 D5 不分配、不换绑 `global_track_id` 和 truth ID 仅离线评分的边界。

| EVAL P1 项 | 当前状态保留 | P1 后续边界 |
|---|---|---|
| YOLOv8 + ByteTrack/BoT-SORT 多 seed 标定 | 18-case 原生 screening 已完成。20 m native active/continuity 为 1.0、IDSW 为 0、P95 约 7.4/16.2 ms；precision/recall 约 0.26-0.33，30/50 m 无检测，0 候选进入 confirmation。 | 先校正 bbox 定义/尺度/时间对齐并恢复远距召回；候选通过 screening 后再做至少 10 seeds confirmation。tracker/local ID 仍只作为本地证据，不替代 `global_track_id`，默认 detect 不变。 |
| 多相机 detector/tracker 状态隔离 | 已闭合，保持回归。`YoloMotAdapter` 按 `(resource_id, camera_id)` 持久化 fallback tracker 和 native model/tracker，并提供 `reset_stream()` / `reset_all_streams()`。metadata 记录 stream key、实际 backend 和状态作用域。 | main 必须保持 stream key 稳定并在 episode 边界 reset；native 每 stream 独立模型会增加内存/显存和首帧加载时延，但不得为节省资源而静默共享 `persist=True` tracker state。 |
| IBVS/间歇可见性重捕获对照 | P0-B 已有投影/search-window 主动重捕获、stable window 和 handoff blocker metadata；D5 当前不实现视觉伺服控制器。 | 用 replay 或对照实验统计 lost/reacquire 时间下降，并保持误锁为 0；D5 只输出 `TerminalAssociation`/`IdentityClaim` 证据，不授权、不重新分配、不驱动 D7 绕过 gate。 |
| 多模态友方识别 replay adapter | `IdentityClaim` 抽象和 simulated Remote ID/OpenDroneID 风格字段已可表达 verified/stale/spoof/unverified，verified friend overlap 会触发 `hold`。 | 至少接入一个 replay adapter，将 Remote ID/MAVLink/DDS/AprilTag 等来源归一化为 `IdentityClaim`；未知或 stale 不升级目标，不绕过几何门控和 assignment 一致性。 |
| 完整相机在线标定/畸变校正 | `CameraModel` 已消费 K/R/t/dist，`projectPoints` 可使用畸变参数；隔离式 P2 已运行合成 calibration/`solvePnP`，但在线标定仍未落地。 | 基于真实 replay/标定样本建立 2D-3D 对应、PnP RANSAC、外参漂移估计和重投影误差验收；将 distortion 接入 projection/registration/误差报告并量化重投影误差下降，不替代上游 `GlobalTrack` 或 D3/D4 gate。 |
| 视觉接管图像边缘裕量 | 2v2 smoke 已记录 `bbox_near_image_edge` 9 次且覆盖 2 个资源对；D7 独立 gate 保守拒绝，未形成安全绕过。 | 跨 seed 统计 bbox 到边界的归一化最小裕量、连续边缘帧、相机指向误差和 D5 handoff 到 D7 reject 的转移；可增强 D5 advisory metadata，但不得降低 D7 camera/LOS/maneuver gate。 |
| 外参漂移与时间同步鲁棒性 | 已携带 K/R/t/dist、measurement/arrival timestamp、measurement age 和 calibration-health 字段；P2 已有合成扰动 benchmark，但尚无真实 AirSim/replay 多 seed 系统标定。 | 注入或采集姿态/位置外参漂移及时间延迟/抖动，统计重投影误差、门控拒绝、误锁和恢复时间；在线逻辑不得读取 truth 位姿补偿。 |
| D4 逐决策 evidence 合同 | D5 已输出 CrossView/Consistency/registration evidence；当前 60-case 报告主要证明 episode 聚合可用。 | 每个 D4 决策 tick 携带 stable/not-registered count、timestamp/age、camera/resource scope、threshold version 和 conflict reasons；D5 只提供证据，不触发降级。 |
| 遮挡/交叉和 MOT ID 变化 | 已有 active reacquire 与 stable window 单元能力；缺真实多相机连续图像压力标定。 | 覆盖同视角交叉、跨视角部分重叠、短时全遮挡和 local ID 变化；候选不唯一时保持 `ambiguous/hold/reacquire`，不得本地换绑全局 ID。 |

## 跨模块合同结论

- 与 D4：D5 输出的是 terminal visual evidence，不是分配结果。`CrossViewAssociation`、`TerminalConsistencySummary`、`DistributedTerminalAssociation`、`duplicate_terminal_lock_risk`、`hypothesis_only/hold/ambiguous` 原因和 `recommended_d4_action` 可作为 D4 CBBA/主动降级的风险加权输入；D5 不生成 `AssignmentPlan`，不选择主备资源，不改写、不新建、不换绑 `global_track_id`。
- 与 D7：D7 视觉 PNG 切换必须依赖 D5 `locked`、当前 D3/D4 `assigned_global_track_id` 一致、bbox 连续稳定、无友方冲突、无重复锁定风险，并通过 D4/D3 gate。D5 的 `visual_png_prelock_recommended` 或 `handoff_recommended` 只是前置证据；D7 仍需独立检查 LOS、相机状态、导引律、机动裕度、检测延迟和 terminal gate。
- 与 AirSim/runtime：在线 D5 不能使用 AirSim `object_id`、`actor_name`、actor truth ID 或离线 truth map 做关联、过滤、换绑或锁定。D5 adapter 过滤 actor/truth alias；main builtin detect 输出匿名 camera-local ID，episode bus 在线路径不读取 `object_id`，intercept/fallback 不生成 actor-name local ID。真实三 case 已完成验收，truth ID 只允许在离线 metadata/evaluator 中计算 `terminal_lock_accuracy`、`locked_mismatch`、stress report 和测试断言。
- 与规模参数：2v2 与 5v5 只是 baseline 和 stress scenario 名称。D5 算法按传入的 `LocalVisualTrack[]`、`GlobalTrack[]`、camera/resource 列表、`TerminalObservation[]` 或 peer DTO 数组长度运行，不写死资源数或目标数。

## 已实现

| 能力项 | 当前状态与证据 | 说明 |
|---|---|---|
| `LocalVisualTrack` | 已实现。`models.py` 定义本地轨迹；`airsim_cv_adapter.py::local_visual_tracks_from_sim_detections()`、`local_visual_tracks_from_offline_yolo_bytetrack()` 和 `yolo_mot_adapter.py::YoloMotAdapter.process_frame()` 可从 AirSim bbox、离线 schema 或图像帧 detector/tracker 输出生成中心点、bbox、质量、类别和 `mot_history_length`。 | 只标准化本地检测/MOT 输出，不携带 truth/global ID；tracker ID 只能是本地 ID。 |
| `TerminalAssociation` | 已实现。`associator.py::TerminalAssociator.decide()` 只评估 `Assignment.assigned_global_track_id`，输出 `locked/ambiguous/hold/reacquire`、候选代价、友方冲突、cue 使用标记和 per-pair geometry log metadata。 | 不是重分配器，不会选择另一个全局 ID 作为新分配。 |
| OpenCV `projectPoints` / 几何门控 | 已实现单相机版。`geometry.py::_project_pixel()` 优先调用 `cv2.projectPoints`，不可用时退回针孔公式；`project_track()` 传播协方差，`mahalanobis_d2()` 做像素马氏距离。 | 只消费已有 `CameraModel.K/R/t/dist_coeffs`，不估计标定参数。 |
| AirSim 相机几何 adapter | 已实现模块内验证辅助。`airsim_geometry.py` 提供 FOV 到 K、AirSim quaternion 到 OpenCV camera rotation、`camera_model_from_airsim_camera_info()`、`associate_tracks_to_detections_geometrically()` 和 `GeometricAssociationResult.to_log_records()`。 | 用于 D5 几何验证；不调用 AirSim API，也不依赖 object truth；main/D6 已接入 actual 日志，后续 P1 是多 seed drift/时延标定。 |
| AirSim `simGetDetections` bbox adapter | 已实现 dry-run 适配。`airsim_cv_adapter.py` 接受 `box2D`、`bbox_xyxy`、`xyxy` 等 schema，发布到 `TerminalObservationBus`。 | 不导入 AirSim；真实采集由 main/runtime 负责。 |
| YOLOv8 + ByteTrack/BoT-SORT adapter | 已实现模块 adapter。`YoloMotAdapter` 默认权重路径为 `/home/linux/Documents/MSM/research_modules/d5_terminal_association/best.pt` 且允许覆盖；可请求 ultralytics ByteTrack/BoT-SORT，缺依赖/权重/原生 tracker 时返回 `unavailable` 或使用确定性 IoU fallback。测试覆盖 mock 输出、truth/global 隔离、交错 stream、episode reset、native 隔离和 native-to-fallback。 | main 已完成 6 episode x 2 帧最小 AirSim smoke；持续图像、非零检测、native MOT、多 seed 和 GPU/CPU 质量标定仍未闭合。D5 不管理 runtime 部署，也不把 tracker ID 替代 `global_track_id`。 |
| AirSim truth ID 隔离 | 已实现并完成真实 AirSim 验收。D5 adapter 过滤 truth alias；main 匿名 camera-local bbox tracker 和 episode bus 在线/离线分流已接通。 | `outputs/p0_truth_isolation_smoke_20260710` 三类 case 的 ID、history、offline truth flag 和 cross-view evidence 均满足关闭条件；保持回归。 |
| `global_track_id` 不变式 | 已实现。`GlobalTrack` frozen；`TerminalAssociator` 记录输入 ID 并 `_assert_global_ids_unchanged()`；`TerminalObservationBus` 只按已有 `assigned_global_track_id` 分组。 | D5 只输出 evidence，不能成为分配权威。 |
| `IdentityClaim` 抽象 | 已实现模拟层。`identity.py::IdentityChecker.parse_claims()` 可把 Remote ID/OpenDroneID 风格 dict 和通用签名字段转为 `IdentityClaim`；verified friend overlap 触发 `hold`。 | 只做正向友方确认；未知不升级。 |
| 二级节点 cue | 已实现摘要/代价基线。`ReconImageCue` 有 producer、frame、global ID、center/bbox、confidence、scope、metadata；`associator.py` 校验 scope、age、frame 和 `reprojected_to_local_camera` 后给代价 bonus。 | cue 不能绕过授权、版本、友方冲突和 MOT 质量门槛。 |
| 跨视角重复锁定 | 已实现摘要层。`observation_bus.py::cross_view_associations()` 按既有全局 ID 汇总多资源支持，命名空间化 local ID，并输出 `duplicate_terminal_lock_risk`；在线可用 timestamp freshness、plan identity 和 per-resource latest-frame scope，避免历史污染。 | 无参数保留全历史离线兼容；main 在线必须传当前 frame timestamp、freshness 和当前 plan ID/version。D5 只上报给 D3/D4 仲裁，不解除锁定，不改计划。 |
| M-to-N 联盟视觉完成汇总 | 已实现。`coalition_visual.py::summarize_coalition_visual_completion()` 和 `TerminalObservationBus.coalition_visual_summary()` 读取 D3 coalition bindings 与当前/历史 association，输出 primary 完成、reserve readiness、consensus、稳定帧、计划内协同 lock 和冲突字段；10-seed CV 双 primary 为 `8/10`。 | reserve readiness 不授权视觉 PNG；二级 cue/其他相机 bbox 不替代本机 lock；持续 detection 与 control gate 仍是物理闭环缺口。 |
| 完全分布式跨 peer 视觉假设 | 已实现 P0 metadata-only。`terminal_cross_view_fusion.py::TerminalCrossViewFusion` 消费 `DistributedVisualObservation`、`VisualTrackletSummary` 和 `PeerCameraState`，基于时间、bearing、bearing rate、bbox area/scale rate、类别/置信度、像素协方差和姿态协方差 gating/cost，输出 `CrossPeerAssociationHypothesis` 与 `DistributedTerminalAssociation`。 | 使用 Hungarian；SciPy 不可用时退回纯 Python 最小代价唯一匹配。missing/stale `global_track_id`、重复锁定、友方冲突或 local/global ID 冲突不会输出 `locked`。 |
| 一致性摘要 | 已实现。`consistency.py::TerminalConsistencyTracker` 输出 `TerminalConsistencySummary`，包含 lock age、连续 ambiguous/hold/reacquire、丢锁/重捕获、重复锁定风险、cross-view support 和 `recommended_d4_action`。2026-07-07 已将连续窗口 key 固化为 `resource_id + assigned_global_track_id`，避免同一 assignment pair 的滚动 plan version 更新清空 D4 需要的连续视觉状态。 | 是 D4/D6 advisory summary，不替代 D4 仲裁；D5 仍不因连续丢锁触发降级。 |
| 二级计划 2v2 语义 | 已实现测试覆盖。`test_airsim_cv_2v2_secondary_plan.py` 覆盖二级 plan 输入后只锁定 `assigned_global_track_id`、locked mismatch 只进入问题统计、不改写 ID、友方冲突阻断。 | 2v2 是测试语义，不是算法规模上限。 |
| N-v-N stress 指标 | 已实现 D5 helper。`compute_terminal_stress_metrics()` 与 `summarize_degradation_case()` 输出 per-camera count、multi-target FOV、cross-view overlap、duplicate risk、lock accuracy、ambiguous count 和三类 degradation evidence。 | 5v5 只是默认 stress baseline；`AirSimCVScenarioSpec` 支持传入不同数量。 |
| Multi-seed calibration readiness | 已实现 D5 helper。`summarize_multiseed_calibration_readiness()` 对每个 seed 的 `TerminalObservation`/`CrossViewAssociation` 做字段覆盖审计，输出 required/recommended missing fields、AirSim/YOLO source/backend counts、offline truth label count、measurement age、bbox stability、handoff advisory、duplicate/friend conflict evidence 计数。 | 只做被动审计；truth label 只从离线 metadata 计数，不参与在线关联或换绑。 |
| 二级覆盖/漏斗诊断 | 已实现 D5 helper。`summarize_secondary_visual_coverage_funnel()` 对 replay frame、`TerminalObservation` 和 `CrossViewAssociation` 输出单二级相机 full-view 率、二级网络联合 full-view 率、每帧可见目标数、覆盖比例均值/最小值，以及 detect/local-or-recon/terminal/cross-view/multi-support 漏斗计数和断点原因。 | offline target label 只用于“看见目标”覆盖统计；形成全局支持仍必须依赖已有 `TerminalAssociation.assigned_global_track_id` 和 `CrossViewAssociation`。 |
| Detect-to-global-track registration | 已实现 D5 helper。`register_local_visual_tracks_to_global_tracks()` 消费 `GlobalTrack[]`、D2/D3 binding/`Assignment`、per-camera `CameraModel(K/R/t)`、timestamp、像素协方差和 `LocalVisualTrack[]`，用像素马氏距离 + Hungarian 选择注册对，并保留 gated candidates 供 JPDA-compatible 下游使用。输出 `DetectToGlobalTrackCandidate`、`TerminalObservation`、即时 `CrossViewAssociation`、稳定 `stable_cross_view_associations` 和 reason counts。P1 已补齐 `camera_pose_source`、`pixel_error_px`、`mahalanobis_d2`、`gate_pass`、`projection_valid`、`bbox_area_px`、离线 `offline_truth_global_id`、bbox 自适应像素协方差和 3 帧 2 次通过的稳定注册窗口。 | 只增加对既有 `global_track_id` 的支持证据；不新建、不重绑、不授权，不让 YOLO/MOT tracker ID 或 AirSim truth/actor ID 替代全局 ID。main P1 sweep 已可消费该证据，后续重点是 AirSim 真实 camera pose 接线、多 seed 阈值、二级覆盖策略和 `stability_window_failed` 验收。 |
| 机动高空侦察云台 cue evidence | 已实现 D5 DTO/summary 字段。`ReconImageCue`、`CrossViewAssociation.metadata` 和 `SecondaryVisualCoverageFunnelSummary.metadata` 可携带 `cue_position_ned`、`look_at_ned`、`gimbal_pointing_metadata`、`cue_pointing_error_m/rad`、`gimbal_track_error_px`、`cue_source=radar_global_track_cue`、`capability_class=mobile_high_recon` 和 `coverage_mode=mobile_recon_gimbal`。测试覆盖固定俯视不足时移动云台补足二级网络联合覆盖。 | 只证明证据字段和 coverage/cross-view 汇总；真实云台控制、传感器指向闭环和多 seed D6 趋势分析仍在 D5 外。 |
| 视觉 PNG handoff 建议 | 已实现 advisory metadata。`visual_handoff.py::annotate_visual_png_handoff()` 在已有 `TerminalAssociation` 上附加 bbox 稳定、距离区间、TGO、延迟、measurement age、LOS rate、friend/duplicate 风险和 maneuver margin 等建议。 | D5 不决定导引律；D7/main 仍需独立 gate；stale measurement age 和 missing LOS 会阻断建议。 |
| P1 calibration sweep / D6 bundle 输入合同 | 已实现接口层状态。main runtime 已可在 P1 sweep 中消费 D5 registration observation、secondary funnel 和 mobile gimbal metadata，并自动调用 D6 输出标准 CSV/JSON/Markdown bundle。 | D5 不运行 AirSim、不调度 sweep、不生成系统报告；后续验收重点是实际多 seed 数据是否提升注册率、覆盖率和降级 case 质量。 |

已实现项的安全边界：

- `locked` 只表示“当前分配 ID 的视觉候选被保守支持”，不是处置授权。
- `hypothesis_only` 只表示“peer metadata 之间可能支持同一视觉目标”，没有 current `assigned_global_track_id` 时不能升级为 `locked`。
- 重复锁定、友方冲突、stale ID、global/local ID 冲突都只输出风险和仲裁建议，不在 D5 内解除冲突。

## 部分实现

| 能力项 | 已有部分 | 未完成部分 | 未完成原因 | 缺少条件 | 优先级 |
|---|---|---|---|---|---|
| OpenCV calibration / 畸变使用 | `CameraModel` 可携带 `dist_coeffs`，`projectPoints` 会消费；P2 合成 benchmark 已调用 `calibrateCamera` 并输出 RMS/K 误差。 | 没有真实标定图像采集、棋盘/AprilTag 角点链或在线标定。 | 当前 benchmark 只验证可复现数值敏感性，不代表 AirSim/硬件标定质量。 | 真实标定图像、畸变模型选择、设备/温漂验收阈值。 | P2 benchmark 已完成；真实链待后续 |
| OpenCV `solvePnP` | P2 合成 benchmark 已调用带外参漂移初值的 `cv2.solvePnP`，输出位姿/重投影及门控前后指标。 | 没有 PnP RANSAC、真实 2D-3D 对应管理或在线外参更新。 | 默认在线 D5 仍只消费上游 `CameraModel.R/t`；benchmark 不写回在线相机。 | 真实对应、RANSAC/outlier 策略、外参漂移判据和回放样本。 | P2 benchmark 已完成；真实链待后续 |
| OpenDroneID / Remote ID | `IdentityChecker` 可解析 `protocol=OpenDroneID` 风格字典并给出 verified/stale/spoof_suspected。 | 未接 OpenDroneID Core C，未解析真实广播报文。 | 缺少真实 Remote ID 数据源、签名/来源校验和平台白名单。 | OpenDroneID decoder、密钥/白名单、位置一致性检查、时间同步。 | P1/P2 |
| MAVLink signing | `IdentityChecker` 可消费 `signed/signature_valid` 风格模拟字段。 | 未验证真实 MAVLink signing，也没有 key 管理。 | 当前没有 MAVLink telemetry source。 | MAVLink 消息流、签名校验库、系统 ID/组件 ID 策略、密钥和时钟策略。 | P2 |
| 跨视角高阶几何优化 | `TerminalObservationBus`、`CrossViewAssociation` 和 `TerminalCrossViewFusion` 已覆盖摘要层与 metadata-only P0 假设生成，包含 measurement/arrival timestamp、协方差、frame/resource/local ID 命名空间和姿态协方差 cost。 | 没有三维重投影、三角化、bundle adjustment、D2 航迹联合预测或跨相机几何优化。 | P0 只需要 metadata-only 分布式假设供 D4 消费；真实 3D 几何需要更完整的相机/D2 合同。 | 每相机 `CameraModel`、D2 `GlobalTrack[]`、时间同步、三维候选生成、几何残差模型。 | P2 |
| 二级侦察图像 cue | 已有 `ReconImageCue`、scope/age/frame/reprojection 校验和代价 bonus。 | 没有从二级相机图像检测结果反投影到 3D 再重投影到拦截机相机。 | 缺少二级相机真实 detection、pose、深度/三维目标估计。 | 二级相机标定和 pose、目标三维估计、cue 新鲜度策略、目标相机 frame 映射。 | P2 |
| MOT 输入质量 | 已按 `(resource_id, camera_id)` 隔离并持久化 Ultralytics native tracker 或 IoU fallback；18-case screening 已给出 continuity、IDSW、latency 和 detector precision/recall。 | 尚未通过 bbox agreement、30/50 m 召回和候选多 seed confirmation，也未完成遮挡恢复与资源预算分布。 | 20 m tracker runtime 已可用，但 detector 质量不足且没有准入候选。 | 对齐 bbox/时间、改进远距检测，候选通过后运行至少 10 seeds confirmation。 | P1 |

部分实现项的口径：

- “接入 OpenCV”当前只代表投影/畸变参数消费，不代表已经具备真实标定链。
- “兼容 YOLO”当前代表已有 bbox schema adapter 和 `YoloMotAdapter` frame adapter；不代表 main runtime 已把 AirSim 连续图像流、部署参数和多 seed 标定闭环接好。
- “支持 OpenDroneID/MAVLink/DDS/AprilTag”当前只代表 `IdentityClaim` 抽象可表达这些来源，不代表真实协议或 detector 已接入。
- “支持 distributed visual association”当前只代表 metadata-only peer evidence，不代表完成三维几何配准、三角化或跨相机 bundle adjustment。

## 未实现

| 未实现项 | 未实现原因 | 缺少条件 | 下一步优先级 |
|---|---|---|---|
| main runtime 持续图像质量闭环 | D5 adapter 和 main 的 18-case screening 已能持续传递 RGB、stream identity、在线 truth 隔离和离线评分事件；20 m native tracker 可运行，但 detector agreement 低且 30/50 m 无检测。 | bbox 定义/尺度/时间对齐证据、远距非零检测、候选配置和多 seed confirmation。 | P1：检测质量与真实多 seed 准入，不替换 D5 几何主线。 |
| BoT-SORT 工程质量评估 | D5 可请求 ultralytics BoT-SORT 或退回 IoU tracker，但小目标运动相机质量未评估。 | 连续图像、相机运动估计、BoT-SORT 依赖、ReID 模型、算力预算、IDF1/IDSW 真值。 | P2：真实图像链路后再评估。 |
| Deep SORT | 小型无人机外观纹理弱，当前没有 embedding 提取或外观真值。 | 图像帧、检测器、embedding 模型、IDSW/IDF1 评估数据。 | P2：作为对照，不作为默认主线。 |
| DDS Security | D5 不运行 ROS 2/DDS middleware。 | ROS 2 runtime、enclave、证书、权限文件、节点身份到 `IdentityClaim` 的映射。 | P2：仅在 ROS 2/DDS runtime 或回放链路确定后实施。 |
| AprilTag | 当前图像帧 adapter 不运行 AprilTag detector，也没有 tag ID 到 `IdentityClaim` 的可信映射。 | RGB/灰度图、AprilTag detector、tag ID 到友方平台映射、误检/漏检评估。 | P2。 |
| ROS 2 `tf2/message_filters` | 仓库当前是 Python 离线/AirSim runtime，不启动 ROS 图。 | 带戳 topic schema、frame tree、ApproximateTime/ExactTime 同步策略、bag/replay。 | P2：仅在项目进入 ROS 2 runtime 或 bag replay 后实施。 |
| 真实图像保存/处理 | D5 默认 metadata-only，不保存 PNG；图像链路不应成为当前逻辑依赖。 | 若接入 MOT/AprilTag，需要图像帧、存储策略、离线复盘格式。 | P2。 |
| 跨相机三维联合优化器 | 当前 `TerminalCrossViewFusion` 是 metadata-only P0，不做三维相机几何联合优化。 | 多相机 `CameraModel`、D2 航迹预测、同步时间戳、三维候选、重投影残差、冲突状态机。 | P2。 |
| YOLOv8 runtime 部署标定 | D5 adapter 已加载 `best.pt` 并完成 18-case AirSim screening；20 m 延迟和 tracker 连续性可用，但 detector precision/recall 低、30/50 m 无检测，尚无准入候选。 | bbox agreement/尺度/时间对齐、远距召回、候选配置、CPU/GPU 预算和至少 10 seeds confirmation。 | P1：检测质量与多 seed 准入。 |

2026-07-11 回归补充：D5 已修复 `offline_truth_detections=tuple[tuple[x1,y1,x2,y2], ...]` 被通用归一化递归拆成标量的问题。离线 evaluator 现稳健支持单 bbox、多 bbox、dict/object detection，并对畸形输入给出明确错误；解析结果仍仅用于 recall/precision/FN/FP/IoU，不能进入在线 MOT 或 `global_track_id` binding。真实 AirSim 多 seed 质量标定仍为 P1，不因该接口修复而宣称闭合。

2026-07-11 真实证据补充：三组既有 D4/D5 回归均形成 `cross_view_association_count=4`，稳定注册约 19-61，但二级同帧全目标覆盖仍不足。`p1_yolov8_bytetrack_smoke_fixed_20260711` 完成 6 episode、每个 2 帧，验证 AirSim RGB -> YOLOv8 -> tracker adapter -> D5 event、在线 truth 隔离和 offline bbox-only 评分合同均可运行；这关闭的是接口 P1。质量 P1 未关闭：当前几何下 `accepted_detection_count=0`，AirSim offline truth boxes 多数为 0，原生 ByteTrack 因无 track ID 回退 `iou_fallback`，延时多数约 38-49 ms、首轮约 197 ms。没有非零检测就不能声明 detector recall、native MOT continuity、IDSW/IDF1 或 cross-view registration 已由 YOLO 路径验证。

按工程链路归纳的未实现项：

- 真实多目标检测器：D5 已有 YOLOv8 frame adapter，main 的最小 AirSim 图像链已 smoke；仍缺持续多帧、非零 accepted detection、class map、阈值策略、硬件加速和误检/漏检多 seed 评估。
- 真实 MOT：D5 已有 ByteTrack/BoT-SORT 请求路径和 IoU fallback；仍缺长遮挡恢复、ReID embedding、frame-to-frame IDSW 统计和 MOT 真值。
- 真实标定链：P2 合成 `calibrateCamera`/`solvePnP` 与重投影指标已完成，但没有真实标定图像、棋盘/AprilTag 角点、相机-机体系-世界系同步姿态、PnP RANSAC、在线外参更新和真实漂移告警验收。
- 真实身份认证链路：没有 OpenDroneID/MAVLink/DDS 实际报文、密钥/证书/白名单管理、时间同步、消息来源到平台身份的可信映射，也没有 AprilTag detector。

## 未实现原因归纳

1. **当前主线是轻量可复现离线科研链路**：D5 默认测试只依赖 Python、NumPy、OpenCV 和 pytest，不强制 AirSim、ROS 2、GPU、MAVLink 或真实 Remote ID 硬件。
2. **D5 的职责是消费抽象证据而不是运行所有外部栈**：MOT、Remote ID、MAVLink、DDS、AprilTag 都应先归一化为 `LocalVisualTrack` 或 `IdentityClaim` 后进入 D5。
3. **真实图像/协议/密钥/标定数据缺失**：未实现项多数需要连续图像帧、协议报文、密钥、标定板/特征点、相机姿态和多源时间同步。
4. **安全边界优先于锁定率**：当前实现宁愿输出 `ambiguous/hold/reacquire`，也不允许用最近目标、truth ID 或局部 MOT ID 换绑 `global_track_id`。
5. **跨模块条件未完全闭合**：真实 episode 中仍需要 main/D2/D3/D4 提供稳定 `GlobalTrack`、当前 `Assignment`、相机外参、时间戳、二级 cue 和 D4/D6 消费路径。

## 缺少条件清单

| 条件 | 影响能力 | 归属/来源 |
|---|---|---|
| 连续 RGB/PNG 或 detector bbox stream | main 接 `YoloMotAdapter`、ByteTrack、BoT-SORT、Deep SORT、AprilTag | main/AirSim runtime 或外部 detector |
| 准确相机 K/R/t/dist、时间戳和 frame_id | `projectPoints` 准确性、solvePnP/calibration、跨相机融合 | main/runtime 或标定流程 |
| 2D-3D 匹配点和重投影误差样本 | `solvePnP`、标定质量评估 | 标定/仿真 fixture |
| Remote ID/MAVLink/DDS 真实报文和密钥 | OpenDroneID、MAVLink signing、DDS Security | 通信/身份层 |
| 二级侦察节点真实检测与 pose | cue 反投影/重投影、degrade_to_secondary 真实性 | D4/main/runtime |
| 机动高空侦察云台真实 pointing telemetry | 验证 `cue_position_ned`、`look_at_ned`、pointing error 和 gimbal track error 的真实性 | main/AirSim runtime 或真实云台控制日志 |
| D3/D4/main runtime 消费 D5 advisory evidence | 重复锁定仲裁、主动降级闭环 | D3/D4/main；D5 侧 evidence 字段已可输出 |
| D6/main 统一记录 terminal record/event | terminal lock accuracy、locked mismatch、cue 依赖、handoff 建议评估 | D6/main；D5 侧 geometry/consistency/handoff metadata 已可输出 |

## 下一步优先级

### 真实 AirSim M=5、N=2 检测/几何历史基线（2026-07-11）

以下 `blocks_cv_m5_n2_cooperative_live_20260711` 是 commit-aware gate 和受控跨版本延续实施前的诊断基线，已被本文“当前状态”的 10-seed `8/10` 合同验收取代，不代表当前 T001 合同状态。

证据 `research_modules/airsim_runtime/outputs/blocks_cv_m5_n2_cooperative_live_20260711` 表明 5 主相机和 2 二级相机均有有效 Scene 图像，但 AirSim built-in detection 基本断流：9 帧 episode 的前 8 帧所有相机 count=0，末帧仅部分 episode 的 `Secondary_Recon_1` count=1。full-flow D5 为 32 `reacquire` + 4 `ambiguous` + 0 `locked`，因此本轮不能作为 M-to-N cooperative lock 成功证据。

D5 模块内解析/几何复核通过：记录 bbox 使用正确 `Secondary_Recon_1:0` 外参时对 `T002` 的重投影误差约 0.09 px，并正确关联到既有 `T002`；`mot_history_length=1` 触发 `mot_history_too_short`，没有放宽门控。18-78 px 日志来自 main runtime 的跨相机 fallback：资源自有相机没有 detection 时返回全部 local tracks，使一个二级 bbox 被多个主资源及主相机模型重复消费。该问题不在 D5 owned path，本次未跨模块修改。

main 验收前置条件：

- filter 同时覆盖 spawn actor exact name 和 asset mesh `Quadrotor1*`，并记录每相机实际 filter/radius；
- spawn/filter 与每次 actor/camera pose 更新后增加至少一个丢弃的 Scene/detection warm-up tick；
- `_local_tracks_for_resource` 无本相机检测时必须返回空，不得回退全部相机；二级 bbox 只能结合二级相机外参进入 recon/cross-view registration；
- 先达到每个预期可见相机连续至少 2 帧 detection、同相机重投影误差可审计，再评估 D5 lock 与联盟锁语义。

该历史轮次的 local ID 为 `Secondary_Recon_1:0:det:0001`，保持 camera-local namespace；actor/object truth 只出现在 offline-only metadata 和评分，未进入 online 绑定。当时因 0 lock 未命中合法 cooperative lock 分支；当前状态以 10-seed `8/10` 合同验收为准。

### M 对 N 协同锁定 P1 已闭合（2026-07-11）

专项证据见 `D5_M_TO_N_TERMINAL_MULTIVIEW_REVIEW.md`，覆盖 11 篇主要论文和 8 个开源候选。D5 已完成启用 `k_j>1` 前的联盟锁语义：

- 只读消费 D3 schema v2 的 `coalition_id/version`、`member_role`、`wave_id`、`required_resource_count`、`coordination_mode`、`plan_id/version`、arrival window 和 activation state；
- 把合法联盟成员对同一 `global_track_id` 的多机锁定解释为 `planned_cooperative_lock`，而不是仅凭资源数大于 1 判定 duplicate；
- 继续将联盟/计划版本不一致、缺失合同、resource scope 不符、超额资源、单资源多本地轨迹和 local-to-global 多重绑定标为 duplicate/conflict；
- 未激活 `reserve/retry` 在视觉匹配可锁时输出 `hold`、原始 visual-match evidence 和 D7 PNG blocker；active primary wave-0 与 k=1 保持回归；
- 每个 resource-camera 的 GlobalTrack 投影和 local MOT 仍独立运行，D5 不分配、裁减联盟或改写 `global_track_id`。

仍未闭合的是同步/序贯支持分层、带权 bearing 三角化、相机位姿/时间误差传播、PDOP/可观测度和融合协方差；这些是协同定位 P1/P2，不影响当前联盟锁语义通过。OpenCV 几何和 ByteTrack 本地 MOT 属于成熟默认候选；BoT-SORT 为可插拔升级；ReST、LMGP、多视图 GLMB及 Omni-swarm 相对位姿栈仅作为研究参考。

### P1 已补齐（D5 侧）

| 能力 | 当前证据 | 边界 |
|---|---|---|
| Geometry log fields | `TerminalAssociation.metadata`、`CandidateBreakdown.to_log_dict()` 和 `GeometricAssociationResult.to_log_records()` 输出 projected pixel、bbox center、pixel error、Mahalanobis、gate pass、candidate margin、measurement age、friend conflict、selected pair 与 duplicate-risk advisory。 | D5 只产出字段；main/D6 若要落盘 JSONL/CSV 需在其 owned paths 接入。 |
| `TerminalConsistencySummary` 连续窗口 | `TerminalConsistencyTracker` 按 `resource_id + assigned_global_track_id` 维护窗口；`assignment_version` 仅进入摘要审计。 | advisory summary，不触发降级，不生成分配计划。 |
| AirSim truth ID 在线隔离 | D5 adapter 忽略 truth/global 字段并过滤 actor/truth alias；main builtin detect 使用匿名 camera-local bbox tracker，intercept/fallback local ID 已清理，truth 只进入离线 evaluator/metadata。 | 已由 `outputs/p0_truth_isolation_smoke_20260710` 真实 AirSim 三 case 验收闭合，转为保持回归。 |
| YOLOv8 frame adapter | `YoloMotAdapter.process_frame()` 默认优先 Ultralytics ByteTrack/BoT-SORT，将图像帧或 mock detector 输出转为命名空间化 `LocalVisualTrack`；fallback/native MOT 状态按资源/相机隔离，native history 进一步按 backend/native ID 累计连续 measured hit。空帧、ID/backend 切换、reset 和模型重建不继承稳定证据。缺依赖明确 unavailable，detector 可用时可退回 deterministic IoU。metadata 标明 selection/backend/scope、wall latency、预算比较、observed device、MOT history、camera-local continuity，并提供 offline-only recall/precision/FN/FP 和 stream/episode reset API。 | Results-like 代码回归已完成；真实 AirSim 持续非零检测、部署参数和多 seed IDF1/IDSW 标定仍由 main/runtime/D6 完成。tracker ID 只属于 camera-local namespace。 |
| Multi-seed readiness helper | `summarize_multiseed_calibration_readiness()` 已输出每个 seed 是否具备 local bbox/timestamp、geometry gate log、measurement age、AirSim detect source、YOLO/MOT backend、offline truth、bbox/handoff advisory 和 duplicate/friend conflict evidence 字段。 | D5 只审计字段覆盖；main/D6 仍负责实际跨 seed 落盘、聚合图表和阈值调参。 |
| Secondary coverage/funnel helper | `summarize_secondary_visual_coverage_funnel()` 已输出 `secondary_single_camera_full_view_frame_rate`、`secondary_network_joint_full_view_frame_rate`、每相机/网络每帧可见目标数、覆盖比例均值/最小值、detect 到 multi-support 漏斗计数，以及 `not_all_targets_visible`、`network_union_incomplete`、`no_global_binding`、`reacquire_not_grouped`、`stale_or_missing_recon_cue`、`projection_invalid`、`geometry_gate_rejected`、`stability_window_failed`、`secondary_detect_offline_only` 和 `registered_to_global_track` 断点。 | D5 只做诊断汇总；main/D4/D6 仍负责从 AirSim replay frames 调用、落盘和仲裁。 |
| D4 frame-scoped evidence | `SecondaryFrameAssociationEvidence` 输出与 D4 `TerminalAssociationSummary` 同名的 coverage/full-view、stable/not-registered、cue/gimbal 和 reject 字段，并保留 frame/timestamp/backend/calibration provenance。builder 只选择当前 frame candidate，拒绝混合 frame/timestamp；127 项 D5 测试已覆盖历史 candidate 隔离、cross-view 当前快照、5v5 多相机 fixture、M-to-N 联盟锁语义和真实 M=5/N=2 几何证据回放。 | D5 只产生证据；main/D4 仍需在真实同一 decision tick 消费、做 freshness/threshold version 检查，禁止 episode 末回填。 |
| Detect-to-global-track registration helper | `register_local_visual_tracks_to_global_tracks()` 已输出 `DetectToGlobalTrackCandidate.outcome`、`detect_registration_outcome`、`detect_registration_reject_reasons`、registration candidates、registered observations、即时 cross-view support、稳定 `stable_cross_view_associations` 和 `registered_to_global_track` 成功状态；timestamp、measurement age、covariance/projection covariance、缺绑定、stale binding/cue、`projection_invalid`、geometry gate、稳定窗口失败和 offline-only truth 均有记录。 | D5 helper 已完成，main P1 sweep/D6 bundle 已有消费口径；后续是 AirSim camera pose metadata、多 seed gate、外参和降级 case 校准。 |
| Mobile recon gimbal cue evidence | `ReconImageCue` 与 coverage/cross-view summaries 已携带 `mobile_high_recon`、`mobile_recon_gimbal`、radar/GlobalTrack cue source、NED look-at、云台 metadata 和 pointing/track error；测试证明固定俯视不足时移动云台可改善二级网络联合覆盖证据。 | D5 不运行云台控制，也不使用 actor/truth ID 绑定；main/D6 已能接收报告字段，后续需真实 telemetry 多 seed 趋势分析。 |
| P1 calibration sweep / D6 bundle 输入合同 | main runtime 可运行 P1 D4/D5 calibration sweep，D6 自动生成 records/summary/report bundle。 | D5 不负责 AirSim 启停和报告生成；只维护 evidence DTO、helper、truth 隔离和 `global_track_id` 不变式。 |
| D4 evidence | `CrossViewAssociation`、`DistributedTerminalAssociation.recommended_d4_action`、`duplicate_lock_resource_ids`、`hypothesis_only/hold/ambiguous` 原因和连续帧 `TerminalConsistencySummary` 已可作为 D4/D6 evidence。 | D5 不仲裁、不授权、不创建或换绑 `global_track_id`。 |
| D7 visual PNG 前置证据 | `annotate_visual_png_handoff()` 输出 handoff/prelock、gate pass、blockers、measurement age、LOS rate、bbox stability、range band、timing 和 maneuver metadata；assignment mismatch、friend/duplicate risk、unstable bbox、stale measurement age、missing LOS 会阻断。 | D5 不决定导引律，D7/main 仍需独立 terminal gate。 |

### P0-B 已闭合

| 优先级 | 任务 | 验收结果 |
|---|---|---|
| P0-B | 主动重捕获。 | 已实现 GlobalTrack 预测投影 + bbox/MOT 历史 + search window 的 assigned-track reacquire；predicted 禁锁且不计稳定帧，同一/变化 MOT ID 均需新的 measured 稳定证据，且不改写 `global_track_id`。保持回归；若恢复逻辑退化为最近目标或 truth/local tracker ID 绑定，则作为 P0 backlog 重开。 |
| P0 | Active reacquire 友方声明复检。 | 已闭合并覆盖同一/新 MOT ID × verified/stale/unverified/spoof-suspected；冲突输出 `hold`、非空 `friend_conflict_state` 和可审计 reason，不改写 `global_track_id`。 |
| P0 | Detection category/truth 隔离。 | 已闭合并覆盖 generic/actor/object name 不影响 category/cost/binding，detector class-id names 映射仍有效，既有 truth isolation 保持。 |
| P0-B | 时序一致性和稳定窗口。 | 已加强 candidate margin、stable window、bbox/MOT history、stale/OOSM 和保守 hold/ambiguous 阻断；`TerminalConsistencyTracker` stable 判定不再把任意正 margin 视为稳定。保持回归；若 stable window、margin 或 stale/OOSM 阻断缺失，则作为 P0 backlog 重开。 |
| P0-B | 相机校准健康监测。 | 已输出 projection valid、reprojection error、camera pose source/trust、calibration health、drift warning、registration health counts 和误差摘要，供 D6/main 直接消费。保持回归；若缺失 reprojection error、pose source、calibration health 或 drift warning，则作为 P0 backlog 重开。 |

### 剩余 P1/P2/P3

| 优先级 | 任务 | 验收建议 |
|---|---|---|
| P1 | M5N2 第二 primary。 | 继续针对 `d5_not_locked`、detection acquisition timeout、bbox 稳定和连续 measured lock 做多 seed 标定，目标至少 8/10；不要求同时到达，不降低安全门控。 |
| P1 | 真实几何 drift。 | 以现有 multi-camera registration 为基线，对真实 AirSim/replay 外参漂移、时间同步、遮挡/交叉和错误绑定做多 seed 压力测试；不以完整在线 PnP 为前置条件。 |
| P1 | detect/YOLO/MOT 多 seed。 | 先解决 bbox 定义/尺度/时间对齐、edge margin、dropout 和 30/50 m 召回；候选达到 precision/recall、continuity、IDSW、fallback 和 P95 门槛后运行至少 10 seeds confirmation。 |
| P1 | 二级同 tick freshness。 | D5 单帧 DTO/字段映射已完成；main/D4 需在同一 decision tick 消费并记录 threshold version、stale rejection、覆盖状态和状态迁移，禁止 episode 聚合回填。 |
| P2 | BoT-SORT/Deep SORT/ReID。 | 在连续真实图像和算力预算下评估 IDF1/IDSW；未达标时保持几何门控 + ByteTrack/schema adapter 默认基线。 |
| P2 | 真实身份来源 `IdentityClaim` adapter。 | 接入 OpenDroneID Core、MAVLink signing、DDS Security 或 AprilTag；未知/stale 不升级目标，也不绕过几何与 assignment 门。 |
| P2 | 完整在线 PnP/标定链。 | 接入真实 2D-3D 对应、PnP RANSAC、畸变校正和在线外参更新；与 P1 drift 统计分开验收。 |
| P3 | IBVS replay/对照。 | D5 只评估 lost/reacquire 变化，不实现视觉伺服控制器、不重新分配、不授权、不换绑 `global_track_id`。 |
| P3 | ROS 2 `tf2/message_filters`。 | 仅在项目进入 ROS 2 runtime 或 bag replay 后实施，保持带戳 frame tree 与 D5 `CameraModel` 一致性。 |

## 关键代码依据

- `research_modules/d5_terminal_association/src/d5_terminal_association/models.py`
- `research_modules/d5_terminal_association/src/d5_terminal_association/geometry.py`
- `research_modules/d5_terminal_association/src/d5_terminal_association/associator.py`
- `research_modules/d5_terminal_association/src/d5_terminal_association/airsim_cv_adapter.py`
- `research_modules/d5_terminal_association/src/d5_terminal_association/airsim_geometry.py`
- `research_modules/d5_terminal_association/src/d5_terminal_association/yolo_mot_adapter.py`
- `research_modules/d5_terminal_association/src/d5_terminal_association/identity.py`
- `research_modules/d5_terminal_association/src/d5_terminal_association/observation_bus.py`
- `research_modules/d5_terminal_association/src/d5_terminal_association/terminal_cross_view_fusion.py`
- `research_modules/d5_terminal_association/src/d5_terminal_association/cross_view_registration.py`
- `research_modules/d5_terminal_association/src/d5_terminal_association/consistency.py`
- `research_modules/d5_terminal_association/src/d5_terminal_association/visual_handoff.py`
- `research_modules/d5_terminal_association/tests/test_terminal_association.py`
- `research_modules/d5_terminal_association/tests/test_airsim_cv_5v5_evidence.py`
- `research_modules/d5_terminal_association/tests/test_airsim_cv_2v2_secondary_plan.py`
- `research_modules/d5_terminal_association/tests/test_geometric_registration_validation.py`
- `research_modules/d5_terminal_association/tests/test_terminal_observation_bus.py`
- `research_modules/d5_terminal_association/tests/test_distributed_cross_view_fusion.py`
- `research_modules/d5_terminal_association/tests/test_cross_view_registration.py`
- `research_modules/d5_terminal_association/tests/test_terminal_consistency.py`
- `research_modules/d5_terminal_association/tests/test_visual_handoff.py`
- `research_modules/d5_terminal_association/tests/test_yolo_mot_adapter.py`

## 2026-07-12 P1 M5N2 鲁棒性补齐审计

本轮由 D5 owner 在模块边界内补齐 replay 与保守证据，模块测试从 `161 passed` 增至 `168 passed`：

| P1 项目 | 当前状态 | 本轮证据 | 仍开放条件 |
|---|---|---|---|
| 锁定后 1-5 帧缺失/恢复 | 模块 replay 已闭合；真实 AirSim 待验收。 | 1-2 个 10 Hz 缺失帧持续 `reacquire`；第 3-5 帧超过 0.25 s 后显式 `terminal_visual_evidence_expired`，恢复后两次 measured 支持才重新 lock。D5 不实现 coast/KF/控制。 | main 用固定注入时刻和相同 seeds 运行真实 detect dropout；wrong binding、truth use 和 ID rewrite 必须为 0。 |
| 相机历史与 local MOT ID 隔离 | 已闭合。 | 历史键增加 camera scope；不同相机相同 local ID 不共享 loss/stability；同相机 MOT ID 变化必须重新确认。 | runtime 调用应显式传 `camera_id`；adapter metadata 仅作兼容来源。 |
| 旧 plan 拒绝 | TerminalAssociator 模块侧已闭合。 | 同一 resource/plan lineage 的下降 `plan_version` 输出 `hold/stale_plan_version_rejected`，未授权或 track-version 不匹配输入不更新 watermark。 | D4/D3 仍需在真实 episode 维持 owner/epoch/lease 的全局版本合同。 |
| 同相机交叉与跨相机部分重叠 | 合成 replay 已闭合；真实场景开放。 | GlobalTrack 投影+马氏门+Hungarian 在同相机交叉后保持既有全局绑定；R1 看 G1/G2/G3、R2 看 G2/G3/G4 时，仅 G2/G3 形成双视角支持。 | 真实 M5N2 crossing/occlusion 多 seed、检测漏帧和外观相似场景仍需校准。 |
| 外参漂移与时间偏差 | fail-closed replay 已闭合；标定开放。 | 注入 4 m 外参平移或 0.5 s 高动态时间偏差时 geometry gate 拒绝，不借助 truth ID 恢复绑定。 | 真实每相机 K/R/t、曝光/arrival/attitude timestamp、漂移量级与门限需 main/runtime 提供。 |
| YOLO/native MOT | 保持 deferred。 | 本轮不改变 detect-first 默认路径，不把现有 `best.pt` 或 fallback tracker 解释为已完成标定。 | 非零持续无人机 detection、native tracker ID、CPU/GPU latency、IDSW/IDF1 和失败回退多 seed 验收。 |

因此 D5 当前无新增 P0。模块内 dropout、相机作用域、stale plan 和扰动 replay 支撑已补齐；系统级 P1 集中在 M5N2 第二 primary、真实几何 drift、detect/YOLO/MOT 多 seed 和二级同 tick freshness。真实身份源保持 P2。

### 版本化 summary 缺口状态

“D5 确定性 visual robustness 没有独立可写盘 summary、D6 只能读取通用 readiness”这一模块 P1 缺口已关闭。新增 `d5.p1_visual_robustness_summary.v1` API/CLI，覆盖 10 个确定性 case，并在顶层和 D6 可保留的 `metadata` 中记录 case/pass/reject、在线 truth 使用和全局 ID 改写计数。JSON 重复生成字节一致，当前 D6 `--d5-summary` 已实际加载成功，source manifest 标记 available 且 schema/version/evidence path 正确。

当前基线：`case_count=10`、`pass_count=10`、`failed_case_count=0`、`reject_count=24`、`online_truth_use_count=0`、`global_track_id_rewrite_count=0`，D5 全量 `171 passed`。该项只关闭离线 summary 生产和消费合同；真实 M5N2 paired、多 seed dropout、持续 detect/native MOT、外参/时间同步和物理结果仍为系统级 P1。
