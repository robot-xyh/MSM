# D5 A3 v2 主动视觉开发态行为克隆候选

验证日期：2026-08-01（America/Los_Angeles）

## 结论

本批语料共 `159502` 个样本，完整 train split `95040` 个样本已用于一次固定配置的行为克隆。
训练语料结构门为 `pass_development_corpus_only`。该门只证明训练 split 的动作、相机角色、episode 和 seed 基础覆盖，不构成正式模型准入。
模型仅为 development shadow-only，不具备 assist 权限，未启动 PPO，规则策略仍是强制回退。
观测 outcome 没有动作执行归因，reward、counterfactual 和 causal label 均不可用，不能用于强化学习或晋级。

## 数据覆盖

- episode：`100`
- train/validation/test episode：`60/20/20`
- train/validation/test sample：`95040/24329/40133`
- 唯一 seed：`60/20/20`，分割交集为 0
- 训练与验证/测试 seed 重叠：`0`
- 训练与显式保留 seed 重叠：`0`
- 训练结构有效样本：`95040`
- 训练 episode：合成 `0`，非合成 `60`
- 意图：`{"hold": 74771, "observe_target": 1547, "reacquire": 79538, "search_sector": 3646}`
- 动作签名：`{"hold|wide|no_target_reference": 74771, "observe_target|wide|target_reference": 1547, "reacquire|wide|target_reference": 79538, "search_sector|wide|no_target_reference": 3646}`
- 视场模式：`{"wide": 159502}`
- 相机类型：`{"interceptor": 153000, "recon": 6502}`

- 补采请求：`0`

逆平方根权重只调整已有样本的损失贡献。语料门按唯一 episode、seed、动作和相机角色计数，复制、过采样和重加权均不能补足覆盖。

## 来源绑定

- dataset manifest SHA-256：`9b80e47aed8f4c7a416694220d63d9156010911951cbbf271905ce5c0d6f31d4`
- split SHA-256：`fb4f6c0ce6566e05113c052af52f45b1ecfbdb3d77727b6c038010777477da7b`
- training-set SHA-256：`3cc6ea166adc74e8cf89e9a5a6b44952b9e4f51d08c83678db39b7b9d1761776`
- generation plan SHA-256：`ed9765395da89e682b250ba23bf7322b290b2a559d0eb4403a2469f9a2cc48a9`
- generation summary SHA-256：`78d814b5dba41533ea9380154a6b8f243f9bfff65da11328679e396b2a89ba50`
- training seed registry SHA-256：`6e4cb133fcd91c12e3aa38039fc2d2fe7fb9ace6b2c3bdb27cc5ce498a7618f5`
- generation summary 内嵌 registry SHA-256：`6e4cb133fcd91c12e3aa38039fc2d2fe7fb9ace6b2c3bdb27cc5ce498a7618f5`
- generation plan 本体不内嵌 registry SHA-256；外部绑定由 generation summary 的 registry 哈希、plan/summary cell 完全相等和三者共同 schedule/Git 绑定建立。
- dataset manifest 内生绑定仅覆盖 manifest、split 和 training-set；不把外部 generation plan/registry 误写成 manifest 内生字段。
- 正式保留 seed：`20` 个，仅做禁止集合核对；R0 和保留 seed 样本读取/运行均为 `false`。

## 训练

固定 seed `20260720`，训练 `5` 个 epoch，
最佳 epoch `5`。训练耗时 `2.876 s`。
训练配置 SHA-256：`87fc2330450afa2487b7a7b3902cbdef2a36a323ba42fc0d6b6cdecef0a51048`；配置总数为 `1`，未做超参数搜索，test 未参与训练或选模。
完整训练样本每个 epoch 使用一次，总样本呈现次数 `475200`。
损失加权：`inverse_sqrt`；缺失动作：`[]`。缺失动作权重保持不可用，没有补零或伪造正样本。

