# D5 Terminal Association

科研模块，用于把末端相机视场中的本地视觉轨迹保守关联到中心分配的 `global_track_id`。模块可在统一三维 episode 中在线运行；训练标签和真值评分仍保持离线。D5 只输出视觉关联与相机观察意图，不修改、重写或重新分配任何全局轨迹 ID。

## 2026-08-01 A3 v3 episode 证据与冻结写出接口

D5 已实现供 main 三维 producer 调用的 A3 v3 episode 配方、证据校验、分区 staging、分区
finalize 和来源 manifest 装配接口。读取入口仍绑定 104 条冻结 schedule、全局 allocation、协议
和内容哈希。main 的逐 episode 配方转换、意图窗口 treatment、五类困难混淆运行时证据适配
以及 D5 writer 单 episode 写出已通过 smoke 验证。readiness 当前为
`producer_adapter_complete=true`，但 `source_generation_request_ready=false`。

每个 episode 固定四个连续的 1.5 秒意图窗口。校验器在每个窗口内按 sample fingerprint 独立
去重并要求至少 24 个有效样本，episode 总数至少 96。样本不能复制、过采样或从其他 episode
转移配额。困难混淆不再由 treatment 名直接判定。离线 boundary state 分别保存分配引用、几何
族、通信状态、投影内外与新鲜度、侦察线索、云台忙闲、目标证据保持、合法目标数和投影质量差；
五类标签由这些状态的边界关系推导，调用方给出的 `achieved` 与推导结果不一致时失败关闭。

在线文件只保存冻结配方、双时间戳、匿名候选指纹、相机/资源角色、控制状态和中心只读
`global_track_id`。truth、actor 和 object 身份只允许进入物理隔离的离线审计文件。development
与 future-held-out 使用独立根目录；分区 manifest 保留原始 48/24/32 split，不随机重分，不跨
episode 补配额。future-held-out 的用途合同明确禁止训练、拟合、选模、校准和阈值选择，只允许
模型冻结且 validation 通过后的一次评估。development loader 遇到 future 分区直接拒绝。

本轮未生成 104 个正式 episode。2026-08-01 的 main smoke 使用非正式 seed
`31100-31104`，配置为 5 个目标、5 个资源、2 个侦察相机和 0.05 秒视觉周期；五类困难混淆均
形成，所有意图窗口均达到至少 24 个唯一样本，在线 truth 使用计数为 0。main adapter 专项为
`4 passed in 17.65s`，D5 evidence/readiness 专项为 `35 passed in 1.16s`，D5 全量为
`846 passed, 2 warnings in 103.23s`。这些结果只关闭 adapter/writer 技术接线，不构成正式
来源生成、模型训练或运行准入。

## 2026-08-01 A3 v3 全局 seed 分配与来源计划

D5 已把 main 的全局 seed 登记表接入冻结的 A3 v3 少数意图协议。新增版本化 allocation
binding 和 source collection schedule，分别绑定全局登记表 ID、内容哈希、文件哈希、协议哈希、
三组 allocation 及其来源文件。train、validation、future-held-out 使用 `24000-24047`、
`24048-24071`、`24072-24103`，对应 48、24、32 个互斥 seed。每个 seed 只对应一个完整
episode，禁止跨 split 复用、复制样本、过采样、合成 fixture 和在线 truth 注入。

采集 schedule 明列 104 条 per-episode 计划。每条记录 split、seed、episode ID、场景、规模、
目标/资源/侦察节点数量、6 秒时长、相机角色、四段意图窗口、两类困难混淆 treatment 和最低
唯一样本配额。每个 episode 的四段窗口合计 96 个计划样本，interceptor/recon 角色交替分配；
8 个意图-角色单元在 train/validation/future-held-out 中分别覆盖 24/12/16 个 episode。五类
困难混淆按 seed 分散安排，每个 episode 只承担两类，集合计数均达到协议下限。三个 split 的
计划最低样本量为 4608、2304、3072。这些都是计划计数，不是已生成语料证据。

`validate_a3_v3_source_readiness.py` 只读协议和元数据。它复现全局登记表自哈希并核对固定文件
SHA-256，检查 D5 allocation 的 owner/version/lifecycle/usage/operations、精确 seed 集、来源
绑定、逐 episode 配额重算、正式/v2 禁止范围和全 false authority。它还固定核对 main producer
入口、采集 treatment 和 v2 参考 schedule 的文件哈希。当前输出为
`plan_and_producer_adapter_ready_generation_not_authorized`：`plan_ready=true`、
`pre_generation_ready=true`、`producer_adapter_complete=true`，生成请求和训练仍为 false。
正式 104 episode 的执行授权、分区 finalize、source manifest 和后续训练均未开始。

最新 evidence/readiness 专项为 `35 passed in 1.16s`，D5 全量为
`846 passed, 2 warnings in 103.23s`。两条 warning 是既有 Matplotlib Axes3D 与 NVML 环境告警。
本轮没有生成 episode、sample、source manifest、cache 或权重，没有训练，也没有授予 shadow、
assist、runtime、camera command、control 或 `global_track_id` 写权限。

## 2026-08-01 A3 v3 少数意图开发协议冻结

下一模型版本冻结为“集合上下文意图分类 + 合法候选排序”。共享候选编码经 masked mean/max
形成四类意图辅助头；辅助交叉熵只按 train 计数计算有界逆平方根 class balance，候选排序始终
在确定性安全枚举给出的合法动作集合内。意图对排序的修正使用有界 `tanh`，低置信、非法输入、
合同不完整或任一门失败时仍回退确定性规则。

v2 train/validation 结构事实与已发布失败摘要只用于冻结方法；v2 test episode/sample 未读取，
也不得用于选 epoch、校准或阈值。唯一配置按 validation composite loss 选最早最佳 epoch，标量
温度只在 validation 固定网格拟合。validation 与 future held-out 分别冻结逐动作召回、逐角色
精确动作和 ECE 门；future held-out 仅在 validation 通过且模型冻结后一次性揭盲，失败后禁止
重训、重校准、改阈值或二次访问。

main 已在独立全局登记表分配全新的 train/validation/future held-out seed。三者互斥，并与
`22100-22199`（v2 全 split/test）及 `1000-1019`（正式保留）零重叠。来源清单仍须覆盖四类
意图、interceptor/recon 两类角色、全部 8 个意图角色单元和五类困难混淆场景的唯一样本、
episode、seed 下限；协议文件本身保持 seed 空值，实际分配由版本化 binding 承载。

当前状态固定为 `protocol_frozen_data_not_generated`。本批未生成或读取新 episode，未运行训练，
未写权重；训练入口只是后续协议预备，默认只校验协议且不创建输出。shadow、assist、PPO、
runtime、camera command、control、assignment、degradation、production、promotion 以及
`global_track_id` create/write 全为 false，规则路径保持默认。

## 2026-08-01 A3 v2 开发态行为克隆候选

D5 已在 v2 owner 验收语料上完成一次冻结配置训练。外部生成证据由 generation summary
内嵌的 training seed registry SHA-256、generation plan 与 summary 的完整 cell 相等关系，
以及三者共同的 schedule/Git 绑定建立。dataset manifest 的内生绑定单独覆盖 manifest、
split 和 training-set，不把外部 registry 误写为 manifest 字段。1000-1019 只作为禁止集合
核对，正式 R0 和对应样本均未读取或运行。

固定配置使用 CPU、seed `20260720`、5 epochs、hidden dimension 64、完整 train split 和
有界 `inverse_sqrt` 意图权重。train/validation/test 为 95,040/24,329/40,133 样本；
validation 只选择 5 个 epoch 内的最佳 checkpoint，test 不参与训练、配置选择或阈值调整。
流水线耗时 `887.994 s`，其中优化器训练 `2.876 s`；CPU 峰值 RSS `2342.352 MiB`，CUDA
allocated/reserved 均为 0。cache 与 47,045-byte 权重只保存在 ignored outputs。

test 总体精确动作准确率为 `0.959958`，但 `observe_target` 与 `search_sector` 召回均为 0，
宏平均召回 `0.495507`，期望校准误差 `0.368239`。拦截和侦察相机精确动作准确率分别为
`0.972377` 和 `0.656527`。development precheck 因两类少数动作、宏召回和校准四项失败
关闭；特征边界 OOD 为 0 只说明 test 特征未超出 train min/max 加 margin，不证明真正场景
分布外、AirSim 或真实相机泛化。

模型包状态固定为 `development_shadow_only`。assist、promotion、PPO、assignment、
degradation、runtime、production、control、camera command 和 `global_track_id` write 均为
false，默认确定性规则不变。权重/manifest/cache SHA-256 分别为
`b984e305...d01c`、`9f370a4e...793f`、`8576ae62...fe1a`。机器摘要与中文报告见
[`results/a3_v2_active_vision_bc_development_candidate_20260801.json`](results/a3_v2_active_vision_bc_development_candidate_20260801.json)
、
[`results/a3_v2_active_vision_bc_development_candidate_evidence_20260801.json`](results/a3_v2_active_vision_bc_development_candidate_evidence_20260801.json)
和
[`reports/D5_A3_V2_ACTIVE_VISION_BC_DEVELOPMENT_CANDIDATE_20260801_CN.md`](reports/D5_A3_V2_ACTIVE_VISION_BC_DEVELOPMENT_CANDIDATE_20260801_CN.md)。
本工作包相关测试为 `35 passed in 4.29s`。训练批次内 D5 全量为
`779 passed, 2 warnings in 102.40s`；收尾复跑为
`779 passed, 2 warnings in 124.10s`，均为零失败。

## 2026-08-01 A3 v2 来源独立语料 owner 验收

D5 已用严格 lazy loader 全量复载 main 冻结的 A3 v2 质点语料。语料绑定 clean commit
`d7bf89060e88a5b1324f2d8d1de36b005ebe5e4d`，包含 100 episode、100 seed、45 个场景规模
单元和 159,502 个样本；train/validation/test 为 60/20/20 episode 和
95,040/24,329/40,133 样本。manifest SHA-256 为
`9b80e47aed8f4c7a416694220d63d9156010911951cbbf271905ce5c0d6f31d4`。

严格数据集门、质点来源研究门和开发训练结构门均通过。train 中三个原空单元已自然补齐：
`hold+interceptor=42,669/60/60`、`hold+recon=1,772/60/60`、
`search_sector+recon=1,023/60/60`，数字依次为唯一样本、episode 和 seed。corpus audit
SHA-256 为 `bce869573f6c1084c2db10b263818d98be2de562f7701fc19ec95aaf56bfc872`。

全语料 ACK 为 159,502/159,502 accepted，匿名 observation key 全部唯一。在线 truth、actor、
object ID 消费和 `global_track_id` 创建/改写均为 0。owner 验收阶段没有训练或写权重；随后
使用同一冻结语料完成的一次行为克隆训练见本文件首节。近端策略优化未启动，assist、promotion
及分配、降级、runtime、production、control 和全局编号写权限均未开放。详细证据见
[`reports/D5_A3_SOURCE_INDEPENDENT_CORPUS_OWNER_ACCEPTANCE_V2_20260801_CN.md`](reports/D5_A3_SOURCE_INDEPENDENT_CORPUS_OWNER_ACCEPTANCE_V2_20260801_CN.md)。
本次 D5 全量回归为 `776 passed, 2 warnings in 102.23s`，零失败。

## 2026-08-01 A3 补采运行时合同复核

D5 已确认现有 `ActiveVisionCameraState` 和 `DeterministicLookAtScanPolicy` 足以接收 main
生成的真实云台状态，不需要新增强制动作或标签接口。拦截相机和侦察相机均在
`slew_available=false`，或 `action_in_progress_until > current_timestamp` 时输出
`hold`。相机仍保留中心计划中的目标引用，但在一个有界 cue-loss 窗口内没有可用的本相机
`ActiveVisionProjectionEvidence` 时，侦察相机输出 `search_sector`。动作不会创建、改写或
换绑 `global_track_id`，也不读取 truth、actor 或 object ID。

main 必须为每台相机传入可判定角色的 `resource_id`、`camera_id`、`state_timestamp`、云台
姿态/速率/限位、`slew_available` 和 `action_in_progress_until`；同时维持当前 plan、coalition、
communication 版本及中心只读航迹引用。补采 episode 必须使用新的 training seed，保留正式
seed 1000-1019，并由真实规则执行自然产生标签。不得复制、过采样、重加权、注入 fixture 或
直接指定动作。

2026-08-01 定向回归覆盖两类相机的 busy/unavailable `hold`、侦察相机 cue-loss
`search_sector`，以及三个缺失动作角色单元的 `2 sample / 2 episode / 2 seed` 失败关闭门，
结果为 `26 passed in 4.14s`。D5 全量为 `776 passed, 2 warnings in 102.06s`。该合同复核
阶段没有修改生产合同，也没有生成新语料、训练模型或开放 assist/promotion/authority。当时的
100-episode v1 语料仍失败关闭；后续补采与重验状态以上方 v2 owner 验收为准。

## 2026-07-31 A3 独立来源语料验收

独立 producer 已在 clean commit
`4a8c1173179b4058d4aee38178e0fb40ecd222b3` 冻结 100 episode、100 seed、45 个场景规模
单元的三维质点主动视觉语料。D5 于 2026-08-01 使用严格 lazy loader 和显式保留 seed
1000-1019 完成复核。语料共 159,487 个样本，train/validation/test 为 60/20/20 episode 和
102,610/23,458/33,419 样本；manifest SHA-256 为
`bccbdad42a71b130720469bb4e99dd1dd99e29a9b33af036679b9d64b0fe35a4`。

来源和完整性门单独通过，状态为 `point_mass_simulation_research_eligible`。训练结构门失败
关闭：train 中 `hold=0`，`search_sector+recon=0`，共 13 个失败原因。补采计划包含
`hold+interceptor`、`hold+recon`、`search_sector+recon` 三项，每项至少需要 2 个新训练
seed、2 个完整 episode 和 2 个唯一样本。corpus audit SHA-256 为
`85db29f86d924a437259a478e2fb182c220d3469c8f8a0c4374820e61e6ef74e`。

全语料运行 ACK 为 159,487/159,487 accepted，匿名 observation key 为
159,487/159,487 且无重复。dataset 未保存物理匿名观测帧和离线 outcome，这两项计数不构成
外部运行结果或目标可见率证据。行为克隆、近端策略优化和 assist 均未启动，全部 authority
保持 false。严格 `validate` CLI 的嵌套只读 mapping JSON 序列化缺陷已用递归 thaw 修复并增加
回归测试。详细结果见
[`reports/D5_A3_SOURCE_INDEPENDENT_CORPUS_ACCEPTANCE_20260731_CN.md`](reports/D5_A3_SOURCE_INDEPENDENT_CORPUS_ACCEPTANCE_20260731_CN.md)。
本次 episode dataset 专项为 `19 passed in 3.55s`，D5 全量为
`770 passed, 2 warnings in 102.24s`，零失败。

## 2026-07-31 A3 来源域与仿真研究门

D5 主动视觉 episode 现使用封闭来源域：历史未说明、合成软件 fixture、三维质点运行、
AirSim 运行和真实相机运行。每个显式来源对应固定证据等级。只有合成 fixture 域允许
`synthetic_fixture=true`；质点、AirSim 或真实相机来源与该标志同时出现时直接拒绝。

新写 episode 的在线 header、descriptor 和 dataset manifest 必须携带显式
`source_provenance`。旧制品缺少该 envelope 时走专用保守读路径：旧 fixture 只映射为软件
fixture，其他旧制品只映射为 `legacy_unspecified`，两者均不能晋级为质点、AirSim 或真实相机
证据。新非合成制品若没有来源声明，在持久化前失败关闭。

严格复载、显式质点来源、clean source identity、完整哈希和 seed split、在线 truth-free 及
语料完整性同时满足时，语料最多通过 `simulation_research` 开发评估门。该门不授予模型候选、
主动视觉、相机命令、分配、接管、运行、生产或控制权限。AirSim 和真实相机来源只形成声明，
声明本身不是外部运行证明。

2026-07-31 定向回归为 `43 passed in 7.83s`，D5 全量为
`769 passed, 2 warnings in 104.87s`。两条警告来自既有 Matplotlib `Axes3D` 环境和 NVML
初始化。该次软件回归只关闭“来源域语义和仿真研究门”软件 P1；当时尚未生成独立质点来源
语料，也没有重训 A3。后续 v2 语料及一次冻结行为克隆训练状态以本文件首节为准；AirSim、
真实相机、production、runtime 和 control 权限仍未取得。

## 2026-07-28 A3 主动视觉训练语料治理

D5 新增公共训练语料审计与补采规划模块
`active_vision_corpus_audit.py`。审计只使用 train split 中通过身份隔离、有限特征和数据
完整性检查的唯一样本，分别按动作意图、相机角色、场景、seed、意图与角色组合统计样本、
episode 和 seed 覆盖。相机角色限定为拦截机和高空侦察机，未知角色失败关闭。

默认开发门要求每个动作意图至少有 4 个唯一样本、2 个 episode 和 2 个 seed；每类相机角色
至少有 8 个唯一样本、2 个 episode 和 2 个 seed；每个“动作意图+相机角色”组合至少有
2 个唯一样本、2 个 episode 和 2 个 seed。该阈值只用于训练语料结构检查，不是模型性能指标
或正式准入指标。调用方还可声明必须覆盖的场景版本，审计会逐场景检查每个动作和相机角色。

审计拒绝缺少 `hold`、少数动作不足、侦察相机缺失、重复 episode、同一 episode 内复制策略
输入、训练/验证/测试 seed 交叉、保留评估 seed 混入、非有限候选特征、truth/actor 字段和
未知相机角色。重复项只进入违规计数，不增加动作、角色、场景或 seed 覆盖。逆平方根权重、
过采样和样本复制均不能改变审计结果。输出按稳定顺序生成
`AV-CORPUS-NNN` 补采请求，逐项给出场景、动作意图、相机角色以及至少还需增加的唯一样本、
episode 和新训练 seed。

行为克隆缓存升级为 `d5.active-vision-bc-cache.v2`，缓存清单和数据审计同时绑定语料审计
及其 SHA-256。训练在模型初始化前要求审计有效且通过。历史 v1 缓存可以读取基础数组，但因
缺少严格语料审计而禁止训练。正式行为克隆入口先写出
`training_corpus_audit.json`，再进入训练。

2026-07-28 使用小型合成开发 fixture 验证审计与训练前门。语料专项为 `11 passed`，D5
全量为 `755 passed, 2 warnings in 123.86s`。正向 fixture 只有 2 个训练 seed，且
`synthetic_fixture=true`；它只证明软件门可运行。既有正式行为克隆证据仍为
`hold=0`、`observe_target` 召回 0，侦察相机精确动作准确率约 `0.621823`。已有
100 episode、1200 sample 的补充课程同样是合成数据。当前没有通过新审计的非合成正式训练
语料，没有 20 个独立未见非合成 seed 的评估，也没有运行 ACK、动作结果或正式候选权限。
本轮未运行 900-cell、大写盘训练或 AirSim。正式候选、assist、相机命令、分配、接管、控制和
`global_track_id` 写权限继续为 false。

## 2026-07-27 A3 主动视觉模型前置诊断

`active_vision_bc_training.py` 的开发态行为克隆链已增加显式不平衡处理。缓存审计同时统计
意图、视场、相机角色和“意图+视场+是否引用目标”的动作签名。训练默认按所选意图使用有界
逆平方根权重：

\[
w_c \propto \min\left(8,\sqrt{N/n_c}\right),
\]

再按训练样本平均权重为 1 做归一化。最佳轮次也按同一训练意图权重计算验证损失。训练集中
没有正样本的动作不会补零、重采样或伪造；它在统计中保持 `unavailable`。若该动作意外出现在
验证集，则使用最大惩罚权重暴露缺口，不会被零权重忽略。

行为克隆报告升级为 v2。train/validation/test 均输出总体精确动作准确率、宏平均
precision/recall/F1、每动作召回、真实/预测动作分布、拦截相机与侦察相机分层指标、精确动作
置信度校准、训练特征边界分布外比例，以及动作不一致、低置信和分布外的诊断回退原因计数。
这些回退原因是模型预检查建议，不替代运行时确定性规则门。

新增的开发模型预检查要求每个动作在 train split 中有真实正样本，并在 test split 达到最低
召回，同时检查宏平均召回、两类相机角色、期望校准误差和分布外比例。逐类 precision、
recall 和 F1 分别按预测样本、真实正样本、真实或预测样本的有效分母报告，分母为零时保持
不可用。默认阈值只用于开发筛查，不能授予正式准入。99:1 极端
不平衡回归中，多数类预测得到 0.99 总体精确动作准确率，但 `observe_target` 召回为 0，
`hold/search_sector` 无正样本，预检查按失败关闭处理；assist、主动视觉、分配和控制权限全部
为 false。零检测帧原有合同保持不变：有分配目标时仍只能是
`reacquire + assigned_reference_visible=false`。

本轮没有启动 900-cell 或大写盘模型实验，也没有重写 2026-07-20 的正式历史结果。旧模型
`0.955978` 总体准确率、`observe_target` 召回 0、`hold=0` 和侦察相机约 `0.621823` 仍是当前
有效模型证据，新代码尚无正式未见 seed 指标。D5 全量回归为
`744 passed, 2 warnings in 111.52s`。正式候选至少还需独立 producer 补齐动作和相机角色，
冻结训练/验证/测试谱系，在至少 20 个明确未见且非 synthetic 的 seed 上完成同配置 R0/A3
成对非退化验证，并保持每 episode 无安全、可见率和重捕获退化。在线输入继续禁止 truth ID，
`global_track_id` 继续只读，bundle 不得自授任何运行权限。

## 2026-07-27 A3 主动视觉采用证据合同

D5 新增独立、失败关闭的 A3 证据组装器
`active_vision_a3_evidence_assembler.py`。它直接复用现有
`ActiveVisionDecisionV1`、`ActiveVisionRuntimeAckV1` 和
`ActiveVisionCameraFeedbackV1`，并通过结构适配器读取 main 的
`CameraObservationCommand`、`runtime.camera_command_ack` 和
`CameraRuntimeState`；没有新增平行 ACK、相机控制权或 main 模块依赖。

证据链分别记录 policy evaluated、command proposed、确定性投影 accepted/rejected、command
issued、运行 ACK、相机反馈、pose applied、后续物理观测窗和 association/coverage outcome。
验证器用 ACK 的 sample/camera/command/plan/coalition/communication version 及有效期绑定命令。
`ActiveVisionA3CameraPoseLineage` 另行保存 ACK 后相机状态的计划、联盟、通信版本和来源序号；
验证器再根据命令前相机状态与 `effective_action` 重算期望方位、俯仰和视场模式。模拟 ACK、
模拟反馈、规则回退、仅加载模型、仅有建议或仅有日志字段均不计为 adopted。

后续观测使用 `ActiveVisionA3AnonymousObservationFrame` 保存逐帧匿名本地轨迹、量测/到达时间、
三类版本和中心航迹只读绑定。轨迹键固定为
`resource_id/camera_id:local_id`。公共映射
`map_active_vision_binding_state()` 统一执行
`bound -> locked`、`ambiguous -> ambiguous`、`unbound -> reacquire`；该键和映射均不得用于
创建、替换或改写 `global_track_id`。

匿名观测帧现保留历史 v1，并新增
`d5.active-vision-a3-anonymous-observation-frame.v2`。v1 字段和内容哈希口径不变，仍强制
至少一个匿名轨迹。v2 使用 `frame_observation_state=processed_zero_detections` 明确表示相机
图像已处理但检测器没有输出，并保存中心航迹只读清单。公开
`active_vision_a3_zero_detection_frame()` 要求显式相机、资源、双时间戳、三类版本、来源序号
和中心目标引用；它不读取 truth/actor ID，也不创建或改写全局编号。有分配目标的零检测帧只
能得到 `reacquire` 和 `assigned_reference_visible=false`；没有分配目标时关联和覆盖保持
unavailable。物理窗口可混合 v1 非空帧与 v2 零检测帧，但同一窗口仍禁止混合 runtime 与
synthetic provenance，所有时间、版本、来源、结果和内容哈希均由严格 loader 重算。

main 已把 v2 工厂接入 scalable 3D 的真实 writer/runtime。每台相机都发布不含 truth 身份的
帧事件，只有图像已处理但零检测时才发布 `sensor.camera_empty_frame`；事件保存相机/资源、
量测/到达时间、扫描序号及计划/联盟/通信版本。A3 与 R0 按时间和版本绑定，观测触发命令后
保留 0.25 秒证据尾窗，通信丢包和抖动使用独立随机流。scalable 3D 全量回归为
`352 passed, 1 warning`。

同配置 seeds `1000-1019` 的 dirty-worktree 开发复跑得到 492 条候选，其中 488 条可配对、
4 条不可配对，可配对覆盖率为 `99.18699%`。可配对窗口内有 329 个 v2 零检测
`reacquire/coverage=false` 和 159 个 v1 `locked`，v2 空帧拒绝数为 0，全部权限仍为 false。
4 条缺失与默认 1% 通信丢包相关，不能据此认定唯一因果。将通信丢包和抖动都设为 0 后，同一
20 seeds 对照为 `500/500` 可配对、覆盖率 `100%`。两组结果均为
`formal_evidence=false`，来源工作树不干净，seed 未证明为 unseen；它们只验证运行接线和合同
覆盖，不证明主动视觉收益、模型准入或任何授权。

规则基线现使用独立的 `ActiveVisionA3RuleArmTrace`。公开入口
`assemble_active_vision_a3_rule_arm_trace()` 只接受学习模式关闭、规则动作等于有效动作、
无模型建议、无模型指纹和零模型推理时延的决定，并要求独立命令、运行 ACK、ACK 后相机反馈和
姿态版本血缘完整。该 DTO 不含候选模型 bundle、权重、实现或采用 trace 字段。规则 episode
可先将 trace 序列化，在另一进程中严格重建，再由
`assemble_active_vision_a3_rule_arm_physical_observation_window()` 使用持久化匿名帧形成 R0
窗口。

只有候选模型动作真实采用、候选后续观测结果可用，并存在场景、规模、seed、相机、资源、目标
引用、窗口序号、配对上下文和版本完全一致的唯一规则 R0 物理窗口时，输出
`d6_benefit_audit_input_allowed=true`。其余模型、相机、分配、接管、控制、晋级、ID 修改和 G1
权限固定为 `false`。`assemble_active_vision_a3_paired_evidence()` 对同一 comparison key 只
接受零个或一个 R0；重复 R0、跨键、跨相机、跨版本、同日志复用、时长不一致、缺双时间戳、
ACK/反馈不完整、在线真值和中心 ID 改写均失败关闭。

逐候选结果由 `attempt_active_vision_a3_pairing()` 返回
`ActiveVisionA3PairingDisposition`。输出固定包含 `pairable`、一个主原因码、底层诊断码和
候选 trace 引用；只有 `pairable=true` 时才引用既有
`ActiveVisionA3BenefitAuditInput`。稳定主原因包括未实际采用、候选物理窗口缺失、同键 R0
缺失、R0 重复或歧义、键或配置不一致、候选/R0 证据不完整、收益结果不可用和证据合同无效。
顶层主原因保持兼容。调用方未提供完整阶段清单时，候选窗口缺失仍保持粗粒度。
调用方提供与 adoption trace 和来源日志摘要绑定的
`ActiveVisionA3CandidateStageEvidence` 后，v2 disposition 才会在独立的
`candidate_stage_reason_codes` 中区分 ACK 缺失或未确认、命令过期或时序不匹配、相机反馈
缺失、匿名观测缺失或不完整，以及物理窗口明确缺失或装配不完整。运行原因只读取
`runtime_event_inventory_complete=true` 的清单，观测原因只读取
`observation_inventory_complete=true` 的清单；物理窗口细因要求两类清单都完整。部分清单中
已出现的时间、状态或计数只能作为上下文，不能单独触发细分归因。

持久化结果可用 `ActiveVisionA3PairingDisposition.from_mapping()` 或
`validate_active_vision_a3_pairing_disposition()` 严格复载。验证器要求顶层字段精确、JSON
类型精确、schema 和 `content_sha256` 正确；pairable 记录递归调用既有 paired evidence
validator，重新核对权限与 trace，unpairable 记录严格禁止携带 paired evidence。v2 还会严格
复载阶段证据，重算细分原因并拒绝未知原因、摘要篡改和 trace 引用不一致。旧 v1 disposition
继续按原字段集合严格复载。该过程不重新采集物理事件；细分原因的可信度来自 main 提供的完整
事件清单和来源日志，而不是离线追溯猜测。

