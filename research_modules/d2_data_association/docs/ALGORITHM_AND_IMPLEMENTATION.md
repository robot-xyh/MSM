# D2 多目标数据关联算法与实施方案

**状态日期**：2026-07-20
**适用范围**：科研仿真、受治理日志回放、六维稀疏规则关联、离线评估和跨节点航迹注册基础
**默认主线**：全局最近邻（Global Nearest Neighbor，GNN）与匈牙利算法的一对一硬关联
**安全边界**：本文不包含真实飞控、自动处置、毁伤评估或绕过人工授权的能力

本文依据 D2 当前代码、`README.md`、`PLAN.md`、`MODULE_PRINCIPLES_CN.md` 和系统总汇总同步编写。文中“已实现”必须有仓库代码或回放证据支撑；“可选”“部分实现”和“未实现”不得解释为默认工程能力。

## 0. 最新 AirSim 运行证据对算法选型的影响

2026-07-15 的 M5N2 SimpleFlight 批次完成 baseline/candidate 各 10 seed。D2 association
阶段共获得 3805 个可用 main-bus 计时样本，mean/P95/max 为
`2.521/3.147/98.942 ms`。这些是阶段墙钟时间，不等同于端到端控制周期，也不应与
包含它的 main-bus 总时间再次相加。

本批在线 truth identity/state use 为 0，故在线 IDSW 和 continuity 按合同保持
unavailable。算法不能利用 AirSim actor ID 补齐，也不能把缺失值解释为“零次身份切换”。
第二 primary 的物理失败和 `collision_stop` 属于下游执行现象；在碰撞对象、离线身份映射
和关联首失败证据缺失时，不构成扩大马氏门、切换 JPDA/MHT 或重建 `global_track_id` 的
依据。默认 GNN/Hungarian 和中心 ID 所有权不变。

本轮只纳入 M5N2 20 case；终止信号生效前额外完成的单个 `png_ttc_2v2_seed001` 被
排除，dropout case 完成数为 0。

## 1. 模块任务与工程边界

### 1.1 D2 在系统中的位置

D2 是反无人机系统（Counter-Unmanned Aircraft System，C-UAS）中的多目标数据关联与身份连续性模块。它位于 D1 多传感器融合之后、D3 资源分配之前，并向 D4 降级仲裁、D5 末端视觉关联和 D6 系统评估提供身份与风险证据。

```text
D1 受治理观测/粗航迹
  -> D2 预测、门控、关联、建轨和身份维护
  -> D3 使用稳定 global_track_id 进行资源分配
  -> D5 使用同一 global_track_id 做末端投影配准

D2 风险摘要 -> D4 主动降级仲裁
D2 日志/离线指标 -> D6 统一评估
```

D2 的核心问题不是“目标位置是否足够接近真值”，而是：

1. 同一物理目标在交叉、密集编队、漏检和短时遮挡后是否仍由同一个全局航迹标识符（Identifier，ID）表示；
2. 新观测应更新已有航迹、生成暂定航迹，还是因统计不相容而被拒绝；
3. 同一观测或同一物理目标是否被重复解释；
4. 不同节点发布的局部航迹能否注册到同一规范全局航迹；
5. 无在线真值时，如何发布可解释风险而不伪造身份切换结论。

### 1.2 不属于 D2 的职责

D2 不承担以下工作：

- 不启动、重置或控制微软 AirSim 无人系统仿真器；
- 不直接调用 AirSim 软件开发工具包（Software Development Kit，SDK）；
- 不处理原始相机图像，不执行目标检测和 D5 局部视觉多目标跟踪；
- 不生成或修改 D3 的版本化 `AssignmentPlan`；
- 不直接决定 D4 是否切换到二级节点或完全分布式模式；
- 不允许 D5、D7、源节点本地航迹或仿真对象名称改写 `global_track_id`；
- 不实现原始乱序量测（Out-of-Sequence Measurement，OOSM）的回溯、重放和平滑；
- 不把旧二维 `Tracker` 与新增六维 `Scalable3DTracker` 混为同一默认入口；
- 不把第三方对象转换适配器表述成端到端多目标跟踪系统。

代码中的 `engageable` 只表示航迹质量足以供下游科研实验使用，不表示授权、处置或控制许可。

### 1.3 动态规模原则

当前活动航迹数记为 `N_t`，本帧观测数记为 `N_z`。旧二维路径按实际输入构造 `N_t x N_z` 代价矩阵；六维路径按实际输入建立空间索引和稀疏候选图，仅对候选连通分量分配局部矩阵。两者都不从场景名推断目标数量，不写死 2 对 2 或 5 对 5。固定规模场景只用于可重复的基准回放。

因此，目标出生、漏检、虚警、丢失和删除造成的 `N_t != N_z` 是正常输入，不需要填充虚拟目标或截断观测。

## 2. 当前能力分层

| 能力 | 当前状态 | 是否默认 | 准确边界 |
| --- | --- | --- | --- |
| 二维常速度预测 | 已实现 | 是 | 状态为位置和速度四维向量 |
| 六维 NED 常速度预测与 3D 位置更新 | 已实现 | 显式选择 | `[pN,pE,pD,vN,vE,vD]`，不替换旧二维入口 |
| KD-tree 稀疏 GNN/匈牙利 | 已实现 | 六维路径 | 3D 马氏门控后按候选图连通分量求解 |
| 协方差输入治理 | 已实现 | 是 | 拒绝非有限、明显非对称或明显非半正定输入 |
| 马氏距离门控 | 已实现 | 是 | 基础门限默认 `9.21` |
| 质量感知门限 | 已实现轻量基线 | 是 | 有界规则，不是完整通用自适应门控框架 |
| 运动一致性代价 | 已实现 | 是 | 方向、短历史和异常加速度的轻量代价 |
| GNN/匈牙利关联 | 已实现 | 是 | 默认一对一硬关联主线 |
| 线性卡尔曼更新 | 已实现 | 是 | 使用 Joseph 协方差更新形式 |
| 航迹生命周期 | 已实现 | 是 | 暂定、确认、可用、丢失、删除 |
| 风险滑窗与软硬风险 | 已实现 | 是 | 风险分数不是身份错误后验概率 |
| 在线真值隔离 | 已实现 | 是 | 真值只在关联完成后进入离线评估 |
| 身份切换与连续性评估 | 已实现 | 离线 | 缺真值时显式标记不可用 |
| 归一化创新平方 | 已实现 | 在线可用 | 用于创新统计一致性检查 |
| 归一化估计误差平方 | 已实现 | 仅离线 | 需要四维离线真值状态 |
| 跨节点规范航迹注册 | 已实现基础 | 显式调用 | 建立规范绑定和融合请求，不计算数值融合后验 |
| 联合概率数据关联 | 轻量研究近似 | 否 | 没有概率混合状态和协方差更新 |
| 多假设跟踪 | 有界研究近似 | 否 | 没有完整长期假设树和 N 次扫描剪枝 |
| Stone Soup/FilterPy | 对象适配和冒烟测试 | 否 | 不是端到端关联跟踪器 |
| 六维规则跟踪 | 已实现基础 | 显式选择 | main 总线接入、真实多 seed 和极端密度预算未完成 |
| 扩展/无迹滤波、交互多模型 | 未实现 | 否 | 只能作为后续研究项 |

优先级零、优先级一和优先级二（Priority 0 / Priority 1 / Priority 2，P0 / P1 / P2）表示工程优先级，不表示算法自动进入默认主线。

## 3. D1 受治理输入

### 3.1 输入合同

D2 支持两类 D1 输入适配路径。

第一类是兼容路径中 D1 六维北-东-地坐标系（North-East-Down，NED）`GlobalTrack` 的二维投影：

- D1 状态顺序为 `[north, east, down, vn, ve, vd]`；
- D1 协方差为 `6 x 6`；
- D2 取北、东位置作为二维观测，取协方差左上 `2 x 2` 子矩阵；
- 保留 `measurement_timestamp`、`arrival_timestamp`、来源 ID 和元数据；
- 该适配只做二维投影，不改变旧 `Tracker` 的状态维度。

第二类是 D1 受治理回放：

- 清单版本为 `d1.governed_replay_manifest.v1`；
- 观测版本为 `d1.sensor_observation.v1`；
- 当前只把 NED 工作空间中的雷达球坐标记录转换为二维北-东观测；
- 声学方位和光电（Electro-Optical，EO）像素观测因量测空间不同而显式跳过；
- 跳过数量及原因写入报告元数据，不能把不同量纲直接混入同一位置代价矩阵；
- 按量测时间和 AirSim 帧号聚合为 D2 帧。

第三类是 2026-07-20 新增的六维稀疏路径：

- 在线输入 `Detection3D` 只包含匿名 ID、NED 三维位置、3x3 covariance、双时间戳、
  置信度及可选速度提示；没有 truth 字段；
- `detections3d_from_d1_global_tracks()` 读取六维状态/协方差但忽略上游对象的
  `global_track_id` 值，D2 重新分配规范 ID；D1 航迹 state-valid timestamp 作为关联
  epoch，原始 sensor measurement/arrival timestamp 保留在 source metadata；
- `detection3d_from_position_measurement()` 只接受 Cartesian NED 三维位置；原始 radar
  `[range,azimuth,elevation]` 和 visual pixel 不得冒充笛卡尔位置，必须先经 D1；
- 当前 scan 必须共享 state-valid association epoch；乱序量测回溯仍未实现。

### 3.2 雷达球坐标到北-东平面的投影

设雷达测得距离 `rho`、方位角 `a` 和俯仰角 `e`，传感器 NED 位置为 `(n_s,e_s,d_s)`，则水平位置为：

\[
\begin{aligned}
n &= n_s + \rho\cos(e)\cos(a),\\
e_N &= e_s + \rho\cos(e)\sin(a).
\end{aligned}
\]

雷达球坐标量测协方差记为 `R_rae`，从球坐标到北-东平面的雅可比矩阵记为 `J`，投影协方差为：

\[
R_{ne}=J R_{rae}J^T.
\]

这样，距离相关噪声不会在转换后丢失。D2 后续门控使用 `R_ne`，而不是只比较投影位置的欧氏距离。

### 3.3 双时间戳

- `measurement_timestamp` 表示观测对应的物理时刻；
- `arrival_timestamp` 表示观测到达处理链路的时刻。

D2 受治理适配器保留二者。当前主跟踪器假定输入已按量测时间整理，并以量测时间推进状态。`dt` 被限制为非负数只能防止反向传播，不等于已经实现 OOSM 回溯。

当输入是 D1 已传播到 `valid_at/published_at` 的融合航迹时，六维 adapter 不把该状态
误标为更早的原始传感器量测状态：`Detection3D.measurement_timestamp` 使用 state-valid
epoch，原始 sensor measurement/arrival timestamp 另存为
`source_measurement_timestamp/source_arrival_timestamp`。main 接线仍需同时传递这些
字段，供 D6 做延迟与 OOSM 审计。

### 3.4 二维 `Detection`

默认关联器消费 `Detection`：

| 字段 | 含义 | 治理要求 |
| --- | --- | --- |
| `detection_id` | 单帧匿名观测 ID | 不是全局身份权威 |
| `timestamp` | 量测时刻 | 必须为有限数值 |
| `position` | 二维位置 | 固定为两维 |
| `covariance` | 二维量测协方差 | 固定 `2 x 2`，进入一致性检查 |
| `confidence` | 观测置信度 | 当前存储并透传，不直接进入默认代价 |
| `feature` | 可选类别或外观特征 | 仅在维度一致时进入特征代价 |
| `metadata` | 时间、来源、投影和谱系 | 在线路径递归移除真值字段 |
| `truth_id` | 离线真值 ID | 在线受治理路径必须为空 |

### 3.5 D2 `GlobalTrack`

D2 规范航迹的默认状态为：

\[
\mathbf{x}=[p_x,p_y,v_x,v_y]^T,
\]

