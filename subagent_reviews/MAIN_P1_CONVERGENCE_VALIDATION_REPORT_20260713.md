# P1 收敛实施与 AirSim 验证报告

**日期**：2026-07-13
**执行边界**：科研仿真与离线评估，不用于实机自动处置。
**组织方式**：main 负责 AirSim、runtime、跨模块总线和汇总；D1-D7 分别修改并验证模块 owned paths。

## 1. 本轮目标

本轮针对四个尚未闭合的 P1 问题执行真实 AirSim 与离线验收：

1. 以严格 4 m/2 m 目标间距重新校准 D1/D2 dense crossing，排除旧场景仍保留 4 m 纵向错位的问题。
2. 运行 M5N2 高威胁目标 `2 primary + 1 reserve` 协同拦截，按 NED 三维 5 m 判定物理成功，不要求同时到达。
3. 对 `best.pt`、ByteTrack 和 BoT-SORT 执行真实 1920x1080 AirSim 准入筛选，未达门限时继续使用 detect。
4. 验证 D4 正常、中心失效、二级失效、延迟、丢包和网络分区恢复，并由 D6 统一输出中文报告和曲线。

D7 继续使用既有位置 PN 与 `png_guidance_delivery` 的视觉 PNG；本轮没有修改 PN/PNG 核心公式。

## 2. 运行链路

```text
AirSim Blocks / actor targets
  -> D1 governed replay（双时间戳、协方差、NED、lineage）
  -> D2 GNN/Hungarian / optional JPDA 对照
  -> D3 M5N2 版本化 AssignmentPlan（2 primary + 1 reserve）
  -> D4 center / secondary / distributed 仲裁
  -> D5 detect 或 YOLO + native MOT、per-primary 几何锁定
  -> D7 contract -> control -> mode switch -> 5 m physical intercept
  -> D6 CSV / JSON / Markdown / PNG
```

在线 D1/D2/D5 不读取 AirSim actor truth ID；truth 仅在在线结果写盘后用于 D6 离线评分。D5/D7 不改写 `global_track_id`，过时计划和未激活 reserve 均不得执行视觉 PNG。

## 3. D1/D2 严格 Dense Crossing

### 3.1 场景

- 模式：ComputerVision。
- 目标数：5。
- nominal：相邻目标三维距离严格为 4 m。
- tight：相邻目标三维距离严格为 2 m。
- 每组 20 seeds，共 40 个真实 AirSim episode。
- 每个 episode 51 帧，不保存截图。
- evaluator-only truth 样本共 10200 条，在线 truth 泄漏为 0。

### 3.2 结果

| 指标 | 基线 | 最佳 GNN 候选 | 变化 |
|---|---:|---:|---:|
| ID switch | 1.3583 | 0.6167 | 下降 54.6% |
| track continuity | 0.9810 | 0.9840 | +0.0030 |
| P95 loop latency | - | 24 ms | 满足实时筛选预算 |

![Dense crossing 标定结果](../research_modules/airsim_runtime/outputs/p1_identity_strict_4m_2m_20260713/d6_dense_crossing/dense_crossing_metrics.png)

候选显著降低了 IDSW，但没有达到冻结的 continuity 至少提升 0.10 的晋级条件。轻量 JPDA 在同输入下退化，因此默认在线关联器仍为 GNN/Hungarian。D2 truth 对齐只允许 `1e-9 s` 内的精确时间匹配；未匹配 truth 明确记录为 partial/unmatched，不再以最近邻补造标签。

## 4. D4 Episode-Time 故障矩阵

### 4.1 场景矩阵

每类 10 seeds，共 60 case：

- normal；
- center failure；
- center + secondary failure；
- 0.5 s message delay；
- 30% message loss；
- partition recovery。

### 4.2 结果

| 指标 | 结果 |
|---|---:|
| safety outcome | 60/60 |
| false degradation | 0 |
| duplicate owner | 0 |
| split-brain prevention failure | 0 |
| 30% 丢包下 fail-closed | 7/10 |

中心失效后可进入二级层；中心和二级均失效时仅在 epoch、lease 和必要成员 ACK 满足时提交分布式联盟。缺 ACK、旧 plan version、旧 coalition epoch 和网络分区均阻断执行。该证据来自 AirSim episode clock 驱动的故障注入，不代表已完成真实 RF 链路或多机网络认证。

## 5. M5N2 协同物理闭环

### 5.1 场景与判据

- 资源数 5、目标数 2。
- 高威胁目标采用 2 个 active primary 和 1 个 standby reserve。
- 10 seeds，baseline 与三个 D3 质点预筛候选，共 40 个 SimpleFlight episode。
- 不要求同时到达；每个 active primary 独立通过 D3/D4/D5/D7 门控。
- NED 三维最近距离不大于 5 m 记为物理拦截成功。

### 5.2 结果

| Profile | Coalition completion |
|---|---:|
| baseline | 0/10 |
| 20 m / 3 s / 40 deg | 5/10 |
| 20 m / 5 s / 40 deg | 2/10 |
| 20 m / 8 s / 40 deg | 1/10 |

![M5N2 协同闭环结果](../research_modules/airsim_runtime/outputs/p1_m5n2_cooperative_10seed_20260713/d6_cooperative_closure_corrected/cooperative_closure_overview.png)

