# D6 M 对 N 协同拦截评估框架审查

**日期**：2026-07-11

**范围**：基于 D1-D5、D7 六份 `M_TO_N` 专项报告，定义 D6 离线评估口径；不修改控制、分配、关联、导引或 AirSim 运行逻辑。

**状态**：D6 日志合同、离线聚合、兼容 duplicate 判定和报告接线已实现；真实上游 M 对 N 写盘与 12 组合实验仍为 P1。当前一对一/N-pair 场景无新增 P0。D6 只消费落盘事件，truth 只用于离线评分。

## 0. 2026-07-11 实现回填

- 新增 `TargetDemandRecord`、`CoalitionRecord`、`ArrivalRecord`，并扩展 `AssignmentRecord/TerminalRecord` 的 D3 对齐字段。
- `EpisodeMetrics`、JSONL loader/writer、episode CSV、batch summary 和 Markdown 已接入本报告第 4 节指标；每项在 `m_to_n_metric_availability` 保存 status、reason、numerator 和 denominator。
- `duplicate_terminal_lock_count` 保留通用同帧多资源锁计数；`authorized_cooperative_lock_count`、`erroneous_duplicate_lock_count` 与 `same_resource_lock_continuity_count` 分开报告，错误锁只含 `k=1`、版本冲突或超需求。
- 探测 POD/miss/FAR 同时要求 truth opportunity 与离线 match/miss 配对裁决；仅有 truth 列表且全部 track truthless 时为 `None/unavailable`，truthless center track 不自动计 false alarm。
- 五类 `center_replan_*` 事件已接入 request/deduplicated/no-change/applied/expired、pending dwell 和 convergence time，并保留 request/target/coalition/risk/resolved-plan 审计字段。
- 测试覆盖 3 个合法 cooperative lock、第四个非法、版本冲突、same-resource continuity、replan complete/expired/unavailable、shortfall、hybrid reserve 等待、simultaneous/sequential、缺证据三态、legacy 和 JSONL/report round-trip。
- 尚未完成的是 D3/main/runtime 真实日志生产、M 对 N AirSim episode 和四路线 x 三中心层级多 seed 实验；这些不属于 D6 owned paths。

## 1. 结论

1. M 对 N 评估必须把“一个目标需要多个资源”与“同一目标被错误复制”分开。合法联盟多分配、多观测和多锁定不能沿用一对一 `duplicate_assignment_count` 或 `duplicate_terminal_lock_count` 的充分判据。
2. 评估单位从单 pair 扩展为 `episode -> target -> coalition/wave -> member/link/frame`。所有比例同时输出 numerator、denominator、aggregation level、evidence availability；缺证据为 `unavailable/null`，证据存在且计数为零才是 `0`。
3. 现有 D6 的实际规模、显式 `id_switch_count`、RMSE/continuity、版本/迟滞、D4 lifecycle、D5 terminal/multi-view、通信、D7 intercept/safety、多 seed 配对与报告能力均可复用。新增项是 P1 合同和离线聚合，不要求立即引入外部库。
4. 实验采用四路线：`independent`、`simultaneous`、`sequential`、`hybrid_primary_reserve`；每条路线覆盖中心正常、二级接管、完全无中心三个层级，并在几何、同步、通信和成员失效四类扰动下比较。
5. 当前场景没有新增 P0。若未来正式启用 `required_resource_count > 1`，在报告成功前必须至少具备 target demand、coalition/version/member role、planned cooperative lock 和 arrival/wave 证据；缺这些证据时 M 对 N 指标应 unavailable，不能按一对一指标猜测。

## 2. 统一输入事件与键

所有事件至少包含：

```text
episode_id, timestamp, event_type, source_node_id,
global_track_id, plan_id, plan_version,
coalition_id, coalition_version, coalition_epoch,
resource_id, member_role, wave_id,
measurement_timestamp, arrival_timestamp,
evidence_available, metadata
```

规范键和责任边界：

- `global_track_id` 由中心或当前合法 owner 维护；D6 不创建、合并或重绑定。
- local track 键必须为 `(source_node_id, local_track_id, local_epoch)`，不能仅比较 local ID 数值。
- 联盟快照键为 `(episode_id, global_track_id, coalition_id, coalition_version, coalition_epoch)`。
- 计划快照键为 `(episode_id, plan_id, plan_version)`；旧版本 reject 单独计数。
- 波次键为 `(coalition_id, coalition_version, wave_id)`；成员角色至少为 `primary | reserve | observer | retry`。
- 消息唯一键为 `message_uuid` 或 `(source_node_id, sequence_id, source_epoch)`，并保留 `parent_fusion_ids/source_lineage`。

