# 第五研究模块末端视觉关联（Terminal Association, D5）原理

**状态日期：2026-07-26**

## 图模型的读取权限与使用权限

模型完整性和模型使用权限是两层独立条件。开发训练与成对影子评估需要读取权重并复现概率，因此
运行时加载器默认允许通过严格完整性校验的 development bundle 进入 shadow。G1 辅助关联属于另一
权限层，调用方必须显式要求 `g1_assist_eligible`。清单没有正向授权时，加载器返回 unavailable，
规则关联继续工作。

当前稳定拒绝原因是 `bundle_g1_assist_not_eligible`。若清单字段缺失或被改为正向授权，原 schema
校验返回 `bundle_admission_invalid`。D5 不从 held-out 指标、文件存在、权重可加载或 scorer
`available` 推导权限。该边界防止开发模型因主程序只检查“可执行”而进入正式辅助路径。

2026-07-26 专项 `19 passed in 2.24s`，D5 全量 `555 passed in 97.04s`，零失败。旧冻结 bundle
绑定修改前的实现哈希，在当前源码下会失败关闭；若需要继续影子复核，应重新封装并重建证据，不能
取消代码溯源校验。main 统一 episode 总线已显式请求严格 assist admission；相关专项
`12 passed, 1 warning`，旧 bundle 在 G1/A1/A2/A3/C1/F1 中均失败关闭。当前仍没有获准的正式
G1 模型。

## 冻结图模型的证据边界

D5 的跨视角图模型接收匿名相机局部航迹节点和经过几何门的稀疏候选边。模型输出

\[
p_{ij}=P(y_{ij}=1\mid \mathbf{h}_i,\mathbf{h}_j,\mathbf{e}_{ij})
\]

其中 \(y_{ij}=1\) 表示两个不同相机的局部航迹可能属于同一物理目标。该概率只用于候选边评分。
同相机互斥、受约束聚类和中心航迹一对一绑定继续独立执行。模型不能生成中心身份，不能改写或
换绑 `global_track_id`。

2026-07-25 冻结 bundle 的 manifest SHA-256 为 `c4284b...674`，权重 SHA-256 为
`99fa4428...d4cd`。同一组哈希贯穿严格加载、20 个未见 seed 的 held-out 评估和同图 paired
shadow，关闭旧训练权重与审计权重不一致的问题。两臂逐帧读取同一匿名图和候选边；truth 只在
两臂完成概率输出和聚类后由 evaluator 使用。

名义 900 帧中候选召回为 1.0，模型边/簇 F1 均为 1.0。该结果受到合成数据捷径限制：bbox 尺度
变化率差的单特征 AUC 为 `0.997340`。label-independent 遮挡重现代理使模型边/簇 F1 降至
`0.563264/0.572845`，独立 bbox 尺度扰动使其降至 `0.893470/0.949131`。这些扰动固定候选拓扑，
只能检查评分器稳定性，不能证明真实时间、外参和遮挡条件下候选门仍能召回正确边。

在线异常必须失败关闭。模型缺失、bundle 不可用、输出尺寸错误、非有限值、概率越界、推理异常、
低置信度、非法阈值和超时共 9 类探针均返回与几何规则逐值一致的概率。bundle 仍为
`development_only_fail_closed`，G1、辅助模式和控制权限均关闭。

2026-07-25 D5 软件验收为 `552 passed in 114.25s`。main 在 D4 因果通信修正后复跑统一
module stack，结果为 `66 passed, 1 warning in 10.17s`。警告来自既有 Matplotlib 三维绘图
导入环境。D5 测试未发现在线身份、默认规则或跨模块合同回归；该结果不开放模型权限。

## 长窗口性能优化的等价边界

2026-07-23 对 clean `4ac3bb2` nominal 200v200 seed 1000 的匿名冻结在线日志完成热态 profiler 归因。长日志为 9.95 秒、114 次终端调用、723 个相机批次、2479 个检测/图节点和 2400 个 binding；truth source 未加载。该 profile 对应最终零符号边界修复前的 `sparse_tracklet_graph.py`（`dc6bcd81...b4c4c`），用于说明热点来源，不冒充最终源码性能证据。

允许复用的对象必须是已经证明内容相同或公式严格退化的内部中间量。本轮只维护历史 gauge 的更新差量、缓存匿名字符串的同一正则结果、跳过精确内建叶子的空递归、让 singleton cluster 复制已算投影行。不得缓存中心身份判断、友方冲突结论、跨帧相机几何或旧 binding；不得减少帧、检测、相机候选、中心候选、几何/身份/友方门或 Hungarian 唯一绑定。

固定诊断显示长日志避免 91,871 次 tracker 引用扫描，复用 2289 个 singleton 行；79 个多节点聚合、32 个无 binding matrix 输出、476401 个 binding 单元和 108 次 Hungarian 求解保持。最终实现进一步把 singleton 有限行的 `-0.0` 按旧求和路径规范为 `+0.0`，当前源码哈希为 `0e8a5880...19d5b`。机器 JSON 的 post-boundary-fix 重放确认短/长逐帧业务、最终 binding、v2 操作数和冻结 v1 operation-equivalence 哈希逐项一致，online truth use 与 `global_track_id` mutation 为 0。增量账本在 reset、空帧、coast、淘汰和 stream replacement 后与旧全扫描 current/peak 一致；内建类型子类仍接受完整 truth 字段审计。

边界修复前热态 `process()` 累计约 `2.320→1.987 s`；两轮各 7 次长日志 A/B 的中位值均值约 `1.149362→0.929495 s`。这些值只支持局部优化方向，不作为最终源码硬墙钟测试或完整系统准入。main 对最终源码的权威全量回归为 `551 passed in 100.83s`；此前 `550 passed in 102.41s` 是 boundary-fix 前历史值。原 10 秒集成 P50/P95/max 约 `11.497/15.969/18.632 ms`、相对短窗约 `2.556x` 的 P1 保持开放，必须由 main/D6 通过正交规模、多 seed 和预注册阈值关闭。

## 相机重叠索引等价优化

跨视角图只需要检查可能共享空间视场的相机对。旧实现从每个占用网格桶向周围完整三维立方体探测，其中多数位置没有相机。当前实现复用占用桶只读索引，直接比较占用桶对是否位于同一切比雪夫搜索半径内，再执行原有时间和视锥包围盒相交检查。

这一变化不调整图候选和几何门。三 seed 10 秒冻结回放中，旧、新逐帧核心、最终 binding 和操作数哈希保持，终端重放中位值均值下降 `16.45%`。在线真值使用、中心 `global_track_id` 改写、降帧、降候选和安全门限变化均为 0。该局部收益不能替代长时规模线性、AirSim 或硬件实时性验收。

## 最终集成等价边界

clean 参考提交 `8f86192` 与 clean 候选提交 `f80b5bd` 使用同一 nominal 200v200 配置、10.0 秒时长和 seeds `42000-42002`。三个候选 episode 均保持有限状态，在线真值使用为 0，D1/D2/D3/D5/D7 最终数量与参考运行一致。D5 终端关联累计耗时三 seed 均值由 `2.545876 s` 降至 `1.974446 s`，约下降 `22.45%`；主动视觉均值由 `4.174315 s` 变为 `4.183797 s`，约增加 `0.23%`，按基本持平处理。

三个 seed 的投影 DTO 缓存命中/未命中均保持 `68/48`、`71/48`、`70/48`，最终 binding 数保持 `22/29/28`。逐条视觉 binding 与主动视觉 payload 语义相同。跨提交审计只归一化 D3 独立运行生成的不透明 `plan_id`，归一化键为计划出现次序和版本；ACK 原始来源载荷 SHA-256 在归一化前验证，owner、version、coalition、`global_track_id` 和 command 等字段仍保留在比较范围内。

等价性的核心约束是作用域。中心轨迹数组在一次 `process()` 内只物化一次；同一量测时刻的不同相机批次共享一份只读 center prediction。函数返回后工作区释放，下一次调用重新读取中心状态。完整局部候选、中心候选、投影矩阵、几何门和唯一绑定仍执行，D5 不能借缓存创建、改写或换绑中心 `global_track_id`。

三 seed 累计耗时下降说明重复预测已从完整系统路径中移除，不能推出单次成本随检测数、相机数或中心候选数线性增长。既有短长归一化结果仍高于线性门，D5 超线性规模成本和正式实时性准入继续保持 P1。

## 等价优化必须保留完整矩阵语义

性能计数不能直接代替热点剖析。seed 42000 长日志的局部匹配比较、中心投影单元和 binding 单元分别为 `33315/499505/472288`，但对应累计耗时约为 `0.098/0.706/0.057 s`。本轮选择优化中心投影中的重复轨迹数组物化，而不是因为局部比较计数最大就截断历史候选，也不因为 binding 单元较多就放宽唯一性门。

中心轨迹数组每个 `process()` 只抽取一次，同一量测时刻的预测 position/covariance 只生成一份只读结果。工作区在函数返回后释放，不跨帧持有相机或中心状态。短/长日志的预测物化由 `76/715` 份降为 `23/116` 份，完整投影与 binding 单元数、固定大小快照 schema 和操作数哈希不变。

逐帧业务及最终 binding 哈希与冻结记录一致，online truth use 和 `global_track_id` mutation 为 0。配对 10 秒平均单次成本中位数下降 `26.6%`，但归一化增长仍约 `2.37-2.45x`，所以“删除重复工作”已经实现，“200v200 规模线性/实时性”仍未证明。当前源码三种子系统复跑已由上节关闭，D6 操作数聚合和正式计时准入继续开放。

## clean 集成证据边界

提交 `8f86192` 的统一三维 200v200 候选对 seeds `42000-42002` 各运行 10 秒。D5 终端关联阶段平均耗时由旧 clean 候选 `2.6985 s` 降至 `2.5459 s`，下降 `5.7%`，每个 seed 的调用次数保持不变。该结果说明当前实现进入完整 D1-D7 状态机后仍保持有限状态和可观测操作数；它是系统墙钟比较，不能把全部差值归因于 D5。

固定大小快照把算法输出与性能解释分开。seed 42000 的 116 次调用处理 2493 个图节点，并执行 33315 次局部匹配对比较。短长序列归一化单次成本增长由 `2.696x` 降至 `2.423x`，说明重复模板准备和快照复用降低了部分成本，但节点、历史、投影和绑定规模仍随场景增长。超线性 P1 因此保持开放。

三种子的在线真值使用和 `global_track_id` 改写均为 0。D6 将三组证据标记为 clean descriptive calibration，只能用于性能描述和后续阈值设计。它不等于正式统计验收、真实相机验证或学习策略收益。后文冻结日志 benchmark 用于 D5 内部操作数归因，不能与本节集成墙钟值合并。

## 操作数与状态规模

D5 的单帧成本取决于局部检测数量、活跃相机流、局部历史和中心航迹数量。检测先转换为相机局部 tracklet，并在各相机命名空间内做历史匹配。跨相机候选经过几何门形成稀疏图，图边被评分和约束聚类。聚类随后与中心航迹投影建立代价矩阵，再用匈牙利算法形成保守绑定。中心身份不由局部图产生。

固定大小性能快照分别记录各阶段的累计操作数。它只保留标量计数和当前/峰值，不保留帧、检测、边或矩阵内容。快照与业务输出分离，因此不会改变关联哈希、发布时间戳或门控决策。episode reset 同时清空局部状态和计数。

冻结长短日志显示，调用密度增长 `1.090x`，平均单次成本增长 `2.135x`。每调用节点、投影矩阵单元和绑定矩阵单元增长 `5.815x/7.274x/6.980x`。这说明长时增长主要由后段可见检测和可绑定中心候选增加造成。局部轨迹历史仍受 missed-frame 清理；已接收时间戳集合是 episode 级重复与乱序审计状态，随接受批次增长。

同一相机批次中的检测共享相机几何。当前实现只对第一条检测完整校验相机内参、外参、旋转和像素协方差，后续检测在全部消费字段一致时复用模板。内容签名只用于证明相等，不能绕过字段校验；几何变化仍失败关闭。该优化减少重复验证，不改变 tracklet、候选边、代价矩阵或绑定。

## 长时性能边界

D5 长时成本由每轮输入规模和调用次数共同决定。主动视觉对每台相机建立一次分配、投影证据和观察意图；终端关联对每帧局部 tracklet 与中心投影候选建图并门控。10 秒 clean 对照中，主动视觉单次成本基本不变，终端关联单次成本随每帧视觉候选均值由 `3.696` 增至 `21.491` 而上升。没有观察到 tracklet 历史或候选图随时间无界增长。

当前实现为只读快照建立相机、投影证据和分配目标索引，建图后的中心投影距离矩阵由绑定阶段复用；矩阵内部又按本调用唯一量测时刻复用只读中心预测状态。同一 D2 航迹快照通过内容指纹复用 DTO；适配实际读取的状态、协方差、航迹时间戳、版本或标识变化都会使缓存失效，episode reset 会清空缓存。相机观测的量测时间戳和到达时间戳继续沿原路径处理。这些操作只消除重复物化和重复投影，不改变候选集合、门控顺序、代价或决策状态。

固定日志重放验证 116/116 条终端记录一致，绑定状态为 `1938/36/384`（bound/ambiguous/unbound），在线真值和全局航迹编号改写均为 0。主动视觉继续使用确定性规则，学习辅助未授权。

## 同图配对与证据分层

paired shadow 的目标是隔离“候选图不同”与“边评分器不同”两个因素。对第 (k) 个保留帧只构造
一个不可变图 (G_k=(V_k,E_k,X_k))。确定性规则和冻结图神经网络读取相同的节点、边、候选顺序
与几何特征，分别输出 (p_k^{rule}) 和 (p_k^{gnn})。双方再使用同一个受约束聚类器，且同一相机
最多有一个 tracklet 进入同一簇。规则、模型和聚类执行后都复算图数组及候选边哈希；任一变化均
失败关闭。

离线标签 (y_k) 不参与候选构造、规则评分、模型评分或聚类。两臂预测完成后，evaluator 才用
(y_k) 计算边级精确率、召回率、F1、错误合并率，以及簇对级错误合并和同目标拆分。该顺序把
真值限定在评分域。中心 `global_track_id` 不在图模型输出空间内，D5 不创建或换绑全局身份。

正式 v2 覆盖 20 个保留 seed、45 个场景规模单元和 900 帧。冻结模型在该合成集上边级、簇对级
F1 均为 1.0，规则基线分别为 0.367980 和 0.239234。这个结果证明冻结模型在同一候选图上没有
质量退化，但不证明真实跨视角泛化。规则基线只按几何门分数和单一共享投影下限产生概率，错误
合并率较高，不能把二者差值直接解释为真实系统收益。

满分数据必须进行后验可分性审查。`shared_global_track_count` 在本保留集全部为 0，互信息为 0，
取值 1 的分层不可用。尺度差、尺度变化率差和角速度差的单特征最佳方向 AUC 约为 0.9973，说明
合成器使同目标运动尺度特征过于一致。该统计只描述数据，不是模型归因。真实准入还需要独立生成
机制、异步与标定漂移、同运动困难负样本、外观变化和代表性多相机回放。

证据状态与运行权限分离。v2 是本输入绑定下的 `authoritative` 评估，旧版仅
`superseded_preserved`；但 `G1=false`、`assist=false`、`authority=false`、`rule_fallback=true`。
D6 独立审计和更困难数据验收前，满分不能用于改变在线默认路径。

当前最终源码已通过 paired-shadow 专项 5 项和 D5 全量 534 项测试。该软件回归只验证实现与既有
合同，不增加真实跨视角泛化证据。

## 稀疏候选图预算

跨相机图先经过时间、视场、极线、射线、重投影、协方差和中心航迹投影门，再按几何质量排序形成
有界稀疏边。前置候选索引和最终图都必须有常数度数上界。两层上界不一致会在几何门之后再次删除
有效边，使分类器看不到应评价的同目标 pair。

修复前的 clean supplemental 使用前置 24、最终 8 两个预算。370,211 个可能 pair 中，几何门只
拒绝 21 个；最终预算却从 370,190 条门后边删除 125,158 条。canonical test 因此只保留
11,409/16,698 个同目标候选，候选召回率为 0.683255。该数值说明候选生成不完整，不能归因于图
分类器性能。

