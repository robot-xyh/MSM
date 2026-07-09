# 框架评估 P0/P1/P2 缺口确认

**文档版本**: v2.1
**更新日期**: 2026-07-09
**生成角色**: main agent
**定位**: EVAL 层跨模块优先级归并，不直接替代 D1-D7 owned GAP/PLAN。

## 1. 输入材料

本次更新在原 8 份评估文档基础上，额外审读了 3 份 patch：

- `EVAL/FRAMEWORK_EVAL_PATCH_ENGINEERING_PRACTICES.md`
- `EVAL/FRAMEWORK_EVAL_PATCH_2026_VERIFIED.md`
- `EVAL/FRAMEWORK_EVAL_PATCH_WEBSEARCH_2026.md`

并同步了 2026-07-09 P1 接口补齐结果：

- `subagent_reviews/MAIN_P0_P1_GAP_STATUS.md`
- `subagent_reviews/MAIN_IMPLEMENTATION_GAP_AUDIT.md`
- D1-D7 各模块 `subagent_reviews/Dx_IMPLEMENTATION_GAP_AUDIT.md`
- main runtime P1 smoke 输出：`research_modules/airsim_runtime/outputs/p1_gap_fix_smoke_20260709/`

仍然参考的原始评估材料：

- `EVAL/FRAMEWORK_EVAL_D1_SENSOR_FUSION.md`
- `EVAL/FRAMEWORK_EVAL_D2_DATA_ASSOCIATION.md`
- `EVAL/FRAMEWORK_EVAL_D3_ASSIGNMENT.md`
- `EVAL/FRAMEWORK_EVAL_D4_COORDINATION.md`
- `EVAL/FRAMEWORK_EVAL_D5_TERMINAL.md`
- `EVAL/FRAMEWORK_EVAL_D6_EVALUATION.md`
- `EVAL/FRAMEWORK_EVAL_D7_GUIDANCE.md`
- `EVAL/FRAMEWORK_EVAL_SYSTEM_INTEGRATION.md`

## 2. 总体判断

三个 patch 的共同结论是：项目当前轻量主线方向正确，但后续可信 AirSim 多 seed、封闭场地、分布式二级接管和真实视觉链路需要更强的工程化依据。

本轮确认：

1. **当前没有新的运行级 P0 blocker**。现有 D1-D7 模块测试、main runtime tests、AirSim 2v2 SimpleFlight smoke 已能运行。
2. **不要把成熟外部工具本身等同为 P0**。例如 OR-Tools、etcd、ROS 2、MLflow、RTI Connext、Kalibr、Apollo Cyber RT 很有价值，但“立即集成这些完整框架”不是当前 P0。
3. **P0 应限定为最小可信闭环硬化项**：时间/配置/健康/异常、任务 outcome、根因诊断、FDIR-light、质量门控、分配迟滞、二级能力判断、终端重捕获、D7 切换迟滞/LOS 滤波、标准化评估映射。
4. **P1 是三个月内能力增强和标定**：标准对齐报告、OR-Tools 对照、JPDA/MHT 选型、Raft 选举对照、YOLO/MOT 多 seed 校准、IBVS/间歇可见性重捕获、3D True PN/APN 对照。
5. **P2 是较重架构升级或高阶算法**：ROS 2/DDS 生产化、PTP 多节点时间同步、Track-to-Track 融合、跨视角联合优化、多资源协同拦截、完整分区合并、标准 MOT/HOTA/OSPA 适配。
6. **2026-07-09 P1 接口补齐已完成一轮**：main runtime 已补齐 P1 calibration suite/threshold metadata、高度对比和 D6 标准报告 bundle；D1-D7 各模块已补充本模块 P1 metadata、summary、evidence 或 gate 字段；剩余工作从“接口缺口”转为“真实 AirSim 多 seed 标定和长期趋势治理”。

## 3. 分级口径

| 等级 | 含义 | 是否阻塞当前测试 | 是否近期排期 |
|---|---|---:|---:|
| P0 | 当前轻量主线进入可信多 seed/闭环验证前必须具备的最小硬化项 | 否 | 是 |
| P1 | 三个月内增强、标定、对照和报告能力 | 否 | 是 |
| P2 | 六个月左右的架构升级、较重依赖或高阶算法 | 否 | 视资源 |
| 规避/P3 | 前沿但实时性、可解释性或认证风险过高，不进入当前路线 | 否 | 否 |

