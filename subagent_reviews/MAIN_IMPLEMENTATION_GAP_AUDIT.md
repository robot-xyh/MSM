# Main 实现差距总审计

**审计来源**：D1-D7 子智能体分别对照 `subagent_reviews/*_REVIEW_AND_PLAN.md`、`C_UAS_MAINSTREAM_SOLUTIONS_AND_DIFFICULTIES.md` 和各自 `research_modules/` 代码完成自查。
**审计目标**：列出共识算法与计划使用的开源代码哪些已经实现，哪些没有实现，为什么没有实现，以及缺少哪些条件。
**边界**：本文只用于科研仿真、接口补齐和后续工程排期；不涉及真实硬件、实机处置、火控或绕过授权的自动动作。

**P0/P1 状态入口**：本文是 main 层唯一的实现差距与 P0/P1 状态入口，集中维护 owner、当前状态、缺少条件和验收口径。`EVAL/FRAMEWORK_EVAL_P0_P1_P2_GAP_CONFIRMATION.md` v2.1 已确认：当前未发现新的运行级 P0 阻塞断链。2026-07-11 本轮已经关闭 P1 合同与实现缺口，包括在线 truth 隔离、受治理 replay、D3 增量规划、D4 二级/完全分布式原子联盟、D5 匿名 detect 几何关联、D7 有界视觉外推和 D6 分层指标。SimpleFlight 已采用 NED 三维距离 `<=5 m` 的成功判据；2026-07-12 的 2v2 candidate 已完成 10-seed、20/20 pair 验收，但同几何/同时间窗的 M5N2 paired candidate 尚未完成，因此不得把 2v2 结果扩展解释为协同联盟已达标。P2 只在独立环境中评估外部库和高阶算法，不替换默认 NumPy/SciPy/PN/PNG/detect 路径。

## 2026-07-12 PNG delivery 增强与实测状态

本轮由 main 下发、D5/D6/D7 分别实现并自测，main 只负责 AirSim runtime 接线、真实运行和汇总。详细报告为 `research_modules/airsim_runtime/outputs/PNG_DELIVERY_ENHANCEMENT_AIRSIM_VALIDATION_REPORT_20260712.md`，D6 结构化对照包位于 `research_modules/airsim_runtime/outputs/png_delivery_enhancement_eval_20260712/`。

| 范围 | 当前状态 | GAP 判定 |
| --- | --- | --- |
| D7 图像 KF 生命周期 | 已按 resource/global/local track 与 plan owner/version 隔离；切换即重置，漏检不伪造身份切换 | P1 实现闭合，保持跨 ID/version/friend/duplicate 回归 |
| D7 `png_ttc` | 已加入 delivery 等价面积 EMA、窗口斜率、跳变/裁剪/TTC 范围拒绝；`png_vm` 不变 | P1 实现闭合，真实 `png_ttc` 多 seed 标定仍开放 |
| soft prediction / trend coast | 默认关闭；candidate profile 显式开启，预测上限 0.25 s，trend 仅水平且不超过 0.75 m/s | P1 optional 能力闭合，不晋级默认 profile |
| D5 证据合同 | 已输出双时间戳、local-track transition、MOT history、bbox clip、相机内外参和姿态有效性；truth ID 在线使用禁止 | P1 合同闭合，真实标定误差/姿态同步长期校准开放 |
| D7 6D LOS KF | 仅离线 replay，兼容 direct `camera_to_ned_rotation` 或分解旋转；字段缺失明确 unavailable | P2 optional，不替换在线 EMA/滑窗 |
| D6 指标 | 已增加滤波状态、TTC 拒绝、soft/coast、命令跳变及 contract/control/mode/physical 分层报告 | P1 指标闭合 |
| 真实 2v2 | candidate 10 seeds 为 20/20 pair 在 5 m 内成功，在线 truth=0；旧基线为 19/20 | 达到本轮非退化验收，但自然场景未触发 soft/trend，不能据此宣称增强算法贡献 |
| 锁定后 dropout | 2 帧均为 `image_kf_predict`，2/2 物理成功，未发生跨身份 coast | 有界预测真实链路闭合 |
| M5N2 | 8 s 短窗口 3 seeds 为 0 成功，最近距离 22-32 m；出现 soft prediction 4、innovation reject 2、truth=0 | 与既有 z=-30 m/35 s 高净空基线不等价；P1 仍是第二 primary 中段闭合和联盟视觉一致性，不归因于 PNG 滤波 |

统一回归：D4 148、D5 161、D6 84、D7 137、AirSim runtime 98、质点集成 7、dry-run 4、跨模块合同 3，全部通过。当前没有新增 P0；仍需用同一高净空 M5N2 几何和相同运行窗口做 paired baseline/candidate，才能决定 soft prediction 或 trend coast 是否进入默认 AirSim profile。

## 2026-07-11 P1 收敛实施后权威状态

完整中文报告和结构化证据位于 `research_modules/airsim_runtime/outputs/p1_p2_validation_20260711/P1_P2_VALIDATION_SUMMARY_CN.md`。本节是当前状态；后文“实施前基线”只保留历史对照。

| 范围 | 实施与验证结果 | 当前判定 |
| --- | --- | --- |
| D1/D2 replay 与 truth 隔离 | D1 输出带 schema、双时间戳、协方差、lineage 的 governed replay；D2 只从独立 offline truth label 评分 | P1 合同闭合，继续补充更长真实 replay 校准 |
| D3 动态规划 | 增量规划、短时 feedback dwell、primary 角色保持和 N/M 非等量合同已实现 | P1 合同闭合，真实阈值仍需多 seed 调参 |
| D4 联盟接管 | 二级节点和完全分布式三成员联盟均达到 `executing`、ACK 3/3；缺 ACK 为 2/3、状态 `aborted` | P1 原子 commit/ACK/epoch/lease 正负例闭合 |
| D5/D7 协同末端合同 | CV 10 seeds 中 8/10 达到 T001 双 primary 视觉共识并授权；10/10 IDSW=0、错误重复锁=0、global ID 改写=0 | 达到本轮 8/10 合同验收；两个失败 seed 保留为鲁棒性回归 |
| D6 结果语义 | 已分离 `contract_allowed`、`control_allowed`、`mode_switched`、`physical_intercept`，ComputerVision 的物理命中为 unavailable 而非 0 | P1 指标口径闭合 |
| SimpleFlight 物理拦截 | runtime 默认成功半径已由 0.75 m 改为 NED 三维 5.0 m；pair/target/coalition 分层统计已接入；首次无锁使用 acquisition grace，已锁定后按 `image_kf_predict -> blind_push -> expired/reacquired` 处理 | P1 代码与接口闭合；真实 2v2/M5N2 多 seed 成功率待重跑 |
| D5 在线视觉链 | 默认继续使用 `simGetDetections` bbox；controlled intercept 已取消 `object_id == target_id` 选框和模拟锁定，改为消费 episode bus 的匿名 local track 与几何 `TerminalAssociation` | P1 truth 隔离和接线闭合；YOLO 数据集标定后置 |
| P2 可选对照 | D1 FilterPy/Stone Soup、D2 GNN/JPDA/MHT、D3 OR-Tools capacity、D4 coalition replay、D5 OpenCV PnP、D6 py-motmetrics、D7 3D/APN/FRPN 均按 available/unavailable 口径隔离运行 | 仅 benchmark；不进入默认 requirements 和在线控制路径 |

