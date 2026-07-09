# 框架评估 P0/P1/P2 缺口确认

**文档版本**: v1.0
**生成日期**: 2026-07-08
**生成角色**: main agent
**输入材料**:

- `EVAL/FRAMEWORK_EVAL_D1_SENSOR_FUSION.md`
- `EVAL/FRAMEWORK_EVAL_D2_DATA_ASSOCIATION.md`
- `EVAL/FRAMEWORK_EVAL_D3_ASSIGNMENT.md`
- `EVAL/FRAMEWORK_EVAL_D4_COORDINATION.md`
- `EVAL/FRAMEWORK_EVAL_D5_TERMINAL.md`
- `EVAL/FRAMEWORK_EVAL_D6_EVALUATION.md`
- `EVAL/FRAMEWORK_EVAL_D7_GUIDANCE.md`
- `EVAL/FRAMEWORK_EVAL_SYSTEM_INTEGRATION.md`
- `.claude/plans/framework_evaluation_plan.md`

## 1. 结论

本轮外部评估不是发现了当前仓库新的运行级 P0 blocker。当前 `MAIN_P0_P1_GAP_STATUS.md` 中“无新增 P0 阻塞断链”的结论仍成立：现有离线点质模型、AirSim Blocks smoke、D1-D7 module tests 和 main runtime tests 仍可运行。

但从工程化、稳定 AirSim 批量验证和后续封闭场地验证角度看，外部评估提出了一组**工程化 P0 缺口**。这些缺口不是“代码现在不能跑”，而是“如果不补，后续多 seed、分布式、真实图像和闭环拦截结果不够可信”。

因此本文件采用以下口径：

| 等级 | 含义 | 是否阻塞当前仓库测试 | 是否应进入近期排期 |
|---|---|---:|---:|
| P0 | 工程化硬化项。进入更可信 AirSim/封闭场地验证前应优先补齐；本文件进一步拆成 P0-A/P0-B/P0-C | 否 | 是 |
| P1 | 三个月内的能力增强和标定项。用于提升鲁棒性、统计可信度和复杂场景覆盖 | 否 | 是 |
| P2 | 六个月左右的架构升级或高阶算法对照。应在 P0/P1 稳定后推进 | 否 | 视资源 |

P0 细分口径：

| 子级 | 含义 | 进入条件 |
|---|---|---|
| P0-A | 基础设施可信度。没有这些，后续多 seed 报告、故障注入和闭环结果难以解释 | 立即进入第一批排期 |
| P0-B | 安全门控与闭环稳定性。直接影响 D1-D7 合同是否可信、是否会误锁/误分配/误降级/误切换 | 紧跟 P0-A |
| P0-C | 场景依赖 P0。若下一阶段继续做 5v5/N-v-N、高差拦截、复杂交叉或二级接管，则应进入 P0；若只做当前 smoke，可延后到 P1 | 由下一阶段测试场景决定 |

## 2. Subagent 使用决策

本文件由 main agent 编写，不再拆给 D1-D7 subagent 分别写新的 EVAL 子文档。

原因：

1. 外部评估材料已经按 D1-D7 和系统集成拆成 8 个独立文档。
2. 用户当前要求是在 `EVAL/` 下确认 P0/P1/P2 缺口，这是跨模块优先级归并，属于 main 的全局调度职责。
3. 如果再让 D1-D7 各写一份 P0/P1/P2 文档，会和现有 `FRAMEWORK_EVAL_Dx_*.md`、`subagent_reviews/Dx_IMPLEMENTATION_GAP_AUDIT.md` 重复。

后续只有在进入实施阶段时才需要 subagent：

- D1-D7 分别把本文件中被确认的条目同步进各自 `PLAN.md` / `README.md` / `subagent_reviews/Dx_IMPLEMENTATION_GAP_AUDIT.md`。
- 每个 subagent 只修改自己的 owned paths，并运行自己的模块测试。
- main 继续负责 AirSim runtime、跨模块合同、D6 汇总报告和总体验收。

## 3. P0 缺口确认

P0 的共同目标是提升当前 AirSim/仿真链路的可信度、可复现性和故障可解释性。P0 不应被理解为“引入所有高级算法”，而应被限制为最小可验收硬化项。

### 3.1 P0-A 基础设施可信度

P0-A 是最高优先级。它们不直接提升某个算法分数，但会决定后续所有实验结果是否可信。

