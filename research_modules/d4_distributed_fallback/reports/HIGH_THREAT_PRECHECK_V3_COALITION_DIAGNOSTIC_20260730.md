# 高威胁联盟闭合开发批次诊断

复核日期：2026-07-30

数据批次：`/dev/shm/msm-high-threat-r0-p0-precheck-v3-20260730`

## 结论

本批次 `high_threat_m_to_n` 共运行 5、20、50、100、200 规模各 20 个种子。100 个
episode 全部保持有限数值，在线真值使用为零，D3 与 D4 计划代次对齐为 100/100；当前
计划联盟执行闭合为 97/100。

三个未闭合 episode 都不是 D4 在收到完整同代 ACK 后仍拒绝提交。共同断点是 D3 当前
计划仍保留 `GT3D-000011`，但该航迹从 D2 当前输出消失后，main 构造 D4 快照时静默
跳过了该任务。D4 后续输出中不再有对应 region task 和 coalition commit；终态审计仍
从 D3 当前计划计算必要成员，因此报告三个成员全部缺失。

100v100 seed 1010 和 200v200 seed 1013 的当前计划广播及成员 ACK 已送达，联盟在任务
消失前已经提交。两例不属于通信丢包后的正常失败关闭，归属 main runtime 当前计划与
D4 快照任务清单不一致。安全门保持关闭，没有错误授权；该问题按 P1 可靠性缺口处理，
并作为正式 R0 重跑前的集成验收阻断。

200v200 seed 1017 同时暴露计划内容寻址冲突。同一
`plan_id/version/epoch` 对应两个不同规范载荷摘要。第一份计划产生的 ACK 与第二份
计划摘要不一致，D4 因 `payload_digest_mismatch` 正确拒绝。该现象来自旧、新计划载荷
交叉绑定，不是 ACK 摘要构造错误。计划身份不可变性属于 D3/main-owned P0 合同；D4
核心协议未发现新增 P0。

## 公共因果链

1. D3 发布带版本的当前计划，`GT3D-000011` 需要三个资源形成联盟。
2. main 发布 regional plan broadcast，成员生成 ACK intent，通信层记录
   `delivered/dropped`。
3. D4 对同代、同摘要、同 lease 的 ACK 进行验证，缺少必要成员时保持
   `collecting_acks`，成员齐全时转为 `committed`。
4. `t=1.20 s` 起，三个 episode 的 D2 当前输出均不再包含 `GT3D-000011`。
5. main 的 `_d4_snapshot()` 从 D2 当前航迹查询任务状态。找不到航迹时直接跳过，
   没有生成 hold/tombstone，也没有先取消 D3 当前计划。
6. 后续 D4 快照不再包含 `task:GT3D-000011`。重发和 ACK 即使继续送达，也没有对应
   task 可用于重评。
7. `d4_current_plan_execution_closure` 仍从 D3 当前计划出发，发现少一个 coalition
   target，并将其三个成员列为缺失。系统保持失败关闭。

三个 episode 的 lease 分别到 `6.0 s`、`6.0 s` 和 `5.95 s`。terminal drain 均运行
到约 `2.50 s`，没有发生 lease 过期。由于每成员两次重试已经耗尽，排空阶段没有新增
D4 intent；三例 `d4_terminal_drain_completed=false`。

## 100v100 seed 1010

### 当前计划

- D3 最新计划总线序号：1556；
- 计划身份：`d3-plan-016e14132d67/v2/e2`；
- 冻结 lease：`6.0 s`；
- `GT3D-000011` 必要成员：`INT-0014`、`INT-0019`、`INT-0017`。

### 状态与通信

- `t=1.00 s`：D4 为三个成员建立 `collecting_acks`，ACK 为 0/3。
- `t=1.05 s`：三个 legacy member ACK 分别在
  `1.08558/1.08939/1.08941 s` 到达，transport disposition 全为 `delivered`。
- `t=1.10 s`：D4 coalition commit 为 3/3，状态 `committed`，
  `execution_authorized=true`。
- 该 task 位于 `region-000`。region 内还有其他联盟未闭合，因此 region 整体仍为
  `hold_for_review/fail_closed`；这不改变 `GT3D-000011` 已完成 3/3 commit 的事实。
