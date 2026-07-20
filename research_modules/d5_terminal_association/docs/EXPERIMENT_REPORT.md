# D5 末端视觉配准与身份认证实验报告

## 2026-07-20 主动视觉与 source-observation 代码级实验

本节仅记录确定性单元/训练 smoke。没有运行 AirSim、没有真实云台动作、没有正式 checkpoint，
也没有形成可用于 assist 准入的 paired report。

| 实验 | 样本/注入 | 实测 | 接受阈值 | 判定 |
| --- | --- | --- | --- | --- |
| v1 snapshot/action 与规则基线 | 1/3/6 相机、不同 assignment 目标子集 | 按输入规模生成 observe 或 scan/hold；输出 ID 始终来自中心候选 | 无 truth/control/assignment 输出；ID rewrite=0 | 通过 |
| safety fail-closed | 缺候选、旧 plan、云台限位、FOV、友方冲突、stale evidence、action timeout、低置信、OOD、NaN、慢推理 | 全部保留规则动作并给出稳定 fallback reason；shadow effective=rule | 任一无效学习动作执行数=0 | 通过 |
| BC/PPO smoke | 8 个合成 `(scenario_version, seed)` group；BC/PPO 各 1 epoch | 整 group 进入唯一 split；loss 均有限；原生 PyTorch actor-critic 可前后向 | seed 跨 split=0；非有限 loss=0 | 管线通过，不是策略质量证据 |
| bundle | 临时 state_dict；SHA tamper、schema mismatch、OOD | weights-only round-trip 通过；篡改/schema 全拒绝；OOD 返回 unavailable proposal | 错误制品执行数=0 | 通过 |
| paired admission gate | 20-seed 合同 fixture；含 synthetic 标志反例 | 正向合同分支要求 20 unseen/non-degrading；synthetic fixture 明确 `assist_admitted=false` | 合成证据正式准入数=0 | 门控通过，不是正式准入 |
| source observation join | 两 detection/同帧、重复 observation、无 label 假目标 | source key 一对一导出；重复在 tracker 更新前拒绝；假目标令 labels incomplete | source key 不等于 local/global ID；补造 truth=0 | 通过 |
| 主动视觉专项 | 17 项参数化测试 | `17 passed in 3.79s` | 零失败 | 通过 |
| D5 全量回归 | 全部 D5 tests | `376 passed in 9.94s` | 零失败 | 通过 |

模型只对有限 camera action 候选评分，不能输出飞控/D3 assignment/global ID。bundle/admission
报告绑定 model fingerprint、dataset manifest、split 和 training-set SHA。正式 assist 仍需至少
20 个完全未见 seed 的真实/代表性 paired shadow 数据，并证明逐 episode/总体 safety、visibility、
reacquisition delay 非退化。当前上述证据全部缺失，因此 library 默认 disabled、CLI 默认 shadow，
规则观察策略不变。

`source_observation_id` 是在线 truth-free 审计键。离线 join 后的 `truth_entity_id` 只存在于
evaluator label，不进入 tracklet graph feature、主动视觉 snapshot 或在线 binding。

## 2026-07-20 训练与模型制品代码级实验

本轮没有运行 AirSim，也没有使用正式图像数据。全部新增实验为 D5-owned 确定性合成图和
`tmp_path` 临时制品，接受阈值均为零测试失败、truth 不进入 graph/online scorer、输出
`global_track_id` 不变。结果只验收软件管线，不验收模型质量或默认准入。

| 实验 | 样本/故障注入 | 实测 | 接受阈值 | 判定 |
| --- | --- | --- | --- | --- |
| 整 episode split | 4 个 `(scenario_version, seed)` group，其中一个 seed 含 2 个 episode | 同 group 全部进入同一 split；train/validation/test 均非空；manifest 明确 edge random split=false | 同 seed 跨 split 为 0 | 通过 |
| graph/label 分流 | 3 相机、2 匿名 tracklet/相机、12 candidate edges | graph NPZ 无 truth 字段、无 `shared_global_track_ids`、无 `ENTITY-*`；truth 只在 label JSON | graph truth occurrence=0 | 通过 |
| 正式训练到评估 | 5 个 synthetic seed group；2 epoch；多图累积；validation calibration | 生成并严格回载 manifest/state_dict/SHA256；test 报告 10 类必需指标字段；admission=`research_candidate_not_default` | 训练/校准只读 train/validation；test 不调参；bundle 可回载 | 管线通过，不是质量准入 |
| bundle fail-closed | 权重追加损坏；graph/model/edge-feature version 和 node feature order 共 4 类 manifest mismatch | SHA 损坏及 4 类版本/顺序错误全部拒绝；runtime wrapper 标记 unavailable | 5/5 拒绝 | 通过 |
| 在线安全回退 | 3 相机、1 中心目标；无模型、缺 bundle、NaN 概率、5 ms 慢模型/0.1 ms 门 | 分别记录 missing/unavailable/invalid-output/timeout，并全部使用 deterministic geometry rule | 不使用无效模型结果；中心 ID 不变 | 通过 |
| D5 新管线专项 | 12 项测试 | `12 passed` | 零失败 | 通过 |
| 稀疏图/adapter/新管线组合 | 46 项测试 | `46 passed` | 零失败 | 通过 |
| D5 全量回归 | 全部 D5 tests | `355 passed in 9.48s` | 零失败 | 通过 |

数据 manifest 现可记录 graph schema、node/edge feature names/version、generation config
SHA256、candidate-recall availability、class balance、hard-negative provenance、split hash 和
training-set hash。加载使用 `allow_pickle=False`，bundle 使用
`torch.load(weights_only=True)`。test 指标实现 precision/recall/F1、false-merge rate、candidate
recall、Brier/ECE、P50/P95 inference latency 和 model size；不完整 truth fixture 验证这些
身份/校准指标均为 unavailable/null，而不是 0。

