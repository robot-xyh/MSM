# D2 文档索引

D2 文档遵循 `research_modules/DOCUMENTATION_STANDARD.md`。推荐阅读顺序：

1. `../README.md`：模块用途、运行方式和目录入口。
2. `../PLAN.md`：研发计划和问题定义。
3. `ALGORITHM_AND_IMPLEMENTATION.md`：二维兼容主线、六维稀疏 GNN/Hungarian、结构歧义身份承诺、恢复水位线与发布新鲜度门控、identity commitment evaluator v2、JPDA/MHT、航迹生命周期、离线 global-track truth mapping、v2 标签处置、严格指标和唯一锚点部分身份诊断。
4. `EXPERIMENT_REPORT.md`：离线仿真结果、5/20/50/100/200 稀疏关联证据、旧歧义候选重入与发布超龄回归、身份合同与 evaluator v2 回归、20-seed 严格身份阻断复核、v2 处置合同验证、active-risk seed 1005、clean-tree 结果、有界 claim/OOSM 模块测试和失败场景分析。
5. `D2_SCALABLE_3D_PERFORMANCE_BENCHMARK_CN.md`：200v200 五 seed 热路径 profile、分阶段墙钟、逐域语义哈希和已知限制。
6. `D2_SCALABLE_3D_IDENTITY_BLOCKER_AUDIT_CN.md`：20-seed producer 重放、严格指标阻断分型、逐航迹时间段和 D1 mapping completeness 结论；聚合机器数据见 `d2_scalable_3d_identity_blocker_audit_20260723.json`。
7. `AIRSIM_INTEGRATION_PLAN.md`：AirSim 离线回放接入计划，以及 D1 观测谱系、versioned claim ledger、整帧 OOSM adapter、v2 truth sidecar、部分身份诊断和 main/D6 持久化字段要求。

本模块只用于离线科研仿真和数据关联评估，不包含真实飞控、硬件、火控、毁伤或自动处置逻辑。
