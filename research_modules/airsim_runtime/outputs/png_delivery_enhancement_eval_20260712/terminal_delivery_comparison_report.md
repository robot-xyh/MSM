# D7 PNG Delivery 增强真实 AirSim 多 Seed 评估

本报告只消费已经写盘的 D5/D7/main 日志，不参与导引、授权或控制。缺失字段按 `unavailable/NA` 展示，不按零值处理。

- Episode 数量：26
- 分组口径：显式 profile、metric scope、scenario group 与实际 N/M 规模。
- 2v2 与 M5N2 分开统计；M5N2 的 target、active-primary pair 和 coalition completion 不互相替代。

## 分组结果

| Scope | 场景 | Profile | 资源/目标 | Seeds | Contract | Control | Mode switch | Pair physical | Target success | Coalition completion |
|---|---|---|---|---|---:|---:|---:|---:|---:|---:|
| real_airsim_simpleflight | airsim_2v2 | baseline | 2/2 | 1,2,3,4,5,6,7,8,9,10 | NA | NA | NA | 19 | 19 | 0 |
| real_airsim_simpleflight | airsim_2v2 | candidate_soft_prediction_trend_coast | 2/2 | 1,2,3,4,5,6,7,8,9,10 | NA | NA | NA | 20 | 20 | 0 |
| real_airsim_simpleflight | airsim_m5n2_high_clearance_35s | baseline | 5/2 | 1,2,3 | NA | NA | NA | 6 | 6 | 0 |
| real_airsim_simpleflight | airsim_m5n2_short_window_8s | candidate_soft_prediction_trend_coast | 5/2 | 1,2,3 | NA | NA | NA | 0 | 0 | NA |

## PNG Delivery 诊断

