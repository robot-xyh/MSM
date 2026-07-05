# D5 Terminal Association Agent

## 责任范围

- `research_modules/d5_terminal_association/**`
- `subagent_reviews/D5_*`

## 模块职责

D5 负责末端视觉配准、跨视角一致性、友方/协同身份确认和 D7 视觉 PNG 前置证据。

## 核心原则

- D5 不重新分配目标。
- D5 不创建、不改写、不换绑 `global_track_id`。
- 在线几何配准不得使用 AirSim `object_id` / actor truth ID。
- truth ID 只能用于离线评分。

## 算法主线

`GlobalTrack -> CameraModel -> image projection -> LocalVisualTrack -> TerminalAssociation`

输出 `locked | ambiguous | hold | reacquire`。

## 默认测试

```bash
pytest -q research_modules/d5_terminal_association/tests
```
