# D6 系统级评估指标体系：算法原理与实施方案

## 1. 模块定位

D6 是系统级离线评估模块，负责消费 D1-D5 产生的记录、仿真日志和评估真值，输出可复现的指标、表格、报告和曲线。D6 不参与实时任务决策，不发布控制指令，不提供火控参数，不建模毁伤效果，不自动处置目标，也不绕过人工授权。

本模块解决的问题不是“某次是否成功”，而是“系统在哪个环节稳定、在哪个环节失效”。因此不能只报告命中率。单一命中率会掩盖探测虚警、航迹断裂、ID Switch、重复分配、降级接管失败、末端误配准、跨节点通信异常、D7 末端切换门控失败和安全约束触发等问题。D6 将这些问题拆成八类指标：探测、跟踪、分配、降级、末端配准、通信链路、导引门控和安全约束。

## 2. 输入输出

### 2.1 输入记录

| 输入类型 | 数据类 | 来源模块 | 主要字段 |
|---|---|---|---|
| 航迹记录 | `TrackRecord` | D1/D2 | `timestamp`, `global_track_id`, `truth_id`, `position`, `truth_position`, `covariance_trace`, `track_state` |
| 分配记录 | `AssignmentRecord` | D3/D4 | `timestamp`, `plan_id`, `version`, `resource_id`, `global_track_id`, `authorization_state`, `active`, `truth_id` |
| 系统事件 | `EventRecord` | D1-D5/仿真器 | `timestamp`, `event_type`, `actor_id`, `value`, `metadata` |
| 通信记录 | `LinkRecord` | C2/二级节点/拦截机/仿真器 | `source_node_id`, `target_node_id`, `link_type`, `payload_kind`, `sent_timestamp`, `received_timestamp`, `sequence_id`, `delivered` |
| 末端记录 | `TerminalRecord` | D5 | `resource_id`, `assigned_global_track_id`, `local_track_id`, `decision_state`, `friend_conflict_state`, `association_correct` |
| 真值摘要 | `truth_summary` | 仿真器/离线标注 | `truth_timestamps`, `high_threat_ids`, `high_threat_by_timestamp`, `scenario` |

所有输入都必须是离线记录。D6 可以消费 AirSim 回放、JSONL、CSV 或其他算法输出转换后的数据，但不连接实时控制接口。

### 2.2 输出产物

| 输出 | 位置 | 用途 |
|---|---|---|
| `EpisodeMetrics` | 内存对象/CSV | 单 episode 标量指标 |
| `episode_metrics.csv` | `outputs/*/` | 每个 episode 一行，便于统计检验 |
| `summary_metrics.csv` | `outputs/*/` | 均值、标准差、置信区间和分位数 |
| `batch_report.md` | `outputs/*/` | 自动生成的中文批量报告 |
| `plots/*.png` | `outputs/*/plots/` | 分类指标柱状图和关键指标分布曲线 |

## 3. 指标体系与事件来源

### 3.1 探测指标

设 `TP` 为与真值匹配的探测记录数，`FP` 为虚警记录数，`FN` 为真值存在但未被探测到的机会数，`T` 为 episode 时长。

```text
detection_probability = TP / (TP + FN)
false_alarm_rate = FP / T
missed_detection_rate = FN / (TP + FN)
```

事件来源：

- `TrackRecord.truth_id != None` 计入候选 `TP`。
- `TrackRecord.truth_id == None` 或 `EventRecord.event_type == "false_alarm"` 计入 `FP`。
- `truth_summary.truth_timestamps` 定义每个目标在每个时间戳的真值机会。

解释要点：探测概率高但虚警率高，会给 D2 关联和 D3 分配制造额外负担；漏检率低但航迹不连续，也可能导致后续交接失败。

### 3.2 跟踪指标

位置误差使用真值位置和估计位置的欧氏距离：

```text
track_rmse = sqrt(mean(||p_est - p_truth||^2))
track_continuity = matched_truth_timestamps / truth_timestamps
id_switch_count = count(global_track_id changes for the same truth_id)
```

事件来源：

- `TrackRecord.position` 与 `TrackRecord.truth_position` 计算 `track_rmse`。
- `TrackRecord.truth_id` 与 `truth_summary.truth_timestamps` 计算 `track_continuity`。
- 对同一 `truth_id` 按时间排序，若 `global_track_id` 改变，则累加 `id_switch_count`。

