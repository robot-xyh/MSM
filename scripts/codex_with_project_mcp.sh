#!/usr/bin/env bash
set -euo pipefail

# Launch Codex with MSM project-scoped MCP overrides only for this process.
# Default: enable only the local MSM filesystem MCP, because npx-based
# literature MCP servers can fail when offline or rate-limited.
#
# To include arXiv and Semantic Scholar for a literature-audit session:
#   MSM_WITH_LITERATURE_MCP=1 scripts/codex_with_project_mcp.sh

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

CONFIG_ARGS=(
  -c 'mcp_servers.msm-repo.command="npx"'
  -c "mcp_servers.msm-repo.args=[\"-y\",\"@modelcontextprotocol/server-filesystem\",\"${ROOT_DIR}\"]"
)

if [[ "${MSM_WITH_LITERATURE_MCP:-0}" == "1" ]]; then
  CONFIG_ARGS+=(
    -c 'mcp_servers.arxiv.command="npx"'
    -c 'mcp_servers.arxiv.args=["-y","@cyanheads/arxiv-mcp-server"]'
    -c 'mcp_servers.semanticscholar.command="npx"'
    -c 'mcp_servers.semanticscholar.args=["-y","@xbghc/semanticscholar-mcp"]'
  )
fi

cd "${ROOT_DIR}"
exec codex "${CONFIG_ARGS[@]}" "$@"
