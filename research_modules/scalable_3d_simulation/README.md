# Scalable 3D Simulation

该 main-owned 模块提供可复现、真值隔离的三维质点环境，用于逐步建设 200 架拦截无人机
对 200 个来袭目标的 D1-D7 完整闭环。现有 `integrated_simulation` 保留为小规模回归基线。

当前阶段已实现世界状态、三维动力学、透视投影、传感器场景、传感器到融合中心的通信
队列、版本化 episode 总线和确定性环境基线。通信队列按配置施加时延、抖动、批次丢失和
序列化带宽开销，并把网络投递时刻写回观测 `arrival_timestamp`。`IntegratedScalableModuleStack` 已把 D1 六维融合、D2 稀疏关联、
D3 稀疏分配、D4 区域权限、D5 匿名跨视角配准和 D7 三维比例导引接入同一在线时钟。
模块栈只做接口转换与调度，各算法仍由 D1-D7 原模块维护。

D5 主动视觉已接入同一 episode 状态机。main 持久化每个拦截/侦察相机的绝对指向、视场
模式及最近接受的计划、联盟和通信版本。D5 只读取 D2 中心航迹、D3 当前分配、D5 几何
证据和相机反馈，输出观察目标、重捕获、扇区搜索或保持命令。命令在下一视觉帧生效并产生
独立 ACK；过期、过时版本、资源不一致和退化指向均由 main 拒绝。该路径不创建分配，也不
改写 `global_track_id`。

main 还在 D3 发布新计划的同一调度周期，将计划逐项绑定到 D7 命令并发布
`runtime.assignment_plan_ack`。确认记录携带计划编号、版本、所有者、每个资源与中心航迹的
绑定、导引模式和保持原因，并绑定来源 D3/D7 总线序号与规范载荷 SHA-256，不携带仿真目标
真值。确认还原样携带 D3 学习代价和 D4 区域建议的 considered/applied/fallback 元数据，缺失
字段保持为空。该记录只证明计划被运行时接收以及绑定是否进入 D7，不把五米接近、任务完成或
规则教师诊断写成结果与奖励。

main 现已把该确认链自动接入 D6 离线结果联接。存在运行时计划确认的 episode 会额外写出
`d6_runtime_plan_outcomes/input_specification.json`，其中登记在线总线、D2 离线身份映射、
三维真值状态、五米接近事件、场景配置和 episode manifest 共 11 项输入及 SHA-256。D6 先
复载并校验该清单，再按确认序号和时间戳建立互不重叠的资源-航迹窗口。同一计划编号和版本
允许产生明确标记的评估刷新窗口，但资源绑定、联盟和 authority 执行签名必须保持不变。
每个窗口输出起始、结束、最小三维距离和五米事件；距离进展只记为诊断，不作为 D3 正式奖励。
输入清单、联接结果、中文报告和 main provenance manifest 均随 episode 保存。

## 2026-07-23 当前优化 20-seed 校准

detached clean `5263e2b343dc4b96d239f77ef09437eb132f9efb` 已完成
seed `1000-1019`、nominal 200 对 200、10 秒规则全栈顺序运行。20/20 状态有限，
在线真值使用总数为 0，D1-D2 后验代次和 D6 schema/provenance 审计通过。候选与已有
`0d2da25` 同 seed 参考的 20/20 直接跨构建审计均通过，规范在线载荷、真值和计划/确认
语义一致。

核心墙钟均值由 `96.391 s` 降至 `86.099 s`，20/20 seed 均改善；配对变化均值为
`-10.63%`，95% seed bootstrap 区间为 `[-11.71%, -9.61%]`。实时倍率均值由
`0.1039` 提升到 `0.1163`，仍未达到实时。D1 扫描输入、D1 融合和 D2 关联分别下降
`22.06%/15.15%/6.41%`。严格 `id_switch_count` 在 20/20 seed 上继续为
unavailable。部分身份映射/完整帧/相邻转换覆盖为
`98.5760%/10.7404%/0.6118%`，19 个 episode 的保守下界合计 199；该值未回填 strict。
D1 RMSE/NEES 因同一 lineage mapping 缺口不可用。学习 bundle、正式七变体矩阵和五米
物理结果均不属于本轮证据。

完整结果见
`docs/SCALABLE_3D_LONG_DURATION_PERFORMANCE_CALIBRATION_CN.md`，机器摘要见
`docs/SCALABLE_3D_20SEED_PERFORMANCE_CALIBRATION_20260723.json`。

## 2026-07-23 后续热点复核

D1 已把扫描 claim 中重复的 JSON 规范化改为单次物化。冻结 seed 1000 的
771 个扫描、11,889 条观测上，旧/新 claim registry、逐次融合状态、协方差、
双时间戳、谱系和最终航迹严格一致；五轮交错 P50/P95 由
`3.618/4.049 s` 降至 `1.905/2.038 s`。该证据来自冻结输入，不代替新的
20-seed 全栈校准。

D2 对上述 20 个 clean episode 重放了离线身份 producer。严格 `id_switch_count`
仍为 unavailable：118 个航迹帧存在同一 `global_track_id` 对应多个真实目标，
形成 107 个多真值连续区间并涉及 83 个 episode/航迹组合；另有 2,464 个受评分
映射缺少显式真值、已知虚警或标签未知标记。D1 的 191,425 条可用估计中可形成
188,951 条唯一候选映射，剩余 2,474 条因 `truth_label_missing` 未解析，因此
20/20 episode 均未发布可消费的部分映射。在线 D2 关联器、门限和
`global_track_id` 均未修改。

D7 使用固定 200 pair、185 frame replay 对两个历史构建各运行 6 次。37,000 条
命令、世界加速度和最终 pair 状态严格相同，候选内核变化为 `+0.626%`，95%
bootstrap 区间为 `[-1.828%, +3.178%]`。该结果没有确认 D7 内核回归，因此
PN/PNG、LOS/TTC、切换门和调用频率保持不变。

main 对 3,430 条持久化在线载荷缓存真值守卫的重复键布局，同时继续逐次递归检查
嵌套值。四组同 seed、同配置、交错 clean 2.2 秒复测中，发布总线累计耗时中位数由
`0.887 s` 降至 `0.775 s`，下降 12.69%；核心墙钟中位数由
`10.824 s` 变为 `10.776 s`，只下降 0.44%，不能认定系统吞吐显著改善。
组合提交 `d79aba3` 的 clean smoke 状态有限、在线真值使用为 0、实时倍率为
`0.204`，跨构建 3,430 条规范在线记录和真值制品全部等价。

## 2026-07-23 离线三态与几何治理复测

D1 已修复冻结相机元数据的解析边界。扫描帧中的只读 `Mapping`、
`rotation_camera_from_ned` 和嵌套相机内参不再退回默认相机模型；非法外参、相机后方目标
和非有限投影失败关闭。冻结 seed 1000 的 771 个扫描和 11,889 条匿名观测中，D2 先前定位的
17 条视觉污染观测全部离开原错误航迹。该核验只在在线回放结束后使用离线标签，没有把真值
身份送入 D1。

main 离线真值合同升级为 `scalable3d-offline-truth-v2`。每条标签显式标记 `target`、
`known_false_alarm` 或 `unknown`；合成视觉虚警与在线量测一一生成，但处置类型仍只写入
离线 sidecar。D2 规范化为 `d2.scalable3d_observation_truth.v2`，已知虚警不进入严格身份
交换分母，未知或冲突标签继续阻断指标。D5 旧训练导出和保留 seed 身份桥只消费 `target`
标签。D6 三个消费入口分别报告三态数量，不从名称、距离或在线状态推断处置，也不回填严格
ID Switch。

detached clean 提交 `488dc39` 包括三组 2.2 秒和一组 10 秒 nominal 200 对 200。四组状态有限，
在线禁用身份字段命中和 `online_truth_use_count` 均为 0。三组短回放共生成 7,098 条目标
标签和 312 条已知虚警标签，缺失身份映射均为 0；seed 1001 的严格 ID Switch 可用且为 9，
seed 1000、1002 各有 2 个雷达多真值映射。10 秒 seed 1000 生成 10,829 条目标标签和
402 条已知虚警标签，剩余 7 个多真值映射，分布在 6 帧和 6 条航迹；来源均为雷达谱系。
严格指标因此继续保持 unavailable，部分下界 49 只用于诊断。

