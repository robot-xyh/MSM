# 可清理数据审计

日期：2026年9月25日。范围：主仓库、四个嵌套外部仓库及此前登记的六个同级目录。

## 一、结论

目前可优先考虑清理的是可重建缓存和已经核对一致的重复压缩包。旧实验输出中存在被新版报告替代的目录，但还没有足够依据将其全部判为可直接删除。

| 类别 | 数量或范围 | 大小 | 建议 |
| --- | --- | ---: | --- |
| 已确认可重建的缓存 | 96个目录、2,114个文件 | 文件内容70.75 MiB，已分配磁盘块约74.87 MiB | 停止相关测试和Python任务后可清理 |
| 内容完整重复、未查到直接引用的ZIP | 6个 | 434.45 MiB | 保留解压文件，确认不再需要原始打包形式后可清理 |
| 内容完整重复、仍有资料链接的ZIP | 4个 | 201.95 MiB | 先处理资料入口和原始下载包保留要求，再决定删除 |
| 较小的旧实验复查候选 | 6个目录 | 1.19 GiB | 先归档、核对替代关系；本次不列入直接删除清单 |
| 两个较大的开发期输出 | 2个目录 | 合计约3.92 GiB | 暂留；没有证明两者内容相同，也没有确认依赖已解除 |

本轮没有删除或移动任何原文件，也没有修改算法、重新运行实验、提交或推送。独立备份仍未建立。表中压缩包和实验目录大小按文件逻辑大小统计，不能直接等同于删除后一定增加的可用空间。

## 二、可重建缓存

检查了99个缓存目录。96个目录满足以下条件：未发现Git跟踪文件，Python字节码对应源码仍在，pytest缓存格式可识别，没有发现符号链接或其他非普通文件。

| 位置 | 目录数 | 文件内容大小 |
| --- | ---: | ---: |
| 主项目，除`paper/` | 75 | 54.62 MiB |
| `paper/`资料工具和外部仓库 | 9 | 0.75 MiB |
| `MSM-d5-training-clean`工作区 | 12 | 15.38 MiB |

这些缓存删除后会由Python或测试工具重新生成，不涉及实验观测、训练权重和报告配图。清理应严格按清单中的`regenerable_cache`条目执行，不能扩展为删除所有名称含`cache`的目录。实验中的普通`cache`目录可能保存不可直接重建的输入或结果。

另有3个缓存目录暂留，因为包含4个没有找到对应源码的字节码：

- `research_modules/d6_evaluation_metrics/d6_evaluation_metrics/__pycache__/learning_run_gate_evidence.cpython-312.pyc`
- `research_modules/independent_experiments/dual_optical_100target_lightweight/__pycache__/online_protocol.cpython-312.pyc`
- `research_modules/independent_experiments/dual_optical_100target_lightweight/__pycache__/online_training.cpython-312.pyc`
- `research_modules/independent_experiments/dual_optical_100target_lightweight/tests/__pycache__/test_online_protocol_and_bridge.cpython-312-pytest-7.4.4.pyc`

这不表示字节码一定有保留价值，但在确认对应源码已迁移或可从历史版本恢复前，不将整个目录判为可重建。

## 三、已核对一致的压缩包

### 1. 可优先考虑的六个包

以下压缩包未被所属Git仓库跟踪。包内每个普通文件均已计算SHA-256，并在相应解压位置找到内容一致的文件；本次引用检查未发现直接引用这些包名的文档或代码。

| 压缩包，相对于仓库根目录 | 大小 | 已匹配包内文件数 |
| --- | ---: | ---: |
| `paper/papers/paper.zip` | 275.05 MiB | 19 |
| `paper/YOPO/YOPO.zip` | 80.14 MiB | 516 |
| `paper/Fastlab_world_fly/Fastlab.zip` | 29.82 MiB | 202 |
| `paper/ego-planner-swarm/EGO-planner-swarm.zip` | 24.18 MiB | 591 |
| `paper/papers/中文详解/PDF.zip` | 18.77 MiB | 26 |
| `deliverables/图片素材/ChatGPT Image Sep 7, 2026, 06_.zip` | 6.49 MiB | 4 |

清理只针对ZIP文件，不删除其解压目录或外部仓库。删除会失去原始包的打包元数据；核对内容相同不等于验证了权限、时间戳等归档信息。未发现直接引用也不排除仓库外的使用，因此执行前仍需确认不再需要这些原始包。

### 2. 先处理引用的四个包

`paper/other-paper/archives/`下四个下载包的40个包内文件，均在现有资料中找到内容一致的副本，合计201.95 MiB：

| 压缩包 | 大小 |
| --- | ---: |
| `bulk-download.zip` | 53.09 MiB |
| `bulk-download(1).zip` | 57.45 MiB |
| `bulk-download(2).zip` | 64.58 MiB |
| `bulk-download(3).zip` | 26.82 MiB |

[论文目录说明](../../../paper/other-paper/README.md)仍链接这四个原始下载包，现存副本的目录或文件名也不完全保持包内布局。删除前应决定是否继续保留原始下载包；如不保留，需要同步处理资料链接，并保留本次包内文件到现存文件的对应记录。本轮没有修改这些链接。

## 四、暂时不能清理的压缩包和论文

| 对象 | 原因 |
| --- | --- |
| `paper/other-paper/中文详解/PDF.zip` | 共36个普通文件，只匹配到21个；另外15个在本次扫描范围内未找到字节一致的副本，可能是不同导出版本 |
| `paper/ego-planner/ego-planner.zip` | 普通内容已匹配560项，但另含`src/CMakeLists.txt`符号链接，当前工具未核验该链接的等价保存关系 |
| 已被Git跟踪的4个ZIP | 分别是根目录历史交付包、相机驱动修改包，以及EGO-Swarm中的两个配套包；不按未跟踪下载副本处理 |
| `paper/other-paper/duplicates/`及其他论文PDF | 本次扫描162个PDF，未查到字节完全相同的重复组；目录名相同或论文题目相似不能证明文件可互相替代 |

