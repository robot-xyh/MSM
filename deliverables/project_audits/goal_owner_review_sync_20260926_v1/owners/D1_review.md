# D1 原 Goal 历史证据复核

核查日期：2026-09-26。身份：D1 所有者。本轮仅审读历史材料；建议状态不改变模块状态或关闭 GAP。机器记录见 [D1_review.json](D1_review.json)。

## 范围与结论

对照主级 [CSV](../../goal_resume_audit_20260926_v1/GOAL_REQUIREMENT_EVIDENCE.csv)、[逐项明细](../../goal_resume_audit_20260926_v1/逐项证据明细_CN.md)、[原完成审计](../../../../research_modules/scalable_3d_simulation/docs/SCALABLE_3D_GOAL_COMPLETION_AUDIT_20260803_CN.md)及 D1 保存文档，复核 owner 明列 D1 或范围包含 D1 的全部 8 项。共认可 1 项、限定认可 5 项、需修订表述 2 项；建议状态均不升级，6 项部分完成、2 项未完成。

仅检查与条目有关的文档章节和主级序列化片段，不声称逐行审查所有历史实现、提交或原始记录。

| 编号 | 原状态 | 意见 | 建议状态 | 理由及缺证据 |
| --- | --- | --- | --- | --- |
| G04 | 部分完成 | 限定认可 | 部分完成 | D1 隔离合同与局部历史验证存在；正式450组只有保存摘要，不能重新确认逐组零泄漏，缺完整载荷及最终统一矩阵。 |
| G16 | 部分完成 | 限定认可 | 部分完成 | D1 完整观测/后验有双时间戳，主级航迹摘要仅单 timestamp；仍有对象直传，缺完整序列化及订阅消费证据。 |
| G17 | 部分完成 | 需修订 | 部分完成 | 0.8183 来自独立雷达短时开发冒烟，不是原 Goal 多传感器正式矩阵；缺原协议独立多种子结果与机器制品绑定。 |
| G38 | 未完成 | 认可 | 未完成 | F1 统一结果不存在于所核材料；局部实现、来源生成和独立视觉实验均不能替代完整体系验收。 |
| G41 | 未完成 | 需修订 | 未完成 | 同样需限定0.8183出处；0.95是建议目标，未定位正式阈值冻结记录，不能写成已冻结门限。 |
| G49 | 部分完成 | 限定认可 | 部分完成 | 522项主模块与D1专项/全量通过数来自不同历史日期及范围；缺最终同版本回归交付记录，本轮未重跑。 |
| G55 | 部分完成 | 限定认可 | 部分完成 | D1文档保存阶段同步与开放项，不证明最终验收合并；旧900/135批次和正式450须按提交、执行计划区分。 |
| G57 | 部分完成 | 限定认可 | 部分完成 | 版本合同和历史哈希存在，不等于原manifest现存；缺450组完整绑定与最终体系版本清单。 |

逐项仓库相对证据路径、具体理由与缺失证据均保存在 JSON 的 `requirements` 中。

## 主要异议

1. G17、G41 应补全召回率来源。[D1实验报告](../../../../research_modules/d1_sensor_fusion/docs/EXPERIMENT_REPORT.md)记录：2026-07-25，200目标、seed 1000、0.61秒、3个发布帧、532条唯一接受观测，暖机召回0.8183。[算法文档](../../../../research_modules/d1_sensor_fusion/docs/ALGORITHM_AND_IMPLEMENTATION.md)明确该独立基准在线输入仅匿名雷达。5目标、seeds 2000-2019 的20/20快速夹具只验证入口，不能替代200目标20个未见seed的正式质量结果。所读材料未提供该短时值的直接机器结果及配置绑定入口，本轮未扩大搜索。
2. G41 的“缺达到冻结阈值”容易误示验收门已冻结。原审计称0.95为建议目标；D1 [原则文档](../../../../research_modules/d1_sensor_fusion/docs/MODULE_PRINCIPLES_CN.md)与 [PLAN](../../../../research_modules/d1_sensor_fusion/PLAN.md)仍保留正式长时门限待冻结事项。建议写为“正式协议与阈值冻结证据未定位，缺同协议独立多种子达标证据”。数值低于建议值不等于已经做过同协议正式验收。
3. G16 的接口层必须分开。[主级module_stack.py](../../../../research_modules/scalable_3d_simulation/module_stack.py)中 `modules.d1.fused_tracks` 使用 `_track_summary`，摘要含状态和协方差，但不完整保留双时间戳；下游转换直接使用 `self.latest_d1_tracks`。这是静态证据，不是运行验证，也不否定 D1 完整后验合同。

