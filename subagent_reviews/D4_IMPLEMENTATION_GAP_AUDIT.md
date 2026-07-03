# D4 实现差距审计：分布式协同与降级接管

**审计范围**：本文件只审计 D4 分布式协同与降级接管模块，对照 `subagent_reviews/D4_DISTRIBUTED_FALLBACK_REVIEW_AND_PLAN.md`、`subagent_reviews/MAIN_COMMUNICATION_AND_DIFFICULTY_REVIEW.md`、`C_UAS_MAINSTREAM_SOLUTIONS_AND_DIFFICULTIES.md` 与 `research_modules/d4_distributed_fallback/` 当前代码和测试。  
**边界**：结论仅用于离线科研仿真、接口补齐和 AirSim ComputerVision dry-run/stress 规划；不涉及真实通信链路、飞控、硬件、火控、毁伤、自动处置或授权绕过。

## 总体结论

D4 已经实现了可运行的离线骨架：`C2Health` 状态机、被动降级优先级、主动降级仲裁、二级侦察节点模型、通信摘要、简化 CBBA、中心恢复合并和 AirSim phase-1 dry-run 合同测试。当前缺口主要不是“没有 D4 代码”，而是尚未完成与 main 统一数据总线、真实 5v5 CV stress 日志、D1-D5 summary 生产链路、D6 指标聚合以及成熟开源 CBBA/拍卖/合同网实现的对照接入。

优先级定义：

- **P0**：阻塞 main 端到端调度或 AirSim D4/D5 stress 评估。
- **P1**：影响算法可信度、覆盖面或工程稳定性，但不阻塞 dry-run。
- **P2**：研究增强项、开源对照或大规模实验优化。

## 差距审计表

