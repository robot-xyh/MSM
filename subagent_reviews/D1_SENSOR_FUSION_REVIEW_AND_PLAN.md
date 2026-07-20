# D1 多传感器融合与目标配准综述及子方案

**定位**: 雷达、声学、光电异构观测进入统一融合链路，输出带协方差、时间戳和状态机的 `GlobalTrack`。  
**边界**: 本文仅用于科研仿真、态势感知和人工复核接口设计，不包含真实火控参数、毁伤参数、自动处置控制律或绕过人工授权的流程。

---

## 0. 当前权威状态（2026-07-16）

- D1 已实现 `sensor_observation_from_local_image_track()`：只把 `measured` 本地图像航迹转换为
  EO/pixel `SensorObservation`；`lost` 返回 `None`，不复用旧 center/bbox/covariance。
- 适配边界保真双时间戳、2×2 pixel covariance、confidence、quality flags 和 visible/
  infrared 波段；缺失、非法或非半正定 covariance 以及 global/truth identity 均 fail closed。
- sensor/stream/local epoch/local ID 组成 namespaced `source_track_key`。它与量测时刻共同形成
  可去重 lineage；被接受视觉来源仅累积到 `GlobalTrack.metadata.source_track_ids`，绝不作为
  `global_track_id`。
- 2026-07-16 构造合同场景无随机 seed；专项 `13/13`、D1 全量 `111/111`。验收阈值为合法
  字段逐项保真、非法 covariance/identity 100% 拒绝、lost 0 输出、来源累积且 global ID
  不变。本轮未运行 AirSim，不提供新的 RMSE/NIS/NEES 或 runtime timing 结论。
- main 后续负责把真实 producer 接到该 API，并验证 backend/batch audit、相机模型和重复投递
  行为；D1 的适配器完成不等价于跨模块运行时接线已完成。

### 0.1 历史权威状态（2026-07-15）

本节覆盖后文按日期保留的历史阶段结论；历史内容用于说明实现演进，不代表当前 GAP 状态。

- main 已完成真实 AirSim M5N2 baseline 10 case 与 candidate 10 case，共 20 case。在线
  identity/state truth use 均为 0，既有 truth 隔离 P0 保持通过。
- 20 case 共记录 3,805 个 main-bus tick。D1 fusion mean/P95/max 为
  `320.00/451.46/1234.88 ms`，是 main-bus 内层主导阶段；main-bus 整体 mean/P95/max 为
  `349.34/487.40/1305.99 ms`。100 ms 预算仍是开放 P1。
- 双时间戳、观测/航迹 covariance、NED 与 source lineage 继续作为硬合同。此前 D1-only
  batch replay 等价性成立，但不能据此声称真实 AirSim 循环已达标。
- 本批面向终端闭环和时序，不提供可用 NIS、NEES 或 RMSE，不能关闭真实 sensor-specific
  covariance、滤波一致性和定位精度标定。
- M5N2 20/20 后已停止；TERM 前额外完成 1 个 `png_ttc_2v2_seed001`，明确排除；dropout
  完成数为 0。
- 当前计划优先级为：先在冻结输入下定位 D1 fusion 的 fixed-lag/batch/history 成本并由 main
  复跑多 seed 预算，再单独建设带 availability 的 NIS/NEES/RMSE 标定；不得通过放宽时间或
  covariance 合同换性能。

### 0.2 历史 Dense Crossing 权威状态（2026-07-13）

- main 已完成 strict dense crossing 的真实 AirSim 采集：nominal 4 m 与 tight 2 m 各
  20 seeds，共 40 个 episode，每个 episode 51 帧、5 个目标。
- D1 governed replay 保留双时间戳、covariance、NED、source lineage、scenario/config
  version、seed、目标间距和 evidence path。evaluator-only truth sidecar 共 10,200 个样本，
  `online_truth_leak_count=0`。
- D6 统一证据报告将 `d1_dense_crossing` 标记为 `available`，并保留 schema、digest 和
  evidence path；缺失指标继续显式为 `unavailable`。
- D1 全量回归为 `79 passed`。当前无 D1 P0 blocker；governed replay、truth 隔离和证据可
  消费性不再作为未实现项。
- 仍开放的 P1 聚焦真实 radar/acoustic/EO 漏检、匿名虚警、部分/完全遮挡、异步采样率、
  sensor-specific latency/故障 fixture，以及区域时间窗、covariance growth、health、NIS/NEES
  和场景自适应 covariance 的长期治理。D1/D2-confirmed 协同融合和节点退出 replay 仍需实证。
- FilterPy、Stone Soup、OpenCV/GTSAM 和 ROS 2 `tf2`/`message_filters` 仍为 P2/P3 可选
  benchmark 或后续工程适配，不是当前已实现的在线能力，也不替换 NumPy EKF/fixed-lag 主线。

## 1. 研究问题

当前难点不是单个传感器能否发现目标，而是不同传感器的观测时间、坐标系、误差模型和语义不同：

- 雷达输出距离、方位、俯仰、径向速度或三维点迹，但存在扫描周期、链路延迟和距离相关误差。
- 声学输出粗方位、声纹或类别提示，定位精度受阵列孔径、风噪、混响和遮挡影响较大。
- 光电输出像素框、类别和置信度，本质上是图像平面约束，不能直接当作三维位置真值。
- 每类观测都有 `measurement_timestamp` 和 `arrival_timestamp`，融合必须按测量时刻处理，不能按到达时刻简单更新。

目标是把所有观测标准化为 `SensorObservation`，经过时间对齐、坐标转换、协方差建模和延迟补偿后，形成统一的 `GlobalTrack`。
运行时目标数量由 main 的 `--drone-count N` 统一控制；D1 接收 main 提供的 N 个 target truth/观测源，并按输入数组长度处理，不在算法路径写死 2 或 5。

---

## 2. 文献综述要点

2015-2026 年异构传感器融合的共识可以概括为四点。

第一，时间基准应以测量时刻为准。雷达扫描、光电曝光、声学采样和网络传输可能相差数十到数百毫秒。滤波更新使用 `measurement_timestamp`，`arrival_timestamp`只用于记录通信延迟、乱序检测和缓存管理。乱序观测通常按 OOSM 处理，可采用 fixed-lag buffer、重传播、平滑更新或信息滤波。

第二，融合状态应在局部米制坐标系中维护。WGS84 适合记录地理元数据，不适合直接线性滤波。推荐在局部 ENU/NED 中估计位置和速度，同时保留原始 `sensor_frame`、`body_frame`、`map_frame` 和外参版本。协方差转换使用近似雅可比：

```text
P_out = J * P_in * J^T + P_calib
```

第三，协方差必须随距离、遮挡、SNR 和杂波动态变化。雷达横向误差会随距离放大；声学 DOA 是粗方位，声纹只应作为身份似然；光电像素框在小目标、截断、遮挡和逆光时应显著放大测量协方差。

第四，融合系统不应把传感器检测直接升级为可处置目标。`GlobalTrack`只表达位置、速度、协方差、置信度和状态，授权逻辑由上层系统单独处理。

---

## 3. 开源代码选型

| 工具 | 用途 | 优点 | 限制 | 估算工作量 |
|------|------|------|------|------------|
| Stone Soup | 多目标跟踪、OOSM、轨迹融合、JPDA/MHT实验 | 组件化强，适合科研验证 | 需要封装ROS/仿真接口 | 5-10人日 |
| FilterPy | EKF/UKF/IMM原型 | 简洁，便于快速验证 | 不含完整航迹管理 | 3-6人日 |
| ROS 2 tf2 | 坐标树、外参、时间化变换 | 工程通用 | 不处理协方差建模 | 3-5人日 |
| message_filters | 多传感器时间同步 | 易集成 | 不能替代OOSM补偿 | 1-3人日 |

