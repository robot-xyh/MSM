# Main 实现差距总审计

**审计来源**：D1-D7 子智能体分别对照 `subagent_reviews/*_REVIEW_AND_PLAN.md`、`C_UAS_MAINSTREAM_SOLUTIONS_AND_DIFFICULTIES.md` 和各自 `research_modules/` 代码完成自查。
**审计目标**：列出共识算法与计划使用的开源代码哪些已经实现，哪些没有实现，为什么没有实现，以及缺少哪些条件。
**边界**：本文只用于科研仿真、接口补齐和后续工程排期；不涉及真实硬件、实机处置、火控或绕过授权的自动动作。

## 2026-07-31 D4 建议代次 clean-smoke 收口

### 当前判断

- 新增运行级 P0：无。
- D3-D4 时期/租约 clean 证据：已通过 6/6。
- D4 建议当前代次修复：开发回归和新 clean 复验均完成。
- 正式 900-cell：仍关闭；D4 低层 formal 门已恢复为 `6/6`，当前直接阻断为正式
  execution plan/矩阵 metadata 尚未生成，以及本机存储不满足 20 GiB 保护线。

### 事实

1. clean `49e43ea` 的 6 个 high-threat episode 覆盖 5、100、200 三档及 seed
   `7/17`。核心制品、配置哈希、有限状态、在线真值隔离、计划标识/版本/时期/租约、
   49 个当前联盟目标和 16101 条通信处置均为 `6/6` 通过。
2. 100 和 200 规模的 4 个重规划 episode 在 v2 计划发布后仍输出 v1 advice，且没有
   最终 v2 advice。这是在线生产时序问题，不能通过 D6 后过滤解决。
3. D4 owner 已增加 advice publication generation gate，分别输出总线发布资格和规划
   采用资格。当前代次故障诊断可发布但不能采用；旧计划、旧版本、旧时期、错误租约和
   回滚不能发布。
4. main 已将在线 advice 改为基于规划后当前快照生成。规划前快照只用于离线学习帧，
   防止修复在线时序时破坏既有 D3/D4 干预数据合同。
5. D4 全量为 `913 passed, 1 warning`，scalable 3D 全量为
   `416 passed, 1 warning`。
6. clean `b063535` 的复验包含 12 条 advice，发布时当前代 12、旧代 0，最终计划
   覆盖和低层 `formal_acceptance_eligible` 均为 `6/6`。D6 没有过滤历史记录或放宽门。

### 开放 P1

1. **正式矩阵**：6-cell 不含冻结 execution plan、20-shard 和矩阵 metadata。需在
   存储条件满足后运行原生 900-cell，并由 D6 执行 targeted/full posterior。
2. **D2 身份 availability**：修复后 clean smoke 仍只有 `3/6` 完整 ID Switch 可用；缺值
   继续保持 unavailable。
3. **性能**：100 和 200 规模实时倍率低于 1，当前结果不能形成部署性能结论。
4. **存储**：2026-07-31 `/dev/shm` 总容量 16 GiB，根文件系统约 21 GiB 可用。
   两处都不能在保留 20 GiB 安全余量的同时完成正式 900-cell。

### 证据

- D6 clean-smoke 报告：
  `research_modules/d6_evaluation_metrics/reports/HIGH_THREAT_CLEAN_SMOKE_B063535_REVALIDATION_20260731_CN.md`
- D4 合同提交：`20895c7`
- main 接入提交：`a2fbdc6`

## 2026-07-30 高威胁时期租约 P1 开发闭合

### 当前判断

- 新增运行级 P0：无。
- v4 的 D3-D4 权威时期和租约不可用 P1：已在 dirty development evidence 层关闭。
- 正式准入：仍关闭。时期/租约已形成 clean 证据，但后续 clean smoke 发现 D4 advice
  在线错代；当前代码修复等待新 clean 复验，900-cell R0 尚未运行。

### 已闭合

1. D3 每个新计划身份显式绑定不可变时期和租约，并发布四个审计字段。
2. 同身份评价刷新保留原绑定，不重复权威发布、不重复 ACK、不续租。
3. 普通重规划、权限 fence、二级接管、区域后继和分布式接管均清理旧身份通用绑定，
   再绑定当前代次。
4. main 在 D4/D5/D7 消费和权威总线发布前统一绑定，缺字段时失败关闭。
5. D6 对 v5 的 100-cell 开发批次确认：
   - plan id/version `100/100`；
   - epoch available/matched `100/100`；
   - lease available/matched `100/100`；
   - current coalition closure `100/100`；
   - authoritative publication / unique identity / runtime ACK
     `151/151/151`；
   - same-identity duplicate publication 和 payload digest conflict 均为 0。

### 开放 P1

1. **clean formal evidence**：时期/租约已在 6-cell clean smoke 中通过，但 D4 advice
   仅 `2/6` formal eligible。需按上一节复验修复后的新提交。
2. **D4 建议生命周期**：旧说法“存在 superseded 与当前建议”已由 clean 证据修正为
   “部分重规划在新计划后发布旧建议且缺当前建议”。代码已修复，正式状态等待 clean
   复验。
3. **D2 身份 availability**：88/100 可用，可用部分 ID switch 合计 52；其余 12 项
   不得补零。
4. **大规模实时性**：v5 的 200 对 200 实时倍率均值为 0.142，墙钟均值/P95 为
   14.209/15.566 秒。50 对 50 以上仍未达到实时。

### 证据

- main 报告：
  `research_modules/scalable_3d_simulation/docs/SCALABLE_3D_HIGH_THREAT_P0_PRECHECK_V5_20260730_CN.md`
- D6 独立报告：
  `research_modules/d6_evaluation_metrics/reports/HIGH_THREAT_PRECHECK_V5_REVALIDATION_20260730_CN.md`
- 回归：D3 `668 passed, 1 skipped`，D4 `903 passed`，D6 `1263 passed`，
  scalable 3D `416 passed`。

## 2026-07-30 D3 来源独立数据故障围栏导出

本轮没有新增运行级 P0。D3 A1 来源独立生成首次完成 60/100 个 episode 后，在
`center_failure` 的 D4 学习制品阶段失败关闭。故障建议已经携带投影拒绝和正式执行
围栏，但 main-owned 批量导出器仍尝试把它作为 D4 可用教师目标。

导出器现把带投影或发布拒绝的 D4 规则建议标为目标不可用，并在 episode 索引中记录
可用数、不可用数和原因分布。该修复没有改变 D4 投影器、故障状态机或权限，只阻止
无效故障建议进入教师标签。`center_failure`、`secondary_failure` 和既有学习导出
专项共 `7 passed`。

批量生成器另增加版本化组件清单。默认仍导出全部学习制品；D3 来源独立专项可只选择
`d3`，清单写入生成计划、逐 episode 索引和批次摘要，恢复时组件变化会失败关闭。该
路径已用三 seed 完成 D3-only 冒烟，不依赖降低 20 GiB 空间门。

当前 P1：

1. 首次 60 项只作为失败诊断，不得与修复后的数据拼接。
2. 必须从包含修复和 D3-only 合同的 clean commit 重新生成 100/100，并由 main 核对真值隔离、
   seed 隔离、有限状态和制品摘要。
3. D3 只读来源独立评价器与机器门需先冻结，再打开新数据。D6 需独立重算评价结果。
4. 以上闭合前，A1 正式 holdout、assist、分配、计划发布、控制和物理权限继续关闭。

## 2026-07-30 D4 v7 来源独立转移泛化评价

本轮没有新增运行级 P0。v7 修复了 v6 的节点动作越权结构问题，但没有形成来源独立的
正确转移能力。候选已失败关闭，确定性 R0 继续作为唯一允许路径。

1. **动作边界已经收紧。** v7 删除学习节点动作头，完整
   `RegionResourceAction` 继承同帧 R0。学习模型只决定帧激活、一条有向边和资源数；
   结果继续通过确定性投影和干预不变量。
2. **开发门曾产生有限正动作。** 固定 M16N24 VALIDATION 的原始激活和 transfer
   change 均为 6，精确正动作为 `2/9`，负类 exact R0 为 `9/11`。该划分参与过
   checkpoint 选择，只能说明结构可形成动作。
3. **独立来源已隔离。** main 从 commit
   `4a83a373f4eb4e29704bb3cf9f62e3d54eee3aec` 生成 seed `5216-5279` 的
   64 个 M16N24、8 区域 episode，共 128 帧和 64 种新布局。训练、正式 holdout、
   既有评价、pilot 与本批 seed 两两无交集。
4. **独立正动作全部未命中。** train/validation/test 的规则正类为 `24/9/9`，
   精确正动作均为 0。validation/test 原始激活和 transfer change 均为 0。
5. **负类出现错误转移。** train 的 10 次原始激活只有 3 次形成实际转移变化，三次
   均为错误边和虚假转移。负类 exact R0 为 `63/66`、`11/11`、`9/9`，合计
   `83/86`。
6. **确定性安全壳没有退化。** 错误方向、错误数量、投影拒绝、不变量失败和原始 R0
   完整动作元组偏差均为 0。投影后 3 帧动作元组变化来自错误转移触发的确定性配额
   联动，不属于节点头越权。
7. **D6 完成低层独立重算。** D6 不调用 D4 高层评价器，从冻结模型、同快照 R0、
   残差解码、投影和不变量重建 128 条记录。D4/D6 JSONL 逐字节一致，SHA-256 为
   `7785ded96360869edfb694c425321fa3323450cf1624607b53edf5d3eca6a5cd`。
8. **权限保持关闭。** 模型拟合、选模、调门、置信校准、注册、准入、正式 holdout
   和既有评价 payload 读取均为 0。v7 保持未注册、准入关闭和规则回退；D3、D7、
   降级、接管、联盟、控制和物理权限全部为 false。

当前 P1：

1. v7 的来源独立规则正动作命中为 `0/42`，validation/test 没有任何转移变化，不能
   进入置信校准。
2. train 存在 3 次错误边和虚假转移。后续候选必须先将独立负类虚假转移归零，再讨论
   运行收益。
3. 当前网络对区域布局变化缺少正类泛化。下一候选应重新审视训练来源、边表示和布局
   多样性，不能继续在 v7 或已读 seed `5216-5279` 上原地调阈值。
4. 只有新版本在全新未见 validation/test 上取得非零且充分的精确正动作，并通过 D6
   独立审计，才可另行设计置信校准。正式 holdout、运行预检、D3/D7 和物理评价继续
   后置。

详细结论见
`research_modules/scalable_3d_simulation/docs/`
`SCALABLE_3D_D4_V7_SOURCE_INDEPENDENT_EVALUATION_20260730_CN.md`。

## 2026-07-30 D4 v6 转移动作来源独立评价

本轮没有新增运行级 P0。main 已关闭“外部正类分母不足”的数据缺口，但 v6 actor 在
新资源规模和新区域布局上没有激活任何 transfer。该结果关闭数据与审计链，不关闭模型
泛化 P1。

1. **候选版本已经隔离。** D4 新建
   `region_resource_a2_edge_transfer_shadow_v6`，显式分离边激活和转移数量，增加有向
   边排序、正边数量及投影后 exact action checkpoint。v4、v5 未修改。内部
   TRAIN/VALIDATION 正动作命中为 `58/60`、`13/15`，负类精确 R0 为 `255/290`、
   `55/60`；内部结果没有证明性能提升。
2. **来源和 seed 已冻结。** main 从 clean commit
   `ed9e086ea8cf5c2138035f710cf4deb3e4a2801e` 生成 M16N24、8 区域、
   seed `4016-4079` 的 64 个 episode 和 126 帧。训练 `0-99`、正式 holdout
   `1000-1019`、既有设计/评价 `3000-3039` 和新设计 pilot `4000-4015` 均与本批
   隔离。
3. **评价分母已补齐。** exporter commit `9bdbe31` 增加默认关闭的 test 正类配额。
   冻结标签集 train/validation/test 的规则正类为 `24/9/9`，负类为 `65/11/8`。
   dataset SHA-256 为 `b1295091...b42c`，split SHA-256 为
   `c767a48b...e332`。test 正类只用于评价，不参与 actor 训练、checkpoint 或阈值。
4. **输入与旧训练零重合。** 冻结 v4 TRAIN+VALIDATION 有 251 个唯一 observable
   key，新数据有 94 个，exact 重合为 0。键只含节点特征、边特征、边索引及张量
   结构，不含 seed、episode、目标标识或真值。
5. **外部正动作全部未命中。** D4 只读评价的 126 帧 raw/projected transfer 均为
   0，规则正动作 exact hit 为 `0/42`，test 为 `0/9`。负类 exact R0 为 `77/84`；
   15 帧节点动作改变但缺少 transfer，触发现有干预不变量。错误方向、错误数量、虚假
   transfer 和投影拒绝均为 0，原因是 actor 没有激活任何边。
6. **指标语义保持分离。** 规则正类召回为 `0/42=0`，可评价。actor-derived 正类
   分母为 0，其比率保持 unavailable，不能用 0 回填。v6 没有置信校准器，未校准
   confidence head 和固定 0.60 门均未用于准入。
7. **D6 独立重算一致。** D6 从冻结 dataset、候选和逐帧记录重算得到 `0/42`、
   `77/84` 和 15 帧不变量失败。D6 重算 JSONL 与 D4 JSONL 的 SHA-256 均为
   `771826bff66d3ba601d0ffecc95f7ab9faf416826898319de7b9f1669020c7c5`。
   source、标签、候选和评价树前后突变均为 0。
8. **权限继续关闭。** v6 保持 unregistered、admission closed 和 rule fallback
   required。assist、分配、降级、接管、联盟、控制、物理、D3、D7、正式 holdout 和
   runtime preflight 权限全部关闭。

当前 P1：

1. 另立 actor 版本，不能原地修改 v6。新 TRAIN 数据需覆盖 M16N24/8 区域安全
   transfer、困难负类、反向边和更多拓扑；同时恢复或提高负类精确 R0。
2. 新 actor 冻结后，先在新的 development 数据上取得非零且充分的 exact 正动作命中，
   再建立只用 TRAIN 拟合的置信校准器。顺序不能倒置。
3. seed `4016-4079` 已进入 D4/D6 评价，不能作为下一候选的独立评价集。正式 holdout
   `1000-1019` 继续不读。
4. 来源独立 actor 门通过前，不启动 D3 successor、运行 ACK、D7 控制、物理窗口或收益
   实验；不通过降低 0.60 门或放宽确定性安全外壳取得正结果。

详细结论见
`research_modules/scalable_3d_simulation/docs/`
`SCALABLE_3D_D4_V6_SOURCE_INDEPENDENT_EVALUATION_20260730_CN.md`。

## 2026-07-29 D4 v5 来源独立外部评价

本轮没有新增运行级 P0。main 已冻结 M16N20 来源独立数据，D4 完成候选只读评价，D6
完成独立重算。结果支持负类拒绝，不支持正类泛化或候选准入。

1. **数据来源已经隔离。** clean commit
   `63987592c216fbdb7e03d77183afc6e9f15748a2` 生成 32 个 episode、63 帧，seed
   为 `3008-3039`。训练 `0-99`、正式 holdout `1000-1019`、设计 pilot
   `3000-3007` 与评价 seed 两两无交集。在线真值、未来结果和 reward 使用均为 0。
2. **可观测输入没有复用旧开发样本。** 冻结 v4 TRAIN+VALIDATION 为 425 帧、
   251 个唯一 observable key；外部数据为 63 帧、41 个唯一键，exact 重合为 0。
   外部 train/validation/test 自身的唯一键也无跨 split 重合。
3. **规则正动作与候选正类已分开。** train/validation/test 为 `43/10/10` 帧，规则
   安全正动作为 `1/1/0`。冻结 actor 没有输出与这两个安全动作相同的可执行签名，
   actor-derived 正类为 `0/0/0`。规则层存在安全动作不能代替候选正类分母。
4. **固定门保持失败关闭。** 63 个 v5 分数均为 0，固定 0.60 门通过 0，负类误接收
   0，规则回退 `63/63`。负类特异度为 1.0；正类召回因分母为 0 保持 unavailable，
   不以 0 回填。
5. **输入在评价期间保持不变。** D4 复核 v4/v5 候选树前后一致，并禁止把输出写入
   source、labeled、v4 或 v5 输入树。D6 对 source、labeled export、labeled dataset、
   v4 和 v5 五棵树执行前后哈希，突变数为 0。
6. **test 与正式 holdout 明确分离。** D4 和 D6 各读取 external test 10 帧；main
   此前也已只读检查同一 10 帧。这是非正式开发 test，不是正式 holdout。seed
   `1000-1019` 的读取数仍为 0。
7. **权限结论不变。** v5 继续 unregistered、admission closed、rule fallback
   required。生产、assist、分配、降级、接管、联盟、控制、D3 和 D7 权限全部关闭。
   正式 holdout、runtime preflight、D3 successor 和 D7 权限测试均未运行。
8. **回归结果。** D4 v5 专项 `18 passed`、全量 `843 passed`；D6 专项
   `5 passed`、全量 `1215 passed`；main scalable 3D 专项 `6 passed`、全量
   `389 passed`。警告仅为既有 Matplotlib `Axes3D` 环境提示。

当前 P1：

1. 当前 v5 的来源独立 actor-derived 正类分母为 0，无法评价正类召回和门限正裕量。
2. 当前 external test 已进入只读评价，不得再用于修改同一候选、0.60 门、split 或
   标签设计。若继续研究，必须另立候选版本和来源独立 development 证据。
3. 新候选只有在独立正类分母充分、D6 盲审通过且 main 单独授权后，才可讨论正式
   holdout。runtime preflight、D3 successor、运行 ACK、物理窗口和收益评价继续后置。

详细结论见
`research_modules/scalable_3d_simulation/docs/`
`SCALABLE_3D_D4_V5_SOURCE_INDEPENDENT_EVALUATION_20260729_CN.md`。

## 2026-07-29 D4 规划专用区域转移与 D6 证据链

本轮没有新增运行级 P0。区域资源不均衡时，D4 已能在不取得任何执行权限的条件下向
D3 提供下一周期规划建议；真实故障代际变化会在建议产生和消费两端失败关闭。该结果只
关闭规则建议合同，不代表 D4 学习模型收益或生产准入。

1. **main 正例已固化。** 20 目标、20 资源、8 区域、seed 29 的 source 计划为
   17 条分配和 3 个未分配目标。D4 v2 建议执行 `region-000 -> region-001`、数量 1，
   来源区域保护 2 个已承诺资源和 1 个备用资源。D3 后继使用新 plan id，版本
   `1 -> 2`，分配 `17 -> 18`，未分配 `3 -> 2`，在线真值使用为 0。
2. **规划权与执行权已分离。** 目标区域可设
   `planning_replan_eligible=true`，但 execution、assignment、coalition、takeover 和
   control authority 全部为 false。建议只能改变 D3 下一周期候选约束，不能直接执行
   分配、联盟、接管或导引。
3. **故障代际负例已固化。** 中心在 2.0 秒失效时，main 把真实
   `fault_generation_fenced=true` 写入区域快照。该帧没有 transfer、没有旧建议消费、
   没有区域提示后继。D4 正式故障状态机和所有安全门未放宽。
4. **D3 因果合同已补齐。** D3 使用 source、同输入未发布 R0 和 treatment 比较
   `execution_signature()`、绑定集合、分配数及未分配集合。treatment 相对 source 和
   R0 均存在真实绑定或目标覆盖变化；机械升版、续租和 metadata 刷新不算干预。
5. **D6 已接入实际总线。** D6 v11 输出合同链、真实绑定干预、同键 R0、描述性非退化、
   模型收益和故障围栏六类独立状态。seed 29 为 `contract_chain_verified`，描述性
   assignment/unassigned 非退化；故障负例为 `fault_generation_fence_verified`。
   两项安全违规均为 0。
6. **权限和模型结论不变。** 本轮建议来源为规则策略。独立同键 R0 不可用，D4 v4
   未注册，因此 `model_benefit_available=false`。assist、分配、降级、联盟、接管、
   控制和物理权限继续关闭。
7. **回归结果。** scalable world/module stack 为 `100 passed`，D3 为
   `618 passed, 1 skipped`，D4 为 `794 passed`，D6 为 `1202 passed`。skip 是可选
   OR-Tools；warning 是既有 Matplotlib 三维后端提示。

当前 P1：

1. 生成 clean、truth-free、内容寻址的 D4 v4 数据和候选，完成正负置信校准、不可变
   review 与注册；注册前不得进入运行加载器。
2. 保存独立同键规则 R0 episode，并连接 advisory、consumption、D3 successor、运行
   ACK、D7 控制及确认后物理窗口。
3. 在独立多 seed 配对场景中验证非退化和收益。当前单 seed 规则正例不能替代模型评估。
4. 继续保持 owner、epoch、lease、reserve、联盟和控制围栏，不通过降低门限或放宽权限
   取得正结果。

## 2026-07-29 D4 readiness v3 隔离双臂最终审计

本轮没有新增运行级 P0。main 已完成 10 组 development control/treatment episode，
D6 已完成紧凑批次和 seed 2007 完整链路的独立审计。软件链能够从 D4 候选评价到 D3
后继、开发 ACK、D7 指令和离线物理窗口，但当前候选没有形成可辨识的可执行动作，
不能声明策略收益或开放生产权限。

1. **10-seed 双臂制品完整。** 20v20、8 区域、seeds 2003-2012 的初态一致和外生
   配置一致均为 10/10。原始推理、运行门、投影和隔离采用覆盖 10/10；D3 严格后继、
   开发 ACK 和摘要级物理窗口只覆盖 seed 2007，即 1/10。其余 9 个 seed 按
   `regional_hint_no_executable_successor` 失败关闭。
2. **非退化与正收益已分开。** 拦截数和最小距离的有界非退化在当前声明口径内
   available/true。该结论只表示候选没有比规则臂更差。10/10 双臂均无拦截，逐 seed
   最小距离完全相同，可辨识候选动作计数为 0；正收益为 unavailable/false。
3. **seed 2007 完整链可重放。** control/treatment 均有 4 条 ACK、77 条 binding 和
   1 次同身份 refresh，treatment 另有 1 次 D4 regional applied。D6 重算确认后继
   首次发布和 refresh 使用相同严格执行签名，authority epoch 与 lease 未丢失。
4. **候选干预不可归因。** source/successor 以及 control/treatment 的资源—目标、
   角色和联盟可执行字段相同。当前 `regional applied` 只证明开发消息被消费，不能把
   后继计划、D7 控制或物理结果归因于学习候选。
5. **身份窗口已按离线评估口径闭合。** seed 2007 的 19 条 D7 非 hold 指令原生有
   18 条物理状态窗口。D2 追踪确认 `GT3D-000004` 在 1.035193 秒经历一次
   confirmed/unmatched 雷达漏检；0.833472 秒和 1.236149 秒的前后 available 锚点
   均唯一指向 `TGT-0004`，无歧义、竞争声明或未承诺身份。D2 保持该帧在线
   unavailable，不复制观测谱系。
6. **D6 已增加有界 coast bridge。** bridge 默认关闭，只在 D4 v3 完整离线审计中
   显式启用。它要求 D2 v2、同航迹/同真值双锚、confirmed/unmatched、reason 精确为
   `track_not_assigned_in_frame`、持续 committed、锚点谱系完整、无竞争声明且间隔
   不超过 0.9 秒。任一条件不满足继续 unavailable。完整链按原生 18 加桥接 1 得到
   有效 19/19；通用 runtime replay 和冻结持久结果仍保持原生 18/19。
7. **权限边界不变。** v3 保持 development/shadow-only、admission closed 和
   rule fallback required。开发 ACK 与生产 authority 分离；assist、assignment、
   degradation、takeover、coalition、control、physical 和 model promotion 权限
   全部为 false。
8. **验证结果。** D2 全量为 `305 passed, 1 warning`，D4 全量为
   `769 passed, 1 warning`，D6 全量为 `1196 passed, 1 warning`，scalable 3D 全量为
   `374 passed, 1 warning`。main 复核 coast/runtime/full-chain 专项为
   `78 passed, 1 warning`，跨模块合同为 `8 passed, 1 warning`。warning 来自本机
   Matplotlib 三维投影依赖，不影响合同和二维输出。

当前 P1：

1. D4 重新形成经安全投影后确实改变资源配额、跨区转移、备用比例或侦察优先级的
   可执行候选；无可执行差异时不得把普通重规划或 evaluation refresh 计为采用。
2. 可辨识干预形成后，再运行独立 full episode 双臂，覆盖通信退化、中心失效、
   二级节点部分就绪和负载变化；逐 seed 保留 ACK、D7、物理状态和同键规则臂。
3. compact 10-seed 仍只保存摘要级结果。若要计算逐 seed ACK、D7 和物理链覆盖率，
   main 必须保存对应 full control/treatment episode，不能由摘要补造。
4. 只有未见 seed、完整分母、可辨识采用、同链确认、物理结果、真值隔离、有限状态、
   非退化和外部权限全部通过后，才可讨论 assist 或 authority 准入。

## 2026-07-29 D4 readiness v3 运行兼容性

本节保留单 seed 预检历史，当前状态以顶部“隔离双臂最终审计”为准。

本轮没有新增运行级 P0。D4 readiness v3 已完成干净构建、不可变登记和单随机种子
development preflight。结论限定为 8 区域影子候选的运行兼容性，不代表区域策略收益、
实际采用、降级授权或正式评价准入。

1. **候选身份和运行合同已固定。** v3 从 clean commit
   `4ba2c8a649dab157d55a2dd7817d5a8ded494114` 构建，候选 manifest 内容、模型权重和
   运行置信门 SHA-256 分别为 `7978aec0...ada2`、`ace5df6d...7f52d` 和
   `77972834...6872`。投影合同为最小备用比例 0.1、最小备用资源 1、建议有效期
   1.5 秒；固定 OOD、置信度、不一致封顶和连续动作容差为
   0.05/0.60/0.59/0.10。重复 clean build 的 8 个文件逐字节一致。
2. **20v20 和 200v200 单 seed 正例通过。** main 从 clean commit
   `83b8869b49c4ac26b6a5b6fb336dfe9af6960226` 加载固定 registry。20v20/8 区域
   seed 2001 和 200v200/8 区域 seed 2002 各产生 3 帧，分布内比例均为 1.0；
   原始推理、运行门应用、动作一致和候选许可均为 3/3，规则回退为 0。在线真值、
   运行门真值、非有限状态、上下文不匹配、权限分歧和正式 D4 决策改动均为 0。
3. **5v5 负例按适用域拒绝。** 5v5/2 区域 seed 2000 的 3 帧均未进入模型推理。
   `candidate_region_count_out_of_scope` 与边 `distance_log`、`transfer_time_log`
   分布外同时触发。该结果证明 8 区域候选对 2 区域输入失败关闭，不构成 8 区域
   正例失败；若后续需要 2 区域学习路径，应另建候选或显式适配器。
4. **权限边界未变化。** `paired_development_rollout_allowed=true` 只表示可以开始
   受控开发配对。registry 内 `runtime_preflight_completed=false` 保持不变；
   assist、assignment、takeover、coalition、control、physical 和 formal evaluation
   权限全部为 false。
5. **回归与证据。** D4 builder 阶段全量为 `750 passed`，登记后 D4 owner 全量为
   `754 passed`；main 的运行兼容性专项为 `8 passed`。三组 preflight 的机器验收通过，
   中文报告和 JSON 摘要见
   `research_modules/scalable_3d_simulation/docs/SCALABLE_3D_D4_READINESS_V3_PREFLIGHT_20260729_CN.md`。

仍开放的 P1：

1. 用多个非正式 development seed 扩展 20v20 和 200v200，覆盖名义、通信退化、
   中心失效、二级节点部分就绪及负载变化，统计运行门通过率、规则回退和时延分布。
2. 在冻结输入上运行 v3 与唯一同键规则基线，形成可辨识区域干预、D3 严格后继计划、
   runtime/owner/coalition ACK、确认后物理窗口和 D6 成对非退化证据。
3. 只有模型来源、未见 seed、实际采用、物理结果、非退化、真值隔离、有限状态和外部
   权限全部通过后，才准备正式 holdout。当前不得改写 registry 或开放运行权限。

## 2026-07-28 学习干预诊断与运行准备度

本轮没有新增运行级 P0。D3、D4、D5 已补齐学习候选进入正式运行前的三类前置检查，
D6 在冻结种子审计之外增加了第一个可信模型来源适配器。G1、A1、A2、A3、C1、F1
仍未取得运行授权，正式学习 episode 仍为 0。

1. **D3 已能量化离散分配边界。** 新增 A1 冻结帧动作裕量校准，复用原规则代价、
   有界残差修正和 Hungarian/需求槽 Hungarian 求解，计算候选边越过规则代价间隔所需的
   `alpha`，并重新核验最终 binding、计划版本和输入摘要。正式 20-seed 结论保持为
   20/20 有效代价矩阵变化、0/20 最终 binding 变化。三资源、两目标开发夹具在
   `alpha=0.25` 出现 3 条 binding 差异，只证明诊断器能找到离散边界，不构成正式 A1
   采用或收益证据。新增公共 strict loader 对 A1 隔离批次的七文件布局、校验和、
   20-seed/帧范围、候选和选择计数、版本连续性及 truth 字段进行重算。loader 固定返回
   未发布、无 ACK、无物理窗口、无 R0、无生产权限。
2. **D4 已生成当前谱系 development/shadow 实物。** 历史候选在 20 个校准 seed、
   420 个样本上得到 76 个安全非零输出，但谱系与当前实现不一致。新候选从独立 clean
   checkout `b0d498d9...` 构建并通过 `review-only`，只读取 train，模型选择只读取
   validation；test、历史 calibration 和保留 seed 读取数固定为 0。候选 manifest 文件
   SHA-256 为 `7cc10ad7...de64`，权重为 `fd1b9c4c...0047`。固定门限开发诊断得到
   train 168/180、validation 54/60 个安全非零实际模型动作，其余样本与基线相同，
   资源不可行、门控回退、身份错配和非有限输出均为 0。全部运行权限仍为 false。
3. **D5 已建立训练语料结构门。** 行为克隆除逆平方根意图权重和逐动作指标外，现按动作、
   相机角色、场景、seed 和 episode 统计独立覆盖。缺 `hold`、少数动作、侦察相机或出现
   split 污染、重复 episode、非有限特征和 truth 字段时拒绝训练。补采计划只列出所需新
   episode 和新训练 seed；复制、过采样和重加权不能补足覆盖。旧 v1 缓存可读但不可继续
   训练。
4. **D6 已接入 G1 模型来源可信适配器。** readiness v2 继续拒绝 manifest 自报 facts 和
   通用自签 gate 文件。新适配器只接受固定 D5 G1 v5 的 13 项原始制品，重跑 external
   audit v2 和 post-assembly audit v2，并重核模型身份、实现谱系、固定布局、文件摘要和
   六项 false 权限。对 `/tmp/MSM-d5-g1-formal-evidence-8d5e02e-20260727` 的只读复核得到
   `formal=true`、`component_ids=[d5_graph]`、`audit_passed=true`。该结果只关闭 G1
   `model_source` 门，不产生模型晋级或运行权限。
5. **磁盘启动保护线当前满足。** 2026-07-28 实测文件系统可用空间约 32 GiB，高于固定
   20 GiB 保护线。该结果只关闭当前时点的低磁盘启动阻断，不证明完整 900-cell 输出容量
   充足，也不改变模型、权限或证据结论。正式未见 seed、确认链和非退化门尚未闭合，
   因此没有启动 900-cell 或完整多 seed 写盘，也未降低保护线。
6. **共享工作区回归通过。** 模块 owner 全量结果为 D3
   `593 passed, 1 skipped`、D4 `697 passed, 1 warning`、D5
   `755 passed, 2 warnings`、D6 `1138 passed, 1 warning`。main 复跑 D3/D5/D6
   本轮专项分别为 46、38、32 项通过，D4 全量为 697 项通过，可扩展三维为
   `352 passed, 1 warning`，跨模块合同为 `8 passed, 1 warning`。skip 为可选
   OR-Tools；warning 为既有 Matplotlib `Axes3D` 和显卡管理接口提示。

仍开放的 P1：

1. D3 需在与调参隔离的冻结 20-seed 输入上形成可辨识 binding 变化，并补齐计划发布、
   运行确认、D7 命令谱系、物理窗口和同键 R0 非退化。strict loader 只关闭离线制品
   完整性，不替代这些运行证据。
2. D4 当前谱系候选已经生成并绑定 clean commit、manifest、权重、数据和 split。仍需在
   至少 20 个严格未见 seed 上形成非零实际模型干预、D3 严格后继计划、
   runtime/owner/coalition ACK、确认后物理窗口、独立同键 R0 和 D6 成对非退化审计。
3. D5 需按补采清单形成非合成 `hold`、少数动作和侦察相机示范，并在冻结谱系及至少
   20 个未见非合成 seed 上完成运行确认和成对非退化。
4. D6 对 G1 仍缺可辨识采用、运行 ACK、物理窗口、同键 R0、成对非退化、truth-use、
   finite-state 和外部权限八门。A1、A2、A3 及组合变体还缺各自模型来源适配器。
5. main 需将临时目录中的正式 G1 原始制品归档到持久只读位置，并在每次正式分片前重新
   核验 20 GiB 保护线、预计输出容量和权限门。当前约 32 GiB 可用空间不构成自动启动
   900-cell 或完整多 seed 的授权。

## 2026-07-27 A3 观测节拍闭环

本节更新并优先于下方 A3 动作/观测节拍缺口。当前没有新增 P0。零检测帧语义、运行时
路由、版本匹配、观测触发和 episode 证据尾窗已实现；正式模型准入和未见 seed 非退化
仍为 P1。

1. **零检测不再等同于没有观测。** D5 新增兼容 v1 的 observation-frame v2。
   `processed_zero_detections` 表示相机已成像且检测器返回空集。目标已分配时只允许
   `reacquire` 和 coverage=false；不生成 tracklet、binding 或身份，不计为锁定。
2. **main 已接入真实事件链。** 每台相机生成 truth-free 帧事件，仅零检测帧使用
   `sensor.camera_empty_frame` 和独立随机流。事件携带双时间戳及计划、联盟、通信版本。
   A3/R0 选择量测时刻前最近的合法命令，并拒绝旧版本、错误资源和超窗事件。
3. **命令节拍已受观测约束。** 首次具备计划和航迹时允许启动，后续命令由已处理视觉帧
   触发。episode 末段 0.25 秒停止发新命令并继续收证据，避免制造无后续观测的尾部窗口。
4. **开发覆盖率明显改善。** seed 1000-1019、默认 1% 通信丢包下为 492 条候选、
   488 条可配对、4 条缺失，覆盖率 99.19%；329 条零检测帧为 `reacquire`，159 条原视觉
   帧为 `locked`，合同拒绝为 0。零丢包/零抖动控制为 500/500。剩余 4 条随通信丢包
   消失，不能通过放宽身份或版本门处理。
5. **证据边界未变化。** 旧冻结 536/152/384 制品及 SHA-256 保持不变。新结果来自
   dirty worktree 和开发 seed，未持久化完整配对清单，`formal_evidence=false`，
   `seeds_verified_unseen=false`，所有学习、相机、分配、降级和控制权限为 false。
6. **回归结果。** D5 A3 专项 `84 passed`，D5 全量 `739 passed, 2 warnings`，
   可扩展三维全量 `352 passed, 1 warning`。报告位于
   `research_modules/scalable_3d_simulation/docs/SCALABLE_3D_A3_OBSERVATION_CADENCE_DEVELOPMENT_20260727_CN.md`。

仍开放的 P1：

1. 从 clean commit 持久化完整候选/R0 记录，使用与训练和调参严格隔离的未见 seed。
2. 把通信丢包率、抖动和带宽作为显式实验因素，报告可用性，而不是把丢包样本改写为
   视觉或身份成功。
