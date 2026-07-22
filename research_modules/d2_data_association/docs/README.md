# D2 文档索引

D2 文档遵循 `research_modules/DOCUMENTATION_STANDARD.md`。推荐阅读顺序：

1. `../README.md`：模块用途、运行方式和目录入口。
2. `../PLAN.md`：研发计划和问题定义。
3. `ALGORITHM_AND_IMPLEMENTATION.md`：二维兼容主线、六维稀疏 GNN/Hungarian、JPDA/MHT、航迹生命周期、离线 global-track truth mapping 和指标说明。
4. `EXPERIMENT_REPORT.md`：离线仿真结果、5/20/50/100/200 稀疏关联证据、身份合同回归、active-risk seed 1005、clean-tree 20-seed 结果、有界 claim/OOSM 模块测试和失败场景分析。
5. `AIRSIM_INTEGRATION_PLAN.md`：AirSim 离线回放接入计划，以及 D1 观测谱系、版本化 claim ledger、整帧 OOSM adapter 和 main runtime 持久化字段要求。

本模块只用于离线科研仿真和数据关联评估，不包含真实飞控、硬件、火控、毁伤或自动处置逻辑。
