#!/usr/bin/env bash
# Install the "Reverse Edit Any Video" Claude skill + everything it needs.
#
#   From a clone:   ./install.sh [--global] [--project DIR] [--no-deps] [setup options]
#   One-liner:      curl -fsSL https://raw.githubusercontent.com/vidwip/reav/main/install.sh | bash
#
# Project install (default): <project>/.claude/skills/reverse-edit-any-video  (project = current dir)
# --global:                  ~/.claude/skills/reverse-edit-any-video
# Then runs scripts/setup.sh: ffmpeg, python3, node, yt-dlp, video-analyzer skill, Remotion skills,
# Remotion packages + headless Chrome. Extra options (--with-whisper, --no-remotion) pass through.

set -euo pipefail

REPO_URL="https://github.com/vidwip/reav.git"
SKILL="reverse-edit-any-video"
PROJECT="$PWD"
GLOBAL=0
DEPS=1
PASS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --global) GLOBAL=1; PASS+=("--global"); shift ;;
    --project) PROJECT="$(cd "$2" && pwd)"; shift 2 ;;
    --no-deps) DEPS=0; shift ;;
    -h|--help) sed -n '2,11p' "$0"; exit 0 ;;
    *) PASS+=("$1"); shift ;;
  esac
done

# where is the skill source? (a clone, or fetch one)
SRC=""
if [[ -n "${BASH_SOURCE[0]:-}" && -f "$(dirname "${BASH_SOURCE[0]}")/skills/$SKILL/SKILL.md" ]]; then
  SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/skills/$SKILL"
else
  command -v git >/dev/null || { echo "git is required" >&2; exit 1; }
  TMP="$(mktemp -d)"
  trap 'rm -rf "$TMP"' EXIT
  git clone -q --depth 1 "$REPO_URL" "$TMP/reav"
  SRC="$TMP/reav/skills/$SKILL"
fi

if [[ $GLOBAL -eq 1 ]]; then DEST="$HOME/.claude/skills/$SKILL"; else DEST="$PROJECT/.claude/skills/$SKILL"; fi
if [[ "$(cd "$SRC" && pwd)" != "$(mkdir -p "$DEST" && cd "$DEST" && pwd)" ]]; then
  rm -rf "$DEST"
  mkdir -p "$DEST"
  (cd "$SRC" && tar --exclude node_modules --exclude __pycache__ -cf - .) | (cd "$DEST" && tar -xf -)
fi
chmod +x "$DEST"/scripts/*.sh "$DEST"/scripts/*.py 2>/dev/null || true
echo "Installed skill -> $DEST"

if [[ $DEPS -eq 1 ]]; then
  bash "$DEST/scripts/setup.sh" --project "$PROJECT" "${PASS[@]+"${PASS[@]}"}"
fi

cat <<EOF

Done. In Claude Code (started in $PROJECT), ask for example:
  "Reverse edit https://www.instagram.com/reel/XXXX/ using my clips in ./footage"
or run:  /$SKILL <reference url or file> <footage folder>
EOF
