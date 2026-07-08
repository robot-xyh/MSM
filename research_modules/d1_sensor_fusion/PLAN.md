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

## 7. 模块接口与当前落地状态

核心数据结构：

- `SensorObservation`: 已实现统一观测合同，包含 `measurement_timestamp`、`arrival_timestamp`、`frame_id`、`measurement`、`covariance`、`confidence`、`quality_flags`、`classification_hint` 和通信元数据。当前允许帧为 radar/acoustic/lidar 的 `ned` 与 EO 的 `pixel`；外部 WGS84/ENU/body/camera 坐标必须先转换或带齐外参元数据，不由融合器静默猜测。
- `GlobalTrack`: 已实现全局航迹输出，包含六维 NED 状态、6x6 协方差、`timestamp`、`track_level`、`source_support`、`identity_likelihood`、`last_nis` 和 `metadata`。`metadata` 已写入 `frame_id="ned"`、`valid_at`、`published_at`、`latest_measurement_timestamp`、`latest_arrival_timestamp`、`latest_observation_latency_s`、通信字段和 `a95_m`。
- `TrackUncertaintySummary`: 已实现 D1 下游单航迹质量摘要，包含 `track_id/global_track_id`、`valid_at`、`published_at`、`track_bucket`、`track_level`、位置/速度协方差迹、`a95_m`、`measurement_age_s`、`source_support`、`coverage_cell`、`measurement_timestamp`、`arrival_timestamp`、`source_diversity_count`、`last_nis`、`handover_readiness` 和 `quality_flags`。
- `LatencyAuditSummary`: 已实现 D1 延迟/OOSM 审计摘要，导出 `observation_count`、`max_delay_s`、`mean_delay_s`、`replay_count`、`oosm_observation_count`、`stale_observation_count`、`stale_or_oosm_observation_count`、重复观测数和最大 replay 历史长度。
- `FusionQualityRegionSummary`: 已实现轻量区域质量摘要，按 `coverage_cell` 聚合 `TrackUncertaintySummary[]` 的 track 数、a95、measurement age、handover readiness、source support、source gap 和 stale track 数，供 D4/D6 做不确定度质量消费。
- `ReconCueSummary`: 已实现面向二级侦察相机粗指向的轻量摘要，由 `summarize_recon_cue_from_tracks()` 从 `GlobalTrack[]` 或 track-like dict 生成；支持按 `coverage_cell` 过滤，并按位置协方差 trace 的倒数加权求 `cue_position_ned`/centroid。
- `FusionAdapter`: 已实现融合入口，提供 `process()`、`ingest_many()`、`predict_track()`、`update_at_measurement_time()`、`compensate_latency()`、`global_tracks()`、`track_uncertainty_summaries()`、`latency_audit_summary()`、`region_quality_summaries()` 和 `_bucket()`。
- `RadarCovarianceConfig`: 已实现可配置距离相关雷达协方差，默认参数保持既有测试行为，可用于近/中/远距离消融。

运行入口：

- `src/d1_sensor_fusion/simulation.py`: 离线仿真与指标生成。
- `scripts/run_simulation.py`: 命令行仿真脚本。
- `tests/`: 单元测试和回归测试。
- `src/d1_sensor_fusion/airsim_dry_run.py`: AirSim-like fake fixture 到 `SensorObservation[]` 的 dry-run adapter，不导入 AirSim。
- `src/d1_sensor_fusion/replay.py`: versioned `sensor_observations.jsonl`/legacy `blocks_sensor_observations.jsonl` reader/replay，以及最小 CSV reader/replay；可将 main/AirSim runtime 或人工审计观测记录读回并喂给 `FusionAdapter`。
- `src/d1_sensor_fusion/recon_cue.py`: 从 `GlobalTrack[]`/track-like dict 生成雷达 cue 粗指向摘要，供 main/AirSim runtime 选择目标群或 coverage cell 子群。

兼容接口：

- FilterPy: 仅有 `FilterPyBackendPlaceholder` 可用性探测，不调用 FilterPy EKF/UKF/IMM，不作为当前运行依赖。
- Stone Soup: 仅有 `StoneSoupAdapterPlaceholder` 和 observation 到 detection dict 的转换边界，不导入 Stone Soup，也未接入真实 tracker/fuser/OOSM 后端。
- AirSim: D1 已提供 dry-run fixture adapter 和 Blocks JSONL replay reader；真实 AirSim 连接、Blocks 启停、`simGetDetections` 调用、frame capture、JSONL 写出和 runtime bus 编排属于 main/shared runtime，不是 D1 包内已完成能力。
- ROS 2: 当前未接入 `tf2` 或 `message_filters`。D1 依赖上游完成坐标转换/时间戳填写，并在离线 replay 内用 `arrival_timestamp` 排序和 fixed-lag replay 处理乱序观测。