| 预期项 | 当前状态 | 证据文件 | 未实现原因 | 缺失条件 | 建议优先级 |
|---|---|---|---|---|---|
| C2Health 状态机：`normal/degraded/suspect/failed`，不能只靠 heartbeat 恢复 | **已部分实现**。支持 heartbeat warning/stale/failure、peer quorum、digest conflict、恢复进入 suspect，中心恢复需 `merge_recovery` | `research_modules/d4_distributed_fallback/d4_distributed_fallback/models.py`；`coordinator.py`；`tests/test_health.py`；`tests/test_coordinator.py` | 当前只在离线 coordinator 内运行，未由 main 的中心心跳、digest、plan version、track digest 驱动 | main 需要生成 C2 heartbeat、assignment digest、track digest、peer fail votes、center epoch；D6 需要消费状态迁移日志 | P0 |
| 被动降级：中心失效后先二级节点/地面备份，再完全无中心 | **已部分实现**。`plan_degraded()` 仅在 center failed 后规划，`elect_leader_resource()` 按 priority/role/lease/availability 选 leader，二级节点优先于分布式 | `coordinator.py`；`tests/test_coordinator.py`；`README.md`；`PLAN.md` | 离线测试覆盖中心失效与二级不可用，但还没有 main 持续监控二级节点健康与覆盖小区生命周期 | main 需要传入二级节点 heartbeat/lease/coverage/link freshness；需要 episode 中的二次被动降级事件流 | P0 |
| 主动降级：中心在线但 D1/D2/D3/D5 风险导致仲裁 | **已实现离线规则版**。`ActiveDegradationArbiter` 消费 D1 定位、D2 关联、D3 分配、D5 终端关联、C2/secondary health，输出 continue/replan/assist/secondary/distributed/hold | `active_degradation.py`；`tests/test_active_degradation.py`；`tests/test_airsim_phase1_dry_run_contracts.py` | 阈值为人工默认值，尚未用 5v5 批量实验校准；主循环尚未稳定生产所有 summary | D1-D5 到 D4 的 summary 映射；跨帧 hysteresis/dwell；D6 对 active_degradation_count 和原因分布的聚合 | P0 |
| D5 一致则不降级；D5 mismatch/duplicate/friend conflict 分流处理 | **已实现核心规则**。D5 locked 且 ID/资源/置信度一致才 `continue_center`；`friend_conflict` 强制 `hold_for_review`；`duplicate_terminal_lock` 不视为一致 | `active_degradation.py`；`tests/test_active_degradation.py` | 当前只消费 D5 的摘要字段，不直接校验 D5 的原始 bbox/MOT/identity evidence | D5 需要稳定输出 `TerminalAssociationSummary`、cross-view 风险、duplicate lock 与 friend conflict；main 需要保持 plan_version 对齐 | P0 |
| 二级系留/高空侦察节点：区域协调者、视频/检测 cue 提供者、`coordinator_only` | **已部分实现**。`NodeRole.SECONDARY_RECON`、`coordinator_only`、`coverage_cell`、lease/priority 已建模；主动仲裁要求覆盖匹配与链路新鲜 | `models.py`；`active_degradation.py`；`coordinator.py`；`tests/test_coordinator.py`；`tests/test_airsim_phase1_dry_run_contracts.py` | 当前没有真实图像 cue adapter；二级节点仅作为 summary/leader 模型，不持有区域图像流或局部 TrackSummary 缓存 | main/AirSim 需生成 `Secondary_Recon_*` 的视频元数据、检测摘要、覆盖区、通信时延；D5/D1 需消费二级 cue | P0 |
| 二级节点失效后的二次被动降级 | **已部分实现**。二级 availability 为 none 或链路 stale 时会选择 distributed；coordinator 也能在二级不可用时选 cluster representative | `active_degradation.py`；`coordinator.py`；`tests/test_active_degradation.py`；`tests/test_coordinator.py` | 没有持续运行的二级节点健康状态机；目前靠每次输入的 summary 表达失效 | main 需要在 episode 中维护 secondary heartbeat、lease epoch、link stale 与 coverage mismatch 事件 | P0 |
| CBBA 分布式协商 | **已实现简化自研版**。`CBBANegotiator` 支持 winner/bid 扩散、确定性 tie-break、bundle 重建、packet loss/delay 仿真、收敛与冲突统计 | `cbba.py`；`network.py`；`tests/test_cbba.py`；`tests/test_coordinator.py` | 不是完整 MIT CBBA；不含路径序列、时间窗、异步鲁棒共识、复杂约束、任务依赖和通信拓扑优化 | 若要提高论文可信度，需要与 MIT CBBA/CBBA-Python/CA-CBBA 做同场景 benchmark，补齐 adapter 与许可证审查 | P1 |
| 拍卖算法 | **未单独实现**。当前 CBBA 评分与 winner 机制可近似覆盖“拍卖式保底”思想，但没有独立 single-round auction baseline | `cbba.py`；`PLAN.md`；`docs/ALGORITHM_AND_IMPLEMENTATION.md` | 现阶段优先实现 CBBA 风格协商以满足降级连续性；拍卖算法未作为单独基线拆出 | 需要定义 auction bid、reserve price、winner confirmation、重复任务消解、失败回滚和测试场景 | P1 |
| 合同网协议 Contract Net | **未实现**。文档中作为可选分布式协议提及，代码没有 manager/contractor announce-bid-award 流程 | `D4_DISTRIBUTED_FALLBACK_REVIEW_AND_PLAN.md`；`PLAN.md` | 当前 5v5 dry-run 更依赖 CBBA/二级节点优先，合同网不是最小闭环必需项 | 需要协议状态机、消息类型、超时、拒绝/重招标、与 D3 plan_version 的映射 | P2 |
| MIT CBBA / CBBA-Python / CA-CBBA 开源代码接入 | **未接入，只有方案对照**。主流方案文档列为理论/原型参考，D4 当前使用本地轻量实现 | `C_UAS_MAINSTREAM_SOLUTIONS_AND_DIFFICULTIES.md`；`cbba.py`；`README.md` | 开源项目接口、维护状态、许可证、依赖和问题建模与本项目 summary bus 不完全一致；直接接入会增加依赖和不确定性 | 需要完成许可证/版本评估、adapter 层、同一任务集 benchmark、性能/收敛差距报告 | P1 |
| CommunicationSummary 增强通信假设 | **已实现核心合同**。包含 source/target/relay、link_type、sent/received timestamp、payload_kind、stale_after_s、sequence_id，并提供 latency/stale 判断 | `models.py`；`active_degradation.py`；`tests/test_active_degradation.py`；`tests/test_airsim_phase1_dry_run_contracts.py` | 比 main 建议字段更精简，尚未包含 `message_type`、`measurement_timestamp`、`arrival_timestamp`、`clock_sync_error`、`plan_version`、`track_version` | main 需要生成 LinkRecord 或扩展 CommunicationSummary；需要统一时间基准和版本字段映射 | P0 |
| 中心/二级/拦截机之间的数据与视频链路用于仲裁 | **已部分实现**。主动仲裁会用 fresh `c2_direct/secondary_relay/video_cue` 链路判断二级节点可用；无新鲜链路不选二级 | `active_degradation.py`；`tests/test_active_degradation.py` | 链路只作为摘要，不包含真实视频 metadata adapter，不记录多跳链路质量历史 | main 需要从中心、二级节点、拦截机之间的数据/视频事件生成 `CommunicationSummary`；D6 需统计 link stale、latency、secondary_selected_rate | P0 |
| 中心恢复合并：双轨日志、冲突后不立即夺权 | **已部分实现**。`merge_recovery()` 比较中心与 fallback assignments，冲突/孤立项进入 review，只有 human_accept 且无冲突才恢复 normal | `coordinator.py`；`tests/test_coordinator.py`；`PLAN.md` | 当前只比较 assignment 列表，不比较完整 track log、terminal lock log、communication log 和 plan digest | 需要持久化双轨 episode log；main 需要提供降级期间和中心恢复后的完整版本序列；D6 需要记录 merge outcome | P1 |
| AirSim D4/D5 stress：case_001/002/003 | **已实现 D4 dry-run 合同测试**。覆盖 continue_center、degrade_to_secondary、degrade_to_distributed，以及 D4 metrics 字段 | `tests/test_airsim_phase1_dry_run_contracts.py`；`README.md` | 尚未直接消费 AirSim runtime 的 5v5 CV JSONL/frames；未形成 D4/D5 stress runner 的端到端报告 | main 需要把 `blocks_frames.jsonl`、D5 terminal/cross-view summary、D1-D3 risk summary 转换成 D4 输入；D6 汇总 stress 指标 | P0 |
| D4 输出指标：`d4_action`、`degradation_mode`、`target_node_id`、风险因素等 | **已部分实现**。`ActiveDegradationDecision.to_metrics()` 输出主要字段，CBBAResult 输出 rounds/conflict/completion/messages | `active_degradation.py`；`models.py`；`tests/test_airsim_phase1_dry_run_contracts.py` | `failover_time`、`secondary_selected_rate`、`distributed_conflict_count` 由 caller 传入，D4 内部没有 episode-level 聚合器 | D6 或 main 需要基于 D4 decisions/events 计算 active/passive 次数、二级接管率、分布式冲突率 | P0 |
| EventRecord / AssignmentPlan 进入主数据总线 | **未在 D4 内实现主总线写入**。D4 可输出 decision dict、CBBAResult、MergeResult，但不直接写 shared bus | `active_degradation.py`；`models.py`；`coordinator.py` | 遵守模块边界，D4 不修改 shared orchestrator；当前等待 main 定义统一 EventRecord/AssignmentPlan adapter | main 需要定义 D4DecisionRecord、DegradationEventRecord、FallbackAssignmentPlan 的跨模块合同 | P0 |
| D1/D2/D3/D5 summary 消费 | **已定义 D4 侧输入 dataclass，未完成跨模块自动适配** | `active_degradation.py`；`README.md`；`PLAN.md` | D4 不能直接依赖其他模块内部模型，避免环形依赖；目前由测试手工构造 summary | 需要 integrated_simulation 或 adapters 将 D1 covariance、D2 id switch、D3 plan validity、D5 terminal association 转成 D4 summary | P0 |
| 分布式无中心下拦截机互通信 | **已实现内存网络仿真**。`SimulatedNetwork` 支持 packet loss、delay、broadcast、message stats | `network.py`；`cbba.py`；`tests/test_cbba.py` | 没有真实链路、ROS 2 topic、AirSim socket 或 mesh adapter，符合当前离线边界 | 若进入更真实仿真，需要 main 统一生成 peer link events；D4 仍只消费摘要，不接真实通信 API | P1 |
| 多区域 coverage_cell 路由与二级节点选择 | **已部分实现**。主动仲裁按 coverage_cell 过滤二级节点并按 priority/lease 排序 | `active_degradation.py`；`models.py`；`tests/test_active_degradation.py` | coordinator 被动 `elect_leader_resource()` 没有严格按任务 coverage 做区域路由，只按资源优先级选全局 leader | 需要多 coverage_cell 场景、每区域 leader/lease、二级节点与任务集的匹配规则 | P1 |
| 安全/身份边界：未知不等于敌方，friend conflict 保守处理 | **已部分实现**。D4 只消费 D5 friend conflict 并输出 hold/review，不做身份判定 | `active_degradation.py`；`tests/test_active_degradation.py` | OpenDroneID、MAVLink signing、DDS Security、AprilTag 属于 D5/main 身份证据栈，D4 不应直接实现 | 需要 D5 把 identity evidence 汇总为 friend_conflict、duplicate lock、auth_state；main 保留授权边界 | P0 |
| 主动降级迟滞/防抖 | **未完整实现**。当前通过 consecutive frames、mismatch limit、plan age、risk threshold 做基础门限，但没有统一 dwell/release hysteresis | `active_degradation.py`；`tests/test_active_degradation.py` | 最小 dry-run 先做单步规则，避免在没有真实数据分布时过早固定迟滞参数 | 需要 5v5 批量 episode 统计、误触发率、恢复条件、最短保持时间和动作切换矩阵 | P1 |
| 与中心化最优解的差距评估 | **未实现系统级对照**。CBBA 有 completion/conflict/rounds，但未和 D3 Hungarian/Min Cost Flow 的最优代价比较 | `cbba.py`；`tests/test_cbba.py`；`C_UAS_MAINSTREAM_SOLUTIONS_AND_DIFFICULTIES.md` | D4 只持有 coarse summaries，缺少 D3 完整 cost matrix 和中心化 plan baseline | 需要 main 同步保存 D3 cost matrix/current plan，并在降级时计算 CBBA assignment gap | P1 |
| 大规模/替代仿真：SCRIMMAGE 或更大多智能体 stress | **未实现**。仅在主流方案文档中作为 AirSim 受限时的可选平台 | `C_UAS_MAINSTREAM_SOLUTIONS_AND_DIFFICULTIES.md`；`reports/AIRSIM_INTEGRATION_PLAN.md` | 当前目标是 AirSim CV 5v5 和离线 point-mass，不需要引入额外仿真引擎 | 完成 5v5 stress 后再评估 SCRIMMAGE adapter、场景评分和通信退化模型 | P2 |

