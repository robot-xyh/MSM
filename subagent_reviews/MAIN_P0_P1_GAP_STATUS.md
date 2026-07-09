# Main P0/P1 缺口状态汇总

**审计目标**：把 D1-D7 当前 P0/P1 缺口集中到一个 main 可调度清单，避免各模块 GAP 文件之间口径分散。
**审计边界**：本文件只用于科研仿真、接口补齐和后续工程排期；不涉及真实硬件、实机处置、火控、自动处置或授权绕过。
**当前结论**：未发现新的 P0 阻塞断链。2026-07-09 已按 EVAL 确认的 P0-A/P0-B/P0-C backlog 完成最小工程闭合：main runtime episode bus 已补齐统一 clock/config/module health/runtime exception outcome；D1-D7 owner 已分别完成本模块 P0 修复和 README/PLAN/GAP 同步；main runtime 已跟进 D4 新二级能力合同，修正 D4/D5 stress 中二级注册 evidence 桥接和成功注册原因过滤。当前 P0 重点转为保持跨模块合同、安全门控和测试回归不退化。三份 patch 更新到 `EVAL/FRAMEWORK_EVAL_P0_P1_P2_GAP_CONFIRMATION.md` v2.1 后，新增的最高优先级不是替换主线算法，而是把 **D6/main 标准化评估映射最小版** 列为 P0-A 跟踪项：建立 `COURAGEOUS/MDPI/OCEF -> 当前 EpisodeMetrics` 的最小 mapping，并在报告中保留 metric family、evidence path 和 scenario version。2026-07-09 P1 接口补齐已完成一轮：D1-D7 各 owner 已更新本模块 GAP/PLAN/README，main runtime 已补齐 P1 calibration suite/threshold metadata、高度对比汇总、D6 标准报告 bundle 和二级接管 owner 保持。剩余缺口主要为 P1 标定项：真实 AirSim 多 seed 长时标定、二级网络全目标覆盖、YOLO/MOT 阈值校准、通信/身份协议真实适配、标准化报告扩展和 D6 长期趋势报告。

## 2026-07-09 P0 实施闭合复核

- **main/runtime P0-A**：`MainAirSimEpisodeBus` tick/metrics 已携带 episode clock、scenario config、D1-D7 module health、runtime errors、mission outcome、failure reason、top failure causes 和性能预算占位。模块异常故障注入能产出明确 `failed/runtime_exception` outcome。
- **D1 P0-A**：补齐 sensor health summary、协方差 floor/ceiling reason、timestamp uncertainty 元数据与 replay summary。
- **D2 P0-B/P0-C**：GNN/Hungarian 增加 motion consistency 和 quality-aware gate baseline，输出 `track_quality/association_risk/quality_metadata`。
- **D3 P0-B/P0-C**：`ResourceState` 增加 energy/availability/load/history failure/intercept feasibility，迟滞增加 high-threat release 和结构化 stale rejection，补齐 explainable threat baseline。
- **D4 P0-B**：二级节点 heartbeat smoothing、lease/epoch 严格检查、capability score、active degradation hard/soft risk debounce 已完成；同时修复 active secondary plan 与 current secondary plan 同 id/version 时被误判为 non-monotonic 的回归。
- **D5 P0-B**：补齐基于分配目标投影/历史的 active reacquire、时序一致性稳定窗口和校准健康 metadata，不改写 `global_track_id`。
- **D6 P0-A/P0-C**：`EpisodeMetrics` 增加 mission outcome、root cause、eval priority/status/evidence path、模块耗时/延迟/预算字段，并更新 reporting/main bus loader。
- **D7 P0-B/P0-C**：新增 terminal latch、dwell/release/reacquire grace、filtered LOS rate/outlier reject evidence，以及不替代默认 2D PN/PNG 的 3D geometry PN benchmark/log。
- **main-owned bridge**：`d4d5_stress.py` 将二级注册观测纳入 D4 evidence summary，用 D5 投影几何生成二级可信 bbox 中心，并把 `registered_to_global_track` 从 reject reasons 中过滤，避免把成功注册误判为注册断点。
- **本轮验收**：D1 32 passed；D2 31 passed；D3 56 passed；D4 84 passed；D5 79 passed；D6 38 passed；D7 45 passed；AirSim runtime 59 passed；`git diff --check` 通过。D2/D6/runtime 的 matplotlib Axes3D warning 为本机环境 warning，不影响 P0/P1。

## 2026-07-09 P1 接口补齐复核

