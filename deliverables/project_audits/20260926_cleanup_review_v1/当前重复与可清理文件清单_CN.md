# 当前重复与可清理文件清单

后续执行：2026年9月26日已按用户指令清理主仓库7个重复ZIP、84个可重建缓存目录和3份论文中间文本，详见[清理完成记录](../20260926_cleanup_execution_v1/低风险文件清理完成记录_CN.md)。本文件及配套候选表保留删除前快照；下文“未删除”等表述仅指审计阶段，不代表当前执行状态。

检查日期：2026年9月26日。范围：MSM主仓库、四个嵌套外部仓库，以及此前登记的六个同级目录。本次只进行文件检查和清单生成，没有删除或移动文件。

## 一、结论

主仓库有一批明确的重复包、可重建缓存和论文中间文本，可作为第一批清理候选，文件逻辑大小合计约507.07 MiB。需保留其解压文件、源码和原始PDF。另有带文档引用的重复包，宜单独处理。旧实验目录暂未证明有完整替代，不列入优先清理范围。

| 类别 | 数量 | 逻辑大小 | 建议 |
| --- | ---: | ---: | --- |
| 主仓库完整重复的ZIP | 7个 | 451.51 MiB | 不需保留原始打包形式时，可优先清理 |
| 主仓库可重建缓存 | 84个目录 | 55.37 MiB | 确认相关任务停止后，按清单逐目录清理 |
| 可从原PDF重新生成的文本 | 3个 | 0.19 MiB | 可优先清理，保留PDF |
| 同级工作区缓存 | 12个目录 | 15.38 MiB | 不在主仓库内，单独决定 |
| 仍有文档引用的重复ZIP | 4个 | 201.95 MiB | 处理引用并保留副本对应关系后再清理 |
| 翻译检索记录、离线网页 | 1个文本、1个网页及资源目录 | 约2.06 MiB | 是否需要保留历史用途，由用户选择 |
| 旧实验复查候选 | 6个目录 | 约1.19 GiB | 暂留，需进一步核对独有内容和引用 |

上述大小均为文件逻辑大小，不是承诺释放的磁盘空间。主仓库84个缓存目录当前占用磁盘块约58.85 MiB；同级工作区12个缓存目录约16.02 MiB。实际删除前仍需检查文件是否变化、是否有相关任务使用。

逐路径清单见[人工复核清单](REVIEWED_CLEANUP_LIST.csv)，共127条，包含保留项和待复查项，不能将整份CSV当作删除列表。以下路径除特别说明外均相对于`/home/linux/Documents/MSM`。

## 二、第一批可优先清理的文件

### 1. 七个重复压缩包

| 文件 | 大小 | 核对依据 |
| --- | ---: | --- |
| `paper/papers/paper.zip` | 275.05 MiB | 19个包内普通文件均找到SHA-256一致的现存副本 |
| `paper/YOPO/YOPO.zip` | 80.14 MiB | 516个普通文件全部匹配 |
| `paper/Fastlab_world_fly/Fastlab.zip` | 29.82 MiB | 202个普通文件全部匹配 |
| `paper/ego-planner-swarm/EGO-planner-swarm.zip` | 24.18 MiB | 591个普通文件全部匹配 |
| `paper/papers/中文详解/PDF.zip` | 18.77 MiB | 26个普通文件全部匹配 |
| `paper/ego-planner/ego-planner.zip` | 17.06 MiB | 560个普通文件全部匹配，另1个符号链接本轮补查一致 |
| `deliverables/图片素材/ChatGPT Image Sep 7, 2026, 06_.zip` | 6.49 MiB | 4个普通文件全部匹配 |

七个包均未被所属Git仓库跟踪，本次有限范围引用扫描未发现直接引用。清理对象仅为表中ZIP文件，解压目录和外部仓库继续保留。原始包的权限、时间戳等打包元数据没有进行等价保存核验，因此仍需保留原始下载包的情况不适用本项。

EGO-Planner此前未确认的是`src/CMakeLists.txt`符号链接。本次读取ZIP中的链接内容，并与解压目录的链接目标比较，二者均为`/opt/ros/kinetic/share/catkin/cmake/toplevel.cmake`。该链接本身已保留，所指ROS文件当前不存在；此检查不代表ROS环境可用。

