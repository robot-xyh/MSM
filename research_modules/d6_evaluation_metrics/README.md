# D6 Evaluation Metrics

## 2026-07-20 scalable 3D 算法实验矩阵离线审计

`d6-scalable3d-offline-evaluation-v5` 新增 D6-owned
`scalable3d-experiment-matrix-v1` 审计，不导入 main 的矩阵生成器或控制代码。评估器只从
`scenario_config.metadata` 读取 `experiment_matrix_schema`、`algorithm_variant`、
`comparison_key` 和 `full_system_validation`。历史 episode 仍按原指标评估，但矩阵字段保持
null/unavailable；目录名不参与变体、规模或配对身份判断。

R0、G1、A1、A2、A3、C1、F1 分别对应纯规则、D5 跨视角图模型、D3 学习分配、D4 区域策略、D5
主动视觉以及四项组合。变体执行同时核对 config/summary 中一致的 learning runtime、bundle loaded、
requested/effective assist、fallback 和实际采用证据。D3 要求 `learning_applied`，D5 图模型要求
`loaded_edge_model` 且无规则回退，D5 主动视觉要求 assist adopted。D4 advice 本身仍不证明采用；只有
main 发布的消费合同通过 schema、来源、先前建议引用和 summary 一致性审计，且
`consumable=true`、`d3_hint_applied=true`，A2/C1/F1 才能取得 D4 实际采用证据。

完整性按每个显式 comparison identity 固定要求 R0/G1/A1/A2/A3/C1；F1 只在中心失效、二级失效和
高威胁 M-to-N 场景进入分母。按变体输出 availability-aware 指标和阶段耗时；有完整 R0 配对时计算
变体减 R0 的 paired delta，至少两个配对键才生成 bootstrap 置信区间。clean/formal、dirty development
和其他 descriptive evidence 分开统计，配对差值不自动解释为因果效果。

2026-07-20 的 producer 风格 fixture 覆盖 R0 正例、三个矩阵标识缺失、伪变体、bundle 回退、F1 场景
限制、固定 cell 分母、双 seed 配对、dirty 分层及 D4 消费正反例。scalable 专项 `40 passed`，D6 全量
`320 passed`，仅有既有 Matplotlib `Axes3D` warning。真实 producer 的
R0/nominal/2v2/seed101 开发 smoke 复读结果为 metadata/execution valid=true、present/expected=1/6；
该 episode `repository_dirty=true`，不属于正式矩阵。另一个临时 5v5 producer smoke 的 D4 消费为
1 条合法、1 次 D3 hint applied、1 次 control adoption。正式全矩阵尚未运行。

## 2026-07-20 scalable 3D 当前 schema 合同准入

当前 `d6-scalable3d-offline-evaluation-v5` 延续 D6 内维护的
`d6-scalable3d-schema-registry-v1`，不导入 main 控制或仿真运行逻辑。当前合同固定为 world
`scalable3d-world-v1`、bus `scalable3d-episode-bus-v1`、scenario
`scalable3d-scenario-v1`、online observation `scalable3d-observation-v1`、offline truth
`scalable3d-offline-truth-v1`，并要求 scenario config 自身 schema 同为
`scalable3d-scenario-v1`。

manifest 和 config 的原始 schema 字段继续原样输出，便于读取历史数据。每项另输出 expected、match、
status 和 failure reason；旧值、未知值、篡改值或缺字段只能作为 descriptive evidence，不能通过 clean
formal acceptance。此前 fixture 使用的 `scalable3d-online-observation-v1` 已改为真实 producer 的
`scalable3d-observation-v1`。

验证覆盖当前合同匹配、五个 manifest schema 分别不匹配和缺失 bus schema。scalable/active-vision
专项 `32 passed`，D6 全量 `304 passed`，仅有既有 Matplotlib `Axes3D` warning。既有 6v6、seed 37
producer smoke 复读得到 schema match=true；formal=false 的唯一原因仍是 worktree dirty。

## 2026-07-20 scalable 3D 主动视觉命令与 ACK 离线评估

`d6-scalable3d-offline-evaluation-v3` 已接入 D5 主动视觉运行证据。D6 仍只读取 main 写盘的
`online_observations.jsonl` 和 `summary.json`，不导入运行时、不控制相机，也不读取在线真值。consumer
只接受 `modules.d5.active_vision` 的 `d5.active-vision-runtime.v1` 和
`runtime.camera_command_ack` 的 `scalable3d-camera-command-ack-v1`。

评估把五层证据分开记录：规则命令、影子建议、D5 辅助动作采用、main ACK applied/rejected、物理
结果。shadow 模式发布的实际命令仍归入规则命令；只有有效模型建议且没有 fallback 的记录才计 shadow
suggestion。`effective_mode=assist` 只说明 D5 经安全外壳选用了模型动作，必须再与同 camera/resource、
issued timestamp、plan/coalition/communication version、intent 和 mode 的 ACK 关联，才能计为运行时
applied。命令与 ACK 缺失、schema 非法、数量冲突或关联不完整时，对应指标为 null/unavailable，不能
补零。

新增指标包括 issued/ACK/applied/rejected、ACK 完成率与 P50/P95/max 延迟、过期/过时版本/相机不可用/
其他拒绝原因，以及 rule/assist 实际 applied 数。summary 的 issued/applied/rejected/ACK 和拒绝原因
计数必须与在线日志一致。目标航迹编号只与命令之前最近的 D2 `associated_tracks` 中心航迹集合核对，
ACK 也必须原样返回同一 `target_global_track_id`；D6 不创建、重绑定或修正该编号。主动视觉相关在线
记录另做递归 truth-like 字段审计。

物理归因继续 fail closed。即使 assist 命令获得 applied ACK，且同一 episode 存在五米接近事件，缺少
同 seed、同场景的规则控制组和实际采用证据时，`d5_active_vision_physical_outcome_attribution` 仍为
null/unavailable。聚合使用显式 target/resource/recon/camera 数量，不从 2v2/5v5 名称推断规模。

2026-07-20 的 8 项主动视觉确定性测试覆盖 rule/shadow/assist 分层、ACK 延迟、四类拒绝、未知中心
航迹、ACK 身份改写、在线 truth 污染、缺日志、summary 冲突、五米非归因和双 seed 报告。主动视觉与
既有 scalable 专项共 `25 passed`；D6 全量 `297 passed`，仅有既有 Matplotlib `Axes3D` warning。
同日使用当前 main runtime 做了一个临时接线 smoke：6v6、recon=1、camera=7、seed=37、duration=2.2 s，
共 133 条 disabled/rule command、133 条 matched/applied ACK、0 rejected、0 target-reference violation、
0 online truth field violation，summary counters 一致，RTF=4.740。该 episode 来自 dirty worktree，只有
1 个 seed，bootstrap 不可用，正式 acceptance 因 `repository_dirty_not_formal_evidence` 为 false；未
运行 AirSim。main 仍需提供 clean、多规模、多 seed 运行数据和配对控制/处理实验，才能评估主动视觉
对物理结果的贡献。

## 2026-07-20 scalable 3D 学习运行时与 D4 advice 离线评估

`d6-scalable3d-offline-evaluation-v2` 继续只读 main-owned episode 文件，不导入 scalable runtime，
不发布总线消息，也不参与控制。除既有 provenance、D1-D7、阶段 timing 和五米离线物理诊断外，
现在交叉消费 `scenario_config.metadata.learning_runtime` 与
`summary.module_final_diagnostics.learning_runtime`，并读取 manifest/config 中 D3/D4/D5 的 runtime
version。三模块分别报告 requested/effective mode、bundle requested/loaded、fallback reason、模型
fingerprint 和模型 version availability；bundle 未加载或字段缺失时，学习模型 fingerprint/version
均为 `null/unavailable+reason`，规则 runtime version 不冒充学习模型版本。

D4 新增只读消费 `modules.d4.region_resource_advice`，只接受
`d4-region-resource-advisory-runtime-v1` 与 `d4-region-resource-recommendation-v1`。逐 episode 输出
advice 发布/合法/非法数、requested/effective mode 分布、recommendation/shadow 输出数、assist
eligible 数、fallback 数与原因、推理延迟 P50/P95、quota delta 守恒违规、projection rejection、
正式裁决 unchanged/mutation，以及过期或缺失 schema/scenario/seed/authority/plan/epoch/lease evidence。
旧 schema、字段非法、digest flag 篡改、非守恒 projected payload 或版本栅栏不一致均 fail closed；
不会用合法记录子集缩小分母。

报告严格区分五层：bundle 能加载、shadow 有输出、assist 获准、控制实际采用、物理结果。D4 advice
只提供建议并保持正式 D4 裁决不变；`assist_eligible` 不是控制生效。当前 producer 另行发布
`d4-region-resource-consumption-v1`。D6 只有在消费合同引用先前已发布的完整 advice、main 来源和
summary 重复证据一致，且 D3 明确应用 hint 时才记录 control adoption；缺消费证据仍为
`null/unavailable`。五米接近仍只是一层离线物理诊断，不归因于 advice，也不生成 `mission_success`。

聚合仍按 scenario/version 和显式 target/resource/recon/camera 数量分组，以不同 seed 的 episode
均值做固定 RNG percentile bootstrap；单 seed 仅 descriptive，不产生 CI 或推断结论。正式 evidence
继续强制 `repository_dirty=false`，并校验配置 hash、D4 policy version、finite 和 online truth 隔离。

2026-07-20 确定性 fixture 覆盖既有规模/缺值边界，以及 learning disabled、D3/D4/D5 missing-bundle
fallback、loaded bundle 的 assist-to-shadow、assist gate、守恒与非守恒 quota、projection rejection、
正式裁决 unchanged/mutation、digest 篡改、旧 advice schema、缺 plan version、缺 advice 和 seeds 1/2
聚合。接受门限为全部字段 availability、五层语义、fail-closed、四类报告和 single-seed 规则通过；
结果为 scalable 专项 `17 passed`、D6 全量 `289 passed`，仅有既有 Matplotlib `Axes3D` warning。本轮
未运行真实 scalable 3D 或 AirSim episode，也没有形成学习模型验收结论。

```bash
python3 research_modules/d6_evaluation_metrics/scripts/run_scalable_3d_offline_evaluation.py \
  --episode-root <scalable_3d_batch_root> --output-dir <d6_report_dir>
```

当前限制：现有 `offline_truth_labels.jsonl` 只有 observation-to-truth 标签，没有显式
`global_track_id -> truth_target_id` 映射时，五米身份正确性保持 unavailable；D2 producer 明确声明
IDSW unavailable 时也不离线补算；D4 消费接口已有单 episode 接线证据，但真实 clean、多规模、多 seed
学习 bundle、完整矩阵与物理结果仍需 main 调用本入口验证。

## 2026-07-15 legacy ClockSpeed provenance 兼容与三档实测

ClockSpeed comparator v2 现兼容旧 1.0 suite 的持久化 settings provenance：仅当调用输入是 suite
root/summary 路径且 summary、20 个 case、20 个 result row 完全没有显式 ClockSpeed 时，才按每个
`case_id` 定位 sibling case 的
`generated_settings/blocks_actor_m5_n2_settings.json`。20/20 文件必须存在、顶层显式包含有限正数
`ClockSpeed` 且全量一致；缺文件、缺键、冲突、非有限值和字符串均 fail closed。mapping 输入不搜索
文件系统，目录名仍不参与推断，也不默认填 1.0。报告 manifest 保存 20 个绝对 evidence path。

真实 1.0/0.2/0.1 三档 comparator 已只读运行，输出在
`../airsim_runtime/outputs/m5n2_clock_speed_comparison_20260715/`。三档各 20 case、20 个跨档配对、truth
identity/state 在线使用均为 0；1.0 provenance scope 为
`sibling_case_generated_settings`，0.2/0.1 为 `case_result`。冻结机会合同在 60 case 中 56 match、4
mismatch；0.1 candidate seed007/009 和 0.2 candidate seed006/009 的受影响 aggregate 为
unavailable，不使用缩小分母。baseline pair/target/coalition 分别为 0.1 `4/30,4/20,0/10`、0.2
`9/30,9/20,0/10`、1.0 `6/30,6/20,0/10`。case wall timing 三档均缺源字段，保持 unavailable；
candidate 0.1/0.2 因合同不完整不形成成功率结论。三档 summary 加 20 个 legacy settings 的“绝对
路径+内容”组合 SHA-256 前后均为
`fdb745ee54f0c5ff414a812bf8e75eacd56fa5ea91ff02f64008fb6ee1759cd1`。

