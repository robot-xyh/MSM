# D4 Distributed Fallback Agent

## 责任范围

- `research_modules/d4_distributed_fallback/**`
- `subagent_reviews/D4_*`

## 模块职责

D4 负责中心失效、二级节点接管、主动降级仲裁和完全无中心时的 CBBA/拍卖式保底协同。

## 降级层级

1. 中心节点正常：中心继续主控。
2. 主动降级但中心可用：`request_center_replan`，中心发布新版本计划。
3. 中心失效：二级系留/高空侦察节点接管。
4. 二级节点失效或不可用：分布式 CBBA/拍卖式保底。

## 硬性要求

- 主动降级读取 D1/D2/D3/D5 的不确定性和一致性证据。
- 被动降级优先看 C2Health。
- 二级节点选择必须考虑 coverage。
- 不假设固定节点数或任务数。

## 默认测试

```bash
PYTHONPATH=research_modules/d4_distributed_fallback python3 -m pytest -q research_modules/d4_distributed_fallback/tests
```
