# D4 文档索引

本目录保存 D4 模块的统一说明文档。

## 主要文档

- `ALGORITHM_AND_IMPLEMENTATION.md`：被动降级、主动降级仲裁、算法原理、数学模型、接口、参数、仿真和实施建议。
- `../PLAN.md`：研发计划与问题抽取。
- `../reports/EXPERIMENT_REPORT.md`：当前实验结果、指标表和丢包率曲线。
- `../reports/AIRSIM_INTEGRATION_PLAN.md`：AirSim 离线回放数据如何映射到 D4 摘要模型。

当前 D4 侧状态见 `../PLAN.md` 的“已实现 / 部分实现 / 未实现 / P1/P2 下一步”：已补二级节点 lifecycle、主动降级迟滞/防抖、D6-compatible event metadata、D5 distributed visual evidence、原子联盟提交和 N 规模输入。2026-07-20 新增 `regional_failover.py`，冻结 scalable3d 场景元数据、逐区域唯一 authority、机动高空二级 coverage/readiness、epoch+plan version+最早 lease、全层 `k>1` 原子门和受约束 distributed fallback 合同；23 项区域测试与 D4 全量 303/303 通过。该结果是纯 Python 合同验证，不是 200v200 动力学、AirSim、真实网络或完整 CCBBA 证据。2026-07-15 的 20-case M5N2 仍只是 `active degradation=0` 的中心负对照，coalition 和第二 primary 5 m 均为 `0/20`。MIT/CA-CBBA、真实通信/视频链路和 Contract Net 不属当前默认路径。

## 阅读顺序

1. 先读 `../PLAN.md`，确认边界和状态机。
2. 再读 `ALGORITHM_AND_IMPLEMENTATION.md`，理解算法与接口。
3. 查看 `../reports/EXPERIMENT_REPORT.md`，核对当前仿真结果。
4. 如需接入 AirSim 离线日志，再读 `../reports/AIRSIM_INTEGRATION_PLAN.md`。
