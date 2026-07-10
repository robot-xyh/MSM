# Main P0/P1 缺口状态汇总

**审计目标**：把 D1-D7 当前 P0/P1 缺口集中到一个 main 可调度清单，避免各模块 GAP 文件之间口径分散。
**审计边界**：本文件只用于科研仿真、接口补齐和后续工程排期；不涉及真实硬件、实机处置、火控、自动处置或授权绕过。
**当前结论**：未发现新的 P0 阻塞断链。2026-07-10 已在既有 P0-A/P0-B/P0-C 闭合基础上继续修复 active-plan stale 合同、truth-unavailable D2 风险、D5 友方重捕获和 AirSim 在线局部 ID 泄漏；真实 AirSim 已完成 D4/D5 5v5 60-case 校准与 2v2 SimpleFlight 10-seed 拦截基线。当前 P0 重点是保持跨模块合同、安全门控和测试回归不退化。剩余缺口已经收敛为 P1：二级节点从 `registration_usable` 到可执行 secondary plan 的状态闭环、真实 YOLO/MOT 标定、CV 5v5 D1/D2/D3 阈值治理、D7 多导引律配对对照、D6 长期趋势/场景库和通信/身份真实适配。

## 2026-07-10 P0/P1 实施与 AirSim 多 Seed 复核

- **P0 truth 隔离闭合**：main runtime 为 AirSim builtin detect 增加匿名 camera-local bbox tracker；`local_track_id/detection_id` 不含 actor 名，actor 名只作为 `offline_truth_*` 标签。`outputs/p0_truth_isolation_smoke_20260710` 三类 case 均连接，匿名 ID 连续 5 帧，跨视角关联均为 4。D5 owner 已复核并将该项转为保持回归。
- **D2/D3/D5 可信合同补强**：D2 无 truth continuity、rejected pair replay 和协方差校验已补齐；D3 active plan 后强制 previous plan，stale rejection 保留当前 plan，switch penalty 在 Hungarian 前计入；D5 reacquire 友方门控与 MOT stream 隔离已补齐。
- **D6 多 seed 统计基线**：cross-seed 聚合按稳定 `scenario_group`，baseline/enhanced 使用同 seed 配对，bootstrap CI 固定随机种子，execution/contract evidence 分离。
- **5v5 D4/D5**：`outputs/p1_gap_closure_calibration_20260710` 共 60 个真实 AirSim episode。50 m 网络平均覆盖约 0.687、joint full-view 约 0.044；200 m 网络平均覆盖约 0.725、joint full-view 约 0.003。20 个 secondary case 均未激活 secondary plan；1300 条 D4 决策中只有 15 条瞬时 `takeover_ready`，且全部停在 pending。
- **2v2 SimpleFlight**：`outputs/p1_gap_closure_2v2_multiseed_20260710` 共 10 seeds/20 pairs，18 个碰撞拦截、2 个末端检测超时，成功率 90%；主要门控为 D5 未锁定、机动裕度、bbox 边缘和 D4 重分配等待。
- **剩余 P1**：D4 逐决策 stable/not-registered evidence 接线、持续 full-view 与 secondary plan activation；D5 YOLO/MOT 多 seed；D7 PN/Pure Pursuit/PNG-TTC/PNG-VM 对照；D6 长期趋势与场景库。D6 拦截指标 cross-seed 输出已闭合。

## 下一阶段 P1 实施顺序

当前没有新的运行级 P0 blocker。下一阶段不引入 P2/P3 重型依赖，按以下顺序补齐：

1. **D4/D5/main 二级接管执行闭环**：把 D5/D6 的逐决策 `stable_cross_view_registration_count/not_registered_count/network_full_view` 接入 D4，构造持续 full-view fixture，闭合 `registration_usable -> takeover_ready -> pending_secondary_plan -> secondary_plan_active`，同时验证 lease/epoch/stale rejection。
2. **D5/main 真实 YOLO/MOT 校准**：使用 `best.pt` 和无人机 mesh，在 50/200 m、遮挡、交叉和多视角场景跑 ByteTrack/BoT-SORT 多 seed；统计 detector recall、local ID continuity、cross-view registration、CPU/GPU 延迟和 AirSim detect 回退。
3. **D7/main/D6 导引律配对对照**：增加 runtime law selector，在相同 seed/初始几何下对比 Pure Pursuit、radar PN、PNG-VM、PNG-TTC；保持 `png_guidance_delivery` 核心控制律不改，只校准切换、相机边缘、机动裕度和 detection timeout。
4. **D1/D2/D3 真实 5v5 总线治理**：main writer 补 `schema_version/coverage_cell/config provenance`；D1 校准预期延迟和 OOSM health；D2 用 offline truth 评估 IDSW/NIS/NEES 和初始化；D3 校准 D5 feedback、N/M mismatch、迟滞与 threat 权重。
5. **D6 场景库与 CI 趋势**：把上述批次固化为带 tags/difficulty/expected failure mode 的场景库，生成跨提交回归摘要、长期趋势和标准化 evidence 索引。

