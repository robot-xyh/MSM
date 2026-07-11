# P1 AirSim Runtime 闭环验证报告（2026-07-11）

## 1. 验证目标

本轮验证检查 P1 集成改动是否真正进入 AirSim episode，而不只停留在模块单元测试：

1. 在线链路去除 AirSim truth ID 后，D1→D2→D3→D5→D4→D7 是否仍可运行；
2. D4 是否区分中心保持、二级节点接管和完全分布式降级；
3. D5 YOLOv8+MOT 是否能接收真实 AirSim 图像，且 AirSim detect 只作为离线 bbox 评分；
4. D7 四种导引律是否能在同 seed、同几何、reset 分隔条件下执行并由 D6 配对统计。

本轮未保存相机截图。报告中的 PNG 为指标图或轨迹图，不是 AirSim 画面截图。

## 2. 代码与合同结果

main runtime 已完成以下闭环：

- D1→D2 在线输入显式清除 `truth_id`、actor name 和 truth position；
- D2→D3 使用 D2 状态、协方差、中心拥有的 `global_track_id` 和可配置威胁先验，不再要求 truth label；
- D2→D5 的三维位置由 D2 水平状态和 main 缓存的 D1 三维运动学组成；
- AirSim actor alias 仅保留在仿真执行器边界，用于驱动 actor，不进入 D3/D5 在线关联；
- D1、D2、D3 governance 摘要和 D4 secondary lifecycle 事件已写入 D6 episode 日志；
- D4 不再把 `continuity_available=False` 时的数值占位 `track_continuity=0` 当作硬风险；
- 导引律 sweep 显式写入 experiment-level guidance law，D6 可进行同 seed 配对。

## 3. 测试环境

| 项目 | 配置 |
|---|---|
| AirSim | Blocks / AirSim 1.8.1 |
| GPU | NVIDIA RTX 4050 Laptop，6 GB |
| 5v5 感知模式 | ComputerVision，多相机实体 + actor target |
| 2v2 拦截模式 | SimpleFlight interceptor + 非 SimpleFlight actor target |
| 在线身份 | D2 `global_track_id`，不使用 AirSim object ID |
| 二级相机 | 1920×1080，FOV 110°，机动高空侦察节点 |
| D5 检测 | `best.pt`，YOLOv8；请求 ByteTrack，允许 IoU fallback |
| D7 导引 | Pure Pursuit、Radar PN、PNG-VM、PNG-TTC |

## 4. D4/D5 真实 5v5 结果

三组运行均使用一次 Blocks 启动、三个 reset 分隔 episode，每个 episode 5 帧，`connected=True`。

| 高差 / 二级节点数 | 场景 | D4 动作 | 联合平均覆盖 | 同帧全覆盖率 | Cross-view 数 | 稳定注册数 |
|---|---|---|---:|---:|---:|---:|
| 200 m / 2 | 不降级 | `continue_center` 25/25 | 0.72 | 0.00 | 4 | 24 |
| 200 m / 2 | 期望二级接管 | `degrade_to_distributed` 25/25 | 0.72 | 0.00 | 4 | 21 |
| 200 m / 2 | 二级不可用 | `degrade_to_distributed` 25/25 | 0.68 | 0.00 | 4 | 19 |
| 50 m / 2 | 期望二级接管 | `degrade_to_distributed` 25/25 | 0.64 | 0.00 | 4 | 19 |
| 200 m / 5 | 期望二级接管 | `degrade_to_distributed` 25/25 | 0.80 | 0.00 | 4 | 58 |

### 结果解释

- **中心保持正例通过**：在线 truth 隔离后没有产生虚假的 D2 continuity 硬风险，D4 全部保持中心控制。
- **完全分布式负例通过**：二级不可用时全部进入 `degrade_to_distributed`。
- **二级接管正例未通过**：二级节点已经能看到并注册大部分目标，但 `secondary_network_joint_full_view_frame_rate` 仍为 0，D4 readiness 只能达到 `registration_usable`，没有达到 `takeover_ready`。D4 保守转分布式符合现有安全门控，不能通过放宽阈值掩盖。
- 从 2 个增加到 5 个二级节点后，平均覆盖提高到 0.80、稳定注册明显增加，但仍缺少“同一同步帧内覆盖全部目标”的证据。当前 P1 核心仍是二级 detect→同步 frame evidence→全局注册，而不是通信或 D4 状态机。

证据：

- [200 m / 2 节点序列](../research_modules/airsim_runtime/outputs/p1_runtime_truth_isolated_d4d5_smoke_20260711/blocks_sequence_summary.json)
- [50 m / 2 节点序列](../research_modules/airsim_runtime/outputs/p1_runtime_truth_isolated_d4d5_50m_20260711/blocks_sequence_summary.json)
- [200 m / 5 节点序列](../research_modules/airsim_runtime/outputs/p1_runtime_truth_isolated_d4d5_secondary5_20260711/blocks_sequence_summary.json)

