# D4 模型登记

本目录保存需要在 clean clone 中复核的 D4 模型原始字节。登记用途限于来源审计、离线加载
和 development/shadow 影子诊断。登记不表示模型通过运行准入，也不授予默认 runtime、
assist、assignment、takeover、coalition commit 或 control 权限。

## region_resource_a2_8region_runtime_action_readiness_shadow_v3

该目录是 detached clean worktree commit
`4ba2c8a649dab157d55a2dd7817d5a8ded494114` 构建结果的逐字节登记副本。D4 review loader
独立复核通过，源目录与登记目录均包含 8 个文件，逐文件 SHA-256 完全相同。固定身份如下：

- 候选 manifest 文件：`5e575ec4c0cd40ddb33ae9f06ce3b5ca015825c5ad3364733234349f143459c3`
- 候选 manifest 内容：`7978aec0bdf577571b9b85df10cf91f11a70f5d1b937f9dd5083bbf7e836ada2`
- 模型权重：`ace5df6dae62f8a9a80a4cd141d50a93427e609e4caa605b9962494ebfe7f52d`
- 源码身份：`e260ff2f69660142985569a73634920700325dbd6282b7e76e78a8a6562214ef`
- 复合数据：`5d174dd3526a0262990c5472556b024ac0306b33262fd805a38da16c999bee03`
- 全局 split：`69ae1b0e40c6478ac62d65d89b1634f867d10b8167c523763741827a6f96d817`
- 运行门：`7797283405cad532f2911ea5965102f3b916c4ce6ccf60c17f955ea87e0e6872`
- 登记文件树：`07c770b05ffc70f190cd8b45d762d579857747e0efb12b472a2354ee5aeaa93a`

运行投影合同为最小备用比例 0.1、最小备用资源 1、建议有效期 1.5 秒；规则权重为
2.0/0.5/0.05，安全门为 0.05/0.60/0.59/0.10。validation 门后 293/344 通过，动作
不一致通过 0，校准接受。在线 truth 和 test/calibration/reserved 使用数均为 0。

候选仍只允许 development/read-only shadow。`runtime_preflight_completed=false`，
formal evaluation 未授权，assist、assignment、takeover、coalition commit、control、
physical 和 runtime ACK 权限全部为 false。main 后续从 clean commit `83b8869...0226`
完成外部单 seed development preflight：20v20/8-region seed 2001 和
200v200/8-region seed 2002 均为 3/3 分布内、3/3 门后许可；5v5/2-region seed 2000
按 8-region 适用域预期拒绝。该外部证据不改写本目录的
`runtime_preflight_completed=false`。目录不得改写；多 seed、配对非退化、收益和正式
holdout 状态继续由外部审计记录。

## region_resource_a2_8region_runtime_action_readiness_shadow_v2

该目录是 detached clean worktree commit
`891b542337ef065eee8c794d38dfa6ba382fea9e` 构建结果的逐字节登记副本。候选 manifest
文件/内容、模型权重、源码身份、复合数据和全局 split SHA-256 为
`c3194c900058e85aad57bd52853fea99846a35c1f8d4fd8a81a53832d4daf72b`、
`481480346f6c7355d3124f7ff3fdc4e9f8208a0209d4319514be25a91793852f`、
`ace5df6dae62f8a9a80a4cd141d50a93427e609e4caa605b9962494ebfe7f52d`、
`331b4f296a1c9fa46b61c9dcb7b59c499280817389b3b1b843181e38d4392ce0`、
`996dbd667deec08451a52c9878b2ad02cf699c69ec0920fe26807fec0f62493e` 和
`69ae1b0e40c6478ac62d65d89b1634f867d10b8167c523763741827a6f96d817`。
登记目录的八个文件与 clean-build 源目录具有相同相对路径和逐文件 SHA-256。

三来源数据内容地址为 `b06d741b...6158`、`7e17aba7...9e72` 和
`34244f1f...c56`。数字 seed 0-99 按 70/15/15 全局原子切分，正式保留 seed
1000-1019、test payload 和校准 seed 使用数均为 0。validation 共 344 个样本；原始
置信度通过 344，其中动作不一致 51；运行时一致性门后通过 293，其中动作不一致 0，
校准接受。

候选只允许 development/read-only shadow。main 已从 clean commit `8421de1...52e0`
执行 5v5/2-region preflight，但 3/3 帧因 main 的 1.5 秒建议有效期与 v2 固定的 1.0 秒
合同不一致而失败关闭。正式评价未执行；assist、assignment、takeover、coalition commit、
control、physical、runtime ACK 与 formal evaluation 权限全部为 false。该目录是不可变
失败证据，不得改写；后续产物必须使用新的候选标识。

## region_resource_a2_8region_runtime_action_shadow_v1

该目录保存从 clean detached checkout
`923f3f6e91af0f85aed446c66420c834d2de63fb` 构建的 8-region 复合训练候选。运行特征源
和动作课程源分别为 `b06d741b...6158`、`7e17aba7...e72`；候选 manifest 文件/内容、
权重、源码身份、bundle manifest、复合数据和 split SHA-256 分别为
`ad5846b1...f5e5`、`52866167...e2f`、`43157f4e...b0ee`、
`f9c52715...53ed`、`824aecf1...b8f`、`ee6bd202...cfd4` 和
`69ae1b0e...d817`。

候选只允许 read-only shadow。validation 中 51 个动作不一致样本越过固定 0.60，
`confidence_calibration_accepted=false`；适配器强制规则回退。main runtime preflight
已执行但未通过，正式 20-seed/900-cell 禁止。该目录不得改写；后续重新训练必须使用新的
候选标识和目录。2026-07-28 最终 registry 专项 14/14、D4 全量 720/720 通过。

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
