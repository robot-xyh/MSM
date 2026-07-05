# D7 比例导引离线研究模块

本模块实现“经典比例导引架构”的离线二维质点版本，用于算法解释、日志评估、研究仿真和后续全流程闭环可视化接入。模块只处理抽象的 `GuidanceState`、`GuidanceCommand` 和 `GuidanceRecord`，不包含真实飞控接口、硬件驱动、实时通信、火控参数、毁伤模型、自动处置或授权绕过逻辑。

## 目录

```text
research_modules/d7_proportional_guidance/
  PLAN.md
  README.md
  d7_proportional_guidance/
    __init__.py
    airsim_dry_run.py
    models.py
    pn.py
    simulator.py
  tests/
    conftest.py
    test_airsim_phase1_dry_run.py
    test_proportional_guidance.py
```

## 核心能力

- `radar_midcourse`：使用抽象 GlobalTrack/雷达航迹估计，计算中段二维 PN 指令。
- `vision_terminal`：使用抽象像素/LOS 观测估计，计算末段二维 PN 指令。
- `pure_pursuit`：轻量纯追踪 baseline，通过 `GuidanceConfig.guidance_law="pure_pursuit"` 启用，用于和默认 PN 做离线对照；没有引入 PythonRobotics 依赖。
- `SimpleFlightPngGuidanceFilter`：从 `png_guidance_delivery` 抽取的轻量视觉 PNG gate，支持 bbox 质量、LOS-rate、TTC/VM 增益和机动裕度判断。
- `guidance_mode_from_terminal_contract(...)`：把 D3/D4/D5 末端合同结果映射为显式 D7 日志状态，包括 `handover_pending`、`hold`、`reacquire` 和 `abort_revoke`。
- `terminal_switch_allowed_rate` / `summarize_terminal_switch_quality`：对 D7 已输出的 gate 结果做离线通过率统计，不重新执行 runtime gate 逻辑。
- 输出 LOS angle、LOS rate、closing speed、range、模式、横向加速度限幅、转向率限幅和离线质点轨迹记录。
- `simulate_guidance_episode` 支持单个 resource-target pair 的离线闭环，返回 `records` 和 `summary`。
- `guidance_records_from_assignment_dry_run` 接收 assignment/resource/target estimate 三类普通 Python 数据，输出一条 `radar_midcourse` 和一条 `vision_terminal` 干运行记录。

## N-pair AirSim runtime 接入边界

D7 不拥有 AirSim 控制状态机，也不创建 `InterceptPair`。仿真规模由 main runtime 的 `--drone-count N` 统一决定；main 应在每次仿真中枚举 D3 输出的有效 assignment pair，并为每个 pair 创建独立 D7 控制上下文。该上下文至少持有 resource/target ID、D3 binding、D4 permission、D5 `TerminalAssociation`、初段位置 PNG/PN 记录状态和该 pair 自己的 `SimpleFlightPngGuidanceFilter` 实例。D7 侧 API 已按 pair 纯函数/实例状态工作，不假设固定 2v2 或 5v5：

- 中段用 `compute_proportional_navigation_command(..., mode=GuidanceMode.RADAR_MIDCOURSE)` 输出 radar PN 几何量。
- 末端先调用 `evaluate_terminal_png_contract(...)`；只有 D3/D4/D5 合同通过时，才调用该 pair 自己的 `SimpleFlightPngGuidanceFilter(PngGuidanceConfig(law="png_vm"))`。
- 合同拒绝时 runtime 应继续记录 `terminal_contract_reject_reason`，并保持中段/保守状态，不把拒绝归因到视觉 gate。
- 每个 time-series 样本建议保留 `resource_id`、`target_id`、`mode`、`guidance_law`、`terminal_switch_allowed`、`terminal_switch_reject_reason`、`terminal_contract_reject_reason`、`ttc_s`、D4/D5 状态和 plan/version 字段。

