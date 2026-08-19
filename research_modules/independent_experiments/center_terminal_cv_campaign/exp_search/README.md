# 区域搜索独立实验

本目录验证中心源线索精度和召回率均为80%时的多机区域搜索。实验与D1-D7、既有双光电实验解耦，只使用 `center_terminal_cv_campaign/common` 的共享合同和固定夹具。

## 已实现

- 中心源线索生成指向性概率单元，搜索走廊同时生成不绑定源航迹的空档单元。
- 按目标概率、预计探测收益、相机转向、到达距离和重复覆盖计算收益，并使用SciPy匈牙利算法进行N规模唯一分配。
- 为ComputerVision节点生成位置和朝向命令。AirSim适配器只连接、控制和读取，不启动、重置或关闭Blocks。
- Terminal节点初始状态与公共settings一致为世界NED原点；运行位姿命令使用世界NED绝对值，不叠加settings起点。
- `simGetDetections` 对象名称在读取后立即转入离线评分映射。在线检测只保留匿名本地编号、检测框、视线和双时间戳。
- 检测框最长边达到10像素且连续两帧满足条件后才形成交接记录。每个单元默认观察3帧，为一次刷新延迟或瞬时漏检保留余量；非连续帧不能确认。
- 支持离线几何假客户端和脚本假客户端，输出结构与真实AirSim入口一致。
- 固定输出 `metrics.json`、`metrics.csv`、在线检测、搜索分配、交接记录、离线真值、覆盖图、首次发现图和 `REPORT_CN.md`。

## 运行

从仓库根目录执行：

```bash
PYTHONPATH=research_modules/independent_experiments \
python3 -m center_terminal_cv_campaign.exp_search.run_experiment \
  --mode offline \
  --target-count 5 \
  --resource-count 8 \
  --output-dir /tmp/msm_search_smoke
```

正式配置可分别传入 `--target-count 20 --resource-count 20|25|30|40`。算法不依赖这些固定规模。

默认每个单元观察3帧。可使用 `--frames-per-assignment` 显式调整，但不得低于连续确认所需的2帧。

`--fixture-dir` 接收 `prepare_campaign.prepare_fixture` 生成的共享夹具目录。规范文件为：

- `online/source_cues.jsonl`；
- `truth/source_cue_labels.jsonl`；
- `truth/targets.jsonl`；
- `scenario.json`。

使用共享夹具且未传入 `--target-count`、`--seed` 时，入口从 `scenario.json` 推断。显式传入的规模或seed与场景不一致时直接报错，不覆盖夹具声明。

main也可直接调用：

```python
from center_terminal_cv_campaign.exp_search.run_experiment import run_experiment

result = run_experiment(
    mode="airsim",
    fixture_dir=fixture_dir,
    output_dir=output_dir,
    target_count=20,
    resource_count=40,
    client=connected_client,
)
```

真实模式要求main已经启动Blocks、加载Common生成的ComputerVision设置并放置目标Actor。本入口不会接管Blocks生命周期，也不会移动目标Actor。

## 验证状态

截至2026-08-16，离线假客户端、匿名化、10像素门限、连续两帧确认、匈牙利唯一分配、空档单元补获和N规模测试已实现。

- v1真实AirSim试验使用20目标、8资源、3轮和每单元2帧，确认18/20。未确认的 `TGT-009`、`TGT-012` 均达到过10像素门限，但没有连续两帧。
- v3最终重跑使用相同目标规模、资源和seed，每单元改为3帧。20/20目标均被检测且至少一次达到10像素门限，最终确认19/20；唯一未确认目标为 `TGT-007`。
- v3中心漏检目标补获3/4，已确认交接精度为1.0，错误确认数为0，在线真值泄漏为0。

三帧驻留使确认数由18提高到19，并找回v1中的两个未确认目标。`TGT-007` 在v3中仅于不连续的第6、8帧出现，说明AirSim `detect` 运行波动仍会阻断连续确认。详细证据及版本边界见 [20目标区域搜索诊断](AIRSIM_N20_FORMAL_DIAGNOSIS_CN.md)。20/25/30/40资源和多seed结果仍待main统一验证。

2026-08-16增加一次规模压力运行。20目标/30资源覆盖28/28个搜索单元，20/20目标完成连续确认，中心漏检补获4/4，规划平均耗时11.739毫秒。40目标/50资源覆盖56/56个搜索单元，40/40目标完成连续确认，中心漏检补获8/8，规划平均耗时35.753毫秒。两组使用同一Blocks进程和同一seed，只能作为容量与接口证据；20/25/30/40资源的独立多seed曲线仍未完成。
