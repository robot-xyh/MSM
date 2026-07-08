# D1 AirSim 集成计划

## 1. 范围与边界

本文只描述 D1 在 AirSim/offline research simulation 中的观测适配、回放和评估合同。D1 不负责 AirSim Blocks 启停、episode reset、actor target 移动、`simGetDetections` 调用、frame capture、runtime bus 编排、真实飞控、硬件驱动、火控、毁伤或自动处置。

当前代码状态：

- **已实现**: 无 AirSim 依赖的 dry-run fixture adapter，可把 fake AirSim-like episode 转成 radar/acoustic/EO/synthetic lidar `SensorObservation[]`；`blocks_sensor_observations.jsonl` reader/replay，可将 main/shared runtime 写出的 D1 JSONL 观测读回并喂给 `FusionAdapter`。
- **部分实现**: D1 可消费 main/shared runtime 提供的 simulation-derived observations，例如 AirSim truth 派生 radar-like 记录和 `simGetDetections`/detector boxes 派生 EO bbox 记录；但 D1 包内不直接调用 AirSim API，也未接入真实 AirSim runtime bus。
- **未实现**: 真实雷达/声学/LiDAR 硬件仿真、AirSim sensor plugin 级桥接、ROS 2 `tf2/message_filters`、OpenCV calibration/solvePnP/projectPoints、Stone Soup/FilterPy 后端。

## 2. 时间基准

- 使用 AirSim simulation time 或 main runtime 统一仿真时钟作为上游 capture time。
- 每条进入 D1 的观测必须同时填写 `measurement_timestamp` 和 `arrival_timestamp`。
- `measurement_timestamp` 表示模拟传感器采样、检测框生成或 truth-derived record 的物理测量时刻。
- `arrival_timestamp` 表示融合进程接收时间或离线 replay 日志时间。
- D1 `FusionAdapter` 以 `arrival_timestamp` 排序处理输入，以 `measurement_timestamp` 执行滤波更新和 fixed-lag replay。
- `GlobalTrack.metadata` 已输出 `latest_measurement_timestamp`、`latest_arrival_timestamp` 和 `latest_observation_latency_s`；`TrackUncertaintySummary` 已输出 `measurement_timestamp`、`arrival_timestamp`、`valid_at`、`published_at` 和 `measurement_age_s`。

## 3. 坐标帧

D1 内部融合状态使用 NED：

```text
x: north / forward
y: east / right
z: down
```

当前 AirSim Blocks 的本地坐标可由 main/shared runtime 转成 D1 接收的 `frame_id="ned"`。如果后续引入 geodetic metadata，应在进入 D1 前把 WGS84/ENU 转成本地切平面 NED，并在 metadata 中记录 scene origin、外参版本和转换来源。

D1 当前帧规则：

- radar/acoustic/lidar 观测只接受 `frame_id="ned"`。
- EO 观测只接受 `frame_id="pixel"`，并通过 metadata 中的相机内参、外参或 `CameraModel` 参与投影约束。
- D1 不在核心融合路径中直接滤波 WGS84、ENU、body frame 或 camera frame；这些转换由上游或专门几何模块完成。

## 4. 传感器桥接合同

### 4.1 Dry-run fixture bridge

- 使用 `observations_from_airsim_dry_run_fixture()` 作为 D1 首个 AirSim-like 集成门。
- fixture 是普通 Python dict，包含 `frames[].timestamp`、`targets[].state_ned` 和 synthetic sensor config。
- 该 bridge 不导入、不连接、不调用 AirSim，只把 fake episode record 转为 `SensorObservation[]`。
- 每条输出观测包含 `measurement_timestamp`、`arrival_timestamp`、`frame_id`、`measurement`、`covariance`、`confidence` 和 dry-run metadata。
- 测试覆盖 radar/acoustic/EO/synthetic lidar 四类观测，以及 optional lidar 开关。

