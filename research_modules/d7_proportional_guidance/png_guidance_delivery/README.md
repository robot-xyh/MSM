# PNG Guidance Delivery Package

本交付包用于在 AirSim Blocks 中复现目标直线运动条件下的比例导引验证，覆盖三种工况：

- `truth`：已知目标真实位置和速度的 PNG 上限验证。
- `gimbal`：云台相机视觉 PNG，检测输入来自目标检测框。
- `strapdown`：捷联固定相机视觉 PNG，检测输入来自目标检测框。

每种工况均支持两种导引律：

- `LAW=TTC`：LOS + TTC 增益调度。TTC 不可靠时默认保留 LOS/Vm soft guidance。
- `LAW=VM`：固定 `N * V_m` 导引增益，不依赖 TTC 面积通道。

本包是仿真交付源码，不是可直接装机飞行的实机固件。真实 PX4/无人机使用前必须重新做油门、坐标系、相机外参、限幅和安全解锁流程标定。

## 1. 目录说明

```text
examples/
  run_airsim_truth_png.py              已知真实位置 PNG
  run_airsim_gimbal_vision_png.py      云台视觉 PNG
  run_airsim_strapdown_vision_png.py   捷联视觉 PNG
vision_guidance/
  geometry.py, ttc.py, los_filter.py, terminal_*.py, truth_png.py
  PNG/LOS/TTC/KF/末端外推等核心算法模块
config/
  airsim_blocks_settings.json          SimpleFlight 双机默认场景
  airsim_blocks_px4_actor_settings.json PX4 SITL 拦截机 + actor 目标场景
  airsim_blocks_px4_sitl_settings.json PX4 SITL 拦截机 + SimpleFlight 目标场景
scripts/
  run_delivery_case.sh                 统一入口脚本
docs/
  已验证报告、控制链路说明、baseline 说明
tools/
  AirSim 端口守护、YOLO/TensorRT 辅助工具
```

## 2. 环境准备

建议环境：

- Ubuntu Linux
- Python 3.10+
- AirSim Python API
- AirSim Blocks Linux 1.8.1
- 可选：PX4-Autopilot SITL
- 可选：NVIDIA GPU + PyTorch/Ultralytics，用于 YOLO 检测

安装 Python 依赖：

```bash
python3 -m pip install -r requirements.txt
```

如果只使用 AirSim detect / 真值验证，可以不安装 `ultralytics`、`lap` 和 CUDA 版 PyTorch。若使用 YOLO，需要把权重放到 `vision_guidance/best.pt` 或运行时传入 `--yolo-model`。

## 3. 启动 AirSim Blocks

默认 SimpleFlight 双机验证：

```bash
BLOCKS_DIR=/path/to/LinuxNoEditor ./run_blocks_nvidia.sh -settings=$PWD/config/airsim_blocks_settings.json
```

`run_blocks_nvidia.sh` 会自动检查 AirSim RPC/PX4 端口冲突，并把实际连接信息写入 `.airsim_runtime/latest.env`。如果在同一台电脑上启动多个 Blocks，必须通过该脚本启动，避免端口冲突。

另一个终端中载入端口环境：

```bash
source .airsim_runtime/latest.env
```

## 4. 一键运行三种工况

统一入口：

```bash
MODE=strapdown LAW=TTC ./scripts/run_delivery_case.sh
```

可选参数：

```bash
MODE=truth|gimbal|strapdown
LAW=TTC|VM
START_RANGE_M=80
START_LATERAL_M=-20
ALTITUDE_OFFSET_M=20
INTRUDER_SPEED=5
SPEED_RATIO=2
RATE_HZ=20
DURATION_S=30
```

示例：

