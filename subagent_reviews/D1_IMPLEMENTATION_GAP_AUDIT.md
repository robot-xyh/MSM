# D1 实现差距审计

**模块**: D1 多传感器融合与目标配准  
**范围**: 对照 `subagent_reviews/D1_SENSOR_FUSION_REVIEW_AND_PLAN.md`、`C_UAS_MAINSTREAM_SOLUTIONS_AND_DIFFICULTIES.md`、`research_modules/d1_sensor_fusion` 源码和测试，审计共识算法、开源方案和当前实现差距。  
**边界**: 本审计只覆盖离线科研仿真、数据合同、传感器观测、航迹融合和评估接口；不涉及真实飞控、硬件驱动、火控、毁伤或自动处置。

**更新时间**: 2026-07-09。

## 1. 总体结论

D1 当前已经实现了可运行的轻量主线：`SensorObservation -> NumPy EKF/FusionAdapter -> GlobalTrack`，支持雷达、声学、EO、可选合成 LiDAR，具备测量时刻/到达时刻分离、fixed-lag replay 延迟补偿、可参数化距离/置信度相关协方差、AirSim dry-run fake fixture 与 schema 检查、跨节点通信元数据、source lineage 去重基线、`TrackUncertaintySummary` 导出、replay schema v1/legacy JSONL 兼容、最小 CSV reader/replay、真实 Blocks/CV 字段保真、raw replay latency/OOSM audit helper、`LatencyAuditSummary`、`SensorHealthSummary`、协方差 floor/ceiling reason、covariance scale reason passthrough、timestamp uncertainty、轻量 `FusionQualityRegionSummary`、`FusionQualityRegionWindowSummary` 和 `ReconCueSummary` 粗指向摘要。D1 接收 main 提供的 N 个 target truth/观测源，并按输入数组长度处理 `SensorObservation[]` 与 `GlobalTrack[]`；真实 AirSim runtime bridge 仍由 shared/main 层负责，D1 不直连 AirSim。

尚未实现的主要是外部成熟框架集成：Stone Soup、FilterPy、ROS 2 `tf2`、`message_filters`、UKF、IMM、D1 包内真实 AirSim ComputerVision/Blocks 运行时适配。这些目前有文档计划或占位类，但未作为 D1 运行依赖接入。原因主要是当前阶段强调依赖轻、可复现、离线测试稳定，且缺少 ROS 2 runtime、稳定真实 AirSim detection schema/外参标定链路、长期真实样本回归和多模型评估基准。

优先级建议已同步 `EVAL/FRAMEWORK_EVAL_P0_P1_P2_GAP_CONFIRMATION.md` 中的 D1 P0/P1 口径：

- **P0**: 无运行级 P0 blocker；当前 NumPy EKF、传感器观测模型、延迟补偿、AirSim dry-run、`measurement_timestamp`/`arrival_timestamp`、协方差和 NED `GlobalTrack` 合同均作为持续回归基线维护。EVAL 确认的 D1 工程化 P0-A 已实现：FDIR-light、协方差上下界限制和时间戳不确定性建模已进入代码与接口回归；后续若真实多 seed/闭环样本发现未覆盖验收场景，按第 1.2 节的最小验收口径进入 P0 backlog。
- **P1**: `TrackUncertaintySummary` 发布/导出、Blocks JSONL replay reader、可配置雷达协方差参数、source de-dup 基线、schema v1/legacy JSONL 兼容、covariance-required CSV reader/replay、latency/OOSM audit、raw replay latency/OOSM helper、轻量区域质量摘要、区域窗口/协方差增长 helper、`ReconCueSummary` 粗指向摘要、真实 CV bbox/camera/detection metadata 保真、covariance scale reason passthrough、secondary/mobile recon cue metadata 保真和嵌套 EO camera metadata replay 已完成；EVAL 确认的剩余 D1 P1 是 IMM/CV-CA-CT 多模型滤波、场景自适应协方差和 Track-to-Track 融合原型，另继续补更多 main/shared AirSim multi-seed CV detection fixture、D6 长期批量 schema、持续阈值和真实样本回归。2026-07-09 复核确认，D1 可读取真实 Blocks JSONL/CSV replay，并保留 multi-seed calibration 需要的 `measurement_timestamp`、`arrival_timestamp`、covariance、NED state、source support、latency/OOSM audit、区域质量摘要、区域窗口摘要、covariance scale reason 和二级/移动侦察相机 cue 字段；Stone Soup、FilterPy、MATLAB 等只作为对照或工程参考，不是当前 P0 依赖。
- **P2**: 接入 Stone Soup/FilterPy/OpenCV/UKF/IMM 作为离线对照，不替换 NumPy fallback；ROS 2 `tf2/message_filters` 和真实 AirSim bus 直连只有在运行环境、topic schema 和 main/shared runtime 合同稳定后再评估。

2026-07-08 补充复核：main runtime 已新增 P1 D4/D5 calibration sweep，并在 sweep 结束后自动生成 D6 标准报告 bundle。该能力属于 main/D6 集成层，不改变 D1 职责边界。D1 当前 P1 重点是保持 replay schema、measurement/arrival timestamp、covariance、latency/OOSM audit、区域质量/窗口摘要和二级侦察 cue 字段稳定，并继续补真实 AirSim multi-seed fixture 与阈值校准样本。

2026-07-09 补充复核：D1 已补齐 main P1 缺口方案中的轻量输入支撑项，包括 dry-run fixture schema version 检查、raw replay observation latency/OOSM audit helper、unsupported JSONL schema 回归、`covariance_scale_reason` passthrough 以及 secondary/mobile recon cue metadata 在 JSONL/CSV reader 和 `GlobalTrack.metadata` 中的保真回归。`SensorHealthSummary`、协方差上下界 reason 和 `timestamp_uncertainty_s` 继续作为已实现 P0-A 质量证据提供给 main/D6；P1 calibration sweep/D6 bundle 对 D1 的消费口径是汇总 observation latency、OOSM、区域质量、窗口趋势、sensor health、covariance reason 和 timing uncertainty，不由 D1 触发主动降级。剩余 P1 不再是这些轻量字段本身，而是更多 main/shared 真实 multi-seed Blocks/CV 样本、D6 长期批量 schema、持续阈值和算法增强项。

