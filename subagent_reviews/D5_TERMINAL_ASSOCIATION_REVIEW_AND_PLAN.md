# D5 末端视觉配准与协同身份认证综述及子方案

## 2026-07-26 G1/A3 bundle 复核

D5 已对齐 main `d59352b` 的学习 scope 准入合同。G1 旧 v3 bundle 仍只允许开发和 shadow，
`require_g1_assist_eligible=True` 不接受通过修改旧 manifest 得到的正向布尔值。主审进一步确认
裸 `TrackletG1AdmissionReport` 不能证明 held-out、paired shadow 和 D6 审计实物存在。D5 采用
保守关闭方案：production writer 不接收 report，公开 loader/runtime 不执行 v4；严格 parser
仅通过私有 fixture 回归。A3 同样禁止裸 report 写入和正向运行加载。

当前 G1 manifest/weights 仍是 `c4284b...674` / `99fa4428...d4cd`。held-out 文件/内容为
`765d39a...20a` / `bada1803...67a`，paired 文件/内容为 `cc960206...f23` /
`53bdc658...7a0`。paired 门已通过，但权限状态仍是 `pending_d6_external_audit`；现有 D6 审计
生成于 2026-07-21，没有绑定 2026-07-25 paired 结果和当前实现。当前 G1 实现摘要为
`ff8c744e...a1b7`，旧 bundle 返回 `bundle_implementation_runtime_mismatch`。

A3 当前实现 SHA 为 `e7db827f...3b4`，旧 manifest/weights 为 `9c0cb50...ad4` /
`829d0166...77b`，严格 assist 同样因实现不一致拒绝。行为克隆报告 `8a40aeb8...81e` 明确
`assist=false`，没有 20 个未见 seed 的正式 paired non-degradation。

因此，D5 已关闭裸 report 自声明和权限字段类型强转的代码缺口；独立证据装配器仍是 P1。G1
私有 fixture 负例覆盖 missing、tampered、cross-model、cross-dataset 和 D6-fail，公开 runtime
对结构完整 fixture 仍失败关闭。定向测试 `47 passed in 2.32s`，D5 全量
`562 passed in 99.88s`。旧 manifest、权重、校准参数、`global_track_id` 和在线 truth 边界均
未修改。

## 2026-07-25 冻结图模型复核

D5 重新选择当前工作树可严格加载的 development bundle，并把 manifest、weights 和
`SHA256SUMS` 的哈希写入稳定引用。模型 manifest 为 `c4284b...674`，权重为
`99fa4428...d4cd`。新的 held-out 和 paired shadow 均使用该组哈希，覆盖 seed `1000-1019`、
45 个场景规模单元和 900 个匿名图帧。旧 `4f5e8cee...1e50` 权重报告继续作为历史证据，不再代表
当前冻结模型。

成对评估保持候选图、候选边、相机局部编号和外生输入完全相同。图模型只输出边属于同一目标的
概率；受约束聚类仍禁止同相机两条轨迹进入同簇，最终中心绑定仍由既有一对一 Hungarian 完成。
模型没有创建、改写或换绑 `global_track_id`。在线输入保持匿名，truth 只在两臂完成推理和聚类后
用于离线评分。

名义数据中，候选召回为 1.0，模型边/簇 F1 均为 1.0，P50/P95 为
`0.983052/1.219528 ms`。最高单特征 AUC 为 `0.997340`。遮挡重现代理使模型边/簇 F1 降至
`0.563264/0.572845`，独立 bbox 尺度扰动降至 `0.893470/0.949131`，说明当前合成数据仍过易，
模型对低置信度重现和尺度变化不够稳健。九类模型异常的规则回退率为 1.0。

本轮只关闭模型哈希与 20-seed 证据不一致的 P1 子项。D6 独立复核、重新执行候选门的独立困难集、
真实匿名多相机回放和权重制品化仍开放。bundle 晋级字段未修改，G1、assist、authority 继续关闭，
主动视觉 PPO 未启动。

最终 D5 回归为 `552 passed in 114.25s`。main 在 D4 因果通信修正后复跑统一
module stack，结果为 `66 passed, 1 warning in 10.17s`。唯一警告为既有 Matplotlib
三维绘图环境提示。D5 自测和跨模块合同均为零失败；模型准入仍因数据与外部复核缺口保持关闭。

## 2026-07-23 clean 4ac3bb2 seed 1000 profiler 复核

D5 使用 nominal 200v200 seed 1000 的冻结匿名在线制品复核长窗口 P1。短/长日志分别覆盖 25/114 次调用，长日志包含 723 个相机批次、2479 个检测/图节点和 2400 个 binding。输入只来自 online bus，长日志 SHA-256 为 `c1dda852...6f77a`，truth source 未加载。

热态 cProfile 将 114 帧 `process()` 累计从 `2.320 s` 定位到 `adapt_batches=1.428 s`、transport truth 隔离审计 `0.400 s`、匿名 payload 审计 `0.358 s`、历史 gauge `0.0544 s` 和 binding `0.0578 s` 等局部项。边界修复前候选对应累计为 `1.987/1.122/0.239/0.162/0.00288/0.0312 s`。该 profile 的 `sparse_tracklet_graph.py` 为 `dc6bcd81...b4c4c`；实现只引入增量历史账本、8192 项匿名 ID 正则 LRU、精确内建叶子审计快路径和 singleton cluster 投影行复用。

固定诊断确认 723 次 gauge 刷新避免扫描 91,871 个 tracker 引用，2289 个 singleton 行复用；79 个多节点 cluster 仍执行旧有限性聚合，32 个无 binding matrix 输出仍物化完整结果。两轮各 7 次描述性 A/B 的长日志中位值均值为 `1.149362→0.929495 s`，约下降 `19.13%`；墙钟不设为测试硬门。

最终源码增加 singleton 有限行零符号规范化，当前 `sparse_tracklet_graph.py` 为 `0e8a5880...19d5b`。机器 JSON 的 `post_boundary_fix_verification` 重新消费同一短/长日志；逐帧核心、最终 binding、v2 操作数和冻结 v1 operation-equivalence 哈希与原记录一致。长序列业务、binding 和 v1 操作面哈希为 `d9629adc...35ca0`、`996763e3...24b6`、`c8a19ee8...affc`；online truth use 与 `global_track_id` mutation 均为 0。几何门、身份门、友方冲突、唯一绑定和输出载荷逐条保持。

本轮关闭冻结日志范围内的 profiler 归因和四个局部重复工作子项，不关闭完整集成长窗口 P1。原 10 秒集成 P50/P95/max 约 `11.497/15.969/18.632 ms`、相对短窗约 `2.556x`；当前源码没有完整系统复跑。后续仍由 main/D6 预注册检测数、活跃相机数、中心候选数和时长的正交多 seed 操作数/耗时联合准入。本轮不改变 AirSim、M-to-N、G1/assist/authority 或 D7 权限。

2026-07-23 main 对最终源码完成 D5 全量回归，权威结果为 `551 passed in 100.83s`，接受阈值为零失败。`550 passed in 102.41s` 仅为 boundary-fix 前历史值。

## 2026-07-22 相机重叠索引专项复核

seed 42000 的函数剖析把 116 次相机重叠索引累计定位为约 `0.357 s`，旧实现约 `0.248 s` 用于探测没有相机的三维网格位置。当前实现保留已建立的占用桶只读索引，直接枚举占用桶对并检查与旧实现相同的切比雪夫搜索半径。视锥描述、时间窗、包围盒相交、预算和候选排序未变。

clean `f80b5bd` 三 seed 10 秒冻结重放的配对中位耗时为 `1.551→1.313 s`、`1.501→1.262 s`、`1.406→1.149 s`，三 seed 中位值均值下降 `16.45%`。逐帧核心哈希包含相机索引、几何拒绝和 binding；三个 seed 的核心、最终 binding 和操作数哈希均与各自原记录一致。在线真值、中心 ID 改写、降帧、降候选、门限和 D7 gate 变化为 0，主动视觉命令哈希保持。

本轮关闭图候选阶段的空网格重复探测子项。它没有改变 G1、assist、authority 或规则回退状态，也不证明长时线性、AirSim 实时性或硬件实时性。D5 超线性规模成本和 D6 正式联合准入继续保持 P1。

定向回归为 `52 passed`，D5 全量回归为 `545 passed in 129.59s`。

## 2026-07-22 f80b5bd 三种子最终复核

main 使用 clean 参考提交 `8f86192` 和 clean 候选提交 `f80b5bd`，完成 nominal 200v200、10.0 秒、seeds `42000-42002` 的同配置重放和逐条语义审计。三个候选 episode 均保持 finite，online truth use=0；D1/D2/D3/D5/D7 最终数量与参考运行相同。

D5 终端关联累计耗时三 seed 均值由 `2.545876 s` 降至 `1.974446 s`，约下降 `22.45%`。主动视觉由 `4.174315 s` 变为 `4.183797 s`，约增加 `0.23%`，基本持平。每 seed 投影 DTO 缓存命中/未命中保持 `68/48`、`71/48`、`70/48`，最终 binding 保持 `22/29/28`。

视觉 binding 和主动视觉 payload 逐条语义相同。审计按 D3 plan occurrence/version 归一化独立运行产生的不透明 `plan_id`，归一化前验证 ACK 原始来源载荷 SHA-256；owner/version/coalition/`global_track_id`/command 等业务字段均保留。单次 `process()` 只在同量测时刻相机批内复用只读 center prediction，不跨调用、不减少候选、不改变中心 ID 所有权。

本轮关闭“当前源码三种子完整集成复跑”与“逐条业务等价”子项。文档同步后的 D5 全量回归为 `544 passed in 163.09s`。累计阶段耗时下降不等于单次复杂度线性，既有短长归一化结果仍超出线性门。D5 长时超线性成本、D6 正式操作数/耗时联合准入、AirSim 和硬件实时性继续保持 P1。

## 2026-07-22 中心预测工作区复核

seed 42000 长日志的固定大小快照记录 33315 次局部匹配比较、499505 个中心投影单元和 472288 个 binding 单元。函数级剖析表明三者累计耗时约为 `0.098/0.706/0.057 s`；计数最大的局部比较并不是主热点。D5 因此保留 tracker 和 binding 语义，只优化中心投影阶段按相机重复抽取中心轨迹数组、重复预测相同量测时刻状态的工作。

当前实现每次矩阵构建物化一次中心轨迹数组，并在函数内缓存只读的同时间戳预测。短/长相机时刻组为 `76/715`，唯一时刻为 `23/116`。工作区不跨调用，完整投影和 binding 单元继续执行。五轮交替旧/新重放的短/长平均单次成本中位数为 `10.879 -> 7.610 ms` 和 `26.078 -> 19.145 ms`；长路径下降 `26.6%`。独立五次候选为 `8.522/20.163 ms`、增长 `2.366x`。

短/长逐帧业务、最终 binding 和操作数哈希与冻结记录一致；online truth use 和 `global_track_id` mutation 为 0。当前源码此前 D5 全量 `544 passed in 155.17s`。配对归一化增长没有稳定下降；当前源码三种子系统复跑已由上节关闭，超线性规模成本、D6 正式操作数聚合和性能准入继续列 P1。本轮没有 AirSim 或在线学习权限变化。

## 2026-07-22 clean 三种子集成复核

提交 `8f86192` 的统一三维 200v200 候选完成 10 秒 seeds `42000-42002`。D5 终端关联阶段耗时为 `2.4496/2.6355/2.5526 s`，调用次数为 `116/119/118`；三种子均值相对旧 clean 候选从 `2.6985 s` 降至 `2.5459 s`，下降 `5.7%`。该比较属于完整系统墙钟结果，不能把全部差值归因于 D5。

seed 42000 的旁路快照记录 2493 个图节点和 33315 次局部匹配对比较。短长序列归一化单次成本增长从 `2.696x` 降至 `2.423x`，性能有所收敛但仍为超线性 P1。在线 truth 使用和 `global_track_id` 改写均为 0。D6 三种子均为 clean descriptive calibration；正式统计准入和 AirSim/硬件实时性仍未建立。

本轮关闭“性能快照尚未接入 main”的 P1 子项。D6 已形成三种子 clean descriptive 阶段汇总，但尚未聚合 D5 操作数，该项继续保持 P1。后续工作集中在按检测规模、活跃相机数、中心候选数和时长拆分增长来源，并保持几何、友方、身份、版本和唯一性门控。既有五次冻结日志 benchmark 保留为独立单模块证据，不与本节集成结果混算。

## 2026-07-22 三维长短序列操作数复核

新增诊断把一次在线处理拆成相机批次适配、局部轨迹历史、稀疏图、中心投影、聚类绑定和匈牙利求解。诊断器只累计固定数量的整数和峰值，不收集逐帧样本，也不写入关联业务结果。这样可以在不改变 DTO 和时序的条件下比较不同长度的冻结在线日志。

2.15 秒日志包含 23 次调用、85 个检测节点；9.95 秒日志包含 116 次调用、2493 个检测节点。五次重放的中位总耗时为 `0.213419/2.289464 s`，平均单次成本为 `9.165/19.564 ms`。长序列的每调用检测节点增长 `5.815x`，投影矩阵和绑定矩阵单元增长 `7.274x/6.980x`。候选边进入门控只增长 `2.495x`，图构建和评分仍各执行每帧一次。局部匹配对比较增长较大，但剖析未显示其单独主导总耗时。

活跃局部历史峰值由 81 增至 416，仍受丢帧生命周期清理；相机流峰值由 63 增至 180。已接收时间戳审计集合由 76 增至 715，该集合承担 episode 内精确重复/OOSM 拒绝。当前不能仅为降低内存而截断它，后续应由 main 明确最长 episode 和重复检测窗口。

相机批次内部原先对每个检测重复构造和校验同一几何模板。现在首检测执行完整验证，后续检测用全部已消费元数据字段的内容签名复用；任一内外参、旋转或协方差变化都会拒绝复用。剖析中模板准备耗时降低约 47.4%，最终 116 帧的业务输出完全一致。一次向量化局部匹配试验虽然保持哈希一致，但运行更慢，已撤销。

下一步由 main/D6 将快照作为 episode 性能旁路消费，避免写入 `TerminalAssociation`。D5 后续只在固定输入和业务哈希等价的条件下继续优化投影/绑定矩阵；不得降低几何、友方、身份、版本和唯一性门控。

## 2026-07-22 三维长时性能复核

D5 对 main clean 的 2.2 秒和 10 秒阶段证据完成剖析，并用固定 10 秒在线日志复现基线。主动视觉单次成本保持稳定；终端关联增长与每帧视觉候选均值由 `3.696` 增至 `21.491` 一致，未发现 tracklet 历史或候选图随时间无界增长。内部热点为中心投影矩阵重复计算、同一 D2 快照重复 DTO 物化和快照内线性查找。

优化后终端日志重放由 `4.133 s` 降至 `2.776 s`，主动视觉由 `37.431 ms/轮` 降至 `25.918 ms/轮`。116/116 终端记录一致，绑定状态、决策哈希、在线 truth=0 和 `global_track_id` 不改写均保持。规则路径继续默认，可选图模型和主动视觉学习接口保留但未授权。

发布载荷不是 D5 内部阶段增长根因。10 秒 active vision 为 93 条、8.273 MB，terminal association 为 116 条、0.779 MB；这部分成本落在 main 发布总线和日志写出边界。本轮不建议在 D5 内通过降频或删减证据改变消息语义。

## 2026-07-22 同图配对影子复核

D5 已用当前最终源码完成 seed `1000-1019`、900 帧和 45 个场景规模单元的 paired shadow v2。
冻结 held-out corpus、held-out 评估报告和开发模型 bundle 通过显式路径及带外 SHA 绑定。每帧只构造
一个只读图对象，规则评分、冻结模型评分和双方受约束聚类使用同一图；各阶段图数组与候选边 SHA
复核为 900/900 一致。truth 只在两臂推理和聚类后由 evaluator 评分，不进入在线特征或概率路径。

冻结模型在 74,024 条候选边上取得边级和簇对级 precision/recall/F1 全 1.0，错误合并和同目标拆分
均为 0。确定性规则的边 F1 为 0.367980、错误合并率 0.774516；簇对 F1 为 0.239234、错误合并率
0.762462。候选召回为 1.0，模型 CPU 评分 P95 为 3.292009 ms。45/45 cell 和 20/20 seed 均满足
当前非退化门。该结论仅适用于同一冻结合成候选图。

补充特征审查否定了 `shared_global_track_count` 的直接解释：该特征在全部边上恒为 0，与标签互信息
为 0 bit，取值 1 的性能无法评价。边界框对数尺度差、尺度变化率差和角速度差的单特征最佳方向
AUC 为 0.997319、0.997340 和 0.997340；同目标样本的尺度率差与角速度差全部为 0。这些线索使
合成保留集偏易，满分不能外推为真实相机、真实目标外观、真实时钟/外参漂移或 M 对 N 联盟条件下
的泛化。统计不是冻结模型的因果特征归因。

v2 report/lineage SHA 为 `b1528af8...40e1` / `03f92ad1...4c1d`，证据状态为
`authoritative`。首次输出保留为 `superseded_preserved`。本轮没有运行 AirSim，没有修改在线关联
默认值，也没有开放 G1、辅助或控制权限。下一步由 D6 独立审计 v2，再建设不同生成机制的困难集、
`shared_global_track_count=1` 分层和代表性真实多相机回放。

当前最终源码的 paired-shadow 专项为 `5 passed in 3.21s`，D5 全量为
`534 passed in 141.66s`。下列 2026-07-21 及更早章节是阶段复核记录，其中未完成表述不覆盖本节
v2 当前状态。