解释要点：RMSE 衡量几何精度，continuity 衡量覆盖稳定性，ID Switch 衡量身份保持能力。多目标交叉场景中，即使 RMSE 不高，ID Switch 也可能导致 D3 分配到错误目标。

### 3.3 分配指标

```text
duplicate_assignment_count =
  count(targets assigned to more than one active resource in the same plan snapshot)

unassigned_high_threat_count =
  count(high_threat targets without an effective active assignment)
```

事件来源：

- `AssignmentRecord.active == True`。
- `authorization_state` 必须在 `recorded/authorized/approved/human_approved/operator_approved` 等有效状态内。
- `truth_summary.high_threat_by_timestamp` 或 `high_threat_ids` 定义评估侧高威胁目标集合。

解释要点：D6 只统计分配结果，不生成新分配。未授权的候选分配不会被算作有效分配，避免把“待审批方案”误计为“已执行方案”。

### 3.4 降级指标

```text
failover_time = t(degraded_stable) - t(central_failure)
consensus_rounds = mean(consensus_round event values)
degraded_completion_rate =
  degraded_task_completed / (degraded_task_completed + degraded_task_failed)
```

事件来源：

- `central_failure` 或 `coordinator_failure` 标记中心失效。
- `degraded_stable` 或 `failover_stable` 标记降级模式稳定。
- `consensus_rounds` 的 `value` 或 `metadata.rounds` 提供协商轮数。
- `degraded_task_completed/failed/cancelled` 统计降级任务完成率。

D4 后续扩展建议：在 `EventRecord.metadata` 中透传 `coordination_mode`, `leader_role`, `coverage_cell`。这样 D6 可以区分“中心节点失效后由二级侦察节点接管”和“完全无中心 CBBA/拍卖式协商”的性能差异。

#### 3.4.1 主动降级评估指标

D4 主动降级不同于被动故障接管。被动降级由中心节点、二级节点或通信链路失效触发；主动降级由系统质量风险触发，例如 D1 定位不确定度升高、D2 关联风险升高、D3 分配冲突、D5 末端与中心航迹不一致。D6 的职责是离线评估主动降级是否必要、是否过度，以及是否减少错误绑定、ID Switch 和重复分配。

建议新增以下 D6 侧离线指标：

| 指标 | 定义 | 解释 |
|---|---|---|
| `passive_failover_count` | `count(degradation_mode == passive)` | 被动故障接管次数，用于与主动降级分开统计 |
| `active_degradation_count` | `count(degradation_mode == active)` | 主动降级决策次数 |
| `secondary_reassignment_count` | `count(secondary_reassignment / degrade_to_secondary / request_secondary_assist)` | 二级节点重分配次数；兼容 D4 `action=request_secondary_assist` 与 Blocks `assignment_phase=secondary_reassignment` |
| `d4_reassign_pending_count` | `count(d4_reassign_pending reject/event/metadata)` | D4 重分配未完成导致 D7 末端切换暂拒次数 |
| `active_degradation_precision` | `necessary_active_degradation_count / active_degradation_count` | 主动降级的必要性精度，越高说明越少过度触发 |
| `unnecessary_active_degradation_count` | `count(active degradation labelled unnecessary)` | 离线复核为不必要的主动降级次数 |
| `terminal_center_disagreement_count` | `count(terminal_center_disagreement events)` | D5 末端局部关联与中心航迹/分配不一致的次数 |
| `time_to_active_degradation_decision` | `t(active_degradation_decision) - t(first_risk_trigger)` | 从风险信号出现到主动降级决策的延迟 |
| `post_degradation_id_switch_delta` | `id_switch_rate_after - id_switch_rate_before` | 主动降级前后 ID Switch 变化，负值表示改善 |
| `post_degradation_assignment_conflict_delta` | `duplicate_assignment_rate_after - duplicate_assignment_rate_before` | 主动降级前后重复分配冲突变化，负值表示改善 |

`active_degradation_precision` 需要离线必要性标签或一致的后验判据。推荐优先使用评估标签：

```text
necessary_active_degradation_count =
  count(active degradation with metadata.review_label == necessary)

active_degradation_precision =
  necessary_active_degradation_count / max(active_degradation_count, 1)
```

