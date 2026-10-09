#!/bin/sh
# code-selfcheck · 一键安装
# 用法：sh install.sh [项目目录]
# 作用：把本目录的 scripts 拷进项目的 ci/，并给项目装上 pre-commit 钩子。
# 适用：任何有 Node 18+ 的机器，AI 工具不限（WorkBuddy/Codex/Cursor/Claude Code 均可）。

set -e
SELF_DIR=$(cd "$(dirname "$0")" && pwd)
PROJ=${1:-$(pwd)}
NODE_BIN=$(command -v node || true)

if [ -z "$NODE_BIN" ]; then
  echo "✗ 未找到 node，请先安装 Node.js 18+"
  exit 1
fi

echo "→ 项目目录: $PROJ"
cd "$PROJ"

# 1) 拷贝执行器到项目（供 CI 与本地共用同一份逻辑）
mkdir -p ci/selfcheck
cp "$SELF_DIR/scripts/selfcheck.cjs" "$SELF_DIR/scripts/ocr_gate.cjs" ci/selfcheck/
echo "✓ 已拷贝执行器到 ci/selfcheck/"

# 2) 安装 pre-commit 钩子
"$NODE_BIN" ci/selfcheck/selfcheck.cjs --install

echo ""
echo "完成。验证："
echo "  node ci/selfcheck/selfcheck.cjs --list      # 看可跑哪些阶段"
echo "  git commit                                   # 会自动触发自检"
