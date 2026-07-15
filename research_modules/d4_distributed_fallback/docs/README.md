# D4 文档索引

本目录保存 D4 模块的统一说明文档。

## 主要文档

- `ALGORITHM_AND_IMPLEMENTATION.md`：被动降级、主动降级仲裁、算法原理、数学模型、接口、参数、仿真和实施建议。
- `../PLAN.md`：研发计划与问题抽取。
- `../reports/EXPERIMENT_REPORT.md`：当前实验结果、指标表和丢包率曲线。
- `../reports/AIRSIM_INTEGRATION_PLAN.md`：AirSim 离线回放数据如何映射到 D4 摘要模型。

当前 D4 侧状态见 `../PLAN.md` 的“已实现 / 部分实现 / 未实现 / P1/P2 下一步”：已补二级节点 lifecycle、主动降级迟滞/防抖、D6-compatible event metadata、D6-compatible CBBA report metadata、D5 distributed visual evidence -> CBBA 风险加权、`assignment_audit` 和 N 规模输入；轻量 CBBA 仍是完全无中心保底，不构造虚拟中心 Hungarian。2026-07-15 的 20-case M5N2 是 `active degradation=0` 的中心继续执行负对照，coalition 和第二 primary 5 m 均为 `0/20`，不能替代真实 secondary/distributed 多 seed 验收。MIT/CA-CBBA、真实通信/视频链路、Contract Net 和 SCRIMMAGE 不属本轮范围；独立 auction baseline 后置为可选对照，不替代当前 CBBA 保底。

## 阅读顺序

1. 先读 `../PLAN.md`，确认边界和状态机。
2. 再读 `ALGORITHM_AND_IMPLEMENTATION.md`，理解算法与接口。
3. 查看 `../reports/EXPERIMENT_REPORT.md`，核对当前仿真结果。
4. 如需接入 AirSim 离线日志，再读 `../reports/AIRSIM_INTEGRATION_PLAN.md`。
