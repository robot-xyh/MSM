# D5 主动视觉 canonical seed 只读视图

验证日期：2026-07-21（America/Los_Angeles）

## 结论

共享数值 seed 已按完整 episode 建立只读重分桶视图。原 manifest 和样本制品未修改。
canonical train/validation/test seed 为 `60/20/20`，保留 seed `1000-1019` 未进入视图。

该结果只关闭 D4/D5 等学习消费者之间的 split 身份不一致。模型准入和运行安全门保持失败关闭。

## 哈希绑定

- source manifest SHA256：`cd2ee22e8566bb14938d34aa997c850c13bf1ec9c8bd09061089c7fcc7ac3d9d`
- view manifest SHA256：`a019854fd87224996f5c84015bb66ccd37b7a0b5605f4784ffc59751e1716703`
- view content SHA256：`37d77ab1c92eddebe6294e59cfa6591bb6cfb1fa9f0ad0ba7817662b0a2b0f6c`
- canonical split SHA256：`4f9226c562758a159dda28cfdba45a6a45a9c5d0252ca6572f84c9ad0f141c09`
- canonical training-set SHA256：`dc8e22b4ba2985a1edaf9bf6b04ffd06f8a68b4f845f94140022a85b174b95e7`

## 计数

- episode：`{'train': 540, 'validation': 180, 'test': 180}`
- sample：`{'train': 695705, 'validation': 229651, 'test': 227886}`

## 未闭合门

- `hold_has_no_positive_demonstrations`
- `observe_target_is_low_prevalence`
- `reacquire_dominates_rule_demonstrations`
- `all_runtime_actions_disabled_no_applied_action_feedback`
- `no_applied_action_runtime_ack_attribution`
- `reward_unavailable`
- `counterfactual_unavailable`
- `causal_label_unavailable`
- `no_paired_shadow_non_degradation_evidence`

## 安全边界

视图不复制样本，不改变在线/离线内容，也不改变默认旧加载路径。学习输出仍不能创建、改写或换绑 `global_track_id`。几何门控、同相机互斥、版本门和规则回退保持不变。
