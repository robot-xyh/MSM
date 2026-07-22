# D4 文档索引

2026-07-21 文档状态新增保留 seed 配对干预合同及冻结候选隔离加载器：规则 control 与隔离 candidate treatment 的 specification、arm evidence、manifest，以及 `region_resource_bc_900_20260720` 三文件 SHA 复核、raw inference 和规则回退入口均已实现。配对专项 26/26、D4 全量 475/475；正式 20-seed episode 和 D6 outcome sidecar 尚未运行。详细边界见算法文档的“同 seed 配对干预”、模块计划 0.0 节和实验报告 4.12 节。

本目录保存 D4 模块的统一说明文档。

## 主要文档

- `ALGORITHM_AND_IMPLEMENTATION.md`：被动降级、主动降级仲裁、算法原理、数学模型、接口、参数、仿真和实施建议。
- `../PLAN.md`：研发计划与问题抽取。
- `../reports/EXPERIMENT_REPORT.md`：当前实验结果、指标表和丢包率曲线。
- `../reports/AIRSIM_INTEGRATION_PLAN.md`：AirSim 离线回放数据如何映射到 D4 摘要模型。
- `../reports/D4_REGION_RESOURCE_FULL_SAMPLE_ADMISSION_20260721.md`：正式区域数据与 clean supplemental 课程的全样本准入结果；同名 JSON 是 D6 显式路径和带外 SHA256 复核入口。

当前 D4 侧状态见 `../PLAN.md` 的“已实现 / 部分实现 / 未实现 / P1/P2 下一步”：`regional_failover.py` 已冻结动态区域 authority、二级 coverage/readiness、epoch+plan version+最早 lease、全层原子门和受约束 distributed fallback；main-owned 质点模块栈现已消费该合同并覆盖单二级、多二级 owner、distributed D3 plan 与 D7 fencing，既有定向测试 8/8。`region_resource.py`/`region_resource_learning.py` 提供默认 disabled/shadow 的 truth-free 区域建议、消费合同和学习研究路径；`region_resource_paired_intervention.py` 只读加载固定 development bundle，生成未投影候选后复用确定性投影和回退，不改变生产 advisor 准入。`region_resource_dataset.py` 的 dataset-v1 对规则教师 target 重验 projector/authority/edge 证明，并对 manifest inventory/split 做独立一致性校验；`canonical_seed_split.py` 提供只读 60/20/20 shared-registry 视图；`region_resource_curriculum.py` 在独立目录生成规则教师动作覆盖课程；`region_resource_full_sample_audit.py` 对正式 900 episode 和 clean supplemental 100 episode 执行只读全样本准入。`region_resource_runtime_ack.py` 输出 v2 只读证据，区分严格新执行计划和同代评估刷新；`region_resource_reward_evidence.py` 再把 ACK 与非重叠区域结果窗口、八项原始成本和来源哈希绑定。运行时确认阶段为 430/430，加入奖励与隔离加载回归后当前 D4 全量为 475/475。旧 `compute_region_resource_reward()` 没有 ACK、availability、provenance 或窗口绑定，只保留为研究辅助函数。冻结全样本仍没有这组 runtime/result 字段；`target.kind=rule` 不是 truth，projected recommendation 和隔离采用也不是 runtime applied ACK。`CoalitionMemberAck`、物理 outcome、因果/paired/on-policy 证据与 D6 外部复核仍 unavailable/pending，PPO、assist 和 authority 继续关闭。2026-07-15 的 20-case M5N2 仍只是 `active degradation=0` 的中心负对照，coalition 和第二 primary 5 m 均为 `0/20`。MIT/CA-CBBA、真实通信/视频链路和 Contract Net 不属当前默认路径。

## 阅读顺序

1. 先读 `../PLAN.md`，确认边界和状态机。
2. 再读 `ALGORITHM_AND_IMPLEMENTATION.md`，理解算法与接口。
3. 查看 `../reports/EXPERIMENT_REPORT.md`，核对当前仿真结果。
4. 如需接入 AirSim 离线日志，再读 `../reports/AIRSIM_INTEGRATION_PLAN.md`。
