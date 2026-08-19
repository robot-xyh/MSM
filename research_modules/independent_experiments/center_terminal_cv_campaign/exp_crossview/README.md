# 拦截无人机跨视角关联独立实验

## 用途

本目录验证多个AirSim ComputerVision拦截机之间的匿名局部航迹关联。它只消费公共`LocalVisualTrackRecord`，不依赖D1、D2、D3或现有D5实现，也不读取AirSim Actor名称、对象编号和离线真实身份。

当前可运行基线为：

```text
相机内匿名成轨
-> 测量时间对齐
-> 检测框中心反投影为世界NED视线
-> 双视线最近交会和重投影
-> 运动方向、连续性和检测框尺度门控
-> 带空匹配的匈牙利一一分配
-> 连续多帧确认
-> 多相机目标簇聚合和每相机唯一性检查
-> 成熟簇跨边冗余检查
-> 短航迹多相机簇级确认
```

检测框最长边达到10像素才进入关联。没有共同几何证据时，局部航迹保持`unresolved`，不为提高召回率而强制合并。

聚类阶段增加两项确定性约束。两个成员数均不少于2的成熟簇至少需要2个不同相机对的确认关系才可合并，单条桥接边只保留为未采用证据。少于3个几何样本的短航迹不降低全局门限；它必须获得同一成熟簇内至少2台相机支持，累计对齐样本不少于4，且最强关系至少含2个样本。多个簇同时满足且代价差小于0.05时继续保持未解决。

## 运行

从项目根目录运行离线fixture：

```bash
python3 -m research_modules.independent_experiments.center_terminal_cv_campaign.exp_crossview.run_experiment \
  --fixture-dir research_modules/independent_experiments/center_terminal_cv_campaign/exp_crossview/fixtures/partial_3cam_5target_seed_20260816 \
  --output-dir research_modules/independent_experiments/center_terminal_cv_campaign/exp_crossview/outputs/partial_3cam_5target_geometry_seed_20260816 \
  --mode offline \
  --association-backend geometry \
  --scenario partial_3cam_5target \
  --seed 20260816
```

main也可直接调用：

```python
from research_modules.independent_experiments.center_terminal_cv_campaign.exp_crossview.run_experiment import run

artifacts = run(
    fixture_dir="path/to/fixture",
    output_dir="path/to/output",
    mode="offline",
    association_backend="geometry",
)
```

main注入真实Actor时间轴时使用：

```python
artifacts = run(
    fixture_dir="path/to/airsim_fixture",
    output_dir="path/to/output",
    mode="airsim",
    association_backend="geometry",
    client=actor_proxy,
    frame_advance=actor_proxy.set_crossview_frame,
    actor_name_to_truth_target={
        target.actor_name: target.truth_target_id
        for target in actor_proxy.targets
    },
    actor_name_aliases=actor_proxy.requested_name_by_actual,
)
```

`frame_advance(frame_index, timestamp)`按零基帧号调用。每个AirSim采集帧只调用一次，首帧也调用，并且调用发生在该帧任何相机位姿命令和detect采集之前。这样Actor位置、相机记录和`capture_plan`测量时间使用同一时间轴。回调异常会终止本轮采集，不会继续使用旧目标位置。

输入使用`--fixture-dir`或`--replay-manifest`二选一，并提供`--output-dir`、`--mode {offline,airsim}`和`--association-backend {geometry,gnn}`。指标固定写入`output_dir/metrics.json`，中文报告固定写入`output_dir/REPORT_CN.md`。

保存的AirSim回放通过统一清单读取，不需要把航迹、标定或真值复制到本目录：

```bash
python3 -m research_modules.independent_experiments.center_terminal_cv_campaign.exp_crossview.run_experiment \
  --replay-manifest path/to/n20_m30_replay.json \
  --output-dir path/to/output \
  --association-backend geometry \
  --camera-pair-policy sector_fov
```

统一清单采用`center-terminal-gnn-replay-v1`。本实验只读取`crossview_local_tracks`、`crossview_calibrations`、`crossview_capture_plan`和`crossview_truth`四个路径及其SHA256摘要，其他中心交接路径由对应实验读取。相对路径以清单所在目录为基准；任一必要文件缺失或摘要不一致时停止运行。在线关联先读取匿名航迹、标定和经过裁剪的相机几何，完成关联后才单独加载`crossview_truth`评分。清单中的Actor名称、离线责任区预期和真实目标编号不会进入候选生成。

