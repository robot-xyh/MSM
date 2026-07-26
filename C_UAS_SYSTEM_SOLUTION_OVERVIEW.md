# 反无人机多目标拦截科研仿真体系总纲

## 0. 文档定位与边界

本文是 `/home/linux/Documents/MSM` 仓库的主智能体总纲文件，用于把 D1-D7 七个子模块、现有代码、仿真结果、算法路线和后续集成计划整理成一套完整的反无人机多目标拦截科研仿真解决方案。

本项目的研究对象是“多目标 vs 多目标”场景下的体系工程链路：复合探测、航迹融合、目标关联、资源分配、中心失效降级、末端视觉配准和系统级评估。当前实现服务于离线科研仿真、日志回放、算法对比和 AirSim Blocks 验证接入。

当前场景想定包含中心 C2、高空侦察二级节点、拦截资源节点和入侵目标。二级节点可以是系留高空平台，也可以是随任务机动出动的高空侦察无人机；当前 AirSim P1 校准重点采用机动高空侦察相机节点。中心节点负责全局态势与主分配；二级侦察无人机健康时提供高视角观测、视频/图像 cue 和局部区域态势摘要，中心节点失效时优先作为二级节点接管覆盖区域内的协调；二级节点不可用后才进入完全无中心的资源间协商。拦截无人机之间、拦截无人机与中心/二级节点之间、二级节点与中心之间均允许交换仿真数据，视频或图像 cue 主要由二级节点定向提供给小范围执行资源。

严格边界：

- 不实现真实飞控接口。
- 不实现硬件驱动。
- 不实现真实无线通信链路、频点规划、抗干扰或加密绕过；本文中的通信仅指仿真消息、状态摘要和图像 cue 的数据合同。
- 不实现火控参数、毁伤模型或自动处置逻辑。
- 不绕过人工授权或安全审查。
- 不把未知目标自动判定为敌对目标。

因此，本文中的“拦截”“分配”“末端锁定”等术语均指离线仿真中的任务建模、目标配准和评估状态，不代表真实系统的自动处置能力。

## 1. 项目目标

项目要解决的问题不是单个算法，而是一个完整链路：

```text
多源探测
  -> 多目标全局航迹
  -> 稳定 global_track_id
  -> 多资源目标分配
  -> 中心失效降级
  -> 末端视觉配准与身份确认
  -> 批量评估与指标闭环
```

核心目标：

1. 在异步、异构、多噪声传感器下形成带协方差的 `GlobalTrack`。
2. 在 5v5 乃至更多目标场景下维持目标身份连续性，显式统计 `id_switch_count`。
3. 在中心节点存在时用成熟的集中式优化方法形成版本化 `AssignmentPlan`。
4. 在中心节点失效时优先降级到二级侦察/备份节点；在中心在线但分配计划因定位不确定、动态延迟或末端视觉不一致而不可靠时，允许触发主动降级仲裁；二级节点失效后才进入完全无中心协商。
5. 在末端视场内同时出现多个目标、友方资源和未知飞行物时，避免“最近目标就是分配目标”的错误绑定。
6. 用系统级指标评估探测、跟踪、分配、降级、末端配准和安全约束，而不是只看命中率。

## 1.1 当前代码落地状态

当前仓库已经形成 D1-D7 七个子模块、离线集成仿真入口和真实 AirSim Blocks runtime：

| 层级 | 目录 | 当前实现 |
|---|---|---|
| D1 | `research_modules/d1_sensor_fusion/` | 延迟雷达、声学方位、EO 像素观测的 EKF 融合与协方差航迹输出 |
| D2 | `research_modules/d2_data_association/` | GNN/Hungarian 主线，JPDA/MHT 对照接口，ID Switch 与连续性统计 |
| D3 | `research_modules/d3_assignment_planner/` | Hungarian 滚动分配、版本化 `AssignmentPlan`、迟滞重分配 |
| D4 | `research_modules/d4_distributed_fallback/` | 被动失效接管、二级侦察节点优先、主动降级仲裁、CBBA 保底 |
| D5 | `research_modules/d5_terminal_association/` | 全局航迹投影、局部视觉配准、友方正向身份确认、保守 `hold/reacquire` |
| D6 | `research_modules/d6_evaluation_metrics/` | 全链路日志、EpisodeMetrics、CSV/Markdown/PNG 报告 |
| D7 | `research_modules/d7_proportional_guidance/` | 经典二维比例导引，覆盖雷达航迹中段 PN 与视觉 LOS 末端 PN |
| Main | `research_modules/integrated_simulation/` | 5v5 离线质点主程序，串联 D1-D7 并输出统一 JSONL、guidance CSV/JSON 和批量报告 |
| AirSim Runtime | `research_modules/airsim_runtime/` | Blocks 启停、settings 生成、reset-separated episodes、SimpleFlight 控制、ComputerVision/actor target replay、D1-D7 main episode bus |

主程序可运行：

```bash
python3 research_modules/integrated_simulation/run_episode.py --scenario nominal_5v5
python3 research_modules/integrated_simulation/run_batch.py
python3 research_modules/integrated_simulation/generate_global_process_gif.py
python3 research_modules/run_all_tests.py
python3 research_modules/run_smoke_simulations.py
```

集成场景覆盖正常 5v5、中心节点被动失效、二级节点失效后完全分布式、末端视觉不一致触发主动降级、友方重叠触发保持审查。输出位于 `research_modules/integrated_simulation/outputs/`，其中包含每个 episode 的 `episode_log.jsonl`、`metrics.json`、`active_degradation_decisions.csv/json`、Markdown 报告和 D6 图表。

D7 接入后，D3 初始分配和 D4 二次分配都会触发离线二维 PN 子过程：先使用全局航迹估计执行 `radar_midcourse`，进入终端距离门限后切换到 `vision_terminal`，并输出 `guidance_records.csv` 与 `guidance_summaries.json`。这些记录用于闭环解释和可视化，不代表真实飞控或硬件接口。

AirSim runtime 已经从“规划接入”推进到可运行的 Blocks 验证路径。当前 main 负责一次启动 Blocks、按 episode reset 场景、采集相机/检测/actor pose/SimpleFlight 控制日志，并把 D1-D7 的 DTO、summary 和 record 接入统一 `main_episode_bus`。最新 P1 D4/D5 registration calibration v2 使用 5v5、3 个机动高空二级侦察节点、200 m 高差、110 deg FOV、1920x1080 和 AirSim `simGetDetections`：`projection_valid_rate=1.0`，`geometry_gate_pass_rate≈0.474`，稳定跨视角注册约 51/55/53，`secondary_network_mean_coverage_ratio≈0.771`，`secondary_network_joint_full_view_frame_rate` 均值约 0.048、最佳约 0.143，cross-view association 为 4/4/5。当前瓶颈已经从相机姿态/投影无效转为覆盖不完整和 `not_all_targets_visible` / `network_union_incomplete`；二级 detect 可以形成候选注册，但仍不能绕过 D3/D4/D5 的全局绑定、仲裁和视觉 PNG gate。

## 1.2 200 对 200 三维学习增强状态

规模化主线在独立功能分支中保留现有 2v2、5v5、M5N2 和 AirSim 基线，新增三维质点世界、
统一 episode 总线、匿名视觉投影、稀疏跨视角图和学习辅助接口。规则基线 R0 使用 900 个
正式单元覆盖 9 类场景、5 档规模和 20 个保留 seed。修复后 clean source 已完成
135/900 单元；磁盘可用空间约 21 GiB，接近 20 GiB 安全下限，因此后续分片等待证据迁移、
扩容或明确清理授权。已有三处正式证据保持不动，不能跨提交拼接。

学习增强保持确定性安全外壳。D3 学习模型只修正规则代价，D4 学习模型只给出区域资源建议，
D5 图模型只输出跨视角同目标概率，主动视觉模型只给出观察目标和云台建议。容量、不可达边、
身份所有权、计划版本、联盟确认、友方冲突和导引许可仍由规则合同判定。D3、D4、D5 图模型
和 D5 主动视觉现有 bundle 均为 development/shadow，G1、A1、A2、A3、C1、F1 全部
失败关闭，正式学习 episode 为 0。