checkpoint round-trip 只证明 state_dict、temperature 和 threshold 可一致恢复；测试生成的
bundle 已随 `tmp_path` 清理，仓库没有新增正式 checkpoint。至少 20 个未见 seed 的独立 test、
代表性近邻交叉/遮挡/时延/外参漂移、冻结质量/时延门限和默认 checkpoint 均未执行或批准。
因此本轮只关闭训练/制品管线 GAP，几何规则继续默认。

该训练制品阶段没有 settings、相机、detector、runtime episode、云台或 handoff 接线变化。
本轮新增主动视觉/source-observation 合同后，`docs/AIRSIM_INTEGRATION_PLAN.md` 已同步未来接线
边界；仍没有新增 AirSim 实验结论。

## 2026-07-20 稀疏图代码级实验

本轮未运行 AirSim。几何样本由 `scalable_3d_simulation.camera_projection` 的 NED 针孔投影和
协方差合同生成，节点只使用匿名 local ID；中心 ID 只作为只读投影/binding 输入，离线
truth 仅在图构建后生成训练边标签。

| 实验 | 样本与 seed | 实测 | 接受阈值 | 判定 |
| --- | --- | --- | --- | --- |
| 200 目标稀疏压力 | seed 200；200 目标；4 相机；800 节点 | 240000 可能跨相机 pair；索引后 tracklet 候选 3050；中心投影门/最终 cap 前 2953；最终 1923 边；密度 0.006017；最大度 6；本次 0.442 s | 密度 `<0.01`；最大度 `<=6`；中心投影候选 `<2%`；`<15 s` | 代码门通过 |
| 相机规模结构矩阵 | 5/20/50/100/200 相机；每相机 1 tracklet；预算 `2C` | 200 相机总对 19900；检查/保留 400；预算丢弃 19500；tracklet 候选 397；全部相机有候选覆盖；本次约 59.2 ms | 检查数不超过预算；每节点候选度 `<=4`；顺序确定；预算不足不猜身份；不设窄时延门 | 结构门通过，不是 episode 性能验收 |
| 原生 PyTorch 训练 smoke | seed 4；8 目标；3 相机；24 节点；192 边 | 24 正边；72 困难负边；正类权重 3.0；60 epoch loss `1.038521 -> 0.011535`；训练准确率 1.0；2.594 s | loss 降低至少 50%；训练准确率 `>=0.90`；困难负样本非空 | 训练管线通过，不是模型准入 |
| scalable DTO adapter | 17 个确定性 case；2/3/4 相机；3 个中心目标 | `17 passed in 2.27s`；部分可见均绑定 3 个输入中心 ID；7 类污染全拒绝 | 零失败；污染后首 ID 仍为 `trk-000001`；中心 ID 不变 | 模块入口通过，不是 episode 验收 |
| D5 回归 | 全量测试 | 训练/制品同步后 `355 passed in 9.48s` | 零失败 | 通过 |

几何专项另验证了三相机/三目标正确边、全部要求的边特征、逐级 gate count、同相机互斥聚类、
Hungarian 只回显中心 ID、递归 truth/actor/object/global identity 拒绝、原生 `index_add_`
前向及四类主动视觉动作。P0 复审新增构造与嵌套 payload 回归，确认 `TGT-0001`、
`TargetDrone_1` 及同类 truth-like local ID 失败关闭，`cam01-track-0001` 不被误伤。超时、
低置信或无效中心 binding 均回退规则扫描。
新增样本共 12 个参数化 case：5 个构造拒绝、3 个递归嵌套拒绝、4 个正常 local-ID 正例；
接受门为 truth-like case 全部拒绝且正常 case 全部构造/递归通过，实测 12/12 满足。

adapter 专项另覆盖跨帧角速度/尺度变化、中心与 bbox covariance、per-camera 重名 namespace、
假目标消失、单帧空扫描恢复、episode reset、六维中心航迹 copy isolation、无模型/低 certainty/
有效注入模型三种 scoring provenance，以及真实 scalable DTO 类形状。当前 DTO 类形状测试没有
运行 world/orchestrator；其 pose covariance 缺失路径按合同记录 configured fallback。

相机索引专项另验证了重叠/非重叠视锥、相机量测时间窗、预算截断、输入顺序确定性、公平
覆盖、tracklet 候选度上限、预算耗尽后的 unbound、递归 truth 拒绝和中心 ID 不变。构图不再
枚举完整相机对，也不再形成每相机对 `n_left x n_right` 矩阵。诊断字段记录总相机对、空间
索引 pair space、检查/保留/预算丢弃、tracklet 候选、几何拒绝原因和模型/规则路径。

该结构结果不代表真实 200 路图像已达实时。真实 checkpoint、跨场景候选召回、内存峰值、
多随机种子 P50/P95 和跨视角准确率仍需 main/D6 运行集成 episode 后确认。

训练 smoke 使用同一小样本拟合和评估，预期可过拟合，不能提供泛化、IDF1/IDSW、真实遮挡
恢复或 200v200 episode 准确率证据。独立 split、概率校准和 test 指标的软件管线现已实现，
但没有 20 个未见 seed 的正式结果或默认 checkpoint；D5 DTO adapter 已实现，
main scalable module stack 已调用该 adapter，但新增诊断尚未持久化到 episode/D6；也无真实
大规模 AirSim 云台闭环或学习型
主动视觉策略验收，因此既有几何默认路径不变。

## 2026-07-16 真实 AirSim ComputerVision 5+1 专项报告

样本为单个 seed（seed 7）的两个 reset-separated episode，每个 12 秒、49 帧。
场景包含 5 个 `1920x1080`/60 度局部相机、1 个 `3840x2160`/75 度侦察相机和
5 个 `Quadrotor1` actor。注册按每个相机 batch 的 `measurement_timestamp` 投影；
该隔离专项没有运行 D1/D2，main 使用 actor truth 运动学合成带中心
`global_track_id` 的 `GlobalTrack` fixture，truth 同时用于离线评分。
`online_truth_identity_use=0` 仅表示 D5 的 local bbox 到 fixture 关联代价、
Hungarian 选择和稳定窗口不读取 actor/object/truth identity，不表示整个专项完全
不读取 truth。
原始报告和两份指标 JSON 位于
`research_modules/airsim_runtime/outputs/d5_cv_5v5_multicamera_formal_20260716/`。

