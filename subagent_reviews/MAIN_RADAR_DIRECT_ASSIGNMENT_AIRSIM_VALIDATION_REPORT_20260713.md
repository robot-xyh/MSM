# 远距雷达直接分配策略 AirSim 验证报告

## 1. 验证目的

本轮调整针对以下工程判断：目标仍处于雷达中段跟踪范围、中心航迹和当前分配有效时，不应因为末端相机尚未锁定目标而强制调用二级侦察节点或触发二次分配。二级节点保留为中心失效接管、真实高风险辅助和末端身份冲突仲裁手段，而不是每个远距航迹的必经环节。

验证范围包括：

1. 2v2 远距雷达直接分配，检查 D3 计划、D4 仲裁和 D7 雷达 PN 是否稳定。
2. 5v5 YOLOv8 + ByteTrack 三 seed 实测，检查真实视觉链路接线及其对中心计划的影响。
3. 显式重分配压力注入，检查 `--cv-reassignment-time` 只在指定场景生效。

本轮使用 AirSim Blocks `ComputerVision` 模式。未保存 PNG 截图；AirSim actor/object ID 只进入离线评价，不参与在线 D5 全局身份绑定。

## 2. 策略与实现

### 2.1 正常执行路径

```text
D1/D2 GlobalTrack
    -> D3 中心 AssignmentPlan(versioned)
    -> main 按当前 binding 和 D2 预测位置指向相机
    -> D5 生成 TerminalAssociation
    -> main 根据资源到分配航迹的距离标记 terminal_evidence_applicable
    -> D4 仲裁
    -> D7 雷达 PN 或经合同许可后的视觉 PNG
```

当 `terminal_evidence_applicable=false`、中心健康、计划 current/feasible 且不存在硬冲突时，D1/D2/D3 的普通软风险只记录、不请求二级视觉辅助，D4 输出 `continue_center`。以下证据仍保持强门控：量测陈旧或高不确定度、已观测 ID switch/重复航迹、计划过期或资源不可执行、友方冲突、重复终端锁定、明确的资源或 `global_track_id` 不一致。

### 2.2 压力测试路径

正常 CV episode 不再默认在半程换向。只有显式设置 `--cv-reassignment-time` 时，main 才在指定时刻用场景重分配几何覆盖实时 D3/D2 相机指向，并写入：

- `assignment_phase=secondary_reassignment`
- `pointing_source=explicit_reassignment_stress`

该功能用于制造跨视场/目标错配压力，不代表 D3 已发布新的作战计划。

## 3. 场景参数

| 项目 | 2v2 雷达直分配 | 5v5 YOLO/ByteTrack | 5v5 显式压力 |
| --- | --- | --- | --- |
| seed | 7 | 7、17、27 | 7 |
| 仿真时长/步长 | 3 s / 0.5 s | 3 s / 0.5 s | 2 s / 0.5 s |
| 主相机初始跟随距离 | 50 m | 50 m | 50 m |
| 目标间距 | 20 m | 20 m | 20 m |
| 目标 asset/缩放 | `Quadrotor1` / 2 | `Quadrotor1` / 2 | `Quadrotor1` / 2 |
| 主相机 | 1920x1080，90 deg | 1920x1080，90 deg | 640x480，90 deg |
| 二级侦察相机 | 3840x2160，80 deg，高差 200 m | 3840x2160，80 deg，高差 200 m | 无 |
| 检测链路 | AirSim detect | YOLOv8 `best.pt` + ByteTrack | AirSim detect |
| YOLO 推理尺寸 | 不适用 | 主相机 960，二级 1280 | 不适用 |
| 图像保存 | 关闭 | 关闭 | 关闭 |

## 4. 结果

### 4.1 2v2 远距雷达直接分配

| 指标 | 结果 |
| --- | ---: |
| AirSim 连接/有效帧 | 成功 / 7 |
| 主相机图像 | 14/14 成功 |
| 二级相机图像 | 7/7 成功 |
| D3 计划 owner/version | `center` / 1，全程不变 |
| D4 `continue_center` | 14/14 |
| D4 主动降级/重分配 pending | 0 / 0 |
| D7 `radar_midcourse` / `radar_pn` | 14/14 |
| `d4_owner_mismatch` | 0 |
| D2/D5 ID switch | 0 / 0 |
| 末端视觉 PNG 切换 | 0 |
| 末帧平均目标距离 | 49.99 m |
| 投影有效率 | 1.0 |
| main bus 平均循环耗时 | 16.45 ms |