3. 使用实际获准主动视觉模型完成同键物理结果和 D6 成对非退化审计。开发夹具、
   零丢包控制和软件合同通过均不能授予运行权限。

## 2026-07-27 A2/A3 独立 R0 配对开发审计

本节更新并优先于下方 2026-07-26 A2/A3 记录。当前没有新增 P0。A2、A3 已从“没有
唯一同键 R0”推进到“独立配对软件链可运行”，但正式未见 seed、实际模型和成对非退化
仍未形成，全部模型及运行权限继续失败关闭。

1. **main 独立运行边界已实现。** 候选组与 R0 使用相同外部配置摘要，分别创建世界、
   总线、模块栈、episode 标识和事件日志。相同 episode、重复事件日志、外部配置不一致
   或同键下存在多个 R0 时，配对装配器拒绝输入。
2. **A2 归因口径已修正。** seed 1000-1019 共 20 组进入 D6。受控策略没有产生资源
   变化、保持状态或跨区转移，因此可识别区域干预、实际安全采用、物理执行窗口和可审计
   同键 R0 均为 0。原先计入的 18 次是并行发生的 D3 常规重规划，不具备 A2 因果绑定。
3. **A2 拒绝语义已修正。** main 为 20 条无操作候选保留
   `identifiable_regional_intervention_missing` 记录。记录不得携带后继计划、运行确认、
   权属确认、联盟提交对象或物理窗口，不刷新计划身份和权限；D6 报
   `a2_actual_adoption_absent`。
4. **A2 真实开发适配器链已接通。** D4 受约束适配器在首次选择和正式投影时使用同一
   `formal_decision`。5 对 5、seed 1、3.0 秒探针形成一个安全 `request_replan`、D3
   严格后继计划、owner ACK、安全采用和物理窗口，在线真值使用为 0。适配器仍为
   development-only；标准 advisor 限制为 shadow，正式收益装配器按
   `development_intervention_benefit_forbidden` 拒绝输入。
5. **A3 完整分母已冻结。** 536 条候选均有严格处置记录，其中 152 条可配对，384 条为
   `candidate_physical_window_missing`，覆盖率为 28.36%，单 seed 范围为 23.08% 至
   33.33%。D6 可报告原因分布；存在不可配对记录时，完整 A3 实际采用、物理窗口、
   同键 R0 和收益计数保持 unavailable，批次可审计 seed 为 0。
6. **A3 阶段原因已在开发探针中拆分。** main 为 536/536 条候选形成候选阶段证据。
   同配置 20-seed 不落盘复跑中，344 条不可配对记录同时具有“匿名观测缺失”和“物理窗口
   确认缺失”，另 40 条因观测清单未闭合而保持细因未解析；物理窗口细因完整率为
   344/384。ACK、确认、命令过期、时序错配和相机反馈缺失均为 0。细分原因允许一条记录
   携带多个标签，不能相加作为候选分母。
   该结果来自未提交工作树，`formal_evidence=false`，未替换原冻结批次。
7. **开发数量与未见证据已经分离。** 当前
   `minimum_seed_count_met=true`，但 `seeds_verified_unseen=false`，所以
   `minimum_unseen_seed_target_met=false`。开发配对批次已拒绝调用方直接把
   `seeds_verified_unseen` 设为 true；只有冻结 seed 注册表、模型训练谱系和正式执行计划
   三者一致时才能形成未见性证据。当前 seed 1000-1019 仍不能按本开发批次计为正式未见集合。
8. **权限边界未变化。** 两批均使用受控测试策略夹具。D6
   `d6_non_degradation_available=false`、`positive_benefit_claimed=false`、
   `model_authorization_allowed=false`，所有运行权限为 false。
9. **回归结果。** 配对编排专项 `6 passed`，D6 严格采用审计 `51 passed`，D3 全量
   `551 passed, 1 skipped`，D4 全量 `674 passed, 1 warning`，D5 全量
   `726 passed, 2 warnings`，D6 全量 `1101 passed, 1 warning`，可扩展三维全量
   `346 passed, 1 warning`，main 模块栈专项 `76 passed`，跨模块合同
   `8 passed, 1 warning`。开发报告位于
   `research_modules/scalable_3d_simulation/docs/SCALABLE_3D_A2_A3_INDEPENDENT_R0_PAIRING_DEVELOPMENT_20260727_CN.md`。

仍开放的 P1：

1. A2 的 development-only 适配器已证明正向运行桥可达。下一步必须使用实际可准入的
   非零学习策略，在至少 20 个严格未见 seed 上完成独立 R0 和成对非退化审计。开发
   适配器不得作为模型收益、准入或运行权限证据；常规 D3 重规划也不得计为 A2 采纳。
2. A3 阶段原因已拆分；当前 P1 收敛为调整动作采样与视觉观测节拍，提高命令窗口和匿名
   观测帧的有效对应率，并从 clean commit 冻结新的完整批次。身份、时间、友方冲突和
   权限门不放宽。
3. A2/A3 仍需实际获准模型、与训练及调参严格隔离的未见 seed、同键规则基线、物理结果
   和 D6 成对非退化审计。完成前不得启动正式 assist 或任何运行权限。

## 2026-07-26 A2/A3 运行证据桥

本节优先于下方“A2/A3 assembler 或实际采用尚未形成”的历史记录。当前没有新增 P0。
A2 和 A3 的软件正向采用链已经可达；实际学习模型仍未授权，正式学习 episode 仍为 0，
相对 R0 的收益仍不可用。

1. **D3 权属绑定已闭合。** 已应用区域提示只能继承一组统一 owner、authority epoch
   和 lease；跨区域 owner、epoch 或 lease 不一致时整份提示失败关闭。区域提示未应用时
   不会获得该权属元数据。
2. **D4 收据复用语义已闭合。** owner ACK 的不可变绑定摘要不再包含后续评估时刻。
   同一收据可以在更晚的物理窗口中复用；时间回退、租约到期、不同目的节点、消息标识、
   计划版本、epoch、分区代次或载荷摘要仍拒绝。
3. **A2 main 运行桥已形成正向物理窗口。** 5 对 5、seed 1、3.0 秒的受控有限策略
   用例产生计划版本 2、1 次 owner ACK、3 个当前计划非 hold 绑定、1 个状态变化物理
   窗口和 1 条安全采用证据，在线真值使用为 0。旧消费记录、旧计划命令和游离绑定均有
   回归阻断。
4. **A3 异步命令/观测桥已形成正向物理窗口。** 每个相机维护待定命令窗口，观测按
   measurement timestamp 匹配已执行且仍有效的最近命令。受控探针得到 40 条运行确认、
   21 帧匿名观测和 21 个物理观测窗口。
5. **随机日程污染已关闭。** 新增严格 D4 证据报文使用独立、确定性的通信随机流，仍
   执行丢包和抖动模型，但不改变共享传感器随机序列。delayed-noisy 20v20 seed 1009
   的结束缓冲恢复为 20 条重放、0 条新鲜量测。
6. **回归已通过。** D3 `546 passed, 1 skipped`、D4 `637 passed`、D5
   `682 passed`、D6 `1071 passed`、scalable `338 passed`、跨模块合同
   `8 passed`。可选 OR-Tools 未安装；Matplotlib 三维投影和显卡管理接口警告不影响
   本轮非图形结论。

仍开放的 P1：

1. A2 需要实际获准模型、唯一同键 R0、至少 20 个未见 seed 和成对非退化审计。当前
   `safe_adoption_available=true` 只证明运行桥可达，
   `a2_benefit_available=false`。
2. A3 需要实际获准主动视觉模型、同键 R0 物理观测窗口和多 seed 非退化。当前候选
   均为 `same_key_r0_window_missing`。
3. A1 仍需可辨识的离散绑定变化、物理结果和同键 R0。G1 仍需用户批准的只读影子
   scope 与现实相机泛化证据。

## 2026-07-27 G1 影子实验授权合同

本节记录 main-owned 运行授权层的当前状态，优先于下方“授权合同尚未定义”的历史判断。
当前无新增 P0。D5 v5 的证据资格已经可以进入受控影子评分，但没有获批授权实例、正式
G1 episode、在线辅助权限或控制权限。

1. **人工授权合同已实现。** 待审批请求固定绑定干净 Git 提交、D5 v5 manifest/文件树/
   权重 SHA-256、场景、规模、seed、时长、设备、有效期和撤销表。请求本身不授予权限。
   批准必须显式给出请求 SHA-256、批准人、理由和固定确认短语
   `APPROVE G1 SHADOW SCORING ONLY`。
2. **授权范围保持最小。** 独立权限图只允许
   `g1_shadow_edge_scoring_granted=true`。模型影响在线关联、模型晋级、中心
   `global_track_id` 权限、默认路径、分配、故障接管、主动视觉命令和控制权限均必须为
   false。D5 v5 内既有六项运行权限继续全部为 false，不因外部影子授权而改写。
3. **确定性链仍是唯一权威。** D5 先用几何规则完成候选图、聚类和中心绑定；影子模型随后
   只对既有匿名候选边计算概率。运行栈保持 applied edge model 为空，影子结果单独发布，
   固定 `model_output_applied=false`，不进入 D3、D4、D7 或控制命令。
4. **执行计划与运行时均失败关闭。** 带授权 G1 计划使用执行计划 schema v2，且只允许
   G1-only scope。`init-scope` 校验显式授权文件 SHA-256、来源提交、模型哈希、设备和
   scope；`run-shard` 在启动、恢复和每个新 cell 前重新检查干净来源、授权、撤销表、
   有效期和作用域。缺文件、摘要错误、超期、撤销、越界或模型变化均停止执行。
5. **旧路径保持兼容。** 不含授权字段的 v1 R0/开发分片计划继续按原合同加载。G1 授权
   不能用于 C1/F1，也不能把规则回退结果记为 G1。授权管理命令只负责准备、人工批准、
   检查和撤销，控制文件必须位于仓库外。
6. **软件回归已通过。** 授权专项覆盖摘要篡改、确认短语、权限越界、scope、缺文件、
   过期、撤销和命令行入口；可扩展三维模块全量为 `331 passed`，跨模块合同为
   `8 passed`。既有 Matplotlib 三维投影环境警告未影响测试结论。

该项关闭“缺少独立人工批准实验授权合同”的代码级 P1。仍开放的 P1 是实际执行与现实证据：
本次改动形成干净提交后，main 只能先生成一个最小、短期、G1-only 的待审批请求，并等待
用户明确批准；批准前正式 G1 episode 保持 0。真实相机泛化、中心身份绑定正确率和物理
闭环仍为 unavailable，不能由合成影子概率替代。

## 2026-07-27 D5/D6 G1 正式证据与权限边界

本节是 D5 图模型准入合同的当前状态，优先于下方 v4/v1 历史记录。当前没有开放的模型
越权 P0。规则路径仍为默认，G1 未获得在线辅助、默认路径、分配、故障接管或控制权限。

1. **同版本双语义缺口已关闭。** D6 external audit 从四权限扩展到六权限后不再沿用
   输出 schema v1，当前输出固定为 `d6.d5-g1-external-audit.v2`。结构未变化的 input
   spec 和 consumer contract 分别保留其 v1，三个版本独立校验。
2. **D5 新装配边界已升版。** 新 admitted bundle 固定为
   `d5.tracklet-model-bundle.v5`，admission report 为
   `d5.tracklet-g1-admission-report.v2`，并嵌入
   `d5.tracklet-g1-authority-contract.v2`。权限合同绑定 D6 审计文件和规范化内容
   SHA-256、证据通过状态、证据资格状态、原因及六项运行权限。
3. **证据资格与运行授权已经分离。** 六项权限为模型晋级、G1 辅助、默认路径变更、
   分配、故障接管和控制。字段必须精确存在、类型为布尔值并全部为 false。证据通过后
   只允许声明 `g1_evidence_eligible_not_authorized`；请求在线 G1 辅助仍失败关闭。
4. **装配后审计升为完整 v2 链。** D6 post-assembly 的 input、output、consumer 和
   profile 均升为 v2，只接受 bundle v5、report v2、authority contract v2 和
   external audit v2。审计交叉校验 held-out、paired-shadow、paired lineage、当前运行
   实现摘要、文件/内容哈希，以及 900 条 lineage 记录和 900 个唯一 `episode_uid`。
5. **旧版和混合版本显式拒绝。** bundle v4、report v1、external audit v1、权限字段
   增删、非布尔值、任一权限为 true 或任一哈希篡改均返回稳定拒绝，不允许兼容白名单
   绕过。旧临时目录中名称带 v2 但内部仍为 schema v1 的制品已标记为 transition
   reject，不能输入新装配链。
6. **真实生产装配正向链已通过。** D5 assembler、lineage 联合专项和模型流水线分别为
   `69/86/20 passed`，D5 全量为 `655 passed, 1 warning`。D6 使用
   `assemble_tracklet_g1_bundle()` 的真实产物完成三项正向/篡改/缺失回归；正向
   post-assembly 结果为 `pass`、blocker 为空，两个负例均失败关闭。D6
   external/post-assembly 专项为 `14/55 passed`，全量为 `1042 passed`。main 另有
   D5/D6 版本、布局、profile、input/consumer、lineage 和六权限直接对照回归。warning
   为既有运行环境提示，不改变测试结论。
7. **当前运行时正式证据链已闭合。** main 在 detached clean commit
   `8d5e02ec989259ce3d39e1e4ad6a90dd0d8d5b54` 上重建补充语料、development bundle、
   seed `1000-1019` held-out、paired-shadow、逐帧 lineage 和 shadow-only registry。
   运行实现摘要为
   `b0708e718b374e5bb52db41c7bd2f994e340a2b009cfd348881a5f9d549baffe`，
   权重仍为 `7fb5db8b...ca71`。held-out 覆盖 20 个未见 seed、900 个 episode 和
   45 个场景规模单元；精确率、召回率、F1 和候选召回率均为 `1.0`，错误合并率为
   `0`，CPU P95 推理时延约 `0.913 ms`。这些结果来自合成匿名候选图。
8. **D6 两级正式审计通过。** external audit v2 状态为 `pass`、blocker 为空，文件/
   内容 SHA-256 为 `cbd6c72b...0cd6` / `334cf662...2d15`。D5 生产装配器随后生成
   manifest SHA-256 为 `b431d066...317d` 的 v5；post-assembly v2 再次得到
   `pass`、blocker 为空，内容 SHA-256 为 `17dda42d...3e1d`。lineage 为 900 条记录、
   900 个唯一 `episode_uid`，SHA-256 为 `83e10529...af1`。
9. **资格没有转化为授权。** v5 strict 和 shadow loader 均通过；
   `require_g1_assist_eligible=True` 的在线辅助请求返回
   `bundle_g1_assist_authority_not_granted`。模型晋级、G1 辅助、默认路径、分配、
   故障接管和控制六项权限全部为 false。当前允许保存和审计该候选，不允许其影响在线
   身份、分配、降级或控制。

本轮关闭了“正式 external audit v2、v5 装配和 post-assembly v2 尚未形成”的 P1。
独立于 D5/D6 制品的人工批准影子实验授权合同已由上节完成，但尚无获批授权实例或 G1
episode。仍开放的 P1 是受控 scope 实际执行和现实证据：真实相机泛化、中心
`global_track_id` 绑定正确率和物理闭环结果继续明确标记为 unavailable。不得通过改写
v5 权限字段或放宽 loader 绕过人工批准。

## 2026-07-26 D3/D4/D5 正式证据与跨视角正向校准

本节记录正式证据和跨视角 R0 校准；D5/D6 当前合同版本以上节为准。当前没有新增 P0。
规则路径仍是默认，G1、A1、A2、A3、C1 和 F1 均未获得在线 assist、默认路径、分配、
故障接管或控制权限。

1. **D3 隔离批量重放合同已正式闭合，A1 未准入。** clean source commit
   `0ed7ca2730f5354be1e6021f9882f1ae26bc42df` 生成 seed `1000-1019`、100 帧
   冻结输入；manifest SHA-256 为
   `e5367d2651955f809b482d78ef3205cbdf44d57eae576c80f64cbd38eac59a44`。
   代码提交 `bdb665eb8e63a17f5f15dbf3fe472af10e5e5b5c` 的 clean evaluator
   输出内容 SHA-256 为
   `c01b13fb5925d99078a3bb9505dc0f9511ec5ab700a432399d3ebe0fcfb55592`。
   80 帧应用学习代价，20 帧分布外回退；20/20 seed 的绑定变化、硬违规和
   `global_track_id` 改写均为 0。当前 development policy 没有越过 Hungarian
   离散边界，不能形成 D7 checkpoint。D3 当前全量为 `521 passed, 1 skipped`。
2. **D4 A2 专用证据装配器已完成，实际候选继续失败关闭。** 新 assembler/strict
   loader 逐文件绑定 development bundle、实现证据、D6 外审、正式 scope、运行链、
   D3 后继计划、联盟确认、物理窗口、唯一同键 R0 和配对非退化结果。成功装配也只允许
   `a2_assist_eligible=true`；默认模型、PPO、故障接管、分配和控制权限固定为 false，
   规则回退固定启用。合成正例只验证软件正向路径。当前实际候选和 D6 审计稳定返回
   `d6_external_audit_fail_closed`，不生成 bundle。D4 当前全量为 `594 passed`。
3. **D5 G1 v4 旧装配完整性证据有效，但不再匹配当前运行实现。** D6 在 clean
   evaluator commit `107cf0756d7b75cd6bf1456d1f1aa940fec6a63c` 完成 post-assembly
   audit：20 个未见 seed、900 个 episode、45 个场景规模单元，三项安全计数为 0，
   审计无 blocker。该证据只确认当时 v4 文件树和谱系完整，不授予模型收益或控制权限。
   D5 异步相机状态修复后实现摘要变化，旧 v4 严格加载返回
   `bundle_implementation_runtime_mismatch`，不得使用兼容白名单绕过。
4. **D5 异步跨相机节点断点已关闭。** 有界快照保留匿名局部航迹、量测时刻、到达
   时刻、像素和外参协方差；默认有效期 1 秒、最多 256 个相机流。OOSM、过期、缺外参、
   重复和容量超限失败关闭。关联图快照现在为每个带来源节点冻结唯一 observation link，
   并精确校验相机命名空间、量测时间和到达时间。漏链、重链、错时间或未知节点均失败
   关闭。D5 全量为 `600 passed, 1 warning`。旧 G1 v4 与当前实现摘要不匹配，仍按预期
   拒绝加载。
5. **main 已完成 clean R0 20-seed 跨视角输入冻结。** detached clean commit
   `64cb865b9933d45b13878019c0e1a21a8fbb2b05` 使用固定 seed `1000-1019`，
   形成 2670 个完整标签图帧、16842 个图节点、5400 条门前候选边、4658 条几何图边
   和 16842 条来源链接。在线真值读取、来源覆盖违规和非有限状态均为 0。dataset
   manifest SHA-256 为
   `5ee284fd3a998c7ec415000cda3def1b1db7b866a762bcc68b6667858730b247`，
   稳定帧 sidecar SHA-256 为
   `f0db1b13913c69ba6b4beb5c07e242135885a3fb16fc9f559f193ac632611a1e`。
   批处理器原子保存逐 seed episode、数据集、sidecar、中文报告和整树 SHA-256。
6. **D6 候选图几何正式评估通过。** 评估状态 `pass`，无 blocker，硬违规为 0。
   4645 个时间合格同目标跨相机对中保留 4642 条真边，另有 16 条假边；微平均精确率
   0.996565、召回率 0.999354、F1 0.997958、假边率 0.003435。20-seed F1 均值
   0.997652，95% bootstrap 区间 `[0.995325, 0.999571]`。评估内容 SHA-256 为
   `dc84c90b90378ba0579311b7b5654018bf3a910ad98f30a59e5dc76eecd422af`。
   `graph.edge_index` 不含 G1 概率、阈值或聚类决定，因此 G1 收益、聚类纯度、中心
   绑定和控制结果明确不可用。D6 全量为 `1022 passed, 1 warning`。

当前最短 P1 路径是：

1. 当前 runtime 的 external audit v2、v5、post-assembly v2 和 main-owned 人工批准
   实验授权合同均已闭合。授权包与 v5 证据包分离，只允许 G1 在既有匿名候选边上参与
   受控影子评分；不得授予 `global_track_id`、分配、降级、主动视觉或控制权限。当前
   尚无获批实例。
2. 用户明确批准后，使用相同 seed、外生配置和随机日程运行 R0/G1。候选图只比较外生输入等价性；G1
   模型收益必须另有带概率、冻结阈值和预测谱系的 prediction sidecar，或使用既有严格
   held-out evaluator。G1 还必须满足实际加载、无 fallback、错误合并不恶化和全部安全
   计数为 0。
3. 在当前近距正向配置之外增加虚警、相似运动、遮挡重现和外参漂移压力组；现有 R0
   正式通过不能替代困难负样本或真实跨视角泛化。
4. D3 需重新训练或冻结能产生离散绑定变化的新 development policy；D4 仍需 20/20
   实际安全采用、D3 后继计划、运行确认、联盟完整确认、物理窗口和唯一同键 R0。

## 2026-07-26 证据装配收尾与当前准入状态

本节是学习辅助准入的当前结论，优先于下方同日早期记录。当前没有开放的模型越权 P0；
G1、A1、A2、A3、C1、F1 仍全部失败关闭，正式学习 episode 仍为 0。软件合同完成不等于
模型性能达标，也不等于取得 assist、默认路径或控制权限。

1. **D3 自我准入 P0 已关闭。** production writer 在写目录或权重前拒绝调用方构造的
   qualified admission；手工正向 v3 manifest 即使字段和占位 SHA 格式正确，也稳定返回
   `bundle_assist_evidence_assembler_unavailable`。现有 development bundle 未修改，
   shadow 仍可用，assist 仍关闭。D3 定向 bundle 测试为 `21 passed`，全量为
   `465 passed, 1 skipped`；跳过项是未安装的可选 OR-Tools。
2. **D4 没有新的 P0。** 现有 v2 writer/loader、运行确认、区域收益、联盟状态机和通信
   因果回执没有自我晋级路径。A2 模块专用 evidence assembler 仍是 P1，必须等待可验证的
   实际采用、物理窗口、同键 R0 和成对非退化证据后实现。D4 全量为 `569 passed`。
3. **D6 外部审计软件已完成。** 新增
   `d6.d5-g1-external-audit.v1`，逐项复核 registry、bundle、held-out、paired-shadow、
   实现来源、鲁棒性和单特征捷径，并输出失败关闭的 D5 consumer contract。D6 已把
   D5 G1 assembler 纳入运行实现摘要；当前实现 SHA-256 为
   `41381db3d11371c049e5569658820ce98abf1a9966ecf86edc0f13f140894b07`。
   D6 全量为 `944 passed, 1 warning`；warning 是既有 Matplotlib `Axes3D` 环境提示。
4. **D5 G1 evidence assembler 软件已完成。** 装配器逐文件校验 manifest、weights、
   held-out、paired-shadow、D6 audit 和带外 SHA-256，使用临时目录原子发布 v4，并由
   公开 strict loader/runtime 复核。正向 fixture 能生成并加载 v4，只证明合同可执行，
   不证明当前模型获准。A3 assembler 仍未实现并保持失败关闭。
5. **当前 D5 图模型仍未准入。** post-assembler 审计文件 SHA-256 为
   `98bf9e0251567a330bf16951acf07da576a6ba3dc47627c3671cd2d491cdc8ed`，
   内容 SHA-256 为
   `40a42af015211d5e721584053e052a893e31aa35b7393195530a5d3d2dc9b90d`。
   实际 assembler 返回 `d6_external_audit_fail_closed`、退出码 2，目标 bundle 目录
   不存在。五项 blocker 为：

   - `implementation_evidence_unavailable`；
   - `implementation_lineage_mismatch`；
   - `robustness_threshold_not_met.cluster_f1`；
   - `robustness_threshold_not_met.edge_f1`；
   - `synthetic_single_feature_shortcut`。

   困难遮挡重现代理的 cluster/edge F1 约为 `0.572845/0.563264`，低于 `0.9`；
   单特征最佳方向曲线下面积约为 `0.997340`，高于允许上限 `0.98`。旧证据缺少 assembler
   来源且 `tracklet_model_bundle.py` 与当前实现不一致。没有放宽门限、增加实现兼容白名单
   或把 fixture 写成模型效果。D5 最终专项为 assembler `14 passed`、模型流水线
   `20 passed`，既有全量为 `571 passed`。

当前开放 P1 分为三组：

1. D3 仍需实际 A1 采用确认、后续物理状态、同键 R0 非退化结果和模块专用 assembler；
   C1/F1 还依赖其他组件独立准入。
2. D4 仍需实际 A2 隔离采用、物理窗口、成对非退化结果和模块专用 assembler。
3. D5 需用当前实现形成没有单特征捷径、困难扰动达到门限的新 G1 模型与完整证据，重新
   通过 D6 外部审计；A3 还需独立 assembler 和实际主动视觉证据。

只有模块预准入形成新的 immutable bundle 后，main 才能启动相应学习 scope。随后 D6
仍须审计逐 cell 实际采用、物理结果和唯一同键 R0 非退化。D3/D4/A3 assembler、实际
合格证据和所有正式学习 scope 目前均未完成。

## 2026-07-26 模块准入复核与 D6 正式证据审计

main 按 D3、D4、D5、D6 owner 边界完成第二轮复核并分四次提交。结论仍是“准入治理
代码增强，实际模型全部未准入”，没有生成或写入任何正式学习 episode。

1. D3 关闭 legacy v2 bundle 仅凭旧 promotion 字段进入 assist 的缺口。v2 shadow
   保持兼容，v2 assist 返回 `bundle_assist_admission_missing`；新 v3 仍须同时满足
   qualified admission 和哈希绑定 promotion。实际 D3 bundle 继续返回
   `bundle_shadow_only`。
2. D4 将 `d4-region-resource-model-bundle-v2` 固定为 development/shadow-only。
   writer 在创建目录前拒绝自声明 qualified/assist，无 manifest 注入策略也不能取得
   assist。实际 A2 状态保持 `pending_runtime_shadow_gate`。
3. D5 首轮设计的 v4 正向报告虽然字段完整，但调用方可以用占位摘要直接构造，不能视为
   可验证证据。主审退回后，D5 采用保守方案：G1/A3 production writer 均拒绝裸 report，
   公开 loader/runtime 拒绝手工 admitted manifest；正向 parser 只由私有 fixture 测试。
   独立 evidence assembler 未完成前，生产路径不能生成或执行 admitted G1/A3 bundle。
4. D6 新增只读 `d6.learning-scope-formal-evidence-audit.v1`。它绑定 execution plan、
   bundle 树、预检设备、merge、shard plan、progress、checkpoint、cell result 和 episode
   文件树，并要求同 `comparison_key` 的唯一 R0、相同父计划、源提交、外生配置和随机
   序列。缺失值不补零。
5. D6 对实际采用采用严格门：D3/D4 必须有正应用计数，D5 图模型必须
   `loaded_edge_model + model_scored + fallback=0 + candidate_edge_count>0`，主动视觉
   必须同时有策略采用和运行确认。C1/F1 任一必要组件未采用即失败关闭。
6. D6 输出只允许声明作用域证据是否完整以及相对 R0 是否非退化，固定
   `model_promotion.allowed=false`。它不能替代模块预准入、不能授予控制权限，也不能用
   shadow/fallback 结果填充学习组。

旧 D3、D4、D5 bundle、manifest 和权重未修改；implementation hash 不设兼容白名单。
main 复跑的 owner 全量结果为 D3 `464 passed, 1 skipped`、D4 `569 passed`、D5
`562 passed`、D6 `930 passed, 1 warning`。D3 跳过项为未安装的可选 OR-Tools，
warning 为既有 Matplotlib `Axes3D` 环境提示。

开放 P1 现在分为两层。第一层是模块预准入证据和新 bundle：D3/D4 仍缺可验证的隔离
采用、物理窗口和 paired non-degradation；D5 仍缺逐文件验证并打包 held-out、paired
shadow 和 D6 外部审计实物的 evidence assembler。第二层是获准后正式 scope：只有新
bundle 通过 `init-scope`，完成逐 cell 实际采用并存在唯一 R0 配对后，D6 才能给出作用域
非退化结论。当前 G1/A1/A2/A3/C1/F1 正式 episode 均为 0。

## 2026-07-26 学习变体正式准入预检

main 对当前实际 D3、D4、D5 图模型和 D5 主动视觉 bundle 做了不写 episode 的解析预检。
修复前，D3、D4 和主动视觉都正确失败关闭，但 D5 图模型只要完整性校验通过就会被
`learning_runtime` 标为 assist，未核对 manifest 中
`g1_assist_eligible=false`。这会使 development-only 模型绕过 G1 使用权限。

D5 owner 已增加严格运行时参数。默认读取继续服务模块内 development/shadow；G1/assist 调用
必须显式要求正向准入，未获准时返回 `bundle_g1_assist_not_eligible`，缺失或自行篡改准入字段
返回 `bundle_admission_invalid`。main 统一 episode 运行时现固定传入严格参数，并增加跨模块
回归。D5 专项和全量为 `19/555 passed`，main 学习运行时与实验矩阵专项为
`12 passed, 1 warning`。

修复后的实际预检中，G1、A1、A2、A3、C1、F1 全部 fail-closed。旧 D5 bundle 还因实现
SHA-256 变化返回 `bundle_implementation_runtime_mismatch`；该拒绝不得通过兼容白名单放宽。
当前无开放的学习模型越权 P0。

main 已关闭“正式分片执行器只支持 R0”的代码级 P1。通用执行计划按变体推导 D3、D4、
D5 图模型和 D5 主动视觉 bundle 需求，并绑定完整文件树、manifest、预检设备、准入诊断
和解析后的模型版本。运行时在调用开始、每个学习单元开始前和发布前复核绑定；缺少或额外
提供 bundle、文件变化、设备变化、规则回退、诊断变化和版本变化均在新建 shard 或发布
单元前失败关闭。旧版不含学习绑定的 R0 计划保持
可读。G1 伪 bundle 开发回归覆盖初始化、拒绝、暂停、恢复和合并；矩阵/分片/学习运行时
定向测试为 `26 passed, 1 warning`，scalable 全量为 `292 passed, 1 warning`。

正式学习变体仍有两项开放 P1：模块模型尚未通过独立 assist 晋级，D6 尚未形成模型实际
采用和规则基线非退化证据。当前实际 G1/A1/A2/A3/C1/F1 预检继续失败关闭，正式学习
episode 仍为 0。R0 不加载模型，现有 `1e5ed8d` source、execution plan 和 135/900
进度未被读取、改写或重新生成。

## 2026-07-25 可扩展三维主线最新状态

**当前优先状态：正式 R0 后验收尾 P0。** clean commit
`2c7b425d076899e1c54a3d87d6ef23a613ba6e3a` 的 20/20 分片和 900/900 R0 单元已经
完成。D6 只确认 895 个 clean-formal 单元；5 个 `delayed_noisy` 单元因最后 D1 后验未被
D2 实际消费而失败。main finalize 使用的简化签名没有状态有效时刻、六维状态和协方差，
却在签名相同时清空 pending generation。五项后验的最大状态、协方差元素和时刻差分别为
`0.415096`、`22.623443` 和 `0.255046 s`，因此不能按合法 no-op 放行。

main 已改为最后 D1 后验必须实际调用 D2，且仅在 D2 成功发布后清空 pending。重复来源
证据由 D2 replay-coast 隔离，不增加命中、不创建新航迹、不刷新原始证据时钟；D7 控制
公式未修改。五个原失败 cell 的开发态复跑全部通过 D6 v10 后验代次合同：
D1 final=D2 consumed、consumption=publication、consumption+merge=generation、skip=0、
pending empty、在线真值使用为 0。scalable、D2、D6 全量分别为 285、305、894 passed。

该 P0 的代码和定向回归已关闭，正式证据尚未关闭。D1 审计、D2 复核、D6 v10 和 main
runtime 已分别提交为 `4b018e4`、`dc5821f`、`8e955f3`、`98d01bf`，未改写分支历史。
修复后的五项运行来自提交前脏工作树，不能与旧提交的 895 项拼接。最终文档同步后还需
以 clean HEAD 生成新 execution plan，再整体重跑 900 项。当前文件系统约余 24 GiB，
现有正式证据约 22 GiB，旧失败现场约 1.2 GiB；在 20 GiB 运行下限下无法并存下一份
约 22 GiB 正式结果。现有证据在获得清理或迁移授权前不得删除。

修复后的正式 source 已冻结为 `1e5ed8d`，execution plan SHA-256 为
`8804ecb4dd0513db55906905f031832711012974fc911546df40e09fb297d373`。main 已完成
shards 0、5、9，共 135/900 单元。新 D6 v10 对原失败的 5v5 seeds 1000/1005 和 20v20
seed 1009 给出 3/3 clean-formal、formal eligible、generation verified，failure reason
为空。D1/D2 最终代次一致，skip 为 0，pending 为空。原失败的 seeds 1008/1018 和其余
765 个单元尚未运行。

新批次约 3.3 GiB后，文件系统可用字节为 `21539827712`，只比 20 GiB 下限
`21474836480` 多约 65 MB。main 已停止启动新单元。当前状态为“3/5 原失败正式闭合、
R0 整体 135/900”；它不能关闭完整 R0 scope，也不能与旧 895 项拼接。

以下 D3 shard-0 记录是本轮 R0 的前序历史，已由 `2c7b425` 批次覆盖：

正式 R0 shard 0 在第 45 个单元
`high_threat_m_to_n/200v200/seed_1000` 暴露新的运行级 P0：D3 滚动规划把旧联盟需求
直接带入当前需求，触发 `coalition demand does not match current demand`。前 44 个完整
单元及最后一个 `.partial` 目录保留为失败证据；绑定 `32b3b40` 的执行计划不得在修复后
继续使用。

D3 owner 已关闭代码层 P0。迟滞评分现在先比较旧、新联盟的资源数量、主资源数量、协同
模式、时间模板和 assignment demand；合同不兼容时旧库存不可保留，使用当前求解候选重建。
同需求成员迟滞、容量、资源唯一性、all-or-none、主备角色、计划版本和过分配拒绝保持不变。
D3 全量为 `464 passed, 1 skipped`；同配置 200v200、seed 1000、2.0 秒开发复验有限状态为
真、在线真值使用为 0，197 个 assignment 使用 197 个唯一资源。正式关闭仍以新 clean
commit 的 shard 0 全部 45 单元通过为准。

D4 模块此前已关闭“联盟提案在网络确认到达前被永久终结”的阻塞。
`CoalitionCommitCoordinator` 在租约有效期内保留 `collecting_acks`，完整必要成员确认后
原子提交；过时或无效确认拒绝且不授权，摘要冲突、分区、租约到期、成员不可执行和显式
终结继续失败关闭。D4 owner 全量回归为 `569 passed`，相关 README、PLAN、GAP 和算法
文档已同步。

main 已把 D4 二级就绪、区域计划广播和联盟确认接入真实 episode 通信队列。2 目标、4 资源、
1 个高空侦察节点的高威胁三成员场景中，中心在 `1.5 s` 失效。二级计划版本 2 在
`2.0 s` 发布；`2.05 s` 时确认数为 0/3，D7 不执行；`2.10 s` 时确认数为 3/3，两个
primary 进入三维中段比例导引，reserve 保持 `assignment_not_current`。区域计划升级后重新
确认，旧版本没有被沿用。在线真值使用和 `global_track_id` 改写均为 0。

main 同步修复了跨任务租约归一化和保留种子因果帧选择。scalable 模块栈为
`66 passed, 1 warning`，scalable 全量为 `272 passed, 1 warning`。warning 是既有
Matplotlib `Axes3D` 环境提示，不影响本轮 JSON、状态机和控制命令验收。

