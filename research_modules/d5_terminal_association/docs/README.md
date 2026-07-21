# D5 文档索引

D5 文档遵循 `research_modules/DOCUMENTATION_STANDARD.md`。推荐阅读顺序：

1. `../README.md`：模块用途、运行方式和接口入口。
2. `../PLAN.md`：终端视觉配准与身份认证研发计划。
3. `D5_MULTICAMERA_ASSOCIATION_REPORT_CN.md`：D5 多相机几何关联技术报告，使用模块内稳定图片路径。
4. `D5_MULTICAMERA_ASSOCIATION_REPORT_CN.docx`：Word 技术报告，严格区分已实现、单 seed 仿真验证、建议指标和待验证内容。
5. `ALGORITHM_AND_IMPLEMENTATION.md`：图像投影、几何门控、局部 MOT、身份正向确认、`ReconImageCue` 约束、`TerminalConsistencyTracker`、distributed visual association 和 D4/D7 合同。
6. `EXPERIMENT_REPORT.md`：离线仿真结果、终端决策曲线和二级侦察 cue 说明。
7. `AIRSIM_INTEGRATION_PLAN.md`：AirSim 离线回放接入计划。
8. `../reports/D5_MANUAL_VIDEO_TRACKING_B_20260715.md`：人工初始化五目标视频 local MOT 实测报告。

2026-07-20 active-vision staging 专项的复现入口为
`../simulations/profile_active_vision_episode_staging.py`，对照 JSON 和 cProfile 文本位于
`../results/active_vision_staging_profile_*`。该专项保持 gzip level 6 和磁盘 schema，关闭 D5-owned
共享 snapshot 重复审计/编码热点；main clean-tree 三 seed 与正式 900 episode 验收仍未完成。

2026-07-20 新增匿名稀疏 tracklet 图文档：实现入口为
`../src/d5_terminal_association/sparse_tracklet_graph.py`、`tracklet_gnn.py` 和
`active_vision.py`；原理、算法、AirSim 待接线和代码级实验分别同步在
`MODULE_PRINCIPLES_CN.md`、`ALGORITHM_AND_IMPLEMENTATION.md`、
`AIRSIM_INTEGRATION_PLAN.md` 与 `EXPERIMENT_REPORT.md`。小样本训练仅为 smoke，
当前没有已验收 checkpoint 或学习型主动视觉策略。2026-07-20 P0 复审后，构造器与递归
payload guard 已进一步拒绝 `TGT-0001`、`TargetDrone_1` 等 truth-like local ID，同时保留
`cam01-track-0001`。当前构图已用视锥/时间/空间桶索引和相机对预算替代全 camera-pair，
并用每 tracklet 候选上限替代每对 `n_left x n_right` 矩阵。

同日新增 `../src/d5_terminal_association/scalable_3d_adapter.py`：这是 D5-owned、duck-typed
scalable 3D 在线 DTO 入口，负责匿名 per-camera tracking、相机 metadata 几何/协方差转换、
六维中心航迹只读投影和带显式规则 fallback 的图关联。2026-07-20 D5 全量
`343 passed`；5/20/50/100/200 相机结构矩阵已通过。main scalable module stack 已调用 adapter，
但新增诊断持久化、真实多 seed、独立数据划分及训练 checkpoint 仍为 P1，不得把结构测试
解释为 episode 或模型验收。

`../scripts/generate_multicamera_report.py` 用于生成中文原理图、中文仿真图表和
Word 技术报告。默认从 `assets/d5_multicamera_association/` 读取稳定截图与
绘图数据；只有显式使用 `--sync-formal-assets` 时才从正式 AirSim 输出同步副本。

本模块只输出 `TerminalAssociation`、`TerminalConsistencySummary`、跨视角证据和身份/配准判断，不输出控制量、处置动作、真实火控参数、降级动作或授权绕过流程；在线 D5 不得使用 AirSim truth ID，truth 只用于离线评分。2026-07-07 后，连续一致性窗口按 `resource_id + assigned_global_track_id` 维护，不因同一 assignment pair 的 D3 `assignment_version` 滚动更新而清零。

2026-07-15 M5N2 最终一致性口径：baseline/candidate 各 10 seeds，共 20 case；第二 primary 按每场 current active-primary membership 动态识别，`3725/3725` 条适用记录可用，但其 5 m 物理结果和 T001 coalition completion 均为 `0/20`。直接 `failure_category` 未持久化。TERM 生效前额外完成的 `png_ttc_2v2_seed001` 排除在该聚合之外，dropout case 执行数为 0。20 个第二 primary 最终均记录为 `collision_stop`，但这只是 D7 停控证据；碰撞对象未落盘，不能单独归因于 D5。

2026-07-14 canonical actual 状态：五层 contract/control/terminal-switch/mode/physical 已独立 available，总计 `102/26/26/2/4`；`terminal_switch_allowed_count` 从最终 `control_commands.csv` 独立统计，2v2/M5N2 为 `26/0`，不从 control 层回填。当前开放 P1 仅聚焦 M5N2 第二 primary、真实几何 drift、detect/YOLO/MOT 多 seed 和二级同 tick freshness；IBVS、真实身份源、完整在线 PnP/ROS 2 保持 P2/P3。

2026-07-14 最新代码级 P1 更新：原生 ByteTrack/BoT-SORT 的 `mot_history_length` 已按资源/相机/backend/native ID 累计连续实测命中；`d5_live_visual_funnel_v1` 进一步分离 live detect、raw lock、execution contract、measured stable lock、bbox 和 handoff，D5 全量 `258 passed`。最新 seed-1 显示 INT-02 实际已有持续 detect/raw lock，剩余主断点是 arrival-window 时基和 main->D7 bbox/handoff 路由；真实多 seed 准入仍开放。

2026-07-15 新增人工初始化单视频 local MOT：首帧多 ROI 生成固定 `local-xxx`，默认独立 CSRT，可选亮点候选 Hungarian 一对一关联。`b.mp4` 95 帧五目标无完全重复中心。该工具不是 GlobalTrack 注册、敌我识别或算法准入证明，不改变 AirSim detect-first 主线。

2026-07-09 P1 状态：D5 侧已具备 detect-to-global registration、`DetectToGlobalTrackCandidate.outcome`、`detect_registration_outcome`/`detect_registration_reject_reasons`、timestamp/measurement-age/covariance/projection covariance 记录、`projection_invalid` 独立断点、自适应像素协方差、默认 3 帧稳定窗口、跨视角配准证据、YOLO/MOT confidence/class/bbox-scale/tracker-backend/CPU-GPU budget metadata 和 mobile recon gimbal evidence；main/D6 已有 P1 sweep 与报告 bundle 消费口径。D5 仍不启动 AirSim、不生成总报告、不使用 AirSim truth ID、不创建/改写/换绑 `global_track_id`。剩余工作集中在真实 AirSim 多 seed 标定、二级覆盖策略、YOLO/MOT 阈值与预算实测、`solvePnP`/外参增强和 BoT-SORT/Deep SORT/ReID 等 P2 评估。
