# Agent Operations Review

## 现状判断

当前项目已经形成 D1-D7 七个稳定模块角色，但过去主要靠会话内临时 prompt 和 `subagent_reviews` 维持上下文，导致：

- 同一 D 模块在不同轮次被重复新建；
- 旧 agent ID 被写入长期文档，但这些 ID 只对某次会话有意义；
- main agent 需要反复复制长提示词；
- 并发上限为 6 时，D1-D7 全开会触顶。

因此应采用“稳定角色文件 + 短任务分派”的模式。

## Skill 配置状态

已创建以下个人 Codex skill，路径均在 `/home/linux/.codex/skills/`。这些 skill 不替代 D1-D7 稳定角色，而是在对应上下文中动态加载工作流，减少 main agent 重复复制长提示词。

| Skill | 触发场景 | 内容 |
| --- | --- | --- |
| AirSim runtime skill | 提到 AirSim、Blocks、SimpleFlight、ComputerVision、settings | 启动/重置/不保存 PNG、常用参数、诊断路径、失败模式 |
| C-UAS module orchestration skill | 提到 D1-D7、subagent、GAP、全流程 | 读取 `agents/`，限制写入范围，关闭完成 agent，按 D6 汇总 |
| Experiment reporting skill | 提到报告、结果分析、批量 seed、图表 | 读取 D6 输出、生成中文 Markdown、引用 metrics/CSV |
| Literature/source audit skill | 提到 arXiv、GitHub、WOS、Google Scholar、开源共识 | 搜索策略、引用格式、只把实现建议写入方案，不直接改算法主线 |

动态 skill 的价值在于减少 main prompt 重复，不建议把 D1-D7 每个都做成 skill；D1-D7 更适合做 project subagent。当前已通过 `quick_validate.py` 校验：

- `airsim-runtime`
- `cuas-module-orchestration`
- `experiment-reporting`
- `literature-source-audit`

## MCP 配置状态

当前不把 MSM MCP 写入全局 `/home/linux/.codex/config.toml`，避免其他项目启动这些服务器，也避免 npx/网络问题导致全局启动失败。MSM 使用项目专用启动脚本 `scripts/codex_with_project_mcp.sh`。

| MCP | 是否建议 | 原因 |
| --- | --- | --- |
| Local filesystem MCP: `msm-repo` | 项目脚本默认启用 | 限定到 `/home/linux/Documents/MSM`，便于后续 MCP 客户端结构化读取项目文件 |
| arXiv MCP: `arxiv` | 项目脚本可选启用 | 使用 `@cyanheads/arxiv-mcp-server`，文献审计时通过 `MSM_WITH_LITERATURE_MCP=1` 启动 |
| Semantic Scholar MCP: `semanticscholar` | 项目脚本可选启用 | 使用 `@xbghc/semanticscholar-mcp`，无 API Key 可用但有限速；有 Key 后可加环境变量 |
| GitHub MCP | 已预留但未启用 | 需要 `GITHUB_PERSONAL_ACCESS_TOKEN`，未检测到 token 时不默认启用，避免 MCP 启动失败 |
| Web of Science MCP | 暂不建议默认配置 | 通常需要机构凭证，稳定性和可访问性不如浏览器/人工导出 |
| AirSim runtime MCP | 暂不建议 | 当前通过 Python scripts/CLI 更直接；MCP 封装成本高 |

结论：本地开发仍主要依赖文件系统和 Python/pytest；MCP 用于增强项目读取和文献检索。GitHub MCP 等用户提供 PAT 后再启用。

## Hooks 需求分析

不建议直接写 `.git/hooks`，因为它们不随仓库版本化且容易影响用户本地流程。建议后续如有需要，再引入版本化的 `pre-commit` 配置。

可选 hook/检查：

- Python 语法：`python3 -m py_compile ...`
- 模块测试：D1-D7 各自默认 pytest。
- AirSim runtime 非真实启动测试：`pytest -q research_modules/airsim_runtime/tests/test_blocks_runtime.py`
- 禁止默认保存 PNG：检查命令是否显式传 `--save-images`。
- 生成物隔离：AirSim 输出默认放在 `research_modules/airsim_runtime/outputs/`。

## AGENTS.md 需要写入的指令

需要。当前 `AGENTS.md` 仍像空仓库模板，不符合 MSM 当前结构。应写入：

- 项目真实目录结构；
- main/D1-D7 固定角色；
- subagent 并发和关闭规则；
- AirSim 运行约束；
- 不保存截图默认规则；
- N-v-N 规模规则；
- 推荐测试命令。
