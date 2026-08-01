# D5 A3 v2 BC model D6 低层独立审计

验证日期：2026-08-01

## 结论

D6 未调用 D5 evaluator、corpus gate、precheck 或模型类，直接读取冻结配置、
generation plan/summary/registry、feature cache 二进制、bundle manifest、
`SHA256SUMS` 和 `weights.pt`，按 state_dict 张量形状重建两层 tanh actor 前向。
候选完整性与 D5 声明指标可复现，但独立质量门失败关闭。

- 审计 schema/实现版本：`d6.d5-a3-v2-bc-model-independent-audit.v1`/`1.1.0`。
- 审计器源码：`research_modules/d6_evaluation_metrics/d6_evaluation_metrics/d5_a3_v2_bc_model_audit.py`；SHA-256：`32e37e0b89ff79068bb776efc4845d128b7421d32f6bdc35edec8b98d59cafd0`。
- test 样本/候选：40133/276437。
- exact action accuracy：0.959958139187203。
- intent recall：observe_target=0.000000000000000，search_sector=0.000000000000000，hold=0.985019920318725，reacquire=0.997006436162251。
- macro intent recall：0.495506589120244。
- interceptor/recon exact accuracy：0.972377123589677/0.656527249683143。
- ECE：0.368238533545216；feature-boundary OOD：0.000000000000000。

## 失败关闭

独立门状态为 `fail_closed`，原因：intent_recall_below_0.25:observe_target、intent_recall_below_0.25:search_sector、macro_intent_recall_below_0.5、expected_calibration_error_above_0.25。
总体准确率不能覆盖 observe_target 与 search_sector 的零召回。所有 authority
保持 false，`paired_shadow_allowed=false`，规则回退继续有效。

## 来源与范围

- generation seed 为 22100-22199，共 100；只核对与保留 seed 1000-1019 的数值交集为 0，未读取或运行保留 episode。
- 本证据只覆盖开发三维质点 test cache，不构成正式 R0、AirSim、真实相机、
物理非退化、assist、运行或控制准入证据。
- 每样本 prediction/confidence/OOD 已写入 `audit.json`；缓存文件在复算前后
再次核对 SHA-256。
