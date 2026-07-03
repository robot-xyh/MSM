# D2 多目标跟踪与数据关联算法原理与实施方案

## 1. 模块定位

D2 负责把 D1 输出的多源融合观测或初始航迹整理成稳定的 `global_track_id` 序列。它解决的核心问题不是“位置是否足够准”，而是“同一个目标在交叉、遮挡、漏检和虚警条件下是否仍由同一个全局身份连续表示”。D2 输出供 D3 做资源-目标分配，供 D5 做末端视觉配准，供 D6 计算系统级指标。

本模块仅用于离线科研仿真与日志回放评估，不包含真实飞控、硬件驱动、火控、毁伤、自动处置或授权绕过逻辑。

## 2. 输入输出

### 2.1 输入

当前可执行实现使用二维位置量测作为研究基线：

- `Detection.detection_id`：单帧观测唯一编号。
- `Detection.timestamp`：量测时间。
- `Detection.position`：二维位置或投影平面坐标。
- `Detection.covariance`：二维量测协方差。
- `Detection.feature`：可选外观、类别或声纹类特征向量。
- `Detection.truth_id`：仅用于离线评估，不参与真实部署决策。

在系统集成中，D1 的 `GlobalTrack` 可通过适配器转换为 D2 的 `Detection` 或直接扩展为带状态预测的航迹输入。关键要求是保留时间戳、协方差和来源元数据。

### 2.2 输出

D2 输出更新后的 `GlobalTrack` 列表和 `AssociationResult`：

- `global_track_id`：稳定身份键，下游模块不得自行改写。
- `state = [x, y, vx, vy]^T`：常速度研究状态。
- `covariance`：状态不确定性。
- `lifecycle_state`：`tentative / confirmed / engageable / lost / dropped`。
- `matched_pairs`、`unmatched_track_ids`、`unmatched_detection_ids`：每帧关联结果。
- `ambiguity_score`、`rejected_pairs`、`metadata`：解释失败和歧义来源。

## 3. 数学模型

### 3.1 运动与观测模型

默认状态向量为：

```text
x = [px, py, vx, vy]^T
```

常速度预测模型为：

```text
x_k = F(dt) x_{k-1} + w
P_k = F P_{k-1} F^T + Q(dt)
```

二维位置观测模型为：

```text
z_k = H x_k + v
H = [[1, 0, 0, 0],
     [0, 1, 0, 0]]
```

其中 `Q` 由 `Tracker.process_noise` 控制，`R` 来自 `Detection.covariance`。

### 3.2 马氏距离门控

对航迹 `i` 和观测 `j`：

```text
z_hat_i = H x_i
S_ij = H P_i H^T + R_j
r_ij = z_j - z_hat_i
d_ij^2 = r_ij^T S_ij^-1 r_ij
```

若 `d_ij^2 > gate_threshold`，该候选对被拒绝，并记录为 `RejectedPair(reason="mahalanobis_gate")`。默认 `gate_threshold=9.21`，约等于二维 99% 卡方门限，适合低维位置量测的初始基线。

## 4. GNN/Hungarian 默认主线

GNN/Hungarian 是本模块默认硬关联方案。它把每一帧的“航迹-观测”匹配建模为线性分配问题：

```text
C_ij = d_ij^2 + w_f * feature_cost_ij
```

其中 `d_ij^2` 是马氏距离，`feature_cost_ij` 是可选特征差异，`w_f` 对应 `feature_weight`。门外候选被填入大代价 `LARGE_COST`。随后使用 `scipy.optimize.linear_sum_assignment` 求解一对一最小总代价匹配。

适用边界：

- 目标数量中小，当前仿真为 2-6 个目标。
- 每条航迹门内候选较少，典型候选数接近 1。
- 观测频率稳定，短时漏检可由预测维持。
- 交叉持续时间短，外观或类别特征能提供辅助区分。

局限：