| 主检测后端 | 召回 | 配准准确率 | 严格准确率 | 稳定配准率 | 联合覆盖 | 侦察全覆盖 | IDSW |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| AirSim detect | 1.000 | 1.000 | 1.000 | 0.975 | 1.000 | 0.918 | 0 |
| YOLOv8 + ByteTrack | 0.622 | 0.996 | 0.966 | 0.955 | 1.000 | 0.878 | 25 |

YOLO+ByteTrack 的 P50/P95 约为 `10.42/12.37 ms`；两路 online truth use 和
`global_track_id` rewrite 均为 `0`。

门限为 detect/YOLO 召回 `>=0.95/>=0.90`、严格配准 `>=0.95`、稳定配准
`>=0.90`、联合覆盖 `>=0.95`、侦察全覆盖 `>=0.90`、IDSW `<=0/<=5`，
truth use/rewrite=0。detect 几何基线全部通过；YOLO+ByteTrack 仅配准、稳定与
联合覆盖通过，因召回、侦察全覆盖和 IDSW 未通过而保持 optional。剩余实验缺口是
召回、IDSW、侦察全覆盖及多 seed；单 seed 不构成主线晋级或总体完成证据。
该专项分支不替换默认 D1-D7 流程，也不形成物理拦截结论。

## 2026-07-16 人工轨迹局部观测合同复核

本次不重新运行 tracker，也不启动 AirSim。输入为 2026-07-15
`b.mp4` 五目标实验已生成的 95 帧、475 条 `ManualTrackFrameRecord` 等价记录；
image size 为 `640x496`，local ID 数为 5，identity audit 的重复量测为 0。

调用 `manual_records_to_local_image_observations()` 后得到：

| 输出状态 | 数量 | 合同判读 |
| --- | ---: | --- |
| measured | 470 | center、`xyxy`、`2x2` 自适应像素协方差、双时间戳可用 |
| lost | 5 | center/bbox/covariance 为空，confidence 为 0 |
| 总计 | 475 | 与 `95 frames x 5 local IDs` 一致 |

确定性测试另使用 infrared、非零 arrival delay 和 measured-lost-recovered 序列验证：
双时间戳保持顺序，`xywh` 正确转为 `xyxy`，连续 measured history 在 lost 后重置；
重复框/中心坍缩输入在生成任何观测前被 identity audit 拒绝。根包导入测试屏蔽
OpenCV/SciPy，确认不加载 `manual_video_tracker`，从而保持离线依赖边界。

验证日期为 2026-07-16；真实记录样本为 1 个视频、95 帧、5 个 local ID、
475 条记录，确定性边界用例覆盖 visible/infrared、协方差、双时间戳、lost、
duplicate 和 import boundary；D5 全量 `288 passed`。接受阈值为零测试失败、
重复量测必须 fail closed、lost 不得携带 stale 量测。剩余限制为人工初始化、
单相机和离线转换；本结果不代表默认 AirSim、跨视角身份或 D7 控制接入。

## 2026-07-15 `b.mp4` 人工五目标 local MOT

输入视频为 `496x640`、5 FPS、95 帧。五个目标用 `12x12` ROI 按顺序初始化。纯 CSRT 12/16 像素框分别在第 38/28 帧出现中心/框塌缩，尽管 summary 显示 95/95 measured；KCF 仅保持 2-3 帧。因此 tracker success 不作为身份连续验收。

人工 ROI 为：

```text
367,275,12,12; 386,262,12,12; 405,268,12,12;
431,260,12,12; 451,260,12,12
```

选择顺序固定生成 `local-001...local-005`。实验没有读取视频真值身份，也没有使用 `global_track_id`。

最终配置为 CSRT proposal + `bright_hungarian`：全帧 `gray - GaussianBlur(31x31)`、阈值 12、常速度预测、Hungarian 一对一关联和 20 像素门。五 ID 有效/丢失为 `92/3`、`95/0`、`93/2`、`95/0`、`95/0`；`duplicate_measurement_count=0`、重复帧 0、最小中心间距 5 px、最大 bbox IoU 0.4118。contact sheet 复核 frame 0/20/40/60/80/94 未发现 ID 同帧共享同一量测。

### 对照结果

| 配置 | tracker success 表象 | 身份连续性复核 | 判定 |
| --- | --- | --- | --- |
| CSRT，16 px ROI | 五 ID 均 `95/95 measured` | 第 28 帧起出现完全重叠，末端多 ID 收敛到同一亮点 | 假连续性，不验收 |
| CSRT，12 px ROI | 五 ID 均 `95/95 measured` | 第 38 帧 `local-002/local-003=(208,286)`；后续 `local-001/002/003` 继续塌缩 | 假连续性，不验收 |
| KCF，12 px ROI | 每 ID 仅 2-3 帧 measured | 不能维持本视频目标 | 失败对照 |
| CSRT + `bright_hungarian` | 允许显式 lost | 重复量测 0，短时 lost 后恢复原 ID | 本视频通过 |

### 五轨迹结果

| 本地 ID | measured | lost | lost 帧 | 最终状态 |
| --- | ---: | ---: | --- | --- |
| `local-001` | 92 | 3 | 57, 58, 89 | measured |
| `local-002` | 95 | 0 | 无 | measured |
| `local-003` | 93 | 2 | 34, 35 | measured |
| `local-004` | 95 | 0 | 无 | measured |
| `local-005` | 95 | 0 | 无 | measured |