| Owner | P0-A 缺口 | 最小范围 | 当前项目状态判断 | 验收口径 |
|---|---|---|---|---|
| Main/System | 统一时间管理 | 定义并写盘 `episode_time`、`measurement_timestamp`、`arrival_timestamp`、`publish_timestamp`、`processing_timestamp` 和 clock source；不要求 ROS2/PTP | 当前字段分散存在，但跨模块 clock 与 processing timestamp 规则还不统一 | D1-D7 records 可用同一 episode clock 对齐，D6 能输出 latency breakdown |
| Main/System | 集中配置管理 | 一个 scenario config 生成 AirSim settings、模块参数、seed、资源/目标数量和 D6 metadata；不要求配置热更新 | 当前参数分散在脚本、settings 和模块配置中 | 同一 config 可复现实验目录、settings 和报告字段 |
| Main/System | 健康监测 | 每个模块输出 lightweight health/status snapshot；不要求真实分布式 supervisor | 当前 main episode bus 有 summary，但运行时健康状态不完整 | episode 中可看到 D1-D7 health、record count、last update age 和 error state |
| Main/System | 异常处理与恢复 | 对模块异常、输入缺失、AirSim RPC 异常输出明确 failed/degraded outcome；不要求自动重启全部模块 | 当前测试链路能跑，但异常后的统一状态表达不足 | 故障注入下系统不中断或能产出明确 failed outcome 和 root cause |
| D6 | 系统级任务成功指标 | 定义 `mission_outcome=success/partial/failed/aborted`、success reason、failure reason；不要求人因/对抗指标 | 当前指标丰富，但端到端 outcome 仍需统一 | 每个 episode 有系统级 outcome，并能解释与 D1-D7 指标关系 |
| D6 | 根因诊断 | 基于已写盘 records 输出 top failure causes；不要求复杂因果推断 | 当前有 metrics/report，但失败链路自动归因不足 | 报告能输出 top failure causes，例如 tracking、assignment、terminal gate、guidance、coverage |
| D6 | 性能监测 | 记录模块耗时、loop latency、record latency、CPU/GPU 预算占位；不要求在线 dashboard | 当前主要是离线指标，性能指标还不系统 | 每个 episode 输出模块耗时、延迟分布和性能回归标记 |
| D1 | FDIR-light | 传感器级 health、漂移/偏置/丢包/延迟异常计数和隔离建议；不做完整工业 FDIR | 当前已有马氏门控、latency/OOSM/区域质量摘要，但缺传感器级健康状态 | 故障注入下能输出 sensor health、fault reason、reject count 和恢复状态 |
| D1 | 协方差上下界限制 | 对长时间外推、低质量观测、遮挡和异常观测设置 covariance floor/ceiling 与 reason | 当前已有协方差传播和质量分级，但真实多 seed 下还缺发散/过度自信保护 | 协方差不发散、不虚假收敛，并在 D6 报告中可解释 |
| D1 | 时间戳不确定性建模 | 先把 timestamp uncertainty 写入观测/summary，并进入质量指标；不要求完整时钟同步协议 | 当前保留 measurement/arrival timestamp，但未显式建模 timestamp uncertainty | 注入 10-50 ms 时钟漂移时，D1 输出 timing uncertainty 与误差变化曲线 |

### 3.2 P0-B 安全门控与闭环稳定性

P0-B 直接影响系统是否会误锁、误分配、误降级或误切换。它们应保持轻量、可解释、可测试。

