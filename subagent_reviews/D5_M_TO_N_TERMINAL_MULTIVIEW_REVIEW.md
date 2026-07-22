# D5 M 对 N 末端多视角配准与协同定位调研

## 2026-07-21 保留集对 M 对 N 的验证范围

正式 held-out profile 以 5、20、50、100 和 200 五个规模标签组织 45 个场景规模单元，并在 20 个
保留 seed 上形成 900 个图帧。当前局部物理混淆窗口仍由四相机、四目标构造，规模字段用于覆盖系统
场景目录和困难因素，并不等同于一次真实 200 相机对 200 目标在线运行。因此，该保留集可检查图
分类器在未见几何和扰动上的边分类与错误合并，不能替代 M 对 N 网络覆盖、候选预算、通信时延和
联盟执行验证。

producer 和 evaluator 已通过 1 seed×2 cell smoke 及 17 项专项测试。正式 900 帧尚未生成，模型
也未在保留集上评分。完成 held-out 后仍需同 seed paired shadow 和真实 M 对 N runtime；在此之前
规则几何关联继续作为默认路径，G1/assist/authority 保持关闭，中心 `global_track_id` 所有权不变。

## 2026-07-21 Composite 训练入口对 M 对 N 的边界

新增训练入口按实际图和候选边数量运行，没有设置 2v2、5v5 或固定相机数。45 个场景规模单元覆盖
5、20、50、100 和 200 规模，但本轮只完成数据预检和软件合同测试，没有得到 M 对 N 模型性能。
后续 D6 cell 报告按已标注候选边数统计分类样本，不能把 episode 数解释为边分类样本数。

即使未来内部 test 通过，M 对 N 运行时覆盖、中心绑定、联盟执行、保留 seed 和同 seed paired
shadow 仍需分别验证。当前没有新权重，G1、assist 和 authority 不变，规则几何路径继续作为默认。

## 2026-07-21 Tracklet 困难样本对 M 对 N 的边界

补充课程按 9 类场景和 5 个规模 cell 组织 100 个独立 seed，实际生成 4,500 个跨视角图帧。课程
内部使用四相机、四物理目标的局部混淆窗口，不把相机数或目标数写死到在线图算法；规模字段用于
与系统 5/20/50/100/200 场景 registry 对齐。245,032 条候选边均经过既有稀疏几何门，其中困难负边
187,740 条，未标注边为 0。该数据补足的是跨视角候选分类监督，不能替代 M 对 N 运行时相机覆盖、
中心绑定、联盟执行或 AirSim 可见性证据。

main 已在 clean commit `79b2550ce2ef407c7cfcc653ce04a80fe2226c06` 上完成同配置复生。组合视图
的数据支持和 `training_readiness` 均 pass，dirty provenance blocker 已关闭。该 pass 只适用于训练
数据；本轮没有训练图模型，不形成 G1/assist 权限，也不改变中心 Hungarian 绑定、同相机互斥或
`global_track_id` 所有权。仍需保留 seed 模型评估和 M 对 N 影子对照，才能讨论在线辅助。

## 2026-07-21 Supplemental BC 全样本审计对 M 对 N 的边界

D5 已对 clean supplemental 100 episode/1200 sample 完成绑定 SHA 的只读全样本审计：canonical
episode/sample 为 `60/20/20`、`720/240/240`，302/302 checksummed 文件、1200/1200 有限特征、
7800 候选行、1200/1200 唯一规则示范均通过，truth/reserved/dirty/违规为 0。审计内容 SHA256 为
`a11b65596a4c416deba6d0cb35dcc0c32342a5bae0481291d43e8de0e26550dd`，来源 commit 为
`13e37286d2996a227924bb1a8e2766e52116a534`；六项 producer 来源 SHA 保持本文下节记录值，正式
900-episode 树保持 43973 files 与
`8ffbe5cf044d121163c8acc3dce1bbd54e14bb6b211b8e1cf440f24c93294fca`。

该结果关闭 supplemental BC 全样本子项，但课程每 episode 仍只有 interceptor/recon 两个角色，不能
替代 M 对 N 的多相机可见性、跨视角关联、真实 ACK/outcome 或模型评估。`400/400/400` 只属 synthetic
故障覆盖；四类离线标签 unavailable，未训练模型或运行 AirSim。main/D6 跨模块准入、M 对 N 真实
runtime、paired shadow 与 PPO/assist/authority 仍开放，规则回退必需。
本轮新增专项 `4 passed in 35.72s`、D5 全量 `486 passed in 119.63s`；这些仍是软件/离线审计回归，
不构成 M 对 N runtime 性能结论。

## 2026-07-21 B1b2 clean evidence 对 M 对 N 的边界

commit `13e37286d2996a227924bb1a8e2766e52116a534` 的 clean supplemental 制品已通过 100/800/1200、canonical `60/20/20` 与 `720/240/240`、truth/reserved/dirty/audit 零违规检查，dataset/view/config/training-registry/shared-registry/summary-content SHA 依次为 `0c474ee1b0bab34a46c2ebce328761983cf2ecc757da30c2d3d2e03a06cd1acf`、`0ab1a4a6bdd439f6c8a74df5059de3c4950791fba35a1b9514942e83779f72a8`、`e93ca6310338be5db4539fac195f5257e28d16a64b78b1a0351bf6aeca01fcee`、`2ab928a476a4430b99326f245222f058bc5be5025158134ba89b01b3dec7815f`、`68608d29d1f733beea87f1faf06464fededb68a9c2972c51c10cd4c2160f032f`、`0577c73810413ced6277e679477422f467cb2db094f1d376e39e4cbb2a3abd65`，正式树前后 SHA 同为 `8ffbe5cf044d121163c8acc3dce1bbd54e14bb6b211b8e1cf440f24c93294fca`。该证据关闭 producer/canonical，后续 supplemental BC 全样本子项也已关闭；它仍不是 M 对 N runtime、真实 ACK 或模型证据。PPO/assist/authority 不变，下一步为 main/D6 跨模块准入审计。

## 2026-07-21 Supplemental curriculum B1b2 对 M 对 N 状态的影响

B1b2 producer 已实现 100 个独立数值 seed、canonical `60/20/20` 和动态 seed 目录治理，但每个课程
episode 按设计只含 interceptor/recon 两个相机角色。它覆盖两角色的四 intent、wide/zoom 和三类
故障 ACK，不是 5/20/50/100/200 相机 M 对 N 可见性、候选预算、跨视角关联或真实执行实验。

实现没有修改 M 对 N adapter、图构造、聚类、中心绑定或 AirSim runtime；`global_track_id` 仍由中心
提供且只读。本次 source-root path guard 和中文报告修正同样不改变 M 对 N 算法或证据。新增专项
`15 passed`、D5 全量 `482 passed in 83.05s` 是软件阶段历史验收；后续 `13e3728` clean 制品已关闭
supplemental producer/canonical evidence，但不构成 M 对 N 模型或 runtime 证据。本轮没有 M 对 N
模型重训、真实 ACK/outcome、reward/counterfactual/causal 或 paired shadow，因此既有 M 对 N 性能
与准入结论不变；supplemental BC 全样本审计已完成，但 main/D6 跨模块准入仍开放，
assist/PPO/authority 继续关闭。

