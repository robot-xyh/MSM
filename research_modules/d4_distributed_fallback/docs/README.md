# D4 文档索引

2026-07-27 新增实际区域策略 calibration-only 诊断。实际 development 模型在 20 个互斥
校准 seed、420 个样本中产生 76 个安全非零区域建议；344 个无操作主要由已承诺资源占满后
备用比例请求被确定性投影压回基线造成。固定门通过 420/420，保留 seed 和在线真值使用为
0，原始离散动作签名为 88 种。候选 manifest SHA-256、模型权重、数据集、逐 seed 分母和
稳定分类摘要已经绑定；两次重跑均为 76/344。候选实现谱系与当前代码不一致，因此当前谱系
开发证据、正式采用、收益和权限均为 false。紧凑结果见
`../reports/region_resource_a2_actual_policy_calibration_20260727_v1/`，专项 10/10、D4 当前
全量 **689/689 passed**。

2026-07-27 提交就绪复核完成。联盟成员确认、联盟时间、通信映射和安全采用布尔字段已改为
严格类型；中心、二级和完全分布式 owner 的可用证据均不授予权限。开发适配器从正式收益
审计来源入口失败关闭。D4 全量 **679/679 passed**，未运行 AirSim；真实 episode ACK、
物理窗口、同键 R0 和多随机种子收益仍为 P1。

2026-07-27 新增受约束的 A2 开发态非零干预适配器。它在学习候选为无操作时优先输出单区域
request-replan-only，其次输出总量受限的跨区转移，最后只对没有 committed binding 的区域
输出 hold。候选仍经过原确定性投影、权威、时期、租约和安全采用门。适配器没有 admitted
manifest，正式收益审计拒绝其策略身份，因此只用于开发链路测试。

候选无操作判定现已与投影后的 D3 消费字段对齐。原始备用比例、transfer 或布尔动作必须先
经过共享确定性投影器、advisory 发布和同 snapshot 消费检查；投影后回到基线时继续尝试
request-replan、bounded transfer 和安全 hold。单样本回归覆盖了 3 个可用资源、2 个已
承诺资源下的备用比例假变化，结果正确转为 request-replan-only。

formal decision 现在通过显式协议进入适配器首次投影。默认关闭的开发开关还允许在规则无
动作、全部资源受保护时输出一个 request-replan-only。标准 advisor 仍保持 shadow，不授予
assist 或 authority。

main 先前固定最小区域 hold+request helper 为 15/20；五个问题 seed 已加入 D4 request-only
回归并通过。当前安全采用专项为 68/68，D4 全量为 674/674 passed。指定 seed 1 内存
full episode 已用 development-only admitted transport 夹具到达
`physical_window_available`，authority 和 benefit 保持 false。main 仍需重跑完整
20-seed；现有结果不能写成模型收益或生产权限证据。

2026-07-27 已完成 A2 无操作建议归因修正。确定性投影和消费只作为链路证据；D4 另行重算
资源配额、跨区转移、整数备用资源、`hold` 和 `request_replan` 是否发生变化。无可辨识
干预时，后继计划和物理窗口不会附着，收益审计也拒绝输入。当前开发 20-seed 正确结果为链路
20/20、可辨识干预 0/20、实际采用 0/20、收益审计 0/20。安全采用专项 **52/52 passed**，
无操作/真实 successor 集成专项 **6/6 passed**，D4 全量 **658/658 passed**。详细语义见
模块原理、算法文档和 GAP 审计。

main/D6 已于 2026-07-27 完成上述 20-seed 正确重算并发布结果。20 个拒绝原因均为
`identifiable_regional_intervention_missing`；批次 SHA-256 为
`ff3c10a089b6a94582451ae05d8a884af3a2bd7485acd4df0496442ea7e0ec55`。原 18/20 采用
结论已被该结果取代，不再作为当前证据。

