# P1 AirSim 专项测试报告

生成日期：2026-07-03  
测试范围：D7/D5 末端接管专项、D4/D5 5v5 二级侦察 200m 高差专项、D6 执行后指标回灌、批量 seed 编排 smoke。

## 1. 总结

本轮完成了两项核心 AirSim 专项验证：

- D7/D5 2v2 terminal-handoff tuned 已达标：`terminal_switch_allowed_rate` 从首次测试的 `0.00` 提升到 `0.75`，且 2/2 完成 `collision_intercept`。
- D4/D5 5v5 200m 高差 stress 已达标：二级侦察镜头相对目标高差 `200.0m`，二级全局视野率 `1.00`，三类 D4 降级动作符合预期。

同时暴露并修复了两个工程问题：

- D7 末端门控使用 AirSim 当前速度估计时受 SimpleFlight 状态滞后影响，误判 `not_closing`。已改为用下一步 PN 命令速度估计 terminal gate 的 closing-speed，并在 `look_at_target` 模式下用目标方位作为相机朝向基准。
- 200m stress settings 的二级相机覆写 `CaptureSettings` 时缺少 `X/Y/Z/Pitch/Roll/Yaw`，导致 Blocks 解析出 NaN transform 并崩溃。已补齐相机局部位姿字段。

仍未完全解决的问题：

- `--batch-seeds` 采用“每个 seed 单独启动 Blocks”的方式时，seed 切换后 AirSim RPC 端口 `41451` 可能超过 60 秒仍保持 open，导致下一轮启动失败。当前已把错误改为显式报错，但真正稳定的批量方案应改成“单个 Blocks 进程内循环 seed/episode 并 reset 场景”，或在外部进程层做更强清理。

## 2. 本地回归

执行：

```bash
python3 research_modules/run_all_tests.py
```

结果：全部 research module 测试通过。唯一警告仍是 Matplotlib `Axes3D` 环境 warning，不影响本轮 AirSim 运行。

## 3. D7/D5 2v2 末端接管专项

### 3.1 首次测试：发现问题

输出目录：`research_modules/airsim_runtime/outputs/p1_terminal_handoff_tuned_001/`

关键结果：

| 指标 | 数值 |
| --- | ---: |
| `intercept_success_count` | 2 |
| `collision_intercept_count` | 2 |
| `terminal_switch_allowed_rate` | 0.00 |
| `camera_quality_gate_pass_rate` | 0.802 |
| `los_quality_gate_pass_rate` | 0.713 |
| `maneuver_margin_gate_pass_rate` | 0.020 |

主要拒绝原因：

| Reject reason | Count |
| --- | ---: |
| `not_closing` | 68 |
| `bbox_near_image_edge` | 12 |
| `los_rate_variance_high` | 10 |
| `maneuver_margin_low` | 7 |
| `stable_frame_count_low` | 2 |
| `los_rate_window_too_short` | 2 |

结论：虽然实际拦截成功，但视觉末端接管没有真正放行。主要原因是 terminal gate 使用 AirSim 当前速度估计，SimpleFlight 速度状态滞后导致 closing-speed 判定过于保守。

### 3.2 修正后复测：达标

输出目录：`research_modules/airsim_runtime/outputs/p1_terminal_handoff_tuned_002/`

运行要点：

- 2v2 SimpleFlight。
- 目标 actor：`MSM_TargetActor_1/2`。
- 默认 asset：`1M_Cube_Chamfer`。
- tuned settings：相机 FOV `120deg`。
- `intercept_yaw_mode=look_at_target`。
- 目标 scale：`2.0`。
- 不保存 AirSim 截图。

关键结果：

| 指标 | 数值 |
| --- | ---: |
| `intercept_success_count` | 2 |
| `collision_intercept_count` | 2 |
| `terminal_switch_allowed_rate` | 0.75 |
| `terminal_switch_reject_count` | 15 |
| `time_to_intercept_s` | 2.50 |
| `min_range_m` | 1.982 |
| `camera_quality_gate_pass_rate` | 0.865 |
| `los_quality_gate_pass_rate` | 0.885 |
| `maneuver_margin_gate_pass_rate` | 0.750 |

