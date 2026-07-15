# D1 多传感器融合与目标配准实施计划

## 当前权威增量与后续计划（2026-07-15）

真实 AirSim M5N2 已完成 baseline/candidate 各 10 case，共 20 case。在线 identity/state truth
使用均为 0；3,805 个 main-bus tick 中 D1 fusion mean/P95/max 为
`320.00/451.46/1234.88 ms`，是 main-bus 内层主导阶段。现有双时间戳、covariance 和 NED
合同必须保持，不能通过丢弃观测、改写量测时刻或人为收紧 covariance 来换取耗时下降。

本轮计划状态更新如下：

1. **已获得的系统证据**：D1 已进入真实 M5N2 20-case 在线链路，truth identity/state use 为
   0；M5N2 case 与实际执行产物完整。
2. **仍开放的 P1 性能项**：100 ms 系统预算未闭合。后续必须在相同冻结输入上继续拆分
   observation 数量、航迹数量、fixed-lag replay、batch cache、历史窗口和日志开销，再由 main
   复跑多 seed 验收；不得仅以单元基准关闭该项。
3. **仍开放的 P1 精度项**：本批没有提供可用 NIS、NEES、RMSE、sensor-specific latency/
   dropout 或 covariance consistency 证据。需另设带离线 truth sidecar、明确 availability 和
   正确身份映射的传感器标定实验。
4. **停止边界**：统计只含 M5N2 20 case；TERM 前额外完成的 1 个 `png_ttc_2v2_seed001`
   排除，dropout 完成数为 0，均不得补零或并入本计划验收。

后文历史计划继续保留；与上述状态冲突时，以本节和 2026-07-15 main 报告为准。

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
- `TrackUncertaintySummary`: 已实现 D1 下游单航迹质量摘要，包含 `track_id/global_track_id`、`valid_at`、`published_at`、`track_bucket`、`track_level`、位置/速度协方差迹、`a95_m`、`measurement_age_s`、`source_support`、`coverage_cell`、`measurement_timestamp`、`arrival_timestamp`、`covariance_growth_rate`、`source_diversity_count`、`last_nis`、`handover_readiness` 和 `quality_flags`。
- `LatencyAuditSummary`: 已实现 D1 延迟/OOSM 审计摘要，导出 `observation_count`、`max_delay_s`、`mean_delay_s`、`replay_count`、`oosm_observation_count`、`stale_observation_count`、`stale_or_oosm_observation_count`、重复观测数和最大 replay 历史长度。
- `FusionQualityRegionSummary`: 已实现轻量区域质量摘要，按 `coverage_cell` 聚合 `TrackUncertaintySummary[]` 的 track 数、a95、measurement age、handover readiness、source support、source gap、stale track 数和可选协方差增长率，供 D4/D6 做不确定度质量消费。
- `FusionQualityRegionWindowSummary`: 已实现轻量窗口摘要，由 `summarize_region_quality_windows()` 从区域摘要序列和可选 `LatencyAuditSummary` 序列生成，用于区分区域协方差增长、freshness 下降、source gap 和 OOSM/latency。
- `ReconCueSummary`: 已实现面向二级侦察相机粗指向的轻量摘要，由 `summarize_recon_cue_from_tracks()` 从 `GlobalTrack[]` 或 track-like dict 生成；支持按 `coverage_cell` 过滤，并按位置协方差 trace 的倒数加权求 `cue_position_ned`/centroid；可选 metadata 保留二级/移动侦察节点、cue 来源和模式。
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
- 这些项不再作为未完成 P1 追踪。剩余 P1 聚焦更多 main/shared 真实 Blocks/CV multi-seed fixture、D6 长期批量 schema、持续窗口阈值和真实样本回归。

## 7.3 2026-07-08 P1 AirSim 多 seed 校准准备

本轮 D1 侧复核聚焦 main/shared runtime 写出的真实 Blocks replay 与 D1 reader/test/GAP 状态，不修改 main runtime。结论如下：

- main runtime 已新增 P1 D4/D5 calibration sweep，并在 sweep 结束后自动调用 D6 标准报告 bundle；D1 不生成 sweep、不写 AirSim runtime，只保证自身 replay/schema/latency/OOSM/region quality 字段可被这些报告消费。
- D6 bundle 对 D1 字段的消费口径限定为报告证据：raw/fusion `LatencyAuditSummary`、`TrackUncertaintySummary`、`FusionQualityRegionSummary[]`、`FusionQualityRegionWindowSummary[]`、`SensorHealthSummary[]`、covariance limit reason、`covariance_scale_reason` 和 `timestamp_uncertainty_s`；这些字段不代表 D1 触发主动降级或生成控制决策。
- JSONL replay 与真实 Blocks writer 的顶层字段保持一致：`measurement_timestamp`、`arrival_timestamp`、`frame_id`、`measurement`、`covariance`、`metadata` 和 `communication` 均会进入 `SensorObservation`，并回放成 NED `GlobalTrack`。
- CSV replay 对缺省 `schema_version` 的行按 `d1.sensor_observation.v1` 处理，因此校准 CSV 必须携带 `covariance`；不再通过 legacy 路径静默接收缺协方差 CSV 行。
- EO replay 可使用嵌套 `metadata.camera_model` 字典恢复相机内外参，避免真实 Blocks/CV JSONL 只保留 camera metadata 但投影模型仍使用默认相机。
- 新增 Blocks calibration CSV 回归，覆盖 measurement/arrival timestamps、covariance、NED state、source support、coverage cell、latency/OOSM audit 和 `FusionQualityRegionSummary`。
- 新增 `ReconCueSummary`/`summarize_recon_cue_from_tracks()` 回归，覆盖全部目标 cue、按 `coverage_cell` cue、缺省协方差保守降权和 measurement/arrival timestamp 保留。
- 当前 D1 状态为无 P0 blocker；时间戳、协方差、NED `GlobalTrack`、N-target 输入和侦察 cue 合同均已进入当前回归基线。
- 轻量区域时间窗口和协方差增长率 helper 已落地；剩余 P1 转为继续收集 main/shared runtime 的真实 Blocks/CV multi-seed detection JSONL/CSV 样本、与 D6 对齐长期批量 schema，并基于真实样本确定持续窗口阈值。

## 7.4 2026-07-09 P1 输入支撑补强

本轮不改 D1 主滤波算法，也不接入 Stone Soup、FilterPy、UKF 或 IMM。补强范围限定为 replay/schema/metadata 回归：

- dry-run fixture 增加 `d1.airsim_dry_run_fixture.v1` schema version，生成的 observation metadata 保留 `d1_fixture_schema_version`，并拒绝不支持的 fixture schema version。
- replay 增加 `summarize_sensor_observation_latency_audit()`，可在不运行融合器时从 `SensorObservation[]` 统计 observation latency、OOSM、stale 和重复 lineage，供 main/D6 在长期批处理前做输入审计。
- Blocks/CV JSONL 与 CSV 回归补充 `covariance_scale_reason`、`mobile_recon`、`recon_cue_summary`、`cue_position_ned` 和 `cue_covariance` 保真检查，并验证这些字段能随最新观测进入 `GlobalTrack.metadata`。
- JSONL replay 已补显式 unsupported schema version 回归；CSV 缺省 schema 仍按 `d1.sensor_observation.v1` 处理并要求 covariance。
- 本轮未重新打开 P0-A：`SensorHealthSummary`、观测/航迹 covariance floor/ceiling reason 和 `timestamp_uncertainty_s` 已作为 D1 质量字段保持回归，并纳入 main/D6 消费口径。

