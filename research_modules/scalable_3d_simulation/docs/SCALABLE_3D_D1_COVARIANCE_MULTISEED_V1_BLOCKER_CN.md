# D1 多 seed 矩阵 v1 阻断记录

## 结论

首次多 seed 与长时矩阵在 long seed 1102 的 reference 报告阶段失败，矩阵按失败关闭停止。
该批次不进入 D1 性能准入，不计算配对置信区间，也不与后续修复提交混合。

失败不在三维世界积分或 D1 在线融合阶段。10 秒仿真已完成，基础 episode 制品已写盘，
`finite_state=true`，`online_truth_use_count=0`。D6 读取 D2 离线身份结果时发现仅虚警排除
计数与持久化 frame mappings 不一致，进程以状态 1 退出。

## 执行进度

预注册 v1 包含 10 个 short pair 和 3 个 long pair，共 26 个进程。停止时已完成：

- short seeds 1101-1110：10/10 pair，20 个进程正常退出；
- long seed 1101：1/1 pair，2 个进程正常退出；
- 上述 11/11 pair 的跨构建语义审计通过；
- long seed 1102 reference：仿真完成，报告阶段退出 1；
- long seed 1102 candidate 和 long seed 1103 两臂未启动。

原运行器在异常前没有把顶层 manifest 状态从 `running` 改为 `failed`，但失败 arm 已记录
`status=failed` 和 `return_code=1`。main 已在提交 `48de55a` 修复该状态记录缺口。

## 阻断字段

D2 离线身份文件中的审计字段为：

```text
audit.known_false_alarm_only_mapping_count = 14
```

同一文件持久化 frame mappings 中满足以下全部条件的记录只有 11 条：

```text
status == "excluded"
reason == "known_false_alarm_only"
truth_target_id is null
candidate_truth_target_ids is empty
```

D6 consumer 对两种口径做 exact-match。14 与 11 不相等，因此抛出：

```text
D2 known-false-alarm exclusion count contradicts frame mappings
```

初步代码定位显示，D2 audit 计数来自所有 `mapping_disposition_audit` 分组的 disposition，
其中包括 association state 未进入观测评分的分组；最终 frame mapping 对这类分组可能记为
`track_not_assigned_in_frame`，并不属于实际排除。D2 owner 正在复核 producer 口径，D6
consumer 保持严格，不通过忽略异常或修改真值分母恢复运行。

## 失败 episode

| 项目 | 值 |
| --- | --- |
| reference commit | `7cc2d0cfd598a72d60c6ba8c7d4a283f4e5a897d` |
| case | `long_seed_1102` |
| duration | 10 s |
| target/resource/recon | 200 / 200 / 2 |
| online observations | 10,994 |
| finite state | true |
| online truth use | 0 |
| external elapsed | 93.00 s |
| maximum RSS | 2,323,972 KiB |
| process exit | 1 |

失败发生在 `write_episode_truth_isolated_outputs()` 调用链。已写盘的主制品可用于定位 producer
和 consumer 口径，但由于进程非零退出，不能作为正式矩阵 arm。

## 后续处理

1. D2 将审计字段绑定到最终持久化 frame mapping 的真实排除数量，并增加非 observed
   association state 回归。
2. D6 保留 exact-match 检查，并增加本次边界的 consumer 回归。
3. main 将同一 D2 修复叠加到 reference 和 candidate 基线，形成两个新的 clean 实验提交。
4. v2 保持 v1 的 seed、时长、arm 顺序和准入门不变，从头运行全部 13 个 pair。
5. v1 输出只保留本阻断摘要；不得复用其性能数据或与 v2 混合统计。

## 证据摘要

- v1 evidence manifest SHA-256：
  `25f0d7839f8f3b14ed359d20d09a91dd1a6bddbef1d2d59db971024894e7850c`
- failure stderr SHA-256：
  `6831ac0ec238e42e053f642a5009e3679c7647097402f5d9eb8a3ec9edb8934c`
- episode manifest SHA-256：
  `83996d68e9bdc43db5e78d1de949b5228ee4bc6cfda0d98baea13dc6c523c4ff`
- summary SHA-256：
  `f606154e939103acb34e130894e0d98cd594a2f56c0222ef00099d0d0f50c02a`
- identity evaluation SHA-256：
  `67a5c142f51e3a67b145115849a62ca70c5ee2d5ec1ae5f1ed348ed00e799224`

这些哈希绑定首次失败时的 `/tmp/msm_d1_cov_multiseed_20260724_v1` 证据。大体积 episode
不作为源码提交。