- **main/runtime**：P1 calibration sweep 写入 `calibration_suite=cv_5v5_d4d5_secondary_coverage`、suite version、threshold version、二级高度/FOV/数量/站距和 expected state fields；汇总报告新增 50 m/200 m 高度对比；自动调用 D6 输出 `d6_airsim_calibration` 标准 CSV/JSON/Markdown bundle。
- **main/runtime secondary takeover**：修正二级接管 plan owner 保持逻辑。若 D4 事件中 legacy source 仍为 `d3_central`，main 按 `target_node_id/selected_secondary_node_id/previous secondary owner/frame secondary names` 选择真实二级节点，避免 secondary plan summary 回退为中心 owner。
- **D1-D7**：各子智能体已按 owned paths 更新本模块 P1 GAP/PLAN/README/review，并完成自测。关键新增包括 D1 replay/latency/region summary、D2 association risk threshold version、D3 assignment evidence export、D4 `secondary_capability_class`、D5 detect registration outcome、D6 calibration trend/height bucket/report mapping、D7 P1 switch/gate calibration fields。
- **smoke 产物**：`research_modules/airsim_runtime/outputs/p1_gap_fix_smoke_20260709/p1_calibration_sweep_summary.json` 和 `P1_AIRSIM_CALIBRATION_SWEEP_REPORT.md` 已生成；row_count=6，包含 50 m/200 m、3 个二级机动高空侦察节点、110 deg FOV、seed=1 的三类 case。
- **smoke 结论**：`projection_valid_rate=1.0`，二级 detect 已能进入注册统计，50 m bbox 均值约 19055 px^2、200 m bbox 均值约 1147 px^2；但 200 m 的同帧全覆盖仍为 0.0，说明下一步仍是多 seed 几何/扫描/coverage 标定，而不是绕过 D3/D4/D5 gate。

## 2026-07-08 文档同步复核

- D1-D7 已按各自 owned paths 同步 `PLAN.md`、`subagent_reviews/Dx_IMPLEMENTATION_GAP_AUDIT.md` 和 review/plan 文件；main 本轮只同步本总表与 `MAIN_IMPLEMENTATION_GAP_AUDIT.md`。
- 最近完整回归自测结果已被 2026-07-09 P0 复核覆盖；旧 2026-07-08 计数只保留为历史基线。
- main runtime P1 sweep 输出已接 D6 标准报告：`p1_calibration_sweep_summary.json`、`P1_AIRSIM_CALIBRATION_SWEEP_REPORT.md` 之外，会自动生成 `d6_airsim_calibration/airsim_calibration_records.csv`、`airsim_calibration_summary.csv`、`airsim_calibration_summary.json` 和 `airsim_calibration_report.md`。
- 最新 AirSim 5v5 D4/D5 registration calibration v2 输出目录为 `research_modules/airsim_runtime/outputs/p1_d4d5_registration_calibration_runtime_v2_20260708*`。本轮 smoke 使用 3 个机动高空二级侦察节点、200 m 高差、110 deg FOV、1920x1080、seed=1；包含 `no_degradation`、`degrade_to_secondary`、`degrade_to_distributed` 三类 case，均 connected。
- D4 动作与预期一致：`no_degradation -> continue_center`，`degrade_to_secondary -> degrade_to_secondary`，`degrade_to_distributed -> degrade_to_distributed`。
- 机动高空侦察节点状态：`secondary_gimbal_pointing_ok_rate=1.0`，`projection_valid_rate=1.0`，`geometry_gate_pass_rate≈0.474`，稳定跨视角注册约 51/55/53，cross-view association 为 4/4/5。bbox mean 约 1150 px^2，当前校准重点是注册链路和覆盖漏斗，不再使用旧固定俯视 bbox 对比作为主结论。
- 未闭合点：`secondary_network_joint_full_view_frame_rate` 均值约 0.048、最佳约 0.143，二级网络平均覆盖约 0.771，主要断点为 `not_all_targets_visible` / `network_union_incomplete`；降级 case 仍有 `secondary_detect_available_but_not_registered≈35`。因此视觉 PNG 仍必须保持 D3/D4/D5 gate，不得因二级节点看清而绕过全局分配和配准合同。

## 2026-07-08 EVAL P0/P1 同步口径

**来源**：`EVAL/FRAMEWORK_EVAL_P0_P1_P2_GAP_CONFIRMATION.md`。

本轮同步只把 EVAL 中已经确认的 P0/P1 缺口落入 `subagent_reviews/*GAP*` 文件。P2/P3 暂不调整。

口径更新如下：