本轮统一回归结果：D1 62、D2 67、D3 123（1 skipped）、D4 144、D5 155、D6 82、D7 117、AirSim runtime 90，均通过。唯一 D3 skip 为未安装 optional OR-Tools；PNG delivery 核心公式未修改。

### P1/P2 模块边界复核

| Owner | P1 当前状态 | P2 当前状态 | 默认路径是否替换 |
| --- | --- | --- | --- |
| D1 | governed replay、truth policy 和融合合同完成；真实长 replay、CI/阈值长期标定开放 | 冻结 replay benchmark 已实现；当前环境 FilterPy/Stone Soup unavailable，显式给出原因 | 否，仍为 NumPy EKF/fixed-lag |
| D2 | D1 adapter、offline truth、N-target synthetic dense calibration 完成；真实长 replay 开放 | GNN/JPDA/MHT 同 replay 对照完成；FilterPy/Stone Soup 对象 adapter 不提供身份指标 | 否，仍为 GNN/Hungarian |
| D3 | M-to-N demand-slot、增量规划、role-aware primary 和 commit/current-binding 合同完成；动态非等量长期标定开放 | capacity benchmark 已实现；当前 OR-Tools unavailable 并显式报告原因 | 否，仍为 SciPy Hungarian/demand-slot |
| D4 | secondary/peer commit、故障矩阵和 member loss/replacement replay 完成 | 原生 6 场景 replay 完成；MIT/CA-CBBA 未配置或未集成时显式 unavailable | 否，仍为本地轻量 CBBA/原子 commit |
| D5 | detect-first 匿名 local track、几何锁定、预测/丢失不锁定和 runtime record 完成；真实多 seed 标定开放 | OpenCV calibration/PnP 离线 benchmark 完成；YOLO/ByteTrack 数据集标定 deferred | 否，在线默认仍为 AirSim detect 与保守门控 |
| D6 | pair/target/coalition、四层结果语义和 detect/coast 诊断完成 | py-motmetrics 可选；HOTA/TrackEval 依赖不足时保持 unavailable | 否，仍为本地 D6 指标主线 |
| D7 | commit-aware gate、N/M topology、有界 KF/coast 外推和 SimpleFlight consumer 接线完成；真实长时标定开放 | 3D PN、True PN、APN、FRPN 仅离线 benchmark；FRPN 是研究近似 | 否，仍为既有位置 PN/视觉 PNG |

## 2026-07-11 P1 收敛实施前基线

真实 AirSim ComputerVision 证据目录为 `research_modules/airsim_runtime/outputs/blocks_cv_m5_n2_liveness_*_20260711/`，中文汇总为 `M_TO_N_AIRSIM_CONVERGENCE_REPORT_CN.md`。该目录属于生成输出，不作为在线真值源。

| 核查项 | seeds 7/17/27 结果 | 当前判定 |
| --- | --- | --- |
| 中心重规划 lifecycle | 每 seed 6 request、6 no-change ACK、0 applied、0 expired，收敛 0.5 s | P1 状态闭环已完成，保持回归 |
| M-to-N 需求槽 | satisfaction=1.0、unmet=0、错误重复锁=0 | 中心化 demand-slot 与合法多锁已完成 |
| T002 单 primary | 共识帧 4/5/4，每 seed 2 次 D7 终端合同许可 | D3-D5-D7 k=1 链路已闭合 |
| T001 hybrid 2+1 | 双 primary 共识帧均为 0 | P1 未闭合；不得宣称协同末端完成 |
| 二级/无中心 k>1 | 当前 `coalition_fallback_unsupported` 并 fail-closed | P1 待实现 ACK/commit/epoch/lease 原子联盟 |
| 物理拦截 | ComputerVision 不执行 SimpleFlight 控制 | P1 待 90 s、10-seed SimpleFlight 验证 |

实施前统一回归基线：D1 54、D2 57、D3 104（OR-Tools 1 skip）、D4 121、D5 127、D6 68、D7 84、AirSim runtime 75、质点集成 7、跨模块合同 3，均通过。D1-D7 owner 已先行同步各自 PLAN/GAP/review；后续能力变化后必须由同一 owner 再次回写实际状态。

## 2026-07-11 M 对 N 协同拦截调研增量

D1-D7 已分别完成高威胁目标 \(k_j=3\) 的文献、开源实现和模块边界审计，main 汇总见 `subagent_reviews/MAIN_M_TO_N_COOPERATIVE_INTERCEPTION_SYNTHESIS.md`。

以下表格保留 2026-07-11 实施前的调研基线，用于解释任务来源；其状态已被后文“中心化 M 对 N 实施闭环”取代：

| Owner | 实施前 P1 新缺口 | 实施前边界（历史） |
| --- | --- | --- |
| D1/D2 | 多平台共同估计时刻、几何质量、跨节点 track registration、公共信息谱系和 CI | 当前有双时间戳、协方差、GNN/Hungarian 和中心 ID 基础，无协同 Track-to-Track 全链路 |
| D3 | target demand、b-matching/flow、联盟原子激活、角色、同步/波次和版本 | 实施前 Hungarian 仍是一对一 |
| D4 | coalition commit/ACK/lease、缩编/补位/重组、分区和恢复 digest | 当前 CBBA 是单 winner，不支持原子 \(k_j>1\) |
| D5 | planned cooperative lock、over support、多视角几何质量和联盟时序 | 当前多资源同目标可能仍被旧 duplicate 语义误判 |
| D6 | 需求满足、联盟形成、到达离散、波次、协同定位一致性和安全统计 | 需在现有 EpisodeMetrics 上新增 M 对 N 口径 |
| D7 | cooperative 与 independent pair 边界、到达窗口、终端扇区、最小间距和成员退出 | 当前仅有任意 N 个独立 PN/PNG pair |

建议默认研究比较 hybrid 2+1、simultaneous 3、sequential 1+1+1 和 independent PN。只有完成上述合同后才能启用 \(k_j>1\)；否则 D3/D4/D5/D7 断链会成为该新增场景的 P0 blocker。

### 2026-07-11 中心化 M 对 N 实施闭环

上述新增场景的中心化 P0 合同已经闭合，原调研表中的“当前仍是一对一/尚未实现”不再代表当前代码状态：

| Owner | 已完成 | 仍保留的 P1 |
| --- | --- | --- |
| D1 | 2..N bearing-ray 定位、共同估计时刻传播、协方差膨胀、CI 和 lineage 去重 | 真实 AirSim 多视角观测接线与几何阈值标定 |
| D2 | `SourceTrackSummary`、公共时刻马氏/Hungarian 注册、canonical registry、跨节点 ID 指标 | 真实 5v5 replay 与 D1 CI 请求闭环标定 |
| D3 | schema v2、`TargetDemand`、demand-slot Hungarian、all-or-none admission、hybrid 2+1、联盟/计划版本与迟滞 | CP-SAT/MILP 复杂约束参考；OR-Tools 仅为可选 benchmark |
| D4 | 中心有效时验证联盟；中心失效且 `k_j>1` 时 fail-closed，禁止单赢家 CBBA 冒充联盟 | 二级/完全分布式 coalition commit、ACK、lease、补位和重构 |
| D5 | 联盟只读合同、合法三成员锁、超额/版本冲突、reserve standby 门控 | 真实多视角三角定位与跨视角 AirSim 多 seed 标定 |
| D6 | demand/coalition/arrival 记录、需求满足、波次、合法锁、通信和安全指标 | 真实 episode 的 arrival/成员损失/替换证据积累 |
| D7 | 成员级 role/wave/window/version gate；reserve 未激活阻断；PNG 核心公式未改 | 同步到达可达性、终端扇区、最小距离和多 seed 飞行校准 |
| main | `--resource-count M --target-count N`、协同需求 CLI、D3→D5/D4/D7/D6 总线、5v2 3+1 闭环 | 真实 Blocks 5v2 多 seed 与 SimpleFlight 3v1/5v2 长时飞行 |