同时检查了删除候选之间的依赖：七个ZIP的匹配副本没有落入其他优先ZIP或拟清理缓存中。EGO-Swarm包内的`multi_map_server.zip`对应现存、受Git跟踪的配套包，该配套包必须保留。

### 2. 可重建缓存

| 范围 | 目录数 | 逻辑大小 |
| --- | ---: | ---: |
| 主仓库，除`paper/` | 75 | 54.62 MiB |
| 主仓库`paper/` | 9 | 0.75 MiB |
| `/home/linux/Documents/MSM-d5-training-clean/` | 12 | 15.38 MiB |

本轮共检查99个缓存目录，其中96个符合可重建条件：未发现所属仓库跟踪文件，字节码对应源码仍在，pytest缓存格式可识别，未发现符号链接或其他非普通文件。完整路径和判断见CSV中的“缓存目录”条目。

另有3个缓存目录未列入优先清理，因为包含以下4个未确认对应源码的文件：

```text
research_modules/d6_evaluation_metrics/d6_evaluation_metrics/__pycache__/learning_run_gate_evidence.cpython-312.pyc
research_modules/independent_experiments/dual_optical_100target_lightweight/__pycache__/online_protocol.cpython-312.pyc
research_modules/independent_experiments/dual_optical_100target_lightweight/__pycache__/online_training.cpython-312.pyc
research_modules/independent_experiments/dual_optical_100target_lightweight/tests/__pycache__/test_online_protocol_and_bridge.cpython-312-pytest-7.4.4.pyc
```

因此不要执行全仓库删除`__pycache__`，更不能按名称批量删除普通`cache`目录。实验缓存可能是保存的输入或结果。

### 3. 三份可重新生成的论文文本

| 中间文件 | 大小 | 保留的原始PDF |
| --- | ---: | --- |
| `paper/other-paper/paper20.txt` | 72.13 KiB | `Hierarchically Depicting Vehicle Trajectory with Stability in Complex Environments.pdf` |
| `paper/other-paper/paper21.txt` | 89.97 KiB | `Impact-Aware Planning and Control for Aerial Robots With Suspended Payloads.pdf` |
| `paper/other-paper/skywalker.txt` | 34.53 KiB | `Skywalker A Compact and Agile Air-Ground Omnidirectional Vehicle.pdf` |

三个PDF均位于`paper/other-paper/`。本次用`pdftotext`输出到标准输出，再计算SHA-256，三个结果分别与现存文本完全一致；没有写入或覆盖文本。恢复对应内容的方法为`pdftotext 原始PDF -`。这是文件格式转换核对，不涉及重新翻译。

## 三、需要先处理用途或引用的文件

### 1. 四个仍被链接的下载包

以下文件位于`paper/other-paper/archives/`，40个普通文件均有内容一致的副本，合计201.95 MiB：

| 文件 | 大小 |
| --- | ---: |
| `bulk-download.zip` | 53.09 MiB |
| `bulk-download(1).zip` | 57.45 MiB |
| `bulk-download(2).zip` | 64.58 MiB |
| `bulk-download(3).zip` | 26.82 MiB |

[论文目录说明](../../../paper/other-paper/README.md)仍链接原包，部分现存副本已经重命名。决定清理时，应同时调整该说明，并保留[机器审计](CLEANUP_AUDIT.json)中的包内文件与现存副本对应关系。

### 2. 检索中间记录和离线网页

| 对象 | 大小 | 判断 |
| --- | ---: | --- |
| `paper/english_lines.txt` | 129.21 KiB | 内容为译文文件的检索行；是否保留旧检查记录可自行选择，尚未核实完整生成命令和原时点的可重现性 |
| `deliverables/background/检索-中国知网.html` | 306.21 KiB | 保存的离线网页，若不再需要该页面可清理 |
| `deliverables/background/检索-中国知网_files/` | 约1.64 MiB | 上述网页的资源目录，应与HTML成对处理 |

定向文本搜索未发现其他已扫描代码或文档引用上述中间文本，网页命中自身标题。该判断不覆盖仓库外使用、动态路径或未展开的所有实验文件。这几项空间较小，主要作用是减少目录杂项。

## 四、旧实验仅列为复查候选

以下六个目录本次重新测量了大小，合计约1.19 GiB。它们尚未证明没有独有结果，不建议直接删除。

