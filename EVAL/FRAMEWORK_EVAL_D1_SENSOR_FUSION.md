# D1 传感器融合架构评估与改进方案

**文档版本**: v1.0
**评估日期**: 2026-07-08
**评估重点**: 工程化、成熟可靠、可在仿真/封闭场地验证

---

## 1. 当前架构分析

### 1.1 核心设计

当前D1模块实现了基于NumPy的轻量级传感器融合系统：

**状态模型**:
- 六维状态向量 `[px, py, pz, vx, vy, vz]`
- NED坐标系统一工作空间
- 常速度(CV)运动模型为主

**融合算法**:
- NumPy实现的EKF
- measurement_timestamp与arrival_timestamp分离
- 延迟补偿通过前向预测
- 协方差传播与不确定性建模

**传感器支持**:
- 雷达：距离相关协方差建模
- 声学：粗方位与类别提示
- 光电：像素框投影约束
- AirSim真值回放

### 1.2 核心假设

1. **运动模型假设**: 目标以常速度运动，加速度视为过程噪声
2. **线性化假设**: EKF雅可比线性化在局部足够精确
3. **独立性假设**: 不同传感器误差独立，无公共模式误差
4. **时间同步假设**: measurement_timestamp准确可信
5. **单航迹假设**: 每个目标维护独立滤波器，无Track-to-Track融合

### 1.3 设计边界

- **坐标系**: 仅支持NED，未实现自动坐标转换
- **模型库**: 仅CV模型，无CA(恒加速)、CT(协调转弯)、Singer模型
- **融合架构**: 集中式融合，不支持分布式Track-to-Track
- **OOSM处理**: fixed-lag缓冲，但无Retrodiction或平滑

---

## 2. 工程化不足识别

### 2.1 鲁棒性问题

#### 问题1: 机动目标跟踪性能差
**表现**: 目标突然机动时，CV模型预测误差大，协方差发散
**根因**: 单一CV模型无法适应多种运动模式
**工程影响**: 5v5场景中，编队变换、规避机动导致航迹丢失

#### 问题2: 传感器故障检测不足
**表现**: 异常观测仅通过马氏门控拒绝，无传感器级健康监测
**根因**: 缺乏传感器性能监测与故障隔离(FDIR)机制
**工程影响**: 单个传感器故障可能污染全局航迹

#### 问题3: 多径与遮挡未建模
**表现**: 雷达多径、声学反射、视线遮挡视为随机噪声
**根因**: 缺乏环境感知与场景相关误差建模
**工程影响**: 低空、建筑物附近性能退化

### 2.2 边界条件处理

#### 边界1: 传感器数量变化
**问题**: 传感器上线/下线时，协方差突变
**缺失**: 渐进式传感器权重调整

#### 边界2: 长时间无观测
**问题**: 外推时协方差线性增长，实际可能非线性
**缺失**: 基于场景的协方差增长上限

#### 边界3: 观测频率不一致
**问题**: 高频传感器主导融合，低频传感器贡献小
**缺失**: 基于信息增益的传感器调度

### 2.3 真实环境适应性

#### 适应性1: 时间同步误差
**现状**: 假设timestamp准确
**真实**: 多节点存在时钟漂移(ms级)
**影响**: 速度估计偏差、延迟补偿失效

#### 适应性2: 非高斯噪声
**现状**: 假设高斯噪声
**真实**: 杂波、虚警、多径为非高斯
**影响**: EKF次优，需粒子滤波或鲁棒滤波

#### 适应性3: 相关观测误差
**现状**: 假设传感器独立
**真实**: 共享时钟、共享环境参数导致相关性
**影响**: 协方差低估，过度自信

---

## 3. 成熟方案对比

### 3.1 工业系统参考

#### Anduril Lattice
**融合架构**:
- 分布式Track-to-Track融合
- 协方差交叉(Covariance Intersection)避免重复计数
- 自适应传感器管理

**可借鉴**:
- Track-to-Track融合接口设计
- 分布式协方差一致性算法
- 传感器性能在线估计

**参考**: Anduril公开文档 <https://www.anduril.com/lattice/>

#### 以色列Drone Guard系统
**融合策略**:
- 雷达主导，光电/RF辅助
- IMM多模型切换(CV/CA/CT)
- 场景自适应协方差调整

**可借鉴**:
- IMM工程化实现
- 雷达-光电数据关联门限标定
- 威胁区域相关协方差建模

