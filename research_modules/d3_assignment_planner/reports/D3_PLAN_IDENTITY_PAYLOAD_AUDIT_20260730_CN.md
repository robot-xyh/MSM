# D3 计划身份与载荷审计

## 结论

100 个高威胁 M 对 N episode 中有 48 个 episode 对同一
`plan_id/plan_version` 形成两次 D3 规划结果。48 组的资源-目标绑定、成员角色、联盟身份、
所有者、租期、未分配目标和规模字段均未发生执行语义变化。第二次结果只刷新规划时刻、
迟滞判断、成本分解和输入快照等诊断信息。

v3 故障不是 D3 把不同执行计划错误地放在同一版本下。直接触发摘要冲突的是 main
运行时在每个分配周期无条件重发 `modules.d3.assignment_plan`，并把本轮时间和动态诊断
写入权威载荷。同一身份因此对应两个完整载荷摘要，旧发布的联盟确认与新发布引用并发后被
D4 严格拒绝。

该问题在 v3 审计时按 P0 开放。main 随后接入 D3 权威发布判定并完成 v4 开发态重跑。
v4 证明同身份重发和摘要并发在开发态已关闭。正式 R0 尚未在 clean commit 和冻结清单下
执行，因此当前状态为“开发态验证关闭、正式 R0 待执行”。摘要、版本、所有者、代次、
租期和确认门限没有放宽。

## 审计范围

输入为 main 的 100-cell 开发预检：

`/dev/shm/msm-high-threat-r0-p0-precheck-v3-20260730`

场景覆盖 5、20、50、100 和 200 规模，每个规模使用 seed 1000 至 1019，仿真时长
2 秒。为取得预检汇总未保存的 D3 载荷本体，本次使用相同配置在内存中复现 100 个
episode，并逐字段比较前两次 `modules.d3.assignment_plan` 发布。

执行投影包含：

1. 资源、全局航迹、成员角色、联盟编号和联盟版本；
2. 中心或二级所有者、权威代次、租期及区域提交字段；
3. 未分配目标、目标数、资源数和分配数；
4. 计划编号、版本、创建时刻和求解器标识。

成本、迟滞判断、输入指纹和评估时刻不作为执行投影，但它们仍属于完整载荷摘要的一部分。

## v4 开发态复核

main 集成后输出为：

`/dev/shm/msm-high-threat-r0-p0-precheck-v4-20260730`

场景、规模、seed 和时长与 v3 开发预检一致。D3 对 main 实现和 100 个 episode 的
`summary.json`、汇总 CSV 进行只读审查，没有修改 main runtime。

| 项目 | v4 结果 |
| --- | ---: |
| episode 总数 | 100 |
| finite | 100/100 |
| 在线真值使用 | 0 |
| 权威计划身份 | 151 |
| 权威计划发布 | 151 |
| 计划 ACK | 151 |
| 同身份评估刷新抑制 | 48 |
| 权威载荷摘要冲突 | 0 |
| 重复传输引用计数 | 0 |
| D3-D4 当前计划对齐 | 100/100 |
| 当前计划联盟闭合 | 100/100 |

每个 episode 的权威身份数、权威发布数和 D3 topic 数一致。计划 ACK 数也与权威发布数
一致。输出目录中未出现 `payload_digest_mismatch` 或
`coalition_member_ack_cross_binding_invalid`。100v100 seed1010、200v200 seed1013 和
200v200 seed1017 的最终对齐与联盟闭合均恢复。

v4 是 2 秒三维质点开发预检。输出位于临时内存文件系统，运行源不是冻结后的 clean
commit，也没有正式结果 manifest、AirSim 或物理拦截证据。该限制不影响开发态 P0
关闭判断，但阻止把结果写成正式 R0。

审查期间，D3 全量回归最初有两条集成测试失败。第一条仍以最新 evaluation refresh
对象校验首次权威载荷；第二条仍期待该刷新生成第二个运行 ACK 和陈旧航迹 hold。两条
假设都与新合同冲突。测试现改为引用首次权威计划，并断言刷新不发布、不生成 ACK。
D3 算法代码未修改。专项 2 项通过；D3 全量收集 655 项，结果为
`654 passed, 1 skipped`，跳过项为未安装的可选 OR-Tools。相关入口 `py_compile` 和
D3-owned `git diff --check` 均通过。

## 统计结果

| 项目 | 结果 |
| --- | ---: |
| episode 总数 | 100 |
| 同一计划身份重复结果 | 48 |
| 完整载荷摘要相同 | 0/48 |
| 权威执行投影相同 | 48/48 |
| assignment 集合相同 | 48/48 |
| 成员或角色变化 | 0/48 |
| 联盟身份或版本变化 | 0/48 |
| owner/epoch/lease 变化 | 0/48 |
| 未分配目标集合变化 | 0/48 |
| assignment 序列顺序相同 | 15/48 |
| assignment 序列仅顺序变化 | 33/48 |
| 第二轮为联盟成员迟滞保持 | 32/48 |
| 第二轮为同分配 unchanged | 16/48 |

重复身份按规模分布为：5v5 20 个、20v20 17 个、50v50 8 个、100v100 2 个、
200v200 1 个。第一次计划在 0.70 至 0.95 秒形成，第二次均在 1.00 秒评估。

48 组中有 23 个 episode 在通信时序上实际形成 D4 摘要拒绝，共计
90 次 `payload_digest_mismatch` 和 90 次
`coalition_member_ack_cross_binding_invalid`。其余重复载荷没有碰到相同的 ACK
交错窗口，不能据此视为安全。