P0 继续拆分：

| 子级 | 含义 |
|---|---|
| P0-A | 基础设施可信度：时间、配置、健康、异常、任务 outcome、根因和性能 |
| P0-B | 安全门控与闭环稳定性：质量、迟滞、二级能力、重捕获、校准健康、导引切换稳定 |
| P0-C | 场景依赖 P0：仅在继续 5v5/N-v-N、高差、密集交叉、可信二级接管时进入 P0 |

## 4. Patch 新增观点的采纳判断

| Patch 观点 | 本项目采纳等级 | 判断 |
|---|---|---|
| COURAGEOUS / CEN CWA C-UAS 标准化测试 | P0-A 最小映射，P1 完整对齐 | D6 应立即建立指标映射表，但不要求一次性完整复刻标准流程 |
| MDPI 2025 C-UAS 标准化评估综述 | P0-A/P1 | 用于修正 D6 指标定义和报告引用；完整文献综述为 P1 |
| OCEF / MLPerf 式复现纪律 | P0-A 最小字段，P1 场景库 | 固定 seed、版本、evidence path 属 P0；完整基准平台属 P1 |
| PX4 EKF2 FDIR | P0-A 的 FDIR-light，P1/P2 完整移植 | 传感器 health、reject reason、协方差边界是 P0；完整 EKF2 移植不是 P0 |
| MATLAB Sensor Fusion Toolbox 调参逻辑 | P1 | 工程参考价值高，但不是运行依赖 |
| Stone Soup / FilterPy | P1/P2 对照 | 当前自研轻量 EKF/GNN 主线保留，外部库作为 benchmark |
| ByteTrack / YOLOv8 | P1 标定 | D5 已有 adapter；真实 AirSim 多 seed 阈值和失败回退仍是 P1 |
| SORT / Deep SORT | P1/P2 | SORT 可作 fallback 对照；Deep SORT/ReID 更偏 P2 |
| OR-Tools | P1 对照，P2 默认升级 | 当前 Hungarian/SciPy 主线足够；复杂约束和多容量才需要 OR-Tools |
| Event-Driven CBBA / Two-Level CBBA | P1 | 与 D4 分布式降级通信优化相关，但不是当前 P0 |
| etcd / SwarmRaft / Raft 选举 | P1 对照，P2 工程集成 | P0 只需要 lease/epoch/anti-split-brain 合同；完整 etcd 集成不列 P0 |
| DDS QoS / RTI Connext / ROS 2 生产部署 | P2 | 对生产化重要，但当前 Python/AirSim runtime 不应立即重写 |
| PTP / DDS 时间同步 | P2，封闭多节点实测前可升 P0-C | 当前单机 AirSim 只需 episode clock；真实多机硬件时才升级 |
| IBVS / 视觉伺服 / 间歇可见性切换控制 | P1，若做真实视觉接管可升 P0-C | 当前 P0 是 D5 reacquire 和 D7 latch；完整视觉伺服是后续增强 |
| 3D True PN 可捕获性 / ADRC / 协同到达时间 | P1/P2 | D7 已有 3D benchmark；默认控制律不应立即替换 |
| MLflow / W&B / Dashboard | P1/P2 | D6 可先导出标准 CSV/JSON/Markdown；平台化实验管理后置 |
| Docker Compose / Hydra / structlog | P1 | 对工程化有帮助，但当前不构成 P0 blocker |

## 5. P0 缺口确认

P0 是“最小可信闭环硬化项”，不是“把所有成熟外部工具集成进来”。

### 5.1 P0-A 基础设施可信度

