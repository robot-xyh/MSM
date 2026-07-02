# D1 多传感器融合与目标配准算法与实施说明

## 1. 模块定位

D1 负责把异步雷达、声学和光电观测统一成带协方差的 `GlobalTrack`。它是后续 D2 数据关联、D3 资源分配、D5 末端投影配准和 D6 指标统计的输入源。模块仅用于离线科研仿真和算法评估，不包含真实飞控、硬件驱动、火控、毁伤、自动处置或绕过授权的内容。

当前实现采用 NumPy EKF fallback，保留 FilterPy 和 Stone Soup 的可选适配位置。所有融合状态均在本地 NED 坐标系中维护，WGS84、ENU、传感器坐标和像素坐标应在传入融合器前完成标准化或带齐外参元数据。

## 2. 输入输出

### 2.1 输入：`SensorObservation`

统一观测结构位于 `src/d1_sensor_fusion/types.py`，关键字段为：

- `observation_id`：观测唯一编号。
- `sensor_id`：传感器编号，如 `radar_ground_01`。
- `modality`：`radar`、`acoustic` 或 `eo`。
- `measurement_timestamp`：传感器实际采样时刻。
- `arrival_timestamp`：融合节点收到观测的时刻。
- `frame_id`：当前实现要求雷达/声学为 `ned`，EO 为 `pixel`。
- `measurement`：传感器量测向量。
- `covariance`：量测协方差，缺省时由观测模型按距离、置信度或框大小生成。
- `classification_hint`、`confidence`、`quality_flags`：分类提示、置信度和遮挡/小框等质量标记。
- `metadata`：传感器位置、相机内外参、bbox、仿真真值 ID 等辅助信息。

### 2.2 输出：`GlobalTrack`

输出航迹为六维 NED 状态：

```text
x = [px, py, pz, vx, vy, vz]^T
```

`GlobalTrack` 同时携带 `6x6` 协方差、`track_level`、`source_support`、`identity_likelihood` 和元数据。`metadata.frame_id="ned"` 表示融合工作空间，`valid_at` 表示航迹状态有效时刻，`published_at` 表示当前发布时刻。

## 3. 时间基准与 OOSM 处理

D1 强制区分两个时间戳：

- `measurement_timestamp` 是物理测量发生的时间，应进入滤波更新方程。
- `arrival_timestamp` 是消息到达融合器的时间，只用于日志排序、延迟统计和 fixed-lag replay 触发。

延迟或乱序观测即 OOSM。当前 `FusionAdapter.compensate_latency()` 的处理流程为：

1. 观测按 `arrival_timestamp` 到达。
2. 选择或创建对应航迹。
3. 将观测插入该航迹的历史观测列表。
4. 按 `measurement_timestamp` 对观测重新排序。
5. 从初始状态开始，逐条预测到量测时刻并 EKF 更新。
6. 将更新后的状态重传播到当前 `arrival_timestamp`。
7. 输出当前时刻的 `GlobalTrack`。

若关闭 `latency_compensation`，系统会把量测时刻替换为到达时刻，用作消融基线。现有实验中，延迟补偿后 RMSE 明显低于不补偿基线。

## 4. 坐标转换链路

D1 的融合工作空间是 NED：

```text
x: north
y: east
z: down
```

推荐坐标链路如下：

- WGS84：外部地理坐标，仅用于接口互操作。
- ENU：部分仿真或 ROS 工具常用的本地切平面坐标。
- NED：D1 内部滤波、输出和跨模块合同坐标。
- `sensor_frame`：雷达、声学阵列或相机自身坐标。
- `pixel`：EO 图像平面坐标。

工程约定：

1. 雷达和声学桥接器先把传感器位置、姿态和量测方向转换到 NED，再生成 `frame_id="ned"` 的观测。
2. EO 观测保留为像素框中心 `frame_id="pixel"`，但必须在 `metadata` 中提供相机内参、相机 NED 位置和 `rotation_world_to_camera`。
3. 若输入来自 WGS84，应先固定局部原点，转换为本地 ENU，再按轴定义转换到 NED。
4. 不允许把像素框、声学方位或单次雷达点直接当作三维真值；它们只能通过观测模型和协方差影响航迹。

