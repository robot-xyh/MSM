# D4 分布式协同与降级接管

本模块用于离线科研仿真：当中心 C2 节点不可用时，评估区域二级节点接管、完全无中心协商、中心恢复合并等保底连续性机制。模块只使用内存网络和粗粒度摘要，不包含真实通信、飞控、硬件、火控、毁伤、自动处置或授权绕过逻辑。

## 目录

- `PLAN.md`：模块研发计划、问题定义、状态机和仿真边界。
- `docs/ALGORITHM_AND_IMPLEMENTATION.md`：算法原理、数学模型、接口、调参建议和实施细节。
- `docs/README.md`：D4 文档索引。
- `d4_distributed_fallback/`：Python 包源码。
- `scripts/run_failover_simulation.py`：默认离线降级仿真入口。
- `tests/`：状态机、CBBA、接管和仿真测试。
- `reports/EXPERIMENT_REPORT.md`：实验报告与曲线。
- `reports/AIRSIM_INTEGRATION_PLAN.md`：AirSim 离线回放集成计划。

## 快速运行

```bash
PYTHONPATH=research_modules/d4_distributed_fallback \
python3 research_modules/d4_distributed_fallback/scripts/run_failover_simulation.py
```

运行 D4 测试：

```bash
PYTHONPATH=research_modules/d4_distributed_fallback \
python3 -m pytest -q research_modules/d4_distributed_fallback/tests
```

## 当前能力

- `C2Health` 状态机：`normal -> degraded -> suspect -> failed`，中心恢复需双轨合并，不能只靠 heartbeat。
- 三级降级链路：中心 C2 -> 高空系留二级侦察节点/地面备份 -> 完全无中心 CBBA。
- 二级节点建模：`NodeRole.SECONDARY_RECON`、`coordinator_only`、`coverage_cell`、lease/priority。
- CBBA 风格协商：用于二级节点不可用后的连续性分配基线。
- 与 D3/D5/D6 的接口：接收上一版分配摘要，向 D5 提供区域观测/cue 语义，向 D6 输出接管、共识和冲突指标。

