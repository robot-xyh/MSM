# D4 文档索引

本目录保存 D4 模块的统一说明文档。

## 主要文档

- `ALGORITHM_AND_IMPLEMENTATION.md`：被动降级、主动降级仲裁、算法原理、数学模型、接口、参数、仿真和实施建议。
- `../PLAN.md`：研发计划与问题抽取。
- `../reports/EXPERIMENT_REPORT.md`：当前实验结果、指标表和丢包率曲线。
- `../reports/AIRSIM_INTEGRATION_PLAN.md`：AirSim 离线回放数据如何映射到 D4 摘要模型。

当前 D4 侧 P1 状态见 `../PLAN.md` 的 `P1 Gap Status`：已补二级节点生命周期摘要、主动降级迟滞/防抖配置、D6-compatible decision event metadata 和对应测试；轻量 CBBA 保持不变，未新增 MIT/CA-CBBA、auction 或 contract-net。

## 阅读顺序

1. 先读 `../PLAN.md`，确认边界和状态机。
2. 再读 `ALGORITHM_AND_IMPLEMENTATION.md`，理解算法与接口。
3. 查看 `../reports/EXPERIMENT_REPORT.md`，核对当前仿真结果。
4. 如需接入 AirSim 离线日志，再读 `../reports/AIRSIM_INTEGRATION_PLAN.md`。
