# D5 跨视角图模型稳健候选复核

## 结论

本轮形成一份新的开发候选，权重 SHA-256 为
`7fb5db8b6099ca4da5706a3bec53ff7cd634e8bd267c036ce3ee4ee4bf71ca71`。候选在
900 帧合成保留集和同图配对影子评估中通过既有分类、困难扰动和单特征捷径门限。它没有获得
G1 辅助准入。训练来源处于脏工作树，D6 外部审计和 G1 证据装配均未运行，模型状态固定为
`development_only_fail_closed`。

旧权重 `99fa4428...d4cd` 及其 post-assembler 审计保持原状。旧模型的五项 blocker 没有通过
重写清单、修改报告、放宽门限或增加兼容名单消除。

## 改进内容

补充课程在每个相机局部量测上加入标签无关的测量误差。误差覆盖检测框尺度、尺度变化率和角速度，
并由匿名 observation ID 确定随机序列。不同相机对同一目标不再得到完全一致的尺度和运动特征。
该过程不读取 evaluator truth 或边标签。

训练增加三类确定性困难视图：

1. `occlusion_reappearance_proxy` 降低部分局部轨迹置信度、增加轨迹年龄和时间差。
2. `similar_motion_confusers` 去除运动与尺度变化特征中的简单区分线索。
3. `independent_bbox_scale_jitter` 独立扰动节点和边的尺度、尺度变化率。

困难视图只修改只读特征副本，不改变候选边拓扑，不读取标签。原图与三个困难视图在每轮共同参与
训练。模型实现谱系与完整运行时谱系分开记录，并要求四个模型源码哈希在两套谱系中逐项一致。
模型实现摘要为
`1883bc36834f7ccd1c5b7a9cbdecf04f40615686ba3cf89bd13be20ce3a06105`，
运行时实现摘要为
`408e71fe6a31bca03de61d10cefbf73c6b32e193fd6b2d7bf734389972f9f4fe`。

## 数据边界

补充课程生成 4,500 个图帧、66,726 个匿名局部航迹节点和 370,190 条候选边，其中正边
83,478 条、困难负边 286,712 条。组合训练视图包含 4,972 个图帧，训练、验证和内部测试分别为
2,961、1,006 和 1,005 帧。100 个 numeric seed 按固定规则划分为 60/20/20，独立保留集使用
seed `1000-1019`，不参与训练、温度拟合或阈值选择。

组合数据的数据量与标签门通过，但训练准入因
`supplemental_source_repository_dirty` 失败关闭。训练命令只以显式
`exact_source_hashes_dirty_development` 模式生成诊断候选，不声称 clean source。训练来源记录的
Git 提交为 `42c5e2e7e45b18fb262ce55b27d294fecdc7fc03`，`repository_dirty=true`。

## 训练结果

| 项目 | 实测值 |
| --- | ---: |
| 训练轮次 | 12 |
| 最佳轮次 | 11 |
| 每轮图呈现数 | 11,844 |
| 训练耗时 | 234.6347 s |
| 温度 | 0.6541651703 |
| 决策阈值 | 0.8964798918 |
| 权重大小 | 202,805 bytes |
| bundle manifest SHA-256 | `ddd7ce4aa0fc5e9b01e1c388992f6e443aebcf4484ac9f0c09727a66bad72f17` |

训练只生成 development v3 bundle。`default_model=false`、`g1_assist_eligible=false`，规则几何
评分仍是运行时默认与异常回退路径。

## 保留集结果

seed `1000-1019` 的 900 帧保留集覆盖 45 个场景规模单元和 74,024 条候选边。冻结权重、温度和
阈值后得到：

| 指标 | 实测值 | 既有门限 |
| --- | ---: | ---: |
| 精确率 | 1.000000 | >= 0.95 |
| 召回率 | 1.000000 | >= 0.90 |
| F1 | 1.000000 | >= 0.92 |
| 错误合并率 | 0.000000 | <= 0.01 |
| 候选召回率 | 1.000000 | >= 0.95 |
| 期望校准误差 | 0.0000346724 | <= 0.05 |
| CPU 推理 P95 | 1.121304 ms | <= 100 ms |

held-out manifest SHA-256 为
`2fb31717318590d11de8f2093be6d60179956ca369ffe9f91dffec2a0f71c502`，评估报告文件
SHA-256 为
`7e1319108bb7105766d1cbafc5f041556aa54c6d2661ad05a5543099b3e50931`。

## 配对影子结果

同一 900 帧匿名图和相同候选边分别送入确定性规则与冻结模型。模型名义边 F1 和簇 F1 均为
1.000000，五类困难扰动的模型边 F1 和簇 F1 也均为 1.000000。最高单特征 AUC 为
0.7200734257，对应角速度差，满足既有 `<=0.98` 门限。在线 truth 特征、同相机互斥违规和
`global_track_id` 改写均为 0；9 类模型异常仍全部逐值回退到规则概率。

paired-shadow 报告文件 SHA-256 为
`595d0c5afb2c34042fad48c257df613c3daf19dd3b23874b56440ecc1c713582`，lineage SHA-256 为
`76cda5bad8479940c6d1ed528c8addc897ed46419e8313e7ee3071d8352193e4`。

这些结果来自固定候选拓扑的合成专项数据。它们不能解释为真实相机、AirSim、重新执行几何候选门
或物理拦截性能。

## Blocker 状态

| 旧 blocker | 新候选结果 | 当前准入判断 |
| --- | --- | --- |
| `implementation_evidence_unavailable` | 记录了模型和完整运行时源码哈希 | 脏来源没有 clean commit 证据，未关闭 |
| `implementation_lineage_mismatch` | D5 内部 bundle、held-out 和 paired-shadow 绑定同一运行时摘要 | D6 外部审计未运行，不能宣称正式关闭 |
| `robustness_threshold_not_met.edge_f1` | 五类合成扰动最小 edge F1 为 1.000000 | 专项门通过，真实重新构图仍待验证 |
| `robustness_threshold_not_met.cluster_f1` | 五类合成扰动最小 cluster F1 为 1.000000 | 专项门通过，真实重新构图仍待验证 |
| `synthetic_single_feature_shortcut` | 最高单特征 AUC 为 0.7200734257 | 当前合成保留集门通过，独立真实数据仍待验证 |

最终剩余阻断为：

- `source_repository_dirty`
- `clean_commit_retraining_required`
- `d6_external_audit_not_run_dirty_source`
- `g1_assembler_not_run_dirty_source`

## 安全检查

在线图继续只使用匿名相机局部轨迹、双时间戳、协方差和几何特征。truth 只在模型与规则两臂完成
预测和聚类后用于离线评分。D5 未创建、重写或换绑 `global_track_id`。候选门、同相机互斥、
友方冲突、版本和控制权限门限均未放宽。

2026-07-26 最终模块回归为 `578 passed in 103.88s`。十个新增或修改 Python 文件通过
`python3 -m py_compile`。

## Clean Commit 重跑

下一次必须从包含本轮实现的 clean commit 重新生成以下制品，不能复用本轮 dirty-source 结果申请
准入：

1. supplemental curriculum 与 composite admission；
2. development model bundle、权重和清单；
3. seed `1000-1019` held-out corpus 与评估报告；
4. paired-shadow 报告和逐 episode lineage；
5. 稳定 model registry reference 与 evidence；
6. D6 外部独立审计；
7. 仅在前六项全部通过后运行 G1 evidence assembler。