## 7.5 历史基线：2026-07-10 main episode bus / AirSim 2v2 合同复核

本轮只读取 main/shared runtime 代码和
`research_modules/airsim_runtime/outputs/p1_gap_closure_2v2_smoke_20260710/` 产物，不修改
main/runtime。六个 reset-separated episode 共 1,528 条 radar/acoustic/EO/synthetic-lidar
观测均可由 D1 reader 解析；所有观测保留 `measurement_timestamp`、
`arrival_timestamp` 和有限、对称、半正定 covariance，未发现到达时刻早于量测时刻的
记录。full-flow 的 36 个 main bus tick 均保留 D1 观测双时间戳和 covariance trace，
`TrackUncertaintySummary` 继续保留 timing/covariance 字段，运行时按 truth-hint 仿真配置
维持 2 条 D1 航迹。因此本轮未发现 D1 双时间戳、协方差或 NED 航迹合同回归。

真实产物同时确认以下 P1 尚未闭合：

- main Blocks writer 尚未写 `schema_version`，新产物当前仍通过
  `legacy.blocks_sensor_observations` 兼容路径读取；D1 v1 reader 已就绪，但 writer 采用
  显式 `d1.sensor_observation.v1` 仍属于 main/shared 集成工作。
- 观测未携带 `coverage_cell`，D1 区域摘要只能输出 `unassigned`；main tick 目前只发布
  `TrackUncertaintySummary[]`，尚未发布区域/窗口、latency audit 和 sensor health 摘要，
  因而真实 smoke 尚未完成区域质量闭环验收。
- 固定 0.2 s 延迟、多传感器同帧顺序处理会产生大量合法 OOSM 计数；当前 advisory
  sensor-health 阈值若直接查询会把正常固定延迟流标为 `isolated`。后续需区分 expected
  latency/OOSM 与异常 clock/stale evidence，并用多 seed 正常/故障样本标定；在此之前
  D4/D6 不得把该状态直接当作降级动作依据。
- main bus 当前以 `use_truth_hints_for_association=True` 的仿真配置维持 2 条航迹；同一
  JSONL 用 D1 默认无 truth-hint replay 会产生 3 条航迹，其中 TGT-002 出现重复初始化。
  后续需把关联配置写入 replay provenance，并用无真值门控/关联校准实现运行时与离线
  replay 一致；truth metadata 只能用于离线评估，不能成为真实在线身份依据。
- 单次 2v2 smoke 已从“只有 dry-run/手工 fixture”推进到真实产物审计，但仍不足以关闭
  N actor、多 seed、CV detection、区域窗口和长期 D6 schema 的 P1 校准项。

## 7.6 历史基线：2026-07-10 十 seed 与 truth-isolation 证据同步

main 随后完成了
`research_modules/airsim_runtime/outputs/p1_gap_closure_2v2_multiseed_20260710/` 的 10-seed
2v2 系统运行，以及
`research_modules/airsim_runtime/outputs/p0_truth_isolation_smoke_20260710/` 的在线身份隔离
smoke。前者证明 D1 合同已被连续用于多 seed episode 编排；后者证明 D5 在线局部检测/
MOT 标识不再依赖 actor/object 名称。两项均是 main/shared 集成证据，不替代 7.5 节对
1,528 条 D1 观测的逐条时间戳/协方差审计，也不代表 D1 无真值关联已经闭合。

truth-isolation smoke 的 D1 合成观测仍可携带 `truth_id` 作为离线评分标签，main bus 的
融合配置仍可启用 simulation-only truth hint。D1 的验收边界保持不变：在线算法不得把
该标签作为身份依据；下一阶段仍需把 fusion/association 配置写入 replay provenance，
并用无 truth-hint 的多 seed replay 校准重复初始化与关联一致性。10-seed 运行产物尚未被
固化为覆盖 schema version、coverage cell、CV bbox covariance 和二级侦察 metadata 的
D1 长期 fixture，因此这些 P1 不能仅凭系统运行次数关闭。

## 7.7 历史基线：2026-07-11 5v5 在线 truth 隔离与 governance 证据

main 完成
`research_modules/airsim_runtime/outputs/p1_runtime_truth_isolated_d4d5_smoke_20260711/`
三个 reset-separated 5v5 episode，分别覆盖不降级、降级到二级节点和降级到完全分布式。
每个 episode 为 seed 7、5 帧、0.4 s 短时 smoke。三组运行中 D1/D2/D3 模块健康均为
`ok`，D1 每组发布 15 条模块记录，D3 assignment coverage 为 1.0，证明 main 在线隔离
truth hint 后，D1 -> D2 -> D3 仍能以中心 `global_track_id` 和状态/协方差继续工作。

`main_episode_bus_metrics.json` 已消费 D1 governance：每组均生成
`d1_latency_audit` 和 `d1_region_quality_window` 事件，并报告
`d1_max_delay_s` 约 0.2 s、`d1_region_quality_coverage_rate=1.0`。因此此前“main bus 尚未
发布任何 D1 region/window/latency governance”的状态已被这次短时接线证据部分关闭。
是否长期保留完整 `SensorHealthSummary`、covariance reason、timestamp uncertainty 及
schema/version 字段，仍需更长 episode 和 D6 批量 schema 审计。

三组运行的 `d1_oosm_observation_rate` 均约为 0.9867。该值来自固定延迟、多模态观测按
到达顺序逐条进入 fixed-lag replay 的当前累计口径，表示绝大多数后续到达的量测时刻早于
已推进融合时刻，不表示约 98.7% 的传感器发生故障。D4 只能消费 unexpected OOSM、stale、
延迟预算超限和持续窗口等已校准证据，不能直接按 raw OOSM rate 降级。

本证据只关闭 truth-isolated 运行时接线的单 seed smoke 风险，不关闭 P1 multi-seed 校准。
下一步仍需多 seed、长时窗口、不同传感器延迟分布、正常/故障对照和批处理/水位线口径对照，
再确定 OOSM、区域质量和 handover readiness 的告警阈值。

## 8. 交付物

- `PLAN.md`: 本实施计划。
- Python 源码：数据结构、运动模型、观测模型、NumPy EKF、融合适配器、dry-run adapter、JSONL replay、仿真和指标。
- 单元测试：RMSE、track continuity、分级准确性、延迟补偿前后对比、接口行为、通信元数据、source lineage 去重、TrackUncertaintySummary、LatencyAuditSummary、FusionQualityRegionSummary、ReconCueSummary、协同 bearing 1/2/3/N 几何、CI 保守性、AirSim dry-run、Blocks JSONL/CSV replay 和 N actor 合同。
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
- **质量摘要**: `TrackUncertaintySummary` 已是单航迹摘要；`FusionQualityRegionSummary` 已提供按 `coverage_cell` 聚合的轻量区域质量摘要；`FusionQualityRegionWindowSummary`/`summarize_region_quality_windows()` 已提供区域时间窗口趋势；`annotate_covariance_growth_rates()` 已提供协方差增长率差分；`ReconCueSummary` 已提供面向二级侦察相机的目标群/coverage cell 粗指向摘要；latency/OOSM replay 计数已可导出。D6 长期批量日志 schema、真实样本阈值和更多 NIS 统计仍需后续对齐。
- **source lineage 去重与 CI**: 观测主线已能抑制同一 source/sequence/payload 经 relay 重复投递；独立 `cooperative.py` 也已实现 message UUID/完整 source-lineage 去重和未知交叉相关下的最小 CI。多节点 runtime 接线、部分共享 lineage 建模和分布式共识仍未实现。
- **replay 合同**: versioned `sensor_observations.jsonl` reader、legacy `blocks_sensor_observations.jsonl` 兼容、真实 CV bbox/camera/detection/recon metadata 字段保真和最小 CSV reader 已实现；长期 main/shared 真实 Blocks/CV multi-seed fixture 回归仍未完成。

