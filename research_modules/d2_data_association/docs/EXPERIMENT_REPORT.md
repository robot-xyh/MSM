# D2 多目标跟踪与数据关联实验报告

## 0. 2026-07-15 M5N2 20-case 补充结果

| 项目 | 结果 | D2 解释 |
|---|---:|---|
| 场景 | baseline 10 seed + candidate 10 seed | 5 资源、2 actor 目标的 SimpleFlight 运行 |
| 完成 case | 20/20 | M5N2 完成后已停止后续多 seed 批次 |
| D2 association timing availability | 3805/3805 | 全部 main-bus tick 可用 |
| D2 association mean/P95/max | 2.521/3.147/98.942 ms | 常态不是总周期主瓶颈，但存在单次长尾 |
| 在线 truth identity/state use | 0/0 | 在线身份边界通过 |
| 在线 IDSW/continuity | unavailable | 无 truth assignment，禁止补零 |
| 第二 primary 进入 5 m | 0/20 | 物理末端结果，不是 D2 身份指标 |
| 最终停止原因 | 20/20 `collision_stop` | 碰撞对象未写盘，不能归因于 D2 |

本批没有形成 D2 专项 offline truth assignment，因此不能从在线日志宣称“IDSW=0”或
“continuity=1”。此前 strict replay 的离线身份结论属于另一套冻结证据，不能混入本批
20 case 的在线统计。D2 只据此确认：在线没有使用真值身份/状态，阶段时延已有真实多
seed 样本，且默认 GNN/Hungarian 与中心 `global_track_id` 所有权保持不变。

candidate 的第二 primary 和 coalition 没有获得物理收益，但当前失败横跨末端视觉、控制
窗口和碰撞诊断，不能由 D2 单独解释。后续 D2 验收仍需单独冻结 offline truth sidecar，
对 duplicate source、teleport、clutter、dropout 和合法新目标进行身份连续性评分。

停止边界：`TERM` 生效前额外完成一个 `png_ttc_2v2_seed001`，该 case 被排除在上述
M5N2 聚合之外；dropout 完成数为 0。

## 1. 实验边界

本报告仅覆盖离线合成数据上的多目标跟踪、航迹生命周期和数据关联算法评估。模块不包含真实火控参数、毁伤逻辑、实机飞控、硬件驱动、自动处置或绕过人工授权的流程。

## 2. 实验目的

D2 的核心任务是维护稳定的 `global_track_id`。本轮实验比较 GNN/Hungarian、JPDA 和 MHT 接口在交叉、编队、遮挡、漏检和虚警条件下的表现，重点关注：

- `id_switch_count`：同一真值目标被不同全局航迹接续的次数。
- `coverage_continuity`：目标存在时是否被任意航迹覆盖。
- `identity_continuity`：目标存在时是否由同一身份连续覆盖。
- `duplicate_assignment_count`：同一帧重复分配或一对多异常。

## 3. 算法配置

详细算法原理、数学模型、参数调节和跨模块接口见 [ALGORITHM_AND_IMPLEMENTATION.md](ALGORITHM_AND_IMPLEMENTATION.md)。本报告只记录当前离线仿真结果和图表解读。

| 算法 | 作用 | 当前定位 |
|---|---|---|
| GNN/Hungarian | 马氏门限 + 一对一硬关联 | 默认工程基线 |
| JPDA | 多假设边缘概率关联 | 交叉/遮挡时的进阶候选 |
| MHT | 有界假设树接口 | 后续完整 MHT 的占位基线 |

## 4. 场景配置

| 场景 | 说明 |
|---|---|
| `crossing` | 两目标中心交叉 |
| `crossing_dense_5v5` | 确定性 dense/crossing 5v5 baseline fixture，用于同场比较 GNN/JPDA/MHT |
| `formation` | 五目标近距编队 |
| `occlusion` | 三目标短时遮挡 |
| `missed` | 四目标随机漏检 |
| `false_alarms` | 四目标叠加虚警杂波 |

运行命令：

```bash
python3 research_modules/d2_data_association/scripts/run_simulation.py --steps 36 --seed 7
```

## 5. 图表与曲线

### 5.1 ID Switch 与 RMSE 对比

![D2 数据关联 IDSW 与 RMSE 对比曲线](association_idsw_rmse.png)

上半部分为不同场景下的 ID Switch 柱状图，下半部分为 RMSE 曲线。该图用于判断是否需要从 GNN/Hungarian 升级到 JPDA/MHT：如果遮挡或虚警场景中 IDSW 明显升高，应优先检查门限、协方差和局部特征，再评估软关联算法。

## 6. 结果解读

- `crossing` 与 `formation` 场景主要验证门控和一对一约束是否稳定。
- `occlusion` 是主要失败模式，遮挡后重新出现的目标容易产生身份断裂。
- JPDA 在高歧义场景可能减少 ID Switch，但代价是运行时间更高。
- 当前 MHT 为有界研究接口，不应直接宣称优于 JPDA。

## 7. 结论

D2 兼容默认路线是 `GNN/Hungarian + 二维常速度 Kalman fallback`；另有显式选择的六维稀疏规则路径，不自动替换旧 replay。候选门内观测数量升高、目标轨迹交叉或 `identity_continuity` 快速下降时，JPDA/MHT 仍只做离线对照；IMM/EKF/UKF、Stone Soup 和 FilterPy 仍是 optional benchmark。D2 输出的 `global_track_id` 是后续 D3 分配、D4 主动降级证据、D5 终端配准和 D6 指标评估的核心键，不能由下游模块改写。D2/D6 必须保留显式 `id_switch_count`。

