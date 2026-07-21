# 集中式资源-目标分配模块（项目模块编号 D3）原理

> 状态基线：2026-07-15。本文只描述当前仓库已实现行为、已验证证据和明确保留的研究边界，不改变模块能力状态。

## 1. 文档范围与术语约定

MSM 是项目既定代号，不是本文自行展开的英文缩写。D3 是反无人机系统（Counter-Unmanned Aircraft System，C-UAS）科研仿真流程中的集中式资源-目标分配模块。D1-D7 是项目模块编号，不是算法缩写。

本文使用以下状态标签，避免把计划或对照算法误写成主线能力：

- **默认主线**：普通调用会实际采用，且已有模块测试合同。
- **已实现辅助能力**：代码与测试已存在，但需要调用方显式选择，或只用于校准、导出、候选预筛。
- **可选离线对照**：与默认规划器隔离，不会自动替换默认主线。
- **未实现**：只有研究计划、接口设想或外部模块职责，不能据此宣称 D3 已具备该能力。

首次出现的常用英文缩写和产品名统一说明如下：

| 名称 | 本文含义 |
|---|---|
| 应用程序编程接口（Application Programming Interface，API） | 模块对调用方公开的函数和数据合同。 |
| 数据传输对象（Data Transfer Object，DTO） | 只携带结构化信息、不自行执行控制的对象。 |
| 北-东-地坐标系（North-East-Down，NED） | 系统融合工作坐标系；D3 消费上游结果，不负责坐标变换。 |
| 1984 世界大地测量系统（World Geodetic System 1984，WGS84） | 外部地理参考；不作为 D3 代价矩阵的内部工作坐标系。 |
| 到达关键区时间（Time to Critical Zone，TTC） | 可解释威胁基线中的时间紧迫度输入。 |
| 预计到达时间（Estimated Time of Arrival，ETA） | 跨模块可达性信息；当前 D3 不求解完整到达动力学。 |
| 视场（Field of View，FOV） | 某资源观察某目标的相对困难程度。 |
| 身份标识（Identifier，ID） | 航迹或计划的稳定标识；例如 `global_track_id`（全局航迹标识）。 |
| 动态规划（Dynamic Programming，DP） | 默认科学计算后端不可用时的小规模位掩码后备求解方法。 |
| 约束规划-可满足性（Constraint Programming-Satisfiability，CP-SAT） | 仅规划中的复杂约束离线参考方法，当前未实现。 |
| 混合整数线性规划（Mixed-Integer Linear Programming，MILP） | 仅规划中的联盟原子性离线参考方法，当前未实现。 |
| 确认应答（Acknowledgement，ACK） | D4 分布式提交合同中的确认消息，不由 D3 生成。 |
| 比例导航（Proportional Navigation，PN） | D7 的中段导引方法，不属于 D3。 |
| 比例导航制导（Proportional Navigation Guidance，PNG） | D7 的末端视觉导引合同，不属于 D3。 |
| 优先级零、优先级一、优先级二（Priority 0/1/2，P0/P1/P2） | 仓库中的能力优先级标签，不等同于算法阶段。 |

库和仿真产品的用途：

- **SciPy 科学计算库**：默认通过 `linear_sum_assignment()` 函数执行匈牙利算法（Hungarian algorithm）求解。
- **谷歌 OR-Tools 运筹优化工具库**：只用于隔离的最小费用流容量对照；当前环境未安装。
- **微软 AirSim 无人系统仿真器**：由主运行时（main runtime）负责启动、重置、场景和日志；D3 不直接导入其接口。
- **AirSim SimpleFlight 多旋翼飞行控制后端**：用于 2026-07-13 的真实仿真闭环试验，不是 D3 内部求解器。

## 2. 模块定位、问题与边界

### 2.1 模块定位

D3 在中心节点可用时，把上游全局航迹和资源状态转换为版本化候选计划。核心职责有四项：

1. 为任意目标数和资源数构造可解释的目标-资源代价矩阵。
2. 为一对一需求或显式多资源需求生成中心化分配结果。
3. 通过计划版本、前序连续性、迟滞和末端反馈规则抑制抖动与旧计划执行。
4. 向 D4、D5、D6、D7 和主运行时输出被动 DTO、有效性证据与绑定，不执行飞行控制。

2v2、5v5、5 资源/2 目标等只是基准场景。矩阵规模始终来自输入列表长度，不允许将任何基准规模写成算法常量。为避免不同材料对 M/N 记号顺序不一致，本文统一以 $m$ 表示目标数，以 $n$ 表示资源数；具体试验直接写“5 资源/2 目标”。

### 2.2 工程问题

工程上，D3 需要同时处理以下矛盾：

- **最优性与稳定性**：每个规划时刻重新求最小代价，可能因微小噪声频繁换配；完全不重规划，又会保留已经劣化的计划。
- **规模通用性**：目标数可以大于、小于或等于资源数，且某个目标可显式要求多个资源。
- **可执行性与可解释性**：不可行边必须被硬拒绝；每个成本、拒绝原因、保持原因和版本变化必须可审计。
- **中心计划与末端反馈一致性**：末端视觉可以报告风险，但不能自行换绑全局身份。
- **候选计算与正式发布分离**：未审核候选不能推进当前计划；纯成本重评不能制造新的执行版本。

### 2.3 科学问题

当前实现围绕三个科学问题建立可重复基线：

1. 在目标不确定性、威胁程度、资源健康、观察难度和冲突风险共同变化时，怎样构造可解释的组合代价？
2. 在动态场景中，何时应保持旧分配，何时应因收益、旧边不可行或高威胁目标未分配而释放迟滞？
3. 当目标需要 $k_i>1$ 个资源时，怎样以角色、波次、能力和全有或全无准入表达一个完整联盟，同时避免把部分成员误记为可执行成功？

当前答案是轻量、确定性和可审计的基线，不是完整动态威胁模型，也不是复杂时空联合最优解。

### 2.4 明确边界

D3 不负责：

- D1 的多传感器融合、协方差传播和 NED/WGS84 转换；
- D2 的多目标数据关联、全局身份维护和身份切换统计；
- D4 的二级节点选择、租约续期、领导者选举、分布式拍卖或恢复仲裁；
- D5 的视觉检测、末端身份判定和跨视角冲突聚合；
- D6 的日志存储、跨种子统计和报告绘图；
- D7 的 PN/PNG 公式、轨迹生成和控制命令；
- AirSim 启停、重置、场景编排、演员目标移动和飞行器控制；
- 真实火控参数、毁伤逻辑、自动处置授权或绕过人工审核的任何能力。

D3 发布的是科研仿真和人工审核前的候选计划。`human_authorization_state`（人工授权状态）是外部状态的透传与记录字段，不是授权决策器。

## 3. 上游输入、核心结构与下游输出

### 3.1 上游输入

公开规划入口接收：

- `tracks`（目标航迹列表）：元素是 `TargetTrack`（目标航迹 DTO）。
- `resources`（资源状态列表）：元素是 `ResourceState`（资源状态 DTO）。
- `timestamp`（当前规划评估时刻）：用于忙碌状态、硬时间窗、驻留时间和新鲜度计算。
- `previous_plan`（前序已发布计划）：首次调用可为空；已有当前计划后必须精确传入。
- `expected_previous_version`（调用方期望的前序版本）：用于并发或链路连续性校验。
- `window_id`（规划窗口标识）：可由调用方给定；缺省时使用版本号。
- `forced_replan`（强制重规划请求标志）：只改变回执语义，不绕过版本安全。
- `publish`（是否正式发布）：为假时只返回候选，不推进规划器当前身份。

增量入口还接收 `changed_track_ids`（声明发生变化的目标航迹标识集合）和 `changed_resource_ids`（声明发生变化的资源标识集合）。这些集合是完整性声明，不是性能提示；输入指纹发现漏报时会带原因回退全量规划。

系统级时间语义需保持清楚：D1/D2 的 `measurement_timestamp`（测量时间戳）和 `arrival_timestamp`（到达时间戳）仍由上游合同保留；D3 的 `timestamp`（规划评估时刻）不能替代前两者。当前 `TargetTrack` 通过 `metadata`（扩展元数据）承接必要的上游审计信息，D3 不重新估计测量时间。

### 3.2 `TargetTrack` 目标航迹 DTO

| 代码字段 | 中文含义 | D3 用法 |
|---|---|---|
| `track_id`（航迹标识） | 引用中心维护的全局航迹身份 | 作为计划中的目标身份；不得由 D3 重命名。 |
| `threat_score`（威胁分数） | 归一化到 ([0,1]) 的目标优先程度 | 高分降低分配成本，并提高未分配代价。 |
| `covariance`（协方差不确定度摘要） | 上游协方差的归一化标量或适配结果 | 只作为代价项；D3 不做滤波更新。 |
| `window_cost`（软时间窗代价） | 当前边的时间紧迫或窗口偏好 | 对开放边排序，不等同硬时间窗。 |
| `assignable`（是否允许分配） | 目标是否可进入候选 | 为假时所有真实资源边硬拒绝。 |
| `fov_difficulty_by_resource`（按资源的视场难度） | 资源观察目标的相对困难度 | 进入边代价，可由 D5 反馈写回。 |
| `conflict_risk_by_resource`（按资源的冲突风险） | 路径或资源间冲突摘要 | 进入边代价。 |
| `feasibility_by_resource`（按资源的可行性） | 显式禁配或允许关系 | 为假时对应边硬拒绝。 |
| `hard_time_window`（是否启用硬时间窗） | 是否把开放/关闭时刻作为硬约束 | 与当前规划时刻共同决定拒绝。 |
| `time_window_open_at_s`（时间窗开启时刻） | 该时刻前不允许分配 | 产生“尚未开启”拒绝原因。 |
| `time_window_close_at_s`（时间窗关闭时刻） | 该时刻后不允许分配 | 产生“已过期”拒绝原因。 |
| `time_window_state`（时间窗状态） | 显式开放、关闭或过期状态 | 可直接触发硬拒绝。 |
| `time_window_by_resource`（按资源的时间窗） | 资源特定硬时间窗 | 优先于通用窗口参与边门控。 |
| `demand`（目标资源需求） | 可选的 `TargetDemand`（目标需求 DTO） | 为空时严格退化为单资源独立需求。 |
| `metadata`（扩展元数据） | 反馈事件、来源、审计和适配信息 | 不应被当作未经定义的控制命令。 |

### 3.3 `ResourceState` 资源状态 DTO

