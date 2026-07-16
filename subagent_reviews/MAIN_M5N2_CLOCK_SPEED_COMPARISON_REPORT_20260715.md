# M5N2 ClockSpeed 1.0/0.2/0.1 对比报告

## 1. 试验目的

本轮检验降低 AirSim `ClockSpeed` 是否能够改善 M5N2 协同拦截的数值稳定性和物理完成率。
除 ClockSpeed 外，三个批次保持相同的场景族、profile、seed 和控制参数。试验属于科研仿真，
不代表实机性能或处置能力。

![三档 ClockSpeed 对比曲线](../research_modules/airsim_runtime/outputs/m5n2_clock_speed_comparison_20260715/clock_speed_comparison_curves.png)

## 2. 场景与执行口径

| 项目 | 配置 |
|---|---|
| AirSim 模式 | Blocks `Multirotor`，拦截机使用 SimpleFlight |
| 规模 | 5 个拦截资源、2 个移动 actor 目标 |
| Profile | baseline；soft prediction + trend coast candidate |
| 随机种子 | 每个 profile 为 1-10，共 20 case/ClockSpeed |
| ClockSpeed | `1.0`、`0.2`、`0.1`，总计 60 case |
| 控制 | `dt=0.1 s`，速度 `6 m/s`，最大时长 `35 s`，NED 高度 `-30 m` |
| 物理成功 | 离线三维距离不大于 `5 m` |
| 相机 | 640x480、120 度视场；本轮未保存相机截图 |
| 目标运动 | Unreal actor 位姿运动，不使用 SimpleFlight |
| 在线安全边界 | AirSim truth identity/state 不进入 D1/D2/D5/D7 在线链路 |

main 启动一次 Blocks，并在 case 间 reset。D1-D7 通过现有 main episode bus 运行；D6 只读
落盘产物。D7 的 PN/视觉 PNG 公式、LOS 滤波和外推策略均未修改。

## 3. 严格结果

### 3.1 Baseline 物理完成率

| ClockSpeed | Active-primary pair | Target | Coalition | 第二 primary 进入 5 m |
|---:|---:|---:|---:|---:|
| `1.0` | `6/30`，20.0% | `6/20`，30.0% | `0/10` | `0/10` |
| `0.2` | `9/30`，30.0% | `9/20`，45.0% | `0/10` | `6/10` |
| `0.1` | `4/30`，13.3% | `4/20`，20.0% | `0/10` | `2/10` |

`0.2` 是本矩阵中 baseline 物理结果最好的设置。`0.1` 的最终锁定率达到 76.7%，第二
primary 最近距离均值降到约 5.32 m，但 pair/target 完成率反而低于 `1.0` 和 `0.2`。
这说明更慢的仿真没有自动形成更好的物理闭环。

### 3.2 时序

| ClockSpeed | Main bus mean | Control tick mean | 归一化 simulated time/tick |
|---:|---:|---:|---:|
| `1.0` | `343.8 ms` | `1070 ms` | `1.070 s` |
| `0.2` | `677.6 ms` | `2208 ms` | `0.4415 s` |
| `0.1` | `679.7 ms` | `3453 ms` | `0.3453 s` |

main bus 是 control tick 的嵌套内层，两者禁止相加。当前控制器按 active primary 顺序调用
`moveByVelocityZAsync(duration=0.1)` 并等待完成。降低 ClockSpeed 会延长每个 RPC 的墙钟等待，
所以名义 0.1 s 控制步并不是固定仿真时间步。`0.1` 的单步墙钟成本约为 `1.0` 的 3.2 倍。

### 3.3 Candidate 合同审计

D6 将每个 M5N2 case 的机会冻结为 3 个 active-primary、2 个 target、1 个 coalition。
60 个 case 中有 56 个匹配，4 个不匹配：

- `ClockSpeed=0.1`：candidate seed007、seed009；
- `ClockSpeed=0.2`：candidate seed006、seed009。

因此 0.1/0.2 candidate 的物理 aggregate 为 `unavailable`。该处理避免把 standby reserve
成功计入 active-primary，也避免使用 27/18 或 28/18 等缩小分母发布看似更高的成功率。
Candidate 只能作为失败定位证据，不能据此宣称相对 baseline 提升。

## 4. 原因分析

1. **ClockSpeed 与控制 RPC 耦合**：慢时钟不仅减慢物理世界，还延长顺序异步命令的完成等待，改变实际闭环采样间隔。
2. **锁定不等于拦截**：`0.1` 提高 final lock、降低最近距离，但控制时序、碰撞停止和剩余 primary 状态仍会阻断 5 m 完成。
3. **联盟仍未闭合**：三个 baseline 均为 `0/10` coalition；降低 ClockSpeed 没有解决第二 primary 的持续执行和联盟完成问题。
4. **Candidate 证据不完整**：部分 case 的 D3/D7 active-primary 机会数与 suite 结果不一致，正式比较必须 fail closed。

## 5. 结论

当前不建议把 `ClockSpeed=0.1` 作为默认仿真设置。对现有顺序 RPC 控制实现，`0.2` 在物理
完成率和慢速数值观察之间取得了更好的实测平衡，但墙钟代价约为 `1.0` 的两倍。若目标是调试
单帧视觉或观察轨迹，0.1 仍可作为诊断选项；若目标是批量闭环性能评估，优先保持 1.0，并在
完成固定仿真时钟/并行控制派发后重新比较 0.2。

下一步优先级：先修复 candidate `3/2/1` 机会合同和 case wall elapsed 记录，再将控制派发改为
不随资源数线性累加 RPC 等待的固定仿真时钟策略；之后用同一 20-case 矩阵复验。

## 6. 文件索引

- D6 中文报告：`research_modules/airsim_runtime/outputs/m5n2_clock_speed_comparison_20260715/CLOCK_SPEED_COMPARISON_REPORT_CN.md`
- 汇总 JSON：`research_modules/airsim_runtime/outputs/m5n2_clock_speed_comparison_20260715/clock_speed_comparison_summary.json`
- Case CSV：`research_modules/airsim_runtime/outputs/m5n2_clock_speed_comparison_20260715/clock_speed_comparison_cases.csv`
- 聚合 CSV：`research_modules/airsim_runtime/outputs/m5n2_clock_speed_comparison_20260715/clock_speed_comparison_aggregates.csv`
- 0.1 原始 suite：`research_modules/airsim_runtime/outputs/p1_clockspeed_0p1_m5n2_20case_20260715/`
- 0.2 原始 suite：`research_modules/airsim_runtime/outputs/p1_clockspeed_0p2_m5n2_20case_20260715_v2/`
- 1.0 原始 suite：`research_modules/airsim_runtime/outputs/p1_terminal_timing_funnel_10seed_20260715_m5n2/`

验证：AirSim runtime `157 passed`；D6 `272 passed`；60 个 case 在线 truth identity/state 使用均为 0。
