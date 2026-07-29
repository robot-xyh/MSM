# D4 A2 当前谱系候选诊断

## 结论

D4 已补齐“当前实现谱系候选构建与复核”软件入口。新入口只读取既有训练切分和验证切分：
训练切分用于参数更新，验证切分用于早停和模型选择。数据集测试切分不读取，历史 calibration
切分和 seed 1000-1019 不进入构建或选择。

当前项目工作区存在未提交代码和未跟踪资料，clean-lineage 检查按预期返回
`source_worktree_dirty`。本轮没有生成当前分支候选实物，也没有形成 A2 准入、实际采用、
收益、接管、分配或控制证据。

## 旧流程审计

`region_resource_training.py` 的参数更新和早停本来使用训练、验证切分，但模型包生成后会遍历
测试切分计算开发指标。`region_resource_development_candidate.py` 还会把原测试切分作为
`test_as_independent_calibration`，用于置信度、时延、分布外和候选门诊断。该产物可以保留为
历史 development 证据，不能作为本轮当前谱系候选。

模型包 v2 的边界保持有效。writer 只允许 `development + shadow`，loader 会复核权重、
模型结构和训练数据清单，`assist_admitted` 固定为 false。新入口没有修改模型包的权限
语义，只在外层增加源码、配置、数据和切分复核。

## 构建边界

构建开始前执行整个工作区检查。源码摘要绑定当前 Git 提交、树对象、五个实现文件的逐文件
SHA-256 和聚合摘要。任何已修改、已暂存或未跟踪文件都会使构建失败；没有
`allow-dirty`、`skip-lineage` 或权限绕过参数。

数据读取使用切分选择器。完整 manifest 用于复核不可变切分和数据来源，episode payload
只读取 `train` 和 `validation`。候选 manifest 明确记录：

- 训练、验证和未触碰测试 seed 目录；
- train/validation 实际读取 episode 数；
- `test_payload_read_count=0`；
- `calibration_seed_use_count=0`；
- `reserved_seed_use_count=0`；
- 数据集 manifest、数据集内容和 split SHA-256。

训练配置单独内容寻址。候选清单同时绑定配置、源码摘要、数据摘要、模型 manifest、模型
权重、模型内嵌训练数据 manifest 和训练摘要。复核入口重新检查 clean worktree、源码摘要、
数据切分、所有文件哈希、模型参数及验证切分推理输出。

权限对象包含 A2 准入、辅助建议、权威、分配、接管、联盟提交、控制、实际采用和收益九项
字段。全部字段必须是原生布尔值且为 false。任一字段为 true 时，manifest 构造和严格
loader 均失败关闭。

## 开发夹具

纯 Python 专项使用临时干净 Git 仓库和五个 seed 的微型数据集运行真实命令入口。切分为
3 个训练 seed、1 个验证 seed 和 1 个未触碰测试 seed。模型训练 2 个 epoch，随后从磁盘
加载 bundle，并在验证样本上重新推理。

结果如下：

- 候选可写入、可加载、可复核；
- 测试 payload、历史 calibration 和保留 seed 使用数均为 0；
- 验证非有限输出数为 0；
- 生命周期为 development，最大运行模式为 shadow；
- A2 准入、实际采用、收益及全部运行权限为 false。

该夹具只证明构建器和复核器的软件路径可达。临时仓库不是当前分支 clean-lineage 实物，
五个 seed 也不是正式未见 seed 评价。

## 失败关闭验证

专项测试覆盖以下负例：

1. 工作区存在未跟踪文件时，在读取数据和训练前拒绝。
2. 候选生成后源码形成新的干净提交时，复核按谱系不一致拒绝。
3. 训练、验证、测试或保留 seed 目录重叠时拒绝。
4. 权限字段被改成 true 时拒绝。
5. 配置或其他内容寻址制品被改动时拒绝。
6. 验证推理产生 NaN 或无穷值时拒绝。

2026-07-28，新增专项 **8/8 passed**，D4 全量 **697/697 passed**。另有既有 Matplotlib
三维投影环境警告。未运行 AirSim、900-cell 正式矩阵或正式多随机种子实验。

## Clean rebuild

当前仓库保留三份未跟踪背景资料，因此提交后应在 main 创建的独立干净 checkout 或 worktree
中运行。下面命令不包含脏工作区绕过。`CLEAN_ROOT` 必须指向 main 完成提交后的干净源码树。

```bash
export CLEAN_ROOT=/path/to/clean/MSM
export DATASET=/home/linux/Documents/MSM/research_modules/d4_distributed_fallback/outputs/region_action_coverage_curriculum_20260721_clean_9445ed6/dataset
export OUTPUT=/home/linux/Documents/MSM/research_modules/d4_distributed_fallback/outputs/region_resource_a2_current_lineage_development_v1

cd "$CLEAN_ROOT"
test -z "$(git status --porcelain=v1 --untracked-files=all)"
PYTHONPATH=research_modules/d4_distributed_fallback \
python3 research_modules/d4_distributed_fallback/scripts/build_region_resource_current_lineage_candidate.py \
  --dataset "$DATASET" \
  --repository-root "$CLEAN_ROOT" \
  --output-dir "$OUTPUT" \
  --candidate-id region_resource_a2_current_lineage_development_v1 \
  --model-version d4-region-a2-current-lineage-development-v1

PYTHONPATH=research_modules/d4_distributed_fallback \
python3 research_modules/d4_distributed_fallback/scripts/build_region_resource_current_lineage_candidate.py \
  --dataset "$DATASET" \
  --repository-root "$CLEAN_ROOT" \
  --output-dir "$OUTPUT" \
  --review-only
```

输出目录位于 Git 忽略的 `outputs/`，模型权重不进入普通提交。main 应保存命令输出、候选
manifest 文件 SHA-256 和干净源码提交号，再决定是否安排正式未见 seed 影子评价。

## 开放项

当前谱系候选实物仍待 clean rebuild。实物生成后还需至少 20 个未见 seed，且不能回看结果
调整当前候选。每个正式 treatment 仍需非零模型干预、严格 D3 后继计划、运行确认、
owner/coalition ACK、确认后的物理窗口、独立同键 R0 和 D6 配对非退化审计。

这些证据齐备前，A2 只保留 development/shadow 状态。二级接管、完全分布式联盟、分配和
D7 控制继续使用确定性路径。