## 2026-07-20 M 对 N 主动视觉行为克隆结果

正式行为克隆覆盖 5v5、20v20、50v50、100v100 和 200v200，算法按输入相机、目标和候选动作数量
运行。完整 train split 685,005 个样本训练 5 epoch，test 各规模精确动作准确率分别为
`0.977165/0.978000/0.972592/0.961015/0.946216`。规模增大时仍保持有限推理开销，但这些数值受
`reacquire` 多数类支配，不能解释为 M 对 N 主动观察已通过。

test 中 `observe_target` 召回为 0，`hold` 无样本，recon 动作准确率为 `0.621823`。v5 bundle 因此
固定为 development shadow-only，assist/PPO/相机命令权均关闭。M 对 N producer 下一轮需要在独立
seed 中增加共同可见、保持观察、侦察节点扫描与重捕获转换，并记录实际 shadow 请求、ACK 和执行后
outcome；不得通过重采样掩盖缺失意图，也不得修改中心 ID 或版本安全门。

## 2026-07-20 M 对 N 多批次接收修复

M 对 N 运行周期会按实际到达队列产生零个、一个或多个同相机 batch。正式数据链在 209 条已完成
进度后，由 `communication_degraded` 200v200 首次触发同流多批次限制。当前适配器按输入数量工作，
先原子预检整个窗口，再以 arrival 主键确定顺序并逐流更新，不设置相机、目标或批次数量上限。

关联图只保留每个相机最后有效状态，历史正常帧仍参与 tracker 推进但不重复占用图节点，OOSM 不
覆盖当前几何。多相机正反输入回归得到相同输出，各 tracker 的 local ID/history 独立。2026-07-20
定向 `31 passed`、D5 全量 `410 passed in 11.68s`。该结果关闭模块代码阻塞；900 episode 和数据
最终化仍需 main 复跑确认。绑定 `c5a9f6d` 的旧 209 条目录只保留为故障证据；main 必须在同时包含
D5 与 runner 修复的新干净提交上，以新输出目录从 sequence 0 重建 900 episode，不得恢复或跨提交
拼接旧数据。

## 2026-07-20 M 对 N 通信乱序处理

200v200 通信退化场景中，不同相机流及同一相机的不同扫描会因链路抖动形成 arrival 顺序与
measurement 顺序不一致。D5 现在按 `(resource_id, camera_id)` 独立维护双高水位，动态 M/N 数量
不影响时序判断。合法 OOSM 被显式计数并禁止回退 camera-local MOT；重复或回退 arrival 失败关闭。

该处理保留每个批次的 measurement/arrival 时间、相机几何、动态相机数量和匿名命名空间，且不把
后到帧绑定到 truth 或中心 ID。修复当时定向 `24 passed`、D5 全量 `403 passed in 9.74s`。main
随后完成首个 45-cell、checkpoint resume，并累计 209 条完成进度，原 OOSM 异常没有复现。正式
M 对 N 数据生成仍因上节多批次问题及 900 episode 未完成而保持开放。

## 2026-07-20 200v200 M 对 N 数据链 clean-tree postopt2 复测

nominal 200v200、2 s、seed 930-932 在提交
`45b36500dc3c6935b1f116614993e291041eb12d` 上完成 clean-tree postopt2 复测。三场均为有限状态，
online truth use=0，D5 graph 均正常最终化。

D5 active-vision staging 从 postopt1 的 `41.5623/43.2639/41.2271 s` 降至
`4.0494/3.9898/3.9995 s`；每场 artifact staging 为 `4.1704/4.1311/4.1357 s`。总 staging
`126.4682→12.4372 s`，总生成 `262.2866→144.5513 s`。该同配置系统证据关闭 writer P1；
gzip/schema/采样/特征/版本/ACK/真值隔离和动态 camera/target/resource 数量合同未改变。

active-vision finalizer 仍因只有 3 个 seed、1 个测试 seed 而以 `insufficient_unseen_test_seeds`
失败关闭。正式 900-episode corpus、20 个未见测试 seed、BC/PPO、checkpoint、paired shadow 和
assist 准入继续开放。该离线写入复测不改变 M 对 N 的成员、到达窗口、执行许可或在线实时性语义。

## 2026-07-20 M 对 N 数据终结开销复核

优化按 episode 和实际 camera 数量工作，不引入 N 的固定上限。非物化审计不再为每个 camera sample
重复扫描共享 snapshot；同一次 finalize 复用一次 stream/offline audit 和实际文件 SHA256，公开
audit 仍独立复核。6-episode 计数中 parse `12/12→6/6`、SHA256 `67→20`；D5 全量
`398 passed in 15.75s`。磁盘 schema、全部训练特征、真值隔离、整 seed 切分及中心 ID 所有权不变。
正式 900-episode M 对 N corpus 的峰值、吞吐和恢复仍需 main 验收；三 seed postopt2 只关闭 writer
系统级热点，不替代正式 corpus 验收。

## 2026-07-20 M 对 N 主动视觉容量与流式数据复核

episode dataset 按实际 camera、target 和 resource 数组工作，不假设 2v2、5v5 或 200v200。
record v2 将同一 cycle 的 snapshot/camera feedback 按 SHA256 key 在 gzip JSONL 中只写一次，sample
保存稳定引用以及规则示范、requested/effective action、三个版本和可选 ACK，不删减证据。offline
reward/outcome/counterfactual/causal label 仍只在 episode 结束后通过
`sample_key + observation_key` 连接，与 online 文件物理分离。

复核确认流式/物化 loader 都拒绝 truth/actor/object identity、未知中心 `global_track_id`、局部换绑、
版本回退、SHA/schema/source identity/label join 错误。finalize 每 episode 执行一次
`materialize=False` 内容审计，并在最终结构复核复用证据；独立 audit 仍逐 episode 重新执行。
两者都不跨 episode 累积 record。lazy dataset 的 episode/BC/PPO iterator 每次只
物化当前 episode；BC 不读 offline label，PPO 对 reward unavailable/null 失败关闭。

完整 `(scenario_version, seed)` group 及共享数值 seed 跨 scenario/scale 原子进入同一 split，test
seed 对 train/validation 未见；唯一 seed 或 unseen seed 不足时拒绝。active learning dataset v2、
episode dataset v3、record/descriptor/sample v2、bundle v4；tracklet dataset/bundle 也为 v2，并
执行同一共享 seed 隔离。snapshot/action/feedback/ACK/offline-label 保持 v1；旧嵌套文件失败关闭。

最终复核确认相对 dataset root 可用，recorded mode/action 不能把模型动作伪装成规则 fallback，且
resource/camera/local tracklet ID 都拒绝 truth-like 命名；这些修正不改变 M 对 N 数量语义或 schema。

