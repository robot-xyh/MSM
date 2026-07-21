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
  --output research_modules/scalable_3d_simulation/outputs/learning_generation_v1
```

正式预检要求完整 45 个场景/规模组合且每个组合至少 20 个 seed，同时记录 schedule SHA256。
九场景存储门和三 seed 批次最终化门已经通过；正式生成吞吐门仍保持开放。当前 D5 主动
视觉 writer/压缩占 200v200 staging 的 99% 以上，runner 还缺少正式批次可恢复的分块执行。
在这两项关闭前，不直接启动上述完整批次。

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

学习变体必须提供对应 bundle，且运行时诊断必须证明模型实际加载、辅助模式获准并生效。
缺 bundle、未准入或规则回退会阻断声明的学习变体，不能把规则结果记到学习组。正式模式
还要求完整 R0/G1/A1/A2/A3/C1/F1、完整场景目录、5/20/50/100/200 五档规模、至少
20 个唯一 seed、独立训练 seed 注册表、训练/测试 seed 零重叠和干净工作树。每个 episode
写盘后由 D6 从离线目录统一评分，矩阵本身不读取在线真值。

2026-07-20 使用 2v2、nominal、seed 101、0.25 秒完成一次脏工作树 R0 开发冒烟，有限状态
为真、在线真值使用为 0，并成功生成矩阵 manifest、逐 cell CSV 和 D6 离线报告。该结果只
验证编排与写盘，不属于正式消融或性能证据。

## 当前验证

2026-07-20 的 main 集成回归为 **71/71 passed**。其中 5v5、seed 7、1.2 秒场景形成
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

当前尚未完成至少 20 个未见 seed 的 NIS/NEES、门控率和长期速度 coverage，也未完成
200-camera 图构建。D3 已具备整 seed 数据集、行为克隆、原生近端策略优化、bundle 和
paired shadow evaluator；D4 已具备变长区域图、规则基线、行为克隆、近端策略优化和安全
投影；D5 已具备真值物理隔离的数据集、原生图网络训练、校准和校验加载；D6 已能离线消费
规模化 episode 并输出逐 seed、聚合、中文报告和曲线。上述结果只证明研究管线和回退机制，
没有独立验证 checkpoint，也没有模型准入结论。D5 主动视觉的正式训练数据、模型权重和
至少 20 个未见 seed 的联合验收仍未完成。

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

同一 nominal seed 930-932 的优化前后计时显示，总耗时由 467.8 秒降至 262.3 秒，staging
由 225.9 秒降至 126.5 秒，批次最终化由 116.6 秒降至 7.7 秒；episode 运行保持在约
125-128 秒。优化后 D3、D4、D5 图的三 seed staging 合计不足 0.5 秒，D5 主动视觉写入为
126.1 秒，占 staging 的 99.7%。因此存储和最终化门已关闭，吞吐门仍由主动视觉 writer/
压缩及批次恢复能力阻塞。详细证据见 `docs/SCALABLE_3D_CAPACITY_AND_RUNTIME_REPORT_CN.md`。

每个物理步结束后，离线评估侧按三维 5 米门限登记唯一接近事件。事件中的真值目标号只
写入 `offline_proximity_intercepts.jsonl`，不进入在线总线；D6 还需结合分配与身份映射
判断该物理接近是否属于正确任务。

## 版本

- 世界：`scalable3d-world-v1`
- 总线：`scalable3d-episode-bus-v1`
- 场景：`scalable3d-scenario-v1`
- 在线观测：`scalable3d-observation-v1`
- 离线真值：`scalable3d-offline-truth-v1`
- D4 区域策略：`d4-region-resource-rule-v1` 或带权重 SHA256 的显式模型版本
- 学习导出：`scalable3d-learning-export-v2`
- 学习生成计划：`scalable3d-learning-generation-plan-v1`
- D5 主动视觉数据集：`d5.active-vision-episode-dataset.v2`
- D5 主动视觉模型 bundle：`d5.active-vision-model-bundle.v3`
- 主动视觉快照/动作：`d5.active-vision-snapshot.v1` / `d5.active-vision-action.v1`
- 主动视觉策略：`d5-active-vision-rule-v1` 或模型语义版本加权重指纹
- 相机命令确认：`scalable3d-camera-command-ack-v1`
- 实验矩阵：`scalable3d-experiment-matrix-v1`
- D1 离线一致性清单：`scalable3d-offline-consistency-evaluation-manifest-v1`
- D2 身份评估清单：`scalable3d-offline-identity-evaluation-manifest-v1`
- D6 真值隔离清单：`scalable3d-d6-truth-isolated-manifest-v1`

每个 episode 的 `manifest.json` 记录上述版本、Git commit、配置 SHA256、seed、模型版本和
阈值版本。在线总线拒绝任何包含 truth/actor/object identity 字段的观测负载。

分支、提交、模型制品和阶段标签规则见 [VERSIONING.md](VERSIONING.md)。
