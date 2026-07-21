# D5 终端视觉配准与身份认证算法原理与实施文档

**状态日期：2026-07-21**

**适用范围：** 本文依据第五研究模块（D5）的当前代码、README、PLAN、模块原理文档和系统总汇总，同步说明算法原理、数据合同、代码实施路径与验证结果。文中严格区分默认在线主线、已实现但非默认的辅助/离线能力，以及尚未实现能力；计划项不能据此解释为已上线能力。

## 2026-07-21 宽视场稳定门实施

实现位于 `DeterministicLookAtScanPolicy`。`ActiveVisionSafetyConfigV1` 新增
`zoom_stability_window_frames` 和 `zoom_minimum_binding_score_margin`，默认分别为 `3` 和 `0.05`。
构造策略时不传新参数仍可正常运行。窗口设为 `1` 时，单帧满足原条件即可缩放。

每次 `select_action()` 先执行原有版本、通信、相机可用性、投影和友方保留检查。新状态表按相机
隔离，只保存该相机当前键、连续帧数以及最近的策略时刻、快照时刻、量测时刻和到达时刻。处理顺序为：

```text
版本或通信失败 -> 清状态 -> WIDE 扫描/保持
相机忙或不可转动 -> 清状态 -> 保持当前 FOV，恢复后重新过宽视场门
无有效投影 -> 清状态 -> WIDE 扫描
仅有旧、低置信或视场外投影 -> 清状态 -> WIDE 重捕获
多个近等质量有效投影 -> 清状态 -> WIDE 重捕获
有效唯一绑定 -> 更新本相机连续帧数 -> N 帧前 WIDE，N 帧后再检查协方差并决定 ZOOM
```

计数要求当前时刻、快照时刻、量测时刻和到达时刻都严格推进。完全重复的同一帧保持原计数；任一
时间倒退清空旧状态并失败关闭。计划版本、联盟版本或目标 ID 进入状态键，变化后不会继承旧缩放
资格。通信版本继续走既有实时一致性门，但不写入稳定键，避免把健康通信的普通版本递增误判为
目标绑定变化。

状态机只选择已有 `ActiveVisionActionV1`，不增加控制字段。`global_track_id` 仍来自当前计划和中心
候选交集；同相机互斥、友方保留、投影几何、机械限位、速率和超时检查不变。当前策略输入不含
runtime ACK 或 `ActiveVisionCameraFeedbackV1.last_accepted_command_version`，本阶段没有新增 ACK
接口。阶段 B 需在既有 episode 数据合同中记录真实执行确认，再评估是否扩展稳定门输入。主动视觉
bundle 会校验实现文件 SHA256，因此旧 v5 development bundle 在新实现上应拒绝加载；本轮不重训、
不改写旧权重，也不据此放宽 shadow/assist 门。

## 2026-07-21 canonical seed 视图实施

`canonical_seed_view.py` 对两类数据使用同一流程：先调用既有 strict loader；读取 training seed
registry；独立复算 shared registry 的数值 seed 排序、assignment/content hash 和 `60/20/20`
目录；核对数据恰好覆盖 0-99 且与 `1000-1019` 无交集；最后按 seed 构造只存在于内存的 episode
descriptor/tracklet episode split。源 manifest、图/标签、在线 gzip 流和离线标签均不写入。

detached manifest 记录 source manifest/content/split/training-set hash，两个 registry 的 file/
content/assignment hash，source/consumer schema，canonical seed/episode/sample/edge 计数，以及新的
split/training-set hash。manifest 自身再计算 content hash。已有 view 加载时先根据当前源数据和
注册表重建期望 payload，再与磁盘 JSON 做全对象比较；任一字段变化直接失败关闭。

图 readiness 和 `run_training_pipeline()`、主动视觉 `run_formal_behavior_cloning()` 新增三个显式
参数：canonical view manifest、training registry、shared registry。三者必须全有或全无。显式
模式把 detached view 文件 SHA256 作为 dataset manifest 身份，并把 registry binding 写入训练配置；
默认模式继续使用旧 manifest/split。这样旧开发 bundle 不会被静默解释为 canonical 模型。

正式图视图的 episode 为 `7715/2574/2562`、候选边为 `281/116/83`、负边为 `13/4/2`。正式主动
视觉视图的 episode 为 `540/180/180`、sample 为 `695705/229651/227886`。两类视图 seed 均为
`60/20/20`，保留 seed 泄漏为 0。该实施只关闭 split 身份不一致，不执行模型训练，不改变在线
关联、相机命令或 `global_track_id` 合同。

## 2026-07-20 主动视觉行为克隆实施

正式入口采用六段流水线：严格加载数据集；在 train 中抽取 5v5、50v50、200v200 容量探针；把每个
安全候选动作展开成 35 维特征并按 split 写入 memmap；在完整 train split 上做掩码批量交叉熵训练；
用 validation 选择最佳 epoch；最后一次性计算 train/validation/test 分层指标和推理时延。候选动作
数量由当前状态决定，当前数据为 4 或 7，不写死相机或目标规模。

流式缓存保存候选特征、候选意图/FOV/yaw/pitch/目标引用标志、每样本候选数、规则动作索引、相机
类型、场景和规模。train/validation/test 分别有 `4,669,959/1,625,596/1,565,555` 条候选行。
训练配置为 seed `20260720`、5 epoch、batch 2048、隐藏层 64、学习率 `3e-4`、CPU 16 线程。每个
epoch 完整呈现 685,005 个训练样本，不做类别复制或小样本替代。

最佳 epoch 为 5，train/validation/test 交叉熵为 `0.106584/0.105403/0.109311`。test 精确动作、
意图和 FOV 准确率为 `0.955978/0.982378/0.982378`。分层结果揭示总体数值的限制：
`observe_target` 4,051 个 test 样本全部被判为 `reacquire`，`hold` 无正样本；search intent 判断正确，
但精确 yaw 动作准确率只有 `0.582657`；recon 精确动作准确率为 `0.621823`。

验证集只读温度缩放得到 `T=0.906731`。test NLL 从 `0.109311` 降至 `0.108656`，Brier 从
`0.059946` 变为 `0.059955`，15-bin ECE 从 `0.020389` 升至 `0.020856`。该校准没有进入 bundle。
bundle v5 记录 `development_shadow_only`、assist=false、PPO=false、rule fallback required=true、
camera command authority=false。shadow loader 可用，assist loader 返回
`bundle_assist_not_admitted`。权重只在 ignored outputs，在线默认规则路径不变。

正式训练没有使用 D6 提供的 1,063,214 条相邻 observed outcome；它们缺少 requested action、runtime
ACK 和执行归因。PPO 仍需独立 reward、counterfactual 和 causal label。2026-07-21 canonical view
已统一 split 身份，联合模型仍需独立标签、准入和运行合同。详细统计见
`../results/active_vision_bc_formal_20260720.json` 和
`../reports/D5_ACTIVE_VISION_BC_FORMAL_20260720.md`。

## 2026-07-20 图数据审计与开发训练实施

`tracklet_training_audit.py` 以只读方式调用正式 dataset loader。loader 对 12851 个 graph/label pair
逐文件校验 SHA256，并检查 dataset/graph/label schema、节点和边特征顺序、整 seed split、class
balance、split hash 与 training-set hash。审计报告按 split 和场景规模统计 edge-free、正负/未标注
边、candidate recall availability、pair 分母和困难负样本来源。

冻结训练门包括：各 split edge-free `<=0.90`；train 正/负边至少 `100/100`，validation/test 至少
`50/30`；candidate recall 标签可用率为 1.0 且每 split 至少 100 个 pair；至少 80% 场景规模 cell
同时具有正负边；test 至少 20 个唯一 seed。当前数据有 `12532/12851` 个 edge-free 图帧，负边为
`11/4/4`，partial recall 分母为 `4/1/1`，因此训练与 promotion 均失败关闭。

正式 `run_training_pipeline()` 仍要求 validation 全图真值完整。只有显式传入 development-only 和
readiness audit SHA256 时，训练器才允许在 eligible labeled edge 上选择模型、拟合 validation-only
temperature 和阈值。此时 precision/recall/F1/Brier/ECE 只标记为
`labeled_candidate_edges_only`；误合并率和完整 candidate recall 保持 unavailable。

模型 bundle 磁盘合同升为 `d5.tracklet-model-bundle.v3`。manifest 除既有 dataset/split/training/
config hash、feature version/order 和模型结构外，新增 readiness audit SHA256、实现源文件 SHA256
和显式 admission 状态。loader 会校验 bundle 记录的实现哈希与当前训练/图网络/审计实现一致；任一
差异使运行时 scorer unavailable 并回退规则路径。开发 bundle 永远为
`development_only_fail_closed`、`default_model=false`、`g1_assist_eligible=false`。

固定 seed `20260720` 运行 40 epoch，选择 210 条正边和 11 条负边，最佳 epoch 38。validation/test
F1 为 `0.9804/1.0`，但各自只有 4 条负边；temperature=`0.839666`、threshold=`0.620054`，完整
误合并率和 candidate recall 不可用。该结果只验证软件管线。权重 SHA256
`9bbe53d6cab52e529155b8b92318e98e9bf7e373846fdee38a1f3b39235cbf2d` 两次一致，完整 bundle 只在
ignored outputs 保存。

## 2026-07-20 同流多批次实施

正式生成器按运行周期把所有已到达视觉批次送入 D5。通信退化场景可能在一次调用中包含同一相机的
多个 batch。旧代码在结构预检后强制 stream key 唯一，导致正式目录写入 209 条进度后于下一项
`communication_degraded` 200v200 中断。

该旧目录及其 generation plan/manifest 绑定提交 `c5a9f6d`。D5 修复与 runner 修复形成新提交后，
不得跨提交恢复或拼接旧进度。正式生成必须在同时包含两项修复的新干净提交上，以新输出目录从
sequence 0 重建全部 900 episode；旧 209 条记录只用于保留故障过程。

当前实现先按下式建立规范处理序列：

```text
sort_key = (arrival_timestamp, resource_id, camera_id, measurement_timestamp)
```

排序只确定同一接收窗口内已到达批次的处理顺序，不改变任何时间戳，也不按 measurement 重排通信
语义。随后从各 tracker 的已提交双高水位复制暂存状态，对规范序列逐项调用无副作用的时间转移函数：

```text
(latest_measurement, last_arrival)
    + (measurement, arrival)
    -> (temporal_status, staged_latest_measurement, staged_last_arrival)
```

正常批次同时推进两个暂存高水位；OOSM 只推进暂存 arrival；重复 arrival、相对已提交高水位的
arrival 回退和重复量测直接抛错。tracker 用有序浮点时间戳序列登记本 episode 已接收的全部
measurement，二分检查容差为 `1e-12 s`；暂存事务另登记本调用已预检时间戳。因此等于当前高水位、
重传较早正常帧和重传已忽略 OOSM 都会在提交前拒绝。登记不保存图像或检测身份。只有所有 stream
的整批推演成功后才调用 tracker update。该两阶段过程使后续非法批次不能留下前缀状态污染。

匿名 local ID 在跨帧保持稳定，因此同一相机的多个正常批次会产生相同 `tracklet_key` 的不同时间
版本。稀疏图是当前状态快照，不能同时容纳这些历史版本。`process()` 先顺序消费全部批次，再为每个
stream 选最后一个 `tracker_state_updated=true` 的 batch 进入图。空的正常扫描会替换此前证据；
OOSM 不替换最后有效状态。`Scalable3DStepResult.camera_batches` 保留全部接收审计，`tracklets`、
`camera_geometries` 和 source-observation link 与实际图节点保持一致。

新增测试验证同流两正常批次、正常/OOSM 混合、历史 measurement/OOSM 重传、三类事务失败和多相机
输入逆序等价。2026-07-20 定向测试 `31 passed`，D5 全量 `410 passed in 11.68s`。在线 payload
仍拒绝 truth/object/actor ID，
本地 tracker 不生成或改写 `global_track_id`，批次数量由输入决定。

## 2026-07-20 camera-local OOSM 实施

原 `_AnonymousCameraTracker` 只保存一个 `_last_timestamp`，它实际记录 measurement 时间。
`adapt_batches()` 在提交前要求该值单调，`update()` 又用它计算速度并覆盖当前状态。通信抖动下，
较新的帧可先到、较旧的帧后到；直接拒绝会中断 episode，直接放行则会把 tracker 状态回退。

实现将单值拆成：

- `_last_arrival_timestamp`：该 camera stream 已接收批次的到达高水位；
- `_latest_measurement_timestamp`：已实际更新 MOT 状态的量测高水位；
- `_oosm_measurement_ignored_count`：合法 OOSM 的累计保守忽略数。

`adapt_batches()` 仍先完成所有 truth-free 和 source observation 唯一性检查，再按上节两阶段事务
对一个或多个同流批次进行无副作用时序预检，最后按规范 arrival 顺序提交。单流判定为：

```text
arrival < last_arrival       -> fail closed: arrival regression
arrival == last_arrival      -> fail closed: duplicate delivery
measurement == latest_state  -> fail closed: duplicate measurement
measurement < latest_state   -> accept as OOSM, no tracker state update
measurement > latest_state   -> normal deterministic MOT update
```

OOSM 分支只推进 arrival 高水位并增加计数，不执行匹配、ID 分配、命中/漏帧、中心/边界框、速度、
尺度变化或 measurement 高水位更新。适配结果保留输入双时间戳和该时刻相机几何，tracklet 为空，状态
为 `oosm_ignored`。下一正常帧继续相对于最后一个有效 measurement 状态计算运动量，避免负时间差或
旧框污染。重复与回退错误均在状态变化前抛出稳定异常。

该实现是没有历史缓冲条件下的保守最小方案。它没有实现固定时滞 OOSM 重放，也不声称利用了迟到
帧的信息增益。在线真值隔离、匿名 local ID、中心 ID 只读和普通顺序匹配公式均未改变。

## 2026-07-20 主动视觉 staging 实施

性能剖析把 active-vision staging 拆为快照/样本构造、online writer、offline join、物化加载、公共
audit、规范化 JSON、SHA256 和 gzip。200-camera/400-track fixture 中，主要开销来自每个相机
样本重复调用 `_validate_snapshot_center_references()` 和对共享 snapshot 做递归 truth-free 审计；
gzip 累计耗时较小，因此保持 level 6。

实现增加私有 `_SnapshotReferenceIndex`。缓存键只使用冻结 snapshot 的对象身份，并由 weakref 在
对象释放时删除。索引保存中心 ID、相机成员和每相机分配集合。sample 构造利用索引校验中心引用，
并单独审计动作、版本、反馈和 ACK。writer 调用 `force=True` 重新建立索引，防止调用方绕过 frozen
语义后把变化写盘。reader 每遇到唯一 snapshot 行建立一次索引；公共 audit 每次重新从文件创建
对象，不复用前次审计证据。

私有 `_PreparedStreamObject` 保存已审计 payload、规范化字节和对象键。对象键直接对规范化字节
计算 SHA256，写行时嵌入同一字节。输出与原 writer 的规范化 JSONL 逐字节一致。确定性测试固定
200/400 fixture 的解压 SHA256，并比较两次 gzip 输出；调用计数测试约束重复编码，篡改测试在
`_snapshot_to_payload()` 注入真值字段后要求写盘前失败关闭。

验证结果为 fixture 构造 `2.3597→0.1097 s`、online stage `0.0634→0.0432 s`、materialized
load `2.3948→0.1802 s`；既有 3,536-sample 制品 writer `3.5529→0.7313 s`。数据专项
`18 passed`，D5 全量 `400 passed in 9.74s`。schema、公开 DTO、采样和特征未改变。

## 2026-07-20 clean-tree 200v200 postopt2 验证

main 在提交 `45b36500dc3c6935b1f116614993e291041eb12d` 上，以固定 nominal 200v200、2 s、
seed 930-932 复跑 writer 优化后的完整生成链。证据目录为
`capacity_probe_v2/nominal_timed_postopt2/`。三场均为有限状态，
`repository_dirty=false`、`online_truth_use_count=0`；D5 graph dataset 正常最终化。

| seed | episode run | artifact staging | D5 active-vision staging |
| ---: | ---: | ---: | ---: |
| 930 | 34.3668 s | 4.1704 s | 4.0494 s |
| 931 | 41.8854 s | 4.1311 s | 3.9898 s |
| 932 | 48.4893 s | 4.1357 s | 3.9995 s |