```json
{
  "schema_version": "center-terminal-gnn-replay-v1",
  "scenario_id": "n20_m8",
  "campaign_seed": 20260816,
  "target_count": 20,
  "resource_count": 8,
  "test_only": true,
  "paths": {
    "crossview_local_tracks": "../crossview/captured_local_tracks.jsonl",
    "crossview_calibrations": "../fixtures/crossview/calibrations.json",
    "crossview_capture_plan": "../fixtures/crossview/capture_plan.json",
    "crossview_truth": "../crossview/truth/local_track_truth_map.json"
  },
  "sha256": {
    "crossview_local_tracks": "<sha256>",
    "crossview_calibrations": "<sha256>",
    "crossview_capture_plan": "<sha256>",
    "crossview_truth": "<sha256>"
  }
}
```

统一清单可以同时包含`scenario`、`source_cues`和中心交接真值等路径；本实验不会校验或打开这些无关项。

main可直接调用保存回放：

```python
artifacts = run(
    replay_manifest="path/to/replay_manifest.json",
    output_dir="path/to/output",
    association_backend="gnn",
    gnn_model_dir="path/to/frozen_model",
    camera_pair_policy="sector_fov",
)
```

使用`--replay-manifest`时默认采用`audit`输出模式；普通fixture和实时AirSim调用仍默认采用兼容的`detailed`模式。

## AirSim detect适配

`AirSimDetectCollector`接收main已经连接的AirSim client，调用`simGetDetections`。在线链路只向本地质心跟踪器传递检测框，生成的`LocalVisualTrackRecord`不含Actor名称或真值编号。原始检测名称单独写入`output/truth/airsim_detection_labels.jsonl`，解析后的`local_track -> truth_target`映射写入`output/truth/local_track_truth_map.json`，两者只供关联完成后的离线评分使用。

名称解析支持显式别名、精确Actor名称和最长前缀。AirSim在实例名后增加编号后缀时，可由Actor名称前缀解析；main掌握实际名到请求名映射时，通过`actor_name_aliases`显式传入。存在冲突身份的局部航迹不会按多数票强行赋真值，而是从评分映射中排除。公开接口`build_offline_truth_from_detection_labels(...)`和`score_from_offline_detection_labels(...)`可供main对已有在线结果单独评分。

`capture_plan.json`中的相机位置和姿态按世界NED直接下发给`simSetVehiclePose`，不叠加`settings.json`起点。main已经控制位姿时，可设置`"apply_vehicle_pose": false`。

AirSim模式要求fixture目录包含`calibrations.json`和`capture_plan.json`：

```json
{
  "schema_version": "terminal-crossview-airsim-capture-plan-v1",
  "apply_vehicle_pose": true,
  "camera_name": "0",
  "detection_filter": {
    "radius_cm": 1000000,
    "mesh_names": ["MSM_TargetActor_*"]
  },
  "frames": [
    {
      "measurement_timestamp": 0.0,
      "arrival_timestamp": 0.01,
      "cameras": [
        {
          "camera_id": "Terminal_CV_01",
          "position_ned_m": [0.0, 0.0, -120.0],
          "yaw_pitch_roll_deg": [0.0, 0.0, 0.0]
        }
      ]
    }
  ]
}
```

本目录不启动、重置或关闭Blocks。main负责Actor运动、episode顺序和AirSim生命周期。

## 可选图网络

`gnn.py`提供不依赖`torch_geometric`的稀疏候选边排序器。模型输入只包含时间、视线、交会和重投影残差、运动、检测框尺度及相机可信度。图网络只接收已经通过硬几何门控的候选，输出仍需经过匈牙利一一约束和连续确认。未提供冻结模型时，`--association-backend gnn`明确失败，不回退到未训练权重。

成熟簇桥接和短航迹簇级确认均为几何规则。图网络不参与这两项决定，也不是默认后端。

默认训练同时覆盖20目标和40目标合成场景，训练种子为`20263000-20263059`，验证种子为`20264000-20264019`。两组种子必须互斥，AirSim留出种子`20260816`不得作为训练、验证或初始化种子。训练入口为：

```bash
python3 -m research_modules.independent_experiments.center_terminal_cv_campaign.exp_crossview.training \
  --output-dir path/to/frozen_model \
  --target-counts 20 40 \
  --device cpu
```