同日 D1、D3-D7 owner 完成未提交补丁和文档收尾复核。D1 修正唯一接受观测的谱系覆盖率
以及真值/虚警混合谱系统计；D3 修正多周期影子评估未实际使用 `cost_weights` 的接线；
D6 将非法 D4 保留种子数字段改为未授权失败关闭；D7 把失效 pair 回收前移到命令计算前，
并在任何状态变更前拒绝同批次重复资源。D4 和 D5 未发现新的模块代码错误，补齐了
development/shadow 与正式准入的文档边界。

最新 owner 回归为 D1 `496 passed`、D3 `464 passed, 1 skipped`、D4 `569 passed`、
D5 `552 passed`、D6 `889 passed, 1 warning`、D7 `220 passed`。D3 跳过项为未安装的
可选 OR-Tools。修正后的 main 模块栈为 `66 passed, 1 warning`。这些结果关闭本轮代码和
文档一致性收尾，不关闭正式多随机种子、200 对 200 实时、AirSim、物理拦截或模型准入。

当前最高优先级仍是 P1 正式证据，而非继续增加在线算法。D6 按实际
`ExperimentMatrixPlan.cells()` 得到 5700 个 formal cell，静态 `post_run` 预检为
expected=`5700`、accepted=`0`、verdict=`fail_closed`。阻塞项包括：

1. R0-G1-A1-A2-A3-C1-F1 正式运行 manifest 和逐 cell 制品尚未生成；
2. D2 `id_switch_count`、五米物理拦截、有限状态和逐 seed 置信区间尚未覆盖完整矩阵；
3. 正式中文报告、曲线、动画和模型清单尚未形成；
4. D3、D4、D5 图模型和 D5 主动视觉模型哈希有效，但只允许 development/shadow，
   尚无 assist 权限；
5. 主工作树含受保护的用户未跟踪资料，不能直接作为 clean formal source；正式运行必须
   使用绑定同一提交的 clean detached worktree。
6. R0 和学习 scope 的分片、断点恢复和确定性合并合同已实现并通过专项测试。完整父清单
   保持 5700 个单元，R0 scope 固定 900 个单元，默认 20 片。任一独立 scope 合并只能
   声明 `formal_scope_complete`，不能声明 5700 单元正式矩阵完成。
7. 学习 scope 基础设施已经可运行，但当前四类实际模型均未获 assist 准入；因此没有
   生成学习 shard、逐单元采用证据或 D6 非退化结论。

正式运行器已增加 20 GiB 默认可用磁盘下限，低于下限时只在完整单元边界暂停，并保留
追加式进度和 checkpoint 以供恢复。main 必须在包含 D3 修复的新 clean commit 上重新
初始化 execution plan，从 shard 0 零开始运行；旧 44 个单元不能拼入新计划。shard 0
全部 45 单元通过后才能启动其余 19 片并由 D6 回灌。学习变体只有在模型权限、逐单元采用
证据和非退化门齐备后才进入 formal 队列。系统实时、目标硬件和 AirSim 代表子场景继续
单独验收。

**P0/P1 状态入口**：本文是 main 层唯一的实现差距与 P0/P1 状态入口，集中维护 owner、当前状态、缺少条件和验收口径。2026-07-14 canonical actual-execution 证据链已完成真实 AirSim seed-1 复验：tuned 2v2 与 M5N2 均生成并通过校验的 `d7-actual-execution-metrics-v2`，不存在 unavailable artifact；`control_commands.csv`、`intercept_summary.json` 和 actual envelope 的物理成功数一致，控制计划 ID 与同一个 canonical D3 history 一致，身份和状态在线真值使用计数均为 0。2026-07-15 main/D6 进一步关闭“只有总耗时、无法定位预算违例阶段”的 P1 可观测性实现缺口；随后复核并关闭 D4 多入口二级接管证据不一致的系统级 P0 边界，以及 D2 continuity 固定 `+0.10` 在高基线下不可达的 P1 准入规则缺口。同日第二次只读审计发现 D4 两个公开 helper 仍把部分缺失证据 `None` 当成“非 False”放行；D4 owner 已改为 exact-true/fail-closed，补齐逐字段缺失负例并完成跨模块回归。D2/D6 随后已用原冻结 replay 生成 ceiling-aware v2 正式联合证据：总体 GNN 候选五项 gate 通过，但只有 `clutter`、`combined` 两个 difficulty 通过，dropout truth alignment 仍为 partial，JPDA 不准入，因此只形成 promotion review，默认 GNN/Hungarian 不变。最新相关回归为 D2 `113`、D4 `280`、D6 `272`、AirSim runtime `157`、integrated point-mass `7`；当前无开放运行级或证据级 P0 blocker。P1 继续包括 D3 长期 churn、M5N2 第二 primary/物理联盟、candidate `3/2/1` 机会合同、ClockSpeed 与顺序控制 RPC 解耦、D5 30/50 m 与 native MOT 准入、真实二级网络时序、D2 候选的跨 difficulty/完整系统评审，以及基于新分阶段证据达到 100 ms 实时预算。P2 仍只在隔离环境评估，不替换默认 NumPy/SciPy/PN/PNG/detect 路径。

**当前状态修订（2026-07-20）**：上段“无开放 P0”只对应此前 AirSim 审计。900-episode
正式生成在第 210 项发现 D5 同流多批次阻塞；以下专项记录为当前状态，优先级高于历史摘要。

**最新 D1 状态（2026-07-24）**：PSD-safe V3 和后续扫描输入同提交矩阵均完成 13 组 pair、
26 个 episode。向量化协方差限制与 `candidate_v2` 扫描输入数据组织均通过 D6 预注册准入；
两项独立 seed 和长时增长子缺口关闭。发布元数据 v1 同提交矩阵已完成但未准入；D1/D2 v2
合同随后在 clean `be399e1` 完成 13 组 pair，并通过 D6 全部预注册门。main 默认已晋级为
`immutable_shared_v2`。固定滞后回放前缀摘要候选随后在 clean `7d2e987` 完成 13 对正式
矩阵，但因短时收益不稳定和核心墙钟退化被 D6 正式拒绝，reference 默认保持不变。系统
实时、逐批审计明细、严格精度、AirSim 和目标硬件证据仍为 P1。以下最新专项记录优先于
“扫描输入或发布元数据仍待治理”的历史表述。

## 2026-07-25 D1 在线发布证据子集快照正式拒绝

当前无新增 P0。main 已实现独立 selector
`d1_publication_evidence_snapshot_implementation`。reference
`full_consistency_snapshot_v1` 仍是默认；candidate
`required_observation_subset_v1` 只读取当前 release cycle 的源观测 ID 和已物化公开航迹
`latest_observation_id`。第一轮 A/B 两臂固定 replay-prefix reference，避免同时改变
回放摘要和 publication 快照范围。

候选对 required ID 去重并按字符串排序，调用 D1 已有精确非破坏性子集接口。未知、非法或
缺失 ID 回退全量快照并记录原因；最终离线 export 始终全量。selector、实现 ID、执行配置和
诊断已贯通 runtime profile、observation governance、module final 和 episode summary。
诊断记录 source/track 引用、required ID、返回记录、lookup miss、fallback 和守恒关系。

3 对 3 开发回归中，reference/candidate 的 D1 fused-track publication payload 完全一致，
候选 fallback、lookup miss 和非法 ID 均为 0，返回记录数低于 reference。未知 ID 负例按预期
回退 full 并记录 `unknown_required_observation_id`；空 required 集合也回退 full。
`test_module_stack.py` 为 `62 passed`，scalable 全量为 `263 passed, 1 warning`。

clean `028ac34`、seed 1151 的 200/200/2 单配对 smoke 已完成。两臂 D1/D2 在线记录 SHA、
consistency digest/count 和原 D1 操作计数一致；candidate 14/14 子集成功，
fallback/lookup miss/非法或空 required 均为 0，返回记录由 `13679` 降至 `4429`，
减少 `67.621902%`。单 pair 的 D1 fusion、module stack、episode 与外部命令计时方向混合，
不形成性能准入。

clean `d0219eb14c529a4fb9bf7d6610a9f32055a09206` 上已完成 13 对/26 个 fresh
episode，0 reused、0 failed。matrix SHA-256 为
`6c808c4df8759fd893c6d37ff9dce4a1efa07f9867fc71aff47a55c5f8517338`。
D6 独立确认 13/13 业务语义、D1/D2 在线记录、consistency digest/count、原 D1 操作
计数、实现身份、在线真值隔离和诊断审计通过。候选 429/429 次子集成功，fallback、
lookup miss、非法或空 required 均为 0；返回记录由 `1602170` 降至 `133917`，削减
`91.641524%`。

D6 正式判定 `reject`，`main_default_promotion_allowed=false`。失败门为：short 更快
`4/10 < 8/10`、short D1 fusion 改善 `-0.147877% < 1%`、bootstrap 上界
`1.374681% > 0%`。reference `full_consistency_snapshot_v1` 继续作为默认；candidate
只保留为显式研究路径，不修改冻结门限和正式证据。

本候选准入流程已审结。系统实时 P1 仍开放，候选最低实时因子
`0.203423 < 1`；AirSim、目标硬件、实机和实飞证据继续独立开放。正式 D6 bundle 位于
`research_modules/d6_evaluation_metrics/outputs/`
`d1_publication_evidence_snapshot_multiseed_20260725_formal_d0219eb_d6/`。

## 2026-07-25 D1 固定滞后回放前缀摘要正式拒绝

当前无新增 P0。D1 owner 已实现默认关闭的
`fixed_lag_checkpoint_prefix_cumulative_summary_v1`。候选通过不可变累计摘要和延迟区间
账本减少完整 checkpoint 前缀的重复扫描；6 秒窗口、状态、协方差、创新、门控、
consistency evidence、双时间戳和原有操作计数不变。中间迟到量测、schema 失配、部分
前缀、无 checkpoint 和禁用一致性刷新均有失败关闭测试。

正式 producer clean commit 为 `7d2e987471b521a1e531bf03a5c99af5096f676a`，matrix
SHA-256 为 `85432d729877eff97e6f3dd517d4baa7a47f44a4fa42e6bfdc7ce85b8d9ec74b`。
short seeds 1151-1160、long seeds 1151-1153 共形成 13 对/26 个 fresh 200/200/2
三维质点 episode，0 reused、0 failed。D6 独立确认 13/13 对业务语义、consistency
records digest/count、原 D1 操作计数、实现身份、诊断守恒和在线真值隔离通过。

| 指标 | short | long | 预注册门限 |
| --- | ---: | ---: | ---: |
| candidate faster | 5/10 | 2/3 | >=8 / >=2 |
| D1 fusion 改善 | 0.959611% | 2.361778% | >=1% / >=1% |
| core wall 改善 | -0.256641% | -1.930083% | >=0.25% / >=0.25% |
| D1 bootstrap 原始变化 95% 上界 | 0.619827% | 不作为失败门 | <=0%（short） |
| 内部物化削减 | 79.497291% | 48.847968% | >=20% |

D6 verdict 为 `reject`，`main_default_promotion_allowed=false`。候选虽然将全矩阵内部物化
减少 `52.150746%`，在线精确 snapshot 仍投影构造 `656481` 条记录，short 和 long 核心
墙钟均未达到冻结门。main 默认继续使用 `per_checkpoint_prefix_rebuild_v1`，候选只保留为
显式研究路径。候选最低实时因子为 `0.197441 < 1`，系统实时 P1 未关闭。正式报告位于
`research_modules/d6_evaluation_metrics/outputs/d1_replay_prefix_summary_multiseed_20260725_formal_7d2e987_d6/`；
main 使用同一 manifest 重复评估后，六个输出的 SHA-256 与正式 bundle 完全一致。

后续若研究按 publication 所需观测标识投影 snapshot，应使用新的实现标识和独立预注册矩阵。
本次冻结矩阵、门限和 `reject` 结论不得改写。本证据仅覆盖三维质点仿真，不覆盖 AirSim、
冻结目标处理器、硬件、实机或实飞。

## 2026-07-25 D1 关联稀疏预筛正式拒绝

当前无新增 P0。D1 owner 已提供默认关闭的
`modality_conservative_quadratic_bound_v1`。候选以保守二次型下界提前排除不可能通过
原马氏门限的关联对；无法认证、奇异或非有限输入继续 fail-open 到精确求解。原门限、
创新残差、双时间戳、协方差、状态机、真值隔离和全局航迹编号均未改变。

main 在 clean commit `9302ccede2ca513c2235370e1a464fc88bc41150` 上完成 10 对 short、
3 对 long，共 13 对/26 个 fresh 200/200/2 三维质点 episode。冻结 matrix SHA-256 为
`a7162d014d1c3c0f207355b24a5d7159bf3486d134ca21876f7469d1e915b71d`。两臂唯一
运行时 treatment 为预筛 selector；0 reused、0 failed。

D6 独立只读评估确认 13/13 对业务语义、有限状态、实现身份、预筛审计、在线真值使用为
0，逐 pair、逐模态 exact gate-pass 完全相等。候选将非雷达精确求解由 `298109` 降至
`39837`，削减 `86.636767%`。资源和下游均值门未出现实质退化。

| 指标 | short | long | 预注册门限 |
| --- | ---: | ---: | ---: |
| candidate faster | 7/10 | 3/3 | >=8 / >=2 |
| D1 fusion 改善 | 0.228437% | 0.713776% | >=1% / >=1% |
| core wall 改善 | 0.091096% | 0.490650% | >=0.25% / >=0.25% |
| D1 bootstrap 原始变化 95% 上界 | 0.443531% | -0.357903% | <=0%（short） |
| 非雷达精确求解削减 | 86.636767% | 合并统计 | >=20% |

五个冻结性能门失败：short 更快数、short/long D1 fusion、short bootstrap 上界和 short
core。D6 verdict 为 `reject`，`main_default_promotion_allowed=false`。main 默认保持
`disabled_v1`；候选仅保留为显式研究和诊断路径，不调整门限、不删除 pair、不覆盖正式
拒绝结论。

仍开放 P1：

1. **系统实时容量。** 候选最低实时因子 `0.206273 < 1`，局部精确求解削减没有关闭
   200 对 200 实时缺口。
2. **候选粒度和耗时归因。** EO 累计 `37571` 次 fail-open，候选还需对每个输入对计算
   保守下界，但现有正式矩阵没有把二者与 D1 其余阶段分别计时，尚不能断定单一瓶颈。
   后续先增加分项画像，再决定采用更粗粒度候选生成还是更低成本的认证边界。
3. **外部证据。** 当前没有 AirSim、冻结目标处理器、硬件、实机、实飞或正式
   RMSE/NEES/NIS 证据。

正式报告位于
`research_modules/d6_evaluation_metrics/outputs/d1_association_sparse_prefilter_multiseed_20260725_formal_9302cce_d6/`。

## 2026-07-25 D1 在线批帧交接正式准入

当前无新增 P0。D1 owner 已将原始在线批次到 `SensorScanFrame` 的两条路径固化为
`convert_then_frame_v1` reference 和 `closed_immutable_batch_to_frame_v1` candidate。
候选先完成整批在线身份检查，再构造封闭不可变快照，最后执行完整只读帧检查；它不删除
真值字段拒绝、时间戳、协方差、重复观测、sensor/batch/模态一致性或最终帧校验。

main 在 clean commit `43feaf600f288a85ce76a76862334256f0d0d352` 上完成 10 对 short、
3 对 long，共 13 对/26 个 fresh 200/200/2 三维质点 episode。冻结 matrix SHA-256 为
`4afbf9ac273763a16aa01cc744fd67b52e437099460b33377a128f986ac5719b`。两臂只改变批帧
实现 selector；独立运行产生的计划编号先验证来源载荷、ACK、D4 内容地址和版本连续性，再按
谱系归一化，分配关系、授权、目标/资源绑定、状态机、计数和安全结果仍严格比较。

D6 独立只读评估确认 13/13 对业务语义、有限状态、在线真值隔离、实现身份和批帧审计通过。
候选 2665/2665 次请求全部使用 closed handoff，reference fallback 为 0，重复量测身份检查
减少率为 `100%`。

| 指标 | short | long | 预注册门限 |
| --- | ---: | ---: | ---: |
| candidate faster | 10/10 | 3/3 | >=8 / >=2 |
| scan input 改善 | 38.289241% | 36.275282% | >=20% |
| core wall 改善 | 4.252745% | 4.916501% | >=2% |
| D2 association 组均值增幅 | 2.113047% | 2.830616% | <=5% |
| RSS 组均值增幅 | -0.061496% | 0.281879% | <=5% |

全部冻结 gate 通过，结论为 `admit`。D1 公共 helper、main 集成配置和 episode CLI 默认均已
晋级为 `closed_immutable_batch_to_frame_v1`；`convert_then_frame_v1` 保留显式回退。
默认状态和完整实现 ID 继续写入 runtime profile、summary、module final 与 observation
governance。D1 全量回归 `443 passed`，scalable 3D 全量回归 `244 passed`，D6 全量回归
`846 passed`。

仍开放 P1：

1. **系统实时容量。** 候选最低实时因子 `0.204490 < 1`。本次只关闭批帧重复检查与默认
   准入缺口，没有关闭 200 对 200 实时 P1。
2. **D2 尾部波动。** `short_seed_1125` 和 `long_seed_1121` 单对 D2 association 增幅分别
   为 `15.778858%/14.408510%`。组均值门通过，但后续长时容量矩阵继续观察尾部。
3. **外部证据。** 本轮不是 AirSim、冻结目标处理器、实机、实飞或正式 RMSE/NEES/NIS
   证据，不能由三维质点准入继承。

正式报告位于
`research_modules/d6_evaluation_metrics/outputs/d1_online_batch_frame_multiseed_20260725_formal_43feaf6_d6/`。
冻结 matrix 和 source episode 不因默认值提升而改写。

## 2026-07-25 D1 不透明来源标识缓存正式拒绝

当前无新增 P0。D1 owner 已增加来源节点、发布 epoch 和航迹标识三段不可变字符串的有界
代际缓存。参考实现 ID 为
`d1.publication.opaque_source_identity.per_publication_build.v1`，候选为
`d1.publication.opaque_source_identity.bounded_generation_lru.v1`。键严格使用
`publisher_node_id + publisher_epoch + track_id`，容量默认 1024、上限 4096；节点或
epoch 改变时失效。候选默认关闭。

D1 冻结微基准使用 200 条航迹、每样本 56 次发布和 7 次交错采样。参考/候选中位耗时为
`0.348622/0.127734 s`，改善 `63.360%`，候选 `7/7` 更快；标识构造
`78,800 -> 200`。main 已接入 selector、容量和 CLI，并将实现身份与缓存诊断写入
runtime profile、summary、module final 和 observation governance。无 source-key 的默认
路径请求数为 0，本次候选只对显式来源键发布面生效。

正式矩阵冻结在
`configs/d1_opaque_source_identity_cache_multiseed_v1.json`，source commit 为
`d8fc76c066f21b077154f7be33c0b43558d237e5`。short seeds `1101-1110`、long
seeds `1101-1103` 均使用 200 个目标、200 个资源和 2 个侦察节点；共完成 13 组 pair、
26 个 fresh arm，0 reused、0 failed。结构歧义 hold 保持关闭，两臂唯一运行时 treatment
为缓存 selector。

D6 独立评估确认 13/13 pair 的业务语义、有限状态、在线真值隔离、实现身份和缓存守恒
通过。候选 13 个 episode 合计将标识构造由 `312,317` 次降至 `2,612` 次，减少率和缓存
命中率均为 `99.163670%`，最大条目数 `202/1024`。

| 指标 | short reference/candidate | short 变化 | long reference/candidate | long 变化 |
| --- | ---: | ---: | ---: | ---: |
| D1 fusion wall | 2.605867/2.359398 s | 改善 9.465972% | 18.573127/17.379809 s | 改善 6.437432% |
| D2 association wall | 0.489031/0.511906 s | 增加 4.677567% | 3.332553/3.519349 s | 增加 5.605213% |
| 核心墙钟 | 9.126686/8.866012 s | 改善 2.845610% | 52.015549/50.597894 s | 改善 2.728043% |
| 实时因子 | 0.241218/0.248269 | 改善 2.934277% | 0.192308/0.197707 | 改善 2.804822% |

long D2 association 增幅超过冻结上限 `5%`，是 19 项门中的唯一失败项。
`long_seed_1101` 单 pair 增加 `19.069868%`，未剔除，门限未调整。D6 判定
`optimization_admitted=false`。main 默认继续使用 `per_publication_build_v1`，候选只保留
为显式实验路径。

仍开放 P1：

1. **系统实时容量。** 候选最低实时因子 `0.193887`，未达到 1；局部缓存收益没有关闭
   200 对 200 实时缺口。
2. **D2 长时稳定性。** 可用新的预注册确认矩阵增加长时 seed 或重复轮次，判断
   `long_seed_1101` 是否属于稳定回归；不得覆盖本次正式拒绝。
3. **默认主线热点。** 默认无来源键 R0 不使用该缓存。下一项应治理上游转换与
   `SensorScanFrame` 构造间重复的在线身份检查，先冻结检查次数和业务语义。
4. **外部环境。** 当前没有 AirSim、冻结目标处理器、RMSE、NEES、NIS 或实飞证据。

正式报告位于
`research_modules/d6_evaluation_metrics/outputs/d1_opaque_source_identity_cache_multiseed_20260725_formal_d8fc76c_d6/`。

## 2026-07-25 D1 结构稀疏数值雅可比正式准入

当前无新增 P0。默认路径画像把 D1 `numerical_jacobian` 定位为可分离热点。D1 owner 已增加
结构稀疏候选：声学、光电、激光雷达和无径向速度雷达只对三个位置列执行原中心
差分；含径向速度雷达仍使用六列。活动列步长和运算顺序、双时间戳、NED、协方差、
fixed-lag/OOSM、门限、量测频率和 `global_track_id` 均未改变。

D1 冻结 480 个混合量测模型、每样本 20 轮并交错运行 9 次。参考/候选中位耗时为
`0.444645/0.319552 s`，改善 `28.13%`，候选 `9/9` 更快；量测函数求值
`124,800 -> 72,000`，减少 `42.31%`。雅可比、归一化创新平方和门控决策摘要完全一致，
D1 全量 `414 passed`。

main 已接入 `dense_output_probe_v1/known_dimension_structural_columns_v1` 选择器。
实现身份和操作数进入 runtime profile、observation governance、module final diagnostics
和 summary。正式矩阵冻结在
`configs/d1_structured_numerical_jacobian_multiseed_v1.json`，并在 clean
`9d1f54f8540fdc4a7a1011121aafac5718290122` 完成 10 组 short 与 3 组 long pair，
共 26 个 fresh arm，0 reused、0 failed。

D6 失败关闭评估确认 13/13 pair 的业务语义、有限状态、在线真值隔离、实现身份、操作数
守恒、性能和内存门全部通过。short/long 的 D1 fusion 改善
`6.084778%/4.676061%`，核心墙钟改善 `1.897370%/1.786530%`，候选分别
`10/10`、`3/3` 更快；量测函数求值减少 `53.846154%`，最大任一 pair RSS 增幅
`0.063858%`。D6 判定 `optimization_admitted=true`，main 默认已晋级为
`known_dimension_structural_columns_v1`；`dense_output_probe_v1` 继续作为显式回退。
D1 独立 `FusionAdapter` 默认不在本次 main 集成准入中改写。

仍开放 P1：

1. **系统实时容量。** 候选最低实时因子为 `0.180726`，未达到 1；局部准入没有关闭
   200 对 200 实时 P1。
2. **尾延迟。** long 的 D1 fusion 最大单次耗时均值未稳定改善，继续保留阶段 P95/max
   治理，不用均值提升覆盖尖峰。
3. **精度与环境。** 当前没有正式 RMSE、NEES、NIS、AirSim、冻结目标处理器或实飞证据。

正式报告位于
`research_modules/d6_evaluation_metrics/outputs/d1_structured_jacobian_multiseed_20260725_formal_9d1f54f_d6/`。

## 2026-07-24 main 在线真值守卫候选正式拒绝

当前无新增 P0。main 在 episode 总线中保留参考实现 `generic_recursive_v1`，并增加默认
关闭的候选 `builtin_specialized_recursive_v2`。候选只为精确内置容器使用专门遍历，
不改变禁止字段、键值递归、循环保护、非有限状态和在线真值隔离规则。实现选择器、身份和
诊断进入 manifest 与 summary。

冻结矩阵 `configs/online_truth_guard_multiseed_v1.json` 的 SHA-256 为
`764574b9897d00101c26c555de2f407e1736c7e6ff50420eebf131e154618dc8`，producer commit
为 `8d8bb6ed7a417705236835f235361f45a021bb2b`。正式运行包含 10 组 2.2 秒 short pair
和 3 组 10 秒 long pair，共 26 个全新 200 对 200 arm；0 reused、0 failed。13/13 pair
业务语义相等，在线真值使用为 0，有限状态、实现身份和消息检查数守恒均通过。

| 指标 | short reference/candidate | short 变化 | long reference/candidate | long 变化 |
| --- | ---: | ---: | ---: | ---: |
| 发布总线及收尾墙钟 | 0.900293/0.696858 s | 改善 22.58% | 3.810588/2.834910 s | 改善 25.63% |
| 核心墙钟 | 9.163492/8.933562 s | 改善 2.50% | 52.362864/54.235533 s | 回退 3.47% |
| D1 fusion | 2.582814/2.580385 s | 下降 0.00% | 18.495864/19.511515 s | 增加 5.29% |
| D2 association | 0.506169/0.497850 s | 下降 1.43% | 3.750915/4.039187 s | 增加 7.34% |

long 核心墙钟未达到至少改善 `0.5%` 的门限，long D1/D2 增幅超过 `5%` 上限。D6 判定
`optimization_admitted=false`、`system_realtime_gap_closed=false`；候选最低实时因子为
`0.165369`。因此默认继续使用 `generic_recursive_v1`，不能通过降低真值审计强度或忽略
下游阶段回退晋级候选。

仍开放 P1：

1. **系统实时容量。** 候选和参考均未达到实时，发布总线局部下降没有关闭全栈实时缺口。
2. **长时稳定性。** long seed 1102 出现核心墙钟、D1 和 D2 同向回退。可用交错顺序更平衡的
   v2 诊断复核热状态或顺序效应，但不得覆盖 v1 正式结论。
3. **下一热点选择。** main 已在同一 clean runtime commit 上对未改动默认路径完成一次
   非准入画像。未插桩 long reference 三 seed 仍以 D1 fusion `18.495864 s` 和 D1 scan
   input `6.612982 s` 为首要核心热点；D1 owner 正在模块内选择一个默认关闭、可分离的
   低风险候选。该候选仍需模块微基准和新的全栈预注册矩阵。
4. **目标环境。** 当前仍是三维质点证据，不包含 AirSim、冻结目标处理器或实飞容量。

正式报告位于
`research_modules/d6_evaluation_metrics/outputs/online_truth_guard_multiseed_20260724_formal_8d8bb6e/`。

## 2026-07-24 D1 常速度模型缓存正式准入

当前无新增 P0。D1 owner 已提供精确 `(dt, process_noise)` 键的有界最近最少使用缓存，
参考实现 ID 为 `d1.fusion.cv_motion_model.per_prediction_build.v1`，候选实现 ID 为
`d1.fusion.cv_motion_model.bounded_exact_lru.v1`。候选容量默认 128、上限 4,096，缓存
矩阵只读；非正或非有限输入回到参考计算。时间戳、NED、协方差、固定滞后重放、门限和
`global_track_id` 均未改变。

D1 模块冻结 benchmark 使用 200 个状态、100 步传播和 7 次交替采样。参考/候选中位耗时
为 `0.220679/0.103950 s`，局部加速约 `2.12x`；模型构造数由 `20,000` 降至 `8`，最终
状态 SHA-256 相同。该结果不构成全栈准入证据。

main 已接入显式 selector、容量校验和 CLI。正式准入后默认已晋级为
`bounded_exact_lru_v1`，参考路径继续可选。selector、
容量、实现 ID 和缓存操作计数写入 runtime profile 哈希、observation governance、
module final diagnostics 和 episode summary。专项回归已覆盖默认、显式选择、清单哈希、
诊断持久化和非法容量；本轮 D1、scalable 3D、D6 全量回归分别为
`395/212/784 passed`。

clean `44223566439a446fc49f2a3fd861d1d51bd676b9` 的 seed 1101、2.2 秒 smoke
两臂均为有限状态且在线真值使用为 0。排除预注册 runtime profile treatment 后，规范在线
载荷、计划谱系、真值状态、离线标签和接近事件一致。参考/候选 D1 fusion 为
`3.278821/3.031855 s`，模型构造为 `32,217/132`。该结果只确认接线和自然工作量。

正式矩阵在冻结 source 上完成 10 组 short 与 3 组 long pair，共 26 个全新 arm，
0 reused、0 failed。13/13 业务语义、有限状态、在线真值隔离、实现身份和缓存审计通过。

| 指标 | short reference/candidate | short 变化 | long reference/candidate | long 变化 |
| --- | ---: | ---: | ---: | ---: |
| D1 fusion wall | 3.289739/3.061518 s | 改善 6.9271% | 23.304548/21.776847 s | 改善 6.6103% |
| 核心墙钟 | 9.900121/9.661069 s | 改善 2.4060% | 57.230178/55.826568 s | 改善 2.4537% |
| D2 association | 0.555747/0.555140 s | 下降 0.1082% | 3.879187/3.772992 s | 下降 2.6729% |
| 最大常驻内存 | 868,449/868,575 KiB | 增加 0.0145% | 1,603,473/1,608,273 KiB | 增加 0.2959% |

候选累计完成 `896,820` 次预测请求、`871,496` 次缓存命中、`3,535` 次未命中和
`3,535` 次模型构造；参考构造 `875,031` 次。构造减少率和命中率均为 `99.5960%`。
所有预注册门通过，D6 判定 `d1_optimization_admitted=true`。

仍开放 P1：

1. **系统实时容量。** 候选最低实时因子 `0.1739499`，未达到 `1.0`，
   `system_realtime_gap_closed=false`。
2. **环境和精度。** 当前无 AirSim、冻结目标处理器、RMSE、NEES、NIS 或严格身份结果。
3. **尾延时。** 累计 D1 与核心墙钟准入通过，但单次 max 仍有噪声和反向变化，不能据此
   宣称最坏周期延时收敛。

正式报告位于
`research_modules/d6_evaluation_metrics/outputs/d1_cv_motion_model_cache_multiseed_20260724_formal_4422356/`。
该准入关闭常速度模型构造热点，不关闭 200 对 200 系统实时 P1。

## 2026-07-24 D1 发布元数据 v1 结论与 v2 准入

当前无新增 P0。历史 v1 矩阵在同一 clean 提交完成 10 组 2.2 秒 short pair 和 3 组
10 秒 long pair，共 26 个 200 对 200 episode。13/13 pair 的业务语义、有限状态、在线
真值隔离和来源合同通过。D1 fusion short/long 分别改善 `16.29%/31.05%`，但 D2
association 分别增加 `53.44%/169.89%`，核心墙钟只改善 `1.65%/1.21%`，未达到
预注册 `5%` 门。D6 正式判定 `d1_optimization_admitted=false`。

根因是 v1 使用自定义 `dict/list` 子类。D2 只能信任精确内置容器，因而对每条
GlobalTrack 的共享子树重新递归审计。D1 已提供 `d1.publication_audit_tree.v2`：
映射以 `frozenset` 为底层、序列以 `tuple` 为底层，并拒绝自定义映射、子类、伪造标记、
循环、重复键、非有限值和不支持叶节点。D2 已接入精确 v2 类型校验、首次内容审计和强引用
身份缓存；200 条航迹、3 个共享根的模块测试得到 3 次合同验证、3 次完整内容审计和
597 次身份复用。

main 在 clean 提交 `be399e138762f5e660f553c8caa812d52ab38c61` 上从头运行 v2
矩阵。10 组 short 和 3 组 long pair 共 26 个 arm 全部完成，旧 episode 复用数为 0。
13/13 pair 的业务语义、有限状态、在线真值隔离、实现身份和 D2 审计通过。D6 只在业务
比较中归一化预注册的 `d2_publication_metadata_audit` treatment 字段，随后在 summary、
final diagnostics、嵌套 governance 和独立 governance 四处单独校验计数。

| 指标 | short reference/candidate | short 变化 | long reference/candidate | long 变化 |
| --- | ---: | ---: | ---: | ---: |
| D1 fusion wall | 3.740630/3.234146 s | 改善 13.5447% | 31.798717/23.264824 s | 改善 26.8298% |
| D2 association wall | 0.657417/0.548699 s | 下降 16.1939% | 5.869413/3.774282 s | 下降 35.6213% |
| 核心墙钟 | 10.451244/9.764102 s | 改善 6.5677% | 68.901075/56.318948 s | 改善 18.2438% |
| 最大常驻内存 | 1,008,978/868,146 KiB | 下降 13.8390% | 2,200,844/1,606,185 KiB | 下降 26.7678% |

候选 13 个 episode 合计完成 `702` 次合同验证、`702` 次内容审计、`139,920` 次身份复用，
合同拒绝为 0；参考臂对应执行 `139,920` 次内置等价复用。17 项准入门全部通过，
`d1_optimization_admitted=true`。main 默认晋级为 `immutable_shared_v2`，
`per_track_copy_v1` 保留为显式参考路径。

仍开放 P1：

1. **系统实时容量。** 候选最低实时因子为 `0.1730801`，未达到 `1.0`，
   `system_realtime_gap_closed=false`。
2. **逐批审计。** 当前持久化合同只有 latest 和 totals。评估器能校验批次数与固定审计
   工作量，但不能回放每个 batch 的独立明细。
3. **环境和精度。** 本矩阵不包含 AirSim、目标硬件、RMSE、NEES、NIS 和严格身份精度。

历史 v1 紧凑报告位于
`research_modules/d6_evaluation_metrics/outputs/d1_publication_metadata_multiseed_20260724_formal_a36f519/`。
v2 正式报告位于
`research_modules/d6_evaluation_metrics/outputs/d1_publication_metadata_v2_multiseed_20260724_formal_be399e1/`。

## 2026-07-24 D1 扫描输入正式多 seed 准入

当前无新增 P0。main 从 clean 提交
`d14285e4fdeb2f2e2cd32fad2f6d42e30f9e73a7` 运行同提交
`reference_v1/candidate_v2` 对照。矩阵固定 short seeds `1101-1110`、long seeds
`1101-1103`、200 个目标、200 个资源和 2 个侦察节点，共 13 组 pair、26 个 episode。
所有 arm 返回 0，13/13 pair 的业务语义、有限状态、在线真值隔离和实现身份检查通过。

| 指标 | short reference/candidate | short 改善 | long reference/candidate | long 改善 |
| --- | ---: | ---: | ---: | ---: |
| D1 scan input wall | 1.212452/1.145650 s | 5.360122%，9/10 更快 | 6.687633/6.340680 s | 5.142482%，3/3 更快 |
| D1 scan input P50 | 0.987604/0.967341 ms | 2.043993% | 1.049555/1.018772 ms | 2.929786% |
| D1 scan input P95 | 110.697266/104.645446 ms | 5.466588% | 110.367862/104.310288 ms | 5.487965% |
| 核心墙钟 | 10.316724/10.242776 s | 0.718745% | 67.164909/66.771564 s | 0.579247% |
| 实时因子 | 0.213469/0.215027 | 0.727454% | 0.149121/0.149983 | 0.585264% |

short 扫描输入原始配对变化 bootstrap 95% 区间为
`[-8.208165%, -3.084141%]`，long 为 `[-8.837129%, -1.669361%]`。核心墙钟、RSS
均值和逐 pair RSS 非退化门全部通过，D6 判定 `d1_optimization_admitted=true`。
扫描输入数据组织优化的正式矩阵 P1 关闭。