四个 episode 的 manifest 均为 `repository_dirty=false`。该批属于 clean 描述性校准，
尚不是 formal acceptance；它证明标签缺失已从新 producer 消失，并把剩余身份阻断收敛到
雷达扫描间关联。该批机器摘要见
`docs/SCALABLE_3D_IDENTITY_DISPOSITION_RECALIBRATION_20260723.json`，后续雷达候选评审见
下一节。

## 2026-07-23 雷达交替环候选评审

main 对 baseline `488dc39` 和 D1 v1 candidate `d967c96` 完成同配置 clean A/B。设置固定为
nominal 200 对 200、2.2 秒、`recon_count=2`、seeds 1000/1001/1002，各 seed 的配置哈希
在两端相同。候选把 ambiguous mapping 从 `2/0/2` 降到 `0/0/0`，严格身份指标可用 seed
由 `1/3` 增至 `3/3`。代价是 D2 航迹数由 `201/202/200` 降至 `200/194/197`，D3 分配数由
`200/200/200` 降至 `198/190/193`；seed 1001 的 continuity 由 `0.869444` 降至
`0.814444`。候选还抑制 `22/130/78` 条雷达观测，占各 seed 雷达量测的
`1.12%/6.61%/3.98%`。

v1 因航迹、分配和连续性退化不晋级，默认在线路径保持原 Hungarian。提交 `8f17c5d` 将
候选改为默认关闭后，同配置三 seed 的全部业务指标恢复 baseline；跨构建审计
`3/3 passed=True` 且规范在线载荷 `3/3` 相等。早先使用 8 架侦察机的结果只保留为
stress 诊断，不能与本次 `recon_count=2` A/B 比较。该诊断揭示 v1 尚未覆盖最大匹配图中的
free-row 和 free-column 交替路径，雷达量测也没有可用于消歧的真实径向速度。

严格身份 P1 继续开放。下一候选必须同时覆盖交替环、free-row 和 free-column 路径，并联合
验收身份可用性、D1/D2 航迹、D3 分配、连续性、抑制率、birth 和 recall。在新的短时 clean
候选通过前，不运行被拒绝 v1 的 10 秒或 20-seed 批次。机器摘要见
`docs/SCALABLE_3D_RADAR_ASSIGNMENT_CANDIDATE_REVIEW_20260723.json`。

main 运行时现提供显式
`--d1-radar-assignment-ambiguity-governance-v2` 实验开关。默认不传入时保持关闭；启用后，
`summary.json` 和 `observation_governance_audit.json` 会记录 D1 的
`selected_policy_version`、enabled/status 及抑制诊断。兼容字段
`policy_version` 不能单独用于判断实际启用策略。`manifest.json` 另存完整
`scalable3d-integrated-stack-runtime-profile-v1` 和 SHA-256，episode ID 同时携带该哈希前缀，
因此相同场景的基线与 treatment 不会共用身份。该接线允许同一代码提交分别运行规则基线和
实验候选，不再通过修改模块默认值制造 A/B。

detached clean `c928727` 已用未见 seed 1100 运行首个 200 对 200、2.2 秒、
`recon_count=2` 同构建门槛。v2 的身份交换保持 `9`，航迹连续性由 `0.865` 降至
`0.830`，D2 航迹由 `203` 降至 `199`，D3 分配由 `200` 降至 `196`；77 条雷达观测被抑制。
候选没有身份收益且下游可用性下降，因此按预注册门槛停止剩余短 seed、10 秒和 20-seed。
v2 保持默认关闭。评审见
`docs/SCALABLE_3D_RADAR_ASSIGNMENT_V2_CLEAN_AB_REVIEW_CN.md`，机器摘要见
`docs/SCALABLE_3D_RADAR_ASSIGNMENT_V2_CLEAN_AB_REVIEW_20260723.json`。

## 2026-07-23 D1-D2 结构歧义保活复核

D1 和 D2 的默认关闭候选链路现已增加显式身份承诺合同。D1 仍只发布带双时间戳、NED
六维状态、协方差和完整允许边的结构歧义侧车。D2 在租约期间发布
`identity_uncommitted_ambiguity_hold`，租约结束但没有新原始证据时发布
`identity_uncommitted_after_hold`。这两类记录不携带来源观测，也不进入 D3 当前分配
窗口。只有不同、更新且首次接受的原始证据可恢复 `committed`。main 对普通已承诺航迹
保留窗口内 D1 谱系；经历歧义恢复的航迹只发布本次被接受量测的精确谱系。D6 使用 v2
证据独立重算承诺覆盖、恢复水位和绑定违规，不回填严格身份指标。

发布新鲜度门已加入 D2 恢复承诺。量测必须晚于 hold 水位，并且
`D2 帧时刻 - measurement_timestamp <= 0.9 s`。超龄证据保持未承诺，等待更新的原始
观测。完整恢复配置由每条 D2 发布携带；离线身份清单升级为
`scalable3d-offline-identity-evaluation-manifest-v2`，绑定本 episode 的规范配置快照、
配置 SHA-256 和记录数。D6 同时验证清单、在线 D2 JSONL 和逐发布配置，历史 v1 清单保持
只读兼容。

detached clean `ff881316243ff5a2991a4659ab78637ed625d123` 使用相同 nominal 200 对 200、
2.2 秒、`recon_count=2` 和 seed 1100 完成最终同构建 A/B。候选形成
`1711/69/7` 条 committed/hold/after-hold 记录；其中 3 条超龄恢复证据被新鲜度门阻断。
严格 ID Switch 由 `9` 降至 `3`，重复分配保持为 0，未承诺来源和候选绑定违规为 0。
两组清单均绑定 9 条 D2 发布，D6 episode 与 runtime provenance 均验证通过。

候选仍未通过准入。D2 航迹由 `203` 降至 `201`，D3 分配由 `200` 降至 `197`，可用
身份映射由 `1566` 降至 `1491`，航迹连续性由 `0.865` 降至 `0.826667`，覆盖连续性由
`0.870` 降至 `0.828333`。seeds 1101/1102、10 秒和 20-seed 按停止规则不执行，默认
路径不变。配置谱系缺口已关闭；结构歧义保活的算法准入仍是 P1。
完整评审见
`docs/SCALABLE_3D_STRUCTURAL_AMBIGUITY_HOLD_CLEAN_AB_REVIEW_CN.md`，机器摘要见
`docs/SCALABLE_3D_STRUCTURAL_AMBIGUITY_HOLD_CLEAN_AB_REVIEW_20260723.json`。

## 2026-07-22 规则全栈性能校准

提交 `33101656b0cf1967a778cdb36a440611e02109b1` 已完成 20、50、100、200 四档 clean-source
校准，每档 seed 42000-42004，共 20 个 2.2 秒 episode。20/20 状态有限，在线真值使用为 0。
平均实时倍率依次为 `1.504/0.540/0.240/0.092`。20 对 20 达到实时，200 对 200 平均墙钟
23.969 秒，仍未达到实时。

200 规模 D1 融合、D2 常规关联和 D3 分配的平均累计时间分别为 `10.275/2.037/0.665 s`，
D2 尾部收束为 `0.640 s`。相对上一轮同配置 clean 批次，200 规模平均墙钟下降 26.7%。
D1 仍是首要热点，下一轮优先处理创新求解、数值雅可比和发布物化，再处理 main 结束收束与
发布序列化。本批没有正式实验矩阵元数据，D6 将其归类为干净来源的
描述性校准，不是 formal acceptance，也不证明融合精度、AirSim 或物理拦截。

完整条件、逐规模表、同 seed 开发对照和制品哈希见
`docs/SCALABLE_3D_RULE_PERFORMANCE_CALIBRATION_CN.md`。

## 2026-07-22 长时性能对照工具

`long_duration_performance.py` 和
`scripts/compare_long_duration_episodes.py` 用于比较同一 clean 提交、同一 seed、仅仿真
时长不同的两个 episode。工具只读取 manifest、场景配置、summary、阶段耗时和可选的
`/usr/bin/time -v` 资源记录，不扫描大体积在线 JSONL 内容。

对照结果包含总墙钟、实时倍率、峰值驻留内存、在线日志速率、D1/D2 治理状态、计划确认
以及各阶段的单位仿真时间增长、调用密度增长和单次调用成本增长。比较前强制核对提交号、
场景版本、seed、目标/资源/侦察节点数量及去除时长后的配置摘要，避免把不同来源 episode
混为同一性能样本。

```bash
python3 research_modules/scalable_3d_simulation/scripts/compare_long_duration_episodes.py \
  --short-episode <2.2-second-episode> \
  --long-episode <10-second-episode> \
  --output-dir <comparison-output>
```

