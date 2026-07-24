# D2 结构歧义保持租约因果审计

## 1. 审计结论

当前结构歧义候选不能通过调整 `gap/hard` 租约参数消除退化。租约参数只决定歧义保持
何时释放，不改变保持期间的处理方式。现有处理对整个歧义分量执行 prediction-only：
不更新运动状态，不增加命中，不增加漏检，不建轨。该策略降低了可计数的身份切换，但
同时减少了可用运动学更新，使部分航迹长期停留在 tentative 或在释放后被淘汰。

默认 `(gap, hard)=(2,5)` 下，候选把 strict ID switch 从 9 降到 3，但 D2 终态航迹从
203 降到 201，D3 分配从 200 降到 197，track continuity 从 `0.8650000` 降到
`0.8266667`。五组缩短租约的 clean 扫描均得到 197 条 D2 终态航迹，没有一组同时恢复
航迹、分配和连续性。因此本轮不修改默认参数，不扩大 `0.9 s` 发布新鲜度预算，也不
实现新算法候选。

三条超龄恢复拒绝必须保留。`GT3D-000185`、`GT3D-000186` 和 `GT3D-000202` 的最新
原始量测时刻为 `1.2 s`，最终 D2 tracker frame 为 `2.1308153038551993 s`，发布年龄
为 `0.9308153038551993 s`，超过固定预算约 `0.030815 s`。放行会用已经超龄的证据恢复
规范身份，并掩盖调度和运动状态维持问题。

## 2. 证据范围

基准 A/B 使用既有 clean 制品：

- baseline：`/tmp/MSM-identity-freshness-final-ff88131/baseline`；
- candidate：`/tmp/MSM-identity-freshness-final-ff88131/candidate`；
- clean 提交：`ff881316243ff5a2991a4659ab78637ed625d123`；
- 场景：nominal 200v200；
- 时长：`2.2 s`；
- 侦察节点数：2；
- seed：1100；
- 场景配置 SHA-256：
  `34f5563579d9d2e7d1ea2b57cf353d2465b3bd16c5310570d40e72fc7aeac461`。

租约扫描在 detached clean 提交
`3fcf5b09fae166bd1c2fd374404e81aa63c1ad9d` 上执行，输出位于
`/tmp/MSM-d2-lease-audit-clean-3fcf5b0`。五组运行的
`manifest.repository_dirty` 均为 `false`，场景、seed、时长和侦察节点数与 A/B 相同。
每个参数点只有一个 seed，只用于因果定位，不用于多 seed 晋级。

本次没有启动 AirSim。所有结论均来自三维质点全栈、在线 truth-free 记录和独立离线
truth sidecar 评分。

### 2.1 合同与配置谱系

权威 baseline/candidate 的 9 条 D2 发布均携带：

- 身份承诺 schema：`d2.identity-evidence-commitment.v2`；
- 身份承诺 policy：`d2-structural-ambiguity-commitment-v2`；
- 恢复配置 schema：`d2.identity-commitment-recovery-config.v2`；
- 实际集成配置版本：
  `main-scalable3d-identity-recovery-publication-freshness-v1`；
- 固定发布新鲜度预算：`0.9 s`；
- 恢复配置规范化 SHA-256：
  `sha256:bd8e362ec4ca128ed902826750b26d862286770d3c0c4d0b75960a50911a201a`。

baseline/candidate 的 offline identity manifest 均为
`scalable3d-offline-identity-evaluation-manifest-v2`，配置记录数均为 9，逐发布一致性
校验为 true。D6 另验证了 manifest 哈希和原始 D2 JSONL 哈希，配置谱系 availability
为 available。D2 单模块默认配置版本名为
`d2-identity-recovery-publication-freshness-v2`；本审计引用的是 main 显式注入并由
制品证明的集成配置，不能把两者名称混写。

五组租约扫描继续使用相同恢复配置版本、预算和配置哈希，只改变
`gap_scan_periods/hard_scan_periods`。因此扫描差异不能归因于恢复新鲜度配置漂移。

## 3. 租约机制

雷达周期为 \(T_s=0.2\ \mathrm{s}\)。若 `gap_scan_periods=g`、
`hard_scan_periods=h`，有效时长为：

\[
T_\mathrm{gap}=gT_s,\qquad T_\mathrm{hard}=hT_s,\qquad h\geq g>0.
\]

新分量首次进入 D2 时：

\[
t_\mathrm{soft}=\min(t_0+T_\mathrm{gap},t_0+T_\mathrm{hard}),
\qquad
t_\mathrm{hard}=t_0+T_\mathrm{hard}.
\]

