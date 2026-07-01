# D2 多目标跟踪与数据关联综述及子方案

**定位**: 维护稳定的 `global_track_id`，在目标交叉、编队密集、漏检和杂波条件下抑制 ID Switch。  
**边界**: 本文只讨论科研仿真中的多目标跟踪、数据关联、状态机和指标记录，不包含真实火控参数、毁伤逻辑或自动处置流程。

---

## 1. 研究问题

多目标场景中，系统最大的风险之一是“目标还在，但身份换了”。如果 `T1` 与 `T3` 在交叉后被互换，后续分配、末端视觉锁定和评估指标都会失真。

本子系统的目标是：

- 使用 GNN/Hungarian 作为默认工程基线。
- 在目标密集、交叉或遮挡时可插拔升级 JPDA/MHT。
- 使用 IMM-EKF/UKF 改善机动预测。
- 强制记录 `id_switch_count`、`track_continuity` 和 `duplicate_assignment_count`。

---

## 2. 文献综述要点

2015-2026 年多目标跟踪主线仍是“运动预测 + 门控 + 数据关联 + 航迹管理”。

GNN/Hungarian 是硬关联方法。它把每个观测分配给一个航迹，优点是计算轻、延迟低、解释性强，适合 5 对 5 初始验证。缺点是当目标距离很近、交叉或并行运动时，一次错误匹配会造成 ID Switch。

JPDA 是软关联方法。它对多个候选观测计算联合概率，再对每条航迹做边缘化更新。相比 GNN，JPDA 在交叉和不确定关联时更稳，但目标过密时存在航迹合并风险。

MHT 是延迟决策方法。它保留多帧假设树，通过剪枝选择全局更合理的解释。MHT 对遮挡和交叉更强，但计算和内存成本高，不建议部署在资源节点，只适合中心节点或离线评估。

IMM-EKF/UKF 不是关联算法，但能改善机动目标预测。目标机动模型切换明显时，IMM 可同时维护匀速、转弯、加速等模型概率，从而降低门控和关联错误。

---

## 3. 开源代码选型

| 工具 | 可复用内容 | 适用方式 |
|------|------------|----------|
| Stone Soup | GNN、JPDA、MHT、轨迹管理、指标示例 | 中心节点科研验证主框架 |
| FilterPy | EKF、UKF、IMMEstimator | 运动模型和滤波器原型 |
| SciPy | `linear_sum_assignment` | GNN/Hungarian底层求解器 |
| py-motmetrics / CLEAR MOT | ID Switch、MOTA等指标 | 离线评估参考 |

二次开发建议：

1. 不直接把 Stone Soup 对象暴露为系统总线消息。
2. 封装统一 `DataAssociator` 接口，让 GNN/JPDA/MHT 可替换。
3. 所有关联器必须输出代价、拒配原因和歧义分数。
4. 指标记录器独立于关联器，避免算法切换后指标不可比。

---

## 4. 子系统架构

### 4.1 类图

```text
abstract DataAssociator
  + associate(tracks, detections, timestamp) -> AssociationResult

GNNHungarianAssociator --|> DataAssociator
JPDAAssociator         --|> DataAssociator
MHTAssociator          --|> DataAssociator

TrackManager
  + predict_all(timestamp)
  + update(association_result)
  + create_tentative_tracks()
  + prune_lost_tracks()

TrackStateMachine
  tentative -> confirmed -> engageable -> engaged -> lost -> dropped

MetricsRecorder
  id_switch_count
  track_continuity
  duplicate_assignment_count
```

### 4.2 关联结果

```text
AssociationResult
- timestamp
- matched_pairs: [(global_track_id, detection_id, cost)]
- unmatched_tracks
- unmatched_detections
- ambiguity_score
- associator_type
- rejected_pairs_with_reason
```

---

## 5. 核心伪代码

```python
class DataAssociator:
    def associate(self, tracks, detections, timestamp):
        raise NotImplementedError

class GNNHungarianAssociator(DataAssociator):
    def associate(self, tracks, detections, timestamp):
        cost = gated_mahalanobis_cost(tracks, detections)
        rows, cols = linear_sum_assignment(cost)
        return reject_pairs_above_gate(rows, cols, cost)

class JPDAAssociator(DataAssociator):
    def associate(self, tracks, detections, timestamp):
        hypotheses = enumerate_valid_joint_hypotheses(tracks, detections)
        marginals = marginalize_probabilities(hypotheses)
        return weighted_association_result(marginals)

class MHTAssociator(DataAssociator):
    def associate(self, tracks, detections, timestamp):
        tree = expand_hypothesis_tree(tracks, detections)
        pruned = prune_by_score_and_depth(tree)
        return best_branch_or_deferred_result(pruned)
```

指标记录：

```python
class MetricsRecorder:
    def update_identity(self, truth_id, track_id):
        old = self.last_truth_to_track.get(truth_id)
        if old is not None and old != track_id:
            self.id_switch_count += 1
        self.last_truth_to_track[truth_id] = track_id
```

---

## 6. 状态机

```text
tentative:
  新观测生成，尚未稳定

confirmed:
  连续命中达到阈值，航迹可参与融合显示

engageable:
  航迹质量、协方差和身份置信度达到分配候选条件

engaged:
  已被AssignmentPlan引用

lost:
  短时未观测到，但仍保留预测

dropped:
  超时或质量发散，移出活动表
```

任何状态变化都必须写入 `TrackRecord`，并带原因字段。

---

## 7. 测试方案

| 测试 | 设置 | 指标 |
|------|------|------|
| 两目标交叉 | 两条航迹交叉，加入噪声 | `id_switch_count` |
| 编队密集 | 5目标平行接近 | `track_continuity` |
| 漏检 | 随机丢失观测 | `lost_to_confirmed_rate` |
| 杂波 | 增加虚假观测 | `false_track_count` |
| 算法对比 | GNN vs JPDA vs MHT | IDSW、延迟、运行时间 |

GNN 是默认基线。JPDA/MHT 不要求所有场景绝对优于 GNN，但必须输出可解释的失败模式。

---

## 8. 交付物

1. GNN/JPDA/MHT/IMM-EKF/UKF 适用边界综述。
2. Stone Soup 与 FilterPy 复用性报告。
3. `DataAssociator` 抽象接口与三类实现设计。
4. 航迹状态机与指标记录器设计。
5. 交叉航迹单元测试和算法对比报告。

---

## 9. 参考资料

- Stone Soup: <https://github.com/dstl/Stone-Soup>
- Stone Soup JPDA tutorial: <https://stonesoup.readthedocs.io/en/latest/auto_tutorials/08_JPDATutorial.html>
- Stone Soup MHT example: <https://stonesoup.readthedocs.io/en/latest/auto_examples/dataassociation/mht_example.html>
- FilterPy: <https://filterpy.readthedocs.io/>
- SciPy `linear_sum_assignment`: <https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.linear_sum_assignment.html>
- SORT paper: <https://arxiv.org/abs/1602.00763>
- Deep SORT paper: <https://arxiv.org/abs/1703.07402>
- py-motmetrics: <https://github.com/cheind/py-motmetrics>
