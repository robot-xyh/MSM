# 第一研究模块：多传感器融合与目标配准算法与实施说明

> 文档日期：2026-07-16
>
> 适用范围：离线科研仿真、受治理回放和系统接口验证
>
> 实现依据：当前第一研究模块代码、`README.md`、`PLAN.md`、模块原理文档和系统总汇总

## 当前权威增量（2026-07-16）

本轮新增 `local_image_track.py` 的保守适配算法。输入是 main-owned
`LocalImageTrackObservation`，输出是 `SensorObservation | None`：

```text
track_state == lost
  -> None

track_state == measured
  -> revalidate timestamps/confidence/center/bbox/2x2 covariance/metadata identity
  -> SensorObservation(modality=eo, frame_id=pixel)
  -> explicit lineage=(local_image_track, source_track_key, measurement_time)
```

visible 与 infrared 不拆成新的内部 modality，而是统一使用 EO 量测模型，并在
`metadata.spectral_band` 区分。默认 observation ID 显式编码 sensor、stream、local epoch、
local track ID 和量测时刻；因此同一本地样本重投递生成同一 ID/lineage，新量测时刻仍保持
唯一。输入 metadata 深复制并保留 backend、batch 与相机等在线审计字段；global/truth identity
键在任意嵌套层级触发拒绝。

融合器接受 EO 更新后，将 namespaced `source_track_key` 去重累积到
`GlobalTrack.metadata.source_track_ids`。该集合用于来源审计而非规范身份，算法不读取它来
生成、选择或改写 `global_track_id`。2026-07-16 的无随机 seed 构造验证为专项 13/13、D1
全量 111/111；没有运行 AirSim，也没有新增 RMSE/NIS/NEES 或 runtime 性能结论。

## 历史权威增量（2026-07-15）

最新真实 AirSim 证据覆盖 M5N2 baseline 10 case 和 candidate 10 case，共 20 case、3,805 个
main-bus tick。D1 fusion 的 mean/P95/max 为 `320.00/451.46/1234.88 ms`，明显主导
main-bus 内层 `349.34/487.40/1305.99 ms`，所以当前算法实施缺口是 fixed-lag/batch 路径在
真实多航迹、多观测循环中的运行时预算，而不是缺少接口级批处理函数。

当前实施约束保持不变：

- 以 `measurement_timestamp` 更新，以 `arrival_timestamp` 审计传输和乱序；
- 每条正式观测和每条航迹必须携带合法 covariance；
- 工作状态在 NED 表达，AirSim truth identity/state 不进入在线估计；本批计数均为 0；
- 性能优化只允许复用预测/雅可比/历史状态和减少重复终结回放，不允许通过观测降采样、时间
  伪同步或 covariance 人为收紧绕过正确性合同。

本批没有输出可用 NIS、NEES 或 RMSE，故不用于选择 EKF/UKF/IMM，也不用于关闭真实
sensor-specific covariance 标定。M5N2 之外仅额外完成 1 个被排除的 `png_ttc_2v2_seed001`，
dropout 为 0；二者不构成算法比较证据。后文历史算法与实现记录继续保留。

## 1. 文档目的与模块边界

第一研究模块的项目代号为 D1。D1 将异步雷达、声学、光电和可选合成激光雷达观测统一到
同一时间基准和坐标工作空间，输出带完整不确定度证据的 `GlobalTrack`。它解决的是“不同
传感器的观测如何形成可供后续处理的航迹候选”，不负责下列事项：

- 不承担第二研究模块（D2）的密集多目标身份保持；
- 不决定第三研究模块（D3）的资源分配；
- 不决定第四研究模块（D4）的主动或被动降级；
- 不执行第五研究模块（D5）的末端视觉绑定；
- 不计算第七研究模块（D7）的导引控制量；
- 不提供真实飞控、硬件驱动、火控、毁伤或自动处置接口。

当前默认在线研究路径是 NumPy 数值计算库实现的常速度扩展卡尔曼滤波、基础门控关联和固定
滞后乱序量测回放。代码按输入数组长度处理目标与观测，不把 2 对 2 或 5 对 5 写成算法常量。

## 2. 术语、缩写与代码名称

本文首次使用的英文缩写统一在此定义，后文直接使用缩写或代码名称。

| 中文名称 | 英文全称与缩写 | 本文含义 |
| --- | --- | --- |
| 北-东-地坐标系 | North-East-Down，NED | D1 的状态估计和跨模块工作空间 |
| 东-北-天坐标系 | East-North-Up，ENU | 外部工具可能使用的本地切平面坐标 |
| 世界大地测量系统 1984 | World Geodetic System 1984，WGS84 | 外部地理参考，不直接作为滤波状态坐标 |
| 扩展卡尔曼滤波 | Extended Kalman Filter，EKF | 当前默认非线性状态估计器 |
| 无迹卡尔曼滤波 | Unscented Kalman Filter，UKF | 尚未进入默认实现的可选对照 |
| 交互多模型 | Interacting Multiple Model，IMM | 尚未进入默认实现的多运动模型路线 |
| 常速度模型 | Constant Velocity，CV | 当前默认运动模型；不是 AirSim 计算机视觉模式 |
| 常加速度模型 | Constant Acceleration，CA | 后续运动模型对照项 |
| 协调转弯模型 | Coordinated Turn，CT | 后续运动模型对照项 |
| 乱序量测 | Out-of-Sequence Measurement，OOSM | 到达顺序晚于物理量测时间顺序的观测 |
| 光电传感器 | Electro-Optical sensor，EO | 当前以像素中心和检测框表达的视觉观测 |
| 激光雷达 | Light Detection and Ranging，LiDAR | 当前仅有合成三维位置观测路径 |
| 归一化创新平方 | Normalized Innovation Squared，NIS | 不使用真值的创新一致性和门控统计量 |
| 归一化估计误差平方 | Normalized Estimation Error Squared，NEES | 需要离线真值的状态一致性指标 |
| 均方根误差 | Root Mean Square Error，RMSE | 需要离线真值和正确身份映射的误差指标 |
| 轻量故障检测、隔离与恢复 | Fault Detection, Isolation and Recovery Light，FDIR-light | 输出健康证据，不执行硬件隔离 |
| 加权最小二乘 | Weighted Least Squares，WLS | 已确认同一身份后的多视线定位助手 |
| 协方差交集 | Covariance Intersection，CI | 未知交叉相关性下的保守状态融合助手 |
| 视线 | Line of Sight，LOS | 观察者到目标的方向射线 |
| 逗号分隔值 | Comma-Separated Values，CSV | 可审计表格回放格式 |
| 逐行存储的 JavaScript 对象表示法 | JSON Lines，JSONL | 观测和运行日志回放格式 |
| JavaScript 对象表示法 | JavaScript Object Notation，JSON | 清单、配置和摘要的结构化文本格式 |
| 应用程序编程接口 | Application Programming Interface，API | 模块对外的 Python 调用接口 |
| 命令行界面 | Command-Line Interface，CLI | 脚本执行入口 |
| 机器人操作系统第二版 | Robot Operating System 2，ROS 2 | 后置工程消息与坐标变换运行环境 |
| 第二代坐标变换库 | Transform Library Version 2，tf2 | ROS 2 中维护坐标变换关系的库 |
| 开源计算机视觉库 | Open Source Computer Vision Library，OpenCV | 后置相机标定和几何后端候选 |
| 佐治亚理工平滑与建图库 | Georgia Tech Smoothing and Mapping，GTSAM | 后置图优化几何后端候选 |

