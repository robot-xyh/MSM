# D4 文档索引

2026-07-26 完成 A2 预准入证据装配盘点。D4 已有 development bundle、运行采用 ACK、联盟
状态、通信因果回执、区域结果窗和隔离 paired 合同，但尚无模块 evidence assembler 将同一
候选、严格后继计划、逐成员 ACK、物理结果和 D6 R0 配对非退化绑定后生成新 bundle。现有
v2 writer/loader 和 advisor 不存在裸布尔或占位摘要自晋级路径，因此当前是 P1，不是 P0。
D6 负责冻结通用外部审计，D4 后续只实现模块语义装配；详细字段见
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

当前 D4 侧状态见 `../PLAN.md` 的“已实现 / 部分实现 / 未实现 / P1/P2 下一步”：`regional_failover.py` 已冻结动态区域 authority、二级 coverage/readiness、epoch+plan version+最早 lease、全层原子门和受约束 distributed fallback；main-owned 质点模块栈现已消费该合同并覆盖单二级、多二级 owner、distributed D3 plan、通信因果收据、异步三成员确认与 D7 fencing。`region_resource.py`/`region_resource_learning.py` 提供默认 disabled/shadow 的 truth-free 区域建议、消费合同和学习研究路径；`region_resource_paired_intervention.py` 只读加载固定 development bundle，生成未投影候选后复用确定性投影和回退，不改变生产 advisor 准入。`region_resource_dataset.py` 的 dataset-v1 对规则教师 target 重验 projector/authority/edge 证明，并对 manifest inventory/split 做独立一致性校验；`canonical_seed_split.py` 提供只读 60/20/20 shared-registry 视图；`region_resource_curriculum.py` 在独立目录生成规则教师动作覆盖课程；`region_resource_full_sample_audit.py` 对正式 900 episode 和 clean supplemental 100 episode 执行只读全样本准入。`region_resource_runtime_ack.py` 输出 v2 生产运行时只读证据，`region_resource_isolated_rollout.py` 输出明确非生产的隔离 receipt/adoption 证据，二者都区分严格新执行计划和同代评估刷新；`region_resource_reward_evidence.py` 再把生产 ACK 与非重叠区域结果窗口、八项原始成本和来源哈希绑定。当前 D4 全量为 569/569。旧 `compute_region_resource_reward()` 没有 ACK、availability、provenance 或窗口绑定，只保留为研究辅助函数。冻结全样本仍没有这组 runtime/result 字段；`target.kind=rule` 不是 truth，projected recommendation 和隔离采用也不是 production runtime applied ACK。正式 v2 producer 提供 execution receipts 和门诊断，D6 consumer sidecar 另提供同帧离线分配比较；物理 outcome、因果/paired/on-policy 性能证据仍 unavailable/pending，PPO、assist 和 authority 继续关闭。2026-07-15 的 20-case M5N2 仍只是 `active degradation=0` 的中心负对照，coalition 和第二 primary 5 m 均为 `0/20`。MIT/CA-CBBA、真实通信/视频链路和 Contract Net 不属当前默认路径。

## 阅读顺序

1. 先读 `../PLAN.md`，确认边界和状态机。
2. 再读 `ALGORITHM_AND_IMPLEMENTATION.md`，理解算法与接口。
3. 查看 `../reports/EXPERIMENT_REPORT.md`，核对当前仿真结果。
4. 如需接入 AirSim 离线日志，再读 `../reports/AIRSIM_INTEGRATION_PLAN.md`。