建议上游落盘事件如下：

| 事件族 | 最小事件/字段 | D6 用途 |
| --- | --- | --- |
| 目标需求 | `target_demand_declared/updated`：`required_count`、能力需求、有效窗口 | demand 分母与 unmet slots |
| 联盟生命周期 | `coalition_proposed/forming/committed/reconfigured/released/failed`、成员集合、ACK bitmap、digest | formation/reconfiguration、digest conflict |
| 分配与版本 | `member_assigned/revoked`、role、plan/version、stale reject | 合法多分配、成员变化、stale rejection |
| 到达与波次 | `arrival_window_assigned`、`member_arrived`、`wave_started/completed/cancelled` | dispersion、common-window、interval/order |
| 主备切换 | `reserve_held/activated/released`、触发原因、新版本 | hybrid primary/reserve |
| 定位 | 估计/真值、`P`、创新 `nu`、`S`、observer lineage、几何质量、reject reason | RMSE/NIS/NEES/一致性/几何拒绝 |
| 跨节点航迹 | local-to-global binding、canonical registry snapshot、fusion lineage、duplicate reject | canonical duplication、cross-node IDSW、公共信息去重 |
| 末端锁定 | local track、resource、decision、coalition/plan/version、slot、authorization | planned cooperative lock 与错误 duplicate lock |
| 失效与冲突 | `member_lost/replaced`、`coalition_digest_conflict`、lease/epoch/version reject | 成员失效和一致性 |
| 通信与安全 | sent/received bytes、round、latency、member pose/range、risk/violation | 消息预算、时延、最小间距、碰撞风险 |

## 3. 聚合层级与 unavailable/zero

### 3.1 聚合层级

| 层级 | 主键 | 适合指标 |
| --- | --- | --- |
| frame/update | timestamp + target/member/link | NIS、NEES、几何拒绝、瞬时 separation/risk、消息 latency |
| member | coalition + resource | 到达误差、锁定、失联、角色切换 |
| wave | coalition + wave | 波次间隔、顺序、完成率 |
| coalition-version | coalition + version/epoch | formation/reconfiguration、digest、消息/字节/轮次 |
| target-episode | episode + global target | demand satisfaction、unmet slots、canonical duplication |
| episode | episode_id | 成功、安全、总开销、三中心层级对比 |
| batch | scenario/version/route/center/fault/seed/actual scale | 均值、分位数、paired effect、bootstrap CI |

batch 分组必须保留实际 `drone_count/resource_count/target_count/camera_count`，不得从 `2v2/5v5` 名称推断。宏平均先对 target/coalition 等权，微平均按机会数加权；两者都报告，不能只给一个总体比例。

### 3.2 unavailable 与零

- `unavailable/null`：需求事件、时间戳、真值、协方差、消息字节或成员位置等必要证据缺失；该样本不进入分母。
- `0`：证据链完整且事件计数确实为零，例如 0 个 unmet slot、0 次 stale reject、0 次碰撞风险越阈。
- `not_applicable`：策略本身不含该概念，例如 `independent` 路线没有 reserve activation rate；不得写成 0。
- 每项输出 `value/numerator/denominator/availability_reason/evidence_path`。分母为 0 时比例 unavailable，而不是 0 或 1。

## 4. 指标定义

### 4.1 目标需求、联盟形成与重构

对目标 `j` 在评估快照 `s` 的需求 `k_js` 和有效已分配成员数 `a_js`：

```text
satisfied_slots_js = min(a_js, k_js)
unmet_slots_js = max(k_js - a_js, 0)
target_demand_satisfaction_rate_micro
  = sum_js satisfied_slots_js / sum_js k_js
target_demand_satisfaction_rate_macro
  = mean_js I[a_js >= k_js]
```

`a_js` 只计 active、授权、current plan/version、未过 lease 且能力/角色满足的成员。`over_support=max(a_js-k_js,0)` 单列，不抵消其他目标 unmet slots。没有 `target_demand_declared` 时以上指标 unavailable。

