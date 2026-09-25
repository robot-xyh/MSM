# PredRecon: A Prediction-boosted Planning Framework for Fast and High-quality Autonomous Aerial Reconstruction

> **元数据**
> - **作者**: Chen Feng, Haojia Li, Fei Gao, Boyu Zhou, and Shaojie Shen
> - **期刊/会议**: 2023 IEEE International Conference on Robotics and Automation (ICRA)
> - **链接**: [Code GitHub](https://github.com/HKUST-Aerial-Robotics/PredRecon), [DOI: 10.1109/ICRA48891.2023.10160933](https://doi.org/10.1109/ICRA48891.2023.10160933)

## 1. 核心思想与一句话概括
**核心思想**：PredRecon 是一个基于深度预测增强的无人机（UAV）自主路径规划框架，旨在单次飞行中快速、高质量地完成未知环境目标的三维重建。
**一句话概括**：通过赋予无人机“举一反三”的脑补能力，利用神经网络从部分观测中预测出目标物体的完整三维表面，以此引导全局视点规划，跳过盲目的探索阶段，从而在单次飞行中实现极高效率和极佳质量的三维重建。

## 2. 外行导读与研究背景
以往的无人机三维重建就像“盲人摸象”。由于一开始不知道要扫描的建筑具体长什么样，传统的策略要么是先飞一圈“踩点”（探明粗略形状），再飞一圈“精描”（获取高清图像），即“explore-then-exploit”策略；要么就只能依靠提前导入一个粗糙的3D模型（prior-based）。前者飞行时间长、耗电量大，效率极其低下；后者则无法做到全自动，且对无图环境束手无策。还有一些边飞边探的方法，会把大量时间浪费在对无用空间的探索上。

**如果无人机能像人一样呢？** 我们人类看到一座房子的一面墙和一半屋顶，就能凭经验大概猜出整座房子的轮廓。PredRecon 就是将这种能力赋予了无人机。它使用一个轻量级的神经网络，能够根据无人机已经看到的局部区域，直接预测出整个建筑的完整形态。有了这个“预测地图”，无人机就知道该往哪飞最高效，从而一次性完美地规划出拍摄路径，极大地节省了时间和航程。

## 3. 当前研究现状与技术路线对比

| 评估维度 | Explore-then-exploit (如 Plan3D) | Prior-based (如 CAPP) | Exploration-based (如 FUEL) | **PredRecon (本文方法)** |
| :--- | :--- | :--- | :--- | :--- |
| **飞行次数** | 2次 (先粗探，再精建) | 1次 | 1次 | **1次** |
| **对先验模型依赖**| 无 | 强依赖 (需要预先输入粗模型) | 无 | **无 (实时预测生成)** |
| **对未知区域处理**| 探索成本极高 (浪费在初次飞行)| 不适用完全未知环境 | 较高 (盲目探索边界) | **极低 (利用预测填补未知)** |
| **底层智能能力** | 纯几何启发 | 无 | 增量式前沿探索 | **基于深度学习端到端完整表面预测**|
| **重建质量优化** | 考虑多视角立体(MVS)启发式 | 考虑 MVS 启发式 | 仅覆盖驱动 | **精细拆解MVS多视角立体几何特性** |
| **全自动化程度** | 较低 (双圈飞行或需人工干预) | 低 (需人工前置作业) | 高 | **极高 (单次飞行，感知到规划闭环)**|

## 4. 核心术语与定义
- **SPM (Surface Prediction Module，表面预测模块)**: 本文提出的基于深度学习的网络模块。输入当前体素地图中的局部残缺点云，输出目标的完整三维表面点云，无需依赖额外检测器。
- **MVS (Multi-View Stereo，多视角立体视觉)**: 一种从多张带有姿态信息的 2D 图像中恢复 3D 密集点云的技术。优质的三维重建极度依赖于为 MVS 算法提供极佳的相机拍摄视角。
- **Online Volumetric Mapping (在线体素建图)**: 实时提取已被多次观测的表面以及预测网络输出的未覆盖表面，为后续的路径规划提供工作空间状态。
- **Hierarchical Planner (分层规划器)**: 包含两层逻辑：(1) **全局覆盖路径规划**，用于粗略决定去哪些视点拍摄以覆盖所有未知表面；(2) **质量驱动局部路径规划**，用于在局部范围内精细调整相机位姿和轨迹，确保满足 MVS 的苛刻几何要求。
- **NBV (Next Best View，次优视点)**: 规划算法在每一步决策时选出的下一个最佳拍摄位置和角度。

## 5. 核心算法与理论模型 (深度解析)

### 5.1 表面预测模块 (SPM)
相比于传统的点云补全网络（如PCN），SPM 摒弃了额外检测器进行归一化的复杂操作，直接处理下采样的局部点云 $M_C$ (点数固定为 $N_C$)。首先进行局部坐标系转换：
$$T_p(p_i, C_C) = p_i - C_C$$
模型主要由两个 Header 构成：
1. **尺度估计头 (Scale Estimation Header)**:
   使用 PointNet 提取全局不变特征，通过回归 MLP 直接输出三个轴向的粗略尺度 $(x_s, y_s, z_s)$。为了提高精度，在 PointNet 后的局部特征图上施加偏移 MLP 得到残差修正 $(\Delta x_s, \Delta y_s, \Delta z_s)$。最终目标尺度 $s_t$ 为：
   $$s_t = \max(x_s+\Delta x_s, y_s+\Delta y_s, z_s+\Delta z_s)$$
2. **表面预测头 (Surface Prediction Header)**:
   将经过尺度归一化的点云输入至一个共享 MLP 中，并利用 **PointPillars** 作为编码器（因为伪图像操作具有空间感知能力且计算量小）。之后连接一个**由粗到细 (coarse-to-fine)** 的解码器，输出 $Y_{fine}$ 和 $Y_{coarse}$。
   损失函数采用排列不变的**倒角距离 (Chamfer Distance, CD)** 监督：
   $$cd(X, Y) = \frac{1}{|X|} \sum_{x\in X} \min_{y\in Y} ||x-y||_2^2 + \frac{1}{|Y|} \sum_{y\in Y} \min_{x\in X} ||x-y||_2^2$$
   $$\mathcal{L} = cd(Y_{coarse}, Y_{gt}) + cd(Y_{fine}, Y_{gt})$$
网络输出通过反归一化并与当前输入点云拼接，经过 GHPR 算法提取出建筑的“内部空间” (Internal Space) 作为后续规划的禁飞区。

### 5.2 层次化规划器 (Hierarchical Planner)

#### A. 全局覆盖路径规划
旨在找到一条高效的全局序列以覆盖所有“未观测但预测出的表面”。
首先将表面聚类为 $N_G$ 个簇。通过双重采样在每个簇法线方向生成候选视点，取“表面可见度比例” $r(v, s) = \frac{\mathcal{N}(v)}{\mathcal{N}(s)}$ 最高的视点作为代表节点。
随后，将其建模为**非对称旅行商问题 (ATSP)**。视点间的代价值 $\Upsilon_G$ 包含路径长度和偏航角(yaw)变化：
$$c_g(v_g^i, v_g^j) = \frac{L(P_g^i, P_g^j)}{v_{max}} + \frac{\min(||\theta_g^i - \theta_g^j||_1, 2\pi - ||\theta_g^i - \theta_g^j||_1)}{\omega}$$
为了保证无人机飞行的**全局一致性**（避免朝向反复横跳），引入了一致性惩罚 $c_{GC}$，基于当前实际飞行向量与上一次规划向量的夹角：
$$c_{GC}(v_g^i) = \arccos \left( \frac{P_g^i - P_{cur}^{now}}{||P_g^i - P_{cur}^{now}||_2} \right) \cdot d_g^{last}$$
最终通过 LKH 启发式算法快速求解 ATSP 得到全局序列。

#### B. 质量驱动的局部路径规划
局部规划的目标是提取相邻的局部航路点，并通过细分聚类使其不仅覆盖目标，还能让 MVS 算法输出最清晰深度的深度图。
MVS 质量 $Q$ 被分解为**三角测量单元**上三个几何因子的乘积：
$$Q(v_1, v_2, s) = \mathcal{S}_{vis} \cdot \mathcal{S}_{dis} \cdot \mathcal{S}_{ang}$$
- **可见性得分 ($\mathcal{S}_{vis}$)**：两视角下表面可见点比例的均值。
- **距离一致性得分 ($\mathcal{S}_{dis}$)**：要求两相机到表面的距离尽量相等，保证分辨率一致性：
  $$\mathcal{S}_{dis}(v_1, v_2, s) = \frac{\min(dis_1, dis_2)}{\max(dis_1, dis_2)}$$
- **三角测量角度得分 ($\mathcal{S}_{ang}$)**：惩罚过大或过小的视差角，期望达到最优角 $\epsilon_d$ (如 22.5°)：
  $$\mathcal{S}_{ang}(v_1, v_2, s) = \exp\left(-\left(\frac{\epsilon - \epsilon_d + \varepsilon_1 - \varepsilon_2}{\kappa}\right)^2\right)$$
通过 Dijkstra 算法在构建的候选图中搜寻综合代价（运动代价+MVS质量惩罚）最小的路径，最后利用 B-spline 优化生成符合动力学的平滑局部轨迹。

## 6. 实验验证与量化分析
本文在 UE4 引擎支持的 AirSim 逼真仿真器中进行了基准测试。测试场景包括 **Palace** ($15\times25\times14m^3$) 和 **Village House** ($14\times11\times12m^3$)。

- **高效率 (Efficiency)**
  - **Palace** 场景中：PredRecon 的总路径长度仅 **213.1m**，耗时 **252.7s**。相比之下，传统的 Plan3D 耗时高达 507.7s，FUEL 耗时 469.8s。PredRecon 时间上缩减了近 50%。
  - **Village House** 场景中：PredRecon 耗时仅 **184.6s**，不仅远快于无先验的 Plan3D (310.6s)，甚至**击败了完全依赖上帝视角输入粗模的 CAPP 方法 (242.3s)**。
- **高质量 (Reconstruction Quality)**
  - 根据生成的 Dense 3D 模型的 F-score 评估，PredRecon 在 Palace 中达到 **80.13%**，在 Village House 中达到 **83.83%**。各项重建指标 (Recall 和 Precision) 均大幅领先传统方法。
- **实时性 (Computation Time)**
  - 核心模块运行于 Intel i9 CPU 配合 RTX 3070 Ti (SPM显存占用约 1GB)。单次完整的规划计算仅耗时 **~124.7ms**（其中 SPM 推理占 ~26.8ms，全局规划占 ~93.5ms），完美契合无人机机载电脑的高频实时重规划需求。

## 7. 创新点突破与局限性
### 🎯 核心创新点
1. **打破信息茧房**：首次在无人机主动重建路径规划领域中深度整合“表面预测模块”，利用 AI 推理打破了传统依赖二次飞行或依赖外部输入模型的物理/信息瓶颈。
2. **轻量化实时推理**：创新的端到端预测网络，用 PointPillars 替代了冗余的 3D CNN，去除了繁琐的外置检测器，实现了极速的 26ms 推理和微小的显存占用 (1GB)。
3. **MVS物理规律建模**：将深奥的 MVS 重建质量严密地量化成了可见度、距离一致性和三角测量视差角的数学模型，并在局部图搜索中显式优化，确保了最终图像集对于 Colmap 的高度友好性。

### ⚠️ 局限性
1. **真实世界验证不足**：论文主要在高度逼真的仿真环境 (UE4) 中进行，仍缺乏大量现实世界中的野外实测验证 (Real-world tests)。
2. **泛化与鲁棒性**：SPM 预测网络的强弱受限于训练集，对于在形状、拓扑结构上与训练集差异过大（Out-of-distribution）的极其罕见或奇特构造，预测精度可能会明显下降。

## 8. 复现提示与工程经验
- **开源资源库**：官方代码已开源于 [HKUST-Aerial-Robotics/PredRecon](https://github.com/HKUST-Aerial-Robotics/PredRecon)。
- **硬件配置建议**：作者表示网络仅占用约 **1GB VRAM**，这意味着可以在挂载了如 NVIDIA Jetson Xavier NX 或 Orin 的机载边缘计算设备上直接运行部署。
- **模型训练建议**：若想训练自己的建筑类型，可以参考作者的数据集构建方法。作者利用了 Houses3K、Blender 以及 UE4 合成了大量的（局部观测点云, 完整点云）Ground Truth Pair。自定义场景下，务必保证训练集尽可能覆盖目标建筑的特征域。
- **调参关键点**：在复现过程中，针对 MVS 视差角的期望参数 $\epsilon_d$ 被设定为 $22.5^{\circ}$，这与传统双目视觉的黄金基线夹角匹配。局部代数中的 MVS 权重 $\alpha_1$ 被设为 $0.8$，这说明：在局部精调时，**“为了拍得清晰，稍微绕远一点也是极其值得的”**。
