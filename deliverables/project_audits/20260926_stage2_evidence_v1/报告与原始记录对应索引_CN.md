# 报告与原始记录对应索引

核查日期：2026年9月26日。范围：四份主要试验报告的现存Word、Markdown及其保存结果。仓库起点为`3c53a03f0cce03fd5e2adebbcab37bdc3805c411`。

本索引用于查找和核对已有材料，不新增实验结论。报告的表格、统计条件、来源版本和配图分别登记；没有执行仿真、训练、配准或重新评分。

## 一、核对结果

| 报告 | Word结果表 | Markdown结果表 | 核对单元格数 | 结果 |
| --- | ---: | ---: | ---: | --- |
| 双光电多目标轨迹配准与交汇定位 | 6 | 6 | 794 | 显示值与保存结果一致 |
| 协同搜索 | 4 | 4 | 108 | 显示值与保存结果一致 |
| 末端目标配准 | 3 | 3 | 192 | 分场景显示值与保存结果一致；两条合计行另按保存计数核对 |
| 中心航迹与拦截无人机目标配准 | 1 | 4 | 210 | 两版分别与其对应的结果子集一致 |
| 合计 | 14 | 17 | 1304 | 未发现数值转录差异 |

1304是表格单元格核对次数，包含同一结果在Word和Markdown中的重复出现，不是实验次数。设置表、方法说明、图中曲线和正文因果解释不包含在该计数中。相同的表格数值不能证明两版正文、图片和适用范围完全相同。

逐项记录见[TABLE_VALUE_CHECKS.csv](TABLE_VALUE_CHECKS.csv)。每项记录包含报告文件、章节、表序号、行号、列名、报告显示值、来源文件、JSON位置或CSV数据行、字段原值和格式化后显示值。Markdown另记录表格所在行；Word按正文表序号定位。CSV来源位置`data_row:1`表示表头后的第一条数据。

完整文件指纹、表格目录及清单校验见[REPORT_EVIDENCE_INDEX.json](REPORT_EVIDENCE_INDEX.json)，记录行数、种子列表、模型文件和图片来源补查见[SUPPLEMENTAL_PROVENANCE.json](SUPPLEMENTAL_PROVENANCE.json)。

## 二、报告与结果入口

### 1. 双光电报告

报告：[Word](../../leadership_report/双光电多目标轨迹配准与交汇定位试验报告_CN.docx)、[Markdown](../../leadership_report/双光电多目标轨迹配准与交汇定位试验报告_CN.md)。

| 报告位置 | 来源 | 查询条件与字段 | 证据范围 |
| --- | --- | --- | --- |
| 3.1理想单站结果 | [combined_summary.json](../../../research_modules/independent_experiments/dual_optical_online_benchmark/outputs/report_replay_20260819_v2/combined_summary.json) | `summary`中`profile=oracle_360`，再按`target_count`和`route_name`选择 | 6组，每组5个seed；使用离线身份整理单站输入的诊断 |
| 3.2.2单站、3.2.3双站 | 同一汇总文件 | `profile=continuous_360`；按规模、干扰和方法查询；单站表取同输入的一份记录，不重复合并两种方法 | 24组，最终窗口为第6圈 |
| 3.3.1单站、3.3.2双站 | 同一汇总文件 | `profile=s180`；字段与360度表一致 | 24组，最终窗口为第12轮；中重干扰为保存观测上的离线派生 |
| 3.4定位演示 | [原40目标metrics.json](../../../research_modules/independent_experiments/dual_optical_40target/outputs/airsim_seed_20260810_run11/metrics.json) | `seed`、关系计数、精度、覆盖度及位置和速度误差字段 | 20260810单seed演示；不属于上述54组矩阵 |

54组对应[最终案例表](../../../research_modules/independent_experiments/dual_optical_online_benchmark/outputs/report_replay_20260819_v2/combined_final_case_metrics.csv)的270行，文件内共有30个不同seed编号。相同seed在不同方法、干扰和诊断条件下重复出现，不能称为270个独立场景。