**参考**: Rafael文档、IEEE TAES论文

#### UK SAPIENT标准
**传感器互操作**:
- 统一传感器任务接口(Detection、Task、Alert)
- 标准化不确定性表达
- 传感器性能元数据

**可借鉴**:
- SensorObservation数据合同对齐SAPIENT
- 协方差标准化表达(ellipse、CDF95)
- 传感器注册与能力声明

**参考**: UK DSTL SAPIENT规范 <https://www.gov.uk/government/publications/sapient>

### 3.2 开源工程实现

#### PX4 EKF2
**特点**:
- 24状态扩展卡尔曼滤波器
- IMM风格的传感器故障检测
- 磁罗盘/GPS/视觉/惯导融合
- 实时性能优化(固定步长、稀疏矩阵)

**代码**: <https://github.com/PX4/PX4-Autopilot/tree/main/src/modules/ekf2>

**可借鉴**:
- 传感器健康检查与故障隔离
- 协方差一致性检查(NIS、innovation)
- 数值稳定性处理(Joseph form、UD分解)

#### Stone Soup (UK DSTL)
**特点**:
- 模块化多目标跟踪框架
- 支持EKF、UKF、PF、IMM
- Track-to-Track融合接口
- 多种关联算法(GNN、JPDA、MHT)

**代码**: <https://github.com/dstl/Stone-Soup>

**可借鉴**:
- IMM工程实现(模型库、转移矩阵标定)
- Track-to-Track融合(CI、Ellipsoidal Intersection)
- 传感器模型库(雷达、光电、RF)

#### NASA JPL姿态估计库
**特点**:
- UKF/SRUKF(Square Root UKF)
- 四元数姿态表示
- 协方差保正定性

**代码**: 部分公开在NASA GitHub

**可借鉴**:
- 非线性观测的UKF实现
- 数值稳定性技术

### 3.3 标准与规范

#### NATO STANAG 4607 (GMTI)
- 地面动目标指示数据格式
- 位置不确定性椭圆表达
- 目标分类标准

#### MISB ST 0601 (UAS Metadata)
- 无人机元数据标准
- 传感器指向、FOV、GSD
- 时间戳标准(Precision Time Stamp)

#### ICD-GPS-200 (GPS接口)
- 位置精度指标(HDOP、PDOP)
- 协方差椭球参数

---

## 4. 改进方案

### 4.1 短期改进 (1-3个月，现有架构内)

#### 改进1: 增加IMM多模型滤波
**目标**: 提升机动目标跟踪性能

**方案**:
- 实现CV、CA(恒加速)、CT(协调转弯)三模型
- 模型转移概率矩阵标定
- 模型概率加权输出

**实施**:
```python
class IMMFilter:
    models = [CVModel(), CAModel(), CTModel()]
    transition_matrix = [[0.9, 0.05, 0.05],
                         [0.05, 0.9, 0.05],
                         [0.05, 0.05, 0.9]]  # 需AirSim标定

    def update(self, measurement):
        # 1. 模型预测
        # 2. 似然计算
        # 3. 模型概率更新
        # 4. 状态混合
```

**验证**:
- AirSim场景: 目标突然加速、转弯
- 对比指标: RMSE、协方差一致性(NEES)
- 成功标准: 机动阶段RMSE < 15m (当前~26m)

**参考**: Stone Soup IMM示例、Bar-Shalom《Estimation with Applications to Tracking and Navigation》

#### 改进2: 传感器健康监测(FDIR)
**目标**: 及时检测与隔离故障传感器

**方案**:
- Innovation监测: 连续N次超过门限→degraded
- 协方差一致性检查(NIS、NEES)
- 传感器级健康评分

**实施**:
```python
class SensorHealthMonitor:
    def check_innovation(self, innovation, S, threshold=9.21):  # chi2_3_0.05
        nis = innovation.T @ inv(S) @ innovation
        if nis > threshold:
            self.fault_count[sensor_id] += 1

        if self.fault_count[sensor_id] > MAX_FAULTS:
            self.mark_degraded(sensor_id)
```

**验证**:
- 故障注入: 雷达偏差+10m、光电漂移
- 检测延迟: <3秒
- 误报率: <5%

**参考**: PX4 EKF2健康检查、NASA FDIR手册

#### 改进3: 协方差上下界限制
**目标**: 防止协方差发散或过度收敛

