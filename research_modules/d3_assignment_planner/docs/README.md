# D3 文档索引

D3 文档遵循 `research_modules/DOCUMENTATION_STANDARD.md`。推荐阅读顺序：

1. `../README.md`：模块用途、运行方式和目录入口。
2. `../PLAN.md`：集中式资源-目标分配研发计划。
3. `ALGORITHM_AND_IMPLEMENTATION.md`：Hungarian、最小费用流、代价函数、迟滞重分配、版本管理，以及面向 D4 主动降级的计划有效性信号。
4. `EXPERIMENT_REPORT.md`：离线仿真结果和图表说明。
5. `AIRSIM_INTEGRATION_PLAN.md`：AirSim 离线回放接入计划。
6. `../results/EXPERIMENT_REPORT_GENERATED.md`：脚本生成的实验报告快照。

本模块只生成候选分配计划和审计数据，不包含真实飞控、硬件、火控、毁伤或自动处置逻辑。

2026-07-26，D3 的 20-seed 隔离批量重放合同完成正式 clean evaluator 复核。冻结输入来自
提交 `0ed7ca2730f5354be1e6021f9882f1ae26bc42df`，正式评估代码提交为
`bdb665eb8e63a17f5f15dbf3fe472af10e5e5b5c`。固定 seed `1000-1019`，每 seed 5 帧，
共 100 帧；80 帧应用学习代价，20 帧分布外回退，逐 seed binding change、硬违规和
`global_track_id` 改写均为 0。输入和输出校验清单全部通过。该结果只关闭隔离重放合同；
`eligible_seed_count=0`，D7 checkpoint、A1 准入、默认路径和生产权限仍未形成。

2026-07-26，D3 完成 A1 学习证据装配复核。production writer 不再接受调用方提供的
qualified admission，production loader 也不接受手工正向布尔和占位 SHA 自我晋级。
现有 development bundle 的 shadow 行为不变；正式 assist 等待 D6 实物审计和 D3
模块专用 evidence assembler。定向测试 `21 passed`，全量为
`465 passed, 1 skipped`。

2026-07-25，clean commit `32b3b40` 的正式 R0
`high_threat_m_to_n` 200v200、seed 1000、2.0 秒单元暴露滚动需求库存 P0。
当前 D3 已在旧计划可行性评分中加入需求合同前置检查，并完成同配置开发复验。
需求升降、同需求迟滞、过分配失败关闭和 200 输入规模回归均已加入；D3 全量为
`464 passed, 1 skipped`。该修复尚未在新 clean commit 下完成 formal 分片重跑，
所以文档将其标为“实现并测试，正式 R0 证据待补”。

当前状态基线为 2026-07-25。新增固定保留种子多周期影子评估，覆盖 1000-1019 共
20 个种子、6 类场景和 620 个规划周期。580 个周期实际改变有效代价矩阵，120 个周期
形成不同绑定；重复资源、硬约束或谱系违规、旧版本采用和在线真值使用均为 0。该证据
只关闭行为克隆残差的多周期可辨识性缺口，模型仍是 `development/shadow-only`，没有
运行确认、物理结果、因果奖励或线上准入。D3 全量收集 460 项，结果为
`459 passed, 1 skipped`，唯一跳过为可选 OR-Tools。
逐 seed 和逐周期 CSV 已固定为 LF 行结束符；该格式修复没有改变证据数值。

AirSim 物理证据基线仍是 2026-07-15 的 M5N2 baseline/candidate 各 10 seeds、共 20 case。
`EXPERIMENT_REPORT.md` 记录物理结果与 D3 history 聚合，`AIRSIM_INTEGRATION_PLAN.md`
记录写盘可用性和后续接线，`PLAN.md` 记录剩余 P1。额外的
`png_ttc_2v2_seed001` 不属于该 M5N2 聚合，未运行 case 不补零。

2026-07-20 新增的 D3 独立证据包括 200×200、top-32、重复 5 次的向量化性能基准，
以及多 secondary owner、single-member authority 和 atomic coalition commit 区域
计划合同单测。该批全量结果为 `193 passed, 1 skipped`。这些结果没有重跑 AirSim；
区域裁决仍待 main/D4 接线，不得替代上述 M5N2 运行证据或写成全栈闭环完成。

同日新增故障代际 fence 接口及 5 个专项测试，最新 D3 全量为
`198 passed, 1 skipped`。该接口只完成 D3 发布代际隔离，50v50 中心故障的 main/D4
接线和系统结果仍待验证。

