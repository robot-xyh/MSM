# 当前工作进展与证据审计

审计日期：2026年9月25日。审计对象：`/home/linux/Documents/MSM`及此前列出的六个同级目录。

## 一、总体判断

当前项目已形成研究软件、分项仿真与离线试验、报告及专利草稿，工作重点已经从搭建框架转向独立试验和汇报材料整理。但尚未形成一套版本一致、证据完整、可整体复现的最终交付基线，不能把分项报告完成等同于整个项目完成。

最近的建议书精简版已经生成。此前讨论的六个同级目录只完成了用途核查，没有清理或迁移。它们包含正式来源数据、审计材料和未纳入Git管理的模型、实验记录，不能按普通临时目录处理。

本次完成的是仓库状态、文档结构、证据文件和版本关系审计。没有重新运行AirSim、训练模型、复跑业务算法或开展实物验证，也没有修改原有报告、代码和历史数据。历史测试通过数不作为本次工作树的测试结果。

## 二、需要先处理的问题

### 1. 本地工作成果尚未形成完整提交

审计开始时，工作树有41个已跟踪文件发生修改，另有1215个未跟踪条目，暂存区为空。未跟踪条目包含四个嵌套Git仓库，不能把这一数字理解为全部物理文件数；本次新增的审计材料不计入上述数字。

改动不只是排版，还包括独立实验代码、测试、报告生成器、图像和证据清单。以下文件当时均未跟踪：

- `research_modules/independent_experiments/dual_optical_online_benchmark/report_matrix_replay.py`
- `research_modules/independent_experiments/center_terminal_cv_campaign/exp_center_handover/run_error_matrix.py`
- `research_modules/independent_experiments/center_terminal_cv_campaign/exp_search/offline_replay.py`
- `deliverables/patents/tools/patent_docx_omml.py`
- `deliverables/project_proposals/建议书模版_智能化火指控补充版.docx`

当前分支为`exp/d5-ideal-20target-registration`，提交为`c0a76f61d9e0cbd5b03782fd612f711d389eac10`，最近提交日期为8月29日。与本机保存的远端跟踪引用相比，领先和落后均为0。本次没有连接远端刷新引用，因此不能据此保证服务器此刻未变化，更不能据此认为本地未提交内容已被备份。

### 2. 同名Word和Markdown存在版本差异

中心配准Word结果部分已经改为“3.1 强干扰组合工况”和“3.2 结论”，同名Markdown仍保留原有六个结果小节，包括正常条件、完整误差矩阵和接口试验。这是实际章节差异，不是显示问题。

另一个同名文档对`MULTIMODAL_FEATURE_FUSION_AND_TRACK_ASSOCIATION_SOLUTION_CN`也存在多处章节标题差异。本次未判定哪一版应覆盖另一版。

双光电、协同搜索、末端配准三份主报告的Markdown章节标题均可在对应Word中找到，但标题一致不能证明每段文字、表格和图片完全一致。

应明确区分“汇报裁剪版”和“实验完整版”，或指定一份作为生成源。直接运行旧生成器可能覆盖已经人工修改的Word，暂不建议批量重新生成。

### 3. 总体进度记录与独立实验记录不是同一条证据链

`subagent_reviews/MAIN_IMPLEMENTATION_GAP_AUDIT.md`最新日期章节为8月10日。三维体系的进展汇总更新到8月7日，而独立实验README已经记录8月19日、20日的新工作。

因此，总体审计不能代表后续独立实验的全部进展；反过来，独立实验形成报告也不能自动关闭总体审计中的待完成事项。独立双光电README明确说明该试验不接入D1—D7主流程。

尤其需要区分两个“900”：学习数据生成目录的检查点记录`900/900、finalized`，正式规则矩阵在已查阅的进展报告中仍记为`450/900`。两者来源提交和用途不同，不能相互替代。

### 4. 部分历史证据的引用路径已经失效

正式规则矩阵历史报告引用的下列目录当前不存在：

```text
/tmp/msm-formal-r0-20260731-80e55eb/d6_strict_partial_450_b6289c5
```