回归证据：D1 54、D2 57、D3 104（OR-Tools 1 skip）、D4 121、D5 127、D6 68、D7 84、AirSim runtime 75、质点集成 7、跨模块合同 3，全部通过。质点 `cooperative_3v1`/`cooperative_5v2` 的需求满足率为 1.0、shortfall 为 0；main episode bus 的 5-resource/2-target 测试形成 3+1 assignment pair，D5/D7 均保留 4 个独立上下文。中心和二级失效时三机联盟输出 `coalition_fallback_unsupported` 并 hold，不发布伪分布式联盟。

## 2026-07-11 P1 实施与真实 AirSim 结果

详细报告见 `subagent_reviews/MAIN_P1_AIRSIM_RUNTIME_VALIDATION_REPORT_20260711.md`。

| Owner | 实施结果 | 当前证据与结论 |
|---|---|---|
| main/runtime | D2→D3/D5 无 truth 转换、仿真 actor alias 边界隔离、D1-D4 governance/lifecycle、guidance experiment law 回灌 | 5v5/2v2 真机进程运行完成；在线 `truth_id=None` 不再造成 D3 空计划 |
| D4 | truth/continuity unavailable 不触发虚假硬风险，在线风险门限保持 | 中心保持和 distributed 负例通过；secondary 正例仍因 full-view readiness 不足而未闭合 |
| D5 | bbox-only offline truth parser 支持真实 AirSim 输入，truth 不进入在线 tracker | 84 个相机样本接口通过；当前模型 accepted detection=0，效果仍为 P1 |
| D6/main | 四导引律 experiment law 可配对，生成 JSON/CSV/中文报告/曲线 | 21 条指标配对行，只有 seed 7；四律 2 秒均 timeout，不作为命中率结论 |
| D7 | Pure Pursuit、Radar PN、PNG-VM、PNG-TTC 真实 SimpleFlight selector/gate 接入 | PNG VM/TTC switch allowed 约 0.762/0.810；需长时多 seed |

## 2026-07-10 P0/P1 实施与实测结果

本轮继续严格执行 “main 下发、D-agent 自改自测、main 只改 runtime/集成/总文档并运行 AirSim”。

| Owner | 实施结果 | 实测/验收 |
|---|---|---|
| main/runtime | stale D3 plan 被拒后保留当前 plan；YOLO/MOT adapter 跨 episode 重置 stream；AirSim builtin detect 改为匿名 camera-local bbox tracker，局部 ID 不含 actor 名 | `p0_truth_isolation_smoke_20260710` 三 case connected，匿名 ID 连续 5 帧，actor-name online 泄漏为 0 |
| D1 | 复核真实 2v2 双时间戳、协方差 finite/symmetric/PSD 和 NED 合同，无源码回归 | 1528 条观测可回放；32 tests passed |
| D2 | truth-unavailable continuity、rejected-pair replay、covariance validation/diagnostic | 39 tests passed |
| D3 | active plan 后 previous-plan 必填；switch penalty 进入 Hungarian 矩阵；stale plan 保留 | 63 tests passed |
| D4 | 保持 takeover-ready 安全门限，并对 60-case 结果完成状态机诊断 | 84 tests passed；15/1300 决策瞬时 takeover-ready，active plan 为 0 |
| D5 | friend-aware reacquire、actor-name category 隔离、MOT per-stream state/reset | 96 tests passed；匿名 ID smoke 各 case cross-view association=4 |
| D6 | cross-seed/scenario-group 聚合、paired baseline/enhanced、deterministic bootstrap、review labels；拦截 outcome/距离/时间/视觉切换/gate 指标进入 cross-seed | 48 tests passed；D6 报告只把有 intercept evidence 的 full-flow 列入 outcome，execution=18/20，read-only 不再误报 0/20 |
| D7 | 不改 PNG 控制律，复核真实 10-seed guidance/gate 输出 | 45 tests passed；18/20 拦截成功 |

AirSim 证据：

- `outputs/p1_gap_closure_calibration_20260710`：10 seeds、50/200 m、3 个二级节点、110 deg、1920x1080、三 case，共 60 episode。
- `outputs/p1_gap_closure_2v2_multiseed_20260710`：10 seeds、20 pairs，18 collision intercept、2 terminal detection timeout；pair 等权平均最小距离 2.113 m，D6 每 episode 最小值均值 1.812 m。
- D4/D5 的主要未闭合项不是投影或注册，而是 sustained network full-view、逐决策 stable evidence 和 secondary plan activation。
- D7 的主要未闭合项是视觉 gate 通过率和 PN/Pure Pursuit/PNG-TTC/PNG-VM 同 seed 对照，不是 PNG 核心公式重写。

## 2026-07-09 P0 实施结果

本轮严格按 “main 下发、D-agent 自改自测、main 汇总验证” 执行。main 只修改 AirSim runtime/总线桥接和 main GAP 文档；D1-D7 各自只改 owned paths。

| Owner | P0 实施结果 | 验证 |
|---|---|---|
| main/runtime | episode bus 输出 episode clock、scenario config、D1-D7 module health、runtime errors、mission outcome/root cause/performance metadata；D4/D5 stress bridge 正确把二级注册 evidence 输入 D4，并避免把 `registered_to_global_track` 当作拒绝原因；P1 calibration suite/threshold metadata、高度对比和 secondary owner 保持已实现 | `pytest -q research_modules/airsim_runtime/tests/test_blocks_runtime.py` -> 59 passed |
| D1 | sensor health、covariance floor/ceiling reason、timestamp uncertainty、replay summary、latency audit 和区域质量摘要已实现 | 32 passed |
| D2 | motion consistency cost、quality-aware gate baseline、`track_quality/association_risk/quality_metadata` 已实现 | 31 passed |
| D3 | 资源状态细化、high-threat release、结构化 stale rejection、explainable threat baseline 和 assignment evidence export 已实现 | 56 passed |
| D4 | heartbeat smoothing、lease/epoch strictness、secondary capability score、active degradation debounce 和 `secondary_capability_class` 已实现；active secondary plan 同 id/version 回归已修复 | 84 passed |
| D5 | active reacquire、temporal consistency、candidate margin、calibration health metadata 和 detect registration outcome 已实现 | 79 passed |
| D6 | mission outcome、failure reason、top failure causes、eval priority/status/evidence path、performance metrics 和 P1 calibration 标准报告 bundle 已实现 | 38 passed |
| D7 | terminal latch、dwell/release/reacquire grace、filtered LOS rate/outlier reject evidence、3D PN benchmark/log 和 P1 switch/gate calibration fields 已实现 | 45 passed |

`git diff --check` 通过。D2、D6、runtime 的 matplotlib Axes3D warning 为本机环境 warning，不构成 P0/P1。

