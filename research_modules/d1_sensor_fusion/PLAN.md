# D1 多传感器融合与目标配准实施计划

## 0. 边界与用途

本模块仅用于科研仿真、离线评估和算法可复现实验。输出为带协方差的 `GlobalTrack`，用于态势估计、误差分析和人工复核接口设计。模块不包含真实火控参数、毁伤逻辑、实机飞控或硬件驱动、自动处置流程，也不包含绕过人工授权的控制接口。

## 1. 工程问题与科学问题

工程问题：

- 将雷达、声学、光电三类异构观测标准化为统一 `SensorObservation`。
- 以 `measurement_timestamp` 为滤波更新时间，以 `arrival_timestamp` 记录链路延迟和乱序到达。
- 保留跨节点通信元数据，如 `source_node_id`、`target_node_id`、`relay_node_id`、`link_type`、`sent_timestamp`、`received_timestamp`、`payload_kind`、`stale_after_s` 和 `source_support`。
- 在统一 NED 坐标下维护 `GlobalTrack`，输出状态、协方差、质量等级和传感器支持。
- 对延迟雷达观测进行 fixed-lag 缓存、测量时刻更新和重传播，比较补偿前后误差。
- 在没有 FilterPy、Stone Soup 依赖时，提供可运行的 NumPy/SciPy fallback。

科学问题：

- 距离相关雷达噪声、粗方位声学观测、二维 EO 像素框约束如何共同约束三维运动状态。
- 延迟观测按到达时刻更新与按测量时刻更新并重传播之间的误差差异。
- 协方差传播、NIS 门限、连续性和多源支持如何形成 `coarse`、`stable`、`handover` 分级判据。

## 2. 状态与运动模型

统一滤波状态为：

```text
x = [px, py, pz, vx, vy, vz]^T
```

其中位置和速度均在 NED 坐标系中表达，单位为米和米每秒。

CV 常速度模型作为默认可运行基线：

```text
x_k = F_cv(dt) x_{k-1} + w
F_cv = [[I3, dt I3],
        [03, I3]]
Q_cv = q * [[dt^4/4 I3, dt^3/2 I3],
            [dt^3/2 I3, dt^2 I3]]
```

CA 常加速度模型用于仿真目标生成或后续模型扩展。当前六维状态中不显式估计加速度，CA 通过已知或采样加速度驱动真值轨迹；若后续切换到九维状态，可扩展为 `[p, v, a]`。

转弯模型用于二维水平面协调转弯真值生成或 IMM 扩展。六维滤波 fallback 仍以 CV 预测吸收机动误差；转弯强度通过过程噪声放大表达。

## 3. 观测模型

雷达观测：

```text
z_radar = [range, azimuth, elevation, radial_velocity]^T
```

从雷达位置 `s` 指向目标相对向量 `r = p - s`：

```text
range = ||r||
azimuth = atan2(ry, rx)
elevation = atan2(-rz, sqrt(rx^2 + ry^2))
radial_velocity = dot(v, r / ||r||)
```

雷达协方差随距离增大：

```text
sigma_range = a0 + a1 * range
sigma_angle = b0 + b1 * range / reference_range
sigma_radial_velocity = c0 + c1 * range / reference_range
```

声学观测：

```text
z_acoustic = [azimuth]^T + optional voiceprint/classification_hint
```

声学只作为粗方位约束和身份似然提示，不强制恢复三维位置。观测模型为 `atan2(ry, rx)`，协方差由阵列条件、信噪比和置信度控制。

光电 EO 观测：

```text
z_eo = [u_center, v_center]^T
```

像素框中心经相机内参和外参对应到成像投影：

```text
p_camera = R_world_to_camera * (p_world - camera_position)
u = fx * x/z + cx
v = fy * y/z + cy
```

EO 用作方向/投影约束。小框、低置信度或遮挡时增大像素协方差，避免把二维检测误当三维真值。

## 4. 协方差传播与延迟补偿

预测传播：

```text
x^- = F x
P^- = F P F^T + Q
```

EKF 更新：

```text
y = wrap(z - h(x^-))
S = H P^- H^T + R
K = P^- H^T S^-1
x^+ = x^- + K y
P^+ = (I - K H) P^- (I - K H)^T + K R K^T
```

延迟补偿使用 fixed-lag 状态缓存：

1. 观测到达后按 `measurement_timestamp` 找到对应或最近早于该时刻的缓存状态。
2. 从缓存状态预测到测量时刻并更新。
3. 将更新后的状态按缓存中的后续时间步逐段重传播到当前融合时间。
4. 与未补偿基线对比，后者直接在 `arrival_timestamp` 对当前状态更新。

## 5. 分级判据

基于水平 95% 误差椭圆长轴：

```text
a95 = sqrt(chi2_2_0.95 * max_eigenvalue(P_xy))
```

默认判据：

- `coarse`: `a95 > stable_threshold`，或观测支持不足，或连续性不足。
- `stable`: `a95 <= stable_threshold`，最近窗口内 NIS 通过率达标，且 track continuity 达标。
- `handover`: `a95 <= handover_threshold`，多源一致，连续稳定帧数达到要求。

`handover` 仅表示科研仿真中的高质量配准状态，不代表处置授权。

## 6. 仿真场景

- 时长 60 s，基准频率 10 Hz。
- `--drone-count 3` 保留为历史 baseline；集成运行由 main 的 `--drone-count N` 统一控制目标数量。
- D1 接收 main 提供的 N 个 target truth/观测源，并按输入数组长度处理，不在算法路径写死 2 或 5。
- 目标数为 N，循环覆盖 CV、CA 和水平转弯轨迹。
- 雷达：0.5-2.0 s 随机延迟，10 Hz 或降采样观测，噪声方差随距离增大。
- 声学：粗方位观测，低频率，带声纹/类别提示。
- EO：像素框中心观测，带相机内参、外参、置信度和遮挡/小框噪声放大。
- 输出 RMSE、航迹连续性、分级准确性、延迟补偿前后对比图和 Markdown 报告。

## 7. 模块接口

核心数据结构：

- `SensorObservation`: 统一观测，包含 `measurement_timestamp` 和 `arrival_timestamp`。
- `GlobalTrack`: 全局航迹，包含六维状态、6x6 协方差、时间戳、等级和源支持。
- `FusionAdapter`: 融合入口，提供 `predict_track()`、`update_at_measurement_time()`、`compensate_latency()`、`_bucket()`。

运行入口：

- `src/d1_sensor_fusion/simulation.py`: 离线仿真与指标生成。
- `scripts/run_simulation.py`: 命令行仿真脚本。
- `tests/`: 单元测试和回归测试。

兼容接口：

- FilterPy: 仅作为后续可选后端，不作为当前运行依赖。
- Stone Soup: 提供占位适配器和转换接口说明，不导入未安装包。
- AirSim: 只提供仿真集成计划和离线观测适配建议，不包含实机飞控或自动处置控制。

## 8. 交付物

- `PLAN.md`: 本实施计划。
- Python 源码：数据结构、运动模型、观测模型、EKF、融合适配器、仿真和指标。
- 单元测试：RMSE、track continuity、分级准确性、延迟补偿前后对比、接口行为。
- 仿真脚本：按 `--drone-count N` 生成 N 个目标、60 s、10 Hz 的雷达/声学/EO 观测；历史 3 目标输出仅作为 baseline。
- 图表和 Markdown 实验报告：输出到 `reports/`。
- AirSim 集成计划：统一时间轴、坐标、传感器桥接和离线评估流程。