仍开放 P1：

1. **系统实时容量。** candidate 最低实时因子为 `0.143427`，未达到 `1.0`。扫描输入只占
   完整模块栈的一部分，核心墙钟改善低于 1%。
2. **精度和身份。** 矩阵没有 RMSE、NEES、NIS、严格 ID Switch 和航迹连续性。
3. **目标环境。** 当前是三维质点证据，不包含 AirSim、真实图像或冻结目标处理器容量。
4. **尾部稳定性。** 单次最大调用耗时仍有离散反向变化，不将累计墙钟准入解释为 max 延时
   已收敛。

正式复核位于
`research_modules/scalable_3d_simulation/docs/SCALABLE_3D_D1_SCAN_INPUT_MULTISEED_REVIEW_CN.md`。
4.2 GB 原始 episode 不进入源码提交。

## 2026-07-24 D1 协方差优化正式多 seed 准入

当前无新增 P0。早期逐项相关裁剪可能在所有二维相关系数均合法时产生非正半定六维协方差。
D1 已在相关矩阵空间执行正半定投影，并提供确定性收缩和对角回退。V3 reference
`a5a472cf81496d94a98db3deb88a3d5c6951f0ce` 与 candidate
`064cbb979d3bab68fee995e476df25709eb666db` 共同包含该修复和 D2 审计修复，唯一 treatment
为标量或向量化协方差限制。

main 完成 short seeds `1101-1110` 的 10 组 2.2 秒 pair，以及 long seeds `1101-1103`
的 3 组 10 秒 pair。每个 episode 使用 200 个目标、200 个资源和 2 个侦察节点，共 26 个
episode。13/13 跨构建业务语义检查通过；进程退出、有限状态、D2 审计、在线真值隔离和
manifest 注册均通过。V1/V2 episode 未复用。

| 指标 | short reference/candidate | short 改善 | long reference/candidate | long 改善 |
| --- | ---: | ---: | ---: | ---: |
| D1 fusion wall | 4.029165/3.652252 s | 9.35462%，10/10 更快 | 32.954357/30.768826 s | 6.631993%，3/3 更快 |
| D1 fusion P95 | 199.662309/186.378972 ms | 6.652902% | 264.820947/247.195761 ms | 6.655511% |
| 核心墙钟 | 10.686187/10.350200 s | 3.144124% | 69.230348/66.828146 s | 3.469868% |
| 外部 elapsed | 17.864/17.584 s | 1.567398% | 98.686667/96.233333 s | 2.485983% |
| 实时因子 | 0.206126/0.212769 | 3.222384% | 0.144648/0.149857 | 3.600960% |

short 的 D1 fusion 原始配对变化 bootstrap 95% 区间为
`[-10.914359%, -8.113134%]`，long 为 `[-7.279095%, -5.406805%]`。长短单位时间增长、
核心墙钟和内存门均通过，D6 判定 `d1_optimization_admitted=true`。

仍开放 P1：

1. **系统实时容量。** candidate 最低实时因子为 `0.143397`，未达到 `1.0`。D1 优化准入
   不能关闭 200 对 200 全系统实时缺口。
2. **精度和身份。** 本性能矩阵没有 RMSE、NEES、NIS、严格 ID Switch 和航迹连续性。
3. **目标环境。** 当前是三维质点证据，不包含 AirSim 或冻结目标处理器运行结果。

后续扫描输入专项已按同提交 13-pair 矩阵完成并准入，当前状态以上节为准。下一轮按最新候选
阶段墙钟在 D1 融合、D2 关联和发布链之间选择可分离热点。不得通过降低量测频率、缩短滞后
窗口或删减协方差字段获得表面性能收益。

紧凑证据和正式复核位于
`research_modules/scalable_3d_simulation/docs/SCALABLE_3D_D1_COVARIANCE_MULTISEED_V3_SUMMARY_20260724.json`
与 `SCALABLE_3D_D1_COVARIANCE_MULTISEED_V3_REVIEW_CN.md`。4.2 GB 原始 episode 不进入
源码提交。

## 2026-07-24 D1 协方差成对限制单 seed clean 准入

当前无新增 P0。D1 已将六维协方差 15 个上三角非对角元素的标量裁剪改为批量裁剪，并保留
`vectorized_covariance_limit=False` 参考路径。优化不缓存协方差，也不跳过预测、更新或
fixed-lag 重放。对角 floor/ceiling、`0.999` 相关上界、对称化、非有限值重置、双时间戳、
NED、谱系和中心身份所有权保持不变。

main 在 clean reference `7cc2d0cfd598a72d60c6ba8c7d4a283f4e5a897d` 与 candidate
`95bf46e34321127313757986bb28bfb14b7e3c59` 上运行三轮交错 pair。输入固定为 seed 1100、
200 对 200、2 个侦察节点、2.2 秒和 2,035 条匿名观测；配置 SHA-256 为
`20ef5248c8b45ff5aced9080c8d47e65a43aaba54f18ce824dc50fac7a52b840`，运行配置
SHA-256 为 `deabac3fbf2a788f68a0b807945e5f1bedacf8c5917c4d3b49c5cffb3c90da70`。
三轮规范在线载荷、真值状态和标签、计划谱系、ACK 来源及 D4 内容地址均通过跨构建语义
检查；六个进程退出码为 0，状态有限，在线真值使用为 0。

| 项目 | reference | candidate | 变化 | 状态 |
| --- | ---: | ---: | ---: | --- |
| D1 fusion wall 均值 | 4.014714 s | 3.595533 s | -10.4411% | 3/3 更快 |
| D1 fusion P95 均值 | 184.228658 ms | 173.330868 ms | -5.9154% | 3/3 更低 |
| 核心墙钟均值 | 10.561416 s | 10.229606 s | -3.1417% | 3/3 更快 |
| 外部 elapsed 均值 | 18.176667 s | 17.516667 s | -3.6310% | 3/3 更快 |
| 最大常驻内存均值 | 1,076,584 KiB | 1,075,045 KiB | -0.1429% | 3/3 更低 |
| 实时因子均值 | 0.208307 | 0.215065 | +3.2441% | 仍低于 1 |
| D1 scan input 均值 | 1.179072 s | 1.183325 s | +0.3607% | 独立阶段，不归因 |

D6 的显式 pair consumer 要求提交、配置、seed、规模、观测数、clean manifest、有限状态、
真值隔离、零退出和跨构建业务语义全部通过；性能门还要求 fusion 3/3 更快、均值至少下降
5%、P95 下降、核心墙钟不恶化且至少 2/3 更快、RSS 增幅不超过 5%。本批全部通过，
`d1_optimization_admitted=true`。

该批是正式 V3 前的单 seed clean 准入。当前状态按上节 V3 修订：

1. **系统实时容量。** 候选实时因子均值为 `0.215065`，约为实时需求的 21.5%，不能关闭
   200 对 200 实时 P1。
2. **独立 seed 与长时增长。** 已由 V3 的 10 组 short 和 3 组 long pair 关闭。
3. **精度和身份。** 本批未计算均方根误差、归一化估计误差平方、归一化创新平方、严格
   ID Switch 和航迹连续性。业务载荷等价不能替代精度验收。
4. **AirSim 与目标硬件。** 当前输入为三维质点，不含真实图像、雷达负载、AirSim 调度和
   目标处理器容量。

该优化保持为默认路径。下一阶段保持算法语义和传感器频率不变，补充严格离线精度和
AirSim/目标硬件结果，并根据 V3 分阶段墙钟决定下一项热点。早期证据见
`research_modules/scalable_3d_simulation/docs/SCALABLE_3D_D1_COVARIANCE_LIMIT_CLEAN_AB_REVIEW_CN.md`
，正式证据见上节 V3 复核。

## 2026-07-24 D1 共同质心原子影子 A2

当前无新增 P0。D1 已冻结单次原子入口，main 已切换默认关闭的审计旁路，D6 已实现
legacy/atomic 双路径只读校验。原子结果在后置完整性失败或装配失败时丢弃 shadow 并恢复
输入 generation 状态。D2/D3 不消费旁路，正式航迹和全局编号所有权不变。

clean `7cc2d0cfd598a72d60c6ba8c7d4a283f4e5a897d` 的 seed 1100 pair 使用 200 对
200、2 个侦察节点和 2.2 秒。9 条 atomic 记录全部通过 post-integrity，覆盖两次各
1813 条航迹摘要；原子失败、shadow 物化、禁止表面修改和在线真值使用均为 0。过滤审计
主题并规范业务相对序号后，两臂各 3294 条业务记录逐条一致，计划谱系和 ACK 来源有效，
离线真值制品摘要一致。

当前 P1 仍开放，A2 不准入：

| P1 项 | clean atomic 证据 | 状态 |
| --- | --- | --- |
| 性能门 | control/shadow 核心墙钟 `10.735/19.450 s`，增量 `81.1799%`；P95 `1536.429 ms` | 未达到 `<=5%` |
| 自然 treatment | 46 条决策，`0 accepted/46 oosm_scan rejected` | 无有效处理样本 |
| 结果效果 | 业务非干预通过，accepted 为 0 | outcome effect unavailable |
| accepted/failure 实际载荷 | rejected-only clean episode 已有；accepted 和 atomic failure 只有单元负例 | 实际 episode 待提供 |

全拒绝场景下，旧 prepared-handle 路径本就跳过 assemble。原子入口的 `544.960 ms` 平均
操作时间仍包含一次规范描述和一次后置完整性复核；main 的禁止表面前后摘要另占
`254.599/196.413 ms`。该改动关闭调用边界安全缺口，没有形成性能收益。A3/A4 和 seeds
`1101/1102` 继续停止。后续将完整 shadow 审计移出在线规则主循环，并优先处理 D1 批量融合、
空间预筛选、固定滞后合并重放和延迟序列化。证据见
`research_modules/scalable_3d_simulation/docs/SCALABLE_3D_CENTROID_OVERLAY_A2_ATOMIC_REVIEW_CN.md`。

## 2026-07-23 D1 共同质心发布影子 A2

当前无新增 P0。D1 已完成不可变 prepared handle、完整载荷强摘要复核和 detached shadow
装配；main 已通过默认关闭开关接入审计旁路，并把禁止表面前后摘要、prepare、evaluate、
assemble、影子摘要和日志物化分别计时。D6 已完成只读 consumer 和同 seed 性能门。代码合同、
失败关闭和业务隔离已实现。

提交 `2b976a7213ccdaa35fe0e22dea88def2651e9467` 的 seed 1100 开发 pair 使用
200 对 200、2 个侦察节点和 2.2 秒。影子臂只多 9 条审计记录。去除该 topic 后，两端
3294/3294 条业务记录经计划编号、总线序号、确认来源和 D4 内容地址规范化后逐条一致；
真值 NPZ、离线真值标签和五米接近事件一致。D1/D2/D3/D7 最终数量均为
`202/201/186/186`。禁止表面修改、全局编号变化、D2/D3 消费和在线真值使用均为 0，
业务非干预门通过。

当前 P1 仍开放，且 A2 不准入：

| P1 项 | 当前证据 | 阻断状态 |
| --- | --- | --- |
| 性能门 | control/shadow 墙钟 `10.7122/19.3765 s`，增量 `80.88%`；影子 P95 `1533.00 ms` | 未达到 `<=5%` |
| 自然 treatment | 46 条 evidence、9 次评估，`0 accepted/46 oosm_scan rejected` | 没有有效处理样本 |
| 结果效果 | 业务等价已证实，但无 accepted treatment | outcome effect unavailable |
| 正式来源 | 两端 manifest 均为 `repository_dirty=true` | 仅开发证据 |

平均耗时中 prepared 构造、前摘要、后摘要和 overlay 评估分别为
`345.10/224.46/207.31/195.42 ms`，合计占影子阶段约 99.99%；装配和日志不是瓶颈。下一步
由 main 与 D1 研究减少完整规范载荷的重复处理，同时保持 metadata、状态、协方差、来源、
身份、双时间戳和全局编号的原地修改检测。不得放宽 OOSM 或结构门制造 accepted。性能门
通过后才运行新的匿名冻结扫描 treatment 发现；A3/A4 和 seeds `1101/1102` 继续停止。
证据见
`research_modules/scalable_3d_simulation/docs/SCALABLE_3D_CENTROID_OVERLAY_A2_PREPARED_REVIEW_CN.md`
及同名 JSON。

## 2026-07-23 D3 身份承诺下游准入

当前无新增 P0。D3 已增加 `d3_identity_commitment_admission_v1`：仅显式
`committed` 航迹可进入普通或 M 对 N 计划；歧义保持、保持后未承诺、字段缺失和未知状态
全部失败关闭。已绑定目标被撤销时，迟滞和每窗口变更预算不能保留旧绑定，D3 发布严格更新的
计划版本。专项覆盖两类未承诺、缺失、未知、旧绑定撤销、M 对 N 全角色阻断、过时前序版本和
非等量规模。D3 全量为 `450 passed, 1 skipped`，跳过项是可选 OR-Tools。

scalable 3D main 已从同一 D2 发布按 `global_track_id` 复载精确承诺集合。撤销发生后，同一
D2 周期先清除旧 D7 binding 并设置强制重规划；D5 主动视觉和 D7 输入还独立复核 committed
集合。承诺 map 缺失、键集合不等于当前 D2 航迹或 schema/policy 不支持时直接报错，不能回退。
main 专项与全量为 `34/157 passed`。

AirSim 经典二维 D2 暂无 v2 承诺侧车。main-owned episode bus 只在该可信中心跟踪器边界生成
逐航迹显式 committed 清单，并要求精确覆盖当前输入；普通适配器缺少清单时输出
`identity_commitment_missing`，D3 仍拒绝。integrated point-mass 的旧中心 D2 适配器也显式
声明来源。AirSim runtime、integrated point-mass 和跨模块合同分别为 `158/7/7 passed`；
新增一项 AirSim 部分承诺清单拒绝负例。

detached clean `7e15dac9cdaf6743999dfe045a70676fd31a17d6` 随后完成同输入
seed 1100 复验。两臂均为 200 对 200、2.2 秒、2 个侦察节点；控制臂启用 source-key
与结构歧义 hold，候选臂只增加身份中性质心。t=0.75 秒的 v1 计划包含 193 项分配；
t=1.0 秒有 11 个原分配目标撤销承诺，D3 绕过迟滞强制发布 v2/186；t=2.0 秒发布
v3/186。11 个目标在 v2 及后续 D3 计划、D5 主动视觉、D5 终端绑定和 D7 导引中的
继续执行违规均为 0。main 运行时记录一次 binding hold 事件和 13 个 binding 撤回计数；
该计数与 D3 的 11 个拒绝目标口径不同，未混写。

两臂 D1/D2/D3 均为 `202/201/186`，严格 ID Switch 均为 `3`，track/coverage
continuity 均为 `0.826667/0.828333`，可用/常规不可用/未承诺映射均为
`1491/218/76`，身份承诺覆盖均为 `0.957471`。质心候选为 `46/0/46` 个
候选/施加/拒绝，仍是零 treatment。该批关闭 clean seed 1100 的下游安全合同，
不关闭 D1/D2 连续性和可用性 P1，也不晋级候选。episode 没有伪造 stale plan；
旧版本拒绝由 AirSim 和模块回归覆盖。

当前剩余 P1 是：真实 AirSim 多 seed 产生并消费真实 D2 承诺侧车，完成撤销、升版、
stale plan 注入和 D5/D7 零越权复验；D1 已在受控冻结扫描中形成非零 treatment，但真实匿名
冻结输入、拒绝路径发布态替换语义和系统收益仍未关闭，因此不恢复 seeds 1101/1102。机器
审计和中文结果位于
`research_modules/scalable_3d_simulation/docs/SCALABLE_3D_IDENTITY_COMMITMENT_GATE_CLEAN_AB_20260723/`。

## 2026-07-23 当前优化 20-seed 全栈校准

当前没有新增 P0。detached clean `5263e2b343dc4b96d239f77ef09437eb132f9efb`
已顺序完成 seed `1000-1019`、nominal 200 对 200、10 秒规则全栈。20/20 状态有限，
在线真值使用总数为 0，generation integrity 和 D6 schema/provenance 审计通过，failure
reason 为空。D6 将 20/20 归类为 `descriptive_clean_source_calibration`；正式实验矩阵
episode 数仍为 0。

已有 clean `0d2da25` 的同 seed 20 组作为性能参考。`0d2da25 -> 5263e2b` 的 20/20
直接跨构建审计全部通过，规范在线载荷、真值状态与标签、D3 计划谱系、D4 内容地址和
ACK 来源一致。核心墙钟均值由 `96.391 s` 降至 `86.099 s`，20/20 seed 均改善；
配对变化均值 `-10.63%`，95% seed bootstrap 区间 `[-11.71%, -9.61%]`。实时倍率
由 `0.1039` 提升到 `0.1163`，仍约差 8.6 倍，系统实时 P1 不关闭。

| P1 项 | 当前证据 | 状态 |
| --- | --- | --- |
| D1/D2/D5 局部优化转化为全栈收益 | D1 扫描输入、D1 融合、D2 关联分别变化 `-22.06%/-15.15%/-6.41%`，三项均 20/20 seed 改善；D5 终端配准变化区间跨零 | 当前实现的多 seed 性能证据已闭合 |
| 200 对 200 实时能力 | 核心墙钟均值 `86.099 s/10 s`，实时倍率均值 `0.1163` | 开放 P1 |
| D1/D2 尾延时 | D1 融合 P95 均值 `233.488 ms`，D2 关联 P95 均值 `142.627 ms` | 开放 P1 |
| D7 与 publication bus 性能 | 业务输出不变，累计时间分别增加 `6.24%/4.44%` | 开放 P1，需固定输入归因 |
| D1/D2 严格真值映射 | strict ID Switch 0/20 可用；partial mapping/frame/transition coverage 为 `98.5760%/10.7404%/0.6118%`，19 个 lower-bound 合计 199；D1 RMSE/NEES 因 `d2_lineage_mapping_missing` 不可用 | 开放 P1 |
| 正式学习和物理效果 | 学习 bundle 未加载，正式矩阵为 0，10 秒名义场景无五米接近 | 开放 P1 |

当前优先级为：先治理 D1 融合/扫描输入和 D2 尾延时；同时补齐 D1/D2 严格真值映射所需的
离线唯一性证据；随后归因 D7/发布总线的小幅性能增长。partial lower bound 不得回填 strict，
也不得形成上界。不能通过降低传感器、融合、关联、视觉或导引频率关闭实时缺口。紧凑机器证据位于
`research_modules/scalable_3d_simulation/docs/SCALABLE_3D_20SEED_PERFORMANCE_CALIBRATION_20260723.json`。

### 2026-07-23 后续复核

| P1 项 | 新证据 | 当前状态 |
| --- | --- | --- |
| D1 scan-input claim 重复序列化 | 771 scans、11,889 observations，旧/新 claim registry 和完整融合语义相同；五轮交错 P50/P95 `3.618/4.049 -> 1.905/2.038 s` | 局部热点关闭；clean 多 seed 全栈收益待复测 |
| D2 严格身份映射 | 20/20 producer 重放通过；118 个多真值航迹帧、107 个连续区间、83 个受影响 episode/航迹组合；2,464 个缺显式标签的受评分映射 | 根因已定位，strict IDSW 仍开放且 unavailable |
| D1 真值精度映射 | 191,425 条可用估计中 188,951 条有唯一候选，2,474 条因 `truth_label_missing` 未解析；可消费 episode `0/20` | 开放 P1；禁止输出不完整 sidecar |
| D7 历史阶段增长 | 固定 200 pair、185 frame、37,000 条命令，两构建各 6 次；变化 `+0.626%`，95% 区间 `[-1.828%, +3.178%]` | 未确认 D7 内核回归，不改导引公式和门控 |
| main publication bus | 四组交错 clean 2.2 秒复测中位数 `0.887 -> 0.775 s`，下降 12.69%；核心墙钟中位数只下降 0.44% | 局部键规范化热点关闭；系统实时 P1 不关闭 |

组合 clean 提交 `d79aba3` 的 nominal 200 对 200、2.2 秒、seed 1000 smoke
状态有限，在线真值使用为 0，实时倍率为 `0.204`。与 `5263e2b` 的 3,430 条规范在线
记录、真值状态、计划谱系和内容地址语义等价。该单 seed 结果只证明集成和语义边界，
不替代 20-seed 性能验收。

下一优先级调整为：D1 先在不读取在线真值的前提下增加雷达/视觉跨模态一致性门控和
混轨分裂回归；main/sensor producer 再扩展离线 truth sidecar，使每条观测明确属于真实
目标、已知虚警或标签未知。修复后由 D2/D6 重跑 strict IDSW、continuity 和 D1
RMSE/NEES。实时性能仍需另行处理 `GlobalTrack` 物化、固定滞后 replay、D2 尾延时及
结束后处理，不能用本轮局部微基准关闭。

### 2026-07-23 三态标签与 D1 几何治理

| P1 项 | 新实现与证据 | 当前状态 |
| --- | --- | --- |
| D1 视觉跨模态污染 | 冻结 771 scans/11,889 observations 中，17/17 已知视觉污染观测离开原错误航迹；相机只读映射、真实旋转和嵌套内参按值解析，非法几何失败关闭；detached clean 四组回放未再出现该视觉谱系污染 | 复现缺陷和 clean 描述性复验均关闭；正式多 seed 验收未启动 |
| 离线观测标签覆盖 | main v2 显式输出 target/known_false_alarm/unknown；detached clean 三组 2.2 秒虚警标签 `100/103/109`，10 秒 seed 1000 为 402，四组 `missing_identity_evidence=0` | 新 producer、消费合同和 clean 描述性复验关闭；旧 20-seed v1 制品不追认 |
| D2/D6 分母语义 | 已知虚警不进入严格 IDSW，unknown/冲突/缺失继续失败关闭，D6 不回填 strict；D5 旧训练导出和保留 seed 桥忽略非目标标签 | 合同与测试关闭 |
| 严格身份可用性 | 三个 2.2 秒 seed 仅 1/3 可用；seed 1000、1002 各剩 2 个雷达混轨映射。10 秒 seed 1000 剩 7 个映射、6 帧、6 航迹 | 开放 P1，当前 owner 为 D1 雷达扫描关联 |
| 本轮证据等级 | detached clean `488dc39`，四组状态有限、在线禁用字段和 truth use 均为 0，manifest 均为 clean | 描述性 clean 校准，尚非 formal acceptance |

独立回归为 D1 `191 passed`、D2 `249 passed`、D6 `586 passed`、scalable main
`134 passed`。当前没有新增 P0。严格 IDSW 不可用不得记为 0，部分下界不得替代严格指标。
三态与几何治理机器摘要位于
`research_modules/scalable_3d_simulation/docs/SCALABLE_3D_IDENTITY_DISPOSITION_RECALIBRATION_20260723.json`。

### 2026-07-23 D1 雷达交替环候选阻断

main 对 baseline `488dc39` 与 D1 v1 candidate `d967c96` 完成相同
200 对 200、2.2 秒、`recon_count=2`、seeds 1000/1001/1002 的 detached clean A/B。
逐 seed 配置哈希完全一致，三组状态有限、来源干净、在线真值使用为 0，缺失身份证据为 0，
目标与已知虚警标签数相同。

| seed | ambiguous | strict identity | D2 航迹 | D3 分配 | suppression |
| ---: | ---: | --- | ---: | ---: | ---: |
| 1000 | `2 -> 0` | unavailable -> available；候选 IDSW 3、continuity 0.8600 | `201 -> 200` | `200 -> 198` | `22/1962 = 1.12%` |
| 1001 | `0 -> 0` | IDSW `9 -> 7`；continuity `0.869444 -> 0.814444` | `202 -> 194` | `200 -> 190` | `130/1966 = 6.61%` |
| 1002 | `2 -> 0` | unavailable -> available；候选 IDSW 4、continuity 0.8350 | `200 -> 197` | `200 -> 193` | `78/1958 = 3.98%` |

strict availability 虽由 `1/3` 增至 `3/3`，D2 航迹、D3 分配和 seed 1001 continuity
出现退化。v1 不晋级，默认在线路径不变。提交 `8f17c5d` 将实验候选设为默认关闭后，三 seed
业务指标全部恢复 baseline；跨构建 `3/3 passed=True` 且规范在线载荷 `3/3` 相等。
main 已增加默认关闭的同构建实验开关
`--d1-radar-assignment-ambiguity-governance-v2`，并在 summary 与 observation-governance
audit 中记录实际 selected policy version、enabled/status 和抑制诊断。兼容 policy version
字段不单独用于判断运行策略。manifest 同时绑定完整
runtime profile、SHA-256 和 episode ID 后缀，后续 A/B 不再依赖修改 D1 默认值，也不会让
不同 treatment 共用 episode 身份。
D1 v2 已完成模块实现；main 独立穷举 `2,666` 个小规模二部图，最大匹配允许边分量与穷举
oracle 全部一致。D1 全量 `220 passed`，scalable 3D 全量 `142 passed`。这些结果只证明图论
边界和运行时接线。

detached clean `c928727` 的首个未见 seed 1100 已完成 200v200、2.2 秒、
`recon_count=2` 同构建 A/B。两组配置哈希相同、来源干净、状态有限、在线真值使用为 0；
目标/已知虚警标签均为 `2352/90`。v2 的 ID Switch `9 -> 9`，track continuity
`0.865 -> 0.830`，available mappings `1566 -> 1503`，D1 航迹 `202 -> 202`，
D2 航迹 `203 -> 199`，D3 分配 `200 -> 196`；9 个歧义扫描抑制
`77/1954=3.94%` 雷达观测并产生 91 次 track coast。候选无身份收益且业务可用性下降，
已在首个 gate 失败后停止 seeds 1101/1102、10 秒和 20-seed。v2 不晋级并保持默认关闭。

早先 `/tmp/msm-clean-radar-d967c96` 遗漏 `--recon-count 2`，实际使用 8 架侦察机，只保留
为 stress 数学诊断。该诊断确认 v1 遗漏最大匹配中的 free-row/free-column 替代路径，雷达
零径向速度为未观测占位，不能用于消歧。严格身份 P1 保持开放。下一候选应保留 v2 的
allowed-edge 结构证据，但不能继续整分量全抑制；需要研究多假设、概率关联或“冻结身份承诺、
保守更新状态”的接口，并联合验收身份、D1/D2 航迹、D3 分配、continuity、suppression、
birth 和 recall。v1/v2 均不运行扩大矩阵。v1 机器摘要位于
`research_modules/scalable_3d_simulation/docs/SCALABLE_3D_RADAR_ASSIGNMENT_CANDIDATE_REVIEW_20260723.json`；
v2 评审位于
`research_modules/scalable_3d_simulation/docs/SCALABLE_3D_RADAR_ASSIGNMENT_V2_CLEAN_AB_REVIEW_CN.md`。

### 2026-07-23 D1-D2 结构歧义保活与身份承诺 v2

D1、D2、D6 和 main 已关闭该候选的合同级缺口。D2 发布
`d2.identity-evidence-commitment.v2`，明确区分已承诺、hold 未承诺和 hold 后未承诺。
未承诺记录不携带来源观测或真值候选，不能进入当前 D3 分配窗口。hold 证据键和量测时间
水位独立于 claim ledger 保留，只有不同、更新且首次接受的原始证据可恢复已承诺状态。
main 对恢复航迹只发布被接受量测的精确 D1 谱系。D6 使用
`d2.scalable3d_identity_evidence.v2` 和独立审计重算承诺覆盖、恢复原因、水位、
overflow 与绑定违规，不回填 strict ID Switch。D2 恢复承诺现在额外检查发布新鲜度：
量测晚于 hold 水位且在当前帧内不超过 `0.9 s` 才可恢复。离线身份清单 v2 绑定完整恢复
配置和全部 D2 发布，D6 从在线 JSONL 独立复核。D2、D6 和 scalable main 回归为
`291/611/146 passed`。

detached clean `ff881316243ff5a2991a4659ab78637ed625d123` 使用 nominal 200 对 200、
2.2 秒、`recon_count=2`、seed 1100 完成同构建 A/B。两端
`config_sha256=34f5563579d9d2e7d1ea2b57cf353d2465b3bd16c5310570d40e72fc7aeac461`，
工作树 clean，状态有限，在线真值使用为 0。

| 指标 | baseline | 结构歧义保活候选 | 判定 |
| --- | ---: | ---: | --- |
| D1 航迹 | 202 | 202 | 持平 |
| D2 航迹 | 203 | 201 | 退化 2 |
| D3 分配 | 200 | 197 | 退化 3 |
| 可用映射 | 1566 | 1491 | 减少 75 |
| 全记录承诺覆盖 | 1.000000 | 0.957471 | 76 条显式未承诺 |
| committed/hold/after-hold | 1800/0/0 | 1711/69/7 | 状态可审计 |
| 未承诺来源/候选绑定违规 | 0/0 | 0/0 | 安全门通过 |
| strict ID Switch | 9 | 3 | 改善 6 |
| track/identity continuity | 0.865/0.865 | 0.826667/0.826667 | 退化 |
| coverage continuity | 0.870 | 0.828333 | 退化 |
| 重复分配 | 0 | 0 | 持平 |
| 实时倍率 | 0.2204 | 0.2076 | 下降 |

候选生成和消费侧车均为 46，D2 接受 33 个分量事件，累计阻止 hit/miss/birth
`69/69/4`。三个恢复航迹 `GT3D-000185/000186/000202` 的 `0.930815 s` 超龄证据已被
`source_observation_outside_recovery_publication_freshness_window` 阻断，严格指标恢复
可用。baseline/candidate 的清单均绑定 9 条 D2 发布和相同恢复配置摘要，D6 episode 与
runtime provenance 均通过。

当前无新增 P0。身份承诺、发布新鲜度、恢复配置谱系、真值隔离和绑定安全已关闭；算法准入
仍是开放 P1。seed 1100 因 D2/D3 可用性和连续性退化未通过，seeds 1101/1102、10 秒和
20-seed 不执行，默认开关保持关闭。下一候选不能扩大评分窗口，应优先校准 gap/hard lease、
birth 抑制和恢复等待，再从 seed 1100 开始。

### 2026-07-23 身份中性质心校正开发门槛

D1 已实现默认关闭的身份中性质心校正，并修复连续 generation 对临时发布态重复叠加的
问题。当前语义从正式观测历史重放到发布时间，每帧只施加一次平移和协方差膨胀；代际登记
按组件保存最新水位，默认容量 1024，固定滞后窗口外才允许淘汰。D1 全量回归为
`282 passed`。main 已增加显式开关、hold 依赖校验、运行审计和 profile 哈希绑定；
scalable 3D 专项/全量回归为 `34/157 passed`。

main 随后在当前未提交工作树运行 seed 1100 开发门槛。两臂使用相同 nominal 200 对 200、
2 个侦察节点、2.2 秒和配置 SHA-256
`20ef5248c8b45ff5aced9080c8d47e65a43aaba54f18ce824dc50fac7a52b840`。
两端都显式启用 source-key 与结构歧义 hold；候选只增加质心校正。

| 指标 | hold 控制臂 | hold + 质心校正 | 判定 |
| --- | ---: | ---: | --- |
| D1/D2/D3 数量 | 202/201/186 | 202/201/186 | 持平 |
| strict ID Switch | 3 | 3 | 持平 |
| track continuity | 0.826667 | 0.826667 | 持平 |
| coverage continuity | 0.828333 | 0.828333 | 持平 |
| 最终有效映射 | 191 | 191 | 持平 |
| 全记录承诺覆盖 | 0.957471 | 0.957471 | 持平 |
| 未承诺来源/候选绑定违规 | 0/0 | 0/0 | 安全门通过 |
| 质心组件 applied/rejected | 不适用 | 0/46 | 无实际 treatment |
| 质心拒绝原因 | 不适用 | OOSM 30；不平衡 16 | 线上资格门阻断 |

该候选没有触发状态校正，因此没有恢复 hold 已知的 D2/D3 可用性和连续性退化。结果也不能
用于判断质心公式本身的收益。当前无新增 P0；P1 仍开放，具体断点从“跨代累积和无界登记”
收敛为“真实异步扫描下零 treatment”。seeds 1101/1102 按停止规则不执行，默认路径不变。
后续受控冻结扫描复核已经完成，结论见下一节；该结果尚不足以重启 clean seed 1100
联合门槛。身份、时间、版本和绑定安全规则继续保持不变。原开发门槛记录见
`research_modules/scalable_3d_simulation/docs/SCALABLE_3D_NEUTRAL_CENTROID_DEV_GATE_CN.md`。

### 2026-07-23 共同质心冻结扫描边界复核

D1 已完成三类受控冻结扫描诊断。同步平衡纯交替环 `2x2` 分量施加一次
`15.000000 m` 共同平移，协方差不收缩；乱序平衡分量以 `oosm_scan` 拒绝；成员/观测
`2/1`、free row/column `1/0` 的分量以 `unbalanced_component` 拒绝。控制臂与候选臂
消费相同的扫描编号、双时间戳和观测数量，在线真值使用为 0。D1 专项/全量为
`5/287 passed`。

该复核同时定位了新的 P1 边界。两个拒绝分量的共同质心公式均未输出平移或协方差膨胀，
`applied_component_count=0`；候选分支仍执行 publication-base replay + replace。由于当前
离散匀速过程噪声的单段重放与分段预测不满足半群等价，候选减控制臂协方差差的最小特征值
分别为 `-0.0071928353214153066` 和 `-0.004617076466238031`。诊断已逐位确认差值来自替换
路径。它不是共同质心 correction，也不能被描述为拒绝路径严格无状态副作用。

当前无新增 P0。受控有效窗口子项已关闭，算法准入 P1 仍开放。D1 已完成 A/B/C 设计比较：
A 采用 detached publication overlay，是下一步最小原型；B 的固定滞后 OOSM 事件在事件排序、
过程噪声分段和一致性 oracle 冻结前暂停；C 保持 D1 只发布证据，由 D2 概率或多假设层消费，
需由 D2 owner 单独规划。该设计没有 Python、开关、DTO 或运行证据。

下一验收先关闭 A1/A2：规范 state/covariance/history/checkpoint/cache 不变，所有拒绝原因下
业务发布与 control byte-identical。通过后才使用新的真实匿名冻结扫描验证自然 treatment、
状态一致性、D2/D3 可用性和性能。候选状态保持 `candidate_not_promoted`，seeds 1101/1102
继续停止。设计文档位于
`research_modules/d1_sensor_fusion/docs/STRUCTURAL_AMBIGUITY_NEXT_CANDIDATE_DESIGN_CN.md`。

## 2026-07-22 后验代次与 clean 长时基线

main 已在 detached clean `0d2da25` 上完成 nominal 200 对 200、10 秒、seeds
`42000-42002`。三组均为有限状态、在线真值使用 0、分配保持 0。核心墙钟均值
`101.298 s`，实时倍率均值 `0.0988`，因此实时性能 P1 保持开放。

D1 final/full posterior publication 为 `453/453`、`516/516`、`505/505`；D2 final/
consumption/publication 为 `453/48/48`、`516/48/48`、`505/48/48`，pre-tick merge 为
`405/468/457`，pending 均为空。D6 v6 被动评估 3/3 integrity 通过、failure reason 为空。
seed 42000 同提交重复运行通过全量语义等价审计。与 `12c5073` 的 811 处在线差异全部是新增
D1/D2 generation 字段，summary、真值、计划谱系和其余载荷一致。

该项关闭 main/D6 的 runtime v2 三 seed 实际消费审计子缺口。它仍是
`descriptive_clean_source_calibration`，正式矩阵 episode 数为 0。