## 2026-07-09 P1 实施结果

本轮 P1 实施仍按 “main 下发、D-agent 自改自测、main 汇总验证” 执行。D1-D7 各自更新 owned paths 和 GAP/PLAN/README/review；main 只修改 AirSim runtime、测试和 main-level GAP/status。

| Owner | P1 实施结果 | 验证 |
|---|---|---|
| main/runtime | `--p1-calibration-sweep` 输出 suite/version/threshold、二级高度/FOV/数量/站距、expected state fields 和 50/200 m 高度对比；自动生成 D6 `d6_airsim_calibration` bundle；修复 secondary takeover plan 在连续 replan 后 `owner_node_id` 回退为 `d3_central` 的问题 | runtime 59 passed；`p1_gap_fix_smoke_20260709` 生成 6 行 smoke summary |
| D1 | dry-run/replay 增加 schema/version/metadata 检查、latency/OOSM audit 和区域质量摘要 | 32 passed |
| D2 | replay 输出 association risk threshold version、gate pass/reject、risk summary 和 threshold sensitivity | 31 passed |
| D3 | 增加 assignment evidence export、cost breakdown/rejected edges/stale reason/secondary fields 和硬时间窗闭合边拒绝 | 56 passed |
| D4 | 增加二级 readiness/capability class，D7 handoff 需 `takeover_ready` 才放行 active secondary visual PNG | 84 passed |
| D5 | detect-to-global candidate 增加 outcome、reject reason、timestamp/age、projection/covariance 和 YOLO/MOT metadata；`projection_invalid` 独立成因 | 79 passed |
| D6 | AirSim calibration report 保留 scenario/standard mapping/evidence/trend/height bucket/actual scale；Markdown 增加 50/200m、coverage funnel、stable registration、D7 reject 等口径 | 38 passed |
| D7 | runtime/comparison/replay/calibration 输出 terminal range、closing speed、bbox/LOS/maneuver gate、D4 block reason、D5/D3 consistency、secondary capability、threshold advisory version 和 visual PNG switch count；未改 PNG 核心控制律 | 45 passed |

## 1. 总体结论

当前项目已经形成一条可运行的轻量科研主线：

```text
D1 NumPy EKF/FusionAdapter
-> D2 GNN/Hungarian 关联与 ID 指标
-> D3 SciPy Hungarian 分配与迟滞
-> D4 C2Health + 主动/被动降级 + 轻量 CBBA
-> D5 几何投影门控 + 保守 TerminalAssociation
-> D7 PN / SimpleFlight 视觉 PNG gate
-> D6 离线 EpisodeMetrics / JSONL / Blocks replay 评估
```

已经落地的主要是**自研轻量实现和少量成熟 Python 科学计算库**：NumPy、SciPy、OpenCV `projectPoints`、AirSim `simGetDetections` metadata、D5 YOLOv8 + ByteTrack/BoT-SORT/IoU fallback adapter、SimpleFlight 控制、D7 delivery 包中的 YOLO+ByteTrack 可选链路。

**2026-07-08 子智能体复核状态**：D1-D7 已分别重审并更新各自 PLAN/GAP 文件，所有子 GAP 均明确拆分为“已实现、部分实现、未实现、未实现原因、缺少条件、下一步优先级”。本轮确认：D1 的 replay schema v1、legacy JSONL、最小 CSV reader/replay、latency/OOSM audit 和区域质量摘要已实现；D2 的 replay helper、5v5 dense/crossing fixture、风险阈值敏感性和显式 ID 指标已实现；D3 的 D5 feedback writeback、secondary takeover DTO/helper、D7 binding、owner/version/source metadata 和 D6 export 已实现；D4 的主动降级硬/软风险分层、二级节点 lifecycle、secondary takeover metadata、D5 evidence 到 CBBA 和 cost gap helper 已实现；D5 的几何日志、handoff advisory、一致性窗口、truth ID 在线隔离、YOLO/ByteTrack 离线 schema adapter、可运行 YOLOv8 + ByteTrack/BoT-SORT/IoU fallback adapter 已实现；D6 的 execution/contract 双口径、实际规模分组、主动降级精度和 D7 replay 指标已实现；D7 的 runtime bus、comparison/replay helper、N-pair 状态、D4 gate blocking、owner/version gate 和 terminal contract gate 已实现。

尚未落地的主要是**完整外部工程栈或高阶研究对照**：Stone Soup、FilterPy、ROS 2 `tf2/message_filters`、OpenDroneID Core、MAVLink signing 验证、DDS Security、AprilTag、BoT-SORT、Deep SORT、SCRIMMAGE、TrackEval/py-motmetrics、正式 OR-Tools Min Cost Flow、完整 MIT/CA-CBBA 适配、PX4/MAVLink 主线控制。

未实现的共同原因主要有四类：

1. **当前阶段优先轻量可复现**：默认测试不依赖 ROS、Stone Soup、AirSim 实时服务、PX4 或 GPU。
2. **main runtime bus 接口基线已接入**：AirSim runtime 已在同一 episode 中持续写入 D1-D7 summary/record 和 D6 JSONL；2026-07-08 已把执行拦截结果回灌到正式 main bus metrics，接入 D5 feedback、二级接管 owner/version 和 D7 runtime bus，并保留 raw contract metrics；2026-07-09 P1 calibration sweep 已自动回灌 D6 标准 CSV/JSON/Markdown 报告 bundle，且 summary 保留 suite/threshold version 与高度对比；secondary takeover 连续 replan 时 owner 不再回退为中心节点；下一步仍需真实 Blocks 多 seed 校准。
3. **二级侦察看清不等于可接管**：2026-07-08 5v5 registration calibration v2 中，二级云台指向成功率为 1.0，`projection_valid_rate=1.0`，几何门通过率约 0.474，稳定跨视角注册约 51/55/53，cross-view association 为 4/4/5；但 `secondary_network_joint_full_view_frame_rate` 均值仍约 0.048，联合覆盖约 0.771，主要断点是 `not_all_targets_visible` / `network_union_incomplete`。它说明二级节点已能提供有效注册证据，但不能绕过 D3/D4/D5 的分配、仲裁和视觉 PNG gate。
4. **真实图像/通信/身份源仍需标定**：D5 已能运行 YOLOv8 + MOT 并由 main runtime 显式接线；Remote ID、MAVLink signing、AprilTag 仍需要真实报文、密钥和时间同步，YOLO/MOT 仍需要 AirSim 多 seed 阈值标定。
5. **高阶算法需要基准场景支撑**：IMM、JPDA/MHT 完整版、FRPN、MPC、OSPA/HOTA 等应在 5v5 crossing、遮挡、主动降级和 AirSim replay 稳定后再做对照。

## 2. 横向开源/共识方案落地状态

