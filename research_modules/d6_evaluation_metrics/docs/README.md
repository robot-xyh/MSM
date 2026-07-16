# D6 文档索引

2026-07-15 已同步 legacy 1.0 provenance 兼容与真实三档报告。fallback 只在路径输入且 suite/cases/
rows 全无显式 ClockSpeed 时读取 20/20 sibling generated settings；不猜目录名、不默认 1.0，缺文件/
缺键/冲突/非法值 fail closed。真实 1.0/0.2/0.1 共 60 case、20 个跨档配对，合同 56 match/4
mismatch，truth identity/state 全 0；candidate 0.1/0.2 的受影响 aggregate unavailable。输出见
`../../airsim_runtime/outputs/m5n2_clock_speed_comparison_20260715/`。ClockSpeed 专项 `18 passed`、D6
全量 `272 passed`，源组合 hash 前后不变。

2026-07-15 已同步 0.1 P1 NameError 紧急回归：timing mode helper 前置并统一命名；新增 20-case 双层
case-aware evaluator 测试。真实 0.1 两层各 4036 records/20 case 的 P1 v6 只读报告生成成功，输入
hash 不变。timing 专项 `28 passed`、D6 全量 `264 passed`。该段记录紧急修复当时状态；真实三档
comparator 随后已完成，见顶部同步项。

2026-07-15 已同步 case-aware merged suite timing 与真实 ClockSpeed=0.2 证据。P1 v6 显式区分
`single_episode/case_aware_suite`，后者只接受四个 case metadata、逐 case 单调并允许边界重置；两层
各 6567 records/20 case 的只读复测通过，禁止跨 case 伪连续和 main/control 相加。ClockSpeed
comparator v2 冻结 M5N2 每 case `3/2/1`，真实 0.2 审计为 18 match/2 mismatch（candidate seed006/
seed009）；reserve 成功不计 active-primary。该 0.2 阶段专项 `27/10 passed`、当时全量
`263 passed`。真实 0.1 P1 状态见顶部，不预写三档结论。

2026-07-15 已同步 M5N2 ClockSpeed=`1.0/0.2/0.1` 三档离线比较接口。每档强制
baseline/candidate 各 seed 1-10，并按 `case_id/profile/seed` 跨档配对；ClockSpeed 来自 suite/case
persisted provenance，不从目录名推断。报告覆盖三层物理结果、第二 primary、最终锁/共识、
collision stop、独立 wall timing、归一化 simulated time/tick 和 truth identity/state availability。
确定性 fixture 为三档各 20 case、总计 60 case，专项 `8 passed`、D6 全量 `254 passed`。
运行前接口记录已由本页顶部更新：真实 0.2/0.1 均已完成 P1 复核；算法见 `ALGORITHM_AND_IMPLEMENTATION.md`，
接线见 `../AIRSIM_INTEGRATION_PLAN.md`，测试证据见 `../EXPERIMENT_REPORT.md` 1.7 节。

2026-07-15 已同步真实 AirSim M5N2 20-case 复核。baseline/candidate 各 10 seed；actual execution
为 `20/20` available，正式物理 pair/target/coalition=`12/60`、`12/40`、`0/20`，在线 truth
identity/state 均为 0。第二 primary 七阶段分母全部 available，但 5 m physical=`0/20`。两层
timing 各 3805 samples，main-bus/control-tick mean=`349.34/1069.45 ms`，禁止相加。partial
acceptance 的正式 timing 接线仍 unavailable。M5N2 完成后、`TERM` 生效前额外完成的 `png_ttc`
seed001 明确排除在 20-case 聚合与验收之外；其余 tuned 2v2 和全部 dropout 未执行，缺失 case 不补零。
`12/40` 固定表示“至少一个 participating pair 成功”的 canonical target physical success；全部
required member 通过阶段只称 cooperative target-stage diagnostic。第二 primary `20/20` 最终为
`collision_stop`，但 collision object 未写盘，原因对象保持 unavailable。
详细结果见 `../EXPERIMENT_REPORT.md`，接线缺口见 `../AIRSIM_INTEGRATION_PLAN.md`，算法和证据边界
见 `ALGORITHM_AND_IMPLEMENTATION.md` 与 `MODULE_PRINCIPLES_CN.md`。

