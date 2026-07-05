# D1 实现差距审计

**模块**: D1 多传感器融合与目标配准  
**范围**: 对照 `subagent_reviews/D1_SENSOR_FUSION_REVIEW_AND_PLAN.md`、`C_UAS_MAINSTREAM_SOLUTIONS_AND_DIFFICULTIES.md`、`research_modules/d1_sensor_fusion` 源码和测试，审计共识算法、开源方案和当前实现差距。  
**边界**: 本审计只覆盖离线科研仿真、数据合同、传感器观测、航迹融合和评估接口；不涉及真实飞控、硬件驱动、火控、毁伤或自动处置。

## 1. 总体结论

D1 当前已经实现了可运行的轻量主线：`SensorObservation -> NumPy EKF/FusionAdapter -> GlobalTrack`，支持雷达、声学、EO、可选合成 LiDAR，具备测量时刻/到达时刻分离、fixed-lag replay 延迟补偿、可参数化距离/置信度相关协方差、AirSim dry-run fake fixture、跨节点通信元数据、source lineage 去重基线、`TrackUncertaintySummary` 导出和 `blocks_sensor_observations.jsonl` reader/replay。D1 接收 main 提供的 N 个 target truth/观测源，并按输入数组长度处理 `SensorObservation[]` 与 `GlobalTrack[]`；真实 AirSim runtime bridge 仍由 shared/main 层负责，D1 不直连 AirSim。

尚未实现的主要是外部成熟框架集成：Stone Soup、FilterPy、ROS 2 `tf2`、`message_filters`、UKF、IMM、D1 包内真实 AirSim ComputerVision/Blocks 运行时适配。这些目前有文档计划或占位类，但未作为 D1 运行依赖接入。原因主要是当前阶段强调依赖轻、可复现、离线测试稳定，且缺少 ROS 2 runtime、稳定真实 AirSim detection schema/外参标定链路、CSV/长期样本回归和多模型评估基准。

优先级建议：

- **P0**: 保持当前 NumPy EKF、传感器观测模型、延迟补偿和 AirSim dry-run 合同稳定。
- **P1**: `TrackUncertaintySummary` 发布/导出、Blocks JSONL replay reader、可配置雷达协方差参数和 source de-dup 基线已完成；CSV reader、更多 AirSim CV detection schema 回归和区域质量摘要仍可后续补。
- **P2**: 接入 Stone Soup/FilterPy 作为离线对照后端，增加 UKF/IMM 基准。
- **P3**: ROS 2 `tf2/message_filters` 与真实 AirSim/Blocks 运行时桥接，待外部运行环境和消息格式稳定后实施。


## 2. 按实现状态归类

### 2.1 已实现

- `SensorObservation` 统一合同已落地，支持 `radar/acoustic/eo/lidar`，强制保留 `measurement_timestamp`、`arrival_timestamp`、`frame_id`、`measurement`、`covariance`、置信度、质量标记和通信元数据。
- `FusionAdapter` 已实现 NumPy EKF 融合主线，输出六维 NED `GlobalTrack`、6x6 协方差、`source_support`、质量等级、`valid_at/published_at`、最近量测时间和最近到达时间。
- fixed-lag/OOSM 延迟补偿已实现，观测按 `measurement_timestamp` 插入历史并重放到当前 `arrival_timestamp`；消融测试要求补偿 RMSE 明显优于未补偿基线。
- 雷达距离相关协方差已通过 `RadarCovarianceConfig` 参数化；声学为弱方位约束；EO 为 pinhole 像素投影约束；合成 LiDAR 作为 dry-run NED 三维位置量测。
- AirSim dry-run fixture 已实现，不导入 AirSim，可生成 radar/acoustic/eo/lidar `SensorObservation[]` 并喂给 `FusionAdapter`。
- Blocks JSONL replay reader 已实现，D1 可读取 `blocks_sensor_observations.jsonl` 并回放融合；N actor 合同测试覆盖按输入数组长度输出 `GlobalTrack[]`。
- `TrackUncertaintySummary` 已实现数据类与导出方法，包含协方差迹、`a95`、等级、measurement age、source support、coverage cell、measurement/arrival timestamp 和 handover readiness。
- source lineage 去重基线已实现，可抑制同一 source/sequence/payload 经 relay 重复投递导致的重复更新。
- `generate_truth(target_count=N)` 和 CLI `--drone-count N` 已按输入 N 运行，不把算法限制为 2v2 或 5v5；历史 2v2/5v5/3-target 仅作为 baseline 名称或样例。