| 共识/开源项 | 预期用途 | 当前状态 | 涉及模块 | 未实现/未完全实现原因 | 缺少条件 | 优先级 |
|---|---|---|---|---|---|---|
| EKF | 融合和航迹滤波主线 | **已实现轻量版**。D1 自研 NumPy EKF，D2 自研二维线性 Kalman | D1, D2 | 未使用 FilterPy/Stone Soup 后端 | 外部库对照接口、三维/非线性量测合同 | P0 已可用，P2 对照 |
| UKF | 强非线性量测升级 | 未实现 | D1, D2 | 当前 EKF/CV 已满足 phase-1；不想提前引依赖 | UKF 后端、sigma-point 参数、强非线性场景 | P2 |
| IMM-EKF/UKF | 高机动目标模型切换 | 未实现 | D1, D2 | 当前场景以 CV/二维基础关联为主 | CV/CA/CT 模型、转移概率、机动基准 | P2 |
| Stone Soup | 多目标跟踪、JPDA/MHT、轨迹融合、指标对照 | **占位/文档级**，未作为运行依赖 | D1, D2, D6 | 默认环境轻依赖；Stone Soup 对象不宜直接污染系统总线 | 安装版本、adapter、对照数据和指标门限 | P2 |
| FilterPy | EKF/UKF/IMM 原型 | **占位/可用性检查**，未调用 | D1, D2 | 已有自研 NumPy fallback | 依赖策略、状态/量测模型、测试容差 | P2/P3 |
| ROS 2 `tf2` | 坐标树、外参、frame 变换 | 未实现 | D1, D5, D7 | 当前是 Python 离线/AirSim runtime，不启动 ROS 图 | ROS 2 runtime、frame tree、带戳消息 | P3 |
| ROS 2 `message_filters` | 多传感器时间同步 | 未实现 | D1, D5 | 当前用 `measurement_timestamp/arrival_timestamp` 和离线 replay | topic schema、同步策略、bag/replay | P3 |
| SciPy `linear_sum_assignment` | Hungarian 关联/分配 | **已实现** | D2, D3 | 不适用 | 仅需保持 SciPy 依赖 | P0 |
| OR-Tools Min Cost Flow | 多容量/复杂约束分配 | 接口预留，未实现 | D3 | 当前 5v5 一对一 Hungarian 足够 | OR-Tools 依赖、容量/需求/禁配边结构 | P1/P2 |
| GNN/Hungarian | 多目标硬关联主线 | **已实现** | D2 | 不适用 | 需增加 5v5 dense/crossing 压测 | P0 |
| JPDA | 密集交叉软关联 | **轻量对照版**，非完整生产级 | D2 | 仅枚举小规模假设，不做完整概率混合更新 | Stone Soup 对照、密集交叉基准、参数标定 | P1 |
| MHT | 多扫描假设跟踪 | **有界 placeholder** | D2 | 完整 MHT 延迟/内存高，不适合资源节点 | N-scan pruning、分簇、中心算力假设 | P2 |
| PN 比例导引 | 单目标/中段默认导引 | **已实现** | D7 | 当前是二维经典 PN 和 SimpleFlight gate | 三维状态、D5/D3 门控、真实飞控约束 | P0 |
| Pure Pursuit | 对照 baseline | **已实现轻量 baseline**。D7 提供 `compute_pure_pursuit_command()` 和 `GuidanceConfig.guidance_law=\"pure_pursuit\"` | D7 | 未直接引入 PythonRobotics，有意保持轻依赖 | 多 seed PN/Pure Pursuit 对照报告、AirSim controlled 选择开关 | P1 已完成基线 |
| 改进 PN / FRPN | 高机动增强导引 | 未实现 | D7 | 当前先稳定经典 PN 与接口 | 目标加速度估计、公式选型、机动场景 | P1 |
| 视觉 PN / PNG | 末端视觉导引 | **部分实现** | D7 | 已有 bbox gate、LOS-rate、TTC/VM，仍非严格纯视觉闭环 | D5 locked、距离/闭合速度估计、相机标定 | P0/P1 |
| AirSim `simGetDetections` | CV 检测框输入 | **已使用** | D5, D7, main runtime | D5 不直接调 AirSim，只消费 fixture/replay；D7/main 调用 runtime | 稳定 detection schema、camera/object ID 映射 | P0 |
| OpenCV `projectPoints` | 图像投影和门控 | **已实现单相机主线**。D5 优先调用 `cv2.projectPoints`，无 OpenCV 时有针孔 fallback，并传播像素协方差 | D5 | 未实现 calibration/solvePnP/跨相机联合优化 | 准确 K/R/t/dist、标定样本、PnP 2D-3D 对应 | P0 已可用，P2 标定增强 |
| OpenCV calibration / `solvePnP` | 相机标定、外参估计 | 未实现 | D5 | 当前假设 AirSim/runtime 提供相机参数 | 2D-3D 匹配点、标定图、PnP RANSAC | P2 |
| YOLOv8 + ByteTrack/BoT-SORT | 局部检测/MOT 默认候选 | **P1 已接入显式运行路径**。D5 `YoloMotAdapter` 可加载 `best.pt`，优先 ByteTrack/BoT-SORT，失败时 deterministic IoU fallback；main runtime 可用 `--detection-backend yolo` 将内存图像送入 D5，并转换为现有 detection contract | D5, main runtime, D7 | 默认仍不保存 PNG；MOT ID 只作为 `LocalVisualTrack.local_track_id`，不得替代 `global_track_id` | AirSim 多 seed 阈值、class id、GPU/CPU 预算、MOT IDSW 标签 | P1 接线已完成，P1/P2 标定 |
| BoT-SORT | 运动相机 MOT | 未实现 | D5 | 需要相机运动补偿、ReID 和检测器链 | 图像序列、依赖、ReID 模型 | P2 |
| Deep SORT | 外观辅助 MOT | 未实现 | D5 | 当前小目标外观未建模 | embedding 模型、图像帧、IDSW 真值 | P2 |
| OpenDroneID / Remote ID | 友方身份正向声明 | **模拟实现** | D5 | 只解析 `protocol=OpenDroneID` 风格 dict，未接 Core C | 报文解码器、白名单、签名/位置一致性 | P1 |
| MAVLink signing | 消息来源认证 | 未在 D5 实现；D7 delivery 有 MAVLink 控制路径 | D5, D7 | 当前没有真实 MAVLink telemetry/signing key 管理 | MAVLink source、签名库、密钥策略 | P2 |
| DDS Security | ROS 2 中间件认证 | 未实现 | D5, main | 当前无 ROS 2/DDS runtime | enclave、证书、权限文件、节点映射 | P3 |
| AprilTag | 合作视觉标签 | 未实现 | D5 | 当前无图像帧和 tag detector | 图像流、tag ID 映射、误检评估 | P2 |
| MIT CBBA / CBBA-Python / CA-CBBA | 分布式降级对照 | 未接入；自研轻量 CBBA | D4 | 外部项目接口/许可证/依赖和 summary bus 不匹配；本轮 P1 明确暂不构造外部开源算法 | adapter、同场景 benchmark、许可证审查 | P2 |
| 拍卖算法 | 分布式保底 baseline | 未单独实现 | D4 | 当前 CBBA 机制覆盖拍卖式思想，但无独立 baseline | bid/award/rollback 协议和测试 | P1 |
| 合同网协议 | 分布式任务协商对照 | 未实现 | D4 | 非 5v5 最小闭环必需 | announce-bid-award 状态机 | P2 |
| SCRIMMAGE | 大规模多智能体仿真 | 未实现 | D6/main | 当前优先 AirSim CV 5v5 和质点仿真 | SCRIMMAGE 输出样例、ID 映射、时钟对齐 | P3 |
| TrackEval / py-motmetrics | HOTA/IDF1/MOTA/MOTP | 未实现 | D6 | 当前先做本地可解释指标 | MOT 格式导出、帧级匹配、依赖版本 | P2 |
| Stone Soup metrics / OSPA/GOSPA/SIAP | 标准跟踪指标对照 | 未实现 | D6 | 需要 D1/D2 Stone Soup Track adapter | cutoff/order、匹配门限、坐标合同 | P2 |
| PX4 SITL / MAVLink body-rate | 更真实飞控闭环 | delivery 包有实验路径，main 未接入 | D7 | 当前主线选 SimpleFlight，避免飞控复杂度 | PX4 SITL、Offboard 状态机、推力/坐标标定 | P2 |