## 7.1 2026-07-07 运行时与降级接口复核

本轮复核发生在 main runtime bus、D3/D4/D5 P1 修复之后。D1 已补齐本轮数据合同收敛项，但仍需明确下游解释边界：

- main runtime bus 负责把 D1/D2/D3/D4/D5/D7 DTO、summary 和 record 接入真实 AirSim episode 状态机；D1 仍只负责本模块 `SensorObservation[]` replay 和 `GlobalTrack[]`/`TrackUncertaintySummary[]` 输出。
- D3 中心重规划的新 plan owner/version 不由 D1 生成。D1 只提供 `track_level`、`a95_m`、`measurement_age_s`、source support 和 timing metadata，供 D3 计算代价和判断候选质量。
- D4 主动降级已经区分硬风险与软质量风险。D1 的高协方差、低 freshness、source gap 或 handover readiness 下降是质量证据；单帧或短窗口软风险不应直接触发降级，必须由 D4 结合 C2 health、D3 plan freshness、D5 terminal evidence 和持续窗口仲裁。
- D5 终端一致性窗口修复后，D1 继续提供可投影 NED 状态、6x6 协方差、EO bbox/camera metadata lineage 和时间戳；D5 反馈不能改写 D1 的 `global_track_id`。
- 严格模块流程下，D1 owned 文件的 README/PLAN/GAP/review 状态由 D1 子智能体自行维护并运行本模块测试；main 只做跨模块汇总和集成验证。

## 7.2 2026-07-07 P1 数据合同收敛

本轮新增实现保持轻依赖，不接入新的外部包：

- replay schema v1 固化为 `d1.sensor_observation.v1`；未来 `sensor_observations.jsonl` 与 Blocks replay 共用同一 reader。无 `schema_version` 的既有 `blocks_sensor_observations.jsonl` 作为 legacy 兼容输入保留。
- CSV replay 最小实现已落地，要求 `measurement`/`covariance` 以 JSON array 写入单元格，`metadata`/`communication`/`source_support` 以 JSON object 写入单元格。
- latency/OOSM 审计以累计摘要导出；OOSM 口径为到达观测的测量时刻早于已处理融合时间，stale 口径为处理时已超过 `stale_after_s` 或 arrival delay 超过该 stale budget。
- 区域质量摘要已按 `coverage_cell` 轻量聚合，作为 D4/D6 的区域态势质量证据；最终主动降级仲裁仍属于 D4。
- 这些项不再作为未完成 P1 追踪。剩余 P1 聚焦更多真实 Blocks/CV fixture、D6 长期批量 schema、区域时间窗口、协方差增长率窗口和真实样本回归。

## 7.3 2026-07-08 P1 AirSim 多 seed 校准准备

本轮 D1 侧复核聚焦 main/shared runtime 写出的真实 Blocks replay 与 D1 reader/test/GAP 状态，不修改 main runtime。结论如下：

- JSONL replay 与真实 Blocks writer 的顶层字段保持一致：`measurement_timestamp`、`arrival_timestamp`、`frame_id`、`measurement`、`covariance`、`metadata` 和 `communication` 均会进入 `SensorObservation`，并回放成 NED `GlobalTrack`。
- CSV replay 对缺省 `schema_version` 的行按 `d1.sensor_observation.v1` 处理，因此校准 CSV 必须携带 `covariance`；不再通过 legacy 路径静默接收缺协方差 CSV 行。
- EO replay 可使用嵌套 `metadata.camera_model` 字典恢复相机内外参，避免真实 Blocks/CV JSONL 只保留 camera metadata 但投影模型仍使用默认相机。
- 新增 Blocks calibration CSV 回归，覆盖 measurement/arrival timestamps、covariance、NED state、source support、coverage cell、latency/OOSM audit 和 `FusionQualityRegionSummary`。
- 新增 `ReconCueSummary`/`summarize_recon_cue_from_tracks()` 回归，覆盖全部目标 cue、按 `coverage_cell` cue、缺省协方差保守降权和 measurement/arrival timestamp 保留。
- 当前 D1 状态为无 P0 blocker；时间戳、协方差、NED `GlobalTrack`、N-target 输入和侦察 cue 合同均已进入当前回归基线。
- 剩余 P1 不变：继续收集更多真实 Blocks/CV detection JSONL/CSV 样本，与 D6 对齐长期批量 schema，并补区域时间窗口与协方差增长率窗口。

