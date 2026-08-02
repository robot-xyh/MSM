# D5 终端视觉配准与身份认证计划

## 2026-08-02 A3 v3 producer 谱系恢复计划

- [x] 重新计算并逐项核对 main `learning_source_recipes.py` 与 `orchestrator.py` 的当前文件
  SHA-256；只更新实际发生漂移且已经验证的 producer binding。
- [x] 用 main recipe loader、D5 frozen loader 和 runtime config builder 遍历 104 条 entry。
  三分区计数为 `48/24/32`，9 个场景族、5 个规模、416 个窗口和 208 个困难混淆 assignment
  全部可构造；在线元数据无 truth/actor/object ID，权限全 false。
- [x] 用非正式 seed 执行五个 runtime probe，覆盖四类意图、两类相机角色和五类困难混淆。
  共 693 帧，在线 truth 使用和 `global_track_id` 创建/改写均为 0。
- [x] 重新冻结 schedule 自哈希和文件哈希，再级联更新 generation-only request 的 schedule
  binding、自哈希和文件哈希。当前 schedule file SHA 为 `d14b19d8...1082e`，request file SHA
  为 `157166b8...80b3`。
- [x] 通过 main generation API 在临时目录执行两次有界 train 续跑，每次最多 1 条。completed
  count 为 `1 -> 2`，future-held-out staged/payload count 为 0；未训练、未读取 held-out。
- [x] 定向回归 `51 passed, 1 warning in 20.13s`；D5 全量
  `877 passed, 2 warnings in 139.85s`，接受阈值为零失败。
- [ ] main 后续只能在新的 clean commit 和独立 generation-only authorization 下启动正式
  104 条来源生成。本任务未授予训练、validation consumption、held-out read、shadow、assist、
  runtime、control、camera command 或 `global_track_id` 写权限。

## 2026-08-01 A3 v3 真实 producer 可达性修复计划

- [x] 复现首条冻结配方：6 秒、四个 1.5 秒窗口、每窗 24 样本；默认 0.1 秒视觉周期下共有
  50 个主动视觉帧，首帧 0.85 秒，`intent-window-1` 只有 15 个唯一样本。
- [x] 将冻结 schedule 升级为 v3：episode 8 秒、四窗各 2 秒、侦察相机下限 4。配额保持
  24/窗、96/episode，不复制、过采样或跨窗口补样本。
- [x] readiness 升级为 v4，绑定真实 generation orchestrator、recipe loader、runtime adapter、
  module stack、orchestrator、主动视觉 treatment 和默认 0.1 秒基础配置的文件哈希。
- [x] 增加 104-cell viability audit。按最多 1.4 秒启动时间和最多 0.5 秒尾段缺口计算每个窗口
  的保守唯一决策容量；任一容量低于 24 时 source request 失败关闭。
- [x] 升级 generation-only request 为 v2并同步 schedule/staging SHA。当前 request 文件
  SHA-256 为 `157166b8...80b3`；执行、训练、验证、future 读取、运行和控制权限继续为 false。
- [x] 使用真实 scalable producer 验证首条配方并完成临时 development staging；另验证 train、
  validation、future-held-out、两种角色排列和五类困难混淆代表配方，实际每窗最低 32，在线
  truth 使用为 0。
- [x] 定向回归 `64 passed`，D5 全量 `875 passed, 2 warnings in 119.98s`，零失败。
- [ ] main 应在新的 clean commit 上重新生成 preflight 与 generation-only authorization。旧请求
  SHA 和旧授权均视为过期；本任务不生成 104 条正式来源，也不训练模型。

## 2026-08-01 A3 v3 来源生成请求与断点恢复计划

- [x] 新建独立 generation-only request；当前为 v2，以仓库相对路径和 SHA-256 绑定 protocol、
  schedule、allocation binding、global seed registry 和 D5 staging/resume 实现。schedule v3
  已按真实 producer 可达性修复，protocol 与 allocation binding 保持原字节。
- [x] readiness 与 producer capability 同时输出稳定的
  `source_generation_request_path/source_generation_request_sha256/`
  `source_generation_request_ready`。仅在 104 episode、48/24/32 split、seed
  `24000-24103`、一次性 future 合同和唯一 source-generation permission 精确成立时 ready。
- [x] descriptor 升级为带自哈希的 v2；新增只读 104-episode 恢复清单和严格幂等 resume helper。
  已完整暂存且内容相同的 episode 不重写；部分写入、损坏、hash/split/partition 漂移均拒绝。
- [x] 新增 `finalize_a3_v3_generation_partition()`。development 可做语义重验；future-held-out
  最终化只核对 descriptor 自哈希、冻结 recipe binding 和 online/offline 文件 SHA，不反序列化
  payload。manifest 固定 `future_held_out_payload_read_count=0`，并声明完整性核验不等于消费。
- [x] 请求、resume、future integrity-only finalize 定向回归通过；训练、模型、future payload
  读取/选模、shadow、assist、camera command、runtime、production、control 和中心 ID 写权限
  保持 false。定向 `61 passed in 1.29s`，D5 全量
  当前 D5 全量 `875 passed, 2 warnings in 119.98s`，均为零失败。
- [ ] main 仍需取得独立 execution authorization，并从合格 clean worktree 按 request 生成 104
  episode。request ready 不是执行 ACK；D5 本轮不生成正式来源。
- [ ] 生成后由 D5 以 generation finalizer 冻结两个 partition，由 main/D6 只读核对来源清单；
  future payload 长期读取计数继续为 0，直至模型冻结和 validation gate 通过后的另行一次性授权。

## 2026-08-01 A3 v3 episode evidence/writer 计划

- [x] 定义严格的逐 episode recipe DTO，绑定 schedule lineage、entry index、split、allocation、
  seed、episode ID、目标/资源/侦察节点数量、相机角色、四段意图窗口、困难混淆配方、控制项和
  schedule entry SHA-256。
- [x] 定义 truth-free 在线 evidence 与独立离线 audit。在线只保留双时间戳、匿名候选指纹、
  控制状态和中心只读 `global_track_id`；创建、改写和在线 truth 使用计数固定为 0。
- [x] 按每个连续 2 秒窗口独立统计唯一样本。每窗口至少 24、episode 总数至少 96；重复
  fingerprint、窗口/角色错配、缺控制状态或跨 episode 补 quota 均失败关闭。
- [x] 为五类困难混淆定义状态边界。标签由投影内外和新鲜度、侦察线索有无、云台忙闲、
  interceptor/recon 同几何签名、合法目标数与质量差推导，不接受 treatment 名直接贴标。
- [x] 实现 development/future-held-out 独立 staging 与 frozen finalize。保留 48/24/32 split，
  禁止随机重分、复制、过采样和跨 episode 配额转移。
- [x] 在 partition manifest 固定用途合同。future-held-out 禁止训练、拟合、选模、校准和阈值
  选择；development loader 禁止读取 future payload。
- [x] 实现 metadata-only source manifest assembler。仅在两分区完整覆盖冻结 schedule、来源
  lineage 一致、样本指纹跨分区无交叉时允许写出。
- [x] 增加最小合法 episode、重复 fingerprint、truth leak、窗口 quota、五类真实状态边界、
  角色/分配绑定、冻结 split、future isolation 和中心 ID 所有权回归。evidence 专项 `9 passed`，
  与来源 readiness 合并为 `35 passed in 1.16s`；D5 全量
  `846 passed, 2 warnings in 103.23s`。
- [x] main 完成 scalable_3d 逐 episode recipe、意图窗口 treatment、五类困难混淆证据适配和
  D5 单 episode writer smoke。非正式 seed `31100-31104` 覆盖五类边界，每窗口不少于 24 个
  唯一样本，在线 truth 使用为 0；main 专项 `4 passed in 17.65s`。
- [ ] main 获得单独执行授权后才可执行 104 个正式 episode。当前 request 已 ready，但未生成正式 inventory、分区
  manifest 或 source manifest，也未读取 future-held-out payload。
- [ ] D5 在实际 48/24/32 分区上 finalize manifest，main/D6 复核真实覆盖。完成前不训练；
  future-held-out 仍保持未访问。

## 2026-08-01 A3 v3 全局 seed 接线计划

- [x] 冻结 D5 allocation binding，固定 main 全局登记表 ID、内容 SHA-256、文件 SHA-256、
  A3 v3 协议 SHA-256 和三个来源 allocation。
- [x] 固定 train `24000-24047`、validation `24048-24071`、future-held-out
  `24072-24103`。三组 seed 整集互斥，每个 seed 只属于一个完整 episode。
- [x] 冻结含 104 条 per-episode entry 的 source collection schedule。每条安排四段意图窗口、
  两类相机角色中的确定角色、两类困难混淆 treatment 和 96 个最低唯一样本；集合覆盖 8 个
  意图-角色单元及五类困难混淆，不复制、重采样或注入在线 truth。
- [x] 实现只读 readiness 和 CLI。严格检查登记表双哈希、来源绑定、精确 seed/episode 集、
  协议配额重算、producer 文件哈希、能力声明和全 false authority。
- [x] 增加 allocation、split、coverage、future 权限、协议哈希、来源哈希、身份和 authority
  漂移负例。专项 `58 passed`，D5 全量 `837 passed, 2 warnings`。
- [x] 完成 producer adapter 独立 smoke，并把 readiness 更新为
  `source_generation_request_ready_generation_only`。逐 episode 字段、四段意图窗口、五类困难
  混淆状态、writer 配额和 resume/finalize 合同均有测试；该状态不授予执行权限。
- [ ] main 取得显式执行授权后，才能按冻结 schedule 生成三 split 来源并输出逐 episode/source
  manifest；不得读取 `1000-1019` 或复用 `22100-22199`。
- [ ] D5 对实际 source manifest 重新核验唯一 sample/episode/seed 覆盖。计划计数不能代替实际
  producer 证据；未通过前不得训练。
- [ ] 仅使用 train 更新参数，validation 只做最佳 epoch、温度校准和冻结门。通过后冻结模型。
- [ ] 模型冻结且 validation gate 通过后，future-held-out 才能一次性打开；失败后禁止训练反馈、
  重新校准、调整阈值或第二次读取。
- [ ] 在独立 D6 审计前保持 shadow、assist、promotion、runtime、camera command、control 和
  `global_track_id` 写权限为 false。

## 2026-08-01 A3 v3 少数意图开发协议

- [x] 仅依据 v2 train/validation 结构事实和已发布失败摘要，冻结层次化意图分类与合法候选
  排序；v2 test 不参与选模、校准或阈值。
- [x] 冻结 train-only 梯度/特征边界/class balance，validation-only best epoch/温度/开发门，
  以及 future held-out 一次性揭盲合同；失败后禁止反馈选模。
- [x] 冻结逐动作召回、interceptor/recon 角色精确动作、ECE 和规则回退门。意图辅助权重、
  排序修正、温度与置信阈值均有界，候选集合继续由确定性安全枚举约束。
- [x] 冻结 main-owned 新来源请求：train/validation/future seed 互斥，与 `22100-22199`、
  `1000-1019` 零重叠，并覆盖 8 个意图角色单元及五类困难混淆场景的 episode/seed 下限。
- [x] 实现 frozen config、JSON Schema、静态 validator 和后续训练入口预备。默认状态为
  `protocol_frozen_data_not_generated`；缺新 source manifest 时不读取 cache、不训练、不写权重。
- [x] shadow、assist、PPO、runtime、camera command、control 和 `global_track_id` create/write
  等全部权限保持 false；确定性规则继续默认。
- [ ] main 按已冻结的三组 allocation 生成全新开发与 future evaluation episode，提交
  source/coverage manifest。分配合同已关闭；实际生成、训练、validation 和 future held-out
  仍未执行。

## 2026-08-01 A3 v2 开发态行为克隆候选

- [x] 分开冻结并验证 dataset manifest 内生的 manifest/split/training-set 哈希，与外部
  generation plan、generation summary、training seed registry 绑定。summary 内 registry
  SHA-256 与实际文件一致；plan 本体不宣称内嵌该字段。
- [x] 仅以 registry 中 1000-1019 做禁止集合交集检查，确认 100 个开发 seed、三个 split 和
  保留集合零重叠；未读取或运行正式 R0 与保留 seed 样本。
- [x] 训练前冻结唯一配置：CPU、seed `20260720`、5 epochs、hidden dimension 64、batch
  2048、完整 train split、有界 `inverse_sqrt` 权重；无超参数搜索、无失败重跑，test 不参与
  训练或选择。
- [x] 构建 v2 strict feature cache，运行 corpus/source gate 后训练一次；cache、bundle 和
  47,045-byte 权重保存在 ignored outputs，不普通提交权重。
- [x] 评估 20 validation 和 20 test 未见 seed，输出逐动作、逐相机角色、置信校准、特征边界
  OOD、CPU 推理延迟和失败原因。validation/test 样本数为 24,329/40,133。
- [x] 保存 tracked JSON、中文报告、完整命令/config 及 model/manifest/cache/source SHA-256。
  bundle 状态为 `development_shadow_only`，shadow load 可用，assist load 失败关闭。
- [x] development precheck 实际未通过：`observe_target/search_sector` 召回均为 0，宏召回
  `0.495507 < 0.50`，期望校准误差 `0.368239 > 0.25`。未放宽门限、未改变 split、未重训。
- [ ] 下一独立工作包研究少数意图判别与置信校准。必须使用新的开发语料或预先冻结的方法，
  保留当前失败候选和 test 只读边界；本工作包不开展重复选模。
- [ ] 在新的模型通过 development precheck 前，不进入 A3/R0 paired shadow。AirSim、真实
  相机、applied-action/outcome 与真正场景域 OOD 仍需独立证据。
- [x] assist、promotion、PPO、assignment、degradation、runtime、production、control、
  camera command 和 `global_track_id` write 全部保持 false；默认确定性规则未改变。
- [x] 相关测试 `35 passed in 4.29s`；训练批次内 D5 全量
  `779 passed, 2 warnings in 102.40s`，收尾复跑
  `779 passed, 2 warnings in 124.10s`。py_compile、JSON/报告/哈希校验和与 owned-path
  `git diff --check` 通过。

## 2026-08-01 A3 v2 来源独立语料 owner 验收

- [x] 使用 D5 严格 lazy loader 全量校验 100 episode、159,502 sample 的 finalized immutable
  dataset。manifest、generation plan、split、training set、dataset config、逐文件 SHA-256、
  gzip 流、只读属性和来源摘要均完成绑定。
- [x] 运行来源研究门和训练结构门。状态分别为
  `point_mass_simulation_research_eligible` 与 `pass_development_corpus_only`，组合入口通过，
  failure reason 和 warning 均为空。
- [x] 按 train/validation/test 统计四类动作、两类相机角色及全部动作角色单元的唯一样本、
  episode 和 seed。train 的 `hold+interceptor=42669/60/60`、
  `hold+recon=1772/60/60`、`search_sector+recon=1023/60/60`，超过 `2/2/2` 下限。
- [x] 核对 159,502 个运行 ACK 全部 accepted，159,502 个匿名 observation key 全部唯一；
  在线 truth/actor/object ID 和中心编号改写为 0，来源全为 clean point-mass。
- [x] 保存 v2/20260801 机器 JSON 与中文 owner 验收报告，保留旧 v1 失败证据，不覆盖、不合并。
- [x] 未启动行为克隆或近端策略优化，未写权重；assist、promotion、assignment、degradation、
  runtime、production、control 和 `global_track_id` write 全部保持 false。
- [x] 2026-08-01 D5 全量回归 `776 passed, 2 warnings in 102.23s`，机器 JSON 解析和
  owned-path `git diff --check` 通过。
- [x] 独立开发任务已构建行为克隆 cache 并完成一次固定训练。模型逐动作/角色和未见 seed
  指标已形成，但 development precheck 失败；A3/R0 非退化评估尚未获准开始。
- [ ] 由 main/D6 后续提供 AirSim、真实相机和物理 applied-action/outcome 证据。本次质点语料
  结构门通过不能关闭这些跨模块边界。

## 2026-08-01 A3 补采运行时合同

- [x] 复核 `ActiveVisionCameraState` 与 `DeterministicLookAtScanPolicy`。现有
  `slew_available`、`action_in_progress_until` 和投影缺失语义可以自然产生补采动作，无需
  新增生产 API 或强制标签入口。
- [x] 覆盖拦截/侦察两类相机的 busy 与 unavailable 状态。两类输入均输出无目标、无扫描扇区
  的 `hold`，并保持中心计划中的 `global_track_id` 只读引用不变。
- [x] 覆盖侦察相机有中心分配但本相机投影暂时缺失的 cue-loss 状态。当前版本与通信健康时
  输出 `search_sector`，不把无投影解释为本地换绑。
- [x] 覆盖 `hold+interceptor`、`hold+recon`、`search_sector+recon` 三个空单元。每个单元
  的唯一样本、完整 episode、独立训练 seed 任一少于 2 时，训练入口保持失败关闭。
- [x] 2026-08-01 定向测试 `26 passed in 4.14s`；D5 全量
  `776 passed, 2 warnings in 102.06s`。本轮只增加合同回归，没有改生产策略。
- [x] main 在 scalable runtime 中传入真实云台忙碌窗口和按 cell cue-loss treatment。角色由
  `resource_id` 中唯一的 `interceptor` 或 `recon` 标记确定；忙碌使用
  `slew_available=false` 或未来的 `action_in_progress_until`；cue-loss 期间保留计划、航迹和
  版本，只暂时不提供该相机目标投影。
- [x] main 使用新 training seed 生成完整、来源独立的补采 episode。保留 1000-1019 和 R0，
  不复制、过采样、重加权、注入 fixture 或直接构造动作标签。
- [x] 新语料生成后重新运行严格 dataset、source 和 corpus gate。三个单元均已超过
  `2 sample / 2 episode / 2 seed`；本轮仍未训练或晋级，assist/promotion/authority 全 false。

## 2026-07-31 A3 独立来源语料验收

- [x] 独立 clean producer 冻结 100 episode、100 seed、45 个场景规模单元、159,487 样本；
  生产提交为 `4a8c1173179b4058d4aee38178e0fb40ecd222b3`。
- [x] 修复严格 `validate` CLI 对嵌套 `mappingproxy` 的 JSON 序列化失败。修复递归处理通用
  JSON mapping/list/tuple，并以真实 finalized 小数据集增加 CLI 回归。
- [x] 严格复载 manifest、逐文件校验和、只读属性、来源 envelope 和 split；manifest
  SHA-256 为 `bccbdad42a71b130720469bb4e99dd1dd99e29a9b33af036679b9d64b0fe35a4`。
- [x] 显式传入保留 seed 1000-1019，确认 train/validation/test 零交叉；该证据来源为
  `explicit_development_argument`，不冒充 canonical registry 正式绑定。
- [x] 来源/完整性研究门通过，九项合同检查全真；全部 claim limit 和 authority 仍为 false。
- [x] 训练结构门按 13 个原因失败关闭。train 中 `hold=0`、`search_sector+recon=0`；未启动
  行为克隆、近端策略优化、assist 或模型晋级。
- [x] 保存机器可读摘要和中文验收报告，区分匿名 observation key 覆盖与物理匿名观测帧证据。
- [x] episode dataset 专项 `19 passed in 3.55s`；D5 全量
  `770 passed, 2 warnings in 102.24s`；`git diff --check` 通过。
- [x] 按 `AV-CORPUS-001..003` 采集 `hold+interceptor`、`hold+recon`、
  `search_sector+recon` 完整新 episode。v2 实际覆盖和证据见本文件首节。
- [x] 补采后重新运行严格 dataset/corpus/source gate。v2 结构门已通过；本次任务没有生成
  训练 cache、权重或 paired-shadow 候选。

## 2026-07-31 A3 来源域与仿真研究门

- [x] 冻结五类来源域及证据等级：`legacy_unspecified`、`synthetic_fixture`、三维质点
  runtime、AirSim runtime 和真实相机 runtime。AirSim/真实相机等级只表示来源声明。
- [x] 强制 `synthetic_fixture=true` 仅能与合成 fixture 域同时出现；质点、AirSim、真实相机
  冲突声明和未知域均失败关闭。
- [x] 新写在线 header、episode descriptor 和 dataset manifest 必须携带显式 provenance。
  新非合成制品缺少来源时拒绝写入。
- [x] 保留专用旧读路径。缺 provenance 且 fixture 标志为真时只映射到软件 fixture；其余旧
  制品只映射到 `legacy_unspecified`，不能静默提升证据等级。
- [x] 增加质点仿真研究门。该门要求严格 loader、全量显式质点来源、clean source identity、
  版本/哈希、seed split、truth-free 和 corpus integrity 完整，并固定全部权限为 false。
- [x] 2026-07-31 定向测试 `43 passed in 7.83s`；D5 全量测试
  `769 passed, 2 warnings in 104.87s`。警告为既有 Matplotlib `Axes3D` 与 NVML 环境问题。
- [x] 由独立 producer 生成并冻结三维质点来源语料。2026-07-31 批次为 100 episode、
  100 seed、45 个场景规模单元；该 v1 批次来源/完整性通过，训练结构覆盖未通过。
- [x] v2 训练结构已补齐，并已在 20 validation/20 test 未见 seed 上完成一次固定配置模型
  评估。模型前置检查失败，不能进入 paired shadow。
- [x] 在独立语料上完成 A3 开发态行为克隆和评估；结果为
  `development_shadow_only/fail_closed_model_precheck`。AirSim/真实相机外部证明形成前，
  production、runtime、assist、相机命令、分配、接管和 control 权限继续关闭。

本节只关闭“来源域语义和仿真研究门”软件 P1，不改变后续模型与运行准入计划。

## 2026-07-28 A3 主动视觉训练语料覆盖

- [x] 新增公共 corpus audit/planner，按动作意图、拦截机/高空侦察机角色、场景、seed、
  意图与角色组合统计唯一样本、episode 和 seed 覆盖。
- [x] 冻结 development-only 结构阈值：每个意图至少 `4 sample / 2 episode / 2 seed`，
  每个相机角色至少 `8 / 2 / 2`，每个意图与角色组合至少 `2 / 2 / 2`。调用方可额外声明
  必须覆盖的场景版本。阈值不构成模型性能或运行准入指标。
- [x] 缺 `hold`、少数动作不足、侦察相机缺失和未知角色时失败关闭。输出稳定编号的
  `AV-CORPUS-NNN` 请求，给出需补采的场景、动作、相机角色、唯一样本、episode 和新训练
  seed 数量。
- [x] 训练、验证、测试和保留评估 seed 严格隔离。验证/测试样本不进入训练覆盖，显式保留
  seed 或 canonical seed view 与训练交叉时拒绝。
- [x] 重复 episode 和同一 episode 内重复策略输入均失败关闭并排除计数。复制、过采样、
  重加权和合成样本不能把正式 coverage 写成已满足。
- [x] 候选特征非有限、truth/actor 字段、候选动作不唯一、数据 descriptor 与实际 episode
  不一致时失败关闭；审计明确记录在线 truth 使用为 0 和中心 `global_track_id` 改写为 0。
- [x] 行为克隆 cache 升级为 v2，manifest 与 data audit 绑定 corpus audit 和 SHA-256。
  训练在模型初始化前强制要求审计通过；旧 v1 cache 缺审计时保持可读但禁止训练。
- [x] 正式行为克隆入口先保存 `training_corpus_audit.json`。审计器固定正式候选、未见
  非合成证据、运行 ACK/结果和全部运行权限为 unavailable/false，禁止通过重新计算哈希
  提权。
- [x] 2026-07-28 小型合成 fixture 覆盖缺类、少数动作不足、同 episode 复制、重复
  episode、角色缺失、seed split 污染、保留 seed、非有限特征、truth 字段、确定性输出、
  legacy cache、权限升级和训练前门。专项 `11 passed`；D5 全量
  `755 passed, 2 warnings in 123.86s`。
- [x] 独立 producer 按补采清单生成非合成训练 episode。v2 质点语料已补齐四类动作和两类
  相机角色；历史模型 `observe_target` 召回 0 和侦察相机约 `0.621823` 仍是旧模型证据。
- [ ] 使用绑定的正式 training seed registry 冻结 train/validation/test 与 reserved
  集合，并在 clean 来源上运行新审计和行为克隆 v2。100 episode、1200 sample 的补充课程
  是合成软件验证，不能关闭该项。
- [ ] 在至少 20 个独立未见、非合成 seed 上形成模型指标、A3/R0 成对非退化、运行 ACK 和
  动作结果谱系。上述证据形成前，正式候选、assist、相机命令、分配、接管和控制权限保持
  unavailable/false。

## 2026-07-27 A3 主动视觉模型前置缺口

- [x] 在正式缓存行为克隆链中统计每个 split 的意图、视场、相机角色和动作签名分布，不再以
  总体精确动作准确率代替少数动作覆盖。
- [x] 默认采用有界逆平方根意图权重训练，训练样本平均权重归一化为 1；使用同一训练意图
  权重选择最佳验证轮次。保留 `none` 作为开发对照，不改变确定性规则默认路径。
- [x] 对训练集中无正样本的动作保持 `unavailable`，禁止补零、伪造正样本或把缺失类解释为
  已覆盖。验证集若出现训练未见动作，使用最大验证惩罚而不是零权重忽略。
- [x] 行为克隆报告升级为 v2，增加宏平均 precision/recall/F1、每动作召回、真实/预测动作
  分布、拦截/侦察相机分层、精确动作置信度校准、训练边界分布外比例和诊断回退原因计数。
- [x] 增加 development-only 模型预检查。动作正样本/召回、宏平均召回、两类相机角色、
  期望校准误差或分布外比例任一不可用或越界时，禁止进入正式 paired-shadow 候选阶段。
  该检查同时要求每个动作在 train split 中有真实正样本，避免测试集偶然命中掩盖训练缺类。
  检查固定 `assist=false`，不授予主动视觉、分配或控制权限。
- [x] 明确逐动作指标分母。precision 仅在存在预测样本时可用，recall 仅在存在真实正样本时
  可用，F1 仅在真实或预测至少一方有样本时可用；宏平均分别按对应可用类计算。
- [x] 增加 99:1 极端不平衡回归。多数类预测的总体精确动作准确率为 0.99 时，
  `observe_target` 召回 0 和 `hold` 无正样本仍使模型预检查失败；无补零正样本。
- [x] 复核 observation-frame v2 回归。有分配目标的零检测帧仍为
  `reacquire + coverage=false`，不会转为 `locked/ambiguous/hold`。
- [x] 2026-07-27 D5 全量回归为 `744 passed, 2 warnings in 111.52s`。警告来自既有
  Matplotlib `Axes3D` 多版本环境和 NVML 初始化失败。
- [ ] 由独立 producer 补充真实 `hold`、`observe_target`、侦察相机、不同 FOV 和动作边界
  示范；不得由当前多数类数据过采样或补零代替。
- [ ] 在 clean/frozen 数据和模型谱系上重新运行行为克隆 v2，并在至少 20 个明确未见、
  非 synthetic seed 上完成 A3/R0 成对非退化。当前 2026-07-20 模型指标继续有效：
  总体 `0.955978`、`observe_target` 召回 0、`hold=0`、recon 约 `0.621823`。
- [ ] 只有模型前置检查通过、正式 unseen seed 谱系完整、每 episode 安全/可见率/重捕获
  均不退化且 production evidence assembler 可用后，才讨论 assist 晋级。本轮未运行
  900-cell 或大写盘实验，所有运行权限保持关闭。

## 2026-07-27 A3 主动视觉真实采用证据

- [x] 新增 D5 独立 A3 证据组装器和严格验证器，不在 D5 内下发相机命令。
- [x] 直接复用 `ActiveVisionDecisionV1`、`ActiveVisionRuntimeAckV1`、
  `ActiveVisionCameraFeedbackV1` 和 `ActiveVisionCameraState`；通过结构适配器读取 main
  的 `CameraObservationCommand`、`runtime.camera_command_ack` 和
  `CameraRuntimeState`，不新增平行 ACK 或相机控制合同。
- [x] 分层保存策略已求值、模型建议、确定性投影接受/拒绝、命令已下发、运行 ACK、相机反馈、
  姿态和视场已生效、后续物理观测窗口及关联/覆盖结果。
- [x] 用命令前相机状态和最终有效动作重算期望方位、俯仰及视场模式，同时核对 ACK 命令版本、
  计划/联盟/通信版本、命令有效期和反馈中的 `last_accepted_command_version`；新增
  `ActiveVisionA3CameraPoseLineage` 保存 ACK 后相机状态的三类版本和来源序号。
- [x] 新增 `ActiveVisionA3AnonymousObservationFrame` 和
  `ActiveVisionA3BindingEvidence`，保存逐帧匿名视觉观测、双时间戳、版本和只读中心绑定；轨迹键
  固定为 `resource_id/camera_id:local_id`。
- [x] 保留历史 observation-frame v1 的精确字段、非空轨迹和内容哈希合同；新增 v2
  `processed_zero_detections` 负观测语义及公开零检测帧工厂。v2 必须显式携带相机/资源、
  双时间戳、三类版本、来源序号和中心航迹只读清单。有分配目标时结果固定为 `reacquire`、
  覆盖为 0；无分配目标时 outcome 保持 unavailable。
- [x] 严格 loader、内容哈希和物理窗口支持同源 v1 非空帧/v2 零检测帧混合；继续拒绝
  runtime/synthetic provenance 混装、非中心目标引用及时间/版本/来源篡改。
- [x] 公共 API 固定匿名状态映射：`bound -> locked`、`ambiguous -> ambiguous`、
  `unbound -> reacquire`，且禁止据此本地创建或改写 `global_track_id`。
- [x] 只有非模拟 ACK、非模拟反馈、姿态版本真实生效、在线真值使用为零且中心全局编号改写为零
  时，才把模型动作记为 adopted。
- [x] 要求 A3 候选窗口与独立规则 R0 窗口在场景、规模、seed、相机、资源、目标只读引用、
  窗口序号、配对上下文、计划/联盟/通信版本及窗口时长上完全一致，且两臂来源日志不同。
- [x] 新增不含模型 provenance 的 `ActiveVisionA3RuleArmTrace`。规则臂只接受
  `requested_mode=effective_mode=disabled`、无模型建议、无模型指纹、零推理时延且
  `rule_action=effective_action` 的决定。
