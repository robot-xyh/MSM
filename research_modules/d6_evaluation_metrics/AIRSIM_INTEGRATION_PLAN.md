# D6 AirSim 离线集成计划

## 2026-07-15 legacy 1.0 settings provenance 接入与三档生成

D6 未修改或启动 main runtime。旧 1.0 suite root/summary 本身无 ClockSpeed，因此 comparator 仅在
summary/cases/rows 全无显式值时，按 20 个已注册 `case_id` 定位同批 sibling case 的
`generated_settings/blocks_actor_m5_n2_settings.json`。必须 20/20 文件存在、每份显式包含同一有限
正数 `ClockSpeed`；不读目录名、不默认 1.0，任一缺失/冲突/非法值即拒绝。0.2/0.1 继续直接使用
case result provenance。

真实三档只读报告已生成到
`../airsim_runtime/outputs/m5n2_clock_speed_comparison_20260715/`，60 case/20 对配对完整。机会合同审计
为 56 match/4 mismatch；0.1 candidate seed007/009 与 0.2 candidate seed006/009 的受影响结果保持
unavailable。main bus/control tick 分层且归一化只乘 control tick wall mean；case wall timing 因源
字段缺失为 unavailable。三档 summary 与 20 个 1.0 settings 的组合 hash 前后不变。

## 2026-07-15 ClockSpeed=0.1 P1 紧急接线复测

D6 未修改 runtime。输入模式规范化函数已前置并统一命名，防止
`evaluate_stage_timing_inputs()` 在 case-aware 双层入口引用不存在的私有名称。真实 0.1 summary 和
`d6_stage_timing/main_bus_stage_timings.jsonl`、`control_tick_stage_timings.jsonl` 只读接入成功：两层
各 4036 records、20 case，manifest 一致，输入 hash 不变。报告写入 D6-owned
`outputs/p1_clockspeed_0p1_m5n2_20case_20260715_case_aware_validation/`。该段记录当时的单档复测；
三档 comparator 随后已完成，见本页顶部。

## 2026-07-15 ClockSpeed=0.2 merged suite 接线完成

main 已完成真实 ClockSpeed=0.2 M5N2 20/20 case。D6 不修改 runtime，只读消费 summary 与两层 merged
JSONL；调用时必须显式指定 `case_aware_suite`。该模式只准入 `case_id/family/profile/seed` metadata，
逐 case 校验 frame/timestamp，case 边界允许重置；双层 ordered case manifest 必须相同。main bus 和
control tick 继续分层，禁止跨 case 拼接和跨层相加。

2026-07-15 复测确认两层各 6567 records、20 case，P1 v6 bundle 无异常生成，输入 SHA-256 未改变。
冻结 M5N2 机会合同为每 case `3/2/1`；真实 0.2 中 candidate seed006（D7 unavailable）和 seed009
（D7 available）均因实际 `2/1/1` 标为 contract mismatch。seed006 的 standby reserve 成功只作
排除审计，不计 active-primary success。真实 0.1 P1 已按顶部复测，仍不在本节写三档比较结论。

```bash
python3 research_modules/d6_evaluation_metrics/scripts/run_p1_acceptance_report.py \
  --output-dir <d6_report_dir> \
  --main-summary <clock_0_2_summary.json> \
  --main-stage-timings <merged_main_bus.jsonl> \
  --control-tick-stage-timings <merged_control_tick.jsonl> \
  --stage-timing-input-mode case_aware_suite
```

## 2026-07-15 ClockSpeed 三档 suite 接线

main 分别运行 ClockSpeed=`1.0/0.2/0.1` 后，将三个 M5N2-only suite root 或
`p1_terminal_closure_summary.json` 传给 D6。每档必须只包含 baseline/candidate 各 seed 1-10，case
注册与 result row 的 `case_id/profile/seed/family/resource_count/target_count` 必须一致；三档 case
键集合也必须完全相同。既有 `comparison_role=enhanced` 按 candidate 归一化。D6 不从路径中的
`0.2/0.1` 字样推断 ClockSpeed。唯一 legacy 兼容是本页顶部按注册 case_id 对 20 个 sibling
generated settings 的封闭审计，不做泛化目录搜索。

ClockSpeed 的正式来源是 suite/case provenance；当前 runtime 若只在每个 result row 持久化
`clock_speed`，D6 要求 20/20 行完整且一致，并与已注册
`intercept_summary.parameters.clock_speed` 交叉验证。summary 根部未归档的裸字段不能替代上述
case provenance。缺 case、重复 seed、profile 角色冲突或跨档 case key 不同均直接拒绝该比较。

每 case 继续显式注册 `intercept_summary`、`main_stage_timings` 和
`control_tick_stage_timings`。D6 从前者重算第二 primary 五米结果/距离、required active-primary
最终锁、coalition 最终锁共识与 collision stop；从后两者分别计算 wall timing。control tick 的
`bus_processing` 已嵌套 main bus，两层不得相加。归一化指标定义为 control tick wall mean 乘
ClockSpeed，不使用目录名或跨层总和。缺路径、坏 schema 或字段缺失保持 unavailable。

2026-07-15 仅完成三档各 20 case、总计 60 case 的确定性接口验收：专项 `8 passed`、全量
`254 passed`。接受门限是三档/seed/profile/配对/provenance 全部完整，truth 缺失不补零，嵌套 timing
不相加。该段是运行前接口记录；真实三档 comparator 随后已完成，结果与限制见本页顶部。

## 2026-07-15 M5N2 20-case 接入复核

本批唯一正式输入是
`../airsim_runtime/outputs/p1_terminal_timing_funnel_10seed_20260715_m5n2/` 及其显式登记的 20 个
M5N2 case 路径。baseline/candidate 各 10 seed。M5N2 完成后、`TERM` 生效前额外完成的
`p1_terminal_timing_funnel_10seed_20260715_png_ttc_2v2_seed001` 明确排除在 M5N2 20-case 聚合与
验收之外；其余 tuned 2v2 和全部 dropout 未执行。不得搜索相邻目录补入，也不得把缺 case 计为 0。

20 个 canonical actual artifact 全部校验可用；物理层 pair/target/coalition 分别为
`12/60`、`12/40`、`0/20`，在线 truth identity/state 为 0。第二 primary 漏斗 20 个分母全部
available，但 physical=`0/20`。因此 actual 接线和 D6 分层消费已经闭合，M 对 N 物理性能尚未
闭合。

