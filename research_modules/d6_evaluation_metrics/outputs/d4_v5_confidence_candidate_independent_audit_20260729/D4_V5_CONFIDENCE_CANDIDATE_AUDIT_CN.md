# D4 v5 置信校准候选独立审计

## 结论

D6 已完成只读审计。候选四个文件、调用方固定哈希、v4 基线、v3 登记树、数据用途和全 false 权限均核验通过。固定 0.60 开发门按冻结 actor 和 TRAIN/VALIDATION payload 独立复算后仍通过。
该结果不构成独立验证。TRAIN 评分把 350/350 个被评样本自身放入近邻库；VALIDATION 有 42/75 条 exact overlap，只有 3 条样本与 TRAIN 最近距离不小于 0.1。候选保持记忆化开发对照、未注册、准入关闭并使用规则回退。
冻结 v4 模型和候选状态的实际 latent 维数均为 24。D4 报告及本次任务口径写为 64 维，两者不一致。D6 未构造虚假的 64 维结果；该项列入严格审计阻断。

## 固定身份

- manifest file SHA-256：`caa774143db4a9c797e2a4ddff42d8f4cbc437471fe95926270f9bdec93b9459`
- manifest content SHA-256：`83192d4f96d7dd2c64ffd8f9b5c7c11a70c8c24a90934a0dfea12fe397c12c52`
- calibration state SHA-256：`d8bd543759f6e52eb62585c1bd8aa67e59e718e7b548d38cc9dd5c690a5612a3`
- calibration summary SHA-256：`7f0047f72ebeea0358c127af5fe3dabe0c7f886bee48ff94b7d92b12b3259c60`
- development gate SHA-256：`e88c9480765369e34a03dd417e4b483143188da40c3403ff35918f9cfd605b3c`
- builder source SHA-256：`77e91e06712013e6c1195c40f72b9a941d8396aa4594b52bd7d839276b57e1e0`
- v4 tree SHA-256：`2afd692874b91a23a5525448a0c5af98f3c2d96f0b12cebbf81a570d58d500d0`
- v3 registry tree SHA-256：`07c770b05ffc70f190cd8b45d762d579857747e0efb12b472a2354ee5aeaa93a`

## 独立复算

| split | 样本 | 正/负 | 正类召回 | 负类特异度 | 最小正裕量 | Brier |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| TRAIN | 350 | 58/292 | 1.000000 | 1.000000 | 0.400000 | 0.000000000 |
| VALIDATION | 75 | 13/62 | 1.000000 | 1.000000 | 0.209319 | 0.000484791 |

D6 从冻结 v4 actor 重建实际 24 维池化 latent，使用 TRAIN 的均值与标准差归一化，再执行 k=11 逆距离评分。重建状态与候选 state 的最大数值差不超过 1e-12。候选 summary 指标只在独立结果生成后进行逐项核对。

## 记忆偏差

- 全库存 TRAIN：self-match 350/350。
- leave-one-sample-out：正类召回 1.000000，负类特异度 0.993151，Brier 0.006652708。
- raw observable key 留组：正类召回 0.965517，负类特异度 0.958904，Brier 0.037610440。
- latent exact key 留组：正类召回 0.965517，负类特异度 0.958904，Brier 0.037610440。

## VALIDATION 重合

| 项目 | 数量 |
| --- | ---: |
| raw graph exact overlap | 42 |
| latent exact overlap | 42 |
| 非 exact 且距离 `<1e-3` | 20 |
| 距离 `[1e-3,0.1)` | 10 |
| 距离 `>=0.1` | 3 |
| 最近邻标签一致 | 75 |
| 正类 exact overlap | 12/13 |

## 分层指标

- `all_validation`：n=75，正/负=13/62，recall=1.000000，specificity=1.000000，margin=0.209319，Brier=0.000485。
- `without_exact_overlap`：n=33，正/负=1/32，recall=unavailable，specificity=1.000000，margin=unavailable，Brier=0.001102。
- `nearest_distance_ge_1e_3`：n=13，正/负=1/12，recall=unavailable，specificity=1.000000，margin=unavailable，Brier=0.002797。
- `nearest_distance_ge_1e_1`：n=3，正/负=0/3，recall=unavailable，specificity=unavailable，margin=unavailable，Brier=unavailable。

去除 exact overlap 后只剩 1 个正类；距离不小于 0.1 的 3 个样本均为负类。低于固定最小分母 5 的指标写为 unavailable，没有用 0 填补。

## 数据与权限

- D6 语义读取 TRAIN 350 条、VALIDATION 75 条。
- TEST payload semantic read/fit 为 0；v4 树完整性检查对 TEST 文件只做字节哈希，不解析内容。
- 正式 holdout payload read/fit 为 0，未运行正式 holdout。
- v4/v5 登记常量均为空，v4/v5 registry 目标路径不存在。
- 所有生产、D3、D7 权限为 false；未执行 runtime preflight。

## 准入结论

候选定性保持 `development memorization baseline`。固定开发门通过只说明同源重合开发集上的数值结果可复现。独立验证、泛化、正式准入和收益证据均不可用。
最终状态为 candidate unregistered、admission closed、rule fallback required。D6 不运行正式 holdout，不授予 D3/D7 权限。

## 失败关闭

- 普通 artifact 字节篡改由调用方固定文件哈希拒绝，错误码 `candidate_artifact_external_anchor_mismatch`。
- 同步修改 payload、候选 artifact hash、content hash 和 manifest 后，仍由 manifest file 外部锚拒绝，错误码 `candidate_manifest_file_external_anchor_mismatch`。
- 重合计数与调用方交叉核对值不一致时，错误码 `validation_overlap_expected_crosscheck_mismatch`。
