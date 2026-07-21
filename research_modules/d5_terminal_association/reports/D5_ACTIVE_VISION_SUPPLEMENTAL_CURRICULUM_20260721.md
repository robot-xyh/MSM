# D5 主动视觉补充课程报告

- 创建时间：`2026-07-21T18:19:52Z`
- 准入状态：`development_shadow_only`
- episode / segment / sample 数量：`100 / 800 / 1200`
- canonical seed 分配：`{"test":20,"train":60,"validation":20}`
- intent 覆盖：`{"hold":200,"observe_target":600,"reacquire":200,"search_sector":200}`
- FOV 模式覆盖：`{"wide":1000,"zoom":200}`
- 相机角色覆盖：`{"interceptor":600,"recon":600}`
- ACK 故障注入覆盖：`{"applied":400,"missing":400,"rejected":400}`

上述 ACK 计数仅表示每个 seed 的 `4/4/4` 确定性故障注入覆盖，不是实际运行分布，也不是 reward、outcome、counterfactual 或 causal 证据。

- 数据集 manifest SHA256：`0c474ee1b0bab34a46c2ebce328761983cf2ecc757da30c2d3d2e03a06cd1acf`
- canonical view SHA256：`0ab1a4a6bdd439f6c8a74df5059de3c4950791fba35a1b9514942e83779f72a8`
- 数据集配置 SHA256：`e93ca6310338be5db4539fac195f5257e28d16a64b78b1a0351bf6aeca01fcee`
- training registry SHA256：`2ab928a476a4430b99326f245222f058bc5be5025158134ba89b01b3dec7815f`
- shared registry SHA256：`68608d29d1f733beea87f1faf06464fededb68a9c2972c51c10cd4c2160f032f`

所有离线 reward、outcome、counterfactual 和 causal 字段均显式标记为 unavailable。PPO、assist、在线 authority 和相机命令 authority 均保持 false。该 synthetic 补充制品不修改，也不替代正式 900-episode 数据集。