协方差为 `4 x 4`。主要字段包括：

- `global_track_id`：由中心 D2 跟踪器创建的规范身份键；
- `state`、`covariance`、`timestamp`：状态、协方差和有效时刻；
- `lifecycle_state`：生命周期；
- `hits`、`consecutive_hits`、`misses`、`age`：命中、漏检和年龄；
- `identity_confidence`：轻量身份置信度；
- `track_quality`：航迹质量；
- `association_risk`：关联风险；
- `quality_metadata`：质量和风险分项；
- `history`、`transition_log`：状态历史和转移审计。

新航迹按 `T001`、`T002` 等中心序号创建。源观测 ID、本地航迹 ID、仿真对象名称和离线真值 ID 都不能替代该编号。

## 4. 默认算法主线

### 4.1 每帧执行流程

```text
受治理 DetectionBatch
  -> 检查时间、维度和协方差
  -> Tracker.predict_all(measurement_timestamp)
  -> 构造创新和创新协方差
  -> 马氏门控与质量感知门限
  -> 计算特征和运动一致性代价
  -> GNN/匈牙利一对一求解
  -> 匹配航迹执行卡尔曼更新
  -> 未匹配航迹执行漏检/丢失/删除逻辑
  -> 未匹配观测生成暂定航迹
  -> 更新质量、风险、状态转移和关联日志
  -> 在线发布不含真值的活动航迹
  -> 全回合结束后由离线评估器读取独立真值
```

### 4.2 二维常速度预测

默认使用常速度模型（Constant Velocity，CV）。这里的 CV 表示运动模型，不是 AirSim 的计算机视觉（Computer Vision）模式。

设相邻量测时间差为 `dt`，状态转移矩阵为：

\[
F(dt)=
\begin{bmatrix}
1&0&dt&0\\
0&1&0&dt\\
0&0&1&0\\
0&0&0&1
\end{bmatrix}.
\]

预测方程为：

\[
\hat{\mathbf{x}}^-_k=F\hat{\mathbf{x}}^+_{k-1},
\qquad
P^-_k=F P^+_{k-1}F^T+Q(dt).
\]

过程噪声强度默认 `q=0.20`，离散过程噪声为：

\[
Q=q
\begin{bmatrix}
dt^4/4&0&dt^3/2&0\\
0&dt^4/4&0&dt^3/2\\
dt^3/2&0&dt^2&0\\
0&dt^3/2&0&dt^2
\end{bmatrix}.
\]

常速度模型计算稳定、参数少，适合建立可解释基线。其限制是强机动或明显垂直运动会增大预测误差，进而导致门内候选重叠。

### 4.3 观测创新

二维位置观测矩阵为：

\[
H=
\begin{bmatrix}
1&0&0&0\\
0&1&0&0
\end{bmatrix}.
\]

对航迹 `i` 与观测 `j`：

\[
\hat{\mathbf{z}}_i=H\hat{\mathbf{x}}^-_i,
\quad
\mathbf{r}_{ij}=\mathbf{z}_j-\hat{\mathbf{z}}_i,
\quad
S_{ij}=H P^-_iH^T+R_j.
\]

`r_ij` 是创新，`S_ij` 是创新协方差，`R_j` 是观测协方差。航迹和观测的不确定性同时进入匹配计算。

### 4.4 协方差治理

观测和航迹协方差必须满足：

1. 形状正确；
2. 所有元素有限；
3. 在数值容差内对称；
4. 在数值容差内为半正定（Positive Semidefinite，PSD）。

明显非法的协方差直接拒绝。仅对浮点误差尺度内的缺陷执行：

- `0.5(P+P^T)` 对称化；
- 将极小或轻微负特征值抬升至机器精度相关下限。

`covariance_consistency` 表示最新检查结果，`regularization_ever_applied` 和 `last_regularization` 保留历史正则化证据。输入矩阵合法不代表滤波统计一致，后者由归一化创新平方和归一化估计误差平方检查。

### 4.5 马氏距离门控

马氏平方距离为：

\[
d^2_{ij}=\mathbf{r}_{ij}^T S_{ij}^{-1}\mathbf{r}_{ij}.
\]

创新协方差不可逆时使用广义逆。基础门限 `g_0=9.21`，接近二维卡方分布 99% 分位。超过实际门限的候选被设为大代价 `10^9`，并记录 `mahalanobis_gate` 拒绝原因。

门控先于全局分配，作用是排除统计上明显不相容的候选。它不是身份确认本身：多个目标协方差重叠时，多个候选可能同时通过门控。

### 4.6 质量感知门限

默认开启轻量质量感知门限。每条航迹质量为：

\[
q_t=0.28q_P+0.18q_H+0.12q_A+0.18q_M+0.16q_L+0.08q_I,
\]

其中：

- `q_P`：位置协方差对应的不确定性质量；
- `q_H`：累计命中质量；
- `q_A`：航迹年龄质量；
- `q_M`：漏检惩罚后的质量；
- `q_L`：生命周期质量；
- `q_I`：身份置信度。

实际门限按以下结构调整：

\[
g_i=\operatorname{clip}
\left(g_0(1+r_q+r_P-t_d-t_a),g_{min},g_{max}\right).
\]

- 低质量和大位置协方差会受控放宽门限，降低漏配概率；
- 局部目标密度高时收紧门限，降低错误吸附概率；
- 上一帧关联风险高且目标密集时进一步收紧；
- 默认上下界为 `4.0` 和 `16.0`。

这是可解释的有界基线，不是完整自适应门控理论，也没有在所有真实场景中完成冻结标定。

### 4.7 关联代价

门内候选总代价为：

\[
C_{ij}=d^2_{ij}+w_f C^{feature}_{ij}+w_m C^{motion}_{ij}.
\]

特征维度一致时：

\[
C^{feature}_{ij}=\|\mathbf{f}_i-\mathbf{f}_j\|^2.
\]

缺少特征或维度不一致时，特征项为零。运动一致性代价为：

\[
C^{motion}_{ij}=\min(3,C_{dir}+0.75C_{hist}+0.50C_{acc}).
\]

其中：

- `C_dir` 比较当前速度方向与候选残差方向；
- `C_hist` 比较短时历史运动方向与候选方向；
- `C_acc` 惩罚异常大的候选加速度；
- 方向项采用 `(1-cos(theta))/2`，同向接近零，反向接近一。

运动一致性只是关联代价增强，不改变常速度预测模型。

### 4.8 GNN/匈牙利一对一求解

GNN 在当前帧求解：

\[
\min_{a_{ij}}\sum_{i=1}^{N_t}\sum_{j=1}^{N_z}a_{ij}C_{ij},
\]

满足：

\[
a_{ij}\in\{0,1\},\qquad
\sum_j a_{ij}\leq1,\qquad
\sum_i a_{ij}\leq1.
\]

即每条航迹最多匹配一个观测，每个观测最多匹配一条航迹。实现调用 Python 科学计算库 SciPy 的 `linear_sum_assignment`。求解后再次检查大代价和对应航迹门限，防止矩形矩阵中的门外项误入匹配结果。

匈牙利求解复杂度约为 `O(max(N_t,N_z)^3)`。它不限制输入规模，但更大目标数仍需要计算预算和场景分区。

### 4.9 歧义度

对每条航迹，将门内代价升序排列。最优与次优代价差记为 `Delta_i`，行歧义分数为：

\[
A_i=\exp(-0.5\Delta_i).
\]

总体 `ambiguity_score` 是各行分数的平均值。仅有一个合法候选时该行记零。代价越接近，歧义越接近一，表示 GNN 硬判决越可能只是打破平局。

### 4.10 卡尔曼更新

匹配后执行线性卡尔曼更新：

\[
K=P^-H^T(HP^-H^T+R)^{-1},
\]

\[
\hat{\mathbf{x}}^+=\hat{\mathbf{x}}^-+K\mathbf{r}.
\]

协方差使用 Joseph 形式：

\[
P^+=(I-KH)P^-(I-KH)^T+KRK^T.
\]

Joseph 形式更利于保持数值对称和半正定。更新后累计命中、清零漏检、记录最近观测 ID，并以默认平滑系数 `0.85` 更新可选特征。

### 4.11 动态建轨

未匹配观测生成暂定航迹：

\[
\mathbf{x}_0=[z_x,z_y,0,0]^T.
\]

初始位置方差为 `4.0`，初始速度方差为 `25.0`。新 ID 由中心 `Tracker` 顺序生成，不继承观测 ID 或仿真真值 ID。

## 5. 生命周期与身份权威

### 5.1 在线状态机

```text
tentative -> confirmed -> engageable
     |           |             |
     +-----------+------miss--> lost --more miss--> dropped
                              |
                              +--hit--> confirmed 或 engageable
```

中文对应为：暂定、确认、可供下游研究使用、丢失和删除。当前没有 `engaged` 状态。

| 条件 | 转移 | 默认值 |
| --- | --- | ---: |
| 连续命中达到确认数 | `tentative -> confirmed` | `confirmation_hits=2` |
| 累计命中和协方差满足质量条件 | `confirmed -> engageable` | `hits>=4` 且协方差迹 `<=20` |
| 连续漏检达到丢失阈值 | 活动状态 `-> lost` | `lost_miss_threshold=2` |
| 连续漏检达到删除阈值 | 非删除状态 `-> dropped` | `drop_miss_threshold=5` |
| 丢失后重新命中 | `lost -> confirmed/engageable` | 按命中和协方差重新判断 |

不同的确认、丢失和删除阈值形成生命周期迟滞，防止单帧漏检立即删轨，也防止一次重获无条件恢复高质量状态。每次转移写入 `TrackTransition`，记录时刻、前后状态和原因。

### 5.2 在线确认与离线 M-of-N

在线跟踪器按连续命中确认。`InitializationGovernanceProfile` 的默认“3 次扫描中至少命中 2 次”（M-of-N，当前为 2-of-3）只用于离线初始化评估，不会读取真值改变在线状态机。

因此，“M-of-N 已实现”表示评估合同和标定工具存在，不表示在线跟踪器已经采用通用滑窗建轨器。

### 5.3 `global_track_id` 权威规则

1. `global_track_id` 只由中心 D2 `Tracker` 或中心跨节点注册表创建和维护；
2. D1 来源 ID 在二维投影中只作为元数据，不自动成为 D2 规范 ID；
3. `detection_id` 只用于单帧匹配和日志；
4. 本地视觉航迹 ID、节点局部航迹 ID、AirSim actor 名称和离线真值 ID 都无改名权限；
5. D5 的末端不一致只能作为风险证据，不能直接把全局航迹重绑到另一个 ID；
6. D7 只能消费 D2/D3 传递的全局 ID，不能按接近对象重新命名；
7. 不因目标数量变化补齐固定长度 ID；
8. 多个合法来源航迹绑定同一个规范航迹，不代表出现多个目标。

## 6. 在线真值隔离与离线评估

### 6.1 隔离流程

受治理回放默认执行：

1. 源观测 ID 替换为按帧匿名 ID；
2. 在线 `Detection.truth_id` 置空；
3. actor、truth、ground-truth 等嵌套元数据递归删除；
4. 在线 `GlobalTrack.truth_id` 置空；
5. 在线关联日志不携带真值标签、真值目标数或归一化估计误差平方；
6. 全部在线关联完成后，独立离线评估器才读取真值文件。

离线标签合同为 `d2-offline-truth-label/v1`，使用 JavaScript 对象表示法（JavaScript Object Notation，JSON）的逐行格式（JSON Lines，JSONL）。每条记录至少包含回合 ID、帧号、时间、真值 ID 和二维位置。

在线帧与真值只允许在冻结的 `1e-9` 秒容差内精确对齐。无唯一对应时标记部分可用或拒绝，不能用最近邻时间补配制造虚假的身份改善。

### 6.2 为什么必须隔离