AirSim 是微软开源的无人系统仿真平台；本文中的 AirSim 数据只作为仿真输入和离线评分证据。
`SensorObservation`、`GlobalTrack` 等名称是当前 Python 数据类或字段名，不属于英文缩写。

## 3. 软件结构与实施职责

D1 的主要实现文件如下。

| 文件 | 当前职责 |
| --- | --- |
| `src/d1_sensor_fusion/types.py` | 观测、航迹、质量、健康、协同定位和回放摘要数据合同 |
| `src/d1_sensor_fusion/motion.py` | 常速度状态转移、过程噪声和角度残差处理 |
| `src/d1_sensor_fusion/observations.py` | 雷达、声学、EO、合成 LiDAR 观测模型和默认协方差 |
| `src/d1_sensor_fusion/local_image_track.py` | 本地图像航迹到 EO/pixel 观测的 fail-closed 适配与来源谱系 |
| `src/d1_sensor_fusion/ekf.py` | EKF 预测、数值雅可比、Joseph 协方差更新 |
| `src/d1_sensor_fusion/fusion.py` | `FusionAdapter`、关联、OOSM 回放、分级和健康审计 |
| `src/d1_sensor_fusion/replay.py` | JSONL/CSV 读写、版本化回放和受治理序列化 |
| `src/d1_sensor_fusion/airsim_replay_freeze.py` | 真实 AirSim 持久化输入冻结和在线真值隔离 |
| `src/d1_sensor_fusion/quality.py` | 协方差增长率和区域时间窗口汇总 |
| `src/d1_sensor_fusion/recon_cue.py` | 给机动高空侦察节点的粗指向摘要 |
| `src/d1_sensor_fusion/cooperative.py` | 可选多观察者方位 WLS 和 CI 数值助手 |
| `src/d1_sensor_fusion/long_replay.py` | 可复现长时异步合成回放和摘要 |
| `src/d1_sensor_fusion/p2_benchmark.py` | 隔离的滤波器和一致性指标对照入口 |

main 全局编排模块负责 AirSim 启动、场景重置、回合顺序、跨模块消息路由和结果收集。D1 只
负责上述数据合同和算法，不在模块内部启动 AirSim，也不控制 D2-D7。

## 4. 统一输入合同

### 4.1 `SensorObservation`

统一观测数据类位于 `types.py`，关键字段如下。

```python
SensorObservation(
    observation_id: str,
    sensor_id: str,
    modality: str,
    measurement_timestamp: float,
    arrival_timestamp: float,
    frame_id: str,
    measurement: np.ndarray,
    covariance: np.ndarray | None,
    classification_hint: str | None,
    confidence: float,
    quality_flags: tuple[str, ...],
    metadata: dict[str, Any],
    source_node_id: str | None,
    target_node_id: str | None,
    relay_node_id: str | None,
    link_type: str | None,
    sent_timestamp: float | None,
    received_timestamp: float | None,
    payload_kind: str | None,
    stale_after_s: float | None,
    source_support: dict[str, int] | None,
    timestamp_uncertainty_s: float | None,
)
```

硬性合同如下。

1. `measurement_timestamp` 和 `arrival_timestamp` 必须同时存在且为有限数。
2. `measurement_timestamp` 表示物理采样时刻；`arrival_timestamp` 表示融合节点接收时刻。
3. 每条严格受治理观测必须携带与量测维度匹配的协方差。
4. `radar`、`acoustic` 和 `lidar` 只接受 `frame_id="ned"`；`eo` 只接受
   `frame_id="pixel"`。
5. 外部 WGS84、ENU、机体系和传感器体系必须在进入融合器前转换，或提供构成观测模型所需
   的完整外参。
6. `classification_hint` 是类别提示，不是规范目标身份。
7. 通信字段描述来源、转发和新鲜度，不会自动改变任务分配或控制状态。

数据类会规范化通信元数据和时间戳不确定度。秒和毫秒形式的时钟偏差、抖动或不确定度会归并
为 `timestamp_uncertainty_s`。若到达时刻早于量测时刻，异常差值也会计入时间不确定度证据。

### 4.2 来源谱系与重复抑制

`source_lineage_key` 用于识别“同一源载荷经不同中继重复到达”的情况。优先使用显式
`source_lineage_key` 或 `lineage_id`；否则组合源节点、传感器、模态、载荷类型、源序号和
载荷指纹。`FusionAdapter` 默认启用 `source_deduplication=True`，重复载荷只增加审计计数，
不能再次执行滤波更新并虚假缩小协方差。

来源谱系只用于去重和审计。它不能替代 D2 的目标身份关联，也不能把不同观察者的相关估计
当成独立信息重复融合。

### 4.3 在线身份和真值隔离

在线 D1 输入不得携带或使用 AirSim actor 名称、对象名称、真值目标编号或真值位置来选择
航迹。当前 `FusionAdapter` 保留 `use_truth_hints_for_association` 测试兼容参数和部分旧仿真
元数据兼容代码，但受治理回放、main 运行总线和正式在线验证必须保持该参数为 `False`，且在
进入在线记录前递归移除身份真值。

真值只允许写入 evaluator-only truth sidecar，即“仅评估器可见的真值旁路文件”。D2 和
第六研究模块（D6）在在线算法完成后读取该旁路计算身份切换、RMSE 或 NEES。任何真值进入
在线观测、`GlobalTrack`、D5 或 D7 都属于合同违规。

## 5. 输出合同与质量证据

### 5.1 `GlobalTrack`

输出状态为 NED 下的六维向量：

```text
x = [p_n, p_e, p_d, v_n, v_e, v_d]^T
```

其中前三项是北、东、地位置，后三项是对应速度。`GlobalTrack` 同时携带：

- `global_track_id`：D1 候选航迹编号；进入规范身份链后由 D2 维护稳定身份；
- `state`：六维状态均值；
- `covariance`：6×6 状态协方差；
- `timestamp`：状态有效时刻；
- `track_level`：粗略、稳定、可交接或枚举中的丢失等级；
- `source_support`：各传感器模态的累计支持；
- `identity_likelihood`：类别提示的归一化权重，不是敌我结论；
- `last_nis`：最近创新一致性证据；
- `metadata`：时间、帧、来源、健康、时延和协方差治理审计。

发布元数据至少说明 `frame_id="ned"`、`valid_at`、`published_at`、`hits`、最近量测和到达
时刻、延迟补偿状态、来源支持、重复计数、时延审计和传感器健康摘要。

### 5.2 衍生摘要

D1 还提供以下只读证据，不直接作出分配或降级决定。

- `TrackUncertaintySummary`：位置/速度协方差迹、水平 95% 误差尺度、量测年龄、来源多样性、
  NIS、协方差限制原因、增长率和交接准备度；
- `SensorHealthSummary`：每个传感器的观测、拒绝、重复、OOSM、陈旧、低质量、协方差异常、
  期望时延偏差和恢复状态；
