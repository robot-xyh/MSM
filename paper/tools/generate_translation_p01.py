#!/usr/bin/env python3
"""Generate high quality faithful translation for Paper 01."""

import os
from pathlib import Path

content = """# 释放四旋翼特技飞行潜能：自主自由式飞行生成与执行（Unlocking Aerobatic Potential of Quadcopters: Autonomous Freestyle Flight Generation and Execution）

> **原文标题**：Unlocking aerobatic potential of quadcopters: Autonomous freestyle flight generation and execution  
> **作者**：Mingyang Wang, Qianhao Wang, Ze Wang, Yuman Gao, Jingping Wang, Can Cui, Yuan Li, Ziming Ding, Kaiwei Wang, Chao Xu, Fei Gao  
> **发表信息**：*Science Robotics*, Vol. 10, Issue 102, eadp9905 (2025-04-16)  
> **原文 PDF**：[01_Unlocking_Aerobatic_Potential_of_Quadcopters.pdf](../01_Unlocking_Aerobatic_Potential_of_Quadcopters.pdf) ｜ **对应中文详解**：[01_释放四旋翼特技飞行潜能.md](../中文详解/01_释放四旋翼特技飞行潜能.md) ｜ **开源代码与数据集**：[GitHub](https://github.com/ZJU-FAST-Lab/Aerobatic-Planner) / [Zenodo](https://doi.org/10.5281/zenodo.14586487)

---

## 摘要（Abstract）

四旋翼无人机在由熟练的人类飞行员手动操控时，能够展现出极其敏捷复杂的特技飞行动作；但在开放空间或复杂环境下的自主飞行中，通常仅局限于简单的平飞或小姿态机动。因此，本研究提出了一个完整的自主特技飞行系统，使四旋翼无人机能够在密集障碍物分布的复杂环境中，自主生成并安全执行高度复杂的自由式特技飞行动作。

我们提出了一种通用化的动作表征方法，将复杂的特技飞行解构为一系列离散的**特技飞行动力学意图（Aerobatic Intentions）**。这些意图包含空间拓扑路径和机身姿态变化，能够以任意形式自由组合以描述各种复杂动作。此外，我们引入了**时空联合优化轨迹规划器（Spatial-Temporal Simultaneous Optimization, OTOP）**，以生成尽可能平滑、无碰撞且满足严格动力学可行性的连续轨迹。

同时，我们深入分析了特技飞行中大姿态机动引发的微分平坦敏感性问题，揭示了微分平坦映射在倒飞和极大俯仰/滚转角下的奇异性对机体偏航旋转的固有影响，并提出了**偏航补偿映射（Yaw Compensation Mapping, YCM）**策略，从根本上消除了奇异点附近的数值跳变与不必要剧烈自旋。大量的仿真和真实物理实验（包括与顶尖人类 FPV 飞行员的对比）验证了所提系统的稳定性、动态可行性与优越性能，展示了释放无人机极限飞行潜能的能力。

---

## I. 引言（Introduction）

特技飞行涉及高难度、大姿态的激进机动，在普通飞行器的日常运行中极为罕见，因为这类动作伴随着固有的高风险和剧烈的不稳定姿态。然而在自然界中，这些空中特技动作是许多飞行生物赖以生存的本能技能。例如，雀鹰和游隼能够通过垂直俯冲或反向倒飞迅速改变速度与方向以捕食猎物或规避障碍；蝙蝠擅长在空中完成敏捷翻转并倒挂在洞穴顶端；年轻的渡鸦则经常展示高超的特技飞行来展示机动能力。对于这些物种而言，特技机动赋予了其在复杂非结构化环境中极强的环境适应性与敏捷性。

受此启发，一个核心问题随之而来：**无人机能否掌握类似的特技飞行能力，以大幅提升其在复杂未知环境中的机动极限与任务适应性？**

![图 1：所提出的四旋翼特技动作表征、生成与执行策略示意图](assets/01_释放四旋翼特技飞行潜能/fig_1.png)

**图 1：所提出的四旋翼特技动作表征、生成与执行策略示意图。**  
(A) 用户仅需构想期望的特技飞行动作，输入离散动作意图；  
(B) 安全飞行走廊（Flight Corridor）确保轨迹拓扑结构与无碰撞空间约束；  
(C) 规划器自适应联合优化意图点的时间与空间位置（OTOP），确保轨迹平滑过渡并满足动力学边界；  
(D) 偏航补偿映射（YCM）消除微分平坦奇异点附近的数值敏感性，确保计划轨迹与实际几何控制之间的高度一致性。

熟练的人类飞行员已经通过**第一人称视角（FPV）自由式特技飞行**证明了四旋翼无人机的卓越潜能。人类驾驶员佩戴头戴式显示器（FPV Goggles），能够以极高速度穿越狭窄障碍物并完成剧烈的大姿态翻滚、倒飞和急转。这种能力在实际任务中极具价值：
1. **多视角高机动感知**：在传感器视场受限的任务中，特技机动允许飞行器进入传统飞行无法企及的空间位姿，获取关键视角的观测数据；
2. **特殊载荷投送**：通过向上抛掷或高动态弹射机动，将传感器探针或物资运送至火山口、竖井等难以接近的危险区域；
3. **狭缝极限穿越与搜救**：通过侧倾 90° 或倒飞快速穿越极狭窄的倾斜缝隙，迅速搜寻受困人员；
4. **高动态避障**：在极度受限且分布有高速障碍物的极端空间中，通过敏捷机动规避碰撞。

然而，实现完全自主的特技飞行面临两大核心挑战：
1. **动作类型的多样性与通用表达**：不同任务需要多种各异的空中动作，如何在统一的数学框架内定义用户任意组合的动作意图并自动求解可行轨迹？
2. **高动态执行的安全性与动力学可行性**：在密集障碍物环境中执行剧烈机动时，必须严格遵守电机的推力上限、角速度极限以及连续安全走廊约束，防止过载或碰撞。

---

## II. 相关工作（Related Work）

在高速自主竞速无人机领域，近年来基于深度强化学习（RL）和模型预测控制（MPC）的方法取得了重大突破，在限定赛道内甚至超越了人类世界冠军飞行员。然而，自主竞速算法仅以通过门框的时间最短为优化目标，缺乏在任意指定位置执行任意姿态动作的能力。

在特技飞行规划领域，早期研究通常将动作划分为若干固定阶段（如多重翻滚的加速、旋转、改平阶段），或采用特定几何曲线（如圆弧、椭圆）拟合特定的动力学环路（Power Loop）。但这些预定义几何方法仅适用于少数规则动作，无法在复杂障碍物环境下泛化生成任意形状与空间拓扑的特技机动。

另一类方法是在轨迹中指定关键航路点及其对应的速度与姿态。然而，现存方法通常需要人工反复精细微调航路点的时间戳和具体坐标，一旦意图点距离过近或动力学不匹配，轨迹优化极易发散。此外，将四旋翼轨迹优化拓展至全 $SO(3)$ 姿态空间时，会不可避免地穿过**微分平坦性奇异区域**，引发严重的数值不稳定与无物理意义的剧烈偏航自旋。

为了克服这些局限，本文提出了一套端到端的自主特技飞行系统，能够将任意组合的特技意图自动转化为无碰撞、平滑且满足全动力学约束的连续轨迹，并通过创新的偏航补偿映射（YCM）彻底解决了全姿态空间下的平坦映射敏感性难题。

---

## III. 系统架构与硬件平台（System Architecture）

![图 2：硬件配置与系统架构规格说明](assets/01_释放四旋翼特技飞行潜能/fig_2.png)

**图 2：硬件配置与系统架构规格说明。**  
(A) 预先构建的三维点云地图，提供环境空间几何与拓扑障碍约束；  
(B) 两种典型自由式 FPV 飞行平台硬件组件（轻量级 2.5 英寸机型与高推重比 4 英寸机型）；  
(C) 基于 Unity 开发的可视化交互式地面站界面，支持用户直观输入特技意图并实时预览优化轨迹；  
(D) 部署于机载计算机上的全自主导航栈，集成激光/视觉惯导里程计、全局/局部轨迹规划器与非线性几何控制器。

系统的核心组成包括：
1. **环境建图与安全走廊生成**：利用机载激光雷达（如 Livox Mid-360）或外部点云预先建立环境三维模型，根据输入的拓扑路径自动膨胀生成连续凸多面体安全飞行走廊 $\mathcal{F} = \{F_1, \dots, F_M\}$；
2. **交互式地面站**：用户在三维界面中指定关键动作意图点（位置与推力朝向），系统实时计算并可视化三维轨迹及姿态演变过程；
3. **机载规划与几何控制**：基于最小控制能量（MINCO）多项式轨迹类，通过时空联合优化器（OTOP）求解最优轨迹，并由机载几何跟踪控制器输出电机 PWM 驱动指令。

---

## IV. 方法论（Methodology）

### 4.1 特技飞行动力学意图参数化（Aerobatic Parameterization）

特技动作的核心特征可以解构为两个基本维度：**空间拓扑路径**与**姿态变化序列**。我们定义三类离散特技意图 $\mathbf{I}_k = \{\mathbf{p}_k, \mathbf{\sigma}_k\}$（$k = 1, \dots, K$）：
1. **Type-I（仅位置约束）**：仅指定空间关键位置 $\mathbf{p}_k$，用于引导轨迹的空间拓扑绕行；
2. **Type-II（位置与期望姿态方向）**：指定关键位置 $\mathbf{p}_k$ 与机体推力方向向量 $\mathbf{\sigma}_k \in \mathbb{S}^2$，允许飞行器在附近自适应完成姿态调整；
3. **Type-III（位置与严格定点姿态）**：要求轨迹在精确到达指定位置 $\mathbf{p}_k$ 的同时严格达到姿态方向 $\mathbf{\sigma}_k$。

通过将若干离散意图组合，即可灵活表达桶滚（Barrel Roll）、动力翻转（Power Loop）、Split-S、破幽灵机动（Immelmann Turn）等任意复杂的特技动作。

### 4.2 微分平坦性与偏航补偿映射（Yaw Compensation Mapping, YCM）

四旋翼飞行器具备著名的**微分平坦性（Differential Flatness）**特性：机体状态 $\mathbf{x} = [\mathbf{p}^T, \mathbf{v}^T, \mathbf{R}, \mathbf{\omega}^T]^T$ 与控制输入 $\mathbf{u} = [f, \mathbf{\tau}^T]^T$ 可以表示为平坦输出 $\mathbf{\zeta}(t) = [\mathbf{p}(t)^T, \psi(t)]^T$ 及其各阶导数的代数函数。

传统平坦映射中，平坦输出定义为三维位置 $\mathbf{p}(t) = [x, y, z]^T$ 和偏航角 $\psi(t)$。推力方向单位向量定义为：
$$
\mathbf{z}_B = \frac{\ddot{\mathbf{p}} + \mathbf{g}}{\|\ddot{\mathbf{p}} + \mathbf{g}\|}
$$
在传统映射下，当机体处于倒飞状态（$\mathbf{z}_B = -\mathbf{z}_W$）或失重垂直下落（$\ddot{\mathbf{p}} + \mathbf{g} \approx \mathbf{0}$）时，映射存在数学奇异性。即使平坦偏航角 $\psi(t)$ 平滑变化，机体实际旋转矩阵与偏航角速度也会出现剧烈震荡（80 ms 内发生 360° 虚假自旋）。

为了消除该奇异敏感性，我们提出了**偏航补偿映射（YCM）**：用具有明确物理意义的机头朝向矢量 $\mathbf{d}(t) \in \mathbb{R}^3$（直接定义为运动速度方向 $\mathbf{d}(t) = \dot{\mathbf{p}}(t)$）代替无物理意义的平坦偏航角：
$$
\mathbf{x}_B = \frac{\mathbf{d} - (\mathbf{z}_B^T \mathbf{d})\mathbf{z}_B}{\|\mathbf{d} - (\mathbf{z}_B^T \mathbf{d})\mathbf{z}_B\|}, \quad \mathbf{y}_B = \mathbf{z}_B \times \mathbf{x}_B
$$
YCM 将机头朝向与位置轨迹完全解耦，确保了在全 $SO(3)$ 姿态空间和剧烈动作过程中，计算得到的机体角速度 $\mathbf{\omega}(t)$ 始终连续平滑，彻底消除了不必要的机体自旋。

### 4.3 轨迹表征与时空联合优化（MINCO & OTOP）

采用 $M$ 段 $D$ 次多项式样条 $\mathbf{p}(t) = \{\mathbf{p}_1(t), \dots, \mathbf{p}_M(t)\}$ 表征平坦输出轨迹，每段持续时间为 $T_i > 0$，总时间 $T_\Sigma = \sum_{i=1}^M T_i$。每段多项式为：
$$
\mathbf{p}_i(t) = \mathbf{c}_i^T \mathbf{\beta}(t), \quad \mathbf{\beta}(t) = [t^0, t^1, \dots, t^D]^T, \quad D = 2s - 1
$$
基于最小控制能量（MINCO）参数化，整条多项式轨迹由中间航路点 $\mathbf{q} = \{\mathbf{q}_1, \dots, \mathbf{q}_{M-1}\}$ 和各段分配时间 $\mathbf{T} = [T_1, \dots, T_M]^T$ 唯一定义。

我们将特技轨迹规划形式化为如下带约束的时空优化问题：
$$
\begin{aligned}
\min_{\mathbf{q}, \mathbf{T}, \mathcal{T}} \mathcal{H} &= \sum_{i=1}^M \int_0^{T_i} \|\mathbf{p}_i^{(s)}(t)\|^2 \mathrm{d}t + \lambda_t T_\Sigma \tag{6A} \\
\text{s.t.} \quad & \mathcal{G}(\mathbf{q}, \mathbf{T}) \preceq \mathbf{0}, \quad \forall t \in [0, T_\Sigma] \tag{6B} \\
& \mathcal{C}(\mathbf{q}, \mathbf{T}) = \mathbf{0}, \quad \forall t \in [0, T_\Sigma] \tag{6C} \\
& \mathcal{A}(\mathbf{q}, \mathbf{T}, t_{\sigma_k}) = \mathbf{0}, \quad \forall t_{\sigma_k} \in \mathcal{T}, \; k=1,\dots,K \tag{6D}
\end{aligned}
$$
其中：
- 式 (6A) 为综合控制代价（平滑度）与飞行总时间的性能指标；
- 式 (6B) 包含安全走廊边界约束 $\mathbf{p}(t) \in \mathcal{F}$、推力极限 $f_{\min} \le f(t) \le f_{\max}$ 及角速度极限 $\|\mathbf{\omega}(t)\| \le \omega_{\max}$；
- 式 (6C) 为段间连续性与边界状态约束；
- 式 (6D) 为特技意图达标约束，$\mathcal{T} = \{t_{\sigma_1}, \dots, t_{\sigma_K}\}$ 为各特技意图发生的时间戳。

通过构造精确惩罚函数与变量代换，我们将上述约束优化问题转化为无约束形式：
$$
\min_{\mathbf{q}, \mathbf{T}, \mathcal{T}} \hat{\mathcal{H}} = \lambda_e \mathcal{J}_e + \lambda_t \mathcal{J}_t + \lambda_a \mathcal{J}_a + \lambda_c \mathcal{J}_c + \lambda_d \mathcal{J}_d \tag{7}
$$
其中下标 $\{e, t, a, c, d\}$ 分别对应控制能量、时间代价、特技意图偏差、走廊碰撞惩罚以及动力学过载惩罚。该目标函数连续可微，采用 **L-BFGS（有限内存 BFGS 拟牛顿法）** 进行毫秒级高效求解。

---

## V. 实验与结果分析（Experiments and Results）

### 5.1 大范围非结构化室外环境特技飞行

![图 3：大范围非结构化室外环境特技飞行实验结果](assets/01_释放四旋翼特技飞行潜能/fig_3.png)

**图 3：大范围非结构化室外环境特技飞行实验结果。**  
(A) 包含桶滚、动力翻转和 Split-S 等连续特技动作的轨迹飞行序列快照；  
(B) 无人机在轨迹最高点完全倒飞的细节特写；  
(C) 环境激光点云地图与重建轨迹；  
(D) 关键飞行动力学数据：位置跟踪误差 $\delta \mathbf{p}$（始终 $<0.15\text{ m}$）、姿态跟踪误差 $\delta \theta$（始终 $<12^\circ$）、净推力比 $\tau$ 及三轴角速度 $\mathbf{\omega}$。

在长达 220 米的复杂林地与拱桥场景中，无人机连续完成了多个大姿态机动。在轨迹规划中，净推力上限仅设定为 $1.5\text{ g}$，角速度上限为 $4\text{ rad/s}$。实测数据显示，机体在执行剧烈特技期间的位置跟踪误差与平飞阶段无显著差异，验证了生成轨迹优异的动力学顺应性。

### 5.2 密集障碍物受限空间极限特技机动

![图 4：在受限空间中执行特技机动并规避障碍物](assets/01_释放四旋翼特技飞行潜能/fig_4.png)

**图 4：在受限空间中执行特技机动并规避障碍物。**  
(A) 规划轨迹与实测飞行速度分布；  
(B) 针对用户输入的初始过于密集的意图点，OTOP 算法自动调整其空间位置与时间间隔，生成可行轨迹；  
(C) 动捕系统内的环境障碍物分布与轨迹重复执行（8 次连续测试）的跟踪误差统计。

在高度仅 $3.5\text{ m}$ 的动作捕捉场地中，场地内密集布设了立柱、圆门和旗帜障碍物。系统成功规划出穿过狭窄圆门并伴随 $360^\circ$ 连续翻转的极限动作，飞行速度超过 $4\text{ m/s}$，重复执行 8 次均保持零碰撞且位置误差保持在 $0.15\text{ m}$ 以内。

### 5.3 丰富特技意图组合验证

![图 5：丰富特技意图与对应生成的复合动作轨迹](assets/01_释放四旋翼特技飞行潜能/fig_5.jpeg)

**图 5：丰富特技意图与对应生成的复合动作轨迹。**  
(A) 由多段经典动作组合生成的复杂长程特技轨迹；  
(B) 四类经典特技机动（Power Loop、Barrel Roll、Split-S、Matty Flip）对应的意图参数与三维轨迹形状；  
(C) 用户自定义随机组合意图生成的非标准特技机动。

### 5.4 与顶尖人类职业 FPV 飞行员对比实验

![图 6：与专业人类 FPV 飞行员的对比实验](assets/01_释放四旋翼特技飞行潜能/fig_6.png)

**图 6：与专业人类 FPV 飞行员的对比实验。**  
(A) 人类飞行员与自主算法在执行单个动力翻转（Power Loop）动作时的轨迹形状与机体姿态对比；  
(B) 连续穿越 6 个平行门框的连续动力翻转任务中，人类最优轨迹与算法规划轨迹的对比；  
(C) 连续特技飞行的成功率与失误率统计对比（自主系统实现 100% 成功率，人类飞行员为 12.5%）。

在连续穿越 6 个平行门框的极限翻转测试中，人类顶尖飞手在单门翻转时虽能维持良好表现，但在连续高速翻转下极易因视觉遮挡与累积误差导致姿态失控或炸机（24 次尝试仅成功 3 次）；而本文算法在 5 次完整测试中均实现了 100% 的精准通过与平稳飞行。

### 5.5 消融实验（Ablation Studies）

![图 7：偏航补偿映射（YCM）与时空优化（OTOP）消融实验分析](assets/01_释放四旋翼特技飞行潜能/fig_7.png)

**图 7：偏航补偿映射（YCM）与时空优化（OTOP）消融实验分析。**  
(A) YCM 机制有效性验证：传统平坦映射在倒飞时刻 $T_0$ 附近出现激烈的 $z$ 轴角速度震荡与 $360^\circ$ 瞬时偏航跳变，而 YCM 保持完全平稳；  
(B) 轨迹优化策略对比：定点调时（OTFP）、定时代点（FTOP）与时空协同优化（OTOP）在动作保真度惩罚、能量消耗与飞行时间分配上的量化对比。

实验表明，OTOP 策略在能量损耗、飞行时间与特技动作保真度之间达到了最优折中；YCM 则是保障全姿态空间轨迹可执行性的关键基石。

---

## VI. 讨论与局限性（Discussion）

1. **航向与速度方向解耦**：本系统默认将机头朝向与轨迹速度方向对齐以降低求解维度。若需实现侧飞、倒飞刷圈等特殊视觉效果，用户只需在线性优化中显式指定额外的偏航角度目标即可。
2. **未知环境下的扩展性**：在缺乏先验完整地图的未知场景中，本系统生成的全局特技轨迹可作为引导路径，结合实时局部重规划模块（如快速避障 replanner）实现动态未知障碍物规避。
3. **高阶气动建模**：当前系统采用经典的 SE(3) 几何控制器，已足以应对常规特技。未来引入考虑旋翼桨叶挥舞、非定常空气动力学效应的高阶模型预测控制（NMPC）或残差学习模型，将进一步提升极限推重比下的控制精度。

---

## VII. 结论（Conclusion）

本研究提出了首个能够在密集复杂障碍物环境中自主生成并执行任意组合四旋翼特技动作的完整软硬件系统。通过离散特技意图表征、时空协同联合优化（OTOP）以及偏航补偿映射（YCM），彻底解决了特技动作通用表达、动力学安全走廊约束求解以及微分平坦全姿态奇异性三大难题。真实世界实验与人类飞手对比充分验证了系统的卓越性能，为下一代高机动空中机器人探索复杂极限环境奠定了坚实的技术基础。

---

## 参考文献（References）

1. BBC, *How sparrowhawks catch garden birds - life in the air: Episode 2 preview* (2016).
2. otk3244, *Sony a1 impressive peregrine hunt 2207 08* (2016).
3. National Geographic, *How do bats land upside down?* (2015).
4. Exploring wildlife with Vance Crofoot, *Young ravens displaying skilled aerial maneuvers* (2022).
5. D. Tezza et al., *Let’s fly! An analysis of flying fpv drones through an online survey*, ACM SIGCHI (2020).
6. DJI, *DJI Enterprise* (2024).
7. E. Kaufmann, L. Bauersfeld, A. Loquercio, et al., *Champion-level drone racing using deep reinforcement learning*, **Nature**, 620, 982–987 (2023).
8. X. Zhou, Z. Wang, H. Ye, C. Xu, F. Gao, *Ego-planner: An ESDF-free gradient-based local planner for quadrotors*, **IEEE RA-L**, 6, 478–485 (2020).
9. Y. Song, A. Romero, M. Müller, et al., *Reaching the limit in autonomous racing: Optimal control versus reinforcement learning*, **Science Robotics**, 8, eadg1462 (2023).
10. Y. Chen, N. O. Pérez-Arancibia, *Controller synthesis and performance optimization for aerobatic quadrotor flight*, **IEEE T-CST**, 28, 2204–2219 (2020).
11. S. Lupashin, A. Schöllig, M. Sherback, R. D'Andrea, *A simple learning strategy for high-speed quadrocopter multi-flips*, **IEEE ICRA**, pp. 1642–1648 (2010).
12. G. Lu, W. Xu, F. Zhang, *On-manifold model predictive control for trajectory tracking on robotic systems*, **IEEE T-IE**, 70, 9192–9202 (2022).
13. E. Kaufmann, A. Loquercio, R. Ranftl, et al., *Deep drone acrobatics*, **RSS** (2020).
14. C. Mollica, *FPV Flight Dynamics: Mastering Acro Mode on High-Performance Drones*, Vespula Ventures (2020).
15. B. E. Jackson, K. Tracy, Z. Manchester, *Planning with attitude*, **IEEE RA-L**, 6, 5658–5664 (2021).
16. E. Tal, G. Ryou, S. Karaman, *Aerobatic trajectory generation for a VTOL fixed-wing aircraft using differential flatness*, **IEEE T-RO**, 39, 4805–4819 (2023).
17. G. Lu, Y. Cai, N. Chen, et al., *Trajectory generation and tracking control for aggressive tail-sitter flights*, **IJRR**, 43, 241–280 (2024).
18. T. Qin, P. Li, S. Shen, *VINS-Mono: A robust and versatile monocular visual-inertial state estimator*, **IEEE T-RO**, 34, 1004–1020 (2018).
19. K. Sun, K. Mohta, B. Pfrommer, et al., *Robust stereo visual inertial odometry for fast autonomous flight*, **IEEE RA-L**, 3, 965–972 (2018).
20. T. Shan, B. Englot, D. Meyers, et al., *LIO-SAM: Tightly-coupled lidar inertial odometry via smoothing and mapping*, **IEEE IROS**, pp. 5135–5142 (2020).
21. W. Xu, F. Zhang, *FAST-LIO: A fast, robust lidar-inertial odometry package by tightly-coupled iterated kalman filter*, **IEEE RA-L**, 6, 3317–3324 (2021).
25. T. Lee, M. Leok, N. H. McClamroch, *Geometric tracking control of a quadrotor UAV on SE(3)*, **IEEE CDC**, pp. 5420–5425 (2010).
26. M. Watterson, V. Kumar, *Control of quadrotors using the Hopf fibration on SO(3)*, **ISRR**, pp. 199–215 (2020).
27. Z. Wang, X. Zhou, C. Xu, F. Gao, *Geometrically constrained trajectory optimization for multicopters*, **IEEE T-RO**, 38, 3259–3278 (2022).
34. D. Mellinger, V. Kumar, *Minimum snap trajectory generation and control for quadrotors*, **IEEE ICRA**, pp. 2520–2525 (2011).
35. B. Morrell et al., *Differential flatness transformations for aggressive quadrotor flight*, **IEEE ICRA**, pp. 5204–5210 (2018).
37. F. Gao, L. Wang, B. Zhou, et al., *Teach-repeat-replan: A complete and robust system for aggressive flight in complex environments*, **IEEE T-RO**, 36, 1526–1545 (2020).
44. D. C. Liu, J. Nocedal, *On the limited memory BFGS method for large scale optimization*, **Math. Program.**, 45, 503–528 (1989).
48. Q. Wang, Z. Wang, M. Wang, et al., *Fast iterative region inflation for computing large 2-d/3-d convex regions of obstacle-free space*, **arXiv:2403.02977** (2024).
"""

target = Path("/home/linux/Documents/MSM/paper/papers/中文翻译/01_释放四旋翼特技飞行潜能_原文翻译.md")
target.write_text(content.strip() + "\n", encoding="utf-8")
print(f"Written faithful translation to {target}")