### 9.3 未实现能力

- **Stone Soup**: 未接入真实 Stone Soup tracker、updater、initiator、JPDA/MHT、OOSM 或 Track Fusion；当前只有不导入依赖的占位类。原因是当前阶段需要轻依赖、可复现、离线测试稳定，且尚未定义 Stone Soup 与 D1 dataclass 的完整转换和对照指标。
- **FilterPy**: 未调用 FilterPy EKF/UKF/IMM；当前只有可用性探测占位。原因是 D1 已有 NumPy EKF fallback，新增后端需要测试容差、版本约束和 UKF/IMM 对照场景。
- **ROS 2 `tf2`**: 未实现坐标树、外参版本化 tf buffer 或时间化 transform。原因是仓库当前没有 ROS 2 runtime/topic/bag 条件，D1 只规定 NED 输入和 camera metadata 边界。
- **ROS 2 `message_filters`**: 未实现 ROS topic ApproximateTime/ExactTime 同步。原因是当前 D1 运行在离线 `SensorObservation[]`/JSONL replay 层，已用 `measurement_timestamp`、`arrival_timestamp` 和 fixed-lag replay 处理乱序；ROS 同步要等 topic schema 稳定。
- **UKF/IMM 与完整 Track-to-Track runtime**: 强非线性 UKF、多模型 IMM、跨 D2/runtime 的多节点 track-fusion 流程尚未实现；NumPy CI 数值 helper 已完成，不等于 Stone Soup 后端或分布式全链路。
- **真实传感器硬件仿真**: 未实现真实雷达、声学阵列、LiDAR 硬件仿真或 AirSim sensor plugin 级接入；当前雷达/声学/lidar 为科研合成观测，EO 依赖上游检测框/metadata。

## 10. 对后续模块的影响

- **对 D2 数据关联**: D1 已提供 NED `GlobalTrack[]`、协方差、`global_track_id`、source support、latest measurement/arrival timestamp 和可选 truth metadata。D2 应使用这些字段进行中心关联和 `id_switch_count` 统计，不应把 2v2/5v5 当作算法规模限制；真实 AirSim truth ID 只能作为离线评估标签。
- **对 D3 分配规划**: D3 可用 `track_level`、`a95_m`、协方差、`measurement_age_s` 和 `source_support` 判断分配候选质量。D1 不生成 `AssignmentPlan`，也不处理 stale plan；D3 仍需按版本化计划拒绝过期输入。
- **对 D4 主动/被动降级**: `TrackUncertaintySummary`、`LatencyAuditSummary` 和轻量 `FusionQualityRegionSummary` 可作为中心态势质量信号；`ReconCueSummary` 只给 main/runtime 粗指向目标群或 coverage cell 子群，不给出最终主动降级建议。D4 应结合 C2 health、D3 版本、D5 反馈和链路状态做最终降级仲裁。
- **对 D5 末端关联**: D1 输出的 `global_track_id`、NED 状态、6x6 协方差、EO bbox/camera metadata lineage、时间戳和可选 `ReconCueSummary` 粗指向可供 D5/main 做相机指向与投影门控。D5 不得改写或本地重绑定 `global_track_id`；终端 truth ID 只能离线评估使用。
- **对 D6 评估指标**: D6 可消费 RMSE、连续性、分级准确性、延迟补偿消融、`TrackUncertaintySummary`、`FusionQualityRegionSummary`、`FusionQualityRegionWindowSummary`、`LatencyAuditSummary` 和 source diversity；后续需要 D1/D6 共同稳定长期批量日志 schema 和真实多 seed 持续阈值。
- **对 D7 导引**: D7 应只把 `stable` 或 `handover` 级 `GlobalTrack` 作为离线中段导引输入，并按协方差/新鲜度扩大门限或请求重规划。D1 不提供飞控、毁伤或自动处置接口。

## 11. 历史计划基线：2026-07-10 下一步优先级

### P1: 当前主线补强

已完成的 P1 基线：

1. D1 replay schema v1 已固化，`blocks_sensor_observations.jsonl` 与未来 `sensor_observations.jsonl` 已共用 reader，legacy 无版本 Blocks JSONL 已兼容。
2. 最小 CSV reader/replay 已落地，D6/人工审计可复用同一批观测记录；缺省 `schema_version` 的 CSV 行按 v1 验证并要求 `covariance`。
3. `LatencyAuditSummary` 已导出 max/mean latency、OOSM replay、stale、duplicate 和 replay history 计数。
4. `FusionQualityRegionSummary` 已在 `TrackUncertaintySummary` 基线之上按 `coverage_cell` 聚合 source gap、freshness、a95、handover readiness 和 stale track count。
5. source lineage de-dup、Blocks JSONL replay、N actor 合同、嵌套 EO camera metadata replay、ReconCueSummary 和 Blocks calibration CSV 字段保真已进入测试基线。
6. 真实 Blocks/CV 风格 JSONL 字段保真、`annotate_covariance_growth_rates()` 和 `summarize_region_quality_windows()` 已进入轻量测试基线，覆盖 bbox/camera/detection/secondary recon metadata、source gap、freshness、协方差增长和 OOSM/latency flags。
7. dry-run fixture schema 检查、raw replay latency/OOSM audit helper、`covariance_scale_reason` 和 secondary/mobile recon cue metadata 保真已进入 P1 输入支撑回归。
8. 中心化协同定位 P1 数值基础已完成：typed DTO、2..N bearing-ray WLS、几何/时间/covariance 保守门控、共同估计时刻传播和 source-aware CI 均保持为独立 helper，不改变 `FusionAdapter` 默认路径。

剩余 P1：

1. main/shared Blocks writer 显式写入 `schema_version="d1.sensor_observation.v1"` 和 `coverage_cell`；D1 保持 legacy 读取兼容，不跨边界修改 runtime。
2. main episode bus 与 D6 长期 JSONL/CSV schema 发布并对齐 `LatencyAuditSummary`、`FusionQualityRegionSummary[]`、`FusionQualityRegionWindowSummary[]`、`SensorHealthSummary[]`、covariance reason 和 timestamp uncertainty；已发布的 `TrackUncertaintySummary[]` 不再列为缺口。
3. 使用正常延迟和故障注入多 seed 样本校准 expected-latency/OOSM 健康阈值，避免固定 0.2 s 合法延迟触发错误隔离建议。
4. 将 fusion/association 配置写入 replay provenance，完成无 truth-hint 多 seed replay，校准重复初始化和在线/离线关联一致性；truth metadata 仅保留为离线评分标签。
5. 将现有十 seed 运行扩展并固化为 D1 Blocks/CV fixture，覆盖 N actor、camera metadata、bbox covariance、`coverage_cell` 和 secondary/mobile recon cue metadata。
6. 基于上述真实 fixture 校准区域窗口、freshness/source-gap、协方差增长率和 handover readiness 的持续阈值，并保持 NumPy EKF、fixed-lag replay、NED、双时间戳和协方差合同不退化。