| Owner | P0-A 缺口 | Patch 支撑 | 最小验收口径 |
|---|---|---|---|
| Main/System | 统一 episode clock 与时间字段 | Apollo/Cyber RT、DDS 时间同步、OCEF 复现纪律 | 每条 D1-D7 record 能区分 `measurement_timestamp`、`arrival_timestamp`、`processing_timestamp`、`publish_timestamp` 或等价字段 |
| Main/System | 集中 scenario config 与 evidence path | OCEF、Hydra、MLflow | settings、seed、资源/目标数量、检测后端、算法版本写入 D6 metadata |
| Main/System | 模块 health snapshot 与异常 outcome | PX4 FDIR、结构化日志实践 | D1-D7 health、last update age、record count、error state、runtime exception 可写盘 |
| D6 | 系统级 mission outcome | COURAGEOUS、MDPI C-UAS 评估 | 每个 episode 输出 success/partial/failed/aborted、success/failure reason |
| D6 | 根因诊断与 top failure causes | COURAGEOUS、OCEF、MLflow | 报告能归因 tracking、assignment、coverage、terminal gate、guidance、runtime exception |
| D6 | 性能和可复现字段 | OCEF、pytest-benchmark、MLflow | 输出模块耗时、loop latency、record latency、CPU/GPU budget placeholder、eval priority/status/evidence path |
| D6 | 标准化评估映射最小版 | COURAGEOUS、MDPI、OCEF | 增加“本项目指标 -> 标准 C-UAS 指标类别”的 mapping，不要求完整认证 |
| D1 | FDIR-light | PX4 EKF2 | 传感器 health、fault reason、reject count、恢复状态、异常隔离建议 |
| D1 | 协方差上下界与 reason | PX4 EKF2、MATLAB fusion 调参 | 低质量/遮挡/外推时 covariance 不虚假收敛、不无限发散 |
| D1 | 时间戳不确定性 | Apollo/Cyber RT、DDS 时间同步实践 | timing uncertainty 进入 observation/track summary 和 D6 延迟报告 |

### 5.2 P0-B 安全门控与闭环稳定性

| Owner | P0-B 缺口 | Patch 支撑 | 最小验收口径 |
|---|---|---|---|
| D2 | 航迹质量评分 | MATLAB tracking、MHT/JPDA/BP 选型论文 | 每条 track 输出 `track_quality` 和 `association_risk`，供 D3/D5/D6 消费 |
| D2 | 运动一致性约束 | SORT/MATLAB tracking 工程实践 | GNN/Hungarian 代价中有速度方向/短时历史一致性，不替换主关联器 |
| D2 | quality-aware gate baseline | MHT/JPDA/BP track coalescence 分析 | dense/crossing 下门限可随 track quality/density 做轻量调整 |
| D3 | 资源状态细化 | OR-Tools/工业分配实践 | energy、availability、current load、history failure、intercept feasibility 进入 cost metadata |
| D3 | 增强迟滞和 stale rejection | 工业资源调度实践 | min dwell、switch penalty、release condition、stale reason 可解释 |
| D3 | 可解释 threat baseline | Iron Dome 公开威胁评估思路 | TTC、关键区接近、速度、协方差、目标状态进入 threat score baseline |
| D4 | Heartbeat 平滑 | etcd/Raft、DDS QoS | 短时丢包不直接 failed，有 degraded/suspect dwell |
| D4 | Lease/epoch 严格合同 | etcd/Raft、SwarmRaft | 过期或非单调二级 plan 不可执行；active secondary same id/version 不误拒绝 |
| D4 | 二级能力评估 | 分布式边缘融合、SwarmRaft | 区分 visible、registered、takeover_capable，并写入 D6 metadata |
| D4 | 主动降级防抖 | UAV 韧性评估、D4 工程实践 | hard/soft risk、dwell/release、false-trigger candidate 可统计 |
| D5 | 主动重捕获 | 间歇可见性切换控制、Fortem/Skydio 工程经验 | reacquire 不改写 `global_track_id`，基于投影和搜索窗口恢复 |
| D5 | 时序一致性和稳定窗口 | ByteTrack、IBVS、视觉跟踪实践 | bbox/MOT history、candidate margin、stable window 抑制误锁 |
| D5 | 相机校准健康监测 | Kalibr、OpenCV、IBVS | 输出 reprojection error、pose source、calibration health、drift warning |
| D7 | 末端切换迟滞 | 视觉间歇可见性、导引工程实践 | dwell/release/reacquire grace，terminal switch reject reason 可解释 |
| D7 | LOS 角速率滤波 | PN/视觉伺服工程实践 | filtered LOS rate、限幅、outlier reject，近距命令无尖峰 |

### 5.3 P0-C 场景依赖项

