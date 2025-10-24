#!/usr/bin/env bash
# setup_piwi.sh — Initialisation de la distro WSL pour Piwi
# - Installe paquets de base (python3, pip, etc.)
# - Installe le SDK OpenAI (>=1.40)
# - Crée PIWI_HOME (Bureau\Piwi) et sa structure
# - Copie create_shortcut.sh dans PIWI_HOME/bin
# - Écrit un marqueur .piwi/.piwi_home.json et un README

set -euo pipefail

# ---------- helpers ----------
log()  { printf "%s\n" "$*"; }
warn() { printf "WARN: %s\n" "$*" >&2; }
err()  { printf "ERROR: %s\n" "$*" >&2; }

is_wsl() {
  [[ -f /proc/version ]] && grep -qiE 'microsoft|wsl' /proc/version
}

# Convertit un chemin Windows -> WSL /mnt/<drive>/… (si besoin)
win_to_wsl() {
  local p="${1:-}"
  if [[ "$p" =~ ^[A-Za-z]:\\ ]]; then
    local d="${p:0:1}"; d="${d,,}"
    local rest="${p:2}"
    rest="${rest//\\//}"
    printf "/mnt/%s/%s" "$d" "$rest"
  else
    printf "%s" "$p"
  fi
}

# Détecte un Bureau Windows plausible pour placer Piwi
guess_piwi_home() {
  # 1) si USERPROFILE disponible
  if [[ -n "${USERPROFILE:-}" && "${USERPROFILE}" =~ ^[A-Za-z]:\\ ]]; then
    local desk="${USERPROFILE}\\Desktop\\Piwi"
    win_to_wsl "$desk"
    return 0
  fi
  # 2) sinon tente /mnt/c/Users/<user>/Desktop
  for d in /mnt/c/Users/*/Desktop; do
    if [[ -d "$d" ]]; then
      printf "%s/Piwi" "$d"
      return 0
    fi
  done
  # 3) fallback home linux
  printf "%s" "$HOME/Desktop/Piwi"
}

ensure_packages() {
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y --no-install-recommends \
    ca-certificates curl gnupg \
    python3 python3-pip python3-venv python3-apt
}

ensure_python_packages() {
  python3 -m pip install --upgrade pip >/dev/null 2>&1 || true
  python3 -m pip install --upgrade "openai>=1.40.0" >/dev/null 2>&1 || true
}

# ---------- main ----------
log "==> Initialisation Piwi (WSL)…"

# 1) Paquets de base
ensure_packages
ensure_python_packages

# 2) Résolution PIWI_HOME (côté Windows si possible)
PIWI_HOME="${PIWI_HOME:-}"
if [[ -z "$PIWI_HOME" ]]; then
  PIWI_HOME="$(guess_piwi_home)"
fi

log "PIWI_HOME ciblé : $PIWI_HOME"
mkdir -p "$PIWI_HOME"/{Applications,bin,_internal} || true

# 3) Copie des utilitaires
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# create_shortcut.sh -> PIWI_HOME/bin
if [[ -f "$SCRIPT_DIR/create_shortcut.sh" ]]; then
  cp -f "$SCRIPT_DIR/create_shortcut.sh" "$PIWI_HOME/bin/create_shortcut.sh"
  chmod +x "$PIWI_HOME/bin/create_shortcut.sh"
fi

# (optionnel) expose aussi launch.sh s'il existe
if [[ -f "$SCRIPT_DIR/launch.sh" ]]; then
  cp -f "$SCRIPT_DIR/launch.sh" "$PIWI_HOME/bin/launch.sh"
  chmod +x "$PIWI_HOME/bin/launch.sh"
fi

# 4) Marqueurs & README
MARKER_DIR="$PIWI_HOME/.piwi"
MARKER_JSON="$MARKER_DIR/.piwi_home.json"
mkdir -p "$MARKER_DIR"

log "==> Écriture du marqueur PIWI_HOME…"
cat > "$MARKER_JSON" <<EOF
{
  "piwi_home": "$(printf "%s" "$PIWI_HOME" | sed 's/\\/\\\\/g')",
  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "created_by": "setup_piwi.sh",
  "version": "1.0"
}
EOF

README_TXT="$PIWI_HOME/README_PIWI.txt"
if [[ ! -f "$README_TXT" ]]; then
  cat > "$README_TXT" <<'EOF'
Piwi – Dossier de travail (PIWI_HOME)
-------------------------------------

Ce dossier contient vos fichiers "utilisateur" créés par Piwi (rapports, exports, etc.).
Les logiciels installés pendant les requêtes sont *dans la distro Linux (WSL)*, pas sur Windows.

Conseil :
- Conservez ici vos documents produits par Piwi (dans la racine ou des sous-dossiers).
- Les fichiers techniques temporaires sont stockés dans PIWI_HOME/_internal.

Astuce :
- Si une action nécessite des droits admin Linux, relancez en mode "Exécuter en root (WSL)"
  OU fournissez un mot de passe sudo quand l’interface le demande.
EOF
fi

# 5) Info finale
log
log "✓ Installation de base Piwi terminée."
log "   PIWI_HOME  : $PIWI_HOME"
log "   create_shortcut.sh installé dans : $PIWI_HOME/bin"
log "   SDK OpenAI : $(python3 - <<'PY'
import importlib.util
print('present' if importlib.util.find_spec('openai') else 'absent')
PY
)"
log
log "Vous pouvez maintenant lancer l’interface Piwi depuis Windows."