当前代码状态：D1 主线采用 NumPy EKF fallback，不依赖 Stone Soup、FilterPy、ROS 2 或 AirSim Python 包即可运行测试。Stone Soup 和 FilterPy 只保留占位/可用性探测边界；ROS 2 `tf2`、`message_filters` 是运行环境稳定后的 P2 后置选项。当前不应把这些开源库写成已接入能力。

---

## 4. 子系统方案

### 4.1 统一数据结构

```text
SensorObservation
- observation_id
- sensor_id
- modality: radar | acoustic | eo | lidar(optional dry-run)
- measurement_timestamp
- arrival_timestamp
- frame_id
- measurement
- covariance
- classification_hint
- confidence
- quality_flags

CanonicalDetection
- detection_id
- source_observation_id
- timestamp
- frame_id: ned | enu
- z
- R
- modality
- confidence

GlobalTrack
- global_track_id
- state: position + velocity
- covariance
- timestamp / valid_at
- measurement_timestamp
- arrival_timestamp / published_at
- track_level: coarse | stable | handover
- source_support
- identity_likelihood
```

### 4.2 融合链路

```text
SensorObservation
-> timestamp normalization
-> sensor_frame to body/map/NED
-> adaptive covariance model
-> OOSM delay compensation
-> track filter update
-> GlobalTrack publish
```

### 4.3 延迟补偿

如果观测到达时刻晚于测量时刻，不能直接用当前状态修正。推荐维护短时状态缓存：

```python
class DelayCompensator:
    def update(self, track, detection):
        if detection.timestamp < track.timestamp:
            past = self.rewind(track, detection.timestamp)
            past.correct(detection)
            return self.replay_to_now(past)

        track.predict_to(detection.timestamp)
        track.correct(detection)
        return track
```

### 4.4 协方差自适应

```text
radar_R = base_R(distance, snr, beam_width)
        + clutter_penalty
        + occlusion_penalty
        + timestamp_latency_penalty

acoustic_R = doa_uncertainty(array_aperture, snr, peak_width)
           + wind_noise_penalty
           + reverberation_penalty

eo_R = projection_uncertainty(bbox_size, detector_confidence)
     + truncation_penalty
     + calibration_penalty
```

---

## 5. 雷达定位误差分档规则

使用水平 95% 误差椭圆长轴作为统一质量指标：

```text
a95 = sqrt(chi2_2_0.95 * lambda_max(P_xy))
```

阈值由仿真或标定数据确定，设 `T_h < T_s < T_c`。

| 档位 | 判据 | 允许用途 |
|------|------|----------|
| `coarse` | `a95 > T_s` 或仅短时单源支持 | 告警、继续观测、请求补充传感器 |
| `stable` | 连续多帧 NIS 通过，`a95 <= T_s` | 进入中心关联和资源分配候选 |
| `handover` | `a95 <= T_h` 且多源一致 | 可交给末端配准或显示，不等价于处置授权 |

---

## 6. 与主动降级/D5/D7 的接口改进

本节补充 D1 在当前主线架构中的接口责任。D4 已引入主动降级，D5 需要多视角目标关联，D7 使用比例导引作为离线仿真中的中段导引模块。D1 不输出控制指令，也不参与处置决策，只输出带时间、坐标和不确定度的数据合同。

### 6.0 2026-07-07 P1 复核更新

main runtime bus 已把 D1-D7 DTO/summary/record 接入真实 AirSim episode 状态机，并将 D7 执行结果回灌到正式 episode metrics；D3 已补充中心重规划后的 plan owner/version；D4 已把主动降级硬风险与软质量风险拆分；D5 已修正终端一致性窗口。对 D1 的影响是接口语义收紧，而不是新增算法职责：

- D1 的 `TrackUncertaintySummary` 是 D3/D4/D5/D6 的质量证据，不是降级动作或授权状态。
- D1 的高协方差、低 freshness、source gap 或 handover readiness 下降，需要由 D4 结合 C2 health、D3 plan freshness、D5 terminal evidence 和持续窗口仲裁；不应由单帧软风险直接触发主动降级。
- D1 不生成 D3 `AssignmentPlan` 版本，不决定二级/分布式接管，也不修改 D7 PN/PNG 控制律。
- 严格 subagent 流程下，D1 owned README/PLAN/GAP/review 状态由 D1 子智能体自行维护和测试；main 只做集成汇总。

### 6.1 面向 D4 主动降级的不确定度信号

D4 的主动降级需要判断“中心节点仍在线，但中心态势质量不足”。当前 D1 已把单航迹质量指标随 `GlobalTrack.metadata` 或 `TrackUncertaintySummary` 输出给 D3/D4，并提供轻量 `FusionQualityRegionSummary` 按 `coverage_cell` 聚合区域质量；主动降级 hint 和最终降级仲裁仍不在 D1 当前实现内。

```text
TrackUncertaintySummary
- global_track_id
- measurement_timestamp
- arrival_timestamp
- valid_at
- published_at
- track_bucket
- track_level
- position_cov_trace
- velocity_cov_trace
- a95_xy_m
- latest_observation_latency_s
- measurement_age_s / observation_freshness_s
- source_support
- source_diversity_count
- last_nis
- handover_readiness
- quality_flags
```

主动降级候选条件：

- 雷达协方差迹或 `a95_xy_m` 短窗口内突增，说明中心定位分辨率下降。
- `latest_observation_latency_s` 或 `measurement_age_s` 超过 D3 分配周期，说明分配使用的是过期观测。
- `observation_freshness_s = published_at - latest_measurement_timestamp` 持续变大，说明航迹主要靠外推维持。
- `source_support` 从雷达+EO等多源退化为单源，或后续区域摘要显示关键区域出现 coverage gap。
- `handover` 不能稳定维持，频繁回退到 `stable/coarse`。
- 雷达与 EO 的 NIS 长时间偏高，说明多源观测不一致。

当前区域摘要只能作为质量证据。若后续需要 D1 给出显式质量建议，也只能是建议字段，例如：

```text
active_degrade_hint = none | regional_secondary_node | distributed_review
reason = high_covariance | stale_observation | sensor_gap | handover_unstable | sensor_disagreement
```

最终是否切换到二级节点或分布式协同，应由 D4 结合 `C2Health`、D3 分配版本、D5 末端反馈和人工授权状态决定。

### 6.2 对 D7 中段雷达比例导引的支撑

D7 的比例导引模块不应直接读取原始雷达点迹，而应使用 D1 发布的融合航迹。D1 需要保证 `GlobalTrack` 至少携带：

```text
position: [px, py, pz] in NED
velocity: [vx, vy, vz] in NED
covariance: 6x6 state covariance
measurement_timestamp: latest contributing measurement time
arrival_timestamp / published_at: fusion output arrival/publish time
track_level: coarse | stable | handover
source_support: radar/acoustic/eo/lidar support counts
```

工程规则：