仓库中的长期摘要目录`research_modules/d2_data_association/docs/formal_r0_identity_causal_pack_summary_20260731/`仍然存在。但摘要不等于全部原始输出。本次没有确认完整归档是否保存在其他位置，因此只能认定“原引用路径失效”，不能认定数据已经全部丢失，也不能认定该历史试验当前可直接复现。

### 5. 实验完成、诊断完成与独立验证需要分开统计

机间配准诊断清单明确记录`diagnostic_testset_tuning=true`、`independent_holdout_validation=false`。它包含36组参数在三个既有场景上的比较，不是108个独立场景验证。

搜索报告的45组是保存运动记录上的离线回放，不是45次新AirSim试验。中心配准的960条结果来自480个场景组合与两种方法，也不是960个独立随机种子。

这些材料有实际文件支撑，但不能统一写成同一种完成状态。尤其不能将理想输入诊断、已查看数据上的参数选择、独立保留测试和设备实测合并成一个完成率。

## 三、各项工作进展

| 工作范围 | 已核实的材料或记录 | 当前应采用的完成状态 |
| --- | --- | --- |
| D1—D7基础研究软件与三维集成框架 | 模块代码、README、PLAN、历史审计和测试记录存在 | 已有研究软件及历史验证记录；本次没有复跑全量回归，不作当前版本整体通过判断 |
| 三维体系原总体目标 | 8月7日进展报告仍列出未完成项；本次未找到足以改判为整体完成的最终验收证据 | 尚不能认定总体目标完成；历史进度数字须绑定原版本 |
| 双光电独立试验 | 权威复算目录有54组、每组5个场景，共270条最终结果；150项清单文件哈希一致 | 已形成可核验的离线结果与报告；没有因本次文件核验变为新的在线或实物验证 |
| 协同搜索独立试验 | 汇总CSV有45行，三个输入记录哈希一致 | 离线试验和报告已经形成；与新AirSim闭环试验分开统计 |
| 机间配准诊断 | 36组参数、108条场景参数结果、3条几何对照；三份输入清单共27项哈希一致 | 已完成保存数据上的诊断比较；没有形成独立留出验证 |
| 中心配准误差试验 | 960条逐组结果、96条汇总；模型、源码快照及环境清单等16项哈希一致 | 已形成可追溯的离线误差试验；报告版本尚待对齐 |
| 四份主要试验报告与方案模板 | Word存在，图片嵌入关系可解析；三份主报告标题与Markdown对应 | 文档已经形成；需完成版本确认和最终版式检查 |
| 三份科学问题报告 | Word及图像、生成工具存在 | 方案材料已形成，不能据此认定研究方案均已实现或验证 |
| 两份专利材料 | 两份Word、Markdown、图片和生成工具存在 | 草稿已形成；未核验申请受理、新颖性或授权状态 |
| 论文与外部仓库资料 | 两个翻译目录共有60篇译文；四个外部Git仓库存在 | 资料已整理；本次未逐篇核验译文忠实度，也未认定外部代码已集成 |
| 建议书精简 | 补充版Word存在，“智能化火指控研究”小节为一段，含两张嵌入图片 | 精简文件已生成，尚未纳入Git提交；本次未重新核验分页 |
| 六个同级目录整理 | 用途、占用、引用和工作区忽略文件已核查 | 只完成审计，没有清理、合并或迁移 |

以上各项不具有统一的工作量分母，不给出“项目完成百分之多少”的估计。

## 四、证据核验结果

### 4.1 四组主要实验材料

| 材料 | 实际核验内容 | 核验结果 | 本次未做 |
| --- | --- | --- | --- |
| `report_replay_20260819_v2` | 汇总行数、完整性清单、来源文件和源码哈希 | 270行，54组完整；150项哈希一致 | 没有重新计算算法结果；没有递归展开全部下级清单核验整个来源树 |
| `offline_search_100pct_cues_20260819` | 汇总行数及三份来源运动记录 | 45行；3项哈希一致 | 没有重新执行搜索回放；没有把运动外推当作新观测 |
| `terminal_gnn_diagnostic_selection_20260819_v2` | 参数与场景行数、三个场景输入清单、诊断标识 | 36/108/3行；27项哈希一致；独立验证标识为否 | 没有重新选参数、加载模型或重新评分 |
| `center_handover_sensor_error_20260820` | 逐组和汇总行数、模型文件、源码快照、环境文件 | 960/96行；16项哈希一致 | 没有重新推理或重跑接口试验 |