| Owner | P0-B 缺口 | 最小范围 | 当前项目状态判断 | 验收口径 |
|---|---|---|---|---|
| D2 | 航迹质量评分 | 输出 `track_quality` / `association_risk`，驱动 D3/D5/D6 消费；不要求完整学习模型 | 当前有 continuity/IDSW 指标，但还缺直接驱动门控/初始化/删除的质量分 | 每条 track 输出 quality，D3/D5/D6 可消费 |
| D2 | 运动一致性约束 | 在 GNN/Hungarian 代价中加入速度方向、加速度异常或短时历史一致性；不替换主关联器 | 当前主要依赖马氏距离和代价矩阵，运动连续性偏弱 | crossing/dense replay 中输出 motion consistency score，并参与关联代价 |
| D3 | 资源状态细化 | 增加 energy/availability/intercept feasibility/current load/history failure 等字段；不做多资源协同 | 当前已有资源状态惩罚和可行性，但状态粒度不足 | ResourceState 影响分配，D6 能解释资源不可行原因 |
| D3 | 增强迟滞逻辑 | 加入切换成本、min dwell、release condition 和 stale rejection；不做预测优化 | 当前已有迟滞和 plan version，但多 seed AirSim 中仍需校准切换成本 | 重分配次数下降，且高威胁目标不因迟滞被漏分配 |
| D4 | Heartbeat 平滑 | 对短时丢包/延迟做滑动窗口和 suspect/degraded 防抖；不引入 Raft | 当前 C2Health 和 heartbeat 可用，但网络抖动下误判风险仍在 | 丢包/延迟注入下误 failover 下降 |
| D4 | Lease 严格管理 | 二级 plan lease、epoch、过期拒绝、恢复双轨审计；不实现版本向量 | 当前已有二级接管 metadata，但 lease 规则还需更严格 | 过期二级 plan 不被 D7 或 main 执行，恢复后有双轨审计 |
| D4 | 二级能力评估 | 基于 coverage/freshness/stable registration/not-registered 输出 secondary capability score；不做视觉注册 | 当前可消费相关摘要，但是否足以接管还未多 seed 标定 | 区分“可见、已注册、可接管”，并进入 D6 |
| D4 | 主动降级防抖 | 校准 dwell/release、hard/soft risk 和 review label；不引入学习式仲裁 | 当前已做硬/软风险分层，但仍需真实 AirSim 多 seed 校准 | active degradation false trigger rate 可统计并下降 |
| D5 | 主动重捕获 | 基于预测投影、bbox 历史和搜索窗口支持 reacquire；不改变 `global_track_id` | 当前有 `reacquire/ambiguous/hold`，但失锁后主动搜索不足 | 遮挡后 reacquire 恢复帧数下降，且不改写 `global_track_id` |
| D5 | 时序一致性 | 对 bbox/MOT 历史、candidate margin、稳定窗口做更强约束；不引入 ReID | 当前有稳定窗口和 cross-view candidate，但 locked/reacquire 抖动仍需抑制 | terminal locked 率提升，误锁仍为 0 |
| D5 | 相机校准健康监测 | 输出 reprojection error、camera pose source、calibration health、drift warning；不做完整在线标定 | 当前支持 OpenCV 投影和 camera pose metadata，但校准误差告警不足 | D6 能看到 projection_valid、reprojection_error、calibration_health |
| D7 | 末端切换迟滞 | 对视觉 PNG 切换加入 dwell、release、reacquire grace 和 reject reason；不改变 D3/D4/D5 gate | 当前已有 gate，但 locked/reacquire 抖动可能传导到导引 | terminal mode switch 次数下降，reject reason 可解释 |
| D7 | LOS 角速率滤波 | 对 LOS rate 做低通/限幅/异常值拒绝；不引入复杂控制器 | 当前 LOS 噪声近距可能放大 | 输出 filtered LOS rate，近距命令不出现尖峰 |

### 3.3 P0-C 场景依赖 P0

P0-C 是否立即实施取决于下一阶段测试目标。若继续做高差 5v5/N-v-N、复杂密集交叉和可信闭环拦截，这些项应进入 P0；若只维持 smoke 和接口验证，可下调为 P1。

| Owner | P0-C 缺口 | 最小范围 | 何时作为 P0 | 若不满足条件 |
|---|---|---|---|---|
| D7 | 三维 PN | 先实现 3D 几何 PN 对照和日志，不做完整动力学控制 | 下一阶段继续测试 200 m 高差、3D target 或高度差拦截 | 降为 P1 |
| D3 | 动态威胁 baseline | 只做可解释 threat score baseline：接近关键区、TTC、速度、协方差，不做完整威胁评估系统 | 下一阶段需要 N/M 不匹配、高威胁优先、资源不足场景 | 完整动态威胁评估降为 P1 |
| D2 | quality-aware 自适应门控 baseline | 基于 track quality / density 调整门限的轻量规则，不做完整 adaptive gating framework | 下一阶段重点测试 dense/crossing/遮挡和 ID switch | 完整自适应门控策略降为 P1 |
| Main/D6 | P0/P1 实施状态追踪字段 | 在 D6 报告里标记 eval_priority、implementation_status、evidence_path | 下一阶段开始按 EVAL 推进 backlog | 可先保留为文档项 |

### 3.4 明确下调出 P0 的项

