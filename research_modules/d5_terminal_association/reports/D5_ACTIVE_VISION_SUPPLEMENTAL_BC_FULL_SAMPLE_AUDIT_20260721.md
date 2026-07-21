# D5 主动视觉补充行为克隆全样本准入审计

- 验证日期：`2026-07-21`
- 审计结论：`complete`
- 违规数：`0`
- episode / segment / sample：`100 / 800 / 1200`
- canonical episode：`{"test":20,"train":60,"validation":20}`
- canonical sample：`{"test":240,"train":720,"validation":240}`
- 完整文件：online / offline / episode = `100 / 100 / 100`
- SHA256 校验：`302 / 302`
- 有限特征样本：`1200 / 1200`，候选特征行 `7800`
- intent：`{"hold":200,"observe_target":600,"reacquire":200,"search_sector":200}`
- FOV：`{"wide":1000,"zoom":200}`
- 相机角色：`{"interceptor":600,"recon":600}`

验收阈值为 100 episode、1200 sample、canonical 60/20/20 episode 与 720/240/240 sample、全部文件哈希一致、全部 35 维候选特征有限，且 truth、reserved seed、dirty source 和审计违规均为 0。

`applied/rejected/missing = 400/400/400` 仅表示 synthetic 确定性故障注入覆盖，不是实际运行 ACK 分布，也不构成动作到 outcome 的归因证据。

reward、outcome、counterfactual、causal 四类离线标签均保持 unavailable，没有用 0 补值。PPO、assist、在线 authority 与相机命令 authority 均为 false，rule fallback required=true。

该结论只完成补充规则教师数据的 behavior-cloning 全样本审计，是 D6 跨模块学习准入的前置证据；它不是正式观测语料、真实 runtime ACK 证据或模型上线许可。

## 来源绑定

- dataset manifest SHA256：`0c474ee1b0bab34a46c2ebce328761983cf2ecc757da30c2d3d2e03a06cd1acf`
- canonical view SHA256：`0ab1a4a6bdd439f6c8a74df5059de3c4950791fba35a1b9514942e83779f72a8`
- dataset config SHA256：`e93ca6310338be5db4539fac195f5257e28d16a64b78b1a0351bf6aeca01fcee`
- training registry SHA256：`2ab928a476a4430b99326f245222f058bc5be5025158134ba89b01b3dec7815f`
- shared registry SHA256：`68608d29d1f733beea87f1faf06464fededb68a9c2972c51c10cd4c2160f032f`
- summary content SHA256：`0577c73810413ced6277e679477422f467cb2db094f1d376e39e4cbb2a3abd65`
- clean source commit：`13e37286d2996a227924bb1a8e2766e52116a534`
- 审计内容 SHA256：`a11b65596a4c416deba6d0cb35dcc0c32342a5bae0481291d43e8de0e26550dd`

## 剩余门槛

- D6 跨模块学习准入审计。
- 真实 runtime applied ACK 与 outcome 归因。
- reward、counterfactual 与 causal 标签。
- paired shadow non-degradation。
- PPO、assist 与 authority 继续关闭。