当前默认将两层预算统一为 24。最终图仍满足每节点度数不超过 24、边数不超过
`floor(V*24/2)=12V`，计算和存储复杂度保持 `O(V*k)`。排序只使用几何门分数和匿名 tracklet key，
不读取离线真值。诊断分别记录几何拒绝和最终预算删除，避免把两类损失合并解释。

2026-07-21 的内存回归在 seed 5、`delayed_noisy`、scale 200 四相机帧上得到 15/15 同目标 pair、
候选召回率 1.0，实际最大度数 12。小 cap=2 回归证明度数上界和确定性仍成立。4,500 帧 clean 语料、
后续已经基于 24 邻居配置重建 supplemental/composite、完成内部训练、900 帧 held-out 和 paired
shadow v2。该完成只证明当前合成数据链闭合；近确定性特征可分性和真实泛化仍阻断线上准入。

## 保留集评估边界

跨视角图模型的训练内测试只说明模型适合训练语料内部的数据分布。D5 另设 seed `1000-1019` 作为
独立保留集。20 个 seed 分别覆盖 45 个场景规模单元，形成 900 个图帧。保留集不参与训练分桶、
温度标定、判决阈值选择或权重更新，其作用是检查模型在未见物理几何和扰动组合上的关联稳定性。

每个保留帧先由三维质点和相机模型投影为匿名局部 tracklet，再执行既有时间、极线、射线、重投影
和协方差门。候选图中不存目标真值或全局轨迹标识。离线 evaluator 通过独立标签和 observation
lineage 计算同目标边、异目标边、候选召回和错误合并。一个边只有在来源观测、局部轨迹、相机、
量测时刻和确定性实体规则全部一致时才可评分。

模型评估沿用训练阶段在 validation 上确定的温度和阈值。整体及每个场景规模单元均输出精确率、
召回率、F1、错误合并率、候选召回率、期望校准误差和推理延迟。任何指标不足只会形成
`fail_closed` 证据。2026-07-22 已完成同 seed paired shadow v2；G1、辅助关联和控制权限仍不会由
D5 单独开启，后续还需 D6 独立审计和更困难数据验证。

## Composite 训练证据分层

组合语料训练入口只接受严格复载的 formal complete frames 与 clean supplemental corpus。源数据、
组合视图、准入报告和共享 seed registry 必须同时命中；seed 按完整数值原子分为 `60/20/20`，
`1000-1019` 保留 seed 不得进入，三个 split 都必须覆盖 45 个场景规模单元并同时含正负边。在线图
仍只含匿名 camera-local tracklet、双时间戳、协方差和几何特征。truth 只参与物理分离的离线标签，
D5 不创建或改写中心 `global_track_id`。

证据分为数据支持、内部模型测试、保留 seed、paired shadow 和 G1/assist 五层。首轮 preflight 的
4,972 帧、245,040 边属于预算修复前历史。修复后 clean supplemental/composite 为 4,500/4,972 帧、
370,190/370,198 边，三个 split 候选召回均为 1.0；固定 30 epoch 内部训练、held-out 和 paired
shadow v2 已完成。cell 样本口径仍为已标注候选边数。即使前四层通过，合成特征偏易、共享中心
线索取值 1 未覆盖和 D6 外部审计未闭合时，G1、assist、在线及相机控制权限仍为 false。

## 跨视角困难样本准入原则

冻结正式语料的缺标签记录只能由精确来源链补齐。有效证据必须同时匹配正式 manifest、episode、
匿名 tracklet、量测时刻、source observation 和 evaluator truth。最近时刻、同 tracklet 跨帧沿用、
几何邻近和模型预测都不构成标签证据。本轮审计的 99 条未标注边涉及 194 个缺失端点，冻结导出没有
保留符合上述条件的来源链，可靠回填为 0，全部继续 `unavailable`。

补数采用独立物理投影课程，不修改冻结语料。四个局部相机观测四个物理目标，在线阶段只形成匿名
camera-local tracklet、双时间戳、像素量测、协方差和几何特征。候选边先经过既有时间、视场、极线、
射线、重投影、协方差和度数门；精确 truth 在图完成后通过独立 observation lineage 加入 evaluator
标签。这样得到的困难负边表示“几何上可混淆但物理身份不同”，不会通过放宽在线安全门增加样本。

准入分为数据支持、训练和模型晋级三层。formal + supplemental 只读视图以完整 numeric seed 为原子
按共享 registry 切分，并复核保留 seed、source hash、标签完整性、边支持、candidate recall 分母和
双类场景覆盖。首轮 245,032 边是修复前历史；当前 clean supplemental 为 370,190 边，组合视图为
370,198 边，候选召回 1.0，未标注和保留 seed 重叠为 0。

训练数据准入与模型晋级保持分层。模型、保留 seed 和同 seed shadow 已有 v2 证据，但 promotion
仍等待 D6 审计和更困难、独立生成的数据。G1、assist 和在线/相机控制权限继续关闭，中心
`global_track_id` 所有权及既有几何、安全门不变。

## Supplemental BC 全样本审计原则

补充规则教师数据进入跨模块学习评审前，必须对 immutable dataset、detached canonical view、training/
shared registry 和 producer summary 重新建立文件级绑定，不能只信任生成时的统计。审计先复用 strict
lazy loader 校验 `SHA256SUMS` 精确文件集合和 online/offline join，再复用 canonical loader 按数值 seed
原子分桶；随后遍历全部 BC 样本，要求每个规则示范在有限动作候选中唯一，35 维候选特征全部有限，
plan/coalition/communication/track 版本单调一致，且所有 track、assignment、projection、action 引用
仍指向调用方提供的唯一中心 `global_track_id`。审计 JSON/中文报告不得写入 supplemental 或 registry
source root，绑定不一致时仍发布 `pending` 证据并返回失败。

2026-07-21 实际 clean 审计接受阈值为 100 episode、1200 sample、canonical episode `60/20/20` 与
sample `720/240/240`、302/302 checksummed 文件、1200/1200 有限特征及零 truth/reserved/dirty/
audit violation。实测全部通过，100 descriptor/online/offline 集合完整，7800 个候选特征行，1200/1200
规则示范唯一；审计内容 SHA256 为
`a11b65596a4c416deba6d0cb35dcc0c32342a5bae0481291d43e8de0e26550dd`，来源 commit 为
`13e37286d2996a227924bb1a8e2766e52116a534`。来源六项 SHA 与 producer clean evidence 一致；
supplemental 树保持 308 files/约 2.2 MiB，正式 900-episode 树保持 43973 files、SHA256
`8ffbe5cf044d121163c8acc3dce1bbd54e14bb6b211b8e1cf440f24c93294fca`。

该审计只关闭 supplemental behavior-cloning full-sample 子项。补充课程是 synthetic 规则教师数据，
不是正式观测语料；`400/400/400` 是故障注入覆盖，不是真实 runtime ACK。四类离线标签仍 unavailable，
不得补零。paired shadow v2 已完成；D6 跨模块准入、真实 ACK/outcome attribution 和
reward/counterfactual/causal 仍未完成，因此 PPO、assist、在线/相机 authority 保持 false，规则
回退必需。

## Supplemental curriculum 生成原则

补充课程与正式 900-episode 数据是两个独立数据集。D5 只接受调用方显式给出的中心
`global_track_id` 和 Git/config provenance；同一 ID 被只读带入 track、assignment、projection 和
action，不允许 producer 创建替代 ID。100 个 training seed 必须完整来自绑定 registry，保留
`1000-1019` 不得出现。shared registry 的 schema、source file SHA、content、assignment 和数值 seed
策略必须由既有 canonical API 复算，而不能信任调用方声明。

training registry 和 shared registry 各自解析后的父目录都是受保护的只读 source root。shared
registry 位于 training root 下时，外层根保护完整正式输入树；两者不在同一根时分别保护。输出目录、
tracked JSON 和 tracked Markdown 不得等于或位于任一 source root 下，路径冲突必须在读取生成输入、
创建 staging 或 tracked 目录前失败关闭。

生成采用“临时 sibling 完成、验证后原子发布”。目的目录预先存在即拒绝；online record、offline
unavailable label、final manifest、lazy audit、detached canonical view 和 readiness 全部在临时目录
闭合。只有 seed/episode/sample、版本、truth、synthetic/dirty、availability 与所有 SHA 门均通过，
才执行 `os.replace()`。视图只重分完整 episode，不改源 manifest 或样本。dirty 数据可以用于验证
失败关闭分支，但不具备 clean development 资格。

每 seed 的 applied/rejected/missing `4/4/4` 是执行器故障注入覆盖，用来确认 ACK 与 camera feedback
语义；它不是运行频率，更不是策略收益。reward、outcome、counterfactual 和 causal label 必须以
null/unavailable 明示，不得补零。synthetic curriculum 只允许 development shadow/BC 研究接口；
PPO、assist、在线 authority 和相机命令权保持关闭。生成报告的标题、说明和约束使用中文，技术
token/SHA 可原样保留。

2026-07-21 main 在 detached clean worktree `13e37286d2996a227924bb1a8e2766e52116a534` 完成实际生成。
100 episode、800 segment、1200 sample 与 canonical seed/episode `60/20/20`、sample
`720/240/240` 全部通过；online truth、reserved overlap、dirty episode 和 audit violation 均为 0。
正式 900-episode 输入树前后 SHA 同为
`8ffbe5cf044d121163c8acc3dce1bbd54e14bb6b211b8e1cf440f24c93294fca`。该生成证据关闭 clean
supplemental producer/canonical 子项；其后绑定 SHA 的 BC 全样本审计也已由本节顶部证据关闭，且不
改变上述权限边界。下一步只进入 main/D6 跨模块准入与真实运行证据建设，不能从 synthetic ACK
推导真实执行效果。

## 宽视场稳定门原理

相机缩窄视场会降低搜索覆盖，对单帧误配也更敏感。D5 因此把缩放资格与当前中心绑定的连续性分开
管理。每个相机只保存一个活动状态，键定义为：

```text
K = (camera_id, global_track_id, plan_version, coalition_version)
```

第 `t` 帧只有同时满足量测与到达时间有效、证据新鲜、可见概率达标、遮挡不过限、关联置信度达标、
投影位于视场、当前分配和三个运行版本有效、无友方保留冲突时，才进入稳定计数。当前帧和投影时间
必须严格晚于上一帧；重复帧不增加计数，时间或证据回退从 1 重新开始。状态键改变也从 1 开始。

默认稳定窗口 `N=3`。当 `s_t < N` 时，规则仍输出中心目标的 `OBSERVE_TARGET`，视场保持 `WIDE`。
当 `s_t >= N` 且投影角度协方差迹不超过原阈值时，才选择 `ZOOM`。设置 `N=1` 可得到旧即时缩放
语义。该门只收紧视场选择，不改变目标引用、云台角速度/限位或动作有效期。

多目标歧义使用保守质量分数
`q = association_confidence * visibility_probability * (1 - occlusion_fraction)`。当前最优投影与其他
已分配投影的分差小于默认 `0.05` 时不累计稳定帧，输出宽视场重捕获。旧证据、低置信、通信异常、
版本失败、友方冲突和相机忙同样清空计数。重捕获和扫描在相机支持时使用宽视场；云台忙保持当前
FOV，执行器恢复后重新通过宽视场稳定门，避免在忙状态下产生额外光学命令。

当前主动视觉 snapshot 不含运行时 ACK。阶段 A 不以相机状态推断 ACK，也不扩展 DTO。真实命令
接受、拒绝和丢失确认仍属于后续 producer/runtime 证据。该限制不影响本次状态门的软件正确性，
但阻止把规则测试解释为执行闭环或策略收益。

## 共享 seed 只读视图原则

跨模块学习必须引用同一组训练、验证和测试 seed。D5 不改写正式数据集解决历史分桶差异，而是在
strict loader 之后叠加 detached view。视图把数值 seed 作为原子单位，同一 seed 的全部场景、规模
和完整 episode 只能进入一个 split。图的节点/边、主动视觉在线流和离线标签均保持原字节内容。

视图同时绑定四类身份：原 manifest 与去除旧 split 后的 source content hash；training registry
文件 hash；shared registry 文件、content 与 assignment hash；D5 consumer/source schema。加载时
独立复算 D3-compatible 排序，不信任 registry 中已经写入的桶。seed 缺失、多余、重复、错桶或
`1000-1019` 保留 seed 出现时失败关闭。三项 canonical 路径未同时提供时，训练入口拒绝半绑定。

split 对齐只解决数据治理问题。它不增加候选边、困难负样本、少数意图、运行 ACK 或 reward，也不
改变旧模型的训练身份。正式图数据对齐后仍有 97.52% 无边帧；主动视觉仍无 hold 正样本和动作结果
归因。因此图模型不进入 G1/assist，主动视觉保持 development shadow-only，PPO 关闭。D5 对
`global_track_id` 的只读边界、几何门、同相机互斥和规则回退不受学习视图影响。

## 主动视觉行为克隆原则

主动视觉行为克隆只模仿确定性规则在有限安全候选集中的选择。每个状态先由版本、通信、相机限位、
友方冲突和投影新鲜度生成 4-7 个合法动作，再最小化规则示范动作的负对数似然：

```text
L_BC = -(1/N) * sum(log pi_theta(a_rule | state, safe_candidates))
```

该训练不读取 reward，不把相邻观测变化解释为动作结果，也不扩大动作集合。模型输出只是候选动作
得分；规则动作、运行时版本复核和相机命令门仍位于模型之外。D5 的主动视觉学习不接触本地视觉到
`global_track_id` 的绑定，更不能改写中心身份。

正式数据完整性与容量允许开发训练。900 个 episode、1,153,242 个样本按整 seed 分割，完整 train
split 685,005 个样本用于 5 epoch 训练。候选动作覆盖 4 和 7 两种规模，5v5 至 200v200 均有样本。
模型 bundle 绑定数据、split、训练集、配置、实现和权重 SHA256，只允许 shadow 回放。

数据分布决定当前不能晋级。`reacquire` 占 92.16%，`observe_target` 只占 1.72%，`hold` 为 0。
test 总体精确动作准确率为 95.60%，但 `observe_target` 召回率为 0，侦察相机精确动作准确率为
62.18%。多数类高分不能替代关键意图覆盖。温度缩放也没有改善期望校准误差，因此模型状态保持
development shadow-only，assist 和 PPO 关闭，规则回退必需。

## 正式图数据准入原则

正式 900 episode 已形成 12851 个匿名跨视角图帧。D5 训练前先由 strict loader 复算每个图和标签
文件的 SHA256，再检查 schema、特征版本和顺序、完整 seed 分割、split hash 与 training-set hash。
模型训练不能先于数据完整性和身份隔离审计。保留评估 seed 不得进入训练。

图数据准入同时检查候选生成覆盖。当前 `12532/12851` 帧没有候选边，edge-free 为 `97.52%`；
训练、验证和测试负边只有 `11/4/4`。partial candidate recall 的分母为 `4/1/1`。局部值为 1.0
只说明这 6 个 pair 没有漏掉，不能说明全数据候选召回。模型在少量已标注边上的高分不得覆盖
edge-free、负样本和 recall availability 门。

系统把训练状态分为三层：数据训练准入、development-only 管线验证、G1/assist 晋级。开发模型只
输出既有候选边的同目标概率，bundle 固定不具备默认或 assist 权限。受约束聚类的同相机互斥、中心
航迹投影、几何门、版本门和规则回退继续执行，D5 不创建或改写 `global_track_id`。

固定 seed 开发训练得到验证/测试 F1=1.0，但各只有 4 条负边，误合并率和完整 candidate recall
不可用，因此 promotion 为失败关闭。下一轮证据必须来自独立场景和 seed 的相机共同可见、密集交叉、
遮挡重捕获和几何可混淆异目标，不允许复制边或降低在线安全门。

**适用范围：** 本文描述第五研究模块（D5）当前代码、测试和主运行链路已经具备的能力。文中将默认主线、已实现但非默认的辅助/离线能力、尚未实现能力严格分开。计划项不能据此解释为已上线能力。

## 2026-07-20 接收窗口与关联快照原则

