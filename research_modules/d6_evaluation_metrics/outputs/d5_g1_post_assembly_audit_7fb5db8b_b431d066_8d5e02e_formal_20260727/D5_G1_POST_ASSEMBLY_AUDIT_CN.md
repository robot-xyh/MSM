# D5 G1 v5 装配后外部审计

审计时间：`2026-07-27T02:38:00Z`

## 结论

装配证据审计结果为 **pass**。
D6 只确认 v5 装配证据完整性，不授予模型晋级、G1 辅助、默认路径、分配、故障接管或控制权限。

## 束缚关系

- v5 manifest SHA-256：`b431d066362005868374d038eb93a83b773c03715a53d8a9dfd0da21784f317d`。
- weights SHA-256：`7fb5db8b6099ca4da5706a3bec53ff7cd634e8bd267c036ce3ee4ee4bf71ca71`。
- 原开发包 manifest SHA-256：`7d459ed855cf74b810fa1f79ed0327efd39eb4be4409451266da3f3a95387ce0`。
- D6 预准入 JSON 文件/内容 SHA-256：`cbd6c72b2d9e7b78bf3aa36f975e6627250d2bf18de5a0b0ebc2c8f6cf760cd6` / `334cf662e49c735931019ff358be1894d1358f1b4a5a868759eee41d3d282d15`。
- 运行实现摘要：`b0708e718b374e5bb52db41c7bd2f994e340a2b009cfd348881a5f9d549baffe`。

## 样本与安全

- 未见 seed：`20`。
- held-out episode：`900`。
- 场景规模单元：`45`。
- 在线真值字段：`0`。
- global_track_id 改写：`0`。
- 同相机互斥违规：0。
- paired lineage SHA-256：`83e105290f3e624f267d92ceaf050d32291bd5bbbabf98580846cd31498b1af1`。
- paired lineage 记录/唯一 episode：`900` / `900`。

## 权限边界

- v5 声明的 G1 辅助资格：`True`。
- D6 模型晋级授权：`False`。
- D6 G1 辅助授权：`False`。
- D6 控制授权：`False`。
- D6 分配授权：`False`。
- D6 故障接管授权：`False`。

## 限制

- 固定候选图限制：`profiles hold the post-gate candidate graph fixed`。
- 真实相机泛化：`unavailable`。
- 中心 global_track_id 绑定正确率：`unavailable`。
- 物理闭环结果：`unavailable`。
- 在线路径：本审计不启用。

## 阻断项

- 无。
