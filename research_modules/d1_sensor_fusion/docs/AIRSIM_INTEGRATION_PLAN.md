# D1 AirSim 集成计划

## 0. 在线证据发布边界（2026-07-25）

- D1 固定滞后回放前缀累计摘要候选已经完成三维质点正式评估。producer clean commit 为
  `7d2e987471b521a1e531bf03a5c99af5096f676a`，matrix SHA-256 为
  `85432d729877eff97e6f3dd517d4baa7a47f44a4fa42e6bfdc7ce85b8d9ec74b`。
  short seeds 1151-1160、long seeds 1151-1153 共形成 13 pair/26 个 fresh episode；
  场景为 200 个目标、200 个资源和 2 个侦察节点。
- D6 verdict 为 `reject`，`main_default_promotion_allowed=false`，
  `system_realtime_gap_closed=false`。reference `per_checkpoint_prefix_rebuild_v1`
  继续作为默认，candidate `fixed_lag_checkpoint_prefix_cumulative_summary_v1` 保持
  默认关闭。候选最低 RTF 为 `0.197441`。
- 正式失败门为 short 更快 `5/10 < 8/10`、short D1 改善
  `0.959611% < 1%`、short bootstrap 上界 `0.619827% > 0%`、short core 改善
  `-0.256641% < 0.25%` 和 long core 改善 `-1.930083% < 0.25%`。13/13 语义、
  consistency、原 operation counts、实现身份、诊断守恒和真值隔离通过，不能覆盖性能门
  失败。
- 该正式矩阵只覆盖三维质点仿真，不是 AirSim 证据。AirSim producer、观测 DTO、双时间戳、
  covariance、NED、`GlobalTrack` 和 episode 数据合同没有改变，也没有因该候选获得实时
  准入。
- main/runtime bus 的在线 publication 若只需要当下证据视图，应调用
  `consistency_evidence_snapshot(observation_ids=None)`。该接口返回精确不可变记录，并在
  candidate 启用时非破坏性叠加 pending replay counter；不得返回陈旧
  `replay_count/replay_revision`。
- episode 最终离线证据导出继续调用 `consistency_evidence_records()` 或
  `export_consistency_evidence()`。两者保留全量精确物化语义，完成后 pending ledger
  必须为 0。
- 当前 D1-owned 模块测试已覆盖重复 snapshot、append 后 snapshot、snapshot 后中间迟到
  量测、子集 ID 和最终导出。scalable 三维质点正式矩阵已经使用 snapshot，并保持最终
  evidence digest、operation counts 和 ledger 守恒；在线路径仍全量投影构造 `656481`
  条记录。AirSim runtime 尚无同配置 A/B 证据。
- main 三维质点模块栈已实现独立 selector：
  `full_consistency_snapshot_v1`/`required_observation_subset_v1`，默认保持 reference。
  required ID 来自同一 release cycle 的 source observations 与 materialized tracks
  `latest_observation_id`；未知/非法 ID 回退 full，selector/config/diagnostics 与 CLI
  已接入，空 required 集合回退 full 已由 main 专项覆盖。模块栈回归为 `62 passed`，
  scalable 全量为 `263 passed`。
- 上述实现尚未接入 AirSim runtime，也没有 AirSim 同配置 A/B、clean 200/200/2 smoke、
  正式矩阵或 D6 判定。后续 AirSim 接线仍需验证 ID 所有权、fallback/lookup miss 为 0、
  最终全量导出和 episode reset 隔离；不得改写前一三维质点 `reject`。
- 该 API 区分只改变证据读取成本，不改变 6 秒 fixed-lag、量测更新、NIS、门控、后验或
  AirSim sensor adapter。模块微基准不能替代 AirSim episode 性能证据。

## 0. 协方差发布合同更新（2026-07-24）

- D1 已在观测和航迹公共限制路径增加完整正半定治理。AirSim 上游 DTO、相机/雷达适配器、
  双时间戳、NED 和来源谱系字段不变。
- 在线观测 covariance 仍在入口执行有限、对称和正半定 fail-closed 校验；D1 不接收非法
  AirSim producer covariance 后静默修复。