- D7 只能把 `stable` 或 `handover` 作为中段仿真输入；`coarse` 应只用于继续观测或保持原计划。
- D7 应根据 `covariance` 和 `track_level` 决定是否扩大预测门限或保持保守状态。
- 若 `latest_observation_latency_s` 或 `measurement_age_s` 过大，D7 应使用 D1 的速度和协方差做外推，并把新鲜度不足反馈给 D4/D3。
- D1 不向 D7 提供真实飞控、硬件、毁伤或自动处置接口；这里只定义离线仿真的航迹状态输入。

### 6.3 对 D5 视觉交接与多视角关联的支撑

AirSim Blocks 运行时默认不再保留截图，只保留相机元数据、检测框和检测置信度。D1 的 EO 接口应适配这种模式：

- EO 输入使用 `bbox_xyxy`、`center_px`、`camera_id`、相机内参、相机外参和 `measurement_timestamp` 构造 `SensorObservation(modality="eo")`。
- D1 不依赖保存 PNG；图像文件不是融合合同的一部分。
- D1 只把位置航迹、速度、协方差和时间戳传给 D5，D5 再将 `GlobalTrack` 投影到对应相机平面做门控。
- 多视角同一目标关联时，D1 应保留 `sensor_id/camera_id`、`frame_id`、外参版本和 `source_support`，便于 D5 判断不同视场观测是否支持同一 `global_track_id`。
- 如果相机检测框很小、截断、遮挡或置信度低，D1 应放大 EO 测量协方差，避免单次视觉框强行拉偏全局航迹。

D5 的末端关联结果可作为 D1/D4 的反馈信号，但不得由 D5 本地直接改写 D1 的 `global_track_id`。

### 6.4 工程改进记录（含 2026-07-10 历史基线）

已完成：

1. **最新量测时间显式化**：`GlobalTrack.metadata` 已记录 `latest_measurement_timestamp`、`latest_arrival_timestamp` 和 `latest_observation_latency_s`；`TrackUncertaintySummary` 已导出 `measurement_timestamp`、`arrival_timestamp`、`valid_at` 和 `published_at`。
2. **距离相关协方差参数化**：`RadarCovarianceConfig` 已支持 range/angle/radial velocity 噪声随距离增长的参数配置，默认参数保持现有测试行为。
3. **声学弱约束边界**：当前代码只允许 radar 初始化新航迹；声学作为方位/类别弱约束参与更新，不会单独生成三维 `GlobalTrack`。
4. **EO 无截图合同**：D1 EO 观测只需要 bbox、中心像素、相机元数据、时间戳和协方差；dry-run 与 JSONL replay 测试不依赖 PNG。
5. **source lineage 去重**：相同 source/sequence/payload 经 relay 重复投递时不会重复更新航迹，`duplicate_observation_count` 会进入 metadata。
6. **replay schema v1/legacy 兼容**：`sensor_observations.jsonl` 使用 `d1.sensor_observation.v1`，既有无版本 `blocks_sensor_observations.jsonl` 作为 legacy 兼容输入。
7. **CSV replay 最小支持**：已提供 `read_sensor_observations_csv()`/`replay_sensor_observations_csv()`，CSV 中 measurement/covariance 使用 JSON array，metadata/communication/source_support 使用 JSON object。
8. **延迟补偿审计字段**：已提供 `LatencyAuditSummary`，记录 max/mean delay、OOSM replay 次数、stale/OOSM count、duplicate count 和最大 replay 历史长度。
9. **区域质量摘要**：已提供轻量 `FusionQualityRegionSummary`，在单航迹 `TrackUncertaintySummary` 之上按 `coverage_cell` 聚合 source gap、freshness、a95、handover readiness、stale track count 和可选协方差增长率。
10. **2026-07-08 AirSim 多 seed 校准准备**：CSV replay 缺省 `schema_version` 时按 `d1.sensor_observation.v1` 验证并要求 `covariance`；Blocks calibration CSV 回归已覆盖 measurement/arrival timestamps、covariance、NED state、source support、latency/OOSM audit 和区域质量摘要。
11. **嵌套 EO camera metadata replay**：JSONL/CSV metadata 中的 `camera_model` 字典可恢复相机内外参并参与 EO 投影模型，避免真实 Blocks/CV replay 使用默认相机。
12. **雷达 cue 侦察粗指向摘要**：已提供 `ReconCueSummary` 和 `summarize_recon_cue_from_tracks()`，可从 `GlobalTrack[]` 或 track-like dict 生成全部目标/指定 `coverage_cell` 子群的协方差加权 `cue_position_ned`、`cue_covariance`、`active_target_ids`、时间戳和基础诊断；可选 `metadata` 保留二级/移动高空侦察节点、cue 来源和模式，供 main/AirSim runtime 控制二级侦察相机指向。
13. **真实 Blocks/CV 字段保真**：JSONL/CSV replay 已将顶层 `bbox_xyxy`、`center_px`、`camera_metadata`、`detection_metadata`、`source_support`、`coverage_cell`、`covariance_scale_reason` 和 secondary/mobile recon cue metadata 规范化进 `SensorObservation.metadata`，并把最新 EO/camera/bbox/recon lineage 带入 `GlobalTrack.metadata`。
14. **区域窗口与协方差增长 helper**：已提供 `annotate_covariance_growth_rates()` 和 `summarize_region_quality_windows()`，输出 `FusionQualityRegionWindowSummary`，可把区域质量下降、freshness 下降、source gap 与 latency/OOSM flags 分开给 D4/D6 消费。
15. **2026-07-09 P1 输入支撑补强**：dry-run fixture 已增加 schema version 检查，JSONL replay 已回归 unsupported schema version 拒绝，`summarize_sensor_observation_latency_audit()` 可在不运行融合器时统计 observation latency/OOSM/stale/duplicate lineage，Blocks/CV JSONL/CSV 回归已覆盖 `covariance_scale_reason`、`mobile_recon`、`recon_cue_summary`、`cue_position_ned` 和 `cue_covariance` 保真。
16. **D6 bundle 消费口径**：main/D6 可把 raw/fusion latency audit、`TrackUncertaintySummary`、区域质量/窗口摘要、`SensorHealthSummary`、covariance limit reason、`covariance_scale_reason` 和 `timestamp_uncertainty_s` 作为观测延迟与质量证据汇总；D1 不把这些字段解释为主动降级动作。
17. **2026-07-10 真实 2v2 合同复核**：六个 reset-separated episode 共 1,528 条
    radar/acoustic/EO/synthetic-lidar 观测均可由 D1 reader 解析，双时间戳完整，covariance
    有限、对称、半正定；full-flow 36 个 main bus tick 的 D1 观测摘要和
    `TrackUncertaintySummary` 也持续保留 timing/covariance 字段，未发现 D1 合同回归。
18. **2026-07-10 十 seed/在线身份隔离边界复核**：2v2 十 seed 系统运行证明 D1 DTO 可被
    多 episode 重复消费；5v5 truth-isolation smoke 证明 D5 在线 local detection/MOT ID 已
    与 actor/object 名称隔离。该证据不等于 D1 truth-free replay 闭合，`truth_id` 仍仅可
    作为离线评分标签，main truth-hint 配置仍需 provenance 和无真值对照。

当前 P0 状态：无 P0 blocker。D1 已实现并回归 measurement/arrival timestamp、协方差、NED `GlobalTrack`、N-target 输入和 `ReconCueSummary` 侦察 cue 合同；剩余工作均为 P1/P2 增强或外部 fixture/schema 对齐。