AirSim producer 必须区分两个 target 口径：canonical target physical success 是至少一个
participating pair 进入 5 m；cooperative target-stage diagnostic 是全部 required member 通过某一
阶段。两者需要不同字段和显式 semantics，D6 不允许后者覆盖 `target_intercept_success`。

本批 20 个第二 primary 最终均为 `collision_stop`，但现有 summary/command 没有持久化 collision
object。后续 runtime 应写出 collision object/actor identifier、事件时间戳、source API 和可用性；
字段缺失时 D6 必须报告 unavailable，不按成员冲突、环境碰撞、AirSim 状态问题或五米成功分类。

每个 case 的 `main_episode_bus/stage_timings.jsonl` 与 `control_tick_timings.jsonl` 均可由 D6
严格 loader 单独消费。按 20 个 case 池化后，两层各 3805 条；main bus mean/P95/max=
`349.34/487.40/1305.99 ms`，control tick=`1069.45/1254.06/2072.51 ms`。后者包含
`bus_processing`，禁止与前者相加。

该段记录修复前状态：partial acceptance 未传两层路径，strict single stream 会拒绝 case 边界重置。
当前已采用顶部 `case_aware_suite` 方案按 manifest 分 case 校验；不再要求重写全局 frame/time，旧
strict single-episode 行为也未改变。

## 2026-07-15 第二 primary/coalition 多 seed 输入合同

本节记录原始输入合同。main 已按相同配置完成 M5N2 baseline/candidate 各 10 seed；额外完成的
`png_ttc` seed001 排除在该结果之外，其余 tuned 2v2 和全部 dropout 未执行。D6 cooperative
consumer 仍要求逐成员写盘
`case/seed/profile/resource_id/target_id/member_role/member_order`、七阶段布尔证据、
`physical_intercept`、`coalition_id/version/epoch` 和失败时的显式 `first_failure_reason`。缺字段由
D6 报 unavailable，不从 actor truth、场景名或相邻层推断。

D6 分别输出第二 primary 漏斗和 pair/target/coalition 独立物理分母；coalition completion 不由
target success 回填。2026-07-15 已取得真实 M5N2 20-case 输入，接线与 availability 复核结果见
本页顶部；聚合外 `png_ttc` seed001 不改变本批结论，其余 tuned 2v2 和全部 dropout 未执行，第二
primary 与性能达标仍为 P1。

## 2026-07-15 两层分阶段计时离线接入

main 分别落盘 main bus 的 `stage_timings.jsonl`（`main-stage-timing-v1`）和 SimpleFlight 外层的
`control_tick_timings.jsonl`（`control-tick-stage-timing-v1`）。D6 只通过显式路径消费，不搜索
邻近目录，也不从旧总延迟反推阶段；缺文件为 unavailable，存在但非法则 fail closed。

control tick 的 `bus_processing` 已包含 main bus，所以两层只并列统计，不能相加。D6 输出两层
独立分布、预算违例和 dominant stage，不改变 AirSim reset、D1-D7 调度或控制。2026-07-15 仅以
两层各 2 帧 fixture 完成 `20/20` 专项和 `236/236` 全量测试。其后真实 M5N2 20-case 已证明
`100 ms` 未达标；case-aware 正式接线已关闭，优化后复验仍待 main 完成。

## 2026-07-14 actual target-state freshness/stale 正式接入

main 必须在最终 `control_commands.csv` 写盘后保留六列：control timestamp、measurement
timestamp、arrival timestamp、measurement age、stale 布尔和非空 state source。D6 不从其他
summary 补列，也不从场景名推断样本。时间约束为
`0 <= measurement <= arrival <= control`，age 必须等于 `control-measurement`；仅用 `1e-9 s`
绝对容差吸收十进制浮点序列化误差。任一行失败则该 case unavailable。

writer 将每 case summary 连同 source path/SHA256 写入 actual envelope。正式 suite consumer 再次
验证 SHA256、重读 CSV、复算并比对 payload；随后才进入 case、pooled aggregate、CSV/JSON 和中文
Markdown。2026-07-14 最新真实 2v2/M5N2 源分别验证 48/608 samples，stale 均为 0，来源均为
`d2_estimated_global_track`。验收报告位于
`outputs/p1_actual_target_state_freshness_20260714/d6_acceptance/`。该接入不改变 AirSim episode
顺序、控制、physical scorer、末端五层或 truth policy；同配置 multi-seed 趋势仍待 main 生产。

后续状态：本页顶部 M5N2 20-case 已提供同配置 multi-seed freshness，10389 条样本 stale=0；当前只
保留跨提交趋势、failure taxonomy 和独立批次复验，不再把缺同配置样本列为开放项。

## 2026-07-14 actual v2 真实 AirSim 接线结果

main 已按 finalize 顺序为 tuned 2v2 seed-1 和 M5N2 seed-1 写盘并注册独立
`d7-actual-execution-metrics-v2`。D6 离线校验 source/schema/hash/case/seed 后得到
required/available/unavailable=`2/2/0`，满足本轮 actual execution P0 的 `2/2` 全可用门限。两例
summary/CSV/actual 的物理成功计数均一致为 `2/2/2`，此前
`d7_actual_execution_command_physical_count_conflict` 未复现并关闭；不再需要以 legacy row、目录
搜索或 replay fallback 补证据。

M5N2 仍保留 pair=`2/3`、target=`2/2`、coalition=available `0/1` 的独立分母。该 coalition
结果是完整证据下的失败，不是接线 unavailable。统一报告 overall=false 的原因是本批仅 2 个
seed-1 case，缺 baseline/candidate 配对、1-5 帧 dropout 全矩阵和 multi-seed，尚未满足完整 P1
suite 设计。2v2/M5N2 loop latency=`123.3/384.6 ms`，性能预算违例合计 `231`，继续由 main/runtime
在 P1 做时延拆分和复跑；D6 只消费写盘结果。

## 2026-07-14 actual-execution suite 与 coalition 接线复核（真实重跑前计划）

AirSim suite 的正式 actual execution 准入只接受通过 source/schema/hash/case/seed 校验的
`d7-actual-execution-metrics-v2`。required case 缺失或登记为 unavailable 时 suite 总验收必须
fail closed；legacy main row 和离线五米结果只作 diagnostics，不能替代 actual envelope。
`arrival_coordination_required=false` 时，D6 按每个 required active primary 的独立五米成功计算
coalition completion，不要求共同到达窗口；required member、denominator、physical result 或开关
缺失，以及 summary/pair 冲突时仍为 `null/unavailable`。