**方案**:
- 预测阶段: 协方差上限(基于物理约束)
- 更新阶段: 协方差下限(传感器物理精度)
- 重置机制: 协方差过大时请求重新初始化

**实施**:
```python
# 位置协方差上限: 雷达视距
P_position_max = (radar_range * 0.1) ** 2

# 速度协方差上限: 目标最大速度
P_velocity_max = (target_max_speed * 0.5) ** 2

# 下限: 传感器物理精度
P_position_min = sensor_precision ** 2
```

**验证**:
- 长时间外推场景
- 传感器突然恢复场景

#### 改进4: 时间戳不确定性建模
**目标**: 处理真实系统的时钟误差

**方案**:
- timestamp附带不确定性±Δt
- 状态预测考虑时间不确定性
- NTP同步质量监测

**实施**:
```python
class TimestampUncertainty:
    def predict_with_time_uncertainty(self, dt, dt_sigma):
        # 时间不确定性传播到状态协方差
        Q_time = self.compute_time_induced_covariance(dt_sigma)
        P_predicted = F @ P @ F.T + Q + Q_time
```

**参考**: ROS2时间同步、MISB ST 0601时间戳标准

### 4.2 中期改进 (3-6个月，局部模块升级)

#### 改进5: Track-to-Track融合架构
**目标**: 支持分布式传感器网络

**方案**:
- 各传感器节点独立维护局部航迹
- 中心节点执行Track-to-Track融合
- 协方差交叉(CI)避免信息重复计数

**架构**:
```
传感器节点1 -> LocalTrack1 ──┐
传感器节点2 -> LocalTrack2 ──┼──> Track-to-Track Fusion -> GlobalTrack
传感器节点3 -> LocalTrack3 ──┘
```

**CI算法**:
```python
def covariance_intersection(track1, track2):
    # Julier-Uhlmann CI公式
    omega = optimize_omega(P1, P2)  # 最小化融合协方差迹
    P_fused = inv(omega * inv(P1) + (1-omega) * inv(P2))
    x_fused = P_fused @ (omega * inv(P1) @ x1 + (1-omega) * inv(P2) @ x2)
    return x_fused, P_fused
```

**验证**:
- 二级侦察节点作为独立传感器
- 对比集中式与T2T融合性能
- 通信带宽降低>50%

**参考**:
- Stone Soup Track-to-Track示例
- Julier & Uhlmann "A Non-divergent Estimation Algorithm in the Presence of Unknown Correlations"
- Anduril分布式融合专利

#### 改进6: 场景自适应协方差调整
**目标**: 根据环境动态调整过程/观测噪声

**方案**:
- 定义场景类型(开阔、城市、低空、高空)
- 每种场景标定噪声参数
- 在线场景识别

**实施**:
```python
class AdaptiveCovariance:
    scenarios = {
        'open_field': {'Q_scale': 1.0, 'R_radar_scale': 1.0},
        'urban_low': {'Q_scale': 1.5, 'R_radar_scale': 2.0},  # 多径
        'high_altitude': {'Q_scale': 1.0, 'R_radar_scale': 0.8},
    }

    def adapt_to_scenario(self, altitude, terrain_type):
        scenario = self.identify_scenario(altitude, terrain_type)
        self.Q *= self.scenarios[scenario]['Q_scale']
        self.R_radar *= self.scenarios[scenario]['R_radar_scale']
```

**验证**:
- AirSim不同高度、地形场景
- 协方差一致性检查(NEES)
- 期望: NEES ∈ [0.8, 1.2]

#### 改进7: UKF用于非线性观测
**目标**: 替代EKF雅可比线性化

**方案**:
- 光电像素观测使用UKF
- Sigma点采样(scaled/unscented transform)
- 保留EKF用于雷达(线性观测)

**实施**:
```python
class UKFVisionUpdate:
    def compute_sigma_points(self, x, P, kappa=3-n):
        # Scaled sigma points
        sigma_points = [x]
        L = cholesky((n + kappa) * P)
        for i in range(n):
            sigma_points.append(x + L[:, i])
            sigma_points.append(x - L[:, i])
        return sigma_points

    def update_with_vision(self, pixel_measurement):
        # 传播sigma点到像素空间
        # 计算加权均值和协方差
        # 卡尔曼更新
```

**验证**:
- 大俯仰角光电观测场景
- 对比EKF vs UKF像素误差
- 期望: 非线性场景UKF RMSE降低20%