- `LatencyAuditSummary`：融合回放、OOSM、陈旧、重复、最大/平均时延和最大回放观测数；
- `FusionQualityRegionSummary`：同一覆盖单元内的航迹数量、质量分布、时延、协方差和来源缺口；
- `FusionQualityRegionWindowSummary`：多个时刻的区域趋势、增长率和时延窗口统计；
- `ReconCueSummary`：给机动高空侦察节点的粗位置、协方差、时间戳和来源摘要。

这些摘要是 D3 成本、D4 仲裁、D5 投影门限和 D6 评估的输入证据。D1 不输出
`active_degrade_recommendation`，也不直接改变中心、二级或分布式模式。

## 6. 时间处理与固定滞后回放

### 6.1 双时间戳语义

量测时延定义为：

```text
latency = arrival_timestamp - measurement_timestamp
```

通信时延在同时存在 `sent_timestamp` 和 `received_timestamp` 时定义为：

```text
communication_latency = received_timestamp - sent_timestamp
```

量测时刻决定状态在哪一时刻更新；到达时刻只决定消息何时可见、回放顺序和延迟审计。把二者
合并会让迟到雷达量测在错误时刻修正当前状态，造成系统性位置偏差和过度自信。

### 6.2 OOSM 处理流程

`FusionAdapter.process()` 按到达顺序接收观测，默认执行以下步骤：

1. `_prepare_observation()` 补齐或限制量测协方差，记录时间不确定度和质量放大原因；
2. 更新当前到达时刻和时延、陈旧、OOSM、传感器健康计数；
3. 将现有航迹预测到当前到达时刻；
4. 按来源谱系拒绝重复载荷；
5. 在观测的 `measurement_timestamp` 计算关联分数；
6. 将新观测插入航迹历史，按“量测时刻、到达时刻、观测编号”确定性排序；
7. 从最早雷达初始化状态开始，逐条预测到各量测时刻并更新；
8. 将回放后的状态重新传播到当前发布时刻；
9. 裁剪固定滞后窗口内非必要旧观测，保留初始化观测；
10. 发布当前 `GlobalTrack` 和审计摘要。

默认 `buffer_horizon=6.0 s`，`bucket_size=0.1 s`。固定滞后窗口必须覆盖预期最大传感器延迟；
超出窗口的行为需通过陈旧计数和场景配置审计，不能假定任意长延迟都能无损恢复。

设置 `latency_compensation=False` 时，融合器把量测时刻替换为到达时刻，形成延迟补偿消融
基线。该开关用于对比，不是推荐在线配置。

## 7. 坐标转换与空间基准

D1 内部统一使用 NED：`x` 轴指北、`y` 轴指东、`z` 轴向下。推荐外部链路为：

```text
WGS84 -> 本地 ENU -> NED -> 传感器观测模型
机体系/传感器体系 -> 标定外参 -> NED
NED 目标状态 -> 相机外参和内参 -> EO 像素平面
```

实施规则如下。

1. WGS84 只作为外部参考；应固定局部原点后转换为本地切平面。
2. 雷达和声学桥接器先将传感器位置、姿态和方向转换到 NED。
3. EO 保留像素量测，但必须提供相机 NED 位置、世界到相机旋转和内参。
4. 相机默认模型只是测试后备值；真实回放必须携带场景实际标定值和版本。
5. 不允许把像素中心、声学方位或检测器编号直接解释为三维目标位置或规范身份。
6. 当前 D1 未接入机器人操作系统第二版（Robot Operating System 2，ROS 2）的坐标变换库
   `tf2`；工程部署中的动态坐标树仍属于后置适配。

## 8. 状态模型与滤波算法

### 8.1 常速度预测

当前状态转移为：

```text
x_k = F(dt) x_(k-1) + w_k

F(dt) = [[I3, dt I3],
         [03, I3   ]]
```

过程噪声采用白加速度谱密度近似：

```text
Q(dt) = q [[dt^4/4 I3, dt^3/2 I3],
           [dt^3/2 I3, dt^2 I3  ]]
```

默认 `process_noise=6.0`。仿真真值可以转弯或加速，但当前滤波器不切换模型，只依靠过程噪声
吸收机动误差。因此高动态目标的状态滞后和协方差一致性必须通过后续多模型基准验证。

### 8.2 EKF 更新

对非线性观测 `z=h(x)+v`，当前实现执行：

```text
x_minus = F x
P_minus = F P F^T + Q
y = wrap(z - h(x_minus))
S = H P_minus H^T + R
K = P_minus H^T S^(-1)
x_plus = x_minus + K y
P_plus = (I-KH) P_minus (I-KH)^T + K R K^T
NIS = y^T S^(-1) y
```

`H` 由数值雅可比计算。角度残差使用包角处理，避免正负圆周边界跳变。协方差采用 Joseph
稳定形式更新，并在矩阵求解失败时使用伪逆后备路径。

### 8.3 默认选型理由

当前使用 NumPy EKF 的原因是状态维度低、实现可审计、依赖少，且适合大量随机种子回放。
UKF、IMM、FilterPy 和 Stone Soup 并未替换默认路径。它们只有在同一冻结输入上证明身份、
一致性或时延收益，并满足运行预算后，才可能进入后续升级评审。

## 9. 各传感器观测模型

### 9.1 雷达

雷达量测为：

```text
z_radar = [range, azimuth, elevation, radial_velocity]^T
```

设目标与雷达的 NED 相对向量为 `r=p-s`，则：

```text
range = ||r||
azimuth = atan2(r_e, r_n)
elevation = atan2(-r_d, sqrt(r_n^2+r_e^2))
radial_velocity = v dot (r / ||r||)
```

缺少显式协方差时，默认标准差按距离增长：

```text
sigma_range = 2.0 + 0.012 * range
sigma_azimuth = deg2rad(0.25 + 0.0008 * range)
sigma_elevation = deg2rad(0.35 + 0.0010 * range)
sigma_radial_velocity = 0.35 + 0.0015 * range
```

这些系数由 `RadarCovarianceConfig` 管理，可由场景配置覆盖。当前只有雷达可初始化新航迹，
因为它能提供三维位置骨架和径向速度。雷达初始化不代表完整三维速度已被直接观测，未观测的
切向速度以较大初始协方差表达。

### 9.2 声学

声学量测只包含水平粗方位：

```text
z_acoustic = [azimuth]
azimuth = atan2(r_e, r_n)
```

默认角度标准差为：

```text
sigma_deg = 2.5 + 8.0 * (1 - confidence)
```

单个声学方位不包含距离和高度信息，不能独立初始化三维航迹，也不能单独把粗略航迹提升为
可交接航迹。声纹或类别提示只进入 `classification_hint` 和来源支持，不构成敌我身份判定。

### 9.3 EO

当前 EO 量测是检测框中心：

```text
z_eo = [u_center, v_center]^T
p_camera = R_world_to_camera (p_ned - camera_position_ned)
u = fx * x_camera / z_camera + cx
v = fy * y_camera / z_camera + cy
```

相机模型支持嵌套或扁平元数据，包含位置、世界到相机旋转、焦距、主点和图像尺寸。缺少显式
像素协方差时，`eo_covariance_from_bbox()` 根据检测框大小和置信度生成后备值：置信度越低，
误差越大；`occluded` 和 `small_bbox` 标志继续放大协方差。

EO 只提供投影方向约束，不把单帧检测框恢复成无协方差三维点。原始图像和视频不由 D1 保存；
D1 接收的是检测框、相机参数、时间戳、质量和协方差。

