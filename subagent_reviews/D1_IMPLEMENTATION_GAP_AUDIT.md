# D1 实现差距审计

**模块**: D1 多传感器融合与目标配准  
**范围**: 对照 `subagent_reviews/D1_SENSOR_FUSION_REVIEW_AND_PLAN.md`、`C_UAS_MAINSTREAM_SOLUTIONS_AND_DIFFICULTIES.md`、`research_modules/d1_sensor_fusion` 源码和测试，审计共识算法、开源方案和当前实现差距。  
**边界**: 本审计只覆盖离线科研仿真、数据合同、传感器观测、航迹融合和评估接口；不涉及真实飞控、硬件驱动、火控、毁伤或自动处置。

**更新时间**: 2026-07-11。

## 1. 总体结论

D1 当前已经实现了可运行的轻量主线：`SensorObservation -> NumPy EKF/FusionAdapter -> GlobalTrack`，支持雷达、声学、EO、可选合成 LiDAR，具备测量时刻/到达时刻分离、fixed-lag replay 延迟补偿、可参数化距离/置信度相关协方差、AirSim dry-run fake fixture 与 schema 检查、跨节点通信元数据、source lineage 去重基线、`TrackUncertaintySummary` 导出、replay schema v1/legacy JSONL 兼容、最小 CSV reader/replay、真实 Blocks/CV 字段保真、raw replay latency/OOSM audit helper、`LatencyAuditSummary`、`SensorHealthSummary`、协方差 floor/ceiling reason、covariance scale reason passthrough、timestamp uncertainty、轻量 `FusionQualityRegionSummary`、`FusionQualityRegionWindowSummary` 和 `ReconCueSummary` 粗指向摘要。D1 接收 main 提供的 N 个 target truth/观测源，并按输入数组长度处理 `SensorObservation[]` 与 `GlobalTrack[]`；真实 AirSim runtime bridge 仍由 shared/main 层负责，D1 不直连 AirSim。

尚未实现的主要是外部成熟框架集成：Stone Soup、FilterPy、ROS 2 `tf2`、`message_filters`、UKF、IMM、D1 包内真实 AirSim ComputerVision/Blocks 运行时适配。这些目前有文档计划或占位类，但未作为 D1 运行依赖接入。原因主要是当前阶段强调依赖轻、可复现、离线测试稳定，且缺少 ROS 2 runtime、稳定真实 AirSim detection schema/外参标定链路、长期真实样本回归和多模型评估基准。

优先级建议已同步 `EVAL/FRAMEWORK_EVAL_P0_P1_P2_GAP_CONFIRMATION.md` 中的 D1 P0/P1 口径：

- **P0**: 无运行级 P0 blocker；当前 NumPy EKF、传感器观测模型、延迟补偿、AirSim dry-run、`measurement_timestamp`/`arrival_timestamp`、协方差和 NED `GlobalTrack` 合同均作为持续回归基线维护。EVAL 确认的 D1 工程化 P0-A 已实现：FDIR-light、协方差上下界限制和时间戳不确定性建模已进入代码与接口回归；后续若真实多 seed/闭环样本发现未覆盖验收场景，按第 1.2 节的最小验收口径进入 P0 backlog。
- **P1**: `TrackUncertaintySummary`、replay/schema/governance、source de-dup、区域/窗口质量、`ReconCueSummary` 和真实 CV 字段保真均已完成。2026-07-11 又完成中心化协同定位数值基础：typed cooperative DTO/summary、2..N bearing-ray WLS、几何/时间/covariance 门控、共同估计时刻传播及最小 CI。剩余 D1 P1 是 IMM/CV-CA-CT、场景自适应协方差、D1/D2 association-to-fusion 接线、真实 AirSim multi-seed 协同 replay、D6 长期 schema/阈值和分布式全链路；Stone Soup、FilterPy、MATLAB 仍只作对照。
- **P2**: 接入 Stone Soup/FilterPy/OpenCV/UKF/IMM 作为离线对照，不替换 NumPy fallback；ROS 2 `tf2/message_filters` 和真实 AirSim bus 直连只有在运行环境、topic schema 和 main/shared runtime 合同稳定后再评估。

