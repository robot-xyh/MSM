# D5 人工初始化五目标视频轨迹关联报告

## 1. 目的与边界

本实验对 `research_modules/b.mp4` 中五个相邻亮目标建立单相机本地轨迹。目标在首帧由人工 ROI 顺序初始化，生成 `local-001` 至 `local-005`。实验不读取视频中的真实目标身份，不使用 actor name、truth ID 或 `global_track_id`。

本工具只回答“同一视频中的五条本地轨迹能否保持区分”。它不完成 GlobalTrack 注册、跨相机关联、敌我识别、任务分配或 D7 控制许可。

## 2. 输入与方法

- 视频：`496 x 640`，`5 FPS`，`95` 帧。
- 初始中心约为 `(373,281)`、`(392,268)`、`(411,274)`、`(437,266)`、`(457,266)`。
- 最终初始框均为 `12 x 12 px`：`367,275,12,12;386,262,12,12;405,268,12,12;431,260,12,12;451,260,12,12`。
- 每个目标维护独立 OpenCV CSRT tracker。
- 专项关联层以 `gray - GaussianBlur(31x31)` 和阈值 `12` 在全帧提取正对比亮点候选，不写死 y 范围；以最近两次有效中心作常速度预测，再通过 Hungarian 算法执行一对一分配，门限为 `20 px`。
- 无候选或关联超门限时写 `lost`，bbox 和 center 留空；恢复后保持原 `local_track_id`。

纯 CSRT 对照中，16 像素框第 28 帧出现完全重叠，12 像素框第 38 帧出现完全重叠；KCF 只有 2-3 个有效帧。因此最终结果采用 `CSRT + bright_hungarian`，不能只用 tracker 的 success 标志评价身份连续性。纯 CSRT summary 的 `95/95 measured` 是假连续性对照，不是身份保持验收结论。

## 3. 结果

| 本地轨迹 | 有效帧 | 丢失帧 | 丢失帧号 | 首帧中心 | 末帧中心 |
| --- | ---: | ---: | --- | --- | --- |
| `local-001` | 92 | 3 | 57, 58, 89 | `(373,281)` | `(6,322)` |
| `local-002` | 95 | 0 | 无 | `(392,268)` | `(6,313)` |
| `local-003` | 93 | 2 | 34, 35 | `(411,274)` | `(16,319)` |
| `local-004` | 95 | 0 | 无 | `(437,266)` | `(33,304)` |
| `local-005` | 95 | 0 | 无 | `(457,266)` | `(52,300)` |

附加区分指标：

- 有效轨迹最小中心间距：`5 px`。
- 最大 bbox 交并比：`0.4118`。
- 完全重复中心：`0`。
- summary `duplicate_measurement_count`：`0`。
- 处理完成：`95/95` 帧。

结果表明五个本地 ID 没有合并为同一条有效量测。`local-001` 和 `local-003` 在候选不满足门限时保守输出 lost，并在后续重新检测到对应亮点后恢复原 ID。

## 4. 产物

- 标注视频：`outputs/manual_video_tracking/b_bright_hungarian_20260715/b_manual_tracks.mp4`
- 逐帧记录：`outputs/manual_video_tracking/b_bright_hungarian_20260715/b_manual_tracks.csv`
- 汇总：`outputs/manual_video_tracking/b_bright_hungarian_20260715/b_manual_tracks_summary.json`
- 多时刻检查图：`outputs/manual_video_tracking/b_bright_hungarian_20260715/tracking_contact_sheet.jpg`

## 5. 限制

亮点候选依赖目标相对背景具有稳定正对比，不能直接推广到普通可见光纹理目标、强遮挡、剧烈相机运动或交叉后外观相同的目标。人工初始化 local ID 也不具备系统级身份含义。进入 D5 主关联链前，仍需中心 GlobalTrack 投影、相机内外参、双时间戳、协方差、几何门限、计划版本和友方冲突检查。

## 6. 验证

2026-07-15 完成：D5 全量 `284 passed`，`python3 -m py_compile` 和 owned-path `git diff --check` 通过。真实输出 MP4 可读为 95 帧，CSV 为 475 行，接受阈值为零测试失败且 summary `duplicate_measurement_count=0`。