## 1.1 2026-07-07 P1 复核结论

本次复核背景是 main runtime bus 已将真实 AirSim D7 执行结果回灌到正式 episode metrics，D3 补充了中心重规划后的新 `AssignmentPlan` owner/version 元数据，D4 将主动降级硬风险与软质量风险拆分，D5 修正了终端一致性窗口的 key。D1 侧结论如下：

- **2026-07-08 状态确认**: 无 P0 blocker。`ReconCueSummary` 与 `summarize_recon_cue_from_tracks()` 已进入已实现基线，可从 `GlobalTrack[]` 或 track-like dict 输出移动高空侦察节点的 radar/global-track cue，并保留 measurement/arrival timestamp、协方差和 NED 合同。
- **无新增运行级 P0**: D1 的 `SensorObservation -> FusionAdapter -> GlobalTrack -> TrackUncertaintySummary` 合同仍满足下游输入要求，测试仍应作为 P0 回归；EVAL 工程化 P0-A 硬化项已按 1.2 和第 7 节闭合。
- **D4 接口语义收紧**: D1 的协方差、freshness、latency、source support 和 handover readiness 只能作为态势质量证据。单帧 `coarse/stable` 波动、短时 latency 或低 handover readiness 不应被 D4 直接解释为中心节点失效或立即主动降级；D4 需要结合 D3 plan freshness、D5 terminal evidence、C2 health 和持续窗口仲裁。
- **D3/D7 使用边界不变**: D3 可把 D1 质量摘要纳入分配代价和 replan 依据，D7 可按 `stable/handover`、协方差和 freshness 做导引门控；D1 不生成 plan version，也不修改 D7 PN/PNG 控制律。
- **D5 使用边界不变**: D1 继续提供可投影的 NED state、6x6 covariance、EO bbox/camera metadata lineage 和时间戳。D5 的跨视角/终端一致性结果只能作为反馈证据，不能反向改写 D1 的 `global_track_id`。
- **严格 subagent 流程**: D1 owned 代码、README、PLAN、GAP 和 review 的能力状态由 D1 子智能体自己检查、修改和测试；main 只汇总与集成验证。若 main 临时代改 D1 文件，后续必须由 D1 复核并同步文档状态。


## 1.2 EVAL P0/P1 同步口径

本节只同步 EVAL 确认的 D1 P0/P1，不新增、移动或改写下方既有 P2/P3 项。P0 口径为工程化硬化项，不是当前仓库测试运行级 blocker；P1 口径为三个月内能力增强和多 seed 标定项。Stone Soup、FilterPy、MATLAB 等外部工具仅作为对照或工程参考，不是当前 P0 依赖。所有后续实现必须继续保持 D1 合同：`SensorObservation[]` 和 `GlobalTrack[]` 按输入数组长度处理，2v2/5v5 只作为 baseline 名称；观测和航迹保留 `measurement_timestamp`、`arrival_timestamp`、covariance，并以 NED 为融合工作坐标系。

| EVAL 优先级 | D1 条目 | 当前 D1 状态 | GAP 同步结论 | 最小验收口径 |
|---|---|---|---|---|
| P0-A | FDIR-light | 已实现传感器级 `SensorHealthSummary`，从延迟/OOSM、stale、低质量/遮挡、异常协方差和重复观测派生 health/status、fault reason、reject count、isolation hint 和 recovery state | 已实现，保持现有门控和摘要基线回归；若故障恢复/隔离建议在真实样本中缺字段，则作为 P0 backlog 补齐 | 故障注入下输出 sensor health、fault reason、reject count、isolation hint 和 recovery state |
| P0-A | 协方差上下界限制 | 已实现观测 covariance floor/ceiling、低质量/遮挡协方差放大、track 6x6 covariance floor/ceiling 和 reason metadata | 已实现，保持 covariance 输出、floor/ceiling reason 和质量分级回归；若低质量/遮挡/外推场景缺 reason，则作为 P0 backlog 补齐 | 协方差不发散、不虚假收敛；D6/报告能解释 floor/ceiling reason |
| P0-A | 时间戳不确定性建模 | 已实现 `SensorObservation.timestamp_uncertainty_s` 标准化，并在观测 metadata、`GlobalTrack.metadata`、`TrackUncertaintySummary` 和 `SensorHealthSummary` 中导出 timing uncertainty | 已实现，保持双时间戳合同和 timing uncertainty 回归；若 D6 延迟报告无法消费，则作为 P0 backlog 补齐 | 注入 10-50 ms 时钟漂移时输出 timing uncertainty，并能关联误差变化曲线 |
| P1 | IMM/CV-CA-CT 多模型滤波 | 当前 CV/EKF 主线可用；CV/CA/CT 模型集、IMM 权重、UKF/Stone Soup/FilterPy 后端仍未接入 | 作为 D1 P1 能力增强 backlog，先做 CV/CA/CT 或等价模型对照，不替换 NumPy fallback；Stone Soup/FilterPy/MATLAB 只作参考或 benchmark | 机动目标 replay/AirSim 样本中输出模型对照，机动 RMSE 或 NIS/连续性指标优于 CV-only 基线 |
| P1 | 场景自适应协方差 | 已有距离/质量相关协方差、bbox confidence/occlusion 输入、低质量/遮挡 scale reason、replay passthrough 和雷达参数化；尚缺杂波、SNR、来源差异和延迟的完整动态 covariance scale rule | 作为 D1 P1 标定 backlog，保留现有 covariance-required replay/schema 已完成状态；MATLAB fusion 调参逻辑只作工程参考 | AirSim/replay 中稳定输出 covariance scale reason，并用多 seed 标定阈值 |
| P1 | Track-to-Track 融合原型 | 已有 source lineage de-dup 基线；多二级节点 TrackSummary、未知相关性处理、重复计数抑制和协方差一致性原型尚未实现 | 作为 D1 P1 原型 backlog，先做离线/回放输入的 T2T 原型，不改变当前观测到航迹主线，也不把 Stone Soup Track Fusion 写成 P0 依赖 | 多二级节点输入不重复计数，保留 source lineage，融合后 covariance 保守一致，能输出对照日志 |