## 2026-07-21 候选图预算复核（历史，已由 v2 更新）

旧 clean supplemental 的 candidate recall 为 `11409/16698=0.683255`。逐级计数显示，370,211 个
可能跨相机 pair 中只有 21 个被几何门拒绝，最终 8 邻居预算却删除 125,158 条门后边。该结果已
定位到双层候选预算不一致，不需要放宽任何几何、协方差、身份、版本或友方门。

D5 将最终默认预算与前置预算统一为 24。候选继续按几何质量与匿名 key 确定性排序，每节点最大度数
为 24，边数不超过 `12V`。seed 5 四相机困难帧回归保留 15/15 个同目标 pair，候选召回 1.0；小
cap 回归确认图仍严格有界。D5 全量 `529 passed in 122.96s`。

当前完成范围仅为代码、诊断和软件回归。main 尚未在 clean commit 上重建 4,500 帧语料、重生成
组合视图或重训模型。旧 clean 数据准入只能作为历史记录；held-out、paired shadow 和 G1/assist/
authority 结论不变，中心 `global_track_id` 所有权不变。

## 2026-07-21 保留 seed 独立评估复核（历史管线阶段）

D5 已实现专用 `held_out_evaluation` 数据合同。正式目录只接受 seed `1000-1019`，每个 seed 必须
覆盖 45 个冻结场景规模单元。producer 不使用训练 split registry，不复制或回写 formal/supplemental，
并在 sibling 临时目录完成逐制品哈希、标签和 lineage 校验后原子发布。训练 seed、cell 缺失、
同相机边、未标注边、候选门变化、hash 篡改和输出重叠均失败关闭。

development bundle evaluator 使用模型包既有 validation 温度和阈值，不提供 held-out 调参或训练
入口。整体及逐 cell 指标与实测延迟写入机器 JSON 和中文 Markdown。权重、模型配置和 corpus 在
评估前后保持只读。当前 1 seed×2 cell smoke 已完成，专项 `17 passed`、D5 全量 `527 passed`；
完整 900 帧没有生成，main 正在执行的 clean 30-epoch 训练不属于本次完成证据。

后续由 main 在训练提交和 clean bundle 固定后运行 900 帧生产与全样本评估，再用相同保留 seed
执行规则/模型 paired shadow。两项完成前，D5 图模型保持 development/shadow-only，G1、assist、
在线身份和相机控制权限均关闭。D5 不创建、改写或换绑 `global_track_id`。

## 2026-07-21 Composite 内部训练入口复核（历史预检）

D5 已把 clean composite corpus 接入现有原生 PyTorch 图模型管线。入口只读复载正式完整帧和补充
语料，并绑定 view、admission 与共享 seed registry；`60/20/20`、45 cell、标签和同相机互斥均为
强制门。实际 preflight 为 4,972 帧、245,040 边，未进入训练分支。

未来 clean 全量训练会附带 D6-facing 独立模型报告。报告的 test/cell 指标和延迟全部来自实际训练
评估，权重及配置哈希来自 bundle；cell 样本数按已标注候选边统计。内部 test 报告不等于保留 seed
或 paired shadow 证据，也不授予 G1/assist/authority。本轮专项 `12 passed in 1.05s`，D5 全量
`510 passed in 121.82s`；正式模型、`.pt`、保留 seed 和 paired shadow 仍未完成。

## 2026-07-21 Tracklet 困难样本复核（历史首轮语料）

正式语料的 99 条未标注边已逐条复核。冻结导出缺少可同时绑定 episode、匿名 tracklet、量测时刻和
source observation 的离线来源链，可靠补标为 0；99 条边继续 unavailable，正式源未改动。D5 随后
使用独立 seed 和物理投影生成 4,500 个困难样本图帧，得到 245,032 条通过既有几何门的候选边，
正/负/未标注为 `57292/187740/0`。truth 只存在于图构建后的独立 evaluator lineage。

formal + supplemental detached 视图共 4,972 帧和 245,040 条边，现有数据量、标签完整性、候选
召回分母与场景双类覆盖门全部通过。main 又基于 clean commit
`79b2550ce2ef407c7cfcc653ce04a80fe2226c06` 同配置复生，supplemental source dirty=false，数据支持和
`training_readiness` 均 pass，原 provenance blocker 关闭。clean supplemental manifest/view SHA 为
`4b9875fee86b5c425f683a6da23e6af1308bcf2383d3633d4fd6207fe2f25a32` 和
`11e8acbdbe268574ead402f2be5c9aa8e3459a7e4147a18e0570df3402892415`。

该结果只闭合 producer、来源和训练数据支持。没有训练模型、没有 `.pt`、没有开放 G1 或 assist；
保留 seed 独立评估和 shadow 仍待完成。clean 制品严格复载通过，专项 `12 passed in 5.40s`；此前
全量回归为 `498 passed in 124.90s`。

## 2026-07-21 Supplemental BC 全样本准入复核

D5 新增只读 fail-closed 审计并对 clean supplemental 完整 100 episode/1200 sample 运行。接受阈值为
canonical `60/20/20` episode 与 `720/240/240` sample、302/302 checksummed 文件、1200/1200 有限
35 维候选特征、版本/身份一致及 truth/reserved/dirty/违规为 0；实测全部通过，候选特征行 7800，
规则示范 1200/1200 唯一。证据 JSON/中文报告内容 SHA 为
`a11b65596a4c416deba6d0cb35dcc0c32342a5bae0481291d43e8de0e26550dd`，来源 commit 为
`13e37286d2996a227924bb1a8e2766e52116a534`，dataset/view/config/registry/summary 六项 SHA 与下节
clean evidence 完全一致。supplemental 树保持 308 files/约 2.2 MiB；正式 900-episode 树保持
43973 files、SHA256 `8ffbe5cf044d121163c8acc3dce1bbd54e14bb6b211b8e1cf440f24c93294fca`。

该证据关闭 supplemental BC full-sample audit，作为 D6 跨模块学习准入的前置证据；不代表 D6 已
准入或模型已训练。`400/400/400` 仍只属 synthetic 故障注入，四类离线 label 仍 unavailable，真实
runtime ACK/outcome、reward/counterfactual/causal、paired shadow 保持开放。PPO/assist/authority=false，
rule fallback required=true；本轮未运行 AirSim、未生成 `.pt`、未修改两棵数据树。
新增专项 `4 passed in 35.72s`，D5 全量 `486 passed in 119.63s`，接受阈值为零失败。

## 2026-07-21 B1b2 clean evidence 复核

main 已在 detached clean worktree `13e37286d2996a227924bb1a8e2766e52116a534` 生成实际 100/800/1200 supplemental 制品与 canonical `60/20/20`、`720/240/240` 视图；dataset/view/config/training-registry/shared-registry/summary-content SHA 依次为 `0c474ee1b0bab34a46c2ebce328761983cf2ecc757da30c2d3d2e03a06cd1acf`、`0ab1a4a6bdd439f6c8a74df5059de3c4950791fba35a1b9514942e83779f72a8`、`e93ca6310338be5db4539fac195f5257e28d16a64b78b1a0351bf6aeca01fcee`、`2ab928a476a4430b99326f245222f058bc5be5025158134ba89b01b3dec7815f`、`68608d29d1f733beea87f1faf06464fededb68a9c2972c51c10cd4c2160f032f`、`0577c73810413ced6277e679477422f467cb2db094f1d376e39e4cbb2a3abd65`，正式树前后 SHA 同为 `8ffbe5cf044d121163c8acc3dce1bbd54e14bb6b211b8e1cf440f24c93294fca`，truth/reserved/dirty/audit 均为 0。clean producer/canonical 与后续 supplemental BC 全样本证据均已关闭；`400/400/400` 只属 synthetic 故障覆盖，四类 label 均 `0/1200 available`，PPO/assist/authority 仍关闭，下一步为 main/D6 跨模块准入审计，本次无训练或 AirSim。

## 2026-07-21 Supplemental curriculum B1b2 复核

D5 已具备独立 100-seed synthetic curriculum 的原子 producer、canonical `60/20/20`、严格审计和
CLI。实现复用 B1b1 builder 与现有 episode staging/finalize/lazy/canonical/readiness API；输出目录
必须不存在，全部校验在 sibling 临时目录完成后才发布。中心 `global_track_id` 必须由调用方显式
提供，truth-like 引用、seed 漏/多、registry mismatch、保留 seed、版本或 availability 异常均失败
关闭。training/shared registry 的父目录分别作为受保护 source root；output 和 tracked 报告不得等于
或位于任一根下，正式嵌套布局和 registry 分离布局均在目录创建前失败关闭。

tmp_path 验收得到 100 episode、800 segment、1200 sample；canonical sample 为 `720/240/240`。
四 intent、两 FOV、interceptor/recon 和三 ACK 已覆盖。ACK 各 400 仅是确定性故障注入，不是 runtime
分布或收益。四类 offline label 均 unavailable，PPO/assist/authority 均 false；dirty 生成状态为
`fail_closed_dirty_source`。Markdown 报告使用中文标题、说明和约束，并明确每 seed `4/4/4` 不是实际
运行分布。新增专项 `15 passed in 71.87s`，D5 全量 `482 passed in 83.05s`。

上述 tmp_path 结果是软件阶段历史验收；后续 main 已在 clean revision `13e3728` 执行 CLI、归档实际
SHA，并关闭 clean supplemental producer/canonical evidence。正式 900 episode 未修改，也未运行
AirSim 或训练。supplemental BC 全样本审计已由本文顶部证据关闭；开放项只剩 main/D6 跨模块准入、
真实 ACK/outcome、reward/counterfactual/causal、
paired shadow 及 PPO/assist/authority 准入。

## 2026-07-21 主动视觉宽视场门复核

规则策略原先可在单帧投影满足阈值时立即进入窄视场。当前实现增加相机局部连续性门，状态键由相机、
中心目标、计划版本和联盟版本组成。默认 3 个独立新帧通过新鲜度、可见、遮挡、关联置信、视场、
版本、通信和友方冲突检查后，才允许继续检查投影不确定度并选择 `ZOOM`。稳定窗口内仍观察当前中心
分配目标，但保持 `WIDE`。

计划、联盟或目标改变会建立新状态键。时间回退、旧投影、低置信、近邻歧义、通信异常、友方保留
冲突和云台忙会清空计数。重捕获和扫描选择宽视场；云台忙保持当前 FOV，恢复后从宽视场窗口重计。
相机状态相互隔离，重复调用同一帧不会增加计数。`N=1` 是明确的旧语义兼容选项，默认仍采用 3 帧
保守值。

阶段 A 当时只完成规则状态机和模块测试。当前 snapshot 没有 runtime ACK 输入，因此没有把 camera
feedback 或模拟状态解释为已执行确认；其后 B1b2 已完成 `13e3728` clean producer/canonical evidence，
但真实 applied/rejected/missing ACK/outcome、reward/counterfactual/causal 和 paired shadow 仍缺失。
主动视觉模型维持 development
shadow-only，assist/PPO 均关闭；阶段 A/B1b2 均没有新增 AirSim 或训练结果。
旧 v5 bundle 绑定修改前实现哈希，严格 loader 会失败关闭，不能直接用于新规则。定向组合测试为
`47 passed`，D5 全量为 `437 passed in 10.28s`。

## 2026-07-21 canonical seed 视图复核

D5 已把正式 tracklet graph 与 active-vision episode 映射到 main 共享的数值 seed 分桶。实现先走
原 strict loader，再校验 training/shared registry 全部 schema、policy 与 SHA256，最后只在内存中
替换完整 episode 的 split。任何 hash 漂移、缺失/多余/重复 seed、错桶、重复 episode 或保留 seed
进入数据都会拒绝加载。默认 loader 不自动切换，训练调用方必须显式提供三个 canonical 路径。

正式复核结果为 seed `60/20/20`。图数据 canonical episode `7715/2574/2562`、edge
`281/116/83`；主动视觉 episode `540/180/180`、sample `695705/229651/227886`。两类数据的保留
seed 泄漏均为 0，原数据树生成前后哈希相同。该结果允许 D4/D5 在后续联合研究中引用同一 split
身份，不代表两个模型、标签或运行合同已经可联合训练。

图监督稀疏和主动视觉动作归因仍是准入主断点。GNN 只输出既有候选边的同目标概率，active-vision
模型只允许 shadow。中心 `global_track_id` 只读、同相机互斥、几何门、友方/版本门和规则回退均未
变化。本轮没有模型重训、AirSim 运行或相机命令接口变化。

## 2026-07-20 主动视觉行为克隆复核

正式主动视觉数据已完成严格审计和全量行为克隆。900 个 episode 按整 seed 分为
`540/180/180`，训练使用 685,005 个样本、固定 seed `20260720` 和 5 个 epoch。最佳 epoch 为 5，
test 损失 `0.109311`、精确动作准确率 `0.955978`；单候选集 CPU 推理 P95 为 `0.1203 ms`。

复核结论是不准入 assist。`reacquire` 占 92.16%，test 中 4,051 个 `observe_target` 样本召回率
为 0，`hold` 无正样本；侦察相机精确动作准确率只有 62.18%。温度缩放没有改善 ECE。总体准确率
主要反映多数类和简单意图，不能证明云台观察策略泛化。

v5 bundle 只允许 shadow，PPO 未启动，规则回退和相机命令安全门保留。无动作归因的相邻 outcome
不作 reward。该段记录 2026-07-20 原 split 状态；2026-07-21 canonical view 已完成 split 身份
对齐，联合模型仍因标签和准入合同未满足而关闭。下一轮先补齐 hold/observe/recon 示范和真实 shadow
ACK/outcome，再用至少 20 个未见 seed 做 paired non-degradation；在此之前不得改变中心
`global_track_id`、版本门、友方冲突门或默认规则路径。

## 2026-07-20 正式图数据训练前复核

正式 900 episode 已完成，D5 对 12851 个匿名跨视角图帧完成 strict load 和 SHA256 审计。数据
合同、整 seed 分割和保留 seed 隔离通过。候选监督覆盖未通过：97.52% 图帧无边，三分割负边只有
`11/4/4`，可评价 candidate recall 的 pair 分母为 `4/1/1`，且负边仅出现在 200v200。

本轮将数据准入、开发训练和模型晋级分开。数据门失败时允许运行 development-only 模型验证管线，
但 bundle 固定 `g1_assist_eligible=false`。固定 seed 的开发训练在少量标注边上得到验证/测试
F1=1.0，这一结果受 4 条负边限制，误合并率和完整候选召回不可用，promotion 继续失败关闭。

下一阶段不调整图网络和在线身份门，优先修改数据 producer：增加多相机共同可见窗口、可混淆异目标、
密集交叉、遮挡进出、时延重捕获和有界外参扰动；同时补齐候选裁剪前同目标跨相机 pair 分母。样本
必须来自独立场景/seed，禁止复制现有边。详细证据见
`reports/D5_TRACKLET_GRAPH_TRAINING_READINESS_20260720.md`。

## 2026-07-20 多批次接收窗口复核

正式生成链在已有 209 条完成进度后暴露第二个通信退化边界：同一运行周期可能收到同相机多个已
到达批次。D5 原适配器只允许每流一批，无法表达通信队列积压。该限制与动态相机数量、目标数量、
检测身份无关。

修复把调用解释为接收窗口。窗口先整体预检，再按 arrival、resource、camera、measurement 的确定
顺序逐批提交。每流独立推演双高水位，任何非法批次都使窗口原子失败；正常与 OOSM 混合时仅正常
帧写 tracker。全部批次保留审计，跨视角图只使用每个相机最后有效状态，避免历史 tracklet key
冲突。已接收 measurement 的有序登记同时拒绝较早正常帧和 OOSM 重传，但不参与身份或运动估计。
定向 `31 passed`、D5 全量 `410 passed in 11.68s`。

代码级阻塞关闭，正式 900 episode、最终化和至少 20 个未见 seed 仍未完成。绑定 `c5a9f6d` 的旧
209 条目录只保留为故障证据。main 必须在同时包含 D5 与 runner 修复的新干净提交上，使用新输出
目录从 sequence 0 重建 900 episode，不得恢复或拼接旧目录。D5 不因恢复吞吐而放宽真值隔离、
中心 ID 只读或 OOSM 失败关闭规则。

## 2026-07-20 通信退化视觉时序复核

正式分块在 `communication_degraded` 200v200 暴露了 camera-local tracker 的时钟语义错误。传输层
按 arrival 时间交付，旧 measurement 后到是合法 OOSM；D5 原实现却要求 measurement 单调，并会在
取消检查后产生状态回退风险。

修复后每个相机流以 arrival 严格推进作为接收合同，以 measurement 高水位决定是否允许 MOT 状态
更新。迟到 measurement 仍按真实到达顺序接收并保留双时间戳，但只输出 `oosm_ignored` 诊断和相机
几何，不生成局部轨迹证据，不改当前状态。重复 measurement、重复 arrival 和 arrival 回退均在
提交前拒绝。该策略没有引入 truth ID，也不接触中心 `global_track_id` 所有权。

OOSM 修复当时定向 `24 passed`、D5 全量 `403 passed in 9.74s`。main 后续在新目录完成首个
45-cell、checkpoint resume，并累计 209 条完成进度，原 OOSM 异常没有复现。后续中断属于上节的
同相机多批次限制。本轮仍没有证明 OOSM 信息利用率、跨视角精度或实时收益；固定时滞回放仅在
900 episode 统计证明有必要时设计。

## 2026-07-20 clean-tree 200v200 postopt2 性能复核

