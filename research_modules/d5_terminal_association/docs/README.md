# D5 文档索引

D5 文档遵循 `research_modules/DOCUMENTATION_STANDARD.md`。推荐阅读顺序：

1. `../README.md`：模块用途、运行方式和接口入口。
2. `../PLAN.md`：终端视觉配准与身份认证研发计划。
3. `ALGORITHM_AND_IMPLEMENTATION.md`：图像投影、几何门控、局部 MOT、身份正向确认、`ReconImageCue` 约束、`TerminalConsistencyTracker`、distributed visual association 和 D4/D7 合同。
4. `EXPERIMENT_REPORT.md`：离线仿真结果、终端决策曲线和二级侦察 cue 说明。
5. `AIRSIM_INTEGRATION_PLAN.md`：AirSim 离线回放接入计划。

本模块只输出 `TerminalAssociation`、`TerminalConsistencySummary`、跨视角证据和身份/配准判断，不输出控制量、处置动作、真实火控参数、降级动作或授权绕过流程；在线 D5 不得使用 AirSim truth ID，truth 只用于离线评分。2026-07-07 后，连续一致性窗口按 `resource_id + assigned_global_track_id` 维护，不因同一 assignment pair 的 D3 `assignment_version` 滚动更新而清零。

2026-07-09 P1 状态：D5 侧已具备 detect-to-global registration、`DetectToGlobalTrackCandidate.outcome`、`detect_registration_outcome`/`detect_registration_reject_reasons`、timestamp/measurement-age/covariance/projection covariance 记录、`projection_invalid` 独立断点、自适应像素协方差、默认 3 帧稳定窗口、跨视角配准证据、YOLO/MOT confidence/class/bbox-scale/tracker-backend/CPU-GPU budget metadata 和 mobile recon gimbal evidence；main/D6 已有 P1 sweep 与报告 bundle 消费口径。D5 仍不启动 AirSim、不生成总报告、不使用 AirSim truth ID、不创建/改写/换绑 `global_track_id`。剩余工作集中在真实 AirSim 多 seed 标定、二级覆盖策略、YOLO/MOT 阈值与预算实测、`solvePnP`/外参增强和 BoT-SORT/Deep SORT/ReID 等 P2 评估。