- [x] 新增 `assemble_active_vision_a3_rule_arm_trace()` 和
  `assemble_active_vision_a3_rule_arm_physical_observation_window()`。独立 R0 episode 可保存
  规则决定、命令、ACK、相机反馈和匿名帧，在不同进程中重建 trace 后形成 R0 窗口，不依赖候选
  trace 或候选模型制品。
- [x] 新增 `assemble_active_vision_a3_paired_evidence()` 唯一配对门。零个 R0 保持
  unavailable，两个及以上 R0 直接拒绝；跨键、跨相机、跨版本、同日志、时长不一致和双时间戳
  不完整均失败关闭。
- [x] 新增 `attempt_active_vision_a3_pairing()` 和冻结的
  `ActiveVisionA3PairingDisposition`。每条候选记录得到唯一 `pairable` 与稳定主原因码；成功时
  引用既有 paired evidence，失败时不携带 paired evidence。候选窗口为 `None` 时只记录粗粒度
  缺失，不虚构 ACK、相机反馈或匿名观测的细分类。
- [x] 固定逐候选原因优先级和诊断码：未实际采用、候选物理窗口缺失、同键 R0 缺失、R0 重复/
  歧义、键或配置不一致、物理证据不完整、收益结果不可用、证据合同无效。输入可为已验证对象
  或其严格 mapping；篡改和 schema 错误转为失败关闭 disposition，不从批处理中静默丢弃。
- [x] 新增 `ActiveVisionA3PairingDisposition.from_mapping()` 和
  `validate_active_vision_a3_pairing_disposition()`，严格校验精确字段、JSON 类型、schema、
  顶层摘要和候选引用。pairable 时复用 paired evidence validator 重算权限与内部一致性；
  unpairable 时禁止任何 paired evidence。
- [x] 新增 `ActiveVisionA3CandidateStageEvidence`，以 comparison/sample、相机/资源、
  adoption trace SHA-256、来源事件日志 SHA-256 和事件清单时间窗绑定候选运行阶段。只有
  对应的 inventory-complete 标志明确为真时，缺失字段才能解释为缺测：运行原因要求完整运行
  清单，观测原因要求完整观测清单，物理窗口细因要求两类清单都完整。
- [x] disposition 升级为 v2，同时保留 v1 严格复载。顶层 `reason_code` 不变；v2 使用受控的
  `candidate_stage_reason_codes` 区分运行 ACK 缺失/未确认、命令过期/时序不匹配、相机反馈
  缺失、匿名观测缺失/不完整和候选物理窗口明确缺失/不完整。细分原因由嵌入的阶段证据重算，
  未知原因、重算不一致、摘要篡改和跨 trace 引用均失败关闭。
- [x] 明确严格复载只证明 disposition 制品完整且内部自洽。原因码的物理或因果真实性仍需原始
  运行日志、时序链和外部审计证明，validator 不根据摘要反推原因。
- [x] 输出 `d5.active-vision-a3-benefit-audit-input.v1`，只开放
  `d6_benefit_audit_input_allowed`；模型、相机、分配、接管、控制、模型晋级、全局编号修改和
  G1 授权均固定为 `false`。
- [x] A3 专项合同累计 84 项，结果为 `84 passed in 1.38s`。覆盖阶段原因分类、
  部分或无完整清单时禁止猜测、v1/v2 持久化往返、v1 混入 v2 字段拒绝、阶段证据和顶层摘要
  篡改、未知细分原因、字段增删、精确 JSON 类型、嵌套权限篡改、pairable/evidence 矛盾，
  以及历史 observation-frame v1、v2 零检测、混合窗口、零覆盖和全部权限关闭。
- [x] 2026-07-27 当前完整 D5 回归为 `739 passed, 2 warnings in 97.98s`，零失败。警告来自
  Matplotlib `Axes3D` 多版本环境和 NVML 初始化失败。
- [x] 只读运行 D6 严格采用审计消费者回归，结果为 `58 passed, 1 warning in 9.40s`，证明
  v1/v2 disposition 公共 validator 未破坏现有完整分母消费；未修改 D6 代码。警告为既有
  Matplotlib `Axes3D` 环境提示。
- [x] main 已优先使用 `config.metadata.paired_exogenous_config_sha256` 形成
  `pairing_context_sha256`，把 `episode_id` 纳入来源事件日志摘要，并逐 episode 持久化
  `learning_adoption_evidence.json`。
- [x] 历史冻结批次以同一外生配置运行状态隔离的候选和规则 episode；20 个开发 seed 形成
  536 条候选动作。536/536 disposition 已持久化并可严格复载，其中 152 条可配对、384 条
  不可配对，主原因均为 `candidate_physical_window_missing`；覆盖率 `28.36%`，20/20 seed
  至少有一个可配对子集。批次 SHA-256 为
  `455d181076553a485ff824618abc6d037a4477bb6342877d1d1e427fd28583a9`。
- [x] D6 已按完整候选分母严格消费 disposition。由于存在合法 unpairable 记录，
  `a3_auditable_pair_count=0`，完整批次的实际采用、物理窗口、同键 R0 和收益计数均为
  `unavailable`，所有权限为 `false`。152 条可配对子集不能替代完整批次审计。
- [x] main 已对 536 条候选逐条调用 disposition API，保存原因分布并核对总数守恒；此前
  384 条静默跳过记录现均有失败关闭处置。
- [x] main 已用同配置 seeds `1000-1019` 和当前 candidate-stage sidecar 做不落盘全量重跑。
  536/536 候选有阶段证据，152 条 pairable、384 条 unpairable，完整可审计 seed 为 `0/20`。
  344 条同时为匿名观测缺失和物理窗口确认缺失；其余 40 条因观测清单不完整保持
  `candidate_stage_reason_codes=[]`，作为物理窗口缺失细因未解析。D6 聚合 evidenced=344、
  unresolved=40、`detail_completeness=false`；每 seed unresolved=2。部分清单门控因此避免
  把这 40 条越界归因为物理窗口不完整。ACK、确认、命令过期、时序错配和反馈缺失均为 0。
  摘要 SHA-256 为
  `1ba6040e7c3e7e3b9e7d5506dfd20cf3539ce12c5aac13cca7f02799f0cd99ef`。
  该摘要标记 `formal_evidence=false`、`source_worktree_clean=false` 和
  `persisted_full_pair_inventory=false`，只用于开发
  定位，不能关闭未见 seed、非退化、收益或授权缺口。
- [x] 完成 D5 侧可审计运行阶段证据 DTO、细分原因重算和持久化失败关闭合同。
- [x] main 已在 scalable 3D 开发运行中接入 truth-free 逐相机帧事件和 v2 零检测工厂。事件
  保留双时间戳、扫描序号、相机/资源及三类版本；A3/R0 按时间和版本绑定，观测触发命令并
  保留 0.25 秒尾窗，通信丢包/抖动使用独立随机流。scalable 3D 全量为
  `352 passed, 1 warning`。
- [x] 同配置 seeds `1000-1019` 默认通信退化开发复跑为 candidate `492`、pairable `488`、
  unpairable `4`、覆盖率 `99.18699%`；329 个 v2 零检测帧为 `reacquire/coverage=false`，
  159 个 v1 帧为 `locked`，empty rejected=0、权限全 false。零丢包/零抖动对照为
  `500/500`、覆盖率 `100%`。
- [ ] main 在 clean/frozen 后续批次逐候选持久化 v2 stage evidence、disposition 和完整 pair
  inventory。旧持久化 disposition 继续保留粗粒度 `candidate_physical_window_missing`，
  不得追溯改写。新开发结果为 `formal_evidence=false`、dirty worktree，seed 未证明 unseen。
- [ ] 在不放宽采用、版本、身份、时间窗或唯一 R0 门控的条件下，用 clean/frozen 制品复核
  默认 1% 通信丢包下的 4 条缺失，并区分相关性与唯一因果。
- [ ] 在至少 20 个未见 seed 上形成真实运行时 paired evidence。当前没有 AirSim 或实机收益
  证据；需完成正式未见策略的成对非退化评估后再讨论准入，A3 assist 和 G1 权限继续关闭。

## 2026-07-27 G1 v5 正式证据闭环

- [x] 在 clean commit
  `8d5e02ec989259ce3d39e1e4ad6a90dd0d8d5b54` 上冻结 runtime implementation SHA-256
  `b0708e718b374e5bb52db41c7bd2f994e340a2b009cfd348881a5f9d549baffe`。
- [x] 由正式 writer 生成 development manifest
  `7d459ed855cf74b810fa1f79ed0327efd39eb4be4409451266da3f3a95387ce0` 和权重
  `7fb5db8b6099ca4da5706a3bec53ff7cd634e8bd267c036ce3ee4ee4bf71ca71`。
- [x] 完成 20 个未见 seed、900 个 episode、45 个场景规模单元的 held-out；precision、
  recall、F1 和 candidate recall 均为 `1.0`，false merge 为 `0`，CPU P95 约
  `0.913 ms`。
- [x] 完成 900 帧、74024 条边的 paired-shadow；模型 edge/cluster F1 均为 `1.0`，最高
  单特征 AUC 为 `0.720073`。
- [x] 冻结 paired lineage SHA-256
  `83e105290f3e624f267d92ceaf050d32291bd5bbbabf98580846cd31498b1af1`，并验证
  900 条记录和 900 个唯一 episode UID。
- [x] D6 external audit v2 通过；文件 SHA-256 为
  `cbd6c72b2d9e7b78bf3aa36f975e6627250d2bf18de5a0b0ebc2c8f6cf760cd6`，内容
  SHA-256 为
  `334cf662e49c735931019ff358be1894d1358f1b4a5a868759eee41d3d282d15`。
- [x] 使用 D5 生产 assembler 生成 `d5.tracklet-model-bundle.v5`，manifest SHA-256 为
  `b431d066362005868374d038eb93a83b773c03715a53d8a9dfd0da21784f317d`。
- [x] D6 post-assembly v2 通过；内容 SHA-256 为
  `17dda42d06b4be1d21ff8f1f8baecc320fd49b532be06a9f9f6b304341763e1d`。
- [x] strict loader 与 shadow loader 通过；G1 assist 请求以
  `bundle_g1_assist_authority_not_granted` 失败关闭。
- [x] 保持模型晋级、G1 辅助、默认路径变更、分配、故障接管和控制六项权限全部为
  `false`；不启用在线 G1，不改变确定性规则默认路径。
- [ ] 使用代表性真实相机或真实 AirSim 图像重建候选图，验证真实相机泛化。
- [ ] 将中心 binding 结果与物理隔离的离线真值连接，验证中心
  `global_track_id` binding 正确性。
- [ ] 由 main、D6、D7 的跨模块闭环提供物理拦截结果；D5 不从合成图证据推导物理能力。

前述“正式 external audit v2、v5 与 post-assembly v2 待生成”条目已关闭。保留的三项工作分别
对应真实相机、中心身份绑定和物理闭环，当前审计状态均为 `unavailable`，继续列为 P1。以下按
日期保留的旧计划记录只说明当时状态，以本节为当前结论。

## 2026-07-26 v5 paired lineage P0（历史，已闭环）

- [x] 将 `paired_episode_lineage.jsonl` 增加为 `TrackletG1EvidenceInputs` 的显式输入，并要求调用方
  提供冻结 SHA-256。
- [x] 逐行解析 JSONL；拒绝空行、非法 JSON、非对象记录、空白 `episode_uid` 和重复 UID。
- [x] 固定正式门为 `record_count=900`、`unique_episode_uid_count=900`，并与 paired report、
  D6 external audit v2 `candidate.paired_lineage` 及 consumer episode count 交叉核对。
- [x] admission report v2 增加 lineage SHA、记录数和唯一 UID 数，并完成严格解析、序列化和
  manifest/report/D6/实物交叉绑定。
- [x] v5 实际复制 lineage 到 `evidence/paired_episode_lineage.jsonl`；manifest 登记四字段，
  `SHA256SUMS` 覆盖该文件，strict loader 每次重新解析和复核。
- [x] paired-shadow writer 使用 D6 v2 要求的
  `schema_version/filename/record_count/sha256`，frozen registry consumer 同步读取
  `filename`。旧 `file` 字段结构失败关闭。
- [x] 覆盖正向 v5 实物、缺失、哈希篡改、非法记录、重复 UID、899 条记录、paired/D6 计数和
  SHA 不一致、manifest/report 缺失或篡改。
- [x] 当前 runtime SHA-256 为
  `b0708e718b374e5bb52db41c7bd2f994e340a2b009cfd348881a5f9d549baffe`。
- [x] assembler 专项 `69 passed`，lineage 相关联合专项 `86 passed`，D5 全量
  `655 passed, 1 warning`。
- [x] main 审查并形成 clean commit
  `8d5e02ec989259ce3d39e1e4ad6a90dd0d8d5b54`。
- [x] clean commit 后从 development writer 开始重建 held-out、paired-shadow、lineage、
  registry 和 D6 external audit v2。
- [x] 全部新证据绑定同一 runtime 后装配正式 v5，并由 D6 执行 post-assembly v2。

本节记录 2026-07-26 的实现阶段。上述正式重证据、external audit v2、v5 装配和
post-assembly v2 已于 2026-07-27 闭环；旧 `fe116fd5...1c91` 及更早 runtime 的证据没有迁移。
默认规则路径和六项运行权限继续关闭。

## 2026-07-26 六权限合同 v2 与版本治理（lineage 修复前的中间阶段）

- [x] 定义 `d5.tracklet-g1-authority-contract.v2`，集中维护六个运行权限字段。
- [x] 将新 admitted bundle 升为 `d5.tracklet-model-bundle.v5`，新 admission report 升为
  `d5.tracklet-g1-admission-report.v2`。
- [x] 新装配只接受 `d6.d5-g1-external-audit.v2`。input spec 和 consumer contract 结构未变，
  分别显式保持 `d6.d5-g1-external-audit-input.v1` 和
  `d6.d5-g1-external-audit-consumer.v1`。
- [x] assembler 精确要求六字段全部存在、严格布尔且全部为 `false`；拒绝缺失、多余、拼写
  错误、旧四字段、未知 schema、非布尔、任一 `true` 和以 `reason` 替代权限。
- [x] v5 manifest 和 admission report 同时绑定合同版本、六权限、D6 文件 SHA-256 与内容
  SHA-256。
- [x] 旧 bundle v4、report v1 和 D6 audit v1 使用专用错误码失败关闭，不提供兼容白名单或
  同 schema 双语义。
- [x] post-assembly verifier 每次重新读取打包的 D6 审计，并与 manifest/report 交叉比对；
  不投影、不丢字段。
- [x] 分离证据资格与运行权限。状态为 `g1_evidence_eligible_not_authorized`；影子加载保持
  可用，G1 辅助请求在 `g1_assist_granted=false` 时以
  `bundle_g1_assist_authority_not_granted` 失败关闭。
- [x] 完成正例及缺字段、多字段、旧 schema、字段拼写、非布尔、权限为真、打包审计篡改等
  回归。assembler/loader 专项 `70 passed, 1 warning`，D5 全量
  `636 passed, 1 warning`。
- [x] 计算新 runtime implementation SHA-256：
  `fe116fd50975e4adc63354a591bbf88d5da0700b43c557dde569658d67e11c91`。
- [x] main 审查 D5 diff 并形成 clean commit；最终正式证据使用
  `8d5e02ec989259ce3d39e1e4ad6a90dd0d8d5b54`。
- [x] clean commit 后按最终 lineage runtime 重训并生成 development bundle。
- [x] 依次重跑 `20 seeds / 900 episodes / 45 cells` held-out、paired-shadow、paired
  lineage 和 shadow-only registry。
- [x] 由 D6 对新 runtime 和六权限合同重新执行 external audit v2。
- [x] 仅在 D6 external audit v2 通过后向全新目录装配 v5，运行 strict/shadow/assist loader
  探针，生成 post-assembly handoff 并交 D6 独立复审。

本节是 lineage 修复前的中间实现计划。2026-07-27 已针对最终 runtime
`b0708e71...baffe` 完成全部正式证据步骤；旧 `55066382...b8ea` 和
`fe116fd5...1c91` 证据未被迁移。默认规则路径和全部运行权限保持关闭。

## 2026-07-26 旧 D6 audit v1 与 v4 合同（修复前记录）

- [x] 核验带 `v2` 后缀的旧输出目录 `SHA256SUMS` 和全部 9 项 D5 引用输入；其 JSON 顶层
  schema 实际为 `d6.d5-g1-external-audit.v1`。
- [x] 确认审计 JSON SHA-256 `24c8b0cd...9ad7d`、内容 SHA-256
  `f17acecf...35f`、`status=pass`、blocker 为空，六类权限全部为 `false`。
- [x] 使用当时 runtime 的正式 evidence assembler 原子尝试装配；结果以
  `d6_authority_fields_mismatch` 失败关闭，未创建 v4。
- [x] 保持 development bundle、held-out、paired-shadow、registry、旧 audit v1、几何门限和全部
  权限不变；不投影审计字段，不增加兼容白名单。
- [x] D5 已实现版本化六权限合同；本条只记录此前阻断。
- [x] 已取得与同一 runtime 完全一致的 D6 external audit v2，并创建全新 v5、执行
  strict/runtime loader 探针并准备 post-assembly audit handoff。

当前新 runtime 的 v5 和 post-assembly handoff 已形成并通过 D6 v2 复核。在线 G1 权限仍为
unavailable；assist 探针按六权限合同失败关闭。规则路径继续默认。

## 2026-07-26 clean R0 与 G1 证据（历史 5506 runtime）

- [x] main 在 clean commit `64cb865b...2b05` 完成 20-seed 几何候选图 R0：`2670` 帧、
  `16842` 节点、`4658` 图边、`4642` 真边、`16` 假边和 `4645` 个真值合格对。
- [x] R0 precision/recall/F1 为 `0.996565/0.999354/0.997958`，hard violation 为 `0`。
  该结果只评价几何候选图，不评价 G1 模型收益。
- [x] 正式 writer 以冻结 composite/formal/supplemental 输入、原 seed 和 robust-v2 超参数完成
  确定性重训。新权重仍为 `7fb5db8b...ca71`，与历史权重完全一致；新 manifest
  `db908b05...1d14` 原生绑定该阶段 runtime `55066382...b8ea`。
- [x] 该阶段 runtime formal held-out 通过 `20 seeds / 900 episodes / 45 cells`。总体
  precision/recall/F1 和候选召回均为 `1.0`，错误合并率为 `0`，P95 推理时延约
  `0.872 ms`。
- [x] paired-shadow 正式通过。5 类真值无关扰动的最低边/簇 F1 均为 `1.0`，最高单特征
  AUC 为 `0.720073 <= 0.98`；在线真值、同相机候选和中心全局编号创建/换绑均为 `0`。
- [x] 通过正式冻结审计和 `assemble-registry` 形成该阶段 runtime 的 shadow-only registry。
  状态为 `evidence_chain_closed_shadow_only`，G1、辅助、权限和默认模型开关保持关闭。
- [x] 冻结 9 项实际文件哈希、当前实现谱系和 D6 external-audit 输入清单。顶层
  `SHA256SUMS` 全部通过。
- [x] 正式 writer/held-out/paired/registry 专项 `46 passed in 3.40s`；clean D5 全量
  `600 passed, 1 warning in 97.84s`。warning 为 PyTorch NVML 初始化提示，不影响 CPU 结果。
- [x] main 已调度 D6 owner 完成当时的外审；文件通过自身门限且六类权限全部关闭，但顶层
  schema 实际为 external audit v1，不能作为当前 v5 输入。
- [x] D6 已按最终 runtime 生成真正的 `d6.d5-g1-external-audit.v2`。
- [x] 历史 v4 仍保留失败关闭记录；最终合同和 runtime 证据已重新对齐，并已装配新 v5、完成
  D6 post-assembly v2。当前规则路径继续默认，旧 v4 继续因 runtime 不匹配而失败关闭。

本轮没有改变 AirSim 消息、settings、检测器、相机外参或 reset 接口。
`docs/AIRSIM_INTEGRATION_PLAN.md` 已检查，无需修改。

## 2026-07-26 关联图来源合同收口

- [x] 复核 main 提交 `690858a` 的近距正向开发结果：667 条真实目标视觉观测、294 条 candidate
  edge、247 条 retained edge、online truth use=0。该结果属于开发场景，不替代正式 R0。
- [x] 明确 `camera_batches` 只表示本次调用；新增 `association_tracklets` 和冻结
  `association_source_links` 表示实际关联图快照。保留 `tracklets`/
  `source_observation_links` 向后兼容别名。
- [x] 为 source link 增加 `arrival_timestamp`，并保留匿名 observation ID、tracklet key、
  camera namespace 和 measurement timestamp。
- [x] 对所有 source-bearing graph node 执行精确全覆盖校验。缺失、重复、未知 tracklet、
  错 camera namespace、observation 不一致和双时间戳不一致均失败关闭。
- [x] 保持缓存节点原来源和双时间戳，不预测、不重新标识；同一 local tracklet 跨调用可接续
  不同 observation，但每个图快照只链接当前节点状态。
- [x] 覆盖异步 `2-node/1-edge`、同步调用、OOSM、coast、多来源接续、缓存淘汰、stream/
  episode reset、缺失/重复/错命名空间/错时间链接。adapter 专项 `50 passed`，D5 全量
  `600 passed, 1 warning in 94.80s`。
- [x] 保持 truth/actor/object ID 隔离、中心 `global_track_id` 只读和全部几何门限不变。
- [x] main 用当前 clean 源码完成 truth-isolated 20-seed R0，冻结 graph、source links、
  offline labels 和实现谱系；候选图 precision/recall/F1 为
  `0.996565/0.999354/0.997958`，hard violation 为 `0`。
- [x] 正式 R0 已形成可计算的 candidate edge truth。该结果属于几何候选图，不证明 G1 收益。
- [x] 该阶段 runtime development bundle、held-out、paired-shadow 和 shadow-only registry
  已按上一节完成并冻结。
- [x] 修复前外审文件已通过自身门限且六类权限全部为 `false`，但其顶层 schema 是
  external audit v1，不是当前装配所需 v2。
- [x] D6 已针对最终 runtime 生成 external audit v2。
- [x] 历史 v4 装配继续保留 authority schema 不一致的失败关闭记录；最终合同和 runtime 证据
  已重新对齐，并已装配 v5、完成 post-assembly v2。规则路径默认，G1 在线作用域关闭。

本次没有改变 AirSim 消息、settings、检测器、相机外参或 reset 接口。
`docs/AIRSIM_INTEGRATION_PLAN.md` 已检查，无需修改。

## 2026-07-26 异步活跃相机快照收口

- [x] 复现 `Scalable3DTerminalAdapter.process()` 只消费本次 adapted batches 的问题：同步
  两相机同目标为 `2 nodes / 1 edge`，异步分两次调用在修复前为 `1 node / 0 edge`。
- [x] 增加按 `(resource_id, camera_id)` 隔离的有界活跃快照。只缓存匿名局部航迹及对应外参，
  默认有效期 `1.0 s`、最大 `256` 个相机流，不读取 AirSim truth ID。
- [x] 以本次顺序实测批次锚定图，复用其他相机仍有效的原始量测。保留双时间戳、像素与外参
  协方差，不预测、不重编号、不创建或改写 `global_track_id`。
- [x] 保持既有 `0.35 s` 量测时间差、`1.0 s` 到达时间差、外参年龄、missed-frame、几何和
  图候选门限。没有为了形成边调整阈值。
- [x] OOSM 不覆盖快照；重复量测、缺外参、旧状态、过期、容量溢出和重复节点失败关闭或剔除。
  `reset_stream()` 与 `reset_episode()` 分别清除相机级和 episode 级快照。
- [x] 新增固定标量诊断，区分本次更新、实测相机、跨调用活跃相机、复用航迹，以及时间、外参、
  过期、OOSM、重复和容量排除。诊断不写业务 ID。
- [x] 增加异步同/异目标、模型/规则评分、双时间窗、TTL、missed-frame、OOSM、缺外参、容量、
  同相机更新和两级 reset 回归。2026-07-26 adapter 专项为 `48 passed`，D5 全量为
  `598 passed, 1 warning in 97.36s`。
- [x] 复跑等价 5v5 seed `1000`、`2.2 s` 短输入。在线 6 条 `vision_bbox` 在离线 sidecar
  中均为 `known_false_alarm/truth_entity_id=null`；发布时刻 `1.25/1.75/1.95 s` 形成双相机
  节点，累计节点 `6 -> 8`，两次跨调用复用各 1 个匿名航迹。`support_by_node` 无共同中心
  `GlobalTrack`，预筛选正确保留 0 边，在线真值使用为 0。
- [x] 将该短输入证据限定为异步节点同图和虚警失败关闭，不用于判断真实目标跨视角候选边、
  几何门或 G1 收益。
- [x] 记录 D6 clean evaluator commit `107cf075...6a63c` 的正式 G1 v4 post-assembly audit：
  `status=pass`、blocker 为空、内容 SHA-256 `37384441...d852`、`20/900/45`，三项安全计数为
  `0`。该结果只证明装配完整性，不授予任何默认、身份、分配或控制权限。
- [x] 验证旧 v4 对该阶段新运行时失败关闭。运行时摘要 `55066382...b8ea` 与审计绑定的
  `408e71fe...f4fe` 不同，严格加载返回 `bundle_implementation_runtime_mismatch`，不增加
  兼容白名单。
- [x] main 已用 truth-isolated 20-seed 场景完成真实目标共同可见 R0。truth 只进入离线
  sidecar/评分，在线 DTO 和候选图保持匿名。
- [x] 已统计入图和候选边 truth：`2670` 帧、`16842` 节点、`4658` 边，候选图
  precision/recall/F1=`0.996565/0.999354/0.997958`，hard violation=0。
- [x] 已按该阶段运行时摘要重新生成 development bundle、held-out、paired-shadow 和 registry
  证据。
- [x] D6 已独立执行 external audit v2；通过后已装配新 v5 并执行 post-assembly v2。
  规则路径保持默认，G1 在线作用域关闭。

本次没有改变 AirSim settings、输入 DTO、检测器、相机安装、episode 编排或 reset 调用方式。
`docs/AIRSIM_INTEGRATION_PLAN.md` 已检查，无需修改。

## 2026-07-26 冻结 registry 生产合同收口

- [x] 在 clean commit `d437744c...4ffb` 重建 supplemental/composite、development bundle、
  seed `1000-1019` held-out、paired-shadow 和冻结引用。权重/manifest 为
  `7fb5db8b...ca71` / `0eff183f...da77`；900 帧、45 cell、lineage 900 条。
- [x] 实现 `assemble_frozen_tracklet_registry(...)` 和 `assemble-registry` 命令模式。五份输入
  均要求调用方冻结的文件 SHA-256；held-out/paired 还要求规范化内容 SHA-256。
- [x] 失败关闭地核对 reference/summary schema、bundle 三哈希、corpus manifest/config/content、
  held-out 文件/content、paired 文件/content、逐帧 lineage、目录计数和输入前后不变性。
- [x] 核对 reference、summary、held-out 和 paired 内全部权限字段；G1、assist、authority、
  default、运行时默认变更及中心 `global_track_id` 改写保持关闭。
- [x] 原子生成旧 D6 consumer 兼容的 `d5.frozen-tracklet-audit-evidence.v1`、冻结引用副本、
  中文报告和精确覆盖三份文件的 `SHA256SUMS`。目标目录存在或输出清单不完整时不发布。
- [x] 动态生成 limitation：单特征 AUC `>=0.995` 才保留合成捷径；共享全局航迹计数非零且近
  确定性时才加入独立阻断项。7fb5 clean 输入的只读预检 AUC=`0.720073`，没有共享计数捷径。
- [x] 增加低/高 AUC、共享计数、文件/内容/schema/lineage 篡改、权限、输出清单和非空目录测试。
- [x] producer 实现提交为 `fa3ec10`，已在对应 clean worktree 运行正式装配。固定目录为
  `outputs/d5_g1_clean_source_chain_d437744_20260726/model_registry/tracklet_gnn_7fb5db8b_registry_fa3ec10/`；
  发布时刻为 `2026-07-26T13:49:10Z`。
- [x] 校验根 `SHA256SUMS`、evidence schema、bundle 三哈希、held-out/paired/lineage 和
  20/900/45 目录；所有 authority 为 false。重复发布被拒绝且正式输出哈希不变。
- [x] D6 owner 已消费正式 registry、bundle、held-out、paired 和 lineage 并完成独立外部审计。
  正式 JSON 文件/内容 SHA-256 为 `10bf19f5...10b0` / `4e24ab33...e54`；
  `audit_passed=true`、blocker 为空且 D6 authority 全 false。
- [x] 使用正式 D6 JSON 运行 G1 v4 evidence assembler，原子生成
  `model_candidate/g1_assist_v4_7fb5db8b_d6_10bf19f5/`。manifest/weights/checksums SHA-256
  为 `a5a53de7...37154` / `7fb5db8b...ca71` / `1221ec23...c75956`。
- [x] 公开 strict loader 在 `require_g1_assist_eligible=True` 下通过；重复装配以
  `output_not_empty` 失败关闭，六份输入和六份输出哈希不变。
- [ ] 在线 G1 作用域、默认配置和真实候选门重新构图仍保持开放。v4 仅有
  `g1_assist_eligible=true`；default、全局身份、分配和控制权限均为 false。

本轮未修改 AirSim settings、相机模型、检测器、多目标跟踪、episode 编排或消息接口。
`docs/AIRSIM_INTEGRATION_PLAN.md` 已检查，内容不受本次离线证据生产合同影响，因此不修改。
2026-07-26 G1 assembler/strict-loader 定向回归为 `34 passed, 1 warning in 2.39s`，D5
全量回归为 `589 passed, 1 warning in 99.17s`。警告为本机 PyTorch NVML 初始化提示。

## 2026-07-26 G1 稳健候选收口

- [x] 为 supplemental 和 held-out 物理投影增加相机局部、标签无关的检测框尺度、尺度变化率和
  角速度量测误差，避免同目标跨相机特征完全相等。