提交 `c0460e0` 的 seed 42000 基线显示，2.2 秒与 10 秒运行的单位仿真时间墙钟由
`9.868 s` 增至 `26.329 s`，归一化增长 `2.668x`；峰值驻留内存由 `1.054 GiB` 增至
`3.154 GiB`。D1 fusion 和 D2 association 的单次调用成本分别增长约 `2.107x` 和
`3.467x`。该结果只用于定位长时历史增长。

模块优化后的 detached clean 提交 `3bac3ff` 已复跑相同 pair，并由 D6 独立消费。2.2 秒与
10 秒核心墙钟为 `18.611/172.214 s`，10 秒相对旧基线下降 34.6%；实时倍率为
`0.118/0.058`。候选长短单位时间成本增长为 `2.036x`，峰值驻留内存为
`1.002/2.981 GiB`。D1/D2/D3/D5/D7 最终规范输出和 201 帧三维世界状态均与旧基线一致，
在线真值使用和 D1/D2 overflow 为 0，最终中心身份集合未发生变化。

该结果证明当前模块优化有效，但 200 对 200 仍未实时，长时内存和发布量仍明显增长。D1 10 秒
融合为 103.176 秒，D5 终端配准单次成本增长 2.696 倍，在线日志仍为 296.336 MiB。详细条件、
阶段耗时、语义哈希和后续边界见
`docs/SCALABLE_3D_LONG_DURATION_PERFORMANCE_CALIBRATION_CN.md`。

同一 clean 提交随后完成 seed 42001、42002 的 10 秒运行。三 seed 核心墙钟均值为
172.097 秒，实时倍率均值 0.0581，峰值驻留内存均值 3.055 GiB；D1/D2/D3/D5 阶段均值为
103.339/8.203/3.348/2.699 秒。3/3 状态有限、在线真值为 0、D1/D2 overflow 为 0，3/3
没有五米接近事件。该批继续属于描述性性能校准，不是拦截效果或学习算法验收。

## 2026-07-22 发布边界与冻结热点复测

detached clean 提交 `8f8619246298bdce34fabb7c7199bc282487bd45` 完成相同 seed 42000
的 2.2/10 秒对照，以及 seeds 42000-42002 的三组 10 秒运行。D1 对每个扫描继续执行状态
更新并保留一条发布；同一融合时刻内只有最后一个后验构造完整航迹数组，其余发布携带空的
`tracks`、`track_count=0`、真实 `current_track_count`、扫描摘要和观测谱系。旧 schema 对
`track_count == len(tracks)` 的约束保持成立。

三组 10 秒核心墙钟均值为 155.895 秒，实时倍率均值 0.0642，峰值驻留内存均值
2.889 GiB。相对上一候选，三项变化分别为 -9.4%、+10.4% 和 -5.4%。D1 融合均值由
103.339 秒降至 92.991 秒；模块发布总线均值由 7.574 秒降至 6.211 秒；文件系统写出块
均值下降 23.4%。state-only/full 快照数量分别为 `310/454`、`328/516` 和 `278/504`。

seed 42000 的长短单位仿真时间成本增长由 2.036 倍降至 1.830 倍，在线日志增长由
1.436 倍降至 1.249 倍。D5 终端配准单次调用成本增长由 2.696 倍降至 2.423 倍，但仍为
开放 P1。D3 三 seed 累计时间由 3.348 秒变为 3.289 秒，按基本持平处理，不据此修改代价、
迟滞或求解主线。

3/3 episode 均为 clean、有限状态、在线真值使用为 0，D1/D2 overflow 为 0。场景配置、
离线真值标签、三维真值数组、接近事件、扫描事件和既有业务摘要与上一候选相同。D6 将三组
结果归类为 `descriptive_clean_source_calibration`；该证据不关闭实时性、物理拦截、AirSim
或学习模型准入。详细结果见
`docs/SCALABLE_3D_LONG_DURATION_PERFORMANCE_CALIBRATION_CN.md`。

## 2026-07-22 创新求解治理与跨构建审计

clean 候选提交 `f80b5bd42e2c1beb707fd68bfb820d9607c80df3` 使用与 `8f86192` 相同的
200 对 200 名义场景、10 秒时长和 seeds 42000-42002。三 seed 核心墙钟均值由
155.895 秒降至 150.875 秒，下降 3.22%；进程总耗时均值由 222.780 秒降至
195.363 秒，峰值驻留内存均值由 2.889 GiB 降至 2.359 GiB。D1 实际创新方程求解次数由
7,130,228 次降至 1,578,677 次，下降 77.86%。D1 融合、D2 关联和 D5 终端关联均值分别为
88.330、7.671 和 1.974 秒。D3 与 D7 均略有增长，按单机描述性波动处理，不改变规则代价、
迟滞或比例导引算法。

`cross_build_equivalence.py` 对两个独立 clean build 的同 seed 制品执行流式语义审计。工具
先验证 D3/D7 原始来源载荷的 SHA-256，再按首次发布顺序映射 D3 不透明计划编号。D4 的
authority digest、正式裁决 digest 和 advisory ID 不按事件号删除或替换；审计先验证原始
内容地址，再用规范化计划谱系重新计算。owner、版本、epoch、lease、区域、资源、目标、
联盟、动作和下游引用仍逐条比较。三个 seed 均通过在线记录数、主题计数、逐主题规范哈希、
真值数组、离线标签、接近事件和 summary 合同检查。

提交 `12c5073` 已为 D1 posterior 跨 D2 调度周期的漏消费建立新的行为基线。main 只锁存
尚未消费的真实后验，并在下一关联 tick 交给 D2；不把航迹时间改为控制时刻，也不放宽
D7 的 `max_track_age_s`。seed 42000 的两次 clean 10 秒运行通过逐主题载荷、计划谱系、
真值数组和摘要合同的同提交语义等价审计，核心墙钟为 `107.853/122.032 s`，波动约 13%。

该修复有意改变旧的漏消费行为。`f80b5bd` 在 `1.00 s` 仍以旧 D2 后验形成 197 条分配，
`12c5073` 在同一时刻消费待处理后验并形成 200 条分配，控制状态从下一积分步开始分叉；
两者不能再要求跨提交业务等价。main 随后在 `b681c8f` 增加后验代次、D2 消费代次、
节拍前合并计数和结束排空回归，观测治理快照升级为
`scalable3d-observation-governance-runtime-v2`。新代次字段不改 D1/D2 算法、量测时间或
协方差，只提供可回放的消费血缘。

detached clean 提交 `0d2da25c14e50f8f9a10ad47a7bd74e5c5e577fb` 已完成新的三 seed
10 秒基线。seed `42000/42001/42002` 的核心墙钟为 `96.787/103.472/103.633 s`，均值
`101.298 s`；实时倍率均值为 `0.0988`。D1 融合、D1 扫描输入、D2 关联、D3 分配、D5
终端配准和 D7 导引累计时间均值分别为 `55.275/12.743/5.679/2.455/1.247/3.981 s`。
该批建立当前行为和性能基线，仍未达到实时目标。

三次 D1 最终代次为 `453/516/505`，完整后验发布数与之逐项相等；D2 最终消费代次逐项
追平 D1，D2 发布/消费均为 48 次，节拍前合并数为 `405/468/457`，结束时 pending 均为空。
D6 v6 被动评估将 3/3 判为 generation integrity 通过，failure reason 为空，在线真值使用
为 0。seed 42000 同提交重复运行通过全量语义等价审计，核心墙钟为 `96.787/96.704 s`。
与 `12c5073` 的 811 处在线差异全部来自新增的 D1/D2 代次字段；summary 合同、真值、计划
谱系和其余载荷一致。该批仍是三 seed 描述性 clean 校准，不是 20 个未见 seed 或正式实验
矩阵验收。

同一 detached clean 提交随后顺序完成 seed `1000-1019` 的 20 组 nominal 200 对 200、
10 秒规则全栈。20/20 进程退出为 0、状态有限、在线真值使用为 0、分配保持为 0；D1 完整
后验代次从 `410` 到 `499`，D2 最终消费逐组追平 D1，消费次数与节拍前合并次数之和逐组
等于 D1 代次，pending 均为空。核心墙钟均值/范围为 `96.391/88.035-102.573 s`，实时倍率
均值/范围为 `0.1039/0.0975-0.1136`，仍未达到实时目标。D1 融合、扫描输入、D2 关联、
D3 分配、D5 终端配准和 D7 导引均值为 `51.649/12.418/5.492/2.448/1.185/3.638 s`。

