# D6 系统评估指标综述及子方案

**定位**: 建立覆盖探测、跟踪、分配、降级、末端配准和安全约束的评估体系，支持批量实验统计。  
**边界**: 本文只用于离线评估、合规测试和科研报告，不参与实时任务决策，不包含火控参数、毁伤逻辑或自动处置流程。

---

## 1. 研究问题

多目标系统不能只报告“命中率”或单一成功率。一个方案可能拦截结果看似成功，但存在虚警高、ID Switch 多、重复分配、中心失效后不可恢复、末端误配准或人工覆盖频繁等问题。

D6 的目标是把所有模块日志统一转为可比较指标，并支持批量实验统计。

---

## 2. 文献综述要点

2015-2026 年评估体系主要来自三类来源。

第一，多目标跟踪评估。MOTChallenge、CLEAR MOT、MOTA/MOTP、IDF1、HOTA、OSPA/GOSPA 等指标分别衡量检测、定位、关联和身份保持能力。其中 ID Switch 对当前项目尤其关键。

第二，C-UAS 测试框架。COURAGEOUS/CWA、JRC 和相关测试规范通常把能力拆成 Detect、Track、Identify，并记录误警、漏检、连续跟踪、识别置信度和场景复现条件。

第三，多智能体系统评估。任务分配和降级协同需要记录收敛轮次、通信开销、故障恢复时间、降级完成率和冲突事件。

因此，D6 应作为独立旁路模块，消费日志，不参与决策。

---

## 3. 指标体系

| 类别 | 指标 | 含义 |
|------|------|------|
| 探测 | `detection_probability` | 真目标被检测到的比例 |
| 探测 | `false_alarm_rate` | 单位时间或单位区域虚警数 |
| 探测 | `missed_detection_rate` | 漏检比例 |
| 跟踪 | `track_rmse` | 航迹与真值的均方根误差 |
| 跟踪 | `track_continuity` | 航迹连续覆盖比例 |
| 跟踪 | `id_switch_count` | 真值目标对应航迹ID变化次数 |
| 分配 | `duplicate_assignment_count` | 多资源重复分配到同一目标次数 |
| 分配 | `unassigned_high_threat_count` | 高优先级目标未分配次数 |
| 降级 | `failover_time` | 中心失效到降级计划稳定耗时 |
| 降级 | `consensus_rounds` | 分布式协商轮次 |
| 降级 | `degraded_completion_rate` | 降级状态下任务连续性比例 |
| 末端配准 | `terminal_association_accuracy` | 末端局部目标绑定正确率 |
| 末端配准 | `terminal_id_switch_count` | 末端局部视觉ID切换次数 |
| 末端配准 | `ambiguous_fov_event_count` | 视场内多候选歧义事件数 |
| 末端配准 | `friend_overlap_hold_count` | 友方重叠导致hold次数 |
| 末端配准 | `time_to_terminal_lock` | 从进入视场到锁定配准耗时 |
| 安全 | `constraint_violation_count` | 违反系统约束次数 |
| 安全 | `human_override_count` | 人工覆盖或拒绝次数 |

---

## 4. 开源工具复用

| 工具 | 可复用内容 | 用途 |
|------|------------|------|
| Stone Soup metrics | SIAP、CLEAR MOT、OSPA/GOSPA | 跟踪指标 |
| TrackEval | HOTA、IDF1、MOTA | MOT和ID保持 |
| py-motmetrics | CLEAR MOT实现 | 轻量离线指标 |
| AirSim recording | 图像、姿态、传感器日志 | 仿真回放 |
| SCRIMMAGE metrics | 多智能体统计接口 | 批量对抗/协同实验 |

---

## 5. 日志模型

```text
TrackRecord
- timestamp
- global_track_id
- truth_id
- state
- covariance_trace
- track_state
- association_source

AssignmentRecord
- timestamp
- plan_id
- version
- resource_id
- global_track_id
- cost_breakdown
- authorization_state

TerminalRecord
- timestamp
- resource_id
- assigned_global_track_id
- local_track_id
- decision_state
- ambiguity_score
- friend_conflict_state

EventRecord
- timestamp
- event_type
- actor_id
- severity
- note

EpisodeMetrics
- detection
- tracking
- assignment
- degradation
- terminal
- safety
- guidance
```

---

## 6. 新增闭环指标与日志

main 已设置 D4 主动降级、D5 多视角目标关联和 D7 比例导引后，D6 需要把闭环事件从“单模块成功率”扩展为可回放、可聚合、可画图的系统级日志。新增指标仍只用于离线评估和报告，不参与实时控制或自动处置。

### 6.1 D4 主动/被动降级与二级节点接管

| 指标 | 来源日志 | 含义 |
|------|----------|------|
| `active_degradation_count` | `EventRecord(event_type="active_degradation")` 或 D4 decision log | 主动降级触发次数，按 episode、资源、目标分别统计 |
| `secondary_node_takeover_count` | D4 failover/coordinator event | 二级节点接管次数，区分中心失效、链路退化、主动仲裁接管 |
| `failover_time` | 中心失效事件与稳定接管事件 timestamp 差值 | 从主节点失效/不可用到降级计划稳定的耗时 |
| `degraded_completion_rate` | D4 decision + assignment/guidance 后续状态 | 降级状态下仍完成可评估闭环的比例 |
| `consensus_rounds` | D4 CBBA/协商日志 | 被动或分布式协商达到一致的轮次 |

