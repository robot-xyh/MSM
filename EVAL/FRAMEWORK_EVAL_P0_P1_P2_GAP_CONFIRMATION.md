# 框架评估 P0/P1/P2 缺口确认

**文档版本**: v2.21
**更新日期**: 2026-07-15
**生成角色**: main agent
**定位**: EVAL 层跨模块优先级归并，不直接替代 D1-D7 owned GAP/PLAN。

v2.19 同步 2026-07-15 D4 公开 helper P0 复审：旧 `278/278` 回归未覆盖
`secondary_readiness_sustained/source/lease epoch=None` 的组合，两个公开 helper 可把
缺失证据解释为“非 False”并放行 active secondary plan。D4 owner 已改为 exact-true、
逐字段 fail-closed，并补齐 same-active-plan 和 distributed-peer 边界回归；D4 `280`、
AirSim runtime `147`、integrated point-mass `7` 均通过。本批未启动 AirSim。

v2.20 同步 D2/D6 ceiling-aware v2 正式联合证据：原冻结 replay 已重生成完整
false-track、P95、baseline/candidate truth leakage、逐 gate reason、逐 difficulty 和 dropout
truth-alignment 证据。总体 GNN 候选五项 gate 通过，但仅 `clutter/combined` 分档通过；
其余四档因 baseline IDSW 为零而 fail-closed，dropout truth alignment 为 partial，JPDA 不准入。
该结果只形成 promotion review，`selected_online_path=baseline_gnn_hungarian`、
`default_online_path_changed=false`。D6 全量 `243 passed`，本批未启动 AirSim。

v2.21 同步真实 M5N2 terminal/timing 批次：baseline 与 soft-prediction/trend-coast
candidate 各完成 10 seed，共 20/20 case 后按用户指令终止。TERM 生效前额外完成 1 个
`png_ttc_2v2_seed001`，但不纳入 M5N2 聚合或多 seed 验收；dropout 完成数为 0，任何缺失
case 都不补零。两组 active-primary/target/coalition 分别为
`6/30`、`6/20`、`0/10`，第二 primary 均为 `0/10` 进入 5 m；candidate 的逐 seed
non-degradation 为 false，因此保持 optional/default-off。20 个 actual artifact 全部 available，
identity/state online truth use 均为 0，无新增 P0。真实 pooled main-bus 与 control-tick
mean/P95 分别为 `349.34/487.40 ms` 与 `1069.45/1254.06 ms`，100 ms 预算违例率为
`95.90%/100%`；两层禁止相加。新增 P1 是第二 primary/联盟物理闭环、D1/AirSim/RPC
性能，以及 D6 对 reset-separated 多 episode timing 的版本化 envelope/manifest 支持。
第二 primary 七阶段漏斗为前四阶段 `20/20`、control/mode `17/20`、5 m physical `0/20`；
20 个最终 stop reason 均为 `collision_stop`，但碰撞对象/法向/成员环境距离未写盘。碰撞
provenance 和 canonical/cooperative target success 术语统一继续作为 P1，当前不能把失败
单独归因于视觉门限。
模块复核同时确认 D1 fusion 为 main-bus 主导耗时，D2 association 不是主要时序瓶颈且
truthless IDSW/continuity 保持 unavailable，D3 20 case 的实际 plan/member/owner churn 为 0，
D4 `active_degradation=0` 仅是中心负对照。各 owner 已将这些边界同步到模块 GAP/PLAN。

## 1. 输入材料

本次更新在原 8 份评估文档基础上，额外审读了 3 份 patch：

- `EVAL/FRAMEWORK_EVAL_PATCH_ENGINEERING_PRACTICES.md`
- `EVAL/FRAMEWORK_EVAL_PATCH_2026_VERIFIED.md`
- `EVAL/FRAMEWORK_EVAL_PATCH_WEBSEARCH_2026.md`

并同步了 2026-07-09 P1 接口补齐结果：

- `subagent_reviews/MAIN_IMPLEMENTATION_GAP_AUDIT.md`
- D1-D7 各模块 `subagent_reviews/Dx_IMPLEMENTATION_GAP_AUDIT.md`
- main runtime P1 smoke 输出：`research_modules/airsim_runtime/outputs/p1_gap_fix_smoke_20260709/`

v2.2 继续同步以下当前状态证据：

- `subagent_reviews/MAIN_IMPLEMENTATION_GAP_AUDIT.md` 的 2026-07-12 状态入口。
- D1-D7 当前 `PLAN.md` 与 `subagent_reviews/Dx_IMPLEMENTATION_GAP_AUDIT.md`。
- `research_modules/airsim_runtime/outputs/PNG_DELIVERY_ENHANCEMENT_AIRSIM_VALIDATION_REPORT_20260712.md`。
- `research_modules/airsim_runtime/outputs/png_delivery_enhancement_eval_20260712/` 的 D6 结构化对照。
- `research_modules/airsim_runtime/outputs/p1_terminal_closure_10seed_20260712/` 的 80-episode 同条件 M5N2、`png_ttc`、dropout 和 D1-D5/D6 统一证据。

v2.3 新增同步：

- `subagent_reviews/MAIN_P1_COOPERATIVE_AND_IDENTITY_CALIBRATION_REPORT_20260712.md`。
- `research_modules/airsim_runtime/outputs/p1_cooperative_closure_v2_contractfix_smoke_20260712/` 的四组 M5N2 cooperative smoke。
- `research_modules/airsim_runtime/outputs/p1_sparse_binding_owner_smoke_20260712/` 的 owner/version 保持专项。
- `research_modules/airsim_runtime/outputs/p1_identity_dense_crossing_cv20_20260712/` 的真实 CV 20-seed D1/D2/D6 标定。

v2.4 新增同步代码状态：

- cooperative terminal 改为 active primary 独立授权，不再要求同时到达；reserve 保持 standby。
- D3 纯成本/诊断重评不再推进 plan id/version/coalition epoch。
- D4 episode communication 已接入 AirSim frame clock，并对 ownerless/partition/reconfiguring fail-closed。
- D5 ByteTrack/BoT-SORT 原生准入和 post-online truth 评分已接入 main；IoU fallback 不可准入。
- D2 六 difficulty profile 已实现真实受控观测变换，2 m tight geometry 必须来自真实 AirSim 捕获。
- D6 已提供 D2-D5/D7 统一 CSV/JSON/中文 Markdown/PNG 汇总接口。

v2.5 新增同步真实执行证据：

- 4 m/2 m strict dense crossing 各 20 seeds，共 40 个真实 AirSim episode；最佳 GNN 候选 IDSW 下降 54.6%，但 continuity 未达到冻结晋级门限。
- M5N2 `2 primary + 1 reserve` 共 40 个 SimpleFlight episode；最佳 profile coalition completion 为 `5/10`，总体 `8/40`，仍未达到 `8/10`。
- D4 六类 episode-time 通信/失效注入共 60/60 通过，false degradation 和 duplicate owner 均为 0。
- ByteTrack/BoT-SORT 18-case 原生 MOT 筛选完成；20 m 延时和 continuity 合格，但 precision/recall 仅约 0.26-0.33，30/50 m 无检测，0 个候选准入。
- D6 已修复 cooperative profile 分组并生成七类来源均 available 的统一 P1 报告；D3 缺失时序 churn 保持 unavailable。
- D1-D7 owner 已分别同步各自 PLAN/GAP；main 只维护本文件和总 GAP。P0/P1 状态以 2026-07-13 顶部权威段为准，文内更早测试计数均属于历史阶段证据。

v2.6 新增可信闭环复核：

- D1 AirSim 在线观测已匿名化，EO 使用 detection bbox；D2 在线策略对 truth 字段 fail-closed。
- D2/D6 在无 truth 配对时将 RMSE、continuity、IDSW 标记为 `unavailable`，不再填 0。
- D1 observation arrival queue 只在量测到达后更新融合状态，离线 integrated replay 显式使用 offline truth policy。
- 当时发现一个开放 P0：SimpleFlight 控制仍直接读取 actor truth 的位置/速度用于导引、距离门限和相机朝向。该代码缺口已由 v2.7 关闭；既有 `online_truth_use=0` 仍只覆盖身份标签，历史物理结果继续按迁移前 smoke 处理并等待同 seed 重跑。

