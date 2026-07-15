# D1 Sensor Fusion Offline Experiment Report

## 2026-07-15 真实 AirSim M5N2 权威增量

本节是当前最新系统证据；后文 3-target RMSE 表和 2026-07-14 专项均为独立历史实验，分母和
用途不能混用。

| 项目 | 结果 | 可用性解释 |
| --- | ---: | --- |
| M5N2 case | 20/20 | baseline 10 + candidate 10 |
| Main-bus timing samples | 3,805 | 逐 case 原始 timing 汇总 |
| D1 fusion mean/P95/max | 320.00/451.46/1234.88 ms | main-bus 内层主导阶段 |
| Main-bus mean/P95/max | 349.34/487.40/1305.99 ms | 与 control-tick 外层是嵌套关系，不相加 |
| Online truth identity/state use | 0/0 | truth 仅允许进入离线评分旁路 |
| NIS/NEES/RMSE | unavailable | 本批不是传感器精度与一致性标定实验 |
| Excluded extra case | 1 | `png_ttc_2v2_seed001`，不计入 M5N2 |
| Dropout case | 0 | 未执行，不补零 |

双时间戳、观测/航迹 covariance 和 NED 合同保持为强制基线。结果说明此前 D1-only batch
replay 的等价性与加速并未关闭真实运行时 P1：D1 fusion 仍占 main-bus 绝大部分时间，100 ms
预算未达到。后续优化必须在相同输入下减少重复 fixed-lag 传播、重放和非关键记录开销，同时
保持全部正式观测和不确定性语义。

证据入口：

- `subagent_reviews/MAIN_M5N2_TIMING_AND_SECOND_PRIMARY_REPORT_20260715.md`；
- `research_modules/airsim_runtime/outputs/p1_terminal_timing_funnel_10seed_20260715_m5n2/m5n2_analysis_summary.json`；
- 同目录 `p1_terminal_closure_summary.json`。

## Scope

This report covers offline research simulation only. It does not include real fire-control parameters, damage logic, vehicle control, hardware drivers, automatic action, or bypass of human authorization.

## Scenario

- Targets: 3
- Baseline: this checked-in report is a historical 3-target baseline; integrated runs size D1 inputs from main `--drone-count N`.
- Duration: 8.0 s
- Base step: 0.50 s
- Seed: 7
- Sensors: delayed range-dependent radar, acoustic bearing with voiceprint hints, EO pixel-box projection.
- Filter: NumPy EKF fallback with fixed-lag measurement-time replay.

## Metrics

| Metric | Value |
|---|---:|
| Compensated RMSE (m) | 2.200 |
| Uncompensated RMSE (m) | 7.732 |
| Compensated track continuity | 0.909 |
| Uncompensated track continuity | 0.909 |
| Compensated grading accuracy | 1.000 |
| Uncompensated grading accuracy | 0.981 |
| Observation count | 153 |
| Mean radar latency (s) | 1.284 |

## Figures

- `tracks_xy.png`
- `rmse_latency_ablation.png`

## Interpretation

The compensated run updates each track at `measurement_timestamp` and replays to the current arrival time. The uncompensated run intentionally updates stale measurements at `arrival_timestamp`, which provides the latency-ablation baseline.

## Online identity-boundary regression (2026-07-14)

This contract regression is separate from the historical RMSE experiment above. It used two EO
batches with two observations each. Target, actor, and truth names changed between batches while
measurement, covariance, both timestamps, bbox, and camera geometry remained identical.

Acceptance required exact field equality after `anonymize_online_observations()`, unchanged numeric
and camera geometry, zero nested identity-key/token leakage, fail-closed rejection of an injected
identity token, and preservation of the original evaluator-only truth sidecar. All four focused tests
passed, and the full D1 suite passed `83/83`. No AirSim episode was run for this API-level regression;
main/runtime call-site integration remains outside this D1-owned report.

## 2026-07-14 关联与固定滞后专项回归

