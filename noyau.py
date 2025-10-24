#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Piwi – Noyau complet (génération IA + exécution dans WSL)

- L'IA (OpenAI) génère un script bash.
- Le script s'exécute DANS la distro WSL (Ubuntu).
- Installations confinées à la distro (apt/pip, etc.).
- I/O : données "utilisateur" -> PIWI_HOME (ou DEST_DIR si précisé)
        artefacts techniques -> REQ_INTERNAL.
- sudo : si lancé en root (wsl -u root) inutile ; sinon possible via PIWI_SUDO_PASSWORD.
- Post-install : si REQ_INTERNAL/shortcuts.json existe, création de .lnk via create_shortcut.sh.

Args :
  argv[1] = instruction (ou "shell: <cmd>")
  argv[2] = REQ_INTERNAL (ex: /mnt/c/Users/<u>/piwi_requests/req_YYYY-MM-DD_HH-MM-SS)
  argv[3] = dest_hint (optionnel)
Env :
  PIWI_OPENAI_KEY, PIWI_MODEL (def="gpt-4o-mini"), PIWI_SUDO_PASSWORD
"""

import os
import sys
import re
import shlex
import json
import time
import subprocess
from pathlib import Path
from datetime import datetime

# --- OpenAI client ---
try:
    from openai import OpenAI
except Exception:
    OpenAI = None

# --- Sanity: WSL? ---
IS_WSL = "microsoft" in open("/proc/version","r",encoding="utf-8",errors="ignore").read().lower() if os.path.exists("/proc/version") else False

def euid_is_root() -> bool:
    try:
        return os.geteuid() == 0
    except AttributeError:
        return False

# --- Base dirs ---
BASE_DIR = Path(__file__).resolve().parent

# --- path_resolver helpers ---
sys.path.insert(0, str(BASE_DIR))
try:
    import path_resolver as PR
except Exception:
    PR = None

def find_piwi_home() -> Path:
    # [AJUSTÉ] Privilégier ~/Piwi si path_resolver ne fournit rien
    if PR:
        try:
            return Path(PR.find_piwi_home())
        except Exception:
            pass
    d = Path.home() / "Piwi"
    (d / ".piwi").mkdir(parents=True, exist_ok=True)
    return d

def resolve_hint(h: str) -> Path:
    # [AJUSTÉ] Si pas d'indice -> on force le répertoire Piwi utilisateur (évite mkdir "")
    if not h:
        return find_piwi_home()
    if PR:
        try:
            return Path(PR.resolve_hint(h))
        except Exception:
            pass
    return Path(h)

# --- IO setup ---
if len(sys.argv) < 2 or not str(sys.argv[1]).strip():
    print("[ERROR] Usage: python3 noyau.py '<instruction>' '<REQ_INTERNAL?>' '<dest_hint?>'")
    sys.exit(1)

INSTRUCTION = str(sys.argv[1]).strip()
REQ_INTERNAL = Path(sys.argv[2]).resolve() if len(sys.argv) >= 3 and sys.argv[2].strip() else (find_piwi_home() / "_internal" / f"req_{time.strftime('%F_%H-%M-%S')}")
DEST_HINT = str(sys.argv[3]).strip() if len(sys.argv) >= 4 else ""
PIWI_HOME = find_piwi_home()
DEST_DIR = resolve_hint(DEST_HINT)

REQ_INTERNAL.mkdir(parents=True, exist_ok=True)
try:
    DEST_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass

# --- OpenAI init ---
API_KEY = os.getenv("PIWI_OPENAI_KEY","").strip()
MODEL = os.getenv("PIWI_MODEL","gpt-4o-mini").strip()
if not API_KEY:
    print("[ERROR] PIWI_OPENAI_KEY manquant.")
    sys.exit(1)
if OpenAI is None:
    print("[ERROR] Bibliothèque 'openai' absente. Installez-la : pip install --upgrade openai")
    sys.exit(1)

client = OpenAI(api_key=API_KEY)

# --- Utils ---
def clean_code(txt: str) -> str:
    if not txt:
        return ""
    return re.sub(r"```[\w-]*\n(.*?)```", r"\1", txt, flags=re.DOTALL).strip()

def write_text(p: Path, content: str, mode=0o644):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    try:
        os.chmod(str(p), mode)
    except Exception:
        pass

def logln(msg: str):
    print(msg, flush=True)
    logf = REQ_INTERNAL / "log.txt"
    try:
        prev = ""
        if logf.exists():
            prev = logf.read_text(encoding="utf-8")
        write_text(logf, prev + msg + "\n", 0o644)
    except Exception:
        pass

def write_exec(script_text: str) -> Path:
    p = REQ_INTERNAL / "exec.sh"
    text = "#!/bin/bash\nset -euo pipefail\n" + script_text.rstrip() + "\n"
    write_text(p, text, 0o755)
    return p

def save_meta(script_text: str):
    meta = {
        "instruction": INSTRUCTION,
        "req_internal": str(REQ_INTERNAL),
        "piwi_home": str(PIWI_HOME),
        "dest_dir": str(DEST_DIR),
        "base_dir": str(BASE_DIR),
        "as_root": euid_is_root(),
        "ts": datetime.utcnow().isoformat()+"Z",
        "model": MODEL
    }
    write_text(REQ_INTERNAL / "meta.json", json.dumps(meta, ensure_ascii=False, indent=2))
    write_text(REQ_INTERNAL / "script.generated.sh", script_text)

def detect_action_script():
    cand = REQ_INTERNAL / "action.py"
    if cand.exists():
        dst = PIWI_HOME / "_internal" / f"action_{REQ_INTERNAL.name}.py"
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            cand.replace(dst)
            logln(f"💾 action.py archivé: {dst}")
        except Exception as e:
            logln(f"[WARN] move action.py: {e}")

def update_cache():
    try:
        subprocess.run(f'"{sys.executable}" -m pip freeze > "{REQ_INTERNAL / "requirements.txt"}"', shell=True, check=False)
    except Exception as e:
        logln(f"[WARN] update_cache: {e}")

# --- Shortcuts (.lnk) ---
def _find_create_shortcut_sh() -> Path | None:
    for c in (PIWI_HOME / "bin" / "create_shortcut.sh", BASE_DIR / "create_shortcut.sh"):
        if c.exists():
            return c
    return None

def create_shortcut(name: str, target: str, workdir: str = "", icon: str = "") -> bool:
    sh = _find_create_shortcut_sh()
    if not sh:
        logln("[WARN] create_shortcut.sh introuvable.")
        return False
    cmd = f'bash -lc {shlex.quote(f"{sh} {shlex.quote(name)} {shlex.quote(target)} {shlex.quote(workdir)} {shlex.quote(icon)}")}'
    try:
        cp = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=str(REQ_INTERNAL))
        if cp.stdout: logln(cp.stdout.strip())
        if cp.stderr: logln("[stderr] " + cp.stderr.strip())
        return cp.returncode == 0
    except Exception as e:
        logln(f"[WARN] create_shortcut exception: {e}")
        return False

def handle_post_install():
    man = REQ_INTERNAL / "shortcuts.json"
    if not man.exists():
        return
    try:
        raw = man.read_text(encoding="utf-8")
        # Sécurise les backslashes windows mal échappés générés par l'IA
        raw = raw.replace("\\", "\\\\")
        data = json.loads(raw)
        if not isinstance(data, list):
            logln("[WARN] shortcuts.json: attendu = liste d'objets, ignoré.")
            return
        created = 0
        for ent in data:
            if not isinstance(ent, dict):
                continue
            name   = str(ent.get("name", "")).strip()
            target = str(ent.get("target", "")).strip()
            workdir = str(ent.get("workdir", "")).strip()
            icon    = str(ent.get("icon", "")).strip()
            # Gardes : name et target exigés, workdir/icon peuvent être vides
            if not name or not target:
                logln("[WARN] entrée raccourci ignorée (name/target manquants).")
                continue
            if create_shortcut(name, target, workdir, icon):
                created += 1
        logln(f"[INFO] Post-install: {created} raccourci(s) créé(s).")
    except Exception as e:
        logln(f"[WARN] handle_post_install: {e}")

# --- Prompt IA ---
IO_RULES = f"""
Variables d'environnement :
- PIWI_HOME="{PIWI_HOME.as_posix()}"
- REQ_INTERNAL="{REQ_INTERNAL.as_posix()}"
- DEST_DIR="{DEST_DIR.as_posix()}"