### 9.4 合成 LiDAR

合成 LiDAR 量测为 NED 三维位置：

```text
z_lidar = [p_n, p_e, p_d]^T
h_lidar(x) = x[0:3]
```

默认标准差为：

```text
sigma_xy = (0.35 + 0.0025 * distance) / confidence
sigma_z = (0.50 + 0.0035 * distance) / confidence
```

该路径用于 dry-run 和回放合同测试，不表示真实 LiDAR 驱动或 AirSim LiDAR 插件已经接入。
LiDAR 当前不能创建新航迹，只能更新已有航迹。

## 10. 量测关联、初始化与生命周期边界

### 10.1 D1 基础关联

D1 的 `_associate()` 对每条观测和已有航迹计算量测时刻的分数：

- 雷达使用三维位置差及观测、预测位置协方差构成马氏距离；
- 声学、EO 和 LiDAR 使用对应观测创新的 NIS；
- 最小分数不超过 `association_gate` 时接受，否则尝试新建航迹；
- 非雷达观测无法初始化时被拒绝并记录 `unsupported_track_initializer`。

默认 `association_gate=40.0`。该关联器只是融合前端的轻量基线，不替代 D2 的全局最近邻、
联合概率数据关联或多假设跟踪。密集交叉场景中的规范身份、身份切换计数和航迹连续性归 D2。

### 10.2 身份所有权

D1 创建的 `global_track_001` 等编号是融合候选编号。规范 `global_track_id` 的跨时保持由 D2
确认；D5 和 D7 禁止自行改写。协同 WLS/CI 也要求调用方先提供由 D2 确认的同一规范身份，
不能利用几何助手绕过身份确认。

### 10.3 当前生命周期限制

`TrackLevel` 枚举包含 `LOST`，但默认 `_classify()` 只输出 `COARSE`、`STABLE` 和
`HANDOVER`。当前没有完整的超时丢失、删除、合并、拆分或带迟滞质量状态机。因此长期目标
消失时，上层运行总线和后续模块必须显式治理，不能把枚举存在误写为完整生命周期已实现。

## 11. 协方差治理与轻量健康诊断

### 11.1 量测协方差

`_prepare_observation()` 对每条观测执行：

1. 根据模态和元数据生成缺省协方差；
2. 验证维度、有限性和对称性；
3. 对对角值施加模态相关下限和统一上限；
4. 对不合理成对相关项限幅；
5. 根据低置信度、杂波、遮挡或低信噪比记录 `covariance_scale_reason`；
6. 将限制原因写入观测和后续航迹元数据。

严格受治理回放要求原始协方差存在且满足合同；普通运行入口允许使用后备模型是为了原型兼容，
不应掩盖真实传感器未标定的问题。

### 11.2 状态协方差

默认六维状态协方差对角下限为：

```text
[0.25, 0.25, 0.25, 0.04, 0.04, 0.04]
```

位置上限为 `1e6`，速度上限为 `1e4`。长时间外推、量测异常或限制动作都会写入
`covariance_limit_reasons`。当前普通入口主要执行有限性、对称性、对角和相关项治理，尚未
形成统一特征值投影和真实统计一致性保证。

### 11.3 FDIR-light

传感器健康摘要统计：

- 重复、拒绝、OOSM 和陈旧观测；
- 低质量、异常协方差和时间戳不确定度；
- 实际时延相对 `SensorTimingExpectation` 的超限；
- 预期或意外 OOSM；
- 故障原因、隔离提示和故障后的名义样本数量。

达到拒绝阈值只产生健康和隔离建议，不会关闭真实传感器、切断通信或触发 D4 降级。恢复状态
同样是审计证据，不是硬件认证。

## 12. 航迹质量等级与交接准备度

水平 95% 误差尺度由位置协方差左上 2×2 子矩阵计算：

```text
a95 = sqrt(chi2_2_0.95 * max_eigenvalue(P_xy))
chi2_2_0.95 = 5.991464547...
```

当前分类规则是：

- `handover`：`a95 <= 12 m`、至少两类传感器支持、命中不少于 8 次、近期 NIS 通过率不低于
  0.55；
- `stable`：`a95 <= 30 m`、命中不少于 3 次、近期 NIS 通过率不低于 0.45；
- `coarse`：其他情况。

`handover_readiness` 被限制在 `[0,1]`，取协方差、量测新鲜度、来源多样性、NIS 和等级得分
中的最小值。它是保守质量证据，不是行动授权。单帧高协方差、等级回退或 OOSM 不应直接触发
D4 主动降级；D4 必须结合持续时间、D2 身份风险、D3 计划状态、D5 末端冲突和指挥控制健康。

质量等级当前没有独立迟滞，因此阈值附近可能往返变化。D3/D4 应在各自决策层实施版本、驻留
时间和恢复门限，D1 不越权实现任务状态迟滞。

## 13. 受治理回放与证据链

### 13.1 一般 JSONL/CSV 回放

`replay.py` 支持版本化 JSONL、兼容旧 Blocks JSONL 和最小 CSV 读写。回放记录保留：

- 双时间戳和量测协方差；
- 规范观测帧和 NED 融合工作空间；
- 通信、相机、覆盖单元和来源谱系；
- 可用的处理/发布时间、健康和质量元数据。

旧格式可读取不代表满足严格证据合同。正式比较应使用受治理入口。

### 13.2 受治理序列化

`serialize_governed_replay()` 返回：

```text
{
  "manifest": {...},
  "records": [...]
}
```

清单结构版本为 `d1.governed_replay_manifest.v1`，记录观测结构、NED 工作空间、场景/配置标识
及版本、摘要、随机种子、时间范围、覆盖单元和每条观测的不透明来源谱系。严格路径会在返回前
验证整个批次：双时间戳必须有限且有序，协方差必须匹配量测维度，覆盖单元和来源谱系必须存在，
所有记录必须可安全序列化。

在线记录递归删除真值、actor 和对象身份。`serialize_offline_governed_replay()` 是唯一显式
离线入口，将评估标签置于独立 `offline_truth`，不会把标签恢复到在线元数据。

### 13.3 AirSim 持久化输入冻结

`freeze_airsim_replay_payloads()` 和对应 CLI 不连接 AirSim 软件开发工具包，只读取 main 已经
落盘的 JSON/JSONL。输出为：

- `manifest.json`；
- `sensor_observations.jsonl`；
- `offline_truth.json`；
- `summary.json`。

冻结器只为真实存在的量测创建观测。遮挡、漏检或节点退出事件若没有量测，只记录事件，不
伪造传感器数据。在线观测编号改为不透明序号；真值编号和 NED 真值位置只进入旁路。

捕获端必须显式声明场景版本、配置版本、随机种子、`target_spacing_m` 和 `evidence_path`。
目标间距以捕获声明为权威，不从真值位置反推；调用参数、不同载荷声明或证据摘要冲突时拒绝
冻结。清单和真值旁路通过来源摘要绑定。

同一 `(truth_id, timestamp)` 的离线真值样本确定性去重：有位置样本覆盖仅身份样本；两个位置
在 `1e-6 m` 容差外不一致时拒绝冻结；缺失位置不插值、不外推。

### 13.4 长回放构造器

