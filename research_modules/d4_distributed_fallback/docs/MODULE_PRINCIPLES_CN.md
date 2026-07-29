# 分布式协同与降级接管模块原理（模块编号 D4）

## 2026-07-29 v4 observable-group 置信校准原理

v4 正样本表示外部 target 在同一快照和同键规则基线 \(R_0\) 下形成安全可执行差异，
no-op 表示负样本。训练集正、负样本数记为 \(N_+\) 和 \(N_-\)。正样本权重为

\[
w_+=\min\left(\frac{N_-}{N_+},8\right),\qquad w_-=1.
\]

有向边动作中，非零和零目标数记为 \(E_+\) 与 \(E_0\)。边损失使用

\[
w_e^+=\min\left(\frac{E_0}{E_+},32\right),\qquad w_e^0=1.
\]

两个上限限制少数类样本对梯度的放大。计数和权重只从 train 计算。validation 只承担
模型选择和审计，test payload 不加载。权重对象绑定训练标签清单摘要；非有限值、篡改、
缺少任一类别或试图用 validation/test 拟合权重时立即拒绝。

checkpoint 选择使用字典序规则，先要求 validation 同时命中正负两类，再比较较低类别
命中率、平衡命中率、固定 train 权重 loss 和 epoch。新数据的 actor 最佳 epoch 107，
train 正/负命中 58/60、276/290，validation 为 13/15、58/60。拒绝记录没有被过滤。

置信可辨识性键为

\[
k(g)=H(\mathcal{A},X_V,X_E,A,S,D),
\]

其中 \(\mathcal{A}\) 是固定图网络架构，\(X_V\)、\(X_E\)、\(A\) 分别是节点特征、边特征
和边索引，\(S,D\) 表示 shape 与 dtype。节点或边身份、seed、episode、target 和来源
身份不进入键。新 observable-group 数据形成 272 个键，混标和 target conflict 均为 0。

冻结 actor 后，confidence train 标签为 58 正、292 负。14 条“可执行但错误”负例是
安全门最危险的样本，其 TRAIN-only 权重为

\[
w_{\mathrm{hard}}
=\min\left(\frac{292}{14},32\right)
=20.857143.
\]

正类权重为 5.034483，16 条动作不一致负例使用上限 8，普通负例为 1。validation/test
不参与权重计算。

固定置信门 \(p_0=0.60\) 转成 logit 中心 \(z_0=\log(p_0/(1-p_0))\)。训练设置
0.20 间隔：正类向 \(z_0+0.20\) 推进，负类向 \(z_0-0.20\) 推进，只累计边界内侧的
平方距离。该目标直接对应运行门，不改变 0.60。模型仍使用原线性 confidence head。

完整复跑有 8 个合格 epoch，最长连续 7 个。最佳 epoch 66 的
positive/negative/inconsistent/executable 计数为 train `12/0/0/12`、validation
`4/0/0/4`。这些结果只证明训练机制和固定门验收在该只读数据上成立；clean candidate、
登记、D3 后继、D6 审计和收益仍未完成。生产权限继续为 false，v3 不受影响。

## 2026-07-29 规划资格模型

区域建议需要区分“能否参与下一轮计算”和“能否执行当前计划”。D4 将区域能力写成

\[
\mathbf{g}_r=(p_r,a_r,c_r,t_r,u_r),
\]

其中 \(p_r\) 表示重规划资格，\(a_r,c_r,t_r,u_r\) 分别表示分配、联盟、接管和控制执行
权限。规划专用状态为

\[
\mathbf{g}_r=(1,0,0,0,0).
\]

该向量允许区域聚合建议进入 D3 下一周期，不允许资源执行当前 binding，也不允许 D7
控制。消费结果还保留独立的汇总执行权限，固定为 false。

规划资格只在中心仍是当前 owner/layer、plan/version/epoch/lease 当前、租约有效、网络
未分区、确认完整且无实际故障代际围栏时成立。正式动作必须是中心重规划请求，拒绝原因
只能是资源不可行或必要成员数量不足。D5 友方冲突、重复末端锁定、身份冲突，以及中心
失效后的二级或分布式接管都属于不同安全状态，不能转换成规划资格。

D3 对区域 transfer 的约束会拒绝触及 `hold=true` 的端点。因此 planning-only 接收区使用

\[
hold_r=0,\qquad request\_replan_r=1.
\]

当前执行失败关闭由能力向量和正式裁决表达。接收区只能获得正的资源配额，不能成为转出
源。对任一源区 \(s\)，转出后的资源须满足

\[
R_s^{after}\geq R_s^{committed}+
\max\left(1,\left\lceil0.10R_s^{before}\right\rceil,R_s^{reserve}\right).
\]

规划证明绑定快照、正式裁决摘要、authority digest、source version、plan/version、
epoch 和 lease。带证明的快照与建议使用 v2；v1 保留原字段和内容标识，不能从缺失字段
推导新资格。2026-07-29 专项 14/14、D4 全量 794/794 通过。真实 D3 successor 仍待 main
集成验证，v4 仍未登记。

## 2026-07-29 v4 候选的安全边界

v4 的目标是研究学习策略能否在确定性规则之外形成可执行区域动作。学习模型只提出建议，
安全性仍由固定投影器、权威版本、租约、联盟确认和规则回退保证。v4 不改变 main/v3 的
最小备用比例 0.10、最小备用资源 1 和建议有效期 1.5 秒，也不改变规则策略的威胁权重
2.0、不确定度权重 0.5 和转移压力门限 0.05。

同键规则基线记为 \(R_0(s,f)\)，其中 \(s\) 是当前区域快照，\(f\) 是同一次正式降级裁决。
候选动作 \(a_L\) 与规则动作都使用同一个确定性投影器：

\[
a_L^P=P(s,a_L,f),\qquad a_0^P=P(s,R_0(s,f),f).
\]

比较键包含 snapshot、场景版本、seed、owner、plan、version、epoch、lease 和
formal decision。v4 invariant 会重新计算 \(R_0\)，不接受调用方提供的替代规则载荷。
候选只有在投影无裁剪、资源总量守恒、区域配额与跨区净流一致、布尔动作与 R0 合同一致，
且可执行签名同时区别于 source 和 R0 时才可进入离线 treatment。该状态仍不授予生产
分配或降级权限。

受控 fixture 用 8 个区域、21 个资源和 19 条既有绑定验证上述边界。源区有 3 个资源，
其中 1 个已承诺、1 个作为安全备用、1 个可转移。转移 1 个后源区剩余 2 个资源，继续保护
1 条承诺和 1 个备用。真正同键 R0 在该输入上不转移。fixture 可以验证
`S=-1、T=+1、S→T=1` 的安全表达，但它不是训练数据，也不证明当前存在可登记模型。

## 2026-07-29 外部数据与置信度原则

v4 builder 不生成 episode。训练输入必须由 main runtime 或独立 D4 数据生产链导出，
并形成 `RegionLearningDataset`、数据集 SHA-256、split SHA-256 和外部来源制品
SHA-256。在线输入不得含 actor truth、目标真实标识或未来结果。每个 episode 必须绑定
clean Git commit 和非零配置 SHA。

训练只读取 train，模型选择和置信度审计只读取 validation。test 与正式 holdout 的
manifest 参与内容绑定，但 payload 不进入构建目录，也不在 builder/reviewer 中读取。
train 和 validation 都必须包含两类样本：

1. 经过固定投影后形成合法跨区可执行差异的正例；
2. 与同键 R0 可执行签名相同的 no-op 负例。

动作模型冻结后再拟合置信度头。正标签要求模型输出与外部正例的可执行签名一致，同时通过
安全 invariant。no-op、模型与目标签名不一致、投影裁剪、动作不一致和缺少可执行差异都
标为负例。任一 split 只有正例或只有负例时，builder 终止。分布外输入、过期建议和低于
0.60 的置信度在运行评价阶段直接规则回退。

当前只完成上述框架和测试。先前使用放宽备用参数、压制 R0 和内生 dirty 数据的 v4 原型
已删除，不能作为模型证据。v4 注册摘要保持未登记，默认 runtime loader 拒绝加载。真实
runtime 数据、clean build、不可变登记、D3 successor 和双臂收益仍是 P1。

## 2026-07-29 运行兼容与模型收益

readiness v3 的最终 v2b 审计把“候选能够进入隔离运行链”和“候选能够改善结果”分成两个
判定。运行兼容要求候选在冻结身份、8-region 适用域和 1.5 秒有效期下完成原始推理、运行
一致性门、确定性安全投影及下一周期隔离采用，同时保持在线真值使用为 0、生产权限为
false。模型收益还要求投影后存在可辨识的 D3 可执行动作，动作形成严格后继计划和完整
ACK/D7/物理窗口链，并在同键规则基线上得到可用的正收益。

三维质点 development 场景使用 20 个目标、20 个资源、2 个侦察节点、8 个区域和
3.2 秒窗口。seeds 2003-2012 的原始推理、运行门、安全投影和隔离采用均为 10/10，
因此运行兼容条件成立。D3 后继、development ACK 和 producer 物理摘要只在 seed 2007
出现，覆盖 1/10；其余 9/10 为 `regional_hint_no_executable_successor`。10/10 的候选
可执行动作辨识数均为 0。

seed 2007 证明了接口谱系可以贯通。D4 advisory、D3 source/successor、development ACK
和 D7 指令能够重放，control/treatment 的 4 条 ACK 和 77 条 binding 与持久化语义一致。
19 条 D7 控制绑定中有 18 条可关联到物理窗口，1 条因身份映射不可用而缺失。source 与
successor 及 candidate 与规则臂的 D3 可执行 successor 字段、资源—目标及联盟绑定均
相同，所以该链只证明隔离消费和版本接线可工作，不能证明学习动作改变了执行。
`GT3D-000004` 的身份映射缺口由 D2/main 另行审计，D4 不读取或补造 truth。

配对非退化目前只对拦截数和最小距离可用。两臂在 10 个 seed 中均没有拦截，逐 seed
最小距离完全相同，因此非退化为 true。3.2 秒窗口没有观察到严格改善，且可辨识动作和
完整同链覆盖不足，正收益保持 unavailable/false。这两个结论不能互相替代：
“没有变差”不等于“候选有效”。

当前晋级门要求可辨识动作、完整同链物理证据和正收益同时成立。本轮三项未全部满足。
候选继续处于 development shadow；普通 assist、生产分配、降级、接管、联盟提交、控制和
模型晋级权限均为 false。运行时继续选择确定性规则。该审计是三维质点集成证据，不是
AirSim 或实飞性能结论。

## 2026-07-29 隔离配对的证据层次

readiness v3 现在可以进入 development control/treatment 配对，但该入口与普通在线
advisor 分离。control 使用确定性规则；treatment 可读取固定 v3 模型。两臂绑定同一场景、
初态、通信日程、故障日程和区域快照谱系。development seeds 固定为 2003-2012，旧正式
保留 seeds 1000-1019 的 schema 和证据对象未放宽。

treatment 的证据分成四层。第一层是原始模型推理，只说明模型产生有限、身份匹配的原始
建议。第二层是候选内嵌运行一致性门；候选经相同确定性投影后，必须与 truth-free 规则
建议在区域集合、资源配额、预备比例、侦察优先级、保持/重规划状态和转移多重集上保持
一致。动作不一致时有效置信度最多为 0.59，低于固定门限 0.60。第三层是确定性安全投影，
继续执行资源守恒、预备资源、版本、epoch、lease、成员确认和故障围栏检查。第四层是
建议在 1.5 秒有效期内通过下一周期消费校验。

只有四层全部通过，结果才标记 `next_cycle_isolated_adoption=true`。该状态表示候选建议
可以影响隔离 treatment 的下一轮 D3 输入，不表示生产采用。preflight 的
`candidate_permitted_after_gate` 只属于运行前检查，不能直接转换为 adoption。D4 不生成
生产 runtime ACK，也不授予 assist、分配、降级、接管、联盟提交或控制权限。

## 2026-07-29 运行适用域与证据边界

readiness v3 的适用域是 8-region 区域图。首轮 clean development preflight 中，
20v20 seed 2001 和 200v200 seed 2002 各产生 3 帧，两组均为 3/3 分布内、3/3 原始
推理、3/3 运行门应用、3/3 动作一致和 3/3 门后许可，规则回退为 0。

名义多 seed 预检继续使用固定 v3 registry。20v20/recon2 与 200v200/recon8 分别运行
seeds 2003-2012，每档 10 cases、30 frames。每个 case 为 2.2 秒；批次门限为累计至少
20 帧、分布内比例至少 0.80、至少 1 帧模型评价。两档的分布内、原始推理、门应用、动作
一致和门后许可均为 30/30，回退、真值、安全异常和 blocker 均为 0。seeds 与训练 0-99
及正式保留 1000-1019 无交集。该结果闭合名义 10-seed 运行兼容性。

5v5 seed 2000 使用 2-region 图，区域数与候选声明不符，边距离和转移时间对数也超出训练
域。系统在模型推理前对 3/3 帧规则回退。该行为证明适用域门正常工作，不能解释为 v3
8-region 正例失败。2-region 若需学习策略，应通过独立 adapter 归一到 8-region 合同，
或训练独立候选，不能临时放宽 OOD 余量。

兼容性不等于策略收益。`paired_development_rollout_allowed=true` 只说明可以在冻结候选下
开始候选与同键规则基线的独立 episode 比较。当前没有通信或节点故障扰动多 seed、同键
规则基线非退化、可辨识区域干预、D3 后继计划、ACK、物理窗口、时延、收益、实际接管或
正式 holdout 证据，全部权限保持 false。

## 2026-07-29 运行投影合同版本

运行时一致性门比较的是同一运行上下文中的学习建议和规则建议。投影配置属于模型运行合同，
建议有效期会改变输出的 `valid_until_s`，因此必须与最小备用比例、最小备用资源和规则权重
一起进入 bundle 内容哈希。TTL 不能作为未绑定默认值由运行端自行替换。

readiness v2 固定 TTL 1.0 秒；main 的实际 Advisor 使用 1.5 秒。main 在 clean commit
`8421de1...52e0` 的 5v5/2-region preflight 中得到 3/3
`runtime_confidence_gate_context_mismatch`，模型按设计失败关闭。v2 作为不可变失败证据
保留。

readiness v3 使用独立 identity，固定投影参数 0.1/1/1.5、规则权重 2.0/0.5/0.05 和安全
门 0.05/0.60/0.59/0.10。来源摘要、训练视图、validation helper 和运行 Advisor 均由同一
v3 合同生成。main 已从 clean commit `4ba2c8a...4114` 构建，D4 review 后将 8 个文件
逐字节登记；manifest 内容和登记树为 `7978aec0...ada2`、`07c770b0...a93a`。
validation 门后 293/344 通过，动作不一致通过 0。后续单 seed 8-region preflight 已通过，
名义 10-seed 也达到运行兼容门；但不能从名义 60 个 frame 推导扰动稳定性、策略收益或
正式运行准入，全部权限仍为 false。

## 2026-07-28 运行时确定性一致性门

readiness v2 采用运行时确定性一致性门。对当前区域快照 \(s\)、学习建议 \(a_L\) 和正式
裁决 \(f\)，Advisor 使用自己的确定性投影器计算
\(a_L^P=P(s,a_L,f)\)，再使用自己的规则策略计算
\(a_R^P=P(s,a_R,f)\)。两次计算共用同一个 projector 实例、同一个 rule policy/config 和
同一次 `formal_decision`。门通过后，最终建议直接使用 \(a_L^P\)，不再执行第二套投影。

一致性要求区域集合相同，配额归一化误差、备用比例误差和侦察优先级误差均不超过 0.10，
hold 与 request-replan 逐区域相同，转移边、源区域、目标区域和资源数的多重集合完全相同。
设模型原始置信度为 \(c_{\mathrm{raw}}\)，则有效置信度为

\[
c_{\mathrm{eff}}=
\begin{cases}
c_{\mathrm{raw}}, & a_L^P \text{ 与 } a_R^P \text{ 一致}\\
\min(c_{\mathrm{raw}},0.59), & \text{其他情况}
\end{cases}
\]

固定运行门限为 0.60，分布外余量为 0.05。动作不一致候选因此不能越过置信度门。bundle
manifest 对上述常数、规则策略名称和版本、投影器名称和版本、最小备用比例、最小备用资源、
建议有效期、高威胁权重、不确定性权重和转移压力边界统一计算内容哈希。Advisor 的任一配置
与 bundle 不一致时停止模型推理并使用规则策略。

validation 不使用 `target.action_consistent` 修改 confidence。标签只用于统计门后误接收和
核对记录规则标签。当前三来源数据集没有 formal decision 字段，因此 validation 明确以
`formal_decision=None` 调用运行时 helper；这与数据生成语义一致。以后若训练数据携带正式
裁决，必须将其作为内容寻址输入并逐帧传入，不能继续使用 None。

`RegionResourceAdvisoryResult` 的门诊断记录原始推理是否完成、门是否应用、动作一致性、
原始/有效置信度、门后候选是否获准、是否因门拒绝进入规则回退、门配置哈希和正式裁决摘要。
字段不含 truth ID，也不改变正式 D4 裁决。`candidate_permitted_after_gate` 只是一项
preflight 事实，不表示 assist、分配、接管、联盟、控制或物理许可。

