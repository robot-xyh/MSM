# D4 A2 development 候选校准报告

## 结论

本次产物是 development/shadow 候选，只允许隔离和影子评估。它不具备 assist、正式 authority 或系统收益结论。

- 候选模型：`d4-region-a2-bc-calibrated-development-v2`
- 权重 SHA256：`cf393eaa2e7777e63645ef244f8e9bf733123fdc768f2610a91954c5f6c4632f`
- 正门样本：420/420
- 置信度 min/mean/max：0.707421/0.972089/1.000000
- 推理时延 P95/max：0.969215/1.294533 ms，固定门限 50 ms
- OOD 硬门拒绝：420/420

## 数据

- 正式语料：900 episode，1798 frame
- 补充课程：100 episode，300 frame
- 训练、验证、校准 seed 为 60/20/20；1000-1019 使用数为 0。

## 动作覆盖

- 非零配额动作：40
- 跨区转移：20
- hold：20
- request-replan：40

## 边界

- failure fixture 项：7
- 低置信、分布外、超时、非有限、旧 epoch/lease、ACK 不完整和安全投影失败均保持规则回退。
- 正门样本只证明候选合同可以进入后续隔离试验，不证明物理收益。
- 正式 1000-1019 留出集、运行时 ACK、物理结果和因果收益仍未评估。