- 滤波预测、更新和 fixed-lag 重放生成的航迹 covariance 在发布前执行对角范围、逐对相关和
  完整正半定治理。projection reason 和操作数进入航迹 metadata，可由 main/D6 统计。
- 当前正式证据已扩展为 short seeds 1101-1110（2.2 s）和 long seeds 1101-1103
  （10 s）的 13 组配对、26 个三维质点 episode；26/26 正常退出且 13/13 跨构建检查通过。
  该矩阵仍不是 AirSim。正式 manifest SHA-256 为
  `40669d10fff8367aa31e24624bab802d8bc3de6b01aaa1e5c92d054753ed93ec`。
- D6 已准入向量化优化，但 `system_realtime_gap_closed=false`，三维质点 candidate 最低
  实时因子为 `0.143397`。该状态不能外推为 AirSim 或目标硬件实时性。
- 后续 AirSim 复跑需显式统计 PSD projection/fallback 次数、D1 fusion P50/P95、总 tick 和
  RSS；fallback 大于 0 时应保留对应输入作为传感器/数值故障 fixture。三维质点准入不能
  替代 AirSim 或目标硬件周期证据。
- 不得通过放宽 D2 PSD 门、增大容差、丢检测、缩短 6 s fixed-lag 或读取 actor/truth ID
  消除异常。

## 0. 融合性能接口状态（2026-07-22）

- D1 默认启用非雷达创新协方差矩阵栈。该变化位于
  `Scalable3DFusionAdapter.process_scan_batch()` 内部，AirSim producer、runtime bus、
  topic、reset 顺序和 `SensorObservation` 字段不变。
- 未见 seed 1000 的三维质点冻结输入含 771 个扫描和 11,889 条匿名观测。完整回放纯融合墙钟
  `50.458 -> 39.994 s`，逐扫描摘要、终态航迹、一致性证据、操作计数和累计诊断相同。
  该输入不是 AirSim 证据，不能替代 Blocks/CV/SimpleFlight 复跑。
- 后续由 main 在同一 AirSim 输入上比较新旧开关，至少报告 D1 fusion、scan input、总 tick、
  实时倍率和 RSS。D1 不通过减少检测框、跳扫描或改变 `measurement_timestamp`、
  `arrival_timestamp`、covariance、NED、门限和 `global_track_id` 所有权换取速度。
- AirSim 上游无需新增配置项。若 NumPy 对异常矩阵栈拒绝批量伪逆，D1 会在该扫描内回退逐候选
  求解；错误不会通过放宽门控或删除观测被隐藏。

## 0.1 历史权威状态（2026-07-15）

- main 已完成真实 AirSim M5N2 baseline/candidate 各 10 case，共 20 case；在线
  `truth_identity` 与 `truth_state` 使用计数均为 0。
- 20 case 共记录 3,805 个 main-bus tick。D1 fusion mean/P95/max 为
  `320.00/451.46/1234.88 ms`，是 main-bus 内层主导阶段；100 ms 运行预算未闭合。
- 当前 AirSim 接入必须继续保留 `measurement_timestamp`、`arrival_timestamp`、合法
  covariance、NED、source lineage 和 offline truth sidecar 隔离。运行时优化不得通过丢弃观测、
  改写时间或收紧 covariance 实现。
- 本批的实际执行和时序证据可用，但 NIS、NEES、RMSE 及 sensor-specific latency/dropout
  consistency 不可用，后续必须另建传感器标定 case，并显式报告 availability。
- M5N2 达到 20/20 后已停止多 seed 批次；TERM 生效前额外完成的 1 个
  `png_ttc_2v2_seed001` 排除，dropout 完成数为 0。

下一步 AirSim 集成优先级是：在相同冻结输入和同一 20-case 规模下继续拆分 D1 的观测数、
航迹数、fixed-lag replay/cache/finalization 成本；由 main 复测完整 control tick。不得以此前
D1-only 3.17 倍重放加速替代真实运行时验收。

### 0.2 历史 Dense Crossing 状态（2026-07-13）

- strict dense crossing 已完成 nominal 4 m 与 tight 2 m 各 20 seeds，共 40 个真实 AirSim
  episode；每个 episode 51 帧、5 个目标。