2026-07-10 main/D6 集成状态：main runtime 已新增 P1 D4/D5 calibration sweep，并在 sweep 后自动生成 D6 标准报告 bundle。D1 不负责启动 AirSim sweep、episode reset 或报告 bundle，只负责保证 `SensorObservation` replay、`GlobalTrack`、`TrackUncertaintySummary`、`LatencyAuditSummary`、`FusionQualityRegionSummary[]`、`FusionQualityRegionWindowSummary[]`、`SensorHealthSummary[]`、covariance reason 和 timestamp uncertainty 字段可被 main/D6 稳定消费。真实 2v2 产物确认 main tick 已发布 per-track uncertainty，但 main writer 尚未写显式 `schema_version`/`coverage_cell`，main tick 也未发布 region/window、latency audit 和 sensor health 摘要；main bus 依赖 simulation-only truth hint 保持 2 条航迹，而默认 truth-free replay 会产生 3 条航迹。因此这些仍是 P1 集成/校准项，truth metadata 只能作为离线评估标签。

剩余 P1：

1. **显式 replay schema 与区域字段**：当前真实 Blocks JSONL 未写 `schema_version` 和 `coverage_cell`，只能通过 legacy schema 兼容并归入 `unassigned`；main/shared writer 需采用 `d1.sensor_observation.v1` 并传递 coverage cell，D1 不跨边界修改 runtime。
2. **D6 长期批量 schema**：main tick 已发布 `TrackUncertaintySummary[]`，仍需发布并对齐 `LatencyAuditSummary`、`FusionQualityRegionSummary[]`、`FusionQualityRegionWindowSummary[]`、`SensorHealthSummary[]`、covariance reason 和 timestamp uncertainty 的长期 JSONL/CSV 字段。
3. **expected-latency/OOSM 健康阈值**：固定 0.2 s 延迟的正常多传感器流会产生大量合法 OOSM；需用延迟预算、同帧 batch/水位线或滑动比率避免 FDIR-light 把正常流误标为 `isolated`，标定前不得把该摘要直接作为 D4 降级证据。
4. **truth-free replay 一致性**：把 fusion/association 配置写入 replay provenance，并修正无 truth-hint 时的重复初始化，使同一日志的离线 replay 与在线约束一致；truth metadata 不得成为真实在线身份证据。
5. **真实 Blocks/CV fixture**：2v2 十 seed 系统运行已完成，但尚未固化为 D1 长期回归 fixture；仍需 N actor、CV detection JSONL/CSV 样本覆盖 camera metadata、bbox covariance、`coverage_cell` 和 secondary/mobile recon metadata，并保证 actor label 只作离线评估标签。
6. **真实样本阈值**：区域窗口、freshness/source-gap、协方差增长率和 handover readiness 的持续阈值仍需带 `coverage_cell` 的多 seed fixture 与 D6 统计共同校准。

P2/后置：

1. **开源对照后端**：FilterPy、Stone Soup、OpenCV、ROS 2 仍未接入；只有在对照场景、依赖环境和收益指标明确后再作为 P2 或 P2 后置扩展。
2. **D1 直连 AirSim runtime**：D1 当前不直接调用 `simGetDetections` 或 AirSim API；P1 只要求消费 main/shared runtime 写出的 JSONL/CSV fixture。

---

## 7. 测试矩阵

| 测试 | 输入 | 期望结果 |
|------|------|----------|
| 雷达延迟 | 固定延迟点迹 | OOSM补偿后RMSE下降 |
| 距离变化 | 近中远三档雷达点迹 | 协方差随距离合理放大 |
| 声学粗方位 | 大角度不确定观测 | 只收窄方位，不强行定位 |
| 光电像素框 | 小框、遮挡、低置信度 | `R`放大，避免误配准 |
| 坐标错误 | 错误外参版本 | 触发质量告警，不发布高置信航迹 |
| 主动降级信号 | 协方差突增、观测延迟、传感器缺口 | 当前输出单航迹质量摘要、latency/OOSM audit、轻量区域质量摘要和区域窗口趋势；Blocks/CV replay 回归已固定这些字段的字段保真；`active_degrade_hint` 与最终区域仲裁仍由后续 D4/系统规则处理 |
| 侦察相机粗指向 | `GlobalTrack[]` 或 track-like dict，可选 `coverage_cell`/cue metadata | 输出 `ReconCueSummary`，按协方差 trace 反比加权 centroid，缺协方差使用保守默认并记录诊断；metadata 可携带二级/移动侦察节点与 cue 来源 |
| D5无截图交接 | 仅相机元数据和检测框 | 已支持不依赖PNG，输出可投影航迹和EO协方差 |
| D7航迹输入 | `stable/handover` 航迹和6x6协方差 | D7可读取位置、速度、时间戳和质量状态 |

---

## 8. 交付物

1. 文献综述：时间同步、坐标转换、协方差自适应建模。
2. 开源选型表：Stone Soup、FilterPy、ROS 2 tf2、message_filters。
3. 数据结构：`SensorObservation`、`CanonicalDetection`、`GlobalTrack`。
4. 接口伪代码：`FusionAdapter`、`DelayCompensator`、`TrackFilter`。
5. 雷达误差分档：`coarse`、`stable`、`handover`。
6. 主动降级/侦察 cue 接口：`TrackUncertaintySummary`、`LatencyAuditSummary`、轻量 `FusionQualityRegionSummary`、`FusionQualityRegionWindowSummary` 和 `ReconCueSummary` 已落地；D4 降级建议字段和最终仲裁仍为后续工作。
7. D5/D7接口合同：无截图 EO 输入、投影所需状态协方差、中段航迹质量门控。

---

## 9. 参考资料

- Stone Soup: <https://github.com/dstl/Stone-Soup>
- Stone Soup documentation: <https://stonesoup.readthedocs.io/>
- FilterPy: <https://filterpy.readthedocs.io/>
- ROS 2 tf2: <https://docs.ros.org/en/rolling/Concepts/Intermediate/About-Tf2.html>
- ROS 2 message_filters: <https://docs.ros.org/en/humble/p/message_filters/doc/Tutorials/Approximate-Synchronizer-Cpp.html>
- REP-103 coordinate conventions: <https://www.ros.org/reps/rep-0103.html>
- REP-105 coordinate frames: <https://www.ros.org/reps/rep-0105.html>

---

## 10. 历史基线：2026-07-11 Replay/Schema 专项评审

本轮将此前“reader 能读真实日志”推进为“D1 能定义并验证新 writer 合同”。

- `ReplayProvenance` 把 scenario/config/run/seed 与每条观测绑定，避免同一 JSONL 无法复现融合参数来源。
- governed writer 强制 schema 与 covariance，默认不写在线 truth/actor/object ID；离线评分标签只能放在 `offline_truth`。
- `SensorTimingExpectation` 明确“固定链路延迟导致的 OOSM 可以是正常现象”。D1 仍统计所有 OOSM，但只有未预期 OOSM、stale 或延迟预算超限才进入对应故障证据。
- 区域质量从任意长度聚合扩展为固定时长 `coverage_cell` 窗口，协方差增长、freshness、source gap 和窗口化 latency/OOSM 分开输出。
- 固化的 Blocks/CV 形态 JSONL/CSV fixture 不依赖 AirSim SDK；无在线 truth hint 的两目标 replay 可保持两条 NED 航迹及其 6x6 协方差。

测试结果为 D1 全量 `38 passed`。该结果关闭 D1-owned 的 schema/provenance、健康字段和窗口 helper 缺口，但不等于真实 AirSim 多 seed 标定完成。main 仍需接入新 writer、提供真实配置摘要、关闭 simulation-only truth hint，并把 D1 region/window/health 输出送入 episode bus 和 D6。