## 5. 传感器观测模型

### 5.1 雷达

雷达量测为：

```text
z_radar = [range, azimuth, elevation, radial_velocity]^T
```

相对向量 `r = p - s`，其中 `p` 为目标 NED 位置，`s` 为雷达 NED 位置：

```text
range = ||r||
azimuth = atan2(ry, rx)
elevation = atan2(-rz, sqrt(rx^2 + ry^2))
radial_velocity = dot(v, r / ||r||)
```

当前代码的距离相关协方差原则为：

```text
sigma_range = 2.0 + 0.012 * range
sigma_azimuth = deg2rad(0.25 + 0.0008 * range)
sigma_elevation = deg2rad(0.35 + 0.0010 * range)
sigma_radial_velocity = 0.35 + 0.0015 * range
```

含义是：距离越远，距离、角度和径向速度不确定性越高。雷达是当前唯一可初始化新航迹的传感器，因为它能提供三维几何和径向速度骨架。

### 5.2 声学

声学量测为粗方位：

```text
z_acoustic = [azimuth]^T
azimuth = atan2(ry, rx)
```

声学观测只约束方位，不恢复三维距离。其协方差由置信度控制：

```text
sigma_deg = 2.5 + 8.0 * (1 - confidence)
```

声学的主要作用是低频补充、类别/声纹提示和多源支持计数。工程上应把声学视为弱证据，不能单独把 `coarse_track` 升级为可交接航迹。

### 5.3 光电 EO

EO 量测为像素中心：

```text
z_eo = [u_center, v_center]^T
p_camera = R_world_to_camera * (p_ned - camera_position_ned)
u = fx * x / z + cx
v = fy * y / z + cy
```

EO 协方差由检测框大小、置信度和质量标记决定：

- bbox 越小，像素中心误差越大。
- `confidence` 越低，协方差越大。
- `occluded`、`small_bbox` 会进一步放大协方差。

EO 是强方向约束，但不是直接三维位置观测。它适合降低横向不确定性，并为 D5 末端投影配准提供一致的几何基础。

## 6. 滤波算法原理

### 6.1 默认运动模型

当前滤波状态为六维常速度模型：

```text
x_k = F(dt) x_{k-1} + w
F = [[I3, dt I3],
     [03, I3]]
```

过程噪声为白加速度谱密度近似：

```text
Q = q * [[dt^4/4 I3, dt^3/2 I3],
         [dt^3/2 I3, dt^2 I3]]
```

仿真真值可以包含常加速度和协调转弯，但滤波器仍以 CV 作为稳健基线，通过调大 `process_noise` 吸收机动误差。

### 6.2 EKF 更新

各传感器观测模型均为非线性或局部非线性，因此采用 EKF：

```text
x^- = F x
P^- = F P F^T + Q
y = wrap(z - h(x^-))
S = H P^- H^T + R
K = P^- H^T S^-1
x^+ = x^- + K y
P^+ = (I - K H) P^- (I - K H)^T + K R K^T
```

代码使用数值雅可比和 Joseph 形式协方差更新，以提升原型实现的稳定性。角度残差使用 wrap 处理，避免 `pi/-pi` 跳变导致错误创新。

### 6.3 EKF、UKF、IMM 选型边界

当前默认 EKF 的理由：

- 状态维度低，观测模型清晰，数值雅可比足以覆盖研究原型。
- 计算量小，便于批量实验和 D6 指标统计。
- 雷达/声学/EO 的非线性强度可通过合理初始化和协方差放大控制。

建议升级边界：

- UKF：当 EO 投影角度极端、雷达近距离非线性明显，或数值雅可比敏感时使用。
- IMM-EKF/IMM-UKF：当目标频繁切换匀速、加速、转弯模型，且 D2 关联质量受运动模型影响明显时使用。
- 粒子滤波：仅适合强非高斯、多模态不确定性研究，不建议作为当前默认路径。

