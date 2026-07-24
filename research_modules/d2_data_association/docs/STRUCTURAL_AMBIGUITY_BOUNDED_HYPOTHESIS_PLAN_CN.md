# D2 结构歧义有界概率与多假设 C0 设计

- **状态**：`C0_DESIGN_ONLY_NOT_IMPLEMENTED`
- **日期**：2026-07-23
- **输入**：D1 `d1.structural-ambiguity-evidence.v1`
- **范围**：D2 关联/身份假设管理、身份承诺门、资源边界和预注册验收
- **默认主线**：GNN/Hungarian 不变；现有 prediction-only hold 保持主线回退
- **明确未发生**：没有 Python、运行开关、配置类、公开 schema、单元测试、回放、
  AirSim 或性能/算法收益证据

## 1. 决策摘要

D2 首版推荐实现**分量局部、固定窗口、身份专用的 bounded MHT**，并从保留的联合假设
权重导出 JPDA 风格边缘概率。它只回答“哪些允许边在连续若干代中得到足够稳定的身份
证据”，不对 D1 成员状态做概率混合，不回放或收缩物理状态协方差。

推荐该顺序的原因是：

1. JPDA 边缘概率适合描述单代边不确定性，但单独的边缘概率不能保留跨代联合排他关系，
   也难以表达“同一身份解释连续三代获胜”。
2. bounded MHT 可以保留少量跨代联合匹配路径，直接支持连续代数、似然比和冲突审计；
   从同一批联合假设求边缘概率，还可以得到 JPDA 风格的边置信和熵。
3. 200 规模不能建立一个 200x200 的全局假设树。首版只处理 D1 allowed-edge 图中的小型
   稀疏分量，不跨分量相乘，不把确定 1x1 边送入多假设管理。
4. `cross_covariance_available=false` 时，不允许把成员边缘协方差当作独立信息重复融合。
   首版因此只管理关联/身份假设，保留现有 prediction-only 运动学路径。

该推荐不是现有 `MHTAssociator` 的晋级声明。当前二维轻量 JPDA/MHT 仍只是研究对照；
本设计要求的新窗口、generation 幂等、残余概率上界、承诺门和 200 规模预算均尚未实现。

## 2. 边界与不变量

### 2.1 首阶段只管理身份假设

C1 首版允许：

- 读取 D1 已发布的 allowed-edge、NIS、generation 和来源谱系；
- 维护有界的联合匹配路径及其 log weight；
- 计算保留假设的边缘概率、归一化熵、第一/第二假设似然比；
- 决定一条已有 D2 航迹继续 `uncommitted`，还是满足门限后恢复 `committed`；
- 在满足承诺门后结束该身份窗口，使**后续**普通扫描重新进入既有 GNN/Hungarian 路径。

C1 首版禁止：

- 对 D1 成员状态做 JPDA 概率混合、MHT 分支状态更新或固定滞后状态回放；
- 把多条成员边缘 covariance 相乘为独立联合似然并收缩状态；
- 用歧义 observation 更新 state、增加 hit、建立 committed claim 或补写历史；
- 创建、删除、改写、交换或局部重绑 `global_track_id`；
- 用 D1 source token、D1 本地 ID、observation key、actor 名称或 truth 标签冒充规范 ID。

歧义窗口未收敛时，现有 hold 继续 prediction-only。即使窗口收敛，首版也不回填此前
歧义帧的状态；它只允许后续新鲜、普通关联证据按现有路径更新。

### 2.2 身份权威

`global_track_id` 继续由中心 D2 tracker 已有合同维护。假设只能引用已经存在的 canonical
track reference：

```text
opaque D1 member/source lineage
  -> lookup existing D2 source binding
  -> reference existing global_track_id
  -> maintain alternative observation-edge histories
```

若 member source lineage 尚未绑定 canonical track，该成员在 C1 中只能保持
`uncommitted + deferred_birth`，不能由 hypothesis manager 建轨。若获胜路径要求改变
既有 source-to-canonical binding，整窗 fail closed；不能把该结果解释为允许 rebind。