历史冻结批次使用同一外生配置运行隔离的候选与规则 episode，并对 20 个开发 seed 的 536 条候选
逐条持久化 disposition。全部 536 条均可严格复载，其中 152 条可配对、384 条不可配对；
384 条的主原因均为 `candidate_physical_window_missing`。可配对覆盖率为 `28.36%`，20/20
seed 均至少存在一个可配对子集。批次 SHA-256 为
`455d181076553a485ff824618abc6d037a4477bb6342877d1d1e427fd28583a9`。

D6 按完整候选分母审计后得到 `a3_auditable_pair_count=0`。只要批次中存在合法 unpairable
记录，完整批次的实际采用、物理窗口、同键 R0 和收益计数均保持 `unavailable`，所有权限均为
`false`。152 条只代表可配对子集，不能写成完整 D6 可审计批次。该批次使用测试策略替身，
不是未见 seed、AirSim、实机或模型收益证据。

main 随后用同配置 seeds `1000-1019` 和当前 candidate-stage sidecar 完成一次不落盘全量重跑。
536/536 候选均有阶段证据，仍为 152 条 pairable、384 条 unpairable，20 个 seed 中完整可审计
seed 为 `0`。其中 344 条同时具有
`candidate_anonymous_observation_missing` 和
`candidate_physical_window_confirmed_missing`；其余 40 条因
`observation_inventory_complete=false` 保持 `candidate_stage_reason_codes=[]`，记为物理窗口
缺失细因未解析。D6 聚合口径为 evidenced `344`、unresolved `40`、
`detail_completeness=false`；每个 seed 的 scope 约为 20，evidenced 为 `scope-2`，
unresolved 为 2。40 条不再归为 `candidate_physical_window_incomplete`，这正是部分清单门控
防止越界归因的预期结果。ACK 缺失、运行确认缺失、命令过期、时序错配和相机反馈缺失均为 0。
开发摘要 SHA-256 为
`1ba6040e7c3e7e3b9e7d5506dfd20cf3539ce12c5aac13cca7f02799f0cd99ef`。该摘要明确标记
`formal_evidence=false`、`source_worktree_clean=false` 和
`persisted_full_pair_inventory=false`，因此只用于定位“命令数多于后续匿名观测帧”的开发断点。
旧持久化 disposition 仍保持原粗粒度原因，不追溯改写。

2026-07-27 当前 A3 专项测试为 **84 passed in 1.38s**，D5 完整回归为
**739 passed, 2 warnings in 97.98s**，无测试失败。新增用例覆盖历史 v1 严格复载、v1 空帧
拒绝、v2 零检测、中心目标引用、v1/v2 混合窗口、时间/版本/来源/哈希篡改、零覆盖和权限
全关闭。两条警告分别来自 Matplotlib `Axes3D`
多版本环境和 NVML 初始化失败。正例属于软件 fixture，不是实际 A3/R0 收益实验。D5 侧阶段
分类和持久化验证已闭合。正式 clean/frozen v2 全清单持久化、通信退化归因和未见策略成对
非退化评估仍是 P1，模型准入和在线权限仍关闭。详细合同见
[`docs/A3_ACTIVE_VISION_EVIDENCE_CONTRACT_CN.md`](docs/A3_ACTIVE_VISION_EVIDENCE_CONTRACT_CN.md)。

## 2026-07-27 G1 v5 正式证据闭环

main 在 clean commit
`8d5e02ec989259ce3d39e1e4ad6a90dd0d8d5b54` 上完成当前 D5 G1 合成证据链。只读证据根目录为
`/tmp/MSM-d5-g1-formal-evidence-8d5e02e-20260727`。本轮绑定的 runtime implementation
SHA-256 为
`b0708e718b374e5bb52db41c7bd2f994e340a2b009cfd348881a5f9d549baffe`。

| 制品或审计 | 正式结果 |
| --- | --- |
| development manifest SHA-256 | `7d459ed855cf74b810fa1f79ed0327efd39eb4be4409451266da3f3a95387ce0` |
| weights SHA-256 | `7fb5db8b6099ca4da5706a3bec53ff7cd634e8bd267c036ce3ee4ee4bf71ca71` |
| held-out | 20 个未见 seed、900 个 episode、45 个场景规模单元；precision、recall、F1、candidate recall 均为 `1.0`，false merge 为 `0`，CPU P95 约 `0.913 ms` |
| paired-shadow | 900 帧、74024 条边；模型 edge/cluster F1 均为 `1.0`，最高单特征 AUC 为 `0.720073` |
| paired lineage | SHA-256 `83e105290f3e624f267d92ceaf050d32291bd5bbbabf98580846cd31498b1af1`；900 条记录、900 个唯一 episode UID |
| D6 external audit v2 | `pass`；文件 SHA-256 `cbd6c72b2d9e7b78bf3aa36f975e6627250d2bf18de5a0b0ebc2c8f6cf760cd6`；内容 SHA-256 `334cf662e49c735931019ff358be1894d1358f1b4a5a868759eee41d3d282d15` |
| D5 生产 v5 | `d5.tracklet-model-bundle.v5`；manifest SHA-256 `b431d066362005868374d038eb93a83b773c03715a53d8a9dfd0da21784f317d` |
| D6 post-assembly v2 | `pass`；内容 SHA-256 `17dda42d06b4be1d21ff8f1f8baecc320fd49b532be06a9f9f6b304341763e1d` |

生产 v5 已通过 strict loader 和 shadow loader。请求 G1 在线辅助时必须失败关闭，稳定原因为
`bundle_g1_assist_authority_not_granted`。模型晋级、G1 辅助、默认路径变更、分配、故障接管和
控制六项权限全部为 `false`，因此状态仍是
`g1_evidence_eligible_not_authorized`。确定性几何关联继续作为默认在线路径，不能把本轮结果
写成 G1 已在线启用。

本轮证据来自冻结合成 tracklet 图。真实相机泛化、中心 `global_track_id` binding 正确性和物理
闭环结果在 D6 两级审计中仍显式标记为 `unavailable`。这些项目继续作为代表性真实相机回放、
离线身份真值连接和跨模块物理闭环的 P1，不由本次 v5 完整性通过替代。

## 2026-07-26 v5 paired lineage P0 修复（历史，已由 2026-07-27 正式闭环）

D5 v5 生产装配器现将 `paired_episode_lineage.jsonl` 作为显式、带调用方冻结 SHA-256 的第五类
输入。每一行必须是合法 JSON 对象，并含非空、全文件唯一的 `episode_uid`。正式 v5 只接受
`record_count=900`、`unique_episode_uid_count=900`，且计数必须与 paired report、D6 external
audit v2 的 `candidate.paired_lineage` 和 D6 consumer 的 episode 计数一致。

v5 实际写入 `evidence/paired_episode_lineage.jsonl`。manifest 的
`evidence.paired_shadow_lineage` 精确记录：

```text
filename
sha256
record_count
unique_episode_uid_count
```

admission report v2 同时增加
`paired_shadow_lineage_sha256`、`paired_shadow_lineage_record_count` 和
`paired_shadow_lineage_unique_episode_uid_count`。`SHA256SUMS` 覆盖 lineage 实物，公开 strict
loader 每次重新解析全部 JSONL 记录并复核 manifest、report、paired report 与打包 D6 audit。

paired-shadow 正式 writer 的 lineage 元数据已对齐 D6 post-assembly v2，使用
`schema_version/filename/record_count/sha256` 四字段。旧 `file` 字段结构不进入新装配路径。
缺文件、文件哈希变化、非法记录、空或重复 UID、非 900 计数、各方摘要或计数不一致均失败关闭。

该代码阶段冻结的 runtime implementation SHA-256 为
`b0708e718b374e5bb52db41c7bd2f994e340a2b009cfd348881a5f9d549baffe`。
assembler 专项 `69 passed in 1.93s`；assembler、paired writer 与 frozen registry 联合专项
`86 passed in 4.32s`；D5 全量 `655 passed, 1 warning in 100.57s`。warning 为既有 PyTorch
NVML 初始化提示。该段记录 2026-07-26 的代码与 fixture 状态，当时没有重训、external audit、
正式 v5 装配或 G1 episode；正式重证据、external audit v2 和 v5 已于 2026-07-27 完成。
此前 `fe116fd5...1c91` 只对应未携带 lineage 的中间实现，不能作为当前证据。

## 2026-07-26 六权限合同 v2 与制品版本（lineage 修复前的中间阶段）

D5 已在代码层完成六权限合同修复。`TrackletG1AuthorityContract` 使用
`d5.tracklet-g1-authority-contract.v2`，精确要求模型晋级、G1 辅助、默认路径变更、分配、
故障接管和控制六个权限字段存在、类型为布尔值且全部为 `false`。D6 审计中的 `reason` 只保留
解释作用，不能替代任一权限字段。缺字段、多字段、拼写错误、旧四字段结构、未知 schema、非布尔
值或任一 `true` 均失败关闭。

新证据链使用以下互相独立的版本：

- admitted bundle：`d5.tracklet-model-bundle.v5`；
- admission report：`d5.tracklet-g1-admission-report.v2`；
- authority contract：`d5.tracklet-g1-authority-contract.v2`；
- D6 external audit：`d6.d5-g1-external-audit.v2`；
- D6 input spec：`d6.d5-g1-external-audit-input.v1`；
- D6 consumer contract：`d6.d5-g1-external-audit-consumer.v1`。

新 v5 manifest 同时绑定权限合同版本、D6 审计文件 SHA-256、规范化内容 SHA-256、证据通过状态
和完整六权限映射。公开严格加载器每次重新读取打包的 D6 审计并交叉比对 manifest、准入报告和
审计实物，不做字段投影。装配状态使用 `g1_evidence_eligible_not_authorized`：证据完整性通过
不授予运行权限。影子加载仍可用；请求 G1 在线辅助时，由于
`g1_assist_granted=false`，运行时加载器返回
`bundle_g1_assist_authority_not_granted`。默认确定性几何规则、中心
`global_track_id` 所有权、双时间戳和协方差合同均未改变。

该六权限合同阶段的中间 runtime implementation SHA-256 为
`fe116fd50975e4adc63354a591bbf88d5da0700b43c557dde569658d67e11c91`。
assembler/loader 专项为 `70 passed, 1 warning in 2.78s`，D5 全量为
`636 passed, 1 warning in 106.54s`。warning 为既有 PyTorch NVML 初始化提示。
该阶段没有重训，没有运行 held-out、paired-shadow、D6 外审或 v5 装配；后续 lineage P0 修复
又改变了 runtime 摘要，因此本节只保留为中间代码合同记录。

旧 `d5.tracklet-model-bundle.v4` 和旧
`d5.tracklet-g1-admission-report.v1` 保留其历史含义。新严格加载路径分别返回
`legacy_g1_bundle_schema_unsupported` 和
`legacy_g1_admission_report_schema_unsupported`，不会把旧制品解释成 v5。旧 D6 external
audit v1 在装配及装配后复核中返回 `legacy_d6_external_audit_schema_unsupported`。

`docs/AIRSIM_INTEGRATION_PLAN.md` 已检查。本次只改变离线证据装配和加载合同，不改变 AirSim
输入、相机、检测、时序、外参或 episode reset 接口，因此该文件无需修改。

## 2026-07-26 旧 D6 audit v1 与 v4 装配阻断（修复前证据）

当时使用的输出目录带 `v2` 后缀，但审计 JSON 的顶层 schema 实际为
`d6.d5-g1-external-audit.v1`。目录校验清单及其引用的 9 项 D5 输入已重新核验。审计 JSON
SHA-256 为 `24c8b0cd...9ad7d`，内容 SHA-256 为 `f17acecf...35f`，结果为
`status=pass`、blocker 为空。模型晋级、G1 辅助、默认路径、分配、故障接管和控制六项权限
均为 `false`。

当时 runtime 的正式 evidence assembler 随后使用原始 development bundle、held-out、
paired-shadow 和该旧 D6 audit v1 文件执行原子装配。装配以
`d6_authority_fields_mismatch` 失败关闭，没有创建 v4 输出目录。原因是该阶段 runtime
`55066382...b8ea` 所绑定的严格 assembler 合同只接受四个权限布尔字段；该审计在此基础上
增加了分配权限和故障接管权限字段。删除 v2 字段、投影为旧 schema 或增加兼容白名单都会破坏
本轮审计边界。

该次失败发生在合同修复之前。修改 assembler 会改变运行时实现摘要，原 development、
held-out、paired-shadow、registry 和旧 D6 audit v1 随之失去实现谱系一致性。失败记录保存在
`/tmp/MSM-d5-g1-current-runtime-v4-64cb865-20260726-failed/`。确定性几何规则继续作为默认路径。

## 2026-07-26 clean R0 与 G1 证据（历史 5506 runtime）

main 使用 clean commit `64cb865b9933d45b13878019c0e1a21a8fbb2b05` 完成 20-seed
几何候选图 R0。正式结果覆盖 `2670` 帧、`16842` 个匿名节点和 `4658` 条图边，其中
`4642` 条真边、`16` 条假边；离线真值中共有 `4645` 个合格同目标对。候选图 precision 为
`0.996565`、recall 为 `0.999354`、F1 为 `0.997958`，hard violation 合计为 `0`。
这些数值评价当前投影、时序、协方差和稀疏几何门产生的候选图，不包含 G1 模型评分，不能解释为
G1 相对规则路径的收益。

D5 使用受审计正式 writer，从原 composite/formal/supplemental 数据、原 seed 和 robust-v2
超参数确定性重训。新权重 SHA-256 仍为 `7fb5db8b...ca71`，与历史候选字节级一致。writer
生成的新 manifest SHA-256 为 `db908b05...1d14`，其中 runtime implementation SHA-256
精确绑定 `55066382...b8ea`。没有手工修改 manifest、兼容白名单、阈值、数据或真值边界。

冻结 held-out corpus 在该阶段实现下正式通过 `20 seeds / 900 episodes / 45 cells`，覆盖
`13344` 个节点和 `74024` 条候选边。总体 precision、recall、F1 和候选召回均为 `1.0`，
错误合并率为 `0`，期望校准误差为 `0.0000347`，CPU P95 推理时延约 `0.872 ms`。
paired-shadow 同样通过；5 类真值无关扰动的最低边/簇 F1 均为 `1.0`，最高单特征
曲线下面积为 `0.720073`。在线真值特征、同相机候选边和中心全局编号创建或换绑均为 `0`。

正式制品位于
`/tmp/MSM-d5-g1-current-runtime-retrain-64cb865-20260726/`。current-runtime registry 状态为
`evidence_chain_closed_shadow_only`；顶层 `SHA256SUMS` 文件 SHA-256 为
`0a3b8e39...b36e`。随后旧 audit v1 通过自身门限，但当时拟装配的 v4 因 authority schema
不兼容未生成；该证据链不能用于 2026-07-27 的正式 v5。
`G1=false`、`assist=false`、`authority=false`、`default_model=false`，确定性几何规则继续
作为默认路径。旧 v4 仍绑定 `408e71fe...f4fe`，对该阶段 runtime 保持失败关闭。

本轮正式流水线专项为 `46 passed in 3.40s`，clean D5 全量为
`600 passed, 1 warning in 97.84s`。warning 是 PyTorch NVML 初始化提示；评估使用 CPU。

## 2026-07-26 关联图来源链接覆盖

main 在提交 `690858a` 的近距正向开发场景记录到 667 条真实目标视觉观测、294 条 candidate
edge 和 247 条 retained edge，在线真值使用为 0。该场景证明当前规则候选链能产生真实目标边，
但正式学习制品还缺一项来源合同：跨调用缓存节点已经进入 `association.graph.nodes`，来源链接
却没有作为关联快照的冻结字段进行全覆盖校验。缺链接会使离线 observation label 无法精确回接
缓存节点，正式 R0/G1 边真值评估不能据此开始。

`Scalable3DStepResult` 现在明确区分两类数据：

- `camera_batches` 继续只表示本次调用收到并审计的批次；
- `association_tracklets` 表示实际进入关联图的当前和缓存节点；
- `association_source_links` 冻结这些图节点的来源链接；
- 既有 `tracklets` 和 `source_observation_links` 保留为向后兼容只读别名。

每个带 `source_observation_id` 的图节点必须恰有一条链接。链接精确保存匿名 observation ID、
tracklet key、camera namespace、`measurement_timestamp` 和 `arrival_timestamp`。结果构造时
逐项核对节点覆盖、来源 ID、相机命名空间和双时间戳；缺失、重复、未知节点、错命名空间或时间
不一致均失败关闭。无来源观测的合成节点不伪造链接。缓存或 coast 节点保留原量测链接，不预测、
不重新标识。同一 camera-local tracklet 在后续调用可关联新的来源观测，但每个图快照只保存与
该节点状态对应的精确链接。

OOSM 不替换当前链接；缓存淘汰和 stream/episode reset 同时移除对应节点与链接。整个合同不读取
truth/actor/object ID，不改写 `global_track_id`，不改变任何时间、几何或模型门限。
2026-07-26 adapter 专项为 `50 passed`，D5 全量为
`600 passed, 1 warning in 94.80s`。warning 是既有 PyTorch NVML 初始化提示。

该合同修复阶段的运行时实现 SHA-256 为
`5506638201623048fb53c8e15493a2dc367d5682abbee3b7235704721586b8ea`。截至该段记录时，该
runtime 的 development bundle、held-out、paired-shadow 和 shadow-only registry 已形成，D6
独立外审及其后的新 v5 装配尚未执行；这些步骤已于 2026-07-27 针对最终 runtime 完成。旧 G1
v4 仍返回
`bundle_implementation_runtime_mismatch`，规则路径继续默认。

本次没有改变 AirSim 输入、settings、相机、检测器或 episode reset 接口。
`docs/AIRSIM_INTEGRATION_PLAN.md` 已检查，无需修改。

## 2026-07-26 异步跨调用活跃相机快照

`Scalable3DTerminalAdapter.process()` 原先只把本次调用中完成状态更新的相机批次送入关联图。统一
三维在线冒烟中，相机常按不同调用到达，因此每次图只有一个相机批次；即使多个相机先后看到目标，
也没有跨视角候选边。该问题不是图评分器漏判，而是评分前没有把仍有效的异步相机状态放进同一张图。

当前实现为每个 `(resource_id, camera_id)` 保存最近一份匿名实测局部航迹及对应外参。新相机批次
到达时，本次顺序实测批次作为图锚点；其他相机只有同时满足量测时间差、到达时间差、外参年龄、
missed-frame 和快照有效期约束，才以原始状态进入同一关联图。复用状态不预测、不改标签，继续携带
原始 `measurement_timestamp`、`arrival_timestamp`、像素协方差、相机位置协方差和姿态协方差。
没有本次实测锚点时不单独用缓存发布关联结果。

默认快照有效期取图配置中量测时间窗、到达时间窗和外参年龄上限的最大值，当前为 `1.0 s`；缓存
最多保留 `256` 个相机流。跨视角配对仍使用既有 `0.35 s` 量测时间差和 `1.0 s` 到达时间差，
几何门限没有调整。OOSM 批次不覆盖快照，重复量测继续拒绝；缺外参、过期、超时间窗、超过
missed-frame 上限、容量淘汰和重复节点均失败关闭或剔除。`reset_stream()` 清除指定相机的跟踪器
和快照，`reset_episode()` 清除全部状态。

关联诊断新增固定标量，分别记录本次更新批次、本次实测相机、跨调用活跃相机、复用局部航迹、
量测/到达时间排除、外参排除、过期、OOSM、重复节点、容量淘汰、入图相机和缓存相机数量。诊断
不携带业务 ID。`Scalable3DStepResult.camera_geometries` 返回实际覆盖关联图节点的当前及缓存外参。

验证结果如下：

- 异步两相机同目标的确定性 fixture 在第二次调用形成 `2` 个节点和 `1` 条边；不同目标形成
  `2` 个节点和 `0` 条边。规则回退和模型评分接口均通过。
- 过期、量测时间超窗、到达时间超窗、OOSM、缺外参、容量约束、同相机更新、stream reset 和
  episode reset 均有失败关闭回归。
- 2026-07-26 D5 全量测试为 `598 passed, 1 warning in 97.36s`；warning 是既有 PyTorch
  NVML 初始化提示。
- 等价 5v5 seed `1000`、`2.2 s` 规则短冒烟输出
  `/tmp/MSM-d5-active-snapshot-rule-seed1000`。在线共 6 条 `vision_bbox` 观测：量测时刻
  `0.7/0.8 s` 来自 `CAM-INT-0002`，`1.1 s` 来自 `CAM-INT-0001`，`1.6 s` 来自两相机，
  `1.8 s` 来自 `CAM-INT-0002`。离线 truth sidecar 将 6 条全部标为
  `disposition=known_false_alarm`、`truth_entity_id=null`；这些标签没有进入在线路径。
- 规则复跑在发布时刻 `1.25/1.75/1.95 s` 形成 2 个跨相机节点，累计图节点由旧运行的 `6`
  增至 `8`，其中两次发布各复用 1 个跨调用匿名航迹。`support_by_node` 没有共同中心
  `GlobalTrack`，稀疏预筛选正确保留 `0` 条边，在线真值使用为 `0`。该短复测只证明异步节点
  同图路径生效和虚警失败关闭，不能评价真实目标跨视角候选边、几何门或 G1 收益。
- 使用实际 `7fb5db8b...ca71` 权重的接口兼容探针在异步同目标 fixture 上得到 `2` 节点、
  `1` 边、`scoring_status=model_scored` 和概率 `0.9999935627`。该探针绕开正式 bundle
  准入，只证明评分接口兼容，不授予在线模型权限。

D6 已在 clean evaluator commit
`107cf0756d7b75cd6bf1456d1f1aa940fec6a63c` 对既有 G1 v4 完成正式 post-assembly audit，输出为
`research_modules/d6_evaluation_metrics/outputs/d5_g1_post_assembly_audit_7fb5db8b_a5a53de7_formal_107cf07_20260726/`。
结果 `status=pass`、`blocker=[]`，内容 SHA-256 为
`3738444168138584c7ec3eb895d123178092176ec751a5b455e575b177a2d852`，覆盖
20 个未见 seed、900 个 episode 和 45 个场景规模单元；在线真值、同相机互斥违规和
`global_track_id` 改写三项安全计数均为 `0`。该审计只证明当时 v4 的装配完整性，不授予模型
晋级、默认路径、G1 在线辅助、全局身份、分配或控制权限。

该阶段修改改变了 `scalable_3d_adapter.py`，当时运行时实现摘要为
`5506638201623048fb53c8e15493a2dc367d5682abbee3b7235704721586b8ea`，不再等于 v4 审计绑定的
`408e71fe...f4fe`。公开严格加载器因此返回
`available=false/failure_reason=bundle_implementation_runtime_mismatch`。这项失败关闭保持
证据边界正确；在该中间阶段，新运行时需要重新装配并由 D6 独立复审。2026-07-27 已完成最终
runtime 的装配完整性复审，但六项权限仍全部关闭，确定性几何规则仍为默认路径。

main 后续已用 truth-isolated 20-seed 场景完成真实目标共同可见 R0，并按该阶段源码生成
development、held-out、paired-shadow 和 shadow-only registry。截至该段记录时，下一步是 D6
独立外审及其后的新 v5、post-assembly audit；这条正式链已于 2026-07-27 闭环。现有门限保持不变。

本次没有改变 AirSim 输入消息、相机 settings、检测器、episode reset 接口或中心 ID 所有权。
`docs/AIRSIM_INTEGRATION_PLAN.md` 已检查，无需修改。

## 2026-07-26 冻结 registry 生产合同

clean commit `d437744c030785859b61cf893d15d0463ab54ffb` 已重建稳健补充语料、组合训练、
development bundle、20-seed held-out 和 paired-shadow。冻结权重 SHA-256 为
`7fb5db8b...ca71`，manifest 为 `0eff183f...da77`。held-out/paired/lineage 文件 SHA-256
分别为 `4ec0b824...c3a`、`f25c9428...57b` 和 `ca122b71...b57`。900 帧、45 个场景规模
单元完成；最高单特征 AUC 为 `0.720073`，非零 `shared_global_track_count` 分层没有样本。

`frozen_tracklet_audit.py` 现提供 `assemble_frozen_tracklet_registry(...)` 和
`assemble-registry` 命令模式。输入固定为冻结引用、审计摘要、held-out 报告、paired-shadow
报告和逐帧 lineage，并要求五份调用方冻结的 SHA-256。装配器复算 held-out/paired 内容摘要，
核对 bundle、corpus、held-out、paired 和 lineage 交叉绑定，确认所有权限字段为 false，再通过
同级 staging 原子发布 `frozen_bundle_reference.json`、兼容
`d5.frozen-tracklet-audit-evidence.v1` 的 `audit_evidence.json`、中文报告和
`SHA256SUMS`。目标目录已存在、输入变化、schema/content/lineage 不一致或权限未关闭时均拒绝。

限制项由 paired 诊断动态生成。最高单特征 AUC 达到或超过 `0.995` 才写入
`synthetic_heldout_single_feature_shortcut`；非零共享全局航迹计数同时呈近确定性时才写入
对应捷径阻断项。7fb5 clean 输入的只读预检只保留
`counterfactual_profiles_hold_candidate_graph_fixed`、`d6_external_audit_required` 和
`no_online_authority`。producer 提交 `fa3ec10` 已于 `2026-07-26T13:49:10Z` 在 clean
worktree 发布正式 registry：
`outputs/d5_g1_clean_source_chain_d437744_20260726/model_registry/tracklet_gnn_7fb5db8b_registry_fa3ec10/`。
中文报告、`audit_evidence.json`、冻结引用和根 `SHA256SUMS` 的 SHA-256 分别为
`1dfe1b3b...8c7c`、`bcee8cbc...8f29`、`9441fa84...a5d` 和 `c1abebfa...7f63`。
根清单三项全部通过；第二次向同目录发布以 `registry_destination_exists` 失败关闭，四份输出和
五份历史输入哈希均未变化。D6 独立 owner 随后完成正式外部审计；该 registry 中
`d6_external_audit_required` 记录的是发布当时状态，不回写历史 producer 输出。正式审计和 G1 v4
装配结果见下节。
2026-07-26 D5 全量回归为 `589 passed in 112.89s`，验收要求为零失败。

## 2026-07-26 G1 v4 正式证据 bundle（历史制品）

D6 正式外部审计 JSON 的文件/内容 SHA-256 为
`10bf19f5fa89788c9cc0a24ab18b647c6cf863149bae08d22fc40796d15210b0` /
`4e24ab33ca290133cf107f2c4ad5fee85d763001556f35fcd0ecdb819bef9e54`。
`audit_passed=true`、blocker 为空，D6 的模型晋级、G1 辅助、默认路径和控制权限字段全部为
false。审计绑定的运行时实现摘要为 `408e71fe...f4fe`，与 clean `fa3ec10` 的 development
bundle、held-out 和 paired-shadow 一致。

D5 于 `2026-07-26T14:14:12Z` 使用正式 D6 JSON 正向装配
`outputs/d5_g1_clean_source_chain_d437744_20260726/model_candidate/g1_assist_v4_7fb5db8b_d6_10bf19f5/`。
输出 schema 为 `d5.tracklet-model-bundle.v4`；manifest、weights 和根 `SHA256SUMS` 的
SHA-256 分别为 `a5a53de7...37154`、`7fb5db8b...ca71` 和 `1221ec23...c75956`。
公开 strict loader 在 `require_g1_assist_eligible=True` 下完成 manifest、weights 和三份
evidence 的复核，返回 `g1_assist_eligible=true`。第二次向同目录装配以 `output_not_empty`
失败关闭，六份输出和六份输入哈希均未变化。

该 v4 只形成 G1 辅助资格证据。`default_model=false`，全局航迹标识、分配和控制 authority
均为 false；main 没有启用在线 G1，也没有修改默认配置。真实候选门重新构图、真实相机泛化和
AirSim 在线作用域仍未完成，确定性几何规则继续作为默认路径。
本轮 G1 assembler/strict-loader 定向回归为 `34 passed, 1 warning in 2.39s`，D5 全量回归为
`589 passed, 1 warning in 99.17s`。警告为本机 PyTorch 无法初始化 NVML，不影响 CPU 严格加载。

## 2026-07-26 G1 稳健开发候选

D5 已针对旧 `99fa4428...d4cd` 候选的遮挡重现、单特征捷径和实现谱系问题形成新开发候选。
补充课程增加相机局部、标签无关的检测框尺度、尺度变化率和角速度误差；训练增加遮挡重现、
相似运动干扰和独立尺度抖动三个确定性困难视图。困难视图不读取 evaluator truth，不改变候选边
拓扑。