## 2026-07-15 ClockSpeed=0.1 NameError 紧急回归修复

`stage_timing.py` 的输入模式规范化函数现统一命名为
`_normalize_stage_timing_input_mode`，并前置定义在 loader、summarizer 和
`evaluate_stage_timing_inputs()` 三个调用点之前；旧 `_timing_input_mode` 名称已删除，避免实际批次
加载到缺失私有名称。新增回归按真实 suite 形态构造 baseline/candidate 各 seed 1-10 的 20-case
双层 merged JSONL，每 case 从 frame/timestamp 0 重置，直接调用 evaluator。

真实 ClockSpeed=0.1 M5N2 20/20 case 已用 P1 v6 只读复测：main bus/control tick 各 4036 records、
20 case，manifest match=true，两层 available，跨 case/跨层 total 均为 null。summary 与两份 timing
输入 SHA-256 前后不变。报告位于
`outputs/p1_clockspeed_0p1_m5n2_20case_20260715_case_aware_validation/`。本轮 timing 专项
`28 passed`、D6 全量 `264 passed`、`py_compile` 与 `diff --check` 通过。该句记录紧急修复当时状态；
三档 comparator 随后已完成，见本页顶部。

## 2026-07-15 ClockSpeed=0.2 case-aware 真实证据复核

`stage_timing.py` 现显式区分默认严格 `single_episode` 与 `case_aware_suite`。suite 模式要求每条记录
除原 schema 外恰好携带 `case_id/family/profile/seed`，拒绝其他 extra field；每个 case 内
frame/timestamp 严格递增，case 切换可重置且已离开的 case 不得再次出现。main bus/control tick 的
ordered case manifest 必须一致，只允许按 scope 池化分布；跨 case 首尾/总时长和跨层总时长均为
null。单 episode 的字段白名单和全流单调规则未放宽。P1 acceptance 升级为 v6，并以显式
`--stage-timing-input-mode case_aware_suite` 启用该 envelope。

真实 ClockSpeed=0.2 M5N2 suite 已完成 20/20 case。D6 对两份 merged timing 做只读复测：main bus
与 control tick 各 6567 records、20 个连续 case envelope，双层 manifest 一致，P1 报告生成成功，
输入文件复测前后 SHA-256 不变。输出位于
`outputs/p1_clockspeed_0p2_m5n2_20case_20260715_v2_case_aware_validation/`。

ClockSpeed comparator v2 冻结每 case opportunities 为 active-primary pair/target/coalition=`3/2/1`。
actual-execution unavailable 或 suite/intercept 机会数不符时，该 case 的物理与末端派生指标整体为
unavailable，不缩小分母、不补零。standby reserve 只进入排除审计，不计 active-primary success。
真实 0.2 审计为 18 match/2 mismatch：candidate seed006 为 D7 actual-execution unavailable，三类
physical/command/main conflict，实际机会 `2/1/1`；其 reserve physical success=true，但 active-primary
success=1、raw top-level success=2。candidate seed009 的 actual-execution available，但实际机会也为
`2/1/1`，因此同样是 contract mismatch。该段记录 0.2 审计；0.1 真实 P1 复测状态见顶部，不在此
混写三档性能结论。

2026-07-15 验证：timing 专项 `27 passed`、ClockSpeed 专项 `10 passed`、D6 全量 `263 passed`；仅有
既有 Matplotlib `Axes3D` warning。

## 2026-07-15 M5N2 ClockSpeed 三档离线对比接口

新增 `clock_speed_comparison.py` 和 `run_clock_speed_comparison.py`，输入同一套 M5N2
ClockSpeed=`1.0/0.2/0.1` 的三个 suite root 或 summary。入口强制每档恰有 20 个 case：baseline 与
candidate 各 seed 1-10；suite 内按 `case_id/profile/seed` 连接 case/result，三档之间再按同一键完整
配对。main 既有 `comparison_role=enhanced` 规范归一化为 candidate；family/resource/target 必须显式
为 `m5n2_paired/5/2`，不从目录名或场景简称推断规模。

ClockSpeed 只接受 suite/case `provenance`，或 20 个 result row 全量一致的显式 case-level
`clock_speed`；summary 根部裸字段和目录名都不作为来源。若 suite、case、result row 或注册的
`intercept_summary.parameters.clock_speed` 同时存在，值必须一致。输出包括 case CSV、profile
aggregate CSV、JSON、中文 Markdown 和 PNG 曲线。

指标覆盖 active-primary pair、target、coalition 三个独立物理分母，第二 primary 五米成功与最小
距离，required active-primary 最终锁、coalition 最终锁共识、`collision_stop`，case wall、main-bus
和 control-tick wall timing，以及
`simulated_time_per_tick_s = control_tick_wall_mean_ms / 1000 * ClockSpeed`。main bus 是 control tick
内层，两层禁止相加，cross-layer total 固定为 null。truth identity/state 在线使用继续逐 case 审计；
任一缺字段或坏 artifact 均为 `availability=unavailable`，不补零。

2026-07-15 确定性验收使用三档各 20 case、总计 60 case，baseline/candidate 各 seed 1-10；接受
门限为三档和 60 case 完整、20 个三档配对键完整、provenance 一致、缺失指标不补零及嵌套 timing
不相加。专项 `8 passed`，D6 当时全量 `254 passed`，仅有既有 Matplotlib `Axes3D` warning。该段是
运行前接口记录；真实三档调用与 availability-aware 结果已由本页顶部更新。

```bash
python3 research_modules/d6_evaluation_metrics/scripts/run_clock_speed_comparison.py \
  --suite <clock_1_0_suite_root_or_summary> \
  --suite <clock_0_2_suite_root_or_summary> \
  --suite <clock_0_1_suite_root_or_summary> \
  --output-dir <comparison_report_dir>
```

## 2026-07-15 真实 AirSim M5N2 20-case 复核

本轮只复核 `p1_terminal_timing_funnel_10seed_20260715_m5n2_*` 下 20 个已完成的
SimpleFlight case：baseline 与 `candidate_soft_prediction_trend_coast` 各 10 seed。M5N2 20/20
完成后、`TERM` 生效前额外完成了 `p1_terminal_timing_funnel_10seed_20260715_png_ttc_2v2_seed001`；
该 `png_ttc` seed001 明确排除在 M5N2 20-case 聚合与验收之外。其余 tuned 2v2 和全部 dropout case
未执行；缺失 case 保持 unavailable，不补零，也不能拼成完整 terminal-closure suite。

canonical `d7-actual-execution-metrics-v2` 的 required/available/unavailable 为 `20/20/0`，20 个
case 均通过 source/schema/hash/case/seed 校验。最终物理结果按独立分母为 pair `12/60`、target
`12/40`、coalition `0/20`；baseline 与 candidate 各为 `6/30`、`6/20`、`0/10`。两配置总量相同，
但逐 seed non-degradation 为 false，candidate 不能据此进入默认路径。10389 条实际命令目标状态
均来自 `d2_estimated_global_track`，stale 为 0；在线 truth identity/state 使用计数均为 0。

术语固定为：canonical target physical success（规范目标物理成功）表示“至少一个 participating
pair 进入 5 m”，本批为 `12/40`；cooperative target-stage diagnostic（协同目标阶段诊断）表示
“该目标全部 required member 通过指定阶段”。后者不能覆盖或替代
`target_intercept_success`，coalition completion 仍只由全部 required primary 的物理结果判定。

第二 primary 的七阶段证据为 assigned/visible/associated/contract `20/20`，control/mode
`17/20`，5 m physical `0/20`，所有阶段分母和 20 个失败原因均 available。首失败分布为：预测窗
过期 10、视觉获取未稳定 6、未形成稳定 D5 锁定 2、bbox 面积过小 1、bbox 靠近图像边缘 1。第二
primary 最近距离 mean/min/max=`12.654/8.843/14.740 m`，因此 coalition 零是完整证据下的失败，
不是 unavailable，也不能由 target 成功回填。

20 个第二 primary 的最终执行状态均为 `collision_stop`，但本批持久化产物未记录 collision object。
因此 D6 只能报告“碰撞停止原因对象 unavailable”，不能把它归因为联盟成员冲突、环境碰撞或
AirSim 状态问题，也不能从该终态反推五米成功。补齐 collision object/actor、时间戳和来源字段是
开放 P1 producer/接线缺口。

20 个 case 的 main-bus 与 control-tick 原始流分别有 3805 条，逐 case 严格校验均通过。离线按
scope 汇总：main bus mean/P95/max=`349.34/487.40/1305.99 ms`，预算违例 `3649/3805`，主导阶段
是 D1 fusion（mean `320.00 ms`）；control tick mean/P95/max=
`1069.45/1254.06/2072.51 ms`，预算违例 `3805/3805`，主导阶段是 AirSim frame sample（mean
`432.29 ms`）。control tick 的 `bus_processing` 已包含 main bus，两层禁止相加。

当前 partial acceptance bundle 未注册 timing 路径，显示 `unavailable`；现有 suite 合并 JSONL
又在 case 边界重置 frame/timestamp，不能作为单一严格递增流直接导入。所以上述 timing 是基于 20
个显式 case 路径的离线复核结果，正式 suite timing 接线仍是 P1。D6 指标口径和 consumer 已实现；
剩余 P1 是第二 primary 物理闭环、100 ms 性能预算、case-aware timing 汇总和后续独立批次验证。

## 2026-07-15 第二 primary 漏斗与独立分母 P1 报告口径关闭

`CooperativeClosureReportGenerator` 输出 schema 升级为 `d6-cooperative-closure-v3`。第二
primary 现按 `assigned -> visible -> associated -> contract_allowed -> control_allowed ->
mode_switched -> physical_intercept` 逐阶段报告通过数、有效分母、不可用数和比例；pair、target、
coalition 的物理结果另以各自写盘机会数统计，禁止跨层回填。coalition completion 单独保留有效/
不可用机会、完成数、失败数和完成率。

首失败原因只统计 producer 明确写出的 `first_failure_reason`。失败结果缺原因时输出
`unavailable/partial` 和缺失数，不再补 `unspecified`；缺物理结果时成功/失败为 null，不把
unavailable 当零。2026-07-15 确定性 fixture 专项 `11 passed`，D6 全量 `246 passed`，仅有既有
Matplotlib `Axes3D` warning；该代码批次未启动 AirSim。其后真实 M5N2 20-case 已按本页顶部回填，
第二 primary 与联盟性能仍为 P1；额外 `png_ttc` seed001 排除在本批聚合外，其余 tuned 2v2 和全部
dropout 未执行。

## 2026-07-15 分阶段延迟可观测性 P1 代码缺口关闭

D6 新增 `stage_timing.py`，严格离线消费 `main-stage-timing-v1` 与
`control-tick-stage-timing-v1` JSONL。schema/scope、frame/timestamp、预算、阶段值与状态、阶段
和、总耗时、未归因耗时、预算标志和错误状态均受校验；负数、NaN/Inf、状态冲突、重复/倒序帧
及和式冲突全部 fail closed。旧产物缺 timing 显示 `unavailable`，不补零。

每层独立输出阶段 sample、mean/P95/max、N/A/error、总 tick、预算违例和 dominant stage，并生成
CSV、JSON、中文 Markdown 与 PNG；嵌套的 main bus 与 control tick 禁止相加。P1 acceptance 当时
升级为 v5，当前已由顶部 case-aware 工作升级为 v6。2026-07-15 确定性动态规模无关 fixture（合法两层各
2 帧及完整负例矩阵）专项 `20 passed`、D6 全量 `236 passed`，未启动 AirSim。真实多 seed
M5N2 20-case 随后已实测并确认 `100 ms` 未达标；case-aware 正式接线现已关闭，瓶颈优化和跨提交
复验仍为开放 P1。