- GNN 是硬判决，一旦交叉帧选错，后续可能产生 ID Switch。
- 当两条航迹协方差高度重叠、门内候选都合理时，GNN 无法表达“不确定但暂缓确认”。
- 虚警密集时，若门限过宽或协方差过大，容易错误吸附杂波。

因此 GNN/Hungarian 是工程默认基线，不是所有场景的最终算法。

## 5. 漏检、虚警与航迹生命周期

### 5.1 漏检处理

未匹配航迹不会立即删除，而是进入预测维持：

```text
misses += 1
consecutive_hits = 0
identity_confidence -= 0.25
```

当 `misses >= lost_miss_threshold` 时转为 `lost`；当 `misses >= drop_miss_threshold` 时转为 `dropped`。这样可以覆盖短时遮挡，但不会无限保留陈旧航迹。

### 5.2 虚警处理

未匹配观测默认可以生成 `tentative` 航迹。只有连续命中达到 `confirmation_hits` 后才进入 `confirmed`，达到 `engageable_hits` 且协方差迹低于 `engageable_covariance_trace` 后才进入 `engageable`。这里的 `engageable` 只表示“可供下游离线分配实验使用的高质量航迹”，不代表授权或处置状态。

### 5.3 生命周期状态机

```text
tentative -> confirmed -> engageable -> lost -> dropped
             ^              |
             |              v
          reacquired <---- lost
```

所有状态转移记录在 `TrackTransition`，用于 D6 复盘身份断裂、遮挡恢复和虚警形成过程。

## 6. JPDA 可插拔升级项

JPDA 将关联从硬判决改为概率边缘化。对于一帧内所有合法联合假设 `H_k`，简化似然为：

```text
L(H_k) = Π matched exp(-0.5 d_ij^2)
         * Pd^(matched_count)
         * (1-Pd)^(missed_count)
         * clutter_density^(unmatched_detection_count)
```

归一化后得到每个候选对的边缘概率：

```text
β_ij = Σ P(H_k | Z), for H_k containing (i, j)
```

当前实现枚举小规模联合假设，并以 `min_marginal_probability` 选出非冲突匹配。它适合作为 2-6 目标交叉、遮挡和高歧义帧的研究对照。

建议触发 JPDA 的条件：

- `candidate_counts_by_track` 的均值持续大于 1.5。
- `ambiguity_score` 连续升高。
- 目标协方差门重叠，且 GNN 在回放中出现 ID Switch。
- 遮挡恢复阶段出现多个合理重连候选。

代价是联合假设数量随目标和观测数量组合增长，必须限制 `max_joint_hypotheses`，并在 `metadata["truncated"]` 中记录截断状态。

## 7. MHT 可插拔升级项

MHT 将多个帧的关联假设保留下来，延迟做全局选择。当前实现维护有界分支：

```text
branch = (score, history, branch_id)
```

每帧扩展合法分配，加入漏检惩罚和虚警惩罚，保留 `max_hypotheses` 个最优分支，并用 `max_history` 限制历史长度。

MHT 适合研究这些情况：

- 长遮挡后需要回看多帧证据。
- 单帧信息不足，但多帧轨迹连续性可以排除错误假设。
- 需要与完整 Stone Soup MHT 或外部研究库对比。

局限是复杂度随时间和候选数呈指数趋势，必须依赖剪枝、N-scan、分簇或场景分区。当前实现是有界研究接口，不应被解释为完整工业级 MHT。

## 8. IMM-EKF/UKF 的意义

当前可执行基线使用常速度 Kalman 预测。若目标存在明显机动，预测误差会扩大，导致门控变宽或候选交叠，从而间接增加 ID Switch。IMM-EKF/UKF 的作用是改善预测质量，而不是替代数据关联：

- EKF：适合轻度非线性观测或二维/三维运动学扩展，计算轻。
- UKF：适合非线性更强、雅可比难维护的模型。
- IMM：并行维护常速度、常加速度、协调转弯等模型，并根据模型概率融合预测。