| 原 P0 建议 | 调整后等级 | 原因 |
|---|---|---|
| D7 APN 目标机动补偿 | P1 | APN 有价值，但不是当前可信验证基础设施；应在 3D PN、LOS 滤波和切换迟滞稳定后做 |
| D5 完整相机在线校准 | P1/P2 | P0 只需要校准健康监测和误差告警；完整在线标定涉及外参估计、PnP/RANSAC 和长期漂移模型 |
| D3 完整动态威胁评估 | P1 | P0 只保留可解释 threat baseline；完整威胁评估需要场景定义和 D6 outcome 支撑 |
| D2 完整自适应门控策略 | P1 | P0 只做 quality-aware gate baseline；完整策略需要密集/遮挡多 seed 标定 |

## 4. P1 缺口确认

P1 主要是三个月内的能力增强、可对照实验和多 seed 标定。P1 不应抢在 P0 硬化项之前大规模重构。

| Owner | P1 缺口 | 当前项目状态判断 | 验收口径 |
|---|---|---|---|
| D1 | IMM 多模型滤波 | 目前 CV/EKF 主线可用，机动目标误差仍是评估指出的关键风险 | CV/CA/CT 或等价模型对照，机动 RMSE 下降 |
| D1 | 场景自适应协方差 | 已有基础距离/质量协方差，仍缺遮挡、杂波、SNR、来源差异的动态规则 | AirSim/replay 中按场景输出 covariance scale reason |
| D2 | 完整自适应门控策略 | P0-C 只保留 quality-aware gate baseline；完整策略需要密集/遮挡多 seed 标定 | 按目标密度、track quality、协方差一致性自动调整门控，并输出 sensitivity report |
| D2 | 工程化 JPDA | 当前有轻量 JPDA 对照，不是完整工程实现 | dense/crossing replay 下 JPDA 与 GNN 可同场景对比 |
| D2 | N/M 初始化优化 | 当前状态机可用，但虚假航迹率和初始化延迟还缺系统标定 | 输出 false track rate、init latency，多 seed 统计 |
| D2 | 协方差一致性检查 | 当前主要消费 D1 covariance，不主动判定一致性 | 输出 NEES/NIS 或等价 consistency flag |
| D3 | 完整动态威胁评估 | P0-C 只保留可解释 threat score baseline；完整威胁评估需要场景定义和 D6 outcome 支撑 | 威胁模型可按 TTC、保护区、速度、目标类别、协方差和资源状态给出可解释评分 |
| D3 | 增量分配 | 当前滚动重算可用，但目标突增/资源失效时还需局部增量策略 | 新目标/资源失效时 plan update latency 下降 |
| D3 | 时间窗口硬约束 | 当前有窗口代价，缺更硬的不可行窗口拒绝 | window closed 的边不会被分配 |
| D3 | OR-Tools Min Cost Flow 接口 | 当前 Hungarian 主线稳定，OR-Tools 仍是预留 | 能在同输入下输出 min-cost-flow 对照计划 |
| D4 | 网络分区检测 | 当前主要关注中心/二级/分布式，脑裂和分区检测不足 | 网络分区注入下输出 partition state 和 conflict count |
| D4 | Raft/Leader 选举对照 | 当前使用轻量接管/CBBA，尚无成熟选举对照 | 选举与二级接管日志可复现，不引入执行绕过 |
| D4 | DDS QoS/通信策略 | 当前通信是仿真消息合同，尚无 QoS 建模 | 丢包、优先级、stale link 在 D6 中可统计 |
| D5 | 多模态友方识别 | 当前 `IdentityClaim` 是仿真/接口，真实 Remote ID/MAVLink/DDS/AprilTag 未接入 | 至少一个 replay adapter 输出 verified/stale/unverified |
| D5 | 完整相机在线标定 | P0-B 只做校准健康监测；完整在线标定涉及外参估计、PnP/RANSAC、畸变和漂移模型 | replay/标定样本中能估计外参漂移并降低重投影误差 |
| D5 | 畸变校正 | 当前以针孔模型/OpenCV 投影为主，广角畸变仍未闭合 | 畸变参数进入 projection，重投影误差下降 |
| D5 | ReID 辅助 | 当前 YOLO/MOT 可接线，但无 ReID 外观特征 | 遮挡恢复和密集目标场景下 ID continuity 有提升 |
| D6 | 基线对比框架 | 当前已有多指标报告，但算法 A/B 对比和统计显著性不足 | 同一场景输出 baseline vs enhanced 表格 |
| D6 | 场景库管理 | 当前已有若干 scenario，但覆盖率管理不足 | 标准场景库带 tags、seed、difficulty、expected failure modes |
| D6 | CI/回归测试 | 当前能手动跑测试，缺实验级 CI 汇总 | 每次变更产出测试矩阵和性能回归摘要 |
| D7 | APN 目标机动补偿 | P0-B 先做 LOS 滤波与切换迟滞；APN 需要目标加速度估计和机动场景标定 | 机动目标场景 miss distance 下降，且不破坏 D3/D4/D5 gate |
| D7 | 最优制导律 OGL 对照 | 当前 PN/PNG 主线可用，OGL 未实现 | OGL 作为研究对照，不替代默认 PN |
| D7 | 预测拦截点 | 当前主要基于 PN 视线率，目标预测拦截点不足 | 输出 predicted intercept point，与 PN 对比 |
| D7 | 动力学补偿 | 当前 SimpleFlight 简化，执行延迟/加速度限制不足 | 命令饱和、响应延迟进入 guidance log |
| Main/System | ROS 2 节点化规划/小规模原型 | 当前为 Python/AirSim runtime，不应一次性重写 | 先做离线 replay 节点原型，保持现有 Python tests |
| Main/System | 事件驱动架构 | 当前 episode bus 已有记录流，但运行时仍偏串行 | 事件 schema 和 replay consumer 稳定 |
| Main/System | 状态机标准化 | D2/D3/D4/D5/D7 均有状态，但统一状态合同不足 | 状态枚举、transition reason、invalid transition 进入日志 |

