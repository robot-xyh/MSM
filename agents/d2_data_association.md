# D2 Data Association Agent

## 责任范围

- `research_modules/d2_data_association/**`
- `subagent_reviews/D2_*`

## 模块职责

D2 负责多目标航迹关联、稳定 `global_track_id`、ID switch 统计和关联风险摘要。

## 算法主线

- 默认：GNN/Hungarian。
- 升级/对照：JPDA、MHT。
- 指标：`id_switch_count`、`track_continuity`、`duplicate_assignment_count`。

## 硬性要求

- 按输入 `tracks/detections` 长度构造代价矩阵。
- 不从场景名推断目标数量。
- 不改写 D1/D3/D5 的合同字段。

## 默认测试

```bash
PYTHONPATH=research_modules/d2_data_association pytest -q research_modules/d2_data_association/tests
```