postopt1 到 postopt2 的总 artifact staging 为 `126.4682→12.4372 s`，总 generation 为
`262.2866→144.5513 s`，finalization 为 `7.7377→7.2777 s`，episode run 为
`127.9871→124.7415 s`。D5 active-vision staging 从
`41.5623/43.2639/41.2271 s` 降至 `4.0494/3.9898/3.9995 s`。同配置、同 seed、干净工作树和
真值隔离证据共同关闭 D5 writer P1 的系统级复跑项。算法、schema、采样、特征和门控未改变，
因此不能将该结果解释为在线关联加速或实时能力。

active-vision 仍只有 3 个 seed 和 1 个测试 seed。finalizer 以
`insufficient_unseen_test_seeds` 失败关闭并保留 staging；正式 900-episode corpus、20 个未见测试
seed、BC/PPO、checkpoint、paired shadow 和 assist 准入仍开放。

## 2026-07-20 clean-tree 200v200 postopt1 历史验证

main 使用固定 nominal 200v200 配置运行 3 个 2 s episode，seed 为 930-932。生产提交为
`4052d9411363c39d52100c0e3a4f60ee88443cab`，三场 `repository_dirty=false`。基线和优化后产物
分别保存在 `capacity_probe_v2/nominal_timed/` 与 `nominal_timed_postopt/`。本节保存 writer
优化前的历史归因，不代表 postopt2 当前性能。

| 计时项 | 基线 | 优化后 | 变化 |
| --- | ---: | ---: | ---: |
| episode run | 125.2205 s | 127.9871 s | +2.2% |
| artifact staging | 225.9243 s | 126.4682 s | -44.0% |
| finalization | 116.5624 s | 7.7377 s | -93.4% |
| generation total | 467.8007 s | 262.2866 s | -43.9% |

分项计时把 D5 两条路径区分开。匿名 tracklet graph 每场 staging 仅
`0.0250/0.0259/0.0290 s`，并完成 dataset 最终化。active-vision 整 episode 记录每场仍需
`41.5623/43.2639/41.2271 s`，占对应 artifact staging 的 99.6% 以上。由此确认当时重复
finalization 审计已不再是主热点，并把 active-vision writer 定位为下一热点。该 writer 热点已经由
上节 postopt2 系统复测关闭；优化保持了同一 schema、采样、特征和真值隔离结果。

三场在线 truth use 都为 0。active-vision finalizer 因测试 seed 规划数为 1、低于正式门限 20，
返回 `insufficient_unseen_test_seeds` 并保留未最终化数据；这是预期的失败关闭。该实验尚未生成
900-episode corpus，也没有运行正式 BC/PPO、生成 checkpoint 或形成 assist 准入报告。

## 2026-07-20 主动视觉整 episode 数据实现

新增 `active_vision_episode_dataset.py`，实现以下版本化合同和 API：

- `ActiveVisionEpisodeRecordV2` / `ActiveVisionEpisodeSampleV2`：truth-free 整 episode 与逐决策记录；
- `ActiveVisionCameraFeedbackV1` / `ActiveVisionRuntimeAckV1`：执行反馈与可选 ACK；
- `ActiveVisionOfflineLabelV1`：独立 evaluator reward/outcome/counterfactual/causal label；
- `stage_active_vision_episode_record()` / `stage_active_vision_offline_labels()`：episode-end 双流写入；
- `audit_active_vision_episode_record()` / `audit_active_vision_episode_dataset()`：不保留完整 record 或
  dataset 的逐 episode 流式审计；
- `load_active_vision_episode_dataset_lazy()`：返回 `LazyActiveVisionEpisodeDataset`，提供逐 split 的
  `iter_episodes()`、`iter_behavior_cloning_episodes()` 和 `iter_ppo_episodes()`；
- `load_active_vision_episode_dataset()`：为既有小数据调用保留的显式全量物化兼容入口。

online record v2 使用确定性 `.online.jsonl.gz`。header 固化 episode/source identity；camera feedback
按内容 SHA256 key 写一次；每个唯一 snapshot 写一次，随后写引用 snapshot/feedback key 的 sample；
footer 固化对象数、样本数与 sample-index SHA。sample 的 rule/requested/effective action、三个版本、
可选 ACK 均完整保留，不接受任意 metadata。构造、流式审计与物化加载都验证 action camera、当前
assignment、中心候选、对象 key/引用、版本单调性和中心 track version/timestamp 不回退；未知中心
引用或局部换绑给出稳定失败码。camera/target/resource 列表均按实际长度处理。

offline JSON 仅通过 `sample_key + observation_key` 连接。offline staging 先验证 descriptor 中的
online SHA、episode UID、source identity、sample/object count，再以
`_read_episode_record_stream(..., materialize=False)` 完成 truth-free、对象引用和 sample 合同审计，
不重新构造完整 online record。非物化 reader 对唯一 snapshot 行只构造和检查一次共享对象；每条
sample 行改用轻量合同摘要，仍检查 rule/requested/effective action、中心 ID、三个版本、有限动作集、
相机反馈、runtime ACK、时间和版本单调性，不再构造会递归扫描共享 snapshot 的完整 sample DTO。
物化 record loader 保持原完整对象构造路径。

finalize 在 staged audit 中为每个 episode 生成 `_StagedEpisodeAudit`，并用 `_FileDigestEvidence` 保存
实际 SHA256 及设备号、inode、大小、修改时间。写完 `manifest.json + SHA256SUMS` 和只读位后，内部
最终结构校验复用这些证据；文件指纹变化时返回 `artifact_changed_during_audit`。公共 lazy/audit
入口不接收内部证据，每次独立哈希全部制品并逐 episode 重新执行 stream/offline join。writer 复用
首次生成并审计的 snapshot/feedback payload，避免压缩写入前重复转换。上述优化不改变采样、特征、
行格式、manifest 字段或 schema version。

reward 合同固定 `[-1,1]`。`reward_available=true` 要求离线 outcome 与 provenance；否则 value 和
provenance 必须为 null。counterfactual 独立带 availability；causal label 只有 outcome 和
counterfactual 同时可用时才允许。`ActiveVisionTransition.reward` 因此改为 `float | None`，PPO
训练入口和 dataset PPO view 遇到 `None` 均拒绝。

目录由 `dataset_config.json`、`online/`、`offline/`、`episodes/`、`manifest.json` 和
`SHA256SUMS` 组成。finalizer 先收集完整 `(scenario_version, seed)` group，再按唯一数值 seed 的
SHA256 确定性顺序计算 split；一个 seed 下所有 scenario/scale group 和 episode 传播同一 split。
少于三个唯一 seed 或不足声明 unseen test seed 时不写 manifest。manifest 固化
`shared_seed_values_atomic_across_scenarios=true`、全部 schema/version、artifact/split/training-set
SHA、source Git commit/dirty、source config SHA 与 availability。完成后所有文件去除写权限；
loader 要求 checksum 集合与实际文件集合完全一致，复算 split，并拒绝 group 或 seed 泄漏。

lazy loader 的构造阶段仍完整验证 artifact 集合、逐文件 SHA、只读位、schema、source identity、
online/offline join、availability 和 seed split，但不保存 episode record。BC iterator 每次只物化
一个 online record，完全不读 evaluator label；PPO iterator 每次只物化一个 record 及对应 offline
labels，任一 reward unavailable/null 立即失败关闭。调用方若把 iterator 全部转成 tuple/list，内存
累积由调用方显式承担；正式大数据训练必须直接消费 iterator。

复核修正后，staging/finalize 先把 dataset root 正规化为绝对路径，避免合法相对目录被包含检查
误判。`ActiveVisionEpisodeSampleV2` 同时验证 controller mode/action 状态矩阵：disabled/shadow 及
assist fallback 的 effective action 必须等于规则示范，只有无 fallback 的有效 assist 才能执行
requested action。`CameraLocalTracklet` 对 resource、camera、local 三层 ID 使用同一 truth-like guard。

该 split 变化会改变持久化 assignment 与哈希，故 `active_vision_learning.py` 的 dataset schema
升为 `d5.active-vision-dataset.v2`，episode dataset 升为
`d5.active-vision-episode-dataset.v3`，record/descriptor/sample 升为 v2；
`active_vision_bundle.py` 的 bundle schema 升为 `d5.active-vision-model-bundle.v4` 并绑定 episode
dataset v3。snapshot/action/feedback/ACK/offline-label 仍为 v1。V1 Python record/sample 名称只是
源码兼容别名，旧 v1 嵌套文件稳定返回 unsupported-schema。新增 lazy API 不改变磁盘语义，因此
不再升级 v3/v4。已有 model fingerprint、weights-only、dataset/split/training-set SHA 和 paired
admission 检查不变；版本升级不等于模型准入。

合成容量 fixture 的 16→64 camera 结果为旧嵌套 `302709→4336869` 字节、v2 去重解压
`59617→234721`、gzip `3995→13084`；200-camera/400-track 单 snapshot 为
`731412/37004` 字节（解压/gzip）。main 的 nominal seed 91、2 s 新格式复测中，200v200 总制品
`2.884 MB`，online/offline `1.064/1.818 MB`、`3536` samples、RSS 约 `1.04 GB`、online truth=0。

2026-07-20 当前最新验证为数据管线 `18 passed`、D5 全量 `400 passed in 9.74s`。6 episode ×
48 camera × 96 track 的可复现计数回归中，finalize 的 stream/offline parse 为 `6/6`，旧路径为
`12/12`；`sha256_file` 为 20 个制品各一次，旧路径共 `67` 次。单独 public audit 会再次独立产生
`6/6` 次 parse 和每制品一次 SHA256。200-camera/400-track 合成 stream audit 本机辅助墙钟从约
`9.81 s` 降至 `0.37 s`；两个既有 200v200 gzip（`3536/3744` samples）独立 audit 约
`2.08/2.21 s`。测试还覆盖完整 record/dataset loader 零调用、流审计 `materialize=False`、缓存期间
文件变化失败关闭，以及 truth/未知中心/局部换绑在非物化和物化路径均拒绝。该证据关闭 D5-owned
重复审计开销子项，但尚未执行 900-episode 正式 corpus、正式 BC/PPO、20 个未见 seed 的性能、
AirSim 或模型准入。本轮没有修改 main/runtime。

## 2026-07-20 主动视觉 BC/PPO 与安全执行实现

新增实现文件：

- `active_vision_contracts.py`：v1 snapshot/action、规则 look-at/reacquire/scan、有限动作枚举、
  safety projection 和 mode controller；
- `active_vision_learning.py`：整 `(scenario_version, seed)` group 与跨场景共享 seed 原子 split、
  固定 feature order、原生 PyTorch actor-critic、behavior cloning 和 clipped PPO；
- `active_vision_bundle.py`：manifest、state_dict、SHA256、模型指纹、OOD bounds、
  `weights_only=True` 加载和 runtime unavailable policy；
- `active_vision_evaluation.py`：至少 20 个完全未见 seed 的 paired shadow 非退化门；
- `active_vision_cli.py`：默认 shadow 的非执行 preflight；库内 controller 默认 disabled。

### Snapshot 与动作编码

`ActiveVisionSnapshotV1` 按 camera/track 数组工作。Track reference 只含中心 ID、track version 和
timestamp；Plan reference 只含 plan/coalition version 与 `(resource,camera,global_track_id)` 成员；
camera state 含当前角度/速率、机械限位、最大轴速/slew 和 FOV 能力；projection evidence 含
yaw/pitch error、`2x2` covariance、visibility、occlusion、association confidence、双时间戳和
in-FOV；communication state 含版本、健康度和友方 exclusive reservation。递归 guard 拒绝
truth/actor/object 字段。

`ActiveVisionActionV1` 的 intent 为 observe/search/hold/reacquire，并总是携带有限 yaw/pitch 增量、
wide/zoom、issued/expiry timestamp 和三个版本。目标动作必须引用 snapshot 候选及当前 camera
assignment；search sector 先与相机机械角范围求交。合同没有飞控或 assignment 输出。

### 规则基线与统一安全投影

规则策略优先选择新鲜、可见、低遮挡且高置信的 assigned projection；短时丢失使用最后投影
reacquire；没有可用候选时按 camera/plan 确定性轮转扫描扇区，全部扇区有友方冲突时 hold。
增量同时裁剪单步角、yaw/pitch rate、合成 slew 和最终机械角。

模型只对 `enumerate_safe_action_candidates()` 的有限候选打分。controller 再验证 snapshot/action
plan、coalition、communication version，目标成员、projection age、FOV、当前 actuator busy/
slew 状态、轴速、友方冲突和 timeout。bundle unavailable、SHA/schema/state mismatch、OOD、
低置信、NaN/Inf、异常和推理超时均保留规则动作。输出 `ActiveVisionDecisionV1` 含 requested/
effective mode、rule/requested/effective action、fallback reason、latency、fingerprint 和版本。

### 数据、训练、bundle 与准入

`split_active_vision_episode_groups()` 保持整个 `(scenario_version, seed)` group，并先按唯一
数值 seed 切分，使共享 seed 的跨场景 group 同处一个 split；随后输出 dataset manifest、split 和
training-set SHA。BC 使用规则/行为 action 的离散交叉熵；PPO 对已安全投影的
rollout 计算 discounted return、旧 log probability、clipped ratio、value loss 和 entropy，使用
原生 PyTorch，不依赖 PyG。网络只输出候选 logits/value，不输出 ID 或连续飞控。

bundle 精确校验顶层字段、feature/action schema/order、architecture、feature bounds、训练数据
SHA、weights SHA/size、稳定 tensor fingerprint、admission report 和 strict state_dict shape；权重
只用 `torch.load(weights_only=True)`。paired evaluator 排除 train/validation 已见 seed，并要求
至少 20 个唯一 test seed、正式非合成、逐 episode/总体 safety/visibility/delay 非退化。报告与
模型及三类 dataset SHA 不一致时 bundle 拒绝加载。

### Scalable observation-label 连接

`_PreparedDetection -> CameraLocalTracklet` 传播只读 `source_observation_id`。tracker 排序和
`_match()` 不读取该字段，local ID 仍由 per-camera `trk-*` sequence 分配；同帧 duplicate source
ID 在 commit 前拒绝。`SourceObservationTrackletLink` 导出 observation、tracklet key、camera key
和 timestamp。在线图冻结后，`join_offline_observation_labels()` 才读取 evaluator-only
`observation_id -> truth_entity_id`；无标签节点进入 `missing_tracklet_keys` 并令
`labels_complete=false`。

### 统一三维 episode 接线

main-owned 运行栈已经把 D5 合同接入统一 episode。`RuntimeStepInput` 提供每台模拟相机当前
yaw/pitch/FOV、最近接受版本、D2 中心航迹、D3 当前计划和 D5 几何证据；D5 构造 truth-free
snapshot 后，默认由规则 look-at/reacquire/scan 产生相机意图。`shadow` 仅记录模型请求，
`assist` 未通过正式准入时使用规则动作。

相机观察命令携带 plan/coalition/communication version、issued/expiry timestamp、资源和中心
目标引用。main 再校验版本、有效期和资源一致性，在下一视觉帧更新模拟相机指向/FOV，并发布
`runtime.camera_command_ack`。5v5 开发冒烟为 `84/84` applied，200v200 seed 17、1.2 s 为
`1872/1872` applied。该证据只覆盖接口和状态流，不覆盖真实 AirSim 云台、实机执行、至少 20
个未见 seed 的非退化、主动视觉可见率/重捕获或物理拦截收益。

2026-07-20 主动视觉专项 `17 passed`，D5 全量 `376 passed in 9.94s`。训练 smoke 是 8 个
合成 seed、BC/PPO 各 1 epoch；bundle/checkpoint 仅在 `tmp_path`，没有正式模型。20-seed fixture
只验证准入门及合成拒绝，不能作为可见性、时延或 safety 性能证据。本轮未运行 AirSim。

## 2026-07-20 版本化离线训练与 bundle 实现

新增实现文件：

- `tracklet_dataset.py`：graph/label 分流、episode staging、整 seed split、manifest/hash 和
  fail-closed loader；
- `tracklet_training.py`：多图梯度累积、固定 seed、困难负样本、不平衡损失、validation-only
  temperature/threshold、test metrics 及 train/evaluate CLI；
- `tracklet_model_bundle.py`：manifest/state_dict/SHA256 制品、`weights_only=True` 严格加载和
  不向在线主线抛错的 runtime unavailable scorer；