2026-07-08 补充复核：main runtime 已新增 P1 D4/D5 calibration sweep，并在 sweep 结束后自动生成 D6 标准报告 bundle。该能力属于 main/D6 集成层，不改变 D1 职责边界。D1 当前 P1 重点是保持 replay schema、measurement/arrival timestamp、covariance、latency/OOSM audit、区域质量/窗口摘要和二级侦察 cue 字段稳定，并继续补真实 AirSim multi-seed fixture 与阈值校准样本。

2026-07-09 补充复核：D1 已补齐 main P1 缺口方案中的轻量输入支撑项，包括 dry-run fixture schema version 检查、raw replay observation latency/OOSM audit helper、unsupported JSONL schema 回归、`covariance_scale_reason` passthrough 以及 secondary/mobile recon cue metadata 在 JSONL/CSV reader 和 `GlobalTrack.metadata` 中的保真回归。`SensorHealthSummary`、协方差上下界 reason 和 `timestamp_uncertainty_s` 继续作为已实现 P0-A 质量证据提供给 main/D6；P1 calibration sweep/D6 bundle 对 D1 的消费口径是汇总 observation latency、OOSM、区域质量、窗口趋势、sensor health、covariance reason 和 timing uncertainty，不由 D1 触发主动降级。剩余 P1 不再是这些轻量字段本身，而是更多 main/shared 真实 multi-seed Blocks/CV 样本、D6 长期批量 schema、持续阈值和算法增强项。

2026-07-10 真实 2v2 smoke 复核：六个 episode 共 1,528 条观测全部保留双时间戳和
covariance，未发现时间倒置、非有限 covariance、非对称 covariance 或负特征值；
full-flow main bus 的 36 个 tick 也持续保留观测双时间戳、covariance trace 和
`TrackUncertaintySummary` timing/covariance 字段，未发现 D1 合同回归。实际产物也暴露了
三个仍需明确保留的 P1：main writer 未写 `schema_version`，所以新日志仍走 legacy
兼容路径；观测缺 `coverage_cell` 且 main tick 未发布区域/窗口、latency/sensor-health
摘要，真实区域质量闭环尚未验收；固定 0.2 s 延迟产生的大量合法 OOSM 会使当前 advisory
sensor-health 阈值误报 `isolated`，必须先做 expected-latency/OOSM 基线标定，不能直接
作为 D4 降级证据；main bus 依赖 simulation-only truth hint 保持 2 条航迹，而默认
truth-free replay 会对 TGT-002 产生重复初始化并输出 3 条航迹，说明 replay 配置 provenance
和无真值关联一致性尚未闭合。本轮不修改 main/runtime，也不把上述集成/标定项误写成
D1 已闭合，更不把 truth metadata 当作真实在线身份依据。

2026-07-10 十 seed/身份隔离证据同步：main 已完成 2v2 十 seed 系统运行，说明 D1 DTO 在
reset-separated episode 中可重复被消费；另一个 5v5 truth-isolation smoke 已确认 D5 在线
local detection/MOT ID 不再依赖 actor/object 名称。这两项不新增 D1 P0，也不关闭 D1 的
truth-free replay P1：D1 合成观测中的 `truth_id` 仍只能作离线评分标签，main 的
simulation-only truth-hint 配置仍需写入 provenance 并通过无 truth-hint 多 seed replay
对照。1,528 条观测仍是本轮已逐条验证双时间戳和 covariance 的直接 D1 证据；十 seed
产物尚需固化为带显式 schema、coverage cell、CV bbox covariance 和二级侦察 metadata 的
长期 fixture。

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
| P1 | Track-to-Track 融合原型 | NumPy CI helper 已实现同 canonical ID、1..N 状态、共同时间传播、message UUID/完整 lineage 去重和保守 covariance；未接 D2/runtime 多节点输入 | D1-owned 最小数值原型已关闭；保留 D1/D2 双阶段合同、真实 replay、部分共享 lineage 和分布式共识为 P1 | 构造测试已满足不重复计数和 CI 不比错误独立融合更自信；真实多节点日志仍需验收 |

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
- 中心化协同定位 typed DTO、2..N bearing-ray WLS、几何质量摘要、共同时间传播和 NumPy CI 已作为独立 helper 实现；不改变 `FusionAdapter` 默认路径，也不执行 D2 关联。
- `generate_truth(target_count=N)` 和 CLI `--drone-count N` 已按输入 N 运行，不把算法限制为 2v2 或 5v5；历史 2v2/5v5/3-target 仅作为 baseline 名称或样例。

