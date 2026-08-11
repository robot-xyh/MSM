# 双光电40目标轨迹关联独立试验

本目录验证两个旋转光电节点在AirSim中对40个移动目标形成匿名本地轨迹并完成跨相机一对一关联。试验与D1-D7隔离，不使用中心全局航迹、目标分配合同或D5数据结构。

## 运行

从项目根目录执行：

```bash
python3 research_modules/independent_experiments/dual_optical_40target/run_experiment.py
```

默认启动一次Blocks，完成3米目标网格预检，reset后运行种子20260810的12秒正式试验，最后关闭Blocks并生成中文报告。

外部已经启动匹配settings的Blocks时可使用：

```bash
python3 research_modules/independent_experiments/dual_optical_40target/run_experiment.py --no-launch
```

已有完整记录时，可在不启动AirSim的条件下重新生成图表和报告：

```bash
python3 research_modules/independent_experiments/dual_optical_40target/run_experiment.py \
  --report-only \
  --output-dir research_modules/independent_experiments/dual_optical_40target/outputs/airsim_seed_20260810_run11
```

## 输出

默认输出目录为：

`research_modules/independent_experiments/dual_optical_40target/outputs/airsim_seed_20260810/`

- `online/`：匿名检测、扫描状态、本地轨迹、候选代价和匈牙利匹配；
- `truth/`：只供运行结束后评分的Actor身份和真实轨迹；
- `keyframes/`：按要求保存的相机关键帧；
- `figures/`：三维场景、扫描、本地轨迹、代价矩阵和配准结果图；
- `metrics.json`：验收指标；
- `DUAL_OPTICAL_40TARGET_AIRSIM_REPORT_CN.md`：中文实验报告。

## 实测结果

2026年8月10日完成种子20260810的单次正式AirSim试验，有效记录位于`outputs/airsim_seed_20260810_run11/`。两台相机均检测到全部40个目标，稳定轨迹真值覆盖率均为1.000。A侧形成50条稳定轨迹，B侧形成47条，说明扫描重访过程仍有轨迹碎片。

跨相机关联输出37组关系，其中36组正确、1组错误，准确率为0.973，全目标召回率为0.900。在线真值泄漏为0，平均三维位置拟合误差为0.080米。结果通过本轮95%准确率和80%召回率门限，但未达到40个目标全部正确配准；4个目标未形成正确关系。

## 测试

```bash
PYTHONPATH=research_modules/independent_experiments \
pytest -q research_modules/independent_experiments/dual_optical_40target/tests
```

图神经网络不在本轮实现范围内。当前只保留可解释的恒速几何拟合和匈牙利算法基线。