当没有人工或规则复核标签时，可用保守后验判据生成研究用标签：若主动降级前窗口内存在明确风险触发，且降级后窗口内 `id_switch_rate`、`duplicate_assignment_rate`、`terminal_ambiguous_or_hold_rate` 至少一项下降，同时 `track_continuity` 未显著恶化，则暂记为 `necessary_candidate`。该标签只用于离线统计，不得用于在线自动处置或授权。

前后窗口建议：

```text
pre_window  = [t_decision - W_pre, t_decision)
post_window = [t_stable, t_stable + W_post]

id_switch_rate_before = id_switch_count(pre_window) / window_duration
id_switch_rate_after  = id_switch_count(post_window) / window_duration

duplicate_assignment_rate_before = duplicate_assignment_count(pre_window) / plan_snapshot_count(pre_window)
duplicate_assignment_rate_after  = duplicate_assignment_count(post_window) / plan_snapshot_count(post_window)
```

`W_pre` 和 `W_post` 的默认建议为 5-15 秒，正式实验中应固定窗口长度，并在报告中说明。若 `t_stable` 不存在，则该次主动降级只计入决策次数和未完成降级，不参与后窗口改善率统计。

#### 3.4.2 主动降级日志字段合同

主动降级可统一通过 `EventRecord` 进入 D6。推荐事件类型：

| 事件类型 | 触发模块 | 用途 |
|---|---|---|
| `degradation_risk_trigger` | D1/D2/D3/D5 | 记录主动降级前的风险信号 |
| `active_degradation_decision` | D4 | 记录 D4 已做出主动降级决策 |
| `passive_failover_start` | D4 | 记录被动故障接管开始 |
| `degraded_stable` | D4 | 记录降级状态稳定 |
| `terminal_center_disagreement` | D5/D4 | 记录末端局部关联与中心态势不一致 |
| `degradation_review_label` | D6/离线复核 | 记录离线必要性标签 |

必需或推荐的 `EventRecord.metadata` 字段：

| 字段 | 取值 | 含义 |
|---|---|---|
| `degradation_mode` | `passive` 或 `active` | 区分被动故障接管和主动质量降级 |
| `trigger_sources` | `d1_uncertainty`, `d2_association`, `d3_assignment`, `d5_terminal`, `mixed` | 主动降级触发源；多源同时触发时使用 `mixed`，并可附 `source_details` |
| `selected_coordinator` | `center`, `secondary_node`, `distributed_cbba` | 降级后由谁负责协调；只表示离线状态，不表示 D6 发出指令 |
| `coverage_cell` | 例如 `north_sector` | 二级节点或局部分布式协商覆盖的小区 |
| `arbiter_score` | `0.0-1.0` 或实现定义标量 | D4 仲裁器给出的主动降级风险分数 |
| `trigger_timestamp` | 秒 | 最早风险触发时间，用于计算决策延迟 |
| `decision_timestamp` | 秒 | 主动降级决策时间；通常等于事件 `timestamp` |
| `review_label` | `necessary`, `unnecessary`, `unknown` | 离线复核标签，用于计算主动降级精度 |
| `source_scores` | dict | D1-D5 各风险源分数，例如定位协方差、关联熵、分配冲突率、末端不一致分数 |

示例：

```python
EventRecord(
    timestamp=42.8,
    event_type="active_degradation_decision",
    actor_id="d4_arbiter",
    metadata={
        "degradation_mode": "active",
        "trigger_sources": "mixed",
        "selected_coordinator": "secondary_node",
        "coverage_cell": "north_sector",
        "arbiter_score": 0.82,
        "trigger_timestamp": 40.9,
        "decision_timestamp": 42.8,
        "source_scores": {
            "d1_uncertainty": 0.71,
            "d2_association": 0.76,
            "d3_assignment": 0.34,
            "d5_terminal": 0.88,
        },
    },
)
```

D6 只消费这些字段进行离线统计；不根据 `arbiter_score` 生成实时切换、控制或处置动作。

### 3.5 末端配准指标