### 2.2 部分实现

- Stone Soup 和 FilterPy 仅有 placeholder/可用性探测与转换边界，未接入真实 tracker、updater、UKF、IMM、JPDA/MHT 或 OOSM 后端。
- AirSim/Blocks 集成在 D1 侧完成 fake fixture 和 JSONL replay；真实 AirSim 连接、`simGetDetections` 调用、frame capture 和 JSONL 写出属于 main/shared runtime，不在 D1 包内直连。
- EO 无截图合同已实现，D1 只消费 bbox、相机元数据、时间戳和协方差；但未实现 OpenCV calibration、畸变模型、`solvePnP` 或 `projectPoints` 对照。
- 合成 LiDAR 仅是 dry-run/replay 观测模型，不是 AirSim LiDAR plugin 或真实硬件桥。
- `TrackUncertaintySummary` 是单航迹摘要；轻量 `FusionQualityRegionSummary`、`FusionQualityRegionWindowSummary` 和 `ReconCueSummary` 已按当前 track summary/track input 聚合。D6 批量日志 schema、真实多 seed 样本阈值、真实样本回归和更细 NIS 统计仍需后续补齐。
- source lineage 去重覆盖观测主线；独立 CI helper 已覆盖 message UUID/完整 lineage 重复和未知交叉相关保守融合。部分共享 lineage 建模、D2/runtime 接线和分布式共识仍未实现。
- JSONL replay schema v1/legacy 兼容、真实 CV 字段保真和最小 CSV reader 已完成；更多 main/shared 真实 Blocks/CV multi-seed fixture 回归仍未完成。
- 2026-07-08 已补强 CSV 缺省 schema 行的 v1/covariance 验证、嵌套 EO camera metadata 解析、真实 CV bbox/camera/detection metadata 字段保真、区域窗口/协方差增长 helper 和 Blocks calibration CSV 回归；更多 main/shared 真实 Blocks/CV multi-seed fixture 回归仍未完成。

### 2.3 未实现

- UKF 与 IMM-EKF/IMM-UKF 未实现。
- 真实 Stone Soup 后端和真实 FilterPy 后端未实现。
- ROS 2 `tf2` 坐标树和 `message_filters` 时间同步未实现。
- D1 包内真实 AirSim ComputerVision/Blocks runtime 直连、`simGetDetections` 直接 adapter 未实现；这属于 P2 后置直连能力，当前 P1 只跟踪 D1 可消费的 Blocks/CV fixture 回归和字段合同。
- OpenCV calibration、畸变校正、`solvePnP`、`projectPoints` 对照未实现。
- 声学 TDOA/阵列主定位未实现，当前按计划只作为粗方位和类别辅助。
- 多节点 D1/D2/runtime Track-to-Track 全链路和 Stone Soup Track Fusion 对照未实现；NumPy CI 数值基础已实现。

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
| 多传感器来源去重/相关性降权 | 观测主线 source lineage 去重已实现；CI helper 额外按 message UUID 或完整 source lineage 去重，并用 CI 处理未知交叉相关 | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/types.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/fusion.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/cooperative.py`; `research_modules/d1_sensor_fusion/tests/test_cooperative_localization.py` | 不适用 | 部分 lineage overlap 的相关性建模和真实 relay/runtime 对照待补 | P1 中心化基础已完成 |
| 航迹到航迹融合 / 协方差交叉 | 最小 NumPy CI 已实现 1..N 个 6-state NED estimate、共同时间 CV 传播、process/timing covariance 和 canonical ID 保持 | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/cooperative.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/types.py`; `research_modules/d1_sensor_fusion/tests/test_cooperative_localization.py` | 不适用 | D2 关联确认、runtime TrackSummary adapter、真实多 seed 和分布式共识未接 | P1 数值基础完成，集成待补 |
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
3. **算法升级需要对照场景**: UKF、IMM、完整 Track-to-Track runtime 和外部 CI 后端仍需要强非线性、高机动、多节点相关观测基准；当前仅关闭依赖轻的中心化 WLS/CI 数值基础。
4. **ROS/真实运行时不是 D1 当前职责边界**: D1 负责 `SensorObservation` 到 `GlobalTrack`，真实 AirSim/ROS topic、bag、tf tree 和 runtime orchestration 应由 main/shared 层提供。
5. **安全边界**: D1 保持为传感器融合与态势估计模块，不输出控制、处置或授权动作，因此未接任何真实飞控/硬件/火控接口。