当前已关闭三类权限漏洞：旧 D3/D4 bundle 不能凭缺省字段进入 assist；D5 development
scorer 可读不等于 G1 获准；调用方不能用裸报告或手工清单生成可执行的 G1/A3 bundle。
进一步复核后，D3 已关闭 v3 调用方构造 qualified admission 的自我晋级入口；D4 没有
发现新的自我晋级 P0。D6 已实现 D5 G1 外部预准入审计，D5 已实现逐文件校验和原子发布的
G1 evidence assembler。正向 fixture 可以生成并加载 v4，只证明准入合同可执行。

当前 D5 `99fa4428...d4cd` 模型的 post-assembler 审计仍为 `fail_closed`。困难遮挡重现
代理的 cluster/edge F1 约为 `0.572845/0.563264`，低于 `0.9`；单特征最佳方向曲线下面积
约为 `0.997340`，超过 `0.98` 上限；旧证据还缺当前 assembler 来源并与当前 bundle
实现不一致。实际装配器退出码为 2，没有生成 admitted bundle。D3、D4 和 A3 专用
assembler 仍未实现。下一步先形成绑定当前代码、未见 seed、实际采用、物理结果和成对
非退化的新证据。获准模型完成正式作用域后，再由 D6 审计逐 cell 实际采用、物理结果和
同键 R0 非退化。D6 审计只评价证据，不授予模型晋级或控制权限。

## 2. 总体架构

系统采用“复合探测网 + 中心化主控 + 二级区域节点 + 分布式保底 + 末端保守配准 + 全链路评估”的架构。

```text
┌──────────────────────────────────────────────────────────────┐
│ 复合探测网                                                     │
│ 雷达 / 声学 / 光电 / 高空系留侦察节点 / AirSim 真值回放           │
└───────────────────────┬──────────────────────────────────────┘
                        │ SensorObservation
                        v
┌──────────────────────────────────────────────────────────────┐
│ D1 多传感器融合与目标配准                                      │
│ 时间对齐、坐标转换、协方差建模、EKF/UKF 接口、延迟补偿            │
└───────────────────────┬──────────────────────────────────────┘
                        │ GlobalTrack(position, velocity, covariance)
                        v
┌──────────────────────────────────────────────────────────────┐
│ D2 多目标跟踪与数据关联                                        │
│ GNN/Hungarian、JPDA/MHT 预留、航迹生命周期、ID Switch 统计        │
└───────────────────────┬──────────────────────────────────────┘
                        │ stable global_track_id
                        v
┌──────────────────────────────────────────────────────────────┐
│ D3 集中式资源-目标分配                                         │
│ Hungarian/LAP、最小费用流预留、滚动重分配、迟滞、版本管理          │
└───────────────┬───────────────────────────────┬──────────────┘
                │ AssignmentPlan                 │ Degraded baseline
                v                                v
┌───────────────────────────────┐     ┌─────────────────────────┐
│ D5 末端视觉配准与身份认证       │     │ D4 分布式协同与降级接管   │
│ 投影门控、MOT、正向身份确认      │     │ 被动降级、主动仲裁、二级节点、CBBA │
└───────────────┬───────────────┘     └─────────────┬───────────┘
                │ TerminalAssociation                │ Event/Plan logs
                └──────────────────────┬─────────────┘
                                       v
┌──────────────────────────────────────────────────────────────┐
│ D6 系统级评估指标体系                                          │
│ 检测、跟踪、分配、降级、末端、安全指标，批量报告和曲线             │
└──────────────────────────────────────────────────────────────┘
```

架构原则：

- 正常状态以中心节点维护全局态势和主分配计划。
- 中心节点失效后，触发 `passive_failover`，优先由高空系留侦察无人机或地面备份节点作为二级区域节点接管局部协调。
- 中心节点仍在线但 D1/D2/D3/D5 证据显示中心计划不可靠时，触发 `active_degradation` 仲裁，判断是继续中心计划、中心重分配、请求二级辅助、降到二级节点，还是进入分布式协商。
- 二级节点失效或不可用后，才进入完全无中心 CBBA/拍卖式保底协商。
- 末端相机只做配准和身份判断，不改写全局航迹，不自行换绑 `global_track_id`。
- 所有模块都输出日志，D6 负责统一评估和可复现实验统计。

## 3. 三层防御圈与三类节点

### 3.1 三层防御圈抽象

本项目不绑定真实部署距离，采用功能分层描述防御流程：

| 防御圈 | 核心任务 | 主模块 | 典型状态 |
|---|---|---|---|
| 外层预警圈 | 发现、粗定位、初始航迹生成 | D1 | `coarse_track` |
| 中层交接圈 | 稳定航迹、目标关联、资源分配、降级接管 | D2/D3/D4 | `confirmed`, `engageable`, `AssignmentPlan` |
| 末端确认圈 | 相机配准、身份正向确认、歧义保持 | D5 | `locked`, `ambiguous`, `hold`, `reacquire` |

外层关注“是否存在可疑目标及大致在哪里”；中层关注“多个目标分别是谁、由哪些资源跟踪/处理”；末端关注“当前相机视场里的哪个局部目标才是中心分配的那个全局目标”。

### 3.2 节点类型

| 节点 | 作用 | 当前建模 |
|---|---|---|
| 中心 C2 节点 | 维护全局态势、计划版本和主分配 | D3 正常工作模式 |
| 二级侦察/备份节点 | 中心失效后的区域协调者；健康时提供区域观测和图像 cue | D4 `NodeRole.SECONDARY_RECON`, `coordinator_only`, `coverage_cell` |
| 执行资源节点 | 接收分配计划，产生本地视觉配准结果和资源状态 | D3 `ResourceState`, D5 `Assignment.resource_id` |

二级节点是本阶段新增的关键假设。它既不是普通执行资源，也不是完全中心节点；它的职责是区域态势摘要、局部计划连续性和对 D5 的辅助图像 cue。

## 4. 端到端工作流

### 4.1 正常中心化流程

1. 雷达、声学和光电传感器产生异步观测。
2. D1 按 `measurement_timestamp` 回溯更新航迹，再按 `arrival_timestamp` 发布时刻前向补偿。
3. D1 输出带协方差的 NED 坐标 `GlobalTrack`。
4. D2 对观测和航迹进行门控、GNN/Hungarian 关联和生命周期更新。
5. D2 维持稳定 `global_track_id`，将 `tentative/confirmed/engageable/lost/dropped` 状态输出给下游。
6. D3 读取 `GlobalTrack[]` 和 `ResourceState[]`，构建代价矩阵，生成版本化 `AssignmentPlan`。
7. D5 对每个资源本地相机视场进行投影配准，输出终端状态。
8. D6 记录全链路日志并生成指标。

### 4.2 被动降级流程：中心或二级节点失效

1. D4 `C2Health` 监控 heartbeat、航迹更新、计划更新和 peer vote。
2. 进入 `suspect/failed` 后，D4 按优先级选择接管方。
3. 若存在地面备份或二级侦察节点，则进入 `coordination_mode="secondary_node"`。
4. 二级节点维护局部计划版本，并可向局部资源提供 `ReconImageCue`。
5. 若二级节点不可用，则资源节点交换 `TrackSummary` 和 `ResourceSummary`，运行 CBBA/拍卖式协商。
6. 中心恢复后不立即夺权，需要双轨合并、人机确认和冲突审计。

### 4.3 主动降级流程：中心在线但计划不再可靠

主动降级不是节点被摧毁后的接管，而是“中心计划仍存在，但局部证据不支持继续执行”的一致性仲裁。D4 汇总四类信号：

