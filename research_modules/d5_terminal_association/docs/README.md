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
9. `../reports/D5_TRACKLET_GRAPH_TRAINING_READINESS_20260720.md`：正式跨视角图数据训练准入、开发模型和补数要求。
10. `../reports/D5_ACTIVE_VISION_BC_FORMAL_20260720.md`：正式主动视觉行为克隆数据审计、分层指标、校准和 shadow-only 准入结论。
11. `../reports/D5_TRACKLET_GRAPH_CANONICAL_SEED_VIEW_20260721.md`：跨视角图数据共享 seed 只读视图、正式计数和失败关闭门。
12. `../reports/D5_ACTIVE_VISION_CANONICAL_SEED_VIEW_20260721.md`：主动视觉共享 seed 只读视图、正式样本计数和 shadow-only 边界。

2026-07-26，scalable 3D 在线入口增加有界跨调用活跃相机快照。异步相机可在双时间戳、外参、
missed-frame 和 TTL 合法时进入同一关联图；快照保持匿名、协方差和中心 ID 只读边界。单元
fixture 已形成 `2 nodes / 1 edge`。5v5 seed 1000 短复跑累计节点由 6 增至 8，但在线 6 条
观测经离线 sidecar 核验均为 `known_false_alarm/truth_entity_id=null`，因此零边只证明虚警
失败关闭，不能评价真实目标几何门或 G1 收益。D6 对既有 G1 v4 的 post-assembly audit 只证明
装配完整性；当前源码摘要变化后，旧 v4 严格加载失败关闭，规则路径继续默认。详细状态见
`ALGORITHM_AND_IMPLEMENTATION.md`、`EXPERIMENT_REPORT.md` 和模块 `PLAN.md`。

2026-07-21，确定性主动视觉规则新增默认 3 帧的宽视场稳定门。状态按相机、中心目标、计划版本和
联盟版本隔离；计划/目标变化、时间或证据回退、歧义、通信异常、友方冲突和相机忙都会清除计数。
该阶段只有模块规则测试，未运行 AirSim 或模型训练，也没有运行时 ACK 输入。详细原理、实现和测试
分别见 `MODULE_PRINCIPLES_CN.md`、`ALGORITHM_AND_IMPLEMENTATION.md` 和 `EXPERIMENT_REPORT.md`。

2026-07-21，D5 已为两类正式学习数据建立 detached canonical seed view。两类数据都使用共享
`60/20/20` 数值 seed，保留 seed `1000-1019` 泄漏为 0，原 manifest 与源文件树未修改。图数据
readiness 因 97.52% 无边和困难负边不足继续失败关闭；主动视觉因 hold/observe 覆盖、运行 ACK 和
reward 归因不足继续只允许 shadow。该更新不改变 AirSim 或在线末端关联接口。

2026-07-20，D5 已在完整正式 train split 上完成主动视觉行为克隆。900 个 episode、1,153,242 个
样本通过整 seed 分割审计；开发模型 test 精确动作准确率为 95.60%，但 observe_target 召回为 0、
hold 无正样本、recon 精确动作准确率为 62.18%。bundle v5 仅允许 shadow，assist/PPO 均关闭。
权重只位于 ignored outputs；可跟踪结果为 `../results/active_vision_bc_formal_20260720.json` 和
`../results/active_vision_bc_calibration_20260720.json`。

2026-07-20，main 已完成正式 900 episode。D5 对 12851 个图帧完成逐文件哈希、整 seed 分割和
训练准入审计。97.52% 图帧无候选边，train/validation/test 负边仅 `11/4/4`，因此 G1/assist
继续失败关闭。固定 seed 开发模型只用于管线验证，权重仅保存在 ignored outputs；可跟踪摘要为
`../results/tracklet_graph_training_readiness_20260720.json`。

2026-07-20 active-vision staging 专项的复现入口为
`../simulations/profile_active_vision_episode_staging.py`，对照 JSON 和 cProfile 文本位于
`../results/active_vision_staging_profile_*`。该专项保持 gzip level 6 和磁盘 schema，关闭 D5-owned
共享 snapshot 重复审计/编码热点。main 已在提交
`45b36500dc3c6935b1f116614993e291041eb12d` 上完成同配置 clean-tree 三 seed postopt2 复跑：
D5 active-vision staging 从 `41.5623/43.2639/41.2271 s` 降至
`4.0494/3.9898/3.9995 s`，writer P1 的系统级复跑项已关闭。该段是 2026-07-20 的历史状态；正式
900 episode 已于下一阶段完成，但图数据训练和 assist 准入因监督覆盖不足仍未通过。离线写入结果
不代表在线实时性。

2026-07-20 新增匿名稀疏 tracklet 图文档：实现入口为
`../src/d5_terminal_association/sparse_tracklet_graph.py`、`tracklet_gnn.py` 和
`active_vision.py`；原理、算法、AirSim 待接线和代码级实验分别同步在
`MODULE_PRINCIPLES_CN.md`、`ALGORITHM_AND_IMPLEMENTATION.md`、
`AIRSIM_INTEGRATION_PLAN.md` 与 `EXPERIMENT_REPORT.md`。2026-07-20 小样本训练仅为 smoke；
2026-07-20 已生成 development-only 图模型，但没有已验收 G1/assist checkpoint 或学习型主动视觉
策略。2026-07-20 P0 复审后，构造器与递归
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