当前四个历史真实 seed-1 case 的 actual artifact 均为 `unavailable`，原因均为
`d7_actual_execution_command_physical_count_conflict`。main 必须真实重跑 M5N2 baseline、M5N2
candidate、2v2 PNG-TTC 与 1-frame dropout，并在 producer 文件 finalize 后生成、注册有效 v2
artifact；旧 summary 或离线评分不能用于登记。2026-07-14 本轮只跑代码级回归：专项
`14 passed, 24 deselected`，D6 全量 `190 passed`；唯一 Matplotlib `Axes3D` warning 的边界是
3D projection 不可用，不影响本轮文件合同、二维报告或测试结论。D6 未启动 AirSim，也未修改
runtime。

## Actual plan identity v2 接线状态（2026-07-14 真实重跑前实现）

D6 consumer 已要求 `control_commands.csv` 的 `plan_id/plan_version/d4_target_node_id`，并在
`d7-actual-execution-metrics-v2` 中写出三项去重 metadata 及 provenance。merge v3 只从通过
schema、provenance、SHA256 和 CSV 对照校验的 actual envelope 发布这些字段，禁止 replay
fallback。plan/version 在每个 command row 必填；owner 只在 effective-authorized 的
secondary/distributed active/execution/reassignment 或显式 execute action 行必填。中心授权和
未授权 pending 可为空，整集无 authoritative owner 时 owner provenance 为 `unavailable`；需要
owner 的执行行缺值必须拒绝。合法 episode 可包含多个不同 plan/version；同一 plan 混用 version
必须拒绝。

该阶段只运行确定性离线测试：execution-evidence focused `20 passed`、D6 全量 `184 passed`，
没有启动真实 AirSim，也没有修改 runtime。main 此后已在两个真实 SimpleFlight seed-1 episode
生成并注册 v2 artifact，核对最终 `metrics.metadata`。单 seed freshness/stale 正式链现已关闭；
剩余工作是同配置 multi-seed 的 provenance 与 freshness 趋势验收。历史 v1 或未包含六个必需
freshness 字段的 artifact 不升级为当前 canonical 证据。

## Actual SimpleFlight execution artifact

正确写盘顺序固定为：

1. SimpleFlight 控制循环结束并关闭 `control_commands.csv`；
2. physical scorer 完成并关闭 `intercept_summary.json`；
3. main episode bus finalize，关闭 `main_episode_bus_metrics.json`；
4. main 调用 D6 `write_d7_actual_execution_evidence()` 写
   `d7_actual_execution_metrics.json`；
5. main 将该独立路径注册到 terminal closure row 的 `d7_execution_metrics`；
6. D6 suite consumer 校验 schema、case/seed 和三份 source SHA256 后聚合。

步骤 4 之前不得注册 D7 execution。`integrated_replay/d7_execution_metrics.json`、
`integrated_replay/metrics.json` 和尚未 finalize 的 main-bus snapshot 均不是 actual execution。
builder 失败时 main 应保留 registration unavailable 并记录 `ActualExecutionEvidenceError.reasons`，
不得用零值、邻近文件搜索或 replay fallback 补齐。

actual artifact 的安全字段必须同时存在：identity 从最终 `control_commands.csv` 的
`truth_identity_online_use` 逐样本计数，state 从最终 `intercept_summary.json` 的
`truth_state_online_use_count` 读取。D6 validator 校验二者各自的 source、semantics 和
availability；main 只注册 builder 产物，不应从 integrated replay 或默认 dataclass 零值补字段。
治理/终端 actual diagnostic 同样由 builder 发布，其中视觉 PNG switch 是 transition，持续授权
帧数保留在 supplemental sample count。

代码接口和当时的 `173 passed` 离线测试已完成。main runtime 后续补齐 identity，并完成本页顶部
两条真实 seed-1 actual artifact 复验；multi-seed 和性能门仍开放。D6 不在本模块内启动、reset
或调度 AirSim。

## 2026-07-14 terminal closure 路径登记合同

main 在每个 reset-separated case 完成 integrated replay 后，应从该 episode 的
`output_paths` 取得 `d3_plan_history_json` 和 `d7_execution_metrics`，再调用：

```python
register_terminal_closure_case_evidence(
    row,
    d3_plan_history_path=d3_history_path,
    d7_execution_metrics_path=d7_execution_path,
)
```

不得由 D6 根据 `case_id` 拼目录或 glob 猜测 D7 文件。路径为 null、文件尚未落盘、JSON/schema
错误或 seed 不匹配时，该 case unavailable，并在 suite 输入证据表和 D7 wiring 专节给出原因。
main 完成接线后的准入标准是：seed-1 的 4 个 terminal closure case 均显示 D7 path registered；
D3 保持 4/4 history available；raw D7 count 不重复进入 main 已提供的 terminal envelope。

2026-07-14 先前四案例 summary 已满足 D3（4/4 case、543 records），但 D7 为 0/4 registered，原因
均为 `d7_execution_metrics_path_not_registered_by_main`。D6 helper 和 consumer 已实现并通过
`159 passed`；runtime 接线与正式 suite 重生成不在 D6 ownership 内，仍列为 main P1。

本文只描述 D6 如何离线消费 AirSim/main runtime 已写盘产物。D6 不连接 AirSim client，不调用 `simGetDetections`、vehicle control、reset、pose 或任何实时 API；AirSim 启停、reset、episode 顺序、日志写盘和最终报告调度由 main runtime 负责。

## 2026-07-14 terminal suite v2 接线状态

D6-owned file consumer 已闭合，AirSim/main producer 接线仍开放。main 的
`p1_terminal_closure_summary.json` 后续每个 terminal count 必须写
`terminal_metrics[]`：`metric_name/value/producer/metric_scope/denominator/lifecycle`。main-bus
planned lock 使用独立 planned lifecycle；D7 runtime execution 使用独立 execution lifecycle，
两者不得复用同一 envelope。pair/target/coalition physical 另写 `physical_metric_context`，并保留
三个独立 opportunity denominator。

main 还需在每个 seed 写 `performance_metrics.sample_count > 0`、`loop_latency_ms` 和
`performance_budget_violation_count`；无样本不得写可用零。candidate 行需写实际 mechanism
trigger 和同口径 baseline/candidate effect。episode 的 `d3_plan_history.json` 通过
`--d3-plan-history` 传给 D6；若 D7 execution 另存文件，可用 `--d7-execution-summary`。