| 代码字段 | 中文含义 | D3 用法 |
|---|---|---|
| `resource_id`（资源标识） | 可参与分配的资源身份 | 每个资源最多有一个可执行分配。 |
| `status`（资源状态） | 可用、忙碌、降级或不可用 | 不可用直接硬拒绝；其他状态进入代价。 |
| `health_score`（健康分数） | 归一化健康程度 | 健康越差，资源状态代价越高。 |
| `busy_until`（忙碌截止时刻） | 忙碌资源恢复时间 | 当前时刻早于该值时拒绝。 |
| `operator_hold`（操作员保持） | 外部明确的人工或 resource-hard 要求 | 为真时该资源所有边硬拒绝；普通 pair hold 不得写入。 |
| `load_penalty`（负载惩罚） | 兼容旧接口的负载摘要 | 进入资源状态代价。 |
| `capability_class`（能力类别） | 资源的主要能力标签 | 与需求槽能力要求匹配。 |
| `energy_fraction`（剩余能量比例） | 归一化剩余能量 | 为零时硬拒绝，否则进入代价。 |
| `availability_score`（可用性分数） | 归一化可用程度 | 为零时硬拒绝，否则进入代价。 |
| `current_load`（当前负载） | 当前工作占用程度 | 进入资源状态代价。 |
| `history_failure_rate`（历史失败率） | 历史可靠性摘要 | 进入资源状态代价。 |
| `intercept_feasibility_by_target`（按目标的可达可行性） | 上游给出的目标-资源硬可行性 | 为假时对应边硬拒绝。 |
| `intercept_feasibility_score_by_target`（按目标的可达分数） | 上游给出的归一化可达性 | 为零时硬拒绝。 |
| `metadata`（扩展元数据） | 附加能力、来源和审计信息 | 可补充能力集合，但不执行控制。 |

### 3.4 多资源需求与联盟结构

`TargetDemand`（目标需求 DTO）的关键字段：

- `required_resource_count`（所需资源总数）记为 $k_i$，默认显式构造值为 3。
- `primary_resource_count`（主资源数量）记为 $p_i$，默认显式构造值为 2，并要求 $1\le p_i\le k_i$。
- `coordination_mode`（协同模式）可为独立、同时、顺序或混合。
- `required_capability_counts`（能力需求计数）规定各能力类别至少需要多少槽。
- `arrival_window_start_s`（到达窗口起点）和 `arrival_window_end_s`（到达窗口终点）定义合同窗口。
- `wave_interval_s`（波次间隔）用于按波次平移窗口。
- `minimum_separation_s`（最小时间间隔）只作为合同字段向下游传递。
- `terminal_authorization_scope`（末端授权范围）当前只支持每个主资源独立门控。
- `arrival_coordination_required`（是否要求到达协调）当前默认是假。

若 `demand`（目标资源需求）为空，`effective_demand`（有效目标需求）固定生成 $k_i=1,p_i=1$ 的独立模式。因此“显式需求对象的默认 3 资源混合模式”不能被误写成“所有目标默认需要 3 个资源”。

`CoalitionPlan`（联盟计划 DTO）记录 `coalition_id`（联盟标识）、`version`（联盟版本）、`state`（联盟状态）、`members`（联盟成员）、`required_resource_count`（需求数）、`assigned_resource_count`（已分配数）、`shortfall`（缺口数）和 `complete`（是否完整）。成员由 `resource_id`（资源标识）、`member_role`（成员角色）、`wave_id`（波次标识）、窗口、能力要求和 `executable`（是否可执行）组成。

### 3.5 下游输出

1. `Assignment`（单条分配 DTO）：记录目标、资源、总代价、代价分解、可行性、计划版本、联盟、角色、波次和窗口。
2. `AssignmentPlan`（版本化分配计划 DTO）：记录完整计划身份、规模、分配、未分配目标、联盟、需求满足摘要、代价、决策状态和审计元数据。
3. `AssignmentGuidanceBinding`（D3 到 D7 的导引绑定 DTO）：把当前计划身份和全局航迹身份被动传给 D7，不携带导引参数。
4. `AssignmentValiditySummary`（计划有效性摘要 DTO）：供 D4 和 D6 消费计划年龄、延迟、成本差、旧版本、重复分配、高威胁未分配和重分配计数。
5. `AssignmentRecord`（分配记录 DTO）与 `AssignmentEvidenceExport`（分配证据导出 DTO）：供主运行时和 D6 写盘、重放与校准。
6. `AssignmentFeedbackDecision`（末端反馈建议 DTO）与 `TerminalFeedbackWriteback`（末端反馈写回 DTO）：把 D5/main 已聚合的风险映射到下一轮输入和下游保持建议。

`AssignmentPlan`（版本化分配计划 DTO）的核心字段：

| 代码字段 | 中文含义 | 关键规则 |
|---|---|---|
| `plan_id`（计划标识） | 当前可执行计划身份 | 执行语义不变时保持，不能被成本刷新伪造。 |
| `version`（计划版本） | 严格单调的执行版本 | 只在执行签名变化时推进。 |
| `window_id`（规划窗口标识） | 外部或缺省规划窗口 | 不代替计划版本。 |
| `plan_schema`（计划结构版本） | 当前计划数据合同版本 | 多资源主线发布第二版结构。 |
| `previous_plan_id`（前序计划标识） | 当前计划精确替代的旧身份 | 发布新版本时必须指向最新已发布计划。 |
| `assignments`（可执行分配集合） | 已准入的资源-目标成员 | 不完整联盟不进入该集合。 |
| `unassigned_target_ids`（未分配目标标识） | 当前没有完整可执行分配的目标 | 包含需求不完整目标。 |
| `total_cost`（当前计划总代价） | 当前矩阵口径下的计划目标值 | 保持旧计划时使用旧分配的当前重评分。 |
| `candidate_total_cost`（候选计划总代价） | 求解器产生的候选目标值 | 用于迟滞审计，不一定成为执行计划。 |
| `previous_total_cost_current`（旧计划当前代价） | 旧分配在当前矩阵上的重评分 | 与候选使用同一成本口径。 |
| `created_at`（身份创建时刻） | 当前执行身份首次形成的时刻 | 纯评估刷新保持不变。 |
| `last_changed_at`（最近执行变化时刻） | 计划上次实质变化时刻 | 用于全局驻留时间。 |
| `decision_state`（决策状态） | 接受、保持、释放或重规划回执 | 与详细原因共同导出。 |
| `changed`（执行是否变化） | 本轮是否改变执行签名 | 纯评估刷新为假。 |
| `human_authorization_state`（人工授权状态） | 外部人工审核状态的透传 | D3 不生成自动授权。 |
| `stale_after_s`（计划允许存活时长） | 最近评估后可保持新鲜的时长 | 不取代当前计划身份校验。 |
| `source_node_id`（来源节点标识） | 发布计划的来源节点 | 中心或已验证的二级所有者。 |
| `target_node_id`（目标节点标识） | 计划消息的目标节点 | 用于跨节点审计。 |
| `link_type`（链路类型） | 计划传输链路类别 | 只记录合同，不模拟通信物理层。 |
| `resource_count`（资源数） | 输入资源列表长度 | 不由基准场景常量决定。 |
| `target_count`（目标数） | 输入目标列表长度 | 不要求等于资源数。 |
| `coalitions`（联盟计划集合） | 每个目标的联盟状态和成员 | 一对一目标也有独立联盟表示。 |
| `demand_summaries`（需求满足摘要） | 所需数、已分配数、缺口和完整性 | 区分合法多资源与异常重复。 |
| `incomplete_target_ids`（不完整目标标识） | 联盟需求未完整满足的目标 | 不发布其候选成员为可执行分配。 |
| `metadata`（扩展元数据） | 矩阵、拒绝、迟滞、所有者和证据 | 只用于合同和审计，不绕过结构化门控。 |

多资源调用方应使用 `assignments_by_target()`（按目标返回多条分配）和 `assignment_by_resource()`（按资源返回唯一分配）。旧接口 `assignment_map()`（一对一目标到资源映射）只适用于每目标恰好一条分配；遇到合法多资源目标会抛错，防止静默丢失联盟成员。

### 3.6 主要公开 API

| 公开入口 | 中文用途 | 状态 |
|---|---|---|
| `AssignmentPlanner.plan()`（全量规划入口） | 构造、求解、迟滞、确定身份并按需发布 | 默认主线。 |
| `AssignmentPlanner.plan_incremental()`（增量规划入口） | 只重解安全的局部连通分量 | 已实现辅助入口。 |
| `AssignmentPlanner.publish_plan()`（显式发布入口） | 提交审核后的候选并更新当前身份 | 已实现。 |
| `guidance_bindings_from_assignment_plan()`（导引绑定导出） | 生成 D7 可消费的版本化被动绑定 | 已实现。 |
| `evaluate_terminal_feedback()`（末端反馈评估） | 把反馈映射为继续、保持、重规划或二级仲裁 | 已实现。 |
| `apply_terminal_feedback_to_planner_inputs()`（反馈写回） | 分级写入 edge-soft/hard、资源/目标 hard 和 D7 gate | 已实现并兼容旧 metadata。 |
| `assignment_validity_summary_from_plan()`（有效性摘要导出） | 生成 D4/D6 计划质量与旧版本摘要 | 已实现。 |
| `assignment_records_from_plan()`（分配记录导出） | 生成逐成员 D6 记录 | 已实现。 |
| `assignment_evidence_from_plan()`（计划证据导出） | 导出当前矩阵、边分解、拒绝和所有者证据 | 已实现。 |
| `plan_history_record_from_plan()`（单时刻历史导出） | 生成 canonical、稳定排序、可 JSON 序列化的单 planning-tick 记录 | 已实现 D3 schema/export。 |
| `prepare_secondary_takeover_plan()`（二级接管计划盖章） | 校验所有者、前序、纪元、就绪和租约 | 已实现 D3 侧合同。 |
| `continue_active_secondary_plan()`（活动二级计划续行） | 保持同一二级所有者的严格版本连续性 | 已实现 D3 侧合同。 |
| `run_p1_assignment_calibration_matrix()`（P1 校准矩阵） | 比较确定性全量与增量转换 | 已实现离线校准。 |
| `rank_cooperative_candidates()`（协同候选排序） | 只根据完整实测观测排序候选 | 已实现离线辅助。 |
| `run_p2_capacity_benchmark()`（P2 容量对照） | 比较容量列展开与可选最小费用流 | 已实现隔离对照合同。 |

