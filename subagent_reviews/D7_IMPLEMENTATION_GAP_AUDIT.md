# D7 比例导引与末端视觉 PNG 实现差距审计

## 2026-07-25 GAP 更新：分配对状态生命周期缺口关闭

此前 `ScalableGuidanceController3D` 只在调用方显式 reset 时删除 pair state。长期
滚动分配中，已撤销、已改绑或目标已丢失的 `(resource_id, global_track_id)` 可能继续
保留。该问题会使状态数量随历史分配累积，并限制 D6 对模式和滤波状态的归因。本轮已
在 D7-owned 范围关闭。

当前批处理先从 binding、active plan 和 GlobalTrack 生命周期判断有效 pair，在命令
计算前对账并回收资源改绑、目标丢失、分配撤销/过期、旧计划和批次缺失状态，避免
旧、新 key 在批内短暂叠加。同 key 的
plan id/version 变化记为状态重置。D4 pending、D5 reacquire 和短时视觉丢帧属于暂态
控制门，不属于分配失效，保留同一 pair 的滤波历史。每批输出活动状态、创建/复用/
重置/回收、回收原因、模式迁移、末端拒绝、饱和、非有限阻断和时延诊断。暂态视觉
历史只在既有 `0.25 s` coast 时限内保留，超时仍清空。
同一批次重复 `resource_index` 或 `resource_id` 会在状态对账前拒绝，避免同一资源
消费两个当前分配。

验证日期为 2026-07-25。冻结输入共 200 pair、9 批次；峰值统计覆盖批前、对账后和
逐 pair 计算阶段。最终有效 pair/state 为
`170/170`，峰值状态 200。累计创建 250、复用 1120、计划版本重置 330、回收 80；
回收分布为资源改绑 40、目标丢失 10、批次撤回 20、旧计划版本 10。状态上界违规、
旧计划接受、身份改写和非有限命令均为 0，暂态滤波状态保持检查通过。D7 全量
`220 passed`，验收阈值为零失败。

**P0 状态：** 未新增运行级 P0。身份、计划版本、D4/D5 合同和非有限命令继续
fail closed。

**仍开放的 P1：**

1. main 尚未把新的生命周期诊断写入统一 episode sidecar，D6 不能在正式多 seed
   结果中关联状态回收、模式迁移和物理结果；
2. 200v200 长时物理闭环、持续视觉末制导和至少 20 个未见 seed 尚未验收；
3. 冻结输入的内存和时延来自单机、单次、启用 `tracemalloc` 的开发测量，不能替代
   固定硬件实时预算；
4. AirSim/SimpleFlight 姿态、推力、碰撞、相机时序和实际平台饱和仍未闭合；
5. 多成员同时到达和避碰不在当前要求内，也未由本轮实现。

本轮未修改 PN、视觉 PNG、LOS、TTC、外推或 `png_guidance_delivery` 核心公式。

## 2026-07-23 GAP 更新：整栈差异未复现为 D7 内核回归

clean `0d2da25 -> 5263e2b` 的 20-seed 整栈 D7 累计墙钟均值为
`3.637837 -> 3.858795 s`，逐 seed 变化均值 `+6.243%`，95% bootstrap 区间
`[+2.954%, +9.825%]`。该现象是有效的系统级性能告警，但两个提交的 86 个 D7
受控源文件摘要完全相同，20/20 跨构建语义审计也全部通过。

固定 200-pair/185-frame replay 在两个工作树各执行 6 次。命令、世界加速度、最终
pair 状态、mode 和 gate reason 严格相等；内核变化为 `+0.626%`，95% bootstrap
区间 `[-1.828%, +3.178%]`。分段 profile 中各类别占比在两版间近似一致，没有出现
候选独有热点。因此不新增 D7 P0/P1 代码缺口，不修改 PN/PNG、LOS/TTC、切换门或
调用频率。

保留的 P1 是证据和系统计时边界：

1. main 的 `module.d7_guidance` 仍同时包含输入组织、D7 内核和世界数组复制；
2. 历史 episode 没有保存完整 D7 pair 输入和私有状态 sidecar；
3. 参考版本没有逐调用 P50/P95，不能与候选 `19.572/22.520 ms` 直接配对；
4. 尚未记录 CPU 频率、温度、上下文切换和缓存计数器；
5. 固定 replay 的视觉 PNG 样本不足以代表真实末端相机链路。

该 P1 的 owner 以 main 性能编排为主，D7 只在未来冻结输入确认稳定模块回归后实施
局部优化。专项详情见
`D7_SCALABLE_3D_GUIDANCE_PERFORMANCE_AUDIT_20260723.md`。

## 2026-07-22 GAP 更新：三维导引 `+7.337%` 未形成代码缺口

clean `8f86192 -> f80b5bd` 三 seed 中，D7 累计 guidance 均值由 `4.991960 s` 增至
`5.358198 s`。专项审计确认两个提交的 D7 文件、terminal gate 和 main 计时路径 blob
相同；三 seed 的 185 次调用、逐帧 pair 数、命令、mode、gate reason 和规范化 D7
topic 哈希均一致。seed 42002 的单点 `+21.430%` 主导汇总，前两个 seed 合并只变化
`+0.328%`。

200-pair 冻结复测覆盖中段、持续中段、stale hold、lost hold、恢复和计划版本切换。
两个独立 controller 的命令数组、完整命令、pair snapshot 和状态迁移逐项相同。同一
源码 12 次平衡交错墙钟测量的总体变异系数为 `12.26%`，人为标签组仍可相差约
`6.58%`。因此没有证据把历史变化归因于 D7 新增重复工作，不新增 D7 P0/P1 代码
blocker，不修改核心代码。

开放性能 GAP 仍是系统级 200 对实时 P1：需要 main 保存 per-call 分布，并把输入查找
和 D4 permission、D7 内核、数组复制、publication 分段。历史私有 pair filter 快照未
写盘，跨构建只直接证明公开命令序列一致；冻结输入补充的是确定性证据，不能替代未来
正式未见 seed 运行。专项详情见
`D7_SCALABLE_3D_GUIDANCE_PERFORMANCE_AUDIT_20260722.md`。

## 2026-07-21 GAP 更新：隔离双臂命令合同关闭

D7-owned 的“control/treatment 各自消费计划并保留可审计命令血缘”缺口已关闭。
`isolated_arm_guidance.py` 提供版本化 context、command、validator、summary、batch 和
world-application receipt。每条命令都绑定 experiment/seed/arm/episode、隔离世界、
源计划 id/version/hash、assignment binding、生成时刻和控制模式；pair 状态同时在
arm 和 resource-track 两级隔离。写回凭据明确是 isolated simulation confirmation，
不是 production runtime ACK。

负向验收覆盖错 arm、跨臂 command/receipt、旧计划、计划 hash 篡改、同版本 hash
冲突、D4 不允许、D5 显式 terminal gate 不满足、resource-track mismatch、held 命令
误写回和在线 truth/actor/object 身份字段。所有失败均在加速度暴露或写回凭据生成前
fail closed；`global_track_id` rewrite 为 0。2026-07-21 新增 9 个场景，D7 全量
`213 passed`，门槛零失败；200 pair 样本的状态和 binding hash 均逐对隔离。核心
PN/PNG/LOS/TTC/coast 公式没有改动。

当前状态表：

| 项目 | 状态 | 剩余边界 |
| --- | --- | --- |
| D7 隔离 arm context 与命令 schema | implemented/tested | main 尚未切换 paired rollout runner |
| source plan/binding/command SHA-256 | implemented/tested | 正式实验 manifest 仍由 main 生成与冻结 |
| generated/held/applied 三态与 summary | implemented/tested | D6 尚未消费新的 command/receipt sidecar |
| isolated world application receipt | implemented/tested contract | 仅 main 写回确认，不能称 production ACK |
| control/treatment 多周期物理效果 | unavailable | 需要 main 克隆世界、同外生时序和后续状态窗口 |
| D4 degraded paired rollout | unavailable | 应使用独立降级场景，不以 nominal 5v5 代替 |

因此 D7 此项不再列为模块接口 P1；开放 P1 位于 main/D6 的多周期集成、写盘、结果
关联和保留 seed 验证。任何离线 receipt 都不得升级成真实在线确认。下文旧 GAP 记录
保留为历史状态。

## 2026-07-20 GAP 重分类：scalable point-mass 3D runtime 已实现

此前表中“online/default 3D PN 控制律仅有 P2 benchmark”的描述已被本轮部分取代。
`scalable_3d_guidance.py` 现提供独立、确定性、可执行的三维质点路径：D2 六维
GlobalTrack + covariance、D3 current binding/version、D4 permission、D5
TerminalAssociation -> per-pair 三维 PN/视觉 PNG/coast -> resource-indexed NED
acceleration。legacy 二维 API 与 delivery 公式保持原样，因此这不是以新路径替换
历史 AirSim/SimpleFlight 默认链路。

关闭证据日期为 2026-07-20。新增 14 个确定性场景全部通过，D7 全量
`204 passed`；覆盖 1/7/200 pair finite 命令、实际 D2/D3 DTO、高度差、TTC/LOS、D5
metadata、2 帧/0.25s dropout、D4 三类 pending、stale active plan、D5 version、camera/
maneuver gate，以及 1 个无随机 seed 的 2-resource/1-target 质点 fixture。5 米验收为
任一 pair 独立首达，首达时另一 pair 仍 `>5m`。安全违规预期值和实测值均为 0：
stale plan 接受 0、D4 pending 视觉切换 0、non-locked/capability-failed 视觉切换 0、
`global_track_id` rewrite 0、端到端 RL 使用 0。

GAP 状态更新如下：