```bash
python3 research_modules/d6_evaluation_metrics/scripts/run_p1_acceptance_report.py \
  --output-dir <episode>/d6_p1_acceptance \
  --main-summary <episode>/p1_terminal_closure_summary.json \
  --d3-plan-history <episode>/d3_plan_history.json \
  --d7-execution-summary <episode>/d7_terminal_execution.json
```

D6 验证日期 2026-07-14：确定性 file fixtures，专项 `8 passed`、全量 `154 passed`；未启动
AirSim。真实同条件 multi-seed AirSim、producer envelope 完整性和跨提交趋势仍是 main-owned
P1 接线/证据项。

## 2026-07-14 truth-state 与 offline physical 写盘合同

`intercept_summary.json` 必须提供 `truth_state_online_use_count`、
`online_control_state_source`、`physical_intercept_source`、
`physical_intercept_available/unavailable_reason`；pair 必须提供
`online_truth_state_used`、`physical_evidence_available`、`physical_min_range_m` 和
`physical_success`，并逐 pair 提供 `target_state_source`。`control_commands.csv` 的
`physical_evidence_available`、`truth_state_online_use`、
`target_state_source`、measurement/arrival timestamp、age 和 stale 由 D6 只读审计。

严格路径要求 online source 为 `d2_estimated_global_track` 且 state-use 为 available `0`；
显式 fixture 使用 truth fixture class 且 state-use `>0`。physical 只有 summary、active pair
summaries、合法 source、显式 availability、逐 pair evidence 与逐 pair source 全部一致时
available。command-only/summary-only 不发布 physical 指标；command CSV 中的 evidence 即使为
真也只作审计，不能替代 pair summary。每个 participating pair 必须持久化可判定 physical
result；coalition 必须持久化 required-primary denominator、全部 required members、arrival
window，以及 opportunity 对应 completion count。缺失时由 D6 输出 null/unavailable 和统一 reason。

2026-07-14 的 7 类确定性离线 provenance 场景（seed N/A）全部通过，D6 全量
`150 passed`，1 条既有 matplotlib warning，未启动 AirSim。这只关闭 D6 P0 代码/测试，不是
真实 AirSim P1 证据。迁移前无 source 的历史 physical 值不能作为新 offline scorer evidence；
新 schema 的真实同条件 multi-seed 写盘、逐 pair provenance 与 freshness 验收仍为 P1。

## 2026-07-14 truth tracking 写盘合同状态

AirSim/main 产物没有 evaluator-side truth-to-track pair 时，D6 的 RMSE、continuity 和 IDSW
必须写为 null/unavailable；不得因 `EpisodeMetrics` 缺省、main-bus load 或 replay/execution merge
出现零。truth 显式配对且身份稳定时，`id_switch_count` 写为 available `0`。episode CSV 单列
三项 availability，JSON/Markdown 保留相同状态与原因。

本次只运行 5 个确定性离线场景（2026-07-14，seed N/A），D6 全量 `137 passed`，没有启动
AirSim。接受门限覆盖 truthless unavailable、完整 truth 的 IDSW available `0/1` 和多格式状态
一致性。真实 AirSim multi-seed 的 seed/config/schema/hash provenance，以及 D2 lifecycle 与
D3 churn 基于统一 episode clock/global ID/plan version 的 join，仍为 P1 集成工作。

## 2026-07-14 第二批 canonical history 集成状态

main 每个 episode 写出的 `d3_plan_history.json` 可直接作为
`P1SystemEvidenceInputs.d3_assignment_churn`。D6 校验 wrapper/record schema、record_count、
sequence/order key、timestamp、assignment/coalition/feedback/owner 结构和 truth 隔离；校验失败
不会尝试排序或修复，而是输出 unavailable 与原因。

CLI 调用：

```bash
python3 research_modules/d6_evaluation_metrics/scripts/run_p1_system_evidence_report.py \
  --d3-plan-history /path/to/episode/d3_plan_history.json \
  --output-dir /path/to/d6_p1_system_evidence
```

main 的 Python 调度也可直接构造
`P1SystemEvidenceInputs(d3_assignment_churn=episode_dir / "d3_plan_history.json")`，再调用
`P1SystemEvidenceReportGenerator().write_report_bundle(...)`。D6 不扫描 main episode、不改变
episode 顺序，也不回写 D3。

新增报告字段为 history record count/validation reasons、计划与联盟 version/epoch churn、
assignment snapshot membership 总体及 primary/reserve 分项、owner change、soft/hard feedback。
正式 cooperative-role snapshot 仍兼容且不用于推断 history churn。

2026-07-14 使用 canonical JSON fixture 完成专项 `24 passed`、D6 全量 `132 passed`，另有 1 条
matplotlib `Axes3D` 环境 warning。本轮没有启动 AirSim，也没有新增物理性能证据；剩余 P1
是把真实 multi-seed episode 持续送入该入口形成跨提交趋势和稳定 failure taxonomy。以下
第一批 2026-07-14 与 2026-07-13 产物状态均为历史快照。

## 2026-07-14 第一批 P0/P1 状态（历史）

D6 已关闭 D3 churn availability 的评估级 P0：AirSim/main 只提供最终 D3 快照、空 mapping
或单条无序记录时，计划版本、联盟版本、联盟 epoch 和成员变化 churn 均保持 unavailable。
只有 producer 显式写出 count，或提供至少两条顺序明确且字段完整的历史记录，才计算该指标；
稳定历史或显式零才是 available `0`。

本次没有启动 AirSim，也没有生成新的物理实验结论。验证日期为 2026-07-14，使用 5 类离线
fixture；前三类四项全 unavailable、两条稳定有序与显式零四项全 available `0`，满足验收
标准。正式 40-case cooperative-role fixture 保持角色统计兼容且四项 churn unavailable。
专项 `12 passed`，D6 全量 `120 passed`，另有 1 条 matplotlib `Axes3D` 环境 warning。

当前剩余 P1 是 main/D3 写盘真实有序 plan history、统一 episode clock、version/epoch、
provenance/availability，以及长期 multi-seed 趋势和跨批次失败原因治理。P2 optional parser 和
外部 benchmark 状态不变。以下 2026-07-13 产物数量和结果均为历史实验快照。

## 2026-07-13 历史正式产物消费状态