本实验的接受条件不是“五条 tracker 都返回 true”，而是 95 帧处理完成、lost 不伪造量测、`duplicate_measurement_count=0`，并由 contact sheet 确认六个抽样时刻没有同帧共享量测。最终 MP4 为 95 帧，逐帧 CSV 为 `95x5=475` 行。

本实验只证明该亮目标视频中的人工初始化 local ID 可区分，不证明通用无人机检测/MOT、GlobalTrack 注册、敌我识别、跨相机关联或 D7 视觉控制准入。完整报告见 `../reports/D5_MANUAL_VIDEO_TRACKING_B_20260715.md`。

验证日期为 2026-07-15，样本为 1 个真实视频、95 帧、5 个 ID、475 条逐帧记录；D5 全量 `284 passed`，零测试失败，语法与格式检查通过。

## 2026-07-15 真实 AirSim M5N2 20-case 复核

### 范围与数据

本节只使用以下 20 个已完成目录：

- `p1_terminal_timing_funnel_10seed_20260715_m5n2_baseline_seed001-010`
- `p1_terminal_timing_funnel_10seed_20260715_m5n2_candidate_soft_prediction_trend_coast_seed001-010`

场景为 M5N2、SimpleFlight、T001 两个 active primary 加一个 standby reserve、T002 一个 primary，默认检测为 AirSim detect。main 在 M5N2 完成后发出 TERM；TERM 生效前额外完整生成一个 `png_ttc_2v2_seed001` 的 `intercept_summary.json`，其余 tuned case 与 dropout case 均未执行。该额外 case 不进入本节 M5N2 的 `3725` 条记录、漏斗、距离或成功率统计，本节也不向 tuned/dropout 外推。每场第二 primary 按 M5N2 `intercept_summary.json` 的 current active primary 资源 ID 排序确定。baseline 10 场及 candidate 9 场的第二 primary 为 `INT-03`，candidate seed 002 为 `INT-02`。truth ID/state 仅用于离线 5 m 评分，不进入在线 D5。

20 个第二 primary 最终都记录为 `collision_stop`。这是 D7 控制循环的停控证据，不是 D5 失败分类；由于 artifact 没有持久化碰撞对象，当前无法区分成员碰撞、环境碰撞或 AirSim 状态问题，不能据此把第二 primary `0/20` 单独归因于 D5。

### 可用性

| 证据 | 可用性 | 说明 |
|---|---:|---|
| case 目录与 actual-execution artifact | `20/20` | 全部真实 AirSim case 已完成 |
| main tick | `3805` | 每场前 4 tick 为 D5 warmup/not applicable |
| D5 适用 tick 与第二 primary runtime record | `3725/3725` | decision 与 live funnel 同步存在 |
| `first_failure_stage/reason` | `3725/3725` | 逐 tick 原始持久化字段 |
| measurement age | `3724/3725` | 1 条缺失，不补零 |
| 直接 `failure_category` envelope | `0/3725` | 本批未持久化，不能虚构分类可用性 |
| 第二 primary 5 m 物理证据 | `20/20` | 由离线 truth-distance scorer 生成 |
| online identity/state truth use | `0/0` | D5 runtime 与 actual execution 均无在线使用 |

### 决策状态与首断点

| profile | second-primary tick | locked | ambiguous | reacquire | hold | bbox stable / handoff ready | strict complete |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline | 1869 | 879 (47.03%) | 403 (21.56%) | 587 (31.41%) | 0 | 58 (3.10%) | 21 (1.12%) |
| candidate | 1856 | 842 (45.37%) | 392 (21.12%) | 622 (33.51%) | 0 | 103 (5.55%) | 31 (1.67%) |
| 合计 | 3725 | 1721 (46.20%) | 795 (21.34%) | 1209 (32.46%) | 0 | 161 (4.32%) | 52 (1.40%) |

`hold=0` 只表示这 20 场没有形成 friend/duplicate/assignment-ID hard conflict，不证明 hold 路径不需要。candidate 的稳定框/交接快照较多，但 locked 比例下降、reacquire 比例上升，不能视为一致改善。

| `first_failure_stage` | baseline | candidate | 合计 | 合计占比 |
|---|---:|---:|---:|---:|
| `bbox_stability` | 677 | 606 | 1283 | 34.44% |
| `live_detection` | 587 | 622 | 1209 | 32.46% |
| `visual_association` | 392 | 372 | 764 | 20.51% |
| `measured_stable_lock` | 109 | 104 | 213 | 5.72% |
| `geometry_gate` | 83 | 121 | 204 | 5.48% |
| `complete` | 21 | 31 | 52 | 1.40% |

主要原始原因是 `bbox_area_unstable_or_too_small=1197`、`terminal_visual_evidence_expired=1068` 和 `insufficient_best_second_margin=683`。另有 `reacquired_assigned_track_in_search_window=173`，它表示受控搜索窗口内重获取，不应与 hard contract conflict 混写。实际 active second primary 的 assignment/global-ID、friend、duplicate conflict 均为 0，bbox edge clipping 为 0，projection valid 为 `3725/3725`。

### bbox、几何和时间

- 当前 measured bbox 为 `2516/3725 (67.54%)`，bbox stable/handoff-ready 仅 `161/3725 (4.32%)`。
- projection valid 为 `100%`，正常 `geometry_gate_accepted` 为 `2312/3725 (62.07%)`。因此问题不是相机投影完全失效，而是候选门内唯一性与重获取阶段的几何连续性不足。
- `visual_evidence_fresh=2657/3725 (71.33%)`；measurement age 均值约 `0.672 s`、P95 `3.4 s`、最大 `12.5 s`。`timing_gate_pass=3725/3725` 属于另一层合同字段，不能抵消 `terminal_visual_evidence_expired`。
- coalition visual consensus 出现 `494/3725 (13.26%)` 个快照，但它是过程状态，不等于两个 primary 均完成 5 m 物理拦截。

### 物理关联与结论

