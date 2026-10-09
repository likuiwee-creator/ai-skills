#!/bin/sh
# ai-skills 一键安装/更新
# 用法: sh sync.sh          安装或更新全部
#       sh sync.sh code-selfcheck photo-to-scan   只同步指定几个
set -e

REPO_DIR=$(cd "$(dirname "$0")" && pwd)

# macOS/Linux 用 ~/.workbuddy；Windows Git Bash 也兼容
SKILLS_DIR="${SKILLS_DIR:-$HOME/.workbuddy/skills}"
mkdir -p "$SKILLS_DIR"

# 未指定参数则同步全部子目录
if [ $# -gt 0 ]; then
  LIST="$*"
else
  LIST=$(ls -1 "$REPO_DIR" | grep -vE '^(README\.md|SKILL-WRITING-GUIDE\.md|LICENSE|sync\.sh|\.git|\.gitignore)$')
fi

echo "同步目标: $SKILLS_DIR"
COUNT=0
for name in $LIST; do
  [ -d "$REPO_DIR/$name" ] || continue
  rm -rf "$SKILLS_DIR/$name"
  cp -r "$REPO_DIR/$name" "$SKILLS_DIR/"
  echo "  ✓ $name"
  COUNT=$((COUNT + 1))
done

echo "完成，共同步 $COUNT 个 skill。"
echo "提示：code-selfcheck 装完后可在项目里执行 node $SKILLS_DIR/code-selfcheck/scripts/selfcheck.cjs --install 装 pre-commit 钩子。"
