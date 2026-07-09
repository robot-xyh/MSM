# D6 评估体系架构评估与改进方案

**文档版本**: v1.0
**评估日期**: 2026-07-08
**评估重点**: 工程化、成熟可靠、可在仿真/封闭场地验证

---

## 1. 当前架构分析

### 1.1 核心设计

当前D6模块实现了多维度离线评估系统：

**指标分类**:
- **探测类**: detection_probability, false_alarm_rate, missed_detection_rate
- **跟踪类**: track_rmse, track_continuity, id_switch_count
- **分配类**: duplicate_assignment_count, unassigned_high_threat_count
- **降级类**: failover_time, consensus_rounds, degraded_completion_rate
- **末端类**: terminal_association_accuracy, terminal_id_switch_count, ambiguous_fov_event_count
- **安全类**: constraint_violation_count, human_override_count

**输出格式**:
- JSONL日志流
- CSV指标表
- Markdown报告
- PNG图表

**批量评估**:
- 多episode聚合
- 场景分组统计
- 对比分析

### 1.2 核心假设

1. **工程指标充分假设**: 可解释指标优于学术标准指标
2. **离线评估充分假设**: 不需要在线实时监测
3. **模块独立评估假设**: 各模块指标独立统计
4. **成功率单一假设**: 任务成功/失败二值评估
5. **静态场景假设**: 场景参数固定

### 1.3 设计边界

- **评估时机**: 离线post-processing，无在线监测
- **指标粒度**: Episode级、Batch级，无实时趋势
- **因果分析**: 缺乏失败根因自动诊断
- **对比基准**: 缺乏与标准算法的自动对比
- **统计推断**: 简单均值/标准差，无置信区间、显著性检验

---

## 2. 工程化不足识别

### 2.1 鲁棒性问题

#### 问题1: 系统级成功指标缺失
**表现**: 各模块指标优秀，但任务整体失败
**根因**:
- 缺乏端到端成功率定义
- 模块指标与任务目标脱节
- 无系统级涌现行为评估

**工程影响**: 无法回答"系统是否真正有效"

**案例**: D1 RMSE低、D2 IDSW少，但拦截失败

#### 问题2: 失败根因难定位
**表现**: 知道失败了，不知道为什么
**根因**:
- 日志分散在各模块
- 缺乏因果链追踪
- 无自动诊断工具

**工程影响**: 调试周期长

#### 问题3: 对比评估不充分
**表现**: 无法判断改进是否真正有效
**根因**:
- 缺乏baseline对比
- 无统计显著性检验
- 参数敏感性分析不足

**工程影响**: 改进决策主观

#### 问题4: 实时性能未监测
**表现**: 离线指标好，实时运行卡顿
**根因**:
- 无计算时间、内存、CPU统计
- 无瓶颈分析
- 无性能回归检测

**工程影响**: 部署后性能问题

### 2.2 边界条件处理

#### 边界1: 极端场景覆盖不足
**问题**: 只测试nominal场景
**缺失**: 压力测试、边界值测试

#### 边界2: 长时间运行评估
**问题**: Episode时长短（<1分钟）
**缺失**: 长时稳定性、资源泄漏、累积误差

#### 边界3: 多种子统计
**问题**: 单次运行，随机性未量化
**缺失**: 多随机种子统计、置信区间

### 2.3 真实环境适应性

#### 适应性1: 对抗性评估缺失
**现状**: 目标行为固定
**真实**: 智能对抗、欺骗、干扰
**影响**: 真实效能未知

#### 适应性2: 人机协同未评估
**现状**: 自动化系统评估
**真实**: 需要人工干预、授权、监督
**影响**: 人因工程学指标缺失

#### 适应性3: 系统退化未监测
**现状**: 单次episode评估
**真实**: 连续运行后性能退化
**影响**: 长期可靠性未知

---

## 3. 成熟方案对比

### 3.1 工业系统参考

#### 航空航天测试标准
**DO-178C软件安全**:
- 需求覆盖率
- 结构覆盖率
- MC/DC (修正条件/判定覆盖)
- 失效模式分析

**可借鉴**:
- 需求到测试的追溯
- 覆盖率度量
- 失效树分析

**参考**: DO-178C标准文档

#### FMEA (失效模式与影响分析)
**汽车/航空工业**:
- 识别失效模式
- 评估严重性、发生率、检测度
- 计算风险优先级数(RPN)