一次 D5 调用表示当前运行周期排出的已到达接收窗口，不等同于“每个相机恰好一帧”。链路延迟和
抖动会使同一相机在一个窗口中包含多个批次。D5 必须按 arrival 语义依次推进该相机的匿名本地
跟踪器，不能以调用边界拒绝合法积压，也不能按 measurement 时间把真实接收顺序改写掉。

多批次采用先验证、后提交。全部输入先完成真值字段隔离、有限值、相机命名空间、来源观测唯一性
检查，再按 arrival 主键形成确定顺序。每个相机用独立的暂存双高水位推演整个窗口。任何重复或
回退错误都会拒绝整个窗口，前面的合法批次也不会先写入状态。该原子边界保证失败恢复后 local ID、
命中数、框、速度和 OOSM 计数仍来自调用前状态。

批次流与关联图具有不同粒度。输出批次保留窗口内每次接收及其双时间戳；关联图表示窗口处理完成后
的当前状态，每个相机只选最后一次有效状态更新。较早正常帧已经用于推进运动状态，但不会与同一
local track 的较新版本一起进入图；后到 OOSM 不替换最后有效快照。该选择维持唯一 tracklet key、
相机几何一致性和中心 ID 只读边界。

双高水位之外，每个相机登记 episode 内已接收的 measurement 时间戳。该登记用于拒绝较早正常帧和
已忽略 OOSM 的重复传输，避免只比较当前 measurement 高水位时漏判历史重复。它不保存检测内容，
不进入跟踪代价、运动估计或身份关联；episode reset 时一并清除。

2026-07-20 回归为定向 `31 passed`、D5 全量 `410 passed in 11.68s`。绑定 `c5a9f6d` 的正式数据
目录仅有 209 条已完成进度，只保留为故障证据。D5 与 runner 修复形成新提交后，必须在该新干净
提交和新输出目录中从 sequence 0 重建 900 episode，不得恢复或拼接旧目录。当前尚无新 900 集的
完成和最终化证据。

## 2026-07-20 双时间戳与 OOSM 原则

`measurement_timestamp` 表示图像形成时刻，`arrival_timestamp` 表示批次到达 D5 的时刻。通信延迟
和抖动允许 arrival 顺序中的 measurement 回退。D5 不得为了维持表面单调而按量测时间重排到达流，
也不得覆盖任一时间戳。

每个相机流维护最近已接收 arrival 和最近已写入状态的 measurement 高水位。arrival 必须严格推进；
相同 arrival 是重复输入，较小 arrival 是接收顺序错误，两者都失败关闭。measurement 高于高水位
时正常更新；等于高水位时判为重复量测并拒绝；低于高水位时判为合法 OOSM。由于当前匿名 tracker
没有固定时滞历史，OOSM 只保留批次、几何和诊断，不更新或老化当前状态。该规则避免利用未来状态
反推过去，也避免后到旧框覆盖当前框。

OOSM 批次的 `status=oosm_ignored`，metadata 记录 temporal status、状态更新标志、累计 OOSM 数和
双高水位。它不产生新的局部 ID 或中心绑定，因而不改变 truth-free 与 `global_track_id` 只读原则。
OOSM 修复当时定向 `24 passed`、D5 全量 `403 passed in 9.74s`。main 随后在同一 clean revision
的新目录完成首个 45-cell、一次 checkpoint resume，并累计到 209 条完成进度；原 OOSM 异常没有
复现。后续同相机多批次阻塞和当前验证状态见上节。

## 2026-07-20 主动视觉数据写入性能

主动视觉 episode 中，一个时刻的完整快照由同批相机样本共享。原实现虽然在磁盘上只保存一次
快照，构造每个相机样本时仍重复扫描快照中的中心航迹、相机和投影证据。200 相机条件下，审计
开销近似按相机数乘快照规模增长。剖析同时确认 gzip level 6 不是主要耗时来源。

当前实现对冻结快照建立弱引用生命周期内的中心引用索引。每条样本仍校验动作、计划/联盟/通信
版本、相机反馈、运行确认、有限动作集和样本自身真值字段。持久化前绕过缓存再次检查快照；公共
audit 从磁盘独立复核，因此缓存不旁路真值隔离或中心 ID 只读门。writer 将一次规范化编码同时用于
SHA256 对象键和 JSONL 写入，gzip 等级、格式和字节保持不变。

200-camera/400-track fixture 构造由 `2.3597 s` 降至 `0.1097 s`，materialized load 由
`2.3948 s` 降至 `0.1802 s`；既有 3,536-sample 制品 writer 由 `3.5529 s` 降至
`0.7313 s`。修改前后 gzip 和解压流 SHA256 相同。D5 全量 `400 passed in 9.74s`。该证据关闭
D5-owned 重复处理子项。main 随后完成同配置 clean-tree 三 seed 系统复测，writer P1 已获得系统级
关闭证据；正式 900 episode、训练与准入验收仍未完成。

## 2026-07-20 规模化数据性能判定原则

规模化数据优化必须分别核算 episode run、artifact staging 和 finalization，不能用总墙钟掩盖单项
热点。postopt1 在提交 `4052d9411363c39d52100c0e3a4f60ee88443cab` 上运行 nominal 200v200、2 s、
seed 930-932，三场均为 clean tree 且 online truth use=0。相对基线，总墙钟
`467.8007→262.2866 s`，staging `225.9243→126.4682 s`，finalization
`116.5624→7.7377 s`；episode run `125.2205→127.9871 s`，应判为基本持平。

D5 graph staging 为 `0.0250/0.0259/0.0290 s` 并正常最终化，重复 finalization 审计热点已经关闭。
D5 active-vision staging 为 `41.5623/43.2639/41.2271 s`，占每场 staging 的 99.6% 以上。这是
writer 优化前的历史基线。优化只能采用等价对象编码、流式写入和落盘实现，不能降低采样、删减
特征，或弱化在线 truth-free、离线标签物理隔离、哈希和失败关闭原则。

main 在提交 `45b36500dc3c6935b1f116614993e291041eb12d` 上用相同 nominal 200v200、2 s、
seed 930-932 完成 postopt2。三场均为有限状态、clean tree、online truth use=0；D5 graph 正常
最终化。active-vision staging 降至 `4.0494/3.9898/3.9995 s`，总 staging
`126.4682→12.4372 s`，总生成 `262.2866→144.5513 s`。episode run 为 `124.7415 s`，因此该
结果只关闭离线 writer P1，不证明在线关联或 200v200 仿真实时运行。

数据可生成不等于学习能力准入。postopt2 的三 seed 只产生 1 个规划测试 seed，未达到 20 个未见
测试 seed；
active-vision dataset 因此保持未最终化，理由为 `insufficient_unseen_test_seeds`。正式 900-episode
corpus、BC/PPO、checkpoint、paired shadow 与 assist 准入均仍是待完成项。

## 2026-07-20 主动视觉 episode 数据最小权限原则

整 episode 数据记录仍必须遵守在线最小权限。正式 `ActiveVisionEpisodeSampleV2` 保存完整
snapshot、规则示范、requested/effective camera action、plan/coalition/communication version、
相机反馈和 runtime ACK，但在线文件不能出现 truth、actor、object identity。所有目标引用都必须
是同一 snapshot 内中心提供的 `global_track_id`；D5 不允许用本地 ID 生成、替换或换绑中心 ID。
V1 Python 类名仅为源码兼容别名，不表示旧 v1 嵌套文件可读。

同一决策周期的 snapshot 与 camera feedback 必须按 SHA256 对象 key 在 episode 内只保存一次，
sample 只保存稳定引用。确定性 gzip JSONL 的 header/object/sample/footer 逐行接受 truth-free 与引用
审计，不得通过删字段降低证据质量。online record v2、sample v2 和 descriptor v2 构成 episode
dataset v3；旧文件必须稳定失败关闭。

在线 observation 与离线 evaluator 结果必须物理分离。episode 先关闭 truth-free online record，
再由 evaluator 通过稳定且一一匹配的 `sample_key + observation_key` 写 offline label。reward、
outcome、counterfactual 和 causal label 永不回填 snapshot。reward 有界 `[-1,1]`；缺 outcome
使用 unavailable/null，不能用 0 伪装；causal label 还必须有 counterfactual。

数据切分以完整 `(scenario_version, seed)` group 为不可分单位，并以唯一数值 seed 作为跨场景
原子分配单元。同一 seed 的所有 scenario/scale group 必须进入同一 split，test seed 不得出现在
train/validation。少于三个唯一 seed、少于声明 unseen test seed 或任一 group/seed 跨 split 都
必须失败关闭。正式默认要求 20 个 unseen seed；单元 smoke 可显式降低门，但不能据此形成准入。
manifest 必须绑定 `shared_seed_values_atomic_across_scenarios=true`、schema/version、全部 artifact
SHA256、split/training-set SHA、source Git/config identity 和 label availability。finalize 后数据
只读，loader 复算全部哈希并拒绝额外制品。

BC 只能从 online record 提取规则示范，不读取 evaluator label。PPO 只能在每个 selected sample
都有有界离线 reward 时加载；缺一项即拒绝，不能补 0。split 持久化语义升级为 learning dataset
v2；episode dataset 为 v3，模型 bundle v4 绑定 episode dataset v3。snapshot/action/feedback/ACK/
offline-label 保持 v1，且仍需正式 paired shadow admission 才能 assist。跨视角 tracklet 数据集和
bundle 同步升为 v2，同一数值 seed 的所有 scenario/scale graph 必须进入同一 split。

finalize 和 dataset audit 必须逐 episode 流式审计，不能调用兼容全量 loader 或跨 episode 保留
record/sample。同一次 finalize 只允许每个 episode 做一次内容审计；该次审计形成在线合同、离线
连接和实际 SHA256 证据，最终结构复核只能在文件设备号、inode、大小和修改时间未变化时复用。
文件变化必须失败关闭。公开 audit 不接受 finalize 的内存证据，每次仍从磁盘独立复算 SHA256、
解压 online stream 并核对 offline join。非物化 stream reader 校验原始 sample、feedback、snapshot
行和全部动作/版本/ACK 关系，只保存紧凑 key/index，不得为每个 sample 重复扫描共享 snapshot。
`LazyActiveVisionEpisodeDataset` 只在 iterator 前进时物化当前 episode；BC iterator 不读取 offline
label，PPO iterator 逐 episode 检查 reward availability。兼容全量 loader 只适用于明确有界的小数据集。

落盘证据必须忠实反映 controller 的规则回退：所有非 assist effective mode 的 effective action
必须与同 tick rule action 完全一致；assist 只有在 requested/effective action 一致且无 fallback 时
成立。数据集相对路径与绝对路径必须具有相同行为。匿名节点命名空间的 resource、camera 和 local
track ID 都不得携带 truth/actor/object-like 标识。

2026-07-20 main 容量实测为 nominal seed 91、每档 2 s：5/20/50/100/200v200 总制品约
`0.086/0.295/0.733/1.543/2.884 MB`；200v200 online/offline `1.064/1.818 MB`、`3536` samples、
RSS 约 `1.04 GB`、online truth=0，单 episode 容量门通过。D5 当前代码证据为数据管线
原阶段 `16 passed`、全量 `398 passed in 15.75s`；本次最新为数据专项 `18 passed`、全量
`400 passed in 9.74s`。6 episode × 48 camera × 96 track 的确定性计数中，
finalize 的 online/offline parse 从 `12/12` 降为 `6/6`，SHA256 调用从 `67` 降为 `20`，每个实际
制品一次；独立 public audit 仍重新执行一轮。200-camera/400-track 合成 stream audit 辅助墙钟约
`9.81→0.37 s`，墙钟不作为验收门。磁盘 schema、在线真值隔离、离线标签分离、whole-seed split、
SHA256 和只读语义均未改变。尚未运行 900-episode 正式集、正式训练、20-unseen-seed 性能或模型
准入；本轮未修改 main/runtime。

## 2026-07-20 主动视觉最小权限与安全回退原则

学习型主动视觉是可选研究支线，不改变 D5 几何关联和确定性规则观察默认主线。版本化 snapshot 只允许中心
GlobalTrack/AssignmentPlan 只读引用、相机云台/FOV 状态、投影不确定度、可见/遮挡统计、通信
状态及 plan/coalition/communication version。truth、actor、object identity 不得进入策略输入；
`global_track_id` 只能从输入候选与当前相机分配交集中只读选择，模型无权创建、改写或换绑。

动作遵循相机意图最小权限：observe target、search sector、hold、reacquire，外加有限 yaw/pitch
增量和 wide/zoom。动作合同没有平台速度、航向、加速度、航点、D3 assignment 或处置字段。
学习模型也不回归任意连续控制量，只能在基于投影和规则扇区生成的有限候选中评分选择。

规则 look-at/reacquire/scan 在所有模式下先计算。学习请求随后必须通过计划/联盟/通信版本、
候选成员、FOV 支持、云台机械角、当前与请求速率、slew、友方 exclusive reservation、证据
freshness 和 action timeout。模型/bundle 缺失、SHA/schema/state 错误、OOD、低置信、非有限、
异常或慢推理均直接采用同 tick 规则动作。shadow 的最终动作永远是规则动作。库默认 disabled；
CLI 默认 shadow preflight。main-owned 统一三维 episode 已连接模拟相机执行器：规则动作经版本、
有效期和资源复核后在下一视觉帧更新 yaw/pitch/FOV，并生成 runtime ACK；这不等于真实 AirSim
云台或实机执行器已经连接。

assist 准入必须来自与模型指纹及 dataset manifest/split/training-set SHA 绑定的 paired shadow
报告。test 至少包含 20 个在 train/validation 中完全未见的 seed，数据必须正式且非合成，
safety、visibility、reacquisition delay 必须逐 episode 和总体均不退化。合成 fixture 即便 20 个
seed 全部为正，也只能证明门控代码可运行，不能授予准入。当前没有正式 checkpoint、正式
paired 报告或真实云台闭环，故 assist 未准入。

`source_observation_id` 是量测审计键而非身份。scalable adapter 可从在线 observation 只读传播
该键，使 evaluator 在图冻结后连接 truth label；tracker 匹配、local ID、tracklet key、图特征、
聚类和 global binding 均不得使用它。同一帧一个 observation 最多连接一个 tracklet；假目标
没有 evaluator label 时必须报告 labels incomplete。

2026-07-20 验证为主动视觉专项 `17 passed`、D5 全量 `376 passed in 9.94s`。BC/PPO 仅在
8 个合成 seed group 上各跑 1 epoch smoke。统一三维 episode 后续完成 5v5 `84/84` 和
200v200 seed 17、1.2 s `1872/1872` 命令 applied 冒烟；均为单 seed、脏工作树接口证据，
不产生 AirSim、实机、性能收益或模型准入结论。

## 2026-07-20 训练数据与模型制品安全原则

离线训练不得改变在线图的语义。每个数据 episode 必须先由在线 D5 匿名构图完成，再将
node feature、candidate edge、edge feature、匿名 tracklet/camera key 和双时间戳写入 graph
NPZ；`truth_entity_id` 只能写入独立 evaluator label JSON。graph 不持久化 evaluator truth 或
`shared_global_track_ids`，模型也只消费固定顺序数值 tensor。graph/label 不能合成单一文件，
在线 scorer 不接收 evaluator label。

数据切分的最小单元是完整 `(scenario_version, seed)` group。一个 seed 下的多个 episode 必须
进入同一 train、validation 或 test；禁止 edge-level random split。dataset manifest 必须记录
schema、node/edge feature names/version、generation config SHA256、class balance、candidate
recall 是否可算、困难负样本来源、split SHA256 和 training-set SHA256。加载必须使用
`allow_pickle=False`，并验证文件 SHA、shape、有限值、feature order、label completeness 和
seed 泄漏。

训练可按多图梯度累积，但随机 seed 必须固定。困难负样本只从匿名在线候选边中产生，truth
在图冻结后只决定二元训练 target；不平衡损失使用显式正类权重。模型选择、scalar temperature
calibration 和 decision threshold 只能读取 validation；test 只用于最终报告，不得回流调参。
test 输出 edge precision/recall/F1、受同相机唯一约束后的 false-merge rate、candidate recall、
Brier/ECE、P50/P95 inference latency 和 model size。对应完整 truth 不可用时指标必须是
unavailable/null，不能填 0。

