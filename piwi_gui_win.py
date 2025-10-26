# -*- coding: utf-8 -*-
r"""
Piwi – Interface principale (WSL + élévation à la demande)

- Vérifie WSL + distro "PiwiUbuntu".
- Auto-réparation : tente d'importer la distro depuis {app}\\wsl\\*.rootfs.tar.gz
  et lance setup_piwi.sh en root WSL si la distro manque.
- Si non prête après ça : lance l’installateur et s’arrête.
- UI minimaliste : clé OpenAI, requête, mot de passe sudo (optionnel), mode root (bandeau visible).
- Si la tâche échoue par manque de droits, propose automatiquement de relancer
  avec sudo (en demandant le mot de passe) ou en root WSL.

Dépendances Windows :
- PyQt5
- requests
"""

import os
import sys
import shlex
import subprocess
import requests
import datetime
from pathlib import Path
from types import SimpleNamespace

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QTextEdit, QPushButton, QMessageBox, QCheckBox,
    QInputDialog, QFrame, QDialog, QDialogButtonBox
)
from PyQt5.QtGui import QIcon

DISTRO_NAME = os.environ.get("PIWI_DISTRO_NAME", "PiwiUbuntu")
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


# ---------- Helpers système ----------

def app_dir() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent

def _decode_bytes(b) -> str:
    if not b:
        return ""
    if isinstance(b, str):
        return b
    if b.startswith(b"\xff\xfe") or b"\x00" in b[:4]:
        try:
            return b.decode("utf-16le", errors="replace")
        except Exception:
            pass
    try:
        return b.decode("utf-8")
    except Exception:
        return b.decode("cp1252", errors="replace")

def run(cmd, **kw) -> SimpleNamespace:
    if os.name == "nt":
        kw.setdefault("creationflags", CREATE_NO_WINDOW)
        kw.setdefault("shell", False)
    kw.setdefault("stdout", subprocess.PIPE)
    kw.setdefault("stderr", subprocess.PIPE)
    kw["text"] = False
    p = subprocess.run(cmd, **kw)
    return SimpleNamespace(
        returncode=p.returncode,
        stdout=_decode_bytes(p.stdout),
        stderr=_decode_bytes(p.stderr),
    )

def _normalize_lines(s: str):
    s = (s or "").replace("\x00", "")
    out = []
    for ln in s.splitlines():
        ln = ln.replace("\ufeff", "").lstrip("*").strip()
        if ln:
            out.append(ln)
    return out

def wsl_ok() -> bool:
    if os.name != "nt":
        return False
    try:
        c = run(["wsl.exe", "--status"])
        return c.returncode == 0
    except Exception:
        return False

def distro_list_quiet():
    q = run(["wsl.exe", "-l", "-q"])
    return _normalize_lines(q.stdout) if q.returncode == 0 else []

def distro_exists(name: str = DISTRO_NAME) -> bool:
    try:
        lines = distro_list_quiet()
        if any(ln.lower() == name.lower() for ln in lines):
            return True
    except Exception:
        pass
    try:
        out = run(["wsl.exe", "-l", "-v"])
        if out.returncode != 0:
            return False
        lines = _normalize_lines(out.stdout)
        return any(name.lower() in ln.lower() for ln in lines)
    except Exception:
        return False

def wsl_bash(cmd: str, *, user: str | None = None) -> list[str]:
    base = ["wsl", "-d", DISTRO_NAME]
    if user:
        base += ["-u", user]
    base += ["--", "bash", "-lc", cmd]
    return base

def distro_healthy(name: str = DISTRO_NAME) -> bool:
    try:
        r = run(["wsl.exe", "-d", name, "--", "bash", "-lc", "echo OK"])
        return r.returncode == 0 and "OK" in (r.stdout or "")
    except Exception:
        return False

def need_install() -> bool:
    return (not wsl_ok()) or (not distro_exists(DISTRO_NAME)) or (not distro_healthy(DISTRO_NAME))