### 2.3 在线 truth 隔离

在线 scoring、排序、剪枝和承诺不得读取：

- simulator truth、actor/object/target 名称；
- D6 离线标签、truth sidecar 或 evaluator mapping；
- 位置最近邻形式的事后 truth 补配；
- 从 source token 文本推断的目标身份。

truth 只在候选运行结束后由隔离 evaluator 计算 strict IDSW、continuity 和 birth delay。

## 3. D1 输入合同

首版只接受已经通过 D1/D2 既有严格校验的
`d1.structural-ambiguity-evidence.v1`。C0 不增加 D1 字段，也不声明新的公开 schema。

| 合同项 | D2 C1 计划语义 | 禁止解释 |
| --- | --- | --- |
| `measurement_timestamp` | 窗口中的物理时间和 OOSM 重放主序 | 不得被 arrival/published 时刻覆盖 |
| `arrival_timestamp` | 网络/队列延迟审计和同量测时刻 tie-break | 不得冒充量测时间 |
| `state_valid_timestamp` | 必须保持与 D1 measurement time 的冻结关系 | 不得由 D2 重定时 |
| `published_at` | 发布新鲜度、网络迟到和审计 | 不作为物理事件主序 |
| `candidate_edges` | 唯一 allowed-edge 集合 | D2 不补几何上“看起来合理”的缺失边 |
| `edge_roles` | 每条可用边必须含 `maximum_matching_allowed` | 其他角色不能放宽 allowed-edge |
| `nis` / `gate_threshold` | 有限、非负且门内的相对关联评分输入 | 不等于独立联合高斯后验 |
| `component_generation` | 每组件严格幂等和窗口推进序号 | 不得用到达次数代替 |
| `evidence_id` / `component_id` | 内容、窗口和冲突审计键 | 不得成为目标身份 |
| `opaque_member_track_token` | D1 成员 opaque reference | 不得成为 `global_track_id` |
| `source_key` | `node::epoch::opaque token` 来源谱系 | 不得成为 canonical ID |
| observation evidence key | opaque allowed-edge/幂等键 | 不得反解原 observation ID |
| member/observation covariance | shape、有限性和输入治理 | C1 不据此做相关状态融合 |
| `cross_covariance_available=false` | 强制身份-only 处理 | 不得假设成员条件独立 |
| free row/column、最大匹配基数 | coast/deferred-birth 结构 | 不得强制补成平衡完美匹配 |
| `posterior_update_applied=false` | D1 仍为 prediction-only 证据 | 不得把侧车当正式 posterior |

任一必需字段缺失、truth 字段出现、NIS/权重非有限、generation 冲突或
`cross_covariance_available` 不是显式 `false`，均不进入概率路径。

## 4. JPDA 与 bounded MHT 比较

| 维度 | JPDA 边缘概率 | bounded MHT |
| --- | --- | --- |
| 核心输出 | 单代或窗口聚合后的边缘概率 `beta_ij` | 跨代联合匹配路径及其权重 |
| 一对一排他关系 | 在联合假设求和前保持，边缘化后会丢失部分联合结构 | 每条保留路径显式保持 |
| 连续代承诺 | 需额外状态机拼接边缘概率 | 直接比较同一路径跨代支持 |
| 延迟决策 | 较弱，通常偏单代 | 原生适合固定窗口延迟承诺 |
| 规模风险 | 联合事件枚举仍可能爆炸 | 分支扩展更明显，需要硬剪枝 |
| 状态更新风险 | 容易被误用为概率混合状态 | 容易被误用为分支状态树 |
| C1 合法用途 | 从保留联合假设导出 `beta_ij`、熵和诊断 | 作为身份假设主结构 |
| 当前推荐 | 辅助输出，不单独作为承诺主机 | **首版推荐** |

推荐不是“完整 MHT 优于 JPDA”的一般结论。它只针对本合同：需要跨 generation 的身份
延迟承诺，同时禁止相关状态融合。若后续只需要单帧歧义风险而不需要身份承诺，JPDA
边缘概率会更轻量。