没有找到一致副本，不等于对应论文题材唯一；相同论文的不同版本、附件或导出文件仍可能不同。本轮未进行语义去重或论文版本取舍。

## 五、旧实验数据的判断

### 1. 已被新版报告替代的候选

`research_modules/independent_experiments/dual_optical_online_benchmark/outputs/report_replay_20260819_v1/`约255.81 MiB，可优先做归档后清理复核。

依据是[当前实验README](../../../research_modules/independent_experiments/dual_optical_online_benchmark/README.md)明确指定`report_replay_20260819_v2`为当前报告的权威目录，报告生成器也引用v2。v1根目录只有`campaign_config.json`，没有v2所具有的最终汇总和复现清单。本次在已扫描文档与选定元数据中未查到v1的外部直接引用。

但是，本次尚未逐文件证明v1全部内容都已被v2覆盖，也未建立独立备份。因此其状态是“旧版归档后清理候选”，不是“现在可以无风险删除”。

### 2. 其他小规模复查候选

下列目录未在本次字面引用扫描中找到外部引用，可以优先核对是否还有保留需要。加上前述v1，六个目录合计约1.19 GiB。

| 目录，省略共同前缀`research_modules/` | 大小 |
| --- | ---: |
| `airsim_runtime/outputs/d5_cv_5v5_multicamera_formal_fast_20260716` | 320.48 MiB |
| `scalable_3d_simulation/outputs/point_mass_integrated_observation_smoke_20260722_development` | 202.80 MiB |
| `airsim_runtime/outputs/d5_cv_5v5_multicamera_preflight_20260716` | 196.72 MiB |
| `airsim_runtime/outputs/d5_cv_5v5_multicamera_preflight_alt50_20260716` | 130.86 MiB |
| `scalable_3d_simulation/outputs/point_mass_integrated_observation_smoke_20260722_development_optimized` | 111.99 MiB |

这些条目只证明“值得先复查”，没有证明可直接删除。目录名包含`preflight`、`smoke`或`development`不构成删除依据。

### 3. 大目录仍需保留

两个`d1_global_track_materialization_ab_dev*4166fe8`目录各约1.96 GiB，大小接近，但尚未做全文件内容比对。不能按名称和大小相近就删除其中一份。

另一个4.18 GiB目录`d1_structured_jacobian_multiseed_20260724_formal_9d1f54f`在首轮自动扫描中未检出外部引用。人工扩大检查后，在[评估JSON](../../../research_modules/d6_evaluation_metrics/outputs/d1_structured_jacobian_multiseed_20260725_formal_9d1f54f_d6/d1_structured_numerical_jacobian_multiseed_evaluation.json)及[精简评估JSON](../../../research_modules/d6_evaluation_metrics/outputs/d1_structured_jacobian_multiseed_20260725_formal_9d1f54f_d6/d1_structured_numerical_jacobian_multiseed_compact.json)中发现了它的来源路径和文件依赖，应保留。机器清单中的零引用是有限扫描结果，采用本节人工复核结论。

`learning_generation_v1_oosmfix`虽然没有完成全量运行，仍被模块README、实验报告及差距记录用作故障证据，也应保留。

V3、V4、V5、S180等历史独立实验仍被对照报告或后续复算引用；此前六个同级目录也没有获得独立备份。不能因版本较老或不再采用某条算法路线而整目录删除。

## 六、建议执行顺序

1. 先确认本次96个可重建缓存是否清理，预计释放约75 MiB已分配磁盘块。
2. 再确认六个已解压且内容一致的ZIP是否保留原包，合计434.45 MiB。
3. 四个仍有资料链接的下载包单独处理，不能删后留下失效链接。
4. 旧实验先做独立备份、文件比对和依赖核查，再逐目录决定去留。

当前能够明确列出的低风险空间较小，主要占用仍是有证据用途的实验数据。若需要释放数十GiB，应采用独立存储归档，不能靠批量删除旧日期目录完成。

## 七、检查方法与限制

本轮读取了15,096个文档、代码或选定元数据文件，329个较大的文本候选因超过2 MiB未展开。实验输出中的引用扫描主要覆盖Markdown，以及文件名含manifest、summary、config、checkpoint、report、plan、settings的元数据；评估JSON的人工补查见第五节。没有穷尽动态拼接路径、二进制引用、仓库外文档和外部存储。

压缩包检查不解压写入原目录，只读取包内字节并与磁盘文件的SHA-256比较。十个完整匹配的ZIP共核对1,398个普通文件。未发生读取错误或校验计算异常。

大实验目录大小取自此前的文件盘点，而非同一时刻的文件系统快照。缓存也可能在后续运行中重新生成或变化，实际删除前应重新核验。

本轮工具及既有审计工具共23项测试通过。仅生成以下材料：

- [机器可读审计](CLEANUP_AUDIT.json)：缓存判断、压缩包内文件对应关系、有限范围引用检查及异常。
- [候选清单](CLEANUP_CANDIDATES.csv)：按路径列出分类和大小，包含待复核项，不是自动删除清单。
- [只读审计工具](../tools/audit_cleanup_candidates.py)与[测试](../tools/test_audit_cleanup_candidates.py)。

`20260925_cleanup_review_v1`保留首轮工具结果；v2补正pytest字节码命名识别及嵌套ZIP比较，以本报告及v2清单为当前依据。两轮审计文件合计约2 MiB，没有复制实验载荷。本次没有创建任何独立备份，也没有执行删除。