- [x] 冻结 `d5-tracklet-robust-views-v2` 训练配置。每轮同时使用原图、遮挡重现代理、相似运动
  干扰和独立尺度抖动视图；变换不读取标签，不改变候选拓扑。
- [x] 分离模型实现来源和完整运行时来源，并要求共享源码逐项交叉绑定。当前模型/运行时摘要为
  `1883bc36...105` / `408e71fe...f4fe`。
- [x] 生成权重 `7fb5db8b...ca71`，完成 seed `1000-1019`、900 帧 held-out 和同图
  paired-shadow。held-out F1=1.0、错误合并率=0、候选召回率=1.0、P95=1.121304 ms；五类困难
  扰动 edge/cluster F1 均为 1.0；最高单特征 AUC=0.720073。
- [x] 保持 dirty-source 结果失败关闭。该历史阶段没有运行 D6 外部审计或 G1 assembler，没有生成 admitted
  v4，没有修改旧 bundle/manifest/报告、门限或兼容名单。
- [x] 在 clean commit `d437744c...4ffb` 上重建 supplemental/composite、重训 development
  bundle，并生成 held-out、paired-shadow 和 registry reference；producer-compatible
  `audit_evidence.json` 已由 `fa3ec10` 在 clean worktree 正式发布。
- [x] D6 owner 已对 clean 制品完成正式外部审计，D5 已据此生成 G1 assist-eligible v4。
  该状态不启用在线 G1；`default_model=false`，全局身份、分配和控制 authority 均为 false。

本轮没有修改 AirSim settings、相机合同、检测器、局部多目标跟踪、episode 编排或消息接口，
因此 `docs/AIRSIM_INTEGRATION_PLAN.md` 检查后无需更新。
2026-07-26 D5 全量回归为 `578 passed in 103.88s`，十个修改或新增 Python 文件通过
`python3 -m py_compile`。

## 2026-07-26 G1 证据装配闭环（历史 v4 合同）

- [x] 实现 D5 独立 G1 evidence assembler 和命令行入口。调用方必须显式提供 v3 development
  bundle、held-out、paired-shadow、D6 audit 四类实物及各自带外 SHA-256；接口不接受
  `TrackletG1AdmissionReport`、准入布尔值或权限对象。
- [x] 严格校验 D6 顶层 schema/content SHA、consumer schema、field availability、审计状态、
  全 false authority、failure reasons、20/900/45、三个安全计数，以及模型、实现、数据集、划分、
  训练集和两份评估报告的文件/内容哈希交叉绑定。
- [x] 仅在全部证据通过后，由 assembler 内部构造 admission report，并通过同级 staging 目录原子
  发布 `d5.tracklet-model-bundle.v4`。失败时删除 staging，不创建或覆盖目标 bundle。
- [x] v4 实际打包 held-out、paired-shadow 和 D6 audit 三份 JSON。`SHA256SUMS` 精确覆盖
  manifest、weights 和三份 evidence；公开 loader/runtime 每次加载都复算这些实物与 admission
  交叉绑定，任一篡改均失败关闭。
- [x] v4 只允许 `g1_assist_eligible=true`。`default_model`、全局航迹编号、分配和控制权限均保持
  `false`；production `write_tracklet_model_bundle()` 继续拒绝 caller-provided report。
- [x] 将 `tracklet_g1_evidence_assembler.py` 纳入 G1 `_IMPLEMENTATION_SOURCE_FILES`。该历史
  v4 阶段的实现摘要为 `41381db3d11371c049e5569658820ce98abf1a9966ecf86edc0f13f140894b07`；
  回归测试确认仅改变 assembler 摘要即可改变整体实现摘要。旧 development bundle 未绑定该文件，
  严格 loader 返回 `implementation_runtime_mismatch`，不设兼容白名单。
- [x] 正向 fixture 可原子生成 v4，并由公开 strict loader/runtime 加载。该结果只证明合同可执行，
  不代表该历史模型获准，也不构成真实多相机或 AirSim 性能证据。
- [x] 用 post-assembler D6 审计复核该历史 `99fa4428...d4cd` 实物。审计文件/内容 SHA-256 为
  `98bf9e02...c8ed` / `40a42af0...b90d`，绑定当时实现摘要 `41381db3...94b07`。assembler 返回
  `d6_external_audit_fail_closed`，进程退出码为 2，目标目录不存在。五项 blocker 为
  `implementation_evidence_unavailable`、`implementation_lineage_mismatch`、
  `robustness_threshold_not_met.cluster_f1`、`robustness_threshold_not_met.edge_f1`、
  `synthetic_single_feature_shortcut`。
- [x] clean `7fb5db8b...ca71` 候选已消除既有单特征 blocker，绑定运行时实现
  `408e71fe...f4fe`，完成 held-out、paired-shadow、正式 D6 外审及 v4 装配。
- [ ] 在真实或代表性匿名多相机输入上重新执行候选门并复核泛化；完成前不启用在线 G1，不改变
  默认路径或权限边界。
- [x] （历史状态说明）该 v4 阶段未实现 A3 主动视觉 evidence assembler。2026-07-27 已补齐
  独立采用证据组装和验证合同；真实运行接线、D6 收益审计和 assist 授权仍按本文件首节开放。

本次改变 G1 bundle 准入软件链和实现来源摘要。模块 README、原理、算法、实验报告及 D5 GAP/review
同步更新；AirSim settings、相机、检测、局部多目标跟踪、episode 和消息接口均未改变。
2026-07-26 最终证据同步复测为 assembler 专项 `14 passed in 1.15s`、模型流水线
`20 passed in 4.08s`；既有 D5 全量结果为 `571 passed in 99.00s`，验收要求为零失败。

## 2026-07-25 冻结图模型证据链

- [x] 冻结一个当前严格可加载的 development bundle，并用 tracked reference 固定 manifest、
  weights 和 bundle 校验清单 SHA-256。权重不进入普通 Git 提交。
- [x] 使用同一 `99fa4428...d4cd` 权重完成 seed `1000-1019` 的 held-out 评估和 paired shadow。
  20/20 seed、45/45 cell、900/900 帧完成，模型哈希在两层报告中一致。
- [x] 保持两臂同图、同候选和同外生输入。evaluator 标签在两臂概率输出和受约束聚类完成后才用于
  离线评分；在线真值字段和中心 `global_track_id` 改写均为 0。
- [x] 增加异步时间、外参漂移、遮挡重现代理、相似运动干扰和独立检测框尺度变化五类
  label-independent 反事实视图。候选拓扑和门控分数固定，扰动只作为评分器脆弱性诊断。
- [x] 增加在线评分边界异常回退探针。模型缺失、bundle 不可用、形状错误、非有限值、越界概率、
  推理异常、低置信度、非法阈值和超时共 9 类异常全部精确返回规则概率。
- [x] 发布 `model_registry/tracklet_gnn_99fa4428/` 小型可复核制品和
  `scripts/run_frozen_tracklet_gnn_audit.py` 入口。模型仍为
  `development_only_fail_closed`，不修改 manifest 晋级字段。
- [x] 完成 2026-07-25 D5 全量回归：`552 passed in 114.25s`。
- [x] main 在 D4 因果通信修正后复跑统一 module stack：
  `66 passed, 1 warning in 10.17s`。警告为既有 Matplotlib `Axes3D` 导入环境提示；
  本次只确认 D5 合同没有跨模块回归，不构成冻结图模型在线准入。
- [x] D6 已对固定 report、lineage、输入语料、bundle SHA 和当前 post-assembler 实现做独立复核。
  复核结果为 `fail_closed`，只完成外部审计，不开放 G1、assist 或 authority。
- [ ] 建设会重新执行物理候选门的独立困难集，覆盖真实遮挡重现、独立目标外形、时钟偏差、变化
  外参和相似运动负样本。当前 post-gate 反事实视图不能替代该项。
- [ ] 将权重迁移到可版本化的独立制品库或 Git LFS，并验证从空环境恢复。当前 tracked registry
  只保存哈希和证据，不包含权重。

## 2026-07-23 clean 4ac3bb2 seed 1000 profiler 收敛

- [x] 用 nominal 200v200 seed 1000 的冻结匿名 2.15 秒/9.95 秒在线日志归因长窗口成本；长日志 SHA-256 为 `c1dda852...6f77a`，覆盖 114 帧、723 个相机批次、2479 个检测/图节点和 2400 个 binding，truth source 未加载。
- [x] 热态 cProfile 定位历史 gauge 全 tracker 扫描、匿名 payload/ID 审计和 singleton binding 物化。`process()` 累计 `2.320→1.987 s`，`adapt_batches()` `1.428→1.122 s`，匿名 payload 审计 `0.358→0.162 s`，历史 gauge `0.0544→0.00288 s`，binding `0.0578→0.0312 s`。该证据对应最终零符号边界修复前的 `dc6bcd81...b4c4c`，不外推为当前源码 cProfile。
- [x] 实施四项局部等价优化：历史 gauge 增量账本、8192 项匿名 ID 正则 LRU、精确内建叶子审计快路径、singleton cluster 投影行复用。长日志固定诊断记录避免 91,871 次 tracker 引用扫描、复用 2289 个 singleton 行；79 个多节点聚合与 32 个无矩阵输出保持。
- [x] 增加旧/新规则等价回归和 `d5-scalable3d-operation-counts-v2` 固定诊断；冻结 v1 操作面通过投影哈希继续审计。短/长逐帧业务、最终 binding 和 v1 操作数哈希与 clean 记录逐项一致，online truth use、`global_track_id` mutation、降帧、降候选和门控变化均为 0。
- [x] 完成 singleton `-0.0` 边界修复和最终源码复核。当前 `sparse_tracklet_graph.py` SHA-256 为 `0e8a5880...19d5b`；机器 JSON 已增加 `post_boundary_fix_verification`，最终短/长业务、binding、v2 操作数和冻结 v1 operation-equivalence 哈希保持，truth use 与 ID mutation 为 0。
- [x] 两轮各 7 次描述性 A/B 的长日志中位值均值为 `1.149362→0.929495 s`，下降约 `19.13%`。墙钟只辅助确认 profiler 方向，测试不设不稳定硬时限。
- [x] main 对最终源码运行 D5 全量 pytest，权威结果为 `551 passed in 100.83s`，零失败。`550 passed in 102.41s` 是 boundary-fix 前历史值，不再代表当前源码。
- [ ] 长窗口单次成本 P1 保持开放。原完整集成 10 秒 P50/P95/max 约 `11.497/15.969/18.632 ms`、相对短窗约 `2.556x`，本轮没有当前源码完整集成复跑；后续仍需 main/D6 预注册正交多 seed 联合准入。

本轮不修改 AirSim、main、D6 或其他模块，不减少视觉帧、候选或门控，也不改变友方冲突、身份门、`global_track_id` 所有权和输出载荷。

## 2026-07-22 相机重叠索引局部收敛

- [x] 用 clean `f80b5bd` nominal 200v200、10 秒、seeds `42000-42002` 的冻结在线日志定位图候选阶段热点。seed 42000 的 116 次相机重叠索引累计约 `0.357 s`，旧三维空网格探测自身约 `0.248 s`。
- [x] 只实施一项低风险优化：复用已建立的只读占用桶序列，直接枚举占用桶对并检查切比雪夫距离。搜索半径、时间窗、视锥包围盒、预算、候选顺序和全部后续几何门不变。
- [x] 三 seed 交替配对中位耗时为 `1.551→1.313 s`、`1.501→1.262 s`、`1.406→1.149 s`，三 seed 中位值均值下降 `16.45%`。优化后重叠索引累计约 `0.117 s`。
- [x] 三 seed 的逐帧核心、最终 binding 和操作数哈希均与冻结记录一致；核心哈希包含几何拒绝和绑定代价。online truth use、`global_track_id` mutation、帧/候选减少、门限变化和 D7 gate 变化均为 0。主动视觉命令哈希保持。
- [x] 定向回归通过 `52 passed`，另完成 500 组随机占用桶与旧整数网格搜索等价检查。
- [x] D5 全量回归通过 `545 passed in 129.59s`。
- [ ] 主动视觉三 seed 集成累计均值仍约 `4.184 s`。合成同规模剖析中快照构造/真值隔离审计约为 `0.691/0.306 s`，但当前冻结日志不能重建真实逐帧主动视觉输入；在形成完整输入 replay 和安全拒绝哈希前不实施缓存或跳过审计。
- [ ] 长时超线性 P1 继续开放。下一轮由 main/D6 对检测数、相机数、中心候选数和时长做预注册正交多 seed 集成准入；不得把本轮单模块 frozen replay 写成 AirSim 或硬件实时性。

## 2026-07-22 f80b5bd 三种子集成证据

- [x] main 在 clean `8f86192 -> f80b5bd` 上完成 nominal 200v200、10.0 秒、seeds `42000-42002` 的同配置对照。三个候选 episode 均为有限状态，在线真值使用为 0，D1/D2/D3/D5/D7 最终数量与参考运行相同。
- [x] 完成跨提交逐条语义审计。只按 D3 plan occurrence/version 归一化独立运行产生的不透明 `plan_id`，并在归一化前验证 ACK 原始来源载荷 SHA-256；owner/version/coalition/`global_track_id`/command 等业务字段继续参与比较。三 seed 的逐条视觉 binding 和主动视觉载荷均语义相同。
- [x] D5 终端关联累计耗时三 seed 均值由 `2.545876 s` 降至 `1.974446 s`，约下降 `22.45%`。主动视觉由 `4.174315 s` 变为 `4.183797 s`，约增加 `0.23%`，按基本持平处理。
- [x] 每 seed 投影 DTO 缓存命中/未命中保持 `68/48`、`71/48`、`70/48`，最终 binding 保持 `22/29/28`。同一量测时刻的只读 center prediction 只在一次 `process()` 内复用，不跨调用、不减少候选、不修改中心 `global_track_id`。
- [x] 文档同步后运行 D5 全量回归，结果为 `544 passed in 163.09s`。
- [ ] D5 长时单次成本超线性 P1 保持开放。三 seed 累计阶段耗时下降不能替代正交控制检测数、活跃相机数、中心候选数和时长的多 seed 线性准入，也不能证明 AirSim 或硬件实时性。
- [ ] D6 仍需把 D5 固定大小操作数与阶段耗时纳入预注册正式性能报告；本轮跨提交语义等价和 clean 描述性计时不能替代正式准入。

## 2026-07-22 中心预测工作区收敛

- [x] 用 seed 42000 的 2.15 秒/9.95 秒冻结日志和固定大小快照进一步归因。长路径 33315 次局部匹配比较仅约占 `0.098 s`，472288 个 binding 单元约占 `0.057 s`；499505 个中心投影单元及重复轨迹数组物化约占 `0.706 s`，是本轮优化目标。
- [x] 在单次 `process()` 作用域内预先物化中心 position/velocity/covariance/timestamp 数组，并按唯一量测时刻缓存只读预测状态。短/长相机时刻组由 `76/715` 份重复预测收敛为 `23/116` 份；缓存不跨调用，不存在旧中心快照或旧相机状态复用。
- [x] 保留全部检测、相机帧、局部候选、几何/友方/身份/计划版本/唯一性门控和完整投影/binding 矩阵。短/长业务哈希、最终 binding 哈希与操作数哈希均和冻结记录一致；在线 truth 使用与 `global_track_id` 改写为 0。
- [x] 五轮交替配对重放中，短/长平均单次成本中位数分别为 `10.879 -> 7.610 ms` 和 `26.078 -> 19.145 ms`；长路径下降 `26.6%`。独立五次候选报告为 `8.522/20.163 ms`、增长 `2.366x`。D5 全量回归 `544 passed in 155.17s`。
- [ ] 超线性规模成本继续保持 P1。配对归一化增长为 `2.418x -> 2.450x`，与独立报告的 `2.366x` 存在墙钟波动，不能据此宣称线性准入。后续须预注册稳定计时环境，正交控制检测数、活跃相机数、中心候选数和时长，并运行多 seed。
- [x] main 已在当前源码 `f80b5bd` 上复跑 200v200、10 秒、seeds `42000-42002` 完整集成，并完成相对 `8f86192` 的逐条语义等价审计。D6 固定大小操作数与阶段耗时的正式联合准入仍按上节 P1 单列。

本轮没有修改 main/scalable、AirSim 或其他模块，也没有减少调用频率、合法候选或诊断字段。

## 2026-07-22 clean 集成证据同步

- [x] 在提交 `8f86192` 上完成 200v200、10 秒、seeds `42000-42002` 的 clean 集成复核。终端关联阶段耗时为 `2.4496/2.6355/2.5526 s`，均值 `2.6985 -> 2.5459 s`，下降 `5.7%`，调用次数保持 `116/119/118`。
- [x] main 在 episode 结束时持久化固定大小 `d5_terminal_performance` 快照；性能字段保持在旁路诊断中，不进入 `TerminalAssociation` 业务合同。D6 已对同三种子形成 clean descriptive 阶段汇总，但尚未聚合 D5 操作数。
- [x] 复核 seed 42000 的 116 次调用、2493 个图节点和 33315 次局部匹配对比较；在线 truth 使用和 `global_track_id` 改写均为 0。
- [ ] 保留超线性规模成本 P1。相同短长对照的单次成本增长由 `2.696x` 降至 `2.423x`，尚未达到线性验收；后续应按可见检测数、活跃相机数、中心候选数和 episode 长度做正交多 seed 扫描。
- [ ] 由 D6 按 seed 汇总 `d5_terminal_performance` 操作数并与阶段耗时联合展示；当前 D6 clean descriptive 报告只包含阶段时间和系统指标，不能替代该项。
- [ ] D6 当前结果只属于三种子 clean descriptive calibration。正式性能准入仍需预注册阈值、独立重复和更长时段，不得把本轮下降直接解释为真实 AirSim 或硬件实时性。

本轮只同步最终 clean 集成证据，不改变几何、身份、友方、计划版本、唯一性门控，也不改变图模型或主动视觉学习权限。冻结日志五次重放继续作为独立单模块 benchmark，不能与本节墙钟结果混算。

## 2026-07-22 三维长短序列操作数归因

- [x] 增加固定大小累计诊断，覆盖帧/批次、输入检测、局部历史、匹配比较、图节点/候选边/几何拒绝、评分/聚类、中心投影缓存、投影/绑定矩阵、匈牙利求解和绑定输出。诊断不进入业务 DTO，episode reset 后归零。
- [x] 对冻结 2.15 秒和 9.95 秒在线日志执行五次确定性重放。短/长序列分别为 23/116 次调用，平均单次成本 `9.165/19.564 ms`，调用密度增长 `1.090x`，单次成本增长 `2.135x`。
- [x] 证明增长与输入状态一致：每调用图节点增长 `5.815x`、投影矩阵单元增长 `7.274x`、绑定矩阵单元增长 `6.980x`；活跃局部历史峰值为 `81/416`，局部轨迹仍由 missed-frame 生命周期清理。
- [x] 对同批次相同相机元数据复用一次完整校验模板。复用签名覆盖全部实际消费字段；外参、内参、旋转或协方差变化时不复用并失败关闭。剖析中的模板准备耗时由 `1.012200 s` 降为 `0.532869 s`。
- [x] 逐帧核对 `TerminalAssociation` 核心输出和最终 binding。短/长业务哈希及最终绑定哈希分别与各自冻结记录一致；在线真值使用和 `global_track_id` 改写均为 0。
- [x] 保留标量局部匹配实现。向量化试验在相同业务哈希下产生运行时间回退，未进入最终实现。
- [x] main 已在 clean 集成 episode 结束时读取并持久化一次 `performance_snapshot()`；D5 reset 回归继续复核计数归零，性能字段未加入在线关联业务合同。D6 操作数聚合按上节 P1 单列。
- [ ] 使用更长、输入规模受控的多 seed 重放区分目标密度、相机可见流数和时间长度。若要压缩已接收时间戳审计集合，需先定义重复/OOSM 检测窗口和可接受漏判边界。

本轮不改变几何、友方、身份、计划版本、唯一性或保守决策门控，不改变候选预算，也不修改中心拥有的 `global_track_id`。

## 2026-07-22 三维长时性能收敛

- [x] 对 2.2 秒和 10 秒 clean 对照完成阶段剖析。主动视觉单次成本保持约 `53.127/53.261 ms`，总量增长来自稳态调用次数；终端关联单次成本由 `13.152 ms` 增至 `32.143 ms`，对应每次视觉候选均值由 `3.696` 增至 `21.491`。
- [x] 增加快照派生索引、中心投影距离矩阵复用、D2 DTO 内容指纹缓存和匿名 tracklet 序号集合。缓存覆盖适配实际读取的状态、协方差、航迹时间戳、版本和 ID，episode reset 强制清空；相机观测的量测/到达双时间戳仍按原路径处理。
- [x] 完成固定 10 秒在线日志三次重放和主动视觉规模基准。终端关联加速 `1.489x`，主动视觉加速 `1.444x`；116/116 记录精确一致，在线真值使用和全局航迹编号改写均为 0。
- [x] 增加长时/规模回归测试并完成 D5 全量回归，`537 passed`。
- [x] 完成发布载荷边界判断：main 总线的 8.273 MB 主动视觉载荷和 0.779 MB 终端关联载荷不在 D5 阶段计时内。本轮不修改消息合同、日志可观测性或发布频率。

本轮不改变相机和关联频率，不放宽几何、友方、版本和身份门控，不改变 `locked/ambiguous/hold/reacquire` 语义，也不授予可选图模型或主动视觉学习策略在线权限。

## 2026-07-22 同图配对影子评估收敛

- [x] 完成 `tracklet_paired_shadow.py`、命令行入口和专项测试。输入路径与带外 SHA 显式给定；目标
  目录必须不存在，发布过程原子化，已有证据不覆盖。
- [x] 对每帧构造一个只读 `SparseTrackletGraph`，将同一对象送入确定性几何规则和冻结模型。分别在
  规则评分、模型评分和受约束聚类后复算图数组及候选边 SHA；900/900 帧一致。
- [x] 将 evaluator 标签评分移到两臂概率推理和聚类之后。边标签与簇标签不进入任一预测路径；专项
  哨兵测试同时确认标签访问顺序和两臂图对象 identity。
- [x] 在当前源码上完成正式 v2：20 seed、45 cell、900 帧、13,344 节点、74,024 条候选边，目录
  完整且无重复/缺失。旧输出按 `superseded_preserved` 保留，v2 为 `authoritative`。
- [x] 输出边级和簇级精确率、召回率、F1、错误合并、同目标拆分、候选覆盖和 CPU 时延。冻结模型
  边/簇 F1 均为 1.0，规则边/簇 F1 为 0.367980/0.239234；45/45 cell 无质量退化。
- [x] 增加后验特征标签审查，不改变候选图、权重、温度或阈值。`shared_global_track_count=0` 覆盖
  74,024 条边，`=1` 无样本；尺度差、尺度率差和角速度差单特征最佳方向 AUC 约为 0.9973。
- [x] 保持同相机候选边、未标注边、在线真值和 `global_track_id` 改写为 0；保持 `G1/assist/
  authority=false`、`rule_fallback=true`。
- [x] 完成当前最终源码回归：paired-shadow 专项 `5 passed in 3.21s`，D5 全量
  `534 passed in 141.66s`。早期章节中的未完成项是历史快照，当前状态以本节 v2 清单为准。
- [x] D6 已在 2026-07-27 对最终 report、lineage、输入 SHA、900 帧证据、同图 checkpoint 和
  45 cell 非退化门做 external audit v2 与 post-assembly v2 独立审计。审计通过不改变任何
  在线权限。
- [ ] 建设独立于当前合成器的困难评估集。重点加入跨相机尺度偏差、目标外形差异、异步采样、外参
  漂移、遮挡重入和同运动困难负样本，并覆盖 `shared_global_track_count=1`。不得在该数据上重选本次
  冻结阈值；新模型或新阈值必须形成独立版本。
- [ ] 在真实或代表性 AirSim 多相机匿名 tracklet 回放上完成同图对照，再讨论 G1 研究影子资格。
  本次合成满分不构成真实跨视角泛化、M 对 N 联盟完成或线上准入。

## 2026-07-21 候选图邻居预算收敛

- [x] 对 clean supplemental 逐级归因：370,211 个可能跨相机 pair 中几何门仅拒绝 21 个，最终
  8 邻居预算从 370,190 条门后边删除 125,158 条。canonical test 候选召回历史值为
  `11409/16698=0.683255`。
- [x] 将默认最终邻居预算与前置候选预算对齐为 24。保留确定性几何评分排序和每节点常数度数上界；
  最大度数为 24，边数上界为 `floor(V*24/2)=12V`，不放宽任何几何、协方差、身份、版本或友方门。
- [x] 分离记录几何门拒绝和最终预算截断，并增加实际最大度数和边数上界诊断。现有 graph schema
  可复载新增计数字段。
- [x] 完成软件回归。seed 5、`delayed_noisy`、scale 200 四相机困难帧保留 15/15 个同目标 pair，
  候选召回 1.0、最终 cap 删除 0、实际最大度数 12；小 cap=2 时保持确定性和严格度数上界。专项
  `20 passed`、`13 passed`，D5 全量 `529 passed in 122.96s`。
- [x] main 已在 clean commit 上重建 4,500 帧 supplemental 和 composite view。补充集 370,190 边，
  组合视图 370,198 边，三个 split 候选召回均为 1.0；修复前 245,032 边只保留为历史证据。
- [x] 已完成 30-epoch 内部开发训练、seed `1000-1019` held-out 和权威 paired shadow v2。该完成只
  关闭合成离线证据；G1、assist、在线和相机控制权限仍保持关闭。

## 2026-07-21 保留 seed 独立评估

- [x] 建立独立 held-out schema、producer 和 strict loader。正式 profile 固定 seed `1000-1019`、45 个
  场景规模 cell 和 900 帧；训练 `0-99` registry 不参与 split，所有 episode 只使用
  `held_out_evaluation` 角色。
- [x] 复用现有物理投影和默认稀疏几何候选门。在线图保持匿名，evaluator truth 分离保存并用
  observation lineage 精确复核；禁止同相机边、未标注边和 `global_track_id` 创建、改写或换绑。
- [x] 实现目标目录不存在检查、source/output 重叠检查、临时目录原子发布、逐图 SHA-256、配置、
  manifest、lineage 和 source Git/config/schema/version 绑定。
- [x] 实现 development bundle 冻结评估入口。整体和逐 cell 输出分类、错误合并、候选召回、校准和
  延迟指标；held-out 不能调温度、选阈值或更新权重。
- [x] 增加训练 seed、seed 缺失/多余、cell 缺失、manifest/graph/lineage 篡改、同相机边、未标注
  边、权重篡改、调参/写权重企图和输出重叠的失败关闭测试。专项为 `17 passed in 1.09s`，D5
  全量为 `527 passed in 120.93s`。
- [x] 运行 1 seed × 2 cell 的代表性 smoke；2 个图帧均通过数据复载和 evaluator 安全审计。随机开发
  bundle 指标不足时保持 `fail_closed`，G1/assist/authority 未开放。
- [x] 已生成正式 900 帧 held-out corpus 并完成冻结模型全样本评估。20 seed、45 cell 完整，
  held-out manifest/report SHA 为 `496f8b31...4d2f` / `8095acc3...15c`。
- [x] 已在同一 `1000-1019` seed 上完成权威 paired shadow v2。45/45 cell 非退化；v2 仍要求 D6
  独立审计，G1、assist、在线身份和相机控制权限保持关闭。

## 2026-07-21 Composite 内部训练入口

- [x] 增加 formal + supplemental 只读 loader 和训练适配器。绑定 composite view、admission report、
  两份 seed registry 及源制品哈希，不复制或回写源数据。
- [x] 强制 seed 原子 `60/20/20`、保留 seed 排除、45 个场景规模单元、正负类、完整标签和同相机
  互斥；模型、特征、默认几何候选门、随机 seed 和 CPU 线程配置固定，漂移时失败关闭。
- [x] 对 clean composite 运行不训练 preflight。实测 4,972 帧、245,040 边、未标注 0，数据支持
  通过；preflight 文件 SHA-256 为
  `f4a498582cffa6672aa5775311f39ea1f5f12756383c9216ff04cbf8aaa026a8`。
- [x] 实现 D6-facing 内部模型测试报告导出。报告严格使用实际训练报告和 bundle；cell
  `sample_count` 使用已标注候选边数。报告不携带 G1/assist/authority 字段。
- [x] 增加成功预检、报告/view/hash 绑定、registry/split、保留 seed、同相机边、未标注边、权限
  分层和 D6 三件套正负测试。专项 `12 passed in 1.05s`；D5 全量
  `510 passed in 121.82s`。
- [x] 已在 clean worktree 执行固定 30-epoch 内部开发训练，最佳 epoch 25；模型 manifest/weights
  SHA 为 `d7feb248...921` / `4f5e8cee...1e50`，内部测试 F1 为 1.0。
- [x] 已完成保留 seed `1000-1019` 独立评估和同 seed paired shadow v2。结果受合成集近确定性特征
  限制，G1、assist、在线和相机控制权限继续关闭。

## 2026-07-21 跨视角困难样本课程与准入视图

- [x] 只读审计冻结正式图语料的 99 条未标注边。194 个缺失端点中 95 条边两端缺失、4 条边缺
  source 端；冻结导出没有精确 offline observation truth lineage，同 tracklet 也无其他 evaluator
  label，可靠回填数为 0。99 条边继续 `unavailable`，未修改正式源，未采用最近邻、连续性或伪标签。
- [x] 新增独立 supplemental producer，使用与正式源分离的随机流、100 个训练 seed 和 45 个场景
  规模 cell，覆盖相机基线、密集交叉、遮挡进出、时间偏差、外参扰动、漏检、虚警和 tracklet
  重入。候选边仍使用默认时间、视场、极线、射线、重投影、协方差和度数门，不提供降低门限参数。
- [x] 保持在线节点匿名，truth 只在图构建后按精确 observation lineage 加入物理分离 evaluator
  制品。manifest 绑定 Git/config/schema/version、正式 manifest、training/shared registry、默认门
  配置、实现文件和全部制品 SHA-256；拒绝保留 seed、重复图/边、缺标签、hash 篡改、split 泄漏、
  候选门变化、负边伪造和正式源变化。