**可借鉴**:
- 系统化失效分析
- 风险量化
- 改进优先级

**参考**: SAE J1739 FMEA标准

#### 自动驾驶测试框架
**Waymo/Tesla评估**:
- 虚拟仿真 + 封闭场地 + 公开道路
- 场景库（corner cases）
- 安全指标（碰撞率、接管率）
- 持续集成测试

**可借鉴**:
- 分层测试策略
- 场景库管理
- 持续集成

**参考**: Waymo Safety Report

### 3.2 开源工程实现

#### MOT评估工具
**TrackEval**:
- HOTA, MOTA, MOTP, IDF1
- 多数据集统一接口
- 可视化工具

**代码**: <https://github.com/JonathonLuiten/TrackEval>

**可借鉴**:
- 标准MOT指标
- 评估脚本模板

#### py-motmetrics
**特点**:
- CLEAR MOT指标
- 事件统计（FP/FN/IDSW）
- 与ground truth对比

**代码**: <https://github.com/cheind/py-motmetrics>

#### MLflow
**特点**:
- 实验跟踪
- 参数记录
- 模型版本管理
- 可视化对比

**代码**: <https://github.com/mlflow/mlflow>

**可借鉴**:
- 实验管理平台
- 参数-指标追踪
- Web UI

### 3.3 评估标准

#### OSPA (Optimal Subpattern Assignment)
- 多目标跟踪统一度量
- 同时考虑定位、势、标签误差

#### HOTA (Higher Order Tracking Accuracy)
- 平衡检测、关联、定位
- 更全面的MOT指标

#### TTC/TTA (Time To Collision/Approach)
- 安全性评估
- 时间裕度量化

---

## 4. 改进方案

### 4.1 短期改进 (1-3个月)

#### 改进1: 系统级任务成功指标
**目标**: 定义端到端成功率

**方案**:
```python
class MissionSuccessEvaluator:
    def evaluate_mission(self, episode_log):
        # 任务成功定义（多条件）
        criteria = {
            'high_threat_neutralized': self.check_high_threat(episode_log),
            'no_friendly_fire': self.check_friendly_safety(episode_log),
            'resource_efficiency': self.check_resource_usage(episode_log),
            'time_constraint': self.check_time_limit(episode_log),
            'authorization_compliant': self.check_authorization(episode_log)
        }

        # 全部满足才算成功
        mission_success = all(criteria.values())

        # 详细结果
        return MissionResult(
            success=mission_success,
            criteria_details=criteria,
            failure_reasons=[k for k, v in criteria.items() if not v],
            metrics=self.compute_detailed_metrics(episode_log)
        )

    def check_high_threat(self, log):
        # 高威胁目标是否全部处理
        high_threat_targets = [t for t in log.targets if t.threat > 0.8]
        neutralized = [t for t in high_threat_targets if t.final_state == 'neutralized']
        return len(neutralized) / len(high_threat_targets) >= 0.9
```

**输出**: 任务成功率、失败原因分布

**验证**: 与人工评估一致性>90%

#### 改进2: 自动根因诊断
**目标**: 失败时自动定位问题模块

**方案**:
```python
class RootCauseAnalyzer:
    def diagnose(self, failed_episode):
        # 1. 收集各模块状态
        d1_health = self.check_d1_metrics(failed_episode)
        d2_health = self.check_d2_metrics(failed_episode)
        d3_health = self.check_d3_metrics(failed_episode)
        d4_health = self.check_d4_metrics(failed_episode)
        d5_health = self.check_d5_metrics(failed_episode)
        d7_health = self.check_d7_metrics(failed_episode)

        # 2. 构建因果链
        causal_chain = []

        if d1_health['rmse'] > threshold:
            causal_chain.append(("D1", "high_tracking_error", "fusion_degraded"))

        if d2_health['id_switch'] > threshold:
            if d1_health['rmse'] > threshold:
                causal_chain.append(("D2", "id_switch", "caused_by_D1_error"))
            else:
                causal_chain.append(("D2", "id_switch", "association_failure"))

        if d5_health['locked_rate'] < threshold:
            causal_chain.append(("D5", "low_lock_rate", "terminal_association_failed"))
            # 进一步分析D5失败原因
            if d3_health['assignment_mismatch']:
                causal_chain.append(("D5_failure", "caused_by_D3_wrong_assignment"))

        # 3. 识别根因（因果链最上游）
        root_cause = self.identify_root(causal_chain)

        return RootCauseReport(
            root_cause=root_cause,
            causal_chain=causal_chain,
            recommendations=self.generate_recommendations(root_cause)
        )
```

