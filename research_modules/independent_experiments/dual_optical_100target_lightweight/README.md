# 双站光电轻量关联独立试验

本目录维护双站光电20、40、60和100目标在线配准中的轻量几何与匈牙利路线。它独立于D1至D7，不启动AirSim，也不改写共享跟踪器。main负责生成匿名双站航迹、冻结数据划分和共享几何候选白名单；本路线只消费统一逐圈快照，在白名单内评分并输出一对一匹配。

历史完整实测证据仍以100目标 `formal_v2_24_6_20` 为准，验证日期为2026年8月13日。V2已经完成9回合预检、30个校准随机种子和20个保留测试随机种子，但保留测试尚未收敛。新的20目标AirSim预检已经通过，说明输入、成轨和共享候选链路具备进入标定的条件。20目标正式标定随后完成，轻量路线在 `online-freeze` 验证选择阶段被规则淘汰：最佳条件精确率为0.6951672862，低于0.70门槛0.0048327138。该结果是预登记精确率门槛按设计生效，不是冻结实现错误。此次失败未生成冻结模型、未访问保留测试，并阻断40、60和100目标晋级；该路线不得在本轮后续规模重新启用。

## 当前接口

- `RevolutionSnapshot.target_count` 存在时必须为正整数，并传入候选图构造使用的 `OnlineEpisode.configured_target_count`。旧快照缺少该字段时仍可读取，原始输入指纹保持不变。
- 目标数量来自main冻结的协议和清单。冻结文件记录 `expected_target_count`，显式快照规模与冻结协议不一致时拒绝发布；算法不根据目录名推断100目标。
- 新快照优先使用main提供的 `geometry_candidate_pairs`。该集合是硬边界，轻量路线不得自行扩边；显式空集合保持为空。旧快照没有候选合同才使用原几何门控兼容路径。
- 第一圈只积累证据，第二圈可发布暂定关系，第三圈起按连续3圈至少命中2次发布确认关系。超时结果清空匹配，且不推进确认历史。
- 冻结模型按验证集召回率优先选择，但条件精确率必须不低于0.70。保留测试数据不参与模型、概率门限或未匹配代价选择。
- 验证选择未达到0.70硬门槛时，`online-freeze` 保持非零退出，同时在输出目录写出 `freeze_failure.json`。文件记录目标规模、协议指纹、最佳验证失败配置、精确率差额和数据访问状态，并固定设置 `promotion_allowed=false`、`stop_before_next_scale=true`。

## 20目标正式判定

20目标AirSim预检已通过。该结果只说明输入合同、匿名局部成轨和共享候选白名单能够进入正式标定，不代表轻量模型已经满足关联质量要求。

正式 `online-freeze` 已运行到验证选择阶段。最佳失败配置为单调概率标定模型 `isotonic_geometry_cost`，条件精确率为0.6951672862，低于0.70门槛0.0048327138；宏平均召回率为0.1994517544，宏平均F1为0.233739019，共发布269个关系，其中正确187个、错误82个。该配置仍未达到硬门槛，因此路线按规则淘汰。`freeze_failure.json` 已保存上述机器可读证据，冻结清单未生成，保留测试未访问。轻量路线未进入40、60和100目标阶段，在本轮逐规模试验中不得复活。

## V2链路

V2输入是main冻结的逐圈匿名快照。快照携带测量协方差、跟踪状态、近期命中、状态向量、状态协方差、输入指纹和共享跟踪器指纹。真实目标编号、AirSim对象名称、真实三维位置和未来观测均不进入在线特征；这些信息只在当圈发布完成后用于离线评分。

处理流程如下：

1. 核对协议、随机种子、逐圈时间、输入指纹和共享跟踪器指纹，不接受外来或被修改的快照。
2. 优先读取main共享候选白名单，只对名单内航迹对计算精确几何证据；旧快照才执行全对全几何门控兼容路径。
3. 从候选边计算18维几何、运动和不确定度特征。V2新增归一化运动残差、归一化共面残差、合成视线标准差和近期命中重叠率。
4. 比较非负几何权重、Platt概率标定、单调概率标定和逻辑回归四类轻量模型。训练集拟合参数，验证集选择模型、概率门限和未匹配代价。
5. 概率门限先拒绝低可信边，匈牙利算法再解决全局一对一冲突。航迹允许保持未匹配。
6. 第一圈不发布，第二圈发布暂定关系，第三圈起同一航迹对在连续3圈中至少命中2次才标为确认关系。超过1000毫秒时限的当圈结果按失败处理，不事后补发。

