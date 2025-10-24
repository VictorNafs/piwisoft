@echo off
setlocal enableextensions enabledelayedexpansion
cd /d "%~dp0"

echo === Piwi - Build GUI unique ===

REM -- Vars
set "PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
set "WSL_DIR=%CD%\wsl"

if not exist "%WSL_DIR%" mkdir "%WSL_DIR%"

echo [DL] (Optionnel) Downloading Ubuntu rootfs (jammy) into "%WSL_DIR%"...
for /f "usebackq delims=" %%F in (`
  "%PS%" -NoProfile -ExecutionPolicy Bypass -File ".\download_latest_rootfs.ps1" -Codename "jammy" -OutputFolder ".\wsl"
`) do set "ROOTFS_FILENAME=%%F"

if defined ROOTFS_FILENAME (
  if exist "%WSL_DIR%\%ROOTFS_FILENAME%" (
    echo [OK] Rootfs ready: "%WSL_DIR%\%ROOTFS_FILENAME%"
  ) else (
    echo [WARN] Rootfs non trouvé. Le build continue sans.
  )
) else (
  echo [INFO] Pas de rootfs téléchargé (continuation).
)

echo.
echo === Building GUI ===

REM -- Trouver PyInstaller
set "PYI="
where pyinstaller >nul 2>nul && set "PYI=pyinstaller"
if not defined PYI (
  python -c "import PyInstaller,sys;sys.exit(0)" 1>nul 2>nul
  if errorlevel 1 (
    echo [ERR] PyInstaller introuvable. Installe:  python -m pip install pyinstaller
    exit /b 1
  )
  set "PYI=python -m PyInstaller"
)

%PYI% -y --clean ".\piwi_gui_win.spec"
if errorlevel 1 goto :error

echo [OK] Build complete. See .\dist\piwi_gui_win\
exit /b 0

:error
echo [ERR] Build failed.
exit /b 1