**输出**: 根因、因果链、改进建议

**验证**: 与专家诊断对比，准确率>70%

#### 改进3: 基线对比框架
**目标**: 自动对比多种配置

**方案**:
```python
class BaselineComparison:
    def compare(self, configs, scenarios):
        # configs: [baseline, improved_v1, improved_v2, ...]
        results = {}

        for config in configs:
            config_results = []
            for scenario in scenarios:
                # 运行episode
                episode_result = self.run_episode(config, scenario)
                config_results.append(episode_result)

            # 聚合指标
            results[config.name] = self.aggregate(config_results)

        # 统计显著性检验
        comparison_table = self.statistical_test(results)

        # 生成报告
        return ComparisonReport(
            metrics_table=comparison_table,
            significance_tests=self.significance_results,
            recommendations=self.select_best(results)
        )

    def statistical_test(self, results):
        # t检验比较配置间差异
        baseline = results['baseline']

        for config_name, config_results in results.items():
            if config_name == 'baseline':
                continue

            # t检验
            t_stat, p_value = ttest_ind(baseline.success_rates,
                                       config_results.success_rates)

            # 效应量(Cohen's d)
            effect_size = self.compute_cohens_d(baseline, config_results)

            self.significance_results[config_name] = {
                'p_value': p_value,
                'significant': p_value < 0.05,
                'effect_size': effect_size
            }
```

**输出**: 对比表、显著性检验、效应量

**验证**: 符合统计学标准

#### 改进4: 性能监测
**目标**: 追踪计算性能

**方案**:
```python
class PerformanceProfiler:
    def profile_episode(self, episode_log):
        # 1. 各模块计算时间
        timing = {
            'D1_fusion': self.extract_timing(episode_log, 'D1'),
            'D2_association': self.extract_timing(episode_log, 'D2'),
            'D3_assignment': self.extract_timing(episode_log, 'D3'),
            'D4_degradation': self.extract_timing(episode_log, 'D4'),
            'D5_terminal': self.extract_timing(episode_log, 'D5'),
            'D7_guidance': self.extract_timing(episode_log, 'D7')
        }

        # 2. 瓶颈识别
        bottleneck = max(timing, key=timing.get)

        # 3. 内存使用
        memory_peak = episode_log.max_memory_usage

        # 4. 实时性评估
        realtime_factor = episode_log.wall_time / episode_log.sim_time

        return PerformanceReport(
            timing=timing,
            bottleneck=bottleneck,
            memory_peak=memory_peak,
            realtime_factor=realtime_factor,
            meets_realtime=realtime_factor < 1.0
        )
```

**输出**: 计时、瓶颈、内存、实时性

**验证**: 识别D3为瓶颈（如果确实是）


---

### 4.2 中期改进 (3-6个月)

#### 改进5: 场景库管理
**目标**: 系统化测试覆盖

**方案**:
```python
class ScenarioLibrary:
    def __init__(self):
        self.scenarios = {
            'nominal': self.load_nominal_scenarios(),
            'stress': self.load_stress_scenarios(),
            'corner_cases': self.load_corner_cases(),
            'failure': self.load_failure_scenarios()
        }

    def load_corner_cases(self):
        # 边界场景
        return [
            Scenario('dense_crossing', targets=5, min_distance=10),
            Scenario('high_speed', target_speed=50),
            Scenario('long_occlusion', occlusion_duration=10),
            Scenario('sensor_failure', failed_sensors=['radar_1']),
            Scenario('network_partition', partition_size=[3, 2]),
            Scenario('friend_overlap', friend_distance=5),
        ]

    def generate_test_suite(self, coverage='full'):
        # 测试套件生成
        if coverage == 'smoke':
            return self.select_subset(n=10)
        elif coverage == 'regression':
            return self.select_critical_scenarios()
        elif coverage == 'full':
            return self.all_scenarios()

    def track_coverage(self, executed_scenarios):
        # 覆盖率分析
        coverage = {
            'nominal': self.compute_coverage(executed_scenarios, 'nominal'),
            'stress': self.compute_coverage(executed_scenarios, 'stress'),
            'corner': self.compute_coverage(executed_scenarios, 'corner_cases'),
            'failure': self.compute_coverage(executed_scenarios, 'failure')
        }
        return coverage
```