模型 bundle 固定为 manifest、纯 state_dict 和 SHA256 校验文件。manifest 固化模型语义版本、
图/feature 版本与顺序、hidden dim、message steps、训练集/split hash、validation-only
temperature/threshold 和验证结果；加载只允许 `torch.load(weights_only=True)`。任一文件缺失、
损坏、版本/顺序不匹配、权重或输出非有限、推理超时、低 certainty 或 threshold 无效，都必须
回退现有 deterministic geometry rule，且保留明确 provenance。

学习模型的权限止于 candidate-edge same-target probability。聚类继续执行同相机最多一个
tracklet 的约束，中心投影/Hungarian 继续只引用中心输入 ID。模型不能创建、改写或换绑
`global_track_id`，也不能绕过几何候选门创建新边。

2026-07-20 代码验证为新管线 `12 passed`、组合专项 `46 passed`、D5 全量
`355 passed in 9.48s`，零失败；checkpoint 均在 `tmp_path` 生成。本轮只关闭训练/校准/评估/
制品软件管线，不构成模型准入。至少 20 个未见 seed、代表性困难场景、冻结门限和默认
checkpoint 均开放，几何规则仍是默认。未运行 AirSim；本轮主动视觉合同已在集成计划文首同步，
随后已完成统一三维模拟接线，但没有新增真实 AirSim 实验或模型准入证据。

## 2026-07-20 匿名稀疏跨视角图原则

跨视角图的基本节点不是目标、actor 或全局航迹，而是唯一命名空间
`resource_id/camera_id:local_track_id` 下的 camera-local tracklet。在线节点只携带双时间戳、
像素中心、bbox、像素协方差、角速度、尺度变化和置信度；truth/actor/object identity 以及
`global_track_id` 均不允许进入节点或 metadata。local ID 也不是可信身份字段：构造器和递归
payload guard 会拒绝 `TGT-0001`、嵌入式 `camera:TGT-002`、`TargetDrone_1`、
`Target_UAV_7`、`intruder-003` 等仿真真值式编号，但不会拒绝正常
`cam01-track-0001`。中心航迹是只读几何先验，不是节点标签。

候选边遵循“索引、物理门、学习评分”顺序。相机位姿与内参先形成有限深度视锥，视锥包围盒
的中心进入三维空间桶；相机量测时间差和包围盒重叠决定相机对是否可检查。总相机对只按
`C(C-1)/2` 计数，`camera_pair_budget` 限制实际检查数。预算裁剪采用确定性的同桶间隔轮转和
跨桶对角线轮转，避免只覆盖低编号相机。未检查相机对没有足够证据，相关节点保持未绑定。

每个入选相机对再按中心 GlobalTrack 投影支持或时间近邻生成 tracklet 候选，并在几何计算前
限制每节点候选度。随后检查时间窗、本机视场、极线、射线正深度与最近距离、交会角、三角
中点重投影、像素协方差马氏距离，以及两个节点是否被同一个中心 GlobalTrack 投影支持。
最终 degree cap 对门内边按确定性几何 score 排序。图神经网络不得绕过任何门，也不得从被
索引或几何拒绝的 pair 创建边。

2026-07-20 的 5/20/50/100/200 相机结构测试已关闭“全相机对和每对全 tracklet 矩阵”代码
缺口。200 相机样本总对数 19900，配置预算 400 时只检查/保留 400 对，预算丢弃 19500，形成
397 个 tracklet 候选；全部相机至少进入一个候选对。该结论不代表真实 200 路图像、多 seed
准确率、内存峰值或真实 checkpoint 已验收。

原生 PyTorch 模型只学习 `P(same target | candidate edge)`。消息使用 `index_add_` 同时聚合到
两个端点；模型看不到 truth ID 或全局 ID，也不输出 cluster ID/global ID。truth 只在图构建
结束后从独立离线流生成二元边标签；几何最相似的异目标边作为困难负样本，正类权重处理
类别不平衡。小样本 loss 下降只验证训练管线可运行，不代表泛化、校准或准入。

边概率之后仍需受约束聚类：任意合并不得让同一 camera namespace 出现两个 tracklet。
匿名簇再与中心提供的 GlobalTrack 做一对一 Hungarian binding；D5 输出只能引用输入中心 ID，
不得为未绑定簇制造替代 `global_track_id`。低 margin 输出 `ambiguous`，门外输出 `unbound`。

主动视觉接口同样保持最小权限。策略只能请求观察一个既有中心目标、扫描扇区、有限云台增量
或 FOV/变焦。当前观测超时、关联置信度不足或中心 binding 无效时，必须回退到确定性规则
扫描；接口不表达平台机动、重新分配或终端授权。规则路径已在统一三维 episode 驱动模拟相机
并获得 runtime ACK；当前没有已训练或已验收的学习型主动视觉策略，也没有真实 AirSim 云台
或实机闭环。

scalable 3D 在线入口遵循“先隔离、后更新状态”。整个 duck-typed batch 在进入任何 tracker
前先递归检查字段和值；transport `observation_id` 只读进入 `source_observation_id` 审计字段，
不进入身份或模型特征。每个 resource/camera 有独立的
匿名序列和有限漏检状态，episode reset 清空该序列。`vision_bbox` 的中心与 bbox covariance
分别保留为 `2x2` 节点协方差和 `4x4` 审计 metadata；像素位移按 `fx/fy/dt` 转成角速度，bbox
面积比按对数尺度率记录。空扫描只老化本相机 tracker，不伪造预测量测；缺少当前 camera
metadata 时也不复用旧外参冒充新时刻几何。

相机内参、NED 位置和 `R_camera_from_ned` 由 metadata 构造，平移固定为 `t=-R C`。metadata
显式给出 position/attitude covariance 时原样使用；当前 DTO 未给出时采用配置 fallback 并标明
来源，不冒充实测。D2 六维中心状态只复制 position、velocity 和 position covariance，中心 ID
原样保留。边模型仅为调用方可选注入；缺失、异常或低 certainty 时使用确定性几何规则并输出
回退原因，不能把 fallback 写成模型推理。

2026-07-20 的最新代码证据为 D5 全量 `355 passed in 9.48s`。其中 scalable adapter 专项
`17 passed in 2.27s`，覆盖 2/3/4 相机部分可见、跨帧匿名 ID、假目标/漏检、污染拒绝、中心
ID 不变、reset、空扫描、真实 DTO 字段形状和 model/rule 状态。seed 200 的 200 目标/4 相机
合成投影场景形成 800 节点，240000 个跨相机可能 pair 经两级索引后为 3050 个 tracklet
候选、2953 个最终 cap 前候选和 1923 条最终边，密度 `0.006017`、最大度 6，本次
`0.442 s`。另有 5/20/50/100/200 相机结构矩阵；200 相机检查 400/19900 个相机对，预算
丢弃 19500，形成 397 个 tracklet 候选。seed 4 的 8 目标/3 相机小样本训练
使用 24 正边、72 困难负边和正类权重 3.0，60 epoch loss 从 `1.038521` 降到
`0.011535`、训练集准确率 1.0。后者仍是过拟合 smoke，不是模型验收；独立数据/校准软件
管线已实现，但至少 20 个未见 seed、runtime 模型接线和真实图像性能仍为开放项。

## 2026-07-16 真实 ComputerVision 5+1 注册原则复核

独立专项使用 5 个 `1920x1080`/60 度局部相机、1 个 `3840x2160`/75 度侦察相机和
5 个 `Quadrotor1` actor，运行 12 秒、49 帧、seed 7。D5 仍按每个相机 batch 的
`measurement_timestamp` 投影中心航迹；局部相机允许只看到目标子集，侦察相机的
全局视场只增加跨视角证据，不能替代局部相机当前 measured bbox 或触发重新分配。

detect 几何基线的召回/配准/稳定/联合覆盖/侦察全覆盖/IDSW 为
`1.000/1.000/0.975/1.000/0.918/0`，通过全部门限。YOLOv8 + 原生 ByteTrack 为
`0.622/0.996（严格 0.966）/0.955/1.000/0.878/25`，P50/P95 约
`10.42/12.37 ms`。两路 online truth use 和 `global_track_id` rewrite 均为 0。

门限为 detect/YOLO 召回 `>=0.95/>=0.90`、严格配准 `>=0.95`、稳定配准
`>=0.90`、联合覆盖 `>=0.95`、侦察全覆盖 `>=0.90`、IDSW `<=0/<=5`，并保持
truth use/rewrite=0。结论仅支持 detect 几何基线；YOLO+ByteTrack 因召回、IDSW、
侦察全覆盖和多 seed 缺口保持 optional。单 seed 不构成主线晋级，独立专项分支
不替换默认 D1-D7 流程。

该隔离专项未运行 D1/D2。main 根据 actor truth 运动学合成带中心
`global_track_id` 的 `GlobalTrack` fixture，truth 还用于离线评分。
`online_truth_identity_use=0` 只表示 D5 的 local bbox 到 fixture 关联代价、
Hungarian 选择和稳定窗口不读取 actor/object/truth identity；不能将其扩展为整个
专项完全不读取 truth。

## 2026-07-16 人工记录到局部图像观测原则

`manual_records_to_local_image_observations()` 是 manual video 离线支线到模块中立
`LocalImageTrackObservation` 合同的被动适配器。它不执行 GlobalTrack 选择或注册。
每条输出的身份作用域固定为：

```text
sensor_id / stream_id / local_epoch / local_track_id
```

measured 记录保留视频 measurement timestamp，并用显式 `arrival_delay_s` 构造
arrival timestamp；`xywh=(x,y,w,h)` 转为
`xyxy=(x,y,x+w,y+h)`，以 bbox 面积和 `image_size` 调用现有
`adaptive_pixel_covariance_px()` 生成 `2x2` 协方差。逐 local ID 的连续 measured
history 只在相邻 frame 均 measured 时递增；lost 或 frame gap 后从 1 重新开始。
lost 输出必须同时满足 center、bbox、covariance 为空且 confidence 为 0。

安全顺序是先对完整输入序列执行 identity audit，再进行任何输出转换。只要存在同帧
重复中心或超过审计 IoU 阈值的重复量测，就拒绝整批，不能返回部分观测。输出只保留
tracker/association backend、frame index 和 camera-local ID，不包含
`global_track_id` 或 truth identity。

该离线子模块不再由 D5 包根强制导入；默认包导入不应因缺少 manual OpenCV/SciPy
依赖失败。2026-07-16 以既有真实视频 475 条记录复核为
`470 measured / 5 lost`，重复量测 0；D5 全量 `288 passed`，接受阈值为零失败、
重复坍缩必须拒绝、lost 不得携带 stale 量测。限制是人工初始化单相机离线记录，
未接入默认 AirSim、跨视角融合或控制许可。

## 2026-07-15 人工初始化本地视频轨迹

D5 新增的 `manual_video_tracker.py` 是单相机离线诊断工具。人工首帧 ROI 只定义目标数量、初始位置和 `local-001...` 顺序。默认保留每目标独立 CSRT，KCF 作为对照；对小型亮目标可使用 `bright_hungarian`，按 `gray - GaussianBlur(31x31)` 提取全帧匿名正对比候选，并用常速度预测、20 像素运动门和 Hungarian 算法完成一对一分配。

设第 `t` 帧灰度图为 `G_t`，局部对比响应为：

```text
R_t = G_t - GaussianBlur_31x31(G_t)
C_t = LocalMax(R_t),  R_t(q_j) >= 12
```

`C_t` 只产生匿名像素候选 `q_j`，不携带真实目标 ID。候选在全帧提取，不写死 y 坐标范围；背景峰由轨迹运动门剔除。人工 ROI 第一次赋予本地 ID 后，第 `i` 条轨迹采用最近两次有效量测作常速度外推：

```text
v_i = (p_i,k - p_i,k-1) / (f_k - f_k-1)
p_hat_i,t = p_i,k + v_i (f_t - f_k)
```

关联代价以预测距离为主，CSRT proposal 只占小权重：

```text
c_ij = ||q_j - p_hat_i,t||_2 + 0.05 ||q_j - p_csrt_i,t||_2
```

Hungarian 求解时，每条轨迹最多选择一个候选，每个候选最多支持一条轨迹。最终还要求 `||q_j-p_hat_i,t|| <= 20 px`；超门限与无候选都不得输出当前量测。

一对一约束意味着同一候选不能同时支持两个本地 ID。未匹配轨迹只能输出 lost，bbox/center 为空；短时恢复沿用人工初始化 ID。summary 同时审计重复量测对数、重复帧数、最小中心间距和最大框交并比，禁止把 `tracker.update=True` 直接解释为身份连续。

重复量测审计对每帧所有 measured pair 计算中心距离和边界框交并比。当中心距离不大于 `1e-6 px`，或交并比不小于 `0.70` 时，计为一个 duplicate measurement。该审计是本地轨迹塌缩告警，不是 GlobalTrack 身份判断。

`b.mp4` 的 95 帧结果为五 ID 有效/丢失 `92/3、95/0、93/2、95/0、95/0`，`duplicate_measurement_count=0`。纯 CSRT 的 `95/95 measured` 对照已发生身份塌缩，只能作为失败案例。该能力不是 GlobalTrack 注册、敌我识别、跨视角融合、D7 控制许可或 MOT 算法准入证明。

2026-07-15 验证为 1 个真实视频、95 帧、5 个 ID、475 条记录，D5 全量 `284 passed`，零测试失败。

## 2026-07-15 M5N2 20-case 原理验证边界

真实 AirSim M5N2 baseline/candidate 各 10 seeds 已证明 D5 能在全部 `3725` 个适用 tick 上保持第二 primary 的中心绑定并输出 `locked/ambiguous/reacquire` 与逐 tick 首断点；online truth identity/state use 均为 0。第二 primary 必须由每场 current active-primary 合同确定，不能由固定资源编号或 AirSim actor ID推断。

本原理验证严格限定于上述 20 个 M5N2 case；TERM 生效前额外完成的 `png_ttc_2v2_seed001` 不纳入统计，dropout case 执行数为 0。20 个第二 primary 最终均记录为 `collision_stop`，该字段仅是 D7 停控证据；由于碰撞对象未持久化，不能把该状态或 `0/20` 单独归因于 D5。

本批同时说明“几何关联锁定”和“可执行交接”不能合并：`locked=1721/3725`，但 bbox stable 和 handoff-ready 仅 `161/3725`，严格 complete 仅 `52/3725`，第二 primary 5 m 为 `0/20`。因此 D5 继续坚持当前 measured bbox、候选唯一性、时效、合同和安全门全部成立后才交接；短时 locked、跨视角支持或 coalition consensus 都不能单独授予控制。直接 `failure_category` 未随本批 artifact 持久化，真实证据只支持 stage/reason 口径。

## 2026-07-15 第二主用资源失败漏斗原则

D5 不用新的身份接口解释第二 primary 失败，而是复用终端关联已有的可见性、投影、马氏门、bbox、候选、双时间戳、计划版本、友方/重复锁定和稳定历史证据。现有 cooperative summary 增加只读 `failure_category`：不可见、投影无效、几何门拒绝、bbox 不稳定或裁切、候选不唯一、量测陈旧、计划/全局身份合同不一致、友方/重复锁定冲突、已关联但稳定锁定不足。分类只服务于 main/D6 统计，不参与控制决策。

错误 `assigned_global_track_id` 的资源证据必须显式归为合同冲突，不能被当作新目标绑定，也不能被掩盖成不可见。2026-07-15 以 11 个确定性 case 验证，D5 全量 `272 passed`；未运行 AirSim，真实多 seed 性能 P1 保持开放。

## 2026-07-14 actual-v2 证据分层原则

2026-07-14 的真实 AirSim actual-v2 只有 tuned 2v2 和 M5N2 各 1 个 seed。两者均使用默认 AirSim detect，不保存 PNG。canonical actual 的 contract/control/terminal-switch/mode/physical 五层均独立 available，总计 `102/26/26/2/4`；`terminal_switch_allowed_count` 从最终 `control_commands.csv` 独立统计，2v2/M5N2 为 `26/0`，不从 control 层推断。2v2 的 `terminal_lock_count=3`、visual/mode switch `2/2`，M5N2 为 `24/0/0`。因此 D5 的 lock acquisition transition、D7 有效视觉控制、terminal switch 和实际 mode switch 必须作为不同证据层，禁止互相推断。

