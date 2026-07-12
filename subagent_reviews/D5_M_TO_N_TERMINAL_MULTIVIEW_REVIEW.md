# D5 M 对 N 末端多视角配准与协同定位调研

**调研日期**：2026-07-11

**范围**：多拦截器共同观测同一 `global_track_id`、跨视角投影、三角定位、相对位姿与时间同步、多视角 MOT、遮挡与小目标，以及计划内多机锁定与错误重复锁定。

**边界**：本文包含文献/开源审计与 D5 模块内合同实现状态。D5 不分配目标，不创建、不改写、不换绑 `global_track_id`；AirSim actor/object truth ID 只能用于离线评分。

## 1. 核心结论

1. **多机协同定位可行，但不能直接平均 bbox 中心。** 每个相机必须提供双时间戳、内参、畸变、量测时刻外参及其协方差。至少两个视角还需具备足够基线和交会角，才能用带权射线交会、三角化或多视图贝叶斯滤波得到目标位置及协方差。
2. **同步观测适合瞬时三角定位，序贯观测必须做运动补偿。** 分批到达的帧不能冒充同步帧，必须把目标和相机状态预测到共同参考时刻，并按时延、机动和外参误差膨胀协方差。
3. **本地 MOT 与跨相机身份是两层问题。** ByteTrack、BoT-SORT 只维护单相机 `local_track_id`；跨相机仍需 GlobalTrack 投影、几何、时间、外观和计划绑定。
4. **M 对 N 下，多资源共同锁定同一目标不必然是 duplicate。** 若同一有效计划明确 `k_j=3`，三名联盟成员分别锁定同一 `global_track_id`，这是计划内协同支持。计划外资源加入、单资源多本地锁定、单一本地轨迹支持多个全局目标或使用过期计划，才是重复/冲突风险。
5. **当前 D5 主线可保留。** `GlobalTrack -> CameraModel -> image projection -> LocalVisualTrack -> TerminalAssociation` 仍是成熟、可解释的默认路线。需要新增“读取联盟合同后解释多锁定”，而不是让 D5 重新分配。
6. **没有成熟的单一开源完整栈。** 几何、单相机 MOT、多视图跟踪和无人机群相对定位均有候选实现，但仍需 MSM 自己组合时空合同、协方差、安全门控和联盟约束。

## 2. 统一问题定义

设目标 `j` 的中心航迹为 `G_j=(global_track_id, x_j, P_j, t_j)`，D3/D4 给出目标需求和合法联盟：

```text
Coalition_j = {
  coalition_id,
  coalition_version,
  global_track_id,
  required_resource_count = k_j,
  members = [{resource_id, member_role, wave_id, arrival_window}],
  plan_id,
  plan_version,
  coordination_mode,     # simultaneous | sequential | hybrid
}
```

D5 只回答：本地轨迹是否支持**已分配的** `G_j`；多个相机的证据是否一致并能否改善定位；多个 `locked` 是计划内支持还是错误重复；证据不足时输出 `ambiguous/hold/reacquire`。D5 不猜测新身份，不改变联盟或分配。

## 3. 同时、序贯和混合观测

| 模式 | D5 处理 | 优点 | 风险与适用条件 |
|---|---|---|---|
| 同时/窄时间窗 | 各 bearing 和位姿对齐到共同量测时刻，做带权三角化或联合门控 | 瞬时几何约束强 | 要求足够交会角；时钟、滚动快门和外参偏差会形成伪交点 |
| 序贯/分批 | 将 GlobalTrack、相机位姿和历史 bearing 预测到统一时刻，再做 OOSM/轨迹级更新 | 允许遮挡、通信延迟和不同波次 | 高动态下模型误差快速增长；必须保留双时间戳并膨胀协方差 |
| 混合 | 同步观测形成主定位，异步观测维护连续性和交叉验证 | 兼顾精度和覆盖 | 公共先验可能被重复融合；分布式条件需保守处理相关性 |

D5 不决定三架拦截器同时到达还是分批到达。D3/D4提供 `coordination_mode`、成员 `wave_id` 和 arrival window，D7负责导引。D5只按时间槽验证视觉证据：同时模式要求同一同步窗口支持；序贯模式允许分槽锁定，但历史锁定不得计为当前同步三角化支持。

## 4. 协同定位方法