同日最新增量为单帧只读规划证据与公开 learning-frame helper。接口把实际规划使用的
rule/effective/shadow/fallback 矩阵、版本和匿名输入快照留在 planner 本地，拒绝路径不
复用旧帧。新增 11 个专项测试后共收集 226 项，结果为 `225 passed, 1 skipped`。
`ALGORITHM_AND_IMPLEMENTATION.md` 记录 schema/捕获点，`AIRSIM_INTEGRATION_PLAN.md`
记录 main 接线要求，`EXPERIMENT_REPORT.md` 记录模块验收。本批未运行 AirSim 或生成
真实 seed 数据。

同日新增上一轮 D4 区域资源建议到下一轮 D3 candidate graph 的可选合同。最新模块
全量收集 240 项，结果为 `239 passed, 1 skipped`；14 个新增 case 仅为确定性 fixture。
算法、审计字段和 fail-safe 回退见 `ALGORITHM_AND_IMPLEMENTATION.md`，main 时序与 D6
验收条件见 `AIRSIM_INTEGRATION_PLAN.md`，测试边界见 `EXPERIMENT_REPORT.md`。该状态不
代表 D4-main-D3 已接线，也没有新增 AirSim 或正式多 seed 性能证据。

同日学习数据合同升级为 numeric-seed-atomic v2：同一数值 seed 跨 scenario、规模和
episode 原子切分，dataset/bundle/shadow schema 同步升级并稳定拒绝 v1。D3 writer 已支持
逐行 iterator、磁盘暂存和完整 frame SHA；当前 scalable main 已移除 batch finalize 的
全量 `read_text().splitlines()`。最新 D3 全量收集 244 项，结果为
`243 passed, 1 skipped`。该结果仅证明软件合同，不含新训练、AirSim 或模型性能结论。

同日 D3 owner 完成 learning 安全复核补正：训练 API 明确拒绝 test frame，frame v2
递归拒绝未知 truth/actor/identity 字段，candidate mask 始终与 hard reject 求交，bundle/
promotion 同时绑定 split、完整 frame 内容和 model-state 三摘要，paired shadow 在统一
`rule_cost_matrix_v1` 上重评分。最新全量收集 252 项，结果为
`251 passed, 1 skipped`。详见 `ALGORITHM_AND_IMPLEMENTATION.md` 的共同评分与证据合同、
`EXPERIMENT_REPORT.md` 的负例结果以及 `AIRSIM_INTEGRATION_PLAN.md` 的运行时边界。本批
仍无正式权重、eligible promotion、AirSim episode 或模型收益结论。

同日 D3 对 200×200 learning export 做模块内性能复核。frame builder 缓存 target demand，
JSONL identity 检查改为迭代容器扫描，dataset writer 使用单次 canonical 编码、磁盘
payload sidecar 和 SQLite key/offset 索引。top-32 六帧 finalization 中位数由 0.910 s
降至 0.244 s，输出字节、schema 和 hash 不变。最新全量收集 255 项，结果为
`254 passed, 1 skipped`。详细数据见 `EXPERIMENT_REPORT.md`；该结果没有运行 AirSim，
也不能解释 D3/D4/D5 组合 staging 的全部耗时。

main 随后完成 clean-tree nominal 200v200 三 seed 集成复测。优化后 D3 stage 为
0.0917/0.1129/0.0999 s，6 帧正常最终化且在线真值使用为 0；总生成由 467.8007 s 降至
262.2866 s。联合 finalization 由 116.5624 s 降至 7.7377 s，但该字段汇总 D3/D4/D5，
不能全部归因 D3。`EXPERIMENT_REPORT.md` 记录完整对照。

2026-07-20 的正式数据与行为克隆开发训练现已完成。正式数据包含 900 episode、1604 帧，
100 个数值 seed 按 60/20/20 原子切分，外部保留 seed 1000-1019 未进入数据集。开发
bundle 使用 `d3_learning_model_bundle_v3`，状态固定为 `development/shadow-only`；内部
test 只作开发诊断，不是最终准入证据。行为克隆训练、分档时延和 rule-only/BC shadow
对照见 `EXPERIMENT_REPORT.md`。在该训练报告生成时，assist promotion、外部 20-seed
验收、AirSim 收益和 PPO 均未完成。后续单帧同输入比较、多周期可辨识性评估和正式
20-seed 隔离重放已补充外部保留种子证据；运行采用、物理非退化、因果收益、assist
promotion 和 PPO 仍未完成。

2026-07-21 增加 C1 detached shared seed registry 只读绑定。算法和哈希链见
`ALGORITHM_AND_IMPLEMENTATION.md` 第 36 节，正式 900-episode 映射验证见
`EXPERIMENT_REPORT.md` 第 17 节。该工作只关闭 D3 切分歧义，现有 BC 仍为
`development/shadow-only`。