控制记录统计：

| 项目 | 结果 |
| --- | --- |
| 控制记录数 | 52 |
| `terminal_switch_allowed=True` | 39 |
| `terminal_switch_allowed=False` | 13 |
| `guidance_law=png_vm` | 50 |
| `guidance_law=los` | 2 |

剩余拒绝原因：

| Reject reason | Count |
| --- | ---: |
| `maneuver_margin_low` | 6 |
| `bbox_near_image_edge` | 5 |
| `stable_frame_count_low` | 2 |
| `los_rate_window_too_short` | 2 |

单机结果：

| Resource | Target | Status | Terminal locked | Time to intercept | Min range |
| --- | --- | --- | --- | ---: | ---: |
| INT-01 / Interceptor1 | TGT-001 | `collision_intercept` | true | 2.4s | 2.039m |
| INT-02 / Interceptor2 | TGT-002 | `collision_intercept` | true | 2.6s | 1.982m |

证据文件：

- `p1_terminal_handoff_tuned_002/episode_006_full_flow/intercept_summary.json`
- `p1_terminal_handoff_tuned_002/episode_006_full_flow/control_commands.csv`
- `p1_terminal_handoff_tuned_002/episode_006_full_flow/integrated_replay/d7_execution_metrics.json`
- `p1_terminal_handoff_tuned_002/episode_006_full_flow/integrated_replay/metrics.json`
- `p1_terminal_handoff_tuned_002/episode_006_full_flow/airsim_3d_intercept_trajectories.png`

![2v2 tuned trajectory](p1_terminal_handoff_tuned_002/episode_006_full_flow/airsim_3d_intercept_trajectories.png)

## 4. D4/D5 5v5 二级侦察 200m 高差专项

### 4.1 首次测试：settings 崩溃

输出目录：`research_modules/airsim_runtime/outputs/p1_d4d5_200m_001/`

首次启动 Blocks 失败，return code `139`。日志中出现：

```text
SpawnActor failed because the given transform (nan,nan,nan|...) is invalid
Unhandled Exception: SIGSEGV
```

原因：二级相机在 settings 中覆写 `Cameras.0.CaptureSettings`，但未显式提供相机局部 `X/Y/Z/Pitch/Roll/Yaw`，AirSim 1.8.1 对该嵌套配置解析不稳。已在 `blocks_cv_5v5_d4d5_stress_200m_settings.json` 中补齐。

### 4.2 修正后复测：达标

输出目录：`research_modules/airsim_runtime/outputs/p1_d4d5_200m_002/`

场景几何：

| 项目 | 数值 |
| --- | ---: |
| 目标数量 | 5 |
| 主拦截镜头数量 | 5 |
| 二级侦察镜头数量 | 2 |
| 目标距离主镜头 | 50.0m |
| 目标间距 | 20.0m |
| 主镜头间距 | 20.0m |
| 二级镜头相对目标高度 | 200.0m |

三类 case 结果：

| Case | D4 主动作 | 模式 | 二级节点 | 多目标视场率 | 单二级全局视野 | 二级组全局视野 | 二级 bbox 均值(px²) | 跨视角关联 | 重复锁定风险 | 终端准确率 | 歧义事件 |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| `no_degradation` | `continue_center` | `none` | SEC-01 | 1.00 | 1.00 | 1.00 | 1494.98 | 4 | false | 1.00 | 20 |
| `degrade_to_secondary` | `degrade_to_secondary` | `active_degradation` | SEC-01 | 1.00 | 1.00 | 1.00 | 1494.98 | 0 | false | 0.00 | 65 |
| `degrade_to_distributed` | `degrade_to_distributed` | `active_degradation` | - | 0.80 | 1.00 | 1.00 | 1494.14 | 0 | false | 0.00 | 65 |

结论：

- 200m 二级高差已恢复，报告中正确显示 `secondary_height_above_targets_m=200.0`。
- 二级侦察镜头在三个 case 中均达到全局视野，`secondary_network_global_view_rate=1.0`。
- 不降级场景中 D5 终端锁定准确率为 `1.0`，D4 保持 `continue_center`。
- 二级可用且终端持续不一致时，D4 进入 `degrade_to_secondary`。
- 二级不可用时，D4 进入 `degrade_to_distributed`。
- 没有出现 `duplicate_terminal_lock_risk`。