## 8. 2026-07-14 Truthless 与 Lifecycle 回归

本批是接口和指标语义回归，不是新的 AirSim 参数实验。验证场景为 8 类拒绝输入、main owner 四布尔状态正例、3 帧与 5 帧无 truth replay、7 帧 birth/lost/rebirth/drop 状态序列；seed 不适用。验收阈值为 owner 状态正例通过、在线身份/offline payload 100% 在状态变更前拒绝、truthless IDSW/continuity/RMSE 100% 输出 `None + unavailable reason`、truth 可用零 IDSW 保持 available `0`、完整模块零失败。

2026-07-14 结果为 `98 passed, 1 warning`；warning 是环境中的 Matplotlib `Axes3D` 多版本导入问题。truth-free lifecycle summary 成功导出 birth/lost/drop/rebirth 计数和 transitions。本结果只关闭 P0 truth policy、owner 状态兼容与伪零边界，不构成 lost/drop/gate 参数收益证据；真实 `T001 -> T005` 生命周期调参仍为 P1。

## 9. 2026-07-14 真实 AirSim `T008` 根因审计与模块回归

修复前样本为 M5N2 baseline seed 1，共 351 帧，真实目标数 2。31.3 秒 D1 首次输出
第三条航迹；该航迹和原第二航迹都位于第二个离线真实目标附近，D2 因一对一硬关联
选择其中一个，并为另一个创建 `T003`。31.8 秒起原 D1 来源发生不符合运动学的状态
跳变，D2 继续产生 `T004...T008`。到 34.4 秒统计为 birth 8、drop 4，34.5 秒 D3 已
对 `T008` 形成分配。这解释了额外计划版本、pair churn 和离线物理配对不可用。

修复后算法测试不使用离线真值：四帧输入包含两条正常来源、一个同门限影子来源和
一个已绑定来源 teleport。验收条件是规范航迹数始终为 2、影子不 birth、teleport
被隔离、新来源可在几何允许时加入既有规范航迹来源集合。专项测试通过，完整回归为
`99 passed, 1 warning`。

离线 truth 只用于事后定位，不进入 D2 在线代价、门限、绑定或建轨逻辑。修复后同
seed 结果见下一节；2026-07-15 的 20-case 后续普通 M5N2 已完成，但显式来源扰动和
该批 offline identity 评分仍开放。

## 10. 2026-07-14 Post-batch M5N2 同 seed 复验

### 10.1 场景和验收

| 项目 | baseline | candidate |
| --- | ---: | ---: |
| AirSim 模式 | Blocks / real AirSim | Blocks / real AirSim |
| 场景 | M5N2 | M5N2 |
| seed | 1 | 1 |
| 帧数 | 142 | 141 |
| 在线活动航迹帧 | 140 | 139 |
| 最大 canonical track 数 | 2 | 2 |
| birth/lost/drop/rebirth | `2/0/0/0` | `2/0/0/0` |
| `T008` | 0 | 0 |

两组在线 track record 都只有 `T001/T002`。baseline 每条 ID 各 140 条记录，candidate
各 139 条；状态依次为一次 tentative、一次 confirmed，之后保持 engageable。来源绑定
全程收敛为 `global_track_001 -> T001`、`global_track_002 -> T002`。

### 10.2 在线与离线指标口径

在线关联不含 truth，故两组 `id_switch_count`、`track_continuity` 都是 `None`，并带
`truth_assignment_unavailable`。这表示不可观测，不表示零。

写盘后的 `offline_truth_labels.jsonl` 分别有 284/282 条记录。现有 D2 governed replay
评分得到两组 IDSW 0、identity continuity 1.0、coverage continuity 1.0、false track 0、
truth isolation violation 0。对 main 实际 track records 直接做 evaluator-only 位置
匈牙利裁决，baseline/candidate 仍均为 IDSW 0，continuity 分别为
0.985915/0.985816；缺失比例恰好对应启动前 2 帧，混淆关系始终一一对应。

### 10.3 结论与限制

同 seed 修复后的 `T008` 航迹膨胀未复发，D2-owned 代码未发现新断点，因此没有调整
GNN/Hungarian、门限或生命周期参数。两组平稳 episode 的 suppression、quarantine、
source conflict 都为 0，只证明来源治理没有误触发；teleport 抑制仍由匿名专项回归
验证。D2 P1 不能据单 seed 关闭。2026-07-15 的后续 20-case 已满足普通运行数量，
但没有显式覆盖重复来源、teleport、dropout、clutter 和合法新目标 birth，也没有输出
该批 D2 offline IDSW/continuity；后续应做专项受治理 replay，而不是继续堆叠同类 seed。

## 11. 2026-07-15 Ceiling-aware 准入回归

### 11.1 问题与算法

旧准入要求候选 continuity 绝对提高 `0.10`。当基线为 `0.9810` 时，理论最大提升仅
`0.0190`，因此该条件不可达。新策略版本
`d2-p1-identity-admission/ceiling-aware-error-reduction-v1` 定义：