- `scalable_3d_adapter.py`：在原模型评分边界增加 bundle-unavailable、invalid-output、timeout
  和 invalid-threshold 回退，聚类与中心 binding 未改。

### 数据合同

`stage_tracklet_dataset_episode()` 的输入是已经冻结的 `SparseTrackletGraph` 和独立
`OfflineTrackletTruthLabel[]`。graph NPZ 只包含：schema/feature version、精确 feature names、
episode key、`node_features`、`edge_index`、`edge_features`、匿名 tracklet/camera key、
measurement/arrival timestamp、gate score 和 candidate counts。它不序列化 edge 的
`shared_global_track_ids`，更不包含 `truth_entity_id`。label JSON 单独保存 tracklet key、
measurement timestamp 和 evaluator truth；加载时拒绝未知 key、重复 label 和 timestamp 错位。

`dataset_config.json` 使用 canonical JSON，manifest 保存其 SHA256。每个 episode descriptor
另保存 graph/label SHA256、class balance、truth completeness、candidate-recall availability 和
hard-negative provenance。`finalize_tracklet_dataset()` 只在 `(scenario_version, seed)` group
层面切分，同 group 的全部 episode 同 split；manifest 明确
`edge_level_random_split=false`，并对 split assignment 与 train artifact 列表分别计算 hash。
`load_tracklet_dataset()` 使用 `np.load(allow_pickle=False)`，逐项验证所有 hash、schema、feature
order、dtype/shape、有限值、canonical edge、label completeness 和 seed leakage。

### 训练、校准与评估

`train_tracklet_edge_model()` 固定 Python、NumPy、PyTorch CPU/GPU seed，并以完整图为梯度累积
单元。每图保留全部已标正边；负边按 `gate_score` 从小到大选择，数量由
`hard_negative_ratio` 控制。每图 BCE 使用 `max(1, negative_count/positive_count)` 正类权重，
每个 optimizer step 对有限数量图损失取均值。每 epoch 仅用 validation BCE 选择 state_dict。

选定模型后，对 validation logits 在固定正温度网格上最小化 NLL；校准后概率再按 validation
F1 选择 threshold，precision 和较高 threshold 依次用于 tie break。test 不进入任何选择。
`evaluate_tracklet_edge_model()` 计算 candidate-edge precision/recall/F1、受同相机唯一约束的
cluster 内跨 truth pair false-merge rate、几何候选对同目标跨相机 pair 的 candidate recall、
Brier、ECE、逐图多次前向的 P50/P95 和权重文件大小。只要 split 中存在不完整 evaluator truth，
上述身份/校准指标整体标记 unavailable/null；时延与模型大小仍可独立报告。

### 模型 bundle 与在线回退

bundle 包含 `manifest.json`、`weights.pt` 和 `SHA256SUMS`。manifest 记录
`MODEL_SEMANTIC_VERSION`、graph/node/edge feature version/order、模型维度、训练 dataset
manifest/split/training-set/config hash、validation temperature/threshold/results，并固定
`admission.status=research_candidate_not_default`。loader 先校验 manifest/weights SHA，再验证
版本和结构，最后调用 `torch.load(map_location="cpu", weights_only=True)`；只接受 string-to-tensor
state_dict，要求全部 tensor 有限且 `load_state_dict(strict=True)` 成功。

`CalibratedTrackletEdgeScorer` 只把 graph 的三个数值 tensor送入模型并输出已校准 edge
probability。`load_tracklet_model_bundle_for_runtime()` 将任何 bundle 错误转成带原因的 unavailable
scorer。adapter 对缺模型、unavailable、exception、shape mismatch、NaN/Inf、越界概率、超过
`model_inference_timeout_ms`、低 mean certainty 或无效 decision threshold 全部丢弃模型结果并
使用原 geometry-rule probability。只有有效模型可提供 bundle threshold；后续仍由
`constrained_tracklet_clusters()` 和 `bind_clusters_to_center_tracks()` 处理，输出 ID 集合继续是
中心输入 ID 集合的子集。

CLI：

```bash
PYTHONPATH=research_modules/d5_terminal_association/src \
python3 -m d5_terminal_association.tracklet_dataset finalize --dataset-dir <dataset-dir>
PYTHONPATH=research_modules/d5_terminal_association/src \
python3 -m d5_terminal_association.tracklet_dataset validate --dataset-dir <dataset-dir>
PYTHONPATH=research_modules/d5_terminal_association/src \
python3 -m d5_terminal_association.tracklet_training train \
  --dataset-dir <dataset-dir> --bundle-dir <bundle-dir> --report <training-report.json>
PYTHONPATH=research_modules/d5_terminal_association/src \
python3 -m d5_terminal_association.tracklet_training evaluate \
  --dataset-dir <dataset-dir> --bundle-dir <bundle-dir> --report <test-report.json>
```

2026-07-20 验证结果为新管线 `12 passed`、组合专项 `46 passed`、D5 全量
`355 passed in 9.48s`。所有 checkpoint 位于测试 `tmp_path`。该结果只证明数据/训练/校准/
评估/bundle/回退实现可运行并失败关闭；没有正式数据结果、20 个未见 seed、冻结准入阈值或
默认 checkpoint，故默认仍为几何规则。本轮未运行或修改 AirSim。

## 2026-07-20 稀疏 tracklet 图实现

实现文件：

- `sparse_tracklet_graph.py`：匿名节点、相机外参与协方差、几何候选边、degree cap、
  同相机互斥聚类和中心 Hungarian binding；
- `tracklet_gnn.py`：原生 PyTorch 消息传递、边概率、独立离线标签、困难负样本、
  正类权重和小样本训练 helper；
- `active_vision.py`：camera-only 环境/策略 protocol、动作 envelope 和规则扫描 fallback。
- `scalable_3d_adapter.py`：duck-typed 在线 batch、匿名 per-camera tracker、相机 metadata、
  六维中心轨迹投影及端到端 sparse graph/cluster/center-binding 封装。

`CameraLocalTracklet` 不定义 `global_track_id`、truth 或 actor/object 字段，构造时递归审计
metadata，并拒绝含 AirSim identity 别名的本地 ID。identity alias 检查除
`truth/actor/object` 字样外，还识别 `TGT-0001`、嵌入式 `camera:TGT-002`、
`TargetDrone_1`、`Target_UAV_7` 和 `intruder-003` 等 truth-like 编号；同一 helper 用于
递归 payload 中的 local-ID 字段，`cam01-track-0001` 保持合法。`TrackletCameraGeometry` 使用 D5
`CameraModel(K,R,t)`，其中 `P_c = R P_ned + t`，另显式携带位置与姿态协方差。实现与
`scalable_3d_simulation.camera_projection` 的 NED 到 optical frame 约定一致。

`Scalable3DTerminalAdapter` 不静态依赖 main 或 D2 类型。它从 duck-typed batch 读取
`measurements`、双时间戳和单一 `sensor_id`，从每条 `vision_bbox` 的
`[u,v,xmin,ymin,xmax,ymax] + covariance` 构造检测。`observation_id` 参与整批安全审计并只读
传播为 `source_observation_id`；
tracker 先按空间顺序规范化检测，再用 IoU/中心距离一对一匹配，并在每个
`(resource_id,camera_id)` 内分配 `trk-%06d`。匹配历史生成
`angular_velocity=[du/fx,dv/fy]/dt` 和 `0.5*log(area_t/area_prev)/dt`。

相机 metadata 支持字典或 `3x3 K` 内参、NED camera center、world-to-camera rotation、位置
与姿态协方差；旋转必须为 proper orthonormal matrix。当前 main DTO 缺少单独 pose covariance
时使用配置 fallback，输出 provenance 为 `configured_fallback`。空扫描只在当前 batch 自带
camera metadata 时输出几何，否则标记 `empty_geometry_unavailable`；不复用旧外参冒充当前
几何，也不输出 stale tracklet。六维中心轨迹 adapter 要求 `state(6)` 与 `covariance(6,6)`，复制前三维
位置/协方差和后三维速度，保留同一 `global_track_id`。

端到端路径固定为 graph -> edge probability -> constrained cluster -> center Hungarian binding。
无模型时状态为 `rule_fallback_model_missing`；模型异常或平均 `2*abs(p-0.5)` 低于门限分别为
`rule_fallback_model_error/low_confidence`；只有调用方注入且输出有效、足够确定的模型才标记
`model_scored`。规则概率只使用已通过物理门的 edge gate score 和共享中心投影数量。

构图先建立相机覆盖索引。对每个相机，从 `K` 的四个像面角点反投影近、远两个深度平面，
转换到北东地坐标系后得到截断视锥的轴对齐包围盒；相机位置协方差按三倍标准差扩张包围盒。
视轴在近远深度中点的位置作为覆盖锚点，按 `camera_index_cell_size_m` 进入三维空间桶。视锥
跨度决定需要查询的邻桶半径，并受配置上限约束。只有时间差不超过
`camera_pair_time_window_s` 且两个视锥包围盒相交的相机对进入下一层。

全部相机对数量通过 `C(C-1)/2` 算术计算，程序不创建完整相机对列表。每个空间桶只与索引
可达邻桶组合；同桶候选按相机索引间隔从小到大轮转，跨桶候选按二维索引对角线轮转。
`camera_pair_budget` 约束实际检查次数。预算耗尽时，剩余索引候选计入
`camera_pair_budget_dropped`，不调用几何门，不进入模型，相关 tracklet 保持单例或未绑定。

入选相机对不再建立 `n_left x n_right` 矩阵。存在中心航迹时，右相机 tracklet 先按中心
投影支持编号建桶；左 tracklet 只读取共享支持桶中距离最小的有限候选。没有中心航迹时，
右侧时间戳有序表通过二分查找返回有限时间近邻。候选按共享中心支持数、投影距离、双时间差、
置信度和 tracklet key 排序，`max_tracklet_candidate_edges_per_node` 同时约束两个端点的候选度。
此后才执行极线、射线、重投影和协方差计算。

对于不同相机节点 `i,j`，先计算时间差和视场有效性，再由相对外参构造
`F = K_j^{-T}[t_ji]_x R_ji K_i^{-1}`，计算双向 point-to-epipolar-line 距离。像素反投影为
世界射线后，要求两个射线最近点参数均为正、交会角大于下限、最近距离小于协方差膨胀门；
最近点中点分别重投影到两个相机，检查 RMS 像素误差和像素马氏距离。

中心 GlobalTrack 按各节点 `measurement_timestamp` 用常速度预测，协方差按时间差和过程噪声
膨胀，再通过投影 Jacobian 传播到像面，并叠加节点像素协方差、相机位置协方差和姿态像素
方差。提供中心航迹时，只有共享至少一个门内中心投影的节点 pair 才保留。边的 14 维特征
固定为时间差、像素马氏距离、重投影误差、射线最近距离、bbox 对数尺度差、尺度变化率差、
角速度差、基线、外参协方差 trace、极线误差、交会角、中心投影马氏距离、置信度乘积和
共享中心候选数。

`NativeTrackletEdgeClassifier` 对节点和边分别编码。每轮将两个端点状态与边状态编码为消息，
使用 `aggregate.index_add_(0, source, message)` 和 `index_add_(0, target, message)` 聚合并按度数
归一化。最终对端点和、绝对差、乘积及边状态做对称分类，公开 forward 只返回边概率。
实现未导入 `torch_geometric`。

边概率不直接绑定身份。`constrained_tracklet_clusters()` 按概率降序合并且检查 camera set
不相交；`bind_clusters_to_center_tracks()` 对匿名簇到中心航迹的平均投影马氏代价执行
Hungarian，并对 margin 不足输出 `ambiguous`。输出 `global_track_id` 必须属于中心输入集合。

`Scalable3DAssociationResult.diagnostics` 合并构图计数与评分来源。字段覆盖全部可能相机对、
空间索引 pair space、实际检查/保留相机对、预算丢弃、tracklet 候选、时间/视场/极线/射线/
重投影/协方差/中心投影拒绝原因，以及 `model_scored` 或规则回退路径。该诊断不包含 truth、
actor 或 object identity。

验证日期为 2026-07-20。seed 200 的 200 目标/4 相机压力测试为 800 节点、240000 可能 pair、
3050 个索引后 tracklet 候选、2953 个最终 cap 前候选、1923 条最终边、最大度 6、密度
`0.006017`，本次实测 `0.442 s`，通过
`<15 s`、密度 `<0.01` 和最大度 `<=6` 的代码门。seed 4 的 24 节点/192 边训练 smoke
包含 24 正边和 72 困难负边，正类权重 3.0，60 epoch loss
`1.038521 -> 0.011535`，训练准确率 1.0。5/20/50/100/200 相机结构矩阵中，每相机一个
匿名 tracklet、相机对预算为 `2C`；200 相机的 19900 总对只检查/保留 400 对，预算丢弃
19500，tracklet 候选 397，全部相机至少进入一个候选对。本次 200 相机结构诊断约 59.2 ms，
测试不设置窄绝对时延阈值。训练/制品同步后的 D5 全量为 `355 passed in 9.48s`。

上述结果关闭 D5 代码内的全相机对和全 tracklet 矩阵缺口。它仍是合成结构验证，不能说明
真实 200 路相机的检测召回、跨视角边准确率、模型概率校准、内存峰值和多 seed P50/P95 已
达标。main/D6 还需持久化新增诊断，量化预算造成的候选召回损失。

该小样本训练结果仍仅为可过拟合性测试；独立数据切分、概率校准和 test 评估的软件已经实现，
但未产生至少 20 个未见 seed 或真实图像的正式结果，也没有默认 checkpoint，不能解释为已
验收 GNN。D5 模块-owned scalable 3D DTO 适配和规则主动视觉模拟相机接线已完成，main scalable
module stack 已调用 adapter；正式 checkpoint、至少 20 个未见 seed 的 paired scalable episode、
真实 AirSim 云台接线和学习型主动视觉训练仍未完成。现有几何规则、约束聚类和 Hungarian
绑定仍是默认运行路径。

## 2026-07-16 真实 ComputerVision 5+1 实现证据

main 的独立专项分支复用了既有 D5 注册链，没有修改算法：每个相机 batch 先按自己的
`measurement_timestamp` 投影 `GlobalTrack`，再执行像素几何门、一对一选择、稳定窗口
和跨视角汇总。场景为 5 个 `1920x1080`/60 度局部相机、1 个
`3840x2160`/75 度侦察相机、5 个 `Quadrotor1` actor；实测 12 秒、49 帧、seed 7。

| 主检测后端 | 召回 | 配准（严格） | 稳定 | 联合覆盖 | 侦察全覆盖 | IDSW |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| AirSim detect | 1.000 | 1.000（1.000） | 0.975 | 1.000 | 0.918 | 0 |
| YOLOv8 + ByteTrack | 0.622 | 0.996（0.966） | 0.955 | 1.000 | 0.878 | 25 |

YOLO+ByteTrack P50/P95 约为 `10.42/12.37 ms`。两路 episode 的 online truth use
和 `global_track_id` rewrite 均为 0。本隔离专项未运行 D1/D2；main 使用 actor
truth 运动学合成带中心 `global_track_id` 的 `GlobalTrack` fixture，truth 另用于
离线评分。`online_truth_identity_use=0` 仅说明 D5 的 local bbox 到 fixture
关联代价、Hungarian 选择和稳定窗口不读取 actor/object/truth identity；它不表示
整个专项完全不读取 truth。

门限为 detect/YOLO 召回 `>=0.95/>=0.90`、严格配准 `>=0.95`、稳定
`>=0.90`、联合覆盖 `>=0.95`、侦察全覆盖 `>=0.90`、IDSW `<=0/<=5`，
truth use/rewrite=0。detect 几何基线通过；YOLO+ByteTrack 因召回、IDSW 和侦察
全覆盖未通过而保持 optional，仍需相应质量改进和多 seed confirmation。单 seed
不能解释为主线晋级，专项分支也不替换默认 D1-D7 流程。

## 2026-07-16 `LocalImageTrackObservation` 离线适配实现

公开入口位于
`d5_terminal_association.manual_video_tracker.manual_records_to_local_image_observations`，
不从 D5 包根重导出。函数接收 `ManualTrackFrameRecord[]` 以及
`sensor_id`、`stream_id`、`image_size`，可选参数为
`spectral_band="visible"`、`local_epoch=0`、`arrival_delay_s=0.0`、
`confidence=1.0`。转换过程为：

