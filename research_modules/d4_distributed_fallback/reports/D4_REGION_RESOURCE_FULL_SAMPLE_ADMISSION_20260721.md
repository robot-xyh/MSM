# D4 区域调度全样本准入审计

验证日期：2026-07-21。审计模式为只读、失败关闭。

## 结论

正式数据全样本状态为 `complete`，补充课程状态为 `complete`，联合状态为 `complete`。
本审计没有训练行为克隆或近端策略优化模型，没有写入权重，也没有开放在线辅助或裁决权限。

## 数据规模

| 数据 | episode | frame | sample | action | 规范切分 |
|---|---:|---:|---:|---:|---|
| 正式区域数据 | 900 | 1798 | 1798 | 14384 | 60/20/20 seed |
| 补充规则课程 | 100 | 300 | 300 | 1200 | 60/20/20 seed |

sample 定义为一个区域资源帧。action 是该帧中按区域输出的投影后动作。

## 正式数据

| split | episode | frame | sample | action |
|---|---:|---:|---:|---:|
| train | 540 | 1079 | 1079 | 8632 |
| validation | 180 | 359 | 359 | 2872 |
| test | 180 | 360 | 360 | 2880 |

动作总数 14384；hold=0，request-replan=0，非零配额=0，跨区转移=0。

数值有限样本 1798/1798，安全合同有效样本 1798/1798。

## 补充课程

| split | episode | frame | sample | action |
|---|---:|---:|---:|---:|
| train | 60 | 180 | 180 | 720 |
| validation | 20 | 60 | 60 | 240 |
| test | 20 | 60 | 60 | 240 |

动作总数 1200；hold=100，request-replan=200，非零配额=200，跨区转移=100。

数值有限样本 300/300，安全合同有效样本 300/300。

补充课程只证明结构、有限值、动作覆盖和确定性安全约束。它不提供真实运行时成员确认、执行结果、回报、中心或二级接管效果，也不提供网络分区效果。
正式数据和补充课程中的 `target.kind=rule` 都只表示规则教师标签；`recommendation.projected=true` 只表示建议通过确定性投影，不表示动作已执行或已收到运行时确认。

## 文件与来源

- 正式数据：`research_modules/scalable_3d_simulation/outputs/learning_generation_v1_multibatchfix/learning_dataset/d4_region`
- 补充课程：`research_modules/d4_distributed_fallback/outputs/region_action_coverage_curriculum_20260721_clean_9445ed6/dataset`
- 共享切分：`research_modules/scalable_3d_simulation/outputs/learning_generation_v1_multibatchfix/shared_seed_split_registry_v1/registry.json`
- 审计 JSON：`research_modules/d4_distributed_fallback/reports/D4_REGION_RESOURCE_FULL_SAMPLE_ADMISSION_20260721.json`

| 项目 | 正式数据 | 补充课程 |
|---|---:|---:|
| 数据文件数 | 901 | 101 |
| episode 哈希通过 | 900 | 100 |
| 审计期间源文件未变化 | true | true |

审计内容 SHA256：`94f4f4bf914dde9fee0ce1d92ac491902019dd7388502fbee5f96c4edfac3e7f`。本次 tracked JSON 文件的带外 SHA256 为 `4245f1db36f1af47259554f0770e75a3fe97fcc5e9b75c1b04c83d5bfb5c9e46`；D6 必须先按显式路径复算文件哈希，再读取内容和 availability。

## 未闭合证据

- 显式投影前动作掩码未记录，状态为 unavailable。
- 旧计划、旧时期和过期租约的被拒候选未作为样本记录，状态为 unavailable。
- 真实运行时 CoalitionMemberAck、执行结果和可归因回报未记录。
- 同 seed 规则与候选策略的 paired shadow 证据未形成。
- 上述证据闭合前，确定性区域规则、lease/epoch 和安全投影仍是唯一可执行路径。

## 审计状态

通过：`true`；违规数：0。
