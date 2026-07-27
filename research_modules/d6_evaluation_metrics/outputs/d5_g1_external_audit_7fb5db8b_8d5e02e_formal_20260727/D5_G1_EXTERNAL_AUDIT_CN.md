# D5 G1 预准入外部审计

审计时间：`2026-07-27T02:36:00Z`

## 结论

证据审计结果为 **pass**。
D6 只确认证据链是否通过，不授予模型晋级、G1 辅助权限、控制权、默认路径变更、分配权或故障接管权。

## 候选绑定

- 模型指纹：`sha256:7fb5db8b6099ca4da5706a3bec53ff7cd634e8bd267c036ce3ee4ee4bf71ca71`。
- manifest SHA-256：`7d459ed855cf74b810fa1f79ed0327efd39eb4be4409451266da3f3a95387ce0`。
- weights SHA-256：`7fb5db8b6099ca4da5706a3bec53ff7cd634e8bd267c036ce3ee4ee4bf71ca71`。
- 当前实现摘要：`b0708e718b374e5bb52db41c7bd2f994e340a2b009cfd348881a5f9d549baffe`；证据实现摘要：`b0708e718b374e5bb52db41c7bd2f994e340a2b009cfd348881a5f9d549baffe`。
- 未见 seed：`20`。
- held-out episode：`900`。
- 场景规模单元：`45`。

## 安全计数

- 在线真值字段：`0`。
- global_track_id 改写：`0`。
- 同相机互斥违规：`0`。

## 泛化限制

- 单特征最高 AUC：`0.7200734256705918`，特征为 `angular_velocity_delta_rad_s`，门限为 `0.98`。
- 扰动最低边/簇 F1：`1.0` / `1.0`。
- 扰动过程重新构建候选图：`False`。

## 未覆盖证据

- 真实相机泛化：`unavailable`。输入只包含合成 held-out 和 paired-shadow 证据。
- 中心 global_track_id 绑定正确率：`unavailable`。输入只证明零创建或换绑违规，不含中心绑定结果与离线真值配对。
- 物理闭环结果：`unavailable`。输入不含导引、控制或物理拦截结果记录。

## 阻断项

- 无。

## 使用边界

D5 后续证据装配器只能消费本 JSON 及其文件 SHA-256、内容 SHA-256。任何字段缺失、类型变化、哈希不一致或 `audit_passed=false` 都必须继续失败关闭。