推荐路径是先保持 D2 的 `DataAssociator` 接口不变，把预测器从常速度 Kalman 替换为 IMM-EKF/UKF，再比较 `id_switch_count` 和 `identity_continuity` 是否改善。

## 9. 主要实施流程

每帧处理链路如下：

```text
DetectionBatch
  -> Tracker.predict_all(timestamp)
  -> DataAssociator.associate(active_tracks, detections, timestamp)
  -> matched tracks: Kalman update + lifecycle advance
  -> unmatched tracks: miss/lost/drop handling
  -> unmatched detections: create tentative tracks
  -> MetricsRecorder.record_frame(...)
```

核心文件：

- `d2_data_association/models.py`：数据结构和生命周期枚举。
- `d2_data_association/gating.py`：马氏门控、代价矩阵、歧义分数。
- `d2_data_association/associators.py`：GNN、JPDA、MHT 关联器。
- `d2_data_association/tracker.py`：预测、更新、建轨、删轨、状态机。
- `d2_data_association/metrics.py`：ID Switch、连续性、重复分配、RMSE。
- `d2_data_association/simulation.py`：交叉、编队、遮挡、漏检、虚警场景。

## 10. 关键接口

```python
associator = GNNHungarianAssociator(gate_threshold=9.21, feature_weight=6.0)
tracker = Tracker(associator=associator)
result = tracker.step(detections, timestamp, truth_ids_present=truth_ids)
summary = tracker.metrics.summary()
```

`DataAssociator.associate()` 是插件边界。任何新算法只要返回 `AssociationResult`，即可复用现有 `Tracker`、生命周期和指标系统。

## 11. 参数与调参建议

| 参数 | 默认/示例 | 作用 | 调参建议 |
|---|---:|---|---|
| `gate_threshold` | `9.21` | 马氏门控大小 | IDSW 高且漏配少时收紧；漏检多时先检查协方差再放宽 |
| `feature_weight` | `6.0` | 特征差异权重 | 只有特征稳定时提高；特征噪声大时降低 |
| `process_noise` | `0.20` | 预测模型机动余量 | 机动目标门外漏配时提高；虚警吸附时降低 |
| `confirmation_hits` | `2` | 建轨确认速度 | 虚警多时提高；短航迹多时降低 |
| `engageable_hits` | `4` | 高质量航迹门槛 | 下游分配过早时提高 |
| `lost_miss_threshold` | `2` | 进入 lost 的漏检帧数 | 短遮挡多时提高 |
| `drop_miss_threshold` | `5` | 删除航迹的漏检帧数 | 长遮挡研究可提高，但会增加陈旧航迹 |
| `min_marginal_probability` | `0.30-0.35` | JPDA 输出阈值 | 歧义高时提高以减少误连，或降低以提高覆盖 |
| `max_hypotheses` | `16` | MHT 分支上限 | 仅在离线研究中按算力增加 |

调参顺序建议：先校准协方差和门限，再引入特征权重，最后切换 JPDA/MHT。不要用复杂关联器掩盖错误的时间戳、坐标转换或协方差建模。

## 12. 仿真验证与指标

内置仿真场景：

- `crossing`：两目标交叉。
- `formation`：五目标近距编队。
- `occlusion`：三目标短时遮挡。
- `missed`：随机漏检。
- `false_alarms`：虚警杂波。

运行示例：

```bash
PYTHONPATH=research_modules/d2_data_association \
python3 research_modules/d2_data_association/scripts/run_simulation.py --steps 36 --seed 7
```

必须显式评估的指标：

- `id_switch_count`：同一真值目标的代表航迹发生变化的次数。它直接反映身份连续性风险。
- `track_continuity` / `identity_continuity`：真值存在期间由同一身份稳定覆盖的比例。
- `coverage_continuity`：真值存在期间是否被任意航迹覆盖。
- `duplicate_assignment_count`：同一帧一对多、多对一或同真值多航迹覆盖的异常数量。
- `rmse`：位置误差，不能替代身份指标。
- `confusion_matrix`：真值目标与全局航迹的对应分布。
- `runtime_seconds_by_associator`：算法耗时，用于比较实时性余量。