## 4. 数学模型

### 4.1 集合、变量与约束

设目标集合为 $\mathcal{T}=\{1,\ldots,m\}$，资源集合为 $\mathcal{R}=\{1,\ldots,n\}$。一对一基线定义二元变量：

\[
x_{ij}=\begin{cases}
1,&\text{资源 }j\text{ 分配给目标 }i,\\
0,&\text{否则，}
\end{cases}
\qquad
u_i=\begin{cases}
1,&\text{目标 }i\text{ 未分配，}\\
0,&\text{否则。}
\end{cases}
\]

基本约束为：

\[
\sum_{j\in\mathcal{R}}x_{ij}+u_i=1,\qquad \forall i\in\mathcal{T},
\]

\[
\sum_{i\in\mathcal{T}}x_{ij}\le 1,\qquad \forall j\in\mathcal{R}.
\]

第一式表示每个目标要么获得一个资源，要么显式未分配；第二式表示一个资源不能同时承担多个可执行分配。实现通过为每个目标添加虚拟未分配列，把可选分配转换为标准矩形匹配问题。

### 4.2 可行性门控

令 $a_{ij}\in\{0,1\}$ 表示边是否可行。以下任一条件成立时 $a_{ij}=0$：

- 目标不可分配；
- 硬时间窗关闭、过期或尚未开启；
- 资源被操作员保持、不可用、仍在忙碌期、能量为零或可用性为零；
- 显式目标-资源禁配；
- 上游可达性为假或可达分数为零；
- 需求槽指定的能力类别不匹配；
- 末端反馈规则临时保护旧主资源，导致其他主资源边被锁定。

不可行边的实现代价为配置中的大惩罚 $P$，默认 $P=10^6$。求解后还会过滤任何达到 $P/2$ 的边，避免把惩罚边发布成真实分配。

### 4.3 可解释边代价

对可行边，基础代价为：

\[
C_{ij}=w_W W_i+w_\Sigma \Sigma_i+w_Q(1-Q_i)
+w_R R_j+w_F F_{ij}+w_C G_{ij}+S_{ij}.
\]

变量物理意义：

- $W_i\in[0,1]$：目标的软时间窗代价，对应 `window_cost`（软时间窗代价）。
- $\Sigma_i\in[0,1]$：航迹协方差不确定度摘要，对应 `covariance`（协方差不确定度摘要）。
- $Q_i\in[0,1]$：威胁分数，对应 `threat_score`（威胁分数）。使用 $1-Q_i$ 意味着高威胁目标的真实分配边更便宜。
- $R_j\in[0,1]$：资源状态惩罚，综合状态、健康、旧负载、能量、可用性、当前负载和历史失败率。
- $F_{ij}\in[0,1]$：目标-资源视场难度。
- $G_{ij}\in[0,1]$：目标-资源冲突风险。
- $S_{ij}\ge0$：切换惩罚；只有目标已有旧资源且候选改到不同可行资源时加入。
- $w_W,w_\Sigma,w_Q,w_R,w_F,w_C$：可配置非负权重，当前默认均为 1。

资源状态项的当前实现为先求和后截断：

\[
R_j=\operatorname{clip}_{[0,1]}(
r_j^{status}+1-h_j+l_j+1-e_j+1-a_j+c_j+f_j),
\]

其中 $h_j$ 是健康分数，$l_j$ 是兼容负载惩罚，$e_j$ 是能量比例，$a_j$ 是可用性，$c_j$ 是当前负载，$f_j$ 是历史失败率。状态惩罚对可用、降级、忙碌、不可用分别取 0、0.35、0.5、1；未知状态取 0.25。该和式容易在多个轻度惩罚叠加后饱和到 1，这是当前基线的明确特征，也是后续标定局限。

未分配成本为：

\[
U_i=B(0.5+Q_i),
\]

其中 $B$ 是 `unassigned_base_cost`（未分配基础代价），默认 4。高威胁目标的未分配成本更高；不可分配目标的未分配成本为 0。

一对一目标函数为：

\[
\min_{x,u}J=\sum_i\sum_j C_{ij}x_{ij}+\sum_i U_i u_i.
\]

所有分量进入 `cost_breakdown`（代价分解）并与求解矩阵、选中分配成本、计划目标值和证据导出保持同值。切换惩罚在求解前只计一次，不在求解后补账。

### 4.4 可解释威胁基线

当 AirSim 风格干运行输入没有显式威胁分数时，适配器可调用可解释基线：

\[
Q_i=\operatorname{clip}_{[0,1]}
\left(
\frac{\sum_r \omega_r q_{ir}}{\sum_r\omega_r}
\right).
\]

默认五个分量及权重为：关键区接近度 0.30、TTC 紧迫度 0.30、速度 0.15、协方差 0.10、目标状态 0.15。具体归一化如下：

- 关键区接近度：在默认 500 m 视距内线性从 0 增至 1；缺值取 0.5。
- TTC 紧迫度：5 s 内取 1，60 s 外取 0，中间线性变化；缺值取 0.5。
- 速度：相对默认 40 m/s 线性归一化；缺值取 0.5。
- 协方差：标量直接截断；矩阵迹 $z$ 使用 $z/(z+1)$；缺值取 0.5。
- 目标状态：按已确认、跟踪、暂定、丢失等离散状态映射。

若提供位置、速度和关键区中心，TTC 只在目标速度沿关键区方向存在正闭合速度时计算：

\[
\mathrm{TTC}=\frac{d}{\boldsymbol{v}\cdot\hat{\boldsymbol{r}}}.
\]

这里 $d$ 是到关键区边界的剩余距离，$\boldsymbol{v}$ 是 NED 速度，$\hat{\boldsymbol{r}}$ 是指向关键区中心的单位向量。该函数只是透明基线，不是经过任务结果标定的完整动态威胁评估。

### 4.5 多资源需求槽与全有或全无准入

对目标 $i$ 的需求 $k_i>1$，实现先展开 $k_i$ 个需求槽 $\ell\in\{1,\ldots,k_i\}$。每个槽携带角色、波次、能力类别和窗口。定义 $x_{i\ell j}$ 表示资源 $j$ 是否占用目标 $i$ 的槽 $\ell$，并满足：

\[
\sum_j x_{i\ell j}\le1,
\qquad
\sum_{i,\ell}x_{i\ell j}\le1.
\]

完整联盟可用二元量 $z_i$ 表达：

\[
\sum_{\ell,j}x_{i\ell j}=k_i z_i.
\]

当前代码没有用 MILP 直接求解该等式，而采用确定性需求槽基线：

1. 用普通边代价复制目标的槽行，并应用能力门控和反馈保护。
2. 槽未分配成本附加随威胁上升的大优先惩罚，使高威胁目标更难被牺牲。
3. 运行匈牙利求解。
4. 若某些目标只得到部分槽，选择其中威胁最低者，整目标移出活动槽集合并重新求解。
5. 迭代到剩余目标全部完整满足。
6. 被移出的目标只保留候选成员和需求缺口证据，不发布可执行 `Assignment`（单条分配 DTO）。

因此当前基线保证发布层面的全有或全无，但它是启发式准入过程，不应宣称等价于完整联盟 MILP 的全局最优解。

### 4.6 角色、波次与窗口语义

- 独立模式：一个主资源，波次 0。
- 同时模式：所有槽为主资源，波次 0；是否真的要求到达协调仍由需求合同字段决定。
- 顺序模式：第一个槽为主资源、波次 0；后续槽为重试资源，波次依次递增。
- 混合模式：前 $p_i$ 个槽是波次 0 的主资源；其余槽是波次 1 的备用资源。

第 $w$ 波窗口按：

\[
[t_i^{start}+w\Delta_i,\ t_i^{end}+w\Delta_i]
\]

生成，其中 $\Delta_i$ 是波次间隔。当前实现只发布这些角色和窗口合同，不根据真实 ETA 求解同步到达，不执行备用资源激活，也不约束连续动力学。

## 5. 默认规划算法与执行步骤

### 5.1 全量规划

一次 `AssignmentPlanner.plan()` 调用依次执行：

1. **校验前序计划**：检查当前规划器是否已有已发布身份、前序计划标识和版本是否精确匹配、期望版本是否一致。
2. **构造矩阵**：计算所有目标-资源边代价、未分配成本、硬拒绝原因和证据元数据。
3. **加入切换惩罚**：对旧目标改到新资源的可行边加入一次惩罚；旧资源边、未分配成本、新目标和不可行边不变。
4. **选择已实现路径**：无显式多资源需求时走普通匈牙利路径；显式多资源需求时走需求槽路径。
5. **构造候选计划**：生成分配、联盟、未分配目标、需求满足摘要和候选总代价。
6. **应用短时反馈驻留**：在普通成本迟滞前处理版本匹配的 D5 短暂反馈。
7. **应用联盟成员迟滞**：先判断多资源联盟成员和角色是否允许替换。
8. **应用全局迟滞**：把旧分配在当前矩阵上重评分，再决定保持或释放。
9. **确定执行身份**：比较执行签名；纯评估刷新保留身份，执行语义变化推进版本。
10. **按需发布**：只有 `publish`（是否正式发布）为真时才更新规划器内部当前计划。

### 5.2 普通匈牙利路径

SciPy 科学计算库可用时调用其线性和指派求解器；不可用时自动落到小规模 DP 后备。后备求解器对列数设置 22 的上限，列数包含真实资源列和每目标一个虚拟未分配列，因此它不是大规模替代后端。

选择理由：

- 一对一矩形匹配模型与现有主线严格一致；
- SciPy 实现成熟、延迟低、输入输出可重现；
- 虚拟列自然支持 $m\ne n$ 和部分未分配；
- 外部计划、版本、迟滞和证据合同不依赖具体求解后端。

### 5.3 增量规划

`plan_incremental()` 函数是已实现辅助入口，不会由默认规划器根据单次耗时自动选择。它执行：

1. 校验前序计划和输入指纹。
2. 比较声明变化集合与实际变化，拒绝漏报的局部假设。
3. 在当前可行二部图上，从变化目标、变化资源及其旧绑定出发，求受影响连通分量。
4. 只求解该分量，保留其他仍可行的分配、联盟身份、角色和波次。
5. 合并为完整候选计划后，再统一执行全局反馈驻留和迟滞。

