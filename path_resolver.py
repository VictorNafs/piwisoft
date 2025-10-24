#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, re, sys, json
from typing import Optional

SYSTEM_USERS = {"Public","Default","Default User","All Users"}

def is_wsl() -> bool:
    try:
        with open("/proc/version","r",encoding="utf-8",errors="ignore") as f:
            v=f.read().lower()
        return "microsoft" in v or "wsl" in v
    except Exception:
        return False

def windows_users_dir() -> str: return "/mnt/c/Users"

def candidate_windows_users():
    try:
        root = windows_users_dir()
        if not os.path.isdir(root): return []
        out=[]
        for u in os.listdir(root):
            if u in SYSTEM_USERS: continue
            p=os.path.join(root,u)
            if os.path.isdir(p): out.append(u)
        return out
    except Exception:
        return []

def likely_windows_user() -> Optional[str]:
    up=os.environ.get("USERPROFILE")
    if up and re.match(r"^[A-Za-z]:\\", up):
        m=re.match(r"^[A-Za-z]:\\Users\\([^\\]+)", up)
        if m: return m.group(1)
    un=os.environ.get("USERNAME")
    if un and un not in SYSTEM_USERS: return un
    best=None; best_mtime=-1.0
    for u in candidate_windows_users():
        d=os.path.join(windows_users_dir(),u,"Desktop")
        if os.path.isdir(d):
            try: m=os.path.getmtime(d)
            except Exception: m=0.0
            if m>best_mtime: best_mtime=m; best=u
    if not best:
        users=candidate_windows_users()
        if users: return users[0]
    return None

def win_to_wsl_path(p: str) -> str:
    m=re.match(r"^([A-Za-z]):\\(.*)$", p)
    if not m: return p
    drive=m.group(1).lower(); rest=m.group(2).replace("\\","/")
    return f"/mnt/{drive}/{rest}"

def get_xdg_dir(key: str) -> str:
    try:
        cfg=os.path.expanduser("~/.config/user-dirs.dirs")
        if os.path.exists(cfg):
            with open(cfg,"r",encoding="utf-8") as f:
                for line in f:
                    line=line.strip()
                    if not line or line.startswith("#"): continue
                    if line.startswith(f"XDG_{key}_DIR"):
                        val=line.split("=",1)[1].strip().strip('"')
                        val=val.replace("$HOME",os.path.expanduser("~"))
                        return os.path.expandvars(val)
    except Exception:
        pass
    mapping={"DESKTOP":"Desktop","DOCUMENTS":"Documents","DOWNLOAD":"Downloads",
             "PICTURES":"Pictures","MUSIC":"Music","VIDEOS":"Videos"}
    return os.path.join(os.path.expanduser("~"), mapping.get(key,"Desktop"))

def win_known_folder(name: str, user: str) -> str:
    base=os.path.join(windows_users_dir(), user)
    mapping={"desktop":"Desktop","documents":"Documents","downloads":"Downloads",
             "pictures":"Pictures","music":"Music","videos":"Videos"}
    sub=mapping.get(name)
    return os.path.join(base, sub) if sub else base

def get_known_folder(name: str) -> str:
    name=name.lower()
    if is_wsl() and os.path.isdir(windows_users_dir()):
        user=likely_windows_user()
        if user:
            p=win_known_folder(name, user)
            if os.path.isdir(p): return p
    xdg_key={"desktop":"DESKTOP","documents":"DOCUMENTS","downloads":"DOWNLOAD",
             "pictures":"PICTURES","music":"MUSIC","videos":"VIDEOS"}.get(name,"DESKTOP")
    return get_xdg_dir(xdg_key)

def get_desktop() -> str:   return get_known_folder("desktop")
def get_documents() -> str: return get_known_folder("documents")
def get_downloads() -> str: return get_known_folder("downloads")
def get_pictures() -> str:  return get_known_folder("pictures")
def get_music() -> str:     return get_known_folder("music")
def get_videos() -> str:    return get_known_folder("videos")

KEYWORDS={
    "desktop":{"desktop","bureau"},
    "documents":{"documents","docs"},
    "downloads":{"downloads","download","telechargements","téléchargements","dl"},
    "pictures":{"pictures","images","photos"},
    "music":{"music","musique"},
    "videos":{"videos","vidéos","video","vidéo"},
}

def resolve_hint(hint: str) -> str:
    if not hint: return get_desktop()
    h = hint.strip().strip('"').strip("'")
    low=h.lower()
    for k, aliases in KEYWORDS.items():
        if low in aliases: return get_known_folder(k)
    if re.match(r"^[A-Za-z]:\\", h): h=win_to_wsl_path(h)
    h=os.path.expanduser(os.path.expandvars(h))
    if not os.path.isabs(h):
        h=os.path.abspath(os.path.join(os.path.expanduser("~"), h))
    return h

# ======= AJOUT : localisation de PiwiHome =======
def find_piwi_home() -> str:
    # 1) Desktop/Piwi + marker
    candidates = [
        os.path.join(get_desktop(),"Piwi"),
        os.path.join(os.path.expanduser("~"),"Piwi"),
    ]
    for c in candidates:
        marker=os.path.join(c,".piwi",".piwi_home.json")
        if os.path.exists(marker): return os.path.abspath(c)
    # 2) Scan C:\Users\*\Desktop\Piwi (WSL)
    root=windows_users_dir()
    if os.path.isdir(root):
        try:
            for u in os.listdir(root):
                p=os.path.join(root,u,"Desktop","Piwi",".piwi",".piwi_home.json")
                if os.path.exists(p):
                    return os.path.join(root,u,"Desktop","Piwi")
        except Exception:
            pass
    # 3) Fallback: crée sur Desktop
    piwi=os.path.join(get_desktop(),"Piwi")
    try: os.makedirs(os.path.join(piwi,".piwi"), exist_ok=True)
    except Exception: pass
    return piwi
# ================================================

def print_json():
    data={
        "desktop": get_desktop(),
        "documents": get_documents(),
        "downloads": get_downloads(),
        "pictures": get_pictures(),
        "music": get_music(),
        "videos": get_videos(),
        "is_wsl": is_wsl(),
        "windows_users_dir_exists": os.path.isdir(windows_users_dir()),
        "likely_windows_user": likely_windows_user(),
        "piwi_home": find_piwi_home()  # AJOUT
    }
    print(json.dumps(data, ensure_ascii=False, indent=2))

def main():
    if len(sys.argv) <= 1:
        print(get_desktop()); return
    arg=sys.argv[1].lower()
    if arg in ("--json","json"): print_json(); return
    if arg in ("--resolve","resolve"):
        hint=" ".join(sys.argv[2:]) if len(sys.argv)>2 else ""
        print(resolve_hint(hint)); return
    if arg in ("piwihome","piwi_home"):  # AJOUT
        print(find_piwi_home()); return
    mapping={
        "desktop":get_desktop, "bureau":get_desktop,
        "documents":get_documents,
        "downloads":get_downloads, "download":get_downloads, "telechargements":get_downloads, "téléchargements":get_downloads,
        "pictures":get_pictures, "images":get_pictures, "photos":get_pictures,
        "music":get_music, "musique":get_music,
        "videos":get_videos, "vidéos":get_videos, "video":get_videos, "vidéo":get_videos,
    }
    func=mapping.get(arg)
    if func: print(func())
    else: print(resolve_hint(" ".join(sys.argv[1:])))

if __name__=="__main__":
    main()
