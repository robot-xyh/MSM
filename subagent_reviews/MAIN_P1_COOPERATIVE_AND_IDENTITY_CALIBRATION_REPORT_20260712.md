# P1 协同闭环与身份连续性标定报告

**日期**：2026-07-12
**执行角色**：main 负责 AirSim 编排、跨模块接线和汇总；D1-D7 分别完成模块实现、自测和文档同步。
**边界**：本轮为科研仿真验证，不改变 PN/PNG 核心公式，不使用在线 truth ID，不允许 D5/D7 改写 `global_track_id`。

## 1. 本轮目标

本轮同时处理两条 P1 主线：

1. 高威胁目标采用 `2 primary + 1 reserve` 的 M5N2 协同拦截，完成 D3 候选筛选、D4 联盟/通信安全、D5 多成员视觉共识、D7 合同门控和 D6 分层统计。
2. 使用真实 AirSim ComputerVision 5 目标交叉 replay，完成 D1 governed replay、D2 54 组 GNN 参数筛选、20-seed confirmation 和轻量 JPDA 同输入对照。

默认运行路径保持：D1 NumPy EKF/fixed-lag、D2 GNN/Hungarian、D3 SciPy demand-slot、D4 lease/epoch/ACK、D5 AirSim detect 几何关联、D7 位置 PN 与既有视觉 PNG。

## 2. 模块实施结果

| 模块 | 本轮实施 | 结果 |
|---|---|---|
| D1 | AirSim JSON/JSONL replay 冻结、独立 truth sidecar、双时间戳/协方差/NED/lineage/OOSM 治理 | 真实 20-seed 输入可重复消费；在线 truth 泄漏为 0 |
| D2 | 54 组 gate/quality/lifecycle/motion 参数矩阵，10-seed screening、20-seed confirmation、轻量 JPDA 对照 | 默认 GNN 保留；JPDA 不晋级 |
| D3 | 27 组 handoff/window/sector 候选，D7 质点预筛，top-3 进入 AirSim | 候选过程可复现，未证明物理协同收益 |
| D4 | 六类通信故障 replay；绑定一致性与视觉 readiness 解耦；arbiter 按 pair 隔离 | 60/60 安全预期满足；错误 `d4_terminal_inconsistent` 在复跑中降为 0 |
| D5 | cooperative visibility/lock funnel、成员变化诊断、跨兼容版本保持连续性 | typed 相机几何接线后，有 local track 的 596/596 条记录 geometry valid |
| D6 | cooperative closure 与 dense crossing 的 CSV/JSON/中文 Markdown/曲线 | D3-D7 证据均可用，pair/target/coalition 分层输出 |
| D7 | pair/coalition 诊断、计划刷新连续性、窗口关闭回退 radar PN | PN/PNG 公式未改；所有不完整合同继续 fail-closed |
| main | reset 后候选 pose、生效的 typed camera geometry、稀疏 binding 保持、D6 证据映射 | owner 缺失专项从历史 6-29 次降为 0 |

## 3. AirSim 场景

### 3.1 M5N2 cooperative smoke

- 模式：SimpleFlight 拦截资源 + actor 目标。
- 资源/目标：5/2。
- 高威胁需求：2 个 active primary、1 个 standby reserve。
- 高度：`z=-30 m`。
- 时长/步长：35 s / 0.1 s，每个 case 351 帧。
- 候选：baseline，以及 `handoff=20 m`、`sector=40 deg`、arrival window 为 3/5/8 s。
- 运行方式：一个 Blocks 进程，四个 reset-separated episode；不保存相机截图。

### 3.2 dense crossing

- 模式：ComputerVision。
- 资源相机/目标：5/5，另有 2 个二级相机。
- 目标间距：4 m；目标速度倍率：2；轨迹实际交叉。
- 20 seeds，每 seed 51 帧，10 s / 0.2 s。
- truth 只写入 D1 独立 sidecar，D2 在线输入不携带 truth identity。

## 4. Cooperative 实测结果

| Profile | pair 成功 | target 成功 | coalition 完成 | contract sample | control sample |
|---|---:|---:|---:|---:|---:|
| baseline | 0 | 0 | 0 | 3 | 0 |
| handoff20/window3/sector40 | 0 | 0 | 0 | 0 | 0 |
| handoff20/window5/sector40 | 0 | 0 | 0 | 1 | 0 |
| handoff20/window8/sector40 | 1 | 1 | 0 | 0 | 0 |

D6 三层漏斗：active-primary pair `12/12` 已分配、可见并完成局部关联；`2/12` 达到合同层，`0/12` 达到控制许可，`1/12` 在雷达 PN 路径进入 5 m，coalition completion 为 `0/4`。