main 在提交 `45b36500dc3c6935b1f116614993e291041eb12d` 上完成 nominal 200v200、2 s、
seed 930-932 的 clean-tree postopt2 复测。三场均为有限状态，记录
`repository_dirty=false` 与 online truth use=0；D5 graph dataset 正常最终化。

每 seed episode run 为 `34.3668/41.8854/48.4893 s`，artifact staging 为
`4.1704/4.1311/4.1357 s`。D5 active-vision staging 从 postopt1 的
`41.5623/43.2639/41.2271 s` 降至 `4.0494/3.9898/3.9995 s`。总 staging
`126.4682→12.4372 s`，总生成 `262.2866→144.5513 s`，finalization
`7.7377→7.2777 s`，episode run `127.9871→124.7415 s`。

这组同配置、同 seed、干净工作树的系统计时关闭 D5 writer P1。先前 200-camera/400-track
fixture 和 3,536-sample 制品结果继续作为根因与等价性证据；gzip level 6、schema、采样、特征、
动作/ACK、真值隔离、SHA256、只读和公共独立 audit 未改变。该结论只针对离线制品写入，不是在线
关联、主动视觉收益或实时运行结论。

三 seed 只规划出 1 个测试 seed，不满足 20 个未见测试 seed 的正式门。active-vision dataset 以
`insufficient_unseen_test_seeds` 保持未最终化。正式 900-episode corpus、BC/PPO、checkpoint、
paired shadow 和 assist 准入仍开放。

## 2026-07-20 主动视觉数据开销复核

本轮只收敛 D5 数据写入与终结开销，不改变末端关联算法或运行时接口。非物化 reader 现在对共享
snapshot 只做一次对象审计，每条 sample 使用轻量合同摘要；finalize 每 episode 只做一次 online/
offline 内容审计，并在文件指纹不变时复用 SHA256 和连接证据。公共 audit 始终独立读盘复核。

6-episode 确定性计数由 stream/offline parse `12/12` 降为 `6/6`，SHA256 `67→20`，每制品一次；
独立 audit 仍重新执行一轮。合成 200-camera/400-track stream audit 辅助墙钟约 `9.81→0.37 s`。
原阶段数据专项 `16 passed`、全量 `398 passed in 15.75s`；本次最新回归为 `18/400 passed`。
schema、采样、特征、真值隔离、whole-seed
split、哈希、只读和失败关闭语义保持。正式 900-episode clean-tree 吞吐与恢复仍开放。

## 2026-07-20 主动视觉整 episode 容量与 lazy 数据合同审查

审查接受 record v2 的确定性 gzip JSONL 为 D5 正式 online 存储。每个唯一 snapshot/camera
feedback 按 SHA256 key 只写一次，sample 保存稳定引用以及完整规则示范、requested/effective
action/mode、plan/coalition/communication version 和可选 ACK；数量由输入 camera/target/resource
决定。source identity 继续固化 Git object ID、dirty 标志和外部 config SHA256。

在线/离线隔离审查通过：writer、stream audit 和 materialized loader 均拒绝 truth/actor/object
identity；offline label 只在 episode 关闭后按 `sample_key + observation_key` 写独立文件，永不回填
snapshot。offline staging 与 finalize 核对 online 文件 SHA、episode/source identity、对象 key/引用、
完整 sample 合同、中心 ID 只读引用和 join 完整性；未知引用、局部换绑、版本/时间回退和篡改均
失败关闭。

跨 episode 内存审查通过：finalize 的 staged audit 与独立 dataset audit 均逐 episode 使用
`materialize=False`；同一次 finalize 的最终结构复核复用 staged 证据，不再次解压。两条路径都不
调用 `load_active_vision_episode_dataset()`，也不保留整个 dataset 的 record。
新增 `load_active_vision_episode_dataset_lazy()`；其 `iter_episodes()`、BC 和 PPO iterator 每推进一次
仅物化当前 episode。BC 不读 offline label；PPO 对任一 reward unavailable/null 立即失败关闭。
兼容全量 loader 仍可用于小数据，但不作为正式 900-episode 训练入口。

split/制品审查保持：完整 `(scenario_version, seed)` group 不可分，同一数值 seed 跨 scenario/scale
原子分配，test 对 train/validation 完全未见；唯一 seed 或声明 unseen seed 不足即拒绝。manifest、
逐文件/split/training-set SHA、source identity、只读、额外文件拒绝和 reward `[-1,1]`/null 语义均
未削弱。tracklet graph 同样修复共享 seed 泄漏，dataset/bundle 为 v2。

去重语义对应 active episode dataset v3、descriptor/record/sample v2 和 bundle v4；learning
dataset 保持 v2，snapshot/action/feedback/ACK/offline-label 保持 v1。旧嵌套文件不兼容；V1 Python
名称仅为源码别名。lazy 读取变化不改变磁盘语义，因此不再升版。

最终复核补强了既有合同而未升版：相对 dataset root 可正常 staging/finalize/load；非 assist
effective mode 必须保持规则动作；resource/camera/local tracklet ID 使用同一 truth-like guard。

main nominal seed 91、每档 2 s 复测的 5/20/50/100/200v200 总制品约
`0.086/0.295/0.733/1.543/2.884 MB`；200v200 online/offline `1.064/1.818 MB`、`3536`
samples、RSS约 `1.04 GB`、online truth=0。D5 数据管线 `14 passed in 20.56s`，全量
`396 passed in 30.02s`；12 episode/576 sample 高基数回归证明 finalize/audit 完整物化调用为 0，
lazy iterator 按 episode 推进。审查只关闭 D5-owned 软件/单 episode 容量阻塞；尚无 900-episode
正式 corpus 峰值、正式训练、20-unseen-seed 性能、checkpoint 或 assist 准入。D5 未修改 main。

## 2026-07-20 主动视觉研究路径与 source-observation 审查

审查确认新增 `ActiveVisionSnapshotV1/ActiveVisionActionV1` 是版本化最小权限合同。snapshot
只接收中心 `GlobalTrack` 和当前 `AssignmentPlan` 的只读候选/成员/version、相机云台/FOV、
投影协方差、可见/遮挡、通信状态及友方 reservation；递归拒绝 truth/actor/object identity。
action 只表达 observe/search/hold/reacquire、有限 yaw/pitch 和 wide/zoom，不存在飞控或重新分配
接口，任何目标引用必须属于输入中心候选与当前相机 assignment 的交集。

安全审查确认模型只能选择规则生成的有限候选，之后仍检查 plan/coalition/communication version、
候选成员、证据 age、FOV、云台机械角与速率、slew、友方冲突和 timeout。OOD、低置信、非有限、
异常、慢推理及 bundle SHA/schema/state 错误均回退同 tick 已计算的规则动作。库默认 disabled，
CLI 默认 shadow；shadow 不改变规则动作。输出具有 requested/effective mode、fallback、latency、
fingerprint 和版本 provenance。

训练审查确认完整 `(scenario_version, seed)` group 不可分，共享数值 seed 的跨场景 group 也原子
分配；已提供 behavior cloning 与原生 PyTorch clipped PPO，不引入 PyTorch Geometric。bundle 只
加载 weights-only state_dict。assist
报告绑定模型和 dataset/split/training-set SHA，准入门不少于 20 个完全未见 seed，并要求正式
非合成、逐 episode/总体 safety、visibility、reacquisition delay 非退化。单测中的 20-seed
fixture 只验证门控逻辑，合成标志会阻止正式准入。

scalable adapter 审查确认 `observation_id` 现在只读传播为 `source_observation_id`，用于 episode
结束后的 evaluator label join。它不进入 tracker cost、local/tracklet/global ID、图特征、聚类或
中心 binding；同帧重复 observation 在 tracker 更新前拒绝。缺少离线标签的假目标显式造成
labels incomplete。2026-07-20 主动视觉专项 `17 passed`，D5 全量
`376 passed in 9.94s`。该段记录 2026-07-20 状态；2026-07-25 已形成同一
development-only 权重的 20-seed 合成报告，但仍没有已准入默认 checkpoint 或 AirSim 云台闭环，
故审查只接受软件路径和模型谱系闭合，不接受 assist/默认路径晋级。

main 后续已把上述合同接入统一三维 episode：snapshot 由 D2 中心航迹、D3 当前计划、D5 几何
证据和模拟相机 yaw/pitch/FOV/最近接受版本构造；规则 look-at/reacquire/scan 生成版本化相机
命令，经 plan/coalition/communication version、有效期和资源一致性复核后在下一视觉帧应用，
并发布 runtime ACK。5v5 `84/84` 和 200v200 seed 17、1.2 s `1872/1872` applied 只构成单
seed、脏工作树接口证据，不构成 AirSim 云台、实机或主动视觉收益证据。shadow 仍不控制，
assist 未正式准入时仍回退规则。

## 2026-07-20 版本化训练与制品管线审查

审查确认 `tracklet_dataset.py` 把匿名 graph NPZ 与 evaluator label JSON 分流：图中只保存在线
D5 已产生的节点、候选边和固定顺序数值特征，不保存 `truth_entity_id` 或共享中心 ID 列表；
truth 只在独立 label 文件中按匿名 tracklet key/timestamp 离线连接。dataset manifest 记录
schema、feature names/version、generation config SHA256、class balance、candidate-recall
availability、hard-negative provenance、split hash 和 training-set hash，加载器使用
`allow_pickle=False` 并校验文件 SHA、shape、有限值和 feature order。

split 审查通过：切分以完整 `(scenario_version, seed)` group 为不可分单元，同 seed 的多个
episode 不跨 split，不存在 edge-level random split。训练按完整图做确定性梯度累积，困难负样本
来自几何门内低 gate-score 异目标边，BCE 使用正类权重。模型选择、temperature calibration 和
F1 threshold selection 仅使用 validation；test 报告 precision/recall/F1、constrained-cluster
false merge、candidate recall、Brier/ECE、P50/P95 latency 和 model size。真值不完整时相关
指标保持 unavailable/null。

bundle 审查通过：`manifest.json + weights.pt + SHA256SUMS` 固化模型/图/feature 版本与顺序、
hidden dim、message steps、训练集/split hash、validation temperature/threshold 和验证结果；
加载只使用 `torch.load(weights_only=True)`。缺失、损坏、SHA/schema/feature/version/state
mismatch 均失败关闭。在线 scorer 仍只输出 candidate-edge probability；非有限输出、超时、
低 certainty 或 bundle 不可用回退确定性几何规则。受约束聚类、同相机唯一、中心 Hungarian
和 `global_track_id` 所有权保持原合同。

2026-07-20 验证为新专项 `12 passed`、组合 `46 passed`、D5 全量
`355 passed in 9.48s`，接受阈值为零失败；checkpoint 仅在 `tmp_path` 生成。本轮审查只接受
训练/校准/评估/制品代码管线闭合，不接受模型准入。至少 20 个未见 seed、代表性困难场景、
冻结门限和默认 checkpoint 均开放；几何规则继续默认。该阶段未运行 AirSim；本轮新增主动视觉
合同后，AirSim 集成计划已同步未来接线边界，但仍无新增 AirSim 证据。

## 2026-07-20 匿名稀疏图审查

审查确认新路径没有把图节点定义成目标或全局航迹，而是严格的 camera-local tracklet。
在线节点合同不含 truth/actor/object/global ID；中心 GlobalTrack 仅参与投影门和最终只读
binding。候选边在学习前经过时间、视场、极线、射线、重投影和协方差门，并受每节点度数
上限约束，最终输出边集在 200 目标/4 相机场景保持稀疏。P0 复审补强了 local-ID 防线：
构造器和递归 payload guard 现在拒绝 `TGT-0001`、嵌入式 `camera:TGT-002`、
`TargetDrone_1`、`Target_UAV_7` 和 `intruder-003` 等 truth-like 编号，但
`cam01-track-0001` 仍合法。

审查新增 `scalable_3d_adapter.py`：实现不导入 main/D2/evaluator 类型，以 duck typing 接收
真实在线 DTO 字段形状；整批 truth guard 先于 tracker 更新。local ID 由每
`resource/camera` 独立 tracker 分配，`observation_id` 只读传播为审计键而不参与身份；相机 metadata 形成 K/R/t 与
协方差，六维中心状态只读形成投影假设。在线封装依次执行构图、规则或注入模型边概率、受约束
聚类和中心 binding，并把 model missing/error/low certainty 标成规则 fallback。

原生 PyTorch 模型使用 `index_add_` 消息聚合且只输出同目标边概率，不依赖
`torch_geometric`。最终聚类强制同一 camera namespace 最多一个 tracklet，Hungarian 只能
选择中心提供的 ID。独立离线 truth 流、困难负样本和正类权重边界清晰，未发现在线标签泄漏
或 D5 创建/改写 `global_track_id` 的路径。

本轮审查确认原实现确实先遍历全部非空相机对，并建立每对 tracklet 笛卡尔矩阵。现已改为
两级索引：相机位姿、截断视锥 AABB、相机量测时间和三维覆盖桶先产生可检查相机对；
`camera_pair_budget` 限制实际检查数。同桶间隔轮转和跨桶对角线轮转保证裁剪确定且不只偏向
低编号相机。第二级按中心投影支持或时间近邻形成 tracklet 候选，并在几何计算前限制每节点
候选度。预算耗尽后的节点保持 anonymous/unbound，不允许模型或规则补猜身份。

2026-07-20 seed 200 压力测试为 800 节点、1923 最终边、密度 `0.006017`、最大度 6、
索引后 tracklet 候选 3050，本次实测 `0.442 s`；seed 4 小样本训练将 loss 从 `1.038521`
降至 `0.011535`，训练准确率 1.0。5/20/50/100/200 相机结构矩阵中，200 相机总对 19900，
只检查/保留 400 对、预算丢弃 19500、tracklet 候选 397，全部相机均得到候选覆盖。
D5 全量在本轮训练/制品同步后为 `355 passed`。审查接受相机索引和候选上界为 D5-owned P1 代码闭合，不把单次时延
当作 200-camera episode 性能门。

独立整 episode 数据合同、validation-only 校准、test 指标和 bundle 软件现已实现。2026-07-25
已完成同一 development-only 权重的 20 个未见 seed 合成 test，但仍无代表性困难整 episode、
默认 checkpoint 或真实 AirSim 模型接线，因此 GNN 不得声明准入或替换现有默认路径。模块 DTO
adapter 和训练制品代码通过不等于运行时或默认 checkpoint 验收。main scalable module stack
已调用 adapter，但新增候选与模型路径诊断仍需
由 main/D6 持久化并做多 seed 预算召回、内存和 P50/P95 评估。

主动视觉 API 的动作集只有观察中心目标、规则扇区扫描、云台增量和 FOV/变焦；timeout、
低置信和无效 binding 回退规则扫描。该接口不等于已训练 RL policy 或已执行云台闭环。
统一三维 runtime 已提供命令 ACK/fallback 的接口证据；后续审查仍需提供在线 truth use=0、
global ID rewrite=0、至少 20 个未见 seed 的 paired 准确率/时延/非退化结果，以及真实 AirSim
云台或实机 ACK，才能决定学习路径是否晋级。

## 2026-07-16 ComputerVision 5+1 真实专项审查

main 已在独立分支完成两个真实 AirSim episode：5 个 `1920x1080`/60 度局部相机、
1 个 `3840x2160`/75 度侦察相机、5 个 `Quadrotor1` actor；每个 episode 为
12 秒、49 帧、seed 7。审查确认 D5 对每个相机 batch 使用
`measurement_timestamp` 投影，没有把最后一帧时间用于整段注册。

detect 的召回/配准/稳定/联合覆盖/侦察全覆盖/IDSW =
`1.000/1.000/0.975/1.000/0.918/0`；YOLOv8 + 原生 ByteTrack =
`0.622/0.996（严格 0.966）/0.955/1.000/0.878/25`，P50/P95 约
`10.42/12.37 ms`。两路 online truth use=0、`global_track_id` rewrite=0。

该隔离专项没有运行 D1/D2。main 使用 actor truth 运动学合成带中心
`global_track_id` 的 `GlobalTrack` fixture，truth 同时用于离线评分。
`online_truth_identity_use=0` 仅表示 D5 的 local bbox 到 fixture 关联代价、
Hungarian 选择和稳定窗口不读取 actor/object/truth identity，不表示整个专项完全
不读取 truth。

验收门限为 detect/YOLO 召回 `>=0.95/>=0.90`、严格配准 `>=0.95`、稳定
`>=0.90`、联合覆盖 `>=0.95`、侦察全覆盖 `>=0.90`、IDSW `<=0/<=5`，
truth use/rewrite=0。审查判定 detect 几何基线通过；YOLO+ByteTrack 因召回、
IDSW 和侦察全覆盖失败而保持 optional。后续必须补齐这些质量缺口和多 seed；
单 seed 不构成默认主线晋级。独立专项不替换默认 D1-D7 流程，也不改变既有
身份、几何、稳定或执行安全门。

## 2026-07-16 人工记录局部观测适配器审查

D5 已在离线 manual tracker 子模块增加公开转换器，把人工轨迹逐帧记录转为
`LocalImageTrackObservation`，但不把该记录直接注册到任何 GlobalTrack。输出保留
camera-local ID、measurement/arrival timestamp、frame、backend 与连续 measured
history；measured 的 bbox 为 `xyxy` 并携带现有自适应像素协方差，lost 不携带
center/bbox/covariance 且 confidence 为 0。identity audit 在转换前执行，重复量测
大于 0 时整批拒绝。

包边界审查确认 `manual_video_tracker` 不再由 D5 根包导出或强制加载；离线 CLI 与测试
显式导入子模块。该变化减少默认 AirSim/D5 包导入对离线视频依赖的耦合，不改变
CSRT、KCF、`bright_hungarian`、AirSim detect-first、TerminalAssociation 或 D7 gate。
输出不包含 `global_track_id`，local ID 仍不能替代中心身份。

