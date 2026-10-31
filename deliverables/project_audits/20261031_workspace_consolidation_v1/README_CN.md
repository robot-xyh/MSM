# MSM工作区目录与分支整理记录

## 1. 执行日期与边界

执行日期：2026年10月31日。

本次仅整理已经核实的外部来源目录、干净Git工作树、空实验子目录和已完全包含的Git分支。没有移动D1至D7源码模块，没有改变正式实验目录名称，没有删除论文、报告、模型或非空实验数据。

## 2. Git提交与推送

整理前按内容分三批提交并推送到 `origin/exp/d5-ideal-20target-registration`：

| 提交 | 内容 |
|---|---|
| `d47167f` | 证据审计、压缩索引和D3至D6证据状态同步 |
| `664147c` | 四份领导报告和外场试验建议更新 |
| `9d2b102` | YOPO、Fastlab_world_fly、ego-planner和ego-planner-swarm子模块登记 |

审计工具测试为60项通过，相关Python入口语法检查通过。

## 3. 外部目录归并

原先位于 `/home/linux/Documents/` 下的三个来源生成目录和两个来源审计目录，已移入统一目录 `/home/linux/Documents/MSM-archive/`。每个批次保留独立子目录，没有平铺混合D3、D4、D5数据。

移动前后逐项核对目录大小和文件数量，五组结果均一致。详细路径见 `RELOCATION_MAP.tsv`。整理后 `/home/linux/Documents/` 下以 `MSM` 开头的实体目录由7个减少为2个：

- `/home/linux/Documents/MSM`；
- `/home/linux/Documents/MSM-archive`。

## 4. 工作树与空目录

`/home/linux/Documents/MSM-d5-training-clean` 为干净的游离工作树，其提交已被当前D5分支、原200对200分支及相应远程分支包含。本次通过Git工作树命令移除，未丢失独有提交。

实验输出中共移除515个嵌套空目录。5个仍为空的顶层实验编号目录继续保留，用于维持历史实验编号和路径语义。

## 5. 分支整理

整理前本地分支6个、远程分支3个；整理后本地分支5个、远程分支2个。

处理内容：

1. 为旧 `main` 建立并推送标签 `archive/main-before-20261031-consolidation`；
2. 将 `main` 快进到 `9d2b102` 并推送；
3. 为 `feat/scalable-3d-200v200` 建立并推送标签 `archive/scalable-3d-200v200-20260807`；
4. 确认该分支已被当前D5分支完整包含后，删除本地和远程分支；
5. 三个D1试验分支相互分叉且未进入当前主线，继续保留。

当前 `main` 与 `exp/d5-ideal-20target-registration` 指向同一提交。详细状态见 `BRANCH_STATE.tsv`。

## 6. 路径使用说明

历史审计文件中的旧绝对路径继续作为当时记录保留，不批量改写。后续需要访问来源生成数据时，应根据 `RELOCATION_MAP.tsv` 使用新的归档路径。
