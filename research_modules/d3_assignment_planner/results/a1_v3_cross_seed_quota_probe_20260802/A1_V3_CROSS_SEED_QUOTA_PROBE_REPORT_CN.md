# A1 v3 跨 seed 配额探针摘要（探索性）

> 日期：2026-08-02。本文只整理既有 28 行探针记录，不是正式 source generation、dataset 或训练报告。

## 结论

- 样本覆盖：28 行，`pass=5`、`quota_failed=23`；来源文件为既有未完成 checkpoint 的 28 行，未运行剩余旧 300 条 recipe。
- `3/3/2` 最低配额保持不变。seed `23001` 实测 `observable/positive/negative/hard_negative=10/1/9/4`，正类缺口为 2。
- 当前仓库 dirty，故全部记录仅为 exploratory；`readiness_eligible=false`，不能转为 source request readiness。
- 正式 source 状态：`staged=1`、`finalized=0`。没有正式数据集、训练或准入证据。
- blocker：`cross_seed_quota_viability_not_proven`。

## 28 行记录

| index | episode | seed | status | observable | positive | negative | hard negative |
|---:|---|---:|---|---:|---:|---:|---:|
| 0 | `a1-v3-cell-00-train-00` | 23000 | `pass` | 10 | 3 | 7 | 3 |
| 1 | `a1-v3-cell-00-train-01` | 23001 | `quota_failed` | 10 | 1 | 9 | 4 |
| 2 | `a1-v3-cell-00-train-02` | 23002 | `quota_failed` | 10 | 3 | 7 | 1 |
| 3 | `a1-v3-cell-00-train-03` | 23003 | `quota_failed` | 10 | 1 | 9 | 1 |
| 4 | `a1-v3-cell-00-train-04` | 23004 | `quota_failed` | 10 | 1 | 9 | 1 |
| 5 | `a1-v3-cell-00-train-05` | 23005 | `quota_failed` | 10 | 1 | 9 | 2 |
| 6 | `a1-v3-cell-00-train-06` | 23006 | `pass` | 10 | 3 | 7 | 2 |
| 7 | `a1-v3-cell-00-train-07` | 23007 | `quota_failed` | 10 | 1 | 9 | 2 |
| 8 | `a1-v3-cell-00-train-08` | 23008 | `quota_failed` | 9 | 1 | 8 | 3 |
| 9 | `a1-v3-cell-00-train-09` | 23009 | `quota_failed` | 10 | 1 | 9 | 2 |
| 10 | `a1-v3-cell-00-train-10` | 23010 | `quota_failed` | 10 | 1 | 9 | 2 |
| 11 | `a1-v3-cell-00-train-11` | 23011 | `quota_failed` | 10 | 1 | 9 | 3 |
| 12 | `a1-v3-cell-00-validation-00` | 23180 | `quota_failed` | 10 | 1 | 9 | 2 |
| 13 | `a1-v3-cell-00-validation-01` | 23181 | `quota_failed` | 10 | 1 | 9 | 3 |
| 14 | `a1-v3-cell-00-validation-02` | 23182 | `pass` | 10 | 3 | 7 | 1 |
| 15 | `a1-v3-cell-00-validation-03` | 23183 | `quota_failed` | 10 | 1 | 9 | 3 |
| 16 | `a1-v3-cell-00-test-00` | 23240 | `quota_failed` | 10 | 1 | 9 | 6 |
| 17 | `a1-v3-cell-00-test-01` | 23241 | `quota_failed` | 10 | 1 | 9 | 1 |
| 18 | `a1-v3-cell-00-test-02` | 23242 | `quota_failed` | 10 | 1 | 9 | 2 |
| 19 | `a1-v3-cell-00-test-03` | 23243 | `quota_failed` | 10 | 1 | 9 | 3 |
| 20 | `a1-v3-cell-01-train-00` | 23012 | `pass` | 10 | 3 | 7 | 6 |
| 21 | `a1-v3-cell-01-train-01` | 23013 | `quota_failed` | 10 | 1 | 9 | 8 |
| 22 | `a1-v3-cell-01-train-02` | 23014 | `pass` | 10 | 3 | 7 | 6 |
| 23 | `a1-v3-cell-01-train-03` | 23015 | `quota_failed` | 10 | 1 | 9 | 9 |
| 24 | `a1-v3-cell-01-train-04` | 23016 | `quota_failed` | 10 | 1 | 9 | 7 |
| 25 | `a1-v3-cell-01-train-05` | 23017 | `quota_failed` | 10 | 2 | 8 | 6 |
| 26 | `a1-v3-cell-01-train-06` | 23018 | `quota_failed` | 10 | 1 | 9 | 8 |
| 27 | `a1-v3-cell-01-train-07` | 23019 | `quota_failed` | 10 | 1 | 9 | 8 |

## 来源绑定

- git commit：`909e7bee3cad6edef0c03991848960f88f616601`；`repository_dirty=true`。
- 原始 28 行 SHA256：`844c15a8f9f57ec70f55f4dedcba9ea87f5a729e12c9f8b0dc987a208b54ab69`。
- `probe_source`：`research_modules/d3_assignment_planner/src/d3_assignment_planner/a1_v3_quota_probe.py`，SHA256 `45f0bfcd0c42b4127635be98f40923394c98b7c69c49af31cc6b266e6a732631`。
- `sidecar_classifier`：`research_modules/d3_assignment_planner/src/d3_assignment_planner/a1_v3_sidecar_classification.py`，SHA256 `b04cbbcb9d696c01875032bf3a2d2ad2e2309160000e25bc16bd772f62c6edaf`。
- `dataset_writer`：`research_modules/d3_assignment_planner/src/d3_assignment_planner/a1_v3_dataset_writer.py`，SHA256 `9a99603640df3dfb5382fbd2447261cce332e245a65c3fc3049026498444301a`。
- `learning_source_recipes`：`research_modules/scalable_3d_simulation/learning_source_recipes.py`，SHA256 `7af7cbcc2585cf79faebe01ea6b231af73d1dd7d2fc8c780a6476201e4d70a44`。
- `episode_treatments`：`research_modules/scalable_3d_simulation/episode_treatments.py`，SHA256 `8e77b53dc1f9a5558d4b2f73e10c03f36aa292a298c76c6182169070c5e5ae19`。
- `orchestrator`：`research_modules/scalable_3d_simulation/orchestrator.py`，SHA256 `bdc5adebe7cbb0f5cb65716ee08fc1f636ed5fd45c65883a3bb8409080e0335f`。
- `generation_schedule`：`research_modules/d3_assignment_planner/configs/a1_source_independent_v3_generation_schedule_v1.json`，SHA256 `0eac8bcfeb09e1e706c31c2532fab82296028e95c5e384ac11c4e81cb7cb05ba`。
- `base_config`：`research_modules/scalable_3d_simulation/configs/nominal_200v200.json`，SHA256 `2279fa380ce2d79d98690b148653b0409a2471bb35d8aab77f9ed5d0f7b97072`。

## 禁止事项与边界

- 未读取 formal seeds `1000-1019`，未读取 R0 shards `10-19`。
- 未使用 truth/teacher override，未复制 frame，未写入或改写 `global_track_id`。
- 本摘要不构成 readiness、source generation authorization、dataset finalization 或 training authorization。