以下情况带 `incremental_fallback_reason`（增量回退原因）回退全量规划：缺少输入快照、变化集合漏报、目标或资源集合变化、需求变化、计划过期、时间相关约束、空受影响分量，或受影响分量已经扩展为全局问题。版本不一致不会静默回退，而是继续硬拒绝。

### 5.4 协同候选预筛

已实现的预筛辅助层生成 27 个候选：末端交接距离 20/30/40 m、主资源到达窗口宽度 3/5/8 s、接近扇区间隔 20/40/60 度。它只修改需求元数据、导出当前计划字段并排序真实观测结果，不改变匈牙利或需求槽求解。

排序优先级是：零安全违规、联盟完成数更高、资源对成功数更高、到达离散更小、候选标识稳定破同分。缺失物理观测不会被预测值补齐。

### 5.5 Canonical 单时刻计划历史

`plan_history_record_from_plan(plan, sequence_index=..., timestamp=..., previous_plan=..., feedback_metadata=...)` 为一个规划时刻生成 `PlanningTickHistoryRecord`。schema 固定为 `d3_plan_history_record_v1`；main 提供的非负 `sequence_index` 和有限 `timestamp` 形成字典序 `[sequence_index, timestamp]`，不能用可能保持不变的计划版本代替时刻顺序。

记录在计划级只保存一次身份、版本、窗口、决策、资源/目标/分配数、所有者/来源、二级纪元/租约、总/候选/前序成本和 stale/rollback/replan 原因。分配按目标、联盟、波次、角色、资源排序，包含主用/备用激活状态、活动标志、联盟标识/版本/纪元、有效性和成本；联盟提供稳定排序的可恢复成员集合。迟滞、成员变化和 feedback soft/hard 分类也使用白名单字段。

调用 `to_dict()` 后只得到 JSON 原生值。该在线历史接口没有真实身份标签参数，并递归排除 truth 命名字段；旧 `assignment_records_from_plan()` 及其离线评估标签能力保持兼容。D3 不负责 JSONL 写盘，也不计算跨时刻 churn。

## 6. 状态机、门控、迟滞与安全规则

### 6.1 规划器身份状态机

`AssignmentPlanner`（分配规划器）是单个仿真回合内有状态的对象，不提供隐式重置。

| 当前状态 | 输入/条件 | 结果 |
|---|---|---|
| 尚无已发布计划 | 前序计划为空 | 允许生成版本 1。 |
| 已有已发布计划 | 前序计划为空 | 抛出 `StalePlanError`（旧计划错误），原因为缺少前序计划。 |
| 已有已发布计划 | 前序标识或版本不匹配 | 硬拒绝，并导出当前最新标识和版本。 |
| 候选未发布 | `publish`（是否正式发布）为假 | 返回候选，不推进当前身份。 |
| 执行签名未变化 | 仅成本或诊断刷新 | 保留计划标识、版本、创建时刻和联盟纪元。 |
| 执行签名变化 | 资源、目标、角色、窗口、所有者、授权或激活语义变化 | 生成严格连续的新版本。 |
| 强制重规划且签名不变 | 外部要求重规划 | 返回“已确认但无变化”状态。 |
| 强制重规划且签名变化 | 外部要求重规划 | 返回“已应用重规划”状态，并只推进一次身份。 |

同一身份再次发布时，执行签名必须完全相同；相同执行签名也不能用新版本冒充执行变化。这两条规则把“评估时间更新”和“执行计划变化”严格分开。

### 6.2 联盟状态

联盟枚举定义形成中、已提交、不完整、已撤销和已完成。当前需求槽规划主线实际生成：

- **已提交**：需求完整，允许生成成员分配；
- **不完整**：资源或能力不足，只记录候选成员与缺口，不发布成员为可执行分配。

联盟成员或角色变化时，`version`（联盟版本）和纪元加一；纯成本刷新保持不变。窗口、所有者或激活等执行语义变化即使成员相同，也可推动计划版本变化。

### 6.3 全局迟滞

旧计划先在当前矩阵上重新计价，记为 $J_{old}$，候选代价记为 $J_{new}$。默认参数是相对改善门限 $\delta=0.2$ 和最小驻留时间 $T_{min}=2.0$ s。普通换配的释放条件为：

\[
J_{new}<(1-\delta)J_{old},
\qquad
T_{dwell}\ge T_{min},
\qquad
N_{change}\le N_{max}.
\]

若最大变更数未配置，第三项不限制。候选减少高威胁未分配目标数时，可通过高威胁释放分支绕过普通三条件；旧计划当前不可行时，也立即释放迟滞。否则保持旧分配，但用当前矩阵更新诊断成本。

### 6.4 联盟成员迟滞

多资源联盟按目标单独维护 `membership_changed_at_s`（成员最近变化时刻）。旧联盟完整且所有旧边仍可行时，成员或角色替换同样要求目标级成本改善超过 20%并满足 2 s 驻留；资源失效、硬禁配、需求结构变化等会立即释放。

该时钟不会被普通评估刷新重置，因此连续规划时刻不会把同一个成员集合错误计为反复换员。

### 6.5 末端反馈状态映射

`evaluate_terminal_feedback()` 函数只给出保守建议：

| D5/main 输入状态 | D3 建议 | 含义 |
|---|---|---|
| 一致或未见风险 | 继续 | 保留当前计划。 |
| 模糊、普通保持 | 保持 | 只提高当前资源-目标边代价并保持 D7，不设置资源级保持。 |
| 需要重新获取、几何/FOV/检测不稳定 | 中心重规划 | 形成边级 soft feedback，进入代价和迟滞。 |
| 友方重叠保持 | 保持 | resource-hard，整资源保持。 |
| verified friend | 保持 | target-hard，目标停止分配。 |
| 不匹配、多帧不一致、跨视角冲突 | 二级仲裁 | 请求 D4/main 处理所有者与降级。 |
| 重复末端锁定风险 | 二级仲裁 | 阻断本地重绑并形成禁配建议。 |

写回函数把已经权威聚合的反馈转换为：

- 安全身份冲突、duplicate 或显式 feasibility reject 对应的硬禁配边；
- 普通 ambiguous/hold/reacquire 与几何/FOV/检测不稳定对应的边级 FOV 代价；
- 仅明确 resource-hard 风险使用的 `operator_hold`，以及 verified friend 的 target-hard；
- 供 D4 的请求和供 D7 的保持动作；
- 带源计划版本、稳定帧数、constraint class/scope 和分类原因的规范化反馈事件。

任何写回均固定 `allow_local_rebind`（允许本地换绑）为假。

### 6.6 短时反馈驻留与主资源保护

在普通迟滞之前，D3 对版本匹配的“主资源锁定稳定性不足”或短暂重新获取执行帧级驻留。有效帧数阈值为：

\[
F_{effective}=\max(F_{D3},F_{upstream}),
\]

其中 D3 默认阈值 $F_{D3}=2$，上游阈值来自 D5 的稳定窗口。未达到阈值且旧主资源仍可行时保持旧主资源；达到阈值后只释放帧级保护，soft candidate 仍必须通过联盟成员和全局 `min_dwell`/收益迟滞。重复锁定、verified friend/友方冲突、错误绑定、资源不可用、显式禁配或旧计划不可行会立即绕过该驻留；普通检测丢失仍是当前边 soft feedback。来自其他计划版本的反馈只用于审计。

另有成员角色保护规则：若所有旧主资源都报告同版本“一致/继续”，至少一个旧备用资源只报告普通“保持”或“重新获取”，且旧主资源边与能力仍可行，则需求槽矩阵固定旧主资源集合，只重解备用槽。主资源自身失败、硬冲突、需求变化或旧反馈会禁用该保护。

### 6.7 身份、协方差与时间安全

- `global_track_id`（全局航迹标识）由中心/D2 维护。D3 只复制到计划和绑定，D5 与 D7 均不得本地改写。
- 协方差必须随 D1/D2 航迹传入；D3 将其作为不确定度代价，但不融合、不缩放为虚假高精度。
- 硬时间窗只以当前规划时刻判断关闭、过期或尚未开启。当前实现不是基于 ETA 的到达时刻可行性证明。
- 计划新鲜度以最近评估时刻加 `stale_after_s`（允许存活时长）计算；旧计划版本不能因新鲜度尚未超时而覆盖当前版本。

### 6.8 D7 绑定门控

一个绑定成为活动且当前状态，至少需要：

1. 计划身份与主运行时声明的当前身份一致；
2. 计划未过期、未撤销且资源未被保持；
3. 联盟存在、版本匹配、状态已提交且需求完整；
4. 成员不是未激活的备用角色；
5. 二级计划还需已激活、持续就绪、领导者纪元单调、租约有效并由调用方显式确认当前身份。

备用成员的绑定固定为保持，原因为备用待命未激活。D3 不提供就地激活开关；角色变化必须进入新的版本化计划。

## 7. 默认、辅助、可选与未实现能力

| 分类 | 能力 | 2026-07-13 的严格状态 |
|---|---|---|
| 默认主线 | 无显式多资源需求的一对一分配 | SciPy 匈牙利算法加虚拟未分配列，已实现并测试。 |
| 默认主线 | 显式多资源需求 | 需求槽匈牙利基线、能力门控、威胁优先和全有或全无发布，已实现并测试。 |
| 默认主线 | 滚动版本、旧计划拒绝、切换惩罚和迟滞 | 已实现；切换惩罚在求解前单次计费。 |
| 默认主线 | 无 SciPy 时的小规模后备 | 位掩码 DP 已实现，但受 22 列上限约束。 |
| 已实现辅助 | 增量规划 | 独立入口已实现；不自动选择，遇到全局或含糊变化会回退全量。 |
| 已实现辅助 | D5 反馈评估与下一轮输入写回 | 已接主运行时合同；仍需真实多种子权重和阈值标定。 |
| 已实现辅助 | D4 二级接管计划盖章与同所有者续行 | D3 只校验所有者、版本、纪元、租约和当前身份；不选择节点或续租。 |
| 已实现辅助 | D6 记录、证据、有效性和校准摘要 | 已实现；D3 不负责写盘总线和跨种子报告。 |
| 已实现辅助 | 27 组协同候选预筛与实测排序 | 已实现；不预测物理成功，不改规划主线。 |
| 可选离线对照 | OR-Tools 最小费用流容量对照 | 接口和结构化不可用状态已实现；当前环境未安装，且不被默认规划器选择。 |
| 可选离线对照 | 容量列展开的 SciPy 对照 | 固定 4 资源/3 目标/5 槽样例目标值为 5.6；只比较槽容量与成本。 |
| 未实现 | CP-SAT/MILP 联盟全局参考模型 | 仅 P2 研究计划，不能写成已有求解后端。 |
| 未实现 | 在线最小费用流自动切换 | 默认规划器没有动态选择该后端。 |
| 未实现 | 完整多窗口、连续到达动力学和同步可达性 | 当前只有合同窗口和轻量当前时刻硬拒绝。 |
| 未实现 | 结果感知的完整动态威胁模型 | 当前只有可解释静态基线和显式输入分数。 |
| 未实现 | 真实通信、时钟漂移和带宽认证 | 属于主运行时/D4 的外部验证边界。 |
| 未实现 | D3 内部分布式拍卖或联盟协商 | 属于 D4，不应在 D3 重复实现。 |
| 未实现 | AirSim 直接控制和飞行器驱动 | 属于主运行时和 D7。 |