| GAP | 新状态 | 剩余限制 |
| --- | --- | --- |
| 六维 NED 3D PN 与世界回写 | D7-owned implemented/tested，main 已接统一 episode 状态机 | 200 对长时多 seed 物理闭环与正式耗时仍开放 |
| 末端三维 strapdown TTC PNG | D7-owned deterministic path implemented/tested | 真实 D5 相机流、姿态同步、识别率和 AirSim 外参未标定 |
| per-pair filter/extrapolation/coast | implemented/tested | 仅 2 帧/0.25s 固定默认，尚无多 seed 平台调参 |
| 5 米闭环 | point-mass fixture passed | 不是 AirSim truth-isolated 多 seed 物理成功率 |
| 真实平台三维机动能力 | open calibration | 姿态/推力、转率、爬升率、延迟、碰撞与 realized command 待测 |
| cooperative 3D guidance | not implemented | 仍无 impact-time consensus、同步到达或成员避碰；本轮明确不要求同时到达 |

因此该 GAP 不能再写成“3D runtime 未实现”，也不能写成“3D AirSim 已闭合”。准确
口径是“scalable point-mass runtime 实现并单测完成，main/AirSim/D6 标定开放”。
下文 2026-07-15 及更早条目保留为当时审计快照。

## 2026-07-15 M5N2 20-case GAP 复核

20 个 truth-isolated 真实 AirSim SimpleFlight M5N2 case 已完成，baseline/candidate 各 10 seeds。M5N2 `20/20` 后 TERM 生效前仅额外完成 `p1_terminal_timing_funnel_10seed_20260715_png_ttc_2v2_seed001`；该单 seed 不纳入本次 M5N2 GAP 统计，也不用于分析或晋级，其余 tuned case 和全部 dropout 均未执行。P0 仍无新 blocker：20 个 M5N2 case 的 online truth identity/state 使用数均为 0，在线目标状态来自 D2 估计，本轮未改 PN/PNG/LOS/外推公式、`global_track_id` 或 D3/D4/D5 gate。

**仍开放的 P1：**

1. **第二 primary 与 coalition 物理闭环未达标。** baseline/candidate active pair 均为 `6/30`，target 均为 `6/20`，coalition 均为 `0/10`；合计 pair/target/coalition 为 `12/60`、`12/40`、`0/20`。第二 primary 按各 case 的 active membership 动态识别，不写死资源编号，物理结果为 `0/20`。
2. **停控归因证据不完整。** 第二 primary 七阶段证据为 `assigned/visible/associated/contract=20/20`、`control/mode=17/20`、physical=`0/20`。20 例均以 `collision_stop` 结束且 collision object 缺失。main 需补齐 collision object、member separation、持续 measured lock 和停控前后时间线，否则不能在航路、机动、D5 gate 和 AirSim 碰撞状态之间归因，更不能将失败归因于 PN、PNG、LOS 或外推公式。
3. **candidate 非退化未通过。** paired active-pair 结果为 6 持平、2 改善、2 退化；trend coast 实际触发为 0，soft-specific duration 为 0，通用 image-KF predicted `14 -> 19` 不能作为 candidate 触发证据。默认保持关闭。
4. **100 ms 实时预算未闭合。** 3805 个 control tick 均值/P95 为 `1069.4/1254.1 ms`，全部超限；main-bus 均值/P95 为 `349.3/487.4 ms`，`3649/3805` 超限。D7 guidance-contract 均值/P95 仅 `4.84/5.78 ms`，故当前瓶颈主要是 main/runtime 的 frame sampling、D1 fusion 和 control RPC，不是 D7 公式计算。

旧的“真实 multi-seed 未采集”缺口已被这 20 case 关闭，不再保留为 P1；现在的 P1 是实测结果未达 5 米/coalition 标准、candidate 未通过晋级条件和性能预算未闭合。

## 2026-07-15 P1 诊断子缺口状态

已关闭 D7-owned 的被动诊断缺口：第二 primary 现在携带规范十级漏斗、细粒度质量门、首失败 stage/reason 和阶段首达时刻；measured-lock 已区分当前帧真实量测、历史锁定和 bounded prediction；seed2 单帧 dropout 与 `png_ttc` 面积跳变/裁剪均有确定性受控回归。验证为 D7 全量 `190 passed`，验收阈值零失败，未运行 AirSim，未修改核心公式或放宽门控。

仍开放的 P1 是证据采集而非 D7 DTO blocker：真实 2v2/M5N2 至少 10 seeds 的第二 primary 漏斗与 5 米结果、真实单帧 dropout 的 measured-lock 时序、真实 bbox area-jump/clipping 样本、loop latency 及三维机动/成员间距。未收集前不得宣称物理闭环或候选晋级。

## 2026-07-14 actual-execution GAP 状态同步

canonical 真实执行证据链 P0 已关闭。五层按 contract/control/terminal-switch/mode/physical 独立统计：tuned 2v2 为 `35/26/26/2/2`，M5N2 为 `67/0/0/0/2`，合计 `102/26/26/2/4`；五层均为 `available`。`terminal_switch_allowed_count` 直接从已写盘 `control_commands` 独立统计，不从 control 层推断或回填。两个 seed-1 required case 均 available，summary/CSV/canonical physical count 与 plan identity 一致，identity/state online truth 均为 0。M5N2 active pair 是 `2/3`、第二 primary 最近约 `11.02 m`，target `2/2` 不能替代 coalition `0/1`。

P1 仍开放：第二 primary acquisition/5 米闭环、同配置 multi-seed/dropout/candidate、约 `123.3/384.6 ms` loop latency，以及 pair funnel/closing-speed/三维几何与机动标定。D6 formal overall fail 反映完整 P1 suite 未通过；terminal-switch 和 main/D6 canonical 聚合均已闭合。3D PN、True PN、APN、FRPN 在线化和同时到达不列当前 P1。该同步不修改 PN/PNG/LOS/外推代码或算法。

## 2026-07-14 导引律语义合同复核

**D7-owned P1 已关闭，P0 无新增。** `D7RuntimePairOutput` 和 `as_log_record()` 现以 `d7_guidance_law_semantics_v1` 输出 `configured_guidance_law`、`configured_midcourse_guidance_law`、`configured_terminal_guidance_law`、`candidate_guidance_law`、`executed_guidance_law`、`visual_control_active` 和 `executed_visual_mode_switch`。这些字段由现有单一状态派生，不复制控制状态；旧 requested/candidate/guidance 字段继续兼容。termination snapshot 没有 executed law。summary 分开聚合三类律，并输出语义违规数和实际视觉入口切换数。

新增不变量回归证明：视觉候选已计算、raw/effective contract 已通过但 bbox/camera gate 失败时，实际执行仍为 `radar_pn`，`latched_visual_mode_active=false`、`effective_control_authorized=false`、`executed_visual_mode_switch=false` 且无视觉速度可消费；视觉入口只有在 effective control 后才计一次实际切换。`guidance_law_semantic_violations()` 会标记无授权视觉律、无锁存有效控制、candidate/configuration 不一致和 termination 执行等错误。2026-07-14 D7 全量为 `188 passed`，零失败；未修改 PN、VM/TTC PNG、LOS 或外推公式。

**canonical 聚合已关闭，证据扩展仍开放。** actual-v2 之前的 postbatch M5N2 曾出现物理 control plan 与 main episode bus replay plan/state instance 不一致；`control_commands.csv` 还把配置/候选 `png_vm` 写成看似执行律，而 canonical D7 bus record 明确为 `executed=radar_pn/effective_control=false`。当前 actual-v2 已以 plan identity 一致和五层独立统计关闭 canonical P0；terminal-switch 层直接从 `control_commands` 统计，不能从配置律、候选律、handover 状态、control 层或 legacy active-sample alias 推断。后续 multi-seed 与 pair-funnel 标定继续保持同一 live instance。

## 2026-07-14 M5N2 no-switch 诊断 P1 关闭与外部 P1

D7-owned 缺口已关闭：`d7_pair_guidance_funnel_v2` 现在按 assignment pair 输出配置交接距离、D5 declared/measured lock、raw gate、camera/LOS/closing-speed/maneuver、effective contract、latch、effective control、mode 和 physical 的 available/reached 漏斗，并汇总全 pair 首失败 stage/reason。runtime 仅新增闭合速度既有门限的显式结果/阈值，未修改 PN/PNG/LOS/外推公式或任何 D3/D4/D5/身份/版本门控。`raw gate=false` 且没有 reject reason 会产生明确数据质量告警，不再归因到默认 false 的 camera 或 maneuver 字段。2026-07-14 当日 D7 全量回归为 `188 passed`，验收阈值零失败。

只读实测证据仍保留开放 P1：seed-1 M5N2 baseline/candidate 的 raw/latch/effective contract/control 均为 0；INT-01/INT-04 在约 `35-39 m` collision stop，未到约 `30 m` 交接区，INT-02 到约 `26 m` 后仍 `d5_not_locked` 并 acquisition timeout。2v2 `png_ttc` 与 1-frame dropout 为 2/2。五层 canonical 聚合已经可用，但 seed-1 的完整 raw reject/measured-lock/closing-speed pair-funnel 覆盖仍不足；航路净空、D5 acquisition、真实 dropout/candidate 和 multi-seed 仍未关闭。该 P1 不回退 D7-owned 诊断关闭状态，也不能通过放宽 gate 修复。

## 2026-07-14 末端状态/指标语义 P1 关闭

该 P1 已在 D7-owned 代码关闭。runtime row/summary 以 `d7_terminal_semantics_v2` 分离 raw terminal gate、latched visual mode、effective terminal contract、effective control authorization、mode transition 和 termination snapshot；旧 contract/switch/control/visual 字段保留为 canonical effective 字段的兼容 alias。termination/abort 快照不再作为 live gate/control/mode-transition 样本，并保留终止前状态。D5 `reacquire` dropout 的无命令结果现在可按 `contract_reset`、`prediction_window`、`measured_lock_not_established` 审计。

安全边界未变：bounded coast 只在 raw D5 non-lock/reacquire、prior measured state 和 active latch 下尝试，且必须保持 resource/global/local identity、current plan/owner/version、D4 许可并无 friend/duplicate/safety 冲突。2026-07-14 D7 全量结果 `188 passed`，验收阈值为零失败，覆盖 termination snapshot、raw/latch/effective scope、三类 dropout 原因、pair first-failure/funnel、导引律执行语义和 local-ID mismatch fail closed。main/D6 canonical 五层消费已经闭合；真实 dropout/candidate 和 pair-funnel/closing-speed 标定仍是 P1。位置 PN、VM/TTC PNG 和 `png_guidance_delivery` 核心公式未修改。

