# D6 Evaluation Metrics Plan

## 2026-07-31 学习作用域归档原生审计

### 已完成

- [x] 保持 `ScopeEvidenceArtifacts(execution_plan_path, merge_dir, label)` 目录模式兼容，
  增加显式 `archive_root + archive_merge_dir` 模式；learned scope 与每个 R0 scope 独立选择
  存储方式，不按文件系统内容猜测。
- [x] CLI 增加 learned archive 参数和可重复 R0 archive 参数，并拒绝同一 scope 同时提交
  目录与归档存储输入。
- [x] 在 D6 `formal_shard_archive_audit` 中增加通用归档集合逐片入口，复用独立的 checksum、
  manifest、payload、计划绑定、inventory 和 tar 安全解析，不导入 main producer。
- [x] 精确校验归档子目录集合，允许普通 sidecar；缺片、额外目录、symlink、非普通项、
  payload 损坏和跨计划绑定均失败关闭。
- [x] 每次只恢复一个 shard；在临时目录清理前完成 shard plan/progress/checkpoint 语义复核、
  每个 cell 的既有学习证据审计和 D6 离线评价。逻辑 episode 路径不当作已 materialized 路径。
- [x] 复核 archive-native merge 的 scope manifest、cell CSV、episode index、archive binding
  和 D6 报告 binding；重复、漏失、乱序 cell 和 merge 篡改失败关闭。
- [x] 明确 archive-native merge 必须由 producer 使用 `write_d6_report=True` 生成。D6 只用
  该报告 bundle 复核执行计划、评价器来源和文件绑定，不采信 producer verdict。
- [x] 通用 archive-set 入口独立校验 `sharding` 映射、排除布尔值的正整数 `shard_count`、
  descriptor 数量、连续索引和 `shard_{index}_of_{count}` 身份，不依赖上游计划加载。
- [x] 保留模型 bundle、实际 assist adoption、在线真值隔离、物理结果、同键 R0 配对和
  非退化判据；不补零、不授予模型晋级或控制权限。
- [x] 公开每个 scope 的 `storage_mode/archive_root/verified_archive_count/`
  `peak_staged_shard_count/sidecar_files`。目录模式明确标记未执行归档验证。
- [x] D6 自建夹具覆盖 G1/A1/A2/A3/C1/F1、归档 R0、混合存储、sidecar 及指定失败关闭
  负例；测试专用耐久夹具另用真实 scalable-3D plan/shard/archive/merge producer 生成紧凑
  G1/R0 正例，明确覆盖 `write_d6_report=True`，且不 monkeypatch D6 验证器。
- [x] 2026-07-31 验证：学习专项 `68 passed, 1 warning in 8.35s`；learning/archive 组合
  `89 passed, 1 warning in 9.61s`；D6 全量
  `1330 passed, 1 warning in 120.34s`。

### 待执行

- [ ] main 在完整、clean、正式学习作用域生成后，为每个 learned/R0 scope 显式提供
  execution plan、archive root、启用 D6 report 写出的 archive-native merge 和对应 bundle；
  D6 再记录正式日期、scope/seed 数、逐 scope 归档计数、配对结果和失败原因。
- [ ] 正式学习变体尚未运行。开发夹具通过只关闭 archive 模式代码 P1，不能登记模型准入、
  非退化结论或控制许可。

## 2026-07-31 正式归档 full posterior

### 已完成

- [x] 在 v1 full posterior 配置中增加可选 `archive_root`，保持未配置时目录模式行为不变。
- [x] 增加 D6-owned 独立归档校验器，不导入或信任 producer 的 verified 结果。
- [x] 精确核对计划规定的归档子目录集合，允许归档根保留普通 pack/verify sidecar 文件；
  额外目录、任意符号链接和非普通项失败关闭。
- [x] 核对 checksum、manifest/payload、执行计划绑定、inventory 和 tar.zst 全成员；
  不安全路径、非普通文件、大小/摘要和确定性元数据错误均失败关闭。
- [x] 逐片临时恢复并复用 targeted posterior 低层审计，峰值 staging 为一个 shard；
  source/archive 不删除。
- [x] 独立复核 archive-native merge 的 manifest、cell CSV、逻辑 episode index、分片
  顺序/集合/cell_count binding 和 D6 报告 binding；core 文件、artifact 及父目录不得为
  symlink，五类报告逐文件复算路径、大小和 SHA-256。
- [x] 核对 D6 binding 中 evaluator schema、Git 提交、dirty 状态和源码树摘要，空容器、
  格式错误和类型伪造失败关闭。源码树摘要按当前 producer/evaluator 合同严格要求
  `sha256:<64位小写十六进制>`；不接受历史依据不明的裸摘要兼容。
- [x] 增加 archive 配置分派、有效归档恢复、payload/计划/path tamper、精确集合和 D6
  报告 tamper 测试。归档/full posterior 专项 `32 passed`，D6 全量
  `1297 passed, 1 warning in 114.12s`。
- [x] 对正式 10/20 归档做非破坏预检；普通 sidecar 被接受，预检只因缺 shard 10-19
  失败关闭。实际低层完成数和父矩阵完成数均为 0，未创建 merge 输出。

### 待执行

- [ ] main 完成 shard 10-19；现有 pack/verify sidecar 可原位保留。D6 随后对精确
  20-shard 子目录集合和 archive-native merge 执行正式 900-cell 审计。
- [ ] 正式运行后记录实际日期、producer/evaluator 提交、900 项通过数、严格身份可用性、
  失败原因和报告摘要。开发夹具结果不得替代正式结果。
- [x] `learning_scope_formal_audit` 的 archive 模式已由同日后续任务关闭，并覆盖
  G1/A1/A2/A3/C1/F1 与显式 R0；正式学习 scope 执行仍待 main 提供完整证据。

## 2026-07-31 正式分片预评估行合并

### 已完成

- [x] 增加 `write_report_bundle_from_rows()` 公共入口，接收
  `evaluate_scalable_3d_episode()` 的行并生成完整五类报告产物。
- [x] 让原 `write_report_bundle()` 只负责目录评估并委托新入口，阶段列、状态终结、聚合、
  性能证据和文件写出不再存在第二套语义。
- [x] 对预评估行执行当前 schema、内部阶段记录、来源、在线真值和严格身份必要字段检查；
  空输入、重复 episode、字段缺失和 schema 错配失败关闭。
- [x] 深拷贝调用方行后再补批次阶段列和终结状态，不原地修改输入。
- [x] 验证目录入口与预评估行入口的 CSV、aggregate JSON、性能证据 JSON、中文 Markdown
  和阶段耗时曲线一致。
- [x] 聚焦测试 `3 passed`，可扩展三维离线测试 `77 passed`，D6 全量
  `1277 passed, 1 warning`。

### main 开发集成状态

- [x] main-owned `merge_verified_formal_shard_archives` 已逐片调用
  `evaluate_scalable_3d_episode()`，保存评估行并在处理下一片前释放恢复目录。
- [x] main 已在全部开发分片处理后调用 `write_report_bundle_from_rows()`，并生成
  `archive_d6_evaluation_binding.json` 绑定五类报告和 evaluator provenance。
- [x] 开发测试已覆盖原 source 目录释放后仍可生成报告，证明最终写包不回读已释放 episode。
- [ ] 上述接线尚未用于正式 20-shard。shard 10-19 完成后仍需运行 900-cell full posterior
  与 post-run admission；这是正式执行 GAP，不是预评估行接口未接线。

## 2026-07-31 D4 历史候选源漂移处置

### 已完成

- [x] 保留绑定 `fd85745` 和旧 `region_resource.py` 摘要 `1b534b4...` 的 v4/v5
  配置及候选制品，不覆盖历史证据，不更新期望哈希。
- [x] 将真实历史 v4 测试改为断言当前源触发
  `source_current_file_differs_from_audited_commit`。
- [x] 将真实历史 v5 测试改为断言当前源触发
  `v4_source_external_anchor_mismatch`。
- [x] 使用 12 条训练样本和 1 条验证样本的受控内存夹具，独立验证重叠诊断不一致返回
  `validation_overlap_expected_crosscheck_mismatch`。
- [x] 保持生产源锚点检查顺序和失败关闭语义不变；未修改生产代码。
- [x] 运行三项专项测试和 D6 全量回归，结果分别为 `3 passed` 和
  `1274 passed, 1 warning`。

### 待执行

- [ ] D4 为当前安全门版本生成新的候选版本、clean 源提交、源实现摘要、源身份和完整
  实现文件摘要清单；不得复用 v4/v5 历史候选标识。
- [ ] D4 提供新候选树、模型状态、训练/验证数据及划分清单、构建配置和权限全关闭声明；
  若保留置信校准层，还需提供新的校准状态、校准摘要和开发门制品。
- [ ] D6 为新候选建立独立版本的调用方外部锚点、审计配置、审计报告和校验和，不修改
  2026-07-29 的 v4/v5 配置与报告。
- [ ] 新候选完成独立 holdout、运行时预检和正式准入审计前，保持未注册、未准入和规则
  回退。

## 2026-07-31 正式 R0 前 450 项严格身份重聚合

### 已完成

- [x] 将在线 D2 producer 诊断迁移到独立字段，保持在线无真值时的 unavailable 合同。
- [x] 将公共 `d2_id_switch_count` 固定为严格离线语义，只读取真值隔离 episode record
  及其绑定的离线身份制品。
- [x] 校验 episode/schema/context、两层 manifest、episode record、身份评价和四类源
  文件 SHA-256，并使用现有 D6 身份适配器重验后与持久化结果逐字段对账。
- [x] 对严格可用 0、严格可用非零、两类严格不可用原因、在线不可用但离线可用、
  episode record/identity manifest 哈希损坏和禁止零回填增加回归测试。
- [x] 正式 R0 full posterior 和实验矩阵 admission 只认可带严格来源、真值隔离、
  哈希验证和非回填声明的指标；来源提交和 evaluator 提交分别记录。
- [x] main 使用 D6 v12 evaluator `b6289c5` 重聚合 clean producer `80e55eb` 的
  shard 0-9，共 450 个 episode；派生输出与原 episode、冻结执行计划分离。
- [x] 复核 `450/450` 有限状态和严格制品哈希/合同；严格身份交换
  `414/450 available`、36 项失败关闭，可用项合计 893，169 项非零。
- [x] 保留 27 项一轨多真值和 9 项谱系窗口外观测的真实不可用状态，不补 0；在线
  producer 继续为 `0/450 available`。
- [x] 保留修复前 90-cell 的 `0/90` 错误汇总与 `73/90` 严格离线诊断作为历史证据，
  不再把原 135-cell 重聚合写成待办。

### 待执行

- [ ] main 完成 shard 10-19，使正式 R0 达到冻结的 900-cell 完整范围；450 项不得登记为
  full posterior 或完整矩阵准入结论。
- [ ] 900-cell 完整范围生成后，重新运行 formal R0 full posterior audit 和 post-run
  matrix admission，报告严格指标的 available/unavailable 分母及原始失败原因。
- [ ] 正式后续执行继续使用同一 v12 语义；G1/A1/A2/A3/C1/F1 不得读取在线
  producer IDSW 作为真值指标。

## 2026-07-31 高威胁 clean smoke 修复后复核

### 已完成

- [x] 只读复核 clean commit `b063535` 的 5/100/200 三档、seed `7/17`，共 6 个
  episode；42 个核心制品、配置哈希、有限状态和在线真值隔离均为 `6/6`。
- [x] 复核最终计划标识/版本/时期/租约及 49 个当前联盟目标均为 `6/6` 闭合。
- [x] 复核 10 次权威发布、10 个不同计划身份和 10 次运行时确认守恒；16101 条通信
  处置在 6 项中全部通过逐记录验证。
- [x] 按发布时序复核 12 条 D4 建议。发布时当前代为 12、旧代为 0，四个重规划项均
  补齐最终 v2 建议，最终计划建议覆盖为 `6/6`。
- [x] 低层 `formal_acceptance_eligible=6/6`，旧批次的
  `d4_advice_version_evidence_issue` 不再出现；未过滤旧记录、未放宽 D6 门。
- [x] 区分当前代故障诊断与旧代建议。10 条诊断均为 shadow、非 assist、正式决策未变；
  没有消费记录，控制采用保持 unavailable。
- [x] 生成修复后中文复核报告并同步 D6 模块与评审文档。
- [x] 6-cell 独立断言通过；低层、计划绑定、targeted/full posterior 四组专项测试
  `95 passed, 1 warning`。

### 待执行

- [ ] main 在存储保护线满足后冻结 clean source、execution plan 和 20-shard 布局，
  再启动正式 900-cell；6-cell smoke 不替代正式矩阵。
- [ ] D6 对正式 900-cell 运行 targeted/full posterior，逐 cell 复核同一低层门、计划
  绑定、联盟、通信和 artifact-tree 完整性。
- [ ] D2 继续补齐本批 3 项不可用的完整 ID Switch 证据；部分下界不得替代完整分母。
- [ ] 继续评估 100/200 规模非实时边界；两 seed、2 秒 smoke 不作为部署性能结论。

## 2026-07-31 高威胁 v5 时期租约复验

### 已完成

- [x] 只读复核 v5 五档规模、每档 20 seeds 的 100 个 episode；核心和离线消费制品、
  配置哈希、有限状态及在线真值隔离均为 `100/100`。
- [x] 复核最终计划标识/版本、时期、租约和当前联盟闭合均为 `100/100`；v4 的时期/
  租约 availability P1 在开发证据层关闭。
- [x] 复核 151 次权威发布、151 个计划身份、151 次运行时计划确认；同身份重复为 0，
  48 次评价刷新抑制不续租。
- [x] 复核 644 个当前联盟目标、28 个航迹回退 episode/391 个回退快照，以及
  195838 条逐消息通信处置。
- [x] 保留 D2 身份切换 `88/100 available`、可用部分合计 52；12 项没有补零。
- [x] 生成 v5 中文复验报告并同步 D6 模块和评审文档。

### 待执行

- [x] main/D4 明确建议 supersession 和发布时当前代次合同；v5 的 51 项旧计划建议保留
  为历史证据，`b063535` clean smoke 已验证发布时旧代 0、最终计划覆盖 `6/6`。
- [ ] 上游补齐 12 项 D2 身份切换缺失证据，D6 保持 availability 分母。
- [ ] clean smoke 已通过；在同一冻结合同上整体执行正式 900-cell R0。开发态 100 项不
  进入正式分母。
- [ ] 对 50、100、200 规模继续做性能剖析和部署处理器预算验证。

## 2026-07-30 高威胁开发态修复复验

### 已完成

- [x] 只读重算 v4 五个规模、每规模 20 seeds 的 100 个 episode；有限状态、在线真值
  零使用、最终计划标识/版本和当前联盟闭合均为 `100/100`。
- [x] 复核 151 次权威 D3 发布对应 151 个不同计划身份，同一
  `(plan_id, plan_version)` 重复权威发布为 0。
- [x] 复核 `payload_digest_mismatch`、`cross_binding_invalid` 均为 0；v3 三个最终
  快照断点在开发证据层关闭。
- [x] 逐消息处置 `100/100 available/verified`，195838 条记录与 episode summary
  对账一致。
- [x] 单列离线 D2 ID switch `88/100 available`、合计 52，12 项缺值保持 unavailable。
- [x] 形成中文专项报告，明确 dirty source、2 秒 episode 和非正式 R0 边界。
- [x] 更新真实 main 3v3 回归预期为单次权威发布/单次 ACK；定向测试 `12 passed`，
  D6 全量 `1263 passed, 1 warning`。

### 待执行

- [ ] D3 合同补充可比较的区域 epoch/lease 后，D6 才能把当前 `100/100 unavailable`
  转为可审计布尔值。
- [ ] 12 项离线 D2 ID switch 不可用样本仍需上游补齐谱系窗口和一轨多真值冲突证据；
  不得补零。
- [ ] 开发态通过后仍须在 clean source 上整体重跑正式 900 项；本批次不得进入正式
  分母。

## 2026-07-30 正式 R0 当前计划绑定审计

### 已完成

- [x] 新增独立离线审计器，以最后 D3 `plan_id/plan_version` 作为当前代次，不接受
  旧 D4 committed 状态替代当前计划。
- [x] 逐区域核对 D4 ownership 的计划身份；D3 合同提供 epoch/lease 时交叉核对，
  缺少比较依据时输出 unavailable。
- [x] 对当前计划多成员联盟核对 required/acked/missing、原子提交、执行授权和租约；
  `collecting_acks`、`proposed` 及其他未提交状态失败关闭。
- [x] 必需联盟分母按同目标当前 D3 资源数大于一，或同代 D4
  `commit_required=true` 确定；单成员 assignment 的 `coalition_id` 不触发提交要求。
- [x] 接入 targeted/full formal R0 逐 cell 门禁，输出 schema 升级为 v2，并在聚合
  中单列当前计划绑定、当前联盟提交和通信处置可用性。
- [x] 支持可选 `communication_dispositions.jsonl`。存在时严格验证逐消息处置，
  缺失时保留 unavailable，不从汇总计数反推消息级事实。
- [x] 覆盖同代通过、D3 v2 对 D4 v1 拒绝、当前计划 ACK 未闭合拒绝、proposed
  拒绝、epoch/lease 错代拒绝、通信处置文件缺失 availability，以及单成员
  `coalition_id` 与真实多成员目标混合合同。专项组合 `27 passed`，D6 全量
  `1261 passed, 1 warning in 128.21s`。
- [x] 只读核对 main runtime 已按 `(plan_id, plan_version, epoch)` 冻结租约，并写出
  `communication_dispositions.jsonl`；文件名、schema 和字段与 D6 消费合同一致。

### 待执行

- [ ] 在新的 clean source 和冻结执行计划上整体重跑 900 项 R0。不得只补 28 项，
  不得与旧来源结果拼接。
- [ ] D6 对新 900 项运行 v2 审计，发布逐 cell、按场景/规模/seed 聚合、失败原因和
  通信处置可用性。当前不得把代码就绪写成正式运行通过。

本轮没有读取 seed `1000-1019` 的新正式保留集，没有改写既有正式结果文件。历史
`872/900` 只保留为旧审计门禁下的基线。

## 2026-07-30 D4 v7 来源独立外部评价盲审

### 已完成

- [x] 固定 raw source、labeled export、labeled dataset、冻结 v4、v7 候选和 D4
  评价目录及其文件树摘要；输入为 M16N24、8 区域、64 episode、128 帧、seed
  `5216-5279`。
- [x] 核验 source/exporter clean commit
  `4a83a373f4eb4e29704bb3cf9f62e3d54eee3aec`、dataset/split、候选 bundle、训练
  审计和 v4 来源绑定。
- [x] 核验训练 `0-99`、正式留出 `1000-1019`、既有设计和评价
  `3000-3039,4000-4079`、pilot `5200-5215` 与独立评价 `5216-5279` 两两隔离。
- [x] 审计前后重算 raw source、labeled export、labeled dataset、冻结 v4 和 v7
  候选五棵输入树；五棵树均未变化。D4 评价树也保持不变。
- [x] 不调用 D4 v7 高层 evaluator，不采用其 summary 指标。D6 从冻结模型重新执行
  图推理、残差边激活和数量解码，再运行确定性 R0、投影和干预不变量。
- [x] 逐帧重算完整 R0 action tuple、raw activation、raw/projected transfer change、
  exact 正动作、negative exact-R0、错误方向/数量/边、虚假 transfer 和投影拒绝。
- [x] 独立重算 train/validation/test 样本 `90/20/18`、规则正类 `24/9/9`、负类
  `66/11/9`、原始激活 `10/0/0`、转移变化 `3/0/0`、精确正动作 `0/0/0`、
  负类精确 R0 `63/11/9`。
- [x] 确认三次转移变化均为 train 负类错误边和虚假转移；错误方向、错误数量、投影
  拒绝、不变量失败及原始 R0 动作元组偏差均为 0。
- [x] 重算冻结 v4 train+validation 的 425 帧/251 个唯一可观测键和外部
  128 帧/92 个唯一键，exact overlap 为 0；键不含 seed、episode、标签或真值。
- [x] 生成 D6 JSONL，并与 D4 JSONL 做逐字节对账；两者 SHA-256 均为
  `7785ded96360869edfb694c425321fa3323450cf1624607b53edf5d3eca6a5cd`。
- [x] 独立核对 D4 CSV、summary、input integrity、observable overlap 和 artifact
  manifest 的文件摘要、内容摘要与交叉绑定，mismatch 均为 0。
- [x] 固定模型拟合、检查点更新、阈值调整、置信校准、mutation、registration、
  admission、正式留出及 prior evaluation payload read 为 0。
- [x] 输出完整 JSON、LF split CSV、逐帧 JSONL、中文报告、`SHA256SUMS`、跟踪版
  紧凑结果和固定 config；不跟踪模型或大数据。
- [x] 结论固定为 `failed_closed`。candidate unregistered、admission closed、
  rule fallback required，全部运行权限为 false。
- [x] 命令行实际复跑得到相同 content SHA 和逐帧 JSONL；输出目录
  `sha256sum -c SHA256SUMS` 全部通过。
- [x] 专项测试 `11 passed, 1 warning in 4.65s`，D6 全量回归
  `1234 passed, 1 warning in 126.73s`；两个 Python 入口通过 `py_compile`。

### 当前边界

- [ ] v7 的 42 个来源独立规则正动作全部未命中，validation/test 没有产生转移变化；
  当前候选不得冻结或进入置信校准。
- [ ] train 的三次可执行差异全部是负类错误边，虚假 transfer 必须回到 0，才能考虑
  下一版本评价。
- [ ] 后续候选必须另立版本，并使用全新未见数据取得 validation/test 非零且充分的
  精确正动作命中；本轮 `5216-5279` 已读，不得复用为下一候选的独立评价集。
- [ ] 达到正动作和负类安全门前，不读取正式留出，不运行 runtime preflight、D3/D7
  许可、AirSim 或物理收益评价。

本轮关闭 D6 对 v7 来源、逐帧低层重算、D4/D6 JSONL 字节对账、完整 R0 动作元组、
错误转移分类和全权限失败关闭的审计实现缺口。剩余项属于 D4 后续候选能力及跨模块准入。

## 2026-07-30 D4 v6 来源独立盲审

### 已完成

- [x] 固定 M16N24、8 区域、64 episode、126 帧、seed `4016-4079` 的 source、
  标签导出、标签 dataset、冻结 v4、v6 候选和 D4 评价制品路径及 50 项摘要。
- [x] 独立核验 source commit
  `ed9e086ea8cf5c2138035f710cf4deb3e4a2801e`、exporter commit
  `9bdbe31dee34907525eabc9cf278e0d11f7dd88a`、dataset/split 和候选 bundle 绑定。
- [x] 核验训练 `0-99`、formal holdout `1000-1019`、旧设计/评价 `3000-3039`、
  pilot `4000-4015`、独立评价 `4016-4079` 两两无交集；在线 truth、旧评价和正式
  holdout 读取均为 0。
- [x] 审计前后重算 source、labeled export、labeled dataset、冻结 v4、v6 候选和
  D4 评价树摘要。六项一致，`input_mutation_count=0`。
- [x] 校验 D4 artifact manifest 的文件 SHA-256 与内容 SHA-256，逐项复核其六个
  artifact；D4 JSONL 与 CSV 的字段集合和 126 行值完全一致。
- [x] 不调用 D4 高层评价器，从冻结 v6 模型、确定性投影器、同快照 R0 和标签动作重建
  126 条逐帧记录。重算 JSONL 与 D4 JSONL 文件摘要完全相同。
- [x] 独立重算 train/validation/test 正类 `24/9/9`、负类 `65/11/8`、raw/projected
  transfer 全 0、精确正动作全 0、负类精确 R0 `61/9/7`、约束失败 `6/6/3`。
- [x] 将规则正类召回记录为可用的 `0/42`，将 actor-derived positive 分母记录为
  `0/unavailable/null`，两者不混用。
- [x] 重算冻结 v4 425 帧/251 个唯一可观测键、外部 126 帧/94 个唯一键，exact overlap
  为 0；键不含 seed、episode、目标标签或 truth。
- [x] 明确 v6 无置信校准器，禁止使用 manifest 中保留的 0.60 值执行 gate；置信门、
  admission、runtime preflight、D3、D7 和控制权限全部关闭。
- [x] 生成完整 JSON、LF split CSV、逐帧 JSONL、中文报告和 `SHA256SUMS`；跟踪固定
  config 和紧凑中文报告。
- [x] 专项测试 `8 passed, 1 warning in 5.20s`，覆盖 summary 篡改、哈希突变、
  unavailable 分母、test 正类独立计数、无校准器 gate 拒绝和 seed/truth 污染拒绝。
- [x] D6 全量回归 `1223 passed, 1 warning in 139.78s`；唯一 warning 是既有
  Matplotlib `Axes3D` 环境提示。

### 当前边界

- [ ] v6 在 42 个来源独立规则正类上精确命中为 0，当前 actor 不得冻结，不得继续进入
  置信校准。
- [ ] D4 需要另立候选版本，提高安全 transfer 正动作和困难负类覆盖；本轮
  `4016-4079` 不得复用为下一候选的独立评价数据。
- [ ] 新 actor 冻结后，先用全新未见 development 数据取得非零且充分的精确正动作命中，
  再建立只使用 train split 的独立置信校准器。
- [ ] 正类证据充分前不读取 formal holdout，不运行 runtime preflight、D3/D7 权限或
  AirSim/物理收益测试。

本轮关闭 D6 对 v6 冻结制品、逐帧动作、D4 artifact manifest、summary 独立对账、
seed/truth 边界和无校准器 gate 的审计实现缺口。actor 转移学习和来源独立正类泛化仍是
D4-owned P1；D6 继续保持只读和失败关闭。

## 2026-07-29 D4 v5 来源独立外部评价审计

### 已完成

- [x] 固定 M16N20、32 episode、63 帧的来源数据、标签数据、v4 actor 和 v5
  calibrator 路径及摘要；来源提交为
  `63987592c216fbdb7e03d77183afc6e9f15748a2`。
- [x] 复核训练 `0-99`、正式 holdout `1000-1019`、pilot `3000-3007` 和独立评价
  `3008-3039` 两两无交集；数据实际 seed 只来自 `3008-3039`。
- [x] 独立校验 source manifest、dataset、split、source artifact、evidence、export
  summary、label audit、v4/v5 文件树和候选交叉绑定。
- [x] 在审计开始前和全部加载、评分、observable key 重合计算结束后，重算 source、
  labeled export、labeled dataset、v4 actor、v5 calibrator 五个完整输入树。before/after
  摘要一致且 `input_mutation_count=0`；新增候选树执行期突变的稳定失败关闭回归。
- [x] 只语义读取外部 train/validation/test `43/10/10` 帧和旧 v4
  train/validation `350/75` 帧；旧 v4 test 与正式 holdout 读取均为 0。
- [x] 记录 main 此前 external test 读取 10 帧；该 split 明确为非正式 test，不是
  `1000-1019` 正式 holdout。
- [x] 在 D6 内独立实现可观测键、冻结 actor 消息传递池化、k=11 评分和动作签名匹配；
  不调用拟合、候选构造、登记、运行时预检或控制入口。
- [x] 重算旧库 425 帧/251 键、新库 63 帧/41 键，exact key 重合为 0。
- [x] 重算 train/validation/test 的规则安全正动作 `1/1/0`、actor-derived positive
  `0/0/0`、有限评分 `43/10/10`、0.60 通过 `0/0/0` 和负类误接收 `0/0/0`。
- [x] 将正类召回写为 `unavailable/null`，denominator=0；负类特异度为
  `63/63=1.0`；规则回退为 `63/63`。
- [x] 生成 JSON、逐 split CSV、中文 Markdown 和 `SHA256SUMS`，不覆盖已有目录。
- [x] 接管 main 的 CSV 行尾紧急修复：`DictWriter` 固定
  `lineterminator="\n"`。字节级测试要求 0 个 CR、文件以 LF 结束且各行无空格或制表符行尾；
  重生制品为 4 个 LF、0 个 CR。
- [x] 固定审计结论为 unregistered、admission closed、rule fallback required、
  production permissions disabled；D6 不生成权限或控制消息。
- [x] 专项测试 `5 passed, 1 warning in 2.33s`，D6 全量回归
  `1215 passed, 1 warning in 123.70s`；唯一 warning 与 Matplotlib `Axes3D` 环境有关。

### 当前边界

- [ ] 冻结 actor 没有命中两个规则安全正动作，来源独立正类召回分母仍不可用。
- [ ] 需要 D4 另行提供冻结、来源独立且能形成 actor-derived 正类分母的数据和候选；D6
  不调整当前 actor、0.60 门、split 或标签规则。
- [ ] 正类分母可用前不运行正式 holdout、runtime preflight、D3 successor 或 D7 权限测试。
- [ ] 本轮只建立负类拒绝证据，不建立正类泛化、运行收益、AirSim、实飞或生产能力结论。

本轮关闭 D6 对来源独立数据的哈希、seed、exact key、冻结评分、分母和回退状态审计实现
缺口。候选准入与正类泛化保持 P1 开放。

## 2026-07-29 D4 v5 记忆偏差与泛化审计

### 已完成

- [x] 增加独立只读 v5 审计模块、固定调用方配置、CLI、机器可读 JSON、中文报告和
  `SHA256SUMS`。
- [x] 固定 manifest file/content、state、summary、gate、builder source、v4
  manifest/model/dataset/split/tree、四个 v4 源文件和 v3 registry 外部锚；候选自签不能
  替换信任根。
- [x] 枚举并复哈希 v5 四文件闭包，拒绝 symlink、特殊文件、缺项、多余文件、普通字节篡改
  和同步自重签。
- [x] 复核 v4 180 文件树、v3 8 文件树、v4/v5 空登记常量和不存在的 registry 路径。
- [x] 逐字段检查 manifest/summary 权限全 false，candidate unregistered、admission closed、
  rule fallback required，formal holdout/preflight 未完成。
- [x] 只语义加载 TRAIN 350 条和 VALIDATION 75 条；TEST/formal holdout payload read/fit
  均为 0。v4 树审计对 TEST 文件只做字节哈希。
- [x] 从冻结 v4 actor 独立重建实际 24 维池化 latent、TRAIN 均值/标准差和 350 条归一化
  特征。state 数值最大差不超过 `1e-12`，标签逐项一致。
- [x] 记录 D4 报告/任务 64 维口径与实际 24 维冻结模型不一致，严格 profile 保持失败关闭。
- [x] 独立复算 k=11 逆距离评分和固定 0.60 门。TRAIN/VALIDATION 正类召回、负类特异度均为
  `1.0/1.0`，最小正裕量为 `0.4/0.209319`，Brier 为
  `0/0.000484791`。
- [x] 审计 TRAIN self-match：350/350 查询把自身放入近邻库；逐样本留一为
  recall `1.0`、specificity `0.993151`、Brier `0.006652708`。
- [x] 按 raw observable key 和 latent exact key 留组，同键副本全部从近邻库剔除；两者均为
  recall `0.965517`、specificity `0.958904`、Brier `0.037610440`。
- [x] 独立复算 VALIDATION overlap：exact `42/75`，非 exact `<1e-3` 为 20，
  `[1e-3,0.1)` 为 10，`>=0.1` 为 3，最近邻标签 `75/75` 一致，正类 exact `12/13`。
- [x] 输出全 VALIDATION、去 exact、距离 `>=1e-3`、距离 `>=0.1` 四层指标；分母小于 5
  时写 `unavailable/null`，不补 0。
- [x] 将结论分为 artifact/development integrity、fixed development gate、independent
  validation/generalization、admission 四层。开发门通过不产生泛化或准入。
- [x] 专项测试 `5 passed, 1 warning in 12.56s`，覆盖 TEST 语义读取阻断、普通篡改、同步
  自重签和诊断计数偏差。D6 全量回归为
  `1210 passed, 1 warning in 119.78s`。

### 当前边界

- [ ] 来源独立扰动集尚未提供。去 exact 后只有 1 个正类，不能计算可用的独立正类召回或裕量。
- [ ] 距离 `>=0.1` 只有 3 个负类，正类为 0；该层 recall、specificity、margin 和 Brier
  按最小分母合同均不可用。
- [ ] 64 维报告口径与实际 24 维模型不一致，D4 需自行修正文档或提供新的、外部固定的 64 维
  候选；D6 不修改 D4。
- [ ] formal holdout 和 runtime preflight 均未运行，候选未注册，全部 D3/D7/生产权限保持
  false。
- [ ] 当前候选只可作为 `development memorization baseline`。规则回退继续为 required。

本轮关闭 D6 对 v5 固定字节、算法复算、记忆偏差和重合分层的审计实现缺口。独立泛化、
正式准入和运行收益仍为 P1 开放项。

## 2026-07-29 D4 v4 未注册候选独立审计

### 已完成

- [x] 增加独立只读审计模块、CLI、固定 reference 配置、机器可读 JSON、中文报告和
  `SHA256SUMS` 输出。
- [x] 以调用方固定的 manifest content、model state、dataset 和 clean source commit
  作为外部锚；候选自签声明不能替换信任根。
- [x] 枚举候选 180 文件和 4 个目录，逐项复算 179 个 artifact SHA-256，拒绝清单缺项、
  多余文件、symlink、特殊文件、模式和摘要漂移。
- [x] 从 commit blob 独立复核 4 个 source implementation 文件；当前只读实现与冻结
  commit 内容一致，当前 HEAD 差异不被当作候选来源身份。
- [x] 交叉绑定外部 evidence、source derivation、export summary、dataset、split 和
  train/validation episode inventory。
- [x] 只读取 train/validation payload。train 为 70 seeds、140 episodes、350 samples，
  目标正/负 `60/290`；validation 为 15 seeds、30 episodes、75 samples，目标正/负
  `15/60`。test manifest 为 15 seeds、30 episodes、74 frames，payload read/fit/weight
  fit 均为 0。
- [x] 验证 truth identifier、future outcome、reward 以及 formal holdout seed 使用均为
  0；所有 train/validation 输入与模型参数有限。
- [x] 从 train 库存独立复算 actor/confidence 类别权重，并重放 actor epoch 107、
  confidence epoch 66 的 checkpoint 选择和固定 0.60 门结果。
- [x] 记录 actor train/validation 正负召回，以及 confidence 正类召回、负类特异度、
  Brier 和薄裕量；最小越门裕量为 `0.000504935`，train 最接近门的负类裕量为
  `-0.000029838`。
- [x] 将固定 development fixture 分类为 `training_domain_smoke_only`；confidence
  `0.602367163` 不产生泛化或正式验证结论。
- [x] 复核 v3 registry 8 文件树未变，v4 注册常量全空且 registry 路径不存在；全部权限
  false，候选保持 unregistered、admission closed。
- [x] 增加 artifact 字节篡改和自重算 manifest 的权限声明篡改负例，两者均失败关闭。
- [x] 将 TRAIN-domain fixture、低 confidence 正类召回、薄越门裕量和 runtime
  outcome/benefit unavailable 显式加入 admission blocker；开发完整性状态保持通过。
- [x] 最终输出 JSON content/file SHA-256 为
  `3a4ed311c55e6419d3db1b3ba830f0ea6ce22c638eb363aa03c3f4510fdcd7c2` /
  `e225a1a16ae2b1988ce5ea34b3cceaa30d7c829004663368ecc6514de3eb3887`；
  Markdown/`SHA256SUMS` 文件 SHA-256 为
  `16a2e5a4efacd4b58b22b7b9dd9d0d632cedb3e7b8d6cc6d55a0dce954870fe0` /
  `6ee4e7822800401b531acc93f03f105fc1ff02a77c1842fe1d36546bc9500af6`。
- [x] 专项测试 `3 passed, 1 warning in 4.97s`；D6 全量
  `1205 passed, 1 warning in 112.59s`。

### 当前边界

- [ ] formal holdout evidence 未完成，本轮 formal holdout seed use 为 0。
- [ ] runtime preflight 未完成，固定 0.60 gate 未登记为运行门。
- [ ] v4 候选未注册，正式准入保持 closed，rule fallback 保持 required。
- [ ] development fixture、train/validation 指标和零已观测负类越门均不能建立独立泛化、
  正式收益或生产权限。
- [ ] confidence 正类召回和门限裕量偏薄；机器可读输出保留
  `thin_margin_warning=true`。
- [ ] runtime outcome 和 benefit 仍 unavailable。

本轮关闭的是 D6 对固定 v4 候选的开发完整性、数据用途和指标独立复算缺口。没有执行正式
holdout、runtime preflight、登记或权限变更。

## 2026-07-29 D4 readiness-v3 v2b 隔离证据

### 已完成

- [x] 增加 v3 紧凑证据审计 adapter、CLI 和原子输出，外部固定 `SHA256SUMS` 摘要。
- [x] 拒绝文件篡改、缺 seed、重复 seed、初态/外生配置不一致声明、在线真值、非有限值和
  生产权限冒充。
- [x] 分离开发 ACK、生产 authority、D4→D3 谱系、ACK/D7 摘要和严格同链可用性。
- [x] 20v20、8 区域、10-seed 审计完成：D3 后继 1/10，开发 ACK 1/10，有界非退化
  10/10 可评价并通过，正收益 unavailable/false。
- [x] 增加同 plan identity refresh 丢失 authority epoch/lease 的失败关闭回归；不放宽
  `runtime_plan_outcome_join`。
- [x] 将最终来源 schema 收紧为
  `scalable3d-d4-v3-isolated-rollout-v2`，精确验证 11 个关键实现文件、episode manifest
  和 implementation-set 摘要；v1 默认拒绝。
- [x] 增加 full-episode chain adapter、CLI、原子 JSON/中文 Markdown 输出；动态文件清单
  要求全量根摘要绑定，并独立重算 control/treatment runtime join。
- [x] 最终 v2b seed 2007 已验证同身份 refresh 保持 authority epoch/lease 和严格执行
  签名；D4→D3 successor→ACK→D7 指令同链成立，全部生产权限保持 false。
- [x] 保持通用 runtime join 默认行为与冻结 persisted 18/19 语义逐字段一致；新增默认关闭的
  D2 v2 evaluator-only bounded coast helper，仅由 full-chain audit 显式启用。
- [x] seed 2007 的 `GT3D-000004` confirmed/unmatched 单帧空档由
  `0.833472220197s` 与 `1.236148794089s` 同 truth 双锚界定，锚间隔
  `0.402676573892s <= 0.9s`；原生 18 + bridge 1 = effective 19/19。
- [x] 桥接路径拒绝跨 schema、lost/dropped/tentative、错误 reason、非空候选/观测/lineage、
  异 track/truth、超时、缺锚、缺 hash/lineage、uncommitted、ambiguous 和竞争 claim；
  不写回 D2、不改 `global_track_id`，在线暴露与生产权限保持 false。
- [x] 2026-07-29 全量 D6 回归 `1196 passed`；重生 full-chain JSON/中文 Markdown/
  `SHA256SUMS`，输出清单摘要为
  `6201eed6f7bcb6396c33631fe484d452cc050c630b5fb9783c11fde0ecf00199`。

### 剩余 P1

- [ ] 候选需产生与规则控制臂不同、且被 D3 合同消费的可辨识动作，随后再评价正收益。
- [ ] compact 10-seed 只提供摘要，不能替代每 seed full-chain replay；若需要 10-seed
  ACK/D7 物理链覆盖率，main 需保留相应完整 episode。

冻结 runtime join 中原生 18/19 仍是上游事实；本次只关闭 D6 对该精确单帧空档的离线评估
覆盖缺口，不把 evaluator bridge 解释为 D2 在线身份恢复。

## 2026-07-28 D4 A2 可信来源与严格配对

### 已完成

- [x] 增加
  `d6.learning-run-d4-a2-current-lineage-model-source-reference.v1`。D6 从固定候选的
  原始制品重算 commit/tree、文件和内容摘要、split 使用、模型加载、参数有限性及 false
  权限，不接受调用方自报 facts。
- [x] reference 和专项测试改用受版本控制的
  `research_modules/d4_distributed_fallback/model_registry/region_resource_a2_current_lineage_development_v1/`。
  已核对该目录与冻结候选逐文件一致，不再依赖 gitignore 下的 `outputs/`。
- [x] 固定候选身份：clean commit
  `b0d498d9e76e19e9045e127b6dae26ea164b3fa4`，候选清单文件 SHA-256
  `7cc10ad770bd95fcb813dbf3d16b17040ec5f41f80fe0dc53e3e291a32f4de64`，权重
  SHA-256 `fd1b9c4cf7580083fadc04a70b87aa6439930eba764a970279611ccc57f30047`。
- [x] readiness 升级为 v3，分别输出 `model_source_verified` 与
  `runtime_distribution_compatible`。来源通过不改变 `development/shadow` 生命周期。
- [x] 增加 shadow 原始记录适配器，按总量和 seed 重算受审/有限/OOD 快照、模型动作、
  动作缺失、规则回退、逐特征原因和候选绑定。
- [x] 修正四层语义。分布兼容只由样本、有限性、feature OOD 和分母守恒决定。动作、非零
  干预和 fallback 只作 rollout 诊断；实际 treatment 由 strict adoption 链决定。
- [x] D6 确定性合同 fixture 的 5 资源/5 目标、2 区域、6 帧保持拒绝：6/6 OOD。模型动作
  0 和规则回退 6 只属于该 fixture 的独立诊断，不作为 main 运行证据。
- [x] main 实际预检单独记录：5 资源/5 目标、2 区域、seed 2000 为 3/3 OOD；
  200 资源/200 目标、8 区域、seed 2001 为 2/2 OOD。
- [x] 增加 A2/R0 严格配对审计。冻结注册、执行先后、同配置异 episode/日志、固定模型
  非零干预、D3 严格后继、runtime/owner/coalition ACK、确认后物理窗口、truth-use=0、
  有限状态和完整分母均为硬门。
- [x] 增加分布内 no-op/规则回退正例。该例
  `runtime_distribution_compatible=true`，但 rollout 前置条件、treatment、adoption 和
  paired readiness 均 unavailable。
- [x] 定向测试 `38 passed, 1 warning in 6.10s`；D6 全量
  `1144 passed, 1 warning in 108.47s`。

### 待补输入

- [ ] main/D4 调整运行特征或重新训练候选，使正式预注册快照无 OOD。当前 main 实际预检
  的 3/3 与 2/2 OOD 均不能进入后续配对；D6 的 6/6 OOD 只作合同回归。
- [ ] 生成至少 20 个执行前冻结注册的真正未见 seed，并保存完整逐 seed shadow JSONL。
- [ ] 在兼容分布上产生至少一个可辨识非零模型动作。分布内 no-op 合法，但不满足 rollout
  treatment 前置条件。
- [ ] 为每个 seed 保存实际采用记录、D3 strict successor、runtime/owner/coalition ACK 和
  确认后的物理窗口；fallback 和普通规则重规划继续排除。
- [ ] 为每个 candidate episode 生成独立 R0。两臂外生配置摘要相同，episode 与事件日志
  不同。
- [ ] 提供候选/R0 指标的分子、正分母、值、方向和容差。缺指标或分母不相等时保持
  unavailable。
- [ ] 完成 20-seed 聚合后再报告非退化。结果不产生 admission、assist、authority、
  assignment、failover 或 control 权限。

## 2026-07-28 G1 模型来源适配器

### 已完成

- [x] 新增
  `d6.learning-run-d5-g1-model-source-reference.v1`。reference 只携带 G1、
  `d5_graph`、13 项原制品相对路径、文件 SHA-256 和自身内容摘要，不接受 facts、formal
  或权限声明。
- [x] 固定正式 D5 v5 模型身份、制品布局、external audit v2、post-assembly audit v2、
  held-out、paired-shadow、lineage 和 clean runtime 实现谱系。完整但未登记的替代模型不能
  通过自签 sidecar 建立信任。
- [x] 在显式 `artifact_root` 内解析并复哈希 sidecar 引用，复用
  `audit_d5_g1_external_evidence()` 和 `audit_d5_g1_post_assembly_bundle()` 重算事实。
  persisted audit、bundle 内嵌 audit 与重算结果必须一致；审计前后再次复核原制品和实现文件。
- [x] 使用
  `/tmp/MSM-d5-g1-formal-evidence-8d5e02e-20260727` 完成一次真实只读正向验证，clean
  source 为同级 `/tmp/MSM-d5-g1-formal-8d5e02e`。验证结果为正式装配后审计、
  `component_ids=[d5_graph]`、`audit_passed=true`，模型指纹为
  `sha256:7fb5db8b6099ca4da5706a3bec53ff7cd634e8bd267c036ce3ee4ee4bf71ca71`。
  适配器没有扫描或修改 `/tmp`。
- [x] 仓库根作为 `artifact_root` 时保持失败关闭。reference 约定的 13 项原制品不在仓库
  根，不使用仓库内 audit JSON 替代原生产链，也不自动回退到外部目录。
- [x] 专项测试 `14 passed, 1 warning in 3.07s`；与 readiness v2 聚合测试合并为
  `32 passed, 1 warning in 8.16s`；D6 全量为
  `1138 passed, 1 warning in 126.65s`。warning 为既有 Matplotlib `Axes3D` 环境提示。

### 当前边界

- [x] G1 `model_source` 软件 adapter 缺口关闭。现有可信来源 adapter 为
  `frozen_unseen_seeds` 和 G1 `model_source` 两类。
- [ ] 当前尚未形成把 reference 与完整 readiness manifest 一同置于显式外部根的正式
  readiness 制品。真实只读验证证明 source adapter 可复算，不等同于六变体正式准备度完成。
- [ ] G1 的 `identifiable_adoption`、`runtime_ack`、`physical_window`、`same_key_r0`、
  `paired_non_degradation`、`truth_use`、`finite_state` 和 `external_permission` 八门仍
  unavailable。模型审计中的零在线真值特征和有限输出不能替代同一运行采用链的受审分母。
- [ ] C1/F1 仍要求 D3、D4、D5 图关联和 D5 主动视觉四组件完整覆盖。单独的
  `d5_graph` model-source 证据按组件不足拒绝。
- [ ] D3 公共
  `load_a1_isolated_intervention_batch()` 已可严格验证 A1 candidate/selection 清单，但其
  公共结果明确不证明计划发布、实际采用、运行 ACK、物理窗口或同键 R0。readiness
  `identifiable_adoption` 要求实际采用、可辨识变化和 binding change，当前没有安全的字段
  映射。本轮不增加 A1 gate adapter；后续可先定义独立的
  `candidate_selection_inventory` 前置证据层，再与同一运行谱系的采用记录联接。

## 2026-07-27 正式学习运行准备度审计

### 已完成

- [x] 将 readiness 合同升级为 v2。manifest 每个 gate 只保留相对制品路径和文件
  SHA-256，不再接收来源类别、formal 标志或调用方自报 facts。
- [x] 撤销十类通用 gate wrapper 的 formal 信任和公共 builder。摘要正确的
  `d6.learning-run-*-evidence.v1` 自签文件不能进入 readiness。
- [x] 首批只接入冻结未见 seed gate。reference sidecar 显式绑定训练 seed 注册表、共享
  split 注册表以及 D3/D4/D5 四个数据集 manifest，逐文件校验 SHA-256 后调用现有
  `audit_canonical_seed_split_readiness()` 重算 seed 数、训练交集和模块 split 一致性。
- [x] 将 manifest 所在目录作为显式只读制品根。绝对路径、`..` 逃逸、目录、缺文件、摘要
  错配、未知 schema 和缺制品根均失败关闭；不扫描邻近目录补找证据。
- [x] 输出升级为 `d6.learning-run-readiness-audit.v2`，consumer 升级为
  `d6.learning-run-readiness-consumer.v2`，保留严格输出复载和小型 JSON/中文
  Markdown/校验和 writer。
- [x] 对 `G1/A1/A2/A3/C1/F1` 固定输出模型来源、冻结未见 seed、可辨识实际采用、运行
  ACK、物理窗口、唯一同键 R0、成对非退化、truth-use、有限状态和外部权限十类门。
- [x] 缺项使用 `availability=false + null + exact reason`；已有但不合格的证据使用
  `availability=true + passed=false`，不把 unavailable 补为 0。
- [x] 将模型、运行证据、正式证据和执行启动四层分离。磁盘与外部权限只进入最后一层，
  不改变模型或算法结论。
- [x] 固定正式运行最低可用空间为 `20 GiB`，不接受调用方下调。当前约
  `13.168 GiB` 且无第二大容量挂载点，执行保持失败关闭。
- [x] 模型、采用、ACK、物理窗口、同键 R0、非退化、truth-use、有限状态和外部权限九类
  gate 暂无 readiness 受信 adapter，统一 unavailable。D6 输出中的模型晋级、分配、接管、
  相机和控制权限始终为 false。
- [x] 新增 18 个临时 producer/攻击/命令行测试。正例经过既有 canonical seed auditor；
  攻击例为每个变体构造十个文件/内容摘要均正确的旧通用 wrapper，正式准备度仍全部
  unavailable。其余负例覆盖原制品与 sidecar 篡改、摘要错配、未知 schema、缺文件、内外层
  路径逃逸、目录、缺根和输出语义篡改。

### 当前阻断

当前六个变体的 `formal_evidence_readiness` 均为 unavailable。canonical seed adapter 通过
只关闭冻结 seed 单门，不提升模型、运行证据或执行准备度。

- [ ] 为 G1 已有 external audit/post-assembly 原制品建立严格 model-source adapter；在此
  之前 held-out/paired-shadow 只保留在独立审计报告，readiness 模型门 unavailable。
- [ ] A1 使用具备生产准入的候选，在冻结未见 seed 上产生可辨识最终绑定变化，并闭合
  runtime ACK、物理窗口和同键 R0。当前 0/20 binding change 不满足该条件。
- [ ] A2 产生非零、受约束且可因果归属的区域干预。开发无操作和 development-only
  `request_replan` 不能进入正式分母。
- [ ] A3 在 clean source 下持久化完整候选 disposition 和 paired evidence，修复 4 条通信
  缺失后仍需证明未见 seed、物理窗口、唯一 R0 和非退化，不能使用零丢包对照替代。
- [ ] C1/F1 待四个组件各自满足模型与运行证据门后，再生成复合采用、复合 ACK 和同键
  R0 证据。当前不得以单组件通过推导复合准入。
- [ ] 逐项为既有严格 producer/auditor schema 增加 adapter。采用、ACK、物理窗口和同键 R0
  必须从同一版本化运行链重算；不能分别引用互不关联的通过摘要。paired non-degradation、
  truth-use、finite-state 和 external authority 同样需要原制品 loader。
- [ ] 由项目外部授权流程提供逐变体权限决定；D6 不承担该步骤。
- [ ] main 提供不少于 `20 GiB` 的正式输出空间或明确的外部归档挂载点后，才能重新检查
  execution startability。保护线不因压缩比下降。

本计划不包含日志压缩实现。单个 delayed-noisy R0 episode 的三份重复 JSONL 原始约
`55.7/37.4/3.5 MB`，流式 gzip-6 约 `13.0/11.4/0.49 MB`，这些数据只说明后续容量治理有
收益，不能替代当前存储保护门。

## 2026-07-27 A1/A2/A3 实际采用与同键配对审计

### 已完成

- [x] 增加统一的只读输入、输出和 consumer schema，精确限制顶层字段并重算
  `content_sha256`。
- [x] A1 复用 D3 公共 strict validator，校验 candidate、selection、publication、lifecycle
  及其候选摘要、计划摘要和注册摘要绑定。
- [x] A2 使用 D4 公共数据对象和严格 `from_value()` / `from_dict()` 接口逐层重建安全采用
  证据，要求与 `to_dict()` 精确往返，并复核后继计划、运行确认、权属确认、联盟确认和物理
  窗口的交叉绑定。
- [x] 对 D4 pair wrapper 实施两遍审计：先严格重建并按内容摘要索引旧安全采用记录，再使用
  `safe_adoption_evidence_sha256` 调用真实 D4 public validator。被引用旧记录不重复计数，
  未引用旧记录保持兼容口径。
- [x] 对齐 D4 投影后拒绝语义。结构合法的 `safe_adoption_rejected` 可确认实际采用数为 0；
  必须保留有效 preparation、投影和非空拒绝原因，并禁止携带 D3 后继计划、运行确认、权属
  确认、联盟执行证据或物理窗口。后三层计数和全部权限保持不可用或 false。
- [x] 兼容真实 `RegionResourceA2BenefitAuditInput` 和
  `RegionResourceA2BenefitAuditBatch`，并独立核对候选物理窗、同键身份、冻结外生摘要、
  episode/事件日志和 R0 唯一性。
- [x] A3 复用 D5 公共 strict validator，校验实际模型命令、运行确认、相机位姿反馈、后续物理
  观测窗口和唯一同键 R0；批次层新增跨 episode 事件日志绑定和 R0 单次消费检查。
- [x] 新增 strict input v2 的 `a3_pairing_dispositions`。旧 v1 构建调用保持不变；输出和
  consumer 先显式升为 v2，并对 v1 输入报告 disposition inventory unavailable。
- [x] 消费 D5 pairing disposition v2 的 `candidate_stage_reason_codes` 与
  `candidate_stage_evidence`。D6 输出和 consumer 升为 v3，同时保留 D5 disposition v1
  顶层原因兼容；v1 缺少的阶段细分计入 unresolved，不补零。
- [x] D6 输出和 consumer 升为 v4，新增
  `observation_outcome_inventory`。候选观测证据可用、覆盖率为 0、正收益未声明和权限全关
  分开表达；D5 v2 零检测帧只能计入 reacquire，不能计入 locked/ambiguous 或可见引用。
- [x] 逐条调用 D5 公共 disposition validator，复核精确字段、内容摘要、唯一 trace、pairable
  与顶层 A3 证据一一对应，以及嵌套/顶层 paired evidence 完全相同。
- [x] 输出候选数、pairable/unpairable 数、覆盖率、reason code 计数、inventory completeness
  和 paired-evidence completeness。合法 unpairable 保留完整原因，但 A3 四级执行/收益计数
  失败关闭，完整模型证据声明固定为 false。
- [x] 分开输出顶层原因和候选阶段细分原因。重算阶段证据有/无记录数、细分原因记录数与
  多标签 assignment 数、全局细分分布、顶层到细分矩阵，以及候选物理窗口缺失的
  scope/evidenced/unresolved/completeness。
- [x] 新增当前 v3 输出 strict loader。输入与输出均支持 JSON round-trip；未知/重复细分、
  细分与哈希绑定阶段证据不一致、schema/顶层/细分计数不守恒及重算摘要后的输出篡改均失败
  关闭。
- [x] 对未知字段、摘要篡改、在线真值或 outcome 泄漏、synthetic fixture、重复 comparison
  key、跨键 R0、证据复用和权限越界提供失败关闭路径。
- [x] availability 与四类计数分开记录。规范输出为 `benefit_auditable_count`，并保留旧字段
  兼容别名。完整配对只表示 `audit_input_available`，正收益和非退化声明固定为 false。
- [x] 支持显式读取多个 `learning_adoption_evidence.json`。逐文件校验 schema、唯一
  `episode_id` 和内容摘要，并要求 D4/D5 wrapper 引用的候选/R0 episode 文件实际存在；
  D4 候选 execution arm 还必须匹配安全采用记录所在 episode。D6 不扫描目录、不自动拼造
  pair wrapper。
- [x] A3 不再访问 trace 不存在的派生 `comparison_identity`；改由 trace 的场景、规模、seed、
  窗口、相机、资源、目标引用、冻结外生摘要和三类版本显式重算，再与窗口公开身份比较。
- [x] A3 事件日志按 episode 级身份审计。同一 episode 多窗口可共享一个日志摘要；同一摘要
  不得跨 episode，同一 episode 不得声明第二个日志身份。
- [x] 公共模块解析兼容安装/`PYTHONPATH` 顶层包和仓库根目录 `research_modules...` 两种
  布局。只有请求模块路径缺失才回退，真实内部依赖错误保持可见。
- [x] strict audit 专项测试增至 59 项，直接使用 D4/D5 生产装配器，覆盖旧兼容、缺窗、身份/汇总篡改、
  R0 重复使用、跨 episode 来源、A3 同 episode 多窗口日志身份，以及投影后拒绝态的四类
  正反例和 disposition inventory 的正向、缺失、重复、篡改、错配、守恒测试；新增 D5 v2
  细分正例、D5 v1 兼容、输入/输出 round-trip、未知/重复/矛盾细分及输出计数篡改负例。
- [x] main 已用 seeds 1000-1019 运行 A2 开发批次。20/20 个候选均被评估，可识别区域干预、
  实际采用和 A2/R0 收益审计均为 0，原因均为
  `identifiable_regional_intervention_missing`；无操作没有被归因为学习采用。批次 SHA-256 为
  `ff3c10a089b6a94582451ae05d8a884af3a2bd7485acd4df0496442ea7e0ec55`。
- [x] main/D5 已为同一批 seeds 提供完整 A3 disposition inventory。536 个候选中 152 个
  pairable、384 个 unpairable，覆盖率 28.36%，全部不可配对原因均为
  `candidate_physical_window_missing`。完整清单下 `a3_auditable_pair_count=0`，四级计数
  unavailable；批次 SHA-256 为
  `455d181076553a485ff824618abc6d037a4477bb6342877d1d1e427fd28583a9`。
- [x] main 以同配置 seeds 1000-1019 完成 A3 候选阶段不落盘开发探针。536/536 个候选具备
  stage evidence，152 条 pairable、384 条 unpairable，完整可审计 seed 为 0。多标签细分为
  anonymous observation missing `344` 和 physical window confirmed missing `344`。其余
  40 条 observation inventory 不完整但 stage reason 为空，D6 保留为 physical-window
  missing detail unresolved；对应 scope/evidenced/unresolved 为 `384/344/40`，detail
  completeness 为 `false`。ACK、确认、命令过期、时序错配和相机反馈缺失均为 0。摘要
  SHA-256 为
  `1ba6040e7c3e7e3b9e7d5506dfd20cf3539ce12c5aac13cca7f02799f0cd99ef`。
  该探针保持 `source_worktree_clean=false`、`formal_evidence=false`、
  `persisted_full_pair_inventory=false`，不替换冻结 v1 批次。
- [x] 本次 v3 修改后，D6 strict 专项为 `59 passed, 1 warning in 11.75s`，纯模块/包导入
  及独立子进程输出复载通过，main A3 paired smoke 为 `1 passed, 1 warning in 3.29s`。
- [x] `_validate_a3_pairing_inventory_output` 入口已在公开输出校验器之前定义，完整实现由内部
  implementation 函数承载；新增干净子进程回归直接构造、审计并复载当前 v3 输出，关闭 D6
  初始化阶段的 `NameError` 阻断。
- [x] 本次 v3 修改前，main 回归结果为 `paired_learning_adoption 5 passed`、scalable
  `345 passed, 1 warning`、cross-module `8 passed`；这些保留为冻结历史证据。
- [x] 本次 v3 修改前，main 运行 D6 全量测试，结果为
  `1093 passed, 1 warning in 98.33s`；warning 是既有 Matplotlib `Axes3D` 环境提示，无失败。
- [x] 本次 v3/候选阶段证据消费逻辑完成后，D6 全量回归为
  `1101 passed, 1 warning in 101.09s`。warning 仍是既有 Matplotlib `Axes3D` 环境提示；
  旧 `1093 passed` 只保留为修改前基线。
- [x] main 在 D5 v2 零检测帧和 truth-free 相机帧事件接线后，以相同 seeds 1000-1019 完成
  第二次未提交工作树开发复跑。492 个候选中 488 个可配对、4 个不可配对，覆盖率
  99.18699%；消费零检测帧 329 个、拒绝 0 个，v1 locked 159 个、v2 reacquire 329 个。4 个
  缺失均出现在默认 1% 通信丢包条件，对应 seed 设为 0 丢包后全部配对。该结果没有持久化完整
  pair inventory，不是正式证据，不替换旧 536/152/384 冻结批次，也不授予运行权限。
- [x] 新增 D5 v2 零检测帧的 D6 正向和输出篡改回归。完整证据且 0 覆盖时
  `benefit_auditable_count` 可用，但 `positive_benefit_claimed`、非退化声明和全部权限保持
  false；locked/ambiguous 伪造及覆盖率篡改失败关闭。
- [x] v4 strict 专项为 `64 passed, 1 warning in 11.79s`；D6 全量为
  `1106 passed, 1 warning in 100.94s`。warning 是既有 Matplotlib `Axes3D` 环境提示。

### 状态与待补

- [ ] D3 为 A1 batch candidate/selection inventory 提供公开 strict loader，并在 lifecycle
  中持久化可复核的 runtime provenance、物理窗口载荷和 R0 comparison identity。
- [x] D4 已落地实际 pair DTO、batch 和 public validator；D6 已使用真实正反例替换预留
  fixture，并兼容安装包与仓库根目录两种导入布局。
- [ ] main 继续生成正式候选/R0 双 episode 样本，使用相同冻结
  `paired_exogenous_config_sha256`、不同 episode 和 episode 级事件日志身份，由 D4/D5 形成
  唯一 pair wrapper 后再送入 D6。开发批次已完成，但 A2 没有可识别干预，A3 缺候选物理
  窗口，尚未形成正式结果证据。
- [x] main/D5 开发批次已向 v2 输入提供每个候选的一条 disposition，包括 pairable 和
  unpairable，完整分母消费链已运行。
- [ ] main/D5 为正式候选逐条持久化 D5 disposition v2 的原始
  `candidate_stage_reason_codes` 和哈希绑定 `candidate_stage_evidence`。现有冻结 v1 批次
  仍是粗粒度证据；同配置开发探针已经给出阶段诊断，但
  `source_worktree_clean=false`、`formal_evidence=false` 且完整逐候选清单未落盘，不能回填或
  替换冻结批次。
- [ ] 正式验收批次继续要求完整 disposition inventory。仅提供 pairable 子集时，D6 v1
  兼容路径只报告局部范围，不能形成完整模型证据。
- [ ] 将第二次开发复跑的 492 条 disposition、488 条 pair evidence 和 4 条丢包处置逐条
  持久化到 clean source 双 episode 批次，再由 v4 consumer 生成正式观测结果清单。当前只有
  main 提供的开发汇总，不能确认未见 seed、模型收益或通信鲁棒性。
- [ ] 结果指标形成后另行计算收益和非退化。当前 `benefit_auditable_count=available` 只代表
  输入可以审计，不代表任何性能结论。

本项不改变 AirSim settings、episode reset、检测、相机控制、计划发布或物理结果 schema。
AirSim 集成计划已检查，因没有 AirSim 接口变化而保持原状；开发证据边界已同步到实验文档。

## 2026-07-27 D5 G1 v5 正式证据链

### 已完成

- [x] 在 clean commit `8d5e02ec989259ce3d39e1e4ad6a90dd0d8d5b54` 上运行正式 external
  audit v2；结果 `pass`，blocker 为空，文件/内容 SHA-256 为
  `cbd6c72b...60cd6` / `334cf662...82d15`。
- [x] 核对 paired lineage 的 900 条记录、900 个唯一 episode UID 和文件 SHA-256
  `83e10529...b1af1`。
- [x] 由 D5 生产 assembler 生成正式 bundle v5；manifest 文件 SHA-256 为
  `b431d066...f317d`，D5 strict loader 和 shadow loader 均通过。
- [x] 运行正式 post-assembly v2；结果 `pass`，blocker 为空，内容 SHA-256 为
  `17dda42d...63e1`，consumer 为 `d6.d5-g1-post-assembly-audit-consumer.v2`。
- [x] 核对外审、authority contract 和装配后审计中的六项权限全部为 false；assist 请求以
  `bundle_g1_assist_authority_not_granted` 失败关闭。
- [x] 关闭“正式 external audit v2、正式 v5、正式 post-assembly v2 待运行”GAP。

### 后续证据

- [ ] 使用真实相机数据验证跨场景、外参漂移、遮挡和检测误差条件下的泛化；在输入形成前保持
  `real_camera_generalization=unavailable`。
- [ ] 将中心 `global_track_id` binding 与隔离的离线真值连接，形成绑定正确性证据；不得从
  边分类或簇指标推断。
- [ ] 接入导引、控制和五米物理结果，形成物理闭环证据；不得把装配完整性写成拦截结果。
- [ ] 后续若申请任何运行权限，必须由独立授权流程处理。D6 审计本身继续只读且不授予权限。

## 2026-07-26 D5 v5 生产装配正向复核

### 已完成

- [x] 逐字段读取并核对 D5 公共装配器、v5 manifest、admission report v2、authority contract
  v2 和公共严格加载器，没有只比较 schema 字符串。
- [x] 在 D6 测试内构造冻结 development-v3、held-out、paired-shadow、lineage 和 external
  audit v2 输入，最终 v5 必须由真实 `assemble_tracklet_g1_bundle()` 生成。
- [x] 正向验证七文件布局、lineage 文件摘要、900 条记录、900 个唯一 episode UID、准入报告
  lineage 三字段、六权限、D6 外审文件/内容摘要及运行实现摘要。
- [x] 对真实生产装配产物分别执行 lineage 字节篡改和文件缺失负例，两者均失败关闭且 D6
  权限保持 false。
- [x] 字段结构与 D6 post-assembly v2 完全一致，无需修改审计器，也未放宽门限或省略字段。
- [x] external 专项 `14 passed, 1 warning in 4.40s`，post-assembly 专项
  `55 passed, 1 warning in 4.93s`，D6 全量 `1042 passed, 1 warning in 91.36s`。

### 状态更新

- [x] 正式 external audit v2、生产 v5 和 post-assembly v2 已于 2026-07-27 按顺序完成；
  本节的 pytest 临时装配仍只作为软件回归证据。

## 2026-07-26 D5 G1 审计版本治理修正

### 已完成

- [x] 将 external audit 主输出从 `d6.d5-g1-external-audit.v1` 升为
  `d6.d5-g1-external-audit.v2`；输入 spec 和
  consumer 字段未变，分别保留 input v1 和 consumer v1，并在输出中独立记录。
- [x] external audit v2 精确携带六项 false 权限，以及真实相机、中心 binding、物理闭环三类
  unavailable evidence；确定性 JSON、CSV、中文 Markdown 和 `SHA256SUMS` 机制保持不变。
- [x] 将 post-assembly 输出、输入、consumer 和 profile 升为 v2。只接受
  `d5.tracklet-model-bundle.v5`、
  admission report v2、authority contract v2 和 external audit v2。
- [x] 将 paired lineage 作为 v5 的独立冻结制品。检查文件 SHA-256、900 条记录、900 个唯一
  episode UID，并与 paired 报告、external audit、manifest 和 admission report 交叉绑定。
- [x] 精确交叉绑定六权限、D6 文件/内容摘要、held-out、paired-shadow、lineage 和十文件运行
  实现摘要。旧 v4、audit v1、report v1 和错误权限合同版本均失败关闭。
- [x] post-assembly 输出六项权限全部为 false；三类 unavailable evidence 原样保留，不由
  装配完整性推断真实相机、中心绑定或物理结果。
- [x] 将 `/tmp/MSM-d5-g1-current-runtime-d6-external-audit-64cb865-20260726-v2/`
  标为版本审查否决的过渡制品 `rejected_transition_schema_v1`。该目录内部 schema 为 v1，
  不得用于新装配。
- [x] 已检查 `AIRSIM_INTEGRATION_PLAN.md`。离线 schema 改动不影响 AirSim 接口，无需修改。
- [x] 最新回归由真实 D5 生产装配正例和 lineage 负例补强，结果见上节。

### 状态更新

- [x] 2026-07-27 已使用新证据目录重跑 external audit v2，未复制或重绑定旧 `/tmp` v1
  过渡制品。
- [x] external audit v2 通过后由 D5 生产 assembler 生成 v5，随后由 D6 完成
  post-assembly v2。六项运行权限仍全部关闭。
- [ ] 真实相机、中心 binding 和物理闭环三类证据继续按本页顶部计划补充。

## 2026-07-26 D5 跨视角候选图几何校准

### 已完成

- [x] 复用 D5 finalized `d5.tracklet-dataset.v2` 严格加载器，保持匿名数值图和 evaluator
  标签物理分离，不读取在线控制路径，不向 D5、D3 或 D7 回写。
- [x] 将评估边界限定为 candidate-graph geometry calibration。所有
  `graph.edge_index` 只按几何候选边解释；G1 概率、阈值、聚类和 scoring 收益明确 unavailable。
- [x] 按 `measurement <= 0.35 s`、`arrival <= 1.0 s` 枚举同真值跨相机时间合格节点对，
  计算几何保留真边、假边、候选精确率、候选召回率、候选 F1 和几何假边率。
- [x] 无分母和缺合同字段保持 unavailable，不补 0。逐帧结果进入 aggregate JSON，逐 seed
  微平均结果进入 CSV；至少 20 个 available seed 时计算均值、总体标准差和 bootstrap 95% CI。
- [x] 实现 `d6.d5-crossview-frame-index.v1` sidecar。sidecar 绑定 dataset manifest
  SHA-256，精确覆盖 episode，并以 `scenario_version + seed + frame_index` 作为唯一稳定配对
  坐标。禁止使用或解析 `episode_id` 配对。
- [x] formal 门要求显式不少于 20 个 expected seed、实际集合精确一致、场景版本单一、标签和
  candidate recall 声明全覆盖、候选召回分母可用及硬违规为 0。缺稳定帧坐标时 R0/G1 formal
  配对失败关闭。
- [x] 显式统计同相机边、自环、重复无向边、缺标签、重复标签键、非有限数组/值、重复
  tracklet key、非法端点和超时候选边。
- [x] 输出确定性 JSON、逐 seed CSV、中文 Markdown 和 `SHA256SUMS`。权限固定为只评估，
  promotion、default、assignment、failover 和 control 全部关闭。
- [x] 独立复核 clean source commit `64cb865b...b05` 的正式 R0 制品。批次 8834 项和
  D6 报告 3 项校验清单全部通过；dataset manifest 与 2670 条 frame-index sidecar 的摘要
  绑定一致，稳定坐标精确覆盖且无重复、无错配。
- [x] 正式 R0 单臂结果覆盖 20 个 seed、2670 帧、16842 个节点和 4658 条几何候选边。
  时间合格真值对 4645，保留真边/假边为 4642/16，微平均 precision/recall/F1/false rate
  为 `0.9965650494/0.9993541442/0.9979576481/0.0034349506`。逐 seed F1 均值
  `0.9976519241`，bootstrap 95% CI 为 `[0.9953251507, 0.9995705026]`。
- [x] 正式 R0 标签和 candidate recall 覆盖均为 2670/2670，硬违规为 0。结果只关闭
  candidate-graph geometry 合同，不授予模型或运行权限。
- [x] 专项测试 `12 passed, 1 warning`；D6 全量
  `1022 passed, 1 warning in 88.77s`；变更 Python 入口编译通过。

### 后续输入

- [ ] 正式 R0 单臂候选图输入已经闭合。若要比较 R0/G1 候选生成差异，main 仍需生成 G1
  finalized dataset 及其 manifest 绑定的稳定 frame-index sidecar，并保持同一
  `scenario_version + seed + frame_index` 坐标集合。
- [ ] 如需评价 G1 scoring 收益，由 main 或后续明确 owner 设计独立 prediction sidecar，
  至少携带候选边键、边概率、冻结阈值、选中边和聚类结果，并与 dataset/模型/实现 SHA
  绑定。本工具不从 finalized dataset 推断这些字段。
- [ ] cluster purity、中心绑定正确率和控制/物理结果继续由具备相应显式字段的独立合同评估。

## 2026-07-26 D3 A1 与 D4 A2 预准入外部审计

### 已完成

- [x] 实现共享只读核心和 D3/A1、D4/A2 两套角色专用 API、CLI、输入 schema、输出 schema
  及 consumer schema。
- [x] 显式冻结数据/内容/切分、全样本审计、manifest、weights、实现来源、正式作用域报告和
  校验清单；D4 另冻结 readiness。所有输入均使用仓库内相对路径和带外 SHA-256。
- [x] 拒绝额外调用方自声明字段，不从相邻目录补找证据，不以文件名推断候选身份。
- [x] D3/A1 固定检查隔离实际采用语义
  `isolated_application/d3_learning_applied_count`；D4/A2 固定检查运行确认语义
  `runtime_ack/d4_advice_control_adoption_count`。
- [x] 检查至少 20 个训练集外未见 seed、实际采用、后续物理窗口、在线真值零使用、安全与
  硬约束、唯一同键 R0 和两项必选 paired non-degradation。
- [x] shadow、规则 fallback、零采用、缺物理窗口、缺失或重复 R0、隐藏 scope/pair blocker、
  来源漂移和 SHA-256 篡改均失败关闭。
- [x] 缺测字段输出 `null + unavailable`，包括正式审计通过标志；不以 false 或 0 冒充缺测
  观测。
- [x] 输出确定性 JSON、证据 CSV、中文 Markdown 和 `SHA256SUMS`。D6 的晋级、辅助、分配、
  降级、默认路径和控制权限固定关闭。
- [x] 当前 D3/A1、D4/A2 实际证据各完成一次严格审计，均为 `fail_closed`，各 15 个
  blocker。原输出保留，新输出写入独立 `strict_v2` 目录。
- [x] 专项 `31 passed, 1 warning`，D6 全量
  `975 passed, 1 warning in 103.81s`；新增入口 `py_compile` 通过。
- [x] 已检查 `AIRSIM_INTEGRATION_PLAN.md`。本项不改变 AirSim 接口或运行编排，无需修改。

### 仍开放

- [ ] D3 owner 需在冻结的 clean 源码上生成版本化实现证据，并提供至少 20 个未见 seed 的
  A1 隔离实际采用、后续物理状态和唯一同键 R0 正式作用域。
- [ ] D4 owner 需在冻结的 clean 源码上生成版本化实现证据，并提供至少 20 个未见 seed 的
  A2 运行确认、后续物理状态和唯一同键 R0 正式作用域。
- [ ] D3/D4 evidence assembler 必须复算 D6 JSON 文件 SHA-256 和
  `content_sha256`，校验角色、变体、来源摘要、availability、`d6_external_audit_passed` 和
  `failure_reasons`。当前两份失败结果不得装配为正向 evidence。
- [ ] 当前 D3/D4 配置中的预期实现摘要已与现工作树漂移。只有模块 owner 在 clean 状态冻结新
  候选时才能形成新配置；D6 不通过改写摘要消除来源阻断。
- [ ] 不启动 900 单元正式矩阵。预准入证据未闭合前，A1/A2 继续保持 development/shadow。

## 2026-07-26 D5 G1 预准入外部审计与装配器后复核

本节记录旧 v1/v4 链路。当前实现和后续正式运行以本文件顶部的 external audit v2、
post-assembly v2 和 bundle v5 合同为准。

### 已完成

- [x] 历史版本定义 `d6.d5-g1-external-audit.v1` 和唯一 D5 consumer contract，D6 只给证据审计
  pass/fail，不给模型晋级、G1 辅助、控制或默认路径权限。
- [x] 用显式输入清单冻结 99fa 候选 registry、manifest、weights、held-out、final
  paired-shadow 和 lineage；没有使用绑定另一模型的 `e39a54d_v2`。
- [x] 重算文件/内容 SHA-256、模型指纹、dataset/split/training-set、当次十文件实现摘要及
  held-out/paired 联合实现摘要。
- [x] 将 D6 运行实现文件集合与 D5 `tracklet_runtime_implementation_sha256()` 对齐，加入
  `tracklet_g1_evidence_assembler.py`；两侧规范摘要实算均为 `41381db3...4b07`。
- [x] 对缺失、篡改、跨模型、跨数据集、实现错配、非正式、严格布尔/整数、阈值不足和
  unavailable 建立稳定 blocker code；缺失不补 0。
- [x] 固定 20 个未见 seed、900 个 episode、45 个场景规模单元和三项安全零计数门。
- [x] 显式审计单特征 AUC、五类鲁棒性 profile、最低边/簇 F1 和候选图是否重建。
- [x] 输出 JSON、证据索引 CSV、中文 Markdown 与 `SHA256SUMS`，重复运行逐文件一致。
- [x] 2026-07-26 实物审计完成：形式化目录和安全计数可用，但实现谱系、单特征 AUC、扰动
  边 F1、扰动簇 F1 四项阻断，结果为 `fail_closed`。
- [x] 使用独立 post-assembler 配置对同一 99fa 实物复核；没有运行新实验。旧证据缺少
  assembler 哈希且 `tracklet_model_bundle.py` 已变化，结果保持 `fail_closed`，原鲁棒性和
  单特征阻断均保留。
- [x] 新旧审计分别保存在独立目录；新主 JSON 文件/内容 SHA-256 为
  `98bf9e02...c8ed` / `40a42af0...90d`，原审计未覆盖。
- [x] 装配器后专项 `14 passed`，覆盖正反例、旧证据双文件差异、CLI 和确定性输出；D6 全量
  `944 passed, 1 warning in 80.12s`。
- [x] 对 clean worktree `fa3ec10` 发布的 7fb5 robust-v2 registry 新建独立冻结配置。九类输入
  文件、两份校验清单、两份 JSON 内容摘要和十文件当次实现摘要均由 D6 重新计算，没有照抄
  producer 结论。
- [x] 7fb5 正式外审在 `2026-07-26T14:01:34Z` 完成。20 个未见 seed、900 个 episode、45 个
  场景规模单元、held-out/paired-shadow、三项安全零计数、单特征 AUC 和五类扰动门均通过；
  `audit_passed=true`，blocker 为空。
- [x] 正式输出写入 clean worktree 的
  `outputs/d5_g1_external_audit_7fb5db8b_fa3ec10_20260726/`。主 JSON 文件/内容 SHA-256 为
  `10bf19f5...10b0` / `4e24ab33...9e54`，输出校验清单复算通过。
- [x] D6 只发布 evidence audit pass。模型晋级、G1 assist、默认路径和控制权限继续固定为
  false。
- [x] 本轮专项为 `14 passed, 1 warning in 4.54s`，D6 全量为
  `975 passed, 1 warning in 86.70s`；相关 Python 入口编译通过。
- [x] 新增独立 `d6.d5-g1-post-assembly-audit.v1`、输入 schema、consumer schema 和 CLI。
  post-assembly 审计只读取显式冻结的 v4 六类文件，不从相邻目录发现替代证据，也不复用
  development-v3 审计结论作为 v4 结论。
- [x] 严格检查 v4 schema、五项 `SHA256SUMS` 精确覆盖、三份 evidence 文件/内容摘要、来源
  development bundle、weights、训练与代码谱系、admission report、20/900/45 和三项安全零
  计数。
- [x] 不跟随符号链接地枚举实际 bundle 树；只允许六个约定文件和 `evidence/` 目录。额外文件/
  目录、特殊文件、任一路径分量的符号链接、清单缺项/重复/越界均失败关闭。
- [x] v4 仅允许 `g1_assist_eligible=true`；default model、全局航迹标识、分配和控制权限必须
  为 false。D6 自身六类授权位固定为 false。
- [x] writer 使用同级临时目录写完 JSON、CSV、中文 Markdown 和校验清单后原子改名。固定时间
  和同输入写入不同目录时逐字节一致，输出与全部输入路径必须分离。
- [x] 2026-07-26T14:43:17Z 正式 post-assembly 审计通过。v4 manifest/weights/checksums 为
  `a5a53de7...7154` / `7fb5db8b...ca71` / `1221ec23...5956`，blocker 为空。
- [x] 正式输出位于 clean worktree 的
  `outputs/d5_g1_post_assembly_audit_7fb5db8b_a5a53de7_20260726/`。主 JSON 文件/内容
  SHA-256 为 `a78c5edb...cf33` / `91d627fb...007e`。
- [x] main 已在 detached clean evaluator commit
  `107cf0756d7b75cd6bf1456d1f1aa940fec6a63c` 上正式执行强化后的装配审计。输出写入新的独立
  `formal_107cf07` 目录，未覆盖原证据目录或首次正式输出。
- [x] 强化版正式结果为 `pass`、`audit_passed=true`、blocker 为空且实际目录树精确；结果
  JSON 文件/内容 SHA-256 为 `12f457e2...8ea` / `37384441...d852`，三项输出校验均通过。
- [x] post-assembly 专项 `35 passed, 1 warning in 4.33s`，D6 全量
  `1010 passed, 1 warning in 87.38s`；Python 编译、JSON 和差异格式检查通过。
- [x] 对 clean commit `64cb865b...b05` 的当次 D5 runtime 重新执行独立预准入外审。输入
  JSON SHA-256 为 `f98b42d3...23a5`；顶层、bundle、formal 和 current-runtime registry
  四套校验清单分别为 24/2/2/3 项，全部通过。
- [x] 独立重算当次十文件 runtime implementation SHA-256
  `55066382...b8ea`，与输入、manifest 及 held-out/paired 联合证据一致。九个 artifact
  均来自当次批次，未混用历史证据；审计前后 80 个输入文件逐字节不变。
- [x] 当次 runtime 证据覆盖 20 seeds、900 episodes、45 cells。五类扰动最低边/簇
  F1 为 `1.0/1.0`，最高单特征 AUC 为 `0.7200734257`；在线真值、同相机边/互斥违规和
  `global_track_id` 创建或换绑违规为 0。
- [x] 当次 runtime 外审按旧 v1 门限为 `pass`、blocker 为空。最终 JSON 文件/内容 SHA-256 为
  `24c8b0cd...ad7d` / `f17acecf...135f`；重复运行 JSON、CSV、中文 Markdown 和
  `SHA256SUMS` 逐字节一致。
- [x] external-audit 输出显式关闭 model promotion、G1 assist、default、control、
  assignment 和 failover 权限，并把真实相机泛化、中心 binding 和物理闭环证据标记为
  unavailable。当次未运行 G1 episode，未装配新的 v4。
- [x] 当次 runtime 外审专项 `14 passed, 1 warning in 4.39s`，D6 全量
  `1022 passed, 1 warning in 89.39s`；Python 编译、文档和差异格式检查通过。
- [x] 已检查 `AIRSIM_INTEGRATION_PLAN.md`。本项不改变 AirSim 数据、episode 或控制接口，
  无需修改。

### 仍开放

- [ ] 五类扰动仍固定 post-gate 候选图。需要在相机投影、时间偏差和遮挡扰动后重新门控、重新
  构图，才能关闭候选生成全链路的外部泛化限制。
- [ ] 当前证据来自合成三维质点投影和离线 truth evaluator，未覆盖真实相机内外参误差、真实
  检测漏检/虚警、纹理退化和在线计算预算。真实相机证据保持开放。
- [ ] 当前输入只有 `global_track_id` 零创建/换绑违规，没有中心 binding 结果与离线真值配对；
  中心绑定正确率保持 unavailable。
- [ ] 当前输入不含导引、控制或物理拦截记录；物理闭环结果保持 unavailable。
- [ ] G1 实际执行后仍需 `learning_scope_formal_audit` 与同 comparison key 的 R0 结果做
  完整运行证据配对。
- [ ] 2026-07-27 正式 v5 已完成装配和两级审计，但六项权限仍全部为 false。任何后续运行都
  需要 D6 之外的独立授权；实际采用、无静默回退证据和后续作用域审计仍未完成。

## 2026-07-25 正式 R0/G1/A1/A2/A3/C1/F1 矩阵准入预检

### 已完成

- [x] 实现独立只读的 `pre_run` 和 `post_run` 预检。D6 不启动 episode，不参与控制。
- [x] 直接消费 `ExperimentMatrixPlan.cells()` 或显式 cell inventory，不从目录名或只有维度
  的摘要推断缺失 cell。
- [x] 使用当前实际 formal 合同动态得到 5700 个 cell；测试另验证 F1 增加一个场景后数量自动
  变为 5800。
- [x] 检查 cell 唯一性、七变体声明、九场景、五规模、至少 20 个未见 seed、训练 seed 零
  交集、formal/禁止回退标志和 clean-source。
- [x] 检查 D3、D4、D5 图模型和 D5 主动视觉 bundle、manifest、weights SHA-256 及 assist
  声明。
- [x] `post_run` 逐 cell 检查声明采用、静默回退、在线真值、有限状态、D2 身份交换可用性、
  五米物理指标和逐 seed 输入。
- [x] 检查 D6 聚合置信区间输入、中文报告、曲线、GIF/MP4 和模型清单制品。
- [x] 缺失 cell 按变体、场景、规模和 seed range 压缩输出；不创建伪指标。
- [x] 输出完整 JSON、逐 cell CSV、中文 Markdown 和 `SHA256SUMS`。
- [x] 区分“缺少 CLI inventory 导致 expected=0”和“实际 formal inventory 为 5700”；
  缺输入时命令行、JSON blocker 和中文报告均明确说明，不把 0 写成正式规模。
- [x] D4 模型清单中的保留 seed 数非法时失败关闭，不因类型转换异常中断预检。
- [x] 当前仓库静态 `post_run` 预检已完成：expected=5700、accepted=0、verdict=
  `fail_closed`。矩阵 manifest 缺失；四个现有学习模型哈希有效但 assist 未准入。
- [x] 专项 `9 passed`，D6 全量 `889 passed, 1 warning`；既有 main 矩阵合同
  `7 passed, 1 warning`；当前报告三项 SHA-256 校验通过。

### 仍开放

- [ ] main 需在 clean detached worktree 生成并冻结正式 expected-cell inventory 和 model
  inventory，D6 再执行 `pre_run`。
- [ ] D3/D4/D5 各模型需先完成各自未见 seed 准入；D6 不替模块开放 assist。
- [ ] 正式矩阵尚未运行。`experiment_matrix_manifest.json`、逐 cell 运行记录、D6 逐 seed
  数据、置信区间、动画和正式模型清单仍缺失。
- [ ] D2 `id_switch_count` 与五米物理指标必须逐 cell 可用。缺失时保持
  `fail_closed`，不得以 0 代替 unavailable。
- [ ] 完整 5700-cell 运行成本很高，main 应按变体和规模分批生产，但每批清单必须能回并到同一
  冻结 expected inventory。

## 2026-07-25 D1 在线发布证据子集快照正式评估状态

### 已完成

- [x] 独立只读、失败关闭 evaluator、CLI、完整/紧凑 JSON、逐 pair CSV、中文 Markdown 和
  `SHA256SUMS` 已实现，schema 为
  `d6.d1_publication_evidence_snapshot_multiseed_evaluation.v1`。
- [x] 正式输入固定为 clean commit
  `d0219eb14c529a4fb9bf7d6610a9f32055a09206`、matrix SHA
  `6c808c4df8759fd893c6d37ff9dce4a1efa07f9867fc71aff47a55c5f8517338`、200/200/2、
  short seeds 1151-1160 和 long seeds 1151-1153。
- [x] 13 pair/26 arm 全部 fresh complete，0 reused、0 failed；两臂只允许
  `d1_publication_evidence_snapshot_implementation` 不同，回放前缀均固定为参考实现。
- [x] 五个实现表面、命令与路径隔离、D1/D2 在线记录、业务语义、consistency digest/count、
  原 D1 操作计数、有限状态和在线真值隔离已独立重算。
- [x] 13/13 pair 的上述合同和候选诊断通过。候选 `429/429` 次子集选择成功，fallback、
  lookup miss、invalid ID 和 empty set 均为 0。
- [x] 返回记录由 `1602170` 减至 `133917`，削减 `91.641524%`，通过 `>=50%` 门。
- [x] 正式结果为 `reject`。失败门为 short 更快 `4/10 < 8/10`、short D1 改善
  `-0.147877% < 1%` 和 short bootstrap 上界 `1.374681% > 0%`；没有调门或删除 pair。
- [x] long D1 改善 `1.047143%`、long 更快 `2/3`，short/long core、D2 与 RSS 门通过。
- [x] 正式 bundle 已保存到
  `outputs/d1_publication_evidence_snapshot_multiseed_20260725_formal_d0219eb_d6/`。
- [x] 同一正式 manifest 重复评估与正式 bundle 逐文件一致；聚焦 `14 passed`，D6 全量
  `880 passed, 1 warning in 76.17s`。

### 仍开放

- [ ] 候选 `required_observation_subset_v1` 未满足冻结性能门，保持默认关闭；参考
  `full_consistency_snapshot_v1` 保持默认。
- [ ] 返回记录削减没有形成稳定 short D1 墙钟收益。后续优化需登记新候选和新矩阵，不得覆盖
  本次 `reject`。
- [ ] 候选最低实时因子 `0.203423 < 1`，200v200 系统实时 P1 未关闭。
- [ ] 当前仅有三维质点证据；AirSim、目标处理器、硬件、实机和实飞证据仍缺失。

## 2026-07-25 D1 回放前缀摘要正式评估状态

### 已完成

- [x] 独立只读 evaluator、CLI、完整/紧凑 JSON、逐 pair CSV、PNG、中文 Markdown 和
  `SHA256SUMS` 已实现，schema 为
  `d6.d1_replay_prefix_summary_multiseed_evaluation.v1`。
- [x] 正式输入固定为 producer commit
  `7d2e987471b521a1e531bf03a5c99af5096f676a`、matrix SHA
  `85432d729877eff97e6f3dd517d4baa7a47f44a4fa42e6bfdc7ce85b8d9ec74b`、200 个目标、
  200 个资源、2 个侦察节点、short seeds 1151-1160 和 long seeds 1151-1153。
- [x] 13 pair/26 episode 均为 fresh complete，0 reused、0 failed；两臂来自同一 clean
  commit，只有回放前缀摘要 selector 不同。
- [x] 13/13 pair 的业务语义、在线 consistency records digest/count、D1 原有融合操作计数、
  实现身份、诊断守恒、有限状态和在线真值隔离通过。
- [x] summary hit/reuse、append revision、pending preservation、snapshot projection、
  append materialization=0 和最终 pending=0 已从正式诊断核验。
- [x] 全矩阵逻辑刷新记录 `811858`、内部实际物化 `388468`，内部物化减少
  `52.150746%`；在线快照另投影构造 `656481` 条记录，没有计作已消失工作量。
- [x] 正式结果为 `reject`，`main_default_promotion_allowed=false`。失败门是 short 更快
  `5/10 < 8/10`、short D1 改善 `0.959611% < 1%`、short bootstrap 上界
  `0.619827% > 0%`、short core 改善 `-0.256641% < 0.25%` 和 long core 改善
  `-1.930083% < 0.25%`。
- [x] long D1 改善 `2.361778%`、内部物化压缩、short/long RSS 和 D2 组均值门通过；门限
  未修改，pair 未删除。
- [x] 正式 bundle 位于
  `outputs/d1_replay_prefix_summary_multiseed_20260725_formal_7d2e987_d6/`。
  `SHA256SUMS` 已通过；main 使用同一 manifest 重跑后全部输出 SHA-256 与正式 bundle 一致。

### 仍开放

- [ ] 候选 `fixed_lag_checkpoint_prefix_cumulative_summary_v1` 不满足冻结准入门，保持默认
  关闭；参考 `per_checkpoint_prefix_rebuild_v1` 保持默认。
- [ ] 候选最低实时因子 `0.197441 < 1`，200v200 系统实时 P1 未关闭。
- [ ] 在线快照仍投影构造 `656481` 条记录。若继续优化，应以 publication 实际需要的观测 ID
  设计新候选，并使用新候选名和新预注册矩阵，不得改写本轮结论。
- [ ] 当前仅有三维质点仿真证据；AirSim、目标处理器、硬件、实机和实飞证据仍缺失。

## 2026-07-25 D1 关联稀疏预筛多种子评估状态

### 已完成

- [x] 新增 schema `d6.d1_association_sparse_prefilter_multiseed_evaluation.v1`、独立只读
  evaluator、CLI、完整/紧凑 JSON、逐 pair CSV、中文 Markdown、PNG 和 `SHA256SUMS`。
- [x] 固定 matrix SHA
  `a7162d014d1c3c0f207355b24a5d7159bf3486d134ca21876f7469d1e915b71d`、clean source
  commit `9302ccede2ca513c2235370e1a464fc88bc41150`、13 pair/26 fresh arm、200/200/2、
  seed、时长、arm 顺序、命令、路径和 `episodes_complete_pending_d6` 状态。
- [x] 在 runtime profile、summary、module final、governance 及冗余 configuration/nested
  governance 表面核对 selector、完整 implementation ID、execution config 和 diagnostics v2。
- [x] 重算六个固定模态桶、计数上界和总计守恒、逐 pair/逐模态 exact gate-pass 相等、有限状态
  和 online truth use=0；不读取 producer 私有验收函数或 admission 结论。
- [x] 业务语义仅归一化预注册 treatment、对应诊断/运行时哈希差异和性能字段，其他在线消息、
  D1-D7 结果、计划谱系、ACK、内容地址及离线 truth 制品继续比较。
- [x] 重算 short/long D1 fusion、core wall、scan input、D2 association、RSS、RTF 和固定
  10000 次 paired bootstrap；全部门限严格取自冻结矩阵。
- [x] 正式 13/13 pair 的业务语义、实现身份、有限状态、真值隔离、逐模态 gate-pass 和预筛审计
  通过。非雷达精确求解由 `298109` 降至 `39837`，减少 `86.636767%`。
- [x] 正式 verdict 为 `reject`：short 更快数 `7/10 < 8/10`、D1 fusion 改善
  `0.228437% < 1%`、bootstrap 上界 `0.443531% > 0%`、core 改善
  `0.091096% < 0.25%`，long D1 fusion 改善 `0.713776% < 1%`。不调门、不删 pair，
  main 默认晋升不允许。
- [x] 正式 bundle 位于
  `outputs/d1_association_sparse_prefilter_multiseed_20260725_formal_9302cce_d6/`；
  `SHA256SUMS` 全部通过，原始 evidence 保持只读。
- [x] 正负测试覆盖 SHA、commit、selector、execution config、diagnostics schema、计数守恒、
  gate-pass mismatch、业务语义、性能门、RSS、D2、online truth 和缺文件。定向
  `13 passed, 1 warning in 7.22s`，D6 全量 `859 passed, 1 warning in 64.83s`。

### 仍开放

- [ ] 候选未通过冻结性能门，reference `disabled_v1` 保持默认。任何重新准入必须使用新的
  预注册矩阵，不得覆盖本轮 `reject`。
- [ ] 候选最低实时因子 `0.206273 < 1`，200v200 系统实时 P1 未关闭。
- [ ] AirSim、目标处理器、硬件和实飞证据未形成，不能从三维质点局部结果继承。

`AIRSIM_INTEGRATION_PLAN.md` 与 `D6_M_TO_N_EVALUATION_FRAMEWORK_REVIEW.md` 已检查。本项不改变
AirSim 接口、episode 调度或通用 M-to-N 指标合同，无需修改。

## 2026-07-25 D1 在线批帧交接多种子评估状态

### 已完成

- [x] 新增 schema `d6.d1_online_batch_frame_multiseed_evaluation.v1`、独立只读 evaluator、
  CLI、完整/紧凑 JSON、逐 pair CSV、中文 Markdown、PNG 和 `SHA256SUMS`。
- [x] 固定 matrix SHA
  `4afbf9ac273763a16aa01cc744fd67b52e437099460b33377a128f986ac5719b`、clean commit
  `43feaf600f288a85ce76a76862334256f0d0d352`、13 对/26 fresh episode、200/200/2、
  seed、时长、arm 顺序、命令和证据路径。
- [x] 在 runtime profile、summary、module final、nested governance 和 governance audit
  核对 selector、implementation ID、execution config、诊断 schema 与四份最终诊断谱系。
- [x] 从原始 episode 重算有限状态、online truth use=0、业务语义、批帧守恒、short/long
  faster count、scan/core 改善、D2 回归、RSS 回归、重复检查减少、closed ratio 和 fallback。
- [x] 对 plan ID 和其内容地址采用先验证后映射的语义谱系；不忽略 assignment、授权、
  target/resource binding、状态机、计数或安全差异。
- [x] 正式结果 `admit`：scan input short/long 改善
  `38.289241%/36.275282%`，core wall 改善 `4.252745%/4.916501%`，D2 增幅
  `2.113047%/2.830616%`；重复检查减少和 closed ratio 均为 `100%`，fallback 为 0。
- [x] 正式 bundle 在
  `outputs/d1_online_batch_frame_multiseed_20260725_formal_43feaf6_d6/`；同目录复跑后全部
  制品 SHA-256 一致，producer evidence 未改写。定向测试 `12 passed, 1 warning`，D6 全量
  `846 passed, 1 warning in 59.24s`。

### 仍开放

- [ ] 候选最低实时因子 `0.204490`，低于 1；200v200 系统实时 P1 未关闭。
- [ ] AirSim、目标处理器和实飞证据未形成，不能由本三维质点准入继承。

## 2026-07-25 D1 不透明来源标识缓存多种子评估状态

### 已完成

- [x] 新增独立 evaluator、CLI 和确定性 writer，schema 为
  `d6.d1_opaque_source_identity_cache_multiseed_evaluation.v1`。
- [x] 固定 matrix SHA
  `218d04f3fc4a764fef82de612c78c8fbb5490380ae5d20aff6b9089635f2060d`、clean source
  commit `d8fc76c066f21b077154f7be33c0b43558d237e5`、13 pair、26 fresh complete arm、
  200/200/2、seed、时长、顺序、命令和证据路径。
- [x] 要求 source-only 发布键启用、结构歧义 hold 关闭；本矩阵不代表默认无来源键 R0 收益。
- [x] 在 runtime profile、summary、module final、嵌套治理和独立治理中核对 selector、实现 ID、
  diagnostics schema、候选标志、容量和最终诊断一致性。
- [x] 实现 request/hit/miss/bypass/build 守恒、容量/峰值、publisher generation 和两臂相同请求
  工作量校验。候选旁路必须为 0；参考必须全部旁路且无缓存活动。
- [x] 业务语义比较只归一化处理字段和性能字段；`GlobalTrack`、来源键业务值、状态/协方差、
  在线观测、D2-D7 结果、计划和控制语义继续比较。
- [x] 严格执行冻结门：short/long D1 fusion、core wall、D2 association、RSS、候选更快数、
  10000 次配对 bootstrap、标识构造减少率和缓存命中率。
- [x] 输入无效时返回 `availability=false`，并固定
  `optimization_admitted=false`、`system_realtime_gap_closed=false`。
- [x] 输出完整 JSON、compact JSON、逐 pair CSV、中文 Markdown、PNG 和校验和，正式目录为
  `outputs/d1_opaque_source_identity_cache_multiseed_20260725_formal_d8fc76c_d6/`。
- [x] 聚焦测试 `16 passed, 1 warning in 5.85s`；D6 全量
  `834 passed, 1 warning in 59.24s`。
- [x] 正式 26/26 arm 全部 fresh complete，0 reused、0 failed；13/13 业务语义、有限状态、
  在线真值零使用、实现身份和缓存审计通过。
- [x] short/long D1 融合改善 `9.465972%/6.437432%`，核心墙钟改善
  `2.845610%/2.728043%`，候选更快数为 `10/10`、`3/3`。标识构造减少率和缓存命中率均为
  `99.163670%`。
- [x] long D2 关联组均值增幅 `5.605213%` 超过冻结上限 `5%`，是唯一失败门。
  `long_seed_1101` 单 pair 增幅 `19.069868%` 已保留。因此
  `optimization_admitted=false`，不得晋级为默认实现。
- [x] 候选最低实时因子 `0.193887`，`system_realtime_gap_closed=false`。

### 后续 P1

- [ ] 预先冻结新的确认矩阵，采用相同 source-only 条件和 D2 上限，增加长时 seed 或重复轮次，
  判断 D2 回归是否稳定；不得覆盖本次正式结论。
- [ ] 在 AirSim 和目标处理器上补充端到端实时证据。当前三维质点结果不能关闭系统实时缺口。

`AIRSIM_INTEGRATION_PLAN.md` 已检查。本项不改变 AirSim 接口或 episode 调度，无需修改。

## 2026-07-25 D1 结构化数值雅可比多种子评估状态

### 已完成

- [x] 实现独立、只读、失败关闭的 evaluator、CLI 和确定性 writer，输出完整 JSON、compact
  JSON、逐 pair CSV、中文 Markdown 和 `SHA256SUMS`。
- [x] 固定 evaluator schema
  `d6.d1_structured_jacobian_multiseed_evaluation.v1`、matrix SHA
  `c6c3cf53c89dfb3155a29ba49bb77a12c8bdf1a5d433c4f645de0d00c506d478` 和 clean producer
  commit `9d1f54f8540fdc4a7a1011121aafac5718290122`。
- [x] 精确校验 13 case、26 个 fresh complete arm、200/200/2、seed、时长、arm 顺序、命令隔离、
  返回码、source clean 状态、证据路径和输入 SHA-256。
- [x] 在 runtime profile/configuration、summary、module final、嵌套 governance 和独立
  governance 中核对 selector；在四份最终诊断中核对完整实现 ID、schema、candidate flag 和操作数。
- [x] 校验雅可比尝试、成功/失败、参考/候选调用、输出探测、非活动列和量测函数求值守恒；两臂
  Jacobian attempt 工作量必须相同。
- [x] 逐对比较业务语义、有限状态和在线真值零使用；处理归一化只覆盖预注册 selector、诊断、
  性能字段和处理派生 episode ID。
- [x] 计算 short/long D1 fusion、core wall、D1 scan input、D2 association、RSS、逐 pair
  更快数和固定 10000 次配对 bootstrap；量测函数求值减少率单独聚合。
- [x] 输入缺失、schema/version 错配或证据无效时输出
  `availability=false + reason`，并保持局部准入和系统实时门为 false。
- [x] 合成测试覆盖通过、性能拒绝、求值减少拒绝、5% RSS 边界、缺失输入/字段、版本错配、
  provenance、diagnostics、conservation、business、dirty、reused、command 和路径篡改。
- [x] 2026-07-25 专项 `20 passed, 1 warning in 6.05s`，D6 全量
  `818 passed, 1 warning in 55.42s`；warning 为既有 Matplotlib `Axes3D` 环境提示。
- [x] main 已在 clean producer commit 上完成冻结 short 10 pair、long 3 pair，共 26 个 fresh
  complete arm；0 reused、0 failed。
- [x] main 已使用 D6 CLI 只读消费正式 evidence。评估结果为 `availability=true`；
  13/13 业务语义、有限状态、在线真值零使用、实现身份、操作数守恒和全部冻结准入门通过。
- [x] 正式结果为 `optimization_admitted=true`。短时 D1 融合/核心墙钟改善
  `6.084778%/1.897370%`，`10/10` 更快；长时改善 `4.676061%/1.786530%`，`3/3`
  更快；量测函数求值减少 `53.846154%`。
- [x] 候选最低实时因子为 `0.180726`，因此独立系统实时门为
  `system_realtime_gap_closed=false`。
- [x] main 已将 scalable 3D `IntegratedStackConfig` 和 `run_episode` CLI 默认实现晋级为
  `known_dimension_structural_columns_v1`，并保留 `dense_output_probe_v1` 显式回退。D6
  evaluator 保持独立，D1 独立 `FusionAdapter` 默认不变。scalable 测试通过；2v2 默认 smoke
  的三处表面均记录候选实现，有限状态为 true，在线真值使用为 0。

### 后续 P1

- [ ] 在 AirSim、目标处理器和目标负载条件下补充端到端实时证据，关闭系统实时 P1。

`EXPERIMENT_REPORT.md` 已记录正式结果及适用边界。
`AIRSIM_INTEGRATION_PLAN.md` 已检查，本项不改变 AirSim 接口或 episode 调度，因此无需修改。

## 2026-07-24 在线真值检查多种子评估状态

### 已完成

- [x] 实现独立只读 evaluator、CLI、完整 JSON、compact JSON、逐 pair CSV、中文 Markdown 和
  `SHA256SUMS`；D6 不参与在线控制，也不修改 producer evidence。
- [x] 固定 matrix SHA
  `764574b9897d00101c26c555de2f407e1736c7e6ff50420eebf131e154618dc8` 与 clean source
  commit `8d8bb6ed7a417705236835f235361f45a021bb2b`。
- [x] 严格绑定 evidence/evaluator/diagnostics schema、13 个 case、arm 顺序、200/200/2、
  short/long seed 与时长、命令隔离、fresh complete 状态、返回码和证据路径。
- [x] 每个 arm 核对 selector、candidate flag、诊断 schema，并要求
  `validation_count = online_message_count > 0`、有限状态和在线真值零使用。
- [x] 对 12 类输入路径计算 SHA-256，固定核对场景、runtime profile、governance 和 stage
  timing schema；来源、配置、路径、摘要和资源层均进入失败关闭检查。
- [x] D6 内部调用跨 episode 比较器。只排除预注册 runtime profile hash 差异，并窄归一化
  selector、诊断、性能和处理派生 episode ID；在线载荷、业务计数、计划谱系和离线真值继续比较。
- [x] 发布总线主阶段与 finalize 相加作为准入主指标；同时报告核心墙钟、外层耗时、实时因子、
  D1、D2 和 RSS。
- [x] short/long 使用固定 10000 次配对 bootstrap；全部数值门从冻结 matrix 读取，不允许运行
  后调整。
- [x] 合成合同专项覆盖正常 13 pair、只读报告、CLI、检查数不守恒、实现身份、业务漂移、性能门、
  dirty/reused/source commit/schema/matrix/command 篡改。
- [x] 2026-07-24 正式结果同步后专项 `14 passed, 1 warning in 4.46s`，D6 全量
  `798 passed, 1 warning in 52.01s`；warning 为既有 Matplotlib `Axes3D` 环境提示。

### 正式结论

- [x] main 已在冻结 clean commit 上完成 short 10 pair 和 long 3 pair，共 26 个 fresh complete
  arm；0 reused、0 failed。D6 已只读消费证据并生成正式 bundle。
- [x] 13/13 pair 的业务语义、有限状态、在线真值隔离、实现身份、诊断守恒和来源门通过；
  参考与候选各 94074 条在线消息均完成递归检查，在线真值使用为 0。
- [x] short/long 发布总线及收尾改善 `22.58%/25.63%`，候选分别 `10/10`、`3/3` 更快；
  short 核心墙钟改善 `2.50%`。
- [x] 正式准入结论为 `optimization_admitted=false`。long 核心墙钟回退 `3.47%`，long D1
  融合增加 `5.29%`，long D2 关联增加 `7.34%`，三项预注册门失败。默认继续使用
  `generic_recursive_v1`，候选 `builtin_specialized_recursive_v2` 保持关闭。
- [x] 候选最低实时因子为 `0.165369`，因此
  `system_realtime_gap_closed=false`。正式结果已同步到 `EXPERIMENT_REPORT.md` 和
  `outputs/online_truth_guard_multiseed_20260724_formal_8d8bb6e/`。
- [ ] 可选 balanced-order v2 只用于诊断 long seed 1102 的顺序和主机热状态影响。它不得覆盖
  v1 正式结果；如需重新准入，必须预先冻结新矩阵并生成独立证据。
- [ ] 系统实时容量、AirSim、目标硬件和实飞证据继续开放。

`AIRSIM_INTEGRATION_PLAN.md` 已检查。本项消费三维质点 episode，不改变 AirSim topic、相机、
actor、reset 或控制接口，因此无需修改。

## 2026-07-24 D1 常速度模型缓存评估状态

### 已完成

- [x] 新增独立 schema
  `d6.d1_cv_motion_model_cache_multiseed_evaluation.v1`、只读 evaluator、CLI 和确定性报告
  bundle，不参与在线控制。
- [x] 固定 matrix SHA
  `9898656598f0fa282620afe2384a3d656b7496f8957109c413bcb62069fd2e9a` 与 clean source
  commit `44223566439a446fc49f2a3fd861d1d51bd676b9`。
- [x] 精确校验 10 short + 3 long case、26 个 fresh complete arm、200/200/2 规模、执行顺序、
  命令隔离、零返回码、资源记录、有限状态和在线真值零使用。
- [x] 在 runtime profile/configuration、summary、module final、嵌套治理和独立治理位置交叉确认
  `per_prediction_build_v1/bounded_exact_lru_v1`、实现 ID、诊断 schema 和容量 128。
- [x] 对 candidate 检查请求守恒、构造守恒、hit/miss/build 非零和 entry/peak 容量；对 reference
  拒绝 hit/miss/eviction/entry/peak，并核对请求与构造数。
- [x] 由 D6 内部调用 `compare_cross_build_episodes()`；只排除
  `same_runtime_profile`，缓存处理字段窄归一化，其他业务、谱系和离线真值继续比较。
- [x] 实现 D1 fusion、D2 association、core wall、RSS、实时因子、构造减少率、命中率、逐 pair
  变化和 10000 次配对 bootstrap。
- [x] 全部门限从冻结矩阵读取并严格核对，不允许运行时降低。局部优化准入和系统实时缺口独立输出。
- [x] 输出完整 JSON、compact JSON、逐 pair CSV、中文 Markdown、PNG 和校验和；原始 evidence
  保持只读。
- [x] 专项 `13 passed, 1 warning in 5.03s`；D6 全量
  `784 passed, 1 warning in 48.64s`。warning 为既有 Matplotlib 环境提示。

### 正式结论

- [x] main 已在 clean source
  `44223566439a446fc49f2a3fd861d1d51bd676b9` 上完成 13 pair、26 个 fresh arm；0 reused、
  0 failed。D6 已只读消费 completed evidence，正式 bundle 位于
  `outputs/d1_cv_motion_model_cache_multiseed_20260724_formal_4422356/`。
- [x] 13/13 pair 的业务语义、有限状态、在线真值隔离、实现身份和缓存审计通过；19/19 准入门
  通过。
- [x] short/long D1 融合改善 `6.9271%/6.6103%`，核心墙钟改善
  `2.4060%/2.4537%`，D2 关联增幅 `-0.1082%/-2.6729%`，RSS 均值增幅
  `0.0145%/0.2959%`。
- [x] 模型构造减少率和缓存命中率均为 `99.5960%`，short `10/10`、long `3/3` 更快，
  short bootstrap 上界为 `-6.0841%`；`d1_optimization_admitted=true`。
- [x] 正式结论文档同步后 D6 全量回归为 `784 passed, 1 warning in 55.02s`；warning 为既有
  Matplotlib `Axes3D` 环境提示。
- [ ] 候选最低实时因子为 `0.17394990897894075`，低于 1；
  `system_realtime_gap_closed=false`。系统实时 P1、AirSim、目标硬件、传感器精度和实飞证据
  继续开放。

`EXPERIMENT_REPORT.md` 已新增正式结果章节。
`AIRSIM_INTEGRATION_PLAN.md` 已检查；本项不改变 AirSim producer、相机、检测、reset、actor 或
控制接口，因此无需修改。`docs/README.md`、`docs/MODULE_PRINCIPLES_CN.md` 和
`docs/ALGORITHM_AND_IMPLEMENTATION.md` 已同步正式结果和适用边界。

## 2026-07-24 D1 发布元数据 v2 正式评估状态

### 已完成

- [x] 新增独立 schema `d6.d1_publication_metadata_v2_multiseed_evaluation.v1`，保留 v1 evaluator
  及历史报告语义不变。
- [x] 精确校验 v2 evidence/matrix schema、矩阵 SHA、clean commit `be399e1`、13 pair/26 arm、
  命令隔离、规模、seed、时长、返回状态、资源记录、有限状态和在线真值零使用。
- [x] 从四个持久化位置核对 D1 `publication_audit_tree.v2` 合同和 D2 审计。候选的合同校验、
  内容审计、完整审计和身份复用关系，以及参考的内建等价复用均已失败关闭。
- [x] D2 审计只作为处理差异诊断归一化；其余 summary、governance、在线总线、计划谱系和离线
  真值继续执行业务等价比较。
- [x] 实现 short/long D1、核心墙钟、D2 关联、RSS、候选更快数和 bootstrap 完整准入门；
  每个 gate 输出实际值、门限、比较符和结论。
- [x] 正例及审计篡改、非白名单业务变化、D2 回归、核心墙钟、source commit 和 dirty provenance
  负例通过。v1/v2 专项为 `37 passed, 1 warning`，D6 全量为
  `771 passed, 1 warning in 47.61s`。
- [x] 正式报告已写入
  `outputs/d1_publication_metadata_v2_multiseed_20260724_formal_be399e1/`，仅保存紧凑制品。

### 正式结论

- [x] 13/13 业务语义、有限状态、真值隔离、实现身份和 D2 审计通过。
- [x] short/long D1 融合改善 `13.5447%/26.8298%`；核心墙钟改善
  `6.5677%/18.2438%`；D2 关联增幅 `-16.1939%/-35.6213%`。全部预注册门通过，
  `d1_optimization_admitted=true`。
- [ ] 候选最低实时因子 `0.17308010045846806`，低于 1；
  `system_realtime_gap_closed=false`。系统实时 P1、AirSim 和目标硬件容量证据继续开放。
- [ ] producer 当前只持久化最近批次和累计 D2 审计；如需定位单批异常，后续增加逐批审计日志。

`AIRSIM_INTEGRATION_PLAN.md` 已检查。本项只消费三维质点写盘证据，不改变 AirSim producer、
相机、检测、reset、actor、控制或 episode 调度，因此无需修改。

## 2026-07-24 D1 航迹发布元数据正式评估状态

### 已完成

- [x] 新增 `d6.d1_publication_metadata_multiseed_evaluation.v1` 独立只读消费者、CLI 和
  合成 evidence fixture，不参与 D1-D7 控制。
- [x] 精确冻结 manifest/matrix schema、矩阵 SHA256、source commit、13 对 short/long case、
  200/200/2 规模、arm order、命令、selector、实现 ID、bootstrap 和准入门。
- [x] 要求 26 个 arm 均为 complete、零返回码、episode 文件齐全；stderr 只接受空或唯一登记的
  Matplotlib `Axes3D` 环境警告，其他内容失败关闭。
- [x] 交叉核对 summary/module final/governance 的 selector、实现 ID、不可变标志和操作计数。
  参考逐航迹复制必须大于 0；候选复制必须为 0、共享复用必须大于 0；两臂完整物化数必须相等。
- [x] 逐对比较在线总线、D2 身份/ID switch、D3 计划谱系、D4 内容地址/确认来源、D5/D7 输出、
  summary/governance 非白名单字段，以及离线真值状态、标签和 5 米事件。在线真值使用为 0。
- [x] 输出 D1 fusion wall/P50/P95/max、scan input、D2/D3/D5/D7、publication bus、core wall、
  external elapsed、RSS 和实时因子。阶段耗时与 core/elapsed 分层，不相加。
- [x] 实现 short/long 配对变化、均值比变化、10000 次/seed 20260724 bootstrap、RSS 门、
  D1 融合门、short/long 核心墙钟 5% 门和独立系统实时门。
- [x] 专项正负测试 `27 passed`，覆盖错误实现 ID、假 selector、候选仍复制、参考不复制、
  无共享复用、不可变标志错误、物化数不等、业务漂移、truth 泄漏、失败 manifest/return code、
  非登记 stderr、RSS/性能/bootstrap 门和 evidence root 内输出拒绝。
- [x] 2026-07-24 D6 全量回归 `761 passed, 1 warning in 41.25s`；warning 为既有
  Matplotlib `Axes3D` 环境提示。
- [x] 正式只读消费 clean commit
  `a36f519ed954a9ba8bdc3fe149ba2835da290c39` 的 13 对、26 arm、约 4.2 GB evidence。
  JSONL 采用逐行哈希和逐行成对比较。
- [x] 正式 bundle 已归档到
  `outputs/d1_publication_metadata_multiseed_20260724_formal_a36f519/`，含 JSON、CSV、
  中文 Markdown、PNG 和 `SHA256SUMS`，未复制原 episode。

### 正式结论

- [x] D1 融合 short/long 均值比改善约 `16.29%/31.05%`，候选分别 `10/10`、`3/3` 更快；
  全部语义、有限状态、真值隔离、实现身份和 RSS 门通过。
- [x] D2 关联 short/long 增加约 `53.44%/169.89%`。源码核对确认候选只读容器未进入 D2
  exact built-in 等值复用，导致共享诊断树逐航迹重扫。
- [x] short/long 核心墙钟只改善约 `1.65%/1.21%`，未达到各 `5%` 的预注册门。
  `d1_optimization_admitted=false`。
- [ ] 候选最低实时因子为 `0.14695931849644195`，
  `system_realtime_gap_closed=false`。系统实时性继续开放。
- [ ] D1/D2 需联合消除容器类型互操作开销，并由 main 重跑同一 13-pair 矩阵。D6 再按原门复评；
  未复评前候选不得写成默认性能准入。

`EXPERIMENT_REPORT.md` 已同步正式结果。`AIRSIM_INTEGRATION_PLAN.md` 已检查；本项不改变 AirSim
producer、日志合同、相机、检测、reset、actor、控制或 episode 调度，因此无需修改。

## 2026-07-24 D1 扫描输入同提交 A/B 评估状态

### 已完成

- [x] 固定 `d6.d1_scan_input_multiseed_evaluation.v1` 只读合同，精确校验矩阵 SHA、
  experiment、short 10 seed、long 3 seed、200/200/2、arm order、bootstrap、准入门和
  evidence boundary。
- [x] 只接受 `episodes_complete_pending_d6`，要求两臂同一 clean 40 位提交，arm 状态为
  `complete|reused`，命令除实现选择和输出目录外完全一致。
- [x] 从 runtime profile、summary、execution config、performance diagnostics、module final
  和治理审计确认 `reference_v1/candidate_v2`；缺失、错绑和交叉污染失败关闭。
- [x] 复核规范化在线业务输出、D3 计划谱系、D4 内容地址与确认引用，以及离线真值状态、
  标签、距离事件、summary 和治理审计等价。
- [x] 修复真实 summary 误拒绝：仅放宽 treatment 派生 `episode_id`、final `stage_timings`
  和 final 内重复 observation governance 的 implementation/performance 字段；其余 final
  diagnostics 保持严格比较。
- [x] 输出扫描输入 wall/P50/P95/max、core wall、GNU time elapsed、RSS、实时因子和完整
  execution/performance diagnostics；实现配对变化、正向改善、分布统计和固定 bootstrap。
- [x] 实现 short/long 性能门、core/RSS 非退化门、语义、有限状态、真值隔离和实现身份门。
  `system_realtime_gap_closed` 由候选实时因子独立判断。
- [x] 输出 evaluation/aggregate JSON、逐 pair CSV、中文 Markdown 和一张改善曲线 PNG；
  writer 拒绝 evidence root 内输出并保留消费文件 SHA256。
- [x] 2026-07-24 专项 `15 passed`，覆盖错误实现、dirty/commit、矩阵 SHA、语义差异、
  阶段缺失、非有限数、running 状态、bootstrap/gate 篡改、目录只读、真实 summary
  允许差异和非白名单业务字段拒绝。

### 正式验证

- [x] main 在 clean commit
  `d14285e4fdeb2f2e2cd32fad2f6d42e30f9e73a7` 完成同提交 13-pair 矩阵；26 个 arm
  均为 complete、零退出，manifest SHA256 为
  `760cd0e522b27b99de8c30c366ad7e65f16f783d71cf28e3492be299e24b2402`。
- [x] D6 已独立消费正式 evidence。short 扫描输入平均改善
  `5.360121886647966%`、`9/10` 更快、bootstrap 原始区间
  `[-8.208165356448217%, -3.0841406102053194%]`；long 改善
  `5.142481684491682%`、`3/3` 更快、区间
  `[-8.837128529506151%, -1.6693612946922343%]`。
- [x] 业务语义、有限状态、在线真值隔离、实现身份、核心墙钟和 RSS 门全部通过，
  `d1_optimization_admitted=true`。正式 D6 评估消费缺口关闭。
- [x] JSON、CSV、中文 Markdown 和 PNG 已连同 `SHA256SUMS` 归档到
  `outputs/d1_scan_input_multiseed_20260724_formal_d14285e/`；4.2GB episode evidence
  保持在外部只读目录，没有复制。
- [ ] 系统实时性继续开放。候选最小实时因子为 `0.14342687633969603`，
  `system_realtime_gap_closed=false`；后续仍需 AirSim 和目标硬件容量证据。

`AIRSIM_INTEGRATION_PLAN.md` 和 `EXPERIMENT_REPORT.md` 已检查。本项产生正式三维质点实验结果，
因此已更新 `EXPERIMENT_REPORT.md`。本项没有改变 AirSim producer、日志合同、运行时接口或测试
计划，`AIRSIM_INTEGRATION_PLAN.md` 无需修改。

## 2026-07-24 D1 多 seed 与长时 clean A/B 评估状态

### 已完成

- [x] 新增固定 short `1101-1110 @ 2.2 s`、long `1101-1103 @ 10.0 s` 的预注册矩阵对象。每个
  单元显式绑定 group、seed、duration、两个 episode、两份 GNU `time -v` 和 cross-build JSON。
- [x] 将现有单 pair 校验提升为可复用公开函数，原三轮入口行为保持兼容，原专项 `9 passed`。
- [x] 逐 arm 校验 clean manifest、固定提交、配置/运行配置哈希、200/200/2 规模、有限 summary、
  online truth 为 0、退出为 0和 cross-build 全通过；结构歧义保活开关必须为 true。
- [x] 跨矩阵校验配置只允许顶层 seed/duration 变化，runtime profile 必须一致；缺 pair、重复 pair、
  group/seed/duration 与 episode 不符均失败关闭。
- [x] 新增 `--evidence-manifest` 只读入口，严格接受
  `scalable3d-d1-covariance-limit-multiseed-evidence-v1` 的 completed manifest。内嵌矩阵、
  experiment ID、13 个 case、arm 标签/提交/状态/返回码、证据路径、cross 状态、固定 runtime
  profile、运行参数、bootstrap 和准入门均执行精确校验；该入口与 `--pair` 互斥。
- [x] 按 experiment ID 登记三套不可变矩阵。v1 精确绑定原 reference/candidate commits；v2 精确
  绑定有效 commits、两端 base commits、公共 D2 修复来源和主题，并要求
  `v1_outputs_reused=false`。未知 experiment、任意提交、字段缺失、字段篡改及 v1 混入 v2 谱系
  均失败关闭。
- [x] v3 精确绑定 reference/candidate effective commits、两个相同 candidate base commit、
  公共 D2 修复、公共 D1 半正定修复、reference treatment 提交和主题；证据边界要求
  `v1_outputs_reused=false`、`v2_outputs_reused=false` 及 reference/candidate
  vectorized=`false/true`。v1/v2 注入 v3 字段时失败关闭。
- [x] short/long 均输出每 seed 配对值、均值、中位数、P95、配对相对变化及固定 RNG 的 10000 次
  bootstrap 95% CI。
- [x] 为全部矩阵指标显式定义改善方向。保留原始相对变化和 `candidate_lower_count`，新增
  `candidate_better_count`；实时因子按越高越好统计，其余六项按越低越好统计。Markdown 使用
  “候选更优 seed”，并说明 bootstrap 区间不翻转原始符号。
- [x] 对共同 seed 的 D1 fusion、core wall、external elapsed 分别计算长短单位仿真时间成本增长；
  core wall 与 external elapsed 不相加。
- [x] 实现 short、long、增长率、core wall、RSS、语义、truth 和 exit 的全部预注册准入门。
- [x] 输出 JSON、逐 pair CSV、中文 Markdown 和固定二维 PNG；CSV 明确使用 LF。PNG 上半图展示
  short/long 的逐 seed D1 融合配对改善，下半图展示五项方向化分组均值改善；RSS 不进入主图。
- [x] PNG writer 在 13 个 pair、五项分组指标、有限值和改善方向完整时才写图；缺 pair 或指标
  unavailable 时删除旧图并失败关闭。CLI `outputs` 返回固定 `png` 路径。
- [x] fixture 正例和矩阵缺项、配置漂移、runtime/hold 漂移、cross false、truth/exit、short
  faster/mean/CI/P95、long faster/mean、增长率、core mean、RSS mean/单 pair 等失败关闭路径
  已覆盖；manifest 另覆盖 schema、experiment、矩阵元数据、规模、运行参数、bootstrap、准入门、
  runtime 摘要、arm 状态/提交/返回码、cross 状态及缺失资源篡改。
- [x] D2 观测处置 consumer 保持 exact-match：旧 producer 的 `14/11`
  `known_false_alarm_only_mapping_count` 与持久化明确排除数矛盾时失败关闭；修复后的 `11/11`
  通过，3 个 unavailable mapping 不计入。
- [x] 2026-07-24 验收：多 seed 专项 `69 passed`，D6 全量
  `719 passed, 1 warning in 24.65s`。新增测试固定 PNG 文件名、签名、非空内容、CLI 路径和
  缺 pair/缺指标失败关闭；warning 为既有 Matplotlib `Axes3D` 环境提示。

### 正式 v3 状态

- [x] main 已完成 v3 的 13 个正式 pair、completed evidence manifest 和首次 D6 报告。
- [x] 修复首次报告的实时因子展示方向。short/long 的原始相对变化
  `+3.222%/+3.601%` 保持不变，候选更优计数改为 `10/10`、`3/3`，改善值改为正数。
- [x] 准入门、正式 evidence、提交绑定和 `d1_optimization_admitted` 不受展示修复影响。
- [ ] main 使用同一 completed manifest 重生正式 JSON/CSV/Markdown/PNG bundle；无需重跑矩阵或
  修改 evidence。
- [ ] 该矩阵仅能评价三维质点计算性能。系统实时缺口仍需 AirSim 或目标硬件条件下的独立证据。

`AIRSIM_INTEGRATION_PLAN.md` 已检查。本轮没有修改 AirSim 日志 schema、相机、检测、reset、actor、
控制或 episode 调度，故无需修改。

## 2026-07-24 D1 协方差成对限制向量化准入状态

### 已完成

- [x] 新增显式三轮 pair 输入合同。每轮绑定 reference/candidate episode、cross-build JSON 和两份
  资源记录，不根据路径名称推断实验臂、规模或 seed。
- [x] 复用 scalable 3D 离线读取器核对 clean manifest、配置 SHA-256、场景版本、运行配置、seed、
  规模、summary 有限值、2035 条观测、在线真值零使用和 v2 阶段计时。
- [x] 独立解析 GNU `time -v` 的外部 elapsed、最大常驻内存和退出状态；核心墙钟与外部 elapsed
  分层输出，禁止相加。
- [x] 每轮和聚合均输出 D1 fusion wall、episode 内 P95、D1 scan input、核心墙钟、外部 elapsed、
  RSS 和实时因子，并保留 availability/reason。
- [x] 准入门固定为：业务语义 3/3；D1 融合 3/3 更快且均值至少下降 5%；P95 均值下降；核心墙钟
  不恶化且至少 2/3 更快；RSS 均值和任一轮增幅不超过 5%；有限值、真值隔离和退出状态全通过。
- [x] 正例、CSV 纯 LF 写入和 cross false、配置/seed 不一致、真值非零、阶段缺失、退出非零、
  RSS 越门负例 `9 passed`；D6 全量 `646 passed, 1 warning in 21.65s`。
- [x] 2026-07-24 clean seed 1100 三轮结果通过全部准入门。D1 fusion wall
  `4.014713519 -> 3.595533106 s`，下降 `10.4411%`；P95
  `184.228658 -> 173.330868 ms`，下降 `5.9154%`；核心墙钟下降 `3.1417%`，外部 elapsed
  下降 `3.6310%`，RSS 下降 `0.1429%`。`d1_optimization_admitted=true`。
- [x] 结果固定区分 D1 优化准入与系统实时结论。候选实时因子均值为 `0.215065`，本批仅单 seed、
  2.2 秒、三维质点重复，故 `system_realtime_gap_closed=false`。

### 后续验证

- [ ] main/D1 在多个独立 seed 和更长稳定窗口上复测同一优化，D6 再报告跨 seed 分布、置信区间和
  长时增长率；本批三次重复不能代替独立 seed。
- [ ] D1/D2 提供冻结 truth sidecar 后，另行计算均方根误差、归一化估计误差平方、归一化创新平方、
  身份连续性和严格 ID Switch。性能准入不能替代精度验收。
- [ ] main 运行 AirSim 或明确的目标硬件容量实验后，再评价实时因子、调度抖动和资源上限；当前
  `0.215065` 不能关闭实时 P1。

`AIRSIM_INTEGRATION_PLAN.md` 已检查。本项只消费三维质点写盘 episode、cross-build 和资源记录，
没有改变 AirSim topic、相机、检测、reset、actor 或控制接口，因此无需修改。

## 2026-07-24 D1 原子影子旁路兼容状态

### 已完成

- [x] 保留 `scalable3d-d1-centroid-overlay-shadow-v1` 和历史 prepared-handle 五字段合同；无准备
  审计的历史记录显式归为 `legacy_uninstrumented_runtime_v1`。
- [x] 新增显式 `atomic_experimental_offline_v1` 分派。atomic 模式只读取 preparation、post
  integrity、canonical/shadow digest、materialization、work 和 failure 摘要，不读取
  `evaluation` 或 `shadow_tracks`。
- [x] 严格核对准备计数、操作后完整性计数、原子工作量、accepted/rejected、shadow 物化和失败
  原因。字段半缺、legacy/atomic 混用、未知模式及交叉关系矛盾均失败关闭。
- [x] 历史缺失原子证据时，原子失败与工作量指标保持 unavailable，不补零；D6 仍为只读消费者，
  不参与状态更新、计划、分配或导引。
- [x] 2026-07-24 专项 `25 passed`，D6 全量
  `637 passed, 1 warning in 21.89s`；seed 1100 的 9 条历史 prepared-handle 记录完成只读兼容
  复核，9/9 完整性检查通过。
- [x] clean commit `7cc2d0c` 的 seed 1100、200 对 200、2.2 s control/atomic-shadow pair 已由
  D6 从原始文件独立复核。9/9 atomic integrity 通过，atomic failure/materialized 为 `0/0`，
  accepted/rejected/error 为 `0/46/0`，业务非干预通过且 evidence failures 为空。
- [x] clean pair 的 control/shadow 墙钟为
  `10.735151270986535/19.449935468961485 s`，相对开销
  `0.8117989190825889`；P50/P95/max 为
  `1024.8383930302225/1536.4285601885058/1549.4359389995225 ms`。性能门和 overall admission
  均为 false。

### 后续验证

- [ ] rejected-only 真实输入已提供；main 仍需分别生成至少一个 accepted 和一个 atomic
  fail-closed clean episode，供 D6 复核 shadow 物化、临时工作量和 failure 分布。
- [ ] 在 clean/frozen 同输入多 seed pair 上继续优化和复测。当前单 seed 相对开销
  `81.18%`，未通过 `+5%` 门，且没有有效 treatment 或 outcome evidence。
- [ ] A3/A4 与后续 seed 仍服从 main/D1 的准入顺序；D6 不使用本次兼容接口改变实验调度。

`AIRSIM_INTEGRATION_PLAN.md` 已检查。本轮只扩展可扩展三维离线日志的读取与审计，不改变 AirSim
话题、相机、检测、reset、actor 或控制接口，因此无需修改。

## 2026-07-23 D1 质心发布影子旁路状态

### 已完成

- [x] 新增独立只读适配器，固定消费 topic
  `audit.d1.centroid_publication_overlay_shadow` 和 schema
  `scalable3d-d1-centroid-overlay-shadow-v1`，不导入 main/D1 runtime。
- [x] canonical/shadow SHA 相等/不同、全局航迹编号序列、accepted/rejected/error、拒绝原因和双
  时间戳按字段域输出 availability；缺字段不补零。
- [x] 校验 `digest_semantics`，重算 canonical tracks 与结构歧义 evidence 的前后对象摘要和摘要
  manifest；任一前后变化或摘要语义不一致失败关闭。
- [x] 阶段 `module.d1_centroid_publication_overlay_shadow` 的 P50/P95/max 只从持久化 v2 stage
  timing 交叉核对；P50/P95/max 由 sidecar 的 `evaluation_wall_time_ms` 独立重算。
- [x] generation watermark 当前/峰值/容量、payload 峰值、禁止表面、D2/D3 消费和在线真值使用
  已接入逐 episode 指标。
- [x] 新增独立业务非干预判据。shadow SHA 不同不作为业务变化；判据要求摘要一致、编号不变、
  禁止表面无违规、正式航迹未替换且 D2/D3/truth 消费为 0。
- [x] 接入 scalable episode CSV、聚合统计和中文 Markdown；离线评估 schema 升级为
  `d6-scalable3d-offline-evaluation-v9`。
- [x] 历史未声明 A2 能力的 episode 保持 unavailable，不影响既有正式证据。
- [x] 显式 control/shadow 墙钟配对接口使用 `+5%` 上限输出独立 performance gate；即使业务
  非干预通过，也不自动形成 overall admission。
- [x] 2026-07-23 确定性适配器专项 `11 passed`，scalable 与后验治理联合回归
  `77 passed`，D6 全量回归 `623 passed, 1 warning in 21.67s`。未运行 AirSim 或真实多 seed；
  warning 为既有 Matplotlib `Axes3D` 环境提示。
- [x] development/dirty seed 1100、200 对 200、2.2 s pair 已只读复核。shadow 为
  9 sidecar/46 decisions，accepted/rejected/error=`0/46/0`，D2/D3/truth/forbidden mutation
  均为 0；业务非干预通过。
- [x] prepared pair 的 sidecar P50/P95/max 为 `1009.256/1532.999/1619.053 ms`，payload
  峰值 `11,275,939 B`；control/shadow 总墙钟
  `10.712171729/19.376483415 s`，相对开销比 `0.808828677`，performance gate 失败，
  overall admitted 为 false。

### 后续验证

- [ ] main 提交 A2 生产端后，冻结至少一组包含有效 accepted treatment 的同输入 pair。当前 seed
  1100 的 46 个 decision 全部为 OOSM rejected，不能评价 treatment 效果。
- [ ] main 在 clean 同输入 control/shadow episode 上持久化 v2 阶段分位；D6 报告真实 P50/P95/max、
  watermark 峰值和 payload 峰值，并要求总墙钟相对开销不高于 `+5%`。当前 dirty 单 seed
  `+80.88%` 不能准入。
- [ ] main 提供多 seed 自然结构歧义场景后，D6 再评估 rejection reason 分布、非干预通过率和开销
  稳定性。业务收益需要另行定义 control/treatment 结果，不能由 shadow SHA 差异推断。

`AIRSIM_INTEGRATION_PLAN.md` 已检查。本轮接口仅消费可扩展三维离线总线、summary 和阶段时序，不改变
AirSim 话题、相机、检测、reset 或控制链，因此该文档无需修改。

## 2026-07-23 observation truth v2 状态

### 已完成

- [x] 新增 D6-owned sidecar 校验器，分别接受 main
  `scalable3d-offline-truth-v1/v2` 与 D2
  `d2.scalable3d_observation_truth.v1/v2`，不 import 生产者。
- [x] v1 保留 target-only 兼容；known false alarm 和 unknown 计数为 unavailable，不将缺失能力
  写成 0。
- [x] v2 强制显式 `target | known_false_alarm | unknown`，校验 target identity 的存在性和非目标
  identity 的缺失性。
- [x] 分别输出 target、known false alarm、unknown、missing disposition 的 availability、count
  和 reason，并记录 sidecar schema、来源 SHA-256 和计数来源。
- [x] main sidecar 与 manifest 声明不一致、v2 缺 disposition、未知状态、混合 schema、重复或冲突
  observation 时失败关闭。
- [x] known false alarm 不进入 target mapping；D2 标记为 `known_false_alarm_only` 的 mapping
  必须是 `excluded`、无 truth target、无候选目标。
- [x] unknown 出现时核对 D2 strict identity 与 `id_switch_count` 均 unavailable；D6 不回填 strict
  IDSW。
- [x] `runtime_plan_outcome_join` 校验 raw file hash、D2 manifest/evaluation source hash 和 D2
  disposition audit 三方一致。
- [x] `truth_isolated_offline` 在只消费 D2 归一化结果时，明确从 D2 audit 读取计数，从
  `source_hashes.observation_truth_labels` 接受 provenance；旧 audit 缺 schema 时计数 unavailable。
- [x] scalable episode CSV/aggregate/中文 Markdown、runtime outcome JSON/Markdown 和
  truth-isolated JSON/CSV/Markdown 已接入。
- [x] v1/v2、三态、缺字段、非法状态、identity 冲突、重复冲突、schema/hash/audit 篡改和 unknown
  fail-closed 均有回归。
- [x] 2026-07-23 新增处置及相关专项 `130 passed`，D6 全量
  `586 passed, 1 warning in 21.99s`，scalable learning export
  `5 passed, 1 warning in 3.13s`。

### 后续验证

- [ ] main/D2 用当前 v2 producer 重跑 clean 多 seed episode，D6 再报告真实三态分布、unknown
  原因和 strict IDSW availability；旧 20-seed v1 结果不回写为 v2。
- [ ] 将 AirSim 视觉虚警显式写为 evaluator-only known false alarm，并保持在线总线无
  disposition/truth 后，再做真实 AirSim 回放验收。
- [ ] D2 上游混轨和缺 truth label 修复后，重新计算 strict IDSW/continuity；处置计数和 partial
  lower bound 仍不得替代严格指标。

`AIRSIM_INTEGRATION_PLAN.md` 已检查。本轮只改变离线 evaluator sidecar 消费，不改变 AirSim
运行时消息、相机/检测接口、reset 或控制链，因此不修改该文档。

## 2026-07-22 scalable 3D stage timing v2 状态

- [x] 严格分派 `scalable3d-stage-timings-v2` 与无 schema legacy CSV。
- [x] v2 强制校验完整字段、显式 `distribution_available`、缺失原因、有限非负值、
  `P50 <= P95 <= max`、均值不大于最大值和 stage 唯一性。
- [x] v2 分布不可用时要求三个分位全空且原因非空；可用时要求三个分位齐全且原因为空。
- [x] legacy 无分位列时输出 `null/unavailable`；legacy 有完整三列但无 availability 列时按三项
  完整性推断，半缺数据失败关闭。
- [x] 逐 episode CSV 输出各阶段 P50/P95/max、逐指标 availability 和分布 availability。
- [x] 跨 seed 聚合输出 episode 分位的描述统计、可用 episode/seed 数和缺失原因；原始调用样本
  未落盘时不计算 pooled quantile。
- [x] 中文报告增加阶段尾延时表，明确其为 episode 内调用分位的 seed 分布，并保留规模和证据边界。
- [x] 覆盖正常 v2、legacy、半缺、非有限、顺序错误、重复 stage 和混合 availability；2026-07-23
  当前权威 D6 全量为 `567 passed, 1 warning in 22.96s`。相较 555 项新增的 12 项来自
  `test_truth_isolated_offline.py` 的 3 项独立部分身份合同和 9 项篡改参数化用例。
- [ ] main 使用当前 v2 producer 生成 clean 200 对 200 多 seed episode，并由 D6 v7 重建逐 seed
  CSV、聚合 JSON 和中文报告。
- [ ] main 若要正式称为“稳定窗口尾延时”，需在场景/manifest 中冻结稳定窗口定义；D6 不从目录名
  或 5v5 冒烟自行推断。
- [ ] 如需 pooled P50/P95/max，main 必须另行持久化可审计的原始逐调用样本；D6 不从 episode
  分位反推 pooled quantile。

`AIRSIM_INTEGRATION_PLAN.md` 已检查。本次只扩展三维质点 `stage_timings.csv` 的离线消费和报告，
不改变 AirSim JSONL producer、reset、话题或控制接口，因此无需修改。

## 2026-07-22 clean 20-seed runtime v2 状态

- [x] 独立读取 source manifest、summary、逐 episode `resource_usage.txt`、D6 v6 逐 seed CSV、
  聚合 JSON 和中文报告，确认 seed `1000-1019` 无重复，来源提交和 clean 状态一致。
- [x] 确认 20/20 episode 有限、在线真值使用为 0、分配 hold 为 0、进程退出码为 0。
- [x] 逐 seed 复核 D1 连续完整后验、D2 严格递增且已发布的来源代次、pending 排空，以及两条最终
  守恒恒等式；20/20 generation contract 为 verified、integrity 为 true。
- [x] 确认 D6 schema 为 `d6-scalable3d-offline-evaluation-v6`，基础
  `formal_acceptance_eligible_episode_count=20`，failure reason 分布为空。
- [x] 将 D1/D2 代次统计、D3 覆盖率、D5 绑定数、无 5 m 接近和证据边界同步到 D6 文档。
- [x] 关闭“runtime v2 尚无 clean 未见 20-seed 输入”的 D6-owned P1 子项。
- [ ] 由 main 提供带冻结 experiment-matrix metadata 的完整变体矩阵；当前 matrix episode 为 0，
  20 个输入仍全部是 `descriptive_clean_source_calibration`。
- [ ] 在正式矩阵中补齐 D2 ID switch、物理接近身份、规则/学习配对和因果归因。当前无 5 m 接近，
  不形成物理拦截结论。
- [ ] 将 D6 进程墙钟和峰值内存写入可哈希的运行 provenance。当前 `3:20.42` 和
  `1,448,612 KiB` 仅有 main 侧进程测量，聚合制品不能独立恢复。

`AIRSIM_INTEGRATION_PLAN.md` 和 `subagent_reviews/D6_M_TO_N_EVALUATION_FRAMEWORK_REVIEW.md` 已检查。
本批是三维质点 nominal 200 对 200 的离线证据复核，不改变 AirSim 接口，也不改变 M 对 N 的
pair/target/coalition 分母，因此无需修改。

## 2026-07-22 后验代次合同评估状态

- [x] 分派 runtime v1/v2；v1 字段缺失保持 unavailable。
- [x] 核对 D1 完整后验代次连续性和 D2 来源代次严格递增、唯一及先发布后引用。
- [x] 交叉核对 pending 排空、最终 consumed 等于 D1、D2 消费/发布数，以及消费数加节拍前合并数
  等于 D1 generation。
- [x] 将异常加入 episode 失败原因并阻断 formal acceptance，不修改控制链。
- [x] 将代次、完整性和 availability 写入 CSV、聚合 JSON 与中文报告。
- [x] 增加 D1/D5 性能 JSON 的可选描述性登记，不形成全栈实时声明。
- [x] 规定正负例和报告集成专项 `58 passed`；D6 全量 `542 passed, 1 warning`。
- [x] 复核 clean commit `0d2da25` 的 nominal 200 对 200、10.0 s、三 seed runtime v2：
  3/3 integrity/formal provenance gate 通过，pending 全部排空，失败原因空，在线真值使用为 0。
- [x] 将 v6 评估日期从历史值修正为实际验证日期 `2026-07-22`，并重生成三 seed 报告。
- [x] 已扩展到 clean commit `0d2da25` 的 20 个未见 seed；20/20 代次完整性和基础来源门通过。
- [ ] 由 main 提供完整实验矩阵 metadata。当前 20 个 seed 仍属于
  `descriptive_clean_source_calibration`，不关闭正式矩阵、算法差异或物理效果 P1。

`AIRSIM_INTEGRATION_PLAN.md` 已检查。本次只扩展质点可扩展三维持久化制品的离线消费，不改变
AirSim producer、话题、reset 或控制接口，因此无需修改。

## 2026-07-22 200 对 200 长时三 seed 集成证据

### 已完成

- [x] 复核 main 提供的 clean reference `8f86192` 与 candidate `f80b5bd`，固定 nominal 200 对 200、
  10.0 s、seed `42000/42001/42002`，不混入误配置的 CLI 冒烟目录。
- [x] 确认 candidate 三个 episode 均 `finite_state=true`、`online_truth_use_count=0`、
  `repository_dirty=false`，D1/D2/D3/D5/D7 最终数量与 reference 相同。
- [x] 接受 main 的逐条跨提交语义审计：先验证原始 ACK 载荷 SHA-256，再仅按计划 occurrence/version
  规范 D3 不透明 `plan_id`；owner/version/coalition/`global_track_id`/command 业务字段不归一化，
  三个 seed 均通过。
- [x] 记录 D6 aggregate：episode 3、基础 formal provenance eligibility 3、dirty 0、运行失败原因
  分布为空；证据类别仍为 3 个 `descriptive_clean_source_calibration`。
- [x] 对齐三类性能量测：核心墙钟 `155.895422 -> 150.874890 s`，进程总墙钟
  `222.780 -> 195.363 s`，峰值 RSS `2.888697 -> 2.359147 GiB`，进程残差约
  `66.885 -> 44.488 s`。
- [x] 固定 candidate 写盘后处理总量测
  `39.274048705/41.663056382/40.982858311 s`，均值 `40.639988 s`；reference 缺
  `post_run_timings.csv`，不做跨提交单阶段归因。
- [x] 说明 JSONL 流式校验、D2 identity 一次建索引和 main 规范 D1/D2 视图复用的作用，同时保留
  全记录 truth-like key 扫描、来源 SHA 复算和 D6 offline-only 边界。
- [x] 文档同步后运行 D6 全量回归：`530 passed, 1 warning`；warning 为既有 Matplotlib `Axes3D`
  环境问题，不影响本批无新增图形输出的离线证据。
- [x] 检查 `AIRSIM_INTEGRATION_PLAN.md` 和 `subagent_reviews/D6_M_TO_N_EVALUATION_FRAMEWORK_REVIEW.md`。
  本批是三维质点 nominal 一对一校准，不改变 AirSim 接线或 M 对 N 指标，因而不修改这两份文件。
- [x] 检查文档布局。D6 以根目录 `EXPERIMENT_REPORT.md` 为唯一实验报告，`docs/README.md` 已指向
  该文件；不新建重复且易漂移的 `docs/EXPERIMENT_REPORT.md`。

### 仍开放的 P1

1. 当前只有 3 个描述性校准 seed，未达到至少 20 个未见 seed 的最终验收要求，也没有完整冻结的实验
   矩阵 metadata；`formal_acceptance_eligible` 不得写成最终实验矩阵通过。
2. candidate 实时因子约为 `0.064-0.068`。D1 扫描输入/融合、D2 关联、D5 主动视觉/终端关联、
   D7 导引和总模块栈仍通过超线性判据，实时和长时归一化 P1 未关闭。
3. reference 没有分阶段后处理计时。进程残差包含输出写盘、离线身份/一致性、D6 评估和其他进程
   开销；后续只有在两版都具备同 schema 计时制品时，才能比较单阶段收益。
4. 本批没有形成五米物理拦截、学习策略采用或因果效果证据。缺失层继续保持 unavailable，不从
   `failure_reason_distribution={}` 推断任务成功。

## 2026-07-22 runtime plan outcome join 离线性能闭环

### 已完成

- [x] 在线 JSONL 改为单次流式解码；唯一 key、非有限数、精确 envelope、sequence 和 truth-like key
  仍对全部记录失败关闭，且真值键检查与对象构造合并。
- [x] 仅保留 D1/D2/D3/D7/assignment ACK 联接证据。D1/D2 改存规范整行 SHA，过滤源逐条重算，
  不降低 sequence/payload 绑定强度。
- [x] D2 identity 在原逐帧合同校验后建立一次 `global_track_id` 索引，消除每个绑定窗重扫同一不可变
  frames/mappings 子树，窗口 freshness、歧义和 availability 语义不变。
- [x] 增加 `8f86192` baseline 业务哈希回归，以及被过滤主题中 Unicode 转义 `ground-truth` 的负向测试。
- [x] 保持报告 schema、漂亮打印 JSON、中文 Markdown、admission、contract/control/physical 分层和
  output hash 语义不变；没有添加调用方布尔跳过参数。

### 固定输入验证

2026-07-22 使用 200 对 200、2.2 s、seed 42000 的 development coalesced 制品，input spec SHA-256
为 `1e41bc47...c2c24a`。在线操作数为 63,014,782 B/3380 条，真值检查 3380 条，保留 130 条，
D1/D2 摘要 95 条、D3/D7/ACK 完整载荷 35 条；结果为 3 ACK/594 binding windows。

同进程各 3 次均值：evaluate `5.302515 -> 2.901966 s`，online load
`2.777838 -> 1.506296 s`，D2 identity `1.544734 -> 0.866780 s`，binding windows
`0.451765 -> 0.028150 s`。业务 SHA `7325b468...cec0a7`、JSON SHA `10db5198...58d3` 和
Markdown SHA `97a364f1...5d76` 前后相同。专项 `25 passed`，D6 全量 `530 passed, 1 warning`。

### 仍开放的 P1

1. 在 clean/frozen 的长时、多 seed、20/50/100/200 与非对称 M 对 N 输入上建立正式 wall/RSS 门限；
   本轮单 seed development A/B 不能作为部署容量验收。
2. 若 main 需要跨进程复用真值检查，先定义带 schema、源文件 SHA、禁用键策略版本和验证者身份的审计
   证明，再增加失败关闭快速路径；不得用裸布尔值跳过。当前未实现，独立入口始终重验。
3. 继续优化完整 JSON 解码和规范摘要只能保持严格等价；不得删去 D2 来源复算或在线真值检查。
4. 本次不改变 AirSim producer、episode 编排、控制状态或物理证据。`AIRSIM_INTEGRATION_PLAN.md` 已检查，
   无需修改。

## 2026-07-22 Scalable 3D 批次根发现闭环

### 已完成

- [x] 将 `--episode-root` 从“任意 manifest 目录”改为“三项主 episode 结构”发现合同：
  `manifest.json`、`scenario_config.json`、`summary.json`。
- [x] 排除主 episode 内 D6 truth-isolated、D2 identity、D1 consistency 等 sidecar manifest，
  不依赖目录名、2v2/5v5 标签或真值编号。
- [x] 保留显式 `--episode-dir` 和历史/缺在线日志或其他制品记录；缺失值继续输出
  `null/unavailable+reason`，不补零。
- [x] 状态收口仅处理 available 的合法非负整数；`None`、缺字段和缺文件不再触发 `int()` 异常。
- [x] 将无实验矩阵声明的 clean 输入归类为 `descriptive_clean_source_calibration`，与
  `clean_formal_experiment_matrix` 分开。
- [x] 增加 batch-root、显式 episode、sidecar、批次根缺在线记录仍计入和 summary `None` 的
  确定性回归。

### 验证

2026-07-22 对 `scalable_3d_rule_performance_calibration_20260722_clean_492979e` 运行真实批次根
入口。验收要求为发现 20 个主 episode、sidecar 混入 0、四档各 5 seed、CLI 正常退出、缺实验
矩阵声明不提升为 formal。结果全部满足：20/20 为描述性 clean-source calibration，dirty 为 0，
实验矩阵 formal availability 为 0/20。专项 `46 passed`，D6 全量 `527 passed`。

### 后续边界

该修复关闭批次根离线评估崩溃，不改变 producer schema、控制链或指标公式。后续仍由 main 提供
冻结实验矩阵 metadata、长时物理结果和多 seed 正式输入；D6 不从 clean 状态单独推断算法正式通过。
`AIRSIM_INTEGRATION_PLAN.md` 已检查，本次不改变 AirSim Blocks、ComputerVision、SimpleFlight、
episode reset 或日志接入，因此无需修改。

## 2026-07-22 长 Episode 观测治理标定

### D6 已完成

1. 冻结输出 `scalable3d-observation-governance-calibration-v1`，并定义批输入、episode
   manifest、在线 D1/D2 审计和 evaluator-only 侧车四层公共 schema。
2. 实现外部输入摘要、逐制品摘要、在线审计到 manifest 的摘要绑定，以及侧车到 manifest、
   在线审计和离线真值摘要的三向绑定。
3. 实现 episode 身份、scale 语义、全局唯一 seed、formal clean source、Git/config/schema
   provenance 和在线真值字段扫描的 fail-closed 校验。
4. 实现 D1 扫描 OOSM 和 D2 claim ledger 的 availability-aware 读取；显式零与 unavailable
   在 CSV/JSON/Markdown 中保持分离。
5. 仅从 evaluator-only 侧车读取近邻召回、错误抑制、错误合并和确认时延。比例按 evaluator
   分母报告样本数，并以 episode 重采样计算 95% 自助法置信区间。
6. 输出逐 seed CSV、按规模 aggregate JSON 和中文 Markdown；在线指标按规模给出均值、P95、
   最大值和可用 episode 数。

2026-07-22 专项 `14 passed`、D6 全量 `521 passed`。fixture 覆盖 20/50/100/200 和 7/37 动态规模、available/
unavailable、零事件与真零、哈希篡改、脏正式来源、在线真值字段、跨制品规模冲突、重复 seed、
缺 provenance、非法侧车在线消费及 producer required-path 清单。

### Clean/formal 制品核验

- [x] 独立核验 `observation_governance_calibration_20260722_formal_e4d66db`：输入策略
  `formal_only`，20 episode/20 个互异 seed，四档各 5 seed、每回合 33.75 s。
- [x] 核对来源提交 `e4d66db02a0b8f1b867a0e81b4a73de84588426b`、clean worktree、formal
  evidence tier 和 online truth use=0；20 个 episode 的来源字段一致。
- [x] 核对 D6 为 `offline_read_only_fail_closed`，不导入运行模块，D1/D2 控制修改均为 false。
- [x] 核对四档 D1 重排 12、拒绝/过旧/溢出 0、峰值缓冲 3；D2 峰值 claim/容量为
  2390/4800、6020/12000、12070/24000、24170/48000，安全淘汰为
  285/735/1485/2985，溢出为 0。
- [x] 核对 evaluator-only 近邻召回 1.0、95% bootstrap 区间 [1,1]；错误抑制/错误合并
  为 0、区间 [0,0]；确认时延均值/P95/最大值为 0.25 s。全部指标为 5/5 available。
- [x] 复算 aggregate SHA-256
  `6fb64252292aaedd3c68d1bfea64b76496136ce6edb32add61a281d511c4ed22` 和中文报告 SHA-256
  `6198854b867d39fb2f1300cddeb1f75972ba8b7952361622213050115feb0827`。
- [x] 保持结论边界：该批是快速治理基准 formal 证据，不是精度、AirSim、实时性、完整控制
  闭环或物理拦截验收。

### Development 制品核验

- [x] 只读核验 `observation_governance_calibration_20260722_development`：四档规模各 5 seed，
  共 20 个 33.75 s episode，均为 dirty/development，online truth use 为 0。
- [x] 核对 D1 各档重排 12、拒绝/过旧/溢出 0、峰值扫描缓冲 3；指标可用性均为 5/5。
- [x] 核对 D2 峰值 claim/容量为 2390/4800、6020/12000、12070/24000、24170/48000，
  安全淘汰为 285/735/1485/2985，溢出为 0；指标可用性均为 5/5。
- [x] 核对 evaluator-only 近邻召回 1.0、错误抑制和错误合并 0、确认时延 0.25 s；比例
  指标保留有效分母和 episode bootstrap 95% 区间。200 规模 D1+D2 tracemalloc 口径峰值
  约 58.99 MB。
- [x] 单独核验 `point_mass_integrated_observation_smoke_20260722_development_coalesced`：200 对
  200、单 seed、2.2 s 世界时间、60.21 s 墙钟、实时因子 0.0365、online truth use 为 0。
  该结果标记为全栈冒烟，不并入快速治理基准，也不作为正式性能验收。

### 后续输入条件

1. 已完成同输入、clean commit 的 20/50/100/200 formal 快速治理复跑。后续不得用 development
   制品覆盖该权威记录；新正式制品必须使用新的来源摘要和独立版本标识。
2. 扩大每档 seed 数、episode 时长和近邻/乱序/漏检/高密度压力条件，确认 claim retention、
   缓冲门限和安全淘汰在不同输入下仍稳定。
3. 对实际 D1-D7 质点栈运行多 seed、长时场景；补齐位置/速度精度、身份连续性、计划消费、
   导引许可和 5 m 物理闭环。单 seed 2.2 s 冒烟不用于上述验收。
4. 所有新增指标继续显式记录 availability。缺 truth sidecar、有效分母或血缘时保持 null，
   不以快速基准的 evaluator-only 结果替代全系统精度。
5. D6 只负责只读核验和报告，不参与 D1/D2 参数调节或控制。

## 2026-07-22 active_risk D2 修复后开发期复跑状态

- [x] 只读核对 `/tmp/msm_active_risk_d2_fix_20260722/` 的 manifest、共同检查点报告、D6 sidecar、
  D6 中文报告和 seed 1005 control 离线身份映射；根目录 447 个摘要和 D6 目录 3 个摘要全部通过。
- [x] 确认 seed `1000-1019` 共 20 对；计划消费、导引血缘、物理窗、D4 adoption、配对物理差值、
  配对非退化和降级配对比较均为 `20/20 available`。
- [x] 确认 D4 区域采用 control/treatment=`94/94 + 94/94`，合计 `188/188`；两臂各 `1960` 条命令
  实际写入隔离 world。
- [x] 确认 seed 1005 仅有 5 条 D2 中心航迹离线映射，均为一对一 `unique_lineage_verified`；整批
  online truth use 和 `global_track_id` rewrite 均为 0。
- [x] 保持结论边界：两臂 5 m 成功数均为 0；20/20 非退化仅为描述性隔离比较；production runtime
  ACK 不可用，counterfactual/causal 为 `0/20 available`，不发布降级有效性声明。
- [x] 将本批标记为 2026-07-22 脏工作树 development rerun，不覆盖下方此前 `19/20` 的 clean formal
  历史证据，不把 `/tmp` 大型输出复制进仓库。
- [x] 文档同步后运行 D6 全量回归：`507 passed, 1 warning`；warning 为既有 Matplotlib `Axes3D`
  环境问题。owned-path `git diff --check` 通过。
- [ ] 由 main 在冻结提交和 clean worktree 上重跑同一输入合同并发布可保留正式制品；正式结果形成前，
  本批只用于确认 D2 修复后的证据链完整性。

## 2026-07-22 隔离双臂多周期物理评估状态

- [x] 冻结 `d6.paired-isolated-physical-inputs.v1`：按唯一 seed/pair 列出共享初态、传感器/通信/故障
  日程和 control/treatment 两套独立 arm 制品；逐文件带外 SHA-256，输入清单另由带外摘要绑定。
- [x] 强制 control/treatment 使用不同 episode ID、world ID 和 arm 文件路径；复核同 seed、同场景、
  同初态、同三类外生日程、同仿真时长/步长/5 m 判据及相同真值时间轴。
- [x] 严格复算 D3 plan identity/version/payload SHA、已消费 binding 摘要、隔离消费时间与状态；
  `production_runtime_ack=true` 或生产 ACK 语义一律失败关闭。
- [x] 严格复算 D7 command payload SHA、计划/资源/中心航迹血缘和独立 world application；至少两个控制
  周期且每个已消费绑定具备 `control_applied_to_world` 证据，才开放 guidance lineage。
- [x] 离线身份映射和真值状态与 online 制品分离；online truth use 固定为 0。物理成功按 NED 三维距离
  `<=5 m`，逐绑定生成最近距离、到达时间、错误目标接近和硬约束结果。
- [x] 将每臂可选 `d4_adoption_evidence.jsonl` 纳入显式 spec/manifest 双重声明、路径隔离、SHA-256 和
  前后快照。旧输入为 `not_declared`；显式名义空文件为 `not_applicable`，不自动搜索邻近文件。
- [x] 逐区域校验 D4 adoption 顶层 schema/arm/region/intervention，以及 source/applied plan、场景
  lineage、candidate gate、isolated plan ACK 和 verdict 的 identity/hash/非生产声明。汇总 region、
  available、reason 和 intervention；部分区域不可用时保留汇总并阻断配对降级比较。
- [x] 对齐 D4 公共证据语义：已写入的隔离 ACK 始终独立校验，但仅在 verdict 声明
  `isolated_plan_consumption_ack_available=true` 时绑定 verdict `ack_id`；未准入 ACK 可保留审计且
  verdict 编号可为 null，不提升 adoption availability。
- [x] 输出九层 availability。一般物理 effect 保持既有依赖；`d4_degraded_adoption` 还要求两臂区域和
  intervention 对齐，`degraded_paired_physical_comparison` 再要求计划消费、导引和物理窗均可用。
  `counterfactual/causal` 始终 unavailable；完整结果只称为 paired isolated simulation comparison。
- [x] 输出逐 seed 和严格完整覆盖聚合，包括两臂成功数、最近距离、到达 5 m 时间、硬约束、错误绑定
  及 treatment-control 差值；写盘生成 sidecar、中文报告、provenance 和 checksum，输入前后摘要一致。
- [x] 合成合同专项 `24 passed`，D6 全量 `507 passed`。测试覆盖旧输入、名义空文件、D4 有效/部分
  区域、未准入但可审计 ACK、文件缺失和 SHA 篡改、声明不一致、arm/region/seed/plan/ACK 篡改、
  available 状态矛盾、生产 ACK 冒充和命令血缘错配。
- [x] main 当前 20 seed producer 路径已把 D4 文件写入 arm manifest 和 D6 input spec；集成专项
  `1 passed`，真实嵌套合同可被 D6 独立校验。
- [x] 只读复跑 `active_risk` seed `1000-1019`：计划消费/导引血缘 20/20，物理窗 19/20；两臂各
  98 个区域均无可用 D4 adoption，原因合计 strict-new 188、scenario-invalid 8。D4 adoption、降级
  比较、聚合物理差值/非退化、counterfactual 和 causal 均按证据保持 unavailable。
- [ ] 以 clean、冻结、可保留的正式多 seed 降级场景发布逐 seed/聚合 sidecar，并预先定义比较问题和
  识别假设。当前合同与集成测试不能关闭策略有效性、反事实、因果、PPO、assist 或 authority GAP。

`AIRSIM_INTEGRATION_PLAN.md` 已检查。本次合同面向 scalable 3D 隔离质点 world，不改变 AirSim
Blocks、SimpleFlight、ComputerVision、episode reset 或现有生产 ACK 接线，因此无需修改 AirSim 计划。

## 2026-07-22 D3/D4 保留 seed v1/v2 审计状态

- [x] 以顶层 schema 严格分派 `scalable3d-reserved-seed-interventions-v1/v2`；保留 v1 默认 API 常量、
  既有位置参数顺序、fail-closed 语义和测试。CLI `--profile v1|v2` 同时绑定预期 source schema；
  同 schema 可覆盖路径/带外摘要，跨 schema profile 失败关闭，默认消费新 v2。
- [x] 对 v2 绑定 source commit `78912963b67fe86ee9a8d29186b18a9dd60c460c`、`SHA256SUMS`
  `821f1503...72bc`、manifest `d6ef23b2...883c`，并重算全部成员、artifact SHA、20 条 lineage、
  seed 目录、dirty/truth/共享标志及 D3/D4 40 arm identity。
- [x] 校验 D3 safety shell v2/config SHA 的 40/40 arm 绑定；重算 treatment applied/fallback=`20/0`、
  20 对选择 identity、规则基准 assignment cost、安全/churn 指标和 linear P95 inference latency。
- [x] 校验 D4 arm evidence v2 和 confidence/OOD/latency/finite/failure 五个分门字段；从 20 条
  treatment evidence 重算各门计数、置信度/时延分布、拒绝原因，并与 source manifest 嵌套汇总一致。
  `treatment_candidate_latency_ms` 使用 nearest-rank P95=`2.241315 ms`；gate summary 使用 linear
  interpolation P95=`2.264415 ms`，两者不混写。
- [x] availability 分层：offline assignment comparison 可用；runtime ACK、physical outcome、
  counterfactual、causal、paired physical outcome/effect/non-degradation 均保持 `null+unavailable`。
  D4 零采用不补效果 0，nominal 5v5 不解释为降级策略评估。
- [x] 输出 v2 JSON sidecar、中文 Markdown、provenance manifest 和 `SHA256SUMS` 到
  `outputs/reserved_seed_interventions_nominal_5v5_1000_1019_formal_7891296_d6_profile_bound_v2_audit_20260722/`；
  固定时间 `2026-07-22T04:56:47Z`，输入目录保持只读，输出 checksum 复算通过，同时间戳四文件
  逐字节复生通过。
- [x] 测试内构造合同完整 v2 fixture，无 ignored output 时仍覆盖 v2 成功路径、availability、D3
  safety-shell、D4 evidence schema/门字段和 manifest 汇总篡改。正式 bundle 存在时继续复算权威 v1/v2；
  sidecar/provenance 均断言 schema binding，同时间戳 writer 逐字节复生纳入测试；专项 `18 passed`、
  无权威输出路径 `16 passed`、D6 全量 `483 passed`。
- [ ] 取得严格绑定的 runtime ACK 和采用后物理状态窗后，另行生成 paired physical outcome/effect；
  当前同帧离线 assignment comparison 不用于 promotion、PPO、assist、authority 或因果验收。

`AIRSIM_INTEGRATION_PLAN.md` 已检查。本次只读消费 scalable 3D JSON/JSONL，不改变 AirSim runtime、
episode 编排、控制或 AirSim 输入合同，因此不修改该计划。

## 2026-07-21 D3/D4 保留 seed 隔离执行审计状态（历史 v1）

- [x] 新增 D6-owned 独立只读 consumer，显式接收输入目录、输出目录、审计时间和七项带外 identity
  binding；输出位于 D6 ignored `outputs/`，输入目录及其子目录禁止写入。
- [x] 复算 `SHA256SUMS`、顶层 manifest 文件 SHA、五个成员文件及 manifest 内全部 artifact SHA；
  审计前后六个输入文件的集合摘要一致。
- [x] 验证 20 条 lineage 精确覆盖 seed `1000-1019`、源提交
  `6d5bfead31d53258b020a5f157b2ad5e7f25ee35`、dirty=0、nonfinite=0、online truth use=0，
  同源/随机/通信/故障四类配对标志均为 20/20。
- [x] 独立核验 D3 40 arm/40 receipt、20 control/20 treatment、pair input identity、bundle digest、
  arm spec/plan payload 内部摘要；重算 control 状态 `15/3/2` 和 treatment `0/20` applied、
  `20/20 out_of_distribution` fallback。
- [x] 独立核验 D4 40 specification/40 evidence、20 control/20 treatment、pair input/lineage、candidate
  bundle 与 specification identity；重算 `0/20` treatment safe-adopted、
  `20/20 candidate_threshold_or_finite_gate_rejected` fallback。
- [x] 将 receipt/candidate inference latency 与 outcome 分层。D3 n=20、mean/P95=`0/0 ms`；D4 n=20、
  mean=`8.291408 ms`、median=`1.196097 ms`、nearest-rank P95=`35.255481 ms`、max=`42.301505 ms`。
- [x] 固定 availability：execution receipt 可用；runtime ACK、physical outcome、counterfactual 和 causal
  不可用。零 treatment adoption 时 paired outcome/effect/non-degradation 必须为 `null+unavailable`，
  禁止填 0 或发布候选有效、非退化、反事实和因果声明。
- [x] CLI 原子生成 JSON sidecar、中文 Markdown、provenance manifest 和 `SHA256SUMS` 到
  `outputs/reserved_seed_interventions_nominal_5v5_1000_1019_d6_audit_20260721/`。
- [x] 2026-07-21（UTC `2026-07-22T04:06:26Z`）专项 `7 passed`、D6 全量 `472 passed`；输出
  `SHA256SUMS` 二次校验通过，仅有既有 Matplotlib warning。
- [x] 历史 v1 已发布目录保持不变。当前 consumer 新生成 v1 时会序列化预期 source schema，属于
  profile-bound provenance；历史哈希只描述旧制品，不作为当前代码的可复生哈希。
- [ ] main/D3/D4 后续若产生严格绑定的实际采用 ACK 和采用后的物理状态窗，再由 D6 生成新的 outcome
  sidecar。当前制品不得用于策略 promotion、线上 assist/authority 或因果收益验收。

## 2026-07-22 D5 paired-shadow 权威 v2 独立审计状态

- [x] 新增 D6-owned 显式输入合同，要求 v2 report/lineage、held-out corpus/evaluation、模型包、D5
  源实现和 superseded report/lineage 的路径及带外 SHA-256；不搜索相邻输出。
- [x] 复算 producer report content SHA、input spec SHA、全部 input binding、2702 项 corpus inventory
  和 7 个 implementation SHA；审计前后 2718 项输入集合哈希一致。
- [x] 验证 seed `1000-1019`、45 cell、900 lineage、74024 条已标注候选边，无缺失、重复或额外记录；
  每帧 `loaded_graph_instance_count=1`，图、候选边和标签 identity 均为 1.0。
- [x] 重新聚合逐 seed、逐 cell 和总体边级/簇级混淆计数及延时；45/45 cell 无质量退化，模型未增删
  候选边，同相机边、未标注边、online truth 和 `global_track_id` 改写均为 0。
- [x] 独立筛查 14 个边特征的单变量标签可分性。中心绑定计数恒为 0，中心投影马氏距离区分力弱；三类
  尺度/角速度差特征近确定性可分，最强特征覆盖 35/45 cell。
- [x] 输出 JSON、中文 Markdown、manifest 和 `SHA256SUMS` 到
  `outputs/d5_paired_shadow_e39a54d/`。paired-shadow=`complete`，research shadow 仅带合成可分性限制。
- [x] 保持 G1/PPO/assist/authority=false、rule fallback=true，不改变线上准入、默认路径和冻结报告。
- [x] 运行专项和 D6 全量回归：`8 passed`、`465 passed`；执行 `SHA256SUMS`、JSON/manifest 内容摘要
  和 `git diff --check` 校验。
- [ ] 生成去除或随机化近确定性合成特征、独立相机噪声和外参偏差的数据，重复 no-center-feature
  paired shadow；形成该证据前，外部泛化状态保持不足。

## 2026-07-21 D5 clean 图数据准入状态（v2 前置阶段）

- [x] 新增八类显式 D5 数据制品及逐文件带外 SHA-256 合同；禁止隐式发现 ignored output。
- [x] 复核内部 content SHA、正式/补充来源绑定、60/20/20 seed、保留 seed 零重叠、正负边、未标注
  0、45 个场景规模单元、dirty=false 和来源未改写。
- [x] 将数据支持、训练来源、模型内部测试、保留 seed、paired shadow 分层输出；数据通过不触发
  G1、assist、authority 或正式 PPO reward。
- [x] 为未来模型报告固定权重 SHA、配置 SHA、训练来源 SHA、测试指标、45 cell 指标和 latency
  合同；缺项、伪造字段和门限降低均失败关闭。
- [x] 将显式输入清单升级到 `d6.d5-clean-graph-inputs.v2`，held-out evaluation report/manifest 只能
  成对提供；v1 仅兼容无 held-out 的旧结构，新增字段在 v1 下按未知字段拒绝。
- [x] 严格消费 D5 held-out v1 report/corpus manifest：双重 SHA、精确 20 seed×45 cell=900 episode、
  内部 model weights/bundle manifest、冻结 validation 温度/阈值、零权重更新、零 online truth/
  同相机边/未标注边和零 `global_track_id` 创建换绑均独立复核。
- [x] held-out 指标通过只完成 `held_out_seed`；指标失败输出 `failed`/producer `fail_closed`；缺制品
  输出 `unavailable`。paired shadow 未提供时 G1/assist/authority 始终 false，规则回退始终 true。
- [x] 提供包级公开 API、带外清单哈希 CLI、JSON/中文 Markdown 报告和 34 项专项合成回归。专项
  `34 passed`，D6 全量 `457 passed`，仅有既有 Matplotlib `Axes3D` warning。
- [x] 已登记冻结模型、seed `1000-1019`、45 cell、900 帧 held-out corpus/report，并由上节消费者完成
  权威 v2 配对审计。该完成项只关闭合成 held-out/paired-shadow 执行与核算层。
- [x] 同 seed paired formal shadow 已运行并由 D6 独立复核；合成可分性使外部泛化和线上准入继续
  fail closed，G1/assist/authority 保持 false，规则回退保持 true。

## 2026-07-21 运行时 ACK 到离线结果联接状态

- [x] 新增 D6-owned `RuntimePlanOutcomeJoinInputs`，固定 11 类显式文件路径与调用方带外 SHA-256；不
  搜索邻近文件，不修改冻结的 900-episode 正式数据。
- [x] 校验 episode manifest/config 规范摘要、当前 world/bus/scenario schema、实际 target/resource
  数量、物理时间轴和固定 5 米事件口径。
- [x] 对每条 `runtime.assignment_plan_ack` 复核 D3/D7 来源 sequence、来源 topic/source/schema、
  规范 payload SHA、plan id/version、assignment/binding 全覆盖及计数。ACK envelope sequence/时间戳
  形成唯一 occurrence；同 plan identity 的显式 refresh 仅在执行签名不变时允许。重复 sequence、
  同版本签名漂移、陈旧版本、额外绑定和 ACK 自报 outcome/reward 均失败关闭。
- [x] 独立校验 D2 identity evaluation、manifest、D1/D2 源记录、观测真值标签和 evidence 文件哈希；
  只允许 `source_observation_lineage` 唯一映射，禁止名称、距离或接近事件反推身份。
- [x] 按同一资源的相邻 ACK 建立不重叠窗口，输出映射 availability、首末/最小三维距离、距离进展、
  正确目标和其他目标 5 米事件，并保留原始 D3 learning 与 D4 regional evidence。
- [x] 新增有界配对进展诊断。只有 accepted ACK、D7 binding 实际 applied、非 hold、唯一 D2 映射和
  完整状态窗同时成立时才可用；正式 D3 PPO reward、counterfactual 和 causal attribution 始终为
  `null+reason/unavailable`。
- [x] CLI 通过带外 SHA-256 加载显式输入清单并输出 JSON、中文 Markdown。专项 `22 passed`，D6
  全量 `423 passed`；仅有既有 Matplotlib warning。
- [x] 真实 main 3v3、recon=1、seed=70、1.2 秒回归形成 2 个 ACK occurrence 和 6 个非重叠 binding
  window；其中 1 个为合法 evaluation refresh，online truth=0，三类学习权限保持 false。同版本修改
  binding/coalition 的负例失败关闭。
- [ ] main 将 11 类输入及 SHA 清单接入每个真实 episode 的离线阶段，并将 D6 输出登记到 episode
  manifest。D6 本任务只提供 API/CLI，不跨所有权修改 main runtime。
- [ ] 运行同 seed paired formal shadow 和规则基线，取得学习动作实际采用、可归因终局结果及保留 seed
  `1000-1019` 多 seed 证据。在这些条件满足前继续保持 PPO=false、assist=false、authority=false 和
  rule fallback=true。

## 2026-07-21 跨模块学习数据联合准入状态

- [x] 扩展 D6-owned 联合审计 API 与 CLI，显式接收 D3、D4、D5 三份全样本审计路径和调用方带外
  文件 SHA-256；报告不记录输入绝对路径，不修改 producer artifact。
- [x] 对三份审计重新校验 schema/date/purpose、文件与规范内容 SHA-256、producer audit、完整计数、
  expected/actual binding、binding checks、canonical 60/20/20、truth/dirty/finite/version/identity/
  constraint 零违规和 complete 状态。任一缺失、篡改、错绑定或权限误开均 fail closed。
- [x] D3 正式全样本覆盖 900 episode/1604 decision frame/3,658,815 candidate edge/117,304 selected
  action/43,905,780 finite feature value；D4 正式覆盖 900/1798/14384，补充课程覆盖 100/300/1200。
- [x] 精确复核 D5 supplemental 的 100 episode/1200 sample、canonical episode=`60/20/20`、sample=
  `720/240/240`、online/offline/descriptor=`100/100/100`、checksummed/verified=`302/302` 和有限特征
  `1200/1200`。
- [x] 复核 online truth、reserved seed、dirty episode、非有限特征以及 D5 创建/改写/换绑
  `global_track_id` 均为 0。四类 offline label 保持 unavailable 且未补零。
- [x] D5 synthetic ACK applied/rejected/missing=`400/400/400` 仍标为确定性故障注入；任何 runtime
  evidence 提升或 PPO/assist/authority 误开均失败关闭，规则回退保持 true。
- [x] 准入矩阵发布 D3/D4/D5 full-sample 和跨模块 structural full-sample=`complete`，overall admission=
  `partial`。BC canonical view 与结构证据可供开发读取，但不能据此开放模型或控制权限。
- [x] 真实输出位于 D6 `outputs/cross_module_learning_admission_20260721/`；JSON/Markdown SHA-256 为
  `6593ee8a...87f5`/`7b6480d0...a4ba`。专项 `37 passed`，D6 全量 `401 passed`；仅有既有
  Matplotlib `Axes3D` 环境 warning。
- [x] D3/D4 producer 已完成逐样本、文件集合和身份审计；D6 通过显式路径与带外 SHA 独立消费并关闭
  structural full-sample 层。
- [ ] producer 持久化真实 action adoption、版本绑定、runtime ACK、可归因 reward/outcome 和终局结果；
  D6 不从 synthetic ACK、相邻状态变化或 unavailable 标签补造这些证据。
- [ ] D5 同 seed paired shadow 与保留 seed 核算已经完成；跨模块 D3/D4 的因果/反事实、真实动作采用
  和终局结果仍未完成。合成可分性也尚未关闭外部泛化门；继续关闭 PPO、在线 assist 和 authority，
  并强制规则回退。

## 2026-07-21 历史 canonical seed split readiness 状态

以下清单记录 detached canonical views 生成前的原始 manifest 审计。当前状态以上一节为准，正式
900 episode 源 manifest 继续冻结。

- [x] 新增 D6 自有、纯文件的 canonical split 审计，不导入 main runtime，不修改 D3/D4/D5 manifest。
- [x] 校验 `scalable3d-shared-seed-split-registry-v1` schema、policy、content SHA-256、assignment
  SHA-256、源 training registry SHA-256、100 个训练 seed 完整覆盖和 `1000-1019` 保留 seed 隔离。
- [x] 独立复算 `d3_numeric_seed_atomic_split_v2` 的 60/20/20 数值 seed assignment；仅信任哈希不足以
  通过 readiness。
- [x] 审计 D3 assignment、D4 region、D5 tracklet graph、D5 active-vision manifest，输出各模块原
  split hash、seed 数、missing/extra/reserved/mismatch，以及可靠层级的 episode/sample mismatch。
- [x] 联合训练门改为四个 required module 全部 canonical exact 才 available；不一致时保持
  `false/null+reason`。未传 registry 时继续使用旧 D4/D5 readiness，兼容既有调用。
- [x] CLI 新增显式 `--shared-seed-split-registry`，audit-only 和 detached sidecar 两条路径均支持；
  registry 身份进入 readiness/source，已有 bundle 不会静默复用不同 registry。
- [x] 2026-07-21 正式 900 episode 全量只读审计通过源哈希检查。D3 exact；D4 mismatch 为
  51 seed/459 episode/917 frame；D5 graph 为 65 seed/8350 graph record/284 candidate edge；D5
  active vision 为 62 seed/558 episode/713298 sample。联合训练 unavailable。
- [x] 测试覆盖 exact、content/assignment tamper、source SHA mismatch、registry missing/extra/reserved
  seed、D3/D4/D5 mismatch、模块 missing/extra/reserved 和无 registry 兼容。2026-07-21 D6 全量
  `364 passed`；接受门限为注册表八项 validation 全真且四模块 exact，本次联合门未通过。
- [x] main/D4/D5 已采用 detached registry 生成规范 split views。正式 900 episode 源 manifest 保持
  冻结；D6 已通过顶部联合审计核对这些视图，并独立消费 D3/D4/D5 producer 全样本报告。跨模块
  structural full-sample 已 complete，overall admission 仍 partial。
- [ ] 共享 split 只关闭数据泄漏治理条件。D4/D5 reward、runtime ACK、动作多样性和 PPO 条件仍按原
  GAP 独立开放，不能由 split exact 自动晋升。

## 2026-07-20 正式离线 outcome/reward 标签状态

- [x] 实现只读 `audit_learning_label_readiness()` 和 CLI，校验正式生成计划、finalized checkpoint、
  100 个训练 seed、20 个保留评估 seed、900 episode index 及 D4/D5 全量文件哈希。
- [x] 实现 detached sidecar 写入和 bundle 自审计。输出目录不得位于正式学习数据源内部；manifest、
  SHA-256、规范 JSON、确定性 gzip 和原子目录发布均已接线。
- [x] 固定 outcome、reward、counterfactual、causal-label 四层 availability 合同。不可用值使用
  `null+reason+provenance`，不以 `0` 表示缺失。
- [x] D4 只从时间窗内相邻 frame 生成区域纯观测转移。正式数据没有推荐采用/执行摘要，故奖励和 PPO
  fail closed；规则 recommendation 可作为行为克隆输入，但当前动作全为零 quota、无 hold/replan/
  transfer，不能据此晋升策略。
- [x] D5 只从同相机时间窗内相邻 snapshot/projection 生成纯观测转移。奖励硬门要求 runtime ACK；
  接受 ACK 还要有版本一致、时间在 ACK 之后的 camera feedback。相邻姿态变化不作为动作应用证据。
- [x] 固定 seed `1000-1019` 为保留评估集，训练标签发现重叠时立即失败。在线 truth-like 字段、对象键
  篡改、模块内 split/identity 不一致和 source hash 变化均 fail closed；跨 D4/D5 split 不一致则保留
  单模块 sidecar，并明确阻断联合训练。
- [x] 2026-07-20 正式 900 episode 审计完成：D4 outcome `898/1798`、reward `0/1798`；D5 outcome
  `1,063,214/1,153,242`、reward `0/1,153,242`、runtime ACK `0`。D4/D5 行为克隆合同可用，PPO、
  counterfactual 和 causal training 均不可用。D4/D5 split 有 423 个 episode 不一致，联合训练不可用。
- [x] 17 项专项测试覆盖接受/拒绝/缺失 ACK、无后继、D4 无归因、schema/identity/split、跨模块 split、保留 seed、
  unavailable 空值、文件篡改、原子写和重复运行确定性。
- [x] 验证日期 2026-07-21：专项 `17 passed`，D6 全量 `351 passed`；审计输出中的证据日期保持
  2026-07-20，未启动 AirSim。

### Producer 准入条件

- [ ] D4/main 在 frame 关闭前持久化版本化 recommendation consumption/adoption、applied digest、
  plan/epoch/lease 绑定和 post-action 状态；同时增加非零 quota、hold、replan、transfer 覆盖。未补齐前
  D4 PPO 保持 unavailable。
- [ ] main 调整 active-vision 生成顺序，使 D5 样本在 episode 最终化前连接
  `runtime.camera_command_ack`，并将运行态最近接受的命令版本写入相机反馈。现有正式数据不得原地
  回填或根据姿态反推 ACK。
- [ ] 若训练奖励包含任务完成，另提供明确的终端任务结果和归因时间窗。PPO 还需 on-policy log
  probability/value；反事实或因果训练需同初态配对重放或受控干预。
- [ ] main/D4/D5 冻结共享的 seed-atomic split registry 后，重新导出或生成只读规范 split sidecar；完成
  前 D4 与 D5 只能分别训练和评估，不能混成联合训练集。

## 2026-07-20 scalable 3D 实验矩阵审计状态

- [x] 只从 `scenario_config.metadata` 读取矩阵 schema、variant、comparison key 和 full-system flag；
  历史 episode 的矩阵字段保持 unavailable，不从目录名补值。
- [x] 独立核对 R0/G1/A1/A2/A3/C1/F1 与 learning runtime diagnostics，bundle 未加载、effective mode
  非 assist、实际采用缺失或规则回退时 `variant_execution_valid=false`。
- [x] 固定每个 comparison identity 的 R0/G1/A1/A2/A3/C1 分母；仅三个完整体系场景增加 F1，缺 cell
  和重复 cell 均显式保留。
- [x] 按 variant 输出 episode/seed、有限性、在线真值、硬约束、ID switch、分配、跨视角、主动视觉、
  五米事件和阶段耗时的 availability-aware 描述统计。
- [x] 对完整 R0 配对输出 variant-minus-R0 delta；至少两个比较键才生成 bootstrap CI。clean/formal 与
  dirty development 分开，所有 paired delta 保持非因果口径。
- [x] producer 风格矩阵专项 `40 passed`，D6 全量 `320 passed`；真实 R0/nominal/2v2/seed101 dirty
  smoke 复读为执行有效、cell 完整性 1/6、正式矩阵资格 false；临时 5v5 producer smoke 的 D4 消费、
  D3 hint applied 和 control adoption 均为 1。
- [ ] main 尚未运行 clean、完整 R0/G1/A1/A2/A3/C1/F1 矩阵。没有正式算法优劣或准入结论。
- [x] D4 advice 与 main 消费证据分层审计；缺消费、旧 schema、未知或篡改 advice、summary 冲突均
  fail closed。有效消费且 D3 明确应用 hint 时，A2 可形成实际采用证据。
- [ ] 若要发现整个 comparison key 完全缺失，main 需把 matrix manifest 作为显式 D6 输入；D6 不从
  目录结构重建未出现的 key。

## 2026-07-20 scalable 3D schema registry 历史状态

- [x] 将两套 D6 fixture 的 online observation schema 对齐真实 producer：
  `scalable3d-observation-v1`。
- [x] 增加 D6-owned `d6-scalable3d-schema-registry-v1`，核对 world、bus、scenario、online observation、
  offline truth 和 scenario config schema，不导入 main runtime。
- [x] 保留原始 schema 字段；另输出逐项 expected/match/status/reason、整体 match 和 registry version。
- [x] 将整体 current-schema match 纳入 formal acceptance；旧、未知、篡改或缺失 schema fail closed，
  但仍可作为 descriptive historical row 展示。
- [x] 增加当前匹配、五项 manifest 不匹配和缺字段测试；专项 `32 passed`、D6 全量 `304 passed`。
- [x] 复读 6v6/seed37 当前 producer smoke，schema match=true；formal 仍只因
  `repository_dirty=true` 被拒绝。
- [ ] 后续新增 producer schema 时，必须先更新 registry 版本和迁移说明；未知版本不得自动准入。

该段记录 v1 registry 的历史实施。2026-07-23 已按本文顶部计划升级为 registry v2 和 offline truth
v2，并保留 v1 只读兼容。

## 2026-07-20 scalable 3D 主动视觉证据闭环状态

- [x] 将 D5 active-vision publication 与 main camera-command ACK 作为两层独立写盘证据消费；D6 不
  导入 scalable runtime，不参与相机控制。
- [x] 区分 rule command、有效 shadow suggestion、assist adopted、ACK applied/rejected 和 physical
  outcome；shadow 实际发布的规则动作不误计为 assist，assist adopted 不自动成为 applied。
- [x] 以 camera/resource、issued timestamp、plan/coalition/communication version、intent 和 mode
  关联命令与 ACK，统计完成率、未 ACK、意外 ACK、P50/P95/max 延迟和拒绝原因。
- [x] 拒绝原因拆分为过期/未来命令、过时计划/联盟/通信版本、相机或资源不可用和其他原因；summary
  四项计数及 reason distribution 与日志交叉校验。
- [x] `target_global_track_id` 只与此前 D2 中心航迹快照核对，并检查 ACK 原样回传；缺 D2 快照为
  evidence incomplete，未知引用或 ACK 改写使正式证据 fail closed。
- [x] 单独统计主动视觉在线 truth-like 字段违规；缺 active-vision/ACK 日志时指标为
  null/unavailable，不用 summary 的零替代缺失日志。
- [x] 物理归因保持 null/unavailable。assist applied 与同 episode 五米接近不能替代同 seed 配对规则
  控制组；当前 producer 尚无正式 paired-experiment 合同。
- [x] 按实际 target/resource/recon/camera 数量和不同 seed 聚合。2026-07-20 主动视觉专项 8 项、合并
  scalable 专项 `25 passed`、D6 全量 `297 passed`，仅既有 Matplotlib warning；未运行 AirSim。
- [x] 用当前 main runtime 运行 6v6/recon1/camera7、seed 37、2.2 s 临时 smoke；133 issued=133 matched
  ACK=133 applied，reject/target-reference violation/truth violation 均为 0，summary match=true。该输入
  `repository_dirty=true` 且只有单 seed，仅证明 v3 consumer 与当前未提交合同兼容，不计正式 evidence。
- [ ] main 在 clean worktree 生成至少 20 个未见 seed 的 rule/shadow/assist episode，确认命令、ACK、
  summary 和拒绝原因分布在真实持久化产物中闭合。
- [ ] main/D5 若正式开展效果归因，冻结同 seed 配对的规则控制组/assist 处理组、模型 bundle/hash、
  场景配置和实际 adopted+applied 证据；D6 再增加跨 episode 配对效应与置信区间，当前不得先写提升值。

## 2026-07-20 scalable 3D 学习运行时离线评估状态

- [x] 保持纯文件、只读、无控制边界；交叉消费 config/summary 的
  `scalable3d-learning-runtime-v1`，不读取在线真值，不导入 scalable runtime。
- [x] D3/D4/D5 分别发布 requested/effective mode、bundle requested/loaded、fallback、runtime
  version、学习模型 fingerprint/version availability；缺字段或 bundle 未加载为 null/unavailable，
  不用规则 version 冒充模型 version。
- [x] 只接受 topic `modules.d4.region_resource_advice` 的
  `d4-region-resource-advisory-runtime-v1`；逐 episode 统计发布/合法/非法、mode 分布、shadow 输出、
  assist eligible、fallback/reason、latency P50/P95、quota 守恒、projection rejection、正式裁决
  unchanged/mutation 和 stale/missing version evidence。
- [x] 对 recommendation schema、scenario/version/seed、authority digest、plan/version/epoch/lease、
  action/transfer/projection、digest flag 做 fail-closed 审计；非法或旧 schema 不缩小分母。
- [x] 报告五层证据：bundle load、shadow output、assist gate、control adoption、physical outcome。
  advice 不改变正式 D4 裁决，`assist_eligible` 不晋升为控制生效；control adoption 只来自通过完整合同
  和 summary 一致性审计的 main 消费记录及 `d3_hint_applied=true`。
- [x] 聚合继续按实际 target/resource/recon/camera 和不同 seed；单 seed descriptive-only。正式证据
  继续要求 `repository_dirty=false`，并校验 config hash、D4 policy version、finite/truth isolation。
- [x] 2026-07-20 确定性 fixture 覆盖 disabled、D3/D4/D5 missing-bundle fallback、assist-to-shadow、
  assist gate、守恒/非守恒、projection rejection、mutation/unchanged、digest 篡改、旧 schema、缺
  plan version、缺 advice 和 seeds 1/2 bootstrap；scalable 专项 `17 passed`、D6 全量 `289 passed`，
  仅既有 Matplotlib `Axes3D` warning。
- [ ] main 用 `repository_dirty=false` 的正式多规模、多 seed 学习 bundle 运行 CLI，冻结 bundle、
  shadow、assist、control 和 physical 五层跨提交趋势；fixture 或 dirty smoke 不作为模型验收。
- [x] producer 已发布独立 `d4-region-resource-consumption-v1`，携带完整建议合同、当前 snapshot、时间、
  consumable/rejection、bridge reason 和 D3 hint applied；D6 不从 advice 或模式字段推断采用。
- [x] D2 producer 已发布 evaluator-only lineage identity evaluation，并新增版本化 partial
  diagnostics；D6 只消费 producer 的 coverage/count/lower-bound 汇总，不从名称、终态、距离或
  邻近事件补算映射。strict IDSW 继续只接受 producer 明确 available 值，partial lower bound
  不回填 strict 指标。
- [ ] main 重新生成正式多规模、多 seed identity evaluation/manifest 后，再把 partial coverage、
  blocker、anchor exclusion 和 lower-bound 分布接入学习运行时最终证据；当前合同 fixture 不作
  模型或物理效果验收。

## 2026-07-15 legacy provenance 与三档 comparator 完成状态

- [x] 对路径输入且 summary/cases/rows 全无 ClockSpeed 的 legacy suite，按 20 个注册 `case_id` 定位
  sibling generated settings；20/20 文件、显式键、有限正数和全量一致均为强制门。
- [x] 保持 mapping 输入无文件系统发现、目录名不推断、无默认 1.0；部分显式 provenance 不能触发
  fallback，缺文件/缺键/冲突/非有限值 fail closed。
- [x] 用真实 1.0/0.2/0.1 各 20 case 生成 JSON、两份 CSV、中文 Markdown 和 PNG；60 case 形成 20
  个完整跨档配对，truth identity/state 审计全 0，源组合 hash 前后不变。
- [x] 冻结 `3/2/1` 机会合同审计为 56 match/4 mismatch；0.1 candidate seed007/009、0.2 candidate
  seed006/009 的受影响 aggregate 保持 unavailable，reserve 仍排除。
- [x] D6 全量 `272 passed`；ClockSpeed 专项 `18 passed`，`py_compile` 与 `diff --check` 通过。
- [ ] candidate 0.1/0.2 因合同 mismatch 不发布完整物理 aggregate；case wall timing 源字段缺失，
  三档均 unavailable。后续由 main 修复 producer 证据后再重跑，不从当前部分数据给出准入结论。

## 2026-07-15 0.1 NameError 紧急回归状态

- [x] 将 timing input-mode 规范化函数前置并统一命名，loader/summarizer/evaluator 三处引用一致，旧
  私有名称删除。
- [x] 新增真实形态 20-case 双层 case-aware evaluator 回归：baseline/candidate 各 seed 1-10，逐 case
  frame/time 重置，manifest match，跨 case/跨层 total 为 null。
- [x] 真实 0.1 P1 只读生成成功：两层各 4036 records、20 case，输入 SHA-256 前后不变。
- [x] timing 专项 `28 passed`、D6 全量 `264 passed`、`py_compile`/`diff --check` 通过。
- [x] 已完成 1.0/0.2/0.1 三个 suite 的 ClockSpeed comparator；availability-aware 结果见顶部，
  不对 unavailable 的 candidate 0.1/0.2 发布性能结论。

## 2026-07-15 0.2 case-aware timing 与冻结机会合同状态

- [x] `single_episode` 与 `case_aware_suite` 显式分离；suite 只接受
  `case_id/family/profile/seed` 四个 metadata，逐 case frame/timestamp 严格单调并允许 case 切换重置，
  禁止 case 重现和跨 case 伪连续。
- [x] main bus/control tick case manifest 一致性校验完成；两层仍为嵌套 scope，不相加，跨 case/跨层
  total 均为 null；P1 acceptance v6 和两个 CLI 已支持显式 suite 模式。
- [x] 用真实 0.2 merged timing 只读复测：两层各 6567 records、20 case，manifest match，P1 bundle
  成功生成，runtime 三个输入 SHA-256 前后不变。
- [x] comparator v2 冻结每 case pair/target/coalition opportunities=`3/2/1`；actual-execution
  unavailable 或机会合同不符时，受影响 case 指标整体 unavailable，不缩分母、不补零。
- [x] standby reserve 从 active-primary success 与 denominator 排除并单独审计。真实 0.2 为 18 match/
  2 mismatch：candidate seed006 是 D7 unavailable 且 `2/1/1`；candidate seed009 是 D7 available 但
  同为 `2/1/1`。
- [x] 2026-07-15 0.2 阶段 timing/ClockSpeed 专项 `27/10 passed`，当时 D6 全量 `263 passed`。
- [x] main 已运行真实 ClockSpeed=0.1，P1 case-aware 复测见顶部。
- [x] 已连同 1.0/0.2/0.1 三个完整 suite 调用 comparator；合同 mismatch 项保持 unavailable。

## 2026-07-15 ClockSpeed 1.0/0.2/0.1 对比状态

- [x] 提供 Python API 和 CLI，输入三个 suite root/summary；强制每档 baseline/candidate 各 seed
  1-10、恰好 20 case，并按 `case_id/profile/seed` 完成 suite 内连接和三档配对。
- [x] ClockSpeed 只从 suite/case provenance 或全量一致的 case result row 读取；拒绝目录名和 summary
  根部裸字段，交叉检查 suite/case/artifact 显式值。
- [x] 输出 availability-aware JSON、case CSV、aggregate CSV、中文 Markdown 与 PNG 曲线；覆盖三层
  物理成功、第二 primary 五米/距离、最终锁/共识、collision stop、wall timing、ClockSpeed 归一化
  simulated time/tick 和 truth identity/state 审计。
- [x] main bus/control tick 保持嵌套层，cross-layer total 为 null；任何缺失指标、坏 timing 或缺
  artifact 为 unavailable，不补零。
- [x] 2026-07-15 三档各 20 case 的确定性 fixture 达到接受门限；专项 `8 passed`、D6 全量
  `254 passed`，仅有既有 Matplotlib `Axes3D` warning。
- [x] main 真实运行 ClockSpeed=`0.1` 已完成，D6 P1 case-aware 只读复测通过。
- [x] 已与 1.0/0.2 同套件配对调用 comparator；真实可用值和 unavailable 边界见顶部。
- [x] 旧 1.0 suite 的 20 个 sibling generated settings 已作为显式持久化 provenance 通过全量一致
  审计；新 suite 仍应优先保证所有 20 个 result row 都持久化同一 `clock_speed`，并与
  `intercept_summary.parameters.clock_speed` 一致；缺任一 case 时整套拒绝。

## 2026-07-15 M5N2 20-case 实测状态

- [x] 只消费 baseline/candidate 各 10 seed 的 20 个真实 M5N2 case；M5N2 完成后、`TERM` 生效前
  额外完成的 `png_ttc` seed001 明确排除在本批聚合与验收之外。其余 tuned 2v2 和全部 dropout
  未执行；缺失 case 保持 unavailable，不补零，也不把本批声明为完整 terminal-closure suite。
- [x] canonical actual execution required/available/unavailable=`20/20/0`，validation reason 为 0；
  truth identity/state 在线使用均为 0，10389 条目标状态样本均来自
  `d2_estimated_global_track`，stale=0。
- [x] 正式物理分母保持独立：pair=`12/60`、target=`12/40`、coalition=`0/20`；baseline/candidate
  均为 `6/30`、`6/20`、`0/10`。总量持平不能覆盖逐 seed non-degradation=false。
- [x] 第二 primary 漏斗 availability 完整：前四阶段 `20/20`、control/mode=`17/20`、physical
  `0/20`；20 个失败原因全部可用，最近距离 mean/min/max=`12.654/8.843/14.740 m`。
- [x] 文档术语统一：`12/40` 只称为 canonical target physical success（至少一个 participating
  pair 成功）；“全部 required member 通过阶段”只称为 cooperative target-stage diagnostic，
  不得写成或回填正式 `target_intercept_success`。
- [ ] 补齐 `collision_stop` 的 collision object/actor、时间戳和来源。当前第二 primary
  `20/20` 最终为 `collision_stop`，但对象字段未写盘，D6 必须保持原因 unavailable，不推断成员
  冲突、环境碰撞或 AirSim 状态问题。
- [x] 20 个 case 的两层 timing 原始流逐 case 严格校验；每层 3805 条，main-bus 与 control-tick
  分别汇总，禁止相加。
- [x] main 的 merged timing 已由 D6 `case_aware_suite` envelope 正式消费；case 边界重置合法，
  逐 case 单调与双层 manifest 已校验，禁止改写成全局伪连续时间轴。
- [ ] 将上述 target 术语固定为 producer schema/字段级 semantics，避免后续 suite 或旧 consumer
  仍按同名字段误聚合；文档口径已统一，代码字段治理仍开放。
- [ ] 降低 main-bus `349.34 ms` 和 control-tick `1069.45 ms` 均值及其预算违例；优先定位 D1
  fusion、AirSim frame sample、bus processing 和 control RPC。
- [ ] 关闭第二 primary `0/20` 五米物理结果和 coalition `0/20`；candidate 当前不晋升默认路径。

## 2026-07-15 第二 primary/coalition 被动报告状态

- [x] 第二 primary 七阶段漏斗按显式写盘证据输出 passed/available/unavailable/rate。
- [x] pair、target、coalition 使用独立物理机会数；新增 availability-aware 物理结果和独立
  coalition completion，禁止 target 或 pair 回填 coalition。
- [x] 首失败原因只消费显式 `first_failure_reason`；缺失为 unavailable/partial，不生成
  `unspecified`，缺物理证据不补零。
- [x] 2026-07-15 确定性 fixture 专项 `11 passed`、D6 全量 `246 passed`、`py_compile` 通过；未
  启动 AirSim。
- [x] main 已完成同配置 M5N2 baseline/candidate 各 10 seed，并提供完整 actual、物理与失败原因
  证据；额外 `png_ttc` seed001 不进入本批聚合与验收，其余 tuned 2v2 和全部 dropout 未执行。第二
  primary 和 coalition 性能未达标，继续保持 P1。

## 2026-07-15 分阶段延迟可观测性 P1 状态

- [x] 严格校验两层 schema/scope、阶段状态和值、frame/timestamp 顺序、总和、未归因耗时和预算
  flag；非法证据 fail closed，旧 artifact 缺 timing 为 unavailable。
- [x] 两层分别汇总 sample、mean/P95/max、N/A/error、总 tick、预算违例和 dominant stage；禁止
  嵌套耗时跨层相加。
- [x] 提供稳定 API、CLI、CSV/JSON/中文 Markdown/PNG；历史接入 P1 acceptance v5，当前 case-aware
  接线已升级为 v6。
- [x] 2026-07-15 动态规模无关 fixture：合法两层各 2 帧，专项 `20 passed`、全量
  `236 passed`；未启动 AirSim。
- [x] 已用真实 M5N2 20 case 的逐 case timing 定位主导阶段并确认 `100 ms` 未达标；两层各 3805
  samples，main-bus/control-tick P95=`487.40/1254.06 ms`。
- [x] case-aware suite timing 注册和只读 P1 复测完成。
- [ ] 完成瓶颈优化、三档 paired comparator 与跨提交趋势；0.1 P1 输入已可用。

## 2026-07-14 actual target-state freshness/stale P1 关闭状态

- [x] 将六个最终 command 字段冻结为 canonical 必需列；缺列、空/非有限/负数、时间顺序冲突、
  age 冲突、非法 stale 布尔和空 source 全部 fail closed，不补零。
- [x] 每 case 输出 sample、mean/p95/max age、stale count/rate、source distribution，以及独立
  availability/source/semantics。
- [x] formal validator 在 source SHA256 通过后重读 CSV 复算并比对 payload，禁止只信 JSON。
- [x] case suite、pooled aggregate、aggregate CSV/JSON 和中文 Markdown 正式报告完成接入；不修改
  physical、末端五层、truth 隔离和既有 availability 语义。
- [x] 2026-07-14 最新真实持久化源达到门限：2v2 `48`、M5N2 `608` samples，stale 均为 `0`，
  source 均为 `d2_estimated_global_track`；D6 全量 `216 passed`。
- [x] 同配置 M5N2 multi-seed freshness 已由本页顶部 20 case、10389 条样本补齐，stale=0。
- [ ] 建立跨提交 freshness 趋势和 failure taxonomy；该项不回退单 seed 指标链和本批 multi-seed
  证据状态。

## 2026-07-14 actual v2 真实 AirSim 证据状态

- [x] tuned 2v2 seed-1 与 M5N2 seed-1 均生成并显式注册通过校验的 canonical
  `d7-actual-execution-metrics-v2`；required/available/unavailable=`2/2/0`，actual P0 证据门关闭。
- [x] 两场景 summary/CSV/actual 物理成功计数均为 `2/2/2`；旧
  `d7_actual_execution_command_physical_count_conflict` 未复现，不再列为开放 GAP。
- [x] 保留三层独立分母：M5N2 pair=`2/3`、target=`2/2`、coalition=available `0/1`；不得以
  target 成功覆盖 coalition 显式失败。
- [x] M5N2 baseline/candidate 同配置各 10 seed 成对比较已完成；结果见本页顶部。
- [ ] 1-5 帧 dropout 全矩阵仍未执行，完成数为 0；缺失 case 保持 unavailable，不能据此声明完整
  terminal-closure suite 通过。
- [ ] 分解并降低 2v2/M5N2 `123.3/384.6 ms` loop latency，复验性能预算违例 `19+212=231`；
  该项继续作为 P1，不由本轮 actual P0 关闭。
- [ ] 关闭 M5N2 第二 required primary 约 `11.02 m` 的物理缺口，使 coalition 从 available
  `0/1` 达到接受目标 `1/1`。

本次为证据和状态同步，不修改 D6 代码。验收日期 2026-07-14；每个场景 1 seed，共 2 case。

## 2026-07-14 actual-execution 最终复核状态（真实重跑前历史）

- [x] required case 只有校验通过的 canonical `d7-actual-execution-metrics-v2` 才算 actual
  execution available；缺失或显式 unavailable 时 `actual_execution_all_available=false`，suite
  总验收 fail closed。
- [x] legacy main row 与离线五米结果只保留 diagnostics，不能替代或补齐 actual envelope。
- [x] `arrival_coordination_required=false` 时按每个 required active primary 的独立五米成功计算
  coalition completion；required member/denominator/physical result/开关缺失或 summary-pair 冲突
  仍输出 `null/unavailable`。
- [x] 2026-07-14 代码级验收：专项 `14 passed, 24 deselected`，D6 全量 `190 passed`；唯一
  Matplotlib `Axes3D` warning 只表示 3D projection 不可用，不影响 JSON/CSV/Markdown、二维报告
  或本轮口径结论。未运行 AirSim。

**仍开放 main P0/P1**：M5N2 baseline、M5N2 candidate、2v2 PNG-TTC、1-frame dropout 四个
历史真实 seed-1 actual artifact 仍为 `unavailable`，原因均为
`d7_actual_execution_command_physical_count_conflict`。main 必须真实重跑并注册有效 v2 artifact，
先关闭 seed-1 fail-closed 门，再进行同条件 multi-seed provenance、趋势和失败原因治理。D6 本轮
不修改 runtime，也不扩展算法范围。

## 2026-07-14 actual plan identity provenance P0 状态（真实重跑前代码验收）

- [x] actual envelope 升级为 `d7-actual-execution-metrics-v2`，强制 command CSV 提供
  `plan_id/plan_version/d4_target_node_id` 列；plan ID 和正整数 version 每行必填。
- [x] 输出去重排序的 `metadata.plan_ids/plan_versions/owner_node_ids`；version 规范化为正整数，
  owner 仅在 effective-authorized secondary/distributed active/execution/reassignment 或显式
  execute action 行必填。中心授权及未授权 pending 可为空；没有 authoritative owner 时 owner
  provenance 为 `unavailable`，owner-required 行缺值 fail closed。
- [x] 为三项 metadata 写出并校验 `status/source_artifact/reason/semantics`；hash 校验路径重读
  CSV 对照 envelope，阻止 metadata 脱离持久化来源被篡改。
- [x] merge 升级为 `d6.execution-metrics-merge.v3`；清除 replay 同名字段，只从 validated
  actual envelope 写最终 `metrics.metadata`，不改变 safety/physical/mode semantics。
- [x] 2026-07-14，seed N/A，execution-evidence focused `20 passed`、D6 全量 `184 passed`；
  中心授权空 owner 和未授权 pending 空 owner 可用，secondary/distributed effective-authorized
  空 owner fail closed，plan/version 仍逐行必填；1 条既有 matplotlib warning。未运行真实 AirSim。

**后续状态**：main/runtime 已用最终 producer 文件生成并注册本页顶部两条真实 SimpleFlight
seed-1 v2 artifact；target-state freshness/stale 的单 seed 正式分布链已由本页顶部关闭。剩余 P1
是同几何、同配置 multi-seed 的 seed/config/schema/hash provenance、跨提交 freshness 趋势和
failure taxonomy。D2 lifecycle 与 D3 plan/membership churn
的 episode-clock join 也仍开放；本次单元测试不替代这些证据。

## 2026-07-14 actual execution P0 收尾状态（真实重跑前代码验收）

- [x] 冻结 `d7-actual-execution-metrics-v2`，只认可显式 producer、post-control phase、actual
  scope、case/seed/规模、三份来源路径和 SHA256。
- [x] 增加 `build_d7_actual_execution_evidence()` 与
  `write_d7_actual_execution_evidence()`；输入仅为最终 `control_commands.csv`、
  `intercept_summary.json`、`main_episode_bus_metrics.json`，D6 不负责 episode 调度。
- [x] contract/control/mode 从 command rows 计算，physical 从 summary 计算，performance 从
  main bus clock 计算；来源冲突、缺样本、hash 篡改和 integrated replay 全部 fail closed。
- [x] 强制 `mode_switched_count <= control_allowed_count`；raw mode 变化只进 metadata audit。
- [x] actual diagnostic count 从 command CSV 按冻结语义计算；视觉 PNG transition 与持续授权 sample
  分离，sample 仅作 supplemental。
- [x] `truth_identity_online_use_count` 与 `truth_state_online_use_count` 并列进入 required count、
  source、semantics、availability 和 validator；identity 来自 command CSV，state 来自 intercept
  summary，禁止互相回填。
- [x] case consumer 在注册后重新计算 source hash，merge 缺 actual 时不再回退 replay。
- [x] 正负测试覆盖有效写盘、零性能样本、main/command mode 冲突、effective-control 冲突、
  source hash 篡改、raw replay 冒充 actual、安全计数来源和视觉 transition/sample 分离；D6 全量
  `173 passed`。

**后续状态**：main 已在三份 producer 文件 finalize 后生成并注册两条独立 artifact，真实 seed-1
门以 `2/2/0` 关闭。source hash 与 actual mode/control/physical/performance 的一致性要求不变；
multi-seed P1 和性能 P1 仍开放。D6 本批没有修改 runtime。

## 2026-07-14 terminal closure case evidence 计划状态（先前四案例）

本批 D6 owner 工作已完成：

- main terminal summary 中的多条 `d3_plan_history` 路径按 `case_id/seed` 独立加载、校验和聚合；
- suite 输出逐 case、逐 seed、总记录数和 churn 合计，单个缺文件或 schema mismatch 不污染其他 case；
- D7 路径缺失、文件缺失、registration/schema/seed mismatch 都保持 unavailable 并输出原因；
- 提供 `register_terminal_closure_case_evidence()` 给 main 在 producer 文件写盘后注册路径；
- raw D7 metrics 不具备 terminal envelope 时不进入四层指标，防止猜测语义和重复计数；
- suite、per-case、缺文件和 schema mismatch 回归已加入，全量 `159 passed`。

剩余跨模块 P1 由 main/runtime owner 执行：在 `_terminal_closure_result_row` 形成 summary 行前，
使用 episode `output_paths["d7_execution_metrics"]` 调用 registration helper；随后重生成
seed-1 正式 suite，验收 4/4 D7 case registered，最后再进入 multi-seed。D6 不修改 runtime，
也不会以目录搜索代替注册。当前实际 seed-1 的 D3 4/4 case、543 records 已可用；D7 原 summary
仍为 0/4 registered，这是明确 wiring 缺口，不是零执行结果。

## 2026-07-14 terminal suite P1 closure（D6-owned 已关闭）

本批次只修改 D6 owned paths，消费 main/D3/D7 已落盘文件，不参与在线控制或回写 producer。

- [x] 冻结 terminal-suite metric envelope：contract/control/mode/switch/physical 每条指标强制携带
  `producer`、`metric_scope`、`denominator`、`lifecycle`；以完整语义键隔离 main-bus
  planned-lock 与 D7 execution，禁止同名跨来源比较、求和或覆盖。
- [x] 提供 D3 canonical history file input；校验 schema/order/count/timestamp 后输出 plan/version、
  primary/reserve membership、owner 与 feedback churn；缺文件或无有效 history 必须保持
  `unavailable`。
- [x] 汇总 `loop_latency_ms`、`performance_budget_violation_count` 及逐项 availability；无样本时
  不得以 `0/0` 或数值零代替 unavailable。
- [x] candidate non-degradation 同时输出 effectiveness evidence；baseline/candidate 效果均为零且
  candidate mechanism trigger 为零时结论只能是 `inconclusive`，不得 promotion。
- [x] 输出 seed-level 与 aggregate 的中文 Markdown、JSON、CSV，并保持 contract/control/mode/
  physical 四层分离；补齐 README、PLAN、D6 GAP/review 文档。
- [x] 验收：`pytest -q research_modules/d6_evaluation_metrics/tests`；
  `git diff --check -- research_modules/d6_evaluation_metrics subagent_reviews/D6_*`。

实现冻结为 `d6-p1-unified-acceptance-v2` 与 `d6-terminal-metric-envelope-v1`。同名指标只在
`source + producer + metric_scope + lifecycle` 单一语义组内聚合；出现多个语义组时顶层
`sum/denominator_sum/mean` 为 `None`，逐组结果保留。D3 terminal-suite 新入口为
`P1AcceptanceInputs.d3_plan_history` / CLI `--d3-plan-history`；缺文件或校验失败保持
unavailable。输出新增 per-seed JSON、terminal metric CSV 和 aggregate CSV。

**验证**：2026-07-14，4 类新增确定性离线场景，seed 1/2/7 或 N/A：planned-lock 与 D7
execution 同名隔离、零样本性能、零效果且零触发 inconclusive、两 tick canonical history。
接受门限全部满足；D6 terminal-suite 专项 `8 passed`，canonical 专项 `24 passed`，D6 全量
`154 passed`，1 条既有 matplotlib `Axes3D` warning；未运行 AirSim。

**main 接线仍开放**：main-owned `p1_terminal_closure` 需逐 metric 写出 producer/scope/正分母/
lifecycle，分开 main planned-lock 与 D7 execution；逐 physical level 写
`physical_metric_context` 和 pair/target/coalition 分母；写出正 `performance sample_count`、
latency/budget violation；传入 `d3_plan_history.json`，并保留 candidate 实际 trigger/effect。
本批次不直接修改 runtime。

## 2026-07-14 truth-state/physical provenance P0 状态

- **P0 已关闭**：`truth_state_online_use_count` 与既有
  `truth_identity_online_use_count` 独立；summary、pair、command 的正证据按实际 pair 聚合，
  严格 D2 estimated-state 路径为 available `0`，truth-state fixture 必须 `>0`。
- **physical gate P0 已关闭**：summary 和 active pair summaries 都必须存在；command-only 与
  summary-only 不得发布 physical 指标。每个 active pair 必须显式
  `physical_evidence_available=true`，且 `target_state_source` 等于 summary
  `online_control_state_source`。offline scorer 只接受 D2 estimated class，truth fixture 只接受
  显式 fixture class。每个参与 pair 还必须有显式 physical 布尔结果或规范 scorer 终态；
  evidence flag 本身不代表失败结果。缺 pair result 时所有层为 `None/unavailable`。
- **coalition completeness P0 已关闭**：`required_primary_count` 超过实际 persisted required
  primary 数、缺 arrival window、缺 coalition denominator，或 summary 有 opportunity 但缺
  completion count 时，coalition count/rate 为 `None/unavailable`；证据完整的显式零保持
  available `0`。pair/target 可用性不被 coalition-only 缺口回填或降级。
- **CSV/legacy 边界已关闭**：command loader 保留 `physical_evidence_available` 供审计，但
  command rows 不生成 physical pair；无来源 legacy status 只作 raw audit。
- **报告链已关闭**：字段进入 `EpisodeMetrics`、standard mapping、execution merge、episode
  CSV、聚合 JSON 和 Markdown；coalition metadata 与各格式使用同一 unavailable reason。
- **验证**：2026-07-14，7 类确定性离线 provenance 场景、seed N/A，接受门限为合法 offline
  scorer/truth fixture available，legacy、command 缺证据、summary-only 和 pair source mismatch
  全层 unavailable，并新增 7 项 result/member/window/denominator/显式零回归；D6 全量
  `150 passed`，1 条既有 matplotlib warning，未运行 AirSim。
- **历史口径**：2026-07-11 至 07-13 缺新 provenance 的 physical 结果不得回填为新 offline
  scorer evidence，也不得与迁移后结果直接比较。
- **开放 P1**：本次只关闭 D6 代码/测试 P0。main/runtime 仍需按新 schema 形成同条件
  multi-seed AirSim 批次，逐 pair 写盘 evidence/source，并统计 target measurement/arrival age、
  stale/reject 分布和跨提交趋势。

## 2026-07-14 truth tracking P0/P1 状态

- **P0 已关闭**：`track_rmse/track_continuity/id_switch_count` 缺 truth-to-track 证据时为
  `None/unavailable`；完整 identity history 的零切换保留为 available `0`，D2/D6
  `id_switch_count` 字段仍显式存在。
- **报告链已关闭**：JSON、episode CSV、batch summary、Markdown、main-bus loader 和
  replay/execution merge 均尊重 availability；旧载荷的 unavailable `0` 不进入统计。
- **验证**：2026-07-14，5 个确定性场景、seed N/A；空输入、匿名 track、不完整 sidecar、
  完整 truth 零切换、完整 truth 有切换全部达到门限。D6 全量 `137 passed`，1 条既有
  matplotlib `Axes3D` warning；未运行 AirSim。
- **剩余 P1**：真实 multi-seed producer 的 seed/config/schema/hash provenance 完整性；
  D2 lifecycle 与 D3 plan/membership churn 按 episode clock、`global_track_id`、plan/version
  的跨源 join 和长期趋势。两项均未由本次单元回归替代。
- **剩余 P2**：外部 MOT/HOTA、OSPA/GOSPA、Stone Soup 和原生 recording parser 状态不变。

## 2026-07-14 第二批当前 P0/P1/P2 状态

- **canonical history 接线已闭合**：D6 识别 `d3_plan_history_v1` wrapper 和
  `d3_plan_history_record_v1` record，不依赖 cooperative snapshot 推断 churn。
- **严格校验已闭合**：至少 2 条；record_count 一致；sequence index 唯一且严格递增；
  ordering key 与 sequence/timestamp 一致且严格递增；timestamp 不倒退；record schema 和
  指标所需 assignment/coalition/owner/feedback 结构完整；禁止 truth 字段。失败原因进入
  CSV、聚合 JSON 和 Markdown，全部 history-derived 指标保持 unavailable。
- **指标已闭合**：计划、联盟 version/epoch churn；基于 assignment snapshot diff 的总体、
  primary、reserve membership change；owner change；soft/hard feedback；history record count
  与 validation audit。membership audit event 不作为计数来源。
- **兼容性已闭合**：旧 snapshot、旧 ordered history 和 formal cooperative-role 输入继续
  可读；只有证据充分的旧有序历史可计算，snapshot/cooperative-role 不足证据仍 unavailable。
- **验证**：2026-07-14 canonical 专项 `24 passed`，D6 全量 `132 passed`，1 条 matplotlib
  `Axes3D` 环境 warning。测试覆盖稳定零、版本/成员/owner/feedback 变化、乱序、重复索引、
  timestamp 倒退、单记录、schema/count/order key 错误和无 truth 字段。
- **剩余 P1**：在真实 AirSim/main multi-seed episode 上持续运行该入口，建立跨提交趋势、
  门限稳定性和统一 failure reason taxonomy。本轮只闭合 D6 schema/metric/report 接线，没有
  新物理实验结论。
- **剩余 P2**：真实 D2/D5 replay 的 py-motmetrics 门限、遮挡和重现标定；TrackEval/HOTA、
  Stone Soup metrics、OSPA/GOSPA、AirSim 原生 recording parser 等 optional/offline 项。

main/D6 调用保持 file-only：CLI 使用 `--d3-plan-history <episode/d3_plan_history.json>`，或
Python API 传入 `P1SystemEvidenceInputs(d3_assignment_churn=history_path)`。D6 不回写 main/D3。

以下第一批 2026-07-14 状态和 2026-07-13 更早章节是历史快照。

## 2026-07-14 第一批 P0/P1/P2 状态（历史）

- **评估级 P0 已闭合**：D3 最终快照、空 mapping、单条无序记录不再把
  `plan_version_churn_count`、`coalition_version_churn_count`、
  `coalition_epoch_churn_count`、`membership_change_count` 推断为 available `0`。
- **可用性合同已冻结**：只有显式 count，或至少两条带顺序语义且同名证据完整的历史记录，
  才计算 churn。稳定有序历史和显式零均输出 available `0`；缺字段、单快照和不完整历史输出
  `unavailable`。formal cooperative-role `pair_rows` 分支继续只报告角色，不补 churn。
- **验证**：2026-07-14 使用 5 类 fixture（最终快照、空输入、单条无序、两条稳定有序、
  显式零）验收，接受标准是前三类四项全 unavailable、后两类四项全 available `0`；专项
  `12 passed`，D6 全量 `120 passed`，1 条 matplotlib `Axes3D` 环境 warning。
- **剩余 P1**：main/D3 写出真实有序 plan history、统一 episode clock、version/epoch、source
  provenance 和 availability；建立长期真实 multi-seed 跨提交趋势；治理跨批次 failure reason
  taxonomy。最终 snapshot 仍不能替代历史。
- **剩余 P2**：真实 D2/D5 replay 的 py-motmetrics 门限、遮挡和重现标定；TrackEval/HOTA、
  Stone Soup metrics、OSPA/GOSPA、AirSim 原生 recording parser 等 optional/offline 项。

以下 2026-07-13 及更早章节均为历史状态和证据快照；历史数字不改写为当前结论。

## 2026-07-13 历史最终状态入口

D6 的统一离线报告入口已经兼容 cooperative 原始 `cases/pair_rows/aggregates` 和修正后的 `d6-cooperative-closure-v2` aggregate。当前冻结证据可展开为：D1 1 条、D2 3660 条、D3 40 条、D4 60 条、D5 per-primary 160 条、native MOT 18 条、D7 164 条。D7 的 164 条由 160 条 pair/safety 记录和 4 条 profile 汇总组成，profile 汇总不与逐 pair 四层指标重复计数。

当前验收结果：

- M5N2 最佳 profile coalition 为 `5/10`，四个 profile 总体为 `8/40`；未达到 `8/10` 是实测结果，不是 D6 分组或分母错误。
- D7 四层显式计数为 contract `35`、control `7`、mode switch `9`、physical `62`；四层只读取同层证据，不跨层反推。
- online truth use、`global_track_id` rewrite 和 reserve unauthorized execution 均为 `0`，且 evidence available。
- D3 输入没有逐时刻 plan history/churn 记录，因此 D3 churn 保持 `unavailable`；D6 不从最终 snapshot、版本总数或其他模块记录重建该值。
- 缺值保持 `unavailable`，显式观测到零才是 0。source manifest 和逐行记录保留 schema、SHA256、producer/run、evidence path 与 provenance。
- bootstrap 95% CI 仅对至少两个显式 seed 的逐 seed 均值计算，固定 2000 次重采样和 RNG seed；不足样本不产生区间。

截至本状态，D6-owned cooperative schema、聚合、availability、四层分离和中文报告缺口均已闭合，全量回归为 `115 passed`。仍开放的 P1 只包括长期真实 multi-seed 趋势、producer 逐时刻 schema（特别是 D3 churn）和跨批次失败原因治理。P2 工具继续保持 optional/offline，不进入默认依赖、默认报告主线或在线控制路径。

以下较早日期章节保留历史实现与证据演进；发生冲突时，以本节为准。

## 2026-07-13 P1 统一系统证据验收历史记录

D6 已将统一离线报告入口收敛到 D1-D7 当前 P1 证据：D1 dense-crossing freeze summary、D2 六难度逐 seed 关联、D3 M5N2 计划/联盟 churn、D4 episode tick 或 fault matrix、D5 per-primary/native MOT、D7 pair guidance/physical intercept。输出为逐 seed/source CSV、聚合 JSON、中文 Markdown 和 PNG，不导入在线 producer，也不控制 AirSim。

验收口径：

- `contract_allowed/control_allowed/mode_switched/physical_intercept` 只读取各自同名语义，不跨层反推。
- 缺值为 `unavailable`；显式观测到零才是 0。source manifest 和逐行记录保留 schema、SHA256、producer/run、evidence path 与 provenance。
- bootstrap 95% CI 只对至少两个显式 seed 的逐 seed 均值计算，固定 2000 次重采样和 RNG seed；不足样本不产生区间。
- D1/D2/D5 truth 只作离线评分，在线 truth use 和 `global_track_id` rewrite 单独审计。
- 失败原因按全局和来源分别统计；成功行的显式空失败列表是“available 且 0”，缺失败字段是 unavailable。

真实 AirSim M5N2 40-case 原始 summary 与修正 cooperative aggregate 已进入统一入口回归。原始 schema 按 40 个 case 展开 D3 显式角色、D5 160 个 pair/safety 行，以及 D7 160 个 pair/safety 行和 4 个 profile 汇总行；修正 aggregate 在没有逐 pair 明细时保守恢复 profile、D5 funnel/common-lock 与 D7 四层/coalition/safety 汇总。两条路径均得到最佳 profile `5/10`、总体 coalition `8/40`，且不再按 `case_id::profile` 形成 40 个单 seed 组。

该批次 D4 fault、native MOT 和 M5N2 证据已经进入最终统一报告；后续新批次继续沿相同 schema 接入。producer 文件缺失或字段尚未写盘时，D6 保持 unavailable，不补零或构造替代数据。

## 2026-07-12 P1 dense-crossing 第二批报告状态

D6 已实现 `d6-dense-crossing-evaluation/v1` 文件协议报告器，直接兼容 D1 `d1.governed_replay_manifest.v1`/offline truth summary 和 D2 `d2-p1-identity-calibration/v1`。D6 不 import D1/D2，不运行 tracker，不把评估结果回写控制。

当前能力包括：

- 10-seed screening 只用于选出明确标记或按 IDSW、continuity、false track、latency 排序的最佳 GNN candidate；不足 10 seeds 不形成选择。
- 20-seed confirmation 分开聚合 GNN baseline、同 config ID 的最佳 GNN candidate 和轻量 JPDA；不足 20 seeds 不形成晋级。
- 历史 `d6-dense-crossing-evaluation/v1` promotion 对照固定检查 IDSW `-30%`、identity continuity `+0.10`、false track `+10%` 上限、冻结 p95 loop latency budget 和 truth leak `=0`；该 `+0.10` 已标记为 legacy，不再用于解释 D2 v2。统一 system-evidence v2 忠实消费 D2 ceiling-aware admission 的显式 gate、门限值和失败原因，不在 D6 内重算判决。
- 每个指标独立携带 available/unavailable 与原因。当前 D2 仅写 NIS/NEES availability 而未写 per-seed mean 时，均值保持 unavailable。
- FilterPy/Stone Soup object adapter smoke、MHT 和未分类实现不进入本轮晋级；轻量 JPDA 保留 `research_approximation` 成熟度标签。
- 固定输出 `dense_crossing_per_seed.csv`、`dense_crossing_aggregate.json`、中文 `DENSE_CROSSING_CALIBRATION_REPORT.md` 和 `dense_crossing_metrics.png`。

下一步由 main 提供真实 AirSim 冻结 replay 的 10/20-seed D1/D2 写盘 evidence 并调用该报告器。若 D2 后续增加 NIS/NEES 均值或置信区间，D6 只沿现有 availability 字段扩展读取；不得把 availability count 当成统计值。

## 2026-07-12 P1 cooperative-closure-v2 状态

本轮离线报告能力已经实现：主行记录支持 JSON/JSONL/CSV 与内存对象，按实际 M/N 形成逐 seed 数据集；pair、target、coalition 使用独立分母；第二 primary failure、共同锁定率、到达离散、最小成员间距和 D4 通信故障可独立统计。D3 candidate、D4 communication、D5 visibility、D7 guidance 均为可选证据，manifest 明确 available/unavailable。

D4 真实合同已对齐：`CommunicationFaultReplayReport` 同时含 `seeds` 和 `cases` 时固定消费 `cases`；case 的 `scenario_id/passed/fail_closed` 分别进入 fault key、pass rate 和 fail-closed rate。别名仅位于 D4 communication 专用归一化，不扩展到 main/D3/D5/D7 通用业务行。

2026-07-13 已用真实 M5N2 40-case/4-profile/10-seed summary 完成 schema 回归并修正聚合键：逐 case/seed 明细继续保留，但 acceptance 按 profile 的唯一 seed 计数；稳定 `coalition_id` 用于跨滚动 version/epoch 合并联盟；只有至少两个 active primary 的目标进入 coalition 分母。source 声明的 `best_candidate_profile` 优先于 D6 fallback 排序，缺少声明时才按通过数、完成率、available seed 数和稳定名称排序。

修正后 source 最佳 profile `d3-p1-h020.0-w03.0-s040.0` 为 `5/10`，`coalition_at_least_8_of_10` 明确为 available+failed，不再因 40 个单 seed case group 误报 insufficient evidence。四 profile 完成数 `0/10、5/10、2/10、1/10` 与 source summary 一致；缺失 seed 继续单列 unavailable，不补 0。后续只需 main 持续提供同 schema 证据，D6 不负责 AirSim 调度。

## 2026-07-15 D2 v2/legacy 准入证据兼容计划状态

本批计划已经完成：

1. 将统一 system-evidence 输出升级为 v2，增加 D2 策略版本、连续率上限感知字段、全部门限状态和逐字段 availability。
2. 失败原因按 v2 gates、legacy structured checks、legacy bool checks 的顺序解析；v2 具体 gate reason 优先，缺 reason 时仍保留 gate 名。
3. aggregate JSON 和中文 Markdown 新增 D2 准入评审段，明确 recommendation-only，不参与控制或默认主线切换。
4. 新增通过、失败、structured legacy、bool legacy 和缺字段回归；缺失值保持 `None/unavailable`。
5. 同步 README、PLAN、GAP/review、模块原理、算法、AirSim 接口和实验文档。

2026-07-15 正式证据闭环：

6. [x] 消费 frozen replay 的 `d2-p1-identity-calibration/v2`，生成 D2-only CSV/JSON/中文
   Markdown/PNG；其他六源显式 unavailable，`full_system_decision=not_evaluated`。
7. [x] aggregate 保留 promotion recommendation/candidates、selected/default path、14 条 overall/
   分档 assessment、五 gate reason 和 dropout truth-alignment summary；legacy 缺字段仍为
   `None/unavailable`，D6 不重算 producer decision。
8. [x] 记录总体五 gate 通过但仅建议评审；仅 clutter/combined 分档通过，四档 baseline IDSW=0
   fail-closed；JPDA research adapter 不准入，默认在线 GNN/Hungarian 未改变。

验收日期 2026-07-15：system-evidence 专项 `31 passed`，D6 全量 `243 passed`；本批未运行
AirSim。“D6 尚无 D2 v2 正式证据”的 P1 报告缺口已关闭。仍需 D2/main owner 完成 promotion
评审决定；D1/D3/D4/D5/D7 未与本批同 case/seed 组合，因此全系统判决仍未评估。

## 1. 模块定位与边界

D6 是系统级离线评估模块。它消费 D1-D7、main runtime、AirSim Blocks replay、合成仿真和人工/规则标注产生的日志，输出可复现的指标、CSV、Markdown 报告和 PNG 图表。

D6 不参与控制：

- 不发布航迹、分配、降级、末端配准或导引决策。
- 不生成 fire-control 参数、毁伤模型、自动处置动作或授权绕过流程。
- 不把评估侧 truth label、高威胁标签或后验 review label 回写到在线系统。
- 只读取已落盘记录；所有 AirSim/D4/D5/D7 接入均为 offline/file adapter。

D2/D6 的硬约束必须保留：`id_switch_count` 是一级显式指标，不能只被 MOTA、成功率或总体得分间接吸收。

## 0.1 2026-07-12 P1 第二批统一验收实现

- `P1AcceptanceInputs/P1AcceptanceReportGenerator` 已形成 file/offline-only 聚合边界，可消费 main P1 terminal closure 与 D1-D5/D7 的版本化 replay/calibration summary；不 import 或调用在线模块。
- 统一 bundle 输出 `p1_acceptance_per_seed.csv`、`p1_acceptance_aggregate.json`、中文 `P1_UNIFIED_ACCEPTANCE_REPORT.md` 和 `p1_acceptance_overview.png`。
- contract/control/mode/physical 四层和 pair/target/coalition 三层分别聚合；上游旧字段缺失保持 unavailable，不做跨层推断。
- D7 dropout、TTC 四类拒绝和 trend 晋级判据，D4 failover matrix，以及 D2 IDSW/continuity 均有独立报告区；D1、D3、D5 保留 source schema 和关键摘要。
- 本轮关闭的是 D6 离线消费和统一报告代码缺口。真实同条件 M5N2 AirSim paired、真实 dropout/`png_ttc`、D5 持续视觉和 D4 物理接管 evidence 仍由 main 与上游模块生成。
- 当独立 D7 summary 缺失时，统一报告从 main suite 的版本化 `acceptance.dropout_matrix` 和显式 family rows 派生 dropout/`png_ttc`/trend 专项摘要；来源写为 `main_terminal_closure`。独立 D7 summary 仍具有优先级。
- `physical_levels` 只统计 `family=m5n2_paired`，不混入 2v2 dropout 或 `png_ttc` 成功。contract/control/mode/physical 继续只读同名字段。
- `p1_terminal_closure_smoke_v2_20260712` 已验证 fallback：dropout complete/compliant，TTC 1 seed 且 not-expanding=1，trend trigger=0/promotion=false；四层字段等待 main 新版本写盘。

## 1.0 2026-07-12 D7 PNG Delivery 评估交付

- 已在 `EpisodeMetrics` 和 D7 CSV/JSON replay 中接入 terminal filter、TTC 面积有效性、soft prediction/coast、锁定连续性、视觉模式驻留和命令跳变指标。
- 所有新增指标使用 `Optional` 与 `metric_availability`；只有上游写出对应证据时才可用。
- 已提供 baseline/candidate 多 seed CSV、JSON、中文 Markdown bundle，并按显式 profile 和实际 N/M 规模分组。
- 继续保持 contract/control/switch/physical 四层与 pair/target/coalition 三层分离；D6 不修改阈值、不授权 coast、不参与控制。
- main/D7 后续需要稳定写出 profile、terminal filter state/reason、TTC reject reason、elapsed time、terminal lock、visual mode 和三轴速度命令；字段缺失时报告保持 NA。

本节是 2026-07-12 的当前 P0/P1 状态入口；后续 2026-07-11 小节只保留历史批次口径：

- **P0 保持闭合**：没有新增运行级 P0 blocker。实际规模归一化、显式 `id_switch_count`、online truth 隔离、execution/contract 分离、evidence availability 和 `cuas-standard-map-v1` 保持原状态。
- **P1 D6 实现闭合**：terminal filter measured/predicted/innovation-rejected/reset/expired、TTC 四类拒绝、soft prediction/coast duration/expiry、terminal lock continuity、visual mode duration、command discontinuity 已进入指标、availability、标准映射和离线 replay；terminal delivery 对照 bundle 已实现。
- **2026-07-12 实际证据**：D6 对照包消费 26 个 episode，按 scope/scenario/profile/实际 N/M 形成 4 组。2v2 baseline 10 seeds 为 pair/target `19/20`，candidate 10 seeds 为 `20/20`；candidate 自然运行未触发 soft prediction 或 trend coast，因此只闭合非退化验收，不证明增强算法贡献。四层 logging smoke 为 `contract_allowed=4/36`、`control_allowed=2/36`、`mode_switched=5`、`physical_intercept=2/2`；早期 10-seed 文件缺新列时保持 NA。
- **M5N2 证据边界**：35 s 高净空 baseline 为 target `6/6`、active-primary pair `6/9`、coalition `0/3`；8 s candidate 为 active pair `0/9`、最近距离 22-32 m。两批几何和窗口不等价，不能形成 baseline/candidate 结论，也不能把 target success 回填为 coalition completion。
- **当前开放 P1**：同一 z=-30 m、35 s 几何和同 seed 的 M5N2 paired baseline/candidate；独立 `png_ttc` 多 seed；1-5 帧锁后 dropout 矩阵与 0.25 s fail-closed；trend coast 在错误绑定、命令跳变和物理成功三项均不退化后再决定是否进入默认 profile；以及既有完整标准化报告、场景库/CI 接线、长期真实 replay/review/window/阈值趋势。
- **下一验收条件**：M5N2 必须分别报告 target、active-primary pair、coalition completion；`png_ttc` 必须报告 area jump、bbox clipping、not expanding、TTC out-of-range；旧日志缺字段继续为 unavailable，不得补 0。D6 只消费 main/D5/D7 写盘证据。
- **验证与变更边界**：该 D7 专项阶段指定测试为 `84 passed`；加入本轮 P1 统一验收和 main-summary fallback tests 后，D6 当前为 `88 passed`，伴随 1 条本机 matplotlib `Axes3D` warning。

## 1.1 P1/P2 历史状态（2026-07-11）

以下内容保留 2026-07-11 当日证据；当前 P0/P1 判定以 1.0 节为准。

D6 当日仍保持 offline-only。当日状态按证据成熟度分为四层：

- **P0 已闭合并保持回归**：实际规模归一化、显式 `id_switch_count`、truth isolation、execution/contract 分离、evidence availability 和 `cuas-standard-map-v1` 均已进入本地主线；当前没有运行级 P0 blocker。
- **P1 合同/指标接口已完成**：M 对 N DTO/loader/writer/聚合、合法协同锁与错误重复锁拆分、center replan 生命周期、联盟 ACK/commit/epoch/lease、二级 lifecycle、D5 YOLO/MOT 预算、四导引律配对和多 seed 报告接口均已实现。
- **P1 合同层实测已闭合**：CV 10-seed 达到 8/10 T001 双 primary 同帧共识与授权证据；secondary 和 distributed 均形成 executing 3/3 commit；missing-ACK 以 aborted 2/3 fail closed。10 个 CV seed 的 IDSW 与错误重复锁均为 0。
- **P1 物理与长期 evidence 仍开放**：SimpleFlight 虽已验证每 seed 4 bindings、3 active + 1 standby，但 30 个 active pair 物理命中为 0；24 个 detection timeout、6 个 timeout。当前 15 s、`control_dt=0.5 s` 仅是诊断窗口，不能用于导引律有效性结论。`ScenarioLibrary` 只是已完成的版本化接口，不等于长期场景语料和 CI 趋势已经建立；D1-D3 长期 replay、YOLO/MOT 长时预算、四导引律长窗口多 seed、跨提交场景覆盖和阈值趋势仍是 P1。
- **P2 optional benchmark**：最小 frame-level schema 与 py-motmetrics adapter 代码已实现，但当前真实 backend 验证仅覆盖 2 帧离线 smoke fixture；IDF1/MOTA/MOTP 在该冻结 schema 上可计算，尚未完成真实 D2/D5 replay 的门限、遮挡和重现标定，HOTA 不可用。TrackEval、Stone Soup metrics、OSPA/GOSPA 和其他非参数统计仍待实现。所有 P2 能力只作隔离离线对照，不替换默认在线关联/导引路径或 D6 本地指标主线，也不进入默认依赖。

同批 P2 evidence 的标签不得升级：D2 FilterPy/Stone Soup 仍只是对象 adapter smoke，D5 OpenCV 结果是离线合成标定/PnP 对照，D6 py-motmetrics 是 2 帧 smoke，D7 3D PN/APN/FRPN 是离线质点对照且 FRPN 仍为研究近似。D6 只在报告中保留这些边界，不把它们表述成默认算法替换或在线能力。

已完成的 D6 代码能力包括：

1. `MetricsCollector` 已实现二级 readiness/plan 状态驻留、activation latency、fallback/lease/stale reject；上游没有显式 lifecycle event 时保持 unavailable。
2. D5 perception event 已实现 YOLOv8 recall、ByteTrack/BoT-SORT local-ID continuity、cross-view rate、latency 和 CPU/GPU budget 统计；离线 truth 只能位于 `metadata.offline_truth`。
3. 四导引律同 seed 配对已独立实现，要求 main 写 `experiment_guidance_law`；command-level `guidance_law_counts` 不作为实验选型，避免把中末段混合模式误判为实验组。
4. `ScenarioLibrary` 已实现 tags、difficulty、expected failure modes、parameters、seed matrix 与 online truth policy，输出 JSON/CSV/中文 Markdown。
5. 通用报告和 AirSim calibration 已接入新指标，提供 CSV/JSON/Markdown 和 PNG 曲线接口。

最新 evidence 根目录为 `research_modules/airsim_runtime/outputs/p1_p2_validation_20260711/`。CV 结果的 `physical_intercept_count=None`、`control_allowed_count=0` 是正确口径：ComputerVision 状态合同没有执行 SimpleFlight 控制。SimpleFlight `physical_intercept_count=0` 且 evidence available，表示确实运行了物理控制但未命中；两者不得合并。

后续顺序固定为：先延长/细化 SimpleFlight 物理实验并解决 detection timeout，再持续补 D1-D3、YOLO/MOT 和四律长窗口 evidence；D6 继续按 contract/control/switch/physical 四层指标汇总。未写出的指标保持 unavailable，禁止用默认 0 补齐。

## 1.2 P1/P2 历史实现状态（2026-07-11）

1. P1 已接入 `d4_coalition_commit_state`，同时兼容扩展 `CoalitionRecord`；按 target/coalition/plan/epoch generation 去重，输出成员 ACK 完成率、ACK latency、lease、timeout、aborted/reconfiguring 和 secondary/distributed commit。
2. P1 已新增终端四层指标：`contract_allowed`、`control_allowed`、`mode_switched`、`physical_intercept`。四层分别按各自 evidence 计数，不从前一层推断后一层；当前 ComputerVision 的 `control_allowed_count=0`，且缺拦截 summary/pair/control status，因此 physical 保持 unavailable。
3. physical 层新增三个独立验收分母：active assigned pair、唯一 target、需要协同的 target。`collision_intercept/range_intercept` 均为 pair physical success；target 只需任一 participating pair 成功；coalition 要求全部 required primary 在各自 arrival window 内成功。缺 arrival window 时 coalition 为 unavailable，不能用 pair 或 target 成功代替。
4. summary 判据审计读取 5 m、NED、3D Euclidean 和 criteria version；ComputerVision 即使存在状态记录也保持 physical unavailable。control record 可报告 detect/coast 六项诊断与 `truth_identity_online_use_count`，D6 不把诊断用于控制。
5. P1 字段已进入 `EpisodeMetrics`、通用报告、标准映射和 main-bus JSON loader；旧 CoalitionRecord、旧 JSONL 和旧 metrics JSON 继续兼容。
6. P2 已实现冻结 `msm-offline-mot-v1` schema 与可选 py-motmetrics adapter；当前只在 2 帧离线 smoke fixture 上验证 IDF1/MOTA/MOTP 可计算，HOTA 明确 unavailable，可选依赖缺失时输出 `unavailable_reason`。依赖仅位于 `/home/linux/.cache/msm-p2-venv`，版本 `motmetrics 1.4.0`，默认 requirements、在线路径和 D6 本地指标主线均不变。
7. 当日 D6 全量回归为 `82 passed`；指定 P2 环境的 2 帧 fixture 输出 IDF1=1.0、MOTA=1.0、MOTP=0.15。该数值只证明 adapter/backend 接线可运行，不是跟踪质量、算法收益或生产 benchmark 结论。

## 1.3 P1 历史实测验收矩阵（2026-07-11）

| 场景 | D6 核对结果 | 状态 |
|---|---|---|
| CV 10 seed 中心正常 | 8/10 T001 双 primary 共识与授权；10/10 IDSW=0、错误重复锁=0；control=0、physical unavailable | 合同层验收闭合；2 个尾部 seed 保留回归 |
| 二级接管 | `secondary_plan_v2` active，secondary executing commit，ACK 3/3 | P1 状态合同闭合 |
| 完全分布式 | interceptor peer executing commit，ACK 3/3 | P1 状态合同闭合 |
| missing ACK | aborted，ACK 2/3，D7 commit/contract/control 均不允许 | P1 fail-closed 负例闭合 |
| SimpleFlight 10 seed | 每 seed 4 bindings、3 active + 1 standby；0/30 active pair 命中，24 detection timeout、6 timeout | 绑定合同闭合；物理拦截开放 |

本矩阵只引用现有小型 JSON/JSONL evidence，不复制 AirSim 大型日志。15 s 和 `control_dt=0.5 s` 是本批次限制，不应外推为系统上限。

## 2. 当前实现概览

当前 D6 已实现轻量、可测试的本地指标主线：

- 数据模型：`EpisodeMetrics`、`TrackRecord`、`AssignmentRecord`、`EventRecord`、`LinkRecord`、`TerminalRecord`。
- 收集器：`MetricsCollector.add_track/add_assignment/add_event/add_link/add_terminal()` 和 `compute_episode()`。
- 日志接口：标准化 JSONL loader、Blocks replay JSONL loader、main episode bus metrics JSON loader、D4 active-degradation CSV loader、D7 intercept/guidance CSV/JSON loader、AirSim calibration 多 seed 汇总 loader。
- 报告接口：`ReportGenerator` 输出 `episode_metrics.csv`、`summary_metrics.csv`、Markdown 报告、分类 PNG 图和 `standard_metric_mapping.csv`；`AirSimCalibrationReportGenerator` 保留原 records/逐 seed summary/Markdown，并新增 `airsim_calibration_cross_seed_aggregate.csv`、`airsim_calibration_paired_comparison.csv`、`airsim_calibration_aggregate.json`、`airsim_calibration_aggregate_report.md`。cross-seed 分组去掉 seed 并保留实际规模，统计键会从 `scenario_version` 移除运行 seed 片段但 records 保留原值；paired comparison 输出 pair/missing seed、delta mean/std、Cohen's dz 和固定 RNG 的 2000 次 bootstrap 95% CI。单一 seed 对仅为 `descriptive_only`，不输出推断 CI/effect size。
- 拦截聚合：calibration record/CSV/summary/cross-seed 直接保留 execution/contract 的成功、collision/range/abort、最小距离、拦截耗时、visual PNG、terminal switch/takeover 和 gate reject 指标。availability gate 要求 `intercept_summary.json`、`control_commands.csv`、显式 summary/pair/status 或正数 D7 execution event 证据；无证据的 read-only episode 写 `None/unavailable`，不把默认零解释为失败。计数输出跨 seed `sum`；四类 outcome 使用实际 target count 输出 opportunity/rate；距离、时间、比例输出分布统计。abort 只从同 scope 的 `intercept_status_counts` 派生，D6 不从失败原因猜测。Outcome 表只显示有证据的行并明确 scope。
- main runtime 接入：`--p1-calibration-sweep` 已在 batch 结束后自动调用 `AirSimCalibrationReportGenerator.write_report_bundle()`，输出 `d6_airsim_calibration/airsim_calibration_records.csv`、`airsim_calibration_summary.csv`、`airsim_calibration_summary.json` 和 `airsim_calibration_report.md`。D6 只消费 sweep 已写盘目录，不启动 AirSim、不控制 camera/gimbal、不参与 D4/D5 降级或配准决策。
- 批量统计：count、mean、sample std、stderr、normal-approximation 95% CI、median、p05、p95。
- 分组统计：通用报告按 `metric_scope`、`seed`、`scenario_group` 和实际 `drone_count/resource_count/target_count/camera_count` 分组；AirSim calibration bundle 按 `metric_scope`、`seed`、`scenario`、`comparison_role`、secondary height/FOV/count、detection backend 和 actual scale/trend 字段分组。

当前依赖保持轻量：Python 标准库、NumPy、matplotlib、pytest。默认测试不依赖 AirSim 服务、Stone Soup、TrackEval、py-motmetrics、SCRIMMAGE、GPU 或网络；可选 benchmark 没有替换任何默认在线路径或 D6 本地离线评估路径。

## 3. 已实现指标

### 3.1 EpisodeMetrics 与规模字段

`EpisodeMetrics` 显式包含：

```text
episode_id
seed
scenario_group
batch_seed
metric_scope
drone_count
resource_count
target_count
camera_count
duration
mission_outcome
success_reason
failure_reason
eval_priority
implementation_status
evidence_path
scenario_version
standard_mapping_version
standard_metric_family_summary
module_duration_ms
loop_latency_ms
record_latency_ms
cpu_budget_utilization
gpu_budget_utilization
performance_budget_violation_count
metadata
```

规模口径：

- 优先读取 `truth_summary` 顶层或 `truth_summary["scenario"]` 中的 `drone_count/resource_count/target_count/camera_count`。
- Blocks replay 从 `resources`、`truth_objects`、`cameras` 计算规模。
- 缺失时从 assignment、terminal、event、link metadata 中推断资源、目标和相机集合。
- `drone_count` 缺失时默认等于 `resource_count`。
- `2v2/5v5` 只保留为 baseline 场景名，不能作为分母或规模推断来源。

测试已覆盖 `episode_id/scenario.name` 含 `5v5`，但实际规模为 `3/3/4/6` 的情况，D6 按实际字段输出。

### 3.1.1 Mission outcome、root cause、性能和 EVAL tracking

P0-A/P0-C 字段已进入 D6 episode 主线：

```text
mission_outcome in {success, partial, failed, aborted}
success_reason
failure_reason
root_cause
top_failure_causes
eval_priority
implementation_status
evidence_path
module_duration_ms
loop_latency_ms
record_latency_ms
cpu_budget_utilization
gpu_budget_utilization
performance_budget_violation_count
```

实现口径：

- `mission_outcome` 优先消费 `truth_summary` 或 event metadata 中显式写盘的 outcome；缺失时基于 intercept success、required success count、abort/runtime exception、安全事件和部分进展被动派生。
- `success_reason`、`failure_reason` 优先使用上游写盘原因；缺失时由 D6 根据指标摘要生成简短解释。
- `top_failure_causes` / `root_cause` 从 records/metadata 和 D6 已计算指标派生，覆盖 tracking、assignment、terminal_gate、guidance、coverage、runtime_exception、communication、safety、performance；D6 不做控制链路因果推断或回写。
- 性能监测消费上游写盘的 module duration、loop latency、record latency、CPU/GPU budget utilization 和 budget violation；缺失时输出 0 和 metadata placeholder，便于 main 报告保持 schema 稳定。
- `eval_priority`、`implementation_status`、`evidence_path` 用于 main 报告追踪 P0/P1 状态，优先来自 truth_summary/metadata。

### 3.1.2 标准化评估映射最小版

P0-A 标准化评估映射最小版已实现，版本固定为 `cuas-standard-map-v1`。D6 只建立离线报告映射，不引入外部认证流程，也不改变 D1-D7/main runtime 控制链路。

映射最小字段：

```text
engineering_metric
standard_metric_family
standard_sources
implementation_status
evidence_requirement
```

覆盖的标准指标族：

```text
mission/root cause
detection
tracking
assignment
degradation
terminal
communication
guidance/intercept
safety
performance
reproducibility/evidence
```

实现口径：

- `standard_mapping.py` 保存 `COURAGEOUS/MDPI/OCEF -> EpisodeMetrics` 的静态映射表。
- `MetricsCollector.compute_episode()` 从 `truth_summary` 或 event metadata 读取 `scenario_version`，固定写入 `standard_mapping_version=cuas-standard-map-v1`，并在 metadata 中保留 `standard_metric_families`、`standard_metric_family_summary` 和 `standard_mapping` 摘要。
- `EpisodeMetrics.metric_names()` 不包含 `scenario_version`、`standard_mapping_version`、`standard_metric_family_summary`，避免污染数值统计。
- `ReportGenerator.write_episode_csv()` 输出这三个非数值字段；`write_markdown_report()` 在 `EVAL Tracking` 后输出 `Standard C-UAS Mapping` 表；`write_standard_mapping_csv()` 输出 `standard_metric_mapping.csv`。
- AirSim calibration records/summary 也保留 `scenario_version`、`standard_mapping_version`、`standard_metric_family_summary`、`evidence_path`、`trend_key`、`secondary_height_bucket`、`metric_scope` 和 actual scale 字段，便于 main 长期趋势报告复用。

### 3.2 探测指标

```text
detection_probability = TP / (TP + FN)
false_alarm_rate = FP / duration
missed_detection_rate = FN / (TP + FN)
```

当前实现来源：

- 落入 `truth_timestamps` 的 `TrackRecord.truth_id + timestamp` 或显式 offline match/miss 事件构成离线配对裁决；仅有 truth opportunity 列表不足以使指标可用。
- `TrackRecord.truth_id is None` 的在线隔离航迹不自动计 false alarm；只有离线裁决为 truth-pair 集合外的带标签检测才计虚警。
- `truth_summary.truth_timestamps` 或 `total_truth_opportunities` 定义真值机会数。

### 3.3 跟踪指标

```text
track_rmse = sqrt(mean(||position - truth_position||^2))
track_continuity = matched_truth_timestamp_pairs / truth_timestamp_pairs
id_switch_count = count(global_track_id changes for the same truth_id over time)
```

`id_switch_count` 对每个 `truth_id` 按时间排序，比较连续 timestamp 的 `global_track_id`。D6 不修改 `global_track_id`，只统计 D2/上游输出的身份连续性。

### 3.4 分配指标

```text
duplicate_assignment_count =
  count(targets assigned to more than one active resource in the same plan snapshot)

unassigned_high_threat_count =
  count(high-threat truth/track items without effective active assignment)
```

当前有效分配要求：

- `AssignmentRecord.active == True`。
- `authorization_state` 属于 `recorded/authorized/approved/human_approved/operator_approved` 等有效状态。
- 同一 `(timestamp, plan_id, version)` 内统计重复分配。

D6 只统计分配结果，不产生重分配建议；`AssignmentPlan` 版本有效性仍由 D3/main 控制链路负责。

### 3.5 降级指标

基础降级：

```text
failover_time = mean(t(degraded_stable) - t(central_failure))
consensus_rounds = mean(consensus_rounds event values)
degraded_completion_rate =
  degraded_task_completed / (degraded_task_completed + degraded_task_failed_or_cancelled)
```

D4 active/passive 扩展已实现 P1 基线：

```text
active_degradation_count
active_degradation_precision
unnecessary_active_degradation_count
passive_failover_count
secondary_node_takeover_count
secondary_reassignment_count
d4_reassign_pending_count
distributed_fallback_count
failover_active_window_delta_s
```

当前识别来源包括 `EventRecord.event_type`、`metadata.mode/degradation_mode`、`metadata.action`、`metadata.assignment_phase`、`metadata.fallback_type`、D7 reject reason 和 D4 CSV loader。`metadata["trigger_reason"]` 等触发原因会进入 `EpisodeMetrics.metadata["trigger_reason_distribution"]`。

已补 P1 最小主动降级必要性口径：

```text
active_degradation_precision
unnecessary_active_degradation_count
```

D6 只在 D4/main 写入可分类的 `review_label`、`active_degradation_necessary`、`post_window_outcome` 或 pre/post risk/window 后验字段时计入 precision 分母；缺少标签时 `active_degradation_label_count=0` 且 precision 输出 unavailable/JSON `null`，只保留 `active_degradation_count`。

### 3.6 末端指标

```text
terminal_association_accuracy
terminal_id_switch_count
ambiguous_fov_event_count
friend_overlap_hold_count
time_to_terminal_lock
terminal_lock_count
multi_view_consensus_rate
cross_view_conflict_count
duplicate_terminal_lock_count
```

当前来源：

- `TerminalRecord` 中的 `decision_state`、`local_track_id`、`assigned_global_track_id`、`expected_global_track_id`、`association_correct`。
- `EventRecord` 中的 `terminal_lock`、`terminal_fov_entry`、`terminal_ambiguous_fov`、`friend_overlap_hold`、`multi_view_consensus_result`、`cross_view_conflict`、`duplicate_terminal_lock`。
- Blocks replay 的同帧多相机 bbox/label metadata，可生成 multi-view consensus/conflict 基线事件。

D5 仍然负责身份确认和 `global_track_id` 合同；D6 不重绑、不改写本地或全局 ID。

### 3.7 二级视角与侦察云台指标

```text
secondary_network_joint_full_view_frame_rate
secondary_network_mean_coverage_ratio
secondary_visible_target_union_ratio
secondary_single_camera_full_view_frame_rate
secondary_detect_count
projection_valid_rate
geometry_gate_pass_rate
registered_candidate_count
stable_cross_view_registration_count
not_registered_count
cross_view_association_count
secondary_detect_available_but_not_registered_count
cue_pointing_error_count / mean_deg / rmse_deg / max_deg
gimbal_pointing_error_count / mean_deg / rmse_deg / max_deg
```

当前来源：

- `EventRecord`/`LinkRecord.metadata` 中的 `secondary_node_type/node_type/camera_node_type`，规范化为 `fixed_downlook_secondary`、`mobile_recon_gimbal` 或 `secondary_network`。
- main/D4/D5 写盘的覆盖/FOV 记录，例如 `covered_target_ids`、`covered_target_count`、`coverage_ratio`、`joint_full_view`、`single_camera_full_view_count`。
- D5 跨视角事件，例如 `d5_cross_view_association`、`cross_view_association_count`、`multi_view_consensus_result`。
- D5 注册缺失事件，例如 `secondary_detect_available_but_not_registered_count`、`detect_available=True` 且 `d5_registered=False`。
- D5 detect-to-registration 校准字段，例如 `projection_valid_rate`、`geometry_gate_pass_rate`、`registered_candidate_count`、`stable_cross_view_registration_count`、`not_registered_count`，以及 reject/outcome reason `not_all_targets_visible`、`network_union_incomplete`、`projection_invalid`、`geometry_gate_rejected`、`stability_window_failed`、`no_global_binding`、`stale_or_missing_recon_cue`、`registered_to_global_track`。
- cue/gimbal 指向误差字段，例如 `cue_pointing_error_deg/rad`、`gimbal_pointing_error_deg/rad`、`pointing_error_deg/rad`。

归一化口径：

- network joint full-view 先按 frame 聚合二级网络覆盖集合，再除以实际 target count，不从 `2v2/5v5` 场景名推断目标数。
- mean coverage ratio 使用实际 target count；只有日志显式给出 per-frame ratio 时才直接消费 ratio。
- single-camera full-view rate 使用 camera-frame 分母；分母来自日志显式 camera frame count 或实际 camera count，而不是场景名。
- `EpisodeMetrics.metadata["secondary_sensing_node_type_metrics"]` 保留 node-type 级指标，报告中对比固定俯视二级节点和机动高空侦察云台节点。

D6 只消费 main/D4/D5 写盘日志，不下发 cue、不控制云台、不触发接管/重分配。

2026-07-08 `p1_d4d5_mobile_recon_20260708_055948*` 是历史 mobile recon stress 批次，可作为 D6 已能消费 `mobile_recon_gimbal`、coverage、bbox、gimbal 和 funnel 字段的旧证据。

2026-07-08 registration calibration v2 历史基线已验证 D6 侧消费口径：

- 输出目录：`research_modules/airsim_runtime/outputs/p1_d4d5_registration_calibration_runtime_v2_20260708*`。
- D6 bundle：`d6_airsim_calibration/airsim_calibration_records.csv`、`airsim_calibration_summary.csv`、`airsim_calibration_summary.json`、`airsim_calibration_report.md`。
- 场景：single seed，3 case；height 200 m，FOV 110 deg，secondary_count 3，detection backend 为 `simGetDetections`。
- 关键结果：`projection_valid_rate=1.0`；`geometry_gate_pass_rate≈0.474`；stable cross-view registration 为 51/55/53；cross-view association 为 4/4/5；degradation case `not_registered_count=35/35`；full-view mean≈0.048，best≈0.143；coverage mean≈0.771。
- 结论：D6 报告链路已能输出 projection/gate/stable registration/not-registered/funnel/D7 reject；剩余是更多真实 AirSim 多 seed/N-v-N 数据和 review labels，用于形成长期趋势。D6 记录该结论为离线评估状态，不参与 D4/D5/D7 控制或云台调度，也不从 `2v2/5v5` 场景名推断规模。

### 3.8 通信指标

```text
cross_node_latency_ms
message_drop_rate
out_of_order_count
stale_track_update_count
video_metadata_delivery_rate
bbox_delivery_rate
consensus_latency_s
```

当前来源：

- `LinkRecord`。
- 带通信字段的 `EventRecord.metadata`。
- Blocks `blocks_sensor_observations.jsonl` 的 `communication` 字段。
- Blocks frame image/bbox metadata 生成的 video metadata 和 bbox delivery 样本。

推荐保留字段：

```text
source_node_id
target_node_id
relay_node_id
link_type
message_type
sequence_id
sent_timestamp
received_timestamp
measurement_timestamp
arrival_timestamp
payload_kind
delivered
stale_after_s
```

### 3.9 D7 gate、visual PNG switch 与拦截统计

D6 已能从 D7 `control_commands.csv`、`guidance_records.csv`、`guidance_summaries.json`、`intercept_summary.json` 读取：

```text
camera_quality_gate_pass_rate
los_quality_gate_pass_rate
maneuver_margin_gate_pass_rate
terminal_switch_allowed_rate
visual_png_switch_count
terminal_takeover_rate
terminal_switch_reject_count
mode_switch_count
terminal_contract_reject_count
intercept_success_count
collision_intercept_count
range_intercept_count
time_to_intercept_s
min_range_m
gate_reject_count
```

`terminal_switch_allowed_rate` 的分母只包含带有 `terminal_switch_allowed` 字段的 D7 control command。空缺字段不进入分母。

`visual_png_switch_count` 的来源包括显式 `visual_png_switch/vision_png_switch/d7_visual_png_switch` 事件，或 `guidance_law=png_vm/png_ttc` 且伴随 `mode_switch=True`、`terminal_mode_entered=True`、`mode=vision_terminal/visual_png/vision_png` 的 D7 记录。

`terminal_takeover_rate` 按 unique `(resource_id, target_id)` pair 统计，证据包括 `terminal_locked=True`、`terminal_switch_allowed=True`、`vision_terminal` mode、`terminal_mode_entered=True`，或 `guidance_law` 为 `png_vm/png_ttc/los`。`terminal_handover_pending` 和 `detection_seen` 只能说明候选可见，不能单独算 takeover。

### 3.10 安全指标

```text
constraint_violation_count
human_override_count
```

安全事件是一级输出。即使其他指标良好，也不能把安全约束触发或人工覆盖事件用总体成功率平均掉。

## 4. 已实现输入适配器

| 适配器 | 输入 | 当前状态 | 边界 |
|---|---|---|---|
| `load_episode_log_jsonl()` | 标准化 `truth_summary/track/assignment/event/link/terminal` JSONL | 已实现并测试 | 未知 record type 直接报错，避免 schema drift 静默进入报告 |
| `load_blocks_replay_jsonl()` | `blocks_frames.jsonl`、可选 `blocks_sensor_observations.jsonl` | 已实现并测试 | 只读文件，不 import AirSim，不调用 runtime API |
| `load_main_episode_bus_metrics()` / `load_main_episode_bus_metric_files()` | `main_episode_bus_metrics.json`、`main_episode_bus_contract_metrics.json` | 已实现并测试 | 只还原已写盘 `EpisodeMetrics`；不运行 AirSim、不合并控制结果 |
| `load_d4_active_degradation_decisions()` | D4 active-degradation CSV | 已实现并测试 | 只消费已写盘 review/window 字段；有 label/后验字段才计算必要性，不从事件名判定 |
| `load_d7_intercept_outputs()` | `control_commands.csv`、`intercept_summary.json` | 已实现并测试 | 只离线评估 D7 输出，不发控制 |
| `load_d7_guidance_timeseries()` | `guidance_records.csv`、`guidance_summaries.json`、D7 control/intercept 输出 | 已实现并测试 | 保留 D4/D5 state、plan/version、guidance law 和 reject reason metadata |
| `load_airsim_calibration_records()` / `AirSimCalibrationReportGenerator` | AirSim batch/seed/case 目录中的 `d4d5_stress_metrics.json`、`airsim_blocks_summary.json`、`main_episode_bus_metrics.json`、`main_episode_bus_contract_metrics.json` | 已实现并测试 | 只读已写盘文件；按真实 count 字段、settings FOV 和 metadata 分组，不从场景名推断规模 |

## 5. 已完成接入与 main runtime bus 剩余条件

当前 D6 已能消费 D4/D5/D7 产物。完整 integrated episode metrics 仍取决于 main runtime 的写盘和汇总接线，但 D7 真实执行结果的 main/orchestrator 合并已经完成一条主线。

截至 2026-07-07 的已完成接线：

- 真实 AirSim D7 执行后，main/orchestrator 从 `control_commands.csv` 与 `intercept_summary.json` 提取执行结果并合并进正式 `main_episode_bus_metrics.json`。
- 执行前的合同检查口径保留为 `main_episode_bus_contract_metrics.json`，用于诊断 D3/D4/D5/D7 gate 与合同拒绝，不再覆盖正式执行指标。
- 正式指标中的 `intercept_success_count`、`collision_intercept_count`、`range_intercept_count`、`terminal_contract_reject_count`、`gate_reject_count`、`guidance_law_counts` 等以执行后合并结果为准。
- D6 仍然只消费日志/CSV/JSON/metrics 文件；不订阅 runtime bus，不触发 replan、failover 或 guidance。

已具备 D6 侧消费能力：

- D4：可读取 active-degradation CSV；可从事件 metadata 中识别 active/passive、secondary takeover/reassignment、distributed fallback、D4 reassign pending、触发原因、review label、trigger/decision timestamp、selected coordinator、coverage cell 和 pre/post window 字段。
- main bus：可读取正式 execution `main_episode_bus_metrics.json` 与 raw contract `main_episode_bus_contract_metrics.json`，保留 `metric_scope`、seed/scenario/实际规模字段、D7 guidance/intercept 指标和 reject reason metadata。
- D5：可通过 `TerminalRecord`、terminal/multi-view event、Blocks bbox/camera metadata 计算末端准确率、ID switch、lock、歧义、friend hold、多视角一致和冲突；可消费 cross-view association、secondary detection available but not registered 和 cue/gimbal pointing error metadata。
- D7：可读取 control/guidance/intercept CSV/JSON，计算 gate、visual PNG switch、terminal takeover、模式切换、拦截结果和 reject metadata。
- Blocks CV：可从 `blocks_frames.jsonl` 与 `blocks_sensor_observations.jsonl` 构建 truth summary、规模字段、视觉检测、terminal records、video/bbox link records 和通信链路样本。

P0/P1 状态（2026-07-12）：

- 无 P0 blocker。D6 离线主线、`id_switch_count` 显式输出、实际规模归一化、main bus metrics loader、D4/D5/D7 写盘消费和二级侦察指标消费均已具备。
- D6 terminal delivery 指标、availability-aware replay 和 baseline/candidate 对照 bundle 已闭合；2v2 candidate `20/20` 达到非退化验收。M5N2 同几何/同窗口 paired 对照、`png_ttc` 多 seed、dropout 矩阵、trend coast 默认 profile 决策及长期趋势仍开放。
- 剩余 P1 不是 D6 在线控制职责，而是真实 episode 写盘、自动汇总、paired 验收和长期趋势报告的持续性要求：

- 真实 episode 需要持续写出 D4 `review_label`、`trigger_timestamp`、`decision_timestamp`、`selected_coordinator`、`coverage_cell` 和固定 pre/post window 字段；D6 已能消费这些字段并计算主动降级必要性/精度。
- 同一 episode 目录仍需稳定聚合 Blocks、D4、D5、D7 和 D6 标准化 JSONL/CSV/JSON，并保持同一 episode clock；D6 loader 本身不会扫描 runtime bus、启动 AirSim 或补写上游日志。
- D5 terminal association、cross-view conflict、duplicate lock、friend overlap hold、validation label 等真实 AirSim 事件应持续进入 D6 可读记录；D6 已有指标和 Blocks metadata 基线。
- AirSim 报告已能把 `mobile_recon_gimbal` / `fixed_downlook_secondary` 的 50m/200m coverage、detect-to-registration funnel、coverage funnel、baseline/enhanced、bbox 和 cue/gimbal 指向指标纳入多 seed 自动汇总；长期趋势仍需要 main 持续产出更多 5v5/N-v-N 批次。
- main runtime P1 D4/D5 calibration sweep 已自动调用 D6 `AirSimCalibrationReportGenerator` 生成标准 records/summary/Markdown bundle；D6 当前重点是保持多 seed 自动汇总口径稳定，沉淀 coverage/funnel/gimbal、projection/gate/stable registration、not-registered、D7 guidance reject 和 `trend_key/evidence_path` 长期趋势，统计 active degradation precision，并按真实 `drone_count/resource_count/target_count/camera_count` 做 actual scale 分组。
- 多 seed、5v5/N-v-N 和非默认 episode 需要继续保持 `metric_scope=execution/contract` 双口径，正式指标采用执行后 metrics，contract metrics 仅用于诊断；D6 已能直接读取两类 main bus metrics JSON，报告分组已按 `metric_scope + seed + scenario_group + scale` 实现，不从场景名推断规模，并在 metadata/Markdown 中保留 reject reason 分布。

2026-07-12 D6 owner 当前回归为 `88 passed`，另有 1 条本机 matplotlib `Axes3D` warning。coalition commit、终端 contract/control/switch/physical 四层验收、pair/target/coalition 分层 physical success、detect/coast、PNG delivery 诊断、main-summary fallback 及 P1 多来源统一报告均已实现并保持回归。2v2 candidate 的 `20/20` 只闭合本轮非退化门槛；M5N2 candidate 与历史 baseline 不可直接配对，仍须按相同几何、窗口和 seed 验收。`physical_intercept_count` 没有物理 evidence 时保持 unavailable，有物理 evidence 且未命中时为 0。

## 6. 开源/外部项状态

| 项目 | 当前状态 | 未实现原因 | 缺少条件 | 优先级 |
|---|---|---|---|---|
| Stone Soup metrics | 没有 Stone Soup import、对象转换器或 metric generator 调用 | 保持默认依赖轻量；D1/D2 track/truth 尚未冻结到 Stone Soup 类型 | 版本锁定；D1/D2 adapter；GroundTruthPath/Track/Detection 映射；坐标和门限合同；CI 样例 | P2 |
| OSPA/GOSPA | 文档有公式，`EpisodeMetrics` 未输出字段 | 需要帧级 truth/estimate set 序列和 cutoff/order | 稳定集合序列；匹配门限；目标 birth/death/遮挡规则 | P2 |
| CLEAR MOT/MOTA/MOTP 标准库对照 | py-motmetrics 1.4.0 隔离 adapter 已实现 IDF1/MOTA/MOTP；真实 backend 仅有 2 帧 smoke，默认环境可无依赖 | 只消费冻结 offline truth/association schema，不覆盖系统级指标，尚未形成真实 replay benchmark | main/D2/D5 持续产出 `msm-offline-mot-v1` fixture；距离/IoU 门限由 fixture metadata 固定 | P2 adapter 已实现，benchmark 未完成 |
| HOTA | unavailable；py-motmetrics 1.4.0 不提供该指标 | 需要支持 HOTA 的外部 evaluator 与完整帧级检测、关联和身份评估表 | 稳定 frame-level 输出；occlusion/reappearance 规则；TrackEval 等 evaluator | P2 |
| AirSim 原生 recording replay | 未实现通用 parser | main 已提供更直接的 Blocks JSONL；原生 recording 字段、坐标、相机版本差异大 | 原生 recording 样例；schema 版本；NED/相机/时间轴映射；测试容差 | P2 |
| Live AirSim replay/API | 未实现，且不作为 D6 默认能力 | D6 边界是 offline-only | 如未来需要，也应由 main runtime 导出日志，D6 仍只读文件 | 禁止在线控制 |
| SCRIMMAGE metrics bridge | 未实现 | 当前仿真主线是 AirSim Blocks 和合成日志；仓库没有 SCRIMMAGE 输出样例或 message schema | SCRIMMAGE episode 输出；agent/resource/target ID 映射；通信事件字段；episode clock 对齐 | P3 |

## 7. 批量统计与报告

D6 报告生成器当前输出：

- `episode_metrics.csv`：每个 episode 一行，包含规模字段、`scenario_version`、`standard_mapping_version`、`standard_metric_family_summary`、所有 `EpisodeMetrics.metric_names()` 和 metadata JSON。
- `summary_metrics.csv`：全局与 `metric_scope + seed + scenario_group + scale` 分组统计。
- `standard_metric_mapping.csv`：输出固定版本 `cuas-standard-map-v1` 的标准映射行，字段为 `engineering_metric/standard_metric_family/standard_sources/implementation_status/evidence_requirement`。
- Markdown 报告：中文说明、规模范围、场景分组、`Standard C-UAS Mapping` 表、固定俯视二级节点 vs 机动侦察云台节点对比表、汇总表、reject reason 分布和图表链接。
- PNG 图表：`detection`、`tracking`、`assignment`、`degradation`、`terminal`、`secondary_sensing`、`communication`、`guidance`、`safety` 和 selected metric distributions。
- AirSim calibration bundle：旧 records/逐 seed summary 文件保持不变；新增 cross-seed aggregate CSV、paired comparison CSV、aggregate JSON/Markdown。main 必须显式写 `comparison_role=baseline|enhanced`；配对键包含稳定 `scenario_group`、去除运行 seed 参数后的 `scenario_version`、实际 N/M/camera count、几何、backend 和 seed，case_name 只审计。active-degradation count/precision/label_count/unnecessary 优先消费 d4d5 stress 显式字段，再 fallback main metrics。

2026-07-10 的 2v2 execution 回灌复核是历史基线，用于固定以下读取优先级：正式 `main_episode_bus_metrics.json` 为执行口径，`main_episode_bus_contract_metrics.json` 为合同诊断口径，`airsim_blocks_summary.integrated_result.metrics` 仅是可能过时的历史快照，不进入 D6 calibration record。该历史基线的正式 execution 为实际规模 `2/2/2/2`、成功拦截 `2/2`、视觉 PNG 切换 3 次；旧 Blocks 快照仍为 `3/3/2/0`，该上游摘要一致性由 main runtime 负责。

历史 10-seed 基线 `p1_gap_closure_2v2_multiseed_20260710_seed001..010` 验证了 full-flow execution cross-seed 行可完整包含十项拦截指标，并输出 `intercept_success_count sum=18`、`opportunity_count=20`、`rate=0.9`，collision/range/abort 为 `18/0/2`。这些数值只保留为当时场景的历史基线，不代表 2026-07-11 M=5、N=2 SimpleFlight 诊断结果；报告由 D6 离线读取 summaries 生成，不启动 AirSim、不发控制。

统计口径：

```text
mean
sample_std
stderr = sample_std / sqrt(N)
ci95 = mean +/- 1.96 * stderr
median
p05 / p95
```

偏态或长尾指标，例如 `id_switch_count`、`constraint_violation_count`、`terminal_switch_reject_count`，在正式结论中仍需要 bootstrap 或非参数方法复核。当前实现先满足回归和工程比较。

## 8. P1 最终开放项

1. 建立长期真实 multi-seed 趋势：按冻结 scenario/version/profile/actual scale 持续生成跨提交趋势、门限稳定性和 bootstrap 置信区间，不把单批次结果外推为长期结论。
2. 完成真实逐时刻 producer schema：优先补 D3 plan history/churn，并统一 episode clock、version/epoch、source provenance 和 availability；最终 snapshot 不能替代逐时刻记录。
3. 治理跨批次失败原因：稳定 reason taxonomy、字段版本和 unknown/unavailable 口径，避免不同 producer 对同一失败重复计数或重命名。

以上三项是当前 D6 P1 的唯一开放主线。下列内容保留为历史专项规划，不改变本节最终优先级。

### 2026-07-12 PNG Delivery 历史验收规划

1. 用同一 z=-30 m、35 s 高净空几何、相同运行窗口和相同 seed 运行 M5N2 baseline/candidate；分别统计 target、active-primary pair 和 coalition completion，不跨层回填。
2. 独立运行 `png_ttc` 多 seed，持续写出并汇总 area jump、bbox clipping、not expanding 和 TTC out-of-range 拒绝。
3. 固定锁定后 dropout 时刻覆盖 1-5 帧；1-2 帧核对有界预测，3-5 帧必须按 0.25 s 上限 fail-closed，且 online truth use 和错误身份绑定保持 0。
4. trend coast 只有在错误绑定为 0、命令跳变不恶化、物理成功不下降时才可进入默认 AirSim profile；否则保持 candidate-only。
5. 所有新批次稳定写出 profile、filter state/reason、TTC reject、soft/coast elapsed、lock、visual mode、三轴速度命令和四层结果；缺字段保持 unavailable。

### 2026-07-11 M 对 N 评估框架

专项框架见 `subagent_reviews/D6_M_TO_N_EVALUATION_FRAMEWORK_REVIEW.md`。D6 将四条研究路线 `independent/simultaneous/sequential/hybrid_primary_reserve` 按中心正常、二级接管、完全无中心三个层级评估，并覆盖几何退化、时间同步、通信异常和成员失效。所有新增指标按 `frame/member/wave/coalition-version/target-episode/episode/batch` 分层聚合，继续区分 `unavailable/null`、证据完整的真实 `0` 和 `not_applicable`。

2026-07-11 已冻结并实现 `TargetDemandRecord/CoalitionRecord/ArrivalRecord`，扩展 assignment/terminal coalition/member 字段，接入 JSONL loader/writer、`EpisodeMetrics`、episode CSV、batch summary 和 Markdown。已实现 demand/unmet slots、formation/reconfiguration、arrival/wave/hybrid、geometry rejection、canonical duplication/cross-node IDSW/common-information rejection、planned/authorized/erroneous lock、same-resource continuity、成员生命周期、通信预算和安全聚合；既有 RMSE/NIS/NEES 指标继续复用 track/governance 路径。探测 POD/miss/FAR 现同时要求 truth opportunity 与离线 match/miss 配对裁决；仅有 truth 列表或 truthless center tracks 时统一 `None/unavailable`。

`duplicate_terminal_lock_count` 保持通用同帧多资源观测计数，不再被错误锁覆盖；`erroneous_duplicate_lock_count` 仅计 `k=1`、版本冲突和超需求。规范 `center_replan_request_created/deduplicated/ack_no_change/applied/expired` 事件已接入请求数、去重数、no-change、applied、expired、pending dwell 与收敛时间；缺事件为 unavailable。当前 P1 合同层已有 CV 8/10、二级/分布式 commit 和 missing-ACK fail-closed 实测证据；2026-07-12 的 2v2 candidate 已达到 `20/20` 非退化验收，未闭合的是同几何 M5N2 paired 物理/联盟验收和长窗口实验矩阵，不是 D6 聚合合同。第 9 节 P2 项只作为隔离 benchmark，其中 SCRIMMAGE 保持 P3。

### 2026-07-11 四导引律证据边界

`p1_guidance_four_law_smoke_20260711` 已验证 main 的 guidance law 回灌和 D6 同 seed
配对链路。当前 CSV 有 21 条指标配对行，但每行 `pair_count=1`，只覆盖 seed 7；四种
导引律在 2 秒窗口内均 timeout。PNG VM/TTC 的末端切换允许率约为 0.762/0.810，最小
距离约为 2.812/2.798 m。该批次只作为接口、写盘和指标口径验收，不作为最终命中率或
算法排序证据。

四律对照的 P1 验收仍要求：使用相同场景版本、实际 N/M/camera count、初始几何和
seed 集合；延长 `intercept_max_duration`；至少形成多个独立 paired seeds；同时报告
timeout、成功/abort、最小距离、切换允许率、接管率和 gate reject 原因。只有样本量满足
要求后才输出 effect size/bootstrap CI 和算法优劣结论。

1. 场景库接口已完成；下一步由 main/CI 使用稳定的 `scenario_group/version`、tags、difficulty、expected failure modes、actual scale、seed matrix 和 evidence path 调度真实批次，D6 再生成跨提交趋势、阈值回归和证据完整性摘要。
2. CV 5v5 的 D1-D3 联合聚合：在同一 episode clock 下汇总 D1 detection/fusion/latency/covariance、D2 association/continuity/ID switch 和 D3 assignment/version/hysteresis 指标，形成从感知到分配的 funnel。D6 只消费 main 写盘的稳定 schema，不从 truth name、场景名或后验结果重建在线决策。
3. YOLO/MOT 的 recall、local-ID continuity、cross-view rate、pipeline latency 和 CPU/GPU budget 已实现；下一步消费 D5 写盘的模型/权重版本、输入分辨率、目标像素尺度、throughput、内存、drop/fallback 字段，形成更完整的 accuracy-latency-budget 对照。D6 不加载 `best.pt`、不运行 YOLO，也不把缺失性能样本记为 0。
4. COURAGEOUS/MDPI/OCEF 完整标准化报告：在 `cuas-standard-map-v1` 基础上补测试阶段、复现纪律、evidence index、场景覆盖矩阵、限制条件和外部审计说明，并把 D1-D7 指标映射到统一中文报告模板。
5. 长期多 seed 对照：现有 cross-seed aggregate、严格 paired comparison、effect size 和 bootstrap CI 只需用真实成对 5v5/N-v-N 批次持续验收；missing seed、单 pair、无 review label 和 read-only unavailable 继续保持不可推断状态。
6. D4/D5 长期趋势与真实标签：持续跟踪 coverage/funnel/gimbal、projection/gate/registration、D7 reject 和 active-degradation review/window；`active_degradation_precision` 只使用 main/D4 写盘的真实 review label 或后验 outcome/risk。
7. execution/contract/evidence availability 已完成，后续仅作为 schema 回归项：正式 execution、raw contract、各自 evidence path 和 availability 状态不得互相覆盖，不再重复扩展同义拦截字段。

## 9. P2 下一步

1. 帧级匹配表：定义 D1/D2/D5 的 frame-level truth/detection/track export，包含 timestamp、truth_id、global/local track ID、position/IoU/distance、occlusion/reappearance 状态。
2. 外部 MOT 对照：py-motmetrics adapter 代码与 2 帧离线 smoke 已完成；IDF1/MOTA/MOTP 在冻结 schema 上可用，但真实 benchmark 尚未完成。下一步用真实冻结 replay 校准距离/IoU 门限、遮挡和重现规则。TrackEval/HOTA 保持未实现 optional，不能用 py-motmetrics 结果伪造 HOTA，也不能替换默认在线关联路径。
3. Stone Soup/OSPA 对照：在 D1/D2 对象映射和版本锁定后接入 Stone Soup metrics 与 OSPA/GOSPA。
4. Bootstrap/非参数 CI：在真实多 seed 数据规模足够后，为偏态指标提供可选统计方法。
5. SCRIMMAGE bridge：仅当 AirSim 多机规模或通信建模不足以回答实验问题，并且已有真实 SCRIMMAGE 样例和 schema 时作为 P3 可选项推进。
6. AirSim 原生 recording parser：只有在 Blocks JSONL 不能满足评估需求时，才补通用 recording parser。

## 10. 验收命令

从仓库根目录运行：

```bash
pytest -q research_modules/d6_evaluation_metrics/tests
git diff --check -- research_modules/d6_evaluation_metrics subagent_reviews/D6_*
```

文档验收点：

- 明确 D6 只消费日志，不参与控制。
- 明确 `id_switch_count` 是 D2/D6 强制显式指标。
- 明确指标按实际 `drone_count/resource_count/target_count/camera_count` 归一化。
- 明确 D4/D5/D7 AirSim 产物的 D6 侧 loader 已实现；D7 real execution metrics 已由 main/orchestrator 合并进正式 `main_episode_bus_metrics.json`，raw contract metrics 保留为诊断文件。
- 明确 P1 合同层和联盟 lifecycle 指标已完成，但物理命中、长期场景库与 CI 趋势仍为 P1。
- 明确 py-motmetrics 当前只完成 2 帧离线 smoke；IDF1/MOTA/MOTP 可用、HOTA 不可用，且默认在线路径与 D6 本地主线未替换。
- 明确 Stone Soup、AirSim replay、SCRIMMAGE 等开源/外部项的实际未实现状态、原因和缺少条件。

## 11. 2026-07-12 P1 汇总接口实施状态

本轮新增 `p1_system_evidence.py`，执行边界仍是“消费而不控制”。D2 六难度、D3 membership/version churn、D4 episode communication、D5 native MOT admission 和 D7 per-primary 四层漏斗，已进入同一版本化 CSV/JSON/中文 Markdown/PNG 输出。

已完成：

1. 输入接受 JSON 路径、mapping、dataclass/to_dict 对象或记录序列，不导入在线 producer。
2. 每个指标独立携带 availability；缺失物理拦截时不会由 mode switch 或 control allowed 推断。
3. D5 按 ByteTrack/BoT-SORT backend 分组，IoU fallback 与 native active 分开。
4. D2 按 `scenario_difficulty` 分组，保留 non-discriminative 标记。
5. D3 分开统计 plan、coalition version、epoch、membership change/hold，并保留 per-primary/arrival 配置。
6. D4 从 tick 序列统计 ACK、lease、epoch、owner、commit/fail-closed；`owner=None` 阶段作为真实 owner transition 保留。
7. D7 四层只消费同名持久化证据，禁止跨层回填。
8. truth identity 不写入汇总，显式在线 truth 使用会使 truth policy 失败。

后续 P1 由 main 提供真实 AirSim 多 seed 路径并调用 CLI；D6 只校验 schema、availability、分组和报告结果。没有真实 producer summary 时，相应 source manifest 必须保持 unavailable。

## 12. 真实 AirSim Native MOT 专项（2026-07-12）

D6 已离线消费 `preflight_rows.json`、`range_rows.json` 和 `confirm_rows.json`，生成 `outputs/p1_native_mot_20260712/` 下的中文 CSV/JSON/Markdown/PNG。证据固定分为 32 帧 discovery、实际 42 帧的约 40 帧 range precheck、102 帧 confirmation，禁止跨等级池化。

本轮结果：20 m confirmation 中 ByteTrack/BoT-SORT 均为 native rate 1.0、continuity 1.0、IDSW 0、fallback 0；P95 分别约 8.292/18.232 ms。但离线 precision/recall 仅约 0.324/0.293，均未准入。30/50 m precheck 无接受检测。下一步由 main/D5 核对离线 truth 框、IoU/几何门限和时间对齐后复测；D6 保持被动消费，不降低准入阈值。

## 13. Replay/Execution 合并计划状态（2026-07-13）

已完成 `d6.execution-metrics-merge.v1` 纯函数接口：

1. integrated replay 保留离线探测、跟踪、分配等指标；main episode bus 对终端、cross-view、在线 truth、合同/控制/切换和物理执行指标具有优先权。
2. 每个执行指标同时记录 replay 值、execution 值、availability、source path 和最终 selected source；显式 `0` 是有效证据，缺字段或 `None` 是 unavailable。
3. `persisted_frame_count` 和 `warmup_inclusive_frame_count` 分开保存，不进行 `+1` 或其他隐式推断。
4. main 后续只需调用合并函数并写盘；D6 不导入 AirSim runtime，也不修改在线 episode 状态。

后续回归要求：真实样本 replay `cross_view_association_count=0`、main bus `=55` 时最终值必须为 55；execution 缺失时不得制造执行值；帧数两层必须分别有 provenance。

## 14. 三维规模化 D1/D2 离线制品接入（2026-07-20）

### 已完成

1. 新增版本化 D6 公共记录：D1 consistency adapter、D1 sensor-range record、D2 identity
   adapter、truth-isolated episode 和 batch summary。
2. D1 入口校验公开 result schema、record schema、内部 content digest、record count、
   `truth_usage=offline_evaluation_only`、aggregation provenance 和逐记录内容一致性。总体
   metric 由 D1 原样保留，sensor/range 统计只基于 D1 公开 aggregation records。输入和
   输出以 `d2_lineage_mapping` 为规范字段；旧 `canonical_mapping` 显式兼容，双字段冲突
   或可用 truth metrics 缺映射摘要时拒绝。
3. D2 入口校验 evaluation/metrics/policy schema 和四类来源摘要。D6 不读取 frame mapping
   来猜测身份，只保留 D2 已发布的指标；文件输入缺任一 expected source hash 时拒绝，在线
   真值隔离或有效 frame/truth-frame 证据不完整时指标和 truth counts 均 fail-closed。
4. episode context 显式携带 scenario/version/run/seed 和实际 target/resource/recon/camera
   数量。D1 provenance 或 D2 episode ID 不一致时拒绝合并。
5. batch 按 scenario/version/actual scale 分组，distinct seed 计算描述统计与固定随机种子
   percentile bootstrap。单 seed 只给描述统计。
6. 报告输出逐 seed CSV、D1 sensor-range CSV、聚合 JSON 和中文 Markdown；所有输出均
   显式包含 `id_switch_count`，缺证据时值为空且原因可追溯。

### 验证

2026-07-20 使用最小公开制品 fixture 覆盖 5/20/50/100/200，专项 `14 passed`，D6 全量
`334 passed`。测试验收为接口、D1 lineage 新字段/旧字段/冲突/缺失、文件/来源哈希、
availability、假零拒绝和规模分组正确；未运行 AirSim，未运行
正式 20 个未见 seed，未验证任何工程阈值。

### 后续计划

1. main-owned reporting 已持久化 D1/D2 公开制品并调用 D6 episode/batch builder；D6 不接入
   在线总线，也不修改该接线。
2. clean `5263e2b` 的 nominal 200 对 200、seed `1000-1019` 已完成 20 episode 描述性聚合。
   三层 manifest/hash 链和“重新构建记录等于持久化记录”均为 20/20。
3. main 仍需把同一合同扩展到 5/20/50/100/200 正式多规模矩阵，并纳入最终统一 scalable 3D
   总报告。届时再报告 sensor/range RMSE、NEES、NIS 与 strict
   IDSW/continuity/duplicate 的置信区间和不可用原因分布。
4. GAP 状态为“D6 适配合同、20 seed nominal 描述性聚合已闭合；正式多规模性能验收、strict
   身份证据和最终统一报告仍开放”。

## 15. D2 部分身份诊断接入（2026-07-23）

### 已完成

1. 新增 `d6.d2_scalable3d_partial_identity_adapter.v1` 归一化记录；旧
   `d2.scalable3d_identity_evaluation.v1` 不含 partial 时继续兼容读取。
2. 独立输出 mapping/frame/adjacent-transition coverage、IDSW lower bound、anchor interval
   count、anchor exclusion 和 scored-mapping exclusion reason；strict IDSW 的字段、availability
   和聚合路径不变。
3. 校验 partial schema/scope/denominator policy、有限 coverage、availability/reason、全部计数
   守恒、lower-bound 范围以及 strict/partial 并存时的保守关系；不接受或构造 upper bound。
4. 校验 identity manifest schema、episode、availability、strict metric availability、
   evaluation SHA-256、四类 source hash、audit/config 和 evaluator-only provenance。任一失败只将
   partial 标为 unavailable，并给出稳定 reason。
5. 逐 seed CSV、aggregate JSON、中文 Markdown 均新增独立 partial 栏和来源状态；输出固定声明
   `strict_id_switch_count_backfilled=false`、`id_switch_upper_bound_reported=false` 和
   `control_consumed=false`。
6. 2026-07-23 专项 `26 passed`，D6 全量 `567 passed, 1 warning in 22.96s`；验收门限零失败。
7. 只读消费 clean `4ac3bb2` 的 nominal 200 对 200、seed 1000、10 秒真实 producer episode。
   manifest/evaluation 和四项源文件 SHA-256 全部一致；strict IDSW 保持 unavailable，partial
   mapping/frame/adjacent coverage 为 `8906/9038`、`3/48`、`0/9400`，385 个 anchor interval
   上的保守 lower bound 为 7，未回填 strict，也未生成 upper bound。
8. 对 clean `5263e2b` 的同类 seed `1000-1019` 运行 20 episode 批量复核。manifest 链、
   重建记录一致性和在线真值隔离均为 20/20；partial mapping/frame/adjacent micro coverage
   为 `178531/181110`、`103/959`、`1149/187800`。lower bound 在 19 个 episode 可用，合计
   199/15215 anchor intervals。逐 seed CSV、聚合 JSON 和中文 Markdown 已写入候选批次的
   `d6_truth_isolated_20seed/`；strict 未回填，也未生成 upper bound。

### 仍开放 P1

1. nominal 200 对 200 的 20 seed producer evaluation/identity manifest 已通过描述性聚合。
   main/D2 仍需生成正式 5/20/50/100/200 多规模、困难场景和长时数据，D6 再比较 coverage、
   blocker、anchor exclusion、lower-bound 分布与置信区间。
2. strict IDSW/continuity 的多 seed 可用性仍取决于完整 lineage truth sidecar。partial lower
   bound 不能关闭 strict 指标 unavailable，也不能支持 promotion、控制切换或算法优劣结论。
3. 真实 AirSim、遮挡/杂波/漏检/OOSM 和不同目标密度下的 partial coverage 仍无正式证据；D6
   不从当前 nominal 20 seed 结果外推。

## 16. D2 identity commitment v2 接入（2026-07-23）

### 已实现并测试

1. `truth_isolated_offline.py` 按冻结 schema/policy 严格区分 evaluation v1/v2。v1 commitment
   metrics 全部显式 unavailable；v2 独立复算嵌入 evidence bundle SHA-256、all/observed
   分母、coverage、state/reason、blocker/watermark/overflow 和 binding violation。
2. 新 typed commitment record 已进入 episode DTO、逐 seed CSV、aggregate JSON 和中文
   Markdown；aggregate 对 coverage 使用 committed/denominator micro 口径，对 blocker 和
   watermark mean 使用 record count 加权，不把 episode coverage 简单平均冒充总体 coverage。
3. strict IDSW 继续只消费 D2 `metrics.id_switch_count`。跨 uncommitted gap 的 strict 值由
   D2 冻结 policy 提供；D6 固定输出
   `strict_id_switch_count_backfilled=false` 和
   `uncommitted_gap_treated_as_zero_id_switch=false`。
4. `runtime_plan_outcome_join.py` 已兼容 v2。显式 uncommitted 只关闭命中的 plan binding
   identity/state/距离诊断，保留 reason/details 且不暴露 truth；普通缺失保持 unavailable，
   schema、source hash、embedded evidence hash 或 audit 篡改仍全局拒绝。
5. 测试覆盖合法 v2、v1 compatibility、缺审计字段、分母/coverage 篡改、负水位线年龄、
   overflow 矛盾、candidate binding 违规、普通 lineage missing、跨空档 strict IDSW 消费、
   CSV/JSON/Markdown 和 runtime 局部不可用。2026-07-23 D6 全量结果为
   `598 passed, 1 warning in 21.44s`，零失败。

### main 接线与实测状态

1. main 必须把每帧 `identity_commitment_by_track` 与 D2 track/frame 原子持久化，生成
   `d2.scalable3d_identity_evidence.v2` 和
   `d2.scalable3d_identity_evaluation.v2`；不得丢弃 evaluation 内嵌
   `identity_evidence_records` 或降级伪装为 v1。
2. 调用 `build_truth_isolated_episode_record()` 时传入 evaluation path、外部 evaluation
   SHA-256、四类 `expected_source_hashes`、identity manifest path 和 manifest SHA-256。
   runtime join 的 input spec 继续提供 11 类独立 `HashedArtifact`。
3. uncommitted mapping 必须保持 truth candidate、source observation/lineage 和三个 evidence
   count 为空/零；main 不得从 tracker 历史 key、actor 名称、距离或 truth sidecar 回填。
4. 接线后先重跑 clean seed 1100 baseline/candidate，再决定是否继续多 seed。验收必须同时
   检查 strict IDSW availability、all/observed commitment coverage、D2 track count、D3
   assignment count、两个 binding violation 为 0 和 online truth use 为 0。

### 2026-07-23 clean seed 1100 结果

1. main 已在 clean commit `909669b2eefeab2ce30c8ac389d6bf9c0a8cbabc` 上原子持久化
   baseline/candidate 的 v2 evidence、evaluation、audit 和 manifest。场景为 nominal
   200 对 200、2 个侦察节点、2.2 秒，在线真值使用为 0。
2. baseline strict IDSW、track continuity、coverage continuity 和 commitment coverage
   分别为 `9`、`0.865`、`0.870` 和 `1.0`；D2/D3 数量为 `203/200`。
3. candidate commitment coverage 为 `1714/1787=0.9591494124`，73 条未承诺记录由 69 条
   ambiguity hold 和 4 条 after hold 组成。source/candidate binding violation 均为 0，
   online truth isolation 为 true；D2/D3 数量为 `201/197`。
4. candidate 的三个恢复航迹 `GT3D-000185/186/202` 在评分帧 `2.1308153039 s` 使用
   `measurement_timestamp=1.2 s` 的证据，差值 `0.9308153039 s` 超过固定 `0.9 s`
   lineage window。D6 按合同令 strict identity metrics unavailable，不扩大窗口，也不回填
   strict IDSW。
5. v2 真实 episode 持久化、独立审计和安全绑定验收通过；候选算法 promotion gate 未通过。
   seed 1101/1102 已停止，不形成多 seed 性能结论。

### 仍开放 P1

- 上游需先使 candidate 在固定 `0.9 s` 评分合同内提供可评分的恢复证据，并恢复 strict
  IDSW/continuity availability；D6 不通过放宽窗口或后验回填规避该问题。
- 候选还需解释或消除 D2 track count `203 -> 201`、D3 assignment count `200 -> 197` 的
  可用性下降。单 seed 准入通过前不恢复 1101/1102。
- 真实 AirSim、多 seed、多规模、困难谱系和长时 blocker/watermark/overflow 分布仍需 main
  生成冻结制品。commitment coverage 不能替代 strict IDSW、partial lower bound、物理成功或
  promotion gate。

## 17. 发布新鲜度证据与 D6 partial 绑定修正（2026-07-23）

### 已完成

1. 只读审计 clean commit `65568579c99e4ef9939f0519f66c46d3076ef035` 的 nominal
   200 对 200、2 个侦察节点、2.2 秒、seed 1100 baseline/candidate。episode ID、identity
   evaluation/manifest SHA 和 D6 manifest 来源摘要全部一致，在线真值使用为 0。
2. 确认 D6 正确消费新的 publication-stale recovery reason。candidate 中 3 条恢复保持
   uncommitted；commitment state 为 `1711 committed + 69 hold + 7 after hold`，coverage
   `0.9574706212`，source/candidate binding violation 为 `0/0`。
3. 确认 strict availability 已恢复。baseline/candidate 的 strict IDSW 为 `9/3`，track
   continuity 为 `0.865/0.8266667`，coverage continuity 为 `0.870/0.8283333`，
   duplicate assignment 为 `0/0`。
4. 修复 D6 对 partial v1 的 audit 分类绑定。校验改为
   `partial unavailable = audit unavailable + excluded + uncommitted`，同时要求
   `available + ambiguous + partial unavailable = total`。没有放宽 schema、manifest、
   source hash、truth isolation、lower-bound 或 strict/partial 分栏规则。
5. 新增生产语义正例和分类缺口负例。修复后对两组原始制品重新适配，partial provenance
   均通过，lower bound 为 `9/3`，strict 值未回填。
6. 专项 partial 用例为 `13 passed`；D6 全量为
   `600 passed, 1 warning in 21.55s`，验收门限零失败。

### 准入判定

strict-unavailable 阻断关闭，但候选仍不准入。D2 航迹 `203 -> 201`、D3 分配
`200 -> 197`、track continuity 下降 `0.0383333`、coverage continuity 下降
`0.0416667`，违反冻结的可用性与连续性非退化要求。候选继续默认关闭，seeds 1101/1102
保持停止。

### 仍开放 P1

1. main/D2 将 `identity_commitment_recovery_config` 的 schema、config version、门控开关、
   `max_recovery_evidence_age_seconds` 和时钟定义写入 episode 公共配置或 identity
   evaluation/manifest，并由 D6 做 SHA-bound 消费。当前制品只能证明新 reason 实际发生，
   不能独立证明完整配置快照。
2. main 在集成 D6 修复后，从原始 A/B producer 制品生成新的 truth-isolated 派生 bundle。
   原目录内旧 episode record 保留为修复前证据，不原地覆盖。
3. 上游形成新的结构歧义候选，先在 seed 1100 同时关闭 D2/D3 数量和连续性退化，再决定是否
   恢复 1101/1102。D6 不调整 `0.9 s` 评分窗口，不用 partial 或 commitment coverage
   替代 strict。
4. 真实 AirSim、至少 20 个未见 seed、多规模、困难谱系和长时 blocker/watermark/overflow
   分布继续开放。本轮单 seed 三维质点结果不形成置信区间或工程性能结论。

## 18. Manifest v2 配置谱系消费（2026-07-23）

### 已完成

1. 新增 D6-owned 配置谱系 DTO，区分 manifest v1 不可用、manifest v2 已验证和 v2
   验证失败。该 DTO 不参与 strict/partial 指标计算和在线控制。
2. 对 manifest v2 复算配置规范 JSON SHA-256，检查非空 v2 schema、配置记录数、
   `d2_record_count`、consistency 与 source 声明。
3. 新增在线 D2 JSONL 路径和期望 SHA API。实际文件摘要必须同时匹配调用方、identity
   evaluation 与 manifest；每条 D2 发布的 recovery config 必须与清单完全一致。
4. 将结果写入 episode JSON、逐 seed CSV、batch source provenance 和配置谱系聚合。
5. 运行时计划结果同时接受 manifest v1/v2。v1 保留兼容输出；v2 缺字段、配置/摘要篡改、
   帧间漂移和计数不符均 fail closed，并在 admission 中暴露配置谱系要求和验证状态。
6. 新增 v1 兼容、v2 正例、配置 SHA 篡改、配置内容篡改、JSONL 帧间漂移、缺字段和记录数
   不符测试。专项 `83 passed`，D6 全量 `611 passed, 1 warning in 21.55s`，零失败。
7. 通过真实 main 三维质点 3 对 3、seed 70、1.2 秒 episode 验证 producer manifest v2
   接线。3 条 D2 发布的配置谱系全部通过；该用例没有启动 AirSim。

### 当前状态

配置谱系 consumer P1 已闭合，生产端到 D6 的最终端到端证据也已补齐。main 在 detached clean
commit `ff881316243ff5a2991a4659ab78637ed625d123` 上完成 nominal 200 对 200、2 个侦察
节点、2.2 秒、seed 1100 baseline/candidate 重跑。两组 manifest 均为 v2，配置规范 SHA
均为 `sha256:bd8e362ec4ca128ed902826750b26d862286770d3c0c4d0b75960a50911a201a`，
配置记录数与 D2 记录数均为 9。D6 episode 和 runtime provenance 均验证通过。

旧 `65568579...` A/B 缺配置快照仍是历史事实，不覆盖也不改写。最终 A/B 使用新目录和新
manifest 形成独立证据。

### 最终判定与后续

1. baseline/candidate 的 D1 航迹为 `202/202`，D2 航迹为 `203/201`，D3 分配为
   `200/197`，runtime binding windows 为 `593/587`。
2. strict IDSW 为 `9/3`，track continuity 为 `0.865/0.8266667`，coverage continuity
   为 `0.870/0.8283333`。partial lower bound 同为 `9/3`，但保持
   `strict_id_switch_count_backfilled=false`。
3. baseline/candidate 配置谱系在 episode JSON 和 runtime outcome 中均 available；
   `online_d2_records_verified=true`、`provenance_verified=true`，两组在线真值使用均为 0。
4. 配置谱系 P1 关闭。结构歧义保活算法准入 P1 未关闭：candidate D2/D3 可用性和 continuity
   仍退化，候选保持默认关闭。
5. 按冻结停止规则不运行 seeds 1101/1102、10 秒或 20-seed 矩阵。AirSim、多规模、困难谱系
   和长时性能证据继续由 main 后续调度。

## 19. 身份承诺执行门 clean A/B 审计（2026-07-23）

### 已完成

1. 只读消费提交 `7e15dac9cdaf6743999dfe045a70676fd31a17d6` 的
   `hold_only` 与 `hold_plus_centroid`。两组 root manifest 均为 clean，场景、seed、时长、
   规模和离线真值一致，运行配置只差质心候选开关。
2. 独立复算 strict IDSW `3/3`、track continuity
   `0.8266666667/0.8266666667`、coverage continuity
   `0.8283333333/0.8283333333`、duplicate assignment `0/0`、commitment coverage
   `0.9574706212/0.9574706212` 和 mapping 分类 `1491/218/76`。两类未承诺绑定违规和
   online truth use 均为 0。
3. 从 `online_observations.jsonl` 冻结 `t=1.0 s` 的 11 个未承诺目标，确认 D3 计划
   `v1 -> v2` 强制升版、迟滞绕过和旧绑定撤销。版本 2、版本 3、D5 主动视觉/终端绑定、
   D7 导引和 runtime control 对该集合的继续执行数均为 0。
4. 使用当前 D6 API 从原 producer 制品重新构造 truth-isolated episode，episode record
   完全一致；4 个派生文件逐字节相同。runtime input specification 的哈希验证通过，重建
   JSON 也逐字节相同。
5. 候选组 46 个质心候选全部被拒绝，`oosm_scan=30`、
   `unbalanced_component=16`，实际应用为 0。两臂不构成有效 treatment，不计算效应或
   非劣结论。

### 后续计划

1. 上游先生成 `applied component count > 0` 的冻结同输入 A/B。D6 保持 strict IDSW、
   continuity、D2/D3 可用性和安全门联合准入，不接受只看 IDSW 的晋级。
2. treatment 门通过后再执行多 seed、长时、困难谱系和 AirSim 证据矩阵。
3. 新增 D6 标准离线派生项，自动输出 D3/D5/D7 对未承诺冻结集合的后续继续执行计数。
4. 在统一 scalable 3D 报告中显式联接 truth-isolated strict identity 结果，同时保留在线
   summary availability，不做跨证据层覆盖。

本节不改变 D6 算法、控制路径或 AirSim 接口。完整结果见
`docs/IDENTITY_GATE_CLEAN_SEED_1100_AUDIT_CN.md`。

## 20. 正式 R0 后验跳过审计（2026-07-25）

本节先保留旧批次和 177/900 增量阶段的处置记录，最新状态见后文“完整 R0 scope 审计
状态”。历史条目中的“当前”和“后续”不再代表本轮完成后的项目状态。

### 已完成

1. 复核 900 个 R0 episode 的后验代次证据。结构性 scope 为 900/900，D6 clean-formal
   为 895/900。
2. 精确定位 5 个 delayed-noisy episode。它们的 pending 均为空、declared skip 均为 1，
   但最终后验与 D2 最后消费后验的状态、协方差和有效时刻不相等。
3. 将离线评估升级到 v10。D6 对 skip 增加逐轨完整后验比较；现有公共 payload 不能证明完整
   D2 输入等价，因此上游版本化完整摘要缺失时 skip 不进入正式代次守恒。
4. 保留原最终代次未消费门限，新增完整后验不等价差值原因。缺字段、伪 skip、航迹集合变化、
   新接受证据和内容变化均失败关闭。

### P0 与后续

1. 原始 main 运行时 P0：D2 输入签名遗漏状态、协方差和有效时刻，导致变化后的最终后验被
   跳过。
2. 合法修复路径是实际消费最终后验；若保留 no-op skip，则必须发布版本化完整输入摘要。
   main 已采用前一路径完成 5 个异常 cell 的定向回归。
3. D6 v10 已提交为 `8e955f3`，runtime 修复已提交为其后继 clean source commit
   `98d01bf`。正式证据不能跨提交拼接；下一步应基于 `98d01bf` 重新执行完整 900-cell
   R0 scope，再由 D6 v10 生成报告。
4. 对旧批次只允许声明 `formal_scope_complete=900/900` 和 `clean-formal=895/900`；
   新批次在 177/900 阶段只允许声明 shard execution 和五个 target cell 正式通过，不允许声明
   900/900 formal acceptance 或完整 5700-cell matrix complete。
5. 2026-07-25 D6 全量回归为 `894 passed, 1 warning in 85.66s`；5 个原始异常
   episode 的 v10 实物复核均保持三层 formal gate 为 false。

### 定向修复状态

main 已修复 finalization 输入判定，并在
`/tmp/msm-r0-finalize-fix-20260725` 定向重跑 5 个异常 cell。D6 v10 合并结果显示五项
generation contract 均为 `verified`：D1 最终代次等于 D2 最终消费代次，消费次数等于
发布次数，消费与节拍前合并之和等于 D1 代次，declared skip 为 0，pending 为空。

该批次在 dirty 工作树生成，五项均为开发态描述性证据，正式验收资格为 0/5。当时状态按两层
管理：

1. runtime P0 的错误跳过现象已在定向开发回归中消失，修复代码已由 clean source commit
   `98d01bf` 固化，进入“完整 R0 待正式重跑”；
2. R0 正式证据仍保留旧 clean 提交的 895/900 结论，不能拼接定向结果；
3. 完整 R0 formal rerun 已在后继 clean source `1e5ed8d` 上启动，当前 shard 0、5、9
   完成 45/45，shard 8、18 完成 21/45，合计 177/900；D6 新专项已独立复核五个原失败
   cell；
4. 新批次验收要求 900/900 generation contract 为 `verified`、skip 为 0 或具有版本化完整
   D2 输入摘要、pending 全空、episode 全部 clean-formal；
5. 若运行时未来重新出现 `skip=1`，没有完整输入摘要时 D6 继续失败关闭，不以计数式放行。

### 正式增量状态与后续（全量完成前阶段记录，2026-07-30）

1. source 为 `1e5ed8ddcf27f375e922a447decfbd875d21bfdf`，`repository_dirty=false`；
   execution plan SHA-256 为
   `8804ecb4dd0513db55906905f031832711012974fc911546df40e09fb297d373`。
2. shard 0、5、9 的 checkpoint 为 `complete`，每个 45/45；shard 8、18 为 `paused`，
   每个 21/45，总计 177/900，剩余 723。
3. 新专项绕过既有聚合，独立复核 5v5 seed 1000/1005/1008/1018 和 20v20 seed 1009。
   五项均 clean-formal、两层 formal eligible、generation verified，failure reasons 为空。
4. 不得把新批次 5/5 与旧批次 895/900 相加，也不得用五项定向结果声明 177/177。
5. main 完成其余 723 cell 后，再由 D6 对同一 source、同一 plan 的完整 900-cell scope
   生成逐 cell、聚合和中文报告。

### D6 专项实施状态（2026-07-30）

1. 已冻结五个 target cell 与五个 shard 的 177/900 进度输入。
2. 已实现 source、execution plan、shard ledger、cell result 和 artifact tree 的独立哈希
   复核，并调用 D6 低层合同从在线总线与 summary 重算后验代次。
3. 已输出逐 cell CSV、聚合 JSON、中文 Markdown 和 `SHA256SUMS`；完整输出保存在 D6
   outputs 忽略目录，紧凑报告与结果保存在 docs。
4. 当时专项 5/5 通过。该阶段计划为执行剩余 723 cell，再审计完整 R0 scope；不对
   未审计的 172 个已执行 cell 作推断。
5. 专项 `9 passed, 1 warning in 2.37s`，D6 全量
   `1243 passed, 1 warning in 150.38s`；输出 SHA、语法和 owned-path diff 检查通过。

### 完整 R0 scope 审计状态（2026-07-30）

1. [x] source `1e5ed8d` 的 20 个分片均完成 `45/45`，正式 R0 执行与审计范围为
   `900/900`。旧 source 的 895 项没有与本批次拼接。
2. [x] D6 已独立核对 execution plan、merged scope 三文件 SHA、20 个 shard ledger、
   900 个 cell result 和每个 episode artifact tree。producer D6 聚合和 episode
   governance audit 不作为输入。
3. [x] 900 项均重新调用低层 evaluator。clean formal、实验矩阵资格和 generation
   verified 均为 `900/900`；skip 总量为 0，pending 全部排空，在线真值使用为 0。
4. [x] D1 generation/full publication 合计 `28777/28777`，D2 final consumed 为
   `28777`；D2 consume/publication/merge 为 `6411/6411/22366`。
5. [x] 输出完整 JSON、逐 cell CSV、中文 Markdown 和 SHA-256 清单。tracked docs 保存
   中文报告及紧凑 JSON，全部 28 个失败 cell 均保留。
6. [ ] 严格总门为 `872/900`。28 项均为高威胁 M 对 N 场景的
   `d4_fail_closed:collecting_member_acks`。该项由 D4/main 处理联盟 ACK 收敛和 episode
   终止条件；D6 继续失败关闭。
7. [ ] D2 ID switch 在 900 项中均显式不可用。后续需要独立离线真值配对制品后再由 D6
   统计，不允许把不可用写成 0。
8. [ ] 完整父矩阵仍为 `900/5700`。G1、A1、A2、A3 尚无同范围结果，因果收益和模型准入
   继续不可用。

专项与五项兼容测试 `19 passed, 1 warning in 2.31s`；D6 全量
`1253 passed, 1 warning in 132.38s`。AirSim 集成计划已检查，本次只读三维质点制品审计
没有新增 AirSim 消息、episode 或硬件接口，因此无需修改。

## 21. 学习作用域正式证据审计（2026-07-26）

### 已完成

1. 实现独立、只读审计入口，消费一个学习 execution plan、对应 scope merge 目录和显式
   R0 对照目录，不接入控制路径。
2. 验证父计划、作用域、分片、cell、episode 和模型 bundle 的哈希绑定；验证 preflight
   device、版本、运行诊断、在线真值为 0 和有限状态。
3. 按变体检查 D3、D4、D5 图模型和 D5 主动视觉的实际 assist 采用。D5 图模型同时要求正的
   候选边计数；shadow、fallback、bundle-loaded-only 和零边空调用均失败关闭。
4. 按 `comparison_key` 唯一配对 R0。必选物理指标任何一侧不可用时不计算非退化，不补零。
5. 输出 JSON、逐 cell CSV、中文 Markdown 和 SHA-256 清单；定向测试覆盖完整通过、缺 R0、
   计划/merge/分片/episode 篡改、重复与错配 R0、设备不符、物理结果缺失、scope 不完整、
   单组件空采用、C1/F1 缺必要组件和 D5 零候选边。

2026-07-26 主审补充后定向回归为 `36 passed, 1 warning in 2.35s`，其中新增 29 项；D6
全量回归为 `930 passed, 1 warning in 78.98s`。warning 为既有 Matplotlib `Axes3D`
环境提示。

### 验收边界

审计 `pass` 只表示证据链完整、实际采用成立且必选 R0 配对指标未退化。它不表示因果效果，
不授予模型晋级，也不修改默认控制路径。缺少任一必要证据时，`non_degraded` 保持空值并返回
`fail_closed`。

### main 待提供

1. d59352b 对应学习 execution plan 与完整 scope merge 目录。
2. 相同父计划、来源提交、外生配置和传感器随机计划的 R0 execution plan/merge 对。
3. execution plan 实际绑定的 D3、D4、D5 图模型或 D5 主动视觉 bundle 根目录。
4. 若需设备强校验，提供预期 preflight device。

收到上述输入后只运行既有审计，不再扩展算法。正式制品缺失前，D6 不声明学习采用、非退化或
晋级。

## 24. D4 规划专用区域建议链（2026-07-29）

### 已完成

1. 新增最小独立审计器，直接消费 D3 plan、D4 advice、main consumption 和 D3 successor
   在线记录，不依赖 D3/D4 运行时实现，也不读取在线真值。
2. 复用 runtime plan outcome join 的规范绑定集合，允许 M 对 N 的多资源同目标，拒绝同一
   资源重复绑定。
3. 严格核对 advisory/source plan、consumption/advisory、successor/source/advisory 的计划
   编号、版本和 metadata。仅升版、续租或 metadata 刷新不计干预。
4. 对 `advisory-v2` 强制规划与执行权限分离。消费可进入下一轮规划，五类执行权限必须全部为
   false；规划专用区域还必须处于 replan eligible 且未被故障代际围栏阻断。
5. 分别输出合同链、真实绑定干预、同键 R0、非退化和模型收益 availability。单 episode 的
   source/successor 改善只标为 `descriptive_source_successor`。
6. 增加故障代际负例。最新 fault-fenced 建议没有 transfer、没有 consumption、没有 successor
   时记录安全围栏通过，不计模型性能失败。
7. 接入 scalable 3D 离线报告 v11，并增加中文区域规划链表。

### 当前证据

20 对 20、8 区域、seed 29 正例为 `17 -> 18` assignments、`3 -> 2` unassigned，
`online_truth_use_count=0`。合同链和真实绑定干预可用，描述性非退化为 true；同键 R0 和模型
收益不可用。`t=2.0 s` 中心故障负例为 `fault_generation_fence_verified`，安全违规为 0。
两项均为内存只读三维质点探针，不是 AirSim、实飞或模型性能实验。

### 后续计划

1. main 持久化与 treatment 完全同键、独立执行的 R0 episode，并由现有严格学习采纳审计
   验证 comparison key、来源提交、外生配置和随机计划。
2. D4 v4 只有在注册后才能作为 learned treatment。规则建议器正例继续只用于合同回归。
3. 至少完成独立多 seed 配对后，再报告模型非退化、置信区间和收益；单 seed 不晋级。
4. 保留 fault-generation、owner、epoch、lease、reserve 和执行权限门，不为获得正例放宽。

验收测试：专项 `6 passed`，D6 全量 `1202 passed, 1 warning in 106.92s`。AirSim 集成计划
已检查；本次没有消息接口、AirSim episode 或硬件适配变化，无需修改。

## 25. D3 A1 来源独立 v2 外部审计（2026-07-31）

### 已完成

1. 实现独立只读审计器和命令行入口。实现不导入 D3 高层 evaluator、aggregate、模型或
   solver，不训练、不选模、不拟合归一化、不调整阈值。
2. 固定核验结果目录普通文件清单、符号链接、`SHA256SUMS` 覆盖和逐文件摘要；输出目录
   已存在时拒绝覆盖。
3. 独立核验 generation plan/summary/checkpoint/progress/seed registry、D3-only export、
   100 个 episode、seed 20000-20099、来源提交存在、生成记录 clean、有限状态和在线真值
   使用为 0。
4. 逐行扫描 169 MB 匿名数据集。复算 292 帧、100 个 episode、60/20/20 episode 和
   178/57/57 frame 分组，强制数据集属于 generation root，并从帧清单独立重算 split hash。
5. 同时扫描数据集和评价 JSONL 的 truth、Actor、Object 和全局身份字段。评价 JSONL 的
   `online_truth_use_count` 仅作为零值审计字段保留。
6. 独立解析固定 21 列、292 行 CSV，将身份、教师机会、三组选择边、换绑、正负类、OOD、
   拒绝原因和 fallback 与 JSONL 逐行闭合。
7. 按 D3 连续 `<f8` 规范从数据集矩阵独立重算每帧规则矩阵 SHA-256；从动作掩码、目标需求
   和匿名资源容量独立重算三组选择边安全计数，并与逐帧自报字段闭合。总体安全门只消费
   effective 独立计数。
8. 新增 CSV 内容与 `SHA256SUMS` 联合篡改、错误数据集路径、三类安全计数冒充、边越界、
   规则矩阵摘要冒充、评价真值字段和 split 清单摘要冒充负例。

### 实际结果

- 正类安全换绑 `13/110=11.82%`，门限 `>=5%` 且至少 1 帧；
- 正类教师完全匹配 `8/110=7.27%`，门限 `>=2%` 且至少 1 帧；
- 负类 exact-R0 绑定 `182/182=100%`，门限 `>=99%`；
- fallback `94/94` 矩阵与绑定均为 exact-R0；
- 非零代价修正 98 帧，OOD 27 帧，拒绝 94 帧；
- 所有安全计数和模型 assignment/plan/runtime 输出为 0；
- CSV `21/21` 列、`292/292` 行闭合，逐行 mismatch 为 0；
- split hash 独立复算为 `f1380dd6...ca5`；R0、candidate、effective 各有 21637 条边，
  三组独立安全计数均为 0；
- 正式 seed 1000-1019 读取数为 0，所有权限为 false；
- 预注册总体机器门通过，但不形成运行采用、物理收益或正式准入。

### 后续计划

1. 保留 test 子组教师完全匹配 `0/25` 的泛化限制。不得将总体门通过改写成 test 子组通过。
2. 由 main/D3 决定是否在完全独立的正式保留集执行一次预注册评价；D6 只做同样的外部
   只读审计，不读取 seed 1000-1019 进行调参。
3. 运行采用、计划发布、控制与物理收益必须由新的可比 episode 和同键规则基线提供；本次
   离线机器门不得进入默认控制路径。
4. 如后续 contract、阈值或 bundle 变化，必须使用新的输出身份和新的审计目录，不覆盖
   2026-07-31 产物。

验收：专项 `18 passed`，新增 9 个失败关闭负例；D6 全量
`1348 passed, 1 warning in 139.42s`，产物 `SHA256SUMS` 全部通过。AirSim 集成计划已检查；
本任务不改变 AirSim 接口或运行流程。