2026-07-16 验证使用既有 95 帧五目标记录 475 条，得到
`470 measured / 5 lost`、重复量测 0；确定性回归覆盖协方差、双时间戳、
infrared、`xyxy`、历史重置、坍缩拒绝和根包导入边界，D5 全量 `288 passed`。
接受阈值为零失败、重复坍缩必须 fail closed。该审查只关闭离线合同适配子项；
通用视频、真实 AirSim、多视角身份与物理拦截证据仍开放。

## 2026-07-15 人工框选视频轨迹关联审查

D5 已增加独立的人工初始化 local MOT 工具。用户在首帧按顺序框选目标，或用显式 ROI 列表复现；顺序固定形成 `local-001...`。默认跟踪后端是每目标独立 CSRT，KCF 仅为对照。为处理 `b.mp4` 中邻近亮点，工具可增加正对比峰候选和 Hungarian 一对一关联，避免多个 tracker 把同一亮点同时写成有效量测。

95 帧五目标结果为 `92/3`、`95/0`、`93/2`、`95/0`、`95/0`（有效/丢失），`duplicate_measurement_count=0`。短时 lost 后 ID 仍按人工初始化顺序恢复，lost 行不保留旧 bbox。纯 CSRT success 标志会掩盖 ID 合并，因此今后本地视频审查必须同时报告重复量测、最小中心间距、框 IoU 和 lost，而不能只报 tracker success。

审查结论仅适用于该单相机亮目标视频。工具不接收分配计划、GlobalTrack 或身份声明，不做敌我识别，不产生 `TerminalAssociation locked`，也不授予 D7 视觉 PNG。任何后续接入 D5 主线都必须先经过 GlobalTrack 投影、时间戳/协方差、几何门控和现有安全合同。

2026-07-15 验证口径为 1 个真实视频、95 帧、5 个 local ID 和 475 条逐帧记录；D5 全量 `284 passed`，接受阈值为零测试失败、零重复量测。语法和格式检查通过。

## 2026-07-15 真实 M5N2 20-case 审查结论

审查范围严格限定为 baseline/candidate 各 10 seeds 的 M5N2。第二 primary 由每场 active-primary 合同动态确定，20 场中 19 场为 `INT-03`、candidate seed 002 为 `INT-02`。D5 在 `3725/3725` 个适用 tick 上均有 decision 与 live first-failure stage/reason；直接 `failure_category` 未持久化，故本审查不把代码级分类能力写成真实 artifact 可用。

第二 primary 决策为 `locked/ambiguous/reacquire/hold=1721/795/1209/0`。bbox-stability、live-detection/freshness 和 visual-association 分别占 `34.44%/32.46%/20.51%`，strict complete 只有 `1.40%`。measured bbox `67.54%`、visual fresh `71.33%`、geometry gate accepted `62.07%`、bbox stable/handoff-ready `4.32%`。没有出现 plan/global-ID、friend 或 duplicate hard conflict；这只说明本场景没有注入该类冲突。

物理 second-primary 结果为 baseline/candidate 各 `0/10`，T001 coalition completion 合计 `0/20`，最近距离范围 `8.843-14.740 m`。candidate 虽增加 handoff-ready 快照，但没有形成 5 m 或联盟收益，不晋级默认路径。后续审查优先级为：持久化 direct failure-category availability；冻结/分层 primary membership；校准 measured bbox 连续性、visual freshness、候选 margin 和重获取几何；保持 center-owned `global_track_id` 与所有安全门不变。TERM 生效前仅额外完成 `png_ttc_2v2_seed001`，但它未并入上述 M5N2 数字；其余 tuned/dropout 未执行，本节不形成 tuned/dropout 结论。

20 个第二 primary 最终均记录为 `collision_stop`，但它仅是 D7 停控证据。碰撞对象未持久化，当前无法区分成员碰撞、环境碰撞或 AirSim 状态问题，因而不能据此把第二 primary `0/20` 单独归因于 D5。

## 2026-07-15 审查补充：第二 primary 被动诊断

审查确认现有 `TerminalAssociation`、live funnel 和 coalition evidence 已包含所需原始证据，采用扩展既有 cooperative summary 的方式，不建立第二套 DTO。新增逐资源及第二 primary 的 `failure_category`/计数，明确区分 visibility、projection、geometry gate、bbox/edge、ambiguity、staleness、assignment/global-ID contract、friend/duplicate 与 stable-lock 断点。错误 `assigned_global_track_id` 只报告合同冲突，输出仍引用中心 binding ID。

2026-07-15 D5 全量 `272 passed`（零失败门），未运行新 AirSim，未改变 locked/hold/reacquire 或任何安全阈值。下一审查证据必须来自真实 2v2/M5N2 至少 10 seeds，并报告第二 primary 各类别比例、unknown/other 比例、online truth use 和 global ID rewrite；此前不得把该诊断闭合写成物理闭环完成。

## 2026-07-14 actual-v2 证据复核

最新真实 AirSim actual-v2 由 tuned 2v2 与 M5N2 各 1 个 seed 组成，均继续使用默认 AirSim detect。canonical actual 五层 contract/control/terminal-switch/mode/physical 均独立 available，总计 `102/26/26/2/4`；`terminal_switch_allowed_count` 从最终 `control_commands.csv` 独立统计，2v2/M5N2 为 `26/0`，不从 control 层回填。2v2 lock acquisition/visual-control/visual-switch/mode-switch 为 `3/26/2/2`，M5N2 为 `24/0/0/0`。

M5N2 物理层为 active pair `2/3`、target `2/2`、coalition `0/1`，T001 第二 primary 最近约 `11.02 m`。这不能用目标级成功解释为联盟完成。两个 case 的 identity/state online truth use 都为 `0/0`；D5 必须保持匿名 local detection 到既有中心航迹的 truth-free registration，且绝不创建、改写或换绑 `global_track_id`。

复核结论是 P0 actual artifact 与五层 schema 可用性 `2/2` 已有证据，但完整 P1 仍开放，D6 formal overall status=`fail`。D5 当前开放 P1 是 M5N2 第二 primary、真实几何 drift、detect/YOLO/MOT 多 seed 和二级同 tick freshness，不是五层 schema 或 main 接线缺口；IBVS、真实身份源、完整在线 PnP/ROS 2 保持 P2/P3。M5N2 既有视觉完成门保持至少 `8/10`，与 physical coalition `0/1` 分母独立。本次只同步证据，不修改 D5 算法或默认 detect 路径。

## 2026-07-14 postbatch live visual evidence 收尾

最新 M5N2 证据要求把三个状态分开：`visual_match_locked` 是本地检测对中心既有航迹的几何关联结果，`execution_lock_allowed` 是 D5 的可执行视觉证据，`d7_handoff_input_ready` 是向 D7 交付当前本机 bbox 的条件。过去第一项可能为真而后两项不具备，造成 `locked` 计数看似较高但末端仍 acquisition timeout。

D5 已补全 truth-free bbox/中心与 resource/camera/stream/backend DTO，并将执行许可收紧到 own-camera measured bbox、完整合同、连续 measured lock、bbox 尺度/稳定性和全部安全门的合取。baseline/candidate `330/311` 条控制记录中均仅 INT-03 有 `40` 条 bbox 非零，说明剩余问题是末端持续 detection 与尺度，不是通过 cross-view 或历史 locked 补值即可解决。2026-07-14 全量 `261 passed`；真实多相机、多 seed 与异常大框仍为 P1。

## 2026-07-14 semantics_v2 第二 primary 历史分层复核

最新 M5N2 seed-1 表明 INT-02 在 baseline/candidate 中并非不可见：measured detect 为 `195/193` 帧，raw visual lock 为 `140/142` 帧，final execution lock 为 `18/18` 帧，T001 coalition consensus 均为 `14` 帧。raw lock 与最终 lock 的差异来自执行合同；INT-02 bbox 到 `19.0/18.6 s` 才稳定，而当前 arrival window 在 `2.2 s` 结束。D5 必须继续把过期合同转为 hold，不能以放宽版本、身份、友方、duplicate、时间戳或几何门控换取锁定率。

实施上新增 `d5_live_visual_funnel_v1`，将检测、投影、马氏门、raw lock、execution gate、连续 measured lock、bbox 稳定和 handoff 分层；连续 lock 只计当前 measured 且执行合同有效的同一局部轨迹。runtime record 顶层字段和 `d7_handoff_input` 允许 main/D6 在不解析自由文本的情况下定位首断点。该阶段确定性验收为 D5 全量 `258 passed`、零失败、truth use/global ID rewrite 均为零。顶部 postbatch 章节已更新 current local-track 路由结论，剩余项为真实持续 detection、尺度和多 seed。

## 2026-07-14 bbox 历史连续性与 producer 合同复核

postfix seed-1 的 M5N2 baseline/candidate 中 `bbox_stable=true` 均为 `0/1388`，T001 consensus 为 `13/347`、`12/347`；2v2 PNG/TTC 为 `0/52`。旧链路每个 association 的 `visible_frame_count <= 1`，因为 runtime 只传当前 tick 的 `scoped_local_tracks`，而 handoff 没有状态。M5N2 的 T001 另有 `326/347` tick 发生真实 primary membership transition，因此低共识同时包含合法安全重置，不能通过放宽门限或跨成员拼接历史解决。

当前 D5 在 `TerminalAssociator` 内维护 measured bbox/MOT 历史，连续身份由 resource、assigned target、local track、camera、stream、detector/tracker backend 和 committed/current membership 构成；plan/coalition version 本身不构成 reset。换绑、换员、local/camera/backend/stream 变化、producer reset、非 measured source、identity/friend/duplicate conflict 均 fail closed。输出可审计 history length、CV、reset reason、key/signature、source、source plan versions 和 raw/effective MOT history；handoff 可消费单 tick 输入后的 D5 累积状态。共同视觉仅认可 current committed active primary，不完整 commit 不贡献 stable count/common window。

2026-07-14 全量 D5 `255 passed`，接受阈值为零失败，未运行新 AirSim。D5-owned 历史/合同 P1 已闭合；后续 canonical actual 已传递 committed membership、pre-decision duplicate hint 和稳定的 camera/stream/backend/local-track transition/MOT 字段，并独立写出五层 envelope。当前开放 P1 仅为 M5N2 第二 primary、几何 drift、detect/YOLO/MOT 多 seed 和二级同 tick freshness；YOLO/MOT backend 缺失仍按合同 fail closed。

## 2026-07-14 原生 MOT history 断点复核

本批关闭一个代码级 P1：Ultralytics 原生 ByteTrack/BoT-SORT 已能返回 camera-local tracker ID，但 `Results` 解析曾把每帧 `mot_history_length` 固定为 1，无法满足 `TerminalAssociator` 默认 `min_mot_history=2`。现由 `YoloMotAdapter` 按资源、相机、实际 native backend 和 native ID 累计连续实测命中；不同流、不同 backend 和不同 ID 不共享历史。

失效规则保持保守：空帧立即中断连续 measured history，native ID 在 `max_track_age_frames` 内可作为 tracker 身份存活，但恢复帧只计 1；超期状态删除。stream/episode reset、原生模型重建以及 native/fallback 切换均隔离历史。原生失败时释放该流模型并转入独立 IoU fallback；恢复原生后不能继承 fallback 或故障前历史。没有使用 AirSim actor/object/truth ID，没有创建或换绑 `global_track_id`，也没有降低 `min_mot_history` 或其他安全门限。

验证日期为 2026-07-14，Results-like 确定性场景覆盖 ByteTrack/BoT-SORT、同流累计、跨资源/相机隔离、ID 切换、短/长遮挡、stream reset、episode reset 和 native-fallback-native；D5 全量 `241 passed`，接受阈值为零失败。本项不代表真实 AirSim/真实图像多 seed 准入，远距召回、bbox/时间对齐、连续图像 IDSW/IDF1 与计算预算仍为 P1/P2。

## 2026-07-14 planner feedback 语义复核

D5 现有输出字段足够，不新增 planner-specific DTO。D3/main 应把 `decision_state in {ambiguous, hold, reacquire}` 默认解释为当前 resource-target pair 的视觉证据不足，只阻断 D7 视觉切换或请求 cue/reacquire；不得据此设置整机 `resource_unavailable`。只有 D5 同时给出 `consistency_state in {conflict, inconsistent}` 与 `recommended_d4_action in {report_conflict, arbitrate}` 时，才建议进入 hard planner feedback。

hard 条件包括 verified friend overlap、spoof suspected overlap、direct/cross-view duplicate lock、assignment authorization/version conflict 和持续 local/global assignment conflict。unverified/stale identity 与 unknown category 仍是待确认状态，不推断 hostile。2026-07-14 专项 52 项、当时 D5 全量 235 项均通过，零失败为接受阈值；`global_track_id` rewrite 与 online truth use 均为 0。该证据仅关闭 D5 合同语义 P1 子项，真实 AirSim M5N2 检测、稳定 lock 与物理闭环仍开放。

## 2026-07-13 M5N2 与原生 MOT 最新实测

高威胁目标的多个 active primary 现在分别形成视觉漏斗和 first-failure 记录。显式 per-primary 合同只要求各成员自己的稳定锁定，不要求共同锁定窗口或同时到达；coalition 合同仍执行原共同窗口。M5N2 实测形成 `120` 条 active-primary 证据、`120` 条 visible 证据和 `74` 条 D5 关联/锁定证据，最佳 coalition completion 为 `5/10`，低于 `8/10` 验收线。主要失败原因为 `d5_not_locked` 和 `terminal_detection_acquisition_timeout`。

原生 MOT 已完成正式 `18`-case AirSim screening：`1920x1080`、FOV `90`、距离 `20/30/50 m`、confidence `0.1/0.2/0.3`、ByteTrack/BoT-SORT。20 m 两后端 native active rate/continuity 均为 `1.0`、IDSW 为 `0`，P95 约为 `7.4/16.2 ms`；但 precision/recall 仅约 `0.26-0.33`，30/50 m 均无检测。准入候选为 `0`，two-camera confirmation 为 `0`，ByteTrack/BoT-SORT 均未晋级，默认在线路径继续使用 AirSim `simGetDetections`。

2026-07-13 detector 子项当时聚焦第二 primary、YOLO/AirSim bbox 口径/尺度/时间对齐、30/50 m 召回和候选多 seed confirmation；当前 P1 四类边界以顶部状态为准。plan owner/node、plan/coalition version、friend/duplicate、reserve standby、truth 隔离和 `global_track_id` 不变式均保持。2026-07-13 当日 D5 全量回归为 `232 passed`，2026-07-14 最新全量为 `241 passed`；本文中的更早测试数字均为对应阶段历史基线。

## 2026-07-13 对象类别与高分辨率 YOLO/MOT 配置

GlobalTrack 的 `uav` 与 detector 的 `drone/intruder` 原本可能被解释为不同类别，从而在末端代价中增加不必要的类别惩罚。当前 D5 已建立统一 object-class taxonomy：大小写和常见空格、连字符、下划线变体先规范化，`uav/drone/intruder` 均比较为 `uav`；`bird` 等真实异类仍产生惩罚。原始 detector 标签写入 `raw_category` metadata 供审计，但不能作为敌我结论，affiliation 仍由 Remote ID/MAVLink/DDS/视觉标签等独立正向证据处理。

高分辨率推理不再固定依赖 Ultralytics 默认尺寸。`YoloMotAdapterConfig.inference_imgsz` 可按相机设置正整数或 `(height, width)`，并透传 ByteTrack/BoT-SORT 的 `model.track()` 及 detector fallback 的 `model.predict()`；未配置时不传参数，保持兼容。该能力只提供 1080p/4K 标定入口，不代表 30-50 m 召回、算力预算或 native MOT 准入已经闭合。per-camera tracker、truth 隔离、身份门控和 `global_track_id` 不变式均保持；该实现阶段回归基线为 `229 passed`，2026-07-13 当日全量为 `232 passed`，2026-07-14 最新全量为 `241 passed`。

## 2026-07-13 双路检测评价复核

同一 AirSim frame 可同时运行在线 YOLO/MOT 与离线 `simGetDetections` 评价，但两路职责严格分离。在线输出先生成匿名 camera-local track；随后 evaluator 用 AirSim bbox 计算 match/miss 和 local IDSW，actor/object ID 只保存在 evaluator 私有状态。D5 汇总现显式区分 online YOLO bbox、online MOT track、offline AirSim reference matched/missed、native tracker 和 IoU fallback，且对 `1920x1080` 与 `3840x2160` 两类输入均保留各自 `image_size`。该合同不允许离线 truth 改变几何关联、决策状态或 `global_track_id`。

**定位**: 分配完成后，资源节点末端视场内可能同时出现多个目标、友方资源和未知飞行物。本模块负责把局部视觉目标配准回中心分配的 `global_track_id`。
**边界**: 本文只讨论视觉配准、协同身份认证和保守决策，不包含真实火控参数、毁伤逻辑、自动处置控制律或绕过人工授权的流程。

---

## 0. 阶段补充：二级侦察节点图像 cue

本阶段假设存在若干可机动高空侦察无人机作为二级节点。节点携带高性能光电云台，可随任务机动并依据 GlobalTrack/radar cue 指向目标簇；中心节点正常时持续把覆盖小区内的侦察图像或图像平面 cue 发给若干拦截资源，中心节点失效时 D4 可将局部协调权降级到二级节点，二级节点失效后才进入完全无中心协商。

D5 使用这些 cue 的原则：