合计196项带路径与SHA-256的清单记录核验一致，未发现这部分记录缺失或内容变化。同一文件可被不同清单引用，196不是去重后的文件总数。文件哈希一致证明保存内容未变，不证明算法结论正确。

双光电复现清单实际记录了Python、NumPy、SciPy、PyTorch和AirSim来源版本。中心误差试验还保留了源码快照及环境文件。既有定位工具的自动评级仍提示部分环境信息缺失，存在对嵌套字段识别不完整的情况；本次以原清单人工复核结果为准，没有直接照抄工具的缺失项。

### 4.2 文档检查

本次检查了`deliverables/leadership_report/`、`deliverables/patents/`和`deliverables/project_proposals/`一级目录下26份Word：

- 26份均可打开为有效DOCX压缩包，CRC检查未发现错误。
- 内部附件引用未发现缺失。
- 其中19份存在同名Markdown，共检查141条行内图片引用，未发现路径缺失。
- 两份专利Word分别包含86个和83个原生Word数学对象，说明公式已经以可编辑对象保存，而非仅留下未转换的公式文本。
- 本次没有将全部文档渲染为页面，没有据此认定字体、公式外观、分页或图片清晰度全部合格。

部分Markdown仍直接引用被Git忽略的实验输出图片。本机能显示，不等于仅克隆Git仓库后也能显示。交付时需要一并保留图片与结果附件。

### 4.3 文件和磁盘状态

当前磁盘可用约30 GiB，使用率94%。本次读取到的目录占用约为：`research_modules` 63 GiB、`paper` 4.1 GiB、`deliverables` 376 MiB、`.git` 400 MiB。数值为当前机器上的磁盘占用，不是版本仓库中所有文件的逻辑大小。

`.gitignore`明确忽略`research_modules/**/outputs/`。普通提交和推送不会自动保存这些实验结果；备份与代码版本管理需要分别核查。本次没有检查外部备份系统，因此不作“没有其他备份”的断言。

四个外部仓库分别是YOPO、Fastlab_world_fly、ego-planner和ego-planner-swarm。它们是嵌套Git仓库，各自包含一个未跟踪压缩包。不能通过主仓库一次`git add`就假定其内部文件已经得到完整备份，也不建议未经比对直接删除压缩包。

## 五、六个同级目录的结论

| 目录 | 占用约 | 保留理由与当前状态 |
| --- | ---: | --- |
| `MSM-d5-training-clean` | 396 MiB | Git无普通未提交改动，但有32485个非缓存忽略文件，共184772746字节；主仓库对应相对路径均不存在，不能直接移除 |
| `MSM-source-audit-request-20260803` | 52 KiB | 审计输入及预检材料，仍有文档引用 |
| `MSM-source-audit-result-20260803-v3` | 24 KiB | 来源完整性审计材料；本次两项SHA256SUMS复核均通过 |
| `MSM-source-generation-output-64dfc08-20260803` | 340 MiB | 完整D5来源数据，审计记录覆盖104次实验 |
| `MSM-source-generation-output-6737b44-20260803` | 297 MiB | 包含完整D4来源及历史未完成运行，不能整目录删除 |
| `MSM-source-generation-output-e7c438c-20260802` | 1.4 GiB | 包含完整D3来源及历史未完成运行，不能整目录删除 |

“主仓库对应路径不存在”不是全盘查重结论。本次没有证明上述忽略文件在其他存储位置完全没有副本。

可以集中归档，但应保留各运行版本的目录边界，不能把失败运行的载荷拼接到已完成数据中。迁移还涉及绝对路径引用和Git工作区登记。归档方案尚未实施，也没有删除任何一个历史目录。

## 六、建议先完成的收尾工作

本次后续建议仅针对版本、证据和交付管理，不替代算法研发计划。

