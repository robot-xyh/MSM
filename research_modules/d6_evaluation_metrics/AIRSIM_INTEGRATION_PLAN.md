# D6 AirSim 离线集成计划

本文只描述 D6 如何离线消费 AirSim/main runtime 已写盘产物。D6 不连接 AirSim client，不调用 `simGetDetections`、vehicle control、reset、pose 或任何实时 API；AirSim 启停、reset、episode 顺序、日志写盘和最终报告调度由 main runtime 负责。

## 2026-07-13 正式产物消费状态

七源统一报告已经消费正式 AirSim/main 产物，各 source 均 available：D1 `1` 行、D2 `3660` 行、D3 `40` 行、D4 `60` 行、D5 per-primary `160` 行、native MOT `18` 行、D7 `164` 行。D7 的 164 行由 160 条 pair/safety 记录和 4 条 profile 汇总组成，profile aggregate 不与逐 pair 四层重复计数。

正式 M5N2 结果为最佳 profile coalition `5/10`、overall `8/40`；D7 四层为 contract `35`、control `7`、mode switch `9`、physical `62`。online truth use、`global_track_id` rewrite 和 reserve unauthorized execution 均为 0。D3 产物缺少逐时刻 plan history，因此 churn 保持 `unavailable`，D6 不从最终 snapshot 或 version 总数重建时序。

当前 D6 回归为 `115 passed`。真实 4 m/2 m dense-crossing、M5N2、D4 episode fault 和 native MOT 已从“待 main 提供”转为“正式产物已消费”。开放 P1 仅包括长期 multi-seed 趋势、producer 逐时刻 schema 和跨批次失败原因治理；P2 工具保持 optional/offline，不进入默认路径。

## 1. 边界

D6 AirSim 集成是 offline-only：

- 输入是已经保存的 JSONL、CSV、JSON、metadata 和可选 PNG 路径。
- D6 不订阅 runtime bus，不向 D1-D7 回写指标，不触发 replan/failover/guidance。
- D6 不读取在线 truth ID 参与控制；truth label 只用于离线评估。
- D6 不生成 fire-control 参数、毁伤逻辑、自动处置或授权绕过流程。

## 2. 当前已实现的离线入口

| 入口 | 当前输入 | 已实现能力 | 未覆盖 |
|---|---|---|---|
| `load_blocks_replay_jsonl()` | `blocks_frames.jsonl`、可选 `blocks_sensor_observations.jsonl` | 构建 truth summary、规模字段、视觉 track、terminal records、video metadata/bbox link records、D1 replay observation links、多视角 consensus/conflict 基线事件 | 不扫描 episode 目录，不解析 AirSim 原生 recording，不调用 AirSim |
| `load_episode_log_jsonl()` | 标准化 `truth_summary/track/assignment/event/link/terminal` JSONL | 读取 D6 统一记录模型，未知 record type 报错 | 不负责上游 schema 转换 |
| `load_d4_active_degradation_decisions()` | D4 active-degradation CSV | 读取主动降级、二级协助、触发原因和窗口 delta metadata | 不判断主动降级必要性，除非 main/D4 提供 review label |
| `load_d7_intercept_outputs()` | `control_commands.csv`、`intercept_summary.json` | 读取 gate、visual PNG switch、terminal takeover、拦截结果、reject reason | 不运行 D7，不发控制 |
| `load_d7_guidance_timeseries()` | `guidance_records.csv`、`guidance_summaries.json`，可合并 control/intercept 输出 | 读取 mode switch、D4/D5 state、plan/version、guidance law、terminal contract reject | 不负责保证 main 每个 episode 都写出这些文件 |
| `P1SystemEvidenceReportGenerator` | D1-D7 正式 summary/aggregate 与 native MOT execution index | 统一展开七源 available 记录，输出 CSV、JSON、中文 Markdown 和 PNG，并保持四层、availability 和 truth 审计 | D3 缺逐时刻 history 时 churn 保持 unavailable |
| `merge_replay_with_execution_metrics()` | integrated replay 与 main bus execution metrics | 按字段优先级合并离线 replay 和正式执行证据，保留 source/availability/provenance | 不回写 AirSim runtime，不从缺失值构造执行结果 |