- **运行级 P0 blocker**：仍未发现。当前离线点质模型、AirSim Blocks smoke、D1-D7 module tests 和 main runtime tests 仍可运行。
- **工程化 P0 backlog**：EVAL 确认存在一组进入可信 AirSim 多 seed、复杂降级和后续封闭场地验证前应优先补齐的硬化项。这些不是“当前代码不能跑”，而是“如果不补，结果可信度和故障解释力不足”。
- **P0-A 基础设施可信度**：优先解决统一时间、集中配置、健康状态、异常恢复、D6 outcome/root cause/performance、D1 FDIR-light/协方差边界/时间戳不确定性。
- **P0-B 安全门控与闭环稳定性**：优先解决 D2 track quality/运动一致性、D3 资源状态/迟滞、D4 heartbeat/lease/二级能力/主动降级防抖、D5 重捕获/时序一致性/校准健康、D7 切换迟滞/LOS 滤波。
- **P0-C 场景依赖 P0**：若下一阶段继续做 5v5/N-v-N、高差 200 m、密集交叉或可信二级接管，则 D7 3D PN、D3 threat score baseline、D2 quality-aware gate baseline、Main/D6 priority/status tracking 按 P0 执行；若只做 smoke，可作为 P1。

## 2026-07-09 Patch v2.0 P0/P1 同步增量

**来源**：`EVAL/FRAMEWORK_EVAL_PATCH_ENGINEERING_PRACTICES.md`、`EVAL/FRAMEWORK_EVAL_PATCH_2026_VERIFIED.md`、`EVAL/FRAMEWORK_EVAL_PATCH_WEBSEARCH_2026.md` 已归并到 `EVAL/FRAMEWORK_EVAL_P0_P1_P2_GAP_CONFIRMATION.md` v2.0。

同步原则：

1. 三个 patch 强化了“标准化评估 + 成熟工程栈 + 规避高风险黑盒路线”，但没有推翻当前轻量主线。
2. 成熟外部工具不自动升为 P0。OR-Tools、etcd/Raft、ROS 2/DDS、MLflow、Kalibr、Stone Soup、FilterPy 等作为 P1/P2 对照或后续工程化升级，不作为当前 P0 强依赖。
3. 新增 P0-A 只限定在最小可信闭环硬化：标准化评估映射、复现字段、evidence path、scenario version 和 failure family，不要求一次性复刻完整认证流程。
4. D1-D7 的模块 owned GAP 由各自子智能体同步；main 只维护本文件和 main/system 条目。

### Patch v2.0 新增 P0/P1 主线

| Owner | 优先级 | 新增/强化缺口 | 当前边界 | 验收口径 |
|---|---|---|---|---|
| D6/main | P0-A | 标准化评估映射最小版 | COURAGEOUS、MDPI C-UAS、OCEF 不作为完整认证流程，只做当前指标族映射 | 输出 `engineering_metric -> standard_metric_family`、`scenario_version`、`evidence_path`、`implementation_status`，并能映射到当前 `EpisodeMetrics` |
| main/runtime | P0-A | 复现纪律和 evidence path 强化 | 固定 seed、settings、算法版本、检测后端、资源/目标数量已由 runtime/D6 metadata 承载，需保持不退化 | 每个 episode 目录可追溯 settings、seed、module health、runtime exception、metrics/report 路径 |
| D6/main | P1 | COURAGEOUS/MDPI/OCEF 完整标准化报告 | P0 只做最小 mapping；完整标准阶段、场景标签、测试矩阵和复现纪律为 P1 | Markdown/CSV/JSON 报告包含标准指标族、测试阶段、复现字段和 evidence link |
| D6/main | P1 | baseline vs enhanced 统计对比 | 当前报告已有分组统计和 95% CI 基础字段，显著性/A-B 口径仍需沉淀 | 同场景多 seed 输出 baseline/enhanced 均值、方差、置信区间和差异结论 |
| D6/main | P1 | 标准场景库和 CI 回归摘要 | 当前 scenario metadata 可写入，尚未形成统一场景库治理 | 场景记录包含 tags、difficulty、expected failure modes、actual scale、seed matrix 和回归状态 |
| main/runtime | P1 | ROS 2 replay 原型 | 不重写当前 Python/AirSim runtime，只做离线 replay 原型规划 | 能把已写盘 JSONL/CSV 映射为 ROS 2 风格 replay schema，保持当前测试不依赖 ROS |
| main/runtime | P1 | 结构化日志和配置治理 | 当前 JSONL/metadata 保留，后续明确 schema/version/config provenance | episode 输出 schema version、config version、module version 和 structured event fields |
| main/runtime | P1 | Docker Compose 开发部署 | 仅用于本地多进程实验，不作为生产部署 | 可复现实验服务组合；不替代单机 Python test/Blocks runtime |

### EVAL 确认的工程化 P0 Backlog

