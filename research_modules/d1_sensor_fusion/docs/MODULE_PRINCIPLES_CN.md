# 第一研究模块（D1）异构传感器融合原理与当前实现

**状态日期：2026-07-22**

**适用范围：科研仿真、离线回放与接口验证**

## 当前权威增量（2026-07-22）

### 状态更新与发布分离原则

D1 的扫描语义不能为了减少日志而合并。每个 released scan 仍独立完成扫描前航迹门控、一对一
关联、固定时滞乱序重放、双时间戳和协方差治理。可以延迟的是 `GlobalTrack` 对象构造，而非状态
更新。`process_scan_batch()` 因此保留默认完整返回，并增加显式
`materialize_tracks=False` 模式。

状态-only 结果以 `tracks_materialized=False` 表明没有航迹快照，并直接提供
`current_track_count`。访问 `tracks` 会抛出错误，不能把未物化结果解释成零航迹。main 完成本
运行时刻的全部扫描后，通过 `materialize_global_tracks()` 生成一次完整快照。该快照仍包含 NED
六状态、6×6 协方差、分级、量测/到达时间、来源谱系、健康和关联审计；内部状态与发布数组不共享。

三目标四扫描构造序列覆盖默认 6 秒 fixed-lag 和检查点前 OOSM。参考路径物化 12 条航迹对象，
延迟路径物化 3 条；终态航迹、协方差、元数据、健康、时延和一致性证据相同。D1 全量
`168 passed in 29.43s`。这一结果证明接口等价和操作数下降，main 接线后的全栈墙钟、内存和日志
收益仍需 clean 多随机种子验证。

发布审计 v2 将 `publication_count` 拆为 `materialized_snapshot_count` 和
`state_only_count`，`track_record_count` 只统计完整快照内的航迹。无新标记的旧 v1 日志继续按
完整快照处理。新 writer 使用 `tracks_materialized=false / tracks=[] / track_count=0`，并以
`current_track_count` 表示真实内部航迹数；audit 同时兼容过渡期 `tracks=null`。state-only 不参与
航迹快照哈希，也不计作零航迹状态。

### 长时固定滞后缓存原则

10 s 冻结回放包含 764 个扫描和 12,107 条匿名观测。随着 episode 变长，已完成滤波的历史前缀
仍会被状态查询和固定滞后重基重复遍历，导致滤波更新次数随扫描数超线性增长。优化遵循一条边界：
只复用由失效规则证明没有变化的后验，不改变观测、时间、协方差或门控语义。

当前实现用有序后验检查点支持二分状态查询。窗口内迟到观测只失效插入点后的检查点；固定滞后
重基后保留边界之后仍有效的后缀。合法缓存前缀的一致性证据沿用原模型、后验和门控结果，只更新
当前 replay revision 和 replay count。起始状态、检查点前历史或后缀发生变化时仍执行完整滤波。

旧路径与优化路径的逐扫描哈希均为
`sha256:e2b4c56d9200ce0b63ccf4311b4c26d0fb395bdca875afd7b4b0dceb6a0d82f8`；终态航迹哈希均为
`sha256:98f11de46483ce36a137ade635244cf00c2cf51fcbef869215c3473319b5aa2c`；一致性证据哈希均为
`sha256:c3380b9b6327731927b60f36474e47ca1ef5f2161c7b53aafa2c7d4793db32ef`。history replay
由 170,106 降至 13,397，filter update 由 120,440 降至 9,549，纯融合墙钟由 157.237 s 降至
107.449 s。优化路径同时记录 152,861 次检查点状态查询、110,891 次固定滞后后缀复用、300,024
次合法前缀快路径和 194,916 次缓存一致性刷新。该结果证明冻结输入语义等价，不证明完整系统
已经实时。

`FusionPerformanceDiagnostics` 只包含固定数量的累计标量，适合 episode profiler 低频采样。
发布侧历史基线的 764 条全量快照约 186.2 MiB，其中 357 条具有相同融合时刻，294 条与上一条
航迹快照相同。D1 必须逐扫描融合；当前已可在同一 tick 延迟中间物化。跨 tick 合并持久化记录
仍属于 main 的后续调度选择。

第二阶段针对第一阶段默认路径中的扫描关联重复计算。clean `492979e` 的 200 规模五个 seed 中，
D1 fusion 均值为 12.103 s。冻结 seed 42000 输入 SHA-256 为
`bc539686b130d96c63b76b9161fadbae2dba59de44cb61ac80d92f2ea1018406`，包含 86 个扫描、
2,051 条匿名观测，在线 truth 使用为 0。

非雷达扫描现在建立短生命周期关联工作区。每条观测只构造一次量测模型，每条航迹只取得一次共同
量测时刻状态。若多条观测的传感器位置、相机位置、旋转和内参完全相同，则它们可共享该航迹的
预测量测和数值雅可比。复用边界由量测函数的实际几何参数决定，不使用目标真值或本地身份。
每个候选对仍独立计算残差、创新协方差及归一化创新平方，随后参加原有 Hungarian 一对一分配。

current-default 与优化路径的候选对和创新求解均为 371,054 次；量测模型构造由 16,457 次降至
82 次，投影构造由 16,457 次降至 14,648 次。86 个逐扫描语义哈希、最终 201 条航迹和一致性
证据哈希相同，`GlobalTrack` 仍物化 16,653 次。纯融合墙钟为 `10.792 s -> 8.635 s`，本机
单次加速 1.25 倍。专项 10 项和 D1 全量 161 项均通过。

该结果证明冻结输入上的扫描内复用语义等价。优化后的 clean 五 seed 完整全栈尚未复跑，不能
据此声称 AirSim、200v200 完整系统或真实传感器链已经实时。

### 第一阶段增量后验基线

D1 已对冻结的 200v200 逐扫描输入完成等价性能治理。输入包含 86 个扫描和 2,051 条匿名观测。
函数剖析显示，主要成本不是扫描整理，而是相同历史前缀被 `_state_at()` 和 fixed-lag replay
重复计算，以及每条发布航迹重复生成同一扫描的传感器健康快照。

当前融合器为每条航迹维护按观测顺序排列的后验检查点。没有改变的历史前缀直接复用；迟到观测
插入后，从插入点开始重算；固定滞后锚点、起始观测或检查点前历史发生变化时清空相关缓存。
检查点同时保存归一化创新平方和门控结果，命中缓存时仍按当前 revision 重建一致性证据。
因此每个扫描的一对一关联、双时间戳、协方差、乱序量测处理和 observer-scan conflict 语义不变。

发布阶段把 association、latency 和 sensor-health 摘要提升为每扫描公共快照，再为每条
`GlobalTrack` 复制完整审计数据。状态和协方差数组也独立复制，调用方不能通过修改已发布对象
改变内部后验。冻结输入对照中，逐扫描输出、最终 201 条航迹和一致性证据哈希完全一致；滤波
更新由 93,234 次降至 1,797 次，健康快照由 16,653 次降至 86 次。未缓存参考为 34.701 s，
优化路径为 9.073 s，本机单次加速 3.82 倍。

该结果关闭 D1-owned 冻结输入热点，不证明 clean 多 seed 全栈实时性、AirSim 性能或融合精度。
正式 RMSE、归一化估计误差平方、归一化创新平方覆盖率仍需独立真值旁路和 D2 身份映射。

## 历史权威增量（2026-07-16）

D1 新增模块中立本地图像航迹适配边界。`LocalImageTrackObservation` 只有在状态为
`measured` 时才生成 `SensorObservation(modality="eo", frame_id="pixel")`；`lost` 不生成
任何观测，因而旧 center、bbox 或 covariance 不能作为新量测重入滤波。visible 和 infrared
均保持内部 EO 模态，波段写入 `metadata.spectral_band`。

适配器原样复制 measurement/arrival 双时间戳、2×2 pixel covariance、confidence 和质量
标志，并在 D1 边界再次检查形状、有限性、对称性与半正定性。sensor、stream、local epoch、
local track ID 和量测时刻形成确定性本地 observation ID 与可去重 source lineage。namespaced
`source_track_key` 只作为来源证据累积到 `GlobalTrack.metadata.source_track_ids`，不能成为或
覆盖 `global_track_id`。metadata 保留 bbox/center、backend/batch 等在线安全审计字段，但含
global/truth identity 的顶层或嵌套键直接拒绝。

2026-07-16 无随机 seed 的构造合同回归为专项 13 项和 D1 全量 111 项全部通过。该证据只证明
API 合同与融合元数据传播，不证明真实 AirSim 接线、相机标定、像素噪声标定或实时预算。

## 历史权威增量（2026-07-15）

真实 AirSim M5N2 已完成 baseline/candidate 各 10 case，共 20 case。在线控制链中的
identity/state truth use 均为 0，说明本轮没有以 AirSim actor/truth 身份或真值状态替代 D1
估计。20 case 共得到 3,805 个 main-bus tick，D1 fusion 阶段 mean/P95/max 为
`320.00/451.46/1234.88 ms`，是 main-bus 内层主导阶段。该结果证明当前首要工程问题是融合
路径实时性，而不是改变融合原则。