## 11. 历史基线：2026-07-11 5v5 Truth-Isolated Runtime 复核

main 在
`research_modules/airsim_runtime/outputs/p1_runtime_truth_isolated_d4d5_smoke_20260711/`
完成三个 5v5 case：不降级、二级节点接管、完全分布式。在线 truth hint 隔离后，每个 case
均运行 5 帧，D1/D2/D3 health 为 `ok`，D1 每组产生 15 条记录，D3 assignment coverage
保持 1.0。这是 D1 状态/协方差经过 D2 中心航迹进入 D3 的首个 truth-isolated 真实
main-bus 正向证据，旧的“main 仍依赖 simulation-only truth hint”状态应视为历史审计结论。

D1 governance 也已进入 `main_episode_bus_metrics.json`：三组均记录一次
`d1_latency_audit` 和一次 `d1_region_quality_window`，region quality coverage 为 1.0，
mean/max delay 约 0.2 s。`d1_oosm_observation_rate` 三组均约为 0.9867，但 stale rate 为
0。这个高 raw OOSM rate 符合当前固定延迟、多传感器逐条异步 replay 的统计定义，不代表
传感器故障，也不得直接触发 D4 降级；后续应使用 sensor-specific expected latency、
unexpected OOSM、stale、预算超限和持续窗口联合判定。

本轮只有 seed 7、5 帧、0.4 s，故不能关闭 multi-seed P1。仍需完成：

1. truth-isolated 多 seed 与长时 episode，覆盖正常、时钟异常、延迟突增和 stale 故障对照；
2. batch/watermark 与逐条 replay 两种 OOSM 口径对照，校准 expected-latency budget；
3. D6 长期 schema 对 `SensorHealthSummary`、covariance reason、timestamp uncertainty 和
   region window 的完整性审计；
4. 将真实 Blocks/CV camera/bbox/遮挡与二级侦察 metadata 固化为长期 fixture。

因此当前仍为“无 D1 P0 blocker，truth-isolated 单 seed 接线通过，multi-seed P1 未关闭”。

## 12. M 对 N 协同定位调研同步（2026-07-11）

专项调研见 `subagent_reviews/D1_M_TO_N_COOPERATIVE_LOCALIZATION_REVIEW.md`，覆盖 12 篇主要论文和 Stone Soup、FilterPy、GTSAM、OpenCV 四个官方开源候选。

对于一个高威胁目标由 3 架无人机共同观测的情况，D1 的默认思路是“共同估计时刻上的异步观测融合”，而不是强制三架严格同帧：

```text
各平台 measurement-time pose + bearing/range/bbox covariance
-> NED/time normalization and OOSM propagation
-> D2 confirms same canonical global_track_id
-> D1 joint observation update or conservative CI track fusion
-> GlobalTrack + covariance + geometric quality
```

两条标定良好且不平行的视线在理想条件下即可三角定位，第三架主要增加冗余、改善几何和抗遮挡能力。三条近似平行视线、过短基线或共享偏置仍会退化，因此必须使用 LOS 交会角、联合信息矩阵秩/条件数、重投影残差和平台位姿 covariance 判断质量。

模块边界明确为：D1 负责观测时空标准化、位姿/观测不确定性传播及已关联状态的数值融合；D2 负责跨平台观测/局部航迹关联、canonical `global_track_id` 和 ID continuity。若 D2 不能唯一确认同一目标，D1 必须保持不融合，不能自行重绑定身份。同步到达或分波次拦截属于 D3/D7，D1 只发布预测状态、协方差和几何质量。

调研阶段未新增 P0；其 P1 建议中的协同几何合同和最小 CI 数值原型已按下一节落地，真实三机 replay、D1/D2 双阶段 runtime 合同和离线开源 benchmark 仍保留，不改变既有 P2/P3 外部依赖安排。

## 13. 中心化协同定位 P1 数值基础实现（2026-07-11）

调研后的 D1-owned 最小基础已在独立 `cooperative.py` 路径实现，未改动
`FusionAdapter.process()` 默认行为：

- `ObserverLineage`、`CooperativeBearingObservation`、`CooperativeObservationGroup` 和
  `CooperativeLocalizationSummary` 保留 center-owned canonical `global_track_id`、observer
  lineage、平台位姿/传感器外参 covariance、measurement/arrival timestamp 和共同估计时刻。
- `localize_bearing_observation_group()` 支持任意 observer 数量且至少两条有效 LOS，使用
  NumPy bearing-ray weighted least squares，输出 pairwise 交会角、information rank/condition、
  perpendicular/angular/weighted residual 和 geometry accept/reject reason。
- 几何 helper 对重复 lineage、短基线、近共线、过大 measurement skew、缺失/非法
  covariance、rank/condition 退化和残差超限保守拒绝；显式配置时可对缺失 covariance 使用
  保守默认并标记 inflation。异步 bearing 按目标速度传播到共同估计时刻，并加入
  process/timestamp covariance。
- `covariance_intersection()` 支持 1/2/3/N 个 6-state NED estimate，先做共同时间 CV 传播，
  再以最小 log-det CI 处理未知交叉相关；相同 message UUID 或完整 source lineage 不重复计数，
  输出始终保留输入 canonical ID，不创建或重绑定 ID。

构造性测试已覆盖良好三视角不劣于最佳双视角、退化拒绝、0.4 s 异步传播、1/2/3/N
observer/source、duplicate 不重复收敛、CI 不比错误独立融合更自信及 mixed canonical ID
拒绝。该结论仅是中心化 P1 数值基础，不表示 D2 跨平台关联、main/AirSim runtime、真实
多 seed、部分共享 lineage、成员退出或分布式协同定位全链路已经完成。

## 14. 历史证据、缺口分层与执行次序（2026-07-11 三 seed）

最新 M-to-N AirSim 报告覆盖 seeds 7/17/27：每组均有 6 次重规划请求和 6 次 no-change
ACK，无 applied/expired，需求满足率为 1.0，错误重复锁定为 0；T002 形成 4/5/4 帧共识并
使 D7 每 seed 获得 2 次终端合同许可，T001 双 primary 共识仍为 0。该 ComputerVision
结果只验证 D1 合同能够进入收敛的 M-to-N 状态链，不是物理拦截或真实传感器精度证据。

- P0 无 blocker，当前 D1 回归为 `62 passed`；双时间戳、NED、协方差、质量治理和身份
  lineage 继续作为硬合同。
- P1 已完成的是接口和中心化数值基础；未完成的是 main/D2 runtime 接线、真实 AirSim
  多 seed 协同 replay、故障/遮挡/节点退出、RMSE/NIS/NEES 与持续阈值、模型集和场景
  自适应 covariance 标定、D6 长期 schema。
- T001 双 primary 视觉共识是 D5/D7 的系统 P1；D1 不能通过放宽 covariance 或身份门控
  代替下游闭合。
- FilterPy、Stone Soup、OpenCV/GTSAM 和 ROS 2 均属于 P2 optional benchmark 或后置
  集成，不进入默认路径。

后续先让 main/shared 采用 governed writer 并分离离线 truth，再由 D1/D2 接通 canonical
ID 已确认的 cooperative adapter；随后采集真实多 seed 数据完成统计标定；最后运行第三方
离线对照。实现阶段验收命令保持为
`PYTHONPATH=research_modules/d1_sensor_fusion/src pytest -q research_modules/d1_sensor_fusion/tests`。