## 2026-07-14 truth-state P0 关闭复核

main/runtime 已在代码和 mock 回归层关闭此前外部 P0。默认、主动中心重规划和主动二级接管均从 episode bus 消费 D2 estimated target position/velocity、协方差和双时间戳；主动合同覆盖只能更新 D3/D4/D5 合同，不能注入运动状态或 actor/object/mesh alias。估计缺失或陈旧时 fail closed。actor truth 只允许用于合成传感器、离线 pairing、绘图和运行后 NED 三维 5 米 scorer。AirSim runtime 回归为 `130 passed`，覆盖 actor truth 扰动命令不变、两条主动路径 `truth_state_online_use_count=0` 和 D2 state source。D7 PN/PNG 核心公式未修改，因此 D7 当前无运行级 P0 blocker。

真值身份与真值状态必须独立审计：`truth_identity_online_use_count=0` 不能替代 `truth_state_online_use_count=0`。迁移前 2v2/M5N2 日志只记录前者，历史物理结果仍是控制接口 smoke/离线评分基线；2026-07-14 actual-v2 seed-1 已同时证明两者为 0 并关闭 canonical P0 证据链。多 seed 和性能标定仍是开放 P1 evidence。

## 2026-07-13 M5N2 最终 P1 证据

**2026-07-13 阶段回归值**：D7 当时全量测试为 `188 passed`。本文后续出现的
`184 passed`、`181 passed`、`178 passed`、`175 passed`、`117 passed`、
`109 passed`、`105 passed` 等数字均为更早子任务完成时的历史阶段计数。当前权威值
以本文顶部最新日期小节为准。

D7 已补齐 10-seed case/seed 隔离和第二 primary 全漏斗诊断，字段覆盖 assigned/active/radar、D5 visible-associated-locked、closest approach、contract/control/mode/physical、首失败、成员间距、reserve unauthorized 及 owner/version mismatch。最终批次包含 40 个真实 AirSim SimpleFlight M5N2 episode；高威胁目标采用 `2 primary + 1 standby reserve`，physical completion 定义为同一 episode 内两个 active primary 分别进入 5m，不要求同时到达。最佳 profile coalition 为 `5/10`，全部 profile 合计 `8/40`，未达到 `8/10` 晋级门限。

D6 四层统计为 contract `35`、control `7`、mode switch `9`、physical `62`。这些层的判定条件和样本口径不同，只能分别审计，不得从任一层反推其他层。迁移前安全审计为 reserve unauthorized `0`、`global_track_id` rewrite `0`、truth identity online use `0`；当时没有独立 truth-state provenance，physical 层不得升级为当前闭环证据。位置 PN 与 `research_modules/d7_proportional_guidance/png_guidance_delivery` 视觉 PNG 核心公式未修改；D5 原生 ByteTrack/BoT-SORT 未准入，默认检测输入保持 AirSim `simGetDetections`。

**审计范围**：`research_modules/d7_proportional_guidance/` 的 README、PLAN、代码和测试，`png_guidance_delivery/` 方案资料，以及 D7 在 `research_modules/airsim_runtime/intercept.py` 中被消费的实际状态。
**修改边界**：本次只更新 D7-owned 代码、测试、文档和 `subagent_reviews/D7_*`，不修改 D1-D6、main runtime、root report 或其他模块。
**系统边界**：D7 只做导引律、导引状态、末端 PNG gate 和日志合同；D7 不分配目标、不授权、不创建、不改写、不本地重绑 `global_track_id`。

## 总体结论

### 2026-07-13 secondary assist 语义修复

P1 合同歧义已关闭：`request_secondary_assist` 的 `target_node_id` 现在只表示观测 cue 提供者，不再与 D3 `owner_node_id` 比较，也不再要求 `takeover_ready`。中心 plan/version 与 D5/安全门控有效时，D7 继续 radar PN，并可在视觉稳定后按原 gate 切换 PNG。真正二级接管只依据 binding 的显式 `active_plan_owner=secondary` 或 `secondary_takeover_state` 判定，仍要求 owner 一致和明确 `takeover_ready`；节点名称不再用于猜测中心、二级或 peer 角色。`request_center_replan`、二级过渡动作、未完成 distributed commit 继续 fail closed。该 secondary-assist 子任务完成时的阶段回归为 `175 passed`，该阶段后续全量值为 `188 passed`。当前权威值以本文顶部最新日期小节为准。未修改 `png_guidance_delivery` 的 PN/TTC-PNG/LOS/外推公式或参数。

### 2026-07-12 delivery 增强与验证同步

当前没有新增 P0 blocker。图像 KF 生命周期、`png_ttc` 面积治理和统一 `0.25s` 外推硬上限已经实现。soft innovation prediction 与水平 LOS trend coast 仍默认关闭，6D LOS KF 保持 replay-only；这些 optional 能力没有晋级默认路径，也不改变位置 PN、`png_vm/png_ttc` 核心公式。

本轮关闭 per-primary terminal authorization 的 D7-owned P1 接口缺口：binding/decision/runtime row/summary 已携带 scope 与 arrival coordination policy。只有显式 `per_primary + arrival_coordination_required=false` 的 active primary 可跳过共同 arrival window 和 coalition visual completion，按自己的 D5 lock、camera/bbox/LOS/maneuver gate 独立进入 PNG。旧合同仍为完整 coalition gate；reserve standby、D4 pending/reconfiguring、ACK/lease/epoch、owner/version、friend/duplicate 均有负向回归。输出 `per_primary_authorization_active`、`coalition_visual_completion_bypassed`、`bypassed_arrival_only`，未修改 PN/PNG 核心公式。剩余 P1 是 main 在真实 AirSim 中接入 D3 新字段并做多 seed 物理验收。

follow-up 已关闭 topology typed API 断点：`build_cooperative_guidance_topology()` 的 `terminal_authorization_scope` 与 `arrival_coordination_required` 均支持统一值或 per-target mapping，并同时写入 target topology 和所有 binding。显式 per-primary/false 的 active primary 不标记 arrival window required，reserve 仍生成 standby；默认旧调用保持 coalition/true。验证覆盖按目标混合 policy、非法/缺失 mapping、默认 fail-closed 和无 window 的 per-primary terminal contract。main 可直接消费 typed topology，不再需要运行时补写 metadata。

2026-07-12 posefix 真实 replay 复核：baseline/w03/w05/w08 的 `control_commands.csv` 分别有 609/651/431/634 行，pair 物理成功为 1/1/0/1，coalition completion 均为 0。指定的 `coalition_window_closed` 为 3/4/0/4 行，`coalition_not_activated` 为 8/0/2/0 行，`d4_owner_missing` 仅 w08 出现 15 行；这些行的视觉 PNG 许可均为 0，全部记录 radar PN 回退。w08 owner 缺失段为 INT-02 在 10.0-11.6s 间收到 `airsim_control_plan v1` 且 owner 为空，D7 保持 fail-closed，不从 D4 target node 反向补写 owner。四组 plan identity change 为 159-276 次、版本回退为 35-90 次，证明滚动 binding 抖动会清空视觉 history/latch；同时大量 `d4_terminal_inconsistent` 和 D5 非锁定仍是上游闭环问题，不能把 coalition 0/4 只归因于这三类拒绝。

本轮关闭 D7-owned 的 P1 子缺口：兼容的单调 current binding 更新保留图像滤波/迟滞历史，但最新 D3/D4/D5 版本仍逐帧重验；owner/target/activation/role 改变或版本回退仍重置。`coalition_window_closed` 改为“视觉窗口关闭、radar midcourse 继续”，不再误标 `abort_revoke`。新增 `airsim_contract_replay.py` 和真实 CSV excerpt 回归，输出三类拒绝对视觉许可、radar PN 回退、受影响资源、连续区间、最小距离和计划回退的审计。剩余 P1 在 main/runtime：消除 sparse `airsim_control_plan v1`、保存完整 owner/coalition binding，并做真实多 seed 非退化验证。

2026-07-12 P1 协同诊断增量：D7 已新增任意 primary 数的被动 pair/coalition 漏斗和 candidate 预筛接口，字段覆盖 radar midcourse、重捕、terminal contract/control/mode、physical intercept、range/closing speed、arrival-window error、closest approach、member separation、first failure、第二 primary 失败阶段和 coalition arrival spread。受控 area jump、bbox clipping、dropout seed 边界以及 D4/D5/version/reserve 回退均进入模块测试。该项关闭“D7 缺少分层诊断/预筛 API”的缺口，但不关闭真实 M5N2 AirSim physical closure，也不实现 impact-time consensus 或协同避碰控制律。

迁移前真实 AirSim 2v2 candidate 在 10 seeds、20 pairs 中达到 `20/20` 的 5 米离线评分成功；旧基线为 `19/20`。当时只证明 truth identity online use 为 0，没有独立审计 truth-state control provenance，因此该结果只保留为接口非退化基线。自然运行中的 soft prediction 和 trend coast 均未触发，不能把 20/20 归因于增强算法。锁定后两帧 dropout 的状态机路径可作为有界预测功能证据，但其物理结果仍需 truth-isolated 同 seed 复跑。

早期 3-seed、8s 短窗口结果已被上述 40-episode 最终批次覆盖，不再作为当前缺口依据。本轮 D7-owned 本地 1-5 帧 dropout helper/测试、TTC 多 seed 拒绝汇总和 trend 晋级判据已经闭合；当前开放 P1 是第二 primary、同配置 multi-seed/dropout/candidate、loop latency 以及 pair funnel/closing speed/三维几何与平台机动标定，不是继续补 DTO/topology 或 canonical 聚合，也不修改默认 PN/PNG 公式。

P2/P3 状态保持原规划：可扩展质点运行时使用已测试的三维位置-速度 PN 基线；参考
3D PN、True PN、APN、FRPN 仍在隔离 benchmark，PX4/MPC/ROS2 等不提前晋级默认
AirSim 或实机 runtime。

