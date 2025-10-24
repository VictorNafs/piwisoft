# -*- coding: utf-8 -*-
r"""
Piwi – Installateur WSL (GUI, non-bloquant)

Changements clés :
- Exécution des opérations lourdes (import WSL, post-install, config user) dans un QThread.
- UI réactive : barre de progression indéterminée, pas de logs en direct.
- Affichage uniquement d'un message final (succès/échec) + bouton "Afficher les détails" si besoin.
- Au succès, ouverture automatique de piwi_gui_win.exe puis fermeture de l'installateur.
- Empêche la fermeture pendant l'installation.
- Auto-lance l'installation si la distro n'existe pas encore (meilleure UX).
"""

import os
import sys
import glob
import shlex
import time
import subprocess
from pathlib import Path
from typing import Optional
from types import SimpleNamespace

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QMessageBox, QDialog, QDialogButtonBox,
    QProgressBar, QPlainTextEdit
)
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer

APP_DISTRO_NAME = "PiwiUbuntu"
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


# ---------- Helpers OS ----------

def app_dir() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _decode_bytes(b: Optional[bytes]) -> str:
    """Décodage robuste des sorties de wsl.exe (UTF-16LE fréquent)."""
    if not b:
        return ""
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
    """
    Lance un sous-processus, capture en BYTES, puis décode proprement.
    Retourne un objet {returncode, stdout(str), stderr(str)}.
    """
    if os.name == "nt":
        kw.setdefault("creationflags", CREATE_NO_WINDOW)
        kw.setdefault("shell", False)
    kw.setdefault("stdout", subprocess.PIPE)
    kw.setdefault("stderr", subprocess.PIPE)
    kw["text"] = False  # bytes

    p = subprocess.run(cmd, **kw)
    return SimpleNamespace(
        returncode=p.returncode,
        stdout=_decode_bytes(p.stdout),
        stderr=_decode_bytes(p.stderr),
    )


def _normalize_lines(s: str):
    """Nettoie les sorties : supprime NULs/BOM/astérisques éventuels, strip par ligne."""
    s = s.replace("\x00", "")
    lines = []
    for ln in (s or "").splitlines():
        ln = ln.replace("\ufeff", "").lstrip("*").strip()
        if ln:
            lines.append(ln)
    return lines


def wsl_ok() -> bool:
    if os.name != "nt":
        return False
    try:
        c = run(["wsl.exe", "--status"])
        return c.returncode == 0
    except Exception:
        return False


def distro_exists(name: str = APP_DISTRO_NAME) -> bool:
    # 1) liste "quiet" fiable (non localisée)
    try:
        q = run(["wsl.exe", "-l", "-q"])
        if q.returncode == 0:
            lines = _normalize_lines(q.stdout)
            return any(ln.lower() == name.lower() for ln in lines)
    except Exception:
        pass
    # 2) fallback verbose
    try:
        out = run(["wsl.exe", "-l", "-v"])
        if out.returncode != 0:
            return False
        lines = _normalize_lines(out.stdout)
        return any(name.lower() in ln.lower() for ln in lines)
    except Exception:
        return False


def to_wsl_path(win_path: Path) -> str:
    p = str(win_path)
    if not p or len(p) < 3:
        return p
    drive = p[0].lower()
    if p[1:3] != ":\\":
        return p
    return f"/mnt/{drive}/{p[3:].replace('\\', '/')}"


def find_rootfs_tar() -> Optional[Path]:
    # Cherche {app}\wsl\*.tar.gz (priorité), sinon *.tar
    p = app_dir() / "wsl"
    for pattern in ("*.tar.gz", "*.tgz", "*.tar"):
        candidates = sorted(glob.glob(str(p / pattern)))
        if candidates:
            return Path(candidates[0])
    return None


def default_install_dir() -> Path:
    # {USERPROFILE}\Piwi\wsl\PiwiUbuntu   (note: 'wsl' en minuscules)
    return Path(os.path.expanduser("~")) / "Piwi" / "wsl" / APP_DISTRO_NAME


def import_distro(log, install_dir: Path, archive: Path) -> bool:
    install_dir.mkdir(parents=True, exist_ok=True)
    log("• Import : distro=PiwiUbuntu")
    log(f"  - Target : {install_dir}")
    log(f"  - Archive: {archive}")

    # Log avant import
    q1 = run(["wsl.exe", "-l", "-q"])
    if q1.stdout:
        log("  - Avant import, `wsl -l -q` : " + " | ".join(_normalize_lines(q1.stdout)))

    r = run(["wsl.exe", "--import", APP_DISTRO_NAME, str(install_dir), str(archive), "--version", "2"])
    if r.stdout:
        log(r.stdout.strip())
    if r.stderr:
        log("[stderr] " + r.stderr.strip())
    if r.returncode != 0:
        log("❌ Échec de l'import WSL.")
        return False

    # Attendre l’enregistrement côté WSL (jusqu’à ~15 s)
    for _ in range(30):
        time.sleep(0.5)
        if distro_exists(APP_DISTRO_NAME):
            log("✓ Distro importée et détectée.")
            q2 = run(["wsl.exe", "-l", "-q"])
            if q2.stdout:
                log("  - Après import, `wsl -l -q` : " + " | ".join(_normalize_lines(q2.stdout)))
            return True

    log("⚠️ Import déclenché mais non détecté (timeout).")
    return False