## 已实现能力清单

1. `C2Health` 核心状态与恢复前置审查已经在 D4 内部实现。
2. 被动降级的三级思路已经落地为：中心 failed -> 二级/备份节点优先 -> 无中心 CBBA。
3. 主动降级已有可测试的规则仲裁器，能消费 D1/D2/D3/D5 摘要并优先选择中心重规划或二级辅助。
4. 二级系留/高空侦察节点已经有 `NodeRole.SECONDARY_RECON`、`coordinator_only`、`coverage_cell`、lease/priority 模型。
5. `CommunicationSummary` 已能表达节点来源、链路类型、收发时间、payload 类型和 stale 判断。
6. 简化 CBBA 和内存网络已可用于离线收敛、冲突和通信开销测试。
7. 中心恢复合并已有基础 `merge_recovery()`，避免 heartbeat 一恢复就立即回到 full normal。
8. AirSim phase-1 D4/D5 三个专项 case 已有 D4 侧合同测试。

## 主要未实现原因

1. **模块边界原因**：D4 不直接依赖 D1-D3/D5 的内部类型，也不修改 main runtime，因此跨模块 summary 适配必须由 integrated_simulation/main 完成。
2. **开源适配成本**：MIT CBBA、CBBA-Python、CA-CBBA 更适合理论和研究对照，直接接入需要处理许可证、依赖、数据模型、异步通信语义和 benchmark 适配。
3. **数据条件不足**：主动降级阈值、迟滞和二级接管策略需要 5v5 CV stress 的统计数据校准；当前没有足够 episode 分布支撑更复杂参数。
4. **离线安全边界**：真实通信、真实视频流、飞控、硬件、火控和自动处置均被有意排除，D4 只保留摘要级决策与日志接口。