| 来源 | 摘要 | 典型异常 |
|---|---|---|
| D1 | `TrackUncertaintySummary` | 位置协方差增大、测量延迟变长、连续外推过长、航迹等级回退 |
| D2 | `AssociationRiskSummary` | 关联 ambiguity 升高、ID Switch 增长、重复航迹、连续性下降 |
| D3 | `AssignmentValiditySummary` | plan stale、版本非 current、cost margin 过低、接近窗口失效 |
| D5 | `TerminalAssociationSummary` | 多帧 `ambiguous/hold/reacquire`、视觉候选与 assigned id 长期不一致、友方冲突 |

主动仲裁规则基线：

1. D5 `locked`，且资源、全局 ID、版本均一致，D1/D2/D3 风险低：继续中心计划。
2. D1/D2 风险升高，但 D5 仍一致：请求二级节点辅助观测或 cue，不直接完全分布式。
3. D3 计划过期、成本恶化或版本失效，但 D5 仍一致：优先请求中心滚动重分配。
4. D5 多帧不一致、`reacquire` 或本地最佳视觉候选长期不支持当前分配：进入 D4 主动仲裁。
5. 二级节点健康且覆盖该 `coverage_cell`：主动降级到二级节点区域协调。
6. 二级节点不可用或局部分区：进入完全分布式 CBBA/拍卖式协商。
7. 已验证友方冲突：输出 `hold_for_review`，不自动换绑。

D4 当前新增 `ActiveDegradationArbiter` 作为规则基线，输出：

```text
continue_center
request_center_replan
request_secondary_assist
degrade_to_secondary
degrade_to_distributed
hold_for_review
```

### 4.4 末端多目标视场流程

末端阶段的难点是：视场内最近目标不一定是分配目标，局部 MOT 的 ID 也不能替代全局 ID。

D5 的保守流程：

1. 读取当前资源的 `Assignment.assigned_global_track_id`。
2. 检查 `assignment_version`、`track_version` 和授权状态。
3. 将该 `GlobalTrack` 预测到相机时间戳。
4. 通过相机内外参投影到图像平面，传播像素协方差。
5. 与 `LocalVisualTrack[]` 做几何门控和代价匹配。
6. 合并身份声明和二级侦察 `ReconImageCue`。
7. 仅在候选唯一、代价足够低、间隔足够大、无友方冲突、MOT 质量足够时输出 `locked`。
8. 否则输出 `ambiguous/hold/reacquire`，等待继续观测或上级辅助。

## 5. 统一数据合同

### 5.1 核心对象

| 对象 | 来源 | 关键字段 | 下游用途 |
|---|---|---|---|
| `SensorObservation` | D1 输入 | `sensor_id`, `measurement`, `covariance`, `measurement_timestamp`, `arrival_timestamp`, `frame_id`, `classification_hint`, `confidence` | 统一异构观测 |
| `GlobalTrack` | D1/D2 | `global_track_id`, `state`, `covariance`, `valid_at`, `published_at`, `track_state`, `confidence` | 全局态势、分配、终端投影 |
| `ResourceState` / `ResourceSummary` | D3/D4 | 可用性、位置、能力、当前任务、`node_role`, `coverage_cell` | 分配与降级接管 |
| `AssignmentPlan` | D3/D4 | `plan_id`, `version`, `assignments`, `costs`, `human_authorization_state` | 任务分配与版本校验 |
| `TrackUncertaintySummary` | D1 -> D4 | 位置标准差、协方差迹、量测年龄、覆盖小区 | 主动降级定位质量输入 |
| `AssociationRiskSummary` | D2 -> D4 | ambiguity、IDSW、重复航迹、连续性 | 主动降级关联风险输入 |
| `AssignmentValiditySummary` | D3 -> D4 | plan 版本、新鲜度、cost margin、资源匹配 | 主动降级分配有效性输入 |
| `TerminalAssociationSummary` | D5 -> D4 | 末端状态、置信度、歧义度、连续不一致帧数、友方冲突 | 主动降级末端一致性输入 |
| `ReconImageCue` | D4 二级节点 | `producer_node_id`, `image_frame_id`, `global_track_id`, `center_px`, `bbox`, `confidence`, `scoped_resource_ids` | D5 辅助候选排序 |
| `TerminalAssociation` | D5 | `assigned_global_track_id`, `local_track_id`, `decision_state`, `association_confidence`, `ambiguity_score` | 终端配准评估 |
| `IdentityClaim` | D5 | `claim_type`, `auth_state`, `platform_id`, `timestamp` | 友方/合作身份正向确认 |
| `EpisodeMetrics` | D6 | 探测、跟踪、分配、降级、末端、安全指标 | 批量评估与报告 |

### 5.2 强制语义

1. 所有观测同时携带 `measurement_timestamp` 和 `arrival_timestamp`。
2. D1/D2 用 `measurement_timestamp` 做滤波和关联，用 `arrival_timestamp` 做延迟统计和回放顺序。
3. 融合工作空间采用本地 NED；WGS84、ENU、sensor frame、pixel frame 必须转换后再进入统一链路。
4. 任何航迹和观测都必须携带协方差或可解释的不确定性，不把传感器位置均值当真值。
5. `global_track_id` 由全局航迹链路维护，D3/D4/D5/D6 不得局部重写。
6. `AssignmentPlan` 必须版本化；D3 拒绝 stale plan，D5 对版本不匹配输出 `hold`。
7. 未知身份不等于敌对身份；合作身份只能通过正向认证确认。

## 6. D1 多传感器融合与目标配准

### 6.1 模块目标

D1 解决“不同传感器、不同时间、不同坐标系、不同信息量的观测如何融合为统一全局航迹”的问题。输入包括雷达三维或球坐标观测、声学粗方位和光电像素框，输出是带 6D 状态和 6x6 协方差的 `GlobalTrack`。

### 6.2 状态模型

状态向量：

```text
x = [px, py, pz, vx, vy, vz]^T
```

工作坐标系为 NED。默认常速度模型：

```text
x_k = F(dt) x_{k-1} + w
P_k = F P_{k-1} F^T + Q
```

其中 `P` 是协方差，`Q` 是过程噪声。当前代码以 EKF 为默认实现，并保留 UKF/IMM 作为未来扩展接口。

### 6.3 传感器模型

雷达：

- 可建模为距离、方位、俯仰或三维位置观测。
- 误差随距离增大，远距离协方差更大。
- 雷达观测适合作为全局航迹骨架，但不能当作真值。

声学：

- 主要提供粗方位、声纹和类别提示。
- 不适合作为单独精确定位源。
- 在低空、遮挡或雷达/光电不稳定时提供辅助证据。

光电 EO：

- 观测通常是像素框或目标中心点。
- 需要相机内参、外参和投影模型。
- 可在末端或交接阶段提供类别确认和视线方向约束。

### 6.4 延迟与 OOSM

D1 明确区分：

- `measurement_timestamp`：传感器实际测量目标的时间。
- `arrival_timestamp`：观测到达融合节点或回放管线的时间。

处理逻辑：

1. 按量测时间找到航迹历史状态。
2. 在量测时间完成 EKF 更新。
3. 将更新后的状态按运动模型前向预测到发布时刻。
4. 用延迟统计评估补偿效果。

这避免了“把迟到观测当成当前观测”导致的系统性位置偏差。

### 6.5 航迹分级

D1 输出的航迹按质量分级：

| 等级 | 含义 | 典型用途 |
|---|---|---|
| `coarse_track` | 初始或不确定航迹，协方差较大 | 外层预警、继续观测 |
| `stable_track` | 航迹连续、协方差收敛 | D2 关联和 D3 初步分配 |
| `handover_track` | 精度与置信度满足交接需求 | 中层交接和 D5 投影准备 |

### 6.6 当前实现

主要文件：

- `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/types.py`
- `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/observations.py`
- `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/ekf.py`
- `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/fusion.py`
- `research_modules/d1_sensor_fusion/src/d1_sensor_fusion/simulation.py`

实现内容：