- 当前计划的三条严格广播绑定总线序号 1556 和摘要
  `ea92cec9...621a`，到达时间为 `1.06419/1.08839/1.09700 s`，均为
  `delivered`。
- 对应严格 ACK 到达时间为 `1.12425/1.13243/1.14797 s`，也全部为
  `delivered`。
- `t=1.15 s`：commit 仍为 3/3；重复 ACK 被幂等处理。
- `t=1.20 s`：D2 不再输出该航迹，D4 region 中该 task 和 commit 同时消失。

终态通信接收 580 条、接受 580 条、拒绝 0 条。执行闭合要求 11 个 coalition target，
实际审计到 10 个；终态将上述三个成员记为缺失。该缺失是最终快照缺 commit 的审计
结果，不是成员没有发送 ACK。

## 200v200 seed 1013

### 当前计划

- D3 最新计划总线序号：3034；
- 计划身份：`d3-plan-e3de86c4e0ef/v2/e2`；
- 冻结 lease：`6.0 s`；
- `GT3D-000011` 必要成员：`INT-0013`、`INT-0020`、`INT-0017`。

### 状态与通信

- `t=1.00 s`：D4 为三个成员建立 `collecting_acks`，ACK 为 0/3。
- `t=1.10 s`：D4 已接收 `INT-0013`，状态为 1/3。
- `t=1.15 s`：三个成员齐全，commit 转为 `committed`。
- 该 task 位于 `region-000`。region 整体因同区其他任务继续保持
  `hold_for_review/fail_closed`，目标级 commit 已完整授权。
- 当前计划三条严格广播绑定总线序号 3034 和摘要
  `99d02fa4...30c`，全部送达。
- 三条首轮严格 ACK 到达时间为 `1.13496/1.13697/1.19025 s`，均为
  `delivered`；legacy ACK 也没有发生该目标所需成员的丢失。
- `t=1.20 s`：D2 不再输出该航迹，D4 快照中对应 task 和 commit 消失。

终态通信接收 1075 条、接受 1075 条、拒绝 0 条。执行闭合要求 14 个 coalition
target，实际审计到 13 个。终态缺失三个成员同样来自快照任务静默删除。

## 200v200 seed 1017

### 计划身份冲突

D3 对同一计划身份发布了两份不同载荷：

- 总线序号 1875，发布时间 `0.95 s`，规范摘要
  `4d5594f32db2e4962f3686b37b8d4d916e11eb0bdd4b2c97683eba92bf265787`；
- 总线序号 2266，发布时间 `1.00 s`，规范摘要
  `b424ce9054d0a998c1cb7c41c9f68fe9910f89f1f0f7765b55234027a22a3bd8`；
- 两者身份均为 `d3-plan-30018d14aa23/v1/e1`，冻结 lease 为 `5.95 s`。

两份载荷的运行时内容实际不同，包括全局 assignment 顺序、资源角色、求解诊断和输入
状态。它们不能共享同一个内容寻址身份。main 的
`_d4_plan_transport_references[(plan_id, version)]` 被后发布记录覆盖，随后收到的
序号 1875 ACK 只能按序号 2266 的摘要验证。

### 状态与通信

- 必要成员为 `INT-0013`、`INT-0016`、`INT-0014`。
- 首轮 legacy ACK 中，`INT-0013` 和 `INT-0014` 为 `delivered`；
  `INT-0016` 的消息 `d4:coalition_member_ack:000000000215` 为 `dropped`。
- 绑定序号 1875、摘要 `4d5594f3...5787` 的三条严格广播和三条严格 ACK 均按原始
  摘要生成。ACK receipt 可解析且具有内容摘要，不存在
  `receipt_not_content_addressed`。
- 在 ACK 到达前，main 已把同一 plan key 的期望引用更新为序号 2266、摘要
  `b424ce90...a3bd8`。D4 拒绝旧摘要 ACK，拒绝原因是
  `coalition_member_ack_cross_binding_invalid/payload_digest_mismatch`。
- 终态共拒绝 37 条严格 ACK。该计数覆盖同一冲突计划中的多个联盟；其共同原因是旧
  摘要对新期望引用，不是单个 `GT3D-000011` 的 ACK 字段计算错误。
