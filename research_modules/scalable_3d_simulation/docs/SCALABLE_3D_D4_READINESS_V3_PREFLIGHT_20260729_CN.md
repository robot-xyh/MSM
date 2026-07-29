# D4 readiness v3 运行兼容性预检

## 结论

D4 readiness v3 已通过 20v20 和 200v200 两个 8 区域单随机种子开发预检。每组 3 帧
均位于训练分布内，原始模型推理、运行置信门应用、动作一致和候选许可均为 3/3。
5v5 使用 2 区域输入，被 8 区域候选按适用域和特征分布外规则拒绝。

该结果允许开展受控开发配对，不授予区域策略实际采用、降级、联盟、控制或正式评价权限。
多随机种子稳定性、同键规则基线、后继计划、运行确认、物理结果和成对非退化尚未验证。

## 候选

- 构建代码提交：`4ba2c8a649dab157d55a2dd7817d5a8ded494114`
- 预检代码提交：`83b8869b49c4ac26b6a5b6fb336dfe9af6960226`
- 候选：`region_resource_a2_8region_runtime_action_readiness_shadow_v3`
- 候选 manifest 内容：`7978aec0bdf577571b9b85df10cf91f11a70f5d1b937f9dd5083bbf7e836ada2`
- 模型权重：`ace5df6dae62f8a9a80a4cd141d50a93427e609e4caa605b9962494ebfe7f52d`
- 运行置信门：`7797283405cad532f2911ea5965102f3b916c4ce6ccf60c17f955ea87e0e6872`
- 适用区域数：8
- 建议有效期：1.5 秒
- OOD / 置信度 / 不一致封顶 / 连续动作容差：0.05 / 0.60 / 0.59 / 0.10

候选使用 development/read-only shadow 权限。assist、assignment、takeover、
coalition、control、physical、runtime ACK 和 formal evaluation 均为 false。

## 方法

main 从统一三维质点运行时提取匿名 D4 区域快照。每帧先检查节点和边特征是否落在候选
记录的训练范围内，再执行模型前向计算。模型输出通过同一个确定性资源投影器和规则动作
一致性门。正式 D4 决策在门控前后保持不变。

开发验收阈值为：

- 区域帧不少于 2；
- 分布内帧比例不低于 0.80；
- 原始模型推理、运行门应用和候选许可各不少于 1 帧；
- 在线真值、运行门真值、非有限状态、正式决策改动和门内容分歧均为 0。

预检使用非正式 seed 2000、2001、2002，与正式保留 seed 1000 至 1019 无重叠。

## 结果

| 场景 | seed | 区域 / 侦察节点 | 帧数 | 分布内 | 推理 / 门 / 一致 / 许可 | 回退 | 在线真值 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 5v5 | 2000 | 2 / 2 | 3 | 0/3 | 0 / 0 / 0 / 0 | 3 | 0 |
| 20v20 | 2001 | 8 / 2 | 3 | 3/3 | 3 / 3 / 3 / 3 | 0 | 0 |
| 200v200 | 2002 | 8 / 8 | 3 | 3/3 | 3 / 3 / 3 / 3 | 0 | 0 |

20v20 和 200v200 的状态均为有限值。运行门真值使用、上下文不匹配、正式决策摘要不匹配、
候选许可分歧和正式决策改动均为 0；运行 blocker 和候选 blocker 均为空。

5v5 是负例。候选声明 8 区域适用域，因此 2 区域输入产生
`candidate_region_count_out_of_scope`。边 `distance_log` 和 `transfer_time_log`
也超出训练范围。模型没有在不支持输入上执行，3 帧均按 `feature_ood` 使用规则路径。
运行置信门没有执行，因此其内部的 gate-rule-fallback 计数为 0。

三份 JSON 的 SHA-256 为：

- 5v5：`06458d5e97c55816bee730db8b505593d7437625c24fb897b61ebe7a9f5483ff`
- 20v20：`cd90ab75a6d3f170a2feef452073af61be659ee4a93f77ea12c8dfc106d07a1b`
- 200v200：`cf98552f23ca1eafef11e006a28adace381121b167f19b68155f29993a4b67db`

## 边界

每个正例只有一个 seed 和 3 个区域帧，不能代表长时稳定性、通信退化、中心失效或二级
节点部分就绪条件。`paired_development_rollout_allowed=true` 只允许下一阶段运行开发性
候选/规则配对。候选 registry 保持不可变，外部预检不回写
`runtime_preflight_completed=false`。

下一步先扩展 20v20 和 200v200 多 development seed，再运行唯一同键规则基线。只有形成
可辨识区域干预、D3 后继计划、runtime/owner/coalition ACK、物理窗口和 D6 成对非退化
证据后，才准备正式 holdout。