双时间戳、观测与航迹 covariance、NED 和 source lineage 仍是不可放宽的正确性合同。性能
优化只能减少重复传播、重复回放和非关键处理，不能丢弃有效观测、把 arrival time 当作
measurement time，或人为缩小 covariance。本批实验面向终端闭环和阶段时序，没有形成可用
NIS、NEES 或 RMSE 统计，因此不证明传感器噪声模型、滤波一致性或真实定位精度已经闭合。
TERM 前额外完成的 1 个 `png_ttc_2v2_seed001` 不进入 M5N2 统计，dropout 完成数为 0。

后文保留此前算法原理和历史验证；当前状态判断以上述边界为准。

`D1` 是第一研究模块编号，不是英文缩写。项目面向反无人机系统
（Counter-Unmanned Aircraft System，C-UAS）的多无人机协同仿真研究。本文只描述仓库当前
代码已经实现的能力及其严格边界，不把计划项、占位适配器或可选对照写成默认主线。

## 1. 模块定位、问题与边界

### 1.1 模块定位

D1 位于传感器观测与中心身份关联之间，负责把雷达、声学、光电（Electro-Optical，EO）和
可选合成激光雷达（Light Detection and Ranging，LiDAR）观测转换为统一时空语义，并估计
带完整协方差的六状态航迹。默认处理链为：

```text
SensorObservation[]（异构传感器观测数组）
  -> 坐标、时间、协方差和来源谱系检查
  -> 雷达初始化或既有航迹门控关联
  -> 轻量扩展卡尔曼滤波与迟到量测回放
  -> GlobalTrack[]（全局航迹数组）+ 质量/时延/健康摘要
  -> D2（第二研究模块）身份关联及其他下游模块
```

融合工作坐标系是北-东-地坐标系（North-East-Down，NED）。世界大地测量系统 1984
（World Geodetic System 1984，WGS84）只允许作为外部地理参考，进入 D1 前必须转换为 NED。
D1 不在内部维护经纬高航迹。

### 1.2 工程问题

D1 当前解决以下工程问题：

1. **异构量测统一**：把雷达极坐标、声学方位、EO 像素中心和可选 LiDAR 三维位置表示为
   统一的 `SensorObservation`（传感器观测）对象。
2. **异步到达处理**：同时保留 `measurement_timestamp`（物理量测时刻）和
   `arrival_timestamp`（融合节点到达时刻），按到达顺序接收、按量测时刻重放。
3. **不确定性贯通**：观测携带量测协方差，航迹携带 6×6 状态协方差；低置信度、遮挡、
   时间不确定性和长外推均留下可审计原因。
4. **轻依赖可复现**：默认算法使用 Python 数值计算库 NumPy，不依赖外部跟踪框架即可完成
   单元测试、合成仿真和持久化日志回放。
5. **在线真值隔离**：受治理回放默认递归清除目标真值、仿真参与实体（actor）名称和仿真
   对象（object）名称；真值仅可进入独立离线评分旁路。
6. **任意输入规模**：观测和航迹数量由输入数组决定；2v2、5v5 只是历史基线名称，不是算法
   上限或常量。

### 1.3 科学问题

模块研究的核心科学问题是：在传感器观测模型、时延、遮挡、异步采样和模型失配同时存在时，
如何得到数值稳定、时间一致且不虚假自信的状态估计。当前代码为以下问题提供了可重复研究
基线：

- 非线性异构量测能否通过统一状态空间进行递推融合；
- 迟到量测按量测时刻插入后，固定滞后回放能否优于把迟到量测当作当前量测；
- 距离、检测框大小、置信度和遮挡如何映射为量测协方差；
- 航迹协方差、二维 95% 误差半径、量测新鲜度和来源多样性如何形成可解释质量证据；
- 未知跨节点相关性存在时，如何用保守融合避免重复信息导致过度收敛；
- 在线数据不接触真值的前提下，如何保留可供离线均方根误差（Root Mean Square Error，
  RMSE）和一致性评估使用的独立证据。

### 1.4 明确边界

D1 **负责**：观测规范化、NED 状态估计、协方差传播、迟到量测回放、D1 内部临时航迹
生成、质量摘要、来源去重、回放治理，以及已由 D2 确认同一规范身份后的独立协同融合数值
助手。

D1 **不负责**：

- D2 的多目标规范身份、身份连续性和身份切换统计；
- D3（第三研究模块）的资源分配、计划版本、计划迟滞和过时版本拒绝；
- D4（第四研究模块）的中心、二级或分布式降级仲裁；
- D5（第五研究模块）的末端视觉身份锁定及本地视觉航迹管理；
- D7（第七研究模块）的比例导航或控制命令；
- main（全局编排器）的微软 AirSim 无人系统仿真器启动、重置、场景规模、实验回合
  （episode）顺序和报告汇总；
- 真实硬件驱动、真实通信认证、真实车辆控制或任何现实处置执行；所有决策只停留在科研仿真
  与离线评估，且不改变人工审核边界。

## 2. 上游输入与数据合同

### 2.1 上游来源

默认系统运行中，main runtime（全局运行编排层）从微软 AirSim 无人系统仿真器的 Blocks
场景取得仿真状态和
`simGetDetections`（仿真检测元数据接口）结果，再通过共享适配器构造 D1 观测。D1 包本身不
导入 AirSim 软件开发工具包（Software Development Kit，SDK），也不直接调用 AirSim
应用程序编程接口（Application Programming Interface，API）。

离线路径还可读取版本化 JavaScript 对象表示法（JavaScript Object Notation，JSON）逐行
记录（JSON Lines，JSONL）和逗号分隔值（Comma-Separated Values，CSV）记录。无版本的旧
Blocks JSONL 仍可兼容读取，但“可读取”不等于满足严格受治理回放合同。

### 2.2 `SensorObservation` 核心字段

| 字段 | 中文含义 | 当前规则 |
| --- | --- | --- |
| `observation_id` | 观测标识 | 受治理回放要求非空；冻结真实输入时改为不透明序号 |
| `sensor_id` | 传感器标识 | 用于健康统计和传感器特定时延预算 |
| `modality` | 传感器模态 | 当前支持 `radar`（雷达）、`acoustic`（声学）、`eo`（光电）、`lidar`（合成激光雷达） |
| `measurement_timestamp` | 物理量测时刻 | 状态更新和乱序重放的时间基准 |
| `arrival_timestamp` | 融合节点到达时刻 | 输入排序、发布时刻和时延审计基准 |
| `frame_id` | 量测坐标框架 | 雷达、声学、LiDAR 必须为 `ned`；EO 必须为 `pixel`（像素平面） |
| `measurement` | 量测向量 | 维度随模态变化 |
| `covariance` | 量测协方差 | 严格受治理回放必填；一般运行入口缺失时按模态生成默认值 |
| `classification_hint` | 通用类别提示 | 可累计为类别似然，但不能使用目标真值身份 |
| `confidence` | 观测置信度 | 截断到 0 至 1，并参与协方差放大 |
| `quality_flags` | 质量标志 | 如低质量、遮挡、部分遮挡和小检测框 |
| `metadata` | 扩展元数据 | 携带相机、覆盖区域、时钟不确定性、谱系和审计原因 |
| `timestamp_uncertainty_s` | 时间戳不确定性，单位秒 | 从秒/毫秒字段、时钟漂移、抖动和异常倒序时间中取保守最大值 |

通信扩展字段包括 `source_node_id`（源节点标识）、`target_node_id`（目标节点标识）、
`relay_node_id`（中继节点标识）、`link_type`（链路类型）、`sent_timestamp`（发送时刻）、
`received_timestamp`（接收时刻）、`payload_kind`（载荷类型）、`stale_after_s`（过期预算）和
`source_support`（来源支持计数）。这些字段用于审计、去重和下游质量解释，不在 D1 中形成
网络授权。

### 2.3 各模态量测

1. **雷达**：`measurement=[range, azimuth, elevation, radial_velocity]`，依次表示距离、
   方位角、俯仰角和径向速度。雷达可初始化新三维航迹。
2. **声学**：`measurement=[azimuth]`，只提供粗方位约束；当前没有到达时间差
   （Time Difference of Arrival，TDOA）阵列主定位。
3. **EO**：`measurement=[u,v]`，表示检测框中心的像素坐标；`bbox_xyxy`（左上和右下角
   组成的检测框）、相机内参和外参位于元数据。D1 不要求保存图像文件。
4. **LiDAR**：`measurement=[p_N,p_E,p_D]`，表示 NED 三维位置；当前仅为合成 dry-run
   （无真实仿真器依赖的试运行）可选输入，不代表真实设备或 AirSim LiDAR 插件已接入。