## 8. 与其他模块和主运行时的接口关系

### 8.1 D1 传感器融合

D1 提供融合状态、协方差、双时间戳和 NED 工作坐标。D3 只消费归一化不确定度、位置/速度衍生的威胁输入和可达性摘要；不融合原始观测，也不把 WGS84 直接混入内部代价矩阵。

### 8.2 D2 数据关联

D2/中心拥有全局航迹身份和身份连续性。D3 的 `track_id`（航迹标识）必须引用该身份。目标交叉、身份不确定或身份切换计数由 D2/D6 管理；D3 只能通过协方差、可分配状态、禁配边或 D4 建议间接响应。

### 8.3 D4 分布式降级

D3 向 D4 提供当前中心计划、计划有效性摘要、旧版本证据、成本差、重复分配数、高威胁未分配数和末端反馈建议。D4/main 决定中心重规划、二级接管或分布式降级。

二级接管时，D4/main 必须提供具体二级所有者、持续就绪、激活时刻、正且单调的领导者纪元、有效租约和精确前序计划。D3 只验证并盖章版本化计划。中心恢复、租约续期和所有者仲裁仍由 D4/main 负责。

### 8.4 D5 末端关联

D3 给 D5 的信息是“该资源当前应观察哪个全局航迹”，不是重新识别授权。D5 报告一致、模糊、重新获取、不匹配、友方冲突和跨视角冲突；main 聚合后由 D3 写回禁配、FOV 难度或资源保持。任何视觉证据都不能直接替换全局航迹身份。

### 8.5 D6 评估指标

D3 导出计划身份、规模、矩阵、边代价、拒绝原因、迟滞原因、联盟需求满足、角色、波次、所有者、租约和绑定状态，并已提供 canonical 单时刻 history schema/export。D6 负责跨回合统计、物理结果关联和报告。main 尚未把该记录写入现有 40 回合正式 aggregate，D6 也未据此计算 churn，因此联盟成员或版本抖动指标仍必须保持“不可用”，不能补零。

### 8.6 D7 导引

D7 只消费当前、有效、未保持的版本化绑定。每个主资源独立通过当前计划、D4 许可和 D5 锁定门控；当前阶段不要求两个主资源同时到达。D7 负责 ETA/可达性、PN/PNG 和控制，D3 只发布角色与窗口合同。

### 8.7 主运行时

主运行时负责：

- 通过 `--drone-count`（飞行器数量参数）建立资源记录；
- 启动和重置 AirSim、顺序运行回合并移动演员目标；
- 聚合 D1-D7 消息、选择当前计划所有者并调用 D3；
- 每个规划时刻调用 `plan_history_record_from_plan(...).to_dict()`，以 `[sequence_index, timestamp]` 排序合同写盘计划、联盟、反馈、迟滞和结果；
- 把当前计划标识和版本传给二级绑定导出；
- 调用 D6 形成最终证据。

D3 的 AirSim 风格干运行适配器只接收字典或轻量对象，不导入 AirSim，也不能替代上述主运行时职责。

## 9. 2026-07-13 验证状态

### 9.1 模块回归与确定性证据

2026-07-14 当前 D3 回归为 **149 个通过，1 个跳过**。唯一跳过项是当前环境缺少可选 OR-Tools 的已安装求解测试；本轮新增 5 个 canonical history case，验证 primary/reserve、所有者/纪元/租约、soft/hard feedback、迟滞/成本、JSON 序列化、旧 metadata 和 truth 排除。标准命令为：

```bash
python3 -m pytest -q research_modules/d3_assignment_planner/tests
```

已实现的 8 场景确定性校准矩阵覆盖 5v5、3v5、5v3、目标新增、资源失效、高威胁需求变化、D5 备用反馈和硬时间窗。全量与增量路径在 8/8 转换上达到分配与成本等价，并输出回退原因、联盟缺口、高威胁未分配和角色保持证据。该结果是确定性接口验证，不代表真实动态多种子性能已经标定。

### 9.2 已解决问题

截至状态基线，以下 D3 问题已关闭：

1. 已发布当前计划后省略前序计划曾可能导致版本回退；现固定硬拒绝并返回最新计划身份。
2. 切换惩罚曾在求解后追加，可能造成矩阵、目标值和证据不一致；现已前移到求解矩阵并只计一次。
3. 纯成本重评曾可能造成不必要版本抖动；现以执行签名区分评估刷新和执行变化。
4. 备用资源的软保持曾连带旋转健康主资源；现从前序计划推导成员角色并固定健康主资源槽。
5. 多资源需求曾可能被误解为多个独立一对一分配；现有显式需求、联盟、角色、波次、缺口和全有或全无发布。
6. 备用资源可能被下游误当活动成员；现绑定固定为待命保持，只有新版本角色变化后才可执行。
7. 旧中心或二级计划的身份、租约和所有者边界不充分；现有严格当前身份、纪元和租约校验。

### 9.3 真实 AirSim 与跨模块结果

2026-07-11 的 5 资源/2 目标 AirSim 计算机视觉模式 10 个种子中，高威胁目标标签 `T001`（试验目标标识）的双主资源视觉共识和当前计划门控达到 8/10；种子 7 和 27 仍是回归样例。该结果关闭的是 D3 P1 合同层，不等同于物理闭环达到验收门限。

2026-07-13 使用 SimpleFlight 完成 40 个 5 资源/2 目标回合，每种配置 10 个种子：

| 配置 | 联盟完成数 |
|---|---:|
| 基线 | 0/10 |
| 20 m / 3 s / 40 度 | 5/10 |
| 20 m / 5 s / 40 度 | 2/10 |
| 20 m / 8 s / 40 度 | 1/10 |

最佳候选 5/10，未达到 8/10 门限。主要失败来自 D5 未锁定、末端检测获取超时，少量来自检测框面积过小。安全合同没有退化：备用资源越权执行为 0，全局航迹身份改写为 0，在线真实身份标签使用为 0。全部配置合计是 8/40，不能误报为 40 个独立单种子配置。2026-07-14 的 D3 修复证明普通 pair hold 不应扩大为资源不可行；这是 churn 根因线索，不是对这 40 回合的因果证明，因为 aggregate 没有逐 planning tick 计划和反馈历史。

D4 故障矩阵的下游证据显示，二级和分布式提交正例可消费 D3 当前绑定；缺 ACK 会关闭执行许可。该结果证明版本化绑定可被保守门控消费，但 D4 通信协议本身不属于 D3。

### 9.4 当前结论

- D3 当前没有开放的 P0 或 P1 **合同层**缺口。
- P1 **物理性能与参数标定**仍开放：最佳联盟完成数只有 5/10。
- 默认主线仍是 SciPy 匈牙利/需求槽、版本和迟滞；验证结果没有触发算法后端替换。
- OR-Tools 仍未安装，最小费用流只有隔离合同和结构化不可用结果。

## 10. 剩余局限与后续证据需求

1. D3 canonical history schema/export 已实现，但 40 回合正式聚合尚无 main 写盘记录，D6 也未计算联盟成员/版本抖动；指标仍不可用，普通 hold 扩大机制只可列为根因线索，不能据此归因具体回合。
2. 真实 3v5、5v3、目标新增、资源失效和高威胁需求变化仍缺多种子标定；确定性夹具不能代替该证据。
3. D5 反馈写回已接通，但 FOV 权重、禁配边、资源保持、相对收益门限、驻留时间和切换惩罚尚未用真实逐时刻结果联合标定。
4. 硬时间窗只完成单窗口和当前时刻边拒绝基线；没有真实 ETA、多窗口、连续动力学或承诺前缀优化。
5. 威胁基线可解释，但未结合完整目标类别、保护区任务结果和资源结果进行结果感知标定。
6. 需求槽准入保证发布层全有或全无，但不提供 CP-SAT/MILP 意义下的全局联盟最优性证明。
7. 资源状态惩罚采用求和后截断，多个轻度风险可能快速饱和；真实阈值和权重分布仍需 D6 数据校准。
8. 后备 DP 只适合小规模；可选最小费用流未在当前环境得到已安装求解实证。
9. AirSim 故障注入不等于真实无线链路、时钟漂移、带宽限制或多机网络认证。
10. 当前每个主资源独立门控，未把同时到达设为成功前提；不得从窗口合同推导已实现同步协同。

## 11. 中文术语表