### 历史实施记录

2026-07-11 D7 fallback commit gate 实现：`D4GuidancePermission`、coercion、`TerminalPngContractDecision` 和 runtime output 已增加 commit state、epoch、lease、required/acked member、plan/coalition version 与 gate 结果字段。中心失效/fallback 的显式 k>1 联盟仅在 `committed|executing`、lease 有效、epoch/version 一致、当前资源 required+acked 且 required 集合全部 ACK 后继续；默认 coalition scope 随后仍执行 D5 coalition visual completion，显式 per-primary scope 只免除共同完成/到达要求。standby reserve、D4 pending、reconfiguring/aborted、缺 ACK、旧 epoch、过期 lease 和版本冲突均明确阻断。中心正常及 k=1 原行为保持回归。D7 未修改 `png_guidance_delivery` 核心公式，也未改 main/D4。

2026-07-11 D7 P2 optional benchmark 实现：新增独立 `optional_p2_benchmark.py` 和 CLI，支持固定 seed 3D PN、True PN、APN、`frpn_research_approximation` 的恒速三维质点与序列化 replay 对照，逐条输出命中、最小脱靶量、控制努力/能量、峰值加速度和 Python 计算耗时。FRPN 明确标记为研究性鲁棒增益调度近似，不宣称标准模糊 FRPN。P2 law 未加入 runtime selector，结果标记不替换默认控制、不修改 delivery、不绕过 D3/D4/D5。完整 D7 回归更新为 `105 passed`。

2026-07-11 D7 N/M topology contract 实现：新增 `build_cooperative_guidance_topology()`、`validate_cooperative_guidance_topology()` 和结构化 topology/report DTO。M=5/N=2、T001 required=3、primary=2 时输出两个 active primary、一个 standby reserve；T002 required=1 输出 independent primary，剩余资源显式保留。专项测试还覆盖 7/3 非固定规模、资源不足和现有 terminal gate：两个 primary 可获得合同许可，未激活 reserve 即使有完整 D5 视觉证据仍拒绝为 `coalition_not_activated`。完整 D7 回归为 `109 passed`。D7 只展开 D3 已排序需求，不替代分配器或 main AirSim pair 创建。

2026-07-11 D7 terminal delivery API 实现：新增 `TerminalGuidanceDelivery`/`TerminalDeliveryConfig`/`TerminalDeliveryResult`，按 assignment pair 暴露 `acquiring/measured/image_kf_predict/blind_push/reacquired/expired`。默认参数与 delivery 已验证机制一致：`0.1s` control、`0.25s` 图像角度/角速度 KF predict、连续丢失 3 帧、`0.10s` 命令平均、`0.25s` blind push、`tau=0.18s`。`D7RuntimeBus` 已消费该 API 并输出状态、原因、预测年龄、丢帧、blind decay 与命令样本字段；stale D3 version、D4 block、D5 binding/friend conflict/execution safety gate 均先于外推 fail closed 并清空 pair 状态。完整 D7 回归为 `117 passed`；未修改位置 PN、TTC PNG、VM PNG 核心公式，P2 law 仍仅离线 optional benchmark。

D7 当前已经实现可测试的二维位置 PN/PNG 几何核、中段雷达/全局航迹 PN、可扩展
质点世界的六维 NED 三维位置-速度 PN、离线 `radar_midcourse -> vision_terminal`
质点仿真、AirSim phase-1 dry-run 记录适配、末端视觉 `png_vm/png_ttc` 轻量 gate、
每个 assignment pair 独立视觉导引状态和生命周期回收、D3/D4/D5 terminal contract、
显式 `handover_pending/hold/reacquire/abort_revoke` 日志状态，以及 SimpleFlight
速度命令抽象。

真实 AirSim SimpleFlight 控制不在 D7 模块内直接执行，而是 main/runtime 的 `intercept.py` 消费 D7 API：每个 `InterceptPair` 持有自己的 `AssignmentGuidanceBinding`、`D4GuidancePermission`、D5-shaped terminal association 和 `SimpleFlightPngGuidanceFilter`，将 `PngGuidanceCommand.velocity_ned` 交给 `command_velocity_z()`/`moveByVelocityZAsync`。因此 D7 文档必须把“D7 实现了可消费的导引/gate/命令抽象”和“main runtime 实际下发 SimpleFlight 命令”分开描述。

`png_guidance_delivery` 已纳入 D7 目录作为方案和复现实验包。主线实际使用 bbox-to-bearing、LOS-rate 窗口、bbox 面积 TTC、`png_vm/png_ttc` 增益思想、质量 gate、图像角度 KF、短时 command coast 和 SimpleFlight 速度命令。truth/gimbal/strapdown、PX4/MAVLink/body-rate、YOLO/ByteTrack 和报告仍是参考或独立实验路径；KF/外推只有 D7 轻量等价封装进入 runtime，不代表完整 delivery 控制栈接入。

2026-07-07 复核：main/runtime 已把真实 D7 控制执行产物合并进正式 `main_episode_bus_metrics.json`，并把执行前合同诊断保留为 raw `main_episode_bus_contract_metrics.json`。D3 `request_center_replan` 后的新中心 plan/binding/version 已接到 D7 current binding gate；D4 软风险和无冲突 D5 `reacquire/ambiguous` 不再被当作必然重规划/降级阻断。D7 本轮不需要修改 PN/PNG 控制律本体，只需保持 gate 和日志合同回归。

2026-07-08 D7 子智能体复核：D7-owned `runtime_bus.py`、`comparison.py`、`replay.py` 已补齐并由 D7 tests 覆盖。D7RuntimeBus 支持任意 N-pair state injection、每 pair 独立 filter、同一 pair plan/version/owner signature 变化时 reset；comparison 输出 PN/Pure Pursuit/`png_vm`/`png_ttc` 多 seed report rows；replay 将 YOLO/ByteTrack/AirSim bbox rows 离线映射到 D7 bbox/LOS/TTC gate，且显式不调用 SimpleFlight。D4 owner/version gate 已加强：D4 指定接管 owner 时，当前 D3 binding 必须携带同一 owner，旧 lock 或 owner mismatch/missing 均不得进入视觉 PNG；二级 plan 还必须有 D4 readiness/capability `takeover_ready`。main runtime 已把 D7 runtime summary 接入 episode bus；controlled 5v5 center replan 与 2v2 secondary visual PNG gate 回归已通过。

2026-07-08 P1 校准执行补齐：D7RuntimePairOutput 和 `summarize_runtime_bus_outputs()` 已补齐 main/D6 可消费字段。单样本记录包含 `terminal_handoff_state`、handover/terminal flags、D4/D5 state aliases、D3 plan/version、bbox、camera/LOS/maneuver gate、TTC、LOS-rate、closing speed 和 maneuver margin；summary 聚合 guidance mode、handoff 状态、D4/D5/plan 计数、contract/switch reject reasons、gate pass rate、bbox/TTC/LOS 数值摘要和 `visual_png_switch_count`。新增回归确保 D4 `request_center_replan`、`degrade_to_secondary`、`degrade_to_distributed` 时即使 bbox/D5 lock 良好也不调用视觉 PNG。

2026-07-08 P1 summary/replay 支持补齐：D7 新增 `calibration.py` 和 `summarize_guidance_calibration()`，可消费多 seed D7 runtime outputs、`GuidanceRecord`、comparison rows 或 replay dict，按 PN、Pure Pursuit、`png_vm`、`png_ttc` 汇总 terminal range、closing speed、bbox/LOS/maneuver gate 和 reject reasons。输出包含 `threshold_advisory.version="d7-p1-guidance-calibration-advisory-v1"`，覆盖 terminal range、min bbox area、max visual latency、min closing speed、min maneuver margin；所有字段均为 advisory，显式 `default_control_law_changed=False`、`d3_d4_d5_gate_bypassed=False`。3D/高度差/FRPN 仅作为 `benchmark_calibration` 字段，不替换默认 PN/PNG API。

2026-07-08 P1 main/D6 calibration sweep 对接：main runtime 已新增 P1 D4/D5 calibration sweep，支持 secondary height/FOV/count/standoff 与多 seed 组合；sweep 完成后 D6 自动生成标准报告 bundle，包括 records CSV、summary CSV、summary JSON 和 Markdown。该能力属于 main/D6 编排与报告写盘，不再作为 D7 未完成接口项。D7 保持 runtime summary、comparison rows、bbox/LOS replay summary 和 `summarize_guidance_calibration()` 字段稳定，供真实 AirSim 多 seed PN/Pure Pursuit/PNG 对照、visual gate/range/closing speed 标定和 D4/D5/D3 gate 回归消费。

2026-07-08 D7 actor asset 复核：D7 `png_guidance_delivery` truth/gimbal/strapdown example 的 `--intruder-actor-asset` 默认值已从历史 cube `1M_Cube_Chamfer` 对齐为 Blocks/AirSim 无人机 mesh asset `Quadrotor1`，并新增测试锁定默认值。main runtime 的 actor asset CLI/default 已由 main 同步为 `Quadrotor1`；cube 仅作为旧接口、旧报告或几何 baseline 显式复现选项。后续重点是真实 AirSim 验证和阈值/检测调参。

2026-07-08 D4/D5 机动高空侦察 stress 复核：main 侧 5v5 D4/D5 stress 覆盖 3 seeds、200m 高差、`mobile_recon_gimbal`、80deg FOV、1920x1080；D4 action 正确，D5 能识别 mobile recon，gimbal OK rate 为 1.0。但二级网络同帧全覆盖仍为 0.0，降级 case cross-view 为 0，`not_registered` 约 65。D7 结论不变：移动侦察节点“看得更清楚”不等于可放行视觉 PNG；D7 仍必须坚持 D3 当前 version/owner、D4 action 允许、二级 readiness/capability 为 `takeover_ready`、D5 `locked` 且 `assigned_global_track_id` 一致、bbox/LOS/闭合速度/距离/机动能力 gate 全部通过。D4 `request_center_replan`、`degrade_to_secondary`、`degrade_to_distributed` 阶段若 plan owner/version 未进入可执行状态，或 D5 未 `locked`、`assigned_global_track_id` 与 binding 不一致，继续阻断视觉 PNG。当前无运行级 P0 blocker。