- `H=max(0,1-C_b)`：基线到理论上限 1.0 的剩余误差空间；
- `Delta=C_c-C_b`：候选实际提升；
- `Delta_req=min(0.10,0.10H)`：至少消除 10% 基线剩余身份错误；
- `Delta/H`：headroom/error reduction fraction；`H=0` 时要求候选合法且不退化。

IDSW 至少改善 30%、false-track 最多增长 10%、P95 不超过冻结预算、在线 truth
leakage 为 0 等联合门限保持。所有指标必须 available、有限且在合法范围内；基线
IDSW 为 0 时不能构造“改善比例”，因此 fail-closed。报告逐 gate 输出原因，v1
`+0.10` 只作为弃用审计字段。

### 11.2 单元与完整回归

| 项目 | 验收 | 结果 |
| --- | --- | --- |
| `0.981 -> 0.984` | 不再被固定 `+0.10` 机械拒绝 | continuity gate 通过 |
| 理论上限 | `C_b + Delta_req <= 1.0` | `0/0.5/0.981/0.999999/1.0` 边界通过 |
| 完美基线 | 候选不得退化或越界 | `1.0 -> 1.0` 通过，退化/`>1` 拒绝 |
| 缺指标 | IDSW/continuity/false-track/latency/leakage 均 fail-closed | 通过 |
| 联合门限 | 零 IDSW 基线、false-track 超限、超时、truth leakage 拒绝 | 通过 |
| 单项 IDSW | 不得自动产生 promotion review | 通过 |
| 默认路径 | `default_online_path_changed=false` | 通过 |
| D2 完整测试 | 零失败 | `113 passed, 1 warning` |

验证日期为 2026-07-15，测试数据是模块单元 fixture，未启动或重新运行 AirSim。
warning 为本机 Matplotlib `Axes3D` 多版本导入问题，不影响准入逻辑。

### 11.3 历史真实数据重新解释

该节记录的是完整冻结重算前的中间判断，现已被下一节的 2026-07-15 六档 v2 完整
证据取代。默认在线 GNN/Hungarian 始终没有自动改变。

## 12. 2026-07-15 六档冻结真实 Replay v2 完整证据

### 12.1 输入与执行

本批没有启动 AirSim，而是消费 main 已冻结的真实 AirSim replay/truth：screening 为
六档各 10 seeds，共 60 case；confirmation 为六档各 20 seeds，共 120 case；P95
预算 0.1 秒。完整 runner 耗时 `2501.32 s`，退出码 0。输出为：

`outputs/p1_identity_ceiling_aware_v2_20260715/d2_identity_calibration_v2.json`

报告 schema 为 `d2-p1-identity-calibration/v2`，policy 为
`d2-p1-identity-admission/ceiling-aware-error-reduction-v1`。screening 和
confirmation 均 available；阶段内 input digest 唯一；全部在线 truth leakage 为 0。

### 12.2 总体结果

| 指标 | Baseline GNN | Candidate GNN | JPDA research |
| --- | ---: | ---: | ---: |
| 平均 IDSW | 1.358333 | 0.616667 | 74.375000 |
| Identity continuity | 0.981046 | 0.983954 | 0.690999 |
| False track | 0 | 0 | 0 |
| P95 loop latency | 12.917 ms | 15.470 ms | 52.655 ms |
| Online truth leakage | 0 | 0 | 0 |

候选 IDSW 下降 `54.6012%`。continuity 的 headroom 为 `0.018954`，所需提升
`0.001895`，实际提升 `0.002908`，error reduction `15.3448%`。候选的 IDSW、
continuity、false-track、P95 和 truth isolation 五项总体 gate 全部通过。

因此：

- `promotion_recommended=true`；
- `promotion_candidates=[gnn-g5.99-qa1-ld3_7-mw0.5x]`；
- `selected_online_path=baseline_gnn_hungarian`；
- `default_online_path_changed=false`。

该结果是晋级评审建议，不是 runner 自动改默认参数。轻量 JPDA 的 IDSW 和 continuity
gate 失败，不是主线候选。

### 12.3 分档结果与限制

clutter 和 combined 的候选五项 gate 全部通过。nominal、tight_crossing、dropout 和
delayed_noisy 的 baseline IDSW 均为 0，候选也为 0；continuity 保持 1.0、不退化，
但无法证明 IDSW “至少下降 30%”，故 reason 为
`baseline_zero_no_measurable_reduction_evidence`，完整分档 gate fail-closed。

dropout 的 offline truth alignment 为 partial：confirmation 20 个 case 共 440 个
unmatched evaluator sample。未做最近邻补齐，online truth leakage 仍为 0。

完整中文审计和图表见：

- `outputs/p1_identity_ceiling_aware_v2_20260715/D2_P1_IDENTITY_CEILING_AWARE_V2_REPORT_CN.md`；
- `outputs/p1_identity_ceiling_aware_v2_20260715/d2_identity_calibration_v2_comparison.png`。

## 13. 2026-07-16 来源身份治理指标专项

### 13.1 目的与方法

本专项验证 D5 人工视频支线暴露的“tracker success 仍可能伴随本地身份塌缩”能够以
审计计数进入 D2，而不把像素/local ID 变成 D2 观测或规范身份。D2 继续使用现有
GNN/Hungarian、Mahalanobis gate 和 source-lineage governance。