### 2.4 输入拒绝与规范化

- 模态未知或坐标框架不符合约定时，`SensorObservation` 构造直接失败。
- 严格受治理入口要求到达时刻不早于量测时刻、协方差维度与量测维度一致、元素有限、矩阵
  对称且半正定，并要求 `coverage_cell`（覆盖区域单元）和来源谱系存在。
- 一般 `FusionAdapter`（融合适配器）入口会把缺失、形状错误或非有限协方差替换为模态默认
  协方差，再执行对称化和对角上下界限制。该一般入口没有对每个输入矩阵执行完整特征值
  半正定投影；需要强保证的运行应使用受治理入口。
- 非雷达观测不能创建新三维航迹。没有可关联雷达航迹时，声学、EO 或 LiDAR 观测被记为
  `unsupported_track_initializer`（不支持的航迹初始化来源），不会伪造深度或位置。

## 3. 核心状态与下游输出

### 3.1 六状态 `GlobalTrack`

航迹状态定义为

\[
\mathbf{x}=
[p_N,p_E,p_D,v_N,v_E,v_D]^\mathsf{T},
\]

其中 \(p_N,p_E,p_D\) 分别是北、东、地向位置，\(v_N,v_E,v_D\) 是对应速度。输出
`GlobalTrack`（全局航迹）包含：

- `global_track_id`：D1 当前适配器生成的航迹标识；进入跨平台协同融合时只能保留 D2 已确认
  的中心规范标识，D1 不得自行重绑定；
- `state`：上述六状态向量；
- `covariance`：对应的 6×6 状态协方差；
- `timestamp`：状态有效时刻；
- `track_level`：质量等级；
- `source_support`：各模态累计支持次数；
- `identity_likelihood`：通用类别提示的归一化累计值，不是规范目标身份；
- `last_nis`：最近一次归一化创新平方；
- `metadata`：双时间戳、发布时刻、二维 95% 误差半径、协方差限制原因、时延审计和传感器
  健康快照等。

### 3.2 质量与审计输出

| 输出类型 | 用途 |
| --- | --- |
| `TrackUncertaintySummary` | 输出位置/速度协方差迹、二维 95% 半径、量测年龄、来源多样性、最近创新、交接准备度和限制原因 |
| `LatencyAuditSummary` | 输出观测数、回放数、乱序数、过期数、重复数、最大/平均时延和最大回放历史长度 |
| `SensorHealthSummary` | 输出每传感器轻量故障证据、状态、拒绝数、隔离建议、恢复阶段和预期时延统计 |
| `FusionQualityRegionSummary` | 按覆盖区域聚合航迹数量、质量等级、量测年龄、来源缺口和协方差增长 |
| `FusionQualityRegionWindowSummary` | 在固定时间窗内聚合区域质量趋势与时延/乱序证据 |
| `ReconCueSummary` | 从多条航迹产生供二级侦察相机使用的粗略 NED 指向摘要 |

这些摘要是证据，不是控制命令。D4 可以消费其风险字段，但降级决策必须由 D4 与系统规则
完成。

### 3.3 侦察粗指向摘要

`ReconCueSummary`（侦察提示摘要）是已实现辅助函数，不属于默认滤波更新。对第 \(i\) 条
有效航迹，以位置协方差迹的倒数作为权重：

\[
w_i=\frac{1}{\operatorname{tr}(\mathbf{P}_{i,p})},\qquad
\bar{w}_i=\frac{w_i}{\sum_j w_j},\qquad
\mathbf{c}=\sum_i\bar{w}_i\mathbf{p}_i.
\]

这里 \(\mathbf{P}_{i,p}\) 是三维位置协方差，\(\mathbf{p}_i\) 是航迹位置，\(\mathbf{c}\) 是
粗指向中心。摘要协方差同时包含各航迹自身协方差和航迹相对中心的离散项。缺失协方差时
使用每轴 \(10000\ \mathrm{m}^2\) 的保守默认值并记录计数；该提示不选择执行资源，也不改变
任何航迹身份。

## 4. 数学模型与主要公式

### 4.1 常速度状态模型

默认运动模型是常速度（Constant Velocity，CV）模型，默认滤波器是扩展卡尔曼滤波器
（Extended Kalman Filter，EKF）。时间步长为 \(\Delta t\) 时，状态转移为

\[
\mathbf{x}_{k|k-1}=\mathbf{F}(\Delta t)\mathbf{x}_{k-1|k-1},\qquad
\mathbf{F}=
\begin{bmatrix}
\mathbf{I}_3 & \Delta t\mathbf{I}_3\\
\mathbf{0}_3 & \mathbf{I}_3
\end{bmatrix}.
\]

代码使用白加速度谱密度 \(q\) 构造过程噪声：

\[
\mathbf{Q}=q
\begin{bmatrix}
\frac{\Delta t^4}{4}\mathbf{I}_3 & \frac{\Delta t^3}{2}\mathbf{I}_3\\
\frac{\Delta t^3}{2}\mathbf{I}_3 & \Delta t^2\mathbf{I}_3
\end{bmatrix},
\]

\[
\mathbf{P}_{k|k-1}=\mathbf{F}\mathbf{P}_{k-1|k-1}\mathbf{F}^{\mathsf T}+\mathbf{Q}.
\]

其中 \(\mathbf{P}\) 是状态协方差，\(q\) 控制未建模加速度引起的不确定性增长。该模型计算
量小、解释直接，适合作为可复现默认基线；代价是高机动转弯和加减速只能由较大的过程噪声
吸收，不能显式表达机动模式。

### 4.2 EKF 量测更新

对非线性量测函数 \(\mathbf{z}=h(\mathbf{x})+\mathbf{v}\)，量测噪声协方差为
\(\mathbf{R}\)，代码用中心差分数值雅可比得到 \(\mathbf{H}\)，并计算：

\[
\mathbf{y}=\mathbf{z}-h(\mathbf{x}^{-}),\qquad
\mathbf{S}=\mathbf{H}\mathbf{P}^{-}\mathbf{H}^{\mathsf T}+\mathbf{R},
\]

\[
\mathbf{K}=\mathbf{P}^{-}\mathbf{H}^{\mathsf T}\mathbf{S}^{-1},\qquad
\mathbf{x}^{+}=\mathbf{x}^{-}+\mathbf{K}\mathbf{y}.
\]

角度分量的残差会归一化到 \([-\pi,\pi)\)。协方差采用数值更稳健的 Joseph 形式：

\[
\mathbf{P}^{+}=(\mathbf{I}-\mathbf{K}\mathbf{H})\mathbf{P}^{-}
(\mathbf{I}-\mathbf{K}\mathbf{H})^{\mathsf T}
+\mathbf{K}\mathbf{R}\mathbf{K}^{\mathsf T}.
\]

归一化创新平方（Normalized Innovation Squared，NIS）为

\[
\epsilon=\mathbf{y}^{\mathsf T}\mathbf{S}^{-1}\mathbf{y}.
\]

它用于关联评分、航迹质量通过率和离线一致性诊断。矩阵求解失败时，代码使用 Moore-Penrose
广义逆作为数值回退。

### 4.3 雷达模型

设传感器位置为 \(\mathbf{s}\)，目标相对位置 \(\mathbf{r}=\mathbf{p}-\mathbf{s}\)，距离
\(\rho=\|\mathbf{r}\|\)，水平距离 \(r_h=\sqrt{r_N^2+r_E^2}\)，单位视线向量
\(\mathbf{u}=\mathbf{r}/\rho\)。雷达预测量测为

\[
h_r(\mathbf{x})=
\begin{bmatrix}
\rho\\
\operatorname{atan2}(r_E,r_N)\\
\operatorname{atan2}(-r_D,r_h)\\
\mathbf{v}^{\mathsf T}\mathbf{u}
\end{bmatrix}.
\]

四项分别是距离、方位角、仰角和径向速度。若上游没有提供协方差，距离 \(d\) 经过最小距离
截断后，各标准差按当前参数线性增长，例如

\[
\sigma_\rho=2.0+0.012d,\qquad
\sigma_{v_r}=0.35+0.0015d,
\]

角度标准差也按距离线性增长后由度转换为弧度。该模型是仿真基线，不是某一真实雷达型号的
标定曲线。

雷达初始化先把极坐标变换为 NED 位置，并把径向速度投到视线方向。切向速度初始不确定性
保持较大，因此单次雷达观测不会被解释为完整三维速度真值。

### 4.4 声学模型

声学量测只约束水平面方位：

\[
h_a(\mathbf{x})=\operatorname{atan2}(r_E,r_N).
\]

置信度 \(c\in[0,1]\) 对应的默认角度标准差为

\[
\sigma_a=\left(2.5+8(1-c)\right)\ \text{度}.
\]

因此声学输入只能收窄方向不确定性，不单独创建距离或高度。选择该弱约束是为了避免在没有
阵列几何、风噪和混响模型时制造虚假三维定位精度。