2026-07-15 已同步 `d6-cooperative-closure-v3`：第二 primary 七阶段漏斗、pair/target/coalition 独立
物理分母、coalition completion 和首失败原因 availability 已写入模块原理、算法、AirSim 计划与
实验报告。确定性专项 `11 passed`、D6 全量 `246 passed`；该代码批次未启动 AirSim，后续 M5N2
20-case 结果以本页首段和实验报告 1.6 节为准。

2026-07-15 已同步两层分阶段延迟能力：模块原理说明嵌套域与 availability，算法文档说明严格
校验、P95、预算和 dominant stage；模块根目录 AirSim 计划与实验报告记录接入和测试证据。代码
可观测性已闭合；M5N2 20-case 已确认预算不达标，正式 case-aware 接线已关闭，优化复验仍为 P1。

2026-07-14 actual target-state freshness/stale 正式指标链已关闭：canonical v2 强制消费最终
command 的六个 freshness 字段，formal validator 从 SHA256 已验证 CSV 复算，case/pooled
aggregate/CSV/JSON/中文 Markdown 均已接入。最新真实 2v2/M5N2 为 48/608 samples，stale 均 0，
source 均为 `d2_estimated_global_track`；pooled 656 samples。D6 全量 `216 passed`。详细算法见
`ALGORITHM_AND_IMPLEMENTATION.md`，AirSim 生产约束见 `../AIRSIM_INTEGRATION_PLAN.md`，真实数值见
`../EXPERIMENT_REPORT.md`。随后 20-case 已补齐 10389 条同配置 freshness 样本；跨提交趋势和
failure taxonomy 仍为 P1。

2026-07-14 最新真实证据状态：tuned 2v2 seed-1 与 M5N2 seed-1 的 canonical
`d7-actual-execution-metrics-v2` 均可用，required/available/unavailable=`2/2/0`；旧
physical-count conflict 未复现并关闭。M5N2 pair/target/coalition=`2/3`、`2/2`、available
`0/1`，显式 coalition 失败不能由 target 成功替代。统一报告 overall=false 是因为 2 个 seed-1
case 不构成 baseline/candidate、1-5 帧 dropout 和 multi-seed 的完整 P1 矩阵。2v2/M5N2 loop
latency=`123.3/384.6 ms`，budget violations=`19/212`、合计 `231`，保持 P1。此次只同步文档，
未改 D6 代码。

2026-07-14 actual SimpleFlight execution evidence 已形成 v2 builder/writer、计划身份 provenance
和 fail-closed validator；plan/version 逐行必填，owner 只对 effective-authorized 的
secondary/distributed active/execution/reassignment 或显式 execute action 行必填。中心授权或
未授权 pending 可无 owner；整集没有 authoritative owner 时 provenance 为 `unavailable`。merge
v3 只发布 validated actual metadata，不从 replay 推断。接口见
模块 `README.md`，证据分层原理见 `MODULE_PRINCIPLES_CN.md`，字段来源和实现见
`ALGORITHM_AND_IMPLEMENTATION.md`，AirSim 生产顺序见根目录 `AIRSIM_INTEGRATION_PLAN.md`，最新
两组 M5N2 审计见根目录 `EXPERIMENT_REPORT.md`。此前 owner-provenance 专项为
execution-evidence focused `20 passed`、当时 D6 全量 `184 passed`；该代码级阶段没有运行真实
AirSim，随后完成的两条真实 seed-1 证据以本页首段为准。
代码级 P0 与本批 actual seed-1 写盘注册门均已关闭；完整 P1 矩阵和性能门仍开放。

本目录保存 D6 的详细设计和实现状态文档。D6 的长期边界是离线评估：只消费日志，不参与 D1-D7 控制链路。

