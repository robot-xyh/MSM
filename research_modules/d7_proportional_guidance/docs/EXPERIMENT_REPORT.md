# D7 末端切换诊断实验记录

## 2026-07-21 隔离双臂命令合同验证

本轮未启动 AirSim。验证对象为隔离质点 paired rollout 的 D7 命令血缘、arm 状态
隔离和写回确认语义。样本为 9 个无随机 seed 的确定性测试，D7 全量
`213 passed`，验收阈值为零失败。

| 场景 | 验收条件 | 结果 |
| --- | --- | --- |
| control/treatment 同 pair | LOS/TTC/模式状态分别保存，不跨臂累计 | 通过 |
| wrong arm/cross-arm receipt | 在 batch 或 validator 阶段拒绝 | 通过 |
| stale plan/hash tamper | 版本回退、载荷 hash 不符时不暴露 batch | 通过 |
| D4 不允许 | held，资源加速度为零 | 通过 |
| 显式 D5 terminal gate 未通过 | held，不能以中段回退掩盖末端门失败 | 通过 |
| resource-track binding 不一致 | held，`global_track_id` 不重绑 | 通过 |
| 200 pair 隔离 | 200 份状态与 binding hash 独立，命令均 finite | 通过 |
| generated/held/applied | 三态独立统计，held 不得生成写回凭据 | 通过 |
| truth/actor/object 在线字段 | context/binding lineage 拒绝 | 通过 |

测试还验证 application receipt 只能引用同 arm、同 episode、同 isolation world、同计划
hash、同 binding 和同加速度命令。所有 receipt 均为
`isolated_simulation_only=true/production_runtime_ack=false`。这些结果证明 D7 的
接口和 fail-closed 行为，不证明 main 已完成双世界多周期运行，也不提供
post-intervention physical outcome。位置 PN、视觉 PNG、LOS、TTC、coast 和
`png_guidance_delivery` 核心公式未修改。

## 2026-07-20 可扩展三维闭环确定性验收

本轮验证对象为新增 `scalable_3d_guidance.py`，未启动 AirSim。测试日期
2026-07-20；新增场景 14 个，均为确定性输入，其中质点闭环 fixture 无随机 seed；
D7 全量结果为 `204 passed`，验收阈值为零失败。

| 场景 | 样本/规模 | 验收条件 | 结果 |
| --- | ---: | --- | --- |
| 单 pair 重复执行 | 2 个独立 controller | 三维命令逐元素一致、finite、模不超过 16 m/s2 | 通过 |
| N pair 独立状态 | 7 pair / 9 资源槽 | 每 pair filter timestamp/mode 独立，空槽为零 | 通过 |
| 规模压力 | 200 pair | 输出形状 `(200,3)`，全部 finite，命令模不越限 | 通过 |
| 三维高度差 | 1 pair | NED 垂向 LOS 与加速度非零且方向正确 | 通过 |
| 实际 DTO | D2 `GlobalTrack3D` + D3 binding | 六维状态、6x6 协方差和版本直接可消费 | 通过 |
| 末端视觉 | 3 帧面积扩张 | D5 locked/双版本一致后 TTC 有效并进入 visual PNG | 通过 |
| D5 metadata 入口 | 3 帧 | 不提供额外 observation 参数也可形成同一视觉输入 | 通过 |
| 丢帧 | 3 个 reacquire tick | 前 2 帧为有界衰减 coast，第 3 帧超时回中段 | 通过 |
| D4/stale plan | 3 类 pending + 1 stale active version | 零命令 hold，fresh visual switch 为 false | 通过 |
| D5/camera/maneuver | non-locked、version mismatch、两类 capability false | 均不能进入视觉模式且 global id 不变 | 通过 |
| 5 米质点闭环 | 2 resources / 1 target / 1 deterministic fixture | 任一资源三维距离 `<=5m` 即通过，首达时另一资源 `>5m` | 通过 |

该结果证明：D7 可按资源索引为 main-owned 六维质点世界形成确定性有限三维命令，
assignment pair 的滤波、外推、TTC、coast 和模式不会共享，且成功判据不含同时到达。
它不证明 AirSim 多旋翼实际轨迹、相机识别率、控制时延、姿态/推力饱和、碰撞安全、
200 对实时速度或多 seed 成功率。剩余标定必须在 main/D6 的真实 episode 和离线 truth
scorer 中完成；D7 在线仍只能消费 D2 estimate，不能把 truth 反馈到控制。

