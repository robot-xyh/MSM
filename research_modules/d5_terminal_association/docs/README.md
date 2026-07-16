# D5 文档索引

D5 文档遵循 `research_modules/DOCUMENTATION_STANDARD.md`。推荐阅读顺序：

1. `../README.md`：模块用途、运行方式和接口入口。
2. `../PLAN.md`：终端视觉配准与身份认证研发计划。
3. `ALGORITHM_AND_IMPLEMENTATION.md`：图像投影、几何门控、局部 MOT、身份正向确认、`ReconImageCue` 约束、`TerminalConsistencyTracker`、distributed visual association 和 D4/D7 合同。
4. `EXPERIMENT_REPORT.md`：离线仿真结果、终端决策曲线和二级侦察 cue 说明。
5. `AIRSIM_INTEGRATION_PLAN.md`：AirSim 离线回放接入计划。
6. `../reports/D5_MANUAL_VIDEO_TRACKING_B_20260715.md`：人工初始化五目标视频 local MOT 实测报告。

本模块只输出 `TerminalAssociation`、`TerminalConsistencySummary`、跨视角证据和身份/配准判断，不输出控制量、处置动作、真实火控参数、降级动作或授权绕过流程；在线 D5 不得使用 AirSim truth ID，truth 只用于离线评分。2026-07-07 后，连续一致性窗口按 `resource_id + assigned_global_track_id` 维护，不因同一 assignment pair 的 D3 `assignment_version` 滚动更新而清零。

2026-07-15 M5N2 最终一致性口径：baseline/candidate 各 10 seeds，共 20 case；第二 primary 按每场 current active-primary membership 动态识别，`3725/3725` 条适用记录可用，但其 5 m 物理结果和 T001 coalition completion 均为 `0/20`。直接 `failure_category` 未持久化。TERM 生效前额外完成的 `png_ttc_2v2_seed001` 排除在该聚合之外，dropout case 执行数为 0。20 个第二 primary 最终均记录为 `collision_stop`，但这只是 D7 停控证据；碰撞对象未落盘，不能单独归因于 D5。

2026-07-14 canonical actual 状态：五层 contract/control/terminal-switch/mode/physical 已独立 available，总计 `102/26/26/2/4`；`terminal_switch_allowed_count` 从最终 `control_commands.csv` 独立统计，2v2/M5N2 为 `26/0`，不从 control 层回填。当前开放 P1 仅聚焦 M5N2 第二 primary、真实几何 drift、detect/YOLO/MOT 多 seed 和二级同 tick freshness；IBVS、真实身份源、完整在线 PnP/ROS 2 保持 P2/P3。

2026-07-14 最新代码级 P1 更新：原生 ByteTrack/BoT-SORT 的 `mot_history_length` 已按资源/相机/backend/native ID 累计连续实测命中；`d5_live_visual_funnel_v1` 进一步分离 live detect、raw lock、execution contract、measured stable lock、bbox 和 handoff，D5 全量 `258 passed`。最新 seed-1 显示 INT-02 实际已有持续 detect/raw lock，剩余主断点是 arrival-window 时基和 main->D7 bbox/handoff 路由；真实多 seed 准入仍开放。

2026-07-15 新增人工初始化单视频 local MOT：首帧多 ROI 生成固定 `local-xxx`，默认独立 CSRT，可选亮点候选 Hungarian 一对一关联。`b.mp4` 95 帧五目标无完全重复中心。该工具不是 GlobalTrack 注册、敌我识别或算法准入证明，不改变 AirSim detect-first 主线。

2026-07-09 P1 状态：D5 侧已具备 detect-to-global registration、`DetectToGlobalTrackCandidate.outcome`、`detect_registration_outcome`/`detect_registration_reject_reasons`、timestamp/measurement-age/covariance/projection covariance 记录、`projection_invalid` 独立断点、自适应像素协方差、默认 3 帧稳定窗口、跨视角配准证据、YOLO/MOT confidence/class/bbox-scale/tracker-backend/CPU-GPU budget metadata 和 mobile recon gimbal evidence；main/D6 已有 P1 sweep 与报告 bundle 消费口径。D5 仍不启动 AirSim、不生成总报告、不使用 AirSim truth ID、不创建/改写/换绑 `global_track_id`。剩余工作集中在真实 AirSim 多 seed 标定、二级覆盖策略、YOLO/MOT 阈值与预算实测、`solvePnP`/外参增强和 BoT-SORT/Deep SORT/ReID 等 P2 评估。