1. **保全本地状态。** 保存当前差异和未跟踪文件清单，核验实验输出与模型的独立备份位置。磁盘空间有限，不在同一分区盲目复制全部63 GiB研究目录。
2. **确认文档版本。** 对中心配准及多模态报告明确汇报版、完整版和生成源的关系，保留人工改稿，不直接运行生成器覆盖原件。
3. **建立当前交付索引。** 每份主报告绑定一个权威结果目录、输入清单、源码版本或源码快照、指标口径和证据类型。历史结果不与当前结果混合统计。
4. **核查历史归档位置。** 优先处理指向`/tmp`的失效引用。找到原始归档后先校验摘要，再更新索引；未找到时明确标记只能查阅摘要。
5. **分组固化版本。** 后续提交按独立实验代码与测试、报告与图片、专利工具、建议书及资料索引分组。嵌套仓库、大数据和压缩包单独处理，不直接全部加入主仓库。
6. **再决定目录迁移和清理。** 只有归档校验通过、引用关系有明确处理办法后，才移动工作区或清理旧输出；本次审计不等于删除授权。

## 七、本次新增材料与验证边界

新增内容均在`deliverables/project_audits/`，没有修改D1—D7文件、原有报告、实验输入或输出，没有提交和推送。

- 本报告：`20260925/当前工作进展与证据审计_CN.md`。
- 机器可读快照：`20260925/WORKSPACE_EVIDENCE_SNAPSHOT.json`，包含Git状态、26份Word的结构检查、19组文档对、四组实验目录核验及嵌套仓库版本。
- 元数据审计脚本：`tools/audit_workspace_metadata.py`。
- 脚本单元测试：`tools/test_audit_workspace_metadata.py`，本次4项通过。
- 当前跟踪文件的`git diff --check`通过。业务算法全量测试没有在本次重跑。

快照的Git状态记录发生在本次审计文件生成过程中，因此未跟踪条目总数包含部分审计文件；`untracked_entries_excluding_this_audit`字段用于与审计开始状态比较。

可使用以下命令重新做文件级核查，不会启动仿真或加载模型。应另取输出文件名，保留本次快照：

```bash
python3 deliverables/project_audits/tools/audit_workspace_metadata.py \
  --output /tmp/MSM-workspace-audit-new.json

python3 -m unittest discover \
  -s deliverables/project_audits/tools -p 'test_*.py' -v
```

本次没有逐行审查全部业务代码，没有重算所有历史实验，没有逐句校对论文翻译，没有核验专利法律状态，也没有验证实物能力。可以明确回答的是：分项研究和文档材料已经积累到可整理交付的阶段，但统一版本、证据归档和总体完成判定尚未收口。

## 八、主要证据入口

- [机器可读审计快照](WORKSPACE_EVIDENCE_SNAPSHOT.json)
- [总体实现差距记录](../../../subagent_reviews/MAIN_IMPLEMENTATION_GAP_AUDIT.md)
- [三维体系进展与后续计划](../../../research_modules/scalable_3d_simulation/docs/SCALABLE_3D_GOAL_PROGRESS_AND_NEXT_PLAN_20260807_CN.md)
- [历史正式规则矩阵记录](../../../research_modules/scalable_3d_simulation/docs/SCALABLE_3D_FORMAL_R0_80E55EB_SHARDS0_9_20260731_CN.md)
- [双光电独立实验README](../../../research_modules/independent_experiments/dual_optical_online_benchmark/README.md)
- [双光电权威复算清单](../../../research_modules/independent_experiments/dual_optical_online_benchmark/outputs/report_replay_20260819_v2/reproduction_manifest.json)
- [搜索及配准实验README](../../../research_modules/independent_experiments/center_terminal_cv_campaign/README.md)
- [搜索复现清单](../../../research_modules/independent_experiments/center_terminal_cv_campaign/outputs/offline_search_100pct_cues_20260819/reproduction_manifest.json)
- [机间配准诊断状态](../../../research_modules/independent_experiments/center_terminal_cv_campaign/outputs/terminal_gnn_diagnostic_selection_20260819_v2/selection_summary.json)
- [中心配准复现清单](../../../research_modules/independent_experiments/center_terminal_cv_campaign/outputs/center_handover_sensor_error_20260820/reproduction_manifest.json)
- [中心配准Word](../../leadership_report/中心航迹与拦截无人机目标配准试验报告_CN.docx)与[Markdown](../../leadership_report/中心航迹与拦截无人机目标配准试验报告_CN.md)
- [建议书精简版](../../project_proposals/建议书模版_智能化火指控补充版.docx)