配置入口为[campaign_config.json](../../../research_modules/independent_experiments/dual_optical_online_benchmark/outputs/report_replay_20260819_v2/campaign_config.json)，完整输入、冻结配置及来源代码校验入口为[reproduction_manifest.json](../../../research_modules/independent_experiments/dual_optical_online_benchmark/outputs/report_replay_20260819_v2/reproduction_manifest.json)。六份图网络冻结记录分别位于`scale_funnel_v3`和`s180_1s_sector_v1`的20、40、60目标目录，实际路径及训练、验证、测试seed列在补查JSON中。

该清单记录历史提交`ad59ff3f48e180248f1168bf72a0e152bd80264a`，同时标明`worktree_dirty=true`，并保存五个来源代码文件的哈希。不能仅检出该提交就认为恢复了原运行源码。40、60目标360度几何结果具有跨规模诊断限制，S180的历史停止状态也不因报告复算而改变。

### 2. 协同搜索报告

报告：[Word](../../leadership_report/协同搜索试验报告_CN.docx)、[Markdown](../../leadership_report/协同搜索试验报告_CN.md)。

3.1至3.3的九行结果及3.5的九行时间结果，均对应[matrix_summary.json](../../../research_modules/independent_experiments/center_terminal_cv_campaign/outputs/offline_search_100pct_cues_20260819/matrix_summary.json)的`aggregates`。以`scenario_id`和`position_sigma_m`定位，分别读取发现率、连续确认率、概率覆盖、未执行任务及时间字段。

[matrix.csv](../../../research_modules/independent_experiments/center_terminal_cv_campaign/outputs/offline_search_100pct_cues_20260819/matrix.csv)有45行，对应3种规模、3档误差和5个seed，不是45次新AirSim运行。配置和输入轨迹入口为[复现清单](../../../research_modules/independent_experiments/center_terminal_cv_campaign/outputs/offline_search_100pct_cues_20260819/reproduction_manifest.json)。三组输入只保存到0.8秒，余下17.2秒使用外推；20/8和20/30两组输入轨迹的哈希相同，不作为两组相互独立的目标运动记录统计。

原文末尾称未记录原始提交号，与现存清单不一致。清单已记录`git_revision=ad59ff3f…`及`working_tree_dirty=true`；但这不等于完整冻结了未提交源码、依赖及环境。本次登记该差异，未改写原文。

### 3. 末端目标配准报告

报告：[Word](../../leadership_report/末端目标配准试验报告_CN.docx)、[Markdown](../../leadership_report/末端目标配准试验报告_CN.md)。该报告的两部分来自不同批次，必须分别索引。

| 报告位置 | 来源 | 定位方式 | 数据用途 |
| --- | --- | --- | --- |
| 5.1中心交接 | [benchmark_summary.json](../../../research_modules/independent_experiments/center_terminal_cv_campaign/outputs/gnn_offline_benchmark_20260816/benchmark_summary.json) | `results`中`task=center_handover`，按场景和方法选择；计数在`metrics`，耗时在`timing` | 三组保存场景的旧版离线比较；不来自8月20日误差矩阵 |
| 5.2机间配准结果 | [selection_summary.json](../../../research_modules/independent_experiments/center_terminal_cv_campaign/outputs/terminal_gnn_diagnostic_selection_20260819_v2/selection_summary.json) | 几何取`geometry_scenario_metrics`，图网络取`selected_cold_scenario_metrics` | 同一批已知场景上的诊断选参 |
| 5.2无缓存时间表 | 同一选参汇总 | 同上，读取`elapsed_s`、`retained_camera_pair_count`和`candidate_edge_count` | 无缓存回放耗时；不能换用参数搜索中的缓存耗时 |

5.1合计行由现存计数相加得到：正确关系61，几何错误关系1、图网络错误关系0，正确中心线索合计64。对应显示值分别为`0.9839/0.9531`和`1.0000/0.9531`，与报告一致。这里只做已保存计数的算术核对，没有重新判定任何关系。

