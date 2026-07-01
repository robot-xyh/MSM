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
```

---

## 6. 批量统计伪代码

```python
class BatchExperimentAnalyzer:
    def compute_episode(self, log):
        metrics = EpisodeMetrics(log.episode_id)
        metrics.detection = calc_detection_metrics(log.truth, log.detections)
        metrics.tracking = calc_tracking_metrics(log.truth, log.tracks)
        metrics.assignment = calc_assignment_metrics(log.assignments)
        metrics.degradation = calc_degradation_metrics(log.events)
        metrics.terminal = calc_terminal_metrics(log.terminal_associations)
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

## 7. 示例实验报告模板

```text
实验名称：
场景/日期/版本/随机种子：
数据来源：仿真 / 回放 / 脱敏日志
算法组合：D1融合 / D2关联 / D3分配 / D4降级 / D5配准

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
- failover_time:
- consensus_rounds:
- degraded_completion_rate:

末端配准：
- terminal_association_accuracy:
- terminal_id_switch_count:
- time_to_terminal_lock:
- friend_overlap_hold_count:

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

## 8. 测试与验收

| 测试 | 验收 |
|------|------|
| 单场景日志解析 | 所有Record可被加载 |
| 缺字段日志 | 给出明确错误，不静默跳过 |
| 跟踪指标 | 与Stone Soup/py-motmetrics结果可对照 |
| 分配指标 | 能统计重复分配和未分配高优先级目标 |
| 降级指标 | 能计算failover_time和consensus_rounds |
| 末端指标 | 能统计歧义、锁定时间和友方hold |
| 批量实验 | 输出CSV/Markdown对比表 |

---

## 9. 交付物

1. 指标体系综述。
2. `EpisodeMetrics`、`TrackRecord`、`AssignmentRecord`、`TerminalRecord`、`EventRecord` 数据模型。
3. 批量实验统计模块设计。
4. 示例实验报告模板。
5. 与 Stone Soup、TrackEval、AirSim、SCRIMMAGE 的复用接口说明。

---

## 10. 参考资料

- Stone Soup metrics: <https://stonesoup.readthedocs.io/en/latest/stonesoup.metricgenerator.tracktotruthmetrics.html>
- Stone Soup OSPA metrics: <https://stonesoup.readthedocs.io/en/latest/stonesoup.metricgenerator.ospametric.html>
- TrackEval: <https://github.com/JonathonLuiten/TrackEval>
- py-motmetrics: <https://github.com/cheind/py-motmetrics>
- AirSim APIs: <https://microsoft.github.io/AirSim/apis/>
- AirSim recording: <https://microsoft.github.io/AirSim/modify_recording_data/>
- SCRIMMAGE: <https://github.com/gtri/scrimmage>