main nominal seed 91、2 s 的 5/20/50/100/200v200 总制品约
`0.086/0.295/0.733/1.543/2.884 MB`；200v200 为 `3536` samples、online/offline
`1.064/1.818 MB`、RSS约 `1.04 GB`、online truth=0。D5 数据管线 `14 passed in 20.56s`，全量
`396 passed in 30.02s`；12 episode × 48 camera × 96 track 回归证明 finalize/audit 全量物化调用
为 0。这关闭 M 对 N 数据软件和单 episode 容量阻塞，不等于 900-episode corpus、正式 BC/PPO、
20-unseen-seed 性能或模型准入；D5 本轮未修改 main/runtime。

## 2026-07-20 M 对 N 主动视觉调度研究接口复核

新增主动视觉路径按输入相机数和当前目标子集工作，不写死 2v2/5v5。每个 camera 的 snapshot
只引用中心候选和当前 assignment，模型在 observe/search/hold/reacquire 的有限候选中选择，并
携带安全投影后的 yaw/pitch 与 wide/zoom。规则基线按新鲜可见投影 look-at、短时丢失
reacquire、否则确定性扫描；候选缺失、版本旧、友方冲突、证据过期、云台/FOV 越界、OOD、
低置信、超时或 bundle 错误都不允许学习动作生效。

研究训练与评估软件已覆盖完整 `(scenario_version, seed)` group 与共享 seed 跨场景原子 split、
behavior cloning、原生 PyTorch clipped PPO、weights-only bundle 和 paired shadow。assist 需要
至少 20 个完全未见 seed 的正式
非合成 paired 结果，且 safety、visibility、reacquisition delay 逐 episode 和总体均不退化；
合成 20-seed fixture 不可晋级。库默认 disabled，CLI 默认 shadow，当前没有正式 checkpoint。

多视角数据导出同步增加匿名 `source_observation_id -> tracklet_key` 审计连接，允许 main 在
episode 结束后连接 evaluator-only truth。该键不成为 MOT 身份或 global ID，同一帧只能属于一个
tracklet，假目标缺 label 时完整性为 false。2026-07-20 主动视觉专项 `17 passed`、D5 全量
`376 passed in 9.94s`。这些是接口和失败关闭证据，不是 M 对 N 真实可见性提升、时延改善或
AirSim 云台执行证据。main 随后已完成统一三维 episode 注入、规则相机命令、版本门控、下一帧
应用和 runtime ACK；正式 paired shadow、真实 AirSim 云台和因果收益仍未完成。

## 2026-07-20 多视角图训练制品复核

D5 现已提供版本化 graph/label 分流、完整 `(scenario_version, seed)` episode group split、
多图训练、validation-only temperature/threshold、test 指标和安全 bundle。离线图只保存匿名
在线节点、候选边和固定 feature order；`truth_entity_id` 仅存在于 evaluator label 文件。
manifest 记录 config/split/training-set SHA256、class balance、candidate-recall availability 和
hard-negative provenance。bundle 用 SHA256 校验并只做 `weights_only=True` state_dict 加载。

在线模型仍只给候选边 same-target probability。bundle 缺失/损坏、版本/feature mismatch、
非有限输出、超时或低 certainty 均回退几何规则；同相机唯一约束、中心投影/Hungarian 和
`global_track_id` 所有权不变。2026-07-20 新专项 `12 passed`，D5 全量
`355 passed in 9.48s`；测试 checkpoint 仅生成于 `tmp_path`。

该结果只关闭训练与模型制品代码管线，不关闭多视角模型准入。至少 20 个未见 seed 的整
episode test、遮挡/近邻交叉/时延/外参漂移、冻结阈值、默认 checkpoint 和真实 AirSim 模型
证据继续开放；几何规则仍是默认。该训练制品阶段本身没有 runtime 变化；其后主动视觉规则
合同已接入统一三维 episode，但没有模型准入或真实 AirSim 执行证据。

## 2026-07-20 匿名 tracklet 图多视角实现复核

原调研中“本地 MOT 与跨相机身份分层”和“先几何门控、后关联评分”的建议已形成 D5 代码：
节点是 camera-local tracklet；边由时间、视场、极线、射线交会、重投影、中心航迹投影和
协方差生成；原生 PyTorch 只给出 same-target edge probability。边特征已覆盖时间差、像素
马氏距离、重投影误差、射线最近距离、bbox 尺度/变化、角速度、基线和外参协方差。
P0 复审后，local-ID guard 还会在构造器和递归 payload 中拒绝 `TGT-0001`、
`TargetDrone_1`、`Target_UAV_7`、`intruder-003` 等 truth-like 编号，同时保留
`cam01-track-0001` 等正常 camera-local sequence。

本轮新增的 `scalable_3d_adapter.py` 补齐 D5-owned 在线入口：duck-typed
`OnlineSensorBatch/vision_bbox` 先做整批 truth isolation，再由每 camera namespace 的 tracker
分配匿名 ID；双时间戳、中心/bbox covariance、角速度和尺度率进入 `CameraLocalTracklet`，
相机 metadata 进入 `TrackletCameraGeometry`。六维中心航迹只读复制为投影假设。模型仅可由
调用方注入，缺失、异常或低 certainty 明确回退几何规则，不产生训练完成声明。

最终身份没有交给 GNN。受约束聚类禁止同一相机两个 tracklet 进入同簇，中心 Hungarian
binding 只能引用既有 `global_track_id`；未绑定簇保持 anonymous。训练 truth 来自独立离线
流，在线图构建完成后才生成标签，并选几何相近的异目标边作为困难负样本。

当前候选生成先按相机位姿、截断视锥 AABB、量测时间和三维覆盖桶建立相机索引，再以
`camera_pair_budget` 限制实际相机对检查。入选相机对按中心投影支持或时间近邻生成 tracklet
候选，并在几何门前限制每节点候选度；不再形成全相机对或每相机对全 tracklet 矩阵。预算
耗尽时节点保持 unbound，不允许图模型补猜身份。

seed 200 的 200 目标、4 相机回归从 240000 个跨相机可能 pair 收缩为 3050 个索引后候选、
2953 个最终 cap 前候选和 1923 条边，密度 `0.006017`、最大度 6，本次 `0.442 s`。seed 4
小样本为 24 正边、72
困难负边，60 epoch loss `1.038521 -> 0.011535`、训练准确率 1.0。adapter 专项
保持通过、D5 全量在本轮同步后为 `355 passed`。5/20/50/100/200 相机结构矩阵中，200 相机只检查/保留
400/19900 个相机对，预算丢弃 19500，tracklet 候选 397，全部相机均有候选覆盖。该证据关闭
D5-owned 索引代码缺口，不关闭真实跨视角泛化、模型准入、内存峰值或多 seed P50/P95。