- [x] 实际生成 4,500 帧、66,726 节点和 245,032 边，正/负/未标注为
  `57292/187740/0`，标签可用率 100%，与正式源重复违规为 0。共享 seed 分桶为 `60/20/20`。
- [x] 建立 detached formal + supplemental canonical admission view，不复制或回写两类源数据。组合
  视图选入正式 472 帧和补充 4,500 帧；各 split 无边比例不超过 10.45%，负边支持均远高于
  `100/30/30`，候选召回分母均高于 100，标签可用率与双类 cell 比例均为 100%，数据支持门通过。
- [x] 本轮明确只闭合 producer 与数据支持，不训练新模型、不生成 `.pt`、不开放 G1/assist，D5 不
  创建、改写或换绑 `global_track_id`。专项 `12 passed in 5.49s`，全量 D5
  `498 passed in 124.90s`。
- [x] main 已基于 clean commit `79b2550ce2ef407c7cfcc653ce04a80fe2226c06` 在 detached worktree
  同配置复生。clean output 已归档到
  `outputs/tracklet_graph_supplemental_curriculum_20260721_clean_79b2550_r2`；补充 manifest/view SHA
  为 `4b9875fee86b5c425f683a6da23e6af1308bcf2383d3633d4fd6207fe2f25a32` 和
  `11e8acbdbe268574ead402f2be5c9aa8e3459a7e4147a18e0570df3402892415`。dirty=false，数据支持与
  `training_readiness` 均 pass，dirty provenance blocker 关闭。
- [x] 已完成新模型、保留 seed 独立评估和同 seed 影子对照。该完成不等于 model promotion；合成
  特征可分性、D6 独立审计和真实多相机泛化仍开放，G1、assist 和在线/相机控制权限均为 false。
- [x] 主工作区严格复载 clean supplemental 与 composite view，实测 manifest/view SHA 命中、
  `data_support=pass`、`training_readiness=pass`、promotion 等待模型证据；专项测试
  `12 passed in 5.40s`。正式源全树指纹复载前后不变。

## 2026-07-21 Supplemental BC 全样本准入审计

- [x] 新增只读 fail-closed 审计入口，复用 strict lazy loader、canonical loader、既有 supplemental
  合同审计与 BC 候选特征 API；逐项复核 dataset 全文件 SHA/集合、1200 个样本、版本、中心 ID、
  truth/dirty/reserved、synthetic ACK 边界和四类 unavailable label。JSON/Markdown 只能原子写到
  supplemental 与 registry source root 之外；绑定错误仍写 `pending` 报告并由 CLI 返回非零。
- [x] 2026-07-21 对 clean commit `13e37286d2996a227924bb1a8e2766e52116a534` 的实际制品完成审计。
  接受阈值为 100 episode、1200 sample、canonical `60/20/20` 与 `720/240/240`、302/302 文件 SHA、
  1200/1200 有限特征和零违规；实测全部通过，7800 个候选特征行、1200/1200 唯一规则示范、
  truth/reserved/dirty=0。tracked JSON/中文报告已发布，内容 SHA 为
  `a11b65596a4c416deba6d0cb35dcc0c32342a5bae0481291d43e8de0e26550dd`；新增专项
  `4 passed in 35.72s`，D5 全量 `486 passed in 119.63s`。
- [x] 关闭 supplemental producer/canonical 之后的 behavior-cloning full-sample audit 子项；确认
  `400/400/400` 仅为 synthetic 故障覆盖，四类 label 均 `0/1200 available`。本轮没有训练、AirSim、
  `.pt` 权重或数据树写入，PPO/assist/authority=false，rule fallback required=true。
- [ ] 由 main/D6 完成跨模块学习准入审计；真实 runtime ACK/outcome、reward/counterfactual/causal、
  paired shadow 未完成前，不开启 PPO、assist、在线或相机命令 authority。

## 2026-07-21 主动视觉课程阶段 B1b2

**Clean evidence：** main 已在 detached clean worktree `13e37286d2996a227924bb1a8e2766e52116a534` 完成 100/800/1200 与 canonical `60/20/20`、`720/240/240` 的实际生成；dataset/view/config/training-registry/shared-registry/summary-content SHA 分别为 `0c474ee1b0bab34a46c2ebce328761983cf2ecc757da30c2d3d2e03a06cd1acf`、`0ab1a4a6bdd439f6c8a74df5059de3c4950791fba35a1b9514942e83779f72a8`、`e93ca6310338be5db4539fac195f5257e28d16a64b78b1a0351bf6aeca01fcee`、`2ab928a476a4430b99326f245222f058bc5be5025158134ba89b01b3dec7815f`、`68608d29d1f733beea87f1faf06464fededb68a9c2972c51c10cd4c2160f032f`、`0577c73810413ced6277e679477422f467cb2db094f1d376e39e4cbb2a3abd65`，正式树前后 SHA 同为 `8ffbe5cf044d121163c8acc3dce1bbd54e14bb6b211b8e1cf440f24c93294fca`；clean producer/canonical evidence 已关闭，synthetic ACK 不作真实 ACK，PPO/assist 仍关闭。

- [x] 新增独立 100-seed producer。严格读取 training registry 的 100 个 seed 和 `1000-1019`
  保留目录，预检 shared registry schema/content/source binding，并在 canonical API 中完整复算 policy、
  assignment 与 `60/20/20`；两个 registry 文件 SHA256、dataset config、manifest、view/content 和
  readiness SHA 均进入 summary。
- [x] 每 seed 只调用 `build_active_vision_curriculum_episode()`，随后复用
  `stage_active_vision_episode_record()`、`unavailable_active_vision_offline_labels()`、
  `stage_active_vision_offline_labels()`、`finalize_active_vision_episode_dataset()` 和 lazy loader；未复制
  active-vision 在线/离线序列化合同。
- [x] 输出目录必须不存在。100 episode 在 sibling 临时目录完成全部生成、finalize、canonical、
  readiness、逐 episode 审计和重载复核后才用 `os.replace()` 发布；目的目录竞争出现或任一步失败均
  不发布并清理临时目录。
- [x] training/shared registry 各自的父目录均作为只读 source root；正式布局中 shared registry
  位于 training root 下时由外层根覆盖，二者分离时分别保护。output、tracked JSON/Markdown 等于或
  位于任一根下时，在创建目的、临时或 tracked 目录前失败关闭，并保持 registry 文件哈希不变。
- [x] 聚合合同固定为 100 episode、800 segment、1200 sample；canonical seed/episode
  `60/20/20`、sample `720/240/240`。四 intent、wide/zoom、interceptor/recon 和三 ACK 均逐 seed
  复核；`4/4/4` 只记为 executor 故障覆盖，不作为真实 ACK 分布或收益。
- [x] reward/outcome/counterfactual/causal label 全部显式 unavailable；synthetic、dirty、truth、
  reserved leakage、版本和中心 ID 均失败关闭。dirty 状态为 `fail_closed_dirty_source`；PPO、assist、
  在线 authority 和相机命令权为 false。
- [x] CLI required 参数为 `--output-dir --training-seed-registry --shared-seed-registry
  --created-at-utc --global-track-id`，默认读取 Git provenance，可选
  `--tracked-summary-json/--tracked-report-markdown`，Markdown 报告为中文。2026-07-21 新增专项
  `15 passed in 71.87s`，D5 全量 `482 passed in 83.05s`。
- [x] main 已在上述 clean revision 使用正式 registry 执行 CLI，归档 ignored output、tracked
  JSON/中文 Markdown 及实际 SHA；正式 900-episode 输入树未修改。
- [x] 已对绑定 dataset/view/config/registry 执行 supplemental BC 全样本审计并发布零违规证据。
- [ ] 由 main/D6 做跨模块准入审计；真实
  runtime ACK/outcome、reward/counterfactual/causal label 和 paired shadow 未完成前，不开启
  PPO/assist/在线或相机命令权。

## 2026-07-21 主动视觉课程阶段 B1b1

- [x] 新增 `active_vision_curriculum.py` 的单-seed、纯内存 supplemental curriculum builder。
  调用方必须显式提供 `ActiveVisionSourceIdentityV1`、配置和中心拥有的 `global_track_id`；builder
  只读复制该 ID，不创建、改写或换绑中心身份，任意非负整数 seed 均可确定性构造，负 seed 拒绝。
- [x] 固定 8 个片段形成 1 个合法 `ActiveVisionEpisodeRecordV2`、12 个连续样本。intent 精确为
  `hold=2 / observe_target=6 / reacquire=2 / search_sector=2`，FOV 为 `wide=10 / zoom=2`，角色为
  `interceptor=6 / recon=6`；每个角色都覆盖四类 intent、`wide/zoom` 和三类 ACK 结果。
- [x] 全部 effective action 都由按片段隔离状态的 `DeterministicLookAtScanPolicy` 经
  `ActiveVisionControllerV1` 产生，再进入 `DeterministicCameraCommandExecutor`；未手填 decision 或
  非法 effective action。两个三帧 observe 片段分别通过既有稳定门自然产生 `WIDE/WIDE/ZOOM`。
- [x] ACK 精确为 `applied=4 / rejected=4 / missing=4`。producer 调用执行器时始终令
  `command_version == action.communication_version`；accepted ACK 与反馈最近接受版本一致，rejected
  和 missing 对执行器输入反馈保持对象不变且不推进最近接受版本。该分布是确定性故障输入覆盖，
  不是 main/runtime 的真实 ACK 频率证据。
- [x] sample timestamp 严格递增，sequence index 为 `0..11`；plan/coalition 按片段单调推进、
  communication 按样本严格递增，snapshot/action/sample/ACK 版本逐项一致。在线 record 通过 truth
  guard，不含 evaluator identity；builder 不生成 reward、outcome、counterfactual 或 causal label，
  不写磁盘、不接 canonical/CLI/报告。
- [x] 同 seed 的 record 对象和规范 JSON、summary 对象和 JSON 均确定；调用方 source/config 输入不变。
  2026-07-21 新定向测试 `12 passed`，主动视觉关联回归 `56 passed`，D5 全量
  `467 passed in 10.40s`，`py_compile` 通过。
- [x] B1b2 已复用该 builder 完成独立 100-seed 生成、detached finalization、canonical
  `60/20/20`、CLI 和严格统计接口；clean producer/canonical evidence 后续已由 `13e3728` 实际制品
  关闭。supplemental BC 全样本审计也已关闭；开放项仅为 main/D6 跨模块准入、真实 runtime
  ACK/outcome、reward/counterfactual/causal、
  paired shadow 及 PPO/assist/authority 准入。

## 2026-07-21 主动视觉相机执行器阶段 B1a

- [x] 新增无隐藏状态的 `DeterministicCameraCommandExecutor`。输入沿用现有 snapshot、action 和
  camera feedback，并显式携带执行时刻、期望计划/联盟/通信版本及可选故障注入。
- [x] 每个动作先通过 `validate_active_vision_action_v1()`；随后只允许反馈态和运行时故障增加拒绝，
  不允许绕过或放宽既有版本、身份、投影、友方、云台和 FOV 门。
- [x] 冻结三态结果：`applied` 生成 `accepted=true/status=applied` ACK 并更新动作后反馈；
  `rejected` 生成稳定拒绝 ACK 且原反馈不变；`missing` 保持 `runtime_ack=None`、反馈不变且
  `applied=false`。
- [x] 成功 ACK 的 `command_version` 与反馈 `last_accepted_command_version` 一致；ACK 的计划、联盟和
  通信版本沿用已验证 action，可直接通过现有 episode sample 合同。旧命令版本失败关闭。
- [x] 2026-07-21 定向测试 `18 passed`，D5 全量 `455 passed in 12.18s`。覆盖 WIDE/ZOOM/HOLD、
  过期、三类版本错、相机忙/不可用、FOV 不支持、非法动作、ACK 缺失、truth guard、确定性和输入不变。
- [x] 阶段 B1b2 已接 supplemental curriculum producer、canonical `60/20/20` 和统计接口。
- [x] main 已在 clean revision `13e3728` 生成 detached supplemental 制品并归档实际 SHA，关闭 clean
  producer/canonical evidence。
- [x] supplemental BC 全样本审计已完成并绑定 clean 数据 SHA。
- [ ] main/D6 跨模块准入、真实 runtime ACK/outcome、reward/counterfactual/causal、paired shadow 和
  PPO/assist/authority 准入仍未完成；B1a/B1b2 与本审计均未运行 AirSim。

## 2026-07-21 主动视觉宽视场稳定门阶段 A

- [x] 在 `DeterministicLookAtScanPolicy` 内建立按相机、中心目标、计划版本和联盟版本隔离的状态键，
  默认连续 3 帧稳定后才允许由宽视场切入窄视场；`N=1` 保留即时缩放兼容选项。
- [x] 稳定帧继续复用既有新鲜度、可见概率、遮挡、关联置信度、`in_fov`、当前分配、版本、通信、
  友方保留和云台包络门，不降低任一安全阈值。
- [x] 对计划/联盟/目标变化、时间回退、证据回退、低置信/投影失效、通信异常、友方冲突和相机忙
  清空相机局部计数；重复同一帧不累计，不同相机不串状态。
- [x] 多个当前分配投影的质量间隔小于默认 `0.05` 时按歧义处理，输出
  `REACQUIRE + WIDE`；重捕获和扫描选择 `WIDE`。云台忙时保持当前 FOV，恢复后从宽视场窗口重计。
- [x] 新增 8 项稳定门专项；主动视觉定向组合 `47 passed`，D5 全量
  `437 passed in 10.28s`。未运行 AirSim，未训练或晋级模型。
- [x] 阶段 B1b2 已建立 supplemental curriculum producer 接口，覆盖
  hold/observe/reacquire/search、两相机角色和视场边界，且不修改正式 900 episode。
- [x] 软件阶段 tmp_path fixture 保留为历史验收；main 后续已在 clean revision `13e3728` 生成实际
  supplemental 制品并归档 SHA，正式 900-episode 输入树哈希前后不变。
- [ ] main/runtime 将真实 applied/rejected/missing ACK 以现有 episode 合同回灌后，再决定是否把 ACK
  纳入稳定门。当前 snapshot 不含 ACK，本阶段不得伪造或扩 DTO。
- [ ] 只有在阶段 B 数据覆盖和准入门通过后才重训 development bundle。旧 v5 bundle 绑定阶段 A
  之前的实现 SHA256，严格加载应失败关闭，不得沿用旧权重解释新规则候选。

## 2026-07-21 共享 canonical seed 视图

- [x] 为 tracklet graph 与 active-vision episode 分别实现 strict、detached、只读的 canonical
  split view；复用原 strict loader，不改原 manifest，不复制或重写在线/离线样本。
- [x] 独立复算 training/shared registry 的 file/content/assignment SHA256、D3-compatible 数值 seed
  策略和 `60/20/20` 分桶；缺失、多余、重复、错桶、schema/policy 变化及 seed `1000-1019` 均失败关闭。
- [x] 冻结 source manifest/content、registry、consumer/source schema、canonical split/training-set
  hash 和 episode/sample/edge 计数，并生成两类 tracked detached manifest 与中文 readiness 报告。
- [x] 图 readiness、图开发训练/评估和主动视觉 BC 增加显式 canonical 参数；三个路径参数必须成组
  提供。默认不带参数时继续使用原 split，避免静默改变既有开发模型语义。
- [x] 正式图视图为 seed `60/20/20`、episode `7715/2574/2562`、edge `281/116/83`；正式主动视觉
  视图为 seed `60/20/20`、episode `540/180/180`、sample `695705/229651/227886`。保留 seed 泄漏为 0。
- [x] 验证原数据树前后内容哈希不变；2026-07-21 新增 15 项 canonical 专项，D5 全量
  `429 passed`。未运行耗时完整模型训练。
- [ ] graph producer 继续补 edge-bearing frame、真实困难负边和完整 candidate-recall 分母；canonical
  对齐不改变 `12532/12851` 无边事实，G1/assist 保持失败关闭。
- [ ] active-vision producer 补 hold/observe/recon、applied-action runtime ACK、独立 reward/
  counterfactual/causal label 与 paired shadow。旧 v5 bundle 不因重分桶自动晋级或改绑。
- [ ] main 更新 VERSIONING，登记 view schema、两类正式 view/hash 和 D4/D5 split 视图已对齐；D5
  owner 不修改 main-owned 文件。

## 2026-07-20 主动视觉行为克隆准入

- [x] 对正式 900-episode、1,153,242-sample 数据执行严格 loader、逐制品 SHA256、schema、整 seed
  原子分割和保留 seed 隔离检查；train/validation/test 唯一 seed 为 `60/20/20`，交集为 0。
- [x] 运行可复现容量探针并采用流式特征缓存。候选动作数为 4-7，完整缓存含
  `4,669,959/1,625,596/1,565,555` 条 train/validation/test 候选行，未把全数据驻留内存。
- [x] 固定 seed `20260720` 在完整 train split 上运行 5-epoch 行为克隆；每 epoch 使用 685,005
  样本，总样本呈现次数 3,425,025，未抽样冒充正式训练。
- [x] 输出总体、逐意图、逐相机类型、逐规模指标和 CPU P50/P95/P99。test 精确动作准确率
  `0.955978`，但 `observe_target` 召回/F1 为 0、`hold` 无正样本、recon 精确动作仅 `0.621823`。
- [x] 完成只读温度校准审计。`T=0.906731` 只轻微降低 test NLL，ECE 反而增加，因此不写回 bundle。
- [x] 生成 v5 development bundle，绑定 dataset/split/training/config/code/weight SHA256；shadow 可
  加载，assist 必须以 `bundle_assist_not_admitted` 拒绝，PPO=false，规则回退必需，相机命令权=false。
- [x] 权重与完整 bundle 只保存到 ignored `outputs/`；tracked results 只保存命令、配置、指标、哈希
  和本地定位。2026-07-20 D5 全量 `414 passed`。
- [ ] producer 以独立场景和 seed 补充 hold、observe_target、recon、不同 FOV 及动作边界示范，避免
  `reacquire` 占比 92.16% 造成多数类假高分。
- [ ] 在 shadow 模式真实产生 requested action，记录 runtime ACK、执行后 outcome、时延和规则回退，
  建立动作归因。无动作归因的相邻观测不得作为 reward。
- [ ] 至少 20 个完全未见 seed 完成 paired shadow 非退化评估后，再讨论 assist；在此之前保持
  `development_shadow_only`。PPO 需独立 reward/counterfactual/causal label，本阶段不启动。
- [x] 2026-07-21 通过共享 canonical seed 只读视图关闭 D4/D5 split 身份不一致。联合模型仍因标签、
  准入和运行合同未满足而关闭；main 在 VERSIONING 中登记 active-vision bundle v5、view schema
  及无 git-lfs 时权重仅位于 ignored outputs 的规则。

## 2026-07-20 正式跨视角图数据准入与补数

- [x] 对 `learning_generation_v1_multibatchfix` 的 12851 个 D5 图帧执行只读严格加载；逐文件验证
  graph/label SHA256、schema、feature version/order、split hash、training-set hash 和 class balance。
- [x] 复核整 seed 分割：train/validation/test 唯一 seed 为 `60/20/20`，交集为 0；保留评估 seed
  `1000-1019` 未进入训练。
- [x] 冻结训练准入门：各分割 edge-free 比例 `<=0.90`；训练正/负边至少 `100/100`，验证和测试
  正/负边至少 `50/30`；candidate recall 标签可用率为 1.0 且每分割 pair 分母至少 100；至少
  80% 场景规模 cell 同时具备正负边；测试至少 20 个唯一 seed。
- [x] 审计结果失败关闭：总 edge-free 为 `12532/12851 (97.52%)`，仅 319 帧有边；三分割边为
  `286/99/95`，负边为 `11/4/4`；partial candidate recall 分母只有 `4/1/1`。15 个数据门失败。
- [x] 新增显式 `development-only` 训练路径。正式训练对不完整验证真值仍失败关闭；开发模式只使用
  已标注 candidate edge，误合并率和 candidate recall 保持 unavailable，不允许用零代替。
- [x] 将图模型 bundle 升为 v3，绑定 readiness audit、数据/split/training/config、节点/边特征和
  实现代码 SHA256；开发 bundle 固定 `default_model=false`、`g1_assist_eligible=false`。
- [x] 固定 seed `20260720` 完成 40 epoch 开发训练：最佳 epoch 38，权重 SHA256
  `9bbe53d6...35cbf2d`；验证/测试 F1 为 `0.9804/1.0`，但各只有 4 条负边，promotion 继续
  `fail_closed`。两次固定 seed 运行权重哈希一致。
- [x] 权重和完整 bundle 只保存到 ignored 的 D5 `outputs/`；`results/` 仅保存命令、配置、指标、
  哈希和本地定位，不复制权重。
- [x] 2026-07-20 验证：图训练专项 `16 passed`，D5 全量 `412 passed`，语法检查通过。
- [ ] main 更新 `research_modules/scalable_3d_simulation/VERSIONING.md`：登记 D5 tracklet bundle v3，
  并明确无 git-lfs 时开发权重不进入普通 Git。本 D5 owner 不修改 main-owned 文件。
- [ ] producer 增加新独立 seed 的相机重叠、密集交叉、遮挡进出、时延重捕获、有界外参扰动和
  epipolar/投影上可混淆的异目标；不得通过复制样本或降低在线安全门补足负边。
- [ ] 补齐评价帧全部 camera-local tracklet 的离线标签及候选裁剪前同目标跨相机 pair 总表，使
  candidate recall 在 validation/test 上具备可审计分母。补数后重新生成新版本数据集并重跑审计。

## 2026-07-20 同相机多批次阻塞修复与正式数据复跑

- [x] 核对正式失败语义：`learning_generation_v1_oosmfix` 已保存 209 条完成记录
  （sequence 0-208），下一项 `communication_degraded` 200v200 因同一次 D5 调用包含同相机多个
  已到达批次而失败。该输入是通信队列积压后的合法排空，不是相机串流或规模配置错误。
- [x] 将 `adapt_batches()` 改为两阶段事务。全部 batch 先完成 truth-free、有限性、来源唯一性和
  per-stream 暂存高水位预检，再按 arrival、resource、camera、measurement 规范顺序提交；任一
  duplicate arrival、已提交 arrival rollback 或 duplicate measurement 均不允许产生部分状态更新。
- [x] 保持既有 OOSM 语义：合法迟到 measurement 保留原双时间戳和几何，只增加 OOSM 计数并推进
  arrival 高水位，不更新或老化 tracker，不生成局部轨迹。
- [x] `process()` 的 `camera_batches` 保留全部到达批次；关联图和 source-observation link 只取每个
  camera stream 最后一次有效状态更新，防止稳定 local track key 的历史版本重复进入一个图快照。
- [x] 对每流登记全部已接收 measurement 时间戳，较早正常帧和已忽略 OOSM 的重传也判为 duplicate；
  登记仅用于去重，不改变运动状态、身份或中心绑定。
- [x] 新增同流两正常批次、同流正常/OOSM 混合、历史 measurement 重传、duplicate arrival/
  rollback/measurement 原子拒绝、多相机多批次确定性与不串流回归。2026-07-20 定向
  `31 passed`、D5 全量 `410 passed in 11.68s`，语法和 `git diff --check` 通过。
- [ ] main 按 `VERSIONING.md` 在同时包含 D5 与 runner 修复的新干净提交上，使用新输出目录从
  sequence 0 开始重建正式 900 episode，并完成 900 条进度、45 cell × 20 seed、finite、clean、
  online truth use=0、checkpoint 和数据最终化审计。绑定 `c5a9f6d` 的旧 209 条目录只保留为故障
  证据，不得恢复、续写或与新数据集拼接。

## 2026-07-20 通信退化 OOSM 修复与正式 resume

- [x] 定位 sequence 29 失败：main 已按 arrival 顺序交付，D5 camera-local tracker 错把 measurement
  时间作为流接收顺序，并在更新时覆盖当前状态时间。
- [x] 按 camera stream 分离 arrival 高水位和 measurement 高水位。合法 OOSM 保留双时间戳并以
  `oosm_ignored` 接收，但不回退、创建、老化或更新 tracker 状态；累计计数随批次 metadata 输出。
- [x] 对 arrival 回退、重复 arrival 和同 measurement 重传在状态变化前失败关闭；不按 measurement
  重排接收语义、不改写时间戳、不使用 truth ID、不创建或改写 `global_track_id`。同一次调用的多个
  已到达批次现按 arrival 主键规范排序，具体见上节。
- [x] 新增 arrival 单调/measurement 乱序正例，以及 arrival 回退、原样重复和同 measurement 重传
  负例。2026-07-20 定向 `24 passed`、D5 全量 `403 passed in 9.74s`，零失败。
- [x] 原 `learning_generation_v1` 保留为旧 revision 失败证据。main 在修复提交的新目录
  `learning_generation_v1_oosmfix` 完成首个 45-episode 分块，原 sequence 29 对应 OOSM cell 已通过。
- [x] main 在同一 clean revision 上完成 checkpoint resume；新目录累计 209 条完成进度
  （sequence 0-208），未把旧版输出混入该正式集。随后阻塞属于同相机多批次，见上节。
- [ ] 正式分块结束后统计 `oosm_measurement_ignored_count`。若 OOSM 占比或信息损失不可接受，再单独
  设计有界固定时滞历史与确定性重放；当前不以未验证回放替代保守失败关闭路径。

## 2026-07-20 200v200 clean-tree 复测与下一热点

- [x] main 在提交 `4052d9411363c39d52100c0e3a4f60ee88443cab` 上完成 nominal 200v200、
  2 s、seed 930-932 clean-tree 复测；三场 `repository_dirty=false`、online truth use 为 0。
- [x] 确认重复 finalization 审计热点关闭：总 finalization 由 `116.5624 s` 降至 `7.7377 s`；
  D5 graph staging 为 `0.0250/0.0259/0.0290 s`，且 graph dataset 正常最终化。
- [x] 确认端到端收益与边界：artifact staging `225.9243→126.4682 s`，总生成
  `467.8007→262.2866 s`；episode run `125.2205→127.9871 s`，不宣称在线仿真加速。
- [x] 完成 D5-owned active-vision sample/writer 性能修复。剖析确认 gzip level 6 只占少量时间，
  主因是共享 snapshot 被每个 camera sample 重复执行中心引用与递归 truth-free 审计，以及 writer
  重复规范化对象。200-camera/400-track fixture 构造 `2.3597→0.1097 s`、materialized load
  `2.3948→0.1802 s`；既有 3,536-sample 制品 writer `3.5529→0.7313 s`。gzip/解压字节和 SHA256
  修改前后完全相同，采样、特征、在线/离线分流、版本/ACK、只读和失败关闭合同保持。
- [x] main 在提交 `45b36500dc3c6935b1f116614993e291041eb12d` 上完成同一 nominal 200v200、
  2 s、seed 930-932 的 clean-tree postopt2 复跑。三场均 finite、`repository_dirty=false`、online
  truth use=0，D5 graph 正常最终化；active-vision staging 从历史
  `41.5623/43.2639/41.2271 s` 降至 `4.0494/3.9898/3.9995 s`。总 staging
  `126.4682→12.4372 s`，总生成 `262.2866→144.5513 s`。该系统级证据关闭 D5 writer P1，
  但不构成在线实时性或模型准入结论。
- [ ] 生成并最终化正式 900-episode corpus，随后运行正式 BC/PPO、checkpoint 制品、paired shadow
  与 assist 准入。当前仅 3 个 seed，因不足 20 个未见测试 seed 返回
  `insufficient_unseen_test_seeds`，该失败关闭状态符合合同但不构成训练准入。

## 2026-07-20 200v200 主动视觉容量与跨视角 seed 隔离

- [x] 将 active-vision online record 升为 record/sample v2：确定性 `.online.jsonl.gz` 按 SHA256 key
  去重 snapshot/camera feedback，sample 只保存稳定引用；全部动作、版本、反馈和 ACK 字段保留。
  `ActiveVisionEpisodeRecordV2/SampleV2` 为正式名称，V1 Python 名称仅是源码兼容别名。
- [x] 新增 `stage_active_vision_episode_record()` 与 `stage_active_vision_offline_labels()`：在线
  `online/*.online.jsonl.gz` 逐行拒绝 truth/actor/object identity，evaluator reward/outcome/
  counterfactual/causal label 只存在于物理独立 `offline/*.offline.json`，并在 episode 结束后按
  `sample_key + observation_key` 精确连接。
- [x] offline staging 改为 SHA+逐行 contract audit，只保留一个当前 snapshot 和紧凑 key/index；
  不调用完整 record loader。非物化 sample 使用合同摘要校验，不再重复遍历共享 snapshot；episode UID、
  source identity、对象哈希/引用、动作/版本/反馈/ACK 和 sample join 仍完整校验，online 字节篡改以
  `online_sha_mismatch` 失败关闭。
- [x] finalize 的 staged audit 改为逐 episode `materialize=False`，不调用兼容全量 dataset loader，
  不跨 episode 累积 record/sample；同一次 finalization 的最终结构复核复用仍匹配文件指纹的 stream/
  SHA 证据，避免二次解压、反序列化和哈希。公共 lazy/audit API 不接受内部证据，仍从磁盘独立完整
  复核。公共 lazy handle 提供逐 split 的 episode、BC 和 PPO iterator。
  BC 只物化当前 online 规则示范，PPO 只物化当前 episode 并逐项核验离线 reward availability。
- [x] reward 固定 `[-1,1]` 并带 availability/provenance；无 outcome 时 reward 为 unavailable/null，
  无 outcome+counterfactual 时 causal label 为 unavailable/null，禁止用 `0` 伪装缺失值。
- [x] finalize/loader 保持完整 `(scenario_version, seed)` group，并把共享同一数值 seed 的所有
  scenario/scale group 原子分到同一 split；数量按唯一 seed 计算。少于三个唯一 seed、少于声明
  unseen seed、group/seed 跨 split、未知中心 ID、局部换绑、版本回退、SHA/schema/source identity/
  offline join 错误均失败关闭；正式默认 minimum unseen seed 为 20。