D6 v6 对 20/20 给出基础 clean provenance 可用、generation integrity=true、failure reason
为空。D3 计划覆盖率均值为 `0.989606`，2000 次 seed bootstrap 95% 区间为
`[0.987144, 0.991813]`；D5 最终 binding 数均值/范围为 `25.95/9-41`。该批没有五米接近，
学习 bundle 未加载，且 episode 未声明实验矩阵 metadata，因此全部只能归类为
`descriptive_clean_source_calibration`。它不是正式 R0/G1/A1/A2/A3/C1/F1 算法比较，也不
证明物理拦截或学习策略采用。

后续诊断代码将 `stage_timings.csv` 升级为
`scalable3d-stage-timings-v2`。每个阶段除总耗时、调用次数和均值外，新增单次调用
`P50/P95/max` 及 availability；缺少调用样本时保留空值和原因，不回填为 0。模块内分布
只在 episode 收束时计算，在线 step 不执行重复分位计算。
5v5、1.2 秒、seed 41 冒烟验证了新列、有限状态和在线真值使用为 0；该冒烟只验证记录
合同。长时对照输出同步升级为 `scalable3d-long-duration-comparison-v2`，可读取无分位列的
历史 CSV，但将其明确标为 unavailable。200 对 200 的稳定窗口分布仍需在下一 clean 候选上
重新测量。

detached clean `4ac3bb2` 已完成 nominal 200 对 200、seed 1000 的 2.2 秒与 10 秒同源
校准。10 秒核心墙钟为 `85.002 s`，实时倍率为 `0.1176`；相对 `0d2da25` 同 seed 的
`94.105 s` 下降 `9.67%`。D1 融合从 `49.697 s` 降至 `40.273 s`，下降 `18.96%`；
D1 扫描输入从 `12.315 s` 增至 `12.561 s`。跨构建审计确认 21,366 条在线记录的规范载荷、
真值状态、计划谱系和运行确认一致。该结果证明优化没有改变当前规则基线业务语义，但仍是
单 seed 描述性校准。

10 秒 episode 的 D1 融合单次调用 `P50/P95/max` 为
`33.252/224.764/592.957 ms`，D2 关联为 `121.972/137.335/145.966 ms`。2.2 秒与 10 秒
长短对照安全合同全部通过，但 D1 融合、D2 关联和 D5 终端配准的单次成本仍随 episode
展开增长。外部进程总时长为 `1:55.95`，峰值驻留内存为 `2,468,928 KiB`；这两个值与
`summary.wall_time_s` 分栏解释。D6 v7 对该 episode 的离线消费耗时为 `10.24 s`、峰值
驻留内存为 `936,056 KiB`。正式七变体矩阵仍为 0 episode，实时性和多 seed 尾延时 P1
继续开放。

原始 episode 约 1.1 GiB，继续按生成物规则保存在忽略目录，不提交 Git。仓库内的紧凑证据
摘要为 `docs/SCALABLE_3D_STAGE_TIMING_CALIBRATION_20260722.json`，记录两端 clean
提交、场景配置哈希、manifest/summary/online 产物哈希、跨构建审计哈希、阶段分位和验收
边界。报告结论不依赖临时目录路径本身。

D1 使用该 seed 1000 冻结输入完成 scan-input 尾延时专项。771 个已校验
`SensorScanFrame` 在快照完整时直接复用，检测到对象、标量或数组可写状态变化时回退原有
完整快照和 fail-closed 校验。帧重建由 771 次降至 0，organizer 内 observation 再快照由
11,889 次降至 0。前 256 个扫描交错 5 轮的 P50/P95 由
`1.942/1.968 s` 降至 `0.881/0.894 s`，P50 描述性加速 `2.204x`；
`ScanInputOrganizer.ingest` cProfile 累计由 `15.545 s` 降至 `5.754 s`。

逐输入结果、审计、释放顺序、融合状态与协方差、双时间戳、谱系、分级、物化航迹、
终态及操作数共 14 项等价条件全部通过，在线 truth 使用为 0。机器报告 SHA-256 为
`9510bd60b862be98a3816f238cd27c08c942e501e9dec27b96d598c45dc2d1df`。
该专项运行来自当前未提交 D1 工作区，只关闭重复快照热点；clean full-stack、多 seed、
AirSim、实时性和融合 P95/max 仍未验收。

D6 更新后的真值隔离入口已实际复读同一 seed 1000 身份制品。严格 ID Switch 仍为
unavailable；部分诊断在来源 SHA 和 identity manifest 校验通过后给出映射/帧/相邻转移覆盖率
`98.54%/6.25%/0%`、385 个锚点区间和保守下界 7。报告明确
`strict_id_switch_count_backfilled=false`、`id_switch_upper_bound_reported=false`。该结果只关闭
单 seed partial consumer 接线。D6 当前全量回归为 `567 passed, 1 warning`；新增 12 项包含
3 项独立合同测试和 9 项来源篡改参数化测试。

D2 随后在同一 seed 1000 冻结总线上完成 profiler v2 和语义等价热点优化。48/48 周期
公开输出、完整 tracker 状态及重复语义哈希一致；输入、fresh、replay quarantine、候选边和
匹配数保持 `9626/9038/588/8862/8823`。D2 core 中位数由 `2.928830 s` 降至
`2.204672 s`，描述性加速 `1.328465x`。优化消除了相同 `dt` 的 9,200 次重复常速度矩阵
构造、19,252 次可信 marginal 冗余比较和每帧一次重复 ledger 全量汇总。`global_track_id`、
ID Switch availability、门控、版本、claim ledger 和在线 truth 隔离语义均未变化。

该回放不构成实时验收。候选早晚 regular 窗口比为 `1.123036x`，与基线
`1.119661x` 基本相同；绝对常数成本下降，长窗口增长没有改善。报告固定在
`research_modules/d2_data_association/docs/d2_clean_4ac3bb2_seed1000_hotpath_20260723.json`，
SHA-256 为 `2256d6fdd29223ed5dd75351cd6bb208a4d67c55925eeba047620ac865b6c7da`。

D5 使用同一 seed 1000 的 25 帧短序列和 114 帧长序列完成热点归因。增量 history gauge
在长序列 723 次刷新中避免扫描 91,871 个 tracker 引用；2,289 个 singleton cluster
直接复用投影距离行，79 个多节点 cluster 保留完整有限性聚合；匿名 payload 内建叶子
快路径和 8,192 项有界 local-ID 缓存保持原 truth 审计与正则规则。pre-boundary-fix
cProfile 中 `process()` 累计由 `2.320 s` 降至 `1.987 s`，两轮 A/B 中位值均值由
`1.149 s` 降至 `0.929 s`。这些墙钟只用于方向归因。

最终源码另行修复了 singleton 行复用的 `-0.0` 符号位边界。修复后冻结短/长重放的业务、
最终 binding 和冻结 v1 操作数哈希均与原发布记录一致；在线 truth 使用和
`global_track_id` 改写均为 0。当前 D5 全量为 `551 passed`。机器报告明确区分 pre-fix
profiler 与 post-fix 语义验证，SHA-256 为
`7be68d15a982f720355e30b631cf44b860a5b017a6b4221819d9c9c08b26c449`。
长序列中 tracker pair、投影矩阵和绑定矩阵仍随输入组成显著增长；完整集成、多 seed、
AirSim 和固定硬件实时性 P1 保持开放。

## 2026-07-21 正式数据与开发训练状态

修复逐 episode checkpoint 和 D5 同流多批次边界后，新的正式生成目录已经完成全部
900 episode。数据覆盖 9 类场景、5 档规模和 100 个训练 seed，每个场景/规模 cell 为
20 episode；seed `1000-1019` 保留给最终验收。episode index 连续且唯一，在线真值字段
使用总数为 0，来源提交为干净的 `39b097e72487567ac915c2297eaa27eed49ef76b`。正式数据约
2.03 GB，未因后续标签或训练工作原地改写。

D3 已在完整数据上完成行为克隆开发训练，内部测试边排序一致性为 `0.803085`，计划完全
一致率为 `0.677019`，推理 P95 为 `2.554 ms`；bundle 保持 `development/shadow-only`，
未启动近端策略优化。D4 行为克隆内部测试 loss 为 `0.071545`、推理 P95 为 `0.7774 ms`，
但 14384 个区域动作没有非零 quota、hold、replan 或 transfer，因而同样不能进入 assist，
近端策略优化不可用。D5 正式跨视角图共有 12851 个图帧，其中 97.52% 没有候选边，负边
只有 19 条；原开发模型的高 F1 来自极弱的负样本分母，不能晋级。D5 已在独立 clean
补充课程中生成 4500 帧和 245032 条默认几何门候选边，正/负/未标注为
`57292/187740/0`，数据支持与训练数据来源门已通过。D5 后续已完成 clean composite 模型
训练和 seed `1000-1019` 的 paired shadow v2，覆盖 45 个场景规模单元、900 帧、13344 个
匿名节点和 74024 条候选边。冻结图模型边/簇 F1 为 1.0，但尺度差、尺度变化率差和角速度差
的单特征最佳方向曲线下面积约为 0.9973，说明合成保留集接近确定性可分。该结果不能代表真实
跨视角泛化；G1、assist 和 authority 仍关闭，等待 D6 独立审计与更困难的独立扰动数据。