建议日志字段：

```text
DegradationRecord / EventRecord.metadata
- timestamp
- mode: passive_failover | active_degradation | secondary_takeover
- resource_id
- global_track_id
- source_node_id
- target_node_id
- action
- reason
- risk_factors
- plan_id
- plan_version
- stable_after_s
```

`EpisodeMetrics.degradation` 应新增 `active_degradation_count`、`secondary_node_takeover_count`、`failover_time` 的均值/最大值/分位数，并在报告中绘制降级事件时间线、接管耗时箱线图和不同故障场景下的降级完成率柱状图。

### 6.2 D5 多视角末端关联

| 指标 | 来源日志 | 含义 |
|------|----------|------|
| `terminal_association_accuracy` | D5 terminal association + 验证标签 | 末端局部观测绑定到 `assigned_global_track_id` 的正确率 |
| `multi_view_consensus_rate` | 跨相机/跨资源 consensus log | 多视角观测对同一 `global_track_id` 达成一致的比例 |
| `cross_view_conflict_count` | D5 conflict/ambiguity event | 不同视角对同一局部目标或全局目标给出冲突绑定的次数 |
| `duplicate_terminal_lock_count` | terminal lock records | 多个资源或多个本地轨迹重复锁定同一终端目标的次数 |
| `time_to_terminal_lock` | 首次进入可见/检测事件到 `locked` 事件的 timestamp 差值 | 末端视场出现后完成稳定配准的耗时 |
| `terminal_detection_timeout_count` | assigned target 可见窗口内无有效检测/无锁定 | 末端检测或锁定超时次数 |
| `terminal_id_switch_count` | local/global association sequence | 末端局部视觉 ID 或绑定目标切换次数 |

AirSim 运行时默认不再保留 PNG 截图不影响 D6 评估。D6 不需要原始图像，只要日志保存以下可验证字段即可：

```text
TerminalObservationRecord
- timestamp
- resource_id
- camera_id
- local_track_id
- bbox_xyxy
- detection_score
- camera_intrinsics
- camera_extrinsics
- assigned_global_track_id
- object_name
- truth_label / validation_label
- frame_id
```

其中 `bbox_xyxy`、相机内参/外参和 `timestamp` 足以复算投影门限、视场一致性和跨视角几何约束；`assigned_global_track_id`、`object_name` 与验证标签足以计算绑定正确率、冲突数和重复锁定数。报告图表建议包括末端锁定状态时间线、多视角一致率曲线、冲突/重复锁定计数条形图和 `time_to_terminal_lock` 分布。

### 6.3 D7 中段/末端比例导引

| 指标 | 来源日志 | 含义 |
|------|----------|------|
| `intercept_success_count` | D7 `GuidanceRecord` summary | 满足闭环成功条件的次数 |
| `collision_intercept_count` | range 低于碰撞/接触阈值事件 | 以碰撞式阈值判定的拦截次数，仅用于离线统计 |
| `range_intercept_count` | range 低于距离阈值事件 | 以最小距离阈值判定的拦截次数 |
| `time_to_intercept_s` | guidance 起始到首次满足拦截阈值的时间 | 完成中段/末端闭环所需时间 |
| `min_range_m` | 每条 guidance episode 的最小 range | 最近接距离 |
| `terminal_detection_timeout_count` | D5/D7 共享终端窗口日志 | 已分配目标在末端窗口未检测或未进入 `vision_terminal` 的次数 |
| `guidance_mode_switch_count` | `GuidanceRecord.mode_switch` | 从 `radar_midcourse` 切换到 `vision_terminal` 的次数 |
| `terminal_mode_entry_rate` | D7 summary | 已分配 episode 中进入末端导引模式的比例 |

D7 日志至少应保留：

```text
GuidanceRecord
- timestamp_s
- resource_id
- target_id / assigned_global_track_id
- mode: radar_midcourse | vision_terminal
- range_m
- los_angle_rad
- los_rate_radps
- closing_speed_mps
- commanded_lateral_accel_mps2
- limited_lateral_accel_mps2
- limited_turn_rate_radps
- mode_switch
- observation.source
- observation.dry_run
```

`EpisodeMetrics.guidance` 应从 `guidance_records` 和 `guidance_summaries` 聚合 `intercept_success_count`、`collision_intercept_count`、`range_intercept_count`、`time_to_intercept_s`、`min_range_m` 和模式切换统计。报告图表建议包括 range-vs-time 曲线、导引模式时间线、最小距离分布和不同 D4/D5 状态下的拦截成功率对比。

### 6.4 EpisodeMetrics 与报告接入

`EpisodeMetrics` 建议扩展为：

