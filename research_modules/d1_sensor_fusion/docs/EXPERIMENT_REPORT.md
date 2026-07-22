# 第一研究模块实验结果

## Clean 200v200 全栈接线复跑

**证据日期：2026-07-22**

**候选提交：`8f86192`**

**场景：200 个目标、200 个资源的三维质点全栈，仿真时长 10 s**

### 验收方法

clean 候选路径启用同一 fusion timestamp 延迟物化。扫描整理器释放的每个扫描仍按原顺序调用
D1；中间后验写入 state-only 发布，该 fusion timestamp 的最后后验写入完整 `GlobalTrack`
快照。对照路径为
旧 clean 提交 `3bac3ff`。两条路径使用相同 seed 和场景配置。

验收要求为：工作区 clean、状态有限、在线 truth 使用为 0、D1/D2 无 overflow、安全合同通过；
扫描总数必须等于 state-only 与完整快照数量之和；事件、scan input、共享摘要和世界真值必须与
旧路径对应 seed 相同。

### 结果

| Seed | 扫描数 | 匿名观测数 | State-only | 完整快照 | 旧 D1 fusion | 新 D1 fusion |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 42000 | 764 | 12,107 | 310 | 454 | 103.176 s | 89.796 s |
| 42001 | 844 | 11,922 | 328 | 516 | 106.447 s | 96.599 s |
| 42002 | 782 | 11,825 | 278 | 504 | 100.394 s | 92.578 s |
| 均值 | - | - | - | - | 103.339 s | 92.991 s |

3/3 episode 均为 clean、finite，在线 truth 使用 0，D1/D2 overflow 和安全合同全部通过。
D1 fusion 三 seed 均值下降 10.0%。seed 42000 的 2.2 s 全栈墙钟由 18.611 s 降至
18.302 s。每个 seed 的 state-only 与完整快照之和等于扫描总数；事件、scan input、共享摘要和
世界真值与旧提交 `3bac3ff` 对应 seed 相同。

### 结果解释

本次结果证明 main 已按 D1 接口完成延迟物化接线，并在三个 clean seed 上保持逐扫描融合和发布
语义。下降来自同一运行时刻中间 `GlobalTrack` 快照不再重复构造，不来自合并扫描、删除观测、
缩短固定时滞窗口或改变协方差和门控。

D1 fusion 对 10 s 输入仍平均耗时 92.991 s，实时预算没有闭合。本组是三维质点证据，不是
AirSim、真实传感器精度、RMSE、归一化估计误差平方、归一化创新平方或物理拦截验收。证据目录：

`../../scalable_3d_simulation/outputs/scalable_3d_long_duration_candidate_20260722_clean_8f86192/`

历史模块级性能、融合精度和时延消融实验见 `../reports/EXPERIMENT_REPORT.md`。