- 新摘要下 `INT-0016` 广播于 `1.14718 s` 到达，ACK 于 `1.18857 s` 到达。
- `t=1.15 s`：D4 仍有 legacy `INT-0013/0014`，缺 `INT-0016`，保持
  `collecting_acks`；`region-000` 保持 `hold_for_review/fail_closed`。
- `t=1.20 s`：D2 不再输出该航迹。D4 没有机会在含该 task 的快照中消费新摘要
  `INT-0016` ACK，task 随后消失。
- `t=1.23 s` 以后，新摘要下 `INT-0013/0014` 的重发广播和 ACK 继续送达，但 task
  已不在 D4 快照中。

终态执行闭合要求 13 个 coalition target，实际审计到 12 个；缺失成员为
`INT-0013/0014/0016`。D4 共接收 569 条因果通信，其中接受 532 条、拒绝 37 条。
通信拒绝体现了正确的失败关闭，不能通过放宽 D4 摘要门限解决。

## 缺陷归属

### D4 核心协议

未发现 D4-owned P0。D4 能在完整 ACK 下提交，也会在摘要冲突时拒绝交叉绑定证据。
近期完成的 plan ID、version、epoch、partition、冻结 lease 和内容摘要绑定正是
seed 1017 保持失败关闭的原因。删除这些检查会把旧 ACK 错误用于新载荷。

### Main runtime

当前计划任务静默消失属于 main-owned P1：

- `_d4_snapshot()` 对当前 D3 assignment 对应的 D2 航迹查询失败后直接跳过；
- D3 计划没有先失效，D4 也没有收到显式取消或 hold task；
- closure 审计因此看到“当前计划要求该联盟，但最终快照没有该联盟”。

正式验收应将其作为 R0 重跑阻断。若系统合同规定每个当前 D3 assignment 必须在 D4 中
显式出现，即使航迹暂时丢失也必须产生 hold/tombstone，则这是 main-owned 集成合同
P0；它仍不是 D4 状态机 P0。

### D3 与 main 计划发布

同一 `plan_id/version/epoch` 对应不同规范载荷属于 P0。内容寻址证据、ACK 重放防护和
跨节点共识都依赖计划身份不可变。运行时不得通过覆盖期望摘要来接受后发布载荷。

## 最小修复

1. main 在接收 `modules.d3.assignment_plan` 时，为
   `(plan_id, version, epoch)` 固定唯一的 authority payload 摘要。相同身份出现不同
   摘要时立即失败关闭并记录 `authority_plan_digest_conflict`，不得覆盖旧引用。
2. D3 只要 authority-relevant 内容变化，就发布新 plan version。仅诊断字段和时间戳
   变化时，应从规范授权载荷摘要中排除这些可变字段。
3. main 构造 D4 快照时，任务集合至少覆盖当前 D3 plan 的全部 assignment target。
   D2 暂时缺轨时生成显式 `track_unavailable` hold/tombstone，或先使当前计划失效并
   触发 D3 新版本重规划，不能静默 `continue`。
4. 已提交联盟的取消必须由新计划版本或显式撤销合同表达。当前航迹暂时缺失不能隐式
   删除 commit。
5. terminal drain 在任务缺轨时仍应保留当前计划的失败关闭 task，直到新计划、显式
   撤销或 lease 到期。

## 验收建议

main-owned 回归至少覆盖：

1. 相同 `plan_id/version/epoch`、不同规范摘要：第二份发布被拒绝，原摘要不被覆盖，
   所有旧 ACK 继续只绑定原计划。
2. D2 单帧或多帧临时丢轨：当前 D3 assignment 在 D4 中以显式 hold/tombstone 存在，
   closure 不把任务静默删除，控制保持失败关闭。
3. 已提交联盟遇到丢轨：只有新计划版本、显式撤销或 lease 到期能够取消。
4. 丢轨后 D3 重规划：旧计划关闭、新计划新版本建立，ACK 不跨版本复用。
5. 复跑本批次 100 个 episode：有限数值和在线真值隔离保持 100/100；D3-D4 plan
   alignment、当前计划 task coverage 和 coalition execution closure 均为 100/100；
   任一摘要冲突计数为零。

## 本次验证