冻结bundle使用`terminal-crossview-gnn-freeze-v2`，记录训练配置、节点和边特征名称、训练/验证种子、按目标规模划分的验证指标，以及`weights.pt`和`normalizer.json`的SHA256摘要。推理时会复核摘要、特征合同和测试种子隔离。清单标记`test_only=true`或`campaign_seed=20260816`时，训练入口失败关闭。

2026年8月16日已经完成20/40目标混合合成训练并冻结正式实验模型。训练集与验证集种子互斥，AirSim种子`20260816`只用于训练完成后的留出回放。合成验证集边分类精确率为0.991445、召回率为1.000000；其中20目标精确率为0.994631，40目标精确率为0.989837，两种规模的召回率均为1.000000。该模型只用于本独立实验的离线对照，不替代几何默认后端。

图网络仍只接收局部相机对中通过硬几何门控的边。融合代价固定为`0.55 × 几何代价 + 0.45 × (1 - 图网络概率)`，后续匈牙利一一匹配、连续确认和每相机唯一性约束保持不变。

## 相机对策略

`--camera-pair-policy full`保持全部活动相机两两组合。`sector_fov`从`capture_plan.json`读取`sector_index`和每帧相机姿态：同责任区相机可以配对；相邻责任区只有远场视锥在5度余量下重叠时可以配对；其他相机对在生成航迹候选前剔除。责任区真值预期、Actor名称和离线标签不参与该判断。

`candidate_audit.json`记录相机对总数、保留数、剔除数、逐帧相机对评估次数，以及候选生成、硬几何通过、锁定约束后通过、匈牙利选中、确认和待确认数量。拒绝原因按类型计数。

## 输出

- `candidate_audit.json`：相机对、候选阶段计数、拒绝原因和限量候选样本；
- `candidate_edges.jsonl`和`candidate_graph.json`：仅`detailed`模式写出的完整匿名候选及门控结果；
- `matches.jsonl`、`clusters.json`、`pending_relations.json`和`unresolved_relations.json`：在线关系；
- `metrics.json`：固定评估入口；
- `offline_truth_score.json`：仅fixture离线评分；
- `truth/offline_error_samples.json`：限量错误关系和身份混合样本，默认最多100条；
- `figures/`：NED俯视图、高度侧视图、像素轨迹和关系图；
- `REPORT_CN.md`：中文实验报告。

`audit`模式不会写`candidate_edges.jsonl`和`candidate_graph.json`，并在同一输出目录重跑时清除这两个旧文件。内存中也只保留配置上限内的通过/拒绝候选样本和短航迹确认所需的最小证据。默认候选样本上限为200，可通过`--candidate-sample-limit`调整。`detailed`模式保留原有完整候选输出，适合小场景逐边检查。

图表采用NED俯视图与高度侧视图组合，不使用当前环境不可用的`Axes3D`。

## 验证

2026年8月16日完成本目录测试。假AirSim client按4个时间帧、每帧2台相机运行，回调顺序为帧推进后再执行两次detect；首帧索引为0。两条匿名局部航迹通过独立离线标签映射到同一目标，在线文件没有出现Actor名称或真值编号。

同日使用v2运行`airsim_n20_formal_20260816/crossview`保存的44条匿名局部航迹做单seed离线重算。旧聚类得到27条正确关系、4条错误关系、3条漏关系和1个身份混合簇；修复后得到30条正确关系，错误关系、漏关系和身份混合均为0。精确率由0.871提高到1.000，召回率由0.900提高到1.000。该结果证明保存replay中的两个已定位结构问题得到修复。详细证据见`outputs/airsim_n20_cluster_consensus_replay_20260816/REPORT_CN.md`。

随后完成v3独立真实重跑`airsim_n20_formal_v3_20260816/crossview`。本轮46条识别航迹形成30条正确关系，错误关系为0，漏关系为2；精确率1.000，召回率0.9375，身份混合为0，另有2条局部航迹保持未解决。v2保存replay的30/30结果继续保留，但v3说明真实detect输出和短航迹长度存在运行间波动。当前算法采用失败关闭策略：证据不足时保留`unresolved`，不以强制合并换取召回率，因此新独立运行没有产生错误关系和身份混合。

```bash
pytest -q research_modules/independent_experiments/center_terminal_cv_campaign/exp_crossview/tests
python3 -m py_compile research_modules/independent_experiments/center_terminal_cv_campaign/exp_crossview/*.py
```

当前30项本目录测试通过。测试覆盖统一回放清单相对路径、SHA256失败关闭、在线真值污染拒绝、`full/sector_fov`相机对策略、审计/详细输出决策一致性、测试种子训练隔离、模型bundle摘要校验、固定代价融合和图网络不绕过硬几何门。

