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

D2 当前默认路线是 `GNN/Hungarian + 二维常速度 Kalman fallback`。当候选门内观测数量升高、目标轨迹交叉或 `identity_continuity` 快速下降时，再启用 JPDA/MHT 做离线对照；IMM/EKF/UKF、Stone Soup 和 FilterPy 仍是未来 optional benchmark 或 adapter 方向，不是当前默认代码路径。D2 输出的 `global_track_id` 是后续 D3 分配、D4 主动降级证据、D5 终端配准和 D6 指标评估的核心键，不能由下游模块改写。D2/D6 必须保留显式 `id_switch_count`。

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