| 路径，省略共同前缀`research_modules/` | 大小 |
| --- | ---: |
| `airsim_runtime/outputs/d5_cv_5v5_multicamera_formal_fast_20260716` | 320.48 MiB |
| `independent_experiments/dual_optical_online_benchmark/outputs/report_replay_20260819_v1` | 255.81 MiB |
| `scalable_3d_simulation/outputs/point_mass_integrated_observation_smoke_20260722_development` | 202.80 MiB |
| `airsim_runtime/outputs/d5_cv_5v5_multicamera_preflight_20260716` | 196.72 MiB |
| `airsim_runtime/outputs/d5_cv_5v5_multicamera_preflight_alt50_20260716` | 130.86 MiB |
| `scalable_3d_simulation/outputs/point_mass_integrated_observation_smoke_20260722_development_optimized` | 111.99 MiB |

当前双光电README明确以`report_replay_20260819_v2`为报告来源，但这只说明报告采用v2，不能证明v1每个文件均可由v2替代。其他五个目录在本轮有限扫描中没有发现外部直接引用，也不能由此认定没有用途。独立备份目前未建立。

## 五、建议保留的内容

- `paper/other-paper/中文详解/PDF.zip`：36个普通文件只匹配到21个，另15个尚未找到字节一致的副本。
- 论文PDF：本次检查162个PDF，没有发现字节完全相同的重复组。`duplicates/`或`损坏重复文件/`的名称不作为删除依据；损坏与版本差异需另行鉴别。
- 已被Git跟踪的4个ZIP：根目录历史交付包、相机驱动修改包及EGO-Swarm两个配套包。
- 外部仓库中的11个编辑器备份文件：EGO-Planner有5个，EGO-Swarm有6个，均被各自Git跟踪，包括`.bridge.launch.swp`和以`~`结尾的文件。
- 当前报告引用的V3、V4、V5、S180及其他来源目录，以及正式来源生成、来源审计和登记中的Git工作区。
- `d1_structured_jacobian_multiseed_20260724_formal_9d1f54f`：此前约4.18 GiB。有限扫描曾漏掉它的引用，本次再次确认D6两个评价JSON仍保存来源依赖，不列为可清理项。
- `.git/`、原始数据、模型权重及人工改写的Word与Markdown。内容相关或名称相似不代表可相互替代。

同级目前仍有六个项目相关目录：三个来源生成目录、来源审计请求目录、来源审计结果目录和`MSM-d5-training-clean`工作区。没有再发现其他名称为`MSM-source-generation-preflight*`的同级目录。该工作区仍在`git worktree list`中登记，不能直接当普通临时文件夹删除；其中12个可重建缓存已单独列出。

## 六、空间情况与检查依据

检查时系统盘使用率93%，可用约32G。`du -sh`显示：`research_modules/`约63G，`paper/`约4.1G，`deliverables/`约397M，`.git/`约935M。这些是当前目录占用的近似值，与前一轮约25G可用空间的快照时间不同。

第一批候选约507 MiB，另加同级工作区缓存约15 MiB；处理四个下载包引用后可再考虑约202 MiB。主要空间仍由实验记录占用，不能按旧日期、失败结果或临时目录名称批量删除。

本轮只读审计读取15,097个文档、代码和选定元数据文件；329个超过2 MiB的文本候选未展开。工具没有覆盖全部动态路径、仓库外引用或所有评价文件，因此对重要大目录补充了人工引用检查。工具记录读取错误和指纹计算异常均为0。

- [人工复核清单](REVIEWED_CLEANUP_LIST.csv)：127条逐路径建议，包含主仓库与同级工作区的区分。
- [机器审计](CLEANUP_AUDIT.json)：缓存、ZIP成员匹配、PDF查重及有限范围引用。
- [补充核验](SUPPLEMENTAL_REVIEW.json)：EGO-Planner符号链接、三份文本SHA-256及旧实验目录现测大小。
- [基础候选表](CLEANUP_CANDIDATES.csv)：工具原始分类，EGO-Planner包仍显示`review_required`，最终判断以补充核验和人工复核清单为准。

本次没有执行清理。实际清理应以最终选定的条目为范围，执行前重新检查文件指纹、引用和相关进程，保留删除记录。
