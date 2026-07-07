# C-UAS 节点能力、通信、算力与部件选型报告

**日期**: 2026-07-05  
**角色**: main agent 汇总 D1-D7 子智能体需求  
**适用阶段**: MSM 当前 AirSim/质点仿真到工程样机需求分解  

## 1. 边界与结论

本文回答的问题是：为了支撑当前反无人机多机拦截体系，从中心节点、地面雷达、高空系留二级节点、拦截无人机、通信链路和评估节点看，需要多大的通信带宽、处理能力、感知能力、续航时间和响应时间。

本文只给出仿真和工程样机层面的需求、公开产品能力对标和预算级成本。本文不包含无线电频点规划、雷达波形/发射参数、干扰压制、绕过授权或自动处置细节。

总判断：

1. 当前 D1-D7 算法主线对算力要求并不高，真正吃资源的是 D5 真实图像检测/MOT、二级节点视频 cue、多相机日志和 D6 批量评估。
2. 对 5v5 baseline，结构化元数据链路通常只需要数 Mbps；如果传多路 1080p/4K 视频，链路立刻进入几十到数百 Mbps。因此系统应默认传 `GlobalTrack/bbox/camera_pose/assignment/status`，视频只做定向 cue。
3. 雷达应优先满足 10 Hz 级航迹更新、带协方差输出、角精度约 0.5-1 deg、距离误差约 1-6 m、端到端时间戳可追溯，而不是把雷达点迹当真值。
4. 系留高空侦察无人机是最有价值的二级节点：它提供持续高视角、局部视频 cue、二级接管和通信中继。它不是常态全局中心，中心失效或主动降级时才接管覆盖区。
5. 拦截无人机的关键不是单纯高速度，而是闭合速度、相机稳定可见、D5 `locked` 和 D7 `maneuver_margin` 同时成立。相机分辨率、帧率、外参和延时直接决定视觉 PNG 能不能切换。
6. 成本主导项是 C-UAS 雷达、系留二级节点、EO/IR 吊舱和高端 MANET；算法计算机和机载 Jetson 不是最大成本项。

## 2. D1-D7 子智能体需求汇总