| Owner | P0 类型 | 缺口 | 最小范围 | 验收口径 |
|---|---|---|---|---|
| main/runtime | P0-A | 统一时间管理 | 统一 `episode_time`、`measurement_timestamp`、`arrival_timestamp`、`publish_timestamp`、`processing_timestamp` 和 clock source | D1-D7 records 能按同一 episode clock 对齐，D6 输出 latency breakdown |
| main/runtime | P0-A | 集中配置管理 | 一个 scenario config 生成 AirSim settings、模块参数、seed、资源/目标数量和 D6 metadata | 同一 config 可复现实验目录、settings 和报告字段 |
| main/runtime | P0-A | 健康监测 | 每个模块输出 lightweight health/status snapshot | episode 中可见 D1-D7 health、record count、last update age、error state |
| main/runtime | P0-A | 异常处理与恢复 | 模块异常、输入缺失、AirSim RPC 异常输出明确 failed/degraded outcome | 故障注入后系统不中断或产出明确 failed outcome 和 root cause |
| D6 | P0-A | 系统级任务成功指标 | 定义 `mission_outcome=success/partial/failed/aborted`、success/failure reason | 每个 episode 有系统级 outcome，并能关联 D1-D7 指标 |
| D6 | P0-A | 根因诊断 | 基于已写盘 records 输出 top failure causes | 报告输出 tracking、assignment、terminal gate、guidance、coverage 等 top causes |
| D6 | P0-A | 性能监测 | 记录模块耗时、loop latency、record latency、CPU/GPU 预算占位 | episode 输出模块耗时、延迟分布和性能回归标记 |
| D6/main | P0-A | 标准化评估映射最小版 | 建立 `COURAGEOUS/MDPI/OCEF -> 当前 EpisodeMetrics` 的最小指标族映射 | 报告输出 standard metric family、engineering metric、scenario version、evidence path 和 implementation status |
| D1 | P0-A | FDIR-light | 传感器级 health、漂移/偏置/丢包/延迟异常计数和隔离建议 | 故障注入下输出 sensor health、fault reason、reject count、恢复状态 |
| D1 | P0-A | 协方差上下界限制 | 对外推、低质量观测、遮挡和异常观测设置 covariance floor/ceiling 与 reason | 协方差不发散、不虚假收敛，并能由 D6 解释 |
| D1 | P0-A | 时间戳不确定性建模 | timestamp uncertainty 进入观测/summary 和质量指标 | 注入 10-50 ms 漂移时输出 timing uncertainty 与误差变化曲线 |
| D2 | P0-B | 航迹质量评分 | 输出 `track_quality` / `association_risk` 给 D3/D5/D6 | 每条 track 有 quality，D3/D5/D6 可消费 |
| D2 | P0-B | 运动一致性约束 | GNN/Hungarian 代价加入速度方向、加速度异常或短时历史一致性 | crossing/dense replay 输出 motion consistency score 并参与代价 |
| D3 | P0-B | 资源状态细化 | 增加 energy、availability、intercept feasibility、current load、history failure | ResourceState 影响分配，D6 可解释资源不可行原因 |
| D3 | P0-B | 增强迟滞逻辑 | 加入切换成本、min dwell、release condition、stale rejection | 重分配次数下降，高威胁目标不因迟滞漏分配 |
| D4 | P0-B | Heartbeat 平滑 | 短时丢包/延迟用滑动窗口和 suspect/degraded 防抖 | 丢包/延迟注入下误 failover 下降 |
| D4 | P0-B | Lease 严格管理 | 二级 plan lease、epoch、过期拒绝、恢复双轨审计 | 过期二级 plan 不被 D7/main 执行，恢复后有双轨审计 |
| D4 | P0-B | 二级能力评估 | 基于 coverage/freshness/stable registration/not-registered 输出 capability score | 区分“可见、已注册、可接管”，并进入 D6 |
| D4 | P0-B | 主动降级防抖 | 校准 dwell/release、hard/soft risk 和 review label | active degradation false trigger rate 可统计并下降 |
| D5 | P0-B | 主动重捕获 | 基于预测投影、bbox 历史和搜索窗口支持 reacquire，不改写 `global_track_id` | 遮挡后 reacquire 恢复帧数下降，且不改写 ID |
| D5 | P0-B | 时序一致性 | bbox/MOT 历史、candidate margin、稳定窗口增强 | terminal locked 率提升，误锁仍为 0 |
| D5 | P0-B | 相机校准健康监测 | 输出 reprojection error、camera pose source、calibration health、drift warning | D6 可见 projection_valid、reprojection_error、calibration_health |
| D7 | P0-B | 末端切换迟滞 | 视觉 PNG 切换加入 dwell、release、reacquire grace、reject reason | terminal mode switch 次数下降，reject reason 可解释 |
| D7 | P0-B | LOS 角速率滤波 | LOS rate 低通、限幅、异常值拒绝 | 输出 filtered LOS rate，近距命令不出现尖峰 |
| D7 | P0-C | 三维 PN baseline | 高差/3D 场景下实现 3D 几何 PN 对照和日志 | 200 m 高差或 3D target 测试中输出 3D PN 指标 |
| D3 | P0-C | 动态威胁 baseline | 可解释 threat score：关键区接近、TTC、速度、协方差 | N/M 不匹配或资源不足场景可解释高威胁优先级 |
| D2 | P0-C | quality-aware 自适应门控 baseline | 基于 track quality / density 调整门限的轻量规则 | dense/crossing/遮挡场景中 ID switch 与误关联下降 |
| Main/D6 | P0-C | 实施状态追踪字段 | D6 报告加入 `eval_priority`、`implementation_status`、`evidence_path` | 后续报告能追踪 EVAL 建议等级和项目实现状态 |