M5N2 的 active pair/target/coalition 结果分别为 `2/3`、`2/2`、`0/1`，第二 primary 最近约 `11.02 m`。target `2/2` 不能覆盖第二 primary 未进入 5 m 和 coalition 显式失败。两 case 的 online identity/state truth use 均为 `0/0`；D5 仍不得以 actor/object truth ID 做在线 acquisition、registration 或 gate，也不得创建、改写或换绑 center-owned `global_track_id`。

本批通过 actual artifact 与 canonical 五层 schema `2/2` available 的 P0 证据可用性门，D6 formal overall status 为 `fail`。D5 当前开放 P1 是 M5N2 第二 primary、真实几何 drift、detect/YOLO/MOT 多 seed 和二级同 tick freshness；不是五层 schema 缺口。IBVS、真实身份源、完整在线 PnP/ROS 2 保持 P2/P3。M5N2 至少 `8/10` 的既有视觉完成门与 physical coalition `0/1` 分母独立；单 seed 的 terminal switch 或 target 成功不能宣称完整 D5 视觉闭环。

## 2026-07-14 几何锁定与执行锁定分层原则

几何 `locked` 只表示当前相机局部轨迹在投影门内唯一支持既有 `assigned_global_track_id`，不等于允许末端视觉控制。D5 现在另行计算 `execution_lock_allowed`：必须存在本资源、本相机、作用域一致的 measured bbox，成员与版本合同完整，连续 measured lock 和 bbox 尺度/稳定性达标，并继续通过 identity、friend、duplicate、calibration 与授权门。任一条件缺失时只保留 `association_lock_only`，不得由下游把历史或 cross-view/predicted 证据冒充当前本机测量。

`local_visual_evidence` 与 `d7_handoff_input` 使用同一 truth-free producer identity，包含 bbox/中心、resource/camera/stream/backend、measurement/arrival timestamp、local state、连续 lock 与 bbox stability。producer scope 与当前资源相机冲突时输出 `hold`；D5 不尝试改绑 `global_track_id`。2026-07-14 确定性回归为 `261 passed`。真实 AirSim 持续检测、bbox 尺度、异常大框和多 seed 是实验 P1，不因合同代码通过而宣称闭合。

## 2026-07-14 live visual funnel 原则

D5 的“看到目标”“几何匹配”“执行锁定”“连续 measured 锁定”“bbox 稳定”和“建议 D7 handoff”是六个不同事实，不能再用单个 `d5_not_locked` 合并表达。`d5_live_visual_funnel_v1` 按固定顺序输出这些事实及首个失败阶段，并保持 measurement/arrival timestamp、plan/version、local track、friend、duplicate、calibration 和 center-owned `global_track_id` 证据。

连续 measured lock 只累计同一 resource-target-camera-local track 在当前执行合同下的 measured `locked`。raw visual match 即使正确，只要 arrival window、授权、成员合同或安全门拒绝，连续执行锁定立即清零；该计数仅用于诊断，绝不把 hold/ambiguous/reacquire 提升为 locked。最新 seed-1 中 INT-02 早期已经 raw locked，但 bbox 晚于到达窗口才稳定，正说明必须分层，而不能放宽 D5 门限。

## 2026-07-14 bbox 稳定历史的连续身份原则

D5 将 bbox/MOT/stable-lock 历史归属于 resource-target-local track-camera-stream-detector/tracker backend 与 committed/current membership，而不是归属于滚动 plan version。仅 plan/coalition version 刷新且上述连续身份不变时，measured 历史可继承；换绑、换员、local track、camera/backend/stream、producer reset、predicted/lost 或 identity/friend/duplicate conflict 必须 fail closed 重置。M-to-N 共同视觉只统计 current committed active primary，不能用旧成员补窗口，也不能改写中心拥有的 `global_track_id`。

审计字段包括 history length、bbox area CV、reset reason、key/signature、measured/predicted source、source plan versions、合同完整性与 raw/effective MOT length。postfix seed-1 旧产物的 M5N2 两组 `bbox_stable=true=0/1388`、T001 consensus `13/347`/`12/347`，2v2 PNG/TTC `0/52`；根因是单 tick 输入使 `visible_frame_count <= 1`，另有 `326/347` T001 tick 的真实 membership 变化。2026-07-14 D5 全量 `255 passed`，零失败；未新增 AirSim 运行，门限和 native-MOT 准入状态不变。

## 2026-07-14 原生多目标跟踪历史的工程口径

原生 ByteTrack/BoT-SORT 的 `tracker id` 只是相机本地身份，Ultralytics `Results` 不直接提供 D5 所需的连续实测历史。D5 因此按“资源、相机、原生 backend、本地 tracker id”维护 `mot_history_length`：同一 ID 每个连续有检测的帧增加 1；空帧、ID 变化、backend 切换和 reset 都打断连续实测历史。短时遮挡期间可在 `max_track_age_frames` 内保留 ID 生命周期，但恢复帧仍从 1 开始，避免把 coast 或长期 ID 复用当成满足 `min_mot_history=2` 的锁定证据。

原生异常进入 IoU fallback 时，原生模型和原生历史失效；fallback 使用自己的相机流历史，原生恢复后重新初始化。2026-07-14 的 Results-like 回归覆盖 6 个新增测试实例，D5 全量 `241 passed`，接受阈值为零失败。该证据只关闭代码断点，不表示真实 AirSim 多 seed 原生 MOT 已准入，也不改变友方、duplicate、版本、时间戳、标定或 `global_track_id` 门控。

## 2026-07-14 输出状态的安全边界

D5 的保守性分为两个层级：

- `ambiguous`、普通 `hold/reacquire`、geometry gate、bbox/时序不稳定是当前 `resource_id + assigned_global_track_id` pair 的视觉不确定性。它们阻断 D7 视觉切换并可请求 secondary cue/reacquire，但不证明整架资源失效；一致性层不得输出 `report_conflict/arbitrate`。
- verified friend、身份 spoof、duplicate lock、assignment authorization/version 或 local/global ID conflict 是安全冲突。它们 fail closed，并通过 `conflict/inconsistent + report_conflict/arbitrate` 允许 hard planner feedback。

未知类别、缺失身份、stale/unverified 身份都不是敌方证据。D5 只引用中心给定 `global_track_id`，online truth use 恒为 0。2026-07-14 的 TerminalAssociation/consistency/distributed cross-view 专项为 `52 passed`，当时 D5 全量为 `235 passed`，门槛为零失败；本日原生 MOT 历史修复后最新全量为 `241 passed`。这些都是合同/代码级验证，不是 AirSim 资源健康实验。

## 0. 缩写、产品和记号约定

为避免后文出现无中文解释的英文缩写，本节先给出全文会使用的缩写和产品名：

- 北-东-地坐标系（North-East-Down, NED）：D5 接收三维全局航迹时使用的工作坐标系。
- 应用程序编程接口（Application Programming Interface, API）：模块之间的函数或数据合同。
- 第一研究模块传感器融合（Sensor Fusion, D1）、第二研究模块数据关联（Data Association, D2）、第三研究模块分配规划（Assignment Planner, D3）、第四研究模块分布式降级（Distributed Fallback, D4）、第六研究模块评估指标（Evaluation Metrics, D6）和第七研究模块比例导航（Proportional Guidance, D7）：D5 的上下游协作模块。
- 多目标跟踪（Multi-Object Tracking, MOT）：在连续图像中维持相机本地目标轨迹标识的过程。
- 只看一次目标检测器（You Only Look Once, YOLO）：可选图像检测器；当前适配版本为 YOLOv8。
- 交并比（Intersection over Union, IoU）：两个二维边界框交集面积与并集面积之比。
- 身份切换次数（Identity Switch, IDSW）：同一离线真值对象被不同本地轨迹标识接续的次数。
- 第 95 百分位数（95th Percentile, P95）：延迟分布中 95% 样本不超过的数值。
- 视场角（Field of View, FOV）：相机可成像的角度范围。
- 视线（Line of Sight, LOS）：相机到目标的视向；D5 只提供相关视觉证据。
- 比例导航（Proportional Navigation, PN）和比例导航导引（Proportional Navigation Guidance, PNG）：D7 使用的导引方法；D5 不计算导引控制量。
- 透视 n 点（Perspective-n-Point, PnP）：用三维参考点和二维像点估计相机位姿的问题。
- 随机采样一致性（Random Sample Consensus, RANSAC）：用于含离群点模型估计的鲁棒抽样方法。
- 重识别（Re-Identification, ReID）：利用外观特征在遮挡或跨相机后恢复对象身份的方法。
- 中央处理器（Central Processing Unit, CPU）和图形处理器（Graphics Processing Unit, GPU）：可选图像算法的计算设备。
- 零级、一级和二级优先级（Priority 0/1/2, P0/P1/P2）：项目风险与实施优先级标签，不表示算法版本。
- 微软 AirSim 无人系统仿真器：当前真实仿真运行环境；`simGetDetections`（仿真检测元数据接口）是 D5 默认在线检测输入。
- AirSim 内置 SimpleFlight 飞行控制器：main runtime 用于物理闭环验证的飞行控制后端，不属于 D5。
- OpenCV 开源计算机视觉库（Open Source Computer Vision Library, OpenCV）：D5 默认投影可调用其 `projectPoints`（三维点投影函数），也用于隔离式离线几何对照。
- NumPy 数值计算库：矩阵、协方差和向量计算的基础库。
- SciPy 科学计算库：可用时提供匈牙利线性和分配求解；不可用时使用确定性唯一匹配回退。
- Ultralytics 视觉模型运行库：可选加载本地 `best.pt`（模型权重文件）并运行 YOLOv8、ByteTrack 多目标跟踪算法或技巧集增强的简单在线实时跟踪（Bag of Tricks for Simple Online and Realtime Tracking, BoT-SORT）。
- `pytest`（Python 自动化测试框架）：D5 模块既有回归测试的执行工具。
- 像素（pixel, px）：图像平面坐标和残差单位。

代码字段在首次出现处给出中文语义；数据结构表中“字段”列的每一项均由“中文语义”列解释。公式中的粗体小写字母表示向量，粗体大写字母表示矩阵。

## 1. 模块定位与边界

### 1.1 系统定位

D5 位于“中心全局航迹与资源分配”之后、“末端视觉证据消费”之前。它回答的不是“应该把哪个资源分给哪个目标”，而是：

> 在某资源已经收到一个中心分配的全局航迹后，当前相机本地检测或本地视觉轨迹是否以足够唯一、稳定、及时且身份安全的证据支持这个既有全局航迹？

当前默认主线可概括为：

```text
中心全局航迹与协方差
  -> 预测到相机量测时刻
  -> 相机投影与像素协方差传播
  -> 相机本地检测框中心
  -> 马氏距离门控与候选代价
  -> 版本、授权、身份和时间稳定性门控
  -> locked / ambiguous / hold / reacquire
  -> 跨视角摘要、D4 仲裁证据、D6 评估字段、D7 前置证据
```

其中 `locked`（唯一且满足门控的锁定）、`ambiguous`（候选或证据仍有歧义）、`hold`（合同或身份冲突，保持不执行）和 `reacquire`（需要重新获取视觉证据）是 D5 的四个主决策状态。

### 1.2 工程问题

末端相机可能同时看到：中心分配目标、其他未分配目标、友方或协同平台、身份未知对象，以及由遮挡、图像边缘截断或检测抖动产生的伪候选。本地轨迹标识只在一个资源和一台相机内有意义，不能替代中心全局身份。工程上必须同时解决：

1. 三维全局航迹与二维检测框的坐标、时间和不确定度对齐；
2. 多候选情况下的唯一匹配，而不是选择最近或最大的框；
3. 检测暂失、本地轨迹标识切换和恢复后的迟滞；
4. 计划版本滚动、联盟成员变化、主用/备用状态和授权窗口约束；
5. 多相机分辨率不同、相机位姿不确定和二级侦察线索作用域；
6. 在线决策与 AirSim 真值评分隔离，防止仿真标签泄漏。

### 1.3 科学问题

D5 当前研究的是带身份安全约束的概率几何关联问题：

- 三维状态协方差投影到二维后，马氏距离门控能否在高不确定度与近邻多目标之间取得可解释平衡；
- 几何残差、像面角速度、类别、检测质量和时序稳定性如何组成保守代价；
- 单视角证据、跨视角支持和协同多资源合法锁定如何区分；
- 在不创建新全局身份的前提下，如何把歧义、重复锁定风险和二级节点证据交给上游仲裁；
- 检测器、相机标定、时间同步与局部跟踪误差如何传导到末端锁定率和错误锁定风险。

### 1.4 明确边界

D5 当前严格遵守以下边界：

- 不创建、修改、换绑或重新分配 `global_track_id`（中心拥有的全局航迹标识）。
- 不生成新的分配计划，不选择主用/备用资源，不决定联盟成员。
- 不触发中心、二级或完全分布式模式切换，只提供 D4 可消费的被动证据。
- 不调用 AirSim 控制接口，不输出速度、加速度、姿态、导引指令或拦截点。
- 不把身份未知解释为对抗身份；只有正向验证的友方声明能够触发友方冲突保护。
- 不使用 AirSim `object_id`（仿真对象标识）、`actor_name`（仿真实体名称）或其他真值身份参与 D5 在线关联；仿真编排可用 truth 构造明确标注的输入 fixture，评价器可用 truth 离线评分，但这些 identity 不得进入 D5 关联代价、Hungarian 选择或稳定窗口。
- 不涉及真实火控、毁伤评估、自动授权、自动处置或绕过人工审核。
- 当前代码用于科研仿真、离线评估和人工审查，不等同实机安全认证。

## 2. 上游输入、核心数据结构与下游输出

### 2.1 上游输入

| 来源 | 当前输入 | D5 使用方式 | 安全约束 |
| --- | --- | --- | --- |
| D1/D2 | 三维位置、速度、协方差、时间戳和中心全局航迹标识 | main 适配器形成 D5 `GlobalTrack`（全局航迹） | D5 只读标识，不回写全局表 |
| 第三研究模块（D3） | 版本化分配、资源、联盟、角色、激活态和到达窗口 | 形成 `Assignment`（只读分配合同）或 `GlobalTrackBinding`（既有全局航迹绑定） | 旧版本、未授权或未激活合同保守拒绝 |
| main runtime | 每相机图像尺寸、内参、位姿、检测框、量测与到达时间 | 形成 `CameraModel`（相机模型）和 `LocalVisualTrack`（相机本地视觉轨迹） | main 负责 AirSim 启停、采集、重置和日志 |
| 友方身份来源 | 仿真字典形式的合作身份声明 | `IdentityChecker`（身份检查器）转换为 `IdentityClaim`（身份声明） | 当前不是实际通信或密码认证适配器 |
| 二级侦察节点 | 已重投影到本地相机平面的图像线索 | `ReconImageCue`（二级侦察图像线索）只降低适用候选代价 | 不能代替版本、授权、友方或唯一性门控 |
| 第四研究模块（D4）降级上下文 | 联盟提交状态、时期、租约、成员确认和当前模式 | 协同摘要检查完全分布式执行合同 | D5 不据此自行切换模式 |

### 2.2 核心数据结构

#### `GlobalTrack`（中心全局航迹）

| 字段 | 中文语义 |
| --- | --- |
| `global_track_id` | 中心拥有的全局航迹标识 |
| `position` | NED 三维位置向量，单位为米 |
| `velocity` | NED 三维速度向量，单位为米每秒 |
| `covariance` | 三维位置协方差矩阵 |
| `timestamp` | 航迹状态时间戳 |
| `track_version` | 航迹版本，需与分配版本匹配 |
| `category` | 对象类别；未知类别保持中性 |

该结构是冻结数据类，配合运行时输入/输出标识断言，防止 D5 意外改写全局标识。

#### `CameraModel`（针孔相机模型）