2026-07-15 D2 准入 schema 兼容与正式证据均已同步：统一 system-evidence v2 支持 D2 v2 gates、
legacy structured/bool checks，并结构化保留 source promotion/path、逐 difficulty、truth alignment
和 JPDA research-only 状态。正式 D2-only bundle 位于
`../outputs/p1_identity_ceiling_aware_v2_20260715/`；其他六源 unavailable、全系统判决未评估。
实验文档记录专项 `31 passed`、D6 全量 `243 passed`；本批未启动 AirSim。

先前 case-wiring 状态（2026-07-14）：terminal suite `d6-p1-unified-acceptance-v2`、
`d6-terminal-metric-envelope-v1` 和逐 case evidence aggregation 已实现并通过 D6 全量
`159 passed`。现有 seed-1 suite 的 D3 为 4/4 case、543 records；D7 原 main row 路径仍全部
未注册并明确 fail-closed。公开 registration helper、逐 case/seed JSON/CSV/Markdown 和缺文件/
schema mismatch 回归已同步到下列文档；main runtime 的 D7 路径登记与正式 suite 重生成仍开放。

| 文档 | 位置 | 说明 |
|---|---|---|
| 模块 README | `../README.md` | 当前能力、规模归一化、AirSim/D4/D5/D7 离线入口、测试命令和 API 示例 |
| 模块计划 | `../PLAN.md` | 已实现、部分实现、未实现、main runtime 接线缺口、P1/P2 下一步 |
| AirSim 离线集成计划 | `../AIRSIM_INTEGRATION_PLAN.md` | Blocks JSONL、D4/D5/D7 AirSim 产物回灌、PNG 策略和未实现 replay 项 |
| 算法原理与当前实现 | `ALGORITHM_AND_IMPLEMENTATION.md` | 指标公式、数据模型、`EpisodeMetrics` 字段、D4/D5/D7 gate、开源 benchmark 缺口 |
| 示例实验报告 | `../EXPERIMENT_REPORT.md` | 批量示例报告和图表引用；不是代码或在线控制输出 |

核心规则：

- `id_switch_count` 是 D2/D6 强制显式指标。
- truth-to-track pair 缺失时 `track_rmse/track_continuity/id_switch_count` 为
  `None/unavailable`；完整 identity history 的零切换是 available `0`。JSON/CSV/Markdown、
  loader、merge 和 batch reporting 必须保留该区别。
- 2026-07-14 五场景 truth tracking 回归已关闭假零 P0，D6 全量 `137 passed`；真实
  seed/provenance 完整性和 D2 lifecycle-D3 churn join 仍为 P1。
- 指标按实际 `drone_count/resource_count/target_count/camera_count` 分组和归一化，不从 `2v2/5v5` 场景名推断。
- D7 guidance records 通过 `guidance_records.csv` / `guidance_summaries.json` loader 转为 `EventRecord` metadata；D6 只做离线 gate/intercept 统计，不提供在线导引控制通道。
- 2026-07-07 起，main/orchestrator 已把 D7 真实执行指标合并进正式 `main_episode_bus_metrics.json`，并把执行前合同检查保留为 `main_episode_bus_contract_metrics.json`；D6 仍只消费这些写盘产物。
- 2026-07-08 起，main runtime P1 calibration sweep 已自动调用 D6 `AirSimCalibrationReportGenerator.write_report_bundle()`，输出 AirSim calibration records/summary/Markdown；报告字段覆盖 coverage、projection/gate、stable registration、`not_registered_count`、active degradation review label 和 D7 guidance reject reason。
- PNG 截图不是默认指标输入；bbox、相机参数、timestamp、ID 和 gate metadata 才是指标主线。
- py-motmetrics 已作为隔离式 P2 benchmark 输出 IDF1/MOTA/MOTP，HOTA unavailable；Stone Soup、OSPA/GOSPA、TrackEval、AirSim 原生 recording replay 和 SCRIMMAGE bridge 仍是未实现的可选项，live AirSim replay/API 仍是禁止在线控制项。