新权重 SHA-256 为
`7fb5db8b6099ca4da5706a3bec53ff7cd634e8bd267c036ce3ee4ee4bf71ca71`，bundle manifest 为
`ddd7ce4aa0fc5e9b01e1c388992f6e443aebcf4484ac9f0c09727a66bad72f17`。模型实现摘要与完整
运行时实现摘要分别为 `1883bc36...105` 和 `408e71fe...f4fe`。seed `1000-1019` 的 900 帧
held-out 得到 F1=1.0、错误合并率=0、候选召回率=1.0、CPU P95=1.121304 ms；同图
paired-shadow 的五类困难扰动 edge/cluster F1 均为 1.0，最高单特征 AUC 为 0.720073，满足既有
`<=0.98` 门限。在线 truth 特征、同相机互斥违规和 `global_track_id` 改写均为 0。

该段记录 clean 重建前的内部运行。补充语料与训练来源记录为 dirty，训练状态为
`hash_bound_dirty_internal_development_complete`，没有 clean commit 声明。D6 外部审计和 G1
assembler 均未运行，`default_model=false`、`g1_assist_eligible=false`。最终 blocker 为
`source_repository_dirty`、`clean_commit_retraining_required`、
`d6_external_audit_not_run_dirty_source` 和 `g1_assembler_not_run_dirty_source`。旧模型、旧
审计、全部门限和兼容策略均未修改。详细结果见
`reports/D5_TRACKLET_G1_ROBUST_V2_FAIL_CLOSED_20260726.md`。
2026-07-26 D5 全量回归为 `578 passed in 103.88s`。

## 2026-07-26 G1 证据装配闭环（历史 v4 合同）

D5 已实现独立 G1 证据装配器和命令行入口。输入固定为一份 v3 development bundle、一份
held-out JSON、一份 paired-shadow JSON 和一份 D6 外部审计 JSON；调用方还必须提供 bundle
manifest、weights、`SHA256SUMS` 及三份 JSON 的带外 SHA-256。装配器不接收
`TrackletG1AdmissionReport`、准入布尔值或调用方填写的权限对象。生产
`write_tracklet_model_bundle()` 仍拒绝任何 caller-provided report。

审计通过时，装配器在同级临时目录生成 `d5.tracklet-model-bundle.v4`，实际打包
`evidence/heldout_evaluation.json`、`evidence/paired_shadow_report.json` 和
`evidence/d6_external_audit.json`。新 `SHA256SUMS` 精确覆盖 manifest、weights 和三份证据。
公开 loader/runtime 每次加载都会复算文件与内容摘要，核对 D6 consumer contract、字段可用性、
20/900/45、三个安全计数、模型/实现/数据集/划分/训练集绑定和 admission report。v4 只获得
`g1_assist_eligible=true`；`default_model`、全局航迹编号、分配和控制权限均为 `false`。

正向 fixture 已证明该软件合同可原子生成并由公开 runtime 严格加载。负例覆盖缺文件、文件及内容
篡改、跨模型/数据集/实现、字段 unavailable、布尔/整数类型伪造、装配后证据篡改、非空目标目录、
失败残留和旧手工 v4 绕过。该 fixture 是合同测试，不是当前模型准入证据。

该历史 `99fa4428...d4cd` 模型未获准。post-assembler D6 审计位于
`research_modules/d6_evaluation_metrics/outputs/d5_g1_external_audit_99fa4428_post_assembler_20260726/d5_g1_external_audit.json`。
文件 SHA-256 为 `98bf9e0251567a330bf16951acf07da576a6ba3dc47627c3671cd2d491cdc8ed`，
内容 SHA-256 为 `40a42af015211d5e721584053e052a893e31aa35b7393195530a5d3d2dc9b90d`。
装配器返回稳定拒绝码 `d6_external_audit_fail_closed`，退出码为 2，目标目录不存在。五个
blocker 为 `implementation_evidence_unavailable`、`implementation_lineage_mismatch`、
`robustness_threshold_not_met.cluster_f1`、`robustness_threshold_not_met.edge_f1` 和
`synthetic_single_feature_shortcut`。没有调整阈值、增加实现兼容白名单或重写旧
bundle/报告/D6 输出。该历史 G1 运行实现摘要为
`41381db3d11371c049e5569658820ce98abf1a9966ecf86edc0f13f140894b07`。该摘要已包含
`tracklet_g1_evidence_assembler.py`；仅改变 assembler 即会改变摘要。旧 development bundle 未绑定
该文件，公开严格 loader 返回 `implementation_runtime_mismatch`，不提供兼容白名单。

A3 主动视觉准入不在本次实现范围。其 production writer 继续拒绝 caller-provided report，公开
assist loader 继续失败关闭。确定性几何关联和规则主动视觉仍是默认路径。

2026-07-26 最终证据同步复测：assembler 专项 `14 passed in 1.15s`，模型流水线
`20 passed in 4.08s`。既有 D5 全量结果为 `571 passed in 99.00s`。

## 2026-07-25 同一 GNN bundle 的 20-seed 证据闭合

D5 已冻结当前可严格加载的跨视角图神经网络 bundle。模型 manifest SHA-256 为
`c4284b2442dba56c0d2857146760f840e72cbe02ffe9a98964a0c68bb69bc674`，权重 SHA-256 为
`99fa4428849773458eb1a537d5f6cd72a23275215a6dfe5d558dbaa3df92d4cd`。同一组哈希已贯穿严格
加载、seed `1000-1019` 保留集评估和规则/模型成对影子评估，关闭了旧报告绑定另一份权重的谱系
断点。模型清单仍为 `development_only_fail_closed`，`default_model=false`、
`g1_assist_eligible=false`。

本次评估覆盖 900 帧、45 个场景规模单元、13,344 个匿名局部航迹节点和 74,024 条候选边。两臂逐帧
读取同一只读图和相同候选边；离线标签只在两臂完成评分和受约束聚类后使用。候选召回率为 1.0，
冻结模型的名义边/簇 F1 均为 1.0，CPU 评分 P50/P95 为 `0.983052/1.219528 ms`。在线真值字段和
`global_track_id` 改写均为 0。

名义满分不能作为准入结论。单特征最高 AUC 为 `0.997340`，对应检测框尺度变化率差。五类
label-independent 反事实扰动中，遮挡重现代理的模型边/簇 F1 降至 `0.563264/0.572845`，独立
检测框尺度扰动降至 `0.893470/0.949131`。九类模型异常均返回与几何规则逐值一致的概率，回退率
为 1.0。`G1=false`、`assist=false`、`authority=false`，主动视觉 PPO 未启动。

可复核的小型制品位于
`model_registry/tracklet_gnn_99fa4428/`，包含冻结引用、审计摘要、中文报告和校验清单；权重继续
保存在被忽略的生成输出或后续独立制品库，不进入普通 Git 提交。复现入口为
`scripts/run_frozen_tracklet_gnn_audit.py`。

2026-07-25 D5 全量验收为 `552 passed in 114.25s`。main 在 D4 因果通信修正后复跑统一
D1-D7 module stack，结果为 `66 passed, 1 warning in 10.17s`。警告是既有 Matplotlib
`Axes3D` 导入环境提示。两组测试确认 D5 模块与当前跨模块合同没有回归，不构成冻结图模型
在线准入或真实多相机性能证据。

## 2026-07-23 seed 1000 长窗口 profiler 收敛

本轮使用 clean `4ac3bb2` nominal 200v200 seed 1000 的冻结匿名在线日志归因 2.2 秒/10 秒长短窗口成本。10 秒输入覆盖 114 次终端调用、723 个相机批次、2479 个检测/图节点和 2400 个 binding；日志 SHA-256 为 `c1dda852...6f77a`，未加载 truth source。

热态 cProfile 将低风险重复工作定位到历史 gauge 全 tracker 扫描、匿名 payload/ID 审计和 singleton cluster binding 物化。当前实现用增量账本替代 gauge 扫描，对匿名 ID 正则使用 8192 项有界 LRU，对精确内建叶子采用审计快路径，并让 singleton cluster 复用已有投影距离行。长日志固定诊断记录避免 91,871 次 tracker 引用扫描、复用 2289 个 singleton 行；79 个多节点聚合和 32 个无矩阵 binding 输出仍走完整语义。

热态 cProfile 的 `process()` 累计为 `2.320→1.987 s`，`adapt_batches()` 为 `1.428→1.122 s`，匿名 payload 审计为 `0.358→0.162 s`，历史 gauge 为 `0.0544→0.00288 s`，binding 为 `0.0578→0.0312 s`。两轮各 7 次描述性 A/B 的长日志中位值均值为 `1.149362→0.929495 s`，约下降 `19.13%`；墙钟不作为测试硬门。该组 cProfile 和 A/B 对应 singleton 有限行零符号边界修复前的源码，`sparse_tracklet_graph.py` SHA-256 为 `dc6bcd81...b4c4c`，不得作为最终源码的性能剖析结果。

最终边界修复把 singleton 有限投影行按旧求和路径规范为 `+0.0`，当前 `sparse_tracklet_graph.py` SHA-256 为 `0e8a5880...19d5b`。机器 JSON 的 `post_boundary_fix_verification` 使用最终源码重新消费同一冻结短/长日志；逐帧业务哈希、最终 binding 哈希、v2 操作数哈希和冻结 v1 operation-equivalence 哈希均与修复前记录一致。长序列业务、binding 和 v1 操作面哈希仍为 `d9629adc...35ca0`、`996763e3...24b6`、`c8a19ee8...affc`，online truth use 与 `global_track_id` mutation 均为 0。结构化证据见 `results/scalable_3d_seed1000_duration_operation_20260723.json`，归因报告见 `reports/D5_SCALABLE_3D_SEED1000_DURATION_OPERATION_20260723.md`。

本轮没有在当前源码上重跑完整 clean 集成。原 10 秒集成 P50/P95/max 约 `11.497/15.969/18.632 ms`、相对短窗约 `2.556x` 的 P1 继续开放；模块冻结重放的候选中位增长 `2.563x` 也未达到线性准入。后续仍需 main/D6 做预注册正交多 seed 操作数/阶段耗时联合验收。

2026-07-23 main 对最终边界修复后的当前源码完成 D5 全量回归，权威结果为 `551 passed in 100.83s`，接受阈值为零失败。`550 passed in 102.41s` 只保留为边界修复前的历史结果。

## 2026-07-22 相机重叠索引占用桶复用

长日志函数剖析显示，116 次 `build_camera_overlap_index()` 累计约 `0.357 s`，其中约 `0.248 s` 消耗在从已占用桶向三维空网格枚举偏移。当前实现复用已经建立的只读占用桶序列，直接检查占用桶对的切比雪夫距离。该条件与旧整数偏移搜索严格等价，视锥、时间、包围盒、相机对预算、轨迹候选和全部后续几何门保持不变。

基于 clean `f80b5bd` nominal 200v200、10 秒 frozen replay 的交替配对 A/B，seeds `42000/42001/42002` 的终端重放中位耗时分别为 `1.551→1.313 s`、`1.501→1.262 s`、`1.406→1.149 s`；三 seed 中位值均值下降 `16.45%`。优化后相机重叠索引累计约 `0.117 s`，占用桶对 helper 约 `0.005 s`。

三个 seed 的逐帧核心、最终 binding 和操作数哈希均与各自冻结记录一致。核心哈希覆盖几何诊断和绑定代价；在线真值使用、中心 `global_track_id` 改写、帧/候选减少、门限变化和 D7 gate 变化均为 0。seed 42000 的主动视觉命令哈希保持 `a9d3d3f2...58f6`。证据见 `reports/D5_SCALABLE_3D_CAMERA_OVERLAP_AB_20260722.md` 和 `results/scalable_3d_camera_overlap_ab_20260722.json`。

该优化关闭“空网格重复探测”局部子项，不关闭 D5 长时超线性 P1。正式结论仍需正交控制检测数、活跃相机数、中心候选数和时长，并由 D6 联合报告操作数与阶段耗时；本轮没有 AirSim 或硬件实时性证据。

本轮定向回归为 `52 passed`，D5 全量回归为 `545 passed in 129.59s`。

## 2026-07-22 f80b5bd 三种子集成等价复核

main 在 clean 参考提交 `8f86192` 与 clean 候选提交 `f80b5bd` 上，使用 nominal 200v200、10.0 秒和 seeds `42000/42001/42002` 完成逐条跨提交审计。三个候选 episode 均保持有限状态，在线真值使用次数为 0；D1、D2、D3、D5、D7 的最终对象数量与参考运行相同。

| D5 证据 | 参考 `8f86192` | 候选 `f80b5bd` | 结论 |
| --- | ---: | ---: | --- |
| 终端关联累计耗时三 seed 均值 | 2.545876 s | 1.974446 s | 下降约 22.45% |
| 主动视觉累计耗时三 seed 均值 | 4.174315 s | 4.183797 s | 增加约 0.23%，基本持平 |
| 投影 DTO 缓存命中/未命中 | 68/48、71/48、70/48 | 68/48、71/48、70/48 | 每 seed 完全相同 |
| 最终 binding 数 | 22/29/28 | 22/29/28 | 每 seed 完全相同 |

逐条视觉 binding 与主动视觉载荷语义相同。审计只按 D3 计划出现次序和版本归一化独立运行生成的不透明 `plan_id`；归一化前先验证 ACK 原始来源载荷的 SHA-256，owner、plan version、coalition、`global_track_id`、command 等业务字段仍逐项比较，没有被忽略。

本轮性能变化来自单次 `process()` 内的工作区复用。同一量测时刻的多个相机批次共享一份只读 center prediction；工作区不跨 `process()` 调用，不删除检测或中心候选，不改变投影、几何门、唯一绑定和 `global_track_id` 所有权。该结果关闭“当前源码三种子集成复跑”子项，但没有证明 D5 长时单次成本已达到线性，超线性规模成本和正式实时性准入继续保持 P1。文档同步后的 D5 全量回归为 `544 passed in 163.09s`。

## 2026-07-22 中心预测工作区等价优化

seed 42000 冻结日志的进一步剖析区分了“操作数大”和“实际热点”。10 秒路径累计包含 33315 次局部匹配比较、499505 个中心投影矩阵单元和 472288 个 binding 矩阵单元；函数级中位累计耗时分别约为 `0.098/0.706/0.057 s`。因此本轮没有截断局部候选或改写 binding，而是消除了中心投影阶段按相机重复抽取中心轨迹数组和重复预测同一量测时刻状态的工作。

当前 `_center_projection_distance_matrix()` 每次调用只物化一次中心 position/velocity/covariance/timestamp 数组，并把每个唯一量测时刻的预测 position/covariance 保存为该调用内的只读工作区。短日志的 76 个相机时刻组共享 23 份预测，长日志的 715 个组共享 116 份预测。所有 `13615/499505` 个投影单元、`13415/472288` 个 binding 单元和 33315 次局部比较继续执行；固定大小快照及其短/长操作数哈希保持 `a8e7a6dc...2b4` / `2577b181...fcf`。

五轮交替旧/新实现的配对重放中，短序列平均单次成本中位数为 `10.879 -> 7.610 ms`，长序列为 `26.078 -> 19.145 ms`，10 秒路径下降 `26.6%`。独立五次候选报告记录 `8.522/20.163 ms`，归一化增长 `2.366x`；配对运行的增长为 `2.418x/2.450x`，说明主机墙钟和短序列对比仍有明显波动。短/长逐帧业务哈希、最终 binding 哈希和操作数哈希均与冻结基线一致，在线 truth 使用与 `global_track_id` 改写为 0。D5 全量回归为 `544 passed in 155.17s`。绝对长路径优化已验证，当前源码三种子集成复跑已由上节关闭；超线性规模成本和正式性能准入仍为 P1。

## 2026-07-22 clean 三种子集成复核

提交 `8f86192` 的 200v200、10 秒 clean 候选已完成 seeds `42000-42002` 复核。D5 终端关联阶段耗时分别为 `2.4496/2.6355/2.5526 s`，均值由旧 clean 候选的 `2.6985 s` 降至 `2.5459 s`，下降 `5.7%`；三种子的调用次数仍为 `116/119/118`。该结果是统一三维系统墙钟证据，包含运行环境波动，不能单独归因给某一项 D5 优化。

seed 42000 的固定大小性能快照记录 116 次调用、2493 个图节点和 33315 次局部匹配对比较。相同 2.2 秒/10 秒对照中的短长序列单次成本增长由旧候选 `2.696x` 降至 `2.423x`，但仍高于线性范围，因此超线性规模成本继续列为 P1。在线真值使用和 `global_track_id` 改写均为 0。D6 将三组 episode 全部标记为 clean descriptive calibration，不能据此给出正式验收或因果结论。

本节引用 `research_modules/scalable_3d_simulation/outputs/scalable_3d_long_duration_candidate_20260722_clean_8f86192/`。下节的五次冻结日志重放仍是 D5 单模块操作数基准，两组数据来源、计时方法和结论边界不同，不合并计算。

## 2026-07-22 三维长短序列操作数复核

D5 增加了固定大小的 `Scalable3DPerformanceSnapshot`。诊断只保留累计计数和当前/峰值标量，不保存逐帧调试历史，也不进入 `TerminalAssociation` 业务载荷。计数覆盖相机批次、检测转局部轨迹、历史更新、候选边与几何拒绝、图评分与聚类、中心投影缓存、投影/绑定矩阵、匈牙利求解和绑定输出。

冻结在线日志五次重放中，短序列为 2.15 秒、23 次调用，长序列为 9.95 秒、116 次调用；中位总耗时为 `0.213419/2.289464 s`，平均单次成本为 `9.165/19.564 ms`。调用密度只增长 `1.090x`，单次成本增长 `2.135x`。每调用检测/图节点、投影矩阵单元和绑定矩阵单元分别增长 `5.815x/7.274x/6.980x`。局部匹配对比较增长 `188.730x`，但剖析表明其不是单一主导热点；投影、绑定、图构建、输入校验和求解共同构成长序列成本。

同一相机批次现在只对首条检测完整校验内参、外参、旋转和像素协方差。后续检测只有在全部已消费字段内容一致时才复用模板；外参变化继续失败关闭。10 秒剖析中完整模板构建调用由 2493 次降为 715 次，模板准备累计耗时由 `1.012200 s` 降为 `0.532869 s`，被剖析的 `process()` 由 `5.403226 s` 降为 `4.701830 s`。逐帧业务输出和最终绑定哈希均与冻结原记录一致，在线真值使用和 `global_track_id` 改写均为 0。

证据见 `reports/D5_SCALABLE_3D_DURATION_OPERATION_BENCHMARK_20260722.md` 和 `results/scalable_3d_duration_operation_benchmark_20260722.json`。当前剩余边界是长序列输入规模继续增大时的投影/绑定矩阵成本，以及按 episode 保存的已接收时间戳审计集合；后者用于精确拒绝重复和乱序批次，不能在没有新合同前任意截断。

## 2026-07-22 三维长时性能收敛

针对 200v200 长时阶段增长，D5 在不改变输入频率、候选门控和决策状态的条件下收敛了内部重复工作。固定 10 秒在线日志重放中，终端关联由基线 `4.133 s` 降至 `2.776 s`，加速 `1.489x`；205 条中心航迹、208 台相机和 199 个分配引用的主动视觉负载由 `37.431 ms/轮` 降至 `25.918 ms/轮`，加速 `1.444x`。

116 次终端关联的输出逐条一致，记录与重放哈希均为 `7f212c56...254e4`。绑定状态保持为 `bound=1938`、`ambiguous=36`、`unbound=384`；在线真值使用和 `global_track_id` 改写均为 0。增长根因是稳态调用次数增加以及每帧视觉候选由均值 `3.696` 增至 `21.491`，不是 tracklet 历史无界累积。优化复用了中心投影矩阵、快照索引和内容未变化的 D2 航迹 DTO，缓存会随状态、协方差、时间戳、版本或 ID 变化而失效，并在 episode reset 时清空。

证据见 `reports/D5_SCALABLE_3D_LONG_DURATION_PERFORMANCE_20260722.md` 和 `results/scalable_3d_long_duration_performance_20260722.json`。10 秒日志中的主动视觉和终端关联发布载荷分别约为 `8.273 MB` 和 `0.779 MB`；D5 阶段计时在发布载荷构造与总线序列化前结束，因此载荷不是本模块内部超线性耗时来源。

## 2026-07-22 同图配对影子评估 v2

D5 已完成 seed `1000-1019` 的正式同图配对影子评估。权威输出为
`outputs/d5_tracklet_paired_shadow_1000_1019_e39a54d_v2`；首次输出保留原目录，状态为
`superseded_preserved`，未覆盖或删除。v2 显式绑定 held-out manifest、配置、held-out 评估报告、
模型 manifest、权重、校验清单以及旧 report/lineage 的带外 SHA-256。输入在运行前后哈希一致。

评估覆盖 20 个保留 seed、45 个场景规模单元和 900 个图帧，共 13,344 个匿名节点与 74,024 条
候选边。每帧只加载一个不可变图实例，确定性几何规则和冻结图神经网络依次读取同一实例；规则
评分、模型评分和两次受约束聚类后的图数组及候选边哈希均保持一致。evaluator 标签只在两臂推理和
聚类完成后用于边级与簇级评分。900 帧中同相机候选边、未标注边、在线真值特征和
`global_track_id` 改写均为 0。

| 指标 | 确定性几何规则 | 冻结图神经网络 |
| --- | ---: | ---: |
| 边精确率 / 召回率 / F1 | 0.225484 / 0.999820 / 0.367980 | 1.000000 / 1.000000 / 1.000000 |
| 边错误合并率 | 0.774516 | 0.000000 |
| 簇对精确率 / 召回率 / F1 | 0.237538 / 0.240954 / 0.239234 | 1.000000 / 1.000000 / 1.000000 |
| 错误合并对 / 同目标拆分对 | 12,910 / 12,670 | 0 / 0 |
| 候选召回率 | 1.000000 | 1.000000 |
| CPU 评分 P95 | 0.602028 ms | 3.292009 ms |

满分只适用于当前冻结合成保留集。`shared_global_track_count` 在 74,024 条边上全部为 0，与标签互
信息为 0 bit；取值 1 的分层没有样本，无法评价。边界框对数尺度差、尺度变化率差和角速度差的
单特征最佳方向曲线下面积分别约为 0.997319、0.997340 和 0.997340，同目标样本的后两项全部为
零。这表明合成生成机制仍提供接近确定性的运动尺度线索。该统计是数据可分性诊断，不是模型特征
归因，也不能表述为真实跨视角泛化。

v2 report 文件 SHA-256 为
`b1528af84d8ad7141e146cc355c4e2e74f296d6a6b67a9bed15155d9e66940e1`，lineage 文件 SHA-256 为
`03f92ad173f695d82d10d6b9c092e00bf7a3fb40cba08e48efff10f7592b4c1d`，报告内部内容 SHA-256 为
`69cb055539f30ae9e84f1e3be25afd09e9dad5df9297ceb1d806305b530fe29e`。本次通过不改变运行默认值：
`G1=false`、`assist=false`、`authority=false`、`rule_fallback=true`，仍等待 D6 独立审计和更困难、
更接近真实相机误差的数据验证。

当前最终源码的 paired-shadow 专项回归为 `5 passed in 3.21s`，D5 全量回归为
`534 passed in 141.66s`。下列早期日期章节保留阶段证据；其中“尚未生成”或“尚未完成”只描述当时
状态，当前 paired-shadow 结论和指标一律以上述 v2 为准。

## 2026-07-21 候选图邻居预算修复（历史阶段）

clean supplemental 历史语料的 canonical test 候选召回率为
`11409/16698=0.683255`。逐级计数表明，370,211 个可能跨相机 pair 中只有 21 个被几何门拒绝；
370,190 条门后边又被独立的最终 8 邻居预算删除 125,158 条，只保留 245,032 条。损失来自最终预算
与前置 `max_tracklet_candidate_edges_per_node=24` 不一致，不来自图神经网络分类器，也不来自时间、
视场、极线、射线、重投影、协方差或全局投影门。

默认最终邻居预算现与前置预算对齐为 24。候选仍按几何门分数和匿名 tracklet key 确定性排序，
每节点最终度数严格不超过 24，边数不超过 `floor(V*24/2)=12V`，复杂度保持 `O(V*k)`。新增诊断分别
记录几何门输入、几何拒绝、最终预算删除、实际最大度数和边数上界。在线选择没有读取 evaluator
truth，没有创建、改写或换绑 `global_track_id`。

软件回归使用 seed 5、`delayed_noisy`、scale 200 的四相机困难帧。15 个节点形成 83 条门后边，
最终保留 83 条；15/15 个可评价同目标跨相机 pair 被保留，候选召回率为 1.0，实际最大度数为 12。
人为设置最终预算为 2 时，测试确认输入顺序不影响结果、最大度数不超过 2，且几何门计数与默认图
一致。专项为 `20 passed` 和 `13 passed`，D5 全量为 `529 passed in 122.96s`。

本轮没有重建 4,500 帧 clean supplemental，没有重生成 composite view，也没有重训或运行 900 帧
保留集。下文旧 clean manifest、245,032 边、`training_readiness=pass` 和相关哈希只作为修复前历史
证据；它们不能证明当前 24 邻居配置已经通过正式准入。G1、assist、在线身份和相机控制权限保持关闭。

## 2026-07-21 保留 seed 独立图评估（历史管线阶段）

D5 已增加独立 held-out producer、严格 loader 和 development bundle 评估入口。正式目录固定为
`1000-1019` 共 20 个保留 seed；每个 seed 覆盖冻结的 9 类场景和 5 个规模，共应生成 900 个图帧。
该入口不读取训练 `0-99` registry，也不形成 train、validation 或 test 划分。每个 episode 只标记
`held_out_evaluation`。formal 与 supplemental 源只绑定 manifest 哈希，目标目录必须不存在，全部
图、标签、描述符、配置和 evaluator lineage 在同级临时目录校验后原子发布。

图生成继续使用现有三维质点、针孔投影和默认时间、极线、射线、重投影及协方差候选门。在线图只
保存匿名相机局部 tracklet；truth 位于独立 label 和 gzip lineage，并按 observation、tracklet、时刻、
相机和确定性实体规则逐项复核。loader 拒绝 `0-99` seed、cell 缺失、同相机候选边、未标注边、
manifest/graph/label/lineage 哈希变化、来源/输出重叠和候选门漂移。

评估入口只接受严格加载的 `development_only_fail_closed` bundle，直接使用 bundle 内 validation
温度和判决阈值。在整体和 45 个 cell 上计算精确率、召回率、F1、错误合并率、候选召回率、期望
校准误差和实测推理延迟。接口没有训练、调温度或选阈值路径，并在前后复核权重、模型配置和
held-out manifest 哈希。评估 JSON 与中文 Markdown 始终把 paired shadow 标为 `not_run`，把 G1、
assist 和 authority 保持关闭。

当前只运行了 1 个保留 seed、2 个 cell 的代表性 smoke，生成 2 帧并完成冻结 bundle 评估合同；
随机开发模型按真实指标保持 `fail_closed`。专项测试为 `17 passed in 1.09s`，D5 全量回归为
`527 passed in 120.93s`。正式 900 帧尚未生成，也未运行正式 held-out 指标或 paired shadow。
另用 1 个 seed 覆盖全部 45 cell 做成本 smoke：45 帧、2,404 边的生成与 strict reload 用时
0.686 s，占用 613,567 bytes/138 files；一次延迟重复的随机模型评估用时 0.117 s。按帧线性估算，
900 帧约需 14 s、约 12.3 MB 和 2,703 个文件；正式执行应预留 30 s 与 20 MB，并以实际记录为准。
本节不包含 AirSim 或在线控制证据。

## 2026-07-21 Composite 内部训练适配器（历史预检阶段）

D5 已增加 formal complete frames 与 clean supplemental full corpus 的只读训练入口。入口严格复载
两类源、detached composite view、admission report 和 training/shared seed registry，强制完整
seed 原子 `60/20/20`、排除 `1000-1019`、覆盖每个 split 的 45 个场景规模单元、标签完整和同相机
候选边为 0。默认配置固定为原生 PyTorch、CPU 单线程、30 epoch、32 维隐藏层和两轮消息传递；
PyTorch Geometric、在线 truth 特征及本地 `global_track_id` 绑定均未引入。

本轮对 clean composite 实际执行只读 preflight：4,972 个图帧、245,040 条候选边，train/validation/
test 的正边为 `34539/11350/11409`，负边为 `112314/37694/37734`，未标注边为 0，每个 split 均为
45 个 cell。preflight 文件 SHA-256 为
`f4a498582cffa6672aa5775311f39ea1f5f12756383c9216ff04cbf8aaa026a8`；运行耗时 29.72 s，峰值
RSS 约 896 MiB。当前实现尚未提交，因此 provenance 记录 `repository_dirty=true`；预检没有调用
训练函数，也没有生成权重。

全量 clean 内部训练完成后，训练适配器会从实际 training report 和 bundle 另写
`d5.tracklet-graph-model-evaluation.v1` 报告，供 D6 与 `weights.pt`、bundle `manifest.json` 三件套
消费。报告只包含实际 test 指标、20 个 test seed、45 个 cell 指标和实测延迟；每个 cell 的
`sample_count` 是该 cell 的 `labeled_candidate_edge_count`，不是 episode 数。该报告只属于内部模型
测试证据，不包含保留 seed 或 paired shadow，也不开放 G1、assist、在线或相机控制权限。