借鉴 `png_guidance_delivery` 的内容限于 LOS 6D KF、bbox ScaleExpansionTTC、
strapdown camera-to-inertial/NED LOS、导航增益和向量/命令限幅、短时命令均值与指数
衰减 coast。交付目录、既有二维 PN/VM/TTC 公式及其历史实验结果均未修改。

## 2026-07-15 真实 AirSim M5N2 20-case 复核

### 实验范围

- 数据：`p1_terminal_timing_funnel_10seed_20260715_m5n2_baseline_seed001..010` 与 `...candidate_soft_prediction_trend_coast_seed001..010`。
- 场景：SimpleFlight M5N2；高威胁 T001 使用 2 个 active primary 和 1 个 standby reserve，T002 使用 1 个 active primary，每 case 有 3 个 active-primary opportunity。
- 成功标准：指定资源与指定目标在 NED 三维距离上不大于 5 米，只由运行后离线 truth scorer 判分。
- 执行边界：M5N2 `20/20` 后 TERM 生效前仅额外完成 `p1_terminal_timing_funnel_10seed_20260715_png_ttc_2v2_seed001`，不纳入本次 M5N2 统计，也不用于分析或晋级；其余 tuned case 和全部 dropout 未执行。本轮不修改 PN/PNG/LOS/外推公式。

### 物理和执行结果

| 指标 | baseline，10 seeds | candidate，10 seeds | 结论 |
| --- | ---: | ---: | --- |
| active-primary 5 米成功 | 6/30，20% | 6/30，20% | 总体无改善 |
| target 成功 | 6/20，30% | 6/20，30% | 不能替代联盟完成 |
| coalition 完成 | 0/10 | 0/10 | P1 未闭合 |
| 第二 primary 5 米成功 | 0/10 | 0/10 | 主要断点仍存在 |
| 第二 primary 最近距离 mean/median | 12.736/13.738 m | 12.573/13.778 m | 均远高于 5 m |
| 第二 primary 最近距离 min-max | 8.873-14.740 m | 8.843-14.309 m | 无单 case 达标 |
| contract allowed sample | 553/5238 | 499/5151 | candidate 未提高合同通过率 |
| control/switch allowed sample | 75/5238 | 89/5151 | 通过样本增加未转化为物理成功 |
| mode transition | 12 | 12 | 无增益 |
| truth identity/state online use | 0/0 | 0/0 | 安全来源约束通过 |

paired seed 上，active-pair 成功数有 6 组持平、2 组 baseline 更好、2 组 candidate 更好。candidate 第二 primary 最近距离在 6/10 seeds 中变小，平均只减少 `0.163 m`，且仍为 `0/10` 成功，不能作为晋级依据。

合并两组后，pair/target/coalition 分别为 `12/60`、`12/40`、`0/20`。第二 primary 按每个 case 的 active membership 动态识别，不写死 `INT-02` 或 `INT-03`；七阶段证据全部可用，`assigned/visible/associated/contract=20/20`、`control/mode=17/20`、physical=`0/20`。20 个最终状态均为 `collision_stop`，但 collision object 未写盘，不能据此归因于 PN、PNG、LOS 或外推公式。candidate 逐 seed non-degradation=false、trend coast 触发=0、soft-specific duration=0，故继续 default-off。D7 阶段 mean/P95 为 `4.84/5.78 ms`，不是主要时序瓶颈。

第二 primary 的阶段证据更具体：两组都有 `10/10` 曾达到 D5 declared lock 和 terminal contract；baseline 有 `8/10`、candidate 有 `9/10` 曾达到 effective control/terminal mode，但物理成功仍是 0。baseline 的规范首失败为 physical 8 例、terminal control 2 例，candidate 为 physical 9 例、terminal control 1 例。20 例最终都为 `collision_stop`，但已写盘记录没有 collision object 名称，故无法进一步判定是场景物体、友方成员、机体或 AirSim 碰撞状态残留。当前不能把它们统一归因为 D5 gate 或 D7 导引律。

### candidate 非退化判定

candidate 的 `terminal_trend_coast_applied` 总数为 0，`soft_prediction_duration_s` 为 0。candidate 中通用 terminal-filter predicted 记录为 19，baseline 为 14；该字段同时覆盖默认 image-KF 短时预测，不能证明 soft innovation prediction 特有分支触发。命令不连续均值在 case 间从 `0.0659` 略升至 `0.0665 m/s`，峰值均为 `6.0 m/s`。结合 paired 结果不稳定和第二 primary `0/10`，候选不满足“实际触发 + 连续性不恶化 + 物理成功不下降”的完整晋级条件，继续 default-off。

### 控制时延