2026-07-22，D6 profile-bound v2 availability sidecar 已独立消费 D3 正式保留-seed
产物，并把同帧离线分配比较标为 available。该状态关闭 D3 assignment 层可用性和独立
消费缺口；runtime ACK、物理结果、paired non-degradation、反事实、因果和 production
promotion 仍不可用。证据目录、双哈希和逐项结果见 `EXPERIMENT_REPORT.md`，实现口径见
`ALGORITHM_AND_IMPLEMENTATION.md` 第 44 节。

2026-07-22 新增隔离计划消费合同。接口使用独立 schema 确认 control/treatment 克隆世界
消费了指定 plan，并固定声明其不是 production runtime ACK。重复、旧版本、错 arm、错
source snapshot、错 receipt 和 payload 篡改均失败关闭。专项 `8 passed`，D3 全量
`380 passed, 1 skipped`。算法见第 45 节，软件合同试验见 `EXPERIMENT_REPORT.md`；本次
没有启动 AirSim 或生成物理结果。

2026-07-22 在线故障代际目标库存已同步。中心、增量和区域授权路径现以当前规划帧形成
版本化完整库存；故障 fence 可在匹配规划上下文存在时保留旧绑定并登记新增未分配目标。
算法见 `ALGORITHM_AND_IMPLEMENTATION.md` 第 47 节，原则见
`MODULE_PRINCIPLES_CN.md`，5v5、seed 1011/1019 的三维质点结果见
`EXPERIMENT_REPORT.md`。D3 全量为 `385 passed, 1 skipped`；本轮没有 AirSim 证据。

2026-07-22 故障代际离线 replay 已同步。authority frame 现先按 previous owner 重建规划
候选，再调用在线相同的二级接管/延续 helper；control 精确匹配和严格 payload 校验未放宽。
算法见 `ALGORITHM_AND_IMPLEMENTATION.md` 第 48 节，20-seed `center_failure` 结果见
`EXPERIMENT_REPORT.md`。D3 全量为 `386 passed, 1 skipped`；本轮仍无 AirSim 或生产 ACK。

2026-07-22 区域授权待分配库存已同步。D4 grant 可以只覆盖上一计划中的可执行绑定目标；
未覆盖目标必须由前序计划严格证明为零绑定、未分配且不完整。D3 保留其需求短缺，但不生成
区域 owner、commit 或执行许可。算法见 `ALGORITHM_AND_IMPLEMENTATION.md` 第 49 节，
原则和两 seed 三维质点结果分别见 `MODULE_PRINCIPLES_CN.md` 与 `EXPERIMENT_REPORT.md`。
D3 全量为 `390 passed, 1 skipped`；本轮仍无 AirSim 或生产 ACK。

2026-07-22 非生产隔离执行计划合同已升级为双源规划帧绑定。规划帧 `previous_plan` 作为
离线求解源，`plan` 作为正式权威；输出采用 `formal_authority.version + 1`，并保存完整帧、
两个源计划、候选和执行计划摘要。算法见 `ALGORITHM_AND_IMPLEMENTATION.md` 第 50 节，原则
见 `MODULE_PRINCIPLES_CN.md`，专项结果见 `EXPERIMENT_REPORT.md`。专项为 `18 passed`，D3
全量为 `408 passed, 1 skipped`；普通 5v5 与中心失效各完成 20 seed、40 arm 离线扫描。
AirSim 接入边界已检查，本轮未运行 AirSim，也未生成生产 ACK、D4 adoption 或物理结果。

2026-07-22，`secondary_failure` 区域权威离线重放已闭合。记录帧新增前序计划与区域计划的
转换摘要；离线执行通过记录 assignment 重建区域授权，并复用线上区域规划校验。算法见
`ALGORITHM_AND_IMPLEMENTATION.md` 第 51 节，原则见 `MODULE_PRINCIPLES_CN.md`，真实 20-seed
结果见 `EXPERIMENT_REPORT.md`，AirSim 边界见 `AIRSIM_INTEGRATION_PLAN.md`。离线干预专项
`23 passed`，D3 全量 `419 passed, 1 skipped`。本轮未运行 AirSim 或生产 ACK。

2026-07-27，D3 完成 A2 非零区域干预严格后继复核。`hold` 现冻结来源计划中仍硬安全的
区域绑定；失效来源边以 `regional_hint_held_assignment_infeasible` 失败关闭。
`request_replan` 单独且执行签名不变时不升版。三区域模块夹具验证守恒跨区转移、无承诺
区域保持和完整 successor 权属谱系。区域提示专项 `25 passed`，D3 全量
`551 passed, 1 skipped`（552 项）。算法见 `ALGORITHM_AND_IMPLEMENTATION.md` 第 66 节，
原则见 `MODULE_PRINCIPLES_CN.md`。本轮未运行 AirSim，未产生运行确认或物理结果。