`build_long_replay_scenario()` 可生成任意配置目标数的 60 秒级合成挑战，包含雷达距离噪声、
声学粗方位、EO 像素观测、交叉杂波、遮挡、延迟雷达 OOSM 和中继重复。在线观测不含稳定
目标槽位，真值轨迹只在独立旁路。该构造器验证回放和审计链，不替代真实传感器数据。

## 14. 可选协同定位与保守航迹融合

### 14.1 多观察者方位定位

`localize_bearing_observation_group()` 对已经由 D2 确认为同一 `global_track_id` 的 2..N 条
标定方位射线执行中心化 WLS。每条 `CooperativeBearingObservation` 携带：

- 双时间戳；
- 平台 NED 位置和机体到 NED 旋转；
- 传感器安装平移和旋转；
- 传感器系单位方位向量；
- 方位、平台位姿、外参和时间不确定度协方差；
- 不可变观察者来源谱系。

助手拒绝观察者不足、基线过短、LOS 近共线、时间偏斜过大、缺少必需协方差、信息矩阵病态、
负深度或残差过大。输出保留所有量测/到达时刻、交会角、信息矩阵条件数、残差、协方差膨胀
和明确拒绝原因。

### 14.2 协方差交集

`covariance_intersection()` 将多个六状态 NED 估计传播到共同时间，在未知交叉相关性时搜索
保守权重。它按消息编号和来源谱系去重，保持调用方给定的规范身份，并避免把相关信息按独立
估计简单相加。

WLS 和 CI 当前是已实现的独立数值基础，但没有接入默认 `FusionAdapter` 或真实多节点运行
总线。它们不执行 D2 关联、不实现分布式共识，也不证明 3->2->1 观察节点退出时的端到端性能。

## 15. 跨模块接口和消费方式

```mermaid
flowchart LR
    S[雷达/声学/EO/合成LiDAR观测] --> D1[第一研究模块融合]
    D1 -->|GlobalTrack与协方差| D2[第二研究模块身份关联]
    D1 -->|质量与时延摘要| D3[第三研究模块资源分配]
    D1 -->|区域质量与侦察粗指向| D4[第四研究模块降级协同]
    D2 -->|规范global_track_id| D5[第五研究模块末端视觉关联]
    D1 -->|NED状态与协方差| D5
    D1 -->|中段状态证据| D7[第七研究模块导引]
    D1 -.日志与旁路真值.-> D6[第六研究模块离线评估]
```

### 15.1 D2

D2 消费 D1 航迹候选、状态、协方差、时间和来源证据，维护规范身份并计算身份切换。D1 的
最近邻门控不能替代 D2；离线真值只有 D2 关联完成后才能用于评分。

### 15.2 D3

D3 可把位置/速度协方差、量测年龄、等级和交接准备度加入分配成本。高不确定度应产生惩罚或
更强迟滞，但不应由 D1 直接取消分配。

### 15.3 D4

D4 聚合 `TrackUncertaintySummary`、区域窗口、传感器健康和时延审计，区分节点失效导致的
被动降级与态势质量不足导致的主动降级。D1 只提供证据；二级节点接管、完全分布式协商、租约
和仲裁均由 D4 管理。

### 15.4 D5

D5 使用 NED 状态、完整协方差、双时间戳和相机标定，将规范航迹投影到各相机像素平面。
D5 的局部检测或多目标跟踪编号不得回写 D1/D2 的 `global_track_id`。D5 反馈可以作为质量
冲突证据，但不能让 D1 利用局部真值重新绑定。

### 15.5 D6

D6 只读消费在线记录、质量摘要和离线真值旁路，计算 RMSE、NIS、NEES、时延、健康和区域
趋势。指标缺少真值、身份映射、协方差或分母时必须标为不可用，不能填零。

### 15.6 D7

D7 使用 D1/D2 的中段状态和协方差支撑位置比例导引，并在 D5 与 D3/D4 合同一致时考虑末端
视觉切换。D1 不计算导引律，也不决定控制许可。

## 16. 默认参数与调参原则

| 参数 | 当前默认值 | 实施含义 |
| --- | ---: | --- |
| `process_noise` | 6.0 | 机动吸收能力；过小会滞后，过大会膨胀协方差 |
| `bucket_size` | 0.1 s | 时间离散桶和摘要对齐粒度 |
| `buffer_horizon` | 6.0 s | 固定滞后历史窗口 |
| `stable_threshold_m` | 30.0 m | 稳定等级水平误差门限 |
| `handover_threshold_m` | 12.0 m | 可交接等级水平误差门限 |
| `association_gate` | 40.0 | 基础马氏距离/NIS 关联门限 |
| `latency_compensation` | `True` | 在量测时刻更新并重传播 |
| `source_deduplication` | `True` | 抑制中继重复载荷 |
| `long_extrapolation_s` | 3.0 s | 记录长外推协方差原因的门限 |
| `timestamp_uncertainty_fault_s` | 0.05 s | 时间不确定度健康告警门限 |
| `sensor_isolation_reject_threshold` | 3 | 生成隔离提示的连续拒绝基线 |

调参必须使用版本化场景、冻结输入和 D6 统计。不能为了降低单次 RMSE 人为压小协方差；不能
用单帧表现设定 D4 降级门限；不能用离线真值帮助在线关联。真实雷达距离曲线、相机检测框误差、
声学置信度和传感器时延应分别标定，不能共用一个经验放大系数。

## 17. 当前实施流程

典型离线或 main 运行总线调用链如下。

1. main 或传感器适配器构造满足合同的 `SensorObservation`。
2. 严格运行先通过受治理序列化或 AirSim 持久化冻结，建立清单、来源和真值旁路。
3. 观测按 `arrival_timestamp` 输入 `FusionAdapter.process()`。
4. D1 完成协方差准备、健康审计、基础关联、雷达初始化和固定滞后回放。
5. `global_tracks()` 发布当前航迹候选。
6. `track_uncertainty_summaries()`、`sensor_health_summaries()`、
   `latency_audit_summary()` 和 `region_quality_summaries()` 发布质量证据。
7. D2 维护规范身份，D3/D4/D5/D7 按各自合同消费，不反向改写 D1 航迹身份。
8. D6 在回合结束后读取在线日志和隔离真值，输出可用性、指标和失败原因。

基础测试命令为：

```bash
PYTHONPATH=research_modules/d1_sensor_fusion/src \
pytest -q research_modules/d1_sensor_fusion/tests
```

长回放和隔离基准分别由 `scripts/run_long_replay.py`、
`scripts/run_p2_isolated_benchmark.py` 调用。文档更新不改变这些入口。

## 18. 当前能力状态

### 18.1 默认主线已实现

- NED 六状态、观测和航迹协方差；
- 双时间戳、时间不确定度和固定滞后 OOSM 回放；
- 雷达、声学、EO 和合成 LiDAR 观测模型；
- NumPy CV/EKF、数值雅可比和 Joseph 协方差更新；
- 雷达初始化、基础马氏距离/NIS 关联和来源谱系去重；
- 粗略、稳定和可交接质量分级；
- 协方差限制原因、FDIR-light、时延和区域质量摘要；
- JSONL/CSV 回放、受治理清单、AirSim 输入冻结和在线真值隔离；
- 不写死 2 对 2、5 对 5或固定目标数。