| 字段 | 中文语义 |
| --- | --- |
| `K` | 三乘三相机内参矩阵 |
| `R` | 世界/NED 到相机坐标系的旋转矩阵 |
| `t` | 世界/NED 到相机坐标系的平移向量 |
| `image_size` | 每台相机独立的图像宽度和高度 |
| `measurement_cov` | 像面量测噪声协方差 |
| `dist_coeffs` | 可选镜头畸变系数 |

#### `LocalVisualTrack`（相机本地视觉轨迹）

| 字段 | 中文语义 |
| --- | --- |
| `local_track_id` | 仅在资源/相机流内有效的本地轨迹标识 |
| `center_px` | 检测框中心像素坐标 |
| `bbox` | 二维边界框，顺序为左上和右下坐标 |
| `bearing_rate` | 像面视向变化率，单位为像素每秒 |
| `quality` | 检测或跟踪质量，范围为零到一 |
| `mot_history_length` | 本地连续实测命中帧数；原生 MOT 的空帧/coast、ID/backend 切换和 reset 会中断累计 |
| `timestamp` | 量测时间戳 |
| `arrival_timestamp` | 数据到达 D5 的时间戳 |
| `exposure_timestamp` | 相机曝光时间戳 |
| `local_track_state` | `measured`（当前有实测）、`predicted`（仅本地预测）或 `lost`（当前丢失） |
| `prediction_age_s` | 本地预测或丢失证据年龄，单位为秒 |
| `track_transition_state` | 初始化、连续、切换、重获或重置状态 |
| `detection_source` | 检测来源，例如 AirSim 检测元数据或 YOLOv8 |
| `image_size` | 该流独立图像尺寸 |
| `camera_geometry` | `CameraGeometryEvidence`（相机几何与同步证据） |

`predicted` 和 `lost` 状态不能产生 `locked` 或 `registered`（已注册）输出。

#### `Assignment`（D3/D4 只读分配合同）

| 字段组 | 中文语义 |
| --- | --- |
| `assigned_global_track_id` | 当前资源被分配的中心全局航迹标识 |
| `assignment_version` | 与航迹版本比对的分配版本 |
| `plan_id`、`plan_version` | 计划标识和计划版本 |
| `authorization_state` | 授权状态；默认主线只接受代码定义的已批准状态 |
| `resource_id` | 资源标识 |
| `coalition_id`、`coalition_version` | 联盟标识与联盟版本 |
| `member_role`、`activation_state` | 成员角色与激活状态 |
| `required_resource_count` | 当前目标所需资源数 |
| `arrival_window_start_s`、`arrival_window_end_s` | 允许执行的到达时间窗口 |
| `terminal_authorization_scope` | `coalition`（联盟共同口径）或 `per_primary`（逐主用资源口径） |
| `arrival_coordination_required` | 是否要求到达协同 |

#### 身份、侦察与跨视角结构

- `IdentityClaim`（身份声明）：保存平台、声明类型、认证状态、可选本地轨迹标识、像素中心/边界框、时间戳和是否友方。
- `ReconImageCue`（二级侦察图像线索）：保存生产节点、图像帧、可选既有全局航迹标识、像素中心、置信度、资源作用域和指向误差元数据。
- `TerminalObservation`（末端观测）：被动总线载荷，可携带本地视觉轨迹、D5 决策、身份声明和侦察线索，同时保留量测/到达双时间戳。
- `CrossViewAssociation`（跨视角关联摘要）：按既有全局航迹标识汇总资源支持、命名空间化本地轨迹、歧义和重复锁定风险。
- `TerminalConsistencySummary`（末端一致性摘要）：保存连续状态计数、锁定年龄、候选代价间隔、跨视角支持和建议 D4 动作。

### 2.3 下游输出

主输出 `TerminalAssociation`（末端关联决策）包含：

| 字段 | 中文语义 |
| --- | --- |
| `assigned_global_track_id` | 原样回显上游中心全局航迹标识 |
| `local_track_id` | 选中的相机本地轨迹标识；无候选时为空 |
| `association_confidence` | 基于几何、质量和历史的关联置信度 |
| `ambiguity_score` | 由最佳/次佳代价间隔导出的歧义分数 |
| `friend_conflict_state` | 友方重叠或可疑身份状态 |
| `decision_state` | 四态决策结果 |
| `reason` | 首要接受或拒绝原因 |
| `candidate_costs` | 候选本地轨迹及总代价 |
| `recon_cue_used` | 二级侦察线索是否实际降低了所选候选代价 |
| `measurement_timestamp`、`arrival_timestamp` | 量测时间和到达时间 |
| `measurement_age_s` | 到达时间减量测时间得到的证据年龄 |
| `truth_identity_used` | 在线是否使用真值身份；结构强制为假 |
| `metadata` | 投影、协方差、门控、标定健康、稳定性和执行合同诊断 |

辅助输出包括：

- `TerminalObservationBus.runtime_records()`（运行时记录）供 main 和第六研究模块（D6）写盘与评估；
- 跨视角和联盟视觉摘要供 D3/D4 识别合法协同锁、超额锁定或合同冲突；
- `PerPrimaryTerminalEvidence`（逐主用资源末端证据）供 5 个资源、2 个目标（M=5，N=2，简称 M5N2）的场景分资源诊断；
- `SecondaryFrameAssociationEvidence`（二级节点单同步帧证据）供 D4 同一决策时刻消费；
- D7 的视觉 PNG 前置元数据。该元数据只是建议，不是控制许可。

## 3. 坐标、相机与时间模型

### 3.1 航迹时间预测

对航迹时间戳 \(t_0\) 与相机量测时刻 \(t\)，当前实现采用常速度预测：

\[
\mathbf{p}(t)=\mathbf{p}(t_0)+\mathbf{v}(t_0)\Delta t,\qquad
\Delta t=t-t_0.
\]

其中 \(\mathbf{p}\) 是 NED 三维位置，\(\mathbf{v}\) 是 NED 三维速度。向未来预测时，代码对三维位置协方差作保守膨胀：

\[
\mathbf{P}(t)=\mathbf{P}(t_0)+
\min(0.05\Delta t^2,25)\mathbf{I}_3.
\]

这里 \(\mathbf{P}\) 是三维位置协方差，\(\mathbf{I}_3\) 是三阶单位矩阵。该项是轻量过程不确定度补偿，不是完整运动滤波器，也不是 D5 自建全局航迹。

量测时刻优先顺序为：显式 `current_time`（当前决策时间）、本地视觉轨迹最新量测时间、分配时间，最后才是全局航迹时间。这样可以在不使用到达时间替代量测时间的前提下补偿传输延迟。

### 3.2 世界到相机坐标变换

对 NED 世界点 \(\mathbf{P}_w\)，相机坐标为：

\[
\mathbf{P}_c=
\begin{bmatrix}X_c & Y_c & Z_c\end{bmatrix}^{\mathsf T}
=\mathbf{R}\mathbf{P}_w+\mathbf{t}.
\]

\(\mathbf{R}\) 和 \(\mathbf{t}\) 分别是世界到相机旋转和平移。若 \(Z_c\le 0\)，目标位于相机后方，投影无效。AirSim 相机轴从前/右/下转换到 OpenCV 光学轴右/下/前，四元数按相机到世界方向解释后取逆得到世界到相机旋转。

### 3.3 针孔投影

忽略畸变时：

\[
u=f_x\frac{X_c}{Z_c}+c_x,\qquad
v=f_y\frac{Y_c}{Z_c}+c_y.
\]

\(u,v\) 是预测像素，\(f_x,f_y\) 是水平和垂直焦距，\(c_x,c_y\) 是主点。矩阵形式为：

\[
\lambda
\begin{bmatrix}u\\v\\1\end{bmatrix}
=\mathbf{K}\left(\mathbf{R}\mathbf{P}_w+\mathbf{t}\right).
\]

OpenCV 可用时，代码调用其投影函数并消费可选畸变系数；不可用时退回上述针孔公式。投影落在图像外或产生非有限值时，不进入几何门控。

AirSim 设置给出图像宽度 \(W\)、高度 \(H\) 和水平视场角 \(\theta\) 时，当前辅助函数使用：

\[
f_x=f_y=\frac{W}{2\tan(\theta/2)},\qquad
c_x=\frac{W}{2},\quad c_y=\frac{H}{2}.
\]

该 FOV 水平口径仍需对具体 AirSim 版本和图像类型做真实标定，不是通用相机定律。

### 3.4 协方差投影

针孔模型对世界位置的雅可比矩阵为：

\[
\mathbf{J}=
\begin{bmatrix}
f_x/Z_c & 0 & -f_xX_c/Z_c^2\\
0 & f_y/Z_c & -f_yY_c/Z_c^2
\end{bmatrix}\mathbf{R}.
\]

像素协方差传播为：

\[
\boldsymbol{\Sigma}_{px}
=\mathbf{J}\mathbf{P}\mathbf{J}^{\mathsf T}
+\mathbf{R}_{meas}+\epsilon\mathbf{I}_2.
\]

\(\boldsymbol{\Sigma}_{px}\) 是二维投影协方差，\(\mathbf{R}_{meas}\) 是相机像面量测协方差，\(\epsilon=10^{-6}\) 是默认数值正则项。协方差不是仅供日志的装饰字段，它直接决定马氏门的方向和尺度。

### 3.5 混合分辨率

每个 `(resource_id, camera_id)`（资源与相机联合键）保存独立图像尺寸。固定像素门限按参考分辨率 \(640\times480\) 的图像对角线缩放：

\[
s=\frac{\sqrt{W^2+H^2}}{\sqrt{640^2+480^2}}.
\]

友方中心距离、侦察线索距离、角速度标准差和重获取搜索半径均乘以 \(s\)。完全分布式的跨视角辅助算法则把像素中心、协方差和边界框面积归一到 \(640\times480\) 参考平面后比较。该实现已支持同一运行中混用 \(1920\times1080\) 与 \(3840\times2160\) 相机，但并不自动证明远距检测质量。

### 3.6 双时间戳与证据年龄

D5 区分：

- `measurement_timestamp`（量测时间戳）：图像/检测实际对应的时刻；
- `arrival_timestamp`（到达时间戳）：该证据进入处理链的时刻；
- `exposure_timestamp`（曝光时间戳）：相机曝光时刻，缺省时回退到量测时间；
- `measurement_age_s`（量测年龄）：到达时间减量测时间。

默认 `AssociationConfig.max_measurement_age_s`（关联器最大量测年龄）为空，因此常规实测候选的绝对时效阈值必须由 runtime 配置或后续 D7 门控明确给出；不能把“字段存在”写成“默认已启用严格时效拒绝”。另一方面，丢失/预测证据默认最多保留 0.25 秒，超过后保持 `reacquire` 并把原因改为 `terminal_visual_evidence_expired`（末端视觉证据过期）。D7 前置建议另有默认 0.35 秒量测年龄上限。

## 4. 默认主线关联算法

### 4.1 几何门控

对本地像素量测 \(\mathbf{z}=[u_l,v_l]^{\mathsf T}\) 和全局航迹预测像素 \(\hat{\mathbf{z}}\)，残差为：

\[
\mathbf{r}=\mathbf{z}-\hat{\mathbf{z}}.
\]

平方马氏距离为：

\[
d_M^2=\mathbf{r}^{\mathsf T}
\boldsymbol{\Sigma}_{px}^{\dagger}\mathbf{r},
\]

其中 \(\dagger\) 表示伪逆。默认门限是：

\[
d_M^2\le 9.21.
\]

该值对应二维卡方分布约 99% 概率门。门外候选代价被设为大数 \(10^{12}\)，不参与后续选择。门控使用检测框中心，不使用 AirSim 对象身份或真值映射。

### 4.2 候选总代价

门内候选总代价为：

\[
C=d_M^2+C_{rate}+C_{class}+C_{quality}+C_{friend}+C_{recon}.
\]

各项物理意义如下。

#### 像面变化率一致性

\[
C_{rate}=w_r
\frac{\lVert\dot{\mathbf{z}}_l-\dot{\mathbf{z}}_g\rVert_2^2}
{(\sigma_r s)^2}.
\]

\(\dot{\mathbf{z}}_l\) 是本地像面变化率，\(\dot{\mathbf{z}}_g=\mathbf{J}\mathbf{v}\) 是全局速度预测的像面变化率。默认 \(w_r=1\)、\(\sigma_r=40\) 像素每秒，\(s\) 是分辨率尺度。

#### 类别一致性

未知类别不加分也不扣分。`uav`、`drone`、`intruder` 等检测标签先统一为“无人机”对象类别；统一仅处理对象类别，不推断友方或对抗属性。两个已知类别不一致时，默认代价增加 16。

#### 质量与历史

\[
C_{quality}=2(1-q)+0.5\max(0,2-h),
\]

其中 \(q\in[0,1]\) 是本地质量，\(h\) 是 MOT 历史帧数。该项让低质量和短历史候选更难锁定，但不会替代后续硬门限。

#### 身份冲突

- 已验证友方重叠：代价增加 \(10^6\)，并由决策逻辑直接输出 `hold`；
- 疑似伪造、过期或未验证的友方重叠：代价增加 6，候选即使最佳也输出 `ambiguous`；
- 无声明或身份未知：身份代价为零，仍只按几何和质量判断，不推断为对抗目标。

身份重叠可由相同本地轨迹标识、边界框 IoU 至少 0.05，或中心距离不超过默认 \(20s\) 像素判定。`IdentityChecker.max_age_s`（身份声明最大年龄）默认 2 秒。

#### 二级侦察线索

适用的二级线索可给候选一个负代价：

\[
C_{recon}=-2q_c,
\]

其中 \(q_c\) 是线索置信度。线索中心与本地候选距离需不超过默认 \(30s\) 像素，并同时满足：全局航迹一致、资源作用域一致、年龄不超过 1 秒、目标相机帧一致，且跨相机线索已明确重投影。线索只能改善候选排序，不能越过授权、版本、友方、稳定性或执行门控。

### 4.3 唯一候选与置信度

把门内候选按总代价升序排列，最佳和次佳代价分别记为 \(C_1,C_2\)，间隔为：

\[
\Delta C=C_2-C_1.
\]

只有一个候选时，间隔视为无穷大。正常锁定默认要求：

- \(C_1\le14\)；
- \(\Delta C\ge3\)；
- 本地质量 \(q\ge0.6\)；
- MOT 历史 \(h\ge2\)；
- 当前状态必须是 `measured`；
- 无友方冲突、旧计划、版本冲突或执行合同阻断。

当前置信度为：

\[
\gamma=
\exp\left(-\frac{1}{2}\min(100,d_M^2)\right)
q\min\left(1,\frac{h}{5}\right).
\]

有限间隔时的歧义分数为：

\[
a=\frac{1}{1+\max(0,\Delta C)}.
\]

只有一个候选时 \(a=0\)。这些是解释性分数，最终状态仍由硬门控决定。

### 4.4 一对多与多对多匹配

`TerminalAssociator.decide()`（单资源末端决策）只评估 D3 已分给该资源的一个全局航迹，不允许本地候选把分配改成另一个全局航迹。默认 main runtime 对每个资源-目标分配分别调用该方法。

几何批量验证和检测到既有全局航迹注册会构建多航迹、多检测代价矩阵。SciPy 可用时使用匈牙利线性和分配，保证每行每列至多选择一次；不可用时按代价排序执行确定性贪心唯一匹配。无论哪种后端，都只能关联到输入中已经存在且有上游绑定的全局航迹。

### 4.5 选型理由

当前主线选择“时间预测 + 针孔投影 + 协方差传播 + 马氏门控 + 可解释代价”，原因是：

1. 能直接消费 D1/D2 已有三维状态和协方差，不建立第二套身份系统；
2. 门限具有统计含义，比固定像素半径更能适应距离和航迹质量变化；
3. 每个拒绝可以落到投影、门控、唯一性、质量、身份、版本或时效的具体原因；
4. 对当前 AirSim 数据规模计算量可控，且没有训练依赖；
5. 错误锁定成本高于暂不锁定，因此保守四态比强制每帧匹配更符合模块职责。

## 5. 状态机、迟滞与重获取

### 5.1 四态判定