- 二级节点 cue 通过 `ReconImageCue` 表示，包含 `producer_node_id`、`image_frame_id`、`global_track_id`、像素中心/框、置信度和 `scoped_resource_ids`。机动高空侦察云台 cue 还可携带 `cue_position_ned`、`look_at_ned`、`gimbal_pointing_metadata`、`cue_pointing_error_m/rad`、`gimbal_track_error_px`、`cue_source`、`capability_class=mobile_high_recon` 和 `coverage_mode=mobile_recon_gimbal`。
- cue 只在指定小范围资源内生效，不能跨覆盖区使用。
- cue 只作为视觉关联代价的辅助证据，不能替代中心授权、版本匹配、友方身份认证和本地 MOT 质量门槛。
- 即使二级节点 cue 与本地相机目标一致，局部节点也只能输出 `TerminalAssociation`，不得自行改写 `global_track_id`。

### 0.1 与二级节点图像下发的坐标约束

二级高空侦察节点下发的图像或像素 cue 不能直接等同于拦截无人机本机相机坐标。若二级节点给出的是自身相机画面中的像素框，必须先通过仿真真值、D1/D2 全局航迹或几何重投影，转换到目标拦截无人机的相机平面，才能和本机 `LocalVisualTrack.center_px` 比较。

建议 `ReconImageCue` 的 `image_frame_id` 使用目标相机帧，例如 `UAV1/front_rgb`；原始二级节点相机帧放入 `metadata.source_image_frame_id`。`scoped_resource_ids` 必须限定 cue 可用资源，例如 `["UAV1", "UAV2"]`，避免未覆盖资源错误使用 cue。

### 0.2 本轮 AirSim ComputerVision N-v-N D4/D5 专项适配

D5 已补充 dry-run 适配层，用于消费 `simGetDetections` 风格检测框 fixture，不导入 AirSim、不调用控制 API。5v5 只是 stress baseline：5 个 `Interceptor_Cam_*` 主镜头、5 个目标，目标距主镜头约 50m，目标间距约 20m，镜头间距约 20m，使每个主镜头视场内出现多个目标；二级可机动高空侦察节点可保持约 200m 高差，使用高分辨率、高性能光电云台按 GlobalTrack/radar cue 指向目标簇并提供区域态势 cue。真实 N-v-N 数量由 main runtime 的 `--drone-count N` 统一控制，D5 只按 `LocalVisualTrack[]`、`GlobalTrack[]`、camera/resource 列表和 bus observation 长度运行。

在线配准只使用 bbox、时间戳、本地 MOT ID、显式 detector 类别/置信度和相机几何。在线 category 仅允许 `category/label/class_name` 或 detector `class_id + names` 映射；通用 `name`、`actor_name`、`object_name` 不得作为 category 或关联证据。AirSim detection 的 `object_id`、actor/object name、truth ID 只能作为离线评估标签，不能参与 `TerminalAssociator`、`TerminalObservationBus` 或跨视角一致性判断。本轮二级节点先使用 AirSim `simGetDetections` bbox/metadata，不启用 YOLO；若检测记录中的 `track_id`/`detection_id` 与 actor/truth 字段完全相同，或以 `: / | #` 分隔组件形式嵌入 actor/truth 值，D5 会回退为相机作用域本地检测 ID。

D5 输出边界保持不变：

- 可输出 `LocalVisualTrack`、`TerminalAssociation`、`IdentityClaim`、`ReconImageCue`、`TerminalObservationBus` 和 `CrossViewAssociation` 摘要。
- 不生成 `AssignmentPlan`。
- 不改写 `global_track_id`。
- 重复锁定只输出 `duplicate_terminal_lock_risk`，交由 D3/D4 仲裁。

三类 D5 证据 case：

- `no_degradation`：终端锁定与 D3 分配及离线评估真值一致。
- `degrade_to_secondary`：终端局部/二级证据与中心分配持续不一致或歧义，且二级 `ReconImageCue` 新鲜可用。
- `degrade_to_distributed`：同样不一致或歧义，但二级证据不可用、过期或失效，只能提供分散降级证据。

建议指标：`per_camera_detection_count`、`multi_target_fov_rate`、`cross_view_overlap_count`、`duplicate_terminal_lock_risk`、`terminal_lock_accuracy`、`ambiguous_fov_event_count`。多 seed 报告前可调用 `summarize_multiseed_calibration_readiness()` 被动审计每个 seed 是否具备 local bbox/timestamp、geometry gate log、measurement age、AirSim detect source、YOLO/MOT backend、offline truth label、bbox/handoff advisory 和 duplicate/friend conflict evidence 字段。二级 detect 没有转成有效跨视角关联时调用 `summarize_secondary_visual_coverage_funnel()`，区分“看见目标”“网络联合覆盖”和“形成既有全局 ID 支持”三层指标；该 helper 还可区分 `fixed_downlook_secondary` 与 `mobile_recon_gimbal`，并记录移动云台通过 GlobalTrack/radar cue look-at 补足的目标簇/子簇。

D5 现已补充 AirSim settings 驱动的 detect-to-global-track registration helper：`register_local_visual_tracks_to_global_tracks()` 输入 `GlobalTrack[]`、D2/D3 binding/`Assignment`、每相机 `CameraModel(K/R/t)`、timestamp、像素协方差和 `LocalVisualTrack[]`，输出 `DetectToGlobalTrackCandidate.outcome`、注册后的 `TerminalObservation`、即时 `CrossViewAssociation` 和稳定 `stable_cross_view_associations`。匹配使用像素马氏距离 + Hungarian；缺 SciPy 时退回确定性唯一匹配并保留 gated candidates，便于 JPDA-compatible 下游使用。输出 reasons 包含 `not_all_targets_visible`、`network_union_incomplete`、`no_global_binding`、`reacquire_not_grouped`、`stale_or_missing_recon_cue`、`projection_invalid`、`geometry_gate_rejected`、`stability_window_failed`、`secondary_detect_offline_only` 和 `registered_to_global_track`。

2026-07-09 P1 二级 detect 校准补充：registration candidate 和 observation metadata 已携带 `detect_registration_outcome`、`detect_registration_reject_reasons`、measurement/arrival/local-track timestamp、`measurement_age_s`、`covariance_px`、`projection_covariance_px`、`pixel_error_px`、`mahalanobis_d2`、`gate_pass`、`projection_valid`、`projection_reason`、`camera_pose_source`、`bbox_area_px` 和仅离线评分用的 `offline_truth_global_id`。`camera_pose_source` 支持 `airsim_camera_pose`、`runtime_guidance_pose`、`look_at_fallback`，D5 只消费 main/runtime 提供的 `CameraModel` 和 metadata，不直接调用 AirSim。`adaptive_pixel_covariance_px()` 按 bbox 面积和图像对角线生成二级相机自适应像素协方差；无 bbox 面积时保留安全 fallback。默认稳定窗口为 3 帧内同一 `resource/camera/local_track/global_track` 至少 2 次 gate pass，单帧通过只记为 candidate，稳定后才标记 `stable_cross_view_support=True`。

2026-07-11 AirSim 集成复核发现 cross-view bus 的全历史汇总会把旧帧/旧 plan lock 当成当前 duplicate。D5 已为 `cross_view_associations()` 增加 `as_of_timestamp`、`max_age_s`、`plan_id`、`plan_version` 快照参数：作用域模式先做 freshness 与 plan identity 过滤，再按 resource 保留最新 timestamp 的同帧观测；duplicate 与 coalition 判定只在该快照上执行。无参数调用保持旧离线兼容，scope metadata 可审计筛选数量。main 在线应传当前 frame timestamp、约 `1.5 * dt` freshness 和当前 plan identity；D5 不修改 D3 prohibited edge 或 runtime 调度。

### 0.3 registration calibration 演进结论

`research_modules/airsim_runtime/outputs/p1_d4d5_mobile_recon_20260708_055948*` 现在只作为历史 stress 证据：该旧批次说明 D5 已能识别 `mobile_recon_gimbal`、`radar_global_track_cue`、`mobile_high_recon` 和云台指向 metadata，目标看清能力相对固定俯视对照改善，但二级网络覆盖与降级注册未闭合。

`research_modules/airsim_runtime/outputs/p1_d4d5_registration_calibration_runtime_v2_20260708*` 的单 seed 结果保留为历史基线：`projection_valid_rate=1.0`，三个 case 的 cross-view association 为 4/4/5，但降级 case not-registered 为 35/35。

当前结论来自 `research_modules/airsim_runtime/outputs/p1_gap_closure_calibration_20260710`：5v5、10 seeds、50/200 m、三类 case，共 60 个 case。D6 `not_registered_count=0`，sweep 的 `secondary_detect_available_but_not_registered` 均值/最大值均为 0；平均 `projection_valid_rate=1.0`、stable registration `92.233`、cross-view association `4.417`。基础 detect-to-global registration 已闭合，但网络同帧全目标覆盖率均值仅 `0.0231`、平均覆盖率 `0.7059`，稳定窗口失败仍需校准。局部注册成功不表示二级接管态势完整。

D5 当前无 P0 blocker。2026-07-10 已闭合 active reacquire 友方声明、通用 detection name category 污染、sim-detection actor alias 和端到端 AirSim actor-name local ID 隔离。真实验收证据为 `research_modules/airsim_runtime/outputs/p0_truth_isolation_smoke_20260710`：三类 case 均 connected、各 5 帧，local/detection ID 不含 actor 名，匿名 ID history 达 5，actor 名仅在 `offline_truth_only=True` metadata，每类 cross-view association 均为 4。当前 D5 的 P1 合同层已闭合，开放项是 M5N2 第二 primary、几何 drift、detect/YOLO/MOT 多 seed 和二级同 tick freshness；`solvePnP` 只完成 P2 离线 benchmark。D5 仍不分配、不授权、不创建/改写/换绑 `global_track_id`，在线逻辑不得使用 AirSim truth ID。

2026-07-11 YOLO/MOT 冒烟修复：offline detector evaluation 的 bbox-only 输入不再经过会拆散裸四元组的通用递归路径，现支持单框、多框和 dict/object detection，畸形输入明确报错。此修复只恢复离线 detector 指标采集，不改变在线 tracker、局部 ID 或全局绑定逻辑，也不把 truth identity 带入 metadata。

### 0.4 P1 D4/D5 calibration sweep 与 D6 bundle 状态

main runtime 已新增 P1 D4/D5 calibration sweep，可按二级高度、FOV、二级节点数量和 standoff 组合运行多 seed stress episode。D4/D5 stress 链路已把 D5 的 detect-to-global-track registration output、`detect_registration_outcome`、`detect_registration_reject_reasons`、timestamp/measurement-age/covariance/projection-covariance evidence、`TerminalObservation`、`CrossViewAssociation`、secondary coverage funnel、mobile gimbal metadata 和 registration rejection reason 放入统一 observation/report 流。

D6 标准报告 bundle 已由 main 自动生成，包含 `d6_airsim_calibration/airsim_calibration_records.csv`、`airsim_calibration_summary.csv`、`airsim_calibration_summary.json` 和 `airsim_calibration_report.md`。D5 的职责是保证 evidence DTO、registration helper、truth ID 在线隔离和 `global_track_id` 不变式；AirSim 启停、sweep 调度、日志落盘和 D6 报告仍由 main/D6 负责。

因此当前 D5 的剩余 P1 不再是“缺 helper、缺报告输入合同或基础 registration 不工作”，而是 M5N2 第二 primary、真实几何 drift、detect/YOLO/MOT 多 seed 和二级同 tick freshness。友方真实身份源保持 P2。所有任务保持现有保守门控。

### 0.5 2026-07-10 2v2 active-secondary visual-PNG 复核

证据目录为 `research_modules/airsim_runtime/outputs/p1_gap_closure_2v2_smoke_20260710`。本轮 2 个资源对均完成 `collision_intercept`，pair summary 的 D5 结果均为 `locked`；D7/main 独立 terminal gate 同时记录 `bbox_near_image_edge` 9 次、覆盖 2 个资源对，控制日志中仅 2 条记录满足 `terminal_switch_allowed=True`。因此本轮证明了 D5 lock 与 D7 camera/LOS/maneuver gate 是串联而非互相替代：边缘框不会因为 D5 已锁定而自动放行视觉 PNG。

该结果保留 P1 动作：跨 seed 记录 bbox 到四条边界的归一化最小裕量、连续边缘帧、相机指向误差和 handoff 重复请求，必要时由 D5 handoff metadata 提前暴露 edge advisory，但不得取消 D7 独立门控。P0 集成 hotfix 已通过上述真实 AirSim 三 case 验收并转为保持回归；D5 不对任意既有 `LocalVisualTrack.local_track_id` 做猜测式重写。

### 0.6 2026-07-10 逐帧 D4 evidence 与 YOLO/MOT adapter 补齐

D5 新增 `SecondaryFrameAssociationEvidence` 和 `build_secondary_frame_association_evidence()`。输入必须是同一同步 `frame_id` 的二级 camera coverage、network coverage 和 registration result；输出直接提供 D4 现有 `TerminalAssociationSummary` 可消费的当前帧字段：单相机/网络 full-view、网络 coverage、stable cross-view registration、not-registered、cross-view conversion gap、cue freshness、gimbal pointing 和 reject diagnostic。metadata 保留 measurement/arrival timestamp、detector/tracker backend、registration backend 与 calibration health。registration result 即使包含历史候选，也只选择当前 frame/timestamp；混合 camera frame 或超出同步容差直接拒绝，所以 episode 末汇总不能冒充在线接管证据。D5 仍不决定降级动作。

`YoloMotAdapter` 的主线明确为：优先调用 Ultralytics `bytetrack.yaml` 或 `botsort.yaml`；依赖/权重缺失返回 `unavailable`；原生 tracker 失败但 detector 仍可用时启用 per-stream deterministic IoU fallback。每帧记录 requested/selected backend、native/fallback 状态、detector+tracker wall latency、CPU/GPU 声明预算比较、observed device、per-local-track history 和 camera-local continuity。可选 offline truth bbox 只在在线输出形成之后计算 recall/precision/FN/FP/IoU，不输出 identity，不影响检测筛选、tracker ID 或全局绑定。

新增测试覆盖 5v5 多相机命名空间、目标交叉、单帧遮挡后恢复、native BoT-SORT 优先、离线召回隔离和跨 frame 防回填；D5 全量结果为 `101 passed`。本机 `best.pt`、Ultralytics 8.4.71 和 Torch CUDA 环境可用；CPU 黑帧烟测中首个模型加载约 3.87 s、第二个独立 adapter 热路径约 118 ms，黑帧无检测导致原生 tracker 无 ID 并按设计回退。该结果只验证真实权重和库入口，不代表无人机目标召回率或多 seed MOT 质量。

### 0.7 2026-07-11 AirSim 检测/MOT 历史冒烟边界

真实证据需要分为几何注册基线和 YOLO/MOT 质量两部分：

- 三组既有 D4/D5 回归均得到 `cross_view_association_count=4`，稳定注册约 19-61，证明已有 bbox/几何路径可形成跨视角支持；二级同帧全目标覆盖仍不足，不能据此声明二级节点态势完整。
- `research_modules/airsim_runtime/outputs/p1_yolov8_bytetrack_smoke_fixed_20260711` 完成 6 个 reset-separated episode、每个 2 帧。AirSim RGB 解码、YOLOv8/ByteTrack 调用、per-stream 状态、在线 truth 隔离、offline bbox-only 评分和 D5 runtime event 均正常执行，接口层已闭合。
- 当前相机/actor 几何下 `accepted_detection_count=0`，AirSim offline truth boxes 多数为 0；因此 detector recall/precision 大多不可计算或为 0。原生 ByteTrack 没有 detector track ID，按设计回退 `iou_fallback`，没有形成可评价的 native MOT identity continuity。
- 本轮处理延时多数约 38-49 ms，首轮约 197 ms。该数字只用于当前短序列部署预算基线，2 帧不足以评价稳态 p95、GPU 并发、遮挡恢复或 IDSW/IDF1。

该结论仅是 2026-07-11 的 2 帧冒烟历史：当时尚未取得非零 accepted detection。后续已经完成 18-case 正式 screening，当前状态以本文顶部和 0.16 节为准。任何检测/MOT 改善仍不能让 tracker ID 生成、改写或换绑 `global_track_id`。

### 0.8 2026-07-11 M-to-N 三 seed 实施前基线

当时证据 `research_modules/airsim_runtime/outputs/blocks_cv_m5_n2_liveness_batch_20260711/M_TO_N_AIRSIM_CONVERGENCE_REPORT_CN.md` 覆盖 seeds 7/17/27。三组均为 6 次重规划请求、6 次无变化确认、0 次应用、0 次过期，需求满足率 1.0，错误重复锁定 0。T002 的视觉共识为 4/5/4，D7 每 seed 得到 2 次终端合同许可；T001 的两个 active primary 在当时计划和有效时间窗内没有形成连续两帧共同锁定，共识为 0。

实施前判断分为四层：P0 已闭合并保持 truth 隔离、保守身份和 ID 不变式回归；P1 的 M-to-N DTO、合法协同锁、两帧汇总、reserve standby 和快照过滤接口已完成；当时仍需完成 T001 共同可见和 SimpleFlight 分层验收；P2 的 OpenCV calibration/`solvePnP` 合成 benchmark 已完成。该判断已由 0.12 节当前结论取代。

当时实施顺序为：T001 双 primary ComputerVision 专项 -> 真实 YOLO/MOT 与几何扰动多 seed -> main/D7 SimpleFlight 长时段验证 -> P2 optional benchmark。当前已完成前述 10-seed 合同验收，后续以 0.12 节的控制/物理断点为准。D5 不修改 D7 PNG 公式，不降低版本、友方冲突、bbox 来源、稳定窗口或 `global_track_id` 安全约束。