历史 AirSim M5N2 seed-001 记录用于只读根因审计：31.3 秒严格关联失败后产生重复雷达 birth，
31.8 秒固定滞后回放从过旧锚点传播后出现状态跳变。修复内容包括同扫描唯一更新、唯一雷达
重捕、模糊 birth 抑制、非测距修正审计，以及对齐已接受量测时刻的后验检查点和旧 OOSM
archive 回放。

专项测试 `5/5`、D1 全量 `87/87`；main 另行验证 AirSim runtime 全量 `134/134`。这些结果
证明代码和接口回归通过，不代表修复后真实 AirSim 场景已经完成。相同 seed 的第三航迹消除和
31.8 秒连续性仍待 main 复跑确认。

## 2026-07-14 Covariance 合同回归

该回归是 API/合同验证，不是新的 AirSim 或传感器精度实验。构造样本无随机 seed，覆盖 radar
covariance 缺失、非有限、非对称、非半正定和错误维度，以及一条无 covariance 的 legacy
record 显式 offline migration。接受阈值为非法输入在任何滤波状态修改前 `100%` 拒绝，迁移
provenance 完整且 JSON-safe，迁移对象在线入口 `100%` 拒绝，合法 governed replay、OOSM 和
七条 AirSim freeze fixture 行为不回归。

D1 全量结果为 `92/92 passed`，满足上述阈值。本轮未启动真实 AirSim，样本 seed 不适用，也
未产生新的 RMSE/NIS/NEES 数值。offline migration 使用的 model default 仅用于历史 evaluator
兼容；真实 radar/acoustic/EO/lidar covariance、故障/遮挡 scale 与长期 consistency 仍待多
seed 真实数据标定。

## 2026-07-14 同帧批量 fixed-lag 性能与等价性报告

### 目的与方法

本次不启动 AirSim，而是使用两类输入验证 D1-owned 优化：第一类为无随机 seed 的构造性
5 航迹、15 条同帧 radar/lidar/acoustic observation；第二类为已有
`p1_terminal_closure_semantics_v2_seed1_20260714_m5n2_baseline_seed001` 的前 40 帧持久化
`blocks_sensor_observations.jsonl`，共 786 条 observation。两个适配器从相同配置和输入顺序
开始，分别逐条 `process()` 与按 frame `process_batch()`，比较最终航迹、状态、covariance、
时间审计和 `_replay_record` 实际调用次数。

接受条件为：

- 不改变输入 measurement/arrival timestamp、covariance、frame、modality 和 source lineage；
- 最终 track ID 集合一致；state/covariance 最大绝对差不超过 `1e-9`；
- 构造场景 history replay 至少下降 50%；
- duplicate、OOSM 和 fixed-lag 边界专项全部通过。

### 结果

| 场景 | 逐条 history replay | batch history replay | 逐条耗时 | batch 耗时 | 数值差异 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 5 航迹、15 条同帧多模态构造输入 | 95 | 24 | 未作为验收量 | 未作为验收量 | `<=1e-9` |
| M5N2 seed-001 前 40 帧、786 条持久化观测 | 1267 | 351 | 18.05 s | 5.70 s | 0 |

构造场景 replay 减少 74.7%；真实持久化输入 D1-only 加速约 3.17 倍、replay 减少 72.3%。
batch summary 在构造场景记录 61 次 cache hit、19 次 miss、5 次终结 replay，并将 15 次接受
更新的逐次发布收敛为 5 个航迹终结发布。专项 `6 passed`，D1 全量 `98 passed`，格式检查通过。

### 结论与限制

结果证明性能瓶颈确由重复 fixed-lag replay 主导，批处理在不减少证据的前提下可显著降低计算，
并保持当前逐条路径的数值结果。该结论仅针对 D1-only 重放；main 尚未改用接口，完整 AirSim
循环的 RPC、观测生成、日志和 D6 报告耗时未包含。下一步由 main 接线后复测完整 245/248 帧
和多 seed，若仍超 100 ms，应继续按分项 profile 治理，不能通过丢观测或改时间戳达标。