完整流水线耗时 `887.994 s`，其中严格输入完整性检查 `78.996 s`、优化器训练 `2.876 s`。
本轮选择 CPU，峰值 RSS 为 `2342.352 MiB`；CUDA allocated/reserved 均为 0。PyTorch 可见
RTX 4050 Laptop GPU，但 NVML 初始化失败，因此未依赖 `nvidia-smi` 数据。feature cache 与
bundle 共约 161 MiB，权重文件为 47,045 bytes，均在 ignored outputs。

## 指标

| 分割 | 损失 | 精确动作 | 意图准确率 | 视场准确率 | 偏航误差 | 俯仰误差 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| train | 0.591878 | 0.959322 | 0.959322 | 1.000000 | 0.201457 deg | 0.051943 deg |
| validation | 0.604907 | 0.953512 | 0.953512 | 1.000000 | 0.216063 deg | 0.056329 deg |
| test | 0.592662 | 0.959958 | 0.959958 | 1.000000 | 0.184872 deg | 0.047352 deg |

### 动作分层

- test 宏平均召回：`0.495507`
- test 宏平均 F1：`0.487563`
- test 每动作召回：`{"hold": {"available": true, "value": 0.9850199203187251}, "observe_target": {"available": true, "value": 0.0}, "reacquire": {"available": true, "value": 0.9970064361622512}, "search_sector": {"available": true, "value": 0.0}}`
- test 相机角色精确动作：`{"interceptor": {"available": true, "value": 0.9723771235896771}, "recon": {"available": true, "value": 0.6565272496831432}}`
- test 期望校准误差：`0.368239`
- test 分布外比例：`0.000000`
- 上述分布外比例只表示特征超出 train 边界及配置 margin，不等于真正场景分布外验证。独立场景域、AirSim 和真实相机分布外结果均为 unavailable。
- 诊断回退原因计数：`{"feature_out_of_distribution": 0, "low_confidence": 584, "model_action_mismatch": 1607}`

单次候选集前向推理 P50/P95/P99 为 `0.0719/0.0788/0.0852 ms`，设备为 `cpu`。

## 准入

- bundle 状态：`development_shadow_only`
- development precheck：`false`
- assist：`false`
- PPO：`false`
- promotion/assignment/degradation/runtime/production/control/camera command/global_track_id write：`false`
- assist 加载：`false`（bundle_assist_not_admitted）
- 模型前置检查：`fail_closed_model_precheck`
- 前置检查失败原因：`["action_recall_below_threshold:observe_target", "action_recall_below_threshold:search_sector", "macro_intent_recall_below_threshold", "expected_calibration_error_above_threshold"]`
- 权重 SHA256：`b984e3052556879b2acd51d108c862a7ecd9361b2a823733e220f1e1419ad01c`
- manifest SHA256：`9f370a4e6d69fcdd6c484016332befdd567a3e8e8645221ae1a95f2962e0793f`
- 实现 SHA256：`fbbe81a6ae2c78f778f0d6104d80892d64ed4b5aaade834f4de276cc96f9bfdd`

完整 bundle 只保存在 D5 ignored outputs。模型不修改全局航迹标识、计划版本、联盟版本、通信版本或相机命令安全门。

## 后续边界

1. 当前语料结构门已经通过，补采请求为 0；本轮模型仍没有学会 `observe_target` 和
   `search_sector`。下一工作包需要预先冻结少数意图判别与校准方法，并使用新的开发/评估
   seed，不能回看本次 test 反复选模。
2. development precheck 未通过，因此不启动 A3/R0 paired shadow，不允许 assist 或相机命令。
3. 在 shadow 模式形成实际请求动作、runtime ack、执行后 outcome、延迟和安全回退后，才能
   建立动作到结果的归因。当前 ACK 只证明命令接受，不证明模型收益。
4. reward、counterfactual、causal label、真正场景 OOD、AirSim、真实相机和物理动作结果均
   unavailable；PPO 与 D4/D5 联合训练继续关闭。