### 0.9 D4 fallback coalition commit 消费实现

D5 已扩展 `CoalitionVisualSummary`、纯函数与 observation bus 薄封装，可选消费 duck-typed D4 commit。输入字段包括 commit state、epoch、lease expiry、coalition/plan id+version、required members、acked members，以及显式 `center_failed/fallback_active` 和评估时刻。中心正常且不提供 fallback commit 时完全保持现有中心合同；对 `k>1` fallback，一旦 commit 存在或中心/回退标记成立，只有 committed/executing、lease 有效、epoch 和双版本匹配、required member 集完整且全部 ACK 才允许 coalition consensus 与 active primary visual PNG authorization。

任何不满足均输出稳定的 `coalition_commit_*` conflict/reason，并保留当前 primary lock evidence、reserve readiness 和 cue policy 供 D4/D6 审计；reserve 不补 primary，不获得 PNG 权限。测试覆盖 T001 双 primary 同快照连续两帧、单 primary、reserve-only、旧 epoch、过期 lease、缺 ACK、版本冲突、未提交状态、center-failed 缺 commit、中心兼容和 truth metadata 隔离。当前 runtime 已验证二级接管与完全分布式完整 ACK commit 正例，以及缺 ACK fail-closed；该结果仍不能解释为物理拦截闭合。

### 0.10 P2 OpenCV calibration/solvePnP 扰动对照

新增隔离模块 `p2_geometry_benchmark.py` 和可执行 Python CLI。benchmark 使用既有 `CameraModel`/`GlobalTrack` 创建多视角合成标定板、非共面 3D PnP 点和运动目标；运行 `cv2.calibrateCamera` 与 `cv2.solvePnP`，分别注入相机中心平移、world-to-camera 旋转、measurement timestamp bias、nominal arrival latency 和 arrival timestamp bias。指标覆盖 calibration RMS/K 相对误差、PnP 重投影/位姿误差、pre/post/arrival 投影 RMSE、真目标 gate acceptance 和假候选 false acceptance。

该模块不被在线 D5 默认路径导入，不写回 `CameraModel`，不生成关联或绑定。`offline_truth_label` 在所有像素残差和马氏门控完成后才附加；测试确认仅更改 truth label 不改变任何指标。OpenCV calib3d 不可用时返回明确 unavailable。默认 seed 7 的合成结果约为 24.0 px -> 1.63 px、true accept 0.0 -> 1.0、false accept 1.0 -> 0.0；该数字只是离线算法对照，不代表真实相机、AirSim 或物理拦截。D5 全量现为 `143 passed`。

### 0.11 T001 primary 跨 plan-version 稳定延续

真实 AirSim 复验中，D3 role-aware 后 T001 primary 从 v1 到 v4 始终为 INT-02/INT-03，reserve soft feedback 仍触发计划单调升版。旧 D5 只接受与当前 binding 完全同版本的历史 association，导致每个 primary 的 `stable_lock_frame_count_by_resource` 在每次升版回到 1。

修正后，`TerminalObservationBus` 保存只读 binding snapshot 和 invalid-version state。当前 association 必须严格匹配当前 plan/coalition version；历史帧只在两个版本同时严格升高、owner/node、`coalition_id`、target/global ID、primary resource-target binding 集合、role、epoch、demand 和 authorization 全部不变，且没有 friend/duplicate/wrong-binding/expiry/commit conflict 时延续计数。合法 replan 可改变 plan ID 和 reserve member，但输出立即使用新 plan/coalition version，不接受 stale plan，不改写 `global_track_id`。相同/下降 coalition version、coalition ID 改变、primary 换员、target rebind、owner/epoch 冲突均清零。新增 metadata 可审计 continued resources、reset reason、source versions 和 stale resources。该机制已通过模块测试和 10-seed ComputerVision `8/10` 双 primary 合同验收。

### 0.12 2026-07-11 P1/P2 历史验收结论

该阶段证据为 `research_modules/airsim_runtime/outputs/p1_p2_validation_20260711/P1_P2_VALIDATION_SUMMARY_CN.md`。当时 P1 合同层结果为 ComputerVision 10 seeds 中 T001 双 active-primary 当前计划授权与视觉共识 `8/10`、错误 duplicate `0/10`；合法计划内协同多锁与错误重复锁保持分离。二级接管和完全分布式完整 ACK commit 正例通过，缺 ACK 场景阻断 D5 consensus/visual PNG authority 并 fail closed。该段不是 2026-07-13 的物理/视觉质量结论。

控制与物理结果仍开放。ComputerVision 的 `control_allowed_count=0`；SimpleFlight 15 s 只是断点诊断，30 个 active pair 均未命中，其中 24 个触发 `terminal_detection_timeout`。D5 后续只需围绕持续 detection、lock evidence 和 D7 gate blocker 提供可审计输入，不能把合同许可写成控制切换或物理命中。

P2 OpenCV calibration/`solvePnP` 仍为离线隔离 benchmark，不由在线关联、coalition summary 或 main/runtime 默认路径调用，不代表真实 AirSim PnP、在线外参更新或硬件标定闭合。

---

### 0.17 1080p 拦截相机与 4K 侦察相机混合分辨率

审计确认原有投影和检测适配器能读取每相机尺寸，但部分辅助像素项仍默认所有相机共享同一尺度。修复后，`ProjectionResult`、分布式视觉 observation/summary 和 YOLO/MOT 元数据显式携带 `image_size`；固定像素阈值以 `640x480` 为参考按图像对角线缩放。二级 detect 的 adaptive covariance 同步缩放 sigma 边界，跨视角 fallback 将中心、协方差和 bbox 面积转换到参考像素坐标再比较，避免同一目标在 1080p 与 4K 中因像素面积相差约 4 倍被误拒绝。

当前场景基线是拦截相机 `1920x1080`、高空侦察相机 `3840x2160`。YOLO/ByteTrack/BoT-SORT 仍按 `(resource_id, camera_id)` 隔离状态，真实 bbox 保持原像素记录；归一化只用于门限和跨视角代价。该实现阶段覆盖等价角度残差、1080p/4K covariance 缩放、混合分辨率跨视角关联和每流 bbox clipping，历史回归基线为 `204 passed`；2026-07-13 当日全量为 `232 passed`，2026-07-14 最新全量为 `241 passed`。D5 不读取 actor truth ID，也不改写全局绑定。

### 0.15 原生 MOT 准入与 per-primary 只读证据

D5 已把“能调用 Ultralytics tracker”和“允许原生 MOT 晋级”分离。`NativeMotAdmissionMonitor` 在每个 `(resource_id, camera_id)` 连续流上累计 native active rate、IoU fallback frames、accepted detections、去预热 P95 latency、local continuity、terminal local IDSW 和 offline detector TP/FP/FN、precision/recall；标准场景 metadata 支持 confidence `0.1/0.2/0.3` 与 20/30/50 m。ByteTrack、BoT-SORT 只有实际原生 local track ID 输出才计 native；IoU fallback 是可审计失败基线，不能通过 native admission。

时序边界已强化：`process_frame()` 无需 truth RPC，只在已完成 result 中保留无身份 detector boxes；main 随后取得 offline truth，再调用 `evaluate_offline_detector_after_online()` 或 `monitor.observe()`。后处理不会修改 result、local ID 或 global binding。旧 metadata 评分兼容保留；当 post-online truth 同时存在时只使用直接重算结果，legacy 不重复累计。离线 identity 只在该后处理阶段匹配 bbox 并累计 IDSW，任何 truth ID 都不进入输出 DTO。

`Assignment` 是 D5 已有的 D3 schema-v2 只读镜像，因此本轮直接增加 `terminal_authorization_scope` 和 `arrival_coordination_required`，而不是创建平行合同 DTO。字段名与 D3 一致，并经 registration binding、association metadata 和 runtime record 透传；旧调用缺字段时默认 `coalition + true`。main 的 adapter 只需从 D3 assignment/guidance binding 复制同名字段，不需要解析 metadata fallback。

`per_primary_terminal_evidence()` 只读检查一个 current primary，并直接使用 association DTO 合同。只有 `per_primary + arrival_coordination_required=false` 时，一个 primary 才可在另一个 primary 未同帧 locked 的情况下独立报告 visual lock；调用参数只作预期值核对，不能覆盖 association。该 evidence 明确不授予 control authority。plan/coalition 双版本、authorized/active primary、measured local track、friend/duplicate 和 execution gate 继续逐资源 fail closed；reserve standby 不得借此激活，`assigned_global_track_id` 只回显中心绑定。

模块单元测试覆盖 ByteTrack/BoT-SORT 正例、九组 confidence/distance metadata、fallback 拒绝、warmup latency、continuity、offline IDSW、post-online TP/FP/FN、result 不可变、legacy 兼容与防双计数、per-stream reset，以及 per-primary DTO 透传、旧默认、scope/arrival 组合、参数不可覆盖合同、reserve standby、当前 resource/global-track/plan/coalition binding、在线 truth 隔离与安全冲突。该实现轮次没有启动 AirSim，历史回归基线为 `200 passed`；后续正式 AirSim screening 已执行，当前结果见 0.16 节，2026-07-13 当日全量为 `232 passed`，2026-07-14 最新全量为 `241 passed`。

### 0.16 2026-07-13 原生 MOT 18-case 正式 screening 与 P1 判定

main 已完成固定前视相机、横向运动目标、`1920x1080`/FOV `90`、距离 `20/30/50 m`、confidence `0.1/0.2/0.3`、ByteTrack/BoT-SORT 的 `18`-case 正式 screening。20 m 两种后端的 native active rate/continuity 均为 `1.0`、IDSW 为 `0`，P95 约为 ByteTrack `7.4 ms`、BoT-SORT `16.2 ms`。这只证明 20 m 受控条件下 tracker 连续性和运行时延成立。

20 m 的离线 precision/recall 仅约 `0.26-0.33`，30/50 m 两种后端均无检测。当前不能在 bbox 定义差异、像素尺度/训练域不匹配和 online/reference 时间偏差之间唯一归因，也不能通过直接下调 IoU、confidence 或 D5 在线门限关闭缺口。

screening 准入候选为 `0`，因此 200 帧 two-camera confirmation 执行数为 `0`。ByteTrack 和 BoT-SORT 均未晋级，默认在线路径保持 AirSim `simGetDetections`；IoU fallback 仍只作为失败对照。

下一步先持久化并校正 online YOLO bbox、后到 AirSim reference bbox、measurement/reference timestamp、中心归一化误差、宽高/面积比和 containment，明确 bbox 口径/尺度/时间偏差；随后恢复 30/50 m 非零稳定召回。只有配置通过既定 screening 门槛后，才运行至少 10 seeds 的 confirmation。30/50 m 零检测时保持 fail closed。

离线 IoU sweep 与 D5 在线像素马氏门是不同合同。前者可用于确认 evaluator 的 bbox 约定，不能直接降低在线几何、唯一性、版本、友方、duplicate 和 authorization gate；AirSim truth 仍必须在 online result 形成后获取，只用于评分，不得回写 local track 或绑定 `global_track_id`。

### 0.13 P1 M5N2 双 primary 视觉协同诊断

D5 已增加只读 `summarize_cooperative_visual_funnel()`。它按中心拥有的 `global_track_id` 汇总动态数量资源与目标，不依赖固定 2v2/5v5 数组。每个资源-目标 binding 输出 current plan/coalition contract、visible、projected、geometry gate accepted、locked、连续锁定帧、共同锁定窗口参与、association confidence、ambiguity、friend conflict 和首个拒绝原因；每个目标输出 active-primary 漏斗、最长共同窗口、完成状态和第二 primary 首个失败阶段。

当前合同规则不变：只有当前双版本匹配、已授权激活的 primary 可计入完成；fallback 还需 D4 committed/executing、epoch、lease 和全成员 ACK；standby reserve 仅作 readiness/诊断，不进入完成率。local-only `TerminalObservation` 可说明“已看见但尚未投影”，不能因此创建或换绑全局 ID。actor/object/truth metadata 不进入诊断输出或身份决策。

模块测试覆盖不同视场、共同窗口不足、版本不一致、友方冲突、稳定共同锁定、动态资源/目标和缺 ACK；该实现阶段回归基线为 `181 passed`。main/D6 已在真实 M5N2 paired AirSim 中消费该 summary：120 条 active-primary/visible 证据中形成 74 条 D5 关联/锁定证据，最佳 coalition completion 为 5/10。开放 P1 是第二 primary 稳定锁定和 detection acquisition，不是 summary 接口接线；D5 不修改 D7 PNG、控制许可或物理命中判定。

### 0.14 pose-fix smoke 的 D5 根因复核

对四组 `p1_cooperative_closure_v2_posefix_smoke_20260712_*` 已按 frame 对齐控制、视觉和 main bus。T001 primary 集合变化 48-87 次，说明不少稳定窗口被有效的成员变更重置；视觉层本身也大量停在 `insufficient_best_second_margin` 或 `terminal_visual_evidence_expired`。`h020/w05/s040` 的 183 帧中有 25 帧两个 current primary 同时 locked，只有 18 帧二者均达到两帧稳定，不能把 `coalition_visual_incomplete` 简化为“相机完全看不见”。

发现并修复一个 D5 局部缺陷：单资源稳定状态允许在 owner、coalition、target、primary 集合和版本单调性全部安全时跨 plan version 延续，但 cooperative common-window 仍只接受当前版本，导致合法连续帧少计。修复后 common-window 从各资源已经认可的 source versions 中选择精确匹配 immutable binding 的证据，并裁剪到当前连续尾段。primary 换员、stale/non-monotonic version、owner/epoch/coalition/target 变化、friend/duplicate/expired evidence 继续 fail closed。新增 `primary_membership_transition` 和 `current_primary_failure_diagnostics`，后续真实输出可区分 contract、visible、projected、gate、locked、stable 各级首断点。

该 smoke 的强类型 `CameraGeometryEvidence` 全部显示 `camera_geometry_not_provided`，但 candidate logs 已有投影像素和马氏门控；这是历史证据透传问题，不允许 D5 用 AirSim actor/object truth pose 修补。后续重跑已经形成 120/120/74 漏斗和最佳 5/10 coalition completion，当前应继续标定第二 primary 获取与锁定，不再把“尚未重跑”列为权威缺口。

## 1. 研究问题

### 0.4 真实 AirSim M=5、N=2 检测/几何历史复核

`blocks_cv_m5_n2_cooperative_live_20260711` 已证明 7 路相机出图和 D3 schema v2 联盟字段可进入 full flow，但没有证明 D5 可锁定：full-flow 为 32 次 `reacquire`、4 次 `ambiguous`、0 次 `locked`。主要断点发生在 D5 前的 `simGetDetections`，绝大多数 camera-frame 返回空列表。

唯一 `Secondary_Recon_1` bbox 的同相机离线复算结果为：`T002` projected pixel 与 bbox center 相差约 0.09 px，D5 几何选择正确；由于只有单帧、MOT history=1，保守输出 `ambiguous`。现有 18-78 px 汇总混入了 main runtime 的跨相机 fallback，不应解释为 D5 外参公式失效或据此放宽 `gate_chi2`。main 应先修正 per-resource camera scope，再用 `Quadrotor1*`/actor exact filter 和 pose-update warm-up 重跑。

边界保持不变：D5 不读取 online truth ID，不根据该唯一 bbox 改绑 `global_track_id`，也不把二级相机 detection 当作任意主资源的本地 MOT。该段是实施前诊断，不能继续用这里的 0 lock 描述现状；2026-07-11 的 `8/10` 是合同层历史结果，2026-07-13 最新 M5N2 实测为 120/120/74 漏斗和最佳 coalition completion `5/10`。

### 1.0 M 对 N 高威胁目标的计划内多机锁定

2026-07-11 专项调研已形成 `D5_M_TO_N_TERMINAL_MULTIVIEW_REVIEW.md`，并已完成 D3 schema v2 联盟锁合同。`Assignment`、`GlobalTrackBinding`、`TerminalAssociation` 和 `CrossViewAssociation` 保留联盟/计划版本、成员角色、波次、需求数、协同模式、arrival window 与 activation state。`k_j>1` 时，同一已授权激活联盟内且不超过 demand 的多个 lock 输出 `planned_cooperative_lock`，不设置 `duplicate_terminal_lock_risk`；第四个超额 lock、联盟/版本不一致、scope 不符和 local/global 多重绑定仍冲突。

错误 duplicate 仍包括计划外资源加入、单资源多本地轨迹锁定、单一本地轨迹支持多个全局目标、stale plan、友方冲突和跨视角几何不一致。同步观测可用于带权三角化；序贯观测必须按量测时间运动补偿并膨胀协方差。像素位置和 bbox 尺度历史只作关联辅助，不能独立提供三维尺度或创建新全局身份。

未激活 `reserve/retry` 即使已形成视觉可锁候选，也只输出 `hold`、`execution_gate_reason` 和 D7 visual PNG blocker；active primary wave-0 与 k=1 回归保持正常。每个 resource-camera 仍独立执行 GlobalTrack 投影与 local MOT，D5 不形成联盟、不重新分配、不裁减超额资源。带权三角化、PDOP/可观测度和融合协方差仍是后续协同定位研究范围；论文与代码成熟度分级以专项报告为准。

末端视场中“最近目标”不一定是分配目标。局部相机可能同时看到：

- 中心分配的目标；
- 其他来袭目标；
- 友方资源节点；
- 空中侦察无人机；
- 未知或无关飞行物。

