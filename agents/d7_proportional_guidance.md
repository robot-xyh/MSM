# D7 Proportional Guidance Agent

## 责任范围

- `research_modules/d7_proportional_guidance/**`
- `subagent_reviews/D7_*`

## 模块职责

D7 负责中段雷达 PN/PNG、末端视觉 PNG、SimpleFlight 控制命令和 D3/D4/D5 合同门控。

## 核心原则

- 每个 assignment pair 独立持有导引状态和 terminal filter。
- D7 不分配目标，不授权，不改写 `global_track_id`。
- D4 `request_center_replan`、`degrade_to_secondary`、`degrade_to_distributed` 时，D7 必须阻断视觉 PNG。
- D5 `locked`、D3 version 一致、D4 action 允许后，才可尝试视觉 PNG。

## 默认测试

```bash
python3 -m pytest -q research_modules/d7_proportional_guidance/tests
```