2026-07-21 新增 composite 专项 `12 passed in 1.05s`，D5 全量为
`510 passed in 121.82s`。正式 30-epoch 训练、最终 `.pt`、保留 seed `1000-1019` 独立评估和
同 seed paired shadow 均未执行。

## 2026-07-21 跨视角困难样本数据支持（历史首轮语料）

D5 已完成冻结正式语料的未标注边溯源审计。正式语料共有 99 条未标注候选边和 194 个缺失端点，
其中 95 条边两端均缺来源链，4 条边缺源端来源链。冻结导出没有保存可与 episode、匿名 tracklet、
量测时刻和 source observation 同时精确绑定的离线来源记录，其他帧也没有同 tracklet 的 evaluator
标签，因此可靠回填为 0。99 条边继续标记 `unavailable`；未使用最近邻、轨迹连续性或几何相似度
伪标签，正式 graph、label 和 manifest 均未修改。

独立 supplemental producer 已实际生成 100 seed、45 个场景规模 cell、4,500 个图帧和 66,726 个
匿名节点。245,032 条默认几何门候选边中，正边 57,292 条、困难负边 187,740 条、未标注边 0，
标签可用率 100%。课程覆盖不同相机基线、密集交叉、遮挡进入/遮挡/退出、时间偏差、外参位置与
姿态扰动、漏检、虚警和重入 tracklet 碎片。在线图不含 evaluator truth；精确观测来源链位于物理
分离的 gzip 制品。与正式源重复 graph、edge 和 episode 的违规数均为 0，seed `1000-1019` 未进入
课程。

detached formal + supplemental 组合视图按共享 seed registry 原子形成 `60/20/20` 分割。视图选入
472 个标签与候选召回均完整的正式帧及全部 4,500 个补充帧，共 4,972 帧和 245,040 条边。训练、
验证、测试的无边比例为 `8.68%/10.34%/10.45%`，正边为 `34539/11350/11409`，负边为
`112314/37694/37734`，可评价同目标候选 pair 为 `50103/16683/16698`，各分割双类场景规模 cell
比例均为 100%。现有数据量与标签门全部通过。

main 已在 detached clean worktree 基于提交
`79b2550ce2ef407c7cfcc653ce04a80fe2226c06` 同配置复生，并将 clean output 保存为
`outputs/tracklet_graph_supplemental_curriculum_20260721_clean_79b2550_r2`。补充 manifest 为
`4b9875fee86b5c425f683a6da23e6af1308bcf2383d3633d4fd6207fe2f25a32`，组合 admission view 为
`11e8acbdbe268574ead402f2be5c9aa8e3459a7e4147a18e0570df3402892415`。来源 dirty=false，数据支持和
JSON 字段 `training_readiness` 均为 `pass`，原 dirty provenance blocker 已关闭。

这里的 `training_readiness=pass` 只表示 formal + supplemental 训练数据满足来源、数量、标签、切分
和完整性门。没有训练新模型、没有生成 `.pt`，promotion 状态仍为
`awaiting_new_model_evidence`，G1、assist 和在线/相机控制权限均保持关闭。保留 seed 独立模型评估
和同 seed shadow 尚未完成。clean supplemental 与 composite view 已在主工作区严格复载，专项测试为
`12 passed in 5.40s`；此前 D5 全量回归为 `498 passed in 124.90s`。

## 2026-07-21 Supplemental BC 全样本 clean 审计

D5 已对 `outputs/active_vision_supplemental_curriculum_20260721_clean_13e3728` 执行只读、
fail-closed 的 behavior-cloning 全样本准入审计。接受阈值为 100 episode、1200 sample、canonical
episode `60/20/20` 与 sample `720/240/240`、全部文件 SHA 命中、1200 个样本的 35 维候选特征全部
有限，以及 truth/reserved/dirty/审计违规均为 0。实测为 100/800/1200，dataset 内 302/302 个
checksummed 文件通过，100 descriptor、100 online、100 offline 集合完整；1200/1200 样本特征有限，
共 7800 个候选特征行，规则示范在候选集中 1200/1200 唯一。intent、FOV、角色分别为
`200/600/200/200`、`1000/200`、`600/600`，版本单调且逐样本一致，唯一中心引用保持调用方提供的
`CENTER-CURRICULUM-TRACK-ALPHA`，D5 未创建、改写或换绑。

证据位于 `results/active_vision_supplemental_bc_full_sample_audit_20260721.json` 和
`reports/D5_ACTIVE_VISION_SUPPLEMENTAL_BC_FULL_SAMPLE_AUDIT_20260721.md`，审计内容 SHA256 为
`a11b65596a4c416deba6d0cb35dcc0c32342a5bae0481291d43e8de0e26550dd`。dataset manifest、canonical
view、dataset config、training registry、shared registry、producer summary content SHA 仍分别为
`0c474ee1b0bab34a46c2ebce328761983cf2ecc757da30c2d3d2e03a06cd1acf`、
`0ab1a4a6bdd439f6c8a74df5059de3c4950791fba35a1b9514942e83779f72a8`、
`e93ca6310338be5db4539fac195f5257e28d16a64b78b1a0351bf6aeca01fcee`、
`2ab928a476a4430b99326f245222f058bc5be5025158134ba89b01b3dec7815f`、
`68608d29d1f733beea87f1faf06464fededb68a9c2972c51c10cd4c2160f032f`、
`0577c73810413ced6277e679477422f467cb2db094f1d376e39e4cbb2a3abd65`，clean source commit 为
`13e37286d2996a227924bb1a8e2766e52116a534`。supplemental 树保持 308 files/约 2.2 MiB；正式
900-episode 树保持 43973 files、SHA256
`8ffbe5cf044d121163c8acc3dce1bbd54e14bb6b211b8e1cf440f24c93294fca`。

该证据关闭 supplemental producer/canonical 后续的 BC 全样本审计子项，但不是模型训练、D6
跨模块准入或 runtime 权限证据。`applied/rejected/missing=400/400/400` 仍只表示 synthetic 故障注入
覆盖，不是实际 ACK 分布；reward/outcome/counterfactual/causal 均为 `0/1200 available`，未补零。
PPO、assist、online/camera authority 保持 false，rule fallback required=true。下一步为 main/D6
跨模块学习准入审计、真实 runtime ACK/outcome 归因与 paired shadow；本轮未训练、未运行 AirSim、
未写 `.pt` 权重，也未修改两棵数据树。
新增专项 `4 passed in 35.72s`，D5 全量 `486 passed in 119.63s`，接受阈值均为零失败。

## 2026-07-21 B1b2 clean evidence

main 已在 detached clean worktree `13e37286d2996a227924bb1a8e2766e52116a534` 完成实际 CLI 生成：ignored output 为 `outputs/active_vision_supplemental_curriculum_20260721_clean_13e3728`，tracked JSON/中文报告位于 `results/active_vision_supplemental_curriculum_20260721.json` 与 `reports/D5_ACTIVE_VISION_SUPPLEMENTAL_CURRICULUM_20260721.md`；实测 100 episode/800 segment/1200 sample，canonical seed/episode `60/20/20`、sample `720/240/240`，intent `200/600/200/200`、FOV `1000/200`、role `600/600`、故障注入 ACK `400/400/400`，online truth/reserved overlap/dirty episode/audit violation 均为 0。dataset manifest、canonical view、config、training registry、shared registry、summary content SHA 依次为 `0c474ee1b0bab34a46c2ebce328761983cf2ecc757da30c2d3d2e03a06cd1acf`、`0ab1a4a6bdd439f6c8a74df5059de3c4950791fba35a1b9514942e83779f72a8`、`e93ca6310338be5db4539fac195f5257e28d16a64b78b1a0351bf6aeca01fcee`、`2ab928a476a4430b99326f245222f058bc5be5025158134ba89b01b3dec7815f`、`68608d29d1f733beea87f1faf06464fededb68a9c2972c51c10cd4c2160f032f`、`0577c73810413ced6277e679477422f467cb2db094f1d376e39e4cbb2a3abd65`；正式 900-episode 输入树前后 SHA 同为 `8ffbe5cf044d121163c8acc3dce1bbd54e14bb6b211b8e1cf440f24c93294fca`。该证据关闭 clean supplemental producer/canonical 子项；后续 supplemental BC 全样本审计也已由上节证据关闭。ACK 仍只表示 synthetic 故障覆盖，四类离线 label 均为 `0/1200 available`，PPO/assist/online/camera authority 保持 false，下一步为 main/D6 跨模块准入审计，本次未训练、未运行 AirSim。

## 2026-07-21 主动视觉 supplemental curriculum B1b2

D5 已实现独立 100-seed supplemental curriculum 的生成、严格审计和原子发布接口。入口
`generate_active_vision_supplemental_curriculum()` 要求调用方显式提供输出目录、training/shared
registry、创建时间、Git provenance 和中心拥有的 `global_track_id`；CLI 还将这些关键参数设为
required。D5 只读复制中心 ID，不创建、改写或换绑。输出目录必须不存在，全部制品先在同级临时
目录完成 staging、finalize、lazy load、canonical view、readiness 和二次审计，最后以
`os.replace()` 一次发布；异常会清理临时目录。

training registry 与 shared registry 各自解析后的父目录均是受保护的只读 source root。若 shared
registry 位于 training root 下，外层 training root 覆盖完整正式输入树；若二者分属不同目录，则
两个根分别受保护。`output_dir`、tracked JSON 和 tracked Markdown 等于或位于任一 source root 下时，
producer 会在创建目的、临时或 tracked 目录前失败关闭，避免把补充制品写入正式 900-episode 输入树。

producer 读取并绑定 100 个 training seed、`1000-1019` 保留 seed、两个 registry schema/file
SHA256 和 shared content/assignment 合同。每个 seed 复用 B1b1 builder 生成 1 episode、8 segment、
12 sample，再复用现有 online staging、显式 unavailable offline labels 和 v3 finalizer。聚合覆盖为
100 episode、800 segment、1200 sample；intent 为 `200/600/200/200`，FOV 为 `1000/200`，角色为
`600/600`。applied/rejected/missing 各 400，只表示每 seed `4/4/4` 的确定性故障注入覆盖，不是
真实 runtime 频率、动作结果或收益证据。

detached canonical view 复用 shared registry 得到 seed/episode `60/20/20`、sample
`720/240/240`，不改源 manifest、episode 或 sample。审计逐项检查 seed/UID/sample、版本单调、
caller-owned ID、truth guard、synthetic/dirty provenance、保留 seed、四类 intent、两类 FOV、
两角色、三类 ACK、dataset/view/config/registry SHA。reward、outcome、counterfactual、causal label
全部显式 unavailable；PPO、assist、在线 authority 和相机命令权均为 false。dirty 输入可形成审计
制品，但状态固定为 `fail_closed_dirty_source`，不能冒充 clean development 数据。

生成的 curriculum Markdown 使用中文标题、说明和约束，并保留技术 token 与 SHA。2026-07-21
软件验收为新增专项 `15 passed in 71.87s`、D5 全量 `482 passed in 83.05s`，接受阈值为零失败。

上述 pytest 输出全部位于临时目录，是软件阶段的历史验收；其后 main 已在 clean revision
`13e37286d2996a227924bb1a8e2766e52116a534` 完成实际 CLI 生成并关闭 supplemental
producer/canonical evidence，见本文顶部。该 clean synthetic 制品没有训练或 AirSim 证据，也不改写
正式 900-episode 数据。supplemental BC 全样本审计现已由本文顶部证据关闭；开放项只剩 main/D6
跨模块准入审计、真实 runtime ACK/outcome、
reward/counterfactual/causal、paired shadow 及 PPO/assist/authority 准入。

## 2026-07-21 主动视觉宽视场稳定门

确定性主动视觉规则已增加“宽视场保持直到绑定稳定”状态门。状态按
`camera_id + global_track_id + plan_version + coalition_version` 隔离，默认要求连续 3 个具有严格
递增时间戳的有效投影帧。首帧和第二帧仍输出 `OBSERVE_TARGET + WIDE`；达到窗口后，只有投影
协方差继续满足既有不确定度门才允许 `ZOOM`。配置 `zoom_stability_window_frames=1` 可恢复原来的
即时缩放语义，旧调用不需要新增参数。

有效帧仍需通过原有新鲜度、可见概率、遮挡、关联置信度、视场内、当前分配、版本、通信和友方
保留门。计划、联盟、目标、时间顺序或证据状态变化会清空该相机的计数；近等质量的多目标投影按
可配置分数间隔判为歧义并回到 `REACQUIRE + WIDE`。重捕获和扫描主动选择宽视场；云台忙时清除
计数并保持当前视场，恢复后重新经过宽视场窗口。不同相机不共享状态。该变化不修改
`global_track_id`、动作 DTO、同相机互斥或运行时权限。

当前 snapshot 没有 runtime ACK 或 `last_accepted_command_version` 输入。本阶段没有构造替代 ACK，
只使用已有 `slew_available/action_in_progress_until` 处理相机忙状态。定向主动视觉组合测试
`47 passed`，D5 全量 `437 passed in 10.28s`。宽视场阶段当时未运行 AirSim、未生成课程数据、
未训练模型；其后的 B1b2 clean producer/canonical evidence 已由 `13e3728` 制品关闭，但没有增加
真实 runtime ACK/outcome、离线因果标签或模型准入证据。
GNN 与主动视觉模型继续失败关闭或 development shadow-only。既有 v5 development bundle 绑定旧
实现哈希，按严格 loader 会因本次规则实现变化拒绝加载；本轮没有重写或追认旧权重。

## 2026-07-21 共享 canonical seed 只读视图

D5 已为正式跨视角图数据和主动视觉 episode 数据实现独立的 canonical split view。视图先调用原有
strict loader 校验全部源制品，再独立复算 main-owned `scalable3d-shared-seed-split-registry-v1`。
它只在内存中按数值 seed 重分完整 episode，不改原 manifest，不复制图、在线流或离线标签。任一
源 hash、注册表 hash、schema、policy、seed 缺失/多余/重复、错桶或保留 seed 泄漏都会失败关闭。

两类正式数据均绑定 training registry
`2ab928a476a4430b99326f245222f058bc5be5025158134ba89b01b3dec7815f` 和 shared registry
`68608d29d1f733beea87f1faf06464fededb68a9c2972c51c10cd4c2160f032f`。canonical seed 为
`60/20/20`，保留 seed `1000-1019` 泄漏数为 0。图数据 canonical episode 为
`7715/2574/2562`，候选边为 `281/116/83`；主动视觉 episode 为 `540/180/180`，样本为
`695705/229651/227886`。原数据树内容哈希在生成前后保持：图数据
`b3bccc7eb4b9c3d27874fae162a277e70c0f11a3ebcf680f90982cf86b18ab79`，主动视觉
`46f7b415a2ed29a6f0f1370b075fe9d2c768bfba49c9d0a64a779039453c20e6`。

`canonical_seed_view.py` 提供 detached manifest CLI/API。图 readiness、图训练/评估和主动视觉
行为克隆只有显式同时传入 view manifest、training registry 与 shared registry 才使用 canonical
分桶；未传参数时保持旧 loader 和旧 split。D4/D5 的 split 身份不一致已在数据视图层关闭，但旧
development bundle 仍绑定原 split，未在本轮重训。图数据 `97.52%` 无边、困难负边不足和候选召回
不完整；主动视觉 `hold=0`、`observe_target` 召回为 0、无 applied-action ACK/reward 归因。
G1/assist 与 PPO 均继续失败关闭，规则回退保持必需。

正式证据位于 `results/*canonical_seed_view_20260721.json`、
`results/*canonical_seed_readiness_20260721.json` 和
`reports/D5_*_CANONICAL_SEED_VIEW_20260721.md`。main 仍需在 VERSIONING 中登记 D5 view schema、
正式 manifest/hash 和“权重不进入普通 Git”的既有规则。

## 2026-07-20 主动视觉行为克隆正式开发训练

D5 对正式 `d5_active_vision` 数据完成只读严格审计和全量行为克隆。数据包含 900 个 episode、
1,153,242 个样本，train/validation/test 为 `540/180/180` episode、`685005/238354/229883`
样本和 `60/20/20` 个唯一 seed。三个分割 seed 无交集，保留评估 seed `1000-1019` 未进入训练。
数据集 manifest SHA256 为
`cd2ee22e8566bb14938d34aa997c850c13bf1ec9c8bd09061089c7fcc7ac3d9d`。

固定 seed `20260720` 在完整 train split 上训练 5 个 epoch，每个 epoch 使用全部 685,005 个样本。
最佳 epoch 为 5，train/validation/test 损失为 `0.106584/0.105403/0.109311`，test 精确动作准确率
为 `0.955978`。该总体数值受类别不平衡支配：`reacquire` 占 `92.16%`，test 中 4,051 个
`observe_target` 样本召回率和 F1 均为 0，`hold` 没有正样本；侦察相机 test 精确动作准确率仅
`0.621823`。模型不能据此替代规则策略。

单候选集 CPU 前向 P50/P95/P99 为 `0.1074/0.1203/0.2220 ms`。严格审计、缓存构建、训练和评估
分别耗时 `786.998/1348.215/53.043/10.630 s`，全流程 `2239.694 s`，峰值 RSS
`1865.87 MiB`。验证集温度缩放得到 `T=0.906731`，test 负对数似然由 `0.109311` 降至
`0.108656`，但 15-bin 期望校准误差由 `0.020389` 升至 `0.020856`，因此未写入 bundle。

bundle 为 `d5.active-vision-model-bundle.v5`，状态固定为 `development_shadow_only`，只允许
shadow 加载；assist 加载以 `bundle_assist_not_admitted` 失败关闭。PPO 未启动，规则回退必需，模型
没有相机命令权。权重 SHA256 为
`829d016611967d7f7adddcb58c99a96e418486e33a7fc987042a16d294c2b77b`，完整 bundle 只保存在
ignored 的 `outputs/active_vision_bc_formal_20260720/`。可跟踪指标与报告位于
`results/active_vision_bc_formal_20260720.json`、`results/active_vision_bc_calibration_20260720.json`
和 `reports/D5_ACTIVE_VISION_BC_FORMAL_20260720.md`。D5 全量回归为 `414 passed`。

下一步 producer 必须补充 `hold`、`observe_target` 和侦察相机动作覆盖，并在 shadow 请求后记录
runtime ACK、实际执行结果和安全回退。当前 1,063,214 条 observed outcome 只是无动作归因的相邻
观测，不作为 reward。2026-07-21 canonical view 已关闭 D4/D5 split 身份不一致；联合模型仍因
标签、准入和运行合同未满足而关闭。main 需在 VERSIONING 中同步 bundle v5、canonical view 和本地
ignored 权重定位。

## 2026-07-20 正式图数据训练前审计

main 已在 `learning_generation_v1_multibatchfix` 完成 900 episode 正式生成。D5 对其中
`d5_tracklet_graph` 执行只读严格加载，逐项复算 12851 个图文件和 12851 个标签文件的 SHA256，
校验 dataset/graph/label schema、节点/边特征版本和顺序、整 seed 原子分割、split/training-set
hash。train/validation/test 唯一 seed 为 `60/20/20`，互相无交集；保留评估 seed
`1000-1019` 没有进入训练。

数据完整性通过，训练准入失败关闭。`12532/12851` 帧没有候选边，edge-free 比例为 `97.52%`；
train/validation/test 候选边为 `286/99/95`，负边只有 `11/4/4`。candidate recall 仅在
`4/1/1` 个可评价同目标跨相机 pair 上得到局部 `1.0`，不能作为准入证据。负边全部来自
`200v200` 的 5 类场景，5/20/50/100 规模没有形成负边覆盖。

新增 `tracklet_training_audit.py`，冻结 edge-free、正负样本、candidate-recall availability/pair
支持、场景规模双类别覆盖和 20 个测试 seed 门。正式入口仍要求完整验证真值；显式开发模式只在
已标注候选边上训练并永久标记 `development_only_fail_closed`。模型 bundle 升为 v3，绑定数据集、
split、训练集、训练配置、readiness audit、特征版本和实现代码 SHA256，且固定
`default_model=false`、`g1_assist_eligible=false`。

固定 seed `20260720` 的 40-epoch CPU 开发训练选择 210 条正边和 11 条负边，最佳 epoch 38。
验证/测试已标注边 F1 为 `0.9804/1.0`，但两者各只有 4 条负边；误合并率与完整 candidate recall
不可用。权重 SHA256 为
`9bbe53d6cab52e529155b8b92318e98e9bf7e373846fdee38a1f3b39235cbf2d`，两次固定 seed 运行一致。
完整 bundle 只位于 ignored 的 `outputs/tracklet_graph_readiness_20260720/`，不使用普通
Git 提交。可跟踪摘要见 `results/tracklet_graph_training_readiness_20260720.json`，详细报告见
`reports/D5_TRACKLET_GRAPH_TRAINING_READINESS_20260720.md`。

2026-07-20 新增专项并入后，D5 全量为 `412 passed`。下一轮 producer 必须增加独立
场景/seed 的跨相机共同可见窗口、几何可混淆负例和完整离线 pair 分母；不得复制样本或降低在线
身份、几何、同相机互斥和 `global_track_id` 所有权门。main 还需在 `VERSIONING.md` 同步 bundle
v3 和“无 git-lfs 时权重只保存在 ignored outputs”的规则。

## 2026-07-20 同相机多到达批次处理

正式 `learning_generation_v1_oosmfix` 已写入 209 条完成记录（sequence 0-208），下一项
`communication_degraded` 200v200 在 D5 入口失败，异常为
`one adapt_batches call may contain at most one batch per camera stream`。通信退化时，一个运行周期会
排空此前已到达的队列，同一 `(resource_id, camera_id)` 出现多个扫描批次是合法接收语义。原限制是
OOSM 修复时为简化无副作用预检增加的临时假设，不适用于积压队列。

`adapt_batches()` 现在分两阶段执行。第一阶段完成真值隔离、字段有限性、相机命名空间、观测来源
唯一性和全部时序预检。批次按
`(arrival_timestamp, resource_id, camera_id, measurement_timestamp)` 确定性排列，各相机使用独立的
暂存 arrival/measurement 高水位。任一重复 arrival、已提交 arrival 回退或重复 measurement 都在
任何 tracker 状态变化前拒绝整个调用。第二阶段才按该顺序逐批提交；合法 OOSM 仍只推进 arrival
高水位并输出 `oosm_ignored`，不倒写局部轨迹状态。

`process()` 保留全部适配批次用于时序审计，但单时刻关联图只使用每个相机最后一次有效状态更新。
这避免同一稳定 `tracklet_key` 的多个历史版本同时进入稀疏图，也避免后到 OOSM 几何覆盖当前状态。
每个 tracker 另以有序时间戳登记已接收 measurement；它只用于识别较早正常帧或已忽略 OOSM 的
再次重传，不参与运动估计、局部 ID 或中心绑定。

2026-07-20 定向适配器测试 `31 passed`，D5 全量 `410 passed in 11.68s`，语法和格式检查通过。
测试覆盖同流两正常批次、正常/OOSM 混合、历史 measurement 重传、三类原子失败关闭及多相机多批次
确定性。在线路径没有
读取 truth/object/actor ID，没有创建或改写 `global_track_id`，也没有固定相机或目标数量。

该证据关闭 D5 代码级多批次阻塞，不证明正式 900 episode 已恢复或完成。按照 `VERSIONING.md`，
main 必须在同时包含 D5 与 runner 修复的新干净提交上，使用新输出目录从 sequence 0 开始重建正式
900 episode 数据集，再复核 900 条进度、有限状态、online truth use=0、checkpoint 和全部 D5 数据
制品。绑定 `c5a9f6d` 的旧 209 条目录只保留为故障证据，不得恢复、续写或与新数据集拼接。

## 2026-07-20 通信退化场景的视觉 OOSM 处理

正式 45-episode 分块在前 29 个 cell 完成后，于 `communication_degraded` 200v200 的 sequence 29
进入 D5 时失败。批次已经按 `arrival_timestamp` 到达，但相机本地跟踪器要求
`measurement_timestamp` 单调。通信延迟和抖动使旧量测晚于新量测到达，这属于合法的乱序量测
（Out-of-Sequence Measurement，OOSM），不能通过重排或改写时间戳消除。

每个 `(resource_id, camera_id)` tracker 现在分别维护到达时间和量测时间高水位。规则为：

- 到达时间必须严格推进；回退和相同到达时间的重复输入在任何状态变化前失败关闭；
- 量测时间高于高水位时按原路径更新局部轨迹；
- 量测时间等于高水位时判为重复帧并失败关闭；
- 量测时间低于高水位但到达时间合法时，保留原始双时间戳和相机几何，输出
  `status=oosm_ignored`，不创建 ID、不更新中心/框/速度、不增加命中或漏帧、不老化当前轨迹；
- 批次 metadata 记录 `temporal_status`、是否更新状态、累计 OOSM 忽略数及两个时间高水位。

当前轻量 tracker 没有固定时滞回放历史，因此忽略 OOSM 的状态更新比把当前状态回退到过去更
保守。在线 payload 仍不含 truth/actor/object identity，`global_track_id` 所有权和只读规则不变。
OOSM 修复当时的定向适配器测试为 `24 passed`，D5 全量为 `403 passed in 9.74s`。原失败目录只有
29 条 progress，不能跨 revision 直接恢复。main 随后在修复提交和新目录
`learning_generation_v1_oosmfix` 完成 209 条进度，原 sequence 29 OOSM 异常未再出现，且至少完成
一次 checkpoint resume。该证据关闭原 OOSM 运行阻塞。第 210 项暴露的同相机多批次问题由上节
处理；正式 900 episode 仍未完成。

## 2026-07-20 active-vision staging 性能修复

D5 owner 对 200 camera、400 center track、1 个共享 snapshot、200 个 camera sample 的确定性
fixture 分别测量 sample/record 构造、online writer、offline join、materialized load 和公共 audit。
修改前工作树基于提交 `153ba1ec4dc89903802ac48ede9ef1fa57a68a53`。主要根因不是 gzip：同一冻结
snapshot 在每个 camera sample 构造和物化时重复执行中心引用扫描与递归 truth-free 审计；writer
还会为 snapshot/feedback 重复规范化 JSON、计算对象键并在写行时再次扫描。

修改后，同一冻结 snapshot 只建立一次弱引用生命周期内的中心引用索引。每个 sample 仍独立检查
动作、计划/联盟/通信版本、相机反馈、ACK、有限动作集和 sample-owned truth-free 字段；writer 在
持久化边界对 snapshot 执行一次不使用缓存的强制复核。规范化 snapshot/feedback 字节同时用于
SHA256 对象键和流式写入。公共 audit 仍独立从磁盘解压、验哈希、审计每行并失败关闭。

| 200/400 fixture 指标 | 修改前 | 修改后中位数 | 结果 |
| --- | ---: | ---: | --- |
| fixture 构造 | 2.3597 s | 0.1097 s | 约 21.50 倍 |
| online stage | 0.0634 s | 0.0432 s | 约 1.47 倍 |
| materialized load | 2.3948 s | 0.1802 s | 约 13.29 倍 |
| fixture 构造 truth-audit 调用 | 80,601 | 1,001 | 重复共享快照扫描消除 |
| online canonical JSON 调用 | 809 | 407 | 对象 payload 只编码一次 |
| online object-key helper 调用 | 402 | 0 | 直接复用已编码字节 |

fixture 的 gzip 仍为 level 6、`37,001` 字节，解压后为 `732,814` 字节；修改前后 gzip SHA256 和
解压流 SHA256 均完全相同。既有 200v200、`3,536` sample、17 snapshot 制品的 writer 为
`3.5529→0.7313 s`，materialized load 为 `38.0052→2.8435 s`，writer 输出逐字节相同。验证脚本与
结果位于 `simulations/profile_active_vision_episode_staging.py` 和 `results/active_vision_staging_*`。
新增确定性、调用计数、解压语义等价和写盘前真值注入拒绝测试；D5 全量 `400 passed in 9.74s`，
接受阈值为零失败。schema、公开 DTO、采样、特征、压缩级别、中心 ID 只读、版本/ACK、SHA256、
只读和 whole-seed split 合同均未改变。

该结果关闭 D5-owned writer/sample 重复处理子项。main 随后在 clean-tree 下复跑同一 nominal
200v200、2 s、seed 930-932，系统级结果见下一节；D5 writer P1 已由真实 episode 计时关闭。正式
900-episode corpus、BC/PPO、20 个未见 seed、checkpoint、paired shadow 和 assist 准入仍未完成。
本次没有改变 AirSim 相机、检测器、云台或运行接口，`docs/AIRSIM_INTEGRATION_PLAN.md` 检查后无需
修改。

