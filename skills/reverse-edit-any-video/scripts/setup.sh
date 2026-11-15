#!/usr/bin/env bash
# Reverse Edit Any Video - dependency installer. Idempotent: re-running only fills what's missing.
#
#   setup.sh [--project DIR] [--global] [--check] [--no-remotion] [--with-whisper]
#
# Installs / verifies:
#   ffmpeg + ffprobe (with drawtext, lut3d, xfade, zscale)   brew ffmpeg-full | apt/dnf/pacman ffmpeg
#   python3 >= 3.9, node >= 20, yt-dlp
#   video-analyzer skill   -> <skills dir>/video-analyzer   (github.com/bsisduck/video-analyzer-skill, GPL-3.0)
#                             + macOS bash 3.2 fix for its empty-array bug
#   Remotion agent skills  -> <skills dir>/remotion-*       (npx skills add remotion-dev/skills)
#   Remotion npm packages + Chrome Headless Shell, cached in ${REAV_CACHE:-~/.cache/reav}/remotion
#   openai-whisper (only with --with-whisper; needed for speech-led references)
#
# <skills dir> = <project>/.claude/skills (default, project = current dir) or ~/.claude/skills (--global)

set -uo pipefail

PROJECT="$PWD"
GLOBAL=0
CHECK=0
REMOTION=1
WHISPER=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --project) PROJECT="$2"; shift 2 ;;
    --global) GLOBAL=1; shift ;;
    --check) CHECK=1; shift ;;
    --no-remotion) REMOTION=0; shift ;;
    --with-whisper) WHISPER=1; shift ;;
    -h|--help) sed -n '2,17p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ $GLOBAL -eq 1 ]]; then SKILLS_DIR="$HOME/.claude/skills"; else SKILLS_DIR="$PROJECT/.claude/skills"; fi
CACHE="${REAV_CACHE:-$HOME/.cache/reav}"
OS="$(uname -s)"
ok=()
warn=()
fail=()