## 3. 各子模块核心结论

| 模块 | 已实现主线 | 关键未实现项 | 直接阻塞条件 | 详细文件 |
|---|---|---|---|---|
| D1 多传感器融合 | `SensorObservation -> NumPy EKF/FusionAdapter -> GlobalTrack`；measurement/arrival timestamp；NED 六维状态；协方差；雷达/声学/EO/合成 LiDAR；延迟补偿；AirSim dry-run；Blocks JSONL reader/replay；replay schema v1/legacy JSONL；最小 CSV reader/replay；`TrackUncertaintySummary`；`LatencyAuditSummary`；`FusionQualityRegionSummary`；source de-dup；N-target 输入 | Stone Soup/FilterPy 后端、UKF/IMM、ROS2 tf2/message_filters、D1 包内真实 AirSim CV 直连、Track-to-Track fusion、更多真实 Blocks/CV fixture | 真实相机/传感器外参、稳定 detection schema、外部依赖、跨节点相关性策略、D6 长期批量 schema | `subagent_reviews/D1_IMPLEMENTATION_GAP_AUDIT.md` |
| D2 数据关联 | GNN/Hungarian、马氏门控、二维 Kalman、轻量 JPDA/MHT、IDSW/连续性、dry-run adapter、`crossing_dense_5v5`、风险滑窗、D1 adapter | 完整 EKF/UKF/IMM、Stone Soup/FilterPy、原生 3D NED、真实 AirSim CV replay 压测 | 5v5 replay 样本、风险阈值、三维跟踪策略 | `subagent_reviews/D2_IMPLEMENTATION_GAP_AUDIT.md` |
| D3 目标分配 | SciPy Hungarian、fallback DP、滚动重分配、迟滞、版本化计划、D5 feedback helper、D7 `AssignmentGuidanceBinding`、`AssignmentValiditySummary`、D6 assignment record export、AirSim dry-run、main episode bus plan/version 输出 | OR-Tools Min Cost Flow、D5 feedback 自动写回真实代价 | D5/D6 重复锁定聚合校准、复杂约束定义 | `subagent_reviews/D3_IMPLEMENTATION_GAP_AUDIT.md` |
| D4 降级接管 | C2Health、被动降级、主动降级、二级侦察节点模型、`SecondaryNodeLifecycleSummary`、CommunicationSummary、主动降级防抖、轻量 CBBA、中心恢复合并、D4 arbitration adapter、D6-compatible event metadata、main episode bus D4 event 写入 | MIT/CA-CBBA 适配、独立拍卖/合同网、真实视频 cue adapter | 二级 heartbeat/coverage/link freshness 的真实 Blocks 多 seed 校准 | `subagent_reviews/D4_IMPLEMENTATION_GAP_AUDIT.md` |
| D5 末端视觉配准 | `GlobalTrack -> CameraModel -> projected image point -> LocalVisualTrack -> TerminalAssociation`；OpenCV `projectPoints`/fallback；马氏门控；保守 `locked/ambiguous/hold/reacquire`；AirSim bbox adapter；YOLOv8 + MOT runtime adapter；truth ID 在线隔离；二级 cue；跨视角摘要；`TerminalConsistencySummary`；视觉 PNG handoff advisory；main episode bus terminal record；禁止改写 ID | Deep SORT/ReID、OpenDroneID Core、MAVLink signing、DDS Security、AprilTag、solvePnP/calibration、ROS2 tf2、跨相机几何联合优化 | 协议报文/密钥、相机标定样本、二级节点真实 pose/detection、真实 AirSim 多 seed YOLO/MOT 阈值标定 | `subagent_reviews/D5_IMPLEMENTATION_GAP_AUDIT.md` |
| D6 评估指标 | 本地 EpisodeMetrics、JSONL、Blocks replay、POD/FAR/RMSE/IDSW/assignment/failover/terminal/communication、D4 active/passive degradation、D7 intercept/guidance time-series adapter、批量图表和分组报告 | Stone Soup metrics、TrackEval、SCRIMMAGE、OSPA/GOSPA/HOTA/IDF1、主动降级必要性标签 | 标准帧级匹配表、真实 D4 metadata、D7 多 seed guidance records/summaries | `subagent_reviews/D6_IMPLEMENTATION_GAP_AUDIT.md` |
| D7 比例导引 | 经典二维 PN、雷达中段 PN、Pure Pursuit baseline、离线 radar->vision 质点闭环、AirSim phase-1 dry-run、SimpleFlight 视觉 PNG gate、TTC/VM 捷联导引核心、D3/D4/D5 terminal contract gate、显式 handoff/hold/reacquire/revoke、N-pair 独立 filter 单测、D6 guidance time-series 字段、main episode bus D7 guidance event 写入 | FRPN/augmented PN、严格 3D PN、严格视觉闭环、PX4/MAVLink 主线、YOLO+ByteTrack 主线检测、MPC/NMPC、ViSP/ROS2 | D5 状态迁移真实标定、相机/距离/闭合速度估计、平台动力学/飞控约束、多 seed 对照 | `subagent_reviews/D7_IMPLEMENTATION_GAP_AUDIT.md` |

## 4. 当前最重要的缺口

### 4.1 已完成的 P0/P1 接口基线

1. **D1 融合合同已成型**
   `SensorObservation`、`measurement_timestamp/arrival_timestamp`、协方差、NED 六维状态、fixed-lag 延迟补偿、雷达距离相关协方差、source lineage 去重、`TrackUncertaintySummary` 和 Blocks JSONL reader/replay 已实现。

2. **D2 关联与身份指标已成型**
   GNN/Hungarian、马氏门控、二维 Kalman、轻量 JPDA/MHT 对照、`id_switch_count`、continuity、duplicate assignment、D1 adapter、AirSim dry-run adapter、`crossing_dense_5v5` 和风险滑窗已实现。

3. **D3 分配到 D7 的版本化合同已成型**
   SciPy Hungarian、fallback DP、迟滞、stale plan 拒绝、版本化 `AssignmentPlan`、D5 feedback helper、`AssignmentGuidanceBinding`、`AssignmentValiditySummary` 和 D6-compatible `AssignmentRecord` 导出已实现。

4. **D4 主动/被动降级仲裁已成型**
   `C2Health`、被动降级、主动降级、二级节点 lifecycle、communication freshness、D1/D2/D3/D5 evidence adapter、D6 event metadata、轻量 CBBA、D7 two-stage secondary handoff 和中心恢复合并基础版已实现。2026-07-07 已增加硬/软风险分层：`d3_assignment_not_current/stale` 仍触发中心重规划，`d3_assignment_cost_margin_low` 与早期 D5 低置信度只进入观察；无 observed mismatch、资源错配、重复锁定或友方冲突的持续 D5 `ambiguous/reacquire` 不再造成名义场景每帧 `request_center_replan` 或分布式降级。