2026-07-08 EVAL 曾把 3D geometry、True PN/APN/ADRC 对照列入 P0/P1 能力增强边界；该历史分类已被当前状态取代。当前 P1 只保留第二 primary、同配置 multi-seed/dropout/candidate、loop latency 以及 pair funnel/closing speed/三维几何与平台机动标定；3D PN、True PN、APN、FRPN 在线化后置，隔离式离线对照保持 P2。默认 PN/PNG 不被替换，不绕过 D3/D4/D5 gate。

2026-07-09 D7 P0-B/P0-C 修复：D7-owned `vision_png.py` 已补 raw/filtered LOS-rate、低通、限幅和 outlier reject evidence；`runtime_bus.py` 已补每 pair terminal latch，显式记录 dwell/release/reacquire grace，并在 D5 non-locked/reacquire 等 contract reject 后重置视觉 filter、要求后续重新稳定，不把 D5 non-locked 转成可用视觉命令；`pn.py` 已补 `compute_three_dimensional_pn_benchmark()`，runtime bus 可输出 3D geometry PN benchmark/log 字段。默认二维 PN/PNG 控制律未改变，D3/D4/D5 gate 未绕过，D4 `request_center_replan`/`degrade_to_secondary`/`degrade_to_distributed` 仍阻断视觉 PNG。

2026-07-09 D7 P1 switch/gate calibration 输出补齐：D7-owned `terminal_gate.py`、`runtime_bus.py`、`comparison.py`、`replay.py` 和 `calibration.py` 已补齐 main/D6 直接消费字段。单样本记录和 runtime summary 现在包含 `terminal_range_m`、`closing_speed_mps`、bbox/LOS/maneuver gate、`d4_action_block_reason`、`secondary_capability_class`/`secondary_readiness_class`、D5 lock consistency、D3 owner/version consistency、D5 `detect_registration_outcome`/reject reasons、measurement age、projection/covariance trace、YOLO/MOT metadata 和 `threshold_advisory_version`。D4 `request_center_replan`、`degrade_to_secondary`、`degrade_to_distributed` 继续阻断视觉 PNG；二级 plan 若 D4 readiness/capability 非 `takeover_ready`，D7 拒绝为 `secondary_capability_not_takeover_ready`，只解释阻断，不绕过 D3/D4/D5 gate。comparison rows 已覆盖 PN/Pure Pursuit/`png_vm`/`png_ttc` 多 seed 字段，calibration summary 按 guidance law 聚合上述 switch/gate 字段。默认 PN/PNG 控制律未改变，未引入 FRPN/APN/OGL/MPC 主线。

历史基线（2026-07-10 真实 AirSim 2v2 单 seed）只读复核：`p1_gap_closure_2v2_smoke_20260710/episode_006_full_flow` 的 `intercept_summary.json` 记录 2/2 `collision_intercept`，assigned actor/object name 匹配，时间为 3.4s/3.5s。71 行 `control_commands.csv` 中 `guidance_law` 为 `radar_pn=49`、`png_vm=21`、`los=1`，但 `vision_terminal=4` 且仅 INT-01 进入；raw `terminal_switch_allowed=True` 为 2/71，camera/LOS/maneuver gate pass rate 分别为 0.2254/0.2394/0.0563。主要合同拒绝为 `d5_not_locked=30`、`d4_reassign_pending=18`，主要视觉拒绝为 `maneuver_margin_low=13`、`bbox_near_image_edge=7`、`los_rate_window_too_short=2`。该结果只证明当时单次控制链路可完成 assigned-target 碰撞拦截，不能代表当前 M=5/N=2 物理结果。D6 aggregate 的 `visual_png_switch_count=3` 与 raw CSV allowed row count=2 属不同口径，后续必须区分 row pass、mode transition 和 aggregate switch event。

历史基线（2026-07-10 真实 AirSim 2v2 10-seed）复核：`p1_gap_closure_2v2_multiseed_20260710` 覆盖 seeds 1-10 和 20 pairs，得到 18 次 assigned-target `collision_intercept` 与 2 次 `terminal_detection_timeout`，后两次均为 INT-02（seed 3/10）。全 pair 平均 `min_range_m=2.113m`，成功 pair 平均拦截时间 3.589s。884 行控制记录和 execution metrics 汇总为 `radar_pn=530`、`png_vm=289`、`los=65`、`visual_png_switch_count=88`，跨 seed `terminal_switch_allowed_rate` 均值 0.0822。该批次仅作 2v2 历史基线，不能替代 2026-07-13 的 40-episode M5N2 最终证据；PN/Pure Pursuit/`png_vm`/`png_ttc` 长时多 seed 对照、timeout 根因和阈值 advisory 仍为 P1。

历史基线（2026-07-11 真实 AirSim 四律 smoke）复核：`p1_guidance_four_law_smoke_20260711` 在固定 2v2、seed 7、同几何、reset 分隔条件下完成 Pure Pursuit、Radar PN、PNG-VM、PNG-TTC 各 2 s 的真实 SimpleFlight 执行。四律均 timeout。该证据只证明 selector 和 D3/D4/D5 gate 当时进入 SimpleFlight，不关闭“较长时长、多 seed 受控对照”。D6 产物中的 21 条是指标配对行，不是 21 个独立 seed；不得用该 smoke 推导命中率或导引律优劣。

本次文档状态复核确认：README/PLAN/review 中早期“离线研究模块”和“2v2 actor baseline”口径已调整为“离线研究核 + D7-owned runtime bus + main/runtime AirSim consumer”的三层描述。D7 已完成的 runtime bus、terminal contract gate、owner/version gate、D4 gate blocking、D5 locked/ID/version gate、replay/comparison/calibration summary 状态保持不变；新增 P0/P1 只作为 EVAL backlog 同步，不把已实现 gate/API 倒退为未实现。

## 已实现