```text
terminal_association_accuracy =
  correct_terminal_associations / terminal_association_attempts

terminal_id_switch_count =
  count(local_track_id changes for the same assigned_global_track_id)

ambiguous_fov_event_count =
  count(unique ambiguous terminal field-of-view events)

friend_overlap_hold_count =
  count(unique friend-overlap hold events)

time_to_terminal_lock =
  first locked time - first fov_entry time
```

事件来源：

- `TerminalRecord.association_correct` 或 `expected_global_track_id` 判断末端配准是否正确。
- 同一 `assigned_global_track_id` 下 `local_track_id` 变化计入 `terminal_id_switch_count`。
- `TerminalRecord.ambiguity_score >= ambiguous_fov_threshold` 或 `EventRecord.event_type == "ambiguous_fov"` 计入视场歧义。
- `friend_conflict_state` 为 hold/overlap 类状态，或 `friend_overlap_hold` 事件，计入友方重叠 hold。
- `decision_state == "fov_entry"` 到 `"locked"` 的时间差计入锁定时间。

D5 后续扩展建议：增加 `recon_cue_used_count`，用于统计二级侦察节点图像 cue 被 D5 采纳为辅助证据的次数。该指标应只说明 cue 被用于离线配准评估，不代表自动授权或局部节点改写 `global_track_id`。

#### 3.5.1 多视角与无 PNG 评估

main 通信假设允许拦截机之间、拦截机与中心/二级节点、拦截机与系留无人机、系留无人机与中心之间进行数据或视频元数据通信。D6 不需要保存 PNG 截图即可评估多视角末端关联，只要求日志保留：

```text
timestamp
resource_id / producer_node_id / consumer_node_id
camera_id / stream_id
bbox_xyxy
camera_intrinsics
camera_extrinsics
assigned_global_track_id
object_name
truth_label / validation_label
```

新增多视角指标：

```text
multi_view_consensus_rate =
  successful multi_view_consensus events / consensus attempts

cross_view_conflict_count =
  count(cross_view_conflict or metadata.cross_view_conflict)

duplicate_terminal_lock_count =
  count(same timestamp and same assigned_global_track_id locked by multiple resources)

terminal_lock_count =
  count(unique terminal_lock events or TerminalRecord decision_state == locked)
```

这些指标用于解释末端关联错误、重复锁定和 D4 主动降级触发原因。视频元数据可以来自中心、二级系留节点、拦截机或拦截机间转发；D6 只统计链路和一致性，不改变 `global_track_id` 或 `AssignmentPlan`。

### 3.6 通信链路指标

`LinkRecord` 是可选输入。如果集成侧已经使用 `EventRecord` 统一记录事件，也可以把同名字段放入 `EventRecord.metadata`。D6 会把两者归一化为通信样本。

```text
cross_node_latency_ms =
  mean((received_timestamp - sent_timestamp) * 1000)

message_drop_rate =
  dropped_messages / attempted_messages

out_of_order_count =
  explicit out_of_order events + decreasing sequence IDs per stream

stale_track_update_count =
  count(track payload latency > stale_after_s)

video_metadata_delivery_rate =
  delivered video_metadata payloads / attempted video_metadata payloads

bbox_delivery_rate =
  delivered bbox payloads / attempted bbox payloads

consensus_latency_s =
  mean(consensus_start_to_stable latency or consensus/bid link latency)
```

推荐 `EventRecord.metadata` / `LinkRecord` 字段：

```text
source_node_id
target_node_id
relay_node_id
link_type: c2_direct | secondary_relay | interceptor_peer | video_cue
message_type
sequence_id
sent_timestamp
received_timestamp
measurement_timestamp
arrival_timestamp
payload_kind: track | bbox | video_metadata | assignment | terminal_association | bid
delivered
stale_after_s
```

### 3.7 D7 PNG Gate 与末端切换门控指标

D7 中段到末端的切换需要同时满足身份一致、相机质量、LOS 质量、机动余量和窗口条件。D6 从 D7 control command 或 event metadata 中读取门控结果：

```text
guidance_law
terminal_switch_reject_reason
camera_quality_gate_pass
los_quality_gate_pass
maneuver_margin_gate_pass
terminal_switch_allowed
```

对应指标：

```text
camera_quality_gate_pass_rate
los_quality_gate_pass_rate
maneuver_margin_gate_pass_rate
terminal_switch_allowed_rate
visual_png_switch_count
terminal_takeover_rate
terminal_switch_reject_count
```