| 层级 | 样本 | mean | P95 | max | 100 ms 预算超限 |
| --- | ---: | ---: | ---: | ---: | ---: |
| control tick 外层，baseline | 1909 | 1070.4 ms | 1248.1 ms | 2072.5 ms | 1909/1909 |
| control tick 外层，candidate | 1896 | 1068.4 ms | 1263.1 ms | 1503.2 ms | 1896/1896 |
| control tick 外层，合计 | 3805 | 1069.4 ms | 1254.1 ms | 2072.5 ms | 3805/3805 |
| main-bus 内层，合计 | 3805 | 349.3 ms | 487.4 ms | 1306.0 ms | 3649/3805 |
| D7 guidance-contract 内部阶段 | 3725 | 4.84 ms | 5.78 ms | 138.74 ms | 不单独用 100 ms 判定 |

control tick 外层中，AirSim frame sample、bus processing、guidance/control RPC 均值分别为 `432.3`、`351.8`、`290.8 ms`。main-bus 内层中 D1 fusion 均值约 `320.0 ms`，是主要阶段；D7 合同计算不是当前主瓶颈。control tick 已包含 main-bus 调用，两层数字不得相加。

### 结论与未闭合 P1

1. P0 安全边界保持：在线控制状态来自 D2 估计航迹，truth identity/state online use 为 0，本地不改写 `global_track_id`。
2. P1 仍未闭合：第二 primary/coalition 5 米完成、持续 measured-lock 与停控归因、三维机动/成员间距、以及 100 ms 实时预算。
3. soft prediction + trend coast 没有完成真实触发与 paired 非退化验收，继续作为 optional/default-off。
4. 后续不通过放宽身份、版本、友方冲突、reserve 或 D3/D4/D5 gate 来伪造成功；先补齐 collision object/成员间距/持续视觉证据并优化 runtime 时延。

## 2026-07-15 本地受控回归

- 场景：任意 primary 数 pair 漏斗、第二 primary 控制层首失败、seed2 单帧 dropout、`png_ttc` 面积跳变与 bbox 裁剪。
- 样本：确定性单元场景；seed2 measured `0.0-0.2s`、dropout `0.3s`、reacquired `0.4s`；TTC 两类各 1 条受控扰动。
- 验收：D7 全量零失败；单帧 run 长度为 1 且重获；两类 TTC 原因匹配、effective control=false、executed law=`radar_pn`、global-track identity 不变。
- 结果：`190 passed`，全部满足；未启动 AirSim，未修改 PN/PNG/LOS/外推公式或上游门控。
- 限制：这些结果只证明诊断/回归可用。真实 2v2/M5N2 多 seed 的第二 primary 5 米完成率、真实 dropout、真实 bbox 扰动和时延仍未采集。

## 2026-07-14 actual-execution 真实 AirSim 结果

验证日期为 2026-07-14，每个场景 1 个 seed。canonical actual 五层按 contract/control/terminal-switch/mode/physical 报告：tuned 2v2 为 `35/26/26/2/2`，M5N2 为 `67/0/0/0/2`，合计 `102/26/26/2/4`；五层均为 `available`。`terminal_switch_allowed_count` 直接从已写盘 `control_commands` 独立统计，不由 control 层推断。2v2 loop latency 约 `123.3 ms`；M5N2 的 3 个 active pair 中 `2/3` 成功，第二 primary 最近约 `11.02 m`，loop latency 约 `384.6 ms`。

M5N2 target 成功为 `2/2`，只表示两个目标各至少有一个 pair 进入 5 米；coalition completion 在独立分母下为 `0/1`，不能写成 target `2/2` 已完成联盟。D6 actual-execution required/available/missing 为 `2/2/0`，summary/CSV/canonical physical count 一致，plan identity 一致，identity/state online truth 均为 0，故 P0 证据链关闭。formal overall fail 是完整 P1 suite 未完成的正确结果；terminal-switch 层和 main/D6 canonical 聚合均已闭合。

剩余 P1：M5N2 第二 primary 获取与 5 米物理闭环、同配置 multi-seed/dropout/candidate、控制延迟拆分，以及 pair funnel/closing speed/三维几何和平台机动标定。3D PN、True PN、APN、FRPN 在线化和同时到达不列当前 P1。本轮仅同步证据，没有修改 PN/PNG/LOS/外推代码或算法。

## 历史 postbatch 导引律语义复核

复核对象为最新两个 seed-1 M5N2 postbatch episode 的 `control_commands.csv`、`intercept_summary.json` 和 main episode bus D7 records。物理控制侧每个 case 有 3 个 active pair，均在约 23 至 29 米 acquisition timeout；collision stop 已为 0。每个 case 的 raw/effective contract 共 40 行，camera gate 通过为 0，latch/effective control 为 0，最大 bbox area ratio 分别约为 `2.49e-4` 和 `2.94e-4`。

