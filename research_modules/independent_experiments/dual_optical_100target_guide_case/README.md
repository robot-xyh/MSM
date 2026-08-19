# 双站光电100目标指南案例

本目录把《双站光电交汇与100目标轨迹配准_初学者完全指南》中的可用思路整理成一个独立 AirSim ComputerVision 案例。它不依赖 D1-D7，也不向主系统发布目标编号。

## 固定场景

- 两个 ComputerVision 相机在 NED 坐标系内横向相距 4 km。
- 相机分辨率 1280×1024，水平视场角 2.93°。
- 100 个 3 m actor，初始三维最小间距大于 100 m。
- 目标水平速度 40～60 m/s，垂直速度限制在 ±20 m/s。
- 10 组目标在 `t=2.5 s` 附近确定性交叉。
- episode 长 5 s，扫描调度 100 Hz，1 s 完成一次往返，共 10 个半程扫描。
- 检测框转成世界视线后注入固定随机种子的 `0.15 mrad` 高斯测角噪声。

## 算法

1. 每台相机将匿名检测框中心转成世界坐标系单位视线。
2. 单站按视线连续性进行匈牙利匹配，并把一次半程扫描内的重复检测汇成一个重访样本。
3. 每个跨站候选计算对称归一化共面性残差序列、中位数、90%分位数、绝对中位差和漂移斜率。
4. 双站视线交会产生临时空间点，匀速直线拟合用于排除明显不符合运动规律的关系。
5. 每个半程扫描独立运行匈牙利匹配，跨 10 次扫描累计票数。
6. 最终继续使用匈牙利算法保证一对一；连续三次支持后确认，竞争关系在交叉附近保持待确认。

指南中的 `99.95%` 不作为本案例的预期结果或验收值。本实现也不采用“均方根误差必然按样本数平方根下降”“像面角速度与视角无关”“多假设跟踪保证100%”作为前提。

## 正式 AirSim 结果

seed `20260812` 已在 AirSim ComputerVision 模式完成正式 episode。该次运行取得16910次匿名检测，其中A站8521次、B站8389次。算法按长度和重访条件形成A站43条、B站29条稳定轨迹，但离线身份纯度检查表明这些轨迹存在严重串号：A/B轨迹纯度中位数分别为0.390和0.345，纯度不低于0.90的轨迹分别只有1条和0条。

跨站处理最终输出0组关系。检测链路已经工作，当前断点在单站扫描轨迹形成，而不是跨站共面性或匈牙利门限。放宽跨站门限会接纳由混合轨迹产生的错误候选，不能修复本次失败。

| 指标 | A站 | B站 | 合计或结果 |
| --- | ---: | ---: | ---: |
| 匿名检测 | 8521 | 8389 | 16910 |
| 算法形成的稳定轨迹 | 43 | 29 | 72 |
| 轨迹纯度中位数 | 0.390 | 0.345 | - |
| 纯度不低于0.90 | 1 | 0 | 1 |
| 最终跨站关系 | - | - | 0 |

这里的“稳定轨迹”表示轨迹满足算法的长度和重访条件，不表示轨迹内观测来自同一目标。正式报告和结构化记录位于 `outputs/airsim_seed_20260812_guide_run01/`。

## 运行方式

先生成 settings 和场景摘要：

```bash
PYTHONPATH=research_modules/independent_experiments \
python3 research_modules/independent_experiments/dual_optical_100target_guide_case/run_experiment.py \
  --output-dir research_modules/independent_experiments/dual_optical_100target_guide_case/outputs/airsim_seed_20260812_guide_run01
```

main 使用生成的 `settings.json` 启动 Blocks。启动、reset 和关闭均由 main 负责。本运行器只连接已启动的实例：

```bash
PYTHONPATH=research_modules/independent_experiments \
python3 research_modules/independent_experiments/dual_optical_100target_guide_case/run_experiment.py \
  --run-airsim \
  --output-dir research_modules/independent_experiments/dual_optical_100target_guide_case/outputs/airsim_seed_20260812_guide_run01
```

重建报告：

```bash
PYTHONPATH=research_modules/independent_experiments \
python3 research_modules/independent_experiments/dual_optical_100target_guide_case/run_experiment.py \
  --report-only \
  --output-dir research_modules/independent_experiments/dual_optical_100target_guide_case/outputs/airsim_seed_20260812_guide_run01
```

本次正式结果未形成最终关系，因此 `acceptance.overall_passed=false`，报告重建命令完成文件生成后会返回退出码2。该退出码反映算法验收未通过，不表示报告生成失败；应同时检查Markdown、Word、图片清单和 `record_manifest.json`。

`--synthetic-fixture` 只用于接口、算法和报告测试。其输出会明确写入 `formal_airsim_result=false`，不能当作正式 AirSim 结果。

## 输出

- `online/anonymous_detections.csv`：匿名检测、双时间戳和带噪视线。
- `online/local_track_samples.csv`：单站扫描重访轨迹。
- `online/residual_statistics.csv`：多时刻几何与运动统计。
- `online/scan_assignments.csv`：每次扫描的一对一关系。
- `online/association_states.csv`：收集证据、待确认、确认和短时保持状态。
- `online/final_matches.csv`：最终匿名关系，不含真实编号。
- `truth/`：Actor、目标和离线评分，只用于报告。
- `metrics.json`：四级对照指标和结构验收。
- `DUAL_OPTICAL_100TARGET_GUIDE_AIRSIM_REPORT_CN.md/.docx`：中文图文报告。

默认不调用 `simGetImages`，不保存 AirSim PNG。

## 当前边界

- 关联在 episode 结束后批量计算，尚不是每 0.5 s 因果增量发布。
- 当前正式证据只有 seed `20260812` 一组，不能据此给出跨seed成功率。
- 单站扫描轨迹的身份连续性尚未满足跨站配准输入要求；需要先解决半程扫描内串号和跨重访误接，再重新标定跨站门限。
- 外参漂移、时间同步误差、持续虚警和随机漏检不在本案例范围内。
- 正式 episode 墙钟耗时为37.05秒，关联计算耗时为0.70秒；这两个数只描述本机本次运行，不作为实时性能结论。

## 测试

```bash
PYTHONPATH=research_modules/independent_experiments \
pytest -q research_modules/independent_experiments/dual_optical_100target_guide_case/tests
```