## 5. 200 规模的稀疏分量策略

### 5.1 不建立全局假设树

每代先按 D1 allowed-edge 构造二部图：

\[
G_k=(R_k,Z_k,E_k),
\]

其中 \(R_k\) 是 opaque member 集，\(Z_k\) 是 opaque observation evidence 集，
\(E_k\) 只含 D1 发布的 allowed edge。处理顺序为：

1. 规范化并校验成员、观测和边；
2. 按二部图连通分量分解；
3. 1x1 且只有一个允许匹配的分量留在既有 GNN/hold 决策，不创建假设窗口；
4. 只对至少含两个合法最大匹配的歧义分量创建局部窗口；
5. 不把不同分量的权重相乘为一个全局 posterior。

最后一项同时服务于规模和统计边界。D1 没有成员间交叉协方差，C1 不能声称不同分量或
同分量成员彼此概率独立。

### 5.2 C0 预注册硬上限

以下值是未来 C1 的预注册设计值，不是当前代码默认值或已存在配置：

| 预算 | C0 值 | 超限处理 |
| --- | ---: | --- |
| 单窗口 member 数 | 8 | 回退 hold，保持 uncommitted |
| 单窗口 observation 数 | 8 | 回退 hold，保持 uncommitted |
| 单窗口 allowed edge 数 | 64 | 回退 hold，保持 uncommitted |
| 完整枚举匹配数 | 256 | 超过后改用 k-best |
| 每代 k-best 匹配数 | 32 | 记录 truncation/残余质量 |
| 每个 parent 最大 child 数 | 32 | 超出不生成 |
| 剪枝前 child 总数 | 2048 | 超限整代 fail closed |
| 每窗口保留联合假设数 | 64 | 确定性剪枝 |
| 窗口 generation 数 | 5 | 到达上限关闭或保持未提交 |
| 窗口 measurement-time 跨度 | 1.0 s | 超窗不重开 |
| 最少承诺连续 generation | 3 | 不足继续 uncommitted |
| active window 总数 | 256 | 新超限窗口回退 hold |
| 全局保留 hypothesis 总数 | 4096 | 超限窗口按规范键失败关闭 |

200 表示输入规模验收点，不是内部常量。上述预算只限制进入概率路径的**局部歧义分量**；
同一帧可以有 200 个输入，但通常只有少量小分量进入 hypothesis manager。

## 6. 匹配生成

### 6.1 full matching

先对 allowed-edge 图计数，枚举所有满足 D1
`maximum_matching_cardinality` 的合法一对一匹配。若可证明总数不超过 256，则保留
全部匹配。free row 形成 `coast`，free column 形成
`deferred_birth_or_clutter`；C1 不增加 D1 未发布的实边。

首版不主动生成低于 D1 最大基数的额外匹配。若输入缺证据，不能靠添加“全漏检”分支
制造概率质量；该代回退现有 hold。以后若要加入低基数 missed-detection 假设，必须由
独立 schema/标定任务冻结，不能夹带在 C1。

### 6.2 k-best matching

完整匹配超过 256 时，计划使用稀疏增广分配上的 Murty 类 k-best 生成器，每代最多返回
32 个合法最大基数匹配。生成器必须：

- 只使用 D1 allowed edge，禁止以大有限代价补缺失边；
- 对 free row/column 使用显式 dummy 语义；
- 返回确定性的第 K+1 候选界或其他可审计残余质量上界；
- 对相同 cost 使用 canonical assignment digest 决胜；
- 不依赖 SciPy/容器对并列解的遍历顺序。

若无法给出遗漏质量上界，k-best 结果只能用于 shadow 诊断，不能产生 `committed`。

## 7. 权重、归一化与边缘概率

### 7.1 身份评分

对边 \(e=(i,j)\)，C1 计划使用温度化 NIS 伪对数似然：

\[
\ell_e=-\frac{1}{2T_{\mathrm{NIS}}}\operatorname{NIS}_{ij},
\qquad T_{\mathrm{NIS}}>0.
\]

对 generation \(k\) 的匹配 \(a_k\) 和 parent path \(h_{k-1}\)：