say() { printf '\033[1m==>\033[0m %s\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }

pkg_install() { # pkg_install <brew name> <apt name>
  [[ $CHECK -eq 1 ]] && return 1
  if [[ "$OS" == "Darwin" ]]; then
    have brew || { echo "Homebrew missing: /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"" >&2; return 1; }
    brew install "$1"
  elif have apt-get; then
    local SUDO=""; [[ $EUID -ne 0 ]] && have sudo && SUDO="sudo"
    $SUDO apt-get update -qq && $SUDO apt-get install -y "$2"
  elif have dnf; then
    local SUDO=""; [[ $EUID -ne 0 ]] && have sudo && SUDO="sudo"
    $SUDO dnf install -y "$2"
  elif have pacman; then
    local SUDO=""; [[ $EUID -ne 0 ]] && have sudo && SUDO="sudo"
    $SUDO pacman -S --noconfirm "$2"
  else
    echo "no supported package manager - install $2 manually" >&2; return 1
  fi
}

# ---------------------------------------------------------------- ffmpeg
ff_bin() {
  for d in "${REAV_FFMPEG_DIR:-}" /opt/homebrew/opt/ffmpeg-full/bin /usr/local/opt/ffmpeg-full/bin; do
    [[ -n "$d" && -x "$d/ffmpeg" ]] && { echo "$d"; return; }
  done
  have ffmpeg && dirname "$(command -v ffmpeg)"
}
ff_ok() {
  local d; d="$(ff_bin)"; [[ -z "$d" ]] && return 1
  local f; f="$("$d/ffmpeg" -hide_banner -filters 2>/dev/null)"
  for need in drawtext lut3d xfade zscale signalstats; do
    grep -q " $need " <<<"$f" || { echo "missing filter: $need" >&2; return 1; }
  done
  [[ -x "$d/ffprobe" ]]
}
say "ffmpeg"
if ! ff_ok; then
  if [[ "$OS" == "Darwin" ]]; then pkg_install ffmpeg-full ffmpeg; else pkg_install ffmpeg ffmpeg; fi
fi
if ff_ok; then
  d="$(ff_bin)"
  ok+=("ffmpeg $("$d/ffmpeg" -version | head -1 | awk '{print $3}') ($d)")
  path_filters="$(ffmpeg -hide_banner -filters 2>/dev/null || true)"   # no pipe: pipefail + grep -q = SIGPIPE
  if ! grep -q " drawtext " <<<"$path_filters"; then
    warn+=("the ffmpeg on PATH lacks drawtext; reav scripts use $d automatically - for other tools (video-analyzer): export PATH=\"$d:\$PATH\"")
  fi
else
  fail+=("ffmpeg with drawtext/lut3d/xfade/zscale (macOS: brew install ffmpeg-full; Linux: distro ffmpeg)")
fi

# ---------------------------------------------------------------- python
say "python3"
if have python3 && python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)'; then
  ok+=("python3 $(python3 -c 'import platform; print(platform.python_version())')")
else
  pkg_install python3 python3 || true
  have python3 && ok+=("python3") || fail+=("python3 >= 3.9")
fi

# ---------------------------------------------------------------- yt-dlp
say "yt-dlp (downloads reference reels / shorts)"
if ! have yt-dlp; then
  pkg_install yt-dlp yt-dlp || { [[ $CHECK -eq 0 ]] && python3 -m pip install --user -U yt-dlp; } || true
fi
have yt-dlp && ok+=("yt-dlp $(yt-dlp --version 2>/dev/null)") || warn+=("yt-dlp missing - pass reference videos as files")

# ---------------------------------------------------------------- node
say "node"
node_ok() { have node && node -e 'process.exit(parseInt(process.versions.node) >= 20 ? 0 : 1)' 2>/dev/null; }
if ! node_ok; then
  if [[ "$OS" == "Darwin" ]]; then pkg_install node nodejs || true
  else warn+=("node >= 20 needed for Remotion: https://nodejs.org or nvm install 22"); fi
fi
node_ok && ok+=("node $(node -v)") || warn+=("node >= 20 missing - Remotion route unavailable (ffmpeg route still works)")

# ---------------------------------------------------------------- video-analyzer skill
say "video-analyzer skill"
VA=""
for d in "$SKILLS_DIR/video-analyzer" "$PROJECT/.claude/skills/video-analyzer" "$HOME/.claude/skills/video-analyzer"; do
  [[ -f "$d/SKILL.md" ]] && { VA="$d"; break; }
done
if [[ -z "$VA" && $CHECK -eq 0 ]]; then
  if have git; then
    tmp="$(mktemp -d)"
    if git clone -q --depth 1 https://github.com/bsisduck/video-analyzer-skill.git "$tmp/va"; then
      mkdir -p "$SKILLS_DIR/video-analyzer"
      (cd "$tmp/va" && tar --exclude .git -cf - .) | (cd "$SKILLS_DIR/video-analyzer" && tar -xf -)
      chmod +x "$SKILLS_DIR/video-analyzer/scripts/"*.sh 2>/dev/null || true
      VA="$SKILLS_DIR/video-analyzer"
    fi
    rm -rf "$tmp"
  fi
fi
if [[ -n "$VA" ]]; then
  # Two upstream bugs in scripts/extract-frames.sh:
  #  1. macOS bash 3.2: "${EMPTY[@]}" + set -u = "unbound variable" when no time range is given
  #  2. ffmpeg inside `while read` without -nostdin eats the next line -> wrong key-frame times
  patched=""
  EF="$VA/scripts/extract-frames.sh"
  if [[ $CHECK -eq 0 && -f "$EF" ]]; then
    if perl -0ne 'exit(/(?<!\+)"\$\{TIME_ARGS\[\@\]\}"/ ? 0 : 1)' "$EF"; then
      perl -pi -e 's/(?<!\+)"\$\{TIME_ARGS\[\@\]\}"/\${TIME_ARGS[@]+"\${TIME_ARGS[@]}"}/g' "$EF"
      patched+=" bash-3.2-arrays"
    fi
    if grep -q 'ffmpeg -i "\$INPUT"' "$EF"; then
      perl -pi -e 's/ffmpeg -i "\$INPUT"/ffmpeg -nostdin -i "\$INPUT"/g' "$EF"
      patched+=" ffmpeg-nostdin"
    fi
  fi
  ok+=("video-analyzer ($VA)${patched:+ - patched:$patched}")
else
  fail+=("video-analyzer skill (git clone https://github.com/bsisduck/video-analyzer-skill $SKILLS_DIR/video-analyzer)")
fi

# ---------------------------------------------------------------- Remotion
if [[ $REMOTION -eq 1 ]]; then
  say "Remotion agent skills"
  RS=""
  for d in "$SKILLS_DIR" "$PROJECT/.claude/skills" "$HOME/.claude/skills"; do
    [[ -f "$d/remotion-best-practices/SKILL.md" ]] && { RS="$d"; break; }
  done
  if [[ -z "$RS" && $CHECK -eq 0 ]] && node_ok; then
    if [[ $GLOBAL -eq 1 ]]; then
      npx -y skills add remotion-dev/skills --skill '*' -a claude-code -g -y </dev/null || true
    else
      (cd "$PROJECT" && npx -y skills add remotion-dev/skills --skill '*' -a claude-code -y </dev/null) || true
    fi
    for d in "$SKILLS_DIR" "$HOME/.claude/skills"; do
      [[ -f "$d/remotion-best-practices/SKILL.md" ]] && { RS="$d"; break; }
    done
  fi
  [[ -n "$RS" ]] && ok+=("Remotion skills ($RS/remotion-*)") || warn+=("Remotion skills not installed (npx skills add remotion-dev/skills)")

  say "Remotion packages + headless Chrome (one-time, cached)"
  RC="$CACHE/remotion"
  if [[ -d "$RC/node_modules/remotion" ]]; then
    ok+=("Remotion $(node -p "require('$RC/node_modules/remotion/package.json').version" 2>/dev/null) cached at $RC")
  elif [[ $CHECK -eq 0 ]] && node_ok; then
    mkdir -p "$RC"
    cp "$SKILL_DIR/templates/remotion/package.json" "$RC/package.json"
    if (cd "$RC" && npm install --no-audit --no-fund --loglevel=error); then
      (cd "$RC" && npx remotion browser ensure >/dev/null 2>&1) || warn+=("Remotion: 'npx remotion browser ensure' failed - it retries on first render")
      ok+=("Remotion packages cached at $RC")
    else
      warn+=("Remotion npm install failed (network?) - ffmpeg route still works")
    fi
  else
    warn+=("Remotion packages not cached")
  fi
fi

# ---------------------------------------------------------------- whisper (optional)
if [[ $WHISPER -eq 1 ]]; then
  say "whisper"
  if ! have whisper && [[ $CHECK -eq 0 ]]; then
    if have pipx; then pipx install openai-whisper || true
    else python3 -m pip install --user -U openai-whisper || true; fi
  fi
  have whisper && ok+=("whisper") || warn+=("whisper missing (pip install openai-whisper) - speech references need a transcript")
fi

echo
echo "Reverse Edit Any Video - setup summary"
for x in "${ok[@]+"${ok[@]}"}"; do printf '  \033[32mOK\033[0m    %s\n' "$x"; done
for x in "${warn[@]+"${warn[@]}"}"; do printf '  \033[33mWARN\033[0m  %s\n' "$x"; done
for x in "${fail[@]+"${fail[@]}"}"; do printf '  \033[31mFAIL\033[0m  %s\n' "$x"; done
[[ ${#fail[@]} -eq 0 ]]
