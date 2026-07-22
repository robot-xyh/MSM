# 200 对 200 三维质点仿真实施计划

## 当前执行状态（2026-07-22）

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

当前执行顺序调整为：

1. D1/main 继续分离固定滞后滤波、检查点查询、剩余航迹物化和 JSON 写出成本；下一版轻量
   heartbeat/lineage sidecar 必须版本化并兼容旧 consumer。
2. D5 按局部历史、图节点、投影单元和 binding 单元治理剩余 2.423 倍单次成本增长，不减少
   视觉帧、不放宽投影与身份门限。
3. D3 冻结输入归因已完成。集成三 seed 累计时间基本持平，当前不修改规则代价、迟滞或
   Hungarian 主线，后续补稳定窗口周期 P50/P95/max。
4. 完成当前吞吐治理后，再扩展 D4 故障、D5 跨视角和 D7 五米接近的长时多 seed 验收。
5. 学习策略继续保持 disabled/shadow；性能优化不得用学习模型、降采样或放宽安全门控替代。

本批属于干净来源的描述性校准，未声明正式实验矩阵。详细结果见
`docs/SCALABLE_3D_RULE_PERFORMANCE_CALIBRATION_CN.md`。

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
  未标注为 `57292/187740/0`，数据支持与训练数据来源门已通过。新模型尚未训练，三者
  均未获得 assist 准入。
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