\[
\log \tilde w_k(h)=
\log w_{k-1}(h_{k-1})
+\sum_{e\in a_k}\ell_e
+n_{\mathrm{coast}}\log p_{\mathrm{coast}}
+n_{\mathrm{deferred}}\log p_{\mathrm{deferred}}
+\log p(a_k\mid h_{k-1}).
\]

C1 原型的 transition prior 先保持中性，不用隐藏的 ID switch penalty 强推现有绑定。
`T_NIS`、coast/deferred prior 均必须版本化，并在 C2 冻结回放中标定。归一化后的数值是
该评分模型内的 `association hypothesis weight`，不是目标存在概率，也不是经真实数据
证明校准的物理 posterior。

### 7.2 log-domain 归一化

所有计算留在 log domain：

\[
\log Z=m+\log\sum_h \exp(\log\tilde w_h-m),
\qquad
m=\max_h\log\tilde w_h,
\]

\[
\log w_h=\log\tilde w_h-\log Z.
\]

输入、部分和、`m`、`log Z`、归一化权重及熵任一出现 NaN/Inf，整窗 fail closed。
禁止用极小常量替换非有限值后继续承诺。

### 7.3 JPDA 风格边缘概率

从同一批保留联合假设计算：

\[
\beta_{ij}
=\sum_{h:(i,j)\in h}w_h.
\]

若存在经证明的 omitted-mass upper bound，必须把它作为 `other` 桶纳入保守概率和熵；
不能在截断后把保留的少数假设重新归一化为虚假 100% 置信度。

对有效假设分布计算归一化熵：

\[
H_\mathrm{norm}
=-\frac{\sum_h w_h\log w_h}{\log |\mathcal H_\mathrm{effective}|}.
\]

只有一个假设时，只有“完整枚举已证明唯一”才允许熵为 0。若只是 k-best 截断后剩一个，
保持 uncommitted。

## 8. 确定性排序、摘要和剪枝

### 8.1 时间与 evidence 顺序

窗口重放主键为：

```text
K_replay = (
  measurement_timestamp,
  arrival_timestamp,
  published_at,
  publisher_node_id,
  publisher_epoch,
  sensor_id,
  scan_id,
  component_id,
  component_generation,
  evidence_id
)
```

同批序列化仍可保留 D1 的规范 component key；measurement time 是窗口重放主序，
arrival/published time 只作因果和 tie-break，二者都不被丢弃。

成员按 `(source_key, opaque_member_track_token)` 排序，观测按
`observation_evidence_key` 排序，边按
`(source_key, observation_evidence_key, canonical_edge_roles)` 排序。

### 8.2 hypothesis ID

设计占位，不表示 schema 已存在：

```text
hypothesis_id = SHA-256(
  design_version,
  window_id,
  ordered_evidence_ids,
  parent_hypothesis_id,
  ordered_assignment_edges,
  ordered_lifecycle_dispositions
)
```

所有数值先通过有限性和规范编码校验。禁止把浮点容差分桶、字典自然顺序或内存地址写入
摘要。

### 8.3 剪枝

候选先按 `(-log_weight, hypothesis_id)` 排序，保留前 64。等权重由
`hypothesis_id` 决胜。剪枝前后记录：

- generated/retained/pruned hypothesis count；
- best/second log weight 和 log likelihood ratio；
- omitted-mass upper bound；
- full-enumeration 或 k-best 标志；
- deterministic input/output digest。

若剪枝丢失质量不可界定，窗口可以继续做 shadow 诊断，但不能承诺身份。

## 9. birth、death 与 coast

C1 的 lifecycle 语义只存在于身份假设中，不直接修改 tracker：

- **coast**：D1 free row 对应已有 member 本代没有可承诺 observation。canonical track
  继续现有 prediction-only hold；不增加 miss，也不删除 ID。
- **deferred birth**：D1 free column 对应 observation 未能关联到已有 member。保持
  `birth_deferred`，不创建 `global_track_id`。