对相机 `c` 的像素观测去畸变后，由 `K_c` 和量测时刻外参得到世界系单位视线 `b_c`：

```text
p_target = o_c + lambda_c * b_c
```

两个以上视角以带权最小二乘求射线最近交点。权重至少包含像素协方差、相机位置/姿态协方差、GlobalTrack预测协方差、measurement/arrival latency、遮挡、尺度、运动模糊和标定健康度。协方差由雅可比、UKF或 Monte Carlo传播验证。射线近似平行、基线过短、重投影误差过大或时间窗不一致时，只保留 bearing/support evidence，不得输出虚假高置信三维定位。

完全分布式时，peer 交换命名空间化 tracklet summary：

```text
(resource_id, camera_id, local_track_id,
 measurement_timestamp, arrival_timestamp,
 bearing, covariance, bbox_area_history, bearing_rate,
 camera_pose, camera_pose_covariance,
 assigned_global_track_id, plan_id, plan_version)
```

像素位置和 bbox 尺度历史适合做一致性与候选排除，但单目尺度有深度歧义，不能单独证明同一目标。缺少有效中心拥有 ID 时，D5仍只输出 `CrossPeerAssociationHypothesis`/`hypothesis_only/hold`，不得创建替代性全局 ID。

## 5. 合法协同锁定与错误 duplicate

### 5.1 `planned_cooperative_lock`

以下条件同时满足时，多架无人机的 `locked` 是计划内协同支持：

- 都属于同一 `coalition_id` 的合法成员；
- `plan_id/version` 有效且 `k_j>1`；
- 每个资源只提交相机命名空间内唯一的本地轨迹支持；
- 所有支持均指向同一中心拥有 `global_track_id`；
- 支持满足到达槽、时效、几何和稳定窗口；
- 没有友方冲突、身份伪造疑点或 local-to-global 多重绑定。

支持数超过 `k_j` 时，D5只报告 `over_support`，由 D3/D4决定备用、轮换或解除资源。

### 5.2 错误重复/冲突

以下情况仍应产生 duplicate/conflict evidence：计划外资源加入；同一资源多个本地轨迹同时锁定同一目标；同一本地轨迹支持多个 `global_track_id`；stale/mismatched plan；一对一计划出现多个 active lock；几何不一致或友方身份重叠。

```text
duplicate_risk = observed_lock_set - authorized_coalition_lock_set != empty
                 or local_to_global_conflict
                 or per_resource_multi_local_conflict
```

因此不能再把“同一 `global_track_id` 的 locked resource 数量大于 1”作为 M 对 N 场景的充分判据。

## 6. 主要论文证据