v2.7 新增 P0 关闭证据：

- 默认、主动中心重规划和主动二级接管统一从 main episode bus 消费 D2 估计位置/速度、协方差、measurement timestamp 和 arrival timestamp。
- 主动降级 fixture 只覆盖 D3 plan/version、D4 permission 和 D5 lock，不再提供目标运动状态或 actor/object/mesh alias；目标重分配后按 canonical `global_track_id` 重新选择同帧 D2 estimate。
- 缺失/陈旧 estimate fail-closed；actor truth 仅保留给合成传感器、离线 pairing、轨迹图和 post-run NED 三维 5 m scorer。
- D6 分离 `truth_state_online_use_count` 与 `truth_identity_online_use_count`。本批代码级回归为 AirSim runtime 130、D1 83、D2 98、D3 全量通过（1 skipped）、D4 198、D5 235、D6 138、D7 178、integrated 7。
- 本批未运行新的真实 AirSim episode，因此代码级 P0 关闭，真实同 seed 物理结果重跑保持 P1 evidence task；历史结果不自动升级。

v2.8 新增 D6 physical provenance P0 关闭证据：

- physical 指标不再从 command rows 回退生成 pair；必须存在 intercept summary 和逐 pair summary。
- 每个参与 pair 必须显式携带 `physical_evidence_available=true`，且 `target_state_source` 必须与 episode 的 `online_control_state_source` 一致。
- command-only、summary-only、缺证据和来源冲突全部输出 `None/unavailable`；合法 offline scorer、显式 truth fixture 和 standby reserve 排除语义保持。
- 回归为 D6 `143 passed`、AirSim runtime `130 passed`、integrated point-mass `7 passed`；未运行新的真实 AirSim episode。

v2.9 新增 D4 lease 与 D6 physical completeness P0 关闭证据：

- D4 secondary resource、plan、active owner 和 D7 handoff 统一要求 expiry/current time 都存在且严格 `current_time < lease_expiry`；缺字段、边界相等、过期、旧 epoch 和 source mismatch 全部 fail-closed。
- D6 要求每个 active pair 除 provenance 外还必须存在可判定 physical result；required-primary 成员不足、缺 arrival window、缺 denominator 或 summary opportunity 缺 completion 时 coalition unavailable，完整显式失败仍为 available `0`。
- main/integrated 合法 fixture 已补 episode time、heartbeat、lease epoch/expiry，没有放宽 D4 安全合同。
- 回归为 D4 `211 passed`、D6 `150 passed`、D7 `178 passed`、AirSim runtime `130 passed`、integrated point-mass `7 passed`；未运行新的真实 AirSim episode。

v2.10 新增 D5 native MOT history P1 子缺口关闭证据：

- 原生 Ultralytics Results 的 camera-local tracker ID 现按 resource、camera、backend 和 native ID 累计连续实测命中，不再把每帧历史固定为 1。
- 空帧、ID/backend 切换、native model 重建、stream reset 和 episode reset 都中断稳定证据；短时 coast 不计入锁定历史。
- 没有降低 `min_mot_history`，没有放宽身份、重复锁定、版本、时间或标定门控，也没有改写 `global_track_id`。
- 回归为 D5 `241 passed`、AirSim runtime YOLO/MOT focused `10 passed`、runtime 全量 `130 passed`；真实图像多 seed 准入仍是 P1。

v2.11 新增 D1 covariance 与 D4 二级接管证据完整性 P0 关闭证据：

- D1 正式 online、governed replay 和 AirSim freeze 现在统一要求每条观测携带维度正确、有限、对称、半正定的 covariance；缺失或非法矩阵在滤波更新前 fail-closed，不再静默使用默认矩阵。
- 历史缺 covariance 数据只允许通过显式 offline legacy migration API 迁移。迁移记录必须携带原始缺失原因、sensor model/default、生成参数和 `offline_only` provenance，且禁止回流在线融合、在线 replay 或 AirSim freeze。
- D4 二级节点只有在 current time、heartbeat、cue freshness、gimbal、communication summary、network full-view 和严格 lease 证据完整且新鲜时才可达到 `takeover_ready`；任一字段缺失均输出明确拒绝原因并 fail-closed。
- main-owned 质点集成适配器补充显式二级视频/数据链摘要，不再依赖“缺通信默认可用”。中心健康、主动中心重规划、完整二级接管正例和二级失效后 distributed 顺序保持。
- 回归为 D1 `92 passed`、D4 `224 passed`、integrated point-mass/contracts `10 passed`、AirSim runtime `134 passed`。本批未运行新的真实 AirSim episode；真实网络时序、多 seed covariance consistency 和二级接管实测仍为 P1。

v2.12 新增第二批 P1 代码闭合与 main runtime 接线：

- D3 已统一迟滞比较成本口径，并把 `max_changes_per_window` 改为同一窗口内的累计已执行变更预算；硬失效仍可 fail-closed 绕过预算。D3 回归 `157 passed, 1 skipped`，skip 仅为可选 OR-Tools 未安装。
- D5 已按 resource/target/local-track/camera/backend/stream 和 committed primary membership 累积 bbox/MOT 历史；普通 plan version 刷新不再清空，换绑、换员、身份/友方/重复冲突仍重置。D5 回归 `255 passed`。
- D7 已区分 raw terminal gate、visual latch、effective contract、effective control 和 termination snapshot，并细分 bounded prediction、contract reset、prediction window 和 measured-lock-not-established 丢帧原因；PN/PNG 核心公式未改。D7 回归 `181 passed`。
- D6 已用带 producer/scope/denominator/lifecycle 的 terminal metric envelope 隔离 planned-lock 与 execution 指标，接入 canonical D3 history、性能样本和 `inconclusive` 双零判读。D6 回归 `154 passed`。
- main runtime 已传递 D5 稳定相机/流/后端、当前可执行 primary 成员和 duplicate risk；D7 event 直接采用 canonical runtime record；SimpleFlight 终止行不再把历史 latch 计作当前授权；P1 bundle 自动生成 D6 suite/case 报告并携带 D3 history、D7 execution、physical context 和性能字段。AirSim runtime `140 passed`，integrated/dry-run `14 passed`。
- 本批仍未运行新的真实 AirSim。代码级 P0 继续无开放 blocker；真实同几何 10-seed M5N2/2v2/dropout 复跑、M5N2 第二 primary、D3 长期 churn、D5 30/50 m 召回/native-MOT 准入、二级真实网络时序和约 1.3 s loop latency 仍是开放 P1。

v2.13 新增 D6 actual-execution 计划来源 P0 关闭证据：

- 复核发现 formal actual-execution merge 会丢失实际 `plan_id/plan_version/owner`，导致中心重规划和二级接管虽已执行，正式 D6 指标却无法证明控制使用的计划来源。
- `d7-actual-execution-metrics-v2` 现在只从最终 `control_commands.csv` 提取计划 ID、正整数版本和 owner provenance，并校验 source hash、字段类型、同一计划版本一致性和 availability。integrated replay 不再作为回填来源。
- 计划 ID/版本逐行必需；二级或分布式有效控制行缺 owner 时 fail-closed。普通中心授权、未授权过渡和 pending 行可缺 owner，并将 owner provenance 显式标为 unavailable，而不是使无关 actual 指标失真。
- D6 回归 `184 passed`，AirSim runtime `142 passed`，P1 terminal/integrated/dry-run 组合 `17 passed`，`git diff --check` 通过。当前无开放运行级 P0。
- 本批没有运行真实 AirSim；历史产物不具备 v2 envelope，真实 seed-1 注册及同配置多 seed 仍是 P1 evidence。

v2.14 新增 canonical actual-execution 真实 AirSim P0 复验：