最佳候选没有达到 `8/10` 验收门限。主要失败原因是 `d5_not_locked` 和 `terminal_detection_acquisition_timeout`，少量 case 为 `bbox_area_too_small`。安全侧没有退化：reserve 越权执行 0、`global_track_id` 改写 0、在线 truth 使用 0。

D6 修复了早期按 `case_id::profile` 分组的问题。正确口径为最佳 profile `5/10`、全部 profile 合计 `8/40`，不是 40 个独立单 seed profile。

## 6. D5 原生 MOT 准入

### 6.1 筛选矩阵

- 目标 mesh：无人机目标，不使用 cube 权重假设。
- 相机：1920x1080、FOV 90 deg。
- 距离：20/30/50 m。
- confidence：0.10/0.20/0.30。
- tracker：ByteTrack、BoT-SORT。
- 18 个真实 AirSim screening case，每个 101 帧；不保存截图。

### 6.2 结果

| 后端 | 距离 | Native active | Continuity | IDSW | P95 | Precision/Recall |
|---|---:|---:|---:|---:|---:|---:|
| ByteTrack | 20 m | 1.0 | 1.0 | 0 | 约 7.4 ms | 0.30-0.32 |
| BoT-SORT | 20 m | 1.0 | 1.0 | 0 | 约 16.2 ms | 0.26-0.33 |
| 两者 | 30/50 m | 0 | unavailable | 0 | 满足预算 | 无有效检测 |

两个 tracker 的局部连续性和处理延时合格，但检测框与离线 AirSim reference box 在 IoU=0.5 口径下 precision/recall 明显不足。18 个候选均未准入，因此 confirmation case 为 0，默认在线检测保持 AirSim detect。第一次运行因 2 s RPC timeout 在 reset 阶段失败，已以 10 s client timeout 的 `strict_v2` 重跑；第一次失败不计为算法失败。

## 7. D6 统一汇总

统一报告已消费七类正式写盘证据：

| 数据源 | 归一化行数 |
|---|---:|
| D1 dense crossing | 1 |
| D2 difficulty profiles | 3660 |
| D3 cooperative cases | 40 |
| D4 communication cases | 60 |
| D5 per-primary | 160 |
| D5 native MOT | 18 |
| D7 pair/profile | 164 |

![P1 统一证据概览](../research_modules/airsim_runtime/outputs/p1_convergence_20260713/d6_system_evidence/p1_system_evidence_overview.png)

D7 四层结果保持独立：合同允许 35、控制允许 7、模式切换 9、pair 物理成功 62；任何后层结果都不会反推前层。D3 cooperative aggregate 不含完整逐时刻 churn 时，D6 保持该指标 unavailable，不补零。

## 8. 回归测试

| 范围 | 结果 |
|---|---:|
| D1 | 79 passed |
| D2 | 93 passed |
| D3 | 139 passed, 1 optional OR-Tools skipped |
| D4 | 198 passed |
| D5 | 232 passed |
| D6 | 115 passed |
| D7 | 178 passed |
| AirSim runtime | 124 passed |
| integrated simulation + dry-run | 11 passed |

`py_compile` 与 `git diff --check` 通过。matplotlib `Axes3D` 警告来自本机多个 matplotlib 版本，不影响本轮二维 PNG 报告。

## 9. 结论与剩余 P1

本轮关闭了场景几何、写盘 schema、D6 分组和原生 MOT 是否真实运行等证据缺口，没有关闭以下性能问题：

1. M5N2 最佳 coalition completion 只有 5/10，第二 primary 的视觉获取和稳定锁定仍是最高优先级。
2. 30/50 m 的当前 YOLO 权重和目标尺度没有形成有效检测；20 m 的 bbox 口径也未达到准入精度。
3. D2 候选虽降低 IDSW，但 continuity 改善不足，不能据此替换默认 GNN/Hungarian。
4. D4 已完成 episode-time 故障注入，不等同真实通信链路、时钟漂移和带宽约束测试。
5. D3 membership/version churn 仍需从真实逐时刻 plan history 写盘，不能由 aggregate 推断。

因此当前默认主线保持：D1 轻量 EKF、D2 GNN/Hungarian、D3 SciPy 分配与迟滞、D4 center/secondary/distributed 保守仲裁、D5 AirSim detect 几何配准、D7 位置 PN 与视觉 PNG。ByteTrack、BoT-SORT、JPDA/MHT 和其他 P2 算法继续作为 optional benchmark，不进入默认在线控制路径。

## 10. 文件索引

- Dense crossing：`research_modules/airsim_runtime/outputs/p1_identity_strict_4m_2m_20260713/`
- D4 fault matrix：`research_modules/airsim_runtime/outputs/p1_convergence_20260713/d4_episode_communication_fault_matrix.json`
- M5N2：`research_modules/airsim_runtime/outputs/p1_m5n2_cooperative_10seed_20260713/`
- Native MOT：`research_modules/airsim_runtime/outputs/p1_native_mot_strict_v2_20260713/`
- D6 unified：`research_modules/airsim_runtime/outputs/p1_convergence_20260713/d6_system_evidence/`
