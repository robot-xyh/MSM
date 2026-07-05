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
- 关联器和 Tracker 按每帧输入的 `tracks`/`detections` 集合长度运行；2v2、5v5 只作为仿真 fixture 或验收场景，不写入算法假设。

---

## 2. 文献综述要点

2015-2026 年多目标跟踪主线仍是“运动预测 + 门控 + 数据关联 + 航迹管理”。

GNN/Hungarian 是硬关联方法。它把每个观测分配给一个航迹，优点是计算轻、延迟低、解释性强，适合 5v5 等初始验证 fixture，也适合 main runtime 通过 `--drone-count` 传入的其他中小规模集合。缺点是当目标距离很近、交叉或并行运动时，一次错误匹配会造成 ID Switch。

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

## 7. 多视角末端反馈与主动降级接口

### 7.1 与 D5 多视角末端反馈的关系

D5 可能同时接收多个拦截无人机的末端视觉结果。典型情况包括：

- 多个拦截无人机都看到同一个目标。
- 某些拦截无人机视场内出现多个候选目标。
- 某些拦截无人机未看到分配目标，只看到友方、未知目标或局部遮挡。
- 二级侦察节点给局部拦截无人机发送图像 cue，形成中心航迹、二级视角和末端相机之间的多视角约束。

D2 的原则是：`global_track_id` 只能由 D2 的全局数据关联链路维护，D5 的 `TerminalAssociation` 和 `IdentityClaim` 只能作为弱证据输入，不允许直接改写规范 ID。

建议的弱证据使用方式：

```text
D5 TerminalAssociation
  -> association_confidence
  -> ambiguity_score
  -> friend_conflict_state
  -> decision_state: locked / ambiguous / hold / reacquire
  -> candidate_global_track_ids
```

```text
D5 IdentityClaim
  -> claim_type: cooperative_id / remote_id / visual_tag
  -> auth_state: verified / stale / unverified / spoof_suspected
```

D2 可以使用这些信息调整航迹置信度或风险摘要：

- 多个 D5 视角稳定支持同一 `global_track_id`：提高该航迹的身份连续性置信，但不跳过 D2 门控。
- D5 报告多个局部目标都可匹配同一 `global_track_id`：提高 `association_ambiguity` 和 `duplicate_track_risk`。
- D5 报告分配目标长期不在投影门内：标记 `d5_disagreement`，提示 D3/D4 重评估。
- `IdentityClaim` 为 verified friendly：作为正向友方证据进入安全约束，但不能反向证明未知目标为敌方。
- `spoof_suspected`、`stale` 或 `unverified`：只能降低身份置信或触发 hold/observe，不得驱动 ID 改绑。

### 7.2 输出给 D4 主动降级的风险量

D4 主动降级需要判断“中心/二级节点仍存在，但当前全局关联和分配是否已经不可靠”。D2 应输出低频 `AssociationRiskSummary` 或等价字段，至少包含：

| 风险量 | 来源 | 解释 |
|--------|------|------|
| `id_switch_count` / `id_switch_rate` | `MetricsRecorder` 滑窗差分 | ID 在交叉或遮挡后是否频繁交换 |
| `track_continuity` 下降 | `identity_continuity` / `track_continuity` | 目标仍被覆盖，但身份连续性变差 |
| 协方差交叠率 | 航迹协方差椭圆或门控候选重叠 | 多个航迹的不确定区域重叠，硬关联风险升高 |
| 重复航迹风险 | `duplicate_assignment_count`、混淆矩阵 | 同一目标被多个 `global_track_id` 解释 |
| 关联歧义 | `AssociationResult.ambiguity_score`、代价 margin | 最优与次优候选差距过小 |
| 检测漏失时间 | `misses`、`last_update_time`、`lost` 状态持续时长 | 高质量航迹长期未被观测，分配输入可能过期 |
| JPDA/MHT 升级建议 | 候选数、歧义、遮挡历史 | 提示 D4 请求软关联或多假设对照 |
| D5 长期不一致 | `TerminalAssociation` 回传 | 中心预测与末端视角持续冲突 |

建议风险等级：

```text
nominal:
  GNN 关联清晰，ID 连续性稳定

elevated:
  单帧或局部歧义升高，建议 D3 提高重分配迟滞

high:
  多帧 ID 风险持续，建议 D4 主动重评估中心/二级节点链路

critical:
  IDSW、重复航迹和末端不一致同时恶化，建议 D4 进入主动降级仲裁
```

