# D6 正式实验矩阵准入预检报告

## D5 G1 预准入外部审计（2026-07-26）

### 输入

本次只读审计使用冻结的 99fa 候选。模型 manifest/weights SHA-256 为
`c4284b24...674` / `99fa4428...d4cd`。held-out 报告文件/内容 SHA-256 为
`765d39a5...320a` / `bada1803...067a`；paired-shadow 使用与该权重一致的 final 报告，文件/
内容 SHA-256 为 `cc960206...bf23` / `53bdc658...57a0`。绑定另一模型的 `e39a54d_v2` 未进入
输入清单。

审计没有启动 AirSim、三维质点 episode 或新多 seed 实验。它只验证已有 20-seed 实物。输入
覆盖 seed `1000-1019`、900 个 episode、45 个场景规模单元、13,344 个匿名局部航迹节点和
74,024 条候选边。

### 结果

形式化目录通过。held-out 和 paired-shadow 均绑定 99fa weights，训练数据的 dataset
manifest、split 和 training set SHA-256 一致。在线真值字段、`global_track_id` 改写和同相机
互斥违规均为 0。这些字段 availability 为 true，零值有实际证据。

整体结果为 `fail_closed`，包含四个稳定阻断项：

1. `implementation_lineage_mismatch`。held-out 与 paired 报告联合形成的九文件实现摘要为
   `81968e0d...066e7f`，当前 D5 运行实现摘要为 `ff8c744e...8a1b7`。
   `tracklet_model_bundle.py` 的证据哈希为 `b92037bb...e8cc`，当前哈希为
   `174b18b9...b0ff`。没有可验证等价桥接。
2. `synthetic_single_feature_shortcut`。检测框尺度变化率差的最高单特征 AUC 为
   `0.997340`，超过 0.98 门限。
3. `robustness_threshold_not_met.edge_f1`。遮挡重现代理下最低边 F1 为 `0.563264`，低于
   0.9。
4. `robustness_threshold_not_met.cluster_f1`。同一 profile 的最低簇 F1 为 `0.572845`，低于
   0.9。

五类扰动均使用冻结的 post-gate 候选图，`candidate_graph_rebuilt=false`。该限制已进入结构化
结果，不能把名义 held-out/paired 满分解释为重新投影和重新构图后的外部泛化能力。

### 制品与验证

结果目录为 `outputs/d5_g1_external_audit_99fa4428_20260726/`，包含 JSON、证据索引 CSV、中文
Markdown 和 `SHA256SUMS`。三项内容文件校验通过。专项测试 `13 passed`，覆盖正例、缺文件、
文件篡改、内容篡改、跨模型、跨数据集、实现变化、严格布尔/整数、阈值边界、unavailable、
CLI、内容哈希和重复运行确定性。D6 全量为 `943 passed, 1 warning in 80.56s`；warning 是既有
Matplotlib `Axes3D` 环境提示，不影响本次二维报告和哈希判定。

D6 没有授予模型晋级、G1 辅助、控制权或默认路径变更。当前证据不能被 D5 装配为正向 admission。
下一次复核需要当前实现上的新 held-out/paired 实物，并处理合成单特征捷径和扰动最低性能。

## 结论

2026-07-25，D6 对 R0、G1、A1、A2、A3、C1、F1 正式实验矩阵执行静态
`post_run` 准入预检。预检读取实际 `ExperimentMatrixPlan.cells()`，没有启动 episode。

当前 expected inventory 为 5700 个 cell。清单本身通过唯一性和范围检查，训练 seed 与评估
seed 没有交集。运行制品尚未形成，通过 cell 为 0，结论为 `fail_closed`。

该结果通过实际 `ExperimentMatrixPlan` 对象调用 D6 接口获得。CLI 未提供 `--inventory` 时也会
失败关闭，但 expected=0 只表示缺少 expected inventory，不代表正式矩阵规模。

## 清单

当前计划包含九类场景、五档规模和 seeds 1000-1019。R0、G1、A1、A2、A3、C1 覆盖九类
场景，共 5400 个 cell。F1 只覆盖中心失效、二级失效和高威胁多对一场景，共 300 个 cell。
合计 5700。

预检不使用固定的 6300。F1 场景范围来自 main 的 cell 枚举。专项测试把 F1 增加到四个场景，
预期数量随清单变为 5800。

## 模型制品

| 模型 | manifest | weights | SHA-256 | assist 声明 |
| --- | --- | --- | --- | --- |
| D3 分配模型 | 存在 | 存在 | 匹配 | 未授权 |
| D4 区域模型 | 存在 | 存在 | 匹配 | 未授权 |
| D5 图模型 | 存在 | 存在 | 匹配 | 未授权 |
| D5 主动视觉模型 | 存在 | 存在 | 匹配 | 未授权 |

文件完整性通过不能替代模型准入。当前四个模型分别处于开发、影子或未完成保留 seed 评估状态。
G1、A1、A2、A3、C1 和 F1 不能在正式矩阵中声明 assist 后静默回退规则路径。

## 缺失证据

当前没有正式 `experiment_matrix_manifest.json`、运行 cell CSV、D6 逐 seed CSV 和聚合 JSON。
逐 cell 的在线真值、有限状态、D2 身份交换与五米物理指标无法评估。正式中文报告、动画和运行
模型清单也未形成。

缺失范围压缩为四条记录：5400 个基础变体 cell 和 300 个 F1 cell 分别缺运行记录与 D6 离线
证据。完整 JSON 和 CSV 仍保留 5700 个 cell 的独立状态。

