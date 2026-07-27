# D5 图模型正式证据

## 结论

2026 年 7 月 27 日，D5 跨视角图模型在干净提交
`8d5e02ec989259ce3d39e1e4ad6a90dd0d8d5b54` 上完成当前运行时证据重建。D6
外部审计和装配后审计均为 `pass`，未发现 blocker。D5 生产装配器据此生成
`d5.tracklet-model-bundle.v5`。

该结论只确认合成匿名候选图上的模型证据资格和 v5 文件完整性。模型晋级、在线图模型
辅助、默认路径变更、分配、故障接管和控制六项权限仍为 false。确定性几何规则继续作为
默认路径。

## 执行边界

正式运行使用 detached clean worktree：

- Git 提交：`8d5e02ec989259ce3d39e1e4ad6a90dd0d8d5b54`
- D5 运行实现摘要：
  `b0708e718b374e5bb52db41c7bd2f994e340a2b009cfd348881a5f9d549baffe`
- 证据目录：
  `/tmp/MSM-d5-g1-formal-evidence-8d5e02e-20260727`
- 证据树：16,262 个普通文件，树 SHA-256 为
  `fa96c41c8b9bf60a131be32c7519a49c7947ebfe73a3f5311ffed4d672a8dd81`

证据目录包含重新生成的 4,500 帧补充课程、development bundle、held-out 语料与评估、
paired-shadow、逐帧 lineage、冻结 registry、D6 外部审计、v5 和 D6 装配后审计。旧
external audit v1、旧 bundle v4 和名称带 v2 但内部仍为 v1 的临时结果未进入本次链路。

## 模型与数据

训练采用原生 PyTorch 图消息传递模型。模型只对既有几何候选边输出“属于同一目标”的
概率，不创建或改写 `global_track_id`。训练后权重 SHA-256 仍为：

`7fb5db8b6099ca4da5706a3bec53ff7cd634e8bd267c036ce3ee4ee4bf71ca71`

development manifest SHA-256 为：

`7d459ed855cf74b810fa1f79ed0327efd39eb4be4409451266da3f3a95387ce0`

保留集固定使用 seed 1000 至 1019，共 20 个未见 seed、900 个 episode 和 45 个场景规模
单元。paired-shadow 使用相同的 900 个匿名图帧，包含 13,344 个局部航迹节点和 74,024
条候选边。离线真值在规则组和模型组完成概率输出及受约束聚类后才进入评分。

## 评估结果

held-out 总体结果如下：

| 指标 | 结果 |
| --- | ---: |
| 精确率 | 1.000000 |
| 召回率 | 1.000000 |
| F1 | 1.000000 |
| 候选召回率 | 1.000000 |
| 错误合并率 | 0.000000 |
| CPU 推理 P95 | 0.913 ms |

paired-shadow 中，确定性规则边 F1 为 `0.367980`，聚类 F1 为 `0.239234`；冻结模型边 F1
和聚类 F1 均为 `1.000000`。最高单特征最佳方向曲线下面积为 `0.720073`，低于
`0.98` 上限。五类真值无关扰动的最低边 F1 和聚类 F1 均为 `1.0`。

这些数值来自合成数据和固定候选图扰动。满分结果不能外推为真实相机跨视角能力，也不能
替代重新执行候选门的物理扰动实验。

## 谱系校验

paired lineage 文件 SHA-256 为：

`83e105290f3e624f267d92ceaf050d32291bd5bbbabf98580846cd31498b1af1`

文件包含 900 条记录和 900 个唯一 `episode_uid`。D5 manifest、准入报告、paired 报告、
D6 外部审计和 D6 装配后审计均绑定同一文件摘要和计数。缺文件、重复编号、记录损坏、
计数变化或摘要不一致均失败关闭。

在线真值特征计数、`global_track_id` 创建或换绑次数、同相机候选边和同相机互斥违规均为
0。

## 两级审计

D6 external audit 输出：

- schema：`d6.d5-g1-external-audit.v2`
- 状态：`pass`
- blocker：空
- 文件 SHA-256：
  `cbd6c72b2d9e7b78bf3aa36f975e6627250d2bf18de5a0b0ebc2c8f6cf760cd6`
- 内容 SHA-256：
  `334cf662e49c735931019ff358be1894d1358f1b4a5a868759eee41d3d282d15`

D5 生产装配器生成的 v5 manifest SHA-256 为：

`b431d066362005868374d038eb93a83b773c03715a53d8a9dfd0da21784f317d`

D6 post-assembly 输出：

- schema：`d6.d5-g1-post-assembly-audit.v2`
- 状态：`pass`
- blocker：空
- 内容 SHA-256：
  `17dda42d06b4be1d21ff8f1f8baecc320fd49b532be06a9f9f6b304341763e1d`

两个 D6 输出目录的 `SHA256SUMS` 均已逐项复核通过。

## 加载行为

v5 通过严格加载和 shadow 加载。manifest 声明
`g1_assist_eligible=true`，表示证据包满足当前合成准入门限。请求在线 G1 辅助时，loader
返回：

`bundle_g1_assist_authority_not_granted`

该行为符合权限设计。证据资格由 D5/D6 证明，运行授权由独立流程决定。D5 和 D6 均不能
给自身授予运行权限。

## 保留缺口

三类证据继续标记为 unavailable：

1. 真实相机和真实目标条件下的跨视角泛化。
2. 中心 `global_track_id` 绑定结果与独立离线真值的正确率。
3. 导引控制和五米物理拦截闭环结果。

下一步先定义 main-owned、人工批准、带作用域和有效期的实验授权包。授权包只允许 G1 在
既有候选边上参与受控评分，不授予身份所有权、分配、降级或控制权限。授权合同完成后，
再使用同一随机种子和外生配置运行 R0/G1 配对作用域，由 D6 检查实际模型采用、回退、
身份安全和相对规则基线的非退化结果。