- tuned 2v2 seed-1 与 M5N2 seed-1 均生成通过结构、source hash、计划来源和物理计数校验的 `d7-actual-execution-metrics-v2`；两场景均无 unavailable artifact，identity/state online truth use 均为 0。
- 离线 5 m scorer 结果已精确同步到每个成功 pair 的一条最终 command row；2v2 的 summary/CSV/actual 均为 `2`，M5N2 均为 `2`，旧 `d7_actual_execution_command_physical_count_conflict` 未复现。
- 控制阶段和 finalize 阶段复用同一个 live `MainAirSimEpisodeBus`。两个场景中 command、actual metadata 与 canonical D3 history 的 plan ID 完全一致。
- direct run 的 canonical case 标识改为 `case_id > sequence_id > episode_id`，修复跨 sequence 聚合时两个 artifact 都名为 `episode_006_full_flow` 的冲突。D6 联合验收 actual available `2/2`。
- 回归为 AirSim runtime `142 passed`、terminal closure `7 passed`、D6 `216 passed`、D5 `261 passed`、D7 `188 passed`、integrated point-mass `7 passed`，`git diff --check` 通过。actual evidence P0 关闭。
- P1 仍开放：M5N2 active pair `2/3`、coalition `0/1`，第二 primary 最近约 `11.02 m`；2v2/M5N2 loop latency 约 `123.3/384.6 ms`；同配置多 seed、完整 dropout/candidate 矩阵及长期趋势尚未执行。actual v2 已独立注册 `terminal_switch_allowed_count`，并从最终 CSV 严格重算 freshness/stale。两例共 656 samples，mean/P95/max age=`0.0872/0.2/0.2 s`、stale=`0/656`、来源全部为 `d2_estimated_global_track`；该 seed-1 正式链路关闭，多 seed 分布仍为 P1。

v2.15 新增 actual target-state freshness/stale P1 证据链关闭：

- D6 只从 source-hash 已验证的最终 `control_commands.csv` 逐行消费控制时间、目标量测时间、到达时间、量测年龄、stale 和状态来源；缺列、空值、非有限值、负值、时间逆序、age 冲突、非法布尔或空来源全部 fail closed。
- 两个 required case 均 available：2v2 为 48 samples，mean/P95/max=`0.0375/0.2/0.2 s`；M5N2 为 608 samples，mean/P95/max=`0.091118/0.2/0.2 s`；stale 均为 0，来源均为 `d2_estimated_global_track`。
- case、pooled aggregate、CSV、JSON 和中文 Markdown 已接入 freshness/stale availability、年龄分布、stale 数量/比例和来源分布。D6 `216 passed`，D5/D7 文档同步分别 `261/188 passed`；完整 paired/dropout/multi-seed 和 100 ms 性能预算仍为 P1。

v2.16 新增 runtime 分阶段延迟可观测性 P1 实现闭合：

- main bus 新增 `main-stage-timing-v1`，按 frame 分离 communication、D1、D2、D6 track recording、D3、coalition commit、D5、D4、D7 和 link/cross-view recording，并写入 `main_episode_bus/stage_timings.jsonl`。
- SimpleFlight 外层新增 `control-tick-stage-timing-v1`，分离 AirSim frame sample、bus processing、control evidence/pair sync 和 guidance/control RPC，并写入 `control_tick_timings.jsonl`。外层包含 bus processing，两层禁止求和。
- 未执行阶段严格使用 `not_applicable + null`；异常保留部分计时；每条记录保存 total、measured sum、unattributed、budget 和 error。历史产物缺文件保持 unavailable，不从旧总耗时反推阶段。
- D6 新增严格离线 validator、分阶段 mean/P95/max、dominant stage、预算违例及 CSV/JSON/中文 Markdown/PNG 报告，并接入 `d6-p1-unified-acceptance-v5`。D6 `236 passed`，AirSim runtime `145 passed`，terminal/integrated `14 passed`。
- 真实 2v2/M5N2 seed-1 旧产物兼容报告均正确显示两层 `stage_timing_artifact_missing`。本批未启动 AirSim，100 ms 预算、真实 dominant stage 和优化后 multi-seed 复验仍为 P1。

v2.17 新增 D4 多入口二级接管 P0 复核与关闭：

- 复核发现 D4 核心仲裁、episode communication 和 main runtime 对二级 readiness 的要求不完全一致：heartbeat-only 曾可能被通信入口解释为可接管，缺 current time 的 D6 metadata 也可能错误保留 lease 可用语义。
- D4 owner 已建立统一 `SecondaryReadinessEvidence`/assessment。二级 owner 必须同时具备显式 current time、有效 epoch/lease、新鲜 heartbeat/cue/communication、gimbal、coverage、network full-view 和持续 readiness；缺失、陈旧或未持续均 fail-closed。
- main communication tick 只消费上一完整 D4 decision，避免使用当前帧尚未完成的仲裁结果；同一节点多条 readiness 的 lease epoch/expiry 冲突时整节点拒绝，不采用后写覆盖。
- heartbeat-only 负例、完整 readiness 正例和冲突 lease 负例均通过；回归为 D4 `278 passed`、AirSim runtime `147 passed`、integrated point-mass `7 passed`。本批未启动 AirSim；真实 RF、带宽、时钟漂移、排队、乱序、重传和 multi-seed failover time 仍为 P1。
- 同轮只读审计确认 D2 strict candidate 的 continuity 绝对提升 `0.10` 在 baseline=`0.9810` 时不可达。默认 GNN 因 fail-safe 未被错误替换，因此不是 P0；但准入规则必须由 D2/D6 改成 ceiling-aware、可复现且多指标联合的 P1 治理口径。

v2.18 新增 D2/D6 ceiling-aware 准入 P1 代码闭合：

- D2 将 continuity 规则升级为 `d2-p1-identity-admission/ceiling-aware-error-reduction-v1`。基线剩余空间为 `H=max(0,1-C_baseline)`，所需提升为 `min(0.10,0.10H)`；基线为 1.0 时只接受合法且不退化的候选。旧 `+0.10` 字段保留为 deprecated 审计信息，不参与 v2 判决。
- IDSW、continuity、false-track、P95 和 baseline/candidate truth leakage 仍是联合 fail-safe gate；仅 IDSW 改善不能晋级，任何通过只产生 promotion review，`default_online_path_changed=false`。
- D6 system evidence v2 同时兼容 D2 v2 gates、legacy structured checks 和 bool checks，并保留 policy version、headroom、实际/所需提升、误差消除比例、all-pass 和具体失败原因；历史缺字段保持 unavailable。
- `0.9810 -> 0.9840` 对应 headroom `0.0190`、所需 `0.0019`、实际 `0.0030`、误差消除约 `15.79%`，因此 continuity 单项通过；旧产物缺完整 false-track 和逐 gate v2 证据，不能追认完整 promotion review。
- 正式联合证据已由原冻结 replay 重生成。总体候选 IDSW `1.3583 -> 0.6167`、continuity `0.9810 -> 0.9840`、false-track `0 -> 0`、P95 `15.47 ms`、truth leakage `0`；只形成评审建议，不改变默认 GNN/Hungarian。回归为 D2 `113 passed`、D6 `243 passed`、AirSim runtime `147 passed`、integrated point-mass `7 passed`。本批未启动 AirSim。

仍然参考的原始评估材料：

- `EVAL/FRAMEWORK_EVAL_D1_SENSOR_FUSION.md`
- `EVAL/FRAMEWORK_EVAL_D2_DATA_ASSOCIATION.md`
- `EVAL/FRAMEWORK_EVAL_D3_ASSIGNMENT.md`
- `EVAL/FRAMEWORK_EVAL_D4_COORDINATION.md`
- `EVAL/FRAMEWORK_EVAL_D5_TERMINAL.md`
- `EVAL/FRAMEWORK_EVAL_D6_EVALUATION.md`
- `EVAL/FRAMEWORK_EVAL_D7_GUIDANCE.md`
- `EVAL/FRAMEWORK_EVAL_SYSTEM_INTEGRATION.md`

## 2. 总体判断

三个 patch 的共同结论是：项目当前轻量主线方向正确，但后续可信 AirSim 多 seed、封闭场地、分布式二级接管和真实视觉链路需要更强的工程化依据。

本轮确认：