## 8. 交付物

- `PLAN.md`: 本实施计划。
- Python 源码：数据结构、运动模型、观测模型、NumPy EKF、融合适配器、dry-run adapter、JSONL replay、仿真和指标。
- 单元测试：RMSE、track continuity、分级准确性、延迟补偿前后对比、接口行为、通信元数据、source lineage 去重、TrackUncertaintySummary、LatencyAuditSummary、FusionQualityRegionSummary、ReconCueSummary、AirSim dry-run、Blocks JSONL/CSV replay 和 N actor 合同。
- 仿真脚本：按 `--drone-count N` 生成 N 个目标、60 s、10 Hz 的雷达/声学/EO 观测；历史 3 目标输出仅作为 baseline。
- 图表和 Markdown 实验报告：输出到 `reports/`。
- AirSim 集成计划：统一时间轴、坐标、传感器桥接和离线评估流程；不宣称真实雷达/声学/LiDAR 硬件仿真已接入。

## 9. 已实现、部分实现、未实现对照

### 9.1 已实现能力

- **时间戳合同**: `SensorObservation` 强制保留 `measurement_timestamp` 和 `arrival_timestamp`；`FusionAdapter` 用测量时刻做滤波更新，用到达时刻推进当前时间、记录延迟和排序 replay。`GlobalTrack.metadata` 与 `TrackUncertaintySummary` 已暴露最新测量/到达时间。
- **协方差合同**: 观测侧支持 radar 4x4、acoustic 1x1、EO 2x2、synthetic lidar 3x3 协方差；航迹侧输出 6x6 状态协方差；分级与摘要使用水平 95% 误差椭圆 `a95_m`、协方差迹和 NIS。
- **NED 工作帧**: 雷达、声学和 lidar 观测在 `frame_id="ned"` 下进入融合；EO 以 `frame_id="pixel"` 和相机模型元数据作为投影约束；`GlobalTrack` 固定输出 NED 六维状态。WGS84/ENU 仅作为上游外部参考，不在 D1 内直接滤波。
- **雷达观测适配**: 已实现 `[range, azimuth, elevation, radial_velocity]` 观测模型、角度 wrap、雷达初始化航迹、距离相关测量协方差和 radar observation 到六维初始状态/协方差转换。
- **声学观测适配**: 已实现粗方位角观测、置信度相关角度协方差和 `classification_hint` 累计；声学不会单独初始化三维航迹，也不会单独把航迹提升为 `handover`。
- **视觉/EO 观测适配**: 已实现 pinhole 像素投影约束、bbox/置信度/遮挡/小框驱动的像素协方差放大；D1 只消费 bbox、中心像素、相机元数据、时间戳和协方差，不要求 PNG 截图。
- **GlobalTrack 输出**: 已实现 `global_track_id`、位置、速度、协方差、质量等级、source support、身份似然、NIS 和元数据输出。`global_track_id` 由 D1/FusionAdapter 创建并作为下游中心化 track ID 使用；D5/D7 不应本地改写。
- **侦察粗指向摘要**: 已实现 `ReconCueSummary` 和 `summarize_recon_cue_from_tracks()`，从 `GlobalTrack[]`/track-like dict 按输入数组长度生成目标群或 `coverage_cell` 子群的 `cue_position_ned`、`cue_covariance`、`active_target_ids`、时间戳和基础诊断；缺协方差时使用保守默认并显式计数。
- **延迟补偿**: 已实现 fixed-lag/OOSM replay。延迟观测按 `measurement_timestamp` 插入历史观测序列，重放到当前 `arrival_timestamp`；测试覆盖延迟观测关联和补偿 RMSE 优于未补偿基线，并导出 max/mean delay、replay count、OOSM/stale count 审计摘要。
- **AirSim adapter/dry-run 支持**: 已实现无 AirSim 依赖的 fake fixture adapter，可生成 radar/acoustic/EO/synthetic lidar `SensorObservation[]` 并喂给 `FusionAdapter`；已实现 Blocks JSONL reader/replay、schema v1/legacy 兼容、CSV replay 和 N actor JSONL 合同测试。
- **输入规模**: `generate_truth(target_count=N)` 与 CLI `--drone-count N` 按输入数量运行，不裁剪到 2v2/5v5；2v2、5v5、3-target 只作为 baseline 名称或样例。

