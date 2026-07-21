# D5 跨视角图 canonical seed 只读视图

验证日期：2026-07-21（America/Los_Angeles）

## 结论

共享数值 seed 已按完整 episode 建立只读重分桶视图。原 manifest 和样本制品未修改。
canonical train/validation/test seed 为 `60/20/20`，保留 seed `1000-1019` 未进入视图。

该结果只关闭 D4/D5 等学习消费者之间的 split 身份不一致。模型准入和运行安全门保持失败关闭。

## 哈希绑定

- source manifest SHA256：`d9a84007995fe94918483bd5cb5ddc38f60f61d819bea27137dfa2619bf75426`
- view manifest SHA256：`59d63560eccb443b09a868c7eb6abc159fea10ea823f6aee0378f3d3c0be85b6`
- view content SHA256：`096f7305c5ddc8821995aeda5c2f11057b386ed04ada79833051ca9e85035407`
- canonical split SHA256：`37386ca3a55d1d2971a74bdab1f1f872a8d7721a74ad28c46f8d7167b37ebfc0`
- canonical training-set SHA256：`4767a00e537e98854e2cdd9c27f5befacb1bc22cad2e7a1633bec099570b7cc1`

## 计数

- episode：`{'train': 7715, 'validation': 2574, 'test': 2562}`
- candidate edge：`{'train': 281, 'validation': 116, 'test': 83}`
- 全量 edge-free：`12532/12851`（`97.52%`）

## 未闭合门

- `edge_free_ratio_above_training_gate`
- `negative_candidate_edges_below_training_and_promotion_gates`
- `candidate_recall_not_fully_evaluable`
- `scenario_scale_dual_class_coverage_insufficient`

## 安全边界

视图不复制样本，不改变在线/离线内容，也不改变默认旧加载路径。学习输出仍不能创建、改写或换绑 `global_track_id`。几何门控、同相机互斥、版本门和规则回退保持不变。