## 15. Governed Replay 合同实施复核

D1 已在现有 `ReplayProvenance` 和 record writer 上增加严格批量入口，而没有再造平行观测
类型。`serialize_governed_replay()` 输出 manifest/records，要求 scenario/config ID、version、
digest、seed、coverage cell、双时间戳、NED fusion working frame、covariance 和 source
lineage 完整且可 JSON 序列化。covariance 同时检查维度、有限性、对称性和半正定性。

在线 metadata 的 truth/actor/object 标识会被递归剥离，lineage 改用不暴露真值的观测摘要。
离线评分只能显式调用 `serialize_offline_governed_replay()`，标签固定放在 `offline_truth`。
旧无版本 Blocks JSONL reader 保持兼容，以免破坏历史回放；它不具备 governed manifest 的
完整性保证。

多目标、字段缺失、legacy、truth stripping、双时间戳、covariance 和 lineage 测试均已
通过。该项关闭 D1-owned P1 实现；最新 main episode bus 已采用
serializer，并把在线记录与离线 truth 标签分离。真实 AirSim 传感器精度和长时统计标定仍
需后续验证，但不影响 P1 合同层闭合。

## 16. 当前结论与真实 Replay 后续项（2026-07-11 最终验证）

最终依据为
`research_modules/airsim_runtime/outputs/p1_p2_validation_20260711/P1_P2_VALIDATION_SUMMARY_CN.md`。

1. **P1 合同层闭合**：D1 governed replay、双时间戳、covariance、coverage/lineage 和
   scenario/config provenance 已由 main episode bus 写出；在线记录递归剥离 truth/actor/object
   identity，truth 只写入独立离线标签供评分。
2. **CV 合同验收通过**：10 seeds 中 8/10 达到 T001 双 primary 合同阈值。二级和完全分布式
   3/3 ACK commit 正例通过，缺 ACK 的 2/3 case abort 并 fail-closed。D1 只把这些结果作为
   状态、协方差、时间和 lineage 成功进入下游链路的证据，不承担联盟仲裁或控制职责。
3. **物理拦截未闭合**：SimpleFlight 15 s 仅为诊断，30 个 active pair 均未命中；该结果既
   不是 D1 融合精度验收，也不能替代真实传感器或长时 replay 标定。
4. **P2 仅隔离 benchmark**：可选第三方 adapter/模型不进入默认依赖，不升级或替换 NumPy
   EKF/fixed-lag 主线。

真实 replay 后续项应准确表述为：D1/D2-confirmed cooperative runtime adapter，以及机动、
遮挡、节点退出、camera/bbox、sensor-delay/fault 的更长多 seed 数据；在这些数据上完成
RMSE/NIS/NEES consistency、sensor-specific expected latency、health/region window、模型集
和场景自适应 covariance 标定。governed writer 接入、在线 truth 隔离和 CV 双 primary 合同
验收已完成，不再作为当前缺口。

## 17. P2 隔离滤波对照复核

本轮没有把 FilterPy 或 Stone Soup 接入在线 D1，也没有增加默认依赖。新增的隔离 runner
只读取冻结 governed replay：online records 保持 truth-stripped，双时间戳、covariance、NED
和 lineage 先通过校验，独立 offline truth sidecar 仅用于滤波后的 RMSE/NEES 评分。

当前 NumPy EKF/fixed-lag 路径在六条固定 radar 观测上输出 RMSE `0.2335 m`、mean NIS
`0.0426`、mean NEES `0.0651` 和两次 `6.9-10.1 ms` 主机耗时。该合成样本显示 covariance 偏保守，
只证明 RMSE/NIS/NEES/time 证据链可运行，不构成真实传感器 consistency 验收。当前环境中
`filterpy` 与 `stonesoup` 均不可用；两项结果固定为 `unavailable`，第三方指标为空且包含
`unavailable_reason`，不存在静默回退或伪对照。

后续 P2 只在隔离依赖环境中实现并评估真实 adapter；收益未证明前不得替换默认 NumPy
路径。真实多 seed 的机动、遮挡、节点退出和延迟/故障 consistency 仍是 P1 标定项。本轮
D1 全量回归为 `62 passed`。

## 18. P1 长 Replay 场景与汇总接口（2026-07-12）

D1 已在现有 governed replay 合同上增加独立 `long_replay.py`，供 main 构造长时、确定性的
crossing/遮挡/延迟/OOSM 科研场景。实现没有直连 AirSim，也没有引入新的滤波后端：

```text
LongReplayConfig
  -> build_long_replay_scenario()
  -> truth-free SensorObservation[] + ReplayProvenance
  -> existing governed writer / FusionAdapter
  -> summarize_long_replay()
  -> latency + health + region windows + metric availability

offline truth trajectory/labels
  -> separate d1.long_replay_offline_truth.v1 sidecar
  -> D2/D6 offline scoring only
```

默认场景 60 s、3 个目标在 NED 中交叉，雷达 covariance 随距离增长并在 crossing clutter 窗口
放大；声学只给粗方位和通用 `small_uas` hint；EO 输出像素/camera metadata，并在交叉区间生成
完全和部分遮挡。延迟分布、显式 radar OOSM 与 relay 重发均可按配置调整。

在线 observation ID/source lineage 使用不透明 payload 序号，不编码稳定目标 slot。真值只在
独立 sidecar，`FusionAdapter` 固定 `use_truth_hints_for_association=False`。没有 D2
canonical-ID 离线映射时，RMSE/NEES 以 unavailable reason 输出，避免把无法计算的指标写成
0 或让 truth 反向进入在线航迹。

默认 smoke 输出 843 条观测、21 次显式 OOSM、6 次被去重 relay copy、29 个区域窗口，在线
truth leak 为 0，耗时约 8.8 s。新增测试覆盖版本冻结、covariance/双时间戳/NED/lineage、
在线 truth 隔离、事件触发、汇总 JSON-safe 与同 seed 确定性；加入 CLI 子进程测试后 D1
全量更新为 `66 passed`。

官方 `scripts/run_long_replay.py` 仅封装上述公共 API，支持 seed、duration、target count 和
JSON output path。CLI 输出与 `LongReplaySummary.to_dict()` 完全一致，不读取 offline truth、
不新增关联旁路，并通过真实子进程测试验证参数和输出 schema。

该能力关闭 D1-owned 合成长 replay 与汇总入口，不关闭真实 Blocks/CV multi-seed、
D2-confirmed mapping、真实 RMSE/NIS/NEES、sensor health/window 阈值、camera/bbox/节点退出、
模型集或场景自适应 covariance 缺口。后续 main 应将真实数据按同一 governed schema 写入，
而不是把合成结论当成真实传感器验收。

## 19. 真实 AirSim dense/crossing Replay 冻结复核（2026-07-12）

D1 已补齐不依赖 AirSim SDK 的持久化输入冻结边界。main 可提供 JSON/JSONL 的直接 observation
或包含 observation list 的 frame；D1 按输入长度转换到既有 governed replay，不限制 5-target。
输出包括 manifest、在线 records、evaluator-only truth sidecar 和诊断 summary。

本轮重点强化旧 Blocks 数据的身份隔离：不仅清理 metadata identity key，还将在线
observation ID 不透明化，并清除嵌套字符串中的已知 truth token。processing/publish 时间、
sensor health、scene/profile/source schema 缺失时显式 unavailable；measurement/arrival、
covariance、coverage 和 canonical frame 缺失则拒绝该 observation。遮挡、漏检和节点退出等
无量测事件不生成观测，避免把场景标签伪装成传感器信息。

