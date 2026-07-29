# 三维学习证据链 P1 复核

## 结论

本轮关闭了四个模块级软件缺口：D3 隔离批次缺少公共严格加载器，D4 无法构建当前实现
谱系候选，D5 行为克隆缺少训练语料结构门，D6 无法从原始制品重算 G1 模型来源。
这些能力使候选生成、加载和审计边界更清楚，但没有形成新的运行授权。

G1 目前只有模型来源和冻结种子两类可信门。实际采用、运行确认、物理窗口、同键规则
基线、成对非退化、真值使用、有限状态和外部权限仍不可用。A1、A2、A3 也没有形成完整
正式证据。G1、A1、A2、A3、C1、F1 的正式学习 episode 均为 0。

## D3 批次加载

D3 新增 A1 隔离批次公共加载器。加载器要求目录只包含固定七个文件，并重新计算
`SHA256SUMS` 覆盖的六项摘要。它逐项复核 20 个 seed、帧范围、候选和选择计数、输入
manifest、模型权重、逐帧 replay、资格摘要及计划版本连续性。

加载器拒绝路径逃逸、符号链接、未知字段、非有限数、摘要篡改和在线 truth/Actor/Object
身份字段。返回对象固定标记为未发布、无运行确认、无物理窗口、无规则基线配对和无生产
权限。该能力只证明离线批次完整，不能把 0/20 binding 变化改写成实际采用。

## D4 当前谱系候选

D4 新增区域资源当前谱系候选构建器。训练数据只来自 train，模型选择和早停只使用
validation。test、历史 calibration 和保留 seed 1000-1019 的读取计数固定为 0。

候选 manifest 绑定源码提交、实现文件摘要、数据集、拆分、训练配置、训练摘要、模型
权重和文件清单。dirty worktree、源码变化、split 重叠、非有限输出、文件篡改和权限字段
升级均失败关闭。当前共享工作区存在并行改动和三份未跟踪背景资料，实测返回
`source_worktree_dirty`，因此没有生成当前分支的 clean-lineage 候选实物。

## D5 训练语料

D5 新增主动视觉训练语料审计。审计按动作意图、拦截机/侦察相机角色、场景、seed、
episode 及其组合统计独立覆盖。缺 `hold`、少数动作、侦察相机或发生 split 污染、
重复 episode、同 episode 样本复制、非有限特征和 truth 字段时，训练前门保持关闭。

补采规划器输出稳定编号的请求，说明需要新增的动作、相机角色、场景、episode 和训练
seed。重加权只改变损失贡献，复制和过采样只增加样本行数，均不能补足独立覆盖。旧 v1
缓存仍可读取用于历史复核，但不能继续训练。历史语料仍缺 `hold`，`observe_target`
召回为 0，侦察相机准确率约 0.622；100 episode、1200 sample 的补充课程属于合成数据。

## D6 模型来源

D6 新增 G1 `model_source` 可信适配器。输入 sidecar 只列出 13 项原始制品的相对路径和
SHA-256，不携带通过断言。适配器逐文件复哈希，并重跑既有 external audit v2 和
post-assembly audit v2。模型身份、实现谱系、固定目录布局、嵌入证据、报告校验和及六项
false 权限均需一致。

本机只读复核使用：

```text
/tmp/MSM-d5-g1-formal-evidence-8d5e02e-20260727
/tmp/MSM-d5-g1-formal-8d5e02e
```

结果为：

```text
source_class=formal_post_assembly_audit
formal=true
component_ids=[d5_graph]
audit_passed=true
model_identity=sha256:7fb5db8b6099ca4da5706a3bec53ff7cd634e8bd267c036ce3ee4ee4bf71ca71
```

该证据树位于临时目录，尚未进入持久只读归档。仓库根不会自动发现或扫描该目录。替代模型、
自签 sidecar、路径逃逸、符号链接、原始制品篡改、模型身份错配和权限升级均被拒绝。

## 验证

| 范围 | 结果 |
| --- | --- |
| D3 全量 | 593 passed，1 skipped |
| D4 全量 | 697 passed |
| D5 全量 | 755 passed |
| D6 全量 | 1138 passed |
| main 复跑 D3/D5/D6 专项 | 46 / 38 / 32 passed |
| 可扩展三维 | 352 passed |
| 跨模块合同 | 8 passed |

D3 的跳过项是可选 OR-Tools。警告来自既有 Matplotlib 三维投影和显卡管理接口环境，
不改变本轮非图形结论。新增 Python 入口语法检查、JSON 校验和 `git diff --check`
均通过。

## 后续工作

1. 本轮提交后，在独立干净 checkout 中生成 D4 当前谱系 development/shadow 候选。
2. 按 D5 补采清单生成非合成训练 episode，覆盖 `hold`、少数动作和侦察相机。
3. 为 A1、A2、A3 增加基于原 producer/auditor 的模型来源适配器。
4. 从同一版本化运行链生成实际采用、ACK、物理窗口、同键 R0 和成对非退化证据。
5. 将 G1 原始证据树归档到持久只读位置，并把可用输出空间恢复到 20 GiB 以上。
6. 条件满足后再启动 900-cell 和完整多 seed；保护线、身份门和权限门不降低。
