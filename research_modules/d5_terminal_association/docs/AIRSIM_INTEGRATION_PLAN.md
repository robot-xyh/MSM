# AirSim 离线集成计划

## 范围

本计划只描述 AirSim 数据采集、离线回放和评估接入。不调用实机飞控、硬件驱动、武器/毁伤模型、自动处置接口，也不绕过人工授权。D5 模块只输出 `TerminalAssociation`，不改写中心维护的 `global_track_id`。

## 数据来源

从 AirSim 场景离线采集：

- RGB 相机帧和时间戳。
- 相机内参 `K`、外参 `R, t`，或可转换为 `P_c = R P_w + t` 的位姿。
- 仿真对象世界坐标、速度、类别和中心系统生成的 `global_track_id`。
- 合作/友方对象的模拟 OpenDroneID 或任务标签消息。
- 可选：分割图、深度图、标注框，用于生成或校验本地检测输入。

## 坐标与投影

AirSim 采集层负责把仿真世界位姿转换为 D5 的 `CameraModel`：

```text
P_c = R_cw P_w + t_cw
p = K [R_cw | t_cw] P_w
```

如果使用 ROS 2/tf2，只在离线回放时提供坐标变换；D5 不订阅或发布控制指令。

## 本地视觉输入

两种离线输入模式：

- 标注模式：由 AirSim 真值投影和噪声模型生成 `LocalVisualTrack`，用于算法单元评估。
- 检测模式：将 AirSim RGB 帧送入本地检测器或 MOT，例如 ByteTrack、BoT-SORT、Deep SORT，再归一化为 `LocalVisualTrack`。

MOT 的 `local_track_id` 只作为本地观测 ID，不得替代或重写 `global_track_id`。

## 身份声明输入

将合作对象元数据转换为模拟身份消息：

```json
{
  "protocol": "OpenDroneID",
  "platform_id": "FRIEND_SIM_1",
  "local_track_id": "L_friend",
  "timestamp": 12.0,
  "is_friend": true,
  "signature_valid": true
}
```

`IdentityChecker` 只把已验证且新鲜的声明作为正向友方确认。过期、未签名、签名失败或几何不一致的声明不会升级为 `locked`。

## 二级侦察节点图像 cue

AirSim 场景中可加入高空系留侦察无人机作为二级节点。二级节点正常时，将其覆盖小区内的离线图像 cue 转换为 `ReconImageCue`：

```json
{
  "cue_id": "sec_cue_001",
  "producer_node_id": "secondary_recon_1",
  "image_frame_id": "secondary_recon_1/camera",
  "timestamp": 12.0,
  "global_track_id": "G_ASSIGNED",
  "center_px": [320.0, 240.0],
  "confidence": 0.8,
  "scoped_resource_ids": ["R1", "R2"]
}
```

`ReconImageCue` 只在 `scoped_resource_ids` 指定的小范围资源中降低视觉关联代价。它不能替代中心授权、版本匹配、友方认证和本地 MOT 质量门槛，也不能让局部节点改写 `global_track_id`。

坐标语义要求：

- 若 `center_px` 来自二级侦察节点相机，回放预处理层必须先根据目标三维位置、二级相机位姿和当前拦截资源相机位姿，将 cue 重投影到当前拦截资源相机平面。
- `image_frame_id` 应标识 cue 当前所属的目标相机帧；建议在 `metadata` 中保留 `source_image_frame_id`。
- 未重投影的二级相机像素不得直接与 `LocalVisualTrack.center_px` 比较。
- 后续离线实验应记录 `recon_cue_used_count`，并对 stale cue、跨资源 cue、空 `scoped_resource_ids` 语义进行回放测试。

## 评估循环

每帧离线回放：

1. 读取中心分配 `Assignment.assigned_global_track_id`。
2. 读取或预测中心全局轨迹 `GlobalTrack`。
3. 构造当前 `CameraModel`。
4. 从标注或 MOT 结果构造 `LocalVisualTrack`。
5. 从模拟 OpenDroneID/友方标签构造 `IdentityClaim`。
6. 可选读取二级侦察节点 `ReconImageCue`。
7. 调用 `TerminalAssociator.decide(...)`。
8. 记录 `locked/ambiguous/hold/reacquire`、候选成本、cue 使用情况、正确性和 ID 不变式。

## 指标

- 终端关联正确率。
- locked precision。
- 错误 locked 数。
- `ambiguous` 次数。
- `hold` 次数，尤其是友方重叠触发次数。
- `reacquire` 次数和遮挡恢复耗时。
- 输入 `global_track_id` 变更次数，期望恒为 0。

## 防护约束

- D5 不调用 AirSim 控制 API。
- D5 不输出控制量、拦截点、打击参数或毁伤判断。
- D5 不改变中心全局轨迹表。
- 友方重叠默认 `hold`。
- 未知身份默认保持未知，不自动推断为对抗目标。
- 所有自动输出仅供离线评估和人工审查。

## 里程碑

1. 用 AirSim 真值投影生成 `LocalVisualTrack`，复现当前合成仿真指标。
2. 加入图像噪声、遮挡和漏检，评估 `ambiguous/reacquire` 行为。
3. 接入离线 MOT 输出，比较 ByteTrack、BoT-SORT、Deep SORT 与 D5 关联层。
4. 加入模拟身份声明异常，包括 stale、unverified、spoof_suspected。
5. 固化离线评估报告模板和结果 JSON 导出。
