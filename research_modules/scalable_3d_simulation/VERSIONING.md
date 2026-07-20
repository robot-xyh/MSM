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
| D5 模型 | `d5-crossview-gnn-v0.1.0` | 网络、特征、权重或训练集改变 |
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