- `SensorObservation` 数据结构。
- EKF 预测与更新。
- 延迟补偿。
- 传感器观测仿真。
- RMSE、连续性和协方差相关指标。

### 6.7 验证结果

当前测试报告显示：

- 延迟补偿前 RMSE：26.522 m。
- 延迟补偿后 RMSE：9.496 m。
- 航迹连续性：0.991。

这说明 D1 的延迟建模和前向补偿对异步观测融合有明显收益。

## 7. D2 多目标跟踪与数据关联

### 7.1 模块目标

D2 解决多目标交叉、编队密集、遮挡、漏检和虚警下的目标身份连续性问题。它消费 D1 的融合航迹或检测，输出稳定的 `global_track_id` 和关联日志。

### 7.2 GNN/Hungarian 主线

默认关联算法为 GNN/Hungarian：

1. 对每条已存在航迹做状态预测。
2. 对每个观测计算创新：

```text
nu = z - Hx
S = HPH^T + R
d^2 = nu^T S^{-1} nu
```

3. 使用马氏距离门控过滤不可行匹配。
4. 构建代价矩阵，代价可包含运动误差、类别差异、时间差、局部特征差异。
5. 使用 Hungarian 求解最小总代价匹配。
6. 匹配成功则更新航迹，未匹配观测尝试建轨，未匹配航迹进入 missed/lost 逻辑。

GNN/Hungarian 的优点是成熟、可解释、实时性好；缺点是在目标密集交叉时容易出现硬关联错误。

### 7.3 JPDA 与 MHT 升级项

JPDA：

- 不是给一个观测硬分配到一条航迹，而是计算多个可能匹配的联合概率。
- 适合目标距离近、门控区域重叠明显的场景。
- 计算量比 GNN 更高，但比 MHT 更可控。

MHT：

- 保留多个历史关联假设，等待后续观测消歧。
- 在复杂交叉和遮挡后恢复 ID 上更强。
- 缺点是分支膨胀，需要假设剪枝和算力预算。

D2 当前把 JPDA/MHT 作为可插拔研究项，不把它们作为默认主线。

### 7.4 航迹生命周期

D2 使用状态机管理航迹：

```text
tentative -> confirmed -> engageable -> lost -> dropped
```

含义：

- `tentative`：新观测刚建轨，尚不可信。
- `confirmed`：连续命中后确认存在。
- `engageable`：满足下游分配需要的质量门槛。
- `lost`：短时漏检或遮挡，暂不删除。
- `dropped`：长时间未恢复，删除或归档。

### 7.5 指标

D2 强制记录：

- `id_switch_count`：身份交换次数。
- `track_continuity`：航迹连续性。
- `duplicate_assignment_count`：重复关联或重复分配风险。
- RMSE 和混淆矩阵。

这些指标直接影响 D3 分配和 D5 末端配准。如果 `global_track_id` 不稳定，下游会出现错误分配和错误视觉绑定。

### 7.6 当前实现

主要文件：

- `research_modules/d2_data_association/d2_data_association/models.py`
- `research_modules/d2_data_association/d2_data_association/gating.py`
- `research_modules/d2_data_association/d2_data_association/associators.py`
- `research_modules/d2_data_association/d2_data_association/tracker.py`
- `research_modules/d2_data_association/d2_data_association/metrics.py`
- `research_modules/d2_data_association/d2_data_association/simulation.py`

已实现内容：

- GNN/Hungarian 关联器。
- JPDA/MHT 风格接口。
- 马氏距离门控。
- 航迹生命周期。
- ID Switch、连续性和 RMSE 统计。

### 7.7 验证结果

当前仿真覆盖：

- crossing。
- formation。
- occlusion。
- missed detection。
- false alarm。

各场景均运行 GNN/JPDA/MHT 风格关联器，并记录 IDSW。图表位于：

- `research_modules/d2_data_association/docs/association_idsw_rmse.png`
- `research_modules/d2_data_association/docs/benchmark_results.json`

## 8. D3 集中式资源-目标分配

### 8.1 模块目标

D3 解决多目标、多资源条件下的分配问题。输入是 D2 输出的稳定 `GlobalTrack[]` 和资源状态 `ResourceState[]`，输出是版本化 `AssignmentPlan`。

### 8.2 数学模型

定义分配变量：

```text
x_ij ∈ {0,1}
```

表示资源 `i` 是否分配给目标 `j`。

目标函数：

```text
minimize Σ_i Σ_j x_ij C_ij
```

约束：

```text
每个资源最多分配一个目标
每个目标最多一个主资源
不可行组合赋高代价或禁止
```

### 8.3 代价函数

当前 D3 把代价拆成可解释分项：

```text
C_ij =
  w_window      * intercept_window_cost
+ w_uncertainty * track_uncertainty_penalty
+ w_threat      * threat_priority_cost
+ w_resource    * resource_state_penalty
+ w_fov         * fov_confirmation_difficulty
+ w_conflict    * resource_conflict_risk
+ infeasible_penalty
```

含义：

- 接近窗口：资源是否能在合理窗口内接近目标。
- 航迹不确定性：协方差越大，分配风险越高。
- 威胁权重：高威胁目标优先获得资源。
- 资源状态：能量、可用性、当前任务等。
- 视场确认难度：末端是否更容易完成 D5 配准。
- 冲突风险：多个资源路径或任务是否冲突。

### 8.4 Hungarian/LAP 主算法

中心节点正常时，默认使用 Hungarian/LAP。理由：

- 适合一对一资源-目标分配。
- 复杂度可控。
- 工程成熟。
- 结果可解释，便于审计。

当需要表达多资源协同、备份资源、容量限制或复杂约束时，D3 预留最小费用流接口。

### 8.5 滚动重分配与迟滞

多目标动态场景下，如果每次代价略有变化就重分配，会造成任务抖动。D3 使用迟滞策略：

```text
J_new < (1 - delta) * J_old
and dwell_time > min_dwell
```

只有新计划显著优于旧计划，并且旧计划已保持足够时间，才允许切换。

同时：

- `plan_id` 标识计划。
- `version` 单调递增。
- stale plan 被拒绝。
- `human_authorization_state` 默认需要外部审查层确认。

### 8.6 当前实现

主要文件：

- `research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py`
- `research_modules/d3_assignment_planner/src/d3_assignment_planner/costs.py`
- `research_modules/d3_assignment_planner/src/d3_assignment_planner/solver.py`
- `research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py`
- `research_modules/d3_assignment_planner/src/d3_assignment_planner/min_cost_flow.py`

已实现：

- `AssignmentPlanner`。
- 成本分解。
- Hungarian 求解。
- 最小费用流预留接口。
- 重分配迟滞。
- 版本管理和过期计划拒绝。

### 8.7 验证结果

当前结果：

- 无迟滞时重分配次数：33。
- 有迟滞后重分配次数：12。
- 高威胁未分配比例：0.0。

相关图表：

- `research_modules/d3_assignment_planner/results/cost_reassignment.png`
- `research_modules/d3_assignment_planner/results/weight_sensitivity.png`

## 9. D4 分布式协同、被动降级与主动降级

### 9.1 模块目标

D4 解决两类问题：

1. 被动降级：中心节点或二级节点失效后，如何保持局部任务连续性。
2. 主动降级：中心节点仍在线，但 D1/D2/D3/D5 证据显示当前中心或二级分配已不可靠时，如何仲裁是否继续中心计划、中心重分配、请求二级辅助、降到二级节点或进入分布式协商。

D4 不追求完全替代中心节点，而是在信息不完整、通信受限的离线仿真中维持最低限度的局部分配一致性，并显式记录仲裁原因。

### 9.2 C2Health 状态机

状态：

```text
normal -> degraded -> suspect -> failed
```

恢复不允许只靠 heartbeat。原因是 heartbeat 恢复只能说明通信重新出现，不能证明中心态势与降级期间形成的局部态势一致。因此恢复需要：

- 双轨航迹合并。
- 分配版本校验。
- 冲突检测。
- 人工接受标志。

### 9.3 被动降级：三级降级链路

