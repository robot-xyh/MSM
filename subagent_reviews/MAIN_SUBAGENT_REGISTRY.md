# Main Subagent Registry

**目的**：梳理当前 D1-D7 子智能体、解释上限原因，并固定后续调度规则。  
**当前规则**：main agent 是主线程，不计入 subagent 槽位；可同时打开的 subagent 槽位上限为 **6**。已完成但未关闭的 subagent 仍会占用槽位。

## 1. 为什么会到上限

上次执行时同时保留了 D1-D6 六个子智能体：

```text
D1 + D2 + D3 + D4 + D5 + D6 = 6 个打开的 subagent
```

此时再创建 D7，会超过当前工具的 6 个并发 subagent 槽位，所以创建失败。随后 main 关闭了 D3，释放 1 个槽位，才成功创建 D7。

注意：这里的上限不是“D1-D7 加 main 共 8 个”，而是“subagent 打开槽位最多 6 个”。main 不占槽，但 D1-D7 不能同时全部保持打开。

## 2. 当前子智能体登记表

| 角色 | 昵称 | Agent ID | 模块职责 | 当前管理状态 | 最近交付物 |
|---|---|---|---|---|---|
| D1 | Helmholtz | `019f1c35-04bd-76f0-8c7a-de767ee0b7cc` | 多传感器融合与目标配准 | 已关闭，可按 ID resume | `subagent_reviews/D1_IMPLEMENTATION_GAP_AUDIT.md` |
| D2 | Feynman | `019f1c35-3d02-7323-9ecd-fec2fc77e395` | 多目标跟踪与数据关联 | 已关闭，可按 ID resume | `subagent_reviews/D2_IMPLEMENTATION_GAP_AUDIT.md` |
| D3 | Tesla | `019f1c35-77b5-70a0-8f77-1e21cbbdba70` | 集中式资源-目标分配 | 已关闭，可按 ID resume | `subagent_reviews/D3_IMPLEMENTATION_GAP_AUDIT.md` |
| D4 | Kant | `019f1c35-be06-7320-9be0-e5abd04b2abf` | 分布式协同与降级接管 | 已关闭，可按 ID resume | `subagent_reviews/D4_IMPLEMENTATION_GAP_AUDIT.md` |
| D5 | Sagan | `019f1c36-0aac-7cd2-8567-9965a00cfbd5` | 末端视觉配准与身份认证 | 已关闭，可按 ID resume | `subagent_reviews/D5_IMPLEMENTATION_GAP_AUDIT.md` |
| D6 | Pauli | `019f2200-44ed-7a73-831c-ba149b109194` | 系统级评估指标 | 已关闭，可按 ID resume | `subagent_reviews/D6_IMPLEMENTATION_GAP_AUDIT.md` |
| D7 | Carver | `019f26c0-a929-74e3-958c-fc9f94fe2b29` | 比例导引与末端视觉 PNG | 已关闭，可按 ID resume | `subagent_reviews/D7_IMPLEMENTATION_GAP_AUDIT.md` |
| main | main agent | 当前主线程 | 全局调度、接口合同、总报告、运行编排 | 始终在线，不占 subagent 槽位 | `subagent_reviews/MAIN_IMPLEMENTATION_GAP_AUDIT.md` |

## 3. 后续调度规则

1. **不再长期保持 D1-D7 全部打开**  
   子智能体完成任务后立即关闭。需要继续工作时按 ID resume。

2. **并行任务最多 6 个 subagent**  
   若需要 D1-D7 全部参与，采用两批：
   - 第一批：D1-D6 并行；
   - 第二批：关闭已完成者后，再恢复/创建 D7；
   - 或者根据任务优先级选择 D1-D5 + D7，最后由 D6 统一评估。

3. **main 负责全局串联，不作为 D 模块子智能体**  
   main 不重复 D1-D7 的模块职责，只维护：
   - 总体接口合同；
   - AirSim/runtime 编排；
   - 跨模块日志；
   - 总报告；
   - 子智能体任务分发与结果合并。

4. **共享上下文以文档和代码为准**  
   关闭 subagent 后，长期上下文不能依赖对话记忆。共享状态应写入：
   - `subagent_reviews/*_REVIEW_AND_PLAN.md`
   - `subagent_reviews/*_IMPLEMENTATION_GAP_AUDIT.md`
   - `subagent_reviews/MAIN_IMPLEMENTATION_GAP_AUDIT.md`
   - 各模块 `PLAN.md` / `README.md` / `docs/`

5. **需要恢复某个模块时的标准动作**
   - 先 resume 对应 agent ID；
   - 只发送该模块相关任务；
   - 限定文件写入范围；
   - 完成后写文档或代码；
   - main 检查结果；
   - 关闭 agent 释放槽位。

## 4. 推荐并行组合

| 场景 | 推荐打开的 subagent | 原因 |
|---|---|---|
| AirSim 5v5 传感器/关联/分配联调 | D1, D2, D3, D6 | D1-D3 是主链路，D6 负责评估 |
| D4/D5 降级与跨视角专项 | D4, D5, D6 | D4/D5 是专项主体，D6 做指标 |
| D7 拦截闭环 | D3, D5, D7, D6 | D3 给分配，D5 给锁定，D7 控制，D6 评估 |
| 全链路方案更新 | D1, D2, D3, D4, D5, D7，然后 D6 | 先让模块给输出，最后 D6 统计评估 |
| 文档总汇总 | main only | 直接读取模块文档，不需要打开所有 subagent |

## 5. 当前清理结果

截至本登记文件写入时，D1-D7 已完成上一轮审计任务并全部关闭，后续子智能体槽位应为空。需要某个模块继续工作时，main 将按上表恢复对应 agent。