主动视觉已在 camera-intent 环境/策略接口和 timeout/低置信规则扫描 fallback 之外，接通统一
三维 episode 的模拟相机/FOV 命令及 runtime ACK。5v5 `84/84` 和 200v200 seed 17、1.2 s
`1872/1872` applied 只证明单 seed 接口闭环；尚无正式学习策略、真实 AirSim 云台、实机或
物理收益证据。D5 adapter 已能接收 scalable 3D 匿名观测，main scalable module stack 已调用
adapter；独立数据划分、概率校准和算力指标的软件管线现已完成，后续仍需用至少 20 个未见
seed 的 200v200/代表性整
episode 数据覆盖遮挡、交叉和外参漂移；在此之前几何
Hungarian/`TerminalAssociator` 保持默认。

## 2026-07-16 真实 ComputerVision 5+1 多视角复核

独立专项使用 5 个 `1920x1080`/60 度局部相机、1 个 `3840x2160`/75 度侦察相机、
5 个 `Quadrotor1` actor，运行 12 秒、49 帧、seed 7。每个局部相机允许只覆盖目标
子集，D5 按各 camera batch 的 `measurement_timestamp` 投影；侦察相机全视场
证据不能替代局部 measured evidence、创建全局 ID 或触发重分配。

detect 的召回/配准/稳定/联合覆盖/侦察全覆盖/IDSW 为
`1.000/1.000/0.975/1.000/0.918/0`，通过全部门限。YOLOv8 + ByteTrack 为
`0.622/0.996（严格 0.966）/0.955/1.000/0.878/25`，P50/P95 约
`10.42/12.37 ms`；召回、侦察全覆盖和 IDSW 未通过。两路 online truth use 与
`global_track_id` rewrite 均为 0。

本隔离专项没有运行 D1/D2；main 根据 actor truth 运动学合成带中心
`global_track_id` 的 `GlobalTrack` fixture，truth 另用于离线评分。
`online_truth_identity_use=0` 只约束 D5 的 local bbox 到 fixture 关联代价、
Hungarian 选择和稳定窗口不读取 actor/object/truth identity，不能解释为整个专项
完全不读取 truth。

门限为 detect/YOLO 召回 `>=0.95/>=0.90`、严格配准 `>=0.95`、稳定
`>=0.90`、联合覆盖 `>=0.95`、侦察全覆盖 `>=0.90`、IDSW `<=0/<=5`，
truth use/rewrite=0。多视角结论只确认 detect 几何基线；YOLO+ByteTrack 保持
optional，仍缺召回、IDSW、侦察全覆盖及多 seed。单 seed 不支持主线晋级，
专项分支不替换默认 D1-D7 流程或既有 M-to-N 物理完成判据。

## 2026-07-15 M5N2 20-case 多视角复核

main 已完成 baseline/candidate 各 10 seeds 的真实 AirSim M5N2。TERM 生效前额外完整生成一个 `png_ttc_2v2_seed001`，其余 tuned/dropout case 未执行；该额外 case 不进入以下 M5N2 统计。D5 对 current active second primary 的 `3725` 条适用记录复核得到：`locked=1721`、`ambiguous=795`、`reacquire=1209`、`hold=0`；bbox-stability/live-detection/visual-association/geometry/complete 首断点为 `1283/1209/764/204/52`。直接 `failure_category` 未在本批 artifact 中持久化，因此只能报告原始 stage/reason 可用，不能补写分类 envelope。

多视角过程证据并未转化为协同完成。T001 coalition visual consensus 有 `494` 个 tick 快照，但第二 primary 5 m 为 `0/20`，physical coalition completion 为 `0/20`；bbox stable/handoff-ready 只有 `161/3725`。这支持既有边界：peer/cross-view 证据用于关联和仲裁，不能替代每个 active primary 自己的当前 measured bbox 和执行交接合同。

20 个第二 primary 最终均记录为 `collision_stop`。该字段是 D7 停控证据，不是 D5 配准失败类别；本批没有持久化碰撞对象，无法区分成员碰撞、环境碰撞或 AirSim 状态问题，不能把 `0/20` 单独归因于 D5。

本批在线 truth use、global-ID mismatch、friend/duplicate conflict 均为 0。第二 primary 必须按每场 current membership 动态确定；candidate seed 002 为 `INT-02`，不能固定按 `INT-03` 汇总。candidate 的 soft prediction/trend coast 没有带来物理收益，不改变 D5 默认主线或多视角合同。额外完成的 `png_ttc_2v2_seed001` 不纳入本 M5N2 结论；其余 tuned/dropout 未执行。

## 2026-07-15 第二 primary 失败分类补充

`summarize_cooperative_visual_funnel()` 已在原有逐资源/逐目标漏斗上增加 `failure_category_counts` 和 `second_primary_failure_category_counts`。第二 primary 可被动区分不可见、投影无效、几何门拒绝、bbox 不稳定/裁切、候选不唯一、量测陈旧、计划/版本/assigned-global-ID 不一致、友方/重复锁定冲突及已关联但稳定锁定不足。最新资源证据若携带错误 global ID，诊断为合同不一致，不再落入 visibility，且不换绑中心 ID。

2026-07-15 确定性专项共 11 case，D5 全量 `272 passed`，零失败；未启动 AirSim、未降低门控。真实 M5N2 至少 10 seeds 的类别分布、第二 primary 5 m 和 coalition completion 仍是开放 P1。

## 2026-07-14 actual-v2 M5N2 联盟证据

最新 M5N2 seed-1 actual-execution 继续使用默认 AirSim detect。canonical 持久化指标出现 `terminal_lock_count=24`，但 visual control、visual switch 和 mode switch 均为 `0`；main diagnostics 的 terminal-switch allowed 也为 `0`。物理层 active pair `2/3`、target `2/2`、coalition `0/1`，T001 第二 primary 最近约 `11.02 m`。这直接证明多次 local/resource-target lock acquisition 不能替代每个 required primary 的可执行视觉证据，也不能替代 coalition completion。

同批 tuned 2v2 seed-1 canonical 已有 visual control `26`、visual/mode switch `2/2`。canonical `terminal_switch_allowed_count` 现已从最终 `control_commands.csv` 独立统计，2v2/M5N2 为 `26/0`；五层 contract/control/terminal-switch/mode/physical 总计 `102/26/26/2/4`，均为 available。缺口集中在 M5N2 第二 primary、几何 drift、detect/YOLO/MOT 多 seed 和二级同 tick freshness，不是五层 schema。两 case identity/state online truth use 为 `0/0`，D5 继续只读中心 `global_track_id`，不得用 peer、actor/object truth 或本地 MOT ID 创建、改写、换绑全局身份。

当前仅有每场景 1 seed，D6 formal overall status=`fail`。D5 当前开放 P1 为上述四类；IBVS、真实身份源、完整在线 PnP/ROS 2 保持 P2/P3。M5N2 至少 `8/10` 的既有视觉完成门与 physical coalition `0/1` 分母独立。默认检测仍为 AirSim detect。本节只同步运行证据，不改变多视角合同或算法。