## 7. 航迹分级

D1 输出 `coarse`、`stable`、`handover` 三类研究质量等级。分级不是授权状态，只是给后续模块做质量门控。

核心不确定性指标为水平 95% 误差椭圆长轴：

```text
a95 = sqrt(chi2_2_0.95 * max_eigenvalue(P_xy))
```

当前工程判据：

- `coarse_track`：初始化初期、`a95` 大于稳定门限、观测支持不足或 NIS 通过率较低。
- `stable_track`：`a95 <= stable_threshold_m`，命中次数达到要求，NIS 通过率基本合格。
- `handover_track`：`a95 <= handover_threshold_m`，至少两类传感器支持，命中次数更多，NIS 通过率更高。

默认参数在 `FusionAdapter` 中：

- `stable_threshold_m = 30.0`
- `handover_threshold_m = 12.0`
- `association_gate = 40.0` 或仿真脚本中 `45.0`
- `buffer_horizon = 6.0`
- `bucket_size = 0.1`

## 8. 面向 D4 主动降级的不确定度信号

D4 的主动降级不是由中心节点失效触发，而是由态势质量不足触发：中心节点仍可运行，但全局定位分辨率、时间新鲜度或多源一致性已经不足以支撑稳定集中式分配。D1 应向 D3/D4/D5 提供可解释的不确定度摘要，使系统在离线仿真中能区分“节点坏了”和“中心态势仍在但质量不够好”。

### 8.1 D1 可提供的核心信号

D1 侧可从 `GlobalTrack` 和近期观测历史派生以下信号：

- 位置协方差迹 `position_cov_trace = trace(P_xyz)`：衡量三维位置总体不确定度。
- 水平协方差椭圆 `a95_xy`：由 `P_xy` 最大特征值计算，适合表达平面定位分辨率。
- 垂向不确定度 `sigma_z = sqrt(P_zz)`：用于区分水平可用但高度不稳定的航迹。
- 速度协方差迹 `velocity_cov_trace = trace(P_vxvyvz)`：衡量预测未来接近窗口时的不确定度。
- 量测延迟 `measurement_latency = published_at - last_measurement_timestamp` 或单观测 `arrival_timestamp - measurement_timestamp`：用于判断观测是否已经落后于分配周期。
- 连续外推时长 `extrapolation_age = published_at - valid_at`：表示当前发布航迹距离最近有效滤波时刻的时间差。
- 轨迹桶 `track_bucket = floor(valid_at / bucket_size)`：用于 D3/D4 判断不同航迹摘要是否属于同一时间离散窗口。
- 航迹等级 `track_level`：`handover`、`stable`、`coarse` 的质量门控结果。
- 多源支持 `source_support`：雷达、声学、EO 最近窗口内的支持数量和比例。
- 观测一致性 `last_nis` 或 NIS 通过率：雷达、EO、声学与预测状态是否一致的统计证据。
- 降级趋势 `track_level_drop`：从 `handover` 退到 `stable/coarse`，或从 `stable` 退到 `coarse`。

这些信号不包含处置指令，只描述定位质量、时间新鲜度和多源一致性。

### 8.2 `TrackUncertaintySummary` 建议结构

建议 D1 在后续接口中为每条 `GlobalTrack` 生成摘要，作为 D3 代价函数和 D4 主动降级判断的输入。示例字段如下：

```python
TrackUncertaintySummary(
    global_track_id: str,
    valid_at: float,
    published_at: float,
    track_bucket: int,
    track_level: str,
    position_cov_trace: float,
    velocity_cov_trace: float,
    a95_xy_m: float,
    sigma_z_m: float,
    covariance_growth_rate: float | None,
    measurement_latency_s: float,
    extrapolation_age_s: float,
    source_support: dict[str, int],
    source_diversity_count: int,
    last_nis: float | None,
    nis_pass_rate: float | None,
    handover_readiness: float,
    quality_flags: tuple[str, ...],
)
```

