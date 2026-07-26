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