def _show_error_window(msg: str):
    app = QApplication.instance() or QApplication(sys.argv)
    w = QMainWindow()
    w.setWindowTitle("Piwi")
    ico = app_dir() / "piwi_icon.ico"
    if ico.exists():
        w.setWindowIcon(QIcon(str(ico)))
    c = QWidget()
    from PyQt5.QtWidgets import QVBoxLayout
    v = QVBoxLayout(c)
    lab = QLabel(msg)
    lab.setWordWrap(True)
    v.addWidget(lab)
    w.setCentralWidget(c)
    w.resize(520, 200)
    w.show()
    app.exec_()

def launch_installer_and_exit():
    exe = app_dir() / "piwi_installer_gui.exe"
    if not exe.exists():
        _show_error_window(
            "L’installateur est introuvable.\n"
            f"Chemin attendu : {exe}\n"
            "Réinstallez Piwi."
        )
        sys.exit(1)
    try:
        if os.name == "nt":
            subprocess.Popen([str(exe)], creationflags=CREATE_NO_WINDOW)
        else:
            subprocess.Popen([str(exe)])
    except Exception as e:
        _show_error_window(f"Impossible de démarrer l’installateur :\n{e}")
        sys.exit(1)
    sys.exit(0)

def to_wsl_path(win_path: str) -> str:
    if not win_path or len(win_path) < 3:
        return win_path
    if win_path[1:3] != ":\\":
        return win_path
    drive = win_path[0].lower()
    return f"/mnt/{drive}{win_path[2:].replace('\\', '/')}"

# ---------- Auto-réparation au démarrage ----------