七源统一报告已经消费正式 AirSim/main 产物，各 source 均 available：D1 `1` 行、D2 `3660` 行、D3 `40` 行、D4 `60` 行、D5 per-primary `160` 行、native MOT `18` 行、D7 `164` 行。D7 的 164 行由 160 条 pair/safety 记录和 4 条 profile 汇总组成，profile aggregate 不与逐 pair 四层重复计数。

正式 M5N2 结果为最佳 profile coalition `5/10`、overall `8/40`；D7 四层为 contract `35`、control `7`、mode switch `9`、physical `62`。online truth use、`global_track_id` rewrite 和 reserve unauthorized execution 均为 0。D3 产物缺少逐时刻 plan history，因此 churn 保持 `unavailable`，D6 不从最终 snapshot 或 version 总数重建时序。

当前 D6 回归为 `115 passed`。真实 4 m/2 m dense-crossing、M5N2、D4 episode fault 和 native MOT 已从“待 main 提供”转为“正式产物已消费”。开放 P1 仅包括长期 multi-seed 趋势、producer 逐时刻 schema 和跨批次失败原因治理；P2 工具保持 optional/offline，不进入默认路径。

## 1. 边界

D6 AirSim 集成是 offline-only：

- 输入是已经保存的 JSONL、CSV、JSON、metadata 和可选 PNG 路径。
- D6 不订阅 runtime bus，不向 D1-D7 回写指标，不触发 replan/failover/guidance。
- D6 不读取在线 truth ID 参与控制；truth label 只用于离线评估。
- D6 不生成 fire-control 参数、毁伤逻辑、自动处置或授权绕过流程。

## 2. 当前已实现的离线入口

| 入口 | 当前输入 | 已实现能力 | 未覆盖 |
|---|---|---|---|
| `load_blocks_replay_jsonl()` | `blocks_frames.jsonl`、可选 `blocks_sensor_observations.jsonl` | 构建 truth summary、规模字段、视觉 track、terminal records、video metadata/bbox link records、D1 replay observation links、多视角 consensus/conflict 基线事件 | 不扫描 episode 目录，不解析 AirSim 原生 recording，不调用 AirSim |
| `load_episode_log_jsonl()` | 标准化 `truth_summary/track/assignment/event/link/terminal` JSONL | 读取 D6 统一记录模型，未知 record type 报错 | 不负责上游 schema 转换 |
| `load_d4_active_degradation_decisions()` | D4 active-degradation CSV | 读取主动降级、二级协助、触发原因和窗口 delta metadata | 不判断主动降级必要性，除非 main/D4 提供 review label |
| `load_d7_intercept_outputs()` | `control_commands.csv`、`intercept_summary.json` | 读取 gate、visual PNG switch、terminal takeover、拦截结果、reject reason | 不运行 D7，不发控制 |
| `load_d7_guidance_timeseries()` | `guidance_records.csv`、`guidance_summaries.json`，可合并 control/intercept 输出 | 读取 mode switch、D4/D5 state、plan/version、guidance law、terminal contract reject | 不负责保证 main 每个 episode 都写出这些文件 |
| `P1SystemEvidenceReportGenerator` | D1-D7 正式 summary/aggregate 与 native MOT execution index | 统一展开七源 available 记录，输出 CSV、JSON、中文 Markdown 和 PNG，并保持四层、availability 和 truth 审计 | D3 缺逐时刻 history 时 churn 保持 unavailable |
| `merge_replay_with_execution_metrics()` | integrated replay 与 main bus execution metrics | 按字段优先级合并离线 replay 和正式执行证据，保留 source/availability/provenance | 不回写 AirSim runtime，不从缺失值构造执行结果 |

## 3. Blocks Replay JSONL 合同

### 3.1 `blocks_frames.jsonl`

每行代表一个 AirSim Blocks frame。D6 当前消费字段：

```text
episode_id
scenario_name
timestamp
truth_objects[]
resources[]
cameras[]
visual_detections[]
metadata.images[] 或 metadata.image
```

`truth_objects[]` 推荐字段：

```text
object_id
object_type = target
position_ned
velocity_ned
threat_score
```

D6 用它构建：

- `truth_summary.truth_timestamps`
- `truth_summary.total_truth_opportunities`
- `truth_summary.high_threat_ids`
- `truth_summary.high_threat_by_timestamp`
- `truth_summary.scenario.target_count`

`resources[]` 推荐字段：

```text
resource_id
metadata.airsim_vehicle_name
```

D6 用它映射 AirSim vehicle/camera owner 到资源 ID，并计算 `resource_count/drone_count`。

`cameras[]` 推荐字段：

```text
camera_id
owner_id
fx
fy
cx
cy
width
height
position_ned
rotation_world_to_camera
```

D6 用它计算 `camera_count`，并把相机内外参保存在 bbox `LinkRecord.metadata` 中，支持无 PNG 的多视角/末端评估。

`visual_detections[]` 推荐字段：

```text
camera_id
object_id
detection_id
local_track_id
bbox_xyxy
center_px
confidence
metadata.airsim_detection_name
object_name
```

D6 当前转换为：

- `TrackRecord`：`association_source="blocks_visual_detection"`。
- `TerminalRecord`：`decision_state="associated"`，用于末端配准准确率。
- `LinkRecord(payload_kind="bbox")`：用于 bbox delivery、多视角和通信统计。
- `EventRecord(event_type="multi_view_consensus_result")`：同一 object 被多个 camera 检出时生成。
- `EventRecord(event_type="cross_view_conflict")`：同一 local track 关联多个 object 时生成。

`metadata.images[]` 推荐字段：

```text
camera_vehicle_name
camera_name
ok
saved
path
width
height
```

D6 当前转换为 `LinkRecord(payload_kind="video_metadata")`。`metadata.images[].path` 是否存在只进入 `png_saved` 元数据；PNG 不参与指标计算。

### 3.2 `blocks_sensor_observations.jsonl`

每行代表一个 D1 replay observation 或传感/通信样本。D6 当前消费字段：

```text
observation_id
sensor_id
modality
measurement_timestamp
arrival_timestamp
metadata.truth_id
metadata.source_node_id
metadata.target_node_id
metadata.sequence_id
metadata.delivered
metadata.stale_after_s
communication.*
```

`communication` 推荐字段：

```text
source_node_id
target_node_id
relay_node_id
link_type
payload_kind
sequence_id
sent_timestamp
received_timestamp
delivered
stale_after_s
```

