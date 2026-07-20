# D1 M 对 N 多无人机协同定位与观测级融合调研

**日期**：2026-07-11

**范围**：D1 多传感器融合；包含文献/开源审计与 2026-07-11 中心化 P1 数值基础状态，不包含 AirSim 运行或分布式全链路。

**问题**：当一个高威胁目标由 3 架拦截/侦察无人机共同观测时，如何把异步测角、测距和局部航迹融合为带一致协方差的中心 `GlobalTrack`。

## 0. 2026-07-15 M5N2 证据增量

main 已完成真实 AirSim M5N2 baseline/candidate 各 10 case，共 20 case。该批确认在线
identity/state truth use 均为 0，并保持 D1 双时间戳、covariance 和 NED 合同；但实验目标是
终端闭环与时序，不是协同定位精度标定。其 3,805 个 main-bus tick 中 D1 fusion
mean/P95/max=`320.00/451.46/1234.88 ms`，表明多观测/多航迹融合的实时性仍是 P1。

本批没有可用 NIS、NEES、RMSE、交会角/条件数分档或按 observer 数量拆分的协同定位指标，
因此不能用 20-case 结果声称 `2..N` bearing-ray WLS、协方差交集或节点退出链路已完成真实
AirSim 验收。TERM 前额外完成的 1 个 `png_ttc_2v2_seed001` 已排除，dropout 完成数为 0。
后续 M-to-N 协同定位仍需独立冻结多 observer 观测、平台位姿/外参及其 covariance，并按
几何质量和 observer 退出模式报告 availability 与误差；不得使用 actor/truth ID 做在线配准。

## 1. 结论摘要

1. **三机不要求严格同时观测**。对运动目标，所有观测必须按 `measurement_timestamp` 和平台在该时刻的位姿，传播到同一估计时刻后再融合。同步观测能减小运动模型误差，但“同时到达拦截点”是 D3/D7 的任务调度与协同导引问题，不是 D1 定位成立的必要条件。
2. **两条不平行视线在理想标定下即可三角定位，第三架提供冗余而不是自动保证精度**。3 条视线仍可能近似平行、基线过短或同时受偏置污染。应以联合观测雅可比/Fisher 信息矩阵的秩与条件数、交会角和传播后协方差判断几何质量，不能以“观测平台数量=3”代替可观测性检查。
3. **集中获得原始观测时，优先做观测级联合滤波**。中心掌握测量模型、位姿协方差和 source lineage 时，EKF/UKF/信息滤波是成熟基线。只有节点只能上传局部航迹或中心/二级节点不可用时，才进入 Track-to-Track 融合。
4. **未知公共信息相关性必须保守处理**。多机航迹可能共享中心先验、雷达 cue、同一标定源或经 relay 重复转发。若不能维护交叉协方差，不能直接按独立高斯相乘；Covariance Intersection（CI）或保守混合是可插拔基线，同时必须保留 source lineage。
5. **D1 已实现依赖轻的中心化 P1 数值基础，但未实现分布式全链路**。新增 typed cooperative DTO/summary、2..N bearing-ray WLS、几何/时间/covariance 保守门控、共同估计时刻传播和 NumPy CI；D2 跨平台关联、`FusionAdapter` 默认接线、AirSim 多 seed replay、部分共享 lineage 与分布式共识仍是缺口。

## 2. 问题定义与最小数学条件

目标状态保持为：

```text
x(t) = [px, py, pz, vx, vy, vz]^T,  frame = NED
```

第 `i` 架无人机在测量时刻 `t_i` 的位置、姿态和外参为 `s_i(t_i)`、`R_i(t_i)`、`T_body_camera_i`。纯方位观测可写为：

```text
z_i = h_i(x(t_i), s_i(t_i), R_i(t_i), T_body_camera_i) + v_i
v_i ~ N(0, R_bearing_i)
```

将各观测按运动模型传播到共同估计时刻 `t_f` 后，局部可观测性由联合雅可比决定：