def run_setup(log) -> bool:
    """
    Exécute `setup_piwi.sh` depuis le dossier d'app, à l'intérieur de la distro.
    """
    basedir = app_dir()
    basedir_wsl = to_wsl_path(basedir)
    sh_wsl = f"{basedir_wsl}/setup_piwi.sh"
    log(f"== Post-install : exécution de {sh_wsl} ==")
    r = run(["wsl.exe", "-d", APP_DISTRO_NAME, "--", "bash", "-lc", f"bash {shlex.quote(sh_wsl)}"])
    if r.stdout:
        log(r.stdout.strip())
    if r.stderr:
        log("[stderr] " + r.stderr.strip())
    ok = (r.returncode == 0)
    log("✓ Post-install OK." if ok else "❌ Post-install a renvoyé une erreur.")
    return ok


def set_default_user(log, username: str = "piwi") -> bool:
    """
    S'assure que l'utilisateur existe, l'ajoute à 'sudo', puis écrit /etc/wsl.conf.
    """
    cmd = (
        "set -e; "
        f"if ! id -u {username} >/dev/null 2>&1; then "
        f"  sudo adduser --disabled-password --gecos \"\" {username}; "
        "fi; "
        f"getent group sudo >/dev/null 2>&1 && sudo usermod -aG sudo {username} || true; "
        f"sudo sh -c 'printf \"[user]\\ndefault={username}\\n\" > /etc/wsl.conf'"
    )
    r = run(["wsl.exe", "-d", APP_DISTRO_NAME, "--", "bash", "-lc", cmd])
    if r.stdout:
        log(r.stdout.strip())
    if r.stderr:
        log("[stderr] " + r.stderr.strip())
    ok = (r.returncode == 0)
    log("✓ Utilisateur par défaut configuré." if ok else "⚠️ Échec config utilisateur par défaut (non bloquant).")
    return ok


def launch_main_ui():
    """Démarre l'UI principale Piwi puis ferme l'installateur."""
    base = app_dir()
    exe = base / "piwi_gui_win.exe"
    py  = base / "piwi_gui_win.py"
    try:
        if exe.exists():
            subprocess.Popen([str(exe)], cwd=str(base), creationflags=CREATE_NO_WINDOW)
        elif py.exists():
            cmd = ["pythonw.exe", str(py)] if os.name == "nt" else ["python3", str(py)]
            try:
                subprocess.Popen(cmd, cwd=str(base), creationflags=CREATE_NO_WINDOW)
            except FileNotFoundError:
                fallback = ["python.exe", str(py)] if os.name == "nt" else ["python3", str(py)]
                subprocess.Popen(fallback, cwd=str(base), creationflags=CREATE_NO_WINDOW)
    except Exception:
        pass  # ignore silencieusement


# ---------- Worker thread (opérations lourdes) ----------

class InstallWorker(QThread):
    # finished(success: bool, final_message: str, details: str)
    finished = pyqtSignal(bool, str, str)

    def __init__(self):
        super().__init__()
        self._logs = []

    def log(self, line: str):
        # On mémorise les logs mais on ne les affiche pas en live
        self._logs.append(line)

    def run(self):
        try:
            # Pré-check WSL
            if not wsl_ok():
                self.finished.emit(False, "WSL n'est pas disponible. Activez WSL2 puis relancez l'installation.", "")
                return

            # Import si nécessaire
            if not distro_exists(APP_DISTRO_NAME):
                tar = find_rootfs_tar()
                if not tar or not tar.exists():
                    self.finished.emit(False, "Aucun rootfs .tar/.tar.gz trouvé dans le dossier 'wsl'.", "")
                    return
                inst_dir = default_install_dir()
                ok = import_distro(self.log, inst_dir, tar)
                if not ok:
                    self.finished.emit(False, "Échec de l'import de la distribution WSL.", "\n".join(self._logs))
                    return

            # Post-install
            ok2 = run_setup(self.log)
            if not ok2:
                # Non bloquant mais on signale l'avertissement
                self.log("⚠️  Post-install en erreur (continuation).")

            # User par défaut
            set_default_user(self.log, "piwi")

            # Succès
            self.finished.emit(True, "Installation/Configuration terminée.", "\n".join(self._logs))
        except Exception as e:
            self.finished.emit(False, f"Erreur inattendue : {e}", "\n".join(self._logs))


# ---------- UI ----------

class InstallerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Piwi – Installateur WSL")
        ico = app_dir() / "piwi_icon.ico"
        if ico.exists():
            self.setWindowIcon(QIcon(str(ico)))
        self.resize(640, 360)

        c = QWidget(self)
        v = QVBoxLayout(c)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(10)
        self.setCentralWidget(c)

        self.info = QLabel(
            "Cet assistant va installer la distribution Linux PiwiUbuntu dans WSL2,\n"
            "puis exécuter la configuration de base."
        )
        self.info.setWordWrap(True)
        v.addWidget(self.info)

        self.progress = QProgressBar(self)
        self.progress.setRange(0, 0)  # indéterminé
        self.progress.setVisible(False)
        v.addWidget(self.progress)

        self.status_lbl = QLabel("")
        v.addWidget(self.status_lbl)

        # Zone détails cachée par défaut
        self.details = Qplain = QPlainTextEdit(self)
        self.details.setReadOnly(True)
        self.details.setVisible(False)
        v.addWidget(self.details, 1)

        btns = QHBoxLayout()
        self.btn_install = QPushButton("Installer / Réparer")
        self.btn_install.clicked.connect(self.on_install)
        btns.addWidget(self.btn_install)

        self.btn_details = QPushButton("Afficher les détails")
        self.btn_details.setVisible(False)
        self.btn_details.clicked.connect(self.toggle_details)
        btns.addWidget(self.btn_details)

        btns.addStretch(1)

        self.btn_quit = QPushButton("Fermer")
        self.btn_quit.clicked.connect(self.close)
        btns.addWidget(self.btn_quit)
        v.addLayout(btns)

        # Précheck simple (non bloquant)
        if distro_exists():
            self.status_lbl.setText("La distribution PiwiUbuntu est détectée. Vous pouvez réparer/reconfigurer si besoin.")
        else:
            # UX : auto-lancer l'installation si la distro est absente
            QTimer.singleShot(250, self.on_install)

        self.worker: Optional[InstallWorker] = None

    def toggle_details(self):
        vis = not self.details.isVisible()
        self.details.setVisible(vis)
        self.btn_details.setText("Masquer les détails" if vis else "Afficher les détails")

    def on_install(self):
        # UI état
        self.btn_install.setEnabled(False)
        self.btn_quit.setEnabled(False)
        self.progress.setVisible(True)
        self.status_lbl.setText("Installation / configuration en cours…")
        self.details.clear()
        self.btn_details.setVisible(False)

        # Lancer le worker
        self.worker = InstallWorker()
        self.worker.finished.connect(self.on_finished)
        self.worker.start()

    def on_finished(self, success: bool, final_message: str, details: str):
        # UI réactive de nouveau
        self.progress.setVisible(False)
        self.btn_install.setEnabled(True)
        self.btn_quit.setEnabled(True)

        self.status_lbl.setText("")

        if success:
            try:
                QMessageBox.information(self, "Terminé", final_message)
            except Exception:
                pass
            # Montrer le bouton détails uniquement si on a des logs utiles
            if details.strip():
                self.details.setPlainText(details)
                self.btn_details.setVisible(True)
            # Lancer l'UI principale et fermer
            launch_main_ui()
            self.close()
        else:
            QMessageBox.critical(self, "Échec", final_message)
            if details.strip():
                self.details.setPlainText(details)
                self.btn_details.setVisible(True)
            # proposer de réessayer
            self.btn_install.setText("Réessayer")

    def closeEvent(self, event):
        # Empêche de fermer en plein traitement
        if getattr(self, "worker", None) and self.worker.isRunning():
            QMessageBox.warning(self, "En cours", "Installation en cours — merci d'attendre la fin.")
            event.ignore()
        else:
            super().closeEvent(event)

    # Mode spécial (rare) : demander un mot de passe et le renvoyer sur stdout
    @staticmethod
    def run_password_prompt_and_exit():
        dlg = QDialog()
        dlg.setWindowTitle("Piwi – Mot de passe sudo (WSL)")
        dlg.setModal(True)
        dlg.setMinimumWidth(360)
        v = QVBoxLayout(dlg)
        lab = QLabel("Mot de passe sudo (WSL) :")
        from PyQt5.QtWidgets import QLineEdit
        edit = QLineEdit(dlg)
        edit.setEchoMode(QLineEdit.Password)
        v.addWidget(lab)
        v.addWidget(edit)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, dlg)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        v.addWidget(btns)
        if dlg.exec_() == QDialog.Accepted:
            print(edit.text().strip())
            sys.exit(0)
        else:
            sys.exit(2)


# ---------- Entrée ----------

def main_gui():
    app = QApplication(sys.argv)
    w = InstallerWindow()
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    # Mode spécial : retourne un mot de passe via stdout
    if len(sys.argv) >= 2 and sys.argv[1] == "--get-password":
        InstallerWindow.run_password_prompt_and_exit()

    # Mode normal GUI
    main_gui()