## 5. 缺少条件汇总

- **真实运行环境条件**: ROS 2 runtime、tf tree、topic schema、bag/replay 工具、AirSim Blocks 稳定启动和长期 fixture 样本。
- **传感器/坐标条件**: 真实或稳定仿真的相机内外参、畸变模型、AirSim detection 字段映射、actor ID 映射、统一时间戳来源和 WGS84/ENU 到 NED 的外部转换合同。
- **数据合同条件**: `sensor_observations.jsonl` schema v1、legacy Blocks JSONL 兼容、最小 CSV reader、真实 CV 字段保真、轻量区域质量摘要、区域窗口摘要和 `ReconCueSummary` 粗指向摘要已落地；仍需 D6 可消费的长期批量摘要字段、真实多 seed 阈值和 coverage cell 规则细化。
- **算法评估条件**: UKF/IMM/Stone Soup/FilterPy 对照场景、强非线性/高机动/多节点相关观测基准、误差门限和与 NumPy EKF fallback 的容差定义。
- **多节点融合条件**: typed state/CI 数值合同已具备；仍需 D2-confirmed 节点级 TrackSummary adapter、融合权威规则、部分共享 lineage 模型、runtime 日志和分布式共识。

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

## 7. 历史优先级基线（截至 2026-07-10）

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

1. **显式 replay schema 与区域字段**: D1 v1 reader 已实现，但当前 main Blocks writer 的真实 2v2 日志没有 `schema_version` 和 `coverage_cell`，只能走 legacy schema 并生成 `unassigned` 区域；main/shared writer 需显式写 `d1.sensor_observation.v1` 并传递覆盖区域，D1 保持兼容但不修改 main/runtime。
2. **main/D6 长期批量 schema**: main tick 已发布 `TrackUncertaintySummary[]`，但尚未发布 `LatencyAuditSummary`、`FusionQualityRegionSummary[]`、`FusionQualityRegionWindowSummary[]` 和 `SensorHealthSummary[]`；需统一长期 JSONL/CSV 字段、covariance reason 与 timestamp uncertainty 命名。
3. **expected-latency/OOSM 健康阈值**: 真实 smoke 的固定 0.2 s 延迟会产生大量合法 OOSM；需要以传感器延迟预算、同帧 batch/水位线或滑动比率区分正常 replay 与 clock/stale 故障，避免 advisory FDIR-light 在正常流上建议隔离。
4. **truth-free replay 一致性**: main bus 的 simulation-only truth-hint 配置未写入 replay provenance；默认无 truth-hint 重放同一 2v2 JSONL 会产生一条重复航迹。需记录融合/关联配置并校准无真值门控，使离线 replay 与真实在线约束一致，truth metadata 仅作离线标签。
5. **AirSim CV/Blocks multi-seed 回归**: 单次真实 2v2 smoke 已完成输入审计，但仍需 `simGetDetections`/detector boxes 的 N actor、多 seed JSONL/CSV 样本，覆盖 actor label、camera metadata、bbox covariance 和 secondary/mobile recon metadata；D1 不直连真实 AirSim runtime bus。
6. **真实样本区域/质量阈值**: 用带 `coverage_cell` 的多 seed 样本校准区域窗口、freshness/source-gap、协方差增长率和 handover readiness 的持续阈值。
7. **IMM/CV-CA-CT 多模型滤波**: 按 EVAL P1 同步为三个月内能力增强项，先做 CV/CA/CT 或等价模型对照和机动目标 replay/AirSim 评估，不替换当前 NumPy CV/EKF fallback；Stone Soup、FilterPy、MATLAB 只作为 benchmark 或调参参考。
8. **场景自适应协方差**: 在现有距离/质量协方差、bbox confidence/occlusion 输入和雷达参数化基础上，补遮挡、杂波、SNR、来源差异、延迟等 covariance scale rule，并在 replay/AirSim 输出 scale reason。
9. **Track-to-Track 融合原型**: 最小 NumPy CI、source/message 去重、共同时间传播和协方差保守性测试已完成；下一步是 D2-confirmed adapter、真实多节点 replay、成员退出和部分共享 lineage，完整外部库后端仍按收益评估。

