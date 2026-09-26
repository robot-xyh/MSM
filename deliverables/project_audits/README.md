# 项目审计与资料登记

## 当前入口

2026年9月26日的接续入口为[当前断点与后续工作计划](20260926/当前断点与后续工作计划_CN.md)，配套[当日文件级快照](20260926/WORKSPACE_EVIDENCE_SNAPSHOT.json)和[工作线状态对照](20260926/工作线状态对照_CN.md)。计划与快照保留第一阶段执行前的状态；状态对照表分别登记历史版本、诊断结果和资料待办，不据此改变模块结论。

第一阶段按已确认范围整理审计工具、登记材料和状态文档，提交及远端核验完成后另存完成记录。备份、删除和新增实验均不在本阶段执行。

2026年9月25日已完成本地文件盘点和报告版本登记，独立备份尚未执行。原报告、实验输出和六个同级目录均未移动或覆盖。

后续的[可清理数据审计](20260925_cleanup_review_v2/可清理数据审计_CN.md)区分了可重建缓存、重复压缩包和旧实验复查候选。本轮仍未执行删除。

| 材料 | 用途 |
| --- | --- |
| [数据保留与归档登记](20260925_preservation_v1/数据保留与归档登记_CN.md) | 文件数量、校验范围、同级目录处置和后续安排 |
| [报告版本对照与使用规则](20260925_preservation_v1/报告版本对照与使用规则_CN.md) | Word与Markdown的关系、主要证据入口、生成器覆盖风险 |
| [文件盘点摘要](20260925_preservation_v1/PRESERVATION_SUMMARY.json) | 本次扫描范围、校验统计、异常及存储情况 |
| [按目录分组的文件清单](20260925_preservation_v1/PRESERVATION_GROUPS.csv) | 查询各目录文件数、逻辑大小和校验数量 |
| [逐文件清单](20260925_preservation_v1/FILES.jsonl.gz) | 路径、大小、修改时间及部分文件的SHA-256 |
| [文档版本登记](20260925_preservation_v1/DOCUMENT_VERSION_REGISTER.json) | 26份Word及19份同名Markdown的校验值、结构与差异 |

## 历史审计

[当前工作进展与证据审计](20260925/当前工作进展与证据审计_CN.md)和[原始快照](20260925/WORKSPACE_EVIDENCE_SNAPSHOT.json)记录的是本轮分组提交前的状态，对应提交`c0a76f6`。其中“尚未提交”等表述保留为历史记录，不代表当前状态。

后续八次提交已将约定范围的中文材料、配图、工具和代码纳入版本管理。当前登记基于`c10fb8bf827e2752cf72b03a21a46176598d1d08`；这只是盘点时的仓库版本，不是所有历史实验的执行版本。实验输出仍需独立备份。

## 更新方式

每次盘点使用新目录，不覆盖历史记录，也不将输出写入实验目录。以下命令只读取原文件并在新目录生成登记材料，不运行仿真或加载模型：

```bash
python3 deliverables/project_audits/tools/prepare_preservation_register.py \
  --root /home/linux/Documents/MSM \
  --prior-snapshot deliverables/project_audits/20260925/WORKSPACE_EVIDENCE_SNAPSHOT.json \
  --output-dir deliverables/project_audits/20260925_preservation_v2

python3 -m unittest discover \
  -s deliverables/project_audits/tools -p 'test_*.py' -v
```

输出目录已存在时工具会停止。登记材料本身也应随后续备份一并保存；清单不包含原始数据载荷。