### P2: 可选算法和开源对照

1. 以可选后端方式接入 FilterPy EKF/UKF 对照，不替换现有 NumPy fallback；先定义同一观测序列下的误差、协方差和运行时间容差。
2. 以离线实验方式接入 Stone Soup，优先验证 OOSM、JPDA/MHT 或 Track Fusion 的指标收益，不把 Stone Soup 作为主运行依赖。
3. 增加 UKF/IMM 高机动目标基准，明确何时值得从六维 CV/EKF 升级到多模型或非线性滤波。
4. 与 D5 对齐 OpenCV calibration/projectPoints/solvePnP 的责任边界：D1 保持融合合同，D5 负责精细视觉几何时，双方通过相机元数据和投影残差测试对齐。
5. 等 ROS 2 runtime、topic schema、tf tree 和 bag/replay 工具稳定后，再评估 `tf2` 与 `message_filters` 接入；接入前 D1 继续要求上游提供 NED 或完整外参元数据。

## 12. 2026-07-11 P1 Replay/Schema 治理执行结果

本轮在 D1 边界内完成以下工作，不连接 AirSim SDK，也不引入 Stone Soup/FilterPy：

1. 新增 JSONL/CSV governed writer，强制写 `d1.sensor_observation.v1` 和场景/配置 provenance；旧无版本 Blocks reader 继续兼容。
2. writer 默认剥离在线 `truth_id`、actor/object ID；离线标签只有显式启用后才进入 `offline_truth`。
3. `SensorTimingExpectation` 和 `SensorHealthSummary` 已区分预期延迟、延迟预算超限、总 OOSM 与 unexpected OOSM，避免固定延迟流仅因合法 OOSM 被误判隔离。
4. `summarize_region_quality_windows(window_size_s=...)` 已按 `coverage_cell` 和固定时间桶输出窗口，并按 `LatencyAuditSummary.published_at` 对齐延迟/OOSM 证据。
5. 固化真实 Blocks/CV 字段形态的 JSONL/CSV fixture；无 truth-hint 两目标 replay 输出两条带 6x6 协方差的 NED 航迹。

本轮已关闭的 D1-owned P1：writer schema/provenance、expected-latency/OOSM 字段、区域固定窗口、协方差增长窗口、基础 truth-free replay fixture。最新验证中 main episode bus 已接入 governed writer，并把在线 truth 与离线评分标签分离；真实多 seed 延迟门限、视觉 bbox/camera fixture 和关联门限继续由后续 AirSim 校准闭合。

## 13. M 对 N 协同定位调研后的 P1 计划补充

专项证据见 `subagent_reviews/D1_M_TO_N_COOPERATIVE_LOCALIZATION_REVIEW.md`。当高威胁目标由 3 架无人机共同观测时，D1 不要求严格同帧或同时到达，而要求所有观测按 `measurement_timestamp`、平台测量时刻位姿和运动模型传播到共同估计时刻。三机数量本身不保证可观测性，必须检查视线交会角、联合信息矩阵秩/条件数、重投影残差和传播后 covariance。

本项不新增 P0 blocker。2026-07-11 实施后的状态拆解为：

1. **D1-owned 基础已完成**：`CooperativeBearingObservation`、`CooperativeObservationGroup` 和 `CooperativeLocalizationSummary` 覆盖共同估计时刻、observer/source lineage、平台位姿/外参 covariance、measurement skew、LOS 交会角、信息矩阵 rank/condition、残差和拒绝原因。
2. **构造性基准已完成，真实 replay 待补**：单元测试覆盖 1/2/3/N observer、良好三视角不劣于最佳双视角、近共线拒绝、0.4 s 异步传播和 covariance 膨胀；near-synchronous/range、机动、遮挡、节点退出、AirSim 多 seed 及 RMSE/NIS/NEES 仍需 replay。
3. 与 D2 固化边界：D1 负责时间/坐标/协方差和已关联状态的数值融合；D2 负责 local-track-to-`global_track_id` 关联、身份连续性与 IDSW。D2 未确认同一目标时 D1 不做跨平台 Track-to-Track 融合。
4. **最小 CI helper 已完成**：支持 1/2/3/N 个同 canonical ID 的 6-state NED estimate、共同时间 CV 传播、process/timing noise、message UUID/完整 lineage 去重；已验证 CI covariance 不比错误独立融合更自信。部分 lineage 相关性模型、D2/runtime 接线和成员退出 replay 仍待补。
5. Stone Soup CI、GTSAM/OpenCV triangulation 仅作离线 benchmark；外部库正式接入、ROS 2 和主运行时替换仍保持既有后置优先级，不改当前 NumPy EKF 主线。

物理拦截的同时到达、分波次到达和三机任务联盟属于 D3/D7；D1 只提供共同估计时刻的目标状态、协方差和协同几何质量。

## 14. 历史基线：2026-07-11 M-to-N 三 seed 证据与后续实施顺序

最新系统证据为
`research_modules/airsim_runtime/outputs/blocks_cv_m5_n2_liveness_batch_20260711/M_TO_N_AIRSIM_CONVERGENCE_REPORT_CN.md`。
seeds 7/17/27 均记录 6 次中心重规划请求、6 次 no-change ACK、0 次 applied、0 次 expired；
需求满足率均为 1.0，错误重复锁定均为 0。T002 视觉共识帧为 4/5/4，D7 每个 seed
获得 2 次终端合同许可；T001 双 primary 共识三组均为 0，仍是系统 P1。该试验运行于
ComputerVision 模式，只证明 D1 数据合同被 M-to-N 状态链消费，不证明 D1 已完成真实
传感器标定，也不表示完成物理拦截。

当前状态分层如下：

- **P0 已闭合并保持回归**：双时间戳、NED、观测/航迹 covariance、FDIR-light、
  covariance floor/ceiling、timestamp uncertainty、source lineage 去重和 N-target 输入无
  运行级 blocker。当前 D1 回归基线为 `62 passed`。
- **P1 接口已完成**：governed replay/schema/provenance、truth-label 默认剥离、区域/窗口
  质量摘要、expected-latency/OOSM 字段、侦察 cue、协同定位 typed DTO、2..N bearing WLS
  和保守 CI 数值 helper 已落地。
- **P1 待实现或真实标定**：main/shared 采用 governed writer；D1/D2-confirmed
  association-to-fusion runtime 接线；真实多 seed 的机动、遮挡、节点退出、相机 bbox、
  传感器延迟和故障注入 replay；RMSE/NIS/NEES consistency、区域/健康持续阈值、
  IMM/CV-CA-CT 和场景自适应 covariance 标定；D6 长期 schema 对齐。T001 双 primary
  共识由 D5/D7 主责，D1 仅提供其所需的时间化状态、协方差和几何质量。
- **P2 optional benchmark**：FilterPy、Stone Soup、OpenCV/GTSAM 和 ROS 2 只在隔离环境
  做对照或后置评估，不替换当前 NumPy EKF/fixed-lag 默认路径。

后续实施顺序固定为：

1. main/shared 接入 D1 governed replay writer，并把场景配置、seed、coverage cell 和离线
   truth 分离规则写入 replay manifest。
2. D1 与 D2 固化 local-track-to-canonical-ID 确认合同，再把 cooperative WLS/CI 接入可选
   runtime adapter；关联不唯一时保持不融合。