D6 当前转换为：

- delivered 且带 `metadata.truth_id` 的 observation -> `TrackRecord`。
- 每条 observation -> `LinkRecord`，用于 `cross_node_latency_ms`、`message_drop_rate`、`out_of_order_count`、`stale_track_update_count`。

必须保留 `measurement_timestamp` 与 `arrival_timestamp`。这既是 D1 时间合同，也是 D6 stale/latency 指标的来源。

## 4. D4/D5/D7 AirSim 产物回灌与长期治理状态

### 4.1 D4

D6 已实现：

- 读取 D4 active-degradation CSV。
- 从 event/control metadata 识别 active/passive failover、secondary takeover、secondary reassignment、D4 reassign pending、distributed fallback。
- 输出 `active_degradation_count`、`passive_failover_count`、`secondary_node_takeover_count`、`secondary_reassignment_count`、`d4_reassign_pending_count`、`distributed_fallback_count`、`failover_active_window_delta_s`。

长期 producer schema 治理：

- 在真实 AirSim episode 中持续写出 D4 decision/event 日志。
- 写入 `trigger_timestamp`、`decision_timestamp`、`selected_coordinator`、`coverage_cell`、`review_label`。
- 固定 pre/post 窗口统计，才能正式输出主动降级必要性和改善 delta。

### 4.2 D5

D6 已实现：

- `TerminalRecord` 末端准确率、local ID switch、FOV 歧义、friend overlap hold、lock time。
- Blocks bbox/camera metadata 的无 PNG 多视角基线。
- `multi_view_consensus_rate`、`cross_view_conflict_count`、`duplicate_terminal_lock_count`。

长期 producer schema 治理：

- 把 D5 terminal association、identity claim、cross-view conflict、duplicate lock、friend overlap hold 和 terminal-center disagreement 事件写成 D6 可读 JSONL/CSV。
- 保留 `assigned_global_track_id`、`local_track_id`、`resource_id/camera_id`、validation label、bbox、相机内外参和 timestamp。
- 确保在线 D5 不使用 AirSim truth ID；truth/validation label 只在离线日志或 D6 评估阶段使用。

### 4.3 D7

D6 已实现：

- 读取 D7 `control_commands.csv`、`intercept_summary.json`、`guidance_records.csv`、`guidance_summaries.json`。
- 输出 gate pass rate、terminal switch allowed/reject、visual PNG switch、terminal takeover、mode switch、terminal contract reject、intercept success/counts、min range、time to intercept。
- 将 guidance law、D4/D5 state、plan/version、reject reason 写入 `EpisodeMetrics.metadata`。

main/orchestrator 已完成的接线：

- 截至 2026-07-07，真实 AirSim 拦截执行后的 `control_commands.csv` 与 `intercept_summary.json` 已合并到正式 `main_episode_bus_metrics.json`。
- 执行前合同检查结果另存为 `main_episode_bus_contract_metrics.json`，用于诊断 terminal contract、D4 reassign pending、D5 gate 等，不再覆盖正式执行结果。
- 正式指标可同时看到 D7 执行结果与 `guidance_law_counts`，避免“执行前集成指标”和“执行后拦截指标”分裂。

长期 producer schema 治理：

- 在每个 integrated AirSim episode 中稳定产出这些 D7 文件。
- 保持 D3 assignment plan version、D4 action/state、D5 terminal state 和 D7 guidance law 的同一时间轴。
- 在多 seed、5v5/N-v-N 和非默认 episode 中维持同样的正式 metrics 合并口径，而不是仅保留独立 D7 报告。

## 5. Integrated Episode Metrics 的推荐流程

main runtime 推荐按以下顺序写盘和评估：

1. 启动或复用 AirSim Blocks，按 reset 分隔 episode。
2. 写出 `blocks_frames.jsonl` 和 `blocks_sensor_observations.jsonl`。
3. 写出 D4 decision/event CSV/JSONL。
4. 写出 D5 terminal/multi-view JSONL 或转换后的 D6 `terminal/event/link` 记录。
5. 写出 D7 `guidance_records.csv`、`guidance_summaries.json`、`control_commands.csv`、`intercept_summary.json`。
6. main 调用 D6 loaders，把所有记录合并进一个 `MetricsCollector`；若执行了真实拦截，还要把 D7 execution metrics 写入正式 `main_episode_bus_metrics.json`，并保留 raw `main_episode_bus_contract_metrics.json`。
7. 调用 `compute_episode()`，传入同一 `truth_summary`、`episode_id`、`seed/batch_seed` 和实际规模字段。
8. 批量调用 `ReportGenerator` 输出 CSV、Markdown、PNG。

D6 代码已经具备第 6-8 步的模块能力，并已在本批正式产物上完成实际消费和统一报告。AirSim 启停、episode 顺序、跨文件合并调度和正式/contract metrics 文件写盘继续属于 main runtime；后续工作是长期 schema 与趋势治理，不是首次接入。

## 6. 时间、坐标和规模合同

时间：

- 所有流使用 episode 内单调秒级时间。
- 外部 timestamp 应转换为 `episode_time = source_timestamp - episode_start_timestamp`。
- `measurement_timestamp` 和 `arrival_timestamp` 必须保留。

坐标：

- D6 不做控制坐标转换。
- NED 是 D1/D6 融合和评估工作帧。
- WGS84 只作为外部参考；若进入 D6，需要先由上游转换或同时标注 frame。

规模：

- `drone_count/resource_count/target_count/camera_count` 必须来自日志字段或可验证记录集合。
- `2v2/5v5` 只作为场景名和 baseline label，不能当成规模分母。
- N-v-N episode 必须显式记录实际资源、目标和相机数量。

## 7. PNG 与视觉 metadata 策略

D6 不需要 PNG 截图来计算默认指标。PNG 只作为调试或人工复核证据。默认指标依赖：

```text
bbox_xyxy
camera_intrinsics
camera_extrinsics
timestamp
resource_id
camera_id
local_track_id
assigned_global_track_id
object_name
truth_label / validation_label
gate outcome
```

`visual_png_switch_count` 的 “PNG” 指导引模式/视觉 PNG 切换含义，不表示必须保存 PNG 图像文件。

## 8. 未实现项

### 8.1 AirSim 原生 recording parser

未实现。当前只支持 main runtime 的 Blocks JSONL。原因：