| 模块 | 通信带宽 | 处理能力 | 感知/输入能力 | 续航/持续运行 | 响应时间 |
| --- | --- | --- | --- | --- | --- |
| D1 多传感器融合 | 结构化观测约 0.1-0.3 Mbps/目标；5 目标约 0.5-1.5 Mbps，不含视频 | 2 倍实时余量，约 `>=34N obs/s`；5 目标约 `>=170 obs/s` | 雷达 5-10 Hz，EO 约 5 Hz，声学 1-2 Hz；所有观测带协方差和双时间戳 | 至少 60 s episode，批跑 10-60 min 无无界内存增长 | 融合粒度 0.1 s；雷达延迟可补偿 0.5-2 s，但新鲜度应小于 D3 周期或 1 s |
| D2 数据关联 | 0.1-1 Mbps metadata/链路；2-10 Hz，必须有 sequence/timestamp/covariance | GNN 每帧 <50-100 ms；JPDA/MHT 只中心或离线 | detection/track 带位置、协方差、来源、时间戳；二维 99% 马氏门限默认 9.21 | 保留 3-10 s 或 5-20 帧风险历史，不重启 mint 新 ID | 平均 <100-200 ms，最大 <一帧周期；超 0.5-1 s 标 stale |
| D3 资源分配 | 5-10 目标资源、2 Hz 约 0.5 Mbps；20x20 预留 1-2 Mbps | Hungarian 8x8 远低于 1 ms；工程预算 p95 <50 ms | 稳定 `global_track_id`、协方差、威胁、资源状态、D5/FOV 风险 | 至少 100 s、2 Hz、200 ticks，保留版本和迟滞状态 | 默认 2 Hz，端到端 <100-200 ms；计划超过 2-3 周期触发重评估 |
| D4 降级接管 | 心跳/摘要/bid 约 0.1-1 Mbps；不传视频；二级 cue stale 0.5-2 s | 仲裁 <50-100 ms；CBBA 每轮 <0.5 s | D1 不确定度、D2 关联风险、D3 plan age、D5 locked/hold、C2/二级健康 | 至少覆盖故障判定、接管、共识和恢复合并窗口 | health: warning 1 s、suspect 2 s、failed 4 s；CBBA round 0.5 s |
| D5 末端视觉配准 | bbox/pose/timestamp/cue metadata 约 0.1-2 Mbps；视频 cue 单独 5-50 Mbps/路 | metadata-only 5-20 Hz，单周期 <50-100 ms；真实 YOLO/MOT 需 GPU | 每帧 camera_id、K/R/t、bbox、confidence、local_track_id、双时间戳；不能在线用 truth ID | 状态缓存 1-5 s；连续 ambiguous/hold/reacquire 必须记录 | metadata latency <100-200 ms，跨相机 skew <50-100 ms |
| D6 评估指标 | 5v5 10-20 Hz 元数据日志建议 1-10 Mbps；交付率 >=99% | CPU 离线即可；单 episode 处理快于回放时长 | truth、track、assignment version、D4 event、D5 bbox/camera、D7 gate 全字段 | 多 episode，正式批量 30-100 seeds；日志覆盖接近 100% | p95 latency 小于上游 stale_after；缺字段必须显式 unavailable |
| D7 比例导引 | `GlobalTrack + Assignment + D5 bbox` 约 20-50 kB/s/pair，不传 PNG | 中段 20 Hz，末端视觉 10-30 Hz；单 pair <5 ms | 雷达航迹 10-20 Hz；D5 locked、D3 version、D4 action 一致；相机 bbox 稳定 | 至少覆盖起飞、中段、handover、末端；工程建议 >=2-3 倍预计拦截时间 | 中段 <100-200 ms；视觉 bbox 到 gate <100-200 ms，上限 0.35 s |

## 3. 主系统节点需求

### 3.1 中心节点 C2

中心节点运行 D1-D4 主循环、main episode bus、D6 在线日志聚合，并可选运行 D5 多视频检测/回放。D1-D4 的数学部分很轻，中心瓶颈来自多路视频、批量实验和长期日志。

| 指标 | 最低可运行 | 工程建议 | 对模块影响 |
| --- | --- | --- | --- |
| CPU | 8 核 x86 或同级 ARM | 16-32 核，支持实时线程和日志压缩 | D1/D2/D3/D4 都能实时；D6 批量更快 |
| GPU | 无 GPU 可跑 metadata-only | 1 块 NVIDIA L4/RTX 6000 Ada/L40S 或同级，用于多路 YOLO/MOT | 影响 D5 真实图像、D6 离线图表和视频 replay |
| 内存 | 32 GB | 64-128 GB | D2 历史、D6 批量、视频缓存 |
| 存储 | 1 TB NVMe | 4-8 TB NVMe + 冷存储 | D6 多 seed、AirSim logs、bbox/video metadata |
| 网络 | 1 GbE 内网，10-30 Mbps 无线 metadata 聚合 | 10/25 GbE 内网；无线优先 metadata，视频定向 | D1-D7 的 timestamp/plan/version 不丢 |
| 响应 | D3 2 Hz、D4 0.5 s round | C2 从接收航迹到新 plan <300 ms | D3 计划不过期；D4 主动降级少误判 |
| 可靠性 | 单中心可跑 | 主中心 + 热备或二级节点接管；UPS | D4 被动降级和恢复合并 |

建议配置：