### 4.5 EO 针孔投影模型

设相机中心为 \(\mathbf{c}\)，从 NED 到相机坐标的旋转矩阵为 \(\mathbf{R}_{cw}\)，则

\[
\begin{bmatrix}X_c&Y_c&Z_c\end{bmatrix}^{\mathsf T}
=\mathbf{R}_{cw}(\mathbf{p}-\mathbf{c}),
\]

\[
u=f_x\frac{X_c}{Z_c}+c_x,\qquad
v=f_y\frac{Y_c}{Z_c}+c_y.
\]

其中 \(f_x,f_y\) 是像素焦距，\(c_x,c_y\) 是主点。目标在相机后方或深度过小时，代码将
分母限制为一个很小正数以避免数值除零；这只是数值保护，不代表后方目标是有效检测。

默认像素标准差随置信度降低而增大，并受检测框尺寸影响；`occluded`（遮挡）和
`small_bbox`（小检测框）进一步放大不确定性。当前没有镜头畸变、滚动快门或在线外参漂移
估计。

### 4.6 LiDAR 三维位置模型

合成 LiDAR 使用线性位置观测

\[
h_l(\mathbf{x})=\mathbf{p}.
\]

默认水平和垂直标准差随距离增加并除以置信度。该路径用于可选 dry-run 和接口回归，不属于
当前 AirSim 主线的必备传感器。

## 5. 默认算法步骤与选型理由

### 5.1 单观测处理步骤

`FusionAdapter.process()`（融合适配器单观测处理）按以下顺序执行：

1. **观测准备**：补全或限制量测协方差，记录时间戳不确定性、低质量放大原因和异常原因。
2. **推进融合时钟**：`current_time`（当前融合时刻）取历史当前时刻与本观测到达时刻的较大值。
3. **时延审计**：若量测时刻早于处理该观测之前的融合时刻，则计为乱序量测
   （Out-of-Sequence Measurement，OOSM）；再按过期预算判断 stale（过期）。
4. **全航迹预测**：所有航迹先预测到当前到达时刻。
5. **来源去重**：相同显式谱系、消息序号或源载荷指纹只处理一次，中继重发不重复收敛。
6. **关联**：在观测量测时刻重建候选航迹状态，选择评分最小且不超过门限的航迹。
7. **初始化或更新**：无匹配时只有雷达可以初始化；有匹配时把观测插入按量测时刻排序的历史。
8. **固定滞后回放**：从最早雷达初始状态依次预测、更新到每个历史量测时刻，最后传播到当前
   到达时刻。
9. **限制与发布**：限制 6×6 航迹协方差，更新质量等级、元数据、时延和健康摘要后输出当前
   全部航迹。

这里的“固定滞后”由默认 `buffer_horizon=6.0 s`（回放历史窗口）控制非初始观测保留。关闭
`latency_compensation`（时延补偿）时，代码把量测时刻替换为到达时刻，作为消融对照。

### 5.2 关联门控

雷达关联使用三维位置差的马氏距离：

\[
d_r^2=(\mathbf{p}_z-\mathbf{p}_t)^{\mathsf T}
(\mathbf{P}_{z,p}+\mathbf{P}_{t,p})^{-1}
(\mathbf{p}_z-\mathbf{p}_t).
\]

其他模态使用 NIS 形式的创新距离。所有候选中最小评分不大于 `association_gate`（关联门限）
时才接受。D1 类默认门限为 40.0；2026-07-13 的 main AirSim 实验回合总线（episode bus）
明确覆盖为 4.0。
这两个数不能混写。当前门限是共享工程参数，并非按各量测维度分别查卡方分布表所得的统计
门限，这是后续真实数据标定需要处理的局限。

`use_truth_hints_for_association`（是否用真值提示关联）类参数存在，但默认值为 `False`，当前
main runtime 也明确设为 `False`。受治理在线回放还会清除相关真值字段，因此默认在线主线不
依赖 AirSim actor/object 名称或真值身份。

### 5.3 默认参数与 main runtime 覆盖

| 参数 | D1 类默认值 | 2026-07-13 main episode bus 值 | 含义 |
| --- | ---: | ---: | --- |
| `process_noise` | 6.0 | 4.0 | 过程噪声谱密度 |
| `bucket_size` | 0.1 s | 0.1 s（未覆盖） | 质量摘要时间桶 |
| `buffer_horizon` | 6.0 s | 6.0 s（未覆盖） | 非初始观测回放保留窗口 |
| `stable_threshold_m` | 30 m | 35 m | 稳定级二维 95% 半径门限 |
| `handover_threshold_m` | 12 m | 14 m | 可交接级二维 95% 半径门限 |
| `association_gate` | 40.0 | 4.0 | 关联评分门限 |
| `long_extrapolation_s` | 3.0 s | 3.0 s（未覆盖） | 长外推原因触发时长 |
| `sensor_isolation_reject_threshold` | 3 | 3（未覆盖） | 健康摘要隔离建议计数门限 |

选择轻量 NumPy EKF 作为默认主线的理由是：当前观测维度低、代码可审计、依赖少、迟到量测
回放易控制，且已有完整单元回归。当前证据不足以证明更复杂模型能在真实多种子场景中稳定
改善误差和一致性，因此不能提前替换默认路径。

## 6. 状态、门控、迟滞、协方差与身份安全

### 6.1 航迹质量状态

`TrackLevel`（航迹质量等级）声明了 `coarse`（粗略）、`stable`（稳定）、`handover`
（可交接）和 `lost`（丢失）四个枚举。当前默认分类函数实际只返回前三种：

- **handover**：二维 95% 误差半径不大于交接门限，至少两种传感器模态，累计命中不少于
  8，最近创新门限通过率不少于 0.55；
- **stable**：二维 95% 误差半径不大于稳定门限，累计命中不少于 3，最近创新门限通过率
  不少于 0.45；
- **coarse**：不满足以上条件；
- **lost**：枚举已声明，但当前分类路径不会进入，也没有默认航迹删除状态机。

二维 95% 误差半径按水平位置协方差最大特征值计算：

\[
a_{95}=\sqrt{\chi^2_{2,0.95}\lambda_{\max}(\mathbf{P}_{NE})},
\qquad \chi^2_{2,0.95}\approx5.9915.
\]

其中 \(\mathbf{P}_{NE}\) 是北-东二维位置协方差。

### 6.2 迟滞的严格归属

D1 当前**没有航迹质量等级迟滞**：每次发布都根据当前协方差、命中数和创新通过率重新计算
等级，没有进入门限与退出门限之分。D3 的分配迟滞、D4 的风险窗口和 D5 的末端锁定迟滞均
属于其他模块，不能写成 D1 已实现能力。

D1 的传感器健康中有 `nominal_after_fault_count`（故障后连续正常计数），用于输出
`recovering`（恢复中）证据；但故障原因计数当前不会自动清空，所以这不是完整的带迟滞故障
恢复状态机。

### 6.3 交接准备度

`handover_readiness`（交接准备度）取以下五项得分的最小值并截断到 0 至 1：协方差、量测
新鲜度、来源多样性、最近创新和当前质量等级。该设计是保守的“短板”汇总：任一关键证据差
都会降低准备度。它只是质量指标，不会自行触发 D5 或 D7。

### 6.4 观测协方差治理

量测协方差在进入 EKF 前执行：默认值补全、形状/非有限值重置、对称化、质量放大、对角
上下界和相关项限幅。默认对角下界为：

- 雷达：\([10^{-2},10^{-8},10^{-8},10^{-4}]\)；
- 声学：\([10^{-8}]\)；
- EO：\([0.25,0.25]\)；
- LiDAR：\([10^{-2},10^{-2},10^{-2}]\)。

各量测维度默认上界均为 \(10^6\)。置信度低于 0.5 时，公共质量放大因子至少为
\(0.5/\max(c,0.05)\)；遮挡至少放大协方差 2 倍，其他低质量标志至少放大 1.5 倍，总因子
上限为 4。EO 默认协方差模型本身还会根据遮挡放大像素标准差，因此应通过输出原因审计实际
组合效果，不能只看单个倍数。

### 6.5 航迹协方差治理

六状态协方差默认对角下界为

\[
[0.25,0.25,0.25,0.04,0.04,0.04],
\]

默认上界为

\[
[10^6,10^6,10^6,10^4,10^4,10^4].
\]

代码同时对称化矩阵，并把相关项限制在对应标准差乘积的 0.999 倍以内。形状错误或非有限的
航迹协方差重置为上界对角阵。原因通过 `covariance_limit_reasons`（协方差限制原因）保留，
包括观测/航迹下界、上界、无效重置、长外推、低质量和遮挡等。限制器避免明显数值爆炸或
虚假零方差，但不能替代真实传感器统计一致性标定。

### 6.6 轻量故障检测、隔离与恢复