## 3. Blocks Replay JSONL 合同

### 3.1 `blocks_frames.jsonl`

每行代表一个 AirSim Blocks frame。D6 当前消费字段：

```text
episode_id
scenario_name
timestamp
truth_objects[]
resources[]
cameras[]
visual_detections[]
metadata.images[] 或 metadata.image
```

`truth_objects[]` 推荐字段：

```text
object_id
object_type = target
position_ned
velocity_ned
threat_score
```

D6 用它构建：

- `truth_summary.truth_timestamps`
- `truth_summary.total_truth_opportunities`
- `truth_summary.high_threat_ids`
- `truth_summary.high_threat_by_timestamp`
- `truth_summary.scenario.target_count`

`resources[]` 推荐字段：

```text
resource_id
metadata.airsim_vehicle_name
```

D6 用它映射 AirSim vehicle/camera owner 到资源 ID，并计算 `resource_count/drone_count`。

`cameras[]` 推荐字段：

```text
camera_id
owner_id
fx
fy
cx
cy
width
height
position_ned
rotation_world_to_camera
```

D6 用它计算 `camera_count`，并把相机内外参保存在 bbox `LinkRecord.metadata` 中，支持无 PNG 的多视角/末端评估。

`visual_detections[]` 推荐字段：

```text
camera_id
object_id
detection_id
local_track_id
bbox_xyxy
center_px
confidence
metadata.airsim_detection_name
object_name
```

D6 当前转换为：

- `TrackRecord`：`association_source="blocks_visual_detection"`。
- `TerminalRecord`：`decision_state="associated"`，用于末端配准准确率。
- `LinkRecord(payload_kind="bbox")`：用于 bbox delivery、多视角和通信统计。
- `EventRecord(event_type="multi_view_consensus_result")`：同一 object 被多个 camera 检出时生成。
- `EventRecord(event_type="cross_view_conflict")`：同一 local track 关联多个 object 时生成。

`metadata.images[]` 推荐字段：

```text
camera_vehicle_name
camera_name
ok
saved
path
width
height
```

D6 当前转换为 `LinkRecord(payload_kind="video_metadata")`。`metadata.images[].path` 是否存在只进入 `png_saved` 元数据；PNG 不参与指标计算。

### 3.2 `blocks_sensor_observations.jsonl`

每行代表一个 D1 replay observation 或传感/通信样本。D6 当前消费字段：

```text
observation_id
sensor_id
modality
measurement_timestamp
arrival_timestamp
metadata.truth_id
metadata.source_node_id
metadata.target_node_id
metadata.sequence_id
metadata.delivered
metadata.stale_after_s
communication.*
```

`communication` 推荐字段：

```text
source_node_id
target_node_id
relay_node_id
link_type
payload_kind
sequence_id
sent_timestamp
received_timestamp
delivered
stale_after_s
```

D6 当前转换为：

- delivered 且带 `metadata.truth_id` 的 observation -> `TrackRecord`。
- 每条 observation -> `LinkRecord`，用于 `cross_node_latency_ms`、`message_drop_rate`、`out_of_order_count`、`stale_track_update_count`。

必须保留 `measurement_timestamp` 与 `arrival_timestamp`。这既是 D1 时间合同，也是 D6 stale/latency 指标的来源。

## 4. D4/D5/D7 AirSim 产物回灌与长期治理状态

### 4.1 D4

D6 已实现：

- 读取 D4 active-degradation CSV。
- 从 event/control metadata 识别 active/passive failover、secondary takeover、secondary reassignment、D4 reassign pending、distributed fallback。
- 输出 `active_degradation_count`、`passive_failover_count`、`secondary_node_takeover_count`、`secondary_reassignment_count`、`d4_reassign_pending_count`、`distributed_fallback_count`、`failover_active_window_delta_s`。