```text
EpisodeMetrics
- detection
- tracking
- assignment
- degradation
  - active_degradation_count
  - secondary_node_takeover_count
  - failover_time
- terminal
  - terminal_association_accuracy
  - multi_view_consensus_rate
  - cross_view_conflict_count
  - duplicate_terminal_lock_count
  - time_to_terminal_lock
  - terminal_detection_timeout_count
- guidance
  - intercept_success_count
  - collision_intercept_count
  - range_intercept_count
  - time_to_intercept_s
  - min_range_m
- safety
```

报告生成流程中，D6 应把新增字段同时写入 `metrics.json`、`episode_metrics.csv` 和 Markdown 报告。图表层按四类面板组织：

1. D4 降级：主动/被动降级次数、二级节点接管次数、`failover_time` 分布。
2. D5 末端关联：`terminal_association_accuracy`、`multi_view_consensus_rate`、冲突/重复锁定计数。
3. D7 导引：`min_range_m`、`time_to_intercept_s`、中段/末端模式时间线。
4. 闭环综合：按场景、故障模式、是否多视角一致分组，对比 `intercept_success_count` 和 `terminal_detection_timeout_count`。

---

## 7. 批量统计伪代码

```python
class BatchExperimentAnalyzer:
    def compute_episode(self, log):
        metrics = EpisodeMetrics(log.episode_id)
        metrics.detection = calc_detection_metrics(log.truth, log.detections)
        metrics.tracking = calc_tracking_metrics(log.truth, log.tracks)
        metrics.assignment = calc_assignment_metrics(log.assignments)
        metrics.degradation = calc_degradation_metrics(log.events)
        metrics.terminal = calc_terminal_metrics(log.terminal_associations)
        metrics.guidance = calc_guidance_metrics(log.guidance_records)
        metrics.safety = calc_safety_metrics(log.events)
        return metrics

    def aggregate(self, episodes):
        return {
            "mean": mean([e.to_dict() for e in episodes]),
            "std": std([e.to_dict() for e in episodes]),
            "ci95": ci95([e.to_dict() for e in episodes]),
        }
```

---

## 8. 示例实验报告模板

```text
实验名称：
场景/日期/版本/随机种子：
数据来源：仿真 / 回放 / 脱敏日志
算法组合：D1融合 / D2关联 / D3分配 / D4降级 / D5配准 / D7导引

探测：
- POD:
- FAR:
- MAR:

跟踪：
- RMSE:
- continuity:
- IDSW:

分配：
- duplicate_assignment_count:
- unassigned_high_threat_count:
- reassignment_count:

降级：
- active_degradation_count:
- secondary_node_takeover_count:
- failover_time:
- consensus_rounds:
- degraded_completion_rate:

末端配准：
- terminal_association_accuracy:
- multi_view_consensus_rate:
- cross_view_conflict_count:
- duplicate_terminal_lock_count:
- terminal_id_switch_count:
- time_to_terminal_lock:
- terminal_detection_timeout_count:
- friend_overlap_hold_count:

比例导引：
- intercept_success_count:
- collision_intercept_count:
- range_intercept_count:
- time_to_intercept_s:
- min_range_m:

安全约束：
- constraint_violation_count:
- human_override_count:

批量统计：
- N:
- mean/std/95%CI:
- 异常样本：

结论：
- 能力边界：
- 主要失效模式：
- 需人工复核事项：
```

---

## 9. 测试与验收

| 测试 | 验收 |
|------|------|
| 单场景日志解析 | 所有Record可被加载 |
| 缺字段日志 | 给出明确错误，不静默跳过 |
| 跟踪指标 | 与Stone Soup/py-motmetrics结果可对照 |
| 分配指标 | 能统计重复分配和未分配高优先级目标 |
| 降级指标 | 能计算failover_time和consensus_rounds |
| 末端指标 | 能统计歧义、锁定时间和友方hold |
| 多视角指标 | 无PNG截图时可用bbox、相机参数、timestamp和验证标签计算一致率/冲突数 |
| 导引指标 | 能从GuidanceRecord计算min_range、time_to_intercept和模式切换 |
| 批量实验 | 输出CSV/Markdown对比表 |

---

## 10. 交付物

1. 指标体系综述。
2. `EpisodeMetrics`、`TrackRecord`、`AssignmentRecord`、`TerminalRecord`、`EventRecord` 数据模型。
3. 批量实验统计模块设计。
4. 示例实验报告模板。
5. 与 Stone Soup、TrackEval、AirSim、SCRIMMAGE 的复用接口说明。
6. D4/D5/D7 闭环指标、日志字段和报告图表接入说明。

---

## 11. 参考资料

- Stone Soup metrics: <https://stonesoup.readthedocs.io/en/latest/stonesoup.metricgenerator.tracktotruthmetrics.html>
- Stone Soup OSPA metrics: <https://stonesoup.readthedocs.io/en/latest/stonesoup.metricgenerator.ospametric.html>
- TrackEval: <https://github.com/JonathonLuiten/TrackEval>
- py-motmetrics: <https://github.com/cheind/py-motmetrics>
- AirSim APIs: <https://microsoft.github.io/AirSim/apis/>
- AirSim recording: <https://microsoft.github.io/AirSim/modify_recording_data/>
- SCRIMMAGE: <https://github.com/gtri/scrimmage>