## 5. P2 缺口确认

P2 是六个月左右的架构升级、高阶算法或较重外部依赖。除非 P0/P1 已经形成稳定数据，否则不建议现在作为默认主线。

| Owner | P2 缺口 | 当前项目状态判断 | 验收口径 |
|---|---|---|---|
| D1 | Track-to-Track 融合 | 当前中心融合主线可用，T2T 适合分布式/多二级节点成熟后推进 | 多节点 track fusion 不重复计数，协方差一致 |
| D1 | UKF 非线性观测 | EKF 目前足够做基线，UKF 用于强非线性雷达/光电模型对照 | UKF 与 EKF 同场景报告 |
| D1 | 传感器管理/主动探测 | 需要 D4/D5/二级节点更稳定后再推进 | 传感器调度能提高 coverage 或降低不确定性 |
| D2 | 有界 MHT | 当前 placeholder 可保留，完整 MHT 计算和延迟较重 | 小规模 dense crossing 中可控延迟、IDSW 下降 |
| D2 | 航迹合并/分裂检测 | 当前尚未作为核心瓶颈，但复杂编队会需要 | 输出 merge/split event，并防止 duplicate assignment |
| D3 | 多资源协同分配 | 当前一对一 Hungarian 是稳定主线，多资源协同需要 D7/D6 成功指标支撑 | high threat target 可分配主/备资源且 D6 能评估收益 |
| D3 | 备份资源机制 | 应在时间窗口和资源状态 P1 稳定后做 | backup activation latency 可统计 |
| D3 | 预测性滚动分配 | 依赖 D1/D2 预测可靠性和 D6 长期报告 | 预测窗口内减少重分配和 missed opportunity |
| D4 | 版本向量 | 当前 plan version/epoch 已够基线，版本向量适合多分区合并 | 分区恢复时冲突可解释 |
| D4 | 分区合并 | 需要网络分区检测 P1 先完成 | merge outcome 与冲突审计可回放 |
| D5 | 跨视角联合优化 | 当前已有 metadata/candidate/stable registration，联合优化较重 | 多相机联合后提升 cross-view consistency |
| D5 | 视觉伺服 | D7/D5 gate 和相机控制链路更稳定后推进 | 保持目标中心且不越过 D3/D4/D5 gate |
| D6 | 对抗性评估 | 需先有稳定场景库和根因诊断 | 红蓝/干扰 scenario 输出标准报告 |
| D6 | 标准 MOT 指标 | 当前工程指标优先，HOTA/IDF1/OSPA 可作为对照 | TrackEval/py-motmetrics 离线 adapter |
| D6 | 场景覆盖率分析 | 依赖场景库标签化 | 输出 coverage matrix 和未覆盖风险 |
| D7 | 协同拦截导引 | 当前单机 PN 是主线，协同导引依赖 D3 多资源分配 | 多资源任务不冲突，D6 能评估协同收益 |
| D7 | 增益自适应 | APN/3D PN 稳定后再做 | gain schedule 不引入振荡 |
| Main/System | 行为树决策 | 当前 D4 rules 更可控，行为树适合系统状态复杂后引入 | 行为树只编排状态，不绕过授权/分配合同 |
| Main/System | 监控 Dashboard | 需要 P0/P1 日志和健康指标稳定 | Dashboard 消费现有日志，不控制系统 |
| Main/System | 自动化部署 | ROS2/事件化稳定后推进 | 一键启动/关闭/收集日志 |