1. 固化输入序列并调用 `audit_tracking_identity()`；duplicate count 大于 0 时抛出
   `ManualVideoTrackingError`，不生成部分 DTO。
2. 按 `local_track_id` 保存上一 frame 与连续 measured count。只有 frame 连续且上一条
   也是 measured 时计数加一；lost 或 gap 后下一条 measured 从 1 开始。
3. measured 将 `bbox=(x,y,w,h)` 转为 `(x,y,x+w,y+h)`，中心转为二维数组，以
   `w*h` 和 `image_size` 调用 `adaptive_pixel_covariance_px()`，arrival timestamp
   设置为 `timestamp_s + arrival_delay_s`。
4. lost 强制 `center_px=None`、`bbox_xyxy=None`、`pixel_covariance=None`、
   `confidence=0`；metadata 只保留离线 source、frame、image size、
   tracker/association backend 和连续 measured history。

`LocalImageTrackObservation` 自身继续校验 visible/infrared、双时间戳顺序、
confidence、协方差形状及 global/truth metadata 禁令。适配器不创建或消费
`global_track_id`，也不调用 AirSim。包根移除 manual tracker 导入后，默认
`import d5_terminal_association` 不再无条件加载 manual OpenCV/SciPy 支线；CLI 和
manual 测试显式导入子模块。

2026-07-16 以既有 `b.mp4` 95 帧、5 local ID、475 条记录做离线复核，结果为
`470 measured / 5 lost`、duplicate 0。确定性测试覆盖协方差、双时间戳、
infrared、`xyxy`、连续历史、lost、重复坍缩和屏蔽离线依赖的根包导入；
D5 全量 `288 passed`，接受阈值为零失败、重复量测整批拒绝。该实现只证明合同转换，
不证明通用检测/MOT、GlobalTrack 注册、AirSim 接入或终端控制闭环。

## 2026-07-15 人工视频 local MOT 实现

`manual_video_tracker.py` 与 `scripts/run_manual_video_tracking.py` 提供首帧 `selectROIs` 和无界面 ROI 参数。每个 ROI 建立固定 `local_track_id` 和独立 CSRT/KCF。纯 tracker 模式对高交并比重复输出失败关闭；小型亮目标模式额外执行：

1. 计算 `gray - GaussianBlur(gray, 31x31)`，阈值默认 12，并在全帧执行局部极大值抑制，不写死图像 y 范围。
2. 根据每条轨迹最近两次有效中心做常速度预测；底层 CSRT 中心只作为很小的辅助代价。
3. 构造预测中心到匿名亮点候选的距离矩阵，使用 Hungarian 算法一对一分配，并执行默认 20 像素运动门。
4. 未匹配输出 lost，严禁沿用旧框作为当前量测；后续重现时仍使用用户初始化的 local ID。

### 人工初始化与状态所有权

首帧 ROI 按用户选择顺序编号：

```text
ROI_1 -> local-001, ROI_2 -> local-002, ..., ROI_N -> local-NNN
```

目标数 `N` 完全由 ROI 列表决定，不写死 2、5 或其他规模。该 ID 只在当前视频流内有效，程序不接收 actor name、truth ID、任务分配或 `global_track_id`，也不提供自动换绑接口。CSRT/KCF 各自维护一个 tracker instance，但其 `update=True` 仅表示内部相关滤波器返回 proposal，不代表 proposal 仍属于原目标。

### 候选与预测模型

对灰度图 `G_t` 计算：

```text
R_t(u,v) = G_t(u,v) - GaussianBlur_31x31(G_t)(u,v)
```

在 `R_t >= tau`、`tau=12` 的像素中执行 `7x7` 非极大值抑制和连通分量峰值选择，得到全帧匿名候选集合 `C_t={q_j}`。算法不使用固定 y 范围。每条轨迹最近两个 measured 记录位于帧 `f_k-1,f_k`，中心为 `p_i,k-1,p_i,k`，则：

```text
v_i = (p_i,k - p_i,k-1) / max(1, f_k - f_k-1)
p_hat_i,t = p_i,k + v_i max(1, f_t - f_k)
```

只有一条历史时，以本帧 CSRT proposal 中心作为预测；CSRT 不可用时保留最后有效中心作为搜索基准。该外推仅服务像素关联，不形成三维目标运动模型。

### 一对一联合关联

对第 `i` 条轨迹和第 `j` 个候选构造：

```text
c_ij = ||q_j-p_hat_i,t||_2 + lambda ||q_j-p_csrt_i,t||_2
lambda = 0.05
```

Hungarian 求解以下线性分配：

```text
min sum_i sum_j x_ij c_ij
sum_j x_ij <= 1
sum_i x_ij <= 1
x_ij in {0,1}
```

求解后再执行预测残差门：`||q_j-p_hat_i,t||_2 <= 20 px`。因此一个候选不可能在同一帧成为两个 ID 的有效 measurement。未分配、超门或非法候选的记录均为 `status=lost,bbox=null,center=null`；旧 bbox 只可用于画 lost 标签位置，不能写入 CSV 充当当前量测。后续候选重新通过一对一分配时恢复原人工 ID，不创建新 ID。

### 重复量测审计

逐帧对 measured track pair 计算：

```text
d_min = min ||p_i-p_j||_2
IoU_max = max IoU(B_i,B_j)
duplicate = (||p_i-p_j||_2 <= 1e-6) or (IoU(B_i,B_j) >= 0.70)
```

summary 输出 `duplicate_measurement_count`、`duplicate_measurement_frame_count`、`minimum_center_separation_px`、`maximum_bbox_iou` 和使用的 IoU 阈值。纯 tracker 模式也在落盘前对高重叠 proposal 失败关闭，避免继续生成明显重复的有效量测。

逐帧 CSV 记录 frame、timestamp、local ID、bbox、center、status、tracker/association backend。JSON summary 增加 `duplicate_measurement_count`、重复帧数、最小中心间距和最大 bbox IoU。2026-07-15 `b.mp4` 95 帧实测的重复量测为 0；纯 CSRT 虽报告 95/95 success，却在第 28-38 帧后发生 ID 塌缩，不能作为正确关联结论。

该实现不包含 `global_track_id`、分配计划或身份声明字段，不能绕过本模块正式主线中的 GlobalTrack 投影、协方差、时间戳、几何门控、友方冲突和计划版本检查。

2026-07-15 验证：真实视频 1 个、95 帧、5 个 ID、475 条逐帧记录；D5 全量 `284 passed`，语法与格式检查通过，接受阈值为零测试失败和零重复量测。

## 2026-07-15 M5N2 20-case 实施证据

本轮不改算法，只验证现有 runtime record。main 完成 baseline/candidate 各 10 seeds 后发出 TERM；TERM 生效前额外完成一个 `png_ttc_2v2_seed001`，其余 tuned/dropout case 未执行。该额外 case 不进入以下 M5N2 统计。D5 按每场最终 active-primary 合同动态选取第二 primary，再读取 `main_episode_bus_ticks.jsonl` 中本资源的 `d5_live_visual_funnel_v1`。20 场 `3725/3725` 个适用 tick 均有 decision、first-failure stage/reason，证明 producer/consumer 接线可用；直接 `failure_category` envelope 未持久化，因此该字段的真实可用性仍为未验收。

结果显示算法的主要限制在证据质量而非身份合同：投影有效率为 `100%`，实际 selected second primary 的 assignment/global-ID/friend/duplicate conflict 均为 0；但 measured bbox 仅 `67.54%`，visual freshness `71.33%`，正常 geometry-gate accepted `62.07%`，bbox stable/handoff-ready 仅 `4.32%`。最终 `locked` 占 `46.20%`，严格 complete 仅 `1.40%`，第二 primary 5 m 为 `0/20`。因此不得把局部 locked 或短时重获取直接映射为视觉控制许可。

20 个第二 primary 的最终控制结果均为 `collision_stop`。该结果只证明 D7 控制循环以该原因停控；artifact 未持久化碰撞对象，尚不能区分成员碰撞、环境碰撞或 AirSim 状态问题，故不能从该字段反推 D5 是 `0/20` 的单一原因。

## 2026-07-15 被动失败分类实现

实现复用 `summarize_cooperative_visual_funnel()`。每个 resource-target 仍先计算原有 `visible -> projected -> gate_accepted -> locked -> stable_lock` 阶段，再根据 `TerminalAssociation`、`d5_live_visual_funnel_v1` 和合同字段生成一个 `failure_category`。聚合层输出全部 active primary 和第二 primary 的分类计数，不改变关联状态机。

分类优先保留安全语义：计划/版本/`assigned_global_track_id` 不一致、友方/重复锁定和量测陈旧先于普通视觉失败；随后区分 bbox/edge、不可见、投影无效、几何门拒绝、候选不唯一和稳定锁定不足。最新资源证据即使携带错误 global ID，也只用于报告 `assignment_or_identity_contract_mismatch`，诊断行仍使用中心 binding ID。在线不读取 actor/object truth。

2026-07-15 回归覆盖 10 类失败/状态与完整成功，共 11 个专项 case；D5 全量 `272 passed`，阈值为零失败。此结果只关闭代码级诊断缺口，未关闭真实 AirSim 多 seed、第二 primary 5 m 或 detector/MOT 性能 P1。

## 2026-07-14 actual-v2 真实运行状态

本次仅同步 main/D6 的持久化真实 AirSim 证据，没有修改本章算法、接口或阈值。tuned 2v2 和 M5N2 各运行 seed 1，默认输入仍为 AirSim `simGetDetections` metadata。canonical actual 的 contract/control/terminal-switch/mode/physical 五层均独立 available，总计 `102/26/26/2/4`；`terminal_switch_allowed_count` 从最终 `control_commands.csv` 独立统计，2v2/M5N2 为 `26/0`，不从 control 层回填。2v2 的 `terminal_lock_count=3`、visual/mode switch `2/2`，M5N2 对应为 `24/0/0`。这验证了既有分层语义：D5 lock acquisition 只是一层证据，不能推出视觉控制允许或 D7 mode switch。

M5N2 离线 5 m scorer 给出 active pair `2/3`、target `2/2`、coalition `0/1`，T001 第二 primary 最近约 `11.02 m`。这些物理结果不反向改变 D5 association，不用于在线 binding。两个 case 的 identity/state online truth use 都为 `0/0`；D5 输入输出继续只读既有 `assigned_global_track_id`，禁止创建、改写、换绑或用 truth ID 注册。

canonical actual-execution artifact 和五层 schema `2/2` available 只关闭 P0 证据可用性，不关闭 P1。D6 formal overall status=`fail`，因为当前仅每场景 1 seed，缺 baseline/candidate 配对、完整 dropout 和多 seed。D5 当前开放 P1 是 M5N2 第二 primary、真实几何 drift、detect/YOLO/MOT 多 seed 和二级同 tick freshness，不是五层 schema 缺口；IBVS、真实身份源、完整在线 PnP/ROS 2 保持 P2/P3。默认 detect-first 主线不变。

## 2026-07-14 live visual evidence DTO 与执行许可实现

`LocalVisualTrack.to_evidence_metadata()` 输出当前 measured 证据的 `center_px`、`bbox_xyxy`、bearing rate、类别/质量、resource/camera/stream/backend、图像尺寸、双时间戳和相机几何。`TerminalAssociator._finalize_association()` 进一步核对 producer scope；明确 camera/resource 冲突时把 raw geometric lock 转为 `hold(local_visual_scope_mismatch)`，并清空对应 bbox 连续历史。

`d5_live_visual_funnel_v1` 保留 `visual_match_locked`，但 `execution_lock_allowed` 使用更严格的合取条件：

```text
geometric_locked
and execution_contract_pass
and own_camera_measured_bbox_available
and history_contract_complete
and measured_stable_lock
and bbox_stable
and no_friend_or_duplicate_conflict
```

`d7_handoff_input` 同步携带原始 bbox/中心、producer identity、measured/stability 明细和上述执行结果；`d7_handoff_input_ready` 还要求 handoff recommendation 为真。该 DTO 不授予控制权，D7 仍需自身视线角速率、机动裕度和控制合同门。bbox 缺失、scope 冲突及低于 `8e-4` 的稳定小框均有专项测试。2026-07-14 `py_compile` 和 D5 全量 `261 passed`；安全门限与 `global_track_id` 不变式未变化。

## 2026-07-14 live detect 到 handoff 的可机读漏斗

`TerminalAssociator._finalize_association()` 现额外维护连续 measured execution-lock streak。累计条件同时要求：本地轨迹为 measured、raw visual decision 为 locked、最终 decision 为 locked、execution gate 通过、M-to-N committed membership 合同完整、无 friend/duplicate 冲突、证据未过期。local track、camera/stream/backend、成员、身份或时间连续性变化按既有 reset 规则清零；普通 plan version 刷新不改变连续身份。

每条 `TerminalAssociation.metadata.d5_live_visual_funnel` 使用 `d5_live_visual_funnel_v1`，顺序判定：

```text
measured detect -> projection -> geometry gate -> raw visual lock
-> evidence/execution contract -> measured stable lock -> bbox stability
-> handoff evaluation
```

输出含 `visual_match_decision_state`、`execution_gate_pass/reason`、`measured_lock_streak_count`、`measured_stable_lock`、`bbox_history_length/area_ratio/stable`、`first_failure_stage/reason/failure_domain`。`annotate_visual_png_handoff()` 再附加 range、closing speed、measurement age、timing、handoff blockers 和 `d7_handoff_input`。这些字段是只读证据，不调用 D7、不授予控制、不改变输入 `assigned_global_track_id`。

最新 seed-1 的 INT-02 measured/raw-lock/final-lock 为 baseline `195/140/18`、candidate `193/142/18`；bbox 分别到 `19.0/18.6 s` 才稳定，而 execution window 在 `2.2 s` 结束。新增 3 个专项测试后 D5 全量为 `258 passed`，接受阈值为零失败；该结果关闭诊断合同，不关闭 main/D3 时基和 main->D7 路由。

## 2026-07-14 bbox/MOT/stable-lock 连续历史实现

`TerminalAssociator.decide()` 现在接收 `stream_id`、`detector_backend`、`tracker_backend`、`committed_coalition_member_ids`、`duplicate_terminal_lock_risk` 和 `identity_conflict`，并按 resource/camera/assigned target 保存有界 bbox history。continuity signature 包含 local track、camera、stream、backend、coalition/authorization/member role 和 committed members，但不包含滚动 `plan_version/coalition_version`。稳定计算仍为至少 4 个 measured frame、bbox area `CV <= 0.30`；predicted/lost 不累计。

任何 resource-target rebinding、membership 缺失/变化、local/camera/backend/stream 变化、producer reset、非 measured source、identity/friend/duplicate conflict 都清空 bbox/MOT 历史。metadata 输出 `bbox_history_length`、`bbox_area_cv`、`bbox_history_reset_reason`、`bbox_history_key/signature/evidence_source/source_plan_versions`、`mot_history_raw_length/effective_length/reset_reason` 和合同缺字段。handoff 优先使用 association 中的累计 ratios，即使调用方只传当前 local track 也可形成稳定窗口；YOLO 缺 detector/tracker backend 时合同不完整并 fail closed。

共同视觉的跨 plan 连续尾段还要求 current committed active-primary membership 不变，旧成员、无效 commit、standby reserve 和安全冲突均不贡献 common window。postfix seed-1 只读审计为 M5N2 两组 `bbox_stable=true=0/1388`、T001 consensus `13/347`/`12/347`，2v2 `0/52`；旧链路每条 `visible_frame_count <= 1`，T001 同时有 `326/347` membership transition。2026-07-14 全量 `255 passed`，零失败；没有新 AirSim 运行，没有改变锁定门限、全局 ID 或 YOLO/native-MOT admission。

## 2026-07-14 Ultralytics 原生 MOT 历史状态

`YoloMotAdapter` 对每个 `(resource_id, camera_id, tracker_backend)` 保存 native ID 状态。对当前帧每个 `Results.boxes.id`，若上一帧同作用域同 ID 有实测，则 `consecutive_measured_hits += 1`；否则从 1 初始化。未在当前帧出现的 ID 将 `missed_frames += 1` 并把连续实测数清零，超过 `max_track_age_frames` 后删除。这样 native tracker 可以在短遮挡内保持自己的 ID，但 D5 的 `mot_history_length` 不会把预测/coast 计为实测，恢复后必须重新积累两帧才能满足默认锁定历史门限。