- D4 因果通信、区域资源安全采纳和区域接管定向回归：165 passed；
- D4 owned paths `git diff --check`：通过；
- D4 源代码修改：无；
- D4 全量回归：未重复执行。此次仅修改诊断和状态文档，定向回归满足本次复核范围。

## 修改边界

本次没有修改 D4 协议代码，也没有修改 main-owned
`research_modules/scalable_3d_simulation`。D4 文档只记录开发批次证据和开放缺口，
不将 97/100 写成已关闭。

## v4 修复后复核

复核日期：2026-07-30

数据批次：`/dev/shm/msm-high-threat-r0-p0-precheck-v4-20260730`

### 结论

v3 诊断提出的 main-owned 当前计划任务覆盖和同身份权威载荷重复发布问题，已在 v4
开发批次关闭。新批次仍覆盖 5、20、50、100、200 规模各 20 个种子：

- 有限状态：100/100；
- 在线真值使用：0；
- D3-D4 当前计划对齐：100/100；
- 当前计划联盟执行闭合：100/100；
- D3 权威计划摘要冲突：0；
- 使用过计划期航迹 fallback 的 episode：28/100；
- 高协方差 tombstone 使用数：0。

三个原失败样本均闭合：

- 100v100 seed 1010：fallback 快照 29 次，最终对齐且联盟闭合；
- 200v200 seed 1013：fallback 快照 17 次，最终对齐且联盟闭合；
- 200v200 seed 1017：fallback 快照 41 次，同一计划只发布一次权威载荷，摘要冲突
  计数为零，最终联盟闭合。

### 合同复核

新行为符合 D4 合同。main 以当前 D3 assignment target 为快照任务基准，D2 临时
缺轨时使用同一计划内最后可信、真值隔离的 D2 状态和协方差。任务和已提交联盟不会
因单帧缺轨被隐式删除；其权限边界仍由新计划、显式撤销或 lease 到期决定。缓存证据
继续携带原更新时间，D4 可以观察量测年龄增长。

D4 没有恢复或伪造 D2 身份承诺。D7 的当前身份门保持独立，缺少当前 D2 航迹或身份
承诺时不产生该目标的导引绑定。由此可同时满足“联盟因果状态不被静默删除”和“控制
不得依赖失效身份依据”。

同一计划身份的 evaluation refresh 不再覆盖首次权威 transport reference。执行签名
若发生变化，main 直接失败关闭；执行语义变化必须提升 D3 计划版本。D4 的 SHA、计划
ID、版本、epoch、冻结 lease、分区代次、联盟成员和 ACK 校验均未放宽。v4 仍存在少量
按既有合同拒绝的通信证据，但没有 authority plan digest conflict，也没有影响最终
100/100 闭合。

### D6 独立审计

D6 已完成 v4 独立审计：

- 计划 ID/版本对齐：100/100；
- 当前多成员联盟目标：644 个，闭合 644/644；
- 通信处置：195838 条，100/100 episode 为 available/verified；
- D3 区域 epoch 对照字段：0/100 available；
- D3 区域 lease 对照字段：0/100 available。

epoch 与 lease 两项不能由计划 ID/版本对齐结果推断，保留为开放 P1。审计对象仍为
dirty development 批次，formal R0 未运行。

### 证据边界

v4 是 dirty development source 上的 100 项高威胁预检，仿真时长为 2 秒。它关闭
此前 main-owned P1 的开发态验证项，不是新的正式 R0。当前仍需：

1. 从 clean source 完整重跑 900 项正式矩阵；
2. 补齐 D3 区域 epoch 与 lease 对照字段，并由 D6 在正式矩阵中复核；
3. 在正式矩阵中覆盖长期缺轨、显式撤销、新版本替换和 lease 到期；
4. 确认 28 个 fallback episode 反映的 D1/D2 临时航迹缺失不会被误写成感知质量已
   解决。

### 修改与验证

- D4 算法代码修改：无；
- main runtime 修复：由 main 完成，本报告只读复核；
- D4 ACK 校验修改：无；
- D4 no-op 集成测试：更新为验证同身份诊断重评不产生第二份权威计划，6/6 通过；
- D4 全量回归：903/903 通过；
- 环境告警：既有 Matplotlib `Axes3D` 导入警告 1 项，与 D4 合同无关；
- v4 开发批次：100/100 当前计划联盟闭合；
- 正式 R0：未执行。