- D1 governed replay 在该批证据中保留 `measurement_timestamp`、`arrival_timestamp`、
  covariance、NED、source lineage、scenario/config version、seed、`target_spacing_m` 和
  `evidence_path`。
- evaluator-only truth sidecar 共 10,200 个样本，`online_truth_leak_count=0`；truth 不进入
  在线 `SensorObservation`、`GlobalTrack` 或控制链。
- D6 统一报告中 `d1_dense_crossing=available`，schema、digest 和 evidence path 可追溯；
  D1 全量回归为 `79 passed`。
- 当前下一阶段不再重复建设 dense crossing freezer，而是采集真实漏检、匿名虚警、遮挡、
  异步采样率、sensor-specific latency/故障样本，并校准区域时间窗和协方差长期治理阈值。
- ROS 2 `tf2/message_filters`、OpenCV 标定、Stone Soup 和 FilterPy 仍未进入当前在线路径，
  继续作为 P2/P3 可选集成或隔离 benchmark。

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
2. runtime 可使用 actor scene state 生成带噪 simulation-derived observation，但须将 truth 标签保存在独立 evaluator-only sidecar。
3. runtime 调用 `anonymize_online_observations()`，并用 `assert_online_observations_identity_free()` fail closed 验证后，才可将在线观测写为 D1 JSONL record 或送入融合；未出现在身份键下的 scene 名称须通过 `identity_tokens` 提供。
4. D1 使用 `read_blocks_sensor_observations_jsonl()` 读回匿名观测，并按 `arrival_timestamp` replay。
5. 分别运行 latency-compensated 与 uncompensated fusion，比较 RMSE、连续性、分级准确性和延迟补偿效果；RMSE 的 truth 只在滤波后由离线 evaluator 对齐。
6. 对 N actor 合同，D1 应按输入数组长度输出对应 `GlobalTrack[]`，不依赖 2v2/5v5 固定数量。
7. 评估结果可交给 D6 汇总；D1 已提供 replay schema v1/legacy JSONL 兼容、最小 CSV reader、`LatencyAuditSummary`、轻量 `FusionQualityRegionSummary`、`FusionQualityRegionWindowSummary` 和协方差增长率 helper，后续仍需与 D6 对齐长期批量 schema、真实多 seed 阈值和固定真实样本回归。

## 7. 对 D2-D7 的接口影响

- **D2**: 使用 D1 的 `global_track_id`、协方差、时间戳和 `source_support` 做关联连续性；truth ID 只作为离线标签，不能替代在线 `id_switch_count`。
- **D3**: 使用 `track_level`、`a95_m`、`measurement_age_s` 和 source diversity 判断分配候选质量；D3 仍负责版本化 `AssignmentPlan` 和 stale plan 拒绝。
- **D4**: 可消费 `TrackUncertaintySummary`、`LatencyAuditSummary`、轻量 `FusionQualityRegionSummary` 和 `FusionQualityRegionWindowSummary` 做态势质量判断；D1 不输出区域级主动降级仲裁，最终降级仍由 D4 结合 C2 health、D3 版本和 D5/D7 反馈决定。
- **D5**: 可用 D1 的 NED 航迹、协方差、EO bbox/camera metadata lineage 做投影门控；D5 不得改写 `global_track_id`。
- **D6**: 可统计 D1 RMSE、连续性、分级、latency ablation、`TrackUncertaintySummary`、`LatencyAuditSummary`、`FusionQualityRegionSummary`、`FusionQualityRegionWindowSummary`、source diversity 和 duplicate count；剩余 P1 是长期批量 schema、真实多 seed 持续阈值和真实样本回归。
- **D7**: 只应使用 `stable`/`handover` 航迹作为离线中段导引输入，并根据协方差和 freshness 门控；D1 不提供飞控或自动处置接口。

## 8. 后续 P1/P2

### P1

- 已完成 governed replay/schema/provenance、legacy JSONL 兼容、最小 CSV reader/replay、
  latency/OOSM audit、区域质量/窗口摘要、协方差增长率 helper、`ReconCueSummary`，以及 4 m/2 m
  各 20 seeds 的真实 AirSim 输入冻结。40 episode 的在线 truth 泄漏为 0，D6 source 已为
  `available`。