- 研究/仿真 C2：16 核 CPU、64 GB RAM、4 TB NVMe、NVIDIA L4 或 RTX 4070/4080 级 GPU，成本约 USD 4k-12k。
- 工程 C2：32 核 CPU、128 GB RAM、8 TB NVMe、RTX 6000 Ada 或 L40S，双网口/UPS/时间同步设备，成本约 USD 15k-50k。
- 若中心只做 D1-D4 metadata，不跑多路视觉，GPU 可以降级；若要中心同时跑 5-10 路 1080p/4K 检测，GPU 是必需项。

### 3.2 地面雷达

雷达的作用是给 D1 提供全局航迹骨架，并给 D7 中段 PN 提供可预测的目标状态。雷达输出应是带时间戳、协方差、位置/速度或量测协方差的航迹，不应被当作真值。

| 指标 | 最低可运行 | 工程建议 | 对模块影响 |
| --- | --- | --- | --- |
| 更新率 | 5 Hz | 10 Hz 或更高 | D1 延迟补偿、D2 ID continuity、D7 PN |
| 角精度 | 约 1 deg | 约 0.5 deg 级 | 1 km 处 1 deg 横向误差约 17 m；影响 D5 投影门限 |
| 距离误差 | 5-10 m 可跑 coarse/stable | 1-6 m 量级，距离相关协方差 | D1 track bucket、D3 代价、D7 中段 |
| 延时 | 可补偿 0.5-2 s，但必须双时间戳 | 端到端 <100-200 ms；扫描/处理/网络分开记录 | OOSM、D3 stale、D7 追旧点 |
| 输出 | 点迹也可跑 | track、measurement、covariance、status、quality、source lineage | D1/D2/D3/D6 全部依赖 |
| 功耗 | 不作为算法约束 | 商用 C-UAS 雷达常见数十到数百 W；以供电/散热预算管理 | 影响固定站、车载或系留平台集成 |

公开对标：Echodyne EchoShield 类 4D 雷达公开资料给出 10 Hz 数据率、约 0.5 deg 方位/俯仰精度、0.75-6 m 距离性能和 <250 W 操作功耗量级。该能力足以支撑本项目 D1 coarse/stable/handover 分档，但 D5 末端锁定仍需要机载或二级光电确认。

成本：

- 单扇区 FMCW/相控阵 C-UAS 雷达：公开价格通常需询价；第三方市场资料给出的量级约 USD 30k-200k/台。
- 多面阵 360 deg 覆盖或宽域 C-UAS 系统：工程预算常进入 USD 200k-500k+。
- 本项目仿真建议先按“1 个主雷达 + 1 个可选角站/二级 EO”建模，不把 360 deg 全覆盖作为第一阶段硬约束。

### 3.3 高空系留侦察无人机/二级节点

二级节点有三类职责：

1. 健康状态下：高视角补盲、局部视频/图像 cue、ID 稳定证据和通信中继。
2. 中心节点失效时：作为覆盖区域内的二级协调节点，接管 D3/D4 局部分配。
3. 主动降级时：当中心计划因不确定度、延时或 D5 末端不一致失效时，二级节点提供更近、更高分辨率的区域态势辅助重分配。

| 指标 | 最低可运行 | 工程建议 | 对模块影响 |
| --- | --- | --- | --- |
| 高度/覆盖 | 当前 AirSim 可 50 m 测试 | 50-200 m 试验分档；实际受法规、系留长度和载荷限制 | D5 多目标视野，D4 coverage 选择 |
| 续航 | 普通电池机 30-60 min | 系留节点 24-50 h 级持续值守 | D4 二级接管、D6 长时批量 |
| 载荷 | 1 kg 级小吊舱 | 2-5 kg 载荷可覆盖 EO/IR、通信中继和计算盒 | D5 高分辨率 cue、D4 relay |
| EO/IR | 1080p 可做局部 cue | 4K/40MP EO + 640/1280 热成像 + 云台 + LRF | D5 跨视角证据、D1 EO 协方差 |
| 通信 | metadata 1-10 Mbps | 系留线 100 Mbps 或更高；无线 MANET 80-100 Mbps 级 | D4 heartbeat/bid，D5 定向视频 cue |
| 计算 | Jetson Orin Nano/NX 可跑轻检测 | Jetson AGX Orin 或 Orin NX，必要时地面端 GPU | D5 二级检测、D6 边缘日志 |
| 接管响应 | 手工或脚本触发 | 中心 failed 约 4 s 内判定，二级 heartbeat stale 2 s | D4 passive/active degradation |