- **clutter/unknown**：只有 D1/upstream 已提供合法 truth-free disposition 时才可记录；
  D2 不从位置、名称或 NIS 事后猜测。
- **death**：hypothesis manager 不删除 canonical track。窗口超时未收敛时保持
  uncommitted 并交回既有 hold/lifecycle 规则；`dropped` ID 永不复用。
- **normal birth/death**：只由结构歧义窗口外既有 GNN/Hungarian 和 tracker lifecycle
  执行，C1 不改变其阈值。

因此 C1 的 birth delay 指标测量“歧义窗口是否延迟既有合法建轨/承诺”，不是宣称 MHT
分支已经具备独立建轨和删轨能力。

## 10. OOSM、generation 和幂等

幂等键为：

```text
(publisher_node_id, publisher_epoch, component_id, component_generation)
```

并绑定规范内容摘要：

1. 相同 key、相同摘要：幂等 no-op，不重复扩展、不刷新窗口、不延长 hold。
2. 相同 key、不同摘要：`generation_content_conflict`，整窗 fail closed。
3. generation 回退：拒绝且无状态副作用。
4. generation 跳号：标记 `missing_generation`，不插值、不承诺。
5. 窗口内 OOSM：按 `K_replay` 插入，从最近身份 checkpoint 重算权重；不重放物理状态。
6. 超出 5 generation 或 1.0 s 固定窗口的 OOSM：不重开已关闭窗口，保持/转为
   uncommitted。
7. publisher epoch 变化：关闭旧 epoch 窗口；旧 epoch 回流拒绝。新 epoch 不继承旧
   source token 的身份权威。

若同一 member、canonical track 或 observation evidence 在重叠窗口中出现冲突声明，
涉及窗口全部标为 `cross_window_conflict`。不得通过选择先到窗口或较高权重窗口解决。

## 11. identity commitment

### 11.1 未收敛状态

以下任一成立时继续发布既有未承诺语义：

- 假设窗口不足三代；
- top path 在连续代中变化；
- likelihood ratio、熵或边缘概率未过门；
- evidence freshness、source support 或 generation 完整性不足；
- 存在 omitted mass 无上界、容量溢出、跨窗冲突或网络超窗。

未收敛不等于失败地选择第二名；它表示没有足够证据做身份承诺。D3 继续只消费
`committed`。

### 11.2 C0 预注册承诺门

同一 canonical assignment 只有同时满足以下条件才可从该窗口输出 committed decision：

1. **新鲜度**：最新支持证据在决策时
   `decision_time - measurement_timestamp <= 0.9 s`；输入本身还必须通过既有
   component age 和双时间戳合同。超网络窗口的 evidence 不补承诺。
2. **似然比**：第一、第二路径
   \(\log(w_1/w_2)\ge \log 20\)。没有第二路径时，必须证明完整枚举唯一且 omitted
   mass 为 0。
3. **熵**：包含 `other` 桶后的 \(H_\mathrm{norm}\le 0.20\)。
4. **边缘概率**：拟承诺 assignment 中每条边 \(\beta_{ij}\ge0.95\)。
5. **连续代数**：同一 canonical assignment 连续至少 3 个严格递增 generation 获胜。
6. **来源证据门**：至少 3 个不同 evidence ID/scan ID、至少 3 个不同 observation
   evidence key、严格推进的 measurement time、同一有效 publisher epoch，且全部
   source lineage 可映射到同一组既有 canonical references。
7. **完整性**：没有 missing/duplicate-conflict generation、cross-window conflict、
   overflow、非有限权重或未界定的截断质量。
8. **身份权威**：结果不要求创建、交换或 rebind canonical ID；否则保持 uncommitted。

来源证据门只证明“新鲜、不可重复、谱系一致的多代支持”，不证明多传感器统计独立。
`cross_covariance_available=false` 时，即使出现多个 sensor/source，也不能据此放宽状态
融合边界。

### 11.3 planned output

未来内部/影子输出至少需要以下审计字段；名称是设计占位，不表示 DTO 已实现：