## 2026-07-20 200v200 clean-tree postopt2 系统复测

main 在提交 `45b36500dc3c6935b1f116614993e291041eb12d` 上运行 nominal 200v200、2 s、
seed 930-932。证据目录为
`outputs/capacity_probe_v2/nominal_timed_postopt2/`。三场均为有限状态，
`repository_dirty=false`、`online_truth_use_count=0`；D5 匿名 tracklet graph 正常最终化。

| seed | episode run | artifact staging | D5 active-vision staging |
| ---: | ---: | ---: | ---: |
| 930 | 34.3668 s | 4.1704 s | 4.0494 s |
| 931 | 41.8854 s | 4.1311 s | 3.9898 s |
| 932 | 48.4893 s | 4.1357 s | 3.9995 s |

相对 postopt1，总 artifact staging 由 `126.4682 s` 降至 `12.4372 s`，总生成由
`262.2866 s` 降至 `144.5513 s`。批次 finalization 由 `7.7377 s` 降至 `7.2777 s`，episode run
由 `127.9871 s` 变为 `124.7415 s`。D5 active-vision staging 从历史
`41.5623/43.2639/41.2271 s` 降至 `4.0494/3.9898/3.9995 s`。这组同配置、同 seed、干净工作树
证据关闭 D5 writer P1 的系统级复跑项；它是离线学习制品写入改进，不是在线关联或仿真实时性
结论。

本批只有 3 个唯一 seed，预检只得到 1 个测试 seed。active-vision dataset 因
`insufficient_unseen_test_seeds` 保持未最终化；正式 900-episode corpus、至少 20 个未见测试
seed、正式训练、checkpoint、paired shadow 和 assist 准入继续开放。

## 2026-07-20 200v200 clean-tree postopt1 历史复测

main 在提交 `4052d9411363c39d52100c0e3a4f60ee88443cab` 上复跑 nominal 200v200、2 s、
seed 930-932。产物记录 `repository_dirty=false`，可与优化前
`outputs/capacity_probe_v2/nominal_timed/` 直接比较；优化后证据位于
`outputs/capacity_probe_v2/nominal_timed_postopt/`。

| 阶段 | 优化前 | 优化后 | 判定 |
| --- | ---: | ---: | --- |
| episode run | 125.2205 s | 127.9871 s | 基本持平，本轮未优化在线仿真 |
| artifact staging | 225.9243 s | 126.4682 s | 降低约 44.0% |
| finalization | 116.5624 s | 7.7377 s | 降低约 93.4% |
| generation total | 467.8007 s | 262.2866 s | 降低约 43.9% |

三场 D5 graph staging 分别为 `0.0250/0.0259/0.0290 s`，图数据正常最终化。该次历史复测的 D5
active-vision staging 分别为 `41.5623/43.2639/41.2271 s`，占对应 episode artifact staging 的
99.6% 以上，因而触发了上节专项剖析。D5-owned writer/sample 重复处理现已修复；这组三 seed
数据保留为 postopt2 的直接基线，不能再解释为当前 writer 性能。

三 seed 只能规划出 1 个测试 seed，未达到正式准入要求的 20 个未见测试 seed，因此 active-vision
dataset 以 `insufficient_unseen_test_seeds` 失败关闭并保留未最终化 episode/online/offline 数据。
三场 `online_truth_use_count=0`。正式 900-episode corpus、行为克隆（BC）、近端策略优化（PPO）、
20 个未见 seed 的性能验收、checkpoint 与 assist 准入仍未完成。

## 2026-07-20 200v200 主动视觉数据容量与跨视角 seed 隔离

新增 `active_vision_episode_dataset.py`，把统一三维 episode 的主动视觉决策形成正式版本化数据
合同。每个 `ActiveVisionEpisodeSampleV2` 保存 truth-free `ActiveVisionSnapshotV1`、规则示范动作、
requested/effective action 与 mode、plan/coalition/communication version、相机反馈和可选 runtime
ACK。`active_vision_sample_from_decision()` 可直接从现有 `ActiveVisionDecisionV1` 构造样本；相机、
目标和资源均按输入数组工作，不存在 2v2、5v5 或 200v200 常量。原 V1 Python 类名保留为源码
兼容别名，但构造的是 v2 合同，不能读取旧 v1 嵌套文件。

容量修复前的 nominal seed 91、每档 2 s 实测 online JSON 为 5v5 `0.91 MB`、20v20
`8.84 MB`、50v50 `52.58 MB`、100v100 `218.17 MB`、200v200 `815.36 MB`（约 778 MiB）；
200v200 在 offline staging 重载并递归扫描整 record 时 RSS 约 4.2 GB，7 分钟仍未完成后由 main
主动终止。根因是同一 decision cycle 的完整 snapshot 被每个 camera sample 重复嵌入。

数据目录固定分流为：

```text
dataset_config.json
online/<episode_uid>.online.jsonl.gz
offline/<episode_uid>.offline.json
episodes/<episode_uid>.episode.json
manifest.json
SHA256SUMS
```

record v2 改为确定性 gzip JSONL：header 后写一次 SHA256-keyed camera feedback；每个唯一 snapshot
只写一次，随后写引用该 snapshot/feedback key 的 sample，最后以 footer 固化对象数、样本数和
sample-index SHA。没有删减 snapshot、action、feedback、ACK 或版本字段。16→64 camera 高基数
fixture 的旧嵌套/去重解压/gzip 字节分别为 `302709/59617/3995` 与
`4336869/234721/13084`；输入规模 4 倍时去重解压增长 3.94 倍、gzip 增长 3.28 倍，而旧嵌套增长
14.33 倍。另一个 200-camera/400-track 单 snapshot fixture 为解压 `731412` 字节、gzip `37004`
字节，`200` samples 只保存 `1` 个 snapshot。以上均为合成容量合同证据。

main 随后用新 v3 格式完成 nominal、seed 91、每档 2 s 容量复测。5/20/50/100/200v200 的 D5
active-vision 总制品约为 `0.086/0.295/0.733/1.543/2.884 MB`；200v200 中 online `1.064 MB`、
offline `1.818 MB`、`3536` samples、进程 RSS 约 `1.04 GB`，online truth occurrence 为 `0`。
该单 seed 实测关闭去重存储的容量门，但不代表 900-episode 正式数据集、训练吞吐或模型性能。

`stage_active_vision_episode_record()` 逐行写入并拒绝 truth/actor/object identity；
`stage_active_vision_offline_labels()` 必须在 episode 关闭后，以完全匹配的 `sample_key +
observation_key` 写独立 evaluator 文件。offline staging 先流式校验 online SHA、episode/source
identity、truth-free 边界、对象 key、引用、完整 sample 合同及 join keys，只保留一个当前 snapshot
和小型索引，不再调用完整 record loader。reward、outcome、counterfactual 和 causal label 不会
复制回 snapshot。reward 固定在 `[-1,1]`；缺少离线 outcome 时
`reward_available=false/value=null`，不能用 `0` 补位；causal label 还要求 factual outcome 与
counterfactual 同时可用。

`finalize_active_vision_episode_dataset()` 只对每个 staged episode 调用一次
`_read_episode_record_stream(..., materialize=False)`。该次调用生成在线合同、离线连接与实际文件
SHA256 证据；写完 manifest、checksum 和只读位后，同一次 finalization 的最终结构复核只复用仍与
设备号、inode、大小和修改时间匹配的证据，不再重复解压或哈希。文件在操作中变化时返回
`artifact_changed_during_audit` 并失败关闭。公共 `audit_active_vision_episode_dataset()` 和
`load_active_vision_episode_dataset_lazy()` 不接受该内部证据，每次调用都从磁盘独立完成一次逐文件
SHA256、逐 episode 流式合同与离线连接复核。后者返回
`LazyActiveVisionEpisodeDataset`：`iter_episodes()`、`iter_behavior_cloning_episodes()` 和
`iter_ppo_episodes()` 仅在迭代推进时物化当前 episode；其中 BC 不读取 offline label，PPO 逐 episode
核验 reward availability。原 `load_active_vision_episode_dataset()` 保留为小数据兼容全量路径。

非物化流审计不再为每条 sample 构造含共享 snapshot 的完整样本对象。原始 sample JSON 行、引用的
camera feedback 行和唯一 snapshot 行仍分别执行递归 truth-free 审计；随后轻量路径完整检查动作、
中心 ID 引用、plan/coalition/communication version、有限动作集、相机反馈、ACK、时间和版本单调性，
只保留 sample key/index 摘要。`materialize=True` 的公开 record loader 保持原对象构造和复核路径。
writer 同时复用已经生成并审计的 snapshot/feedback payload，避免写入时再次转换同一对象；字段、
采样频率和压缩格式均未改变。

`finalize_active_vision_episode_dataset()` 保持完整 `(scenario_version, seed)` group 不可分，并先以
唯一数值 seed 做确定性分配：共享同一 seed 的所有 scenario/scale group 必须原子进入同一
train/validation/test，因而 test seed 对 train/validation 完全未见。split 数量按唯一 seed 数计算；
少于三个唯一 seed、少于声明的 unseen test seed 或任一 group/seed 跨 split 均失败关闭。CLI/API
正式默认门为 20 个 unseen seed，单测 smoke 仅显式使用 1。manifest 固化
`shared_seed_values_atomic_across_scenarios=true`、全部 schema/version、逐文件 SHA256、split/
training-set SHA、source Git commit/dirty 状态、source config SHA 和 availability。finalize 后全部
制品去除写权限；loader 要求 `SHA256SUMS` 精确覆盖目录并复算哈希、版本、split、source
identity、键连接、奖励边界和中心 ID 引用。未知中心引用、相机对中心 ID 的局部换绑、版本回退
或额外未审计文件均拒绝。

`LoadedActiveVisionEpisodeDataset.behavior_cloning_episodes()` 只加载规则示范，不接触 evaluator
label；`ppo_episodes()` 只加载 effective action，并要求每个样本都有有界离线 reward，否则失败
关闭。旧 `ActiveVisionTransition.reward` 的 unavailable 表达已从默认 `0.0` 改为 `None`。split
seed split 的学习 dataset 保持 `d5.active-vision-dataset.v2`；新存储将 episode dataset 升为
`d5.active-vision-episode-dataset.v3`、descriptor/record/sample 升为 v2，绑定它的模型 bundle
升为 `d5.active-vision-model-bundle.v4`。snapshot/action/camera-feedback/runtime-ACK/offline-label
仍为 v1。旧 dataset/record/bundle 稳定失败关闭，不会被新 loader 静默解释；没有正式 admission
report 时仍不能 assist。

复核 `tracklet_dataset.py` 确认旧实现会按 `(scenario_version, seed)` 独立 shuffle，数值 seed 在
多个 scenario/scale 复用时可能跨 split。现改为唯一 seed 的 SHA256 确定性原子分配，dataset 升为
`d5.tracklet-dataset.v2`，tracklet bundle 升为 `d5.tracklet-model-bundle.v2` 并显式绑定 dataset
schema；loader 复算并拒绝跨场景 seed 泄漏。

本次 D5 复核补强三项失败关闭边界：dataset root 在 staging/finalize 时先正规化，故相对目录与
绝对目录行为一致；recorded decision 强制执行 controller 的 mode/action 矩阵，所有非 assist
effective action 必须保持同 tick 规则动作；匿名 tracklet 的 resource、camera 和 local ID 均拒绝
truth/actor/object-like 命名。

2026-07-20 当前验证：数据管线 `18 passed`、D5 全量 `400 passed in 9.74s`，接受阈值为零失败。
确定性 6-episode/48-camera/96-track 计数微基准中，finalize 在线解压/解析由 `12` 次降至 `6` 次，
offline join 解析由 `12` 次降至 `6` 次，`sha256_file` 调用由 `67` 次降至 `20` 次；20 个实际制品
各哈希一次，finalize 内部公开 audit 调用为 0。随后单独调用公开 audit 时再次产生 `6` 次在线流
解析、`6` 次 offline join 和每制品一次 SHA256，证明公开复核保持独立。200-camera/400-track 合成
stream audit 的本机辅助墙钟由约 `9.81 s` 降至约 `0.37 s`；已有 nominal/dense 200v200 gzip
（`1.066/1.134 MB`、`3536/3744` samples）独立审计约 `2.08/2.21 s`。墙钟不作为测试门，正式门是
重复调用计数、零物化、篡改失败关闭和零测试失败。既有动态数量、ACK 可选、真值分流、未知/换绑
中心 ID、SHA 篡改、reward null、共享 seed 原子 split 和不足样本失败关闭回归均保留。磁盘和公开
DTO schema/version 全部保持不变。D5 本轮没有修改 main/runtime；尚未执行
900-episode 正式集峰值/吞吐、正式 BC/PPO、20-unseen-seed 性能、checkpoint 或 paired shadow
准入。main 后续仍需以真实 source Git/config identity 和独立 outcome/counterfactual 生成正式集。

## 2026-07-20 统一三维 episode 主动视觉接线状态

main-owned `scalable_3d_simulation` 已把 D5 主动视觉合同接入统一 episode。每个决策时刻由
D2 中心 `GlobalTrack`、D3 当前 `AssignmentPlan`、D5 几何关联证据和相机反馈构造
`ActiveVisionSnapshotV1`；相机反馈包含当前 yaw/pitch/FOV 和最近接受的命令版本。在线输入继续
排除 actor/object/truth identity，`global_track_id` 只读引用中心候选。

库配置为 `disabled` 时仍执行 `DeterministicLookAtScanPolicy` 的 look-at、短时 reacquire 和
确定性 scan。`shadow` 只记录模型建议，最终命令仍来自规则路径；`assist` 未通过正式准入时也
回退规则。`RuntimeStepOutput` 已输出版本化相机观察命令，main 对 plan/coalition/communication
version、有效期和资源一致性复核后，在下一视觉帧更新模拟相机指向/FOV，并发布
`runtime.camera_command_ack`。这关闭了“统一三维 episode 尚未接线”的接口缺口。

开发冒烟中，5v5 的相机命令为 `84/84` applied；200v200 seed 17、1.2 s 诊断为
`1872/1872` applied。两组均为单 seed、脏工作树下的接口证据，只证明命令生成、门控、应用和
ACK 链路可运行，不证明可见率、重捕获时延或物理拦截收益。真实 AirSim 云台、实机执行、正式
训练数据/checkpoint、至少 20 个未见 seed 的 paired 准入和因果非退化结论仍未完成。

## 2026-07-20 可选主动视觉 BC/PPO 研究路径与量测审计连接

本轮在既有匿名 tracklet 图之外新增独立、默认不执行学习控制的主动视觉研究路径。版本化
`ActiveVisionSnapshotV1` 只包含中心 `GlobalTrack` 候选的只读 ID/version/timestamp、当前
`AssignmentPlan` 的 plan/coalition version 与成员引用、相机/云台角度和速率、wide/zoom FOV
能力、目标投影协方差、可见率/遮挡率/关联置信度、通信版本和友方 exclusive reservation。
合同没有 actor/object/truth identity、飞行控制或 D3 分配字段；递归 guard 拒绝任何此类输入。
策略输出的 `target_global_track_id` 只能从 snapshot 的中心候选和当前相机分配交集中选择，D5
不能创建、改写或重新绑定 ID。

`ActiveVisionActionV1` 统一表达 `observe_target/search_sector/hold/reacquire`，并携带有限
yaw/pitch 增量及 `wide/zoom` 模式。`DeterministicLookAtScanPolicy` 是始终可用的 look-at、
last-projection reacquire 和规则扇区扫描基线。学习策略只在规则构造的有限动作候选中选择；
`validate_active_vision_action_v1()` 对 plan/coalition/communication version、候选成员、证据时效、
FOV 支持、云台机械角、当前/请求速率、slew、友方冲突和 action timeout 再做安全投影。bundle
缺失或损坏、schema/SHA 错误、OOD、低置信、非有限输出、异常或推理超时均使用已经计算好的
规则动作。shadow 的 `effective_action` 永远等于 `rule_action`。

`ActiveVisionControllerV1` 的库默认模式是 `disabled`；`active_vision_cli.py` 默认请求
`shadow`，只做非执行 preflight。决策固定输出 requested/effective mode、fallback reason、
inference latency、model fingerprint、plan/coalition/communication version、规则动作、模型请求
动作和最终动作。`assist` 只有在 bundle 绑定的 paired shadow 报告满足至少 20 个完全未见 seed、
正式且非合成、逐 episode/总体 safety、visibility 和 reacquisition delay 均不退化时才可生效。
报告同时绑定 dataset manifest、split、training-set 和模型指纹 SHA。20-seed 合成 fixture 即使
数值全为正例也固定不能授予正式准入。

研究训练 API 位于 `active_vision_learning.py`：完整 `(scenario_version, seed)` group 进入唯一
train/validation/test split，共享数值 seed 的跨场景 group 同样原子分配；
`train_behavior_cloning()` 和 `train_clipped_ppo()` 使用原生
PyTorch actor-critic，不依赖 `torch_geometric`。bundle 为
`manifest.json + weights.pt + SHA256SUMS`，只通过 `torch.load(weights_only=True)` 加载。
仓库未提交主动视觉 checkpoint，也没有已准入模型。

scalable adapter 同步将在线 `SensorMeasurement.observation_id` 复制为只读审计字段
`CameraLocalTracklet.source_observation_id`。该键不参与 tracker 匹配、`local_track_id` 分配、
`tracklet_key`、图特征、聚类或中心 binding；同一帧重复 source ID 在 tracker 更新前拒绝。
`join_offline_observation_labels()` 仅在在线图冻结后，把 main 的 evaluator-only
`observation_id -> truth_entity_id` 转为匿名 tracklet label，并显式返回 `labels_complete`、缺标签
tracklet 和未消费 observation。假目标没有离线标签时必须是 incomplete，不能补造 truth。

CLI preflight：

```bash
PYTHONPATH=research_modules/d5_terminal_association/src \
python3 -m d5_terminal_association.active_vision_cli
```

2026-07-20 代码验证：主动视觉研究专项 `17 passed`；新增能力并入后 D5 全量
`376 passed in 9.94s`，接受门为零失败。BC/PPO smoke 使用 8 个合成 seed group、各 1 epoch；
20-seed paired 数据仅验证门控代码，并明确覆盖合成证据拒绝，不是正式准入结果。随后 main 已
接通统一三维 episode 的模拟相机/FOV 命令与运行时 ACK，但未运行真实 AirSim 云台或实机，
也没有 visibility/delay 的正式非退化证据；默认几何关联与规则观察路径保持不变。

## 2026-07-20 版本化训练与模型制品管线

本轮新增 `tracklet_dataset.py`、`tracklet_training.py` 和 `tracklet_model_bundle.py`，关闭的是
“匿名稀疏图无法形成可复核数据集、正式训练/校准和安全制品”的代码管线缺口，不是图模型
准入。`stage_tracklet_dataset_episode()` 只能从已经构造完成的匿名在线
`SparseTrackletGraph` 写图归档；图文件固定保存节点特征、候选边索引、边特征、匿名
tracklet/camera key、双时间戳、gate score 和候选计数，不保存 evaluator
`truth_entity_id` 或 `shared_global_track_ids`。真值只写入独立 `*.labels.json`，加载时以
tracklet key 和 measurement timestamp 离线对齐。

数据集 manifest 固化 dataset/graph/label schema、节点/边特征版本与精确顺序、生成配置
SHA256、逐 split class balance、candidate-recall availability 和困难负样本 provenance。
切分单元固定为完整 `(scenario_version, seed)` group；同一 group 下的所有 episode 只能处于
同一 `train/validation/test` split，禁止边级随机切分。manifest 另记录 split SHA256 和训练集
SHA256；加载使用 `np.load(..., allow_pickle=False)` 并逐文件校验 SHA、版本、shape、有限值、
feature order、label completeness 和 seed 泄漏。

正式训练按多个完整图做梯度累积，固定 Python/NumPy/PyTorch seed，按最小 geometry gate
score 选择困难负样本，并用 `pos_weight` 处理类别不平衡。模型选择、scalar temperature
calibration 和 F1 threshold selection 全部只使用 validation；test 才输出 edge
precision/recall/F1、受约束聚类后的 false-merge rate、candidate recall、Brier/ECE、P50/P95
推理时延和权重大小。缺少完整 evaluator truth 时相关指标写为
`{"available": false, "value": null, "reason": ...}`，不补零。

模型制品固定为 `manifest.json + weights.pt + SHA256SUMS`。manifest 包含模型语义版本、图/节点/
边特征版本与顺序、hidden dim、message-passing steps、训练数据及 split hash、validation-only
temperature/threshold 和验证结果；状态只用 `torch.load(..., weights_only=True)` 加载。SHA、
schema、feature order、state_dict shape 或有限值任一不符即失败关闭。在线 bundle scorer 仍只
输出现有 candidate edge 的 same-target probability；模型缺失/bundle 无效、异常、错误 shape、
非有限/越界输出、推理超时、低平均 certainty 或无效阈值均显式回退原确定性几何规则。模型
阈值之后仍由原 `constrained_tracklet_clusters()` 保证同相机唯一，再由中心投影/Hungarian
引用输入 `global_track_id`；模型不能创建、改写或换绑 ID。

CLI：

```bash
PYTHONPATH=research_modules/d5_terminal_association/src \
python3 -m d5_terminal_association.tracklet_dataset finalize \
  --dataset-dir <dataset-dir> --split-seed 20260720
PYTHONPATH=research_modules/d5_terminal_association/src \
python3 -m d5_terminal_association.tracklet_dataset validate --dataset-dir <dataset-dir>
PYTHONPATH=research_modules/d5_terminal_association/src \
python3 -m d5_terminal_association.tracklet_training train \
  --dataset-dir <dataset-dir> --bundle-dir <bundle-dir> --report <training-report.json>
PYTHONPATH=research_modules/d5_terminal_association/src \
python3 -m d5_terminal_association.tracklet_training evaluate \
  --dataset-dir <dataset-dir> --bundle-dir <bundle-dir> --report <test-report.json>
```

episode 生成端在每个在线图冻结后调用 `stage_tracklet_dataset_episode()`，再运行 `finalize`；
不能把 graph 与 evaluator labels 合成一个输入文件。

2026-07-20 验证：新增管线专项 `12 passed`，原稀疏图/adapter/新管线组合
`46 passed`，D5 全量 `355 passed in 9.48s`，接受门为零失败。测试覆盖整 seed 无泄漏、
图/真值分流、训练到评估、checkpoint round-trip、SHA/schema/feature/version mismatch、缺失
bundle、非有限输出、超时、无模型、同相机唯一和中心 ID 不变；checkpoint 均在 `tmp_path`
生成，当时未新增正式或默认 checkpoint。2026-07-25 已冻结一份严格可加载的
development-only bundle 并完成同权重审计，但它仍不是默认或已准入 checkpoint。

当前仍没有来自代表性场景的正式训练数据和准入结果。2026-07-25 的 20 个未见 seed
同权重审计使用合成匿名图，已关闭模型谱系断点；会重新执行物理候选门的困难整 episode
测试、真实遮挡/近邻交叉/漂移覆盖、冻结验收阈值以及默认 checkpoint 审批继续开放。在这些
条件完成前，几何规则仍是默认路径。

## 2026-07-20 匿名多相机 tracklet 稀疏图主线

新增 `sparse_tracklet_graph.py`、`tracklet_gnn.py` 和 `active_vision.py`。图节点严格为
`resource_id/camera_id:local_track_id` 命名空间内的 camera-local tracklet；节点合同
不含 truth、actor、object 或 `global_track_id` 字段，递归 metadata guard 和本地 ID
别名 guard 会在入图前失败关闭。本地 ID guard 除拒绝 `truth/actor/object` 字样外，还拒绝
`TGT-0001`、嵌入式 `camera:TGT-002`、`TargetDrone_1`、`Target_UAV_7` 和
`intruder-003` 等仿真真值式编号；递归 payload guard 对 `local_track_id`、`tracklet_id`、
`track_id` 和 `detection_id` 等 local-ID 字段执行同一检查。正常
`cam01-track-0001`、`local-001` 与 detector sequence ID 保持可用。中心 `GlobalTrack`
仅作为只读投影假设传入，不进入节点身份，也不能由 D5 创建或改写。

新增 `scalable_3d_adapter.py` 作为 main scalable 3D 在线 DTO 的模块-owned 入口。模块采用
duck typing，只依赖 D5 数据合同，不导入 simulator、D2 实现类或 evaluator truth 类型。
`Scalable3DTerminalAdapter` 在任何 tracker 状态更新前递归拒绝 truth/actor/object/target/entity
字段及 `TGT-*`、`TargetDrone_*`、`intruder-*` 值；`observation_id` 只读传播为
`source_observation_id` 审计键，绝不复制为 local/global ID，也不参与匹配。匿名
`trk-000001...` 由每个 `(resource_id,camera_id)` tracker 独立分配，支持 IoU/
中心距离匹配、有限漏检、episode/stream reset，并计算像素角速度、bbox 对数尺度变化、中心
协方差和 bbox `4x4` 协方差。

相机 metadata 被转换为 `CameraModel(K,R,t)` 和 `TrackletCameraGeometry`，其中
`t=-R@camera_position_ned`；显式位置/姿态协方差按原值使用。当前 main `sensor_scene` DTO 形状
没有单独发布这两项协方差时使用可配置保守 fallback，并在 batch metadata 标明来源，不能写成
metadata 实测协方差。D2 六维 `[pN,pE,pD,vN,vE,vD] + 6x6 covariance` 只读复制为 D5
投影假设，原中心 `global_track_id` 原样保留。

稀疏候选采用两级索引。第一级根据相机位姿、内参、截断视锥包围盒、相机量测时间和三维
覆盖桶生成相机对；总相机对只按 `C(C-1)/2` 计数，不构造完整列表。相机对检查受
`camera_pair_budget` 限制，同桶按索引间隔轮转、跨桶按对角线轮转，使有限预算先覆盖更多
相机。未检查相机对记录为预算丢弃并保持未绑定，不补猜身份。第二级以中心航迹投影支持和
时间近邻生成 tracklet 候选，按 `max_tracklet_candidate_edges_per_node` 在昂贵几何计算前
确定性裁剪，不再为每个相机对建立 `n_left x n_right` 中间矩阵。

保留候选边按以下顺序验证：双时间戳窗口、各自视场、双向极线距离、世界射线最近交会、
三角中点重投影、像素协方差马氏门、中心 GlobalTrack 投影与协方差门，最后执行确定性的
最终 degree cap。每条边至少携带时间差、像素马氏距离、重投影误差、射线最近距离、
bbox 尺度差和尺度变化率差、角速度差、相机基线及外参协方差；另携带极线误差、交会角、
中心投影马氏距离、置信度乘积和共享中心候选数。

`NativeTrackletEdgeClassifier` 只输出每条现有边的“同一目标”概率。模型使用原生
PyTorch MLP 和 `index_add_` 对两个端点聚合消息，不依赖 `torch_geometric`，也不输出
全局 ID。`OfflineTrackletTruthLabel` 是独立 evaluator-only 流；训练批只在在线图完成后
连接真值，按最小几何 gate score 选择困难负样本，并通过 `positive_weight` 处理类别不平衡。
最终身份仍由 `constrained_tracklet_clusters()` 保证同一相机每簇最多一个 tracklet，再由
`bind_clusters_to_center_tracks()` 对中心输入 ID 做 Hungarian 一对一绑定；输出 ID 集合被
运行时断言限制为中心输入集合的子集。

`SafeRuleScanPolicy` 提供主动视觉环境/策略安全接口。动作枚举仅含观察中心目标、搜索扇区、
云台增量和 FOV/变焦；观测超时、低置信或中心 binding 无效时轮转规则扫描扇区。它不包含
飞行动作、目标分配或火控动作。该规则路径已接入统一三维 episode 的模拟相机命令和 ACK，
尚未接入真实 AirSim 云台或实机，也没有训练或验收学习策略。

2026-07-20 固定 seed 代码证据：

| 场景 | 结果 | 代码验收门 |
| --- | --- | --- |
| seed 200，200 目标，4 相机 | 800 节点；240000 个跨相机可能对；索引后 3050 个 tracklet 候选；中心投影门/最终 cap 前 2953；最终 1923 边；密度 0.006017；最大度 6；本次实测 0.442 s | 800 节点；密度 `<0.01`；最大度 `<=6`；中心投影候选 `<2%`；运行 `<15 s` |
| 5/20/50/100/200 相机结构矩阵 | 每相机 1 个匿名 tracklet；预算为 `2C`；200 相机总对数 19900，只检查/保留 400 对，预算丢弃 19500；tracklet 候选 397；本次实测约 59.2 ms | 实际检查 `<=pair budget`；每 tracklet 候选度 `<=4`；全部相机至少进入一个候选对；不设窄绝对时延门 |
| seed 4，8 目标，3 相机小样本 | 24 节点、192 边；24 正样本、72 困难负样本；`positive_weight=3.0`；60 epoch loss `1.038521 -> 0.011535`，训练集准确率 1.0 | loss 至少下降 50%；训练集准确率 `>=0.90`；困难负样本非空 |
| scalable 3D adapter 专项 | `17 passed in 2.27s`；2/3/4 相机部分可见、跨帧稳定、假目标/漏检、7 类污染、中心 ID、reset、空扫描、model/rule 状态及真实 DTO 形状 | 零失败；污染不得改变 tracker 序列；输出 ID 只能来自中心输入 |
| D5 全量回归 | 本轮训练/制品管线同步后 `355 passed in 9.48s` | 零失败 |

