# 低风险文件清理完成记录

执行日期：2026年9月26日。删除完成时间：13:16:14 UTC，即America/Los_Angeles时间06:16:14。

执行依据：用户要求“删除无风险项目”，范围取自此前[人工复核清单](../20260926_cleanup_review_v1/REVIEWED_CLEANUP_LIST.csv)中主仓库的“可优先清理”条目。

## 一、执行结果

本次选定94项，全部通过删除前复核并完成清理，无跳过或失败项。共删除1,785个普通文件，文件逻辑大小为531,706,313字节，约507.07 MiB。

| 类别 | 删除项数 | 说明 |
| --- | ---: | --- |
| 重复ZIP | 7个 | 原包指纹与审计一致，包内内容对应的现存副本保留 |
| 可重建缓存 | 84个目录 | 字节码源码及pytest格式复核通过，未包含Git跟踪文件 |
| 论文中间文本 | 3个 | 从保留PDF重新提取的文本与原文件SHA-256一致 |
| 合计 | 94项 | 其中目录内普通文件计入1,785个文件总数 |

删除文件原占用磁盘块合计535,379,968字节，约510.58 MiB。执行器观测到的文件系统可用空间从33,613,492,224字节变为34,149,261,312字节；可用空间差值也可能受同时发生的系统活动影响，因此不将其作为精确的文件释放量。

## 二、删除的压缩包和中间文本

以下路径相对于`/home/linux/Documents/MSM`：

```text
paper/papers/paper.zip
paper/YOPO/YOPO.zip
paper/Fastlab_world_fly/Fastlab.zip
paper/ego-planner-swarm/EGO-planner-swarm.zip
paper/papers/中文详解/PDF.zip
paper/ego-planner/ego-planner.zip
deliverables/图片素材/ChatGPT Image Sep 7, 2026, 06_.zip

paper/other-paper/paper20.txt
paper/other-paper/paper21.txt
paper/other-paper/skywalker.txt
```

84个缓存目录的完整路径，以及其中被删除的文件名，保存在[执行结果](EXECUTION.json)的`records`中。目录只按审计清单处理，没有进行全仓库通配删除。

## 三、复核结果

1. 预检94项全部通过，正式删除前再次复核文件、缓存状态及保留副本。
2. 1,921个保留文件在删除前完成内容校验，删除后文件签名未变；EGO-Planner的保留符号链接目标未变。
3. 7个ZIP和3个文本均未被所属Git仓库跟踪，84个缓存目录未包含Git跟踪文件。
4. 主仓库和四个嵌套仓库在执行前后的已跟踪文件Git状态完全一致。随后只更新审计说明及首页。
5. 独立复查确认94个选定路径均已不存在；原人工复核清单中其余33项全部仍在。

## 四、继续保留的内容

同级`MSM-d5-training-clean`工作区的12个缓存目录未处理；四个带文档引用的下载ZIP、三个源码未确认的缓存目录、副本不完整的PDF包、六个旧实验候选目录，以及需人工决定用途的网页和检索记录全部保留。

原始PDF、解压文件、外部仓库、报告、模型、实验记录及Git历史保留。未运行算法、仿真或模型，未提交或推送。

## 五、执行记录

- [删除前预检](PREFLIGHT.json)
- [正式执行结果](EXECUTION.json)
- [逐项执行日志](EXECUTION.jsonl)
- [本次限定范围的执行脚本](cleanup_reviewed.py)
- [删除前的完整候选说明](../20260926_cleanup_review_v1/当前重复与可清理文件清单_CN.md)

原审计清单和来源哈希保留为删除前快照，本次执行结果单独保存。执行脚本检测到本批已有记录时会停止，不能将本批目录直接用于下一轮清理。