```bash
python3 research_modules/d6_evaluation_metrics/scripts/run_stage_timing_report.py \
  --output-dir <report_dir> --main-stage-timings <stage_timings.jsonl> \
  --control-tick-stage-timings <control_tick_timings.jsonl>
```

## 2026-07-14 actual target-state freshness/stale P1 指标链关闭

`d7-actual-execution-metrics-v2` 现从最终 `control_commands.csv` 强制消费
`timestamp_s`、`target_measurement_timestamp_s`、`target_arrival_timestamp_s`、
`target_measurement_age_s`、`target_state_stale` 和 `target_state_source`。缺列、空值、非有限值、
负值、measurement 晚于 arrival、arrival 晚于 control、age 与 `control-measurement` 冲突、非法
stale 布尔或空 source 都使整份 canonical evidence fail closed；不补零。合法显式 `False` 会形成
available stale `0`，合法 `True` 会形成 available 正计数，不会被误判为 unavailable。

每个 canonical case 的 `metrics.target_state_freshness` 输出 `sample_count`、mean/p95/max age、
stale count/rate 和 source distribution，并由独立 `metric_availability/source/semantics` 描述来源。
formal validator 仅在 source path 与 SHA256 通过后重读 CSV，使用同一严格算法复算并逐项对照
payload。case suite、pooled aggregate、aggregate CSV/JSON 和中文 Markdown 已接入该指标；physical、
末端五层、truth identity/state 隔离和 availability 三态未改变。

2026-07-14 使用最新持久化真实源复建：tuned 2v2 seed-1 为 48 samples，mean/p95/max=
`0.0375/0.2/0.2 s`；M5N2 seed-1 为 608 samples，`0.091118/0.2/0.2 s`。两例 stale 均为
`0/0%`，source distribution 分别为 `d2_estimated_global_track:48/608`；pooled 为 656 samples，
mean/p95/max=`0.087195/0.2/0.2 s`。关闭门限是两 case 均通过列、数值、时间、age、source hash 与
payload 精确复算检查；stale 零是本批观测结果，不是 availability 的通用定义。正式产物位于
`outputs/p1_actual_target_state_freshness_20260714/`。D6 全量 `216 passed`，仅保留既有
Matplotlib `Axes3D` warning。单 seed 正式 freshness/stale 指标链关闭；同配置 multi-seed、跨提交
趋势和 failure taxonomy 当时仍为 P1。其后本页顶部 20-case 已提供 10389 条同配置样本；现在只保留
跨提交趋势、failure taxonomy 和独立批次复验，不再把“缺同配置 multi-seed”列为当前缺口。

## 2026-07-14 actual v2 真实 AirSim 证据同步

main 于 2026-07-14 完成 tuned 2v2 seed-1 与 M5N2 seed-1 两次真实 AirSim/SimpleFlight
重跑。D6 统一报告对 canonical `d7-actual-execution-metrics-v2` 的
required/available/unavailable 判定为 `2/2/0`；本轮 actual execution 的接受门限是所有 required
case 均 available 且 unavailable 为 0，因此该 P0 证据门已通过。两场景的
`intercept_summary.json`、`control_commands.csv` 离线 scorer 和 actual artifact 物理成功计数均
为 `2/2/2`，旧 `d7_actual_execution_command_physical_count_conflict` 未复现并关闭。

M5N2 的 active pair、target、coalition 结果分别为 `2/3`、`2/2`、available `0/1`。coalition
是有完整分母和成员证据的显式失败，不是 unavailable；target `2/2` 不能替代第二 required
primary 未进入 5 m 的 coalition 结论。统一报告的 `overall_acceptance_passed=false` 也不否定
上述 actual gate：本批只有 2 个 seed-1 case，没有 baseline/candidate 成对比较、1-5 帧 dropout
全矩阵和多 seed，不能构成完整 P1 terminal-closure suite。

性能仍为开放 P1：2v2/M5N2 loop latency 分别为 `123.3 ms`、`384.6 ms`，性能预算违例分别为
`19`、`212`，合计 `231`。真实证据见
`../airsim_runtime/outputs/p0_actual_v2_validation_20260714/d6_acceptance/P1_UNIFIED_ACCEPTANCE_REPORT.md`
和 `../../subagent_reviews/MAIN_P0_ACTUAL_EXECUTION_AIRSIM_VALIDATION_REPORT_20260714.md`。本次仅同步
D6 文档，没有改变代码或指标算法。

## 2026-07-14 actual-execution 验收门与独立到达口径复核（真实重跑前历史）

正式 suite 只把通过校验的 canonical `d7-actual-execution-metrics-v2` 作为 actual execution
envelope。任一 required case 缺少该 artifact，或显式登记
`d7-actual-execution-unavailable-v1`，`actual_execution_all_available` 即为 false，suite 总验收
fail closed。legacy main row 和离线五米物理结果只保留 diagnostics；它们可独立说明离线物理
评分，但不能替代、补齐或晋升为 actual envelope。

当 `arrival_coordination_required=false` 时，coalition completion 不再要求共同到达窗口，而是对
每个 required active primary 的独立五米物理成功逐一评分：全部 required primary 成功才完成该
target coalition。required-primary denominator/member、physical result 或该开关缺失，以及 summary
与 pair 间冲突时，结果仍为 `null/unavailable`，不得补零。

本轮只完成代码级回归，没有启动 AirSim。四个历史真实 seed-1 case（M5N2 baseline、M5N2
candidate、2v2 PNG-TTC、1-frame dropout）的 actual artifact 仍为 `unavailable`，现有原因均为
`d7_actual_execution_command_physical_count_conflict`；main 必须真实重跑并注册有效 v2 artifact，
旧 main acceptance 与离线五米结果不能关闭该缺口。2026-07-14 实际验证结果为专项
`14 passed, 24 deselected`、D6 全量 `190 passed`。唯一 warning 来自 Matplotlib
`projections/__init__.py:63` 无法导入 `Axes3D`，边界仅为 3D projection 不可用，不影响本轮
JSON/CSV/Markdown 口径、二维报告或测试结论。

## 2026-07-14 actual plan identity provenance P0 关闭

`d7-actual-execution-metrics-v2` 现在把最终 `control_commands.csv` 中的 `plan_id`、
`plan_version` 和 `d4_target_node_id` 严格提取为 envelope `metadata.plan_ids`、
`metadata.plan_versions` 与 `metadata.owner_node_ids`。plan ID 和正整数 version 在每行都必填；
`d4_target_node_id` 列必需，但值只在“effective control 已授权且该行处于 secondary/distributed
active、execution、reassignment，或显式 execute secondary/distributed action”时必填。中心授权
行和未授权的 pre-transition/pending 行可为空；若没有观测到 authoritative owner，owner 集合为
空且 provenance 明确为 `unavailable`。secondary/distributed effective-authorized 行缺 owner 仍使
整个 actual envelope fail closed。三个数组均去重排序，合法多计划可形成多版本历史，但同一
`plan_id` 绑定多个 version、plan/version 缺失或非法 version 都 fail closed。

validator 除结构和 provenance 校验外，在 merge 的 SHA256 校验路径上重读 command CSV，并把
提取结果与 envelope metadata 逐项对照。`d6.execution-metrics-merge.v3` 会先删除 replay 中的
同名计划 metadata，再只复制 validator 返回的 actual metadata；因此最终
`metrics.metadata.plan_ids` 不再为空，也不会从 replay 推断。contract/control/mode、physical、
performance 和 truth safety 的既有来源及计数语义未改变。

验证日期为 2026-07-14：确定性离线测试（seed N/A）覆盖中心授权空 owner 正例、未授权 pending
空 owner 正例、secondary effective-authorized 空 owner 负例、plan/version 缺失、合法多版本、
同 plan 混合版本冲突、provenance/来源篡改和 merge 隔离；execution-evidence focused
`20 passed`，D6 全量 `184 passed`，仅有 1 条既有 matplotlib `Axes3D` warning。没有启动或
运行真实 AirSim。该阶段关闭 D6-owned P0；其后 main/runtime 已完成本页顶部两条真实 seed-1
v2 artifact 的生成和注册。同条件 multi-seed provenance 与趋势验收仍保持 P1。

D6 是 MSM 的离线评估与报告模块。它只消费已经写盘的日志、CSV、JSON/JSONL 和仿真真值，输出 `EpisodeMetrics`、CSV、Markdown 报告和 PNG 图表；不参与 D1-D7 的实时控制链路，不生成任务、分配、导引、授权、火控、毁伤或自动处置动作。

## 2026-07-14 actual SimpleFlight execution evidence P0 收尾（真实重跑前实现记录）

D6 不再接受 `integrated_replay/d7_execution_metrics.json` 作为执行后规范证据。该文件可以保留
合同、模式和性能的离线诊断值，但只能作为 audit-only replay；当 actual execution 缺失时，
`merge_replay_with_execution_metrics()` 会把 execution-only 指标保持为
`null/unavailable`，不会回退 replay 数值。

main 应在 SimpleFlight 控制结束且三个输入文件均已最终写盘后调用：

```python
from d6_evaluation_metrics import write_d7_actual_execution_evidence

actual_path = write_d7_actual_execution_evidence(
    output_path=episode_dir / "d7_actual_execution_metrics.json",
    control_commands_path=episode_dir / "control_commands.csv",
    intercept_summary_path=episode_dir / "intercept_summary.json",
    main_episode_bus_metrics_path=(
        episode_dir / "main_episode_bus" / "main_episode_bus_metrics.json"
    ),
)
```

writer 输出 `d7-actual-execution-metrics-v2`，包含固定 producer
`main_airsim_runtime`、阶段 `post_simpleflight_control`、scope `actual_execution`、case/seed/
规模、三份来源的绝对路径和 SHA256。合同与控制计数取最终 command CSV，物理结果取 intercept
summary，性能样本与时延取最终 main bus clock。规范模式切换只统计
`mode_switched=true AND effective_control_authorized=true`，并强制
`mode_switched_count <= control_allowed_count`。无正性能样本、来源计数冲突、控制字段冲突、
文件缺失或 hash 不一致时不发布 canonical artifact。

同一 envelope 还从 command CSV 严格计算主动降级、二级重分配、重分配 pending、终端锁定获取、
视觉 PNG 切换和拒绝原因等 actual diagnostic count。`visual_png_switch_count` 是“获得控制授权后
进入视觉 PNG”的状态迁移数，`visual_png_control_allowed_sample_count` 是持续授权样本数，后者只作
supplemental，不得冒充切换次数。安全计数并列发布：`truth_identity_online_use_count` 来自
`control_commands.csv.truth_identity_online_use` 的显式布尔样本，
`truth_state_online_use_count` 来自 `intercept_summary.json` 的显式计数；二者均有独立 source、
semantics 和 availability，缺列、缺字段或来源错误时整个 actual envelope fail closed。

main 随后只能把该独立文件注册为 `d7_execution_metrics`；不得注册 integrated replay 或把旧文件
改名。`terminal_closure_evidence` 会再次核对 schema、case/seed、来源文件存在性和 SHA256。

本批复核 2026-07-14 两个既有 M5N2 seed-1 episode，未重新运行 AirSim：baseline 的 raw replay
为 mode `17`、loop `0 ms`，actual builder 为 mode `0`、`142` samples、`386.519 ms`；candidate
raw replay 为 mode `13`、loop `0 ms`，actual builder 为 mode `0`、`141` samples、`398.333 ms`。
两组 effective control 和 physical 均为 0。2026-07-14 main runtime 在 state 字段接入后暴露
identity 字段缺失；本次已在 D6 canonical schema/builder/validator 中补齐。D6 全量回归
`173 passed`，仅有 1 条既有
Matplotlib `Axes3D` 环境 warning。

## 2026-07-14 terminal closure 多案例证据接线（先前四案例状态）

`P1AcceptanceReportGenerator` 现在会安全消费
`main_terminal_closure.rows[*].d3_plan_history`，输出
`d6-d3-case-history-suite-v1` 的逐 `case_id/seed`、逐 seed 和 suite 汇总。每个文件独立检查路径、
JSON root、D3 wrapper/record schema、记录顺序和 seed 绑定；坏文件只使对应 case
`unavailable`，不会中断整个 suite，也不会补零。显式传入单个
`P1AcceptanceInputs.d3_plan_history` 的兼容入口保留。

