# D4 v5 来源独立外部评价审计

## 结论

D6 于 2026-07-29 对冻结 D4 v4 actor 与 v5 置信校准器完成只读外部评价。输入为 M16N20、32 个 episode、63 帧，seed 为 3008-3039。
冻结 actor 在 63 帧上没有输出与规则安全正动作签名一致的可执行动作。actor-derived positive 分母为 0，正类召回不可评价。63 个负类评分均为 0，固定 0.60 门通过数为 0，负类误接收为 0。
该结果支持来源独立负类拒绝，不支持正类泛化或正式准入。候选保持 `unregistered`、`admission_closed`、`rule_fallback_required`，生产、D3 和 D7 权限继续关闭。

## 数据边界

| 项目 | 结果 |
| --- | ---: |
| episode | 32 |
| 帧 | 63 |
| 目标/资源 | 16/20 |
| 独立评价 seed | 3008-3039 |
| D6 读取 external train/validation/test | 43/10/10 |
| main 此前读取 external test | 10 |
| 正式 holdout seed 1000-1019 读取 | 0 |
| 模型拟合/门限调整/split 调整 | 0/0/0 |

external test 的 10 帧属于来源独立开发数据的 test 子集。它不是正式 holdout。D6 没有读取 1000-1019，也没有运行 runtime preflight、D3 successor 或 D7 权限测试。

## 哈希复核

| 制品 | SHA-256 |
| --- | --- |
| source manifest 文件 | `af12051917cfe9eedfc8587c953599112db62858e4b01820a16ddd5b0a10231d` |
| labeled dataset | `ed2fd4b1a4d50ec80e5abdaa35a1470cec03d419665ae0e08b7c4339e9b8887e` |
| labeled split | `cdaa40241195516eb1679f6ed0a8179f3d2365c9768f9ef9a44b6f85fabcefb6` |
| source artifact 文件 | `ccf327717a293f63b5655e978202ff720f20c74bfd8ae401f2233cc590bb753a` |
| external evidence 内容 | `1d9cfa165f4fe24fa3881d66b73c0ed14f3902dd9f901c29d29fa7d6dae60191` |
| label audit 内容 | `8798bd28037a7c52abc972e9a13551525e68eeb590d49e497b0db6cd31800336` |
| v4 actor tree | `2afd692874b91a23a5525448a0c5af98f3c2d96f0b12cebbf81a570d58d500d0` |
| v4 actor state | `33a28060f11277a549b90d2f2f365962fec057b2bfb50a70ab5a422059cb9fe5` |
| v5 calibrator tree | `632f066fcad363531762e6b7a1ef0f21c03b7b0d0aa3b4cd39a16e4fbbf7c273` |
| v5 calibrator state | `d8bd543759f6e52eb62585c1bd8aa67e59e718e7b548d38cc9dd5c690a5612a3` |

全部实际摘要与调用方冻结摘要一致。source derivation、evidence、export summary、labeled manifest、v4 和 v5 绑定关系也通过交叉核对。
审计开始前和全部加载、评分及可观测键重合计算完成后，D6 分别重算 source、labeled export、labeled dataset、v4 actor 和 v5 calibrator 完整文件树摘要。before/after 逐项一致，`input_mutation_count=0`。

## 来源独立性

| 库存 | 帧 | 唯一可观测键 |
| --- | ---: | ---: |
| 旧 v4 TRAIN+VALIDATION | 425 | 251 |
| 新外部评价 | 63 | 41 |
| exact key 重合 | - | 0 |

可观测键只包含图结构、节点特征和边特征的形状、类型与数值，不包含 seed、来源、actor 或目标身份。

## 分片结果

| split | 样本 | 规则安全正动作 | actor-derived positive | score 范围 | 0.60 通过 | 负类误接收 | 规则回退 |
| --- | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| train | 43 | 1 | 0 | 0.000000-0.000000 | 0 | 0 | 43 |
| validation | 10 | 1 | 0 | 0.000000-0.000000 | 0 | 0 | 10 |
| test | 10 | 0 | 0 | 0.000000-0.000000 | 0 | 0 | 10 |

train 和 validation 各有 1 个规则安全正动作，test 没有。规则层存在安全动作只说明标签库有可执行差异，不能替代冻结 actor 的输出。
聚合负类特异度为 1.000000。正类召回保持 `unavailable`，不以 0 回填。

## 准入判断

1. 来源、标签、候选和分片哈希完整，seed 类别互不相交。
2. 新旧 exact observable key 重合为 0，外部数据具有来源独立性。
3. 冻结候选完成负类拒绝，但 actor-derived positive 分母为 0。
4. 正类泛化、正式 holdout 和运行收益证据仍不可用。
5. 候选不注册、不准入，所有样本继续使用规则回退。

## 限制

- 本轮是离线外部评价，不是 AirSim、实飞或生产运行结果。
- 未运行正式 holdout、运行时预检、D3 后继计划或 D7 权限测试。
- 结果不能用于调整候选、门限、split 或正类生成规则。