- [x] manifest 固化 schema/version、dataset config、逐文件/split/training-set SHA256、source Git
  commit/dirty 与 source config SHA、availability 和共享 seed 原子策略；`SHA256SUMS` 精确覆盖目录，
  finalize 后文件只读。
- [x] loader 输出不可变对象；BC 视图只取规则示范且不加载 evaluator label，PPO 视图只取 effective
  action 并要求每个样本 reward available。`ActiveVisionTransition.reward=None` 是唯一缺失表达。
- [x] active learning dataset 保持 v2；episode dataset 升 v3、descriptor/record/sample 升 v2、主动
  视觉 bundle 升 v4。旧 v1 嵌套 record 返回稳定 unsupported-schema，snapshot/action/feedback/
  ACK/offline-label 保持 v1；没有正式 admission report 时仍不能 assist。
- [x] 复核并修复 tracklet split：共享数值 seed 的跨 scenario/scale group 原子分配，test seed 对
  train/validation 完全未见；tracklet dataset/bundle 均升 v2，少于三个唯一 seed 失败关闭。
- [x] D5 最终复核：相对 dataset root 可完成 staging/finalize/load；非 assist mode 只能落盘规则
  effective action；resource/camera/local tracklet ID 全部拒绝 truth/actor/object-like 命名。
- [x] 2026-07-20：16→64 camera fixture 的旧嵌套字节 `302709→4336869`，v2 去重解压
  `59617→234721`，gzip `3995→13084`；200-camera/400-track 单 snapshot 为
  `731412/37004` 字节（解压/gzip）。12 episode × 48 camera × 96 track 回归共 `576` samples，
  finalize/audit 的完整 record/dataset loader 调用为 0。
- [x] 2026-07-20 开销收敛：6 episode × 48 camera × 96 track 的确定性计数中，finalize stream/offline
  parse 从 `12/12` 降至 `6/6`，SHA256 从 `67` 降至 `20`，20 个制品各哈希一次；独立 public audit
  仍另做 `6/6` 次 parse 和每制品一次哈希。200-camera/400-track 合成 stream audit 辅助墙钟约
  `9.81→0.37 s`；已有 nominal/dense 200v200 文件独立 audit 约 `2.08/2.21 s`。墙钟不是硬门。
  数据管线 `18 passed`、D5 全量 `400 passed in 9.74s`，接受阈值为零失败。
- [x] main 容量复测：nominal seed 91、每档 2 s 的 5/20/50/100/200v200 总制品约
  `0.086/0.295/0.733/1.543/2.884 MB`；200v200 online/offline 为 `1.064/1.818 MB`、`3536`
  samples、RSS 约 `1.04 GB`、online truth=0。该结果关闭单 episode 去重容量门。
- [ ] 正式 corpus 验收：使用真实 source Git/config identity 与独立 evaluator label 生成约
  900 episode 数据集，实测 finalize/lazy 训练的峰值 RSS、吞吐和故障恢复。本轮没有修改
  main/scalable runtime，也没有完成该 corpus 级压力验收。
- [ ] 正式数据与准入：收集代表性 train/validation/test、至少 20 个完全未见 seed、真实 outcome/
  counterfactual、困难场景和 paired shadow；完成正式 BC/PPO、冻结指标门与 checkpoint 审批。

本轮已关闭 D5 软件/容量合同、split 泄漏和 writer 的三 seed clean-tree 系统级复跑项，不关闭
nominal 200v200 正式 corpus/训练验收。postopt2 是 3 个 2 s episode 的离线制品计时，不是正式
训练、20-seed 实验、AirSim 运行、可见率/重捕获收益、在线实时性或 assist 准入。模块内
`docs/MODULE_PRINCIPLES_CN.md`、
`docs/ALGORITHM_AND_IMPLEMENTATION.md`、`docs/AIRSIM_INTEGRATION_PLAN.md` 和
`docs/EXPERIMENT_REPORT.md` 已按相同边界同步。

## 2026-07-20 主动视觉学习研究路径与 source observation 审计

- [x] 定义 `d5.active-vision-snapshot.v1` / `d5.active-vision-action.v1`；输入只含中心航迹和
  AssignmentPlan 只读引用、相机/云台/FOV、投影不确定度、可见/遮挡、通信和版本信息，递归
  拒绝 truth/actor/object identity。
- [x] 动作限制为 observe/search/hold/reacquire、有限 yaw/pitch 增量和 wide/zoom；无飞行控制、
  D3 分配、处置或授权字段，目标 ID 只能引用当前候选与相机分配交集。
- [x] 实现确定性 look-at/reacquire/scan 基线及统一 safety projection，覆盖 plan/coalition/
  communication version、候选成员、证据 age、FOV、机械角/当前与请求速率、slew、友方冲突、
  timeout、低置信、OOD、非有限输出和 bundle SHA/schema 错误。
- [x] 实现 library `disabled` 默认、CLI `shadow` 默认和 `disabled/shadow/assist` 决策输出；输出
  包含 requested/effective mode、fallback、latency、fingerprint 和三个版本。shadow 不改变规则动作。
- [x] 实现完整 `(scenario_version, seed)` group split，并把共享数值 seed 的跨场景 group 原子
  分配；提供原生 PyTorch behavior cloning 和 clipped PPO，学习模型只对有限安全动作候选评分，
  不增加 `torch_geometric` 依赖。
- [x] 实现主动视觉 manifest/state_dict/SHA256 bundle 与 `weights_only=True` 严格加载；paired
  shadow report 绑定模型、dataset manifest、split 和 training-set SHA。
- [x] assist 门固定为至少 20 个完全未见 seed、正式非合成证据，以及逐 episode/总体 safety、
  visibility、reacquisition delay 非退化；20-seed 合成 fixture 正例明确拒绝正式准入。
- [x] scalable adapter 只读传播 `source_observation_id`，同帧一 observation 对一 tracklet；新增
  evaluator-only observation label join，缺失假目标标签时 `labels_complete=false`。该键不参与
  tracker、图特征、tracklet/global ID 或 binding。
- [x] 2026-07-20：主动视觉专项 `17 passed`，D5 全量 `376 passed in 9.94s`；BC/PPO 为 8 个
  合成 seed 的 1-epoch smoke，checkpoint/bundle 只在 `tmp_path` 生成。
- [x] main 已将 snapshot 接到统一三维 episode 的 recon/interceptor 模拟相机状态和调度；输入
  包含实际 yaw/pitch/FOV、最近接受版本、D2 中心航迹、D3 计划和 D5 几何证据。规则动作经
  plan/coalition/communication version、有效期和资源一致性复核后在下一视觉帧应用，并发布
  `runtime.camera_command_ack`。5v5 开发冒烟为 `84/84` applied，200v200 seed 17、1.2 s 为
  `1872/1872` applied；两者仅是单 seed、脏工作树接口证据。
- [ ] 收集代表性 train/validation/test 和至少 20 个完全未见 seed 的正式 paired shadow 结果；
  当前无正式 checkpoint、无 assist 准入，不得把单测 fixture 写成性能或晋级证据。
- [ ] 在真实 AirSim 云台和后续实机上验证命令/ACK、机械速率、时延、reset 和失败回退；当前
  模拟相机接线不得写成真实执行或主动视觉因果收益。

`docs/AIRSIM_INTEGRATION_PLAN.md` 已同步“统一三维模拟接线已完成、真实 AirSim/实机仍待接入”
的边界；`docs/EXPERIMENT_REPORT.md` 已同步代码级 smoke 和“不构成正式准入”的口径。本阶段
没有新增 AirSim episode、settings、detector、相机外参来源或真实云台/FOV/ACK 证据。

## 2026-07-20 版本化数据、训练、校准与制品管线

- [x] 新增 `tracklet_dataset.py`：在线匿名图和 evaluator label 分文件写入；图归档不保存
  `truth_entity_id`/`shared_global_track_ids`，标签只在独立 evaluator JSON 中出现。
- [x] 固化 dataset/graph/label schema、节点/边 feature version 与精确顺序、generation config
  SHA256、class balance、candidate-recall availability、hard-negative provenance、split hash 和
  training-set hash；加载时以 `allow_pickle=False` 校验 SHA、shape、有限值、版本和 feature order。
- [x] 切分固定以 `(scenario_version, seed)` 为 group，完整 episode 随 group 进入
  train/validation/test；禁止 edge-level random split，同 seed 跨 split 直接失败关闭。
- [x] 新增多图梯度累积训练：固定 Python/NumPy/PyTorch seed，按 geometry gate score 选择
  hard negative，BCE `pos_weight` 处理类别不平衡；validation 独占模型选择、temperature
  calibration 和 F1 threshold selection，test 不参与调参。
- [x] test 输出 precision/recall/F1、constrained-cluster false-merge rate、candidate recall、
  Brier/ECE、P50/P95 inference latency 和 model size；完整真值不足时相应指标明确
  `unavailable/value=null`，不得补零。
- [x] 新增 `manifest.json + weights.pt + SHA256SUMS` bundle；manifest 固化模型语义版本、
  graph/node/edge feature 版本与顺序、hidden dim、message steps、训练数据/split hash、
  validation-only temperature/threshold 和验证结果。加载只允许 `torch.load(weights_only=True)`。
- [x] 在线 bundle scorer 仍只输出 candidate-edge same-target probability。bundle 缺失/损坏、
  SHA/schema/feature/version/state mismatch、非有限或越界输出、超时、低 certainty、无效阈值均
  回退现有 deterministic geometry rule；受约束聚类、同相机唯一、中心投影/Hungarian 和
  `global_track_id` 所有权不变。
- [x] 2026-07-20 验证：新管线 `12 passed`，稀疏图/adapter/新管线组合 `46 passed`，D5 全量
  `355 passed in 9.48s`；checkpoint 只在 `tmp_path` 生成，没有提交正式 checkpoint。
- [ ] P1 数据与准入仍开放：按本合同收集代表性 train/validation/test，test 至少包含
  20 个未见 seed，并覆盖近邻交叉、遮挡、时延和外参漂移；冻结门限后才能形成候选准入报告。
- [ ] 默认 checkpoint 仍开放：本轮只关闭训练/制品代码管线，不授予默认模型资格，不改变
  几何规则默认路径。

该阶段未改变 AirSim runtime；本轮新增主动视觉/source-observation 合同后，
`docs/AIRSIM_INTEGRATION_PLAN.md` 已在文首同步下一轮接线边界，仍未新增 AirSim 运行证据。

## 2026-07-20 匿名稀疏 tracklet 图与主动视觉接口

- [x] 新增严格匿名 `CameraLocalTracklet`：节点仅使用 camera-local namespace、双时间戳、
  bbox/中心、像素协方差、角速度、尺度变化和置信度；metadata 与本地 ID 中的
  truth/actor/object/global identity 失败关闭；构造器和递归 payload guard 另拒绝
  `TGT-0001`、`TargetDrone_1`、`Target_UAV_7`、`intruder-003` 等 truth-like local ID，
  并保留 `cam01-track-0001` 等正常 camera-local sequence。
- [x] 新增 `scalable_3d_adapter.py` duck-typed 在线入口：直接消费真实
  `OnlineSensorBatch`/`vision_bbox` 字段形状，不导入 main/D2/evaluator 类型；在 tracker 更新前
  拒绝 truth/actor/object/target/entity 字段和 truth-like 字符串，local ID 仅由 per-camera
  tracker 产生；`observation_id` 只读传播为审计键，不用于身份、匹配或 binding。
- [x] 按 `(resource_id,camera_id)` 隔离 IoU/中心门 tracker，输出双时间戳、中心/bbox 协方差、
  角速度和 bbox 尺度变化；支持有限漏检、空扫描、stream/episode reset。相机 metadata 生成
  `K/R/t` 及外参协方差；缺失独立 pose covariance 时只允许显式 configured fallback 并标源。
- [x] 六维 D2 center track 只读转换为现有 D5 `GlobalTrack` 投影假设；在线封装完成
  构图、确定性规则/注入模型边概率、同相机互斥聚类和中心 Hungarian binding。模型缺失、
  异常或低 certainty 有明确 fallback 状态，D5 不加载默认 checkpoint、不创建/改写中心 ID。
- [x] 新增时序、视场、极线、射线交会、重投影、像素马氏、中心 GlobalTrack 投影和
  外参/航迹协方差逐级门控；按 `max_neighbors_per_node` 确定性截断，避免构造全连接图。
- [x] 在几何门前增加相机 overlap/index：由位姿、截断视锥 AABB、量测时间窗和三维覆盖桶
  生成相机对；用 `camera_pair_budget` 限制实际检查数。预算后同桶间隔轮转和跨桶对角线轮转
  保持确定性和相机覆盖，未检查对保持 unbound。
- [x] 增加 `max_tracklet_candidate_edges_per_node`，优先按中心投影支持/时间近邻构造有界
  tracklet 候选，再执行极线、射线和重投影；不再构造每相机对 `n_left x n_right` 矩阵。
- [x] 边特征覆盖时间差、像素马氏距离、重投影误差、射线最近距离、bbox 尺度/变化、
  角速度、基线、外参协方差，并补充极线误差、交会角和中心投影支持。
- [x] 使用原生 PyTorch 实现 `NativeTrackletEdgeClassifier`，通过 `index_add_` 聚合消息；
  forward 只输出同目标边概率，不引入或依赖 `torch_geometric`。
- [x] 独立 `OfflineTrackletTruthLabel` 仅在在线图完成后构造训练标签；困难负样本按几何
  gate score 选择，BCE 使用正类权重处理不平衡。
- [x] 最终决策保持分层：受约束聚类保证每相机每簇最多一个 tracklet，中心 Hungarian
  binding 只能引用输入 `GlobalTrack.global_track_id`，运行时检查输出 ID 是输入集合子集。
- [x] 主动视觉动作域限制为观察目标、搜索扇区、云台增量、FOV/变焦；超时、低置信和
  无效中心 binding 回退确定性规则扫描。接口不包含飞行、分配、处置或授权动作。
- [x] 2026-07-20 seed 200 压力回归：200 目标、4 相机、800 节点，240000 可能跨相机对
  经两级索引形成 3050 个 tracklet 候选、2953 个最终 cap 前候选和 1923 条最终边，密度
  `0.006017`、最大度 6，本次 `0.442 s`；接受门为密度 `<0.01`、最大度 `<=6`、运行 `<15 s`。
- [x] seed 4 小样本 smoke：8 目标、3 相机、24 节点/192 边，24 正样本与 72 困难负样本，
  60 epoch loss `1.038521 -> 0.011535`、训练集准确率 1.0。
- [x] adapter 专项保持通过，训练/制品同步后 D5 全量 `355 passed in 9.48s`；覆盖 2/3/4 相机
  部分可见、跨帧 ID、假目标/漏检、7 类真值污染、中心 ID 不变、reset、空扫描与模型回退。
- [x] 5/20/50/100/200 相机结构矩阵：每相机 1 个匿名 tracklet、相机对预算 `2C`；200 相机
  的 19900 个总对只检查/保留 400，对预算丢弃 19500，tracklet 候选为 397，全部相机至少进入
  一个候选对。测试只约束结构上界，不使用易抖动的窄绝对时延阈值。
- [ ] P1：main scalable module stack 已调用 D5 adapter；main 需把新增扁平诊断
  `association.diagnostics` 持久化到 episode/D6，并在真实 scalable 3D 多 seed 下报告相机对预算
  命中率、漏配率、内存峰值和 P50/P95。camera pose covariance 仍应显式放入在线 metadata，
  evaluator truth 流继续物理分离。
- [ ] P1 数据/准入：独立整 episode 切分、困难负样本、校准、阈值和指标的软件管线已完成；
  仍需真实代表性数据、至少 20 个未见 seed、近邻交叉与遮挡/漂移场景及 CPU/GPU 时延预算。
  当前没有默认 checkpoint，不替换既有几何 Hungarian 主线。
- [x] main-owned scalable runtime 已接入模拟相机/FOV 命令、版本门控、下一帧应用和 ACK/timeout
  记录；规则 fallback 保持默认。
- [ ] P2：接入真实 AirSim 云台和实机执行反馈；BC/PPO 软件流程已有合成 smoke，但学习型主动
  视觉策略尚未用正式数据训练、验证或验收。

## 2026-07-16 ComputerVision 5+1 独立专项状态

- [x] 完成 5 个 `1920x1080`/60 度局部相机、1 个 `3840x2160`/75 度侦察相机、
  5 个 `Quadrotor1` actor 的真实 AirSim 运行；样本为 12 秒、49 帧、seed 7。
- [x] AirSim detect 与 YOLOv8 + 原生 ByteTrack 两路均按每个相机 batch 的
  `measurement_timestamp` 投影，并保持 online truth use=0、
  `global_track_id` rewrite=0。
- [x] detect 几何基线达到召回/配准/稳定/联合覆盖/侦察全覆盖/IDSW =
  `1.000/1.000/0.975/1.000/0.918/0`，通过全部专项门限。
- [x] 记录 YOLO+ByteTrack 的 `0.622/0.996（严格 0.966）/0.955/1.000/0.878/25`，
  P50/P95 约 `10.42/12.37 ms`；召回、侦察全覆盖和 IDSW 未过门限，保持 optional。
- [ ] 提升 YOLO 召回、降低 ByteTrack IDSW、恢复侦察全覆盖，并完成多 seed
  confirmation；单 seed 不允许作为默认主线晋级依据。

本专项门限为 detect/YOLO 召回分别 `>=0.95/>=0.90`、严格配准 `>=0.95`、
稳定配准 `>=0.90`、联合覆盖 `>=0.95`、侦察全覆盖 `>=0.90`、IDSW 分别
`<=0/<=5`，且 truth use/rewrite 均为 `0`。专项分支不替换默认 D1-D7 流程；
本轮只同步真实证据，不修改 D5 算法、默认 backend 或安全阈值。

本隔离专项未运行 D1/D2。main 使用 actor truth 运动学合成带中心
`global_track_id` 的 `GlobalTrack` fixture，truth 同时用于离线评分。
`online_truth_identity_use=0` 的边界仅覆盖 D5 的 local bbox 到 fixture
关联代价、Hungarian 选择和稳定窗口不读取 actor/object/truth identity；它不表示
整个专项完全不读取 truth。

## 2026-07-16 人工轨迹局部观测适配器（已完成）

- [x] 在离线 `manual_video_tracker` 子模块公开
  `manual_records_to_local_image_observations()`，参数固定包含 `sensor_id`、
  `stream_id`、`image_size`、`spectral_band="visible"`、`local_epoch=0`、
  `arrival_delay_s=0.0`、`confidence=1.0`。
- [x] measured 将 `xywh` 转为 `xyxy`，复用
  `adaptive_pixel_covariance_px()` 生成 `2x2` 像素协方差，保留双时间戳、
  camera-local ID、frame index、tracker/association backend 和逐 local ID
  连续 measured history；lost 不携带 stale center/bbox/covariance，confidence 固定为 0。
- [x] 转换前运行整批 identity audit；`duplicate_measurement_count > 0` 时拒绝转换，
  不输出部分结果。
- [x] 从包根移除 `manual_video_tracker` 强制导入；CLI/测试使用显式子模块导入，
  根包在 manual OpenCV/SciPy 依赖不可用时仍可导入。
- [x] 2026-07-16 复核既有 95 帧、5 local ID、475 条记录，转换结果为
  `470 measured / 5 lost`、重复量测 0。D5 全量 `288 passed`，接受阈值为零失败、
  lost 无 stale 量测且重复坍缩必须 fail closed。
- [ ] 保持该能力为人工初始化单相机离线支线；不接入默认 AirSim，不将 local ID
  提升为 `global_track_id`，不据此关闭通用 detector/MOT、多视角或物理闭环 GAP。

`docs/AIRSIM_INTEGRATION_PLAN.md` 已检查：本任务没有 AirSim 输入、runtime episode、
默认 detector 或 handoff 接线变化，因此不修改该文件。

## 2026-07-15 人工初始化本地视频 MOT（已完成）

- [x] 新增首帧 `selectROIs` 和无界面 `--rois`，目标数量由输入决定，选择顺序固定为 `local-001...`。
- [x] 新增每目标独立 CSRT 默认路径和 KCF 可选路径；重复 tracker 框失败关闭，不把同一量测写给多个 ID。
- [x] 新增亮目标正对比峰 + 常速度预测 + Hungarian 一对一关联选项，用于 `b.mp4` 中五个相邻亮目标。
- [x] 输出 MP4、逐帧 CSV、JSON summary；lost 帧的 bbox/center 为 null/空，不沿用旧框伪造量测。
- [x] 2026-07-15 无界面运行 `b.mp4` 95 帧：五 ID 有效/丢失为 `92/3`、`95/0`、`93/2`、`95/0`、`95/0`；`duplicate_measurement_count=0`，最小中心间距 `5 px`，最大 bbox IoU `0.4118`。
- [x] 单元测试覆盖 ROI 解析/边界、ID 稳定、lost 语义、合成 MP4 和一对一亮点关联。
- [x] 2026-07-15 验证：D5 全量 `284 passed`，`py_compile` 和 owned-path `git diff --check` 通过，接受阈值为零失败。
- [ ] 后续仅在独立 benchmark 中增加人工重选事件日志、外观模板或通用检测器比较；不得把本工具的 local ID 直接注册为 GlobalTrack。

本工具是离线人工初始化 local MOT，不是敌我识别、GlobalTrack 注册、跨相机关联、D7 视觉 PNG 授权或 ByteTrack/BoT-SORT 准入证据。它不改变 AirSim detect-first 默认路径，因此 `docs/AIRSIM_INTEGRATION_PLAN.md` 已检查但无需修改。

## 2026-07-15 M5N2 20-case 复核与停止状态

- [x] 只读复核 baseline seed 001-010 与 `candidate_soft_prediction_trend_coast` seed 001-010；共 20 个真实 AirSim M5N2 case。TERM 生效前额外完成 `png_ttc_2v2_seed001`，但不进入 M5N2 统计；其余 tuned case 与 dropout case 均未执行。
- [x] 每场从最终 active-primary 合同动态确定第二 primary；19 场为 `INT-03`，candidate seed 002 为 `INT-02`，避免把 standby reserve 错计为第二 primary。
- [x] 确认 `3725/3725` 个 D5-available tick 具备第二 primary runtime record、decision state 和 live first-failure stage/reason；D5 warmup not-applicable 为 `80` tick。实际 execution artifact 为 `20/20` available，online identity/state truth use 为 `0/0`。
- [x] 输出实测漏斗：`locked/ambiguous/reacquire/hold=1721/795/1209/0`；bbox-stability/live-detection/visual-association/geometry/complete 为 `1283/1209/764/204/52`；measured bbox `2516`、bbox stable 与 handoff-ready 各 `161`。
- [x] 保留物理结果独立分母：第二 primary 5 m 为 `0/20`，最近物理距离 `8.843-14.740 m`；T001 coalition completion `0/20`。snapshot locked 或短时 consensus 不替代物理闭环。
- [x] 保留停控原因责任边界：20 个第二 primary 最终均记录为 `collision_stop`，但这只是 D7 停控证据；碰撞对象未持久化，不能把该状态或 `0/20` 单独归因于 D5。
- [ ] P1：由 main/D6 在后续报告接线中直接持久化 `failure_category` envelope。本批只有 `first_failure_stage/reason` available，不能声称真实分类字段已经验收。
- [ ] P1：继续校准第二 primary 当前 measured bbox 连续性、bbox 尺度、visual freshness、候选唯一性和几何搜索恢复；目标仍是提升 5 m 结果且不放宽 global-ID、friend、duplicate、版本和时间门控。
- [ ] P1：candidate 仅有 handoff-ready snapshot 比例上升，locked/freshness/consensus 与物理结果未一致改善；默认路径维持不变。candidate seed 002 发生 primary membership 变化，后续公平对照应冻结或显式分层成员合同。

本轮没有代码修改、没有运行 AirSim，也不把 truth ID 作为在线输入。

## 2026-07-15 第二 primary 被动诊断（代码级已完成）

- [x] 复用现有 `TerminalAssociation` 与 `d5_live_visual_funnel_v1`，在 `summarize_cooperative_visual_funnel()` 中增加逐资源 `failure_category`、全 active-primary 分类计数和第二 primary 分类计数，不新增重复 DTO。
- [x] 区分不可见、投影无效、几何门拒绝、bbox 不稳定/边缘裁切、候选不唯一、量测陈旧、计划/版本/全局 ID 合同不一致、友方/重复锁定冲突和稳定锁定未完成；冲突全局 ID 只作为合同错误证据，不换绑中心 ID。
- [x] 保持全部 locked/hold/reacquire 与身份安全门不变；2026-07-15 专项 11 case、D5 全量 `272 passed`，接受阈值为零失败。
- [ ] 由 main 在真实 AirSim 2v2/M5N2 至少 10 seeds 中持久化并聚合该分类，验收每个失败样本恰有一个分类、online truth use/global ID rewrite 为 0，并量化第二 primary 的主要断点。该项未由确定性测试关闭。

本批未启动 AirSim，也未调整 PNG、bbox、几何、唯一性、友方、版本或时效阈值。M5N2 第二 primary 5 m/联盟完成、真实几何 drift、detect/YOLO/MOT 和二级同 tick freshness 仍为 P1。

## 2026-07-14 actual-v2 真实 AirSim 证据同步

- [x] 只读同步两个真实 AirSim seed-1 case：tuned 2v2（8 s、`png_ttc`）与 M5N2（35 s、`png_vm`）；actual-execution canonical artifact 为 `2/2` available，在线 identity/state truth use 为 `0/0`。
- [x] 分层记录末端事实：canonical actual 五层均独立 available，contract/control/terminal-switch/mode/physical 总计 `102/26/26/2/4`。`terminal_switch_allowed_count` 从最终 `control_commands.csv` 独立统计，2v2/M5N2 为 `26/0`，不从 control 层推断；2v2 visual/mode switch 为 `2/2`，M5N2 为 `0/0`。
- [x] 保留物理结果的独立分母：M5N2 active pair `2/3`、target `2/2`、coalition `0/1`，T001 第二 primary 最近约 `11.02 m`。不得以 target 成功替代第二 primary 或联盟完成，也不得以 lock acquisition 替代视觉控制接管。
- [x] 保持 AirSim detect 默认在线路径、online truth use 为 0 和 center-owned `global_track_id` 只读合同；本任务不修改代码、算法、阈值或默认 backend。
- [ ] P1 继续完成 visual acquisition/registration/gate 分层闭环、第二 primary 5 m/联盟完成、30/50 m 召回、1-5 帧 dropout 与 YOLO/native-MOT 至少 10 seeds confirmation。M5N2 既有视觉完成门仍为至少 `8/10`，与 physical coalition `0/1` 分母独立；D6 本批 formal overall status=`fail`，不得因 actual artifact `2/2` available 提前关闭。

本节仅同步 2026-07-14 运行证据。来源为 `p0_actual_v2_validation_20260714/d6_acceptance/P1_UNIFIED_ACCEPTANCE_REPORT.md` 和 main actual-execution 报告；不新增 AirSim episode。

## 2026-07-14 postbatch live visual evidence 收尾

- [x] 审计最新 M5N2 baseline/candidate：相机作用域为各自 `InterceptorN:0`，没有跨资源串用或在线 truth；baseline/candidate 分别为 `330/311` 条控制记录、`151/120` 条几何 locked，两组均仅 INT-03 有 `40` 条控制 bbox 非零。
- [x] 扩展 truth-free DTO：`local_visual_evidence` 和 `d7_handoff_input` 携带 bbox、中心、资源、camera/stream/backend、双时间戳及 measured/stability 状态。
- [x] 分离 geometric association lock 与 execution lock：`execution_lock_allowed` 必须同时通过 own-camera measured bbox、scope、合同、稳定 lock、bbox 稳定/尺度及原有安全门；scope 冲突 fail closed 为 `hold`。
- [x] 新增 bbox 缺失、相机 scope 冲突、小稳定框和完整 handoff 回归；2026-07-14 `py_compile` 通过，D5 全量 `261 passed`，零失败为接受阈值。
- [ ] main 在真实 AirSim 至少 10 seeds 校准多相机持续 detection、进入 30 m 后的当前 bbox、`640x480` 小框尺度和异常大框来源；D5 不通过降低 bbox、identity、friend、duplicate、version 或 calibration 门获得通过率。

本批代码级 DTO/执行锁定语义 P1 已关闭。没有新增 AirSim 运行；真实终端可见性和多 seed 准入仍开放。

## 2026-07-14 semantics_v2 seed-1 live funnel 历史诊断

- [x] 逐资源复核最新 M5N2 baseline/candidate：INT-02 measured detection 为 `195/193`，raw visual lock 为 `140/142`，final execution lock 为 `18/18`，两组 T001 consensus 均为 `14`，稳定锁定最大连续计数均为 `17`。
- [x] 确认主要时序断点：execution gate 只在 `0.4-2.2 s` 通过；INT-02 bbox 到 `19.0/18.6 s` 才稳定，此时已由 `arrival_window_expired` fail closed。该结论不支持降低任何 D5 安全门限。
- [x] 增加 `d5_live_visual_funnel_v1`、连续 measured execution-lock streak、首断点/责任域和显式 `d7_handoff_input`；运行记录顶层提供 main/D6 可直接消费的字段。
- [x] 覆盖正常连续 lock、raw lock 被到达窗口阻断、M-to-N committed membership 缺失三类确定性回归；2026-07-14 D5 全量 `258 passed`，接受阈值为零失败。
- [x] postbatch 在 `arrival_coordination_required=false` 时不再生成共同到达窗口；D5 对显式协调场景仍只读并拒绝已过期合同。
- [x] postbatch 已确认 main 能把当前 D5 local track 送入 D7；其他资源控制 bbox 为零来自末端阶段缺少当前 measured detection，不再归类为相机串线或简单 DTO 丢失。顶部 DTO 补丁仍需由 main 在后续 AirSim rerun 验证。

该历史批次没有修改 lock、bbox、identity、friend、duplicate、timestamp、calibration、plan/version gate，也没有修改或换绑 `global_track_id`。顶部 postbatch 章节给出当前开放项。

## 2026-07-14 bbox 稳定历史/共同视觉证据 P1 闭合（已完成）