其中 `terminal_switch_allowed_rate` 的口径为 `terminal_switch_allowed=True` 的 D7 control command 数 / 有 `terminal_switch_allowed` 字段的 D7 control command 数；空缺字段不进入分母。`visual_png_switch_count` 统计显式 `visual_png_switch` / `vision_png_switch` / `d7_visual_png_switch` 事件，或 `guidance_law=png_vm/png_ttc` 且伴随 `mode_switch=True`、`terminal_mode_entered=True` 或 `mode=vision_terminal/visual_png/vision_png` 的 D7 记录。`terminal_takeover_rate` 按 episode 内 unique `(resource_id, target_id)` pair 计算，pair 出现 `terminal_locked=True`、`terminal_switch_allowed=True`、`vision_terminal` mode、`terminal_mode_entered=True`，或 `guidance_law` 为 `png_vm` / `png_ttc` / `los` 时记为已由末端接管；分母优先使用 `intercept_summary.json` 的 `pair_count`，否则使用已观测 pair 数。`terminal_handover_pending` 和 `detection_seen` 只表示接管候选或探测可见，不能单独算作 takeover。`terminal_switch_reject_reason` 会进入 `EpisodeMetrics.metadata["terminal_switch_reject_reasons"]`，去重到 pair 维度的拒绝原因会进入 `EpisodeMetrics.metadata["terminal_switch_reject_reason_pair_counts"]`；`guidance_law` 会进入 `EpisodeMetrics.metadata["guidance_law_counts"]`，pair 维度最后一次导引律会进入 `EpisodeMetrics.metadata["guidance_law_pair_counts"]`，用于报告 PN/LOS/Pure Pursuit 等导引律在不同门控条件下的分布。PNG 不作为必需输入；只要检测框、相机参数、时间戳和门控结果可追溯，D6 就能完成离线评估。

### 3.8 安全约束指标

```text
constraint_violation_count = count(safety constraint violation events)
human_override_count = count(human override/rejection events)
```

事件来源：

- `constraint_violation` 或 `safety_constraint_violation`。
- `human_override`, `human_reject`, `human_rejection`, `operator_override`。

解释要点：安全事件是一级指标，不应被总体成功率平均掉。即使其他指标良好，安全约束频繁触发也说明策略不可接受或评估场景设置过激。

## 4. 与 OSPA、CLEAR MOT、MOTA/MOTP 的关系

标准多目标跟踪评估中常见三类指标：

- OSPA：同时度量定位误差和目标数量误差，适合比较不同多目标估计器的集合误差。
- CLEAR MOT：将漏检、虚警、ID Switch 和定位误差统一到 MOT 指标框架。
- MOTA/MOTP：MOTA 侧重综合准确率，MOTP 侧重匹配目标的定位精度。

典型公式如下：

```text
MOTP = sum_t sum_i d(t, i) / sum_t m_t

MOTA = 1 - sum_t(FN_t + FP_t + IDSW_t) / sum_t GT_t
```

OSPA 对真值集合 `X` 和估计集合 `Y` 定义截断距离和阶数：

```text
OSPA_p,c(X,Y) =
  (1/n * (min_pi sum_i min(c, d(x_i, y_pi(i)))^p + c^p * |n-m|))^(1/p)
```

本项目保留这些指标作为对照和后续扩展，但默认输出更可解释的工程指标，原因是：

1. D1-D5 的工程问题跨越探测、分配、降级和末端身份认证，不只是 MOT benchmark。
2. MOTA 这类综合指标容易把严重安全事件或少量 ID Switch 平均掉。
3. 工程排障需要知道问题来自虚警、漏检、ID 交换、重复分配、降级慢还是末端歧义。
4. 当前代码实现的指标可直接从 D1-D5 日志字段计算，便于单元测试和批量实验复现。

## 5. 实施流程

```text
离线日志/仿真真值
        |
        v
适配器转换为 TrackRecord / AssignmentRecord / EventRecord / LinkRecord / TerminalRecord
        |
        v
MetricsCollector.add_*()
        |
        v
compute_episode(episode_id, seed, duration, truth_summary)
        |
        v
EpisodeMetrics
        |
        v
ReportGenerator -> CSV / Markdown / PNG 图表
```

