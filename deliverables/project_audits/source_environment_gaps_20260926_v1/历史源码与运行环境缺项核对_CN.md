# 历史源码与运行环境缺项核对

核查日期：2026年9月26日。

本批接续A02、A03和A12，只检查三个已登记批次的源码索引、静态依赖、环境记录及搜索逐次清单。没有重新检查结果表，没有导入研究模块、安装依赖、运行模型或仿真，也没有扩大到全盘、其他主机和私人会话目录。

## 一、本次结论

没有找到新的历史源码副本或完整环境导出，原样复现条件仍未齐备。本批的进展是把“版本和环境不完整”细化为具体文件、缺少的版本声明及可接受的补证材料，见[材料清单](MATERIAL_REQUESTS.csv)。

| 批次 | 源码已有依据 | 尚缺的源码依据 | 环境已有记录 | 仍未解决的问题 |
| --- | --- | --- | --- | --- |
| 双光电报告回放 | 5份源码有历史文件哈希；此前已保存副本 | 46条静态候选记录中，另外41条只有与基线相同的证据 | Python 3.12.3；NumPy 2.5.0、SciPy 1.17.1、Torch 2.11.0+cu128 | 未定位完整历史环境导出；Matplotlib、scikit-learn等候选库的本批版本未记录，实际使用范围也需区分 |
| 中心误差矩阵 | 11份源码快照有历史哈希 | 另外3个包初始化文件未纳入原源码哈希索引 | Python 3.12.3及上述三个库，另有Matplotlib 3.10.9；环境摘要有哈希 | 四个包的版本摘要不是完整环境锁定；包的传递依赖及安装来源仍未完整记录 |
| 搜索离线矩阵 | 基线提交及45份逐次参数配置可查 | 11条静态候选记录均缺本批历史文件哈希，3个文件尤其需要补证 | 所查总清单及45份逐次清单中未定位Python及依赖版本字段 | 执行源码与环境都不足以按原状态还原 |

71条“批次—源码”记录中，16条有原批次文件哈希，55条仍缺这种依据。这不是55个独立文件丢失，也不是55个运行必需文件：不同批次可能引用同一路径，静态检查还会纳入没有实际执行的可选路径。完整名单见[SOURCE_GAPS.csv](SOURCE_GAPS.csv)。

## 二、源码缺项

### 1. 双光电批次

此前登记的41条未单独冻结候选源码，当前内容仍与上一批核查一致。原清单明确记录工作区有未提交修改，因此“当前与基线相同”不能单独证明原运行使用的也是该文件。

所需材料是与原批次对应的源码快照或当时文件指纹，以及能够说明实际使用范围的记录。新建一份当前源码压缩包只能保全现状，不能补成历史证明。

### 2. 中心误差批次

原11份源码快照未单列的三个文件为：

- `research_modules/independent_experiments/center_terminal_cv_campaign/__init__.py`；
- `research_modules/independent_experiments/center_terminal_cv_campaign/common/__init__.py`；
- `research_modules/independent_experiments/center_terminal_cv_campaign/exp_center_handover/__init__.py`。

当前文件分别为79、678、315字节，不能因其名称是初始化文件就视为空文件。三者与基线相同，但本批没有新增与原执行状态对应的哈希证明。原工作区补丁仅列出三份已跟踪源码的修改，不能自动用来证明所有未列文件和未跟踪文件的状态。

### 3. 搜索批次

优先需要核对`exp_search/run_offline_matrix.py`、`exp_search/offline_replay.py`和`common/scenario.py`。前两份不在原记录的基线提交中，第三份当前内容与该基线不同；另有8条静态候选仅与基线相同。

本批定向检查45份`evidence_manifest.json`，均保存配置，但在所查源码及环境字段中没有新增版本依据。检查的字段范围和逐文件结果见[SEARCH_METADATA_CHECKS.json](SEARCH_METADATA_CHECKS.json)。这只能说明这些清单未提供所需证明，不代表外部副本不存在。中心误差批次保存的同名源码也不能自动作为搜索批次的执行源码证明。

## 三、环境记录的含义

### 1. 有版本摘要，不等于完整环境已经锁定

中心清单的`runtime.dependency_lock`指向[environment.json](../../../research_modules/independent_experiments/center_terminal_cv_campaign/outputs/center_handover_sensor_error_20260820/environment.json)，本批确认其SHA-256与原声明一致。文件实际包含Python、平台、四个直接库版本和设备信息，没有完整安装包清单及包文件校验值。

因此，该文件可证明保存过这份环境摘要，不能仅凭字段名将它视为完整锁定文件。文件哈希约束的是JSON摘要本身，不是所有已安装软件包。

### 2. 有GPU设备信息，不等于该批模型在GPU上运行

同一环境摘要同时保存GPU型号和`gnn_device: cpu`，并写明`airsim_used: false`。按该批保存声明，应记为CPU上的离线试验，不能因为存在GPU型号便解释为GPU执行或新AirSim运行。本批没有运行程序来重新验证设备选择。

### 3. 静态出现的库，不一定在该次运行中使用

本次将已有静态导入登记与历史版本记录对应，形成13条“批次—外部库”记录，其中7条有版本声明、6条未在所查材料中找到版本。逐项出处见[DEPENDENCY_EVIDENCE.csv](DEPENDENCY_EVIDENCE.csv)。

双光电的scikit-learn、搜索代码中的AirSim等，只能先列为静态候选，不能凭文件中的导入语句认定它们在本次试验中执行。也不能从输入最初由AirSim生成，推定后续离线处理环境的AirSim版本。

本批只在三个确定的输出根目录内，按环境、依赖、锁定文件和源码索引名称查找，定位6份候选材料，见[CHECKED_METADATA_FILES.csv](CHECKED_METADATA_FILES.csv)。没有发现完整环境导出，不使用当前安装环境或相邻批次版本填补历史空缺。

## 四、补证材料及停止条件

[MATERIAL_REQUESTS.csv](MATERIAL_REQUESTS.csv)列出六项具体材料，分别覆盖三个批次的源码与环境。优先联系原资料保存位置或维护人，取得与原运行对应的副本；随后仅按批次标识和已有哈希定向核对。

没有新材料时，本轮列出的源码与环境缺项保持开放，不重复扫描这三个目录，不重复生成当前环境导出来充当历史记录。450组原始载荷仍需其他主机或外部备份线索，本批未开展新的归档查找。

A07的6份结果表规则验证和A11的模块文档入口同步保持原状态，不因本次缺项检查重新列为待办。原Goal完成分类未变。最新进展登记于[NEXT_ACTIONS.csv](NEXT_ACTIONS.csv)。

## 五、检查范围与保存情况

本批重新核对71条静态源码登记，其当前指纹均与上次一致；所查原文件在本次读取前后保持不变。机器结果见[AUDIT_RESULTS.json](AUDIT_RESULTS.json)和[INPUT_FINGERPRINTS.json](INPUT_FINGERPRINTS.json)，辅助脚本测试及保护文件检查见[VALIDATION_RECORD.json](VALIDATION_RECORD.json)。

机器记录中的passed仅表示本次限定范围核查正常完成，不能解释为源码齐全、环境已还原或原Goal通过验收。本批没有复制模型权重、读取原始标签、提交、推送或删除文件。