安全结果：reserve 越权为 0，`global_track_id` 改写为 0，在线 truth 使用为 0。通信故障矩阵 normal、0.5 s delay、30% loss、center failure、center+secondary failure、partition recovery 均符合预期；丢包负例保持 fail-closed。

### 4.1 根因变化

修复前，`d4_terminal_inconsistent` 将“D5 尚未锁定”错误解释为“绑定不一致”，并存在不同 pair 共用迟滞状态的问题。修复后四个 case 中该拒绝均为 0。

当前实际断点变为：

- primary 到达窗口关闭；
- D5 best/second candidate margin 不足或视觉证据过期；
- reserve 尚未激活；
- 两个 primary 无法维持同步、连续的视觉锁定；
- SimpleFlight 中段几何和到达时序不足以形成 coalition completion。

main 另做 12 s 稀疏 binding 专项：121 帧、360 条控制记录，`d4_owner_missing=0`，所有最终 pair 保持 D3 plan 与 `d3_central` owner；该场景有 1 个 pair/target 进入 5 m，但 coalition 仍未完成。

## 5. Typed 相机几何

main 将每个资源相机的 `K`、camera-to-NED 旋转、相机 NED 位置、量测/曝光/到达/姿态时间构造成 D5 `CameraGeometryEvidence`，挂入对应 `LocalVisualTrack`，并由 D5 association 透传至 D7。

baseline 复跑中：

- 596 条存在 local track 的 runtime record：`596/596 geometry_valid=true`，来源均为 `airsim_camera_info`。
- 757 条无 local track 的 `reacquire`：明确记录 geometry unavailable，不伪造证据。
- actor/object truth pose 未用于在线几何补齐。

## 6. D1/D2 20-seed 结果

| 路径 | IDSW mean | identity continuity | coverage continuity | false track | RMSE | P95 loop latency |
|---|---:|---:|---:|---:|---:|---:|
| 默认 GNN/Hungarian | 0 | 1.0 | 1.0 | 0 | 约 0.164 m | 约 3.7 ms |
| 最佳候选 GNN | 0 | 1.0 | 1.0 | 0 | 约 0.164 m | 约 3.8 ms |
| 轻量 JPDA | 0 | 1.0 | 1.0 | 0 | 约 0.164 m | 约 4.7 ms |

screening、confirmation 和 JPDA 对照均正确标记为真实 AirSim governed replay。晋级策略结论为：`promotion_recommended=false`，在线路径继续 `baseline_gnn_hungarian`。

该结果只能说明本轮 crossing fixture 未击穿默认 GNN，不能说明密集交叉关联问题已经解决。所有候选的身份指标相同，场景缺少足够的漏检、虚警、长遮挡和可辨识度变化，后续需要增加难度分层。

## 7. 验证

| 范围 | 结果 |
|---|---:|
| D1 | 74 passed |
| D2 | 82 passed |
| D3 | 132 passed，1 optional OR-Tools skip |
| D4 | 167 passed |
| D5 | 181 passed |
| D6 | 100 passed |
| D7 | 155 passed |
| AirSim runtime | 106 passed |
| integrated/dry-run/cross-module | 14 passed |

## 8. 结论与后续 P1

本轮关闭的是接口和错误状态聚合缺口：D1 replay/truth 隔离、D2 固定矩阵、D4 binding 判定、D5 typed geometry、D7 滚动版本连续性、D6 证据汇总和 main 稀疏 binding 均已形成代码与回归证据。

仍未关闭的是性能缺口：M5N2 coalition completion 仍为 0，视觉控制许可仍为 0，dense crossing fixture 区分度不足。下一轮应优先运行至少 10 seeds 的 cooperative top-3，对第二 primary 中段可达性、同步锁定窗口和成员稳定性分别做因果拆分；随后再增加 D2 漏检/虚警/遮挡强度，不应直接把 JPDA 或其他 P2 算法替换进主线。

## 9. 证据路径

- cooperative 汇总：`research_modules/airsim_runtime/outputs/p1_cooperative_closure_v2_contractfix_smoke_20260712/`
- D6 cooperative 报告：`.../d6_cooperative_closure/P1_COOPERATIVE_CLOSURE_REPORT.md`
- 稀疏 binding 专项：`research_modules/airsim_runtime/outputs/p1_sparse_binding_owner_smoke_20260712/`
- dense crossing 汇总：`research_modules/airsim_runtime/outputs/p1_identity_dense_crossing_cv20_20260712/`
- D6 dense crossing 报告：`.../d6_dense_crossing/DENSE_CROSSING_CALIBRATION_REPORT.md`