下一阶段验收仍要求：online 不使用 truth ID、不改写 `global_track_id`、过时 plan 被拒绝、D4/D5 gate 不因提高成功率而放宽、所有指标区分 unavailable 与零值。

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
| main | 统一 AirSim episode bus 多 seed 校准 | **首轮真实多 seed 已完成**：D4/D5 5v5 为 10 seeds x 2 heights x 3 cases；2v2 SimpleFlight 为 10 seeds x 2 pairs；episode clock、实际规模、execution/contract、evidence path 和 D6 bundle 均已写盘 | CV 5v5 D1/D2/D3 阈值、YOLO/MOT、D7 多导引律和长期 scenario/version 治理 | 多 seed 报告继续按稳定 scenario group 汇总，禁止把已完成批次重新列为“未运行” |
| D1/main | D1 replay schema version、CSV reader、更多 Blocks fixture | **P1 基线已补齐**：replay schema v1、legacy JSONL 兼容、最小 CSV reader/replay 已实现 | 更多真实 Blocks/CV fixture、D6 长期批量字段、长期回归样本 | D1 能读取带 version 的 replay fixture，D6 可追踪 observation latency/OOSM |
| D1/D4/D6 | 区域质量摘要和 OOSM 审计字段 | **P1 基线已补齐**：`LatencyAuditSummary` 和轻量 `FusionQualityRegionSummary` 已实现 | 区域时间窗口、协方差增长率窗口、D6 长期趋势字段 | D4 可消费区域级不确定度；D6 可输出 OOSM/latency 统计 |
| D2/main/D6 | 真实 5v5 AirSim replay 的 association log 和 risk threshold 校准 | **P1 基线已补齐**：D2 replay helper、AirSim-like replay、threshold sensitivity 和 risk split 已实现 | 真实 replay、truth offline labels、阈值版本、D6 grouped report | 输出 IDSW、continuity、risk summary 和 threshold sensitivity |
| D3/main/D4 | `request_center_replan` 后新 plan owner/version 闭环 | **P1 基线已补齐**：main 监听 D4 `request_center_replan`，下一规划周期强制 D3 生成新 version，并写入 `replan_reason/supersedes_plan_id/supersedes_plan_version/active_plan_owner=center`；secondary takeover replan 会保持真实二级 owner，不再回退为 `d3_central`；D7 gate 继续按当前 binding/version 放行或拒绝 | 仍需真实 Blocks 多 seed 校准 | D4 request/replan 后 D3 发布新 version，D7 只接受当前 version；名义场景不能因软 cost margin 每帧 replan；secondary plan summary 的 owner 为真实二级节点 |
| D4/main/D3/D5 | 主动降级过敏抑制 | **P1 基线已补齐**：D4 已将 `d3_assignment_not_current/stale` 作为硬风险，将 `d3_assignment_cost_margin_low` 作为软风险；软 margin + 早期 D5 low confidence 只 `continue_center/observe_more`；持续 D5 `ambiguous/reacquire` 若无 observed mismatch/资源错配/重复锁定/友方冲突，则不触发分布式降级 | 真实 Blocks 多 seed 下的 threshold、dwell/release 和 review label 校准 | 名义 2v2/5v5 不应全帧 `request_center_replan` 或 `degrade_to_distributed`；硬 stale/not-current 和真实 terminal mismatch 仍触发仲裁 |
| D3/D5/main | D5 feedback 写回下一轮 D3 代价 | **P1 基线已补齐**：D3 feedback helper 已接入 main runtime bus，输出 `d3_terminal_feedback_writeback`，无冲突 ambiguous/reacquire 不再误触发 operator hold | 真实多 seed 下 duplicate/friend/fov/feasibility metadata 阈值校准 | D5 feedback 能生成 `operator_hold/prohibited_edges/fov_difficulty` 输入 |
| D4/main/D3/D7 | 二级接管 plan version 与 D7 two-stage handoff | **P1 基线已补齐**：D4 secondary takeover metadata、D3 secondary plan owner/version、main secondary owner 保持、D7 owner gate 和 controlled 2v2 visual PNG 回归已通过 | 真实 Blocks 多 seed 的 secondary heartbeat/link freshness 校准 | `degrade_to_secondary` 阶段 1 阻断 visual PNG，阶段 2 新 plan 生效后才放行；secondary plan `owner_node_id` 必须是可用二级节点 |
| D4/D5/main/D6 | 机动高空侦察二级节点覆盖与接管必要性 | **真实多 seed 基线已完成，接管状态机未闭合**：60 case 中注册链路稳定，20 个 secondary case 均因持续 full-view/plan activation 不足转 distributed；15/1300 决策瞬时 takeover-ready，secondary plan active 为 0 | 持续 coverage cell、逐决策 stable/not-registered evidence、plan lease/activation delay、active-plan 专项和 D6 长期趋势 | 构造 `registration_usable -> takeover_ready -> pending_secondary_plan -> secondary_plan_active` 可复现 case，且不得降低门限 |
| D4/D3/D6 | CBBA vs 中心 Hungarian cost gap | **P1 基线已补齐**：D4 已有 `CBBACostGapBenchmark` helper | 同 episode 保存 D3 center cost matrix/current plan；D6 cost gap 长期聚合 | 同场景输出 completion/conflict/cost gap/rounds/messages |
| D4 | 独立 auction baseline 是否后置 | 未单独实现；当前 CBBA 覆盖 winner/bid 思想 | bid/award/rollback 协议和测试预算 | 若进入 P1/P2，需与 CBBA 同输入对照；默认本轮不实现 |
| D5/main/D6 | AirSim geometry、TerminalConsistencySummary 全量写盘 | **P1 基线已补齐**：D5 geometry log fields、handoff advisory、consistency 连续窗口和 main event/snapshot 字段已接入 | 真实多 seed 下 projected pixel、Mahalanobis、duplicate risk 的长期统计 | D6 能按 episode/seed 统计 terminal lock、ambiguous、hold、duplicate risk 和重捕获连续性 |
| D5/D4/main | 多相机/二级视角 detect 到 global track 的跨视角配准 | **AirSim builtin detect 几何注册基线已闭合**：60-case 中 projection valid=1.0、cross-view association 均值约 4.42、`secondary_detect_available_but_not_registered=0`；匿名 local ID 的真实 smoke 也已通过 | 真实 YOLO/MOT、外参漂移、时间同步、逐决策 stable/not-registered 到 D4、复杂遮挡/交叉 | 保持 online truth 隔离，YOLO/MOT 多 seed 下校准 ID continuity、投影门限和失败回退 |
| D5/D7 | 视觉 PNG 前置证据合同固化 | **P1 基线已补齐**：D5 handoff advisory、D7 D3/D4/D5 gate、center/secondary controlled intercept owner/version 回归均通过 | 真实 bbox 稳定窗口、measurement age、duplicate risk、friend conflict 多 seed 校准 | D7 仅在 D5 locked、assigned ID 一致、D3/D4 gate 通过时视觉 PNG |
| D5/main | YOLOv8 + MOT detector adapter | **P1 基线已补齐**：D5 可加载 `best.pt` 运行 YOLOv8，优先 ByteTrack/BoT-SORT，缺依赖时 deterministic IoU fallback；main runtime 可用 `--detection-backend yolo` 将内存图像送入 D5 adapter | 真实 AirSim 多 seed 目标尺寸、置信度、tracker backend 和 FOV 阈值标定 | adapter 只输出 `LocalVisualTrack`，tracker ID 不替代 `global_track_id` |
| D6/main | D4/D5/D7 产物统一回灌 | **真实多 seed 与拦截字段聚合已闭合**：5v5 calibration 和 2v2 execution/contract 均可扫描；cross-seed 已输出 success/collision/range/abort/min-range/time/visual-switch/terminal rates/gate rejects；read-only episode 为 unavailable，不误报 0/20 | 长期场景库、CI 趋势、更多算法组配对 | 一个 D6 bundle 同时给出 coverage/registration/degradation 和 intercept/guidance 多 seed 指标，contract 不污染 execution |
| D6 | 主动降级必要性/精度 | **P1 基线已补齐**：`metric_scope`、`active_degradation_precision`、`unnecessary_active_degradation_count` 和 review label/后验最小口径已实现 | 真实 episode 持续写出 review/window 字段 | 输出 active_degradation_precision 和 unnecessary_active_degradation_count |
| D7/main/D6 | N-pair runtime bus 与多 seed PN/Pure Pursuit/PNG 对照 | **真实 radar-PN + PNG-VM 10-seed 基线已完成**：18/20 成功，平均 min range 2.113 m，主要 gate 原因已统计 | AirSim PN/Pure Pursuit/PNG-TTC/PNG-VM 同 seed 选择器与配对报告；视觉切换率仍低 | 多 seed 报告输出每种 law 的 min range、成功率、mode switch、terminal reject 和 visual PNG switch |
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