readiness v2 已从 detached clean worktree commit `891b542...fea9e` 构建并逐字节登记。
manifest 内容、模型权重和运行门配置 SHA-256 分别为 `48148034...3852f`、
`ace5df6d...7f52d` 和 `acdcb781...cde`。validation 共 344 个样本：原始置信度
344/344 越过 0.60，其中动作不一致 51 个；运行门后 293/344 越过门限，动作不一致通过
数为 0，通过动作一致率 1.0，Brier 为 0.056837453793788656。规则参考与记录标签
mismatch 为 0。

登记专项 3/3、v1/v2/运行门联合专项 37/37、D4 全量 743/743 passed。main runtime
preflight 后续已执行但因 TTL 上下文不匹配未通过。validation 门接受只证明离线运行门
合同成立，全部 assist、分配、接管、联盟、控制、物理、runtime ACK 和正式评价权限保持
false。

## 2026-07-28 八区域训练视图与置信度原则

复合训练视图不直接拼接不同区域数的标签。运行数据保留真实八区域图和特征范围；四区域课程
只提供 hold、request-replan 和 transfer 的动作配方。D4 在选定的八区域运行快照上重放
配方，再调用规则策略与确定性安全投影生成八区域标签。该过程不读取目标真值标识、评价
结果或未来物理结果。两个来源的同一数字 seed 进入同一 split，避免跨来源泄漏。

动作模型训练完成后保持冻结。设五项归一化动作误差为 \(e_q,e_r,e_s,e_b,e_t\)，分别对应
资源配额、备用比例、侦察优先级、hold/replan 二值不一致率和转移比例，则

\[
\bar e=\frac{e_q+e_r+e_s+e_b+e_t}{5}.
\]

连续动作最大绝对误差不超过 0.10、两个二值动作完全一致、解码后的转移数量完全一致时，
置信度目标为 \(\operatorname{clip}(1-\bar e,0,1)\)。条件不成立时，目标上限为 0.59。
置信度头使用 train 上的连续 Brier 等价均方误差拟合，validation 只计算 Brier、十箱期望
校准误差、0.60 通过率及通过样本的动作一致率。

本轮 validation 的平均误差指标改善，但 51 个动作不一致样本仍越过 0.60。低 Brier 不能
替代固定门限下的一致性检查。候选因此标记校准未接受，并将既有 failure gate 置为 false。
模型原始输出仍可保留用于 shadow 审计，任何区域计划、联盟确认、接管或控制都继续使用
确定性规则路径。

候选只声明 8 区域适用域。区域数不等于 8 时增加图级 OOD 记录；区域数正确但校准未接受时
增加独立校准拒绝原因。两类拒绝都不修改模型输出，也不放宽 5% 特征 OOD 余量或 0.60
置信门限。

本候选由 clean detached checkout
`923f3f6e91af0f85aed446c66420c834d2de63fb` 生成。最终 manifest 文件/内容、模型、源码
身份、bundle manifest、复合数据和 split SHA-256 为 `ad5846b1...f5e5`、
`52866167...e2f`、`43157f4e...b0ee`、`f9c52715...53ed`、
`824aecf1...b8f`、`ee6bd202...cfd4` 和 `69ae1b0e...d817`。这些身份只证明候选可复现
和可审计，不授予运行或正式评价权限。2026-07-28 最终 registry 专项 14/14、D4 全量
720/720 通过。

main development preflight 对该候选给出了两层边界。5v5/2 区域 3 帧全部分布外，
raw model execution 为 0，符合 8 区域适用域限制。200v200/8 区域 3 帧中有 1 帧进入
raw 模型，另外 2 帧只因 `secondary_readiness` 越界而回退；训练范围 [1.0, 1.0] 未覆盖
运行范围 [0.0, 1.0]，24 个节点值中 16 个低于训练下界。两组均为有限值，在线真值使用
数为 0。

raw model execution 表示输入通过模型的分布门，不表示候选获得运行许可。八区域场景的
candidate-permitted execution 仍为 0，因为置信度校准清单明确未接受。双源重切分将 raw
execution 从 0 提高到 1，但运行分布仍未闭合。后续需补采真实八区域
`secondary_readiness=0` 运行帧，并消除验证集中 51 个动作不一致样本越过 0.60 的误接收；
在两项证据闭合前继续使用确定性规则路径。

## 2026-07-28 影子运行与分布适用域

冻结候选的可信加载与运行适用性是两个独立判据。源码、数据、权重和 manifest 全部匹配，
只能证明执行了指定模型；运行图特征超出训练范围时，模型仍必须失败关闭。当前适配器使用
模型清单中的逐特征上下界和固定 5% 余量，不按场景临时放宽。

冻结候选的原始字节必须与生成型输出分开保存。受控 `model_registry` 保存 manifest、
源码/数据/训练摘要、训练配置、模型 manifest、训练数据 manifest 和权重。加载器仍按冻结
SHA-256 逐项复核，不信任目录名称。登记使 clean clone 能复核来源，但不能把
development/shadow 改为默认运行策略，也不能改变任何权限字段。

main 的 5v5/2 区域和 200v200/8 区域共 5 个快照全部 OOD。稳定偏移包括资源承诺、D1/D2
不确定度、D5 可见/一致、二级覆盖/就绪、租约、通信和转移几何。影子链可保存原始模型动作
及其确定性投影，但实际执行仍为规则策略；这些记录不能生成后继计划、确认、物理结果或
收益。

下一训练视图采用互补数据源。运行快照提供实际特征范围，动作课程提供
`hold/request_replan/quota/transfer` 安全标签。两个来源均使用数字 seed 0-99，必须按
数字 seed 全局原子分割，同一 seed 的全部场景不得跨 split。seed 1000-1019 完全排除。
现有 union 覆盖默认 8 区域预检主要范围；2 区域边距离仍未覆盖，因此适用域不能泛化声明。

## 2026-07-28 当前谱系候选原则

区域学习候选首先是离线模型制品，不是区域权威。当前谱系候选必须同时回答四个问题：运行的
是哪一版实现，读取了哪一版数据，使用了哪些切分，最终加载了哪一份权重。任一项不能通过
内容摘要复核时，候选身份不成立。

候选构建采用训练/验证两段式边界。训练集用于梯度更新，验证集用于早停和选择最佳 epoch。
测试集属于后续评价，构建器不读取其 episode payload。历史 calibration 数据和 seed
1000-1019 同样不进入参数、阈值或候选选择。该约束避免候选在正式评价前吸收评价结果。

源码身份由 Git 提交、树对象和固定实现文件摘要构成。整个工作区必须 clean，原因是模块输出
依赖 Python import 后的实际文件；只记录 `HEAD` 而忽略未提交文件会把一个不可复现模型错误
归到旧提交。clean 检查覆盖已修改、已暂存和未跟踪文件，不提供绕过开关。

模型包仍受确定性安全外壳约束。当前候选只允许 development/shadow，A2 准入、辅助建议、
权威、分配、接管、联盟提交、控制、实际采用和收益字段必须逐项为 false。复核成功只表示
源码、数据、配置、权重和有限值软件合同一致，不表示模型优于规则策略。

实际 clean rebuild 已绑定 commit `b0d498d9...`、数据集 `7e17aba7...2d7f0`、split
`b413fa81...0c16` 和权重 `fd1b9c4c...0047`。review-only 在同一 clean checkout
重新验证源码身份、数据、bundle 和 60 个 validation 输出。该模型在 train/validation
开发样本上分别得到 168/180 和 54/60 个安全非零动作，说明当前谱系模型没有在已见动作覆盖
课程上退化为全 no-op。训练集用于参数更新，验证集用于 epoch 选择，两者都不能作为正式
未见样本。该观察不改变全部权限为 false 的结论。

## 2026-07-27 实际区域策略的分层诊断

实际模型动作必须与规则适配器动作分开计数。诊断输入是
`LearnedRegionResourcePolicy` 的原始输出，候选清单、模型 manifest、权重和数据集
SHA-256 必须一致。每个样本依次经过模型身份、置信度、分布外、权威绑定、资源可行性、
确定性投影和 advisory 消费检查。分类运行固定使用 0 ms 功能性时延覆盖，不把主机调度
抖动混入动作分类；独立时延基准仍须执行。任一门失败都不能形成实际模型非零证据。

设区域 \(i\) 当前可用资源为 \(n_i\)，已承诺资源为 \(c_i\)，投影器保护的基线备用资源为
\(b_i\)，模型输出备用比例为 \(\rho_i\)。原始离散备用请求为

\[
\hat b_i=\left\lceil \rho_i(n_i+\Delta n_i)\right\rceil .
\]