样本包括：连续 namespaced source、同一来源集合跨两个 canonical track 的 binding
conflict、绑定来源统计大跳 quarantine、零 detection 的 upstream rejection、5 类非法
frame metadata，以及缺 metadata 的 legacy 帧。replay 使用 synthetic seed 7/8，
每个 3 帧；本批没有启动 AirSim Blocks，也没有使用 actor/truth ID 或原始像素。

### 13.2 结果

| 指标 | Seed 7 | Seed 8 | 多 seed 均值 |
| --- | ---: | ---: | ---: |
| `source_binding_conflict_count` | 1 | 1 | 1.0 |
| `source_lineage_quarantine_count` | 1 | 1 | 1.0 |
| `upstream_local_identity_rejection_count` | 2 | 4 | 3.0 |

连续同一 source 的冲突/隔离均为 0；legacy 无 metadata 的三项均为 0。零 detection
upstream rejection 只增加审计数，track 数和 birth 数保持 0。负数、布尔、浮点、
字符串和 `None` 均在 tracker 状态变化前被拒绝。

全量 D2 结果为 `123 passed, 1 warning`，验收阈值为零失败、表中计数精确一致、非法
输入零状态副作用。warning 为本机 Matplotlib `Axes3D` 多版本导入，不影响指标。

### 13.3 结论与限制

三项已进入 metrics summary、逐帧/episode risk summary、replay threshold sensitivity
逐 seed 行、多 seed group 以及 dense/long/P1 calibration 聚合；`id_switch_count` 仍显式
保留。本轮没有改变默认关联器、门限、source weight、lifecycle 或 risk classification。

该专项证明的是接口、计数与 fail-closed 行为，不是实际 AirSim 场景的统计性能。至少
10 个真实 duplicate-source/teleport/dropout/clutter/合法新目标 case 的 recall、false
suppression、offline IDSW/continuity 和置信区间仍不可用，继续作为 P1 验收限制。

## 14. 2026-07-20 六维稀疏规模实验

### 14.1 场景与验收

本批是 D2-owned 合成规则测试，不启动 AirSim。状态采用
`[pN,pE,pD,vN,vE,vD]`，目标位于 100 m 间隔三维网格并作匀速运动；位置 covariance
为单位阵，速度提示 covariance 为 `0.25 I`。规模依次为 5、20、50、100、200。

验收条件：

- 第二帧匹配数等于输入目标数，state/covariance 维度为 6/6x6；
- gate 的 innovation dimension 为 3，Down 轴统计不一致会被拒绝；
- 候选图不分配全局 cost/distance matrix，candidate/component 数显式可审计；
- crossing、连续两帧漏检和 15 个匿名虚警不造成离线 ID switch；
- 在线对象无 truth 字段，上游 `global_track_id` 不成为 D2 canonical ID；
- track history 和 frame log 不超过配置上限；完整 D2 测试零失败。

### 14.2 结果

| 目标数 | 候选边 | 潜在全对 | 分量矩阵元素 | 裁剪率 |
| ---: | ---: | ---: | ---: | ---: |
| 5 | 5 | 25 | 5 | 80.0% |
| 20 | 20 | 400 | 20 | 95.0% |
| 50 | 50 | 2,500 | 50 | 98.0% |
| 100 | 100 | 10,000 | 100 | 99.0% |
| 200 | 200 | 40,000 | 200 | 99.5% |

原六维专项 13 个测试通过；增加 3 个速度稳定性专项后，完整命令结果为
`139 passed, 1 warning`，验收阈值零失败。
warning 是环境 Matplotlib `Axes3D` 导入，不影响本批三维数值代码。

200 目标另做 3 个独立 trial，每个 trial 预热 1 帧后连续测量 30 帧。90 个测量帧的
候选边始终为 200，最大单分量矩阵元素为 1；下表为 90 帧聚合值：

| 阶段 | Mean | P50 | P95 | Max |
| --- | ---: | ---: | ---: | ---: |
| 稀疏关联 | 6.683 ms | 6.306 ms | 7.056 ms | 22.471 ms |
| Tracker step | 25.491 ms | 25.016 ms | 26.797 ms | 41.613 ms |

crossing 用例在同位置时形成 4 条候选边，通过门内速度一致性打破平局，离线
`id_switch_count=0`、continuity 1.0；漏检用例 20 目标中 1 个目标连续缺失两帧，重获后
IDSW 0，identity/coverage continuity 均为 0.98；虚警用例 50 个真目标叠加 15 个无标签
虚警，真目标 IDSW 0、continuity 1.0，15 个虚警 assignment 只在离线 evaluator 计数。

### 14.3 证据限制

上述性能只来自当前主机、单进程、一个确定性网格和 3 x 30 个测量帧，尾值包含系统
调度抖动；它不是多 seed 置信区间、实时 SLA、AirSim 或 200v200 全链路结果。KD-tree
避免无条件全对扩张，但极端全重叠目标
仍会形成大连通分量；候选预算、分区与召回率需要联合标定。main-owned scalable
point-mass bus 已有只读运行诊断，但该阶段修复后的跨模块复跑和多 seed 验收尚未完成；
后续第 18 节已实现有界 whole-scan OOSM adapter。六维 JPDA/MHT、OOSM 状态回溯/平滑
和高机动滤波仍未实现。

## 15. 2026-07-20 六维速度状态稳定性实验