5. **D5 末端视觉配准安全合同已成型**
   OpenCV `projectPoints`/fallback、像素协方差传播、马氏门控、`LocalVisualTrack`、`TerminalAssociation`、`IdentityClaim`、AirSim/YOLO bbox schema adapter、AirSim truth ID 在线隔离、二级 cue、跨视角重复锁定风险、`TerminalConsistencySummary` 和视觉 PNG handoff advisory 已实现。

6. **D6 离线评估主线已成型**
   `EpisodeMetrics` 显式保留实际 `drone_count/resource_count/target_count/camera_count`，并可消费 track/assignment/event/link/terminal、Blocks replay、D4 active/passive degradation、D7 intercept replay、D7 guidance time-series、批量 CSV/Markdown/PNG 报告。

7. **D7 PN/PNG 导引合同已成型**
   经典二维 PN、雷达中段 PN、Pure Pursuit baseline、离线 radar-to-vision 质点闭环、SimpleFlight 视觉 PNG gate、TTC/VM 捷联导引核心、D3/D4/D5 terminal contract gate、handoff/hold/reacquire/revoke 状态和 N-pair 独立 filter 单测已实现。

### 4.2 当前最关键的未闭合项

1. **main runtime bus 已完成接口闭合，仍需真实多 seed 校准**
   `research_modules/airsim_runtime/episode_bus.py` 已由 main 串接 D1 track、D2 risk、D3 plan/version、D4 action、D5 terminal decision、D7 pair state 和 D6 collector，并在每个 Blocks episode 输出 `main_episode_bus.jsonl`、ticks、metrics 和 summary。执行拦截时，main 还会把 `control_commands.csv` 和 `intercept_summary.json` 的成功数、碰撞拦截数、guidance law 和 terminal reject 回灌到正式 metrics，同时保留 contract-only metrics。2026-07-08 已补齐 D5 terminal feedback 到 D3、D4 二级接管 owner/version 到 D3/D7，以及 D7 N-pair runtime summary。2026-07-09 已补齐 P1 calibration sweep suite/threshold metadata、高度对比、D6 标准报告 bundle，并修复 secondary takeover 连续 replan 后 owner 回退问题。未闭合的是在真实 Blocks 长时/多 seed 条件下校准阈值、状态迁移和降级必要性标签。

2. **N-pair 真实控制状态机已有 main 接线，仍需真实多 seed 校准**
   D7 已支持每个 assignment pair 独立 filter，main runtime bus 已按每个有效 pair 注入 `AssignmentGuidanceBinding`、D4 permission/action、D5 `TerminalAssociation`、资源状态、目标估计并写 D6 guidance log。下一步重点不是再补接口，而是在真实 Blocks 多 seed 下校准终端切换、重捕获和拒绝原因分布。

3. **D4/D5/D7 的状态迁移需要真实 episode 校准**
   `locked/ambiguous/hold/reacquire`、锁定丢失、重捕获、friend conflict、duplicate lock、`request_center_replan`、`degrade_to_secondary`、`degrade_to_distributed` 和 terminal contract reject 需要在多 seed AirSim replay 中统一记录与评估。本轮已修正软 cost margin 造成的 replan 抖动，并把“无冲突持续重捕获”与“真实 terminal mismatch”分离，但阈值仍需 5v5/multi-seed 统计确认。

4. **机动高空侦察二级节点仍需覆盖/配准校准**
   5v5 registration calibration v2 已验证二级节点 `mobile_recon_gimbal`、`radar_global_track_cue`、200 m 高差、110 deg FOV 和 1920x1080 观测链路能稳定出图、保持有效投影，并把二级 detect 转成稳定 cross-view registration。当前未闭合的不是姿态/投影，而是二级网络同帧全目标覆盖：`secondary_network_joint_full_view_frame_rate` 均值约 0.048，主要断点为 `not_all_targets_visible` / `network_union_incomplete`。下一步应优先校准二级站位/扫描策略、coverage cell、cue freshness、外参/时间戳和 D6 coverage funnel 指标。

5. **YOLO/MOT 已有显式运行路径，真实协议/标定链路仍待推进**
   D5 YOLOv8 + ByteTrack/BoT-SORT/IoU fallback adapter 和 main `--detection-backend yolo` 接线已完成；Deep SORT/ReID、OpenDroneID Core、MAVLink signing、DDS Security、AprilTag、solvePnP/calibration 和 ROS2 tf2/message_filters 仍需真实图像/报文、密钥、相机外参、时间同步和依赖隔离。

6. **高阶算法仍需作为 optional benchmark 接入**
   UKF/IMM、完整 JPDA/MHT、Stone Soup、FilterPy、OR-Tools Min Cost Flow、MIT/CA-CBBA、TrackEval/py-motmetrics、OSPA/GOSPA/HOTA/IDF1、FRPN、MPC、PX4/MAVLink 都不应直接替换当前轻量主线，应先在同场景对照报告中验证收益。

### 4.3 直接下一步缺口

1. main 继续用 `MainAirSimEpisodeBus` 做 Blocks episode 的统一 DTO/record 总线，并保持 `main_episode_bus.jsonl` 可由 D6 `load_episode_log_jsonl()` 反读。
2. main 在真实 Blocks 多 seed 中校准 D3 `AssignmentPlan`、D3 `AssignmentGuidanceBinding`、D4 action、D5 terminal decision 和 D7 guidance records 的状态迁移阈值。
3. main/AirSim runtime 继续固化 Blocks JSONL/replay schema，保留实际目标数、资源数、相机数、bbox、相机内外参、truth offline label、plan/version、D4/D5/D7 状态字段，并避免在线 D5 使用 truth ID。
4. main/D4/D5/D6 继续跑机动高空侦察节点 5v5 stress，分别统计单相机全局视野率、二级网络联合覆盖率、detect-to-registration 转换率、`secondary_detect_available_but_not_registered` 和 cross-view association。
5. D5 已实现 YOLOv8 + MOT runtime adapter，main 已接入显式 YOLO 检测后端。下一步用真实 AirSim 多 seed 校准 `best.pt`、置信度、tracker backend、目标尺度和 FOV 条件；adapter 只输出 `LocalVisualTrack`，不允许 tracker ID 替代 `global_track_id`。
6. D6 已实现主动降级必要性最小指标口径，main P1 sweep 已自动生成 D6 标准报告 bundle。下一步要求 main/D4 在真实 multi-seed episode 中持续写出 review/window 字段，形成可比较的 active degradation precision 和 unnecessary active degradation count。
7. D6/main 按 patch v2.0 新增 P0-A 口径补齐标准化评估映射最小版：先把当前工程指标映射到 COURAGEOUS、MDPI C-UAS、OCEF 的指标族，并在报告中保留 `standard_metric_family`、`scenario_version`、`evidence_path`、`implementation_status`；完整标准流程、场景库和显著性对比留作 P1。

## 5. 建议实施顺序

1. **保持 P0 合同回归**
   继续用 D3-D7 与 AirSim runtime 测试覆盖 `AssignmentGuidanceBinding`、`D4DecisionRecord`、`TerminalAssociation`、D7 terminal gate 和 D6 intercept adapter。

2. **用 main runtime bus 做真实 episode 校准**
   main 已把 D3 plan/version、D4 action、D5 terminal decision、资源状态和 D7 控制 pair 合并到同一个 AirSim episode state machine，并写入 D6 已支持的分组/降级/guidance 字段；下一步用真实 Blocks 多 seed 校准阈值和报告口径。

