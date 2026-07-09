# D1 多传感器融合与目标配准综述及子方案

**定位**: 雷达、声学、光电异构观测进入统一融合链路，输出带协方差、时间戳和状态机的 `GlobalTrack`。  
**边界**: 本文仅用于科研仿真、态势感知和人工复核接口设计，不包含真实火控参数、毁伤参数、自动处置控制律或绕过人工授权的流程。

---

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

### 6.4 当前已完成和仍需补充的工程改进

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

当前 P0 状态：无 P0 blocker。D1 已实现并回归 measurement/arrival timestamp、协方差、NED `GlobalTrack`、N-target 输入和 `ReconCueSummary` 侦察 cue 合同；剩余工作均为 P1/P2 增强或外部 fixture/schema 对齐。

2026-07-08 main/D6 集成状态：main runtime 已新增 P1 D4/D5 calibration sweep，并在 sweep 后自动生成 D6 标准报告 bundle。D1 不负责启动 AirSim sweep、episode reset 或报告 bundle，只负责保证 `SensorObservation` replay、`GlobalTrack`、`TrackUncertaintySummary`、`LatencyAuditSummary`、`FusionQualityRegionSummary[]`、`FusionQualityRegionWindowSummary[]`、`SensorHealthSummary[]`、covariance reason 和 timestamp uncertainty 字段可被 main/D6 稳定消费。

剩余 P1：

1. **D6 长期批量 schema**：需要把 `TrackUncertaintySummary[]`、`LatencyAuditSummary`、`FusionQualityRegionSummary[]`、`FusionQualityRegionWindowSummary[]`、`SensorHealthSummary[]`、covariance reason 和 timestamp uncertainty 整理成 D6 可长期回归的稳定 JSONL/CSV schema，并确保 D6 calibration bundle 中的字段命名长期稳定。
2. **真实 Blocks/CV fixture**：D1 已能读 `blocks_sensor_observations.jsonl`/`sensor_observations.jsonl` 和 covariance-required CSV，并已有 Blocks calibration CSV、真实 CV 字段保真、covariance scale reason、secondary/mobile recon cue metadata 和 dry-run fixture schema 回归；仍需要更多来自 main/shared runtime 的真实 AirSim multi-seed CV detection 字段样本，避免只覆盖 dry-run/手工结构。
3. **真实样本阈值**：区域窗口、freshness/source-gap、协方差增长率和 handover readiness 的持续阈值仍需 main 真实多 seed fixture 与 D6 统计共同校准。

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