`tests/test_proportional_guidance.py::test_runtime_sized_pairs_keep_independent_terminal_gate_and_png_time_series` 覆盖 1/3/5/7 个 pair 的并行 D7 合同、初段 radar PN、`png_vm`、TTC 和 time-series 字段形状，防止不同 pair 共用视觉滤波状态。2v2 actor 拦截仍可作为 baseline 和 active-secondary 合同回归，但不能作为 main runtime 的数量假设。

## 2v2 active-secondary 视觉 PNG 合同

AirSim Blocks 2v2 主动降级链路采用保守解释：D4 `degrade_to_secondary` 是重分配发起事件，不是 D7 视觉终端授权。D7 必须把它视为 `d4_reassign_pending`，日志模式映射为 `abort_revoke`，即使当前位置 PN、TTC、检测框和 D5 旧锁定状态看起来可用，也不能调用视觉 PNG。

二级节点 plan 生效后，D7 才能评估视觉 PNG。进入 `mode=vision_terminal` 且输出 `guidance_law=png_vm` 的必要条件是：

- D3 binding 已切到二级 resource/plan/version，且 assignment 仍为 authorized/current。
- D4 action 为 `request_secondary_assist` 或 `continue_center`，并且可选的 `new_plan_id/new_plan_version` 与当前 D3 binding 一致。
- D5 terminal association 为 `decision_state=locked`，无 friend conflict，`assigned_global_track_id` 和 `assignment_version` 与当前 binding 一致。
- 当前视觉观测的 `assigned_global_track_id` 与 binding 一致，随后才允许调用该二级 pair 自己的 `SimpleFlightPngGuidanceFilter(PngGuidanceConfig(law="png_vm"))`。

`tests/test_proportional_guidance.py::test_2v2_active_secondary_visual_png_requires_effective_secondary_plan` 固化该合同：主动降级阶段拒绝为 `d4_reassign_pending`；二级 plan 版本不一致拒绝为 `d4_plan_mismatch`；二级 plan 生效且 D5 locked 后才产生 `png_vm`/`vision_terminal`。

## PNG guidance delivery 融合边界

`png_guidance_delivery` 已复制到本模块下作为算法来源和复现实验资料。主线当前只吸收其中与 SimpleFlight/AirSim detect 兼容的算法核：

- 相机检测框到视线角的几何转换。
- LOS-rate 滑窗质量判断。
- bbox 面积扩张 TTC 估计。
- `png_ttc` 与 `png_vm` 两种终端导引增益。
- bbox 太小、贴边、检测不连续、视觉延迟过高、机动裕度不足时拒绝切入视觉终端。

以下内容暂不接入主线：PX4 Offboard、MAVLink body-rate/attitude、YOLO/TensorRT、真实飞控解锁和实机安全流程。AirSim 当前阶段继续使用 SimpleFlight `moveByVelocityZAsync`，视觉输入来自 AirSim `simGetDetections` 的 bbox 和相机元数据，不默认保存 PNG 图像。

## AirSim 目标命名约定

本次核对 `png_guidance_delivery` 后，D7 文档采用以下命名口径：

- 当前 main/runtime 默认目标 actor 和检测过滤名为 `MSM_TargetActor_*`，实际 spawn 名通常类似 `MSM_TargetActor_1`。D7 与 D5/D6 的运行时日志、handoff 记录和新测试应优先使用这个命名。
- runtime 默认目标 asset 为 `1M_Cube_Chamfer`。
- `png_guidance_delivery` 复现实验脚本仍保留历史默认：`--mesh Intruder*`、`--intruder-actor-name IntruderActor`，其中 truth/gimbal/strapdown actor 路径默认 `--intruder-actor-asset 1M_Cube_Chamfer`。`Intruder*`/`IntruderActor` 仅作为 legacy alias 和旧报告复现口径。
- 旧 baseline 文档中出现的 `Quadrotor1` 是历史 actor asset 记录，不是当前 runtime 默认目标 asset。

## 运行测试