### 18.2 已实现但不在默认主线

- 2..N 个已确认同一身份观察者的方位 WLS；
- 未知交叉相关性的 CI；
- 合成长回放和隔离滤波评分；
- 旧 Blocks JSONL 兼容读取；
- `use_truth_hints_for_association` 测试兼容参数。该参数严禁用于受治理在线验证。

### 18.3 尚未实现或尚未闭合

- UKF、IMM-EKF、IMM-UKF 和完整多运动模型主线；
- FilterPy、Stone Soup 可执行后端替换；
- ROS 2 `tf2`、消息同步和真实传感器驱动；
- D1 直连 AirSim 在线传感器；
- 纯 EO/声学新航迹初始化；
- 完整 `lost/dropped` 生命周期、航迹合并/拆分和质量迟滞；
- WLS/CI 的真实多节点运行总线闭环；
- 工程级真实雷达、声学和相机误差曲线冻结。

## 19. 2026-07-13 验证结果

### 19.1 D1 回归基线

当前模块原理和计划记录的 D1 全量回归为 **79 passed**。本次只同步文档，没有修改代码，
因此不重新声称执行全量测试。

### 19.2 真实 AirSim 密集交叉输入

当前严格输入证据包括：

- AirSim 计算机视觉模式，5 个目标；
- 常规相邻间距严格 4 m、紧密相邻间距严格 2 m；
- 每种间距 20 个随机种子，共 40 个真实 AirSim 回合；
- 每回合 51 帧，默认不保存截图；
- evaluator-only truth sidecar 共 10,200 个样本；
- 在线真值泄漏计数为 0；
- 全部冻结记录保留双时间戳、协方差、NED、来源谱系、场景/配置版本、随机种子、目标间距和
  证据路径；
- D6 将 `d1_dense_crossing` 证据标记为可用。

这组结果证明 AirSim 持久化输入冻结、捕获来源校验、真值旁路隔离和下游可消费性已经闭合。
它不证明真实雷达/声学/EO 误差模型已经标定，也不证明 D1 在密集交叉中保持规范身份；后者
属于 D2 的离线评分。

### 19.3 隔离合成基准

六条雷达观测的小型冻结样本曾得到：

- 位置 RMSE 约 0.2335 m；
- 平均 NIS 约 0.0426；
- 平均 NEES 约 0.0651；
- 验证主机相关耗时约 6.9 至 10.1 ms。

该样本规模很小，低 NIS/NEES 反而说明协方差偏保守。它只证明评分路径可运行，不能作为真实
传感器精度或实时性结论。验证环境中的 FilterPy 和 Stone Soup 均不可用，结果明确标记
`unavailable_reason`，没有替换当前 NumPy 路径。

### 19.4 合成长回放证据

默认长回放曾生成 843 条观测、21 个注入雷达 OOSM、6 个被抑制中继重复和 29 个区域窗口，
在线真值泄漏为 0。RMSE/NEES 在缺少 D2 规范身份映射时保持不可用，不由 D1 猜测或填零。

## 20. 剩余限制与下一步实施重点

当前优先级一限制如下。

1. **真实传感器挑战数据不足**：现有严格 4 m/2 m 回放主要验证几何声明、冻结和离线身份
   输入，尚未覆盖有代表性的雷达/声学/EO 漏检、匿名虚警、遮挡、异步采样、特定时延、时钟
   异常和节点退出分布。
2. **长期阈值未冻结**：区域协方差增长、量测新鲜度、交接准备度、NIS/NEES、期望时延和
   健康误报/漏报仍需正常/故障多随机种子对照。
3. **协同定位未运行时闭环**：WLS/CI 助手存在，但 D1/D2 规范身份适配、部分共享谱系、
   真实多节点回放和 3->2->1 节点退出质量退化尚未闭合。
4. **单模型限制**：高机动目标仍由 CV 过程噪声吸收，缺少 CA/CT/IMM 同输入对照。
5. **长期 D6 一致性**：跨场景和长时运行中的结构版本、可用性、证据路径、健康、区域窗口和
   RMSE/NIS/NEES 汇总还需持续校验。
6. **数值治理边界**：普通入口未形成统一半正定特征值投影与统计一致性保证。
7. **生命周期不完整**：默认融合器尚无完整丢失、删除、合并、拆分和状态迟滞。

优先级二只做隔离对照：UKF、IMM、FilterPy、Stone Soup、OpenCV/GTSAM 协同几何后端和
ROS 2 适配均不得在未完成冻结输入、依赖、指标和收益评审前写成默认能力。下一阶段应先由
main 提供版本化真实多随机种子长回放，D1 冻结实际观测并保持真值隔离，再由 D2/D6 完成身份
映射和统计校准。

## 21. 实施结论

D1 已形成一条可执行、可审计的研究链：异构观测先经过双时间戳、坐标和协方差规范化，再由
常速度 EKF 在量测时刻更新，通过固定滞后回放传播到发布时刻，最后输出带质量、来源、健康和
不确定度证据的 `GlobalTrack`。严格回放将在线算法与离线真值物理分离，来源谱系避免中继重复
造成虚假收敛。

当前结论应限定为“科研仿真的融合合同和证据链已经闭合，真实传感器长期标定和高机动、多节点
协同融合仍需验证”。不得把 AirSim 几何回放、合成低误差样本或枚举中存在的状态解释为真实
设备性能、完整身份保持或工程部署能力。

## 22. 在线 Scene Observation 匿名化算法（2026-07-14）

scene-derived observation 的边界流程为：

```text
scene truth
-> sensor projection/noise/miss/occlusion generation
-> SensorObservation[] + separate offline truth labels
-> anonymize_online_observations()
-> assert_online_observations_identity_free()
-> online D1/D2 algorithms
```

匿名化先从调用方 `identity_tokens` 和递归身份 metadata 键收集 token。随后深拷贝观测，删除
truth/actor/object/segmentation/identity/instance 等身份键，清理嵌套字符串、quality flag 和
`classification_hint` 中的 token，并删除原 source-lineage metadata。frame 优先使用已存在的
frame index，否则使用 `measurement_timestamp`；每个 frame 按输入顺序分配不透明 observation
序号。原始 source lineage 在 frame 内按首次出现顺序映射为不透明 source 序号，因此 relay
重复可保持同 lineage，而目标名字不会进入新 ID。

算法只复制而不改写输入，并逐元素复制 measurement/covariance。双时间戳、sensor ID、通信
时间、payload kind、NED/pixel frame、bbox 和相机内外参保持。构造完成后 validator 遍历全部
在线字符串、metadata 容器和 dataclass；任何身份键或已知 token 立即抛出 `ValueError`。对于
未出现在身份键中的任意别名，main/runtime 必须通过 `identity_tokens` 显式声明，不能假设 D1
可从任意字符串自动判断语义身份。

2026-07-14 单测以两组各 2 条仅更换 target/actor/truth 名字的 EO 观测验证全字段严格相等、
数值和 camera geometry 不变、嵌套 key/value、observation ID、classification 和 lineage 无
泄漏；同时验证人工注入泄漏 fail closed，以及原始 observation/offline sidecar 不变。专项
`4 passed`，模块全量 `83 passed`。本实现不改变 dry-run、replay reader、offline serializer
或 evaluator sidecar。