| 中文术语 | 英文或代码表示 | 定义 |
|---|---|---|
| 分配计划 | `AssignmentPlan` | 某一规划身份下的完整目标-资源分配、联盟和证据集合。 |
| 执行签名 | `execution_signature()` | 决定计划执行身份是否变化的稳定结构，包括资源、目标、角色、窗口、所有者和激活语义。 |
| 评估刷新 | `evaluation_refresh_only`（仅评估刷新） | 执行语义不变，只更新当前代价和最近评估时刻。 |
| 前序计划 | `previous_plan` | 当前规划调用必须精确延续的已发布计划。 |
| 旧计划拒绝 | `StalePlanError` | 前序身份或版本不满足连续性时的硬错误。 |
| 虚拟未分配列 | dummy unassignment column | 让目标可以显式选择不分配的扩展矩阵列。 |
| 切换惩罚 | `reassignment_switch_penalty` | 目标从旧资源改到不同可行资源时，在求解前加入的附加代价。 |
| 迟滞 | hysteresis | 以收益、驻留时间、变更数量和高威胁条件决定是否换配。 |
| 驻留时间 | dwell time | 自计划或联盟成员上次真实变化以来的时间。 |
| 硬拒绝 | hard rejection | 因不可分配、资源状态、禁配、可达性或硬时间窗而禁止某条边。 |
| 软时间窗代价 | `window_cost` | 只参与开放边排序、不单独造成不可行的代价。 |
| 硬时间窗 | hard time window | 当前规划时刻位于窗口外时直接拒绝边的约束。 |
| 需求槽 | demand slot | 多资源目标展开后的一个角色、波次、能力和窗口位置。 |
| 联盟 | coalition | 为同一目标联合保留的多个资源成员集合。 |
| 全有或全无准入 | all-or-none admission | 只有需求槽全部满足时才发布该目标的可执行分配。 |
| 主资源 | `primary` | 可独立进入下游门控的活动联盟成员。 |
| 备用资源 | `reserve` | 保留容量但默认待命、不可执行的联盟成员。 |
| 重试资源 | `retry` | 顺序模式中后续波次的成员角色。 |
| 联盟纪元 | coalition epoch | 联盟成员或角色变化时递增的版本语义。 |
| 需求缺口 | demand shortfall | 所需资源数减去当前候选成员数的非负差。 |
| 当前绑定 | current binding | 身份、版本、联盟、租约和角色门控均有效的 D3 到 D7 被动绑定。 |
| 本地换绑 | local rebind | 末端资源绕过中心计划自行替换全局航迹身份；D3 始终禁止。 |
| 保守增量规划 | conservative incremental planning | 仅在变化完整且受影响图局部独立时求解子问题，否则回退全量。 |
| 计划所有者 | plan owner | 当前计划由中心或具体二级节点持有的审计身份。 |
| 租约 | lease | 二级计划在给定截止时刻前保持有效的外部所有权合同。 |
| 干运行适配器 | dry-run adapter | 把字典或轻量对象转换为 D3 DTO、但不连接真实 AirSim 接口的适配层。 |
| 多种子 | multi-seed | 在多个确定性随机种子上重复同一配置，用于估计稳定性。 |

## 12. 依据与维护原则

本文依据当前 `README.md`（模块说明文件）、`PLAN.md`（模块计划文件）、`models.py`（数据模型源码）、`costs.py`（代价模型源码）、`solver.py`（求解器源码）、`planner.py`（规划器源码）、适配与校准源码、D3 测试、D3 差距审计/综述，以及 `MAIN_P1_CONVERGENCE_VALIDATION_REPORT_20260713.md`（主 P1 收敛验证报告）编写。

后续只有在代码、测试和正式验证证据已经改变能力状态时，才应更新本文对应结论。计划项、可选依赖、一次性候选结果或跨模块设想不得单独升级为“默认主线已实现”。

## 13. 保持计划与候选目标范围隔离（2026-07-14）

迟滞中的“保持”必须保持整个可执行身份，而不只是资源-目标 assignment 集合。可执行
身份还包括 coalition、unassigned/incomplete scope、授权状态和 owner/version。
如果 D2 在某 tick 新增候选航迹，而 D3 因 dwell、收益门限或成员迟滞决定 hold，
该候选不能先进入 current plan 的 unassigned scope，否则即使 assignment 不变，
execution signature 仍会变化并错误生成新版本。

当前实现遵循：

```text
当前 D2 候选集合
  -> 计算 candidate plan
  -> hysteresis hold
  -> 保留 previous current execution identity
  -> 候选只写入 hysteresis_candidate_* 审计
  -> release 后才形成新 current plan/version
```

这不是目标识别过滤器。D3 仍以 D2/main 提供的 `assignable` 为准，不使用 AirSim
truth，也不按已知物理目标数截断。真实 seed 001 中 T008 是 D2 后段新生航迹；是否为
幻影必须由 D2 生命周期和 main 准入合同解决。D3 只保证在迟滞未释放时不提前赋予它
current execution identity。

## 14. 同窗口累计变更与双成本口径原则（2026-07-14）

迟滞收益不能直接比较两个来源不同的 objective。D3 现在显式区分：

- **候选搜索成本**：包含 switch penalty、soft-feedback FOV shaping、demand-slot
  priority 和 role pin，用于减少搜索空间并生成候选；
- **执行比较成本**：candidate 与 previous 均按当前 tick 的基础边成本、硬可行性和
  当前 demand/unassigned 规则重评分，用于 `delta` 和 membership gain；schema 为
  `d3_hysteresis_current_objective_v1`。

`max_changes_per_window` 的“窗口”由调用方 `window_id` 定义。计划 metadata 在同一
window 内累计已经接受的 assignment change count；普通 hold 和评估刷新不增加，
新 window 从零开始。目标消失、资源硬失效以及 plan-level owner/activation/
authorization 变化属于 fail-closed release，不可被普通预算阻止，但必须记录 bypass
和 release reason。primary/reserve 成员候选仍属于 coalition membership 变化，不能
伪装成外部 activation 来绕过迟滞。

最新真实动因是 1 个 M5N2 seed 的 347 records、v1..v35；本批验收是 5 个新增
确定性测试函数，全量 `157 passed, 1 skipped`，零失败。没有重跑 AirSim，因此真实
10-seed 稳定性、上游 lifecycle admission、runtime reserve demotion 和 `8/10`
coalition completion 仍保持开放。动态 M/N、truth 隔离和中心 `global_track_id`
所有权原则未改变。

## 15. Actual-v2 证据分层原则（2026-07-14）

真实运行的 command、actual metrics 和 canonical history 必须携带同一计划身份。
tuned 2v2 seed 1 三层均为 `d3-plan-c3cc6d28c365/1`，history 24 条；M5N2
seed 1 三层均为 `d3-plan-cfdd088a10e1/1`，history 214 条。D6 两个 history
case 均 available 且无 validation reason，故运行级计划身份 P0 证据链关闭。

M5N2 feedback churn 为 50，但计划版本、成员和 owner churn 为 0；物理
pair/target/coalition 为 `2/3`、`2/2`、`0/1`。目标级 `2/2` 不等于联盟
完成，第二 primary 的 5 m 闭环与多 seed 仍属 P1。

## 16. M5N2 20-Case 对算法原理的验证（2026-07-15）

本批采用 5 个资源、2 个目标：高威胁 T001 显式要求 2 个 active primary 与 1 个
standby reserve，T002 要求 1 个 primary。20 个真实 AirSim case 共写入 `3725` 个
canonical planning tick，每条都保留动态 N/M、计划版本、成员角色、联盟状态、迟滞
与反馈审计。这验证了 D3 原理中的三点：

1. **资源数与目标数解耦**：所有记录均为 `resource_count=5`、`target_count=2`，
   不是方阵 N 对 N 假设；每 tick 的 4 个 assignment 来自任务需求槽，而不是写死数量。
2. **执行身份与候选评估解耦**：每个 case 只有一个 current `plan_id/version=1`，
   `3555` 次成员候选评估均未改变实际 roster；其中 `3524` 次由成员迟滞保持，另有
   `31` 次通过成员层后被全局迟滞保持。
3. **角色而非资源编号定义协同成员**：19 个 case 的 T001 primary 是
   `INT-02/INT-03`，另 1 个 case 是 `INT-01/INT-02`。第二 primary 必须按当前计划、
   target 和 role 识别，不能固定成 `INT-03` 或数组第二项。

物理层 pair `12/60`、canonical target `12/40`、coalition `0/20`，第二 primary
`0/20` 进入 5 m。该结果说明“计划完整且稳定”不是“协同物理完成”的充分条件；
D3 的职责是形成 current coalition 和抑制无依据换员，D5/D7/runtime 还必须完成视觉、
控制和碰撞诊断。20 个 `collision_stop` 没有碰撞对象证据，不能据此调整 D3 成本或
推断分配器退化。candidate 非退化失败同理只是不满足系统级晋级条件。

统计术语必须保持分层：`canonical target success` 指 D6 的标准目标级结果，
`cooperative target diagnosis` 指 T001 的两个 primary、第二 primary 和 coalition
诊断。前者不能替代后者。额外 `png_ttc_2v2_seed001` 和未执行 dropout case 不进入
本节样本，缺失项保持不可用。

## 2026-07-20 三维稀疏与学习辅助原则

1. **规则和确定性求解器是主线**：三维可达性、NED 协方差、区域、容量和友方冲突
   先形成 `C_rule` 与 hard mask；最终仍由 Hungarian/demand-slot solver 生成计划。
2. **学习只能修正候选边成本**：唯一公式是
   `C_final=C_rule+alpha*tanh(delta_C)`。模型不得直接输出 assignment、联盟成员、
   `global_track_id`、plan owner 或 version。
3. **稀疏动作而非固定大动作头**：策略按共享网络处理候选边集合 `E x 12`。200v200
   的确定性样本只有 800 条策略边，不定义 40,000 个自由动作。
4. **硬约束不可学习绕过**：不可达、容量耗尽、友方冲突、区域拒绝和版本不匹配全部
   mask；published stale plan 仍由 planner 抛出 `StalePlanError`。
5. **回退必须逐元素等于规则矩阵**：timeout、低置信、OOD、模型异常和非法输出均
   返回 `C_rule`；shadow 建议不进入 solver。
6. **能力声明按证据分层**：2026-07-20 只完成 13 个新增确定性测试和 32-edge synthetic
   BC 预热。全量为 `170 passed, 1 skipped`；尚无真实训练集、checkpoint、PPO、
   多 seed shadow 非退化或 AirSim 物理验收。

解析 constant-speed reachability 只用于候选预筛，不代替 D7 三维动力学、障碍规划、
友方轨迹解冲或区域配额策略。区域编号和邻区许可必须来自上游合同，D3 不根据 truth
自行创建区域或改写中心航迹身份。

## 17. 大规模向量化稀疏分配原则（2026-07-20）

稀疏候选必须在成本构造阶段生效。旧实现虽然在求解前只保留每个目标的 top-k 边，
仍会先对全部资源-目标组合逐边调用 Python 规则函数，并为后续剪枝边构造完整解释
字典。在 200 个资源、200 个目标、每目标 32 条候选边时，该过程仍处理 40,000 个
Python 边对象，稀疏化没有降低主要计算开销。

当前可扩展三维配置采用以下顺序：

```text
资源和目标数组
  -> NumPy 批量计算三维截获、协方差、资源状态和区域项
  -> 应用不可达、容量、友方冲突和区域硬门控
  -> 按规则成本和资源编号确定性选择每目标 top-k
  -> 仅为候选边物化完整成本解释
  -> 按候选二部图连通分量运行局部 Hungarian
  -> 进入原有迟滞、M-to-N 准入和版本发布链
```