从仓库根目录执行：

```bash
python3 -m pytest research_modules/d7_proportional_guidance/tests
```

## 接口示例

```python
from d7_proportional_guidance import (
    GuidanceConfig,
    GuidanceState,
    PngGuidanceConfig,
    SimpleFlightPngGuidanceFilter,
    VisionGuidanceObservation,
    simulate_guidance_episode,
)

config = GuidanceConfig(
    dt_s=0.05,
    navigation_constant=3.0,
    terminal_switch_range_m=250.0,
    max_lateral_accel_mps2=60.0,
    max_turn_rate_radps=0.8,
)
pursuer = GuidanceState("R0", 0.0, (0.0, 0.0), (180.0, 0.0))
target = GuidanceState("T0", 0.0, (1200.0, 150.0), (-20.0, 0.0))

records, summary = simulate_guidance_episode(pursuer, target, config)
print(summary["min_range_m"], summary["terminal_mode_entered"])
print(records[0].los_angle_rad, records[0].closing_speed_mps)
```

Pure Pursuit 对照示例：

```python
pp_config = GuidanceConfig(guidance_law="pure_pursuit", dt_s=0.05)
records, summary = simulate_guidance_episode(pursuer, target, pp_config)
print(summary["guidance_law"], summary["min_range_m"])
```

视觉 PNG gate 示例：

```python
gate = SimpleFlightPngGuidanceFilter(PngGuidanceConfig(law="png_vm"))
cmd = gate.evaluate(
    VisionGuidanceObservation(
        timestamp_s=0.2,
        bbox_xyxy=(300.0, 220.0, 360.0, 280.0),
        detection_confidence=0.9,
        local_track_id="R1:det-1",
        assigned_global_track_id="TGT-001",
    ),
    current_heading_rad=0.0,
    current_speed_mps=6.0,
    intercept_speed_mps=6.0,
    relative_position_ned=(20.0, 1.0, 0.0),
    relative_velocity_ned=(-4.0, 0.0, 0.0),
)
print(cmd.quality.terminal_switch_allowed, cmd.quality.reject_reason)
```

AirSim phase-1 干运行接口只接受离线夹具或 DTO，不导入 `airsim`，不连接仿真器，也不调用车辆控制 API：

```python
from d7_proportional_guidance import (
    guidance_records_from_airsim_dry_run_fixture,
    make_minimal_airsim_dry_run_fixture,
)

fixture = make_minimal_airsim_dry_run_fixture()
records, summary = guidance_records_from_airsim_dry_run_fixture(fixture)
print([record.mode.value for record in records], summary["boundary"])
```

如果未安装为包，可在命令行示例中临时加入模块路径：

```bash
PYTHONPATH=research_modules/d7_proportional_guidance python3 - <<'PY'
from d7_proportional_guidance import simulate_guidance_episode

records, summary = simulate_guidance_episode()
print(len(records), summary)
PY
```

## 数据约定

- 所有位置为米 `m`，速度为米每秒 `m/s`，加速度为米每二次方秒 `m/s^2`。
- 角度为弧度 `rad`，角速度/LOS rate 为 `rad/s`。
- `GuidanceRecord.range_m` 是真实二维几何距离；`los_angle_rad` 和 `closing_speed_mps` 来自当前模式的估计状态。
- `GuidanceCommand` 中 `commanded_*` 为原始 PN 计算值，`limited_*` 为加速度和转向率约束后的值。
- `GuidanceMode` 当前包括 `radar_midcourse`、`handover_pending`、`vision_terminal`、`hold`、`reacquire`、`abort_revoke`。`hold/reacquire/abort_revoke` 是日志和状态机语义，不表示绕过 D3/D4/D5 授权链路的本地重分配。

## 边界

该模块只用于离线二维质点仿真和日志分析。它不读取或写入真实平台接口，不控制实体设备，不处理作战授权，不提供毁伤评估，也不输出可直接用于真实系统执行的控制命令。