### P2: 开源库和算法对照

1. **FilterPy 对照后端**: 以可选依赖方式验证 EKF/UKF 数值差异、运行时间和协方差一致性，不替换现有 NumPy fallback。
2. **Stone Soup 离线实验**: 先做 observation/track 转换、OOSM replay 或 JPDA/MHT/Track Fusion 对照，只有指标收益明确后再扩大接入。
3. **UKF/IMM 基准**: 构造高机动、强非线性和多模型场景，定义相对当前 CV/EKF 的 RMSE、NIS、连续性和计算成本收益门限。
4. **OpenCV/D5 几何对齐**: 将 calibration、畸变、`projectPoints`、`solvePnP` 作为 D5/D1 边界对照项，D1 保持 bbox/camera metadata/协方差合同。
5. **ROS 2 `tf2/message_filters` 评估**: 等 topic schema、tf tree、bag/replay 和 main/shared runtime 稳定后再接入；接入前仍由上游转成 NED 或提供完整外参元数据。

## 8. 历史基线：2026-07-11 P1 缺口复核

| 项目 | 当前状态 | 证据 | 后续责任 |
| --- | --- | --- | --- |
| writer `schema_version` | D1-owned 已关闭 | governed JSONL/CSV writer 强制输出 `d1.sensor_observation.v1` | main/shared 改用该 writer，D1 保留 legacy reader |
| config/scenario provenance | D1-owned 已关闭 | `ReplayProvenance` 强制 scenario/config ID、version/digest | main 传入真实 settings/config digest 和 episode seed |
| 在线 truth hint 隔离 | D1 fixture 已关闭，main 单 seed smoke 已接线 | writer 默认剥离 truth/actor/object ID；`p1_runtime_truth_isolated_d4d5_smoke_20260711` 三个 5v5 episode 在在线 truth 隔离后仍保持 D1 -> D2 -> D3 和 1.0 assignment coverage | 继续做 truth-isolated 多 seed、长时 replay 和离线 truth-only 评分审计 |
| `coverage_cell` 时间窗口 | D1-owned 已关闭 | 固定 `window_size_s` 分桶，窗口输出带开始/结束/持续时间 | main/D6 发布并聚合真实窗口 |
| 协方差增长率窗口 | D1-owned 已关闭 | track growth annotation 与 region window 聚合已回归 | 多 seed 标定报警持续阈值 |
| expected latency/OOSM health | 字段和判定基线已关闭 | 总/非预期 OOSM、期望延迟、容差、均值/最大值和超限率已导出 | 按真实 radar/acoustic/EO 延迟分布校准预算 |
| Blocks/CV JSONL/CSV fixture | 基础 P1 已关闭 | 静态 fixture 保留双时间戳、协方差、NED、coverage 和 provenance | 扩充真实 camera/bbox/遮挡、多 seed fixture |

当前无 D1 P0 blocker。剩余 P1 不再包含最小协同 DTO/WLS/CI 字段和数值 helper，而是 main/D2 runtime 接线、真实多 seed 阈值治理、视觉/协同 fixture、D6 长期趋势、IMM/场景自适应协方差和分布式 Track-to-Track 全链路。Stone Soup、FilterPy 仍未引入。

## 9. 历史基线：2026-07-11 Truth-Isolated 5v5 证据状态

