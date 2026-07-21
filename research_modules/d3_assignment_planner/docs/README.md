# D3 文档索引

D3 文档遵循 `research_modules/DOCUMENTATION_STANDARD.md`。推荐阅读顺序：

1. `../README.md`：模块用途、运行方式和目录入口。
2. `../PLAN.md`：集中式资源-目标分配研发计划。
3. `ALGORITHM_AND_IMPLEMENTATION.md`：Hungarian、最小费用流、代价函数、迟滞重分配、版本管理，以及面向 D4 主动降级的计划有效性信号。
4. `EXPERIMENT_REPORT.md`：离线仿真结果和图表说明。
5. `AIRSIM_INTEGRATION_PLAN.md`：AirSim 离线回放接入计划。
6. `../results/EXPERIMENT_REPORT_GENERATED.md`：脚本生成的实验报告快照。

本模块只生成候选分配计划和审计数据，不包含真实飞控、硬件、火控、毁伤或自动处置逻辑。

最新证据基线为 2026-07-15 的 M5N2 baseline/candidate 各 10 seeds、共 20 case。
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
不能全部归因 D3。`EXPERIMENT_REPORT.md` 记录完整对照，`PLAN.md` 与 GAP 记录正式
900 episode、训练和至少 20 个未见 seed 评估仍开放。