同一分量只有出现新的原始观测证据时才延长 soft deadline：

\[
t_\mathrm{soft}\leftarrow
\min(t_\mathrm{last\_new}+T_\mathrm{gap},t_\mathrm{hard}).
\]

重复 evidence、generation 回退和 posterior replay 不刷新租约。D2 只在消费新 tracker
frame 时检查 deadline，因此实际释放时刻是首个满足

\[
t_\mathrm{D2}\geq \min(t_\mathrm{soft},t_\mathrm{hard})
\]

的 D2 消费时刻，不一定等于 deadline。

释放只删除 claim reservation，并把
`identity_uncommitted_ambiguity_hold` 转为
`identity_uncommitted_after_hold`。恢复阻断 key 和最大歧义量测时间水位线继续保存。
恢复还需满足以下条件：

1. 没有活动租约；
2. 使用本扫描首次接纳、未回放的原始观测；
3. evidence key 未被歧义期使用；
4. source measurement timestamp 严格晚于恢复水位线；
5. truth-free disposition 为 `target_candidate`；
6. tracker frame timestamp 减 source measurement timestamp 不超过 `0.9 s`。

## 4. 默认候选的逐状态证据

### 4.1 发布序列

| D2 总线时刻/s | 航迹数 | committed | active hold | after hold |
|---:|---:|---:|---:|---:|
| 0.75 | 193 | 193 | 0 | 0 |
| 0.85 | 193 | 193 | 0 | 0 |
| 1.00 | 197 | 186 | 11 | 0 |
| 1.20 | 200 | 189 | 11 | 0 |
| 1.40 | 200 | 188 | 12 | 0 |
| 1.60 | 201 | 190 | 11 | 0 |
| 1.80 | 201 | 190 | 11 | 0 |
| 2.00 | 201 | 190 | 11 | 0 |
| 2.20 | 201 | 192 | 2 | 7 |

全部 1787 条证据记录中，1711 条 committed，69 条处于 active hold，7 条处于
after hold。累计阻止 hit/miss/birth 为 `69/69/4`。

### 4.2 终态未提交航迹

| 航迹 | 终态 | 直接原因 |
|---|---|---|
| `GT3D-000057`、`GT3D-000058` | after hold | 租约释放后没有合格新原始观测 |
| `GT3D-000079`、`GT3D-000080` | after hold | 租约释放后没有合格新原始观测 |
| `GT3D-000185`、`GT3D-000186` | after hold | 新观测发布年龄超过 `0.9 s` |
| `GT3D-000202` | after hold | 新观测发布年龄超过 `0.9 s` |
| `GT3D-000200`、`GT3D-000203` | active hold | 最终帧仍有活动分量 |

`GT3D-000034`、`GT3D-000035`、`GT3D-000060`、`GT3D-000112` 和
`GT3D-000113` 在租约释放后获得合格的新原始证据并恢复 committed，说明恢复状态机
本身可以闭合。

### 4.3 航迹数 201 的来源

候选累计初始化 203 条 D2 航迹。`GT3D-000133` 和 `GT3D-000164` 只出现在前两个证据
帧，之后退出活动集合，终态因此为 201 条。

离线 sidecar 表明：

- `GT3D-000133` 初始对应 `TGT-0139`，后续证据先落到
  `GT3D-000200`，再落到 `GT3D-000203`；
- `GT3D-000164` 初始对应 `TGT-0171`，后续证据落到
  `GT3D-000202`。

这两条真值链分别产生 2 次和 1 次 committed 锚点切换，合计为候选 strict IDSW 3。
原始轨迹退出、替代轨迹新建和替代轨迹随后进入 hold 共同降低了连续性。

baseline 终态 203 条轨迹中还包含 1 条已知纯虚警航迹和 2 条 lost 航迹。因此
`203 -> 201` 不能单独解释为少检测了两个真实目标。更直接的业务退化证据是候选最终
只有 191 个可用 truth target 映射，另有 9 个目标处于未提交状态；baseline 最终有
200 个可用 truth target 映射。

## 5. D3 分配数 197 的来源

D3 共发布三版计划。将每版计划的 `global_track_id` 与同一总线时刻最新 D2 承诺状态
联接，结果如下。

| 计划版本 | 时刻/s | 分配数 | D2 航迹数 | 被分配的未提交航迹 |
|---:|---:|---:|---:|---:|
| 1 | 0.75 | 193 | 193 | 0 |
| 2 | 1.00 | 197 | 197 | 11 |
| 3 | 2.00 | 197 | 201 | 8 |

