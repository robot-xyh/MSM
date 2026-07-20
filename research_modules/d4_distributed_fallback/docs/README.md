# D4 文档索引

本目录保存 D4 模块的统一说明文档。

## 主要文档

- `ALGORITHM_AND_IMPLEMENTATION.md`：被动降级、主动降级仲裁、算法原理、数学模型、接口、参数、仿真和实施建议。
- `../PLAN.md`：研发计划与问题抽取。
- `../reports/EXPERIMENT_REPORT.md`：当前实验结果、指标表和丢包率曲线。
- `../reports/AIRSIM_INTEGRATION_PLAN.md`：AirSim 离线回放数据如何映射到 D4 摘要模型。

当前 D4 侧状态见 `../PLAN.md` 的“已实现 / 部分实现 / 未实现 / P1/P2 下一步”：`regional_failover.py` 已冻结动态区域 authority、二级 coverage/readiness、epoch+plan version+最早 lease、全层原子门和受约束 distributed fallback；main-owned 质点模块栈现已消费该合同并覆盖单二级、多二级 owner、distributed D3 plan 与 D7 fencing，定向测试 8/8。新增 `region_resource.py`/`region_resource_learning.py` 提供默认 disabled/shadow 的 truth-free 区域配额/邻区转移建议、确定性安全投影、共享图 actor-critic、BC/PPO、bundle/SHA 和 paired evaluator；专项 32/32、D4 全量 335/335。以上不是 AirSim、真实网络、已训练 checkpoint 或至少 20 个未见 seed 收益证据。2026-07-15 的 20-case M5N2 仍只是 `active degradation=0` 的中心负对照，coalition 和第二 primary 5 m 均为 `0/20`。MIT/CA-CBBA、真实通信/视频链路和 Contract Net 不属当前默认路径。

## 阅读顺序

1. 先读 `../PLAN.md`，确认边界和状态机。
2. 再读 `ALGORITHM_AND_IMPLEMENTATION.md`，理解算法与接口。
3. 查看 `../reports/EXPERIMENT_REPORT.md`，核对当前仿真结果。
4. 如需接入 AirSim 离线日志，再读 `../reports/AIRSIM_INTEGRATION_PLAN.md`。