- Blocks JSONL 已包含 D6 需要的 truth、camera、bbox、observation 和 communication metadata。
- AirSim 原生 recording 字段和版本差异大，需要单独的 schema 样例。
- 原生 recording 到 NED、camera frame、resource ID、target ID 和 episode clock 的映射尚未固定。

缺少条件：

- 至少一个原生 recording 样例目录。
- 字段版本说明。
- 坐标和时间对齐规则。
- 与 Blocks JSONL 对照的测试 fixture。

### 8.2 Live AirSim replay/API

未实现，且不属于 D6 默认目标。D6 不应连接 live AirSim 或控制车辆。若未来需要 replay，仍应由 main runtime 执行 replay 并导出 D6 可读日志。

### 8.3 SCRIMMAGE 统计接口

未实现。原因：

- 当前仿真主线是 AirSim Blocks 和合成日志。
- 仓库没有 SCRIMMAGE message schema、episode 输出或 ID 映射样例。
- SCRIMMAGE 的通信/资源/目标/episode clock 需要独立映射。

缺少条件：

- SCRIMMAGE 输出样例。
- agent/resource/target ID 映射。
- 通信事件字段。
- episode clock 对齐规则。
- 批量目录结构和 CI fixture。

## 9. 验证建议

当前文档对应的 D6 全量回归基线为 `115 passed`。后续批次重点验证 source 行数、availability、逐时刻 provenance 和失败原因 taxonomy 的稳定性，不重新把已消费的正式 AirSim 产物标为待接入。

D6 模块测试：

```bash
pytest -q research_modules/d6_evaluation_metrics/tests
```

文档和空白检查：

```bash
git diff --check -- research_modules/d6_evaluation_metrics subagent_reviews/D6_*
```

AirSim 集成验收样例应至少覆盖：

- `blocks_frames.jsonl` 不保存 PNG 时仍能计算 detection、terminal、multi-view 和规模字段。
- `blocks_sensor_observations.jsonl` 能计算 latency/drop/stale。
- D4 active-degradation CSV 能生成 active/passive/secondary/pending 指标。
- D5 terminal/multi-view 事件能进入 terminal metrics。
- D7 control/guidance/intercept 文件能进入 gate/intercept metrics。
- `scenario_name="5v5"` 但实际 `resource_count/target_count/camera_count` 不等于 5 时，D6 按实际字段输出。

## 10. D2 v2 写盘合同补充（2026-07-15）

真实 AirSim dense-crossing episode 由 main/D2 写盘 D2 assessment 时，应保留
`admission_policy_version`、`gates`、`checks`、`gate_reasons`、连续率 baseline/headroom/
actual/required/error-reduction 和 `all_thresholds_passed`。D6 只在 episode 结束后读取，
不会通过该 recommendation 触发在线关联器切换。

历史 artifact 可以缺少这些字段；D6 将对应值报告为 `None/unavailable`，不会从连续率或
其他指标补算。2026-07-15 已离线消费 D2 从既有真实 Blocks/D1 governed replay 冻结生成的
20-seed、六 difficulty v2 artifact；D6 本批未新启动 AirSim。D2-only bundle 保留总体/分档
decision、dropout partial truth alignment、JPDA research-only 和默认路径未变，其他六源明确
unavailable，不与异批 case/seed 混合。system-evidence 专项 `31 passed`、D6 全量 `243 passed`。

## 11. 三维规模化 D1/D2 制品接线（2026-07-20）

本轮没有启动 AirSim。新增接口同时适用于三维质点和后续小规模 AirSim episode，因为 D6
只读取 episode 结束后写盘的公共评估制品，不依赖仿真后端。

main 后续应在同一 episode 目录持久化：

1. D1 `OfflineConsistencyResult` JSON，并在 manifest 记录文件 SHA-256；其规范映射摘要字段为
   `input_digests.d2_lineage_mapping`，aggregation row 对应
   `d2_lineage_mapping_digest`；
2. D2 `Scalable3DIdentityEvaluation` JSON，并在 manifest 记录文件 SHA-256和其四类 source
   hash；
3. actual scenario/version/run/seed 与 target/resource/recon/camera count；
4. D1/D2 在线源文件和 evaluator-only truth sidecar 的独立路径，truth 文件不得进入在线
   runtime bus。

D6 通过 `build_truth_isolated_episode_record()` 接收上述 context 和 hash-verified artifact；
D2 文件路径还必须携带完整四类 expected source hash。
任何文件缺失时相应指标保持 unavailable；文件存在但 SHA-256、schema、episode identity 或
真值隔离审计不一致时直接拒绝。D6 不通过 AirSim object name、actor ID、detect 返回的真实
名称或最近距离恢复 D2 身份。

D6 仅为历史 D1 制品读取 `canonical_mapping/canonical_mapping_digest` 别名；输出 CSV、JSON
和中文报告统一写为 `d2_lineage_mapping`。新旧字段同时出现但摘要不同，或 truth metrics
可用却两者均缺失时拒绝制品。

2026-07-20 的 5/20/50/100/200 仅为离线结构 fixture。真实 AirSim 仍按 5～20 架代表性
子场景运行；200 对 200 的正式验证由三维质点环境承担。当前工作树的 main-owned scalable
3D reporting 已调用 D6 生成单 episode/batch bundle；AirSim 正式 producer、稳定文件名/
manifest key 和真实多 seed 证据仍待 main 冻结与验收。

## 12. Identity commitment v2 与 runtime outcome 接线（2026-07-23）

该变化影响跨运行时评估，因此本计划需要同步。main 在 point-mass 或 AirSim episode 结束后
必须原子写出：

1. `d2.scalable3d_identity_evidence.v2`，每个 D2-owned track/frame 含公开
   `identity_commitment`；uncommitted records 的 `source_observations` 必须为空；
2. `d2.scalable3d_identity_evaluation.v2`，保留同一批完整
   `identity_evidence_records`、frames、strict metrics 和 commitment audit；
3. identity manifest，绑定 evaluation、evidence、online D1、online D2 和 observation truth
   五项文件 SHA-256，并保留 episode、availability 与 online truth isolation；
4. D6 truth-isolated manifest/input，向
   `build_truth_isolated_episode_record()` 传 evaluation SHA、四类 expected source hashes、
   identity manifest path 与 manifest SHA。