```text
中心 C2 正常
  -> 中心失效
  -> 地面备份 / 高空系留二级侦察节点接管局部区域
  -> 二级节点不可用
  -> 完全无中心 CBBA / 拍卖式协商
```

节点角色：

- `GROUND_BACKUP`：地面备份协调者。
- `SECONDARY_RECON`：高空系留侦察二级节点。
- `CLUSTER_REPRESENTATIVE`：资源集群代表。
- `INTERCEPTOR`：普通执行资源。

关键字段：

- `node_role`：节点角色。
- `coordinator_only`：是否只做协调/观测，不作为执行资源。
- `coverage_cell`：覆盖小区。
- `takeover_priority`：接管优先级。
- `lease_epoch`：租约版本，防止旧 leader 复活。

### 9.4 CBBA/拍卖式协商

CBBA 思路：

1. 每个节点根据本地 `TrackSummary` 和 `ResourceSummary` 计算出价。
2. 节点构建任务 bundle。
3. 节点交换 winner/bid 信息。
4. 冲突时按出价、优先级、节点 ID 等规则消解。
5. 多轮传播后收敛到一致 assignment view。

CBBA 的价值在于中心缺失时维持分布式一致性；缺点是通信开销、收敛时间和局部最优问题。

### 9.5 主动降级仲裁器

D4 当前新增规则基线：

- `research_modules/d4_distributed_fallback/d4_distributed_fallback/active_degradation.py`
- `research_modules/d4_distributed_fallback/tests/test_active_degradation.py`

核心类：

- `ActiveDegradationArbiter`
- `ActiveDegradationConfig`
- `ActiveDegradationDecision`
- `DegradationMode`
- `DegradationAction`
- `TrackUncertaintySummary`
- `AssociationRiskSummary`
- `AssignmentValiditySummary`
- `TerminalAssociationSummary`

仲裁器输入 D1-D5 的摘要和 `C2Health`。若 `C2Health.FAILED`，直接进入 `passive_failover`；若中心仍在线，则检查末端一致性、定位不确定度、关联风险和计划有效性。

重要保护规则：

- 单帧视觉不一致不直接触发完全分布式。
- D5 `locked` 且资源/ID/版本一致时，不因 D5 触发主动降级。
- D3 计划风险为主时，优先 `request_center_replan`。
- D1/D2 风险升高但 D5 仍一致时，优先 `request_secondary_assist`。
- D5 连续多帧不一致或 `reacquire` 才进入 `degrade_to_secondary` 或 `degrade_to_distributed`。
- 友方冲突进入 `hold_for_review`。

### 9.6 二级侦察节点的新增作用

二级节点健康时：

- 作为局部区域协调者。
- 汇总局部航迹摘要。
- 维护局部 `AssignmentPlan` 版本。
- 向小范围资源下发观测摘要或图像 cue。

二级节点对 D5 的 cue 只作为辅助配准证据：

- 不能授权。
- 不能绕过版本校验。
- 不能替代身份认证。
- 不能改写 `global_track_id`。

### 9.7 当前实现

主要文件：

- `research_modules/d4_distributed_fallback/d4_distributed_fallback/models.py`
- `research_modules/d4_distributed_fallback/d4_distributed_fallback/coordinator.py`
- `research_modules/d4_distributed_fallback/d4_distributed_fallback/cbba.py`
- `research_modules/d4_distributed_fallback/d4_distributed_fallback/active_degradation.py`
- `research_modules/d4_distributed_fallback/d4_distributed_fallback/network.py`
- `research_modules/d4_distributed_fallback/d4_distributed_fallback/simulation.py`

已实现：

- `C2Health`。
- `FailoverCoordinator`。
- `CBBANegotiator`。
- `NodeRole.SECONDARY_RECON`。
- 二级节点优先接管逻辑。
- `coordination_mode` 写入 `final_views`。
- `ActiveDegradationArbiter` 主动降级规则基线。
- 被动/主动降级动作枚举和摘要 dataclass。
- 主动降级单元测试。

### 9.8 当前结果与不足

验证结果：

- 5 节点降级协商收敛。
- 接管时间：6.0 s。
- 共识轮数：5。
- 完成率：1.0。
- 单元测试覆盖二级侦察节点优先于完全分布式 CBBA。
- D4 主动降级测试覆盖 D5 一致继续、风险上升请求二级辅助、D3 风险请求中心重分配、持续末端不一致降级到二级节点、二级不可用降级到分布式、中心失败被动降级、coverage cell 过滤和 resource mismatch。

已知不足：

- 默认 smoke simulation 仍主要是 CBBA 降级基线，尚未默认构造 `secondary_recon` 节点。
- `coordination_mode/leader_role/coverage_cell` 尚未透传到顶层 D6 metrics。
- 多 `coverage_cell` 的区域过滤和交界区策略仍需扩展。
- D1/D2/D3/D5 的摘要目前多为文档合同，D4 内先用 dataclass 作为离线规则基线。

## 10. D5 终端视觉配准与身份认证

### 10.1 模块目标

D5 解决末端视场内“多个候选目标、友方资源、未知飞行物同时出现”时的配准问题。它的核心原则是：本地相机看到的最近目标不等于中心分配目标。

D5 只输出配准状态，不输出控制量，不改变全局分配。

### 10.2 图像投影模型

对全局航迹点 `P_w`，使用相机模型：

```text
P_c = R_cw P_w + t_cw
p = K P_c
```

其中：

- `K` 为相机内参。
- `R_cw, t_cw` 为世界到相机的外参。
- `p` 为像素平面点。

协方差通过雅可比传播：

```text
Sigma_pixel = J Sigma_world J^T + R_pixel
```

再用像素马氏距离做门控：

```text
d^2 = (p_local - p_pred)^T Sigma_pixel^{-1} (p_local - p_pred)
```

### 10.3 综合代价

D5 的候选代价包括：

- 投影误差。
- 像素角速率一致性。
- 类别差异。
- 时间戳差异。
- 友方冲突惩罚。
- MOT 历史和质量。
- 二级侦察 cue 命中奖励。

即使 `ReconImageCue` 命中，也只能降低代价，不能跳过授权和版本检查。

### 10.4 决策状态

| 状态 | 含义 |
|---|---|
| `locked` | 唯一候选通过几何、版本、授权、身份和 MOT 质量约束 |
| `ambiguous` | 多候选接近、代价过高、身份不可靠或 MOT 质量不足 |
| `hold` | 未授权、版本不一致或已验证友方重叠 |
| `reacquire` | 目标不可投影、不可见或无候选过门限 |

D5 的目标不是最大化 `locked` 次数，而是避免错误绑定。

### 10.5 友方与合作身份

身份来源可包括：

- Remote ID / OpenDroneID。
- MAVLink 签名。
- DDS Security。
- AprilTag 或仿真视觉标签。

原则：

- verified friend 才能作为友方正向确认。
- stale、unsigned、unverified、spoof suspected 不作为可信友方确认。
- unknown 不等于 hostile。

### 10.6 二级侦察节点 `ReconImageCue`

`ReconImageCue` 包含：

- `producer_node_id`。
- `image_frame_id`。
- `global_track_id`。
- `center_px`。
- `bbox`。
- `confidence`。
- `scoped_resource_ids`。

硬约束：

如果 cue 来自二级侦察节点自己的相机，不能直接与拦截资源本地相机像素坐标比较。必须先把 cue 重投影到当前拦截资源相机平面，或者明确 `image_frame_id` 已是当前本地相机帧。

建议后续增加：

- `max_recon_cue_age_s`。
- `target_camera_frame_id`。
- `recon_cue_used_count`。
- 空 `scoped_resource_ids` 的广播语义或禁用语义。

### 10.7 多无人机重叠视场配准

当无人机1看到局部目标 `1,2,3`，无人机2看到局部目标 `2,3,4` 时，两个编号不能直接合并。它们只是各自相机内的 `local_track_id`，必须带命名空间，例如 `INT-01/L2`、`INT-02/L1`。系统应以 D2 的 `global_track_id` 为唯一全局身份，把不同相机的局部观测都作为证据挂到同一个全局航迹上。