核心流程：

1. 对齐时间轴，将所有源数据转换为 episode 内单调秒级时间。
2. 将 D1-D7 日志转换为 D6 数据类。
3. 提供 `truth_summary`，至少包含真值时间戳；若要评估高威胁未分配，需提供高威胁集合。
4. 调用 `MetricsCollector.compute_episode()` 生成单 episode 指标。
5. 批量运行多个随机种子和场景因素。
6. 使用 `ReportGenerator` 生成表格、Markdown 报告和曲线。

## 6. 关键接口

### 6.1 指标收集器

```python
collector = MetricsCollector(ambiguous_fov_threshold=0.6)
collector.add_track(track_record)
collector.add_assignment(assignment_record)
collector.add_event(event_record)
collector.add_link(link_record)
collector.add_terminal(terminal_record)

metrics = collector.compute_episode(
    episode_id="case_001",
    seed=1,
    duration=60.0,
    truth_summary=truth_summary,
)
```

### 6.2 报告生成器

```python
report_generator = ReportGenerator()
report_generator.write_episode_csv(episodes, "episode_metrics.csv")
report_generator.write_summary_csv(episodes, "summary_metrics.csv")
report_generator.write_markdown_report(episodes, "batch_report.md")
report_generator.write_plots(episodes, "plots")
```

### 6.3 批量脚本

```bash
python3 research_modules/d6_evaluation_metrics/scripts/run_batch_example.py --seeds 100
```

输出默认位于：

```text
research_modules/d6_evaluation_metrics/outputs/example_batch/
```

## 7. 参数与调参建议

| 参数/字段 | 默认或建议 | 调参影响 |
|---|---:|---|
| `ambiguous_fov_threshold` | `0.6` | 越低越容易计入视场歧义，适合保守评估；越高则只统计严重歧义 |
| 批量随机种子数 | `100` | 种子越多，均值和置信区间越稳定，计算和报告体积增加 |
| episode 时长 | `60 s` 示例 | 时间越长越能暴露长尾 ID Switch 和降级恢复问题 |
| 高威胁标签粒度 | 按时间戳提供优先 | `high_threat_by_timestamp` 比静态 `high_threat_ids` 更适合动态场景 |
| 虚警事件来源 | 记录或事件均可 | 若同时记录，需在上游避免重复标注同一虚警 |

建议在正式对比中固定以下条件：随机种子列表、目标数量、噪声水平、遮挡概率、中心故障时间、二级节点可用性、终端视场歧义概率。每次只改变一个算法变量，便于解释差异来源。

## 8. 批量实验设计

批量实验至少包含三层设计：

| 层级 | 示例因素 | 目的 |
|---|---|---|
| 场景因素 | 目标数量、目标密度、机动强度、遮挡概率 | 验证算法在不同难度下的稳定性 |
| 系统因素 | 探测噪声、D2 关联器、D3 分配权重、D4 降级模式、D5 cue 可用性 | 比较不同工程方案 |
| 随机因素 | 固定随机种子集合 | 估计均值、标准差和置信区间 |

统计输出包括：

```text
mean
sample_std
stderr = sample_std / sqrt(N)
ci95 = mean +/- 1.96 * stderr
median
p05 / p95
```

当指标偏态明显时，例如 `id_switch_count` 或 `constraint_violation_count` 大量为 0、少数 episode 很高，应额外采用 bootstrap 置信区间或非参数检验。当前实现先输出可解释的基础统计量，并在报告中提示长尾风险。

### 8.1 主动降级批量评估设计

主动降级应按“降级前后窗口”做成对比较，而不是只统计触发次数。推荐每个 episode 记录所有 `active_degradation_decision`，并围绕每个决策构造前后窗口：

```text
pre_window  = [t_decision - W_pre, t_decision)
post_window = [t_stable, t_stable + W_post]
```

批量报告应至少输出以下对比：