3. main 采集 ComputerVision/AirSim 多 seed replay，覆盖 crossing、机动、遮挡、漏检、
   传感器延迟和节点退出；D1 校准 covariance、OOSM/health、区域窗口及 RMSE/NIS/NEES。
4. 在 P1 数据和验收口径稳定后，启动 FilterPy/Stone Soup 等离线 P2 benchmark；第三方
   后端不可用时必须报告 `unavailable`，不得静默替代为当前实现。
5. 每轮实现后运行
   `PYTHONPATH=research_modules/d1_sensor_fusion/src pytest -q research_modules/d1_sensor_fusion/tests`，
   并由 D1 owner 更新 README、PLAN、GAP 和 review。

## 15. Governed Replay Manifest/Serializer P1 实施结果

D1-owned 严格回放合同已经实现，不直连 AirSim，也未修改 main/runtime：

- `ReplayProvenance` 在原有 scenario/config ID、scenario version 和 config digest 基础上增加
  `scenario_digest` 与 `config_version`；严格 governed 路径同时要求非空 seed。
- `serialize_governed_replay()` 一次性生成 JSON-safe manifest 与在线 records。manifest 固定为
  `d1.governed_replay_manifest.v1`，包含 observation schema、NED fusion working frame、双时间
  范围、coverage cells 和逐观测 opaque source lineage。
- 严格校验拒绝缺失 coverage cell/covariance、非有限或倒序时间戳、维度不匹配/非对称/非
  半正定 covariance，以及缺失 scenario/config identity/version/digest/seed 的 provenance。
- 默认在线序列化递归剥离 truth/actor/object ID；source lineage 使用观测内容摘要，不能通过
  fallback fingerprint 泄漏 truth。`serialize_offline_governed_replay()` 是显式 offline-only
  标签出口，标签只进入 `offline_truth`。
- 旧无版本 Blocks JSONL 继续由 legacy reader 兼容；兼容读取不等于满足严格 governed 合同。

单元测试覆盖多目标批次、manifest JSON 序列化、字段缺失拒绝、legacy 兼容、深层 truth
剥离、显式离线标签、双时间戳、NED working frame、covariance 和 source lineage 往返保真。
当前全量结果为 `62 passed`。最新 main episode bus 已采用该 API，并在 governed manifest
中提供 scenario/config provenance、seed 和 coverage cell；下一步不再重复实现 serializer，
而是用更长的真实 multi-seed replay 校准 D1 统计与阈值。

## 16. 当前状态与后续项（2026-07-11 最终验证）

最终依据为
`research_modules/airsim_runtime/outputs/p1_p2_validation_20260711/P1_P2_VALIDATION_SUMMARY_CN.md`。

- **P1 合同层已闭合**：main episode bus 已携带 D1 governed replay、双时间戳、covariance
  和 lineage；在线记录剥离 truth/actor/object identity，truth 只进入独立离线评分标签。
- **ComputerVision 合同验收已通过**：10 seeds 中 8/10 达到 T001 双 primary 合同阈值。
  二级和完全分布式 3/3 ACK commit 正例通过，缺 ACK 的 2/3 case abort 并 fail-closed。
  这些是 D1 数据合同进入下游链路的系统证据，不扩大 D1 的分配、联盟或控制职责。
- **P1 物理/长期标定仍开放**：SimpleFlight 15 s 仅作断点诊断，30 个 active pair 均未命中；
  该结果不能解释为 D1 融合精度验收，也不能用于关闭真实传感器、多 seed 长 replay、
  sensor-specific latency/health/window 或 RMSE/NIS/NEES 标定。物理拦截闭环由 main/D7 等
  系统链路负责，D1 只对状态、协方差、时间和质量证据负责。
- **P2 隔离 benchmark 已收敛到可审计状态**：D1 冻结 governed replay 已对当前 NumPy
  EKF/fixed-lag 路径输出 RMSE/NIS/NEES/耗时。当前环境未安装 FilterPy 或 Stone Soup，两个
  adapter 均输出 `status=unavailable`、空指标和 `unavailable_reason`；未伪装为当前实现，也未
  加入默认 requirements。UKF/IMM 和第三方可执行 tracker/fuser 仍未实现。
- **adapter/smoke/研究近似边界**：D1 AirSim dry-run adapter、静态 JSONL/CSV fixture 与
  ComputerVision 合同验收只证明接口和 truth policy 可运行；当前合成 radar/acoustic/EO
  观测、CV/EKF 机动吸收及 WLS/CI 数值 helper 属科研仿真基线，不能替代真实传感器标定、
  长时 AirSim replay 或完整分布式 Track-to-Track 后端。

当前 D1 后续项不再包含 governed writer 接入、在线 truth 隔离或 CV 双 primary 合同闭合。
保留的工作是 D1/D2-confirmed cooperative runtime 验证，以及真实多 seed 的机动、遮挡、
节点退出、camera/bbox 和 sensor-delay replay；据此完成 RMSE/NIS/NEES、sensor-specific
expected latency、health/region window、模型集和场景自适应 covariance 标定。15 s
SimpleFlight 诊断不能替代这些更长时、带故障对照的 replay。

## 17. P2 隔离滤波基准收敛结果

本轮复用现有 governed replay 和 `FusionAdapter`，没有重复实现在线观测类型、serializer 或
滤波主线。静态 fixture 固定 scenario/config digest、seed、双时间戳、NED frame、观测
covariance 和 source lineage；在线 records 不含 truth，六状态 truth 只位于独立
`offline_truth` sidecar 并在滤波完成后用于 RMSE/NEES 评分。

当前路径在六条 radar 观测上的一次验证结果为 RMSE `0.2335 m`、mean NIS `0.0426`、mean
NEES `0.0651`、两次 wall time 为 `6.9-10.1 ms`。耗时是主机相关观测值；低 NIS/NEES 表明该小型合成
fixture 下 covariance 偏保守，不能用于关闭真实多 seed consistency 标定。FilterPy 与 Stone
Soup 在当前环境均不可导入，因此只记录 unavailable 状态和原因，不生成第三方指标。

P2 当前关闭的是“无审计输出的可用性探测”缺口；仍开放的是安装于隔离环境后的真实可执行
adapter 对照，以及 UKF/IMM/OOSM/JPDA/MHT 等收益评估。默认 requirements、在线 D1 和
NumPy EKF/fixed-lag 路径均未改变。全量回归为 `62 passed`。

## 18. 2026-07-12 P0/P1 文档状态同步

本节依据当前 `HEAD=33e6fa0` 的 D1 源码与测试、
`subagent_reviews/MAIN_IMPLEMENTATION_GAP_AUDIT.md` 和
`research_modules/airsim_runtime/outputs/PNG_DELIVERY_ENHANCEMENT_AIRSIM_VALIDATION_REPORT_20260712.md`
同步当前状态。`33e6fa0` 未修改 D1 源码、测试或既有能力；本轮 PNG delivery 实现与实测属于
D5/D6/D7 和 main/runtime。D1 在该轮没有行为变化，P0/P1 保持原状态，不因 2v2 `20/20`、
锁定后两帧 dropout 或 M5N2 `0/9` 新增或关闭融合能力。2026-07-12 重新执行 D1 指定测试，
结果为 `62 passed in 11.60s`。

### 18.1 P0 当前状态