| Owner | P0-C 缺口 | 升为 P0 的条件 | 否则等级 |
|---|---|---|---|
| D7 | 3D PN geometry benchmark/log | 继续做 200 m 高差、3D target 或高度差拦截 | P1 |
| D6 | COURAGEOUS 完整流程映射 | 准备封闭场地或外部可审计测试报告 | P1 |
| D4 | 二级接管 anti-split-brain 合同强化 | 多二级节点/网络分区/完全无中心测试 | P1 |
| D5 | 视觉接管前置证据增强 | 要求视觉 PNG 稳定接管率显著提升 | P1 |
| Main/System | 多 seed 标定强制化 | 开始以 AirSim 多 seed 作为主验收口径 | P1 |

## 6. P1 缺口确认

P1 是三个月内能力增强、对照实验、标定和标准化报告。

| Owner | P1 缺口 | Patch 支撑 | 验收口径 |
|---|---|---|---|
| D1 | IMM/CV-CA-CT 多模型滤波 | PX4/Stone Soup/MATLAB | 机动目标 RMSE 下降，同场景 EKF baseline 保留 |
| D1 | 场景自适应协方差 | PX4 FDIR、MATLAB 调参 | 输出 covariance scale reason：遮挡、杂波、距离、来源、延迟 |
| D1 | Track-to-Track 融合原型 | West Point MWI 分布式边缘融合 | 多二级节点输入不重复计数，协方差一致 |
| D2 | JPDA/MHT/BP 选型对照 | IEEE OJSP 2024 track coalescence | dense/crossing 下输出 IDSW、coalescence、latency 对照 |
| D2 | SORT/ByteTrack style fallback | SORT/ByteTrack 工程实践 | GNN 异常或视觉 MOT 场景可回退轻量 baseline |
| D2 | N/M 初始化和协方差一致性检查 | MATLAB/Stone Soup | false track rate、init latency、NIS/NEES 或等价 flag |
| D3 | OR-Tools Min Cost Flow 对照 | OR-Tools patch | 同输入下输出 Hungarian vs min-cost-flow 对照计划 |
| D3 | 增量分配和时间窗口硬约束 | OR-Tools/工业调度实践 | 目标新增/资源失效时 update latency 下降，closed window 不被分配 |
| D3 | 完整动态威胁评估 | Iron Dome 公开思路 | threat score 可解释并进入 D6 scenario report |
| D4 | Raft/SwarmRaft leader election 对照 | etcd、SwarmRaft | 二级选举日志可复现，不绕过 D3/D4/D7 执行合同 |
| D4 | Event-Driven CBBA 通信优化 | arXiv 2025 Event-Driven CBBA | 共识消息量下降，冲突率和完成率可统计 |
| D4 | 网络分区检测与恢复韧性指标 | UAV resilience metric | 输出 partition state、merge audit、resilience score |
| D4 | DDS QoS 通信策略仿真 | ROS 2 DDS QoS / RTI | 丢包、stale link、priority delivery 进入 D6 指标 |
| D5 | YOLOv8 + ByteTrack/BoT-SORT 多 seed 标定 | YOLO/ByteTrack patch | 目标尺度、FOV、置信度、tracker backend、CPU/GPU budget 形成报告 |
| D5 | IBVS/间歇可见性重捕获对照 | IEEE TIE/TAES/arXiv | lost/reacquire 时间下降，误锁仍为 0 |
| D5 | 多模态友方识别 replay adapter | OpenDroneID/MAVLink/DDS/AprilTag 规划 | 至少一个 replay path 输出 verified/stale/unverified |
| D5 | 完整相机在线标定/畸变校正 | Kalibr/OpenCV | 标定样本中重投影误差下降，distortion 进入 projection |
| D6 | COURAGEOUS/MDPI/OCEF 标准化报告 | WebSearch patch 最大收获 | D6 报告增加标准指标映射、测试阶段、复现纪律字段 |
| D6 | 基线对比和统计显著性 | MLflow/OCEF/pytest-benchmark | baseline vs enhanced、多 seed 均值/方差/置信区间 |
| D6 | 场景库管理和 CI 回归摘要 | OCEF、MLflow、CI 工程实践 | scenario tags、difficulty、expected failure modes、test matrix |
| D7 | 3D True PN/APN/ADRC 对照 | Aerospace S&T、IECON、PX4 L1 | 作为 benchmark，不替换默认 PN/PNG，不绕过 D3/D4/D5 gate |
| D7 | 预测拦截点和动力学补偿 | 导引工程实践 | predicted intercept point、命令饱和、响应延迟写入 guidance log |
| Main/System | ROS 2 replay 原型 | ROS 2/RTI/DDS patch | 离线 replay 节点原型，不重写当前 Python runtime |
| Main/System | 结构化日志和配置治理 | structlog/Hydra | 当前 JSONL 记录继续保留，配置版本和 schema 明确 |
| Main/System | Docker Compose 开发部署 | Docker Compose patch | 用于本地多进程实验，不作为生产部署 |

