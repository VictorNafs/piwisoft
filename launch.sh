#!/bin/bash
# Piwi launcher — crée un dossier de requête et délègue à noyau.py
set -euo pipefail

# --- Usage ---
if [ $# -lt 1 ]; then
  echo "Usage: $0 <instruction utilisateur...> [destination_optionnelle]"
  echo "Exemples :"
  echo "  $0 \"copie la page Wikipédia d'Elon Musk dans elon.txt sur le Bureau\""
  echo "  $0 \"télécharge ce PDF\" desktop"
  echo "  $0 \"génère un rapport\" \"C:\\Users\\Moi\\Documents\\PiwiOut\""
  exit 1
fi

# 1) On prend TOUTES les args sauf la dernière comme instruction,
#    et on considère la DERNIÈRE comme "destination" si on a 2+ args.
if [ $# -ge 2 ]; then
  DEST_HINT="${@: -1}"
  INSTRUCTION="${*:1:($#-1)}"
else
  DEST_HINT=""
  INSTRUCTION="$*"
fi

# --- HOME de secours (certains contextes WSL non interactifs) ---
if [ -z "${HOME:-}" ]; then
  HOME="$(getent passwd "$(whoami)" | cut -d: -f6 || true)"
  [ -n "$HOME" ] || HOME="/tmp"
  export HOME
fi

# --- Dossier de requête ---
TIMESTAMP="$(date +%F_%H-%M-%S)"
REQDIR="${HOME}/piwi_requests/req_${TIMESTAMP}"
mkdir -p "$REQDIR"

# --- Dossier d’installation = là où se trouve ce script ---
INSTALL_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- Variables d'info (facultatif) ---
echo "⏳ Instruction : $INSTRUCTION"
echo "📁 Dossier de requête : $REQDIR"
echo "📦 Dossier d'installation : $INSTALL_PATH"
[ -n "$DEST_HINT" ] && echo "🎯 Destination demandée : $DEST_HINT"
echo

# --- Lancement du noyau livré avec l’appli ---
#    (PIWI_OPENAI_KEY doit être présent dans l'env)
python3 "$INSTALL_PATH/noyau.py" "$INSTRUCTION" "$REQDIR" "$DEST_HINT"

# --- Post-run : infos utiles ---
echo
echo "✅ Terminé. Artefacts générés (si présents) :"
[ -f "$REQDIR/exec.sh" ] && echo "  • Script Bash : $REQDIR/exec.sh"
[ -f "$REQDIR/log.txt" ]  && echo "  • Log IA      : $REQDIR/log.txt"
[ -f "$REQDIR/meta.txt" ] && echo "  • Métadonnées : $REQDIR/meta.txt"
[ -f "$REQDIR/action.py" ] && echo "  • Action      : $REQDIR/action.py (déplacé ensuite si noyau l'a détecté)"

echo
echo "ℹ️ Tous les dossiers de requêtes sont conservés dans: $HOME/piwi_requests"
echo "   Utilisez piwi_purge.sh pour nettoyer (purge non automatique)."