**输出**: 场景库、测试套件、覆盖率报告

**验证**: 覆盖率100%的场景库

#### 改进6: 对抗性评估
**目标**: 测试对抗鲁棒性

**方案**:
```python
class AdversarialEvaluator:
    def generate_adversarial_scenarios(self, baseline_scenario):
        adversarial_scenarios = []

        # 1. 目标对抗行为
        scenarios.append(self.add_evasive_maneuver(baseline_scenario))
        scenarios.append(self.add_spoofing_attack(baseline_scenario))
        scenarios.append(self.add_jamming(baseline_scenario))

        # 2. 传感器欺骗
        scenarios.append(self.add_false_targets(baseline_scenario))
        scenarios.append(self.add_measurement_bias(baseline_scenario))

        # 3. 通信攻击
        scenarios.append(self.add_message_delay(baseline_scenario))
        scenarios.append(self.add_message_drop(baseline_scenario))

        return adversarial_scenarios

    def evaluate_robustness(self, system, adversarial_scenarios):
        # 评估对抗鲁棒性
        results = []
        for scenario in adversarial_scenarios:
            result = self.run_episode(system, scenario)
            results.append({
                'scenario': scenario.name,
                'attack_type': scenario.attack_type,
                'success_rate': result.success_rate,
                'degradation': baseline_success - result.success_rate
            })

        return AdversarialRobustnessReport(results)
```

**输出**: 对抗场景、鲁棒性指标、脆弱性分析

**验证**: 识别系统薄弱环节

#### 改进7: 持续集成/回归测试
**目标**: 自动化测试流水线

**方案**:
```python
class CITestPipeline:
    def run_ci_tests(self, code_commit):
        # 1. 快速smoke测试
        smoke_results = self.run_smoke_tests()
        if not smoke_results.all_passed:
            return CIResult(status='FAILED', stage='smoke')

        # 2. 回归测试
        regression_results = self.run_regression_tests()
        if regression_results.performance_degraded:
            return CIResult(status='WARNING', stage='regression',
                           details=regression_results.degraded_metrics)

        # 3. 全量测试（可选，夜间运行）
        if self.is_nightly_build():
            full_results = self.run_full_test_suite()

        return CIResult(status='PASSED')

    def detect_performance_regression(self, new_results, baseline):
        # 性能回归检测
        regressions = []
        for metric in metrics:
            if new_results[metric] < baseline[metric] * 0.95:  # 下降5%
                regressions.append({
                    'metric': metric,
                    'baseline': baseline[metric],
                    'current': new_results[metric],
                    'degradation_pct': (baseline[metric]-new_results[metric])/baseline[metric]
                })

        return regressions
```

**集成**: GitHub Actions / GitLab CI

**输出**: CI状态、回归报告

#### 改进8: 标准MOT指标对齐
**目标**: 与学术界对比

**方案**: 集成py-motmetrics

**实施**:
```python
import motmetrics as mm

class StandardMOTEvaluator:
    def compute_mot_metrics(self, ground_truth, predictions):
        # 1. 构建motmetrics累加器
        acc = mm.MOTAccumulator(auto_id=True)

        # 2. 逐帧更新
        for frame in range(num_frames):
            gt_ids = ground_truth.get_ids(frame)
            gt_boxes = ground_truth.get_boxes(frame)
            pred_ids = predictions.get_ids(frame)
            pred_boxes = predictions.get_boxes(frame)

            # 计算距离矩阵
            distances = mm.distances.iou_matrix(gt_boxes, pred_boxes, max_iou=0.5)

            # 更新
            acc.update(gt_ids, pred_ids, distances)

        # 3. 计算指标
        mh = mm.metrics.create()
        summary = mh.compute(acc, metrics=['mota', 'motp', 'num_switches',
                                          'idf1', 'precision', 'recall'])

        return MOTMetrics(
            mota=summary['mota'],
            motp=summary['motp'],
            id_switches=summary['num_switches'],
            idf1=summary['idf1'],
            precision=summary['precision'],
            recall=summary['recall']
        )
```