这些指标必须进入 D6，因为单看 RMSE 可能掩盖身份交换；单看命中或覆盖也可能掩盖重复分配。

## 13. 面向 D4 主动降级的关联风险信号

D4 的主动降级不是被动等待中心节点失效，而是在中心或二级节点仍存在时，根据态势质量判断当前中心化分配链路是否需要重评估、切换到二级节点辅助，或进入分布式协同对照。D2 不直接决定降级，也不改变 D3 的分配计划；D2 只提供“关联不确定度与 ID 风险”信号，供 D3/D4/D6 在离线仿真中仲裁。

### 13.1 D2 可提供的触发信号

| 信号 | 数据来源 | 含义 | 风险解释 |
|---|---|---|---|
| `association_ambiguity` | `AssociationResult.ambiguity_score` | 候选代价差距是否变小 | 越接近 1，说明多个候选观测都合理，GNN 硬关联更容易选错 |
| `cost_margin` | `cost_matrix` 每行最小和次小有效代价 | 最优匹配相对次优匹配的优势 | margin 小表示航迹身份容易交换 |
| `gating_overlap_ratio` | `candidate_counts_by_track`、`candidate_counts_by_detection` | 多条航迹共享观测候选或单条航迹有多个候选 | 交叉、密集编队、协方差膨胀时会升高 |
| `id_switch_rate` | `MetricsRecorder.id_switch_count` 窗口增量 | 单位时间 ID Switch 增长速度 | 直接说明 `global_track_id` 连续性已经失稳 |
| `continuity_drop` | `track_continuity` / `identity_continuity` 窗口变化 | 身份连续性下降 | 说明目标仍被覆盖，但身份键可能不稳定 |
| `duplicate_track_risk` | `duplicate_assignment_count`、混淆矩阵 | 同一真值或观测被多个航迹解释 | 会污染 D3 的一对一资源分配输入 |
| `state_regression_count` | `TrackTransition` | `engageable/confirmed -> lost` 或高质量航迹退化 | 说明下游可用航迹数量正在下降 |
| `jpda_recommended` | 候选数、歧义分数、门控重叠 | 是否建议从 GNN 升级到 JPDA 对照 | 适合短时交叉、遮挡恢复和多候选软关联 |
| `mht_recommended` | 连续多帧歧义、遮挡历史、ID 证据冲突 | 是否建议启用 MHT 对照 | 适合需要跨多帧回溯的持续遮挡或反复交换 |
| `d5_disagreement` | D5 终端关联反馈，若接入 | 中心航迹预测与终端局部观测长期不一致 | 说明中心身份链路可能与末端视觉证据冲突 |

这些信号不等同于“目标处置建议”。它们只表示 D2 对当前 `global_track_id` 稳定性的可信程度。

### 13.2 `AssociationRiskSummary` 建议结构

建议在 D2 风险摘要中表达跨视角弱证据和跨节点通信来源，而不是让 D4 直接解析完整代价矩阵。D2 仍是 `global_track_id` 权威；D5、二级节点和拦截机只能提交弱证据、候选 ID 和风险提示，不能直接改写规范 ID。字段建议如下：

```text
AssociationRiskSummary
  timestamp: float
  window_start: float
  window_end: float
  source_module: "D2"
  source_node_id: str | None
  link_type: c2_direct | secondary_relay | interceptor_peer | video_cue | None
  associator_type: str
  global_risk_score: float        # 0.0 nominal, 1.0 critical
  risk_level: nominal | elevated | high | critical
  affected_global_track_ids: list[str]
  association_ambiguity_ema: float
  mean_cost_margin: float
  low_margin_pair_count: int
  mean_candidates_per_track: float
  multi_candidate_track_ratio: float
  shared_detection_candidate_ratio: float
  id_switch_rate: float
  track_continuity: float
  continuity_drop: float
  duplicate_assignment_delta: int
  state_regression_count: int
  engageable_to_lost_count: int
  d5_disagreement_count: int       # optional feedback field
  jpda_recommended: bool
  mht_recommended: bool
  recommend_active_reevaluation: bool
  evidence: list[str]
```