1. **当前无开放运行级 P0 blocker**。SimpleFlight 默认、主动中心重规划和主动二级接管均已改接 D2 估计状态，actor truth 只进入离线 scorer；D4 二次审计发现并关闭公开 helper 对缺失 sustained readiness/source/lease epoch 的 fail-open，active secondary plan 现要求完整证据 exact-true，heartbeat-only、缺字段与冲突 lease 均 fail-closed。真实 AirSim multi-seed 仍是 P1 证据任务。
2. **不要把成熟外部工具本身等同为 P0**。例如 OR-Tools、etcd、ROS 2、MLflow、RTI Connext、Kalibr、Apollo Cyber RT 很有价值，但“立即集成这些完整框架”不是当前 P0。
3. **P0 应限定为最小可信闭环硬化项**：时间/配置/健康/异常、任务 outcome、根因诊断、FDIR-light、质量门控、分配迟滞、二级能力判断、终端重捕获、D7 切换迟滞/LOS 滤波、标准化评估映射。
4. **P1 是三个月内能力增强和标定**：标准对齐报告、OR-Tools 对照、JPDA/MHT 选型、Raft 选举对照、YOLO/MOT 多 seed 校准、IBVS/间歇可见性重捕获、3D True PN/APN 对照。
5. **P2 是较重架构升级或高阶算法**：ROS 2/DDS 生产化、PTP 多节点时间同步、Track-to-Track 融合、跨视角联合优化、多资源协同拦截、完整分区合并、标准 MOT/HOTA/OSPA 适配。
6. **2026-07-09 P1 接口补齐已完成一轮**：main runtime 已补齐 P1 calibration suite/threshold metadata、高度对比和 D6 标准报告 bundle；D1-D7 各模块已补充本模块 P1 metadata、summary、evidence 或 gate 字段；剩余工作从“接口缺口”转为“真实 AirSim 多 seed 标定和长期趋势治理”。
7. **2026-07-12 当前无新增 P0 blocker**：同一 `z=-30 m`、35 s 的 M5N2 paired 已完成 10 seeds；candidate 从 baseline 的 pair/target `7` 降为 `4`，coalition 均为 `0/10`，因此 optional soft/trend 不得晋级默认。1-5 帧 dropout 矩阵已完整执行，逐 seed 为 49/50（单帧 seed 2 未进入预测）；tuned 2v2 `png_ttc` 为 20/20。
8. **cooperative 合同错误已修正但性能未闭合**：D4 不再把 D5 non-locked 当成绑定冲突，arbiter 状态按 pair 隔离；main typed camera geometry 和稀疏 binding 已接通。四个单-seed case 中 `d4_terminal_inconsistent=0`、`d4_owner_missing` 专项为 0，但 control `0/12`、coalition `0/4`，继续列为 P1。
9. **D2 真实 CV 20-seed 对照不支持换主线**：默认 GNN 与候选/轻量 JPDA 均为 IDSW=0、continuity=1.0；JPDA 延迟更高，未达到晋级收益。该 fixture 区分度不足，后续提高漏检、虚警和遮挡难度，不把 JPDA 提前升级为默认。
10. **P1 接口与场景生成缺口已经转入实测判定，不等于算法晋级**：早期 20/30/50 m 预检已经由 18-case 正式筛选取代。正式结果仍为 20 m native active/continuity 合格、30/50 m 零检测，且 20 m 离线 precision/recall 只有约 0.26-0.33；因此没有后端进入 10-seed confirmation，默认 detect、GNN/Hungarian 和既有 PN/PNG 主线不变。
11. **2026-07-13 真实执行已完成，但性能 P1 仍开放**：D2 strict dense crossing、D4 60-case、M5N2 40-episode 和原生 MOT 18-case 均已实际运行。M5N2 最佳只有 `5/10`，原生 MOT 没有候选通过准入，因此不能把场景执行完成表述为性能闭合。
12. **2026-07-14 状态修正与关闭**：reserve 越权、`global_track_id` 改写、truth identity/state 使用、duplicate owner 和 false degradation 分开审计。SimpleFlight 状态真值隔离已在默认和两条主动降级路径关闭；D5 第二 primary、远距检测尺度、真实同 seed 复跑和长期 D3 churn 保持 P1，不启动 P2 主线替换。
13. **D6 physical provenance P0 已关闭**：command-only、summary-only、缺逐 pair evidence 或 pair/source 不一致时，物理指标保持 unavailable；历史缺 provenance 的结果不能因聚合字段或 command status 被升级为物理证据。
14. **D4 lease 与 D6 completeness P0 已关闭**：secondary 各执行层统一严格校验 lease 边界；D6 不再把 evidence flag 当作物理结果，也不在联盟成员、到达窗口或分母不完整时发布 coalition 零值。
15. **D5 native MOT history 代码断点已关闭**：真实 Results 路径能够累计连续实测命中，空帧、reset 和 native/fallback 切换不会继承锁定历史；远距召回、精度、连续性和延时仍按 P1 多 seed 准入。
16. **D4 多入口 readiness P0 边界已关闭**：核心仲裁、episode communication、main runtime 和 D6 metadata 统一要求完整、可校验且未过期的二级证据；heartbeat-only、缺 current time、未持续 readiness 和冲突 lease 不再生成可执行 owner。
17. **D2 continuity 准入不可达 P1 与联合报告缺口已关闭**：ceiling-aware v2、D6 双 schema 消费和原冻结 replay 正式联合报告均已通过回归；总体候选进入 promotion review，但逐 difficulty 证据不足以替换默认 GNN/Hungarian，dropout truth alignment 仍为 partial，JPDA 不准入。
18. **D4 公开 helper 缺失证据 P0 已二次关闭**：旧测试只覆盖主 readiness 入口，未覆盖 public handoff/metadata helper 的 `None` 组合。当前两个 helper、已激活同 plan 维持路径和 adapter 均要求 sustained readiness、expected/actual source、plan/required epoch、expiry/current time 与 monotonic plan 完整通过；逐字段负例和 distributed peer 不受误约束的回归已加入，D4 `280 passed`。

### 2.1 v2.10 历史状态表

本表保留 v2.10 阶段证据，不再作为当前入口。当前状态以本文 v2.20 增量和
`subagent_reviews/MAIN_IMPLEMENTATION_GAP_AUDIT.md` 第 7 节为准。

| 范围 | 当前证据 | 状态判定 |
|---|---|---|
| P0 | D1/D2/D6 身份隔离、availability、时间队列、truth-state provenance、D4 strict lease 和逐 pair physical provenance/result/coalition completeness gate 回归通过；三条 SimpleFlight 路径均使用 D2 estimate | **代码级无开放 blocker**；truth 仅留离线 scorer，过期 owner、缺证据、缺结果或来源冲突 fail closed |
| 2v2 SimpleFlight | 历史 candidate 10 seeds、20/20 pair 在 5 m 内成功；本批代码/fixture state use=0 | 历史结果仍只作迁移前 smoke；需按同 seed 真实重跑后发布新版 truth-isolated 物理证据 |
| 检测丢失 | 10 seeds：1 帧预测 9/10、2 帧 10/10；3-5 帧各 10/10 命中 0.25 s 硬过期；物理 100/100 | 矩阵完整但存在单帧 seed 2 时序尾部；truth/identity/version 回归通过 |
| D5/D7 | 双时间戳/相机几何证据、生命周期重置、`png_ttc` 面积治理已实现 | P1 合同闭合；真实同步/阈值继续标定 |
| D5 native MOT | Results 连续历史按 resource/camera/backend/native ID 隔离；空帧/reset/backend 切换后从 1 重计；D5 `241 passed` | 代码级历史断点已关闭；真实 AirSim/真实图像多 seed 准入仍开放 |
| Optional delivery | 10-seed paired 中 candidate pair/target `4`，baseline 为 `7`；trend 实际触发 0 | 明确不晋级默认 profile；6D LOS KF 继续 replay-only |
| M5N2 | 同条件 10 seeds：baseline pair `7/30`、target `7/20`；candidate `4/30`、`4/20`；coalition 均 `0/10` | paired 数据闭合，协同物理性能仍未闭合 |
| `png_ttc` | tuned 2v2 10 seeds、20/20；not-expanding 13、TTC out-of-range 22 | 真实多 seed 主链闭合；area-jump/clipping 受控覆盖开放 |
| D4 | secondary resource/plan/active owner/D7 handoff 统一要求 `current_time < lease_expiry`；D4 `211 passed` | lease 边界与失效 owner 已 fail closed；真实网络时序和自主成员重构保持 P1 |
| D6 | physical gate 已要求 summary + pair evidence + result + source 一致，并校验 coalition completeness；D6 `150 passed` | availability/zero、pair/target/coalition 继续分离；历史缺 provenance/result 结果保持 unavailable |

