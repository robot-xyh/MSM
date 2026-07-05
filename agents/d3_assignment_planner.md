# D3 Assignment Planner Agent

## 责任范围

- `research_modules/d3_assignment_planner/**`
- `subagent_reviews/D3_*`

## 模块职责

D3 负责中心节点存在时的资源-目标分配、版本化计划、迟滞重分配和 D7 guidance binding。

## 算法主线

- 默认：Hungarian / `linear_sum_assignment`。
- 复杂约束预留：Min-Cost Flow / OR-Tools。

## 硬性要求

- `AssignmentPlan` 必须版本化。
- 输出中记录 `resource_count`、`target_count` 或等价规模字段。
- 重分配必须考虑迟滞和 stale plan 拒绝。
- 不根据 5v5 写死矩阵规模。

## 默认测试

```bash
python3 -m pytest -q research_modules/d3_assignment_planner/tests
```