D7 使用相同的逐 case fail-closed 接线。main 行没有显式
`d7_execution_metrics` 时，报告给出
`d7_execution_metrics_path_not_registered_by_main`；D6 不扫描相邻目录。已注册文件按
`d6-episode-metrics-structural-v1` 检查 episode、seed、availability、metadata 和核心执行计数。
raw `EpisodeMetrics` 不带 terminal metric envelope 的 producer/scope/lifecycle，因此只进入
`d7_execution_evidence`，不被二次导入四层指标。

main 可在文件写盘后调用纯函数合同：

```python
from d6_evaluation_metrics import register_terminal_closure_case_evidence

row = register_terminal_closure_case_evidence(
    row,
    d3_plan_history_path=d3_history_path,
    d7_execution_metrics_path=d7_metrics_path,
)
```

对现有
`p1_terminal_closure_semantics_v2_seed1_20260714` 的离线复核中，4/4 case 的 D3 history
可用，共 543 records；原 summary 的 4 个 D7 路径均未注册，均按上述原因 unavailable。使用
helper 在临时 summary 中显式注册现有 D7 文件后，4/4 case 通过结构校验，执行侧
`control_allowed_count` 合计 51；main 四层同名指标仍独立为 51，没有重复聚合。测试结果为
`159 passed`，仅有 1 条既有 matplotlib `Axes3D` 环境 warning。未启动 AirSim，也未修改
AirSim runtime；main 注册 D7 路径并重生成正式 suite 仍是跨模块 P1。

## 2026-07-14 terminal suite P1 评估口径关闭

`P1AcceptanceReportGenerator` 已升级为 `d6-p1-unified-acceptance-v2`。terminal count 使用
`d6-terminal-metric-envelope-v1` 长表，每条 `contract_allowed_count`、
`control_allowed_count`、`terminal_switch_allowed_count`、`mode_switched_count` 和
`physical_intercept_count` 必须带：

```json
{
  "metric_name": "contract_allowed_count",
  "value": 1,
  "producer": "d7_runtime_bus",
  "metric_scope": "execution",
  "denominator": 3,
  "lifecycle": "terminal_execution"
}
```

`denominator` 必须为正样本数；缺 producer/scope/lifecycle、无样本 `0/0`、值越过分母或层级
不匹配均输出 unavailable。聚合键包含 `source + producer + metric_scope + lifecycle`。因此
main-bus `planned_lock/plan_generation` 与 D7 `execution/terminal_execution` 即使指标同名，也只
逐组报告，顶层 `sum` 为 `null`，不会比较、求和或覆盖。`terminal_switch_allowed_count` 保留为
control 层 gate，`mode_switched_count` 保留为 mode 层执行结果；contract/control/mode/physical
四层不互推。

pair/target/coalition physical outcome 还要求 `physical_metric_context` 提供 producer、scope、
lifecycle，并分别使用各自 opportunity count。`loop_latency_ms` 和
`performance_budget_violation_count` 只有在 `performance_metrics.sample_count > 0` 时可用；
无样本的显式零保持 unavailable。candidate non-degradation 另带 `effectiveness_evidence`：
baseline/candidate 效果均为 0 且 candidate trigger 为 0 时固定为 `inconclusive`，promotion 为
false。

terminal suite 可直接读取 D3 canonical 文件：Python API 使用
`P1AcceptanceInputs(d3_plan_history=Path(...))`，CLI 使用 `--d3-plan-history`。校验通过后输出最新
plan ID/version、primary/reserve membership、owner 及 plan/coalition/membership/owner/feedback
churn；缺文件或坏 history 保持 unavailable。报告产物为：

- `p1_acceptance_per_seed.csv` / `p1_acceptance_per_seed.json`；
- `p1_acceptance_terminal_metrics.csv`；
- `p1_acceptance_aggregate.json` / `p1_acceptance_aggregate.csv`；
- 中文 `P1_UNIFIED_ACCEPTANCE_REPORT.md` 与 PNG。

```bash
python3 research_modules/d6_evaluation_metrics/scripts/run_p1_acceptance_report.py \
  --output-dir /tmp/msm_p1_acceptance \
  --main-summary /path/to/p1_terminal_closure_summary.json \
  --d3-plan-history /path/to/d3_plan_history.json \
  --d7-execution-summary /path/to/d7_terminal_execution.json
```

2026-07-14 使用 planned-lock/execution 同名隔离、零样本性能、零效果零触发、canonical 两 tick
history 四类确定性离线场景验收；专项 `8 passed`，D6 全量 `154 passed`，1 条既有 matplotlib
warning，未运行 AirSim。关闭的是 D6 schema/consumer/report P1；main `p1_terminal_closure` 仍需
写出上述 envelope、physical context、performance sample count、candidate trigger/effect，并把
`d3_plan_history.json` 传给 D6，之后才可形成真实 multi-seed 结论。

## 2026-07-14 physical provenance gate P0 关闭

D6 现将真值身份和真值状态分为两个 availability-aware 指标：既有
`truth_identity_online_use_count` 保持兼容；新增 `truth_state_online_use_count` 从
`intercept_summary.json`、pair summary 和 `control_commands.csv` 的实际布尔值与
`target_state_source` 聚合。严格 D2 estimated-state 路径为 available `0`；显式
`airsim_actor_truth_fixture` 必须为正数，summary 的假零不能覆盖 pair/command 正证据。

当前 physical layer 只在 summary 显式 `physical_intercept_available=true`、source 合法、
summary online control source 属于对应 class，且至少一个 active assigned pair summary 存在时
available。`offline_truth_distance_scorer` 只接受 `d2_estimated_global_track`；
`online_truth_state_fixture` 只接受显式 truth fixture class。每个 active pair 必须同时声明
`physical_evidence_available=true`，且 `target_state_source` 必须与 summary online source 完全
一致；此外每个参与 pair 必须有显式 `physical_success/physical_intercept`，或 D7 scorer 规范终态
`collision_intercept/range_intercept/timeout/aborted`。仅声明 evidence available 不构成结果。
command-only、summary-only、缺 pair result/evidence 或 pair source mismatch 时，pair/target/
coalition physical count/rate 与 `physical_intercept_count` 全部为 `None/unavailable`，并带明确
reason。command CSV loader 保留 `physical_evidence_available` 供审计，但 command rows 不再生成
physical pair。coalition 还要求显式机会分母、完整 persisted required-primary 成员、arrival
window，以及 summary 有机会时的显式 completion count；缺任一项均为 unavailable。证据完整的
显式失败仍保留 available `0`。`physical_min_range_m` 与在线估计距离分开消费；无 scorer
provenance 的旧 status 只保留 `legacy_physical_status_present`，不晋升为 physical success。

2026-07-14 以 7 类确定性离线 provenance 场景验收，seed N/A：严格 estimated-state、显式
truth fixture、合法 offline scorer、缺 source legacy、command 缺 pair evidence、summary-only
aggregate、active pair source mismatch；接受标准为两个合法 source 正例 available，其余缺证据
负例全层 `None/unavailable`。新增 7 项 result/denominator/window 正负例覆盖缺 pair result、
缺 required member、缺 window、缺 denominator、summary 缺 completion、规范终态和完整显式零；
结果全部满足，D6 全量 `150 passed`，1 条既有 matplotlib
`Axes3D` 环境 warning，未运行 AirSim。本次只关闭 D6 consumer/metric/test 的 P0，不等于
真实 AirSim P1 物理证据完成。2026-07-11 至 07-13 缺新 provenance 的 physical 数值仍是
迁移前历史口径；target-state age/stale 单 seed 正式分布已由本文顶部关闭，真实同条件
multi-seed AirSim 重跑和跨批 freshness 趋势仍为 P1。

## 2026-07-14 truthless tracking 假零 P0 关闭

`EpisodeMetrics.track_rmse`、`track_continuity` 和显式保留的 `id_switch_count` 现支持
`None/unavailable`。空输入、只有匿名 `TrackRecord`，或没有 evaluator-side truth-to-track
配对时不再输出默认零。RMSE 需要同一记录的 track/truth position；continuity 需要非空且覆盖
已配对 track timestamp 的 truth sidecar；ID switch 需要显式 truth ID 与 global track ID 历史。
因此完整 identity history 中“没有切换”是 available `0`，没有 identity pair 则是 unavailable。

availability 进入 `EpisodeMetrics.to_dict()` JSON、episode CSV 的三项独立 status 列、统一
`metric_availability`、batch summary/Markdown。main-bus loader 会把“值为零但声明 unavailable”
归一为 `None`；replay/execution merge 保留 `id_switch_count` 字段但不会把旧默认零升级为证据；
reporting 也不再把显式 unavailable 的非空旧值计入统计。

2026-07-14 使用 5 个确定性场景验收：空输入、仅匿名 track、不完整 truth sidecar、完整
truth 且零切换、完整 truth 且有切换。seed 不适用；接受标准为前两类三项全 unavailable，
不完整 sidecar 不产生 RMSE/continuity 假零但已配对 identity 的 IDSW 为 available `0`，完整
稳定/切换场景的 IDSW 分别为 available `0/1`，且 JSON/CSV/Markdown/merge 状态一致。实际
结果全部通过；D6 全量 `137 passed`，1 条既有 matplotlib `Axes3D` 环境 warning。本轮未运行
AirSim。真实 multi-seed 的 seed/config/schema/hash provenance 完整性，以及按 episode clock、
`global_track_id`、plan/version 连接 D2 lifecycle 与 D3 churn 的 join，仍是 P1。

## 2026-07-14 第二批 D3 canonical ordered history

`P1SystemEvidenceReportGenerator` 已正式消费 main 写盘的 `d3_plan_history.json`：wrapper
schema 为 `d3_plan_history_v1`，每条 record schema 为
`d3_plan_history_record_v1`。D6 不导入 D3 或 main，只读取该 JSON 文件。

canonical history 只有在以下校验全部通过时才进入计算：至少 2 条记录；顶层
`record_count` 与实际长度一致；`sequence_index` 为非负整数、唯一且严格递增；
`ordering_key=[sequence_index,timestamp]` 一致、唯一且严格递增；timestamp 有限且不倒退；
每条 record 的 schema/version、plan、assignment、coalition、hysteresis、feedback 和 owner
字段满足冻结结构；record 不含 truth 字段。失败时所有 history-derived 指标保持
`unavailable`，原因写入 `d3_history_validation_reasons`，不会输出假零。

新增或正式接入的字段包括：

- `d3_history_record_count`、`d3_history_validation_status/reasons`；
- `plan_version_churn_count`、`coalition_version_churn_count`、
  `coalition_epoch_churn_count`；
- `membership_change_count`、`primary_membership_change_count`、
  `reserve_membership_change_count`；
- `owner_change_count`、`soft_feedback_count`、`hard_feedback_count`。

membership 按相邻 tick 的 `(target_id, resource_id) -> (role, activation_state, active)` 状态
变化计数，不累加 `membership_change_records` 审计事件。primary/reserve 分项按变化前后涉及的
角色归类；同一成员从 primary 改为 reserve 会同时进入两个分项，但总体只计一次。owner 按
`(active_plan_owner, owner_node_id)` 相邻变化计数；feedback 汇总各 tick 显式
`soft_count/hard_count`。coalition version/epoch 对相邻 coalition ID 映射的变化、出现或消失
计数。

CLI 调用可使用：

```bash
python3 research_modules/d6_evaluation_metrics/scripts/run_p1_system_evidence_report.py \
  --d3-plan-history /path/to/episode/d3_plan_history.json \
  --output-dir /path/to/d6_p1_system_evidence
```

Python API 继续使用
`P1SystemEvidenceInputs(d3_assignment_churn=Path(".../d3_plan_history.json"))`。旧
`--d3-churn-summary` 参数仍兼容。旧 snapshot/cooperative-role 输入也保持兼容；证据不足时
churn 仍为 unavailable。