## 建议下一步

1. **P0：补 main 到 D4 的 adapter**  
   将 D1 的协方差/延迟、D2 的 ID switch/歧义、D3 的 plan_version/plan_age/cost_margin、D5 的 terminal/cross-view/friend conflict 转为 D4 summary，并把 D4 decision 写入统一 EventRecord。

2. **P0：跑 AirSim CV 5v5 D4/D5 stress 端到端**  
   用 `case_001_no_degradation`、`case_002_degrade_to_secondary`、`case_003_degrade_to_distributed` 生成真实 dry-run JSONL 输入，验证二级节点优先级、链路 stale 和 terminal mismatch。

3. **P1：补二级节点生命周期与 coverage 路由**  
   在 main 或 D4 adapter 层维护 secondary heartbeat、lease epoch、coverage cell、video cue freshness，并覆盖多区域多二级节点冲突。

4. **P1：建立 CBBA/拍卖/合同网对照基线**  
   保留当前轻量 CBBA 作为默认保底；新增独立 auction baseline，并评估是否引入 MIT CBBA/CA-CBBA adapter 做论文对照。

5. **P1：完善中心恢复双轨合并**  
   从 assignment-only 扩展到 track digest、terminal lock、communication link 和 plan_version 的组合校验，恢复 normal 前输出明确 review/conflict 列表。
