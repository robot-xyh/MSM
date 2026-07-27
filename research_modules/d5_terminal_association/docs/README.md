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

2026-07-27，clean commit `8d5e02ec989259ce3d39e1e4ad6a90dd0d8d5b54` 已完成 D5 G1
正式合成证据闭环。runtime SHA-256 为
`b0708e718b374e5bb52db41c7bd2f994e340a2b009cfd348881a5f9d549baffe`；development manifest
和权重 SHA-256 分别为
`7d459ed855cf74b810fa1f79ed0327efd39eb4be4409451266da3f3a95387ce0` 与
`7fb5db8b6099ca4da5706a3bec53ff7cd634e8bd267c036ce3ee4ee4bf71ca71`。held-out
`20/900/45` 全部通过，precision/recall/F1/candidate recall 均为 1.0，false merge 为 0，
CPU P95 约 0.913 ms。paired-shadow 覆盖 900 帧和 74024 条边，模型 edge/cluster F1 均为
1.0，最高单特征 AUC 为 0.720073；lineage SHA-256 为
`83e105290f3e624f267d92ceaf050d32291bd5bbbabf98580846cd31498b1af1`，记录数和唯一 UID 数均
为 900。

D6 external audit v2 的文件/内容 SHA-256 为
`cbd6c72b2d9e7b78bf3aa36f975e6627250d2bf18de5a0b0ebc2c8f6cf760cd6` /
`334cf662e49c735931019ff358be1894d1358f1b4a5a868759eee41d3d282d15`，结果为 pass。D5 生产
assembler 生成的 v5 manifest SHA-256 为
`b431d066362005868374d038eb93a83b773c03715a53d8a9dfd0da21784f317d`；D6 post-assembly v2
结果为 pass，内容 SHA-256 为
`17dda42d06b4be1d21ff8f1f8baecc320fd49b532be06a9f9f6b304341763e1d`。strict/shadow loader
通过，assist 请求以 `bundle_g1_assist_authority_not_granted` 失败关闭。六项权限全部为
false，在线 G1 未启用。真实相机泛化、中心身份 binding 正确性和物理闭环仍为 unavailable。

2026-07-26，D5 已关闭 v5 paired lineage 的 D5-owned P0。生产 assembler 现在显式接收并冻结
`paired_episode_lineage.jsonl`，逐行校验非空且唯一的 `episode_uid`，并要求正式
`record_count/unique_episode_uid_count=900/900`。v5 manifest、admission report v2、
paired report 和 D6 external audit v2 `candidate.paired_lineage` 必须对同一 lineage SHA 与计数
一致；`SHA256SUMS` 和 strict loader 已覆盖 lineage 实物。当前 runtime SHA 为
`b0708e71...baffe`，D5 全量 `655 passed, 1 warning`。该段是代码和 fixture 阶段记录；正式
重训、外审和 v5 制品状态以上述 2026-07-27 记录为准。

2026-07-26，D5 已完成版本治理修正。新 admitted bundle 为
`d5.tracklet-model-bundle.v5`，admission report 为
`d5.tracklet-g1-admission-report.v2`，权限合同继续使用
`d5.tracklet-g1-authority-contract.v2`。新装配只接受
`d6.d5-g1-external-audit.v2`；结构未变的 input spec 和 consumer contract 分别继续使用各自
v1，三者独立校验。

新合同精确保存六个
运行权限字段，要求全部存在、严格为布尔值且全部为 `false`；旧四字段审计、未知 schema、字段
增删或拼写错误、非布尔和任一授权值均失败关闭。v5 manifest、准入报告和打包的 D6 审计同时绑定
合同版本、审计文件 SHA-256 和内容 SHA-256，公开严格加载器每次重新核验。

证据资格与运行权限已分离。v5 代码状态为 `g1_evidence_eligible_not_authorized`，影子加载与
G1 在线辅助请求采用不同门；六权限关闭时，辅助请求返回
`bundle_g1_assist_authority_not_granted`。该中间 runtime SHA-256 为
`fe116fd5...1c91`，专项测试 `70 passed, 1 warning`，D5 全量
`636 passed, 1 warning`。该段记录 lineage P0 修复前的六权限中间实现；当时未重训、未运行
held-out/paired-shadow、D6 外审或正式 v5 装配。旧 bundle v4、report v1 和 D6 audit v1 均以
专用错误码拒绝，不解释为新版本。

修复前带 `v2` 后缀的 D6 输出目录已通过自身检查，但其中 JSON 顶层 schema 实际是
`d6.d5-g1-external-audit.v1`。其文件 SHA-256 为 `24c8b0cd...9ad7d`，内容
SHA-256 为 `f17acecf...35f`，blocker 为空且六类权限全部关闭。当时的 runtime 正式 assembler
随后以 `d6_authority_fields_mismatch` 拒绝历史 v4 装配：该 audit authority 比冻结 assembler contract 多出
分配权限和故障接管权限字段。没有创建 v4、loader 探针或 post-assembly handoff。规则路径继续
默认。该段为合同修复前失败证据，记录文件保留；该 audit v1 不能用于新 v5。

2026-07-26，main clean commit `64cb865b...2b05` 的 20-seed 几何候选图 R0 覆盖
`2670` 帧、`16842` 节点和 `4658` 边，precision/recall/F1 为
`0.996565/0.999354/0.997958`，hard violation 为 `0`。该结果不包含 G1 模型评分。
随后正式 writer 以冻结输入重训出相同权重，并原生生成绑定该阶段 runtime
`55066382...b8ea` 的 manifest `db908b05...1d14`。该阶段实现下 held-out `20/900/45` 和
paired-shadow 均通过，5 类扰动最低边/簇 F1 为 `1.0`，最高单特征 AUC 为 `0.720073`。
shadow-only registry 与 D6 输入清单已形成；随后通过自身门限的审计文件虽然位于带 `v2`
后缀的目录，其顶层 schema 实际仍为 external audit v1。历史 v4 因当时合同不兼容未生成。
本段所述 external audit v2 与正式 v5 缺口已由 2026-07-27 的当前 runtime 证据闭合。
正式流水线专项 `46 passed`，clean D5 全量 `600 passed, 1 warning`。

2026-07-26，关联图来源合同增加 `association_tracklets` 和冻结
`association_source_links`。当前调用批次继续单独审计，缓存图节点则保留原 observation ID 和
双时间戳；漏链、重链、错命名空间或错时间均失败关闭。adapter 专项 `50 passed`，D5 全量
`600 passed, 1 warning`。main 的 667 条正向观测属于修复前开发证据；正式状态以上述 clean
R0 为准。

2026-07-26，scalable 3D 在线入口增加有界跨调用活跃相机快照。异步相机可在双时间戳、外参、
missed-frame 和 TTL 合法时进入同一关联图；快照保持匿名、协方差和中心 ID 只读边界。单元
fixture 已形成 `2 nodes / 1 edge`。5v5 seed 1000 短复跑累计节点由 6 增至 8，但在线 6 条
观测经离线 sidecar 核验均为 `known_false_alarm/truth_entity_id=null`，因此零边只证明虚警
失败关闭，不能评价真实目标几何门或 G1 收益。D6 对既有 G1 v4 的 post-assembly audit 只证明
装配完整性；当时源码摘要变化后，旧 v4 严格加载失败关闭，规则路径继续默认。详细状态见
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