证据文件：

- `p1_d4d5_200m_002/D4_D5_5V5_STRESS_AIRSIM_REPORT.md`
- `p1_d4d5_200m_002/case_*/d4d5_stress_metrics.json`
- `p1_d4d5_200m_002/case_*/d5_terminal_observations.jsonl`
- `p1_d4d5_200m_002/case_*/d4_decisions.jsonl`

## 5. D6 执行后指标回灌验证

本轮确认 D6 的执行后回灌已生效：

- `episode_006_full_flow/intercept_summary.json` 中 `success_count=2`。
- `episode_006_full_flow/integrated_replay/d7_execution_metrics.json` 中 `intercept_success_count=2`。
- `episode_006_full_flow/integrated_replay/metrics.json` 已同步为执行后口径，包含：
  - `intercept_success_count=2`
  - `terminal_switch_allowed_rate=0.75`
  - `guidance_law_counts`
  - `terminal_switch_reject_reasons`

这解决了上一轮“执行前 integrated metrics”和“执行后 AirSim intercept metrics”分裂的问题。

## 6. 批量 seed smoke

### 6.1 结果

已尝试以下批量 smoke：

- `p1_batch_terminal_handoff_tuned_smoke_seed000/seed001`
- `p1_batch_terminal_handoff_tuned_smoke_rerun_seed000/seed001`
- `p1_batch_terminal_handoff_tuned_2seed_seed000/seed001`
- `p1_batch_cv5v5_port_smoke_seed000/seed001`

现象一致：

- seed000 可以完整运行并生成 summary。
- seed001 在启动前或 wrapper 启动时失败，原因是 AirSim RPC port `41451` 在上一轮 Blocks 退出后仍保持 open。

最终错误已被明确化：

```text
RuntimeError: AirSim RPC port 127.0.0.1:41451 is still open before Blocks launch
```

### 6.2 结论

当前 `--batch-seeds` 的“每个 seed 单独启动 Blocks”方案在本机 Blocks 1.8.1 环境下不稳定。端口释放不是简单等待 8s 或 60s 就能稳定解决。

推荐下一步改法：

1. 批量实验不要每个 seed 启停 Blocks。
2. 改成 main agent 启动 Blocks 一次，在同一个进程内循环 seed，并通过 `reset + setup_episode` 刷新场景。
3. 只在所有 seed 结束后关闭 Blocks。
4. 若必须多进程批量，应加入外部端口/进程清理策略，但这不如单进程 reset 稳定。

本轮报告中，批量 seed 不作为性能统计结论，只作为编排缺陷发现与修复方向。

## 7. 本轮代码修正

本轮测试期间新增了两处必要修正：

1. D7 terminal gate closing-speed 修正  
   AirSim runtime 在 D7 terminal gate 中使用下一步 PN 命令速度估计相对速度，避免 SimpleFlight 当前速度滞后导致 `not_closing` 误判。

2. Blocks 端口保护修正  
   `BlocksProcessManager` 在 stop 后和 start 前检查 RPC port 状态。当前可以给出明确错误，但仍建议后续把批量 seed 改成单 Blocks 进程内循环。

## 8. 最终结论

本轮核心专项测试通过：

- D7/D5 terminal-handoff tuned：通过，`terminal_switch_allowed_rate=0.75`，目标是 `>=0.40`。
- D4/D5 5v5 200m stress：通过，高差、二级全局视野、D4 仲裁动作均符合预期。
- D6 执行后指标回灌：通过，episode 级 metrics 已包含真实 AirSim 拦截结果。

未通过项：

- 多 seed 批量：当前按 seed 多次启停 Blocks 的方案不稳定，需要改为单 Blocks 进程内循环 seed。

建议下一步优先级：

1. 把 batch seed 编排改成“启动一次 Blocks，多 seed reset 循环”。
2. 在这个新 batch 架构上跑 10 seed 的 2v2 tuned 和 5v5 200m stress。
3. 对剩余 `bbox_near_image_edge` 和 `maneuver_margin_low` 做参数敏感性分析。