### 2.2 部分实现

- Stone Soup 和 FilterPy 仅有 placeholder/可用性探测与转换边界，未接入真实 tracker、updater、UKF、IMM、JPDA/MHT 或 OOSM 后端。
- AirSim/Blocks 集成在 D1 侧完成 fake fixture 和 JSONL replay；真实 AirSim 连接、`simGetDetections` 调用、frame capture 和 JSONL 写出属于 main/shared runtime，不在 D1 包内直连。
- EO 无截图合同已实现，D1 只消费 bbox、相机元数据、时间戳和协方差；但未实现 OpenCV calibration、畸变模型、`solvePnP` 或 `projectPoints` 对照。
- 合成 LiDAR 仅是 dry-run/replay 观测模型，不是 AirSim LiDAR plugin 或真实硬件桥。
- `TrackUncertaintySummary` 是单航迹摘要；区域聚合窗口、D6 批量日志 schema、协方差增长率和更细 NIS 统计仍需后续补齐。
- source lineage 去重只解决重复 payload；未知相关性的跨节点 Track-to-Track fusion、协方差交叉和相关性降权尚未实现。
- JSONL replay 已完成；CSV reader、通用 schema version 和更多真实 Blocks fixture 回归仍未完成。

### 2.3 未实现

- UKF 与 IMM-EKF/IMM-UKF 未实现。
- 真实 Stone Soup 后端和真实 FilterPy 后端未实现。
- ROS 2 `tf2` 坐标树和 `message_filters` 时间同步未实现。
- D1 包内真实 AirSim ComputerVision/Blocks runtime 直连、`simGetDetections` 直接 adapter 未实现。
- OpenCV calibration、畸变校正、`solvePnP`、`projectPoints` 对照未实现。
- 声学 TDOA/阵列主定位未实现，当前按计划只作为粗方位和类别辅助。
- 多节点 Track-to-Track fusion、协方差交叉和 Stone Soup Track Fusion 对照未实现。

## 3. 逐项差距表