## 2026-07-14 M5N2 本机证据与多视角证据边界

postbatch baseline/candidate 表明，多视角或联盟历史不能替代每个 active primary 的当前本机 measured bbox。D5 虽有 `151/120` 条几何 locked，但控制阶段两组均仅 INT-03 有 `40` 条非零 bbox，其余 active pair 在约 `23-29 m` acquisition timeout。camera scope 已按 `InterceptorN:0` 隔离；没有证据表明匿名 detection 被跨资源共享。

当前合同把跨视角支持保留为关联/仲裁证据，只有 own-camera measured bbox、连续稳定 lock、bbox scale/stability 及安全合同全部成立时，单个 primary 的 `execution_lock_allowed` 才为真。DTO 已携带 bbox/中心和完整 producer scope，D5 不从 peer bbox 构造本机控制输入，也不改写 `global_track_id`。代码级 P1 已关闭并通过 `261` 项测试；真实多相机持续 detection、异常大框与至少 10 seeds 仍开放。

## 2026-07-14 semantics_v2 M5N2 第二 primary 历史断点

最新 seed-1 的 T001 第二 primary 已经形成持续本地视觉证据：baseline/candidate 的 INT-02 measured detect 为 `195/193`，raw visual lock 为 `140/142`，final execution lock 为 `18/18`，两组 coalition consensus 均为 `14`。因此 M-to-N 共同视觉的主要缺口不是 LocalVisualTrack 完全缺失，而是 bbox 稳定时间晚于当前 `arrival_window_end_s=2.2`：bbox 分别在 `19.0/18.6 s` 才稳定，后续 raw lock 被执行合同 fail closed。

D5 新增逐资源 `d5_live_visual_funnel_v1` 与 measured-lock streak，使第二 primary 的 first failure 可稳定归类为 detection、geometry、association、evidence contract、execution contract、stable lock、bbox 或 handoff，不依赖 AirSim truth ID。M-to-N 缺 committed membership 仍在 evidence-contract 阶段阻断；计划/联盟版本、friend、duplicate 和 `global_track_id` 规则均未变化。该阶段 D5 全量 `258 passed`。顶部 postbatch 章节已确认 current local track 可进入下游，后续重点转为持续 detection、bbox 尺度和多 seed。

## 2026-07-14 committed/current 共同视觉连续性补充

postfix seed-1 的 M5N2 baseline/candidate 中，T001 consensus 仅 `13/347`、`12/347`，且两组 `bbox_stable=true` 均为 `0/1388`。旧 runtime 每 tick 仅交付当前 local track，导致所有 bbox history 的 `visible_frame_count <= 1`；与此同时 T001 有 `326/347` tick 的真实 primary membership 变化。D5 现可跨普通 plan version 刷新保留同一 resource-target-local track-camera-backend-stream 的 measured history，但 membership 换员、缺少 committed/current 成员合同或其他身份/安全冲突仍立即重置。

共同视觉和 stable-lock continuity 只统计 current committed coalition 的 active primary，不允许历史成员、standby reserve、无效 commit 或旧 plan snapshot 补足完成度；`global_track_id` 仍只回显中心绑定。输出新增 bbox history length/CV/reset/key/signature/source 等审计字段。2026-07-14 D5 全量 `255 passed`，零失败，未运行新 AirSim；锁定门限和 YOLO/native-MOT 准入状态不变。后续 canonical actual 已传递 committed membership、pre-decision duplicate hint 和稳定的 camera/stream/backend/local-track transition/MOT 字段，该接线不再是开放项。

## 2026-07-14 多视角反馈分级补充

M-to-N 跨视角输出继续区分“看不清”与“安全冲突”。单视角/多视角 confidence、geometry、bbox、timestamp 或 unknown/unverified identity 不足时，输出 `hypothesis_only/ambiguous/hold/reacquire` 与 `observe/request_secondary_cue`，只影响该 pair 的视觉授权，不表示资源不可用。verified friend、spoof、local/global ID conflict 和 duplicate terminal lock 输出 `report_conflict/arbitrate`，保持 hard fail-closed；合法 planned cooperative lock 仍不等于 duplicate。

2026-07-14 确定性专项 52 项和当时 D5 全量 235 项全部通过；本日原生 MOT 历史修复后最新全量为 `241 passed`。接受阈值为零失败、未知不推断敌方、普通不确定性无 hard planner action、`global_track_id` rewrite 与 online truth use 为 0。本次未运行新的 M5N2 AirSim episode；当前 P1 为第二 primary、几何 drift、detect/YOLO/MOT 多 seed 和二级同 tick freshness。三维联合几何/ReID/真实身份链保持 P2，IBVS/ROS 2 保持 P3。

**调研日期**：2026-07-11

**范围**：多拦截器共同观测同一 `global_track_id`、跨视角投影、三角定位、相对位姿与时间同步、多视角 MOT、遮挡与小目标，以及计划内多机锁定与错误重复锁定。

**边界**：本文包含文献/开源审计与 D5 模块内合同实现状态。D5 不分配目标，不创建、不改写、不换绑 `global_track_id`；AirSim actor/object truth ID 只能用于离线评分。

## 1. 核心结论

1. **多机协同定位可行，但不能直接平均 bbox 中心。** 每个相机必须提供双时间戳、内参、畸变、量测时刻外参及其协方差。至少两个视角还需具备足够基线和交会角，才能用带权射线交会、三角化或多视图贝叶斯滤波得到目标位置及协方差。
2. **同步观测适合瞬时三角定位，序贯观测必须做运动补偿。** 分批到达的帧不能冒充同步帧，必须把目标和相机状态预测到共同参考时刻，并按时延、机动和外参误差膨胀协方差。
3. **本地 MOT 与跨相机身份是两层问题。** ByteTrack、BoT-SORT 只维护单相机 `local_track_id`；跨相机仍需 GlobalTrack 投影、几何、时间、外观和计划绑定。
4. **M 对 N 下，多资源共同锁定同一目标不必然是 duplicate。** 若同一有效计划明确 `k_j=3`，三名联盟成员分别锁定同一 `global_track_id`，这是计划内协同支持。计划外资源加入、单资源多本地锁定、单一本地轨迹支持多个全局目标或使用过期计划，才是重复/冲突风险。
5. **当前 D5 主线可保留。** `GlobalTrack -> CameraModel -> image projection -> LocalVisualTrack -> TerminalAssociation` 仍是成熟、可解释的默认路线。需要新增“读取联盟合同后解释多锁定”，而不是让 D5 重新分配。
6. **没有成熟的单一开源完整栈。** 几何、单相机 MOT、多视图跟踪和无人机群相对定位均有候选实现，但仍需 MSM 自己组合时空合同、协方差、安全门控和联盟约束。

## 2. 统一问题定义

设目标 `j` 的中心航迹为 `G_j=(global_track_id, x_j, P_j, t_j)`，D3/D4 给出目标需求和合法联盟：