D1 实现轻量故障检测、隔离与恢复（Fault Detection, Isolation and Recovery，FDIR-light）
证据汇总。每个传感器累计重复、拒绝、OOSM、过期、低质量、异常协方差和时间戳不确定性
计数。

`SensorTimingExpectation`（传感器时延期望）可配置期望时延、容差和“固定延迟 OOSM 是否
属于正常”。因此原始 OOSM 计数与 `unexpected_oosm_count`（非预期乱序计数）严格分开。
状态判定为：

- 拒绝数达到 3、异常协方差数达到 3，或“过期数 + 非预期 OOSM 数”达到 3：
  `isolated`（建议隔离）；
- 存在任何累计故障原因但未达上述门限：`degraded`（退化）；
- 没有故障原因：`nominal`（正常）。

关键边界是：`isolated` 只是摘要状态和 `isolation_hint`（隔离建议），`FusionAdapter` 当前
不会据此停用该传感器，D1 也不会发出 D4 降级动作。固定 0.2 s 多传感器延迟曾产生很高的
原始 OOSM 比例，这不等于传感器故障。

### 6.7 身份和来源安全

1. D1 普通融合的 `global_track_id` 是内部航迹标识；D2 负责中心规范身份和连续性。
2. D1 不允许 EO 本地检测标识、仿真 actor 名称或 truth 标识重写规范身份。
3. 跨平台协同数据必须全部携带同一个由 D2 确认的 `global_track_id`；混合身份直接拒绝。
4. `source_lineage_key`（来源谱系键）结合源节点、传感器、模态、载荷类型、序号和载荷指纹
   去重；显式谱系优先。
5. 协同路径按通用唯一标识符（Universally Unique Identifier，UUID）消息标识和完整来源谱系
   双重去重，中继重发不能重复增加信息。
6. 受治理 writer（写出器）默认递归剥离真值、actor、object 和离线专用字段；离线真值只在
   显式 `offline_truth`（离线真值）旁路或 evaluator-only（仅评估器使用）sidecar（旁路文件）
   中保存。

## 7. 已实现但不在默认主线的算法

### 7.1 中心化多观察者方位定位

D1 已实现独立的 2..N 观察者方位射线定位助手。它使用加权最小二乘
（Weighted Least Squares，WLS），但**不会被 `FusionAdapter.process()` 自动调用**。
输入必须先由 D2 确认属于同一规范身份。

对第 \(i\) 条视线，原点为 \(\mathbf{o}_i\)，单位方向为 \(\mathbf{u}_i\)，垂直投影矩阵为

\[
\mathbf{A}_i=\mathbf{I}-\mathbf{u}_i\mathbf{u}_i^{\mathsf T}.
\]

无权初值求解

\[
\left(\sum_i\mathbf{A}_i\right)\mathbf{p}
=\sum_i\mathbf{A}_i\mathbf{o}_i.
\]

随后把方位协方差、平台位姿协方差、传感器外参协方差、传播过程噪声和时间戳不确定性投影
到视线切平面，迭代构造信息矩阵并求 WLS 位置。异步观测传播到共同估计时刻；如果需要传播
却没有目标速度，则保守拒绝。

默认门控包括：至少 2 个唯一观察者、基线至少 2 m、至少一对视线交会角不小于 2 度、量测
时差不大于 0.5 s、信息矩阵满秩、条件数不大于 \(10^8\)、最大角残差不大于 5 度、最大垂直
残差不大于 100 m、加权残差均方根不大于 6。视线（Line of Sight，LOS）近共线、解在观察者
背后、协方差不完整或无效等情况均返回明确拒绝原因。

默认 `incomplete_covariance_policy="reject"`（协方差不完整即拒绝）；可选 `inflate`
（保守补全并膨胀）只适用于研究对照。

### 7.2 协方差交集

对已确认同一规范身份、但交叉相关性未知的多个状态估计，D1 提供协方差交集
（Covariance Intersection，CI）助手。两估计形式为

\[
\mathbf{P}_{CI}^{-1}=\omega\mathbf{P}_1^{-1}+(1-\omega)\mathbf{P}_2^{-1},
\]

\[
\mathbf{x}_{CI}=\mathbf{P}_{CI}
\left[\omega\mathbf{P}_1^{-1}\mathbf{x}_1
+(1-\omega)\mathbf{P}_2^{-1}\mathbf{x}_2\right].
\]

权重 \(\omega\in[0,1]\) 在默认 101 点网格上搜索，使输出协方差的对数行列式最小。所有输入
先用 CV 模型传播到共同时间，并把时间戳不确定性沿速度方向加入位置协方差。该实现按顺序做
成对 CI，保持输入规范身份和双时间戳，不处理部分共享谱系的精细相关图。

### 7.3 合成长回放与真实 AirSim 输入冻结

- `long_replay.py`（合成长回放模块）可生成 crossing（交叉）、遮挡、延迟、显式 OOSM 和
  中继重复的确定性科研场景，并输出质量摘要；它不是实测传感器数据。
- `airsim_replay_freeze.py`（AirSim 持久化输入冻结模块）把 main 已保存的 JSON/JSONL 转为
  受治理 manifest（清单）、在线 records（记录）、仅评估真值旁路和诊断摘要；它不连接
  AirSim SDK，也不补造缺失量测。
- `ReplayProvenance`（回放来源证明）保存场景/配置标识、版本、摘要、运行标识、随机种子和
  证据路径。捕获声明冲突、4 m/2 m 间距声明冲突或真值旁路同键位置冲突时均 fail closed
  （保守拒绝）。

### 7.4 隔离滤波基准

D1 已实现只读取冻结回放的 P2（后续可选优先级）隔离基准运行器。它真正执行的只有当前
NumPy EKF/固定滞后路径；第三方后端不可执行时必须输出 `unavailable`（不可用）及原因，
不能静默回退后声称完成第三方对照。

## 8. 默认、可选与未实现能力矩阵

| 能力 | 状态 | 是否进入默认在线主线 | 严格说明 |
| --- | --- | --- | --- |
| NumPy CV/EKF | 已实现 | 是 | 当前 D1 默认滤波主线 |
| 双时间戳与固定滞后 OOSM 回放 | 已实现 | 是 | 默认启用，可关闭做消融 |
| 雷达/声学/EO 观测更新 | 已实现 | 是 | 只有雷达可初始化 |
| 合成 LiDAR | 已实现 | 可选 | dry-run 输入，不代表真实接入 |
| FDIR-light 证据 | 已实现 | 是 | 只建议，不实际隔离传感器 |
| 区域/窗口质量摘要 | 已实现 | 按需发布 | 阈值尚未完成真实长期标定 |
| 侦察粗指向摘要 | 已实现 | 辅助调用 | 不参与默认 EKF 更新 |
| 多观察者方位 WLS | 已实现数值助手 | 否 | 需 D2 先确认规范身份 |
| CI 航迹融合 | 已实现数值助手 | 否 | 未接真实多节点 runtime |
| 受治理 JSONL/CSV 回放 | 已实现 | main 已消费 | 旧日志兼容路径不等价于严格合同 |
| 无迹卡尔曼滤波器（Unscented Kalman Filter，UKF） | 未实现 | 否 | 只有计划项 |
| 交互多模型（Interacting Multiple Model，IMM） | 未实现 | 否 | 常加速度（Constant Acceleration，CA）和协调转弯（Coordinated Turn，CT）模型集也未接入 |
| Python 滤波库 FilterPy | 占位/可用性探测 | 否 | 没有可执行适配器 |
| 英国国防科学技术实验室 Stone Soup 跟踪融合框架 | 占位 | 否 | 没有真实跟踪器/融合器后端 |
| 开源计算机视觉库（Open Source Computer Vision Library，OpenCV）标定/投影对照 | 未实现 | 否 | 没有畸变、标定或位姿求解对照 |
| 机器人操作系统第二版（Robot Operating System 2，ROS 2）坐标树与时间同步 | 未实现 | 否 | `tf2`（坐标变换库）和 `message_filters`（消息同步库）仅为计划 |
| 佐治亚理工学院平滑与建图库（Georgia Tech Smoothing and Mapping，GTSAM）几何后端 | 未接入 | 否 | 仅为可选研究候选 |
| D1 直连 AirSim runtime | 未实现且非当前职责 | 否 | main/shared runtime 负责连接 |
| 声学 TDOA 主定位 | 未实现 | 否 | 当前声学只作粗方位 |
| 完整航迹丢失/删除状态机 | 未实现 | 否 | `lost` 仅为枚举声明 |

## 9. 与其他模块和 main runtime 的接口关系

### 9.1 main runtime

main 决定 `--drone-count N`（无人机/目标规模参数）、AirSim settings（仿真设置）、actor target
（移动目标实体）、相机名、reset（重置）和 episode 顺序。`observations_from_blocks_frame()`
（Blocks 帧到观测适配函数）生成 D1 输入，main 再依到达时刻顺序调用融合适配器。