| 预期项 | 当前状态 | 证据文件 | 未实现原因 | 缺失条件 | 建议优先级 |
|---|---|---|---|---|---|
| 统一 `SensorObservation` 数据合同 | 已实现。支持 `radar/acoustic/eo/lidar`、`measurement_timestamp`、`arrival_timestamp`、`frame_id`、`covariance`、质量字段和通信元数据 | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/types.py`; `research_modules/d1_sensor_fusion/tests/test_interfaces.py` | 不适用 | D1 JSONL reader/replay 已完成；仍需通用 schema version 和更多真实 Blocks 样本回归 | P0/P1 |
| `GlobalTrack` 六维航迹输出 | 已实现。输出 `[px, py, pz, vx, vy, vz]`、6x6 协方差、`track_level`、`source_support`、`metadata.frame_id/valid_at/published_at/a95_m` | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/types.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/fusion.py` | 不适用 | 需要继续补充 track version / latest measurement summary 标准化 | P0 |
| 跨节点通信元数据 | 已实现最小支持。字段包括 `source_node_id`、`target_node_id`、`relay_node_id`、`link_type`、`sent_timestamp`、`received_timestamp`、`payload_kind`、`stale_after_s`、`source_support` | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/types.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/fusion.py`; `research_modules/d1_sensor_fusion/tests/test_interfaces.py` | 不适用 | 需要 main 确定节点 ID、链路类型和 stale 策略的枚举 | P0 |
| EKF 主滤波器 | 已实现。自研 NumPy EKF、数值雅可比、Joseph 形式协方差更新、NIS 输出 | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/ekf.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/fusion.py` | 不适用 | 后续需增加与 FilterPy/Stone Soup 的数值对照 | P0 |
| 常速度 CV 运动模型 | 已实现。六维 CV 预测和白加速度谱密度过程噪声 | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/motion.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/ekf.py` | 不适用 | 对高机动目标需更多模型 | P0 |
| UKF | 未实现。文档中列为强非线性场景升级项 | `research_modules/d1_sensor_fusion/docs/ALGORITHM_AND_IMPLEMENTATION.md`; `subagent_reviews/D1_SENSOR_FUSION_REVIEW_AND_PLAN.md` | 当前 EKF 足够覆盖离线主线；未引入 FilterPy/Stone Soup 依赖 | 需要 UKF 后端接口、sigma-point 参数、对照场景和误差指标 | P2 |
| IMM-EKF/IMM-UKF | 未实现。文档中列为机动目标升级项 | `C_UAS_MAINSTREAM_SOLUTIONS_AND_DIFFICULTIES.md`; `research_modules/d1_sensor_fusion/docs/ALGORITHM_AND_IMPLEMENTATION.md` | 当前状态维度和场景仍以 CV/EKF 为主；D2 关联先用基础航迹 | 需要 CV/CA/CT 模型集合、模型转移概率、机动场景和 D2 接口约定 | P2 |
| Stone Soup 集成 | 占位实现。只提供不导入 Stone Soup 的 placeholder 和 detection dict 转换；未接入真实 Stone Soup tracker/fuser/OOSM | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/compat.py`; `research_modules/d1_sensor_fusion/tests/test_interfaces.py` | 保持当前测试不依赖外部包；Stone Soup 适合作为离线对照而非主运行依赖 | 需要安装依赖、设计 D1 observation/track 转换、选择 Stone Soup updater/initiator/fuser、定义对照实验 | P2 |
| FilterPy 集成 | 占位实现。只检测可用性并说明 fallback 状态；未调用 FilterPy EKF/UKF/IMM | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/compat.py`; `research_modules/d1_sensor_fusion/tests/test_interfaces.py` | 当前已有自研 EKF，避免新增依赖和版本差异 | 需要明确 FilterPy 后端接口、测试容差、UKF/IMM 目标 | P2 |
| ROS 2 `tf2` | 未实现，仅文档计划。当前只用 `metadata` 中的 NED 位置和相机外参 | `research_modules/d1_sensor_fusion/docs/AIRSIM_INTEGRATION_PLAN.md`; `research_modules/d1_sensor_fusion/docs/ALGORITHM_AND_IMPLEMENTATION.md` | 当前仓库没有 ROS 2 runtime 和 tf tree；AirSim dry-run 不需要 ROS | 需要 ROS 2 环境、frame 命名规范、外参版本、tf buffer 与时间戳策略 | P3 |
| ROS 2 `message_filters` | 未实现，仅文档计划。当前依赖 `arrival_timestamp` 排序和 fixed-lag replay | `research_modules/d1_sensor_fusion/docs/AIRSIM_INTEGRATION_PLAN.md`; `subagent_reviews/D1_SENSOR_FUSION_REVIEW_AND_PLAN.md` | 离线 replay 不需要 ROS message filters；OOSM 补偿已经在 D1 内实现 | 需要 ROS topic schema、同步策略、允许延迟窗口和 bag/replay 工具 | P3 |
| 雷达观测模型 | 已实现。`[range, azimuth, elevation, radial_velocity]`，支持传感器位置和角度 wrap | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/observations.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/simulation.py` | 不适用 | 需要真实/仿真雷达配置时再参数化噪声模型 | P0 |
| 雷达距离相关协方差 | 已实现并可参数化。`RadarCovarianceConfig` 保持默认行为兼容，也可按距离系数覆盖 | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/observations.py`; `research_modules/d1_sensor_fusion/tests/test_interfaces.py` | 不适用 | 后续可按真实雷达型号、SNR、杂波、遮挡策略扩展配置来源 | P1 已完成基线 |
| 雷达初始化新航迹 | 已实现。`_create_track()` 只允许雷达初始化，避免声学/EO 单独造三维真值 | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/fusion.py` | 不适用 | 如果要 EO/depth 初始化，需要额外深度/多视角约束 | P0 |
| 声学观测模型 | 已实现弱约束。仅方位角 + confidence 相关角度协方差 + `classification_hint` | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/observations.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/simulation.py` | 不适用 | 未实现 TDOA/声阵列硬件模型；缺少阵列几何和声学仿真参数 | P0 |
| 声学主定位/TDOA | 未实现，且不建议作为主线。文档明确声学只作粗方位和类别辅助 | `C_UAS_MAINSTREAM_SOLUTIONS_AND_DIFFICULTIES.md`; `subagent_reviews/D1_SENSOR_FUSION_REVIEW_AND_PLAN.md` | 主流共识认为声学主定位场景受限，且硬件相关性强 | 需要阵列几何、采样率、TDOA 估计、风噪/混响模型 | P3 |
| EO 像素观测模型 | 已实现。使用 pinhole 相机模型，像素中心观测，bbox/置信度/遮挡影响协方差 | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/observations.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/simulation.py` | 不适用 | 需要与 D5/主程序统一 camera metadata schema | P0 |
| EO 无截图输入 | 已实现合同层面。D1 只需要 bbox、相机元数据、时间戳和协方差，不要求 PNG | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/observations.py`; `research_modules/d1_sensor_fusion/docs/ALGORITHM_AND_IMPLEMENTATION.md`; `subagent_reviews/D1_SENSOR_FUSION_REVIEW_AND_PLAN.md` | 不适用 | 需要 main 从 AirSim CV 输出稳定 JSONL/CSV detection 记录 | P1 |
| OpenCV calibration / solvePnP / projectPoints | 未实现。当前是自研简单 pinhole 投影，不依赖 OpenCV | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/observations.py`; `C_UAS_MAINSTREAM_SOLUTIONS_AND_DIFFICULTIES.md` | 当前仅需 dry-run 和离线约束；OpenCV 更适合 D5 精细投影/标定 | 需要真实相机内外参、畸变模型、坐标链和 D5 共同接口 | P2 |
| 合成 LiDAR 观测 | 已实现 optional dry-run。作为 NED 三维位置量测，含 3x3 covariance | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/types.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/observations.py`; `research_modules/d1_sensor_fusion/tests/test_airsim_dry_run.py` | 不适用 | 当前为合成 dry-run，不是 AirSim LiDAR plugin 或真实硬件 | P1 |
| fixed-lag / OOSM 延迟补偿 | 已实现。按 `measurement_timestamp` 重排历史观测、回放更新并传播到当前时刻 | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/fusion.py`; `research_modules/d1_sensor_fusion/tests/test_interfaces.py`; `research_modules/d1_sensor_fusion/tests/test_simulation_metrics.py` | 不适用 | 需要补充 OOSM 计数、最大延迟、重放次数等审计指标 | P0/P1 |
| 延迟补偿消融实验 | 已实现。测试要求补偿 RMSE 明显优于未补偿 | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/simulation.py`; `research_modules/d1_sensor_fusion/tests/test_simulation_metrics.py`; `research_modules/d1_sensor_fusion/reports/EXPERIMENT_REPORT.md` | 不适用 | 需要扩大到 main `--drone-count N` 集成、跨节点通信、二级节点转发延迟；历史 2v2/5v5 只作为 baseline | P1 |
| 协方差输出与航迹分级 | 已实现。输出 6x6 协方差、`a95_m`、`coarse/stable/handover`、NIS 通过率参与分级，并可导出 `TrackUncertaintySummary` | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/fusion.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/metrics.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/types.py` | 不适用 | 区域级质量摘要仍需后续对齐 D4/D6 | P1 已完成基线 |
| `TrackUncertaintySummary` | 已实现 D1 数据类和 `FusionAdapter.track_uncertainty_summaries()` 导出。字段包含 track IDs、协方差迹/a95、等级、measurement age、source support、coverage cell 和时间戳 | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/types.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/fusion.py`; `research_modules/d1_sensor_fusion/tests/test_interfaces.py` | 不适用 | 后续可继续补区域聚合窗口、D6 批量日志 schema 和更细 NIS 统计 | P1 已完成基线 |
| 多传感器来源去重/相关性降权 | 已实现 source lineage 去重基线。相同 source/sequence/payload lineage 或 relay 重复投递不会重复更新同一观测 | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/types.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/fusion.py`; `research_modules/d1_sensor_fusion/tests/test_interfaces.py` | 不适用 | 未实现未知相关性跨节点 Track-to-Track fusion、协方差交叉或相关性降权模型 | P1 已完成基线 |
| 航迹到航迹融合 / 协方差交叉 | 未实现。Stone Soup Track Fusion 仅在主流方案中列为候选 | `C_UAS_MAINSTREAM_SOLUTIONS_AND_DIFFICULTIES.md`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/compat.py` | 当前 D1 融合的是观测到航迹，不是多节点 Track-to-Track | 需要节点级 TrackSummary、相关性未知处理、融合权威规则 | P2 |
| AirSim dry-run fake fixture | 已实现。可从 fake fixture 生成 radar/acoustic/eo/lidar `SensorObservation[]`，不连接真实 AirSim | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/airsim_dry_run.py`; `research_modules/d1_sensor_fusion/tests/test_airsim_dry_run.py`; `research_modules/d1_sensor_fusion/docs/AIRSIM_INTEGRATION_PLAN.md` | 不适用 | 需要继续与 shared/main 的 Blocks JSONL 输出保持回归一致 | P0 |
| 共享 AirSim dry-run orchestrator 对接 | 已由共享模块复用 D1 dry-run 适配器；D1 侧合同可用 | `research_modules/airsim_dryrun/adapters.py`; `research_modules/airsim_dryrun/tests/test_dryrun_contracts.py` | 不适用 | 该模块不属于 D1；后续由 main 维护统一 runtime | P0 |
| shared/main AirSim Blocks D1 replay 写出 | shared runtime 可从 Blocks frame 生成 `SensorObservation` 并写 `blocks_sensor_observations.jsonl`；D1 包内已能读取该 JSONL 并回放 `FusionAdapter` | `research_modules/airsim_runtime/adapters.py`; `research_modules/airsim_runtime/orchestrator.py`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/replay.py`; `research_modules/d1_sensor_fusion/tests/test_airsim_dry_run.py` | 不适用 | 后续需继续跟随 schema 演进补更多真实输出回归样本 | P1 已完成基线 |
| 真实 AirSim ComputerVision / Blocks runtime | 未在 D1 包内实现。D1 只提供 fake fixture 和 `SensorObservation` 类型；真实 AirSim 连接、frame capture、`simGetDetections` 和 JSONL 写出在 main/shared 层 | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/airsim_dry_run.py`; `research_modules/d1_sensor_fusion/docs/AIRSIM_INTEGRATION_PLAN.md`; `research_modules/airsim_runtime/real_runtime.py` | 避免 D1 依赖 AirSim Python 包和 runtime；真实 AirSim orchestration 由 main/shared 层负责 | 需要稳定 Blocks JSONL/detection schema、真实相机外参、actor ID 映射、时间戳来源和长期 fixture 回归 | P1/P3 |
| AirSim `simGetDetections` 直接适配 | 未实现 D1 直连。当前要求 main 转成 bbox/camera metadata 或 fake fixture | `research_modules/d1_sensor_fusion/docs/AIRSIM_INTEGRATION_PLAN.md`; `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/airsim_dry_run.py` | 避免 D1 依赖 AirSim Python 包和 runtime | 需要 detection 字段命名、相机坐标、actor ID 映射、时间戳来源 | P1 |
| JSONL/CSV replay 输入合同 | JSONL 基线已实现。D1 可读取 `blocks_sensor_observations.jsonl` 并回放 `FusionAdapter`；CSV reader 未实现 | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/replay.py`; `research_modules/d1_sensor_fusion/tests/test_airsim_dry_run.py`; `research_modules/airsim_runtime/orchestrator.py` | 不适用 | 需要未来通用 `sensor_observations.jsonl` schema version、CSV reader 和更多真实 Blocks fixture | P1 JSONL 基线完成 |
| N-target D1 独立真值生成 | 已实现。`generate_truth(target_count=N)` 不再把目标数裁剪到 2/5 或 1-3，命令行统一使用 `--drone-count N`，历史 3 目标输出保留为 baseline | `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/simulation.py`; `research_modules/d1_sensor_fusion/scripts/run_simulation.py` | 不适用 | 系统级真值仍由 main/integrated 场景提供，D1 只消费其输出 | P1 已完成基线 |
| 单元/接口测试 | 已实现。覆盖时间戳、桶、协方差增长与参数化、延迟观测、通信元数据、dry-run、JSONL replay、source de-dup、TrackUncertaintySummary、N actor 合同和仿真指标 | `research_modules/d1_sensor_fusion/tests/test_interfaces.py`; `research_modules/d1_sensor_fusion/tests/test_airsim_dry_run.py`; `research_modules/d1_sensor_fusion/tests/test_simulation_metrics.py` | 不适用 | 更多真实 AirSim CV 场景和 JSONL 样本仍可后续扩充；2v2/5v5 只作为 baseline 回归命名 | P0/P1 |

## 4. 主要未实现原因归类

1. **依赖与环境未固定**: Stone Soup、FilterPy、ROS 2、tf2、message_filters 和真实 AirSim runtime 都会引入外部环境约束。当前 D1 选择 NumPy fallback，保证仓库在无外部服务时可测试。
2. **消息合同仍需继续演进**: D1 已有 Blocks JSONL reader/replay 基线，但通用 schema version、CSV reader、更多真实 detection 字段映射和长期回归样本仍需补齐。
3. **算法升级需要对照场景**: UKF、IMM、Track-to-Track fusion、协方差交叉需要明确强非线性、高机动、多节点相关观测等触发场景，否则容易增加复杂度但不提升当前基线。
4. **ROS/真实运行时不是 D1 当前职责边界**: D1 负责 `SensorObservation` 到 `GlobalTrack`，真实 AirSim/ROS topic、bag、tf tree 和 runtime orchestration 应由 main/shared 层提供。
5. **安全边界**: D1 保持为传感器融合与态势估计模块，不输出控制、处置或授权动作，因此未接任何真实飞控/硬件/火控接口。


## 5. 缺少条件汇总

- **真实运行环境条件**: ROS 2 runtime、tf tree、topic schema、bag/replay 工具、AirSim Blocks 稳定启动和长期 fixture 样本。
- **传感器/坐标条件**: 真实或稳定仿真的相机内外参、畸变模型、AirSim detection 字段映射、actor ID 映射、统一时间戳来源和 WGS84/ENU 到 NED 的外部转换合同。
- **数据合同条件**: `sensor_observations.jsonl` schema version、CSV reader 需求、D6 可消费的批量摘要字段、区域质量摘要窗口和 coverage cell 规则。
- **算法评估条件**: UKF/IMM/Stone Soup/FilterPy 对照场景、强非线性/高机动/多节点相关观测基准、误差门限和与 NumPy EKF fallback 的容差定义。
- **多节点融合条件**: 节点级 TrackSummary、相关性未知处理策略、协方差交叉/Track-to-Track fusion 权威规则和 source lineage 之外的相关性降权模型。

## 6. 下一步优先级

1. **P0 保持稳定**: 现有 EKF、雷达/声学/EO/LiDAR 观测模型、延迟补偿、通信 metadata 和 dry-run 测试继续作为主线。
2. **P1 补接口缺口**: `TrackUncertaintySummary` 导出、Blocks JSONL replay reader、雷达协方差参数配置和 source de-dup 基线已完成；下一步补 CSV reader、区域质量摘要和更多 AirSim CV/Blocks detection schema 测试。
3. **P2 做开源对照**: 在不替换主线的前提下接入 FilterPy/Stone Soup 对照实验，先验证 EKF/UKF/OOSM/Track Fusion 的指标差异。
4. **P3 接运行时**: 待 ROS 2 和真实 AirSim Blocks 运行时稳定后，再引入 `tf2/message_filters`、ROS bag replay 和真实 camera/radar bridge。