## 23. 无真值关联治理与事件对齐检查点（2026-07-14）

关联阶段为每条已接受观测生成 `(modality, observer_id, scan_id)` 键。同一航迹已消费该键时，
后续候选记为 `observer_scan_conflict`，不更新也不生成新航迹。因为键中含 modality，同一时刻
的 radar 与 acoustic/EO 可分别提供一次支持。雷达严格关联失败后，只对近期、至少已有两次
雷达支持且总命中成熟的航迹计算独立重捕候选；唯一候选可重捕，多候选记为
`ambiguous_radar_birth_suppressed`。非测距更新则以更新前后位置改变量对先验位置协方差计算
马氏分数，异常修正拒绝并记录传感器健康原因。

固定滞后裁剪不再把初始雷达状态长期作为唯一回放起点。算法先找到滞后边界之前最新的已接受
量测时刻，重放到该时刻并保存量测后的后验，再只保留其后的活动窗口。选择量测时刻而不是任意
墙钟边界，是因为当前常随机加速度离散过程噪声不满足任意分段后协方差完全等价；事件对齐可
保持原预测区间和后续更新增益。被裁剪观测进入 archive，仅在合法旧 OOSM 到达时从 origin
重建检查点。输出审计使用 `d1.association_audit.v1`，不包含 actor/truth ID。

专项测试覆盖同扫描去重、唯一雷达重捕、非测距异常修正拒绝、检查点连续性和检查点之前的
声学 OOSM。结果专项 `5/5`、D1 全量 `87/87`；main 的 AirSim runtime 接口回归为
`134/134`。修复后的真实同 seed episode 仍待 main 复跑。

## 24. Observation Covariance 硬门控（2026-07-14）

`validate_sensor_observation_covariance()` 按 modality 固定 measurement/covariance 维度，并依次
检查缺失、数值转换、shape、finite、symmetry 和最小特征值。`FusionAdapter` 使用
`validate_online_sensor_observation()`，额外拒绝带 offline imputation provenance 的对象；
测量模型和雷达初始化不再调用 default covariance 作为缺值回退。合法输入随后仍执行既有低
质量 scale、diagonal floor/ceiling、EKF 更新和 fixed-lag/OOSM replay。

普通 JSONL/CSV reader 对 legacy 和 v1 均要求 covariance，且不再把 flat array reshape 成矩阵。
`migrate_offline_legacy_sensor_observation()` 是唯一缺值兼容入口：根据 radar range、acoustic
confidence、EO bbox/confidence/flags 或 synthetic lidar distance 显式生成研究默认值，并写入
可 JSON 序列化的 model/default provenance。该 observation 在 online/governed/AirSim 路径被
拒绝。

2026-07-14 验收覆盖 missing、non-finite、non-symmetric、non-PSD、wrong shape、显式 legacy
migration、governed round trip、合法 OOSM 和 AirSim freeze 回归；无随机 seed，D1 `92/92`。
这些测试证明合同行为，不证明默认噪声模型已按真实传感器标定。

## 25. 批量观测的惰性状态重放算法（2026-07-14）

逐条模式对每条观测执行两类高成本操作：关联时计算每个候选航迹的 measurement-time 状态，
接受后再把该航迹全历史重放到 current time。同一帧有 `M` 条观测、`N` 条航迹时，未缓存的
关联近似重复执行 `O(MN)` 次历史遍历，接受更新又增加 `O(M)` 次发布重放。

批量实现维护 `_BatchProcessingContext`：

```text
state_cache[(track_id, history_revision, measurement_timestamp)] -> EKFState
dirty_track_ids                                               -> set
checkpoint_dirty_track_ids                                    -> set
```

算法步骤：

1. 先对全批观测执行不修改滤波状态的正式 covariance/online 合同校验；
2. 按调用方输入顺序逐条更新 current arrival watermark、latency/OOSM 和 sensor health；
3. 逐条执行 duplicate、observer scan、关联和非测距修正门控；
4. `_state_at()` 先按 track history revision 查缓存，命中返回副本；
5. 接受量测后写入原始 observation history，并仅增加对应 track revision；
6. 检查点前 OOSM 写入 archive 并标记 checkpoint dirty，只有需要检查点后状态时才重建；
7. 批末按 track ID 排序，每个 dirty track 重放一次到最终 current time、更新 NIS、covariance
   限制和 fixed-lag checkpoint，然后统一生成 `GlobalTrack[]`。

缓存不能跨 batch 保留，避免配置、健康状态或外部调用导致隐式陈旧。输出顺序沿用内部 track
插入顺序，终结处理使用 track ID 排序，因此相同初始状态和相同输入序列产生确定输出。异常
语义与 streaming API 一致：预校验失败不修改状态；处理阶段发生意外异常时已经成功处理的前缀
不会自动回滚。

`FusionBatchResult.tracks` 是批末快照，`summary` 给出接受/拒绝/重复、创建/更新、实际 replay、
cache hit/miss 和合并的发布重放。2026-07-14 的 5 航迹/15 观测测试中 replay 为 95 -> 24；
真实 M5N2 seed-001 前 40 帧 D1-only 为 1267 -> 351，最终数值完全一致。完整 D1 回归为
`98 passed`。

## 26. 可扩展三维扫描级一对一融合算法（2026-07-20）

### 26.1 总线适配与球坐标 covariance 传播

`Scalable3DFusionAdapter` 通过字段合同而非 Python 类型依赖读取 `OnlineSensorBatch`。适配前
递归遍历字段名并拒绝在线身份真值。三维雷达量测为

```text
z = [rho, azimuth, elevation]
```

当 producer 未提供径向速度时，D1 为兼容 canonical radar 合同扩展为：

```text
z_contract = [rho, azimuth, elevation, 0]
R_contract = block_diag(R_spherical_3x3, sigma_rdot_placeholder^2)
radial_velocity_observed = false
```

第 4 维只是序列化/接口占位。`measurement_model_for()` 在该标志为 false 时构造
`z_filter=z_contract[:3]`、`R_filter=R_contract[:3,:3]`，观测函数也只返回 range/azimuth/
elevation；因此补零径向速度不会进入创新。位置转换为：

```text
pN = sN + rho cos(elevation) cos(azimuth)
pE = sE + rho cos(elevation) sin(azimuth)
pD = sD - rho sin(elevation)
```

位置 Jacobian `Jp` 只对前三维球坐标求导。无多普勒起始状态和 covariance 为：

```text
x0 = [pN, pE, pD, 0, 0, 0]
P0 = [[Jp R_spherical Jp^T + P_sensor, 0],
      [0,                                  25 I3]]
```

`25 m2/s2` 是公开可配置的各轴零均值高斯先验，不是速度裁剪，也不读取场景真实速度。若 producer
确实提供第 4 维多普勒且标为 observed，则保留原四维量测路径，并仅对未观测切向速度增加方差。
输入原 `3x3` spherical covariance 不被默认模型替换，canonical observation 的左上块逐元素
保留。最终 track 始终是 `[pN,pE,pD,vN,vE,vD]` 和 `6x6` covariance。

### 26.2 扫描级关联与批量 birth

设扫描前航迹数为 `T`、点迹数为 `O`。radar 路径先把所有航迹传播/重放到统一
measurement time，把每个点迹转为 NED 位置和 covariance，再向量化计算：