相机 overlap/index bucket、camera-pair budget、tracklet 候选上限和 200-camera 结构测试已在
D5 范围内关闭原平方级候选构造缺口。诊断显式输出总相机对、索引对、检查对、预算丢弃、
tracklet 候选、各几何拒绝原因以及模型/规则路径。该证据是确定性合成结构测试，尚未覆盖
真实 200 路图像、真实 checkpoint、跨场景准确率、内存峰值或多随机种子 P50/P95；这些继续
作为 main/D6 集成与模型准入 P1，而不是本索引代码缺口。

小样本结果只证明原生 PyTorch 前向、反向、困难负样本和不平衡损失可运行，是过拟合 smoke，
不是独立验证、概率校准或模型准入。版本化数据、训练、validation-only calibration、test
评估和 bundle 校验代码现已实现。2026-07-25 已用同一 development-only 权重完成 20 个未见
seed 的合成成对影子结果，但尚无代表性真实数据结果，也没有默认图模型 checkpoint。D5 模块入口已能消费
`OnlineSensorBatch`/`vision_bbox` 和六维中心航迹的真实 DTO 形状，main scalable module stack
已经调用该 adapter；新增 `association.diagnostics` 仍需由 main 持久化到 episode/D6 输出。
后续必须用该整 episode 合同收集困难遮挡和近邻交叉数据，并以独立困难集、真实时延预算和
冻结门限完成准入；模型缺失、损坏、版本不符、异常、超时或平均 certainty
不足时明确回退确定性几何规则，既有默认主线不被替换。

## 2026-07-16 AirSim ComputerVision 5+1 单种子仿真证据

报告入口：

- [Markdown 技术报告](docs/D5_MULTICAMERA_ASSOCIATION_REPORT_CN.md)：详细算法、数据合同、逐相机误差和正式图表。
- [Word 技术报告](docs/D5_MULTICAMERA_ASSOCIATION_REPORT_CN.docx)：按体系架构、关键技术、关联方案、实验结果和边界与计划组织。

Word 与静态原理图可通过
[`scripts/generate_multicamera_report.py`](scripts/generate_multicamera_report.py)
复现；报告图片和绘图数据固定在
`docs/assets/d5_multicamera_association/`，不依赖 `outputs` 目录显示。

main 已完成独立专项分支的两个 reset-separated episode。场景使用 5 个
`1920x1080`、60 度局部相机，1 个 `3840x2160`、75 度侦察相机，以及 5 个
`Quadrotor1` actor；运行 12 秒、49 帧、seed 7。D5 对每个相机 batch 使用自己的
`measurement_timestamp` 投影 `GlobalTrack`，没有用最后一帧时间覆盖整段观测。

| 主检测后端 | 召回 | 配准准确率（严格） | 稳定配准率 | 联合覆盖 | 侦察全覆盖 | 本地 IDSW |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| AirSim detect 几何基线 | 1.000 | 1.000（1.000） | 0.975 | 1.000 | 0.918 | 0 |
| YOLOv8 + 原生 ByteTrack | 0.622 | 0.996（0.966） | 0.955 | 1.000 | 0.878 | 25 |

YOLO+ByteTrack 推理时延 P50/P95 约为 `10.42/12.37 ms`。两路 episode 的
online truth use 和 `global_track_id` rewrite 均为 `0`。本隔离专项没有运行
D1/D2；main 根据 actor truth 运动学合成带中心 `global_track_id` 的 `GlobalTrack`
fixture，truth 还用于离线评分。`online_truth_identity_use=0` 仅表示 D5 从 local
bbox 到该 fixture 的关联代价、Hungarian 选择和稳定窗口不读取 actor/object/truth
identity，不表示整个专项完全不读取 truth。

验收门限为 detect/YOLO 召回分别 `>=0.95/>=0.90`、严格配准 `>=0.95`、稳定配准
`>=0.90`、联合覆盖 `>=0.95`、侦察全覆盖 `>=0.90`、本地 IDSW 分别 `<=0/<=5`，
且 truth use/rewrite 必须为 `0`。因此 detect 几何基线通过；YOLO+ByteTrack 的召回、
侦察全覆盖和 IDSW 未通过，继续作为 optional 研究后端。当前剩余缺口是提升召回、
降低 IDSW、恢复侦察全覆盖并完成多 seed 验证；单 seed 结果不构成主线晋级。
该独立专项分支不替换默认 D1-D7 流程，也不改变 D5 的默认在线路径或安全门限。

## 2026-07-16 人工轨迹到局部图像观测合同

离线子模块 `d5_terminal_association.manual_video_tracker` 公开
`manual_records_to_local_image_observations()`，把 `ManualTrackFrameRecord[]`
转换为 main 提交的
`research_modules.integration_contracts.LocalImageTrackObservation[]`。调用方必须显式提供
`sensor_id`、`stream_id` 和 `(width, height)`，并可设置
`spectral_band`、`local_epoch`、`arrival_delay_s` 与 measured confidence。

measured 记录保留 camera-local `local_track_id`、frame index、tracker/association
backend 和逐 local ID 的连续 measured history；`xywh` 转为 `xyxy`，像素协方差复用
`adaptive_pixel_covariance_px()`。measurement timestamp 使用视频帧时间，
arrival timestamp 为帧时间加显式延时。lost 记录强制
`center_px/bbox_xyxy/pixel_covariance=None`、`confidence=0`，并清零连续 measured
history。转换前对整批记录执行 identity audit，只要重复量测数大于 0 就拒绝整批转换。

该函数不生成、接收或换绑 `global_track_id`。`manual_video_tracker` 已从 D5 包根
`__init__.py` 移除；离线 CLI 和测试显式导入子模块，因此默认导入
`d5_terminal_association` 不再强制加载 manual tracker 的 OpenCV/SciPy 离线视频依赖。
该适配器未接入默认 AirSim detect、TerminalAssociation 或 D7 handoff。

2026-07-16 对既有 `b.mp4` 475 条记录做离线转换复核，得到
`470 measured / 5 lost`，identity audit 重复量测为 0；确定性测试另覆盖协方差、
双时间戳、infrared、bbox `xyxy`、lost、连续历史、重复坍缩拒绝和根包导入边界。
D5 全量 `288 passed`，接受阈值为零失败、重复坍缩必须 fail closed。剩余限制仍是
人工初始化、单相机、离线输入；不构成通用 MOT、跨视角身份或真实 AirSim 性能证据。

## 人工初始化的本地视频多目标跟踪

`scripts/run_manual_video_tracking.py` 支持在普通离线视频首帧用 OpenCV `selectROIs` 按顺序框选任意数量目标，或用 `--rois 'x,y,w,h;...'` 无界面复现。选择顺序固定生成 `local-001...`；默认每目标运行独立 CSRT，可选 KCF。纯 tracker 路径会把高度重叠的重复量测失败关闭为 `lost`，不允许两个本地 ID 同时占用同一框。

针对小型亮目标，可显式启用 `--association bright_hungarian`：程序以 `gray - GaussianBlur(31x31)` 提取全帧正对比峰，再使用本地轨迹常速度预测和 Hungarian 一对一分配。候选区域不写死 y 范围，运动门限负责剔除远端背景峰。候选只能归属一个 `local_track_id`，短时丢失帧的 bbox/center 留空，恢复后仍沿用用户初始化的本地 ID。该路径不读取 truth ID、actor name 或 `global_track_id`。

交互运行：

```bash
python3 research_modules/d5_terminal_association/scripts/run_manual_video_tracking.py \
  --input research_modules/b.mp4 --display
```

无界面复现本次五目标实验：

```bash
python3 research_modules/d5_terminal_association/scripts/run_manual_video_tracking.py \
  --input research_modules/b.mp4 \
  --output-dir research_modules/d5_terminal_association/outputs/manual_video_tracking/b_bright_hungarian_20260715 \
  --tracker csrt --association bright_hungarian \
  --rois '367,275,12,12;386,262,12,12;405,268,12,12;431,260,12,12;451,260,12,12'
```

输出为带彩色框、ID、轨迹尾迹和 lost 标签的 MP4，以及逐帧 CSV 和 JSON summary。2026-07-15 对 `b.mp4` 的 95 帧实测中，五个 ID 有效/丢失帧分别为 `92/3`、`95/0`、`93/2`、`95/0`、`95/0`；summary 明确 `duplicate_measurement_count=0`、最小中心间距 `5 px`。详见 `reports/D5_MANUAL_VIDEO_TRACKING_B_20260715.md`。

能力边界：这是**人工初始化的单相机 local MOT 工具**，不是 GlobalTrack 注册、敌我识别、跨相机身份融合、D7 控制许可或算法准入证明。`local_track_id` 不能替代或换绑中心拥有的 `global_track_id`。

## 2026-07-15 真实 AirSim M5N2 20-case 复核

main 已完成 M5N2 baseline seed 001-010 与 `candidate_soft_prediction_trend_coast` seed 001-010，共 20 个 reset-separated SimpleFlight case。TERM 生效前还额外完整生成了 `p1_terminal_timing_funnel_10seed_20260715_png_ttc_2v2_seed001` 的 `intercept_summary.json`；该独立 case 不进入本节 M5N2 的 `3725` 条记录或任何比例，其他 tuned case 与 dropout case 均未执行。D5 只读复核每场 M5N2 `intercept_summary.json` 后按当前 active-primary 资源 ID 排序选取第二 primary，不能固定写成 `INT-03`：candidate seed 002 的第二 primary 为 `INT-02`，其余 19 场为 `INT-03`。

20 场共有 `3805` 个 main tick，其中 D5 前四个 warmup tick/场为 not applicable；其余 `3725/3725` 个 D5-available tick 均持久化了第二 primary runtime record、决策状态和 `d5_live_visual_funnel_v1` 首断点。决策分布为 `locked=1721 (46.20%)`、`ambiguous=795 (21.34%)`、`reacquire=1209 (32.46%)`、`hold=0`。首断点以 bbox 稳定性 `1283 (34.44%)`、当前检测/新鲜度 `1209 (32.46%)` 和视觉候选关联 `764 (20.51%)` 为主；严格 `complete` 只有 `52 (1.40%)`。当前 measured bbox 为 `2516/3725 (67.54%)`，bbox stable 与 D7 handoff-ready 均为 `161/3725 (4.32%)`；投影有效 `3725/3725`，但正常 geometry-gate accepted 仅 `2312/3725 (62.07%)`。

时间证据方面，`visual_evidence_fresh=2657/3725 (71.33%)`，`terminal_visual_evidence_expired=1068`；measurement age 为 `3724/3725` available，均值约 `0.672 s`、P95 `3.4 s`、最大 `12.5 s`。`timing_gate_pass=3725/3725` 是另一层合同字段，不能覆盖 visual freshness 失败。实际 active second primary 未出现 plan/assignment/global-ID、友方或 duplicate 冲突，online truth identity use 为 0；这只能说明本场景未注入相应冲突，不能替代确定性安全回归。

第二 primary 的 5 m 物理结果为 baseline `0/10`、candidate `0/10`，20 场最近物理距离为 `8.843-14.740 m`，均值约 `12.654 m`；T001 physical coalition completion 为 `0/20`。candidate 的 handoff-ready 快照从 baseline 的 `58/1869 (3.10%)` 增至 `103/1856 (5.55%)`，但 locked、freshness 和 coalition-consensus 比例没有一致改善，且没有转化为物理成功，因此 soft prediction/trend coast 不因本批晋级。直接 `failure_category` envelope 未写入这批 runtime artifact，当前只能用已持久化 stage/reason 统计；这项可用性仍是 P1 报告接线缺口。

20 个第二 primary 的最终控制结果均记录为 `collision_stop`；该字段仅是 D7 停控证据，且本批未持久化碰撞对象，无法区分成员碰撞、环境碰撞或 AirSim 状态问题，不能据此把 `0/20` 单独归因于 D5。

## 2026-07-15 第二 primary 被动失败漏斗

D5 复用既有 `TerminalAssociation`、`d5_live_visual_funnel_v1` 和 cooperative summary，没有新增并行运行时 DTO。`summarize_cooperative_visual_funnel()` 现为每个 resource-target 输出 `failure_category`，并分别聚合全部 active primary 与第二 primary 的分类计数。分类可区分：不可见、投影无效、几何门拒绝、bbox 不稳定或边缘裁切、候选不唯一、时间戳或量测陈旧、计划/版本/`assigned_global_track_id` 合同不一致、友方或重复锁定冲突，以及已关联但稳定锁定未完成；成功、standby reserve 和共同锁定窗口不足保留独立口径。

错误 `assigned_global_track_id` 的最新资源证据不再被诊断层过滤成“不可见”，而是显式报告 `assignment_or_identity_contract_mismatch`；输出行仍保留中心 binding 的 `global_track_id`，不采纳冲突 ID。该变更只增加只读诊断，不改变 `locked/hold/reacquire`、bbox、友方、重复锁定、版本或身份门控。

2026-07-15 确定性测试覆盖上述失败类别和完整成功，共 11 个专项 case；D5 全量 `272 passed`，接受阈值为零失败。未启动新 AirSim。仍需 main 在真实 2v2/M5N2 至少 10 seeds 中验证分类覆盖率、第二 primary 分布和 unknown/other 比例，M5N2 第二 primary 5 m/联盟闭环、真实几何 drift、detect/YOLO/MOT 和二级同 tick freshness 继续为 P1。

## 2026-07-14 actual-v2 真实 AirSim 证据同步

本节同步 main/D6 已写盘的两个 seed-1 actual-execution case，不包含 D5 代码或算法修改。tuned 2v2（8 s、`png_ttc`）和 M5N2（35 s、`png_vm`）均继续以 AirSim `simGetDetections` metadata（AirSim detect）作为默认在线检测输入，不保存 PNG；YOLO/ByteTrack/BoT-SORT 没有因此晋级默认路径。

- canonical actual 五层已经分别注册为 available；两 case 的 contract/control/terminal-switch/mode/physical 总计为 `102/26/26/2/4`。其中 `terminal_switch_allowed_count` 从最终 `control_commands.csv` 独立统计，2v2/M5N2 为 `26/0`，不由 `control_allowed_count` 推断或回填。2v2 的 `terminal_lock_count=3`、visual/mode switch `2/2` 说明该单 seed 已真实发生末端视觉切换。
- M5N2 canonical actual 虽记录 `terminal_lock_count=24`，但视觉控制允许样本、visual switch 和 mode switch 均为 `0`，main diagnostics 的 terminal switch 也为 `0`。物理层为 active pair `2/3`、target `2/2`、coalition `0/1`；T001 第二 primary 最近距离约 `11.02 m`。因此“出现 lock acquisition”不等于“视觉控制或联盟闭环”。
- 两 case 的 online identity/state truth use 均为 `0/0`。D5 继续只读回显中心拥有的 `global_track_id`，不得创建、改写、换绑或用 AirSim actor/object truth ID 修正在线关联。

本批 actual-execution canonical artifact 和五层 schema 可用性均为 `2/2`，但 D6 formal overall status 仍为 `fail`：每个场景只有 1 个 seed，且未完成 baseline/candidate 成对比较、1-5 帧 dropout 全矩阵和完整多 seed P1 suite。D5 当前开放 P1 是 M5N2 第二 primary、真实 AirSim/replay 几何 drift、detect/YOLO/MOT 多 seed，以及二级证据同一 decision tick 的 freshness；不是五层 schema 或 main 接线缺口。IBVS、真实身份源、完整在线 PnP 和 ROS 2 保持 P2/P3。M5N2 既有视觉完成验收目标仍至少 `8/10`，与本轮 physical coalition `0/1` 使用不同分母，均不能由 target `2/2` 替代。

证据：`research_modules/airsim_runtime/outputs/p0_actual_v2_validation_20260714/d6_acceptance/P1_UNIFIED_ACCEPTANCE_REPORT.md` 与 `subagent_reviews/MAIN_P0_ACTUAL_EXECUTION_AIRSIM_VALIDATION_REPORT_20260714.md`。

## 2026-07-14 postbatch M5N2 DTO 与执行锁定语义收尾

最新只读证据来自 `p1_terminal_closure_postbatch_seed1_20260714_m5n2_{baseline,candidate_soft_prediction_trend_coast}_seed001`。baseline 有 `330` 条控制记录和 `151` 条 D5 几何 `locked`，candidate 有 `311` 条控制记录和 `120` 条 D5 几何 `locked`；两组都只有 INT-03 在控制阶段形成 `40` 条非零 bbox，baseline 最大面积比约 `2.4943e-4`。其余 active pair 在约 `23-29 m` 因 `terminal_detection_acquisition_timeout` 退出。相机作用域分别保持为 `InterceptorN:0`，没有发现跨资源相机串用、在线 truth ID 或 `global_track_id` 改写。

本轮关闭两个 D5-owned P1 子缺口。第一，`LocalVisualTrack.to_evidence_metadata()` 和 `d7_handoff_input` 现在显式携带 `bbox_xyxy`、`center_px`、`resource_id`、`camera_id`、`stream_id`、detector/tracker backend、双时间戳以及 measured/stability 状态。第二，几何 `decision_state="locked"` 与 `execution_lock_allowed` 明确分离：后者只有在本资源相机 measured bbox、作用域一致、合同完整、连续 measured lock、bbox 尺度/稳定性及全部既有安全门同时通过时才为真；bbox 缺失或过小只能形成 `association_lock_only`。相机/资源 producer scope 明确冲突时直接 `hold`。

2026-07-14 验证：Python 语法检查通过，D5 全量 `261 passed`，接受阈值为零失败。未降低 identity、friend、duplicate、plan/version、calibration 或 bbox 门，也未启动新 AirSim。真实多相机持续 detection、当前 `640x480` 小框尺度、candidate 中单帧约 `0.64-0.70` 的异常大框，以及至少 10 seeds 统计仍为 P1。

## 2026-07-14 semantics_v2 seed-1 历史 live funnel 诊断

最新真实证据取自 `p1_terminal_closure_semantics_v2_seed1_20260714_m5n2_{baseline,candidate_soft_prediction_trend_coast}_seed001`。T001 的第二 primary `INT-02` 在 baseline/candidate 中分别有 `195/193` 帧 measured detection、`140/142` 帧原始视觉匹配为 locked、`18/18` 帧最终执行 lock；T001 两组均有 `14` 帧 coalition visual consensus，稳定锁定最大连续计数均为 `17`。因此 `terminal_detection_acquisition_timeout/d5_not_locked` 不能再笼统解释为 detect 未到达。

真实断点是时序错位：两组执行合同只在 `0.4-2.2 s` 内通过，INT-02 的 bbox 分别到 `19.0 s`、`18.6 s` 才达到当前面积/CV 稳定门限；从 `2.3 s` 起上游 `arrival_window_expired` 把原始视觉 lock 转为 `hold`。该批旧 `control_commands.csv` 的面积比全为零，当时作为待查路由问题；顶部 postbatch 复核现已确认 main 能传递当前 local track，其他资源控制 bbox 为零主要因为末端阶段已无当前 measured detection。D5 不通过放宽身份、版本、friend、duplicate、timestamp、calibration 或唯一性门限处理该问题。

D5 现增加 `d5_live_visual_funnel_v1`：逐帧区分 measured detection、projection、geometry gate、raw visual lock、execution contract、连续 measured execution lock、bbox stability 和 handoff。`TerminalAssociation.to_runtime_record()` 同时顶层输出 `visual_match_decision_state`、`execution_gate_pass/reason`、`measured_lock_streak_count`、`measured_stable_lock`、`bbox_stable`、`handoff_recommended` 及首断点/责任域；handoff annotation 追加完整 `d7_handoff_input`，但不授予控制权。2026-07-14 新增 3 个专项回归，D5 全量 `258 passed`，接受阈值为零失败；本任务复用既有 seed-1 输出，没有启动新 AirSim。

## 2026-07-14 bbox 稳定历史与共同视觉 P1 闭合

postfix seed-1 只读复核显示：M5N2 baseline/candidate 的 `bbox_stable=true` 均为 `0/1388`，T001 consensus 分别仅 `13/347`、`12/347`；2v2 PNG/TTC 为 `0/52`。所有旧记录 `visible_frame_count <= 1`。根因是 runtime 每 tick 只把当前 `scoped_local_tracks` 交给 handoff，旧 D5 handoff 本身不跨调用保存 bbox 历史；M5N2 T001 同时有 `326/347` tick 的真实 primary membership 变化，这部分必须继续重置共同证据。

`TerminalAssociator` 现按 resource-target-local track-camera-stream-detector/tracker backend 及 committed/current membership 保存 measured bbox 历史。普通 plan/coalition version 刷新不进入 continuity signature；上述身份和成员不变时历史继续累计。resource-target 换绑、成员变化/缺失、local track、camera/backend/stream、producer reset、predicted/lost、identity/friend/duplicate 冲突都会 fail closed 清空 bbox/MOT/stable-lock 历史。association/handoff metadata 输出 `bbox_history_length`、`bbox_area_cv`、`bbox_history_reset_reason`、`bbox_history_key`、`bbox_history_signature`、`bbox_history_evidence_source`、source plan versions，以及 raw/effective MOT history 和合同完整性。`annotate_visual_png_handoff()` 优先消费这组 D5 累积证据，不再要求 main 传入四帧列表。

M-to-N 共同视觉只认可当前 committed coalition 中的 active primary；membership 缺失、无效 commit 或换员不累计共同窗口。YOLO 输入缺显式 detector/tracker backend 时 fail closed；AirSim builtin 可由稳定的 detection source/backend 映射接入。锁定门限、bbox `N=4/CV<=0.30`、`global_track_id` 和 YOLO/native-MOT 准入状态均未改变。2026-07-14 D5 全量 `255 passed`，接受阈值为零失败；本轮未运行新 AirSim episode。

canonical actual 路径现已传递 committed coalition、pre-decision duplicate hint 及 camera/stream/backend/local-track transition/MOT 字段，并将五层同名 envelope 持久化；该接线不再是开放 GAP。真实 M5N2 第二 primary、几何 drift、detect/YOLO/MOT 多 seed 和二级同 tick freshness 仍是开放 P1。

## 2026-07-14 原生 MOT 连续实测历史 P1 修复

`YoloMotAdapter` 不再依赖 Ultralytics `Results` 中不存在的历史长度字段。对原生 ByteTrack/BoT-SORT 输出，适配器按 `(resource_id, camera_id, tracker_backend, native tracker id)` 累计 `mot_history_length`，其口径是**连续实测命中帧数**：同一流同一 ID 连续出现时从 1 增至 2 及以上；ID 变化、一次空帧后重现、backend 切换、流重置或 episode 重置都从 1 重新积累。空帧中的 ID 状态最多保留 `max_track_age_frames`，但 coast 不计实测历史；长期消失后复用 ID 不会自动满足锁定历史门限。

原生 tracker 异常转入 IoU fallback 时，D5 清除该流原生历史并释放失败模型；连续 fallback 段使用自己独立的 IoU 历史，原生模型恢复后仍从 1 开始。新增 `reset_episode()` 作为 `reset_all_streams()` 的 episode 边界接口。2026-07-14 使用 Ultralytics `Results`-like 连续帧、双 backend、跨资源/相机、ID 切换、空帧/遮挡、stream/episode reset 和 native-fallback-native 场景验证，D5 全量 `241 passed`，验收门槛为零失败。

这是代码级 P1 断点闭合，不代表真实 AirSim/真实图像多 seed 准入完成。默认 `min_mot_history=2`、友方/重复锁定/版本/时间戳/标定门控、truth 隔离和 center-owned `global_track_id` 合同均未改变。

## 2026-07-14 D3 planner feedback 分级合同

D5 现用既有字段稳定区分两类输出，不新增公共 DTO：

- **pair 级视觉不确定性**：候选接近、普通 `hold/reacquire`、geometry gate、bbox 或时序不稳定继续输出 `ambiguous/hold/reacquire`；`TerminalConsistencySummary.consistency_state=unknown`，`recommended_d4_action` 只能是 `observe/request_secondary_cue`。它们阻断当前 pair 的 D7 视觉切换或请求重新获取，不表示整架资源 `resource_unavailable`，也不得单独触发 D3 hard planner feedback。
- **安全冲突**：`verified_friend_overlap`、`spoof_suspected_overlap`、`duplicate_terminal_lock_risk`、授权/版本冲突和持续 assignment/ID conflict 继续 fail closed；一致性输出为 `conflict/inconsistent`，并用 `report_conflict/arbitrate` 明确允许 D3/main 形成 hard planner feedback。
- stale/unverified 身份只表示待确认，不推断敌方；未知类别同样不得升级为敌方。所有路径保持输入 `assigned_global_track_id`，online `truth_identity_used=false`。

2026-07-14 专项单元回归覆盖单机 ambiguity/geometry reacquire/bbox hold、verified friend、spoof、TerminalAssociation 自带与 cross-view duplicate，以及分布式 unknown/unverified identity；专项 `52 passed`，随后当时 D5 全量 `235 passed`。验收门槛为零失败、普通不确定性无 `report_conflict/arbitrate/resource_unavailable` 语义、hard conflict 必须有 hard action。该结果是 D5 合同级证据，不是新增 AirSim episode 或资源健康实测。

## 2026-07-13 per-primary 漏斗与 MOT sweep 合同

- M5N2 漏斗按每个 active primary 独立记录 `visible -> projected -> gate_accepted -> locked -> stable_lock`、plan owner/version 和 first failure。显式 `per_primary + arrival_coordination_required=false` 不计算或要求共同锁定窗口；旧 `coalition` 合同仍保留共同窗口门控。standby reserve 不计入完成。
- MOT 准入显式区分 100 帧 screening 与 200 帧 confirmation；summary 同时输出 main sweep 使用的 `tracker_backend`、`detector_precision/recall`、`local_track_continuity` 等字段。IoU fallback 不计 native，truth 必须在 online result 形成后逐帧评分。
- 2026-07-13 当日模块回归为 `232 passed`；2026-07-14 最新全量回归为 `241 passed`，真实 AirSim sweep 仍由 main 调度。

## 目录

- `src/d5_terminal_association/`: Python 实现。
- `tests/`: pytest 单元测试。
- `simulations/`: 多目标、友方、未知目标和遮挡的确定性仿真。
- `scripts/`: 显式运行的隔离式 P2 benchmark CLI。
- `docs/`: 算法说明、实验报告和 AirSim 离线集成计划。

## 运行

```bash
pytest -q research_modules/d5_terminal_association/tests
python3 research_modules/d5_terminal_association/simulations/run_terminal_association_sim.py --frames 120 --seed 7
python3 research_modules/d5_terminal_association/scripts/run_p2_opencv_geometry_benchmark.py --seed 7
```

核心测试仅依赖 Python 标准库、NumPy、OpenCV 和 pytest；OpenCV 不可用时，投影函数会退回简化针孔模型。`YoloMotAdapter` 可选使用 `ultralytics` 与本地权重运行 YOLOv8/ByteTrack/BoT-SORT，缺依赖或原生 tracker 不可用时会返回 `unavailable` 或退回确定性 IoU tracker。

### 混合相机分辨率

D5 支持同一 episode 内每个 `(resource_id, camera_id)` 使用独立分辨率。当前 AirSim 场景基线为拦截相机 `1920x1080`、高空侦察相机 `3840x2160`。`CameraModel.image_size`、每帧 YOLO/MOT 输入尺寸和 bbox 边缘判定均按相机独立保存；固定像素门限按 `640x480` 参考尺度转换，二级配准协方差与无中心跨视角的中心、协方差、bbox 面积也先归一到参考像素尺度。原始 bbox 和像素坐标仍保留用于日志，不使用 truth ID，也不改变 `global_track_id`。

### 对象类别与 YOLO 推理尺寸

`YoloMotAdapter` 将 detector 的 `uav`、`drone`、`intruder` 及常见大小写、空格、连字符和下划线变体统一为对象类别 `uav`。原始标签保存在每条 `LocalVisualTrack.metadata.raw_category` 和 frame metadata 中；类别归一化不推断 `friend/hostile`，敌我属性仍只来自独立 `IdentityClaim` 证据。真实类别差异（例如 `uav` 与 `bird`）继续产生类别不一致惩罚。