有效 backend 发生切换时状态隔离：native 异常会释放该流 native model 和 history，再启动独立 IoU fallback；持续 fallback 帧可累计自己的 IoU history；native 重建成功后清除 fallback tracker 并从 1 开始。`reset_stream()` 只清指定资源/相机，`reset_all_streams()` 和 `reset_episode()` 清整个 episode。状态中从不保存 AirSim actor/object/truth ID，也不生成全局绑定。

2026-07-14 Results-like 单元回归覆盖 ByteTrack 与 BoT-SORT、连续同 ID、跨资源/相机、ID 切换、空帧、短/长遮挡、stream/episode reset 和 native-fallback-native；D5 全量 `241 passed`，接受阈值为零失败。真实图像 precision/recall、IDSW/IDF1、P95 和多 seed 准入仍开放。

## 2026-07-14 consistency/planner feedback 分级

无需新增输出类型，消费者按现有字段组合判定：

| 类别 | 典型输入 | `consistency_state` | `recommended_d4_action` | 下游语义 |
|---|---|---|---|---|
| 视觉不确定性 | candidate margin、geometry gate、bbox/时序不稳、普通 hold/reacquire、unknown/unverified identity | `unknown` | `observe` 或 `request_secondary_cue` | 仅阻断该 pair 的 D7 视觉切换/请求重获取；资源仍可执行非视觉路径 |
| 安全冲突 | verified friend、spoof、duplicate lock、authorization/version、持续 assignment/ID conflict | `conflict` 或 `inconsistent` | `report_conflict` 或 `arbitrate` | fail closed，可形成 hard planner feedback |

`TerminalConsistencyTracker` 同时读取 association 自带和 cross-view 的 duplicate risk。普通 hold/reacquire 达到连续阈值时只请求 secondary cue，不再升级为 conflict/arbitration。`TerminalCrossViewFusion` 对 stale/unverified identity 保持 `ambiguous/observe`，对 spoof 输出 `ambiguous/report_conflict`；unknown category 仍不推断 hostile。所有输出原样保留 `assigned_global_track_id`，`truth_identity_used=false`。

2026-07-14 专项 52 项和当时 D5 全量 235 项测试全部通过，接受阈值为零失败及上述 action 分级完全匹配；本日原生 MOT 历史修复后最新全量为 `241 passed`。未新增 AirSim episode，真实资源健康仍由 main/D3 自己判断。

## 0. 缩写、产品和记号约定

为避免后文出现无中文解释的英文缩写，本节先给出全文会使用的缩写和产品名：

- 北-东-地坐标系（North-East-Down, NED）：D5 接收三维全局航迹时使用的工作坐标系。
- 应用程序编程接口（Application Programming Interface, API）：模块之间的函数或数据合同。
- 第一研究模块传感器融合（Sensor Fusion, D1）、第二研究模块数据关联（Data Association, D2）、第三研究模块分配规划（Assignment Planner, D3）、第四研究模块分布式降级（Distributed Fallback, D4）、第六研究模块评估指标（Evaluation Metrics, D6）和第七研究模块比例导航（Proportional Guidance, D7）：D5 的上下游协作模块。
- 多目标跟踪（Multi-Object Tracking, MOT）：在连续图像中维持相机本地目标轨迹标识的过程。
- 只看一次目标检测器（You Only Look Once, YOLO）：可选图像检测器；当前适配版本为 YOLOv8。
- 交并比（Intersection over Union, IoU）：两个二维边界框交集面积与并集面积之比。
- 身份切换次数（Identity Switch, IDSW）：同一离线真值对象被不同本地轨迹标识接续的次数。
- 第 95 百分位数（95th Percentile, P95）：延迟分布中 95% 样本不超过的数值。
- 视场角（Field of View, FOV）：相机可成像的角度范围。
- 视线（Line of Sight, LOS）：相机到目标的视向；D5 只提供相关视觉证据。
- 比例导航（Proportional Navigation, PN）和比例导航导引（Proportional Navigation Guidance, PNG）：D7 使用的导引方法；D5 不计算导引控制量。
- 透视 n 点（Perspective-n-Point, PnP）：用三维参考点和二维像点估计相机位姿的问题。
- 随机采样一致性（Random Sample Consensus, RANSAC）：用于含离群点模型估计的鲁棒抽样方法。
- 重识别（Re-Identification, ReID）：利用外观特征在遮挡或跨相机后恢复对象身份的方法。
- 中央处理器（Central Processing Unit, CPU）和图形处理器（Graphics Processing Unit, GPU）：可选图像算法的计算设备。
- 零级、一级和二级优先级（Priority 0/1/2, P0/P1/P2）：项目风险与实施优先级标签，不表示算法版本。
- 微软 AirSim 无人系统仿真器：当前真实仿真运行环境；`simGetDetections`（仿真检测元数据接口）是 D5 默认在线检测输入。
- AirSim 内置 SimpleFlight 飞行控制器：main runtime 用于物理闭环验证的飞行控制后端，不属于 D5。
- OpenCV 开源计算机视觉库（Open Source Computer Vision Library, OpenCV）：D5 默认投影可调用其 `projectPoints`（三维点投影函数），也用于隔离式离线几何对照。
- NumPy 数值计算库：矩阵、协方差和向量计算的基础库。
- SciPy 科学计算库：可用时提供匈牙利线性和分配求解；不可用时使用确定性唯一匹配回退。
- Ultralytics 视觉模型运行库：可选加载本地 `best.pt`（模型权重文件）并运行 YOLOv8、ByteTrack 多目标跟踪算法或技巧集增强的简单在线实时跟踪（Bag of Tricks for Simple Online and Realtime Tracking, BoT-SORT）。
- `pytest`（Python 自动化测试框架）：D5 模块既有回归测试的执行工具。
- 匈牙利算法（Hungarian Algorithm）：批量几何注册时使用的一对一线性和分配方法。
- 联合概率数据关联（Joint Probabilistic Data Association，JPDA）：密集候选下保留多种关联概率的可选研究路线，当前未进入 D5 默认在线主线。
- 远程身份识别（Remote Identification，Remote ID）与开源无人机身份协议实现（Open Drone Identification，OpenDroneID）：合作飞行器广播身份声明的候选标准与实现。
- 微型飞行器链路（Micro Air Vehicle Link，MAVLink）签名与数据分发服务安全机制（Data Distribution Service Security，DDS Security）：合作通信来源认证的候选机制，当前没有真实适配器。
- 视觉重识别（Re-Identification，ReID）：基于外观特征恢复本地目标身份的候选方法，当前未准入小型无人机默认路径。
- 像素（pixel, px）：图像平面坐标和残差单位。

代码字段在首次出现处给出中文语义；数据结构表中“字段”列的每一项均由“中文语义”列解释。公式中的粗体小写字母表示向量，粗体大写字母表示矩阵。

## 1. 模块定位与边界

### 1.1 系统定位

D5 位于“中心全局航迹与资源分配”之后、“末端视觉证据消费”之前。它回答的不是“应该把哪个资源分给哪个目标”，而是：

> 在某资源已经收到一个中心分配的全局航迹后，当前相机本地检测或本地视觉轨迹是否以足够唯一、稳定、及时且身份安全的证据支持这个既有全局航迹？

当前默认主线可概括为：

```text
中心全局航迹与协方差
  -> 预测到相机量测时刻
  -> 相机投影与像素协方差传播
  -> 相机本地检测框中心
  -> 马氏距离门控与候选代价
  -> 版本、授权、身份和时间稳定性门控
  -> locked / ambiguous / hold / reacquire
  -> 跨视角摘要、D4 仲裁证据、D6 评估字段、D7 前置证据
```

其中 `locked`（唯一且满足门控的锁定）、`ambiguous`（候选或证据仍有歧义）、`hold`（合同或身份冲突，保持不执行）和 `reacquire`（需要重新获取视觉证据）是 D5 的四个主决策状态。

### 1.2 工程问题

末端相机可能同时看到：中心分配目标、其他未分配目标、友方或协同平台、身份未知对象，以及由遮挡、图像边缘截断或检测抖动产生的伪候选。本地轨迹标识只在一个资源和一台相机内有意义，不能替代中心全局身份。工程上必须同时解决：

1. 三维全局航迹与二维检测框的坐标、时间和不确定度对齐；
2. 多候选情况下的唯一匹配，而不是选择最近或最大的框；
3. 检测暂失、本地轨迹标识切换和恢复后的迟滞；
4. 计划版本滚动、联盟成员变化、主用/备用状态和授权窗口约束；
5. 多相机分辨率不同、相机位姿不确定和二级侦察线索作用域；
6. 在线决策与 AirSim 真值评分隔离，防止仿真标签泄漏。

### 1.3 科学问题

D5 当前研究的是带身份安全约束的概率几何关联问题：

- 三维状态协方差投影到二维后，马氏距离门控能否在高不确定度与近邻多目标之间取得可解释平衡；
- 几何残差、像面角速度、类别、检测质量和时序稳定性如何组成保守代价；
- 单视角证据、跨视角支持和协同多资源合法锁定如何区分；
- 在不创建新全局身份的前提下，如何把歧义、重复锁定风险和二级节点证据交给上游仲裁；
- 检测器、相机标定、时间同步与局部跟踪误差如何传导到末端锁定率和错误锁定风险。

### 1.4 明确边界

D5 当前严格遵守以下边界：

- 不创建、修改、换绑或重新分配 `global_track_id`（中心拥有的全局航迹标识）。
- 不生成新的分配计划，不选择主用/备用资源，不决定联盟成员。
- 不触发中心、二级或完全分布式模式切换，只提供 D4 可消费的被动证据。
- 不调用 AirSim 控制接口，不输出速度、加速度、姿态、导引指令或拦截点。
- 不把身份未知解释为对抗身份；只有正向验证的友方声明能够触发友方冲突保护。
- 不使用 AirSim `object_id`（仿真对象标识）、`actor_name`（仿真实体名称）或其他真值身份参与 D5 在线关联；仿真编排可用 truth 构造明确标注的输入 fixture，评价器可用 truth 离线评分，但这些 identity 不得进入 D5 关联代价、Hungarian 选择或稳定窗口。
- 不涉及真实火控、毁伤评估、自动授权、自动处置或绕过人工审核。
- 当前代码用于科研仿真、离线评估和人工审查，不等同实机安全认证。

### 1.5 三层身份模型

D5 必须同时区分三种不同语义的身份，三者不能互相替代：

1. **规范战术身份。** `global_track_id` 是由 D2 或当前合法全局航迹所有者维护的中心规范身份，并受航迹版本、分配计划版本、联盟版本、所有者和租约约束。D5 只能引用和核对，不能创建、修改、换绑或把本地证据提升为新的规范身份。
2. **相机本地身份。** `resource_id/camera_id/local_track_id` 只表示某资源、某相机流中的短时本地多目标跟踪身份。ByteTrack、BoT-SORT 或检测框历史都只能改善这一层的连续性；不同相机的相同编号没有身份等价含义，本地编号变化也不自动表示全局目标变化。
3. **合作身份声明。** `IdentityClaim` 表示 Remote ID、OpenDroneID、MAVLink 签名、DDS Security 或视觉合作标签等正向声明证据，状态包括 `verified`（已验证）、`stale`（过期）、`unverified`（未验证）和 `spoof_suspected`（疑似伪造）。它只能正向确认友方或合作平台，不能把“未知”反向判定为对抗目标。

完全分布式时形成的 `hypothesis_only`（仅假设）或临时跨节点证据不是第四种规范身份。它只在当前时期、租约、时间窗和参与资源作用域内有效；没有新鲜的既有 `global_track_id` 时，D5 不得把临时假设升级为永久全局航迹，必须交由 D4 仲裁，并在恢复合法所有者后重新核对。

## 2. 上游输入、核心数据结构与下游输出

### 2.1 上游输入

| 来源 | 当前输入 | D5 使用方式 | 安全约束 |
| --- | --- | --- | --- |
| D1/D2 | 三维位置、速度、协方差、时间戳和中心全局航迹标识 | main 适配器形成 D5 `GlobalTrack`（全局航迹） | D5 只读标识，不回写全局表 |
| 第三研究模块（D3） | 版本化分配、资源、联盟、角色、激活态和到达窗口 | 形成 `Assignment`（只读分配合同）或 `GlobalTrackBinding`（既有全局航迹绑定） | 旧版本、未授权或未激活合同保守拒绝 |
| main runtime | 每相机图像尺寸、内参、位姿、检测框、量测与到达时间 | 形成 `CameraModel`（相机模型）和 `LocalVisualTrack`（相机本地视觉轨迹） | main 负责 AirSim 启停、采集、重置和日志 |
| 友方身份来源 | 仿真字典形式的合作身份声明 | `IdentityChecker`（身份检查器）转换为 `IdentityClaim`（身份声明） | 当前不是实际通信或密码认证适配器 |
| 二级侦察节点 | 已重投影到本地相机平面的图像线索 | `ReconImageCue`（二级侦察图像线索）只降低适用候选代价 | 不能代替版本、授权、友方或唯一性门控 |
| 第四研究模块（D4）降级上下文 | 联盟提交状态、时期、租约、成员确认和当前模式 | 协同摘要检查完全分布式执行合同 | D5 不据此自行切换模式 |

### 2.2 核心数据结构

#### `GlobalTrack`（中心全局航迹）

| 字段 | 中文语义 |
| --- | --- |
| `global_track_id` | 中心拥有的全局航迹标识 |
| `position` | NED 三维位置向量，单位为米 |
| `velocity` | NED 三维速度向量，单位为米每秒 |
| `covariance` | 三维位置协方差矩阵 |
| `timestamp` | 航迹状态时间戳 |
| `track_version` | 航迹版本，需与分配版本匹配 |
| `category` | 对象类别；未知类别保持中性 |

该结构是冻结数据类，配合运行时输入/输出标识断言，防止 D5 意外改写全局标识。

#### `CameraModel`（针孔相机模型）

| 字段 | 中文语义 |
| --- | --- |
| `K` | 三乘三相机内参矩阵 |
| `R` | 世界/NED 到相机坐标系的旋转矩阵 |
| `t` | 世界/NED 到相机坐标系的平移向量 |
| `image_size` | 每台相机独立的图像宽度和高度 |
| `measurement_cov` | 像面量测噪声协方差 |
| `dist_coeffs` | 可选镜头畸变系数 |

#### `LocalVisualTrack`（相机本地视觉轨迹）

| 字段 | 中文语义 |
| --- | --- |
| `local_track_id` | 仅在资源/相机流内有效的本地轨迹标识 |
| `center_px` | 检测框中心像素坐标 |
| `bbox` | 二维边界框，顺序为左上和右下坐标 |
| `bearing_rate` | 像面视向变化率，单位为像素每秒 |
| `quality` | 检测或跟踪质量，范围为零到一 |
| `mot_history_length` | 本地连续跟踪历史帧数 |
| `timestamp` | 量测时间戳 |
| `arrival_timestamp` | 数据到达 D5 的时间戳 |
| `exposure_timestamp` | 相机曝光时间戳 |
| `local_track_state` | `measured`（当前有实测）、`predicted`（仅本地预测）或 `lost`（当前丢失） |
| `prediction_age_s` | 本地预测或丢失证据年龄，单位为秒 |
| `track_transition_state` | 初始化、连续、切换、重获或重置状态 |
| `detection_source` | 检测来源，例如 AirSim 检测元数据或 YOLOv8 |
| `image_size` | 该流独立图像尺寸 |
| `camera_geometry` | `CameraGeometryEvidence`（相机几何与同步证据） |

`predicted` 和 `lost` 状态不能产生 `locked` 或 `registered`（已注册）输出。

#### `Assignment`（D3/D4 只读分配合同）

| 字段组 | 中文语义 |
| --- | --- |
| `assigned_global_track_id` | 当前资源被分配的中心全局航迹标识 |
| `assignment_version` | 与航迹版本比对的分配版本 |
| `plan_id`、`plan_version` | 计划标识和计划版本 |
| `authorization_state` | 授权状态；默认主线只接受代码定义的已批准状态 |
| `resource_id` | 资源标识 |
| `coalition_id`、`coalition_version` | 联盟标识与联盟版本 |
| `member_role`、`activation_state` | 成员角色与激活状态 |
| `required_resource_count` | 当前目标所需资源数 |
| `arrival_window_start_s`、`arrival_window_end_s` | 允许执行的到达时间窗口 |
| `terminal_authorization_scope` | `coalition`（联盟共同口径）或 `per_primary`（逐主用资源口径） |
| `arrival_coordination_required` | 是否要求到达协同 |