长期 producer schema 治理：

- 在真实 AirSim episode 中持续写出 D4 decision/event 日志。
- 写入 `trigger_timestamp`、`decision_timestamp`、`selected_coordinator`、`coverage_cell`、`review_label`。
- 固定 pre/post 窗口统计，才能正式输出主动降级必要性和改善 delta。

### 4.2 D5

D6 已实现：

- `TerminalRecord` 末端准确率、local ID switch、FOV 歧义、friend overlap hold、lock time。
- Blocks bbox/camera metadata 的无 PNG 多视角基线。
- `multi_view_consensus_rate`、`cross_view_conflict_count`、`duplicate_terminal_lock_count`。

长期 producer schema 治理：

- 把 D5 terminal association、identity claim、cross-view conflict、duplicate lock、friend overlap hold 和 terminal-center disagreement 事件写成 D6 可读 JSONL/CSV。
- 保留 `assigned_global_track_id`、`local_track_id`、`resource_id/camera_id`、validation label、bbox、相机内外参和 timestamp。
- 确保在线 D5 不使用 AirSim truth ID；truth/validation label 只在离线日志或 D6 评估阶段使用。

### 4.3 D7

D6 已实现：

- 读取 D7 `control_commands.csv`、`intercept_summary.json`、`guidance_records.csv`、`guidance_summaries.json`。
- 输出 gate pass rate、terminal switch allowed/reject、visual PNG switch、terminal takeover、mode switch、terminal contract reject、intercept success/counts、min range、time to intercept。
- 将 guidance law、D4/D5 state、plan/version、reject reason 写入 `EpisodeMetrics.metadata`。

main/orchestrator 已完成的接线：

- 截至 2026-07-07，真实 AirSim 拦截执行后的 `control_commands.csv` 与 `intercept_summary.json` 已合并到正式 `main_episode_bus_metrics.json`。
- 执行前合同检查结果另存为 `main_episode_bus_contract_metrics.json`，用于诊断 terminal contract、D4 reassign pending、D5 gate 等，不再覆盖正式执行结果。
- 正式指标可同时看到 D7 执行结果与 `guidance_law_counts`，避免“执行前集成指标”和“执行后拦截指标”分裂。

长期 producer schema 治理：

- 在每个 integrated AirSim episode 中稳定产出这些 D7 文件。
- 保持 D3 assignment plan version、D4 action/state、D5 terminal state 和 D7 guidance law 的同一时间轴。
- 在多 seed、5v5/N-v-N 和非默认 episode 中维持同样的正式 metrics 合并口径，而不是仅保留独立 D7 报告。

## 5. Integrated Episode Metrics 的推荐流程

main runtime 推荐按以下顺序写盘和评估：

1. 启动或复用 AirSim Blocks，按 reset 分隔 episode。
2. 写出 `blocks_frames.jsonl` 和 `blocks_sensor_observations.jsonl`。
3. 写出 D4 decision/event CSV/JSONL。
4. 写出 D5 terminal/multi-view JSONL 或转换后的 D6 `terminal/event/link` 记录。
5. 写出 D7 `guidance_records.csv`、`guidance_summaries.json`、`control_commands.csv`、`intercept_summary.json`。
6. main 调用 D6 loaders，把所有记录合并进一个 `MetricsCollector`；若执行了真实拦截，还要把 D7 execution metrics 写入正式 `main_episode_bus_metrics.json`，并保留 raw `main_episode_bus_contract_metrics.json`。
7. 调用 `compute_episode()`，传入同一 `truth_summary`、`episode_id`、`seed/batch_seed` 和实际规模字段。
8. 批量调用 `ReportGenerator` 输出 CSV、Markdown、PNG。

