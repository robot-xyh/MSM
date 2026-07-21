# D5 跨视角困难样本补充课程

## 结论

独立补充课程生成 `4500` 个图帧、`66726` 个匿名局部航迹节点和 `245032` 条默认几何门候选边。标签完整率为 `100.00%`。

正边 `57292` 条，困难负边 `187740` 条，未标注边 `0` 条。producer 未修改正式语料，未训练模型，未开放 G1 或在线辅助权限。

## 数据来源

- supplemental manifest SHA-256：`77d117ba7a0d6cdbddf4ce9fcccd63455e2b28a916c6526d97e17857bfb9ad90`
- dataset manifest SHA-256：`ec2708477332416be83e12f1458cc2dff72a2c5196d1fdb58fbb074a85660ee4`
- evaluator lineage SHA-256：`587a05927a00f795ab5b1828f0443f41297b79ae1d115dcc1193f35164b77c49`
- 正式源 manifest SHA-256：`d9a84007995fe94918483bd5cb5ddc38f60f61d819bea27137dfa2619bf75426`
- 源 Git 提交：`087a568c71a0c1004653d0e4175b156856b2e34b`
- 源工作区 dirty：`true`

## 覆盖

- numeric seed：`100` 个，canonical 分桶 `{'train': 60, 'validation': 20, 'test': 20}`。
- 场景规模 cell：`45` 个。
- 遮挡进入/退出、时间偏差、外参扰动、漏检和虚警均有生成记录。
- 与正式源重复图、重复边和重复 episode：`0`。

## 安全边界

在线图只含匿名局部航迹、时间戳、像素量测、协方差和几何特征。真值位于独立 evaluator lineage 与 label 文件。候选边仍经过默认时间、视场、极线、射线、重投影和协方差门，D5 不创建或改写 `global_track_id`。
