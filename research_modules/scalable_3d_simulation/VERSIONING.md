# 三维规模化仿真版本管理

## 分支

```text
main
└── feat/scalable-3d-200v200
```

- `main` 保留已验证的 2v2、5v5、M5N2 和 AirSim 基线。
- `feat/scalable-3d-200v200` 承载三维环境、D1-D7 扩展、图神经网络和强化学习集成。
- D1-D7 默认不分别创建长期分支。各模块所有者只修改自身目录，main 审查后分批提交。
- PyTorch Geometric 等高风险依赖实验可使用 `exp/<topic>` 短期分支。验证结束后合并有效部分，随后删除实验分支。
- 专项分支推送并进入协作后不改写历史，不使用强制推送。同步 `main` 使用普通合并。

## 提交

提交按可独立审查和回归的能力分组：

1. `plan: define scalable 3D contracts`
2. `feat(sim): add vectorized 3D world`
3. `feat(d1-d2): support dense 3D tracking`
4. `feat(d7): close 3D guidance loop`
5. `feat(d5): add sparse graph association`
6. `feat(d3): add RL-assisted assignment`
7. `feat(d4): add regional fallback coordination`
8. `feat(d6): add large-scale evaluation`
9. `feat(integration): connect 200v200 episode bus`
10. `docs: synchronize plans, gaps and reports`

子智能体不操作共享 Git 索引。main 检查模块测试和文档同步后统一暂存、提交和推送。

## 数据合同

代码提交号不能单独说明实验条件。每个 episode 必须同时记录以下版本：

| 项目 | 当前格式 | 变更条件 |
| --- | --- | --- |
| 世界模型 | `scalable3d-world-v1` | 状态语义、坐标或动力学改变 |
| 总线合同 | `scalable3d-episode-bus-v1` | 跨模块消息出现不兼容变更 |
| 场景配置 | `scalable3d-scenario-v1` | 配置字段语义或默认场景改变 |
| 在线观测 | `scalable3d-observation-v1` | 观测字段、单位或时序语义改变 |
| 离线真值 | `scalable3d-offline-truth-v1` | 标签结构或评分口径改变 |
| 学习导出 | `scalable3d-learning-export-v2` | D3/D4/D5 训练制品布局或真值隔离规则改变；v2 增加 D5 主动视觉整 episode 在线记录与独立离线标签 |
| 学习生成计划 | `scalable3d-learning-generation-plan-v1` | 场景、规模、seed、正式预检或保留评估 seed 规则改变 |
| 学习生成检查点 | `scalable3d-learning-generation-checkpoint-v2` | 暂停/恢复状态、累计调用计时、计划哈希或完成序号语义改变；v2 在每个完整 episode 后原子推进，并记录严格校验后的旧检查点滞后恢复 |
| 训练 seed 注册表 | `scalable3d-training-seed-registry-v1` | 训练/保留评估 seed 身份、来源或隔离规则改变 |
| 实验矩阵 | `scalable3d-experiment-matrix-v1` | 变体语义、配对键或正式准入条件改变 |
| D1 一致性评估清单 | `scalable3d-offline-consistency-evaluation-manifest-v1` | 在线证据、真值状态、D2 映射或哈希绑定改变 |
| D2 身份评估清单 | `scalable3d-offline-identity-evaluation-manifest-v1` | 谱系映射、身份指标或来源校验改变 |
| D6 真值隔离清单 | `scalable3d-d6-truth-isolated-manifest-v1` | D1/D2 适配、availability 或批量聚合口径改变 |
| D5 模型 | `d5-crossview-gnn-v0.1.0` | 网络、特征、权重或训练集改变 |
| D5 主动视觉 | `d5-active-vision-rule-v1` 或模型语义版本加指纹 | 特征、动作空间、权重或准入报告改变 |
| D5 主动视觉数据 | `d5.active-vision-episode-dataset.v2` | split、episode、在线/离线标签或哈希语义改变；v2 固定共享数值 seed 跨场景原子划分 |
| D5 主动视觉 bundle | `d5.active-vision-model-bundle.v3` | 模型、特征、数据集 schema 绑定或权重改变 |
| D3 策略 | `d3-rl-cost-policy-v0.1.0` | 策略结构、权重或动作定义改变 |
| D4 区域策略 | `d4-region-resource-rule-v1` 或模型版本加权重 SHA 前缀 | 区域特征、动作、安全投影或权重改变 |
| 阈值配置 | `scalable3d-thresholds-v1` | 门限和回退条件改变 |
| 分配计划 | 递增 `plan_version` | 每次发布新计划 |
| 联盟状态 | `epoch + lease + version` | 所有权、成员或有效期改变 |

兼容性新增字段可保留当前主版本。不兼容的字段删除、单位变化、坐标语义变化或行为变化必须升级主版本。模型和策略采用语义化版本号。

## 实验清单

每个输出目录必须包含 `manifest.json`，至少记录：