| 状态 | 进入条件 | 典型原因 | 下游语义 |
| --- | --- | --- | --- |
| `locked` | 唯一门内实测候选通过代价、质量、历史、身份、版本和执行门控 | `unique_candidate_inside_gate`（门内唯一候选） | 仅表示 D5 视觉关联成立，仍需 D7 独立门控 |
| `ambiguous` | 有候选但唯一性、质量、历史、身份可信度或时序稳定性不足 | 候选间隔不足、质量过低、历史太短、身份未验证 | 继续观测或请求二级线索 |
| `hold` | 当前视觉证据暂停，或计划/身份安全门控阻断 | bbox/时序不稳、备用未激活、旧计划、版本/授权冲突、友方重叠 | 普通 hold 只请求线索；明确安全冲突才报告/仲裁，均不执行视觉接管 |
| `reacquire` | 分配航迹缺失、投影无效、无门内候选或证据丢失 | 目标出图、遮挡、检测缺失 | 进入受限重获取，不得本地换绑 |

这不是一个允许任意跳转的控制状态机，而是每帧决策加每资源/相机/全局航迹历史。历史键由资源、稳定相机作用域和中心全局航迹组成，避免不同相机历史串流。

### 5.2 正常迟滞

候选历史默认保留最近 32 条记录。稳定窗口参数为 3 帧窗口内至少 2 次连续、可锁定的同一本地候选。常规连续锁定不要求每帧重新积累两帧；该窗口主要约束丢失后的恢复和注册稳定支持。

一致性摘要另按 `(resource_id, assigned_global_track_id)`（资源与分配全局航迹联合键）维护连续状态。相同资源继续执行相同全局航迹时，D3 计划版本正常递增不会清空连续计数；真正换目标才进入新窗口。这解决了滚动版本把真实视觉连续性错误打断的问题。

### 5.3 主动重获取

当主马氏门内没有候选时，代码可以在全局航迹预测周围做受限搜索。搜索半径为：

\[
r=\max(45s,3\sigma_{max},0.75d_{bbox})+r_v.
\]

\(\sigma_{max}\) 是投影协方差最大特征值平方根，\(d_{bbox}\) 是上次锁定边界框对角线，\(r_v\) 是按预测像面速度和失锁时间增加的项，最大增加 \(60s\) 像素。

重获取候选默认还需满足：质量至少 0.55、历史至少 2 帧、旧锁定历史不超过 2 秒、边界框面积比位于 0.25 到 4 之间。多个重获取候选的分数间隔至少为 1；恢复为 `locked` 前需达到 3 帧窗口内 2 次稳定支持。若上一帧状态是 `reacquire`，主线恢复锁定所需最佳/次佳代价间隔从 3 提高到 4。

即使本地轨迹标识未变化，重获也不能继承此前授权；即使本地轨迹标识变化，D5 也只能重新支持原分配全局航迹。任何重获候选与已验证或可疑友方声明重叠时，保守输出 `hold`。

### 5.4 丢失证据的失效

当前本地轨迹缺失时，D5 保留最后锁定的匿名相机本地连续性用于说明 `lost/reacquire`，但不输出 coast（无量测外推锁定）状态。默认 0.25 秒后，缺失证据显式过期并保持失败关闭。项目中 D7 对短丢检的有界预测是 D7 自己的能力，不能写成 D5 已实现 coast 或滤波跟踪。

### 5.5 一致性摘要阈值

`TerminalConsistencyTracker`（末端一致性跟踪器）默认使用：

- 锁定置信度至少 0.6、歧义不大于 0.5；
- 锁定年龄至少 1 秒，或候选间隔无穷大/至少 3；
- 连续 5 帧 `ambiguous` 后建议请求二级线索；
- 连续 2 帧普通 `hold` 后建议请求二级线索；
- 连续 5 帧 `reacquire` 后建议请求二级线索/重获取；
- verified friend、spoof、duplicate 或 assignment authorization/version 冲突立即报告冲突或仲裁；
- 本地最佳证据连续 3 帧与分配冲突后建议仲裁。

这些建议只形成 `observe`（继续观测）、`request_secondary_cue`（请求二级线索）、`report_conflict`（报告冲突）或 `arbitrate`（请求仲裁）元数据，不执行动作。

## 6. 身份、版本和全局标识安全

### 6.1 友方身份规则

当前身份检查器只做正向友方确认：

1. 声明需在默认 2 秒有效期内；
2. 声称友方但签名无效时标为疑似伪造；
3. 已验证友方与任何门内候选重叠时直接 `hold`；
4. 过期、未验证或疑似伪造的友方重叠只允许 `ambiguous/hold`，不能提升为锁定；
5. 没有身份声明时保持未知，不自动赋予对抗属性。

当前解析的是离线仿真字典，不是实际远程身份广播、密钥、证书或视觉标签链路。

### 6.2 版本和执行合同

D5 在锁定前依次检查：

- `assignment_version`（分配版本）必须与 `track_version`（航迹版本）一致，除非调用方显式关闭该检查；
- 同一资源和计划只接受不低于已见最高值的 `plan_version`（计划版本），下降版本返回 `hold`；
- `authorization_state`（授权状态）必须属于已批准集合；
- observer（观察成员）不可执行；reserve/retry（备用/重试成员）未激活时只能保留视觉准备证据，不能锁定执行；
- 当前时间必须位于可选到达窗口内；
- 资源、计划、联盟、目标和版本作用域必须与当前上游合同一致。

版本水位只在通过授权且找到有效分配航迹后更新，因此非法输入不能抬高水位并阻断合法计划。

### 6.3 逐主用资源合同

显式满足 `terminal_authorization_scope=per_primary`（逐主用资源末端授权作用域）且 `arrival_coordination_required=false`（不要求到达协同）时，各已授权、已激活主用资源可独立报告锁定，不要求另一个主用资源同帧锁定或同时到达。

该合同只取消共同到达/共同锁定要求，不取消以下条件：当前资源和目标绑定、计划与联盟版本、执行门控、实测本地轨迹、友方冲突、重复锁定风险以及 standby reserve（待命备用）不计完成。`per_primary_terminal_evidence()`（逐主用资源证据函数）的参数只能核对合同，不能覆盖数据对象中的合同，也不授予控制权限。

### 6.4 全局标识不变式

全局身份安全由多层共同保证：

1. `GlobalTrack` 是冻结数据结构；
2. D5 只寻找与 `assigned_global_track_id` 相同的输入航迹；
3. 单资源决策不在其他全局航迹中选择替代目标；
4. 输入和输出前后会断言全局航迹标识序列未改变；
5. `TerminalAssociation` 拒绝 `truth_identity_used=true`（在线使用真值身份）；
6. 本地轨迹标识按资源/相机命名空间汇总，绝不提升为全局标识；
7. 无上游 `GlobalTrackBinding` 时，检测只保留为本地证据并报告 `no_global_binding`（没有全局绑定）。

## 7. 跨视角、联盟与二级节点证据

### 7.1 已实现的跨视角摘要

`TerminalObservationBus`（末端观测总线）把各资源已经独立完成的 D5 决策按既有全局航迹标识分组。本地轨迹键写成 `资源/相机:本地轨迹`，防止不同相机恰好使用相同本地编号时被误合并。

总线无参数调用保留全历史离线兼容行为；main 的当前帧路径使用快照作用域：按当前时间、最大年龄、计划标识和计划版本过滤，再为每个资源保留最新时刻的同帧观测。这样历史锁定不会冒充当前并发锁定。

当前摘要能表达：

- 单视角支持；
- 多资源对同一既有全局航迹的多视角支持；
- 同一本地轨迹同时支持多个全局航迹的冲突；
- 单资源同帧锁定多个本地轨迹的冲突；
- 合法的计划内协同多锁；
- 超出需求、版本不一致、联盟外或未授权成员造成的重复锁定风险。

### 7.2 合法协同锁与重复锁定风险

多个资源同时锁定同一全局航迹不一定是错误。如果所有锁定具有完整且相同的计划/联盟合同、资源作用域正确、成员已授权激活、人数不超过 `required_resource_count`（所需资源数），则标记为 `planned_cooperative_lock`（计划内协同锁），不标记重复风险。

以下情况标记 `duplicate_terminal_lock_risk`（重复末端锁定风险）或联盟冲突：

- 缺少计划或联盟版本；
- 合同签名不一致；
- 资源不在分配作用域；
- 成员未激活或执行门控失败；
- 锁定资源数超过需求；
- 单资源多本地锁定；
- 同一本地轨迹被绑定到多个全局航迹。

D5 只上报风险。资源去冲突、主备调整或计划重发由 D3/D4 负责。

### 7.3 联盟稳定窗口

联盟视觉摘要默认要求每个已授权 active primary（激活主用资源）至少连续 2 帧保持执行锁定。standby reserve 的本机视觉匹配可记录为准备就绪，但不计入主用完成。

同一联盟身份和相同主用成员集合下，计划/联盟版本严格单调增加时可安全延续稳定计数；成员变化、目标变化、旧版本重放、友方冲突、重复风险或过期证据都会重置。对于逐主用资源且不要求到达协同的合同，不再计算共同同帧窗口。

### 7.4 检测到既有全局航迹注册

`register_local_visual_tracks_to_global_tracks()`（检测到既有全局航迹注册函数）消费：

- 上游全局航迹；
- D2/D3 既有绑定；
- 每相机 `CameraLocalTrackBatch`（相机本地轨迹批）；
- 相机模型、量测时间、到达时间和像素协方差。

它输出逐候选投影像素、边界框中心、像素误差、马氏距离、门控结果、是否被唯一分配、拒绝原因和稳定支持。默认稳定规则同样是 3 帧内至少 2 次门控通过。即时 gate pass（门控通过）只是候选，达到稳定窗口后才进入 `stable_cross_view_associations`（稳定跨视角关联）。

### 7.5 二级节点证据

二级相机原始像素不能直接与拦截相机像素比较。`ReconImageCue` 必须携带目标本地帧，或明确声明已重投影到该本地相机。其资源作用域、全局航迹、时间新鲜度和图像帧均需匹配。

`SecondaryFrameAssociationEvidence` 强制使用同一 `frame_id`（帧标识）和时间容差内的相机覆盖与注册候选。历史候选只计入“被忽略数量”，不能把 episode（完整运行片段）聚合值伪装成实时接管证据。

### 7.6 完全分布式辅助融合

代码已实现 `TerminalCrossViewFusion`（末端跨节点视觉融合器），可在没有完整中心几何时用时间偏差、像素/视向、像面变化率、边界框尺度变化、类别、置信度、观测协方差和相机位姿质量构造仅元数据（metadata-only）跨节点假设。默认至少 2 个资源支持、置信度至少 0.55、歧义不大于 0.55 才可能输出 `locked`。

缺少当前全局航迹标识时只能输出 `hypothesis_only`（仅假设）；过时标识、友方冲突、身份冲突或重复锁定风险会输出 `hold/ambiguous`。该路径已实现但属于 D4 完全分布式降级的辅助证据，不是默认中心在线主线，也不是完整多相机三维融合。

## 8. D7 视觉导引前置证据

D5 的 `annotate_visual_png_handoff()`（视觉比例导航导引交接注释函数）不改变关联状态和全局标识，只在现有决策上增加建议字段。默认检查：

- D5 决策为 `locked`；
- 当前分配全局航迹一致；
- 无友方冲突和重复锁定风险；
- 量测年龄不超过 0.35 秒；
- LOS 变化率可用；
- 同一本地轨迹至少有 4 帧边界框历史；
- 边界框面积变异系数不大于 0.30；
- 当前边界框面积占图像面积至少 0.0008；
- 检测延迟、预计剩余时间和 D7 机动裕度满足配置。

边界框面积比例 \(a_k\) 的变异系数为：

\[
c_v=\frac{\operatorname{std}(a_k)}{\operatorname{mean}(a_k)}.
\]

稳定分数为：

\[
s_{bbox}=\operatorname{clip}\left(1-\frac{c_v}{0.30},0,1\right).
\]

距离分区默认是 30 至 50 米准备、15 至 30 米交接、5 至 15 米近距优先。预计剩余时间采用距离除以闭合速度。所有数值只针对当前 AirSim 大目标基线，不是通用物理常数。

即使 D5 建议交接，D7 仍必须独立检查相机、LOS、机动和当前计划合同。D5 的建议不是控制授权；D7 也不得选择另一个本地目标替换全局航迹。

## 9. 默认主线、可选/离线能力与未实现能力

### 9.1 当前默认在线主线

截至 2026-07-13，main runtime 的 `detection_backend`（检测后端）默认值仍为 `airsim`，即：

```text
AirSim simGetDetections 检测元数据
  -> 去除对象身份含义的相机本地检测
  -> 检测框中心与每相机 CameraModel
  -> D2/D3 既有 GlobalTrack/Assignment
  -> TerminalAssociator 几何关联
  -> ObservationBus / Consistency / D7 handoff metadata
```

在线本地轨迹标识由相机本地跟踪语义产生；AirSim 对象标识只允许在在线结果形成后进入离线评价映射。主线关联来源固定记录为 `geometric_detect`（几何检测关联）。

### 9.2 已实现但非默认的辅助或离线能力

| 能力 | 已实现状态 | 不能宣称的内容 |
| --- | --- | --- |
| YOLOv8 + ByteTrack/BoT-SORT adapter（适配器） | 可读取连续红绿蓝（Red Green Blue, RGB）图像，按资源/相机隔离跟踪器状态，输出本地视觉轨迹；依赖不可用时可显式返回 unavailable（不可用）或使用 IoU 跟踪回退 | 18 组筛选无候选准入，不能写成默认后端或已通过质量验收 |
| `NativeMotAdmissionMonitor`（原生 MOT 准入监视器） | 已实现逐流统计、失败关闭准入、在线结果后真值评分和重置接口 | 监视器具备不等于任一后端已经准入 |
| AirSim 几何批量关联 | 已实现多航迹/多检测矩阵、匈牙利分配和离线真值评价分离 | 不等于真实多相机三维融合 |
| 跨视角总线摘要 | 已实现按既有全局航迹汇总、快照过滤和合法联盟多锁判断 | 不做三角定位或融合新航迹 |
| 完全分布式元数据融合 | 已实现跨节点假设和保守状态 | 不是默认中心路径，不创建全局身份 |
| OpenCV `calibrateCamera`（相机标定函数）/`solvePnP`（PnP 求解函数）合成对照 | 隔离式 P2 benchmark（基准实验）已实现，在线模块不导入、不写回相机模型 | 不代表真实 AirSim 标定、在线位姿更新或硬件标定闭合 |
| 确定性鲁棒性矩阵 | 已实现交叉、部分重叠、丢检、本地标识变化、外参漂移、时间偏差和旧计划重放用例 | 不能替代真实连续图像和物理闭环 |

IoU fallback（IoU 跟踪回退）明确是失败对照：任何回退帧都不计入原生 MOT 活跃率，默认准入要求回退帧数为零。

### 9.3 尚未实现或尚未闭合

以下能力不能写成当前主线已实现：

1. 带多相机位姿的三维视向三角化、可观测度分析和融合协方差；
2. 真实图像标定采集、PnP RANSAC、联合优化和在线外参漂移估计；
3. 真实二级侦察原始图像到各拦截相机的完整在线重投影链；当前线索主要来自 fixture（测试夹具）或预处理结果；
4. 深度关联度量增强的简单在线实时跟踪算法（Simple Online and Realtime Tracking with a Deep Association Metric, Deep SORT）、ReID、长遮挡身份恢复及其真实小目标质量验收；
5. 机器人操作系统 2（Robot Operating System 2, ROS 2）的 `tf2`（坐标变换树工具）和 `message_filters`（带时间戳消息同步工具）接入；
6. 真实远程身份广播、密钥/证书和视觉标签适配器；
7. 真实通信带宽、时钟漂移、认证链和实机硬件级验证；
8. D5 自身的 coast、卡尔曼滤波、轨迹创建、目标重分配、降级仲裁或导引控制；
9. YOLOv8/ByteTrack/BoT-SORT 的正式准入和 30/50 米检测能力；
10. M5N2 至少 8/10 协同完成率的系统级 P1 验收。

## 10. 与其他模块及 main runtime 的接口关系

### 10.1 D1 与 D2