当前 episode bus 以 `use_truth_hints_for_association=False` 运行 D1，并在每个 tick（时钟步）
发布观测数、航迹数、航迹标识、`TrackUncertaintySummary[]` 和观测摘要；episode 结束时额外
写入时延审计和区域质量事件。main 还使用受治理 serializer（序列化器）把在线观测与离线
真值标签分离写盘。

### 9.2 D2 数据关联

D1 的位置和水平协方差通过集成适配器转换为 D2 detection（检测输入）。当前 D2 默认关联器
是全局最近邻（Global Nearest Neighbour，GNN）加匈牙利分配。D2 负责建立和维护中心规范
`global_track_id`、身份连续性和身份切换计数。

历史集成仿真适配器仍包含读取 D1 `truth_id`（真值标识）的兼容逻辑，但当前 main runtime
明确关闭 D1 真值提示，受治理回放也清除在线真值。该历史兼容代码不能作为在线身份合同。

协同 WLS/CI 路径的边界更严格：只有 D2 已确认同一规范身份后，D1 才能融合数值状态；关联
不唯一时必须保持不融合。

### 9.3 D3 分配规划

D3 消费 D2 的中心航迹，而不是直接让 D1 生成分配。D1 只提供状态、协方差、时间和质量；
D3 负责威胁/资源成本、分配迟滞、计划版本和过时版本拒绝。D1 不能创建或更新
`AssignmentPlan`（分配计划）。

### 9.4 D4 分布式降级

D4 可消费 D1 的位置不确定性、协方差迹、量测年龄、来源缺口、区域窗口和传感器健康证据，
并与 D2 关联风险、D3 计划有效性和通信状态共同仲裁。D1 的 `isolation_hint`、高协方差或高
OOSM 不能单独等价为主动降级命令。

### 9.5 D5 末端关联

D5 使用中心 `global_track_id`、三维状态、协方差和相机模型投影已有全局航迹，再与本地视觉
检测匹配。D1 可提供 EO 元数据和粗指向提示，但 D5 负责末端锁定状态、跨视角一致性和本地
检测标识；D5 不得回写或重绑定中心身份。

### 9.6 第六研究模块（D6）评估

D6 消费受治理回放、证据路径、可用性状态、时延、健康、区域窗口、RMSE、NIS 和归一化估计
误差平方（Normalized Estimation Error Squared，NEES）等离线指标。没有 D2 规范身份映射或
真值样本时，相关指标必须标为 `unavailable`，不能补零或用最近邻真值伪造标签。

### 9.7 D7 导引

D7 当前默认使用位置比例导航（Proportional Navigation，PN）和视觉比例导航制导
（Proportional Navigation Guidance，PNG）的门控合同。D1 只提供中段状态、协方差和质量
证据，不计算 D7 导引律，不决定模式切换，也不直接下发控制。

## 10. 2026-07-13 验证结果

### 10.1 D1 当前回归

2026-07-13 收敛报告记录 D1 全量测试为 **79 passed**。环境变量 `PYTHONPATH`（Python 模块
搜索路径）对应的既有测试命令是：

```bash
PYTHONPATH=research_modules/d1_sensor_fusion/src pytest -q research_modules/d1_sensor_fusion/tests
```

本文只新增原理文档，不改变能力状态，因此本次文档验收不要求重新执行全量代码测试。

### 10.2 严格 Dense Crossing 输入证据

当前真实 AirSim 证据为：

- AirSim 的计算机视觉模式（ComputerVision mode）；
- 5 个目标；
- nominal（常规）相邻间距严格 4 m，tight（紧密）相邻间距严格 2 m；
- 每组 20 个随机种子，共 40 个真实 AirSim episode；
- 每个 episode 51 帧，默认不保存截图；
- evaluator-only truth sidecar 共 10,200 个样本；
- `online_truth_leak_count=0`，即在线真值泄漏计数为 0；
- D1 受治理回放保留双时间戳、协方差、NED、来源谱系、场景/配置版本、随机种子、目标间距和
  证据路径；
- D6 将 `d1_dense_crossing`（D1 密集交叉证据源）标为 `available`（可用）。

这组证据关闭的是 D1 持久化输入冻结、捕获来源证明、真值旁路隔离和 D6 可消费性缺口。它
不等于真实雷达、声学或 EO 误差模型已经标定，也不直接证明 D1 的多目标身份性能；身份切换
和连续性结果属于 D2。

### 10.3 已解决问题

截至当前日期，D1 已解决或保持关闭的关键问题包括：

1. 双时间戳、NED 六状态和观测/航迹协方差合同；
2. 固定滞后 OOSM 回放及延迟补偿消融入口；
3. 雷达、声学、EO 和可选合成 LiDAR 观测模型；
4. FDIR-light、协方差上下界原因和时间戳不确定性输出；
5. 观测来源谱系去重和中继重复抑制；
6. 区域质量、时间窗口、时延审计、传感器健康和侦察粗指向摘要；
7. 严格受治理回放 schema（结构版本）、场景/配置来源证明和在线真值清除；
8. 真实持久化 AirSim 输入冻结、缺失量测不补造、真值旁路同键冲突保守拒绝；
9. 2..N 方位 WLS 与 CI 的独立数值基础及其身份/几何/协方差门控；
10. 任意输入数组长度处理，未把 2v2 或 5v5 写成算法常量。

### 10.4 较早的隔离合成基准

隔离 P2 小型冻结样本上，当前 NumPy 路径曾得到位置 RMSE 约 0.2335 m、平均 NIS 约
0.0426、平均 NEES 约 0.0651，主机相关耗时约 6.9 至 10.1 ms。该样本只有六条雷达观测，
低 NIS/NEES 反而提示协方差偏保守；它只证明评分链能运行，不能作为真实传感器精度或实时性
结论。FilterPy 和 Stone Soup 当时均未执行。

## 11. 剩余局限与开放问题

### 11.1 当前优先级一问题

P1 表示当前能力增强和真实标定优先级，不代表已经实现：

1. **真实传感器挑战回放不足**：现有严格 4 m/2 m 数据主要验证几何声明、冻结和身份评分
   输入，尚未形成覆盖雷达/声学/EO 漏检、匿名虚警、部分/完全遮挡、异步采样、传感器特定
   时延、时钟异常和节点退出的长时多种子数据集。
2. **阈值尚未冻结**：区域协方差增长、量测新鲜度、交接准备度、NIS/NEES、期望时延、健康
   误报/漏报和动态协方差放大原因仍需正常/故障对照标定。
3. **协同路径尚未接入真实运行时**：WLS/CI 助手已实现，但 D1/D2 规范身份适配、部分共享
   谱系、真实多节点回放和 3->2->1 节点退出质量退化仍未闭合。
4. **单模型限制**：默认仍是 CV/EKF；高机动目标缺少 CV/CA/CT 多模型对照和场景自适应
   协方差规则。
5. **长期 D6 一致性**：跨场景、跨随机种子和长时回放中的可用性（availability）、证据路径、
   健康、区域窗口和一致性指标还需持续验证。
6. **普通入口数值治理有限**：受治理回放严格验证协方差半正定；一般运行协方差限制器主要做
   形状、有限性、对称性、对角和成对相关限幅，尚无统一特征值投影与统计一致性保证。
7. **航迹生命周期不完整**：没有默认 `lost` 状态进入、超时删除、合并/拆分或带迟滞质量状态
   机；长期目标消失时需要由后续实现或上层生命周期治理处理。

### 11.2 可选后续，不是当前主线

P2 表示隔离对照或后置工程适配：UKF、IMM、FilterPy、Stone Soup、OpenCV、GTSAM、ROS 2
和 D1 直连 AirSim 均不属于当前默认能力。只有在依赖环境、冻结输入、验收指标和收益门槛明确
后，才应实现可执行对照；收益不足时继续保持 NumPy CV/EKF 主线。

## 12. 中文术语表