AirSim actor ID 是仿真真值，不是现实传感器可获得的信息。若在线关联直接使用 actor ID，身份切换计数和连续性将失去意义。当前“在线匿名运行、写盘后独立评分”的方式保证算法只使用位置、时间、协方差、特征和历史，同时保留可重复评估。

### 6.3 可用性语义

无离线真值时：

- `truth_metrics_available=false`；
- `continuity_available=false`；
- 身份切换、身份连续性和归一化估计误差平方不可解释；
- 兼容字段即使为 `0.0`，也不能解释为“没有身份切换”或“连续性为零”。

## 7. 风险摘要和指标

### 7.1 航迹质量与关联风险

每条航迹输出 `track_quality` 和 `association_risk`。当前关联风险由以下分量组成并截断至 `[0,1]`：

- 低航迹质量；
- 多候选；
- 运动不一致；
- 连续漏检；
- 本帧未匹配；
- 暂定或丢失状态；
- 新建航迹。

该值是可解释规则分数，不是“身份错误概率”。

### 7.2 五帧风险滑窗

`AssociationRiskSummaryWindowGenerator` 默认按五帧汇总：

- 关联歧义；
- 候选重叠率；
- 最优和次优代价间隔风险；
- 身份切换窗口增量；
- 重复分配窗口增量；
- 可用时的连续性风险；
- D5 末端不一致次数；
- 航迹质量和最大关联风险；
- 来源节点和链路类型。

不可用的连续性不参与硬风险计算。D2 向 D4 发布摘要，不要求 D4 解析完整代价矩阵。

### 7.3 软风险和硬风险

| 风险类型 | 证据 | 默认阈值 | 解释 |
| --- | --- | ---: | --- |
| 软风险 | 歧义分数 | `>=0.45` | 多个候选代价接近 |
| 软风险 | 候选重叠率 | `>=0.30` | 多航迹共享候选 |
| 软风险 | 代价间隔风险 | `>=0.45` | 最优优势不足 |
| 软风险 | D5 不一致 | `>=1` | 末端证据与中心预测冲突 |
| 硬风险 | 身份切换增量 | `>=1` | 已发生规范身份切换 |
| 硬风险 | 重复分配增量 | `>=1` | 已出现重复解释 |
| 硬风险 | 重复航迹风险 | `>=0.65` | 规范目标可能被重复表示 |
| 硬风险 | 可用身份连续性 | `<0.75` | 身份稳定覆盖明显退化 |

软风险只支持继续观察、提高 D3 迟滞或请求额外证据；不能由单帧软风险直接触发主动降级。D4 必须结合 D1 不确定度、D3 计划时效、D5 末端证据和通信健康状态仲裁。

### 7.4 身份切换与连续性

标识符切换计数（Identifier Switch Count，IDSW）定义为：同一真实目标本帧的代表 `global_track_id` 与上一已分配帧不同，则计数增加一。

设真实目标集合为 `U`，目标 `u` 存在 `T_u` 帧，被任意航迹覆盖 `C_u` 帧，由同一代表航迹稳定覆盖 `S_u` 帧：

\[
\text{coverage continuity}=
\frac{1}{|U|}\sum_{u\in U}\frac{C_u}{T_u},
\]

\[
\text{identity continuity}=
\frac{1}{|U|}\sum_{u\in U}\frac{S_u}{T_u}.
\]

当前 `track_continuity` 是 `identity_continuity` 的兼容别名。`duplicate_assignment_count` 统计同一观测、同一航迹或同一真实目标被重复使用和解释的异常。

### 7.5 几何误差

均方根误差（Root Mean Square Error，RMSE）为：

\[
\mathrm{RMSE}=\sqrt{\frac{1}{K}\sum_{k=1}^{K}
\|\hat{\mathbf{p}}_k-\mathbf{p}^{truth}_k\|^2}.
\]

RMSE 只衡量几何精度。两个目标交换身份但位置仍接近真值时，RMSE 可能较小，因此不能替代 IDSW 和身份连续性。

### 7.6 NIS 与 NEES

归一化创新平方（Normalized Innovation Squared，NIS）为：

\[
\mathrm{NIS}=\mathbf{r}^T S^{-1}\mathbf{r}.
\]

它不需要真值，可在线计算。当前按二维量测自由度二的 95% 卡方区间统计样本数、均值、中位数和区间覆盖率。

归一化估计误差平方（Normalized Estimation Error Squared，NEES）为：

\[
\mathrm{NEES}=(\hat{\mathbf{x}}-\mathbf{x}^{truth})^T
P^{-1}(\hat{\mathbf{x}}-\mathbf{x}^{truth}).
\]

它需要四维离线真值状态，仅在独立评估器中计算，并按自由度四的 95% 卡方区间统计。缺真值状态时必须标记不可用，不能填零。

## 8. 跨节点规范航迹注册

该能力用于中心、二级高空侦察节点和拦截节点把各自局部航迹注册到规范全局身份。它与单帧 `Detection -> GlobalTrack` 关联路径分离。

### 8.1 来源航迹合同

`SourceTrackSummary` 包含：

- `(source_node_id, local_track_id, local_epoch)` 来源命名空间；
- `measurement_timestamp` 和 `arrival_timestamp`；
- 六维 NED 状态 `[north,east,down,vn,ve,vd]`；
- `6 x 6` 协方差；
- 质量、信息谱系和载荷消息 ID；
- 相关性状态；
- 非权威候选规范 ID 和当前规范 ID 提示。

候选提示没有改写权限，只有中心 `CrossNodeTrackRegistry` 能创建和维护规范绑定。

### 8.2 公共时刻传播

来源航迹先传播到公共融合时刻。六维常速度状态转移为：

\[
F_6(dt)=
\begin{bmatrix}
I_3&dtI_3\\
0&I_3
\end{bmatrix}.
\]

传播同时加入三维白噪声加速度过程协方差。融合时刻不得早于量测时刻或消息到达时刻，注册表时间必须单调。

### 8.3 航迹到航迹门控

来源与规范航迹状态残差为：

\[
\mathbf{e}=\mathbf{x}_{source}-\mathbf{x}_{canonical}.
\]

已知交叉协方差 `P_sc` 时：

\[
P_\Delta=P_c+P_s-P_{sc}-P_{sc}^T.
\]

相关性未知时，当前门控采用保守膨胀：

\[
P_\Delta=2(P_c+P_s).
\]

随后计算六维马氏平方距离：

\[
d^2=\mathbf{e}^TP_\Delta^{\dagger}\mathbf{e},
\]

其中 `dagger` 表示广义逆，默认门限为 `16.812`。已有绑定可获得最多 `4.0` 的连续性代价偏置，但门外候选不能靠偏置回到门内。

### 8.4 按来源分组的匈牙利注册

注册表按 `source_node_id` 分组，对每个来源分别执行一对一匈牙利匹配：

- 同一来源内部保持一对一；
- 不同节点各自的一条来源航迹可以绑定同一个规范 ID；
- 合法多源观测不会增加目标基数；
- 无门内规范航迹时创建 `GT-000001` 等规范 ID。

注册表拒绝重复来源键、重复载荷 ID、重复信息谱系、明确重复信息以及时间不递增的陈旧或重放消息。

### 8.5 相关性决策与数值融合边界

| 条件 | D2 输出 | 后续职责 |
| --- | --- | --- |
| 单一来源 | `NO_FUSION_SINGLE_SOURCE` | 不需要融合 |
| 已知交叉协方差 | `REQUEST_EXACT_CORRELATED_FUSION` | 请求 D1 做精确相关融合 |
| 相关性未知 | `REQUEST_COVARIANCE_INTERSECTION` | 请求 D1 做协方差交集 |
| 重复信息 | `REJECT_DUPLICATE_INFORMATION` | 禁止重复使用 |

协方差交集（Covariance Intersection，CI）用于未知交叉相关时的保守融合。D2 当前只完成身份对应、相关性分类、规范绑定和融合请求，不在本模块计算或回写数值后验。

在线跨节点指标只统计规范重绑、重复拒绝和传输/排队/融合延迟。跨节点 IDSW、规范重复、精确率和召回率仍由独立离线评估器使用隔离真值计算。

## 9. 可选研究算法的准确边界

### 9.1 轻量 JPDA

联合概率数据关联（Joint Probabilistic Data Association，JPDA）对每条航迹最多保留四个门内候选，最多枚举 `4096` 个联合假设。当前假设对数似然为：

\[
\log L(h)=
\sum_{(i,j)\in h}
\left[\log P_D-\frac{1}{2}C_{ij}\right]
+n_{miss}\log(1-P_D)
+n_{fa}\log\lambda_c.
\]

默认探测概率 `P_D=0.90`，杂波密度 `lambda_c=10^{-3}`。归一化后，候选边缘概率为包含该匹配的假设概率之和。当前只选取边缘概率不低于 `0.35` 的非冲突匹配，再由普通 `Tracker` 做单一观测卡尔曼更新。

因此当前 JPDA：

- 已实现小规模联合假设枚举、概率归一化和边缘概率；
- 未实现概率加权状态混合和协方差混合；
- 未实现航迹合并抑制和生产级分簇；
- 目标数增大时依赖假设上限截断；
- 必须显式选择，不会按风险自动替换 GNN；
- 2026-07-13 同输入回放结果退化，未获主线晋级资格。

### 9.2 有界 MHT

多假设跟踪（Multiple Hypothesis Tracking，MHT）维护有限分支。分支代价为：

\[
J_{new}=J_{old}+\sum C_{ij}+6.0n_{miss}+4.0n_{fa}.
\]

默认每条航迹最多三个候选，每帧最多生成 `512` 个分配，保留最优 `16` 个分支和最近五帧历史，当前帧采用最优分支结果。

当前 MHT：

- 已实现有限分支、短历史、漏检和虚警惩罚；
- 未实现完整 N 次扫描剪枝、长期假设树、分簇和确认管理；
- 未建立真实场景下的中心算力预算；
- 只用于接口、复杂度和离线对照研究；
- 不能称为完整工业级 MHT。

### 9.3 第三方框架

P2 隔离基准可在同一冻结回放摘要下输出五类结果：默认 GNN、模块内轻量 JPDA、模块内有界 MHT、Stone Soup 和 FilterPy。

- Stone Soup 多目标跟踪研究框架当前只完成 D2 `Detection` 到框架对象的转换和延时冒烟测试；
- FilterPy 滤波算法库当前只创建二维常速度卡尔曼对象并执行对象级预测和更新；
- 两条外部路径都没有端到端跨帧身份、生命周期和数据关联；
- 外部路径的 IDSW 和连续性必须标记不可用；
- 依赖缺失或接口失败时必须输出 `unavailable_reason`，不能静默回退；
- 它们不进入默认依赖，不替换 NumPy/SciPy 主线。

### 9.4 明确未实现的预测升级

扩展卡尔曼滤波（Extended Kalman Filter，EKF）、无迹卡尔曼滤波（Unscented Kalman Filter，UKF）和交互多模型（Interacting Multiple Model，IMM）当前均未进入 D2 跟踪器。若未来证明机动预测误差是身份切换主因，应先冻结三维状态、非线性量测、模型转移概率和评估场景，再做同输入、同预算对照。

## 10. 代码实施结构