### EVAL 确认的 P1 Backlog

| Owner | P1 缺口 | 当前边界 | 验收口径 |
|---|---|---|---|
| D1 | IMM 多模型滤波 | CV/EKF 主线可用，机动目标误差仍是风险 | CV/CA/CT 或等价模型对照，机动 RMSE 下降 |
| D1 | 场景自适应协方差 | 基础距离/质量协方差已有，遮挡/杂波/SNR/来源差异规则不足 | replay 中输出 covariance scale reason |
| D2 | 完整自适应门控策略 | P0-C 只保留 quality-aware baseline | 按密度、quality、协方差一致性自动调整门控并报告 sensitivity |
| D2 | 工程化 JPDA | 当前轻量 JPDA 不是完整工程实现 | dense/crossing replay 下 JPDA 与 GNN 同场景对比 |
| D2 | N/M 初始化优化 | 当前状态机可用，虚假航迹率/初始化延迟需标定 | 输出 false track rate、init latency 多 seed 统计 |
| D2 | 协方差一致性检查 | 当前主要消费 D1 covariance | 输出 NEES/NIS 或等价 consistency flag |
| D3 | 完整动态威胁评估 | P0-C 保留 explainable threat baseline | threat model 可解释 TTC、保护区、速度、类别、协方差和资源状态 |
| D3 | 增量分配 | 当前滚动重算可用 | 新目标/资源失效时 plan update latency 下降 |
| D3 | 时间窗口硬约束 | 当前有窗口代价，缺硬拒绝 | window closed 的边不会被分配 |
| D3 | OR-Tools Min Cost Flow 接口 | Hungarian 主线稳定，OR-Tools 仍为预留 | 同输入输出 min-cost-flow 对照计划 |
| D4 | 网络分区检测 | 当前关注中心/二级/分布式，脑裂检测不足 | 网络分区注入下输出 partition state 和 conflict count |
| D4 | Raft/Leader 选举对照 | 当前轻量接管/CBBA，无成熟选举对照 | 选举与二级接管日志可复现，不绕过执行合同 |
| D4 | DDS QoS/通信策略 | 当前通信为仿真消息合同 | 丢包、优先级、stale link 可由 D6 统计 |
| D5 | 多模态友方识别 | `IdentityClaim` 仍主要是仿真/接口 | 至少一个 replay adapter 输出 verified/stale/unverified |
| D5 | 完整相机在线标定 | P0-B 只做校准健康监测 | 标定样本中估计外参漂移并降低重投影误差 |
| D5 | 畸变校正 | 当前以针孔/OpenCV 投影为主 | 畸变参数进入 projection，重投影误差下降 |
| D5 | ReID 辅助 | YOLO/MOT 可接线，无 ReID 外观特征 | 遮挡恢复和密集目标 ID continuity 提升 |
| D6 | 基线对比框架 | 指标报告已有，A/B 和显著性不足 | 同场景输出 baseline vs enhanced 表格 |
| D6 | 场景库管理 | scenario 有但覆盖率管理不足 | 标准场景库带 tags、seed、difficulty、expected failure modes |
| D6 | CI/回归测试 | 当前手动测试为主 | 每次变更产出测试矩阵和性能回归摘要 |
| D6/main | COURAGEOUS/MDPI/OCEF 完整标准化报告 | P0 只要求最小 mapping，完整标准流程和阶段化测试为 P1 | 报告包含标准指标族、测试阶段、复现纪律字段和 evidence link |
| D7 | APN 目标机动补偿 | P0-B 先做 LOS 滤波与切换迟滞 | 机动目标 miss distance 下降且不破坏 D3/D4/D5 gate |
| D7 | 最优制导律 OGL 对照 | PN/PNG 主线可用，OGL 未实现 | OGL 作为研究对照，不替代 PN |
| D7 | 预测拦截点 | PN 视线率主线，预测点不足 | 输出 predicted intercept point，与 PN 对比 |
| D7 | 动力学补偿 | SimpleFlight 简化，执行延迟/加速度限制不足 | 命令饱和、响应延迟进入 guidance log |
| main/runtime | ROS 2 节点化规划/小规模原型 | 现阶段不重写 Python/AirSim runtime | 离线 replay 节点原型保持现有 Python tests |
| main/runtime | 事件驱动架构 | episode bus 已有记录流，运行时仍偏串行 | 事件 schema 和 replay consumer 稳定 |
| main/runtime | 状态机标准化 | 各模块有状态，统一状态合同不足 | 状态枚举、transition reason、invalid transition 进入日志 |