- 由 main/shared runtime 采集版本化真实 challenge fixture，显式覆盖 radar/acoustic/EO 的
  漏检、匿名虚警、部分/完全遮挡、异步采样率、sensor-specific latency、故障注入和节点退出；
  actor/truth identity 只进入 evaluator-only sidecar。
- 在正常/故障多 seed 长 replay 上校准区域时间窗、freshness/source-gap、covariance growth、
  expected-latency/OOSM、sensor health、handover readiness、NIS/NEES 和
  `covariance_scale_reason` 的持续阈值。
- 与 D6 保持长期批量 JSONL/CSV schema 对齐，稳定消费 `TrackUncertaintySummary[]`、
  `LatencyAuditSummary`、`FusionQualityRegionSummary[]`、`FusionQualityRegionWindowSummary[]`
  和 evidence availability；缺失项不得补零。
- 保持 D1 不直连真实 AirSim runtime bus，由 main/shared runtime 继续拥有 AirSim 启停和日志写出。

### P2

- 可选接入 FilterPy EKF/UKF 对照，验证与 NumPy fallback 的误差和协方差一致性。
- 可选接入 Stone Soup OOSM/JPDA/MHT/Track Fusion 离线实验，先做指标对照再决定是否扩大使用。
- 与 D5 对齐 OpenCV calibration/projectPoints/solvePnP 边界。
- 等 ROS 2 runtime、tf tree、topic schema 和 bag/replay 稳定后再评估 `tf2/message_filters`。

## 9. 2026-07-14 在线身份边界验收

D1 包顶层已导出 `anonymize_online_observations()` 和
`assert_online_observations_identity_free()`。仿真 scene state 可以生成噪声 measurement，但
actor/object/truth/segmentation 身份只能进入 evaluator-only sidecar，不能进入在线 D1/D2。
匿名化保持 measurement、covariance、双时间戳和 sensor/camera geometry，并重写 observation
ID/source lineage；validator 对残留身份 fail closed。

验收场景为两组各 2 条 EO observation，只更换 target/actor/truth 名称，几何和其余字段完全
一致。阈值是匿名输出逐字段严格一致、几何逐元素不变、泄漏为 0、注入泄漏必须拒绝；专项
`4 passed`、D1 全量 `83 passed`。D1-owned P0 API 已关闭，main-owned runtime call-site 接线仍
是系统完成条件。开放 P1 仍为真实 challenge 长 replay、持续阈值、协同融合和 D6 长期统计，
本次没有启动 AirSim、保存截图或改变 episode 编排。

## 10. 关联治理修复后的 AirSim 验收项（2026-07-14）

历史 M5N2 seed-001 产物显示 31.3 s 出现第三条 D1 航迹，31.8 s 既有航迹发生大幅状态变化。
D1 已完成同扫描唯一更新、雷达唯一重捕、模糊 birth 抑制、非测距修正审计和事件对齐 fixed-lag
检查点修复。D1 全量 `87/87`，main 报告 runtime 全量 `134/134`，说明接口和 episode 编排
没有测试回归。

真实场景关闭条件仍由 main 执行：使用相同设置和 seed 重跑，在线路径继续禁用 truth hints，
检查航迹总数、birth/reacquisition/suppression 计数、31.8 s 状态步长、双时间戳、协方差和
source lineage。只有航迹保持 2 且状态跳变消失后，才能把该 P1 episode 缺口标为关闭。

## 11. AirSim Covariance Freeze 边界（2026-07-14）

main 持久化的每条 radar/acoustic/EO/lidar candidate 必须在 freeze 前携带对应
`4x4/1x1/2x2/3x3` covariance，且矩阵有限、对称、半正定。freezer 不生成、reshape、对称化或
重置 covariance；非法 candidate 进入 `rejected_observations`，不得成为在线 record。带
`covariance_imputation_provenance` 的 offline legacy observation 同样禁止冻结到在线总线。

现有七条合法 AirSim freeze fixture、双时间戳、NED/pixel 输入、coverage/source lineage 和
OOSM 回归在 2026-07-14 D1 全量 `92/92` 中保持通过。本轮没有启动真实 AirSim，也没有改变
launch/reset/episode 顺序。main 后续真实 writer 必须直接提供传感器模型 covariance；历史缺值
只能先走 D1 显式 offline migration，并且只能用于 evaluator。

