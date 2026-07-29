# D4 A2 当前谱系候选诊断

## 结论

D4 已补齐“当前实现谱系候选构建与复核”软件入口。新入口只读取既有训练切分和验证切分：
训练切分用于参数更新，验证切分用于早停和模型选择。数据集测试切分不读取，历史 calibration
切分和 seed 1000-1019 不进入构建或选择。

首次检查时主工作区存在未提交代码和未跟踪资料，clean-lineage 检查按预期返回
`source_worktree_dirty`，当时没有伪造 clean 结论。main 完成分批提交后，D4 已从独立
clean checkout `b0d498d9e76e19e9045e127b6dae26ea164b3fa4` 生成当前谱系
development/shadow 实物，并完成第二次 `review-only`。该实物没有形成 A2 准入、实际
采用、收益、接管、分配或控制证据。

## 旧流程审计

`region_resource_training.py` 的参数更新和早停本来使用训练、验证切分，但模型包生成后会遍历
测试切分计算开发指标。`region_resource_development_candidate.py` 还会把原测试切分作为
`test_as_independent_calibration`，用于置信度、时延、分布外和候选门诊断。该产物可以保留为
历史 development 证据，不能作为本轮当前谱系候选。

模型包 v2 的边界保持有效。writer 只允许 `development + shadow`，loader 会复核权重、
模型结构和训练数据清单，`assist_admitted` 固定为 false。新入口没有修改模型包的权限
语义，只在外层增加源码、配置、数据和切分复核。

## 实际构建

clean checkout 的 `HEAD` 为 `b0d498d9e76e19e9045e127b6dae26ea164b3fa4`，tree 为
`8e62257a078d85cc40f62b3f5a8238f9f24079af`。构建前后
`git status --porcelain=v1 --untracked-files=all` 均为空。

实际输出位于 Git 忽略目录
`research_modules/d4_distributed_fallback/outputs/region_resource_a2_current_lineage_development_v1`。
没有执行 `git add -f`。主要内容身份如下：

| 对象 | SHA-256 |
| --- | --- |
| 候选 manifest 文件 | `7cc10ad770bd95fcb813dbf3d16b17040ec5f41f80fe0dc53e3e291a32f4de64` |
| 候选 manifest 规范内容 | `b51f2ed01d7f8b963166fe1d7e73acd6a481c5359d54ed5c3712371733aa6ba9` |
| 模型权重 | `fd1b9c4cf7580083fadc04a70b87aa6439930eba764a970279611ccc57f30047` |
| 模型 manifest 文件 | `d9fcdb348b3de8fd139b5052a4e7123a48641975cc7dcc708701a2a72ff7ab00` |
| 数据集 manifest 文件 | `82819c2470505e61da753d0d24ddf910e154435cd8d2cbd0a979dfb3dd643904` |
| 数据集内容 | `7e17aba7911602c1b9e9f5b917aea97f1eeec478f03963b119fbcfc8de299e72` |
| 数据切分 | `b413fa810ae426ad143b713afac2c7a3366fae123e397054dbb9b0449d7b0c16` |
| 源码身份 | `b81780cece11c792acb3113af2d4be48a19b51c0337a67c926b388197d09dfdf` |
| 源码摘要文件 | `d4d678a3f1625e01999dde819641c57a7f29a0055b992cf7c0e8677f268ad9a7` |
| 训练配置文件 | `a534c9ae4bd4b53613f5618d51d74e66823de31082b71f3c2618069bbc5cd3ce` |
| 训练摘要文件 | `0fccf4ba2d5323ee6ead0043360c1d902680dc527d0bf2b3ffb24bc45b48402d` |

训练目录包含 60 个 seed、180 个样本；验证目录包含 20 个 seed、60 个样本；20 个 test seed
只保存在 manifest 目录中，episode payload 没有读取。训练完成 60 epoch，最佳 epoch 为
60，最佳 validation loss 为 `0.2042998969554901`。validation 置信度范围为
`0.6390655040740967` 至 `0.7147282361984253`，非有限输出为 0。

`review-only` 重新加载 manifest、权重和内嵌训练数据 manifest，并在同一 clean commit
重新计算源码、数据与 validation 输出。结果为 `clean_lineage_verified=true`、
`train_validation_only_verified=true`、`bundle_loadable=true` 和
`development_shadow_verified=true`。

## 非零动作诊断

独立诊断没有调用 historical calibration 批次入口。它只加载 train 和 validation，并对
每个 frame 调用实际 `LearnedRegionResourcePolicy`，随后复用固定候选门、确定性投影和 D3
消费检查。`minimum_confidence=0.60`、`ood_margin=0.05` 和功能性分类时延覆盖均保持原值，
没有依据结果调参。

| 切分 | seed | 样本 | 门通过/回退 | 安全非零 | 与基线相同 | 资源不可行 | 非有限 | 原始动作签名 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| train | 60 | 180 | 180/0 | 168 | 12 | 0 | 0 | 11 |
| validation | 20 | 60 | 60/0 | 54 | 6 | 0 | 0 | 10 |

模型身份错配为 0。12 个 train 样本和 6 个 validation 样本均为投影后没有 D3 可消费变化，
分类为 `action_same_as_baseline`，没有误写成资源不可行。该结果说明当前谱系实际模型在动作
覆盖课程的已见开发分布上不是全 no-op。train 用于参数更新，validation 用于模型选择，
两者都不是独立未见评价。诊断规范摘要 SHA-256 为
`772763f9cf81b4aabab51f158d66f902adede5b80b4a5ec95337a757fa9edad6`。

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

## 已执行命令

下面命令已经执行，不包含脏工作区、切分或权限绕过：

```bash
export CLEAN_ROOT=/tmp/MSM-d4-current-lineage-b0d498d
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
manifest 文件 SHA-256 和干净源码提交号。后续评价必须引用上述冻结身份。

## 开放项

当前谱系 development/shadow 实物构建缺口已经关闭。仍需至少 20 个未见 seed，且不能回看
结果调整当前候选。每个正式 treatment 仍需非零模型干预、严格 D3 后继计划、运行确认、
owner/coalition ACK、确认后的物理窗口、独立同键 R0 和 D6 配对非退化审计。

这些证据齐备前，A2 只保留 development/shadow 状态。二级接管、完全分布式联盟、分配和
D7 控制继续使用确定性路径。
