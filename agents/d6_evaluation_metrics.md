# D6 Evaluation Metrics Agent

## 责任范围

- `research_modules/d6_evaluation_metrics/**`
- `subagent_reviews/D6_*`

## 模块职责

D6 负责系统级指标、批量实验统计、图表和报告。D6 消费日志，不参与控制。

## 指标要求

- 探测：detection probability、false alarm、miss。
- 跟踪：RMSE、continuity、ID switch。
- 分配：duplicate assignment、unassigned high threat。
- 降级：failover time、reassign pending、consensus。
- 末端：terminal lock、visual PNG switch、ambiguous/hold。
- 安全：constraint violation、human override。

## 硬性要求

- 指标按实际 `drone_count/resource_count/target_count/camera_count` 归一化。
- 不从 `2v2/5v5` 场景名推断规模。

## 默认测试

```bash
pytest -q research_modules/d6_evaluation_metrics/tests
```