| 文件 | 主要职责 |
| --- | --- |
| `models.py` | `Detection`、`GlobalTrack`、关联结果和生命周期数据结构 |
| `gating.py` | 协方差感知门控、质量门限、特征与运动一致性代价 |
| `associators.py` | GNN/匈牙利、轻量 JPDA 和有界 MHT |
| `tracker.py` | 预测、更新、动态建轨、漏检处理、状态机和质量风险 |
| `metrics.py` | IDSW、连续性、重复分配、风险滑窗和风险分类 |
| `d1_governed_adapter.py` | D1 受治理回放到匿名二维观测的转换 |
| `d1_offline_truth_adapter.py` | D1 独立真值旁路到 D2 离线标签的严格对齐 |
| `offline_truth.py` | 离线真值合同、评估和可用性语义 |
| `replay_governance.py` | 初始化治理、日志模式和在线真值隔离 |
| `replay.py` | JSON/JSONL 回放、报告和门限敏感性汇总 |
| `p1_replay_stress.py` | 漏检、杂波、延迟噪声和组合压力变换 |
| `p1_identity_calibration.py` | 54 配置筛选、20 种子确认和冻结准入规则 |
| `calibration.py` | 密集交叉多种子校准工具 |
| `cross_node_models.py` | 跨节点来源航迹、规范绑定和融合请求结构 |
| `cross_node_registry.py` | 公共时刻传播、按来源匈牙利匹配和注册表 |
| `cross_node_metrics.py` | 在线无真值指标和离线跨节点评分 |
| `p2_benchmark.py` | 同输入可选算法与第三方对象适配基准 |
| `dry_run_adapter.py` | AirSim 风格离线帧和跨模块总线消息适配 |

### 10.1 核心调用关系

```python
associator = GNNHungarianAssociator(
    gate_threshold=9.21,
    quality_aware_gate=True,
)
tracker = Tracker(associator=associator)
result = tracker.step(detections, timestamp)
summary = tracker.metrics.summary()
```

`DataAssociator.associate(tracks, detections, timestamp)` 是关联器插件边界。新关联器必须返回统一 `AssociationResult`，才能复用跟踪器、生命周期、日志和评估。但接口兼容不等于算法已通过主线准入。

### 10.2 关键输出

每帧 `AssociationResult` 至少包括：

- `matched_pairs`；
- `unmatched_track_ids`；
- `unmatched_detection_ids`；
- `ambiguity_score`；
- `rejected_pairs`；
- `cost_matrix` 和 `distance_matrix`；
- 各航迹门限、候选数量、运动一致性和质量风险元数据；
- 可选风险摘要。

`AssociationLogEntry` 再增加运行耗时、输入规模、配置版本和可用性。下游使用摘要和规范航迹，不应自行重算或改写身份。

## 11. 参数治理与调参顺序

| 参数 | 默认/基线 | 作用 | 主要风险 |
| --- | ---: | --- | --- |
| `gate_threshold` | `9.21` | 基础马氏门限 | 太宽吸附错误目标，太窄增加漏配 |
| 质量门限下界/上界 | `4.0 / 16.0` | 限制自适应幅度 | 未分层标定时不能任意扩大 |
| `feature_weight` | 类默认 `1.0`；干运行显式 `6.0` | 可选特征代价 | 特征不稳定时可能反向伤害关联 |
| `motion_weight` | `1.0` | 运动一致性权重 | 机动目标过高权重可能拒绝真实候选 |
| `process_noise` | `0.20` | 常速度模型机动余量 | 过大使协方差膨胀，过小导致门外漏配 |
| `confirmation_hits` | `2` | 在线确认速度 | 太低形成虚假航迹，太高增加确认延迟 |
| `engageable_hits` | `4` | 高质量航迹命中要求 | 只影响研究质量状态，不是授权 |
| `lost_miss_threshold` | `2` | 进入丢失状态 | 太低使短漏检频繁退化 |
| `drop_miss_threshold` | `5` | 删除航迹 | 太高会保留陈旧航迹 |
| JPDA 边缘概率阈值 | `0.35` | 研究对照匹配阈值 | 不应直接迁移到主线 |
| MHT 最大分支数 | `16` | 限制研究对照计算量 | 分支过少可能提前剪掉正确历史 |

调参顺序必须是：

1. 检查时间戳、坐标和协方差；
2. 校准固定马氏门限；
3. 校准质量感知门限；
4. 校准过程噪声和生命周期；
5. 仅在特征可靠时引入特征权重；
6. 最后才比较 JPDA/MHT。

复杂关联器不能用来掩盖时间、坐标或协方差错误。

## 12. 严格回放校准方法

### 12.1 固定参数矩阵

P1 身份校准固定 54 组 GNN 配置：

- 马氏门限：`5.99 / 9.21 / 13.82`；
- 质量感知门控：关闭/开启；
- 丢失/删除阈值：`1/3`、`2/5`、`3/7`；
- 运动权重倍数：`0.5 / 1.0 / 2.0`。

十个唯一种子用于候选筛选，二十个唯一种子用于确认默认基线、最佳 GNN 和同输入轻量 JPDA。基准场景生成器不能在真实数据缺失时冒充 AirSim 结论。

### 12.2 版本化联合准入条件

候选必须同时满足：

1. 平均 IDSW 至少下降 30%；
2. 身份连续性满足 ceiling-aware error-reduction 判据：
   `H=max(0,1-C_b)`、`Delta=C_c-C_b`、
   `Delta_req=min(0.10,0.10H)`，且 `Delta>=Delta_req`；
3. 虚假航迹增幅不超过 10%；
4. 第 95 百分位（95th Percentile，P95）循环延迟不超过冻结预算；
5. 在线真值泄漏为零。

其中 `Delta/H` 表示消除基线剩余身份错误的比例。`H=0` 时不再要求超过理论上限
1.0，只接受合法且不退化的候选。缺指标、连续性越界/退化、基线 IDSW 为 0、虚假
航迹超限、延时超预算或 truth leakage 非零均逐 gate fail-closed。满足全部条件也只
生成晋级评审建议，不会由运行器自动替换默认配置。v1 固定 `+0.10` 以
`legacy/deprecated` 字段保留，但不参与 v2 判决。

### 12.3 六档压力场景

回放治理已支持：

- 标称；
- 紧密交叉；
- 连续漏检；
- 杂波；
- 延迟噪声；
- 组合压力。

压力变换只操作受治理雷达记录，不读取真值旁路，不移动目标几何。支持接口不等于六档长期真实 AirSim 数据已经全部完成。

## 13. 2026-07-13 严格 4 米/2 米结果

### 13.1 测试条件

本轮权威证据来自主收敛验证报告：

- AirSim ComputerVision（计算机视觉）模式；
- 五个目标；
- 标称相邻目标三维距离严格为 4 米；
- 紧密相邻目标三维距离严格为 2 米；
- 两种难度各 20 个种子，共 40 个真实 AirSim 回合；
- 每回合 51 帧；
- 仅离线评估器可见的真值样本共 10200 条；
- 在线真值泄漏为零。

### 13.2 结果

| 指标 | 默认基线 | 最佳 GNN 候选 | 变化 |
| --- | ---: | ---: | ---: |
| 平均 IDSW | `1.3583` | `0.6167` | 下降 `54.6%` |
| 身份连续性 | `0.9810` | `0.9840` | 提高 `0.0030` |
| P95 循环延迟 | 基线行未单列 | `24` 毫秒 | 满足冻结实时筛选预算 |

2026-07-15 已在六档冻结真实 replay/truth 上完成完整 v2 重算。基线 headroom 为
`0.018954`，所需提升 `0.001895`，实际提升 `0.002908`，即消除 `15.3448%` 的
剩余身份错误；IDSW 下降 `54.6012%`、false-track 0、P95 `15.470 ms`、baseline/
candidate truth leakage 0，因此总体五项联合 gate 全部通过并形成 promotion review
recommendation。轻量 JPDA 的 IDSW/continuity gate 失败。默认在线 GNN/Hungarian
仍不改变。

2026-07-15 的算法回归使用模块单元 fixture；证据重算则消费 2026-07-13 冻结的真实
AirSim replay/truth，未重新启动 AirSim。screening/confirmation 分别为 6x10/6x20
seeds，阶段内 digest 唯一且全部在线 truth leakage 为 0。分档只有 clutter/combined
通过完整 gate，另外四档因 baseline IDSW=0 fail-closed；dropout truth alignment 为
partial，不做最近邻补齐。

### 13.3 未晋级结论

本轮没有算法或参数候选获得主线晋级资格：

- 最佳 GNN 候选未同时通过身份连续性门限；
- 轻量 JPDA 没有表现出替换收益；
- 完整 JPDA、完整 MHT 和端到端第三方跟踪器未实现，不能用名称替代证据；
- 当前权威默认仍是门限 `9.21`、质量感知门控开启、丢失/删除阈值 `2/5`、运动权重倍数 `1.0` 的 GNN/匈牙利主线。

“IDSW 下降 54.6%”不能单独解释为密集交叉问题已解决。准入采用多指标联合约束，避免优化一个指标却损害身份稳定覆盖、虚假航迹或实时性。

## 14. 与其他模块的实施接口

### 14.1 D1 到 D2

D1 提供量测时间、到达时间、NED 状态或可投影观测、协方差、来源、谱系和可选分类提示。D2 只把合法二维位置观测送入默认关联器，不把声学方位或 EO 像素冒充北-东位置。

### 14.2 D2 到 D3

D3 消费 `global_track_id`、状态、协方差、生命周期、`track_quality` 和 `association_risk`。D3 可以对暂定、丢失或高风险航迹增加代价或延迟分配，但不能重命名目标。D2 不维护分配计划版本。

### 14.3 D2 到 D4

D2 发布软硬风险、IDSW 增量、重复解释、连续性可用性、来源节点和链路信息。D4 再结合 D1、D3、D5 和通信状态决定继续中心方案、请求重规划、请求二级辅助或降级。D2 不直接发出模式切换命令。

### 14.4 D2 与 D5

D5 使用 `global_track_id` 把中心航迹投影到局部相机图像。D5 可回传候选集合、匹配置信度、歧义和不一致，D2 可将其纳入风险摘要。D5 的本地多目标跟踪 ID 和 AirSim actor ID 均不得成为规范 ID。

### 14.5 D2 与 D6

D6 消费关联日志、状态转移、指标摘要、配置版本、离线真值评分和可用性。D2 与 D6 都必须显式保留 `id_switch_count`。D6 不能用 RMSE、覆盖率或物理拦截结果替代身份指标。

### 14.6 D2 与 D7

D7 沿用 D2/D3 传递的规范 ID 和计划上下文，不得因局部接近另一个目标而重绑身份。D2 不提供制导许可，也不使用物理接近结果反向修改离线真值。

### 14.7 main runtime

主运行时负责 AirSim 启动和重置、回合编排、`--drone-count N` 场景规模、在线受治理输入、独立离线真值文件和 D6 报告。D2 只消费受治理文件或总线消息，不直接管理 AirSim。

## 15. 实施检查与回归

### 15.1 文档对应的模块测试

```bash
PYTHONPATH=research_modules/d2_data_association \
pytest -q research_modules/d2_data_association/tests
```

2026-07-14 Post-batch 审计没有修改算法代码，但仍重新运行全量模块测试，结果为
`99 passed, 1 warning`。warning 来自本机 Matplotlib `Axes3D` 多版本环境，不影响
关联、指标或文档结论。2026-07-13 的 `93 passed` 仅是历史测试规模。

### 15.2 每次算法调整的验收顺序

1. 检查在线输入不含真值和 actor ID；
2. 检查量测时间、到达时间和协方差合同；
3. 运行模块单元测试；
4. 在冻结回放上比较默认与候选；
5. 输出逐种子 IDSW、连续性、重复解释、NIS/NEES 可用性和延迟；
6. 检查候选是否同时满足全部准入条件；
7. 由 main 和 D6 汇总，禁止模块运行器自动替换默认主线。

## 16. 当前局限与后续实施重点

### 16.1 仍属 P1 的工作

- 扩展更长的真实 OOSM、遮挡、连续漏检、杂波和延迟噪声组合回放；
- 按目标密度和漏检率冻结确认、丢失、删除和 M-of-N 评估参数；
- 按传感器、距离、场景和种子分层标定 NIS/NEES；
- 继续标定质量感知门限和风险阈值，控制软风险误报；
- 闭合跨节点注册后的 D1 数值融合回写和 D6 统计一致性评估；
- 明确二级或分布式模式下规范 ID 所有者和纪元切换合同。

### 16.2 保持隔离的 P2 研究