公开对标：

- Elistair Orion 2.2 TE 公开资料给出 50 h 续航、100 m 系留、Heavy Lift 下 50 m 高度 5 kg 载荷、70 m 高度 4 kg 载荷、100 Mb/s 系留数据链和 <15 min 部署时间。
- DJI Matrice 400 作为非系留对标，公开规格为 59 min 飞行时间、6 kg 最大载荷、25 m/s 最大水平速度，适合说明“电池二级节点”的持续性明显弱于系留节点。
- DJI Zenmuse H30T 公开规格包含 40 MP 变焦相机、48 MP 广角、1280x1024@30fps 热成像、3-3000 m 测距和 34x 混合光学变焦，适合作为二级节点 EO/IR 吊舱参考。

成本：

- 系留二级节点整套系统：通常公开询价；工程预算约 USD 100k-300k/套，取决于系留站、飞行器、吊舱、通信和保障。
- EO/IR 吊舱：H30T 公开零售/经销商价格约 USD 9.8k-12k；更高端军警 ISR 吊舱通常询价。
- 非系留 M400/H30T 级电池平台：平台约 USD 10k-20k，H30T 约 USD 10k-12k，整套约 USD 25k-40k，不含通信中继和地面站增强。

### 3.4 拦截无人机/比例导引执行节点

拦截无人机执行 D7 中段 PN 和末端视觉 PNG，但它不分配目标、不授权、不改写 `global_track_id`。它只执行 D3/D4 当前计划，并依赖 D5 证明“相机看到的是被分配目标”。

| 指标 | 最低可运行 | 工程建议 | 对模块影响 |
| --- | --- | --- | --- |
| 飞行速度 | 高于目标速度即可测试 | 拦截机/目标速度比 >=1.5-2.0；多旋翼样机 15-25 m/s，专用平台更高 | D7 closing speed、TTC、PN 命令余量 |
| 机动能力 | D7 gate 可配置 | 软件 gate 当前按中段 60 m/s^2、0.8 rad/s，末端至少 20 m/s^2、0.9 rad/s 建模；实机需按平台重标定 | `turn_capacity`、`maneuver_margin`、视觉 PNG 是否允许 |
| 飞控 | SimpleFlight/AirSim 可跑 | Pixhawk 6X/PX4 或同类，机载 companion 只发高层速度/姿态目标 | D7 控制命令时延，D6 控制日志 |
| 相机 | 640x480 可触发 gate | 2-4 MP global shutter，60 fps，已知内外参；前移约 0.5 m 避免机架遮挡 | D5 几何配准，D7 bbox-to-LOS |
| 机载算力 | CPU 可跑 D7 gate | Jetson Orin Nano Super 可跑轻量检测；Orin NX/AGX 支持更重 YOLO/MOT | D5 本地检测、D7 实时 gate |
| 通信 | metadata 0.1-1 Mbps | MANET 10-100 Mbps，可定向接收二级 cue；控制/状态优先级高于视频 | D3/D4/D5/D7 合同一致 |
| 续航 | 5-10 min 可做短测 | 10-20 min 热备/巡逻；高性能载荷会下降 | D3 resource_state、D7 timeout |
| 起飞响应 | 冷启动 30-90 s | 热备 2-10 s；任务前上电、已定位、已建立通信 | D3 可用资源池、D4 降级保底 |

相机建议：