| profile | second-primary 5 m | 最近物理距离均值 | 范围 | T001 coalition completion |
|---|---:|---:|---:|---:|
| baseline | 0/10 | 12.736 m | 8.873-14.740 m | 0/10 |
| candidate | 0/10 | 12.573 m | 8.843-14.309 m | 0/10 |
| 合计 | 0/20 | 12.654 m | 8.843-14.740 m | 0/20 |

当前能力已经完成 runtime record、动态成员识别、逐 tick 决策/首断点、truth 隔离和物理结果可用性；没有闭合第二 primary 5 m、联盟物理完成、稳定 bbox/交接比例和 direct failure-category artifact。soft prediction/trend coast 在本批未带来物理收益，不晋级默认路径。candidate seed 002 的 primary membership 与 baseline 不同，后续 paired 比较必须冻结成员或显式分层，不能把全部差异只归因于 D7 profile。

## 2026-07-15 第二 primary 被动诊断回归

本批是确定性代码回归，不是新 AirSim episode。输入构造两个 active primary，并分别注入：无当前检测、投影出界、几何门拒绝、bbox 边缘裁切/稳定性失败、多候选歧义、量测过期、错误 assigned-global-ID、友方重叠、重复锁定风险、单帧稳定性不足，以及双帧完整成功。

结果为 11 个专项 case 全通过，D5 全量 `272 passed`，接受阈值为零失败。`failure_category_counts` 和 `second_primary_failure_category_counts` 能区分上述断点；错误 global ID 的输出仍保持 binding `G1`，online truth use 与 global ID rewrite 均为 0。测试没有放宽 locked/hold/reacquire、安全门或阈值。

局限性：本批 seed 数为 0，没有新增相机图像、检测率、延迟、5 m 物理拦截或联盟完成证据。真实 2v2/M5N2 至少 10 seeds 的类别比例、第二 primary 主失败原因和 unknown/other 占比仍需 main 调度后由 D6 汇总。

## 2026-07-14 actual-v2 真实 AirSim 执行证据

本节同步两次已完成的真实 AirSim seed-1 运行，不是 D5 新实验或代码变更。两次均使用默认 AirSim detect，不保存相机 PNG；canonical actual-execution artifact 为 `2/2` available，identity/state online truth use 均为 `0/0`。

| case | 时长/导引 | terminal lock | visual control | visual / mode switch | 5 m 物理结果 |
|---|---|---:|---:|---:|---|
| tuned 2v2 seed-1 | 8 s / `png_ttc` | 3 | 26 | 2 / 2 | pair `2/2`，target `2/2` |
| M5N2 seed-1 | 35 s / `png_vm` | 24 | 0 | 0 / 0 | pair `2/3`，target `2/2`，coalition `0/1` |

M5N2 高威胁 T001 的第二 primary 最近约 `11.02 m`，standby reserve 未越权。`terminal_lock_count=24` 只统计 resource-target lock acquisition transition，不能解释为 24 个视觉控制样本；相反，visual control、visual switch 和 mode switch 的 canonical 持久化值均为 0。canonical `terminal_switch_allowed_count` 已从最终 `control_commands.csv` 独立统计，2v2/M5N2 为 `26/0`，不由 control 层回填。五层 contract/control/terminal-switch/mode/physical 总计 `102/26/26/2/4`，均为 available；target `2/2` 也不能替代 coalition `0/1`。

验收日期为 2026-07-14，共 2 个 case，每个 case 只有 seed 1。P0 actual artifact 与五层 schema 可用性通过，但统一 D6 formal overall status=`fail`；未达到完整 P1 所需的 baseline/candidate 配对、1-5 帧 dropout 全矩阵和多 seed。D5 当前开放 P1 为 M5N2 第二 primary、真实几何 drift、detect/YOLO/MOT 多 seed 和二级同 tick freshness；IBVS、真实身份源、完整在线 PnP/ROS 2 保持 P2/P3。该边界不改变 D5 默认 detect、online truth 隔离和不改写 `global_track_id` 的约束。

来源：`research_modules/airsim_runtime/outputs/p0_actual_v2_validation_20260714/d6_acceptance/P1_UNIFIED_ACCEPTANCE_REPORT.md`、`subagent_reviews/MAIN_P0_ACTUAL_EXECUTION_AIRSIM_VALIDATION_REPORT_20260714.md` 及其登记的两个 `d7_actual_execution_metrics.json`。

## 2026-07-14 postbatch M5N2 执行语义审计

本节只读复核以下两个既有真实 AirSim seed-1 episode，不是新增运行：

| case | 控制记录 | D5 几何 locked | 控制 bbox 非零 | active pair 退出距离 |
|---|---:|---:|---|---|
| baseline | 330 | 151 | INT-03: 40 | 24.78-28.87 m |
| candidate | 311 | 120 | INT-03: 40 | 23.31-28.55 m |

baseline 中 INT-02/03/04 的 measured detection 分别为 `37/120/48`，最后出现于 `4.4/12.9/5.3 s`；几何 locked 分别为 `32/76/43`。这说明控制 CSV 中其他资源 bbox 为零不是 D5 把同一个 detection 错分到 INT-03，而是这些资源在末端阶段已经没有当前本相机 measured bbox。所有 camera scope 均为对应 `InterceptorN:0`。baseline INT-03 控制 bbox 最大面积比约 `2.4943e-4`，D7 按现有门限拒绝 `bbox_area_too_small`。

candidate 另观察到约 `0.64-0.70` 面积比的单帧异常大框，可形成低置信 raw geometric lock，但未形成稳定可执行 handoff。该现象仍需真实图像/遮挡和 detection source 专项定位。本轮代码修复只使 `execution_lock_allowed` 对 bbox、scope、连续性和稳定性 fail closed，并补全下游 DTO，不声称解决物理可见性。2026-07-14 语法检查通过、D5 全量 `261 passed`，验收阈值为零失败。

## 2026-07-14 semantics_v2 M5N2 seed-1 历史复核

