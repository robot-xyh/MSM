# D4 v5 来源独立评价

## 结论

D4 v5 近邻置信候选没有取得准入证据。M16N20 来源独立数据证明该候选能在本批输入上
拒绝负类，但冻结 actor 没有正确输出任何来源独立安全正动作。正类召回没有分母，不能
评价。

候选继续保持未注册、准入关闭和规则回退。正式留出集、运行时预检、D3 后继计划和 D7
执行权限均不启动。本轮结果不能解释为区域调度收益、AirSim 性能或生产能力。

## 数据边界

来源数据由 clean commit
`63987592c216fbdb7e03d77183afc6e9f15748a2` 生成。场景包含 16 个目标、20 个资源、
8 个区域和 4 个真实备用资源，覆盖 nominal、dense crossing、evasive multilevel 和
delayed noisy 四类三维布局。

| 项目 | 结果 |
| --- | ---: |
| episode | 32 |
| 帧 | 63 |
| 独立评价 seed | 3008-3039 |
| train/validation/test 帧 | 43/10/10 |
| dirty episode | 0 |
| 在线真值使用 | 0 |
| 正式 holdout 读取 | 0 |

训练 seed `0-99`、正式 holdout `1000-1019`、设计 pilot `3000-3007` 和独立评价
`3008-3039` 两两无交集。D4 和 D6 均读取 external test 的 10 帧；main 此前也已
只读检查该 10 帧。该 split 是本批来源独立开发数据的非正式 test，不是正式 holdout。

## 标签口径

每个区域快照在离线边界重算确定性规则 R0。在线 D4 recommendation 只保留为来源审计
字段，不作为教师标签。规则安全正动作要求外部规则目标相对 R0 形成可执行差异，并通过
现有确定性投影和干预不变量。

候选正类还要求冻结 actor 输出同一可执行动作签名：

\[
y_{\mathrm{actor}} =
\mathbf{1}\left[
y_{\mathrm{safe}}=1,\quad
\operatorname{sig}(a_\theta)=\operatorname{sig}(a_{\mathrm{safe}}),\
\operatorname{safe}(a_\theta)=1
\right].
\]

规则层有安全动作只说明该帧存在可用调度差异。actor 没有命中该动作时，该帧不能进入
候选正类分母。

## 来源独立性

可观测键只包含区域图架构、节点特征、边特征和边索引的形状、类型及数值，不包含 seed、
来源、actor、目标或真值身份。

| 数据 | 帧 | 唯一可观测键 |
| --- | ---: | ---: |
| 冻结 v4 TRAIN+VALIDATION | 425 | 251 |
| M16N20 外部数据 | 63 | 41 |
| exact 重合 | - | 0 |

外部 train、validation 和 test 之间的 exact key 重合也为 0。该结果排除了复用旧开发
输入造成的直接记忆命中。

## 评价结果

| split | 样本 | 规则安全正动作 | actor-derived 正类 | 得分范围 | 0.60 通过 | 负类误接收 | 规则回退 |
| --- | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| train | 43 | 1 | 0 | 0-0 | 0 | 0 | 43 |
| validation | 10 | 1 | 0 | 0-0 | 0 | 0 | 10 |
| test | 10 | 0 | 0 | 0-0 | 0 | 0 | 10 |

冻结 actor 在 63 帧中产生 16 个相对 R0 的可执行差异，但没有一个与两个规则安全正动作
签名一致。actor-derived 正类总数为 0。63 个置信得分均为 0，固定 0.60 门没有放行
任何样本。

负类特异度可计算为 \(63/63=1.0\)。正类召回的分母为 0，指标状态为 unavailable。
这里的 unavailable 表示没有形成可评价的候选正类，不能写成召回率 0，也不能写成评价
通过。

## 完整性

D4 在评价前后复核 v4 actor 和 v5 calibrator 文件树，并禁止把评价输出写入 source、
labeled、v4 或 v5 输入树。D6 进一步对五棵输入树执行前后内容摘要。

| 输入树 | SHA-256 | 前后变化 |
| --- | --- | ---: |
| source root | `2462ff5be038c367180a6710f169fb6cf60bd1b553b831fa96d1589ca1ea3b54` | 0 |
| labeled export | `2163503b115462f79fadc2a0fea6b32ffa557cbd3a6178d16f2b7ae81685ad89` | 0 |
| labeled dataset | `796ba3a6237058f00396d6faf742767dc912ace42feb2892c2f25c9d4ee0d85e` | 0 |
| v4 actor | `2afd692874b91a23a5525448a0c5af98f3c2d96f0b12cebbf81a570d58d500d0` | 0 |
| v5 calibrator | `632f066fcad363531762e6b7a1ef0f21c03b7b0d0aa3b4cd39a16e4fbbf7c273` | 0 |

来源 manifest、标签数据、split、来源推导和标签审计 SHA-256 分别为：

- source manifest：
  `af12051917cfe9eedfc8587c953599112db62858e4b01820a16ddd5b0a10231d`
- labeled dataset：
  `ed2fd4b1a4d50ec80e5abdaa35a1470cec03d419665ae0e08b7c4339e9b8887e`
- split：
  `cdaa40241195516eb1679f6ed0a8179f3d2365c9768f9ef9a44b6f85fabcefb6`
- source artifact：
  `ccf327717a293f63b5655e978202ff720f20c74bfd8ae401f2233cc590bb753a`
- label audit：
  `8798bd28037a7c52abc972e9a13551525e68eeb590d49e497b0db6cd31800336`

D6 审计 JSON 内容 SHA-256 为
`16acba58d4b045215f421940f13b57a884152d3099eb7c22b4468a4bc7afee17`。

## 验收

- D4 v5 专项：18 项通过。
- D4 全量：843 项通过。
- D6 外部审计专项：5 项通过。
- D6 全量：1215 项通过。
- main 来源生成专项：6 项通过。
- scalable 3D 全量：389 项通过。

测试仅出现既有 Matplotlib `Axes3D` 环境警告，不影响本轮哈希、评分、JSON 或 CSV。

## 后续

当前 v5 停止晋级。外部 test 已被读取，不能用于继续调整同一候选、固定 0.60 门、split
或标签设计。

后续如继续研究，需要另立候选版本和来源独立 development 数据。新数据应形成足量、
可复核的 actor-derived 正类，并保持正式 holdout 未读。D6 完成新的盲审后，main 再决定
是否授权正式 holdout。运行时预检、D3 后继、D7 权限、物理窗口和收益评价均排在该门之后。