- 完整 JPDA 状态与协方差混合；
- 完整 MHT 假设树、分簇和 N 次扫描剪枝；
- Stone Soup 端到端跟踪对照；
- FilterPy 扩展卡尔曼、无迹卡尔曼和交互多模型对照；
- 六维路径的 main episode-bus 接入、多 seed 高密度标定与最坏情况候选预算；
- 基于风险且带迟滞的 GNN/JPDA/MHT 自动切换。

这些研究只能在冻结回放和独立可选环境中进行。在同输入、同评估、同算力预算下未证明身份收益前，不进入默认依赖或在线控制路径。

## 17. 结论

截至 2026-07-20，D2 同时保留可运行、可审计的二维兼容主线，并新增按动态输入规模工作的六维稀疏规则路径。新路径完成 NED 六维 CV、3D 马氏门控、空间候选图、分量级 GNN/匈牙利、中心 ID、在线真值隔离、风险摘要和独立离线 IDSW/连续性评分；它尚未替换旧 replay/AirSim 默认入口，也尚未形成 scalable 3D 全链路多 seed 证据。

严格 4 米/2 米、40 回合 AirSim 结果证明参数候选可以降低 IDSW，但没有同时达到冻结的身份连续性准入门限。因此当前正确实施结论是：继续保持 GNN/匈牙利为默认主线；轻量 JPDA、有界 MHT 和第三方框架只作为显式、隔离的研究对照；跨节点注册只负责规范身份和融合请求，不越权承担 D1 数值融合或 D4 模式切换。

## 18. 2026-07-14 Online/Offline Truth 实现补充

`TrackerTruthPolicy.ONLINE` 是默认策略。`Tracker.step()` 先递归验证 `Detection.truth_id`、`truth_ids_present`、Detection metadata 和 frame metadata，再执行预测与关联；检测到 truth、actor 或 object identity 时抛出 `ValueError`，且 tracker/metrics 状态保持未变。main owner 使用的 `online_truth_isolated`、`online_truth_hints_used`、`truth_metrics_available`、`continuity_available` 是例外状态键，但只接受 `bool`；字符串、payload 或其他身份承载值仍拒绝。`OFFLINE` 仅用于 synthetic simulation 和 evaluator truth 评分。

`MetricsRecorder.summary()` 对 truthless IDSW、track continuity 和 RMSE 返回 `None`，并分别提供 availability/reason；truth 存在时零 IDSW 保持 available `0`。同一 recorder 另外从 tracker 事件累计 birth/lost/drop/rebirth 和完整 transitions，不读取 truth。rebirth 的实现判据是 `lost -> confirmed|engageable`，不是 dropped 后新航迹身份重认。

2026-07-14 验证样本包括 8 类拒绝输入、main owner 四布尔状态正例、3/5 帧 truthless replay 和 7 帧 lifecycle 序列；模块验收阈值为零失败、在线拒绝无状态副作用、truthless 三字段均不返回伪零，结果 `98 passed, 1 warning`。算法参数未变，真实 `T001 -> T005` 生命周期调参继续作为 P1。

## 19. 上游来源航迹连续性与影子建轨抑制

D1 输出的 `source_global_track_id` 不是目标真值，但它是同一个上游航迹产品的稳定
谱系。D2 为每条规范航迹维护来源集合 `S_i`。对观测 `z_j` 的来源集合 `S_j`，在
原 GNN 代价上增加：

\[
C^{src}_{ij}=\begin{cases}
0,&S_i=\varnothing\text{ 或 }S_j=\varnothing,\\
0,&S_i\cap S_j\neq\varnothing,\\
1,&\text{其他情况}.
\end{cases}
\]

总代价仍由马氏距离先门控，再叠加运动代价和 `w_src C_src`，最后由匈牙利算法做
一对一分配。默认 `w_src=2.0`，它只能在门内候选之间提供连续性偏好，不能让门外
观测越过统计门限。

未匹配观测仅在两类在线安全条件下抑制 birth：一是它仍是某个活动航迹的门内候选，
说明可能是同帧影子；二是它携带已绑定活动规范航迹的来源 ID，但与绑定航迹的马氏
距离超过来源治理门限，说明上游状态发生不连续。前者延迟初始化直至候选分离，后者
隔离并等待上游恢复。输出保留 `suppressed_births`、`source_track_bindings` 和
`source_lineage_governance`，便于 main/D6 审计。

2026-07-14 的 4 帧、2 目标匿名回归加入 1 条近邻影子和 1 次来源 teleport，要求
活动规范 ID 始终为 2、影子抑制和隔离各发生 1 次、truth 使用为 0；结果通过，模块
全量为 `99 passed`。该测试不证明真实多目标近距初始化参数已完成标定；同 seed
AirSim 复跑已完成，后续普通 M5N2 又完成 20 case，但没有显式来源扰动和该批离线
身份评分。合法新目标初始化延迟、重复来源与 teleport 仍需专项统计。

## 20. Post-batch 真实 M5N2 复核

2026-07-14 的 baseline/candidate seed 1 分别包含 142/141 帧。在线 D2 在启动后
140/139 帧内都只输出 `T001/T002`，且 `birth/lost/drop/rebirth=2/0/0/0`。GNN
matched pair 总数分别为 278/276，只有最初两条 detection 进入 birth；之后没有
unmatched active track，也没有 `T008`。

在线摘要保持 IDSW/continuity unavailable。离线 sidecar 的作用域是 evaluator-only：
现有 governed replay API 对两组均报告 IDSW 0、continuity 1.0；对实际发布的 track
records 做独立匈牙利裁决时 continuity 为 0.985915/0.985816，因为最初两帧还没有
D1/D2 航迹。两种口径都证明没有身份交换，但前者是重新运行 governed replay，后者
是对总线发布结果的事后评分，文档和报告不得混用。

本批 `suppressed_births`、quarantine 和 source conflict 均为 0。算法因此没有新增
修改：继续保持来源连续性只在原马氏门内参与代价，teleport 超门限 fail-closed，
canonical `global_track_id` 不由来源 ID 或离线 truth 改写。2026-07-15 的普通 M5N2
20-case 已补齐时延和运行数量；下一步只做带独立离线真值的扰动专项，不因单 seed 或
无真值多 seed 结果调整默认 GNN/Hungarian。

## 21. 来源治理诊断的显式累计实现

`Tracker.step()` 仍先做在线 truth/identity policy 与来源连续性治理，再调用原
GNN/Hungarian。关联完成后，D2 在 `AssociationResult.metadata` 中规范化输出：

- `source_binding_conflicts`：一个 namespaced source 已绑定活动 canonical track，
  却又随本帧匹配尝试绑定另一个 canonical track；
- `quarantined_sources`：已绑定 source 与其 canonical track 的 Mahalanobis distance
  超出原来源治理门限；
- `upstream_local_identity_rejection_count`：上游在本帧已拒绝的局部身份塌缩数量。

`MetricsRecorder.record_frame()` 对前两个列表取条目数并跨帧累加。第三项不从 Detection
metadata、association metadata 或 local ID 反推，而只从传给 `Tracker.step()` 的
frame metadata 读取。验证伪代码为：

```text
if key missing: count = 0
elif type(value) is an integer-like non-bool and value >= 0: count = value
else: reject frame before predict/associate/update/birth
```

逐帧 `AssociationRiskSummary` 输出当前滑窗计数和 delta；episode metrics/risk 输出累计值；
threshold sensitivity、multi-seed group、dense/long replay calibration 与 P1 identity
calibration 输出逐 seed 和分布聚合。三项没有加入 `RiskThresholds` 或
`classify_risk_summary()` 的 hard/soft 判定，因此不会隐式改变现有仲裁门限。

2026-07-16 单元/回放验证使用连续 source、双 canonical binding conflict、绑定 source
teleport、零观测 upstream audit、5 类非法值和 legacy 缺失字段。两个 3-frame replay
seed 7/8 精确得到 conflict=`1/1`、quarantine=`1/1`、upstream rejection=`2/4`；
多 seed 均值为 `1/1/3`。全量 `123 passed, 1 warning`，验收阈值为零失败、非法输入
零状态副作用。默认 GNN/Hungarian、gate、source weight 和 lifecycle 均未变化；未运行
AirSim，真实扰动召回率与误抑制率仍不可用。

## 22. 六维稀疏全局最近邻路径

### 22.1 状态、预测与三维创新

六维路径使用状态

\[
x=[p_N,p_E,p_D,v_N,v_E,v_D]^T,
\]

常速度转移矩阵为

\[
F(\Delta t)=\begin{bmatrix}I_3&\Delta t I_3\\0&I_3\end{bmatrix},
\]

过程噪声采用三轴独立白加速度离散形式。位置量测矩阵为
`H=[I_3,0]`，创新、创新协方差和门控距离分别为

\[
r=z-H\hat{x},\qquad S=HPH^T+R,\qquad d^2=r^TS^{-1}r.
\]

默认门限 `11.344866730144373` 是三自由度 99% 卡方门限。速度只以封顶代价进入门内
tie-break，不把 gate 改成六维创新，也不因速度离群拒绝位置门内 pair；因此文档、日志
和测试固定输出 `innovation_dimension=3` 与
`gate_metric=3d_position_mahalanobis_squared`。

状态更新按输入统计语义分三类：位置-only 量测使用 `H=[I_3,0]` 的 Joseph update；明确
独立的六维量测使用 `H=I_6` 的 Joseph update；D1 fused-track 是已使用历史量测形成的
source posterior，和 D2 预测之间的相关性未知，必须保留其完整 6x6 covariance 并走
covariance intersection。D1 adapter 不读取或复制上游 `global_track_id`，也不丢弃
position-velocity cross block。

### 22.2 空间索引与稀疏 Hungarian

对第 `i` 条预测航迹，设其位置协方差最大特征值为 `lambda_i`，本帧所有量测位置
协方差最大特征值上界为 `lambda_z`。KD-tree 查询半径取

\[
r_i=\sqrt{\gamma(\lambda_i+\lambda_z)},
\]

其中 `gamma` 为马氏门限。若某边满足 `d^2<=gamma`，则其欧氏残差必不超过该保守
半径，因此正常半正定 covariance 下不会因空间预筛漏掉门内边。查询结果再执行精确
3D 马氏门控，形成二部候选图。

候选图按连通分量拆分，每个分量使用 `scipy.optimize.linear_sum_assignment`。不同分量
之间没有可行边，因此分量最优解之和等价于整个稀疏候选图上的全局最近邻解。实现不
创建或持久化无条件 `N_t x N_z` cost/distance matrix；仍输出潜在全对数、空间查询边、
门内候选边、局部分量矩阵元素和 peak component 大小供预算审计。极端全重叠目标会
形成大分量，故稀疏性是数据相关性质，不是无条件复杂度保证。

### 22.3 身份、风险与真值边界

`Detection3D` 没有 truth 字段，metadata 递归拒绝 truth/actor/object/entity 和上游
canonical identity。`Scalable3DTracker` 是 `GT3D-*` 的唯一创建者；D1 六维对象的
`global_track_id` 被 adapter 忽略，namespaced source key 只能作为连续性弱证据。

在线结果显式记录：

- `id_switch_count=None` 和 `id_switch_count_available=false`；
- `track_continuity=None` 和 continuity unavailable；
- `AssociationRiskSummary` 中的候选重叠、cost margin、漏配率、风险分值和稀疏统计。

`Sparse3DOfflineEvaluator` 是单独模块，只接收已完成的 `AssociationResult` 和外部 truth
sidecar，计算 IDSW、identity/coverage continuity、duplicate 和 false-alarm assignment。
truth 结果不回写 tracker、候选图、ID binding 或风险代价。

### 22.4 2026-07-20 验证

