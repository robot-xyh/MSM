# D6 系统级评估指标体系：算法原理与实施方案

## 1. 模块定位

D6 是系统级离线评估模块，负责消费 D1-D5 产生的记录、仿真日志和评估真值，输出可复现的指标、表格、报告和曲线。D6 不参与实时任务决策，不发布控制指令，不提供火控参数，不建模毁伤效果，不自动处置目标，也不绕过人工授权。

本模块解决的问题不是“某次是否成功”，而是“系统在哪个环节稳定、在哪个环节失效”。因此不能只报告命中率。单一命中率会掩盖探测虚警、航迹断裂、ID Switch、重复分配、降级接管失败、末端误配准和安全约束触发等问题。D6 将这些问题拆成六类指标：探测、跟踪、分配、降级、末端配准和安全约束。

## 2. 输入输出

### 2.1 输入记录

| 输入类型 | 数据类 | 来源模块 | 主要字段 |
|---|---|---|---|
| 航迹记录 | `TrackRecord` | D1/D2 | `timestamp`, `global_track_id`, `truth_id`, `position`, `truth_position`, `covariance_trace`, `track_state` |
| 分配记录 | `AssignmentRecord` | D3/D4 | `timestamp`, `plan_id`, `version`, `resource_id`, `global_track_id`, `authorization_state`, `active`, `truth_id` |
| 系统事件 | `EventRecord` | D1-D5/仿真器 | `timestamp`, `event_type`, `actor_id`, `value`, `metadata` |
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
| `plots/*.png` | `outputs/*/plots/` | 六类指标柱状图和关键指标分布曲线 |

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

### 3.6 安全约束指标

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
适配器转换为 TrackRecord / AssignmentRecord / EventRecord / TerminalRecord
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
2. 将 D1-D5 日志转换为 D6 数据类。
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
- 合成日志不是 AirSim 物理回放，不能代表真实传感器或真实通信系统。
- 置信区间使用正态近似，强偏态指标应进一步采用 bootstrap。

后续工作：

1. 增加 OSPA/CLEAR MOT 适配器，用于与 Stone Soup、TrackEval 或 py-motmetrics 对照。
2. 在 `EventRecord.metadata` 解析 D4 的二级节点字段，输出分组降级统计。
3. 增加 D5 `recon_cue_used_count` 与 cue/非 cue 末端指标对比。
4. 增加 AirSim 回放适配器，将仿真导出的 CSV/JSONL 转换为 D6 数据类。
5. 在报告中加入场景因素分组表，例如“目标密度 vs ID Switch vs 终端歧义”。