D4 已另建不修改正式 900 episode 的区域动作覆盖课程。clean commit `9445ed6` 生成
100 个 seed、100 个 episode 和 300 帧，覆盖 hold 100、request_replan 200、非零配额
200 和跨区转移 100；硬约束、在线真值和保留 seed 泄漏均为 0。课程已具备 canonical
60/20/20 行为克隆只读视图，但没有可归因 outcome/reward，PPO、assist 和在线 authority
继续关闭。

D5 已另建主动视觉补充规则课程。clean commit `13e3728` 生成 100 episode、800 segment
和 1200 sample，覆盖 hold/observe-target/reacquire/search-sector=`200/600/200/200`、
wide/zoom=`1000/200`，拦截与侦察相机各 600 条。applied/rejected/missing 各 400 是确定性
故障注入覆盖，不是真实运行 ACK；reward、outcome、counterfactual 和 causal 标签均为
`0/1200 available`，PPO、assist 和相机权限继续关闭。

D5 已对该补充课程完成只读全样本审计。100 个 episode、1200 个样本、302 个受清单约束的
文件全部通过；1200 个样本的 35 维候选特征均为有限值，规范 episode/sample 切分为
`60/20/20` 和 `720/240/240`，在线真值、保留 seed 泄漏、dirty episode 和身份改写均为 0。
审计文件和内容 SHA-256 分别为
`9a03653538e6dae054da8c127ad4a20aae2481af6c9bbef987edfddff0b423d3` 和
`a11b65596a4c416deba6d0cb35dcc0c32342a5bae0481291d43e8de0e26550dd`。

D5 主动视觉已在 1,153,242 个规则示范样本上完成五轮完整行为克隆。测试精确动作准确率
为 `0.955978`，CPU 推理 P95 为 `0.1203 ms`，但 `reacquire` 占 92.16%，4,051 个
`observe_target` 测试样本的召回率为 0，hold 没有正样本，侦察相机精确动作准确率为
`0.621823`。该 bundle 只允许 shadow 加载，assist 和 PPO 均失败关闭。

D6 对正式数据生成了源外标签 sidecar，并完成 D3、D4、D5 producer 的全样本结构审计。
D3 覆盖 900 episode/1604 frame、3,658,815 条候选边和 117,304 条选择边；D4 覆盖正式
900 episode/1798 frame 及补充 100 episode/300 frame；D5 主动视觉补充覆盖 100 episode/
1200 sample/302 个制品。三类 producer 全样本状态均为 complete，联合报告 JSON/中文
Markdown SHA-256 分别为
`6593ee8a11d33b7c75d633f87e0fbd84cea421798bab0920ef4117cb044a87f5` 和
`7b6480d08870cbf21f532235ddfdbe9ca7f23ce05f681f2d18846f988355a4ba`。总体准入仍为 partial：
D4 只有 `898/1798` 帧具备无动作归因的相邻状态结果，D5 主动视觉虽有大量相邻观测结果，
但两者可归因 reward 均为 0；正式数据也没有新的 runtime ACK、paired shadow 和保留 seed
性能。D5 正式图的 99 条未标注边因缺少精确 lineage 保持 unavailable，clean 补充图数据尚未
训练模型。在正式 reward、同 seed 对照和学习实际采用证据闭合前，不能开展 PPO、在线辅助或
因果训练。

D6 还已在真实 main 3v3 质点 episode 上完成运行时计划确认与离线结果联接。2 条确认被识别
为 1 条新计划身份和 1 条同身份评估刷新，共形成 6 个资源-航迹窗口；来源序号、载荷哈希、
D2 身份映射和离线三维状态均通过校验，在线真值使用为 0。所有窗口具备有界距离进展诊断，
但当前没有同 seed 配对影子、保留 seed 结果、正式强化学习奖励或因果证据，因此 PPO、assist
和 authority 仍为 false，规则回退保持启用。

跨模块切分现由 detached `scalable3d-shared-seed-split-registry-v1` 统一管理。100 个训练
seed 固定为 `60/20/20`，映射与现有 D3 正式开发数据逐项一致，保留 seed 未进入任一桶。
原 D4、D5 manifest 仍保留各自历史切分；源外 canonical views 已形成，并通过 D6 的
manifest/view/readiness/summary 层一致性审计。D5 补充课程进一步通过 D6 的全样本证据消费，
但 D3、D4 仍停留在清单层。C1 联合训练继续关闭，原因已从 seed 切分不一致转为 D3/D4
全样本审计、真实动作采用/ACK、reward/outcome 和 paired shadow 缺失。
生成命令为：

```bash
python3 research_modules/scalable_3d_simulation/run_shared_seed_split.py \
  <formal-output>/training_seed_registry.json \
  <formal-output>/shared_seed_split_registry_v1/registry.json
```

main 已增加可选侦察观察线索，把 D3 当前计划中已有的 `global_track_id` 作为 D5 观察任务
送给侦察相机。它不改变 D3 分配，也不读取真值。2026-07-21 的 5v5、3 秒、seed 70-74
同 seed 对照中，启用线索后平均视觉观测从 `157.4` 增至 `163.4`，但候选边总数从 128
降至 64，命令拒绝均为 0。问题集中在观察目标选择与过早变焦的协同，当前默认关闭；专项
运行必须显式使用 `--d5-recon-track-cues`，该选项同时写入学习生成计划。

## 运行

```bash
python3 research_modules/scalable_3d_simulation/run_episode.py \
  --drone-count 200 \
  --duration 10 \
  --integrated-stack \
  --output research_modules/scalable_3d_simulation/outputs/smoke_200v200
```

三维静态图、GIF 和 MP4 只在需要时显式增加 `--plot`、`--gif` 或 `--mp4`。动画读取离线
真值状态文件，不进入在线 D1-D7 总线。

批量课程测试：

```bash
python3 research_modules/scalable_3d_simulation/run_batch.py \
  --scales 5 20 50 100 200 \
  --seeds 7 17 27 \
  --scenarios nominal dense_crossing formation_split evasive_multilevel \
  --integrated-stack --export-learning-data
```

`--export-learning-data` 只在集成栈下可用。单次运行输出 D3 匿名规划帧、D4 区域图、
D5 跨视角图和 D5 主动视觉整 episode staging；D5 不会在单一 seed 上伪造训练、验证和
测试集。主动视觉在线记录保存快照、规则示范、请求/实际动作和同帧相机反馈，离线文件
明确把 reward/outcome/counterfactual 标成 unavailable，不以数值零填充，也不伪造运行时
ACK。批量运行把完整 `(scenario_version, seed)` 组汇总到 `learning_dataset/`，至少有
三个组时才最终化 D5 跨视角图数据集；主动视觉数据集还必须满足至少 20 个完全未见 seed
的自身准入条件。D5 数值图与 `truth_entity_id` 标签保存为不同文件，主动视觉在线记录与
离线结果标签也物理分离，图特征和在线总线均不含真值编号。

大量训练 episode 使用流式入口，避免保存每个 episode 的完整世界状态：

```bash
python3 research_modules/scalable_3d_simulation/run_learning_dataset.py \
  --output research_modules/scalable_3d_simulation/outputs/learning_generation \
  --scenarios nominal dense_crossing \
  --scales 5 20 50 100 200 \
  --seeds 1 2 3 \
  --reserved-evaluation-seeds 1001 1002 1003 \
  --duration 2
```

该入口每个 episode 结束后立即写入 D3/D4/D5 staging，只在内存中保留轻量进度行。批次
成功最终化后，根目录保留 `episodes.jsonl`，已经转换为正式 D3 数据集的重复 staging 会被
删除；finalizer 异常或 D4 数据条件不足时保留相应 staging 供诊断和恢复。正式模式要求完整
场景目录、五档规模、训练 seed 与保留评估 seed 零重叠、干净工作树和 Git
忽略的输出目录。D5 主动视觉按数值 seed 跨场景/规模原子切分；默认 20% 测试比例和至少
20 个未见测试 seed，因此正式计划还必须提供足够的唯一生成 seed。该条件在 episode 启动
前检查，不能等批量运行结束后再失败。