- 低成本接口验证：Raspberry Pi Global Shutter Camera 类 1.6 MP 全局快门，适合快速运动机器视觉样机。
- 工程视觉：Basler ace 2 或同类工业 global shutter，2-5 MP、60 fps 级，硬触发/时间戳更好。
- 不建议只依赖滚动快门消费级相机做末端 LOS-rate，因为快速机动会引入几何畸变，直接影响 D5 马氏门控和 D7 LOS-rate。

计算建议：

- D7 PN/PNG gate 本身轻量，任意 companion CPU 都能跑。
- 若本机跑 YOLOv8/ByteTrack，建议 Jetson Orin Nano Super 作为最低工程样机，Orin NX 作为稳妥方案，AGX Orin 用于二级节点或多路视频。
- Jetson Orin Nano Super 公开资料给出 67 TOPS 和 USD 249 开发套件量级；Jetson AGX Orin 64GB 公开资料给出 275 TOPS，适合高负载边缘融合。

成本：

- 研究型拦截资源：机架/动力/电池/飞控/相机/Jetson/通信，约 USD 2k-8k/架。
- 工程型拦截资源：工业相机、MANET、冗余电源、结构件和安全件，约 USD 8k-25k+/架。
- 若采用高端封装、冗余飞控、长距 MANET 和工业云台，成本会继续上升。

### 3.5 通信系统

通信系统分三层：

1. 控制与安全层：心跳、C2Health、AssignmentPlan、授权状态、资源状态，低带宽高可靠。
2. 态势元数据层：GlobalTrack、bbox、camera pose、TerminalAssociation、bid/CBBA，数 Mbps 级。
3. 视频 cue 层：二级节点定向发给小范围资源，不做全网广播。

| 链路 | 推荐承载 | 最低带宽 | 工程建议 | 主要影响模块 |
| --- | --- | --- | --- | --- |
| C2-雷达 | Track/measurement/covariance | <10 Mbps | 1 GbE 或专线，时间同步 | D1/D2/D7 |
| C2-二级节点 | heartbeat、GlobalTrack、视频 cue 控制、局部摘要 | 1-10 Mbps metadata | 系留 100 Mbps + 无线备份 | D4/D5/D6 |
| 二级-拦截机 | 区域 cue、bbox、replan、身份摘要 | 1-10 Mbps | 10-100 Mbps MANET，视频定向 | D4/D5/D7 |
| C2-拦截机 | AssignmentPlan、ResourceState、D5/D7状态 | 0.5-2 Mbps/架 | QoS，控制状态优先 | D3/D4/D7 |
| 拦截机-拦截机 | 分布式 bid、TrackSummary、ResourceSummary | 0.1-1 Mbps/架 | 低延时 MANET，丢包可观测 | D4 CBBA/拍卖 |
| 视频 replay | 离线保存或局部回传 | 可关闭 | 5-50 Mbps/路压缩视频 | D5/D6 调试 |

公开对标：

- Doodle Labs Mesh Rider 系列公开资料给出 80-100 Mbps 量级吞吐和长距 mesh 能力。
- Silvus StreamCaster 4200/4200EP 公开资料给出 100 Mbps 级吞吐，4200EP 资料还给出 7 ms average latency 条件值。
- Elistair Orion 2.2 TE 系留链路公开资料给出 100 Mb/s micro tether data transfer。

身份/安全：

- 友方正向身份可组合 Remote ID/OpenDroneID、MAVLink signing、DDS Security 和任务内白名单。
- FAA Remote ID 公开说明其广播无人机和控制站识别/位置信息；OpenDroneID 提供开源实现；MAVLink signing 提供认证但不加密；DDS Security 提供认证、访问控制和加密插件模型。
- 对 D5 的原则是：身份认证只能支持“友方已验证”，不能把未知直接推断为敌方。

## 4. 每个指标对 D1-D7 的影响