同一 detached clean `0d2da25` 随后顺序完成 seed `1000-1019` 的 20 组 200 对 200、10 秒
规则全栈。20/20 进程退出 0、状态有限、在线真值使用 0、分配保持 0、generation integrity
通过且 pending 为空。核心墙钟均值/范围为 `96.391/88.035-102.573 s`，实时倍率均值/范围为
`0.1039/0.0975-0.1136`。D1 融合、扫描输入、D2 关联、D3 分配、D5 终端配准和 D7 导引均值
为 `51.649/12.418/5.492/2.448/1.185/3.638 s`；实时 P1 保持开放。

D6 v6 将 20/20 判为基础 clean provenance 可用，failure reason 为空。D3 计划覆盖率均值为
`0.989606`，95% seed bootstrap 区间为 `[0.987144, 0.991813]`；D5 最终 binding 数均值/范围
为 `25.95/9-41`。本批没有五米接近，学习 bundle 未加载，实验矩阵 metadata 缺失，因此全部
仍为 `descriptive_clean_source_calibration`，正式矩阵 episode 数为 0。该批关闭规则基线
20-seed 描述性稳定性与代次消费审计，不关闭算法优劣、学习采用、实时或物理拦截验收。

## 2026-07-21 运行采用、离线结果与跨视角数据收敛

当前没有新增 P0。D3、D4、D5 的学习数据 producer 已完成全样本结构审计，main 的配对实验
矩阵固定使用 `sensor_random_schedule_version=entity_fixed_v1`，并持久化外生配置 SHA-256。
冻结 900 episode 保持只读，在线真值使用为 0。学习运行状态继续固定为
`PPO=false`、`assist=false`、`authority=false`、`rule_fallback=true`。

同日先完成 D3/D4 保留 seed v1 正式证据及 D6 独立审计。detached clean 提交 `6d5bfea` 的
nominal 5v5、2.2 秒、seed `1000-1019` 共有 20 个干净源 episode，在线真值使用为 0；其中
D3 的 20 次 OOD 回退已定位为二元 `previous_binding=1` 被错误套用连续 z 门。D3 owner 已按
端点语义修复，连续 6σ、冻结 bundle 和规则回退未变。随后在 clean 源提交 `7891296` 上完成
同配置 v2 正式重跑：D3 treatment applied/fallback=`20/0`，有效代价矩阵变化 `20/20`，最终
binding 变化 `0/20`；D4 confidence gate 通过 `0/20`，OOD/latency/finite/failure 各通过
`20/20`，safe adopted/fallback=`0/20`/`20/20`，冻结门限仍为 `0.6`。

D6 提交 `d4e8562` 已生成 profile-bound v2 availability sidecar，并独立重算上述 lineage、arm、
安全壳、分配和门控汇总。sidecar 状态为 `pass_offline_assignment_comparison_only`：D3 同帧
assignment comparison 可用，runtime ACK、post-intervention physical outcome、paired effect/
non-degradation、counterfactual 和 causal 仍为 `unavailable/null`。因此 v2 正式重跑和 D6 消费
缺口已经关闭；候选策略有效性、物理效果和 D4 故障降级效果仍是 P1，后者必须另用中心/二级失效
场景评估。

D4 新增 `d4-region-resource-runtime-ack-evidence-v2`。它把区域建议采用分为
`new_execution_plan_applied` 和 `evaluation_refresh_applied`。真实 main 5v5、seed 41 的同计划
刷新链为 source D3 seq 10、current D3 seq 94、consumption seq 96、D7 seq 99、ACK seq 100。
计划编号和版本均保持 v1，资源绑定、联盟和 authority 执行签名不变，因此只准入评估刷新；
刷新标志、binding/coalition、执行签名或前序计划证据被篡改时失败关闭。D4 当前全量
`430 passed`。该证据不等于新执行计划、成员 ACK、物理结果或奖励。

D6 新增运行时确认到离线三维结果的严格联接。真实 main 3v3 episode 的 2 条 ACK 被识别为
1 条新计划身份和 1 条同身份评估刷新，按 ACK sequence/timestamp 形成 6 个非重叠资源-航迹
窗口。D2 离线身份映射、三维真值状态、五米接近事件和 11 项输入 SHA-256 均在消费前校验；
在线真值使用为 0。窗口输出起始、终止、最小距离和有界距离进展诊断，但该诊断不是 D3
正式近端策略优化奖励，也不构成反事实或因果证据。D6 全量 `423 passed`。main 已把 11 项
输入清单、JSON、中文报告和 provenance manifest 自动接入有运行时 ACK 的 episode，scalable
3D 全量 `90 passed`。

D5 对冻结正式图语料的 99 条未标注边完成逐条审计。原导出没有保存可核验 source-observation
lineage，99 条全部保持 unavailable，没有使用最近邻或轨迹连续性伪标签。独立困难样本课程已在
detached clean 提交 `79b2550ce2ef407c7cfcc653ce04a80fe2226c06` 上复生：4,500 帧、
66,726 个匿名局部航迹节点、245,032 条默认几何门候选边，正/负/未标注为
`57,292/187,740/0`。补充 manifest、dataset manifest 和 composite view SHA-256 分别为
`4b9875fee86b5c425f683a6da23e6af1308bcf2383d3633d4fd6207fe2f25a32`、
`4c49aebae8040f8a7dace329b5d1769739e2e40d811c3ad5eb733f302ebd8f6f` 和
`11e8acbdbe268574ead402f2be5c9aa8e3459a7e4147a18e0570df3402892415`。数据支持与训练数据
来源门为 pass；尚未训练新模型、未生成 `.pt`，promotion 状态为
`awaiting_new_model_evidence`，G1 和 assist 继续关闭。

当前 P1 按以下顺序推进：先在 clean composite view 上训练新的 D5 图模型并完成内部独立测试；
再使用保留 seed `1000-1019` 做未见场景评估；随后建立规则与学习候选的同 seed paired shadow，
要求身份交换、错误合并、重复分配和安全违规不恶化；最后生成多 seed 的实际学习采用、运行确认
和物理结果证据。D3/D4 的有界诊断需另行冻结正式 reward 口径。上述门完成前不启动 PPO，
不开放在线辅助或控制权限。

## 2026-07-21 跨模块学习数据联合准入

D6 owner 已实现 `d6.cross-module-learning-data-admission.v1` 只读审计和命令行入口。审计显式
消费 training/shared seed registry、D3 正式 manifest、D4 正式 manifest 与独立 canonical view、
D5 tracklet/active-vision 正式 manifest/view/readiness、D4/D5 补充课程 summary，以及 D5 补充
主动视觉全样本审计和带外文件 SHA。正式观测语料、补充规则课程、逐样本审计、离线评分标签和
运行时 ACK 分层发布，来源混用、哈希篡改、dirty source、错误 seed、保留 seed 泄漏和 synthetic
ACK 冒充 runtime ACK 均失败关闭。

main 使用冻结的 900 episode 制品独立复跑。100 个训练 seed 的规范切分为 60/20/20，保留 seed
`1000-1019` 泄漏为 0，在线真值使用为 0。D4 补充课程的 hold/replan/nonzero quota/transfer 为
`100/200/200/100`；D5 补充课程为 100 episode/800 segment/1200 sample，四类 intent 为
`200/600/200/200`，wide/zoom 为 `1000/200`，拦截/侦察角色各 600。synthetic ACK
applied/rejected/missing 各 400 只算故障注入覆盖。D5 tracklet 的 480 条候选边中 381 条已标注、
99 条未标注，离线标签状态为 partial。

随后 D5 owner 对 clean 补充课程完成 100 episode/1200 sample 全样本审计：302/302 个受清单约束
文件、1200/1200 个 35 维有限特征、规范 episode/sample `60/20/20` 与 `720/240/240` 全部通过，
在线真值、保留 seed、dirty episode 和身份改写均为 0。审计文件/内容 SHA-256 为
`9a03653538e6dae054da8c127ad4a20aae2481af6c9bbef987edfddff0b423d3` 和
`a11b65596a4c416deba6d0cb35dcc0c32342a5bae0481291d43e8de0e26550dd`。

D6 已重新消费该证据。当前结论为 BC canonical view available，D5 supplemental full-sample
complete，D3/D4 full-sample pending，跨模块总状态 partial。reward、outcome、counterfactual、
causal、真实 runtime ACK 和 paired shadow 仍 unavailable；PPO、在线 assist 和 authority 均关闭，
规则回退强制。联合报告 JSON/中文 Markdown SHA-256 为
`d3e3e858a14fb570cd0eb19da2661ce76686906530e313b5f79e6bf6af336de2` 和
`aaaeaefd99f38a03e4f80ffa96dabcb0eef0dd9724cb38fdb163c0bf603eff21`。专项 `21 passed`、D6
全量 `385 passed`；main 复算正式 43,973 个文件的树 SHA-256 仍为
`8ffbe5cf044d121163c8acc3dce1bbd54e14bb6b211b8e1cf440f24c93294fca`。

开放 P1 转为：逐样本审计 D3/D4 canonical views；producer 持久化真实动作采用、版本绑定、
runtime ACK、终局 outcome 和可归因 reward；建立同 seed paired shadow；最后使用保留 seed
`1000-1019` 做独立模型验收。上述条件未闭合前不启动 PPO，也不允许学习策略进入在线控制权限。

## 2026-07-20 三维学习数据容量与吞吐复核

九类 200v200、每例 2 秒的 clean-tree 容量探针已完成。9/9 episode 状态有限，在线真值
使用为 0；D3、D4 和 D5 跨视角图正常最终化，D5 主动视觉因三 seed 不满足 20 个未见测试
seed 而保留 staging。九个 episode 的最终学习目录为 55.36 MB；全部 900 例均按本轮
200v200 平均值计算的存储保守上界为 5.54 GB。存储 P1 门已关闭，5 GB 运行中停止门保留。

同一 nominal seed 930-932 的第二轮 clean-tree 复测由提交
`45b36500dc3c6935b1f116614993e291041eb12d` 产生，完整生成达到 `467.8007→144.5513 s`，
staging `225.9243→12.4372 s`，批次 finalization `116.5624→7.2777 s`；episode run
`125.2205→124.7415 s`。D5 active-vision 三 seed 为
`4.0494/3.9898/3.9995 s`，由上一轮 `41.5623/43.2639/41.2271 s` 降低约一个数量级。
三场均为有限状态、`repository_dirty=false`、在线真值使用 0。D5 仍占 staging 96.8%，
但写入与最终化合计 19.7 秒，低于 episode 计算 124.7 秒，D5 writer 系统级 P1 阻塞关闭。
runner 已实现 episode 边界暂停、同计划/同提交恢复、连续 progress 与 staging index 复核。
2026-07-20 正式生成先完成两个 45-episode 分块，90/90 均为有限状态、干净提交且在线真值
使用为 0。连续运行随后完成到 209/900，在第 210 项
`communication_degraded 200v200 seed 64` 暴露 D5 同一相机流单次多批次边界异常并退出。
该目录没有最终化，不能作为正式训练集；D5 修复改变提交后必须从零重跑，禁止混合提交。

本次退出同时暴露旧 checkpoint 只在显式暂停时更新，导致 progress 为 209 而 checkpoint
停在 90。main 已升级 `scalable3d-learning-generation-checkpoint-v2`：每个完整 episode
同步写 progress 后原子推进 checkpoint；旧 checkpoint 滞后仅在 progress、staging、计划顺序和
安全字段全部通过时恢复，并记录恢复次数和行数。checkpoint 领先、staging 不完整、提交改变仍
失败关闭。开发定向测试 13/13 通过；正式 900 episode 复跑尚未完成，因此该项状态为“软件
修复完成、正式证据待重跑”。

D5 修复后的 main 开发回归已复跑原失败 cell `communication_degraded 200v200 seed 64`。
该单元状态有限、在线真值使用为 0，episode 运行 27.4 秒、写入 3.9 秒，并在三 seed 计划的
1/3 边界写出 checkpoint v2 后正常暂停。该运行来自脏工作树，仅关闭原异常路径的开发验证，
不能替代新干净提交上的 900-episode 正式重建。

当前代码级阻塞已关闭，正式证据阻塞为新提交上的 900 episode 重建。行为克隆、近端策略优化、
20 个未见 seed、paired shadow 和模型准入仍未执行。

## 2026-07-20 三维 D1/D2/D6 真值隔离评估闭环

main 已将 D1 最终一致性证据带到 episode 离线边界，并保存在线证据、离线真值状态、D2
规范映射和离线结果。D2 映射只读取 D1 源观测谱系；代码路径不使用最近距离、目标名称、
actor ID 或末端接近结果。在线总线文件、真值状态 NPZ 和 D2 身份评估文件均以真实
SHA256 写入来源证明，D6 消费前再次校验结果和 D2 四类原始来源。缺失或冲突映射会使
RMSE/NEES unavailable，NIS 仍按在线证据独立统计；`id_switch_count` 缺证据时保持 null，
不会转成零。

D6 owner 已完成公开 D1/D2 适配器、逐 seed CSV、传感器/距离分档 CSV、聚合 JSON 和
中文 Markdown，D6 全量 `334 passed`。main 的 5v5 单 episode、无模块栈负例和双 seed
3v3 聚合均通过，scalable 3D 全量 `72 passed`。D1 在线证据通过
`observation_id + measurement_timestamp` 与 D2 规范身份精确联接，不使用航迹区间前向
填充。该工作关闭了“真实 episode 制品没有接入
D6”的接口级 P1 缺口。开放项转为实验级 P1：在 clean tree 上按 5/20/50/100/200 和至少
20 个未见 seed 生成正式统计，冻结 NIS/NEES、航迹连续性、身份交换和分阶段耗时门限；
当前单 seed/双 seed 结果不得作为性能达标结论。

## 2026-07-20 D4 下一周期消费与 D5 主动视觉整 episode 导出

main 已闭合 `plan N -> D4 advisory N -> plan N+1` 的单进程受控桥接。D4 只有实际
`assist` 且包含后投影 `d4-region-resource-advisory-v1` 时才进入消费候选；main 使用建议
生成时冻结的区域快照和正式 D4 裁决调用一次性 gate。通过后转换为 D3-owned
`d3_regional_planning_hint_v1`，D3 再按当前 previous plan、资源区域、已提交成员、备用和
transfer candidate 校验。shadow、无准入、replay、严格到期、fault generation 变化和
regional authority 路径均 fail closed。定向 4/4 及 scalable 3D 全量 72/72 通过，在线
真值使用为 0。开放项是跨进程 consumed advisory ledger、正式 D4 checkpoint、20 个未见
seed paired shadow 和长时/真实通信验证。

D5 owner 提供的主动视觉整 episode 合同已由 main 接入统一学习导出。数据集 split 语义已
升级为 learning/episode dataset v2 和 bundle v3：完整 `(scenario_version, seed)` group 不可分，
同一数值 seed 跨场景和规模原子进入同一 train/validation/test split。main 的
`scalable3d-learning-export-v2` 逐决策保存 truth-free snapshot、规则示范、requested/effective
action、计划/联盟/通信版本和同帧相机反馈；在线文件与离线 reward/outcome/counterfactual
文件物理分离。缺失 reward 保持 unavailable/null，不伪造 ACK 或因果标签。

main 新增 `scalable3d-learning-generation-plan-v1` 流式生成入口。nominal 2v2/5v5、seed
1/2/3、6 个 2 秒开发 episode 全部有限且在线真值使用为 0；D3/D4/D5 图成功落盘，主动视觉
107 帧因测试 seed 只有 1 个按预期不最终化。正式模式已在启动前检查完整场景/规模、训练与
保留评估 seed 零重叠、干净工作树、忽略输出目录及 D5 至少 20 个未见测试 seed。开放 P1
是 D6 outcome/counterfactual 回填、训练与模型准入。后续 clean-tree 九场景和两轮三 seed
优化复测已经关闭存储、finalization 和 D5 writer 系统级子项；当前容量/吞吐状态以本文顶部
专项为准。剩余 P1 是首个正式 45-episode 分块恢复证据，以及 900 episode 的运行、标签回填
和训练。

main 已冻结 `scalable3d-balanced-curriculum-v1`：100 个生成 seed 均衡进入 45 个场景/规模
cell，每 cell 20 个、总计 900 episode；seed 1000-1019 只用于最终评估。正式预检现会拒绝
缺失交叉 cell、cell 分母不足、训练/评估 seed 交集和 D5 未见 seed 不足，并记录 schedule
SHA256。runner 的可恢复分块软件合同已完成，D5 writer 已由同 seed clean-tree 复测确认收敛；
首个正式代表分块验证前不得连续执行完整批次。

D6 已接入 `scalable3d-experiment-matrix-v1` 的独立离线审计，按 R0/G1/A1/A2/A3/C1/F1
验证运行时实际采用证据、固定 cell 分母、同 comparison key 配对差值和 bootstrap 置信区间。
D6 全量 334 项测试通过；当前只有 dirty producer smoke，尚无 clean 完整矩阵和算法准入结论。

## 2026-07-20 规模化学习运行时接线

D3、D4、D5 和 D6 owner 已分别完成规模化研究管线，并由 main 分四次提交。D3 提供整
`(scenario, seed)` 数据划分、行为克隆、原生近端策略优化、bundle 和 paired shadow
准入；D4 提供变长区域图、规则基线、学习建议和资源守恒/通信邻接/owner/epoch/lease/
故障围栏/联盟提交投影；D5 提供真值物理隔离的图数据、原生消息传递网络、验证集校准和
校验加载；D6 提供离线逐 episode、逐 seed、聚合、中文报告和阶段耗时曲线。

main 已新增显式学习运行时装配。默认 D3/D4/D5 学习路径全部关闭。D3 `assist` 必须通过
bundle 内至少 20 个未见 seed、成本非退化、安全非退化和零回退帧门限；D4 当前没有正式
准入制品，任何 `assist` 请求均保持 `shadow`，区域建议以独立总线消息发布且不能修改正式
D4 裁决；D5 只有显式 bundle 才使用图边概率，缺失、校验失败、非有限、低置信和超时均
回退几何规则。episode manifest 新增 D4 策略版本，场景 metadata 记录请求/实际模式、权重
SHA256 和回退原因，不记录不可复现的本地绝对路径。

2026-07-20 main 回归为 `39 passed`。额外命令行 smoke 使用 5v5、seed 41、1.2 秒和三个
缺失 bundle，结果为有限状态、在线真值使用 0、实时因子 8.133；D3 回退
`model_bundle_missing`，D4 `assist -> shadow` 且正式裁决摘要前后相同，D5 回退几何规则。
该 smoke 来自 dirty 开发工作树，只验证接线和失败关闭，不属于正式模型证据。

当前没有新增 P0。D4 到下一轮 D3 的单进程消费闭环和 D5 主动视觉整 episode staging 已
关闭到接口/确定性回归层。开放 P1 为：生成 clean-tree 真实整 seed D3/D4/D5 数据；由 D6
回填主动视觉 outcome/counterfactual；持久化跨进程 D4 consumed-ID ledger；完成通信分区/
乱序、5/20/50/100/200 规模和至少 20 个未见 seed 的规则、图网络、强化学习及组合对照。
合成 fixture、三 seed staging 和单 seed smoke 不得用于模型准入。

## 2026-07-16 D5 5+1 ComputerVision 多相机专项

main 新增隔离入口 `run_d5_multicamera_branch.py`，单次启动 Blocks 后用 reset 分隔
AirSim detect 基线与 YOLOv8+原生 ByteTrack 候选。场景包含 5 个
`1920x1080/60°` 主相机、1 个 `3840x2160/75°` 俯视侦察相机和 5 个
`Quadrotor1` actor；运行 12 s、49 帧、seed 7，并按 2 s 间隔保存本专项要求的画面。
五个主相机允许只看到目标子集，侦察相机提供较宽视野。本专项未运行 D1/D2，main
用 actor 运动学合成中心侧 GlobalTrack fixture，并用 truth 做离线交并比评分；D5
关联代价、Hungarian 选择和稳定窗口只使用既有 GlobalTrack ID、相机内外参、双时间戳、
协方差和 camera-local track，不读取局部 actor/object/truth identity。

首次分析把全部 camera batch 的投影时间错误覆盖为最后一帧，导致前半段系统性像素偏移。
main 已修正为按各批次 `measurement_timestamp` 投影，并增加 `--replay-existing`，使用
完全相同的原始 AirSim 帧重算，未重新检测或改变仿真输入。

| 后端 | 检测召回 | 配准准确率 | 严格准确率 | 稳定配准 | 主相机联合覆盖 | 侦察全覆盖 | local IDSW | P50/P95 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| AirSim detect | `1.000` | `1.000` | `1.000` | `0.975` | `1.000` | `0.918` | `0` | N/A |
| YOLOv8 + ByteTrack | `0.622` | `0.996` | `0.966` | `0.955` | `1.000` | `0.878` | `25` | `10.42/12.37 ms` |

两条路径的在线 truth use 和 `global_track_id` rewrite 均为 0。结论是 detect 几何基线
通过本专项门限，证明“局部子集视场 + 侦察视场 + GlobalTrack 投影 + Hungarian/稳定
窗口”链路在该单 seed 场景可运行；YOLOv8+ByteTrack 虽满足延迟和配准门限，但召回、
本地身份连续性和侦察全覆盖未通过，继续保持 optional，不替换默认 detect。开放 P1
细化为：同几何至少 10 seeds、不同目标间距/遮挡、YOLO 类别和尺度标定、ByteTrack
IDSW 治理、侦察视野稳定性及真实相机同步/外参漂移。专项报告位于
`research_modules/airsim_runtime/outputs/d5_cv_5v5_multicamera_formal_20260716/`
`D5_CV_5V5_MULTICAMERA_BRANCH_REPORT_CN.md`。

回归结果：D5 `291 passed`，AirSim runtime `154 passed`；后者只有既有 Matplotlib
`Axes3D` 环境提示，不影响二维曲线或相机截图。两条路径各保存 7 个 2×3 间隔拼图，
共 14 个，覆盖 `0/2/4/6/8/10/12 s`。

## 2026-07-16 本地图像航迹可复用机制接入

`b.mp4` 人工框选实验继续作为 P2 离线诊断支线，不进入默认 AirSim、D1 融合或 D2
关联路径。本轮只抽取了与具体视频、亮度和跟踪器无关的机制：

| 层级 | 已实现内容 | 当前边界 |
| --- | --- | --- |
| main 合同 | `LocalImageTrackObservation` 统一携带 camera-local ID、local epoch、可见光/红外波段、measurement/arrival 双时间戳、像素中心/框、2×2 协方差、confidence 和显式 lost | metadata 禁止 global/truth identity；local ID 永远不是 `global_track_id` |
| D5 离线适配 | 人工视频记录可转换为上述合同；重复量测整批拒绝，lost 不携带旧像素 | 人工 ROI、CSRT、亮度候选、固定像素门限仍是离线案例调优，不晋级主线 |
| D1 融合边界 | `measured -> EO/pixel SensorObservation`，`lost -> None`；namespaced `source_track_key` 去重累积到 `GlobalTrack.metadata.source_track_ids` | 不改变全局 ID；真实相机模型、像素噪声和 producer 接线仍需标定 |
| main 到 D2 | `CanonicalTrack -> Detection` 只保留 NED 位置、位置协方差、版本和 `source_track_ids` | 像素中心、bbox 和像素协方差不进入 D2 |
| D2 审计 | 显式累计来源绑定冲突、来源不连续隔离和上游本地身份拒绝；进入 metrics、risk 和 replay 聚合 | 三项是审计量，不替代 `id_switch_count`，不自动改变 GNN/Hungarian、门限或风险分类 |

验证日期为 2026-07-16：D5 `288 passed`，D1 `111 passed`，D2
`123 passed, 1 warning`，跨模块合同 `7 passed`；warning 是既有 Matplotlib
`Axes3D` 环境提示。本批未启动 AirSim。D5 文档记录的 95 帧、5 local ID、475 条离线
记录转换结果为 `470 measured / 5 lost`，只证明合同转换，不证明通用多目标跟踪性能。

本轮关闭的是“局部图像航迹无法以双时间戳、协方差和命名空间来源进入 D1/D2”的接口
缺口。仍开放的 P1 是：真实可见光/红外/雷达 producer 接线、相机内外参和时间同步、
像素协方差标定、D5 拒绝计数到 main/D2 frame metadata 的运行时接线，以及至少 10 个
duplicate-source、teleport、dropout、clutter 和合法新目标 AirSim 受治理 case 的
false-suppression、recall、离线 IDSW/continuity 与置信区间。亮度差分、人工 ROI 身份、
固定 20 px gate、两点像素外推和 CSRT 权重不列为主线待办。

## 2026-07-15 M5N2 ClockSpeed 三档 60-Case 对比

main 使用同一 M5N2 baseline/candidate、seed 1-10 和 reset-separated Blocks
流程，补跑 `ClockSpeed=0.2` 与 `0.1`，并与既有 `1.0` 批次组成 60 个真实
AirSim case。D6 按 `case_id/profile/seed` 形成 20 组跨档配对；0.1/0.2 的
ClockSpeed 来自 case result，旧 1.0 来自 20/20 sibling generated settings，禁止按
目录名推断。三个 suite 的 identity/state online truth use 均为 0。

| ClockSpeed | Baseline active-primary | Baseline target | Baseline coalition | Control tick mean | 判定 |
|---:|---:|---:|---:|---:|---|
| `1.0` | `6/30` | `6/20` | `0/10` | `1070 ms` | 原实时倍率基线 |
| `0.2` | `9/30` | `9/20` | `0/10` | `2208 ms` | 本矩阵物理结果最好，但墙钟代价约翻倍 |
| `0.1` | `4/30` | `4/20` | `0/10` | `3453 ms` | 锁定和最近距离改善未转化为物理完成率 |

该结果不支持“ClockSpeed 越低，拦截效果越好”的假设。当前每个 active primary 的
`moveByVelocityZAsync(duration=0.1)` 顺序等待，导致 AirSim ClockSpeed 同时改变 RPC
墙钟占用和每个名义控制步覆盖的仿真时间；这不是严格固定步长闭环。P1 新增/保持两项：

1. 将控制派发改造成可审计的并行/固定仿真时钟调度后，按同一 20-case 矩阵复验；在此之前不以 `0.1` 作为默认运行倍率。
2. 修复 candidate 机会合同：0.1 seed007/009、0.2 seed006/009 共 4 个 case 的 observed active-primary/target/coalition 与冻结 `3/2/1` 不一致。相关 candidate aggregate 保持 unavailable，不以缩小分母发布性能结论。

本批关闭 multi-episode timing manifest、三档 provenance 和比较报告能力；未关闭 100 ms
实时预算、第二 primary/联盟完成率和 candidate 机会合同。D6 `272 passed`，AirSim runtime
`157 passed`。报告见 `subagent_reviews/MAIN_M5N2_CLOCK_SPEED_COMPARISON_REPORT_20260715.md`。

## 2026-07-15 M5N2 20-Case 实测完成与批次终止

按用户指定边界，main 在 baseline/candidate 各 10 seed、共 20 个 M5N2 case 落盘后终止当前批次。TERM 生效前批处理已额外完成 1 个 `png_ttc_2v2_seed001`；该单 case 不构成多 seed 证据并明确排除在本节统计之外，dropout 完成数为 0。20/20 M5N2 case 均有 physical 与 `d7-actual-execution-metrics-v2`，identity/state online truth use 均为 0；因此没有新增 P0 blocker。

| 指标 | Baseline | Soft prediction + trend coast candidate | P1 判定 |
|---|---:|---:|---|
| Active-primary physical | `6/30` | `6/30` | aggregate 持平，但逐 seed non-degradation 为 false，candidate 不晋级 |
| Target physical | `6/20` | `6/20` | 未形成稳定目标级改善 |
| Coalition completion | `0/10` | `0/10` | 第二 primary/联盟闭环继续开放 |
| 第二 primary 5 m | `0/10` | `0/10` | 最近距离均值 `12.74/12.57 m`，不是轻微阈值偏差 |
| 最终双 primary 视觉共识 | `1/10` | `1/10` | D5 证据持续性仍不足 |
| 预测/窗口过期 | `14/157` | `19/257` | candidate 增加预测但同时增加过期，未转化为物理收益 |

真实 pooled timing 为 3805 个 tick。main-bus 内层 mean/P95/max=`349.34/487.40/1305.99 ms`，100 ms 违例 `3649/3805`，主导阶段为 D1 fusion（均值约 `320.00 ms`）；control-tick 外层 mean/P95/max=`1069.45/1254.06/2072.51 ms`，100 ms 违例 `3805/3805`，主导阶段为 AirSim frame sample（均值约 `432.29 ms`）。外层包含 bus processing，两层禁止相加。

新增开放 P1：main 合并 timing 文件附加 case 标签并跨 case 重置 `frame_index`，D6 的严格单-episode loader 会拒绝该 suite 文件。逐 case 原始 timing 完整，本轮报告直接从 20 个原始 JSONL 分层汇总；后续需要版本化 multi-episode timing envelope/manifest，不能伪造连续 frame index。专项报告见 `subagent_reviews/MAIN_M5N2_TIMING_AND_SECOND_PRIMARY_REPORT_20260715.md`。

D5 复核确认第二 primary 时序记录 `3725/3725` 可用，但 bbox stable/handoff-ready 只有
`161/3725`（4.32%）；主要失败类别为 bbox 稳定性 34.44%、检测/新鲜度 32.46% 和
视觉关联 20.51%。当前统一 `failure_category` 没有直接写入最终产物，只能从 producer
漏斗字段重建，继续列为 D5/D6 P1 接线项。第二 primary 成员按当前 D3/D5 membership
识别，禁止将 `INT-03` 写死为固定第二成员。

D6 七阶段证据显示第二 primary 前四阶段 `20/20`、control/mode `17/20`、5 m physical
`0/20`；D7 复核发现 20 个第二 primary 均以 `collision_stop` 结束。当前没有写出 collision
object、碰撞法向及碰撞时的成员/环境距离，无法区分成员间冲突、环境碰撞或 AirSim 状态异常。
该碰撞 provenance 与 canonical target success/cooperative target diagnosis 术语统一均列为
main/D6/D7 P1，未补齐前不得把第二 primary 失败单独归因于 D5。

模块 owner 同步复核还确认：D1 fusion `320.00/451.46/1234.88 ms` 是 main-bus 主导阶段，
NIS/NEES/RMSE 仍无本批可用分母；D2 association `2.521/3.147/98.942 ms`，truthless 在线
IDSW/continuity 保持 unavailable；D3 `3725/3725` 条 history 中每 case 始终单一
`plan_id/version=1`，实际 plan/member/owner churn 为 0；D4 `active_degradation=0`，本批只构成
中心继续执行负对照，不构成二级或分布式性能证据。对应 P1 已由 D1-D4 owned GAP/PLAN 更新。

## 2026-07-15 D4 公开 Secondary Helper Fail-Closed P0 关闭

| 范围 | 本次关闭内容 | 当前边界 |
|---|---|---|
| D4 public helpers | `build_d7_secondary_handoff()` 与 `build_secondary_takeover_plan_metadata()` 对 active secondary plan 强制要求 sustained readiness、expected/actual source、plan/required lease epoch、expiry/current time 和 plan monotonicity 全部可用并通过；任一缺失均输出稳定 reject reason，只能 pending/phase 1 | 该规则只约束二级 owner/plan；distributed interceptor/peer 继续使用自身 ACK/lease/epoch/commit 合同 |
| D4 adapter | 不再用 required epoch 自动补造 plan epoch；同一已激活 secondary plan 的维持路径也逐 tick 重验完整证据 | 正常中心和未激活 pending 计划不会被误写为可执行二级计划 |
| 回归证据 | 新增两个公开 helper 的逐字段 `None` 负例、完整正例、same-active-plan 缺证据负例和 distributed bypass 回归 | 本批未启动 AirSim，不替代真实 RF/mesh、时钟漂移、队列、乱序和重传 P1 |

验证结果：D4 `280 passed`，AirSim runtime `147 passed`，integrated point-mass `7 passed`，`git diff --check` 通过。旧 `278/278` 只覆盖 heartbeat/readiness 主入口，不能证明公开 helper 的所有缺失组合；本节记录发现、修复和新增覆盖后的权威结论。

## 2026-07-15 D2/D6 Ceiling-Aware 准入 P1 代码缺口关闭

| 范围 | 关闭内容 | 当前边界 |
|---|---|---|
| D2 owner | continuity 准入升级为 `d2-p1-identity-admission/ceiling-aware-error-reduction-v1`：基线剩余空间 `H=max(0,1-Cb)`，所需提升 `min(0.10,0.10H)`；输出 headroom、实际/所需提升、误差消除比例、逐 gate reason 和 policy version | 旧 `+0.10` 仅保留 deprecated 审计字段；通过只形成 promotion review，不自动改变默认 GNN/Hungarian |
| D2 fail-safe | 指标缺失/越界、continuity 退化、IDSW baseline 为零、false-track 超限、P95 超预算及 baseline/candidate truth leakage 均拒绝；仅 IDSW 改善不可晋级 | `0.9810 -> 0.9840` 只证明 continuity 单项通过，不能从旧摘要追认完整联合门限 |
| D6 owner | `d6-p1-system-evidence` v2 同时消费 D2 v2 gates、legacy structured checks 和 bool checks；保留 policy/headroom/required/actual/error-reduction/all-pass 与失败原因 availability | 已用原冻结 replay 生成正式 v2 联合报告；历史 artifact 缺字段继续保持 `None/unavailable`，不补零 |

正式证据位于 `research_modules/d6_evaluation_metrics/outputs/p1_identity_ceiling_aware_v2_20260715/`。总体候选 IDSW `1.3583 -> 0.6167`，continuity `0.9810 -> 0.9840`，false-track `0 -> 0`，P95 `15.47 ms`，在线 truth leakage 为 `0`；仅 `clutter/combined` 分档通过，其他四档因 baseline IDSW 为零而 fail-closed，dropout truth alignment 为 partial，JPDA research adapter 未准入。`promotion_recommended=true` 只表示进入人工评审，`selected_online_path=baseline_gnn_hungarian` 且 `default_online_path_changed=false`。

验证结果：D2 `113 passed`，D6 `243 passed`，AirSim runtime `147 passed`，integrated point-mass `7 passed`。本批未启动 AirSim。

## 2026-07-15 D4 多入口二级接管 P0 边界关闭

| 范围 | 关闭内容 | 当前边界 |
|---|---|---|
| D4 owner | 新增统一 `SecondaryReadinessEvidence`/assessment；所有二级入口共同要求显式 episode time、有效 epoch/lease、新鲜 heartbeat/cue/communication、gimbal、coverage、network full-view 和持续 readiness | distributed interceptor peer 不套用二级视觉条件；真实 RF、时钟漂移、排队、乱序和重传仍为 P1 |
| main episode bus | communication tick 只消费上一完整 D4 decision，不读取当前帧尚未完成的仲裁结果；heartbeat-only、缺失、陈旧、未持续或同一节点租约冲突均不生成二级执行证据 | 本批只完成代码和确定性回归，没有启动新 AirSim episode |
| D6 metadata | 缺 current time 时 lease 视为 invalid，atomic commit 为 false；不得从默认时间或 heartbeat 推断可执行接管 | 真实 multi-seed failover time 与网络负载分布仍待采集 |

验证结果：D4 `278 passed`，AirSim runtime `147 passed`，integrated point-mass `7 passed`。专项正反测试同时证明 heartbeat-only 不可执行、完整 readiness 可接管、冲突 lease fail-closed。

## 2026-07-15 Runtime 分阶段延迟可观测性 P1 实现缺口关闭