冻结的首版训练计划为 `configs/learning_generation_balanced_v1.json`。它使用 100 个生成
seed，按五个 20-seed 分块均衡分配到 9 类场景和 5 档规模；每个场景/规模 cell 有 20 个
episode，总计 900 个。seed 1000-1019 完全保留给最终评估。正式运行命令为：

```bash
python3 research_modules/scalable_3d_simulation/run_learning_dataset.py \
  --schedule research_modules/scalable_3d_simulation/configs/learning_generation_balanced_v1.json \
  --formal \
  --max-episodes-per-run 45 \
  --output research_modules/scalable_3d_simulation/outputs/learning_generation_v1
```

每个完整 episode 都先同步写入 `episode_progress.jsonl`，再原子推进
`generation_checkpoint.json`；模块 staging 与进度索引必须一一对应。继续运行时使用相同参数并
增加 `--resume`。恢复入口逐字比较生成计划和训练 seed 注册表，校验 Git 提交、计划 SHA256、
连续 sequence、在线安全结果和 batch episode index。版本 2 checkpoint 允许在全部进度和
staging 已通过校验时恢复“进度领先旧 checkpoint”的崩溃窗口，并记录恢复次数与行数；checkpoint
领先、重复 episode、未索引或不完整制品仍失败关闭。全部 900 个 cell 完成后才执行统一最终化。
开发回归已覆盖 `1 + 2` 分块、单 episode 后异常续跑、旧版本 checkpoint 滞后恢复和篡改拒绝。
冻结 schedule 使用 `round_robin_cells_v1`，每连续 45 个 episode 各覆盖一次 9 类场景和
5 档规模，避免首个分块只运行单一场景或单一规模。

正式预检要求完整 45 个场景/规模组合且每个组合至少 20 个 seed，同时记录 schedule SHA256。
九场景存储门、三 seed 批次最终化门和代表分块启动门已经通过。D5 主动视觉仍占代表性
200v200 staging 的 96.8%，但三 seed 只需 12.04 秒，写入与最终化合计低于 episode 计算，
不再形成系统级阻塞。2026-07-20 的第一次正式运行曾在 209/900 后暴露 D5 同流多批次边界
问题；该未最终化目录只保留作故障证据。修复后使用干净提交从零生成的新目录已完成
900/900，旧、新 episode 没有拼接。

学习模型默认关闭。显式研究运行可增加下列参数；bundle 缺失、校验失败、分布外、低置信或
超时均保留规则路径：

```bash
python3 research_modules/scalable_3d_simulation/run_episode.py \
  --drone-count 20 --duration 3 --integrated-stack \
  --d3-learning-mode shadow --d3-model-bundle <d3_bundle> \
  --d4-learning-mode shadow --d4-model-bundle <d4_bundle> \
  --d5-model-bundle <d5_bundle> \
  --d5-active-vision-mode shadow \
  --d5-active-vision-bundle <d5_active_vision_bundle> \
  --output <episode_output>
```

D3 的 `assist` 只有在 bundle 内准入清单证明至少 20 个未见 seed、成本与安全非退化且
无回退帧时才可能生效。D4 建议先经过资源守恒、通信邻接、owner、epoch、lease、故障
围栏和联盟提交约束投影。只有运行时实际进入 `assist` 的后投影建议，main 才会在下一分配
周期使用冻结的来源快照和正式裁决进行一次性重验，再转换为 D3-owned 区域提示。D3 仍会
按当前计划、资源、已提交成员、备用和候选边二次校验。shadow 建议、重放、严格到期、
fault generation 变化和 regional authority 路径都不生效。D4 不修改正式裁决，也不直接
授权 D7。当前没有正式 D4 未见 seed 准入制品，实际研究运行仍保持 disabled/shadow。
D5 只有显式给出校验通过的 bundle 才使用图边概率，异常时继续采用几何规则。

主动视觉即使在学习模式 `disabled` 下也运行确定性 look-at/reacquire/scan 策略；这里的
`disabled` 只表示学习模型关闭。`shadow` 记录学习建议但实际执行规则动作，`assist` 仅在
bundle 内正式准入报告覆盖至少 20 个完全未见 seed、无安全/可见性/重捕获延迟退化时允许
采用学习动作。bundle 缺失、校验失败、分布外、超时或未准入时均执行规则命令。

场景目录还包含时延噪声、通信退化、中心失效、二级失效和高威胁多机需求配置。单一二级
接管、多二级区域所有权和二级再次失效后的完全分布式计划已经接入质点模块栈。所有路径
仍校验计划版本、区域所有者、故障代际、租约和提交模式；证据缺失或过期时保持闭锁。

默认不生成 200 路图像。相机模块只输出匿名 bbox、像素中心、投影协方差和独立离线真值
标签。远距离投影只有达到相机类型对应的最小 bbox 面积后才形成在线视觉观测，避免把
亚像素投影误报为可用检测。高频状态写入压缩 NPZ，事件写入 JSONL，汇总写入 JSON、
CSV 和中文 Markdown。

传感器自身处理时延与网络传输时延分开计算。批次先在 `measurement_timestamp + sensor
latency` 时刻进入通信队列，再按链路时延、抖动、带宽和丢包结果到达融合中心。episode
汇总记录发送、投递、丢弃、在途批次数和字节数。当前 D1-D7 仍作为同一进程内的组合栈
执行，模块间发布消息尚未拆成独立通信节点；报告不把传感器链路验证写成全分布式网络
闭环。

传感器场景包含中心雷达、分布式声学阵列和拦截/侦察相机。声学观测输出粗方位、协方差
和类别级声纹概率，`soundprint_is_identity=False`，不能作为目标身份编号使用。

`ScalableModuleStack` 是后续 D1-D7 的统一在线端口。输入只包含本时刻到达的匿名传感器
批次以及拦截机、侦察机自身导航状态；输出为 NED 三维加速度和版本化模块记录。目标真值
状态不会通过该端口传入在线模块，模块记录仍经过递归真值字段检查。

## 实验矩阵

`run_experiment_matrix.py` 统一编排 R0 纯规则、G1 跨视角图网络、A1 D3 代价修正、A2
D4 区域策略、A3 主动视觉、C1 学习组合和 F1 故障/高威胁完整体系。可比较变体使用相同的
场景、规模和 seed 形成 `comparison_key`。F1 只运行中心失效、二级失效和高威胁 M 对 N
场景，避免把与 C1 相同的模型组合重复解释为一种新算法。

矩阵运行强制使用 `entity_fixed_v1` 传感器随机序列。每个雷达、声学和视觉扫描按固定目标
槽位预取检测与噪声随机量，目标是否进入视场、是否已失活不会改变后续随机数位置。每个
`comparison_key` 另记录剔除算法版本后的外生配置 SHA-256；不同变体的该哈希不一致时停止
运行。普通 episode 继续默认 `sequential_v1`，因此既有正式数据和小规模回归不被重解释。

学习变体必须提供对应 bundle，且运行时诊断必须证明模型实际加载、辅助模式获准并生效。
缺 bundle、未准入或规则回退会阻断声明的学习变体，不能把规则结果记到学习组。正式模式
还要求完整 R0/G1/A1/A2/A3/C1/F1、完整场景目录、5/20/50/100/200 五档规模、至少
20 个唯一 seed、独立训练 seed 注册表、训练/测试 seed 零重叠和干净工作树。每个 episode
写盘后由 D6 从离线目录统一评分，矩阵本身不读取在线真值。

2026-07-20 使用 2v2、nominal、seed 101、0.25 秒完成一次脏工作树 R0 开发冒烟，有限状态
为真、在线真值使用为 0，并成功生成矩阵 manifest、逐 cell CSV 和 D6 离线报告。该结果只
验证编排与写盘，不属于正式消融或性能证据。

## 当前验证

2026-07-21 的 main 集成回归当前为 **90/90 passed**。其中 5v5、seed 7、1.2 秒场景形成
5 条 D1 航迹、5 条 D2 中心航迹、5 项 D3 分配和 5 路 D7 中段指令，在线真值字段使用为
0。200v200、seed 17、0.25 秒雷达烟测形成 200 条 D1/D2 航迹和 200 项分配；D3 从
40000 个完整 pair 中保留 6400 条候选边，D7 输出 `(200, 3)` 有限加速度。