## P0 状态

| 模块 | P0 状态 | 保持口径 | 验收 |
|---|---|---|---|
| D1 | 无新增 P0 blocker | `SensorObservation` 必须保留 `measurement_timestamp`、`arrival_timestamp`、协方差、NED 状态和 `GlobalTrack` 输出；fixed-lag/OOSM 与 source de-dup 不退化 | `PYTHONPATH=research_modules/d1_sensor_fusion/src pytest -q research_modules/d1_sensor_fusion/tests` |
| D2 | 无新增 P0 blocker | GNN/Hungarian、马氏门控、稳定 `global_track_id`、`id_switch_count`、continuity 和 duplicate assignment 指标不退化 | `PYTHONPATH=research_modules/d2_data_association pytest -q research_modules/d2_data_association/tests` |
| D3 | 无新增 P0 blocker | `AssignmentPlan` version、Hungarian/fallback DP、迟滞、stale/rejected plan、D7 binding 和规模字段不退化 | `python3 -m pytest -q research_modules/d3_assignment_planner/tests` |
| D4 | 无新增 P0 blocker | `C2Health`、主动/被动降级、二级节点 lifecycle、D5 distributed visual evidence 到 CBBA 风险加权、D6 event metadata 不退化 | `PYTHONPATH=research_modules/d4_distributed_fallback python3 -m pytest -q research_modules/d4_distributed_fallback/tests` |
| D5 | 无新增 P0 blocker | D5 不分配、不授权、不创建/改写/换绑 `global_track_id`；online 不使用 AirSim truth ID；friend conflict 和 duplicate risk 保守 hold/ambiguous | `pytest -q research_modules/d5_terminal_association/tests` |
| D6 | 无新增 P0 blocker | D6 只消费日志，不参与控制；显式保留 `id_switch_count` 和实际 `drone/resource/target/camera` 规模字段 | `pytest -q research_modules/d6_evaluation_metrics/tests` |
| D7 | 无新增 P0 blocker | D7 不分配、不授权、不改写 `global_track_id`；D3/D4/D5 gate 失败时阻断视觉 PNG | `python3 -m pytest -q research_modules/d7_proportional_guidance/tests` |
| main/runtime | 无新增 P0 blocker | AirSim runtime 不保存 PNG 默认截图；online D5 association 不使用 truth ID；D1-D7 record/summary 总线保持可回放 | `pytest -q research_modules/airsim_runtime/tests/test_blocks_runtime.py` |

## P1 缺口清单