```text
coalition_formation_time
  = t(first committed with demand/capability/ACK satisfied)
    - t(demand declared or formation requested)

coalition_reconfiguration_time
  = t(first new committed version after trigger)
    - t(member loss/digest conflict/stale-plan trigger)
```

超时但证据完整的样本按预先声明 censor/timeout 规则报告，不把 timeout 当作 0。另报 formation success、reconfiguration success、shrink/replacement/reform count 和 target-uncovered duration。

### 4.2 同时到达、波次与混合主备

对同一 simultaneous primary group 的实际到达时刻集合 `A_j={t_ij}`：

```text
simultaneous_arrival_dispersion_s = max(A_j) - min(A_j)
arrival_time_std_s = sample_std(A_j)
common_window_success
  = I[all required primary members arrived in assigned common window
      and dispersion <= allowed_dispersion]
```

成员缺失时 `common_window_success=0` 仅限需求、窗口和 episode 完成状态均有证据；未落盘到达事件则 unavailable。

对有序波次：

```text
wave_interval_w = t_start(w+1) - t_complete(w)
wave_interval_error_w = wave_interval_w - assigned_gap_w
wave_order_violation
  = I[t_start(w+1) < t_release_or_complete(w)]
```

同时报告早启、迟启、wave completion、cancel、immutable-prefix rollback 和 stale-wave execution。序贯路线没有公共到达窗口时为 not_applicable。

混合主备至少报告：

```text
primary_demand_satisfaction_rate
reserve_hold_integrity_rate
reserve_activation_rate
reserve_activation_latency
unnecessary_reserve_activation_count
reserve_release_latency
```

reserve 永久等待不能计入 demand satisfied；只有计划明确把 observer/reserve 计入任务需求且满足对应时间槽时才可计入。

### 4.3 协同定位精度与一致性

位置维度为 `d_p`，状态维度为 `d_x`：

```text
position_RMSE = sqrt((1/N) * sum_n ||p_hat_n - p_truth_n||^2)
NEES_n = (x_hat_n - x_truth_n)^T P_n^-1 (x_hat_n - x_truth_n)
NIS_n  = nu_n^T S_n^-1 nu_n
```

报告 RMSE 的单机、最佳双机、全部合法成员对照；NEES/NIS 报均值、分位数、超出 `chi-square(alpha, dof)` 上下界比例和 `consistency_pass_rate`。缺 truth 时 NEES unavailable，但 NIS 可在创新与 `S` 完整时计算；缺 `P/S` 时不能用 RMSE 代替一致性。

几何评估输出 observer count、LOS 最小/最大交会角、baseline/range、联合信息矩阵 rank/condition number、重投影残差、PDOP 或等价 covariance quality。定义：

```text
geometry_rejection_rate
  = rejected_updates_due_to_geometry / geometry_evaluated_updates
```

拒绝原因至少拆分 `rank_deficient | near_parallel_los | short_baseline | condition_number | reprojection | pose_covariance | time_skew`。退化几何下增大 covariance 或拒绝是正确行为，不应单独视为失败；应结合 RMSE/NEES 和下游 readiness 解释。

### 4.4 规范身份、公共信息与末端锁定

```text
canonical_duplicate_count
  = sum_truth_or_adjudicated_target max(number_of_active_canonical_ids - 1, 0)

cross_node_id_switch_count
  = count of canonical global_track_id changes for one physical target
    after namespace-aware local-to-global registration

common_information_duplicate_rejection_rate
  = rejected_duplicate_payloads / known_duplicate_payload_opportunities
```

canonical duplication 需要离线 truth 或人工裁决；没有裁决证据时 unavailable。cross-node IDSW 与现有 D2/D6 `id_switch_count` 都必须显式保留，并按 source node、center level 和 target 报告。公共信息机会由 message UUID、source lineage、source epoch 或 parent fusion ID 建立；没有 lineage 时不能宣称 rejection rate 为 1。

末端锁定集合记为 `L_obs`，计划授权集合记为 `L_auth`：

```text
planned_cooperative_lock_count = |L_obs intersect L_auth|
authorized_cooperative_lock_count
  = authorized resource locks in same-frame multi-resource snapshots within k
erroneous_duplicate_lock_count
  = legacy k=1 overflow
    + current coalition/assignment version conflict
    + locks beyond required_resource_count
same_resource_lock_continuity_count
  = sum_target,resource max(number_of_distinct_lock_timestamps - 1, 0)
```