| Scope/场景/Profile/N/M | 指标 | 可用 | unavailable | Sum | Mean | Std |
|---|---|---:|---:|---:|---:|---:|
| real_airsim_simpleflight/airsim_2v2/baseline/2/2 | terminal_filter_measured_count | 10 | 0 | 185 | 18.5 | 3.17105 |
| real_airsim_simpleflight/airsim_2v2/baseline/2/2 | terminal_filter_predicted_count | 10 | 0 | 0 | 0 | 0 |
| real_airsim_simpleflight/airsim_2v2/baseline/2/2 | terminal_filter_innovation_rejected_count | 0 | 10 | unavailable | unavailable | unavailable |
| real_airsim_simpleflight/airsim_2v2/baseline/2/2 | terminal_filter_reset_count | 0 | 10 | unavailable | unavailable | unavailable |
| real_airsim_simpleflight/airsim_2v2/baseline/2/2 | terminal_filter_expired_count | 10 | 0 | 500 | 50 | 91.6867 |
| real_airsim_simpleflight/airsim_2v2/baseline/2/2 | ttc_area_jump_reject_count | 0 | 10 | unavailable | unavailable | unavailable |
| real_airsim_simpleflight/airsim_2v2/baseline/2/2 | ttc_bbox_clipping_reject_count | 0 | 10 | unavailable | unavailable | unavailable |
| real_airsim_simpleflight/airsim_2v2/baseline/2/2 | ttc_not_expanding_reject_count | 0 | 10 | unavailable | unavailable | unavailable |
| real_airsim_simpleflight/airsim_2v2/baseline/2/2 | ttc_out_of_range_reject_count | 0 | 10 | unavailable | unavailable | unavailable |
| real_airsim_simpleflight/airsim_2v2/baseline/2/2 | soft_prediction_count | 0 | 10 | unavailable | unavailable | unavailable |
| real_airsim_simpleflight/airsim_2v2/baseline/2/2 | soft_prediction_duration_s | 10 | 0 | 0 | 0 | 0 |
| real_airsim_simpleflight/airsim_2v2/baseline/2/2 | soft_prediction_expired_count | 0 | 10 | unavailable | unavailable | unavailable |
| real_airsim_simpleflight/airsim_2v2/baseline/2/2 | terminal_coast_count | 10 | 0 | 0 | 0 | 0 |
| real_airsim_simpleflight/airsim_2v2/baseline/2/2 | terminal_coast_duration_s | 10 | 0 | 0 | 0 | 0 |
| real_airsim_simpleflight/airsim_2v2/baseline/2/2 | terminal_coast_expired_count | 0 | 10 | unavailable | unavailable | unavailable |
| real_airsim_simpleflight/airsim_2v2/baseline/2/2 | terminal_lock_continuity | 9 | 1 | 9 | 1 | 0 |
| real_airsim_simpleflight/airsim_2v2/baseline/2/2 | visual_mode_duration_s | 10 | 0 | 10.5 | 1.05 | 0.383695 |
| real_airsim_simpleflight/airsim_2v2/baseline/2/2 | command_discontinuity_mean_mps | 10 | 0 | 4.72722 | 0.472722 | 0.120892 |
| real_airsim_simpleflight/airsim_2v2/baseline/2/2 | command_discontinuity_max_mps | 10 | 0 | 95.7365 | 9.57365 | 2.47392 |
| real_airsim_simpleflight/airsim_2v2/baseline/2/2 | contract_allowed_count | 0 | 10 | unavailable | unavailable | unavailable |
| real_airsim_simpleflight/airsim_2v2/baseline/2/2 | control_allowed_count | 0 | 10 | unavailable | unavailable | unavailable |
| real_airsim_simpleflight/airsim_2v2/baseline/2/2 | mode_switched_count | 0 | 10 | unavailable | unavailable | unavailable |
| real_airsim_simpleflight/airsim_2v2/baseline/2/2 | physical_intercept_count | 10 | 0 | 19 | 1.9 | 0.316228 |
| real_airsim_simpleflight/airsim_2v2/baseline/2/2 | pair_physical_success_count | 10 | 0 | 19 | 1.9 | 0.316228 |
| real_airsim_simpleflight/airsim_2v2/baseline/2/2 | pair_physical_success_rate | 10 | 0 | 9.5 | 0.95 | 0.158114 |
| real_airsim_simpleflight/airsim_2v2/baseline/2/2 | target_intercept_success_count | 10 | 0 | 19 | 1.9 | 0.316228 |
| real_airsim_simpleflight/airsim_2v2/baseline/2/2 | target_intercept_success_rate | 10 | 0 | 9.5 | 0.95 | 0.158114 |
| real_airsim_simpleflight/airsim_2v2/baseline/2/2 | coalition_completion_count | 10 | 0 | 0 | 0 | 0 |
| real_airsim_simpleflight/airsim_2v2/baseline/2/2 | coalition_completion_rate | 0 | 10 | unavailable | unavailable | unavailable |
| real_airsim_simpleflight/airsim_2v2/candidate_soft_prediction_trend_coast/2/2 | terminal_filter_measured_count | 10 | 0 | 39 | 3.9 | 0.316228 |
| real_airsim_simpleflight/airsim_2v2/candidate_soft_prediction_trend_coast/2/2 | terminal_filter_predicted_count | 10 | 0 | 0 | 0 | 0 |
| real_airsim_simpleflight/airsim_2v2/candidate_soft_prediction_trend_coast/2/2 | terminal_filter_innovation_rejected_count | 10 | 0 | 0 | 0 | 0 |
| real_airsim_simpleflight/airsim_2v2/candidate_soft_prediction_trend_coast/2/2 | terminal_filter_reset_count | 10 | 0 | 0 | 0 | 0 |
| real_airsim_simpleflight/airsim_2v2/candidate_soft_prediction_trend_coast/2/2 | terminal_filter_expired_count | 10 | 0 | 11 | 1.1 | 0.316228 |
| real_airsim_simpleflight/airsim_2v2/candidate_soft_prediction_trend_coast/2/2 | ttc_area_jump_reject_count | 0 | 10 | unavailable | unavailable | unavailable |
| real_airsim_simpleflight/airsim_2v2/candidate_soft_prediction_trend_coast/2/2 | ttc_bbox_clipping_reject_count | 0 | 10 | unavailable | unavailable | unavailable |
| real_airsim_simpleflight/airsim_2v2/candidate_soft_prediction_trend_coast/2/2 | ttc_not_expanding_reject_count | 0 | 10 | unavailable | unavailable | unavailable |
| real_airsim_simpleflight/airsim_2v2/candidate_soft_prediction_trend_coast/2/2 | ttc_out_of_range_reject_count | 0 | 10 | unavailable | unavailable | unavailable |
| real_airsim_simpleflight/airsim_2v2/candidate_soft_prediction_trend_coast/2/2 | soft_prediction_count | 0 | 10 | unavailable | unavailable | unavailable |
| real_airsim_simpleflight/airsim_2v2/candidate_soft_prediction_trend_coast/2/2 | soft_prediction_duration_s | 10 | 0 | 0 | 0 | 0 |
| real_airsim_simpleflight/airsim_2v2/candidate_soft_prediction_trend_coast/2/2 | soft_prediction_expired_count | 0 | 10 | unavailable | unavailable | unavailable |
| real_airsim_simpleflight/airsim_2v2/candidate_soft_prediction_trend_coast/2/2 | terminal_coast_count | 10 | 0 | 0 | 0 | 0 |
| real_airsim_simpleflight/airsim_2v2/candidate_soft_prediction_trend_coast/2/2 | terminal_coast_duration_s | 10 | 0 | 0 | 0 | 0 |
| real_airsim_simpleflight/airsim_2v2/candidate_soft_prediction_trend_coast/2/2 | terminal_coast_expired_count | 0 | 10 | unavailable | unavailable | unavailable |
| real_airsim_simpleflight/airsim_2v2/candidate_soft_prediction_trend_coast/2/2 | terminal_lock_continuity | 10 | 0 | 10 | 1 | 0 |
| real_airsim_simpleflight/airsim_2v2/candidate_soft_prediction_trend_coast/2/2 | visual_mode_duration_s | 10 | 0 | 1.9 | 0.19 | 0.0316228 |
| real_airsim_simpleflight/airsim_2v2/candidate_soft_prediction_trend_coast/2/2 | command_discontinuity_mean_mps | 10 | 0 | 3.96931 | 0.396931 | 0.00852329 |
| real_airsim_simpleflight/airsim_2v2/candidate_soft_prediction_trend_coast/2/2 | command_discontinuity_max_mps | 10 | 0 | 60 | 6 | 7.833e-16 |
| real_airsim_simpleflight/airsim_2v2/candidate_soft_prediction_trend_coast/2/2 | contract_allowed_count | 0 | 10 | unavailable | unavailable | unavailable |
| real_airsim_simpleflight/airsim_2v2/candidate_soft_prediction_trend_coast/2/2 | control_allowed_count | 0 | 10 | unavailable | unavailable | unavailable |
| real_airsim_simpleflight/airsim_2v2/candidate_soft_prediction_trend_coast/2/2 | mode_switched_count | 0 | 10 | unavailable | unavailable | unavailable |
| real_airsim_simpleflight/airsim_2v2/candidate_soft_prediction_trend_coast/2/2 | physical_intercept_count | 10 | 0 | 20 | 2 | 0 |
| real_airsim_simpleflight/airsim_2v2/candidate_soft_prediction_trend_coast/2/2 | pair_physical_success_count | 10 | 0 | 20 | 2 | 0 |
| real_airsim_simpleflight/airsim_2v2/candidate_soft_prediction_trend_coast/2/2 | pair_physical_success_rate | 10 | 0 | 10 | 1 | 0 |
| real_airsim_simpleflight/airsim_2v2/candidate_soft_prediction_trend_coast/2/2 | target_intercept_success_count | 10 | 0 | 20 | 2 | 0 |
| real_airsim_simpleflight/airsim_2v2/candidate_soft_prediction_trend_coast/2/2 | target_intercept_success_rate | 10 | 0 | 10 | 1 | 0 |
| real_airsim_simpleflight/airsim_2v2/candidate_soft_prediction_trend_coast/2/2 | coalition_completion_count | 10 | 0 | 0 | 0 | 0 |
| real_airsim_simpleflight/airsim_2v2/candidate_soft_prediction_trend_coast/2/2 | coalition_completion_rate | 0 | 10 | unavailable | unavailable | unavailable |
| real_airsim_simpleflight/airsim_m5n2_high_clearance_35s/baseline/5/2 | terminal_filter_measured_count | 1 | 2 | 5 | 5 | 0 |
| real_airsim_simpleflight/airsim_m5n2_high_clearance_35s/baseline/5/2 | terminal_filter_predicted_count | 1 | 2 | 0 | 0 | 0 |
| real_airsim_simpleflight/airsim_m5n2_high_clearance_35s/baseline/5/2 | terminal_filter_innovation_rejected_count | 0 | 3 | unavailable | unavailable | unavailable |
| real_airsim_simpleflight/airsim_m5n2_high_clearance_35s/baseline/5/2 | terminal_filter_reset_count | 0 | 3 | unavailable | unavailable | unavailable |
| real_airsim_simpleflight/airsim_m5n2_high_clearance_35s/baseline/5/2 | terminal_filter_expired_count | 1 | 2 | 56 | 56 | 0 |
| real_airsim_simpleflight/airsim_m5n2_high_clearance_35s/baseline/5/2 | ttc_area_jump_reject_count | 0 | 3 | unavailable | unavailable | unavailable |
| real_airsim_simpleflight/airsim_m5n2_high_clearance_35s/baseline/5/2 | ttc_bbox_clipping_reject_count | 0 | 3 | unavailable | unavailable | unavailable |
| real_airsim_simpleflight/airsim_m5n2_high_clearance_35s/baseline/5/2 | ttc_not_expanding_reject_count | 0 | 3 | unavailable | unavailable | unavailable |
| real_airsim_simpleflight/airsim_m5n2_high_clearance_35s/baseline/5/2 | ttc_out_of_range_reject_count | 0 | 3 | unavailable | unavailable | unavailable |
| real_airsim_simpleflight/airsim_m5n2_high_clearance_35s/baseline/5/2 | soft_prediction_count | 0 | 3 | unavailable | unavailable | unavailable |
| real_airsim_simpleflight/airsim_m5n2_high_clearance_35s/baseline/5/2 | soft_prediction_duration_s | 1 | 2 | 0 | 0 | 0 |
| real_airsim_simpleflight/airsim_m5n2_high_clearance_35s/baseline/5/2 | soft_prediction_expired_count | 0 | 3 | unavailable | unavailable | unavailable |
| real_airsim_simpleflight/airsim_m5n2_high_clearance_35s/baseline/5/2 | terminal_coast_count | 1 | 2 | 0 | 0 | 0 |
| real_airsim_simpleflight/airsim_m5n2_high_clearance_35s/baseline/5/2 | terminal_coast_duration_s | 3 | 0 | 0 | 0 | 0 |
| real_airsim_simpleflight/airsim_m5n2_high_clearance_35s/baseline/5/2 | terminal_coast_expired_count | 0 | 3 | unavailable | unavailable | unavailable |
| real_airsim_simpleflight/airsim_m5n2_high_clearance_35s/baseline/5/2 | terminal_lock_continuity | 0 | 3 | unavailable | unavailable | unavailable |
| real_airsim_simpleflight/airsim_m5n2_high_clearance_35s/baseline/5/2 | visual_mode_duration_s | 3 | 0 | 0 | 0 | 0 |
| real_airsim_simpleflight/airsim_m5n2_high_clearance_35s/baseline/5/2 | command_discontinuity_mean_mps | 3 | 0 | 0.987575 | 0.329192 | 0.00818804 |
| real_airsim_simpleflight/airsim_m5n2_high_clearance_35s/baseline/5/2 | command_discontinuity_max_mps | 3 | 0 | 31.2554 | 10.4185 | 0.884845 |
| real_airsim_simpleflight/airsim_m5n2_high_clearance_35s/baseline/5/2 | contract_allowed_count | 0 | 3 | unavailable | unavailable | unavailable |
| real_airsim_simpleflight/airsim_m5n2_high_clearance_35s/baseline/5/2 | control_allowed_count | 0 | 3 | unavailable | unavailable | unavailable |
| real_airsim_simpleflight/airsim_m5n2_high_clearance_35s/baseline/5/2 | mode_switched_count | 0 | 3 | unavailable | unavailable | unavailable |
| real_airsim_simpleflight/airsim_m5n2_high_clearance_35s/baseline/5/2 | physical_intercept_count | 3 | 0 | 6 | 2 | 0 |
| real_airsim_simpleflight/airsim_m5n2_high_clearance_35s/baseline/5/2 | pair_physical_success_count | 3 | 0 | 6 | 2 | 0 |
| real_airsim_simpleflight/airsim_m5n2_high_clearance_35s/baseline/5/2 | pair_physical_success_rate | 3 | 0 | 2 | 0.666667 | 0 |
| real_airsim_simpleflight/airsim_m5n2_high_clearance_35s/baseline/5/2 | target_intercept_success_count | 3 | 0 | 6 | 2 | 0 |
| real_airsim_simpleflight/airsim_m5n2_high_clearance_35s/baseline/5/2 | target_intercept_success_rate | 3 | 0 | 3 | 1 | 0 |
| real_airsim_simpleflight/airsim_m5n2_high_clearance_35s/baseline/5/2 | coalition_completion_count | 1 | 2 | 0 | 0 | 0 |
| real_airsim_simpleflight/airsim_m5n2_high_clearance_35s/baseline/5/2 | coalition_completion_rate | 1 | 2 | 0 | 0 | 0 |
| real_airsim_simpleflight/airsim_m5n2_short_window_8s/candidate_soft_prediction_trend_coast/5/2 | terminal_filter_measured_count | 3 | 0 | 45 | 15 | 8.7178 |
| real_airsim_simpleflight/airsim_m5n2_short_window_8s/candidate_soft_prediction_trend_coast/5/2 | terminal_filter_predicted_count | 3 | 0 | 4 | 1.33333 | 1.1547 |
| real_airsim_simpleflight/airsim_m5n2_short_window_8s/candidate_soft_prediction_trend_coast/5/2 | terminal_filter_innovation_rejected_count | 3 | 0 | 2 | 0.666667 | 0.57735 |
| real_airsim_simpleflight/airsim_m5n2_short_window_8s/candidate_soft_prediction_trend_coast/5/2 | terminal_filter_reset_count | 3 | 0 | 0 | 0 | 0 |
| real_airsim_simpleflight/airsim_m5n2_short_window_8s/candidate_soft_prediction_trend_coast/5/2 | terminal_filter_expired_count | 3 | 0 | 97 | 32.3333 | 13.2035 |
| real_airsim_simpleflight/airsim_m5n2_short_window_8s/candidate_soft_prediction_trend_coast/5/2 | ttc_area_jump_reject_count | 0 | 3 | unavailable | unavailable | unavailable |
| real_airsim_simpleflight/airsim_m5n2_short_window_8s/candidate_soft_prediction_trend_coast/5/2 | ttc_bbox_clipping_reject_count | 0 | 3 | unavailable | unavailable | unavailable |
| real_airsim_simpleflight/airsim_m5n2_short_window_8s/candidate_soft_prediction_trend_coast/5/2 | ttc_not_expanding_reject_count | 0 | 3 | unavailable | unavailable | unavailable |
| real_airsim_simpleflight/airsim_m5n2_short_window_8s/candidate_soft_prediction_trend_coast/5/2 | ttc_out_of_range_reject_count | 0 | 3 | unavailable | unavailable | unavailable |
| real_airsim_simpleflight/airsim_m5n2_short_window_8s/candidate_soft_prediction_trend_coast/5/2 | soft_prediction_count | 0 | 3 | unavailable | unavailable | unavailable |
| real_airsim_simpleflight/airsim_m5n2_short_window_8s/candidate_soft_prediction_trend_coast/5/2 | soft_prediction_duration_s | 3 | 0 | 0 | 0 | 0 |
| real_airsim_simpleflight/airsim_m5n2_short_window_8s/candidate_soft_prediction_trend_coast/5/2 | soft_prediction_expired_count | 0 | 3 | unavailable | unavailable | unavailable |
| real_airsim_simpleflight/airsim_m5n2_short_window_8s/candidate_soft_prediction_trend_coast/5/2 | terminal_coast_count | 3 | 0 | 0 | 0 | 0 |
| real_airsim_simpleflight/airsim_m5n2_short_window_8s/candidate_soft_prediction_trend_coast/5/2 | terminal_coast_duration_s | 3 | 0 | 0 | 0 | 0 |
| real_airsim_simpleflight/airsim_m5n2_short_window_8s/candidate_soft_prediction_trend_coast/5/2 | terminal_coast_expired_count | 0 | 3 | unavailable | unavailable | unavailable |
| real_airsim_simpleflight/airsim_m5n2_short_window_8s/candidate_soft_prediction_trend_coast/5/2 | terminal_lock_continuity | 0 | 3 | unavailable | unavailable | unavailable |
| real_airsim_simpleflight/airsim_m5n2_short_window_8s/candidate_soft_prediction_trend_coast/5/2 | visual_mode_duration_s | 3 | 0 | 0 | 0 | 0 |
| real_airsim_simpleflight/airsim_m5n2_short_window_8s/candidate_soft_prediction_trend_coast/5/2 | command_discontinuity_mean_mps | 3 | 0 | 0.909219 | 0.303073 | 0.0268654 |
| real_airsim_simpleflight/airsim_m5n2_short_window_8s/candidate_soft_prediction_trend_coast/5/2 | command_discontinuity_max_mps | 3 | 0 | 27.1418 | 9.04726 | 0.397832 |
| real_airsim_simpleflight/airsim_m5n2_short_window_8s/candidate_soft_prediction_trend_coast/5/2 | contract_allowed_count | 0 | 3 | unavailable | unavailable | unavailable |
| real_airsim_simpleflight/airsim_m5n2_short_window_8s/candidate_soft_prediction_trend_coast/5/2 | control_allowed_count | 0 | 3 | unavailable | unavailable | unavailable |
| real_airsim_simpleflight/airsim_m5n2_short_window_8s/candidate_soft_prediction_trend_coast/5/2 | mode_switched_count | 0 | 3 | unavailable | unavailable | unavailable |
| real_airsim_simpleflight/airsim_m5n2_short_window_8s/candidate_soft_prediction_trend_coast/5/2 | physical_intercept_count | 3 | 0 | 0 | 0 | 0 |
| real_airsim_simpleflight/airsim_m5n2_short_window_8s/candidate_soft_prediction_trend_coast/5/2 | pair_physical_success_count | 3 | 0 | 0 | 0 | 0 |
| real_airsim_simpleflight/airsim_m5n2_short_window_8s/candidate_soft_prediction_trend_coast/5/2 | pair_physical_success_rate | 3 | 0 | 0 | 0 | 0 |
| real_airsim_simpleflight/airsim_m5n2_short_window_8s/candidate_soft_prediction_trend_coast/5/2 | target_intercept_success_count | 3 | 0 | 0 | 0 | 0 |
| real_airsim_simpleflight/airsim_m5n2_short_window_8s/candidate_soft_prediction_trend_coast/5/2 | target_intercept_success_rate | 3 | 0 | 0 | 0 | 0 |
| real_airsim_simpleflight/airsim_m5n2_short_window_8s/candidate_soft_prediction_trend_coast/5/2 | coalition_completion_count | 0 | 3 | unavailable | unavailable | unavailable |
| real_airsim_simpleflight/airsim_m5n2_short_window_8s/candidate_soft_prediction_trend_coast/5/2 | coalition_completion_rate | 0 | 3 | unavailable | unavailable | unavailable |

## 解释约束

- `measured/predicted/rejected/reset/expired` 是滤波样本或事件计数，不等同于目标命中数。
- soft prediction 与 coast 只评估持续时间、到期和控制平滑性；不得作为身份或授权证据。
- `physical_intercept_5m` 只来自显式物理拦截证据；ComputerVision 只读 episode 应为 unavailable。
- M5N2 中任一目标成功不能回填全部 active-primary pair 成功，也不能回填 coalition completion。