## 历史边界

- 正式450组继续登记“摘要可查、完整记录未定位”。[7月31日报告](../../../../research_modules/scalable_3d_simulation/docs/SCALABLE_3D_FORMAL_R0_80E55EB_SHARDS0_9_20260731_CN.md)绑定80e55eb及执行计划b922ff5f开头的哈希。历史校验通过不等于本轮已恢复或重验。
- D3/D4/D5来源728组不是450组。当前A1 v3、A2 v8、A3 v3训练未完成，来源完整性审计和后续独立实验不能替代当前代际模型与原Goal统一验收。
- [7月25日D1代次诊断](../../../../subagent_reviews/D1_FORMAL_R0_GENERATION_FINALIZATION_DIAGNOSIS_20260725_CN.md)中的旧900组和135/900重跑绑定另一提交及8804ecb4开头的执行计划；不能拼入正式450组，也不需回写历史数值。
- 原审计522项通过是2026-08-03记录；D1质量基准8项专项与496项全量通过是2026-07-25记录。本轮没有生成新的模块测试结果。
- [独立双光电README](../../../../research_modules/independent_experiments/dual_optical_online_benchmark/README.md)明确不接入D1-D7。独立成果存在、局部程序调用与原Goal同版统一验收不是同一层证据。

## 文档检查

以下11份文件均存在，已检查相关章节；逐文件理由见 JSON 的 `documentation_checked`。

| 文件 | 本轮不同步原因 |
| --- | --- |
| D1 README.md | 已明确独立基准范围，主表遗漏限定在本审计登记。 |
| D1 PLAN.md | 正式长时多seed及阈值冻结仍开放；本轮未改变计划或能力。 |
| D1_IMPLEMENTATION_GAP_AUDIT.md | 实现关闭、接口关闭和正式证据P1开放已分开，无新GAP关闭。 |
| D1_SENSOR_FUSION_REVIEW_AND_PLAN.md | 短时证据边界与未完成结论一致，没有新验证。 |
| docs/MODULE_PRINCIPLES_CN.md | 原则不变；与主表“冻结阈值”的措辞差异已登记。 |
| docs/ALGORITHM_AND_IMPLEMENTATION.md | 输入模态及时间戳合同明确，无算法或接口变更。 |
| docs/AIRSIM_INTEGRATION_PLAN.md | 已区分质点和AirSim证据，无适配变更或新AirSim结果。 |
| docs/EXPERIMENT_REPORT.md | 保留历史日期、样本范围和原数值，不重算或覆盖。 |
| D1_M_TO_N_COOPERATIVE_LOCALIZATION_REVIEW.md | 旧M5N2结果不作200目标质量验收，无协同定位能力变化。 |
| D1_STRUCTURAL_AMBIGUITY_HOLD_CAUSAL_AUDIT_CN.md | 默认关闭候选与单seed因果研究不升级为原Goal准入。 |
| D1_FORMAL_R0_GENERATION_FINALIZATION_DIAGNOSIS_20260725_CN.md | 不同批次历史快照按原身份保留，不改为450组。 |

上表 docs 路径均属于 `research_modules/d1_sensor_fusion/`，D1_* 文件属于 `subagent_reviews/`。本轮没有能力变更、GAP关闭或新实验，且授权仅允许写本批审计文件，因此未修改原模块、旧报告或其他智能体文件。没有制定或执行新增算法、训练或控制路径。

## 文件检查

写入后仅执行 JSON 解析、字段/枚举、CSV owner范围及编号覆盖、原状态、引用路径、Markdown编号一致性和原文档SHA-256检查。检查结果见 JSON 的 `validation`；文件存在只证明引用可定位，不证明引用所述历史实验完整可复现。

文件检查通过：编号及原状态8/8一致，21个唯一证据/文档路径存在，11份文档检查已记录，12个Markdown本地链接有效；11份原D1文档及源CSV共12个文件的前后SHA-256未变。未运行模块pytest、训练、GPU、AirSim、控制或重新评分。