## 6. 不建议作为 P0/P1 的内容

以下内容在外部评估中出现，但不建议现在进入 P0/P1：

| 项 | 原因 | 建议 |
|---|---|---|
| 强化学习导引 | 需要大量训练数据，安全边界难解释 | P3 研究项 |
| 端到端深度学习关联 | 数据需求大，解释性弱，容易破坏 `global_track_id` 合同 | P3 研究项 |
| 云原生部署 | 当前重点是 AirSim/封闭场地可信验证，不是大规模服务部署 | P3 |
| 数字孪生 | 需要稳定真实数据闭环后才有意义 | P3 |
| BFT 共识 | 对当前二级/分布式仿真过重 | P3 |
| MPC/NMPC 作为默认导引 | 编译/调参/实时性成本高，当前 PN/PNG 仍是默认主线 | P3 或专项对照 |

## 7. 与当前 GAP 文件的关系

本文件不直接修改 `subagent_reviews/Dx_IMPLEMENTATION_GAP_AUDIT.md`。它是 EVAL 层的优先级确认文件。

后续若要进入实施，应按以下方式同步：

1. main 将本文件拆成 D1-D7 module tasks。
2. D1-D7 subagent 各自更新 owned GAP/PLAN/README。
3. main 更新 `subagent_reviews/MAIN_P0_P1_GAP_STATUS.md`，明确哪些 EVAL P0 已转入项目 P0/P1 backlog。
4. D6 新增统一跟踪字段，后续报告中同时展示“评估建议等级”和“项目实现状态”。

## 8. 建议执行顺序

### 第一批：先补系统可信度

1. Main/System：统一时间管理、集中配置、健康监测、异常恢复。
2. D6：系统级任务成功指标、根因诊断、性能监测。
3. D1：FDIR-light、协方差上下界、时间戳不确定性。

理由：这些项会提高所有后续 AirSim 多 seed 实验的可信度。

### 第二批：补闭环稳定性

1. D2：航迹质量、运动一致性、quality-aware gate baseline。
2. D3：资源状态、增强迟滞、可解释 threat score baseline。
3. D4：heartbeat 平滑、lease 管理、二级能力评估、主动降级防抖。
4. D5：主动重捕获、时序一致性、相机校准健康监测。
5. D7：末端切换迟滞、LOS 角速率滤波；若继续做高差拦截，则加入 3D PN。

理由：这些项直接影响 5v5/N-v-N 的关联、分配、降级和导引闭环稳定性。

### 第三批：能力增强和对照实验

推进 P1/P2 中的完整自适应门控、完整动态威胁评估、APN、JPDA、OR-Tools、ReID、完整在线标定、3D/动力学导引、标准 MOT 指标和 ROS2 replay 原型。每个新增算法必须保留当前轻量主线作为 baseline。

## 9. 当前状态摘要

| 模块 | 当前运行级 P0 blocker | 工程化 P0 缺口 | P1/P2 主要方向 |
|---|---:|---|---|
| D1 | 无 | FDIR、协方差界、时间戳不确定性 | IMM、T2T、UKF |
| D2 | 无 | 航迹质量、运动一致性、quality-aware gate baseline | 完整自适应门控、JPDA、MHT、合并/分裂 |
| D3 | 无 | 资源状态、增强迟滞、threat score baseline | 完整动态威胁、OR-Tools、多资源、备份资源 |
| D4 | 无 | heartbeat、lease、二级能力、防抖 | 分区检测、Raft/QoS、版本向量 |
| D5 | 无 | 主动重捕获、时序一致性、相机校准健康监测 | 完整在线标定、ReID、畸变、跨视角联合 |
| D6 | 无 | 系统级 outcome、根因诊断、性能监测 | 场景库、CI、标准 MOT |
| D7 | 无 | 切换迟滞、LOS 滤波；高差场景下 3D PN 属 P0-C | APN、OGL、预测导引、协同导引 |
| Main/System | 无 | 时间、配置、健康、异常恢复 | ROS2 replay、事件驱动、Dashboard |

最终判断：本轮评估应作为下一阶段工程化 backlog 的来源，而不是推翻现有 D1-D7 轻量主线。当前最合理做法是先用 main 维护本 EVAL 总表，待用户确认优先级后，再由 subagent 分别把选中的 P0/P1 条目落入模块 PLAN/GAP。