完整载荷的差异包括：

- 顶层发布 `timestamp`；
- `last_evaluated_at_s`、`evaluation_refresh_only` 和
  `execution_signature_changed`；
- 迟滞状态、理由、候选变化数、驻留和窗口预算；
- 当前成本、前序成本、成本边列表及其摘要；
- 航迹和资源输入指纹；
- 候选需求槽、矩阵形状和区域提示诊断；
- 33 组中相同 assignment 集合的序列化顺序。

上述字段可以用于评估和复盘，但不得改写已经发布的权威执行载荷。

## seed1017

200v200、seed1017 的第一次计划在 0.95 秒形成，第二次在 1.00 秒评估。两次均引用
版本 1，共有 198 条执行 assignment。

两次 assignment 集合、资源-目标对、成员角色、联盟编号和版本、owner、未分配目标均
一致。assignment 列表顺序发生交换。第二次结果为
`coalition_membership_hold`，并更新需求槽矩阵、迟滞成本、成本边证据和 200 个资源的
状态指纹。

逐叶比较得到 990 处完整载荷差异，其中 977 处位于 metadata。D4 最终记录
37 次 `payload_digest_mismatch` 和 37 次
`coalition_member_ack_cross_binding_invalid`。因此该 seed 的精确判断是：
执行计划没有重分配，失败来自同一权威身份下的载荷漂移和旧、新引用并发。

## 身份语义

同一 `plan_id/version` 下必须保持以下内容不变：

1. assignment 的资源、目标、成员角色、联盟编号和联盟版本；
2. 联盟成员集合、主备角色、波次、窗口和完成状态；
3. owner、authority epoch、lease、激活和区域原子提交语义；
4. 人工授权、来源节点、目标节点、链路和计划有效期；
5. 未分配和不完整目标集合、需求满足摘要、目标数和资源数；
6. 创建时刻、前序计划编号和执行 schema。

`last_evaluated_at_s`、当前成本、候选成本、迟滞原因、输入指纹、成本边证据和性能计数可以
随评估周期变化。这些字段属于 evaluation diagnostics。

迟滞保留原执行 assignment 时，D3 可以产生一个新的本地评估结果对象，但该对象仍引用
原计划身份。运行时必须继续使用首次发布的权威计划对象和完整载荷，不得把评估结果作为
同身份的新权威发布。若需要把“计划存活”与 D7 freshness 解耦，应使用独立心跳或评估记录，
不能靠改写原计划载荷完成。

## 缺陷归属

D3 版本管理没有在 48 组中漏升版本。`execution_signature()` 已覆盖 assignment、成员、
角色、联盟、owner 和 lease，现有发布检查也会拒绝同身份执行语义篡改。

D3 接口仍有一项合同歧义：`AssignmentPlan` 同时承载执行内容和动态诊断，调用方容易把
evaluation refresh 当作新的权威载荷。本轮新增
`AssignmentPlan.requires_authoritative_publication(previous_plan)`，明确区分新权威计划
与同身份评估刷新，并对同身份执行字段篡改失败关闭。该接口不改变 Hungarian、需求槽、
迟滞或版本算法。

v3 运行级 P0 的直接归属在 main adapter：

1. assignment due 时无条件发布 D3 topic；
2. 顶层 `timestamp` 使用本轮时刻；
3. 完整动态 metadata 被放入权威载荷；
4. ACK 和 D4 通信引用可能分别绑定同一身份的不同摘要。

v4 中 main 已按 D3 合同修复上述路径。首次权威计划按身份缓存；同身份评估刷新只更新
诊断；已有传输引用遇到不同摘要时在进入 ACK 链路前失败关闭。D3 没有发现新的模块内
身份语义缺陷。

## 最小修复合同

main 应保留每个计划身份的首次权威载荷和摘要。处理新的 D3 结果时：

1. 调用 `plan.requires_authoritative_publication(last_authoritative_plan)`；
2. 返回 `True` 时发布新权威计划，并替换当前权威引用；
3. 返回 `False` 时不重发 `modules.d3.assignment_plan`，只发布或写盘独立评估记录；
4. 同一计划身份若出现不同权威签名，立即失败关闭；
5. 传输重试如需重复发送，必须复用首次载荷的原始内容和 SHA-256；
6. 运行 ACK、联盟 ACK 和 D7 binding 始终引用首次权威发布的 sequence 和摘要；
7. 新 assignment、角色、联盟、owner、epoch 或 lease 只有在 D3 形成新版本后才能发布。

评估记录可复用 `d3_plan_history_record_v1`，或定义不带执行权限的新 topic。该记录需要
携带 source plan id/version 和 evaluated_at，但不得被 D4、D5 或 D7 当作新计划。

main 的必要回归应覆盖：

- 同身份迟滞刷新只产生一次权威 D3 发布；
- 评估记录可以多次写出，且不生成运行 ACK；
- 同身份不同权威载荷在发送前失败；
- 传输重试保持完全相同的载荷摘要；
- 100-cell 重跑中 `payload_digest_mismatch` 和
  `coalition_member_ack_cross_binding_invalid` 均为 0；
- 新版本计划仍能形成新的 ACK、D4 引用和 D7 binding。

main 已完成去重、诊断分流和开发态回归，本项可标记为开发态关闭。正式 R0 仍需在 clean
commit、冻结配置和结果清单下复跑同一门限；在此之前不得标记为正式关闭，也不得从本项
推导 AirSim、D7 控制或物理拦截结论。