## 2. 按实现状态归类

### 2.1 已实现

- `SensorObservation` 统一合同已落地，支持 `radar/acoustic/eo/lidar`，强制保留 `measurement_timestamp`、`arrival_timestamp`、`frame_id`、`measurement`、`covariance`、置信度、质量标记、通信元数据和 `timestamp_uncertainty_s`。
- `FusionAdapter` 已实现 NumPy EKF 融合主线，输出六维 NED `GlobalTrack`、6x6 协方差、`source_support`、质量等级、`valid_at/published_at`、最近量测时间、最近到达时间、timestamp uncertainty、covariance limit reason 和 sensor health snapshot。
- fixed-lag/OOSM 延迟补偿已实现，观测按 `measurement_timestamp` 插入历史并重放到当前 `arrival_timestamp`；消融测试要求补偿 RMSE 明显优于未补偿基线。
- 雷达距离相关协方差已通过 `RadarCovarianceConfig` 参数化；声学为弱方位约束；EO 为 pinhole 像素投影约束；合成 LiDAR 作为 dry-run NED 三维位置量测。
- AirSim dry-run fixture 已实现，不导入 AirSim，可生成 radar/acoustic/eo/lidar `SensorObservation[]` 并喂给 `FusionAdapter`。
- Blocks JSONL replay reader 已实现并升级为 replay schema v1/legacy 兼容，D1 可读取 `blocks_sensor_observations.jsonl` 与未来 `sensor_observations.jsonl` 并回放融合；N actor 合同测试覆盖按输入数组长度输出 `GlobalTrack[]`。
- 最小 CSV reader/replay 已实现，支持以 JSON array/object 单元格表达 measurement、covariance、metadata、communication 和 source support，便于 D6/人工审计复用观测记录。
- `TrackUncertaintySummary` 已实现数据类与导出方法，包含协方差迹、`a95`、等级、measurement age、source support、coverage cell、measurement/arrival timestamp 和 handover readiness。
- `LatencyAuditSummary` 已实现，导出 max/mean delay、replay count、OOSM/stale count、重复观测数和最大 replay 历史长度。
- `SensorHealthSummary` 已实现，导出 per-sensor `status`、`fault_reason`、`reject_count`、`isolation_hint`、`recovery_state`，并保留 duplicate、OOSM/stale、低质量/遮挡、异常协方差和 timestamp uncertainty 计数。
- 协方差上下界限制已实现，观测协方差进入 EKF 前会 floor/ceiling，低质量或遮挡观测会保守放大，track 6x6 covariance 在预测/replay/update 后会 floor/ceiling，并在 metadata/summary 中记录 reason。
- `FusionQualityRegionSummary` 已实现轻量区域聚合，按 `coverage_cell` 汇总 track 数、a95、measurement age、handover readiness、source support、source gap、stale track 数和可选协方差增长率。
- `FusionQualityRegionWindowSummary`、`annotate_covariance_growth_rates()` 和 `summarize_region_quality_windows()` 已实现轻量窗口趋势，区分区域协方差增长、freshness 下降、source gap 与 latency/OOSM。
- `ReconCueSummary` 已实现轻量侦察相机粗指向摘要，按全部 tracks 或指定 `coverage_cell` 子群输出协方差加权 `cue_position_ned`、`cue_covariance`、`active_target_ids`、measurement/arrival timestamp、可选二级/移动侦察 metadata 和基础诊断。
- source lineage 去重基线已实现，可抑制同一 source/sequence/payload 经 relay 重复投递导致的重复更新。
- `generate_truth(target_count=N)` 和 CLI `--drone-count N` 已按输入 N 运行，不把算法限制为 2v2 或 5v5；历史 2v2/5v5/3-target 仅作为 baseline 名称或样例。

### 2.2 部分实现

- Stone Soup 和 FilterPy 仅有 placeholder/可用性探测与转换边界，未接入真实 tracker、updater、UKF、IMM、JPDA/MHT 或 OOSM 后端。
- AirSim/Blocks 集成在 D1 侧完成 fake fixture 和 JSONL replay；真实 AirSim 连接、`simGetDetections` 调用、frame capture 和 JSONL 写出属于 main/shared runtime，不在 D1 包内直连。
- EO 无截图合同已实现，D1 只消费 bbox、相机元数据、时间戳和协方差；但未实现 OpenCV calibration、畸变模型、`solvePnP` 或 `projectPoints` 对照。
- 合成 LiDAR 仅是 dry-run/replay 观测模型，不是 AirSim LiDAR plugin 或真实硬件桥。
- `TrackUncertaintySummary` 是单航迹摘要；轻量 `FusionQualityRegionSummary`、`FusionQualityRegionWindowSummary` 和 `ReconCueSummary` 已按当前 track summary/track input 聚合。D6 批量日志 schema、真实多 seed 样本阈值、真实样本回归和更细 NIS 统计仍需后续补齐。
- source lineage 去重只解决重复 payload；未知相关性的跨节点 Track-to-Track fusion、协方差交叉和相关性降权尚未实现。
- JSONL replay schema v1/legacy 兼容、真实 CV 字段保真和最小 CSV reader 已完成；更多 main/shared 真实 Blocks/CV multi-seed fixture 回归仍未完成。
- 2026-07-08 已补强 CSV 缺省 schema 行的 v1/covariance 验证、嵌套 EO camera metadata 解析、真实 CV bbox/camera/detection metadata 字段保真、区域窗口/协方差增长 helper 和 Blocks calibration CSV 回归；更多 main/shared 真实 Blocks/CV multi-seed fixture 回归仍未完成。

### 2.3 未实现