def try_auto_repair():
    r"""
    Si la distro n'existe pas, tente un import depuis {app}\\wsl\\*.rootfs.tar.gz,
    puis exécute setup_piwi.sh en root dans WSL. Silencieux et idempotent.
    """
    # Déjà présente ? on sort
    try:
        q = subprocess.run(["wsl.exe", "-l", "-q"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        have = any(DISTRO_NAME.lower() == ln.strip().lower() for ln in (q.stdout or "").splitlines())
    except Exception:
        have = False
    if have:
        return

    # Cherche un rootfs embarqué
    base_dir_win = os.path.dirname(os.path.abspath(
        sys.executable if getattr(sys, 'frozen', False) else __file__
    ))
    rootfs_dir = os.path.join(base_dir_win, "wsl")
    if not os.path.isdir(rootfs_dir):
        return

    rootfs = None
    for fn in os.listdir(rootfs_dir):
        if fn.endswith(".rootfs.tar.gz"):
            rootfs = os.path.join(rootfs_dir, fn)
            break
    if not rootfs:
        return

    # Import WSL2
    install_dir = os.path.join(rootfs_dir, "PiwiUbuntuFS")
    os.makedirs(install_dir, exist_ok=True)
    subprocess.run(
        ["wsl.exe", "--import", DISTRO_NAME, install_dir, rootfs, "--version", "2"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )

    # Setup initial dans WSL (root)
    app_wsl = to_wsl_path(base_dir_win)
    bash = f'cd {shlex.quote(app_wsl)} && chmod +x setup_piwi.sh || true && ./setup_piwi.sh || true'
    subprocess.run(
        ["wsl.exe", "-d", DISTRO_NAME, "-u", "root", "--", "bash", "-lc", bash],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )

# ---------- UI ----------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Piwi – Assistant IA (Windows + WSL)")
        ico = app_dir() / "piwi_icon.ico"
        if ico.exists():
            self.setWindowIcon(QIcon(str(ico)))
        self.resize(900, 720)

        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Bandeau root
        self.root_banner = QFrame()
        self.root_banner.setStyleSheet("background:#ffebee;border:1px solid #ffcdd2;border-radius:8px;padding:10px;")
        hb = QHBoxLayout(self.root_banner)
        lab = QLabel("⚠️  Mode administrateur (root WSL) ACTIVÉ — utilisez-le seulement si nécessaire.")
        f = lab.font(); f.setBold(True); lab.setFont(f)
        hb.addWidget(lab); self.root_banner.setVisible(False)
        layout.addWidget(self.root_banner)

        # Clé API
        api_row = QHBoxLayout()
        api_row.addWidget(QLabel("Clé OpenAI :"))
        self.api_input = QLineEdit()
        self.api_input.setPlaceholderText("sk-...")
        self.api_input.setEchoMode(QLineEdit.Password)
        api_row.addWidget(self.api_input)
        layout.addLayout(api_row)

        # Sudo / Root
        sudo_row1 = QHBoxLayout()
        self.as_root_chk = QCheckBox("Exécuter en root (WSL)")
        self.as_root_chk.toggled.connect(self._toggle_root)
        sudo_row1.addWidget(self.as_root_chk); sudo_row1.addStretch(1)
        layout.addLayout(sudo_row1)

        sudo_row2 = QHBoxLayout()
        self.sudo_label = QLabel("Mot de passe sudo (WSL) :")
        self.sudo_input = QLineEdit()
        self.sudo_input.setEchoMode(QLineEdit.Password)
        self.sudo_input.setPlaceholderText("laisser vide si inutile")
        sudo_row2.addWidget(self.sudo_label); sudo_row2.addWidget(self.sudo_input)
        layout.addLayout(sudo_row2)

        # Instruction
        layout.addWidget(QLabel("Votre requête (langage naturel) :"))
        self.req_input = QTextEdit()
        self.req_input.setPlaceholderText("Ex : Installe nmap et scanne mon réseau local")
        self.req_input.setAcceptRichText(False)
        layout.addWidget(self.req_input, 1)

        # Exécution
        btn_row = QHBoxLayout()
        self.run_btn = QPushButton("Lancer dans WSL")
        self.run_btn.clicked.connect(self.lancer_piwi)
        btn_row.addStretch(1); btn_row.addWidget(self.run_btn)
        layout.addLayout(btn_row)

        # Logs
        layout.addWidget(QLabel("Sortie / Logs :"))
        self.result_box = QTextEdit(); self.result_box.setReadOnly(True)
        layout.addWidget(self.result_box, 2)

    def _toggle_root(self, checked: bool):
        self.root_banner.setVisible(checked)
        self.sudo_input.setEnabled(not checked)
        self.sudo_label.setEnabled(not checked)

    def _ask_sudo_password_now(self) -> str | None:
        pw, ok = QInputDialog.getText(self, "Sudo requis",
                                      "Entrez le mot de passe sudo (utilisateur 'piwi') :",
                                      QLineEdit.Password)
        return pw if ok and pw else None

    def _ask_reauth_dialog(self, err_text: str) -> str:
        """
        Propose de relancer avec sudo (demande mdp) ou en root. Retourne "sudo", "root" ou "".
        """
        dlg = QDialog(self); dlg.setWindowTitle("Droits requis")
        v = QVBoxLayout(dlg)
        m = QLabel(
            "La tâche semble nécessiter des privilèges administrateur.\n\n"
            "Voulez-vous la relancer avec sudo (mot de passe) ou en root WSL ?"
        ); m.setWordWrap(True); v.addWidget(m)
        if err_text:
            snippet = "\n".join((err_text or "").splitlines()[-6:])
            txt = QTextEdit(); txt.setReadOnly(True); txt.setPlainText(snippet)
            txt.setMinimumHeight(120); v.addWidget(txt)
        btns = QDialogButtonBox()
        b_sudo = btns.addButton("Relancer avec sudo", QDialogButtonBox.AcceptRole)
        b_root = btns.addButton("Relancer en root", QDialogButtonBox.ActionRole)
        b_cancel = btns.addButton("Annuler", QDialogButtonBox.RejectRole)
        v.addWidget(btns)
        def acc(): dlg.done(1)
        def act(): dlg.done(2)
        def rej(): dlg.done(0)
        b_sudo.clicked.connect(acc); b_root.clicked.connect(act); b_cancel.clicked.connect(rej)
        res = dlg.exec_()
        return "sudo" if res == 1 else ("root" if res == 2 else "")

    def _build_cmd(self, instruction: str, api_key: str, reqdir_wsl: str, sudo_pw: str | None, as_root: bool):
        base_dir_win = os.path.dirname(os.path.abspath(
            sys.executable if getattr(sys, 'frozen', False) else __file__
        ))
        base_dir_wsl = to_wsl_path(base_dir_win)

        env_exports = f'export PIWI_OPENAI_KEY={shlex.quote(api_key)}; '
        if (not as_root) and sudo_pw:
            env_exports += f'export PIWI_SUDO_PASSWORD={shlex.quote(sudo_pw)}; '

        bash_fragment = (
            f'{env_exports}'
            f' REQDIR="{reqdir_wsl}"; '
            f' mkdir -p "$REQDIR"; '
            f' cd {shlex.quote(base_dir_wsl)} || exit 2; '
            f' python3 noyau.py {shlex.quote(instruction)} "$REQDIR"'
        )
        if as_root:
            cmd_list = wsl_bash(bash_fragment, user="root")
        else:
            cmd_list = wsl_bash(bash_fragment)
        return cmd_list, bash_fragment

    def _run_once(self, cmd_list, display_fragment):
        self.result_box.append("> " + " ".join(shlex.quote(x) for x in cmd_list[:-1]) + " " +
                               shlex.quote(display_fragment))
        r = subprocess.run(cmd_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        out = r.stdout or ""
        if r.stderr:
            out += ("\n[stderr]\n" + r.stderr)
        self.result_box.append(out)
        return r.returncode, out

    def lancer_piwi(self):
        instruction = self.req_input.toPlainText().strip()
        api_key = self.api_input.text().strip()
        sudo_pw = self.sudo_input.text().strip()
        as_root = self.as_root_chk.isChecked()

        if not instruction or not api_key:
            QMessageBox.warning(self, "Champs manquants", "Merci de remplir la clé API et la requête.")
            return

        # Petit test non-bloquant
        try:
            requests.get("https://api.openai.com/v1/models",
                         headers={"Authorization": f"Bearer {api_key}"}, timeout=5)
        except Exception:
            pass

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        reqdir_win = os.path.join(os.path.expanduser("~"), "piwi_requests", f"req_{timestamp}")
        os.makedirs(reqdir_win, exist_ok=True)
        reqdir_wsl = to_wsl_path(reqdir_win)

        cmd_list, frag = self._build_cmd(instruction, api_key, reqdir_wsl,
                                         sudo_pw if sudo_pw else None, as_root)
        masked_key = api_key[:6] + "..." if len(api_key) > 8 else "****"
        display_fragment = frag.replace(api_key, masked_key)
        if sudo_pw:
            display_fragment = display_fragment.replace(sudo_pw, "******")

        rc, out = self._run_once(cmd_list, display_fragment)
        if rc == 0:
            return

        # Si échec permissions et qu’on n’était pas root -> proposer relance
        low = out.lower()
        likely_perm = ("permission denied" in low) or ("operation not permitted" in low) or ("sudo:" in low)
        if (not as_root) and likely_perm:
            choice = self._ask_reauth_dialog(out)
            if choice == "sudo":
                pw = sudo_pw or self._ask_sudo_password_now()
                if not pw:
                    return
                cmd_list2, frag2 = self._build_cmd(instruction, api_key, reqdir_wsl, pw, False)
                disp2 = frag2.replace(api_key, masked_key).replace(pw, "******")
                self._run_once(cmd_list2, disp2)
            elif choice == "root":
                cmd_list3, frag3 = self._build_cmd(instruction, api_key, reqdir_wsl, None, True)
                disp3 = frag3.replace(api_key, masked_key)
                self._run_once(cmd_list3, disp3)


# ---------- main ----------

if __name__ == "__main__":
    # Tente une auto-réparation silencieuse (import + setup) avant tout
    try_auto_repair()

    # Si malgré tout la distro n'est pas prête, on lance l'installateur
    if need_install():
        launch_installer_and_exit()

    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