2026-07-27 已完成 A2 同键 R0 只读审计输入合同。候选与规则臂使用相同
`paired_exogenous_config_sha256`、comparison key 和逻辑窗口，使用不同 execution arm、
episode 事件日志和物理窗口；持久化 `learning_adoption_evidence.json` 可在离线阶段严格
解析，不依赖原进程对象。D4 只输出 D6 审计资格，不计算收益或开放权限。安全采用专项
50/50、D4 全量 655/655 passed；真实独立双 episode、20 个未见 seed 和 D6 收益结果仍未
形成。

2026-07-27 已完成 A2 owner/coalition 公共确认合同。D4 现可保留 main runtime assignment
ACK 的 payload SHA-256 和 bus sequence，构造并严格解析
`d4.regional_plan_owner_ack.v1`，从实际 delivered message 生成内容寻址 receipt，并通过
公共 validator 校验 owner 与嵌套 `CoalitionMemberAck`。四文件联合 130/130、D4 全量
626/626 passed。main 尚未完成真实 ACK 路由、采用后物理窗口和 same-key R0，因此正式
learned adoption 仍为 0，缺失项保持 unavailable。

2026-07-26 的 A2 模块 evidence assembler、strict loader 和外层 bundle 合同已经完成。
它能把同一候选、严格后继计划、逐成员 ACK、物理结果和 D6 R0 配对非退化绑定为可校验内容
身份，但现有实物外审仍失败关闭。v2 writer/loader 和 advisor 不存在裸布尔或占位摘要
自晋级路径，因此当前剩余项是跨模块 P1 证据生产，不是 P0。详细字段见
`ALGORITHM_AND_IMPLEMENTATION.md` 和 `../PLAN.md`。

2026-07-26 已完成 A2/C1/F1 严格准入复核。现有 `d4-region-bc-900-development-v1` 继续是
development/shadow-only；v2 writer 已禁止自声明 qualified/assist，无 admitted manifest 的注入策略
也不能进入 assist。nominal 20-seed 候选采用为 0/20；`active_risk` 20-seed 虽有物理窗和描述性
非退化结果，但 D4 候选采用为 0/20，执行路径均为确定性规则回退。当前不得生成 admitted bundle，
正式学习 scope 数为 0。详细结论见 `../README.md`、`../PLAN.md` 和本目录两份原理文档。

2026-07-25 当前 D4 全量为 **569/569 passed**。新增通信因果证据门和异步联盟确认状态机均已实现并完成模块回归。main-owned scalable 3D 单随机种子场景 `1271` 已验证 2 目标、4 资源下的 0/3 ACK 保持、3/3 ACK 原子提交、两个主成员释放和备用成员待命；在线真值使用与 `global_track_id` 改写均为 0。该结果不是 AirSim、多随机种子、真实网络、正式 5700 单元矩阵或 200 对 200 性能证据。

2026-07-22 已复核隔离多周期 degraded rollout 的 source/applied 代际。source 必须是 formal D4 decision 命名的当前区域 authority 计划；被动降级前的中心/二级 `previous_plan` 只能作为 D3 祖先。applied 只能是同 owner/epoch/lease 下的严格更高版本，或同身份、同 binding 的显式刷新。中心失效 20-seed 首轮 196 条区域记录均因同版本异 ID 被安全拒绝；这是当时的生产者缺口记录。专项 26/26、该阶段 D4 全量 508/508；`production_runtime_ack`、因果和生产 authority 仍保持不可用。详细判据见算法文档 0.0A 和模块计划的 2026-07-22 复核项。

2026-07-22 文档状态已包含保留 seed 配对干预合同、冻结候选隔离加载器、正式 evidence v2 和 D6 profile-bound v2 outcome-availability sidecar。D6 独立重算确认 nominal 5v5 seed 1000-1019 的 20/20 candidate considered、confidence 0/20、OOD/latency/finite/failure 各 20/20、aggregate 0/20、safe adoption 0/20 和规则回退 20/20，`minimum_confidence=0.6` 未改变。sidecar 状态为 `pass_offline_assignment_comparison_only`；执行时延 nearest-rank P95 为 `2.241315 ms`，门控汇总线性插值 P95 为 `2.264415 ms`。availability sidecar 已存在不代表 runtime ACK、物理结果、paired effect/non-degradation、counterfactual、causal 或降级策略效果可用。详细边界见算法文档的“同 seed 配对干预”、模块计划 0.0 节和实验报告 4.12 节。