### 4.2 Radar-like bridge

- 当前 radar-like 观测来自科研仿真或 AirSim truth 派生，不代表真实雷达硬件仿真已接入。
- 上游将目标 NED state 和传感器 NED position 转成 `[range, azimuth, elevation, radial_velocity]`。
- D1 使用 `RadarCovarianceConfig` 或记录内 covariance，支持距离相关 range/angle/radial velocity 噪声。
- radar 是当前唯一可初始化新 `GlobalTrack` 的观测类型，避免声学/EO 单源把弱约束误当三维真值。

### 4.3 Acoustic bridge

- 当前 acoustic 是粗方位观测和可选 `classification_hint`，用于弱约束和身份似然提示。
- 观测为方位角，协方差随 confidence 放大或缩小。
- D1 不实现 TDOA、阵列主定位、风噪/混响硬件模型，也不允许 acoustic 单独初始化三维航迹。

### 4.4 EO bridge

- 当前 EO 入口为 detector bbox 或 `simGetDetections`/detector boxes 派生记录，不要求 PNG 截图。
- D1 使用 bbox center `[u_center, v_center]` 作为像素观测，并从 metadata 读取 camera intrinsics/extrinsics 或 `CameraModel`。
- bbox 小、置信度低、截断或遮挡时应放大 EO 像素协方差，避免二维检测框过度拉偏 NED 航迹。
- D1 当前只实现 pinhole 投影约束；畸变、标定、`solvePnP`、`projectPoints` 和跨视角几何一致性应由 D5 或后续 OpenCV 对照项处理。

### 4.5 Synthetic lidar bridge

- synthetic lidar 只用于 dry-run/replay 中的 NED 三维位置观测，含 3x3 covariance。
- 该桥不是 AirSim LiDAR plugin，也不是真实硬件驱动。
- 若未来 main/shared runtime 提供真实或 AirSim LiDAR 记录，仍需先固化 schema、时间戳、坐标和 covariance 来源。

## 5. D1 输入输出合同

输入记录应能构造为：

```python
SensorObservation(
    observation_id=...,
    sensor_id=...,
    modality="radar" | "acoustic" | "eo" | "lidar",
    measurement_timestamp=sim_capture_time,
    arrival_timestamp=fusion_receive_time,
    frame_id="ned" or "pixel",
    measurement=np.ndarray,
    covariance=np.ndarray,
    confidence=...,
    classification_hint=...,
    metadata={...},
)
```

Blocks N actor gate：

- main 通过 `--drone-count N` 决定场景规模；D1 按输入 `SensorObservation[]` 和 truth/actor record 长度运行，不写死 2v2 或 5v5。
- historical 2v2/5v5 logs 只能作为 baseline；不能成为算法常量。
- 必填字段为 `measurement_timestamp`、`arrival_timestamp`、`frame_id`、`measurement` 和 `covariance`。
- 当前 AirSim evidence 是 simulation-derived：radar-like 记录可由 target truth 派生，EO pixel 记录可由 `simGetDetections`/detector boxes 派生。
- radar、acoustic、lidar 在当前阶段是科研合成观测；不能写成真实传感器硬件仿真已完成。

输出为：

```python
GlobalTrack(
    global_track_id=...,
    state=[px, py, pz, vx, vy, vz],
    covariance=6x6,
    timestamp=...,
    track_level="coarse" | "stable" | "handover",
    source_support={...},
    metadata={
        "frame_id": "ned",
        "valid_at": ...,
        "published_at": ...,
        "latest_measurement_timestamp": ...,
        "latest_arrival_timestamp": ...,
        "a95_m": ...,
    },
)
```

下游模块应消费 `GlobalTrack.position`、`GlobalTrack.velocity`、`GlobalTrack.covariance`、`track_level`、`source_support` 和 timing metadata。`handover` 只是仿真质量标签，不是授权状态，也不能直接接入任何动作链。