2026-07-14 最新回归计数：D1 83、D2 98、D3 全量通过（optional OR-Tools 1 skipped）、D4 211、D5 241、D6 150、D7 178、AirSim runtime 130、质点集成 7，均通过。未启动新的真实 AirSim episode；matplotlib `Axes3D` 为环境 warning，不影响二维评估。

## 3. 分级口径

| 等级 | 含义 | 是否阻塞当前测试 | 是否近期排期 |
|---|---|---:|---:|
| P0 | 当前轻量主线进入可信多 seed/闭环验证前必须具备的最小硬化项 | 是（阻塞可信闭环证据，不阻塞单元测试执行） | 是 |
| P1 | 三个月内增强、标定、对照和报告能力 | 否 | 是 |
| P2 | 六个月左右的架构升级、较重依赖或高阶算法 | 否 | 视资源 |
| 规避/P3 | 前沿但实时性、可解释性或认证风险过高，不进入当前路线 | 否 | 否 |

P0 继续拆分：

| 子级 | 含义 |
|---|---|
| P0-A | 基础设施可信度：时间、配置、健康、异常、任务 outcome、根因和性能 |
| P0-B | 安全门控与闭环稳定性：质量、迟滞、二级能力、重捕获、校准健康、导引切换稳定 |
| P0-C | 场景依赖 P0：仅在继续 5v5/N-v-N、高差、密集交叉、可信二级接管时进入 P0 |

## 4. Patch 新增观点的采纳判断

| Patch 观点 | 本项目采纳等级 | 判断 |
|---|---|---|
| COURAGEOUS / CEN CWA C-UAS 标准化测试 | P0-A 最小映射，P1 完整对齐 | D6 应立即建立指标映射表，但不要求一次性完整复刻标准流程 |
| MDPI 2025 C-UAS 标准化评估综述 | P0-A/P1 | 用于修正 D6 指标定义和报告引用；完整文献综述为 P1 |
| OCEF / MLPerf 式复现纪律 | P0-A 最小字段，P1 场景库 | 固定 seed、版本、evidence path 属 P0；完整基准平台属 P1 |
| PX4 EKF2 FDIR | P0-A 的 FDIR-light，P1/P2 完整移植 | 传感器 health、reject reason、协方差边界是 P0；完整 EKF2 移植不是 P0 |
| MATLAB Sensor Fusion Toolbox 调参逻辑 | P1 | 工程参考价值高，但不是运行依赖 |
| Stone Soup / FilterPy | P1/P2 对照 | 当前自研轻量 EKF/GNN 主线保留，外部库作为 benchmark |
| ByteTrack / YOLOv8 | P1 标定 | D5 已有 adapter；真实 AirSim 多 seed 阈值和失败回退仍是 P1 |
| SORT / Deep SORT | P1/P2 | SORT 可作 fallback 对照；Deep SORT/ReID 更偏 P2 |
| OR-Tools | P1 对照，P2 默认升级 | 当前 Hungarian/SciPy 主线足够；复杂约束和多容量才需要 OR-Tools |
| Event-Driven CBBA / Two-Level CBBA | P1 | 与 D4 分布式降级通信优化相关，但不是当前 P0 |
| etcd / SwarmRaft / Raft 选举 | P1 对照，P2 工程集成 | P0 只需要 lease/epoch/anti-split-brain 合同；完整 etcd 集成不列 P0 |
| DDS QoS / RTI Connext / ROS 2 生产部署 | P2 | 对生产化重要，但当前 Python/AirSim runtime 不应立即重写 |
| PTP / DDS 时间同步 | P2，封闭多节点实测前可升 P0-C | 当前单机 AirSim 只需 episode clock；真实多机硬件时才升级 |
| IBVS / 视觉伺服 / 间歇可见性切换控制 | P1，若做真实视觉接管可升 P0-C | 当前 P0 是 D5 reacquire 和 D7 latch；完整视觉伺服是后续增强 |
| 3D True PN 可捕获性 / ADRC / 协同到达时间 | P1/P2 | D7 已有 3D benchmark；默认控制律不应立即替换 |
| MLflow / W&B / Dashboard | P1/P2 | D6 可先导出标准 CSV/JSON/Markdown；平台化实验管理后置 |
| Docker Compose / Hydra / structlog | P1 | 对工程化有帮助，但当前不构成 P0 blocker |

## 5. P0 缺口确认

P0 是“最小可信闭环硬化项”，不是“把所有成熟外部工具集成进来”。

### 5.1 P0-A 基础设施可信度

| Owner | P0-A 缺口 | Patch 支撑 | 最小验收口径 |
|---|---|---|---|
| Main/System | 统一 episode clock 与时间字段 | Apollo/Cyber RT、DDS 时间同步、OCEF 复现纪律 | 每条 D1-D7 record 能区分 `measurement_timestamp`、`arrival_timestamp`、`processing_timestamp`、`publish_timestamp` 或等价字段 |
| Main/System | 集中 scenario config 与 evidence path | OCEF、Hydra、MLflow | settings、seed、资源/目标数量、检测后端、算法版本写入 D6 metadata |
| Main/System | 模块 health snapshot 与异常 outcome | PX4 FDIR、结构化日志实践 | D1-D7 health、last update age、record count、error state、runtime exception 可写盘 |
| D6 | 系统级 mission outcome | COURAGEOUS、MDPI C-UAS 评估 | 每个 episode 输出 success/partial/failed/aborted、success/failure reason |
| D6 | 根因诊断与 top failure causes | COURAGEOUS、OCEF、MLflow | 报告能归因 tracking、assignment、coverage、terminal gate、guidance、runtime exception |
| D6 | 性能和可复现字段 | OCEF、pytest-benchmark、MLflow | 输出模块耗时、loop latency、record latency、CPU/GPU budget placeholder、eval priority/status/evidence path |
| D6 | 标准化评估映射最小版 | COURAGEOUS、MDPI、OCEF | 增加“本项目指标 -> 标准 C-UAS 指标类别”的 mapping，不要求完整认证 |
| D1 | FDIR-light | PX4 EKF2 | 传感器 health、fault reason、reject count、恢复状态、异常隔离建议 |
| D1 | 协方差上下界与 reason | PX4 EKF2、MATLAB fusion 调参 | 低质量/遮挡/外推时 covariance 不虚假收敛、不无限发散 |
| D1 | 时间戳不确定性 | Apollo/Cyber RT、DDS 时间同步实践 | timing uncertainty 进入 observation/track summary 和 D6 延迟报告 |

### 5.2 P0-B 安全门控与闭环稳定性