| 指标 | D1 | D2 | D3 | D4 | D5 | D6 | D7 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 雷达精度 | 决定 `a95`、协方差和 track bucket | 协方差门过大/过小影响 IDSW | 影响不确定性惩罚 | 高不确定触发主动降级 | 投影门限变宽或错位 | RMSE/track quality | 中段 PN 命令和 handover 时机 |
| 雷达延时 | OOSM/延迟补偿 | 旧量测导致错配 | stale plan 风险 | 主动降级证据 | 预测到相机平面误差 | latency/stale 统计 | 追旧点、命令饱和 |
| 通信带宽 | 观测丢失降为单源 | 漏帧和重复摘要增加 IDSW | plan age 增大 | CBBA 轮数和二级 cue stale | cross-view support 降低 | 日志缺字段 | visual_latency_high |
| 中心算力 | 多源融合实时性 | JPDA/MHT 是否可用 | replan 是否及时 | 仲裁是否及时 | 多视频检测是否可中心运行 | 批量报告吞吐 | 间接影响 gate 输入 |
| 二级节点 EO | EO cue 改善 source_support | 交叉场景辅助 ID | 视场难度成本更准 | 支持 degrade_to_secondary | 跨视角 evidence 和 hold/reacquire 消解 | terminal metrics 更完整 | D5 locked 质量提高 |
| 拦截机相机 | EO observation 可选 | 局部证据可辅助风险 | FOV cost | 末端不一致触发主动降级 | 核心输入，决定 locked/ambiguous | terminal/guidance 指标 | bbox-to-LOS 和视觉 PNG |
| 拦截机机动 | 不直接影响 | 不直接影响 | ResourceState 约束 | 低机动可触发 replan/hold | 相机是否能保持目标 | constraint violation | turn_capacity/maneuver_margin |
| 续航 | 长时航迹连续 | 避免 tracker 重启 | resource health/availability | 二级/分布式持续性 | MOT history 连续 | episode 覆盖 | timeout/abort |
| 响应时间 | 预测误差 | 关联延迟 | 迟滞和版本有效性 | 被动/主动降级窗口 | stale cue 和 timestamp skew | time_to_lock/failover | terminal_switch_allowed |

## 5. 推荐系统配置

### 5.1 5v5 AirSim/工程样机验证配置

| 节点 | 推荐配置 | 成本量级 |
| --- | --- | --- |
| 中心 C2 | 16-32 核 CPU、64-128 GB RAM、4-8 TB NVMe、NVIDIA L4/RTX 6000 Ada 级 GPU、1/10 GbE | USD 8k-35k |
| 主雷达 | EchoShield/同级 4D C-UAS radar；10 Hz、0.5 deg 级角精度、带 covariance/track 输出 | USD 80k-250k/扇区，需询价 |
| 二级系留节点 | Elistair Orion 2.2 TE/同级；50 h、100 m、4-5 kg 载荷、100 Mb/s 系留数据 | USD 100k-300k/套，需询价 |
| 二级 EO/IR | DJI H30T 级或更高端 ISR 吊舱；40MP/48MP/1280 thermal/LRF | USD 10k-12k 起，高端询价 |
| 拦截无人机 | 自研多旋翼/高速平台 + Pixhawk 6X/PX4 + Jetson Orin Nano/NX + global shutter camera + MANET | USD 5k-25k+/架 |
| MANET 通信 | Doodle Labs/Silvus/Microhard 等，metadata 优先，视频定向 | 低端数百到数千 USD/节点，高端 USD 5k-20k+/节点 |
| 时间同步 | PTP/GNSS disciplined clock 或统一系统时间源 | USD 0.5k-5k |
| 日志/评估 | C2 本地 NVMe + D6 offline report | 随 C2 配置 |

### 5.2 低成本纯算法验证配置

