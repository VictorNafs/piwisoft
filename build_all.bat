@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"

echo === Piwi - Build GUI, download RootFS, and build Installer ===

rem --- Paths & files ---
set "ROOT=%CD%"
set "WSL_DIR=%ROOT%\wsl"
set "PYI_SPEC_MAIN=%ROOT%\piwi_gui_win.spec"
set "PYI_SRC_MAIN=%ROOT%\piwi_gui_win.py"
set "PYI_SPEC_INSTALLER=%ROOT%\piwi_installer_gui.spec"
set "PYI_SRC_INSTALLER=%ROOT%\piwi_installer_gui.py"
set "INNO_ISS=%ROOT%\piwi_installer.iss"

rem Clean previous builds (optional)
if exist "%ROOT%\dist" rmdir /s /q "%ROOT%\dist"
if exist "%ROOT%\build" rmdir /s /q "%ROOT%\build"
del /q "%ROOT%\piwi_installer.exe" 2>nul

rem Ensure WSL_DIR exists
if not exist "%WSL_DIR%" mkdir "%WSL_DIR%"

echo [1/5] Checking PyInstaller availability...
where /q pyinstaller
if errorlevel 1 (
  echo [ERR] PyInstaller not found in PATH. Please: pip install pyinstaller
  goto :error
)

echo [2/5] Building main GUI...
if exist "%PYI_SPEC_MAIN%" (
  echo [INFO] Using spec: "%PYI_SPEC_MAIN%"
  pyinstaller --noconfirm "%PYI_SPEC_MAIN%"
) else (
  if not exist "%PYI_SRC_MAIN%" (
    echo [ERR] Missing "%PYI_SPEC_MAIN%" and "%PYI_SRC_MAIN%".
    goto :error
  )
  echo [INFO] Using source: "%PYI_SRC_MAIN%"
  pyinstaller --noconfirm --onefile --windowed --name piwi_gui_win "%PYI_SRC_MAIN%"
)
if errorlevel 1 (
  echo [ERR] PyInstaller failed for main GUI.
  goto :error
)
echo [OK] Main GUI built.

echo [3/5] Downloading RootFS from GitHub Releases and verifying SHA256...
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0download_latest_rootfs.ps1"
if errorlevel 1 (
  echo [ERR] RootFS download or verification failed.
  goto :error
)
if not exist "%WSL_DIR%\ubuntu-jammy-wsl-amd64-ubuntu22.04lts.rootfs.tar.gz" (
  echo [ERR] RootFS file not found after download.
  goto :error
)
echo [OK] RootFS ready: "%WSL_DIR%\ubuntu-jammy-wsl-amd64-ubuntu22.04lts.rootfs.tar.gz"

echo [4/5] Building installer GUI...
set "SKIP_INSTALLER_GUI="
if exist "%PYI_SPEC_INSTALLER%" (
  echo [INFO] Using spec: "%PYI_SPEC_INSTALLER%"
  pyinstaller --noconfirm "%PYI_SPEC_INSTALLER%"
) else (
  if not exist "%PYI_SRC_INSTALLER%" (
    echo [WARN] Missing "%PYI_SPEC_INSTALLER%" and "%PYI_SRC_INSTALLER%". Skipping installer GUI build.
    set "SKIP_INSTALLER_GUI=1"
  ) else (
    echo [INFO] Using source: "%PYI_SRC_INSTALLER%"
    pyinstaller --noconfirm --onefile --windowed --name piwi_installer_gui "%PYI_SRC_INSTALLER%"
  )
)
if not defined SKIP_INSTALLER_GUI if errorlevel 1 (
  echo [ERR] PyInstaller failed for installer GUI.
  goto :error
)
if defined SKIP_INSTALLER_GUI (
  echo [INFO] Installer GUI build skipped.
) else (
  echo [OK] Installer GUI built.
)

rem ---- Build Inno via subroutine (évite "not était inattendu") ----
call :build_inno
goto :done

:build_inno
echo [5/5] Building final Windows installer (Inno Setup)...
set "ISCC_EXE="
where /q iscc && for /f "delims=" %%P in ('where iscc') do set "ISCC_EXE=%%P"
if not defined ISCC_EXE if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC_EXE=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not defined ISCC_EXE if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set "ISCC_EXE=C:\Program Files\Inno Setup 6\ISCC.exe"

if defined ISCC_EXE (
  if not exist "%INNO_ISS%" (
    echo [INFO] No "%INNO_ISS%" found. Skipping .exe installer build.
    goto :eof
  )
  "%ISCC_EXE%" /Qp "%INNO_ISS%"
  if errorlevel 1 (
    echo [WARN] Inno Setup failed. You can still distribute the built GUI binaries under dist\ .
    goto :eof
  )
  echo [OK] Inno Setup installer built.
  goto :eof
)

rem === ISCC non trouvé : proposer d'ouvrir l'interface Inno Setup (Compil32.exe) ===
set "COMPIL_GUI="
if exist "C:\Program Files (x86)\Inno Setup 6\Compil32.exe" set "COMPIL_GUI=C:\Program Files (x86)\Inno Setup 6\Compil32.exe"
if exist "C:\Program Files\Inno Setup 6\Compil32.exe" set "COMPIL_GUI=C:\Program Files\Inno Setup 6\Compil32.exe"

if not defined COMPIL_GUI (
  echo [INFO] Inno Setup non trouve (ni ISCC ni Compil32). Skipping .exe installer build.
  goto :eof
)

if not exist "%INNO_ISS%" (
  echo [INFO] No "%INNO_ISS%" found. Skipping .exe installer build.
  goto :eof
)

echo [INFO] ISCC non detecte. Ouvrir l'interface Inno Setup pour compiler maintenant ? [O/N]
choice /C ON /N
if errorlevel 2 (
  echo [INFO] Compilation GUI annulee. Vous pouvez lancer manuellement :
  echo        "%COMPIL_GUI%" "%INNO_ISS%"
  goto :eof
)

echo [INFO] Ouverture de l'interface Inno Setup...
start "" "%COMPIL_GUI%" "%INNO_ISS%"
echo [TIP] Dans Inno Setup, cliquez sur "Compiler" (F9) pour generer l'installeur.
goto :eof

:done
echo.
echo === Done ===
exit /b 0

:error
echo.
echo [ERR] Build failed.
exit /b 1