| 项 | 实现状态 | 关键证据 | 当前口径 |
|---|---|---|---|
| 中段雷达 PN/PNG | 已实现 | `d7_proportional_guidance/pn.py`; `simulator.py`; `airsim_dry_run.py`; `tests/test_proportional_guidance.py` | `compute_proportional_navigation_command()` 用二维相对位置/速度计算 `N * V_c * lambda_dot`，记录 range、LOS、LOS-rate、closing speed、限幅加速度和限幅转向率。 |
| 中段 PN 越目标重捕 selector | 已实现，待真实多 seed 标定 | `midcourse_reacquisition.py`; `tests/test_midcourse_reacquisition.py` | M5N2 seed1 的 INT-01/INT-04 在最近距离后发散到 143.64m/151.04m。每 pair selector 连续不闭合或 range 从最近点回升时选择 bounded Pure Pursuit，连续恢复正 closing 后回 PN；metadata 记录 selection/reason/streak。未修改核心公式。 |
| 位置比例导引融合 | 已实现主线等价核 | `pn.py`; `airsim_runtime/intercept.py` 读取该 API | delivery 的 truth PNG 不被主线直接调用；主线用 D7 PN 几何和 actor/global-track 等价估计实现位置 PN/PNG。 |
| 末端视觉 PNG gate | 已实现轻量主线核 | `vision_png.py`; D7 tests | `SimpleFlightPngGuidanceFilter` 从 bbox 中心生成 bearing/LOS-rate，支持 `los`、`png_vm`、`png_ttc`，输出 raw/filtered LOS-rate、限幅/outlier evidence 和 `PngGuidanceCommand.velocity_ned`。 |
| TTC 捷联比例导引融合 | 已实现 delivery 等价预处理，非默认 runtime | `vision_png.py`; `tests/test_png_delivery_enhancements.py` | `png_ttc` 增加面积 EMA=.25、window=5、min area=16px2、jump ratio=2.5、裁剪拒绝和 max TTC=20s；`png_vm` 不受 TTC 有效性 gate 影响。 |
| 每个 assignment pair 独立导引状态 | 已实现 | `terminal_delivery.py`; `test_runtime_keeps_terminal_delivery_state_independent_per_assignment_pair`; 既有 1/3/5/7 pair tests | 每 pair 独立保存 image KF、loss count、command window、blind push、LOS/TTC filter 和 latch；binding signature/请求律/reset_pair 变化时只重置对应 pair。 |
| 末端短时 KF/coast delivery API | 已实现 | `terminal_delivery.py`; `test_terminal_delivery.py` | 状态覆盖 acquiring/measured/image_kf_predict/blind_push/reacquired/expired；第一次无锁不伪造视觉 lock，同 global track 才标记 reacquired，到期为 `terminal_visual_lost_after_coast`。 |
| SimpleFlight 控制命令抽象 | 已实现并被 runtime 消费 | `vision_png.py`; `airsim_runtime/intercept.py`; runtime tests | D7 输出 `velocity_ned`；runtime 下发 `moveByVelocityZAsync` 并记录 `control_commands.csv`。D7 模块本身不连接 AirSim。 |
| D3/D4/D5 terminal gate | 已实现 D7 API | `terminal_gate.py`; `test_runtime_contract_failure_immediately_clears_pair_coast` | 校验授权/current/expiry、plan/version、D4 action、D5 locked、friend conflict、execution/safety gate、D5 ID/version 和观测 global ID；任一失败不继续 KF/coast。 |
| D4 主动降级保守阻断 | 已实现 | `BLOCKING_D4_ACTION_REASONS`; D7 active-secondary 测试 | `request_center_replan`、`degrade_to_secondary`、`degrade_to_distributed`、`reassign` 均拒绝视觉 PNG，reject reason 为 `d4_reassign_pending`，日志模式映射 `abort_revoke`。 |
| D4 assist/owner/version/secondary readiness gate | 已实现 | `terminal_gate.py`; `test_secondary_assist_target_is_cue_not_assignment_owner`; `test_terminal_contract_blocks_d4_reassign_until_new_owner_version_and_d5_lock`; `test_runtime_bus_blocks_secondary_plan_until_takeover_ready_and_reports_reason` | `request_secondary_assist` 的 target 只作 cue provider，不触发 owner/readiness 拒绝；非 assist owner 指令仍必须与 D3 binding 一致。真正二级 plan 由显式 owner-role 元数据识别，并要求 `takeover_ready`；旧 D5 lock 不能跨 plan 复用。 |
| D5 locked 与 ID/version 一致才切换 | 已实现 | `evaluate_terminal_png_contract()`; D7 tests | 只有 locked、无 friend conflict、execution/safety gate 未显式失败、global ID/version 一致时才允许后续 measured/predicted visual gate。 |
| 30m/稳定 bbox 等切换策略 | 已实现为可配置 gate，不是硬编码 | `PngGuidanceConfig`; D7 tests; `BlocksSmokeConfig` | D7 离线默认 terminal range `250m`，AirSim runtime 默认 `8m`；测试中 `30m` 左右相对距离用于验证 gate。bbox 稳定默认 `min_stable_frames=2`，还需面积、置信度、边缘、延迟、LOS 方差、闭合速度和机动裕度通过。 |
| D7-owned N-pair runtime bus adapter | 已实现 | `runtime_bus.py`; `test_runtime_bus_injects_n_pairs_with_independent_filters_and_summary`; `test_runtime_bus_blocks_visual_png_for_d4_reassign_actions_even_with_good_bbox`; `test_runtime_bus_reports_d5_registration_projection_and_yolo_mot_metadata` | 调用方注入每个 pair 的 D3/D4/D5/observation 状态；D7 输出 terminal handoff、D4/D5/plan/version、terminal range、closing speed、D4 block reason、D5 lock/D3 owner-version consistency、secondary readiness、D5 registration/projection/covariance/Yolo-MOT、bbox/LOS/TTC、gate pass 和 guidance summary 字段，不创建 assignment、不控制车辆、不假设 2v2/5v5。 |
| 可扩展三维导引与 pair 生命周期 | 已实现并测试 | `scalable_3d_guidance.py`; `pair_lifecycle_benchmark.py`; `test_scalable_3d_guidance.py`; `test_scalable_3d_pair_lifecycle.py` | 六维 NED 目标/资源状态经当前 D3/D4/D5 合同输出三维加速度；状态按资源-全局航迹 pair 隔离，计划升级重置，改绑/丢失/撤销/过期/旧计划/批次缺失回收。200 pair 冻结输入最终状态 170、峰值 200，旧计划接受和身份改写为 0。该状态不等于 AirSim/实机三维姿态推力闭环。 |
| 四导引律 runtime selector 与审计字段 | 已实现并进入历史 SimpleFlight smoke | `selector.py`; `runtime_bus.py`; `comparison.py`; D7 selector/gate tests; `p1_guidance_four_law_smoke_20260711` | main 可按 pair 请求 `pure_pursuit|radar_pn|png_vm|png_ttc`；混合模式仅在 D3/D4/D5 + 视觉 gate 通过后由 radar PN 切换。历史单 seed、2 s smoke 只证明合同接线，不证明命中率或四律优劣。pending、过期 lease、旧 owner/version、D5 非 locked 或 ID 不一致均保持视觉阻断。未修改 delivery 核心公式。 |
| P0-B terminal latch / reacquire grace | 已实现 | `runtime_bus.py`; `test_runtime_bus_applies_reacquire_grace_after_d5_locked_jitter` | contract 通过后才评估视觉 PNG；D5 non-locked/reacquire 等 contract reject 不发布视觉命令，并触发 filter reset 与后续 reacquire grace；日志字段包含 `terminal_dwell_active`、`terminal_release_grace_active`、`terminal_reacquire_grace_active` 和对应 reject reason。 |
| P0-B bounded detect-loss coast contract | 已实现 | `terminal_gate.py`; `terminal_delivery.py`; `runtime_bus.py`; `test_runtime_allows_bounded_coast_for_consistent_d5_reacquire_only` | fresh switch 仍要求 D5 locked；既有 measured lock 后的 D5 `reacquire` 空观测，仅在 D3/D4、身份/版本、friend conflict 与 safety 字段均一致时允许 bounded KF/coast。D4 硬阻断立即清空。 |
| delivery 生命周期与创新审计 | 已实现，默认保守 | `terminal_delivery.py`; `runtime_bus.py`; `tests/test_png_delivery_enhancements.py` | resource/global/local track、owner/version 变化重置历史；输出 measured/predicted/innovation_rejected/reset/expired。soft reject prediction 与水平 trend coast 默认关闭，friend/duplicate conflict 和旧版本继续 fail-closed。 |
| 6D LOS KF replay | 已实现 optional backend | `los_replay.py`; `tests/test_png_delivery_enhancements.py` | 优先消费 D5 组合后的 `camera_to_ned_rotation`，否则使用 split rotations；两者都保留曝光/姿态时间同步检查。在线 EMA/滑窗默认不变，该项不解决 M5N2 coalition closure。 |
| P1 maneuver-margin diagnostics | 已校正 | `vision_png.py`; `test_maneuver_margin_uses_unclipped_required_turn_rate` | `required_turn_rate_radps` 改为未限幅需求并新增 `turn_rate_capacity_radps`；超能力需求产生负 margin，不修改 PN/VM/TTC 核心公式。 |
| P0-B filtered LOS-rate / spike evidence | 已实现 | `vision_png.py`; `test_visual_png_filters_los_rate_spike_before_near_range_command` | 视觉 PNG 使用 filtered LOS-rate 计算命令；输出 `raw_los_rate_radps`、`filtered_los_rate_radps`、`los_rate_clamped`、`los_rate_outlier_rejected`，尖峰可拒绝为 `los_rate_spike_rejected`。 |
| P2 isolated 3D geometry PN benchmark/log | 已实现为 benchmark/advisory | `pn.py`; `runtime_bus.py`; `test_3d_pn_benchmark_logs_advisory_fields_without_replacing_default_png` | `compute_three_dimensional_pn_benchmark()` 和 runtime bus 输出 `height_delta_m`、`range_3d_m`、`pn3d_los_rate_norm_radps`、`pn3d_commanded_accel_norm_mps2`；显式 `benchmark_only`，不替换默认二维 PN/PNG API。 |
| PN/Pure Pursuit/PNG 对照 report rows | 已实现 D7 接口 | `comparison.py`; `test_guidance_strategy_comparison_reports_all_p1_fields` | 输出 PN、Pure Pursuit、`png_vm`、`png_ttc` 多 seed rows，字段含 `min_range_m`、`terminal_range_m`、`closing_speed_mps`、标准化 runtime law、mode/law transition、raw gate、terminal timeout、command saturation、D4/D5/D3 consistency 和 reject reasons；D6/main 后续负责真实同 seed 报告。 |
| YOLO/ByteTrack bbox/LOS 离线 replay adapter | 已实现 D7 接口 | `replay.py`; `test_bbox_los_replay_normalizes_yolo_bytetrack_and_stays_offline` | bbox replay rows 归一成 `VisionGuidanceObservation`，保留 registration outcome、measurement age、projection 和 tracker metadata，离线评估 D3/D4/D5 contract 与 bbox/LOS/TTC gate；summary 显式 `vehicle_control=False`、`simpleflight_control_called=False`。 |
| 多 seed calibration summary/advisory | 已实现 D7 接口 | `calibration.py`; `test_guidance_calibration_summary_groups_multiseed_runtime_records_and_advisory` | 汇总 runtime outputs、`GuidanceRecord`、comparison rows 或 replay dict，按 PN/Pure Pursuit/`png_vm`/`png_ttc` 输出 terminal range、closing speed、bbox/LOS/maneuver gate、D4 block、D5 lock/D3 owner-version consistency、secondary readiness、D5 registration/projection/covariance/Yolo-MOT 和 reject reasons；阈值建议只作为 advisory，不改默认控制律。 |
| AirSim active center/secondary 合同回归 | 已通过当前 P1 回归 | `airsim_runtime/tests/test_blocks_runtime.py`; runtime CSV/summary 字段 | controlled 5v5 center replan 验证新 plan/binding/version 后 D7 才接受视觉 PNG；2v2 secondary visual PNG gate 验证 `degrade_to_secondary` 阶段阻断旧锁定，二级 owner/version 生效、D4 readiness/capability 为 `takeover_ready` 且 D5 locked 后才允许 `png_vm`。 |
| episode bus 真实执行指标回灌 | 已接线，保持回归 | `main_episode_bus_metrics.json`; `control_commands.csv`; `intercept_summary.json` | D7 runtime summary 已接入 episode bus；正式 metrics 可包含 D7 真实执行后的 `intercept_success_count`、`collision_intercept_count`、`guidance_law_counts` 等；raw contract metrics 仅作执行前诊断。 |
| D3 replan 后 current binding gate | 已接线并通过 controlled 5v5 回归 | `terminal_gate.py`; runtime summary/version metadata | D4 真正请求中心重规划后，D7 只接受新的当前 D3 binding/version；旧 plan、stale binding、revoked assignment 和 plan mismatch 均阻断视觉 PNG。 |
| D4 软风险 continue_center 路径 | 已接线，保持回归 | `D4GuidancePermission(action="continue_center")`; D7 tests | 低 cost margin、短时低置信度、无冲突 `ambiguous/reacquire` 由 D4 观察时，D7 不误映射为 `d4_reassign_pending`；后续仍需 D5 `locked` 和视觉 gate 通过。 |
| Pure Pursuit baseline | 已实现轻量版 | `compute_pure_pursuit_command()`; tests | 用于离线对照，并由中段重捕 selector 以有界转率临时调用；不引入 PythonRobotics。 |

## EVAL P0/P1 同步状态

