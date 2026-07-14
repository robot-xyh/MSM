# P1 独立主资源授权与原生 MOT 实施报告

## 1. 本轮边界

本轮不处理多机同时到达。高威胁目标继续采用 `2 primary + 1 reserve`：两个 active primary 分别完成末端授权和 NED 三维 5 m 物理成功判定，reserve 未被新计划激活时保持 standby。D7 的位置 PN、`png_vm`、`png_ttc` 公式未修改。

## 2. 已实施内容

- D3 的 `terminal_authorization_scope=per_primary` 和 `arrival_coordination_required=false` 已贯通 D5 Assignment、D7 binding、main episode bus 和 SimpleFlight topology。
- D3 纯成本、诊断和评估刷新不再推进 `plan_id`、plan version 或 coalition epoch；真实 assignment/owner/activation 变化才发布新执行版本。
- D4 使用 AirSim frame timestamp 驱动 heartbeat、ACK、lease、epoch 和 owner。无可执行 owner、网络分区或 reconfiguring 时，main 明确设置 `visual_png_allowed=false`。
- D5 原生 ByteTrack/BoT-SORT 准入监测统计 native active rate、fallback、precision/recall、local continuity、local IDSW 和 P95 latency。IoU fallback 不可作为真实 MOT 通过项。
- AirSim truth bbox/actor identity 仅在在线 YOLO/MOT result 生成后读取，并仅供 D5/D6 离线评分。
- D2 六类 profile 已使用真实观测变换：dropout、匿名 clutter、arrival delay/covariance inflation 和 combined；2 m tight crossing 必须来自真实 AirSim 捕获。
- D6 新增统一 P1 evidence CSV、JSON、中文 Markdown 和 PNG 汇总，严格区分 contract allowed、control allowed、mode switched 和 physical intercept。

## 3. 回归结果

| 范围 | 结果 |
|---|---:|
| D1 | 74 passed |
| D2 | 88 passed |
| D3 | 138 passed, 1 optional OR-Tools skipped |
| D4 | 179 passed |
| D5 | 200 passed |
| D6 | 103 passed |
| D7 | 174 passed |
| main runtime / integrated / contracts | 125 passed |

`py_compile` 和 `git diff --check` 均通过。Matplotlib 存在本机 Axes3D 版本警告，不影响本轮二维 D6 图表。

## 4. 真实 AirSim 最小 smoke

运行目录：`research_modules/airsim_runtime/outputs/p1_native_mot_smoke_20260712/`。

配置为 ComputerVision、1 个资源相机、1 个 `Quadrotor1` actor、30 m 目标距离、1920x1080、90 度 FOV、YOLO `best.pt`、ByteTrack、confidence 0.2、禁止 IoU fallback、21 帧，不保存截图。Blocks 成功启动并完成 reset-separated full-flow episode。

| 相机 | 帧数 | Native active | Accepted detection | Fallback | P95 latency |
|---|---:|---:|---:|---:|---:|
| Interceptor_Cam_1 | 22 | 0.0 | 0 | 0 | 8.11 ms |
| Secondary_Recon_1 | 22 | 0.0 | 0 | 0 | 7.48 ms |
| Secondary_Recon_2 | 22 | 0.0 | 0 | 0 | 7.31 ms |

三路均返回 `bytetrack produced no local track IDs`，因此准入失败。在线 truth 使用和 `global_track_id` 改写均为 0。当前证据说明 runtime、后端选择、统计和 fail-closed 路径有效，但 `best.pt` 对当前 AirSim actor 外观/尺度没有产生有效检测；不能据此评价 ByteTrack 与 BoT-SORT 的 ID 保持能力。

## 5. 后续实测顺序

1. 先用单相机 30 m 画面确认 `Quadrotor1` 在相机光轴和尺寸范围内，并离线验证 `best.pt` 的类别、预处理和置信度输出。
2. 检测可用后运行 18-case screening：ByteTrack/BoT-SORT、confidence 0.1/0.2/0.3、20/30/50 m。
3. 每后端选定 30 m 阈值后运行 10-seed 双相机 confirmation；任何 fallback 帧均拒绝准入。
4. 采集 4 m nominal 与 2 m tight crossing 各至少 10 seeds，运行 D2 六 profile；20 seeds 后才执行 confirmation admission。
5. 最后复跑 M5N2 独立 primary 和 D4 center/secondary/peer 故障矩阵，并由 D6 汇总四层结果。

## 6. 真实预检与 20 m 确认结果

main 随后修正了 MOT 距离工况：关闭 CV 相机跟随，目标 X 方向速度设为 0，仅保留横向运动。这样 20/30/50 m 表示实际初始距离档位，而不是目标持续远离后的混合结果。筛选编排同时增加了早停条件：若 30 m 工况没有有效原生 track、检测和离线评分，则不机械选择阈值，也不启动 10-seed confirmation。

输出：

- `research_modules/airsim_runtime/outputs/p1_native_mot_preflight_20260712/preflight_rows.json`
- `research_modules/airsim_runtime/outputs/p1_native_mot_range_matrix_20260712/range_rows.json`
- `research_modules/airsim_runtime/outputs/p1_native_mot_20m_confirm_20260712/confirm_rows.json`

### 6.1 距离预检

| 后端 | 距离 | Native active rate | 检测数 | Continuity | IDSW | P95 |
|---|---:|---:|---:|---:|---:|---:|
| ByteTrack | 20 m | 1.0 | 42 | 1.0 | 0 | 7.71 ms |
| ByteTrack | 30 m | 0.0 | 0 | unavailable | 0 | 6.91 ms |
| ByteTrack | 50 m | 0.0 | 0 | unavailable | 0 | 6.72 ms |
| BoT-SORT | 20 m | 1.0 | 42 | 1.0 | 0 | 18.05 ms |
| BoT-SORT | 30 m | 0.0 | 0 | unavailable | 0 | 16.16 ms |
| BoT-SORT | 50 m | 0.0 | 0 | unavailable | 0 | 16.35 ms |

30/50 m 两个后端同时为零检测，说明瓶颈在 YOLO 权重、目标像素尺度或当前 actor 外观，不是 tracker 选择。ByteTrack 的处理延时约为 BoT-SORT 的一半。

### 6.2 20 m、102 帧确认

| 后端 | Native active | Fallback | Continuity | Local IDSW | Precision | Recall | P95 |
|---|---:|---:|---:|---:|---:|---:|---:|
| ByteTrack | 1.0 | 0 | 1.0 | 0 | 0.324 | 0.324 | 8.29 ms |
| BoT-SORT | 1.0 | 0 | 1.0 | 0 | 0.293 | 0.293 | 18.23 ms |

两个 tracker 的原生运行、局部连续性、IDSW、fallback 和延时均满足当前门限，但整体准入仍失败，因为使用 IoU=0.5 与 AirSim detect 框做 post-online 离线评分时，precision/recall 明显低于 0.9/0.8。逐帧证据显示 YOLO 框持续存在，失败主要来自 YOLO 框与 AirSim detect 框的重叠口径，而不是 local track 中断。

当前不直接降低在线几何门限，也不把 AirSim truth 引入在线关联。下一步应把离线评分拆成中心偏差、尺度比、IoU 多阈值曲线和可见性 availability，确认系统性 bbox 定义差异后再冻结准入阈值。完整 18-case/10-seed 矩阵暂缓，默认 AirSim detect 与 GNN/Hungarian 主线不变。