### 15.1 问题与实现前证据

main 在不向 D2 暴露 truth/actor/object ID 的只读诊断中运行 50v50、seed 17、2.2 s、
radar-only。D1 与旧 D2 的帧末分布为：

| 指标 | D1 输入 | 旧 D2 输出 |
| --- | ---: | ---: |
| 速度 P50 | 6.28 m/s | 8.89 m/s |
| 速度 P90 | 12.16 m/s | 17.43 m/s |
| 速度 max | 21.03 m/s | 27.49 m/s |
| Pvv trace P50 | 101.24 | 62.95 |
| Pvv trace P90 | 110.31 | 69.37 |
| Pvv trace max | 112.32 | 70.86 |

速度均值放大的同时 covariance 反而收缩，说明不是单纯保守预测。代码审计确认旧 D1
adapter 只传位置和速度 marginal，丢弃完整 6x6 的 position-velocity cross block；旧
tracker 出生时复制一次 D1 速度，后续只把每帧 D1 posterior 当作独立位置量测。CV 预测
生成的 Ppv 令位置 random-walk residual 持续修正速度，Joseph update 又把 Pvv 伪收缩。

修复后，D1 source posterior 携带完整 covariance，并使用固定
`correlated_state_ci_track_weight=0.5` 的 6D covariance intersection。速度创新 NIS
超过三自由度 99% 门限时，以 `NIS/gate` 膨胀速度 covariance；关联速度项在相同门限
封顶。3D 位置马氏门控、稀疏候选、中心 ID 和离线 truth 隔离不变，没有按 4.7 m/s、
场景名或速度模长硬裁剪。

### 15.2 50 条多帧噪声验收

测试使用 seed 17、50 条、12 帧、0.2 s 周期，即时间戳 0.0--2.2 s。在线 Detection3D
只有匿名六维 source posterior、timestamp 和 covariance；离线标签只在每帧关联完成后
进入 `Sparse3DOfflineEvaluator`。验收要求输出速度 P50/P90/max 不高于相应输入分位数
的 `1.05/1.05/1.00` 倍，Pvv trace 中位数不少于输入 trace 的 90%，位置 RMSE 不劣于
输入 posterior，活动航迹 50、IDSW 0、continuity 1.0。

| 指标 | 匿名输入 | 旧 D2 复现 | 修复后 D2 |
| --- | ---: | ---: | ---: |
| 速度 P50 | 5.415 m/s | 9.41 m/s | 5.082 m/s |
| 速度 P90 | 7.960 m/s | 14.31 m/s | 6.401 m/s |
| 速度 max | 12.274 m/s | 21.88 m/s | 7.218 m/s |
| Pvv trace | 102 | 62.76 | 101.181 |
| 最终位置 RMSE | 52.634 m | 未作为旧门限 | 48.364 m |
| 离线 IDSW / continuity | evaluator-only | 0 / 1.0 | 0 / 1.0 |

全部门限通过。该结果证明当前固定输入下 D2 不再把位置 residual 解释成过大的高置信
速度，不表示输出速度已接近某个场景真值或 CI 参数已最优。

### 15.3 交叉和 200 条批量验收

seed 29 双目标交叉运行 21 帧、0.2 s 周期，在交叉帧向一条六维 posterior 注入一次
速度离群值。交叉帧仍有 4 条三维位置门内候选；update velocity NIS gate 和有限速度
tie-break 均触发，最终活动航迹 2、IDSW 0、continuity 1.0。速度离群值没有被当作位置
拒配依据，也没有创建新 canonical ID。

seed 41 的 200 条批量回归运行 10 帧、0.2 s 周期：

| 指标 | 结果 |
| --- | ---: |
| 每更新帧 candidate / dense pair | 200 / 40,000 |
| component matrix pair | 200 |
| 活动航迹 | 200 |
| 输入 / 输出速度 P90 | 8.097 / 5.980 m/s |
| 输入 / 输出 Pvv trace 中位数 | 75 / 69.685 |
| 离线 IDSW / continuity | 0 / 1.0 |

这同时通过速度稳定性、位置/身份连续性和稀疏规模验收，没有按目标数量建立固定 shape。

### 15.4 回归与证据限制

执行命令为：

```bash
PYTHONPATH=research_modules/d2_data_association \
pytest -q research_modules/d2_data_association/tests
```

结果 `139 passed, 1 warning in 27.49s`；warning 是本机 Matplotlib `Axes3D` 多版本导入
提示，不影响六维数值测试。相关 Python 入口 `py_compile` 通过。

固定 CI track weight `0.5` 只是本轮一致性基线，尚无多 seed 最优性证据。当前专项只
检查速度 NIS gate 是否按模型冲突触发，没有形成按距离、covariance、量测频率分组的
六维 NIS coverage；离线标签只用于身份和位置验收，没有形成六维 NEES coverage。
至少 20 个未见 seed 的 CI weight sweep、持续加速度/协调转弯/漏检、不同交叉 covariance
结构以及 main 修复后 50v50/200v200 与 D3 reachability 复跑仍未完成。上述合成数据不是
AirSim、实时 SLA 或端到端物理拦截证据。

## 16. Scalable 3D 离线身份合同回归（2026-07-20）

### 16.1 目的与场景