```text
Coalition_j = {
  coalition_id,
  coalition_version,
  global_track_id,
  required_resource_count = k_j,
  members = [{resource_id, member_role, wave_id, arrival_window}],
  plan_id,
  plan_version,
  coordination_mode,     # simultaneous | sequential | hybrid
}
```

D5 只回答：本地轨迹是否支持**已分配的** `G_j`；多个相机的证据是否一致并能否改善定位；多个 `locked` 是计划内支持还是错误重复；证据不足时输出 `ambiguous/hold/reacquire`。D5 不猜测新身份，不改变联盟或分配。

## 3. 同时、序贯和混合观测

| 模式 | D5 处理 | 优点 | 风险与适用条件 |
|---|---|---|---|
| 同时/窄时间窗 | 各 bearing 和位姿对齐到共同量测时刻，做带权三角化或联合门控 | 瞬时几何约束强 | 要求足够交会角；时钟、滚动快门和外参偏差会形成伪交点 |
| 序贯/分批 | 将 GlobalTrack、相机位姿和历史 bearing 预测到统一时刻，再做 OOSM/轨迹级更新 | 允许遮挡、通信延迟和不同波次 | 高动态下模型误差快速增长；必须保留双时间戳并膨胀协方差 |
| 混合 | 同步观测形成主定位，异步观测维护连续性和交叉验证 | 兼顾精度和覆盖 | 公共先验可能被重复融合；分布式条件需保守处理相关性 |

D5 不决定三架拦截器同时到达还是分批到达。D3/D4提供 `coordination_mode`、成员 `wave_id` 和 arrival window，D7负责导引。D5只按时间槽验证视觉证据：同时模式要求同一同步窗口支持；序贯模式允许分槽锁定，但历史锁定不得计为当前同步三角化支持。

## 4. 协同定位方法

对相机 `c` 的像素观测去畸变后，由 `K_c` 和量测时刻外参得到世界系单位视线 `b_c`：

```text
p_target = o_c + lambda_c * b_c
```

两个以上视角以带权最小二乘求射线最近交点。权重至少包含像素协方差、相机位置/姿态协方差、GlobalTrack预测协方差、measurement/arrival latency、遮挡、尺度、运动模糊和标定健康度。协方差由雅可比、UKF或 Monte Carlo传播验证。射线近似平行、基线过短、重投影误差过大或时间窗不一致时，只保留 bearing/support evidence，不得输出虚假高置信三维定位。

完全分布式时，peer 交换命名空间化 tracklet summary：

```text
(resource_id, camera_id, local_track_id,
 measurement_timestamp, arrival_timestamp,
 bearing, covariance, bbox_area_history, bearing_rate,
 camera_pose, camera_pose_covariance,
 assigned_global_track_id, plan_id, plan_version)
```

像素位置和 bbox 尺度历史适合做一致性与候选排除，但单目尺度有深度歧义，不能单独证明同一目标。缺少有效中心拥有 ID 时，D5仍只输出 `CrossPeerAssociationHypothesis`/`hypothesis_only/hold`，不得创建替代性全局 ID。

## 5. 合法协同锁定与错误 duplicate

### 5.1 `planned_cooperative_lock`

以下条件同时满足时，多架无人机的 `locked` 是计划内协同支持：

- 都属于同一 `coalition_id` 的合法成员；
- `plan_id/version` 有效且 `k_j>1`；
- 每个资源只提交相机命名空间内唯一的本地轨迹支持；
- 所有支持均指向同一中心拥有 `global_track_id`；
- 支持满足到达槽、时效、几何和稳定窗口；
- 没有友方冲突、身份伪造疑点或 local-to-global 多重绑定。

支持数超过 `k_j` 时，D5只报告 `over_support`，由 D3/D4决定备用、轮换或解除资源。

### 5.2 错误重复/冲突

以下情况仍应产生 duplicate/conflict evidence：计划外资源加入；同一资源多个本地轨迹同时锁定同一目标；同一本地轨迹支持多个 `global_track_id`；stale/mismatched plan；一对一计划出现多个 active lock；几何不一致或友方身份重叠。

```text
duplicate_risk = observed_lock_set - authorized_coalition_lock_set != empty
                 or local_to_global_conflict
                 or per_resource_multi_local_conflict
```

因此不能再把“同一 `global_track_id` 的 locked resource 数量大于 1”作为 M 对 N 场景的充分判据。

## 6. 主要论文证据

