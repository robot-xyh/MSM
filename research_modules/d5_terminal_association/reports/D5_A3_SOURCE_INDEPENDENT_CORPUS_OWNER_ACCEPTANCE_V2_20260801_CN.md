# D5 A3 v2 来源独立语料验收

## 结论

D5 于 2026-08-01 对 A3 v2 来源独立主动视觉候选语料完成 owner 验收。严格 loader 全量复载
100 个 episode 和 159,502 个样本，返回 `valid_detached_immutable_dataset`。来源研究门返回
`point_mass_simulation_research_eligible`，训练结构门返回
`pass_development_corpus_only`，组合的质点仿真研究入口通过。

补采针对的三个动作角色单元已经在 train split 自然形成，且均超过
`2 sample / 2 episode / 2 seed` 下限：`hold/interceptor=42,669/60/60`、
`hold/recon=1,772/60/60`、`search_sector/recon=1,023/60/60`。统计没有复制、过采样、
强制标签、重加权或借用 validation/test 样本。

本次通过只说明语料满足开发态结构与质点仿真来源要求。D5 没有启动行为克隆或近端策略优化，
没有写入权重，也没有开放辅助、晋级、分配、降级、运行、生产、控制或全局航迹编号写权限。

## 证据绑定

| 项目 | 结果 |
| --- | --- |
| 验收日期 | 2026-08-01 |
| 生产提交 | `d7bf89060e88a5b1324f2d8d1de36b005ebe5e4d` |
| generation plan SHA-256 | `ed9765395da89e682b250ba23bf7322b290b2a559d0eb4403a2469f9a2cc48a9` |
| manifest SHA-256 | `9b80e47aed8f4c7a416694220d63d9156010911951cbbf271905ce5c0d6f31d4` |
| dataset config SHA-256 | `3c05993d9b919e639993f1eb074a10bae6fe88d05267342933281e91c35624e7` |
| split SHA-256 | `fb4f6c0ce6566e05113c052af52f45b1ecfbdb3d77727b6c038010777477da7b` |
| training-set SHA-256 | `3cc6ea166adc74e8cf89e9a5a6b44952b9e4f51d08c83678db39b7b9d1761776` |
| corpus audit SHA-256 | `bce869573f6c1084c2db10b263818d98be2de562f7701fc19ec95aaf56bfc872` |
| episode / seed | 100 / 100 |
| seed 范围 | 22100-22199 |
| 场景规模单元 | 45 |
| 样本数 | 159,502 |

生产提交由 D5 从 manifest source identity 复核，manifest SHA-256 由 D5 重新计算。generation
plan SHA-256 使用 main 下发的冻结引用；输入数据集目录内不含该 plan 实物，因此本次不把它
表述为 D5 独立复算结果。

语料按完整 episode 和 seed 分为 train、validation、test。三个 split 互不交叉。

| split | episode | seed | 样本 |
| --- | ---: | ---: | ---: |
| train | 60 | 60 | 95,040 |
| validation | 20 | 20 | 24,329 |
| test | 20 | 20 | 40,133 |

## 严格复载

`load_active_vision_episode_dataset_lazy()` 逐文件复算 `SHA256SUMS`，检查文件集合、只读属性、
gzip 在线流、离线 sidecar、episode descriptor、manifest、完整 episode 分割、来源摘要和
可用性摘要。100 个 episode 均显式声明 `scalable_3d_point_mass_runtime`，dirty episode 为
0，合成 fixture、历史未说明、AirSim 和真实相机来源均为 0。

来源研究门的九项合同检查全部为真，包括严格 loader、显式来源、单一质点来源、完整 source
identity、clean source、版本与哈希绑定、seed 分割、在线 truth-free 和语料完整性。AirSim、
真实相机、生产和运行控制证明继续为 false，来源声明没有被扩大解释。

## 训练门

开发训练结构门使用固定阈值：每类动作至少 `4/2/2`，每类相机角色至少 `8/2/2`，每个动作
与角色组合至少 `2/2/2`，数字依次表示唯一样本、完整 episode 和独立 seed。训练覆盖只使用
train split。验证和测试样本没有进入训练覆盖，保留 seed 也没有被当作训练样本。

训练门无失败原因、无警告、无排除样本。来源门与训练结构门组合调用通过。该门仍标记为
development corpus only，不代表模型精度、泛化能力、统计充分性或正式候选资格。

## 动作覆盖

下表依次给出唯一样本、episode 和 seed 数量。