## 5. D5 YOLOv8 + MOT 结果

修复 bbox-only 离线评分解析后，6 个 reset 分隔 episode 均完成；每个 episode 2 帧、7 路相机，共产生 84 个相机处理样本。

| 指标 | 结果 |
|---|---:|
| pipeline status=ok | 84 / 84 |
| YOLO accepted detection | 0 |
| AirSim detect 离线 truth bbox | 24 |
| 匹配 truth bbox | 0 |
| false negative | 24 |
| 当前样本检测 recall | 0.00 |
| 请求 tracker | ByteTrack |
| 实际 tracker | IoU fallback 84 / 84 |
| 延时中位数 | 36.4 ms |
| 延时 P95 | 85.6 ms |
| 冷启动最大延时 | 2148.3 ms |

结论是**接口跑通但检测效果未通过**。当前 `best.pt` 对该 AirSim 图像、目标尺度、视角或渲染域没有产生有效检测；native ByteTrack 因没有检测 track ID 而按设计回退。AirSim detect 的 bbox 只进入离线 precision/recall 统计，`used_by_online_tracker=False`，没有 truth ID 泄漏。

证据：[YOLOv8 + ByteTrack smoke summary](../research_modules/airsim_runtime/outputs/p1_yolov8_bytetrack_smoke_fixed_20260711/blocks_sequence_summary.json)

## 6. D7 四导引律同 Seed 结果

运行条件为固定 2v2、seed 7、相同初始几何、每种导引律 reset 后执行，单组最大拦截时间 2 s。该时长用于接口冒烟，不用于最终命中率评价。

| 导引律 | Pair | 成功 | 状态 | Pair 平均最小距离 | 视觉切换允许率 |
|---|---:|---:|---|---:|---:|
| Pure Pursuit | 2 | 0 | timeout 2 | 2.922 m | 0.000 |
| Radar PN | 2 | 0 | timeout 2 | 3.905 m | 0.000 |
| PNG-VM | 2 | 0 | timeout 2 | 2.913 m | 0.762 |
| PNG-TTC | 2 | 0 | timeout 2 | 2.884 m | 0.810 |

四条导引路径均输出 42 条控制记录。Pure Pursuit 和 Radar PN 没有进入视觉接管；PNG-VM/TTC 仅在 D3 计划、D4 权限和 D5 terminal gate 通过时切换，说明选择器和门控合同生效。由于四组均 timeout，不能声称 PNG 命中率优于 PN；当前只能说明短窗口内 PNG 两组更接近目标且视觉切换发生。

![D6 同 Seed 配对差值](../research_modules/airsim_runtime/outputs/p1_guidance_four_law_smoke_20260711/d6_guidance_comparison/guidance_same_seed_deltas.png)

证据：

- [main sweep summary](../research_modules/airsim_runtime/outputs/p1_guidance_four_law_smoke_20260711/guidance_law_sweep_summary.json)
- [D6 paired summary](../research_modules/airsim_runtime/outputs/p1_guidance_four_law_smoke_20260711/d6_guidance_comparison/guidance_same_seed_summary.json)
- [D6 中文报告](../research_modules/airsim_runtime/outputs/p1_guidance_four_law_smoke_20260711/d6_guidance_comparison/guidance_same_seed_report.md)

## 7. 测试回归

| 模块 | 结果 |
|---|---:|
| D1 | 38 passed |
| D2 | 44 passed |
| D3 | 84 passed |
| D4 | 95 passed |
| D5 | 105 passed |
| D6 | 57 passed |
| D7 | 61 passed |
| AirSim runtime | 66 passed |

仅有既存 Matplotlib `Axes3D` 多版本警告，不影响本轮 2D 指标图和 JSON/CSV 输出。

## 8. 当前结论与下一步

### 已验证

- 无在线 truth ID 的 D1→D7 main episode bus 可以完成 5v5 计划、关联、仲裁和日志闭环；
- D4 中心保持与完全分布式降级两条路径有效；
- D5 bbox-only 离线评分与在线身份隔离合同有效；
- D7 四导引律选择、D5/D4 门控和 D6 同 seed 配对链路有效。

### 未关闭的 P1

1. 二级高空侦察网络需要形成同一同步帧内的全部目标覆盖和稳定 global registration，才能产生真实 `degrade_to_secondary` 正例；
2. YOLO 权重需要针对 Quadrotor1 mesh 的渲染域、尺度、相机姿态和曝光做离线数据检查与阈值校准，随后才能验证 native ByteTrack/BoT-SORT；
3. 四导引律需增加拦截时长并运行至少 10 个 seed，拆分 timeout 的几何、机动和视觉 gate 原因；
4. D1 高 OOSM 比例需按 measurement/arrival 时序和期望延迟配置重新标定，不能直接当作硬件故障率；
5. 真实多 seed 后才能校准 D3 迟滞、D4 主动降级必要性标签和 D6 置信区间。