## 保存回放离线对照

2026年8月16日使用一个Blocks进程完成两组规模采集。20目标/30相机形成165条局部航迹和85847条候选边，离线评分为558条正确关系、302条错误关系和71条漏关联，精确率0.6488，召回率0.8871，身份混合5个。40目标/50相机形成584条局部航迹和1104646条候选边，得到3538条正确关系、2537条错误关系和794条漏关联，精确率0.5824，召回率0.8167，身份混合18个。

同日使用冻结模型和AirSim留出种子`20260816`完成20目标/8相机、20目标/30相机和40目标/50相机的四路离线对照。四路方法分别为全相机几何、全相机图网络、责任区视锥几何和责任区视锥图网络。全相机组用于诊断候选规模，不作为规模场景的部署建议。

| 场景 | 方法 | 正确关系 | 错误关系 | 漏关系 | 精确率 | 召回率 | 身份混合 | 用时/秒 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 20目标/8相机 | 全相机几何 | 30 | 0 | 2 | 1.0000 | 0.9375 | 0 | 见基准汇总 |
| 20目标/8相机 | 全相机图网络 | 30 | 0 | 2 | 1.0000 | 0.9375 | 0 | 见基准汇总 |
| 20目标/8相机 | 责任区视锥几何 | 30 | 0 | 2 | 1.0000 | 0.9375 | 0 | 见基准汇总 |
| 20目标/8相机 | 责任区视锥图网络 | 30 | 0 | 2 | 1.0000 | 0.9375 | 0 | 见基准汇总 |
| 20目标/30相机 | 全相机几何 | 558 | 302 | 71 | 0.6488 | 0.8871 | 5 | 见基准汇总 |
| 20目标/30相机 | 全相机图网络 | 571 | 310 | 58 | 0.6481 | 0.9078 | 3 | 见基准汇总 |
| 20目标/30相机 | 责任区视锥几何 | 564 | 198 | 65 | 0.7402 | 0.8967 | 4 | 见基准汇总 |
| 20目标/30相机 | 责任区视锥图网络 | 571 | 142 | 58 | 0.8008 | 0.9078 | 2 | 见基准汇总 |
| 40目标/50相机 | 全相机几何 | 3538 | 2537 | 794 | 0.5824 | 0.8167 | 18 | 1842.79 |
| 40目标/50相机 | 全相机图网络 | 4031 | 2094 | 301 | 0.6581 | 0.9305 | 7 | 2062.61 |
| 40目标/50相机 | 责任区视锥几何 | 4031 | 16 | 301 | 0.9960 | 0.9305 | 0 | 770.99 |
| 40目标/50相机 | 责任区视锥图网络 | 4031 | 16 | 301 | 0.9960 | 0.9305 | 0 | 812.96 |

20目标/8相机中，责任区视锥策略将相机对由28组减到16组，候选由5778条减到3296条，四种方法质量一致。20目标/30相机中，相机对由435组减到267组，候选由85847条减到52635条；责任区视锥图网络相对责任区视锥几何提高精确率和召回率，并将身份混合由4个降到2个。40目标/50相机中，相机对由1225组减到403组，候选由1104646条减到375236条；两种责任区视锥方法质量完全相同，图网络用时更长。

结果表明，相机图稀疏化是规模场景的主要收益。图网络在20目标/30相机的稀疏场景有增益，但在40目标/50相机的稀疏场景没有质量增益，运行时间由770.99秒增加到812.96秒。因此图网络继续作为离线可选对照，几何与匈牙利路径保持默认。所有方法的在线真值泄漏计数均为0。

这些数字来自一个真实AirSim种子`20260816`的保存回放，不是多seed统计，也不代表生产能力。40目标/50相机及全相机诊断组采用单次计时，不能据此给出稳定时延边界。后续仍需独立seed和导航、姿态、云台、时间同步误差注入验证。

规模运行还暴露了报告开销。候选图的确认状态查询已经由逐候选遍历全部匹配改为集合查询。NED关系图最多绘制200条关系，相机像素图和关系图最多均匀抽取20台相机。保存回放基准使用`audit`模式，只保留阶段计数和限量样本，避免四种对照重复写出GB级候选文件；需要逐边复核时显式选择`detailed`。完整基准证据位于`../outputs/gnn_offline_benchmark_20260816/benchmark_summary.json`和同目录中文报告。
