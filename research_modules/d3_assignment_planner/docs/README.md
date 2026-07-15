# D3 文档索引

D3 文档遵循 `research_modules/DOCUMENTATION_STANDARD.md`。推荐阅读顺序：

1. `../README.md`：模块用途、运行方式和目录入口。
2. `../PLAN.md`：集中式资源-目标分配研发计划。
3. `ALGORITHM_AND_IMPLEMENTATION.md`：Hungarian、最小费用流、代价函数、迟滞重分配、版本管理，以及面向 D4 主动降级的计划有效性信号。
4. `EXPERIMENT_REPORT.md`：离线仿真结果和图表说明。
5. `AIRSIM_INTEGRATION_PLAN.md`：AirSim 离线回放接入计划。
6. `../results/EXPERIMENT_REPORT_GENERATED.md`：脚本生成的实验报告快照。

本模块只生成候选分配计划和审计数据，不包含真实飞控、硬件、火控、毁伤或自动处置逻辑。

最新证据基线为 2026-07-15 的 M5N2 baseline/candidate 各 10 seeds、共 20 case。
`EXPERIMENT_REPORT.md` 记录物理结果与 D3 history 聚合，`AIRSIM_INTEGRATION_PLAN.md`
记录写盘可用性和后续接线，`PLAN.md` 记录剩余 P1。额外的
`png_ttc_2v2_seed001` 不属于该 M5N2 聚合，未运行 case 不补零。