- [x] 审计 postfix seed-1 的 `bbox_stable=false` 与 T001 `13/347`、`12/347` 共同视觉证据，定位 D5 consumer 与 main producer 的字段断点。
- [x] 将 bbox/MOT/stable-lock 历史绑定到 resource-target-local track-camera-backend-stream 身份；仅 plan version 刷新且该身份及 committed/current coalition membership 未变时继承历史。
- [x] 对 membership、resource-target binding、local track、camera/backend/stream、identity/friend/duplicate 冲突变化执行 fail-closed reset，并输出 history length、CV、reset reason、key/signature 和 measured/predicted source 审计字段。
- [x] 共同视觉证据只采纳 committed/current coalition 成员；保持锁定门限、center-owned `global_track_id` 和 YOLO/MOT 准入状态不变。
- [x] 增加 D5 合同/回归测试并同步 README、PLAN、D5 GAP/review 及受影响的 D5 docs；2026-07-14 D5 全量 `255 passed`，接受阈值为零失败，owned-path `git diff --check` 通过。

只读基线为 postfix seed-1：M5N2 baseline/candidate 的 `bbox_stable=true` 均为 `0/1388`，T001 consensus 分别为 `13/347`、`12/347`；2v2 PNG/TTC 为 `0/52`。每条旧 runtime 记录的 `visible_frame_count <= 1`，原因是 main 每 tick 只把当前 `scoped_local_tracks` 交给 stateless handoff；T001 另有 `326/347` tick 的真实 primary membership 变化，必须继续阻断共同连续证据。本轮没有新增 AirSim 运行。

D5-owned 历史/合同 P1 已关闭。canonical actual 已消费 committed coalition、pre-decision duplicate hint 及 camera/stream/backend/local-track transition/MOT 字段，并独立持久化五层 metric envelope；不再把这部分列为 main 未接线。当前开放 P1 收敛为 M5N2 第二 primary、真实几何 drift、detect/YOLO/MOT 多 seed 和二级同 tick freshness。

## 2026-07-14 原生 MOT 历史累计 P1 子缺口闭合

- 已完成：为 Ultralytics ByteTrack/BoT-SORT 增加 `(resource_id, camera_id, backend, native id)` 作用域的连续实测命中历史，不再把 `Results.boxes.id` 每帧固定解释为 `mot_history_length=1`。
- 已完成：一次空帧即中断连续 measured history，恢复帧从 1 重计；状态只在 `max_track_age_frames` 内保留，长期复用 ID 不继承稳定证据。
- 已完成：`reset_stream()`、`reset_all_streams()`/`reset_episode()`、native model 失败重建以及 native/fallback backend 切换均清理对应错误历史；IoU fallback 与 native 历史相互隔离。
- 验证：2026-07-14 Results-like 确定性回归覆盖双 backend、连续帧、跨资源/相机、ID 切换、空帧/遮挡、两类 reset 和 native-fallback-native，D5 全量 `241 passed`，接受阈值为零失败。
- 保持开放：真实 AirSim/真实图像至少 10 seeds 的 detector precision/recall、IDSW/continuity、P95、bbox/时间对齐和 30/50 m 召回准入。该代码修复不晋级 ByteTrack/BoT-SORT，不改变 detect 默认路径，也不降低任何终端安全门控。

## 2026-07-14 D3 feedback 分级 P1 复核

本轮关闭 D5 输出语义混淆子缺口，未增加公共 API。`TerminalAssociation` 的 `decision_state/friend_conflict_state/duplicate_terminal_lock_risk` 与 `TerminalConsistencySummary` 的 `consistency_state/recommended_d4_action` 已足够表达分级：

- 普通 `ambiguous/hold/reacquire`、geometry gate、bbox/时序不稳定保持 pair 级视觉不确定性，只能 `unknown + observe/request_secondary_cue`；连续帧不会再被自动升级为 `conflict/arbitrate`，且没有 resource-unavailable 含义。
- verified friend、spoof suspected、duplicate lock、assignment 授权/版本和 local/global ID conflict 保持 fail closed，并输出 `conflict/inconsistent + report_conflict/arbitrate`，供 D3/main 选择 hard planner feedback。
- 未验证/过期身份和 unknown category 保持待确认，不推断 hostile；`global_track_id` 不改写，online truth use 为 0。

2026-07-14 专项 52 项和当时 D5 全量 235 项测试全部通过，门槛为 0 failure；本日后续原生 MOT 历史修复后最新全量为 `241 passed`。当前 P1 为 M5N2 第二 primary、真实几何 drift、detect/YOLO/MOT 多 seed 和二级同 tick freshness；P2 为 Deep SORT/ReID、真实身份 adapter 和完整在线 PnP，IBVS/ROS 2 保持 P3。本次没有新增 AirSim 物理证据，也不改变这些开放项。

## 2026-07-13 M5N2 与原生 MOT 实测状态

- M5N2 实测已形成 `120` 条 active-primary 证据，`visible=120`，其中 D5 关联/锁定证据为 `74`；最佳参数组合的 coalition completion 为 `5/10`，未达到 `8/10` 验收线。主要失败原因是 `d5_not_locked` 和 `terminal_detection_acquisition_timeout`，因此该系统级 P1 仍未闭合。
- `per_primary + arrival_coordination_required=false` 只解除同帧/同时到达要求，不解除 D3 plan/owner/version、D4 coalition commit、友方、duplicate、measured evidence 和 reserve standby 门控。实测中 `global_track_id` rewrite 为 `0`、online truth use 为 `0`，安全合同继续保持。
- 原生 MOT screening 使用 `1920x1080`、FOV `90`，覆盖距离 `20/30/50 m`、confidence `0.1/0.2/0.3` 和 ByteTrack/BoT-SORT，共 `18` 个 case。20 m 时两种后端的 native active rate/continuity 均为 `1.0`、IDSW 为 `0`，P95 约为 `7.4/16.2 ms`；但离线 precision/recall 仅约 `0.26-0.33`，30/50 m 均无检测。
- 原生 MOT screening 的准入候选数为 `0`，因此 two-camera confirmation 执行数为 `0`。不得把 20 m 的 tracker 连续性解释为 detector 或跨视角关联已达标，默认在线路径保持 AirSim `simGetDetections` 不变。
- 当前 D5 P1 收敛顺序为：第二 primary 稳定获取与锁定、YOLO/AirSim bbox 口径和尺度诊断、30/50 m 远距召回、候选配置多 seed 标定。任何调参都不得降低 identity、版本、唯一性、友方冲突和 `global_track_id` 不变式门控。
- 2026-07-13 当日 D5 全量回归为 `232 passed`；2026-07-14 原生 MOT 历史修复后最新全量回归为 `241 passed`。本文中的 `235 passed`、`229 passed`、`204 passed`、`200 passed` 及更早数字均为对应实现阶段的历史基线，不代表当前测试总数。

## 1. 范围与安全边界

D5 只面向科研仿真、离线回放和保守的终端视觉配准评估。模块不实现真实飞控、硬件驱动、火控参数、毁伤逻辑、自动处置流程，也不绕过人工或中心授权。

局部终端节点必须遵守一个硬约束：不得改写、重建或重新分配 `global_track_id`。D5 只能基于中心分配的 `assigned_global_track_id`，报告本地视觉轨迹是否与该全局航迹匹配。

### 1.13 2026-07-13 类别同义词与高分辨率推理配置

- 对象类别比较统一经过 D5 taxonomy：`uav/drone/intruder` 及常见分隔变体均按 `uav` 比较，避免 detector 的 `intruder` 与 GlobalTrack 的 `uav` 产生 16 分错误惩罚。
- 原 detector 标签同时写入 track/frame metadata；类别字段不产生 affiliation，友方、未知和可疑身份仍由 `IdentityClaim` 独立处理。
- `YoloMotAdapterConfig.inference_imgsz` 接受正整数或 `(height, width)`，原样传给 Ultralytics native track/predict；`None` 保持旧默认调用兼容。
- per-camera tracker、online truth 隔离和 center-owned `global_track_id` 合同不变。该实现阶段的历史回归基线为 `229 passed`；2026-07-13 当日全量为 `232 passed`，2026-07-14 最新全量为 `241 passed`。
- 下一步由 main/runtime 为主相机和高空侦察相机分别选择推理尺寸，运行真实 AirSim 多 seed，对显存、P95 延迟、20-50 m recall 和 fallback 进行标定；本次实现不关闭该系统级 P1。

### 1.11 2026-07-13 混合 1080p/4K 分辨率闭合

- AirSim 场景合同记录拦截相机 `1920x1080`、高空侦察相机 `3840x2160`；main 仍负责把这些参数写入真实 settings。
- `CameraModel` 和投影结果携带各相机 `image_size`，YOLO/MOT 从每帧数组读取尺寸，检测适配器把尺寸写入无 truth 的本地元数据。
- 以 `640x480` 为参考像素尺度缩放 friend/recon/reacquire/rate 固定像素项；马氏门仍由对应相机的 K、投影协方差和检测协方差决定。
- 二级 detect 自适应协方差的最小/最大 sigma 随分辨率缩放；完全无中心跨视角比较在计算中心差、协方差迹和 bbox 面积差前转换到参考像素尺度。
- 模块单测为 `204 passed`。该项关闭 D5 内部“所有相机默认同一像素尺度”的缺陷；目标 Actor 扩大和真实 AirSim 重跑由 main/runtime 执行。

### 1.12 2026-07-13 YOLO 与 AirSim detect 双路评价合同

- 在线顺序固定为 `YOLO/MOT process_frame(no truth) -> main 获取 simGetDetections -> monitor.observe(post-online truth)`；后到 reference 只作用于 evaluator state，不修改已生成的 result、local ID 或任何 `global_track_id` 绑定。
- 汇总显式区分在线 detector bbox、在线 local MOT track、离线参考框 matched/missed/unmatched-online，以及 native/fallback tracker 帧。拦截相机 `1920x1080`、侦察相机 `3840x2160` 的 `image_size` 均由 frame result 和 local track 独立携带。
- 保留 legacy inline offline-evaluation 兼容入口，但本轮真实 AirSim 双路模式必须使用 post-online monitor 路径；报告以 `post_online_truth_frame_count` 审计实际执行顺序。

### 1.9 2026-07-12 原生 MOT 准入与 per-primary 证据

- 新增 `NativeMotAdmissionMonitor`，按 resource/camera stream 汇总 native active frame rate、fallback frame count、accepted detections、warmup-excluded P95 latency、local continuity、terminal local IDSW 和 offline detector precision/recall。标准 sweep metadata 覆盖 confidence `0.1/0.2/0.3` 与目标距离 `20/30/50 m`。
- ByteTrack/BoT-SORT 只有实际原生 tracker 产生 local ID 时才计 native active；deterministic IoU fallback 是失败基线，不进入 native MOT 准入。默认准入还要求至少 100 帧、native active rate >= 0.95、fallback=0、continuity >= 0.90、IDSW <= 1、precision >= 0.90、recall >= 0.80、去预热 P95 <= 100 ms。
- truth bbox/identity 只在 online `YoloMotFrameResult` 形成后做离线 detector 与 local-ID scoring；summary 不输出 truth identity，tracker ID 仍只属于相机本地命名空间。
- 严格 runtime 顺序固定为 `process_frame(no truth) -> main 获取 offline truth -> NativeMotAdmissionMonitor.observe()`。frame result 只暴露不含身份的 detector bbox；public post-online evaluator 计算 TP/FP/FN、precision/recall 且不回写 result。legacy metadata 评分保留兼容，但 post-online truth 优先且同帧不双计数。
- 新增 `per_primary_terminal_evidence()`。`per_primary` 只取消“必须等待另一个 primary 同帧 locked”的 D5 证据依赖，不取消 plan/coalition version、active role、friend、duplicate、measured local track 和 execution gate。输出明确 `grants_control_authority=false`，最终控制仍由 D3/D4/D7 仲裁。
- D5 `Assignment`、registration `GlobalTrackBinding` 和 `TerminalAssociation` 已新增同名只读字段 `terminal_authorization_scope`、`arrival_coordination_required`。旧合同默认 `coalition + true`；main 复制 D3 显式 `per_primary + false` 后，字段通过 metadata/runtime record 原样下发。调用参数不能把 coalition association 临时改成 per-primary。
- D5 单元回归在该实现任务时为 `200 passed`；当时未启动真实 AirSim。2026-07-13 的最新实测见本计划顶部和 1.10 节：screening 已执行，但没有候选晋级，默认 detect 主线不变。

### 1.10 2026-07-13 真实 AirSim 原生 MOT 标定状态与后续计划

本轮严格 screening 已完成 `18` 个 AirSim case，参数为 `1920x1080`、FOV `90`、距离 `20/30/50 m`、confidence `0.1/0.2/0.3`、ByteTrack/BoT-SORT。20 m 已关闭“原生 tracker 无法连续运行或延迟超预算”的子问题：两种后端 native active rate/continuity 均为 `1.0`，IDSW 为 `0`，P95 约为 ByteTrack `7.4 ms`、BoT-SORT `16.2 ms`。但 precision/recall 只有约 `0.26-0.33`，30/50 m 均无检测；`native_mot_admitted=false`、候选数 `0`、confirmation 数 `0` 均为正确结果，默认 detect 主线不变。

剩余 P1 分为三个可证伪假设：远距模型尺度/渲染域上限、YOLO 与 AirSim bbox 定义差异、在线结果与后到 truth bbox 的时序偏差。不能通过直接下调 IoU、confidence 或 D5 在线安全门限得出准入结论；应先保存并对齐逐帧在线 bbox、离线 reference bbox、时间戳、目标像素尺度和零检测原因。

下一轮标定矩阵：

| 维度 | 取值 | 必记证据 |
|---|---|---|
| 距离/尺度 | `20/25/30/40/50 m` | YOLO bbox 宽高/面积、置信度、目标是否在图、AirSim bbox 是否返回 |
| detector confidence | 主网格 `0.1/0.2/0.3`，诊断点 `0.05` | raw/accepted detection、precision/recall 与零检测原因 |
| tracker | ByteTrack、BoT-SORT | native active、fallback、continuity、local IDSW、去预热 P95 |
| bbox 评分 | IoU `0.1-0.5`，中心归一化误差、宽高/面积比、containment | 区分框定义差异与真正误检 |
| 时间对齐 | same frame、`-1/0/+1` frame | truth RPC timestamp、缺框/异常原因、最佳对齐偏移 |
| 重复性 | 候选配置至少 10 seeds、每组 >=100 帧 | 分 seed 指标、均值/区间、失败原因分布 |

验收保持分层。runtime 层要求 native rate >=0.95、fallback=0、continuity >=0.90、IDSW <=1/episode、P95 <=100 ms；评分可用性要求 truth 帧覆盖率 >=0.99 且未评分帧均有原因；检测层在已验证的 bbox 定义下要求 20 m precision >=0.90、recall >=0.80。30/50 m 必须先取得非零稳定检测后才可谈准入。任何离线 IoU 口径调整都不得传播到 D5 在线马氏门、唯一性/友方/版本/duplicate/authorization gate，也不得让 truth 进入在线 local track 或 `global_track_id` binding。

### 1.1 2026-07-11 实施前状态基线

以下内容只保留 `research_modules/airsim_runtime/outputs/blocks_cv_m5_n2_liveness_batch_20260711/M_TO_N_AIRSIM_CONVERGENCE_REPORT_CN.md` 的实施前历史基线。ComputerVision 模式只验证状态机与导引合同，不执行 SimpleFlight 动力学控制，因此下列结果不能解释为当前状态、物理拦截或命中：

- seeds 7/17/27 均为 6 次重规划请求、6 次 `no-change` 确认、0 次应用、0 次过期；需求满足率为 1.0，错误重复锁定为 0。
- 普通目标 T002 的视觉共识帧为 4/5/4，D7 每个 seed 获得 2 次终端合同许可，说明 D3-D4-D5-D7 的单 primary 状态链可重复闭合。
- 高威胁目标 T001 的双 active-primary 视觉共识在三个 seed 中均为 0。D5 的 M-to-N DTO、快照作用域、合法协同锁和两帧稳定汇总接口已完成，但共同可见和连续锁定的真实 AirSim P1 验收尚未完成。
- D5 当时回归基线为 `152 passed`。P0 无 blocker，truth ID 在线隔离、保守决策和 `global_track_id` 不变式继续作为强制回归项。

### 1.2 2026-07-11 验收历史状态（已由 1.6 节更新）

当时的证据为 `research_modules/airsim_runtime/outputs/p1_p2_validation_20260711/P1_P2_VALIDATION_SUMMARY_CN.md`。P1 合同层已经闭合：ComputerVision 10 seeds 的 T001 双 active-primary 当前计划授权与视觉共识为 `8/10`；10/10 的错误 duplicate 为 0，计划内合法协同多锁与错误重复锁已分离。commit-aware gate 的二级接管、完全分布式完整 ACK 正例均通过，缺 ACK 场景保守阻断 consensus/visual PNG authority 并 fail closed。

P1 物理/长期标定仍开放，而不是 D5 合同 DTO 未完成。ComputerVision 的 `control_allowed_count=0`；SimpleFlight 15 s 仅为诊断，30 个 active pair 均未命中，其中 24 个触发 `terminal_detection_timeout`。后续 P1 应定位持续 detection、D5 lock、D7 control gate 和闭合速度各层断点，并用长时真实多 seed 物理验收，不得把 `8/10` 合同验收写成控制切换或拦截成功。

能力层级仍需分开：`YoloMotAdapter` 是图像/MOT adapter，6 episode x 2 帧只算 smoke 且 accepted detection 为 0；IoU fallback 只提供确定性本地连续性；`TerminalCrossViewFusion` 仍是 metadata-only 研究近似，不是三维重投影、三角化或 bundle adjustment。它们均未替换默认在线关联路径。

P2 optional benchmark 已完成到隔离式离线合成对照：`p2_geometry_benchmark.py`/CLI 执行 OpenCV calibration/`solvePnP`，默认样本将后投影 RMSE 从约 24.0 px 降至 1.63 px，PnP 重投影 RMSE 约 0.43 px。它不进入在线 D5 默认路径，不写回 `CameraModel`，也不替代真实相机标定、PnP RANSAC、AirSim 外参漂移或硬件验收；默认在线路径仍是中心航迹投影、像素马氏门控、本地视觉轨迹和保守关联，未被 P2 替换。

### 1.3 本轮 detect-first / truth-isolated P1

- 在线探测保持 `simGetDetections` bbox，association source 为 `geometric_detect`；AirSim actor/object/truth/global 字段不参与 local ID、category、cost 或 binding，`truth_identity_used` 固定为 `false`。
- `LocalVisualTrack.local_track_state` 显式支持 `measured/predicted/lost`。predicted 只作为匿名 camera-local `reacquire` 证据，不计入几何 assignment 或稳定帧，不得输出 `locked/registered`。
- detection 暂失后，即使 MOT local ID 未变化，也必须重新通过几何门限并积累 measured stable frames；predicted 帧会打断稳定窗口。任何重捕只继续核对上游现有 `assigned_global_track_id`。
- `TerminalAssociation`/`TerminalObservation` 强类型保留 measurement/arrival 双时间戳、measurement/prediction age、local state、association confidence/reason，并通过 `to_runtime_record()`/`runtime_records()` 供 main/D6 直接消费。
- 本轮模块回归为 `157 passed`。P2 YOLO/ByteTrack 数据集标定保持 deferred；已有 OpenCV geometry benchmark 仅复核隔离状态，不接入默认在线路径。

### 1.4 2026-07-12 真实 AirSim 2v2 pilot 复核

证据 `research_modules/airsim_runtime/outputs/p1_5m_2v2_pilot_fix2_20260712/episode_006_full_flow` 共 96 条 D5 association：36 `locked`、48 `ambiguous`、12 `reacquire`。离线 truth 仅用于事后审计，36 个 lock 全部命中各自真实目标；ambiguous 中 37 个最佳候选为真实目标、10 个为本机拦截机、1 个为另一目标，均未被错误升级为 lock。ambiguous 原因为 37 次 `insufficient_best_second_margin`、9 次 `best_cost_exceeds_lock_threshold` 和 2 次首帧 `mot_history_too_short`；无 friend/duplicate 硬冲突。当前 `min_lock_margin=3.0`、`max_lock_cost=14.0` 和 3 帧窗口至少 2 次 measured 支持不应因单轮 pilot 放宽。

12 个 reacquire 均为分配航迹预测投影 `outside_image/behind_camera`，输出 `association_source=geometric_detect`、`truth_identity_used=false`、匿名上一 local ID、最后 measurement timestamp 和 `prediction_age_s=0.1-0.7 s`，属于可供 D4/D7 grace 的丢检/出视场证据，不是本地换绑或硬冲突。复核发现 handoff 注释在 `local_track_id=None` 时曾借用同相机其他检测的 timestamp/LOS/bbox，使 2.2 s 帧的真实 prediction age 0.6 s 被覆盖为 measurement age 0.0。现已修复为只沿用当前 association 的 measurement/prediction age，并在无 local ID 时禁止借用其他轨迹的 LOS/bbox。建议 D4/D7 短时 grace 先与 D5 `max_measurement_age_s=0.35 s` 对齐，即 10 Hz 下约 3 帧；超过该值继续 radar PN/fail closed，不把 0.6-0.7 s lost 证据当作新鲜视觉测量。

### 1.5 2026-07-12 D7 视觉证据合同补齐

D5 已完成 truth-free 视觉证据 DTO 与 adapter 接线：`CameraGeometryEvidence` 强类型携带 K、camera-to-NED rotation/position、measurement/arrival timestamp、attitude timestamp/age/validity；`LocalVisualTrack` 携带稳定 local ID、MOT history、迁移/reset、detect source 和 bbox edge clipping。关联输出/runtime record 原样透传这些证据，并保留 friend/duplicate/locked-hold-reacquire 门控。缺失几何明确为 unavailable，MOT coast 不产生授权。模块回归为 `161 passed`。

后续由 main/runtime 接入真实 AirSim 曝光时间、camera pose 与同步机体姿态；D7 在这些字段完整前只能使用现有 2D 图像证据，6D LOS 保持 replay-only/unavailable。D5 不实现导引 KF、TTC 或 LOS 滤波。

### 1.6 2026-07-12 commit 33e6fa0 后历史状态同步

本节保留 commit `33e6fa0` 时的 P0/P1 历史状态，依据当时的 D5 代码与测试、`subagent_reviews/MAIN_IMPLEMENTATION_GAP_AUDIT.md` 和 `research_modules/airsim_runtime/outputs/PNG_DELIVERY_ENHANCEMENT_AIRSIM_VALIDATION_REPORT_20260712.md`。当前结论以本文顶部 2026-07-13 实测状态为准。

| 优先级/能力 | 当前状态 | 2026-07-12 证据与边界 | 下一验收条件 |
| --- | --- | --- | --- |
| P0 安全合同 | 已闭合，保持原状态。 | 在线 truth/actor ID 隔离、相机作用域 local ID、friend/duplicate 保守门控、predicted/lost 禁止授权和 `global_track_id` 不变式均由 161 项模块测试保持；PNG delivery 报告的在线 truth 使用为 0。 | 持续运行 D5 全量测试；任何 truth/local ID 参与 binding、predicted 升级为 lock 或全局 ID 改写均重开 P0。 |
| P1 truth-free 视觉证据 schema | D5 侧已闭合，保持原状态。 | `CameraGeometryEvidence`、双时间戳/曝光时间、local-track transition/reset、MOT history、bbox clipping、相机 K/外参/姿态有效性已由 adapter、association 和 runtime record 透传。 | main/runtime 继续提供真实曝光时刻、camera pose、安装外参和同步姿态，并按相机/seed 校准时延与误差；缺字段时保持 unavailable。 |
| P1 2v2 主线非退化 | 系统级验收已通过，不新增 D5 算法完成项。 | candidate 10 seeds 为 20/20 pair 在 5 m 内成功，旧基线为 19/20，在线 truth=0，平均最小距离 4.844 m；自然运行没有触发 soft prediction/trend coast，因此不能把提升归因于 D5 或新增外推。 | 保持 D5 wrong binding/ID rewrite 为 0，并在同场景继续记录 D5 lock/hold/reacquire、D7 gate 和物理结果分层。 |
| P1 锁定后短时丢检 | 两帧真实链路已验证，长窗口仍开放。 | 锁定后 1.5-1.7 s 两帧 dropout 由 D7 在原 global/local track 与计划上下文内有界预测并达到 2/2 物理成功；D5 只提供身份/时序证据，不实现 coast 或控制。 | 跑 1-5 帧固定时刻矩阵；超过 0.25 s 必须 fail closed，重捕后需重新通过 D5 measured geometry gate 与稳定窗口，错误绑定为 0。 |
| P1 M5N2 视觉/联盟鲁棒性 | 开放。 | 2026-07-13 已取得 120 条 active-primary/visible 证据和 74 条 D5 关联/锁定证据；最佳 coalition completion 为 5/10，`global_track_id` rewrite 与 online truth use 均为 0。 | 优先提升第二 primary 的持续检测、稳定 bbox 和连续 measured lock；保持 plan/owner/version、friend/duplicate 和 reserve standby 门控，目标仍为至少 8/10。 |
| P1 真实几何/时间同步标定 | 部分实现，开放。 | DTO/日志字段和 unavailable 语义已闭合；真实 per-camera K/R/t/dist、曝光/arrival/attitude 同步误差、漂移恢复和 PnP RANSAC 尚未形成多 seed 验收。 | 固定相机与姿态来源，注入/采集漂移和延迟，报告重投影误差、门控拒绝、误锁、恢复时间及 unavailable 比例。 |
| P1 YOLO/native MOT、二级覆盖、D4 逐决策 evidence、真实友方 replay | 部分实测，继续开放。 | 原生 MOT 已完成 18-case screening；20 m tracker 连续性和延迟达标，但 precision/recall 仅约 0.26-0.33，30/50 m 无检测，0 候选进入 confirmation。二级覆盖和真实身份源状态不变。 | 先校正 bbox 口径/尺度/时间对齐和远距召回，再对候选做多 seed confirmation；同时保持二级完整覆盖、同 tick freshness/threshold version 和真实身份 replay 的既有验收条件。 |

### 1.7 P1 M5N2 双 primary 诊断接口（2026-07-12 已实现）

新增 `CooperativeResourceTargetDiagnostic`、`CooperativeTargetVisualFunnel`、`CooperativeVisualFunnelSummary` 和纯函数 `summarize_cooperative_visual_funnel()`。接口按现有 `global_track_id` 分组，逐资源输出 visible、projected、gate accepted、locked、稳定帧、共同窗口参与、置信度、歧义和拒绝原因；逐目标输出动态 active-primary 漏斗、最长共同锁定窗口、协同完成状态及第二 primary 的首个失败阶段。

完成判据保持 fail closed：只计算当前 plan/coalition 双版本匹配、已授权激活且在 committed coalition 中的 primary；D4 fallback commit 需要 epoch/lease/required member/ACK 全部有效；standby reserve 不计 active-primary completion。在线输出不读取或传播 actor/object/truth ID，也不创建或换绑 `global_track_id`。专项测试覆盖不同视场、共同窗口不足、版本不一致、友方冲突、稳定正例、动态资源/目标和缺 ACK，D5 全量基线更新为 `181 passed`。

main/D6 已将该 summary 接入 M5N2 paired AirSim episode，并形成 `assigned -> visible -> projected -> gate -> locked -> stable -> common window -> physical intercept` 漏斗。最新结果为 120 条 active-primary/visible 证据、74 条 D5 关联/锁定证据和最佳 coalition completion 5/10；D5 仍不修改 runtime、D7 控制和 PNG 公式。

### 1.8 pose-fix smoke 根因与共同窗口修正（2026-07-12）

已只读复核四组 `p1_cooperative_closure_v2_posefix_smoke_20260712_*`。T001 的 primary 成员集合频繁变化；`h020/w05/s040` 是当前单 seed 中视觉证据最充分的一组，但 183 帧仍只有 25 帧双 current lock、18 帧双稳定 lock。主要首断点是 best/second candidate margin 不足和视觉证据过期，另有 arrival window、outside-image/behind-camera。强类型 `camera_geometry` 在这些 runtime record 中全部 unavailable，尽管 candidate pair log 已携带投影和门控结果；main 后续需修复真实 K/R/t/姿态证据透传，D5 不允许用 truth pose 回填。

D5 已修复 cooperative funnel 的共同窗口跨版本不一致：共同窗口只使用 `stable_lock_frame_count` 已认可的 source plan versions、immutable historical binding 和当前连续尾段。合法单调升版且 primary 集合不变时可形成跨版本共同窗口；成员变化或任何安全冲突仍重新计数。`CoalitionVisualSummary.metadata` 新增逐 primary 首断点和相邻计划成员变化，cooperative summary 按 `global_track_id` 输出成员变化映射。新增测试覆盖安全跨版本正例、primary 换员阻断和真实 runtime 风格的 margin/expiry 失败。2026-07-13 重跑后的最佳 coalition completion 为 5/10，下一步针对第二 primary 的 `d5_not_locked` 和 detection acquisition timeout 做多 seed 标定，而不是降低视觉门限。

## 2. 核心工程问题与科学问题

工程问题：末端相机视场内可能同时出现分配目标、非分配目标、友方资源和未知飞行物。相机最近目标不一定是中心分配目标，本地 MOT 的 `local_track_id` 也不能替代全局身份。D5 需要在这些干扰下输出可解释、可审计的 `locked/ambiguous/hold/reacquire` 决策。

科学问题：如何融合中心航迹预测、像素协方差传播、几何门控、局部 MOT 稳定性、合作身份声明和二级侦察 cue，在不引入虚假确定性的前提下降低终端 ID switch 和错误绑定。

## 3. 输入输出

输入：