| 对比项 | 前窗口 | 后窗口 | 期望方向 |
|---|---|---|---|
| ID Switch | `id_switch_rate_before` | `id_switch_rate_after` | 下降 |
| 重复分配 | `duplicate_assignment_rate_before` | `duplicate_assignment_rate_after` | 下降 |
| 末端歧义 | `ambiguous_fov_rate_before` | `ambiguous_fov_rate_after` | 下降 |
| 友方 hold | `friend_overlap_hold_rate_before` | `friend_overlap_hold_rate_after` | 不上升或下降 |
| 末端 reacquire | `terminal_reacquire_rate_before` | `terminal_reacquire_rate_after` | 下降 |
| 任务连续性 | `track_continuity_before` | `track_continuity_after` | 不显著下降 |

建议分组维度：

- `degradation_mode`: `passive` vs `active`。
- `trigger_sources`: D1 不确定度、D2 关联风险、D3 分配失效、D5 末端不一致、mixed。
- `selected_coordinator`: center、secondary_node、distributed_cbba。
- `coverage_cell`: 二级节点或局部分布式覆盖区域。
- `arbiter_score` 分桶：例如 `[0.5, 0.7)`, `[0.7, 0.85)`, `[0.85, 1.0]`。

关键解释原则：

1. `active_degradation_count` 高但 `active_degradation_precision` 低，说明主动降级过度。
2. `post_degradation_id_switch_delta` 和 `post_degradation_assignment_conflict_delta` 均为负，说明主动降级可能降低身份错配和分配冲突。
3. 若冲突下降但 `track_continuity` 明显下降，说明降级可能过于保守，需要 D4 调整仲裁阈值。
4. 若 `terminal_center_disagreement_count` 高但主动降级未触发，说明 D5-D4 的风险上报或 D4 仲裁阈值可能偏钝。
5. 若 `selected_coordinator=distributed_cbba` 时共识轮数过高，应单独报告通信和一致性成本。

## 9. 图表与曲线

现有批量示例生成以下图表：

- 探测指标图：`outputs/example_batch/plots/detection_metrics.png`
- 跟踪指标图：`outputs/example_batch/plots/tracking_metrics.png`
- 分配指标图：`outputs/example_batch/plots/assignment_metrics.png`
- 降级指标图：`outputs/example_batch/plots/degradation_metrics.png`
- 末端指标图：`outputs/example_batch/plots/terminal_metrics.png`
- 安全指标图：`outputs/example_batch/plots/safety_metrics.png`
- 关键指标分布曲线：`outputs/example_batch/plots/selected_metric_distributions.png`

根目录 `EXPERIMENT_REPORT.md` 已引用这些图表。D6 的图表用于观察均值、置信区间和长尾分布，不用于实时决策。

## 10. 与 D1-D5 的接口关系

| 模块 | D6 消费内容 | 评估重点 |
|---|---|---|
| D1 多传感器融合 | `TrackRecord`, 协方差摘要、真值匹配 | 探测概率、虚警率、RMSE、协方差相关诊断 |
| D2 多目标关联 | 稳定 `global_track_id`、ID 变更日志 | `id_switch_count`, `track_continuity` |
| D3 集中式分配 | `AssignmentRecord`, plan version, 授权状态 | 重复分配、高威胁未分配、版本有效性 |
| D4 降级接管 | `EventRecord`, consensus rounds, degraded task events | 接管时间、协商轮数、降级完成率 |
| D5 末端配准 | `TerminalRecord`, 友方冲突和歧义事件 | 末端配准准确率、终端 ID Switch、hold 和 lock 时间 |

跨模块硬约束：

- D6 只读取日志，不回写任务、航迹或分配。
- 上游必须保留时间戳、版本和授权状态；否则 D6 只能给出不完整统计。
- 高威胁标签和真值标签是评估侧标注，不能被 D6 用于在线决策。
- 本地终端身份和 `global_track_id` 的一致性由 D5 负责，D6 只统计结果。

## 11. D4/D5 新扩展的日志建议

D4 的二级节点降级链路建议增加以下事件元数据：

```python
EventRecord(
    timestamp=t,
    event_type="degraded_stable",
    actor_id="secondary_recon_01",
    metadata={
        "coordination_mode": "secondary_node",
        "leader_role": "secondary_recon",
        "coverage_cell": "north_sector",
    },
)
```

D6 后续可基于这些字段输出分组统计：

- 二级节点接管平均 `failover_time`。
- 完全无中心 CBBA 的平均 `consensus_rounds`。
- 不同 `coverage_cell` 的降级完成率。