| split | hold | observe_target | reacquire | search_sector |
| --- | ---: | ---: | ---: | ---: |
| train | 44,441 / 60 / 60 | 839 / 36 / 36 | 47,570 / 60 / 60 | 2,190 / 60 / 60 |
| validation | 11,505 / 20 / 20 | 307 / 9 / 9 | 11,925 / 20 / 20 | 592 / 20 / 20 |
| test | 18,825 / 20 / 20 | 401 / 13 / 13 | 20,043 / 20 / 20 | 864 / 20 / 20 |

四类动作在三个 split 中均有自然样本。`observe_target` 仍是少数动作，后续训练评估必须继续
使用逐动作召回、相机角色分层和分布外检查，不能只看总体准确率。

## 角色覆盖

| split | 拦截相机 | 侦察相机 |
| --- | ---: | ---: |
| train | 91,170 / 60 / 60 | 3,870 / 60 / 60 |
| validation | 23,275 / 20 / 20 | 1,054 / 20 / 20 |
| test | 38,555 / 20 / 20 | 1,578 / 20 / 20 |

两类相机覆盖所有 episode 和 seed。侦察相机样本量明显低于拦截相机，模型训练时仍需单独报告
角色指标，不能用拦截相机多数样本掩盖侦察相机退化。

## 动作角色覆盖

### Train

| 动作 | 拦截相机 | 侦察相机 |
| --- | ---: | ---: |
| hold | 42,669 / 60 / 60 | 1,772 / 60 / 60 |
| observe_target | 822 / 36 / 36 | 17 / 10 / 10 |
| reacquire | 46,512 / 60 / 60 | 1,058 / 60 / 60 |
| search_sector | 1,167 / 37 / 37 | 1,023 / 60 / 60 |

### Validation

| 动作 | 拦截相机 | 侦察相机 |
| --- | ---: | ---: |
| hold | 11,017 / 20 / 20 | 488 / 20 / 20 |
| observe_target | 300 / 9 / 9 | 7 / 2 / 2 |
| reacquire | 11,646 / 20 / 20 | 279 / 20 / 20 |
| search_sector | 312 / 11 / 11 | 280 / 20 / 20 |

### Test

| 动作 | 拦截相机 | 侦察相机 |
| --- | ---: | ---: |
| hold | 18,093 / 20 / 20 | 732 / 20 / 20 |
| observe_target | 386 / 13 / 13 | 15 / 6 / 6 |
| reacquire | 19,646 / 20 / 20 | 397 / 20 / 20 |
| search_sector | 430 / 14 / 14 | 434 / 20 / 20 |

三个原空单元在 train、validation 和 test 中均非零。训练门只依赖 train；validation/test 的
计数用于确认评估集可观测性，没有用于补足训练阈值。

## 身份与运行记录

全语料 159,502 个样本均携带运行 ACK，接受 159,502，拒绝和缺失均为 0。匿名
`observation_key` 覆盖 159,502/159,502，全部唯一。ACK 证明命令响应记录存在，不证明动作
改善了视野或关联结果；离线 outcome、reward、counterfactual 和 causal label 仍全部不可用。

严格 truth-free 检查确认在线 truth、actor 和 object ID 消费计数均为 0。D5 只读取中心
提供的 `global_track_id` 引用，创建或改写计数为 0。正式保留 seed 1000-1019 未被读取或运行，
只以禁止值集合执行 overlap 检查；dataset overlap 和 training overlap 均为空。该检查来源为
显式开发参数，不冒充正式 registry binding。

## 权限边界

本轮没有调用行为克隆训练、近端策略优化、模型 bundle、相机执行或在线辅助入口，没有写入
权重。formal candidate、assist、主动视觉、相机命令、分配、降级、runtime、production、
control 和 `global_track_id` 写权限全部保持 false。旧 v1 失败批次继续保留为历史证据，不与
本 v2 批次合并。

下一步可以在独立开发流程中构建行为克隆缓存并评估模型，但这不是本次验收的一部分。模型仍需
逐动作、逐角色、未见 seed、分布外和 A3/R0 成对非退化证据。AirSim、真实相机和实际物理
动作结果形成之前，默认确定性规则路径和全部运行权限不变。

机器可读结果见
`results/a3_source_independent_corpus_owner_acceptance_v2_20260801.json`。

## 软件回归

验收完成后运行 D5 全量测试，结果为 `776 passed, 2 warnings in 102.23s`，验收阈值为零
失败。两条警告来自既有 Matplotlib `Axes3D` 导入环境和 NVML 初始化，不涉及数据复载、来源
门、训练门或权限。机器 JSON 解析和 owned-path `git diff --check` 通过。本轮没有修改 D5
生产算法。