D6 代码已经具备第 6-8 步的模块能力，并已在本批正式产物上完成实际消费和统一报告。AirSim 启停、episode 顺序、跨文件合并调度和正式/contract metrics 文件写盘继续属于 main runtime；后续工作是长期 schema 与趋势治理，不是首次接入。

## 6. 时间、坐标和规模合同

时间：

- 所有流使用 episode 内单调秒级时间。
- 外部 timestamp 应转换为 `episode_time = source_timestamp - episode_start_timestamp`。
- `measurement_timestamp` 和 `arrival_timestamp` 必须保留。

坐标：

- D6 不做控制坐标转换。
- NED 是 D1/D6 融合和评估工作帧。
- WGS84 只作为外部参考；若进入 D6，需要先由上游转换或同时标注 frame。

规模：

- `drone_count/resource_count/target_count/camera_count` 必须来自日志字段或可验证记录集合。
- `2v2/5v5` 只作为场景名和 baseline label，不能当成规模分母。
- N-v-N episode 必须显式记录实际资源、目标和相机数量。

## 7. PNG 与视觉 metadata 策略

D6 不需要 PNG 截图来计算默认指标。PNG 只作为调试或人工复核证据。默认指标依赖：

```text
bbox_xyxy
camera_intrinsics
camera_extrinsics
timestamp
resource_id
camera_id
local_track_id
assigned_global_track_id
object_name
truth_label / validation_label
gate outcome
```

`visual_png_switch_count` 的 “PNG” 指导引模式/视觉 PNG 切换含义，不表示必须保存 PNG 图像文件。

## 8. 未实现项

### 8.1 AirSim 原生 recording parser

未实现。当前只支持 main runtime 的 Blocks JSONL。原因：

- Blocks JSONL 已包含 D6 需要的 truth、camera、bbox、observation 和 communication metadata。
- AirSim 原生 recording 字段和版本差异大，需要单独的 schema 样例。
- 原生 recording 到 NED、camera frame、resource ID、target ID 和 episode clock 的映射尚未固定。

缺少条件：

- 至少一个原生 recording 样例目录。
- 字段版本说明。
- 坐标和时间对齐规则。
- 与 Blocks JSONL 对照的测试 fixture。

### 8.2 Live AirSim replay/API

未实现，且不属于 D6 默认目标。D6 不应连接 live AirSim 或控制车辆。若未来需要 replay，仍应由 main runtime 执行 replay 并导出 D6 可读日志。

### 8.3 SCRIMMAGE 统计接口

未实现。原因：

- 当前仿真主线是 AirSim Blocks 和合成日志。
- 仓库没有 SCRIMMAGE message schema、episode 输出或 ID 映射样例。
- SCRIMMAGE 的通信/资源/目标/episode clock 需要独立映射。

缺少条件：

- SCRIMMAGE 输出样例。
- agent/resource/target ID 映射。
- 通信事件字段。
- episode clock 对齐规则。
- 批量目录结构和 CI fixture。

## 9. 验证建议

当前文档对应的 D6 全量回归基线为 `115 passed`。后续批次重点验证 source 行数、availability、逐时刻 provenance 和失败原因 taxonomy 的稳定性，不重新把已消费的正式 AirSim 产物标为待接入。

D6 模块测试：

```bash
pytest -q research_modules/d6_evaluation_metrics/tests
```

文档和空白检查：

```bash
git diff --check -- research_modules/d6_evaluation_metrics subagent_reviews/D6_*
```

AirSim 集成验收样例应至少覆盖：

- `blocks_frames.jsonl` 不保存 PNG 时仍能计算 detection、terminal、multi-view 和规模字段。
- `blocks_sensor_observations.jsonl` 能计算 latency/drop/stale。
- D4 active-degradation CSV 能生成 active/passive/secondary/pending 指标。
- D5 terminal/multi-view 事件能进入 terminal metrics。
- D7 control/guidance/intercept 文件能进入 gate/intercept metrics。
- `scenario_name="5v5"` 但实际 `resource_count/target_count/camera_count` 不等于 5 时，D6 按实际字段输出。
