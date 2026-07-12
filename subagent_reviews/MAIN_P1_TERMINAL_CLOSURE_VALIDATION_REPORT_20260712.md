# P1 末端闭环与模块证据综合验证报告

## 1. 验证范围

本轮由 main 统一启动 AirSim Blocks，并按 settings 分为两个 reset-separated 批次：

- M5N2：5 个 SimpleFlight 拦截资源、2 个 actor 目标，高威胁目标采用 `2 primary + 1 reserve`，NED 高度 `-30 m`，最长 35 s，10 seeds。
- tuned 2v2：`png_ttc` 10 seeds，以及锁定后 1-5 帧 dropout 各 10 seeds。
- 成功判据：NED 三维距离 `<=5 m`。
- 检测：AirSim `simGetDetections`，在线 D5 不使用 actor/truth ID。
- 运行规模：80 个 episode，全部 connected；未保存 PNG 截图。

算法主线保持 NumPy/SciPy、GNN/Hungarian、版本化 AssignmentPlan、D4 原子联盟、D5 几何配准和现有 PN/PNG。位置 PN、`png_vm`、`png_ttc` 核心公式未修改。

![P1 综合验收概览](../research_modules/airsim_runtime/outputs/p1_terminal_closure_10seed_20260712/d6_unified_acceptance_full/p1_acceptance_overview.png)

## 2. AirSim 结果

| 场景 | Pair | Target | Coalition | 判定 |
| --- | ---: | ---: | ---: | --- |
| M5N2 baseline | 7/30 | 7/20 | 0/10 | 基线仍不能完成三机联盟 |
| M5N2 soft/trend candidate | 4/30 | 4/20 | 0/10 | 相对基线退化，不得晋级默认 |
| 2v2 `png_ttc` | 20/20 | 20/20 | N/A | 5 m 物理主链通过 |
| Dropout 1-5 帧 | 100/100 | 100/100 | N/A | 物理不退化；视觉生命周期逐 seed 49/50 |

Dropout 的大部分控制证据符合预期：1 帧组有 9/10 seeds 进入 image KF，2 帧组为 10/10；3-5 帧均为 10/10 在 0.25 s 后出现 `terminal_visual_prediction_window_expired`。seed 2 的单帧注入没有进入预测，需复核锁定与注入边界。80 个 episode 的 online truth use 均为 0。

`png_ttc` 共记录 120 个 contract-allowed、84 个 control-allowed sample 和 20 次进入视觉模式，出现 `area_not_expanding=13`、`ttc_out_of_range=22`。自然场景没有覆盖 area jump 和 bbox clipping，因此这两项仍需受控注入，不能写成算法失效。

## 3. D1-D6 模块证据

| 模块 | 结果 | 工程判读 |
| --- | --- | --- |
| D1 | 5 目标、1398 条异构观测，35 次 OOSM、10 次 relay duplicate，truth leak=0 | replay/schema/OOSM 链路闭合；RMSE/NEES 等待 D2 canonical-ID 映射 |
| D2 | 10 seeds，IDSW 均值 138.1，continuity 0.694，false track 5.4，RMSE 0.307 m | 校准入口有效，但默认 GNN 未通过 dense crossing 治理阈值 |
| D3 | 8/8 full/incremental 等价，1/8 局部增量，7/8 安全回退 | 正确性优先策略有效；增量收益有限 |
| D4 | 9/9 扰动矩阵通过，误降级 0，五个负例 fail-closed | ACK/epoch/lease/digest 和恢复合同闭合 |
| D5 | 10/10 确定性鲁棒性用例通过，reject 24，truth use=0，ID rewrite=0 | 重捕获、漂移和时间偏差保持保守；真实 YOLO/MOT 仍待标定 |
| D6 | main 与 D1-D5 证据全部 available，四层结果独立统计 | 统一离线报告入口闭合 |

## 4. 结论

当前无新增 P0 blocker。真实 `png_ttc` 多 seed、版本化模块 summary 和 D6 统一报告已经闭合；dropout 矩阵已完整执行，但保留单帧 seed 2 的 P1 时序尾部。

M5N2 协同物理拦截仍是最高优先级 P1：candidate 不仅没有改善，而且 pair/target 比 baseline 少 3 个成功；两个 profile 的 coalition completion 都为 0。下一轮应分层定位第二 primary 中段重捕、共同视觉窗口、D7 合同许可、到达扇区和成员间距，不能通过放宽身份、版本或友方门控换取成功率。

D2 dense crossing 是第二个明确 P1：高 IDSW 和低 continuity 已由 10-seed 数据确认。应继续标定 gate、生命周期和运动模型，再决定是否把 JPDA/IMM 等 optional benchmark 引入候选路径。

## 5. 文件索引

- Main summary：`research_modules/airsim_runtime/outputs/p1_terminal_closure_10seed_20260712/p1_terminal_closure_summary.json`
- Main 中文报告：`research_modules/airsim_runtime/outputs/p1_terminal_closure_10seed_20260712/P1_TERMINAL_CLOSURE_AIRSIM_REPORT.md`
- D6 中文报告：`research_modules/airsim_runtime/outputs/p1_terminal_closure_10seed_20260712/d6_unified_acceptance_full/P1_UNIFIED_ACCEPTANCE_REPORT.md`
- D6 aggregate：`research_modules/airsim_runtime/outputs/p1_terminal_closure_10seed_20260712/d6_unified_acceptance_full/p1_acceptance_aggregate.json`
- D6 per-seed CSV：`research_modules/airsim_runtime/outputs/p1_terminal_closure_10seed_20260712/d6_unified_acceptance_full/p1_acceptance_per_seed.csv`
- D1-D5 module evidence：`research_modules/airsim_runtime/outputs/p1_terminal_closure_10seed_20260712/module_evidence/`
