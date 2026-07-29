# D4 模型登记

本目录保存需要在 clean clone 中复核的 D4 模型原始字节。登记用途限于来源审计、离线加载
和 development/shadow 影子诊断。登记不表示模型通过运行准入，也不授予默认 runtime、
assist、assignment、takeover、coalition commit 或 control 权限。

## region_resource_a2_current_lineage_development_v1

该目录是冻结 current-lineage 候选的逐字节登记副本。原始候选由 clean commit
`b0d498d9e76e19e9045e127b6dae26ea164b3fa4` 构建。候选内部文件不得改写；需要产生新模型
时必须使用新的候选标识和独立目录。

固定身份如下：

- 候选 manifest 文件 SHA-256：
  `7cc10ad770bd95fcb813dbf3d16b17040ec5f41f80fe0dc53e3e291a32f4de64`
- 候选 manifest 内容 SHA-256：
  `b51f2ed01d7f8b963166fe1d7e73acd6a481c5359d54ed5c3712371733aa6ba9`
- 模型权重 SHA-256：
  `fd1b9c4cf7580083fadc04a70b87aa6439930eba764a970279611ccc57f30047`
- bundle manifest SHA-256：
  `d9fcdb348b3de8fd139b5052a4e7123a48641975cc7dcc708701a2a72ff7ab00`
- 内嵌训练数据 manifest SHA-256：
  `82819c2470505e61da753d0d24ddf910e154435cd8d2cbd0a979dfb3dd643904`
- 源码身份 SHA-256：
  `b81780cece11c792acb3113af2d4be48a19b51c0337a67c926b388197d09dfdf`

候选已知不具运行分布兼容性。2026-07-28 的 5v5/2 区域和 200v200/8 区域开发预检共
5/5 帧触发 `feature_ood`，模型实际执行为 0。该候选不得作为默认运行策略，不得启用
assist 或 control，不得用于正式 20-seed。运行时必须继续使用确定性规则回退。
