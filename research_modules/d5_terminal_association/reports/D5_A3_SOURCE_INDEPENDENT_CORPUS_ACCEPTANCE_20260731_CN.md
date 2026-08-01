# D5 A3 独立来源语料验收

## 结论

2026-07-31 冻结的 A3 主动视觉语料通过 D5 严格文件、来源和完整性校验。100 个 episode
来自 100 个 seed，覆盖 45 个场景规模单元，共 159,487 个策略样本。全部 episode 显式声明
三维质点运行来源，生产提交为 `4a8c1173179b4058d4aee38178e0fb40ecd222b3`，dirty episode
为 0。

该语料没有通过训练结构门。训练集中 `hold=0`，高空侦察相机没有 `search_sector` 示范。
组合训练入口按 13 个原因失败关闭。D5 未启动行为克隆、近端策略优化或辅助模式，也未授予
模型、相机、分配、接管、运行、生产、控制和全局编号写权限。

## 数据绑定

| 项目 | 结果 |
| --- | --- |
| 冻结日期 | 2026-07-31 |
| D5 严格复核日期 | 2026-08-01 |
| episode / seed / 场景规模单元 | 100 / 100 / 45 |
| seed 范围 | 21000-21099 |
| 样本数 | 159,487 |
| train / validation / test episode | 60 / 20 / 20 |
| train / validation / test 样本 | 102,610 / 23,458 / 33,419 |
| manifest SHA-256 | `bccbdad42a71b130720469bb4e99dd1dd99e29a9b33af036679b9d64b0fe35a4` |
| split SHA-256 | `aaad1f7d12f3d383e1d1a6d9160c534ad6a76c3281397cc421e893369cb761cd` |
| training-set SHA-256 | `4d2056c8e66f335a8a8ebf6843840ac9c9a60899263349aad222676301f15f35` |
| corpus-audit SHA-256 | `85db29f86d924a437259a478e2fb182c220d3469c8f8a0c4374820e61e6ef74e` |

严格 CLI 返回 `valid_detached_immutable_dataset`。manifest SHA、分割 SHA、训练集 SHA、
dataset config SHA、逐文件校验和和只读属性均由 loader 重新验证。来源清单为
`scalable_3d_point_mass_runtime=100`，`synthetic_fixture=0`，来源声明覆盖 100/100。

显式排除清单为正式保留 seed 1000-1019，与 train、validation、test 均无交叉。该检查由
D5 调用时显式传入，审计字段为 `explicit_development_argument`，不冒充 canonical registry
的正式绑定。

## 训练覆盖

训练集 102,610 个样本全部通过单样本完整性检查，没有 truth 字段、重复样本、非有限特征或
禁止 seed 被排除。动作和角色分布仍不完整。

| 动作意图 | 全训练集 | 拦截机 | 高空侦察机 |
| --- | ---: | ---: | ---: |
| 保持 | 0 | 0 | 0 |
| 观察目标 | 1,795 | 1,727 | 68 |
| 重捕获 | 98,094 | 93,947 | 4,147 |
| 搜索扇区 | 2,721 | 2,721 | 0 |

训练门共有 13 个失败原因。`hold` 缺少总体样本、episode 和 seed；`hold+interceptor`、
`hold+recon`、`search_sector+recon` 分别缺少样本、episode 和 seed。来源研究门单独返回
`point_mass_simulation_research_eligible`，九项合同检查全部为真。组合入口先要求训练结构
通过，因此最终拒绝训练和晋级。

补采计划固定为三项：

1. `AV-CORPUS-001`：`hold + interceptor`，至少 2 个新训练 seed、2 个完整 episode、
   2 个唯一样本。
2. `AV-CORPUS-002`：`hold + recon`，至少 2 个新训练 seed、2 个完整 episode、
   2 个唯一样本。
3. `AV-CORPUS-003`：`search_sector + recon`，至少 2 个新训练 seed、2 个完整 episode、
   2 个唯一样本。

三项请求的建议场景均为 `center_failure-200v200-v1`。新增数据必须使用新的训练 seed 和完整
episode，不能用复制、过采样、重加权或验证/测试样本补足。

## 运行记录

全语料 159,487 个样本均有运行 ACK，接受 159,487，拒绝 0。ACK 只证明语料保存了运行响应
记录。离线 outcome、reward、counterfactual 和 causal label 全部不可用，当前 ACK 不能单独
证明动作在外部运行环境中产生了有效物理结果。

159,487 个样本均有匿名 `observation_key`，键值全部唯一。episode dataset 没有保存 A3
物理匿名观测帧或离线结果，因此匿名键覆盖不能解释为目标可见率、关联正确率或实际相机收益。
这三项证据继续标为不可用。

## 权限边界

语料审计固定记录在线 truth 使用为 0，中心 `global_track_id` 创建或改写为 0。formal
candidate、assist、主动视觉、相机命令、分配、降级、runtime、production、control 和
`global_track_id` 写权限全部为 false。下一步只执行三项版本化补采请求；完成新的严格审计前，
不训练、不晋级、不切换默认规则路径。

机器可读摘要见
`results/a3_source_independent_corpus_acceptance_20260731.json`。

## 软件回归

新增 CLI 回归为 `1 passed`，episode dataset 专项为 `19 passed in 3.55s`。D5 全量为
`770 passed, 2 warnings in 102.24s`，零失败。两条警告来自既有 Matplotlib `Axes3D` 导入
环境和 NVML 初始化，不涉及数据校验、训练门或权限判断。`git diff --check` 通过。