V2冻结选择 `logistic_edge_features_C0.1`，概率门限为 `0.4`，未匹配代价为 `0.9`。模型参数以JSON数值保存，不使用pickle。

## 试验协议

| 阶段 | 随机种子 | 样本范围 | 用途 |
| --- | --- | --- | --- |
| 预检 | `20270001`至`20270003` | 理想、姿态误差、完整干扰各3回合，共9回合 | 检查局部成轨纯度和共同成轨覆盖 |
| 训练 | `20270101`至`20270124` | 24个随机种子，3档干扰，6圈，共432份快照 | 拟合轻量模型 |
| 验证 | `20270125`至`20270130` | 6个随机种子，3档干扰，6圈，共108份快照 | 选择模型和门限并冻结 |
| 保留测试 | `20270201`至`20270220` | 20个未见随机种子，3档干扰，6圈，共360次在线发布 | 冻结后盲测 |

统一场景包含100个3米目标，速度50米/秒；其中50个沿0度航向，50个沿负30度航向。双站基线2千米，光电设备每2秒连续周扫360度，单回合持续12秒。逻辑采样率为100赫兹，AirSim时钟倍率为0.1。每台云台注入0.4毫弧度固定偏差和0.3毫弧度逐帧抖动，测试包含轻、中、重三档漏检和虚警。

## 100目标历史预检

预检最终接受3米运动初始化残差门和单一全局假设。三类场景结果如下：

| 场景 | 平均共同确认率 | 中位航迹纯度 | 预检门槛 | 结果 |
| --- | ---: | ---: | --- | --- |
| 理想 | 0.7767 | 1.0000 | 共同确认率不低于0.70 | 通过 |
| 姿态误差 | 0.7433 | 0.9167 | 共同确认率不低于0.65 | 通过 |
| 完整干扰 | 0.6833 | 0.8889 | 共同确认率不低于0.50，纯度不低于0.85 | 通过 |

预检是9回合的小样本早期止损和结构可行性门，不负责冻结正式跟踪器配置。该阶段选中3米运动初始化残差门和单一全局假设，对应指纹为 `0b3838...bc9`。正式标定扩大到30个随机种子，并在13个候选配置中独立选择最终配置；只有10米运动初始化残差门和3个全局假设的旧默认候选通过全部正式门槛，对应指纹为 `867bdf...95d`。两阶段指纹不同符合试验设计，不构成合同断链。正式校准、保留测试和三条路线的快照均使用 `867bdf...95d`，内部一致。该结果同时说明，9回合预检只能用于提前排除明显不可行方案，不能代替正式多随机种子标定。

## 100目标历史冻结

验证集选择逻辑回归路线。验证集宏平均F1为 `0.156884`，发布 `2044` 个关系，其中正确 `780` 个、错误 `1264` 个；宏平均精确率为 `0.188149`，宏平均召回率为 `0.137554`。联合冻结文件据此记录 `accepted=true`。

该接受条件只检查F1、正确匹配数和发布关系数均为非零，用于阻止零输出模型进入保留测试。它不是性能验收门槛。验证集已经显示错配多于正确匹配，不能据此认定路线有效收敛。

## 100目标历史测试

20个未见随机种子的结果如下：

| 指标 | 结果 |
| --- | ---: |
| 宏平均F1 | 0.011777 |
| 宏平均精确率 | 0.023362 |
| 宏平均召回率 | 0.007944 |
| 发布关系总数 | 1051 |
| 正确关系总数 | 286 |
| 错误关系总数 | 765 |
| 重复身份数 | 0 |
| 计算可用率 | 0.0944 |
| 1000毫秒时限满足率 | 0.5944 |
| 端到端时延中位数 | 298.51毫秒 |
| 端到端时延95%分位数 | 2183.95毫秒 |

360次发布中，180次因稳定航迹或候选图为空而没有进入关联，146次超过1000毫秒，只有34次记为可用计算。当前路线形成了非零匹配，但精确率、召回率和时限均未收敛，不应进入系统主线。

## 历史口径

- `formal_24_6_20` 是旧快照和旧共享跟踪器协议。该轮轻量路线零匹配，专项分析保留在 `docs/DUAL_OPTICAL_100TARGET_LIGHTWEIGHT_FORMAL_24_6_20_FAILURE_ANALYSIS_CN.md`。
- `formal_v2_24_6_20` 是当前V2在线协议，使用协方差快照、共享跟踪器冻结、三圈两次确认和联合冻结保护。它形成了非零匹配，但保留测试未收敛。
- 早期 `formal_expanded_20260820_20260920_run01` 是保存后候选图的离线轻量对照。其高分结果和旧图不能替代当前连续周扫在线测试，现仅作为历史方法验证材料。