| P0 项 | 当前状态 | 2026-07-12 证据与下一验收 |
| --- | --- | --- |
| 双时间戳、NED 与 covariance 合同 | 已实现，保持回归 | `SensorObservation`、`GlobalTrack`、governed replay 和现有接口测试继续覆盖；下一验收仍要求观测/航迹双时间戳、NED 六状态和有限、对称、半正定 covariance 不退化 |
| fixed-lag/OOSM、source lineage 去重与 N-target 输入 | 已实现，保持回归 | 当前 62 项回归通过；下一验收要求乱序补偿、relay 重发去重和按输入数组长度处理继续通过，且 online path 不使用 truth/actor/object ID |
| FDIR-light、covariance 上下界和 timestamp uncertainty | 已实现，保持回归 | `SensorHealthSummary`、limit reason 和 timing uncertainty 字段无变化；下一验收要求正常预期延迟不被误判为故障，故障注入仍输出可解释 reason/recovery evidence |

当前没有 D1 运行级 P0 blocker。PNG delivery 报告没有修改或重新验收 D1 滤波精度，因此其
物理成功/失败数字只作为下游系统证据，不作为 D1 P0 状态变化依据。

### 18.2 P1 当前状态与下一验收

| P1 项 | 当前状态 | 开放缺口 | 下一验收条件 |
| --- | --- | --- | --- |
| governed replay/schema/provenance 与 online truth 隔离 | 已实现并已被 main episode bus 采用；本轮无行为变化 | 需要更长真实 replay 持续验证，而不是重复实现 serializer | 冻结 scenario/config version、digest、seed、coverage/lineage；多 seed online records 保持 truth-free，offline label 只用于评分 |
| 区域/窗口质量、expected-latency/OOSM、sensor health 与 recon cue | 接口和构造回归已实现；真实阈值部分实现 | 缺 sensor-specific 正常/故障对照、长窗口和 D6 长期趋势校准 | 在多 seed radar/acoustic/EO 延迟及 fault injection replay 中量化误报/漏报，稳定发布 health/region/window/covariance reason/timing uncertainty |
| 协同 bearing WLS 与保守 CI | D1-owned typed DTO 和数值 helper 已实现；runtime 全链路部分实现 | 缺 D2-confirmed canonical-ID adapter、真实多节点 replay、部分共享 lineage 和节点退出验证 | 关联不唯一时拒绝融合；良好三视角不劣于最佳双视角；退化几何增大 covariance 或拒绝；3 -> 2 -> 1 节点退出时航迹连续且质量显式下降；relay 重发不改变 posterior |
| 真实 AirSim/ComputerVision 长 replay 与统计一致性 | 未闭合 | 缺 crossing、机动、遮挡、漏检、camera/bbox、节点退出、sensor delay/fault 的长期多 seed fixture | 用版本化 governed replay 输出并审计 RMSE/NIS/NEES、continuity、expected latency/OOSM 和 handover/region window；不得用短时 SimpleFlight 命中率替代 D1 精度验收 |
| CV/CA/CT 模型集与场景自适应 covariance | 未实现/待标定 | 当前仍为 NumPy CV/EKF 主线；缺机动模型对照及杂波、SNR、来源差异、遮挡和延迟 scale rule | 同一真实/冻结 replay 下给出 CV-only 对照、RMSE/NIS/连续性和运行成本，并稳定输出可解释 `covariance_scale_reason`；未达到收益门槛时不替换默认路径 |
| D6 长期批量 schema 与趋势 | 部分实现 | 当前字段可被消费，但缺长时跨 seed 统计一致性和冻结阈值 | D6 对同一 governed replay 可稳定聚合 latency、health、region/window、RMSE/NIS/NEES 与 evidence path，字段缺失必须显式 unavailable |

P2/P3 内容保持原有规划；本轮不删除、不移动，也不新增完成声明。

## 19. 2026-07-12 P1 长 Replay 构造与汇总实施结果

本轮由 D1 owner 在既有 governed replay、Blocks/CV reader、`FusionAdapter`、latency/OOSM、
sensor health 和 region window 接口上增量实现，没有引入 Stone Soup/FilterPy，也没有修改
main/runtime 或其他模块：

- 新增 `LongReplayConfig`、`LongReplayScenario`、`LongReplaySummary`、
  `build_long_replay_scenario()` 和 `summarize_long_replay()` 公共入口。默认场景为 60 s、3
  目标 crossing，输入目标数来自配置，不写死 2v2/5v5。
- 场景同时覆盖距离相关雷达 covariance、crossing clutter、声学粗方位、EO 像素投影、完全/
  部分遮挡、传感器延迟、显式 OOSM 和 relay 重发；所有观测保留 measurement/arrival 双时间
  戳、covariance、NED 工作空间、coverage cell 和 source lineage。
- 冻结 `d1.long_replay_scenario.v1`、`d1.long_replay_config.v1`、
  `d1.long_replay_summary.v1`、`d1.long_replay_thresholds.v1` 和既有
  `d1.sensor_observation.v1`。provenance 继续携带 scenario/config digest、seed 和 run ID。
- online observation ID 与 lineage 只使用传感器本地不透明 payload 序号，不携带持久目标
  slot；六状态真值和 observation-to-truth 标签只进入独立
  `d1.long_replay_offline_truth.v1` sidecar，不能进入在线 `GlobalTrack`。
- 汇总复用 raw/fusion latency audit、sensor health 和固定区域窗口，导出 modality/event、track
  level、source support、truth leak 和 metric availability。没有 D2 canonical-ID 离线映射时，
  RMSE/NEES 明确输出 unavailable reason，不填 0、不使用 truth 辅助在线关联。
- 新增官方 `scripts/run_long_replay.py` 薄 CLI，支持 `--seed`、`--duration`、
  `--target-count` 和 `--output`；输出严格为 `LongReplaySummary.to_dict()` JSON，CLI 不复制
  场景、融合或汇总算法。

默认 smoke 为 843 条观测、21 次显式雷达 OOSM、6 次 relay 重复、29 个区域窗口、0 个在线
truth leak，验证主机耗时约 8.8 s。CLI 子进程测试覆盖参数透传、输出目录创建、JSON schema
和 truth 隔离；本轮 D1 全量为 `66 passed`。

因此本轮关闭 D1-owned 的“可由 main 调用的合成长 crossing/遮挡/延迟/OOSM replay 与汇总”
缺口。仍开放的 P1 是：main 采集真实 Blocks/CV 多 seed 长 replay；D2-confirmed canonical-ID
映射后计算 RMSE/NEES；真实 sensor-specific latency/health/window、camera/bbox、节点退出和
covariance 阈值标定；CV/CA/CT/IMM 及场景自适应 covariance 对照。P2 外部库安排不变。

## 20. P1 真实 AirSim dense/crossing 输入冻结落实（2026-07-12）

本轮在既有 governed replay 上增加不连接 AirSim SDK 的真实持久化输入边界：

1. loader 接受 JSON/JSONL 直接观测和 frame 内嵌观测，按输入长度处理。
2. freezer 只转换实际存在且满足 covariance、coverage 和 canonical frame 合同的观测；缺
   measurement 的遮挡、漏检或节点退出 frame 只记事件，不伪造量测。
3. online observation ID 改为不透明序号，递归剥离 actor/object/truth identity；truth ID 和
   NED position 只进入 evaluator-only sidecar。
4. measurement/arrival 严格必填；processing/publish、sensor health、scene/profile/source
   schema 缺失时显式 `unavailable`。事件覆盖 crossing、遮挡、漏检、虚警、OOSM 和节点退出。