```text
IdentityHypothesisDecision
  decision = committed | uncommitted | fail_closed
  canonical_track_references[]
  window_id
  ordered_evidence_ids[]
  winning_hypothesis_id
  generation_start / generation_end / consecutive_generation_count
  best_log_weight / second_log_weight / log_likelihood_ratio
  normalized_entropy
  edge_marginals[]
  full_enumeration / k_best / truncated
  omitted_mass_upper_bound
  freshness_summary
  source_support_summary
  hypothesis_count_summary
  fail_closed_reason
  online_truth_used = false
  mutates_kinematic_state = false
  mutates_global_track_id = false
```

未承诺输出不得携带 observation-to-canonical binding。公开输出若未来新增 schema，必须
单独评审与版本化；C0 不创建该 schema。

## 12. D3 消费边界

D3 合同不因 C0 改变：

- D2 继续发布每条既有 canonical track 的 commitment state；
- D3 只消费 `committed` 航迹；
- `uncommitted`、`fail_closed`、overflow、证据缺失或网络超窗都不能进入新计划；
- 已有计划中的航迹转为未提交时，沿现有合同强制重规划、撤回旧绑定并严格增加版本；
- D2 不创建 `AssignmentPlan`，不修改 plan version，也不决定 D5/D7 许可。

固定提交 `7e15dac9` 的历史 clean 复验只证明 committed-only 下游准入已接通，不能作为
本 C0 算法实现或收益证据。

## 13. fail-closed 矩阵

| 条件 | C1 计划动作 | 禁止动作 |
| --- | --- | --- |
| 局部分量/全局 hypothesis 溢出 | 保持 uncommitted，回退 hold，记录预算 | 不静默截断后承诺 |
| NIS/log weight/归一化/熵非有限 | 整窗拒绝 | 不以 epsilon 修补 |
| 缺 member/observation/edge/generation | 保持 uncommitted | 不补边、不插值 |
| 相同 generation 内容冲突 | 整窗冲突 | 不采用先到或后到 |
| OOSM 在窗内 | 只重放身份权重 | 不重放/改写物理状态 |
| OOSM/网络延迟跨窗 | 不重开窗口 | 不用旧证据恢复 committed |
| cross-window member/observation 冲突 | 涉及窗口全部失败关闭 | 不按最高权重抢占 |
| source token 无 canonical binding | deferred birth/uncommitted | 不把 token 当 ID |
| 获胜路径要求 canonical rebind | 保持 uncommitted并审计 | 不交换/重写 ID |
| `cross_covariance_available=false` | 身份-only | 不做独立状态融合 |
| truth/actor/target 字段出现 | 输入拒绝 | 不进入 scoring |

fail closed 必须保持有界内存和幂等；不能因审计记录本身无限增长造成第二次溢出。

## 14. 预注册测试

### 14.1 C1 合同与算法测试

1. 2x2 对称、3x3 稀疏、含 free row/column、1xN、N x1 和非 2/5/200 数量 fixture。
2. full matching oracle 与 k-best 前 K 项一致；缺失边永不出现于输出。
3. logsumexp、边缘概率、`other` 桶、熵和似然比的手算 oracle。
4. 输入成员、观测、边和 generation 到达顺序全排列产生 byte-identical decision。
5. exact duplicate no-op；同代异内容、回退代、跳代和 epoch 回流 fail closed。
6. 窗内 OOSM 重算与规范有序输入一致；跨窗 OOSM 不改变已关闭窗口。
7. cap 边界 `limit-1/limit/limit+1`；超限保持 uncommitted，内存不增长。
8. birth/death/coast 只改变假设 disposition，不创建/删除 canonical track。
9. 未绑定 source token 不建轨；任何 token-to-`global_track_id` 冒充均拒绝。
10. winning path 需要 rebind 时不承诺；已有 `global_track_id` 字节级不变。
11. 未收敛、非有限、missing evidence、cross-window conflict 和网络超窗全部阻断 D3。
12. 在线输入递归 truth 隔离；truth sidecar 只能在候选运行完成后评分。

### 14.2 预注册指标与门槛

