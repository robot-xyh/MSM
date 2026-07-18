# 体系方案与阶段进展报告

`C_UAS_PROJECT_LEADERSHIP_REPORT_CN.md` 是正文源文件，`build_report.py` 负责生成插图、Word 和 PDF。发布产物统一使用 `C_UAS_PROJECT_LEADERSHIP_REPORT_CN` 文件名。

## 生成

从项目根目录执行：

```bash
python3 deliverables/leadership_report/build_report.py
```

生成器优先刷新项目内仍可访问的实验图；原始实验输出未纳入版本管理时，使用本目录已归档并在正文中标明证据边界的图。生成前应先更新 `TEST_RESULTS_YYYYMMDD.txt` 和 `EVIDENCE_MANIFEST.md`。

## 发布检查

1. D1-D7 模块所有者核查各自算法、接口、状态和局限性。
2. 检查 Markdown 图片引用、Word/PDF 页数和文档结构。
3. 搜索个人信息、绝对本地路径、旧测试计数和未标记的设备性能结论。
4. AirSim 和质点模型结果必须明确标为仿真证据。