```text
H = [H_1; H_2; H_3]
I(x) = H^T R^-1 H
```

仅有“3 个观测”不足以保证有效定位。工程上至少检查：

- 与待估位置维度对应的联合信息矩阵具有足够秩；
- 视线交会角不接近 0 或 180 度，且基线与目标距离之比不能过小；
- `I(x)` 的条件数、三角化深度和重投影残差在标定阈值内；
- 平台位置、姿态、相机/阵列外参及其协方差在 `t_i` 有效；
- 目标在时间偏差内的位移误差 `||v_rel|| * |delta_t|` 不超过定位误差预算；
- 各观测的 native covariance、时间戳不确定性和平台位姿协方差均进入传播，而不是只使用像素/方位噪声。

### 2.1 三架无人机共同定位的必要输入

| 条件 | 最小输入 | 缺失后果 |
| --- | --- | --- |
| 几何 | 每个平台 NED 位姿、传感器外参、方位/测距观测、相机内参 | 只能得到未标定视线或错误交会点 |
| 时间 | `measurement_timestamp`、`arrival_timestamp`、时钟不确定性、平台位姿历史 | 高动态目标被错误地当作同一时刻，产生系统偏差 |
| 不确定性 | 观测、平台位置/姿态、外参、传播过程噪声的 covariance | 输出虚假收敛，D3/D5 门限过窄 |
| 身份 | `sensor_id`、observation/sequence ID、source/relay lineage、D2 关联结果 | 把不同目标误融合或把同一 payload 重复计数 |
| 运动模型 | CV/CA/CT/IMM 候选和共同估计时刻 | 序贯观测的传播误差无法量化 |

### 2.2 同时、序贯与混合观测

- **近同时观测**：适合高动态末端和 bearing-only 三角定位，模型传播短，几何解释直接；代价是同步、通信和共同可见性要求高。
- **序贯观测**：适合视场不同、通信异步或分批观测；必须保留双时间戳、位姿历史并做 OOSM/固定时滞重传播，目标机动越强，过程噪声和结果协方差越大。
- **混合观测**：推荐工程默认。雷达/二级侦察节点给连续粗航迹，多架拦截机在可见窗口提供近同时方位或像素约束；缺失节点不阻断融合，但会降低几何质量和 `handover_readiness`。

因此，D1 不要求三架拦截机严格同时到达。D1 应输出共同估计时刻的状态、协方差和几何质量；D3/D7 再决定是同步到达、分波次到达还是保留备份资源。

## 3. 文献审计

检索以 2015-2026 为主，并保留未知相关性融合的基础路线。Google Scholar 仅用于发现候选；本表引用 DOI、arXiv 或出版社原始页。当前环境无 Web of Science 订阅/API，因此未把 WOS 收录状态或引文统计作为证据。