5.1的时长记录每种方法重复计时5次，这五次不是五个不同seed。旧基准记录`held_out_seed=20260816`；其训练与验证seed保存在同一汇总及[training_summary.json](../../../research_modules/independent_experiments/center_terminal_cv_campaign/outputs/gnn_offline_benchmark_20260816/training_summary.json)。当前索引保留原记录用途，没有重新认定其独立性。

5.2共有36组参数、108条场景与参数组合，以及3条几何对照。`diagnostic_testset_tuning=true`、`independent_holdout_validation=false`明确表明该批不属于新留出验证。[三组输入清单](../../../research_modules/independent_experiments/center_terminal_cv_campaign/outputs/terminal_gnn_diagnostic_selection_20260819_v2/manifests/)保存输入路径和27项哈希，但没有完整的执行提交及环境字段。不能用本次仓库版本补写历史执行版本。

### 4. 中心配准误差报告

报告：[Word](../../leadership_report/中心航迹与拦截无人机目标配准试验报告_CN.docx)、[Markdown](../../leadership_report/中心航迹与拦截无人机目标配准试验报告_CN.md)。

| 报告位置 | 对应记录 | 查询条件 |
| --- | --- | --- |
| Markdown 3.1 | [aggregate_metrics.csv](../../../research_modules/independent_experiments/center_terminal_cv_campaign/outputs/center_handover_sensor_error_20260820/aggregate_metrics.csv) | `normal`、`satellite`、`ideal` |
| Markdown 3.2 | 同一CSV | `normal`、`satellite`、`light` |
| Markdown 3.3 | 同一CSV | `degraded`、`visual_navigation`、`light` |
| Word 3.1 | 同一CSV中的裁剪子集 | 上一行条件，再限定`handover_mode=coarse_hint`；表中保留两种方法 |
| Markdown 3.5 | 三组接口试验的`summary_metrics.csv` | [20目标](../../../research_modules/independent_experiments/center_terminal_cv_campaign/outputs/center_handover_sensor_error_airsim_20260820_n20_retry01/summary_metrics.csv)、[40目标](../../../research_modules/independent_experiments/center_terminal_cv_campaign/outputs/center_handover_sensor_error_airsim_20260820_n40/summary_metrics.csv)、[60目标](../../../research_modules/independent_experiments/center_terminal_cv_campaign/outputs/center_handover_sensor_error_airsim_20260820_n60/summary_metrics.csv) |

每条CSV再按`target_count`、`handover_mode`和`backend`定位。完整矩阵为96类汇总、960条逐组记录，仅有10个不同seed，不能写成960个独立随机样本。接口试验各有4条方法与条件组合，三组均使用seed 20260820，不能与960条离线构造结果混为同一试验批次。

配置见[protocol.json](../../../research_modules/independent_experiments/center_terminal_cv_campaign/outputs/center_handover_sensor_error_20260820/protocol.json)，分母见[metrics_contract.json](../../../research_modules/independent_experiments/center_terminal_cv_campaign/outputs/center_handover_sensor_error_20260820/metrics_contract.json)，源码、冻结模型和环境记录见[reproduction_manifest.json](../../../research_modules/independent_experiments/center_terminal_cv_campaign/outputs/center_handover_sensor_error_20260820/reproduction_manifest.json)。该批保存了`source_snapshot/`和未提交修改补丁，与只记录提交号的批次不同。

## 三、统计口径对照