## 6. Replay 与评估流程

1. main/shared runtime 运行 AirSim episode，控制 Blocks launch/reset/actor target/检测记录。
2. runtime 将每个 actor target 的 simulation-derived observation 写为 D1 JSONL record，例如 `blocks_sensor_observations.jsonl`。
3. D1 使用 `read_blocks_sensor_observations_jsonl()` 读回观测，并按 `arrival_timestamp` replay。
4. 分别运行 latency-compensated 与 uncompensated fusion，比较 RMSE、连续性、分级准确性和延迟补偿效果。
5. 对 N actor 合同，D1 应按输入数组长度输出对应 `GlobalTrack[]`，不依赖 2v2/5v5 固定数量。
6. 评估结果可交给 D6 汇总；D1 已提供 replay schema v1/legacy JSONL 兼容、最小 CSV reader、`LatencyAuditSummary` 和轻量 `FusionQualityRegionSummary`，后续仍需与 D6 对齐长期批量 schema、区域时间窗口和协方差增长率窗口。

## 7. 对 D2-D7 的接口影响

- **D2**: 使用 D1 的 `global_track_id`、协方差、时间戳和 `source_support` 做关联连续性；truth ID 只作为离线标签，不能替代在线 `id_switch_count`。
- **D3**: 使用 `track_level`、`a95_m`、`measurement_age_s` 和 source diversity 判断分配候选质量；D3 仍负责版本化 `AssignmentPlan` 和 stale plan 拒绝。
- **D4**: 可消费 `TrackUncertaintySummary`、`LatencyAuditSummary` 和轻量 `FusionQualityRegionSummary` 做态势质量判断；D1 不输出区域级主动降级仲裁，最终降级仍由 D4 结合 C2 health、D3 版本和 D5/D7 反馈决定。
- **D5**: 可用 D1 的 NED 航迹、协方差、EO bbox/camera metadata lineage 做投影门控；D5 不得改写 `global_track_id`。
- **D6**: 可统计 D1 RMSE、连续性、分级、latency ablation、`TrackUncertaintySummary`、`LatencyAuditSummary`、`FusionQualityRegionSummary`、source diversity 和 duplicate count；剩余 P1 是长期批量 schema、区域时间窗口和协方差增长率窗口。
- **D7**: 只应使用 `stable`/`handover` 航迹作为离线中段导引输入，并根据协方差和 freshness 门控；D1 不提供飞控或自动处置接口。

## 8. 后续 P1/P2

### P1

- 已完成 `blocks_sensor_observations.jsonl`/未来 `sensor_observations.jsonl` schema v1、legacy JSONL 兼容、最小 CSV reader/replay、latency/OOSM audit 和轻量区域质量摘要。
- 增加来自 main/shared runtime 的真实 AirSim CV detection fixture，覆盖 bbox、camera metadata、actor label、timestamp、covariance 和 N actor 输出，并形成真实样本回归。
- 与 D6 对齐长期批量 JSONL/CSV schema，稳定 `TrackUncertaintySummary[]`、`LatencyAuditSummary` 和 `FusionQualityRegionSummary[]` 字段。
- 补区域时间窗口、freshness/source-gap 趋势、协方差增长率窗口和更细 NIS 统计。
- 保持 D1 不直连真实 AirSim runtime bus，由 main/shared runtime 继续拥有 AirSim 启停和日志写出。

### P2

- 可选接入 FilterPy EKF/UKF 对照，验证与 NumPy fallback 的误差和协方差一致性。
- 可选接入 Stone Soup OOSM/JPDA/MHT/Track Fusion 离线实验，先做指标对照再决定是否扩大使用。
- 与 D5 对齐 OpenCV calibration/projectPoints/solvePnP 边界。
- 等 ROS 2 runtime、tf tree、topic schema 和 bag/replay 稳定后再评估 `tf2/message_filters`。