| Owner | P0-B 缺口 | Patch 支撑 | 最小验收口径 |
|---|---|---|---|
| D2 | 航迹质量评分 | MATLAB tracking、MHT/JPDA/BP 选型论文 | 每条 track 输出 `track_quality` 和 `association_risk`，供 D3/D5/D6 消费 |
| D2 | 运动一致性约束 | SORT/MATLAB tracking 工程实践 | GNN/Hungarian 代价中有速度方向/短时历史一致性，不替换主关联器 |
| D2 | quality-aware gate baseline | MHT/JPDA/BP track coalescence 分析 | dense/crossing 下门限可随 track quality/density 做轻量调整 |
| D3 | 资源状态细化 | OR-Tools/工业分配实践 | energy、availability、current load、history failure、intercept feasibility 进入 cost metadata |
| D3 | 增强迟滞和 stale rejection | 工业资源调度实践 | min dwell、switch penalty、release condition、stale reason 可解释 |
| D3 | 可解释 threat baseline | Iron Dome 公开威胁评估思路 | TTC、关键区接近、速度、协方差、目标状态进入 threat score baseline |
| D4 | Heartbeat 平滑 | etcd/Raft、DDS QoS | 短时丢包不直接 failed，有 degraded/suspect dwell |
| D4 | Lease/epoch 严格合同 | etcd/Raft、SwarmRaft | 过期或非单调二级 plan 不可执行；active secondary same id/version 不误拒绝 |
| D4 | 二级能力评估 | 分布式边缘融合、SwarmRaft | 区分 visible、registered、takeover_capable，并写入 D6 metadata |
| D4 | 主动降级防抖 | UAV 韧性评估、D4 工程实践 | hard/soft risk、dwell/release、false-trigger candidate 可统计 |
| D5 | 主动重捕获 | 间歇可见性切换控制、Fortem/Skydio 工程经验 | reacquire 不改写 `global_track_id`，基于投影和搜索窗口恢复 |
| D5 | 时序一致性和稳定窗口 | ByteTrack、IBVS、视觉跟踪实践 | bbox/MOT history、candidate margin、stable window 抑制误锁 |
| D5 | 相机校准健康监测 | Kalibr、OpenCV、IBVS | 输出 reprojection error、pose source、calibration health、drift warning |
| D7 | 末端切换迟滞 | 视觉间歇可见性、导引工程实践 | dwell/release/reacquire grace，terminal switch reject reason 可解释 |
| D7 | LOS 角速率滤波 | PN/视觉伺服工程实践 | filtered LOS rate、限幅、outlier reject，近距命令无尖峰 |

### 5.3 P0-C 场景依赖项

| Owner | P0-C 缺口 | 升为 P0 的条件 | 否则等级 |
|---|---|---|---|
| D7 | 3D PN geometry benchmark/log | 继续做 200 m 高差、3D target 或高度差拦截 | P1 |
| D6 | COURAGEOUS 完整流程映射 | 准备封闭场地或外部可审计测试报告 | P1 |
| D4 | 二级接管 anti-split-brain 合同强化 | 多二级节点/网络分区/完全无中心测试 | P1 |
| D5 | 视觉接管前置证据增强 | 要求视觉 PNG 稳定接管率显著提升 | P1 |
| Main/System | 多 seed 标定强制化 | 开始以 AirSim 多 seed 作为主验收口径 | P1 |

## 6. P1 缺口确认

P1 是三个月内能力增强、对照实验、标定和标准化报告。

| Owner | P1 缺口 | Patch 支撑 | 验收口径 |
|---|---|---|---|
| D1 | IMM/CV-CA-CT 多模型滤波 | PX4/Stone Soup/MATLAB | 机动目标 RMSE 下降，同场景 EKF baseline 保留 |
| D1 | 场景自适应协方差 | PX4 FDIR、MATLAB 调参 | 输出 covariance scale reason：遮挡、杂波、距离、来源、延迟 |
| D1 | Track-to-Track 融合原型 | West Point MWI 分布式边缘融合 | 多二级节点输入不重复计数，协方差一致 |
| D2 | JPDA/MHT/BP 选型对照 | IEEE OJSP 2024 track coalescence | dense/crossing 下输出 IDSW、coalescence、latency 对照 |
| D2 | SORT/ByteTrack style fallback | SORT/ByteTrack 工程实践 | GNN 异常或视觉 MOT 场景可回退轻量 baseline |
| D2 | N/M 初始化和协方差一致性检查 | MATLAB/Stone Soup | false track rate、init latency、NIS/NEES 或等价 flag |
| D2/D6/main | ceiling-aware v2 候选评审与完整系统证据 | 正式联合报告已生成；总体五项 gate 通过，但只有 `clutter/combined` 通过，四个零 baseline-IDSW difficulty fail-closed，dropout truth alignment 为 partial | 保持默认 GNN/Hungarian；补同 case/seed 的完整 D1-D7 system bundle 和长期趋势后再决定候选是否晋级，JPDA 继续不准入 |
| D3 | OR-Tools Min Cost Flow 对照 | OR-Tools patch | 同输入下输出 Hungarian vs min-cost-flow 对照计划 |
| D3 | 增量分配和时间窗口硬约束 | OR-Tools/工业调度实践 | 目标新增/资源失效时 update latency 下降，closed window 不被分配 |
| D3 | 完整动态威胁评估 | Iron Dome 公开思路 | threat score 可解释并进入 D6 scenario report |
| D4 | Raft/SwarmRaft leader election 对照 | etcd、SwarmRaft | 二级选举日志可复现，不绕过 D3/D4/D7 执行合同 |
| D4 | Event-Driven CBBA 通信优化 | arXiv 2025 Event-Driven CBBA | 共识消息量下降，冲突率和完成率可统计 |
| D4 | 网络分区检测与恢复韧性指标 | UAV resilience metric | 输出 partition state、merge audit、resilience score |
| D4 | DDS QoS 通信策略仿真 | ROS 2 DDS QoS / RTI | 丢包、stale link、priority delivery 进入 D6 指标 |
| D5 | YOLOv8 + ByteTrack/BoT-SORT 多 seed 标定 | YOLO/ByteTrack patch | Results 历史累计、遮挡/reset/backend 隔离已关闭；继续以真实 AirSim/真实图像校验目标尺度、FOV、置信度、远距召回、IDSW/continuity、tracker backend、CPU/GPU P95 budget，不改写 `global_track_id` |
| D5 | IBVS/间歇可见性重捕获对照 | IEEE TIE/TAES/arXiv | lost/reacquire 时间下降，误锁仍为 0 |
| D5 | 多模态友方识别 replay adapter | OpenDroneID/MAVLink/DDS/AprilTag 规划 | 至少一个 replay path 输出 verified/stale/unverified |
| D5 | 完整相机在线标定/畸变校正 | Kalibr/OpenCV | 标定样本中重投影误差下降，distortion 进入 projection |
| D6 | COURAGEOUS/MDPI/OCEF 标准化报告 | WebSearch patch 最大收获 | D6 报告增加标准指标映射、测试阶段、复现纪律字段 |
| D6 | 基线对比和统计显著性 | MLflow/OCEF/pytest-benchmark | baseline vs enhanced、多 seed 均值/方差/置信区间 |
| D6 | 场景库管理和 CI 回归摘要 | OCEF、MLflow、CI 工程实践 | scenario tags、difficulty、expected failure modes、test matrix |
| Main/D6 | 分阶段实时性能 multi-seed 标定 | pytest-benchmark/OCEF 复现纪律 | 使用两层 timing JSONL 分别报告阶段 mean/P95/max、dominant stage 和预算违例；同配置 2v2/M5N2 优化后复验 100 ms，禁止跨层求和 |
| D7 | 3D True PN/APN/ADRC 对照 | Aerospace S&T、IECON、PX4 L1 | 作为 benchmark，不替换默认 PN/PNG，不绕过 D3/D4/D5 gate |
| D7 | 预测拦截点和动力学补偿 | 导引工程实践 | predicted intercept point、命令饱和、响应延迟写入 guidance log |
| Main/System | ROS 2 replay 原型 | ROS 2/RTI/DDS patch | 离线 replay 节点原型，不重写当前 Python runtime |
| Main/System | 结构化日志和配置治理 | structlog/Hydra | 当前 JSONL 记录继续保留，配置版本和 schema 明确 |
| Main/System | Docker Compose 开发部署 | Docker Compose patch | 用于本地多进程实验，不作为生产部署 |

## 7. P2 缺口确认

P2 是较重外部依赖、生产化架构、高阶算法和长期对照。P2 不应抢在 P0/P1 前改主线。