## 同输入消融

独立命令 `candidate-ablation` 比较两种候选构造。两路使用同一原始逐圈快照、同一冻结模型、同一概率门限、同一未匹配代价和同一三圈确认规则。唯一变量如下：

- `shared_allowlist`：只计算main共享白名单内的候选，不允许扩边。
- `legacy_all_pairs`：离线重放旧全对全候选评估，再执行同一精确几何门控。该模式仅存在于消融命令，正式 `online-run` 没有全对全开关。

两路发布完成后才读取离线真实标签。输出包括原始输入指纹、候选图指纹、全组合数、实际评估数、候选边数、正确候选保留率、评分通过数、匈牙利选择数、精确率、召回率、F1值、错配数、时限满足率，以及候选构造、模型评分、匈牙利求解、确认发布和端到端95%分位时延。汇总文件为 `candidate_ablation_summary.json`，逐快照记录为 `candidate_ablation_rows.csv`。

中噪声和重噪声分别执行停止晋级检查。任一档缺少配对证据、共享白名单召回率相对旧全对全下降至少0.02、召回率差的配对自助法95%置信区间上界低于0，或共享方案条件精确率低于0.70，均设置 `promotion_allowed=false` 和 `stop_before_next_scale=true`。命令返回码为2，main不得继续下一目标规模。

```bash
PYTHONPATH=research_modules/independent_experiments \
python3 -m dual_optical_100target_lightweight candidate-ablation \
  --test-manifest /path/to/test_manifest.json \
  --freeze-manifest /path/to/lightweight_freeze_manifest.json \
  --output-dir /path/to/ablation_output
```

正式执行顺序为20、40、60、100目标。每个规模使用自己的协议、训练集、验证集、保留测试集和冻结文件；上一规模的中重噪声晋级闸门通过后，才允许进入下一规模。20目标预检已经通过，正式标定也已完成，但最佳验证条件精确率为0.6951672862，未达到0.70，因此本轮不生成冻结模型、不打开保留测试，也不执行正式同输入消融。轻量路线在验证阶段结构化淘汰，不进入40、60和100目标，并且不得在这些后续规模重新出现。

旧的20目标失败运行只抛出了异常，没有保存验证排行榜或最佳失败行。重新执行相同冻结命令后，当前 `freeze_failure.json` 已记录准确的最佳结果和差额：条件精确率0.6951672862、门槛0.70、差额0.0048327138。失败证据留存没有改变0.70门槛，也没有把旧失败改判为通过；旧产物本身仍不作为具体数值证据。

## 证据文件

- 当前20目标结构化淘汰证据：`research_modules/independent_experiments/dual_optical_online_benchmark/outputs/scale_funnel_v3/targets_020/dataset/freezes/lightweight/freeze_failure.json`
- 联合冻结：`research_modules/independent_experiments/dual_optical_online_benchmark/outputs/formal_v2_24_6_20/dataset/freezes/all_routes_frozen.json`
- 轻量冻结：`research_modules/independent_experiments/dual_optical_online_benchmark/outputs/formal_v2_24_6_20/dataset/freezes/lightweight/`
- 预检摘要：`research_modules/independent_experiments/dual_optical_online_benchmark/outputs/formal_v2_24_6_20/preflight/preflight_summary.json`
- 最终指标：`research_modules/independent_experiments/dual_optical_online_benchmark/outputs/formal_v2_24_6_20/results/comparison_metrics.json`
- 统一报告：`research_modules/independent_experiments/dual_optical_online_benchmark/outputs/formal_v2_24_6_20/results/DUAL_OPTICAL_100TARGET_ONLINE_COMPARISON_REPORT_CN.md`
- 本路线报告：`docs/DUAL_OPTICAL_100TARGET_LIGHTWEIGHT_REPORT_CN.md`

## 检查

从项目根目录运行：

```bash
PYTHONPATH=research_modules/independent_experiments pytest -q \
  research_modules/independent_experiments/dual_optical_100target_lightweight/tests

PYTHONPATH=research_modules/independent_experiments \
python3 -m py_compile \
  research_modules/independent_experiments/dual_optical_100target_lightweight/*.py

git diff --check -- \
  research_modules/independent_experiments/dual_optical_100target_lightweight
```

本次只同步轻量路线 `README.md` 和 `PLAN.md` 中的20目标结构化淘汰事实，没有修改代码、测试或实验输出。
