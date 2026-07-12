# D7 PNG Delivery 增强与真实 AirSim 验证报告

日期：2026-07-12

## 1. 工作范围

本轮在不修改位置 PN、`png_vm`、`png_ttc` 核心导引公式的前提下，补充 `png_guidance_delivery` 中已经验证过的量测治理和短时外推机制：

- D5 输出 local-track 生命周期、双时间戳、bbox 裁剪和相机几何有效性。
- D7 按资源、global/local track、计划 owner/version 隔离图像 KF。
- `png_ttc` 增加面积 EMA、窗口斜率、面积跳变、边缘裁剪和 TTC 范围检查。
- soft innovation prediction 与水平 LOS trend coast 作为显式 candidate profile，默认关闭。
- 6D LOS KF 只用于离线 replay，不进入 SimpleFlight 默认控制。
- D6 分离合同许可、控制许可、模式切换和 5 米物理拦截。

在线链路不使用 AirSim actor/object truth ID；truth 只用于离线 5 米距离评分。所有运行均未保存相机截图。

## 2. 实现参数

| 参数 | 设置 |
| --- | ---: |
| 图像 KF 最大预测时间 | 0.25 s |
| soft innovation prediction | 默认关闭，专项 profile 开启 |
| LOS trend coast | 默认关闭，专项 profile 开启 |
| trend 水平速度上限 | 0.75 m/s |
| TTC 面积 EMA | 0.25 |
| TTC 面积窗口 | 5 帧 |
| 最小 bbox 面积 | 16 px² |
| 最大面积跳变比 | 2.5 |
| 最大有效 TTC | 20 s |
| AirSim 控制 | SimpleFlight 速度命令 |
| 物理成功判据 | NED 三维距离不大于 5 m |

candidate 能力仍服从 D3 计划版本、D4 action、D5 locked、友方冲突和重复锁定门控。局部节点不能修改 `global_track_id`。

## 3. 测试结果

### 3.1 模块与集成回归

| 测试 | 结果 |
| --- | ---: |
| D4 | 148 passed |
| D5 | 161 passed |
| D6 | 84 passed |
| D7 | 137 passed |
| AirSim runtime | 98 passed |
| integrated point-mass | 7 passed |
| AirSim dry-run contracts | 4 passed |
| cross-module contracts | 3 passed |

`git diff --check` 通过。Matplotlib `Axes3D` warning 为本机多版本环境问题，不影响控制和指标计算。

### 3.2 2v2 十个 seeds

场景使用 AirSim detect、SimpleFlight、5 米成功判据和 candidate profile。10 个 seed 共 20 个拦截 pair。

| 指标 | 旧基线 | 本轮 candidate |
| --- | ---: | ---: |
| Pair 物理成功 | 19/20 | 20/20 |
| 目标级成功 | 19/20 | 20/20 |
| Timeout | 1 | 0 |
| 在线 truth 使用 | 0 | 0 |
| 平均最小距离 | 未重算 | 4.844 m |
| 自然 soft prediction | unavailable | 0 |
| 自然 trend coast | unavailable | 0 |

本轮结果满足“不低于 19/20”的非退化门槛。由于自然运行没有触发 soft prediction 或 trend coast，20/20 只能证明 candidate profile 没有破坏 2v2 主链，不能证明成功率提升由新增外推导致。

在四层日志字段补齐后，额外运行 seed 12 logging smoke：`contract_allowed=4/36`、`control_allowed=2/36`、`mode_switched=5`、`physical_intercept=2/2`。这证明 D6 已能分别消费合同、控制、模式和物理结果；早期 10-seed 文件缺少这些新列时继续显示 NA，不做零值回填。

轨迹示例：

![2v2 seed 1 三维轨迹](png_delivery_candidate_2v2_20260712_seed001/episode_006_full_flow/airsim_3d_intercept_trajectories.png)

### 3.3 锁定后两帧检测丢失

故障窗口设为 1.5-1.7 s，此时 INT-02 已建立视觉测量和终端锁定。

| 时间 | D7 状态 | 结果 |
| --- | --- | --- |
| 1.5 s | `predicted / image_kf_detection_loss_predict` | 保持有界预测 |
| 1.6 s | `predicted / image_kf_detection_loss_predict` | 保持有界预测 |
| episode | 2/2 range intercept | 在线 truth=0 |

该结果证明漏检不会被误判为 local-track 切换；预测只在原 global/local track 和原计划上下文内延续。

### 3.4 M5N2 短窗口压力测试

本轮运行 5 个资源、2 个目标、hybrid `2 primary + 1 reserve`，3 seeds，8 s 控制窗口。

| 指标 | 结果 |
| --- | ---: |
| Active pair | 9 |
| 5 米成功 | 0/9 |
| 最近距离范围 | 22-32 m |
| soft prediction | 4 次 |
| innovation hard reject | 2 次 |
| terminal switch allowed | 0 |
| reserve 越权 | 0 |
| 在线 truth 使用 | 0 |

该批次不能与既有 z=-30 m、35 s 高净空基线比较。当前 8 s 时各 active primary 尚未接近末端，部分 pair 因 `terminal_detection_acquisition_timeout` 中止；结果反映的是中段闭合时间和场景几何不足，不是 TTC/KF 末端滤波退化。原高净空基线仍为目标级 6/6、active-primary 6/9、双 primary 联盟完成 0/3。

## 4. 结论

1. 图像 KF 生命周期、TTC 面积治理、审计字段和 D5 相机几何合同已经实现并通过回归。
2. 2v2 candidate 达到 20/20，满足主线非退化要求；库默认仍保持 soft prediction 和 trend coast 关闭。
3. 锁定后 2 帧 dropout 已验证 0.25 s 内的有界图像 KF 预测，且没有 truth ID 或本地 ID 重写。
4. trend coast 尚未在本轮真实运行中被触发，不具备进入默认 profile 的实验依据。
5. `png_ttc` 面积预处理已完成代码和 replay 测试，但本轮真实主场景使用 `png_vm`，仍需独立 `png_ttc` 多 seed。
6. M5N2 仍受第二 primary 中段闭合、D5 hold/reacquire 和联盟视觉一致性约束，不能依靠末端滤波单独解决。

## 5. 后续验收

- 使用同一 z=-30 m、35 s 高净空几何运行 baseline/candidate paired M5N2，分别统计 target、active-primary 和 coalition completion。
- 对 1-5 帧锁定后 dropout 做固定时刻矩阵；3-5 帧必须按 0.25 s 上限 fail-closed。
- 单独运行 `png_ttc` 多 seed，统计面积跳变、裁剪、非扩张和 TTC 超范围拒绝。
- trend coast 只有在错误绑定为 0、命令跳变不恶化且物理成功不下降时，才允许进入 AirSim 默认 profile。

## 6. 证据索引

- D6 对照报告：`png_delivery_enhancement_eval_20260712/terminal_delivery_comparison_report.md`
- D6 结构化汇总：`png_delivery_enhancement_eval_20260712/terminal_delivery_summary.json`
- 2v2 10 seeds：`png_delivery_candidate_2v2_20260712_seed001` 至 `seed010`
- 锁定后 dropout：`png_delivery_candidate_postlock_dropout_2v2_20260712`
- 四层日志 smoke：`png_delivery_logging_smoke_2v2_20260712`
- M5N2 短窗口：`png_delivery_candidate_m5n2_short_20260712_seed001` 至 `seed003`
- 既有可比基线：`P1_REAL_AIRSIM_2V2_M5N2_MULTI_SEED_P2_DECISION_REPORT_20260712.md`