## 12. main 每帧批量调用接入（2026-07-14）

最新 M5N2 seed-001 的 main profiling 表明逐条 `FusionAdapter.process()` 会让相同 tick 的多模态
量测重复触发 fixed-lag 历史重放。D1 已提供正式 `process_batch()`，但按模块边界本轮没有修改
`research_modules/airsim_runtime/**`。main 应在已经生成、匿名化并校验完整个 tick 的
`SensorObservation[]` 后一次调用：

```python
d1_result = fusion_adapter.process_batch(sensor_observations_for_frame)
global_tracks = list(d1_result.tracks)
d1_batch_summary = d1_result.summary.to_dict()
```

接线约束：

1. batch 边界是当前 episode frame/tick，不跨 tick 等待，也不改变列表内到达顺序；
2. 继续保留 radar latency 产生的真实 measurement time，不把它改成 frame arrival time；
3. 不在 main 预去重独立观测，D1 只按 source lineage 去掉真正 relay duplicate；
4. main 发布 `tracks` 前可记录 summary，但 D6 离线报告不能阻塞控制循环；
5. 保留逐条路径作为对照开关，使用同一持久化输入比较状态、covariance、track ID、OOSM 和耗时。

D1-only 接入前验证使用既有 M5N2 baseline seed-001 前 40 帧、786 条 observation：18.05 s
降至 5.70 s，history replay 1267 降至 351，状态和 covariance 最大差为 0。main 验收仍需覆盖
完整 245/248 帧及至少 10 seeds，并拆分 observation generation、D1、D2-D7、日志和 D6 离线
报告耗时。只有完整 loop 达到项目预算后才能关闭系统实时性能 P1。

## 13. Consistency evidence 合同影响检查（2026-07-20）

D1 已实现通用 `export_consistency_evidence()`、独立 truth sidecar、D2 evaluator-only
observation-lineage mapping adapter
输入和离线 RMSE/NEES/NIS coverage evaluator，但本轮目标是 scalable 3D 质点总线合同，没有
修改 `research_modules/airsim_runtime/**`、Blocks launch/reset/episode 顺序、相机截图策略或
AirSim persisted observation schema，也没有启动 AirSim。

因此 2026-07-15 M5N2 20-case 和现有 AirSim freeze 报告中的 NIS/NEES/RMSE availability 结论
不变：main writer 尚未持久化 online evidence bundle，D2 尚未为这些 episode 产出 digest-bound
lineage mapping adapter，不能回填为 available。后续若接线，main 应在每个 episode 结束后单独写
online bundle、truth sidecar、D2 mapping 和 offline result；在线文件不得包含 truth/actor/object
字段，D6 必须按 availability 聚合。该后续接线和真实 AirSim 多 seed 标定均为 main-owned 开放项。

## 14. main-owned 可扩展三维扫描接入（2026-07-22）

本节给出 main 的推荐调用合同，不修改 `scalable_3d_simulation` 或 AirSim runtime 文件。对于
每个按 arrival 顺序到达的 `OnlineSensorBatch`：

```python
observations = sensor_observations_from_online_batch(online_batch)
frame = SensorScanFrame.from_observations(
    observations,
    scan_id=online_batch.batch_id,
)
decision = scan_organizer.ingest(frame)

for fusion_time, scans_at_time in group_by_fusion_timestamp(decision.released_scans):
    last_state_result = None
    for scan_index, released in enumerate(scans_at_time):
        state_result = fusion_adapter.process_scan_batch(
            released.observations,
            materialize_tracks=False,
        )
        if scan_index + 1 < len(scans_at_time):
            publish_d1_audit(
                tracks_materialized=False,
                tracks=[],
                track_count=0,
                current_track_count=state_result.current_track_count,
                summary=state_result.summary.to_dict(),
            )
        last_state_result = state_result
    if last_state_result is not None:
        snapshot = fusion_adapter.materialize_global_tracks()
        full_payload = last_state_result.to_dict()
        full_payload.update(snapshot.to_dict())
        persist_full_d1_publication(full_payload)
        publish_fused_tracks_to_d2(snapshot.tracks)

write_scan_events(decision.events)
write_scan_audit(decision.audit)
```

