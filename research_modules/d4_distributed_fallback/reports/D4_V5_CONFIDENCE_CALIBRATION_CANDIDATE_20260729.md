# D4 v5 置信校准开发候选

## 结论

D6 已确认 v4 候选完整，并完成 v5 独立只读审计。v5 artifact、数据用途和预先固定的
TRAIN/VALIDATION 开发门均可复现；重合与留组诊断确认当前数据不具来源独立性。v5 定性为
“记忆化开发对照，等待来源独立扰动集”，仍未注册，不具备 D3、D7 或其他生产权限。
开发门通过不关闭低召回 P1。

## 基线问题

| split | v4 正类召回 | v4 负类特异度 | v4 最小越门正裕量 |
| --- | ---: | ---: | ---: |
| TRAIN | 0.206897 | 1.000000 | 0.000504935 |
| VALIDATION | 0.307692 | 1.000000 | 0.000504935 |

v4 对负类保持完全拒绝，但大部分正类没有越过 0.60。已越门样本离门限最近只有
0.000504935，数值扰动可能改变通过状态。v4 因此冻结，不进入登记或准入。

## 校准方法

v5 保留 v4 actor 的动作网络和所有确定性安全门。它从冻结 actor 提取消息传递后的
实际 24 维节点均值 latent，使用 TRAIN 均值和标准差归一，再按固定 11 近邻的逆距离
正标签比例输出置信度。冻结 v4 `hidden_dim` 与 v5 `feature_dimension` 均为 24；这是
冻结候选配置，不改变通用模型默认维度。

拟合只使用 TRAIN 350 条记录，其中正类 58、负类 292。VALIDATION 75 条记录只计算
开发指标；validation 的拟合、权重拟合、门限拟合、超参数拟合和候选选择计数均为 0。
TEST 与正式 holdout payload 的读取和拟合计数均为 0。输入和拟合不使用 truth
identifier、未来结果或 reward。

## 开发门

固定置信门为 0.60。候选必须同时满足：

- TRAIN 和 VALIDATION 正类召回均不低于 0.80；
- TRAIN 和 VALIDATION 负类特异度均为 1.0；
- TRAIN 和 VALIDATION 的最小越门正裕量均不低于 0.02；
- validation、TEST 和正式 holdout 的数据用途符合冻结边界；
- v4 候选树和 v3 registry 树在拟合、落盘前后保持不变。

开发门不可由命令行重配。指标未达到时不创建候选目录，只保存
`candidate_created=false` 的失败回执。

## 结果

| split | 正类召回 | 负类特异度 | 最小越门正裕量 | Brier |
| --- | ---: | ---: | ---: | ---: |
| TRAIN | 1.000000 | 1.000000 | 0.400000 | 0.000000 |
| VALIDATION | 1.000000 | 1.000000 | 0.209319 | 0.000485 |

开发门通过。候选身份如下：

- candidate：`region_resource_a2_confidence_knn_shadow_v5`
- model version：`d4-region-resource-v4-actor-knn-confidence-v5`
- manifest content SHA-256：`83192d4f96d7dd2c64ffd8f9b5c7c11a70c8c24a90934a0dfea12fe397c12c52`
- manifest file SHA-256：`caa774143db4a9c797e2a4ddff42d8f4cbc437471fe95926270f9bdec93b9459`
- calibration state SHA-256：`d8bd543759f6e52eb62585c1bd8aa67e59e718e7b548d38cc9dd5c690a5612a3`
- calibration summary SHA-256：`7f0047f72ebeea0358c127af5fe3dabe0c7f886bee48ff94b7d92b12b3259c60`
- builder source SHA-256：`77e91e06712013e6c1195c40f72b9a941d8396aa4594b52bd7d839276b57e1e0`
- v4 tree SHA-256：`2afd692874b91a23a5525448a0c5af98f3c2d96f0b12cebbf81a570d58d500d0`
- v3 registry tree SHA-256：`07c770b05ffc70f190cd8b45d762d579857747e0efb12b472a2354ee5aeaa93a`

## 独立性诊断

诊断在 TRAIN 定义的标准化 latent 空间执行，不改变模型、阈值或候选选择。原始图键仅
包含冻结 actor 可见张量及其 shape/dtype，不含 seed、样本身份或标签。VALIDATION
诊断拟合计数为 0，TEST 和正式 holdout payload 读取为 0。

| 诊断项 | 数量 |
| --- | ---: |
| VALIDATION 记录 | 75 |
| 原始图键完全重合 | 42 |
| latent 完全重合 | 42 |
| 原始图键和 latent 同时重合 | 42 |
| 非完全重合且最近距离 `<1e-3` | 20 |
| 最近距离 `[1e-3,0.1)` | 10 |
| 最近距离 `>=0.1` | 3 |
| 最近 TRAIN 标签一致 | 75 |
| 最近 TRAIN 标签不一致 | 0 |
| VALIDATION 正类完全重合 | 12/13 |

最近距离 P50、P90 和 P95 分别为 0、0.0123058 和 0.0940144。42/75 完全重合，
72/75 距离小于 0.1，最近邻标签 75/75 一致。该 VALIDATION 不能宣称为独立未见分布，
也不能用于证明泛化。

## D6 最终审计

D6 使用固定外部哈希独立核验候选四个 artifact、v4 基线、v3 registry 树、数据用途和
全部 false 权限。原 TRAIN/VALIDATION 开发门可复现，候选状态与独立重建的最大数值差
不超过 `1e-12`。

- TRAIN 全库存 self-match：350/350；
- raw observable key 留组：recall 0.965517、specificity 0.958904、
  Brier 0.037610440；
- latent exact key 留组：recall 0.965517、specificity 0.958904、
  Brier 0.037610440；
- validation exact overlap：42/75；
- 去除 exact overlap 后：33 条记录，其中正类 1 条，独立 recall 与 margin unavailable。

该审计证明 artifact 和同源开发门可复现，不证明来源独立泛化。

## 安全边界

v5 没有注册摘要。默认 loader 返回 `v5_candidate_unregistered`。只有显式
`offline_development` 上下文可以检查制品和读取校准状态。候选保持：

- `development_only=true`
- `shadow_only=true`
- `admission_closed=true`
- `rule_fallback_required=true`
- `independence_evidence_available=false`
- `generalization_evidence_available=false`
- 所有生产、D3 和 D7 权限为 false

固定 0.60 门、确定性投影、备用资源、版本、联盟和权限门没有变化。v4 候选、v3 registry
和 D6 审计制品未修改。

## 验证

2026-07-29 v5 定向测试 10/10 通过。测试覆盖数据用途、固定门、召回和裕量、重合与最近
距离诊断、虚假泛化声明同步重签、普通 artifact 篡改、同步重签固定门、未注册加载、
失败关闭回执以及 v4/v3 不变性。D4 全量测试 835/835 通过；唯一警告来自环境中的
Matplotlib 多版本，导致 `Axes3D` 不可用，与本次 v5 逻辑无关。三个修改或新增 Python
文件均通过 `py_compile`，owned paths 通过 `git diff --check`。

## 限制

TRAIN Brier 为 0，说明固定近邻库存对训练 latent 形成精确记忆。VALIDATION 的重合比例
和最近邻标签一致性进一步限制了证据等级。D6 已完成当前 v5 制品的独立只读审计；当前
没有来源独立扰动集、正式 holdout、runtime preflight、D3 successor、D7/物理窗口或
收益证据。

下一步先冻结来源独立的 development 扰动输入，再由 D6 对新输入执行独立只读审计并检查
召回、特异度和裕量。完成前不登记、不运行正式 holdout、不授予运行权限。