| Owner | P1 缺口 | 当前状态 | 缺少条件 | 验收口径 |
|---|---|---|---|---|
| main | 统一 AirSim episode bus 多 seed 校准 | `MainAirSimEpisodeBus` 已接入 D1-D7 summary/record；2026-07-08 已将真实 D7 控制执行指标合并到正式 `main_episode_bus_metrics.json`，保留 raw contract metrics，并补齐 D5 feedback、二级接管、D7 runtime bus 字段；P1 calibration sweep 已自动回灌 D6 标准 CSV/JSON/Markdown 报告 bundle，并写入 suite/threshold version 与高度对比；`p1_gap_fix_smoke_20260709` smoke 已通过 | 稳定 episode 目录、seed/scenario 命名、真实 Blocks 多 seed 阈值和状态迁移校准 | 多 seed 报告能按 seed/scenario 汇总 D3/D4/D5/D7/D6 指标，并区分 contract 与 execution 指标 |
| D1/main | D1 replay schema version、CSV reader、更多 Blocks fixture | **P1 基线已补齐**：replay schema v1、legacy JSONL 兼容、最小 CSV reader/replay 已实现 | 更多真实 Blocks/CV fixture、D6 长期批量字段、长期回归样本 | D1 能读取带 version 的 replay fixture，D6 可追踪 observation latency/OOSM |
| D1/D4/D6 | 区域质量摘要和 OOSM 审计字段 | **P1 基线已补齐**：`LatencyAuditSummary` 和轻量 `FusionQualityRegionSummary` 已实现 | 区域时间窗口、协方差增长率窗口、D6 长期趋势字段 | D4 可消费区域级不确定度；D6 可输出 OOSM/latency 统计 |
| D2/main/D6 | 真实 5v5 AirSim replay 的 association log 和 risk threshold 校准 | **P1 基线已补齐**：D2 replay helper、AirSim-like replay、threshold sensitivity 和 risk split 已实现 | 真实 replay、truth offline labels、阈值版本、D6 grouped report | 输出 IDSW、continuity、risk summary 和 threshold sensitivity |
| D3/main/D4 | `request_center_replan` 后新 plan owner/version 闭环 | **P1 基线已补齐**：main 监听 D4 `request_center_replan`，下一规划周期强制 D3 生成新 version，并写入 `replan_reason/supersedes_plan_id/supersedes_plan_version/active_plan_owner=center`；secondary takeover replan 会保持真实二级 owner，不再回退为 `d3_central`；D7 gate 继续按当前 binding/version 放行或拒绝 | 仍需真实 Blocks 多 seed 校准 | D4 request/replan 后 D3 发布新 version，D7 只接受当前 version；名义场景不能因软 cost margin 每帧 replan；secondary plan summary 的 owner 为真实二级节点 |
| D4/main/D3/D5 | 主动降级过敏抑制 | **P1 基线已补齐**：D4 已将 `d3_assignment_not_current/stale` 作为硬风险，将 `d3_assignment_cost_margin_low` 作为软风险；软 margin + 早期 D5 low confidence 只 `continue_center/observe_more`；持续 D5 `ambiguous/reacquire` 若无 observed mismatch/资源错配/重复锁定/友方冲突，则不触发分布式降级 | 真实 Blocks 多 seed 下的 threshold、dwell/release 和 review label 校准 | 名义 2v2/5v5 不应全帧 `request_center_replan` 或 `degrade_to_distributed`；硬 stale/not-current 和真实 terminal mismatch 仍触发仲裁 |
| D3/D5/main | D5 feedback 写回下一轮 D3 代价 | **P1 基线已补齐**：D3 feedback helper 已接入 main runtime bus，输出 `d3_terminal_feedback_writeback`，无冲突 ambiguous/reacquire 不再误触发 operator hold | 真实多 seed 下 duplicate/friend/fov/feasibility metadata 阈值校准 | D5 feedback 能生成 `operator_hold/prohibited_edges/fov_difficulty` 输入 |
| D4/main/D3/D7 | 二级接管 plan version 与 D7 two-stage handoff | **P1 基线已补齐**：D4 secondary takeover metadata、D3 secondary plan owner/version、main secondary owner 保持、D7 owner gate 和 controlled 2v2 visual PNG 回归已通过 | 真实 Blocks 多 seed 的 secondary heartbeat/link freshness 校准 | `degrade_to_secondary` 阶段 1 阻断 visual PNG，阶段 2 新 plan 生效后才放行；secondary plan `owner_node_id` 必须是可用二级节点 |
| D4/D5/main/D6 | 机动高空侦察二级节点覆盖与接管必要性 | **P1 接线已补齐，校准未闭合**：2026-07-08 registration calibration v2 中 radar cue + gimbal 指向正常，`projection_valid_rate=1.0`，稳定跨视角注册约 53，cross-view association 均值约 4.33；2026-07-09 smoke 进一步输出 50/200 m 高度对比和 D6 bundle。瓶颈仍是 200 m/高动态下 `not_all_targets_visible/network_union_incomplete`，不是投影链路断开 | 二级节点站位/扫描策略、target grouping、coverage cell、heartbeat/link freshness、review label、plan activation delay 和 D6 长期趋势 | D6 报告能同时输出单相机全局视野率、二级网络联合覆盖率、coverage funnel breakpoint、接管必要性和误降级率 |
| D4/D3/D6 | CBBA vs 中心 Hungarian cost gap | **P1 基线已补齐**：D4 已有 `CBBACostGapBenchmark` helper | 同 episode 保存 D3 center cost matrix/current plan；D6 cost gap 长期聚合 | 同场景输出 completion/conflict/cost gap/rounds/messages |
| D4 | 独立 auction baseline 是否后置 | 未单独实现；当前 CBBA 覆盖 winner/bid 思想 | bid/award/rollback 协议和测试预算 | 若进入 P1/P2，需与 CBBA 同输入对照；默认本轮不实现 |
| D5/main/D6 | AirSim geometry、TerminalConsistencySummary 全量写盘 | **P1 基线已补齐**：D5 geometry log fields、handoff advisory、consistency 连续窗口和 main event/snapshot 字段已接入 | 真实多 seed 下 projected pixel、Mahalanobis、duplicate risk 的长期统计 | D6 能按 episode/seed 统计 terminal lock、ambiguous、hold、duplicate risk 和重捕获连续性 |
| D5/D4/main | 多相机/二级视角 detect 到 global track 的跨视角配准 | **P1 metadata-only 基线已补齐，真实转换未闭合**：D5 有 `TerminalObservationBus`、`CrossViewAssociation`、`TerminalCrossViewFusion` 和覆盖漏斗诊断；最新 stress 中二级 detect 可见但未转成有效 cross-view 支持 | 多相机外参/时间同步、二级 cue 重投影、D2/D3 binding、稳定 bbox/MOT、全局航迹投影门限和离线 truth label 校准 | 降级 case 不再停留在 visible-only，`secondary_detect_available_but_not_registered` 显著下降，cross-view association 可被 D4/D6 消费 |
| D5/D7 | 视觉 PNG 前置证据合同固化 | **P1 基线已补齐**：D5 handoff advisory、D7 D3/D4/D5 gate、center/secondary controlled intercept owner/version 回归均通过 | 真实 bbox 稳定窗口、measurement age、duplicate risk、friend conflict 多 seed 校准 | D7 仅在 D5 locked、assigned ID 一致、D3/D4 gate 通过时视觉 PNG |
| D5/main | YOLOv8 + MOT detector adapter | **P1 基线已补齐**：D5 可加载 `best.pt` 运行 YOLOv8，优先 ByteTrack/BoT-SORT，缺依赖时 deterministic IoU fallback；main runtime 可用 `--detection-backend yolo` 将内存图像送入 D5 adapter | 真实 AirSim 多 seed 目标尺寸、置信度、tracker backend 和 FOV 阈值标定 | adapter 只输出 `LocalVisualTrack`，tracker ID 不替代 `global_track_id` |
| D6/main | D4/D5/D7 产物统一回灌 | **P1 基线已补齐**：执行拦截时，main 将 `control_commands.csv` 和 `intercept_summary.json` 中的成功数、碰撞拦截数、guidance law、terminal reject 等回灌到正式 main bus metrics；raw contract metrics 单独保留。P1 sweep 已自动调用 D6 `AirSimCalibrationReportGenerator` 扫描 sequence/episode artifacts 并输出标准 CSV/JSON/Markdown bundle | episode clock、records merge order、review label 和真实多 seed 报告数据 | `EpisodeMetrics` 能从一个 episode 目录汇总 Blocks/D4/D5/D7 指标，且执行前 contract 指标与执行后 intercept 指标不混淆；P1 sweep 目录包含 D6 标准报告 |
| D6 | 主动降级必要性/精度 | **P1 基线已补齐**：`metric_scope`、`active_degradation_precision`、`unnecessary_active_degradation_count` 和 review label/后验最小口径已实现 | 真实 episode 持续写出 review/window 字段 | 输出 active_degradation_precision 和 unnecessary_active_degradation_count |
| D7/main/D6 | N-pair runtime bus 与多 seed PN/Pure Pursuit/PNG 对照 | **P1 基线已补齐**：D7 `runtime_bus.py`、`comparison.py`、`replay.py` 已实现，main 已注入每 pair D3/D4/D5 状态并写 D7 runtime summary | 真实多 seed grouped guidance report | 多 seed 报告输出 min range、mode switch、terminal reject、visual PNG switch |
| D7/D5/main | YOLO/MOT 到 D7 bbox/LOS gate | **P1 接线已补齐**：D5 运行 adapter 输出 `LocalVisualTrack`，main runtime 将 YOLO/MOT track 转为现有 detection contract，D7 bbox/LOS replay 可消费 YOLO/ByteTrack 或 AirSim bbox schema | 真实图像/检测框回放、失败回退策略、多 seed 样本 | replay 可生成 D7 gate 摘要；默认控制仍需 D3/D4/D5 gate 全部通过 |

## 本轮 Subagent 补充规则

1. D1-D7 只修改各自 owned paths。
2. 本轮默认补文档/GAP 状态，不引入外部开源算法或强依赖。
3. 若发现真正 P0 blocker，只在本模块 GAP 中标为 blocker 并汇报 main，不跨模块实现。
4. P2/P3 项保留在 GAP，不进入本轮执行。
5. 所有模块继续遵守：不写死 2v2/5v5，不改写 `global_track_id`，D6 不控制系统，main 统一 AirSim runtime。

## Main 验收

```bash
git diff --check
git status --short
pytest -q research_modules/airsim_runtime/tests/test_blocks_runtime.py
python3 -m pytest -q research_modules/airsim_runtime/tests/test_blocks_runtime.py::test_controlled_5v5_active_center_replan_visual_png research_modules/airsim_runtime/tests/test_blocks_runtime.py::test_controlled_2v2_active_degradation_secondary_plan_visual_png
```
