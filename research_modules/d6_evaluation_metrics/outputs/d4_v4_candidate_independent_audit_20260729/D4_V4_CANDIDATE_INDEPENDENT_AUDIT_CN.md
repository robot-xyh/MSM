# D4 v4 未注册候选独立审计

## 结论

D6 独立、只读审计通过候选完整性和 development 指标重算。该结论仅适用于 train/validation 开发证据；候选保持未注册、admission closed、rule fallback required，正式 holdout 与 runtime preflight 均未完成。
固定 0.60 门在已读 train/validation 上没有负类越门，但正类召回和置信度裕量偏薄，不能解释为泛化、正式验证、收益或运行准入证据。

## 冻结身份与文件树

- manifest content SHA-256：`4f3e973597469d394a594bec3dd7d2c16b24e80d2e97ba45f718d9ef8397e116`
- manifest file SHA-256：`2986d166ad6de231896e46f78aa2d9304c21b6d68714eaf34dfe21439220bebe`
- model state SHA-256：`33a28060f11277a549b90d2f2f365962fec057b2bfb50a70ab5a422059cb9fe5`
- dataset SHA-256：`b31fc43f3d3cff34ee53f2b2c33ece0b06d7624e46e26a36c4aa834135e7fb8c`
- split SHA-256：`c212fe9b48e9908fd4d47488711724ed361429cf9df29667ac32c3e88d094619`
- clean source commit：`fd857457bb27a4a709a7c4937e22ebe1cbd7f848`
- 候选树：180 个文件，179 个 manifest artifact，4 个目录；逐文件 SHA-256 全部一致，无 symlink 或特殊文件。
- source implementation：4 个文件与 commit blob 逐字节一致。

## 外部数据与用途

- 外部 evidence content SHA-256：`f059ff5dc1436977f75593edf0cffe5fde7b1865c8db0c5b6330cc7b834e3ca5`
- source derivation file SHA-256：`f39d9ba996c60ca3213f82d2547159bfbd581387bbd421824f9b5a659c37630f`
- train：70 seeds / 140 episodes / 350 samples；目标正/负 60/290，confidence 正/负 58/292。
- validation：15 seeds / 30 episodes / 75 samples；目标正/负 15/60，confidence 正/负 13/62。
- test 仅解析 manifest 元数据：15 seeds / 30 episodes / 74 frames；候选 payload、builder read、D6 payload read、fit、weight fit 均为 0。
- truth identifier use、future outcome available/use、reward available 均为 0。

## Actor 与权重

- actor checkpoint：独立复算 epoch 107，与声明一致；history 共 240 epochs。
- train 正/负召回：0.966667 / 0.951724；validation 正/负召回：0.866667 / 0.966667。
- actor 与 confidence 权重均只由 TRAIN 推导；validation/test weight fit 为 0。具体权重和库存见机器可读 JSON。

## 固定 0.60 门

| split | 正类召回 | 负类特异度 | Brier | 越门最小裕量 | 最大负类裕量 |
| --- | ---: | ---: | ---: | ---: | ---: |
| train | 0.206897 | 1.000000 | 0.186847275 | 0.000504935 | -0.000029838 |
| validation | 0.307692 | 1.000000 | 0.186468779 | 0.000504935 | -0.000602221 |

confidence checkpoint 独立复算 epoch 66，固定门接受 epoch 8 个，最长连续 7 个。

## Fixture、Registry 与权限

- development fixture 有效置信度 0.602367163，高于 0.60 的裕量仅 0.002367163；其分类固定为 `training_domain_smoke_only`，不是泛化或正式验证。
- v3 registry 共 8 个文件，树摘要 `07c770b05ffc70f190cd8b45d762d579857747e0efb12b472a2354ee5aeaa93a`，与冻结值一致。
- v4 注册常量全部为 null，registry 目标路径不存在；候选未注册。
- 逻辑权限全部为 false，核验通过；formal holdout/preflight 均未完成，生产权限不可用。

## 准入阻断项

- `candidate_unregistered`
- `formal_holdout_not_completed`
- `runtime_preflight_not_completed`
- `development_fixture_train_domain_smoke_only`
- `confidence_positive_recall_low`
- `confidence_threshold_passing_margin_too_thin`
- `runtime_outcome_and_benefit_unavailable`

## 失败关闭负例

- 普通候选 artifact 的字节篡改由逐 artifact SHA-256 门拒绝，错误码为 `candidate_artifact_sha256_mismatch`。
- 权限声明篡改后，即使同步重算候选自有 manifest content hash，仍由 D6 固定外部锚拒绝，错误码为 `candidate_manifest_content_anchor_mismatch`。
- 两类合同均由 `tests/test_d4_v4_candidate_audit.py` 的临时副本负例覆盖；原候选和外部 evidence 保持只读。

## 审计边界

- 本次未运行正式 holdout，未执行 runtime preflight，未登记候选。
- 本次未授予或建议开放 assist、authority、assignment、takeover、coalition、control 或其他生产权限。
- JSON 中保留候选逐文件 SHA-256、v3 registry 逐文件 SHA-256、权重库存、checkpoint 和全部重算指标。