## 7. P2 缺口确认

P2 是较重外部依赖、生产化架构、高阶算法和长期对照。P2 不应抢在 P0/P1 前改主线。

| Owner | P2 缺口 | Patch 支撑 | 验收口径 |
|---|---|---|---|
| D1 | UKF/非线性强量测后端 | Stone Soup/FilterPy/MATLAB | 与 EKF 同场景对照，收益明确后再进入主线 |
| D1 | 主动传感器管理 | 多传感器 C-UAS 设计指南 | coverage 或不确定性有量化改善 |
| D2 | 有界 MHT 工程实现 | Stone Soup/MHT 选型论文 | N-scan pruning、延迟、内存可控 |
| D2 | 标准 MOT/HOTA/IDF1 adapter | TrackEval/py-motmetrics 规划 | 离线 truth label 数据稳定后接入 |
| D3 | 多资源协同/备份资源/预测性滚动分配 | OR-Tools/防空资源分配实践 | D6 能评估协同收益、备份触发和冲突风险 |
| D4 | etcd/Consul/完整 Raft 集成 | etcd/SwarmRaft | 多节点真实通信条件满足后再做，不替代当前 lease 合同 |
| D4 | 版本向量、分区合并、完整 recovery audit | Raft/分区恢复实践 | 网络分区恢复后冲突可解释 |
| D5 | Deep SORT/ReID 外观特征 | SORT/Deep SORT/视觉工程实践 | 遮挡恢复和密集场景 ID continuity 提升 |
| D5 | 跨视角联合优化 | 多相机视觉实践 | 多相机外参、同步和稳定 bbox 足够后再做 |
| D5 | 视觉伺服控制闭环 | IBVS/Skydio/Fortem | 必须保持 D3/D4/D5/D7 gate，不让视觉节点改写任务绑定 |
| D6 | MLflow/W&B 平台化实验管理 | MLflow/W&B patch | 先保证本地 CSV/JSON/Markdown，再接平台 |
| D6 | 对抗性评估和场景覆盖率矩阵 | COURAGEOUS/OCEF | 场景库标签化后实施 |
| D7 | 协同到达时间制导 | Cooperative Impact Time Guidance | 依赖 D3 多资源协同和 D6 成功指标 |
| D7 | 默认 3D 控制律/平台动力学/FRPN/ADRC 主线升级 | 3D True PN/ADRC | benchmark 数据证明优于 PN 后再考虑替换 |
| Main/System | ROS 2 + RTI Connext 生产硬化 | RTI/ROS2/DDS patch | 不在当前 Python/AirSim 阶段重写；生产化时推进 |
| Main/System | PTP 多节点时间同步 | DDS/PTP patch | 进入真实多机硬件前推进 |
| Main/System | Dashboard/Kubernetes/KubeEdge 自动化部署 | 工程实践 patch | 运行指标稳定后再平台化 |

## 8. 明确规避或降为 P3 的方向

这些方向不进入当前 P0/P1/P2 默认实施，除非后续作为独立研究专项。

| 方向 | 涉及模块 | 规避原因 |
|---|---|---|
| LLM 辅助实时传感器融合 | D1 | 延迟高、不可解释、实时闭环风险大 |
| 区块链集群协调 | D4 | 延迟和计算开销不适合拦截实时性 |
| DMPC/重型分布式 MPC 作为默认降级控制 | D4/D7 | 计算量大、标定复杂，先保留规则/PN 主线 |
| 深度强化学习制导律 | D7 | 黑盒、难认证、泛化风险高 |
| 端到端深度学习任务分配或身份绑定 | D2/D3/D5 | 容易破坏可解释性和 `global_track_id` 合同 |
| BFT 共识 | D4 | 当前二级/分布式仿真过重，Raft/lease 已够基线 |
| 云原生/Kubernetes 生产部署 | Main/System | 当前目标是 AirSim/封闭场地可信验证，不是大规模服务平台 |