5. writer 输出 governed manifest、records、offline truth 和 summary；CLI 只负责参数、digest
   和文件写出，不复制转换逻辑。

本阶段验收为 online truth leak 0、缺失量测伪造 0、5-target fixture 和任意长度输入可运行、
四类文件可被现有 reader 消费。后续仍需 main 提供真实 multi-seed payload，D2 提供离线
canonical mapping，D6 汇总 RMSE/NIS/NEES、latency、health 和区域窗口统计。本轮 D1 全量
回归在 sidecar follow-up 后为 `74 passed`。

### 20.1 Truth sidecar 唯一键修复

main + D2 端到端验证发现同一 `(truth_id, timestamp)` 可能同时来自 frame truth 和 observation
metadata。D1 在 sidecar 构造阶段按该二元组确定性归并：available position 覆盖 unavailable；
两个 available 在 `1e-6 m` 内视为同一值，超过容差直接拒绝冻结；不同 timestamp 独立保留。
仅有 identity 的样本继续保留为 unavailable，summary 显式输出 unavailable 数量，不插值、不
外推、不借用相邻帧位置。该规则保证 D2 strict adapter 不再因同键 available/unavailable 重复
拒绝整个 sidecar，同时不会掩盖真实 truth 冲突。

### 20.2 捕获 Provenance 强校验（2026-07-13）

D1 AirSim freeze 现在要求捕获文件显式携带 scenario/config version、seed、
`target_spacing_m` 和 `evidence_path`。目标间距只以捕获 provenance 为权威来源，不从 truth
几何反推；API/CLI 声明、跨 payload 声明与捕获值不一致时 fail closed。manifest/summary
输出字段 availability，在线 records 与 evaluator-only truth sidecar 通过 provenance digest
绑定。专项测试覆盖 4 m/2 m 各 20 seeds，D1 全量回归为 `79 passed`。截至 2026-07-13，main
已经完成对应的 40 个真实 AirSim episode，D2/D6 已分别消费冻结产物做离线关联标定和统一
汇总；该结果关闭的是输入冻结与证据可消费性，不代表真实传感器误差和长期融合精度已标定。

## 21. 2026-07-13 真实 Dense Crossing 证据与后续计划

### 21.1 已完成并作为当前基线

- main 在 ComputerVision 模式完成 nominal 4 m 与 tight 2 m 两组严格几何，各 20 seeds，共
  40 个真实 AirSim episode；每个 episode 51 帧，目标数为 5，默认不保存截图。
- D1 governed replay 在全部 episode 保留 `measurement_timestamp`、`arrival_timestamp`、
  covariance、NED 工作空间、source lineage、scenario/config version、seed、
  `target_spacing_m` 和 `evidence_path`。捕获声明与 API/CLI 或跨 payload 不一致时继续
  fail closed。
- evaluator-only truth sidecar 共 10,200 个样本，`online_truth_leak_count=0`。truth 只用于
  D2/D6 离线评分，不进入在线 D1 观测、`GlobalTrack` 或下游控制链。
- D6 统一报告把 `d1_dense_crossing` 标记为 `available`，并携带 schema、digest 与 evidence
  path；缺失指标仍保持 `unavailable`，不由 D1 或 D6 补零。
- D1 全量回归为 `79 passed`。双时间戳、协方差、NED、source lineage、governed replay、
  capture provenance 和 truth 隔离均属于已闭合且必须保持的回归合同。

### 21.2 仍开放的 P1

1. **真实传感器 challenge fixture**：现有 4 m/2 m 数据主要验证几何、冻结合同和离线身份
   评估输入，尚未覆盖可代表工程传感器的雷达/声学/EO 漏检率、虚警率、遮挡过程、异步采样
   率、sensor-specific latency 和故障注入分布。后续由 main 采集版本化长 replay，D1 只冻结
   实际观测，不为缺失帧伪造量测。
2. **长期质量与协方差治理**：需要在正常/故障多 seed 长 replay 上标定区域时间窗口、
   covariance growth、expected-latency/OOSM、sensor health、NIS/NEES 和
   `covariance_scale_reason` 的持续阈值；raw OOSM 或短窗口高协方差不得直接触发 D4 降级。
3. **协同融合运行时验证**：D1/D2-confirmed canonical-ID adapter、部分共享 lineage、节点
   退出和 3 -> 2 -> 1 质量退化仍需真实 replay。D2 未确认同一 `global_track_id` 时，D1
   继续拒绝跨平台 Track-to-Track 融合。
4. **D6 长期统计一致性**：当前 D1 summary 已可用，但仍需验证跨场景、跨 seed、长时运行
   时 schema、availability、evidence path、区域窗口和 RMSE/NIS/NEES 汇总的一致性。

### 21.3 P2 可选项

FilterPy、Stone Soup、UKF/IMM、OpenCV/GTSAM 协同几何后端和 ROS 2 `tf2`/
`message_filters` 继续作为隔离 benchmark 或后续工程适配项。当前未安装或未接入的后端必须
显式报告 `unavailable`，不得写成已实现，也不得替换 NumPy EKF/fixed-lag 默认路径。

## 22. 2026-07-14 P0 在线 Scene Truth 身份边界

### 22.1 D1-owned 实施结果

- 包顶层新增稳定 API：`anonymize_online_observations(observations, *, identity_tokens=(),
  stream_id="online")` 和 `assert_online_observations_identity_free(observations, *,
  identity_tokens=())`。
- 仿真器允许用 scene truth 生成噪声量测；生成完成后，main/runtime 必须先调用匿名化 API，
  才能把 `SensorObservation[]` 交给在线融合/关联。scene actor/object/truth/segmentation 身份不
  是在线算法输入。
- 匿名化递归删除身份键，清理嵌套身份值和 `classification_hint` 中的目标 token，并按 frame
  及帧内顺序重写 `observation_id`。source lineage 同样映射为不含目标名字的不透明 ID；原始
  lineage 相同的 relay 重复仍映射到同一匿名 lineage。
- 返回新对象并保持 measurement、covariance、`measurement_timestamp`、
  `arrival_timestamp`、sensor/camera geometry 及通信时间字段。返回前强制执行 fail-closed
  validator，任何残留身份键或已知 token 都会抛出 `ValueError`。
- dry-run、governed/offline evaluator 和 truth sidecar 原路径不改；offline evaluator 必须继续
  消费原 scene observation 对应的独立 sidecar，不得从匿名在线副本反推身份。

### 22.2 验收证据与边界

2026-07-14 专项场景包含两组各 2 条 EO 观测，仅替换 target/actor/truth 名字，measurement、
covariance、双时间戳、bbox、相机内外参和其余字段完全相同。验收阈值为匿名结果逐字段严格
相等、数值/相机几何逐元素不变、身份泄漏数为 0、人工注入泄漏必须拒绝、原离线 sidecar 标签
保持。专项 `4 passed`，D1 全量 `83 passed`，全部满足。

D1-owned P0 API 缺口关闭；main-owned 系统接线仍必须把该 API 和 validator 放在每个 scene
state 在线入口。若身份值没有出现在可识别身份键下，main 必须通过 `identity_tokens` 提供完整
token 集。该集成条件不改变以下开放 P1：真实 radar/acoustic/EO challenge 长 replay、区域/
协方差/健康持续阈值、D1/D2-confirmed 协同融合、D6 长期一致性，以及 CV/CA/CT/IMM 和场景
自适应 covariance 对照。