物理控制证据按 `d7_pair_guidance_funnel_v2` 得到：baseline 的 INT-02/T001 与 INT-04/T002 首失败为 `raw_terminal_gate/d5_not_locked`，INT-03/T001 为 `camera_quality/bbox_area_too_small`；candidate 的 INT-01/T001 与 INT-04/T002 首失败为 `raw_terminal_gate/d5_not_locked`，INT-03/T001 为 `camera_quality/bbox_area_too_small`。两组均没有实际视觉控制或物理成功。

同时发现物理 control 与 main episode bus replay 使用不同的 D3 plan/state instance。bus replay 把三个 active pair 都推进到 camera gate，而物理控制日志只有一个 pair 到达该阶段；外部 CSV 还把 40 行视觉配置/候选律写成看似实际执行的 `png_vm`。canonical D7 bus record 对这些 gate-failed sample 明确给出 `candidate=png_vm`、`executed=radar_pn`、effective control=false。两类 evidence 不能混合成一个 pair funnel，D6 也不能从候选律或普通 mode transition 推断视觉切换。

D7 已新增 `d7_guidance_law_semantics_v1` 和 4 个专项回归。2026-07-14 全量结果为 `188 passed`，验收阈值零失败。该历史 postbatch 的 state-instance 问题已由当前 actual-v2 plan identity 和五层正式聚合关闭；后续 multi-seed 与 pair-funnel 标定继续保持同一 state instance。未修改位置 PN、VM/TTC PNG、LOS、外推或安全门控。

## 实验范围

- 日期：2026-07-14。
- 数据：`research_modules/airsim_runtime/outputs/p1_terminal_closure_semantics_v2_seed1_20260714*`。
- 样本：真实 AirSim seed 1；M5N2 baseline、M5N2 soft-prediction/trend-coast candidate、2v2 `png_ttc`、2v2 1-frame dropout。
- 方法：只读审计既有 CSV/JSON；没有启动新 AirSim episode。
- 成功半径：5 米；多主资源不要求同时到达。

## 结果

| 场景 | pair 物理结果 | 末端状态 | 主要现象 |
| --- | ---: | --- | --- |
| M5N2 baseline | 0/3 active pair | raw/latch/effective contract/control 均为 0 | INT-01/INT-04 在约 35.7/38.7 米 collision stop；INT-02 在约 26.0 米 acquisition timeout。 |
| M5N2 candidate | 0/3 active pair | raw/latch/effective contract/control 均为 0 | INT-01/INT-04 在约 35.2/38.4 米 collision stop；INT-02 在约 26.6 米 acquisition timeout；soft/trend 未触发。 |
| 2v2 `png_ttc` | 2/2 | effective control 已出现 | 对照链路能够进入视觉末端并达到 5 米。 |
| 2v2 dropout 1 帧 | 2/2 | 出现 2 条 image-KF prediction | 单 seed 证明有界短时预测路径可用，不构成多 seed 晋级证据。 |

## 原因判定

M5N2 不能统一归因为“视觉 gate 太保守”。两个 active pair 没有进入候选约 30 米交接区，应首先归为 `terminal_handoff_range_not_reached`；进入交接区的 INT-02 首先失败在 `d5_not_locked`。现有 main CSV 没有完整 raw reject/measured-lock 字段，部分 `raw=false` 行的原因为空；这些行只能标记证据缺失，不能推断为 camera、LOS、closing-speed 或 maneuver 失败。

## D7 验证

新增测试复现上述 no-switch 结构，并分别覆盖 measured lock 未建立、camera gate、closing-speed gate、maneuver gate 和拒绝原因缺失。2026-07-14 运行：

```bash
python3 -m pytest -q research_modules/d7_proportional_guidance/tests
```

结果：当前全量 `188 passed`，验收阈值为零失败。位置 PN、VM/TTC PNG、LOS 滤波、外推公式、D3/D4/D5 门控和 `global_track_id` 均未修改。

## 剩余限制

- 只有 seed 1，不能形成成功率或置信区间结论。
- M5N2 航路净空和 D5 acquisition 尚未修复。
- canonical actual 五层已经正式聚合；`d7_pair_guidance_funnel_v2` 的完整拒绝原因、measured-lock、closing-speed 和三维机动覆盖仍属 P1 标定。
- candidate 未实际触发，不能声称 soft prediction/trend coast 有收益。