| 年份 | 文献与原始来源 | 核心问题/方法 | 架构 | 时间方式 | 验证与对 D1 的启示 |
| --- | --- | --- | --- | --- | --- |
| 2024 | Qian 等，[A Maneuvering Target Tracking Algorithm Based on Cooperative Localization of Multi-UAVs With Bearing-Only Measurements](https://doi.org/10.1109/TIM.2024.3382741) | 多 UAV 纯方位机动目标定位；IMM、按平台定位/测量能力构造 belief factor、轨迹平滑和转率识别 | 协同融合，摘要未证明完全分布式 | 连续/序贯 | 数值仿真；说明协同定位仍需机动模型和按平台质量加权，不能只做静态三角化 |
| 2022 | Doostmohammadian 等，[Distributed Estimation Approach for Tracking a Mobile Target via Formation of UAVs](https://doi.org/10.1109/TASE.2021.3135834) | UAV 共享 TOA/TDOA 与目标估计，单时间尺度分布式估计，只要求全局可观测与强连通 | 分布式 | 同采样尺度连续更新 | 仿真；为低通信分布式估计提供研究路线，但观测类型和 MSM 相机/雷达合同仍需适配 |
| 2015 | Oh 等，[Coordinated standoff tracking of moving target groups using multiple UAVs](https://doi.org/10.1109/TAES.2015.140044) | 多 UAV 变半径盘旋、目标群分配和局部重规划，并分析 UAV 角分离与定位敏感度 | 中心分配+局部协同 | 连续/混合 | 数值仿真；直接支持“角分离和感知配置决定定位质量”，平台多不等于几何好 |
| 2019 | Lyu 等，[Unscented Transformation-Based Multi-Robot Collaborative Self-Localization and Distributed Target Tracking](https://doi.org/10.3390/app9050903) | 联合机器人自定位和目标跟踪；近似 inter-robot 相关性，以 CI 保守丢弃 robot-target 相关性；异步多类观测 | 分布式 | 异步/混合 | 仿真和四旋翼实验；最贴近 MSM 的位姿不确定性、异步观测与未知相关性组合 |
| 2023 | Wang 等，[Optimal Geometry and Motion Coordination for Multisensor Target Tracking with Bearings-Only Measurements](https://doi.org/10.3390/s23146408) | 纯方位多传感器跟踪的最优几何和运动协调 | 集中几何优化 | 连续/近同时 | 仿真；支持用信息/协方差指标调平台几何，而非固定“三机三角形”规则 |
| 2019 | Yang 等，[A Sequential Two-Stage Track-to-Track Association Method in Asynchronous Bearings-Only Sensor Networks](https://doi.org/10.3390/s19143185) | 异步纯方位传感器网络中的序贯两阶段 Track-to-Track 关联 | 多传感器航迹级 | 序贯/异步 | 仿真；证明先解决跨节点航迹关联再融合，身份归 D2、数值融合归 D1 |
| 2017 | Abu Bakr 与 Lee，[Distributed Multisensor Data Fusion under Unknown Correlation and Data Inconsistency](https://doi.org/10.3390/s17112472) | 未知交叉相关和数据不一致下的分布式保守融合 | 分布式 | 序贯/混合 | 数值场景；支持 CI 类方法用于交叉协方差未知，而不是假定节点估计独立 |
| 2023 | Di Gennaro 与 Waldmann，[Sensor Fusion with Asynchronous Decentralized Processing for 3D Target Tracking with a Wireless Camera Network](https://doi.org/10.3390/s23031194) | 无线相机网络的异步、去中心化三维跟踪 | 去中心化 | 异步/序贯 | 相机网络仿真/实验性处理；支持每相机时间化位姿和异步融合，不要求严格同帧 |
| 2020 | Li 等，[Distributed multi-sensor multi-view fusion based on generalized covariance intersection](https://doi.org/10.1016/j.sigpro.2019.107246) | 不同节点/视角后验的广义 CI 融合，处理公共信息未知 | 分布式 | 序贯共识/混合 | 数值仿真；属于多目标/多视角升级项，不是简单 EKF 默认替代 |
| 2016 | Wang 等，[Distributed Fusion With Multi-Bernoulli Filter Based on Generalized Covariance Intersection](https://doi.org/10.1109/TSP.2016.2617825)，[arXiv](https://arxiv.org/abs/1603.08340) | GCI 融合多 Bernoulli 后验并用近似保持可继续融合 | 分布式 | 序贯节点融合 | 数值仿真；适用于多目标 RFS，复杂度和状态表达超出当前 D1 单高斯主线 |
| 2018 | Li 等，[Partial Consensus and Conservative Fusion of Gaussian Mixtures](https://doi.org/10.1109/TAES.2018.2882960)，[arXiv](https://arxiv.org/abs/1711.10783) | 仅交换高权 Gaussian components，并做保守混合/约简 | 分布式 | 部分共识/序贯 | 多传感器仿真；为受限带宽提供研究路线，但需要 D2 多目标关联和 mixture 合同 |
| 2022 | Wang 等，[Target localization and encirclement control for multi-UAVs with limited information](https://doi.org/10.1049/cth2.12314) | 每架 UAV 只获得目标方位，分布式估计目标并形成环绕队形 | 分布式 | 连续/混合 | 数值仿真；说明定位与平台运动耦合，但其控制律不属于 D1 实施范围 |

### 3.1 文献证据的边界

- 这些论文支持“可行算法路线”，不等于存在适配 MSM 的成熟端到端实现。
- 多数工作使用仿真或受控实验，未同时覆盖 AirSim、雷达+声学+EO、中心/二级/无中心切换及中心规范 `global_track_id`。
- 同时到达、分批拦截和多资源分配不由上述定位论文直接解决；D1 只能提供到达调度所需的预测状态及协方差。

## 4. 开源代码审计

维护状态按 2026-07-11 官方仓库和发布页核查。

| 项目 | 可复用能力 | 许可证/维护状态 | 适配难点 | 定位 |
| --- | --- | --- | --- | --- |
| [Stone Soup](https://github.com/dstl/Stone-Soup) | EKF/UKF/信息滤波、网络/信息架构、Track-to-Track 示例、`ChernoffUpdater`/CI 类融合、指标 | MIT；未归档；官方最新 release `v1.9.1`（2026-06-24） | 需要把 `SensorObservation`/`GlobalTrack` 转换为其 Detection/Track；其示例不能替代 MSM 的 D2 身份治理和 source lineage | **成熟开源研究框架，可插拔升级** |
| [FilterPy](https://github.com/rlabbe/filterpy) | EKF、UKF、IMM、Information Filter、fixed-lag smoother 原型 | MIT；未归档，但默认分支最近提交为 2022-08，维护活跃度较低 | 无多目标航迹管理、跨节点相关性和 Track-to-Track CI；适合数值原型，不适合直接承担协同系统 | **成熟教学/原型库** |
| [GTSAM](https://github.com/borglab/gtsam) | BearingFactor、TriangulationFactor、SmartProjection、增量因子图和 Python/C++ 接口 | simplified BSD；活跃维护 | 需要自行建立动态目标、平台位姿、时钟偏差和数据关联因子；不是现成目标跟踪/C2 框架 | **几何/平滑可插拔升级** |
| [OpenCV](https://github.com/opencv/opencv) | calibration、`triangulatePoints`、`solvePnP`、投影与重投影工具 | Apache-2.0；活跃维护 | `triangulatePoints` 只给几何点，不自动传播平台/像素/时间协方差，也不处理目标运动和公共信息 | **成熟几何基元，不能单独作为融合器** |

### 4.1 开源实现结论

- **成熟默认**：OpenCV/GTSAM 提供标定、视线和三角化基元；FilterPy/Stone Soup 提供滤波原型。它们可降低实现成本，但必须由 MSM 合同约束时间、坐标、协方差和身份。
- **可插拔升级**：Stone Soup Track Fusion/CI、GTSAM 动态因子图。先离线 benchmark，再决定是否进入主线。
- **研究方案**：GCI-RFS、部分共识 Gaussian mixture、分布式单时间尺度估计和主动几何优化。
- **无成熟开源端到端方案**：尚未发现一个维护良好的仓库能直接完成“三架 UAV 异步观测同一机动目标 + 位姿/时间协方差 + 中心/二级/无中心切换 + MSM `global_track_id`”全链路。

## 5. D1 与 D2 的责任边界

多平台协同定位容易把“融合”和“关联”混成一个模块。本项目采用下列边界：

| 阶段 | D1 责任 | D2 责任 |
| --- | --- | --- |
| 原始观测接入 | 坐标/时间标准化、位姿与观测协方差传播、OOSM、source lineage | 不负责传感器标定和坐标转换 |
| 观测门控 | 提供创新、NIS、几何质量和候选似然 | 决定观测/局部航迹属于哪个中心目标，维护关联假设 |
| 多平台同目标融合 | 在 D2 已确认同一 canonical target 的前提下做联合 EKF/UKF/信息融合或 CI 数值更新 | 维护 local-track-to-`global_track_id` 映射、ID continuity 和 `id_switch_count` |
| Track-to-Track | 处理状态、协方差、交叉相关未知和 source lineage 的数值融合 | 先做 Track-to-Track association，拒绝不同目标误融合 |
| 身份治理 | 不新建局部替代身份，不因几何交会自行改写 canonical ID | 中心拥有并稳定 `global_track_id`；truth ID 只供离线评估 |

在当前 D1→D2 运行顺序下，D1 继续发布候选 `GlobalTrack` 及观测 lineage，D2 稳定规范身份。若未来接入多个二级节点的局部 TrackSummary，新增跨模块流程应是：

```text
D1 标准化 local TrackSummary
-> D2 local-to-global 关联/身份确认
-> D1 对已确认同目标状态做 CI/保守数值融合
-> D2 发布稳定 canonical GlobalTrack 视图
```

其中 D1 的同 canonical ID 数值 CI helper 已实现；D2 local-to-global 关联和上述双阶段 runtime 流程仍未接线。

## 6. 对 M 对 N 协同拦截的影响

当一个高威胁目标需要 3 架无人机时，D1 应把三架平台视为可动态加入/退出的传感器集合，而不是三个独立目标：

- 三架都观测到目标时，报告 `observer_count=3`、几何质量和融合协方差；不能把合法多机支持记作 duplicate assignment。
- 只有两架具备良好交会角时，可以继续定位并提高协方差；第三架可机动改善几何、提供身份/遮挡冗余。
- 只有单架纯方位且没有可靠距离/先验时，不输出虚假三维精确点，只维持 bearing constraint 和放大的协方差。
- 分批拦截时，先到平台的观测可改善后续资源的共同 `GlobalTrack`；退出或失联平台的旧信息必须按 source lineage 和 freshness 老化。
- 多机通信不能把同一中心航迹预测作为三份独立证据再次融合。共享先验导致的相关性应保留交叉协方差；未知时使用 CI。

## 7. 本项目状态与 P1 拆解

### 已实现

- `measurement_timestamp` 与 `arrival_timestamp`；
- NED 六维状态和观测/航迹 covariance；
- fixed-lag/OOSM replay、timestamp uncertainty 和 sensor health；
- radar/acoustic/EO 观测模型、source lineage de-dup；
- `TrackUncertaintySummary`、区域窗口和 recon cue；
- governed replay 与 truth-isolated D1→D2→D3 main episode-bus 合同已进入 10-seed P1 验证。
- cooperative typed DTO/summary，包含 canonical ID、observer lineage、平台位姿/外参 covariance、双时间戳和共同估计时刻；
- 2..N bearing-ray weighted least squares，输出 LOS 交会角、信息 rank/condition、残差和 geometry reason，并对短基线、近共线、超时差及 covariance 缺失保守拒绝/膨胀；
- 1..N state 的 NumPy Covariance Intersection，共同时间 CV 传播、process/timing covariance 和 message UUID/完整 lineage 去重。

### P1 缺口

1. **协同几何质量合同已完成 D1-owned 基础**：上述字段均由 `CooperativeLocalizationSummary` 输出；尚未进入默认 `FusionAdapter`/main bus。
2. **三机异步构造测试已完成，真实 replay 未完成**：已覆盖 1/2/3/N、良好三视角、退化几何和 0.4 s skew；仍需 near-synchronous/range、不同基线/距离、机动/遮挡/失联和 AirSim 多 seed RMSE/NIS/NEES consistency。
3. **D1/D2 跨平台关联合同**：需要明确 local TrackSummary、association confidence、canonical `global_track_id` 和拒绝误融合事件；D1 不自行重绑定身份。
4. **保守 Track-to-Track 数值原型已完成**：已验证 relay/message/完整 lineage duplicate 不重复收敛，CI 不比错误独立融合更自信；shared-prior 部分 lineage、成员退出 replay、D2/runtime adapter 和分布式共识仍待补。
5. **开源离线 benchmark**：Stone Soup CI、GTSAM/OpenCV triangulation 只作为对照；正式外部库接入继续后置，不改变当前 NumPy fallback。

当前无新增 P0 blocker。上述能力是 M 对 N 协同定位的 P1 研究与验证项；现有双时间戳、NED、covariance、source lineage 和 canonical ID 禁止改写规则继续作为硬回归。

## 8. 建议验收口径

- 几何良好时，三机融合的 RMSE 和 95% consistency 不劣于最佳双机组合；几何退化时必须增大 covariance 或拒绝三角化。
- 同一观测经 relay 重发不改变 posterior；共享先验但交叉协方差未知时，CI 输出不得比错误独立融合更自信。
- 序贯观测按共同估计时刻传播后，报告 measurement skew、propagation horizon 和 covariance growth。
- D2 关联不确定或候选冲突时，D1 输出 hold/不融合，不创建替代 `global_track_id`。
- 成员从 3 降到 2/1 时保持航迹连续，并显式降低 observer diversity/geometric quality。
- 所有真值只进入离线 RMSE/NEES/IDSW 评分，在线融合和关联日志不含 actor/truth ID。

## 9. 来源统计与访问限制

- 主要论文：12 篇，年份覆盖 2015-2024；均提供 DOI，开放版本存在时同时给出 arXiv。
- 官方开源候选：4 个；许可证和维护状态来自官方 GitHub 仓库/发布页。
- Google Scholar：仅用于发现，不作为最终证据。
- Web of Science：当前无订阅/API 权限，未声称完成 WOS 引文或收录核验。

## 10. 最新系统证据与定位（2026-07-11 最终验证）

最终验证的 ComputerVision 10-seed batch 中，T001 双 primary 合同达到 8/10 验收阈值；
二级和完全分布式 3/3 ACK commit 正例通过，缺 ACK 的 2/3 case abort 并 fail-closed。
main episode bus 同时写出 D1 governed replay，在线记录不含 truth/actor/object identity，
truth 只进入独立离线评分标签。因此 D1 的 P1 合同层和 truth 隔离不再是未完成项。

这些结果仍不是本调研中的三机协同定位精度验证。SimpleFlight 15 s 诊断的 30 个 active
pair 均未物理命中，不能用于关闭协同定位或物理拦截。D1 typed DTO、bearing WLS 和 CI
数值基础已完成，但 D2-confirmed runtime adapter、真实多 seed 三机机动/遮挡/成员退出
replay 和 RMSE/NIS/NEES consistency 仍需验证。P2 只做隔离 benchmark，不替换 NumPy
默认路径。

## 11. Scalable 3D 声学方位接口补充（2026-07-20）

新三维质点总线的单个声学节点输出匿名 `[azimuth,elevation]`、`2x2` covariance、双时间戳、
节点 NED 位置和类别级 soundprint 概率。D1 将其映射为 `acoustic_3d` bearing-only 约束：只能
更新已有 radar `GlobalTrack`，没有距离/多视角几何时不单独 birth。`soundprint_is_identity`
必须为 `False`，类别向量不参与跨节点同目标确认，也不创建或改写 `global_track_id`。

2026-07-20 构造回归中，单声学 scan 的 5 条观测在无 radar 先验时产生 0 条航迹，在 5 条
radar 先验存在时更新 5/5 且 ID 集不变。该结果只关闭输入适配和保守单节点更新合同，不关闭
本评审的 M 对 N 协同定位 GAP：跨声学节点 bearing 分组仍需 D2-confirmed identity，几何定位
仍需 WLS/CI 的 observer lineage、基线/交会角和多 seed RMSE/NIS/NEES 验收。