该接口可作为第二批 D1 -> D2/D6 输入冻结入口。下一步由 main 用真实 AirSim 多 seed 产物调用，
由 D2 使用独立 truth sidecar 离线评分，由 D6 聚合 consistency 和阈值；D1 不承担 AirSim 连接、
目标身份关联或报告评分职责。本轮 D1 全量回归在 sidecar follow-up 后为 `74 passed`。

### 19.1 D2 strict adapter follow-up

sidecar 现以 `(truth_id, timestamp)` 为唯一键。frame truth 的 available position 会覆盖同键
observation metadata identity-only 样本；两个 available 不一致时 freeze 直接失败并给出 key 和
两组位置。不同时间的样本保持独立，仅有 unavailable 的样本保留并计入 summary，绝不生成
估计位置。专项回归覆盖 available-first/unavailable-first、available 冲突和不同时间三类情况。

### 19.2 4 m/2 m 捕获证据治理

AirSim persisted-input freezer 已增加捕获 provenance 强门控。输入必须声明 scenario/config
version、seed、目标间距和 evidence path；D1 将捕获值写入 governed manifest/record provenance
并发布字段 availability。`target_spacing_m` 不从离线 truth 位置估算，调用方声明或多个 payload
声明冲突时直接拒绝。truth 继续只写 evaluator sidecar，sidecar 与在线 manifest 共享 capture
digest。专项测试覆盖 4 m/2 m 各 20 seeds，完整 D1 测试为 `79 passed`。截至本节记录的
2026-07-12 阶段，下一步是由 main 提供符合该合同的真实多 seed 采集，并由 D2/D6 按职责
完成关联与统计；该阶段计划已由下一节的 2026-07-13 证据更新。

### 19.3 真实 40-Episode 收敛结果（2026-07-13）

上一节所述采集已经由 main 完成：4 m/2 m 各 20 seeds，共 40 个真实 AirSim episode；D1
冻结产物对应 10,200 条 evaluator-only truth，在线 truth 泄漏为 0。D2 已进行离线关联标定，
D6 已将 D1 source 标为 `available`。因此当前下一步不再是“补齐 dense crossing 采集”，而是：

1. 采集带真实漏检、匿名虚警、部分/完全遮挡、异步采样率、sensor-specific latency 和节点
   退出的版本化多 seed 长 replay；D1 对无量测事件只记事件，不伪造观测。
2. 用正常/故障对照校准区域时间窗、covariance growth、expected-latency/OOSM、sensor health、
   handover readiness、NIS/NEES 和 `covariance_scale_reason` 的持续阈值。
3. 由 D6 对跨场景、跨 seed、长时运行的 availability、evidence path、health/region window 和
   consistency 指标做长期汇总；缺失指标保持 `unavailable`。

上述事项仍是 P1。Stone Soup、FilterPy、ROS 2、OpenCV/GTSAM 等第三方路径继续保持
P2/P3 可选状态，不能因本次 AirSim 证据写成已经接入。

## 20. 在线 Scene Observation 身份边界评审（2026-07-14）

本轮定位到的 P0 不是“仿真 scene truth 完全不能参与传感器仿真”，而是 scene state 生成
`SensorObservation` 后，原 `observation_id`、source lineage、classification 和嵌套 metadata
仍可能携带目标/actor/object/segmentation 身份。D1 现从包顶层提供：

- `anonymize_online_observations(observations, *, identity_tokens=(), stream_id="online")`；
- `assert_online_observations_identity_free(observations, *, identity_tokens=())`。

前者返回深拷贝匿名观测，按 frame/帧内顺序生成不透明 observation ID，并把原 source lineage
映射为匿名 lineage；同一原 lineage 的 relay duplicate 仍保持同一映射。递归身份键、嵌套
token 和 classification target token 被清理。measurement、covariance、measurement/arrival
双时间戳、sensor/camera geometry 和通信时间不变。后者遍历在线对象并在任何残留身份键或
已知 token 时 fail closed；匿名化函数返回前必经该 validator。

2026-07-14 专项回归用两组各 2 条 EO 观测，仅替换 target/actor/truth 名字，要求匿名结果所有
字段严格相等、数值/相机几何逐元素一致、在线泄漏为 0、注入泄漏全部拒绝，并确认原 observation
和 evaluator-only sidecar 不变。结果专项 `4 passed`，D1 全量 `83 passed`。因此 D1-owned P0
API 缺口关闭；main/runtime 仍须在每个 scene-state 在线入口接线，并通过 `identity_tokens`
补充无法从身份键推断的别名。本轮没有修改 dry-run/offline evaluator、AirSim episode 编排、
D2 身份关联或 D6 评分。

剩余 P1 仍是：真实 sensor-specific challenge 长 replay 和 latency/health 分布、区域/
covariance/NIS/NEES 持续阈值、D1/D2-confirmed 协同融合与 3->2->1 节点退出、D6 跨场景长期
一致性，以及 CV/CA/CT/IMM 和场景自适应 covariance 对照。第三方库继续保持 P2/P3 可选。

## 21. 真实 Episode 重复 Birth/Teleport 专项评审（2026-07-14）

对 `p1_terminal_closure_truthisolated_preflight_v2_20260714_m5n2_baseline_seed001` 的持久化
观测和 main bus 进行只读审计后，D1 侧确认三个相互叠加的问题：同一物理 observer scan 可
重复更新同一航迹；严格雷达门限失败可直接生成重复 birth；fixed-lag 裁剪丢弃了中间滤波后验，
后续回放可能从过旧锚点长时间外推。source lineage 能识别重复 payload，但不能替代匿名目标
关联，因此修复不能依赖 actor/truth ID。

当前实现增加扫描唯一性、唯一近期成熟雷达重捕、模糊 birth 抑制、非测距状态修正审计和
`d1.association_audit.v1`。fixed-lag 检查点放在滞后边界之前最近的已接受量测后验，避免任意
拆分当前过程噪声区间；更早的合法 OOSM 通过 origin/archive 回放。回归明确覆盖同 scan 编号
的跨模态 acoustic 融合，防止 observer-scan 规则误伤。

2026-07-14 验证：专项 `5/5`、D1 全量 `87/87`；main 报告 AirSim runtime `134/134`。
修复后同 M5N2 seed 尚未复跑，所以评审结论是“D1 根因与代码回归已闭合，真实 episode P1
证据仍开放”。下一步仅由 main 复跑并检查航迹数、状态步长和审计原因；D1 后续再基于多 seed
统计校准门限和回放资源预算。

## 22. Covariance 输入合同复核（2026-07-14）

复核确认历史风险来自两条旁路：普通 legacy reader 可产生 `covariance=None`，而
`FusionAdapter` 会用 modality default 替换缺失/非法矩阵。现已统一为正式路径 fail closed：
radar/legacy acoustic/`acoustic_3d`/EO/lidar 分别要求
`4x4/1x1/2x2/2x2/3x3`，并校验有限、对称和半正定；测量模型、
在线融合、governed replay 和 AirSim freeze 不再修复坏输入。