RÈGLES :
1) Données utilisateur -> "$DEST_DIR" si non vide, sinon racine de "$PIWI_HOME".
2) Artefacts techniques -> "$REQ_INTERNAL" UNIQUEMENT.
3) Pas d'install Windows : utilise apt/pip dans la distro.
4) Raccourcis Windows : écris "$REQ_INTERNAL/shortcuts.json" (liste d'objets
   {{ "name":"...", "target":"C:\\\\Path\\\\app.exe", "workdir":"...", "icon":"..." }}).
5) set -euo pipefail & n'utilise sudo que si indispensable.
"""

def generate_script(prompt: str) -> str:
    try:
        resp = client.chat.completions.create(
            model=MODEL or "gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Tu es une IA système Ubuntu. Retourne UNIQUEMENT du code bash, sans explications."},
                {"role": "user", "content": prompt}
            ],
            temperature=0,
            timeout=30,  # <— timeout dur
        )
        content = resp.choices[0].message.content
    except Exception as e:
        logln(f"[ERROR] Appel OpenAI: {e}")
        return "echo 'OpenAI indisponible pour le moment' >&2; exit 2"
    return clean_code(content)

def build_prompt() -> str:
    return f"""Instruction utilisateur :
{INSTRUCTION}

CONSIGNE :
- Écris un script BASH pour réaliser la tâche, en respectant strictement les règles I/O ci-dessous.
- Tu n'écris QUE du BASH (aucun commentaire/texte hors code).