推荐处理链路：

1. 每个拦截资源输出 `CrossViewObservation`，包含 `resource_id`、`camera_id`、`frame_id`、`measurement_timestamp`、`arrival_timestamp`、`camera_pose`、`bbox`、`center_px`、`quality`、`bearing_rate` 和像素协方差。
2. 中心或二级节点把 `GlobalTrack` 按各相机曝光时间预测，并分别投影到每个相机画面。
3. 对每个相机内部先做 D5 已有的像素马氏门控和候选代价排序。
4. 对重叠视场建立 `CrossViewAssociation`：例如 `INT-01/L2 -> G2` 与 `INT-02/L1 -> G2` 可形成同一目标的多视角证据。
5. 对多视角观测只更新候选置信度和协方差摘要，正式 `global_track_id` 仍由 D2 维护。
6. 若两个相机对同一目标给出冲突候选，或者同一局部轨迹可解释为多个全局目标，则输出 `ambiguous` 并请求 D4/D2 仲裁。

因此，例子中的理想配准结果不是“两个无人机的 2 就是同一个 2”，而是：

```text
INT-01/L1 -> G1
INT-01/L2 -> G2
INT-01/L3 -> G3

INT-02/L1 -> G2
INT-02/L2 -> G3
INT-02/L3 -> G4
```

其中 `G2` 和 `G3` 因被两架无人机同时观测，可降低交接不确定性；`G1` 与 `G4` 是单侧可见目标，应保留较大不确定性或等待雷达、声学、二级侦察节点补充。

下一步建议新增 `TerminalObservationBus` 或 `TerminalCrossViewFusion`，集中维护：

- `CrossViewObservation`：带资源、相机、时间戳和像素协方差的局部视觉观测。
- `CrossViewAssociation`：局部视觉轨迹到全局航迹的候选关系、代价、置信度和歧义度。
- `CrossViewTrackEvidence`：同一 `global_track_id` 来自多个相机的证据集合。
- `cross_view_conflict_count` 与 `cross_view_consistency_rate`：供 D6 统计。

该扩展仍然遵守 D5 硬约束：本地或跨视场模块只能报告候选证据，不能新建、重写或换绑规范 `global_track_id`。

### 10.8 当前实现

主要文件：

- `research_modules/d5_terminal_association/src/d5_terminal_association/models.py`
- `research_modules/d5_terminal_association/src/d5_terminal_association/geometry.py`
- `research_modules/d5_terminal_association/src/d5_terminal_association/identity.py`
- `research_modules/d5_terminal_association/src/d5_terminal_association/associator.py`
- `research_modules/d5_terminal_association/simulations/run_terminal_association_sim.py`

已实现：

- `TerminalAssociator`。
- `IdentityChecker`。
- `CameraModel`。
- `ReconImageCue`。
- 版本检查、授权检查、友方冲突检查。
- `global_track_id` 不变式测试。
- 单机视场内多候选目标的保守关联。
- 二级侦察 cue 的资源作用域约束。

尚未完整实现：

- 多架拦截无人机各自独立相机模型。
- `LocalVisualTrack` 的 `resource_id/camera_id/frame_id/camera_pose/covariance` 字段。
- 跨相机 `INT-01/L2` 与 `INT-02/L1` 同属 `G2` 的联合配准。
- 多视角视觉观测对 `GlobalTrack` 协方差摘要的融合回传。

### 10.9 验证结果

当前结果：

- `locked` precision：1.0。
- `global_track_id_mutations`：0。
- 二级 `ReconImageCue` 只对 scoped resource 降低代价。
- 未授权 assignment 即使有 cue 也不能升级为 `locked`。

图表：

- `research_modules/d5_terminal_association/docs/terminal_decision_timeline.png`

## 11. D6 系统级评估指标体系

### 11.1 模块目标

D6 解决“不能只报命中率”的问题。多目标反无人机系统的风险往往来自身份错配、重复分配、降级冲突、友方重叠和授权状态，而不是单一成功率。

D6 统一消费 D1-D5 的日志，输出 episode 指标、批量统计和图表。

### 11.2 指标分类

探测类：

- `detection_probability`
- `false_alarm_rate`
- `missed_detection_rate`

跟踪类：

- `track_rmse`
- `track_continuity`
- `id_switch_count`

分配类：

- `duplicate_assignment_count`
- `unassigned_high_threat_count`

降级类：

- `failover_time`
- `consensus_rounds`
- `degraded_completion_rate`

末端配准类：

- `terminal_association_accuracy`
- `terminal_id_switch_count`
- `ambiguous_fov_event_count`
- `friend_overlap_hold_count`
- `time_to_terminal_lock`

安全类：

- `constraint_violation_count`
- `human_override_count`

### 11.3 工程指标与学术指标

D6 文档也讨论 OSPA、CLEAR MOT、MOTA/MOTP 等指标。当前项目保留可解释工程指标，是因为：

- 工程调试需要定位到哪个模块出错。
- 分配和降级问题无法只用 MOT 指标覆盖。
- 末端友方重叠和授权状态需要单独统计。
- 批量实验需要按场景、算法和节点状态分组。

### 11.4 当前实现

主要文件：

- `research_modules/d6_evaluation_metrics/d6_evaluation_metrics/metrics.py`
- `research_modules/d6_evaluation_metrics/d6_evaluation_metrics/reporting.py`
- `research_modules/d6_evaluation_metrics/d6_evaluation_metrics/simulation.py`
- `research_modules/d6_evaluation_metrics/scripts/run_batch_example.py`

输出：

- `episode_metrics.csv`
- `summary_metrics.csv`
- `batch_report.md`
- `plots/*.png`
- `logs/*.jsonl`

### 11.5 当前结果

D6 已生成：

- 探测类图表。
- 跟踪类图表。
- 分配类图表。
- 降级类图表。
- 末端类图表。
- 安全类图表。
- selected metric distributions。

位置：

- `research_modules/d6_evaluation_metrics/outputs/example_batch/`
- `research_modules/d6_evaluation_metrics/outputs/integration_smoke/`

## 12. 多目标 vs 多目标场景下的体系运行

以 5 个来袭目标与 5 个资源为例：

### 12.1 初始发现

雷达产生较粗但覆盖范围大的观测，声学提供粗方位和类别提示，光电或侦察节点在局部区域提供像素观测。D1 把这些观测统一为 `GlobalTrack`，并通过协方差表达不确定性。

### 12.2 目标交叉

当 5 个目标出现交叉或密集编队：

- D2 首先用 GNN/Hungarian 做硬关联。
- 若门控区域重叠明显、`id_switch_count` 升高，则引入 JPDA/MHT 做对照。
- D6 记录 ID Switch 和连续性，判断是否需要升级关联策略。

### 12.3 资源分配

D3 构建 5x5 代价矩阵：

- 航迹不确定性高的目标分配风险更高。
- 高威胁目标有更高优先级。
- 资源状态差的资源代价更高。
- 末端视场确认难度也进入代价。

Hungarian 给出主分配，迟滞逻辑避免每帧频繁换绑。

### 12.4 有的目标在视场内，有的不在视场内

末端时：

- D5 对已分配的全局目标做相机投影。
- 视场内目标进入几何门控和 MOT 匹配。
- 不在视场内则输出 `reacquire` 或等待 D1/D2/D4 继续提供预测和 cue。
- 若多个局部目标都可能对应同一个全局目标，则输出 `ambiguous`。
- 若已验证友方与候选重叠，则输出 `hold`。
- 若多个拦截无人机存在重叠视场，当前程序仍按单机 D5 决策分别处理；下一阶段应由 `TerminalCrossViewFusion` 把 `INT-01/L2`、`INT-02/L1` 这类局部观测统一配准到同一 `global_track_id`，并把冲突和置信度摘要回传给 D4/D6。