| 节点 | 配置 | 可验证内容 | 不可验证内容 |
| --- | --- | --- | --- |
| 单机工作站 | CPU + 普通 GPU | D1-D7 点质模型、AirSim metadata、D6 指标 | 真实多视频延时、真实无线链路 |
| AirSim ComputerVision | N 个 CV camera actor + moved actor targets | D1/D2/D3/D4/D5 metadata 流、跨视角配准 | 真实飞控、气动、相机噪声 |
| AirSim SimpleFlight | N 个拦截机 + moved actor targets | D7 PN/PNG high-level velocity loop | PX4 低层姿态/推力响应 |
| 模拟通信 | JSONL delay/drop/stale | D4 主动/被动降级、D6 latency metrics | 真实 MANET 干扰和吞吐 |

## 6. 关键部件选型建议

| 类别 | 首选 | 备选 | 选择理由 |
| --- | --- | --- | --- |
| 中心 GPU | NVIDIA L4/RTX 6000 Ada | L40S 或消费级 RTX | L4 低功耗视频推理，RTX 6000/L40S 适合多路高负载 |
| 二级边缘计算 | Jetson AGX Orin 64GB | Orin NX 16GB | AGX Orin 275 TOPS 适合多相机/二级检测；Orin NX 更省电 |
| 拦截机计算 | Jetson Orin Nano Super | Orin NX | D7 轻量，D5 若跑 YOLO/MOT 需要 Orin 级 |
| 飞控 | Pixhawk 6X/PX4 | 同级 ArduPilot/PX4 控制器 | 成熟、日志完整、便于 future ROS/MAVLink 接入 |
| 拦截机相机 | 2-5 MP global shutter 工业相机 | Raspberry Pi Global Shutter 快速样机 | 减少快速运动畸变，提升 D5/D7 LOS 稳定 |
| 二级吊舱 | DJI H30T 级 EO/IR | 更高端 ISR 吊舱 | 支持高分辨率广角/变焦/热成像/LRF，一体化成本低 |
| 主雷达 | EchoShield/同级 4D C-UAS radar | EchoGuard/Robin/Fortem 类 | 公开能力接近 D1/D7 对 10 Hz、0.5 deg 的需求 |
| MANET | Doodle Labs 或 Silvus | Microhard 等 | 80-100 Mbps 级足够 metadata 和定向视频 cue |
| 身份认证 | Remote ID/OpenDroneID + MAVLink signing + DDS Security | AprilTag 近距辅助 | D5 需要正向友方确认，未知不能自动升级 |

## 7. 成本汇总

| 系统层 | 低成本验证 | 工程样机 | 成本不确定性 |
| --- | ---:| ---:| --- |
| 中心节点 | USD 4k-12k | USD 15k-50k | GPU、机架、UPS、时间同步 |
| 主雷达 | 可用仿真替代 | USD 80k-250k/扇区 | 多数 C-UAS 雷达需询价；360 deg 覆盖更高 |
| 二级系留节点 | 可用 CV 高空相机替代 | USD 100k-300k/套 | 飞行器、系留站、载荷、保障 |
| 二级 EO/IR | USD 10k-12k | USD 10k-100k+ | H30T 公开价低，高端 ISR 询价 |
| 拦截无人机单机 | USD 2k-8k | USD 8k-25k+ | 速度、续航、MANET、工业相机 |
| MANET 单节点 | USD 0.5k-3k | USD 5k-20k+ | 认证、加密、频段、功率、天线 |
| 标定/时间同步 | USD 0.5k-2k | USD 2k-10k | 多相机几何和 PTP/GNSS |
| 软件/集成 | 项目内开发 | 可能高于硬件小项 | 标定、日志、测试和安全流程是主要工时 |

5v5 工程样机粗预算：

- 仅算法 + AirSim + 单机 C2：USD 5k-15k。
- 加 5 架研究拦截机、无真实雷达、无系留：USD 30k-120k。
- 加 1 台 C-UAS 雷达、1 套二级系留节点、5 架工程拦截机和 MANET：USD 300k-900k+。

该预算不含场地、合规、保险、维护、备件、人员和安全审批。