第 2 版计划把当时全部 197 条 D2 航迹投入分配，其中 11 条为
`identity_uncommitted_ambiguity_hold`。第 3 版仍分配 8 条未提交航迹，并未分配
`GT3D-000200`、`GT3D-000201`、`GT3D-000202` 和 `GT3D-000203`。最终 D2 flush
发生在 `2.2 s`，晚于该轮 D3 规划，因此 9 条终态未提交航迹没有触发新的计划。

由此可见，197 不是“当前 committed 且可分配航迹数”。它由 `1.0 s` 规划时 D2 只有
197 条航迹和后续 D3 计划保持共同形成。该结论描述的是冻结 seed-1100 制品。当前
工作区已有 D3-owned 承诺状态准入修改，但尚未使用同一冻结输入完成 main 集成复验。
后续验收仍需证明：未提交航迹不得进入新计划，已有计划中的对应条目进入版本化
hold/replan，不能继续沿用。

## 6. 三条超龄恢复

`GT3D-000185` 和 `GT3D-000186` 的 hard deadline 为
`1.4778654876914714 s`。前一 D2 tracker frame 为
`1.46409938706653 s`，尚未到期；下一 frame 跳到
`2.1308153038551993 s`，此时才释放。

`GT3D-000202` 的 soft/hard deadline 分别为
`1.654272675115119 s` 和 `1.8665157718361352 s`，同样在
`2.1308153038551993 s` 才被消费和释放。

三条恢复候选的 source measurement timestamp 均为 `1.2 s`：

\[
2.1308153038551993-1.2
=0.9308153038551993\ \mathrm{s}>0.9\ \mathrm{s}.
\]

因此租约释放的离散调度确实推迟了恢复机会。拒绝仍然正确。该证据已经超出冻结发布
新鲜度预算，且在量测更新前被撤回，没有增加 hit、更新状态、绑定 claim 或进入
`detection_to_track`。应调整调度或运动学保持方式，不能扩大预算。

## 7. 参数扫描

下表为 detached clean 单 seed 结果。`g/h` 分别表示 gap/hard 扫描周期。

| 参数 | D2 航迹 | D3 分配 | 可用映射 | 未提交记录 | strict IDSW | track continuity | coverage continuity |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline，hold 关闭 | 203 | 200 | 1566 | 0 | 9 | 0.8650000 | 0.8700000 |
| 默认候选 `(2,5)` | 201 | 197 | 1491 | 76 | 3 | 0.8266667 | 0.8283333 |
| `(1,2)` | 197 | 195 | 1499 | 48 | 7 | 0.8288889 | 0.8327778 |
| `(1,3)` | 197 | 195 | 1499 | 56 | 5 | 0.8300000 | 0.8327778 |
| `(1,4)` | 197 | 197 | 1498 | 62 | 3 | 0.8305556 | 0.8322222 |
| `(2,3)` | 197 | 195 | 1494 | 62 | 5 | 0.8272222 | 0.8300000 |
| `(2,4)` | 197 | 197 | 1493 | 68 | 3 | 0.8277778 | 0.8294444 |

五组扫描均保持 duplicate assignment、online truth use、未提交 source binding
violation 和未提交 candidate binding violation 为 0。0.9 秒预算没有改变。

缩短 hard deadline 后，活动租约在终态全部释放，但航迹数统一降到 197：

- `(1,2)` 运行中共创建 207 条，终态前退出 10 条；
- `(1,3)` 和 `(2,3)` 共创建 205 条，退出 8 条；
- `(1,4)` 和 `(2,4)` 共创建 203 条，退出 6 条。

反复退出的航迹包括 `GT3D-000057`、`GT3D-000058`、`GT3D-000079`、
`GT3D-000080`、`GT3D-000133` 和 `GT3D-000164`。默认 `(2,5)` 仍用活动 hold
保护前四条，使其未被 lifecycle 淘汰，但没有恢复运动状态或身份承诺。

`(1,4)` 是五组中最好的诊断点：清除三条超龄恢复、保持 IDSW 为 3，并把两项连续性
略高于默认候选；但其 D2 航迹只有 197，仍低于默认候选和 baseline，不能作为新默认。
`hard<=3` 会把 IDSW 提高到 5 至 7，且 D3 分配降到 195。当前没有经验上可准入的
`gap/hard` 范围。

## 8. 根因排序

1. **prediction-only 丢失运动学信息。** 活动 hold 累计阻止 69 次正常 hit 和对应
   update。轨迹均值没有吸收观测，协方差只按模型传播，后续唯一观测更难重新进入正确
   门限。
