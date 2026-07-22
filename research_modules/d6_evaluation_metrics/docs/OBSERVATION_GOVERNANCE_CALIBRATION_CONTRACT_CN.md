# 长 Episode 观测治理标定合同

## 1. 用途

该合同用于评估 20、50、100、200 等动态规模长 episode 中的 D1 扫描级乱序观测治理和
D2 观测 claim ledger。D6 在 episode 结束后读取公共制品，不导入 D1/D2 运行模块，不回写
控制状态。

输出版本为 `scalable3d-observation-governance-calibration-v1`。v1 将 `scale` 定义为来袭
目标数量，因此每个制品中的 `scale` 必须等于 `target_count`。`resource_count` 独立记录，
不要求与目标数量相等。

## 2. Schema

| 制品 | Schema |
| --- | --- |
| 批输入清单 | `scalable3d-observation-governance-calibration-input-v1` |
| Episode 清单 | `scalable3d-observation-governance-episode-manifest-v1` |
| 在线治理审计 | `scalable3d-observation-governance-online-audit-v1` |
| D1 扫描乱序审计 | `d1-scalable3d-scan-oosm-audit-v1` |
| D2 claim ledger 审计 | `d2-scalable3d-claim-ledger-audit-v1` |
| evaluator-only 侧车 | `scalable3d-observation-governance-evaluator-sidecar-v1` |
| D6 聚合输出 | `scalable3d-observation-governance-calibration-v1` |

## 3. 批输入清单

```json
{
  "schema_version": "scalable3d-observation-governance-calibration-input-v1",
  "created_at_utc": "2026-07-22T00:00:00Z",
  "producer": "main-scalable3d-orchestrator",
  "admission_policy": "formal_only",
  "expected_scales": [20, 50, 100, 200],
  "episodes": [
    {
      "episode": {
        "episode_id": "long-governance-s20-seed20001",
        "scale": 20,
        "target_count": 20,
        "resource_count": 20,
        "seed": 20001,
        "duration_s": 120.0
      },
      "manifest_artifact": {
        "path": "s20-seed20001/observation_governance_manifest.json",
        "sha256": "sha256:<64 lowercase hex>"
      },
      "online_audit_artifact": {
        "path": "s20-seed20001/observation_governance_online_audit.json",
        "sha256": "sha256:<64 lowercase hex>"
      },
      "evaluator_sidecar": {
        "availability": "available",
        "artifact": {
          "path": "s20-seed20001/observation_governance_evaluator_sidecar.json",
          "sha256": "sha256:<64 lowercase hex>"
        },
        "reason": null
      }
    }
  ]
}
```

侧车未生成时必须显式写为：

```json
{
  "availability": "unavailable",
  "artifact": null,
  "reason": "evaluator_only_sidecar_not_produced"
}
```

`formal_only` 只接收 `evidence_tier=formal` 且 `repository_dirty=false` 的 episode。
`allow_development` 可以读取 development 制品，但 formal 制品只要标记为脏仍会被拒绝。
批内 `episode_id` 和 `seed` 均必须全局唯一，实际规模集合必须与 `expected_scales` 完全一致。

## 4. Episode 清单

```json
{
  "schema_version": "scalable3d-observation-governance-episode-manifest-v1",
  "episode": {
    "episode_id": "long-governance-s20-seed20001",
    "scale": 20,
    "target_count": 20,
    "resource_count": 20,
    "seed": 20001,
    "duration_s": 120.0
  },
  "provenance": {
    "producer": "main-scalable3d-runtime",
    "git_commit": "<40 lowercase hex>",
    "repository_dirty": false,
    "evidence_tier": "formal",
    "config_sha256": "sha256:<64 lowercase hex>",
    "world_schema": "scalable3d-world-v1",
    "bus_schema": "scalable3d-episode-bus-v1",
    "scenario_schema": "scalable3d-scenario-v1",
    "online_observation_schema": "scalable3d-observation-v1",
    "d1_scan_oosm_audit_schema": "d1-scalable3d-scan-oosm-audit-v1",
    "d2_claim_ledger_audit_schema": "d2-scalable3d-claim-ledger-audit-v1"
  },
  "online_truth_use_count": 0
}
```

Git 提交必须使用完整 40 位小写十六进制值。配置和制品摘要必须使用 SHA-256。在线真值使用
计数不是可选指标，必须存在且等于零。

## 5. 在线治理审计

```json
{
  "schema_version": "scalable3d-observation-governance-online-audit-v1",
  "episode": {
    "episode_id": "long-governance-s20-seed20001",
    "scale": 20,
    "target_count": 20,
    "resource_count": 20,
    "seed": 20001,
    "duration_s": 120.0
  },
  "provenance": {
    "producer": "main-scalable3d-runtime",
    "git_commit": "<40 lowercase hex>",
    "config_sha256": "sha256:<64 lowercase hex>",
    "episode_manifest_sha256": "sha256:<manifest file hash>",
    "source_bus_sha256": "sha256:<online episode bus hash>",
    "source_bus_schema": "scalable3d-episode-bus-v1"
  },
  "online_truth_use_count": 0,
  "d1_scan_oosm_audit": {
    "schema_version": "d1-scalable3d-scan-oosm-audit-v1",
    "metrics": {}
  },
  "d2_claim_ledger_audit": {
    "schema_version": "d2-scalable3d-claim-ledger-audit-v1",
    "metrics": {}
  }
}
```