本批只验证 evaluator 合同，不比较关联参数性能。23 个专项覆盖：稳定 identity、真实
ID switch、一个 truth 对多 track、一个 track 对多 truth、缺 lineage、同帧重复
lineage、跨 track 冲突、显式/未标记 replay、冲突 truth label、标签文件篡改、label/ref
timestamp 不一致、未来/超窗 observation、dropped 后 canonical ID 复用、无 truth、在线
truth 字段泄漏、未知 record sequence、schema 拒绝、artifact round-trip、非六维 source
track、非 D2-owned ID、在线 IDSW 伪零、矛盾 availability，以及 37 目标两帧输入规模。

### 16.2 验收结果

| 验收项 | 结果 |
| --- | --- |
| 稳定 identity | IDSW 0，track/identity/coverage continuity 1.0 |
| 真实换轨 | IDSW 1，identity continuity 0.5 |
| 一个 truth / 两条有效 track | duplicate 1，mapping 均 available |
| 一条 track / 两个 truth | ambiguous，全部 identity values `None` |
| 缺失、冲突、时间/lifecycle 不一致 | unavailable/ambiguous 且带原因，不填 0 |
| 显式 replay generation | 去重审计 1 次，稳定 mapping available |
| truth 文件篡改、在线 actor identity、未知 sequence | evaluator 入口 fail closed |
| 非六维 source、非 D2-owned ID、在线 IDSW 伪零 | evaluator 入口 fail closed |
| public IDSW availability 与值/reason 矛盾 | artifact loader fail closed |
| 动态规模 | 37 目标 x 2 帧共 74 mappings，无 2/5 固定维度 |

专项命令结果为 `23 passed in 0.71s`。完整命令：

```bash
PYTHONPATH=research_modules/d2_data_association \
pytest -q research_modules/d2_data_association/tests
```

结果 `162 passed, 1 warning in 30.63s`；warning 为本机 Matplotlib `Axes3D` 环境问题，
不影响 evaluator。相关 Python 入口 `py_compile` 通过。

### 16.3 证据限制

本批输入是确定性 DTO/文件 fixture，没有启动 AirSim、没有 point-mass episode、没有
正式 seed，也没有修改在线算法。因此它只关闭 schema、hash、lineage mapping、指标
availability 和 main/D6 公共 artifact 的 D2-owned 合同缺口；不能声明 scalable 3D
IDSW 性能、多 seed continuity、门限收益或实时性。main producer 当前会跳过无 lineage
的 D2 track/frame，尚不满足完整 evidence 集合合同；修正后仍需使用独立 sidecar 生成
正式 episode artifact。

## 17. active-risk seed 1005 陈旧观测重放治理（2026-07-22）

### 17.1 现象与根因

专项使用 scalable 3D 质点场景 `active_risk`、seed 1005、5 个目标和 2.2 s 短时回放。
旧路径在 `t=0.247 s` 建立 5 条 tentative 航迹；`t=0.439 s` 时原 GT4 未匹配，D1 的
第 4 条后验触发 GT6。此后 GT4 持续接收新的雷达观测，GT6 却反复携带同一个
`latest_observation_id=radar-s000002-d0003`。GT6 的状态有效时刻随帧更新，但底层量测
谱系没有变化。旧 D2 将每帧包装出的新 detection ID 计为新命中，因而把陈旧后验确认成
第二条全局航迹。

GT4 与 GT6 相距约 1.5--1.6 km。二者不满足合理的统计近距合并条件。本次治理在关联前
使用传感器命名空间与不透明 `latest_observation_id` 组成在线证据键。同一证据只能贡献
一次关联和一次命中；重复证据进入 quarantine，不参与 KD-tree、Hungarian、状态更新或
确认计数。证据键不解析目标序号，也不读取仿真 truth、actor ID 或 object name。

### 17.2 生命周期与重复合并边界

tentative 航迹首次缺少新证据时保留，连续第二次缺少新证据时删除。该规则允许 GT4 在
短时漏配后被新的雷达观测重获，同时使只依靠陈旧后验维持的 GT6 退出。重复航迹合并仅在
共享在线观测谱系或带命名空间的 source-track 谱系、且位置和速度三维马氏门同时通过时
启用；同帧双方都有新证据时禁止合并。survivor 按航迹成熟度、创建时间、命中数、漏失数
和 ID 顺序确定，保留原 `global_track_id`。本 seed 没有触发合并，GT6 通过 tentative
生命周期删除。

### 17.3 结果

| 项目 | 结果 |
| --- | --- |
| 10 个 D2 发布帧的活动航迹数 | `5, 6, 6, 5, 5, 5, 5, 5, 5, 5` |
| 最终活动航迹 | `GT3D-000001` 至 `GT3D-000005` |
| replay quarantine | 9 次 |
| tentative stale drop | 1 次 |
| duplicate coalescence | 0 次 |
| 在线 truth 使用 | 0 次 |
| 专项回归 | 6 个通过 |
| D2 完整回归 | `168 passed, 1 warning in 26.15s` |

warning 是既有 Matplotlib `Axes3D` 环境提示，不影响关联结果。在线
`id_switch_count` 继续显式输出 `None + unavailable`，没有用缺失 truth 伪造零值。

### 17.4 限制