D1 提供三维运动学和协方差来源；D2 维护全局航迹连续性和中心全局航迹标识。main adapter 把 D2 平面状态与 D1 缓存的高度/垂向速度组合成 D5 三维航迹。D5 不修改 D1/D2 状态，也不计算系统级 IDSW。

### 10.2 D3

D3 提供版本化分配计划、资源-目标绑定、联盟角色、需求数、激活态和到达窗口。D5 是只读合同消费者：版本或作用域冲突时保守拒绝，而不是就地修复计划。合法协同多锁和超额锁定风险摘要返回给 D3/D4，但 D5 不调整计划。

### 10.3 D4

D4 消费四态决策、连续非锁定帧、跨视角支持、重复风险、二级覆盖、线索新鲜度和建议动作。中心或二级失效时，D5 的联盟摘要还检查 D4 提供的 committed/executing（已提交/执行中）状态、时期、租约和必要成员确认。D5 不根据这些证据自行降级。

### 10.4 D6

D6 消费运行时记录、几何对日志、跨视角摘要、逐主用资源漏斗和 MOT 准入汇总。在线真值使用计数、全局标识改写计数、错误锁定、歧义、门控拒绝、检测查准率/召回率和本地 IDSW 都应保持分层统计。D5 不生成系统最终报告。

### 10.5 D7

D7 只有在 D5 `locked`、分配一致、当前实测、无友方/重复风险且交接证据满足时，才可进一步评估视觉 PNG。D7 保留相机、LOS、机动、时效和控制合同的独立门控。`ambiguous/hold/reacquire/hypothesis_only` 均不得被解释为可执行视觉目标。

### 10.6 main runtime

main 负责：

- AirSim Blocks 启停、reset-separated episodes（重置分隔的运行片段）和运行顺序；
- `--drone-count N`（无人机数量参数）和动态资源/目标规模；
- 相机设置、实际相机位姿、图像/检测采集和时间戳；
- 每个运行片段重置 D5 关联历史、YOLO/MOT 流状态和准入监视器；
- AirSim 真值可由仿真编排用于构造明确标注的输入 fixture，并可交给 D6/离线评价；不得进入 D5 在线关联代价、Hungarian 选择或稳定窗口；
- 日志、表格、曲线和总报告。

D5 算法按输入数组长度运行，2 对 2、5 对 5 和 M5N2 只是基线场景名，不是硬编码上限。

## 11. 当前运行流程

默认单资源决策步骤如下：

1. 从当前 D3/D4 合同取得分配全局航迹标识、资源、计划版本、联盟版本和成员状态；
2. 拒绝低于已接受水位的旧计划、未授权合同和缺失分配航迹；
3. 检查航迹版本与分配版本；
4. 用本地量测时刻预测中心航迹并膨胀协方差；
5. 用当前资源的相机内外参投影，拒绝相机后方、图像外或非有限投影；
6. 从当前资源/相机批次取得实测本地轨迹，不借用其他相机检测；
7. 计算每个候选的马氏距离、像面变化率、类别、质量、身份和二级线索代价；
8. 无门内候选时执行受限重获取；有已验证友方门内候选时直接 `hold`；
9. 计算最佳/次佳间隔，应用成本、质量、历史、量测时效和稳定性门控；
10. 应用成员角色、激活态和到达窗口执行门控；
11. 形成 `TerminalAssociation`，写入量测/到达时间、投影、协方差、门控和拒绝原因；
12. 通过总线形成当前快照跨视角摘要和一致性摘要；
13. 注释 D7 前置证据，但不改变 D5 决策状态；
14. 仿真编排可用真值构造明确标注的输入 fixture，D6 可用真值做离线评价；两者均不得把 truth identity 注入 D5 在线关联链。

## 12. 验证结果

### 12.1 模块回归

2026-07-14 D5 最新全量结果为：

```text
241 passed
```

2026-07-13 的 `232 passed` 保留为历史基线；本次状态分级实现与文档同步后已重跑全量。命令为：

```bash
pytest -q research_modules/d5_terminal_association/tests
```

### 12.2 M5N2 协同视觉闭环

当前场景为 5 个资源、2 个目标，高威胁目标采用 2 个激活主用资源和 1 个待命备用资源；每个主用资源独立通过 D3/D4/D5/D7 门控，不要求同时到达。

截至 2026-07-13：

- 共形成 120 条 active-primary（激活主用资源）证据；
- 120 条均记录为可见；
- 其中 74 条形成 D5 关联/锁定证据；
- 最佳参数组合的联盟完成率为 5/10，低于 8/10 验收线；
- 主要失败原因为 `d5_not_locked`（D5 未锁定）和 `terminal_detection_acquisition_timeout`（末端检测获取超时），少量为 `bbox_area_too_small`（边界框面积过小）；
- 待命备用资源越权执行为 0；
- 全局航迹标识改写为 0；
- 在线真值身份使用为 0。

结论是“逐主用资源合同和诊断接口已闭合，但系统级协同视觉性能未闭合”。不能把 5/10 写成 M5N2 已验收，也不能通过取消版本、身份或稳定窗口门控提高表面完成率。

### 12.3 原生 MOT 18 组筛选

真实 AirSim 筛选矩阵为：

- 图像分辨率 1920×1080；
- FOV 90 度；
- 距离 20/30/50 米；
- 检测置信门限 0.10/0.20/0.30；
- ByteTrack 和 BoT-SORT 两种后端；
- 共 18 个筛选算例，每个 101 帧。

结果为：

| 后端 | 20 米原生活跃率 | 20 米本地连续性 | 本地 IDSW | 去预热 P95 延迟 | 检测查准率/召回率 | 30/50 米 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| ByteTrack | 1.0 | 1.0 | 0 | 约 7.4 毫秒 | 约 0.30 至 0.32 | 无有效检测 |
| BoT-SORT | 1.0 | 1.0 | 0 | 约 16.2 毫秒 | 约 0.26 至 0.33 | 无有效检测 |

20 米结果只证明受控条件下原生 tracker（跟踪器）能连续运行且延迟满足筛选预算。由于边界框离线查准率/召回率明显低于准入线，18 个候选均未准入，200 帧双相机确认算例数为 0。默认在线后端继续是 AirSim 检测元数据。

默认准入条件包括：至少 100 帧、原生活跃率至少 0.95、IoU 回退帧为 0、本地连续性至少 0.90、本地 IDSW 不超过 1、P95 不超过 100 毫秒、查准率至少 0.90、召回率至少 0.80，并要求在线结果后真值帧覆盖完整。当前结果不满足后两项及远距检测要求。

### 12.4 二级节点和跨视角校准证据

截至当前状态，较早的 60 算例 D4/D5 校准扫描已证明基础检测到既有全局航迹注册能形成可审计结果：投影有效率均值为 1.0，`not_registered_count`（未注册计数）为 0，平均跨视角关联数为 4.417。与此同时，二级网络同帧全目标覆盖率均值只有 0.0231，平均覆盖比例为 0.7059。

因此“局部检测可注册”已经有证据，“二级网络同帧拥有完整态势”仍未成立。二者不能合并成一个成功结论。

### 12.5 隔离式 OpenCV P2 对照

默认随机种子 7 的合成外参扰动对照约得到：投影误差从 24.0 像素降到 1.63 像素，真候选门控接受率从 0 升到 1，构造的假候选接受率从 1 降到 0。

该实验在所有几何门控完成后才附加离线真值标签，且在线 D5 不导入该模块、不写回 `CameraModel`。结果只证明合成条件下 PnP 位姿恢复对投影误差敏感，不能代表真实相机标定、AirSim 在线 PnP 或物理闭环。

## 13. 已解决问题

截至 2026-07-13，D5 已关闭的关键实现问题包括：

1. AirSim 对象/实体/真值字段进入在线本地身份或全局绑定的泄漏路径；
2. 仿真实体名称曾出现在本地轨迹标识中的端到端污染；
3. 活动重获取路径未重新检查友方声明的问题；
4. 多相机本地跟踪器状态可能串流的问题，现按资源/相机隔离并支持逐流和全运行片段重置；
5. 总线全历史观测污染当前重复锁定判断的问题，现支持时间与计划快照；
6. 合法联盟协同多锁曾被一律标为重复风险的问题；
7. 计划版本滚动错误清空同一资源/目标连续窗口的问题；
8. 共同窗口没有复用安全跨版本连续尾段的问题；
9. `per_primary`（逐主用资源）合同、到达协同字段和逐资源漏斗没有贯通的问题；
10. 1080 行与 2160 行相机混用时固定像素门限、协方差和边界框面积尺度不一致的问题；
11. 无人机类别同义标签产生错误类别惩罚的问题；
12. YOLO/MOT 在线结果、离线 AirSim 参考框和本地轨迹数量混为同一检测计数的问题；
13. 后到真值可能反向影响在线结果或重复评分的问题；
14. 二级节点聚合证据可能冒充单决策时刻证据的问题；
15. 丢失/预测本地轨迹产生锁定的风险，现由数据结构和决策逻辑双重拒绝。

这些修复关闭的是合同、隔离和可审计性问题，不自动关闭检测召回、稳定锁定或物理完成率问题。

## 14. 剩余局限与下一步证据要求

### 14.1 当前最高优先级局限

1. **第二主用资源稳定获取不足。** M5N2 的最高优先级仍是持续检测、稳定边界框和连续实测锁定，目标是最佳组合至少 8/10。
2. **检测框口径未对齐。** 20 米 YOLO 框与 AirSim 离线参考框可能存在定义、尺度或时间偏差，尚不能唯一归因。
3. **远距召回缺失。** 当前本地权重在 30/50 米无有效检测，不能靠直接降低在线几何门或身份门关闭缺口。
4. **真实外参/时间同步未完成多随机种子标定。** 强类型相机几何字段在部分历史运行中仍为 unavailable，不能用仿真真值位姿补齐。
5. **二级同 tick freshness 尚未闭合。** 基础注册成功不等于 main/D4 已在同一 decision tick 消费 freshness、threshold version 和状态迁移证据。
6. **完整多视角三维融合属于 P2。** 当前跨视角主线是“独立单相机关联后的证据摘要”，不是三角定位、完整在线 PnP 或联合状态估计。

### 14.2 后续验证不得放宽的条件

后续提高性能时必须继续保持：

- 在线真值身份使用为 0；
- 全局航迹标识改写为 0；
- 旧计划和旧联盟版本拒绝；
- 友方重叠失败关闭；
- standby reserve 不计主用完成；
- 丢失/预测轨迹不产生 D5 锁定；
- D7 保留独立相机、LOS、时效和机动门控；
- D4 保留独立降级仲裁；
- 任何离线阈值扫描不能直接替换在线安全门限。

### 14.3 所需证据

后续收敛应至少提供：

- 按资源、相机、目标和时间对齐的检测可用率、投影有效率、马氏门通过率、锁定率和稳定锁定率；
- 20/25/30/40/50 米逐距离的边界框尺度、中心归一化误差、宽高/面积比、包含关系和前后各一帧时间对齐诊断；
- 候选 MOT 配置至少 10 个随机种子、每组不少于 100 帧的确认；
- 真实相机内外参、曝光/量测/到达/姿态时间差、重投影误差和漂移告警；
- 将持续检测失败、D5 未锁定、D7 门控拒绝和控制闭环不足分层报告，不能用一个“未完成”字段合并。

## 15. 中文术语表

| 中文术语 | 代码/英文对应 | 本文含义 |
| --- | --- | --- |
| 中心全局航迹标识 | `global_track_id` | 由中心 D2 拥有并维护的系统级航迹身份 |
| 本地视觉轨迹标识 | `local_track_id` | 仅在一个资源/相机流内有效的检测跟踪身份 |
| 末端关联 | terminal association | 把当前本地视觉候选保守地支持到既有中心分配航迹 |
| 实测轨迹 | `measured` | 当前帧存在实际检测量测的本地轨迹 |
| 预测轨迹 | `predicted` | 只有本地跟踪器预测、没有当前检测量测的轨迹 |
| 丢失轨迹 | `lost` | 当前不可用的本地轨迹证据 |
| 锁定 | `locked` | 唯一实测候选通过全部 D5 门控 |
| 歧义 | `ambiguous` | 有候选，但唯一性、质量、身份或稳定性不足 |
| 保持 | `hold` | 合同、版本、身份或执行门控阻断 |
| 重获取 | `reacquire` | 目标投影或本地量测不可用，需要重新取得证据 |
| 针孔相机模型 | pinhole camera model | 用内外参把三维点投到二维图像的模型 |
| 投影协方差 | `covariance_px` | 三维航迹不确定度和像面量测噪声传播后的二维协方差 |
| 马氏距离门 | Mahalanobis gate | 按协方差尺度判断像素残差是否统计一致的门控 |
| 候选代价间隔 | `candidate_cost_margin` | 次佳代价减最佳代价，表示候选唯一性 |
| 边界框 | `bbox` | 图像中的二维目标外接矩形 |
| 边界框面积比例 | `bbox_area_ratio` | 边界框面积除以图像总面积 |
| 量测时间 | `measurement_timestamp` | 图像或检测对应的物理采样时刻 |
| 到达时间 | `arrival_timestamp` | 证据进入处理链的时刻 |
| 证据年龄 | `measurement_age_s` | 到达时间与量测时间之差 |
| 身份声明 | `IdentityClaim` | 合作平台对自身身份及友方属性的声明 |
| 已验证友方重叠 | `verified_friend_overlap` | 可靠友方声明与视觉候选重叠，必须保持 |
| 二级侦察图像线索 | `ReconImageCue` | 二级节点产生且已投到目标本地相机平面的辅助线索 |
| 跨视角支持 | `CrossViewAssociation` | 多资源对同一既有全局航迹的被动证据摘要 |
| 计划内协同锁 | `planned_cooperative_lock` | 符合同一计划/联盟合同的多资源锁定 |
| 重复末端锁定风险 | `duplicate_terminal_lock_risk` | 超额、越界、冲突或多重绑定造成的风险信号 |
| 稳定窗口 | stability window | 最近若干帧中要求足够连续门控通过的迟滞规则 |
| 失败关闭 | fail closed | 证据缺失或冲突时保持非执行状态，而不是默认通过 |
| 在线路径 | online path | 真值不可见、直接形成 D5 决策的处理路径 |
| 离线评价 | offline evaluation | 在线结果冻结后使用真值计算指标的过程 |
| 检测后端 | `detection_backend` | main runtime 选择 AirSim 检测元数据或可选 YOLOv8 的配置 |
| 原生跟踪 | native tracker | Ultralytics 实际返回 ByteTrack/BoT-SORT 本地轨迹标识的路径 |
| IoU 跟踪回退 | `iou_fallback` | 原生跟踪不可用时的确定性失败对照，不计准入 |
| 逐主用资源合同 | `per_primary` | 每个激活主用资源可独立形成视觉证据的合同口径 |
| 待命备用资源 | standby reserve | 未激活时可准备但不能计入主用完成的资源 |
| 相机几何证据 | `CameraGeometryEvidence` | 内参、相机到 NED 外参、姿态时间和有效性摘要 |
| 标定健康 | `calibration_health` | 依据投影有效性、重投影误差和位姿来源形成的诊断状态 |
| 末端一致性摘要 | `TerminalConsistencySummary` | 面向 D4/D6 的连续状态、冲突和建议动作摘要 |

## 16. 结论

D5 当前已经形成一条可执行、可审计且身份隔离的末端视觉关联主线：它把中心全局航迹预测到相机量测时刻，将三维协方差传播到像面，用马氏门和多项可解释代价选择本地实测候选，再由版本、授权、友方、稳定窗口和联盟合同作保守四态决策。它还能输出跨视角、逐主用资源、二级节点和 D7 前置证据，但始终不创建或改写全局身份。

截至 2026-07-14，合同安全、诊断接口和 canonical actual 五层 schema 已闭合，P0 无阻断项；性能侧仍未闭合。当前 P1 仅为 M5N2 第二 primary、真实几何 drift、detect/YOLO/MOT 多 seed 和二级同 tick freshness。IBVS、真实身份源、完整在线 PnP/多视角三维融合与 ROS 2 保持 P2/P3。因此当前主线必须继续保持 AirSim 检测元数据加几何关联，所有可选算法和离线对照都不得写成已经替代默认路径。