调用约束：

1. 一个 batch 构造一个 `SensorScanFrame`，不得按检测点拆帧；batch 内 sensor、modality、双时间戳
   和 scan ID 必须一致。main 冻结后的嵌套 `mappingproxy` 相机元数据可直接输入；D1 会建立
   独立只读快照，不要求 main 解冻或转成普通字典。
2. 所有 measurement/arrival time 必须先归一到统一 episode clock，观测 frame 必须先满足 D1
   canonical 合同；organizer 不估计 clock offset，也不执行 tf/外参变换。
3. `ingest()` 每个到达批次调用一次。只有 `released_scans` 可进入 `process_scan_batch()`；
   buffered/rejected 扫描不能直接送 D2。
4. episode tick 前进但没有扫描时，调用 `advance_arrival_time(current_episode_time)`。该调用只
   清理超过 `max_buffer_residence_s` 的帧，不推进 measurement watermark。
5. producer 全部结束后调用一次 `close()`。必须处理 `close_result.released_scans`，再结束 D1
   和 D2；否则尾部合法扫描会留在窗口中。
6. 每个 episode manifest 固定 scan input 五个 schema 版本和 `ScanInputConfig.to_dict()`；逐帧
   `events`、累计 `audit`、D1 fusion summary 分开写入日志。
7. D6 可统计 too-late、reordered、buffer peak、overflow 和 expiry。未经长 episode 标定的计数
   不直接触发 D4 主动降级。
8. `group_by_fusion_timestamp()` 是 main 调度侧按融合时刻分组的伪代码，不是新增 D1 API。同一
   fusion timestamp 的每个扫描仍按顺序调用 state-only 接口；不得把扫描拼接。中间日志为
   `tracks_materialized=false`、`tracks=[]`、`track_count=0`，实际内部航迹数写入
   `current_track_count`。D2 v1 可继续校验数组长度，且不会把未物化记录当成规范航迹快照。
9. 每个 fusion timestamp 只在末次后验调用一次 `materialize_global_tracks()`。完整发布的 `track_count`、
   `current_track_count` 和 `len(tracks)` 必须相等。旧日志无 `tracks_materialized` 时按完整快照
   解释；`tracks=None` 仅由 D1 audit 作为过渡兼容输入，不作为新 writer 推荐格式。

推荐初始参数只可作为开发配置，不可写成传感器指标。`max_lateness_s` 应覆盖正常 sensor-specific
抖动而不是平均固定链路延迟；`max_buffer_residence_s` 和数量上限需按扫描率、传感器数、最大 N
及日志压力共同计算。20/50/100/200 长 episode 各自记录水位线、缓冲峰值、误拒、尾部释放和
处理耗时后再冻结 profile。

`ScanInputOrganizer` 和延迟物化接口均为纯 Python 合同，不依赖 AirSim SDK。延迟物化构造回归
覆盖三目标四扫描、默认 6 s fixed-lag 和检查点前 OOSM；D1 全量 `168 passed in 29.43s`。本轮
没有启动 Blocks/CV、没有修改 settings、launch/reset 或
episode 顺序。随后 main 从 clean 提交
`e4d66db02a0b8f1b867a0e81b4a73de84588426b` 对 scalable 快速治理路径完成
20/50/100/200 各 5 seed 的 formal 复跑；20/20 `repository_dirty=false`，扫描拒绝、过旧和
溢出均为 0。该结果只更新非 AirSim 的治理接线状态。真实 Blocks/CV/SimpleFlight 适配、
settings、传感器桥接、launch/reset 和多 seed AirSim 验收计划均无变化，仍由 main 负责。

随后 clean 候选 `8f86192` 已在 200v200 三维质点 10 s seeds 42000-42002 验证上述按
fusion timestamp 延迟物化合同；3/3 clean、finite、在线 truth 使用 0，D1 全量回归为
`168 passed`。该证据不表示 AirSim writer 已采用此模式，也不改变前述 AirSim 开放项。