`YoloMotAdapterConfig.inference_imgsz` 可选接受正整数或 `(height, width)` 正整数二元组，并透传给 Ultralytics `model.track()`/`model.predict()`；`None` 不传 `imgsz`，保持 Ultralytics 默认行为。该参数允许 1080p 拦截相机和 4K 侦察相机使用不同推理尺度，但不自动证明远距检测质量，仍需 main 在真实 AirSim 多 seed 中标定显存、延迟和召回率。

## 核心接口

- `TerminalAssociator.project_tracks_to_image(global_tracks, camera)`
- `TerminalAssociator.build_cost_matrix(projections, local_tracks, identity_claims, recon_image_cues=(), resource_id=None)`
- `TerminalAssociator.decide(assignment, global_tracks, local_tracks, identity_claims, camera, current_time=None, recon_image_cues=(), camera_pose_source=None, arrival_timestamp=None)`
- `IdentityChecker.parse_claims(raw_messages, current_time)`
- `TerminalObservationBus.publish_terminal_association(...)`
- `TerminalObservationBus.runtime_records()`
- `TerminalObservationBus.cross_view_associations(as_of_timestamp=None, max_age_s=None, plan_id=None, plan_version=None)`
- `TerminalObservationBus.coalition_visual_summary(coalition_bindings, historical_associations=(), required_stable_frames=2, coalition_commit=None, current_time_s=None, center_failed=False, fallback_active=False)`
- `TerminalObservationBus.cooperative_visual_funnel(coalition_bindings, historical_associations=(), required_stable_frames=2, coalition_commits=None, current_time_s=None, center_failed=False, fallback_active=False)`
- `summarize_coalition_visual_completion(coalition_bindings, current_associations, historical_associations=(), required_stable_frames=2, historical_bindings=(), coalition_commit=None, current_time_s=None, center_failed=False, fallback_active=False)`
- `summarize_cooperative_visual_funnel(coalition_bindings, current_associations, historical_associations=(), required_stable_frames=2, historical_bindings=(), coalition_commits=None, current_time_s=None, center_failed=False, fallback_active=False)`
- `TerminalCrossViewFusion.summarize_observations(...)`
- `TerminalCrossViewFusion.build_hypotheses(...)`
- `TerminalCrossViewFusion.associate(...)`
- `TerminalConsistencyTracker.update(...)`
- `summarize_terminal_consistency(...)`
- `annotate_visual_png_handoff(...)`
- `bbox_area_stability(...)`
- `local_visual_tracks_from_sim_detections(...)`
- `local_visual_tracks_from_offline_yolo_bytetrack(...)`
- `YoloMotAdapter.process_frame(...)`
- `YoloMotAdapter.reset_stream(resource_id, camera_id)`
- `YoloMotAdapter.reset_all_streams()`
- `YoloMotAdapter.reset_episode()`
- `NativeMotAdmissionMonitor.observe(result, scenario=..., offline_truth_detections=...)`
- `NativeMotAdmissionMonitor.summary(resource_id, camera_id)`
- `NativeMotAdmissionMonitor.reset_stream(resource_id, camera_id)`
- `evaluate_offline_detector_after_online(result, offline_truth_detections)`
- `per_primary_terminal_evidence(association, expected_resource_id=..., expected_plan_version=...)`
- `publish_sim_detections_as_local_observations(...)`
- `compute_terminal_stress_metrics(...)`
- `summarize_degradation_case(...)`
- `summarize_multiseed_calibration_readiness(...)`
- `summarize_secondary_visual_coverage_funnel(...)`
- `build_secondary_frame_association_evidence(...)`
- `SecondaryFrameAssociationEvidence.to_terminal_association_summary_fields()`
- `register_local_visual_tracks_to_global_tracks(...)`
- `CameraLocalTrackBatch` / `GlobalTrackBinding`

推荐使用关键字参数传入时间和二级侦察 cue，避免误用位置参数：

```python
decision = associator.decide(
    assignment=assignment,
    global_tracks=global_tracks,
    local_tracks=local_tracks,
    identity_claims=identity_claims,
    camera=camera,
    current_time=current_time,
    arrival_timestamp=arrival_timestamp,
    recon_image_cues=reprojected_recon_cues,
    camera_pose_source="runtime_guidance_pose",
)
```

## 原生 MOT 准入

`YoloMotAdapter` 继续用本地 `best.pt` 请求 Ultralytics 原生 ByteTrack 或 BoT-SORT，并在已完成 frame result 中记录实际 backend、confidence、可选 `target_distance_m` 和不带身份的 `detector_bboxes_xyxy`。标准标定网格为 confidence `0.1/0.2/0.3`、距离 `20/30/50 m`。`NativeMotAdmissionMonitor` 按 `(resource_id, camera_id)` 独立累计：原生 active 帧率、IoU fallback 帧数、accepted detections、去除预热帧后的 P95 延迟、local continuity、terminal local IDSW，以及离线 detector TP/FP/FN、precision/recall。

双路 AirSim 评价汇总同时保留 `online_detector_box_count`/`online_yolo_detection_count`、`online_local_track_count`、离线参考框 matched/missed/unmatched-online 计数以及 native/fallback 帧数。这样报告不会把 YOLO 原始框数、本地 MOT 输出数和 `simGetDetections` 离线参考框混为同一个 detection count；`simGetDetections` 的 actor/object identity 仍不会写入在线 result、local track 或全局绑定。

严格时序为：main 先调用 `process_frame()`，再获取 AirSim offline truth boxes，最后调用 `monitor.observe(result, offline_truth_detections=...)`。`evaluate_offline_detector_after_online()` 直接比较 result 中已冻结的 detector bbox 与后到 truth，不修改 result 或 local tracks。旧的 `process_frame(offline_truth_detections=...)` metadata 评分继续兼容；同一帧若 monitor 同时收到后到 truth，则优先 post-online 重算，忽略 legacy metadata，避免双计数。

IoU fallback 明确是失败基线，任何 fallback 帧都不会计入 native active，也会使默认准入失败。identity-bearing truth 只在 `YoloMotFrameResult` 已形成后送入 monitor 计算 local IDSW；summary 只输出计数，不保存 truth ID。episode 切换时 main 必须同时 reset adapter 与 monitor。当前完成的是准入 DTO、统计和 fail-closed 判定，尚未完成真实 AirSim 连续图像多 seed 质量验收，因此 detect 仍是默认在线路径。

`Assignment` 现在只读携带 `terminal_authorization_scope` 和 `arrival_coordination_required`，字段名与 D3 assignment/guidance binding 一致。main 的 D3->D5 adapter 应显式复制这两个字段；旧输入缺字段时使用 `coalition + true`，保持原共同视觉/到达合同。字段沿 `GlobalTrackBinding`、`TerminalAssociation.metadata` 和 runtime record 无损透传。

`per_primary_terminal_evidence()` 默认直接读取 association 内的合同。只有 `terminal_authorization_scope=per_primary` 且 `arrival_coordination_required=false` 时，每个已授权、激活、版本匹配的 primary 才可独立报告 D5 lock，不要求另一个 primary 同帧锁定。函数参数只能核对预期合同，不能覆盖 DTO。它不授予控制权，reserve standby、friend conflict、duplicate risk、缺 plan/coalition 版本或 execution gate 拒绝仍 fail closed，且只回显中心拥有的 `assigned_global_track_id`。

### 2026-07-12 真实 AirSim 20 m 原生 MOT 复核

受控条件为固定前视相机、目标横向运动、`1920x1080`、90 度 FOV、`Quadrotor1` actor、confidence `0.10`。ByteTrack 与 BoT-SORT 均完成 102 帧，`native_active_frame_rate=1.0`、`local_continuity=1.0`、`terminal_local_id_switch_count=0`、`fallback_frame_count=0`、在线 truth 使用和 `global_track_id` 改写均为 0。去除 5 帧预热后的 P95 分别为 8.29 ms 和 18.23 ms。ByteTrack 当前延迟更低，但两者都未通过准入，不能据此把任一 backend 提升为默认主线。

未准入的直接原因是 IoU=0.5 的离线 AirSim detect bbox 评分偏低：ByteTrack 为 33 TP、69 FP、69 FN，precision/recall 均为 0.3235；BoT-SORT 为 29 TP、70 FP、70 FN，precision/recall 均为 0.2929。20 m 日志中的 YOLO 框宽约 49-59 px、高约 26-30 px、置信度中位数约 0.83，说明该距离下 detector 和 native tracker 持续工作。30 m 和 50 m 在 confidence `0.10` 下两后端均为零检测；preflight 中 30 m 即使降到 `0.05` 仍为零，因此不能把远距失败简单归因于当前 `0.10` confidence 门限。

当前证据支持三个待分离因素：

1. 20 m 连续检出而 30/50 m 完全失效，强烈提示 `best.pt` 对当前 actor 的像素尺度、视角或渲染域泛化存在上限。
2. 20 m 每帧基本各有一个稳定 YOLO 框，而 TP 失败同时增加一个 FP 和 FN，强烈提示 YOLO 可见机体/旋翼框与 AirSim mesh-level detect 框定义不同，或二者存在采集时序偏移。
3. IoU=0.5 对窄小框可能敏感，但现有 `blocks_frames.jsonl` 只持久化 YOLO 在线框和累计评分，没有逐帧 AirSim truth bbox，尚不能证明应修改 IoU 阈值。BoT-SORT 在 frame 7、29、33 未增加离线评分计数，最终仅 99/102 帧有 truth score；现有日志无法区分临时空 detect、RPC 抖动或转换失败。

因此下一轮先做离线诊断，不改变在线安全门限：保存后到的 AirSim bbox、采集时间和有效性原因，扫 IoU `0.1/0.2/0.3/0.4/0.5`、同帧及 `-1/0/+1` 帧对齐，并报告中心误差/真值框对角线、宽高比、面积比和 containment。距离矩阵扩展为 `20/25/30/40/50 m`，confidence 使用主网格 `0.1/0.2/0.3` 并增加 `0.05` 诊断点；每个 backend 记录 bbox 像素尺度、置信度、native rate、continuity、IDSW、fallback 和 P95。候选配置确定后至少运行 10 seeds、每组 100 帧以上。

准入继续 fail closed：native rate >= 0.95、fallback=0、continuity >= 0.90、terminal local IDSW <= 1/episode、去预热 P95 <= 100 ms、离线 truth 帧覆盖率 >= 0.99 且缺帧原因可审计；在经验证的 bbox 约定下，20 m precision >= 0.90、recall >= 0.80。30/50 m 在零检测状态下不得准入。IoU sweep 只用于离线评估口径诊断，不能直接降低 D5 在线马氏几何门、唯一性、版本、友方、duplicate 或授权门限，truth 仍只能在 online result 形成后用于评分。

## P1 M5N2 双 primary 视觉诊断

`summarize_cooperative_visual_funnel()` 按现有 `global_track_id` 对动态数量的资源/目标分组，并输出逐资源、逐目标的只读诊断。逐资源阶段固定为：当前合同、可见、投影、几何门控、锁定、稳定锁定、共同锁定窗口；同时保留 association confidence、ambiguity、friend conflict 和首个拒绝原因。逐目标汇总输出 active-primary 漏斗、最长共同锁定窗口、协同完成状态，以及第二 primary 的首个失败阶段。

接口只认可当前 plan/coalition 双版本匹配且已授权激活的 primary。fallback 联盟还必须通过 D4 committed/executing、epoch、lease 和全成员 ACK 校验。standby reserve 只保留诊断行，不进入 active-primary 分母或完成率。`LocalVisualTrack` 可通过 `TerminalObservation` 提供“已看见但尚未投影/注册”的断点证据；它不能创建或换绑 `global_track_id`。输出不传播或消费 AirSim actor/object/truth ID。

模块回归覆盖双 primary 不同视场、共同窗口不足、版本不一致、友方冲突、稳定共同锁定、动态资源/目标数和 fallback 缺 ACK，叠加原生 MOT 准入、严格后评分时序、per-primary DTO 与混合 1080p/4K 相机回归后，该实现阶段 D5 全量为 `204 passed`。后续 main/D6 已在真实 M5N2 paired AirSim 日志和统一漏斗报告中消费这些 summary；该运行级接线已完成。

### 2026-07-12 pose-fix smoke 复核与 D5 修正

对四组 `p1_cooperative_closure_v2_posefix_smoke_20260712_*` 的 `control_commands.csv`、`blocks_frames.jsonl` 和 `main_episode_bus` 对时复核表明，T001 双 primary 不足不是单一门限问题。四组运行中 T001 primary 集合分别变化 73、87、48、70 次；`h020/w05/s040` 的 183 帧中，133 帧没有 current primary lock、25 帧只有一个 lock、25 帧两个 primary 同帧 locked，最终只有 18 帧两个成员均达到两帧稳定。仅用于离线诊断的 actor label 显示，该组各拦截相机对 T001 的可见率约 63%-100%，且两个目标同框率约 38%-100%，所以问题不是“完全看不见”，而是多候选歧义与成员/时序连续性。主要 association 断点为 `insufficient_best_second_margin`、`terminal_visual_evidence_expired`，其次为 arrival-window、投影出图和本地检测门限。所有 active-primary runtime record 的强类型 `camera_geometry` 为 unavailable，但 candidate pair log 仍有 `projected_px`/Mahalanobis/gate 证据；这是 main 的几何证据透传缺口，不能在 D5 内用 actor/object truth pose 补齐。

复核同时发现共同窗口 helper 的实现缺陷：单资源稳定计数已经允许安全的 plan/coalition 单调升版连续性，但共同窗口只接受当前版本 association，导致同一 primary 构型跨版本连续锁定仍只计 1 帧。现已统一语义：共同窗口只复用单资源稳定逻辑认可的 source versions，并只取当前连续尾段；每帧仍需匹配其原始 immutable binding。primary 换员、owner/epoch/coalition/target 变化、旧版本、friend/duplicate/expired evidence 均不跨接。summary 另输出 `primary_membership_transition` 和 `current_primary_failure_diagnostics`，可直接区分成员抖动、无检测、投影、几何门控、锁定和稳定帧断点。该修复由真实 replay 风格 fixture 覆盖；已有 smoke 输出是修复前证据，仍需 main 重跑或重放后才能更新系统级完成率。

## P1 Detect-first 在线合同

默认在线输入保持 AirSim `simGetDetections` bbox。`actor_id/object_id/actor_name/object_name/truth_id/global_track_id` 等仿真真值字段不会参与 local ID、类别、几何代价或 `global_track_id` binding；actor/object ID 置换不改变在线几何关联结果。`association_source` 固定为 `geometric_detect`，`truth_identity_used` 固定为 `false`。

`LocalVisualTrack` 现在显式区分 `measured/predicted/lost`。predicted 轨迹只携带匿名 camera-local continuity 和 `prediction_age_s`，不能进入几何 assignment，也不能输出 `locked/registered`；丢失后的重捕无论 local ID 是否相同，都必须重新通过几何门限和 measured 稳定帧。D5 仍只回显上游 `assigned_global_track_id`，不创建、不改写、不换绑全局 ID。

`TerminalAssociation.to_runtime_record()`、`TerminalObservation.to_runtime_record()` 和 bus `runtime_records()` 向 main/D6 提供扁平字段：`association_source`、`measurement_timestamp`、`arrival_timestamp`、`measurement_age_s`、`prediction_age_s`、`local_track_state`、`truth_identity_used=false`、置信度、决策状态与拒绝原因。lost/reacquire handoff 注释只沿用该 association 的最后测量/预测年龄；没有当前 local ID 时不会借用同相机其他检测的 timestamp、LOS 或 bbox。

面向 D7 身份感知 KF/TTC/可选 6D LOS replay，D5 新增 `CameraGeometryEvidence` 和兼容扩展后的 `LocalVisualTrack`。detect、离线 schema 与 YOLO/MOT adapter 可输出稳定的 camera-local ID、`mot_history_length`、`initialized/continued/switched/reacquired/reset` 迁移证据、measurement/arrival 双时间戳、检测来源、bbox 四边裁剪状态，以及 K、camera-to-NED rotation、camera position、姿态时间戳/年龄/有效性。`geometry_valid` 只有在内参、外参和同步姿态均有效时为真；缺字段显式给出 `geometry_unavailable_reasons`。这些字段经 `TerminalAssociation` 和 runtime record 透传，但 MOT coast、predicted track、二级 cue 仍不能授权视觉 PNG，也不能改写 `global_track_id`。当前 D5 全量回归为 `161 passed`。

canonical actual 路径现已携带 measurement/arrival timestamp、camera pose、姿态时戳和 `CameraModel` 几何证据；P1 转为真实 AirSim/replay 多 seed 的外参 drift 与时间同步标定。任一 case 字段不完整时 6D LOS 仍必须 fail closed 为 unavailable，不能用 AirSim actor/object truth pose 补齐；完整在线 PnP 保持 P2。

本轮不启动 YOLO/ByteTrack 数据集标定，该 P2 工作保持 deferred。已有 OpenCV calibration/`solvePnP` geometry benchmark 仅复核为隔离式离线对照，未导入默认在线路径、未写回 `CameraModel`。

详细算法原理、数学模型和实施流程见 `docs/ALGORITHM_AND_IMPLEMENTATION.md`。

## 最新验收基线

最新集成证据为 `research_modules/airsim_runtime/outputs/PNG_DELIVERY_ENHANCEMENT_AIRSIM_VALIDATION_REPORT_20260712.md`。candidate 2v2 10 seeds 达到 20/20 pair 在 5 m 内成功，旧基线为 19/20，在线 truth 使用为 0，满足该场景主线非退化门槛；自然运行没有触发 soft prediction 或 trend coast，因此不能把结果提升归因于 D5 或新增外推算法。锁定后两帧 dropout 由 D7 在原 global/local track 与计划上下文中有界预测并达到 2/2；D5 只提供身份、时序、几何和 unavailable evidence，不实现 coast、KF、TTC 或控制。

M5N2 的 8 s、3-seed 短窗口为 0/9 active pair、最近距离 22-32 m、terminal switch allowed=0；该场景与既有 z=-30 m、35 s 高净空基线不可比，不能归因于 D5 或 PNG 滤波。下一验收必须在同一高净空几何和相同窗口下做 paired baseline/candidate，分别统计 target、active-primary、coalition completion，并审计 D5 hold/reacquire、视觉共识、错误绑定和 duplicate。

2026-07-11 的 ComputerVision `8/10` 双 primary 合同验收、错误 duplicate 0/10、完整 ACK commit 正例和缺 ACK fail-closed 仍有效；当时的 `control_allowed_count=0` 与 SimpleFlight 15 s 0/30 仅保留为历史诊断。当前 P0 无 blocker，D5 回归为 `161 passed`。仍开放的是 M5N2 paired 长时验收、1-5 帧 dropout/fail-closed 矩阵、真实相机曝光/外参/姿态同步标定、持续非零 YOLO/native MOT、二级完整覆盖、D4 逐 tick evidence 和真实身份 replay。P2 OpenCV calibration/`solvePnP` 仍仅是隔离式离线合成 benchmark，不进入在线 D5 主线。

## P1 受控跨版本稳定延续

`TerminalObservationBus` 现在保存只读 coalition binding 快照。当前 association 必须首先严格匹配当前 plan/coalition 新版本；历史帧只可增加稳定计数，不能恢复旧版本授权。reserve-only soft-feedback replan 导致 plan ID 变化且 plan/coalition version 同时严格升高时，只要 plan owner/node、`coalition_id`、target、`global_track_id`、primary resource-target binding 集合、role、epoch、需求和授权均不变，两个 primary 的连续视觉计数可从旧版本延续到新版本，并立即以新版本输出 consensus。`coalition_version` 是可单调演进的代际字段，不再被误当作不可变 identity。

primary 换员或 target 换绑时整个 primary 构型重新计数。相同/下降的 coalition version、新 plan 旧版本回放、`coalition_id` 改变、owner/epoch 冲突、friend/duplicate/wrong-binding、过期证据或历史 commit conflict 会清零或 fail closed。输出 metadata 包含 continued resource、reset reason、source plan versions 和 stale replay resource；reserve 始终不能补 primary，也不能获得 visual PNG authority。该机制已由上述 10-seed ComputerVision 验证支持 `8/10` 双 primary 合同验收，但不得外推为控制许可或物理命中。

## P2 OpenCV 几何扰动 Benchmark

`p2_geometry_benchmark.py` 是隔离式离线研究入口，不由 `TerminalAssociator`、registration 或 main/runtime 默认路径导入。它使用既有 `CameraModel`/`GlobalTrack` 合同生成可复现的标定板、3D 参考点和运动目标，运行 `cv2.calibrateCamera` 与带漂移初值的 `cv2.solvePnP`，并注入相机平移/旋转漂移、measurement timestamp bias、arrival latency/bias。输出标定/PnP 重投影误差、扰动前后投影 RMSE、arrival-time 投影 RMSE、真目标门控接受率和离线假候选错误接受率。

默认 seed 7 的当前基线为：48 个样本，投影 RMSE 从约 24.0 px 降至 1.63 px，真目标接受率从 0.0 恢复到 1.0，构造的离线假候选错误接受率从 1.0 降至 0.0。该数字只验证合成几何敏感性，不代表 AirSim 或真实相机标定质量。OpenCV calib3d 不可用时结果明确为 `status=unavailable/reason=opencv_calib3d_unavailable`。

truth identity 只在所有投影与门控完成后附加为 `offline_truth_label`，修改标签不会改变任何几何或门控指标。benchmark 不创建绑定、不调用在线关联、不修改 `global_track_id`。真实棋盘/AprilTag 图像采集、PnP RANSAC、在线外参更新和硬件标定仍未实现。

## 当前状态总览

已实现：

- `GlobalTrack` 投影到图像平面、像素协方差传播、马氏门控和保守候选排序；`TerminalAssociation.metadata` 和 `GeometricAssociationResult.to_log_records()` 已输出 projected pixel、bbox center、pixel error、Mahalanobis、gate pass、friend conflict、measurement age 和 duplicate-risk advisory 字段，便于 main/D6 写 JSONL/CSV。
- `LocalVisualTrack`、`TerminalAssociation`、`IdentityClaim`、`ReconImageCue`、`TerminalObservation`、`CrossViewAssociation`、`DistributedVisualObservation`、`VisualTrackletSummary`、`PeerCameraState`、`CrossPeerAssociationHypothesis` 和 `DistributedTerminalAssociation` 等 DTO。
- `locked/ambiguous/hold/reacquire` 保守状态机；D5 只核对当前 `assigned_global_track_id`，不会把本地最佳或最近目标改写成新的全局身份。P0-B 已补主动重捕获：丢锁后基于 GlobalTrack 预测投影、上次 bbox/MOT 历史和 search window 恢复同一 `assigned_global_track_id`，MOT ID 更换时需先通过稳定窗口。2026-07-10 P0 回归补齐 active reacquire 的 `IdentityChecker` 门控：选中候选与 verified/stale/unverified/spoof-suspected 友方声明重叠时一律输出 `hold`，并记录 `friend_conflict_state`、reason 和逐候选审计字段。
- D3 schema v2 的 M-to-N 只读合同：`Assignment`、`GlobalTrackBinding` 和 `TerminalAssociation` 携带 `plan_id/version`、`coalition_id/version`、`member_role`、`wave_id`、`required_resource_count`、`coordination_mode`、arrival window 和 `activation_state`。各 resource-camera 仍独立执行 GlobalTrack 投影与 camera-local MOT 配准；这些字段只解释执行门控和跨视角 lock set，不允许 D5 形成联盟或改绑 `global_track_id`。
- 合法协同锁：同一目标上的多个 `locked` 若计划/联盟版本一致、成员已授权激活且资源数不超过 `required_resource_count`，`CrossViewAssociation` 输出 `planned_cooperative_lock=True` 且不设置 `duplicate_terminal_lock_risk`。联盟/计划版本不一致、缺失联盟合同、资源 scope 不符、未获执行授权、超额资源、单资源多 local lock 或单 local-to-global 冲突仍输出 conflict/duplicate evidence。k=1 保持原语义。
- Cross-view 当前快照作用域：`cross_view_associations()` 无参数时保留历史兼容的全 bus 汇总；传入任一 scope 参数后，先按 `as_of_timestamp/max_age_s` 和当前 `plan_id/plan_version` 过滤，再对每个 resource 只保留其最新 timestamp 的同帧观测，duplicate/coalition 判定不再跨帧或跨 plan 累积。`max_age_s` 必须与 `as_of_timestamp` 同时提供，未来 observation 被拒绝；输出 metadata 记录 scope 参数及 input/candidate/selected count。main 在线调用口径为 `as_of_timestamp=frame.timestamp`、`max_age_s` 约 `1.5 * dt`、当前 plan ID/version。
- 波次执行门控：默认 `primary`、wave 0、`activation_state=active` 保持兼容；未激活 `reserve/retry` 即使几何和 MOT 已得到可锁候选，也降级为 `hold`，保留 `visual_match_decision_state=locked`、`execution_gate_reason` 和 D7 visual PNG blocker。arrival window 未开启或已过期同样不能输出可执行 lock。
- 联盟视觉完成汇总：`summarize_coalition_visual_completion()` 是 main 可直接调用的纯函数，输入一组 D3 `AssignmentGuidanceBinding`/等价 mapping、当前和历史 `TerminalAssociation`/`TerminalObservation`，输出 `CoalitionVisualSummary.primary_required_count`、`primary_locked_resource_ids`、`primary_lock_complete`、`reserve_ready_resource_ids` 和 `coalition_visual_consensus`。hybrid 默认要求全部 active primary 当前锁定且每个资源至少连续 2 帧锁定；standby reserve 的本机几何/MOT 匹配只进入 ready 集合，不进入 consensus 或 `visual_png_authorized_resource_ids`。
- 汇总只认可 association 的本资源 local detection。若 observation/association resource scope 不符、`measurement_resource_id` 指向其他资源、`measurement_camera_id != projection_camera_id` 或标记 `borrowed_bbox=True`，该证据不能形成 primary lock 或 reserve ready。二级 cue 仍只可用于搜索/配准；无本机 `local_track_id` 时不能借用其他相机 bbox。合同/版本冲突、联盟外执行 lock、over-demand 和单资源多 local lock 保持保守阻断，且输出 ID 始终是 binding 中已有的 `assigned_global_track_id`。
- 跨视角 distributed visual association P0：`TerminalObservationBus` 汇总多资源终端证据，`TerminalCrossViewFusion` 在完全无中心场景输出 metadata-only 多相机 peer evidence。
- AirSim `simGetDetections` 风格 bbox dry-run adapter、离线 YOLO/ByteTrack schema adapter，以及 `YoloMotAdapter` 图像帧入口。默认权重路径为 `/home/linux/Documents/MSM/research_modules/d5_terminal_association/best.pt`，可通过参数覆盖；真实 `ultralytics` ByteTrack/BoT-SORT 路径不可用时，adapter 使用确定性 IoU fallback tracker，并在 `YoloMotFrameResult.metadata` 标明实际后端、每个 `LocalVisualTrack` 的 confidence、class id、bbox area/scale、tracker backend，以及请求的 CPU/GPU budget。2026-07-10 已按 `(resource_id, camera_id)` 隔离 fallback/native MOT 状态，metadata 携带 stream key、实际 backend 和状态作用域；`reset_stream()` 与 `reset_all_streams()` 支持相机重启和 episode 边界清理。在线 category 只接受显式 `category/label/class_name` 或 detector `class_id + names` 映射；通用 `name`、`actor_name`、`object_name` 和 truth/global 字段不进入 category、cost、binding 或 online metadata。sim-detection adapter 还会拒绝与 truth/actor 值完全相同或以 `: / | #` 分隔组件形式嵌入该值的本地 ID，例如 `Interceptor1:0:MSM_TargetActor_1`。
- P1 AirSim multi-seed calibration readiness helper：`summarize_multiseed_calibration_readiness()` 被动检查每个 seed 的 `TerminalObservation`、`CrossViewAssociation` 和 metadata 是否带齐 local bbox/timestamp、geometry gate log、measurement age、YOLO/MOT backend、AirSim detect source、offline truth label、bbox stability、handoff advisory、duplicate/friend conflict 等报告字段。truth label 只从离线 `TerminalObservation.metadata` 计数，不进入在线关联。
- 二级视觉覆盖与 detect 漏斗诊断：`summarize_secondary_visual_coverage_funnel()` 消费普通 replay frame dict/dataclass、`TerminalObservation` 和 `CrossViewAssociation`，输出单个二级相机 full-view 帧率、二级网络联合 full-view 帧率、每相机/网络每帧可见目标数、覆盖比例均值/最小值，以及 detect -> local/recon cue -> terminal association -> cross-view association -> multi-support 计数。offline target label 只用于“看见目标”覆盖统计，不进入在线绑定。
- D4 逐决策证据合同：`build_secondary_frame_association_evidence()` 只接收一个同步 `frame_id` 的 `SecondaryCameraFrameCoverage[]`、`SecondaryNetworkFrameCoverage` 和 registration result，并输出 `SecondaryFrameAssociationEvidence`。`to_terminal_association_summary_fields()` 的字段名与 D4 现有 `TerminalAssociationSummary` 兼容，包含当前帧 coverage/full-view、stable registration、not-registered、cue freshness、gimbal 状态和转换断点；metadata 保留 measurement/arrival timestamp、detector/tracker backend 和 calibration health。历史 candidate 会按 frame/timestamp 过滤，混合 camera frame 直接拒绝，禁止用 episode 汇总冒充逐帧接管证据。
- AirSim settings 驱动的 detect-to-global-track registration：`register_local_visual_tracks_to_global_tracks()` 消费 `GlobalTrack[]`、D2/D3 `GlobalTrackBinding`/`Assignment`、每相机 `CameraModel(K/R/t)`、timestamp、像素协方差和 `LocalVisualTrack[]`，用像素马氏距离 + Hungarian 匹配注册到既有 `global_track_id`，并保留 JPDA-compatible gated candidates。输出 `DetectToGlobalTrackCandidate.outcome`、`TerminalObservation`、即时 `CrossViewAssociation` 和稳定 `stable_cross_view_associations`；reject/status reasons 包含 `not_all_targets_visible`、`network_union_incomplete`、`no_global_binding`、`reacquire_not_grouped`、`stale_or_missing_recon_cue`、`projection_invalid`、`geometry_gate_rejected`、`stability_window_failed`、`secondary_detect_offline_only` 和 `registered_to_global_track`。truth/actor ID 只用于 offline metadata 计数，不参与在线绑定。
- P0-B 时序一致性与校准健康字段：`TerminalAssociator` 按 `resource_id + assigned_global_track_id` 保留候选历史，重捕获后加强 candidate margin、stable window、bbox/MOT 历史和 stale/OOSM 阻断；`TerminalAssociation.metadata` 与 `TerminalConsistencySummary.to_metadata()` 输出 `projection_valid`、`reprojection_error`/`reprojection_error_px`、`camera_pose_source`、`camera_pose_source_trusted`、`calibration_health`、`calibration_health_reason` 和 `drift_warning`。
- P1 二级 detect 校准字段：registration candidate 和 observation metadata 现在携带 `detect_registration_outcome`、`detect_registration_reject_reasons`、`measurement_timestamp`、`arrival_timestamp`、`measurement_age_s`、`covariance_px`、`projection_covariance_px`、`pixel_error_px`、`reprojection_error`、`mahalanobis_d2`、`gate_pass`、`projection_valid`、`projection_reason`、`camera_pose_source`、`calibration_health`、`drift_warning`、`bbox_area_px` 和仅离线评分用的 `offline_truth_global_id`。`camera_pose_source` 支持 `airsim_camera_pose`、`runtime_guidance_pose`、`look_at_fallback`，D5 只消费 main/runtime 传入的 `CameraModel` 与 metadata，不调用 AirSim。
- P1 自适应像素协方差与稳定注册：当 batch metadata 或 `LocalVisualTrack.bbox` 提供 bbox 面积时，`adaptive_pixel_covariance_px()` 使用 `sigma_px = clamp(max(25, 0.5*sqrt(bbox_area_px), 0.008*image_diag_px), 25, 90)` 生成二级相机像素协方差；无面积时保留已有 `batch.covariance_px` fallback。单帧 gate pass 先记为 candidate；默认近 3 帧同一 `resource/camera/local_track/global_track` 至少 2 次通过才标记 `stable_cross_view_support=True`，D5 仍不创建、不改写、不换绑 `global_track_id`。
- 机动高空侦察云台 cue evidence：`ReconImageCue`、`CrossViewAssociation.metadata` 和 secondary coverage funnel 可携带 `cue_position_ned`、`look_at_ned`、`gimbal_pointing_metadata`、`cue_pointing_error_m/rad`、`gimbal_track_error_px`、`cue_source=radar_global_track_cue`、`capability_class=mobile_high_recon` 和 `coverage_mode=mobile_recon_gimbal`。报告可区分 `fixed_downlook_secondary` 与 `mobile_recon_gimbal`，并标出固定俯视未覆盖、移动侦察云台补足网络联合覆盖的帧和目标集合。
- D7 视觉 PNG 前置证据：`annotate_visual_png_handoff()` 只在 D5 `locked`、当前 `assigned_global_track_id` 一致、friend/duplicate 风险安全、bbox 稳定、LOS rate 可用、measurement age 新鲜且 D4/D3 gate 允许时输出 handoff/prelock 建议。
- P1 D4/D5 calibration sweep 消费口径：main runtime 已新增 P1 sweep，可按二级高度、FOV、二级节点数量和 standoff 组合运行多 seed D4/D5 stress，并把 D5 registration observation、secondary funnel、mobile gimbal metadata 和 cross-view support 交给 D6 标准报告 bundle。D6 自动产物包括 `d6_airsim_calibration/airsim_calibration_records.csv`、`airsim_calibration_summary.csv`、`airsim_calibration_summary.json` 和 `airsim_calibration_report.md`。D5 不启动 AirSim、不写总报告，只保证这些输入字段和安全边界稳定。