2026-07-14 验证覆盖稳定零、版本变化、primary/reserve 与 activation 变化、owner 切换、
soft/hard feedback、乱序、重复索引、timestamp 倒退、单记录、schema/record_count/order key
错误、缺少 required field 和无 truth 字段。专项 `24 passed`，D6 全量 `132 passed`，另有 1 条本机 matplotlib
`Axes3D` 环境 warning。本轮未启动 AirSim、未形成新的物理性能结论。剩余 P1 是用真实
multi-seed episode 持续形成跨提交趋势和稳定 failure taxonomy；P2 optional benchmark
状态不变。

以下第一批 P0 修复及 2026-07-13 更早章节均为历史记录，不覆盖本节当前状态和测试计数。

## 2026-07-14 第一批 D3 churn availability P0 修复（历史）

`P1SystemEvidenceReportGenerator` 不再把 D3 最终快照、空 mapping 或单条无序记录解释为
“没有发生变化”。`plan_version_churn_count`、`coalition_version_churn_count`、
`coalition_epoch_churn_count` 和 `membership_change_count` 仅在以下条件之一成立时可用：

- producer 显式写出对应 count；显式 `0` 是 available 的有效证据；
- 至少两条记录具有顺序语义，且该指标所需的 version/epoch 或 membership change 证据完整。

有序历史中的稳定同值才计算为 available `0`。`plans/history` 序列保留其历史顺序；通用
`rows/records` 必须具有统一且唯一的 sequence/index/timestamp 字段。coalition 指标还要求
每条历史记录提供同一 coalition 的 version/epoch，membership 指标要求每条记录显式提供
`membership_change_records` 或 `membership_change_count`。证据不完整时 CSV 留空，JSON 和
availability 为 `unavailable`。

2026-07-14 回归覆盖 5 类输入：最终快照、空 mapping、单条无序记录、两条稳定有序历史、
顶层显式零。前三类四项 churn 均为 unavailable；后两类四项均为 available `0`。正式
40-case cooperative-role fixture 仍只统计 `active_primary/member_role`，四项 churn 保持
unavailable。验收结果为专项 `12 passed`、D6 全量 `120 passed`，另有 1 条本机 matplotlib
`Axes3D` 环境 warning。当前 P0 已闭合；剩余 P1 是上游 D3 真实有序 plan history/provenance、
长期 multi-seed 趋势和跨批次失败原因治理。P2 optional benchmark 状态不变。

以下 2026-07-13 及更早章节是历史实现与实验快照，不覆盖本节当前结论和测试计数。

## 2026-07-13 M5N2 cooperative closure 统一入口适配

`P1SystemEvidenceReportGenerator` 可直接被动消费 main 写出的原始
`p1_cooperative_closure_summary.json`，包括顶层 `cases/pair_rows/aggregates`；也可消费
`CooperativeClosureReportGenerator` 修正后的
`d6-cooperative-closure-v2/cooperative_closure_aggregate.json`。两种输入不需要改写为
`summaries/rows/records`，缺失值继续保持 `unavailable`。

- D3：原始 schema 仅从 40 个 case 的显式 `active_primary/member_role` 统计角色，计划与联盟 churn 没有时序证据时不推断。
- D5：active-primary 的 `visible/associated/common_lock` 分开统计。该 AirSim schema 的 `associated` 由 `d5_decision_state=locked` 生成，因此可同时进入独立锁定计数；reserve 行只进入安全审计。
- D7：active-primary 的 contract/control/mode/physical 四层逐层消费，profile aggregate 单独提供 case、pair、coalition opportunity/completion；reserve unauthorized 和 online truth 使用单独审计。
- 修正 aggregate 没有逐 pair 行时，报告从 `funnels.pair`、`common_lock`、`primary_source.aggregates` 和 `acceptance.checks` 恢复聚合证据，不伪造 seed、资源规模或逐 pair 明细。

固定 40-case fixture 的结果为：4 个 profile、每 profile 10 seed，最佳 profile
`d3-p1-h020.0-w03.0-s040.0` 完成 `5/10`，总体 coalition 完成 `8/40`；reserve
unauthorized、global ID rewrite、online truth use 均为 0。D7 四层 active-primary 合计为
contract 35、control 7、mode 9、physical 62。完整 D6 回归为 `115 passed`。

## 2026-07-12 D1/D2 dense-crossing 离线评估

新增 `DenseCrossingEvaluationReportGenerator`，离线消费 D1 governed replay manifest、独立 offline truth summary，以及 D2 的 10-seed screening 和 20-seed confirmation。报告固定分开 `gnn_baseline`、最佳 `gnn_candidate` 和 `lightweight_jpda`；FilterPy/Stone Soup object adapter smoke 只进入排除审计，不进入身份指标排名或晋级结论。

逐 seed CSV 和聚合 JSON/中文 Markdown/PNG 覆盖显式 availability-aware 的 IDSW、identity/coverage continuity、false track、RMSE、NIS/NEES、初始化延迟、p95 loop latency 和 truth leakage。D2 当前 calibration 行只提供 NIS/NEES availability 时，D6 将均值标为 unavailable，不从 RMSE 或 availability count 推导数值。

该独立 `d6-dense-crossing-evaluation/v1` 报告器历史上使用至少 20 seeds 的 confirmation，并检查 IDSW 相对下降 30%、identity continuity 绝对提高 0.10、false track 不超过基线 110%、p95 loop latency 预算和 truth leakage。该 `+0.10` 只属于历史 D6 v1 对照，已弃用作 D2 v2 准入判决。当前 `P1SystemEvidenceReportGenerator` 不重新计算或覆盖 D2 判决，而是兼容读取 D2 v2 的 ceiling-aware headroom/error-reduction gate 和 legacy checks；轻量 JPDA 的任何通过结果仍只是隔离候选评审，不直接替换默认 GNN。

```bash
python3 research_modules/d6_evaluation_metrics/scripts/run_dense_crossing_evaluation.py \
  --d1-manifest /path/to/manifest.json \
  --d1-offline-truth-summary /path/to/summary.json \
  --d2-screening /path/to/d2_identity_calibration.json \
  --d2-confirmation /path/to/d2_identity_calibration.json \
  --output-dir /path/to/d6_dense_crossing
```

当 screening/confirmation 位于同一个 D2 calibration 文件时，两个参数可指向同一路径；历史 dense-crossing v1 报告器仍读取原 stage/JPDA comparison。统一 system-evidence v2 另行兼容 `d2-p1-identity-calibration/v2` 的 `gates`、structured checks 和 bool checks，并保留缺字段的 unavailable 状态。

## 2026-07-12 cooperative-closure-v2 离线报告

D6 新增 `CooperativeClosureReportGenerator`，用于消费 main 的通用资源-目标行记录，并可选叠加 D3 candidate、D4 communication、D5 visibility、D7 guidance summary。该报告器只读写盘证据，不导入在线控制模块，不向分配、降级、视觉关联或导引回写结果。

输入支持 JSON、JSONL、CSV、mapping/dataclass 序列。输出固定为逐 seed CSV、聚合 JSON、中文 Markdown 和 PNG。pair/target/coalition 使用独立分母；target/coalition 只有在全部 active primary 具备显式证据时才进入相应阶段分母，reserve 不进入预期完成分母。共同锁定必须由 D5/main 提供 `common_lock` 同窗证据，不能用普通 `associated` 代替。

验收检查为 coalition 至少 10 个有效 seed 且完成率不低于 0.8、reserve unauthorized 为 0、global track ID rewrite 为 0、online truth use 为 0。任一证据缺失时结论为 unavailable；结果始终为 advisory-only。

D4 communication 输入兼容真实 `CommunicationFaultReplayReport` dataclass/`to_dict()` JSON：顶层优先读取 `cases` 而不是整数 `seeds`，并在 D4 专用归一化层映射 `scenario_id -> communication_fault`、`passed -> communication_passed`。`fail_closed` 保持原字段独立统计，不由 `passed` 推断。

2026-07-13 使用真实 M5N2 40-case summary 复核后，验收聚合固定为“按 `profile` 分组、每个 profile 按唯一 `seed` 计数”。`case_id` 只保留逐 case/seed 审计，不能进入验收分组键。联盟成员按稳定 `coalition_id` 合并；滚动计划中的 coalition version/epoch 仅作 provenance，不能把同一联盟拆成多个单成员单位。只有至少两个 active primary 的目标才进入 coalition 分母，普通单 primary 目标不计为联盟。

profile 选择优先采用 source summary 的 `best_candidate_profile`；缺少该声明时，才按“通过 seed 数、完成率、available seed 数、profile 名稳定排序”选择。真实 40-case fixture 的 source 最佳 profile 为 `d3-p1-h020.0-w03.0-s040.0`，D6 修正后得到 `5/10`，验收状态为 available 且 failed；四个 profile 的完成数依次为 `0/10、5/10、2/10、1/10`，与 source aggregates 一致。`unavailable` seed 单独报告，绝不按 0 或失败补入。

```bash
python3 research_modules/d6_evaluation_metrics/scripts/run_cooperative_closure_report.py \
  --rows /path/to/cooperative_rows.jsonl \
  --d3-candidate /path/to/d3_summary.json \
  --d4-communication /path/to/d4_summary.json \
  --d5-visibility /path/to/d5_summary.json \
  --d7-guidance /path/to/d7_summary.json \
  --output-dir /path/to/d6_cooperative_closure
```

## 2026-07-12 P1 第二批统一验收

新增 `P1AcceptanceReportGenerator` 和命令行入口 `scripts/run_p1_acceptance_report.py`。该入口可离线消费 main 的 `p1_terminal_closure_summary.json`，以及 D1 长 replay、D2 多 seed 关联、D3 分配矩阵、D4 failover matrix、D5 visual readiness 和 D7 dropout/`png_ttc`/trend coast summary。输入既可为 JSON 路径，也可由 Python API 直接传入 mapping 或各模块 dataclass/report 对象。

输出固定为逐 seed/source CSV、聚合 JSON、中文 Markdown 和 PNG 概览图。四层 `contract_allowed/control_allowed/mode_switched/physical_intercept` 只接受同名证据；pair/target/coalition 使用独立分母。旧输出缺字段时 CSV 留空、JSON 为 `null/unavailable`，不会从 terminal switch、pair success 或其他近似字段回填。

```bash
python3 research_modules/d6_evaluation_metrics/scripts/run_p1_acceptance_report.py \
  --output-dir /tmp/msm_p1_acceptance \
  --main-summary <p1_terminal_closure_summary.json> \
  --d1-summary <d1_long_replay_summary.json> \
  --d2-summary <d2_long_replay_calibration.json> \
  --d3-summary <d3_assignment_calibration.json> \
  --d4-summary <d4_failover_matrix.json>
```

D5 和 D7 三类 summary 可通过对应可选参数继续加入。未提供来源会保留在 `source_manifest` 并标为 unavailable。D6 不运行这些 producer，也不控制 AirSim。

独立 D7 summary 未提供时，D6 会从版本化 main terminal-closure summary 做保守回退：`acceptance.dropout_matrix` 转为 1-5 帧矩阵，`rows[family=png_ttc]` 汇总四类显式拒绝计数，M5N2 candidate 行的 `terminal_trend_coast_count` 汇总实际触发。独立 D7 summary 始终优先；回退结果带 `derived_from=main_terminal_closure`。四层执行指标仍只读取每行同名字段，不从这些专项字段推断。

真实 smoke `p1_terminal_closure_smoke_v2_20260712` 已重跑：dropout 1-5 帧 matrix complete/all compliant 均为 true；`png_ttc` 有 1 个 seed，not-expanding 拒绝 1 次，其余三类为 0；trend coast 实际触发 0，保持不建议晋级。当前 main 文件尚未包含四层同名字段，因此四层正确显示 unavailable。

## 2026-07-12 D7 PNG Delivery 被动评估

D6 已增加 availability-aware 的 D7 终端 delivery 评估。离线 loader 可消费 `terminal_filter_state/reason`、innovation reject/reset、TTC area jump/bbox clipping/not-expanding/out-of-range、soft prediction/coast 状态与 elapsed time、terminal lock、visual mode、速度命令和显式 `terminal_delivery_profile/comparison_role`。旧日志缺少字段时对应指标为 `None/unavailable`，不会记为零。