向量化只覆盖核心数组合同。资源-目标字典覆盖、按资源时间窗和其他复杂 pair-specific
约束继续自动使用旧参考路径，避免改变既有优先级。候选数仍不低于目标需求数，上一
有效计划中的可行成员仍被保留。SciPy Hungarian、未分配代价、全有或全无联盟准入、
学习残差上界和规则回退语义均未改变。

2026-07-20 的独立基准使用同一 200×200 输入、top-32、同进程重复 5 次。旧路径中位
耗时 1904.261 ms，新路径 85.367 ms；两者均完成 200 个分配。新路径批量计算全部
规则标量，只为 6,400 条候选边生成解释字典，Python 全边规则调用为 0。该结果是
D3 模块基准，不代表全栈 AirSim 实时能力。

## 18. 区域所有权与联盟提交原则（2026-07-20）

D4 负责判断中心、二级节点或完全分布式层级，并裁决区域 owner。D3 不重复故障判断，
也不自行选举 owner。D3 只消费 `RegionalAuthorityInput`，验证裁决结果后生成一个
普通、版本化的 `AssignmentPlan`。一个计划可以同时包含多个二级 owner，也可以包含
完全分布式 peer owner；每条分配保留 region、owner、epoch、lease 和 commit 证据。

区域发布采用 fail-closed 原则。D4 输入必须引用当前 `plan_id/version`，区域 epoch
不得回退，lease 必须覆盖发布时间，资源不能重复分配，指定成员必须仍通过 D3 规则
候选和能力门控。所需资源数为 1 时，D4 的区域所有权、epoch、lease、执行许可和唯一
成员构成单成员授权；distributed 层级也不把它伪装成原子联盟。若 D4 提供单成员
summary，D3 只接受 `single_member_authorized`、非 atomic、成员授权完整且租约有效的
证据。所需资源数大于 1 时仍必须提供 committed、atomic committed、完整成员确认、
同一 epoch、匹配成员集合和未过期 lease。任一条件不满足时，D3 抛出明确拒绝原因。

区域计划继续使用现有计划版本和迟滞机制。真实执行身份改变时版本严格递增；旧来源
计划由 `StalePlanError` 拒绝；候选若被迟滞保持且没有形成区域合同，也不得伪装为
已提交计划。当前只完成 D3 模块级合同和单元测试。main 尚需把 D4 区域裁决映射到该
接口，并在中心失效、多个二级 owner、二级失效和网络分区场景中完成运行时验收。

计划 metadata 使用 `single_member_authority` 和 `atomic_coalition_commit` 区分两类
授权，同时记录 `regional_commit_required`、实际状态和 evidence 是否存在。该区分供
D6 分别统计区域单成员授权与多成员原子提交，不改变 k>1 的全有或全无原则。

## 19. 故障代际隔离原则（2026-07-20）

D4 在中心或二级 owner 变化前要求新的计划 generation，以便旧 owner 的消息、租约和
授权不能继续引用同一代际。普通 `plan(..., forced_replan=True)` 仍受执行签名和迟滞
规则约束；分配未变时返回原版本是正确的重规划语义，但不能满足故障隔离。因此 D3
提供独立的 `advance_authority_generation()`，把“重新求解”与“故障代际隔离”分开。

Fence 具有以下不变量：

1. assignment 的目标、资源、角色、波次和 coalition 绑定不变；
2. coalition identity、version、成员和状态不变；
3. owner、human authorization、activation 和 executable 语义不变；
4. 只生成新的 `plan_id` 和严格递增 `version`，assignment 的上下文版本同步更新；
5. metadata 声明 non-reassignment、non-execution-authorization 和 D4 gate required；
6. 发布后旧 generation 立即被 D3 stale 检查拒绝。

`publish_plan()` 仍禁止普通相同执行签名的新身份。只有 schema、来源计划、前序版本、
非重分配和非授权标记全部匹配的 fence 可以通过该例外。声明 fence 后再篡改 assignment、
coalition、owner 或授权会被拒绝。该计划本身不是 D4 decision，也不能使 D7 从 hold
切换为 continue。

## 20. 学习研究数据、策略与晋级原则（2026-07-20）

1. **完整 catalog 先于切分**：采集帧只能标记 `unassigned`；finalize 取得全部唯一数值
   seed 后，按 seed 数量一次性分配 train、validation 和 test。scenario、规模、episode
   均不得改变 seed 身份，同一数值 seed 的所有帧必须原子进入同一 split，三组数值 seed
   两两不交。少于 3 个唯一 seed 或 test 少于声明 unseen 数时失败关闭。
2. **只存匿名派生状态**：帧记录使用 `target_0000/resource_0000` ordinal token，保存
   TargetTrack/ResourceState 的允许字段摘要、候选边特征、action mask、规则成本/选边、
   前序版本、反馈/迟滞和离线 reward 分量。不得保存 truth actor ID、原始 track/resource
   ID 或任意未审核 metadata。
3. **策略不拥有分配权**：共享边 actor 只输出当前候选边的 bounded residual；低频
   head 只给出 neutral/hold/replan 建议。容量、友方冲突、不可达、区域、demand slot、
   stale version 和最终 assignment 始终由 deterministic mask/solver/planner 处理。
4. **变长边而非固定动作表**：actor 输入为 `E x 12`，`E` 是当前帧候选边数；同一
   参数处理 3v5、5v3、200 edges 或更大稀疏图。value 从 masked mean-pooled edge context
   计算，不定义固定 200x200 head。
5. **数据和模型版本必须绑定**：dataset/frame 为 `d3_learning_dataset_v2`，split policy
   为 `d3_numeric_seed_atomic_split_v2`，bundle 为 `d3_learning_model_bundle_v2`。manifest
   固化 split 参数、逐 split 数量、split hash 和完整 frame SHA；bundle 再绑定 dataset/
   split policy。v1 不兼容并稳定拒绝，模型加载只用 weights-only，不宽松或部分加载。
6. **shadow 先于 assist**：shadow 在同一 scenario/seed/frame 上比较规则与 proposal，
   但不改规则矩阵或发布计划。assist 需要显式配置，并且 manifest 必须证明至少 20 个
   全局数值未见 test seed、零 fallback、安全和 assignment-cost 非退化；unseen 计数
   不得把同一 seed 在多个 scenario 重复累计，不足时 promotion 为 false/unavailable。
7. **导出内存必须有界**：D3 writer 逐条消费 iterator，使用磁盘暂存完成全局 seed
   finalize 和稳定排序。frame SHA 与 split audit 不因流式写出而降低。调用方不得先把
   staging JSONL 整体 `read_text().splitlines()` 后再构造全量 record tuple。
8. **能力按证据分层**：当前已实现 v2 数据、bundle、多 episode BC、原生 clipped PPO、
   paired evaluator 和 CLI；历史 30-seed smoke 属于 v1，不是 v2 性能证据。没有正式
   权重、真实 D2/D3 训练、AirSim 物理收益或 20 未见真实 seed 准入。

hold/replan head 当前用于 BC/PPO 和离线 counterfactual rollout，未接入在线 planner
发布状态机。在线 `LearningCostAssistant` 仍只消费 residual，并执行
`C_final=C_rule+alpha*tanh(delta_C)`；这一限制避免研究建议绕过既有迟滞、版本或人工
授权链。

## 21. 单帧只读规划证据原则（2026-07-20）

1. **矩阵必须来自同一次规划**：`C_rule` 在规则成本、候选稀疏化和换绑 penalty 完成后
   固化；`C_effective` 是 shadow/assist/fallback 处理后真正交给 solver 的矩阵。main
   不得再次调用私有成本函数重建标签。
2. **四种学习结果不可混写**：无模型为 `rule_only`；shadow proposal 单独保存且
   `C_effective == C_rule`；assist 才允许 `C_effective` 含有界 residual；fallback 必须
   逐元素回到 rule 并携带 reason。
3. **只保留一帧且先清旧帧**：新 planning attempt 开始即替换旧证据。只有矩阵、输入
   roster 和最终 plan 一致时 `available=true`；异常、stale、invalid regional 或无成本
   fence 只留 unavailable reason，禁止退回上一成功帧。
4. **证据不是在线消息**：它只存于 `AssignmentPlanner` 本地，不附加到 plan metadata，
   不改变 D4/D7 DTO。所有实体 ID 在快照时变为 ordinal token，上游 metadata 与
   truth/actor/object/node alias 全部剥离。
5. **调用者不能反向修改规划器**：矩阵来自独立不可写 buffer，mapping 只读，plan 和
   entity 是最小安全副本。由 helper 生成的 `LearningFrameRecord` 即使被离线调用方修改，
   也不影响 planner retained evidence 或已发布计划。
6. **状态机结果必须可审计**：held、unchanged 和 forced-replan ack 使用当前 tick 的
   矩阵/timestamp；regional 另标 selection source。无法映射当前 roster 时宁可
   unavailable，也不生成看似完整的学习标签。

2026-07-20 的 11 个专项测试覆盖上述原则及 1x3、3x2、7x4 动态 shape。D3 全量
226 项结果为 `225 passed, 1 skipped`，零失败达到门限；这不代表 main 已导出真实
AirSim seed，也不改变 shadow/assist 的准入边界。

## 22. 区域建议只能约束候选，不能取得规划权（2026-07-20）

1. **提示必须属于上一计划**：区域提示的 source `plan_id/version` 必须与调用时的
   `previous_plan` 完全一致；created/expiry、逐区域 epoch/lease 和当前 episode 时钟必须
   同时有效。reset、旧 generation 或区域集合不一致均视为 rejected hint。
2. **只接收 D3-owned 值对象**：公共 DTO 和 schema 由 D3 定义，mapping 采用字段 allow
   list，禁止 D4 控制对象以及 truth/actor/object/target/resource identity 泄漏。
3. **projected 才可影响候选**：quota delta 必须总量守恒并与邻区 transfer 净额逐区域
   一致；hold、reserve、owner 和 request-replan 都是显式合同字段。非法输入必须记录
   reason 并完整回退原规则规划，禁止静默解释为零。
4. **commit 和 reserve 先于 transfer**：上一计划 assignment/coalition 成员不得进入新
   跨区资源池；post-quota reserve floor 也必须留下。许可数超过可安全解释资源时拒绝
   整个提示。