本批关闭的是 seed 1005 暴露出的 D2-owned 陈旧观测重复确认缺口。证据来自一个质点
seed，不是 AirSim、200 对 200 或物理拦截结论。该初版在当时仍按 episode 保存 claim
且不淘汰；该限制已由第 18 节的有界 ledger、离线误抑制基准和整帧 OOSM adapter 后续
关闭。真实 AirSim 与 200v200 多 seed 证据仍开放。

### 17.5 development 20-seed 集成复跑

main 于 2026-07-22 在脏工作树运行 `/tmp/msm_active_risk_d2_fix_20260722/`。场景为
active-risk seeds 1000--1019，共 20 对隔离的 control/treatment 质点 episode，每个
episode 1.0 s。该批用于检查修复后的运行时证据链，不是 clean formal benchmark。

| 验收项 | 结果 |
| --- | --- |
| plan consumption availability | 20/20 |
| guidance lineage availability | 20/20 |
| physical window availability | 20/20 |
| D4 degraded adoption availability | 20/20 |
| paired physical effect availability | 20/20 |
| paired non-degradation availability | 20/20 |
| degraded paired comparison availability | 20/20 |
| D4 adoption | control 94 + treatment 94 = 188/188 |
| 控制命令 | control 1960，treatment 1960，held 0 |
| seed 1005 离线身份 | GT1-GT5 五条 `unique_lineage_verified` |
| 在线 truth / global ID 改写 | 0 / 0 |

总线已持久化 `d2-observation-evidence-governance-v1`，包含 fresh/replay、timestamp
conflict、coalescence、suppressed births 和 tentative stale drop 的逐帧/累计字段。D6
报告的 control/treatment 平均最近距离相同，物理差值为 0；paired non-degradation 为
20/20。counterfactual 和 causal availability 均为 0/20，production runtime ACK 未评估。
因此该批只证明开发期接线、可用性和非退化记录完整，不证明因果收益或生产运行能力。

main 同批回归记录 D2 `168 passed, 1 warning`、scalable `110 passed`，其余 D1、D3-D7
也全部通过。该 development 结果随后由 clean-tree 运行取代，不能单独作为正式来源。

### 17.6 clean-tree 20-seed 复跑

提交 `0fa7c00c3514c4fa87a17953ab66fdfb73489b0b` 的输出 manifest 记录
`repository_dirty=false`、`dirty_source_episode_count=0` 和统一源提交。active-risk
seeds 1000--1019 共 20 个 pair；D4 adoption 188/188，control/treatment 各 1960 条命令，
离线唯一身份映射合计 100，seed 1005 为 GT1-GT5 五条唯一映射。物理窗、D4 adoption、
paired physical effect 和 paired non-degradation 均为 20/20 可用。

两臂在 1 s 计划有效窗内的 5 m 拦截成功均为 0。counterfactual、causal 和 production
runtime ACK 不可用。该批证明提交与输入来源可复现，未证明物理拦截效果或主动降级收益。

## 18. 长 episode 声明和 OOSM 模块测试（2026-07-22）

本轮不启动 AirSim，不运行随机 seed。新增 15 个确定性测试，完整 D2 为
`183 passed, 1 warning in 29.08s`；warning 是既有 Matplotlib `Axes3D` 环境提示。

| 验收项 | 输入 | 结果 |
| --- | --- | --- |
| 小规模长期循环 | 5 目标 x 500 帧，max-count=30 | peak/current <=30，overflow 0，evicted >0 |
| 中规模长期循环 | 40 目标 x 200 帧，max-count=240 | peak/current <=240，overflow 0，evicted >0 |
| 近邻离线基准 | 3 目标，16 帧，0.75 m | 43 条合法检测，误抑制 0，recall 1.0，错误合并 0 |
| 动态 N 离线基准 | 12 目标，16 帧，末目标第 5 帧进入 | 187 条合法检测，误抑制 0，recall 1.0，错误合并 0 |
| 确认延迟 | 3/12 目标基准 | mean/P95 0.25/0.25 s |
| 离线身份 | 3/12 目标基准 | IDSW 0，continuity 1.0，truth 仅 evaluator 可见 |
| OOSM 排序 | 0.0、2.0、1.5、3.0 s 到达序列 | Tracker 释放为 0.0、1.5、2.0、3.0 s |
| OOSM fail closed | 超窗、buffer overflow、早于已释放 state | 逐原因拒绝，状态时间不回退 |

模块测试证明 `O(C_max)` 常驻 claim 上界、旧证据水位线防重放、动态 N 和公开审计合同。
数据没有覆盖真实 AirSim observation ID、传感器时钟偏差、长尾网络迟到、遮挡/杂波、
20/50/100/200 多 seed 或最坏大连通分量。这些仍是 P1 实验项。

## 19. 重复全量后验 coast 模块测试（2026-07-22）

5 个确定性专项验证 D2 自身的 bounded replay 分支。跨帧重复后验在 0.5 s grace 内不
增加 hit、birth 或 miss；0.25 s 配置下，0.30 s replay 恢复 miss 并进入 lost；同一
observation ID 对应冲突量测时间时不 coast。12 目标、200 帧、雷达每 0.5 s 更新的
fixture 产生 1920 次 coast，所有航迹 misses=0，claim 未超过 max-count。