{IO_RULES}
"""

# --- Exécution script (sudo si nécessaire) ---
def run_script_with_env(script_path: Path) -> tuple[int, str, str]:
    env = dict(os.environ)
    env["PIWI_HOME"]    = PIWI_HOME.as_posix()
    env["REQ_INTERNAL"] = REQ_INTERNAL.as_posix()
    env["DEST_DIR"]     = DEST_DIR.as_posix()

    cp = subprocess.run(["bash", str(script_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=str(REQ_INTERNAL), env=env)
    out, err, rc = cp.stdout or "", cp.stderr or "", cp.returncode
    if rc == 0:
        if out: logln(out)
        if err: logln("[stderr] " + err)
        return rc, out, err

    low = (out + "\n" + err).lower()
    need_sudo = ("sudo" in low or "permission denied" in low or "operation not permitted" in low)
    if need_sudo and not euid_is_root():
        pw = os.getenv("PIWI_SUDO_PASSWORD","").strip()
        if not pw:
            logln("🔒 Sudo requis mais aucun mot de passe fourni (PIWI_SUDO_PASSWORD).")
            return rc, out, err
        wrapped = f'echo {shlex.quote(pw)} | sudo -S -p "" env PIWI_HOME={shlex.quote(env["PIWI_HOME"])} REQ_INTERNAL={shlex.quote(env["REQ_INTERNAL"])} DEST_DIR={shlex.quote(env["DEST_DIR"])} bash {shlex.quote(str(script_path))}'
        cp2 = subprocess.run(wrapped, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=str(REQ_INTERNAL), env=env)
        out2, err2, rc2 = cp2.stdout or "", cp2.stderr or "", cp2.returncode
        if out2: logln(out2)
        if err2: logln("[stderr] " + err2)
        return rc2, out2, err2

    if out: logln(out)
    if err: logln("[stderr] " + err)
    return rc, out, err

# --- Shell passthrough ---
def maybe_shell_passthrough() -> bool:
    low = INSTRUCTION.strip().lower()
    if low.startswith("shell:"):
        cmd = INSTRUCTION.split(":",1)[1].strip()
        logln(f"> shell passthrough: {cmd}")
        cp = subprocess.run(["bash","-lc",cmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=str(REQ_INTERNAL))
        if cp.stdout: logln(cp.stdout)
        if cp.stderr: logln("[stderr] " + cp.stderr)
        return True
    return False

# --- Main ---
def main():
    if not IS_WSL:
        print("[ERROR] Ce noyau doit tourner dans WSL.")
        sys.exit(1)

    logln("=== Piwi noyau (IA + WSL) ===")
    logln(f"Date: {datetime.now().isoformat(sep=' ', timespec='seconds')}")
    logln(f"WSL: yes | EUID: {'root' if euid_is_root() else 'user'}")
    logln(f"PIWI_HOME: {PIWI_HOME}")
    logln(f"REQ_INTERNAL: {REQ_INTERNAL}")
    if DEST_DIR and DEST_DIR != PIWI_HOME:
        logln(f"DEST_DIR: {DEST_DIR}")
    logln(f"Model: {MODEL}")
    write_text(REQ_INTERNAL / "info.json", json.dumps({
        "instruction": INSTRUCTION,
        "created_at": datetime.utcnow().isoformat()+"Z",
        "env": {"as_root": euid_is_root(), "has_sudo_password": bool(os.getenv("PIWI_SUDO_PASSWORD",""))}
    }, ensure_ascii=False, indent=2))

    if maybe_shell_passthrough():
        handle_post_install()
        sys.exit(0)

    prompt = build_prompt()
    bash_code = generate_script(prompt)
    script_path = write_exec(bash_code)
    save_meta(bash_code)

    rc, out, err = run_script_with_env(script_path)
    detect_action_script()
    update_cache()
    handle_post_install()

    if rc != 0:
        corr = f"""SCRIPT BASH :
{bash_code}

ERREUR :
{err}

Corrige le script ci-dessus. Rappels OBLIGATOIRES :
- Artefacts techniques UNIQUEMENT dans "$REQ_INTERNAL".
- Données utilisateur dans "$DEST_DIR" si défini, sinon à la racine de "$PIWI_HOME".
- Pour les raccourcis Windows, écris un manifest JSON "$REQ_INTERNAL/shortcuts.json" (liste d'objets).
- Retourne UNIQUEMENT du BASH.
"""
        fixed = generate_script(corr)
        script_path2 = write_exec(fixed)
        save_meta(fixed)
        logln("[INFO] Exécution du script corrigé...")
        rc2, out2, err2 = run_script_with_env(script_path2)
        detect_action_script()
        update_cache()
        handle_post_install()
        sys.exit(rc2)

    sys.exit(0)

if __name__ == "__main__":
    main()