本目录保存 D4 模块的统一说明文档。

## 主要文档

- `ALGORITHM_AND_IMPLEMENTATION.md`：被动降级、主动降级仲裁、算法原理、数学模型、接口、参数、仿真和实施建议。
- `../PLAN.md`：研发计划与问题抽取。
- `../reports/EXPERIMENT_REPORT.md`：当前实验结果、指标表和丢包率曲线。
- `../reports/AIRSIM_INTEGRATION_PLAN.md`：AirSim 离线回放数据如何映射到 D4 摘要模型。
- `../reports/D4_REGION_RESOURCE_FULL_SAMPLE_ADMISSION_20260721.md`：正式区域数据与 clean supplemental 课程的全样本准入结果；同名 JSON 是 D6 显式路径和带外 SHA256 复核入口。

当前 D4 侧状态见 `../PLAN.md` 的“已实现 / 部分实现 / 未实现 / P1/P2 下一步”：`regional_failover.py` 已冻结动态区域 authority、二级 coverage/readiness、epoch+plan version+最早 lease、全层原子门和受约束 distributed fallback；main-owned 质点模块栈现已消费该合同并覆盖单二级、多二级 owner、distributed D3 plan、通信因果收据、异步三成员确认与 D7 fencing。`region_resource.py`/`region_resource_learning.py` 提供默认 disabled/shadow 的 truth-free 区域建议、消费合同和学习研究路径；`region_resource_paired_intervention.py` 只读加载固定 development bundle，生成未投影候选后复用确定性投影和回退，不改变生产 advisor 准入。`region_resource_dataset.py` 的 dataset-v1 对规则教师 target 重验 projector/authority/edge 证明，并对 manifest inventory/split 做独立一致性校验；`canonical_seed_split.py` 提供只读 60/20/20 shared-registry 视图；`region_resource_curriculum.py` 在独立目录生成规则教师动作覆盖课程；`region_resource_full_sample_audit.py` 对正式 900 episode 和 clean supplemental 100 episode 执行只读全样本准入。`region_resource_runtime_ack.py` 输出 v2 生产运行时只读证据并保留 assignment ACK 内容引用，`region_resource_safe_adoption.py` 提供 owner/coalition 公共确认和严格采用装配，`region_resource_isolated_rollout.py` 输出明确非生产的隔离 receipt/adoption 证据；`region_resource_reward_evidence.py` 再把生产 ACK 与非重叠区域结果窗口、八项原始成本和来源哈希绑定。当前 D4 全量为 674/674。旧 `compute_region_resource_reward()` 没有 ACK、availability、provenance 或窗口绑定，只保留为研究辅助函数。冻结全样本仍没有这组 runtime/result 字段；`target.kind=rule` 不是 truth，projected recommendation 和隔离采用也不是 production runtime applied ACK。正式 v2 producer 提供 execution receipts 和门诊断，D6 consumer sidecar 另提供同帧离线分配比较；物理 outcome、因果/paired/on-policy 性能证据仍 unavailable/pending，PPO、assist 和 authority 继续关闭。2026-07-15 的 20-case M5N2 仍只是 `active degradation=0` 的中心负对照，coalition 和第二 primary 5 m 均为 `0/20`。MIT/CA-CBBA、真实通信/视频链路和 Contract Net 不属当前默认路径。

## 阅读顺序

1. 先读 `../PLAN.md`，确认边界和状态机。
2. 再读 `ALGORITHM_AND_IMPLEMENTATION.md`，理解算法与接口。
3. 查看 `../reports/EXPERIMENT_REPORT.md`，核对当前仿真结果。
4. 如需接入 AirSim 离线日志，再读 `../reports/AIRSIM_INTEGRATION_PLAN.md`。