```json
{
  "git_commit": "<commit>",
  "repository_dirty": false,
  "config_sha256": "<sha256>",
  "scenario_version": "200v200-nominal-v1",
  "seed": 17,
  "world_schema": "scalable3d-world-v1",
  "bus_schema": "scalable3d-episode-bus-v1",
  "d5_model_version": "d5-crossview-gnn-v0.1.0",
  "d3_policy_version": "d3-rl-cost-policy-v0.1.0",
  "d4_policy_version": "d4-region-resource-rule-v1",
  "threshold_version": "scalable3d-thresholds-v1"
}
```

bundle 的本地绝对路径不写入 manifest。解析成功后记录语义版本和权重 SHA256；解析失败时
保留规则版本，并在 scenario metadata 与在线诊断中记录请求模式、实际模式和稳定回退原因。

正式验收只使用 `repository_dirty=false` 的结果。开发期脏工作树结果可以用于调试，但报告必须明确标注，不能作为阶段标签依据。

正式学习数据生成必须在启动 episode 前验证训练 seed 与保留评估 seed 零重叠，并验证
D5 主动视觉默认 20% 测试切分可提供至少 20 个唯一未见 seed。生成过程中逐 episode 检查
剩余磁盘；容量不足时停止，不删除或覆盖既有制品。

长批次可以通过 `--max-episodes-per-run` 在完整 episode 边界暂停，并以 `--resume` 继续。
恢复必须保持生成计划、训练 seed 注册表、Git 提交和计划 SHA256 不变，并逐项核对连续
progress 与 batch episode index。未索引、重复或不完整 staging 失败关闭；只有全部 cell
完成后才执行统一数据集最终化。正式标签仍绑定最终生成摘要和冻结 schedule，不以单个分块
替代完整批次证据。
版本 2 checkpoint 在 progress 行同步写盘后逐 episode 原子替换。进程若在 progress 已完整
落盘而 checkpoint 尚未替换的窄窗口退出，恢复入口只在全部 progress、staging、计划顺序、
在线真值隔离和安全字段均通过校验时接受滞后，并记录恢复次数、恢复行数和最后 episode。
checkpoint 领先、staging 领先或来源提交改变仍拒绝恢复。不同 Git 提交产生的 episode 不得
拼接为同一个正式学习数据集。
冻结的 balanced schedule 显式记录 `round_robin_cells_v1`。每轮依次遍历全部声明 cell 的
同一 seed offset，因此连续 45 个 episode 各覆盖一次 9 类场景和 5 档规模；执行顺序变化会
改变 schedule SHA256 和 generation plan，已有 checkpoint 必须拒绝恢复。

批次学习导出在成功最终化后把 episode 索引固化为根目录 `episodes.jsonl`，并删除已经转换
为正式 D3 数据集的重复 staging。任一 finalizer 异常时保留尚未消费的 staging；D4 因 seed
或标签条件未最终化时，其暂存目录继续保留。临时 `_staging/` 路径不属于长期消费合同。

正式实验矩阵还必须记录 R0/G1/A1/A2/A3/C1/F1、完整场景目录、5/20/50/100/200
规模、至少 20 个测试 seed 和训练 seed 注册表摘要。测试 seed 与训练 seed 有交集、模型
bundle 未加载、assist 未准入或运行时回退规则时，相关学习变体不得进入正式比较。矩阵
manifest 只记录版本和摘要，不记录 bundle 的本地绝对路径。

每个持久化 episode 的 D1、D2 和 D6 子目录分别保存独立 manifest。D1 结果必须绑定在线
总线、离线真值状态和 D2 规范映射；D2 结果必须绑定原始 D1/D2 记录、观测真值标签和身份
证据；D6 在消费前重新校验结果文件及 D2 四类来源文件 SHA256。缺文件、哈希不一致或真值
隔离未验证时，指标保持 unavailable，不能填零。

## 模型文件

- 训练中间检查点和临时数据放入忽略目录，不进入普通 Git 提交。
- 长期保留的模型权重使用 Git LFS 或独立制品存储。
- 仓库提交模型说明、训练配置、数据集版本、输入特征定义和权重 SHA256。
- 在线加载权重前校验模型版本、特征版本和 SHA256；不匹配时回退规则路径。

## 阶段标签

阶段验收后由 main 创建带说明标签：

| 标签 | 验收范围 |
| --- | --- |
| `scalable3d-v0.1.0` | 三维环境、传感器和真值隔离 |
| `scalable3d-v0.2.0` | 200v200 规则跟踪和分配基线 |
| `scalable3d-v0.3.0` | D5 稀疏图关联 |
| `scalable3d-v0.4.0` | D3 学习代价修正和规则回退 |
| `scalable3d-v0.5.0` | 区域降级和三维导引闭环 |
| `scalable3d-v1.0.0` | 20 个未见 seed 的最终验收 |

标签只在对应测试、实验产物、GAP/PLAN 和中文报告齐全后创建。当前阶段未达到要求时不得提前打标签。
