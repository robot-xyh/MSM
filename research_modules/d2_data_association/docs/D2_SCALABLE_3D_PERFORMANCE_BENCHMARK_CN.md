# D2 200 规模关联热路径基准

## 结论

2026 年 7 月 22 日完成 200 目标、200 资源、5 个随机种子的 D2 第二阶段性能对照。候选
实现保持三维门控、全局最近邻和匈牙利算法不变，只减少在线身份元数据审计中的重复工作。
每个种子包含 8 个常规关联周期和 1 个尾部收束周期，共比较 45 个 D2 发布周期。

候选实现的常规关联平均累计墙钟由 `7.5552 s` 降至 `2.2033 s`，加速 `3.429` 倍；
尾部收束平均累计墙钟由 `2.2747 s` 降至 `0.5646 s`，加速 `4.029` 倍。单个 episode
的 D2 总墙钟均值由 `9.8299 s` 降至 `2.7679 s`，加速 `3.551` 倍。五个种子的 D2
总墙钟由 `49.1497 s` 降至 `13.8397 s`。

45/45 个周期的完整 D2 发布、关联结果、规范身份与生命周期、声明账本与审计哈希全部
一致。基线和候选的在线真值使用均为 0。该结果证明本轮改动在冻结输入上保持 D2 发布
语义，不构成实时服务等级、真实 AirSim 性能或物理拦截结论。

![五组运行耗时对比](d2_scalable_3d_performance_by_seed.png)

## 冻结输入

基线使用 clean 校准目录
`research_modules/scalable_3d_simulation/outputs/scalable_3d_rule_performance_calibration_20260722_clean_492979e`。
场景相对目录为 `nominal/200v200`，随机种子为 42000 至 42004。候选使用同一场景配置、
离线真值 sidecar 和随机种子重新运行。基线与候选的场景配置文件及离线真值文件逐 seed
执行 SHA-256 对照，五组均一致。

本轮候选原始 episode 位于临时目录，不作为源文件保留。机器可读比较结果保存在
`outputs/scalable_3d_performance_20260722/d2_scalable_3d_performance_comparison.json`，
其 SHA-256 为
`955c1e5e3d5e113e6ffe11f0524d4f38a02bbaa8ea5c3eca33682faff28539d2`。

## 热点定位

优化前单 seed 全流程的 `cProfile` 累计调用时间显示，身份元数据递归审计约为
`31.805 s`，D1 后验到 D2 检测适配约为 `22.133 s`，Tracker step 约为 `11.516 s`。
这些数值是嵌套函数累计时间，不能与阶段墙钟相加。它们说明主要开销来自同一有限键集合
的字符串归一化、禁用身份键判断和重复递归扫描，匈牙利求解并非该批输入的主要热点。

候选 profile 中，身份审计、适配器和 Tracker step 的累计调用时间分别降至
`6.694 s`、`5.317 s` 和 `2.988 s`。稀疏全局最近邻/匈牙利求解累计约 `0.136 s`，
航迹更新累计约 `0.284 s`。因此本轮没有调整门限、候选图、代价函数或求解器。

## 实施内容

本轮只实施一组紧密相关的等价优化：

1. 运行时映射检查使用 `collections.abc.Mapping`。
2. 元数据键归一化和禁用身份键分类使用容量为 1024 的有界缓存。
3. 身份域名前缀和后缀判断改用原生元组形式的 `startswith` 和 `endswith`。
4. D1 后验适配器删除一次冗余预扫描。`Detection3D` 构造仍执行完整递归审计，
   `Scalable3DTracker.step()` 仍再次检查输入，可继续阻断构造后的 metadata 篡改。

缓存只保存字符串到分类结果，不保存 observation、track、claim 或 episode 数据。缓存
容量固定，不随目标数和 episode 长度增长。

## 分阶段结果

| 随机种子 | 常规关联优化前 / 后（秒） | 尾部收束优化前 / 后（秒） | 周期数 | 语义一致 |
| ---: | ---: | ---: | ---: | --- |
| 42000 | 5.8620 / 1.7287 | 1.9134 / 0.4731 | 9 | 是 |
| 42001 | 8.0012 / 2.1836 | 2.5804 / 0.5972 | 9 | 是 |
| 42002 | 9.2124 / 2.5737 | 2.4199 / 0.5771 | 9 | 是 |
| 42003 | 7.6449 / 2.1538 | 2.2851 / 0.5748 | 9 | 是 |
| 42004 | 7.0556 / 2.3768 | 2.1748 / 0.6010 | 9 | 是 |
| 均值 | 7.5552 / 2.2033 | 2.2747 / 0.5646 | 9 | 是 |

## 语义合同

比较器把运行时字段与在线发布分开。每个周期分别计算以下规范哈希：

- 完整 D2 发布记录；
- 匹配、未匹配、拒配和关联审计；
- `global_track_id`、状态、协方差和生命周期；
- observation claim ledger、replay、stale、overflow 与 truth-isolation 审计。

五个种子的四类聚合哈希和 45 个逐周期哈希全部相等。`global_track_id` 仍由中心 D2
创建；claim ledger、生命周期状态机、显式 `id_switch_count=None/unavailable` 和
continuity unavailable 语义没有改变。比较过程读取离线真值文件只用于确认两次运行输入
相同，不把真值交给在线关联。

## 复现

```bash
PYTHONPATH=research_modules/d2_data_association \
python3 research_modules/d2_data_association/scripts/run_scalable_3d_performance_comparison.py \
  --baseline-root research_modules/scalable_3d_simulation/outputs/scalable_3d_rule_performance_calibration_20260722_clean_492979e \
  --candidate-root /path/to/candidate-output \
  --relative-scenario-dir nominal/200v200 \
  --seeds 42000 42001 42002 42003 42004 \
  --output /tmp/d2-scalable-performance.json \
  --plot /tmp/d2-scalable-performance.png
```

比较器要求两侧存在相同 seed 的 D2 在线记录、阶段计时、场景配置和离线真值 sidecar。
任一必需阶段缺失、记录为空或输入哈希不同都会使验收失败。

## 限制

- 候选运行来自未提交工作树，当前结果属于开发态性能证据。正式晋级仍需 clean-tree
  复跑并冻结运行环境。
- 墙钟包含同一主机上的 Python 调度和文件处理，不是单周期控制延迟，也没有给出并发
  负载下的最坏时延保证。
- 场景只有 `nominal/200v200` 五个 seed。极端全重叠候选图、长时间遮挡、杂波、乱序
  量测和真实 AirSim 输入仍需分别评估。
- 本轮未改变全局最近邻/匈牙利、三维门控、生命周期或 claim 策略，因此不提供新的
  ID Switch 改善结论。在线无真值时，ID Switch 和连续性继续显式不可用。