```bash
MODE=truth LAW=TTC START_RANGE_M=80 ./scripts/run_delivery_case.sh
MODE=truth LAW=VM  START_RANGE_M=80 ./scripts/run_delivery_case.sh

MODE=gimbal LAW=TTC START_RANGE_M=90 ./scripts/run_delivery_case.sh
MODE=gimbal LAW=VM  START_RANGE_M=90 ./scripts/run_delivery_case.sh

MODE=strapdown LAW=TTC START_RANGE_M=80 ./scripts/run_delivery_case.sh
MODE=strapdown LAW=VM  START_RANGE_M=80 ./scripts/run_delivery_case.sh
```

输出默认写入：

```text
logs/delivery/
```

每次运行会生成：

- `*.csv`：逐帧日志，包含目标位置、检测框、LOS、TTC、导引模式、速度/角速度/过载等。
- `*_meta.json`：实验参数和派生参数。
- 若未传 `--no-plot`，还会生成轨迹图。

## 5. 三种工况的控制含义

### truth

使用 AirSim 真值计算目标相对位置和相对速度，只用于算法上限验证。它不代表可部署视觉路径。

### gimbal

目标由相机检测框提供。云台根据像面误差转动，使目标尽量保持在画面中心；导引只使用检测框、机体状态和云台姿态，不使用目标真值。

### strapdown

相机固定在机体上。目标保持在视场内主要依靠机体 yaw / frame-centering / terminal-capture 逻辑。该工况最接近固定相机无人机拦截方案。

## 6. 导引律说明

`LAW=TTC`：

```text
a_cmd = K(TTC) * (omega_LOS x lambda_I)
```

其中 `lambda_I` 是惯性系 LOS 单位向量，`omega_LOS` 是 LOS 角速度。TTC 由检测框面积扩张估计，TTC 越小，增益越高。当前实现默认启用 soft guidance：TTC 无效时不直接退出，而是保留 LOS/Vm 导引。

`LAW=VM`：

```text
a_cmd = N * V_m * (omega_LOS x lambda_I)
```

其中 `N` 默认 `3.0`，`V_m = speed_ratio * intruder_speed`。该模式不依赖检测框面积，因此适合排查 TTC 面积噪声或近距裁切问题。

## 7. 预期结果

最近一次完整诊断结果见 `docs/BodyRate_三问题线实施实验报告.md`。典型结论如下：

|工况|检测/输入|导引|预期表现|
|---|---|---|---|
|truth|目标真值|TTC/VM|几何最小距离应显著收敛，可作为导引上限诊断。|
|gimbal|AirSim detect|TTC|云台 yaw feedback 后，70/90/100m 工况可达到 3/3 命中。|
|gimbal|AirSim detect|VM|VM 对 bbox 面积失败更不敏感，历史诊断中为 2/3 到 5/6，取决于测试距离集。|
|strapdown|AirSim detect|TTC|50/60/70/80/90/100m 可达到 6/6 命中。|
|strapdown|AirSim detect|VM|五组诊断中可达到 6/6 命中，最小距离略小于 TTC。|
|strapdown|YOLO + ByteTrack|TTC/VM|结果依赖检测连续性；历史 body-rate YOLO baseline TTC 为 4/6。|

验收建议：

- 先用 `MODE=truth` 确认场景几何和导引律正常。
- 再用 `MODE=strapdown LAW=TTC` 和 AirSim detect 确认固定相机视觉闭环。
- 最后切换 YOLO 或 PX4 SITL，逐项排查识别连续性、LOS/KF、PX4 响应和推力饱和。

## 8. 安全边界

当前代码中存在可向 PX4 Offboard 下发 `SET_ATTITUDE_TARGET` 的接口，但本交付包不允许直接作为实机飞行代码使用。实机前必须至少完成：

- 禁用自动 arm / 自动 Offboard。
- 台架验证 body-rate 符号和 thrust 悬停值。
- 标定真实相机外参、延迟、畸变和坐标系。
- 设置遥控器 kill switch、围栏、低速限幅和人工接管。
- 在低速、低高度、无桨或安全网环境逐步验证。

## 9. 版本

源仓库提交：`d786d2e`
打包日期：`2026-07-02`