## 8. 对当前项目的落地建议

### P1: 继续仿真但补齐工程约束字段

1. main runtime bus 每个 episode 记录 `resource_battery_or_endurance_state`、`compute_latency_ms`、`link_latency_ms`、`delivered/drop/stale`。
2. D1 输出雷达距离相关协方差、`measurement_latency_s` 和 `a95_xy_m`。
3. D3 cost 加入资源续航/机动余量字段，不只看几何距离。
4. D4 主动降级阈值继续使用 D1/D2/D3/D5 风险摘要，并记录是“中心误差大”还是“末端不一致”触发。
5. D5 继续坚持 metadata-first；真实图像接入后必须保存相机 K/R/t、曝光时间和 bbox 置信度，不在线用 AirSim truth ID。
6. D7 把平台实测 `max_turn_rate/max_lateral_accel/current_speed` 作为配置输入，不能固定使用仿真理想值。

### P2: 工程样机前的最小采购/搭建路径

1. 先用一台工作站 + Jetson Orin Nano/NX + global shutter camera 做 D5/D7 视觉 PNG bench。
2. 再接入一台二级高位相机或非系留 M400/H30T 级平台，验证跨视角 cue 和 D4 主动降级。
3. 最后再接入 C-UAS 雷达或雷达模拟器硬件输出，验证 D1 雷达协方差、D2 ID continuity 和 D7 中段 PN。

## 9. 公开资料来源

- Elistair Orion 2.2 TE leaflet: <https://elistair.com/wp-content/uploads/2021/02/ORION_2_Leaflet.pdf>
- Echodyne EchoShield product/spec sources: <https://www.echodyne.com/radar-systems/echoshield>, <https://www.defenseadvancement.com/company/echodyne/echoshield-radar/>
- DJI Zenmuse H30 Series specs: <https://enterprise.dji.com/zenmuse-h30-series/specs>
- DJI Matrice 400 specs: <https://enterprise.dji.com/matrice-400/specs>
- NVIDIA Jetson Orin official specs: <https://www.nvidia.com/en-us/autonomous-machines/embedded-systems/jetson-orin/>
- NVIDIA Jetson Orin Nano Super: <https://www.nvidia.com/en-us/autonomous-machines/embedded-systems/jetson-orin/nano-super-developer-kit/>
- NVIDIA RTX 6000 Ada: <https://www.nvidia.com/en-us/products/workstations/rtx-6000/>
- NVIDIA L40S: <https://www.nvidia.com/en-us/data-center/l40s/>
- NVIDIA L4: <https://www.nvidia.com/en-us/data-center/l4/>
- Doodle Labs Mesh Rider products: <https://doodlelabs.com/products/>
- Silvus StreamCaster 4200EP datasheet: <https://silvustechnologies.com/wp-content/uploads/2026/01/StreamCaster-4200-SC4200EP-Enhanced-Plus-Datasheet.pdf>
- Holybro Pixhawk 6X: <https://holybro.com/products/pixhawk-6x>
- Raspberry Pi Global Shutter Camera: <https://www.raspberrypi.com/products/raspberry-pi-global-shutter-camera/>
- Basler ace 2: <https://www.baslerweb.com/en-us/cameras/ace2/>
- FAA Remote ID: <https://www.faa.gov/uas/getting_started/remote_id>
- OpenDroneID Core: <https://github.com/opendroneid/opendroneid-core-c>
- MAVLink message signing: <https://mavlink.io/en/guide/message_signing.html>
- DDS Security: <https://www.omg.org/spec/DDS-SECURITY/1.2/About-DDS-SECURITY>
- Radar price range reference: <https://www.airsight.com/blog/drone-detection-radar-guide>
- DJI H30T retail references: <https://www.dronenerds.com/collections/dji-h30-series-enterprise-sensors>, <https://www.dronefly.com/collections/dji-zenmuse-h30t-cameras>