此前 main 尾部逐次调用 D2 时，active-risk seed 1005 曾记录 replay quarantine/coast 9。
该数值只描述旧接线版本。main 现已在 D2 前合并尾部融合后验，当前集成结果见第 20 节。
D2 的 coast 算法和上述模块 fixture 均未修改，真实 AirSim grace 仍待按传感器节拍标定。

## 20. scalable 尾部合并复核（2026-07-22）

### 20.1 seed 1005 当前结果

active-risk 5v5、seed 1005、1.1 s 当前运行发布 2 个 D2 帧：1 个来自常规在线关联，
1 个来自 episode finalize。两帧均为 GT1-GT5 五条航迹，终帧全部 confirmed。main 在
尾部按量测时间逐条融合 D1 扫描，只把最终融合后验送 D2 一次，并禁止该 finalize 路径
生成相机或运动控制命令。

| 项目 | 当前结果 |
| --- | --- |
| D2 发布帧 | 2，航迹数均为 5 |
| birth / claim | 5 / 10 |
| replay quarantine / coast | 0 / 0 |
| tentative stale drop / coalescence | 0 / 0 |
| D2 finalize 调用 | 1 |
| `coalesced_release_count` | 5 |
| 在线 truth 使用 | 0 |

旧报告的 7 帧、claim 26、replay 9 来自 D1 尾部每次释放都调用 D2 的上一版 main。当前
`replay=0` 表示重复尾部后验没有进入 D2，并不表示 D2 删除了 replay quarantine 或 coast。

### 20.2 D2 复现脚本与测试口径

复现报告升级为 `d2.active-risk-seed1005-reproduction.v3`，验收 profile 为
`canonical_five_tracks_with_optional_bounded_replay_v3`。replay=0 与正数 bounded replay
均可接受；正数分支只允许 `repeated_latest_observation_id`，两种分支都要求 coast 与
quarantine 一致。报告还检查全部发布帧为 GT1-GT5、owner 为 `D2_center`、birth 5、最终
confirmed、无 stale drop/错误合并且 online truth 0。

当前 2.2 s 运行得到 6 个五航迹发布帧，birth 5、active track 5、replay
quarantine/coast 0、stale drop 0、coalescence 0、online truth 0，
`acceptance_passed=true`。专项测试 2 个通过，完整 D2 回归为 `189 passed, 1 warning`；
warning 是既有 Matplotlib `Axes3D` 环境提示。本次只调整复现和测试验收合同，没有修改
GNN/Hungarian、claim ledger、coast 或生命周期算法。

### 20.3 干预库存

保留 seeds 1011 和 1019 在 1.0 s 干预时刻各只有 4 条在线航迹。两例首个雷达扫描各漏检
一个目标，第 5 条新鲜观测在干预时刻之后到达，终态恢复为 5 条 confirmed。干预源应冻结
实际在线库存，并把相对场景目标总数的差额记录为覆盖率和初始化延迟；在线 D2 不使用
离线 truth 补轨。

## 21. 200v200 单 seed development 复核（2026-07-22）

持久化的 `point_mass_integrated_observation_smoke_20260722_development_coalesced` 制品采用
200 个目标、200 个资源、seed 42000、2.2 s 质点场景。manifest 标记
`repository_dirty=true`。它验证 main 尾部调用数量和 D2 治理审计，不是正式性能验收。

| 项目 | 结果 |
| --- | --- |
| 常规 D2 关联 | 8 次，共 6.135 s |
| 尾部 D2 关联 | 1 次，2.033 s |
| 合并的尾部释放 | 30 |
| claim current / peak / capacity | 1583 / 1583 / 60000 |
| overflow / too-old | 0 / 0 |
| duplicate coalescence | 0 |
| online truth use | 0 |

上一份 `development_optimized` 制品在尾部仍调用 D2 31 次，claim current/peak 为
1976/1976。该数值不能与新制品的单次 finalize 和 2.033 s 时延合并报告。当前代码的
独立 `/tmp` 复跑同样得到 `coalesced_release_count=30`、单次 finalize、claim
1583/1583 和 truth use 0；运行时波动使尾部关联为 2.881 s，说明本批时延只能作为
development 主机样本，不能声明实时服务等级。

## 22. 四规模快速治理标定（2026-07-22）

快速 runner 覆盖 20、50、100、200 四个规模，每档 5 个唯一 seed，共 20 个 episode。
报告明确 `formal_episode_count=0`，全部属于 development。truth 仅在 online step 后由
evaluator sidecar 使用，在线 truth use 合计为 0。

| 规模 | seed 数 | claim peak | capacity | safe evicted | overflow / too-old |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 20 | 5 | 2390 | 4800 | 285 | 0 / 0 |
| 50 | 5 | 6020 | 12000 | 735 | 0 / 0 |
| 100 | 5 | 12070 | 24000 | 1485 | 0 / 0 |
| 200 | 5 | 24170 | 48000 | 2985 | 0 / 0 |

四档 near-neighbor recall 均为 1.0，false suppression rate 和 erroneous coalescence
rate 均为 0，confirmation latency mean/P95 均为 0.25/0.25 s。这些指标来自专用治理
benchmark，输入结构和难度受控。它不包含完整的 D1-D7 运动、分配、降级、视觉和制导
闭环，也不是 AirSim 或完整 200v200 多 seed 验收。正式结论仍需 clean commit、至少
20 个未见 seed、代表性漏检/遮挡/杂波/OOSM 分布和隔离离线身份评分。