5. **Hungarian 保留最终裁决**：同区边沿用原规则，跨区边只对固定大小且互斥的许可池
   开放；学习只能修改这些候选的有界成本。资源唯一性、M-to-N all-or-none、D5 hard
   feedback、迟滞和版本状态机继续由 D3 决定。
6. **建议不等于授权**：该入口不选择区域 owner、不提交 coalition、不授权 D7，也不
   替代 `plan_regional_authority()`。metadata 的 applied 只表示候选约束生效。

2026-07-20 的 14 个确定性 fixture case 和 240 项全量回归结果为
`239 passed, 1 skipped`，门限为零失败；这不是 main/D4 接线、多 seed 性能、AirSim 或
物理拦截证据。

## 23. 学习数据与晋级必须保持双重真值隔离（2026-07-20）

1. **test 不是训练数据**：BC 只允许 train/validation，PPO 只允许 train；训练入口看到
   test frame 必须拒绝。dataset loader 可以读取完整文件以验证 canonical SHA、split 和
   统计合同，但 test 的特征、标签和 seed 不得进入 normalization、更新或训练期指标。
2. **匿名 schema 必须正向声明**：frame v2 只接受固定字段集合。未知普通字段需要新
   schema；任意层级的 truth/actor/identity、实体 ID、UUID、vehicle name 类键均拒绝。
   兼容项仅为 ordinal token、声明过的强类型匿名字段和不携带实体身份的 hard-reject
   reason 计数。
3. **candidate 不是 permission**：candidate mask/hint 在候选索引、assistant 返回和
   solver 消费处都必须与 hard reject reasons 求交，形状不一致宁可 unavailable。学习只
   处理最终允许边，不能恢复 D5、可达性、容量、友方冲突或版本禁边。
4. **完整内容与模型共同绑定**：bundle 和 promotion evidence 必须同时绑定 split hash、
   canonical frame SHA256 与 state-dict SHA256。assist 只接受严格类型、eligible、正式
   test、paired rule/residual、`rule_cost_matrix_v1` 口径且摘要一致的证据；任何 bypass、
   validation、synthetic/non-eligible 或错配都回退规则。
5. **非退化只能在共同代价坐标系声明**：proposal 用
   `C_rule+alpha*tanh(delta_C)` 选边；rule/proposal 的最终 assignment 都必须用同一
   `C_rule + unassigned_costs` 重新评分。模型输出不是 assignment、coalition、计划版本
   或 D7 授权。

本轮 252 项全量回归为 `251 passed, 1 skipped`，零失败门限通过，skip 仅 optional
OR-Tools。该证据关闭 D3-owned 的上述软件合同缺口，但没有正式模型权重、至少 20 个
未见真实/高保真 test seed、promotion 结论、AirSim 收益或物理执行证据。

## 24. 大规模学习记录的流式确定性原则（2026-07-20）

D3 学习记录优化遵守“内容先于速度”。`d3_learning_dataset_v2` 的字段、精度、candidate
edge、dense rule matrix、action mask、匿名实体、split 和 SHA 均保持不变；不能通过删除
字段、降低精度或压缩候选数制造性能提升。每个 record 写盘前重新执行结构、有限值、
掩码、匿名 token 和身份字段校验，构造后修改可变 NumPy 数组或 mapping 仍失败关闭。

数据集收口分成两个有界阶段。采集阶段将每帧只 canonical 编码一次，临时 SQLite 只保留
稳定排序键和 sidecar 字节偏移。输出阶段按键排序读取单帧字节，替换 writer 自己生成的
唯一顶层 split 占位符并增量计算 SHA。这样不再为排序把全部 frame 常驻内存，也不再为
写最终 split 解码密集数组、重建对象并再次编码。正序和逆序输入必须产生逐字节相同的
`frames.jsonl`、manifest 和 hash。

200×200 top-32 微基准中，每帧 6,400 条候选边、约 2.20 MB。单帧构造中位数由
48.19 ms 降至 22.99 ms，6 帧 finalization 由 910.20 ms 降至 243.65 ms。该结果只说明
D3 局部导出路径；它不能解释 main 的 D3/D4/D5 总 staging 时间，也不是模型、AirSim 或
物理拦截性能。测试不设置墙钟阈值，只校验内容等价、顺序确定、篡改拒绝和失败关闭。

当前主要剩余成本是 NumPy `tolist()` 与标准库 canonical JSON 编码。改变编码格式或引入
第三方高性能编码器会形成新的兼容和依赖问题，必须另建 optional adapter 并做 schema/
hash 对照，不能直接替换默认持久化合同。本批全量结果为 `254 passed, 1 skipped`。

## 25. 模块计时与联合计时分离原则（2026-07-20）

性能结论必须同时保留模块分项和跨模块总量。main 的 clean-tree nominal 200v200 三 seed
复测中，D3 stage 分别为 0.0917 s、0.1129 s 和 0.0999 s，6 帧数据正常最终化，在线真值
使用为 0。这是 D3 导出路径进入统一三维质点生成链后的直接证据。

同一复测的总生成时间由 467.8007 s 降至 262.2866 s，联合 finalization 由 116.5624 s
降至 7.7377 s。联合 finalization 同时包含 D3、D4、D5，不能把该差值记为 D3 单模块收益。
后续优化同样以 `d3_stage_wall_s` 和联合阶段字段分别报告，避免用系统总量替代 owner 证据。
本节形成时正式 900 episode 和训练尚未执行；其后正式数据与 BC 开发训练已完成，见下节。
外部保留 seed 1000-1019 和 assist 准入仍需单独验收。

## 26. 正式行为克隆模型的开发准入原则（2026-07-20）

1. **内部 test 不是最终保留集**：正式数据内部三分用于训练开发和过拟合诊断。即使内部
   test 有 20 个 seed，也不能替代预先隔离的 1000-1019。bundle 必须把两者状态分开。
2. **学习只改变允许边的相对成本**：行为克隆学习规则已选边与未选边的有界 residual，
   最终仍由 demand-slot Hungarian 决定资源唯一性和未分配。学习输出不产生计划版本、
   联盟成员、目标身份或 D7 控制许可。
3. **类别不平衡必须显式绑定配置**：正式数据正边约占候选边 3.2%。训练可使用有上限的
   正类权重，但权重值必须进入 bundle 配置和报告，不能隐式改变损失口径。
4. **非退化使用共同规则成本**：rule-only 与 BC shadow 可用不同矩阵选边，最终成本都
   回到原 `C_rule + unassigned_costs`。本轮 internal-test 平均差为 +0.022345，因此不
   满足成本改善判断。
5. **安全不退化不等于模型可晋级**：本轮 duplicate 和 hard violation 均为 0，需求满足
   与规则相同；边排序 0.8031、计划一致 0.6770，且 163/322 帧 OOD 回退。安全门控有效，
   模型质量和门限仍未达到 assist 证据要求。
6. **开发 bundle 必须先于 promotion 失败关闭**：v3 admission 的 stage 为 development
   时，只允许 shadow。即使 promotion 字段被改写为 recommended，loader 仍返回规则路径。
7. **模型文件和代码版本分开管理**：普通 Git 保存训练配置、数据摘要、指标、定位说明和
   权重 SHA256；`.pt` 保存在 ignored output。长期权重使用 Git LFS 或独立制品存储。本机
   Git LFS 不可用时，不得把二进制权重临时提交到 results。
8. **基线提交不能替代训练源码摘要**：训练发生在有 D3 模块改动的工作树时，Git 字段必须
   标为数据/训练基线角色，并同时记录工作树状态和训练源码 SHA256，禁止写成 clean commit。

当前 v3 权重 SHA256 为
`e3da9fd5b54451da83358405b6051991e0c78bcf9f538b350d459b05faf8e0b2`，只作为开发 shadow
模型。PPO 未启动，AirSim 和物理闭环均未由本轮验证。
对应全量回归为 `257 passed, 1 skipped`，skip 仅 optional OR-Tools。

## 27. 联合训练先绑定共享 Seed，再读取样本（2026-07-21）

模块内数据切分解决单个数据集的泄漏问题，跨模块训练还需要共同的 seed 注册表。D3 在
C1 路径中先验证 main 提供的 detached registry，再允许训练入口消费样本。验证顺序包括
schema 和 policy、registry content 与 assignment 哈希、源 training registry 文件哈希、
完整 seed 集合、逐 seed split，以及保留 seed 排除。任一条件不成立即停止，不采用局部
重算结果继续训练。

共享注册表只描述数据分割，不取得规划权。它不能改变 Hungarian、需求槽、硬拒绝、迟滞、
计划版本或 D7 binding，也不能证明学习模型优于规则模型。新 bundle 可以记录已验证 binding；
旧 bundle 保留开发兼容，但没有 binding 时不能作为 C1 联合训练产物。正式 100-seed 数据
已与共享映射逐项一致，现有 BC 仍为 `development/shadow-only`，PPO 未启动。

## 28. 全样本通过不等于运行授权（2026-07-21）

正式学习数据审计分为数据结构、运行绑定和在线授权三个层次。数据结构层检查每个文件、
episode、决策帧和候选边是否可读、有限、维度一致，并验证 seed 切分、容量、需求槽、
匿名身份和前序版本。运行绑定层需要当前计划 owner、当前 plan version、实际应用应答和
结果归因。在线授权还需要同 seed 配对 shadow 的安全与性能非退化。前一层通过不能替代
后一层证据。

本批 900 个实际 episode、1604 个决策帧、3658815 条候选边和 117304 条选中动作的数据
结构审计为 0 违规。规范数值 seed 切分是 60/20/20；实际 episode 和决策帧分别是
540/180/180 与 962/320/322。该区别是统计原则的一部分。训练、验证、测试的比例必须按
各自单位报告，不能把 seed 比例写成样本比例。

学习帧有 `previous_plan_version`，可以检查非负和不回退。它没有当前 owner/current
version，因此不能证明 stale plan 已被运行时拒绝。匿名 token 及严格字段白名单保证
在线 truth 字段和 `global_track_id` 未进入正式学习数据；它们也不能证明运行期间没有
发生其他模块的 ID 错绑。身份安全结论只覆盖当前数据合同。

`reward_components` 保存规则成本、高威胁覆盖、未满足槽、抖动、过期和安全拒绝等诊断
分量。这些分量来自规则教师帧，不是实际执行结果，也没有 applied ACK、反事实基线或
因果归因。正式全样本结构审计完成后，PPO、assist、在线权限和权重写入仍关闭。规则代价
与需求槽匈牙利继续作为默认路径，直到运行绑定和配对非退化证据单独通过。