#### 身份、侦察与跨视角结构

- `IdentityClaim`（身份声明）：保存平台、声明类型、认证状态、可选本地轨迹标识、像素中心/边界框、时间戳和是否友方。
- `ReconImageCue`（二级侦察图像线索）：保存生产节点、图像帧、可选既有全局航迹标识、像素中心、置信度、资源作用域和指向误差元数据。
- `TerminalObservation`（末端观测）：被动总线载荷，可携带本地视觉轨迹、D5 决策、身份声明和侦察线索，同时保留量测/到达双时间戳。
- `CrossViewAssociation`（跨视角关联摘要）：按既有全局航迹标识汇总资源支持、命名空间化本地轨迹、歧义和重复锁定风险。
- `TerminalConsistencySummary`（末端一致性摘要）：保存连续状态计数、锁定年龄、候选代价间隔、跨视角支持和建议 D4 动作。

### 2.3 下游输出

主输出 `TerminalAssociation`（末端关联决策）包含：

| 字段 | 中文语义 |
| --- | --- |
| `assigned_global_track_id` | 原样回显上游中心全局航迹标识 |
| `local_track_id` | 选中的相机本地轨迹标识；无候选时为空 |
| `association_confidence` | 基于几何、质量和历史的关联置信度 |
| `ambiguity_score` | 由最佳/次佳代价间隔导出的歧义分数 |
| `friend_conflict_state` | 友方重叠或可疑身份状态 |
| `decision_state` | 四态决策结果 |
| `reason` | 首要接受或拒绝原因 |
| `candidate_costs` | 候选本地轨迹及总代价 |
| `recon_cue_used` | 二级侦察线索是否实际降低了所选候选代价 |
| `measurement_timestamp`、`arrival_timestamp` | 量测时间和到达时间 |
| `measurement_age_s` | 到达时间减量测时间得到的证据年龄 |
| `truth_identity_used` | 在线是否使用真值身份；结构强制为假 |
| `metadata` | 投影、协方差、门控、标定健康、稳定性和执行合同诊断 |

辅助输出包括：

- `TerminalObservationBus.runtime_records()`（运行时记录）供 main 和第六研究模块（D6）写盘与评估；
- 跨视角和联盟视觉摘要供 D3/D4 识别合法协同锁、超额锁定或合同冲突；
- `PerPrimaryTerminalEvidence`（逐主用资源末端证据）供 5 个资源、2 个目标（M=5，N=2，简称 M5N2）的场景分资源诊断；
- `SecondaryFrameAssociationEvidence`（二级节点单同步帧证据）供 D4 同一决策时刻消费；
- D7 的视觉 PNG 前置元数据。该元数据只是建议，不是控制许可。

## 3. 坐标、相机与时间模型

### 3.1 航迹时间预测

对航迹时间戳 \(t_0\) 与相机量测时刻 \(t\)，当前实现采用常速度预测：

\[
\mathbf{p}(t)=\mathbf{p}(t_0)+\mathbf{v}(t_0)\Delta t,\qquad
\Delta t=t-t_0.
\]

其中 \(\mathbf{p}\) 是 NED 三维位置，\(\mathbf{v}\) 是 NED 三维速度。向未来预测时，代码对三维位置协方差作保守膨胀：

\[
\mathbf{P}(t)=\mathbf{P}(t_0)+
\min(0.05\Delta t^2,25)\mathbf{I}_3.
\]

这里 \(\mathbf{P}\) 是三维位置协方差，\(\mathbf{I}_3\) 是三阶单位矩阵。该项是轻量过程不确定度补偿，不是完整运动滤波器，也不是 D5 自建全局航迹。

量测时刻优先顺序为：显式 `current_time`（当前决策时间）、本地视觉轨迹最新量测时间、分配时间，最后才是全局航迹时间。这样可以在不使用到达时间替代量测时间的前提下补偿传输延迟。

### 3.2 世界到相机坐标变换

对 NED 世界点 \(\mathbf{P}_w\)，相机坐标为：

\[
\mathbf{P}_c=
\begin{bmatrix}X_c & Y_c & Z_c\end{bmatrix}^{\mathsf T}
=\mathbf{R}\mathbf{P}_w+\mathbf{t}.
\]

\(\mathbf{R}\) 和 \(\mathbf{t}\) 分别是世界到相机旋转和平移。若 \(Z_c\le 0\)，目标位于相机后方，投影无效。AirSim 相机轴从前/右/下转换到 OpenCV 光学轴右/下/前，四元数按相机到世界方向解释后取逆得到世界到相机旋转。

### 3.3 针孔投影

忽略畸变时：

\[
u=f_x\frac{X_c}{Z_c}+c_x,\qquad
v=f_y\frac{Y_c}{Z_c}+c_y.
\]

\(u,v\) 是预测像素，\(f_x,f_y\) 是水平和垂直焦距，\(c_x,c_y\) 是主点。矩阵形式为：

\[
\lambda
\begin{bmatrix}u\\v\\1\end{bmatrix}
=\mathbf{K}\left(\mathbf{R}\mathbf{P}_w+\mathbf{t}\right).
\]

OpenCV 可用时，代码调用其投影函数并消费可选畸变系数；不可用时退回上述针孔公式。投影落在图像外或产生非有限值时，不进入几何门控。

AirSim 设置给出图像宽度 \(W\)、高度 \(H\) 和水平视场角 \(\theta\) 时，当前辅助函数使用：

\[
f_x=f_y=\frac{W}{2\tan(\theta/2)},\qquad
c_x=\frac{W}{2},\quad c_y=\frac{H}{2}.
\]

该 FOV 水平口径仍需对具体 AirSim 版本和图像类型做真实标定，不是通用相机定律。

### 3.4 协方差投影

针孔模型对世界位置的雅可比矩阵为：

\[
\mathbf{J}=
\begin{bmatrix}
f_x/Z_c & 0 & -f_xX_c/Z_c^2\\
0 & f_y/Z_c & -f_yY_c/Z_c^2
\end{bmatrix}\mathbf{R}.
\]

像素协方差传播为：

\[
\boldsymbol{\Sigma}_{px}
=\mathbf{J}\mathbf{P}\mathbf{J}^{\mathsf T}
+\mathbf{R}_{meas}+\epsilon\mathbf{I}_2.
\]

\(\boldsymbol{\Sigma}_{px}\) 是二维投影协方差，\(\mathbf{R}_{meas}\) 是相机像面量测协方差，\(\epsilon=10^{-6}\) 是默认数值正则项。协方差不是仅供日志的装饰字段，它直接决定马氏门的方向和尺度。

### 3.5 混合分辨率

每个 `(resource_id, camera_id)`（资源与相机联合键）保存独立图像尺寸。固定像素门限按参考分辨率 \(640\times480\) 的图像对角线缩放：

\[
s=\frac{\sqrt{W^2+H^2}}{\sqrt{640^2+480^2}}.
\]

友方中心距离、侦察线索距离、角速度标准差和重获取搜索半径均乘以 \(s\)。完全分布式的跨视角辅助算法则把像素中心、协方差和边界框面积归一到 \(640\times480\) 参考平面后比较。该实现已支持同一运行中混用 \(1920\times1080\) 与 \(3840\times2160\) 相机，但并不自动证明远距检测质量。

### 3.6 双时间戳与证据年龄

D5 区分：

- `measurement_timestamp`（量测时间戳）：图像/检测实际对应的时刻；
- `arrival_timestamp`（到达时间戳）：该证据进入处理链的时刻；
- `exposure_timestamp`（曝光时间戳）：相机曝光时刻，缺省时回退到量测时间；
- `measurement_age_s`（量测年龄）：到达时间减量测时间。

默认 `AssociationConfig.max_measurement_age_s`（关联器最大量测年龄）为空，因此常规实测候选的绝对时效阈值必须由 runtime 配置或后续 D7 门控明确给出；不能把“字段存在”写成“默认已启用严格时效拒绝”。另一方面，丢失/预测证据默认最多保留 0.25 秒，超过后保持 `reacquire` 并把原因改为 `terminal_visual_evidence_expired`（末端视觉证据过期）。D7 前置建议另有默认 0.35 秒量测年龄上限。

## 4. 默认主线关联算法

### 4.1 几何门控

对本地像素量测 \(\mathbf{z}=[u_l,v_l]^{\mathsf T}\) 和全局航迹预测像素 \(\hat{\mathbf{z}}\)，残差为：

\[
\mathbf{r}=\mathbf{z}-\hat{\mathbf{z}}.
\]

平方马氏距离为：

\[
d_M^2=\mathbf{r}^{\mathsf T}
\boldsymbol{\Sigma}_{px}^{\dagger}\mathbf{r},
\]

其中 \(\dagger\) 表示伪逆。默认门限是：

\[
d_M^2\le 9.21.
\]

该值对应二维卡方分布约 99% 概率门。门外候选代价被设为大数 \(10^{12}\)，不参与后续选择。门控使用检测框中心，不使用 AirSim 对象身份或真值映射。

### 4.2 候选总代价

门内候选总代价为：

\[
C=d_M^2+C_{rate}+C_{class}+C_{quality}+C_{friend}+C_{recon}.
\]

各项物理意义如下。

#### 像面变化率一致性

\[
C_{rate}=w_r
\frac{\lVert\dot{\mathbf{z}}_l-\dot{\mathbf{z}}_g\rVert_2^2}
{(\sigma_r s)^2}.
\]

\(\dot{\mathbf{z}}_l\) 是本地像面变化率，\(\dot{\mathbf{z}}_g=\mathbf{J}\mathbf{v}\) 是全局速度预测的像面变化率。默认 \(w_r=1\)、\(\sigma_r=40\) 像素每秒，\(s\) 是分辨率尺度。

#### 类别一致性

未知类别不加分也不扣分。`uav`、`drone`、`intruder` 等检测标签先统一为“无人机”对象类别；统一仅处理对象类别，不推断友方或对抗属性。两个已知类别不一致时，默认代价增加 16。

#### 质量与历史

\[
C_{quality}=2(1-q)+0.5\max(0,2-h),
\]

其中 \(q\in[0,1]\) 是本地质量，\(h\) 是 MOT 历史帧数。该项让低质量和短历史候选更难锁定，但不会替代后续硬门限。

#### 身份冲突

- 已验证友方重叠：代价增加 \(10^6\)，并由决策逻辑直接输出 `hold`；
- 疑似伪造、过期或未验证的友方重叠：代价增加 6，候选即使最佳也输出 `ambiguous`；
- 无声明或身份未知：身份代价为零，仍只按几何和质量判断，不推断为对抗目标。

身份重叠可由相同本地轨迹标识、边界框 IoU 至少 0.05，或中心距离不超过默认 \(20s\) 像素判定。`IdentityChecker.max_age_s`（身份声明最大年龄）默认 2 秒。

#### 二级侦察线索

适用的二级线索可给候选一个负代价：

\[
C_{recon}=-2q_c,
\]

其中 \(q_c\) 是线索置信度。线索中心与本地候选距离需不超过默认 \(30s\) 像素，并同时满足：全局航迹一致、资源作用域一致、年龄不超过 1 秒、目标相机帧一致，且跨相机线索已明确重投影。线索只能改善候选排序，不能越过授权、版本、友方、稳定性或执行门控。

### 4.3 唯一候选与置信度

把门内候选按总代价升序排列，最佳和次佳代价分别记为 \(C_1,C_2\)，间隔为：

\[
\Delta C=C_2-C_1.
\]

只有一个候选时，间隔视为无穷大。正常锁定默认要求：

- \(C_1\le14\)；
- \(\Delta C\ge3\)；
- 本地质量 \(q\ge0.6\)；
- MOT 历史 \(h\ge2\)；
- 当前状态必须是 `measured`；
- 无友方冲突、旧计划、版本冲突或执行合同阻断。

当前置信度为：

\[
\gamma=
\exp\left(-\frac{1}{2}\min(100,d_M^2)\right)
q\min\left(1,\frac{h}{5}\right).
\]

有限间隔时的歧义分数为：

\[
a=\frac{1}{1+\max(0,\Delta C)}.
\]

只有一个候选时 \(a=0\)。这些是解释性分数，最终状态仍由硬门控决定。

### 4.4 一对多与多对多匹配

`TerminalAssociator.decide()`（单资源末端决策）只评估 D3 已分给该资源的一个全局航迹，不允许本地候选把分配改成另一个全局航迹。默认 main runtime 对每个资源-目标分配分别调用该方法。

几何批量验证和检测到既有全局航迹注册会构建多航迹、多检测代价矩阵。SciPy 可用时使用匈牙利线性和分配，保证每行每列至多选择一次；不可用时按代价排序执行确定性贪心唯一匹配。无论哪种后端，都只能关联到输入中已经存在且有上游绑定的全局航迹。

### 4.5 可选联合概率数据关联

当多个全局航迹的投影协方差椭圆明显重叠、多个本地候选的最佳/次佳代价长期接近时，可选联合概率数据关联（Joint Probabilistic Data Association，JPDA）保留“一个量测可能来自多个航迹”的概率，而不是立即作唯一硬匹配。概念上，对候选事件计算归一化概率 \(\beta_{jm}\)，并用概率加权残差形成关联证据：

\[
\bar{\mathbf r}_j=\sum_m \beta_{jm}\mathbf r_{jm}.
\]

D5 对该路线的实施约束是：

- JPDA 只能作为 `DataAssociator` 风格的可插拔研究对照，不能绕过现有几何门、版本、授权、友方和稳定窗口；
- 概率未形成显著优势时必须输出 `ambiguous`，不能用最大概率强行换绑；
- 输入和输出仍引用既有 `global_track_id`，不允许用联合事件生成新的全局身份；
- 准入前必须用同一真实 AirSim 回放比较错误锁定、身份切换、延迟和内存，并证明收益大于实时性代价。

当前代码没有在线 JPDA 实现。默认单资源决策采用面向已分配目标的候选排序，批量检测到航迹注册采用匈牙利算法；文档中的 JPDA 仅表示明确预留的升级方向。

### 4.6 选型理由

当前主线选择“时间预测 + 针孔投影 + 协方差传播 + 马氏门控 + 可解释代价”，原因是：

1. 能直接消费 D1/D2 已有三维状态和协方差，不建立第二套身份系统；
2. 门限具有统计含义，比固定像素半径更能适应距离和航迹质量变化；
3. 每个拒绝可以落到投影、门控、唯一性、质量、身份、版本或时效的具体原因；
4. 对当前 AirSim 数据规模计算量可控，且没有训练依赖；
5. 错误锁定成本高于暂不锁定，因此保守四态比强制每帧匹配更符合模块职责。

## 5. 状态机、迟滞与重获取

### 5.1 四态判定

| 状态 | 进入条件 | 典型原因 | 下游语义 |
| --- | --- | --- | --- |
| `locked` | 唯一门内实测候选通过代价、质量、历史、身份、版本和执行门控 | `unique_candidate_inside_gate`（门内唯一候选） | 仅表示 D5 视觉关联成立，仍需 D7 独立门控 |
| `ambiguous` | 有候选但唯一性、质量、历史、身份可信度或时序稳定性不足 | 候选间隔不足、质量过低、历史太短、身份未验证 | 继续观测或请求二级线索 |
| `hold` | 当前视觉证据暂停，或计划/身份安全门控阻断 | bbox/时序不稳、备用未激活、旧计划、版本/授权冲突、友方重叠 | 普通 hold 只请求线索；明确安全冲突才报告/仲裁，均不执行视觉接管 |
| `reacquire` | 分配航迹缺失、投影无效、无门内候选或证据丢失 | 目标出图、遮挡、检测缺失 | 进入受限重获取，不得本地换绑 |

这不是一个允许任意跳转的控制状态机，而是每帧决策加每资源/相机/全局航迹历史。历史键由资源、稳定相机作用域和中心全局航迹组成，避免不同相机历史串流。

### 5.2 正常迟滞

候选历史默认保留最近 32 条记录。稳定窗口参数为 3 帧窗口内至少 2 次连续、可锁定的同一本地候选。常规连续锁定不要求每帧重新积累两帧；该窗口主要约束丢失后的恢复和注册稳定支持。