原六维专项 13 个，加 3 个速度稳定性专项，覆盖 5/20/50/100/200、D 轴门控、三维
交叉、两帧漏检、15 个虚警、truth 拒绝、上游 ID 非权威、history/log 上限、完整
covariance 和速度离群值；完整 D2 为 `139 passed, 1 warning`，验收阈值零失败。
200 目标规则网格执行 3 个独立 trial，每个
trial 预热 1 帧后测量 30 帧；90 个测量帧的候选边均为 `200/40,000`，候选裁剪率
`99.5%`，聚合关联/tracker-step P95 为 `7.056/26.797 ms`，max 为
`22.471/41.613 ms`。该结果仅是当前主机、单进程、确定性合成布局的工程证据，包含
系统调度尾值，不代表实时 SLA、AirSim、200v200 全链路或多 seed 置信区间。

### 22.5 相关六维 posterior 更新与速度模型门控

设预测状态/协方差为 `(x_p,P_p)`，D1 source posterior 为 `(x_s,P_s)`。在不知道两者
交叉相关的情况下，当前实现使用 covariance intersection：

\[
P_{CI}^{-1}=\omega P_p^{-1}+(1-\omega)P_s^{-1},
\]

\[
x_{CI}=P_{CI}\left(\omega P_p^{-1}x_p+(1-\omega)P_s^{-1}x_s\right).
\]

当前 `correlated_state_ci_track_weight=0.5`，即 `omega=0.5`。这是保守、确定性的工程
baseline，只证明当前专项下不再重复消费相关 posterior；没有多 seed 优化、置信区间或
最优性证明，文档和报告不得写成“最佳权重”。该 CI 只处理 D1 source posterior 与 D2
预测的时序相关性，不代表跨节点多 source 的数值融合已经从 D1 移交给 D2。

速度创新和归一化创新平方为

\[
\nu_v=z_v-\hat v,\qquad S_v=P_{vv}+R_{vv},\qquad
\eta_v=\nu_v^TS_v^{-1}\nu_v.
\]

当 `eta_v` 超过三自由度 99% 门限 `gamma_v=11.344866730144373` 时，令
`alpha=max(1,eta_v/gamma_v)`，并用
`D=diag(1,1,1,sqrt(alpha),sqrt(alpha),sqrt(alpha))` 形成
`R'=D R D^T`。该相似变换同时保留并一致缩放 position-velocity cross block，再用
`R'` 做 CI/Joseph update。关联速度代价为
`w_v min(eta_v,gamma_v)`，所以速度仍可打破交叉平局，但不会无限主导位置门内分配。
这些规则没有读取 truth/actor/object ID，也没有设置速度模长上限。

2026-07-20 的 seed 17、50 条、12 帧合成回归中，输入速度 P50/P90/max
`5.415/7.960/12.274 m/s`，旧 position-only 重复更新复现
`9.41/14.31/21.88 m/s`、Pvv trace `62.76`；新路径输出
`5.082/6.401/7.218 m/s`、trace `101.181`，位置 RMSE
`52.634 -> 48.364 m`，离线 IDSW 0、continuity 1.0。seed 41 的 200 条、10 帧回归
保持每更新帧 `200/40,000` 候选/全对，输入/输出速度 P90 `8.097/5.980 m/s`，IDSW 0、
continuity 1.0。seed 29 双目标交叉中的速度离群值触发 update NIS gate 和有限速度
代价后仍保持 IDSW 0。

剩余统计一致性验收包括：至少 20 个未见 seed 的 CI weight sweep；按 covariance 结构、
量测周期和机动强度报告在线 velocity NIS coverage；仅在隔离 offline truth state 可用时
报告六维 NEES coverage；补充持续加速度、协调转弯、漏检和 main 修复后 50v50/200v200
端到端复跑。当前合成结果不能替代这些标定。

## 18. Scalable 3D evaluator-only 身份映射

### 18.1 输入与哈希边界

`Scalable3DIdentityEvidenceBundle` 使用
`d2.scalable3d_identity_evidence.v1`。每条
`GlobalTrackLineageEvidence` 对应一个 frame/global track，包含：

```text
episode_id, frame_index, frame_timestamp,
global_track_id, lifecycle_state, association_state,
source_observations[observation_id, measurement_timestamp,
                    source_lineage, replay_generation],
d1_record_sequences, d2_record_sequence
```

这些字段全部 truth-free。bundle 绑定 `online_d1_records`、`online_d2_records` 和
`observation_truth_labels` 的 SHA-256；episode manifest 另存 bundle 自身 SHA-256。
`evaluate_scalable_3d_identity_files()` 先核验四个文件 hash，再严格核验 D1/D2 schema、
record sequence 和递归在线 identity 隔离。sequence 引用还必须语义绑定对应 D1
observation lineage，以及 D2 record 中同 frame、同 D2-owned `global_track_id` 的六维
`state_ned`、`6x6 covariance`、lifecycle、association 和 source observations；evidence
必须覆盖被持久化的完整 D2 track-frame 集合。状态/协方差只用于证明来源记录合同完整，
不进入 truth identity 选择。现有 producer
`scalable3d-offline-truth-v1` 的 `truth_entity_id` 仅在 loader 中规范化为 evaluator 的
`truth_target_id`，包含 `global_track_id` 或未知身份字段的 sidecar 被拒绝。

### 18.2 逐帧映射算法

对每个 source ref，evaluator 要求 `source_lineage[-1] == observation_id`，并用
observation ID 精确索引 truth label；label timestamp 必须与 ref timestamp 在容差内，
ref 不得来自未来且不得超过配置的 lineage window。算法不读取状态位置或目标名称。

同一 track 的全部有效 ref 只支持一个 truth 时 mapping available。多个 truth 候选、同
lineage/observation 被多个 track 声明、冲突 label 或 replay payload 冲突时 ambiguous；
缺 lineage/label、时间窗不符、未标记 replay、非法 lifecycle 时 unavailable。显式
replay 必须在原 lineage 后使用更大的 generation。同一 truth 被多条 track 通过不同
observation 支持时保留全部 mapping，随后计入 duplicate，不用一一 Hungarian 消掉。

输出 `d2.scalable3d_global_track_truth_mapping.v1`，逐 frame 含 mapping status、truth
候选、source observation IDs、lineage hashes、evidence/labeled/replay/duplicate 数量和
原因计数。顶层 evaluation 同时保留四类 source hashes 与禁止使用的 identity heuristic
审计。

### 18.3 指标口径

`d2.scalable3d_identity_metrics.v1` 按 frame evidence 的持久化顺序选择每个 truth 的
first assignment，和 `MetricsRecorder` 相同：

- 前一可见 frame 的 representative track 改变，`id_switch_count += 1`；
- 首次或保持同 representative 的 frame 计入 stable frame；
- `identity_continuity` 为各 truth 的 `stable_frames / present_frames` 均值，
  `track_continuity` 是同义字段；
- `coverage_continuity` 为各 truth 的 `assigned_frames / present_frames` 均值；
- 同 frame 同 truth 的额外 unique track 累计
  `duplicate_truth_to_track_count`，并映射为兼容字段 `duplicate_assignment_count`。

任何影响身份的 mapping 不完整都会使上述值和 confusion matrix 全部为 `None`，同时输出
availability/reason；已知存在 truth frame 但无 assignment 时的可验证 0 除外。专项测试
直接与 `MetricsRecorder` 对照 IDSW、continuity 和 duplicate 数值。

### 18.4 兼容与限制

旧 `Sparse3DOfflineEvaluator` 的内存 sidecar 接口继续兼容；新文件合同供 main/D6
持久化接线使用。在线 `Detection3D`、`GlobalTrack3D`、association result、门限和默认
GNN/Hungarian 没有改动。当前 main producer 仍跳过无 source lineage 的 D2 track/frame，
必须补齐 unavailable/unassigned evidence 后才满足完整性校验。当前只有合同/合成回归，
不是正式多 seed 身份性能结果。

## 19. 2026-07-22 重放隔离和强证据合并

### 19.1 输入分区

`Scalable3DTracker.step()` 先从每条六维 D1 posterior metadata 读取
`latest_observation_id`、`latest_sensor_id` 和 `source_measurement_timestamp`。组合键

```text
observation_key = sensor_namespace + "::" + latest_observation_id
```

只作完全相等比较，不解释字符串内容。首次出现的 key 进入关联；已消费 key 的后续
posterior 进入 quarantine。若同 key 的源量测时间变化超过 `1e-6 s`，原因记为
`observation_identity_timestamp_conflict`。没有该 metadata 的旧调用保持兼容，但
`observation_freshness_unavailable_count` 会显式增加。

隔离发生在 KD-tree 和 Hungarian 前。被隔离 posterior 不参与候选边、不更新状态、
不增加 hits，也不写入 `detection_to_track`。每条事件保留 observation ID、传感器
namespace、源量测/状态有效/到达时间、首次 detection、已声明中心航迹、D2 本地计算的
replay generation 和 `online_truth_used=false`。

### 19.2 tentative 删除

默认 `confirmation_hits=2`，`tentative_drop_miss_threshold=2`。一次漏配后的 tentative
仍可由新 observation 恢复，但连续第二次没有新证据时直接 dropped；已确认航迹继续按
`lost_miss_threshold=2`、`drop_miss_threshold=5` 处理。该规则没有把 detection 序号、
场景目标数或离线 truth 用作条件。

### 19.3 航迹合并

两个活动航迹只有满足以下全部条件才进入合并：

1. 共享至少一个已消费 observation key 或 namespaced source-track key；
2. 本帧没有双方同时获得不同的新鲜 observation；
3. `delta_p` 在 `Pp_i + Pp_j` 下的三维马氏距离不超过 99% 卡方门；
4. `delta_v` 在 `Pv_i + Pv_j` 下的三维马氏距离不超过同一门。

survivor 排序为 `engageable > confirmed > tentative > lost`，同级选择创建更早、hits
更多、misses 更少、ID 字典序更小的航迹。survivor 的 ID 不变；重复航迹转 dropped。
两条状态使用固定 0.5 权重协方差交叉，hits/consecutive hits 取最大值，source 和
observation claims 转移到 survivor，不对相关信息求和。

### 19.4 审计输出

逐帧 metadata 新增 fresh/unavailable/replay 数量、`replay_quarantine_events`、
`duplicate_coalescence_events`、suppressed births、survivor policy 和 tentative 门限；
tracker summary 累计 replay quarantine、timestamp conflict、tentative stale drop、
observation claim 和 coalescence。在线 `id_switch_count` 仍为 `None` 且 availability
为 false，离线 evaluator 口径不变。

2026-07-22 的 seed 1005 真值隔离复现使用 5v5 active-risk、2.2 s、10 个 D2 帧，
航迹数为 `5,6,6,5,5,5,5,5,5,5`，replay quarantine 9、tentative stale drop 1、
coalescence 0、online truth use 0。完整 D2 测试 `168 passed, 1 warning in 26.15s`。

### 19.5 main 总线和 20-seed 验证

main 已把逐帧与累计审计包装为 `d2-observation-evidence-governance-v1` 并持久化，字段
覆盖 fresh/replay、timestamp conflict、coalescence、suppressed births 和 tentative
stale drop。2026-07-22 的脏工作树 development rerun 使用 seeds 1000--1019，D6 七类
证据 availability 均为 20/20；seed 1005 离线 identity 为 GT1-GT5 五条唯一映射，在线
truth use 0。随后提交 `0fa7c00` 的 clean-tree 复跑记录 `repository_dirty=false`、源提交
统一、20 个 pair、D4 adoption 188/188、两臂各 1960 条命令和 100 条离线唯一映射。
1 s 计划窗内两臂均无 5 m 拦截；counterfactual、causal、production runtime ACK 仍
unavailable。该结果关闭 clean 复跑缺口，不是算法参数 promotion 或拦截效果证据。

## 20. 有界 claim ledger 与整帧 OOSM

### 20.1 两个时间水位线

配置 `ObservationClaimLedgerConfig` 包含 schema/config version、保留时间 `T_r`、最大
claim 数 `C_max` 和最大迟到 `T_l`。Tracker 状态时刻为 `t` 时，观测接纳边界为