同日补齐 D1/D2/D6 真值隔离评估链。D1 最终在线证据按观测保存创新平方和、门控、
六维估计、协方差、距离分档和乱序重放版本；D2 只依据 D1 源观测谱系生成逐帧中心航迹
真值映射。main 以 `observation_id + measurement_timestamp` 将每条 D1 在线证据精确连接
到 D2 `global_track_id` 和离线 `truth_id`，不使用航迹区间前向填充。连接不完整时相关
身份指标保持 unavailable。在线证据、离线真值状态、规范映射和结果文件分别写盘并绑定
真实文件 SHA256。D6 再通过公开适配器
输出逐 seed CSV、传感器/距离分档 CSV、聚合 JSON 和中文报告。5v5、seed 7、1.2 秒
回归中 D1 位置/速度 RMSE、NEES、NIS 均为 available，D2 `id_switch_count=0` 是有证据
的零；无模块栈时该字段保持 null/unavailable。该结果验证合同和写盘链，不是多 seed
精度达标结论。

中心失效场景已验证单一高空侦察节点覆盖全部活动区域时，D3 发布严格更新版本且 owner
切换为 `RECON-001`。两个二级节点可发布一份多 owner 区域计划；中心和二级先后失效时，
D3 可发布与 D4 裁决一致的 distributed 区域计划。D7 只对具有当前 owner、epoch、lease
和提交证据的任务区域恢复导引，空区域继续闭锁。该结果是接口和质点仿真证据，不是
AirSim、真实网络或实飞证据。

同一 seed、0.25 秒、仅启用雷达的短时规模测试结果如下。该数据用于定位开销，不作为
长时多 seed 验收结果。

| 目标/资源规模 | 实时因子 | D3 分配累计耗时/ms |
| ---: | ---: | ---: |
| 5 | 8.54 | 3.2 |
| 20 | 2.32 | 25.5 |
| 50 | 0.61 | 136.5 |
| 100 | 0.28 | 495.2 |
| 200 | 0.09 | 1970.7 |

200v200 条件下，D1、D2 和 D7 的累计耗时分别约为 120.0、107.8 和 20.3 毫秒，D3
约为 1970.7 毫秒，是当前首要性能瓶颈。D3 虽将 40000 条完整资源目标边压缩到 6400
条候选边，内部代价构造或求解仍存在密集矩阵和 Python 循环开销。episode 输出现在同时
记录世界、传感器、在线发布总线和 `module.d1_fusion` 至 `module.d7_guidance` 的分阶段
累计耗时。在线真值字段检查保持递归覆盖，已改为循环安全的迭代扫描并缓存重复字段名，
避免大批量航迹发布时重复执行昂贵的类型解析。外部模块发布仍默认深拷贝；集成模块栈对
每次新建且不再修改的负载显式转移所有权，省去一次大型航迹负载复制，真值扫描仍然执行。

2026-07-20 完成 D1 无多普勒雷达速度先验和 D2 相关六维后验修复后，以 radar-only、
seed 17 复测：

| 规模/时长 | D1 速度 P50/P90/max m/s | D2 速度 P50/P90/max m/s | D3 分配 | 实时因子 |
| --- | --- | --- | ---: | ---: |
| 50v50 / 2.2 s | 4.53 / 6.15 / 9.27 | 3.94 / 5.28 / 8.83 | 50 | 1.055 |
| 200v200 / 2.2 s | 4.13 / 6.78 / 9.19 | 3.51 / 6.02 / 8.34 | 195 | 0.254 |
| 200v200 / 3.2 s | - | - | 200 | 0.210 |

2.2 秒结果中的 5 项差额不是 `intercept_unreachable_3d`。首个雷达周期受检测概率影响只形成
195 条航迹，D3 在最小驻留时间内保留版本 1；`t=3.0 s` 时发布版本 2 并覆盖全部 200 条
航迹。D2 没有继续放大 D1 速度均值，200 条航迹和 ID 集保持稳定。上面的原 0.25 秒表是
稀疏分配优化前的历史短测，仅保留作性能演进参照。

保留 seed `1000-1019` 上的 D1/D2 NIS、NEES、门控率和长期速度 coverage 仍未完成。
D5 已完成 20-seed paired shadow，但 `shared_global_track_count=0` 且尺度特征接近确定性
可分，满分结果只说明当前合成保留集可分，不能外推到真实跨视角泛化。D3、D4 和 D5 均已
具备模块内数据、训练、bundle 与规则回退管线；现有 bundle 均未获得 assist 准入。D3/D4
clean v2 保留集和 D6 profile-bound availability sidecar 已完成，D3 同帧 assignment comparison
可用。当前剩余条件是取得严格绑定的 runtime ACK 和采用后物理结果窗口，并在独立故障场景
评估 D4 降级策略。缺少这些证据时不计算 paired physical effect，也不开放 PPO、assist 或
authority。

同日完成主动视觉运行时接线后，5v5、1.4 秒开发冒烟发出并确认 84 条相机命令，拒绝数为
0。200v200、seed 17、1.2 秒开发诊断发出并确认 1872 条命令，主动视觉 9 次调用累计约
0.374 秒；整段实时因子为 0.068。该运行来自未提交工作树和单一 seed，只用于接口及耗时
定位。D1、D2、D3 累计耗时分别约 7.76、3.50、3.82 秒，仍是主要开销，主动视觉不是本次
实时性下降的首要来源。

同日补齐 D4 区域建议的下一周期消费桥接。定向回归验证一次正常消费与 D3 应用，以及
advisory replay、严格到期和 fault generation 变化三类闭锁；在线真值使用仍为 0。该结果
关闭的是单进程质点 planning-loop 接线，不代表已有可准入 D4 checkpoint，也不包含跨进程
持久化 consumed-ID ledger、长时 200v200 或真实通信验证。

D5 主动视觉整 episode 数据已接入 main 学习导出。单 episode 和三 seed staging 测试证明
在线记录与离线标签分目录写入，奖励不可用时保持 null；三 seed 不满足 20 个未见 seed，
因此数据集按预期不最终化。该结果只证明数据合同和失败关闭，尚无 D6 outcome/
counterfactual 回填、正式行为克隆或近端策略优化结果。

同日新增 `run_learning_dataset.py` 流式生成入口，并以 nominal、2v2/5v5、seed 1/2/3、
每例 2 秒完成 6 个开发 episode。6/6 均为有限状态，在线真值使用为 0；导出 D3 12 帧、
D4 12 帧、D5 图 11 帧和主动视觉 107 帧。D5 图数据集成功最终化；主动视觉因计划测试
seed 只有 1 个而以 `insufficient_unseen_test_seeds` 保留 staging，符合失败关闭。开发输出
共 4.4 MB，其中主动视觉约 3.6 MB。

容量探针随后完成九类 200v200、每例 2 秒的干净工作树复测。9/9 状态有限，在线真值使用为
0，最终学习目录为 55.36 MB；全部 900 例均按该 200v200 平均值计算的存储保守上界为
5.54 GB。D3、D4 和 D5 跨视角图正常最终化，D5 主动视觉因不足 20 个未见测试 seed 保留
staging，符合失败关闭。

同一 nominal seed 930-932 的 clean-tree 计时经过两轮优化后，总耗时由 467.8 秒降至
144.6 秒，staging 由 225.9 秒降至 12.4 秒，批次最终化由 116.6 秒降至 7.3 秒；episode
运行保持在 124.7-125.2 秒。第二轮 D5 主动视觉写入为 12.04 秒，三场分别为
4.05/3.99/4.00 秒。D5 仍占 staging 的 96.8%，但写入与最终化合计 19.7 秒，已低于
episode 计算的 124.7 秒，不再主导总耗时。存储、最终化和首个正式代表分块启动门已经
通过；完整 900 episode、20 个未见 seed 和 200v200 实时性目标仍开放。两个正式代表分块
已完成到 90/900，连续运行随后完成到 209/900，并在第 210 项触发 D5 同流多批次异常。
runner 的 checkpoint 已升级为逐 episode 原子推进并兼容严格校验后的旧 checkpoint 滞后恢复；
这只解决异常后的完整边界恢复，不允许跨 Git 提交拼接正式数据。详细结果见
`docs/SCALABLE_3D_CAPACITY_AND_RUNTIME_REPORT_CN.md`。

每个物理步结束后，离线评估侧按三维 5 米门限登记唯一接近事件。事件中的真值目标号只
写入 `offline_proximity_intercepts.jsonl`，不进入在线总线；D6 还需结合分配与身份映射
判断该物理接近是否属于正确任务。

### 保留种子隔离干预