`window_start/window_end` 应采用滑动窗口，例如 3-10 秒或 5-20 帧。单帧歧义只应触发“观察/重评估”，连续窗口异常才建议 D4 进入主动降级仲裁，避免偶发噪声导致模式抖动。

### 13.3 风险评分建议

一个可解释的离线评分可以采用加权归一化：

```text
S = 0.25 * ambiguity_term
  + 0.20 * gate_overlap_term
  + 0.20 * id_switch_term
  + 0.15 * continuity_drop_term
  + 0.10 * duplicate_term
  + 0.10 * state_regression_term
```

各分项建议定义：

- `ambiguity_term = EMA(AssociationResult.ambiguity_score)`。
- `gate_overlap_term = max(multi_candidate_track_ratio, shared_detection_candidate_ratio)`。
- `id_switch_term = clamp(id_switch_delta / window_frames, 0, 1)`。
- `continuity_drop_term = clamp(previous_continuity - current_continuity, 0, 1)`。
- `duplicate_term = clamp(duplicate_assignment_delta / max(1, matched_pair_count), 0, 1)`。
- `state_regression_term = clamp(state_regression_count / max(1, active_track_count), 0, 1)`。

风险等级建议：

| `global_risk_score` | `risk_level` | D2 解释 |
|---:|---|---|
| `< 0.25` | `nominal` | GNN 关联稳定，正常记录 |
| `0.25-0.50` | `elevated` | 有局部歧义，建议 D3 延迟不必要重分配并继续观察 |
| `0.50-0.75` | `high` | 身份连续性存在明显风险，建议 D4 主动重评估中心/二级节点链路 |
| `>= 0.75` | `critical` | 多指标同时恶化，建议 D4 进入主动降级仲裁并请求 JPDA/MHT 对照结果 |

阈值应通过离线仿真标定，不应直接用于真实系统。

### 13.4 从现有日志提取风险

当前 D2 已经记录或输出多数所需证据：

- `AssociationResult.ambiguity_score`：直接作为歧义基础项。
- `AssociationResult.cost_matrix`：计算每条航迹的最小/次小代价 margin。
- `AssociationResult.metadata["candidate_counts_by_track"]`：统计多候选航迹比例。
- `AssociationResult.metadata["candidate_counts_by_detection"]`：统计共享观测候选比例。
- `AssociationResult.unmatched_track_ids`：结合航迹状态，统计高质量航迹漏配。
- `MetricsRecorder.id_switch_count`：窗口差分得到 `id_switch_rate`。
- `MetricsRecorder.track_continuity`：窗口差分得到 `continuity_drop`。
- `MetricsRecorder.duplicate_assignment_count`：窗口差分得到重复解释风险。
- `Tracker.state_transitions`：筛选 `confirmed/engageable -> lost/dropped` 得到退化计数。

代价 margin 计算示例：

```text
valid_costs = sorted(row[row < LARGE_COST])
if len(valid_costs) >= 2:
    margin = valid_costs[1] - valid_costs[0]
else:
    margin = +inf
low_margin = margin < margin_threshold
```

`margin_threshold` 可先取 `1.0-2.0` 的马氏距离代价差作为离线实验初值，再用交叉和编队场景标定。

### 13.5 主动重评估触发条件

以下情况应提示 D3/D4 进入主动重评估，而不是继续信任上一版分配：