首帧采用 2 条场景 bootstrap 指向；后续 6 帧使用 12 条 D3 binding + D2 预测位置指向。AirSim detect 在该 actor/几何组合下未返回框，但这不再导致远距 D4 辅助请求。该场景验证了雷达中段链路可在没有视觉锁定时保持中心计划和雷达 PN。

### 4.2 5v5 YOLOv8 + ByteTrack 三 seed

| 指标 | 聚合结果 |
| --- | ---: |
| 成功运行 | 3/3 seeds |
| 总有效帧 | 21 |
| D3 稳定中心计划 | 3/3，均为 version 1 |
| D4 `continue_center` | 105/105 |
| D7 `radar_midcourse` | 105/105 |
| 主动降级 / ID switch | 0 / 0 |
| 在线 truth 字段违规 | 0 |
| D5 视觉处理平均耗时 | 12.99 ms（12.47-13.28 ms） |
| 末帧在线检测总数 | 15，平均每 seed 5 |
| 离线检测 precision 均值 | 1.00 |
| 离线检测 recall 均值 | 0.678 |
| native MOT 正式准入 | 0/18 相机-seed 流 |

四组主相机流在三个 seed 中保持 `native_active_frame_rate=1.0`，局部连续性为 1.0；第三主相机没有稳定检测。200 m 高差二级相机的离线 recall 约为 0.08-0.09，并在每个 seed 出现 1 次局部 ID switch。所有流只有 8 个 warmup-inclusive 帧，尚未满足 native MOT 准入所需的样本长度；部分流还受召回率门限限制。

因此，本次结果证明 YOLO/ByteTrack 已进入真实 AirSim 在线链路，但不能据此宣布 200 m 二级视觉或 ByteTrack 参数完成标定。当前正确处理是继续使用雷达中心分配，不把低召回的二级观察设为正常执行前置条件。

### 4.3 显式重分配压力注入

压力场景共 5 帧：

- `t=0.0 s`：5 条 `scenario_bootstrap`。
- `t=0.5 s`：5 条 `d3_binding_d2_predicted_state`。
- `t=1.0/1.5/2.0 s`：15 条 `explicit_reassignment_stress`。
- Camera 2/3 的观察目标按预设互换；其他相机保持原目标。

这说明显式压力参数已恢复生效，同时正常 2v2/5v5 场景仍由实时 D3/D2 指向控制。

## 5. 结论与边界

本轮完成了“远距雷达直接分配”的代码闭环和真实 AirSim 验证。中心健康、计划有效且只有软风险时，系统不会因为末端相机未锁定而调用二级观察或二次分配；D7 持续执行雷达 PN。进入末端距离、出现硬身份冲突、计划失效或中心故障后，原有 D4/D5 安全门控继续生效。

尚未闭合的工作是视觉性能标定，而不是中心分配链路：需要更长的 YOLO/ByteTrack episode、第三主相机视角检查、200 m 二级相机的目标尺度/云台/推理阈值校准，以及后续数据集补充。`cross_view_association_count` 在当前 D6 口径中表示已处理的关联上下文，不等同于成功的跨相机身份注册；本轮多视角共识率仍为 0。

## 6. 证据索引

- 2v2：`research_modules/airsim_runtime/outputs/radar_direct_2v2_far_policy_v2_20260713/`
- 5v5 batch：`research_modules/airsim_runtime/outputs/radar_direct_5v5_yolo_bytetrack_20260713/`
- 5v5 seed 7/17/27：同名前缀的 `_seed007`、`_seed017`、`_seed027` 目录
- 显式压力：`research_modules/airsim_runtime/outputs/explicit_cv_reassignment_stress_5v5_v2_20260713/`
- 主指标：各 episode 的 `main_episode_bus/main_episode_bus_summary.json`
- 原始帧：各 episode 的 `blocks_frames.jsonl`
- 集成指标：各 episode 的 `integrated_replay/metrics.json`