```text
W_admit = t - T_l
```

源量测时刻严格早于 `W_admit` 的新 key 不进入候选图。claim 的安全淘汰边界为

```text
W_evict = t - max(T_r, T_l)
```

只有源量测时刻严格早于 `W_evict` 的 claim 可删除。因 `W_evict <= W_admit`，已删除 key
携带原旧量测时间再次到达时，仍会在字典查询前被 admission watermark 拒绝。实现不保存
无限 tombstone；防重放依赖带命名空间的 observation ID、可信且不可回退的源量测时间，
以及 main/DDS 层对消息完整性的保证。缺少源量测时间的 claim 不淘汰，容量满后新 key
按 `observation_claim_ledger_overflow` 拒绝。

### 20.2 内存与运行复杂度

claim 字典最多 `C_max` 项，按 track 组织的 observation key 总数不超过 resident claims，
淘汰最小堆最多保存每个有时间 claim 一项。常驻声明内存为 `O(C_max)`。每次有时间 claim
写入和淘汰为摊销 `O(log C_max)`；一次 scan 的声明分区为 `O(M log M)` 的确定性 key/
detection 排序加 claim 操作，其中 `M` 为本帧观测数。淘汰 key 时同步删除 track 反向索引，
不会由历史 episode 长度继续增长。

### 20.3 拒绝原因与审计

逐帧 `AssociationResult.metadata` 输出：

- `observation_rejection_reason_counts` 与累计版本；
- `replay_quarantine_events`；
- `observation_claim_ledger`；
- 本帧 eviction count/events。

原因至少区分 `observation_measurement_too_old`、
`observation_identity_timestamp_conflict`、`repeated_latest_observation_id`、
`duplicate_observation_within_scan` 和 `observation_claim_ledger_overflow`。summary 的 ledger
包含 current/peak/evicted、overflow/too-old/replay、admission/safe watermark、undated、
eviction index、track observation key/index count、`tombstone_count=0`、配置版本和
`online_truth_used=false`。

### 20.4 整帧 OOSM 边界

`Scalable3DOOSMScanAdapter` 是 Tracker 前置排序器。每次 submit 接收一个共同 state-valid
measurement epoch 的完整 scan，arrival time 表示该 scan 已完整到达。适配器以
`latest_arrival - max_lateness` 作为释放水位线，从最小堆按 measurement time 释放 0 到
多帧。超过 max-lateness、早于已释放 Tracker state、arrival 回退或 buffer overflow 的
scan 整帧拒绝。Tracker `step()` 始终按非递减时间调用。

`flush()` 只表示 episode 输入终止，把仍在迟到窗内的 scan 排序排空。它不允许在 episode
中周期调用来绕过 max-lateness，也不做固定滞后回溯、状态重放或平滑。adapter summary
输出 submitted/admitted/released/rejected、current/peak scan/detection buffer、measurement inversion、
逐原因累计值、arrival/release/state 时间和 `rewind_or_fixed_lag_smoothing=false`。

### 20.5 离线治理基准

`run_observation_governance_benchmark()` 先用匿名检测运行 online Tracker，再把独立 truth
label 交给 `Sparse3DOfflineEvaluator`。truth 不进入检测 metadata、候选生成、Hungarian、
生命周期或 claim ledger。公开报告字段包括合法检测数、false suppression 数/率、近邻
独立目标 recall、错误 coalescence、逐 truth confirmation latency、离线 IDSW/continuity
和 ledger summary。

2026-07-22 的确定性 3/12 目标、16 帧、0.75 m 间距测试分别含 43/187 条合法检测，误抑制
0、召回 1.0、错误合并 0、确认延迟均值/P95 0.25/0.25 s、离线 IDSW 0。5 目标 x 500 帧
和 40 目标 x 200 帧循环的 peak/current 均不超过 `6N`，overflow 0 且发生安全淘汰。
新增 15 个测试后完整 D2 为 `183 passed, 1 warning in 29.08s`。

上述结果关闭模块内有界账本、显式整帧排序边界和确定性误抑制基准。真实 AirSim、多规模
多 seed、时钟漂移、ID 唯一性、遮挡/杂波和最坏大连通分量仍需标定，不能据模块 fixture
声称 200v200 完整验收。

## 21. 重复后验的有界预测 coast

设当前统一状态时刻为 `t_k`，航迹最后一次接受新鲜量测的时刻为 `t_u`，版本化宽限为
`G`。重放 detection 先按原规则进入 quarantine。只有以下条件同时成立时，航迹本帧免计
一次 miss：拒绝原因为 `repeated_latest_observation_id`；claim 已绑定该现存非 dropped
航迹；同航迹本帧没有时间冲突等其他拒绝；且 `0 <= t_k-t_u <= G`。

coast 帧仍执行常速度预测和协方差传播，以保持 Tracker 状态时刻单调。它不执行量测
Joseph 更新或协方差交叉，不修改 hits、misses、last detection 和 `last_update_time`，也
不允许 quarantined detection 形成 birth。后续 replay 始终使用同一个 `t_u` 计算年龄，
因此 `t_k-t_u > G` 后恢复 miss。持续重放不能延长宽限。

`ReplayCoastConfig` 公开 schema/config version、grace、时钟来源和
`refresh_on_replay=false`。每帧输出 coast event、track、reason、age、grace 和实际 miss；
summary 累计 coast count/reason。候选 coast 只使用本帧 quarantine 事件，额外临时复杂度
为 `O(Q)`，其中 `Q` 为本帧拒绝数；没有新增随 episode 长度增长的容器。

## 22. 在线库存与集成验收

设冻结干预时刻的在线 D2 活动航迹集合为 \(\mathcal{T}_k\)，仿真离线目标集合为
\(\mathcal{G}_k\)。在线合同只允许由观测证据构造 \(\mathcal{T}_k\)，因此一般只能要求
\(|\mathcal{T}_k| \le |\mathcal{G}_k| + N_{FA}\)，其中 \(N_{FA}\) 是在线可能形成的虚警
航迹数。不能直接要求 \(|\mathcal{T}_k|=|\mathcal{G}_k|\)。是否漏检、虚警或身份错误只能
在关联结束后通过隔离 truth sidecar 评分。

当前 seed 1005 的 1.1 s 运行产生 1 个常规 D2 帧和 1 个 finalize D2 帧，每帧均为
GT1-GT5 五条规范中心航迹。最终累计 birth 5、claim 10、replay quarantine/coast 0、
stale drop 0、coalescence 0；finalize 只调用 D2 一次并合并 5 条尾部释放，不用于控制。
seed 1011/1019 的 1.0 s 干预快照各为 4 条航迹，因为首个雷达扫描各漏检一目标，后续
观测在干预时刻之后到达。两例最终均为 5 confirmed。

main 验收应使用三个独立关系：D2 在线库存与 D3 匿名目标库存等长；在线目标桥覆盖 D2
库存且不改写规范 ID；离线 truth mapping 单独携带可用性。发布次数和航迹数不再由固定
5v5 序列断言。复现脚本采用 `d2.active-risk-seed1005-reproduction.v3`：允许 replay=0
或有界 replay，同时强制五条规范中心航迹、birth 5、coast/quarantine 一致、无 stale
drop/错误合并和在线 truth 0。当前完整 D2 测试为 `189 passed, 1 warning`。

## 23. formal/clean 多规模治理证据

2026-07-22 在提交 `e4d66db02a0b8f1b867a0e81b4a73de84588426b` 上运行
20/50/100/200 四个规模，每档 5 个 seed。全部 20 个 manifest 都是
`evidence_tier=formal`、`repository_dirty=false`，并绑定同一源提交。校准输入清单对
manifest、online audit 和 evaluator sidecar 分别登记 SHA-256；60 个关键文件的
逐个重算结果全部一致。

claim peak/capacity 随规模依次为 2390/4800、6020/12000、12070/24000 和
24170/48000。安全淘汰数依次为 285、735、1485 和 2985，说明 30 s retention
水位线已在长 episode 内实际激活；overflow 和 too-old 均为 0。离线 evaluator-only
侧近邻召回率为 1.0，误抑制率和错误合并率为 0，确认延迟均值/P95 为
0.25/0.25 s。所有 sidecar 均标记 evaluator-only 且未被在线路径消费，在线真值使用为 0。

该运行验证的是已有 claim ledger、安全淘汰和离线指标合同在 clean 来源上的多规模行为，
没有改变 GNN/Hungarian、门控、coast、生命周期或中心 ID ownership。它是受控质点治理
benchmark，不是完整融合、真实 AirSim、多场景 IDSW/连续性、实时服务等级或物理拦截验收。

## 24. 200 规模身份审计热路径

### 24.1 处理顺序

六维在线输入仍按以下顺序处理：递归检查 metadata 中的真值/外部身份键，校验状态、
协方差和时间，进入 observation claim 分区，再执行 KD-tree 候选生成、三维马氏门控、
分量级 Hungarian、状态更新和生命周期推进。本轮没有改变上述顺序。

原 D1 adapter 在创建 `Detection3D` 前递归扫描一次 metadata；`Detection3D.__post_init__`
随后执行相同完整扫描。adapter 预扫描没有产生额外状态或审计字段，因此删除后，非法
metadata 仍在对象构造时以相同异常拒绝。Tracker step 保留第三方可能在构造后修改对象
时的再次审计。

### 24.2 有界分类缓存

禁用键判定只依赖归一化后的字符串。实现把字符串归一化和禁用键分类分别放入
`lru_cache(maxsize=1024)`。缓存值是字符串或布尔值，不含量测、航迹、声明或真值对象。
容量固定，最坏常驻项数不随 episode 长度增长。域名前缀和身份后缀判定使用 Python 原生
元组形式的 `startswith`/`endswith`，与原生成器 `any()` 的分类结果等价。

专项测试保留旧分类器作为测试参考，对真值键、actor/object/entity/target/AirSim 身份键、
中心 ID、合法 observation/source/audit 键和嵌套容器执行新旧结果对照。另有回归验证
D1 adapter 仍拒绝嵌套 `truthId`，Tracker 仍拒绝构造后注入的身份 metadata。

### 24.3 性能与语义比较器

`scalable_3d_performance.py` 从两侧 episode 读取 D2 topic、阶段计时、场景配置和离线真值
sidecar。运行时计时不进入在线语义哈希。对每个周期生成完整记录哈希，并分别生成关联、
规范 ID/生命周期、claim/审计域哈希。场景配置或 sidecar 文件哈希不一致时，
`semantics_equal` 为 false。

五 seed、45 周期对照中，全部域哈希一致。常规关联平均累计墙钟
`7.5552 -> 2.2033 s`，finalize `2.2747 -> 0.5646 s`，单 episode D2 合计
`9.8299 -> 2.7679 s`。该比较器验证发布语义等价，不证明不同输入上的轨迹身份正确性；
后者仍需隔离 truth evaluator 给出 IDSW/continuity availability。

## 25. 长时元数据批审计与合同投影

`detections3d_from_d1_global_tracks()` 先把输入固化为一批 metadata。批审计遍历所有顶层
键和非共享容器。对 `sensor_health`、`association_audit`、`latency_audit` 三类 D1
批内共享诊断，维护本批已完整审计的代表值；只有完全由可信内置容器和标量组成、无循环
且内容相等时才跳过重复递归。未知或自定义 Mapping 不进入代表缓存，即使其 `__eq__`
恒为 True 也必须完整审计。内容不同同样完整审计。代表集合只在一次函数调用内存在，
不跨批缓存，也不持有航迹状态。

全部输入通过后，适配器投影到 D2 在线合同字段。投影保留 measurement/arrival/published
时间、observation/detection/scan 标识、source node/track、modality、frame 和 lineage。
位置、速度和 6x6 协方差仍直接来自 D1 对象，不从 metadata 重建。D1 的大型健康和融合
诊断不进入每个 `Detection3D`，避免其大小乘以航迹数和周期数。