## 9. 与当前项目状态的关系

截至本文件更新时，项目已完成一批 P0 最小实现：

- main runtime：episode clock/config/module health/runtime exception outcome。
- D1：sensor health、covariance floor/ceiling、timestamp uncertainty。
- D2：track quality、motion consistency、quality-aware gate baseline。
- D3：资源状态细化、迟滞增强、threat score baseline。
- D4：heartbeat smoothing、lease/epoch strictness、secondary capability score、主动降级防抖。
- D5：active reacquire、temporal consistency、calibration health metadata。
- D6：mission outcome、root cause、performance metrics、eval tracking。
- D7：terminal latch、LOS rate filtering、3D PN benchmark/log。

同时，2026-07-09 已完成一批 P1 接口补齐：

- main runtime：`--p1-calibration-sweep` 输出 `calibration_suite=cv_5v5_d4d5_secondary_coverage`、suite version、threshold version、二级高度/FOV/数量/站距、expected state fields 和 50m/200m 高度对比；自动生成 D6 `d6_airsim_calibration` CSV/JSON/Markdown bundle。
- main runtime：修复 secondary takeover plan 在连续 replan 后 `owner_node_id` 回退为 `d3_central` 的问题；若 D4 legacy metadata 指向中心，main 会按 D4 target node、历史 secondary owner 或当前 frame 中的二级节点名保持真实 secondary owner。
- D1：dry-run/replay schema/version/metadata 检查、latency/OOSM audit 和区域质量摘要已补齐。
- D2：association risk threshold version、gate pass/reject、risk summary 和 threshold sensitivity 已补齐。
- D3：`AssignmentEvidenceExport`、current cost matrix、per-edge breakdown、hard rejected edges、stale reason、secondary fields 和 hard time-window closed-edge baseline 已补齐。
- D4：`secondary_capability_class` / `secondary_readiness_class` 已补齐；二级节点必须达到 `takeover_ready` 才能作为接管依据，visible-only / registration-usable 只能作为辅助或标定证据。
- D5：`detect_registration_outcome`、reject reasons、measurement age、projection/covariance、`projection_invalid` 独立原因和 YOLO/MOT metadata 已补齐；在线 D5 仍不得使用 AirSim truth ID 或改写 `global_track_id`。
- D6：AirSim calibration records/summary/Markdown 保留 scenario/standard mapping/evidence/trend/height bucket/actual scale；Markdown 增加 50m vs 200m coverage、coverage funnel、baseline vs enhanced、stable registration、not registered、active degradation、D7 reject 等口径。
- D7：runtime/comparison/replay/calibration 输出 terminal range、closing speed、bbox/LOS/maneuver gate、D4 block reason、D5/D3 consistency、secondary capability/readiness、threshold advisory version 和 visual PNG switch count；PNG 核心控制律未改。

本轮 smoke 验证：

- 输出目录：`research_modules/airsim_runtime/outputs/p1_gap_fix_smoke_20260709/`
- 组合：50m/200m 二级高度、3 个机动高空二级侦察节点、110 deg FOV、seed=1、三类 case。
- 结果：`row_count=6`，`projection_valid_rate=1.0`，D6 标准报告 bundle 已生成。
- 解释：50m bbox 均值约 19055 px^2，200m bbox 均值约 1147 px^2；200m 网络同帧全覆盖仍为 0.0，说明剩余 P1 重点是二级站位/扫描/coverage 和多 seed 阈值标定，而不是绕过 D3/D4/D5 gate。

因此本文件后续使用方式是：

1. **已完成的 P0**：保持回归，不重复列为新 blocker。
2. **已完成的 P1 接口补齐**：保持回归，后续不要重复列为“缺字段/缺接口”。
3. **剩余 P1 标定项**：真实 AirSim 多 seed、二级网络全目标覆盖、YOLO/MOT 阈值、D4/D5/D7 状态迁移、D6 长期趋势和 review label。
4. **P2**：作为后续子智能体任务来源，由 main 分发给对应 D-agent 后再同步模块 GAP/PLAN。

## 10. 建议执行顺序