| 范围 | 已关闭内容 | 当前边界 |
|---|---|---|
| main bus 内层 | `main-stage-timing-v1` 按 frame 保存 communication、D1、D2、D6 track recording、D3、coalition commit、D5、D4、D7 和 link/cross-view recording；输出 `main_episode_bus/stage_timings.jsonl` | 只测 main bus 内部，不包含 AirSim frame sample 和控制 RPC |
| SimpleFlight 外层 | `control-tick-stage-timing-v1` 保存 AirSim frame sample、bus processing、control evidence/pair sync、guidance/control RPC 和 control tick total；输出 `control_tick_timings.jsonl` | 外层包含 bus processing，禁止与 bus 内层总耗时相加 |
| availability/error | 使用单调 `perf_counter`；未执行阶段为 `not_applicable + null`，异常保留已完成/失败阶段耗时；记录 total、measured sum、unattributed、budget 和 error | 历史 artifact 没有新 JSONL 时保持 unavailable，不从旧 loop total 反推阶段 |
| D6 正式消费 | 严格校验 schema/scope、顺序、时间、非负有限值、状态/数值一致性、总和和 budget flag；独立汇总阶段 mean/P95/max、dominant stage 和预算违例，输出 CSV/JSON/中文 Markdown/PNG；P1 schema 升为 v5 | 关闭代码和报告能力，不证明 100 ms 已达标 |
| 兼容验收 | 真实 2v2/M5N2 seed-1 旧产物分别生成兼容报告，两层均正确显示 `stage_timing_artifact_missing` | 下一步必须重新运行同配置真实 AirSim multi-seed 才能得到实际 dominant stage |

兼容报告位于 `research_modules/d6_evaluation_metrics/outputs/p1_stage_timing_legacy_compat_20260715/`。本批没有启动 AirSim，没有修改 D1-D7 算法，也没有修改 D7 PN/PNG/LOS/外推公式。旧证据中的 2v2/M5N2 `123.3/384.6 ms` 和 231 次违例仍是总量基线；性能达标继续为开放 P1。

## 2026-07-14 D6 Target-State Freshness/Stale P1 证据链关闭

| 范围 | 已关闭内容 | 当前边界 |
|---|---|---|
| canonical actual evidence | 从 source-hash 已验证的最终 `control_commands.csv` 逐行校验控制时间、量测时间、到达时间、量测年龄、stale 和状态来源；缺列、非有限值、负值、时间逆序、age 冲突、非法布尔或空来源全部 fail closed | 不从 main diagnostics 或默认值回填；历史缺字段 artifact 保持 unavailable |
| 两例真实源重建 | 2v2 为 48 samples，mean/P95/max=`0.0375/0.2/0.2 s`；M5N2 为 608 samples，mean/P95/max=`0.091118/0.2/0.2 s`；两例 stale 均为 0，来源均为 `d2_estimated_global_track` | 只关闭 seed-1 schema 和证据注册；同配置多 seed 分布、100 ms 性能预算和异常 stale 正例实测仍为 P1 |
| 正式报告 | case、pooled aggregate、CSV、JSON 和中文 Markdown 均输出 freshness/stale availability、样本数、年龄分布、stale 数量/比例和来源分布；五层正式证据为 contract/control/terminal-switch/mode/physical=`102/26/26/2/4` | 完整 P1 suite 仍因缺 paired/dropout/multi-seed 保持 fail，不能误写为整体通过 |

正式报告位于 `research_modules/d6_evaluation_metrics/outputs/p1_actual_target_state_freshness_20260714/d6_acceptance/P1_UNIFIED_ACCEPTANCE_REPORT.md`。D6 `216 passed`，D5 文档同步回归 `261 passed`，D7 文档同步回归 `188 passed`；本批未修改 D7 PN/PNG/LOS/外推公式。

## 2026-07-14 Actual-Execution 真实 AirSim P0 复验关闭

| 场景 | Canonical evidence | 物理结果 | 计划/安全证据 | 当前判定 |
|---|---|---|---|---|
| tuned 2v2 seed-1 | actual v2 `available`，无 unavailable artifact | pair/target `2/2`，最小距离约 `4.98/4.89 m` | command/actual/history plan ID 一致；identity/state online truth `0/0` | P0 通过；`png_ttc` 多 seed 仍为 P1 |
| M5N2 seed-1 | actual v2 `available`，无 unavailable artifact | active pair `2/3`，target `2/2`，coalition `0/1`；第二 primary 最近约 `11.02 m` | command/actual/history plan ID 一致；identity/state online truth `0/0` | P0 证据链通过；第二 primary 与联盟性能仍为 P1 |

D6 联合报告位于 `research_modules/airsim_runtime/outputs/p0_actual_v2_validation_20260714/d6_acceptance/P1_UNIFIED_ACCEPTANCE_REPORT.md`；新增 freshness/stale 重建报告位于 `research_modules/d6_evaluation_metrics/outputs/p1_actual_target_state_freshness_20260714/d6_acceptance/P1_UNIFIED_ACCEPTANCE_REPORT.md`。其中 `actual_execution_all_available=true`；总 P1 suite 仍为 fail 是因为本批只运行两项 P0 smoke，没有 baseline/candidate 配对、1-5 帧 dropout 全矩阵和多 seed，不能误写为完整 P1 验收通过。2v2 loop latency 约 `123.3 ms`、M5N2 约 `384.6 ms`，性能预算违例合计 `231`，继续列 P1。actual v2 已正式独立提供 contract/control/terminal-switch/mode/physical 五层证据，并从最终 CSV 重算 freshness/stale；不从 `control_allowed` 或默认值回填。

## 2026-07-14 D6 Actual-Execution 计划来源 P0 关闭

| 范围 | 关闭内容 | 验证与剩余边界 |
|---|---|---|
| D6 canonical evidence | actual envelope v2 严格保存 `plan_ids`、正整数 `plan_versions`、`owner_node_ids` 及 availability/source/semantics；缺列、空计划、坏版本、同一 plan 混合版本及二级/分布式有效控制缺 owner 均 fail-closed | D6 `184 passed`；安全计数、physical provenance 和实际视觉切换语义未放宽 |
| D6 merge | merge v3 清除 replay 中同名计划来源，只接受通过 source hash 和结构校验的 actual envelope metadata | 中心重规划与二级接管两个原失败场景均已通过 |
| main integration | actual artifact 仍由 main 在三份最终执行源写盘后生成和注册；最终 metrics 保留实际计划来源及两个在线真值安全计数 | AirSim runtime `142 passed`；P1 terminal/integrated/dry-run `17 passed`；`git diff --check` 通过 |

该代码级结论已由上节真实 2v2/M5N2 seed-1 复验补强。更早历史 output 不追溯升级；后续多 seed 必须生成新的 v2 artifact。

## 2026-07-14 第二批 P1 代码闭合与 main 接线

| 范围 | 已闭合代码项 | 仍开放 P1 证据 |
|---|---|---|
| D3/main | 当前 tick 成本口径、窗口累计变更预算、canonical history 写盘 | 同几何至少 10 seeds 下 churn、未分配高威胁率、reserve demotion 与 D2 生命周期准入 |
| D5/main | 稳定 camera/stream/backend/local-track 历史，committed primary 与 duplicate risk 接线 | M5N2 第二 primary 获取/锁定，30/50 m recall，YOLO/ByteTrack/BoT-SORT 至少 10 seeds 准入 |
| D7/main | raw gate、latch、effective contract/control、termination snapshot 和 dropout scope；终止行不再复用历史 latch | truth-isolated 2v2/M5N2/dropout 同 seed 物理复跑、range/closing speed/机动/3D 标定 |
| D6/main | terminal metric envelope、物理分母、性能样本、D3 history 和 suite/case 报告入口 | 跨 case/multi-seed 长期聚合、约 1.3 s loop latency 与预算违例根因、显著性和趋势治理 |

本批没有运行真实 AirSim，历史 postfix seed-1 的 M5N2 `0/3 pair`、`0/2 target`、`0/1 coalition` 和 2v2 最近距离约 `7 m` 仍只是修复前诊断证据，不能用于宣称第二批 P1 性能闭合。

## 2026-07-14 D1 Covariance 与 D4 二级证据完整性 P0 关闭

| 范围 | 关闭内容 | 验证与剩余边界 |
|---|---|---|
| D1 covariance contract | online fusion、online replay、governed bundle 和 AirSim freeze 统一校验 measurement/covariance 维度、有限性、对称性和半正定性；缺失/非法矩阵不再静默修复 | D1 `92 passed`。显式 offline legacy migration 保留，但必须写原始缺失原因、model/default/参数和 offline-only provenance；真实传感器标定与多 seed NIS/NEES 仍为 P1 |
| D4 secondary evidence | 缺 current time、heartbeat、cue freshness、gimbal、communication summary 或 network full-view 均不可达到 `takeover_ready`；lease 继续严格要求 `current_time < expiry` | D4 `224 passed`。完整正例和中心/二级/distributed 顺序保持；真实网络、时钟漂移、排队/乱序/丢包和自主联盟重构仍为 P1 |
| main integration | 质点集成场景显式生成二级视频/数据链 `CommunicationSummary`，不通过恢复 fail-open 兼容旧 fixture | integrated point-mass/contracts `10 passed`；AirSim runtime `134 passed` |

本批没有启动真实 AirSim。历史缺字段 replay 只能作为 legacy/unavailable 证据，不能用于证明二级节点可执行接管。

## 2026-07-14 D5 Native MOT History P1 子缺口关闭

D5 owner 已修复真实 Ultralytics `Results.boxes.id` 路径：原生 ByteTrack/BoT-SORT 的
`mot_history_length` 不再每帧固定为 1，而是按
`(resource_id, camera_id, tracker_backend, native_tracker_id)` 累计连续实测命中。同一 ID
连续帧从 1 增长到 2 及以上；ID 变化、任一空帧、backend 切换、原生模型重建、stream reset
和 episode reset 都从 1 重新开始。短时消失的 ID 状态可在 `max_track_age_frames` 内保留供
tracker 审计，但 coast 不计入连续实测历史，长期复用 ID 不能直接满足锁定门限。

该修复没有降低 `min_mot_history`，没有放宽 friend/duplicate/version/timestamp/calibration
gate，也没有创建或换绑 `global_track_id`。Results-like 专项为 `41 passed`，D5 全量
`241 passed`，AirSim runtime YOLO/MOT focused `10 passed`，runtime 全量 `130 passed`。
本项只关闭代码级 P1；真实 AirSim/真实图像的远距召回、IDSW/continuity、P95 延迟、失败回退
和 M5N2 第二 primary 稳定锁定仍开放。

## 2026-07-14 D4 Lease 与 D6 Physical Completeness P0 关闭

本批由 D4 owner 将 secondary resource 候选、secondary plan 发布/维持、active secondary owner
和 D7 handoff 统一到同一严格租约判据：expiry 与当前 episode time 必须同时存在，且严格满足
`current_time < lease_expiry`。缺 expiry、缺 current time、`current_time == lease_expiry`、过期、
旧 epoch 和 source mismatch 均不可执行；active secondary owner 的 lease 失效时进入
`hold_review`，不保留过期执行权。D4 全量 `211 passed`。

D6 owner 在既有 physical provenance gate 上继续补齐结果和联盟完整性：每个 active pair
必须存在显式 `physical_success` 或规范 scorer 终态；required-primary 持久化成员不足、缺到达
窗口、缺 denominator，或 summary 声明 opportunity 但缺 completion 时，coalition 指标保持
unavailable；证据完整的显式失败仍保持 available `0`。CSV、JSON 和 Markdown 使用同一
availability/reason。D6 全量 `150 passed`，仅有既有 Matplotlib 3D 后端环境 warning。

main 只修正合法跨模块 fixture：integrated simulation 与 AirSim runtime 的 secondary 资源和
plan 现在显式携带 heartbeat、lease epoch/expiry 和 episode time，没有放宽 D4。验证结果为
AirSim runtime `130 passed`、integrated point-mass `7 passed`、D7 `178 passed`。本批未运行
新的真实 AirSim episode；真实同 seed AirSim 重跑仍是 P1 证据任务。

## 2026-07-14 D6 Physical Provenance P0 关闭

只读复核曾发现 D6 在 summary 宣称物理证据可用、但缺逐 pair summary 时，仍可能从
`control_commands.csv` 回退生成物理 pair；同时没有逐 active pair 校验
`target_state_source` 与 episode 的 `online_control_state_source`。该缺口会把证据缺失或
来源冲突的结果误标为物理成功，因而按评估级 P0 处理。

本批由 D6 owner 完成修复：物理指标必须同时具备 intercept summary、持久化 pair summary、
每个参与 pair 的 `physical_evidence_available=true`、可判定 physical result 和一致的状态来源。
command-only、summary-only、缺证据、缺结果或来源冲突全部 fail closed；required-primary 成员、
到达窗口、denominator 和 completion opportunity 也必须完整。合法 offline scorer、显式 truth
fixture 和证据完整的显式失败正例保持。运行结束后的 generic `active=false` 不再被误解为
assignment inactive，standby reserve 仍排除。验证结果为 D6 `150 passed`、AirSim runtime
`130 passed`、integrated point-mass `7 passed`，`py_compile` 与 `git diff --check` 通过。该修复
关闭代码级 P0，不替代真实同条件 multi-seed AirSim P1 复验。

## 2026-07-14 在线真值隔离 P0 复核

| 范围 | 当前状态 | 判定与下一验收 |
|---|---|---|
| D1 AirSim 观测入口 | 已移除 actor/object/truth 身份；EO 使用真实 detection bbox；雷达/声学/LiDAR 作为传感器仿真可由场景真值生成带噪量测，但生成后的在线 DTO 不携带目标身份 | 已关闭；改名不改变在线 observation，D1 `83 passed` |
| D1 arrival queue | 量测只在 `arrival_timestamp <= episode clock` 时进入融合；尚在传输中的量测可写 governed replay，但不得提前更新状态 | 已关闭；未来量测不提前消费，main runtime `124 passed` |
| D2/D6 truthless 语义 | D2 在线策略拒绝 truth/actor/object 字段；无完整 truth 配对时 RMSE、continuity、IDSW 保持 `None/unavailable`，不再伪造 0 | 已关闭；D2 `98 passed`，D6 `137 passed` |
| 离线 integrated replay | 离线 runner 显式使用 `TrackerTruthPolicy.OFFLINE`，与真实 main episode bus 的 `ONLINE` 策略分离 | 已关闭；integrated `7 passed` |
| SimpleFlight 在线控制状态 | 默认、主动中心重规划和主动二级接管统一消费 D2 `target_estimate`；合同覆盖只修改 plan/version/owner/D4/D5 状态，目标状态与 actor alias 不可注入；无估计/陈旧估计 fail-closed | **P0 closed**。actor truth 扰动不改变命令，在线 state use 为 0，actor truth 只进入运行后离线 NED 三维 5 m scorer；AirSim runtime `130 passed` |

关闭后的边界仍需保持：`truth_identity_online_use_count=0` 与
`truth_state_online_use_count=0` 必须分别成立；历史缺少 state provenance 的物理结果仍只作
迁移前 smoke/离线证据。同 seed 真实 AirSim 复跑属于 P1 性能与证据验收，不回退为 P0
代码断链。

## 2026-07-14 第二批 P1 修复：D3 有序历史与 D6 churn

| 范围 | 本批实现 | 验证与剩余边界 |
|---|---|---|
| D3 canonical history | 新增 `d3_plan_history_record_v1`，每个 planning tick 保存顺序索引、时间、plan/version/window、owner/epoch/lease、primary/reserve active 状态、联盟成员、迟滞、反馈分类和成本；递归排除 truth 字段 | D3 `149 passed, 1 skipped`；D3 owner 已同步 README/PLAN/GAP/算法和实验文档 |
| main episode bus | 每次实际规划调用只生成一条 history；非规划 frame 不重复；独立写出 `main_episode_bus/d3_plan_history.json`，tick 仅在本帧发生规划时携带记录 | focused end-to-end 测试已覆盖 3 planning ticks、稀疏 planning frame 和 truth 隔离 |
| D6 canonical consumer | 严格校验 wrapper/record schema、record count、sequence 唯一单调、ordering key 和 timestamp；按相邻 assignment 集合计算 membership churn，不累加重复审计事件 | D6 `132 passed`；乱序、重复索引、单记录均为 `unavailable` |
| D6 新指标 | `primary_membership_change_count`、`reserve_membership_change_count`、`owner_change_count`、`soft_feedback_count`、`hard_feedback_count` 和四项 churn 正式可用 | AirSim runtime `122 passed`，integrated point-mass `7 passed` |

本批完成的是证据链和离线算法验收，不是新的物理性能证据。修复前 M5N2 `5/10` 仍为当前真实基线；下一步必须在相同 20 m/3 s/40° 几何、相同 seeds 1-10 下复跑，比较 plan/member churn、第二 primary 锁定和 coalition completion。

## 2026-07-14 第一批 P0/P1 修复

本批继续采用“main 下发、D3/D5/D6 owner 自改自测、main 只处理运行时桥接和集成回归”的流程。

| 范围 | 本批修复 | 验证与当前边界 |
|---|---|---|
| D6 评估级 P0 | 最终快照、空输入和单条无序记录不再推断 plan/coalition/epoch/membership churn 为 `0`；只有显式计数或至少两条有序历史才可计算 | D6 `120 passed`；P0 已关闭。真实逐 tick D3 history 仍为 P1 |
| D5 反馈语义 | 普通 ambiguity/hold/reacquire 保持视觉不确定性；verified friend、spoof、duplicate 和 assignment conflict 保持硬冲突 | D5 `235 passed`；没有放宽 D7 当前 pair 的视觉切换门控 |
| D3 写回与迟滞 | 普通视觉不确定性改为 resource-target edge-soft，不再把整架资源设为 `operator_hold`；硬身份/重复/显式可行性冲突继续 fail-closed；soft feedback 不再绕过 `min_dwell` | D3 `144 passed, 1 skipped`；40-case 高 churn 仍只是根因线索，需要同输入复跑证明效果 |
| main episode bus | 输出显式 `feedback_constraint_class`；stale/unverified identity 保持 soft，verified/spoof/duplicate 保持 hard；standby reserve 的 D6 `AssignmentRecord.active=False` | AirSim runtime `121 passed`，integrated point-mass `7 passed` |

本批没有修改 D7 PN/PNG 公式，也没有启动新的 AirSim 物理 episode。M5N2 `5/10` 是修复前基线，必须用同几何、同 seeds 复跑后才能判断计划抖动和第二 primary 锁定是否改善。

## 2026-07-13 P1 收敛实测与统一验收

详细结果见 `subagent_reviews/MAIN_P1_CONVERGENCE_VALIDATION_REPORT_20260713.md`，统一 D6 证据位于 `research_modules/airsim_runtime/outputs/p1_convergence_20260713/d6_system_evidence/`。

| 范围 | 真实 AirSim/离线验收结果 | 当前判定 |
|---|---|---|
| D1/D2 dense crossing | 4 m 与 2 m 横向间距各 20 seeds，共 40 episode、10200 条 evaluator-only truth；在线 truth 泄漏 0。最佳 GNN 候选 IDSW `1.3583 -> 0.6167`，下降 54.6%，continuity `0.9810 -> 0.9840`，P95 24 ms | 未达到冻结的 continuity `+0.10` 晋级条件；默认 GNN/Hungarian 不变，轻量 JPDA 不晋级 |
| D4 episode-time fault matrix | normal、center failure、center+secondary failure、0.5 s delay、30% loss、partition recovery，共 60/60 safety outcome 通过；false degradation、duplicate owner 均为 0 | episode-time 接管/原子 fail-closed 合同闭合；不等同真实 RF/网络验证 |
| M5N2 cooperative closure | 10 seeds、baseline + 3 个候选，共 40 episode；最佳 20 m/3 s/40 deg profile 为 `5/10`，其他为 `2/10`、`1/10`，baseline `0/10`；总体 `8/40` | 未达到 `8/10`。主要断点为 `d5_not_locked` 与 terminal detection acquisition timeout；继续列 P1 |
| D5 原生 MOT | 18 个 1920x1080 筛选工况全部 connected；20 m native active/continuity=1、IDSW=0，ByteTrack P95 约 7.4 ms、BoT-SORT 约 16.2 ms；30/50 m 无检测 | 20 m precision/recall 仅约 0.26-0.33，0 个候选准入，未启动 confirmation；默认 detect 不变 |
| 安全合同 | reserve unauthorized=0、global track rewrite=0、online truth use=0 | P0 安全门控保持 |
| D6 | 修正 profile 分组并展开 40 case、160 条 D5 和 164 条 D7 证据；合同/控制/模式/物理严格分层 | 统一 P1 证据入口闭合；缺失的 D3 时序 churn 保持 unavailable |

本轮还修正了 main-owned integrated point-mass 回归的旧断言：中心健康时，持续 D5 ID 不一致的正确动作是先请求二级辅助、再请求中心重规划，不直接转移计划 owner。该修正未改变 D4 模块策略。

统一回归结果：D1 79、D2 93、D3 139（optional OR-Tools 1 skipped）、D4 198、D5 232、D6 115、D7 178、AirSim runtime 124、integrated/dry-run 11，全部通过。matplotlib `Axes3D` 为本机依赖 warning，不影响本轮二维图表。

### D1-D7 PLAN/GAP 同步状态

2026-07-13 已由 D1-D7 owner 分别复核并更新各自 `research_modules/Dx_*/PLAN.md` 与 `subagent_reviews/Dx_IMPLEMENTATION_GAP_AUDIT.md`。本次同步只更新状态、证据和后续验收口径，没有修改模块算法代码。当前权威开放 P1 为：

| Owner | 当前开放 P1 |
|---|---|
| D1 | 真实漏检/虚警/遮挡/异步采样 fixture，区域时间窗和协方差长期治理 |
| D2 | 更长 OOSM/遮挡/杂波 replay、gate/risk 与 NIS/NEES 分档；当前候选不晋级 |
| D3 | 逐时刻 plan/coalition history、D5 feedback 权重/迟滞和动态 N/M 标定 |
| D4 | 真实带宽、时钟漂移、排队/抖动/乱序/重传与长期恢复统计 |
| D5 | 第二 primary 稳定获取、bbox 口径/尺度/时间对齐、30/50 m 召回和候选 confirmation |
| D6 | 长期 multi-seed 趋势、producer 逐时刻 schema 和跨批次失败原因治理 |
| D7 | 第二 primary 视觉 gate/acquisition、closing speed/range、三维几何和机动标定 |

P2 内容保持原计划，不因本次文档同步提前进入默认依赖或在线路径。

## 2026-07-13 远距雷达直接分配增量

详细实现与实测见 `subagent_reviews/MAIN_RADAR_DIRECT_ASSIGNMENT_AIRSIM_VALIDATION_REPORT_20260713.md`。main 已将正常 CV 场景的相机指向改为持续消费当前 D3 binding 和 D2 预测位置；`--cv-reassignment-time` 只作为显式压力注入。D4 新增末端视觉证据适用范围：约 50 m 雷达中段、中心正常、计划 current/feasible 且只有 D1/D2/D3 软风险时继续中心计划，不请求二级视觉辅助；高不确定度/陈旧量测、已观测 IDSW/duplicate、计划硬失效和 D5 身份冲突保持原强门控。

真实 2v2 复测为 14/14 `continue_center`、14/14 `radar_midcourse`、plan owner/version 全程 `center/v1`、owner mismatch=0。5v5 YOLOv8+ByteTrack 三 seed 为 105/105 `continue_center`、active degradation=0、在线 truth 违规=0，视觉平均处理耗时约 12.99 ms。P1 尚未关闭的是视觉效果准入：18 个相机-seed 流均因 episode 仅 8 个 warmup-inclusive 帧或召回不足未获 native MOT admission，第三主相机无稳定检测，200 m 二级相机离线召回约 0.08-0.09；后续需更长 episode 和视角/尺度/阈值校准，但不再作为远距中心分配的前置条件。

## 2026-07-12 P1 Cooperative/Identity 收敛增量

详细实施与实测报告见 `subagent_reviews/MAIN_P1_COOPERATIVE_AND_IDENTITY_CALIBRATION_REPORT_20260712.md`。

| 范围 | 已关闭缺口 | 当前开放 P1 |
|---|---|---|
| D1 | 真实 AirSim replay 冻结、governed schema、独立 truth sidecar、双时间戳/协方差/NED/lineage | 增加漏检、虚警、遮挡和不等采样率 fixture |
| D2 | 54 组固定矩阵、10/20-seed screening/confirmation、轻量 JPDA 同输入对照；真实 AirSim 证据分类修正 | 当前 crossing fixture 区分度不足，不能据 `IDSW=0` 关闭身份治理 |
| D3/D7 | 27 组 cooperative 候选、质点预筛、滚动兼容版本保持视觉滤波历史；PN/PNG 公式未改 | top-3 至少 10 seeds；第二 primary 可达性和同步窗口仍未闭合 |
| D4 | binding 与视觉 readiness 解耦；arbiter 按 pair 隔离；六类通信 replay 60/60 | 真实通信时序和二级/peer 联盟继续多 seed |
| D5/main | 有 local track 的 596/596 条记录携带有效 typed camera geometry；无 truth 回填 | 同步双 primary 锁定、候选 margin 和失锁恢复仍需标定 |
| D6/main | cooperative/dense crossing 中文报告、曲线和 D3-D7 evidence manifest | 长期趋势、难度分层和 10-seed cooperative 汇总 |

本轮四个 35 s M5N2 case 全部 connected。D4 错误 `d4_terminal_inconsistent` 已降为 0；D6 active-primary 漏斗为 assigned/visible/associated `12/12`、contract `2/12`、control `0/12`、physical `1/12`，coalition completion `0/4`。12 s 稀疏 binding 专项中 `d4_owner_missing=0`。因此当前无新增 P0，但 M5N2 协同物理闭环仍是最高优先级 P1。

真实 CV dense crossing 20 seeds 中默认 GNN 的 IDSW=0、identity/coverage continuity=1.0、false track=0、RMSE 约 0.164 m、P95 约 3.7 ms；轻量 JPDA 指标无改善且 P95 约 4.7 ms，`promotion_recommended=false`，默认 GNN/Hungarian 不变。

### 2026-07-12 独立主资源、原生 MOT 与运行时失效接线

本轮不再研究同时到达。高威胁目标继续采用 `2 primary + 1 reserve`，但两个 active primary 使用 `terminal_authorization_scope=per_primary`、`arrival_coordination_required=false`，分别通过 D3/D4/D5/相机质量/机动余量门控，并分别按 NED 三维 5 m 判断物理成功；reserve 仍为 standby，未激活不得切换视觉 PNG。PN、`png_vm`、`png_ttc` 公式均未修改。

| 范围 | 本轮关闭的实现缺口 | 仍开放的 P1 |
|---|---|---|
| D3/main/D5/D7 | 同名授权字段已贯通 demand、plan、D5 Assignment、D7 binding 和 SimpleFlight topology；纯成本/诊断刷新不再推进 plan id/version/coalition epoch | 需真实 M5N2 多 seed 复跑，确认每个 primary 的 contract/control/mode/physical 四层结果 |
| D4/main | AirSim frame 时钟驱动 center/secondary/peer heartbeat、ACK、lease、epoch、owner；无可执行 owner、分区、reconfiguring 时 fail-closed 阻断视觉 PNG | 需真实 center failure、center+secondary failure、missing ACK 多 seed episode |
| D5/main | ByteTrack 与 BoT-SORT 原生准入监测接入真实帧；truth RPC 严格在 online result 之后，IoU fallback 不可准入 | 需实际运行 18-case screening 和每后端 10-seed 双相机 confirmation |
| D2/main | 六 difficulty profile 不再只换标签；dropout 删除量测、clutter 注入匿名虚警、delayed/noisy 增加延迟并放大协方差；2 m tight geometry 必须真实捕获 | 需采集 4 m nominal 与 2 m tight 各 10/20 seeds 并完成阈值治理 |
| D6 | 新增统一 P1 evidence CSV/JSON/中文 Markdown/PNG，分离 contract/control/mode/physical，汇总 D2-D5/D7 availability | 需用真实 AirSim 产物填充全部 source，当前代码回归不能替代实测结论 |

本轮代码级回归已覆盖 main runtime、跨模块合同和 D1-D7 模块测试；原生 MOT 与新的多 seed AirSim 矩阵尚未实际启动，因此不得把“接口闭合”表述为算法已晋级。默认在线检测/关联主线继续保持 AirSim detect 与 GNN/Hungarian，ByteTrack/BoT-SORT 只有达到准入阈值后才进入主线评审。

后续真实预检已完成 20/30/50 m 距离矩阵和 20 m、102 帧单相机确认。20 m 下 ByteTrack/BoT-SORT 均达到 native active=1、continuity=1、IDSW=0、fallback=0，P95 分别约 8.29/18.23 ms；30/50 m 均无检测。20 m 使用 AirSim detect 框做 IoU=0.5 post-online 评分时 precision/recall 仅约 0.29-0.32，因此两者均未通过准入。P1 开放项已从“原生 MOT 未运行”细化为：30/50 m 小目标检测召回、YOLO/AirSim bbox 口径与 IoU 多阈值标定、之后再运行完整 confidence 和多 seed 矩阵。

## 2026-07-12 P1 Terminal Closure 10-Seed 结果

main 使用 `p1-terminal-closure-v1` 运行 80 个 reset-separated episode，全部 connected，默认不保存 PNG。执行索引为 `research_modules/airsim_runtime/outputs/p1_terminal_closure_10seed_20260712/p1_terminal_closure_summary.json`，D6 中文报告和曲线位于同目录 `d6_unified_acceptance_full/`。

| 范围 | 实测结果 | 当前 GAP 判定 |
| --- | --- | --- |
| M5N2 baseline | active-primary `7/30`，target `7/20`，coalition `0/10` | 物理协同未闭合 |
| M5N2 candidate | active-primary `4/30`，target `4/20`，coalition `0/10` | 相对 baseline 退化，soft/trend 不得晋级默认 |
| 1-5 帧 dropout | 物理 100/100；1 帧预测 9/10，2 帧 10/10；3-5 帧各 10/10 命中 0.25 s 硬过期 | 矩阵完整但为 49/50；seed 2 单帧注入/锁定时序仍需复核 |
| 2v2 `png_ttc` | 10 seeds、pair/target `20/20`，115 个 control-allowed sample；not-expanding 13、TTC out-of-range 22 | 真实多 seed 主链闭合；area-jump/clipping 受控拒绝覆盖仍开放 |
| Truth/ID 安全 | 80 episode online truth use=0；D5 deterministic 10/10，global ID rewrite=0 | P0/P1 安全合同保持 |
| D2 long replay | 10 seeds，IDSW 均值 138.1，continuity 0.694，false track 均值 5.4，RMSE 0.307 m | 校准链路闭合，但默认 GNN 风险阈值未通过 |
| D3 matrix | 8/8 full/incremental 等价；仅 1/8 使用局部增量，7/8 安全回退 | 正确性闭合，增量收益仍需真实事件校准 |
| D4 matrix | 9/9 通过，误降级 0，五个负例 fail-closed | 确定性扰动矩阵闭合；真实通信时序仍开放 |
| D6 | D1-D5/main 证据 available；四层和 pair/target/coalition 分离 | 统一离线验收入口闭合 |

当前最急 P1 已从“缺少 paired 数据”转为：M5N2 第二 primary/联盟物理闭合、D2 dense crossing ID 连续性治理、真实二级通信时序、真实相机同步/YOLO-MOT 标定，以及 `png_ttc` 剩余两类受控拒绝覆盖。

## 2026-07-12 PNG delivery 增强与实测状态

本轮由 main 下发、D5/D6/D7 分别实现并自测，main 只负责 AirSim runtime 接线、真实运行和汇总。详细报告为 `research_modules/airsim_runtime/outputs/PNG_DELIVERY_ENHANCEMENT_AIRSIM_VALIDATION_REPORT_20260712.md`，D6 结构化对照包位于 `research_modules/airsim_runtime/outputs/png_delivery_enhancement_eval_20260712/`。

| 范围 | 当前状态 | GAP 判定 |
| --- | --- | --- |
| D7 图像 KF 生命周期 | 已按 resource/global/local track 与 plan owner/version 隔离；切换即重置，漏检不伪造身份切换 | P1 实现闭合，保持跨 ID/version/friend/duplicate 回归 |
| D7 `png_ttc` | 已加入 delivery 等价面积 EMA、窗口斜率、跳变/裁剪/TTC 范围拒绝；`png_vm` 不变 | P1 实现闭合，真实 `png_ttc` 多 seed 标定仍开放 |
| soft prediction / trend coast | 默认关闭；candidate profile 显式开启，预测上限 0.25 s，trend 仅水平且不超过 0.75 m/s | P1 optional 能力闭合，不晋级默认 profile |
| D5 证据合同 | 已输出双时间戳、local-track transition、MOT history、bbox clip、相机内外参和姿态有效性；truth ID 在线使用禁止 | P1 合同闭合，真实标定误差/姿态同步长期校准开放 |
| D7 6D LOS KF | 仅离线 replay，兼容 direct `camera_to_ned_rotation` 或分解旋转；字段缺失明确 unavailable | P2 optional，不替换在线 EMA/滑窗 |
| D6 指标 | 已增加滤波状态、TTC 拒绝、soft/coast、命令跳变及 contract/control/mode/physical 分层报告 | P1 指标闭合 |
| 真实 2v2 | candidate 10 seeds 为 20/20 pair 在 5 m 内成功，在线 truth=0；旧基线为 19/20 | 达到本轮非退化验收，但自然场景未触发 soft/trend，不能据此宣称增强算法贡献 |
| 锁定后 dropout | 2 帧均为 `image_kf_predict`，2/2 物理成功，未发生跨身份 coast | 有界预测真实链路闭合 |
| M5N2 | 8 s 短窗口 3 seeds 为 0 成功，最近距离 22-32 m；出现 soft prediction 4、innovation reject 2、truth=0 | 与既有 z=-30 m/35 s 高净空基线不等价；P1 仍是第二 primary 中段闭合和联盟视觉一致性，不归因于 PNG 滤波 |

统一回归：D4 148、D5 161、D6 84、D7 137、AirSim runtime 98、质点集成 7、dry-run 4、跨模块合同 3，全部通过。当前没有新增 P0；仍需用同一高净空 M5N2 几何和相同运行窗口做 paired baseline/candidate，才能决定 soft prediction 或 trend coast 是否进入默认 AirSim profile。

## 2026-07-11 P1 收敛实施后历史检查点

完整中文报告和结构化证据位于 `research_modules/airsim_runtime/outputs/p1_p2_validation_20260711/P1_P2_VALIDATION_SUMMARY_CN.md`。本节保留 2026-07-11 当日状态；当前权威状态以前文 2026-07-12 小节和第 7 节为准。

| 范围 | 实施与验证结果 | 当前判定 |
| --- | --- | --- |
| D1/D2 replay 与 truth 隔离 | D1 输出带 schema、双时间戳、协方差、lineage 的 governed replay；D2 只从独立 offline truth label 评分 | P1 合同闭合，继续补充更长真实 replay 校准 |
| D3 动态规划 | 增量规划、短时 feedback dwell、primary 角色保持和 N/M 非等量合同已实现 | P1 合同闭合，真实阈值仍需多 seed 调参 |
| D4 联盟接管 | 二级节点和完全分布式三成员联盟均达到 `executing`、ACK 3/3；缺 ACK 为 2/3、状态 `aborted` | P1 原子 commit/ACK/epoch/lease 正负例闭合 |
| D5/D7 协同末端合同 | CV 10 seeds 中 8/10 达到 T001 双 primary 视觉共识并授权；10/10 IDSW=0、错误重复锁=0、global ID 改写=0 | 达到本轮 8/10 合同验收；两个失败 seed 保留为鲁棒性回归 |
| D6 结果语义 | 已分离 `contract_allowed`、`control_allowed`、`mode_switched`、`physical_intercept`，ComputerVision 的物理命中为 unavailable 而非 0 | P1 指标口径闭合 |
| SimpleFlight 物理拦截 | runtime 默认成功半径已由 0.75 m 改为 NED 三维 5.0 m；pair/target/coalition 分层统计已接入；首次无锁使用 acquisition grace，已锁定后按 `image_kf_predict -> blind_push -> expired/reacquired` 处理 | 2026-07-11 时 P1 代码与接口闭合、实测待重跑；已被 2026-07-12 的 2v2 20/20 与 M5N2 paired 开放项更新 |
| D5 在线视觉链 | 默认继续使用 `simGetDetections` bbox；controlled intercept 已取消 `object_id == target_id` 选框和模拟锁定，改为消费 episode bus 的匿名 local track 与几何 `TerminalAssociation` | P1 truth 隔离和接线闭合；YOLO 数据集标定后置 |
| P2 可选对照 | D1 FilterPy/Stone Soup、D2 GNN/JPDA/MHT、D3 OR-Tools capacity、D4 coalition replay、D5 OpenCV PnP、D6 py-motmetrics、D7 3D/APN/FRPN 均按 available/unavailable 口径隔离运行 | 仅 benchmark；不进入默认 requirements 和在线控制路径 |