| 术语 | 含义 |
| --- | --- |
| C-UAS | 反无人机系统，用于本项目科研仿真的任务领域 |
| NED | 北-东-地坐标系，D1 的统一状态工作空间 |
| WGS84 | 世界大地测量系统 1984，仅作为外部地理参考 |
| EO | 光电传感器；当前 D1 使用像素中心、检测框和相机参数 |
| LiDAR | 激光雷达；当前仅有合成三维位置观测路径 |
| CV | 常速度运动模型，不要与 AirSim 的 ComputerVision 模式混淆 |
| EKF | 扩展卡尔曼滤波器，当前默认非线性递推估计器 |
| UKF | 无迹卡尔曼滤波器，当前未实现 |
| IMM | 交互多模型，当前未实现 |
| CA | 常加速度模型，当前未接入默认滤波器 |
| CT | 协调转弯模型，当前未接入默认滤波器 |
| OOSM | 乱序量测，指量测时刻早于融合已处理时刻的迟到观测 |
| NIS | 归一化创新平方，用于创新一致性、关联和质量诊断 |
| NEES | 归一化估计误差平方，需要离线真值评估状态一致性 |
| RMSE | 均方根误差，需要正确身份映射和离线真值 |
| FDIR-light | 轻量故障检测、隔离与恢复证据；不执行真实传感器隔离 |
| WLS | 加权最小二乘，用于已确认同一身份的多视线定位助手 |
| CI | 协方差交集，用于未知交叉相关性的保守状态融合 |
| LOS | 视线，指观察者到目标的方位射线方向 |
| `measurement_timestamp` | 物理量测时刻，决定状态更新所在时间 |
| `arrival_timestamp` | 到达融合节点的时刻，决定输入顺序和时延审计 |
| `timestamp_uncertainty_s` | 时间戳不确定性，单位秒 |
| `covariance` | 协方差，描述量测或状态误差及其相关性 |
| `GlobalTrack` | D1 输出的 NED 六状态航迹及 6×6 协方差 |
| `global_track_id` | 航迹标识；跨模块规范身份由中心/D2 维护，D1 不重绑定 |
| `source_lineage` | 来源谱系，用于识别同一源载荷及其中继重复 |
| `coverage_cell` | 覆盖区域单元，用于区域质量聚合 |
| `a95_m` | 水平面二维 95% 置信椭圆的保守长半轴，单位米 |
| `handover_readiness` | 交接准备度；是质量证据，不是交接命令 |
| governed replay | 受治理回放；强制时间、协方差、坐标、来源证明和真值隔离合同 |
| sidecar | 与在线记录分离的旁路文件；本项目用于仅离线评分的真值证据 |
| fail closed | 条件不完整或冲突时保守拒绝，不猜测、不补造 |

## 13. 状态结论

截至 2026-07-13，D1 没有运行级 P0（阻断级优先级）问题。默认主线仍是
`SensorObservation[] -> NumPy CV/EKF + fixed-lag OOSM replay -> GlobalTrack[]`，并附带
协方差、双时间戳、来源谱系和质量治理证据。严格 4 m/2 m、40 个真实 AirSim episode 证明
了输入冻结、来源证明、在线真值隔离和下游可消费性，但没有关闭真实传感器长期误差标定、
协同运行时接线、多模型滤波或动态阈值治理。所有 P1/P2 项必须继续按“已实现数值助手、可选
离线对照、未实现运行能力”三类明确表述。

## 14. 2026-07-14 在线身份真值隔离补充原则

仿真器中的 scene truth 有两个不同用途，必须物理区分：

1. **量测生成允许使用**：scene state 可用于投影、加噪、漏检/遮挡事件生成和离线评分标签。
2. **在线算法禁止使用**：量测生成后，actor/object/truth/segmentation 身份、目标名字、带目标
   token 的 classification/lineage 和原始 observation ID 不得进入 D1/D2 在线路径。

D1 已提供 `anonymize_online_observations()` 和
`assert_online_observations_identity_free()`。前者返回匿名副本、递归清理身份并重写帧内不透明
ID/lineage；后者在残留身份键或已知 token 时 fail closed。measurement、covariance、双时间
戳、sensor/camera geometry 保持不变。dry-run 和 evaluator-only truth sidecar 不经过破坏性
修改，离线评分仍使用与在线记录分离的原始标签。

2026-07-14 验证使用两组各 2 条、仅身份名字不同且几何完全相同的 EO scene observations。
接受阈值为匿名结果全字段严格相等、几何逐元素不变、在线泄漏为 0、注入泄漏 100% 拒绝；
专项 `4 passed`，D1 全量 `83 passed`。该结果关闭 D1-owned P0 API 缺口，但 main/runtime 仍须
在每个 scene-state 在线入口实际调用该边界，并提供没有出现在身份键下的额外 identity token。
真实传感器长期标定、协同运行时、持续阈值和 D6 长期一致性仍是 P1。

## 15. 扫描唯一性与固定滞后检查点原则（2026-07-14）

同一物理观测者在一次扫描内产生的多条候选量测不能重复更新同一航迹，否则会形成虚假信息
增益；但雷达、声学和光电是不同 modality，即使 scan 序号相同也必须允许合法跨模态融合。
雷达严格门限外的重捕仅允许“近期、成熟、唯一候选”，多候选时保守抑制新 birth。

固定滞后检查点不能任意放在两个量测之间。本模块的常速度过程噪声按一个预测区间离散，任意
拆分区间会改变协方差和后续扩展卡尔曼滤波增益。检查点因此对齐到滞后边界之前最近的已接受
量测后验；更早的合法乱序量测从原始锚点和历史 archive 重放。该语义保持双时间戳、NED、
协方差和 source lineage，不使用在线 truth。

2026-07-14 回归结果为 D1 `87/87`、main 报告 AirSim runtime `134/134`。修复后同一真实
AirSim seed 尚未复跑，因此历史 episode 的第三航迹和状态跳变只能记为“根因已定位、代码回归
已通过”，不能记为真实场景缺口已关闭。

## 16. Covariance 必须先合法再治理（2026-07-14）

正式在线、versioned governed replay 和 AirSim freeze 的 observation covariance 是硬输入，
不是可选质量提示。radar/legacy acoustic/`acoustic_3d`/EO/lidar 必须分别提供
`4x4/1x1/2x2/2x2/3x3` 的有限、对称、
半正定矩阵；缺失或非法时在滤波更新前 fail closed。质量缩放与 floor/ceiling 只能治理已通过
合同的合法矩阵，不能用于修复来源不明的缺值或坏值。

历史缺值仅允许显式 offline migration，并必须保留原始缺失原因、migration mode、生成它的
sensor model/default、参数来源和生成输入。迁移结果是 evaluator-only，不能进入在线 bus、
在线 governed serializer 或 AirSim freeze。2026-07-14 构造合同回归无随机 seed，D1 全量
`92/92`；真实传感器 covariance 与长期 NIS/NEES 标定仍是 P1。

## 17. 批处理不等于时间同步或观测合并（2026-07-14）

D1 的正式批处理原则是“同一到达批次共享计算，不共享证据”。`process_batch()` 不把不同传感器
改成同一个时间戳，也不把多个量测平均成一条；每条观测仍以自己的 measurement time 更新，
arrival time 仍用于 OOSM/延迟审计，covariance、NED/pixel frame、modality 和 source lineage
完整保留。batch 只复用相同航迹历史版本在相同测量时刻的预测结果，并把多次发布时刻历史
重放收敛为每个被改变航迹一次。

航迹历史一旦加入新量测，其 revision 立即变化，只失效该航迹的缓存。检查点之前的合法 OOSM
继续使用 origin/archive；检查点按需重建，不能为了性能剪掉旧证据。因而性能优化的安全边界是
计算复用，不是观测降采样、时间伪同步或 covariance 人为收紧。

2026-07-14 构造回归中重放减少 74.7%，M5N2 seed-001 前 40 帧持久化输入 D1-only 加速
3.17 倍，逐条与 batch 的最终 state/covariance 差为 0，D1 全量 `98/98`。main 尚需完成正式
runtime 接线和完整多 seed 预算验收。

## 18. 扫描级关联与逐条等价批处理必须分离（2026-07-20）

`process_batch()` 与 `process_scan_batch()` 解决不同问题，不能互换口径：

- `process_batch()` 保持调用顺序和逐条关联结果，用于历史 2v2/5v5/M5N2 数值等价回归；
- `process_scan_batch()` 把同一 observer 的整次扫描视为一个集合，所有点迹只与 scan 前航迹
  比较，强制一条航迹最多匹配一个点迹、一个点迹最多匹配一条航迹；
- 一对一匹配后，未匹配 radar 点迹可分别起始，不能因为它们同时落入某条新航迹的宽门限而
  被 observer-scan 规则压成少量航迹；
- 未匹配 acoustic/EO 等非测距观测不能单独制造三维航迹。

新总线适配器必须先执行身份字段治理，再转换数值。在线 payload 中的 truth/actor/object/
entity/target ID 和 offline truth 对象一律拒绝；匿名 observation ID、sensor ID、scan ID 只作
来源和去重，不表示目标身份。雷达球坐标及 covariance 使用解析 Jacobian 转到 NED 六状态，
无径向速度时必须保留足够大的未观测速度不确定性，不能把补零解释为已测得零速度。

二维 `acoustic_bearing` 同时约束方位和俯仰，但仍没有距离。其 soundprint 概率只能描述类别，
必须由 `soundprint_is_identity=False` 治理并在 D1 内改写为 category-only 标志；滤波和关联不能
把类别向量作为稳定目标 ID。2026-07-20 的 seed 7 回归在 5/20/50/100/200 五档首扫/次扫中
分别保持全部航迹，200 档为 `200 birth -> 200 update`；专项 `9/9`、全量 `120/120`。这证明
D1 模块合同，不代表复杂场景多 seed recall、ID continuity 或实时预算已经闭合。

