# D1 Sensor Fusion Agent

## 责任范围

- `research_modules/d1_sensor_fusion/**`
- `subagent_reviews/D1_*`

## 模块职责

D1 负责把雷达、声学、光电等异构观测统一到 NED 工作空间，输出带协方差、时间戳和质量分级的 `GlobalTrack[]`。

## 硬性要求

- 同时携带 `measurement_timestamp` 和 `arrival_timestamp`。
- 每个观测和航迹都携带协方差。
- 输入数量由 main 场景提供，不限制 1/2/3/5。
- 2v2/5v5 只作为 baseline，不作为算法常量。

## 默认测试

```bash
PYTHONPATH=research_modules/d1_sensor_fusion/src pytest -q research_modules/d1_sensor_fusion/tests
```
