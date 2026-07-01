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

默认选型：ROS 2 管消息和坐标，Stone Soup 做中心融合研究原型，FilterPy 用于小模块或单元测试验证。

---

## 4. 子系统方案

### 4.1 统一数据结构

```text
SensorObservation
- observation_id
- sensor_id
- modality: radar | acoustic | eo
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
- timestamp
- track_state: tentative | confirmed | engageable | lost | dropped
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
| `coarse_track` | `a95 > T_s` 或仅短时单源支持 | 告警、继续观测、请求补充传感器 |
| `stable_track` | 连续多帧NIS通过，`a95 <= T_s` | 进入中心关联和资源分配候选 |
| `handover_track` | `a95 <= T_h` 且多源一致 | 可交给末端配准或显示，不等价于处置授权 |

---

## 6. 测试矩阵

| 测试 | 输入 | 期望结果 |
|------|------|----------|
| 雷达延迟 | 固定延迟点迹 | OOSM补偿后RMSE下降 |
| 距离变化 | 近中远三档雷达点迹 | 协方差随距离合理放大 |
| 声学粗方位 | 大角度不确定观测 | 只收窄方位，不强行定位 |
| 光电像素框 | 小框、遮挡、低置信度 | `R`放大，避免误配准 |
| 坐标错误 | 错误外参版本 | 触发质量告警，不发布高置信航迹 |

---

## 7. 交付物

1. 文献综述：时间同步、坐标转换、协方差自适应建模。
2. 开源选型表：Stone Soup、FilterPy、ROS 2 tf2、message_filters。
3. 数据结构：`SensorObservation`、`CanonicalDetection`、`GlobalTrack`。
4. 接口伪代码：`FusionAdapter`、`DelayCompensator`、`TrackFilter`。
5. 雷达误差分档：`coarse_track`、`stable_track`、`handover_track`。

---

## 8. 参考资料

- Stone Soup: <https://github.com/dstl/Stone-Soup>
- Stone Soup documentation: <https://stonesoup.readthedocs.io/>
- FilterPy: <https://filterpy.readthedocs.io/>
- ROS 2 tf2: <https://docs.ros.org/en/rolling/Concepts/Intermediate/About-Tf2.html>
- ROS 2 message_filters: <https://docs.ros.org/en/humble/p/message_filters/doc/Tutorials/Approximate-Synchronizer-Cpp.html>
- REP-103 coordinate conventions: <https://www.ros.org/reps/rep-0103.html>
- REP-105 coordinate frames: <https://www.ros.org/reps/rep-0105.html>