证据目录：
`research_modules/airsim_runtime/outputs/p1_runtime_truth_isolated_d4d5_smoke_20260711/`。

| 核查项 | 当前证据 | 缺口判定 |
| --- | --- | --- |
| D1 -> D2 -> D3 在线断链 | 三个 5v5 case 均运行 5 帧；D1/D2/D3 health 为 `ok`，D1 每组 15 条记录，D3 assignment coverage 为 1.0 | 单 seed 短时 smoke 已通过，无 P0 断链 |
| 在线 truth 隔离 | main 在线关联不再依赖 truth hint，仍输出中心航迹和分配 | 单 seed 接线已通过；multi-seed/长时一致性仍为 P1 |
| D1 governance 进入 main bus | 每组均有 `d1_latency_audit`、`d1_region_quality_window`；metrics 含 delay、OOSM、region quality/readiness | 基础接线已完成；长期 schema 和完整 health/reason 字段仍为 P1 |
| OOSM 口径 | 三组 `d1_oosm_observation_rate=0.9866666667`，mean/max delay 约 0.2 s，stale rate 为 0 | 这是固定延迟异步回放累计口径，不是传感器故障率；预算、水位线和故障对照标定仍为 P1 |
| multi-seed 阈值治理 | 当前只有 seed 7、5 帧、0.4 s | 未关闭；必须保留 P1 |

因此本轮只更新证据状态，不关闭 D1 的真实多 seed、长时间窗口、sensor-specific latency、
故障注入负例、D6 长期 schema 和真实 Blocks/CV fixture P1。尤其不得把 raw OOSM rate
直接解释为 FDIR 隔离建议或 D4 主动降级条件。

## 10. M 对 N 协同定位 P0/P1 状态（2026-07-11）

文献与开源证据详见 `D1_M_TO_N_COOPERATIVE_LOCALIZATION_REVIEW.md`。本节只增加 P0/P1 现状，不改既有 P2/P3 外部库接入条目。

- **P0**：无新增 blocker。双时间戳、NED、观测/航迹 covariance、source lineage 去重和 canonical `global_track_id` 禁止本地改写仍为硬回归。
- **P1-协同几何质量 D1-owned 基础完成**：typed DTO/summary 已输出共同估计时刻、平台位姿/外参 covariance、measurement skew、LOS 交会角、联合信息矩阵秩/条件数、bearing residual、observer lineage 和 accept/reject reason；三架平台数量仍不得直接解释为 `handover` 就绪。
- **P1-异步三机构造基准完成，真实 replay 未完成**：单元测试覆盖 1/2/3/N observer、良好三视角、退化几何和 0.4 s 异步传播；near-synchronous/range、机动、遮挡、节点退出、AirSim 多 seed 及 RMSE/NIS/NEES consistency 仍缺。
- **P1-D1/D2 合同**：D2 应先确认 local TrackSummary 与 canonical `global_track_id` 的关联，D1 再进行数值 Track-to-Track 融合；当前尚无该双阶段合同和拒绝误融合事件。D1 不得因三角化结果自行创建替代身份。
- **P1-保守 Track-to-Track 数值原型完成**：NumPy CI 支持 1/2/3/N source、共同时间 CV 传播、process/timing covariance、message UUID/完整 lineage 去重并保持 canonical ID；已验证不比错误独立融合更自信。部分共享 lineage、D2/runtime adapter、成员退出 replay 和 Stone Soup 对照仍待补。
- **P1-到达时序边界**：D1 不要求三机严格同时观测或同时到达拦截点；必须按 measurement time 传播到共同估计时刻并报告 covariance growth。同步/分波次拦截决策属于 D3/D7。

P1 最小验收：良好几何下三机融合不劣于最佳双机；退化几何必须增大 covariance 或拒绝融合；relay 重发不改变 posterior；未知相关性融合保持保守；节点从 3 降到 2/1 时航迹连续且质量显式下降；在线链路不使用 truth/actor ID。

## 11. 历史基线与双轨实施顺序（2026-07-11 三 seed）