如果局部节点自行换绑 `global_track_id`，会造成重复分配、漏分配、ID Switch 或友方安全风险。因此末端节点只能输出 `TerminalAssociation`，不能直接改写中心分配。

### 1.1 多无人机重叠视场问题

阶段一 AirSim Blocks 或后续离线回放中，会出现多个拦截无人机同时观察同一空域但视场不完全重叠的情况。例如：

```text
UAV1 camera sees: target 1, target 2, target 3
UAV2 camera sees: target 2, target 3, target 4
```

这里 `UAV1` 和 `UAV2` 都可能生成 `local_track_id="L2"`，但它们只是各自相机/MOT 内部的本地编号，不能用字符串相等判断是否为同一目标。D5 必须把本地轨迹限定在 `(resource_id, camera_id, frame_id, local_track_id)` 命名空间下，再通过 D2 提供的 `GlobalTrack`、相机投影、时间戳、姿态和协方差门控，将本地观测配准到既有 `global_track_id`。

单视角目标不是错误：目标 1 只出现在 UAV1，目标 4 只出现在 UAV2，可能是视场边界、遮挡或距离造成的正常现象。D5 不能因为另一个视角未观察到目标就删除航迹或判定分配错误，只能降低跨视角一致性置信度，必要时输出 `hold/reacquire/ambiguous`。

---

## 2. 文献综述要点

局部 MOT 方面，ByteTrack 通过高低置信检测两阶段关联提升召回率，适合短时遮挡和小目标跟踪；BoT-SORT 加入相机运动补偿和 ReID，更适合运动相机；Deep SORT 使用深度外观特征，能降低 ID Switch，但无人机视角下目标小、模糊、逆光和外观相似会导致退化。

几何配准方面，OpenCV 标定、`solvePnP/projectPoints` 和 ROS 2 `tf2` 是默认工具链。核心不是全图识别，而是把 `GlobalTrack` 预测位置投影到相机平面，生成几何门限，再与 `LocalVisualTrack` 做关联。

身份认证方面，Remote ID/OpenDroneID、MAVLink signing、DDS Security 和任务内协同 ID 都只能正向确认友方或协同方。未知目标不能自动等同于敌方。AprilTag 等视觉标签可用于实验室合作目标，但不能作为复杂环境中的唯一身份依据。

---

## 3. 开源代码选型

| 工具 | 用途 | 适用性 |
|------|------|--------|
| ByteTrack | 局部MOT默认基线 | 小目标短时遮挡较稳，但不负责全局身份 |
| BoT-SORT | 运动相机MOT | 有相机运动补偿，适合资源节点视角 |
| Deep SORT | 外观辅助MOT | 纹理足时有效，低分辨率会退化 |
| OpenCV Calibration/solvePnP | 相机标定和投影 | 几何配准核心 |
| ROS 2 tf2 | 坐标变换 | 维护世界系、机体系、相机系 |
| OpenDroneID | Remote ID实现 | 仅作身份声明证据 |
| MAVLink signing / DDS Security | 消息来源认证 | 需与任务清单交叉验证 |
| AprilTag | 合作视觉标识 | 近距实验辅助 |

### 3.1 当前实际接入状态

当前仓库内 D5 只接入了轻量、可离线复现的几何和证据层，不应把上表开源项理解为已经完整工程化：

| 项目 | 当前状态 |
|------|----------|
| OpenCV `projectPoints` | 已用于单相机在线主线投影；隔离式 P2 已增加合成 `calibrateCamera`/`solvePnP` 扰动 benchmark。当前仍不做真实标定采集、PnP RANSAC、在线外参更新或 bundle adjustment。 |
| AirSim `simGetDetections` | 已有 dry-run bbox adapter，兼容 `box2D`、`bbox_xyxy`、`xyxy` 等 fixture/schema。在线转换忽略 `object_id`、`actor_name`、actor truth ID，并过滤与这些 truth/actor 字段同值的 `track_id/detection_id`。本轮二级节点优先使用该输入口径。 |
| YOLOv8 / ByteTrack | 已有离线 schema adapter 和 `YoloMotAdapter` frame adapter。fallback/native tracker state 按 `(resource_id, camera_id)` 隔离，提供 `reset_stream()` / `reset_all_streams()`；native `persist=True` 使用每 stream 独立 model/tracker，缺依赖/原生 tracker 时退回 per-stream IoU tracker。metadata 记录 stream key、backend/scope、confidence、class id、bbox area/scale 和 CPU/GPU budget；在线转换忽略 truth/global 字段，tracker ID 只作为 `LocalVisualTrack.local_track_id`。 |
| Multi-seed calibration readiness | 已有 `summarize_multiseed_calibration_readiness()`，对 D5 输出的 `TerminalObservation` 与 `CrossViewAssociation` 做字段覆盖审计，标出每个 seed 缺少的 required/recommended 报告字段。truth label 只从离线 metadata 计数，不进入在线关联。 |
| Secondary coverage/funnel diagnostics | 已有 `summarize_secondary_visual_coverage_funnel()`，对普通 replay frame、`TerminalObservation` 和 `CrossViewAssociation` 输出二级覆盖率、联合覆盖率、detect 到 multi-support 漏斗和断点原因。offline target label 只用于覆盖统计，不参与在线绑定。 |
| Mobile high-recon gimbal cue evidence | 已有 `ReconImageCue` 字段和 coverage/cross-view summary metadata，可记录 `cue_position_ned`、`look_at_ned`、云台指向元数据、cue pointing error、gimbal track error、`radar_global_track_cue`、`mobile_high_recon` 和 `mobile_recon_gimbal`；测试覆盖固定俯视不足时机动云台改善二级网络联合覆盖。 |
| BoT-SORT / Deep SORT | `YoloMotAdapter` 可请求 ultralytics BoT-SORT；Deep SORT/ReID 仍作为未来对照。BoT-SORT/Deep SORT 的小目标质量、遮挡恢复、IDSW/IDF1 和算力预算仍需真实图像链路后评估。 |
| ROS 2 `tf2/message_filters` | 只是未来坐标变换和时间同步方案；D5 当前不启动 ROS graph，不订阅 topic。 |
| OpenDroneID / MAVLink signing / DDS Security | 仅通过 `IdentityClaim` 抽象表达仿真身份声明；未接真实报文、密钥、证书或白名单。 |
| AprilTag | 仅作为未来实验室合作目标标识方案；当前没有图像 detector 或 tag ID 到平台身份的可信映射。 |
| Distributed visual association | 已实现 P0 metadata-only DTO 与 `TerminalCrossViewFusion`，输出 peer evidence；未实现三维重投影、三角化或跨相机联合优化。 |

---

## 4. 处理链路

目标工程链路如下，其中 `tf2`、ByteTrack/BoT-SORT/Deep SORT 是预期上游能力，不是当前 D5 代码内已运行组件：

```text
AssignmentPlan.assigned_global_track_id
-> GlobalTrack按measurement_timestamp预测
-> tf2转换到camera_frame
-> OpenCV投影到图像平面
-> 生成几何门限
-> ByteTrack/BoT-SORT/Deep SORT生成LocalVisualTrack
-> Hungarian/JPDA匹配LocalVisualTrack与GlobalTrack
-> IdentityClaim做友方正向确认
-> 输出 locked | ambiguous | hold | reacquire
```

当前已实现的 P0 路径是：

```text
Assignment.assigned_global_track_id
-> D2 GlobalTrack + CameraModel
-> projectTracksToImage / cv2.projectPoints fallback
-> LocalVisualTrack[]  # 来自 fixture、AirSim bbox adapter 或外部 detector/tracker schema
-> TerminalAssociator.decide()
-> TerminalAssociation
-> TerminalObservationBus / TerminalCrossViewFusion / TerminalConsistencySummary
```

在线 D5 禁止使用 AirSim `object_id`、`actor_name` 或 actor truth ID。truth ID 只允许作为离线评分标签，计算 `terminal_lock_accuracy`、`locked_mismatch` 或测试断言。

### 4.1 多视角跨视场处理链路

多视角情况下，D5 需要在“单机终端关联”之外增加一个被动跨视场汇总层。该层不分配目标，只把多个局部视觉证据配准到中心/二级节点已有的 `global_track_id`。

```text
UAV1 LocalVisualTrack[]
UAV2 LocalVisualTrack[]
...
-> TerminalObservationBus按(resource_id, camera_id, frame_id, local_track_id)汇聚
-> 对每个GlobalTrack按各相机measurement_timestamp预测
-> 用每个相机的CameraModel把同一GlobalTrack投影到对应图像平面
-> 每个相机内做像素马氏门控和候选代价排序
-> 跨视角合并同一global_track_id的支持证据
-> 输出CrossViewAssociation / TerminalConsistencySummary
```

完全无中心时，当前 P0 metadata-only 链路为：

```text
DistributedVisualObservation[]
+ VisualTrackletSummary[]
+ PeerCameraState[]
-> TerminalCrossViewFusion.build_hypotheses()
-> CrossPeerAssociationHypothesis
-> DistributedTerminalAssociation
-> D4/D6 distributed evidence
```

该链路基于时间窗口、bearing/center_px、bearing rate、bbox area/scale rate、类别/置信度、像素协方差和姿态协方差匹配 peer 视觉 tracklet。缺失或 stale `assigned_global_track_id` 输出 `hypothesis_only/hold`；重复锁定、友方冲突、local/global ID 冲突输出 `hold/ambiguous`。D5 不创建全局 ID，不分配资源。

核心原则：

- `local_track_id` 不跨资源共享语义，只是局部观测编号。
- `global_track_id` 只能来自 D2/D3/D4 的全局航迹和分配计划。
- 一个 `global_track_id` 可以被多个视角同时支持，也可以暂时只有单视角支持。
- 跨视角证据冲突时输出 `ambiguous/conflict/mismatch`，不得由 D5 本地改写 `global_track_id`。

### 4.2 示例：UAV1 sees {1,2,3}, UAV2 sees {2,3,4}

假设 D2 当前维护四条全局航迹：

```text
G1 -> target 1
G2 -> target 2
G3 -> target 3
G4 -> target 4
```

UAV1 的局部 MOT 输出：

```text
UAV1/front/L_a, UAV1/front/L_b, UAV1/front/L_c
```

UAV2 的局部 MOT 输出：

```text
UAV2/front/L_a, UAV2/front/L_b, UAV2/front/L_c
```

即使两个无人机都出现 `L_a/L_b/L_c`，这些 ID 也不能直接比较。正确流程是：

1. 对 `G1/G2/G3/G4` 分别投影到 UAV1 相机平面。
2. 对 `G1/G2/G3/G4` 分别投影到 UAV2 相机平面。
3. UAV1 内部用投影门控判断 `{L_a,L_b,L_c}` 对应 `G1/G2/G3` 的候选代价。
4. UAV2 内部用投影门控判断 `{L_a,L_b,L_c}` 对应 `G2/G3/G4` 的候选代价。
5. 对共享目标 `G2/G3`，合并 UAV1 和 UAV2 的支持证据：若两个视角都在门内、时间差可接受、姿态协方差可接受、候选 margin 足够，则提高 `G2/G3` 的跨视角一致性置信度。
6. 对单视角目标 `G1/G4`，保持单视角置信，不因另一架无人机未观察到而判错。若该资源被分配到对应目标，可继续由本资源做单机 `TerminalAssociation`；若投影不可见或候选缺失，则输出 `reacquire`。
7. 若 UAV1 和 UAV2 都对同一个 `global_track_id` 输出 `locked`，但 D3/D4 只允许一个主资源负责该目标，则 D5 只上报“重复锁定风险”，由 D3/D4 仲裁，D5 不自行取消或换绑任一资源。

避免重复锁定同一目标的建议：

- D5 输出 `TerminalAssociation` 时携带 `resource_id`、`assigned_global_track_id`、`local_track_id`、`decision_state` 和 `association_confidence`。
- 跨视场层输出 `CrossViewAssociation`，记录同一 `global_track_id` 被哪些资源支持。
- 若多个资源同时 `locked` 同一 `assigned_global_track_id`，且 AssignmentPlan 不允许多资源协同，则输出 `duplicate_terminal_lock_risk` 给 D4/D3。
- D3/D4 根据计划版本、资源状态、视场质量和任务优先级决定保留哪个资源为主，其他资源降为观察/备份；D5 不直接改分配计划。

---

## 5. 数据结构

当前 `LocalVisualTrack` 保持单相机本地检测/MOT 输出的轻量结构，跨资源命名空间由 `TerminalObservationBus` 或 distributed DTO 提供；不要把 `local_track_id` 字符串直接跨无人机比较。

```text
LocalVisualTrack
- local_track_id
- bbox
- center_px
- bearing_rate
- mot_history_length
- timestamp
- quality

TerminalAssociation
- assigned_global_track_id
- local_track_id
- association_confidence
- ambiguity_score
- friend_conflict_state
- decision_state: locked | ambiguous | hold | reacquire
- assignment_version

IdentityClaim
- platform_id
- claim_type: cooperative_id | remote_id | visual_tag
- auth_state: verified | stale | unverified | spoof_suspected
- associated_track_id
- timestamp
```

已实现跨视场摘要结构：

```text
TerminalObservation
- resource_id
- source_node_id
- link_type
- timestamp
- arrival_timestamp
- camera_id
- frame_id
- local_track
- terminal_association
- identity_claims
- recon_image_cues

CrossViewAssociation
- global_track_id
- supporting_resource_ids
- local_track_ids  # resource/camera:local_track_id
- ambiguity_score
- duplicate_terminal_lock_risk
- support_count
- duplicate_lock_resource_ids
- duplicate_local_track_ids

TerminalConsistencySummary
- resource_id
- assigned_global_track_id
- decision_state
- association_confidence
- ambiguity_score
- friend_conflict_state
- candidate_cost_margin
- recon_cue_used
- mismatch_with_assignment
- recommended_d4_action: observe | request_secondary_cue | report_conflict | arbitrate
```

已实现完全分布式 P0 metadata-only 结构：

```text
DistributedVisualObservation
- resource_id / camera_id / frame_id / local_track_id
- measurement_timestamp / arrival_timestamp
- center_px or bearing
- covariance_px or covariance
- bbox / bearing_rate / category / confidence
- assigned_global_track_id / assigned_global_track_stale
- friend_conflict_state

VisualTrackletSummary
- resource/camera/local_track namespace
- bbox_area / scale_rate / observation_count
- assigned_global_track_ids / stale_assigned_global_track_ids

PeerCameraState
- resource_id / camera_id / frame_id
- pose_covariance
- optional position_ned / orientation_quat_xyzw

CrossPeerAssociationHypothesis
- participant_tracklet_keys
- supporting_resource_ids
- support_state
- duplicate_terminal_lock_risk
- global_track_id_conflict / local_id_conflict

DistributedTerminalAssociation
- decision_state: locked | ambiguous | hold | hypothesis_only
- assigned_global_track_id
- supporting_resource_ids
- local_track_ids
- recommended_d4_action

CalibrationSeedReadiness / MultiSeedCalibrationReadiness
- seed_id / ready / missing_required_fields / missing_recommended_fields
- source_counts / detector_backend_counts / tracker_backend_counts
- geometry_log_count / measurement_age_count / local_bbox_count
- truth_label_count / handoff_advisory_count / bbox_stability_count
- duplicate_terminal_lock_risk_count / friend_conflict_count

SecondaryVisualCoverageFunnelSummary
- secondary_single_camera_full_view_frame_rate
- secondary_network_joint_full_view_frame_rate
- secondary_camera_frame_visible_target_counts
- secondary_network_frame_joint_visible_target_counts
- secondary_single_camera_coverage_ratio_mean / min
- secondary_network_joint_coverage_ratio_mean / min
- funnel_counts.detect_count / local_or_recon_cue_count
- funnel_counts.terminal_association_count / cross_view_association_count / multi_support_count
- rejection_reason_counts
- metadata.coverage_mode_counts / capability_class_counts / cue_source_counts
- metadata.mobile_recon_gimbal_improved_joint_coverage_frame_count
- metadata.mobile_recon_gimbal_added_target_ids_by_frame
- metadata.cue_pointing_error_m_by_camera_frame / cue_pointing_error_rad_by_camera_frame
- metadata.gimbal_track_error_px_by_camera_frame

ReconImageCue mobile gimbal fields
- cue_position_ned / look_at_ned
- gimbal_pointing_metadata
- cue_pointing_error_m / cue_pointing_error_rad
- gimbal_track_error_px
- cue_source / capability_class / coverage_mode
```

后续真实多相机三维几何融合仍可新增 `CrossViewObservation/CrossViewTrackEvidence`，携带完整 `CameraModel`、三维候选、重投影残差和协方差摘要；该扩展仍不能改变 D5 不改写 `global_track_id` 的边界。二级覆盖诊断中，`visible_target_ids`/覆盖比例只是离线可见性，`secondary_network_joint_full_view_frame_rate` 是网络并集覆盖，`cross_view_association_count`/`multi_support_count` 才是已形成全局 ID 支持。`mobile_recon_gimbal_improved_joint_coverage_frame_count` 只说明机动云台 evidence 补足固定俯视覆盖，不是 D5 获得云台控制或分配权限。

---

## 6. 匹配代价

```text
terminal_association_cost =
    image_projection_error
  + los_rate_consistency_error
  + timestamp_latency_penalty
  + track_covariance_penalty
  + mot_history_penalty
  + class_mismatch_penalty
  + friend_identity_conflict_penalty
```

只有候选唯一、代价差距明显、无友方冲突且版本匹配时，才能进入 `locked`。

跨视角时，单视角代价先独立计算，再做全局航迹级证据合并：