另报 `planned_cooperative_lock_success_rate`、`over_support_count`、stale/mismatched plan lock、geometry-inconsistent lock 和 friend-overlap conflict。通用 `duplicate_terminal_lock_count` 只表示同一 timestamp+target 有多个 resource 的锁观测，不表达授权正确性，也不得覆盖 `erroneous_duplicate_lock_count`。

replan 生命周期只消费以下规范事件：`center_replan_request_created`、`center_replan_request_deduplicated`、`center_replan_ack_no_change`、`center_replan_applied`、`center_replan_expired`。请求、去重、no-change、applied、expired 分别计数；`replan_pending_dwell_s` 汇总 resolved/expired 的 `pending_dwell_s`，缺该字段时用 `resolved_at-requested_at`；`replan_convergence_time_s` 仅对 no-change/applied 成功闭合请求取均值。无事件证据时全部为 unavailable。

### 4.5 成员失效、摘要冲突、通信和安全

```text
coalition_member_loss_count
replacement_time = t(replacement committed) - t(member loss detected)
coalition_digest_conflict_count
stale_rejection_count
stale_rejection_rate = rejected_stale_messages / detected_stale_messages
```

按 shrink、replacement、full reform、hold/abort 分支统计结果，并记录失效后需求不满足持续时间。digest conflict 必须比较 member set、role、target binding、plan version、epoch、lease 和 immutable wave prefix，而不只比较 owner。

每次 coalition change 及每 episode 报告：

```text
messages_sent/delivered/dropped
payload_bytes_sent/delivered
consensus_rounds
end_to_end_latency_ms = received_timestamp - sent_timestamp
measurement_age_ms = arrival_timestamp - measurement_timestamp
```

同时给出 per-member、per-coalition-change、per-satisfied-target-slot 归一化开销。消息大小未知时 bytes unavailable，不能由消息数估算。

安全指标：

```text
minimum_member_separation_m = min_t,i!=j ||p_i(t)-p_j(t)||
collision_risk_exposure_s
  = integral I[predicted_or_actual_separation < safety_threshold] dt
collision_risk_event_count
collision_or_constraint_violation_count
```

区分预测风险、实际阈值越界和碰撞；只有离散采样时同时报告 sample period，防止漏掉采样间最小距离。到达同步成功不能覆盖 separation 或 collision failure。

## 5. 四路线 x 三中心层级实验矩阵

每个单元都运行相同 scenario version、实际规模、初始几何和 paired seeds。四类扰动至少各设 baseline 与 stress：几何为良好/近共线或短基线；同步为低 skew/时钟偏差与 arrival jitter；通信为正常/延迟丢包乱序分区；成员失效为无失效/primary 或 coordinator 在形成中与执行中退出。

| 路线 | 中心层级 | 几何变量 | 同步变量 | 通信变量 | 成员失效变量 | 主比较指标 |
| --- | --- | --- | --- | --- | --- | --- |
| independent | 中心正常 | 单/双/三观察者、退化 LOS | 各 pair 独立 | 中心链路延迟/丢包 | 单成员退出 | RMSE、需求满足、IDSW、min separation |
| independent | 二级接管 | 二级 coverage/基线 | 接管时钟偏差 | center-secondary 断链 | owner/成员退出 | takeover、stale reject、需求缺口 |
| independent | 完全无中心 | peer 几何差异 | peer clock skew | mesh 分区/乱序 | peer 退出 | CBBA rounds/bytes、canonical duplicate |
| simultaneous | 中心正常 | 终端扇区/交会角 | common-window jitter | time-to-go 广播延迟 | primary 退出 | dispersion、window success、separation/risk |
| simultaneous | 二级接管 | 区域视角退化 | coordinator clock offset | 接管丢包 | coordinator/primary 退出 | reconfiguration、window miss、digest conflict |
| simultaneous | 完全无中心 | 分布式几何质量 | consensus skew | 间歇通信/分区 | leaderless member loss | rounds/latency、window success、collision risk |
| sequential | 中心正常 | 每波几何变化 | wave gap jitter | feedback latency | 前波成员退出 | interval/order、stale wave、完成率 |
| sequential | 二级接管 | coverage cell 切换 | wave clock offset | feedback drop | reserve/owner 退出 | prefix 保持、重排时间、unmet slots |
| sequential | 完全无中心 | peer 可见性变化 | local wave clocks | mesh partition | wave member loss | order violation、digest、messages/bytes |
| hybrid primary/reserve | 中心正常 | primary 几何+reserve 视角 | primary window/reserve delay | activation feedback latency | primary 退出 | primary satisfaction、activation latency、safety |
| hybrid primary/reserve | 二级接管 | 二级 cue/primary 基线 | takeover 与 reserve slot 偏差 | lease/activation 丢包 | coordinator/primary 退出 | hold integrity、replacement、stale reject |
| hybrid primary/reserve | 完全无中心 | observer/primary 几何 | distributed release epoch | 分区/重复消息 | primary/reserve 退出 | digest conflict、duplicate reject、需求恢复 |