最新依据为
`research_modules/airsim_runtime/outputs/blocks_cv_m5_n2_liveness_batch_20260711/M_TO_N_AIRSIM_CONVERGENCE_REPORT_CN.md`：
seeds 7/17/27 均为 6 次 replan request、6 次 no-change ACK、0 applied、0 expired，需求满足率
1.0，错误重复锁定 0；T002 共识为 4/5/4 且 D7 每 seed 许可 2 次；T001 双 primary 共识为
0。该证据证明 ComputerVision 状态合同收敛，不是物理拦截证据，也没有关闭 D1 的真实
传感器、多机协同定位或长期阈值标定。

| 层级 | 当前结论 | 后续动作 |
| --- | --- | --- |
| P0 | 无运行级 blocker；双时间戳、NED、covariance、FDIR-light、上下界、时间戳不确定性、lineage 去重和 N-target 输入已闭合 | 维持 `62 passed` 回归，不降低合同 |
| P1 已完成接口 | governed writer/schema/provenance、truth 默认剥离、区域/窗口摘要、expected-latency/OOSM、recon cue、协同 DTO/WLS/CI | 接入 main/D2/D6，不重复实现 helper |
| P1 待实现/标定 | main writer 采用、D2-confirmed runtime adapter、真实多 seed 机动/遮挡/节点退出/camera fixture、RMSE/NIS/NEES、health/window 阈值、IMM/场景自适应 covariance、长期 D6 schema | 按真实 replay 逐项关闭；T001 共识由 D5/D7 主责，D1 只提供状态/协方差/几何质量 |
| P2 optional | FilterPy、Stone Soup、OpenCV/GTSAM、ROS 2 | 仅隔离 benchmark；不得替换默认 NumPy 主线 |

实施顺序为：main/shared 采用 governed writer 和离线 truth 分离；D1/D2 接通 canonical-ID
确认后的可选 WLS/CI adapter；main 采集 crossing、机动、遮挡、漏检、延迟和节点退出的
真实多 seed replay；D1/D6 校准统计与阈值；最后才运行 P2 第三方对照。每次 D1 能力变更后
使用
`PYTHONPATH=research_modules/d1_sensor_fusion/src pytest -q research_modules/d1_sensor_fusion/tests`
验收，并同步本审计、PLAN、README 和 review。

## 12. Governed Replay Manifest/Serializer P1 状态

本轮已关闭 D1-owned 的严格 manifest/serializer 实现缺口：

| 项目 | 当前状态 | 边界 |
| --- | --- | --- |
| manifest schema | 已实现 `d1.governed_replay_manifest.v1`，汇总 observation schema、NED working frame、时间范围、coverage cells、lineage 和 truth policy | main 负责持久化位置和 episode 组织 |
| scenario/config identity | strict provenance 要求 scenario/config ID、version、digest 和 seed | main 必须传入真实 settings/config digest；D1 不猜测 |
| record validation | 已校验双时间戳、covariance 形状/有限性/对称/半正定、coverage cell 和 source lineage | legacy reader 继续宽松兼容旧日志，不视为 governed 输入 |
| online truth isolation | 默认批量 serializer 递归剥离 truth/actor/object ID，opaque lineage 不含 truth fingerprint | 离线标签仅由 `serialize_offline_governed_replay()` 写入 `offline_truth` |
| 多目标与数值保真 | 已测试任意长度批次、双时间戳、NED frame、covariance、coverage 和 lineage 往返 | 未代表真实 AirSim 传感器标定完成 |

当前 D1 全量测试为 `62 passed`。因此“构造可供 main 调用的 governed manifest/serializer”
不再列为 P1 缺口；最新 main episode bus 也已采用该 API 并分离在线记录与离线 truth 标签。
仍开放的是更长的真实 multi-seed 数据生成与阈值标定、D1/D2-confirmed runtime fusion
adapter、D6 长期统计一致性和算法增强。P2 外部库安排不变。

## 13. 当前缺口判定（2026-07-11 最终验证）

最终依据为
`research_modules/airsim_runtime/outputs/p1_p2_validation_20260711/P1_P2_VALIDATION_SUMMARY_CN.md`。