| 对象 | 统计时间与分母 | 不能混用的口径 |
| --- | --- | --- |
| 双光电质量精度 | 最后一圈或最后一轮，正确关系数除以输出关系数 | 不等于所有历史时刻累计正确率 |
| 双光电质量覆盖度 | 最终正确目标数除以固定目标总数 | 不以候选数、可见数或输出数代替固定目标数 |
| 双光电按时覆盖度 | 保持上述目标分母，超时结果贡献计为0 | 不可用超时后质量结果证明按时输出能力 |
| 双光电单站覆盖度 | 两站身份正确航迹对应的机会数，分母为两倍目标总数 | 不等于双站已匹配目标比例 |
| 搜索发现与连续确认 | 18秒窗口内是否曾达到相应条件，再按五个seed给出均值和最差值 | 不是最后一帧配准覆盖度，也不是身份绑定成功率 |
| 旧版中心交接覆盖度 | 正确绑定数除以正确中心线索数；分场景为16、16、32 | 不能直接与20、20、40的全目标分母结果对比 |
| 机间关系覆盖度 | 正确关系数除以应建立的真实关系数 | 不等于正确成簇目标比例；目标等权指标另列 |
| 中心误差矩阵覆盖度 | 最后一帧有效确认关系，分母为正确中心线索数；此批中心输入全对，因此等于目标数 | 不与中心只有80%线索的旧版表直接比较 |

计时也不统一：双光电是最后窗口耗时；搜索是各次规划P95再取场景均值；旧版中心交接包含关联、审计输出和绘图的重复计时；机间表使用无缓存整次回放；中心误差表使用逐组运行时长。不能把这些数值并列为同一种算法单帧时延。

## 四、数据使用和版本边界

六份双光电图网络冻结清单各列8个训练seed、2个验证seed和5个预留测试seed，各清单内部编号无重合。对应权重、归一化、模型配置及相关训练记录，加上旧中心和机间模型，共57项文件校验一致。本次只读取字节计算哈希，没有加载模型，也没有复核每一次历史训练过程。

现存测试数据已经在历史比较和本次结果核对中使用，不能重新称为“尚未见过的数据”。180度和360度使用不同seed集合，跨版本比较不能自动解释为只改变扫描周期的一项受控试验。理想单站诊断明确借助离线标签整理输入，也不属于纯匿名在线性能证明。

四组主清单原有的196项校验全部一致。额外检查双光电报告生成清单时，28项中26项一致，Word及其生成脚本两项与旧清单不符，详见[版本差异核对](报告版本差异核对_CN.md)。该差异不改变本次结果表与保存数值一致的判断，也不能据此声称整份报告仍是旧生成器的原始输出。

## 五、图片与附件

[IMAGE_ASSET_REGISTER.csv](IMAGE_ASSET_REGISTER.csv)登记19份Markdown的141处图片引用，全部在本机存在，138处由Git跟踪，3处被Git忽略。这里统计的是引用次数，不是不同图片文件数量。

三处忽略引用均在中心配准Markdown中，指向其结果目录的`figures/01_association_flow.png`、`02_scale_results.png`和`03_error_heatmaps.png`。只克隆Git仓库不能保证显示这三张图。本阶段仅登记，不复制图片、不改引用；实际交付时须选择随Markdown带齐图片，或明确仅使用已嵌入图片的Word版本。

搜索报告5张配图与原结果目录逐字节一致；末端报告两张局部航迹、关系图也与选参目录中的对应图片一致，7组记录见补查JSON的`figure_lineage`。双光电图表来源以报告生成清单和原始表为索引。流程图与场景示意图不作为额外实验样本。

图片存在、字节一致和嵌入关系正确分别属于文件检查。本次未逐页渲染Word，也未重新解读每张图的坐标与曲线，不将文件检查写成图像内容验证。

## 六、尚未关闭的事项

结果表的转录核对已经完成，但下列问题仍保留：旧生成清单与现Word版本不一致；中心配准两版用途尚待最终确认；多模态两版有独有章节和配图；搜索报告的源码记录说明滞后；个别批次没有完整执行源码和环境归档；Markdown引用的三张图尚未纳入独立交付包。

这些事项已经形成明确位置和依据，不通过改写历史清单、覆盖Word、重新选择参数或补跑实验解决。本次没有作出算法优劣或装备指标的新判定。