新增指标覆盖滤波 measured/predicted/innovation-rejected/reset/expired，TTC 四类拒绝，soft prediction/coast 次数、持续时间和到期，terminal lock continuity、visual mode duration 以及 command discontinuity mean/max。既有 `contract_allowed/control_allowed/mode_switched/physical_intercept` 四层和 pair/target/coalition 三层物理结果保持独立。

`ReportGenerator.write_terminal_delivery_comparison_bundle()` 输出逐 episode CSV、聚合 JSON 和中文 Markdown，按显式 profile、scope、scenario 和实际 `resource_count/target_count/camera_count` 分组；2v2 与 M5N2 不合并，M5N2 的 target success、active-primary pair success 和 coalition completion 不互相回填。D6 仍只读日志，不参与 D7 控制。

2026-07-12 实际对照包包含 26 个 episode、4 个独立分组：2v2 baseline/candidate 各 10 seeds，pair/target success 分别为 `19/20`、`20/20`；M5N2 35 s baseline 为 target `6/6`、active-primary pair `6/9`、coalition `0/3`，8 s candidate 为 active pair `0/9`。M5N2 两批几何和窗口不等价，仍需同条件 paired 验收。四层 logging smoke 为 `contract_allowed=4/36`、`control_allowed=2/36`、`mode_switched=5`、`physical_intercept=2/2`；旧日志缺列时保持 NA。该 D7 专项当时回归为 `84 passed`；加入本轮 P1 统一验收和 main-summary fallback 后，D6 当前回归为 `88 passed`，仍有 1 条本机 matplotlib `Axes3D` warning。

## 2026-07-11 P1 统一验收与 P2 adapter

D6 已消费 main episode bus 的 `d4_coalition_commit_state`，并从事件或扩展 `CoalitionRecord` 聚合 epoch、plan/coalition version、lease、required/acked members、commit state/reason、ACK latency、timeout、aborted/reconfiguring 以及 secondary/distributed commit。相同 generation 的 `committed -> executing` 转换只计一次有效 commit，状态与原因保留在 metadata audit。

终端验收现显式分为 `contract_allowed`、`control_allowed`、`mode_switched` 和 `physical_intercept`。`physical_intercept_count` 只接受通过 provenance gate 的 persisted pair scorer result；intercept summary、command/status 或 ComputerVision `d7_guidance_record` 均不能单独晋升 physical availability。physical 层进一步拆成 `pair_physical_success_count/rate`、`target_intercept_success_count/rate` 和 `coalition_completion_count/rate`：pair 分母只含 active assigned pair，target 以任一 participating pair 成功为准，coalition 必须有显式分母、全部 persisted required primary、arrival window 与可判定 completion，三者不共用分母。`collision_intercept/range_intercept` 是规范成功终态，`timeout/aborted` 是规范失败终态；证据完整的失败输出 available `0`。

`intercept_summary.json` 的物理判据审计保留 `intercept_radius_m`、`intercept_distance_frame`、`intercept_distance_dimension` 和 `intercept_success_criteria_version`；当前 5 m 验收要求 NED 3D Euclidean。缺 required-primary arrival window 时 coalition 指标为 unavailable，不用 pair/target 成功回填。detect/coast 诊断新增 `detection_acquisition_timeout_count`、`image_kf_predict_count`、`blind_push_count`、`visual_reacquisition_count`、`terminal_visual_lost_after_coast_count`、`truth_identity_online_use_count`，只读取 summary/control record 或从带明确 detect/coast 状态的逐 pair 时序离线推导。

隔离式 P2 `py-motmetrics` adapter 已实现冻结 `msm-offline-mot-v1` schema，输出 IDF1/MOTA/MOTP。HOTA 在 `motmetrics 1.4.0` 中不受支持，固定输出 `None/unavailable`；可选依赖缺失时同时输出兼容 `reason` 和显式 `unavailable_reason`。依赖只在 `/home/linux/.cache/msm-p2-venv` 验证，默认 requirements 和默认测试依赖不变；offline truth 禁止回流在线链路。

## 2026-07-11 M 对 N 离线指标合同

当日实测基线来自 `p1_p2_validation_20260711`：CV 10 seeds 中 8/10 形成 T001 双 primary 同帧共识与授权证据，全部 seed 的 IDSW 和错误重复锁为 0；secondary 与 distributed 正例均为 executing 3/3，missing-ACK 负例为 aborted 2/3。CV 的 `control_allowed_count=0`、`physical_intercept_count=None` 正确表示未执行物理控制。SimpleFlight 10 seeds 均保持 4 bindings、3 active + 1 standby，但 30 个 active pair 中 0 命中，包含 24 detection timeout 和 6 timeout；15 s、`control_dt=0.5 s` 仅为诊断配置。

D6 已实现中心化 M 对 N 的兼容日志与离线聚合。新增 `TargetDemandRecord`、`CoalitionRecord`、`ArrivalRecord`，并在 `AssignmentRecord`、`TerminalRecord` 保留 `coordination_mode`、`coalition_id/version/state`、`member_role`、`wave_id`、`required_resource_count`、`demand_assigned/shortfall/complete`、arrival window 和 `minimum_member_separation`。标准 JSONL 支持 `target_demand/coalition/arrival`，collector writer 可 round-trip；旧日志缺少这些字段时只对 duplicate 判定使用明确的 legacy `k=1`，其余新增指标保持 `null/unavailable`。

`EpisodeMetrics` 已接入 demand micro/macro、unmet slots、over-support、formation/reconfiguration、simultaneous arrival/common-window、sequential wave、hybrid primary/reserve、planned/authorized/erroneous lock、same-resource lock continuity、member lifecycle/digest/stale、messages/bytes/rounds/latency、minimum separation/collision exposure、geometry rejection、canonical duplicate/cross-node IDSW/common-information rejection。`duplicate_terminal_lock_count` 保留通用“同一 timestamp+target 出现多个 resource”计数，不再由 `erroneous_duplicate_lock_count` 覆盖；后者仅计 legacy `k=1`、当前 coalition/assignment 版本冲突或超过 `required_resource_count`。同一 resource 跨帧持续锁定只进入 `same_resource_lock_continuity_count`，授权 coalition 内同帧多资源锁进入 `authorized_cooperative_lock_count`。

探测三项要求同时存在 `truth_timestamps` 机会集合与检测/航迹到 truth 的离线配对裁决。配对证据可以是落入 truth pair 集合的 `TrackRecord.truth_id`，也可以是显式 `offline_detection_match/offline_track_truth_match/offline_detection_miss/offline_missed_detection` 事件。仅有 truth opportunity 列表、所有 track 均为 `truth_id=None` 且无显式 match/miss 时，`detection_probability/missed_detection_rate/false_alarm_rate=None` 且 `metric_availability.status=unavailable`。可用时按 pair 集合求命中和漏检；`truth_id=None` 的 center track 不自动计虚警。

`center_replan_request_created/deduplicated/ack_no_change/applied/expired` 已接入请求、去重、no-change、applied、expired、pending dwell 总时长和 no-change/applied 收敛均值。D6 优先消费 `request_id/requested_at/resolved_at/pending_dwell_s`，并在 metadata 审计保留 target、coalition/version、risk signature 和 resolved plan/version。无这些事件时所有 replan 指标为 `None/unavailable`。

每个新增指标在通用 `metric_availability` 中记录 `status/reason/numerator/denominator`，M 对 N 子集继续保留兼容的 `m_to_n_metric_availability`。数值 `0` 仅表示证据完整且事件确为零；缺证据为 JSON/CSV 空值和 `unavailable`；路线无此概念为 `not_applicable`。batch summary 分别输出可用、unavailable 和 not-applicable 样本数，并继续按实际 `drone_count/resource_count/target_count/camera_count` 分组。

## 2026-07-10 P1 扩展

本轮已补齐以下离线评估接口，不运行 AirSim：

- 二级接管生命周期：统计 `registration_usable`、`takeover_ready`、`pending_secondary_plan`、`secondary_plan_active` 驻留时间、ready-to-active latency、fallback、lease expiry 和 stale-plan reject。没有显式 lifecycle event 时字段为 `None/unavailable`，不写成 0。
- D5 YOLO/MOT：统计 detection recall、local-ID continuity、cross-view registration rate、pipeline latency、CPU/GPU budget utilization 和 budget violation。recall/continuity 只读取事件中嵌套的 `offline_truth`；在线顶层出现 `truth_id/actor_name/object_name/segmentation_id` 会计入 `online_truth_field_violation_count`。
- 四导引律同 seed 对照：`GuidanceLawComparisonReportGenerator` 对 `pure_pursuit/radar_pn/png_vm/png_ttc` 按相同 `scenario_group/version/seed/actual scale` 配对，输出 CSV、JSON、中文 Markdown 和差值曲线。D6 不选择导引律。
- 场景库：`ScenarioLibrary` 输出带 tags、difficulty、expected failure modes、parameters 和 seed matrix 的 JSON/CSV/Markdown；`scenario_group` 保持跨 seed 稳定，在线 truth policy 固定为 `forbidden`。
- `ReportGenerator.write_plots()` 新增 `visual_perception_metrics.png`；AirSim calibration record/cross-seed 表同步携带 lifecycle、视觉预算、tracker backend 和 experiment guidance law。

main 需要按事件写盘以下字段：

```text
d4_secondary_readiness:
  timestamp, readiness_state
d4_secondary_plan_state:
  timestamp, plan_state, plan_id, plan_version, owner, lease_id, lease_expiry_timestamp
secondary_takeover_fallback / secondary_lease_expired / stale_plan_reject:
  timestamp, reason, plan_id, plan_version, owner
d5_yolo_mot_frame:
  timestamp, camera_id, detection_backend, tracker_backend,
  cross_view_candidate_count, cross_view_registered_count,
  detector_latency_ms, tracker_latency_ms, pipeline_latency_ms,
  cpu_budget_utilization, gpu_budget_utilization,
  latency_budget_ms, cpu_budget_utilization_limit, gpu_budget_utilization_limit,
  offline_truth.{visible_truth_count,matched_truth_count,truth_to_local_track_id}
episode metadata:
  experiment_guidance_law, scenario_group, scenario_version, seed,
  drone_count, resource_count, target_count, camera_count
```

## 当前能力

已实现的核心数据模型：

- `EpisodeMetrics`：单 episode 标量指标对象，包含 `mission_outcome`、`success_reason`、`failure_reason`、`eval_priority`、`implementation_status`、`evidence_path`、`scenario_version`、`standard_mapping_version`、`standard_metric_family_summary`、`metric_scope` 和规模字段 `drone_count/resource_count/target_count/camera_count`。
- `TrackRecord`：探测和跟踪记录，保留 `global_track_id`、`truth_id`、位置、真值位置、协方差摘要和来源。
- `AssignmentRecord`：分配快照，保留 `plan_id`、`version`、资源、目标、授权状态和评估侧真值标签。
- `EventRecord`：通用事件记录，用于降级、安全、D5/D7 gate、通信元数据等。
- `LinkRecord`：跨节点通信记录，支持 latency/drop/out-of-order/stale/video metadata/bbox delivery。
- `TerminalRecord`：末端配准记录，支持局部视觉 ID、锁定、歧义、友方 overlap hold 和正确性标签。

已实现的指标族：