| Owner | P2 缺口 | Patch 支撑 | 验收口径 |
|---|---|---|---|
| D1 | UKF/非线性强量测后端 | Stone Soup/FilterPy/MATLAB | 与 EKF 同场景对照，收益明确后再进入主线 |
| D1 | 主动传感器管理 | 多传感器 C-UAS 设计指南 | coverage 或不确定性有量化改善 |
| D2 | 有界 MHT 工程实现 | Stone Soup/MHT 选型论文 | N-scan pruning、延迟、内存可控 |
| D2 | 标准 MOT/HOTA/IDF1 adapter | TrackEval/py-motmetrics 规划 | 离线 truth label 数据稳定后接入 |
| D3 | 多资源协同/备份资源/预测性滚动分配 | OR-Tools/防空资源分配实践 | D6 能评估协同收益、备份触发和冲突风险 |
| D4 | etcd/Consul/完整 Raft 集成 | etcd/SwarmRaft | 多节点真实通信条件满足后再做，不替代当前 lease 合同 |
| D4 | 版本向量、分区合并、完整 recovery audit | Raft/分区恢复实践 | 网络分区恢复后冲突可解释 |
| D5 | Deep SORT/ReID 外观特征 | SORT/Deep SORT/视觉工程实践 | 遮挡恢复和密集场景 ID continuity 提升 |
| D5 | 跨视角联合优化 | 多相机视觉实践 | 多相机外参、同步和稳定 bbox 足够后再做 |
| D5 | 视觉伺服控制闭环 | IBVS/Skydio/Fortem | 必须保持 D3/D4/D5/D7 gate，不让视觉节点改写任务绑定 |
| D6 | MLflow/W&B 平台化实验管理 | MLflow/W&B patch | 先保证本地 CSV/JSON/Markdown，再接平台 |
| D6 | 对抗性评估和场景覆盖率矩阵 | COURAGEOUS/OCEF | 场景库标签化后实施 |
| D7 | 协同到达时间制导 | Cooperative Impact Time Guidance | 依赖 D3 多资源协同和 D6 成功指标 |
| D7 | 默认 3D 控制律/平台动力学/FRPN/ADRC 主线升级 | 3D True PN/ADRC | benchmark 数据证明优于 PN 后再考虑替换 |
| Main/System | ROS 2 + RTI Connext 生产硬化 | RTI/ROS2/DDS patch | 不在当前 Python/AirSim 阶段重写；生产化时推进 |
| Main/System | PTP 多节点时间同步 | DDS/PTP patch | 进入真实多机硬件前推进 |
| Main/System | Dashboard/Kubernetes/KubeEdge 自动化部署 | 工程实践 patch | 运行指标稳定后再平台化 |

## 8. 明确规避或降为 P3 的方向

这些方向不进入当前 P0/P1/P2 默认实施，除非后续作为独立研究专项。

| 方向 | 涉及模块 | 规避原因 |
|---|---|---|
| LLM 辅助实时传感器融合 | D1 | 延迟高、不可解释、实时闭环风险大 |
| 区块链集群协调 | D4 | 延迟和计算开销不适合拦截实时性 |
| DMPC/重型分布式 MPC 作为默认降级控制 | D4/D7 | 计算量大、标定复杂，先保留规则/PN 主线 |
| 深度强化学习制导律 | D7 | 黑盒、难认证、泛化风险高 |
| 端到端深度学习任务分配或身份绑定 | D2/D3/D5 | 容易破坏可解释性和 `global_track_id` 合同 |
| BFT 共识 | D4 | 当前二级/分布式仿真过重，Raft/lease 已够基线 |
| 云原生/Kubernetes 生产部署 | Main/System | 当前目标是 AirSim/封闭场地可信验证，不是大规模服务平台 |

## 9. 与当前项目状态的关系

截至本文件更新时，项目已完成一批 P0 最小实现：

- main runtime：episode clock/config/module health/runtime exception outcome。
- D1：sensor health、covariance floor/ceiling、timestamp uncertainty。
- D2：track quality、motion consistency、quality-aware gate baseline。
- D3：资源状态细化、迟滞增强、threat score baseline。
- D4：heartbeat smoothing、lease/epoch strictness、secondary capability score、主动降级防抖。
- D5：active reacquire、temporal consistency、calibration health metadata。
- D6：mission outcome、root cause、performance metrics、eval tracking。
- D7：terminal latch、LOS rate filtering、3D PN benchmark/log。

同时，2026-07-09 已完成一批 P1 接口补齐：

- main runtime：`--p1-calibration-sweep` 输出 `calibration_suite=cv_5v5_d4d5_secondary_coverage`、suite version、threshold version、二级高度/FOV/数量/站距、expected state fields 和 50m/200m 高度对比；自动生成 D6 `d6_airsim_calibration` CSV/JSON/Markdown bundle。
- main runtime：修复 secondary takeover plan 在连续 replan 后 `owner_node_id` 回退为 `d3_central` 的问题；若 D4 legacy metadata 指向中心，main 会按 D4 target node、历史 secondary owner 或当前 frame 中的二级节点名保持真实 secondary owner。
- D1：dry-run/replay schema/version/metadata 检查、latency/OOSM audit 和区域质量摘要已补齐。
- D2：association risk threshold version、gate pass/reject、risk summary 和 threshold sensitivity 已补齐。
- D3：`AssignmentEvidenceExport`、current cost matrix、per-edge breakdown、hard rejected edges、stale reason、secondary fields 和 hard time-window closed-edge baseline 已补齐。
- D4：`secondary_capability_class` / `secondary_readiness_class` 已补齐；二级节点必须达到 `takeover_ready` 才能作为接管依据，visible-only / registration-usable 只能作为辅助或标定证据。
- D5：`detect_registration_outcome`、reject reasons、measurement age、projection/covariance、`projection_invalid` 独立原因和 YOLO/MOT metadata 已补齐；在线 D5 仍不得使用 AirSim truth ID 或改写 `global_track_id`。
- D6：AirSim calibration records/summary/Markdown 保留 scenario/standard mapping/evidence/trend/height bucket/actual scale；Markdown 增加 50m vs 200m coverage、coverage funnel、baseline vs enhanced、stable registration、not registered、active degradation、D7 reject 等口径。
- D7：runtime/comparison/replay/calibration 输出 terminal range、closing speed、bbox/LOS/maneuver gate、D4 block reason、D5/D3 consistency、secondary capability/readiness、threshold advisory version 和 visual PNG switch count；PNG 核心控制律未改。

本轮 smoke 验证：

- 输出目录：`research_modules/airsim_runtime/outputs/p1_gap_fix_smoke_20260709/`
- 组合：50m/200m 二级高度、3 个机动高空二级侦察节点、110 deg FOV、seed=1、三类 case。
- 结果：`row_count=6`，`projection_valid_rate=1.0`，D6 标准报告 bundle 已生成。
- 解释：50m bbox 均值约 19055 px^2，200m bbox 均值约 1147 px^2；200m 网络同帧全覆盖仍为 0.0，说明剩余 P1 重点是二级站位/扫描/coverage 和多 seed 阈值标定，而不是绕过 D3/D4/D5 gate。

### 2026-07-10 P0/P1 实施与真实 AirSim 复核

本轮按 “main 下发、D-agent 自改自测、main 集成与 AirSim 编排” 完成以下闭合：

- D2：无 truth 场景不再产生虚假 continuity 硬风险，`rejected_pairs` 可序列化/回放，协方差增加 finite/symmetric/PSD 校验和诊断。
- D3：已有 active plan 后拒绝缺失 `previous_plan` 的请求；stale rejection 保留当前 plan；switch penalty 在 Hungarian 求解前进入代价矩阵。
- D5：reacquire 继续执行友方身份保守门控；MOT 状态按 `(resource_id, camera_id)` 隔离；AirSim actor/object 名不再参与在线 category/local identity。
- main/runtime：AirSim builtin detect 使用匿名 camera-local bbox tracker，`local_track_id/detection_id` 不含 actor 名；actor 名只保留为 `offline_truth_*` 评估字段。真实证据目录 `research_modules/airsim_runtime/outputs/p0_truth_isolation_smoke_20260710/` 中三类 case 均连接，匿名 ID 连续 5 帧，cross-view association 均为 4。
- D6：多 seed 聚合和 baseline/enhanced 配对使用稳定 `scenario_group`；bootstrap CI 固定随机种子；execution/contract evidence path 分离；无有效 active-degradation label 时不再误报零精度。拦截 success/collision/abort/min-range/time/visual-switch/gate 指标已进入 cross-seed，且无 intercept evidence 的 read-only episode 为 unavailable，不再伪造 0/20。

