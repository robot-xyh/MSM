# D4 中心失效与分布式降级综述及子方案

**定位**: 中心节点失效后，先由备份节点接管；无备份或通信受限时，使用 CBBA/拍卖式协商维持保底任务连续性。  
**边界**: 本文只讨论保底协同、摘要交换、故障注入和人工复核，不包含真实火控参数、毁伤逻辑或自动授权绕过。

---

## 0. 阶段补充：高空系留二级侦察节点

本阶段假设存在若干高空系留侦察无人机，作为区域二级节点。正常情况下中心节点仍是主控；中心节点失效后，系统优先降级到覆盖小区内的二级侦察节点，由其汇总局部航迹摘要、维持局部分配版本，并向若干拦截资源下发观测 cue。只有当二级节点也失效或不可用时，才进入完全无中心的 CBBA/拍卖式协商。

降级层级固定为：

```text
中心 C2
  -> 二级侦察节点
  -> 集群代表 / 完全分布式 CBBA
  -> 不收敛时 hold / continue_observe
```

实现上使用 `ResourceSummary.node_role=secondary_recon`、`coordinator_only=True`、`coverage_cell` 和 lease/priority 字段表达二级节点。二级节点只提供区域协调和观测摘要，不代表真实通信链路或自动执行权限。

---

## 1. 研究问题

中心节点正常时，全局态势、航迹融合和资源分配都由中心统一完成。但中心失效后，各无人机可能只有局部观测、旧版计划和不完整通信链路。此时不能假设分布式节点拥有完整态势，也不能直接执行全局最优算法。

本子系统目标：

- 通过 `C2Health` 状态机判断中心状态。
- 优先备份节点接管。
- 无备份时降级为 CBBA/拍卖式协商。
- 只交换摘要，不交换未经校验的完整态势。
- 中心恢复后双轨校验，不立即夺权。

---

## 2. 文献综述要点

2015-2026 年无人机集群任务分配中，CBBA、拍卖算法和合同网协议是常见分布式路线。

CBBA 通过 winner/bid 向量扩散和一致性消解，在连通图、确定仲裁和边际收益条件满足时可有限轮收敛。优点是适合多智能体任务协商，缺点是通信量随任务数、束长和网络直径上升。

拍卖算法实现简单、收敛快，适合保底协商；但如果缺少稳定拍卖人或一致仲裁，可能发生反复竞价。合同网协议适合动态插入任务，通信过程清晰，但结果通常偏贪心。

工程共识是：中心正常时不主动全分布式；分布式只作为中心失效后的保底能力。

---

## 3. 开源代码选型

| 项目 | 成熟度 | 用途 |
|------|--------|------|
| MIT CBBA 项目页 | 理论基准 | 理解CBBA和时间窗扩展 |
| CBBA-Python | 研究原型 | 快速仿真、故障注入 |
| CA-CBBA | 研究扩展 | 通信受限和调度策略参考 |

不建议直接把研究仓库部署到实时系统。正确方式是提炼消息结构、收敛规则、冲突消解和失败日志。

---

## 4. C2Health 状态机

```text
normal
  -> degraded : 更新延迟升高但心跳仍存在
  -> suspect  : 心跳过期、摘要不一致或链路异常

suspect
  -> normal : 双轨校验恢复
  -> failed : 多源确认中心不可用或自检失败

failed
  -> degraded : 备份节点lease有效或peer quorum成立

degraded
  -> normal  : 中心恢复且双轨校验通过
  -> suspect : 备份摘要冲突或网络分区
```

状态转移必须记录触发原因和时间。

---

## 5. 接管优先级

```text
1. 地面备份节点
2. 空中侦察/中继节点
3. 资源集群代表
4. CBBA/拍卖式保底协商
5. 无共识时 hold / continue_observe / return_safe
```

注意：分布式计划只维持保底连续性，不追求中心化最优，也不绕过人工授权。

---

## 6. 摘要消息

```text
TrackSummary
- id_hash
- coarse_cell
- age
- confidence_band
- source_count

ResourceSummary
- node_id
- capability_class
- availability_band
- comm_band
- operator_hold

BidState
- task_id
- bidder
- score_rank
- constraints_hash
- epoch
```

摘要必须粗粒度、带版本、带 epoch，防止旧消息重放或网络分区导致双主。

---

## 7. 核心伪代码

```python
def update_c2_health(heartbeat, track_digest, assignment_digest):
    if heartbeat.ok and track_digest.ok and assignment_digest.ok:
        return "normal"
    if heartbeat.stale or track_digest.conflict:
        return "suspect"
    if heartbeat.failed_by_quorum:
        return "failed"
    return "degraded"

def degraded_takeover(state):
    if state != "failed":
        return current_plan()
    if backup_lease_valid():
        return backup_plan(mode="safe_only")
    if peer_quorum_available():
        summaries = exchange_summaries()
        return cbba_or_auction(summaries, whitelist="continuity_only")
    return hold_or_return_safe()

def center_recovery(center_log, peer_logs):
    if dual_track_hash(center_log, peer_logs) and human_accepts():
        return "normal"
    return "degraded"
```

---

## 8. 故障注入测试

| 故障 | 期望 |
|------|------|
| 心跳丢失 | `normal -> suspect -> failed` |
| 更新乱序 | 不误判为完整恢复 |
| 主备lease冲突 | 进入`suspect`，禁止双主 |
| 网络分区 | 每个分区只保底，不全局夺权 |
| TrackSummary过期 | 拒绝参与新计划 |
| BidState重放 | epoch检查失败 |
| CBBA超时 | 回退到hold/observe |
| 中心恢复但日志落后 | 双轨校验失败，不立即恢复normal |

---

## 9. 交付物

1. CBBA、拍卖、合同网协议综述。
2. 开源项目成熟度评估。
3. `C2Health` 状态机。
4. 摘要消息：`TrackSummary`、`ResourceSummary`、`BidState`。
5. 降级协商伪代码和故障注入测试用例。

---

## 10. 参考资料

- MIT CBBA: <https://acl.mit.edu/projects/consensus-based-bundle-algorithm>
- CBBA-Python: <https://github.com/zehuilu/CBBA-Python>
- CA-CBBA: <https://github.com/mit-acl/CACBBA>
- Dynamic UAV task allocation survey: <https://www.mdpi.com/2504-446X/9/1/75>