本节复用 `p1_terminal_closure_semantics_v2_seed1_20260714_m5n2_*_seed001` 既有真实 AirSim 产物，不是新 episode。逐帧审计结果如下：

| case | INT-02 measured detect | raw visual lock | final execution lock | T001 consensus | INT-02 bbox 首次稳定 |
|---|---:|---:|---:|---:|---:|
| baseline | 195 | 140 | 18 | 14 | 19.0 s |
| candidate | 193 | 142 | 18 | 14 | 18.6 s |

两组 execution gate 都只有前 `19` 个 tick 通过，即 `0.4-2.2 s`；随后 `arrival_window_expired`。因此 raw visual lock 在后续仍可出现，但不能成为 execution lock。该批旧 control CSV 的 bbox area ratio 全为零，当时作为待查路由现象；顶部 postbatch 证据现已证明 main 可消费当前 local track，其他资源末端 bbox 为零主要来自当前 measured detection 已消失。历史结果仍证明 bbox 达标时刻与旧到达窗口不重叠。

D5 新增 truth-free `d5_live_visual_funnel_v1`、连续 measured-lock streak 和 `d7_handoff_input`。确定性测试覆盖连续锁定、raw lock 被过期 arrival contract 阻断、M-to-N 缺 committed membership 三类场景；新增专项 `3 passed`，该阶段 D5 全量 `258 passed`，接受阈值为零失败。没有降低任何安全门限，没有在线 truth use 或 `global_track_id` rewrite。当前结论和开放项以顶部 postbatch 章节为准。

## 2026-07-14 bbox 稳定历史/共同视觉证据复核

本轮只读分析 postfix seed-1 既有产物，没有启动新 AirSim。M5N2 baseline/candidate 各有 1388 条相关记录，`bbox_stable=true` 均为 0；T001 在 347 个 summary tick 中分别只有 13、12 个 consensus。2v2 PNG/TTC 52 条记录同样为 0 个 stable bbox。全部记录的 `visible_frame_count <= 1`，证明旧 handoff 每 tick 只看到当前 `scoped_local_tracks`，无法形成默认四帧窗口。M5N2 T001 另有 `326/347` tick 的 primary membership transition，属于必须保留的共同证据重置。

D5 确定性回归验证了：同 resource-target-local track-camera-backend-stream 与 committed/current membership 下跨普通 plan version 累积；binding/membership/local/camera/backend/stream、producer reset、predicted/lost、identity/friend/duplicate 变化清空；输出 history length、CV、reset/key/signature/source 和 raw/effective MOT；单 tick handoff 消费 associator 历史；M-to-N 缺 current committed membership 与 YOLO backend 缺字段均 fail closed；共同视觉不使用历史成员。D5 全量结果 `255 passed`，接受阈值为零失败，owned-path `git diff --check` 通过。

结论仅关闭 D5-owned history/contract P1。没有改变 bbox N=4/CV<=0.30、锁定门限、`global_track_id` 或 YOLO/native-MOT admission。后续 canonical actual 已接入 committed coalition、pre-decision duplicate hint 及稳定 camera/stream/backend/local-track transition/MOT 字段，并独立写出五层证据；该 main 接线不再开放。M5N2 第二 primary、几何 drift、30/50 m recall、detect/YOLO/MOT 多 seed 和二级同 tick freshness 继续开放。

## 2026-07-14 原生 MOT 历史专项回归

本批使用模拟 Ultralytics `Results.boxes.xyxy/conf/cls/id` 的连续帧对象验证代码级 P1 修复。场景覆盖 ByteTrack/BoT-SORT、同流同 ID 连续三帧、不同资源和相机隔离、native ID 切换、一个空帧后的恢复、超过 `max_track_age_frames` 的长期消失、stream reset、episode reset，以及 native failure -> IoU fallback -> native reinitialize。

验收要求为：连续实测历史必须从 1 增至 2 及以上；所有新 ID、恢复帧和状态边界必须从 1 开始；空帧保持 native 空结果而不伪造检测；fallback/native 不能共享历史；在线输出不得出现 truth/global ID。结果为专项文件 `41 passed`、D5 全量 `241 passed`，零失败。未降低 `min_mot_history`、友方/duplicate/版本/时间戳/标定 gate。

本节不是 AirSim 实测：本批 seed 数为 0，没有新图像、检测率、IDSW、延迟或物理拦截数据。因此只关闭原生 Results 历史固定为 1 的代码断点，真实 AirSim/真实图像至少 10 seeds 准入仍为 P1。

## 2026-07-14 输出分级回归

本轮是 D5 合同级确定性测试，不是新的 AirSim 物理实验。场景覆盖单机候选 ambiguity、geometry gate reacquire、bbox 时序 hold、verified friend、spoof、association/cross-view duplicate，以及 distributed unknown/unverified identity。专项结果为 `52 passed`，随后当时 D5 全量为 `235 passed`；本日原生 MOT 历史修复后最新全量为 `241 passed`。接受阈值是零失败、普通视觉不确定性不输出 `conflict/report_conflict/arbitrate/resource_unavailable` 语义、hard conflict 必须 fail closed、`global_track_id` rewrite 和 online truth use 均为 0。

结果确认：普通 `ambiguous/hold/reacquire` 仅阻断当前 pair 的 D7 视觉切换，并通过 `observe/request_secondary_cue` 请求继续观测；verified friend、spoof、duplicate 和 assignment/ID conflict 通过 `report_conflict/arbitrate` 允许 hard planner feedback。未知或未验证身份不等于敌方。由于未运行新 AirSim episode，本节不更新既有 seed 数、检测率、物理命中率或资源健康结论；M5N2 第二 primary 稳定 lock、远距检测/native MOT 和外参/时序标定仍是 P1。

## 1. 实验边界