真实 AirSim D4/D5 5v5 校准已完成，不再属于“尚未执行多 seed”的缺口：

- 输出目录：`research_modules/airsim_runtime/outputs/p1_gap_closure_calibration_20260710/`。
- 组合：seed 1-10，50/200 m，3 个机动二级侦察节点，110 deg，1920x1080，三类降级 case，共 60 个 episode，全部 connected。
- 50 m：网络平均覆盖约 0.687，joint full-view 约 0.044，稳定跨视角注册均值约 86.9。
- 200 m：网络平均覆盖约 0.725，joint full-view 约 0.003，稳定跨视角注册均值约 97.6；bbox 均值约 1146 px^2。
- 20 个 `degrade_to_secondary` case 最终均保守转为 `degrade_to_distributed`。1300 条 D4 决策中 1285 条为 `registration_usable`，只有 15 条瞬时 `takeover_ready`，全部停在 `pending_secondary_plan`；`secondary_plan_active=0`。主要断点是 network full-view、coverage ratio、逐决策 stable/not-registered evidence 和二级 plan activation，不是 heartbeat/link/cue/gimbal 失效。

真实 AirSim 2v2 SimpleFlight 10-seed 基线也已完成：

- 输出目录：`research_modules/airsim_runtime/outputs/p1_gap_closure_2v2_multiseed_20260710/` 及对应 `_seed001..010` 目录。
- 20 个拦截对中 18 个 `collision_intercept`，2 个因 `terminal_detection_timeout` 中止；成功率 90%。
- 按 20 个 pair 等权统计，平均最小距离约 2.113 m，成功 pair 平均拦截时间约 3.589 s；D6 的 episode 口径取每 seed 的最小 pair 距离和 episode 时间，均值分别为 1.812 m、3.66 s。两种口径不混用。
- 导引记录汇总：`radar_pn=530`、`png_vm=289`、`los=65`；平均 `terminal_switch_allowed_rate` 约 0.082。
- 主要视觉/切换拒绝：`d5_not_locked=309`、`maneuver_margin_low=194`、`bbox_near_image_edge=182`、`d4_reassign_pending=165`。当前证明雷达 PN + 受门控视觉 PNG 可闭环，但尚不能宣称视觉 PNG 稳定接管，也没有完成 AirSim PN/Pure Pursuit/PNG-TTC/PNG-VM 四路线同场景对照。

因此本文件后续使用方式是：

1. **已完成的 P0**：保持回归，不重复列为新 blocker。
2. **已完成的 P1 接口补齐**：保持回归，后续不要重复列为“缺字段/缺接口”。
3. **剩余 P1 标定项**：M5N2 paired、1-5 帧 dropout、真实 `png_ttc` 多 seed 和 D5 原生 MOT history 代码修复已执行，不再列为“未运行/未实现”。当前开放项是 M5N2 candidate 退化与 coalition 0/10 的根因、D2 dense crossing ID 连续性、`png_ttc` area-jump/clipping 受控覆盖、二级真实通信时序、D5 真实图像阈值与多 seed 准入、D6 长期趋势治理。
4. **P2**：作为后续子智能体任务来源，由 main 分发给对应 D-agent 后再同步模块 GAP/PLAN。

## 10. 建议执行顺序

### 第一批：保持 P0/P1 接口回归

1. D6/main：保持 `COURAGEOUS/MDPI/OCEF -> 当前 EpisodeMetrics` 最小映射、`standard_metric_family`、`evidence_path` 和 `scenario_version` 不退化。
2. main/runtime：保持 P1 calibration sweep suite/version/threshold、高度对比、D6 bundle、secondary owner 保持和不保存 PNG 默认规则。
3. D1-D7：保持各自 P1 metadata/summary/evidence/gate 字段不退化，并由对应 subagent 同步 GAP/PLAN。

### 第二批：扩展已建立的多 seed 校准

1. AirSim 2v2 intercept：保持 1-5 帧硬窗口与 `png_ttc` 20/20 回归；下一轮只补 area-jump/clipping 受控注入和真实相机同步，不把未触发 trend 宣称为增强有效。
2. M5N2：基于已完成的 10-seed paired，分解 candidate 退化和 coalition 0/10 的第二 primary 中段、D5 共识、D7 gate 与成员安全根因。
3. D4/D5 5v5 stress：现有 60-case 作为覆盖/注册基线，下一轮构造持续 `takeover_ready -> pending_secondary_plan -> secondary_plan_active` 专项，不降低安全门限。
4. CV 5v5：补充 D1/D2/D3/D5 质量门控、assignment stability、ID switch、terminal association 和 active degradation necessity 的长期聚合。

### 第三批：做 P1 对照

1. D3 OR-Tools min-cost-flow 对照。
2. D2 JPDA/MHT/SORT/ByteTrack-style 对照。
3. D4 Raft/SwarmRaft election replay 对照。
4. D5 IBVS/间歇可见性重捕获对照。
5. D7 3D True PN/APN/ADRC benchmark。

## 11. 最终确认表

| 模块 | 当前运行级 P0 blocker | 仍需保持/补充的 P0 | P1 主线 | P2 主线 |
|---|---:|---|---|---|
| D1 | 无 | FDIR-light、协方差界、时间戳不确定性、latency/OOSM/region summary 保持回归 | IMM、自适应协方差、T2T 原型、更多真实 Blocks/CV fixture | UKF、主动传感器管理 |
| D2 | 无 | 航迹质量、运动一致性、quality-aware gate、risk threshold summary 保持回归 | JPDA/MHT/BP 选型、SORT/ByteTrack fallback、真实 5v5 replay 阈值校准 | 有界 MHT、标准 MOT adapter |
| D3 | 无 | 资源状态、迟滞、threat baseline、assignment evidence export、secondary DTO 保持回归 | OR-Tools 对照、增量分配、硬时间窗多场景校准、D5 feedback 权重标定 | 多资源协同、备份资源、预测性滚动 |
| D4 | 无 | heartbeat、lease、二级能力、防抖、secondary readiness/capability class 保持回归 | Raft/SwarmRaft、Event-CBBA、分区检测、二级覆盖/接管必要性多 seed 标定 | etcd 集成、版本向量、分区合并 |
| D5 | 无 | 重捕获、时序一致性、校准健康、detect registration outcome、truth ID 在线隔离保持回归 | YOLO/MOT 标定、IBVS、间歇可见性、多模态身份 replay、跨视角注册阈值 | ReID、联合优化、视觉伺服闭环 |
| D6 | 无 | mission outcome、根因、性能、标准映射最小版、P1 calibration bundle 保持回归 | COURAGEOUS/OCEF 完整报告、A/B 显著性、场景库、多 seed 长期趋势 | MLflow/W&B、对抗评估、标准 MOT/OSPA |
| D7 | 无 | latch、LOS/KF 生命周期、`png_ttc` 面积治理、D3/D4/D5 gate 和 fail-closed 保持回归 | M5N2 candidate 退化根因、`png_ttc` 剩余受控拒绝覆盖、trend 保持 candidate-only、3D/APN benchmark | 协同到达时间、默认 3D/FRPN 升级 |
| Main/System | 无 | 时间、配置、健康、异常恢复、P1 calibration sweep、secondary owner 和四层结果日志保持回归 | 同条件 M5N2 paired、长期结构化日志/场景治理、ROS2 replay 原型 | ROS2/RTI 生产硬化、PTP、Dashboard/KubeEdge |

结论：三个 patch 强化了“标准化评估 + 成熟工程栈 + 明确规避前沿黑盒方法”的方向，但没有推翻当前轻量主线。2026-07-12 已完成 80-episode terminal-closure、D1-D5 版本化证据和 D6 统一报告；实测证明 dropout/`png_ttc` 主链可用，也证明 M5N2 candidate 退化且联盟未闭合。下一步最急的是修复协同物理与 D2 ID 连续性，而不是引入重型外部框架、提前晋级 optional delivery 或降低安全门限。