D4 主动降级建议沿用同一 `EventRecord` 通道，但必须显式区分 `degradation_mode`：

```python
EventRecord(
    timestamp=t_decision,
    event_type="active_degradation_decision",
    actor_id="d4_arbiter",
    metadata={
        "degradation_mode": "active",
        "trigger_sources": "d2_association",
        "selected_coordinator": "secondary_node",
        "coverage_cell": "north_sector",
        "arbiter_score": 0.79,
        "trigger_timestamp": t_first_trigger,
        "review_label": "unknown",
    },
)
```

被动降级建议写成：

```python
EventRecord(
    timestamp=t_failure,
    event_type="passive_failover_start",
    actor_id="c2_health_monitor",
    metadata={
        "degradation_mode": "passive",
        "trigger_sources": "c2_failure",
        "selected_coordinator": "secondary_node",
        "coverage_cell": "north_sector",
    },
)
```

主动降级复核标签建议由离线评估脚本或人工复核写入，不应由实时节点在运行时自证：

```python
EventRecord(
    timestamp=t_review,
    event_type="degradation_review_label",
    actor_id="offline_evaluator",
    metadata={
        "decision_event_id": "active_deg_0042",
        "review_label": "necessary",
        "reason": "post-window id_switch and duplicate assignment rates decreased",
    },
)
```

D5 的二级侦察图像 cue 建议增加以下终端或事件字段：

```python
EventRecord(
    timestamp=t,
    event_type="recon_cue_used",
    actor_id="R03",
    metadata={
        "producer_node_id": "secondary_recon_01",
        "assigned_global_track_id": "G12",
        "coverage_cell": "north_sector",
    },
)
```

D6 后续可扩展：

```text
recon_cue_used_count = count(recon_cue_used events)
terminal_accuracy_with_cue / terminal_accuracy_without_cue
time_to_terminal_lock_with_cue / time_to_terminal_lock_without_cue
```

这些扩展只能用于离线评估，不能被解释为 cue 自动授权或自动目标处置。

## 12. 仿真验证

当前示例仿真是轻量合成日志生成器，不是物理拦截仿真。它覆盖：

- 多目标真值轨迹和带噪声航迹记录。
- 漏检和虚警。
- 随机 ID Switch。
- 分配重复和高威胁未分配。
- 中心失效、降级稳定、共识轮数和降级任务结果。
- 末端 FOV、锁定、歧义、友方 hold 和本地 ID Switch。
- 安全约束违反和人工覆盖事件。

推荐验证命令：

```bash
python3 -m pytest research_modules/d6_evaluation_metrics/tests
python3 research_modules/d6_evaluation_metrics/scripts/run_batch_example.py --seeds 100
```

## 13. 局限与后续工作

当前局限：

- OSPA、MOTA/MOTP 只在文档中给出公式和扩展方向，未作为默认输出字段。
- 终端 cue 使用情况尚未进入 `EpisodeMetrics` 的默认字段。
- 降级统计尚未按 `coordination_mode/leader_role/coverage_cell` 自动分组。
- 主动降级统计尚未进入 `EpisodeMetrics` 的默认字段；当前文档先定义日志合同、公式和批量评估方法。
- 合成日志不是 AirSim 物理回放，不能代表真实传感器或真实通信系统。
- 置信区间使用正态近似，强偏态指标应进一步采用 bootstrap。

后续工作：

1. 增加 OSPA/CLEAR MOT 适配器，用于与 Stone Soup、TrackEval 或 py-motmetrics 对照。
2. 在 `EventRecord.metadata` 解析 D4 的二级节点字段，输出分组降级统计。
3. 增加 D5 `recon_cue_used_count` 与 cue/非 cue 末端指标对比。
4. 增加 AirSim 回放适配器，将仿真导出的 CSV/JSONL 转换为 D6 数据类。
5. 在报告中加入场景因素分组表，例如“目标密度 vs ID Switch vs 终端歧义”。
6. 增加主动降级窗口评估器，输出 `passive_failover_count`, `active_degradation_count`, `active_degradation_precision`, `unnecessary_active_degradation_count`, `terminal_center_disagreement_count`, `time_to_active_degradation_decision`, `post_degradation_id_switch_delta`, `post_degradation_assignment_conflict_delta`。
