# Scalable 3D Simulation

该 main-owned 模块提供可复现、真值隔离的三维质点环境，用于逐步建设 200 架拦截无人机
对 200 个来袭目标的 D1-D7 完整闭环。现有 `integrated_simulation` 保留为小规模回归基线。

当前阶段已实现世界状态、三维动力学、透视投影、传感器场景、通信模型、版本化 episode
总线和确定性环境基线。`IntegratedScalableModuleStack` 已把 D1 六维融合、D2 稀疏关联、
D3 稀疏分配、D4 区域权限、D5 匿名跨视角配准和 D7 三维比例导引接入同一在线时钟。
模块栈只做接口转换与调度，各算法仍由 D1-D7 原模块维护。

## 运行

```bash
python3 research_modules/scalable_3d_simulation/run_episode.py \
  --drone-count 200 \
  --duration 10 \
  --integrated-stack \
  --output research_modules/scalable_3d_simulation/outputs/smoke_200v200
```

三维静态图、GIF 和 MP4 只在需要时显式增加 `--plot`、`--gif` 或 `--mp4`。动画读取离线
真值状态文件，不进入在线 D1-D7 总线。

批量课程测试：

```bash
python3 research_modules/scalable_3d_simulation/run_batch.py \
  --scales 5 20 50 100 200 \
  --seeds 7 17 27 \
  --scenarios nominal dense_crossing formation_split evasive_multilevel \
  --integrated-stack
```

场景目录还包含时延噪声、通信退化、中心失效、二级失效和高威胁多机需求配置。单一二级
节点接管已接入；区域多二级计划和完全分布式 D3 计划仍保持闭锁，配置文件存在不等同于
相应能力已经验收。

默认不生成 200 路图像。相机模块只输出匿名 bbox、像素中心、投影协方差和独立离线真值
标签。远距离投影只有达到相机类型对应的最小 bbox 面积后才形成在线视觉观测，避免把
亚像素投影误报为可用检测。高频状态写入压缩 NPZ，事件写入 JSONL，汇总写入 JSON、
CSV 和中文 Markdown。

传感器场景包含中心雷达、分布式声学阵列和拦截/侦察相机。声学观测输出粗方位、协方差
和类别级声纹概率，`soundprint_is_identity=False`，不能作为目标身份编号使用。

`ScalableModuleStack` 是后续 D1-D7 的统一在线端口。输入只包含本时刻到达的匿名传感器
批次以及拦截机、侦察机自身导航状态；输出为 NED 三维加速度和版本化模块记录。目标真值
状态不会通过该端口传入在线模块，模块记录仍经过递归真值字段检查。

## 当前验证

2026-07-20 的 main 集成回归为 **30/30 passed**。其中 5v5、seed 7、1.2 秒场景形成
5 条 D1 航迹、5 条 D2 中心航迹、5 项 D3 分配和 5 路 D7 中段指令，在线真值字段使用为
0。200v200、seed 17、0.25 秒雷达烟测形成 200 条 D1/D2 航迹和 200 项分配；D3 从
40000 个完整 pair 中保留 6400 条候选边，D7 输出 `(200, 3)` 有限加速度。

中心失效场景已验证单一高空侦察节点覆盖全部活动区域时，D3 计划由版本 1 更新为版本 2，
owner 切换为 `RECON-001`，D4 八个区域允许继续执行。二级节点再次失效时，D4 能进入
distributed candidate，但当前没有与其匹配的 D3 分布式计划合同，因此八个区域和 D7 均
fail closed。该结果是接口和质点仿真证据，不是 AirSim、真实网络或实飞证据。

同一 seed、0.25 秒、仅启用雷达的短时规模测试结果如下。该数据用于定位开销，不作为
长时多 seed 验收结果。

| 目标/资源规模 | 实时因子 | D3 分配累计耗时/ms |
| ---: | ---: | ---: |
| 5 | 8.54 | 3.2 |
| 20 | 2.32 | 25.5 |
| 50 | 0.61 | 136.5 |
| 100 | 0.28 | 495.2 |
| 200 | 0.09 | 1970.7 |

200v200 条件下，D1、D2 和 D7 的累计耗时分别约为 120.0、107.8 和 20.3 毫秒，D3
约为 1970.7 毫秒，是当前首要性能瓶颈。D3 虽将 40000 条完整资源目标边压缩到 6400
条候选边，内部代价构造或求解仍存在密集矩阵和 Python 循环开销。episode 输出现在同时
记录世界、传感器、在线发布总线和 `module.d1_fusion` 至 `module.d7_guidance` 的分阶段
累计耗时。在线真值字段检查保持递归覆盖，已改为循环安全的迭代扫描并缓存重复字段名，
避免大批量航迹发布时重复执行昂贵的类型解析。外部模块发布仍默认深拷贝；集成模块栈对
每次新建且不再修改的负载显式转移所有权，省去一次大型航迹负载复制，真值扫描仍然执行。

当前尚未完成阶段耗时优化、长时多 seed 或 200-camera 图构建。D5 默认使用几何规则
回退；现有图网络只有训练管线 smoke，没有独立验证 checkpoint。区域多二级 owner、完全
分布式 D3 计划、D6 规模评估和学习策略验收仍是后续 P1/P2 工作。

每个物理步结束后，离线评估侧按三维 5 米门限登记唯一接近事件。事件中的真值目标号只
写入 `offline_proximity_intercepts.jsonl`，不进入在线总线；D6 还需结合分配与身份映射
判断该物理接近是否属于正确任务。

## 版本

- 世界：`scalable3d-world-v1`
- 总线：`scalable3d-episode-bus-v1`
- 场景：`scalable3d-scenario-v1`
- 在线观测：`scalable3d-observation-v1`
- 离线真值：`scalable3d-offline-truth-v1`

每个 episode 的 `manifest.json` 记录上述版本、Git commit、配置 SHA256、seed、模型版本和
阈值版本。在线总线拒绝任何包含 truth/actor/object identity 字段的观测负载。

分支、提交、模型制品和阶段标签规则见 [VERSIONING.md](VERSIONING.md)。