本轮统一回归结果：D1 62、D2 67、D3 123（1 skipped）、D4 144、D5 155、D6 82、D7 117、AirSim runtime 90，均通过。唯一 D3 skip 为未安装 optional OR-Tools；PNG delivery 核心公式未修改。

### P1/P2 模块边界复核

| Owner | P1 当前状态 | P2 当前状态 | 默认路径是否替换 |
| --- | --- | --- | --- |
| D1 | governed replay、truth policy 和融合合同完成；真实长 replay、CI/阈值长期标定开放 | 冻结 replay benchmark 已实现；当前环境 FilterPy/Stone Soup unavailable，显式给出原因 | 否，仍为 NumPy EKF/fixed-lag |
| D2 | D1 adapter、offline truth、N-target synthetic dense calibration 完成；真实长 replay 开放 | GNN/JPDA/MHT 同 replay 对照完成；FilterPy/Stone Soup 对象 adapter 不提供身份指标 | 否，仍为 GNN/Hungarian |
| D3 | M-to-N demand-slot、增量规划、role-aware primary 和 commit/current-binding 合同完成；动态非等量长期标定开放 | capacity benchmark 已实现；当前 OR-Tools unavailable 并显式报告原因 | 否，仍为 SciPy Hungarian/demand-slot |
| D4 | secondary/peer commit、故障矩阵和 member loss/replacement replay 完成 | 原生 6 场景 replay 完成；MIT/CA-CBBA 未配置或未集成时显式 unavailable | 否，仍为本地轻量 CBBA/原子 commit |
| D5 | detect-first 匿名 local track、几何锁定、预测/丢失不锁定和 runtime record 完成；真实多 seed 标定开放 | OpenCV calibration/PnP 离线 benchmark 完成；YOLO/ByteTrack 数据集标定 deferred | 否，在线默认仍为 AirSim detect 与保守门控 |
| D6 | pair/target/coalition、四层结果语义和 detect/coast 诊断完成 | py-motmetrics 可选；HOTA/TrackEval 依赖不足时保持 unavailable | 否，仍为本地 D6 指标主线 |
| D7 | commit-aware gate、N/M topology、有界 KF/coast 外推和 SimpleFlight consumer 接线完成；真实长时标定开放 | 3D PN、True PN、APN、FRPN 仅离线 benchmark；FRPN 是研究近似 | 否，仍为既有位置 PN/视觉 PNG |

## 2026-07-11 P1 收敛实施前基线

真实 AirSim ComputerVision 证据目录为 `research_modules/airsim_runtime/outputs/blocks_cv_m5_n2_liveness_*_20260711/`，中文汇总为 `M_TO_N_AIRSIM_CONVERGENCE_REPORT_CN.md`。该目录属于生成输出，不作为在线真值源。

| 核查项 | seeds 7/17/27 结果 | 当前判定 |
| --- | --- | --- |
| 中心重规划 lifecycle | 每 seed 6 request、6 no-change ACK、0 applied、0 expired，收敛 0.5 s | P1 状态闭环已完成，保持回归 |
| M-to-N 需求槽 | satisfaction=1.0、unmet=0、错误重复锁=0 | 中心化 demand-slot 与合法多锁已完成 |
| T002 单 primary | 共识帧 4/5/4，每 seed 2 次 D7 终端合同许可 | D3-D5-D7 k=1 链路已闭合 |
| T001 hybrid 2+1 | 双 primary 共识帧均为 0 | P1 未闭合；不得宣称协同末端完成 |
| 二级/无中心 k>1 | 当前 `coalition_fallback_unsupported` 并 fail-closed | P1 待实现 ACK/commit/epoch/lease 原子联盟 |
| 物理拦截 | ComputerVision 不执行 SimpleFlight 控制 | P1 待 90 s、10-seed SimpleFlight 验证 |

实施前统一回归基线：D1 54、D2 57、D3 104（OR-Tools 1 skip）、D4 121、D5 127、D6 68、D7 84、AirSim runtime 75、质点集成 7、跨模块合同 3，均通过。D1-D7 owner 已先行同步各自 PLAN/GAP/review；后续能力变化后必须由同一 owner 再次回写实际状态。

## 2026-07-11 M 对 N 协同拦截调研增量

D1-D7 已分别完成高威胁目标 \(k_j=3\) 的文献、开源实现和模块边界审计，main 汇总见 `subagent_reviews/MAIN_M_TO_N_COOPERATIVE_INTERCEPTION_SYNTHESIS.md`。

以下表格保留 2026-07-11 实施前的调研基线，用于解释任务来源；其状态已被后文“中心化 M 对 N 实施闭环”取代：

| Owner | 实施前 P1 新缺口 | 实施前边界（历史） |
| --- | --- | --- |
| D1/D2 | 多平台共同估计时刻、几何质量、跨节点 track registration、公共信息谱系和 CI | 当前有双时间戳、协方差、GNN/Hungarian 和中心 ID 基础，无协同 Track-to-Track 全链路 |
| D3 | target demand、b-matching/flow、联盟原子激活、角色、同步/波次和版本 | 实施前 Hungarian 仍是一对一 |
| D4 | coalition commit/ACK/lease、缩编/补位/重组、分区和恢复 digest | 当前 CBBA 是单 winner，不支持原子 \(k_j>1\) |
| D5 | planned cooperative lock、over support、多视角几何质量和联盟时序 | 当前多资源同目标可能仍被旧 duplicate 语义误判 |
| D6 | 需求满足、联盟形成、到达离散、波次、协同定位一致性和安全统计 | 需在现有 EpisodeMetrics 上新增 M 对 N 口径 |
| D7 | cooperative 与 independent pair 边界、到达窗口、终端扇区、最小间距和成员退出 | 当前仅有任意 N 个独立 PN/PNG pair |

建议默认研究比较 hybrid 2+1、simultaneous 3、sequential 1+1+1 和 independent PN。只有完成上述合同后才能启用 \(k_j>1\)；否则 D3/D4/D5/D7 断链会成为该新增场景的 P0 blocker。

### 2026-07-11 中心化 M 对 N 实施闭环

上述新增场景的中心化 P0 合同已经闭合，原调研表中的“当前仍是一对一/尚未实现”不再代表当前代码状态：

| Owner | 已完成 | 仍保留的 P1 |
| --- | --- | --- |
| D1 | 2..N bearing-ray 定位、共同估计时刻传播、协方差膨胀、CI 和 lineage 去重 | 真实 AirSim 多视角观测接线与几何阈值标定 |
| D2 | `SourceTrackSummary`、公共时刻马氏/Hungarian 注册、canonical registry、跨节点 ID 指标 | 真实 5v5 replay 与 D1 CI 请求闭环标定 |
| D3 | schema v2、`TargetDemand`、demand-slot Hungarian、all-or-none admission、hybrid 2+1、联盟/计划版本与迟滞 | CP-SAT/MILP 复杂约束参考；OR-Tools 仅为可选 benchmark |
| D4 | 中心有效时验证联盟；中心失效且 `k_j>1` 时 fail-closed，禁止单赢家 CBBA 冒充联盟 | 二级/完全分布式 coalition commit、ACK、lease、补位和重构 |
| D5 | 联盟只读合同、合法三成员锁、超额/版本冲突、reserve standby 门控 | 真实多视角三角定位与跨视角 AirSim 多 seed 标定 |
| D6 | demand/coalition/arrival 记录、需求满足、波次、合法锁、通信和安全指标 | 真实 episode 的 arrival/成员损失/替换证据积累 |
| D7 | 成员级 role/wave/window/version gate；reserve 未激活阻断；PNG 核心公式未改 | 同步到达可达性、终端扇区、最小距离和多 seed 飞行校准 |
| main | `--resource-count M --target-count N`、协同需求 CLI、D3→D5/D4/D7/D6 总线、5v2 3+1 闭环 | 真实 Blocks 5v2 多 seed 与 SimpleFlight 3v1/5v2 长时飞行 |

回归证据：D1 54、D2 57、D3 104（OR-Tools 1 skip）、D4 121、D5 127、D6 68、D7 84、AirSim runtime 75、质点集成 7、跨模块合同 3，全部通过。质点 `cooperative_3v1`/`cooperative_5v2` 的需求满足率为 1.0、shortfall 为 0；main episode bus 的 5-resource/2-target 测试形成 3+1 assignment pair，D5/D7 均保留 4 个独立上下文。中心和二级失效时三机联盟输出 `coalition_fallback_unsupported` 并 hold，不发布伪分布式联盟。

## 2026-07-11 P1 实施与真实 AirSim 结果

详细报告见 `subagent_reviews/MAIN_P1_AIRSIM_RUNTIME_VALIDATION_REPORT_20260711.md`。

| Owner | 实施结果 | 当前证据与结论 |
|---|---|---|
| main/runtime | D2→D3/D5 无 truth 转换、仿真 actor alias 边界隔离、D1-D4 governance/lifecycle、guidance experiment law 回灌 | 5v5/2v2 真机进程运行完成；在线 `truth_id=None` 不再造成 D3 空计划 |
| D4 | truth/continuity unavailable 不触发虚假硬风险，在线风险门限保持 | 中心保持和 distributed 负例通过；secondary 正例仍因 full-view readiness 不足而未闭合 |
| D5 | bbox-only offline truth parser 支持真实 AirSim 输入，truth 不进入在线 tracker | 84 个相机样本接口通过；当前模型 accepted detection=0，效果仍为 P1 |
| D6/main | 四导引律 experiment law 可配对，生成 JSON/CSV/中文报告/曲线 | 21 条指标配对行，只有 seed 7；四律 2 秒均 timeout，不作为命中率结论 |
| D7 | Pure Pursuit、Radar PN、PNG-VM、PNG-TTC 真实 SimpleFlight selector/gate 接入 | PNG VM/TTC switch allowed 约 0.762/0.810；需长时多 seed |

## 2026-07-10 P0/P1 实施与实测结果

本轮继续严格执行 “main 下发、D-agent 自改自测、main 只改 runtime/集成/总文档并运行 AirSim”。

| Owner | 实施结果 | 实测/验收 |
|---|---|---|
| main/runtime | stale D3 plan 被拒后保留当前 plan；YOLO/MOT adapter 跨 episode 重置 stream；AirSim builtin detect 改为匿名 camera-local bbox tracker，局部 ID 不含 actor 名 | `p0_truth_isolation_smoke_20260710` 三 case connected，匿名 ID 连续 5 帧，actor-name online 泄漏为 0 |
| D1 | 复核真实 2v2 双时间戳、协方差 finite/symmetric/PSD 和 NED 合同，无源码回归 | 1528 条观测可回放；32 tests passed |
| D2 | truth-unavailable continuity、rejected-pair replay、covariance validation/diagnostic | 39 tests passed |
| D3 | active plan 后 previous-plan 必填；switch penalty 进入 Hungarian 矩阵；stale plan 保留 | 63 tests passed |
| D4 | 保持 takeover-ready 安全门限，并对 60-case 结果完成状态机诊断 | 84 tests passed；15/1300 决策瞬时 takeover-ready，active plan 为 0 |
| D5 | friend-aware reacquire、actor-name category 隔离、MOT per-stream state/reset | 96 tests passed；匿名 ID smoke 各 case cross-view association=4 |
| D6 | cross-seed/scenario-group 聚合、paired baseline/enhanced、deterministic bootstrap、review labels；拦截 outcome/距离/时间/视觉切换/gate 指标进入 cross-seed | 48 tests passed；D6 报告只把有 intercept evidence 的 full-flow 列入 outcome，execution=18/20，read-only 不再误报 0/20 |
| D7 | 不改 PNG 控制律，复核真实 10-seed guidance/gate 输出 | 45 tests passed；18/20 拦截成功 |

AirSim 证据：

- `outputs/p1_gap_closure_calibration_20260710`：10 seeds、50/200 m、3 个二级节点、110 deg、1920x1080、三 case，共 60 episode。
- `outputs/p1_gap_closure_2v2_multiseed_20260710`：10 seeds、20 pairs，18 collision intercept、2 terminal detection timeout；pair 等权平均最小距离 2.113 m，D6 每 episode 最小值均值 1.812 m。
- D4/D5 的主要未闭合项不是投影或注册，而是 sustained network full-view、逐决策 stable evidence 和 secondary plan activation。
- D7 的主要未闭合项是视觉 gate 通过率和 PN/Pure Pursuit/PNG-TTC/PNG-VM 同 seed 对照，不是 PNG 核心公式重写。

## 2026-07-09 P0 实施结果

本轮严格按 “main 下发、D-agent 自改自测、main 汇总验证” 执行。main 只修改 AirSim runtime/总线桥接和 main GAP 文档；D1-D7 各自只改 owned paths。

| Owner | P0 实施结果 | 验证 |
|---|---|---|
| main/runtime | episode bus 输出 episode clock、scenario config、D1-D7 module health、runtime errors、mission outcome/root cause/performance metadata；D4/D5 stress bridge 正确把二级注册 evidence 输入 D4，并避免把 `registered_to_global_track` 当作拒绝原因；P1 calibration suite/threshold metadata、高度对比和 secondary owner 保持已实现 | `pytest -q research_modules/airsim_runtime/tests/test_blocks_runtime.py` -> 59 passed |
| D1 | sensor health、covariance floor/ceiling reason、timestamp uncertainty、replay summary、latency audit 和区域质量摘要已实现 | 32 passed |
| D2 | motion consistency cost、quality-aware gate baseline、`track_quality/association_risk/quality_metadata` 已实现 | 31 passed |
| D3 | 资源状态细化、high-threat release、结构化 stale rejection、explainable threat baseline 和 assignment evidence export 已实现 | 56 passed |
| D4 | heartbeat smoothing、lease/epoch strictness、secondary capability score、active degradation debounce 和 `secondary_capability_class` 已实现；active secondary plan 同 id/version 回归已修复 | 84 passed |
| D5 | active reacquire、temporal consistency、candidate margin、calibration health metadata 和 detect registration outcome 已实现 | 79 passed |
| D6 | mission outcome、failure reason、top failure causes、eval priority/status/evidence path、performance metrics 和 P1 calibration 标准报告 bundle 已实现 | 38 passed |
| D7 | terminal latch、dwell/release/reacquire grace、filtered LOS rate/outlier reject evidence、3D PN benchmark/log 和 P1 switch/gate calibration fields 已实现 | 45 passed |

`git diff --check` 通过。D2、D6、runtime 的 matplotlib Axes3D warning 为本机环境 warning，不构成 P0/P1。

## 2026-07-09 P1 实施结果

本轮 P1 实施仍按 “main 下发、D-agent 自改自测、main 汇总验证” 执行。D1-D7 各自更新 owned paths 和 GAP/PLAN/README/review；main 只修改 AirSim runtime、测试和 main-level GAP/status。

| Owner | P1 实施结果 | 验证 |
|---|---|---|
| main/runtime | `--p1-calibration-sweep` 输出 suite/version/threshold、二级高度/FOV/数量/站距、expected state fields 和 50/200 m 高度对比；自动生成 D6 `d6_airsim_calibration` bundle；修复 secondary takeover plan 在连续 replan 后 `owner_node_id` 回退为 `d3_central` 的问题 | runtime 59 passed；`p1_gap_fix_smoke_20260709` 生成 6 行 smoke summary |
| D1 | dry-run/replay 增加 schema/version/metadata 检查、latency/OOSM audit 和区域质量摘要 | 32 passed |
| D2 | replay 输出 association risk threshold version、gate pass/reject、risk summary 和 threshold sensitivity | 31 passed |
| D3 | 增加 assignment evidence export、cost breakdown/rejected edges/stale reason/secondary fields 和硬时间窗闭合边拒绝 | 56 passed |
| D4 | 增加二级 readiness/capability class，D7 handoff 需 `takeover_ready` 才放行 active secondary visual PNG | 84 passed |
| D5 | detect-to-global candidate 增加 outcome、reject reason、timestamp/age、projection/covariance 和 YOLO/MOT metadata；`projection_invalid` 独立成因 | 79 passed |
| D6 | AirSim calibration report 保留 scenario/standard mapping/evidence/trend/height bucket/actual scale；Markdown 增加 50/200m、coverage funnel、stable registration、D7 reject 等口径 | 38 passed |
| D7 | runtime/comparison/replay/calibration 输出 terminal range、closing speed、bbox/LOS/maneuver gate、D4 block reason、D5/D3 consistency、secondary capability、threshold advisory version 和 visual PNG switch count；未改 PNG 核心控制律 | 45 passed |

## 1. 总体结论

当前项目已经形成一条可运行的轻量科研主线：

```text
D1 NumPy EKF/FusionAdapter
-> D2 GNN/Hungarian 关联与 ID 指标
-> D3 SciPy Hungarian 分配与迟滞
-> D4 C2Health + 主动/被动降级 + 轻量 CBBA
-> D5 几何投影门控 + 保守 TerminalAssociation
-> D7 PN / SimpleFlight 视觉 PNG gate
-> D6 离线 EpisodeMetrics / JSONL / Blocks replay 评估
```

已经落地的主要是**自研轻量实现和少量成熟 Python 科学计算库**：NumPy、SciPy、OpenCV `projectPoints`、AirSim `simGetDetections` metadata、D5 YOLOv8 + ByteTrack/BoT-SORT/IoU fallback adapter、SimpleFlight 控制、D7 delivery 包中的 YOLO+ByteTrack 可选链路。

**2026-07-08 子智能体复核状态**：D1-D7 已分别重审并更新各自 PLAN/GAP 文件，所有子 GAP 均明确拆分为“已实现、部分实现、未实现、未实现原因、缺少条件、下一步优先级”。本轮确认：D1 的 replay schema v1、legacy JSONL、最小 CSV reader/replay、latency/OOSM audit 和区域质量摘要已实现；D2 的 replay helper、5v5 dense/crossing fixture、风险阈值敏感性和显式 ID 指标已实现；D3 的 D5 feedback writeback、secondary takeover DTO/helper、D7 binding、owner/version/source metadata 和 D6 export 已实现；D4 的主动降级硬/软风险分层、二级节点 lifecycle、secondary takeover metadata、D5 evidence 到 CBBA 和 cost gap helper 已实现；D5 的几何日志、handoff advisory、一致性窗口、truth ID 在线隔离、YOLO/ByteTrack 离线 schema adapter、可运行 YOLOv8 + ByteTrack/BoT-SORT/IoU fallback adapter 已实现；D6 的 execution/contract 双口径、实际规模分组、主动降级精度和 D7 replay 指标已实现；D7 的 runtime bus、comparison/replay helper、N-pair 状态、D4 gate blocking、owner/version gate 和 terminal contract gate 已实现。

尚未落地的主要是**完整外部工程栈、生产级适配或高阶主线替换**：Stone Soup、FilterPy、ROS 2 `tf2/message_filters`、OpenDroneID Core、MAVLink signing 验证、DDS Security、AprilTag、Deep SORT/ReID、SCRIMMAGE、TrackEval/HOTA、正式 OR-Tools Min Cost Flow、完整 MIT/CA-CBBA 适配、PX4/MAVLink 主线控制。BoT-SORT 和 py-motmetrics 已有 optional adapter/可用性路径，但真实多 seed、依赖和指标口径未完成时不算生产落地。

未实现的共同原因主要有四类：

1. **当前阶段优先轻量可复现**：默认测试不依赖 ROS、Stone Soup、AirSim 实时服务、PX4 或 GPU。
2. **main runtime bus 接口基线已接入**：AirSim runtime 已在同一 episode 中持续写入 D1-D7 summary/record 和 D6 JSONL；2026-07-08 已把执行拦截结果回灌到正式 main bus metrics，接入 D5 feedback、二级接管 owner/version 和 D7 runtime bus，并保留 raw contract metrics；2026-07-09 P1 calibration sweep 已自动回灌 D6 标准 CSV/JSON/Markdown 报告 bundle，且 summary 保留 suite/threshold version 与高度对比；secondary takeover 连续 replan 时 owner 不再回退为中心节点；下一步仍需真实 Blocks 多 seed 校准。
3. **二级侦察看清不等于可接管**：2026-07-08 5v5 registration calibration v2 中，二级云台指向成功率为 1.0，`projection_valid_rate=1.0`，几何门通过率约 0.474，稳定跨视角注册约 51/55/53，cross-view association 为 4/4/5；但 `secondary_network_joint_full_view_frame_rate` 均值仍约 0.048，联合覆盖约 0.771，主要断点是 `not_all_targets_visible` / `network_union_incomplete`。它说明二级节点已能提供有效注册证据，但不能绕过 D3/D4/D5 的分配、仲裁和视觉 PNG gate。
4. **真实图像/通信/身份源仍需标定**：D5 已能运行 YOLOv8 + MOT 并由 main runtime 显式接线；Remote ID、MAVLink signing、AprilTag 仍需要真实报文、密钥和时间同步，YOLO/MOT 仍需要 AirSim 多 seed 阈值标定。
5. **高阶算法需要基准场景支撑**：IMM、JPDA/MHT 完整版、FRPN、MPC、OSPA/HOTA 等应在 5v5 crossing、遮挡、主动降级和 AirSim replay 稳定后再做对照。

## 2. 横向开源/共识方案落地状态

| 共识/开源项 | 预期用途 | 当前状态 | 涉及模块 | 未实现/未完全实现原因 | 缺少条件 | 优先级 |
|---|---|---|---|---|---|---|
| EKF | 融合和航迹滤波主线 | **已实现轻量版**。D1 自研 NumPy EKF，D2 自研二维线性 Kalman | D1, D2 | 未使用 FilterPy/Stone Soup 后端 | 外部库对照接口、三维/非线性量测合同 | P0 已可用，P2 对照 |
| UKF | 强非线性量测升级 | 未实现 | D1, D2 | 当前 EKF/CV 已满足 phase-1；不想提前引依赖 | UKF 后端、sigma-point 参数、强非线性场景 | P2 |
| IMM-EKF/UKF | 高机动目标模型切换 | 未实现 | D1, D2 | 当前场景以 CV/二维基础关联为主 | CV/CA/CT 模型、转移概率、机动基准 | P2 |
| Stone Soup | 多目标跟踪、JPDA/MHT、轨迹融合、指标对照 | **占位/文档级**，未作为运行依赖 | D1, D2, D6 | 默认环境轻依赖；Stone Soup 对象不宜直接污染系统总线 | 安装版本、adapter、对照数据和指标门限 | P2 |
| FilterPy | EKF/UKF/IMM 原型 | **占位/可用性检查**，未调用 | D1, D2 | 已有自研 NumPy fallback | 依赖策略、状态/量测模型、测试容差 | P2/P3 |
| ROS 2 `tf2` | 坐标树、外参、frame 变换 | 未实现 | D1, D5, D7 | 当前是 Python 离线/AirSim runtime，不启动 ROS 图 | ROS 2 runtime、frame tree、带戳消息 | P3 |
| ROS 2 `message_filters` | 多传感器时间同步 | 未实现 | D1, D5 | 当前用 `measurement_timestamp/arrival_timestamp` 和离线 replay | topic schema、同步策略、bag/replay | P3 |
| SciPy `linear_sum_assignment` | Hungarian 关联/分配 | **已实现** | D2, D3 | 不适用 | 仅需保持 SciPy 依赖 | P0 |
| OR-Tools Min Cost Flow | 多容量/复杂约束分配 | 接口预留，未实现 | D3 | 当前 5v5 一对一 Hungarian 足够 | OR-Tools 依赖、容量/需求/禁配边结构 | P1/P2 |
| GNN/Hungarian | 多目标硬关联主线 | **已实现** | D2 | 不适用 | 需增加 5v5 dense/crossing 压测 | P0 |
| JPDA | 密集交叉软关联 | **轻量对照版**，非完整生产级 | D2 | 仅枚举小规模假设，不做完整概率混合更新 | Stone Soup 对照、密集交叉基准、参数标定 | P1 |
| MHT | 多扫描假设跟踪 | **有界 placeholder** | D2 | 完整 MHT 延迟/内存高，不适合资源节点 | N-scan pruning、分簇、中心算力假设 | P2 |
| PN 比例导引 | 单目标/中段默认导引 | **已实现** | D7 | 当前是二维经典 PN 和 SimpleFlight gate | 三维状态、D5/D3 门控、真实飞控约束 | P0 |
| Pure Pursuit | 对照 baseline | **已实现轻量 baseline**。D7 提供 `compute_pure_pursuit_command()` 和 `GuidanceConfig.guidance_law=\"pure_pursuit\"` | D7 | 未直接引入 PythonRobotics，有意保持轻依赖 | 多 seed PN/Pure Pursuit 对照报告、AirSim controlled 选择开关 | P1 已完成基线 |
| 改进 PN / FRPN | 高机动增强导引 | **已有隔离式研究近似 benchmark，未进入主线** | D7 | 当前先稳定经典 PN/PNG；现有 FRPN 不是生产级完整实现 | 目标加速度估计、严格公式、机动场景和同输入对照 | P2 benchmark |
| 视觉 PN / PNG | 末端视觉导引 | **部分实现** | D7 | 已有 bbox gate、LOS-rate、TTC/VM，仍非严格纯视觉闭环 | D5 locked、距离/闭合速度估计、相机标定 | P0/P1 |
| AirSim `simGetDetections` | CV 检测框输入 | **已使用** | D5, D7, main runtime | D5 不直接调 AirSim，只消费 fixture/replay；D7/main 调用 runtime | 稳定 detection schema、camera/object ID 映射 | P0 |
| OpenCV `projectPoints` | 图像投影和门控 | **已实现单相机主线**。D5 优先调用 `cv2.projectPoints`，无 OpenCV 时有针孔 fallback，并传播像素协方差 | D5 | 未实现 calibration/solvePnP/跨相机联合优化 | 准确 K/R/t/dist、标定样本、PnP 2D-3D 对应 | P0 已可用，P2 标定增强 |
| OpenCV calibration / `solvePnP` | 相机标定、外参估计 | 未实现 | D5 | 当前假设 AirSim/runtime 提供相机参数 | 2D-3D 匹配点、标定图、PnP RANSAC | P2 |
| YOLOv8 + ByteTrack/BoT-SORT | 局部检测/MOT 默认候选 | **P1 已接入显式运行路径**。D5 `YoloMotAdapter` 可加载 `best.pt`，优先 ByteTrack/BoT-SORT，失败时 deterministic IoU fallback；main runtime 可用 `--detection-backend yolo` 将内存图像送入 D5，并转换为现有 detection contract | D5, main runtime, D7 | 默认仍不保存 PNG；MOT ID 只作为 `LocalVisualTrack.local_track_id`，不得替代 `global_track_id` | AirSim 多 seed 阈值、class id、GPU/CPU 预算、MOT IDSW 标签 | P1 接线已完成，P1/P2 标定 |
| BoT-SORT | 运动相机 MOT | **已接入 D5 可选 tracker backend**，失败时可回退 IoU；未完成真实 ReID/相机运动补偿验收 | D5 | 当前缺真实图像多 seed 和稳定 ReID/运动补偿证据 | 图像序列、依赖、ReID 模型、IDSW truth | P1/P2 标定 |
| Deep SORT | 外观辅助 MOT | 未实现 | D5 | 当前小目标外观未建模 | embedding 模型、图像帧、IDSW 真值 | P2 |
| OpenDroneID / Remote ID | 友方身份正向声明 | **模拟实现** | D5 | 只解析 `protocol=OpenDroneID` 风格 dict，未接 Core C | 报文解码器、白名单、签名/位置一致性 | P1 |
| MAVLink signing | 消息来源认证 | 未在 D5 实现；D7 delivery 有 MAVLink 控制路径 | D5, D7 | 当前没有真实 MAVLink telemetry/signing key 管理 | MAVLink source、签名库、密钥策略 | P2 |
| DDS Security | ROS 2 中间件认证 | 未实现 | D5, main | 当前无 ROS 2/DDS runtime | enclave、证书、权限文件、节点映射 | P3 |
| AprilTag | 合作视觉标签 | 未实现 | D5 | 当前无图像帧和 tag detector | 图像流、tag ID 映射、误检评估 | P2 |
| MIT CBBA / CBBA-Python / CA-CBBA | 分布式降级对照 | 未接入；自研轻量 CBBA | D4 | 外部项目接口/许可证/依赖和 summary bus 不匹配；本轮 P1 明确暂不构造外部开源算法 | adapter、同场景 benchmark、许可证审查 | P2 |
| 拍卖算法 | 分布式保底 baseline | 未单独实现 | D4 | 当前 CBBA 机制覆盖拍卖式思想，但无独立 baseline | bid/award/rollback 协议和测试 | P1 |
| 合同网协议 | 分布式任务协商对照 | 未实现 | D4 | 非 5v5 最小闭环必需 | announce-bid-award 状态机 | P2 |
| SCRIMMAGE | 大规模多智能体仿真 | 未实现 | D6/main | 当前优先 AirSim CV 5v5 和质点仿真 | SCRIMMAGE 输出样例、ID 映射、时钟对齐 | P3 |
| TrackEval / py-motmetrics | HOTA/IDF1/MOTA/MOTP | **py-motmetrics optional adapter 已实现**；依赖缺失时 unavailable。TrackEval/HOTA 未接入 | D6 | 当前先保持本地可解释指标，外部结果不得回流控制 | 稳定 MOT 导出、帧级 truth 匹配、TrackEval 依赖版本 | P2 |
| Stone Soup metrics / OSPA/GOSPA/SIAP | 标准跟踪指标对照 | 未实现 | D6 | 需要 D1/D2 Stone Soup Track adapter | cutoff/order、匹配门限、坐标合同 | P2 |
| PX4 SITL / MAVLink body-rate | 更真实飞控闭环 | delivery 包有实验路径，main 未接入 | D7 | 当前主线选 SimpleFlight，避免飞控复杂度 | PX4 SITL、Offboard 状态机、推力/坐标标定 | P2 |

## 3. 各子模块核心结论

| 模块 | 已实现主线 | 关键未实现项 | 直接阻塞条件 | 详细文件 |
|---|---|---|---|---|
| D1 多传感器融合 | `SensorObservation -> NumPy EKF/FusionAdapter -> GlobalTrack`；measurement/arrival timestamp；NED 六维状态；协方差；雷达/声学/EO/合成 LiDAR；延迟补偿；AirSim dry-run；Blocks JSONL reader/replay；replay schema v1/legacy JSONL；最小 CSV reader/replay；`TrackUncertaintySummary`；`LatencyAuditSummary`；`FusionQualityRegionSummary`；source de-dup；N-target 输入 | Stone Soup/FilterPy 后端、UKF/IMM、ROS2 tf2/message_filters、D1 包内真实 AirSim CV 直连、Track-to-Track fusion、更多真实 Blocks/CV fixture | 真实相机/传感器外参、稳定 detection schema、外部依赖、跨节点相关性策略、D6 长期批量 schema | `subagent_reviews/D1_IMPLEMENTATION_GAP_AUDIT.md` |
| D2 数据关联 | GNN/Hungarian、马氏门控、二维 Kalman、轻量 JPDA/MHT、IDSW/连续性、dry-run adapter、`crossing_dense_5v5`、风险滑窗、D1 adapter | 完整 EKF/UKF/IMM、Stone Soup/FilterPy、原生 3D NED、真实 AirSim CV replay 压测 | 5v5 replay 样本、风险阈值、三维跟踪策略 | `subagent_reviews/D2_IMPLEMENTATION_GAP_AUDIT.md` |
| D3 目标分配 | SciPy Hungarian、fallback DP、滚动重分配、迟滞、版本化计划、D5 feedback helper、D7 `AssignmentGuidanceBinding`、`AssignmentValiditySummary`、D6 assignment record export、AirSim dry-run、main episode bus plan/version 输出 | OR-Tools Min Cost Flow、D5 feedback 自动写回真实代价 | D5/D6 重复锁定聚合校准、复杂约束定义 | `subagent_reviews/D3_IMPLEMENTATION_GAP_AUDIT.md` |
| D4 降级接管 | C2Health、被动降级、主动降级、二级侦察节点模型、`SecondaryNodeLifecycleSummary`、CommunicationSummary、主动降级防抖、轻量 CBBA、中心恢复合并、D4 arbitration adapter、D6-compatible event metadata、main episode bus D4 event 写入 | MIT/CA-CBBA 适配、独立拍卖/合同网、真实视频 cue adapter | 二级 heartbeat/coverage/link freshness 的真实 Blocks 多 seed 校准 | `subagent_reviews/D4_IMPLEMENTATION_GAP_AUDIT.md` |
| D5 末端视觉配准 | `GlobalTrack -> CameraModel -> projected image point -> LocalVisualTrack -> TerminalAssociation`；OpenCV `projectPoints`/fallback；马氏门控；保守 `locked/ambiguous/hold/reacquire`；AirSim bbox adapter；YOLOv8 + MOT runtime adapter；truth ID 在线隔离；二级 cue；跨视角摘要；`TerminalConsistencySummary`；视觉 PNG handoff advisory；main episode bus terminal record；禁止改写 ID | Deep SORT/ReID、OpenDroneID Core、MAVLink signing、DDS Security、AprilTag、solvePnP/calibration、ROS2 tf2、跨相机几何联合优化 | 协议报文/密钥、相机标定样本、二级节点真实 pose/detection、真实 AirSim 多 seed YOLO/MOT 阈值标定 | `subagent_reviews/D5_IMPLEMENTATION_GAP_AUDIT.md` |
| D6 评估指标 | 本地 EpisodeMetrics、JSONL、Blocks replay、POD/FAR/RMSE/IDSW/assignment/failover/terminal/communication、D4 active/passive degradation、D7 intercept/guidance time-series、PNG delivery 对照和 py-motmetrics optional adapter | Stone Soup metrics、TrackEval、SCRIMMAGE、OSPA/GOSPA/HOTA、长期主动降级 review label | 标准帧级匹配表、真实 D4 metadata、D7 同条件多 seed records/summaries | `subagent_reviews/D6_IMPLEMENTATION_GAP_AUDIT.md` |
| D7 比例导引 | 经典二维 PN、雷达中段 PN、Pure Pursuit baseline、视觉 PNG、TTC/VM、D3/D4/D5 gate、生命周期 KF、`png_ttc` 面积治理、N-pair filter、6D LOS/3D/APN/FRPN optional benchmark | 严格生产级 3D/FRPN、完整视觉闭环、PX4/MAVLink 主线、MPC/NMPC、ViSP/ROS2 | 同条件 M5N2、1-5 帧 dropout、真实 `png_ttc`、trend coast 晋级和平台动力学约束 | `subagent_reviews/D7_IMPLEMENTATION_GAP_AUDIT.md` |

## 4. 当前最重要的缺口

### 4.1 已完成的 P0/P1 接口基线

