; -----------------------------------------------------------------------------
; Piwi Installer Script (Inno Setup)
; -----------------------------------------------------------------------------
; Installe Piwi, son GUI, le RootFS Ubuntu, et configure WSL
; -----------------------------------------------------------------------------

#define MyAppName "Piwi"
#define MyAppVersion "1.0"
#define MyAppPublisher "VictorNafs"
#define MyAppExeName "piwi_installer_gui.exe"

[Setup]
AppId={{A9F5C7F6-1E5E-4D7F-B93C-19A4AFA5C43B}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL=https://github.com/VictorNafs
AppSupportURL=https://github.com/VictorNafs
AppUpdatesURL=https://github.com/VictorNafs
DefaultDirName={autopf}\{#MyAppName}
DisableProgramGroupPage=yes
OutputDir=dist\installer
OutputBaseFilename=Piwi_Installer
Compression=lzma
SolidCompression=yes
PrivilegesRequired=admin
WizardStyle=modern
; Evite le warning "x64 deprecated" en utilisant x64compatible
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

; (optionnel) si tu veux quand même laisser la case "Icône sur le Bureau", décommente:
; [Tasks]
; Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
Source: "dist\piwi_gui_win.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\piwi_installer_gui.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "wsl\ubuntu-jammy-wsl-amd64-ubuntu22.04lts.rootfs.tar.gz"; DestDir: "{app}\wsl"; Flags: ignoreversion
Source: "wsl\piwi-rootfs.sha256"; DestDir: "{app}\wsl"; Flags: ignoreversion
Source: "setup_piwi.sh"; DestDir: "{app}"; Flags: ignoreversion
Source: "init.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "build_all.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "download_latest_rootfs.ps1"; DestDir: "{app}"; Flags: ignoreversion
; (facultatif)
Source: "piwi_icon.ico"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "piwi_icon.png"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
; Menu Démarrer
Name: "{autoprograms}\{#MyAppName}\Piwi"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\piwi_icon.ico"; WorkingDir: "{app}"
; Bureau (FORCÉ — pas de Tasks: -> le raccourci est toujours créé)
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\piwi_icon.ico"; WorkingDir: "{app}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]

function IsWSLInstalled(): Boolean;
var
  ResultCode: Integer;
begin
  Result := Exec('wsl', '--version', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := (ResultCode = 0);
end;

procedure RunInWSLAsRoot(const Command: String);
var
  ResultCode: Integer;
begin
  if not IsWSLInstalled() then
  begin
    MsgBox('WSL n''est pas installé. Veuillez installer WSL avant de continuer.', mbError, MB_OK);
    Exit;
  end;
  Exec('wsl', '-u root bash -c "' + Command + '"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

procedure DoInitialSetupInWSL;
var
  AppWin, AppWSL, Bash: string;
begin
  // Chemin Windows -> forme Unix
  AppWin := AddBackslash(ExpandConstant('{app}'));
  AppWSL := AppWin;
  StringChangeEx(AppWSL, '\', '/', True);  // modifie AppWSL in-place

  // "C:/..." -> "/mnt/c/..."
  AppWSL := '/mnt/' + LowerCase(Copy(AppWSL, 1, 1)) + Copy(AppWSL, 3, Length(AppWSL));

  Bash :=
    'cd ' + AppWSL + ' && ' +
    'chmod +x setup_piwi.sh || true && ' +
    './setup_piwi.sh || true';

  RunInWSLAsRoot(Bash);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    MsgBox('L’installation de Piwi est terminée. Configuration de WSL en cours...', mbInformation, MB_OK);
    DoInitialSetupInWSL;
  end;
end;