字段计算建议：

- `valid_at` 取 `GlobalTrack.metadata["valid_at"]`，缺省时取 `GlobalTrack.timestamp`。
- `published_at` 取 `GlobalTrack.metadata["published_at"]`，缺省时取当前回放时刻。
- `track_bucket = FusionAdapter._bucket(valid_at)`，用于跨模块对齐同一决策周期。
- `position_cov_trace = trace(covariance[:3, :3])`。
- `velocity_cov_trace = trace(covariance[3:, 3:])`。
- `a95_xy_m` 使用 D1 现有 `covariance_a95()` 逻辑。
- `sigma_z_m = sqrt(covariance[2, 2])`。
- `measurement_latency_s` 优先取最近观测的 `arrival_timestamp - measurement_timestamp`，只有航迹摘要时可退化为 `published_at - valid_at`。
- `covariance_growth_rate` 可用最近两个摘要的 `position_cov_trace` 差分除以时间差。
- `source_diversity_count` 统计最近窗口中非零支持的传感器类型数。
- `handover_readiness` 建议归一化到 `[0, 1]`，由 `a95_xy_m`、`source_diversity_count`、`track_level`、NIS 通过率和延迟共同计算。

一个保守的 `handover_readiness` 原型可定义为：

```text
readiness = min(
    clamp(handover_threshold_m / max(a95_xy_m, eps), 0, 1),
    clamp(latency_budget_s / max(measurement_latency_s, eps), 0, 1),
    source_diversity_score,
    nis_consistency_score,
    level_score
)
```

其中 `level_score` 可令 `handover=1.0`、`stable=0.6`、`coarse=0.2`。该指标只用于科研仿真中的质量门控，不代表授权状态。

### 8.3 主动降级触发信号

以下情况说明中心节点仍在线，但中心态势质量可能不足，D4 可考虑从集中式分配切换到二级节点区域协同，或在更差条件下降级为分布式协同：

- 协方差突增：`position_cov_trace` 或 `a95_xy_m` 在短窗口内快速增加，例如超过上一窗口的 1.5-2.0 倍。
- 连续外推过长：`extrapolation_age_s` 超过 D3 分配周期，说明当前发布航迹主要靠预测维持。
- 延迟超过分配周期：`measurement_latency_s > assignment_period_s`，集中式分配可能基于过期态势。
- 速度不确定度过高：`velocity_cov_trace` 增大，导致 D3 的接近窗口预测不稳定。
- 多源不一致：雷达与 EO 的创新/NIS 长时间偏高，或同一目标在不同传感器下的残差方向系统性偏离。
- 航迹等级回退：关键目标从 `handover` 回退到 `stable/coarse`，或 `stable` 回退到 `coarse`。
- 传感器支持退化：`source_diversity_count` 从多源降到单源，尤其是 EO 或雷达连续缺失。
- 空域局部质量不均：中心全局仍可用，但某个 `coverage_cell` 内多数航迹 `handover_readiness` 偏低，此时更适合交给该区域二级节点重新融合和协调。

主动降级应使用迟滞和持续时间约束，避免单帧噪声导致频繁切换。建议 D4 在仿真中采用：

```text
active_degrade = bad_quality_ratio >= ratio_threshold
                 and median_duration >= min_hold_time
                 and affected_tracks include high_priority_tracks
```

其中 `bad_quality_ratio` 可按区域或全局统计 `handover_readiness < readiness_threshold` 的航迹比例。恢复集中式模式也应满足更严格的恢复门限，例如连续多个周期 `readiness` 回升并且延迟低于预算。

### 8.4 面向 D3/D4/D5 的使用方式

D3 使用方式：

- 将 `a95_xy_m`、`position_cov_trace`、`velocity_cov_trace` 加入分配代价，避免对高不确定目标做频繁重分配。
- 当 `track_bucket` 落后于当前分配周期时，提高该目标代价或保持原分配。
- 当 `handover_readiness` 降低但未触发 D4 降级时，增加分配迟滞，减少抖动。