## 19. 未观测速度不能伪装成零速度量测（2026-07-20）

三值 radar 的 producer 只观测 range、azimuth 和 elevation。为保持 D1 既有 radar `4x4`
canonical 合同，可以在第 4 维放置零和距离相关方差，但必须同时标记
`radial_velocity_observed=False`，并遵守以下原则：

1. 滤波 `z/R/h/H` 只使用前三维；补零是合同占位，不是 0 m/s 多普勒证据；
2. 六维起始状态应显式给出速度先验。本实现采用 `v0=0`、`Pvv=25I m2/s2`、`Ppv=0`，它是
   可配置高斯分布而非速度上限，不能读取场景 truth 或 `target_speed_max_mps`；
3. 位置-only radar 使用与量测维数一致的 3 自由度 NIS。默认 99.9% 卡方门限为 `16.2662`，
   门外观测不做后验更新，但保留原始 measurement/arrival timestamp 和 replay history；
4. 门控必须可审计。输出至少区分本次 replay 的 innovation、实际 update 和 rejection 数，
   不能把关联接受数等同于滤波更新数；
5. 速度均值下降不能以隐藏 covariance 为代价。测试必须同时检查有限六维状态、`6x6`
   covariance、速度均值相对方差的尺度，以及多帧 covariance 不坍缩。

2026-07-20、radar-only、seed 17 的 200 航迹/10 scan/2,000 条匿名量测回归始终保持 200 个
ID；末帧速度 median/P90/max=`3.87/6.43/8.54 m/s`，速度 covariance trace=
`57.97/60.69/61.19`。顺序/乱序 OOSM 对照在 `1e-9` 容差内保持 state/covariance 等价。
专项 `13/13`、D1 全量 `124/124`。这些是模块回归，不是多 seed 速度精度、D2/D3 集成或真实
AirSim 标定结论。

## 20. 一致性证据必须在线无真值、离线显式对齐（2026-07-20）

NIS 来自在线滤波创新，可以在不读取 truth 的情况下逐更新记录；RMSE 和 NEES 依赖状态真值与
身份对应，只能在 episode 结束后的离线 evaluator 计算。二者不得写入同一在线 payload，也不能
让 truth sidecar 或 canonical mapping 进入 `FusionAdapter`。

在线 DTO 的最小可审计单位是 observation/update，而不是最终 track 的一个 `last_nis`。它必须
保留双时间戳、sensor/source lineage、innovation dimension、NIS、gate 与 accepted、距离和质量/
covariance scale、D1 `source_global_track_id` availability，以及该更新时刻的六维
estimate/covariance。D2-owned `global_track_id` 只能由离线 lineage adapter 带入结果。
OOSM 到达后，以最终 measurement-time replay 结果覆盖该 observation 的 evidence revision；
未产生 innovation 的初始化、未关联 acoustic/EO 和拒绝项必须写 unavailable reason，不能写 0。

离线对齐采用三个独立且互相绑定 hash 的 artifact：online evidence、truth state sidecar、D2
evaluator-only observation-lineage mapping adapter。每个带 estimate 的记录必须按
`observation_id + measurement_timestamp` 获得唯一 D2 canonical mapping 和唯一六维 NED truth
sample；不得把 D1 source track ID 直接复制成 D2 canonical ID。缺失、重复、未知 truth、时间错位、schema/hash 或
provenance 不一致均停止全部 truth-dependent aggregation。禁止 nearest-neighbor、名称、actor/
object ID、列表顺序和目标数量推断。NEES 只在 estimate covariance 正定时用线性求解计算；奇异
矩阵不使用 pseudo-inverse，availability 设为 false。

2026-07-20 的 `12` 个新增构造测试还验证在线 artifact 注入额外 truth 字段会 fail closed；与
main 复跑的 D1 全量 `136 passed` 共同证明上述合同可执行、
JSON 有限且原有滤波回归保持。已知误差 `5 m/12 m/s` 和 coverage `0.5` 是 evaluator oracle，
不是传感器精度指标。正式多 seed RMSE/NEES/NIS coverage 与阈值仍由 main/D2/D6 后续实验闭合。

## 21. 扫描先整理再融合（2026-07-22）

迟到扫描进入滤波器前先经过独立输入整理。`ScanInputOrganizer` 按 arrival 顺序接收整帧，按
measurement time 水位线释放。窗口内乱序允许重排；严格早于已关闭水位线的帧全部拒绝。等于
水位线的时刻暂不关闭，便于同一时刻的不同传感器来源在窗口内到齐。

整帧原子性是本合同的核心。任何 duplicate、relay replay、scan ID/时间/payload conflict、
too-late、缓冲溢出或驻留超时，都不会把部分点迹送入融合器。每条观测仍携带双时间戳、
covariance、NED/pixel canonical frame、source frame 和 source lineage。在线 truth 字段在摘要
计算前拒绝，`global_track_id` 不在该层产生或改写。

输入整理具有时间和数量上限，并输出逐帧事件和累计审计。main 只处理
`decision.released_scans`：每一帧再交给 `process_scan_batch()`，融合后的 tracks 才能进入 D2。
无扫描 tick 用 `advance_arrival_time()` 检查驻留期限，episode 结束用 `close()` 释放有效尾部。

扫描帧通过字段级快照接收只读输入。数组独立复制并设为只读，嵌套映射递归冻结，因此 main
视觉元数据中的 `mappingproxy` 不需要解冻。快照后仍执行协方差合同和递归在线身份检查，原始
元数据或数组的后续修改不会改变已接收扫描。

该层不做卡尔曼回溯。现有 fixed-lag replay 仍在扫描释放后根据 measurement time 运行。
2026-07-22 的 15 项构造测试覆盖 1/7/200 动态数量、主要拒绝路径及嵌套只读视觉元数据，D1
全量 `151 passed`；未运行 AirSim，也未完成真实长 episode 阈值标定。

## 22. 治理通过不等于融合实时（2026-07-22）

提交 `e4d66db02a0b8f1b867a0e81b4a73de84588426b` 的正式快速治理结果说明水位线、缓冲和
尾部关闭合同在预注册构造流上可执行。20/50/100/200 各 5 seed，20/20 clean/formal；每
episode 136 帧中重排 12、拒绝/过旧/溢出 0、峰值缓冲 3、结束缓冲 0，在线 truth 使用 0。
200 规模峰值内存均值约 40.91 MB、最大 40,926,870 B。该 runner 不执行完整融合，因此不能
用它证明 200v200 实时性或精度。

单次 200v200 三维质点全栈把问题定位到释放后的后验处理。86 个扫描的 D1 fusion 累计
35.115 s，平均 408.313 ms；输入整理累计 2.682 s。当前每个小扫描都可能触发全套关联、历史
重放和后验快照。后续优化必须保持每帧审计和扫描级关联语义，只减少未变航迹的重复传播、复制
和发布。任何通过丢观测、改写时间或压低 covariance 获得的加速都不接受。

治理数据已完成 clean/formal 多 seed 复跑；全栈性能数据仍来自 dirty development 的一个 seed。
AirSim、融合精度、长 episode 历史增长和 clean 全栈多 seed 周期预算仍未验收。

## 23. 后验检查点只复用不变历史（2026-07-22）

常规逐扫描融合会多次询问同一航迹在不同候选量测时刻的状态。如果每次都从固定滞后锚点开始
重放全部历史，已经完成且没有变化的观测前缀会反复执行预测、量测更新和创新计算。目标数和
历史长度同时增长时，这部分成为主要成本。

增量后验检查点把每条已处理观测后的状态、协方差、归一化创新平方和门控结果保存在航迹内部。
检查点只在观测身份和 `(measurement_timestamp, arrival_timestamp, observation_id)` 排序键
完全匹配时复用。迟到观测插入历史中部后，插入点之前的后验仍有效，插入点及其后的后验删除并
重算。固定滞后锚点或起始观测改变会清空全部相关检查点。

缓存不改变证据生成。每次请求状态时，命中的观测仍按当前顺序重新登记 consistency evidence
revision；未命中的后缀执行原有滤波更新。这样保留 OOSM、门控和审计语义，同时避免重复数值
计算。`FusionBatchSummary` 输出实际滤波更新数、检查点复用数、航迹物化数和健康快照构造数，
性能回归可以检查确定性操作数，不依赖容易波动的墙钟阈值。

冻结 200v200 输入的未缓存参考执行 93,234 次滤波更新，增量路径执行 1,797 次，下降 98.07%。
1/7/200 动态规模、窗口内乱序、检查点前合法 OOSM、一致性证据和发布数组隔离均有确定性测试。
性能专项 `6 passed`，main 复跑 D1 全量 `157 passed in 28.77s`。后续仍需在 clean 完整全栈
和更长历史上验证内存及周期预算。