2026-07-10 对 `outputs/p1_gap_closure_2v2_smoke_20260710` 的 D5 复核结论：2 个资源对均以 `collision_intercept` 完成，pair summary 的 D5 状态均为 `locked`；但 D7/main 的独立视觉接管门控仍记录 `bbox_near_image_edge` 9 次、覆盖 2 个资源对，`terminal_switch_allowed=True` 只出现 2 个控制记录。这说明“D5 已锁定”不等于“相机视线和机动条件已允许视觉 PNG”，安全门控没有被放宽。该结果新增一个 P1 校准项：统计 bbox 到图像边界的归一化裕量、连续边缘帧和相机指向误差，并由 D5 handoff advisory 向 D7 提供可审计证据，D7 的独立 camera/LOS/maneuver gate 仍保留。

同一输出曾暴露跨模块 P0 集成断点：真实 runtime 终端记录的 `local_track_id` 为 `Interceptor*:0:MSM_TargetActor_*`。main hotfix 已实现匿名 camera-local bbox tracker：builtin detect 的 `local_track_id` 为 `<camera_id>:det:<sequence>`，`detection_id` 不含 actor 名，匹配只使用 bbox IoU/中心距离且在 episode setup 清空；actor 名仅保留在 `offline_truth_actor_name` + `offline_truth_only=True` 评估 metadata。episode bus 在线 D5 路径使用 `geometric_local_visual_tracks_from_blocks_frame()`，不读取 `object_id`，truth map 只在 D5 决策后计算离线正确率；intercept 注入和 D4/D5 fallback 的 actor-name local ID 也已清理。真实 AirSim 证据 `research_modules/airsim_runtime/outputs/p0_truth_isolation_smoke_20260710` 已完成端到端验收：三类 case 均 connected、各 5 帧，`blocks_frames.jsonl` 的 local/detection ID 无 `MSM_TargetActor`，匿名 ID 连续到 `mot_history_length=5`，actor 名均带 `offline_truth_only=True`，每类 cross-view association 均为 4。该 P0 已闭合并转为保持回归项；D5 不在模块内猜测或重写任意既有 `LocalVisualTrack.local_track_id`。

2026-07-11 实测状态分层如下。既有 D4/D5 三组真实回归均形成 `cross_view_association_count=4`，稳定注册约为 19-61，但二级相机网络仍不能在同一帧稳定覆盖全部目标，因此“跨视角支持可形成”不等于“二级态势完整”。`research_modules/airsim_runtime/outputs/p1_yolov8_bytetrack_smoke_fixed_20260711` 已跑通 6 个 reset-separated episode、每个 2 帧，证明 AirSim RGB 解码、YOLOv8/ByteTrack 调用、per-stream 状态、在线 truth 隔离、离线 bbox-only 评分和 runtime 事件接口可执行。该场景中 `accepted_detection_count=0`，多数 AirSim offline truth box 也为 0；原生 ByteTrack 因没有 detector track ID 按合同退回 `iou_fallback`。观测延时多数约 38-49 ms，首轮约 197 ms。故当前只关闭“接口未接通”缺口，检测有效性、真实 detector recall、native MOT 连续性/IDSW 和预算稳定性仍是 P1，不能把 6 episode 冒烟结果解释为视觉终端闭环已验收。

部分实现或仅为抽象/adapter：

- OpenCV 已用于在线主线投影和可选畸变参数消费；隔离式 P2 benchmark 已调用合成 `calibrateCamera`/`solvePnP` 并量化外参/时间扰动。真实标定图像、PnP RANSAC、标定板/AprilTag 采集和在线外参更新仍未接入。
- YOLOv8/ByteTrack/BoT-SORT adapter 已能消费图像帧或 mock detector 输出并返回 `LocalVisualTrack`；默认优先调用 Ultralytics 原生 `bytetrack.yaml` / `botsort.yaml`，无依赖或权重缺失时返回明确 `unavailable`，原生 tracker 失败但 detector 可用时才启用确定性 IoU fallback。metadata 记录请求/实际 tracker、fallback 是否激活、wall-clock detector+tracker latency、声明预算是否超限、observed device、per-local-track MOT history 和 camera-local continuity。可选 `offline_truth_detections` 只在在线跟踪结束后计算 detector recall/precision、FN/FP 和 IoU 汇总，不输出 truth identity，也不影响 tracker/local/global ID。多相机状态隔离已闭合：IoU tracker 按 stream 懒创建；Ultralytics native tracker 因 `persist=True` 状态没有稳定交换接口，按 stream 使用独立 model/tracker 实例。代价是 native 模式显存/内存和首帧加载时延随活跃 stream 数增长；纯 detector/injected detector 仍可共享。
- `offline_truth_detections` 现支持 AirSim runtime 使用的单个裸 `xyxy` 四元组、多个 bbox-only 四元组及 dict/object detection。该解析器只提取离线评估框，畸形输入会给出明确合同错误；标签不会进入在线 tracker、local ID 或 `global_track_id` binding。
- ByteTrack、BoT-SORT 的真实质量依赖上游 `ultralytics` 和连续图像输入；Deep SORT/ReID 仍未接入。IoU fallback 只提供确定性本地 ID 连续性，不声明遮挡恢复或 IDSW/IDF1 工程质量。
- OpenDroneID、MAVLink signing、DDS Security、AprilTag 只通过仿真字典归一化为 `IdentityClaim`；未接入真实报文、密钥、证书或 tag detector。
- ROS 2 `tf2/message_filters` 只是未来时间同步和坐标树方案；D5 当前不运行 ROS 2 节点。

未实现：

- AirSim/main runtime 的最小 RGB 图像链和 2 帧冒烟入口已接通，但持续多帧、多 seed 的真实 detector/tracker 质量验收尚未完成。当前 actor/相机几何下 YOLO 无有效 accepted detection，原生 ByteTrack 无 track ID 并回退 IoU；仍需标定目标尺度、视角、置信度/class map、连续帧长度、CPU/GPU 预算、真实标定链、真实身份认证链路和跨相机三维联合优化。episode 边界仍必须调用 `reset_all_streams()`。
- 在线 D5 不得使用 AirSim `object_id`、`actor_name` 或 actor truth ID。truth ID 只能作为离线评分标签进入 metadata/evaluator，用于 `terminal_lock_accuracy`、`locked_mismatch` 等指标。

剩余工程状态不在 D5 evidence schema：P1 仅为 M5N2 第二 primary、真实几何 drift、detect/YOLO/MOT 多 seed 和二级同 tick freshness，其中 dropout、edge margin 与远距召回作为多 seed 检测/关联子场景。P2 为 Deep SORT/ReID、真实身份 adapter 和完整在线 PnP/标定链；IBVS 与 ROS 2 `tf2/message_filters` 保持 P3 可选研究。D5 的 OpenCV calibration/`solvePnP` 仅为隔离式合成 benchmark，不等同于在线 AirSim 或硬件 PnP。

## 决策状态

- `locked`: 唯一候选通过几何门限和保守代价检查。
- `ambiguous`: 候选接近、身份声明不可靠或代价过高。
- `hold`: 已验证友方与普通 gate 候选重叠、任意非空友方声明与 active reacquire 候选重叠，或版本不一致。
- `reacquire`: 无候选通过门限，或投影不可用。

## 主动降级仲裁信号

D5 可通过 `TerminalConsistencyTracker` 把连续帧 `TerminalAssociation` 派生为 `TerminalConsistencySummary`，供 D4/D6 判断中心/二级节点分配与末端视觉证据是否一致。摘要包含 `decision_state`、`association_confidence`、`ambiguity_score`、`friend_conflict_state`、candidate cost margin、`recon_cue_used`、terminal lock age、连续 `locked/ambiguous/hold/reacquire` 帧数、丢锁/重捕获事件、`duplicate_terminal_lock_risk` 和 `cross_view_support_count`。

连续帧窗口按 `resource_id + assigned_global_track_id` 维护，而不是按每次 D3 `assignment_version` 重置。这样同一资源持续执行同一全局目标时，即使中心滚动发布新的 plan version，D5 也能保留末端视觉丢锁/重捕获的连续性；只有 assigned global track 变化才进入新的窗口。

该摘要只用于离线一致性评估和 D4 仲裁输入。D5 不触发降级、不重写 `global_track_id`、不生成新分配计划。

## 视觉 PNG 接管建议

D5 可在 `TerminalAssociation.metadata` 或 `TerminalConsistencySummary.metadata` 中输出视觉 PNG 提前接管建议，但不决定导引律、不调用控制、不修改 `global_track_id`。D7/main 仍需独立检查相机、LOS、机动裕度和自身 terminal gate。

默认配置把当前 AirSim Blocks 5v5 大目标 actor 的经验值写成可调区间，而不是固定 30m 门限：

- 远距候选区 `30-50m`：只允许准备/预锁定，`visual_png_prelock_recommended=True`，不直接建议视觉接管。
- 中距候选区 `15-30m`：若 bbox 面积连续稳定、D3/D4/D5 一致、无友方冲突和重复锁定，且 `time_to_go`、检测延迟和 D7 机动裕度可接受，可输出 `handoff_recommended=True`。
- 近距强制评估区 `5-15m`：若检测稳定则优先建议视觉 PNG；若 bbox 不稳定则建议保持或回退 radar PN，避免过早触发 `terminal_detection_timeout`。

bbox 稳定性默认要求同一 `local_track_id` 或同一 assigned track 窗口连续 `N=4` 帧可见，`bbox_area_ratio` 的变异系数 `CV <= 0.30`，可在 `VisualPngHandoffConfig` 中调整为 `N=3-5`、`CV=0.25-0.35`。输出字段包括 `handoff_recommended`、`visual_png_gate_pass`、`visual_png_handoff_blockers`、`handoff_reason`、`recommended_range_band`、`bbox_stability_score`、`bbox_area_cv`、`measurement_age_s`、`measurement_age_ok`、`los_rate_px_s`、`los_rate_ok`、`range_to_assigned_track_m` 和 `time_to_go_s`。

## 完全分布式跨视场视觉假设

当前程序已覆盖单机视场内多目标候选、友方 `hold`、二级侦察 cue 作用域和保守 `global_track_id` 不变式，并提供两层跨视场证据：

- `TerminalObservationBus`：被动收集多架拦截无人机、二级节点或 peer 链路发布的 `LocalVisualTrack`、`TerminalAssociation`、`IdentityClaim` 和 `ReconImageCue` 摘要，按既有 `global_track_id` 汇总支持关系。
- `TerminalCrossViewFusion`：在完全分布式模式下消费 `DistributedVisualObservation`、`VisualTrackletSummary` 和 `PeerCameraState`，基于时间窗口、bearing、bearing rate、bbox area/scale rate、类别/置信度、像素协方差和相机姿态协方差生成 `CrossPeerAssociationHypothesis` 与 `DistributedTerminalAssociation`。

示例：UAV1 看到目标 1/2/3，UAV2 看到目标 2/3/4 时，目标 2/3 会形成包含 `("UAV1", "UAV2")` 的多视角支持摘要；目标 1/4 保持单视角支持。局部 ID 按 `resource/camera:local_track_id` 命名空间处理，因此 `UAV1/front:track_1` 与 `UAV2/front:track_1` 不会被误认为同一本地轨迹。若多个资源同时持有同一 current `assigned_global_track_id`，或同一本地命名空间出现全局 ID 冲突，D5 只输出 `duplicate_terminal_lock_risk=True`、`hold/ambiguous/hypothesis_only` 等保守状态，供 D4 仲裁，不会改写分配。

`TerminalCrossViewFusion` 使用 Hungarian 匹配；若 SciPy 不可用，会退回纯 Python 最小代价唯一匹配。缺失或 stale `global_track_id` 时只输出 `hypothesis_only/hold`，不会输出 `locked`。未知类别不会被升级为敌方。

当前实现仍是 metadata-only P0 融合器，不做三维重投影、三角化、多相机 bundle adjustment、真实图像 ReID 或 D4 分配决策。

## 二级侦察节点输入

高空系留侦察无人机可作为二级节点向覆盖小区内的拦截资源发送 `ReconImageCue`。该 cue 只在 `scoped_resource_ids` 限定范围内降低关联代价，用于帮助末端相机把本地视觉轨迹配准到中心分配的 `global_track_id`。它不能替代授权、版本校验、友方正向认证或本地 MOT 质量门槛，也不能触发局部节点自行改写 `global_track_id`。

`ReconImageCue.center_px` 必须已经处在当前拦截资源相机平面。若 cue 来自二级侦察节点自己的相机，需要先重投影到本地相机帧，再与 `LocalVisualTrack.center_px` 比较。

机动高空侦察节点使用同一输入边界：雷达/D1-D2 的 GlobalTrack cue 给出 `cue_position_ned` 和 `look_at_ned`，高性能光电云台执行 look-at 后形成 `mobile_recon_gimbal` 证据；本地或多相机 detector/MOT 只产出 `LocalVisualTrack`，随后仍由几何门控、Hungarian/JPDA 风格候选排序和 `TerminalAssociator` 对既有 `assigned_global_track_id` 做保守确认。固定俯视二级相机覆盖不足时，coverage funnel 会把 `fixed_downlook_secondary` 与 `mobile_recon_gimbal` 分开统计，并记录移动云台补足的目标簇/子簇。

cue 使用规则：

- `scoped_resource_ids` 非空时，仅指定资源可使用；为空时按配置允许广播。
- `current_time` 存在时，超过 `AssociationConfig.max_recon_cue_age_s` 或来自未来的 cue 不参与代价。
- `frame_id` 存在时，`image_frame_id` 必须等于目标相机帧；若通过 `metadata["target_frame_id"]` 指向目标相机帧，则必须同时有 `metadata["reprojected_to_local_camera"] == True`。
- 若 `metadata["source_image_frame_id"]` 与目标帧不同，也必须显式标记已重投影。

在跨视角总线中，系留无人机视频 cue 只作为几何门控和复核证据随 `TerminalObservation` 记录。它可以增加 `recon_cue_used_count`，但不能创建新的 `global_track_id`、不能替代 D2 航迹，也不能让本地节点换绑分配目标。

## AirSim ComputerVision N-v-N 专项适配

D5 提供不依赖 AirSim Python 包的 dry-run 适配器，用于消费 `simGetDetections` 风格的检测框 fixture。5v5 只是历史 stress baseline：目标距拦截镜头约 50m，目标间距约 20m，拦截镜头间距约 20m；二级系留侦察镜头比目标高约 200m，分辨率更高并提供全局视野。真实 N-v-N 仿真数量由 main runtime 的 `--drone-count N` 决定，D5 只按传入的 `LocalVisualTrack[]`、`GlobalTrack[]` 和 camera/resource 列表长度运行，不在模块内固定 2/5 个相机或目标。

当前主线使用捷联固定相机和 AirSim detect bbox，不默认运行 YOLO。为了减少机架遮挡，建议 main/D7/AirSim settings 将拦截机相机沿机体系前向前移约 `0.5m`；D5 只消费更新后的 `CameraModel` 外参，不直接修改相机安装或 AirSim settings。

在线几何配准只使用 bbox、时间戳、相机几何、本地 MOT ID、类别/置信度等观测字段。AirSim detection 的 `object_id`、`actor_name` 或 truth ID 只能作为离线评估标签进入 `metadata`/评估 helper，不能进入 `TerminalAssociator`、`TerminalObservationBus` 或跨视角一致性决策。

二级节点本轮输入口径与主线一致：优先消费 AirSim `simGetDetections` 产生的 bbox/metadata，不启用 YOLO。若 AirSim 记录中的 `track_id`、`detection_id` 或类似本地 ID 字段与 `object_id`、`actor_name`、`name`、`truth_id` 或 `global_track_id` 等 truth/actor 字段相同，D5 会把该字段视为仿真真值别名并回退为 `camera_id_det_index` 形式的本地检测 ID；该 ID 只在本相机观测内有效，不能作为在线身份或 `global_track_id` 来源。

处理链路：

1. 每个当前 runtime camera/resource 的检测框转换为 `LocalVisualTrack`。
2. `register_local_visual_tracks_to_global_tracks()` 用当前 `GlobalTrack`、D2/D3 binding、相机 `K/R/t`、timestamp 和协方差把 detect 注册为既有 `global_track_id` 的支持候选。
3. 多镜头本地观测和注册结果写入 `TerminalObservationBus`。
4. 单机 `TerminalAssociation`、二级 `ReconImageCue` 和 registration evidence 作为被动证据发布。
5. `cross_view_associations()` 或 `TerminalCrossViewFusion.associate()` 汇总重叠视场支持、metadata-only 分布式假设和重复锁定风险。
6. `summarize_degradation_case()` 输出 `no_degradation`、`degrade_to_secondary` 或 `degrade_to_distributed` 证据标签。

建议指标包括 `per_camera_detection_count`、`multi_target_fov_rate`、`cross_view_overlap_count`、`duplicate_terminal_lock_risk`、`terminal_lock_accuracy` 和 `ambiguous_fov_event_count`。多 seed 报告前可调用 `summarize_multiseed_calibration_readiness()` 检查每个 seed 是否有 local bbox/timestamp、geometry gate log、measurement age、backend/source、offline truth、bbox/handoff 和 conflict evidence 字段；二级 detect 未能转成跨视角关联时调用 `summarize_secondary_visual_coverage_funnel()`，区分三层指标：`visible_target_ids`/覆盖比例只表示“看见目标”，`secondary_network_joint_full_view_frame_rate` 表示多二级相机并集覆盖，`cross_view_association_count`/`multi_support_count` 才表示已形成既有 `global_track_id` 支持。该 helper 还输出 `coverage_mode_counts`、`mobile_recon_gimbal_improved_joint_coverage_frame_count`、`mobile_recon_gimbal_added_target_ids_by_frame` 以及云台 pointing/track error 字段。这些指标只供 D4/D6 仲裁和评估使用；D5 不生成 `AssignmentPlan`，不改写 `global_track_id`。

2026-07-10 状态：`p0_truth_isolation_smoke_20260710` 的三类 case 均连续运行 5 帧，匿名 local/detection ID 不含 actor 名，actor 名只保留在 `offline_truth_only=True` 元数据，每类 cross-view association 均为 4；truth ID 在线隔离 P0 已闭合。随后 `p1_gap_closure_calibration_20260710` 完成 5v5、10 seeds、50/200 m、三类 case 共 60 个 registration case，`not_registered_count=0`、`secondary_detect_available_but_not_registered=0`，平均 `projection_valid_rate=1.0`、stable registration `92.233`、cross-view association `4.417`。基础 detect-to-global registration 已闭合，但网络同帧全目标覆盖率均值仅 `0.0231`、平均覆盖率 `0.7059`，不能据此声明二级接管态势完整。

当前 P1 仅聚焦 M5N2 第二 primary、真实几何 drift、detect/YOLO/MOT 多 seed 和二级证据同一 decision tick freshness；遮挡/交叉与 local MOT ID 变化归入多 seed 检测/关联矩阵。真实身份源保持 P2。所有校准保持现有唯一性、友方冲突、版本、时效和 D7 独立安全门控；在线 D5 仍不得使用 truth ID 或 tracker ID 生成、改写、换绑 `global_track_id`。

## AirSim Blocks 2v2 二级计划语义

在主动降级后，D4/D3 的二级节点重分配结果仍必须以 `Assignment.assigned_global_track_id` 输入 D5。D5 只核对该 ID 对应的中心/二级计划航迹是否被本机 `simGetDetections` 检测框支持：

- `locked` 只表示当前 `assigned_global_track_id` 的投影与唯一稳定候选一致、已授权、版本一致、MOT 质量足够且无友方冲突。
- 若离线真值或评估元数据表明检测目标不是 `assigned_global_track_id`，D5 只能把该帧统计为 `locked_mismatch` 或阻断视觉 PNG handoff，不能把结果改写成另一个 `global_track_id`。
- bbox 连续稳定性由 `annotate_visual_png_handoff()` 检查；稳定性不足时即使单帧几何可 `locked`，也不得输出视觉 PNG handoff 建议。
- 已验证友方与门内候选重叠时必须 `hold`；未验证或疑似伪造身份声明降级为 `ambiguous`。

## 边界

本模块只用于科研仿真和离线评估；不包含真实火控参数、毁伤逻辑、实机飞控、硬件驱动、自动处置或绕过人工授权的流程。

## 2026-07-12 P1 M5N2 视觉鲁棒性支撑

D5 新增模块内 replay 回归，覆盖锁定后连续 1-5 帧观测缺失与恢复、同相机目标交叉、两相机部分重叠视场、外参漂移、量测时间偏差、相机间 local ID 重名和 MOT ID 变化。默认在线探测仍为 AirSim `simGetDetections`，局部 ID 保持 camera-local 匿名标识；注册仍使用 GlobalTrack 预测投影、像素马氏门控和 Hungarian 唯一匹配，在线路径不读取 actor/object/truth ID。

`TerminalAssociator` 的时间历史现在按 `resource_id + camera_id + assigned_global_track_id` 隔离。调用方应显式传入 `camera_id`；AirSim detect/离线 YOLO adapter 同时把 camera/resource scope 写入 `LocalVisualTrack.metadata` 作为兼容来源。不同相机即使出现相同 local ID，也不会共享丢锁或稳定窗口。

锁定后无 measured detection 时，D5 只输出身份、几何和时序证据：

- 1-2 个 10 Hz 缺失帧仍为 `reacquire`，不产生 lock、coast、KF 或控制量。
- 距最后 measured lock 超过 `max_missing_evidence_age_s=0.25 s` 后，输出 `terminal_visual_evidence_expired`、`visual_evidence_fail_closed=True`。
- 观测恢复后必须重新通过几何门、唯一候选、友方检查和 measured 稳定窗口；local MOT ID 变化不能直接继承 lock。
- 同一 `plan_id` 的下降 `plan_version` 输出 `hold/stale_plan_version_rejected`，不会污染当前版本历史；`clear_history()` 同时清除相机历史和 plan watermark。

模块回归为 `168 passed`。这关闭的是 D5 模块内 replay/helper 与保守证据语义，不代表真实 AirSim M5N2 长时视觉共识、持续 detect、YOLO/native MOT、真实外参同步或物理拦截已经闭合；这些仍是 main/runtime 多 seed P1 验收项。YOLOv8/ByteTrack/BoT-SORT 继续列为 deferred calibration，不替换 detect-first 默认链路。

### 版本化离线 summary

`run_p1_visual_robustness_matrix()` 将上述确定性 replay 固化为 `d5.p1_visual_robustness_summary.v1`，包含 10 个 case：1-5 帧 dropout/recovery、MOT ID change、same-camera crossing、cross-camera partial overlap、4 m extrinsic drift 和 0.5 s high-dynamic timestamp bias。每个 case 记录 `passed`、检查计数、保守拒绝计数、决策/拒绝原因分布、在线 truth 使用计数和 `global_track_id` 改写计数。

CLI 写出可直接交给 D6 `--d5-summary` 的 JSON：

```bash
python3 research_modules/d5_terminal_association/scripts/run_p1_visual_robustness_summary.py \
  --output /tmp/d5_p1_visual_robustness_summary.json

python3 research_modules/d6_evaluation_metrics/scripts/run_p1_acceptance_report.py \
  --output-dir /tmp/d6_p1_acceptance \
  --d5-summary /tmp/d5_p1_visual_robustness_summary.json
```

当前确定性结果为 `case_count=10`、`pass_count=10`、`reject_count=24`、`online_truth_use_count=0`、`global_track_id_rewrite_count=0`。D6 兼容字段和逐 case 紧凑结果同时保存在 `metadata`；完整 case/check 明细保留在顶层 `cases`。测试 truth 只用于在线关联返回后的离线期望检查，不进入 cost、gate、Hungarian 或 binding。模块回归更新为 `171 passed`。
