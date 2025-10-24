@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion

:: =========================================================
:: Piwi Doctor — diagnostic & réparation de base
:: Usage:
::   piwi_doctor.bat               -> diagnostic interactif
::   piwi_doctor.bat /diag         -> diagnostic uniquement
::   piwi_doctor.bat /reimport     -> réimporte la distro PiwiUbuntu
::   piwi_doctor.bat /network      -> test réseau
::   piwi_doctor.bat /setkey       -> renseigne PIWI_OPENAI_KEY (persistant)
::
:: Prérequis:
::   - download_latest_rootfs.ps1 présent à côté de ce .bat
::   - build_all.bat NON requis pour l’utilisateur final
:: =========================================================

set "BASE=%~dp0"
set "DISTRO=PiwiUbuntu"
set "WSL_DIR=%BASE%wsl"
set "UBUNTU_CODENAME=jammy"

if /I "%~1"=="/diag"      goto :DIAG
if /I "%~1"=="/reimport"  goto :REIMPORT
if /I "%~1"=="/network"   goto :NETWORK
if /I "%~1"=="/setkey"    goto :SETKEY

echo.
echo ==============================
echo   Piwi Doctor (mode interactif)
echo ==============================
echo   [1] Diagnostic rapide
echo   [2] Reimporter la distro WSL (%DISTRO%)
echo   [3] Tester la connectivite reseau
echo   [4] Renseigner la cle API (PIWI_OPENAI_KEY)
echo   [Q] Quitter
echo.
set /p CHOIX="Votre choix: "
if /I "%CHOIX%"=="1" goto :DIAG
if /I "%CHOIX%"=="2" goto :REIMPORT
if /I "%CHOIX%"=="3" goto :NETWORK
if /I "%CHOIX%"=="4" goto :SETKEY
goto :EOF


:DIAG
echo.
echo === DIAGNOSTIC ===

:: WSL installe ?
wsl --status >nul 2>&1
if errorlevel 1 (
  echo [ERREUR] WSL n'est pas actif. Activez "Sous-systeme Windows pour Linux" puis redemarrez Windows.
  goto :END_PAUSE
) else (
  echo [OK] WSL detecte.
)

:: Distro presente ?
set "HAVE_DISTRO=1"
wsl --list --quiet | findstr /i "^%DISTRO%$" >nul
if errorlevel 1 (
  set "HAVE_DISTRO=0"
  echo [WARN] La distribution %DISTRO% n'est pas installee.
) else (
  echo [OK] Distribution %DISTRO% detectee.
)

:: Dossier app
if exist "%BASE%noyau.py" (
  echo [OK] Dossier d'application: %BASE%
) else (
  echo [ERREUR] noyau.py introuvable dans %BASE%. Reinstaller Piwi.
)

:: Test Reseau rapide
call :NETWORK_QUICK

:: Smoke test WSL (si distro dispo)
if "%HAVE_DISTRO%"=="1" (
  echo.
  echo [TEST] Lancement WSL basique...
  wsl -d %DISTRO% -- bash -lc "echo -n 'user='; whoami; uname -a; python3 --version 2>/dev/null || true"
)

:: Cle API presente ?
call :CHECK_KEY

echo.
echo [INFO] Pour reimporter la distro:  piwi_doctor.bat /reimport
echo [INFO] Pour configurer la cle:     piwi_doctor.bat /setkey
goto :END_PAUSE


:REIMPORT
echo.
echo === REIMPORT WSL %DISTRO% ===
if not exist "%BASE%download_latest_rootfs.ps1" (
  echo [ERREUR] download_latest_rootfs.ps1 introuvable dans %BASE%.
  goto :END_PAUSE
)
if not exist "%WSL_DIR%" mkdir "%WSL_DIR%"

echo [Step] Telechargement du rootfs verifie (via PowerShell)...
for /f "delims=" %%f in ('
  powershell -ExecutionPolicy Bypass -NoProfile -File "%BASE%download_latest_rootfs.ps1" -Codename %UBUNTU_CODENAME% -OutputFolder "%WSL_DIR%"
') do set "ROOTFS_NAME=%%f"

if not exist "%WSL_DIR%\%ROOTFS_NAME%" (
  echo [ERREUR] Archive rootfs introuvable: "%WSL_DIR%\%ROOTFS_NAME%"
  goto :END_PAUSE
)

echo [Step] Nettoyage et reimport...
wsl --terminate %DISTRO% >nul 2>&1
wsl --unregister %DISTRO% >nul 2>&1
if exist "%WSL_DIR%\%DISTRO%" rmdir /S /Q "%WSL_DIR%\%DISTRO%" 2>nul

wsl --import %DISTRO% "%WSL_DIR%\%DISTRO%" "%WSL_DIR%\%ROOTFS_NAME%" --version 2 || (
  echo [ERREUR] Import WSL echoue.
  goto :END_PAUSE
)
wsl --set-default %DISTRO%
echo [OK] Reimport termine.

echo.
echo [TEST] Smoke test...
wsl -d %DISTRO% -- bash -lc "echo hello-from-%DISTRO% && uname -a && python3 --version || true"
goto :END_PAUSE


:NETWORK
echo.
echo === TESTS DE CONNECTIVITE ===
call :NETWORK_QUICK
goto :END_PAUSE

:NETWORK_QUICK
:: Ping DNS + HTTP simple
ping -n 1 1.1.1.1 >nul 2>&1
if errorlevel 1 (echo [WARN] Ping 1.1.1.1: ECHEC) else (echo [OK] Ping 1.1.1.1: OK)

powershell -NoProfile -Command "try { (Invoke-WebRequest -Uri 'https://www.microsoft.com' -UseBasicParsing -TimeoutSec 8 ^| Select-Object -First 1 ^| Out-Null); exit 0 } catch { exit 1 }"
if errorlevel 1 (echo [WARN] HTTP test: ECHEC) else (echo [OK] HTTP test: OK)
exit /b 0


:SETKEY
echo.
echo === CONFIGURER LA CLE OPENAI (PIWI_OPENAI_KEY) ===
echo Entrez votre cle (elle sera stockee dans l'environnement utilisateur Windows):
set /p NEWKEY="> Clé: "
if "%NEWKEY%"=="" (
  echo [INFO] Aucune valeur entree.
  goto :END_PAUSE
)
:: Persiste pour l'utilisateur (nouveau shell requis pour prise en compte)
setx PIWI_OPENAI_KEY "%NEWKEY%" >nul
echo [OK] Variable d'environnement enregistree: PIWI_OPENAI_KEY
echo [NOTE] Fermez puis rouvrez l'application/terminal pour qu'elle soit visible.
goto :END_PAUSE


:CHECK_KEY
set "_k=%PIWI_OPENAI_KEY%"
if "%_k%"=="" (
  for /f "tokens=2,*" %%A in ('reg query "HKCU\Environment" /v PIWI_OPENAI_KEY 2^>nul ^| find "PIWI_OPENAI_KEY"') do set "_k=%%B"
)
if "%_k%"=="" (
  echo [WARN] PIWI_OPENAI_KEY non definie. Lancez:  piwi_doctor.bat /setkey
) else (
  echo [OK] PIWI_OPENAI_KEY est configuree.
)
exit /b 0


:END_PAUSE
echo.
pause
exit /b