安全检查有三层：批输入检查全部原始 metadata；`Detection3D.__post_init__` 检查投影后
对象；`Scalable3DTracker.step()` 检查构造后可能发生的修改。测试验证共享内容复用、
单轨变体中的嵌套 `truth_id` 拒绝、上游 `global_track_id` 忽略，以及 48 周期参考/候选
状态、关联、claim 和生命周期语义一致。恶意自定义 Mapping 的第二项包含 `truth_id`
时继续 fail closed。

## 26. 关联内核批处理与可信复用

### 26.1 候选生成

`Sparse3DGNNHungarianAssociator.associate()` 将全部 detection 位置组成一个 KD-tree，并对
本周期所有航迹的 3x3 位置 covariance 批量调用 `eigvalsh`。每条航迹仍使用原公式
`sqrt(gate * (lambda_max(track) + max_detection_variance))` 和原最小半径；
`query_ball_point` 只由逐航迹调用改为向量调用，返回索引仍排序。候选随后逐条执行原
3D innovation covariance 和马氏门控，不截断结果。只有连通分量为 1x1 时直接选择其
唯一已门控边；其他分量仍调用 `linear_sum_assignment()`。

### 26.2 Innovation 与 covariance 复用

稀疏边保存关联阶段已经计算的 velocity NIS。关联器返回私有
`_SparseAssociationResult`，其 `matched_velocity_nis` 不在继承的公开 serializer 中；
Tracker 只在紧随其后的匹配更新使用该值。外部提供普通 `AssociationResult` 时仍执行原
计算。

D1 adapter 先完整治理 6x6 covariance。consistent 结果由内部
`_detection3d_from_governed_d1_track()` 在对象初始化前预置，且要求与传入
`state_estimate_covariance` 为同一 ndarray；对应 dataclass field 为 `init=False`，普通
构造签名无法传入。若第一次治理发生 regularization，则 adapter 使用普通构造，保留原
第二次 full governance。CI posterior 同样只复用本函数刚产生的 consistent diagnostics；
regularized 情况继续调用 `ensure_covariance_consistency()`。

### 26.3 验证器

`scripts/run_scalable_3d_association_hotpath_benchmark.py` 从冻结 online bus 中恢复 D1 输入、
claim/replay 状态和 48 个 D2 周期，不读取 truth sidecar。每周期与冻结 D2 输出比较公开
航迹、匹配/未匹配、ambiguity、候选数、claim ledger 和 coalescence，并对完整 tracker/
result 状态计算去除计时字段后的 SHA-256。报告同时固定 dense pair、空间候选、位置和
速度 innovation 求解、边、分量及匹配数量。

普通构造负例提供 3x3 位置/速度单位阵和 2 倍单位交叉块；两个 marginal 均正定，但 6x6
矩阵非 PSD。即使传入伪造的 public consistency 字典，构造仍在 full covariance
governance 中拒绝；旧的私有预验证关键字现在直接触发 `TypeError`。公开 DTO 和
`to_dict()` 未增加字段。

## 27. 三 seed 集成等价验证

### 27.1 验证输入

main 使用 reference `8f86192` 和 candidate `f80b5bd` 的独立 clean worktree，固定
nominal 200v200、10.0 s 和 seeds 42000/42001/42002。每个 episode 的 D2 association
均调用 47 次。两侧按同一 seed 比较，在线路径不读取 truth sidecar，三组
`online_truth_use_count` 均为 0。

### 27.2 优化边界

候选把同一周期的 covariance 最大特征值和 KD-tree 查询合并为批处理。已经为匹配边
计算的 velocity innovation 由紧随其后的更新复用；D1 adapter 刚完成且结果为 consistent
的 covariance governance 才能在内部复用。发生 regularization 或无法证明可信时仍执行
完整 6x6 检查。只有候选图连通分量为 1x1 且唯一边已经通过全部门控时才绕过
`linear_sum_assignment()`。这些处理不改变查询半径、候选排序、合法边、状态更新或
`global_track_id` 所有权。

### 27.3 跨提交审计

main 的审计器逐条比较在线 topic 载荷和 topic counts。D3 独立运行产生的随机
`plan_id` 按计划出现顺序和 version 规范化，原始 ACK 载荷 SHA 在规范化前校验；owner、
version、coalition、`global_track_id` 和 command 业务字段保持精确比较。D2 在线记录
无需该规范化，三组语义比较均通过。

D2 association 累计耗时三 seed 均值为 `8.317513 -> 7.671266 s`，减少约 `7.77%`；
终态航迹数依次为 `205/204/203`，两侧相同。该验证证明 nominal 三 seed clean 集成
非退化。短长对照仍将 D2 association 列为超线性，因此实时预算和困难场景标定尚未完成。

## 28. 部分身份诊断算法

### 28.1 映射分类

评估器先保留逐帧 mapping 的原始 `available/ambiguous/unavailable` 计数。身份评分集合
只取 association state 为 `created` 或 `matched` 的映射。映射同时满足以下条件时记为
可评估：

1. mapping status 为 available；
2. 只有一个 `truth_target_id`；
3. 该真值出现在本帧 truth-presence 时间窗。

映射覆盖率为可评估映射数除以受评分映射数。受评分集合为空时，值和 availability 分别为
`None/false`，原因固定为 `no_scored_identity_mappings`。缺失计数只覆盖
`source_lineage_missing`、`truth_label_missing` 和
`truth_mapping_evidence_unavailable`；其他时间、生命周期和冲突原因仍保存在 reason
counts，不混入缺失数。

### 28.2 帧和转移

完整可评估帧要求 truth presence 非空，且本帧每条受评分映射都可评估。帧内一个真值有
多条有效航迹时，两类指标采用不同处理。strict metrics 继续使用已冻结的“持久化证据
顺序第一条”为代表航迹，并保留 duplicate 语义。部分下界不复用该代表：只有某真值帧
恰好存在一个唯一可评估 `global_track_id` 时才建立锚点；存在两个及以上唯一航迹时排除
该真值帧，并按
`multiple_evaluable_global_tracks_for_truth_frame` 计数。该排除按真值帧计数，不按
映射条数计数；即使同帧另有缺失或歧义证据，也保留重复映射排除审计。

对每个真值按帧序列建立两种转移：

- 转移机会数为真值存在帧数减一；
- 相邻可评估转移要求相邻真值存在帧都为完整可评估帧，且该真值在两端各有一个唯一锚点。

IDSW 下界使用连续唯一锚点。若两端唯一航迹 ID 不同，则该不相交时间区间至少发生一次
切换。公式为

\[
L_{\mathrm{IDSW}} =
\sum_u \sum_{j=2}^{K_u}
\mathbf{1}\!\left[g_{u,j} \ne g_{u,j-1}\right],
\]

其中 \(g_{u,j}\) 是真值 \(u\) 的第 \(j\) 个唯一锚点航迹，\(K_u\) 是锚点数。每个求和
区间互不重叠，端点唯一且 ID 不同，因此每项 1 至少对应一次身份变化。重复映射帧没有
唯一端点，不能证明发生切换，也不能贡献下界。当所有 \(K_u<2\) 时，下界 unavailable。
当前不计算上界，因为缺失侧车不能证明完整真值基数和所有转移机会。

### 28.3 序列化与防篡改

`partial_identity_diagnostics` 是 evaluation v1 的可选附加块，schema 为
`d2.scalable3d_partial_identity_diagnostics.v1`。旧 evaluation v1 无该块时仍可读取；
新 producer 始终写出。loader 校验状态计数总和、评分分类总和、coverage 分子分母、唯一
锚点排除数及原因、下界范围和固定分母定义，并从逐帧 mapping 重新计算后逐项比较。任何
矛盾都会拒绝制品。

该块不进入 online D2 DTO、association log 或 tracker state。唯一身份来源仍是离线
`observation_id -> truth_target_id` 谱系侧车；最近距离、目标名称、actor ID 和终端邻近
均未使用。

## 29. clean `4ac3bb2` 冻结热路径 profiler 与等价优化

### 29.1 输入恢复与诊断器

`run_scalable_3d_association_hotpath_benchmark.py` 的 v2 schema 从在线 JSONL 顺序扫描，
保存最新 D1 record，并在遇到 D2 record 时形成输入/输出对。MAIN、D5 或 D7 插入记录
不会破坏配对；首条 D2 之前没有 D1 时 fail closed。随后使用原有 source frame 恢复、
tracker 配置和去计时语义比较器重建 48 个周期，不读取 truth sidecar。

除总 adapter/tracker 时间外，v2 记录每周期输入、fresh、active track、candidate edge、
claim count 和分阶段样本，并将最后一个周期作为 finalize 从前后 regular 窗口比较中
排除。`cProfile` 同时导出指定函数及全局 top cumulative/own-time 列表。CPU affinity、
`OPENBLAS_NUM_THREADS` 和 `OMP_NUM_THREADS` 写入报告；墙钟策略固定为
`diagnostic_only_no_wall_clock_pass_fail`。

### 29.2 三项实现

`Scalable3DTracker.predict_all()` 在单次调用内维护
`dt -> (transition, process_noise)` 字典。具有相同精确 `dt` 的航迹使用同一对只读计算
结果，各航迹的矩阵乘法、covariance governance、timestamp 和 age 更新顺序不变；缓存
不跨帧保存。

D1 adapter 已先对完整 6x6 covariance 调用 `govern_covariance()`。consistent 情况下，
内部构造器同时预置 full、position marginal 和 velocity marginal 的对象引用；
`Detection3D.__post_init__()` 只有在这些引用分别就是当前三个构造参数时才跳过两次
`np.allclose`。完整 6x6 governance、metadata truth 审计和后续字段校验仍执行。普通
dataclass 构造无法传入该私有状态，引用不一致立即拒绝，regularized 输入继续走原完整
验证。

claim ledger 新增 `_observation_claim_undated_count` 和
`_track_observation_key_count`。前者随无时间 claim 成功插入更新；后者随绑定、安全淘汰
和 duplicate coalescence 的集合净变化更新。summary 不再遍历 claim/key 容器，并在每帧
只计算一次，再以相同内容写入 `result.metadata` 和逐帧 audit。ledger schema、字段、
watermark、容量、淘汰事件及拒绝原因不变。

### 29.3 等价检查与结果边界

单元测试分别用旧逐轨公式构造 CV 参考状态、完整直接 `Detection3D` 校验构造 adapter
参考输出，并把 claim/key 容器替换为禁止 `values()` 扫描的字典，验证三项优化的操作数
和结果。profiler 测试覆盖交错总线配对、无前置 D1 拒绝、固定业务诊断和无墙钟断言。

冻结输入 SHA-256 为
`c1dda8523e48c255bbeef48d9516b05863eb1bbb3a3ae2e09733259e6a66f77a`。旧/新 48/48 周期
完整语义 SHA-256 均为
`b2334c619b9d2f7c467387ad27b62614d028af83f0b7842b867cab1c4aa9824b`；
input/fresh/replay/candidate/matched 为 `9626/9038/588/8862/8823`，逐项不变，
在线 truth use 为 0。

CPU 0、BLAS/OMP 单线程、1 次 warmup、7 次重复下，总中位数
`2.928830 -> 2.204672 s`，描述性加速 `1.328465x`。早/晚 regular 窗口比从
`1.119661x` 变为 `1.123036x`，没有关闭长窗口增长。报告文件
`d2_clean_4ac3bb2_seed1000_hotpath_20260723.json` 的 SHA-256 为
`2256d6fdd29223ed5dd75351cd6bb208a4d67c55925eeba047620ac865b6c7da`。本实现没有改变
逐条在线输出、中心 `global_track_id`、`id_switch_count` availability、门控、版本、
观测声明账本或真值隔离；也不把单 seed 冻结回放外推为 AirSim、完整链路或实时 SLA。
