# Delivery Manifest

## Included Source

- `examples/run_airsim_truth_png.py`
- `examples/run_airsim_gimbal_vision_png.py`
- `examples/run_airsim_strapdown_vision_png.py`
- `examples/run_airsim_blocks.py`
- `vision_guidance/*.py`
- `tools/airsim_port_guard.py`
- `tools/benchmark_yolo_detector.py`
- `tools/export_yolo_tensorrt.py`

## Included Scene Settings

- `config/airsim_blocks_settings.json`
  - SimpleFlight `Interceptor` + SimpleFlight `Intruder`
  - 640x480 camera, FOV 120 deg, NoDisplay, ClockSpeed 0.2
- `config/airsim_blocks_px4_actor_settings.json`
  - PX4 SITL `Interceptor` + spawned actor target
  - NoDisplay, trace enabled, FOV 120 deg
- `config/airsim_blocks_px4_sitl_settings.json`
  - PX4 SITL `Interceptor` + SimpleFlight `Intruder`
- `config/airsim_blocks_px4_actor_clock0p2_settings.json`
  - PX4 SITL + actor variant with ClockSpeed 0.2
- `config/airsim_blocks_recording_settings.json`
  - Recording/visual inspection settings

## Included Run Scripts

- `run_blocks_nvidia.sh`
- `run_blocks_px4_actor.sh`
- `run_blocks_px4_sitl.sh`
- `run_px4_sitl.sh`
- `install_airsim_blocks_settings.sh`
- `scripts/run_delivery_case.sh`

## Included Documentation

- `README.md`
- `requirements.txt`
- `docs/PNG到PX4角速度控制实现说明.md`
- `docs/比例导引到控制链路说明.md`
- `docs/BodyRate_三问题线实施实验报告.md`
- `docs/mavlink_body_rate_TTC_relaxed_baseline_README.md`
- `docs/YOLO_SITL_frame_centering_tuned_50_100测试报告.md`

## Not Included

- AirSim Blocks binary directory `Blocks/`
- PX4-Autopilot source tree
- Full historical `logs/`
- Training datasets
- Python virtual environments
- `__pycache__/` files

The package is intentionally source-focused. Large third-party binaries and generated experiment logs should be supplied separately when needed.
