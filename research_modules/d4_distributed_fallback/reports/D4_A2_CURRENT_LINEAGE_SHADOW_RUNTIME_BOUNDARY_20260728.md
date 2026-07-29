# D4 A2 当前谱系影子运行边界

## 结论

当前谱系 A2 候选已经具备可信加载、逐帧影子推理、确定性安全投影、逐特征分布外诊断和
内容寻址复核能力。候选仍不具备运行分布兼容性。main 于 2026-07-28 执行了两组开发预检：
5 个资源、5 个目标、2 个区域的 3 个快照，以及 200 个资源、200 个目标、8 个区域的
2 个快照。两组共 5/5 快照均被固定分布外门拒绝，模型实际执行数为 0，在线真值使用数为
0，有限状态检查正常。

该结果是当前正式 20-seed 评价的阻断项。不能通过增大分布外余量、降低置信门、复用规则
派生动作或把影子投影写成实际采用来绕过。候选的准入、辅助、分配、接管、联盟提交和控制
权限继续全部关闭。

## 固定候选

只读适配器固定核验以下身份：

- clean commit：`b0d498d9e76e19e9045e127b6dae26ea164b3fa4`
- candidate manifest 文件 SHA-256：
  `7cc10ad770bd95fcb813dbf3d16b17040ec5f41f80fe0dc53e3e291a32f4de64`
- candidate manifest 内容 SHA-256：
  `b51f2ed01d7f8b963166fe1d7e73acd6a481c5359d54ed5c3712371733aa6ba9`
- 模型权重 SHA-256：
  `fd1b9c4cf7580083fadc04a70b87aa6439930eba764a970279611ccc57f30047`
- 源码身份 SHA-256：
  `b81780cece11c792acb3113af2d4be48a19b51c0337a67c926b388197d09dfdf`

加载过程只读取候选 manifest、源码摘要、模型 manifest、权重和内嵌数据集 manifest。
运行入口不接受数据集目录，不读取 train、validation、test、历史 calibration 或
reserved episode payload，也不提供重训和门限修改参数。

冻结原始字节已登记到
`research_modules/d4_distributed_fallback/model_registry/region_resource_a2_current_lineage_development_v1/`。
该目录包含候选 manifest、源码/数据/训练摘要、训练配置及 bundle 三个文件，与原
`outputs/` 候选逐字节一致。登记使 clean clone 可以复核固定候选，不改变其
development/shadow、运行分布不兼容和权限全闭结论。

## 影子流程

main 先为每个开发或正式 episode 提供 seed 注册。注册内容包括 episode、场景、seed、
registry 版本、候选绑定以及完整 calibration 排除目录。D4 不产生 seed，也不自动挑选
正式 seed。

每个影子决策按以下顺序处理：

1. 核验候选文件、权重、源码谱系和 development/shadow 权限。
2. 拒绝 train、validation、test、calibration 和 reserved seed 重叠。
3. 核验 episode、seed、场景、帧号、时间戳及各区域 owner、plan、version、epoch 和
   lease。重复帧、时间回退、计划代次回退和同代身份变化失败关闭。
4. 生成不含目标真值的输入摘要，绑定完整区域快照 SHA-256。
5. 使用固定 `ood_margin=0.05` 计算逐节点、逐有向边、逐特征的分布外原因。
6. 运行冻结模型，保存原始区域动作及其 SHA-256。
7. 无论候选门是否通过，都只在影子链执行确定性资源投影，保存投影动作、投影说明和
   advisory 摘要。投影结果不发布给 D3。
8. 按投影后的资源配额、整数备用资源、跨区转移、`hold` 和
   `request_replan` 判断是否存在可辨识非零动作。
9. 返回内容寻址记录。实际执行源固定为规则回退，候选执行标志固定为 false。

独立 verifier 使用同一冻结候选、记录中的实际推理时延和原快照重新执行模型与投影。原始
动作、投影、分类、输入摘要或顺序不一致时，复核失败。

## 分布外诊断

逐特征诊断使用模型训练范围和与原门控完全相同的 5% 余量：

```text
scale = max(abs(training_min), abs(training_max), 1)
accepted_min = training_min - 0.05 * scale
accepted_max = training_max + 0.05 * scale
```

每个越界项记录实体、特征名、特征序号、观测值、训练范围、允许范围、越界方向和超出量。
因此 `feature_ood` 不再只有一个汇总字符串，可以区分传感器不确定度、资源承诺、二级覆盖、
租约和通信边特征的具体偏移。

main 的 5 对 5、2 区域预检给出的主要偏移如下。

| 特征 | 训练范围 | 运行范围 | 越界值数 |
| --- | ---: | ---: | ---: |
| 已承诺资源占比 | 0 至 0 | 0.2 至 0.6 | 6 |
| D1 不确定度对数 | 0.0953 至 0.1823 | 5.0664 至 6.5591 | 6 |
| D2 不确定度对数 | 0.0770 至 0.1222 | 0 至 0 | 6 |
| D5 可见率 | 0.85 至 0.90 | 1.0 至 1.0 | 6 |
| D5 一致率 | 0.87 至 0.92 | 1.0 至 1.0 | 6 |
| 备用资源占比 | 0.0588 至 0.0588 | 0 至 0.2 | 6 |
| 二级覆盖率 | 0.90 至 0.90 | 0 至 0 | 6 |
| 租约剩余分钟 | 2.0 至 2.0 | 0.0833 至 0.0833 | 6 |
| 区域间距离对数 | 6.2166 至 6.3561 | 8.0528 至 8.0528 | 6 |
| 转移时间对数 | 2.3979 至 2.6391 | 5.4179 至 5.4179 | 6 |
| 边带宽对数 | 3.0445 至 3.0445 | 3.7136 至 3.7136 | 6 |