历史兼容被隔离到显式 `migrate_offline_legacy_sensor_observation()`。provenance 固定记录
`explicit_offline_legacy_migration`、原始缺失原因、model/default ID、参数来源和生成输入；
带该标记的 observation 只能供 evaluator 使用，进入在线融合、在线 serializer 或 freezer 会
被拒绝。2026-07-14 无随机 seed 的构造合同用例与既有 replay/OOSM/AirSim freeze 回归全部
通过，D1 全量 `92/92`。

评审结论是 D1-owned covariance 合同硬化缺口已关闭。仍开放的是用真实多 seed 传感器数据
标定 covariance、NIS/NEES consistency、故障/遮挡 scale 和长期阈值；offline migration default
不得作为上述证据。

## 23. 同帧批量 OOSM/Fused Replay 评审（2026-07-14）

main 对最新 M5N2 seed-001 前 40 帧的只读 profile 显示，同一 tick 多模态观测逐条处理会反复
计算同一航迹、同一 measurement time 的历史状态，并在每次接受后重放到 current time。D1
新增正式 `process_batch()`，仍按输入顺序逐条执行 covariance、双时间戳、NED/pixel、source
lineage、scan uniqueness、关联和 OOSM 规则，仅复用相同 history revision 的 state-at-time，
并把发布重放合并到每个 changed track 一次。

批量结果明确区分 `tracks` 批末快照和 `summary` 审计。后者提供 observation/accept/duplicate、
created/updated、affected tracks、history/origin replay、cache hit/miss、finalization replay 和
deferred replay avoidance。`ingest_many()` 保持 arrival 排序兼容并使用该实现；需要每条中间
快照的调用方仍使用 streaming `process()`。

验证日期 2026-07-14。构造场景为 5 航迹/15 条 radar-lidar-acoustic 同帧 observation，
replay 95 -> 24、下降 74.7%，state/covariance 在 `1e-9` 容差内等价。已有 M5N2 baseline
seed-001 前 40 帧共 786 条持久化 observation，逐条 18.05 s/1267 replay，batch
5.70 s/351 replay，3.17 倍加速，state/covariance 最大差 0。专项 `6/6`，D1 全量
`98/98`。

评审结论：D1-owned 批量接口和最少 replay P1 已闭合；main/runtime call site、完整 245/248
帧及多 seed 100 ms loop 验收仍开放。不得将 D1-only persisted replay 的 3.17 倍加速写成系统
实时预算已经达成。Stone Soup、FilterPy、ROS 2 等 P2/P3 状态不变。

## 24. Scalable 3D 扫描级融合评审（2026-07-20）

旧 `process_batch()` 的目标是与逐条流式处理等价，因此同一雷达 scan 仍逐条关联。密集首扫中，
第一条点迹 birth 后，其他近邻点迹可能先命中同航迹的固定门限，再被 observer-scan uniqueness
判为重复；航迹数于是由门限空间 packing 决定，而不是由可分点迹数量决定。该语义必须保留给
历史回归，但不适合作为新三维总线的扫描级起始器。

本轮增加独立 `process_scan_batch()`：所有点迹只与 scan 前航迹比较，使用三维马氏代价和
Hungarian 做一对一匹配，随后让每个未匹配 radar 点迹独立 birth。main 的三维球坐标 covariance
通过解析 Jacobian 传播到 NED 六状态；无径向速度时显式保留未观测速度不确定性。适配器不导入
main 模块，且在读取业务字段前拒绝任何 truth/actor/object/entity/target ID。输出继续使用 D1
六维 `GlobalTrack`，数量不含 2/5/200 常量。

新增 `acoustic_3d` 处理 `[azimuth,elevation]` 与 `2x2` covariance。它是 bearing-only 弱约束，
不能起始三维航迹；soundprint 只保留归一化类别概率，`soundprint_is_identity=False` 被转换为
category-only 治理证据，不参与匹配或稳定 ID。该边界与 cooperative bearing WLS/CI 不同：
本轮没有把单节点声学方位伪装成三维定位，也没有实现跨节点身份确认。

2026-07-20 模块验证使用 seed 7：5/20/50/100/200 各两次扫描，共 750 条匿名 radar
measurement，首扫和次扫均 100% birth/update，200 档保持 200 个 ID；另验证 2 条 delayed
OOSM、5 条 acoustic 无先验 0 birth/有先验 5 update，以及注入 truth/actor/object ID 100%
拒绝。专项 `9/9`、全量 `120/120`。评审结论为 D1-owned scalable scan path 已实现；main bus
接线、D2 六维 continuity、D6 至少 20 个未见 seed 的召回/IDSW/一致性和复杂生命周期仍开放。

## 25. Scalable 3D 六维速度稳定性评审（2026-07-20）

### 25.1 根因与设计判定

main 在 radar-only、seed 17 的 50/200 条链路中观察到 D1/D2 航迹数量完整，但速度均值明显
高于短 episode 的物理运动尺度。D1 复核确认没有显式位置差分代码；放大来自两个统计环节：

1. scalable producer 只提供 `[range, azimuth, elevation]`，旧适配器却把 canonical 补零的
   radial velocity 继续送入四维 EKF，等价于反复声明径向速度为 0；
2. 0.2 s 内真实位移小于单帧球坐标位置噪声，CV 的位置-速度交叉协方差会把短基线噪声写入
   速度后验。速度 covariance 很大，因此这不是“假装高精度”，但下游直接使用均值仍会受影响。

本轮采用统计先验而非硬限速。canonical observation 继续保持 4 维/`4x4` 兼容合同，但
`radial_velocity_observed=False` 时滤波只消费前三维；起始状态使用 `v0=0`、
`Pvv=25I m2/s2`、`Ppv=0`。该方差与 3 自由度 99.9% NIS 门限均公开可配置，不读取 truth、
actor/object ID、`target_speed_max_mps` 或 4.7 m/s 上界。

### 25.2 门控、OOSM 与审计

位置-only radar 的更新门限为 `chi2_3(0.999)=16.26623619623813`。超门限量测不修改预测状态，
但仍保留 observation history 和原始双时间戳，使后续 replay 在相同 measurement-time 顺序下
确定地得到同一拒绝结果。航迹 metadata 显式记录 `latest_replay_innovation_count`、实际 filter
update 数、gate rejection 数和匿名 observation IDs。构造用例让离群点仍在扫描关联门限 40
之内，以证明拒绝发生在滤波创新层，而不是通过新建/丢失航迹绕开。

### 25.3 证据与边界

2026-07-20 自动化场景如下：

- 一个无多普勒 radar 样本验证 3 维滤波模型、零均值速度和 `25I` 方差；
- 一个 3 scan 离群序列验证 1 次创新拒绝及全部审计字段；
- 两条航迹的顺序/乱序 3 scan 对照验证 2 条 OOSM，state/covariance 容差 `1e-9`、双时间戳和
  `6x6` covariance；
- seed 17、200 条、10 scan、2,000 条匿名 radar measurement，数量和 ID 全程为 200，末帧
  速度 median/P90/max=`3.87/6.43/8.54 m/s`，速度 covariance trace=
  `57.97/60.69/61.19`。

专项 `13/13`，D1 全量 `124/124`。50 条开发探针从 `6.28/12.16/21.03` 改善为
`3.99/6.12/9.69 m/s`，但 trace 仍为 `58.22/60.43/60.90`，所以评审结论是 D1-owned
噪声放大缺口已关闭、短基线速度仍是高不确定度估计。至少 20 个未见 seed 的 NIS/NEES 和
coverage、机动/漏检/虚警、D2 二次滤波与 D3 分配正式复验仍开放。本轮不影响 AirSim 文档。