- `Assignment`：来自 D3/D4，包含 `assigned_global_track_id`、版本、授权状态和资源 ID。
- `GlobalTrack[]`：来自 D2，包含位置、速度、协方差、类别、时间戳和 `global_track_id`。
- `LocalVisualTrack[]`：来自本地检测/MOT，包含像素中心、bbox、角速率、质量、本地轨迹历史、`local_track_state` 和可选 `prediction_age_s`。
- `IdentityClaim[]`：来自仿真的 Remote ID、MAVLink 签名、DDS Security 或 AprilTag 等合作身份声明。
- `CameraModel`：相机内参、外参、图像尺寸和测量协方差。
- `ReconImageCue[]`：来自 D4 二级可机动高空侦察节点的局部图像 cue；高性能光电云台按 GlobalTrack/radar cue 指向目标簇，并可额外携带 `cue_position_ned`、`look_at_ned`、`gimbal_pointing_metadata`、`cue_pointing_error_m/rad`、`gimbal_track_error_px`、`cue_source`、`capability_class` 和 `coverage_mode`。

完全分布式跨视场输入：

- `resource_id/camera_id/frame_id`：给每个本地视觉轨迹建立唯一观测命名空间，避免不同无人机都使用 `track_1` 时发生冲突。
- `PeerCameraState`：记录每个 peer 相机在量测时刻的姿态协方差和可选位姿元数据。
- `measurement_timestamp/arrival_timestamp`：区分图像形成时刻和数据到达时刻，便于跨视场时间对齐。
- `covariance` 或 `covariance_px`：描述本地像素检测的不确定性，不把框中心当作确定值。
- `DistributedVisualObservation`：把上述字段和本地 `local_track_id`、bearing、bbox、类别、置信度封装为跨 peer 视觉观测。
- `VisualTrackletSummary`：按 `resource/camera:local_track_id` 汇总观测窗口，保留 bbox 面积、scale rate、bearing rate 和可选 `assigned_global_track_id` 状态。

输出：

- `TerminalAssociation`：包含中心分配 ID、本地候选 ID、置信度、歧义度、友方冲突状态、决策状态、候选代价、cue 使用标记，以及 detect-first source、双时间戳、age、local state 和 `truth_identity_used=false`。
- `CrossPeerAssociationHypothesis`：完全分布式模式下的跨 peer metadata-only 视觉假设，不创建全局 ID。
- `DistributedTerminalAssociation`：供 D4 完全分布式决策消费的保守摘要；missing/stale global ID、重复锁定、友方冲突或局部 ID 冲突时不得输出 `locked`。

## 4. 简化数学模型

### 4.1 时间预测

用常速度模型把中心航迹预测到图像帧时间：

```text
dt = t_image - t_track
p(t_image) = p(t_track) + v * dt
Sigma_p(t_image) = Sigma_p(t_track) + Q(dt)
```

该预测只用于终端投影对齐，不替代 D2 的航迹滤波器。

### 4.2 相机投影

使用针孔模型：

```text
P_c = R * P_w + t
u = fx * X_c / Z_c + cx
v = fy * Y_c / Z_c + cy
```

`Z_c <= 0` 或投影落出图像范围时，当前帧不可配准，输出 `reacquire`。

### 4.3 像素协方差传播

将世界坐标协方差传播到像素平面：

```text
J = d(project(P_w)) / d(P_w)
Sigma_px = J * Sigma_w * J^T + Sigma_measurement
```

用二维马氏距离进行几何门控：

```text
d2 = (z - p)^T * Sigma_px^-1 * (z - p)
```

默认门限采用 `gate_chi2 = 9.21`。

### 4.4 综合代价

候选代价：

```text
C = C_geo + C_rate + C_category + C_quality + C_friend + C_recon
```

其中 `C_recon` 只作为二级侦察 cue 的辅助负代价，不能越过授权、版本和友方冲突规则。

## 5. 算法选型理由

默认采用“中心航迹投影 + 像素马氏门控 + 本地 MOT 候选排序”的路线，原因是：

- 可解释：每个候选都有投影误差、角速率、类别、质量和身份冲突分项。
- 保守：没有候选过门限时不会强行匹配。
- 可集成：D2/D3/D4 已提供全局航迹、分配版本和降级计划。
- 可评估：D6 可以直接统计错误 `locked`、歧义事件、友方 `hold` 和 cue 使用次数。

ByteTrack、BoT-SORT、Deep SORT 只作为本地 MOT 输入来源。它们输出的 `local_track_id` 不能替代 `global_track_id`。

### 5.1 当前代码与测试状态

本节按当前 `src/d5_terminal_association/` 和 `tests/` 状态记录能力边界，避免把计划项写成已接入工程栈。

已实现并有测试或代码支撑的能力：

- `GlobalTrack -> CameraModel -> image projection`：`GlobalTrack` 是 frozen dataclass，`geometry.py` 和 `airsim_geometry.py` 支持投影、协方差传播、马氏门控和 AirSim camera info 到 D5 `CameraModel` 的离线转换。OpenCV 可用时使用 `cv2.projectPoints`；不可用时退回针孔模型。`TerminalAssociator.decide()` 和 `GeometricAssociationResult.to_log_records()` 已提供 projected pixel、bbox center、pixel error/reprojection error、Mahalanobis、gate pass、friend conflict、measurement age、selected pair、camera pose source、calibration health、drift warning 和 duplicate-risk advisory 字段，供 main/D6 后续写盘。
- `LocalVisualTrack`、`TerminalAssociation`、`IdentityClaim`、`ReconImageCue`：核心 DTO 已落地。`TerminalAssociator.decide()` 只核对 `Assignment.assigned_global_track_id`，输出 `locked/ambiguous/hold/reacquire`，不会选择另一个全局 ID 作为新分配。
- 保守 `decision_state`：未授权、版本不一致、已验证友方重叠时 `hold`；候选接近、质量不足或身份声明不可靠时 `ambiguous`；无有效投影或无门内候选时 `reacquire`；只有唯一、稳定、版本一致且无友方冲突时才 `locked`。
- P0-B 主动重捕获与时序一致性：`TerminalAssociator` 已保留 per `resource_id + assigned_global_track_id` 历史，正常 gate 失败时用 GlobalTrack 预测投影、上次 bbox/MOT 历史和 search window 主动寻找同一 assigned track；predicted 只输出 `reacquire` 且打断稳定窗口，恢复时无论 MOT ID 是否变化都必须重新通过 measured geometry gate 和 stable window，candidate margin、stale/OOSM、friend conflict、assignment/version mismatch 仍保持保守 `ambiguous/hold`。
- AirSim truth ID 隔离：`local_visual_tracks_from_sim_detections()`、`local_visual_tracks_from_offline_yolo_bytetrack()` 和 `YoloMotAdapter.process_frame()` 明确忽略 `object_id`、`actor_name`、`truth_id`、`true_global_track_id`、`global_track_id` 等真值/全局字段；若 AirSim `track_id`/`detection_id` 与 actor/truth 字段相同，sim detection adapter 会将其视为 truth alias 并回退到相机作用域本地检测 ID。truth label 只可在 `TerminalObservation.metadata` 或离线 evaluator 中用于 `terminal_lock_accuracy`、`locked_mismatch` 等评分。
- 跨视角 distributed visual association DTO 与 fusion：`DistributedVisualObservation`、`VisualTrackletSummary`、`PeerCameraState`、`CrossPeerAssociationHypothesis`、`DistributedTerminalAssociation` 和 `TerminalCrossViewFusion` 已实现 P0 metadata-only 融合。融合基于 measurement/arrival timestamp、bearing 或像素中心、bearing rate、bbox area/scale rate、类别/置信度、像素协方差和姿态协方差做 gating/cost；SciPy 可用时用 Hungarian，缺失时退回纯 Python 唯一匹配。
- 完全无中心下多相机 peer evidence 输出：缺失或 stale `assigned_global_track_id` 时输出 `hypothesis_only/hold`，重复锁定、友方冲突或 local/global ID 冲突时输出 `hold/ambiguous` 风险证据；不会创建新 `global_track_id`。
- D7 视觉 PNG 前置证据：`annotate_visual_png_handoff()` 已在 `TerminalAssociation.metadata` 上附加 bbox 面积稳定性、距离区间、TGO、延迟、measurement age、LOS rate、friend/duplicate 风险和机动裕度建议。该建议只给 D7/main 做 gate 输入，不决定导引律。
- D4/D6 一致性摘要：`TerminalConsistencyTracker` 已按 `resource_id + assigned_global_track_id` 维护连续窗口；`assignment_version` 只随摘要审计输出，不作为窗口 key。因此同一资源持续执行同一全局目标时，D3 plan version 滚动更新不会清空连续 `locked/ambiguous/hold/reacquire` 状态。该摘要只作为 advisory evidence，不触发降级、不生成分配计划、不改写 `global_track_id`。
- 二级视觉覆盖与 detect 漏斗诊断：`summarize_secondary_visual_coverage_funnel()` 接受普通 replay frame dict/dataclass、`TerminalObservation` 和 `CrossViewAssociation`，输出单二级相机 full-view 率、二级网络联合 full-view 率、每相机/网络每帧可见目标数、覆盖比例均值/最小值，以及 detect -> local/recon cue -> terminal association -> cross-view association -> multi-support 计数。offline target label 只用于“看见目标”覆盖统计，不进入在线绑定。
- Detect-to-global-track registration：`register_local_visual_tracks_to_global_tracks()` 接受 `GlobalTrack[]`、D2/D3 binding/`Assignment`、每相机 `CameraModel(K/R/t)`、timestamp、协方差和 `LocalVisualTrack[]`，输出 registration candidates、registered observations、即时 cross-view support 和稳定 `stable_cross_view_associations`。truth/actor ID 和 tracker ID 不参与在线绑定。
- P0-B calibration health：`TerminalAssociation.metadata`、`TerminalConsistencySummary.to_metadata()`、registration candidate、registration observation 和 registration result summary 已输出 `projection_valid`、`reprojection_error`/`reprojection_error_px`、`camera_pose_source`、`camera_pose_source_trusted`、`calibration_health`、`calibration_health_reason`、`drift_warning`、health/source counts 和重投影误差摘要。P0-B 只做健康监测和告警，不做在线标定或外参重估。
- P1 二级 detect 注册校准：candidate/observation metadata 已补齐 `pixel_error_px`、`reprojection_error`、`mahalanobis_d2`、`gate_pass`、`projection_valid`、`camera_pose_source`、`calibration_health`、`drift_warning`、`bbox_area_px` 和仅离线评分用的 `offline_truth_global_id`。`camera_pose_source` 只从 batch metadata 标注 `airsim_camera_pose`、`runtime_guidance_pose` 或 `look_at_fallback`，D5 不调用 AirSim。
- P1 自适应像素协方差：`adaptive_pixel_covariance_px()` 按 `sigma_px = clamp(max(25, 0.5*sqrt(bbox_area_px), 0.008*image_diag_px), 25, 90)` 生成二级相机 bbox 观测协方差；有 bbox 面积时用于几何门控，无面积时保留 `batch.covariance_px` fallback。
- P1 多帧稳定注册：默认 `RegistrationStabilityConfig(window_frames=3, required_gate_passes=2)`。单帧 gate pass 只形成 candidate；近 3 帧内同一 `resource/camera/local_track/global_track` 至少 2 次通过才标记 `stable_cross_view_support=True`，否则 reason 记为 `stability_window_failed`。该逻辑只增加既有 `global_track_id` 的视觉支持，不创建、不改写、不换绑 ID。
- 机动高空侦察云台覆盖证据：`ReconImageCue`、`TerminalObservationBus.cross_view_associations()` 和 `summarize_secondary_visual_coverage_funnel()` 已支持 `fixed_downlook_secondary` 与 `mobile_recon_gimbal` 分层。移动侦察节点可记录雷达/GlobalTrack cue 到云台 look-at 的 NED 位置、pointing error 和像素 track error；coverage funnel 会标出固定俯视未 full-view、移动云台补足网络联合覆盖的帧和新增目标集合。

2026-07-08 AirSim D4/D5 视觉校准历史状态：

- `research_modules/airsim_runtime/outputs/p1_d4d5_mobile_recon_20260708_055948*` 现在只作为历史 stress 证据：旧批次覆盖 3 个 seed、5v5 D4/D5 stress、200 m 高差、80 deg FOV、1920x1080，证明 D5 已能识别 `mobile_recon_gimbal`、`radar_global_track_cue`、`mobile_high_recon` 和云台指向 metadata。该批次的 bbox 3326-3334 px^2 对固定俯视约 1144-1145 px^2 只能说明目标看清能力改善，不能作为当前闭环结论；其覆盖与降级注册仍未闭合。
- 当时最新的 registration calibration v2 输出为 `research_modules/airsim_runtime/outputs/p1_d4d5_registration_calibration_runtime_v2_20260708*`，单 seed、3 个机动高空二级节点、200 m、110 deg、1920x1080。
- v2 结果：`projection_valid_rate=1.0`，`geometry_gate_pass_rate≈0.474`，三个 case 的 stable cross-view registration 为 51/55/53，cross-view association 为 4/4/5，`degrade_to_secondary` / `degrade_to_distributed` 的 not-registered case 仍为 35/35，full-view mean≈0.048，coverage mean≈0.771。
- 该单 seed 结果只保留为历史基线；其中降级 case not-registered 35/35 已被 2026-07-10 的 60-case sweep 改写，不能继续作为当前状态。

2026-07-08 P1 calibration sweep 集成状态：

- main runtime 已新增 P1 D4/D5 calibration sweep，用于扫描二级高度、FOV、二级节点数量和 standoff 组合，并在每个组合内运行多 seed stress episode。
- main runtime 的 D4/D5 stress 链路已可把二级 detect-to-global-track registration 输出写入同一个 `TerminalObservationBus`，用于统计 `registered_to_global_track`、`geometry_gate_rejected`、`secondary_detect_available_but_not_registered`、cross-view support 和 coverage funnel。
- D6 标准报告 bundle 已由 main runtime 自动生成，输出 `d6_airsim_calibration/airsim_calibration_records.csv`、`airsim_calibration_summary.csv`、`airsim_calibration_summary.json` 和 `airsim_calibration_report.md`。
- 因此 D5 当前 P1 重点不再是“是否有 registration/helper/report 接口”，而是通过真实 AirSim 多 seed sweep 校准二级网络覆盖、注册门限、YOLO/MOT 阈值、外参误差和 D4/D7 消费口径。

2026-07-10 真实 AirSim 60-case registration 状态：

- 证据目录为 `research_modules/airsim_runtime/outputs/p1_gap_closure_calibration_20260710`：5v5、10 seeds、50/200 m 二级高度、3 类 case，共 60 个 case。
- 60 个 case 均已形成有效 registration 记录；D6 的 `not_registered_count=0`，sweep 的 `secondary_detect_available_but_not_registered` 均值/最大值均为 0。平均 `projection_valid_rate=1.0`、`stable_cross_view_registration_count=92.233`、`cross_view_association_count=4.417`。
- 该结果关闭“detect 无法注册到既有 `global_track_id`”这一接口缺口，但不等于二级节点已具备完整接管态势：网络同帧全目标覆盖率均值仅 `0.0231`，平均覆盖率 `0.7059`，稳定窗口失败仍是主要 reject reason。D5 不因注册成功而放宽唯一性、友方冲突、版本、时效或 D7 独立安全门控。

2026-07-11 AirSim YOLO/MOT 冒烟状态：

- `p1_yolov8_bytetrack_smoke_fixed_20260711` 已完成 6 个 reset-separated episode、每个 2 帧；RGB 解码、YOLOv8/ByteTrack 调用、per-stream tracker state、在线 truth 隔离、offline bbox-only 评分和 runtime event 均能执行。
- 当前相机/actor 几何下 `accepted_detection_count=0`，AirSim offline truth box 多数也为 0，无法据此计算有效 detector recall 或 MOT continuity。原生 ByteTrack 因没有 track ID 退回 `iou_fallback`；观测延时多数约 38-49 ms，首轮约 197 ms。
- 三组既有 D4/D5 回归均有 `cross_view_association_count=4`，稳定注册约 19-61，但二级同帧全目标覆盖仍不足。后续不得用局部 cross-view count 替代完整网络覆盖指标。
- 因此计划状态为“接口闭合、检测/MOT 质量未闭合”。下一轮先让 AirSim offline truth bbox 对有效视场提供非零标签，再校准 YOLO 类别映射、阈值、目标像素尺度和相机指向；只有 accepted detection 非零且原生 tracker 产生稳定 ID 后，才进入多 seed IDSW/IDF1、遮挡恢复和预算验收。

部分实现或仅作为 adapter/抽象的能力：

- 真实工程几何配准：当前消费已有 `CameraModel.K/R/t/dist_coeffs`，并能离线验证投影误差；P2 已有合成 `calibrateCamera`/`solvePnP` 扰动 benchmark，但没有真实标定采集、PnP RANSAC、bundle adjustment 或在线外参漂移估计链路。
- YOLOv8/ByteTrack/BoT-SORT：已提供 `YoloMotAdapter` 图像帧入口，默认权重为 `/home/linux/Documents/MSM/research_modules/d5_terminal_association/best.pt` 且允许参数覆盖。`ultralytics` 可用时可请求 ByteTrack 或 BoT-SORT 原生 tracker；依赖、权重或原生 tracker 不可用时返回 `unavailable` 或退回确定性 IoU tracker，并在 `YoloMotFrameResult.metadata` 标明 stream key、实际 backend 和 per-stream 状态作用域。fallback tracker 与 native model/tracker 均按 `(resource_id, camera_id)` 隔离；输出仍只是带 camera namespace 的 `LocalVisualTrack`，tracker ID 不替代 `global_track_id`。
- Deep SORT/ReID：仍仅作为未来对照来源；当前没有 ReID embedding、长遮挡恢复或 IDSW/IDF1 统计实现。
- OpenCV：已用于投影与可选畸变参数消费；未实现标定工作流和真实图像角点/AprilTag 检测。
- ROS 2 `tf2/message_filters`：仅作为未来坐标/时间同步方案；D5 当前不启动 ROS graph，不订阅 topic，不消费 bag。
- OpenDroneID、MAVLink signing、DDS Security、AprilTag：`IdentityChecker` 只解析仿真/fixture 风格身份字典并生成 `IdentityClaim`；未接入真实广播报文、密钥、证书、tag detector 或硬件链路。

未实现的真实工程能力及原因：

- 真实 AirSim/main 图像接线：最小 2 帧 RGB/YOLO/MOT 冒烟链已接通；仍需推进到连续多帧、多 seed 和非零 accepted detection。main 必须保持 stream key 稳定，并在 episode 边界调用 `reset_all_streams()`。
- 真实 MOT 标定：ByteTrack/BoT-SORT 原生质量依赖 `ultralytics` 和连续图像；IoU fallback 只保证 deterministic local ID 连续性，不声明遮挡恢复、ReID、IDSW/IDF1 工程质量。
- 真实标定链：缺少标定图像、标定板/AprilTag 角点、相机-机体系-世界系同步姿态、重投影误差验收阈值和 drift 告警流程。
- 真实身份认证链路：缺少 OpenDroneID/MAVLink/DDS 实际报文、密钥和白名单管理、时钟一致性、消息来源到平台身份的可信映射。
- 跨相机三维联合优化：缺少多相机同步 `CameraModel`、D2 航迹预测合同、三角化候选、重投影残差模型和 D4/D6 消费协议；当前只承诺 metadata-only peer evidence。

## 6. 二级侦察节点 cue 计划

本阶段假设存在若干可机动高空侦察无人机作为二级区域节点。节点携带高性能光电云台，可随任务机动，并依据 GlobalTrack/radar cue 指向目标簇；中心节点正常时向覆盖小区内的拦截资源发送图像 cue，中心节点失效时由 D4 降级到二级节点协调，二级节点也失效时才进入完全无中心协商。

D5 将该输入表示为 `ReconImageCue`：

- `producer_node_id`：cue 来源二级节点。
- `image_frame_id`：cue 所属图像帧。
- `global_track_id`：可选的全局航迹提示。
- `center_px` 与 `bbox`：图像平面提示。
- `confidence`：cue 置信度。
- `scoped_resource_ids`：允许使用该 cue 的资源集合。
- `cue_position_ned` / `look_at_ned`：雷达或 GlobalTrack cue 与云台 look-at 的 NED 位置。
- `gimbal_pointing_metadata`：云台 yaw/pitch、目标簇/子簇、时间同步或控制状态等报告字段。
- `cue_pointing_error_m` / `cue_pointing_error_rad` / `gimbal_track_error_px`：cue 指向和图像跟踪误差。
- `cue_source`：例如 `radar_global_track_cue`。
- `capability_class` / `coverage_mode`：例如 `mobile_high_recon` 与 `mobile_recon_gimbal`；固定俯视二级相机使用 `fixed_downlook_secondary`。

关键约束：

- 若 cue 来自二级侦察节点自己的相机，必须先重投影到当前拦截资源相机平面。
- 未重投影的二级相机像素不能直接与 `LocalVisualTrack.center_px` 比较。
- cue 只能降低候选代价，不能绕过授权、版本校验、友方确认和 MOT 质量门槛。
- 空 `scoped_resource_ids` 当前可视为广播 cue；若实验要求严格小范围分发，应改为显式广播标记或视为空无效。
- 当前实现已加入 cue 新鲜度、目标相机帧校验、重投影标记校验和 `recon_cue_used` 决策标记；`recon_cue_used_count` 仍需进入 D6/main 统一日志。

机动侦察节点的图像服务末端跨视角配准的目标链路是：

```text
GlobalTrack/radar cue
-> mobile high-recon gimbal look-at(cue_position_ned, look_at_ned)
-> detector/MOT produces LocalVisualTrack[] on recon/interceptor cameras
-> per-camera geometry gate and Hungarian/JPDA-style candidate selection
-> TerminalAssociation for the existing assigned_global_track_id
-> TerminalObservationBus/CrossViewAssociation evidence
```

固定俯视二级相机覆盖不足时，D5 只在 evidence 中报告 `fixed_downlook_secondary` 的覆盖缺口和 `mobile_recon_gimbal` 对目标簇/子簇的补充覆盖；它仍不生成分配计划、不控制云台、不改写 `global_track_id`。

## 7. 多无人机重叠视场配准计划

典型场景：无人机 1 的相机看到目标 1/2/3，无人机 2 的相机看到目标 2/3/4。两个相机的 `local_track_id` 只在本机本相机内有效，例如 `UAV1:cam0:L2` 与 `UAV2:cam0:L2` 可能指向不同目标，也可能分别是同一个 `global_track_id` 的两个观测。D5 的跨视场目标是把这些本地观测配准到 D2 已存在的 `global_track_id`，而不是在本地创造新的全局 ID。

建议流程：

1. 当前 `TerminalObservationBus` 收集每架无人机的 `TerminalObservation` 摘要；完全分布式 metadata-only 路径使用 `DistributedVisualObservation` 和 `VisualTrackletSummary` 携带资源、相机、帧、时间戳、协方差和本地 MOT 命名空间信息。
2. 对 D2 的每个 `GlobalTrack` 按各自相机的 `measurement_timestamp` 做时间预测。
3. 将同一个 `GlobalTrack` 分别投影到 UAV1、UAV2 等相机平面，得到每个视场内的像素预测和协方差。
4. 在每个相机内先做像素马氏门控，形成局部候选代价。
5. 对重叠视场中的共享目标 2/3，比较多相机候选是否同时支持同一 `global_track_id`。
6. 对时间差过大、相机姿态不可信、协方差过大或候选代价接近的情况输出 `ambiguous/unknown`，不强行跨视场绑定。
7. 二级侦察 cue 先重投影到每个目标相机平面，再按 `scoped_resource_ids` 对相应资源降低候选代价。

当前已实现接口：

- `TerminalObservation`：单条跨节点末端摘要，可携带 `LocalVisualTrack`、`TerminalAssociation`、`IdentityClaim` 和 `ReconImageCue`。
- `TerminalObservationBus`：被动收集多资源/多链路摘要，按既有 `global_track_id` 生成跨视角汇总。
- `CrossViewAssociation`：表达一个 `global_track_id` 的 `supporting_resource_ids`、命名空间化 `local_track_ids`、`ambiguity_score`、`duplicate_terminal_lock_risk`、来源节点和链路类型。
- `DistributedVisualObservation`、`VisualTrackletSummary`、`PeerCameraState`：完全分布式 metadata-only 跨 peer 输入 DTO。
- `TerminalCrossViewFusion`：基于时间窗口、bearing、bearing rate、bbox area/scale rate、类别/置信度、像素协方差和姿态协方差做 gating/cost，并使用 Hungarian 或纯 Python fallback 做唯一匹配。
- `CrossPeerAssociationHypothesis`、`DistributedTerminalAssociation`：向 D4 输出支持假设、`hypothesis_only/hold/ambiguous/locked` 状态、重复终端锁定风险和命名空间化 local track IDs。

该最小实现覆盖 UAV1 看到目标 1/2/3、UAV2 看到目标 2/3/4 的摘要层逻辑：目标 2/3 得到多视角支持，目标 1/4 保持单视角支持；重复锁定只上报风险，不改分配。

当前 `TerminalCrossViewFusion` 是 P0 metadata-only 融合器，不做三维重投影、三角化、bundle adjustment、真实图像 ReID 或 D4 分配决策。后续完整几何融合可新增 `CrossViewTrackEvidence`，把相机几何重投影和 D2 航迹预测纳入同一摘要，但仍不改变 D5 不改写 `global_track_id` 的边界。

## 8. 实施流程

1. 读取 D3/D4 分配，确认授权状态和版本。
2. 从 D2 航迹表中查找中心分配的 `global_track_id`。
3. 按图像帧时间预测该航迹。
4. 调用 `project_tracks_to_image()` 得到像素预测和协方差。
5. 将本地检测/MOT 输出标准化为 `LocalVisualTrack[]`。
6. 将合作身份消息标准化为 `IdentityClaim[]`。
7. 将已重投影的二级节点图像提示标准化为 `ReconImageCue[]`。
8. 调用 `build_cost_matrix()` 构造候选代价。
9. 调用 `decide()` 输出 `TerminalAssociation`。
10. 记录候选代价、身份冲突、决策状态和 cue 使用情况，交给 D6 离线评估。
11. 当前可由 `TerminalObservationBus` 汇总多个资源的 `TerminalAssociation` 摘要，向 D3/D4/D6 上报 `CrossViewAssociation` 支持关系和重复锁定风险。
12. 完全分布式模式可由 `TerminalCrossViewFusion` 对多个资源的 `DistributedVisualObservation` 或 `VisualTrackletSummary` 做 metadata-only 跨 peer 融合，并只向 D4/D6 上报 `CrossPeerAssociationHypothesis` 和 `DistributedTerminalAssociation`。

## 9. 代码模块划分

```text
research_modules/d5_terminal_association/
├── PLAN.md
├── README.md
├── docs/
│   ├── ALGORITHM_AND_IMPLEMENTATION.md
│   ├── EXPERIMENT_REPORT.md
│   ├── AIRSIM_INTEGRATION_PLAN.md
│   └── terminal_decision_timeline.png
├── simulations/
│   └── run_terminal_association_sim.py
├── src/d5_terminal_association/
│   ├── airsim_cv_adapter.py
│   ├── airsim_geometry.py
│   ├── associator.py
│   ├── consistency.py
│   ├── geometry.py
│   ├── identity.py
│   ├── observation_bus.py
│   ├── terminal_cross_view_fusion.py
│   ├── visual_handoff.py
│   └── models.py
└── tests/
    ├── test_airsim_cv_2v2_secondary_plan.py
    ├── test_airsim_cv_5v5_evidence.py
    ├── test_distributed_cross_view_fusion.py
    ├── test_geometric_registration_validation.py
    ├── test_terminal_association.py
    ├── test_airsim_dry_run_interface.py
    ├── test_terminal_consistency.py
    ├── test_terminal_observation_bus.py
    └── test_visual_handoff.py
```

主要职责：

- `models.py`：定义 `GlobalTrack`、`LocalVisualTrack`、`Assignment`、`IdentityClaim`、`ReconImageCue` 和 `TerminalAssociation`。
- `airsim_cv_adapter.py`：转换 `simGetDetections` 风格检测框，生成 N-v-N ComputerVision 压测指标、三类降级证据摘要和 multi-seed calibration readiness 字段覆盖审计；5v5 只是 stress baseline。
- `yolo_mot_adapter.py`：运行或适配 YOLOv8 图像帧检测，优先请求 ByteTrack/BoT-SORT，缺依赖时退回确定性 IoU tracker，输出 `LocalVisualTrack` 和 backend metadata。
- `airsim_geometry.py`：提供 AirSim 相机内外参到 D5 投影模型的离线转换和几何匹配验证辅助，不读取 AirSim truth 做在线关联。
- `observation_bus.py`：定义最小跨节点 `TerminalObservationBus` 汇总逻辑，输出 `CrossViewAssociation` 风险与支撑摘要。
- `terminal_cross_view_fusion.py`：定义完全分布式 metadata-only 跨 peer 假设生成，输出 `CrossPeerAssociationHypothesis` 和 `DistributedTerminalAssociation`。
- `consistency.py`：把连续帧 `TerminalAssociation`、跨视角摘要和冲突状态压缩为 `TerminalConsistencySummary`。
- `visual_handoff.py`：给 D7/main 输出视觉 PNG handoff advisory metadata，检查 locked、bbox 稳定、分配一致和重复锁定风险。
- `geometry.py`：实现投影、协方差传播和马氏距离。
- `identity.py`：解析仿真身份声明并判断友方冲突。
- `associator.py`：实现投影、代价矩阵和保守决策。
- `simulations/`：生成离线合成场景和实验结果。
- `docs/`：保存算法说明、实验报告、图表和 AirSim 离线计划。

## 10. 关键接口

推荐全部使用关键字参数调用，尤其是 `current_time` 和 `recon_image_cues`：

```python
decision = associator.decide(
    assignment=assignment,
    global_tracks=global_tracks,
    local_tracks=local_tracks,
    identity_claims=identity_claims,
    camera=camera,
    current_time=current_time,
    recon_image_cues=reprojected_recon_cues,
)
```

核心接口：

