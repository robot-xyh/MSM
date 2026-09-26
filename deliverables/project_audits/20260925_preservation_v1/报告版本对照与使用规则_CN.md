# 报告版本对照与使用规则

登记日期：2026年9月25日。适用范围：`deliverables/leadership_report/`、`deliverables/patents/`及`deliverables/project_proposals/`一级目录中的Word报告。

## 一、版本检查结果

共登记26份Word，其中19份有同名Markdown。26份Word均通过DOCX压缩包完整性检查，内部附件引用未发现缺失；19份Markdown共检查141条行内图片引用，当前本机均可找到。

| 文档关系 | 数量 | 使用规则 |
| --- | ---: | --- |
| Markdown章节标题可在Word中找到 | 17组 | 可相互参考，尚未逐段核对正文、表格及图片，不能直接认定内容完全相同 |
| 存在章节标题差异 | 2组 | 两版分别保留，按下述用途登记，不自动覆盖 |
| 无同名Markdown或由多个素材形成 | 7份 | Word独立保留，不推定某个素材文件是唯一生成源 |

26份Word与19份同名Markdown的校验值均与[原始审计快照](../20260925/WORKSPACE_EVIDENCE_SNAPSHOT.json)一致。本次没有改正文或版式。完整记录见[文档版本登记](DOCUMENT_VERSION_REGISTER.json)。

## 二、需要区别使用的文档

### 1. 中心配准报告

- [Word](../../leadership_report/中心航迹与拦截无人机目标配准试验报告_CN.docx)：保留当前人工修改后的汇报稿，结果部分为“3.1 强干扰组合工况”和“3.2 结论”。
- [Markdown](../../leadership_report/中心航迹与拦截无人机目标配准试验报告_CN.md)：保留实验完整版，结果部分仍有正常条件、全部误差组合、接口代表试验等六个小节。

两版用途分别登记，暂不改名。汇报时采用已裁剪的Word；查询完整实验设置和记录时参考Markdown及原始结果。不得根据Markdown直接重新生成并覆盖现有Word，也不得为追求同名一致而删除完整版内容。

### 2. 多模态特征融合报告

[Word](../../leadership_report/MULTIMODAL_FEATURE_FUSION_AND_TRACK_ASSOCIATION_SOLUTION_CN.docx)与[Markdown](../../leadership_report/MULTIMODAL_FEATURE_FUSION_AND_TRACK_ASSOCIATION_SOLUTION_CN.md)有15项Markdown标题未在Word全文中原样找到，涉及任务判断、技术边界、关联方案、验证方式等。

该检查不能判断哪版更新，也不能代替正文比较。两版均保留，后续需确认采用哪份作为汇报稿，以及是否还需要保留另一份的独有内容。在此之前不批量同步或重新生成。

### 3. 综合方案与建议书

[方案模板](../../leadership_report/方案模板.docx)包含多次融合和人工修改，按独立综合稿保留；[补充素材](../../leadership_report/方案模板_4_1_4_4_4_5补充素材_CN.md)是素材入口，不代表整份Word的唯一来源。

[建议书原模板](../../project_proposals/建议书模版.docx)与[智能化火指控补充版](../../project_proposals/建议书模版_智能化火指控补充版.docx)分别保留。后续修改只针对明确指定的版本，不覆盖原模板。

### 4. 专利文档

两份专利Word分别保留86个和83个原生数学对象。现有公式结构无需因本次登记而重新转换。结构检查未验证所有公式的页面显示效果，后续排版调整仍应查看实际渲染页面。

## 三、主要报告的证据入口

以下目录用于查找已保存的结果及来源，不代表本次重跑或新增验证。表中“汇总行数”沿用原始数据表口径。

| 报告 | 主要证据目录 | 已核实的记录 | 引用时需保留的区别 |
| --- | --- | --- | --- |
| [双光电试验报告](../../leadership_report/双光电多目标轨迹配准与交汇定位试验报告_CN.docx) | [report_replay_20260819_v2](../../../research_modules/independent_experiments/dual_optical_online_benchmark/outputs/report_replay_20260819_v2/) | 270条最终结果，54组 | 保存数据上的复算结果；按原配置区分场景和统计范围 |
| [协同搜索试验报告](../../leadership_report/协同搜索试验报告_CN.docx) | [offline_search_100pct_cues_20260819](../../../research_modules/independent_experiments/center_terminal_cv_campaign/outputs/offline_search_100pct_cues_20260819/) | 45条汇总记录 | 运动记录离线回放，不写成45次新AirSim试验 |
| [末端配准试验报告](../../leadership_report/末端目标配准试验报告_CN.docx) | [terminal_gnn_diagnostic_selection_20260819_v2](../../../research_modules/independent_experiments/center_terminal_cv_campaign/outputs/terminal_gnn_diagnostic_selection_20260819_v2/) | 36组参数、108条场景参数结果、3条对照 | 参数在既有数据上选择，属于诊断，不是独立保留数据验证 |
| [中心配准试验报告](../../leadership_report/中心航迹与拦截无人机目标配准试验报告_CN.docx) | [center_handover_sensor_error_20260820](../../../research_modules/independent_experiments/center_terminal_cv_campaign/outputs/center_handover_sensor_error_20260820/) | 960条逐组结果、96条汇总 | 报告为裁剪版，结果目录保留完整矩阵 |

主仓库Git默认忽略实验`outputs`目录。报告中图片在本机可打开，并不保证仅克隆代码仓库后也可打开。交付Markdown时需带齐实际引用的图片和附件；本次没有更改图片路径。

本表只列主要结果入口，不能替代每份报告逐项溯源。实验是否可重放，仍需核对对应的输入、配置、模型、环境记录和执行版本；盘点时的仓库提交不能替代实验执行版本。

## 四、生成工具的覆盖风险

| 工具 | 已检查到的写入行为 | 后续处理 |
| --- | --- | --- |
| [build_dual_optical_registration_report.py](../../leadership_report/tools/build_dual_optical_registration_report.py) | 写入报告Markdown并保存Word | 明确版本来源后，再决定是否生成新文件 |
| [build_center_terminal_split_reports.py](../../leadership_report/tools/build_center_terminal_split_reports.py) | 写入搜索、末端报告及Word | 不用当前脚本直接覆盖人工修改稿 |
| [integrate_scheme_template_sections.py](../../leadership_report/tools/integrate_scheme_template_sections.py) | 未指定输出时，以输入文件作为最终写入位置 | 后续执行时明确指定新的输出文件，并保留原件 |
| [build_fire_control_supplement.py](../../project_proposals/tools/build_fire_control_supplement.py) | 默认保存到既有补充版文件名 | 如需重生成，先确认原文件是否有后续人工改动 |

本轮没有执行上述生成器，也没有修改其默认行为。登记中的`overwrite_allowed=false`是管理标记，不是文件系统写保护，不能阻止其他程序覆盖原文件。

## 五、后续版本更新

后续编辑前，先确定要改的是汇报稿、实验完整版还是综合模板。需要同时更新Word和Markdown时，应从实际修改内容核对差异，不能只按文件时间或同名关系互相覆盖。

新版本形成后，另建日期目录保存登记，记录原文件和新文件的校验值、主要改动及证据来源。历史登记不随新稿同步改写。多模态报告的采用版本和独立备份位置目前仍待确认。
