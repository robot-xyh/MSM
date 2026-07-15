# P0 Actual-Execution 真实 AirSim 验收报告

## 1. 验收目的

本轮只验证 SimpleFlight 控制结束后的规范执行证据链，不修改 D1-D7 算法，也不调整
PN、`png_vm` 或 `png_ttc` 核心公式。需要确认：

1. 离线 NED 三维 5 m scorer 与 `control_commands.csv`、`intercept_summary.json` 的
   物理成功计数一致；
2. `d7-actual-execution-metrics-v2` 能从最终写盘源构建并通过 D6 校验；
3. 控制命令和 canonical D3 history 来自同一个 live episode bus；
4. 在线控制不使用 AirSim actor 身份或运动真值；
5. 独立 direct run 使用唯一 sequence 标识，不因共同的 `episode_006_full_flow` 发生
   case 冲突。

## 2. 场景与输出

| 场景 | 规模 | 导引 | 时长 | 高度 | 规范输出 |
|---|---:|---|---:|---:|---|
| tuned 2v2 seed-1 | 2 资源/2 目标 | `png_ttc`，中段仍为雷达 PN | 8 s | -5 m NED | `p0_actual_v2_2v2_seed001_20260714/` |
| M5N2 seed-1 | 5 资源/2 目标，T001 为 2 primary + 1 reserve | `png_vm`，中段仍为雷达 PN | 35 s | -30 m NED | `p0_actual_v2_m5n2_seed001_20260714/` |

两次运行都使用 AirSim detect，不保存相机 PNG。入侵目标为 actor，无 SimpleFlight
动力学；拦截资源使用 SimpleFlight。

## 3. P0 证据结果

| 检查项 | tuned 2v2 | M5N2 | 判定 |
|---|---:|---:|---|
| actual v2 available | 1/1 | 1/1 | 通过 |
| unavailable artifact | 0 | 0 | 通过 |
| summary/CSV/actual 物理成功数 | 2/2/2 | 2/2/2 | 一致 |
| command/actual/history plan ID | 一致 | 一致 | 通过 |
| identity online truth use | 0 | 0 | 通过 |
| state online truth use | 0 | 0 | 通过 |
| D6 actual case availability | available | available | 2/2 通过 |

旧的 `d7_actual_execution_command_physical_count_conflict` 未复现。main 已将每个离线
确认成功的 active pair 精确标记到一条最终 command row，并让 orchestrator finalize 控制时
使用的同一个 `MainAirSimEpisodeBus`。direct run 的标识优先级固定为
`case_id > sequence_id > episode_id`。

## 4. 物理与性能结果

### 4.1 tuned 2v2

- pair/target 成功：`2/2`、`2/2`；
- 两个 pair 最小三维距离约 `4.98 m`、`4.89 m`；
- 拦截时间均约 `2.7 s`；
- loop latency 约 `123.3 ms`，性能预算违例 `19`。

### 4.2 M5N2

- active pair 成功：`2/3`；
- target 成功：`2/2`；
- 高威胁 T001 的一个 primary 成功，第二 primary 最近约 `11.02 m`；
- standby reserve 未越权执行；
- coalition completion：`0/1`，该值为 available 的显式失败，不是缺证据；
- loop latency 约 `384.6 ms`，性能预算违例 `212`。

目标级 `2/2` 只说明两个目标都至少被一个资源进入 5 m，不能替代高威胁目标的
required-primary 联盟完成结果。

## 5. D6 判读

统一 D6 报告位于：

`research_modules/airsim_runtime/outputs/p0_actual_v2_validation_20260714/d6_acceptance/P1_UNIFIED_ACCEPTANCE_REPORT.md`

![Actual execution 验收概览](../research_modules/airsim_runtime/outputs/p0_actual_v2_validation_20260714/d6_acceptance/p1_acceptance_overview.png)

报告中 `actual_execution_all_available=true`，说明本轮 P0 证据门通过；
`overall_acceptance_passed=false` 是正确结果，因为本批没有运行 baseline/candidate 成对
比较、1-5 帧 dropout 全矩阵和多 seed，不构成完整 P1 terminal-closure suite。

## 6. 结论与开放 P1

canonical actual-execution 的运行级和证据级 P0 已关闭。开放 P1 为：

1. 同配置 2v2、M5N2、dropout、`png_ttc` 多 seed 重跑；
2. M5N2 第二 primary 的获取、机动和 5 m 物理闭环；
3. D3 feedback churn 与 M5N2 计划稳定性；
4. 2v2/M5N2 超过 100 ms 控制周期的延迟拆分；
5. D5 30/50 m detect/YOLO/MOT 召回与准入；
6. D4 二级/完全分布式真实网络时序与多 seed 复验。
7. actual v2 独立五层和 freshness/stale 注册已经关闭；后续只需按相同 schema 做多 seed 聚合、异常 stale 工况和长期趋势治理，不得用 `control_allowed` 或缺失值回填。

本报告只适用于科研仿真，不构成实机控制或处置能力证明。