- `TerminalAssociator.project_tracks_to_image(global_tracks, camera, timestamp=None)`
- `TerminalAssociator.build_cost_matrix(projections, local_tracks, identity_claims=(), recon_image_cues=(), resource_id=None)`
- `TerminalAssociator.decide(assignment, global_tracks, local_tracks, identity_claims=(), camera=None, current_time=None, recon_image_cues=())`
- `IdentityChecker.parse_claims(raw_messages, current_time)`
- `TerminalObservationBus.publish_terminal_association(...)`
- `TerminalObservationBus.publish_local_track(...)`
- `TerminalObservationBus.cross_view_associations()`
- `TerminalCrossViewFusion.summarize_observations(...)`
- `TerminalCrossViewFusion.build_hypotheses(...)`
- `TerminalCrossViewFusion.associate(...)`
- `local_visual_tracks_from_sim_detections(...)`
- `YoloMotAdapter.process_frame(frame, resource_id=..., camera_id=..., frame_id=..., timestamp=...)`
- `YoloMotAdapter.reset_stream(resource_id, camera_id)`
- `YoloMotAdapter.reset_all_streams()`
- `YoloMotAdapter.reset_episode()`
- `publish_sim_detections_as_local_observations(...)`
- `compute_terminal_stress_metrics(...)`
- `summarize_degradation_case(...)`
- `summarize_multiseed_calibration_readiness(...)`
- `summarize_secondary_visual_coverage_funnel(...)`

最小跨视角摘要接口：

```python
bus.publish_terminal_association(
    resource_id="UAV1",
    source_node_id="UAV1",
    link_type="interceptor_peer",
    timestamp=current_time,
    terminal_association=decision,
    local_track=local_track,
    camera_id="front_rgb",
    frame_id="UAV1/front_rgb",
)

cross_view = bus.cross_view_associations()
```

完全分布式 metadata-only 跨视场接口：

```python
distributed = terminal_cross_view_fusion.associate(
    observations=distributed_visual_observations,
    tracklet_summaries=peer_tracklet_summaries,
    camera_states=peer_camera_states,
    current_assigned_global_track_ids=current_ids,
    stale_assigned_global_track_ids=stale_ids,
)
```

该接口只输出 `DistributedTerminalAssociation`，每条摘要携带 `CrossPeerAssociationHypothesis`；不产生新分配计划，不创建或换绑 `global_track_id`。

## 11. 仿真场景设计

初始仿真使用简单图像平面和质点投影，不涉及真实飞控或硬件：

- 一个中心分配目标。
- 一个非分配干扰目标。
- 一个带合作身份声明的友方目标。
- 一个未知目标靠近分配目标投影，制造歧义。
- 分配目标短时遮挡，触发 `reacquire`。
- 友方目标与投影重叠，触发 `hold`。

后续补充：

- 已重投影的二级侦察 cue。
- stale cue。
- 跨资源 cue。
- 空 `scoped_resource_ids` 语义对照。
- UAV1 看到目标 1/2/3、UAV2 看到目标 2/3/4 的重叠视场 metadata-only 配准。
- N-v-N ComputerVision 压测：数量由 main runtime 的 `--drone-count N` 统一控制；5v5 baseline 使用目标距主镜头约 50m、目标间距 20m、镜头间距 20m，每个主镜头视场内至少两个目标。
- 二级可机动高空侦察节点可保持约 200m 高差，使用高性能光电云台按 GlobalTrack/radar cue 指向目标簇，并输出已重投影到拦截机相机平面的 `ReconImageCue`。
- 相同 `local_track_id` 在不同无人机中重复出现的命名空间冲突测试。
- 相机姿态误差、时间戳错位和高协方差观测导致的跨视场 `ambiguous`。
- `no_degradation`、`degrade_to_secondary`、`degrade_to_distributed` 三类 D5 证据 case。

## 12. 指标

D5 至少记录：

- `terminal_association_accuracy`
- `locked_precision`
- `wrong_locked_count`
- `ambiguous_count`
- `hold_count`
- `friend_overlap_hold_count`
- `reacquire_count`
- `time_to_terminal_lock`
- `terminal_id_switch_count`
- `global_track_id_rewrite_count`
- `recon_cue_used_count`
- `cross_view_association_accuracy`
- `cross_view_id_switch_count`
- `cross_view_ambiguous_count`
- `cross_view_duplicate_local_id_count`
- `per_camera_detection_count`
- `multi_target_fov_rate`
- `cross_view_overlap_count`
- `duplicate_terminal_lock_risk`
- `terminal_lock_accuracy`
- `ambiguous_fov_event_count`
- `secondary_single_camera_full_view_frame_rate`
- `secondary_network_joint_full_view_frame_rate`
- `secondary_camera_frame_visible_target_counts`
- `secondary_network_frame_joint_visible_target_counts`
- `secondary_single_camera_coverage_ratio_mean`
- `secondary_single_camera_coverage_ratio_min`
- `secondary_network_joint_coverage_ratio_mean`
- `secondary_network_joint_coverage_ratio_min`
- `detect_count`
- `local_or_recon_cue_count`
- `terminal_association_count`
- `cross_view_association_count`
- `multi_support_count`
- `rejection_reason_counts`
- `coverage_mode_counts`
- `mobile_recon_gimbal_improved_joint_coverage_frame_count`
- `mobile_recon_gimbal_added_target_ids_by_frame`
- `cue_pointing_error_m_by_camera_frame`
- `cue_pointing_error_rad_by_camera_frame`
- `gimbal_track_error_px_by_camera_frame`

其中 `global_track_id_rewrite_count` 应始终为 0。二级覆盖指标分三层解释：`visible_target_ids`/覆盖比例只表示二级相机“看见目标”；`secondary_network_joint_full_view_frame_rate` 表示同一帧多二级相机并集覆盖全部 active targets；`cross_view_association_count` 和 `multi_support_count` 才表示检测/本地 cue 已经转成既有 `global_track_id` 支持。`mobile_recon_gimbal_improved_joint_coverage_frame_count` 只说明机动云台 evidence 补足固定俯视覆盖，不代表 D5 获得分配或控制权限。

## 13. 预期交付物

- 根目录 `PLAN.md` 和 `README.md`。
- `docs/ALGORITHM_AND_IMPLEMENTATION.md`：中文算法原理与实施方案。
- `docs/EXPERIMENT_REPORT.md`：中文实验报告和图表引用。
- `docs/AIRSIM_INTEGRATION_PLAN.md`：AirSim 离线回放与接口计划。
- Python 源码、单元测试和离线仿真脚本。

## 14. 局限与后续工作

- `ReconImageCue` 的 scope、age、frame 和重投影标记已有代码校验，但真实二级侦察图像反投影/重投影链路尚未接入；当前 cue 仍主要来自 fixture 或预处理结果。
- 已实现 `TerminalObservationBus`、`CrossViewAssociation`、`TerminalCrossViewFusion` 和 N-v-N ComputerVision dry-run evidence helper。
- 尚未完整实现跨无人机多相机三维几何融合；`CrossViewTrackEvidence` 仍是后续接口建议。
- 当前身份声明为离线仿真抽象，不连接真实 OpenDroneID、MAVLink signing、DDS Security 或 AprilTag detector。
- 本地 MOT 质量对小目标场景影响大；18-case AirSim screening 已证明 20 m 下 ByteTrack/BoT-SORT 可原生连续运行且延迟在预算内，但 precision/recall 仅约 0.26-0.33，30/50 m 无检测，0 候选进入 confirmation。bbox 口径/尺度、远距召回、GPU/CPU 多 seed 预算仍未闭合。native 模式为避免 `persist=True` tracker 串流而按 stream 创建独立 model/tracker，资源占用随活跃 stream 数增长。
- D5 输出只用于 D4/D6/D7 的证据、评估和上游复盘，不应被解释为自动处置命令。

### 14.4 P1 M5N2 视觉鲁棒性 replay（2026-07-12 已实现）

本轮完成 D5 模块侧的可重复 replay 支撑，不修改 main/runtime、D7 控制或 PNG/KF 公式：

- 关联历史按 resource/camera/assigned GlobalTrack 隔离，阻止跨相机 local ID 和丢锁窗口串联。
- 对同一 plan lineage 保存最高已接受版本，下降版本保守 `hold`；未授权或 track-version 不匹配的输入不会抬高 watermark。
- 无 measured detection 或仅有 predicted local track 时不授权；超过 0.25 s 输出显式过期/fail-closed evidence。
- 恢复观测必须重新满足马氏门、候选唯一性、身份冲突检查和两次 measured 稳定支持，MOT ID 变化不触发全局换绑。
- 专项测试覆盖 1-5 帧 dropout、同相机交叉、跨相机 1/2/3 与 2/3/4 式部分重叠、外参漂移、时间偏差和 stale plan。

该实现轮次验收结果为 D5 全量 `168 passed`。main 后续已运行 M5N2 paired AirSim；当前实测为 120 条 active-primary/visible、74 条 D5 关联/锁定证据和最佳 coalition completion 5/10。真实 detector/MOT、相机曝光/姿态同步和第二 primary 多 seed 阈值仍开放，不能用本轮合成 replay 代替。

### 14.5 P1 版本化 summary API/CLI（2026-07-12 已实现）

- `P1VisualRobustnessSummary`/`P1VisualRobustnessCaseResult` 固化 schema、profile 和逐 case 安全计数。
- `run_p1_visual_robustness_matrix()` 无随机数、无 AirSim 依赖，复用当前 D5 在线 API 运行 10-case 矩阵。
- `write_p1_visual_robustness_summary()` 和 CLI 写出稳定排序 JSON，重复运行字节一致。
- payload 同时携带 D6 readiness 兼容字段与 `metadata.case_results`；已用当前 D6 `--d5-summary` 实际加载并生成 aggregate/source manifest。
- truth/expected mapping 只在关联结果返回后离线比较；在线输入不携带 actor/object/truth/global label。

当前 API 结果为 10/10 case 通过、24 次预期保守拒绝、在线 truth 使用 0、全局 ID 改写 0，D5 全量 `171 passed`。下一步 main/D6 可把该 JSON 与真实 AirSim paired/multi-seed summary 并列，不得用确定性 fixture 代替真实持续 detect 和物理闭环。

### 14.1 M 对 N 计划内多机锁定（合同已实现）

专项调研见 `subagent_reviews/D5_M_TO_N_TERMINAL_MULTIVIEW_REVIEW.md`。当前主线继续使用中心航迹投影、像素马氏门控、本地 MOT 和跨视角稳定支持，不引入单一重型多视图框架替代现有合同。

2026-07-11 已按 D3 `assignment_plan_v2` 名称实现只读消费：`coalition_id/version`、`member_role`、`wave_id`、`required_resource_count`、`coordination_mode`、arrival window、`plan_id/version` 和 activation state 均由 `Assignment -> TerminalAssociation` 保留，detect-to-GlobalTrack registration binding 也携带同一合同。多个已授权且已激活成员锁定同一中心拥有 `global_track_id`，在联盟/计划版本一致且资源数不超过 demand 时记为 `planned_cooperative_lock`，不再仅因 locked resource 数量大于 1 设置 duplicate。第四个超额资源、联盟外或版本不一致、resource scope 不符、未激活成员、单资源多本地锁定及 local-to-global 多重绑定仍形成 conflict/duplicate evidence。

未激活 `reserve/retry` 的视觉候选不会被丢弃：D5 完成本资源/本相机投影与 MOT 配准后输出 `hold`，并记录原始视觉匹配状态、activation blocker 和 D7 visual PNG execution gate；默认 active primary wave-0 与 k=1 保持兼容。D5 不决定联盟、不裁减超额资源、不修改分配或全局 ID。

2026-07-11 已补 `CoalitionVisualSummary`、纯函数 `summarize_coalition_visual_completion()` 和 `TerminalObservationBus.coalition_visual_summary()`。接口只读消费单联盟 D3 guidance bindings 与当前/历史 terminal associations，输出 `primary_required_count`、`primary_locked_resource_ids`、`primary_lock_complete`、`reserve_ready_resource_ids`、`coalition_visual_consensus`，并保留 `planned_cooperative_lock`、duplicate/over-demand、版本冲突和 excess resource 字段。D3 guidance binding 未直接暴露总需求数时，接口以该单联盟 binding 数量作为 `required_resource_count`，`primary_resource_count` 仍由 D3 合同提供。

hybrid 默认稳定口径为：所有已授权 active primary 都必须在当前帧锁定，且每个 primary 至少连续 2 帧保持 execution lock，才设置 `primary_lock_complete=True` 和 `coalition_visual_consensus=True`。standby reserve 的本机几何/MOT 匹配可由 `hold + visual_match_decision_state=locked` 形成 `reserve_ready_resource_ids`，但不进入 consensus 或视觉 PNG 授权。resource/camera provenance 不一致、借用 bbox、无本机 local detection、计划/联盟版本冲突或联盟外执行 lock 均保守阻断。

连续两帧不再要求 plan/coalition version 完全相同。bus 会保存先前 binding 快照并逐帧验证两者严格单调上升；当前输出永远使用当前 binding 的 plan ID/version 与 coalition version，历史 association 仅贡献稳定计数。`coalition_id` 仍是不可变 identity，reserve 集合可变化但 primary 集合必须相同。metadata 输出 `stability_continued_across_plan_version_resource_ids`、`stability_reset_reason_by_resource`、`stability_source_plan_versions_by_resource` 和 `stale_plan_replay_resource_ids`。`clear()` 同时清理 observation、binding snapshot 和 invalid-version state，episode 之间不得串联。

2026-07-11 真实 AirSim 集成暴露 `TerminalObservationBus` 历史污染：旧实现的 `cross_view_associations()` 遍历全部 `_observations`，导致旧 timestamp/旧 plan 的 lock 被解释为当前并发 duplicate，进而向 D3 提供持续错误风险。现已增加可选 `as_of_timestamp`、`max_age_s`、`plan_id`、`plan_version` 快照作用域；作用域模式先做时间与计划过滤，再按 resource 保留最新 timestamp 的同帧全部观测，最后才运行 local/global duplicate 和 coalition 合法性判断。无参数调用仍保留离线兼容行为，`CrossViewAssociation.metadata` 可审计 scope 与筛选数量。main 应在每个 decision frame 使用当前 frame timestamp、约 `1.5 * dt` freshness 和当前 plan identity。

跨视角边界保持两层：已实现层只汇总各 resource-camera 独立完成的投影/MOT/锁定证据并解释联盟合法性；尚未实现层是带相机位姿/像素协方差的多视角 bearing 三角化、可观测度/PDOP 和融合协方差。同步帧可作为后续瞬时三角化输入；序贯帧必须按 measurement timestamp 运动补偿并膨胀协方差，历史支持不得冒充当前同步支持。OpenCV 是几何默认候选，ByteTrack 是本地 MOT 默认候选，BoT-SORT、ReST 和多视图 GLMB 只作为可插拔或研究对照。

### 14.2 真实 AirSim M=5、N=2 检测/几何历史基线（2026-07-11）

以下 `blocks_cv_m5_n2_cooperative_live_20260711` 记录是 commit-aware gate 和受控跨版本延续实施前的诊断基线，已被 1.2 节的 10-seed 当前验收取代，不得再解释为当前 T001 状态。

证据目录 `research_modules/airsim_runtime/outputs/blocks_cv_m5_n2_cooperative_live_20260711` 使用 5 个主 ComputerVision 相机、2 个二级相机和 2 个 `Quadrotor1` actor。7 个相机均持续返回 640x480 Scene 图像，但 `simGetDetections` 在每个 9 帧 episode 的前 8 帧均为 0；仅部分 episode 的末帧由 `Secondary_Recon_1` 返回 1 个约 7x7 px 的 bbox。full-flow D5 输出为 32 `reacquire`、4 `ambiguous`、0 `locked`。

D5 复核没有发现 bbox 解析或几何公式 bug。把唯一 bbox 与其真实来源相机 `Secondary_Recon_1:0` 的同帧外参配对后，`T002` 投影与 bbox center 误差约 0.09 px，几何关联正确选择 `T002`；该检测 `mot_history_length=1`，低于默认 2，因此 `ambiguous:mot_history_too_short` 是预期行为。日志中的 18-78 px 不是同相机标定残差：main runtime 在资源自有相机无检测时把全部 local tracks 作为 fallback，导致二级相机 bbox 被 4 个主资源用各自主相机模型重复评估。D5 只接受调用方提供的单 camera local-track batch，不能在缺少 resource-to-camera 映射时猜测或重绑来源。

当时的 main/runtime 修复建议（历史）：主资源无本相机检测时返回空 local batch，不得 fallback 到其他相机；二级检测必须使用二级相机模型形成 recon/cross-view evidence。AirSim 侧在 spawn 后同时尝试 actor exact name 与 asset mesh filter `Quadrotor1*`，并在 filter、actor pose 或 camera pose 更新后增加渲染 warm-up，再采集计数。专项验证时可临时 `--save-images`，验证后恢复默认不保存 PNG。

建议 main 修复 scope/warm-up 后运行：

```bash
python3 research_modules/airsim_runtime/run_blocks_sequence.py \
  --sequence-id blocks_cv_m5_n2_filter_probe \
  --cv-5v5 --resource-count 5 --target-count 2 --secondary-count 2 \
  --enable-cooperative-demand --high-threat-resource-count 3 \
  --cooperative-high-threat-target-count 1 \
  --duration 8 --dt 0.5 \
  --target-asset-name Quadrotor1 \
  --target-detection-filter 'Quadrotor1*' \
  --secondary-height-above-targets 50 \
  --save-images

jq -r '[.frame_index,.timestamp,.metadata.detection_count,
  ([.metadata.detections[] | .camera_vehicle_name + ":" + (.count|tostring)] | join(","))]
  | @tsv' \
  research_modules/airsim_runtime/outputs/blocks_cv_m5_n2_filter_probe/episode_006_full_flow/blocks_frames.jsonl
```

验收要求不是单个末帧偶发 detection，而是预期可见相机至少连续 2 帧 count>0；每条 terminal geometry record 必须同时记录且满足 `measurement_camera_id == projection_camera_id`。完成图像诊断后去掉 `--save-images`。

P1 补齐状态：

- 已完成 M-to-N 联盟视觉完成纯函数和 bus 薄封装，专项测试覆盖 hybrid 2+1、缺一个 primary、reserve-only、两帧稳定、版本冲突、跨相机 bbox 拒绝和 over-demand。
- 已完成 cross-view 当前快照过滤，专项测试覆盖同资源跨帧不 duplicate、旧 plan 多资源 lock 不污染新 plan、同帧当前 plan 非授权多 lock 仍 duplicate、授权 coalition 同帧合法，以及无参数历史兼容；实现当时的 D5 回归基线为 `127 passed`。
- 已完成 D5 侧 AirSim CV replay 可写盘字段：projected pixel、bbox center、pixel error、Mahalanobis、gate pass、candidate margin、measurement age、friend conflict、selected pair、`duplicate_terminal_lock_risk` advisory、`recon_cue_used_count` 和 visual PNG advisory metadata。main/D6 若需要实际 JSONL/CSV sink，应在 runtime/D6 owned path 接入这些 D5 输出字段。
- 已完成 D5 侧 multi-seed calibration readiness helper：`summarize_multiseed_calibration_readiness()` 对 `TerminalObservation` 和 `CrossViewAssociation` 做被动字段覆盖审计，输出每个 seed 的 `missing_required_fields`、`missing_recommended_fields`、source/backend counts、truth-label count、handoff/bbox-stability count 和 duplicate/friend conflict count。truth label 只作为离线 metadata 计数，不参与在线关联。
- 已完成 D5 侧二级覆盖/漏斗诊断 helper：`summarize_secondary_visual_coverage_funnel()` 输出 `not_all_targets_visible`、`network_union_incomplete`、`no_global_binding`、`reacquire_not_grouped`、`stale_or_missing_recon_cue`、`projection_invalid`、`geometry_gate_rejected`、`stability_window_failed`、`secondary_detect_offline_only` 和 `registered_to_global_track` 断点计数，帮助 main/D4/D6 区分“二级相机看见了目标”“二级网络并集覆盖了目标”和“D5 已形成全局 ID 支持”。
- 已完成 D5 侧 AirSim settings 驱动 detect-to-global-track registration helper：`register_local_visual_tracks_to_global_tracks()` 消费 `GlobalTrack[]`、D2/D3 binding/`Assignment`、每相机 `CameraModel(K/R/t)`、timestamp、像素协方差和 `LocalVisualTrack[]`，用像素马氏距离 + Hungarian 匹配输出 `DetectToGlobalTrackCandidate.outcome`、`TerminalObservation` 和 `CrossViewAssociation`；SciPy 不可用时退回确定性唯一匹配，同时保留 gated candidates 供 JPDA-compatible 下游使用。输出 records 携带 `detect_registration_outcome`、`detect_registration_reject_reasons`、projection reason、timestamp、measurement age、covariance/projection covariance summary 和 reasons，覆盖 `no_global_binding`、`stale_or_missing_recon_cue`、`projection_invalid`、`geometry_gate_rejected`、`network_union_incomplete`、`stability_window_failed`、`secondary_detect_offline_only` 和 `registered_to_global_track`。二级 detect 只能增加既有 `global_track_id` 支持，不能创建、重绑或使用 AirSim truth/actor ID。
- 已完成 main runtime P1 calibration sweep 和 D6 bundle 对 D5 evidence 的接线口径：D5 不启动 AirSim、不生成报告，但其 `TerminalObservation`、`CrossViewAssociation`、registration reason、secondary funnel 和 mobile gimbal metadata 已是 sweep/D6 统计的输入合同。
- 已完成 D5 侧机动侦察云台 cue evidence：`ReconImageCue` 与 coverage/cross-view summary 可携带 NED cue/look-at、云台 metadata、pointing/track error、`cue_source=radar_global_track_cue`、`capability_class=mobile_high_recon` 和 `coverage_mode=mobile_recon_gimbal`。历史 mobile recon stress 只保留为旧批次基线；2026-07-10 的 60-case sweep 已达到 `not_registered_count=0` 和平均 cross-view association `4.417`，当前主瓶颈转为同帧全目标覆盖、稳定支持和 D4 逐决策消费。
- 已完成 `TerminalConsistencySummary` 连续窗口修正：`TerminalConsistencyTracker` 按 `resource_id + assigned_global_track_id` 维护窗口，`assignment_version` 只做摘要审计字段。同一资源持续执行同一全局目标时，滚动 plan version 不会清空连续 `locked/ambiguous/hold/reacquire` 状态。
- 已完成 D4 evidence 输出：`CrossViewAssociation`、`DistributedTerminalAssociation.recommended_d4_action`、`duplicate_lock_resource_ids`、`hypothesis_only/hold/ambiguous` 原因和连续帧 `TerminalConsistencySummary` 均为 D4/D6 advisory evidence；D5 不触发降级、不生成 `AssignmentPlan`、不选择主备资源。
- 已完成 D7 visual PNG 前置证据：`annotate_visual_png_handoff()` 输出 handoff/prelock 建议、gate pass、blockers、measurement age、LOS availability、bbox stability、range band、timing 和 maneuver metadata；assignment mismatch、friend conflict、duplicate risk、unstable bbox、stale measurement age 或 missing LOS 都会阻断建议。
- 已完成 AirSim truth ID 在线隔离、YOLO/ByteTrack 离线 schema adapter 和 YOLOv8 frame adapter：AirSim `object_id`、`actor_name`、`truth_id`、`true_global_track_id` 或 `global_track_id` 输入字段不会进入在线关联；在线 category 只接受 `category/label/class_name` 或 detector `class_id + names` 映射，通用 `name/actor_name/object_name` 不影响 category、cost、binding 或 online metadata。本轮二级节点也先按 `simGetDetections` bbox/metadata 转 `LocalVisualTrack`，不启用 YOLO，且不会把 actor/truth alias 当作本地在线身份。truth 只允许进入离线 evaluator/metadata 统计。YOLO/ByteTrack row 或 frame adapter 输出只转为命名空间化 `LocalVisualTrack`，metadata 记录 confidence、class id、bbox scale、tracker backend 与 CPU/GPU budget，tracker ID 不替代 `global_track_id`。
- 2026-07-10 已闭合 active reacquire 友方声明复检 P0：候选在任何 `locked` 输出前复用 `IdentityChecker`，verified/stale/unverified/spoof-suspected 友方声明重叠均输出 `hold`，顶层与 search-window/candidate metadata 保留冲突状态和 reason；同一/新 MOT ID 回归均保持 `global_track_id` 不变。
- 2026-07-10 已闭合多相机 MOT 状态隔离 P1：fallback tracker 与 Ultralytics native model/tracker 按 `(resource_id, camera_id)` 持久化，提供单 stream 和全 episode reset API；交错相机、reset、native 成功及 native-to-fallback 回归均不串 ID/history。
- 2026-07-10 已闭合 D5 侧逐帧 D4 evidence P1：新增 `SecondaryFrameAssociationEvidence` 和 `build_secondary_frame_association_evidence()`，只消费同一 `frame_id`/timestamp 的 camera/network coverage 与当前帧 registration candidate，输出 D4 `TerminalAssociationSummary` 可直接消费的 coverage/full-view、stable/not-registered、cue freshness、gimbal 和 reject reason 字段。历史 candidate 只记 ignored count，混合 frame/timestamp 拒绝，禁止 episode 聚合冒充实时证据。
- 2026-07-10 已补齐 D5 YOLO/MOT adapter P1 元数据：默认优先 Ultralytics ByteTrack/BoT-SORT，依赖缺失明确 `unavailable`，detector 可用时提供 deterministic IoU fallback；输出实际 selection、processing latency、CPU/GPU budget comparison、observed device、camera-local continuity 和离线 detector recall/precision/FN/FP。离线 bbox 只在在线结果形成后评分，不携带 identity，也不影响 `LocalVisualTrack` 或 `global_track_id`。新增 5v5 多相机、交叉、短时遮挡恢复 fixture；本机 `best.pt` + Ultralytics 8.4.71 CPU 黑帧烟测可加载运行，因无检测按预期回退，不能替代真实目标多 seed 质量验收。
- 2026-07-11 已修复真实 AirSim YOLO/MOT 冒烟中的 bbox-only 离线标签解析：单个 `xyxy`、多个 `xyxy` 和 dict/object detection 均可进入 offline detector evaluation；畸形输入明确失败。该路径只计算聚合检测指标，不向在线 tracker 或全局绑定暴露身份。
- 2026-07-10 2v2 smoke 复核：2/2 资源对完成拦截，pair summary 的 D5 状态均为 `locked`，但 D7/main 因 `bbox_near_image_edge` 拒绝视觉接管 9 次、覆盖 2 个资源对，仅 2 个控制记录允许切换。该现象不要求放宽 D5/D7 门控；P1 需补充边缘裕量、连续边缘帧、相机指向误差和 handoff 抖动的多 seed 标定。
- 同一 smoke 的终端记录曾包含 `Interceptor*:0:MSM_TargetActor_*` 本地 ID。D5 sim-detection adapter 已过滤 actor/truth alias；main hotfix 已把 builtin detect 改为仅基于 bbox 的匿名 camera-local tracker，清理 intercept 注入和 D4/D5 fallback 的 actor-name local ID，并把 actor 名限制为 offline truth metadata。真实 AirSim 证据 `research_modules/airsim_runtime/outputs/p0_truth_isolation_smoke_20260710` 中三类 case 均 connected、各 5 帧，local/detection ID 无 actor 名，匿名 ID history 达 5，offline truth 标记正确且 cross-view association 均为 4。端到端 truth 隔离 P0 已闭合；D5 不越权修改 runtime，也不对任意既有本地 tracker ID 做字符串重写。

P0 状态：无 P0 blocker。active reacquire 友方声明复检、detection category/truth 隔离和端到端 AirSim actor-name local ID 隔离均已闭合。安全合同仍需持续回归：D5 不分配、不授权、不改写 `global_track_id`，在线逻辑不得使用 AirSim truth ID。

剩余 P1：

- M5N2 协同视觉闭合：2026-07-13 paired AirSim 已取得 120 条 active-primary/visible 证据和 74 条 D5 关联/锁定证据，但最佳 coalition completion 仅 5/10。下一验收聚焦第二 primary 的持续检测、bbox 稳定和 measured lock，将 `d5_not_locked` 与 `terminal_detection_acquisition_timeout` 分开统计，目标至少 8/10；不恢复同时到达要求，不降低安全门控。
- 真实 YOLOv8 + ByteTrack/BoT-SORT 多 seed：18-case screening 已完成；20 m native active/continuity 为 1.0、IDSW 为 0、P95 约 7.4/16.2 ms，但 precision/recall 仅约 0.26-0.33，30/50 m 无检测。先完成 bbox 定义/尺度/时间对齐和远距召回诊断；只有候选通过 screening 后才运行至少 10 seeds 的 confirmation，并由 D6 评估 IDSW/IDF1、遮挡恢复、`locked_mismatch`、false handoff 与 `terminal_id_switch_count`。
- 外参漂移与时间同步：P2 已完成合成扰动敏感性对照；P1 仍需针对真实 AirSim/replay 的 per-camera `K/R/t/dist_coeffs`、measurement/arrival timestamp 做多 seed 漂移与时延标定，统计重投影误差、马氏门控拒绝率、错误锁定率和恢复时间，不在 D5 内伪造同步后的真值位姿。
- 二级同 tick freshness：D5 frame-scoped DTO 和 D4 字段映射已完成；main/D4 仍需在同一 decision tick 消费该 DTO，并记录 threshold version、stale rejection、覆盖状态和接管迁移。不得使用 episode 聚合值回填，也不得让 D5 直接触发降级。

剩余 P2/P3（OpenCV 合成 calibration/`solvePnP` benchmark 已完成）：

- 在真实图像链路后评估 BoT-SORT、Deep SORT 和 ReID 是否适合小型无人机图像；用 IDF1/IDSW、遮挡恢复和算力预算决定是否只保留 ByteTrack + 几何门控基线。
- P2 接入真实身份源、密钥/证书和白名单运维；未知、过期、伪造或校验失败只能降低可信度，不能升级为敌方或锁定目标。
- P2 建立完整在线 PnP/PnP RANSAC、真实标定图像、畸变校正和在线外参更新链；P1 几何 drift 验收不以此为前置条件。
- P3 仅以离线 replay/对照研究 IBVS，D5 不实现视觉伺服控制器、不授权控制。
- P3 ROS 2 `tf2/message_filters` 只在项目进入 ROS 2 runtime 或 bag replay 后实施，目标是维护带戳 frame tree 和相机/航迹时间同步，不改变 D5 不改写 `global_track_id` 的边界。
