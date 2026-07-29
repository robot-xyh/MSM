# D4 A2 实际区域策略开发诊断

## 结论

实际模型在与训练/验证互斥的开发校准集 20 个种子、420 个样本上产生 76 个通过固定门限、安全投影和消费检查的非零区域动作。
该结果记录历史实现谱系模型的可辨识动作输出。当前谱系开发证据、运行时采用、系统收益和正式准入均不可用。

## 诊断边界

- 候选：`region_resource_a2_development_calibrated_20260726_v1`
- 候选清单 SHA-256：`d3c96f0abf059d6726b4706f8380a59687d8635898253cfa04f0a8a61df036a2`
- 模型：`d4-region-a2-bc-calibrated-development-v2`
- 当前实现谱系：不一致，仅允许开发诊断
- 最低置信度保持 0.60；分类运行固定使用 0 ms 功能性时延覆盖，50 ms 运行门配置未改变，本报告不提供时延性能证据。
- 保留种子使用数为 0，在线真值字段使用数为 0。
- 中心重规划、二级接管、联盟提交、分配、控制和 assist 权限均为 false。
- 当前谱系开发证据可用：false。
- 候选固定门通过/回退：420/0。

## 结果分布

- `action_masked`：0/420
- `action_same_as_baseline`：0/420
- `confidence_insufficient`：0/420
- `out_of_distribution`：0/420
- `owner_lease_epoch_blocked`：0/420
- `policy_output_invalid`：0/420
- `resource_infeasible`：344/420
- `safe_nonzero_actual_model`：76/420
- 样本身份摘要：`3fa3b4ae9bf1e3b1e79d90a1130d5e604fa9ced6c2b70ebc53b8d70b269f69bb`
- 分类摘要：`89dea13a7d501e4c5026659e5056c60f54e904f5d80d79f74260eeb34b942ff3`
- 原始可执行动作签名数：88
- 批次策略输出退化：false
- 资源不可行样本主要来自已承诺资源占满后仍请求正备用量；整数化和确定性投影将该请求压回受保护基线。
- 本批没有低置信、分布外、权威/租约/时期错绑或动作掩码拒绝。

## 正式证据前置条件

1. 重新生成与当前实现谱系一致的候选制品。
2. 在不使用校准种子调参的前提下运行至少 20 个正式未见种子。
3. 形成严格后继计划、owner/coalition ACK、物理窗口和独立同键 R0。
4. 由 D6 完成非退化和收益审计后，另行评审 assist 准入。
