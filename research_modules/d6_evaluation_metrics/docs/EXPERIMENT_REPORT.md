# D6 正式实验矩阵准入预检报告

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