每个在线指标都使用同一可用性记录：

```json
{"availability": "available", "value": 0, "reason": null}
```

或：

```json
{"availability": "unavailable", "value": null, "reason": "producer_counter_not_instrumented"}
```

`unavailable` 携带零值会被拒绝。D1 必填指标为：

```text
scan_count
current_oosm_buffer_count
peak_oosm_buffer_count
oosm_buffered_count
oosm_reordered_count
oosm_rejected_count
oosm_too_old_count
oosm_overflow_count
oosm_eviction_count
estimated_current_memory_bytes
estimated_peak_memory_bytes
```

D2 必填指标为：

```text
current_claim_count
peak_claim_count
claim_eviction_count
claim_too_old_count
claim_overflow_count
replay_quarantine_count
timestamp_conflict_count
duplicate_coalescence_count
estimated_current_memory_bytes
estimated_peak_memory_bytes
```

在线制品不得出现目标真值、Actor 名称、对象编号或离线标签。D6 检查
`current <= peak`、内存当前值不超过峰值，以及 D1 的 `too_old + overflow <= rejected`。

## 6. Evaluator-only 侧车

```json
{
  "schema_version": "scalable3d-observation-governance-evaluator-sidecar-v1",
  "evaluator_only": true,
  "online_consumed": false,
  "episode": {
    "episode_id": "long-governance-s20-seed20001",
    "scale": 20,
    "target_count": 20,
    "resource_count": 20,
    "seed": 20001,
    "duration_s": 120.0
  },
  "provenance": {
    "producer": "offline-truth-evaluator",
    "evaluator_git_commit": "<40 lowercase hex>",
    "config_sha256": "sha256:<64 lowercase hex>",
    "truth_schema": "scalable3d-offline-truth-v1",
    "truth_artifact_sha256": "sha256:<truth artifact hash>",
    "episode_manifest_sha256": "sha256:<manifest file hash>",
    "online_audit_sha256": "sha256:<online audit file hash>"
  },
  "metrics": {
    "near_neighbor_recall": {
      "availability": "available",
      "numerator": 19,
      "denominator": 20,
      "reason": null
    },
    "false_suppression_rate": {
      "availability": "available",
      "numerator": 0,
      "denominator": 20,
      "reason": null
    },
    "erroneous_coalescence_rate": {
      "availability": "available",
      "numerator": 0,
      "denominator": 10,
      "reason": null
    },
    "confirmation_latency_s": {
      "availability": "available",
      "samples_s": [0.2, 0.4],
      "reason": null
    }
  }
}
```

比例指标只有在正分母下才能标记为 available。确认时延只有在至少一个 evaluator 样本下才能
标记为 available。无评估机会时应使用 `unavailable`、空值和具体原因。D6 不读取原始真值，
只核验真值制品摘要并消费侧车中的已计算统计量。

## 7. 哈希和一致性规则

1. 调用方必须在 API 或命令行中提供批输入清单的外部 SHA-256。
2. 批输入清单分别提供 manifest、在线审计和可用侧车的外部 SHA-256。
3. 在线审计的 `episode_manifest_sha256` 必须绑定实际 manifest。
4. 侧车必须同时绑定实际 manifest 和在线审计，配置摘要必须与 manifest 一致。
5. descriptor、manifest、在线审计和侧车中的六个 episode 字段必须逐项一致。
6. manifest 与在线审计的 Git、配置和总线 schema 必须一致。
7. 任一摘要、schema、provenance 或 episode 身份不一致时拒绝整批输入，不生成部分正式报告。

## 8. 调用

Python API：

```python
from d6_evaluation_metrics import (
    ObservationGovernanceCalibrationReportGenerator,
    load_observation_governance_calibration_inputs,
)

inputs = load_observation_governance_calibration_inputs(
    "observation_governance_calibration_input.json",
    expected_sha256="sha256:<input spec hash>",
)
outputs = ObservationGovernanceCalibrationReportGenerator().write_report_bundle(
    "outputs/observation_governance_calibration",
    inputs=inputs,
)
```

命令行：

```bash
python3 research_modules/d6_evaluation_metrics/scripts/run_observation_governance_calibration.py \
  --input-spec observation_governance_calibration_input.json \
  --input-spec-sha256 'sha256:<input spec hash>' \
  --output-dir outputs/observation_governance_calibration
```

输出为逐 seed CSV、聚合 JSON 和中文 Markdown。在线计数按规模给出均值、P95 和最大值。
比例指标给出 evaluator 样本数、汇总比例和 episode 重采样自助法 95% 置信区间。没有可用
侧车时比例和时延保持 unavailable。

## 9. 当前证据

2026-07-22 完成 14 项合成合同回归，D6 全量为 `521 passed`。专项覆盖 available/unavailable、显式零、篡改、脏正式源、
在线真值泄漏、规模不一致、重复 seed、缺 provenance、侧车在线消费、20/50/100/200 以及
7/37 非基线动态规模。该结果只验证 D6 合同和报告器。

同日 main 已按本合同生成一组 dirty/development 快速基准：20/50/100/200 各 5 seed、每回合
33.75 s，online truth use 为 0。D6 已给出 claim 峰值、安全淘汰、近邻召回、错误抑制、错误
合并、确认时延和内存的开发期描述，详见 `../EXPERIMENT_REPORT.md` 2.16 节。该批不是 clean
formal 制品，输入模式和 seed 数仍有限，不能据此冻结生产门限或发布正式性能结论。