一致性摘要另按 `(resource_id, assigned_global_track_id)`（资源与分配全局航迹联合键）维护连续状态。相同资源继续执行相同全局航迹时，D3 计划版本正常递增不会清空连续计数；真正换目标才进入新窗口。这解决了滚动版本把真实视觉连续性错误打断的问题。

### 5.3 主动重获取

当主马氏门内没有候选时，代码可以在全局航迹预测周围做受限搜索。搜索半径为：

\[
r=\max(45s,3\sigma_{max},0.75d_{bbox})+r_v.
\]

\(\sigma_{max}\) 是投影协方差最大特征值平方根，\(d_{bbox}\) 是上次锁定边界框对角线，\(r_v\) 是按预测像面速度和失锁时间增加的项，最大增加 \(60s\) 像素。

重获取候选默认还需满足：质量至少 0.55、历史至少 2 帧、旧锁定历史不超过 2 秒、边界框面积比位于 0.25 到 4 之间。多个重获取候选的分数间隔至少为 1；恢复为 `locked` 前需达到 3 帧窗口内 2 次稳定支持。若上一帧状态是 `reacquire`，主线恢复锁定所需最佳/次佳代价间隔从 3 提高到 4。

即使本地轨迹标识未变化，重获也不能继承此前授权；即使本地轨迹标识变化，D5 也只能重新支持原分配全局航迹。任何重获候选与已验证或可疑友方声明重叠时，保守输出 `hold`。

### 5.4 丢失证据的失效

当前本地轨迹缺失时，D5 保留最后锁定的匿名相机本地连续性用于说明 `lost/reacquire`，但不输出 coast（无量测外推锁定）状态。默认 0.25 秒后，缺失证据显式过期并保持失败关闭。项目中 D7 对短丢检的有界预测是 D7 自己的能力，不能写成 D5 已实现 coast 或滤波跟踪。

### 5.5 一致性摘要阈值

`TerminalConsistencyTracker`（末端一致性跟踪器）默认使用：

- 锁定置信度至少 0.6、歧义不大于 0.5；
- 锁定年龄至少 1 秒，或候选间隔无穷大/至少 3；
- 连续 5 帧 `ambiguous` 后建议请求二级线索；
- 连续 2 帧普通 `hold` 后建议请求二级线索；
- 连续 5 帧 `reacquire` 后建议请求二级线索/重获取；
- verified friend、spoof、duplicate 或 assignment authorization/version 冲突立即报告冲突或仲裁；
- 本地最佳证据连续 3 帧与分配冲突后建议仲裁。

这些建议只形成 `observe`（继续观测）、`request_secondary_cue`（请求二级线索）、`report_conflict`（报告冲突）或 `arbitrate`（请求仲裁）元数据，不执行动作。

## 6. 身份、版本和全局标识安全

### 6.1 友方身份规则

当前身份检查器只做正向友方确认：

1. 声明需在默认 2 秒有效期内；
2. 声称友方但签名无效时标为疑似伪造；
3. 已验证友方与任何门内候选重叠时直接 `hold`；
4. 过期、未验证或疑似伪造的友方重叠只允许 `ambiguous/hold`，不能提升为锁定；
5. 没有身份声明时保持未知，不自动赋予对抗属性。

当前解析的是离线仿真字典，不是实际远程身份广播、密钥、证书或视觉标签链路。

### 6.2 版本和执行合同

D5 在锁定前依次检查：

- `assignment_version`（分配版本）必须与 `track_version`（航迹版本）一致，除非调用方显式关闭该检查；
- 同一资源和计划只接受不低于已见最高值的 `plan_version`（计划版本），下降版本返回 `hold`；
- `authorization_state`（授权状态）必须属于已批准集合；
- observer（观察成员）不可执行；reserve/retry（备用/重试成员）未激活时只能保留视觉准备证据，不能锁定执行；
- 当前时间必须位于可选到达窗口内；
- 资源、计划、联盟、目标和版本作用域必须与当前上游合同一致。

版本水位只在通过授权且找到有效分配航迹后更新，因此非法输入不能抬高水位并阻断合法计划。

### 6.3 逐主用资源合同

显式满足 `terminal_authorization_scope=per_primary`（逐主用资源末端授权作用域）且 `arrival_coordination_required=false`（不要求到达协同）时，各已授权、已激活主用资源可独立报告锁定，不要求另一个主用资源同帧锁定或同时到达。

该合同只取消共同到达/共同锁定要求，不取消以下条件：当前资源和目标绑定、计划与联盟版本、执行门控、实测本地轨迹、友方冲突、重复锁定风险以及 standby reserve（待命备用）不计完成。`per_primary_terminal_evidence()`（逐主用资源证据函数）的参数只能核对合同，不能覆盖数据对象中的合同，也不授予控制权限。

### 6.4 全局标识不变式

全局身份安全由多层共同保证：

1. `GlobalTrack` 是冻结数据结构；
2. D5 只寻找与 `assigned_global_track_id` 相同的输入航迹；
3. 单资源决策不在其他全局航迹中选择替代目标；
4. 输入和输出前后会断言全局航迹标识序列未改变；
5. `TerminalAssociation` 拒绝 `truth_identity_used=true`（在线使用真值身份）；
6. 本地轨迹标识按资源/相机命名空间汇总，绝不提升为全局标识；
7. 无上游 `GlobalTrackBinding` 时，检测只保留为本地证据并报告 `no_global_binding`（没有全局绑定）。

## 7. 跨视角、联盟与二级节点证据

### 7.1 已实现的跨视角摘要

`TerminalObservationBus`（末端观测总线）把各资源已经独立完成的 D5 决策按既有全局航迹标识分组。本地轨迹键写成 `资源/相机:本地轨迹`，防止不同相机恰好使用相同本地编号时被误合并。

总线无参数调用保留全历史离线兼容行为；main 的当前帧路径使用快照作用域：按当前时间、最大年龄、计划标识和计划版本过滤，再为每个资源保留最新时刻的同帧观测。这样历史锁定不会冒充当前并发锁定。

当前摘要能表达：

- 单视角支持；
- 多资源对同一既有全局航迹的多视角支持；
- 同一本地轨迹同时支持多个全局航迹的冲突；
- 单资源同帧锁定多个本地轨迹的冲突；
- 合法的计划内协同多锁；
- 超出需求、版本不一致、联盟外或未授权成员造成的重复锁定风险。

### 7.2 合法协同锁与重复锁定风险

多个资源同时锁定同一全局航迹不一定是错误。如果所有锁定具有完整且相同的计划/联盟合同、资源作用域正确、成员已授权激活、人数不超过 `required_resource_count`（所需资源数），则标记为 `planned_cooperative_lock`（计划内协同锁），不标记重复风险。

以下情况标记 `duplicate_terminal_lock_risk`（重复末端锁定风险）或联盟冲突：

- 缺少计划或联盟版本；
- 合同签名不一致；
- 资源不在分配作用域；
- 成员未激活或执行门控失败；
- 锁定资源数超过需求；
- 单资源多本地锁定；
- 同一本地轨迹被绑定到多个全局航迹。

D5 只上报风险。资源去冲突、主备调整或计划重发由 D3/D4 负责。

### 7.3 联盟稳定窗口

联盟视觉摘要默认要求每个已授权 active primary（激活主用资源）至少连续 2 帧保持执行锁定。standby reserve 的本机视觉匹配可记录为准备就绪，但不计入主用完成。

同一联盟身份和相同主用成员集合下，计划/联盟版本严格单调增加时可安全延续稳定计数；成员变化、目标变化、旧版本重放、友方冲突、重复风险或过期证据都会重置。对于逐主用资源且不要求到达协同的合同，不再计算共同同帧窗口。

### 7.4 检测到既有全局航迹注册

`register_local_visual_tracks_to_global_tracks()`（检测到既有全局航迹注册函数）消费：

- 上游全局航迹；
- D2/D3 既有绑定；
- 每相机 `CameraLocalTrackBatch`（相机本地轨迹批）；
- 相机模型、量测时间、到达时间和像素协方差。

它输出逐候选投影像素、边界框中心、像素误差、马氏距离、门控结果、是否被唯一分配、拒绝原因和稳定支持。默认稳定规则同样是 3 帧内至少 2 次门控通过。即时 gate pass（门控通过）只是候选，达到稳定窗口后才进入 `stable_cross_view_associations`（稳定跨视角关联）。

### 7.5 二级节点证据

二级相机原始像素不能直接与拦截相机像素比较。`ReconImageCue` 必须携带目标本地帧，或明确声明已重投影到该本地相机。其资源作用域、全局航迹、时间新鲜度和图像帧均需匹配。

`SecondaryFrameAssociationEvidence` 强制使用同一 `frame_id`（帧标识）和时间容差内的相机覆盖与注册候选。历史候选只计入“被忽略数量”，不能把 episode（完整运行片段）聚合值伪装成实时接管证据。

### 7.6 完全分布式辅助融合

代码已实现 `TerminalCrossViewFusion`（末端跨节点视觉融合器），可在没有完整中心几何时用时间偏差、像素/视向、像面变化率、边界框尺度变化、类别、置信度、观测协方差和相机位姿质量构造仅元数据（metadata-only）跨节点假设。默认至少 2 个资源支持、置信度至少 0.55、歧义不大于 0.55 才可能输出 `locked`。

缺少当前全局航迹标识时只能输出 `hypothesis_only`（仅假设）；过时标识、友方冲突、身份冲突或重复锁定风险会输出 `hold/ambiguous`。该路径已实现但属于 D4 完全分布式降级的辅助证据，不是默认中心在线主线，也不是完整多相机三维融合。

## 8. D7 视觉导引前置证据

D5 的 `annotate_visual_png_handoff()`（视觉比例导航导引交接注释函数）不改变关联状态和全局标识，只在现有决策上增加建议字段。默认检查：

- D5 决策为 `locked`；
- 当前分配全局航迹一致；
- 无友方冲突和重复锁定风险；
- 量测年龄不超过 0.35 秒；
- LOS 变化率可用；
- 同一本地轨迹至少有 4 帧边界框历史；
- 边界框面积变异系数不大于 0.30；
- 当前边界框面积占图像面积至少 0.0008；
- 检测延迟、预计剩余时间和 D7 机动裕度满足配置。

边界框面积比例 \(a_k\) 的变异系数为：

\[
c_v=\frac{\operatorname{std}(a_k)}{\operatorname{mean}(a_k)}.
\]

稳定分数为：

\[
s_{bbox}=\operatorname{clip}\left(1-\frac{c_v}{0.30},0,1\right).
\]

距离分区默认是 30 至 50 米准备、15 至 30 米交接、5 至 15 米近距优先。预计剩余时间采用距离除以闭合速度。所有数值只针对当前 AirSim 大目标基线，不是通用物理常数。

即使 D5 建议交接，D7 仍必须独立检查相机、LOS、机动和当前计划合同。D5 的建议不是控制授权；D7 也不得选择另一个本地目标替换全局航迹。

## 9. 默认主线、可选/离线能力与未实现能力

### 9.1 当前默认在线主线

截至 2026-07-13，main runtime 的 `detection_backend`（检测后端）默认值仍为 `airsim`，即：

```text
AirSim simGetDetections 检测元数据
  -> 去除对象身份含义的相机本地检测
  -> 检测框中心与每相机 CameraModel
  -> D2/D3 既有 GlobalTrack/Assignment
  -> TerminalAssociator 几何关联
  -> ObservationBus / Consistency / D7 handoff metadata
```

在线本地轨迹标识由相机本地跟踪语义产生；AirSim 对象标识只允许在在线结果形成后进入离线评价映射。主线关联来源固定记录为 `geometric_detect`（几何检测关联）。

### 9.2 已实现但非默认的辅助或离线能力

| 能力 | 已实现状态 | 不能宣称的内容 |
| --- | --- | --- |
| YOLOv8 + ByteTrack/BoT-SORT adapter（适配器） | 可读取连续红绿蓝（Red Green Blue, RGB）图像，按资源/相机隔离跟踪器状态，输出本地视觉轨迹；依赖不可用时可显式返回 unavailable（不可用）或使用 IoU 跟踪回退 | 18 组筛选无候选准入，不能写成默认后端或已通过质量验收 |
| `NativeMotAdmissionMonitor`（原生 MOT 准入监视器） | 已实现逐流统计、失败关闭准入、在线结果后真值评分和重置接口 | 监视器具备不等于任一后端已经准入 |
| AirSim 几何批量关联 | 已实现多航迹/多检测矩阵、匈牙利分配和离线真值评价分离 | 不等于真实多相机三维融合 |
| 跨视角总线摘要 | 已实现按既有全局航迹汇总、快照过滤和合法联盟多锁判断 | 不做三角定位或融合新航迹 |
| 完全分布式元数据融合 | 已实现跨节点假设和保守状态 | 不是默认中心路径，不创建全局身份 |
| OpenCV `calibrateCamera`（相机标定函数）/`solvePnP`（PnP 求解函数）合成对照 | 隔离式 P2 benchmark（基准实验）已实现，在线模块不导入、不写回相机模型 | 不代表真实 AirSim 标定、在线位姿更新或硬件标定闭合 |
| 确定性鲁棒性矩阵 | 已实现交叉、部分重叠、丢检、本地标识变化、外参漂移、时间偏差和旧计划重放用例 | 不能替代真实连续图像和物理闭环 |

IoU fallback（IoU 跟踪回退）明确是失败对照：任何回退帧都不计入原生 MOT 活跃率，默认准入要求回退帧数为零。

### 9.3 尚未实现或尚未闭合

以下能力不能写成当前主线已实现：

1. 带多相机位姿的三维视向三角化、可观测度分析和融合协方差；
2. 真实图像标定采集、PnP RANSAC、联合优化和在线外参漂移估计；
3. 真实二级侦察原始图像到各拦截相机的完整在线重投影链；当前线索主要来自 fixture（测试夹具）或预处理结果；
4. 深度关联度量增强的简单在线实时跟踪算法（Simple Online and Realtime Tracking with a Deep Association Metric, Deep SORT）、ReID、长遮挡身份恢复及其真实小目标质量验收；
5. 机器人操作系统 2（Robot Operating System 2, ROS 2）的 `tf2`（坐标变换树工具）和 `message_filters`（带时间戳消息同步工具）接入；
6. 真实远程身份广播、密钥/证书和视觉标签适配器；
7. 真实通信带宽、时钟漂移、认证链和实机硬件级验证；
8. D5 自身的 coast、卡尔曼滤波、轨迹创建、目标重分配、降级仲裁或导引控制；
9. YOLOv8/ByteTrack/BoT-SORT 的正式准入和 30/50 米检测能力；
10. M5N2 至少 8/10 协同完成率的系统级 P1 验收。

## 10. 与其他模块及 main runtime 的接口关系

### 10.1 D1 与 D2

D1 提供三维运动学和协方差来源；D2 维护全局航迹连续性和中心全局航迹标识。main adapter 把 D2 平面状态与 D1 缓存的高度/垂向速度组合成 D5 三维航迹。D5 不修改 D1/D2 状态，也不计算系统级 IDSW。

### 10.2 D3

D3 提供版本化分配计划、资源-目标绑定、联盟角色、需求数、激活态和到达窗口。D5 是只读合同消费者：版本或作用域冲突时保守拒绝，而不是就地修复计划。合法协同多锁和超额锁定风险摘要返回给 D3/D4，但 D5 不调整计划。

### 10.3 D4

D4 消费四态决策、连续非锁定帧、跨视角支持、重复风险、二级覆盖、线索新鲜度和建议动作。中心或二级失效时，D5 的联盟摘要还检查 D4 提供的 committed/executing（已提交/执行中）状态、时期、租约和必要成员确认。D5 不根据这些证据自行降级。

### 10.4 D6

D6 消费运行时记录、几何对日志、跨视角摘要、逐主用资源漏斗和 MOT 准入汇总。在线真值使用计数、全局标识改写计数、错误锁定、歧义、门控拒绝、检测查准率/召回率和本地 IDSW 都应保持分层统计。D5 不生成系统最终报告。

### 10.5 D7

D7 只有在 D5 `locked`、分配一致、当前实测、无友方/重复风险且交接证据满足时，才可进一步评估视觉 PNG。D7 保留相机、LOS、机动、时效和控制合同的独立门控。`ambiguous/hold/reacquire/hypothesis_only` 均不得被解释为可执行视觉目标。

### 10.6 main runtime

main 负责：