**输出**: MOTA, MOTP, IDF1等标准指标

**验证**: 与公开数据集对比

---

### 4.3 长期改进 (6-12个月)

#### 改进9: 在线监测Dashboard
**目标**: 实时系统健康监测

**方案**: Web Dashboard (Flask/Dash)

**功能**:
- 实时指标显示
- 历史趋势图
- 告警与通知
- 系统拓扑图

**参考**: Grafana、Prometheus

#### 改进10: 机器学习辅助评估
**目标**: 自动学习失败模式

**方案**:
- 聚类失败案例
- 预测潜在失败
- 推荐测试场景

**限制**: 需要大量历史数据

---

## 5. AirSim/封闭场地验证方案

### 5.1 测试场景

#### 场景1: Baseline性能
- 标准5v5场景
- 建立性能基线

#### 场景2: 压力测试
- 10v10、15v15
- 验证可扩展性

#### 场景3: 长时运行
- 持续运行10分钟
- 验证稳定性

#### 场景4: 对抗场景
- 目标规避机动
- 验证鲁棒性

#### 场景5: 故障注入
- 传感器失效、网络故障
- 验证容错性

### 5.2 成功指标

| 指标 | 当前 | 短期 | 中期 |
|------|------|------|------|
| 任务成功率 | 未定义 | 定义并>80% | >90% |
| 根因诊断准确率 | 0% | N/A | >70% |
| 测试场景覆盖率 | ~30% | >70% | >90% |
| CI运行时间 | N/A | <10分钟 | <5分钟 |
| 性能回归检测率 | 0% | >90% | >95% |

### 5.3 对比基准

- 工程指标 vs 学术指标 (MOTA/MOTP)
- 改进版本 vs Baseline
- 不同参数配置对比

---

## 6. 实施风险与缓解

### 6.1 技术风险

| 风险 | 影响 | 缓解 |
|------|------|------|
| 指标定义争议 | 评估标准不统一 | 与用户确认、文档化 |
| 数据量大 | 存储/计算开销 | 压缩、采样、增量处理 |
| 对比不公平 | 误导结论 | 固定随机种子、多次运行 |

### 6.2 集成风险

| 风险 | 缓解 |
|------|------|
| 破坏现有流程 | 保持向后兼容 |
| CI时间过长 | 分级测试（smoke/full） |
| Dashboard维护成本 | 可选组件 |

---

## 7. 参考案例与文献

### 7.1 工业标准
1. DO-178C: 航空软件安全
2. ISO 26262: 汽车功能安全
3. FMEA: SAE J1739标准

### 7.2 开源实现
1. TrackEval: <https://github.com/JonathonLuiten/TrackEval>
2. py-motmetrics: <https://github.com/cheind/py-motmetrics>
3. MLflow: <https://github.com/mlflow/mlflow>

### 7.3 学术文献（工程导向）
1. Bernardin & Stiefelhagen "Evaluating Multiple Object Tracking Performance: The CLEAR MOT Metrics" (MOTA/MOTP)
2. Luiten et al. "HOTA: A Higher Order Metric for Evaluating Multi-object Tracking" (HOTA)
3. Schuhmacher et al. "A Consistent Metric for Performance Evaluation of Multi-Object Filters" (OSPA)

### 7.4 工业报告
1. Waymo Safety Report
2. Tesla Autopilot Safety Report

---

## 8. 实施优先级

### P0 (立即)
1. 系统级任务成功指标
2. 根因诊断
3. 性能监测

### P1 (3个月)
1. 基线对比框架
2. 场景库管理
3. CI/回归测试

### P2 (6个月)
1. 对抗性评估
2. 标准MOT指标
3. 场景覆盖率分析

### P3 (长期)
1. 在线Dashboard
2. ML辅助评估

---

## 9. 结论

当前D6评估体系已建立基础指标框架，但在**系统级评估、根因诊断、对比分析、持续集成**方面存在不足。

**推荐路径**:
1. **短期**: 任务成功率 + 根因诊断 + 性能监测
2. **中期**: 场景库 + CI流水线 + 对抗评估
3. **长期**: 在线监测 + ML辅助

所有改进基于成熟工程实践(DO-178C、FMEA、MOT标准)，可在AirSim验证。

---

**文档维护者**: 框架评估工作组
**下次更新**: 短期改进完成后