3. **跑多 seed 校准**
   使用单次 Blocks 启动 reset 循环跑 CV 5v5、D4/D5 stress 和 2v2 intercept，校准 D4 防抖、D5 一致性、D7 terminal handoff 和 D6 分组指标。

4. **随后做开源对照，不替换主线**
   Stone Soup、FilterPy、TrackEval、ByteTrack、MIT/CA-CBBA、OR-Tools 都建议以 optional benchmark/adapter 方式接入，先生成同场景对照报告，再决定是否进入默认运行路径。

## 6. 子智能体交付文件

- `subagent_reviews/D1_IMPLEMENTATION_GAP_AUDIT.md`
- `subagent_reviews/D2_IMPLEMENTATION_GAP_AUDIT.md`
- `subagent_reviews/D3_IMPLEMENTATION_GAP_AUDIT.md`
- `subagent_reviews/D4_IMPLEMENTATION_GAP_AUDIT.md`
- `subagent_reviews/D5_IMPLEMENTATION_GAP_AUDIT.md`
- `subagent_reviews/D6_IMPLEMENTATION_GAP_AUDIT.md`
- `subagent_reviews/D7_IMPLEMENTATION_GAP_AUDIT.md`

## 7. P0/P1 集中状态与验收

本节合并原独立 P0/P1 状态文档的权威信息。前文保留实现历史和开源落地审计，本节只维护当前优先级、保持项和验收入口。

### 7.1 当前判断

- 未发现新的运行级 P0 blocker。
- 当前 P0 任务是保持跨模块合同、安全门控、truth 隔离、版本拒绝和测试回归不退化。
- 现有 \(k_j=1\) 主线继续可用；M 对 N 的 demand-slot、合法多机锁定、二级/完全分布式原子联盟和成员级 D7 门控合同已实现。
- 历史 ComputerVision 合同验收为 8/10，历史 SimpleFlight 15 s 诊断为 0/30；当前已完成 5 m 成功判据、detect-first truth 隔离、D7 有界外推和 D6 分层指标，下一步是重跑真实 AirSim 多 seed，不再扩展成功语义。
- P2 隔离 benchmark 已覆盖 D1-D7 的当前可运行范围；不可用外部依赖均显式记录 `unavailable_reason`，不得宣称为主线算法替换。

### 7.2 P0 保持矩阵

| Owner | P0 状态 | 必须保持的合同 | 验收 |
| --- | --- | --- | --- |
| D1 | 无新增 blocker | 双时间戳、NED、协方差、OOSM、source de-dup 和 GlobalTrack | D1 模块测试 |
| D2 | 无新增 blocker | GNN/Hungarian、稳定 global_track_id、id_switch_count、continuity | D2 模块测试 |
| D3 | 无新增 blocker | 版本化 AssignmentPlan、迟滞、stale rejection、D7 binding | D3 模块测试 |
| D4 | 无新增 blocker | C2Health、主动/被动降级、二级 lifecycle、lease/epoch | D4 模块测试 |
| D5 | 无新增 blocker | 不改写 global_track_id、truth 隔离、friend/duplicate 保守门控 | D5 模块测试 |
| D6 | 无新增 blocker | 只消费日志；实际规模、id_switch_count 和 unavailable/zero 分离 | D6 模块测试 |
| D7 | 无新增 blocker | 不分配目标；D3/D4/D5 gate 失败时阻断视觉 PNG | D7 模块测试 |
| main/runtime | 无新增 blocker | episode bus 可回放、online 不用 truth ID、默认不保存 PNG | AirSim runtime 测试 |

### 7.3 当前 P1 清单

| Owner | 当前缺口 | 已有基础 | 缺少条件/下一验收 |
| --- | --- | --- | --- |
| D5/D7/main | SimpleFlight 末端检测持续性 | detect-first 几何锁、1 s acquisition grace、0.25 s image KF、3 帧丢失、0.25 s blind push 和 fail-closed expiry 已接线 | 用真实 detect 多 seed 校准重捕率和 `terminal_visual_lost_after_coast` 分布 |
| D7/main/D6 | 5 m 物理接近与导引律长时配对 | NED 三维 `<=5 m`、pair/target/coalition 分层、最小距离和 D6 执行指标已具备 | 完成 2v2 30 s 和 M5N2 90 s、0.1 s 控制周期的 10-seed 实测 |
| D5/main | YOLOv8/native MOT 校准 | adapter 和离线 benchmark 已有，但当前在线明确继续使用 AirSim detect | 等数据集补充后再校准类别、尺度、置信度、GPU/CPU 延时和 tracker 连续性；不阻塞当前 P1 |
| D1/D2/D3/main | 真实 replay 长期治理 | governed schema、offline truth、D2 calibration、增量规划和 N/M mismatch 已具备 | 更长 crossing/遮挡/OOSM replay，冻结 risk/threshold/scenario version 并量化迟滞收益 |
| D4/D5 | 联盟重构和恢复 | 二级/peer 原子 commit、ACK、epoch、lease 与缺 ACK fail-closed 已验证 | member loss/replacement、partition recovery、中心恢复 digest 双轨合并的多 seed 扰动矩阵 |
| D5/D6 | M 对 N 视觉鲁棒性 | 8/10 双 primary 合同验收、planned cooperative lock 和错误 duplicate 分离已实现 | 关闭 seed 7/27 鲁棒性缺口，并验证遮挡、外参漂移和时间偏差下的共识保持 |
| D6/main | 场景库与长期趋势 | cross-seed、paired effect、bootstrap、联盟 lifecycle 和证据路径已具备 | 固化 scenario version，生成长期 CI、失败漏斗和 active-degradation review 趋势 |
| D7 | 协同到达与成员安全 | role/wave/window、active/standby、commit-aware gate 和 N/M topology 已有 | 真实 simultaneous/sequential arrival dispersion、terminal sector、minimum separation 和 member loss |

### 7.4 M 对 N 场景升级条件

required resource count \(k_j>1\) 的合同层升级条件已经满足，后续启用物理协同拦截前仍须满足以下运行级条件：

1. 保持 D3/D4 coalition id、成员、角色、版本、epoch、lease 和原子 ACK/commit 回归不退化。
2. 保持 D5/D6 planned cooperative lock、over-support、错误 duplicate 和 truth 隔离语义不退化。
3. 在真实 SimpleFlight 中验证 D7 simultaneous/sequential/hybrid 到达窗口、成员间距和退出策略，而不修改既有 PNG 核心公式。
4. 用更长真实 replay 验证 D1/D2 canonical registration、lineage 去重和 CI，不让 offline truth 回流在线总线。

### 7.5 统一验收命令

```bash
PYTHONPATH=research_modules/d1_sensor_fusion/src pytest -q research_modules/d1_sensor_fusion/tests
PYTHONPATH=research_modules/d2_data_association pytest -q research_modules/d2_data_association/tests
python3 -m pytest -q research_modules/d3_assignment_planner/tests
PYTHONPATH=research_modules/d4_distributed_fallback python3 -m pytest -q research_modules/d4_distributed_fallback/tests
pytest -q research_modules/d5_terminal_association/tests
pytest -q research_modules/d6_evaluation_metrics/tests
python3 -m pytest -q research_modules/d7_proportional_guidance/tests
pytest -q research_modules/airsim_runtime/tests/test_blocks_runtime.py
git diff --check
```