## 制品

当前预检制品位于
`../outputs/formal_matrix_admission_precheck_20260725_current/`：

- `experiment_matrix_admission_precheck.json`
- `experiment_matrix_admission_cells.csv`
- `EXPERIMENT_MATRIX_ADMISSION_PRECHECK_CN.md`
- `SHA256SUMS`

该结果只说明正式矩阵尚未具备准入条件，不构成算法性能比较，也不代表物理拦截结果。
专项测试为 `9 passed`，D6 全量为 `889 passed, 1 warning`；既有 main 矩阵合同测试为
`7 passed, 1 warning`。当前 JSON、CSV 和中文 Markdown 的 SHA-256 校验均通过。

## R0 后验代次定向复核

clean 提交 `2c7b425d076899e1c54a3d87d6ef23a613ba6e3a` 的 900-cell R0 已完成结构性
执行，原 D6 结果为 895 个 clean-formal 和 5 个 delayed-noisy 后验代次失败。逐轨审计确认
这 5 项的最终状态、协方差和有效时刻已经变化，原运行时将其错误登记为一次 no-op skip。
D6 v10 保持失败关闭，未用扩展计数式放行，并已提交为 `8e955f3`。

main 修复 finalization 后，在 dirty 工作树定向重跑原 5 项。D6 合并结果为：

| 场景与 seed | D1 final / D2 consumed | consume / publication / merge | skip | pending | contract |
| --- | --- | --- | ---: | :---: | --- |
| delayed_noisy 20v20 seed 1009 | 27 / 27 | 7 / 7 / 20 | 0 | empty | verified |
| delayed_noisy 5v5 seed 1000 | 13 / 13 | 6 / 6 / 7 | 0 | empty | verified |
| delayed_noisy 5v5 seed 1005 | 9 / 9 | 5 / 5 / 4 | 0 | empty | verified |
| delayed_noisy 5v5 seed 1008 | 13 / 13 | 5 / 5 / 8 | 0 | empty | verified |
| delayed_noisy 5v5 seed 1018 | 14 / 14 | 6 / 6 / 8 | 0 | empty | verified |

五项均由 D2 实际消费最终后验，generation integrity reasons 为空。该批次的
`repository_dirty=true`，因此正式验收资格仍为 0/5，只能作为修复后的开发态定向证据。
旧 clean 895 项与新 dirty 5 项不能拼接。runtime 修复已形成 clean source commit
`98d01bf`。完整 R0 formal rerun 已在后继 clean source `1e5ed8d` 上启动，当前完成
135/900，尚未形成整体结果。D6 仍保持旧正式结论 895/900。
详细清单和判定边界见 `FORMAL_R0_POSTERIOR_SKIP_AUDIT_CN.md`。

## Clean-source 正式增量复核

执行计划 SHA-256 为
`8804ecb4dd0513db55906905f031832711012974fc911546df40e09fb297d373`。shard 0、5、9
均完成 45/45。D6 定向结果覆盖三个原失败 cell，3/3 均为
`clean_formal_experiment_matrix`，基础与矩阵 formal eligibility 均为 true，generation
contract 为 `verified`，episode/matrix/variant failure reasons 全为空。

三个 cell 分别为 5v5 seed 1000、1005 和 20v20 seed 1009。D1/D2 最终代次分别为
13/13、9/9、27/27；skip 均为 0，pending 均为空。该证据不能外推到其余已执行 cell。
新批次剩余 765 个 cell，原失败项 5v5 seed 1008、1018 仍开放。磁盘可用空间仅比 20 GiB
下限多约 64 MB。完整批次结束前，旧正式结论保持 895/900。

## 学习作用域审计合同验证

2026-07-26 完成 D6 学习作用域审计器的合同测试。测试使用临时构造且完整哈希绑定的
G1/R0 单 cell 制品，不是 d59352b 的正式运行结果，也不是 AirSim 或物理拦截证据。

完整 G1 与唯一 R0 配对时，审计可验证正候选边上的实际模型评分、零 fallback、在线真值使用
为 0、物理结果可用和两项必选指标非退化，同时明确
`model_promotion.allowed=false`。其余 35 项负向测试覆盖：

1. 缺 R0 时配对 availability 为 unavailable，`non_degraded=None`；
2. shadow/fallback 时实际采用状态为 unavailable，不能进入比较；
3. bundle 文件树被篡改时在准入前阻断；
4. 预检设备与预期不一致时阻断；
5. 物理结果缺失时不以 0 补齐，配对非退化保持空值；
6. scope merge 未完成时阻断整个作用域；
7. execution plan 内容或摘要、merge checksum、progress/checkpoint、episode tree 被篡改时
   阻断；
8. R0 comparison key 重复，或来源提交、父计划、外生配置、随机计划不一致时阻断；
9. D3、D4、D5 主动视觉仅加载 bundle、处于 shadow 或实际采用为 0 时阻断；
10. C1/F1 任一必要组件未采用，以及 D5 图模型候选边为 0 时阻断。

定向测试结果为 `36 passed, 1 warning in 2.35s`，D6 全量回归为
`930 passed, 1 warning in 78.98s`。warning 为既有 Matplotlib `Axes3D` 环境提示。正式审计
仍需 main 提供学习 execution plan、完整 merge、同键 R0 计划与 merge、实际绑定 bundle
根目录，以及可选预期设备。上述实物输入缺失前，D6 不形成学习采用率、R0 非退化或晋级结论。