本报告验证保守的末端视觉关联模块。模块只在离线科研仿真中评估“中心分配目标”和“本地视觉轨迹”的对应关系，不包含真实火控参数、毁伤逻辑、实机飞控、硬件驱动、自动处置或绕过人工授权的流程。局部节点严禁自行改写 `global_track_id`。

## 2. 实验目的

D5 解决的问题是：拦截资源末端视场内可能同时出现分配目标、其他目标、友方资源和未知飞行物，相机看到的最近目标不一定是中心分配目标。本轮重点验证：

- 全局航迹能否按当前图像帧时间做常速度预测后投影。
- 局部 MOT 结果能否通过像素马氏门限、角速度一致性和类别线索关联。
- 高空系留二级侦察节点发布的局部图像 cue 能否作为小范围资源的辅助证据。
- 友方正向认证能否触发 `hold`，避免把友方重叠误当作目标。
- 未授权计划、版本不匹配、短历史或低质量 MOT 是否会阻止 `locked`。

## 3. 几何模型

相机采用针孔模型：

```text
p = K [R | t] P_w
u = fx X_c / Z_c + cx
v = fy Y_c / Z_c + cy
```

位置协方差通过投影雅可比传播到像素平面：

```text
Sigma_px = J Sigma_w J^T + Sigma_measurement
```

本地检测与预测投影之间使用二维像素马氏距离门限，默认 `d2 <= 9.21`。

## 4. 决策状态

| 状态 | 含义 |
|---|---|
| `locked` | 唯一匹配、版本一致、已授权、MOT 质量足够、无友方冲突 |
| `ambiguous` | 候选接近、质量不足、身份未验证或代价过高 |
| `hold` | 未授权、版本不匹配、验证友方重叠 |
| `reacquire` | 分配航迹不可见或无本地轨迹通过门限 |

未知身份不等于敌方身份；`ambiguous` 和 `hold` 不得被下游解释为自动授权。

## 5. 多无人机重叠视场配准现状

当前程序已覆盖单机视场内多目标候选、友方 `hold`、二级 cue 作用域和 `global_track_id` 不变式。例如，单机相机中同时存在分配目标、干扰目标、友方目标和未知目标时，D5 通过中心航迹投影、像素马氏门控和候选代价排序选择本地候选，或保守输出 `ambiguous/hold/reacquire`。

当前已实现最小 `TerminalObservationBus`、`CrossViewAssociation` 摘要层，以及完全分布式 metadata-only `TerminalCrossViewFusion` peer evidence。对于“无人机 1 看到目标 1/2/3、无人机 2 看到目标 2/3/4”的场景，单元测试验证了：

- 目标 2/3 可以被汇总为 `("UAV1", "UAV2")` 的多视角支持。
- 目标 1/4 保持单视角支持，不被错误丢弃。
- 相同 `global_track_id` 被多个资源同时 `locked` 时，只输出 `duplicate_terminal_lock_risk=True`，不改变 D3/D4 分配。
- `local_track_id` 在摘要中按 `resource_id/camera_id:local_track_id` 命名空间化，避免不同无人机本地 ID 冲突。
- `TerminalCrossViewFusion` 在 missing/stale `assigned_global_track_id`、重复锁定、友方冲突或 local/global ID 冲突时输出 `hypothesis_only/hold/ambiguous`，不得输出 `locked`。

完整跨无人机多相机三维几何融合尚未实现。后续几何增强仍需要通过以下信息做跨视场关联：

- D2 已有 `global_track_id` 的时间预测。
- 每个无人机相机的 `measurement_timestamp`、相机姿态和内参。
- 全局航迹投影到各相机平面的像素位置与协方差。
- 本地观测的像素协方差、MOT 质量和候选代价。
- 已重投影到目标相机平面的二级侦察 `ReconImageCue`。

建议在当前 `TerminalObservationBus` 和 metadata-only `TerminalCrossViewFusion` 之上继续新增 `CrossViewObservation` 与几何层 `CrossViewTrackEvidence`，只做离线跨视场配准和一致性评估。D5 仍不得创建、改写或换绑 `global_track_id`。

## 6. 面向 D4 主动降级的一致性信号

主动降级需要 D4 判断“末端视觉证据是否仍支持中心或二级节点分配”。D5 侧不做降级决策，但可以提供如下离线信号：

- `decision_state`、`association_confidence`、`ambiguity_score` 和 `friend_conflict_state`。
- 候选代价间隔 `candidate_cost_margin`，用于判断最佳候选是否唯一。
- `recon_cue_used`，用于区分自相机锁定与依赖二级侦察 cue 的锁定。
- `terminal_lock_age_s`，用于衡量连续锁定稳定性。
- 连续 `ambiguous/hold/reacquire` 帧数，用于形成 soft cue/reacquire 请求；不能单独触发 hard 仲裁。

2026-07-07 后，连续帧统计按 `resource_id + assigned_global_track_id` 保持，不把同一 assignment pair 的 D3 `assignment_version` 滚动更新当成新目标。因此 D4 可以看到真实的末端视觉连续性，而不是被计划版本号变化打断。D5 的输出仍是 advisory summary，不触发降级、不生成计划、不改写 `global_track_id`。

推荐判定：

- `locked` 且全局 ID/版本一致：末端一致，不触发主动降级。
- 多帧 `ambiguous`：请求二级节点 cue 或继续观测。
- 已验证友方重叠 `hold`：上报冲突，不自动换绑。
- 多帧 `reacquire`：请求 secondary cue/reacquire，不由 D5 推断资源失效；D1/D2/D3 可依据自身独立风险另行决策。
- 本地最佳视觉候选长期不支持 `assigned_global_track_id`：触发主动仲裁，但 D5 不改写 `global_track_id`。

更完整的字段建议见 `ALGORITHM_AND_IMPLEMENTATION.md` 中的 `TerminalConsistencySummary`。

## 7. 二级侦察节点图像 cue