| EVAL 条目 | 当前项目状态 | D7 GAP 同步口径 | 优先级 |
|---|---|---|---|
| 末端切换迟滞 | 已补 terminal latch：dwell/release/reacquire grace 字段和 reject reason 可被 runtime/D6 消费；D5 non-locked/reacquire 不会绕过 contract 发布视觉命令。 | 保持 D3/D4/D5 gate，不让 D7 分配、授权或改写 `global_track_id`；真实 AirSim 多 seed 中继续观察 switch count。 | P0-B done / P1 runtime validation |
| LOS 角速率滤波 | 已补 raw/filtered LOS-rate、低通、限幅和 outlier reject evidence；近距视觉 PNG 尖峰由 D7 测试覆盖。 | 不引入复杂控制器；后续用真实 bbox replay/AirSim 数据校准 `max_los_rate_*` 阈值。 | P0-B done / P1 calibration |
| 三维 PN 执行基线与几何对照 | 可扩展质点运行时已有六维 NED 三维位置-速度 PN 和世界加速度回写；`compute_three_dimensional_pn_benchmark()` 继续提供隔离对照字段。 | 质点基线保持当前合同；AirSim/SimpleFlight 的姿态、推力、高度和平台响应仍按 P1 标定，参考算法不替换默认 API。 | scalable baseline done / P1 platform calibration |
| 3D PN/True PN/APN/FRPN 对照 | 隔离式离线质点 benchmark 已实现，replay 只保留为可选输入接口；FRPN 是研究近似。 | 只作为 P2 benchmark/advisory 比较 miss distance、控制努力、峰值加速度和耗时；不进入默认主线，不替换 PN/PNG。 | P2 optional benchmark |
| PN/Pure Pursuit/PNG 多 seed 对照 | D7 已完成四律 selector、comparison rows、迁移/raw gate/timeout/saturation 字段和 calibration helper；main 已有历史 `png_vm` 2v2 10-seed 基线和四律单-seed 2 s smoke。 | 历史短时 smoke 只证明 selector 和 D3/D4/D5 gate 进入 SimpleFlight；仍需在当前 topology、相同 seed/几何/阈值下运行较长时长、多 seed 四律对照，D7 保持字段稳定且不允许对照路径绕过 gate。 | P1 main/D6 integration |
| 预测拦截点 | 当前主要基于 PN 视线率，D7 comparison/calibration 可输出对照字段但未形成默认 intercept-point guidance。 | 输出 predicted intercept point 并与 PN 对比；只作为 P1 对照能力。 | P1 |
| 动力学补偿 | SimpleFlight 高层速度接口已可执行，D7 已记录 turn/maneuver margin；真实执行延迟、加速度限制和饱和响应仍需标定。 | 将命令饱和、响应延迟和加速度限制进入 guidance log/report；不直接升级为 PX4/body-rate 默认主线。 | P1 |

## 部分实现

| 项 | 当前做到什么 | 还缺什么 | 原因 | 优先级 |
|---|---|---|---|---|
| 真实 AirSim 多 seed calibration | 2v2 candidate 已完成 10 seeds、`20/20` 非退化验收；M5N2 已完成 40 个真实 SimpleFlight episode，最佳 profile coalition `5/10`、overall `8/40`。 | 校准第二 primary 的视觉 acquisition/locked/gate，并按 terminal range、closing speed、bbox/LOS、二维/三维 geometry 和 maneuver margin 分层统计。 | 合同和安全门控已保持，但性能未达到 `8/10`；D7 不生成 assignment、D4 仲裁或 D5 lock。 | P1 performance calibration |
| 相机前移 0.5m / FOV / 姿态朝向目标 | AirSim settings/tests 已覆盖 tuned terminal camera `X=0.5m`、`640x480`/`120deg` FOV；runtime 支持 `look_at_target` yaw 和 CV camera follow/look-at。 | D7 主线没有直接读取真实 camera intrinsics/extrinsics、畸变、姿态估计，也没有把 FOV 从 runtime 自动传入 `PngGuidanceConfig`。 | D7 当前保持轻量 bbox 几何；相机管理属于 main/runtime。 | P1/P2 |
| 末端视觉 PNG 与检测闭环 | AirSim detect metadata bbox 可进入 D7 gate；D5-shaped lock 通过后 runtime 可进入 `png_vm`；D7 已提供 bbox/LOS 离线 replay adapter；D7 delivery actor 默认外观和 main runtime actor asset default 均已对齐到无人机 mesh asset `Quadrotor1`。 | D5 原生 ByteTrack/BoT-SORT admission 未通过，默认继续使用 AirSim detect；YOLO/MOT 只产出 optional replay 与 D5 local-track/D7 bbox-LOS gate 摘要，不进入默认 SimpleFlight 控制。 | 原生 MOT 的 precision/recall 和远距检测未达准入要求；先用 detect 完成第二 primary 与 gate 标定。 | P1 detect calibration / optional MOT |
| TTC 面积通道 | `png_ttc` 已实现面积 EMA=.25、5 帧斜率、16px2 最小面积、2.5 跳变比、裁剪拒绝和 20s 最大 TTC；2026-07-14 actual-v2 2v2 seed-1 pair 物理成功 `2/2`。 | 扩展真实 `png_ttc` 多 seed，统计 jump/clipping/non-expanding/out-of-range 拒绝及物理结果。 | seed-1 actual-execution 关闭 P0 接线，不关闭专项拒绝覆盖和统计标定 P1。 | P1 calibration |
| truth-isolated 真实执行证据 | main/runtime 代码和 `130 passed` mock 回归关闭状态真值代码 P0；2026-07-14 actual-v2 两个 seed-1 case 均 available，identity/state online use 均为 0。 | 扩展同配置多 seed，并保持逐 episode 双 truth-use 计数和 canonical artifact 校验。 | canonical P0 证据链已关闭；历史 physical 不追溯升级，统计性能仍为 P1。 | P0 done / P1 multi-seed |
| soft prediction / trend coast | 两者实现完成但库默认关闭；本地 1-5 帧矩阵已验证统一 `0.25s` 硬上限，trend helper 固化 paired seed、实际触发、错误绑定、命令跳变和物理成功判据。 | 在 truth-isolated 真实 AirSim 中受控触发 dropout/trend 并把 execution rows 输入 helper。 | optional candidate 不能因代码存在或迁移前 2v2 非退化结果自动晋级。 | P1 optional validation |
| 机动能力 gate | PN 有加速度/转向率限幅；视觉 gate 估计 required turn rate、turn capacity、maneuver margin；可扩展质点基线可记录三维加速度饱和。 | 真实动力学、姿态/推力/延迟、PX4 饱和响应和 AirSim 三维高度通道未标定；200m 高差 mobile recon stress 只能证明观测可见性改善，不能替代平台机动验证。 | P1 标定平台 gate；True PN、APN、FRPN 仅进入 P2 optional benchmark。 | P1 calibration / P2 benchmark |
| D6 指标输入 | D7/runtime 日志已有 `d7_terminal_semantics_v2`、`d7_guidance_law_semantics_v1` 与 `d7_pair_guidance_funnel_v2`；canonical actual 五层均已独立 `available`，合计 `102/26/26/2/4`。D7 新增 `PairStateLifecycleDiagnostics3D`。 | future multi-seed/dropout/candidate 继续使用同一 live state instance；main/D6 尚需把生命周期诊断写入正式 episode sidecar。pair funnel、first-failure、closing speed 和 3D maneuver 的缺失字段保持 evidence missing，不从五层指标反推。 | 正式五层聚合已闭合；D7 本地 `220 passed` 已关闭字段语义、被动诊断和状态生命周期接口，剩余是 P1 持久化、证据扩展和标定。 | P0 evidence done / P1 integration/calibration |

## 未实现

| 项 | 当前状态 | 未实现原因 | 缺少条件 | 优先级 |
|---|---|---|---|---|
| AirSim/实机三维平台闭环 | 可扩展质点运行时的六维 NED 状态、三维位置-速度 PN 和世界加速度回写已实现并测试；AirSim/SimpleFlight 默认链路仍是高层速度抽象，尚无姿态、推力和真实动力学闭环。 | 质点加速度命令不能替代多旋翼平台控制与饱和响应。 | 姿态/推力/高度通道、平台响应、控制时延、硬件约束和 D6 三维平台指标。 | P1 platform calibration / real control deferred |
| 在线 default True PN / APN / FRPN | 未实现为默认主线；隔离 P2 benchmark 已实现，其中 FRPN 是研究近似。 | 高机动算法公式、目标加速度估计和场景尚未冻结，FRPN 也不是规范实现。 | 保持 P2 与在线 runtime 隔离；不绕过 D3/D4/D5 gate，不替换默认 PN/PNG。 | P2 optional benchmark complete / online deferred |
| MPC / NMPC | 未实现。 | 当前 PN/PNG 足够支撑第一阶段闭环；MPC 需要强约束模型和求解器。 | 平台动力学、约束、求解器依赖、实时预算、失败回退。 | P3 |
| 硬件飞控 / 实机控制 | 未实现。 | 本仓库是研究/仿真路径，不能把 D7 输出当实机控制指令。 | 实机安全流程、kill switch、围栏、台架标定、人工接管。 | P3 |
| PX4/MAVLink/body-rate 默认主线 | delivery 中有脚本和报告，main D7 主线未接入。 | Offboard、解锁、推力和坐标系风险高，不适合默认路径。 | 继续后置，不属于本轮 P2 benchmark。 | deferred |
| YOLO/ByteTrack 控制闭环 | delivery 有 detector 和报告，D7 已提供 bbox/LOS 离线 replay adapter，但主线不直接控制。 | 默认 runtime 使用 `simGetDetections` metadata，不保存 PNG，不管理模型权重/GPU。 | 图像帧流、YOLO 权重、class id、依赖版本、GPU/CPU 预算、MOT 稳定性、D5 local track 事件流和 main/D6 replay 数据。 | P1 先 replay |
| OpenCV/KCF/solvePnP/完整标定 | D7 主线未依赖。 | 当前只需 bbox 到 LOS 的轻量几何。 | 相机内外参、畸变、重投影误差、图像流、性能预算。 | P2 |
| ViSP / ROS2 tf2 / message_filters | 未实现。 | 当前项目不是 ROS2 graph 或视觉伺服栈。 | ROS2 runtime、frame tree、带戳消息 schema、bag/replay 基准。 | P3 |