训练课程采用 4 个区域和 17 份聚合资源。主运行预检采用 2 个区域和 5 个资源。图模型支持
可变节点数，因此区域数差异本身不是当前 `feature_ood` 判据；它仍是图拓扑和归一化分布的
外推风险。真正触发门控的是上表中的逐特征越界。

main 预检 JSON 位于
`research_modules/scalable_3d_simulation/outputs/d4_runtime_compatibility_preflight_current_lineage_dev_seed2000/d4_runtime_compatibility_preflight.json`，
文件 SHA-256 为
`de465c7fa5ef971305329a36c1614649cd6136ecef93d23286f425e0eb412296`。
该文件属于 main 生成的开发输出，D4 本轮只读引用，没有修改。

200 对 200、8 区域预检采用开发 seed 2001，运行 1.2 秒。2/2 快照均为
`feature_ood`。稳定越界包括已承诺资源占比 0.115 至 0.13、D1 不确定度对数
6.10 至 6.58、转移时间对数 4.04、租约剩余分钟 0.0833、二级覆盖/就绪度 0、
通信容量/带宽、D5 可见率/一致率和备用资源占比。预检 JSON 文件 SHA-256 为
`41cdbf8f532300521d56b6b30302b4373356ad3056e1576776c703b4ff5a89eb`。
5 对 5 和 200 对 200 的 OOD gate 均与逐特征诊断一致，不能放宽
`ood_margin=0.05`。

## 证据边界

影子记录明确固定以下状态：

- D3 后继计划不可用；
- runtime ACK 不可用；
- owner ACK 不可用；
- coalition ACK 不可用；
- 确认后物理窗口不可用；
- 独立同键 R0 不可用；
- 配对非退化和收益不可用；
- assist、authority、assignment、takeover、coalition commit 和 control 全部关闭。

影子记录中的 `candidate_gate_passed` 只表示固定诊断门是否通过。即使门通过且投影后存在
非零动作，系统仍执行规则路径。该记录不能转换为
`RegionResourceSafeAdoptionEvidence`，也不能替代 D3、main、owner、联盟成员或 D6 的证据。

## 后续候选

下一版候选需要先建设 runtime-compatible 训练视图，不能直接复用本轮 5 帧预检训练模型。
现有两套源数据可作为该视图的基础：

- 运行快照数据：900 episodes、1798 frames、100 个数字 seed，数据集 SHA-256 为
  `b06d741bd22a0cd84ef1e47a48a0b8cd81ceb7e4ea294eeeb38b892e69d36158`。
  它覆盖 D1 不确定度对数 0 至 8.33、已承诺资源占比 0 至 0.6、备用资源占比
  0 至 0.2、0.0833 分钟租约、运行带宽/容量和 8 区域转移几何，但规则目标全为零动作。
- 动作覆盖课程：100 episodes、300 frames、100 个数字 seed，数据集 SHA-256 为
  `7e17aba7911602c1b9e9f5b917aea97f1eeec478f03963b119fbcfc8de299e72`。
  它提供 `hold` 100 次、`request_replan` 200 次、非零资源配额 200 次和跨区转移
  100 次，并补充 D2、D5、二级节点和网络分区变化。

两套数据都使用数字 seed 0 至 99，但各自原始 split 不同。不得直接按原 split 拼接。
训练视图必须先以 `(source scenario, numeric seed)` 保留来源身份，再对数字 seed 0 至
99 执行一次全局原子重分割。同一数字 seed 的全部场景和两个来源必须处于同一
train、validation 或 test 分区。seed 1000-1019 完全排除。清单分别记录两个源数据集
SHA-256、来源角色、场景/seed 库存和各类动作库存。

现有运行快照与动作课程的特征 union 足以覆盖本次 200 对 200、8 区域预检的主要越界。
它不自动证明 5 对 5、2 区域兼容：该场景的区域间距离对数 8.0528 仍高于运行数据覆盖。
下一候选必须把 `region_count=8` 及相应转移几何写入适用域；2 区域输入继续由 OOD 门拒绝并
回退规则路径，直至取得独立覆盖数据。

最小任务分为四步。

1. D4 复用现有复合视图构造逻辑，按共享全局 60/20/20 数字 seed 目录重建 1000-episode
   训练视图；运行快照承担特征覆盖，动作课程承担安全动作多样性。
2. D4 在清单中分别审计两个来源的特征范围和动作库存，并验证 union 覆盖默认
   8 区域运行预检；不把 2 区域几何写成已覆盖。
3. main 冻结 seed registry 和独立 holdout。seed 1000-1019 不进入训练、验证、测试、
   校准、门限选择或运行兼容性调参。
4. 在独立 clean checkout 构建新 development/shadow 候选。先运行非正式 seed 兼容性
   预检，确认出现真实模型动作后，main 才能注册新的正式 20-seed；旧候选和 5% OOD 门
   保持不变。

本轮任务明确禁止重训，当前工作区也包含其他模块未提交改动，因此没有生成新权重或冒充
clean-lineage 候选。已有复合视图构造能力可复用，但下一候选仍需 main 在 D4 代码提交后从
独立 clean checkout 构建。正式 20-seed 在新候选通过运行分布预检前保持阻断。

## 验证

新增测试覆盖固定候选绑定、五类 seed 重叠、重复帧、旧 registry、计划代次回退、seed
跨 episode 复用、权重篡改、非有限模型输出、权限篡改、逐特征 OOD 和全帧 OOD blocker。
专项测试结果为 **17 passed**，D4 全量为 **706 passed**。全量测试只有既有 Matplotlib
`Axes3D` 环境警告，不影响本轮结果。
