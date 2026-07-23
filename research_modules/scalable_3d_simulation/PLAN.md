# 200 对 200 三维质点仿真实施计划

## 当前执行状态（2026-07-23）

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

main 真值守卫键布局缓存已通过完整测试、嵌套可变负例和跨构建语义审计。四组交错
clean 2.2 秒复测的 publication bus 中位数下降 12.69%，核心墙钟中位数只下降
0.44%。该项关闭局部重复键规范化，不关闭 200 对 200 实时 P1。组合 clean
`d79aba3` smoke 的实时倍率为 `0.204`，状态有限且在线真值使用为 0。

当前执行顺序调整为：

1. D1 扫描输入和融合合计仍占候选核心墙钟约 62%。下一轮优先治理 scan-input
   `GlobalTrack` 物化、非雷达扫描关联、固定滞后回放和检查点查询；不得缩短 6 秒窗口、
   丢观测或放宽协方差治理。D1 融合 episode P95 均值仍为 `233.488 ms`。
2. D2 关联 episode P95 均值为 `142.627 ms`，超过 100 ms 预算。继续分离 covariance
   governance、重复航迹合并和 publication 成本。三态 truth sidecar 与视觉几何解析已完成，
   严格身份仍由 D1 雷达扫描间多真值谱系阻断；v1 已拒绝，下一候选必须覆盖完整交替路径，
   不得从距离、名称或零径向速度占位补算身份。
3. D7 固定输入没有确认内核回归，核心公式保持不变。main publication bus 已关闭重复键
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