D4 使用方式：

- 以区域为单位聚合 `TrackUncertaintySummary`，判断是全局主动降级还是局部交给二级侦察节点。
- 区分被动降级与主动降级：被动降级来自心跳/节点状态；主动降级来自 D1 不确定度、D3 重分配失败反馈和 D5 末端配准反馈。
- 中心仍在线但某区域 `measurement_latency_s`、`a95_xy_m`、`handover_readiness` 长时间不达标时，优先切换到覆盖该区域的二级节点。
- 若二级节点也无法提供新鲜观测或局部摘要，则再进入完全无中心的分布式协同。

D5 使用方式：

- 用 `a95_xy_m` 和完整协方差传播到图像平面，决定终端投影门限大小。
- 当 `handover_readiness` 低或航迹等级回退时，终端应倾向 `ambiguous/hold/reacquire`，而不是自行改写 `global_track_id`。
- D5 的 `TerminalAssociation` 反馈可回传 D1/D4，作为“中心预测与局部视觉不一致”的辅助信号。

### 8.5 给 D4 的接口建议

D1 到 D4 的建议消息可按周期发布，粒度为“单航迹摘要 + 区域聚合摘要”：

```python
TrackUncertaintySummary[]  # 每条航迹
FusionQualityRegionSummary(
    coverage_cell: str,
    published_at: float,
    track_count: int,
    median_a95_xy_m: float,
    p90_a95_xy_m: float,
    stale_track_ratio: float,
    handover_ready_ratio: float,
    multi_source_ratio: float,
    active_degrade_recommendation: str,  # "none" | "secondary_node" | "distributed_review"
    reasons: tuple[str, ...],
)
```

`active_degrade_recommendation` 只表达态势质量建议，不直接改变任务状态。D4 应结合自身 `C2Health`、D3 分配版本、D5 末端反馈和人工授权状态后再决定降级模式。

## 9. 主要实施流程

离线融合主流程：

1. 传感器桥接器生成 `SensorObservation`。
2. 观测按 `arrival_timestamp` 回放。
3. `FusionAdapter.process()` 预测所有航迹到当前到达时刻。
4. `_associate()` 计算观测与现有航迹的马氏距离/NIS 分数。
5. 雷达观测可触发 `_create_track()` 初始化新航迹。
6. 已有关联调用 `compensate_latency()` 在测量时刻更新并重传播。
7. `_classify()` 根据协方差、多源支持、hits 和 NIS 生成质量等级。
8. `global_tracks()` 发布当前 `GlobalTrack` 列表。

关键代码位置：

- `src/d1_sensor_fusion/types.py`：输入输出数据结构。
- `src/d1_sensor_fusion/observations.py`：雷达、声学、EO 观测模型和协方差。
- `src/d1_sensor_fusion/ekf.py`：EKF 预测、更新和数值雅可比。
- `src/d1_sensor_fusion/fusion.py`：融合适配器、延迟补偿、关联、分级和不确定度摘要的建议来源。
- `src/d1_sensor_fusion/simulation.py`：离线质点仿真、图表和报告生成。

## 10. 参数与调参建议

- `process_noise`：机动越强取值越大。过小会导致转弯目标滞后，过大会导致协方差膨胀和分级保守。
- `association_gate`：越大越容易关联，越小越容易新建或漏关联。D1 只做基础关联，密集交叉场景应交给 D2。
- `stable_threshold_m`：影响 `stable` 输出数量。若 D3 需要更保守输入，可降低该值。
- `handover_threshold_m`：影响交接质量。该值不应被解释为行动授权，只代表几何和协方差质量。
- `buffer_horizon`：必须覆盖最大预期观测延迟。若雷达延迟上限为 2 s，建议留 4-6 s。
- 雷达协方差：根据仿真距离、杂波、遮挡或信噪比调大，不要为了降低 RMSE 人为压小。
- EO 协方差：小目标、逆光、遮挡、截断框应增加像素协方差。
- 声学协方差：声源混叠、风噪或低置信度时应显著放大。
- 主动降级门限：建议先用 D6 批量实验确定 `a95_xy_m`、`measurement_latency_s`、`handover_readiness` 的经验分位数，再设置区域级迟滞门限。