```text
cross_view_cost(global_track_id) =
    sum(valid_view_costs)
  + timestamp_skew_penalty
  + camera_pose_uncertainty_penalty
  + missing_view_penalty_if_expected_visible
  + duplicate_lock_risk_penalty
```

注意 `missing_view_penalty_if_expected_visible` 只能在几何上确认目标应在该相机视场内时使用。若目标本来就在视场外，不能因为缺失观测惩罚该 `global_track_id`。

---

## 7. 决策伪代码

```python
def terminal_association(global_track, assignment, local_tracks, claims):
    if assignment.assigned_global_track_id != global_track.global_track_id:
        return TerminalAssociation(decision_state="hold")

    gate = project_global_track_to_image(global_track)
    candidates = []

    for local in local_tracks:
        if not inside_projection_gate(local, gate):
            continue
        cost = projection_cost(local, gate)
        cost += los_rate_cost(local, global_track)
        cost += identity_conflict_cost(local, claims)
        candidates.append((cost, local))

    best, margin = select_unique_candidate(candidates)
    friend_state = evaluate_positive_friend_claim(best, claims)

    if friend_state == "friend_conflict":
        return TerminalAssociation(decision_state="hold")
    if best is None:
        return TerminalAssociation(decision_state="reacquire")
    if margin < MIN_MARGIN:
        return TerminalAssociation(decision_state="ambiguous")

    return TerminalAssociation(decision_state="locked")
```

### 7.1 跨视场汇总伪代码

```python
def cross_view_association(global_tracks, observations_by_resource, cameras, assignment_plan):
    cross_view_results = []

    for global_track in global_tracks:
        supports = []
        conflicts = []

        for resource_id, local_tracks in observations_by_resource.items():
            camera = cameras[resource_id]
            predicted = predict_to_measurement_time(global_track, camera.timestamp)
            projection = project_global_track_to_camera(predicted, camera)

            if not projection.valid:
                continue

            candidates = gate_local_tracks(local_tracks, projection)
            best = select_best_candidate(candidates)

            if best.is_friend_conflict:
                conflicts.append((resource_id, best.local_track_id))
            elif best.is_valid:
                supports.append((resource_id, best.local_track_id, best.cost))

        if conflicts:
            state = "conflict"
        elif len(supports) >= 2:
            state = "consistent"
        elif len(supports) == 1:
            state = "single_view_supported"
        else:
            state = "unknown"

        cross_view_results.append(
            CrossViewAssociation(
                global_track_id=global_track.global_track_id,
                supporting_observations=supports,
                consistency_state=state,
            )
        )

    duplicate_risks = detect_duplicate_terminal_locks(cross_view_results, assignment_plan)
    return cross_view_results, duplicate_risks
```

`single_view_supported` 不是错误状态。它表示当前只有一个视角提供有效证据，需要结合 D2 航迹质量、相机视场覆盖和 D4/D3 分配计划判断是否足够。

---

## 8. 失败案例测试

| 场景 | 期望状态 |
|------|----------|
| 最近目标不是分配目标 | 锁定投影门内匹配目标，不抢绑最近目标 |
| 短时遮挡 | `hold -> reacquire` |
| Remote ID匹配但签名失败 | `ambiguous/hold` |
| AprilTag可见但投影残差异常 | 拒绝身份提升 |
| 外参偏移 | 投影门失败并记录校准告警 |
| 时间戳延迟 | 预测补偿后再匹配 |
| 两候选代价接近 | `ambiguous`，不上报锁定 |
| UAV1/UAV2 本地ID同名 | 不按 `local_track_id` 字符串合并，必须使用 `(resource_id,camera_id,local_track_id)` |
| 目标2/3被两个视角看到 | 合并为对同一 `global_track_id` 的多视角支持证据 |
| 目标1/4仅单视角可见 | 保持单视角置信，不判为错误 |
| 两资源同时锁定同一目标 | 上报 `duplicate_terminal_lock_risk` 给 D4/D3 仲裁 |
| 二级cue未重投影 | 不得用于本机 `LocalVisualTrack.center_px` 代价计算 |
| AssignmentPlan与末端视觉不一致 | 输出 `mismatch/ambiguous`，触发D4仲裁，不本地换绑 |

---

## 9. 与 D4 主动降级的仲裁接口

D5 是 D4 主动降级的重要观测源，但不是降级决策者。D4 需要判断中心/二级节点分配与末端视觉证据是否一致，并可把 D5 的 distributed evidence 作为 CBBA/分布式仲裁风险加权输入：

| D5 输出 | D4 含义 | 建议动作 |
|---------|---------|----------|
| `locked` 且 `assigned_global_track_id`/版本一致 | 分配与末端视觉一致 | 继续当前计划 |
| 多帧 `ambiguous` | 末端证据不足或候选接近 | 请求二级侦察 cue 或延长观测 |
| `hold` + `verified_friend_overlap` | 友方/合作目标重叠 | 上报冲突，不自动换绑 |
| 多帧 `reacquire` | 当前 pair 无法确认分配目标 | 请求 secondary cue/reacquire；不产生资源失效或 hard planner 语义 |
| `mismatch_with_assignment=True` | 本地最佳视觉证据长期不支持当前 AssignmentPlan | D4 仲裁中心/二级节点分配 |
| `duplicate_terminal_lock_risk=True` | 多资源可能重复锁定同一目标 | D4/D3 调整主备资源或计划版本 |
| `DistributedTerminalAssociation.decision_state="hypothesis_only"` | peer 视觉证据存在但缺少 current global ID 或单视角不足 | 观察或请求 D2/D3/D4 更新，不让 D5 本地建 ID |
| `DistributedTerminalAssociation.decision_state="hold/ambiguous"` | stale ID、重复锁定、友方冲突、global/local ID 冲突或跨 peer 置信不足 | 仅当 action 为 `report_conflict/arbitrate` 时进入 hard 仲裁；`observe/request_secondary_cue` 保持 pair 级视觉不确定性 |

主动降级触发建议使用连续帧统计，避免单帧检测噪声导致抖动：

- `consecutive_ambiguous_frames >= 5`：请求二级节点 cue 或继续观测。
- `consecutive_hold_frames >= 2` 或 `consecutive_reacquire_frames >= 5`：请求二级线索/重获取，不由 D5 触发 hard 仲裁；D1/D2/D3 可基于自身独立风险另行决策。
- `friend_conflict_state="verified_friend_overlap"` 连续出现：上报冲突并保持 `hold`。
- 同一 `global_track_id` 被多个资源 `locked` 且计划不允许多资源协同：上报重复锁定风险。

2026-07-07 代码状态：`TerminalConsistencyTracker` 的连续窗口按 `resource_id + assigned_global_track_id` 维护，`assignment_version` 只作为摘要审计字段输出，不作为窗口 key。因此 D3 对同一资源/目标滚动发布新的 plan version 时，不会清空 D5 的连续 `ambiguous/hold/reacquire/locked` 计数；只有 `assigned_global_track_id` 实际变化才进入新的窗口。

无论 D4 是否决定降级到二级节点或分布式协商，D5 都只能输出视觉配准、身份确认和 advisory summary，不得直接生成新 `AssignmentPlan`，不得选择主备资源，不得触发降级动作，不得改写 `global_track_id`。

---

## 10. 与 D7 视觉比例导引/LOS 的接口

D7 负责末端视觉比例导引或 LOS 角速率导引时，必须以 D5 的保守锁定结果为前置条件。接口原则：

1. 只有 `TerminalAssociation.decision_state == "locked"`，且 `assigned_global_track_id` 与 D3/D4 当前 AssignmentPlan 一致时，D7 才能考虑该视觉目标作为 `visual PN / LOS` 输入。
2. 视觉 PNG 切换还必须满足 bbox 连续稳定、无友方冲突、无重复终端锁定风险、LOS rate 可用、measurement age 新鲜、检测延迟与机动裕度可接受，并通过 D4/D3 gate。
3. D7 输入应包含 `assigned_global_track_id`、`resource_id`、`local_track_id`、图像中心、LOS 角速率、时间戳、置信度和 D5 handoff/prelock metadata。
4. 若 D5 输出 `ambiguous/hold/reacquire/hypothesis_only/mismatch`，或 `annotate_visual_png_handoff()` 给出 `assignment_mismatch`、`duplicate_terminal_lock_risk`、`bbox_area_unstable`、`measurement_age_stale`、`los_rate_unavailable` 等阻断原因，D7 只能进入保持、继续观测或等待上级计划更新的状态，不能自行选择另一个本地目标。
5. D7 严禁根据本地相机“更近”或“更清晰”的目标直接改绑 `global_track_id`。
6. 若二级侦察 cue 参与锁定，D7 应记录 `recon_cue_used=True`，用于 D6 评估 cue 依赖和误锁风险。

推荐 D5 -> D7 消息：

```text
VisualLockForGuidance
- resource_id
- assigned_global_track_id
- assignment_version
- local_track_id
- decision_state == locked
- center_px
- bearing_rate
- association_confidence
- measurement_timestamp
- measurement_age_s
- visual_png_handoff_blockers
- camera_id / frame_id
- recon_cue_used
```

该消息不是处置授权，也不是新的分配计划，只是 D7 视觉导引模块的离线仿真输入合同。

---

## 11. AirSim Blocks 当前实现约束

AirSim Blocks 阶段一适配应保持离线/仿真边界：

- 视觉输入优先来自 `simGetDetections` 或离线检测器/tracker 输出的检测框，再归一化为 `LocalVisualTrack`；D5 已提供 `YoloMotAdapter.process_frame()`，按 `(resource_id, camera_id)` 隔离 fallback/native 状态，依赖、权重或原生 tracker 不可用时返回 `unavailable` 或退回 per-stream IoU tracker。main 必须保持 stream key 稳定，单相机重启调用 `reset_stream()`，episode 边界调用 `reset_all_streams()`；真实 AirSim 连续图像流已接入 18-case screening，剩余是 bbox/时间口径、30/50 m 召回、GPU/CPU 长期预算和候选多 seed confirmation。
- 相机输入必须包含相机内参、相机位姿、图像时间戳和图像尺寸，转换为 D5 `CameraModel`。
- AirSim 默认不要求保存 PNG。若主程序选择保存图像，只能作为离线复盘和可视化，不应成为 D5 逻辑依赖。
- `actor/object_name` 可以作为仿真真值辅助评估 `association_correct`，用于 D6 指标计算和测试断言。
- 正式 D5 关联逻辑不能依赖 `actor/object_name`、`truth_id` 或 `global_track_id` 输入字段作弊。运行时配准必须基于 `GlobalTrack` 投影、局部检测框、时间戳、相机姿态、协方差门控、身份声明和 cue。
- Blocks 中同一目标在不同相机下可能产生不同检测框和本地 ID，必须通过 `global_track_id` 投影门控和跨视角证据合并处理。
- 不调用 AirSim 控制 API，不输出控制量、拦截点、毁伤判断或自动处置动作。

建议阶段一 dry-run 输入：

```text
AirSim detection bbox
-> LocalVisualTrack(resource_id, camera_id, frame_id, center_px, bbox, timestamp)

Offline YOLO/ByteTrack row
-> LocalVisualTrack(local_track_id namespaced by camera/source tracker id)

YOLO/MOT frame
-> YoloMotAdapter.process_frame(...)
-> LocalVisualTrack(local_track_id namespaced by camera/source tracker id)

AirSim camera metadata
-> CameraModel(K, R_cw, t_cw, image_size, measurement_cov)

D2 GlobalTrack
-> project into each camera frame

optional actor/object_name
-> evaluator-only truth label, never used in association decision
```

---

### 11.1 当前 P1 补齐状态与剩余聚焦

D5 侧 P1 已补齐项包括：M-to-N 双 primary 合同、合法协同多锁与错误 duplicate 分离、commit-aware state/epoch/lease/双版本/member ACK gate、受控跨版本稳定延续、geometry log fields、detect-to-global outcome/reject reason、registration covariance/timestamp、`TerminalConsistencySummary` 连续窗口、D4 frame-scoped evidence DTO、D7 visual PNG handoff/prelock blockers、AirSim truth ID 在线隔离、YOLO/MOT adapter、multi-seed readiness、二级覆盖/漏斗和 mobile high-recon gimbal cue。2026-07-11 的 10-seed CV 双 primary `8/10` 是合同层历史结果；2026-07-13 最新 M5N2 质量结果为 120/120/74 漏斗和最佳 `5/10`。二级/完全分布式完整 ACK commit 和缺 ACK fail-closed 均已验证。上述输出都是 evidence 或 adapter，不赋予 D5 分配、授权、降级、云台控制或导引控制权。

P0 状态：无 blocker。active reacquire 友方声明复检、detection category/truth 隔离、sim-detection actor alias 过滤和端到端 AirSim actor-name local ID 隔离均已闭合；证据路径为 `research_modules/airsim_runtime/outputs/p0_truth_isolation_smoke_20260710`。D5 不分配、不授权、不改写 `global_track_id`，在线逻辑不得使用 AirSim truth ID。

P1 合同层已经闭合；剩余 P1 为 M5N2 第二 primary、真实几何 drift、detect/YOLO/MOT 多 seed 和二级同 tick freshness。P2 保留 Deep SORT/ReID、真实身份源和完整在线 PnP/硬件级三维标定；IBVS 与 ROS 2 `tf2/message_filters` 保持 P3 optional。任何增强均不得放宽唯一性、友方冲突、版本、时效或 D7 独立 camera/LOS/maneuver gate；在线 D5 仍不得使用 truth ID 或 tracker ID 生成、改写、换绑 `global_track_id`。

---

## 12. 交付物

1. 末端MOT、几何投影、友方认证综述。
2. ByteTrack、BoT-SORT、Deep SORT、OpenCV、tf2、OpenDroneID适用性评估。
3. `LocalVisualTrack`、`TerminalAssociation`、`IdentityClaim` 数据结构。
4. 匹配代价和保守决策逻辑。
5. 模拟相机投影与歧义场景测试用例。
6. 多视角 `CrossViewObservation/CrossViewAssociation` 接口建议。
7. D4 主动降级仲裁信号和 D7 视觉导引输入合同。
8. AirSim Blocks 检测框/相机元数据离线适配约束。

---

## 13. 参考资料

- ByteTrack: <https://github.com/FoundationVision/ByteTrack>
- BoT-SORT: <https://github.com/NirAharon/BoT-SORT>
- Deep SORT: <https://github.com/nwojke/deep_sort>
- OpenCV camera calibration: <https://docs.opencv.org/4.x/dc/dbb/tutorial_py_calibration.html>
- OpenCV `solvePnP`: <https://docs.opencv.org/4.x/d5/d1f/calib3d_solvePnP.html>
- ROS 2 tf2: <https://docs.ros.org/en/rolling/Concepts/Intermediate/About-Tf2.html>
- FAA Remote ID: <https://www.faa.gov/uas/getting_started/remote_id>
- OpenDroneID Core C: <https://github.com/opendroneid/opendroneid-core-c>
- MAVLink message signing: <https://mavlink.io/en/guide/message_signing.html>
- ROS 2 DDS Security: <https://design.ros2.org/articles/ros2_dds_security.html>
- AprilTag: <https://github.com/AprilRobotics/apriltag>

## 14. 2026-07-12 鲁棒性实现复核

本轮没有更换 D5 算法主线。在线仍按“中心 GlobalTrack 预测到相机量测时刻 -> K/R/t 投影及协方差传播 -> 像素马氏门 -> Hungarian 唯一匹配 -> 友方/版本/稳定窗口保守决策”执行，AirSim detect 为默认输入，truth 只允许离线评分。

实现补强集中在时间与作用域：每个相机独立维护 local association history；锁定后缺失帧只产生 lost/reacquire evidence，0.25 s 后显式过期；恢复时即使 MOT ID 未变也需要 measured 稳定窗口，ID 改变时同样不能继承授权；同一 plan lineage 的旧版本直接 hold。D5 不输出 coast 状态、滤波状态或控制量。

新增回归复现了 M5N2 需要的基本困难：单相机目标交叉、不同相机部分重叠、外参漂移、时间偏差和 local ID 重置。部分重叠场景中，单视角目标只保留单视角支持，共同可见目标才生成 multi-view support；不存在“把两台相机的同名 local ID 当作同一目标”的路径。全量 `168 passed`。

该结果属于模块 replay 验收，不能替代真实 AirSim。下一轮仍需 main 固定 M5N2 几何/时长/seeds，分别统计 target、active-primary、coalition completion，并把 detect availability、D5 gate/lock、D7 control gate 和物理距离分层报告。YOLO/MOT 继续 deferred calibration。

### 14.1 离线 summary 消费合同

D5 已把 1-5 帧缺失/恢复、MOT ID change、crossing、partial overlap、extrinsic drift 和 timestamp bias 组织为无随机数的版本化矩阵。summary 不构造第二套关联器，而是调用现有 `TerminalAssociator`、GlobalTrack 投影/马氏门/Hungarian 和 cross-view registration API；因此 case 结果直接验证主线合同。

`d5.p1_visual_robustness_summary.v1` 的每个 case 都记录 pass/check/reject、decision/reason、online truth use 和 global ID rewrite。顶层提供 D6 readiness 兼容字段，`metadata.case_results` 保留 D6 当前聚合器需要的逐 case 紧凑记录。当前 D6 CLI 已成功消费该文件。确定性基线为 10/10 case、24 次预期保守拒绝、truth use 0、ID rewrite 0；该实现阶段 D5 回归基线为 `171 passed`，2026-07-13 当日全量为 `232 passed`，2026-07-14 最新全量为 `241 passed`。