main 不得把 v2 内嵌 records 从 evaluation 删除，也不得把 v2 文件仅改 schema 字符串降为 v1。
`known_false_alarm/unknown` 仍只能来自 truth-free 上游 disposition；AirSim actor/object 名称和
offline truth sidecar 不得进入 online commitment。

runtime plan outcome join 的 11 类 `HashedArtifact` 输入不变，但 D2 evaluation 可以是 v2。
assignment window 命中 uncommitted mapping 时，D6 只令该 binding 的 identity/state/距离诊断
unavailable，并在 JSON/Markdown 保留 reason/details；不得回填 truth，也不得因这个合法显式状态
终止整个 episode。文件缺失、SHA 不符、audit 缺字段或违反零 binding policy 仍失败关闭。

接线后的首个验收为 clean seed 1100 baseline/candidate A/B，而不是直接启动多 seed AirSim：

- evaluation/evidence/manifest SHA 链全部通过；
- strict IDSW availability 与 D2 原值一致，跨 uncommitted gap 不由 D6 重算；
- all/observed commitment coverage 和 uncommitted mapping count 可用；
- candidate/source binding violation 均为 0，online truth use 为 0；
- D2 track count、D3 assignment count 和 runtime binding 可用性不比 baseline 退化。

2026-07-23 已在 clean commit `909669b2eefeab2ce30c8ac389d6bf9c0a8cbabc` 完成该首个
验收。baseline strict IDSW/track continuity/coverage continuity 为 `9/0.865/0.870`，
commitment coverage 为 `1.0`。candidate commitment coverage 为
`1714/1787=0.9591494124`，69 条 hold、4 条 after hold，两个 binding violation 为 0，在线
真值隔离通过。

candidate 未通过后两项准入要求：三个恢复航迹的证据与评分帧相差
`0.9308153039 s`，超过固定 `0.9 s` window，strict identity metrics 因此 unavailable；
D2/D3 数量也由 `203/200` 降至 `201/197`。不得通过扩大窗口或回填 strict IDSW 使其通过。
seed 1101/1102 已停止。本次是三维质点 episode，不是 AirSim；新 AirSim episode、AirSim
多 seed 及其 runtime binding 证据仍未执行。

## 13. Recovery publication freshness 评估接线（2026-07-23）

clean commit `65568579c99e4ef9939f0519f66c46d3076ef035` 的三维质点 seed 1100 A/B 已证明
D6 可以消费新的 publication-stale recovery reason，并保持 strict IDSW、continuity、
commitment coverage 和 binding violation 分栏。该验证没有启动 AirSim，不替代真实传感器
时间戳和网络迟到标定。

后续 point-mass 与 AirSim producer 应在同一 episode 公共配置中原子持久化：

```text
identity_commitment_recovery_config.schema_version
identity_commitment_recovery_config.config_version
identity_commitment_recovery_config.publication_freshness_gate_enabled
identity_commitment_recovery_config.max_recovery_evidence_age_seconds
identity_commitment_recovery_config.publication_freshness_clock
identity_commitment_recovery_config.publication_stale_behavior
```

该配置快照必须进入 manifest SHA-256 来源链，并与 D2 每帧 commitment reason 同属一个
runtime profile。D6 只读验证配置版本、预算和结果计数，不从 reason 字符串反推配置，也不把
AirSim `ClockSpeed`、墙钟时间或 arrival timestamp 冒充 D2 tracker frame 与 source
measurement timestamp 的差值。

当前 A/B 制品没有上述完整快照。D6 已确认 3 条
`source_observation_outside_recovery_publication_freshness_window` 记录和 strict
availability，但 recovery config v2 的完整 provenance 仍为 P1。main 集成本次 D6 partial
计数修复后，应从原 producer 制品写出新的 D6 派生 bundle；旧 clean A/B 目录保持只读。
该段描述旧制品状态，D6 consumer 的完成状态见第 14 节。

真实 AirSim 验收至少需要：

1. 同时保存统一状态有效时刻、source measurement timestamp、arrival timestamp 和 D2 tracker
   frame timestamp；
2. 按传感器、距离、遮挡和网络延迟统计 publication age 分布及被阻断恢复数；
3. 逐 seed 报告 strict IDSW/continuity availability、D2/D3 可用性、commitment coverage 和
   两类 binding violation；
4. 配置快照缺失或 SHA 不一致时，将 recovery-config provenance 标为 unavailable，不回填
   `0.9 s` 默认值；
5. 单 seed 非退化门未通过前不启动多 seed 算法准入。

## 14. Manifest v2 接线状态（2026-07-23）

D6 配置谱系 consumer 已实现。AirSim/main 调用可向
`build_truth_isolated_episode_record()` 传入：

```text
d2_identity_manifest
d2_expected_identity_manifest_sha256
d2_online_d2_records
d2_expected_online_d2_records_sha256
```

manifest 和在线 D2 JSONL 与 identity evaluation 位于同一目录时，D6 也可自动发现这两个
文件，但 main 仍应显式传入路径和外部 SHA，以保留完整的 episode 调度证据。manifest v2
必须绑定配置快照、规范配置 SHA、配置记录数、D2 记录数、consistency/source 声明和
`source_hashes.online_d2_records`。

AirSim runtime outcome join 已采用同一验证器。manifest v2 的任一缺字段、错误摘要、配置漂移
或计数不符均阻断联接；manifest v1 继续兼容，并将配置谱系标为
`identity_recovery_config_not_manifest_bound_v1`。该兼容状态不改变旧 episode 的 strict 或
partial 指标。

配置谱系合同实现阶段只执行 Python 合同测试，没有启动 Blocks 或 ComputerVision。随后 main
已在 detached clean `ff881316243ff5a2991a4659ab78637ed625d123` 上完成 seed 1100
baseline/candidate 的三维质点最终 A/B。两组 online D2 JSONL 均为 9 条，manifest v2 配置
SHA 均为
`sha256:bd8e362ec4ca128ed902826750b26d862286770d3c0c4d0b75960a50911a201a`；
D6 episode 和 runtime provenance 均为 verified。配置谱系 P1 已关闭。

该重跑不是 AirSim。AirSim 下一轮仍需确认每个 reset-separated episode 重新生成 manifest，
逐条 D2 发布携带同一配置，并保留真实传感器 measurement/arrival/frame timestamp。不得沿用
上一 episode 的配置 SHA。结构歧义候选因 D2/D3 可用性和 continuity 退化保持默认关闭，
因此没有继续 seeds 1101/1102、10 秒或 20-seed 矩阵。