### 12.5 中心节点失效

中心失效后：

- 若二级侦察节点可用，D4 选择其作为区域协调者。
- 二级节点向小范围资源提供观测摘要和 `ReconImageCue`。
- D5 使用已重投影 cue 辅助候选排序，但不跳过保守规则。
- 若二级节点也失效，进入完全无中心 CBBA 协商。

### 12.6 高威胁目标的 M 对 N 联盟流程

当目标 \(j\) 的威胁和任务模型要求多资源协同时，系统使用 required resource count \(k_j\)，不再假设一目标只有一个 owner。高威胁研究基线可设 \(k_j=3\)。

推荐的完整流程为：

```text
D1/D2 建立唯一 canonical GlobalTrack
-> D3 根据 k_j、能力、威胁、可达性和冲突风险形成联盟
-> D4 发布并维护 coalition version/epoch/lease
-> D5 验证每个成员的 local track 是否支持同一 global_track_id
-> D7 按 simultaneous/sequential/hybrid 合同执行成员级 PN/PNG
-> D6 评估需求满足、到达时序、成员重构、身份和安全
```

中心正常时，基数需求可用 b-matching/最小费用流研究；复杂能力、主备、同步和波次使用 CP-SAT/MILP 参考模型。二级节点接管时必须发布新的联盟版本。完全无中心时，现有单 winner CBBA 只能作为候选成员选择基线，不能把目标复制三份来冒充原子联盟。

当前推荐比较四条路线：

- independent PN：多个独立 pair，只作基线，不称为协同导引。
- simultaneous 3：三名成员满足共同窗口，并使用不同终端扇区和最小安全间距。
- sequential 1+1+1：按波次执行，后续成员根据新版本反馈继续。
- hybrid 2+1：两名 primary 首批协同，一名 reserve/observer 保持间隔，作为默认研究假设。

多平台协同定位要求双时间戳、共同 NED、量测时刻位姿、相机/传感器外参和协方差，以及非退化视线交会几何。第三个视角只增加冗余，不能自动保证精度。多个合法联盟成员锁定同一 global_track_id 时，D5/D6 应记录 planned cooperative lock；只有计划外加入、过期版本、local-to-global 冲突等才属于错误 duplicate。

当前代码已实现中心化 \(k_j>1\) 基础闭环：D3 schema v2 和 demand-slot Hungarian 按 all-or-none 形成联盟，默认高威胁策略为 hybrid 2+1；D5 区分合法联盟多锁与越权/超额锁；D7 按成员角色、波次、时间窗和版本门控 PN/视觉 PNG；D6 记录需求、联盟和到达指标。main episode bus 已验证 5-resource/2-target 的 3+1 pair 不折叠，质点 `cooperative_3v1`/`cooperative_5v2` 需求满足率为 1.0。尚未实现的是二级节点和完全分布式条件下的原子 coalition commit/ACK/补位；中心失效时 \(k_j>1\) 当前 fail-closed 并输出 `coalition_fallback_unsupported`。详细状态见 `subagent_reviews/MAIN_M_TO_N_COOPERATIVE_INTERCEPTION_SYNTHESIS.md` 和 `subagent_reviews/MAIN_IMPLEMENTATION_GAP_AUDIT.md`。

## 13. AirSim 离线集成规划

当前阶段已经具备 Python 质点仿真和离线日志评估。后续 AirSim 集成建议采用离线回放优先：

### 13.1 数据采集

AirSim 输出：

- 目标和资源真值位置、速度、类别。
- RGB 图像帧。
- 相机内参和外参。
- 模拟雷达观测。
- 模拟声学方位。
- 模拟光电框。
- 中心节点 heartbeat 和分配计划。

### 13.2 回放转换

转换为：

- D1 `SensorObservation`。
- D2 检测/航迹输入。
- D3 `ResourceState`。
- D4 `TrackSummary` / `ResourceSummary` / `EventRecord`。
- D5 `CameraModel` / `LocalVisualTrack` / `IdentityClaim` / `ReconImageCue`。
- 跨视场扩展需要新增 `CrossViewObservation`、`CrossViewAssociation` 和 `CrossViewTrackEvidence`，并要求每个相机观测携带 `resource_id/camera_id/frame_id/camera_pose`。
- D6 JSONL/CSV 日志。

### 13.3 ROS 2 离线节点规划

后续可把每个模块封装为 ROS 2 离线节点：

| 模块 | 订阅 | 发布 |
|---|---|---|
| D1 | `/radar/tracks`, `/acoustic/bearings`, `/vision/detections` | `/tracks/fused` |
| D2 | `/tracks/fused` | `/tracks/associated` |
| D3 | `/tracks/associated`, `/resources/state` | `/assignment/plan` |
| D4 | `/c2/heartbeat`, `/assignment/plan`, `/resources/summary` | `/degraded/plan`, `/recon/cues` |
| D5 | `/tracks/associated`, `/assignment/plan`, camera topic, `/recon/cues` | `/terminal/associations`, `/terminal/identity_claims` |
| D6 | 所有日志/rosbag | 离线报告和图表 |

## 14. 当前验证状态

来自 `research_modules/TEST_REPORT.md`：

| 模块 | 测试结果 |
|---|---|
| D1 Sensor Fusion | 54 passed |
| D2 Data Association | 57 passed |
| D3 Assignment Planner | 99 passed, 1 optional OR-Tools skipped |
| D4 Distributed Fallback | 101 passed |
| D5 Terminal Association | 112 passed |
| D6 Evaluation Metrics | 63 passed |
| D7 Proportional Guidance | 79 passed |
| AirSim Runtime | 70 passed |
| Point-mass Integration | 7 passed |
| Cross-module Contract | 3 passed |
| 总计 | 645 passed, 1 optional skipped |

集成验证覆盖：

- D1 canonical NED track。
- D2 detection kwargs。
- D3 authorization handoff。
- D5 `locked` state。
- D6 terminal metrics。

已知环境 warning：

- Matplotlib `Axes3D` warning。
- 项目当前只使用 2D 图表，不影响输出。

### 14.1 规模化三维分支验证

`feat/scalable-3d-200v200` 已把 D1-D7 规则路径接入统一三维质点时钟。2026-07-23
完成 nominal 200 对 200、10 秒、seed 1000-1019 的 clean-source 描述性校准。
20/20 episode 状态有限，在线真值使用为 0，跨构建规范载荷和真值制品等价。核心
墙钟均值为 86.099 秒，实时倍率均值为 0.1163，距离实时仍约 8.6 倍。该结果属于
科研仿真性能证据，不代表 AirSim、实机或物理拦截能力。

后续身份审计确认旧 20 个 episode 的严格身份交换指标尚不可用。当时有 118 个航迹帧发生
多真值混轨，另有 2,464 个受评分映射缺少明确离线标签。当前已完成第一轮治理：D1 修复冻结
相机元数据导致的错误视觉投影；main、D2、D6 建立目标、已知虚警、未知三态离线标签合同；
已知虚警不进入严格身份交换分母，未知或冲突证据继续失败关闭。detached clean 提交
`488dc39` 的三组 2.2 秒回放和一组 10 秒回放中，标签缺失均为 0，在线真值使用仍为 0。

严格指标尚未整体闭合。三个 2.2 秒 seed 中只有一个可计算严格 ID Switch，另两个仍出现
雷达扫描间多真值谱系；10 秒 seed 1000 的 402 条已知虚警已被 D6 排除，仍剩余 7 个雷达
谱系歧义映射。D1 雷达交替环 v1 已完成 200 对 200、2.2 秒、2 架侦察机、三 seed 同配置
clean A/B。候选把严格身份可用率从 `1/3` 提高到 `3/3`，但 D2 航迹分别减少 `1/8/3`，
D3 分配分别减少 `2/10/7`，seed 1001 continuity 下降约 `0.055`，并抑制
`1.12%/6.61%/3.98%` 的雷达量测，因此不晋级。