## 缺少条件

1. **真实 AirSim 多 seed calibration**：D7 已提供本地 `D7RuntimeBus` adapter、comparison rows、bbox/LOS replay adapter 和 `summarize_guidance_calibration()` advisory helper，main 已把 D7 runtime summary、delivery audit 和正确 M5N2 topology 接入 episode bus。40-episode 批次已完成但最佳 profile 只有 `5/10`；下一验收聚焦第二 primary 的 acquisition/gate、closing speed/range、三维几何和平台机动响应，不再重复 DTO/topology 接线。
2. **D5 状态事件流**：`locked/ambiguous/hold/reacquire`、锁定丢失、重捕获、friend conflict、duplicate lock 和 timeout 需要持续进入 D7 pair state machine 与 D6 指标。
3. **视觉 replay 条件**：D7 已提供 bbox rows 到 bbox/LOS gate 的离线接口；YOLO/ByteTrack 或真实图像链路只作为 replay/optional，需要图像或 bbox replay 数据源、camera intrinsics/extrinsics、bbox timestamp、local track 连续性、measurement age、LOS-rate 噪声、丢检策略和 D5 local track 事件流。
4. **飞控/动力学条件**：PX4/MAVLink 或真实飞控升级前必须有 Offboard 状态机、推力/坐标/限幅标定、饱和日志、安全边界和回归 baseline。
5. **对照实验条件**：P1 的 PN、Pure Pursuit、`png_vm`、`png_ttc` 物理闭环需要同批
   多 seed 场景、统一成功/失败判据、阈值版本和 D6 报告。可扩展质点运行时的三维
   位置-速度 PN 是已实现基线；`optional_p2_benchmark.py` 中的参考 3D PN、True PN、
   APN、FRPN 仍是隔离 P2 对照，不能与在线 P1 或平台验收混写。默认 PN/PNG API
   不替换，D3/D4/D5 gate 不绕过。

## 下一步优先级

| 优先级 | 下一步 | 验收口径 |
|---|---|---|
| P0-B done | 工程化闭环稳定性：末端视觉 PNG 切换迟滞和 LOS 角速率滤波已在 D7-owned runtime bus/filter 中补齐；继续保持 D7 不分配、不授权、不改写 `global_track_id`。 | D7 tests 通过；D4 `request_center_replan`/`degrade_to_secondary`/`degrade_to_distributed`、D5 non-locked、D5 `assigned_global_track_id` 与 binding 不一致、ID/version mismatch、friend conflict 均拒绝视觉 PNG；输出 filtered LOS rate，近距命令尖峰被限幅/拒绝。 |
| P1 done/保持 | D7RuntimeBus、comparison、replay、calibration summary/advisory、D4 gate blocking、D4 secondary readiness block、D3/D4/D5 terminal contract gate、owner/version gate、D5 registration/projection/Yolo-MOT reporting、episode bus runtime summary、handoff/guidance summary fields、controlled 5v5 center replan 和 2v2 secondary visual PNG gate。 | D7 tests 通过；main CSV/summary 持续写出 `plan_id/plan_version/owner_node_id/track_version/d4_action/d4_action_block_reason/d5_decision_state/terminal_contract_reject_reason/terminal_range_m/closing_speed_mps`；D7 summary 保留 `guidance_mode_counts`、`terminal_handoff_state_counts`、gate pass rate、bbox/TTC/LOS 摘要、D5 lock/D3 owner-version consistency、secondary readiness、registration/projection 摘要和 `visual_png_switch_count`；D7 calibration summary 保留 threshold advisory 和 benchmark-only 3D/FRPN 字段；D4 replan/degrade 或 secondary 非 `takeover_ready` 阶段不调用旧锁定视觉 PNG。 |
| P1 M5N2 性能校准 | 40 个真实 SimpleFlight episode 已完成，保持 `2 primary + 1 standby reserve` 且不要求同时到达；最佳 profile `5/10`、overall `8/40`。 | 逐 seed 分层输出 target、active-primary、第二 primary acquisition/gate、closing speed/range、三维高度差、maneuver margin、coalition completion、D7 filter state 和 truth-use；安全三项继续保持 0。 |
| P1 dropout/TTC helper done | D7-owned 本地 1-5 帧矩阵和 TTC 四类拒绝多 seed 汇总已经实现；dropout 失败原因已分离 contract reset、prediction window 和 measured lock 未建立。 | 当前全量 `220 passed`；1-2 帧只在同 resource/global/local identity 和 current plan/owner/version 下有界预测，默认 10Hz 第 3-5 帧超过 0.25s 后 fail-closed；TTC helper 报告 jump/clipping/non-expanding/out-of-range。 |
| P1 trend candidate helper done | trend coast 保持默认关闭，paired 晋级 helper 已实现。 | 仅当 seeds 配对、candidate 实际触发、错误绑定为 0、命令跳变不恶化且物理成功不下降时，才输出晋级建议。 |
| P1 real execution open | `png_ttc` 已有 actual-v2 seed-1 `2/2`；真实 AirSim dropout/trend candidate 和 `png_ttc` 专项多 seed 仍待 main 编排。 | execution rows 必须输入上述 helper，并由 D6 形成正式多 seed 结论。 |
| P1 midcourse validation | 在 M5N2 多 seed 验证 PN -> bounded PP reacquisition -> PN 的重捕闭环。 | 按 pair 记录 selection/reason、负 closing entry、正 closing recovery、切换次数、重捕时间和发散后最终 min/final range；校准 enter/exit closing 与 2/3 帧迟滞。 |
| P1 | 预测拦截点、二维 gate 与动力学响应标定。 | 命令饱和、响应延迟和加速度限制进入在线 guidance log；不混入 P2 的 3D/True PN/APN/FRPN benchmark。 |
| P1 detect / optional MOT | 默认 AirSim detect 继续进入 D5/D7 gate；原生 ByteTrack/BoT-SORT 本轮未准入，只接入 optional replay。 | 优先用 detect 校准第二 primary；MOT 只有在后续 admission 指标达标后再评估，不进入默认 SimpleFlight 控制。 |
| P2 optional | 保持已完成的隔离式离线质点 3D PN、True PN、APN、FRPN benchmark；replay 只作为可选输入接口。 | 不修改位置 PN 或 `png_guidance_delivery` VM/TTC 核心公式，不进入默认 SimpleFlight runtime。 |
| P3 | 评估 MPC/NMPC、ViSP、ROS2。 | 仅在需要强约束控制或机器人中间件集成时进入，不作为当前 D7 主线阻塞项。 |

## 关键依据路径

- `research_modules/d7_proportional_guidance/d7_proportional_guidance/pn.py`
- `research_modules/d7_proportional_guidance/d7_proportional_guidance/midcourse_reacquisition.py`
- `research_modules/d7_proportional_guidance/d7_proportional_guidance/simulator.py`
- `research_modules/d7_proportional_guidance/d7_proportional_guidance/terminal_gate.py`
- `research_modules/d7_proportional_guidance/d7_proportional_guidance/vision_png.py`
- `research_modules/d7_proportional_guidance/d7_proportional_guidance/runtime_bus.py`
- `research_modules/d7_proportional_guidance/d7_proportional_guidance/replay.py`
- `research_modules/d7_proportional_guidance/d7_proportional_guidance/comparison.py`
- `research_modules/d7_proportional_guidance/d7_proportional_guidance/airsim_dry_run.py`
- `research_modules/d7_proportional_guidance/tests/test_proportional_guidance.py`
- `research_modules/d7_proportional_guidance/tests/test_airsim_phase1_dry_run.py`
- `research_modules/d7_proportional_guidance/README.md`
- `research_modules/d7_proportional_guidance/PLAN.md`
- `research_modules/d7_proportional_guidance/png_guidance_delivery/README.md`
- `research_modules/airsim_runtime/intercept.py`

## M 对 N 协同导引 P0/P1 复核（2026-07-11）

依据 `D7_M_TO_N_COOPERATIVE_GUIDANCE_REVIEW.md` 的 12 篇主要论文和 5 个开源候选审计，D7 已实现中心化 coalition 合同的成员级执行门控，但仍未实现 impact-time consensus、终端扇区协调或成员间避碰控制律。不得把版本/时间窗 gate 或多个独立 PN pair 称为完整协同导引。

- **P0：无新增 blocker。** N-pair PN/PNG、D3/D4/D5 gate、SimpleFlight 消费链和 k=1 合同保持回归；D7 继续不分配、不授权、不改写 `global_track_id`，也未修改 `png_guidance_delivery` 核心公式。
- **P1 done：中心化 coalition 与 per-primary 合同门控。** 默认 scope 要求本资源 D5 locked、版本一致及 coalition visual completion；显式 per-primary scope 只取消共同视觉完成/arrival window，其他安全门控不变。测试覆盖 T001 primary 独立切换、T002 k=1、D4 replan/pending/reconfiguring、standby reserve、ACK/lease、visual completion 和版本冲突。row/summary 明确保留 scope、bypass 诊断、`terminal_contract_allowed`、`visual_png_switch(_count)` 与拒绝原因。
- **后置研究，非当前 P1：协同控制律与同时到达。** 同步 ITCG、序贯/混合主备对照、terminal sector/impact angle、成员最小间距、通信时延与失效敏感性分析均暂缓。现阶段只保持既有 per-primary 独立执行、联盟合同和安全审计；D7 不拥有联盟形成、成员选择、波次授权或原子联盟重构。
- **后置研究，非当前 P1：协同开源基准。** 未发现同时具备协同到达、多旋翼模型、避碰、清晰许可证和自动测试的成熟库。许可证明确的 MATLAB 候选仅支持单拦截器 ITCG，其余协同候选不可直接复制。

本轮 D7 P2 只保留 3D PN、True PN、APN、FRPN 的隔离式离线质点 benchmark；其他实机或全栈升级继续后置，不进入当前 P1/P2 执行序列。