**参考**: Julier & Uhlmann UKF原始论文、Stone Soup UKF实现

#### 改进8: 传感器管理与主动探测
**目标**: 根据任务需求调度传感器资源

**方案**:
- 信息增益计算(posterior vs prior熵减)
- 传感器任务分配(指向、功率、模式)
- 与D3分配模块接口

**实施**:
```python
class SensorManager:
    def compute_information_gain(self, sensor, target):
        # 预测观测
        z_pred, S = sensor.predict_observation(target.state, target.P)

        # 信息增益 = 熵减
        info_gain = 0.5 * log(det(S) / det(sensor.R))
        return info_gain

    def allocate_sensors(self, targets, sensors):
        # 匹配传感器到最大信息增益目标
        assignment = hungarian(info_gain_matrix)
        return assignment
```

**验证**:
- 二级侦察节点动态指向
- 对比固定扫描 vs 自适应指向
- 目标不确定性降低>30%

**参考**:
- Hero et al. "Sensor Management for Multi-Target Tracking"
- SAPIENT Sensor Tasking接口

### 4.3 长期改进 (6-12个月，架构调整)

#### 改进9: SAPIENT标准对齐
**目标**: 与工业标准互操作

**方案**:
- SensorObservation映射到SAPIENT Detection消息
- 支持SAPIENT Sensor Registration
- 实现SAPIENT Status Report

**SAPIENT消息示例**:
```xml
<Detection>
  <timestamp>2026-07-08T10:30:45.123Z</timestamp>
  <objectID>TGT_001</objectID>
  <position>
    <latitude>39.123456</latitude>
    <longitude>-77.234567</longitude>
    <altitude>150.5</altitude>
    <covariance type="CEP95">25.0</covariance>
  </position>
  <classification>
    <type>SMALL_UAV</type>
    <confidence>0.85</confidence>
  </classification>
</Detection>
```

**实施路径**:
1. 定义SAPIENT adapter
2. 映射坐标系(WGS84 ↔ NED)
3. 测试与SAPIENT模拟器互操作

**参考**: SAPIENT ICD v6.1规范

#### 改进10: 粒子滤波备用链路
**目标**: 处理非高斯、多模态场景

**方案**:
- 实现Bootstrap粒子滤波器
- 触发条件: EKF协方差发散、多假设
- 降级使用(计算量大)

**验证**:
- 杂波密集场景
- 多径场景
- 目标突然出现/消失

**参考**: Arulampalam et al. "A Tutorial on Particle Filters"

---

## 5. AirSim/封闭场地验证方案

### 5.1 测试场景设计

#### 场景1: 常速目标基线
- 5个目标，恒速直线飞行
- 雷达1Hz、光电5Hz、声学0.5Hz
- 验证基础融合性能

#### 场景2: 机动目标
- 目标突然加速、减速、转弯
- 验证IMM性能
- 对比CV vs IMM RMSE

#### 场景3: 传感器故障
- 雷达偏差注入(t=30s, +10m bias)
- 光电间歇性丢失(t=45-55s)
- 验证FDIR检测延迟

#### 场景4: 长时间外推
- 所有传感器失效10秒
- 验证协方差上限机制
- 恢复后收敛时间

#### 场景5: 分布式传感器
- 3个独立雷达节点
- 二级侦察节点
- 验证Track-to-Track融合

### 5.2 成功指标定义

| 指标 | 当前基线 | 短期目标 | 中期目标 |
|------|----------|----------|----------|
| 常速RMSE | 9.5m | <8m | <6m |
| 机动RMSE | ~26m | <15m | <10m |
| 协方差一致性(NEES) | 未测 | 0.8-1.2 | 0.9-1.1 |
| FDIR检测延迟 | N/A | <3s | <1s |
| T2T融合开销 | N/A | <100ms | <50ms |

### 5.3 故障注入计划

- **传感器故障**: 偏差、漂移、丢包、延迟
- **时间同步**: 时钟漂移±50ms
- **杂波**: 虚警率10%
- **遮挡**: 视线阻挡5秒
- **多径**: 雷达反射+噪声

### 5.4 对比基准

- **Baseline**: 当前NumPy EKF + CV
- **IMM**: CV/CA/CT三模型
- **UKF**: Unscented变换
- **Stone Soup**: 完整工具链
- **简化版**: 仅延迟补偿，无协方差

---

## 6. 实施风险与缓解

