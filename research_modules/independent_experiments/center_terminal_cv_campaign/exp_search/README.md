# 区域搜索独立实验

本目录包含两套相互独立的搜索验证。旧AirSim接口试验使用精度和召回率均为80%的固定线索夹具；2026-08-19新增的离线矩阵假设每个目标都有一条正确中心线索，只考察30、60、100米粗位置误差下的搜索调度。两套试验均与D1-D7和既有双光电实验解耦，结果不能混用。

## 100%线索离线矩阵

新入口 `run_offline_matrix.py` 读取既有AirSim搜索episode保存的Actor运动记录。20目标/8机、20目标/30机和40目标/50机分别使用对应规模的保存轨迹。每个目标生成一条匿名中心线索；北、东、地三个方向按指定标准差实际注入有seed的零均值误差，并截断在三倍标准差内。在线分配记录不含Actor名称和目标真实编号。

每条线索的三倍标准差区域按1920×1080、水平视场19度、700米观察距离的相机足迹划分，垂直视场由画幅比例推得10.75度，相邻子单元保留20%重叠。滚动收益矩阵通过匈牙利算法执行一一分配。平台速度按97米/秒、云台转速按200度/秒、每个观察点按0.3秒计算；预计不能在18秒内完成的候选不执行。

离线观测使用运动后的相机位置和云台角建立真实针孔视锥。目标进入视锥且检测框最长边达到10像素后才形成匿名检测，连续两帧确认。任务获得分配不计作观察，只有实际到位和完成取帧才更新覆盖。负观测只消除实际视锥覆盖到的子单元概率。真值只在离线观测生成和最终评分中使用。

正式矩阵包含3个规模、3档误差和5个seed，共45组。20目标/8机在30、60、100米档的平均连续确认率为100%、97%和91%，后两档最差seed分别为90%和80%。20目标/30机和40目标/50机三档均为100%。45组在线真值泄漏均为0。

```bash
PYTHONPATH=research_modules/independent_experiments \
python3 -m center_terminal_cv_campaign.exp_search.run_offline_matrix
```

证据位于 `../outputs/offline_search_100pct_cues_20260819/`。其中包含逐组配置、指标、匿名在线记录、独立真值、输入哈希、矩阵汇总和复现清单。该目录属于生成输出，不作为源码提交。

证据限制如下：保存轨迹只到0.8秒，之后17.2秒按保存速度线性外推；资源从北向2100米的前出待机线开始；97米/秒和200度/秒是仿真假设；没有加入随机漏检、虚警、导航误差、碰撞和通信延迟。搜索确认只表明视场内形成稳定视觉目标，不等同于中心线索与机载航迹完成身份绑定。

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

## 旧AirSim接口验证状态

截至2026-08-16，离线假客户端、匿名化、10像素门限、连续两帧确认、匈牙利唯一分配、空档单元补获和N规模测试已实现。

- v1真实AirSim试验使用20目标、8资源、3轮和每单元2帧，确认18/20。未确认的 `TGT-009`、`TGT-012` 均达到过10像素门限，但没有连续两帧。
- v3最终重跑使用相同目标规模、资源和seed，每单元改为3帧。20/20目标均被检测且至少一次达到10像素门限，最终确认19/20；唯一未确认目标为 `TGT-007`。
- v3中心漏检目标补获3/4，已确认交接精度为1.0，错误确认数为0，在线真值泄漏为0。

三帧驻留使确认数由18提高到19，并找回v1中的两个未确认目标。`TGT-007` 在v3中仅于不连续的第6、8帧出现，说明AirSim `detect` 运行波动仍会阻断连续确认。详细证据及版本边界见 [20目标区域搜索诊断](AIRSIM_N20_FORMAL_DIAGNOSIS_CN.md)。20/25/30/40资源和多seed结果仍待main统一验证。

2026-08-16增加一次规模压力运行。20目标/30资源覆盖28/28个搜索单元，20/20目标完成连续确认，中心漏检补获4/4，规划平均耗时11.739毫秒。40目标/50资源覆盖56/56个搜索单元，40/40目标完成连续确认，中心漏检补获8/8，规划平均耗时35.753毫秒。两组使用同一Blocks进程和同一seed，只能作为容量与接口证据；20/25/30/40资源的独立多seed曲线仍未完成。