本阶段假设存在若干高空系留侦察无人机作为二级节点。中心节点正常时，二级节点持续向其覆盖小区内的若干拦截资源发送侦察图像或图像平面 cue。中心节点失效时，D4 可把局部协调权降级到二级节点；二级节点失效后才进入完全无中心协商。

D5 对二级节点图像 cue 的使用原则：

- cue 通过 `ReconImageCue` 表示，包含 `producer_node_id`、`image_frame_id`、`global_track_id`、像素中心、置信度和 `scoped_resource_ids`。
- cue 的像素中心必须已经重投影到当前拦截资源的相机平面；二级侦察相机原始像素不能直接与本地 `LocalVisualTrack.center_px` 比较。
- cue 只对覆盖范围内的资源生效，不在范围内的资源不能使用该 cue 降低代价。
- cue 只能降低候选视觉轨迹的关联代价，不能绕过 `authorization_state`、`assignment_version`、友方验证或 MOT 质量门槛。
- 即便 cue 与本地检测一致，终端模块仍必须输出 `locked/ambiguous/hold/reacquire` 之一，且不得改写 `global_track_id`。
- 建议后续实验记录 `recon_cue_used_count`，并加入 cue 新鲜度、`image_frame_id`/目标相机帧一致性和空 `scoped_resource_ids` 语义的对照测试。

更完整的算法原理、数学模型和接口说明见 `ALGORITHM_AND_IMPLEMENTATION.md`。

## 8. 仿真场景

运行命令：

```bash
python3 research_modules/d5_terminal_association/simulations/run_terminal_association_sim.py --frames 120 --seed 7
```

覆盖内容：

- 一个中心分配目标 `G_ASSIGNED`。
- 一个非分配干扰目标。
- 一个带模拟 OpenDroneID 友方标签的合作目标。
- 一个未知目标在部分帧靠近分配目标投影，制造歧义。
- 分配目标短时遮挡，触发 `reacquire`。
- 友方目标与分配投影重叠，触发 `hold`。
- 后续扩展：UAV1 看到目标 1/2/3、UAV2 看到目标 2/3/4 的跨视场配准，验证重复本地 ID、相机姿态误差、时间戳错位和二级 cue 重投影。

### 8.1 ComputerVision N-v-N 专项 dry-run

新增 D5-only 单元测试覆盖 AirSim ComputerVision 风格输入，不导入 AirSim、不调用控制 API：

- N-v-N 数量由 main runtime 的 `--drone-count N` 统一控制；D5 按传入的 camera/resource、`LocalVisualTrack[]` 和 `GlobalTrack[]` 长度运行。
- 5v5 只是 stress baseline；当前 baseline 使用 5 个 `Interceptor_Cam_*` 主镜头，每个镜头 3 个检测框，验证 `per_camera_detection_count` 和 `multi_target_fov_rate`。
- 目标距主镜头约 50m，目标间距和镜头间距约 20m 的压测假设由 `AirSimCVScenarioSpec` 作为可调 baseline 保存。
- 二级系留侦察镜头高约 200m，输出已重投影到本地镜头的 `ReconImageCue`。
- UAV1 看到 1/2/3、UAV2 看到 2/3/4，验证 `cross_view_overlap_count` 和 `duplicate_terminal_lock_risk`。
- 在线配准不读取 AirSim detection 的 `object_id`、`actor_name` 或 truth ID；这些字段只允许用于离线 accuracy/mismatch 评估。
- `no_degradation`、`degrade_to_secondary`、`degrade_to_distributed` 三类证据 case 均有测试覆盖。

D5 在该专项中仍只输出 `LocalVisualTrack`、`TerminalAssociation`、`IdentityClaim`、`ReconImageCue`、`TerminalObservationBus` 和 `CrossViewAssociation` 摘要，不生成 `AssignmentPlan`。

## 9. 图表与曲线

### 9.1 末端决策时间线

![D5 末端决策时间线与累计曲线](terminal_decision_timeline.png)

上图第一部分展示每一帧的终端决策状态，第二部分展示 `locked/ambiguous/hold/reacquire` 的累计数量。该图用于分析保守策略是否在遮挡、友方重叠和歧义区域进入 `hold/ambiguous/reacquire`，并向 D4 提供仲裁建议，而不是盲目锁定或由 D5 触发降级。

## 10. 基线结果

| 指标 | 数值 |
|---|---:|
| 正确 locked 次数 | 84 |
| 错误 locked 次数 | 0 |
| ambiguous 次数 | 8 |
| hold 次数 | 19 |
| reacquire 次数 | 9 |
| locked precision | 1.0 |
| 全帧正确 locked 比例 | 0.7 |
| `global_track_id` 改写次数 | 0 |

## 10.1 N-v-N 专项新增指标

| 指标 | 含义 |
|---|---|
| `per_camera_detection_count` | 每个拦截镜头的检测数量 |
| `multi_target_fov_rate` | 视场内至少两个目标的镜头比例 |
| `cross_view_overlap_count` | 同一 `global_track_id` 被多个视角支持的数量 |
| `duplicate_terminal_lock_risk` | 多资源同时锁定同一全局目标的风险信号 |
| `terminal_lock_accuracy` | 带离线真值的 locked 关联正确率 |
| `ambiguous_fov_event_count` | 视场歧义事件数量 |

## 11. 结论

D5 的目标不是最大化锁定次数，而是避免错误绑定和友方冲突。当前实现默认要求 assignment 版本匹配，并在未授权、版本不一致、短 MOT 历史或低质量检测时输出 `hold/ambiguous`。二级侦察节点 cue 可以提升局部关联的可解释性，但不能成为授权或身份确认的替代品。这使 D5 可以作为 D3/D4 分配计划与 D6 终端评估之间的保守安全门。

跨视场摘要层和 metadata-only peer evidence 已作为 P0 能力落地；下一阶段是多相机三维几何融合和 main/D4/D6 消费闭环。无论后续扩展到何种几何层，D5 都只报告关联证据，不改写全局 ID，也不输出处置动作。
