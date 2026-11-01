#!/usr/bin/env bash
# 把本地技能目录同步到本仓库并推送
# 用法：./sync.sh ["提交说明"]
set -euo pipefail

SRC="${SKILL_SRC:-$HOME/.workbuddy/skills/koubo-ad-video}"
DST="$(cd "$(dirname "$0")" && pwd)"
MSG="${1:-同步本地技能更新}"

[ -d "$SRC" ] || { echo "找不到源目录：$SRC"; exit 1; }
[ -d "$DST/.git" ] || { echo "目标不是 git 仓库：$DST"; exit 1; }

rsync -a --delete \
  --exclude='.git/' --exclude='.gitignore' --exclude='README.md' --exclude='sync.sh' \
  --exclude='.cache/' --exclude='__pycache__/' --exclude='*.pyc' --exclude='*.bak_*' \
  --exclude='*.bak_pre_*' --exclude='_bak_*/' \
  --exclude='assets/fonts/' --exclude='assets/bgm/' --exclude='assets/sfx/' \
  --exclude='assets/sfx_*/' --exclude='assets/textfx/' --exclude='assets/cover/' \
  --exclude='assets/voice/' --exclude='assets/burst/' --exclude='assets/caption_fx/' \
  --exclude='assets/config.json' --exclude='assets/_motion_mode_last.json' \
  --exclude='assets/_bgm_last.json' --exclude='assets/_bgm_looped.*' \
  "$SRC/" "$DST/"

cd "$DST"

if git diff --quiet && git diff --cached --quiet && [ -z "$(git ls-files -o --exclude-standard)" ]; then
  echo "没有改动，无需提交"
  exit 0
fi

git add -A
git commit -q -m "$MSG"
git push -q origin main
echo "已推送：$(git log --oneline -1)"
