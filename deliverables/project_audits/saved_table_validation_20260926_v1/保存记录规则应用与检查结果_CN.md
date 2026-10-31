# 保存记录规则应用与检查结果

检查日期：2026年9月26日。

本批将上一轮新增的记录检查用于6份已经登记的CSV文件，覆盖双光电最终表及逐圈表、搜索结果表、中心误差结果表。只检查字段、完整键、空值、分组数量和文件是否改变，不重新评分，不计算精度或覆盖度，也不改写源文件。

## 一、结果

四组来源合计3615条保存记录通过本次规则检查。未发现完整键重复、必查字段缺失、未声明的数值空值或非有限数值；行数、配置组数和组内不同种子数均与已登记数量一致。

| 来源 | 文件数 | 记录行数 | 配置组数 | 每组不同种子数 | 允许为空的字段单元格 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 双光电最终结果表 | 1 | 270 | 54 | 5 | 0 |
| 双光电逐圈表 | 3 | 2340 | 54 | 5 | 540 |
| 搜索结果表 | 1 | 45 | 9 | 5 | 0 |
| 中心误差结果表 | 1 | 960 | 96 | 10 | 480 |

3615是检查的记录行数，不能写成3615次独立实验。双光电最终表与逐圈表含同批次结果的不同表达，同一种子也会在不同方法和条件中重复出现。两类双光电表各包含30个不同种子编号，搜索表为5个，中心误差表为10个；编号数量本身也不能证明样本独立。

本批源文件为：

- [双光电最终表](../../../research_modules/independent_experiments/dual_optical_online_benchmark/outputs/report_replay_20260819_v2/combined_final_case_metrics.csv)：270行。
- [理想单站条件逐圈表](../../../research_modules/independent_experiments/dual_optical_online_benchmark/outputs/report_replay_20260819_v2/oracle_360/round_metrics.csv)：180行。
- [360度逐圈表](../../../research_modules/independent_experiments/dual_optical_online_benchmark/outputs/report_replay_20260819_v2/continuous_360/round_metrics.csv)：720行。
- [180度派生逐圈表](../../../research_modules/independent_experiments/dual_optical_online_benchmark/outputs/report_replay_20260819_v2/s180_derived/round_metrics.csv)：1440行。
- [搜索结果表](../../../research_modules/independent_experiments/center_terminal_cv_campaign/outputs/offline_search_100pct_cues_20260819/matrix.csv)：45行。
- [中心误差结果表](../../../research_modules/independent_experiments/center_terminal_cv_campaign/outputs/center_handover_sensor_error_20260820/per_run_metrics.csv)：960行。

## 二、完整键如何确定

| 来源 | 判定一条记录是否重复的字段 | 分组方式 |
| --- | --- | --- |
| 双光电最终表 | 扫描配置、目标数、干扰条件、方法、种子 | 前四项组成配置组；同组同种子只允许一条最终记录 |
| 双光电逐圈表 | 最终表五项字段加圈号 | 同组同种子可以有多圈；同圈不能重复 |
| 搜索结果表 | 场景编号、位置误差参数、种子 | 前两项组成配置组 |
| 中心误差结果表 | 目标数、交接模式、姿态条件、导航条件、检测条件、方法、种子 | 除种子外的六项组成配置组 |

字段名、数值字段清单及预期数量保存在[本批配置](../tools/saved_table_records_20260926_spec.json)。这些规则依据此前保存的分组登记和当前文件结构制定，不是运行时自行猜测。它们仅适用于列出的来源，新批次增加方法、重复运行编号或其他条件时，需要另行核对完整键。

键按CSV原有字符串读取，不自动把不同写法合并；本批没有将“20”和“20.0”等字符串作数值归一化。非键文本字段及布尔字段的内容没有在本次作语义校验，未作类型检查的列已列入机器记录的unchecked_column_types。

## 三、空值如何处理

本次逐行登记1020处允许的空值，原表中的空白均未替换。

| 字段 | 空值数量 | 处理方式 |
| --- | ---: | --- |
| 双光电逐圈表association_precision | 540 | 沿用不可计算时可为空的记录方式。三个文件分别为60、240、240处；保留空白，不按零参与任何新计算。 |
| 中心误差表final_hint_validation_rate | 480 | 作为可选线索校验率字段允许为空。只登记缺失，不把空白解释为校验失败或零分。 |

具体文件、数据行号、字段和完整键见[空值位置表](NULL_FIELD_LOCATIONS.csv)。CSV行号标识为data_row，从表头后的第一条数据记录开始计数。

“符合可空规则”只说明这种缺失被明确允许，不证明每一处空值的生成原因均已核实。此前中心误差表以零表示无输出的既有处理没有改变，单站零分母的旧处理也没有在本次修复。本批不据此调整任何平均值或结论。

## 四、校验和复查入口

| 材料 | 用途 |
| --- | --- |
| [VALIDATION_RECORD.json](VALIDATION_RECORD.json) | 四组来源的规则、检查状态、缺失计数、种子数量及脚本指纹 |
| [GROUP_RECORD_COUNTS.csv](GROUP_RECORD_COUNTS.csv) | 按配置分别列出记录行数和不同种子数 |
| [FILE_HASH_CHECKS.csv](FILE_HASH_CHECKS.csv) | 六份源表检查前后的SHA-256，全部一致 |
| [TESTS_AND_PRESERVATION.json](TESTS_AND_PRESERVATION.json) | 普通工具回归、历史代码及汇报文件保护检查 |

新增15项批次检查器测试，连同已有87项，共102项普通工具测试通过。三个历史统计入口和8份汇报文件的指纹与此前保存值一致，六份源表也在检查结束后再次核对。没有执行任何研究模块测试、训练、仿真或原始标签评分。

复查命令如下。输出必须使用新目录；下面的v2仅为下次复查目录示例，本批没有创建它。

```bash
python3 -B deliverables/project_audits/tools/audit_saved_table_records.py \
  --root /home/linux/Documents/MSM \
  --spec deliverables/project_audits/tools/saved_table_records_20260926_spec.json \
  --output-dir deliverables/project_audits/saved_table_validation_20260926_v2
```

同一规则再次通过不代表输入仍是同一版本，需另与本批文件哈希对照。检查前后哈希一致仅证明本次读检期间文件未变，不证明历史实验执行源码齐全或所有结果可以复现。

## 五、待办状态

A07中“为选定来源配置规则并用实际文件检查”的工作已完成，原实验汇总函数的边界问题仍未修改，因此A07整体保持部分完成。本批6份表不再重复作为配置待办，新来源需单独登记。

最新[待办表](NEXT_ACTIONS.csv)继续保留缺失归档、历史执行源码和环境证据等事项。450组完整记录仍未定位，原Goal的完成分类不变。本批没有提交、推送或删除文件。