- 探测：`detection_probability`、`false_alarm_rate`、`missed_detection_rate`。
- 跟踪：`track_rmse`、`track_continuity`、强制显式保留的 `id_switch_count`。
- 分配：`duplicate_assignment_count`、`unassigned_high_threat_count`。
- 降级：`failover_time`、`consensus_rounds`、`degraded_completion_rate`、`active_degradation_count`、`active_degradation_precision`、`active_degradation_label_count`、`unnecessary_active_degradation_count`、`passive_failover_count`、`secondary_node_takeover_count`、`secondary_reassignment_count`、`d4_reassign_pending_count`、`distributed_fallback_count`、`failover_active_window_delta_s`。precision 只以可分类 review label 样本为分母；`active_degradation_label_count=0` 时输出 unavailable/JSON `null`，不伪装成 0 精度。
- 末端：`terminal_association_accuracy`、`terminal_id_switch_count`、`ambiguous_fov_event_count`、`friend_overlap_hold_count`、`time_to_terminal_lock`、`terminal_lock_count`、`multi_view_consensus_rate`、`cross_view_conflict_count`、`duplicate_terminal_lock_count`。
- 二级视角/侦察：`secondary_network_joint_full_view_frame_rate`、`secondary_network_mean_coverage_ratio`、`secondary_visible_target_union_ratio`、`secondary_single_camera_full_view_frame_rate`、`secondary_detect_count`、`projection_valid_rate`、`geometry_gate_pass_rate`、`registered_candidate_count`、`stable_cross_view_registration_count`、`not_registered_count`、`cross_view_association_count`、`secondary_detect_available_but_not_registered_count`、`cue_pointing_error_*`、`gimbal_pointing_error_*`。
- 通信：`cross_node_latency_ms`、`message_drop_rate`、`out_of_order_count`、`stale_track_update_count`、`video_metadata_delivery_rate`、`bbox_delivery_rate`、`consensus_latency_s`。
- D7 gate 与拦截统计：`camera_quality_gate_pass_rate`、`los_quality_gate_pass_rate`、`maneuver_margin_gate_pass_rate`、`terminal_switch_allowed_rate`、`visual_png_switch_count`、`terminal_takeover_rate`、`terminal_switch_reject_count`、`mode_switch_count`、`terminal_contract_reject_count`、四层 execution funnel、pair/target/coalition 三层 physical success、detect/coast 六项诊断、`collision_intercept_count`、`range_intercept_count`、`time_to_intercept_s`、`min_range_m`、`gate_reject_count`。
- 安全：`constraint_violation_count`、`human_override_count`。
- 任务结果/root cause：每个 episode 输出 `mission_outcome=success/partial/failed/aborted`、`success_reason`、`failure_reason`，metadata 保留 `root_cause`、`top_failure_causes`、`failure_cause_scores` 和 `failure_cause_details`；根因只从已写盘 records/metadata 和 D6 指标被动派生，覆盖 tracking、assignment、terminal_gate、guidance、coverage、runtime_exception、communication、safety、performance 等类别。
- 性能监测：`module_duration_ms`、`loop_latency_ms`、`record_latency_ms`、`cpu_budget_utilization`、`gpu_budget_utilization`、`performance_budget_violation_count` 进入 summary；metadata 保留 module/loop/record latency 分布和 CPU/GPU budget 占位状态。
- 标准化评估映射最小版：`cuas-standard-map-v1` 已把 `COURAGEOUS/MDPI/OCEF -> EpisodeMetrics` 映射落到 D6。映射字段为 `engineering_metric`、`standard_metric_family`、`standard_sources`、`implementation_status`、`evidence_requirement`，覆盖 mission/root cause、detection、tracking、assignment、degradation、terminal、communication、guidance/intercept、safety、performance、reproducibility/evidence。`MetricsCollector.compute_episode()` 在 metadata 中写入 `standard_mapping_version`、`standard_metric_families`、`scenario_version` 和 `standard_mapping` 摘要；`ReportGenerator.write_standard_mapping_csv()` 可输出 `standard_metric_mapping.csv`，Markdown 报告在 `EVAL Tracking` 后输出 `Standard C-UAS Mapping` 表。

D2/D6 的硬规则仍然保留：`id_switch_count` 必须显式输出，不能被综合准确率隐藏。

## 规模归一化

D6 按实际 `drone_count/resource_count/target_count/camera_count` 归一化和分组。规模优先来自 `truth_summary` 或 Blocks replay 的资源、目标和相机字段；缺失时才从已记录的资源、目标、终端和相机元数据推断。`2v2`、`5v5` 只作为 baseline 场景名，不能用于推断算法规模或报告分母。二级网络 full-view/coverage 和单相机 full-view 指标使用实际 target/camera count 或日志中显式记录的实际计数作为分母。报告会按 `metric_scope`、`seed`、`scenario_group` 和实际规模字段分组，区分 execution metrics 与 contract metrics。

## AirSim 与 Runtime 输入

D6 已有离线 loader，但不直接连接 AirSim：

- `load_blocks_replay_jsonl()` 读取 main runtime 写出的 `blocks_frames.jsonl` 和可选 `blocks_sensor_observations.jsonl`。
- `load_main_episode_bus_metrics()` / `load_main_episode_bus_metric_files()` 读取 main runtime 写出的 `main_episode_bus_metrics.json` 与 `main_episode_bus_contract_metrics.json`，还原为 `EpisodeMetrics`，保留 execution/contract 口径、seed/scenario/实际规模字段和 metadata 分布。
- `load_d4_active_degradation_decisions()` 读取 D4 主动降级 CSV，并离线消费 `review_label`、trigger/decision timestamp、selected coordinator、coverage cell 和 pre/post window 字段。
- `load_d7_intercept_outputs()` / `load_d7_guidance_timeseries()` 读取 D7 `control_commands.csv`、`intercept_summary.json`、`guidance_records.csv`、`guidance_summaries.json`。
- `load_episode_log_jsonl()` 读取 D6 标准化 dry-run JSONL。
- `load_airsim_calibration_records()` / `AirSimCalibrationReportGenerator` 自动扫描 main runtime 已写盘的 `d4d5_stress_metrics.json`、`airsim_blocks_summary.json` 和 `main_episode_bus/*.json`，保留旧的逐 seed `GROUP_FIELDS`/CSV，并新增去 seed、包含实际规模的 cross-seed aggregate。records 保留原始 `scenario_version`，统计键只移除其中 `seed1/seed2/...` 这类运行参数，防止真实多 seed 被拆成单样本组；baseline/enhanced 仍要求相同稳定 `scenario_group`、规范化版本、实际 `drone_count/resource_count/target_count/camera_count`、几何、detection backend 和 seed。case-specific `scenario/case_name` 只保留审计。active-degradation 显式标注优先读取 d4d5 stress metrics，再 fallback main `EpisodeMetrics`。

这些 loader 都是 file/offline-only。D6 已能消费 D4/D5/D7 写盘产物；D6 不拥有 live bus 订阅、AirSim 原生 recording 通用解析器或自动跨目录 episode 聚合调度。

截至 2026-07-10，main runtime 的 `--p1-calibration-sweep` 仍由 main 负责 AirSim 启动、settings 组合、reset-separated seeds/cases 和日志落盘。D6 bundle 保留 `airsim_calibration_records.csv`、`airsim_calibration_summary.csv`、`airsim_calibration_summary.json`、`airsim_calibration_report.md`，并新增 `airsim_calibration_cross_seed_aggregate.csv`、`airsim_calibration_paired_comparison.csv`、`airsim_calibration_aggregate.json`、`airsim_calibration_aggregate_report.md`。D6 只读取 main 已写盘目录，不参与 sweep 调度或场景控制。

配对统计中，`pair_count=1` 只标记为 `descriptive_only`，保留单次差值但不输出 bootstrap CI 或 Cohen's dz；至少两个有效 seed 对才标记 `available` 并运行固定 RNG 的 percentile bootstrap。缺 baseline/enhanced seed、指标不可用和零 review-label precision 都显式保留，不会按 0 或成功样本处理。

AirSim calibration record 和 cross-seed aggregate 现直接消费 execution/contract `EpisodeMetrics` 中的 `intercept_success_count`、`collision_intercept_count`、`range_intercept_count`、`min_range_m`、`time_to_intercept_s`、`visual_png_switch_count`、`terminal_switch_allowed_rate`、`terminal_takeover_rate`、`gate_reject_count`；`intercept_abort_count` 从各 scope 自己的 `metadata.intercept_status_counts` 派生。只有 episode 存在 `intercept_summary.json`、`control_commands.csv`、显式 intercept summary/pair/status，或正数 D7 control execution event count 时这些字段才可用；read-only episode 的 dataclass 默认零会转换为 `None/unavailable`。execution 与 contract 不合并。cross-seed 对计数指标输出 `sum`，对四类拦截 outcome 额外输出实际 `target_count` 累计得到的 `opportunity_count` 和 `rate`；距离、时间和比例只使用 mean/std/min/max，不把它们的跨 seed 求和解释为工程指标。`Interception Outcome` 只列有执行证据且 opportunity 可计算的行，scope 列明确区分 execution 与 contract。

截至 2026-07-07，main/orchestrator 已在真实 D7 AirSim 执行后把 `control_commands.csv` 与 `intercept_summary.json` 中的执行结果合并进正式 `main_episode_bus_metrics.json`，同时把执行前的合同检查口径保留为 `main_episode_bus_contract_metrics.json`。因此正式 episode 指标中的 `intercept_success_count`、`collision_intercept_count`、`range_intercept_count`、`terminal_contract_reject_count`、`guidance_law_counts` 等字段以执行后结果为准；raw contract metrics 只用于诊断 D3/D4/D5/D7 gate 合同。D6 通过 `metric_scope=execution/contract` 保留这两个口径，并在 CSV/Markdown 中分组展示。episode CSV 保留 metadata JSON；Markdown 在存在数据时输出 terminal switch/contract reject reason 分布。D6 仍只读取这些文件或由 main 写出的 metrics，不参与控制或重规划。

2026-07-10 对 `outputs/p1_gap_closure_2v2_smoke_20260710/episode_006_full_flow` 的复核表明：正式 execution 文件记录实际规模 `2/2/2/2`、`intercept_success_count=2`、`visual_png_switch_count=3`；contract 文件保持独立诊断口径。该 episode 的 `airsim_blocks_summary.integrated_result.metrics` 仍含执行前旧快照（规模 `3/3/2/0`）。D6 loader 明确以两个 `main_episode_bus` metrics 文件为准并忽略旧快照，且每个 calibration record 的 evidence path 指向其实际 execution/contract 文件；旧快照一致性需要 main runtime 单独修复，D6 不回写运行时文件。

同日使用 `p1_gap_closure_2v2_multiseed_20260710_seed001..010/blocks_sequence_summary.json` 验收：full-flow execution 聚合为 10 seeds、成功 `18/20`（0.9）、碰撞拦截 18、距离拦截 0、abort 2；`min_range_m` 均值约 1.812 m，`time_to_intercept_s` 均值约 3.66 s，visual PNG switch 合计 88，terminal switch allowed rate 均值约 0.0822，terminal takeover rate 均值 1.0，gate reject 合计 881。该结果证明 D6 可以直接从现有 summaries 生成多 seed 拦截结果，D6 未参与任何控制。

D6 现在也能离线汇总 main/D4/D5 已写盘的二级视角 metadata，并在报告中明确对比 `fixed_downlook_secondary` 与 `mobile_recon_gimbal`。该口径只消费覆盖、FOV、分辨率、cue source、cross-view association、D5 registration 和 cue/gimbal pointing error 字段；D6 不下发 cue、不控制云台、不参与接管或重分配。

P1 二级侦察 detect-to-registration 校准报告已经补齐分层漏斗字段：`secondary_detect_count`、`secondary_visible_target_union_ratio`、`secondary_network_joint_full_view_frame_rate`、`projection_valid_rate`、`geometry_gate_pass_rate`、`registered_candidate_count`、`stable_cross_view_registration_count` 和 `not_registered_count`。reject/outcome reason 统一保留 `not_all_targets_visible`、`network_union_incomplete`、`projection_invalid`、`geometry_gate_rejected`、`stability_window_failed`、`no_global_binding`、`stale_or_missing_recon_cue`、`registered_to_global_track`，缺失时按 0 输出，便于跨 seed 比较。

截至 2026-07-09，P1 AirSim calibration Markdown 进一步输出 50m vs 200m 二级覆盖对比、coverage funnel、Detect-to-registration funnel、baseline vs enhanced 对照、D7 guidance reject reason 和 Standard C-UAS Mapping。baseline/enhanced 只使用日志显式写出的 comparison role；D6 不从 `2v2/5v5` 场景名推断规模或对照组，不接 TrackEval、Stone Soup、SCRIMMAGE 等外部 evaluator。

截至 2026-07-08，`research_modules/airsim_runtime/outputs/p1_d4d5_mobile_recon_20260708_055948*` 是历史 mobile recon stress 批次，可作为 D6 已能消费 `mobile_recon_gimbal`、coverage、bbox、gimbal 和 funnel 字段的旧证据。