## 23. 2026-07-14 关联治理与固定滞后回放修复

### 23.1 已完成

- 同一物理观测者的一次扫描对同一航迹最多更新一次；扫描键包含 modality，合法雷达/声学/
  光电跨模态融合不互相阻断。
- 近期成熟航迹可在唯一候选条件下使用独立雷达重捕门限；多候选时抑制新 birth 并保留审计，
  不使用 truth/actor ID。
- 非测距观测增加笛卡尔状态修正审计；超门限观测拒绝更新，不通过伪造协方差提高确定性。
- fixed-lag 检查点改为滞后边界之前最近的已接受量测后验，保持原预测区间的过程噪声语义；
  更早到达的合法 OOSM 通过 origin/archive 重建检查点后继续传播。
- 新增 `d1.association_audit.v1` 计数和回归测试。2026-07-14 D1 全量 `87 passed`；main
  报告 AirSim runtime 全量 `134 passed`。

### 23.2 剩余 P1 与验收

1. 由 main 对同一 M5N2 seed-001 真实 episode 复跑或冻结输入重放，验证 D1 航迹数保持 2、
   不再生成历史 `global_track_003`，且 31.8 s 不再出现状态 teleport。
2. 在多 seed、交叉、遮挡、虚警和漏检场景标定雷达重捕门限、非测距修正门限及模糊 birth
   拒绝率；不得用离线 truth 参与在线关联。
3. 记录 fixed-lag 检查点边界滞后、回放长度和循环耗时，确认历史 archive 只服务迟到量测，
   不造成在线时间或内存无界增长。

## 24. 2026-07-14 Covariance 合同硬化批次计划

本批先收紧观测入口合同，不改变 NED 状态、双时间戳或 fixed-lag/OOSM 数值流程：

1. 为 `SensorObservation` 定义按 modality/measurement 的 covariance 维度，并统一校验有限、
   对称、半正定和维度正确；正式 online、versioned governed replay 与 AirSim freeze 路径对
   缺失或非法 covariance 一律 fail-closed。
2. 删除正式融合入口对缺失/非法 observation covariance 的静默 default/reset；保留合法
   covariance 的既有质量缩放和上下界治理行为。
3. 历史缺失 covariance 仅通过显式 offline legacy migration API 补齐，并在 observation
   metadata 中记录 migration mode、原始缺失原因、sensor model/default 标识及其参数来源；
   普通 legacy reader 不得无标记放行缺失 covariance。
4. 补充回归，覆盖 governed/online 缺失拒绝、非有限/非对称/非半正定/维度错误拒绝、显式
   offline migration provenance，以及当前合法正式 observation、NED、双时间戳和 OOSM 行为
   不变。

验收口径：D1 全量测试通过；非法 covariance 在进入滤波更新或 governed bus 前抛出明确
`ValueError`；迁移观测携带完整且可序列化的 imputation provenance；`git diff --check` 无
格式问题。完成后同步 README、PLAN、D1 GAP audit 和受影响 review，并把真实传感器 covariance
标定继续保留为开放项。

### 24.1 执行结果

2026-07-14 已完成统一 covariance validator、在线/序列化/AirSim freeze fail-closed 接线和
`migrate_offline_legacy_sensor_observation()`。正式入口拒绝缺失、非有限、非对称、非半正定及
modality 维度错误 covariance；显式迁移记录 mode、原始缺失原因、sensor model/default、参数
来源和生成输入，并被所有在线入口拒绝。合法 covariance 后续质量缩放、上下界、双时间戳、
NED 和 OOSM/fixed-lag 流程保持原行为。

验收日期为 2026-07-14；构造性合同测试无随机 seed，覆盖 radar 五类非法/缺失拒绝与一条
legacy migration，并保持 governed replay、现有合法 OOSM 和七条 AirSim freeze observation
回归。D1 全量结果 `92 passed`。本批关闭 covariance 合同硬化实现缺口；真实 radar/acoustic/
EO/lidar sensor-specific covariance 标定与长期 NIS/NEES consistency 仍为开放 P1。

## 25. P1 同帧批处理与 fixed-lag 重放预算（2026-07-14）

### 25.1 问题与约束

main 对最新 M5N2 seed-001 前 40 帧剖析显示 D1 占 episode bus 绝大部分时间。根因是同一
main tick 内 radar、EO、acoustic/lidar 等观测逐条调用 `process()`：每次关联都从活动历史
重建 measurement-time 状态，每次接受后又重放到发布时刻。同一/近同测量时刻因此重复遍历
同一 fixed-lag 历史。

本批必须保持：

1. 每条观测原始 `measurement_timestamp`、`arrival_timestamp`、covariance、frame、modality
   和 source lineage 不变；
2. 关联与 observer scan/source duplicate 门控逐条执行，不能用聚合均值替换量测；
3. 乱序和检查点前 OOSM 仍从合法 origin/archive 重建；
4. 输出在相同输入顺序下与逐条处理数值等价且确定；
5. 性能收益来自消除重复 replay，而非丢观测、改时间或缩短证据。

### 25.2 接口与实现

已实现 `FusionAdapter.process_batch(observations) -> FusionBatchResult`。处理顺序是调用方输入
顺序；每条观测仍做正式校验、延迟/健康审计和关联。批内状态缓存键为
`(global_track_id, history_revision, measurement_timestamp)`：未改变的航迹可复用同测量时刻
状态；某航迹接受新观测后仅该航迹 revision 失效。接受更新先写入权威 observation history，
批次末按 track ID 确定性排序，每个 dirty track 只做一次发布时刻重放。

检查点之前的新 OOSM 会标记 checkpoint dirty。若后续关联只查询检查点之前的时刻，直接从
origin/archive 计算；首次查询检查点之后状态或批次终结时才重建检查点，因此同批旧 OOSM 不会
无条件重复重建。`FusionBatchSummary` 记录实际 history/origin replay、cache hit/miss、每航迹
终结重放和 deferred update replay avoidance，供 main/D6 做性能审计。

main 接线方式：

```python
result = fusion_adapter.process_batch(observations_received_this_tick)
tracks = list(result.tracks)
batch_summary = result.summary.to_dict()
```

一个 batch 应对应 main 已收齐的同一 episode tick 输入，不应跨未来 tick 等待水位线，也不应
改写观测时间。`tracks` 只表示批末快照；若调用方需要每条观测中间状态，继续使用 `process()`。

### 25.3 验收结果与后续

- 构造验收：5 航迹、15 条 radar/lidar/acoustic 同帧观测；逐条 95 次 history replay，batch
  24 次，减少 74.7%；最终 state/covariance 在 `1e-9` 绝对容差内等价。
- fixed-lag 验收：先接收窗口内观测、再接收 checkpoint 前 OOSM，逐条与 batch 的 checkpoint
  timestamp/count、pre-checkpoint replay count、state/covariance 一致。
- 真实持久化输入：M5N2 seed-001 baseline 前 40 帧、786 条观测；逐条 18.05 s/1267 次，
  batch 5.70 s/351 次，3.17 倍加速，state/covariance 最大差为 0。
- 2026-07-14 D1 全量：`98 passed`；`git diff --check` 通过。

D1-owned P1 实现已完成。剩余系统 P1 由 main 把逐条调用替换为每 tick 一次 batch，复测完整
245/248 帧、记录 D1 与总 loop 分项耗时并做多 seed；在该证据完成前不能宣称 100 ms 实时预算
闭合。