```text
d(i,j) = (z_j - x_i)^T (P_i + R_j)^-1 (z_j - x_i)
```

门外项设为大代价，使用 `scipy.optimize.linear_sum_assignment` 求一对一最小代价；SciPy
不可用时退化为确定性门内贪心匹配。求解后再次检查原始门限。所有匹配只针对 scan 前航迹，
随后再应用 measurement-time EKF/OOSM 更新；未匹配 radar 点迹逐条调用合法起始器。这样第一
条 birth 不会参与同一 scan 后续点迹的竞争，从算法上消除固定门限造成的空间 packing 上限。

更新仍使用 `_BatchProcessingContext`：同测量时刻的 track state 只重放一次，dirty track 在
批末各重放一次到 arrival watermark。历史 scan 迟到时写入原 observation history，并按既有
fixed-lag/origin/archive 规则重建；track 输出同时保留 measurement/arrival timestamp。

### 26.3 三维声学弱约束

`acoustic_3d` 的观测函数为：

```text
h(x) = [atan2(rE, rN), atan2(-rD, sqrt(rN^2 + rE^2))]
```

两个角度残差均 wrap，Jacobian 数值计算，输入 `2x2` covariance。该模态只进入已有航迹的
创新和 EKF 更新，不属于 radar 起始器。soundprint 概率先检查有限、非负、和大于零，再归一化
并仅作为 category metadata 保存；它不进入代价矩阵，也不作为 truth hint。

### 26.4 回归证据与复杂度边界

2026-07-20、seed 7，5/20/50/100/200 各两次 scan，共 750 条匿名 radar measurement：首扫
全部 birth，次扫全部一对一 update，200 档航迹数保持 200；状态有限、`6x6` covariance 半
正定。2 目标 delayed scan 验证 2 条 OOSM 重放；声学验证 0 birth/5 update 类别边界；身份注入
全部拒绝。专项 `9 passed`、模块全量 `120 passed`。

radar 关联的矩阵规模为 `O(T*O)`，200x200 当前可接受，但本轮没有给出长 episode、多 sensor、
虚警增长下的正式实时上界。track confirmation/deletion、跨 scan ID continuity 和至少 20 个
未见 seed 的 recall/NIS/NEES 由后续 D2/D6/main 集成验收。

### 26.5 位置-only radar 创新门控与速度稳定性

对于预测状态 `x-`、covariance `P-` 和三维量测模型，先计算：

```text
nu = z_filter - h_filter(x-)
S = H P- H^T + R_filter
NIS = nu^T S^-1 nu
```

默认门限 `gamma=chi2_3(0.999)=16.26623619623813`。若 `NIS>gamma`，replay 保留预测状态和预测
covariance，不应用该 measurement update；量测仍保留在按 measurement timestamp 排序的历史
中，所以顺序处理与 OOSM 重放会得到相同的门控判定。metadata 记录本次 replay 的创新数、
实际滤波更新数、拒绝数及匿名 observation IDs。扫描关联接受数和滤波更新数因此是两个不同
审计口径。

2026-07-20 的自动化证据包括：无多普勒三维模型/`25I` 先验、一个门内关联但超 NIS 阈值的
离群点、2 航迹顺序/乱序 3 scan 数值等价，以及 seed 17 的 200 航迹/10 scan/2,000 条匿名
radar measurement。200 条末帧速度 median/P90/max=`3.87/6.43/8.54 m/s`，速度 covariance
trace=`57.97/60.69/61.19`；数量和 ID 全程保持 200。专项 `13 passed`、模块全量
`124 passed`。

该结果只证明短基线噪声不再被当前 D1 路径过度写入速度均值，且不确定性仍显式存在。固定
零均值先验会收缩早期速度；过程噪声仍为现有 CV 参数。多 seed 速度误差 coverage、NIS/NEES、
机动和漏检/虚警，以及 D2 二次滤波/D3 分配仍需后续正式验证。

## 27. 逐更新 consistency evidence 与纯离线 evaluator（2026-07-20）

### 27.1 在线 evidence 采集

`FusionAdapter` 为每个 observation 建立固定 schema record。track birth 写六维初始化 estimate，
不伪造 innovation；正式 `_finalize_record_replay()` 和 checkpoint 前 origin replay 在已有
`_filter_update()` 返回后记录 posterior/prediction、NIS 与 gated 标志。采集不参与 association
candidate 的临时 `_state_at()` 查询，因此不会把代价矩阵内部探针误写成 episode evidence。
OOSM 触发新 replay 时，同一 observation record 按 revision 更新；算法仍调用原 NumPy EKF 和
原 gate，evidence 不反馈状态、门限或 track ID。

online record 使用 opaque lineage SHA-256，保留 sensor 和 lineage 等价关系但不复制潜在身份
值。radar 直接 range 按 `d1.consistency.range_bins.v1` 输出 `[0,1000)`、`[1000,3000)`、
`[3000,5000)`、`[5000,+inf)`；同时保留 `range_m`，D6 可按正式实验另行重分箱。records digest
覆盖排序后的所有 DTO，bundle digest 覆盖 schema、range profile、provenance、count 和 records
digest。所有序列化均要求 `allow_nan=False` 可通过。

### 27.2 离线严格对齐与指标

truth sidecar 的键为 `(truth_id, timestamp)`，state 必须是六维 NED；D2 先用 source
observation lineage 形成 canonical identity，再输出以
`(observation_id, measurement_timestamp) -> (D2 global_track_id, truth_id)` 表示的 adapter，
并绑定 online/truth digest。D1 evidence 内的航迹键明确命名为 `source_global_track_id`，不进入
D2 canonical namespace。对每个 available estimate，evaluator 要求：

```text
estimate_timestamp == measurement_timestamp
exactly_one_lineage_mapping(observation_id, measurement_timestamp)
exactly_one_truth_sample(truth_id, estimate_timestamp)
```

容差默认 `1e-9 s`，不插值、不外推、不做 proximity matching。对误差 `e=x_est-x_truth`：

```text
position_rmse = sqrt(mean(||e_position||^2))
velocity_rmse = sqrt(mean(||e_velocity||^2))
NEES = e^T P^-1 e
normalized_nees = NEES / 6
nis_gate_coverage = mean(NIS <= configured_gate)
```

NEES 先对 `P` 做 Cholesky 正定检查，再使用 `solve`；任一样本奇异则 episode-level NEES
unavailable，不能仅挑选可逆样本形成偏置统计。NIS 与 gate coverage 不依赖 truth，因此缺失
mapping/truth 时仍可单独 available。result 不嵌入 online state 或完整 truth，只保留误差、
metric availability 与三个输入 digest，形成物理分离的离线 artifact。

### 27.3 输出和验证边界

online/offline `aggregation_records()` 均输出 scenario/version/run/seed、sensor ID/type、range、
observation/update 指标和 source/input digest，记录数随输入变化，无 2v2/5v5 常量。2026-07-20
新增 `12` 项合同测试，包含额外在线 truth 字段 fail-closed；main 复跑 D1 全量
`136 passed`。oracle 夹具为 position RMSE `5 m`、
velocity RMSE `12 m/s`、NIS gate coverage `0.5`；其目的仅是验证公式和 fail-closed 路径。
正式多 seed 精度、统计 coverage 和传感器 covariance 校准尚无新证据。