D2 不决定是否切换二级节点或分布式协同；D2 只发布风险证据，D4 综合 D1 定位质量、D3 分配抖动和 D5 末端反馈后做仲裁。

风险摘要中的 `affected_global_track_ids`、`candidate_global_track_ids` 和 D3/D5 消费的航迹列表都应由当前活动航迹集合派生，不应按 2 或 5 个目标预分配、补齐或截断。

### 7.3 输出给 D7 比例导引的稳定目标状态要求

D7 的中段 PN 需要连续、低抖动、可解释的目标状态。D2 不输出导引指令，只提供目标状态质量门槛。建议 D7 只能消费满足以下条件的 `GlobalTrack`：

- `lifecycle_state` 为 `confirmed` 或 `engageable`。
- `global_track_id` 在最近滑窗内无 ID Switch，或 `id_switch_rate` 低于配置门限。
- `track_continuity` / `identity_continuity` 高于配置门限。
- 位置和速度协方差低于 D7 接口门限，且 `last_update_time` 未超时。
- 当前航迹没有被标记为重复航迹或高歧义航迹。
- 若 D5 回传末端关联冲突，该 `GlobalTrack` 应暂缓进入 PN 输入，等待 D4/D3 重评估。

推荐向 D7 提供的字段：

```text
StableTargetState
- global_track_id
- timestamp
- position
- velocity
- covariance
- lifecycle_state
- identity_confidence
- continuity_score
- association_risk_level
- stale_time
```

只有稳定目标状态可用于中段 PN 仿真；`tentative`、`lost`、`dropped` 或 `risk_level >= high` 的航迹不应进入 D7 主输入。

### 7.4 工程改进检查

当前 D2 工程路线应保持：

- 默认关联器为 GNN/Hungarian，作为低延迟、可解释、可测试的主线。
- JPDA/MHT 作为交叉密集、遮挡恢复和多候选歧义场景的可插拔升级项。
- IMM-EKF/UKF 作为后续运动预测增强，不替代数据关联接口。
- 所有关联器必须输出 `AssociationResult`，包括匹配、拒配、代价矩阵、歧义分数和元数据。
- `id_switch_count`、`track_continuity`、`duplicate_assignment_count`、协方差交叠、检测漏失时间和 D5 不一致事件必须进入 D6 评估。

---

## 8. 测试方案

| 测试 | 设置 | 指标 |
|------|------|------|
| 两目标交叉 | 两条航迹交叉，加入噪声 | `id_switch_count` |
| 编队密集 | 5目标平行接近，作为 baseline fixture | `track_continuity` |
| 漏检 | 随机丢失观测 | `lost_to_confirmed_rate` |
| 杂波 | 增加虚假观测 | `false_track_count` |
| 算法对比 | GNN vs JPDA vs MHT | IDSW、延迟、运行时间 |

GNN 是默认基线。JPDA/MHT 不要求所有场景绝对优于 GNN，但必须输出可解释的失败模式。除固定 fixture 外，应至少保留一个非 2/5 数量的合同测试，证明 `global_track_id` 输出和指标统计来自输入集合长度。

---

## 9. 交付物

1. GNN/JPDA/MHT/IMM-EKF/UKF 适用边界综述。
2. Stone Soup 与 FilterPy 复用性报告。
3. `DataAssociator` 抽象接口与三类实现设计。
4. 航迹状态机与指标记录器设计。
5. 交叉航迹单元测试和算法对比报告。

---

## 10. 参考资料

- Stone Soup: <https://github.com/dstl/Stone-Soup>
- Stone Soup JPDA tutorial: <https://stonesoup.readthedocs.io/en/latest/auto_tutorials/08_JPDATutorial.html>
- Stone Soup MHT example: <https://stonesoup.readthedocs.io/en/latest/auto_examples/dataassociation/mht_example.html>
- FilterPy: <https://filterpy.readthedocs.io/>
- SciPy `linear_sum_assignment`: <https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.linear_sum_assignment.html>
- SORT paper: <https://arxiv.org/abs/1602.00763>
- Deep SORT paper: <https://arxiv.org/abs/1703.07402>
- py-motmetrics: <https://github.com/cheind/py-motmetrics>