- 多目标交叉窗口内 `id_switch_rate` 上升，且 `association_ambiguity_ema > 0.5`。
- 多个 `GlobalTrack` 同时把同一观测列为门内候选，`shared_detection_candidate_ratio` 持续升高。
- `engageable` 航迹连续回退到 `lost`，导致 D3 的可分配目标集合不稳定。
- `duplicate_assignment_count` 在窗口内增长，说明同一目标可能被多个全局身份解释。
- D5 末端视觉配准长期报告“分配目标不在预期投影门内”或多个局部目标都可匹配同一 `global_track_id`。
- GNN 输出稳定但 JPDA 边缘概率分散，说明硬关联结果可能只是任意打破平局。
- MHT 多分支长期不能收敛到单一低代价历史，说明需要 D4 引入二级节点或分布式视角进行独立交叉校验。

### 13.6 给 D4/D3 的接口建议

D2 建议向 D4/D3 发布低频风险摘要，例如 1-2 Hz，而不是每帧发布完整矩阵。推荐消费方式：

- D3：当 `risk_level >= elevated` 时，提高重分配迟滞，避免在身份不稳定窗口内频繁改分配；当 `risk_level >= high` 时，请求使用 `confirmed/engageable` 且低风险的航迹子集重新计算分配。
- D4：当 `risk_level >= high` 且持续超过 `min_risk_dwell_time` 时，进入主动降级仲裁，比较中心节点、二级侦察节点和局部分布式节点的航迹一致性。
- D6：记录 `AssociationRiskSummary`，用于统计主动降级是否真正减少 ID Switch、重复分配和末端不一致事件。

D2 只给出 `recommend_active_reevaluation`、`jpda_recommended` 和 `mht_recommended` 等研究信号。是否切换二级节点、是否进入分布式协同，必须由 D4 在综合 D1/D3/D5 信号后决定。

## 14. 跨模块接口关系

### D1 -> D2

D1 输出多传感器融合后的观测或粗航迹。D2 需要其中的时间戳、位置/投影、协方差、置信度、可选类别或特征。若 D1 使用三维 NED 航迹，进入 D2 前应明确投影平面或扩展 D2 状态维度。

### D2 -> D3

D3 依赖稳定的 `global_track_id`、状态、协方差和生命周期状态构造分配代价。D2 应避免把 `tentative` 或长期 `lost` 航迹直接作为高置信输入；推荐 D3 优先消费 `confirmed/engageable` 航迹。

### D2 -> D5

D5 使用 `global_track_id` 将中心航迹投影到终端相机平面。D5 可以回传终端关联置信度和身份冲突事件，但不得自行改写 D2 的规范 `global_track_id`。

### D2 -> D6

D6 消费 `AssociationLogEntry`、`TrackTransition`、`MetricsRecorder.summary()` 和混淆矩阵，用于批量实验统计、失败案例定位和算法对比。

## 15. 局限与后续工作

当前实现的主要局限：

- 状态空间为二维常速度，尚未直接承载 D1 的完整三维 NED `GlobalTrack`。
- JPDA 是小规模可执行研究实现，不是完整生产级 JPDA 滤波器。
- MHT 是有界接口和对照基线，缺少完整 N-scan、分簇和高级剪枝。
- 特征代价为简单欧氏差异，尚未区分类别置信、外观 embedding、声纹等来源。
- OOSM 和异步传感器回溯主要由 D1 处理，D2 当前假设输入帧已按时间整理。

建议后续工作：

- 增加三维状态和 D1 `GlobalTrack` 原生适配器。
- 引入 IMM-EKF/UKF 预测器并比较机动场景 IDSW。
- 增加 JPDA/MHT 与 Stone Soup 的离线基准对照。
- 把 D5 的终端关联反馈作为低权重身份证据接入，但保持 D2 对 `global_track_id` 的唯一管理权。
- 将 `ambiguity_score`、候选数、协方差重叠率作为自动切换 JPDA/MHT 的触发器。
- 增加 `AssociationRiskSummary` 的离线生成器，把 D2 风险信号以低频摘要形式交给 D3/D4/D6。
