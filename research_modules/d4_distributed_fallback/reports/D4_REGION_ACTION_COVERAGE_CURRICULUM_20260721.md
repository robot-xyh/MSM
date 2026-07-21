# D4 区域动作覆盖课程报告

## 结论

2026-07-21，D4 完成独立区域动作覆盖课程的生成和审计能力。课程复用现有区域资源快照、规则策略、确定性安全投影、episode 数据集和共享 seed 注册表，不修改正式 900 episode 数据。

本次开发产物包含 100 个数值 seed、100 个 episode 和 300 帧。四类稀缺标签均已覆盖：保持 100 个，请求重规划 200 个，非零配额动作 200 个，跨区转移 100 个。硬约束违规、在线真值字段和保留 seed 泄漏均为 0。

课程没有真实可观测任务结果。300 帧 reward 和 outcome 全部标记为 unavailable。PPO、在线 assist 和 authority 准入保持关闭。当前工作区包含并行未提交改动，实际课程的 100 个 episode 均标记为 dirty，只能用于结构审计；main 在代码合并后的 clean worktree 中重新生成，才能交给默认行为克隆加载器。

## 课程构造

每个数值 seed 生成三帧完整 episode。区域数和资源总数由输入参数决定，本次使用 4 个区域和 17 份聚合资源，二者没有等量约束。

1. **保持帧**：一个区域出现聚合降级失败信号。规则策略输出 `hold=true` 和 `request_replan=true`，其他区域维持平衡。该信号不绕过 owner、版本、租约或资源投影。
2. **重规划帧**：一个区域出现分配冲突，区域边处于不可转移状态。规则策略输出 `request_replan=true`，不生成资源转移。
3. **转移帧**：一个相邻区域有安全余量，另一区域存在可由该余量消解的需求缺口。规则策略提出跨区转移，确定性投影据此重建源区负配额和目标区正配额。

区域位置随 seed 确定性轮换。相同配置、seed、Git 来源和创建时间会得到相同 episode 内容、数据集 SHA256 和 canonical view SHA256。

## 数据治理

课程读取正式训练 seed 注册表和共享切分注册表。源注册表文件 SHA256 为 `2ab928a476a4430b99326f245222f058bc5be5025158134ba89b01b3dec7815f`，共享注册表文件 SHA256 为 `68608d29d1f733beea87f1faf06464fededb68a9c2972c51c10cd4c2160f032f`。

数据集先按 D4 既有 finalizer 写入新的独立目录，再由 `d4-canonical-region-seed-split-view-v1` 建立只读 60/20/20 视图。原 manifest 不改写。保留 seed `1000-1019` 不进入课程。

| 切分 | seed | episode | frame | 保持 | 请求重规划 | 非零配额动作 | 跨区转移 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 训练 | 60 | 60 | 180 | 60 | 120 | 120 | 60 |
| 验证 | 20 | 20 | 60 | 20 | 40 | 40 | 20 |
| 测试 | 20 | 20 | 60 | 20 | 40 | 40 | 20 |
| 合计 | 100 | 100 | 300 | 100 | 200 | 200 | 100 |

课程数据集 SHA256 为 `b3739fefa6f082713af4ecf6a5dcb72cd73fd6dfb39d32cdf40c272cab2390ef`。canonical view SHA256 为 `aa92705a308a1387648731f10c8380dcac614301b8f298202ec2902e08beebae`。结果摘要保存在同目录的 JSON 文件中。

## 安全审计

每个 teacher target 都由 `RuleRegionResourcePolicy` 生成，再经 `DeterministicResourceProjector` 投影。审计重新构造 advisory contract，检查区域动作全集、资源总量、转移净流量、边容量、通信与机动可用性、最低备用、owner、plan version、epoch 和 lease。

| 审计项 | 结果 |
|---|---:|
| 硬约束违规 | 0 |
| 资源守恒失败 | 0 |
| 在线真值或目标身份字段 | 0 |
| 保留 seed 泄漏 | 0 |
| reward available | 0/300 |
| outcome available | 0/300 |
| PPO 可用 | 否 |
| 在线 assist 可用 | 否 |

课程只提供规则 teacher 的动作覆盖。它不证明 teacher 优于现有规则，不包含动作执行后的真实收益，也不改变 D4 健康状态机、二级接管、联盟提交、D3 计划或 D7 门控。

## 验证

专项测试共 6 项，覆盖动作分布、真值隔离、确定性、安全投影、60/20/20 canonical 切分、保留 seed 隔离、reward unavailable、行为克隆加载和 PPO 失败关闭，结果为 6/6 通过。D4 全量回归为 387/387 通过。

clean fixture 中 canonical 训练桶可加载 180 个行为克隆样本。PPO loader 因 reward unavailable 按预期拒绝。实际开发产物因来源 dirty，`behavior_cloning_manifest_available=false`；该状态是来源治理门，不是课程内容错误。

复核命令：

```bash
PYTHONPATH=research_modules/d4_distributed_fallback \
python3 -m pytest -q research_modules/d4_distributed_fallback/tests

PYTHONPATH=research_modules/d4_distributed_fallback \
python3 -m d4_distributed_fallback.region_resource_curriculum_cli \
  --output-dir <new-output-dir> \
  --training-seed-registry <training_seed_registry.json> \
  --shared-seed-registry <shared_registry.json> \
  --created-at-utc <UTC timestamp> \
  --region-count 4 \
  --resource-count 17
```

## 剩余工作

1. main 合并 D4 后在 clean worktree 重生课程，并固定生成提交和结果 SHA256。
2. 将课程作为补充 teacher 数据，与正式观测分布分开报告。训练报告必须给出两类数据的采样比例，避免模型只学习人为构造状态。
3. D6 仍需从真实 episode 提供可归因 outcome、reward、causal 和 counterfactual 证据。缺少这些字段时继续禁止 PPO。
4. 使用保留 seed `1000-1019` 运行规则基线与候选模型的成对 shadow 评估。安全、积压、通信、转移耗时或计划抖动退化时不得进入 assist。
