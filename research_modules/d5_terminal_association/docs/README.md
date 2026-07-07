# D5 文档索引

D5 文档遵循 `research_modules/DOCUMENTATION_STANDARD.md`。推荐阅读顺序：

1. `../README.md`：模块用途、运行方式和接口入口。
2. `../PLAN.md`：终端视觉配准与身份认证研发计划。
3. `ALGORITHM_AND_IMPLEMENTATION.md`：图像投影、几何门控、局部 MOT、身份正向确认、`ReconImageCue` 约束、distributed visual association 和 D4/D7 合同。
4. `EXPERIMENT_REPORT.md`：离线仿真结果、终端决策曲线和二级侦察 cue 说明。
5. `AIRSIM_INTEGRATION_PLAN.md`：AirSim 离线回放接入计划。

本模块只输出 `TerminalAssociation`、跨视角证据和身份/配准判断，不输出控制量、处置动作、真实火控参数或授权绕过流程；在线 D5 不得使用 AirSim truth ID，truth 只用于离线评分。