每个组合至少输出 target/coalition 级原始行和 episode/batch 汇总；不能只输出总成功率。严格 simultaneous、sequential、hybrid 是研究路线，不表示当前 D3/D4/D5/D7 已实现相应控制能力。

## 6. 原始指标与算法证据

以下来源均用于定义评估或实验设计，不表示 MSM 已实现论文算法：

| 家族 | 原始/基础来源 | D6 使用方式 |
| --- | --- | --- |
| CLEAR MOT | Bernardin, Stiefelhagen, *Evaluating Multiple Object Tracking Performance: The CLEAR MOT Metrics*, [DOI](https://doi.org/10.1155/2008/246309) | MOTA/MOTP、miss、false positive、ID switch 的标准对照；D6 继续显式输出 IDSW |
| HOTA | Luiten et al., *HOTA: A Higher Order Metric for Evaluating Multi-object Tracking*, [DOI](https://doi.org/10.1007/s11263-020-01375-2), [arXiv](https://arxiv.org/abs/2009.07736) | 检测、关联和定位平衡的帧级外部对照 |
| OSPA | Schuhmacher, Vo, Vo, *A Consistent Metric for Performance Evaluation of Multi-Object Filters*, [DOI](https://doi.org/10.1109/TSP.2008.920469) | 集合定位与基数误差，需固定 order/cutoff |
| GOSPA | Rahmathullah, García-Fernández, Svensson, *Generalized Optimal Sub-Pattern Assignment Metric*, 2017 International Conference on Information Fusion, [DOI](https://doi.org/10.23919/ICIF.2017.8009645), [arXiv](https://arxiv.org/abs/1601.05585) | 分解 localization、missed、false target 代价 |
| NEES/NIS consistency | Lyu et al., 多机器人异步协同定位与 CI，[DOI](https://doi.org/10.3390/app9050903)；D1 专项的 Qian et al.，[DOI](https://doi.org/10.1109/TIM.2024.3382741) | 用卡方区间审计 covariance consistency；NIS 不需 truth，NEES 需离线 truth |
| 航迹融合 ANEES | `jonassagild/Track-to-Track-Fusion`（MIT，D2 专项已核验）及 CI 基础 Julier/Uhlmann，[DOI](https://doi.org/10.1109/ACC.1997.609105) | 对照独立假设、已知相关和 CI 的一致性 |
| MRTA one-to-many | Dutta, Asaithambi, [DOI](https://doi.org/10.1109/ICRA.2019.8793855) | demand satisfaction、联盟完整性和求解时延设计 |
| CBBA | Choi, Brunet, How, [DOI](https://doi.org/10.1109/TRO.2009.2022423) | 完全无中心 rounds/messages/conflict 基线；不把 single-winner 当原子联盟 |
| Coalition/deadline | Guerrero et al., [DOI](https://doi.org/10.1371/journal.pone.0170659) | formation、deadline、成员物理干扰和重构评估 |
| 通信感知 coalition | Maždin, Rinner, [DOI](https://doi.org/10.1109/ACCESS.2021.3061149) | event/time/hybrid 通信的 bytes/messages/一致性与故障矩阵 |
| Cooperative impact time | Zhou, Yang, [DOI](https://doi.org/10.2514/1.G001609)；Yu et al., [DOI](https://doi.org/10.1109/TAES.2023.3243154) | simultaneous arrival dispersion、consensus latency 和 common-window success |
| Collision safety | Jha et al., [DOI](https://doi.org/10.2514/1.G004139)；Li et al., [DOI](https://doi.org/10.1016/j.jfranklin.2021.06.030) | minimum separation、risk exposure、同步与安全联合判定 |

## 7. 开源评估候选

| 项目 | 许可证/状态 | 适用性 | 限制与结论 |
| --- | --- | --- | --- |
| [Stone Soup](https://github.com/dstl/Stone-Soup) | MIT；D1/D2 专项核验为活跃维护，2026-06-24 发布 `v1.9.1` | Track/Detection/GroundTruth、OSPA/SIAP、track-to-track/CI 研究对照 | 需 MSM adapter、版本锁定、时间/坐标/lineage 合同；适合作为 P2 隔离 benchmark，不替换本地主线 |
| [TrackEval](https://github.com/JonathonLuiten/TrackEval) | MIT；公开 evaluator | CLEAR、HOTA、Identity 等标准 MOT 对照 | 需要 frame-level export、IoU/距离门限和遮挡规则；适合 D2/D5 P2 benchmark，不覆盖联盟/通信/安全 |
| [py-motmetrics](https://github.com/cheind/py-motmetrics) | MIT；公开 Python MOT accumulator | CLEAR MOT、ID 指标和逐帧匹配核对 | 需稳定 accumulator 输入；可作为轻量备选，但不提供 HOTA、联盟或 covariance consistency 全链路 |

至少优先选择 TrackEval 或 py-motmetrics 之一，再与 Stone Soup/OSPA 做互补对照。三者都不得进入在线总线或成为 D6 默认测试硬依赖。

## 8. D6 可复用能力、P1 与 P2/P3

### 8.1 已有可复用能力

- `EpisodeMetrics` 与 track/assignment/target-demand/coalition/arrival/event/link/terminal 记录模型。
- 实际规模归一化、`metric_scope/seed/scenario_group/scale` 分组和 unavailable/zero 基础语义。
- `track_rmse`、continuity、显式 `id_switch_count`，以及 D4 failover/consensus、D5 multi-view/terminal、通信 latency/drop/stale、D7 min range/intercept/safety 指标。
- main execution/contract 双口径、evidence path、场景库、多 seed 严格配对、effect size/bootstrap CI 和 CSV/Markdown/PNG 报告。
- D6 offline-only 与 truth isolation 边界。

### 8.2 P1 实现状态

1. 已实现 M 对 N DTO、assignment/terminal 扩展和 JSONL loader/writer。
2. 已实现 target/coalition/wave/member 聚合器和 unavailable/not-applicable/zero 三态。
3. 已实现合法 coalition multiplicity 判定，以及 canonical duplicate、cross-node IDSW、common-information duplicate rejection、planned/authorized/erroneous lock、same-resource continuity 和 center replan lifecycle。
4. 已接入 episode CSV、batch summary、Markdown 和 actual-scale 分组。
5. 待完成项是上游真实日志、四路线 x 三中心层级 x 四类扰动的多 seed 实验，以及基于真实 evidence 的 paired 报告。

当前场景无新增 P0。D6 本地合同与聚合已完成；缺日志时只标 unavailable，不阻断现有 `k_j=1` 回归。

### 8.3 保留 P2/P3

- P2 保持：frame-level export、TrackEval/py-motmetrics、Stone Soup、OSPA/GOSPA、HOTA/IDF1、bootstrap/非参数 CI 和必要时的 AirSim recording parser。
- P3 保持：仅在已有真实 schema/样例且 AirSim 无法回答实验问题时评估 SCRIMMAGE bridge。
- 禁止项保持：D6 不接 live AirSim 控制，不把评估 truth 或后验标签回写在线链路。

## 9. 验收口径

- 每项指标能追溯到输入事件、公式、聚合层级、分母和 evidence path。
- 合法 `k_j>1` assignment/lock 不产生异常 duplicate；计划外、stale、local-to-multiple-global 冲突仍被计数。
- 几何退化时 covariance 增大或更新被拒绝；RMSE 与 NEES/NIS 共同解释。
- simultaneous 同时满足 common window 和 minimum separation 才算完整成功；sequential 保持 wave order；hybrid 不把未激活 reserve 冒充需求满足。
- 三个中心层级均报告 demand、formation/reconfiguration、digest/stale、messages/bytes/rounds/latency。
- 缺失证据保持 unavailable，真实零保持 0；not-applicable 不进入分母。
- 当前任务已实现并运行 D6 离线单元测试；未运行 AirSim，也未修改上游控制或日志生产代码。