当前默认路径仍为原 Hungarian。默认关闭候选后三 seed 全部恢复 baseline，跨构建规范在线
载荷 `3/3` 相等。严格身份 P1 继续开放，下一候选必须覆盖最大匹配中的交替环、free-row 和
free-column 路径，并联合验收身份、航迹、分配、连续性、抑制、birth 与 recall。10 秒
baseline 的 7 个歧义映射保留为长期跨模态验收目标；部分身份下界继续只作诊断，不进入系统
效果结论。

D7 对 37,000 条固定输入命令的复核没有确认导引内核回归，比例导引、视觉比例导航
制导、视线/预计碰撞时间滤波和安全切换门保持不变。main 发布总线的重复键检查已
优化，但单 seed 核心墙钟只出现描述性小幅变化，200 对 200 实时缺口仍保持开放。

正式实验采用同一 5700 单元父清单，按 R0、G1、A1、A2、A3、C1 和 F1 分 scope
执行。R0 当前冻结在 clean source `1e5ed8d`，已完成 135/900；磁盘空间达到保护下限后
停止启动新单元。main 已补齐学习 scope 的可恢复分片、模型文件树和设备绑定、准入预检、
断点恢复及确定性合并。D3 自我准入入口已关闭；D4 没有开放 P0；D6 的 D5 G1 外部审计和
D5 G1 装配器软件均已完成。当前 D5 模型仍因实现证据、实现谱系、困难扰动和单特征捷径
五项 blocker 失败关闭，D3/D4/A3 装配器仍开放。D3、D4、D5 图模型和 D5 主动视觉模型
均未获正式辅助权限，因此学习变体仍为 0 个正式 episode。该状态区分了“执行基础设施和
部分装配软件已具备”与“模型效果已验证”，不得用正向 fixture、开发模型或规则回退补齐
学习组。

## 15. 代码与文档索引

### 15.1 总体文件

| 文件 | 作用 |
|---|---|
| `research_modules/README.md` | 七模块总入口 |
| `research_modules/INTEGRATION_CONTRACT.md` | 跨模块数据合同 |
| `research_modules/DOCUMENTATION_STANDARD.md` | 文档结构规范 |
| `research_modules/TEST_REPORT.md` | 集成测试和结果摘要 |
| `research_modules/run_all_tests.py` | 全量测试入口 |
| `research_modules/run_smoke_simulations.py` | smoke simulation 入口 |
| `C_UAS_RESEARCH_MODULES_DELIVERABLE_20260701.zip` | 当前交付包 |

### 15.2 七个子模块

| 模块 | 算法文档 | 实验报告 |
|---|---|---|
| D1 | `research_modules/d1_sensor_fusion/docs/ALGORITHM_AND_IMPLEMENTATION.md` | `research_modules/d1_sensor_fusion/reports/EXPERIMENT_REPORT.md` |
| D2 | `research_modules/d2_data_association/docs/ALGORITHM_AND_IMPLEMENTATION.md` | `research_modules/d2_data_association/docs/EXPERIMENT_REPORT.md` |
| D3 | `research_modules/d3_assignment_planner/docs/ALGORITHM_AND_IMPLEMENTATION.md` | `research_modules/d3_assignment_planner/docs/EXPERIMENT_REPORT.md` |
| D4 | `research_modules/d4_distributed_fallback/docs/ALGORITHM_AND_IMPLEMENTATION.md` | `research_modules/d4_distributed_fallback/reports/EXPERIMENT_REPORT.md` |
| D5 | `research_modules/d5_terminal_association/docs/ALGORITHM_AND_IMPLEMENTATION.md` | `research_modules/d5_terminal_association/docs/EXPERIMENT_REPORT.md` |
| D6 | `research_modules/d6_evaluation_metrics/docs/ALGORITHM_AND_IMPLEMENTATION.md` | `research_modules/d6_evaluation_metrics/EXPERIMENT_REPORT.md` |
| D7 | `research_modules/d7_proportional_guidance/docs/ALGORITHM_AND_IMPLEMENTATION.md` | `research_modules/d7_proportional_guidance/reports/EXPERIMENT_REPORT.md` |

## 16. 当前不足与下一步

### 16.1 已知不足

1. AirSim 真实多 seed 校准尚未闭合；D3/D4/D5/D7 的状态迁移阈值、降级必要性标签、视觉 gate 和超时原因还需要批量统计。
2. 二级机动高空侦察节点已能稳定出图、云台指向和投影，但网络同帧全覆盖仍偏低；当前 P1 瓶颈是 `not_all_targets_visible` / `network_union_incomplete`。
3. D5 多相机/二级 detect 到既有 `global_track_id` 的跨视角注册已有候选和稳定注册统计，但仍需外参、时间戳、coverage cell、D2/D3 binding 和 MOT 稳定窗口的长期标定。
4. YOLOv8 + ByteTrack/BoT-SORT/IoU fallback 已有可运行接线，但真实 AirSim 多 seed 下的目标尺度、置信度、FOV、CPU/GPU 预算和失败回退仍需校准。
5. D1 仍需更多真实 Blocks/CV fixture、区域时间窗口、协方差增长率窗口和 D6 长期 schema 对齐。
6. D2 的 JPDA/MHT 当前仍以研究对照和接口为主，尚未作为大规模默认运行模式。
7. D7 当前主线是二维 PN/PNG 与 SimpleFlight gate；三维高度差、FRPN/MPC 对照和真实多 seed PN/Pure Pursuit/PNG 统计仍属后续 P1/P2。

### 16.2 短期迭代

1. 复跑 5v5 D4/D5 registration calibration，按二级数量、站位、FOV、coverage cell 和扫描策略输出覆盖漏斗。
2. 将 D5 cross-view registration、D4 active/passive degradation、D7 terminal gate 和 D6 AirSim calibration report 继续合并到统一 episode/seed 报告。
3. 针对 SimpleFlight 5v5 拦截增加更长 `intercept_max_duration` 和多 seed 统计，拆分 timeout 来自机动能力、初始几何还是视觉 gate。
4. 校准 YOLOv8/MOT 路径的 bbox 稳定窗口、置信度、延迟、FOV 和回退到 AirSim detect 的条件。
5. 增强 D2 密集交叉场景，形成 GNN/JPDA/MHT 的定量对比表。
6. 将 D6 报告扩展为“算法配置 vs 指标”的自动对比矩阵。

### 16.3 中期迭代

1. 将 AirSim Blocks 多 seed replay 固化为稳定 fixture，并引入离线 truth label。
2. 将 D1-D7 封装为 ROS 2 离线回放节点。
3. 接入 tf2/message_filters 的时间与坐标对齐语义。
4. 引入 Stone Soup、FilterPy、OR-Tools、BoT-SORT/ByteTrack 做开源基准对照。

### 16.4 长期迭代

1. 标准化场景库：交叉、密集编队、遮挡、虚警、中心失效、二级节点失效、友方重叠。
2. 批量运行不同算法组合，形成统计显著的方案比较。
3. 完善人机审查状态、授权版本、安全约束和审计日志。
4. 将体系文档、代码、仿真和结果形成可复现实验包。

## 17. 结论

本项目已经形成一个可运行、可测试、可扩展的反无人机多目标拦截科研仿真体系。它不是单个算法 demo，而是一条完整的系统链路：

- D1 解决多源异步观测到协方差航迹的问题。
- D2 解决多目标身份连续性问题。
- D3 解决中心化多资源分配和重分配抖动问题。
- D4 解决中心失效后的二级节点接管和分布式保底问题。
- D5 解决末端多目标视场配准和友方正向确认问题。
- D6 解决全系统可复现评估问题。
- D7 解决雷达中段 PN 与末端视觉 PNG 的导引合同门控问题。

这套方案的核心价值是把探测、跟踪、分配、降级、末端配准、比例导引和评估放入同一个数据合同和测试框架中，使后续 AirSim 校准、算法对比和论文实验都能建立在统一、可审计、可复现的工程基础上。