### 第一批：保持 P0/P1 接口回归

1. D6/main：保持 `COURAGEOUS/MDPI/OCEF -> 当前 EpisodeMetrics` 最小映射、`standard_metric_family`、`evidence_path` 和 `scenario_version` 不退化。
2. main/runtime：保持 P1 calibration sweep suite/version/threshold、高度对比、D6 bundle、secondary owner 保持和不保存 PNG 默认规则。
3. D1-D7：保持各自 P1 metadata/summary/evidence/gate 字段不退化，并由对应 subagent 同步 GAP/PLAN。

### 第二批：跑多 seed 校准

1. AirSim 2v2 intercept 多 seed：统计 terminal latch、LOS filter、PN/PNG gate、visual PNG switch、D7 reject reason。
2. D4/D5 5v5 stress 多 seed：统计 secondary visible/registered/takeover capable、single-camera full view、network union coverage、not-registered 和 cross-view association。
3. CV 5v5：统计 D1/D2/D3/D5 的质量门控、assignment stability、ID switch、terminal association 和 active degradation necessity。

### 第三批：做 P1 对照

1. D3 OR-Tools min-cost-flow 对照。
2. D2 JPDA/MHT/SORT/ByteTrack-style 对照。
3. D4 Raft/SwarmRaft election replay 对照。
4. D5 IBVS/间歇可见性重捕获对照。
5. D7 3D True PN/APN/ADRC benchmark。

## 11. 最终确认表

| 模块 | 当前运行级 P0 blocker | 仍需保持/补充的 P0 | P1 主线 | P2 主线 |
|---|---:|---|---|---|
| D1 | 无 | FDIR-light、协方差界、时间戳不确定性、latency/OOSM/region summary 保持回归 | IMM、自适应协方差、T2T 原型、更多真实 Blocks/CV fixture | UKF、主动传感器管理 |
| D2 | 无 | 航迹质量、运动一致性、quality-aware gate、risk threshold summary 保持回归 | JPDA/MHT/BP 选型、SORT/ByteTrack fallback、真实 5v5 replay 阈值校准 | 有界 MHT、标准 MOT adapter |
| D3 | 无 | 资源状态、迟滞、threat baseline、assignment evidence export、secondary DTO 保持回归 | OR-Tools 对照、增量分配、硬时间窗多场景校准、D5 feedback 权重标定 | 多资源协同、备份资源、预测性滚动 |
| D4 | 无 | heartbeat、lease、二级能力、防抖、secondary readiness/capability class 保持回归 | Raft/SwarmRaft、Event-CBBA、分区检测、二级覆盖/接管必要性多 seed 标定 | etcd 集成、版本向量、分区合并 |
| D5 | 无 | 重捕获、时序一致性、校准健康、detect registration outcome、truth ID 在线隔离保持回归 | YOLO/MOT 标定、IBVS、间歇可见性、多模态身份 replay、跨视角注册阈值 | ReID、联合优化、视觉伺服闭环 |
| D6 | 无 | mission outcome、根因、性能、标准映射最小版、P1 calibration bundle 保持回归 | COURAGEOUS/OCEF 完整报告、A/B 显著性、场景库、多 seed 长期趋势 | MLflow/W&B、对抗评估、标准 MOT/OSPA |
| D7 | 无 | latch、LOS 滤波、3D benchmark、P1 switch/gate calibration fields 保持回归 | 3D True PN、APN、ADRC、预测点、动力学补偿、真实 PN/Pure Pursuit/PNG 对照 | 协同到达时间、默认 3D/FRPN 升级 |
| Main/System | 无 | 时间、配置、健康、异常恢复、P1 calibration sweep、secondary owner 保持回归 | ROS2 replay 原型、结构化日志、Docker Compose、真实 AirSim 多 seed 标定 | ROS2/RTI 生产硬化、PTP、Dashboard/KubeEdge |

结论：三个 patch 强化了“标准化评估 + 成熟工程栈 + 明确规避前沿黑盒方法”的方向，但没有推翻当前轻量主线。2026-07-09 已完成 D6/main 标准化映射最小版与 P1 calibration/report 接口的基础闭合；下一步最急的是真实 AirSim 多 seed 标定和二级网络覆盖/跨视角注册稳定性，而不是引入重型外部框架替换主线。