| 年份 | 论文与原始来源 | 问题 | 中心/分布式 | 同时/序贯/混合 | 验证/代码与 D5 适用性 |
|---|---|---|---|---|---|
| 2017 | Liu et al., *Multi-camera Multi-Object Tracking*, [arXiv:1709.07065](https://arxiv.org/abs/1709.07065) | 跨相机、跨帧联合图关联 | 中心式 | 混合 | 多相机数据验证；说明外观和运动需联合，不能直接合并 local ID |
| 2018 | Chavdarova et al., *WILDTRACK*, [DOI](https://doi.org/10.1109/CVPR.2018.00528), [arXiv](https://arxiv.org/abs/1707.09299) | 七台同步标定相机的遮挡与联合检测 | 中心式 | 同时 | 真实同步 HD 数据和标定；成熟基准，但与机动空中小目标有域差异 |
| 2019 | Tang et al., *CityFlow*, [DOI](https://doi.org/10.1109/CVPR.2019.00900), [arXiv](https://arxiv.org/abs/1903.09254) | 大范围 MTMC 和 ReID | 中心式 | 序贯/混合 | 40相机同步视频和几何；支撑时空约束，车辆纹理条件优于小无人机 |
| 2020 | Hou et al., *MVDet*, [DOI](https://doi.org/10.1007/978-3-030-58571-6_1), [arXiv](https://arxiv.org/abs/2007.07247) | 多视图特征投影到地平面 | 中心式 | 同时 | WILDTRACK/MultiviewX；[代码](https://github.com/hou-yz/MVDet)。固定地平面不能直接套用三维空中目标 |
| 2021/2022 | Nguyen et al., *LMGP*, [DOI](https://doi.org/10.1109/CVPR52688.2022.00866), [arXiv](https://arxiv.org/abs/2111.11892) | 3D几何预聚类与时空 lifted multicut | 中心式全局优化 | 混合 | 多相机基准；适合离线研究对照，在线延迟较大 |
| 2021/2022 | Xu et al., *Omni-swarm*, [DOI](https://doi.org/10.1109/TRO.2022.3182503), [arXiv](https://arxiv.org/abs/2103.04131) | 无GPS无人机群视觉-惯性-UWB相对状态 | 分布式前端/图优化后端 | 混合 | 多机实飞；[代码](https://github.com/HKUST-Aerial-Robotics/Omni-swarm)。可提供相对位姿参考，不直接解决目标身份 |
| 2021/2022 | Zhang et al., *ByteTrack*, [DOI](https://doi.org/10.1007/978-3-031-20047-2_1), [arXiv](https://arxiv.org/abs/2110.06864) | 关联高低置信检测框 | 单相机本地 | 序贯 | MOT17/20等；[代码](https://github.com/FoundationVision/ByteTrack)。适合本地 MOT，不输出全局任务身份 |
| 2022 | Aharon et al., *BoT-SORT*, [arXiv:2206.14651](https://arxiv.org/abs/2206.14651) | 运动、外观、相机运动补偿 | 单相机本地 | 序贯 | MOT17/20；[代码](https://github.com/NirAharon/BoT-SORT)。机动相机有价值，小目标 ReID 可能退化 |
| 2023 | Cheng et al., *ReST*, [DOI](https://doi.org/10.1109/ICCV51070.2023.00922), [arXiv](https://arxiv.org/abs/2308.13229) | 先空间关联、再时间图关联 | 中心式在线图 | 混合 | WILDTRACK等；[代码](https://github.com/chengche6230/ReST)。研究升级路线，依赖训练和 GPU 图网络 |
| 2023 | Du et al., *A Cooperative Target Localization Method Based on UAV Aerial Images*, [DOI](https://doi.org/10.3390/aerospace10110943) | 多 UAV 图像/AOA联合定位和 PDOP | 领导者坐标系集中融合 | 同时为主 | 真实航拍图像、Monte Carlo、UKF；直接支持几何构型和 AOA 协方差的重要性 |
| 2024 | Ma et al., *Track Initialization and Re-Identification for 3D Multi-View MOT*, [DOI](https://doi.org/10.1016/j.inffus.2024.102496), [arXiv](https://arxiv.org/abs/2405.18606) | 2D检测驱动3D轨迹初始化、遮挡、重识别 | 中心式 Bayes/GLMB | 混合 | CMC/WILDTRACK；[代码](https://github.com/linh-gist/3D-Visual-MOT)。理论完整但复杂、依赖域内 detector/ReID |

共 `11` 篇主要论文。Google Scholar 仅用于发现，表内证据均回到 DOI、arXiv或官方仓库。当前环境没有 Web of Science 订阅或导出记录，因此不声称完成 WOS 引文网络核验。

## 7. 开源代码审计

维护状态按 2026-07-11 GitHub元数据和 README 检查；最近 push 不代表已适配 MSM。

| 项目 | 用途 | 许可证/维护 | 适用性 |
|---|---|---|---|
| [OpenCV](https://github.com/opencv/opencv) | 投影、三角化、PnP、标定/畸变 | Apache-2.0；活跃 | **成熟默认**几何原语；不负责身份、协方差或联盟语义 |
| [ByteTrack](https://github.com/FoundationVision/ByteTrack) | 单相机 tracking-by-detection | MIT；非归档，主要代码活动约2024 | **成熟默认本地 MOT**；需重标定小无人机检测，local ID 不能替代 GlobalTrack |
| [BoT-SORT](https://github.com/NirAharon/BoT-SORT) | 相机运动补偿 + ReID | MIT；非归档，主要代码活动约2024 | **可插拔升级**；FastReID/GPU/纹理依赖较重 |
| [MMTracking](https://github.com/open-mmlab/mmtracking) | MOT/SOT/VID工具箱 | Apache-2.0；非归档，主分支活动约2023 | **研究对照**；依赖栈重，不能解决联盟和全局绑定 |
| [MVDet](https://github.com/hou-yz/MVDet) | 标定多相机特征投影 | 仓库 API/根 README未发现明确许可证；2025有提交 | **研究方案，暂不可直接复用**；固定地平面和行人域差异大 |
| [ReST](https://github.com/chengche6230/ReST) | 空间图 + 时间图 MTMC | MIT；非归档，主要代码活动约2024 | **研究升级**；需要 DGL、权重和域内数据 |
| [3D-Visual-MOT](https://github.com/linh-gist/3D-Visual-MOT) | 多视图 GLMB、ReID、遮挡 | MIT；2026有提交 | **强研究对照**；Python/C++混合、计算和数据准备成本高 |
| [Omni-swarm](https://github.com/HKUST-Aerial-Robotics/Omni-swarm) | 无GPS群体相对位姿 | README声明 GPLv3；主代码活动约2022 | **相对位姿参考**，不是目标 MOT；ROS/TensorRT/UWB依赖重且需许可证审查 |

## 8. 选型分级

- **成熟默认**：中心 GlobalTrack 按量测时间预测；OpenCV几何、像素/位姿协方差传播和重投影门控；ByteTrack维护本地连续性；跨相机以几何、时间和计划绑定为主。
- **可插拔升级**：BoT-SORT相机运动补偿；多视图 JPDA/GLMB软关联；带权三角化/UKF；分布式保守信息融合。
- **研究方案**：MVDet/BEV、ReST/LMGP图模型、3D-Visual-MOT/GLMB；Omni-swarm只作为相对位姿参考。
- **无成熟完整实现**：没有单一仓库同时覆盖机动多无人机相机、中心 GlobalTrack、`k_j`联盟合同、到达槽、友方身份、保守授权、分布式失效和 D7门控。

## 9. 本项目状态与优先级

已实现基础包括中心航迹投影、像素协方差/马氏门控、camera-local MOT namespace、truth隔离、detect-to-existing-GlobalTrack注册、跨视角 support、分布式 metadata-only hypothesis，以及友方/版本/时效保守门控。

M 对 N 联盟锁合同已实现：D5 只读携带 D3 schema v2 的 `coalition_id/version`、成员 role/wave、`required_resource_count`、`coordination_mode`、arrival window、`plan_id/version` 和 activation state；`TerminalObservationBus` 将同联盟、同版本、已授权激活且不超 demand 的多资源 lock 解释为 `planned_cooperative_lock`。超额资源、联盟/版本冲突、resource scope 不符、未获执行授权和 local/global 多重绑定仍产生 duplicate/conflict evidence。未激活 reserve/retry 的视觉可锁候选输出 `hold` 和 D7 visual PNG blocker，active primary wave-0 与 k=1 保持兼容。

联盟完成度接口也已实现：`summarize_coalition_visual_completion()`/`TerminalObservationBus.coalition_visual_summary()` 输入 D3 coalition bindings 和当前/历史 terminal associations，输出 `primary_required_count`、`primary_locked_resource_ids`、`primary_lock_complete`、`reserve_ready_resource_ids`、`coalition_visual_consensus`。hybrid 默认要求每个 active primary 当前锁定且连续至少 2 帧；standby reserve 的本机几何匹配只标记 ready，不进入 consensus 或视觉 PNG 授权。无本机 detection、跨 resource/camera bbox、合同版本冲突和 over-demand 均保守阻断。

- **联盟锁与完成汇总语义 P1 已闭合。** 回归覆盖 k=3 三锁合法、第四锁超额、hybrid 2+1、缺一个 primary、reserve-only、连续两帧、联盟/计划版本冲突、reserve 未激活 hold、跨相机 bbox 拒绝和 k=1。
- **跨视角边界不变。** 各 resource-camera 独立做中心 GlobalTrack 投影和 local MOT；cross-view summary 只汇总支持并解释联盟合法性，不创建或重绑全局身份。
- 三角定位、PDOP、同步/序贯支持分层、异步多视图滤波仍属于 P1/P2 研究验证；深度 ReID和图网络保留为研究对照。

`blocks_cv_m5_n2_liveness_batch_20260711` 的三 seed、T001 共识为 0 是实施前历史基线。当前运行证据为 `p1_p2_validation_20260711`：ComputerVision 10 seeds 中，T001 双 primary 在当前计划授权下形成视觉共识 `8/10`；错误 duplicate 为 `0/10`。这验证了计划内合法协同多锁与错误重复锁分离，P1 合同层已经闭合。

控制与物理层仍未闭合：ComputerVision 的 `control_allowed_count=0`；SimpleFlight 15 s 诊断中 30 个 active pair 均未命中，其中 24 个为 `terminal_detection_timeout`。后续应定位持续 detection、D5 lock 与 D7 control gate，而不是回退或放宽合法协同锁、版本、友方冲突和本机检测来源门控。

2026-07-11 D5 已实现 fallback commit 消费接口。对于 `k>1`，只要存在 `coalition_commit` 或 center-failed/fallback 标记，视觉联盟完成必须同时通过 D4 commit 的 `state=committed|executing`、epoch、lease expiry、coalition/plan id+version、required members 和 acked members 校验。commit 无效时 `CoalitionVisualSummary` 保留 primary/reserve 视觉证据，但输出明确 conflict/reason，`coalition_visual_consensus=False` 且 visual PNG authorized resources 为空。当前二级接管和完全分布式完整 ACK commit 正例均已通过，缺 ACK 场景按合同 fail closed；这证明合同语义，不表示物理命中。

OpenCV calibration/`solvePnP` 已增加隔离式 P2 合成 benchmark：它复用 `CameraModel`/`GlobalTrack`，评估外参和双时间戳偏差对单/多视角投影门控的敏感性，但不接入 coalition summary、跨视角在线绑定或 main runtime。truth label 仅用于门控后的离线评分。该结果可为后续三角定位/PDOP 提供外参误差量级参考，不能替代真实多相机标定，也不能证明控制许可或物理拦截。

T001 复验新增了计划/联盟双版本连续性边界：reserve-only replan 可改变 plan ID 和 reserve member，并让 plan/coalition version 同时严格升高；只要两个 primary 的 owner/node、`coalition_id`、target/global ID、resource-target binding、role、epoch 和需求保持不变，D5 可把上一安全帧计入新版本的两帧稳定窗口。`coalition_version` 是代际而非 identity；当前 association 必须已经精确匹配新 plan/coalition version，旧版本绝不重新获得授权。相同/下降 coalition version、coalition ID 改变、primary 换员、换绑、owner/epoch conflict、stale replay、friend/duplicate/wrong-binding、过期或 commit-conflicted evidence 均中断链路。该接口已通过模块测试和 10-seed ComputerVision `8/10` 双 primary 合同验收。

## 10. 建议验证场景

1. `k_j=3`、三名合法成员同时锁定：不得产生 duplicate risk。
2. 第四架计划外资源加入：必须产生 unauthorized over-lock evidence。
3. 三名资源分三个 arrival slot 锁定：历史锁定不得计入同步三角化。
4. 交会角过小、外参漂移或帧时延：输出低可观测度/高协方差，不得提高 lock confidence。
5. 一台相机遮挡、另一台连续可见：恢复仍只能绑定原 `global_track_id`。
6. 单资源多本地锁定或单本地多全局支持：保持 duplicate/conflict。
7. 完全分布式且中心 ID stale：只输出 hypothesis/hold，不创建全局身份。

## 11. 真实 AirSim M=5、N=2 历史证据补充

以下 `blocks_cv_m5_n2_cooperative_live_20260711` 是实施前诊断，已被第 9 节的 10-seed 当前验证取代，不代表当前 T001 合同状态。

2026-07-11 的 `blocks_cv_m5_n2_cooperative_live_20260711` 未形成 cooperative lock。虽然 5 主相机与 2 二级相机均出图，AirSim built-in detection 在绝大多数帧为空；full-flow 只有最后一帧 `Secondary_Recon_1` 对 `TGT-002` 的单 bbox，D5 总计 32 `reacquire`、4 `ambiguous`、0 `locked`。

使用记录的 `Secondary_Recon_1:0` 外参、目标位置和 bbox 重放，D5 得到约 0.09 px 的同相机误差并选择 `T002`。单帧 MOT history=1 导致 `mot_history_too_short`，属于预期安全门控。runtime 把该二级 local track fallback 给多个主资源后产生的 18-78 px 不能作为同相机重投影误差。下一轮必须先修正 camera scope、mesh filter 与 pose/render warm-up，真实连续锁定后才能评价 `planned_cooperative_lock`；本轮只证明联盟合同未因空检测而改绑或误锁。

## 12. 2026-07-12 部分重叠与重捕获 replay

D5 已增加不依赖 AirSim truth ID 的 M-to-N 视觉回归。两相机部分重叠用例明确模拟“R1 看到 G1/G2/G3、R2 看到 G2/G3/G4”：每个 camera batch 先独立使用 GlobalTrack 投影、像素协方差、马氏门和 Hungarian 注册，汇总层只让 G2/G3 形成双资源支持，G1/G4 保持单视角；相同 local ID 始终按 resource/camera 命名空间隔离。

锁定后 1-5 帧缺失用例不引入 D5 coast/KF。前两帧只输出未过期的 lost/reacquire evidence，第 3-5 帧在 10 Hz 下超过 0.25 s 后 fail closed；观测恢复和 MOT ID 变化均需两次 measured 支持。外参漂移、0.5 s 高动态时间偏差和旧 plan replay 均被保守门控。模块全量为 `168 passed`。

这关闭 M-to-N 的模块级 replay 支撑，不关闭真实 AirSim 的双 primary 共同可见、遮挡恢复、二级完整覆盖或联盟物理完成。后续 paired M5N2 必须使用相同几何、35 s 和相同 seeds，并保持 online truth use、wrong binding、reserve 越权和 `global_track_id` rewrite 为 0。

### 12.1 M-to-N summary 证据

上述 partial-overlap 与重捕获场景现由 `d5.p1_visual_robustness_summary.v1` 固化。逐 case JSON 明确区分单视角/多视角支持、预期 geometry reject、恢复前 ambiguous/reacquire 和恢复后 lock，并单列在线 truth 使用与全局 ID 改写计数。D6 可通过 `--d5-summary` 读取版本、证据路径、10/10 通过、24 次保守拒绝和逐 case 紧凑结果；完整明细仍留在 D5 JSON 顶层 `cases`。该证据只证明确定性合同，不替代 M5N2 AirSim 联盟完成率。