投影后备用资源还要满足 \(0\le b_i'\le n_i+\Delta n_i-c_i\)。当资源全部承诺时，
\(n_i-c_i=0\)。备用比例头采用 Sigmoid 后严格大于零，\(\hat b_i\) 会因向上取整变为至少
1，但安全投影只能给出 \(b_i'=0\)。这类输出记为 `resource_infeasible`，不能把连续比例变化
写成可执行干预。

可辨识干预集合仍限定为资源配额、整数备用资源、跨区转移、保持和请求重规划：

\[
\mathcal I =
\{\Delta n_i\ne0\}\cup\{b_i'\ne b_i\}\cup
\{\mathrm{hold}_i\}\cup\{\mathrm{replan}_i\}\cup
\{\mathrm{transfer}_{ij}>0\}.
\]

只有 \(\mathcal I\ne\varnothing\)、候选固定门通过、advisory 可消费且模型身份一致时，样本才
记为 `safe_nonzero_actual_model`。该状态仍位于运行时采用之前，不表示 D3 已发布严格后继
计划，也不表示 owner/coalition 已确认或物理窗口已经形成。

实际 development 候选在互斥 calibration split 的 20 个 seed、420 个样本上得到
76 个安全非零动作和 344 个资源不可行无操作。全部 420 个样本通过 0.60 置信、0.05 分布外
和安全门；保留 seed、真值字段、权限使用均为 0。每个校准 seed 固定包含 21 个样本，两次
重跑的样本身份与分类摘要一致。88 种原始可执行动作签名说明整批输出没有退化为同一动作。
该历史候选的实现谱系已经落后于当前代码，因此它仍只能保留为历史非零观察。当前谱系实物
及其 train/validation 非零开发诊断已经另行形成，但两类开发证据均不能进入正式准入。

## 2026-07-27 安全采用类型边界

权威证据中的布尔值不做字符串真值转换。成员 `can_execute`、采用可用性和所有权限字段只
接受原生布尔值；`"false"` 不再被解释为可执行。成员确认、提交和执行时间必须为有限非负
数。通信回执映射必须与版本化字段全集一致，附加真值字段会在进入因果门前被拒绝。

中心、二级和完全分布式 owner 使用相同的建议、后继计划、运行确认、owner ACK、必要联盟
ACK 和物理窗口链。链路可用只表示观察事实闭合，不产生 authority 或收益。开发探针也可以
验证软件链，但其固定策略身份不能进入正式 A2/R0 收益审计。

## 2026-07-27 开发态干预选择

开发态非零候选用于测试“建议到后继计划”的软件链。它不用于替代学习策略。原学习候选已经
给出投影后可由 D3 消费的非零动作时不做修改；原候选投影后为零动作时，D4 从确定性规则
结果中选择一个最小且可审计的动作。

判定发生在确定性投影之后。适配器先投影原候选，构造 advisory 并完成同 snapshot 消费
检查，再按资源配额、整数备用资源、跨区转移、保持和请求重规划五类字段计算干预。这样可
排除一类假变化：原始备用比例不同，但 committed resource 限制使投影后的备用资源数量与
受保护基线完全相同。侦察优先级仍不是 D3 可执行字段，不进入该判定。

snapshot 和 formal decision 对已承诺资源的观察范围可能不同。正式裁决还可携带已原子提交
的联盟成员。适配器现在在选择干预前接收 current formal decision，使首次判断和正式发布
投影采用同一资源保护边界。标准 advisor 仍会再次投影，适配器不能修改裁决。

优先动作是 request-replan-only。请求重规划只表达当前区域资源配置需要由 D3 重新计算，
不会冻结已有 assignment。固定区域同时输出 hold 会使已承诺资源进入
`held_assignment_infeasible`，因此不作为首选。没有合法重规划请求时，适配器才尝试满足
资源守恒、邻接、容量和备用约束的跨区转移。hold 位于最后，只允许
`committed_resources=0` 的区域。每一级都重新投影；投影后仍为无操作时继续下一级，所有
级别均不可消费时保留原候选并交由正式链路失败关闭。

开发场景若所有资源均已承诺，规则策略可能没有可用动作。显式开发开关允许对一个权威有效
区域发出 request-replan-only。该动作只请求 D3 重新计算，不冻结任务、不移动资源。开关
默认关闭，标准 advisor 仍把适配器限制为 shadow。

设区域 \(i\) 的可用资源为 \(n_i\)，已承诺资源为 \(c_i\)，最低备用为 \(r_i\)。跨区转移
仍需满足

\[
\sum_i \Delta n_i=0,\qquad n_i+\Delta n_i\ge c_i+r_i.
\]

适配器只选择候选，不执行动作。owner、计划版本、时期号和租约来自原候选，随后由原投影器
和正式 D4 裁决复核。D3 对 held assignment 的拒绝、网络分区门和严格后继计划门保持不变。

该适配器没有准入模型清单，最大模式为 shadow。开发策略名被正式收益审计明确拒绝。当前
五个 committed-region 问题 seed 的 D4 回归均输出 request-replan-only 并到达
`awaiting_d3_plan`。新增单样本回归确认，投影前备用比例差异在投影后消失时，适配器会继续
生成 request-replan-only；formal-only committed member 和显式开发 request 也已覆盖。
安全采用专项为 68/68，D4 全量为 674/674。

指定 seed 1 内存 full episode 的 1 条 A2 记录到达 `physical_window_available`，在线真值
使用为 0，authority 和 benefit 为 false。该结果使用 development-only admitted transport
夹具，只说明非空干预链可被测试。main 尚未重跑完整 20 seed，也没有形成模型效果或生产
控制权限证据。

## 2026-07-27 无操作建议的因果边界

区域建议被程序读取，不等于模型改变了区域资源状态。A2 证据需要区分三个事件：

\[
E_{\mathrm{link}}=\text{建议通过投影并被消费},
\]

\[
E_{\mathrm{int}}=\text{建议产生可辨识且可执行的区域干预},
\]

\[
E_{\mathrm{exec}}=\text{该干预被后继计划和物理窗口采用}.
\]

实际动作采用至少要求

\[
E_{\mathrm{adopt}}=
E_{\mathrm{link}}\land E_{\mathrm{int}}\land E_{\mathrm{exec}}.
\]

D4 对 \(E_{\mathrm{int}}\) 不采用单一总量字段，而是比较投影前后载荷。干预集合包括区域资源
配额、跨区域转移、按 \(\lceil r_i n_i\rceil\) 计算的整数备用资源、保持命令和请求重规划。
资源守恒的跨区转移满足 \(\sum_i\Delta n_i=0\)，因此 `total_quota_delta=0` 不能说明无
干预。反过来，所有区域 \(\Delta n_i=0\)、转移为空、备用资源不变且两个布尔动作均为假时，
属于无操作建议。

侦察优先级变化目前不属于可执行干预。现有 main 到 D3 的提示接口没有传递该字段，D3 后继
计划也无法据此形成可归因状态变化。它可以保留为研究输出，不能用于增加实际采用计数。

无操作建议允许完成 \(E_{\mathrm{link}}\)，便于检查模型加载、确定性投影和消息消费链路。
装配器随后以 `identifiable_regional_intervention_missing` 失败关闭，不读取或附着同期普通
D3 后继计划。收益审计要求非空干预字段和内容摘要，进一步阻断普通重规划被误归因到 A2。

main/D6 已于 2026-07-27 完成开发批次的正确 20-seed 重算：
\(E_{\mathrm{link}}=20/20\)、\(E_{\mathrm{int}}=0/20\)、
\(E_{\mathrm{adopt}}=0/20\)，A2/R0 收益审计为 0/20。20 个拒绝原因均为
`identifiable_regional_intervention_missing`，批次 SHA-256 为
`ff3c10a089b6a94582451ae05d8a884af3a2bd7485acd4df0496442ea7e0ec55`。原先 18 个安全
采用布尔值由普通 D3 后继计划误归因产生，已被本次结果取代。所有权限保持关闭。

## 2026-07-27 A2 同外生条件配对原理

候选策略已经产生物理动作，只能说明动作确实执行，不能说明动作优于规则策略。收益判断至少
需要两个相互独立的执行臂：候选 A2 臂和确定性规则 R0 臂。两臂共享外生条件，不共享执行
日志、物理窗口或计划结果。

设外生配置为 \(\xi\)，逻辑评估窗口为 \(w\)，候选臂和规则臂分别为 \(A2\) 与 \(R0\)。
可交给 D6 的必要配对条件为

\[
\xi_{A2}=\xi_{R0},\quad
w_{A2}=w_{R0},\quad
k_{A2}=k_{R0},\quad
L_{A2}\ne L_{R0},\quad
E_{A2}\ne E_{R0}.
\]

其中 \(k\) 是 comparison key，\(L\) 是事件日志内容身份，\(E\) 是独立执行臂身份。
外生配置以 `paired_exogenous_config_sha256` 固定，至少覆盖场景配置、规模、seed 和调用方
冻结的外部扰动。窗口身份还包含场景版本、逻辑窗口编号和持续时间。候选与 R0 的仿真时钟
区间相同，但物理窗口 ID、窗口载荷摘要、episode 事件日志 ID/hash 和 execution arm ID
必须不同。

候选窗口不能自行声明其来源。它必须引用
`RegionResourceSafeAdoptionEvidence.content_sha256`，并与其中的建议 ID/版本、策略身份、
后继计划 ID/版本、计划有效期、权威租约及物理窗口摘要逐项一致。R0 不允许引用候选的安全
采用记录或建议，只能声明冻结的确定性规则身份。两臂均要求物理执行已观测、窗口完整、硬约束
违规为零，且窗口在计划和租约到期前结束。

D4 只判断这组输入是否具备 D6 审计资格。结果指标不进入 D4 配对 DTO，真值、奖励和 outcome
字段也不进入安全采用前缀。D6 根据两份独立事件日志计算结果和非退化结论。D4 输出继续固定
`a2_benefit_available=false` 和 `authority_granted=false`，即使配对输入完整也不获得
assist、模型晋级、分配、接管或控制权限。

main 可以在两个独立进程或两个 reset-separated episode 中运行 A2 与 R0。候选 episode 的
完整安全采用记录从 `learning_adoption_evidence.json` 读取后重新计算内容哈希；R0 episode
通过独立事件日志摘要引用。该方式不依赖内存对象，也不允许把同一 episode 日志复制成两臂。

2026-07-27 的纯 Python 合同回归为专项 **50/50 passed**、D4 全量 **655/655 passed**。
验证覆盖正常配对、持久化读取、篡改、缺失、跨键、重复 R0、事件日志/窗口复用、过期、
不完整、时长错误、硬约束和真值字段。尚未运行实际双 episode 或多 seed，当前只证明合同
能够失败关闭。

## 2026-07-27 不可变确认收据的时间语义

确认收据表示一条消息已经从指定源节点送达指定目的节点。该历史事实由收据内容、消息类型、
消息标识、权威所有者、计划版本、时期号、租约范围、分区代次和载荷摘要确定。安全采用的
评估时刻表示系统何时引用这条历史事实，两者不应使用同一个摘要。

设不可变绑定为 \(b\)，收据为 \(r\)，第 \(i\) 次评估时刻为 \(t_i\)。同一收据的后续引用
仅在以下条件下成立：

\[
b_i=b_{i-1},\qquad
t_i \ge t_{i-1},\qquad
t_i \ge t_{\mathrm{arrival}},\qquad
t_i < t_{\mathrm{lease}}.
\]

实现保存每个 receipt ID 的唯一绑定摘要和该绑定的最新评估时刻。更晚评估不会直接复用旧
通过结论，而是重新检查到达时间与租约。绑定变化按跨证据复用拒绝，时间回退单独拒绝，收据
内容变化按冲突重放拒绝。该处理允许早期 owner ACK 支撑稍后形成的物理窗口，同时不允许 ACK
被改绑到其他计划、节点、消息或权威代次。

2026-07-27 的纯 Python 回归覆盖一次早期确认和一次后续物理窗口装配，通信与安全采用专项
**99/99 passed**，D4 全量 **637/637 passed**。验证没有授予 authority，也没有形成 A2
收益或 AirSim 物理效果证据。

## 2026-07-27 A2 确认链原理

A2 采纳证据由相互独立的业务绑定和通信事实组成。业务绑定回答“哪个建议产生了哪个后继
计划、由谁在什么时期和租约内执行”；通信事实回答“确认消息是否经过指定链路并在决策前
到达”。只验证其中一层不能形成安全采纳。

所有者确认按以下不可变关系建立：

```text
advisory identity
  + D3 successor plan ID/version/payload SHA/bus sequence
  + runtime assignment ACK payload SHA/bus sequence
  + authority owner/layer/epoch/lease
  + partition generation
  + sent timestamp/arrival timestamp
  -> delivered owner-ACK evidence
```

运行时确认散列来自 main 实际发布的 `runtime.assignment_plan_ack` payload，不由所有者自行
声明。回执 ID 和 payload 摘要由
`CommunicationDeliveryReceipt.from_delivered_message()` 根据实际 envelope 和交付事实
计算。main 使用 D4 公共 builder、parser 和 validator，不复制散列算法。

联盟确认继续使用现有 `CoalitionMemberAck`。嵌套对象绑定
resource、`global_track_id`、coalition ID/version、plan ID/version、epoch、执行能力、证据
时间和有效期。外层交付合同再绑定协调者、计划 payload SHA/总线序号、租约和分区代次。
required member 全部确认并原子提交前，任何单个成员确认都不能授予执行权限。

证据状态遵循失败关闭原则。缺确认表示 unavailable，不等于指标值 0；确认错绑、晚到、过期
或分区代次不一致表示 rejected；两者都不能产生 authority。规则回退只证明安全后备路径被
使用，不属于 learned adoption。2026-07-27 的纯 Python 合同回归为四文件
**130/130 passed**、D4 全量 **626/626 passed**。本轮无 AirSim、真实网络、物理窗口或同键
R0 证据，正式 A2 收益仍不可用。

## 2026-07-26 A2 安全采用证据原理

区域学习策略的输出先被视为候选建议，不直接改变计划或权威。D4 把一次安全采用拆成“建议
准备”和“运行证据装配”两个阶段。这样可以单独回答两个问题：候选是否通过确定性约束；通过
后的动作是否真正进入新计划并在有效权威下执行。

设候选建议为 \(a_\theta\)，确定性安全可行域为 \(\mathcal{F}(s_k,d_k)\)。其中 \(s_k\)
包含区域资源、备用和已提交资源、区域邻接与容量、通信和分区状态；\(d_k\) 是正式 D4 裁决
中的所有者、计划版本、时期号和租约。第一阶段计算

\[
a_k^{safe} = \Pi_{\mathcal{F}(s_k,d_k)}(a_\theta).
\]

当前正式采用口径只接受学习来源、无规则回退标记、模型摘要有效且置信度
\(p_\theta \ge 0.60\) 的候选。投影发生非法邻接、容量裁剪、备用或已提交资源越界、权威不
一致、网络分区或正式裁决不可执行时，本次建议不可用于实际采用。通过后的
`RegionResourceAppliedRecommendation` 只表示可交给后继计划生成器，仍不授予执行权限。

第二阶段把安全建议与运行事实做内容寻址绑定。可用性判据为

\[
G_{adopt} =
G_{plan}\land G_{runtime}\land G_{owner}\land G_{coalition}
\land G_{physical}.
\]

其中 \(G_{plan}\) 要求 D3 计划具有新标识和严格更高版本，并引用同一建议标识、建议版本和
载荷摘要；计划载荷摘要和总线序号也必须一致。\(G_{runtime}\) 要求生产运行时确认明确为
“新执行计划已采用”。\(G_{owner}\) 要求当前二级或对等所有者的确认消息实际到达 main，
并与所有者、区域、计划、时期、租约和分区代次一致。\(G_{coalition}\) 在多成员任务中要求
联盟进入执行态、必要成员集合与已确认集合完全相等，且每个确认均有实际投递回执。
\(G_{physical}\) 要求确认后的状态窗口可用、无硬约束违规，并在计划有效期和权威租约内结束。

中心正常时只能接受中心所有者。中心失效后，具有有效二级节点的区域必须先采用二级所有者；
只有二级不可用时才允许完全分布式对等所有者。中心未失效的主动降级还需正式 D4 裁决和显式
主动降级证据。证据不足时保持中心路径或失败关闭，学习建议不能改变这一层级。

在线输入递归拒绝目标真值、离线结果和奖励字段。D4 输出的
`safe_adoption_available=true` 只证明运行证据链完整，固定不声明 A2 收益，也不授予
assist、PPO、分配权、接管权或控制权。D6 在带外使用同一比较键的规则基线和物理结果计算
非退化；既有 A2 最终装配器继续要求 20 个实际采用及完整配对证据。

2026-07-26 的模块验证为专项 27/27、相邻证据链 100/100、D4 全量 621/621。测试覆盖二级和
对等节点正例及主要失败关闭门。这些结果来自纯 Python 单元合同。本轮没有 AirSim、真实网络
或正式多随机种子物理证据，现有真实学习候选采用仍为 0。

## 2026-07-26 A2 证据装配原理

A2 准入采用“双层不可变包”。内层仍是 development/shadow 模型及其训练身份，外层只保存
与该候选严格绑定的外部证据。外层通过候选指纹连接数据 manifest、数据内容和切分摘要、
模型 manifest、权重摘要及当前实现摘要。内层文件不因外部证据通过而改写，历史模型状态也
不能通过修改布尔字段获得新权限。

证据链按“建议、计划、确认、执行、比较”顺序闭合。区域 advisory 必须由同一模型产生，置信
度不低于 0.6，经过确定性安全投影后实际进入下一周期；D3 后继计划必须严格升版；runtime ACK
必须与 advisory、计划、owner、epoch、lease 和 fault generation 一致；联盟必须由
`CoalitionCommitState` 和全部 `CoalitionMemberAck` 证明已经进入执行态；物理状态窗口只能
从确认后开始，并在最早租约到期前结束；D6 再证明同一 comparison key 的唯一 R0 和候选臂
配对非退化。规则回退、同代评估刷新、nominal 规则臂和 `active_risk` 规则臂都不属于候选
实际采用。

严格加载不是对 manifest 的一次信任。加载器重算包内精确文件清单、文件 SHA-256、JSON
规范内容 SHA-256、当前实现文件摘要、候选指纹和所有跨证据键。额外文件、额外字段、旧
epoch、过期 lease、缺少成员 ACK、物理窗越过租约或权限字段误开都拒绝加载。装配采用临时
目录和原子发布，已有目标目录不覆盖。

装配成功的语义限于“该候选具备 A2 区域建议资格”。它不授予默认模型、在线 PPO、故障接管、
D3 分配或 D7 控制权限，规则策略始终可用。2026-07-26 合成完整 fixture 17/17、相关合同
124/124、D4 全量 594/594 通过，证明软件合同可执行。当前实际 D6 审计仍失败关闭，真实
候选没有获得该资格。

## 2026-07-26 校准 development 候选原理

新版候选沿用“学习建议、确定性裁决”的边界。共享区域图网络只输出未投影的区域配额变化、
备用比例、侦察优先级、hold、request-replan 和邻区转移。确定性投影继续检查资源守恒、
邻接和容量、最低备用、owner、plan version、epoch、lease、联盟 ACK、故障栅栏和网络分区。
学习模型不能形成联盟、生成 D3 系统计划或授权 D7。

训练数据由两个不可变来源的规范只读视图组成。正式 900 episode 提供常态区域分布，clean
supplemental 100 episode 提供四类稀有动作正样本。两者共享 60/20/20 seed 目录；训练桶用于
动作拟合，validation 桶用于置信头区分域内样本与合成分布外样本，test 桶只做独立校准。
0.6 和 50 ms 是固定系统门，不使用 test 桶调节。seed 1000-1019 作为后续外部试验保留，
本轮使用数为 0。

校准 420 个样本全部通过候选门，置信度均值为 0.972089，时延 P95 为 0.969215 ms；合成
分布外样本 420/420 被特征边界拒绝。后投影动作覆盖 quota、transfer、hold 和
request-replan。该结果修复旧候选置信头未训练和动作正类缺失的问题，只形成
development/shadow 研究候选。没有保留 seed 的采用、运行 ACK、物理结果和配对非退化，
因此不产生 assist、authority、production 或策略收益结论。

本轮 D4 全量模块测试为 **577/577 passed**。测试覆盖候选正门及主要失败关闭路径，不包含
AirSim 和保留 seed 正式评估。

## 2026-07-26 预准入证据分层

本节的“当前 development bundle”指旧冻结候选；新版校准候选状态见上一节。正式权限所需的
外部采用和结果证据对两者都不放宽。

模型准入需要同时回答四个问题：候选是否为声明的模型输出，候选是否实际改变了下一版计划，
该计划是否在有效权威和完整联盟确认下执行，执行结果是否相对同输入规则基线非退化。D4 当前
可以分别验证前三类事实中的大部分字段，也可以记录非因果结果窗口，但还不能把全部事实装配为
一个可发布新 bundle 的准入证明。

证据分层如下：

- **软件合同层**验证 bundle、advisory、计划、owner、epoch、lease、联盟状态、通信回执和结果
  窗口内部一致性。合同通过只说明对应事实可验证。
- **development bundle 层**固定当前模型、训练数据和特征边界。其最高模式为 shadow。
- **运行与评估 evidence 层**必须来自同一 clean 场景、seed、comparison key 和候选身份。
  nominal 候选未采用、规则回退后的物理窗或不可用字段不能跨批拼接。
- **正式权限层**只能由新的内容寻址准入 bundle 表达。当前没有该 bundle，assist、PPO 和
  authority 均关闭。

D6 外部审计负责检查运行制品完整性、实际采用、物理指标 availability 和规则基线配对。D4
现已增加模块专用装配：重验候选模型和 advisory、严格后继计划、owner/version/epoch/lease、
联盟 required/acked members、逐成员通信投递回执及 D6 pair 身份。D4 不重新定义 D6 通用
审计 schema，也不把一个 `passed=true` 或一个 SHA-256 字符串当作完整证据。装配输入缺任一
原始制品、字段或可重算摘要时，结论保持 unavailable。

2026-07-26 的验证只包含代码与调用方审计及 D4 现有 569 项模块回归，结果为 569/569
通过。没有新增仿真场景、随机种子或物理结果，因此该结果只确认安全边界没有退化。

## 2026-07-26 学习准入原则

D4 区域学习策略只能提供受确定性安全投影约束的规划建议。模型文件存在、哈希正确、推理可运行或规则回退后物理日志可计算，都不能单独获得 assist 资格。正式准入必须证明“哪个模型在什么降级场景被实际采用、哪个新计划收到运行确认、采用后产生了什么物理结果，以及相对同输入规则基线是否非退化”。

当前 `d4-region-resource-model-bundle-v2` 没有独立准入证据绑定，因此定义为 development/shadow-only。bundle writer 在写目录前拒绝 `qualified/assist`，advisor 只认可带正式 D4 manifest 的准入状态；普通注入策略和缺 manifest 策略不能借 20 个未见 seed 绕过。现有 bundle 未改写。

现有证据边界如下：

- nominal 保留 seed 干预中，D4 候选 20/20 被置信度门拒绝，安全采用 0/20，物理结果和运行 ACK 不可用；
- `active_risk` 隔离试验中，物理窗和描述性非退化为 20/20 可用，但 D4 候选 0/20 被考虑，188/188 区域采用的是确定性规则回退计划；隔离 ACK 不等于生产运行 ACK；
- main `d59352b` 已能哈希绑定学习 bundle 并拒绝规则回退，但 D4 预检仍停在 `pending_runtime_shadow_gate`，所以 A2、C1、F1 在创建正式 scope 前失败关闭。

正式 promotion 必须创建新 bundle，不修改 v2 旧 manifest。证据至少绑定 clean source、未见 seed、非 nominal 降级场景、候选实际采用、新执行计划 ACK、联盟成员 ACK、采用后物理状态窗、配对非退化、零在线真值和零安全违规，并由 D6 提供独立摘要。当前不具备这些条件。

## 2026-07-25 异步联盟确认原则

联盟确认窗口与一次区域状态快照不是同一个时间尺度。区域状态机每次只处理决策时刻前已经送达的 ACK，并把同一计划代次的确认位图保留到下一快照。没有 ACK 或 ACK 不完整时，状态保持“收集确认”，所有成员继续等待；必要成员全部确认后，联盟才整体获得执行资格。

状态转移为：

```text
proposed -> collecting_acks
collecting_acks + partial ACK -> collecting_acks
collecting_acks + all required ACK -> committed
collecting_acks + explicit finalization/lease expiry/partition/conflict -> aborted
committed/executing + lease expiry/partition/member failure -> reconfiguring
```

陈旧版本、过期、非必要成员或内容不匹配 ACK 会被拒绝并记录原因。它们不进入确认位图，当前快照仍不授权执行。若同一有效代次随后收到合法 ACK，可继续收集；这样既保持失败关闭，也避免网络乱序旧包形成永久拒绝服务。分区代次由通信因果证据门先行校验，区域状态机只消费通过该门的 ACK。

2026-07-25 验证包含提案无 ACK、部分 ACK、三成员分时完整 ACK、显式终结、租约到期、分区、陈旧代次和无效 ACK。三文件专项 **97 passed**，D4 全量 **569 passed**；完整 ACK 前执行授权必须为 0。该组数字限于纯 Python 模块测试。

main-owned scalable 3D 已完成随机种子 `1271` 的单场景集成验证。2 目标、4 资源和 1 个二级侦察节点条件下，高威胁目标采用 2 个主成员与 1 个备用成员。二级计划版本 2 发布后先保持 0/3 ACK，随后按实际通信投递达到 3/3 ACK 并原子提交；提交前主成员保持，提交后主成员进入三维中段比例导引，备用成员继续待命。在线真值使用和 `global_track_id` 改写均为 0。该结果不是 AirSim、多随机种子、真实网络或规模性能证据。

## 2026-07-25 通信因果证据原则

二级节点就绪、区域计划广播、区域计划所有者确认和联盟成员确认都属于通信事实。布尔量只能
描述节点当前自报状态，不能证明消息已经经过链路并在决策前到达。D4 因此把“业务内容正确”
和“通信实际发生”分成两层：既有 readiness/coalition 状态机继续检查业务条件；新增通信
证据门检查投递回执。

一条可接受回执需同时满足：

```text
topic 映射的消息类型 = payload 声明类型 = 当前验证入口类型
source/destination/authority/plan/epoch = 当前期望
sent_time <= arrival_time <= decision_time < lease_expiry
partition_generation = 当前网络分区代次
SHA256(payload) = expectation.payload_digest
```

回执记录版本化 topic、总线序号和 envelope schema。严格工厂从 delivered message 及其 envelope/payload 取值，调用方不能另传一套 authority、plan、epoch、lease 或消息类型覆盖运输事实。payload 缺少协议字段、包含 evaluator truth 字段，或 envelope source/timestamp 与 transport 不一致时，回执不能建立。

证据门保存 receipt ID 对应的不可变摘要。相同 receipt 和相同 expectation 重复验证只返回幂等结果，不重复产生状态作用；相同 receipt ID 的内容变化、同一回执转用于另一证据或不同决策上下文均被拒绝。验证结果只表示“这条通信证据可供后续状态机使用”，固定不授予 authority，也不推进 plan version、epoch、lease 或 coalition commit。

2026-07-25 验证覆盖 5/20/50/100/200 成员、三类消息、顺序反转、精确重复、冲突重放和全部主要负例。因果证据专项 56/56 通过；加入异步联盟回归后 D4 全量为 569/569。main 的 5v5 通信关闭复现现为 0 个可执行区域、8 个失败关闭区域；随机种子 `1271` 的三成员分时 ACK 单场景系统正例也已通过。AirSim 多随机种子和真实通信条件仍需复跑。

**状态日期**：2026-07-25
**适用范围**：离线科研仿真、合同验证、故障注入与评估日志。
**事实来源**：当前 D4 源码与测试、模块说明文件 `README.md`、模块计划文件 `PLAN.md`、D4 实现差距审计与综述，以及 2026-07-13 主级优先级 1 收敛验证报告 `MAIN_P1_CONVERGENCE_VALIDATION_REPORT_20260713.md`。
**状态声明**：本文只解释当前能力，不改变能力状态。凡标为“可选/离线”或“未实现”的内容，不属于默认在线主线。

**隔离多周期证据增量**：D4 现提供独立的 degraded-scenario lineage、候选门、隔离计划消费回执和采用证据。它处理 `center_failed`、`center_and_secondary_failed` 与 `active_risk`，并把区域、arm、cycle、场景配置、初始状态、通信/故障时序、D4 snapshot/decision、源计划和候选门绑定为内容哈希。nominal 场景不能进入这条证据链。采用判据分为两层：先确认候选是否被评估并通过固定的 0.6 置信门、50 ms 时延门、分布外、有限值、失败和安全投影门；再确认 D3 是否发布严格更新的新 plan ID/version，且 owner、epoch、lease、binding 和隔离世界消费回执一致。只有两层都成立且未使用规则回退，才记录隔离候选采用。同代评估刷新要求执行绑定、未分配集合、权威和创建时间不变，只能记录 refresh，不能记录候选采用。

**计划代际解释**：source plan 必须与同帧 formal D4 区域 ownership 完全一致。被动降级的故障前 `previous_plan` 仍属于中心或二级权威，只能作为 D3 的规划祖先，不能直接作为 secondary/distributed D4 source。applied plan 若改变执行，必须在同一 formal owner/epoch/lease 下使用新 ID 和严格更高版本；若没有改变执行，只能保持同一 ID/version、binding、未分配清单和创建时间并显式标记刷新。owner、epoch 或 lease 变化时需要新的 formal decision 和 lineage。

该回执固定标记为 `isolated_simulation_only=true` 和 `production_runtime_ack=false`。缺 ACK、旧 epoch、到期 lease、binding 篡改、网络分区、缺联盟确认和低置信候选继续失败关闭；低置信只允许确定性规则计划。D3 v1 隔离消费证据只有通过 D4 对来源、计划、binding、时间窗和非生产权限的独立复核后，才可转换为该回执。计划代际专项 26/26、D4 全量 508/508 passed。中心失效 20-seed 首轮续跑的 196 条区域记录仍因 source/applied 不是严格后继而全部不可用；main 修正 producer 并由 D6 重算前，不能宣称降级采用、因果收益或获得 PPO、assist、生产 authority。

**保留 seed 配对实验增量**：D4 已形成规则区域调度与候选学习建议的正式实验边界。seed 固定为 1000-1019，每个 seed 具有一个规则 control arm 和一个隔离 treatment arm；场景配置、初始状态、通信时序、故障时序和区域快照 lineage 必须逐 SHA 相同。隔离加载器只读取 `region_resource_bc_900_20260720` development bundle，固定 manifest、权重和训练清单 SHA，并在每次推理前后复核文件指纹。它直接生成未投影的学习候选，不调用生产 advisor。control 始终执行确定性规则；treatment 候选经过分布外、时限、置信、有限值检查后，复用原 owner/version/epoch/lease、fault fence、联盟 ACK、邻接、容量、备用和资源守恒投影。只有全部门及下一周期消费均通过，才记录隔离 arm 安全采用；该标志不等于线上运行确认，不能授予计划所有权或导引权限。

arm evidence v2 保存 confidence/最小置信门、OOD、latency/limit、finite 和逐项 gate，并分别使用 low-confidence/OOD/timeout/nonfinite 稳定拒绝码；旧 generic reason 只保留兼容。v1 reader 在验证旧 content ID 后迁移，未知新字段保持 unavailable，不反向改写冻结记录。当前权威 `formal_7891296` 绑定源提交 `78912963b67fe86ee9a8d29186b18a9dd60c460c`，其 `SHA256SUMS` 与 manifest SHA256 分别为 `821f1503...72bc`、`d6ef23b2...883c`。D6 独立重算得到 20/20 source clean 且 finite、truth 使用数 0，20/20 候选被评估。confidence min/mean/max 为 `0.508892953/0.563426384/0.569492280`，在保持不变的 `minimum_confidence=0.6` 下通过 0/20；OOD、latency、finite、failure gate 各通过 20/20，aggregate 通过 0/20，safe adoption 0/20，规则回退 20/20。执行时延 `treatment_candidate_latency_ms` 的 nearest-rank P95 为 `2.241315 ms`；门控汇总 `candidate_gate_summary.candidate_latency_ms` 的线性插值 P95 为 `2.264415 ms`。D6 profile-bound v2 sidecar 位于 `research_modules/d6_evaluation_metrics/outputs/reserved_seed_interventions_nominal_5v5_1000_1019_formal_7891296_d6_profile_bound_v2_audit_20260722/`，状态为 `pass_offline_assignment_comparison_only`，文件/内容 SHA256 为 `f3852251...1c3b`/`c02a345c...5d2d`。该 sidecar 只使同帧离线分配比较可用；runtime ACK、干预后物理结果、paired effect/non-degradation、counterfactual、causal 和故障场景降级策略效果仍不可用。manifest 的 `confidence_head_uncalibrated` 和 `formal_twenty_seed_performance_completed=false` 仍有效；不能降低 0.6 门、宣称候选或降级策略有效，也不能开放 PPO/assist/authority。专项 33/33、D4 全量 482/482。

**当前事实增量**：main-owned scalable 3D 质点模块栈已接入单一二级、多二级区域 owner 和中心/二级连续失效后的 distributed D3 plan；D7 依据 owner、plan version、epoch、lease、commit 与 fault generation fence 恢复导引。此前定向集成测试 8/8 passed，仅是质点接口证据。D4 同时具备默认 disabled/shadow 的区域资源学习建议层，以及 `d4-region-resource-advisory-v1` 后投影消费合同；它只建议区域配额和邻区转移，下一轮消费必须重验 current snapshot/authority，确定性 D4 安全状态机继续拥有健康检测、leader、epoch/lease、ACK/commit 和最终降级裁决。2026-07-21 新增独立动作覆盖补充课程，100 个 seed 的 300 帧中已形成 hold、request-replan、非零 quota 和 transfer 正类；该课程 reward/outcome 全部不可用，未改变正式 900 episode、PPO、assist 或在线裁决状态。

**运行时证据增量**：D4 的只读验证器已升级为 `d4-region-resource-runtime-ack-evidence-v2`。执行签名发生变化时，验证器要求严格更新的 plan ID/version、完整 owner/epoch/lease 和 D3-D7-main 绑定，输出 `new_execution_plan_applied`。执行签名不变时，验证器可校验显式 refresh-only 元数据，但该事实不构成 A2 动作采用。无操作区域建议只允许 `no_successor`，不能刷新 authority/lease，也不能生成 applied ACK。当前集成测试以无操作和显式 `hold/request_replan` 两条链验证该差异，并覆盖四个 successor 篡改负例，结果 **6/6 passed**；D4 全量 **658/658 passed**。两类运行记录都不等于联盟成员确认、物理结果或因果策略回报，也不授予 PPO、assist 或正式 authority。冻结 900 episode 不含这条证据链。

**区域结果证据增量**：`d4-region-resource-observational-reward-v1` 已把区域 reward 的组成、归一化和证据边界固定下来。八项成本分别为高威胁积压、配额满足缺口、转移完成缺口、备用不足、通信负载、分配冲突、降级失败和计划抖动。每项保留原值、单位、归一化分母、来源哈希和可用原因；缺测时整项不可用，不使用相邻状态差或控制命令补零。ACK 时间是窗口起点，结果快照是窗口终点，执行和联盟绑定在首尾必须一致，owner/epoch/lease/fault generation 在窗口内不得改变。新执行计划可得到时间窗口层面的非因果观测奖励，同代评估刷新只能得到观测成本。两者都不证明 `CoalitionMemberAck`、物理执行、因果改善或策略优于规则。新增专项 19/19、D4 全量 449/449；正式 episode producer、paired shadow、on-policy 数据和 PPO 仍未完成。

## 1. 模块定位与问题定义

### 1.1 模块定位

D4 是反无人机系统（Counter-Unmanned Aircraft System，C-UAS）多无人机流程中的分布式协同与降级接管模块。它位于上游态势、关联、分配和末端视觉证据与下游执行门控之间，负责回答“当前中心计划是否还能继续”“何时请求补充观测或中心重规划”“中心失效后由谁接管”“无中心时怎样保守维持任务连续性”。

本文中的指挥与控制（Command and Control，C2）表示中心协调权威及其健康状态；`C2Health` 是中心健康枚举。D1 至 D7 是仓库内的模块编号：D1 为传感器融合，D2 为数据关联，D3 为分配规划，D4 为本模块，D5 为末端关联，D6 为评估指标，D7 为比例导航与导引门控。

D4 的默认实现不是另一套常驻中心规划器。中心可用时，D3 仍拥有系统级分配计划；D4 只进行保守仲裁。只有中心被判定为 `failed`（失效）后，D4 才允许二级节点接管或进入完全分布式保底。

### 1.2 工程问题

当前实现针对以下工程问题：

1. **失效识别**：用心跳（heartbeat）、摘要校验值（digest）、世代号（epoch）和对等节点（peer）投票，区分短时抖动、可疑状态和中心失效。
2. **层级接管**：保持“中心 -> 二级协调节点 -> 完全分布式”的顺序，避免中心仍可用时直接争夺计划所有权（owner）。
3. **证据仲裁**：把 D1 协方差、D2 关联风险、D3 计划有效性和 D5 末端证据归一化为有限动作集合。
4. **接管可执行性**：把“二级节点看见目标”与“二级节点能持续接管”分开，要求覆盖、新鲜度、跨视角注册、租约（lease）、来源和计划版本同时满足。
5. **原子联盟安全**：多资源共同覆盖一个目标时，只有必要成员确认（Acknowledgement，ACK）齐全、版本一致且租约有效，才允许联盟进入可执行状态。
6. **无中心连续性**：使用一致性捆绑算法（Consensus-Based Bundle Algorithm，CBBA）风格的单获胜者协商作为一对一连续性保底，并显式报告收敛、冲突和通信开销。
7. **恢复防双主**：中心心跳恢复后先做双轨校验，不因单次恢复立即夺回所有权。
8. **建议消费防重放**：区域资源建议必须先形成内容寻址、限时、逐 generation 可审计的后投影合同；main 在下一轮规划边界重验后才能把它作为 D3 输入，同一 advisory 不得重复消费。
9. **结果窗口防误归因**：区域结果必须绑定实际采用 ACK、计划和 authority generation，并在非重叠租约窗口内记录完整分项来源；评估刷新、目标级真值诊断和命令记录不能直接升级为策略奖励。
10. **配对干预防混淆**：规则与候选实验必须使用保留 seed 上完全相同的输入、通信和故障时序；隔离 treatment 的安全采用、线上 ACK、D6 结果和因果结论分别记录，不得互相替代。

### 1.3 科学问题

D4 的研究问题不是“如何得到一次最优分配”，而是以下受不确定证据、通信退化和版本约束共同影响的序贯决策问题：

- 在观测误差、身份不确定和计划时效同时变化时，怎样降低误降级与漏降级；
- 在有限通信和节点失效下，怎样维持唯一可执行所有者并避免脑裂；
- 二级节点的覆盖质量、跨视角注册质量和证据持续时间怎样共同决定接管能力；
- 分布式保底相对中心化基线会付出多少代价、完成率和通信轮次损失；
- 多资源对多目标（Multiple Resources to Multiple Targets，M-to-N）问题中，怎样把单获胜者协商与多成员原子提交严格分开。

### 1.4 明确边界

D4 当前只处理粗粒度摘要、内存网络、状态机、仲裁结果、回放（replay）和审计元数据（metadata）。它不负责：

- 启动、重置或编排微软 AirSim 无人系统仿真器；这些属于主编排器（main）和运行时（runtime）；
- 图像像素投影、检测框几何、多视角视觉注册或局部视觉身份生成；这些属于 D5 和 main；
- 创建、改写或本地重绑定 `global_track_id`（中心拥有的全局航迹标识）；
- 生成完整系统级 `AssignmentPlan`（版本化分配计划）；D3/main 拥有其模式、所有者与版本事实；
- 真实无线频率（Radio Frequency，RF）链路、网络设备、套接字、视频传输、硬件驱动或飞行控制；
- 真实火控、毁伤、自动授权、自动处置或绕过人工审核。`hold_for_review`（保持并请求复核）始终是安全结果之一。

D4 按输入列表长度运行，不把 2 对 2、5 对 5 或任意 N 对 N 场景写死为算法规模。

## 2. 默认主线与分层架构

### 2.1 默认主线

当前默认主线为：

```text
D1 融合航迹与协方差
  -> D2 关联连续性和重复风险
  -> D3 中心版本化分配计划
  -> D4 保守仲裁
       中心可用：继续中心 / 请求二级观测辅助 / 请求中心重规划 / 保持复核
       中心失效：二级节点接管 / 完全分布式保底 / 保持复核
  -> D5 末端身份与视觉锁定继续独立门控
  -> D7 导引合同继续独立门控
  -> D6 只读评估与报告
```

主动降级 `active_degradation`（主动降级模式）处理“中心仍可用，但证据要求重新评估当前计划”；被动降级 `passive_failover`（被动接管模式）处理“中心已失效”。两者不能混写：

- 主动降级不会直接把所有权转给二级或分布式节点；
- `degrade_to_secondary`（降到二级节点）和 `degrade_to_distributed`（降到完全分布式）只属于中心失效后的接管路径；
- `request_secondary_assist`（请求二级观测辅助）不等于二级接管；
- `request_center_replan`（请求中心重规划）不等于 D4 自己生成新计划。

### 2.2 二级节点角色

二级节点可由地面备份、固定系留侦察节点、机动高空侦察节点或二级侦察节点表示。`coordinator_only`（仅协调标志）默认使其只提供区域协调与观测证据，不作为拦截执行资源参与 CBBA 出价。

中心可用时，二级节点最多提供区域图像线索、覆盖摘要和跨视角支持。中心失效后，只有二级节点通过瞬时能力门限和持续就绪性（readiness）窗口，才可成为接管候选。二级节点不可用、不可达、覆盖不足或证据不持续时，才进入完全分布式保底。

## 3. 输入、核心数据结构与输出

### 3.1 上游输入

| 来源 | 当前 D4 输入 | 关键字段及中文释义 |
|---|---|---|
| D1 | `TrackUncertaintySummary`（航迹不确定度摘要） | `track_id`（航迹标识）、`coverage_cell`（覆盖小区）、`position_sigma_m`（位置标准差，米）、`covariance_trace`（协方差迹）、`velocity_sigma_mps`（速度标准差，米每秒）、`measurement_age_s`（量测年龄，秒） |
| D2 | `AssociationRiskSummary`（关联风险摘要） | `ambiguity_score`（歧义评分）、`id_switch_count`（身份切换计数）、`duplicate_track_count`（显式重复航迹计数）、`duplicate_track_risk`（连续重复风险评分）、`track_continuity`（航迹连续率）、`truth_metrics_available`（真值指标是否可用）、`continuity_available`（连续率是否可用） |
| D3 | `AssignmentValiditySummary`（分配有效性摘要） | `global_track_id`（全局航迹标识）、`assigned_resource_id`（已分配资源标识）、`plan_version`（计划版本）、`is_current`（是否当前版本）、`plan_age_s`（最近评估活性年龄）、`cost_margin`（当前方案相对备选的代价裕度）、`resource_feasible`（资源是否可行） |
| D5 | `TerminalAssociationSummary`（末端关联摘要） | `decision_state`（锁定、歧义、保持或重捕获状态）、`terminal_evidence_applicable`（末端证据是否处于适用窗口）、`association_confidence`（关联置信度）、`ambiguity_score`（末端歧义）、`observed_global_track_id`（观测到的全局航迹标识）、连续非锁定/不一致计数、友方冲突、重复锁定、跨视角支持和二级覆盖诊断 |
| main/runtime | `C2Health`（中心健康）、`ResourceSummary[]`（资源摘要列表）、`CommunicationSummary[]`（通信摘要列表）、当前计划与联盟版本、二级计划回填状态 | 当前时间、心跳、链路新鲜度、计划所有者、计划/联盟版本、租约世代、租约到期时间、重规划请求状态、联盟提交状态 |

D1 仍以北-东-地（North-East-Down，NED）坐标系作为融合工作坐标；D4 不做坐标变换，只消费协方差和粗粒度覆盖小区。D4 不使用在线仿真真值生成身份结论。

### 3.2 适配原则

`D4ArbitrationAdapter`（D4 仲裁适配器）使用对象属性或字典字段读取上游数据，不直接导入 D1、D2、D3、D5 的实现类型。适配器按以下顺序构造证据：

1. 解析资源和全局航迹标识；
2. 从协方差构造 D1 不确定度摘要；
3. 区分 D2 连续风险评分与显式已发生事件；
4. 从 D3 最近评估时间计算计划活性年龄；
5. 先构造 D3 联盟安全证据，再归一化 D5 末端证据；
6. 按 `(resource_id, global_track_id)`（资源标识与全局航迹标识对）选择独立仲裁器，避免一个资源/航迹对的迟滞状态污染其他对；
7. 构造二级节点生命周期和持续就绪窗口；
8. 运行仲裁、联盟安全门控、中心重规划生命周期和二级计划生命周期；
9. 输出 D6 可消费的决策记录。

### 3.3 被动降级与 CBBA 数据结构

- `TrackSummary`（航迹任务摘要）：包含 `track_id`（任务使用的上游航迹标识）、`coarse_cell`（粗粒度区域）、`age_s`（年龄）、`confidence_band`（置信等级）、`source_count`（来源数）、`epoch`（世代号）和 `visual_evidence`（分布式视觉证据）。它还可携带 `required_resource_count`（所需资源数）和联盟版本，但轻量 CBBA 只处理单获胜者分配。
- `ResourceSummary`（资源摘要）：包含节点角色、能力类别、可用性、通信等级、人工保持标志、接管优先级、租约、心跳、覆盖、线索新鲜度、云台指向和跨视角注册摘要。
- `BidState`（出价状态）：包含 `task_id`（任务标识）、`bidder`（出价节点）、`score`（出价评分）、`constraints_hash`（约束摘要哈希）、`epoch`（世代号）和 `round_id`（协商轮次）。
- `CBBAResult`（CBBA 结果）：包含唯一任务所有者、共识轮数、是否收敛、冲突计数、完成率、消息计数、估计字节数、最终视图和分配审计。

### 3.4 二级接管数据结构

`SecondaryNodeLifecycleSummary`（二级节点生命周期摘要）同时保存：

- 心跳年龄、心跳是否陈旧；
- 租约世代、租约到期时间和是否过期；
- 覆盖小区是否匹配、覆盖比例；
- 图像线索新鲜度、链路新鲜度和云台指向；
- 是否可见、是否完成稳定跨视角注册、综合能力评分；
- `secondary_readiness_class`（二级就绪等级）：`not_ready`（未就绪）、`visible_only`（仅可见）、`registration_usable`（注册可用但不足以接管）、`takeover_ready`（可接管）；
- 连续就绪决策数、就绪起始时间、持续时间、是否满足持续窗口和回落原因。

`SecondaryTakeoverPlanMetadata`（二级接管计划元数据）只描述状态，不创建系统计划。它有三态：

- `not_applicable`（不适用）；
- `pending_secondary_plan`（二级计划待生效）：D4 已选择来源节点，但当前所有者不变；
- `secondary_plan_active`（二级计划已激活）：main/D3 已回填正确来源、新计划标识与版本、有效租约，且持续就绪没有回落。

### 3.5 原子联盟数据结构

- `CoalitionMemberAck`（联盟成员确认）：绑定资源、全局航迹、联盟标识/版本、计划标识/版本、世代号、成员可执行性、证据时间和有效期。
- `CoalitionCommitState`（联盟提交状态）：记录协调者、必要成员、已确认成员、租约和 `proposed -> collecting_acks -> committed -> executing -> reconfiguring/aborted`（提议、收集确认、已提交、执行中、重构中/已中止）生命周期。
- `CoalitionSafetyEvidence`（联盟安全证据）：记录中心是否可用、联盟是否完整、授权/锁定成员、双版本、冲突原因、原子联盟是否形成、候选动作与门控后动作。

### 3.6 下游输出

| 输出 | 消费方 | 语义 |
|---|---|---|
| `ActiveDegradationDecision`（主动/被动仲裁决策） | main、D6 | 动作、模式、原因、目标二级节点、风险因子、当前绑定是否可信、是否需人工复核 |
| `D4DecisionRecord`（D4 决策记录） | main、D6 | 完整输入摘要、硬/软风险、二级生命周期、接管状态迁移、重规划冷却、联盟门控和审计字段 |
| `SecondaryTakeoverPlanMetadata` | main、D3、D7 | 二级计划待生效/已激活、来源、版本、租约和可执行性；不是系统计划 |
| `D7SecondaryHandoff`（D7 二级交接门控） | D7 | 两阶段交接；阶段 1 不允许视觉比例导航制导（Proportional Navigation Guidance，PNG），阶段 2 仍需新计划和 D5/D7 独立条件 |
| `CBBAResult` | main、D6 | 一对一无中心保底结果与收敛、冲突、完成率、消息开销 |
| `MergeResult`（恢复合并结果） | main、D6 | 中心与降级计划的接受、复核、冲突和是否恢复正常 |
| `EpisodeCommunicationTick`（单次试验时钟步通信状态） | main、D6 | 每时钟步的健康、层级、所有者、版本、ACK、租约、提交、闭锁和恢复状态 |
| `RegionResourceSnapshot`（区域资源快照） | 规则/可选学习建议层 | 版本化、truth-free 变长区域图；含聚合需求、不确定性、可见/一致性、资源/备用、二级和通信、当前 authority fence |
| `RegionResourceRecommendation`（区域资源建议） | main、D6、shadow evaluator | 只含区域配额增减、邻区转移、备用比例、侦察优先级和 hold/replan；不是 D3 assignment，也不授权 D7 |
| `RegionResourceAdvisoryContract`（后投影建议合同） | main 下一轮规划边界 | 内容寻址 ID、创建时间/有效期、scenario/snapshot/authority、source plan、policy/model/projector identity，以及逐区域/transfer generation、资源和 edge 安全证明；不含目标级分配 |
| `RegionResourceConsumptionView`（消费判定视图） | main | 在 current snapshot/formal verdict 上输出 `consumable` 与稳定拒绝原因；`true` 只表示可作为 D3 下一轮输入，不表示已生成计划或获执行授权 |
| `RegionLearningEpisodeSource/Frame`（区域学习 episode 数据） | main writer、离线训练 | source 固化 scenario/version/scale、seed、episode/Git/config identity；frame 固化 truth-free snapshot、显式 target/reward availability 和可选 recommendation |

### 3.7 区域资源快照与动作边界

区域节点必须包含目标需求和高威胁积压的聚合值、D1/D2 不确定性、D5 可见性/一致性、可用资源与备用、二级覆盖/就绪、通信容量/时延/丢包，以及当前 owner layer/node、plan version、epoch 和 lease。区域边包含可转移资源、距离、转移时间、带宽、通信/机动可用性与 partition。合同递归拒绝具体 actor/target/object 真值标识和 `global_track_id` 字段；它不拒绝教师标签使用的 `target` 容器。

建议动作不能列出资源成员或目标标识。`resource_quota_delta` 由投影后的邻边 transfer 重新计算，所有区域之和必须为零；模型不能通过直接写 quota delta 绕开资源守恒。`reserve_ratio`、`reconnaissance_priority`、`hold` 和 `request_replan` 只表达建议，不改变 formal D4 verdict。

规则 fallback 与学习候选在 `RegionResourceAdvisor` 内共享同一 `DeterministicResourceProjector` 实例；学习模型只能返回 `projected=false` 的 raw proposal。投影器随后生成 `d4-region-resource-advisory-v1`：`advisory_id` 是合同内容的 SHA256 幂等键；默认有效期为创建后 1.0 episode-clock 秒，并取所有区域 authority lease 的最早截止。每个区域记录 source snapshot/version/authority、owner/layer、plan id/version、epoch/lease、ACK/fault、资源前后量、protected reserve/committed；每个 transfer 还记录两端 generation、edge 端点、capacity、transfer time、bandwidth 和通信/机动/partition 状态。

消费门严格使用 `evaluated_at < valid_until`。旧 snapshot/plan/epoch、lease 到期、非 projected、ACK 不完整、fault fence、formal verdict 变化、资源不守恒、reserve/committed 保护失败、未知/非邻接/不可用/超 capacity transfer，或已在 gate 中成功消费过的 `advisory_id`，均输出 `consumable=false`。当前 gate 的 replay ledger 是进程内集合；跨进程运行时由 main 持久化。D4 不借此创建或修改 D3 `AssignmentPlan`。

独立 planner 的不透明 `plan_id` 会进入区域 authority 摘要、正式裁决摘要和 advisory 内容地址。跨提交比较必须保留原始记录，先回算三层摘要并验证同一运行内的副本关系，再在只读比较视图中使用 D3 已审计的谱系 token 重算三层身份。`advisory_id` 不能直接删除或改成事件序号。owner/layer、版本、epoch、lease、ACK/fence、区域/任务/航迹/资源/节点/联盟身份和建议动作仍须严格相等。缺完整 authority payload 且无法从现有证明精确回算原摘要时，比较失败关闭。

### 3.8 区域学习 episode 数据治理

`d4-region-learning-dataset-v1` 以完整 episode 为最小持久化和 split 单元。source 必须记录 scenario/version/scale、数值 seed、episode ID、Git commit/dirty 与 config SHA256；每帧 `target` 容器只能保存区域级 `rule|formal` 教师建议或带原因的 unavailable，reward 同样必须显式 available/unavailable，可选 recommendation 只作记录。`target` 字段名和 `target.kind=rule` 本身不是 truth；被拒绝的是 actor/target/object/global-track/evaluator/offline truth 标识及其键变体，不能让真实身份进入在线特征。

stage 产物使用 canonical JSONL header/frame/footer 和 frame SHA；finalizer 再固化逐 episode SHA、dataset SHA、feature/target/reward semantics、全部 source identity 和 availability。同一数值 seed 下的不同场景、规模和多个 episode 原子进入同一 train/validation/test split，三份 seed 两两零交集；唯一 seed 少于 3 或实际 unseen 少于声明下限时不生成 dataset。BC loader 缺 target 即失败，PPO loader 缺 target 或 reward 即失败，二者默认拒绝 dirty source，不以 0 填补。`model-bundle-v2` 可嵌入并验证 dataset/split manifest；这些数据治理能力不改变 D4 authority、lease、epoch、CBBA、联盟或降级状态机。

### 3.9 正式行为克隆与准入边界

2026-07-20 正式数据包含 900 episode 和 1798 frame。训练、验证、内部测试分别使用 70、15、15 个数值 seed，外部保留 seed 1000-1019 不在数据集中。审计重新计算 900 个 episode SHA256，并核对 dataset/source/schema、Git/config identity 和 split hash。固定 seed `20260720` 的行为克隆在 CPU 单线程完成 66 epoch，最佳 epoch 为 54；内部测试损失为 `0.071545`。2026-07-21 准入复跑的端到端建议与投影推理 P95 为 `0.7774 ms`，本地权重 SHA256 仍为 `3da0360be8788f3ffeb8e9f9eba3e0d5369ec0bdf9e05729dfb1db07d71d5f62`。

数据中的 14384 个区域动作没有非零配额、跨区域转移、保持或重规划正样本。保留比例和侦察优先级存在变化，模型可复现这两个连续字段；配额和转移的零误差只反映零动作基线。D6 审计还发现 898/1798 帧只有无归因相邻状态转移，reward、causal label 和 counterfactual label 可用数均为 0。模型置信度头没有校准标签。由此，训练管线可用，但动作多样性不足；低损失不构成完整动作策略能力证据，PPO 不可启动。

模型 manifest 固定 `lifecycle_stage=development`、`maximum_advisor_mode=shadow`、`action_diversity_sufficient=false` 和 `strategy_capability_claim_allowed=false`，并保存五项动作计数。`RegionResourceAdvisor` 会读取模式上限；即使请求 `assist` 并传入 20 个 unseen seed，也只能保持 shadow。权重位于 Git 忽略目录，当前无 Git LFS；普通 Git 只记录训练配置、数据/模型准备度、指标、训练命令、权重 SHA256 和本地相对定位。

### 3.10 共享 seed 切分视图

联合训练不能分别沿用 D3、D4、D5 的模块内 split，否则同一数值 seed 可能在一个模块用于训练、在另一个模块用于测试。D4 新增只读 canonical view，消费 main 发布的 `scalable3d-shared-seed-split-registry-v1`，但不导入 main runtime。消费者独立复现 D3 兼容哈希排序，并校验 registry schema/policy、content/assignment SHA、源 training-seed-registry SHA、100 个 dataset seed 的完整覆盖、无额外 seed 和 1000-1019 保留集隔离。

canonical view 是冻结内存覆盖层。它保存每个 episode 的原 split 和共享 split，并绑定原 dataset SHA、原 split SHA、manifest 文件 SHA、共享 registry 文件/内容 SHA、assignment SHA 和源 registry SHA。源 manifest 与 episode 文件不修改。BC loader 只有显式传入 view 时采用共享 60/20/20；默认仍使用原 70/15/15。

正式 900 episode 的共享视图包含 60/20/20 seed、540/180/180 episode 和 1079/359/360 frame。源数据目录树在审计前后哈希相同。该能力解决数据治理问题，不证明模型收益，不解除动作多样性、reward、PPO 或 assist 门槛。

### 3.11 区域动作覆盖补充课程

`d4-region-action-coverage-curriculum-v1` 是独立的规则 teacher 数据源。它不从正式 episode 抽取标签，也不修改正式 900 episode。生成器读取共享训练 seed 注册表，对每个数值 seed 依次构造三种区域聚合状态：降级失败触发保持、分配冲突触发中心重规划请求、相邻区域余量和需求缺口触发资源转移。动作由现有 `RuleRegionResourcePolicy` 生成，再由 `DeterministicResourceProjector` 投影；课程自身不能直接写入可信 quota。

本次配置为 4 个区域、17 份聚合资源、100 个 seed、每 seed 3 帧。结果含 hold 100、request-replan 200、非零 quota action 200、transfer 100。canonical 训练、验证、测试桶为 60/20/20 seed，每个桶都有四类动作。硬约束违规、在线真值字段和保留 seed 泄漏均为 0。

课程没有动作执行后的真实结果。300 帧 reward 和 outcome 全部显式 unavailable，因此只能用于行为克隆 teacher 覆盖和离线 shadow。main 已在 detached clean worktree commit `9445ed6` 上生成 dirty episode 为 0 的课程，canonical 训练桶 180 帧可由行为克隆只读 view 加载；PPO loader 仍因 reward unavailable 失败关闭，assist 和 authority 不开放。首次 dirty 产物只保留为开发历史。该结果关闭 producer、标签覆盖和 clean BC 数据准入缺口，不关闭策略有效性、因果归因、外部保留 seed 性能或在线准入。

### 3.12 全样本准入审计

`d4-region-resource-full-sample-admission-audit-v1` 对冻结正式数据和 clean supplemental 课程执行只读全样本检查。正式数据为 900 episode、1798 frame/sample、14384 action；共享规范视图按 60/20/20 seed 映射为 540/180/180 episode、1079/359/360 sample 和 8632/2872/2880 action。补充课程为 100 episode、300 frame/sample、1200 action，映射为 60/20/20 episode、180/60/60 sample 和 720/240/240 action。审计逐项核对 manifest、episode SHA256、来源/schema、数值有限性、动作类型、配额守恒、transfer 邻接和容量、owner/plan/epoch/lease/version、保留 seed、dirty 状态和真值隔离；900/900 与 100/100 episode 哈希通过，安全有效样本分别为 1798/1798 和 300/300，违规数为 0。

准入状态 `complete` 只表示上述模块内数据合同全部通过。正式与补充数据中的 `target.kind=rule` 都是规则教师标签，不能作为在线真值或策略收益；`recommendation.projected=true` 只表示后投影建议通过确定性安全合同，不能作为运行时 applied ACK。显式投影前 action mask、被拒旧计划/旧时期/旧租约候选、真实 `CoalitionMemberAck`、observed outcome、可归因 reward 和同 seed paired shadow 均没有可验证字段，状态必须保持 `unavailable/pending`。D6 还需按 tracked JSON 显式路径和带外 SHA256 独立准入。在这些证据形成前，PPO、assist 和 authority 不开放。

## 4. 数学模型与核心公式

### 4.1 集合、状态与决策

设资源集合为

\[
\mathcal{R}=\{r_i\}_{i=1}^{M},
\]

目标任务集合为

\[
\mathcal{T}=\{t_j\}_{j=1}^{N}.
\]

这里，\(M\) 是输入资源数，\(N\) 是输入任务数；二者由 main 的场景输入决定，不固定为 2 或 5。对一对一保底任务，D4 寻找映射 \(a:t_j\mapsto r_i\)。对需要 \(k_j>1\) 个资源的任务，必须使用联盟 \(\mathcal{C}_j\subseteq\mathcal{R}\) 和原子提交门控，不能把一条任务复制 \(k_j\) 次来冒充联盟。

D4 决策函数可抽象为

\[
d_t=\pi(z_t,h_t,m_t),
\]

其中 \(z_t\) 是 D1/D2/D3/D5 的当前证据，\(h_t\) 是中心与二级节点健康，\(m_t\) 是迟滞、重规划请求、计划与联盟提交的内部记忆；\(d_t\) 只取六种实现动作之一。

### 4.2 中心健康判定

令最近一次有效中心心跳时间为 \(t_{hb}\)，当前时间为 \(t\)，心跳年龄为

\[
\Delta t_{hb}=t-t_{hb}.
\]

`FailoverCoordinator`（降级协调器）的默认阈值是：预警 1 秒、陈旧 2 秒、失效 4 秒。心跳窗口长度为 5，退化、可疑和失效的默认缺失计数阈值分别为 1、2、3。窗口缺失数为

\[
m_t=\sum_{q\in W_t}\mathbf{1}[q=\text{缺失}],
\]

其中 \(W_t\) 是最近五个心跳样本，\(\mathbf{1}[\cdot]\) 是条件成立时取 1 的示性函数。实际迁移还受状态驻留时间和 peer 多数阈值约束。若参与判定的节点数为 \(n\)，默认多数阈值为

\[
q=\left\lfloor\frac{n}{2}\right\rfloor+1.
\]

只要 peer 失效票数达到 \(q\)，中心可直接进入 `failed`。反向恢复不对称：恢复心跳和 digest 只使状态进入 `suspect`（可疑），必须通过双轨合并与显式接受才能回到 `normal`（正常）。

### 4.3 协方差到 D1 风险

适配器从上游协方差矩阵 \(P\) 取位置子矩阵 \(P_p\) 和速度子矩阵 \(P_v\)。位置标准差定义为

\[
\sigma_p=\sqrt{\max(\lambda_{\max}(P_p),0)},
\]

其中 \(\lambda_{\max}(P_p)\) 是位置协方差最大特征值；速度标准差定义为

\[
\sigma_v=\sqrt{\max(\operatorname{tr}(P_v),0)}.
\]

当前规则中，\(\sigma_p\ge 20\) 米产生中等位置不确定风险，\(\sigma_p\ge 50\) 米产生高风险；\(\operatorname{tr}(P)\ge 2500\) 产生高协方差风险；量测年龄大于 4 秒产生陈旧量测风险。这些是离线规则阈值，不是传感器物理认证参数。

### 4.4 D2、D3 与 D5 风险门限

D2 当前门限为：

- 关联歧义 \(a_2\ge0.35\) 为中等风险，\(a_2\ge0.70\) 为高风险；
- `duplicate_track_risk`（重复航迹连续风险）\(\ge0.50\) 只产生软观察证据；
- 只有显式重复计数、增量或已观测标志才产生硬重复事件；
- 只有 `truth_metrics_available=true`（真值指标可用）时，`id_switch_count>0`（身份切换计数大于零）才成为硬风险；身份切换（Identity Switch，IDSW）不会由不可用真值的占位数值推断；
- 只有 `continuity_available=true`（连续率可用）时，连续率 \(<0.60\) 才成为硬风险。

D3 当前门限为：

- `is_current=false`（不是当前计划）、计划活性年龄大于 4 秒或资源不可行是硬风险；
- `cost_margin<0.10`（代价裕度过低）是软证据，不能单独触发逐帧重规划；
- 计划年龄优先以最近评估时间计算，计划创建时间只在缺少最近评估时间时回退使用，因此稳定计划标识不会仅因存在时间较长而被误判陈旧。

D5 中，友方冲突、重复末端锁定、资源与分配不一致、已分配/已观测全局航迹不一致属于硬绑定或身份证据。低置信度（小于 0.65）、高末端歧义（大于等于 0.55）和高跨视角风险（大于等于 0.65）只在末端证据适用窗口内作为软风险。

### 4.5 末端绑定与末端视觉准备度分离

令当前 D3 绑定为 \((r_a,g_a,v_a)\)，分别表示资源、全局航迹和计划版本；D5 末端摘要提供 \((r_o,g_o)\)。D4 的 `terminal_consistent`（当前计划绑定是否可信）要求没有以下硬拒绝原因：

\[
r_o\ne r_a,
\quad g_o\ne g_a,
\quad \text{友方冲突},
\quad \text{重复锁定},
\quad \text{计划陈旧、非当前或不可行}.
\]

低置信度、歧义、`reacquire`（重捕获）或连续未锁定本身不证明中心绑定错误。它们只描述视觉准备度，并由 D5/D7 独立决定是否允许后续导引。这个分离修复了历史上 D4 重复解释 D5 就绪性、导致无硬冲突时 `terminal_consistent=false` 的问题。

`terminal_evidence_applicable=false`（末端证据尚不适用）时，远距阶段的普通低置信度、歧义、跨视角软风险和未锁定连续计数不参与辅助/重规划动作；明确观测航迹错配、资源错配、重复锁定和友方冲突仍立即有效。

### 4.6 二级节点能力评分

对候选二级节点，D4 构造以下归一化分量：

- \(c\)：覆盖比例；
- \(n\)：网络同帧全覆盖率；若缺失，则回退为 \(c\)；
- \(r\in\{0,1\}\)：是否有稳定注册；
- \(h,l,u\in\{0,1\}\)：心跳、链路、线索是否新鲜；
- \(f=(h+l+u)/3\)：综合新鲜度；
- \(g\in\{0,1\}\)：云台指向是否可用。

当前综合能力评分为

\[
S_{sec}=\operatorname{clip}_{[0,1]}(
0.25c+0.15n+0.25r+0.15f+0.10g+0.05u+0.03l+0.02h
).
\]

式中各变量都是摘要证据，不是图像几何计算。四级分类为：

1. **未就绪**：节点不可用、覆盖为零、心跳/租约/线索/链路/云台条件失败；
2. **仅可见**：可见但没有稳定跨视角注册；
3. **注册可用**：已有注册，但 \(c<0.65\)、可用的 \(n<0.80\) 或 \(S_{sec}<0.70\)；
4. **可接管**：可见且已注册，并满足覆盖、网络全覆盖和综合评分门限。

若网络全覆盖率没有提供，代码不以缺失值直接判失败；它用覆盖分数参与评分并把网络门限视为可用。真实接线应尽量提供该字段，以减少乐观缺省。

### 4.7 持续就绪与二级节点选择

瞬时 `takeover_ready` 不足以接管。对节点 \(s\)、航迹 \(g\) 和覆盖小区 \(c\) 的组合，持续就绪条件为

\[
R_{s,g,c}(t)=
\mathbf{1}[K\ge3]
\cdot\mathbf{1}[t-t_0\ge0.2]
\cdot\mathbf{1}[\Delta t_{evidence}\le1.0],
\]

其中 \(K\) 是不同时间戳上的连续可接管判定数，\(t_0\) 是本次连续就绪起点，\(\Delta t_{evidence}\) 是相邻证据间隔。相同时间戳的多资源/多目标重复调用不增加 \(K\)；时间倒退、间隔超过 1 秒或能力回落会从 1 重新计数。

通过所有硬过滤后，候选按以下字典序排序：

\[
(\text{更小接管优先级},
\text{更高能力评分},
\text{节点类别秩},
\text{更新租约世代},
\text{节点标识}).
\]

机动高空侦察、机动二级侦察、固定系留二级、普通二级侦察、地面备份依次参与类别秩比较。持续条件不满足时，候选二级接管会保守回落为分布式路径或待生效/不可执行状态，而不是放宽门限。

### 4.8 CBBA 出价与视觉修正

当前轻量 CBBA 对资源 \(i\) 和任务 \(j\) 的基础评分为

\[
B_{ij}=2.0C_j+1.4A_i+0.5L_i+1.2M_{ij}+1.0Q_j-0.8D_j+V_{ij}-0.15|b_i|.
\]

变量物理意义如下：

- \(C_j\in\{1,2,3\}\)：任务低、中、高置信等级；
- \(A_i\in\{0,1,2,3\}\)：资源无、低、中、高可用等级；
- \(L_i\in\{0.5,1.0,1.5\}\)：通信差、受限、良好等级；
- \(M_{ij}\)：能力匹配分，`observe`（观测）为 1.0，`relay`（中继）按来源数为 0.85 或 0.65，`hold`（保持）为 0.2，其他为 0.5；
- \(Q_j=0.15\min(\text{来源数},3)\)：多来源奖励；
- \(D_j=\min(\max(\text{航迹年龄},0),30)/30\)：航迹年龄惩罚；
- \(V_{ij}\)：D5 分布式视觉证据修正；
- \(|b_i|\)：资源当前任务束（bundle）长度。

视觉修正遵循“支持可加分、身份冲突可阻断”：

- 当前资源有直接视觉支持时，完整证据最多加 2.75；仅假设证据最多加 0.75；
- 其他资源被支持而当前资源不在支持集合时减 1.25；
- 当前资源歧义减 1.25，并按末端歧义再减最多 1.0；
- 重复锁定风险对相关资源减 2.5，对其他资源减 0.75；局部身份冲突再减 1.0；
- 友方冲突、陈旧/缺失/冲突全局航迹标识或当前资源处于保持集合时，直接不产生可执行出价。

获胜比较首先看更新世代，再看更高评分；评分在 \(10^{-9}\) 容差内相同时，使用更小节点标识和更小约束摘要确定性消歧。只有所有节点对每个任务的获胜者和评分视图一致时才算收敛；未收敛时 `assignments`（分配结果）为空，不发布为有效保底计划。

若通信图边集合为 \(\mathcal{E}\)，任务数为 \(|\mathcal{T}|\)，每轮获胜者/出价（winner/bid）传播的量级为

\[
O(|\mathcal{E}|\,|\mathcal{T}|).
\]

全连接 \(M\) 节点网络约为 \(O(M^2|\mathcal{T}|)\)。稀疏网络降低单轮消息量，但通常增加传播轮数。当前 `SimulatedNetwork`（内存仿真网络）只使用均匀延迟和独立丢包近似，不代表真实网络队列与协议。

### 4.9 原子联盟提交条件

对需要 \(k_j>1\) 个资源的目标，设必要成员集合为 \(R_j\)，已确认集合为 \(A_j\)。一个降级保底（fallback）联盟可进入 `committed`（已提交）或 `executing`（执行中）的必要条件可写为

\[
G_j=
\mathbf{1}[A_j=R_j]
\mathbf{1}[t<t_{lease}]
\mathbf{1}[v_p=v_p^*]
\mathbf{1}[v_c=v_c^*]
\mathbf{1}[e=e^*]
\mathbf{1}[d=d^*]
\mathbf{1}[\text{成员可执行}],
\]

其中 \(t_{lease}\) 是联盟租约到期时间，\(v_p\) 和 \(v_c\) 是计划与联盟版本，\(e\) 是世代号，\(d\) 是联盟摘要。只有 \(G_j=1\) 才设置 `atomic_coalition_formed=true`（原子联盟已形成）。缺 ACK、旧版本、旧世代、过期租约、非必要成员确认、成员不可执行、网络分区或 digest 冲突都保持失效时闭锁（fail closed）。

合法联盟内多个授权资源锁定同一 `global_track_id` 不算重复所有者；联盟外、超额或旧版本资源锁定会被拒绝。轻量单获胜者 CBBA 不承担 \(k_j>1\) 的成员形成。

### 4.10 离线代价差距

若 D3/main 提供同一场景的中心计划和代价矩阵，D4 可计算

\[
\Delta C=C_{CBBA}-C_{center},
\qquad
\delta C=\frac{\Delta C}{|C_{center}|},
\]

其中 \(C_{CBBA}\) 是 D4 保底分配总代价，\(C_{center}\) 是中心化计划总代价。若任一已分配任务/资源对缺少代价，总代价和差距保持不可用，不补造数值。该辅助函数（helper）只做离线比较，不在无中心路径运行匈牙利算法（Hungarian algorithm）或最小费用流（Minimum Cost Flow）。

### 4.11 区域所有权与世代

scalable3d 区域集合记为 \(\mathcal{R}\)。每个区域只能有一个 active owner：

\[
\forall r\in\mathcal{R},\quad \sum_o \mathbf{1}[owner(r)=o\land active(r)]\le 1.
\]

中心未失效时 owner 保持中心，D1/D2/D3/D5 主动证据只能请求辅助、重规划或保持复核；中心计划中的 \(k>1\) 任务也必须完整 ACK 后才把 owner 标为 active。中心失效后，机动高空二级节点必须对区域具有显式 coverage，并满足完整 strict readiness 与 `secondary_lease_epoch >= authority_epoch`。只有无有效二级节点时才进入受约束 distributed candidate formation。owner/layer 切换要求 `epoch` 与 `plan_version` 同时严格递增；同 generation 换 owner、过期租约或任一层级分区都闭锁。区域 authority/commit lease 取 authority、D3 task 和二级 lease 的最早 expiry。区域候选形成按 capability、跨区域 capacity、communication 和 D5 member evidence 做确定性选择，一个成员可覆盖多项 capability，但 \(k>1\) 的可执行性仍由第 4.9 节完整 ACK 决定。

### 4.12 区域资源安全投影与学习奖励

设区域配额变化为 \(\Delta q_r\)，接受的有向邻边转移为 \(x_{uv}\)。确定性投影强制：

\[
\sum_{r\in\mathcal R}\Delta q_r=0,\qquad
\Delta q_r=\sum_u x_{ur}-\sum_v x_{rv}.
\]

仅当边可通信、可机动且未 partition 时允许 \(x_{uv}>0\)，并满足 edge capacity。源区域转出后必须保留已提交联盟资源和最低备用；owner/plan/epoch/lease 与 formal verdict 不一致、fault fence、缺 ACK 或过期 lease 时该区域 transfer 为零并进入 hold。正式 v1 观测成本固定为高威胁积压、配额满足缺口、转移完成缺口、备用不足、通信负载、分配冲突、降级失败和计划抖动八项归一化成本的加权平均；只有 ACK 锚定、来源哈希完整且八项均可用的新执行计划窗口才取负成本作为非因果观测奖励。旧 `compute_region_resource_reward()` 不含 availability、provenance 和窗口绑定，只是研究辅助函数。任何奖励都不能减弱安全投影条件。

## 5. 算法步骤

### 5.1 每次仲裁的默认步骤

1. **解析绑定**：确定资源标识、全局航迹标识、覆盖小区和当前计划版本。
2. **归一化 D1-D5 证据**：计算协方差风险、关联风险、计划活性与末端证据适用性。
3. **构造联盟安全证据**：校验需求数、成员、计划/联盟双版本、视觉共识和可选原子提交。
4. **更新二级生命周期**：检查心跳、租约、覆盖、线索、链路、云台和跨视角注册，计算能力评分与四级就绪性。
5. **更新持续窗口**：按节点、航迹和覆盖小区累计不同时间戳的连续就绪证据。
6. **运行基础仲裁**：先处理友方冲突，再处理中心失效，然后处理中心计划硬失效、远距软证据、末端持续不一致和一般风险。
7. **应用迟滞**：在风险窗口未满足或释放条件未满足时保持原动作。
8. **应用联盟安全门控**：多成员降级保底没有合法原子提交时，中心可用则请求重规划，中心不可用则保持复核。
9. **应用中心重规划生命周期**：抑制冷却期内重复的非硬请求；硬安全风险不受抑制。
10. **应用二级计划门控**：校验来源、持续就绪、版本单调、租约世代和租约到期时间。
11. **输出审计记录**：把候选动作、最终动作、硬/软风险、状态迁移和拒绝原因交给 main/D6。

### 5.2 中心可用时的动作优先级

1. 友方冲突：`hold_for_review`。
2. D3 计划非当前、陈旧、资源不可行，或明确资源/身份硬错配：`request_center_replan`。
3. 末端证据尚不适用，且只有软风险：`continue_center`，但保留风险审计。
4. 末端窗口内持续 `ambiguous/hold/reacquire`，但没有身份或绑定硬冲突：有健康二级节点则 `request_secondary_assist`，否则继续中心观察。
5. D1/D2 风险升高而当前绑定仍可信：优先请求二级辅助；若没有辅助节点且风险属于硬主动仲裁因素，则请求中心重规划。
6. 风险低且绑定可信：`continue_center`。

### 5.3 中心失效时的被动接管

1. 只有 `C2Health.FAILED`（中心失效）才启动被动接管。
2. 过滤处于人工保持、无可用性、覆盖不匹配、心跳/租约/线索/链路陈旧或云台不可用的二级节点。
3. 对剩余候选计算瞬时评分和持续就绪；满足后输出 `degrade_to_secondary`。
4. 二级节点不满足持续条件时输出 `degrade_to_distributed`，进入轻量 CBBA 或原子联盟提交路径。
5. 一对一 CBBA 未收敛时不发布分配；多成员联盟无完整提交时保持复核或撤销。

### 5.4 单次试验时钟通信状态机

`AirSimEpisodeCommunicationAdapter`（AirSim 单次试验通信适配器）不启动 AirSim，只消费 main 提供的严格递增单次试验（episode）时间戳。默认验证配置为：中心预警 0.5 秒、中心失效 1.0 秒、二级心跳陈旧 0.75 秒、ACK 截止 0.75 秒、ACK 有效期 1.0 秒、联盟租约 10 秒、恢复需连续 2 个 digest 匹配时钟步。

每个时钟步（tick）的处理顺序为：

1. 记录中心与二级心跳；
2. 分类中心健康，选择期望层级；
3. 递送到期 ACK，并拒绝旧世代、旧计划版本或过期 ACK；
4. 若需要接管，提升 epoch、计划版本和联盟版本，清空可执行所有者并开始收集 ACK；
5. 全部必要成员确认后从 `committed` 进入 `executing`，才发布单一可执行所有者；
6. 截止时间到达仍缺 ACK 时中止；分区时清空降级保底所有者；
7. 中心恢复时连续校验双轨 digest，且必须收到显式恢复授权，之后再以新世代恢复中心。

该适配器的 `owner_id`（所有者标识）是层级/计划发布提示，main 仍负责生成系统级计划。

### 5.5 scalable3d 区域仲裁步骤

1. 从 `scalable3d-scenario-v1` mapping 读取 target/resource/recon/region count，不导入 main 模块。
2. 校验 schema、scenario 声明数量、region definition、active task、secondary coverage 和 fallback member region scope。
3. 按区域聚合 D1 covariance/age、D2 ambiguity/IDSW/duplicate、D3 plan/version/epoch/lease/current/feasible 和 D5 consistency/binding/friend/duplicate。
4. 中心未 `failed` 时保留中心 owner；中心 `failed` 时选 valid `mobile_high_recon`；没有有效二级节点时才形成 distributed candidate。
5. 校验 authority generation 与最早 lease；对中心、二级和 distributed 三层的 \(k>1\) 候选逐成员记录 ACK，并在完整 ACK 后一次性进入 `committed`；分区时三层均闭锁。
6. 输出 `d4-regional-failover-v1` truth-free payload，包含逐区域 ownership、selected layer、action、risk、readiness、assignment、commit 和 reject reason。

## 6. 状态机、门控与身份安全规则

### 6.1 `C2Health` 状态机

| 状态 | 中文含义 | 当前主要进入条件 |
|---|---|---|
| `normal` | 正常 | 心跳、digest、epoch 可信，且不存在未完成恢复合并 |
| `degraded` | 退化 | 心跳预警、缺失窗口初步触发，或降级节点正在维持连续性 |
| `suspect` | 可疑 | 心跳陈旧、digest 冲突、中心 epoch 过旧、恢复待合并 |
| `failed` | 失效 | 硬超时或 peer 多数判定失效 |

恢复路径必须经过双轨校验；`stable_recovery_s`（稳定恢复时间）字段存在于协调器配置，但当前基础 `merge_recovery()` 没有实现完整多轮稳定窗口。

### 6.2 降级动作状态机

```text
continue_center
  -> request_secondary_assist       中心仍拥有计划，仅请求补充观测
  -> request_center_replan          中心仍拥有计划，由 main/D3 生成新版本
  -> hold_for_review                身份/友方/联盟安全证据冲突

C2Health == failed
  -> degrade_to_secondary           仅在持续就绪和计划门控通过后
  -> degrade_to_distributed         二级不可用或不满足接管条件
  -> hold_for_review                原子联盟或身份安全门控失败
```

### 6.3 迟滞与防抖

主动仲裁有两类时间记忆：

- 风险窗口：最近 \(w\) 个样本中至少 \(k\) 个风险样本成立才认为窗口触发；默认 \(w=k=1\)，保持轻量单步行为；
- 释放迟滞：只有绑定可信、风险为空、连续一致帧数达到配置值且最短驻留时间满足，才释放上一降级动作；默认连续 1 帧、驻留 0 秒。

适配器按资源/航迹对隔离上述状态。二级持续就绪另按节点/航迹/覆盖小区隔离，避免同一帧多次调用虚增连续计数。

### 6.4 中心重规划请求生命周期

`CenterReplanStatus`（中心重规划状态）有 `pending`（等待处理）、`applied`（已应用）、`acknowledged_no_change`（确认无需变更）、`expired`（已过期）四态。风险签名是排序去重后的不可变风险元组。

默认冷却时间为 2 秒，以解决时间为起点；等待中的请求没有解决时间时，以请求时间为起点。严格在

\[
t\ge t_{reference}+2.0
\]

时重新开放非硬风险请求。友方冲突、重复锁定、资源/身份错配、显式身份切换或重复事件、计划/联盟版本错误、资源不可行、联盟冲突与提交不完整等硬风险直接绕过冷却。

若等待中的请求与当前目标/联盟范围一致，中心仍可用，双版本当前，所有主成员稳定锁定并形成无冲突视觉共识，且必要提交完整，D4 可输出 `continue_center` 并给出 `acknowledged_no_change` 解决提示。它不清除 D5/D7 自己的门控。

### 6.5 二级计划生命周期

二级计划可执行条件为：

\[
E_{sec}=
\mathbf{1}[\text{已激活}]
\mathbf{1}[\text{来源匹配}]
\mathbf{1}[\text{持续就绪}]
\mathbf{1}[e_{lease}\ge e_{required}]
\mathbf{1}[t<t_{lease}]
\mathbf{1}[v_{new}>v_{current}\ \text{或同一已激活计划}].
\]

其中来源必须等于选中的二级节点；新计划版本必须严格更新，只有当前所有者已经是同一个二级计划时才允许标识和版本相等。任何条件失败都会保留待生效、标记不可执行，或在当前二级计划已失效时进入 `hold_for_review`。

### 6.6 身份与协方差安全

- D4 只复制上游 `global_track_id`，不创建、不改写、不按本地视觉重绑定；
- D1 协方差始终作为风险证据保留，不能用低维点估计替代；
- D2 的连续风险评分不能冒充显式身份切换或重复事件；
- D5 友方冲突优先于接管和重规划，直接保持复核；
- 合法联盟内的授权多资源锁不算重复，联盟外锁定仍闭锁；
- D4 的 `terminal_consistent=true` 只表示当前计划绑定未被硬证据推翻，不表示 D5 已锁定，也不授权 D7；
- 旧计划、旧联盟版本、旧 epoch、过期 lease、缺 ACK 或 digest 冲突都不能通过“可见性高”或“评分高”绕过。

## 7. 与其他模块及 main/runtime 的接口

### 7.1 D1 传感器融合

D1 提供带协方差和量测时间的全局航迹。D4 从协方差计算位置/速度不确定度，从量测时间计算年龄；不重新滤波、不做坐标转换、不修改航迹。

### 7.2 D2 数据关联

D2 提供歧义、显式 IDSW、重复航迹事件、连续风险和航迹连续率。在线真值隔离时，D4 读取可用性标志，防止缺失真值的零值或占位值变成错误硬风险。`id_switch_count`（身份切换计数）仍保持显式，不被 D4 隐藏或重建。

### 7.3 D3 分配规划

D3 是中心计划权威。D4：

- 读取计划标识、版本、最近评估时间、资源可行性、代价裕度、联盟成员和需求；
- 对非当前、陈旧、不可行或联盟冲突计划请求中心重规划；
- 输出二级计划来源、待生效/已激活、租约和 supersedes（替代关系）元数据；
- 不创建系统级 `AssignmentPlan`，不绕过 D3 的旧版本拒绝。

### 7.4 D5 末端关联

D5 提供末端状态、友方冲突、重复锁定、观测全局航迹、跨视角共识和二级覆盖/注册漏斗。D4 只判断这些证据是否支持保持绑定、请求辅助、重规划或闭锁；不做像素几何，也不把二级检测可见直接解释为接管就绪。

完全无中心时，`merge_distributed_visual_evidence_into_tracks()`（把分布式视觉证据合入航迹摘要）可把 D5 多 peer 证据写入匹配的 `TrackSummary.visual_evidence`（航迹摘要视觉证据），但仍按上游全局航迹标识匹配。

### 7.5 D6 评估指标

D6 只读消费 D4 的事件和结果，不控制系统。主要字段包括：动作、模式、原因、硬/软风险、误触发候选、接管延迟、待生效持续时间、就绪等级、覆盖缺口、共识轮数、完成率、冲突、消息数、唯一所有者和脑裂防护结果。

### 7.6 D7 导引门控

D7 继续独立检查计划、所有者、末端锁定和导引合同。二级接管的第一阶段 `visual_png_allowed=false`（不允许视觉 PNG）；第二阶段仍需二级计划已激活、来源与版本正确、租约有效、能力为 `takeover_ready` 且持续就绪。D4 不实现 D7 的导引公式，也不替代其运动学可达性判断。

### 7.7 main/runtime

main/runtime 负责 AirSim 启停与 episode 顺序、故障注入时间轴、D3 新计划发布、所有者/版本回灌、D6 日志收集和最终报告。D4 的 episode 适配器只返回可审计状态；main 必须把它转换成系统级计划和运行时动作。scalable 3D 质点模块栈现已完成该转换：单一二级、多二级区域 owner 和连续失效后的 distributed D3 plan 都经过 D4 verdict，D7 再检查 owner/epoch/lease/commit/fault fence。该接线事实不代表 AirSim 或真实网络已验证。

## 8. 已实现主线、可选算法与未实现能力

仓库以优先级 0、优先级 1、优先级 2（Priority 0/1/2，P0/P1/P2）表示优先级层级；本文只用这些标签描述项目状态，不把优先级计划当作已实现能力。

### 8.1 当前已实现并属于默认主线

| 能力 | 当前事实 |
|---|---|
| 中心健康与被动接管 | 四态健康、滑动窗口、缺失阈值、peer 多数、digest/epoch 检查、中心 -> 二级 -> 分布式顺序 |
| scalable3d 区域 authority | 动态 scenario/region/task/node metadata、声明数量上限、逐区域唯一 owner、机动高空二级 coverage/readiness、epoch+plan version+最早 lease 和全层原子门控 |
| 主动降级仲裁 | 中心可用时只继续中心、请求辅助、请求重规划或保持复核；末端适用性、硬/软风险和按绑定隔离迟滞已实现 |
| 二级接管门控 | 四级瞬时就绪、综合评分、默认 3 次/0.2 秒持续窗口、来源/版本/租约严格校验和待生效/已激活状态 |
| 原子联盟安全合同 | 双版本、epoch、成员 ACK、租约、digest、分区和 fail-closed；已有二级与 peer 正例及缺 ACK 负例 |
| 一对一无中心保底 | 本地轻量 CBBA、D5 视觉风险修正、唯一任务所有者、确定性消歧、收敛/冲突/消息审计 |
| episode 时钟接口 | 严格递增时间戳、顺序接管、ACK 延迟/丢弃、分区、租约、中心双轨恢复状态 |
| D6 输出 | 仲裁事件、二级生命周期、接管迁移、联盟提交、CBBA 与通信指标 |

### 8.2 已实现但仅属可选或离线

| 能力 | 状态边界 |
|---|---|
| P1 九场景确定性扰动回放 | 已实现，用于合同回归；不等于真实网络或物理连续性 |
| P1 六类多随机种子通信回放 | 已实现内存通信矩阵；不等于真实带宽、排队、重传或硬件 |
| P2 原生联盟故障回放 | 已实现且与在线 D4 隔离；CBBA 只选协调者/补位候选，不冒充多成员形成 |
| CBBA 与中心化代价差距 | 辅助函数已实现；只有 D3/main 提供同场景代价矩阵时才有结果 |
| 外部能力探测 | 只探测本地参考路径和源码能力，不导入、不执行、不增加默认依赖 |
| 区域资源规则建议与投影 | 已实现 truth-free 变长区域图、守恒/邻边/备用/authority/commit/fault 安全投影；只输出建议 |
| 共享区域图学习研究管线 | 旧 900-episode 候选保留为历史冻结基线；新版候选合并 clean supplemental 课程并完成动作平衡训练、validation 置信拟合和独立 calibration，四类动作均有正样本。新版仍强制 development/shadow-only，PPO/assist/authority 不可用 |
| 区域学习 episode dataset | 正式 dataset-v1 已完成 900 episode/1798 frame 审计和 70/15/15 seed 原子 split；外部 1000-1019 保持隔离。reward/causal/counterfactual 仍 unavailable |
| 跨模块共享 seed 切分消费端 | D4 已实现独立严格校验和只读 60/20/20 canonical view；原 dataset 零修改。仅属 development/data-governance，不是模型性能证据 |
| 区域动作覆盖补充课程 | 独立 producer 已覆盖 hold、request-replan、非零 quota 和 transfer；所有 target 经确定性投影，reward/outcome unavailable。仅用于 clean 来源下的行为克隆和离线 shadow，不是正式策略证据 |
| paired shadow evaluator | 已报告 backlog、transfer、churn、communication、fail-closed、安全违规和 P50/P95 latency；少于 20 个未见 seed 不推荐 assist |

### 8.3 未实现或明确不作为 D4 主线

| 能力 | 当前严格结论 |
|---|---|
| 麻省理工学院（Massachusetts Institute of Technology，MIT）CBBA 外部执行 | 未集成。矩阵实验室（Matrix Laboratory，MATLAB）数值计算与仿真平台参考代码即使被探测到，也没有运行时适配器 |
| 通信感知一致性捆绑算法（Communication-Aware Consensus-Based Bundle Algorithm，CA-CBBA）外部执行 | 未实现；已审计公共参考没有可执行源码，不存在性能结论 |
| 耦合约束一致性捆绑算法（Coupled-Constraint Consensus-Based Bundle Algorithm，CCBBA） | 只作为研究方向，未进入默认或在线路径 |
| 独立单轮拍卖 | 未实现；当前 CBBA 含获胜者/出价思想，但不是独立拍卖状态机 |
| 合同网协议（Contract Net Protocol，CNP） | 未实现管理者/承包者（manager/contractor）公告、投标、授标和失败重招标状态机 |
| 自主多成员形成与完整重构 | 区域能力与跨区域容量约束的确定性 bid selection 已实现；仅 distributed fallback 使用该算法。完整 CBBA/CCBBA 共识、全局组合最优、时序约束、预留激活、缩编、补位和整盟重组未实现 |
| 完整中心恢复审计 | 当前 `merge_recovery()` 只比较分配所有者与 epoch；完整航迹、计划、末端锁定、通信和 D5/D7 门控 digest 尚未合并 |
| 真实通信和视频链路 | 未实现真实 RF、网状网络（mesh）、带宽、时钟漂移、操作系统队列、乱序、重传和硬件故障认证 |
| 虚拟中心优化 | 明确不在无中心路径运行中心匈牙利算法或最小费用流；只允许离线对照 |
| D4 直接生成系统计划 | 明确不做；D3/main 拥有 `AssignmentPlan` |
| 已验收可推荐模型 | 已有开发 checkpoint，但无动作正样本、D6 可验证回报和外部 20-seed paired 结果；不得声称 learned policy 优于规则，最高只允许 shadow |

## 9. 2026-07-20 验证状态

### 9.1 当前结果

最新真实 AirSim M5N2 批次完成 baseline/candidate 各 10 seeds，共 20/20 case。该批中心 owner 始终有效且 `active degradation=0`，属于中心继续执行的负对照，不是 secondary/distributed 故障注入。物理结果为 coalition completion `0/20`、第二 primary 进入 5 m `0/20`；20 个第二 primary 均报告 `collision_stop`，但未持久化碰撞对象，因而不能从该字段推断冲突类型。

这组结果只支持两个判断：一是没有因物理失败自动误触发 D4 主动降级；二是 M-to-N 第二 primary 和联盟物理闭环仍未完成。D4 不使用单个 `collision_stop` 或“未进入 5 m”直接改变 owner，而继续依据 D1/D2/D3/D5 的不确定性、关联、计划有效性和末端一致性证据仲裁。D4 main-bus 阶段 mean/P95/max 约为 `5.59/6.70/94.10 ms`，当前 control tick 总体超时不能归因于 D4 算法计算。额外 `png_ttc_2v2_seed001` 排除在聚合之外，dropout case 为 0。

根据 2026-07-13 主验证报告与 D4 审计：

- 2026-07-21 全样本准入阶段为 **397/397 项通过**，验收阈值为零失败；加入运行时确认和区域奖励合同时为 **449/449**，候选门诊断阶段为 **482/482**。2026-07-25 当前 D4 全量为 **569/569**。全样本审计专项 10/10，覆盖正常数据、非有限值、规范切分错误、配额不守恒、非法转移、旧 epoch/lease/version、generation 回退、真值泄漏和文件篡改。正式 900 episode 与补充 100 episode 的模块内全样本状态均为 complete；D6 外部复核和真实 ACK/outcome/reward/paired-shadow 仍 pending。该结果不包含新的 AirSim 或真实网络样本，历史阶段计数保持不变。
- `build_d7_secondary_handoff()` 与 `build_secondary_takeover_plan_metadata()` 当前统一要求 readiness exact-true、expected/actual source 均存在且匹配、plan/required lease epoch 均存在且满足、expiry/current time 均存在且严格 `current_time < expiry`。逐字段 `None`、完整正例和同 id/version 维持路径均有回归；未运行新 AirSim episode。
- 完全分布式 interceptor/peer 选择不套用二级视觉 readiness 门；动态 N/M、版本/epoch/lease、ACK 和 `global_track_id` 所有权规则未改变。
- 二级 resource 和 plan lease 只有在 expiry/current time 均存在且严格 `current_time < expiry` 时有效；等于边界按过期处理。缺字段分别输出可审计原因并 fail-closed，不能发布或维持 executable secondary plan。
- 七个规范单次试验时间轴（episode time）场景为 **7/7 通过**：正常中心、中心失效、中心后二级再次失效、缺 ACK、旧 epoch、过期 lease、分区。
- 在 0.25 秒逻辑时钟步下，中心故障到二级可执行所有者为 **1.25 秒**，二级故障到对等节点原子执行为 **1.00 秒**；对应验收上限为 1.5 秒和 2.5 秒。
- 主编排器/运行时又按 AirSim 单次试验时钟（episode clock）运行六类场景、每类 10 个随机种子（seed），共 **60 个试验用例（case）**：安全结果 **60/60**，误降级 0，重复所有者 0，脑裂防护失败 0。
- 30% 消息丢失下，7/10 因缺 ACK 保守闭锁，只有 3/10 在 ACK 完整后执行。这证明“缺确认不执行”，不是通信性能优良的证明。
- 更早的 D4 P1 合同层正负例中，二级协调者和完全分布式对等节点都以 3/3 ACK 进入 `executing`，确认窗口显式截止后的缺 ACK 场景以 2/3 进入 `aborted`（已中止）并保持复核；截止前普通快照保持 `collecting_acks`。
- 区域化合同验证为 23 个确定性单元 test case，无随机 seed；它关闭 D4 模块内 metadata/authority/安全门控。早期 main 质点接线定向回归为 8/8；2026-07-25 加入通信因果收据和异步三成员确认后，main-owned 模块栈为 66 passed、scalable 3D 全量为 272 passed。上述结果覆盖单二级、多二级 owner、distributed D3 plan、D7 fencing 和单随机种子三成员原子提交；仍不构成 AirSim、真实网络、硬件或长时 200 对 200 多随机种子证据。
- 区域资源学习的旧冻结 checkpoint 仍保留 14384 个动作无 quota/transfer/hold/replan 正样本这一历史限制。新版 development 候选已加入 clean supplemental 正类并在 calibration 桶覆盖四类动作，但 reward/causal/counterfactual 仍为 0，保留 1000-1019 尚未评估，因此 assist 资格仍不可用。
- 独立补充课程已提供四类规则 teacher 正样本，clean 数据及 canonical BC 只读 view 已可用，但仍没有 outcome/reward。它不能覆盖正式数据的状态分布，也不能把现有 development bundle 重新分类为可推荐策略。

这些结果验证的是单次试验时间轴上的顺序接管、版本/租约/ACK 门控和唯一所有者，不代表真实 RF、真实吞吐带宽、节点时钟漂移、网络设备或硬件故障已经验证。

### 9.2 已解决问题

1. **末端一致性误判**：`terminal_consistent` 已只表达计划绑定安全，不再把低置信度、歧义或重捕获重复解释为绑定错误；迟滞按资源/航迹对隔离。
2. **远距视觉误触发**：新增 `terminal_evidence_applicable`，未进入末端窗口时普通视觉软证据不再逐帧请求二级辅助。
3. **D2 风险语义混淆**：连续重复风险评分与显式重复事件分离；真值不可用时，IDSW/连续率占位值不触发硬风险。
4. **计划年龄误判**：优先使用最近评估时间，稳定计划标识不因创建较早而自动陈旧。
5. **重规划请求抖动**：四态请求生命周期和 2 秒冷却已实现；硬安全风险保持即时绕过。
6. **二级可见性过度外推**：已建立四级就绪性、综合评分和持续就绪窗口，单帧可见或单帧 `takeover_ready` 不接管。
7. **二级计划执行边界**：来源、版本单调、租约世代、租约到期和持续就绪已纳入待生效/已激活门控。
8. **多成员降级保底原子性**：完整 ACK、双版本、epoch、lease 和 digest 合同已实现；缺 ACK、旧世代、过期租约和分区保持闭锁。
9. **单次试验多随机种子安全矩阵**：六类、10 个随机种子、60 个试验用例的误降级、重复所有者和脑裂安全结果已闭合。
10. **区域 authority 合同**：动态 region/task/node metadata、声明数量上限、中心保持、二级 coverage 接管、跨区域 capacity candidate、双 generation、最早 lease 和全层原子 ACK/partition 门控已完成模块测试。
11. **区域资源建议安全边界**：资源守恒、邻边/分区、最低备用、formal owner/epoch/lease/fault/commit fence、模型回退和 shadow 不变性已完成模块测试；正式降级裁决仍归确定性 D4 状态机。
12. **下一周期 advisory 消费合同**：版本化内容 ID、严格有效期、逐区域/transfer 来源版本、安全证明、旧 generation/重放/ACK/fault/守恒/edge fail-closed 已完成模块测试；main/D3 实际消费尚未接线。
13. **区域学习 episode 数据合同**：truth-free source/frame、完整 episode、数值 seed 原子 split、多层 SHA、availability 和严格 BC/PPO loader 已完成模块测试；main 正式 episode writer 尚未接线。
14. **D4 共享切分消费端**：source-external registry 的 schema/policy/hash/source binding、100-seed 完整覆盖、保留集隔离和只读 BC 视图已完成；D3/D5 消费端和联合训练不由 D4 单独关闭。
15. **区域动作覆盖 producer**：独立课程在三个 canonical 桶中覆盖 hold、request-replan、quota 和 transfer，并保持投影、真值和保留 seed 门控；课程未生成 reward，不开放 PPO 或 assist。
16. **区域调度全样本准入**：正式数据和补充课程的 manifest、逐文件哈希、全部样本、规范 split、有限值和确定性安全合同已完成只读 fail-closed 审计；结果不把规则教师 target 或 projected recommendation 升格为运行 ACK。

### 9.3 剩余局限

- 真实 secondary takeover 和完全分布式 commit 尚未在与上述 M5N2 相同的多 seed 几何中执行，继续是 P1。
- `d4-region-resource-advisory-v1` 目前只有 D4 单元/接口证据；main 尚未在真实 planning loop 持久化 consumed ID 或将合同接入下一轮 D3，不能据此声称在线规划收益。
- `d4-region-learning-dataset-v1` 已形成 900 episode 正式训练集和 development checkpoint；但动作正样本、可归因转移、D6 reward/causal/counterfactual、外部 20-seed paired 结果仍缺失，不能据此声称已有可推荐策略。
- D4 全样本准入已完成，D6 尚未使用显式 JSON 路径和带外文件 SHA256 独立复核。真实 ACK、outcome、可归因 reward、被拒旧 generation 样本和同 seed paired shadow 没有进入当前 corpus，不能从 post-projection recommendation 推导。
- 20 个 `collision_stop` 缺少 collision object/source lineage，无法区分成员间碰撞、环境碰撞或 AirSim 状态异常；在证据补齐前不得把它设为主动降级硬触发。

1. **真实网络未验证**：带宽、拥塞、时钟漂移、操作系统/网络排队、抖动、乱序、重传、实际二级节点到执行资源链路和对等节点图分裂仍开放。
2. **恢复合并不完整**：当前基础合并没有覆盖完整航迹摘要校验值、计划摘要校验值、末端锁定、通信链路、联盟执行前缀和 D5/D7 门控。
3. **完整自主联盟形成未实现**：区域合同已有仅用于 distributed fallback 的能力与跨区域容量约束 candidate；中心和二级使用 D3 给定成员，三层 `k>1` 都执行完整 ACK 原子提交。当前仍没有 CBBA 网络图多轮共识、全局组合最优性、CCBBA 时序耦合或 D7 arrival feasibility；member-loss/replacement replay 仍由测试手工给定替换成员，只验证新 generation 全量 ACK，也不解决预留激活、缩编、补位和整盟重构。
4. **CBBA 是合成基线**：评分函数未与 D3 的真实中心代价完全对齐；真实单次试验尚未持续保存同场景中心代价矩阵并由 D6 做多随机种子差距聚合。
5. **D5 分布式视觉合流仍需标定**：模块内辅助函数已实现，但真实无中心多随机种子下的合流频率、风险权重和覆盖小区切换仍未闭合。
6. **物理闭环不能由 D4 合同结果替代**：2026-07-15 中心负对照的五资源对二目标（Five Resources to Two Targets，M5N2）20-case 聚合中，联盟完成率为 0/20、第二主资源进入 5 米为 0/20。较早的 5/10 结果属于不同批次历史证据，不覆盖本次同口径聚合。当前物理缺口不能归因于或由 D4 的 60/60 安全门控结果关闭。
7. **外部算法无性能结论**：MIT CBBA 与 CA-CBBA 当前只有能力不可用记录；未执行就不能比较优劣。
8. **学习建议仍无推广证据**：正式 BC 开发模型已生成，但 14384 个动作标签没有 quota/transfer/hold/replan 正样本，898/1798 帧状态转移无归因，reward/causal/counterfactual 可用数均为 0；外部 20-seed 和 AirSim/真实网络 paired evaluator 尚未完成。bundle admission 明确 `action_diversity_sufficient=false` 和 `strategy_capability_claim_allowed=false`，模型继续 development/shadow-only，低损失不能用于宣称调度策略能力。

## 10. 选型理由

### 10.1 为什么默认采用分层而非全时分布式

中心可用时，D3 拥有更完整的全局状态、版本和代价信息。全时运行分布式分配会引入所有权竞争、消息开销和版本分叉。因此 D4 把完全分布式限定为中心和二级都不可用后的连续性保底。

### 10.2 为什么二级节点需要覆盖与持续门控

二级节点可能“看见一部分目标”但不能在同一时间窗覆盖完整目标集合，也可能只有检测而没有稳定全局绑定。将可见性直接等同于接管会增加错误所有权和后续计划失效。四级就绪性与持续窗口使接管依据从单帧证据变成可审计的时空证据。

### 10.3 为什么使用轻量 CBBA

轻量 CBBA 无外部运行时依赖，能在任意输入规模上复现实验，显式输出轮数、冲突、消息和收敛状态，并保持每任务唯一所有者。它适合作为一对一无中心连续性基线，但不被外推为多成员联盟形成算法。

### 10.4 为什么原子提交独立于成员选择

“谁应该加入联盟”和“这组成员是否对同一版本达成可执行共识”是两个问题。单获胜者 CBBA 可用于选择协调者或候选，但只有 ACK/epoch/lease/digest 门控才能阻止部分成员执行、旧联盟复活和分区双主。因此当前实现把成员选择能力的开放项与已实现的原子提交安全合同分开。

### 10.5 为什么中心恢复需要双轨校验

心跳恢复只能证明中心重新发声，不能证明其航迹、分配和联盟状态最新。双轨校验和显式接受避免旧中心计划覆盖降级期间的新世代状态。

## 11. 证据与复核入口

当前模块使用 Python 编程语言的 pytest 测试框架。下列命令通过 Python 模块搜索路径环境变量 `PYTHONPATH` 指定 D4 包目录：

```bash
PYTHONPATH=research_modules/d4_distributed_fallback python3 -m pytest -q research_modules/d4_distributed_fallback/tests
```

本次新增区域化代码、测试和文档，并已重跑全量测试。主要源码证据：

- `models.py`：共享数据结构、中心健康、资源/航迹/通信/结果模型；
- `active_degradation.py`：风险规则、二级评分、动作仲裁、二级计划与 D7 交接门控；
- `adapter.py`：D1-D5/main 数据归一化、持续就绪性、中心重规划和联盟门控；
- `coordinator.py`：中心健康、协调负责人（leader）选择、被动保底和基础恢复合并；
- `cbba.py`：轻量 CBBA、视觉风险修正和离线代价差距；
- `coalition_safety.py`：多成员 ACK、原子提交与联盟安全证据；
- `regional_failover.py`：scalable3d 区域元数据、逐区域 authority、机动高空二级覆盖和受约束原子 fallback；
- `region_resource.py`：区域资源快照、规则基线、确定性安全投影、reward、数值 seed 原子划分与 paired evaluator；
- `region_resource_dataset.py`：episode source/frame、stage/finalize/load、数值 seed split、manifest/availability/hash；
- `canonical_seed_split.py`：共享 seed registry 严格校验、原 dataset/split/source 多级绑定和只读 canonical view；
- `region_resource_curriculum.py`：独立动作覆盖课程、三类确定性状态构造、canonical 绑定和安全/真值/reward 审计；
- `region_resource_full_sample_audit.py`：正式与补充数据的全 manifest、全 episode、全 frame/sample 只读准入、来源/哈希/规范切分和证据 availability 审计；
- `region_resource_learning.py`：共享区域图 actor-critic、严格 BC/PPO loader、bundle-v2/SHA/OOD 和 fail-closed advisor；
- `region_resource_cli.py`、`scripts/run_region_resource_advisor.py`：默认 shadow 的建议/paired evaluation CLI；
- `episode_communication.py`：单次试验时钟通信接口与七场景验收；
- `communication_fault_replay.py`、`p1_failover_replay.py`：P1 内存通信与确定性扰动回放；
- `p2_coalition_replay.py`：隔离式 P2 原生回放和外部能力探测。

## 12. 中文术语表

| 术语 | 中文解释 | 在 D4 中的严格含义 |
|---|---|---|
| C-UAS | 反无人机系统 | 本仓库的多模块研究流程，不表示实机自动处置系统 |
| C2 | 指挥与控制 | 中心协调权威及其健康状态 |
| CBBA | 一致性捆绑算法 | 当前为本地轻量、单获胜者、一对一无中心保底 |
| ACK | 确认 | 必要联盟成员对同一目标、计划、联盟版本和 epoch 的有效确认 |
| IDSW | 身份切换 | 只有上游明确指标可用时才作为在线硬风险 |
| NED | 北-东-地坐标系 | D1 融合工作坐标；D4 不做坐标变换 |
| RF | 无线频率 | 当前未做真实链路或硬件验证 |
| PNG | 视觉比例导航制导 | D7 的导引门控语义，不是 D4 输出的自动授权 |
| M-to-N | 多资源对多目标 | 资源数和目标数由输入决定；\(k_j>1\) 时需要联盟语义 |
| heartbeat | 心跳 | 节点存活和新鲜度证据，不足以单独证明计划权威最新 |
| digest | 摘要校验值 | 用于比较计划、联盟或恢复双轨状态的一致性 |
| epoch | 世代号 | 分区恢复、接管或成员重构时用于拒绝旧状态的单调代际标识 |
| lease | 租约 | 限定协调者、计划或联盟状态有效期的时间合同 |
| owner | 所有者 | 当前被 main/D3 认可的计划协调来源或降级保底协调者 |
| fail closed | 失效时闭锁 | 证据缺失、冲突、过期或不完整时不允许执行 |
| readiness | 就绪性 | 二级节点从未就绪、仅可见、注册可用到可接管的分级状态 |
| active degradation | 主动降级 | 中心仍可用时的保守仲裁，不转移计划所有权 |
| passive failover | 被动接管 | 中心明确失效后的二级或分布式接管 |
| terminal consistency | 末端绑定一致性 | 当前资源/全局航迹/版本/联盟绑定未被硬证据推翻，不等于视觉已锁定 |
| atomic coalition | 原子联盟 | 全部必要成员对同一版本完成有效 ACK，且租约和摘要一致 |
| replay | 回放 | 确定性或多随机种子的离线合同验证，不等于真实网络认证 |
| main/runtime | 主编排器/运行时 | 拥有 AirSim 单次试验、系统计划发布、日志收集和跨模块接线 |
| metadata | 元数据 | 随决策输出的版本、原因、状态迁移和评估审计字段 |
| hold for review | 保持并请求复核 | 身份、友方、联盟或版本安全条件不满足时的保守动作 |