### 9.2 部分实现能力

- **AirSim/Blocks 集成**: D1 包内只完成 dry-run adapter 与 JSONL replay；真实 AirSim Blocks episode 启停、`simGetDetections`、frame capture、actor target 移动、runtime bus 和 JSONL 写出由 main/shared runtime 负责。D1 当前可消费这些输出，但不直接连接 AirSim。
- **EO/视觉几何**: D1 有简单 pinhole 投影和 camera metadata 约定；未接入 OpenCV 标定、畸变校正、`solvePnP`、`projectPoints` 或 D5 级跨视角几何一致性。
- **合成 LiDAR**: synthetic lidar 只是 dry-run/replay 里的 NED 三维位置测量模型，用于测试融合合同；不是 AirSim LiDAR plugin，也不是硬件驱动。
- **质量摘要**: `TrackUncertaintySummary` 已是单航迹摘要；`FusionQualityRegionSummary` 已提供按 `coverage_cell` 聚合的轻量区域质量摘要；`ReconCueSummary` 已提供面向二级侦察相机的目标群/coverage cell 粗指向摘要；latency/OOSM replay 计数已可导出。区域时间窗口、协方差增长率窗口、D6 长期批量日志 schema 和更多 NIS 统计仍需后续补齐。
- **source lineage 去重**: 已能抑制同一 source/sequence/payload 经 relay 重复投递造成的重复更新；未知相关性的多节点 Track-to-Track fusion、协方差交叉和相关性降权还未实现。
- **replay 合同**: versioned `sensor_observations.jsonl` reader、legacy `blocks_sensor_observations.jsonl` 兼容和最小 CSV reader 已实现；长期真实 Blocks/CV fixture 回归仍未完成。

### 9.3 未实现能力

- **Stone Soup**: 未接入真实 Stone Soup tracker、updater、initiator、JPDA/MHT、OOSM 或 Track Fusion；当前只有不导入依赖的占位类。原因是当前阶段需要轻依赖、可复现、离线测试稳定，且尚未定义 Stone Soup 与 D1 dataclass 的完整转换和对照指标。
- **FilterPy**: 未调用 FilterPy EKF/UKF/IMM；当前只有可用性探测占位。原因是 D1 已有 NumPy EKF fallback，新增后端需要测试容差、版本约束和 UKF/IMM 对照场景。
- **ROS 2 `tf2`**: 未实现坐标树、外参版本化 tf buffer 或时间化 transform。原因是仓库当前没有 ROS 2 runtime/topic/bag 条件，D1 只规定 NED 输入和 camera metadata 边界。
- **ROS 2 `message_filters`**: 未实现 ROS topic ApproximateTime/ExactTime 同步。原因是当前 D1 运行在离线 `SensorObservation[]`/JSONL replay 层，已用 `measurement_timestamp`、`arrival_timestamp` 和 fixed-lag replay 处理乱序；ROS 同步要等 topic schema 稳定。
- **UKF/IMM/Track-to-Track fusion**: 未实现强非线性 UKF、多模型 IMM、协方差交叉、多节点 track fusion。原因是缺少明确高机动/多节点相关观测基准和与现有 EKF 的收益门限。
- **真实传感器硬件仿真**: 未实现真实雷达、声学阵列、LiDAR 硬件仿真或 AirSim sensor plugin 级接入；当前雷达/声学/lidar 为科研合成观测，EO 依赖上游检测框/metadata。

## 10. 对后续模块的影响