- AirSim Blocks 启停、reset-separated episodes（重置分隔的运行片段）和运行顺序；
- `--drone-count N`（无人机数量参数）和动态资源/目标规模；
- 相机设置、实际相机位姿、图像/检测采集和时间戳；
- 每个运行片段重置 D5 关联历史、YOLO/MOT 流状态和准入监视器；
- AirSim 真值可由仿真编排用于构造明确标注的输入 fixture，并可交给 D6/离线评价；不得进入 D5 在线关联代价、Hungarian 选择或稳定窗口；
- 日志、表格、曲线和总报告。

D5 算法按输入数组长度运行，2 对 2、5 对 5 和 M5N2 只是基线场景名，不是硬编码上限。

### 10.7 代码实施映射

| 实施文件 | 主要职责 | 在线能力边界 |
| --- | --- | --- |
| `models.py` | 定义全局航迹、相机、本地视觉轨迹、身份声明、末端决策和分布式证据数据合同 | 数据结构不授予分配或控制权限 |
| `geometry.py`、`airsim_geometry.py` | 航迹预测、针孔投影、像面协方差、AirSim 相机内外参转换与离线几何评分 | 在线关联不读取 AirSim 真值身份 |
| `associator.py` | 构建几何/运动/类别/质量/身份/侦察代价并输出四态决策 | 只评估当前分配全局航迹 |
| `cross_view_registration.py` | 按每相机模型把本地检测注册到已有 D2/D3 全局绑定，执行唯一匹配和稳定窗口 | 不创建、重写或本地换绑全局航迹标识 |
| `observation_bus.py`、`coalition_visual.py`、`per_primary_evidence.py` | 形成快照跨视角摘要、合法协同锁、逐主用资源漏斗和重复风险 | 只汇总证据，不重规划联盟 |
| `secondary_frame_evidence.py` | 形成二级侦察节点同帧覆盖、检测和注册证据 | 历史聚合值不能冒充当前帧证据 |
| `terminal_cross_view_fusion.py` | 完全分布式时融合双时间戳、像素/视向、边界框历史和姿态质量 | 无新鲜规范身份时只输出临时假设 |
| `identity.py` | 解析模拟合作身份声明并执行正向友方冲突检查 | 尚非真实 Remote ID、密钥或证书适配器 |
| `visual_handoff.py` | 给 D7 注释视觉比例导航导引前置证据 | 建议字段不是控制许可，不改变 D5 决策 |
| `yolo_mot_adapter.py`、`native_mot_admission.py` | 接入 YOLOv8、ByteTrack、BoT-SORT，并执行原生多目标跟踪准入统计 | 当前未通过 18 组质量准入，默认仍用 AirSim 检测元数据 |
| `p2_geometry_benchmark.py` | 隔离式 OpenCV 标定和 PnP 合成对照 | 不导入默认在线 runtime，不回写在线相机模型 |

## 11. 当前运行流程

默认单资源决策步骤如下：

1. 从当前 D3/D4 合同取得分配全局航迹标识、资源、计划版本、联盟版本和成员状态；
2. 拒绝低于已接受水位的旧计划、未授权合同和缺失分配航迹；
3. 检查航迹版本与分配版本；
4. 用本地量测时刻预测中心航迹并膨胀协方差；
5. 用当前资源的相机内外参投影，拒绝相机后方、图像外或非有限投影；
6. 从当前资源/相机批次取得实测本地轨迹，不借用其他相机检测；
7. 计算每个候选的马氏距离、像面变化率、类别、质量、身份和二级线索代价；
8. 无门内候选时执行受限重获取；有已验证友方门内候选时直接 `hold`；
9. 计算最佳/次佳间隔，应用成本、质量、历史、量测时效和稳定性门控；
10. 应用成员角色、激活态和到达窗口执行门控；
11. 形成 `TerminalAssociation`，写入量测/到达时间、投影、协方差、门控和拒绝原因；
12. 通过总线形成当前快照跨视角摘要和一致性摘要；
13. 注释 D7 前置证据，但不改变 D5 决策状态；
14. 仿真编排可用真值构造明确标注的输入 fixture，D6 可用真值做离线评价；两者均不得把 truth identity 注入 D5 在线关联链。

## 12. 验证结果

### 12.1 模块回归

2026-07-14 D5 最新全量结果为：

```text
241 passed
```

2026-07-13 的 `232 passed` 保留为历史基线；本次状态分级实现与文档同步后已重跑全量。命令为：

```bash
pytest -q research_modules/d5_terminal_association/tests
```

### 12.2 M5N2 协同视觉闭环

当前场景为 5 个资源、2 个目标，高威胁目标采用 2 个激活主用资源和 1 个待命备用资源；每个主用资源独立通过 D3/D4/D5/D7 门控，不要求同时到达。

截至 2026-07-13：

- 共形成 120 条 active-primary（激活主用资源）证据；
- 120 条均记录为可见；
- 其中 74 条形成 D5 关联/锁定证据；
- 最佳参数组合的联盟完成率为 5/10，低于 8/10 验收线；
- 主要失败原因为 `d5_not_locked`（D5 未锁定）和 `terminal_detection_acquisition_timeout`（末端检测获取超时），少量为 `bbox_area_too_small`（边界框面积过小）；
- 待命备用资源越权执行为 0；
- 全局航迹标识改写为 0；
- 在线真值身份使用为 0。

结论是“逐主用资源合同和诊断接口已闭合，但系统级协同视觉性能未闭合”。不能把 5/10 写成 M5N2 已验收，也不能通过取消版本、身份或稳定窗口门控提高表面完成率。

### 12.3 原生 MOT 18 组筛选

真实 AirSim 筛选矩阵为：

- 图像分辨率 1920×1080；
- FOV 90 度；
- 距离 20/30/50 米；
- 检测置信门限 0.10/0.20/0.30；
- ByteTrack 和 BoT-SORT 两种后端；
- 共 18 个筛选算例，每个 101 帧。

结果为：

| 后端 | 20 米原生活跃率 | 20 米本地连续性 | 本地 IDSW | 去预热 P95 延迟 | 检测查准率/召回率 | 30/50 米 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| ByteTrack | 1.0 | 1.0 | 0 | 约 7.4 毫秒 | 约 0.30 至 0.32 | 无有效检测 |
| BoT-SORT | 1.0 | 1.0 | 0 | 约 16.2 毫秒 | 约 0.26 至 0.33 | 无有效检测 |

20 米结果只证明受控条件下原生 tracker（跟踪器）能连续运行且延迟满足筛选预算。由于边界框离线查准率/召回率明显低于准入线，18 个候选均未准入，200 帧双相机确认算例数为 0。默认在线后端继续是 AirSim 检测元数据。

默认准入条件包括：至少 100 帧、原生活跃率至少 0.95、IoU 回退帧为 0、本地连续性至少 0.90、本地 IDSW 不超过 1、P95 不超过 100 毫秒、查准率至少 0.90、召回率至少 0.80，并要求在线结果后真值帧覆盖完整。当前结果不满足后两项及远距检测要求。

### 12.4 二级节点和跨视角校准证据

截至当前状态，较早的 60 算例 D4/D5 校准扫描已证明基础检测到既有全局航迹注册能形成可审计结果：投影有效率均值为 1.0，`not_registered_count`（未注册计数）为 0，平均跨视角关联数为 4.417。与此同时，二级网络同帧全目标覆盖率均值只有 0.0231，平均覆盖比例为 0.7059。

因此“局部检测可注册”已经有证据，“二级网络同帧拥有完整态势”仍未成立。二者不能合并成一个成功结论。

### 12.5 隔离式 OpenCV P2 对照

默认随机种子 7 的合成外参扰动对照约得到：投影误差从 24.0 像素降到 1.63 像素，真候选门控接受率从 0 升到 1，构造的假候选接受率从 1 降到 0。

该实验在所有几何门控完成后才附加离线真值标签，且在线 D5 不导入该模块、不写回 `CameraModel`。结果只证明合成条件下 PnP 位姿恢复对投影误差敏感，不能代表真实相机标定、AirSim 在线 PnP 或物理闭环。

## 13. 已解决问题

截至 2026-07-13，D5 已关闭的关键实现问题包括：

1. AirSim 对象/实体/真值字段进入在线本地身份或全局绑定的泄漏路径；
2. 仿真实体名称曾出现在本地轨迹标识中的端到端污染；
3. 活动重获取路径未重新检查友方声明的问题；
4. 多相机本地跟踪器状态可能串流的问题，现按资源/相机隔离并支持逐流和全运行片段重置；
5. 总线全历史观测污染当前重复锁定判断的问题，现支持时间与计划快照；
6. 合法联盟协同多锁曾被一律标为重复风险的问题；
7. 计划版本滚动错误清空同一资源/目标连续窗口的问题；
8. 共同窗口没有复用安全跨版本连续尾段的问题；
9. `per_primary`（逐主用资源）合同、到达协同字段和逐资源漏斗没有贯通的问题；
10. 1080 行与 2160 行相机混用时固定像素门限、协方差和边界框面积尺度不一致的问题；
11. 无人机类别同义标签产生错误类别惩罚的问题；
12. YOLO/MOT 在线结果、离线 AirSim 参考框和本地轨迹数量混为同一检测计数的问题；
13. 后到真值可能反向影响在线结果或重复评分的问题；
14. 二级节点聚合证据可能冒充单决策时刻证据的问题；
15. 丢失/预测本地轨迹产生锁定的风险，现由数据结构和决策逻辑双重拒绝。

这些修复关闭的是合同、隔离和可审计性问题，不自动关闭检测召回、稳定锁定或物理完成率问题。

## 14. 剩余局限与下一步证据要求

### 14.1 当前最高优先级局限

1. **第二主用资源稳定获取不足。** M5N2 的最高优先级仍是持续检测、稳定边界框和连续实测锁定，目标是最佳组合至少 8/10。
2. **检测框口径未对齐。** 20 米 YOLO 框与 AirSim 离线参考框可能存在定义、尺度或时间偏差，尚不能唯一归因。
3. **远距召回缺失。** 当前本地权重在 30/50 米无有效检测，不能靠直接降低在线几何门或身份门关闭缺口。
4. **真实外参/时间同步未完成多随机种子标定。** 强类型相机几何字段在部分历史运行中仍为 unavailable，不能用仿真真值位姿补齐。
5. **完整多视角三维融合未实现。** 当前跨视角主线是“独立单相机关联后的证据摘要”，不是三角定位或联合状态估计。
6. **二级完整覆盖不足。** 基础注册成功不等于网络同帧覆盖全部目标。

### 14.2 后续验证不得放宽的条件

后续提高性能时必须继续保持：

- 在线真值身份使用为 0；
- 全局航迹标识改写为 0；
- 旧计划和旧联盟版本拒绝；
- 友方重叠失败关闭；
- standby reserve 不计主用完成；
- 丢失/预测轨迹不产生 D5 锁定；
- D7 保留独立相机、LOS、时效和机动门控；
- D4 保留独立降级仲裁；
- 任何离线阈值扫描不能直接替换在线安全门限。

### 14.3 所需证据

后续收敛应至少提供：

- 按资源、相机、目标和时间对齐的检测可用率、投影有效率、马氏门通过率、锁定率和稳定锁定率；
- 20/25/30/40/50 米逐距离的边界框尺度、中心归一化误差、宽高/面积比、包含关系和前后各一帧时间对齐诊断；
- 候选 MOT 配置至少 10 个随机种子、每组不少于 100 帧的确认；
- 真实相机内外参、曝光/量测/到达/姿态时间差、重投影误差和漂移告警；
- 将持续检测失败、D5 未锁定、D7 门控拒绝和控制闭环不足分层报告，不能用一个“未完成”字段合并。

## 15. 中文术语表

| 中文术语 | 代码/英文对应 | 本文含义 |
| --- | --- | --- |
| 中心全局航迹标识 | `global_track_id` | 由中心 D2 拥有并维护的系统级航迹身份 |
| 本地视觉轨迹标识 | `local_track_id` | 仅在一个资源/相机流内有效的检测跟踪身份 |
| 末端关联 | terminal association | 把当前本地视觉候选保守地支持到既有中心分配航迹 |
| 实测轨迹 | `measured` | 当前帧存在实际检测量测的本地轨迹 |
| 预测轨迹 | `predicted` | 只有本地跟踪器预测、没有当前检测量测的轨迹 |
| 丢失轨迹 | `lost` | 当前不可用的本地轨迹证据 |
| 锁定 | `locked` | 唯一实测候选通过全部 D5 门控 |
| 歧义 | `ambiguous` | 有候选，但唯一性、质量、身份或稳定性不足 |
| 保持 | `hold` | 合同、版本、身份或执行门控阻断 |
| 重获取 | `reacquire` | 目标投影或本地量测不可用，需要重新取得证据 |
| 针孔相机模型 | pinhole camera model | 用内外参把三维点投到二维图像的模型 |
| 投影协方差 | `covariance_px` | 三维航迹不确定度和像面量测噪声传播后的二维协方差 |
| 马氏距离门 | Mahalanobis gate | 按协方差尺度判断像素残差是否统计一致的门控 |
| 候选代价间隔 | `candidate_cost_margin` | 次佳代价减最佳代价，表示候选唯一性 |
| 边界框 | `bbox` | 图像中的二维目标外接矩形 |
| 边界框面积比例 | `bbox_area_ratio` | 边界框面积除以图像总面积 |
| 量测时间 | `measurement_timestamp` | 图像或检测对应的物理采样时刻 |
| 到达时间 | `arrival_timestamp` | 证据进入处理链的时刻 |
| 证据年龄 | `measurement_age_s` | 到达时间与量测时间之差 |
| 身份声明 | `IdentityClaim` | 合作平台对自身身份及友方属性的声明 |
| 已验证友方重叠 | `verified_friend_overlap` | 可靠友方声明与视觉候选重叠，必须保持 |
| 二级侦察图像线索 | `ReconImageCue` | 二级节点产生且已投到目标本地相机平面的辅助线索 |
| 跨视角支持 | `CrossViewAssociation` | 多资源对同一既有全局航迹的被动证据摘要 |
| 计划内协同锁 | `planned_cooperative_lock` | 符合同一计划/联盟合同的多资源锁定 |
| 重复末端锁定风险 | `duplicate_terminal_lock_risk` | 超额、越界、冲突或多重绑定造成的风险信号 |
| 稳定窗口 | stability window | 最近若干帧中要求足够连续门控通过的迟滞规则 |
| 失败关闭 | fail closed | 证据缺失或冲突时保持非执行状态，而不是默认通过 |
| 在线路径 | online path | 真值不可见、直接形成 D5 决策的处理路径 |
| 离线评价 | offline evaluation | 在线结果冻结后使用真值计算指标的过程 |
| 检测后端 | `detection_backend` | main runtime 选择 AirSim 检测元数据或可选 YOLOv8 的配置 |
| 原生跟踪 | native tracker | Ultralytics 实际返回 ByteTrack/BoT-SORT 本地轨迹标识的路径 |
| IoU 跟踪回退 | `iou_fallback` | 原生跟踪不可用时的确定性失败对照，不计准入 |
| 逐主用资源合同 | `per_primary` | 每个激活主用资源可独立形成视觉证据的合同口径 |
| 待命备用资源 | standby reserve | 未激活时可准备但不能计入主用完成的资源 |
| 相机几何证据 | `CameraGeometryEvidence` | 内参、相机到 NED 外参、姿态时间和有效性摘要 |
| 标定健康 | `calibration_health` | 依据投影有效性、重投影误差和位姿来源形成的诊断状态 |
| 末端一致性摘要 | `TerminalConsistencySummary` | 面向 D4/D6 的连续状态、冲突和建议动作摘要 |

## 16. 结论

D5 当前已经形成一条可执行、可审计且身份隔离的末端视觉关联主线：它把中心全局航迹预测到相机量测时刻，将三维协方差传播到像面，用马氏门和多项可解释代价选择本地实测候选，再由版本、授权、友方、稳定窗口和联盟合同作保守四态决策。它还能输出跨视角、逐主用资源、二级节点和 D7 前置证据，但始终不创建或改写全局身份。

截至 2026-07-13，合同安全与诊断接口已基本闭合，P0 无阻断项；性能侧仍未闭合。M5N2 最佳联盟完成率为 5/10，原生 MOT 18 组筛选无候选准入，30/50 米无有效检测，真实多相机三维融合和在线标定也尚未实现。因此当前主线必须继续保持 AirSim 检测元数据加几何关联，所有可选算法和离线对照都不得写成已经替代默认路径。