2. **租约释放和 lifecycle 没有配套。** 长租约让 tentative 轨迹保留但长期未提交；
   短租约让它们更早回到普通 miss/drop 路径，在没有合格运动学更新时被淘汰。
3. **D2 消费时刻离散。** 部分 deadline 刚好晚于 `1.464099 s` tracker frame，下一次
   消费已是 `2.130815 s`，导致三条新证据发布年龄超过 0.9 秒。
4. **冻结 D3 制品未使用承诺状态准入。** 第 2/3 版计划分别包含 11/8 条未提交航迹，
   197 不能解释为 D2 的 committed 可分配能力。当前 D3-owned 修改需另做同输入集成复验。
5. **上游轨迹和建轨差异。** candidate 的 D1 结构歧义侧车改变了部分早期输入与
   deferred birth；D2 侧可定位退出和替代 ID，但不能单独判定四次 birth suppression
   都是假重复还是有效目标，需要 D1 独立审计。

## 9. 参数建议

1. 保持候选默认关闭。
2. 保持默认 `(2,5)` 不变，避免在算法合同未改变时用参数替换掩盖退化。
3. 不扩大 `0.9 s` 发布新鲜度预算。
4. `(1,4)` 仅保留为下一候选的同 seed 诊断对照，不进入在线默认或多 seed 晋级。
5. 下一候选先通过 seed 1100 的联合非退化门槛，再启动 seeds 1101/1102 或长时矩阵。

## 10. 下一候选的 D2 合同

若参数不能解决退化，下一步应增加“身份未提交、运动学保守更新”的独立合同。该合同
尚未实现，至少需要满足以下约束。

### 10.1 身份和运动学解耦

- `identity_commitment_state` 继续保持未提交，不能因运动学支持自动恢复。
- 不生成 `detection_to_track` 身份绑定，不消费为 committed claim，不增加
  commitment generation。
- 不建轨、不 rebind、不 merge、不改写 `global_track_id`。
- identity hit、confirmation 和 identity confidence 不增加。

### 10.2 保守状态更新

- 只允许更新歧义分量中已经存在的成员航迹。
- 更新必须对观测排列不敏感，并使用整个可行候选集合，不选择一个观测作为硬身份。
- 后验协方差不得在歧义子空间内小于纯预测协方差。候选创新离散度、模型噪声和分量
  几何范围必须作为额外膨胀项，后验保持有限、对称和半正定。
- 均值修正必须有显式上限；超过上限时退回纯预测，不以大范围伪量测拉动航迹。
- 运动学支持使用独立计数和有界 TTL，不能重置身份 hard deadline。

### 10.3 时间、来源和回放

- 继续携带 measurement timestamp、arrival timestamp 和 D2 tracker frame timestamp。
- 同一 evidence generation 最多影响一次运动学状态，replay 和 generation 回退不得
  再次更新或延长租约。
- source binding、publisher epoch、不可逆 evidence key 和 claim ledger 规则不变。
- 恢复 committed 仍需新的原始证据严格越过水位线，并满足固定 0.9 秒发布新鲜度。

### 10.4 下游准入

- D2 发布运动状态时必须同时发布承诺状态、运动学支持模式、协方差膨胀量和证据时刻。
- main/D3 集成复验只允许 `committed` 航迹进入新 AssignmentPlan。
- 已有计划中的航迹转为未提交时，集成复验必须生成 hold/replan 结果并版本化发布。
- D5/D7 可以把未提交状态用于搜索视场或保持观察，不得据此重绑身份或执行新的终端
  控制许可。

### 10.5 验收

- source binding、publication freshness、replay protection、publisher epoch 和
  fail-closed 专项继续零违规；
- 未提交航迹进入 D3 的数量必须为 0；
- 不允许通过 uncommitted 航迹维持旧计划来提高分配数；
- seed 1100 同时满足 D2/D3 数量、track continuity、coverage continuity 不低于
  baseline，duplicate assignment 和 online truth use 为 0；
- 通过单 seed 后再进行多 seed 和长时测试。

## 11. 本轮边界

本轮只完成因果审计、参数扫描和合同建议。没有修改 D2 算法、0.9 秒新鲜度预算、默认
租约参数或默认启用状态。没有实现保守运动学更新，也没有修改 main/D3 的规划准入。

2026-07-23 因果审计阶段运行
`test_ambiguity_hold_lease.py` 和 `test_identity_commitment_v2.py`，结果为
`42 passed in 0.61s`。本次文档复核又运行完整 D2 回归，结果为
`291 passed, 1 warning in 31.00s`；warning 为既有 Matplotlib `Axes3D` 环境提示。
未运行额外 seed、长时重放或 AirSim。