- UKF 与 IMM-EKF/IMM-UKF 未实现。
- 真实 Stone Soup 后端和真实 FilterPy 后端未实现。
- ROS 2 `tf2` 坐标树和 `message_filters` 时间同步未实现。
- D1 包内真实 AirSim ComputerVision/Blocks runtime 直连、`simGetDetections` 直接 adapter 未实现；这属于 P2 后置直连能力，当前 P1 只跟踪 D1 可消费的 Blocks/CV fixture 回归和字段合同。
- OpenCV calibration、畸变校正、`solvePnP`、`projectPoints` 对照未实现。
- 声学 TDOA/阵列主定位未实现，当前按计划只作为粗方位和类别辅助。
- 多节点 Track-to-Track fusion、协方差交叉和 Stone Soup Track Fusion 对照未实现。

## 3. 逐项差距表

| 预期项 | 当前状态 | 证据文件 | 未实现原因 | 缺失条件 | 建议优先级 |
|---|---|---|---|---|---|
| 统一 `SensorObservation` 数据合同 | 已实现。支持 `radar/acoustic/eo/lidar`、`measurement_timestamp`、`arrival_timestamp`、`frame_id`、`covariance`、质量字段、通信元数据、真实 CV bbox/camera/detection metadata 和 secondary/mobile recon cue metadata；replay schema v1、legacy JSONL 和最小 CSV replay 已落地 | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/types.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/replay.py`; `research_modules/d1_sensor_fusion/tests/test_interfaces.py`; `research_modules/d1_sensor_fusion/tests/test_airsim_dry_run.py` | 不适用 | 仍需更多 main/shared 真实 Blocks/CV multi-seed fixture、真实样本回归和 D6 长期批量 schema 对齐 | P0/P1 |
| `GlobalTrack` 六维航迹输出 | 已实现。输出 `[px, py, pz, vx, vy, vz]`、6x6 协方差、`track_level`、`source_support`、`metadata.frame_id/valid_at/published_at/a95_m/latest_measurement_timestamp/latest_arrival_timestamp` | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/types.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/fusion.py` | 不适用 | 需要继续补充 track/schema version 与下游日志命名标准化 | P0/P1 |
| 跨节点通信元数据 | 已实现最小支持。字段包括 `source_node_id`、`target_node_id`、`relay_node_id`、`link_type`、`sent_timestamp`、`received_timestamp`、`payload_kind`、`stale_after_s`、`source_support` | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/types.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/fusion.py`; `research_modules/d1_sensor_fusion/tests/test_interfaces.py` | 不适用 | 需要 main 确定节点 ID、链路类型和 stale 策略的枚举 | P0 |
| EKF 主滤波器 | 已实现。自研 NumPy EKF、数值雅可比、Joseph 形式协方差更新、NIS 输出 | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/ekf.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/fusion.py` | 不适用 | 后续需增加与 FilterPy/Stone Soup 的数值对照 | P0 |
| 常速度 CV 运动模型 | 已实现。六维 CV 预测和白加速度谱密度过程噪声 | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/motion.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/ekf.py` | 不适用 | 对高机动目标需更多模型 | P0 |
| UKF | 未实现。文档中列为强非线性场景升级项 | `research_modules/d1_sensor_fusion/docs/ALGORITHM_AND_IMPLEMENTATION.md`; `subagent_reviews/D1_SENSOR_FUSION_REVIEW_AND_PLAN.md` | 当前 EKF 足够覆盖离线主线；未引入 FilterPy/Stone Soup 依赖 | 需要 UKF 后端接口、sigma-point 参数、对照场景和误差指标 | P2 |
| IMM-EKF/IMM-UKF | 未实现。文档中列为机动目标升级项 | `C_UAS_MAINSTREAM_SOLUTIONS_AND_DIFFICULTIES.md`; `research_modules/d1_sensor_fusion/docs/ALGORITHM_AND_IMPLEMENTATION.md` | 当前状态维度和场景仍以 CV/EKF 为主；D2 关联先用基础航迹 | 需要 CV/CA/CT 模型集合、模型转移概率、机动场景和 D2 接口约定 | P2 |
| Stone Soup 集成 | 占位实现。只提供不导入 Stone Soup 的 placeholder 和 detection dict 转换；未接入真实 Stone Soup tracker/fuser/OOSM | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/compat.py`; `research_modules/d1_sensor_fusion/tests/test_interfaces.py` | 保持当前测试不依赖外部包；Stone Soup 适合作为离线对照而非主运行依赖 | 需要安装依赖、设计 D1 observation/track 转换、选择 Stone Soup updater/initiator/fuser、定义对照实验 | P2 |
| FilterPy 集成 | 占位实现。只检测可用性并说明 fallback 状态；未调用 FilterPy EKF/UKF/IMM | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/compat.py`; `research_modules/d1_sensor_fusion/tests/test_interfaces.py` | 当前已有自研 EKF，避免新增依赖和版本差异 | 需要明确 FilterPy 后端接口、测试容差、UKF/IMM 目标 | P2 |
| ROS 2 `tf2` | 未实现，仅文档计划。当前只用 `metadata` 中的 NED 位置和相机外参 | `research_modules/d1_sensor_fusion/docs/AIRSIM_INTEGRATION_PLAN.md`; `research_modules/d1_sensor_fusion/docs/ALGORITHM_AND_IMPLEMENTATION.md` | 当前仓库没有 ROS 2 runtime 和 tf tree；AirSim dry-run 不需要 ROS | 需要 ROS 2 环境、frame 命名规范、外参版本、tf buffer 与时间戳策略 | P2 后置 |
| ROS 2 `message_filters` | 未实现，仅文档计划。当前依赖 `arrival_timestamp` 排序和 fixed-lag replay | `research_modules/d1_sensor_fusion/docs/AIRSIM_INTEGRATION_PLAN.md`; `subagent_reviews/D1_SENSOR_FUSION_REVIEW_AND_PLAN.md` | 离线 replay 不需要 ROS message filters；OOSM 补偿已经在 D1 内实现 | 需要 ROS topic schema、同步策略、允许延迟窗口和 bag/replay 工具 | P2 后置 |
| 雷达观测模型 | 已实现。`[range, azimuth, elevation, radial_velocity]`，支持传感器位置和角度 wrap | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/observations.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/simulation.py` | 不适用 | 需要真实/仿真雷达配置时再参数化噪声模型 | P0 |
| 雷达距离相关协方差 | 已实现并可参数化。`RadarCovarianceConfig` 保持默认行为兼容，也可按距离系数覆盖 | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/observations.py`; `research_modules/d1_sensor_fusion/tests/test_interfaces.py` | 不适用 | 后续可按真实雷达型号、SNR、杂波、遮挡策略扩展配置来源 | P1 已完成基线 |
| 雷达初始化新航迹 | 已实现。`_create_track()` 只允许雷达初始化，避免声学/EO 单独造三维真值 | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/fusion.py` | 不适用 | 如果要 EO/depth 初始化，需要额外深度/多视角约束 | P0 |
| 声学观测模型 | 已实现弱约束。仅方位角 + confidence 相关角度协方差 + `classification_hint` | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/observations.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/simulation.py` | 不适用 | 未实现 TDOA/声阵列硬件模型；缺少阵列几何和声学仿真参数 | P0 |
| 声学主定位/TDOA | 未实现，且不建议作为主线。文档明确声学只作粗方位和类别辅助 | `C_UAS_MAINSTREAM_SOLUTIONS_AND_DIFFICULTIES.md`; `subagent_reviews/D1_SENSOR_FUSION_REVIEW_AND_PLAN.md` | 主流共识认为声学主定位场景受限，且硬件相关性强 | 需要阵列几何、采样率、TDOA 估计、风噪/混响模型 | P2 后置 |
| EO 像素观测模型 | 已实现。使用 pinhole 相机模型，像素中心观测，bbox/置信度/遮挡影响协方差 | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/observations.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/simulation.py` | 不适用 | 需要与 D5/主程序统一 camera metadata schema | P0 |
| EO 无截图输入 | 已实现合同层面。D1 只需要 bbox、相机元数据、时间戳和协方差，不要求 PNG | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/observations.py`; `research_modules/d1_sensor_fusion/docs/ALGORITHM_AND_IMPLEMENTATION.md`; `subagent_reviews/D1_SENSOR_FUSION_REVIEW_AND_PLAN.md` | 不适用 | 需要 main 从 AirSim CV 输出稳定 JSONL/CSV detection 记录 | P1 |
| OpenCV calibration / solvePnP / projectPoints | 未实现。当前是自研简单 pinhole 投影，不依赖 OpenCV | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/observations.py`; `C_UAS_MAINSTREAM_SOLUTIONS_AND_DIFFICULTIES.md` | 当前仅需 dry-run 和离线约束；OpenCV 更适合 D5 精细投影/标定 | 需要真实相机内外参、畸变模型、坐标链和 D5 共同接口 | P2 |
| 合成 LiDAR 观测 | 已实现 optional dry-run。作为 NED 三维位置量测，含 3x3 covariance | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/types.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/observations.py`; `research_modules/d1_sensor_fusion/tests/test_airsim_dry_run.py` | 不适用 | 当前为合成 dry-run，不是 AirSim LiDAR plugin 或真实硬件 | P1 |
| fixed-lag / OOSM 延迟补偿 | 已实现。按 `measurement_timestamp` 重排历史观测、回放更新并传播到当前时刻，并导出 max/mean delay、replay count、OOSM/stale count 审计摘要 | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/fusion.py`; `research_modules/d1_sensor_fusion/tests/test_interfaces.py`; `research_modules/d1_sensor_fusion/tests/test_simulation_metrics.py` | 不适用 | 后续可补窗口化成本统计和 D6 长期趋势字段 | P0/P1 |
| 延迟补偿消融实验 | 已实现。测试要求补偿 RMSE 明显优于未补偿 | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/simulation.py`; `research_modules/d1_sensor_fusion/tests/test_simulation_metrics.py`; `research_modules/d1_sensor_fusion/reports/EXPERIMENT_REPORT.md` | 不适用 | 需要扩大到 main `--drone-count N` 集成、跨节点通信、二级节点转发延迟；历史 2v2/5v5 只作为 baseline | P1 |
| 协方差输出与航迹分级 | 已实现。输出 6x6 协方差、`a95_m`、`coarse/stable/handover`、NIS 通过率参与分级，并可导出 `TrackUncertaintySummary` 与轻量 `FusionQualityRegionSummary` | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/fusion.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/metrics.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/types.py` | 不适用 | 后续可继续对齐 D4/D6 长期窗口和批量日志字段 | P1 已完成基线 |
| `TrackUncertaintySummary` / `FusionQualityRegionSummary` / `FusionQualityRegionWindowSummary` | 已实现 D1 单航迹摘要、`FusionAdapter.track_uncertainty_summaries()`、`FusionAdapter.region_quality_summaries()`、`annotate_covariance_growth_rates()` 和 `summarize_region_quality_windows()` 导出。字段包含 track IDs、协方差迹/a95、协方差增长率、等级、measurement age、source support、coverage cell、时间戳、source gap、stale track 数、窗口趋势和 latency/OOSM flags | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/types.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/fusion.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/quality.py`; `research_modules/d1_sensor_fusion/tests/test_interfaces.py` | 不适用 | 后续可继续对齐 D6 批量日志 schema、真实多 seed 阈值和更细 NIS 统计 | P1 已完成轻量基线 |
| `ReconCueSummary` 侦察粗指向摘要 | 已实现。`summarize_recon_cue_from_tracks()` 可从 `GlobalTrack[]` 或 track-like dict 生成全部目标或指定 `coverage_cell` 的协方差加权 `cue_position_ned`/centroid、`cue_covariance`、`active_target_ids`、时间戳、可选二级/移动侦察 metadata 和 `track_count/stale_count/default_covariance_count` 诊断 | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/recon_cue.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/types.py`; `research_modules/d1_sensor_fusion/tests/test_recon_cue.py` | 不适用 | main/AirSim runtime 仍负责消费该摘要并控制二级侦察相机指向；D1 不修改 runtime | P1 已完成基线 |
| 多传感器来源去重/相关性降权 | 已实现 source lineage 去重基线。相同 source/sequence/payload lineage 或 relay 重复投递不会重复更新同一观测 | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/types.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/fusion.py`; `research_modules/d1_sensor_fusion/tests/test_interfaces.py` | 不适用 | 未实现未知相关性跨节点 Track-to-Track fusion、协方差交叉或相关性降权模型 | P1 已完成基线 |
| 航迹到航迹融合 / 协方差交叉 | 未实现。Stone Soup Track Fusion 仅在主流方案中列为候选 | `C_UAS_MAINSTREAM_SOLUTIONS_AND_DIFFICULTIES.md`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/compat.py` | 当前 D1 融合的是观测到航迹，不是多节点 Track-to-Track | 需要节点级 TrackSummary、相关性未知处理、融合权威规则 | P2 |
| AirSim dry-run fake fixture | 已实现。可从 fake fixture 生成 radar/acoustic/eo/lidar `SensorObservation[]`，不连接真实 AirSim；fixture 已带 `d1.airsim_dry_run_fixture.v1` schema version 并拒绝 unsupported fixture schema | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/airsim_dry_run.py`; `research_modules/d1_sensor_fusion/tests/test_airsim_dry_run.py`; `research_modules/d1_sensor_fusion/docs/AIRSIM_INTEGRATION_PLAN.md` | 不适用 | 需要继续与 shared/main 的 Blocks JSONL 输出保持回归一致 | P0 |
| 共享 AirSim dry-run orchestrator 对接 | 已由共享模块复用 D1 dry-run 适配器；D1 侧合同可用 | `research_modules/airsim_dryrun/adapters.py`; `research_modules/airsim_dryrun/tests/test_dryrun_contracts.py` | 不适用 | 该模块不属于 D1；后续由 main 维护统一 runtime | P0 |
| shared/main AirSim Blocks D1 replay 写出 | shared runtime 可从 Blocks frame 生成 `SensorObservation` 并写 `blocks_sensor_observations.jsonl`；D1 包内已能读取该 JSONL 并回放 `FusionAdapter` | `research_modules/airsim_runtime/adapters.py`; `research_modules/airsim_runtime/orchestrator.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/replay.py`; `research_modules/d1_sensor_fusion/tests/test_airsim_dry_run.py` | 不适用 | 后续需继续跟随 schema 演进补更多真实输出回归样本 | P1 已完成基线 |
| 真实 AirSim ComputerVision / Blocks runtime | 未在 D1 包内实现。D1 只提供 fake fixture 和 `SensorObservation` 类型；真实 AirSim 连接、frame capture、`simGetDetections` 和 JSONL 写出在 main/shared 层 | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/airsim_dry_run.py`; `research_modules/d1_sensor_fusion/docs/AIRSIM_INTEGRATION_PLAN.md`; `research_modules/airsim_runtime/real_runtime.py` | 避免 D1 依赖 AirSim Python 包和 runtime；真实 AirSim orchestration 由 main/shared 层负责 | 需要稳定 Blocks JSONL/detection schema、真实相机外参、actor ID 映射、时间戳来源和长期 fixture 回归 | P1 fixture / P2 后置直连 |
| AirSim `simGetDetections` 直接适配 | 未实现 D1 直连。当前要求 main/shared runtime 转成 bbox/camera metadata JSONL/CSV 或 fake fixture，D1 负责离线 reader/replay 和字段回归 | `research_modules/d1_sensor_fusion/docs/AIRSIM_INTEGRATION_PLAN.md`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/airsim_dry_run.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/replay.py` | 避免 D1 依赖 AirSim Python 包和 runtime | P1 需要 main/shared 真实 Blocks/CV multi-seed fixture 覆盖 detection 字段；D1 直连 AirSim API 需等 runtime 合同稳定后再评估 | P1 fixture / P2 后置直连 |
| JSONL/CSV replay 输入合同 | 已实现 replay schema v1、legacy `blocks_sensor_observations.jsonl` 兼容、未来 `sensor_observations.jsonl` reader 和 CSV reader/replay；CSV 缺省 schema 行按 v1 验证并要求 covariance，unsupported JSONL schema 已回归拒绝，Blocks calibration CSV 测试覆盖 timestamps、covariance、source support、NED state、raw/fusion latency/OOSM audit、区域质量摘要、`covariance_scale_reason` 和 secondary/mobile recon cue metadata，真实 CV JSONL 测试覆盖 bbox/camera/detection/secondary/mobile recon metadata 字段保真 | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/replay.py`; `research_modules/d1_sensor_fusion/tests/test_airsim_dry_run.py`; `research_modules/airsim_runtime/orchestrator.py` | 不适用 | 需要更多 main/shared 真实 Blocks/CV multi-seed fixture 和 D6 长期批量 schema 对齐 | P1 已完成轻量基线 |
| N-target D1 独立真值生成 | 已实现。`generate_truth(target_count=N)` 不再把目标数裁剪到 2/5 或 1-3，命令行统一使用 `--drone-count N`，历史 3 目标输出保留为 baseline | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/simulation.py`; `research_modules/d1_sensor_fusion/scripts/run_simulation.py` | 不适用 | 系统级真值仍由 main/integrated 场景提供，D1 只消费其输出 | P1 已完成基线 |
| 单元/接口测试 | 已实现。覆盖时间戳、桶、协方差增长与参数化、延迟观测、通信元数据、dry-run schema、JSONL/CSV replay、unsupported schema、raw/fusion latency audit、source de-dup、TrackUncertaintySummary、LatencyAuditSummary、FusionQualityRegionSummary、FusionQualityRegionWindowSummary、ReconCueSummary、N actor 合同、嵌套 camera metadata replay、真实 CV bbox/camera/detection/covariance scale/recon metadata 字段保真、Blocks calibration CSV 字段保真和仿真指标 | `research_modules/d1_sensor_fusion/tests/test_interfaces.py`; `research_modules/d1_sensor_fusion/tests/test_airsim_dry_run.py`; `research_modules/d1_sensor_fusion/tests/test_recon_cue.py`; `research_modules/d1_sensor_fusion/tests/test_simulation_metrics.py` | 不适用 | 更多真实 AirSim CV multi-seed 场景和 JSONL/CSV 样本仍可后续扩充；2v2/5v5 只作为 baseline 回归命名 | P0/P1 |

## 4. 主要未实现原因归类

1. **依赖与环境未固定**: Stone Soup、FilterPy、ROS 2、tf2、message_filters 和真实 AirSim runtime 都会引入外部环境约束。当前 D1 选择 NumPy fallback，保证仓库在无外部服务时可测试。
2. **消息合同仍需继续演进**: D1 已有 replay schema v1、legacy Blocks JSONL 兼容和最小 CSV reader，但更多真实 detection 字段映射、D6 长期批量字段和长期回归样本仍需补齐。
3. **算法升级需要对照场景**: UKF、IMM、Track-to-Track fusion、协方差交叉需要明确强非线性、高机动、多节点相关观测等触发场景，否则容易增加复杂度但不提升当前基线。
4. **ROS/真实运行时不是 D1 当前职责边界**: D1 负责 `SensorObservation` 到 `GlobalTrack`，真实 AirSim/ROS topic、bag、tf tree 和 runtime orchestration 应由 main/shared 层提供。
5. **安全边界**: D1 保持为传感器融合与态势估计模块，不输出控制、处置或授权动作，因此未接任何真实飞控/硬件/火控接口。


## 5. 缺少条件汇总

- **真实运行环境条件**: ROS 2 runtime、tf tree、topic schema、bag/replay 工具、AirSim Blocks 稳定启动和长期 fixture 样本。
- **传感器/坐标条件**: 真实或稳定仿真的相机内外参、畸变模型、AirSim detection 字段映射、actor ID 映射、统一时间戳来源和 WGS84/ENU 到 NED 的外部转换合同。
- **数据合同条件**: `sensor_observations.jsonl` schema v1、legacy Blocks JSONL 兼容、最小 CSV reader、真实 CV 字段保真、轻量区域质量摘要、区域窗口摘要和 `ReconCueSummary` 粗指向摘要已落地；仍需 D6 可消费的长期批量摘要字段、真实多 seed 阈值和 coverage cell 规则细化。
- **算法评估条件**: UKF/IMM/Stone Soup/FilterPy 对照场景、强非线性/高机动/多节点相关观测基准、误差门限和与 NumPy EKF fallback 的容差定义。
- **多节点融合条件**: 节点级 TrackSummary、相关性未知处理策略、协方差交叉/Track-to-Track fusion 权威规则和 source lineage 之外的相关性降权模型。

## 6. 对后续模块的影响

### 6.1 对 D2 数据关联

- D1 已输出 `GlobalTrack[]`、NED 六维状态、6x6 协方差、`track_level`、`source_support`、`latest_measurement_timestamp`、`latest_arrival_timestamp` 和可选 `truth_id` 元数据。D2 应把这些字段作为中心航迹输入，并继续显式统计 `id_switch_count`。
- `global_track_id` 当前由 D1/FusionAdapter 生成；D2 可以维护关联连续性，但不应把 D5/D7 的局部身份重绑定写回覆盖该 ID。
- 当前 D1 的 N actor 合同按输入数组长度输出航迹；D2 不应把 2v2/5v5 写成关联算法限制，2v2/5v5 只能作为 baseline 场景名。
- AirSim truth ID 和 dry-run `truth_id` 只能作为离线评估/测试辅助，不能作为在线关联真值捷径。

### 6.2 对 D3 分配规划

- D3 可使用 `track_level`、`a95_m`、协方差、`measurement_age_s`、`source_support` 和 `handover_readiness` 判断目标是否进入分配候选。
- D1 不生成 `AssignmentPlan`，也不管理 plan version；D3 必须继续按版本化计划拒绝 stale input。
- 如果 D1 航迹只处于 `coarse` 或 measurement age 过大，D3 应倾向继续观测、请求补传感器或保守分配，而不是把低质量航迹当成稳定目标。
- `ReconCueSummary` 可帮助 main/runtime 指向目标群或 `coverage_cell` 子群，但不替代 D3 的资源分配、版本化计划或重规划逻辑。

### 6.3 对 D5 末端关联

- D1 已支持 EO bbox/center pixel/camera metadata 的无截图合同，并输出可投影的 NED `GlobalTrack` 与协方差。D5 可用这些字段做相机平面门控和末端身份确认。
- `ReconCueSummary` 可作为二级侦察相机的粗指向 cue；D5 仍需用自身终端观测做身份确认，不能把 cue 当作在线 truth ID。
- D5 不得改写 `global_track_id`；末端视觉结果应作为 `TerminalAssociation`、`IdentityClaim` 或反馈证据回流，而不是本地重绑定中心 ID。
- 当前 D1 未实现 OpenCV calibration、畸变校正、`solvePnP` 或跨视角几何一致性；这些若进入 D5，应通过相机 metadata 和投影残差与 D1 合同对齐。

### 6.4 对 D6 评估指标

- D6 可消费 D1 已有 RMSE、track continuity、grading accuracy、延迟补偿消融、`TrackUncertaintySummary`、`FusionQualityRegionSummary`、`FusionQualityRegionWindowSummary`、`ReconCueSummary`、`LatencyAuditSummary`、source diversity 和 duplicate observation count。
- D1 已提供最小 CSV reader、区域质量摘要、区域窗口趋势、协方差增长率 helper 和 OOSM replay 计数；仍未提供 D6 长期批量 schema 和真实多 seed 阈值。
- D6 的 `id_switch_count` 仍由 D2/系统日志显式提供；D1 不应用 truth ID 在线替代该指标。

### 6.5 对 D7 导引

- D7 应只消费 `stable` 或 `handover` 级 `GlobalTrack` 作为离线中段导引输入，并使用协方差、新鲜度和 source support 做门控。
- 当 D1 的 `measurement_age_s` 或 `latest_observation_latency_s` 过大时，D7 应扩大预测门限、请求 D3/D4 重新规划或保持保守状态。
- D1 不提供真实飞控、硬件、毁伤或自动处置接口；`handover` 是仿真质量标签，不是授权状态。

## 7. 下一步 P0/P1/P2 优先级

### P0: EVAL 工程化硬化项（已实现，保持回归）

当前无运行级 P0 blocker。以下三项是已实现的 P0-A 保持回归项；若真实多 seed/闭环样本暴露未覆盖字段或验收缺口，按第 1.2 节最小验收口径进入 P0 backlog。

1. **FDIR-light**: 已实现 `SensorHealthSummary` 和 `FusionAdapter.sensor_health_summaries()`，输出 sensor health、fault reason、reject count、isolation hint 和 recovery state。
2. **协方差上下界限制**: 已实现观测与 track covariance floor/ceiling，长时间外推、低质量观测、遮挡和异常观测会记录 covariance limit reason。
3. **时间戳不确定性建模**: 已保持 `measurement_timestamp` 与 `arrival_timestamp` 双时间戳合同，并在观测、track metadata、summary 和 sensor health 中显式记录 timing uncertainty；10-50 ms clock drift 注入已进入接口回归。

### P1: 稳定 D1 到 main/D2-D7 的数据合同

已完成的 P1 基线：

1. **JSONL schema version**: 已固化 D1 replay schema v1，字段覆盖 `measurement_timestamp`、`arrival_timestamp`、`frame_id`、`measurement`、`covariance`、camera metadata、communication metadata、source lineage 和可选评估标签；legacy Blocks JSONL 继续兼容。
2. **CSV reader/转换工具**: 已实现最小 CSV reader/replay；JSONL-to-CSV 导出工具可在 D6 长期 schema 稳定后再补。
3. **区域质量摘要**: 已基于 `TrackUncertaintySummary` 增加轻量 `FusionQualityRegionSummary`，聚合 coverage cell、source gap、freshness、a95 和 handover readiness。
4. **延迟补偿审计**: 已记录 max/mean latency、OOSM replay 次数、stale/OOSM count、重复观测计数和 replay 历史长度。
5. **侦察粗指向摘要**: 已提供 `ReconCueSummary`/`summarize_recon_cue_from_tracks()`，覆盖全部 tracks、`coverage_cell` 过滤、缺省协方差保守降权和时间戳保留。
6. **source de-dup 与 replay 回归**: source lineage de-dup、Blocks JSONL replay、legacy JSONL 兼容和 N actor 合同已进入测试基线。
7. **P1 输入支撑字段回归**: dry-run fixture schema 检查、raw replay latency/OOSM helper、unsupported JSONL schema 回归、`covariance_scale_reason` passthrough 和 secondary/mobile recon cue metadata 保真已进入 D1 测试基线；sensor health、covariance floor/ceiling reason 和 timestamp uncertainty 继续作为 D6 可消费质量证据保持回归。

剩余 P1：

1. **AirSim CV/Blocks fixture 回归**: D1 已有 Blocks calibration CSV、真实 CV 字段、covariance scale reason 和 secondary/mobile recon cue metadata 保真回归；main 已能通过 D4/D5 calibration sweep 与 D6 bundle 汇总结果，但 D1 仍需增加来自 main/shared runtime 的 `simGetDetections`/detector boxes multi-seed JSONL/CSV 样本，覆盖更多 actor label、camera metadata、timestamp、bbox covariance、secondary/mobile recon metadata 和 N actor 输出；D1 不直连真实 AirSim runtime bus。
2. **D6 长期批量 schema**: 对齐 `TrackUncertaintySummary[]`、`LatencyAuditSummary`、`FusionQualityRegionSummary[]`、`FusionQualityRegionWindowSummary[]`、`SensorHealthSummary[]`、covariance limit reason 和 timestamp uncertainty 的长期 JSONL/CSV 字段，使 D6 标准 bundle 能稳定消费 D1 输出。
3. **真实样本阈值/回归**: 将更多真实 Blocks/CV 样本纳入固定测试或审计 fixture，并用多 seed 统计校准区域窗口、freshness/source-gap、协方差增长率和 handover readiness 的持续阈值。
4. **IMM/CV-CA-CT 多模型滤波**: 按 EVAL P1 同步为三个月内能力增强项，先做 CV/CA/CT 或等价模型对照和机动目标 replay/AirSim 评估，不替换当前 NumPy CV/EKF fallback；Stone Soup、FilterPy、MATLAB 只作为 benchmark 或调参参考。
5. **场景自适应协方差**: 在现有距离/质量协方差、bbox confidence/occlusion 输入和雷达参数化基础上，补遮挡、杂波、SNR、来源差异、延迟等 covariance scale rule，并在 replay/AirSim 输出 scale reason。
6. **Track-to-Track 融合原型**: 按 EVAL P1 同步为多二级/分布式输入的离线原型，重点验证 source lineage、重复计数抑制和协方差一致性；完整外部库融合后端仍按后续对照收益再评估。

### P2: 开源库和算法对照

1. **FilterPy 对照后端**: 以可选依赖方式验证 EKF/UKF 数值差异、运行时间和协方差一致性，不替换现有 NumPy fallback。
2. **Stone Soup 离线实验**: 先做 observation/track 转换、OOSM replay 或 JPDA/MHT/Track Fusion 对照，只有指标收益明确后再扩大接入。
3. **UKF/IMM 基准**: 构造高机动、强非线性和多模型场景，定义相对当前 CV/EKF 的 RMSE、NIS、连续性和计算成本收益门限。
4. **OpenCV/D5 几何对齐**: 将 calibration、畸变、`projectPoints`、`solvePnP` 作为 D5/D1 边界对照项，D1 保持 bbox/camera metadata/协方差合同。
5. **ROS 2 `tf2/message_filters` 评估**: 等 topic schema、tf tree、bag/replay 和 main/shared runtime 稳定后再接入；接入前仍由上游转成 NED 或提供完整外参元数据。