### 6.1 技术风险

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| IMM模型切换抖动 | 跟踪不稳定 | 中 | 保守转移概率、平滑输出 |
| UKF数值不稳定 | 协方差非正定 | 中 | SRUKF、UD分解 |
| T2T融合信息丢失 | 性能劣化 | 低 | CI保守融合 |
| FDIR误报 | 传感器误禁用 | 中 | 多准则融合、人工复核 |

### 6.2 集成风险

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 破坏现有D2接口 | 下游失效 | 保持GlobalTrack接口不变 |
| 性能下降 | 实时性不足 | 增量实现、性能剖析 |
| AirSim不兼容 | 无法验证 | 保留NumPy fallback |

### 6.3 性能风险

- **计算开销**: IMM/UKF增加2-3倍计算量
  - 缓解: 仅关键目标使用、C++重写
- **内存占用**: T2T需维护多份航迹
  - 缓解: 航迹合并、老化删除
- **实时性**: AirSim仿真已非实时
  - 缓解: 离线处理可接受

---

## 7. 参考案例与文献

### 7.1 工业系统
1. **Anduril Lattice**: 分布式传感器融合, <https://www.anduril.com/lattice/>
2. **Rafael Drone Guard**: IMM多模型, <https://www.rafael.co.il/worlds/air-missile-defense/counter-uas/>
3. **Dedrone RF/视觉融合**: <https://www.dedrone.com/>
4. **Fortem TrueView雷达**: <https://www.fortemtech.com/>

### 7.2 军方标准
1. **UK SAPIENT标准**: <https://www.gov.uk/government/publications/sapient>
2. **NATO STANAG 4607**: GMTI数据格式
3. **MISB ST 0601**: UAS元数据标准
4. **FAA C-UAS技术考虑**: <https://www.faa.gov/airports/airport_safety/Attachment-3-UAS-Detection-Technical-Considerations.pdf>

### 7.3 开源工程实现
1. **PX4 EKF2**: <https://github.com/PX4/PX4-Autopilot/tree/main/src/modules/ekf2>
2. **Stone Soup**: <https://github.com/dstl/Stone-Soup>
3. **FilterPy**: <https://github.com/rlabbe/filterpy>

### 7.4 学术文献（工程导向）
1. Bar-Shalom, Y., et al. "Estimation with Applications to Tracking and Navigation" (经典教材)
2. Blackman, S., Popoli, R. "Design and Analysis of Modern Tracking Systems" (工程实践)
3. Julier, S., Uhlmann, J. "Unscented Filtering and Nonlinear Estimation" (UKF原始论文)
4. Bar-Shalom, Y. "Update with Out-of-Sequence Measurements in Tracking" (OOSM处理)
5. Niehsen, W. "Information Fusion Based on Fast Covariance Intersection Filtering" (CI快速算法)

### 7.5 JRC报告
- **JRC C-UAS报告**: <https://publications.jrc.ec.europa.eu/repository/handle/JRC140692>
- **欧洲C-UAS技术评估**

---

## 8. 实施优先级建议

### P0 (立即实施)
1. **传感器健康监测(FDIR)** - 提升系统鲁棒性
2. **协方差上下界限制** - 防止发散
3. **时间戳不确定性** - 真实环境必需

### P1 (3个月内)
1. **IMM多模型滤波** - 显著提升机动目标性能
2. **场景自适应协方差** - 环境适应性

### P2 (6个月内)
1. **Track-to-Track融合** - 分布式架构需求
2. **UKF非线性观测** - 光电融合增强
3. **传感器管理** - 二级节点主动感知

### P3 (长期)
1. **SAPIENT标准对齐** - 工业互操作
2. **粒子滤波备用** - 极端场景

---

## 9. 结论

当前D1传感器融合模块已实现轻量可用的基础融合能力，但在**机动目标跟踪、传感器故障处理、分布式融合、真实环境适应**方面存在明显不足。

**推荐改进路径**：
1. **短期**：增加IMM、FDIR、协方差限制 - 显著提升鲁棒性
2. **中期**：Track-to-Track、场景自适应 - 支持分布式部署
3. **长期**：SAPIENT对齐 - 工业标准互操作

所有改进均有成熟工业案例支撑(Anduril、PX4、SAPIENT)，可在AirSim和封闭场地验证，不引入未经验证的学术算法。

---

**文档维护者**: 框架评估工作组
**下次更新**: 完成短期改进后