`run_reserved_seed_interventions.py` 对 seed `1000-1019` 各运行一个规则源 episode，固定
`entity_fixed_v1` 传感器随机流，并在同一个 D3/D4 时刻派生 control 和 treatment 两臂。
每个源 episode 只运行一次，两臂共享量测、规划帧、区域快照、通信日程和故障日程。输出
包含 20 条来源谱系、D3/D4 各 40 条隔离收据、顶层 manifest、中文报告和 SHA-256 清单。
任何臂均不可发布到在线总线，也不生成运行确认、物理结果、反事实或因果结论。

2026-07-21 已在 detached clean worktree 的提交 `6d5bfea` 上完成 nominal 5v5、2.2 秒、
seed `1000-1019` 的 v1 正式运行。20 个源 episode 均为干净、有限状态，在线真值使用为 0。
D6 已独立校验输入清单、lineage、D3/D4 各 40 条收据和全部 SHA-256。v1 中 D3 的 20 个
treatment 均因旧 OOD 门回退；复核确认 `previous_binding` 是二元特征，合法值 1 被错误套用
连续高斯 z 门。D3 已按二元端点修复，连续 6σ 门、模型和权重未变。D4 的候选分布外、有限值
和 50 ms 时延门均为 20/20 通过，置信度范围为 `0.508893-0.569492`，低于冻结门限 `0.6`，
因此 20/20 继续规则回退。D6 对 v1 的 paired outcome/effect 保持 `unavailable/null`。

运行器现升级为 `scalable3d-reserved-seed-interventions-v2`。D3 安全外壳标识升级为
`d3-offline-intervention-safety-shell-v2`，绑定二元端点与连续特征分离检查；顶层 manifest
和中文报告增加 D4 v2 的 confidence/OOD/latency/finite/failure 分门统计。clean 源提交
`78912963b67fe86ee9a8d29186b18a9dd60c460c` 的 v2 正式结果包含 20 个有限、在线真值使用为 0
的源 episode。D3 20/20 treatment 实际应用、0 回退，20/20 有效代价矩阵变化但最终 binding
均未变；D4 20/20 候选被评估，只有 confidence gate 为 0/20，其余四门均为 20/20，最终全部
规则回退。

D6 在提交 `d4e8562` 中完成 v1/v2 严格 consumer 和 profile/schema 绑定。当前 canonical 输出为
`reserved_seed_interventions_nominal_5v5_1000_1019_formal_7891296_d6_profile_bound_v2_audit_20260722`，
sidecar 文件/内容 SHA-256 分别为 `f3852251...c3b` / `c02a345c...d2d`。审计只开放同帧 offline
assignment comparison；runtime ACK、physical outcome/effect、counterfactual 和 causal 仍不可用。
学习权限继续固定为 `PPO/assist/authority=false`、`rule_fallback=true`。

### D1/D2 观测治理

2026-07-22，D1 前置扫描组织器和 D2 观测声明账本已接入统一 episode 状态机。D1 按量测
时间水位线对完整扫描做有界排序，重复、冲突、过晚和容量溢出整扫描拒绝。D2 使用不透明
观测标识、源命名空间和量测时刻区分新证据与后验重放；声明按安全水位线淘汰，超过容量时
失败关闭。main 总线保留双时间戳、协方差、公开审计和中心航迹身份所有权。

active-risk 5v5 seed 1005 的当前 1.1 秒集成路径始终保持 5 条规范航迹，起始数为 5，重复
出生、暂定删除和错误合并均为 0。结束排空阶段先按量测顺序融合并发布全部 D1 尾部扫描，
只把最终融合后验送 D2 一次，并在该次中心关联中归档所有待发布的 D1 源观测谱系。因此旧
实现由逐尾帧产生的 9 次人工重放现为 0，离线一致性映射仍覆盖全部已融合观测。正常运行期
的周期关联、短时 coast、失联老化和控制门控没有改变。

快速治理基准位于
`outputs/observation_governance_calibration_20260722_development`。20、50、100、200 四档各
运行 5 个 seed，每例 136 帧、33.75 秒。全部 episode 在线真值使用为 0；每例 D1 正确重排
12 个扫描，拒绝、过旧和溢出均为 0，峰值缓冲为 3 个扫描。D2 峰值声明数分别为
2390/4800、6020/12000、12070/24000 和 24170/48000，安全淘汰数分别为 285、735、1485
和 2985，容量溢出为 0。离线侧车的近邻召回为 1.0，错误抑制和错误合并为 0，确认时延为
0.25 秒。200 规模 D1 与 D2 合计峰值 `tracemalloc` 约 58.99 MB。

上述 development 批次来自脏工作树。同配置已在 detached clean 提交
`e4d66db02a0b8f1b867a0e81b4a73de84588426b` 正式复跑，输出位于
`outputs/observation_governance_calibration_20260722_formal_e4d66db`。20 个 episode 均为
`formal/clean`，D6 采用 `formal_only` 输入策略；在线真值、D1 结束缓冲、D1/D2 溢出均为
0。200 规模 D1+D2 峰值内存均值为 58996981 B，最大为 59007120 B。聚合 JSON 和中文报告
SHA-256 分别为 `6fb64252292aaedd3c68d1bfea64b76496136ce6edb32add61a281d511c4ed22`
和 `6198854b867d39fb2f1300cddeb1f75972ba8b7952361622213050115feb0827`。

该正式批次只测试观测治理，不是完整 D1/D2 精度、AirSim 或 200 对 200 拦截验收。另行运行
的 200v200 单 seed、2.2 秒全栈质点烟测在尾部合并后用时 60.21 秒，实时倍率 0.0365；相比
合并前 95.41 秒有所下降，但仍明显不实时。当前主要耗时为 D1 融合累计 35.12 秒和 D3 三次
分配累计 7.33 秒。完整多 seed 物理闭环、真实 AirSim 时延分布和阈值冻结仍开放。

## 版本

- 世界：`scalable3d-world-v1`
- 总线：`scalable3d-episode-bus-v1`
- 场景：`scalable3d-scenario-v1`
- 在线观测：`scalable3d-observation-v1`
- 离线真值：`scalable3d-offline-truth-v2`，读取端继续兼容 target-only v1
- D4 区域策略：`d4-region-resource-rule-v1` 或带权重 SHA256 的显式模型版本
- 学习导出：`scalable3d-learning-export-v2`
- 学习生成计划：`scalable3d-learning-generation-plan-v1`
- D5 主动视觉数据集：`d5.active-vision-episode-dataset.v3`
- D5 主动视觉模型 bundle：按 D5 当前代码和权重 manifest 记录，不从目录名推断
- 主动视觉快照/动作：`d5.active-vision-snapshot.v1` / `d5.active-vision-action.v1`
- 主动视觉策略：`d5-active-vision-rule-v1` 或模型语义版本加权重指纹
- 相机命令确认：`scalable3d-camera-command-ack-v1`
- 实验矩阵：`scalable3d-experiment-matrix-v1`
- D1 离线一致性清单：`scalable3d-offline-consistency-evaluation-manifest-v1`
- D1 扫描输入审计：`d1.scan_input.audit_summary.v1`
- D2 身份评估清单：当前 producer 使用 `scalable3d-offline-identity-evaluation-manifest-v2`，D6 只读兼容 v1
- D2 观测证据治理：`d2-observation-evidence-governance-v1`
- D2 观测声明账本：`d2-observation-claim-ledger-v2`
- main 观测治理快照：`scalable3d-observation-governance-runtime-v2`
- D1 融合性能诊断：`d1.fusion_performance_diagnostics.v1`
- D5 终端操作数诊断：`d5-scalable3d-operation-counts-v1`
- D6 观测治理标定输入：`scalable3d-observation-governance-calibration-input-v1`
- D6 真值隔离清单：`scalable3d-d6-truth-isolated-manifest-v1`
- 跨模块共享 seed 切分：`scalable3d-shared-seed-split-registry-v1`
- 保留 seed 隔离干预：新制品使用 `scalable3d-reserved-seed-interventions-v2`；历史正式证据保留 v1
- 共同检查点隔离物理续跑：`scalable3d-checkpoint-paired-physical-rollout-v2`，记录源 Git 提交、源提交一致性、源 episode 数和脏源计数

每个 episode 的 `manifest.json` 记录上述版本、Git commit、配置 SHA256、seed、模型版本和
阈值版本。在线总线拒绝任何包含 truth/actor/object identity 字段的观测负载。

分支、提交、模型制品和阶段标签规则见 [VERSIONING.md](VERSIONING.md)。