未来 C2/C3 必须同时报告，不允许只报告 IDSW 改善：

| 指标 | 预注册口径 |
| --- | --- |
| strict IDSW availability | baseline/candidate 均必须 available；缺失即停止 |
| strict IDSW | candidate 不高于同输入 GNN+hold baseline |
| track continuity | seed 1100 不低于 baseline；多 seed 配对 95% CI 下界不低于 `-0.005` |
| coverage continuity | 同上 |
| D2 可用性 | committed/available mapping 和终态有效 track 不低于 baseline |
| D3 可用性 | committed target/assignment 不低于 baseline；uncommitted assignment 为 0 |
| birth delay | P95 不超过 baseline + 1 scan；max 不超过 baseline + 2 scans |
| hypothesis 数 | 每窗 `<=64`、全局 `<=4096`；报告 generated/retained/pruned/overflow |
| P95 | hypothesis stage `<=20 ms`，且 D2 core P95 不超过 baseline `1.25x` |
| RSS | 峰值增量 `<=128 MiB` 且不超过 baseline `1.20x`；长时不得线性增长 |
| truth 隔离 | online truth/actor/target use 为 0 |
| 绑定违规 | ID create/rewrite/rebind、token-as-ID、uncommitted source/candidate binding 均为 0 |
| 幂等/确定性 | duplicate side effect、digest mismatch 和排序漂移均为 0 |

若候选减少 IDSW 但 continuity、D2/D3 可用性、birth delay、P95/RSS 或绑定合同任一退化，
不得晋级。

## 15. 阶段计划

### C0：设计冻结，当前阶段

本文件以及 README/PLAN/GAP/review/算法说明同步。完成标志仅为：

- 输入和身份权威边界成文；
- JPDA/bounded MHT 比较和首版选择成文；
- 窗口、上限、排序、剪枝、承诺门和 fail-closed 口径成文；
- 测试、指标、停止条件和后续阶段成文。

**C0 不包含 Python、开关、配置/schema、测试或运行证据。**

### C1：纯身份假设原型

- 新建内部、默认关闭的 component-local hypothesis manager；
- 只用确定性 fixture 和手算 oracle；
- 不接 main bus，不发布新 schema，不更新状态；
- full enumeration 先于 k-best；k-best 无残余上界时禁止 commit；
- 完成幂等、OOSM、排序、剪枝、容量和 truth 隔离测试。

### C2：离线 shadow 与 seed 1100 首门

- 对冻结 D1/D2 输入做 shadow，业务输出仍由 GNN+hold 产生；
- 比较 shadow decision 与现有 commitment/hold，不回写状态；
- 先完成 200 规模 P95/RSS 和长时有界性；
- 只有 C1 全过后，才可在独立任务中预注册并复核 seed 1100；
- 任一 strict availability、连续性、D2/D3 可用性或绑定门失败即停止。

### C3：有限候选接线与确认性试验

- 仍默认关闭，只允许 commitment decision 结束后续身份 hold；
- 不做历史状态融合，不回填歧义帧；
- 先同输入非退化，再登记全新的未见 seed 和固定硬件预算；
- 只有全部指标联合通过，才讨论是否保留为默认关闭候选。

seeds 1101/1102 在 C0 不恢复，在 C1/C2 也不自动恢复。C3 的 seed 清单必须重新预注册并
获得独立授权；本设计不把 1101/1102 预留为默认下一批。

## 16. 当前状态

截至 2026-07-23：

- C0 文档规划完成后，推荐算法为 component-local identity-only bounded MHT；
- JPDA 风格边缘概率只从同一联合假设池导出，用于熵、似然比和审计；
- 默认 GNN/Hungarian、现有 hold、`global_track_id` 权威和 D3 committed-only 准入不变；
- 相关状态融合、自动 birth/death、公开 schema、运行开关和任何 C1-C3 实现均不存在；
- 没有新的测试、回放、AirSim、seed、P95/RSS 或收益证据；
- seeds 1101/1102 继续停止。

本文不能作为算法实现、配置可用、系统接线、性能达标或候选晋级证据。