| 层级 | 当前结论 | D1 边界 |
| --- | --- | --- |
| P1 合同层 | 已闭合 | main episode bus 已写 D1 governed replay；双时间戳、covariance、coverage/lineage 和 provenance 进入同一 episode 合同链，在线 truth/actor/object ID 被剥离，truth 仅进入独立离线标签 |
| CV 验收 | 8/10 通过 | 证明 D1 合同可被下游双 primary 链路消费；不表示 D1 负责视觉共识或控制许可 |
| 二级/分布式故障语义 | 3/3 ACK commit 正例和 2/3 ACK abort fail-closed 均通过 | D1 只提供状态、协方差、时间和质量证据，不参与 coalition commit/ACK 仲裁 |
| P1 物理/长期标定 | 未闭合 | SimpleFlight 15 s 为诊断，30 个 active pair 为 0 命中；不作为 D1 真实传感器或融合精度验收。D1 仍需真实 multi-seed 长 replay、sensor-specific latency/health/window 与 RMSE/NIS/NEES 标定；系统物理拦截闭环不由 D1 单独负责 |
| P2 optional benchmark | 隔离 harness 已完成；第三方后端 unavailable | 冻结 governed replay 已对当前 NumPy EKF/fixed-lag 输出 RMSE/NIS/NEES/耗时；FilterPy/Stone Soup 当前均未安装，结果包含 `unavailable_reason` 且指标为空。未新增默认依赖、未替换在线路径；真实第三方 adapter、UKF/IMM 仍开放 |

当前 D1 的 AirSim dry-run adapter、静态 JSONL/CSV fixture 和 ComputerVision 合同验证属于
adapter/smoke 证据；合成 radar/acoustic/EO 观测、CV/EKF 机动吸收及 WLS/CI 数值 helper
属于科研仿真基线。它们证明接口、数值合同和 truth policy 可回归，不等于真实传感器模型、
长时物理 replay、完整分布式 Track-to-Track 或第三方 tracker/fuser 已完成。

当前 D1 P1 后续项只保留真实 replay 与标定：D1/D2-confirmed cooperative adapter、机动、
遮挡、节点退出、camera/bbox、sensor-delay/fault 多 seed 数据，以及 RMSE/NIS/NEES、
sensor-specific expected latency、health/region window、模型集和场景自适应 covariance。
不得再把 governed writer 接入、在线 truth 隔离或 CV 双 primary 合同验收列为当前未完成项。

## 14. P2 隔离 Benchmark GAP 收敛（2026-07-11）

| 核查项 | 当前证据 | GAP 判定 |
| --- | --- | --- |
| 冻结输入治理 | `p2_governed_filter_benchmark_v1.json` 固定 manifest、scenario/config digest、seed、NED、双时间戳、covariance 和 lineage | 最小离线 benchmark 输入已闭合；不替代真实 multi-seed replay |
| truth 隔离 | online records 禁止 truth/actor/object metadata，truth 六状态只在独立 offline sidecar，测试覆盖泄漏拒绝 | benchmark 未向 `FusionAdapter` 注入 truth |
| 当前路径指标 | runner 输出 position RMSE、NIS、NEES、normalized consistency 和 wall time；结果为 `0.2335 m`、`0.0426`、`0.0651`，两次耗时 `6.9-10.1 ms` | 指标 plumbing 已闭合；小型合成样本的低 NIS/NEES 不关闭真实标定 |
| FilterPy | 当前环境依赖不可用，adapter 为 placeholder，输出 null metrics 和 `unavailable_reason` | 不得写成已接入；隔离安装后的可执行 EKF/UKF 对照仍为 P2 |
| Stone Soup | 当前环境依赖不可用，adapter 为 placeholder，输出 null metrics 和 `unavailable_reason` | 不得写成已接入；OOSM/JPDA/MHT/Track Fusion 对照仍为 P2 |
| 默认路径 | requirements 和在线 `FusionAdapter` 未修改 | NumPy EKF/fixed-lag 继续是唯一默认路径 |

本轮 D1 全量回归为 `62 passed`。因此 P2 可用性、不可用原因和当前路径指标证据已收敛；
第三方后端的算法收益仍未证明，不能因本轮 harness 完成而关闭相应实现 GAP。