- **对 D2 数据关联**: D1 已提供 NED `GlobalTrack[]`、协方差、`global_track_id`、source support、latest measurement/arrival timestamp 和可选 truth metadata。D2 应使用这些字段进行中心关联和 `id_switch_count` 统计，不应把 2v2/5v5 当作算法规模限制；真实 AirSim truth ID 只能作为离线评估标签。
- **对 D3 分配规划**: D3 可用 `track_level`、`a95_m`、协方差、`measurement_age_s` 和 `source_support` 判断分配候选质量。D1 不生成 `AssignmentPlan`，也不处理 stale plan；D3 仍需按版本化计划拒绝过期输入。
- **对 D4 主动/被动降级**: `TrackUncertaintySummary`、`LatencyAuditSummary` 和轻量 `FusionQualityRegionSummary` 可作为中心态势质量信号；`ReconCueSummary` 只给 main/runtime 粗指向目标群或 coverage cell 子群，不给出最终主动降级建议。D4 应结合 C2 health、D3 版本、D5 反馈和链路状态做最终降级仲裁。
- **对 D5 末端关联**: D1 输出的 `global_track_id`、NED 状态、6x6 协方差、EO bbox/camera metadata lineage、时间戳和可选 `ReconCueSummary` 粗指向可供 D5/main 做相机指向与投影门控。D5 不得改写或本地重绑定 `global_track_id`；终端 truth ID 只能离线评估使用。
- **对 D6 评估指标**: D6 可消费 RMSE、连续性、分级准确性、延迟补偿消融、`TrackUncertaintySummary`、`FusionQualityRegionSummary`、`LatencyAuditSummary` 和 source diversity；后续需要 D1/D6 共同稳定长期批量日志 schema、协方差增长率窗口和区域/freshness 趋势字段。
- **对 D7 导引**: D7 应只把 `stable` 或 `handover` 级 `GlobalTrack` 作为离线中段导引输入，并按协方差/新鲜度扩大门限或请求重规划。D1 不提供飞控、毁伤或自动处置接口。

## 11. 下一步优先级

### P1: 当前主线补强

已完成的 P1 基线：

1. D1 replay schema v1 已固化，`blocks_sensor_observations.jsonl` 与未来 `sensor_observations.jsonl` 已共用 reader，legacy 无版本 Blocks JSONL 已兼容。
2. 最小 CSV reader/replay 已落地，D6/人工审计可复用同一批观测记录；缺省 `schema_version` 的 CSV 行按 v1 验证并要求 `covariance`。
3. `LatencyAuditSummary` 已导出 max/mean latency、OOSM replay、stale、duplicate 和 replay history 计数。
4. `FusionQualityRegionSummary` 已在 `TrackUncertaintySummary` 基线之上按 `coverage_cell` 聚合 source gap、freshness、a95、handover readiness 和 stale track count。
5. source lineage de-dup、Blocks JSONL replay、N actor 合同、嵌套 EO camera metadata replay、ReconCueSummary 和 Blocks calibration CSV 字段保真已进入测试基线。

剩余 P1：

1. 增加更多来自 main/shared runtime 的真实 Blocks/CV detection fixture，覆盖 actor label、camera metadata、timestamp、bbox covariance 和 N actor 输出，并形成真实样本回归。
2. 与 D6 对齐长期批量 JSONL/CSV schema，明确 `TrackUncertaintySummary[]`、`LatencyAuditSummary` 和 `FusionQualityRegionSummary[]` 的批量字段命名。
3. 为区域质量摘要补区域时间窗口、freshness/source-gap 趋势和跨窗口统计。
4. 为 `covariance_growth_rate` 补窗口化计算和回归样本。
5. 保持 NumPy EKF、fixed-lag replay、NED、时间戳、协方差和 N actor 合同为 P0/P1 稳定基线，避免引入会破坏离线测试的强依赖。

### P2: 可选算法和开源对照

1. 以可选后端方式接入 FilterPy EKF/UKF 对照，不替换现有 NumPy fallback；先定义同一观测序列下的误差、协方差和运行时间容差。
2. 以离线实验方式接入 Stone Soup，优先验证 OOSM、JPDA/MHT 或 Track Fusion 的指标收益，不把 Stone Soup 作为主运行依赖。
3. 增加 UKF/IMM 高机动目标基准，明确何时值得从六维 CV/EKF 升级到多模型或非线性滤波。
4. 与 D5 对齐 OpenCV calibration/projectPoints/solvePnP 的责任边界：D1 保持融合合同，D5 负责精细视觉几何时，双方通过相机元数据和投影残差测试对齐。
5. 等 ROS 2 runtime、topic schema、tf tree 和 bag/replay 工具稳定后，再评估 `tf2` 与 `message_filters` 接入；接入前 D1 继续要求上游提供 NED 或完整外参元数据。