2026-07-08 registration calibration v2 历史基线位于 `research_modules/airsim_runtime/outputs/p1_d4d5_registration_calibration_runtime_v2_20260708*`。D6 bundle 已生成 `d6_airsim_calibration/airsim_calibration_records.csv`、`airsim_calibration_summary.csv`、`airsim_calibration_summary.json` 和 `airsim_calibration_report.md`。该 v2 批次为 single seed、3 case，height 200 m、FOV 110 deg、secondary_count 3；当时指标为 `projection_valid_rate=1.0`、`geometry_gate_pass_rate≈0.474`、stable cross-view registration 51/55/53、cross-view association 4/4/5、degradation case `not_registered_count=35/35`、full-view mean≈0.048、best≈0.143、coverage mean≈0.771。该历史批次证明 D6 报告链路能够输出 projection/gate/stable registration/not-registered/funnel/D7 reject，但不作为 2026-07-11 P1 当前结论。D6 仍只消费日志，不参与控制，也不从 `2v2/5v5` 场景名推断规模。

## 当前 P0/P1 状态（2026-07-12）

### 2026-07-11 四导引律短窗口实测证据

main 已修复 experiment-level guidance law 的执行后回灌，并从
`research_modules/airsim_runtime/outputs/p1_guidance_four_law_smoke_20260711/`
生成 D6 同 seed 对照产物。`guidance_same_seed_pairs.csv` 包含 21 条“候选导引律 x
指标”配对记录，但每条记录的 `pair_count=1`，实际只有 seed 7 一个独立 seed；不能把
21 条指标行解释为 21 次独立实验。

该 smoke 使用 2 秒短窗口，Pure Pursuit、Radar PN、PNG VM 和 PNG TTC 均 timeout，
拦截成功率均为 0。PNG VM/TTC 的 `terminal_switch_allowed_rate` 分别约为 0.762 和
0.810，最小距离分别约为 2.812 m 和 2.798 m。这些结果证明四律标签回灌、同 seed
配对、末端切换事件和距离指标能够被 D6 正确消费；它们不构成最终命中率、导引律优劣
或统计显著性结论。延长运行窗口并开展真实多 seed、同几何、同规模对照仍为 P1。

- P0：P0-A/P0-C 字段已补齐，当前没有新增运行级 P0 blocker。D6 输出 mission outcome、success/failure reason、top failure causes/root cause、性能监测字段、EVAL tracking schema 和 `cuas-standard-map-v1` 标准化评估映射最小版；仍保持离线消费日志，不参与控制；指标继续按实际规模归一化，不从 `5v5` 名称推断分母。
- P1 已闭合：coalition commit、`contract/control/switch/physical` 四层验收、pair/target/coalition 分层 physical success、detect/coast 和 PNG delivery availability-aware 指标及对照 bundle。CV T001 8/10、二级/分布式 commit、missing-ACK fail-closed 和 2v2 candidate `20/20` 非退化均有 evidence；自然 2v2 未触发 soft/trend，不宣称增强算法贡献。
- P1 仍开放：同一 z=-30 m、35 s 几何与同 seed 的 M5N2 paired baseline/candidate，独立 `png_ttc` 多 seed，1-5 帧 dropout 与 0.25 s fail-closed，trend coast 默认 profile 判定，以及既有完整标准化报告、场景库/CI 接线和长期真实 replay/review/window/阈值趋势。缺失字段继续为 unavailable，不得补 0。
- P2：py-motmetrics IDF1/MOTA/MOTP adapter 已作为冻结 replay 上的 optional benchmark 实现；TrackEval、Stone Soup、OSPA/GOSPA、HOTA 和非参数统计仍待实现。所有 P2 能力均不进入在线链路、默认依赖或控制决策。

## PNG 策略

PNG 截图不是 D6 计算指标的必需输入。D6 可用 bbox、相机内外参、timestamp、资源/相机 ID、`assigned_global_track_id`、object label、truth/validation label 和 D7 gate 结果计算多视角、末端和 visual PNG switch 指标。`--save-images` 只应在调试视角时启用；指标主线依赖 metadata。

## 文档

- 模块计划：`PLAN.md`
- AirSim 离线集成计划：`AIRSIM_INTEGRATION_PLAN.md`
- 详细算法与实施说明：`docs/ALGORITHM_AND_IMPLEMENTATION.md`
- 文档索引：`docs/README.md`
- 示例实验报告：`EXPERIMENT_REPORT.md`

## 运行测试

从仓库根目录运行：

```bash
pytest -q research_modules/d6_evaluation_metrics/tests
```

## 运行 100 Seed 示例

```bash
python3 research_modules/d6_evaluation_metrics/scripts/run_batch_example.py --seeds 100
```

默认输出：

```text
research_modules/d6_evaluation_metrics/outputs/example_batch/
  episode_metrics.csv
  summary_metrics.csv
  batch_report.md
  logs/*.jsonl
  plots/*.png
```

## 核心 API 示例

```python
from d6_evaluation_metrics import (
    AssignmentRecord,
    EventRecord,
    LinkRecord,
    MetricsCollector,
    ReportGenerator,
    TerminalRecord,
    TrackRecord,
)

collector = MetricsCollector()
collector.add_track(
    TrackRecord(
        timestamp=0.0,
        global_track_id="G0",
        truth_id="T0",
        position=(0.0, 0.0, -10.0),
        truth_position=(0.0, 0.0, -10.0),
    )
)
collector.add_event(EventRecord(timestamp=1.0, event_type="terminal_lock"))
collector.add_link(
    LinkRecord(
        timestamp=1.0,
        source_node_id="interceptor_01",
        target_node_id="center",
        payload_kind="track",
        sent_timestamp=0.9,
        received_timestamp=1.0,
    )
)
metrics = collector.compute_episode(episode_id="example", duration=10.0)
ReportGenerator().write_standard_mapping_csv("standard_metric_mapping.csv")
```

## 外部项状态

py-motmetrics 已有隔离 adapter、冻结 schema、available/unavailable 测试及 `motmetrics 1.4.0` 实际环境验证。Stone Soup metrics、TrackEval、OSPA/GOSPA/HOTA、AirSim 原生 recording replay 和 SCRIMMAGE metrics bridge仍没有实际 adapter；它们继续作为 P2/P3 可选项，不替代当前本地离线指标主线。

## P1 系统证据统一汇总（2026-07-13）

`P1SystemEvidenceReportGenerator` 新增一套不影响旧 `P1AcceptanceReportGenerator` 的版本化离线接口，统一消费以下已写盘证据：

- D1 dense crossing：冻结 replay 的 spacing/seed provenance、双时间戳、协方差、source lineage、观测接收/拒绝和在线 truth 隔离。
- D2 六难度 profile：逐 seed IDSW、continuity、false track、RMSE、P95 loop latency、admission 与 `scenario_still_non_discriminative`。
- D3：membership change/hold、plan version、coalition version/epoch churn，以及 `terminal_authorization_scope` 和 `arrival_coordination_required`。
- D4：逐 tick 或 fault-case 的 ACK、missing/rejected ACK、lease、epoch、owner、commit state、execution allowed、fail-closed 和失败原因。
- D5：per-primary 独立锁定/拒绝原因与 ByteTrack/BoT-SORT native active rate、IoU fallback、precision/recall、continuity、local IDSW、P95 latency、admitted/reasons。
- D7：兼容 per-seed summary 与 pair diagnostics，严格分离 `contract_allowed`、`control_allowed`、`mode_switched`、`physical_intercept`，并保留物理最近距离和失败漏斗。

所有指标都有独立 `*_availability`，缺字段不补零；每个文件保留 schema、路径、SHA256、producer/run 和 provenance。聚合数值按显式 seed 计算固定 RNG、2000 次 percentile bootstrap 95% CI，不足两个 seed 时 CI 为 unavailable。失败原因按来源和全局输出分布。D2/D5 的 truth 指标只消费离线聚合值，报告不导出 truth identity。D6 仍不启动 AirSim、不加载 YOLO/MOT 权重、不参与分配、接管或导引。

```bash
python3 research_modules/d6_evaluation_metrics/scripts/run_p1_system_evidence_report.py \
  --output-dir /tmp/d6-p1-system \
  --d1-dense-crossing-summary /path/to/d1.json \
  --d2-difficulty-summary /path/to/d2.json \
  --d3-churn-summary /path/to/d3.json \
  --d4-communication-summary /path/to/d4.json \
  --d5-per-primary-summary /path/to/d5_per_primary.json \
  --d5-native-mot-summary /path/to/d5.json \
  --d7-per-primary-summary /path/to/d7.json
```

输出固定为 `p1_system_evidence_rows.csv`、`p1_system_evidence_aggregate.json`、中文 `P1_SYSTEM_EVIDENCE_REPORT.md` 和 `p1_system_evidence_overview.png`。

## Replay 与执行指标合并（2026-07-13）

`merge_replay_with_execution_metrics()` 为 main 提供纯函数接口，用于合并
`integrated_replay/metrics.json` 与 `main_episode_bus_metrics.json`。终端配准、
cross-view、在线 truth 审计、合同/控制许可和物理拦截等执行指标，在 main bus 有明确
值时以 main bus 为规范值；被覆盖的 replay 原值和两侧 evidence availability 保留在
`execution_metric_provenance` 中。

```python
from d6_evaluation_metrics import merge_replay_with_execution_metrics

bundle = merge_replay_with_execution_metrics(
    replay_metrics,
    main_bus_execution_metrics,
    persisted_frame_count=11,
    warmup_inclusive_frame_count=12,
)
assert bundle["execution_metrics_merged"] is True
```

接口不把缺失值补成 `0`。`persisted_frame_count` 与
`warmup_inclusive_frame_count` 是独立证据，分别携带 availability 和 source；不能由
其中一个推导另一个。D6 只返回合并 bundle，写盘位置和 episode 调度仍由 main 负责。

## D2 准入 Schema 兼容（2026-07-15）

`P1SystemEvidenceReportGenerator` 输出升级为 `d6-p1-system-evidence-v2`，同时接受三类
D2 准入证据：v2 `gates`、legacy structured `checks` 和 legacy bool `checks`。失败解析
优先读取 v2 gate 自身的 `reason`，其次读取 `gate_reasons`；失败项始终保留 gate 名，
reason 缺失时写为 `gate_name:reason_unavailable`，不会生成空失败原因。

逐行 CSV、aggregate JSON 和中文 Markdown 现在保留 source-level decision、逐 difficulty
assessment、五项 gate outcome/reason、IDSW、连续率 baseline/headroom/actual/required/error
reduction、false-track、P95、truth leakage、promotion recommendation、默认路径状态和 truth
alignment。历史 artifact 缺字段时值为 `None`/CSV 空值且状态为 `unavailable`，绝不补 `0`。

2026-07-15 已消费正式冻结 replay
`../d2_data_association/outputs/p1_identity_ceiling_aware_v2_20260715/d2_identity_calibration_v2.json`，
在 `outputs/p1_identity_ceiling_aware_v2_20260715/` 生成 D2-only CSV、JSON、中文 Markdown 和 PNG。
总体 GNN 候选五 gate 全部通过，IDSW baseline/candidate=`1.3583/0.6167`，continuity
headroom/actual/required/error reduction=`0.018954/0.002908/0.001895/0.153448`；这只形成
`promotion_recommended=true` 的评审建议。分档仅 clutter/combined 通过，delayed_noisy、dropout、
nominal、tight_crossing 因 baseline IDSW=0 fail-closed。dropout truth alignment 在
screening/confirmation 为 `10/10`、`20/20` partial；JPDA research adapter 不准入；
`default_online_path_changed=false`，默认 GNN/Hungarian 未改变。其他六源均为 unavailable，
因此 `full_system_decision=not_evaluated`，不得宣称全系统通过。D6 不重算 D2 判决，不参与控制。

验证日期 2026-07-15：system-evidence 专项 `31 passed`，D6 全量 `243 passed`；本批未启动
AirSim，另有一条既有 Matplotlib `Axes3D` 环境 warning。
