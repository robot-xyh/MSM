# Skill and MCP Setup

## 已安装 Skill

| Skill | 路径 | 用途 |
| --- | --- | --- |
| `airsim-runtime` | `/home/linux/.codex/skills/airsim-runtime` | AirSim Blocks、SimpleFlight、ComputerVision、settings、episode 调度 |
| `cuas-module-orchestration` | `/home/linux/.codex/skills/cuas-module-orchestration` | main/D1-D7 分工、GAP 修复、全流程集成 |
| `experiment-reporting` | `/home/linux/.codex/skills/experiment-reporting` | 中文实验报告、D6 指标、图表和结论 |
| `literature-source-audit` | `/home/linux/.codex/skills/literature-source-audit` | 文献、GitHub、开源实现和共识算法审计 |

所有 skill 已通过：

```bash
python3 /home/linux/.codex/skills/.system/skill-creator/scripts/quick_validate.py <skill-path>
```

## MCP 配置状态

MCP 不再写入全局 `/home/linux/.codex/config.toml`。原因是这些 MCP 只服务 MSM 项目，写入全局会导致其他项目也启动，并且 npx/网络/包入口问题会造成启动失败。

当前采用项目专用启动方式：

- 模板：`.codex/project-mcp.toml`
- 启动脚本：`scripts/codex_with_project_mcp.sh`

| MCP | 状态 | 说明 |
| --- | --- | --- |
| `msm-repo` | 项目脚本默认启用 | `@modelcontextprotocol/server-filesystem`，根目录为当前 MSM 仓库 |
| `arxiv` | 项目脚本可选启用 | `MSM_WITH_LITERATURE_MCP=1` 时启用，避免日常启动受 npx/网络影响 |
| `semanticscholar` | 项目脚本可选启用 | `MSM_WITH_LITERATURE_MCP=1` 时启用，API Key 可选但无 Key 限速 |
| `github` | 已预留注释 | 需要 `GITHUB_PERSONAL_ACCESS_TOKEN` 后再启用 |

默认项目启动：

```bash
scripts/codex_with_project_mcp.sh
```

文献审计时启动：

```bash
MSM_WITH_LITERATURE_MCP=1 scripts/codex_with_project_mcp.sh
```

## 使用规则

- D1-D7 仍以 `agents/*.md` 为稳定角色定义，skill 只负责动态加载工作流。
- GitHub MCP 未启用前，需要查 issue、repo、PR 时继续用 web/CLI。
- WOS 不默认配置 MCP；优先使用用户导出的 WOS 结果或浏览器检索。
- AirSim 不做 MCP 封装，继续由 main 通过本项目 Python runtime 脚本调度。
