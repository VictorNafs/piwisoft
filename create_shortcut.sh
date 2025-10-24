#!/usr/bin/env bash
# create_shortcut.sh — crée un raccourci Windows (.lnk) depuis WSL
# Usage:
#   create_shortcut.sh "<name>" "<target>" ["<working_dir>"] ["<icon_path>"]

set -euo pipefail

err()  { printf "ERROR: %s\n" "$*" >&2; }
warn() { printf "WARN: %s\n"  "$*" >&2; }
log()  { printf "%s\n" "$*"; }

safe_mkdir() {
  local p="${1:-}"
  if [ -n "$p" ]; then mkdir -p "$p"; fi
}

to_win_path() {
  local p="${1:-}"
  if [ -z "$p" ]; then printf "%s" ""; return 0; fi
  if command -v wslpath >/dev/null 2>&1; then
    local winp
    if winp=$(wslpath -w "$p" 2>/dev/null); then
      printf "%s" "$winp"; return 0
    fi
  fi
  printf "%s" "$p"
}

sanitize_filename() {
  local s="${1:-}"
  s="${s//\\/}" ; s="${s//\//}" ; s="${s//:/}" ; s="${s//\*/}"
  s="${s//\?/}" ; s="${s//\"/}" ; s="${s//</}" ; s="${s//>/}"
  s="${s//|/}"
  s="$(printf "%s" "$s" | sed 's/[[:space:]]\+$//; s/^[[:space:]]\+//')"
  [ -z "$s" ] && s="PiwiShortcut"
  printf "%s" "$s"
}

NAME="${1:-}"
TARGET="${2:-}"
WORKDIR="${3:-}"
ICON="${4:-}"

if [ -z "$NAME" ] || [ -z "$TARGET" ]; then
  err "Usage: $0 \"<name>\" \"<target>\" [\"<working_dir>\"] [\"<icon_path>\"]"
  exit 2
fi

PIWI_HOME="${PIWI_HOME:-}"
if [ -z "$PIWI_HOME" ]; then
  PIWI_HOME="$HOME/Desktop/Piwi"
  warn "PIWI_HOME non défini, fallback: $PIWI_HOME"
fi

APPS_DIR="$PIWI_HOME/Applications"
safe_mkdir "$APPS_DIR"

NAME_SAFE="$(sanitize_filename "$NAME")"
LNK_LINUX="$APPS_DIR/$NAME_SAFE.lnk"

LNK_WIN="$(to_win_path "$LNK_LINUX")"
TARGET_WIN="$(to_win_path "$TARGET")"
WORKDIR_WIN="$(to_win_path "$WORKDIR")"
ICON_WIN="$(to_win_path "$ICON")"

if [ -z "$LNK_WIN" ] || [ -z "$TARGET_WIN" ]; then
  err "Chemins convertis invalides (lnk/target). Abandon."
  exit 3
fi

PS_EXE="/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
if [ ! -x "$PS_EXE" ] && command -v powershell.exe >/dev/null 2>&1; then
  PS_EXE="powershell.exe"
fi

TMPDIR="$(mktemp -d)"
PS1="$TMPDIR/piwi_create_link.ps1"

# Échappe les quotes simples pour PS
psq() { printf "%s" "$1" | sed "s/'/''/g"; }

cat > "$PS1" <<'EOF'
param(
  [Parameter(Mandatory=$true)][string]$LnkPath,
  [Parameter(Mandatory=$true)][string]$Target,
  [Parameter(Mandatory=$false)][string]$WorkDir,
  [Parameter(Mandatory=$false)][string]$IconPath
)
$ErrorActionPreference = "Stop"
$parent = Split-Path -Path $LnkPath -Parent
if ($parent -and -not (Test-Path -LiteralPath $parent)) {
  New-Item -ItemType Directory -Path $parent | Out-Null
}
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut($LnkPath)
$sc.TargetPath = $Target
if ($WorkDir) { $sc.WorkingDirectory = $WorkDir }
if ($IconPath) { $sc.IconLocation = $IconPath }
$sc.Description = 'Piwi'
$sc.Save()
EOF

# Exécute le script PS
"$PS_EXE" -NoProfile -ExecutionPolicy Bypass -File "$(to_win_path "$PS1")" \
  -LnkPath   "$(psq "$LNK_WIN")" \
  -Target    "$(psq "$TARGET_WIN")" \
  -WorkDir   "$(psq "$WORKDIR_WIN")" \
  -IconPath  "$(psq "$ICON_WIN")"

ec=$?
rm -rf "$TMPDIR"

if [ $ec -ne 0 ]; then
  err "Echec création raccourci ($ec)."
  exit $ec
fi

log "OK: raccourci créé -> $LNK_WIN"
exit 0