| 年份 | 论文与原始来源 | 问题 | 中心/分布式 | 同时/序贯/混合 | 验证/代码与 D5 适用性 |
|---|---|---|---|---|---|
| 2017 | Liu et al., *Multi-camera Multi-Object Tracking*, [arXiv:1709.07065](https://arxiv.org/abs/1709.07065) | 跨相机、跨帧联合图关联 | 中心式 | 混合 | 多相机数据验证；说明外观和运动需联合，不能直接合并 local ID |
| 2018 | Chavdarova et al., *WILDTRACK*, [DOI](https://doi.org/10.1109/CVPR.2018.00528), [arXiv](https://arxiv.org/abs/1707.09299) | 七台同步标定相机的遮挡与联合检测 | 中心式 | 同时 | 真实同步 HD 数据和标定；成熟基准，但与机动空中小目标有域差异 |
| 2019 | Tang et al., *CityFlow*, [DOI](https://doi.org/10.1109/CVPR.2019.00900), [arXiv](https://arxiv.org/abs/1903.09254) | 大范围 MTMC 和 ReID | 中心式 | 序贯/混合 | 40相机同步视频和几何；支撑时空约束，车辆纹理条件优于小无人机 |
| 2020 | Hou et al., *MVDet*, [DOI](https://doi.org/10.1007/978-3-030-58571-6_1), [arXiv](https://arxiv.org/abs/2007.07247) | 多视图特征投影到地平面 | 中心式 | 同时 | WILDTRACK/MultiviewX；[代码](https://github.com/hou-yz/MVDet)。固定地平面不能直接套用三维空中目标 |
| 2021/2022 | Nguyen et al., *LMGP*, [DOI](https://doi.org/10.1109/CVPR52688.2022.00866), [arXiv](https://arxiv.org/abs/2111.11892) | 3D几何预聚类与时空 lifted multicut | 中心式全局优化 | 混合 | 多相机基准；适合离线研究对照，在线延迟较大 |
| 2021/2022 | Xu et al., *Omni-swarm*, [DOI](https://doi.org/10.1109/TRO.2022.3182503), [arXiv](https://arxiv.org/abs/2103.04131) | 无GPS无人机群视觉-惯性-UWB相对状态 | 分布式前端/图优化后端 | 混合 | 多机实飞；[代码](https://github.com/HKUST-Aerial-Robotics/Omni-swarm)。可提供相对位姿参考，不直接解决目标身份 |
| 2021/2022 | Zhang et al., *ByteTrack*, [DOI](https://doi.org/10.1007/978-3-031-20047-2_1), [arXiv](https://arxiv.org/abs/2110.06864) | 关联高低置信检测框 | 单相机本地 | 序贯 | MOT17/20等；[代码](https://github.com/FoundationVision/ByteTrack)。适合本地 MOT，不输出全局任务身份 |
| 2022 | Aharon et al., *BoT-SORT*, [arXiv:2206.14651](https://arxiv.org/abs/2206.14651) | 运动、外观、相机运动补偿 | 单相机本地 | 序贯 | MOT17/20；[代码](https://github.com/NirAharon/BoT-SORT)。机动相机有价值，小目标 ReID 可能退化 |
| 2023 | Cheng et al., *ReST*, [DOI](https://doi.org/10.1109/ICCV51070.2023.00922), [arXiv](https://arxiv.org/abs/2308.13229) | 先空间关联、再时间图关联 | 中心式在线图 | 混合 | WILDTRACK等；[代码](https://github.com/chengche6230/ReST)。研究升级路线，依赖训练和 GPU 图网络 |
| 2023 | Du et al., *A Cooperative Target Localization Method Based on UAV Aerial Images*, [DOI](https://doi.org/10.3390/aerospace10110943) | 多 UAV 图像/AOA联合定位和 PDOP | 领导者坐标系集中融合 | 同时为主 | 真实航拍图像、Monte Carlo、UKF；直接支持几何构型和 AOA 协方差的重要性 |
| 2024 | Ma et al., *Track Initialization and Re-Identification for 3D Multi-View MOT*, [DOI](https://doi.org/10.1016/j.inffus.2024.102496), [arXiv](https://arxiv.org/abs/2405.18606) | 2D检测驱动3D轨迹初始化、遮挡、重识别 | 中心式 Bayes/GLMB | 混合 | CMC/WILDTRACK；[代码](https://github.com/linh-gist/3D-Visual-MOT)。理论完整但复杂、依赖域内 detector/ReID |

共 `11` 篇主要论文。Google Scholar 仅用于发现，表内证据均回到 DOI、arXiv或官方仓库。当前环境没有 Web of Science 订阅或导出记录，因此不声称完成 WOS 引文网络核验。

## 7. 开源代码审计

维护状态按 2026-07-11 GitHub元数据和 README 检查；最近 push 不代表已适配 MSM。

| 项目 | 用途 | 许可证/维护 | 适用性 |
|---|---|---|---|
| [OpenCV](https://github.com/opencv/opencv) | 投影、三角化、PnP、标定/畸变 | Apache-2.0；活跃 | **成熟默认**几何原语；不负责身份、协方差或联盟语义 |
| [ByteTrack](https://github.com/FoundationVision/ByteTrack) | 单相机 tracking-by-detection | MIT；非归档，主要代码活动约2024 | **成熟默认本地 MOT**；需重标定小无人机检测，local ID 不能替代 GlobalTrack |
| [BoT-SORT](https://github.com/NirAharon/BoT-SORT) | 相机运动补偿 + ReID | MIT；非归档，主要代码活动约2024 | **可插拔升级**；FastReID/GPU/纹理依赖较重 |
| [MMTracking](https://github.com/open-mmlab/mmtracking) | MOT/SOT/VID工具箱 | Apache-2.0；非归档，主分支活动约2023 | **研究对照**；依赖栈重，不能解决联盟和全局绑定 |
| [MVDet](https://github.com/hou-yz/MVDet) | 标定多相机特征投影 | 仓库 API/根 README未发现明确许可证；2025有提交 | **研究方案，暂不可直接复用**；固定地平面和行人域差异大 |
| [ReST](https://github.com/chengche6230/ReST) | 空间图 + 时间图 MTMC | MIT；非归档，主要代码活动约2024 | **研究升级**；需要 DGL、权重和域内数据 |
| [3D-Visual-MOT](https://github.com/linh-gist/3D-Visual-MOT) | 多视图 GLMB、ReID、遮挡 | MIT；2026有提交 | **强研究对照**；Python/C++混合、计算和数据准备成本高 |
| [Omni-swarm](https://github.com/HKUST-Aerial-Robotics/Omni-swarm) | 无GPS群体相对位姿 | README声明 GPLv3；主代码活动约2022 | **相对位姿参考**，不是目标 MOT；ROS/TensorRT/UWB依赖重且需许可证审查 |

## 8. 选型分级

- **成熟默认**：中心 GlobalTrack 按量测时间预测；OpenCV几何、像素/位姿协方差传播和重投影门控；ByteTrack维护本地连续性；跨相机以几何、时间和计划绑定为主。
- **可插拔升级**：BoT-SORT相机运动补偿；多视图 JPDA/GLMB软关联；带权三角化/UKF；分布式保守信息融合。
- **研究方案**：MVDet/BEV、ReST/LMGP图模型、3D-Visual-MOT/GLMB；Omni-swarm只作为相对位姿参考。
- **无成熟完整实现**：没有单一仓库同时覆盖机动多无人机相机、中心 GlobalTrack、`k_j`联盟合同、到达槽、友方身份、保守授权、分布式失效和 D7门控。

## 9. 本项目状态与优先级

已实现基础包括中心航迹投影、像素协方差/马氏门控、camera-local MOT namespace、truth隔离、detect-to-existing-GlobalTrack注册、跨视角 support、分布式 metadata-only hypothesis，以及友方/版本/时效保守门控。

M 对 N 联盟锁合同已实现：D5 只读携带 D3 schema v2 的 `coalition_id/version`、成员 role/wave、`required_resource_count`、`coordination_mode`、arrival window、`plan_id/version` 和 activation state；`TerminalObservationBus` 将同联盟、同版本、已授权激活且不超 demand 的多资源 lock 解释为 `planned_cooperative_lock`。超额资源、联盟/版本冲突、resource scope 不符、未获执行授权和 local/global 多重绑定仍产生 duplicate/conflict evidence。未激活 reserve/retry 的视觉可锁候选输出 `hold` 和 D7 visual PNG blocker，active primary wave-0 与 k=1 保持兼容。

联盟完成度接口也已实现：`summarize_coalition_visual_completion()`/`TerminalObservationBus.coalition_visual_summary()` 输入 D3 coalition bindings 和当前/历史 terminal associations，输出 `primary_required_count`、`primary_locked_resource_ids`、`primary_lock_complete`、`reserve_ready_resource_ids`、`coalition_visual_consensus`。hybrid 默认要求每个 active primary 当前锁定且连续至少 2 帧；standby reserve 的本机几何匹配只标记 ready，不进入 consensus 或视觉 PNG 授权。无本机 detection、跨 resource/camera bbox、合同版本冲突和 over-demand 均保守阻断。

- **联盟锁与完成汇总语义 P1 已闭合。** 回归覆盖 k=3 三锁合法、第四锁超额、hybrid 2+1、缺一个 primary、reserve-only、连续两帧、联盟/计划版本冲突、reserve 未激活 hold、跨相机 bbox 拒绝和 k=1。
- **跨视角边界不变。** 各 resource-camera 独立做中心 GlobalTrack 投影和 local MOT；cross-view summary 只汇总支持并解释联盟合法性，不创建或重绑全局身份。
- 三角定位、PDOP、同步/序贯支持分层、异步多视图滤波仍属于 P1/P2 研究验证；深度 ReID和图网络保留为研究对照。

`blocks_cv_m5_n2_liveness_batch_20260711` 的三 seed、T001 共识为 0 是实施前历史基线。当前运行证据为 `p1_p2_validation_20260711`：ComputerVision 10 seeds 中，T001 双 primary 在当前计划授权下形成视觉共识 `8/10`；错误 duplicate 为 `0/10`。这验证了计划内合法协同多锁与错误重复锁分离，P1 合同层已经闭合。

控制与物理层仍未闭合：ComputerVision 的 `control_allowed_count=0`；SimpleFlight 15 s 诊断中 30 个 active pair 均未命中，其中 24 个为 `terminal_detection_timeout`。后续应定位持续 detection、D5 lock 与 D7 control gate，而不是回退或放宽合法协同锁、版本、友方冲突和本机检测来源门控。

2026-07-11 D5 已实现 fallback commit 消费接口。对于 `k>1`，只要存在 `coalition_commit` 或 center-failed/fallback 标记，视觉联盟完成必须同时通过 D4 commit 的 `state=committed|executing`、epoch、lease expiry、coalition/plan id+version、required members 和 acked members 校验。commit 无效时 `CoalitionVisualSummary` 保留 primary/reserve 视觉证据，但输出明确 conflict/reason，`coalition_visual_consensus=False` 且 visual PNG authorized resources 为空。当前二级接管和完全分布式完整 ACK commit 正例均已通过，缺 ACK 场景按合同 fail closed；这证明合同语义，不表示物理命中。

OpenCV calibration/`solvePnP` 已增加隔离式 P2 合成 benchmark：它复用 `CameraModel`/`GlobalTrack`，评估外参和双时间戳偏差对单/多视角投影门控的敏感性，但不接入 coalition summary、跨视角在线绑定或 main runtime。truth label 仅用于门控后的离线评分。该结果可为后续三角定位/PDOP 提供外参误差量级参考，不能替代真实多相机标定，也不能证明控制许可或物理拦截。

T001 复验新增了计划/联盟双版本连续性边界：reserve-only replan 可改变 plan ID 和 reserve member，并让 plan/coalition version 同时严格升高；只要两个 primary 的 owner/node、`coalition_id`、target/global ID、resource-target binding、role、epoch 和需求保持不变，D5 可把上一安全帧计入新版本的两帧稳定窗口。`coalition_version` 是代际而非 identity；当前 association 必须已经精确匹配新 plan/coalition version，旧版本绝不重新获得授权。相同/下降 coalition version、coalition ID 改变、primary 换员、换绑、owner/epoch conflict、stale replay、friend/duplicate/wrong-binding、过期或 commit-conflicted evidence 均中断链路。该接口已通过模块测试和 10-seed ComputerVision `8/10` 双 primary 合同验收。

## 10. 建议验证场景

1. `k_j=3`、三名合法成员同时锁定：不得产生 duplicate risk。
2. 第四架计划外资源加入：必须产生 unauthorized over-lock evidence。
3. 三名资源分三个 arrival slot 锁定：历史锁定不得计入同步三角化。
4. 交会角过小、外参漂移或帧时延：输出低可观测度/高协方差，不得提高 lock confidence。
5. 一台相机遮挡、另一台连续可见：恢复仍只能绑定原 `global_track_id`。
6. 单资源多本地锁定或单本地多全局支持：保持 duplicate/conflict。
7. 完全分布式且中心 ID stale：只输出 hypothesis/hold，不创建全局身份。

## 11. 真实 AirSim M=5、N=2 历史证据补充

以下 `blocks_cv_m5_n2_cooperative_live_20260711` 是实施前诊断，已被第 9 节的 10-seed 当前验证取代，不代表当前 T001 合同状态。

2026-07-11 的 `blocks_cv_m5_n2_cooperative_live_20260711` 未形成 cooperative lock。虽然 5 主相机与 2 二级相机均出图，AirSim built-in detection 在绝大多数帧为空；full-flow 只有最后一帧 `Secondary_Recon_1` 对 `TGT-002` 的单 bbox，D5 总计 32 `reacquire`、4 `ambiguous`、0 `locked`。

使用记录的 `Secondary_Recon_1:0` 外参、目标位置和 bbox 重放，D5 得到约 0.09 px 的同相机误差并选择 `T002`。单帧 MOT history=1 导致 `mot_history_too_short`，属于预期安全门控。runtime 把该二级 local track fallback 给多个主资源后产生的 18-78 px 不能作为同相机重投影误差。下一轮必须先修正 camera scope、mesh filter 与 pose/render warm-up，真实连续锁定后才能评价 `planned_cooperative_lock`；本轮只证明联盟合同未因空检测而改绑或误锁。