1. **D1 融合合同已成型**
   `SensorObservation`、`measurement_timestamp/arrival_timestamp`、协方差、NED 六维状态、fixed-lag 延迟补偿、雷达距离相关协方差、source lineage 去重、`TrackUncertaintySummary` 和 Blocks JSONL reader/replay 已实现。

2. **D2 关联与身份指标已成型**
   GNN/Hungarian、马氏门控、二维 Kalman、轻量 JPDA/MHT 对照、`id_switch_count`、continuity、duplicate assignment、D1 adapter、AirSim dry-run adapter、`crossing_dense_5v5` 和风险滑窗已实现。

3. **D3 分配到 D7 的版本化合同已成型**
   SciPy Hungarian、fallback DP、迟滞、stale plan 拒绝、版本化 `AssignmentPlan`、D5 feedback helper、`AssignmentGuidanceBinding`、`AssignmentValiditySummary` 和 D6-compatible `AssignmentRecord` 导出已实现。

4. **D4 主动/被动降级仲裁已成型**
   `C2Health`、被动降级、主动降级、二级节点 lifecycle、communication freshness、D1/D2/D3/D5 evidence adapter、D6 event metadata、轻量 CBBA、D7 two-stage secondary handoff 和中心恢复合并基础版已实现。2026-07-07 已增加硬/软风险分层：`d3_assignment_not_current/stale` 仍触发中心重规划，`d3_assignment_cost_margin_low` 与早期 D5 低置信度只进入观察；无 observed mismatch、资源错配、重复锁定或友方冲突的持续 D5 `ambiguous/reacquire` 不再造成名义场景每帧 `request_center_replan` 或分布式降级。

5. **D5 末端视觉配准安全合同已成型**
   OpenCV `projectPoints`/fallback、像素协方差传播、马氏门控、`LocalVisualTrack`、`TerminalAssociation`、`IdentityClaim`、AirSim/YOLO bbox schema adapter、AirSim truth ID 在线隔离、二级 cue、跨视角重复锁定风险、`TerminalConsistencySummary` 和视觉 PNG handoff advisory 已实现。

6. **D6 离线评估主线已成型**
   `EpisodeMetrics` 显式保留实际 `drone_count/resource_count/target_count/camera_count`，并可消费 track/assignment/event/link/terminal、Blocks replay、D4 active/passive degradation、D7 intercept replay、D7 guidance time-series、批量 CSV/Markdown/PNG 报告。

7. **D7 PN/PNG 导引合同已成型**
   经典二维 PN、雷达中段 PN、Pure Pursuit baseline、离线 radar-to-vision 质点闭环、SimpleFlight 视觉 PNG gate、TTC/VM 捷联导引核心、D3/D4/D5 terminal contract gate、handoff/hold/reacquire/revoke 状态和 N-pair 独立 filter 单测已实现。

### 4.2 当前最关键的未闭合项

1. **main runtime bus 已完成接口闭合，仍需真实多 seed 校准**
   `research_modules/airsim_runtime/episode_bus.py` 已由 main 串接 D1 track、D2 risk、D3 plan/version、D4 action、D5 terminal decision、D7 pair state 和 D6 collector，并在每个 Blocks episode 输出 `main_episode_bus.jsonl`、ticks、metrics 和 summary。执行拦截时，main 还会把 `control_commands.csv` 和 `intercept_summary.json` 的成功数、碰撞拦截数、guidance law 和 terminal reject 回灌到正式 metrics，同时保留 contract-only metrics。2026-07-08 已补齐 D5 terminal feedback 到 D3、D4 二级接管 owner/version 到 D3/D7，以及 D7 N-pair runtime summary。2026-07-09 已补齐 P1 calibration sweep suite/threshold metadata、高度对比、D6 标准报告 bundle，并修复 secondary takeover 连续 replan 后 owner 回退问题。未闭合的是在真实 Blocks 长时/多 seed 条件下校准阈值、状态迁移和降级必要性标签。

2. **N-pair 真实控制状态机已有 main 接线，仍需真实多 seed 校准**
   D7 已支持每个 assignment pair 独立 filter，main runtime bus 已按每个有效 pair 注入 `AssignmentGuidanceBinding`、D4 permission/action、D5 `TerminalAssociation`、资源状态、目标估计并写 D6 guidance log。下一步重点不是再补接口，而是在真实 Blocks 多 seed 下校准终端切换、重捕获和拒绝原因分布。

3. **D4/D5/D7 的状态迁移需要真实 episode 校准**
   `locked/ambiguous/hold/reacquire`、锁定丢失、重捕获、friend conflict、duplicate lock、`request_center_replan`、`degrade_to_secondary`、`degrade_to_distributed` 和 terminal contract reject 需要在多 seed AirSim replay 中统一记录与评估。本轮已修正软 cost margin 造成的 replan 抖动，并把“无冲突持续重捕获”与“真实 terminal mismatch”分离，但阈值仍需 5v5/multi-seed 统计确认。

4. **机动高空侦察二级节点仍需覆盖/配准校准**
   5v5 registration calibration v2 已验证二级节点 `mobile_recon_gimbal`、`radar_global_track_cue`、200 m 高差、110 deg FOV 和 1920x1080 观测链路能稳定出图、保持有效投影，并把二级 detect 转成稳定 cross-view registration。当前未闭合的不是姿态/投影，而是二级网络同帧全目标覆盖：`secondary_network_joint_full_view_frame_rate` 均值约 0.048，主要断点为 `not_all_targets_visible` / `network_union_incomplete`。下一步应优先校准二级站位/扫描策略、coverage cell、cue freshness、外参/时间戳和 D6 coverage funnel 指标。

5. **YOLO/MOT 已有显式运行路径，真实协议/标定链路仍待推进**
   D5 YOLOv8 + ByteTrack/BoT-SORT/IoU fallback adapter 和 main `--detection-backend yolo` 接线已完成；Deep SORT/ReID、OpenDroneID Core、MAVLink signing、DDS Security、AprilTag、solvePnP/calibration 和 ROS2 tf2/message_filters 仍需真实图像/报文、密钥、相机外参、时间同步和依赖隔离。

6. **高阶算法仍需作为 optional benchmark 接入**
   UKF/IMM、完整 JPDA/MHT、Stone Soup、FilterPy、OR-Tools Min Cost Flow、MIT/CA-CBBA、TrackEval/py-motmetrics、OSPA/GOSPA/HOTA/IDF1、FRPN、MPC、PX4/MAVLink 都不应直接替换当前轻量主线，应先在同场景对照报告中验证收益。

### 4.3 直接下一步缺口

1. main 继续用 `MainAirSimEpisodeBus` 做 Blocks episode 的统一 DTO/record 总线，并保持 `main_episode_bus.jsonl` 可由 D6 `load_episode_log_jsonl()` 反读。
2. main 在真实 Blocks 多 seed 中校准 D3 `AssignmentPlan`、D3 `AssignmentGuidanceBinding`、D4 action、D5 terminal decision 和 D7 guidance records 的状态迁移阈值。
3. main/AirSim runtime 继续固化 Blocks JSONL/replay schema，保留实际目标数、资源数、相机数、bbox、相机内外参、truth offline label、plan/version、D4/D5/D7 状态字段，并避免在线 D5 使用 truth ID。
4. main/D4/D5/D6 继续跑机动高空侦察节点 5v5 stress，分别统计单相机全局视野率、二级网络联合覆盖率、detect-to-registration 转换率、`secondary_detect_available_but_not_registered` 和 cross-view association。
5. D5 已实现 YOLOv8 + MOT runtime adapter，main 已接入显式 YOLO 检测后端。下一步用真实 AirSim 多 seed 校准 `best.pt`、置信度、tracker backend、目标尺度和 FOV 条件；adapter 只输出 `LocalVisualTrack`，不允许 tracker ID 替代 `global_track_id`。
6. D6 已实现主动降级必要性最小指标口径，main P1 sweep 已自动生成 D6 标准报告 bundle。下一步要求 main/D4 在真实 multi-seed episode 中持续写出 review/window 字段，形成可比较的 active degradation precision 和 unnecessary active degradation count。
7. D6/main 按 patch v2.0 新增 P0-A 口径补齐标准化评估映射最小版：先把当前工程指标映射到 COURAGEOUS、MDPI C-UAS、OCEF 的指标族，并在报告中保留 `standard_metric_family`、`scenario_version`、`evidence_path`、`implementation_status`；完整标准流程、场景库和显著性对比留作 P1。

## 5. 建议实施顺序

1. **保持 P0 合同回归**
   继续用 D3-D7 与 AirSim runtime 测试覆盖 `AssignmentGuidanceBinding`、`D4DecisionRecord`、`TerminalAssociation`、D7 terminal gate 和 D6 intercept adapter。

2. **用 main runtime bus 做真实 episode 校准**
   main 已把 D3 plan/version、D4 action、D5 terminal decision、资源状态和 D7 控制 pair 合并到同一个 AirSim episode state machine，并写入 D6 已支持的分组/降级/guidance 字段；下一步用真实 Blocks 多 seed 校准阈值和报告口径。

3. **跑多 seed 校准**
   使用单次 Blocks 启动 reset 循环跑 CV 5v5、D4/D5 stress 和 2v2 intercept，校准 D4 防抖、D5 一致性、D7 terminal handoff 和 D6 分组指标。

4. **随后做开源对照，不替换主线**
   Stone Soup、FilterPy、TrackEval、ByteTrack、MIT/CA-CBBA、OR-Tools 都建议以 optional benchmark/adapter 方式接入，先生成同场景对照报告，再决定是否进入默认运行路径。

## 6. 子智能体交付文件

- `subagent_reviews/D1_IMPLEMENTATION_GAP_AUDIT.md`
- `subagent_reviews/D2_IMPLEMENTATION_GAP_AUDIT.md`
- `subagent_reviews/D3_IMPLEMENTATION_GAP_AUDIT.md`
- `subagent_reviews/D4_IMPLEMENTATION_GAP_AUDIT.md`
- `subagent_reviews/D5_IMPLEMENTATION_GAP_AUDIT.md`
- `subagent_reviews/D6_IMPLEMENTATION_GAP_AUDIT.md`
- `subagent_reviews/D7_IMPLEMENTATION_GAP_AUDIT.md`

## 7. P0/P1 集中状态与验收

本节合并原独立 P0/P1 状态文档的权威信息。前文保留实现历史和开源落地审计，本节只维护当前优先级、保持项和验收入口。

### 7.1 当前判断

- 当前无开放运行级 P0 blocker；SimpleFlight 默认、主动中心重规划和主动二级接管已经统一使用 D2 估计状态。
- D1/D2/D6 身份隔离、指标 availability、到达时间队列、truth-state provenance 和逐 pair physical provenance gate 已修复；actor truth 仅允许进入离线评分边界。
- 现有 \(k_j=1\) 主线继续可用；M 对 N 的 demand-slot、合法多机锁定、二级/完全分布式原子联盟和成员级 D7 门控合同已实现。
- 历史 ComputerVision 合同验收为 8/10；当前已完成 5 m 成功判据、detect-first truth 隔离、1-5 帧硬窗口、D6 分层指标、2v2 `png_ttc` 20/20 和同条件 M5N2 paired。M5N2 candidate 退化且联盟 0/10，下一步是物理协同和阈值根因修复，不再扩展成功语义。
- P2 隔离 benchmark 已覆盖 D1-D7 的当前可运行范围；不可用外部依赖均显式记录 `unavailable_reason`，不得宣称为主线算法替换。
- main 已修复 D1 新后验在 D2 调度 tick 之间被遗漏的问题。clean `12c5073` 同 seed 重复运行全量语义等价；D2 owner 已确认这是漏消费修复而非过关联。锁存只保存未消费的真实 posterior，D2 使用原有效时刻，D7 过期门和 PN/PNG 公式不变；`0d2da25` 三 seed 已通过后验代次、消费代次、节拍前合并计数和 finalize 排空的实际 D6 审计。

### 7.2 P0 保持矩阵

| Owner | P0 状态 | 必须保持的合同 | 验收 |
| --- | --- | --- | --- |
| D1 | 无新增 blocker | 双时间戳、NED、协方差、OOSM、source de-dup、局部图像航迹 fail-closed 适配和 GlobalTrack | D1 `185 passed` |
| D2 | 无新增 blocker | GNN/Hungarian、稳定 global_track_id、id_switch_count、continuity、陈旧观测隔离和来源身份治理显式计数 | D2 `234 passed, 1 warning` |
| D3 | 无新增 blocker | 版本化 AssignmentPlan、迟滞、stale rejection、D7 binding；运行证据按各 ACK 对应的计划快照验证，真实 stale ACK 保持 fail-closed | D3 `438 passed, 1 skipped, 0 failed` |
| D4 | 无新增 blocker | C2Health、主动/被动降级、二级 lifecycle；active secondary helper/owner 必须对 sustained readiness、expected/actual source、plan/required epoch、expiry/current time 和 plan monotonicity exact-true；冲突或缺失证据 fail-closed | D4 `508 passed` |
| D5 | 无新增 blocker | 不改写 global_track_id、truth 隔离、friend/duplicate 保守门控；原生 MOT 连续实测历史按 stream/backend/ID 隔离并在空帧/reset 后重计；离线人工记录转换重复坍缩 fail-closed；补充课程全样本审计不得开放在线权限 | D5 `551 passed` |
| D6 | 无新增 blocker | 只消费日志；实际规模、id_switch_count、unavailable/zero 分离；逐 pair physical evidence/result/source、联盟完整性和跨模块学习准入严格门控；runtime v1 generation 保持 unavailable，v2 重复、倒序、未知引用、计数不守恒或 pending 未排空均失败关闭 | D6 `567 passed, 1 warning` |
| D7 | 核心公式无 blocker；控制输入 P0 由 main/runtime 持有 | 不分配目标；D3/D4/D5 gate 失败时阻断视觉 PNG；不修改 PN/PNG 核心公式 | D7 `213 passed` + truth-isolated control contract |
| main/runtime | 无新增 blocker | episode bus 可回放；在线 truth identity/state 均为 0；SimpleFlight 只消费 D2 estimate；未消费 D1 posterior 跨 tick 锁存但不改写时间戳；v2 治理快照记录 D1/D2 generation 消费血缘并在 finalize 排空；二级 communication 只消费上一完整 D4 readiness；actor truth 仅离线 5 m scorer；默认不保存 PNG | scalable main `128 passed, 1 warning`；既有 AirSim runtime `147 passed` |

### 7.3 当前 P1 清单

| Owner | 当前缺口 | 已有基础 | 缺少条件/下一验收 |
| --- | --- | --- | --- |
| main/D1/D2/D3/D5/D6 | 分阶段实时性能与长时增长达标 | clean `0d2da25` 已完成带 generation 审计的三 seed 基线和 20 个保留 seed 描述性校准；20-seed 核心墙钟均值 `96.391 s`、实时倍率 `0.1039`，20/20 代次守恒通过。clean `4ac3bb2` 同 seed 1000 核心墙钟从 `94.105 s` 降至 `85.002 s`，D1 融合从 `49.697 s` 降至 `40.273 s`，跨构建规范载荷一致；D1 冻结回放将 scan-input 前 256 扫描 P50 从 `1.942 s` 降至 `0.881 s`，14 项语义验收通过；D2 冻结总线等价优化将 core 中位数从 `2.928830 s` 降至 `2.204672 s`，48/48 周期语义一致；D5 最终源码短/长重放的业务、binding 和冻结操作数哈希相等，truth/ID 改写为 0；`scalable3d-stage-timings-v2` 已由 D6 v7 消费真实 200 对 200 分位 | 仍未实时；D1/D2/D5 候选都缺 clean full-stack 多 seed。D1 融合 P95/max 为 `224.764/592.957 ms`，D2 完整阶段 P95 为 `137.335 ms`；D2 长窗口增长未改善，D5 tracker pair 和投影/绑定矩阵仍随输入组成显著增长。结束后处理仍需关闭，正式七变体矩阵仍为 0 episode。不得把冻结回放加速或 R0 nominal 描述性校准当算法验收 |
| D2/D6/main | 不完整身份真值的可评估范围与保守 IDSW 下界 | D2 已输出版本化 evaluator-only partial diagnostics；clean `4ac3bb2` seed 1000 的映射/帧/相邻转移覆盖为 `8906/9038`、`3/48`、`0/9400`，385 个唯一锚点区间给出 IDSW 下界 7，并排除 1 个重复映射真值帧。D6 truth-isolated consumer 已在 identity manifest、evaluation 与四项 source SHA 验证后分栏输出，且 `strict_id_switch_count_backfilled=false`、`id_switch_upper_bound_reported=false`。strict IDSW 继续因一条航迹对应多个真值而 unavailable | 单 seed producer-consumer 接线已关闭；仍需正式多规模、多 seed 制品和完整 sidecar，形成 strict IDSW/continuity 统计。不得把 partial 下界写成 strict 值或伪造上界 |
| D2/D6/main | v2 关联候选评审与跨 difficulty 证据 | 正式 v2 联合报告已生成；总体五项 gate 通过，IDSW 下降 54.6%，P95 15.47 ms，truth leakage=0；默认在线主线未改变 | 仅 `clutter/combined` 通过，四个零 baseline-IDSW difficulty fail-closed，dropout truth alignment 为 partial；需补同 case/seed 完整多源 system bundle 后再决定是否晋级，JPDA 保持不准入 |
| D3/D5/D7/main | M5N2 协同物理闭环 | 同条件 10-seed paired 和四层日志已完成；baseline 7/30 pair，candidate 4/30，联盟均 0/10 | 分离第二 primary 中段重捕、D5 共识、D7 gate 和成员安全根因；candidate 保持关闭 |
| D5/D7/main | 单帧 dropout 尾部 | 2-5 帧逐 seed 全通过，物理结果 100/100，truth/ID/version 无违规 | 复核 seed 2 在 0.8 s 注入时没有进入 image-KF 的锁定时序；不得用聚合计数掩盖 |
| D7/main/D6 | `png_ttc` 受控覆盖 | tuned 2v2 10 seeds 为 20/20，not-expanding/TTC-out-of-range 已实测 | 补 area-jump 与 bbox-clipping 受控注入，不把未自然出现解释为算法缺失 |
| D5/main | YOLOv8/native MOT 校准 | adapter、Results 连续历史和离线 benchmark 已有；当前在线明确继续使用 AirSim detect | 等数据集补充后再校准类别、尺度、置信度、远距召回、IDSW/continuity、GPU/CPU P95 延时和失败回退；代码级历史累计已关闭，不阻塞 detect-first P1 |
| D1/D2/D5/main | 通用图像来源谱系真实运行标定 | 局部观测合同、D5 离线适配、D1 EO 入口、D1 `source_track_ids`、main NED-only D2 handoff 和 D2 三项来源治理计数已实现 | 接入真实可见光/红外 producer 与 D5 拒绝计数，冻结内外参/时间同步/像素协方差；至少 10 个来源扰动 AirSim case 评估 false-suppression、recall 和离线 IDSW/continuity |
| D1/D2/D3/main | 长 replay 治理阈值 | 版本化 replay/CLI 已具备；D2 10 seeds 的 IDSW=138.1、continuity=0.694 | 默认 GNN 未通过阈值；继续调 gate/lifecycle/model，不用 truth 或本地重绑掩盖问题 |
| D1/D2/main/D6 | 陈旧观测治理长期标定 | 有界扫描排序、声明账本、安全淘汰、replay coast、main 持久化和 D6 严格 consumer 已实现；commit `e4d66db` 的 clean/formal 四档各 5 seed 中 200 规模 peak claim 24170/48000、evicted 2985、overflow 0、near recall 1.0、false suppression/merge 0 | clean 治理复跑已关闭；继续增加完整质点多 seed、真实 AirSim 时钟/遮挡/杂波分档。该 fixture 不关闭融合精度、正式阈值冻结或完整 200v200 验收 |
| D4/main | 联盟重构、二级接管和恢复实测 | 9/9 确定性矩阵通过，含 member replacement、partition recovery 和双轨合并；严格二级 readiness 已统一到所有入口 | 映射到真实 AirSim 通信延迟/丢包/乱序/时钟漂移多 seed，并量化 failover time；不得以 heartbeat-only 作为正例 |
| D5/D6 | M 对 N 视觉鲁棒性 | 确定性 10/10，外参漂移/时间偏差保守拒绝，ID rewrite=0 | 在真实多视角 AirSim/相机同步和持续 detect 下复验，不以确定性 fixture 代替实测 |
| D3/D4/D5/D6/main | 学习数据全样本与运行证据 | canonical seed 60/20/20 和全样本审计已完成；D5 20-seed paired shadow 已完成但有合成可分性限制；D3/D4 v2 clean 5v5 正式制品和 D6 profile-bound availability sidecar 已完成，真值使用为 0；D3 20/20 隔离应用且 binding 未变，D4 20/20 因低置信回退 | 取得严格绑定的 runtime ACK 和采用后物理窗口后再计算 paired physical outcome/effect；D4 confidence 只在独立 calibration split 校准，不用保留 seed 降门限；故障策略另跑 degraded snapshot；完成前 PPO/assist/authority 保持关闭 |
| D6/main | 场景库与长期趋势 | cross-seed、paired effect、bootstrap、联盟 lifecycle 和证据路径已具备 | 固化 scenario version，生成长期 CI、失败漏斗和 active-degradation review 趋势 |
| D7 | 成员安全与独立到达 | role/wave/window、active/standby、commit-aware gate 和 N/M topology 已有 | 当前不要求同时到达；先验证独立 primary 的 terminal sector、minimum separation 和 member loss，协同到达时间后置 |

### 7.4 M 对 N 场景升级条件

required resource count \(k_j>1\) 的合同层升级条件已经满足，后续启用物理协同拦截前仍须满足以下运行级条件：

1. 保持 D3/D4 coalition id、成员、角色、版本、epoch、lease 和原子 ACK/commit 回归不退化。
2. 保持 D5/D6 planned cooperative lock、over-support、错误 duplicate 和 truth 隔离语义不退化。
3. 在真实 SimpleFlight 中验证 D7 simultaneous/sequential/hybrid 到达窗口、成员间距和退出策略，而不修改既有 PNG 核心公式。
4. 用更长真实 replay 验证 D1/D2 canonical registration、lineage 去重和 CI，不让 offline truth 回流在线总线。

### 7.5 统一验收命令

```bash
PYTHONPATH=research_modules/d1_sensor_fusion/src pytest -q research_modules/d1_sensor_fusion/tests
PYTHONPATH=research_modules/d2_data_association pytest -q research_modules/d2_data_association/tests
python3 -m pytest -q research_modules/d3_assignment_planner/tests
PYTHONPATH=research_modules/d4_distributed_fallback python3 -m pytest -q research_modules/d4_distributed_fallback/tests
pytest -q research_modules/d5_terminal_association/tests
pytest -q research_modules/d6_evaluation_metrics/tests
python3 -m pytest -q research_modules/d7_proportional_guidance/tests
pytest -q research_modules/airsim_runtime/tests/test_blocks_runtime.py
git diff --check
```

## 2026-07-22 有界观测治理与规模复核

D1 扫描组织器、D2 声明账本和 main 运行时审计已接入同一 episode 状态机。D1 使用量测
时间水位线排序完整扫描；D2 以源命名空间、不透明观测标识和量测时刻声明新证据，按安全
水位线淘汰旧声明。重放只允许有上界的预测 coast，不增加命中、不刷新宽限，也不生成航迹。
所有在线记录继续携带双时间戳和协方差，`global_track_id` 由 D2 中心链路持有，在线
`id_switch_count` 保持显式 unavailable，真值只进入 D6 离线侧车。

active-risk 5v5 seed 1005 的当前 1.1 秒集成路径所有发布均为 5 条中心航迹，birth=5，暂定
删除、错误合并和在线真值使用均为 0。main 结束排空依次融合并发布全部 D1 尾部扫描，只把
最终融合后验送 D2 一次，并把待发布的 D1 源观测谱系批量归档到该次中心关联；离线一致性
映射继续覆盖全部已融合观测。旧路径由逐尾帧产生的 9 次人工 replay quarantine/coast 因而
降为 0。运行期关联和失联老化没有放宽。

development 快速标定覆盖 20、50、100、200 四档各 5 seed。每例 136 帧、33.75 秒，D1
重排 12、拒绝/过旧/溢出 0、峰值缓冲 3。200 规模 D2 峰值声明 24170/48000，安全淘汰
2985、溢出 0；离线近邻召回 1.0、错误抑制和错误合并 0、确认时延 0.25 秒。200 规模 D1 与
D2 合计峰值 `tracemalloc` 约 58.99 MB，在线真值使用为 0。该批是治理 fixture 和脏工作树
证据，不能替代完整融合精度或正式 200v200 验收。

同一配置已在 detached clean 提交 `e4d66db02a0b8f1b867a0e81b4a73de84588426b` 完成 20 个
episode 正式复跑。四档各 5 seed 均通过 `formal_only` 准入，`repository_dirty=false`、在线
真值使用 0、D1 结束缓冲 0、D1/D2 溢出 0；容量、淘汰和 evaluator-only 指标与 development
批次一致。200 规模合计峰值内存均值 58996981 B、最大 59007120 B。聚合 JSON SHA-256 为
`6fb64252292aaedd3c68d1bfea64b76496136ce6edb32add61a281d511c4ed22`。该证据只关闭 clean
治理复跑，不升级融合精度、AirSim、实时性或物理闭环状态。

同 seed 的 200v200、2.2 秒全栈质点烟测在尾部合并前后分别用时 95.41 秒和 60.21 秒，
实时倍率从 0.0231 提高到 0.0365，D2 尾部调用由 31 次降为 1 次。当前主要瓶颈为 D1 融合
35.12 秒和 D3 三次分配 7.33 秒。下一步先完成模块性能优化，再增加完整质点多 seed、AirSim
时钟/遮挡/杂波和物理闭环。此前提交 `0fa7c00c...`
的 clean active-risk 物理窗证据继续保留，但不与本批 development 标定混写。

## 2026-07-22 D1/D2/D3 性能优化与 clean 多 seed 校准

### 已关闭

1. D1 冻结输入逐扫描重复后验热点已关闭。未缓存与增量路径逐扫描语义、终态航迹和一致性
   证据哈希一致，滤波更新 `93,234 -> 1,797`，纯融合 `34.701 -> 9.073 s`。
2. D3 规划证据完整矩阵重复深拷贝热点已关闭。规则代价、候选边、匈牙利、迟滞和计划版本
   不变，独立 200x200 中位数 `2651.953 -> 189.111 ms`。
3. D1 扫描量测模型缓存保持候选对和创新求解次数不变；冻结 seed 42000 中模型构造
   `16,457 -> 82`，逐扫描、终态航迹和一致性证据哈希相同。
4. D2 元数据审计缓存保持全局最近邻、匈牙利、中心身份、生命周期和声明账本不变；五个
   200 规模 seed 的 45 个发布周期语义哈希全部一致。
5. main 从 clean 提交 `3310165` 完成 20/50/100/200 四档各 5 seed 的第二轮短时规则全栈
   校准。20/20 状态有限，在线真值使用为 0，所有 episode 工作树干净。

### 当前结果

| 规模 | 平均墙钟 | 平均实时倍率 | D1 融合 | D2 关联 | D3 分配 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 20 | 1.466 s | 1.504 | 0.457 s | 0.085 s | 0.052 s |
| 50 | 4.082 s | 0.540 | 1.296 s | 0.283 s | 0.157 s |
| 100 | 9.180 s | 0.240 | 3.312 s | 0.709 s | 0.419 s |
| 200 | 23.969 s | 0.092 | 10.275 s | 2.037 s | 0.665 s |

相对上一轮同配置 clean 批次，200 规模平均墙钟下降 26.7%，实时倍率提高 35.9%。D1 融合
与扫描输入合计 13.041 秒，仍是首要模块热点；发布总线为 2.246 秒，D2 运行期关联与结束
关联合计 2.677 秒。20 规模达到实时，50/100/200 尚未达到。短时校准没有五米接近事件，
不能用于任务成功率。

### 本轮关闭与仍开放 P1

1. clean `8f86192` 的同 seed 2.2/10 秒候选对已完成。seed 42000 的 10 秒核心墙钟由上一
   候选 172.214 秒降至 152.254 秒；三 seed 均值为 155.895 秒，实时倍率均值 0.0642。
   长短单位时间成本增长由 2.036 倍降至 1.830 倍，仍未关闭实时和线性增长 P1。
2. D1 同一融合时刻全量快照重复物化已关闭。三 seed state-only/full 数量为
   `310/454`、`328/516`、`278/504`；全部扫描仍融合并保留摘要、当前库存与谱系。D1 融合
   均值降至 92.991 秒。固定滞后回放、检查点查询和剩余物化仍需继续治理。
3. D3 冻结 200×200 输入已分离成本矩阵、Hungarian、计划边证据、迟滞、身份发布和离线
   证据。三 seed 集成累计时间 `3.348 -> 3.289 s` 按基本持平处理，不因墙钟噪声改变代价或
   迟滞。D5 已补图节点、配对、投影与 binding 操作数；终端配准均值降至 2.546 秒，但长时
   单次成本仍为短时的 2.423 倍。
4. 峰值驻留内存均值降至 2.889 GiB，seed 42000 的 10 秒在线日志降至 221.338 MiB，报告
   与写出后处理仍为 65.746 秒。main 需继续治理版本化 heartbeat/lineage sidecar 和离线写出，
   同时保持旧 schema、状态变化、身份、生命周期、质量跨档和来源谱系兼容。
5. 三组 episode 均为 clean、finite、truth/overflow 0。当前 manifest 没有正式实验矩阵元数据，
   D6 将其归为 clean-source descriptive；仍需稳定窗口 P50/P95/max、更多未见 seed、长时
   物理闭环、AirSim 时钟和学习消融。三个 episode 均没有五米接近事件。

详细证据见
`research_modules/scalable_3d_simulation/docs/SCALABLE_3D_RULE_PERFORMANCE_CALIBRATION_CN.md` 和
`research_modules/scalable_3d_simulation/docs/SCALABLE_3D_LONG_DURATION_PERFORMANCE_CALIBRATION_CN.md`。

## 2026-07-28 D4 当前谱系运行兼容性

### 已关闭

1. main 已增加运行兼容性预检，按候选清单中的固定特征边界复核统一三维质点运行快照。
2. D4 已增加冻结候选只读影子适配器、main-owned seed 注册、内容寻址记录、独立重放
   verifier 和逐特征 OOD 诊断。
3. D3 已增加候选身份、确定性投影动作、同输入 R0 和严格后继计划的归因证据边界。
4. `ood_margin` 固定为 0.05；确定性资源投影、规则回退和所有权限门保持不变。
5. 冻结候选已逐字节登记到 D4 `model_registry`。D4/D6 的来源审计和测试不再依赖
   `.gitignore` 下的本机输出目录，clean clone 可以复核相同清单与权重摘要。

### 实测结论

| 场景 | 区域快照 | `feature_ood` | 非回退模型执行 | 在线真值 |
| --- | ---: | ---: | ---: | ---: |
| 5 资源/5 目标/2 区域，seed 2000 | 3 | 3 | 0 | 0 |
| 200 资源/200 目标/8 区域，seed 2001 | 2 | 2 | 0 | 0 |

当前 current-lineage 候选可以可信加载，但不具运行分布兼容性。正式 20-seed A2/R0
评价继续关闭。D3 successor、运行 ACK、owner/coalition ACK、物理窗口、D7 执行和收益
均不可由本轮预检推断。

### 当前 P1

1. D4 已从 clean commit `923f3f6e91af0f85aed446c66420c834d2de63fb`
   构建 8 区域双源候选。1000 个 episode、2098 帧按数字 seed 全局原子切分，
   seed 1000 至 1019 使用数为 0。来源、切分、动作库存、适用域和权限均已绑定。
2. main 已完成新候选预检。5v5/2 区域 seed 2000 为 0/3 分布内、0 次原始模型执行；
   200v200/8 区域 seed 2001 为 1/3 分布内、1 次原始模型执行。两组候选许可执行均为 0，
   在线真值使用为 0，状态有限。
3. 8 区域运行分布仍未闭合。唯一越界特征为 `secondary_readiness`，训练范围
   `[1.0, 1.0]`、运行范围 `[0.0, 1.0]`，16/24 个节点值越界。main 需补采真实
   8 区域、部分二级节点未就绪的匿名运行帧；不得扩大固定 0.05 OOD 余量。
4. D4 置信度校准仍失败关闭。315 个验证样本全部超过 0.60，其中 51 个动作不一致。
   必须降低误接收并保持 0.60 门限，不得用测试集、保留 seed 或人工常量标签调门。
5. 当前候选采用 70/15/15 跨源原子切分。D4 单模块训练不存在跨源泄漏，但面向
   D3/D4/D5 联合训练的 shared canonical 60/20/20 仍需保持独立一致性审计。
6. 2 区域几何不在当前候选适用域，继续规则回退。正式 20-seed/900-cell、runtime ACK、
   后继计划、物理窗口和收益证据继续关闭。

当前没有新增运行级 P0。规则主线可继续使用；A2 assist、分配权、降级权、联盟提交和
控制权保持关闭。

## 2026-07-30 高威胁计划身份与联盟连续性

### P0 关闭项

1. 同一 `plan_id + plan_version` 已收敛为一次不可变 D3 权威发布。随后同身份评估
   刷新只保留诊断，不再生成第二份 `modules.d3.assignment_plan` 或运行确认。
2. 同身份的 owner、epoch、lease、成员绑定或其他权限签名发生变化时失败关闭。D4
   通信缓存保留首次内容摘要和序号，冲突载荷不得覆盖权威引用。
3. D2 临时缺少当前计划目标时，D4 使用最后一份在线 D2 六维状态和协方差保持任务及
   已提交联盟。保持边界为新计划、明确撤销或租约到期。
4. D7 没有继承 D4 的缓存定位。当前 D2 航迹、身份承诺、D3 计划、D4 联盟和 D5
   终端门控仍须同时满足，缺轨目标不生成制导输入。
5. A2 无后继评估通过非权威回调保留评价分母，不授予分配、联盟或控制权限。

main 全量可扩展测试为 `415 passed`。开发批次覆盖 5/20/50/100/200 五档和 seed
1000 至 1019。100/100 状态有限、在线真值为零、D3-D4 最终计划一致、当前联盟闭合；
151 次权威发布与运行确认守恒，48 次评估刷新被抑制，重复计划身份发布和载荷摘要冲突
均为零。D4 缓存连续性在 28 个 episode、391 个任务快照中触发。

D6 独立只读审计确认 644 个当前多成员联盟目标闭合，100/100 个通信处置文件可用并
通过检查，共 195838 条记录。D3 当前计划没有发布可与 D4 对照的区域时期编号和区域
租约，两项均为 `0/100 available`，不能写成一致或不一致。

### 仍开放 P1

1. D3 需要发布当前区域时期编号和区域租约，并把它们纳入同身份权威签名；D4 和 D6
   才能完成双边一致性检查。
2. 本批次来自提交 `2790b165ff54f1d038dba7c08142c46e22b366c9` 的脏工作树，
   只能作为 development 证据。正式 R0 必须从本轮修复后的干净提交复跑。
3. 200 对 200 平均实时倍率约 0.156；50、100 和 200 规模均未达到实时。
4. D2 严格离线身份指标只有 88/100 个 seed 可用，200 对 200 为 10/20。其余 seed
   必须保留 unavailable，不能按零填充。
5. 2 秒短 episode 没有关闭 5 米物理拦截、长时增长、困难视觉、多故障代际和学习
   策略收益。
6. 在正式 900-cell 矩阵前，先完成 D3/D4/D6 所有者完整回归、干净提交和 clean
   smoke。详细证据见
   `research_modules/scalable_3d_simulation/docs/SCALABLE_3D_HIGH_THREAT_P0_PRECHECK_V4_20260730_CN.md`。