## 11. 仿真验证与图表

当前仿真入口：

```bash
PYTHONPATH=research_modules/d1_sensor_fusion/src \
python3 research_modules/d1_sensor_fusion/scripts/run_simulation.py \
  --targets 3 \
  --duration 60 \
  --dt 0.1 \
  --seed 7 \
  --output research_modules/d1_sensor_fusion/reports
```

实验覆盖：

- 1-3 个目标，包含常速度、转弯和轻机动。
- 雷达 0.5-2.0 s 延迟，协方差随距离增长。
- 声学粗方位和声纹式分类提示。
- EO 像素框投影和 bbox/置信度相关协方差。
- 延迟补偿与不补偿两条基线对比。

现有实验报告和图表：

- `reports/EXPERIMENT_REPORT.md`
- `reports/tracks_xy.png`
- `reports/rmse_latency_ablation.png`

主要指标：

- `compensated_rmse_m`
- `uncompensated_rmse_m`
- `track_continuity`
- `grading_accuracy`
- `observation_count`
- `mean_radar_latency_s`

建议后续为主动降级增加指标：

- `median_a95_xy_m`
- `p90_a95_xy_m`
- `stale_track_ratio`
- `handover_ready_ratio`
- `active_degrade_event_count`
- `active_degrade_lead_time_s`

## 12. 跨模块接口关系

- D2：消费 D1 的 `GlobalTrack`，进一步执行多目标数据关联和稳定 `global_track_id` 管理。D1 的基础关联不替代 D2 的 GNN/JPDA/MHT。
- D3：使用 `state`、`covariance`、`track_level` 和威胁/质量字段构造分配代价。高协方差航迹应提高分配惩罚。
- D4：消费 D1 的 `TrackUncertaintySummary` 和区域质量摘要，用于区分被动降级与主动降级；主动降级只表达态势质量不足，不代表节点失效。
- D5：使用 `GlobalTrack` 的 NED 状态和协方差投影到局部相机平面。D5 不应直接使用 D1 内部单次传感器观测改写终端绑定。
- D6：消费 D1 输出和日志，统计 RMSE、连续性、分级准确率、延迟补偿收益等指标。

跨模块硬约束：

- 所有观测保留 `measurement_timestamp` 和 `arrival_timestamp`。
- 所有航迹保留协方差。
- D1 输出坐标系为 NED。
- `handover_track` 仅代表研究质量等级，不代表授权或自动处置。
- 主动降级信号只描述定位质量、延迟和一致性，不直接触发真实控制或处置动作。

## 13. 局限与后续工作

当前局限：

- D1 只提供基础最近邻式关联，密集交叉目标下的 ID 保持能力有限。
- 雷达是唯一新航迹初始化源，纯 EO/声学初始化尚未启用。
- 仅实现 EKF fallback，UKF、IMM 和 Stone Soup OOSM 对照仍为后续扩展。
- 坐标转换工具以接口约定为主，尚未集成 ROS 2 `tf2`。
- 仿真为质点模型和合成传感器，不代表真实传感器标定误差全集。
- `TrackUncertaintySummary` 当前为接口设计建议，尚未落地为代码数据类。

后续建议：

1. 增加 WGS84/ENU/NED 转换实用函数和单元测试。
2. 增加 UKF 后端，对比强非线性 EO 场景。
3. 增加 IMM-CV/CA/CT 运动模型，输出模型概率供 D2 使用。
4. 将 D1 观测日志与 D6 统一事件记录格式对齐。
5. 在 AirSim 离线回放中验证相机外参误差、遮挡和时间同步误差对 `handover_track` 的影响。
6. 将 `TrackUncertaintySummary` 和 `FusionQualityRegionSummary` 实现为离线日志结构，供 D4 主动降级策略和 D6 批量统计使用。
