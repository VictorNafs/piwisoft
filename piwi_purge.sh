#!/usr/bin/env bash
set -euo pipefail

# Trouver PiwiHome via path_resolver (WSL)
PIWI_HOME="$(python3 - <<'PY'
import os, json, sys
try:
    import path_resolver as PR
    print(PR.find_piwi_home())
except Exception:
    # fallback Desktop/Piwi
    print(os.path.join(os.path.expanduser("~"), "Desktop", "Piwi"))
PY
)"

INTERNAL_DIR="$PIWI_HOME/_internal"
REQBASE="$INTERNAL_DIR"   # req_* vivent ici
SCRIPTS_DIR="$INTERNAL_DIR" # actions archivées également ici
CACHE_DIR="$PIWI_HOME/cache"  # si tu utilises ce cache ; sinon laisse vide

# Paramètres
KEEP_DAYS="${PIWI_KEEP_REQUESTS_DAYS:-7}"
MAX_BYTES="${PIWI_MAX_REQUESTS_BYTES:-2147483648}"  # 2 Go

# (1) Purge des req_* par ancienneté
if [ -d "$REQBASE" ]; then
  find "$REQBASE" -maxdepth 1 -type d -name "req_*" -mtime +"$KEEP_DAYS" -print -exec rm -rf {} \; 2>/dev/null || true
fi

# (2) Plafond d'espace total des req_* (on ne touche PAS aux fichiers à la racine de PiwiHome)
if [ -d "$REQBASE" ]; then
  current_size=$(du -sb "$REQBASE" 2>/dev/null | awk '{print $1}')
  if [ -n "${current_size:-}" ] && [ "$current_size" -gt "$MAX_BYTES" ]; then
    while true; do
      current_size=$(du -sb "$REQBASE" 2>/dev/null | awk '{print $1}')
      [ -z "$current_size" ] && break
      [ "$current_size" -le "$MAX_BYTES" ] && break
      oldest="$(find "$REQBASE" -maxdepth 1 -type d -name 'req_*' -printf '%T@ %p\n' | sort -n | head -n1 | cut -d' ' -f2-)"
      [ -n "$oldest" ] && rm -rf "$oldest" || break
    done
  fi
fi

# (3) Nettoyage ancien des artefacts/archives et cache
if [ -d "$SCRIPTS_DIR" ]; then
  find "$SCRIPTS_DIR" -type f -name 'action_*.py' -mtime +30 -delete 2>/dev/null || true
  find "$SCRIPTS_DIR" -type f -name '*.log' -mtime +30 -delete 2>/dev/null || true
fi

if [ -d "$CACHE_DIR" ]; then
  find "$CACHE_DIR" -type f -mtime +30 -delete 2>/dev/null || true
fi

# (4) Info
human() { numfmt --to=iec "$1" 2>/dev/null || echo "$1"; }
sz="0"
[ -d "$REQBASE" ] && sz="$(du -sb "$REQBASE" 2>/dev/null | awk '{print $1}')"
echo "🧹 Purge OK (<= $(human "$MAX_BYTES") visé) — espace actuel reqs: $(human "${sz:-0}") — base: $REQBASE"
