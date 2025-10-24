; -------------------------------------------------------------
; Piwi - Inno Setup installer (100% automatisé, un seul EXE)
; -------------------------------------------------------------

#define MyDistroName "PiwiUbuntu"

[Setup]
AppId={{8A2C5A7E-1027-4D2C-9B7E-PIWI-000000000001}}
AppName=Piwi
AppVersion=1.0
AppPublisher=Piwi
SetupIconFile=piwi_icon.ico
UninstallDisplayIcon={app}\piwi_icon.ico
; IMPORTANT: on demande l'admin pour pouvoir activer les features WSL/VMP
PrivilegesRequired=admin
DefaultDirName={%USERPROFILE}\Piwi
DefaultGroupName=Piwi
ArchitecturesInstallIn64BitMode=x64
OutputDir=.
OutputBaseFilename=piwi_installer
Compression=lzma
SolidCompression=yes
DisableDirPage=no
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
WizardStyle=modern

[Files]
; On installe TOUT le répertoire PyInstaller du GUI (un seul binaire utilisateur)
Source: "dist\piwi_gui_win\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; (optionnel) si tu gardes les icônes au repo
Source: "piwi_icon.ico"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "piwi_icon.png"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
; Un seul raccourci : "Piwi" -> piwi_gui_win.exe
Name: "{userdesktop}\Piwi"; \
  Filename: "{app}\piwi_gui_win.exe"; \
  WorkingDir: "{app}"; \
  IconFilename: "{app}\piwi_icon.ico"

; (facultatif) Menu Démarrer
Name: "{userprograms}\Piwi\Piwi"; \
  Filename: "{app}\piwi_gui_win.exe"; \
  WorkingDir: "{app}"; \
  IconFilename: "{app}\piwi_icon.ico"

[Run]
; Lance directement l’application en fin d’install
Filename: "{app}\piwi_gui_win.exe"; \
  WorkingDir: "{app}"; \
  Description: "Lancer Piwi"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Purge éventuelle des artefacts WSL dans le dossier app
Type: filesandordirs; Name: "{app}\wsl"

[Code]
const
  DistroName = '{#MyDistroName}';

function FileToString(const FileName: string; var S: AnsiString): Boolean;
var
  Stream: TFileStream;
begin
  Result := False;
  if not FileExists(FileName) then Exit;
  Stream := TFileStream.Create(FileName, fmOpenRead or fmShareDenyNone);
  try
    SetLength(S, Stream.Size);
    if Stream.Size > 0 then Stream.Read(S[1], Stream.Size);
    Result := True;
  finally
    Stream.Free;
  end;
end;

function ExecHidden(const FileName, Params: string; out RC: Integer): Boolean;
begin
  Result := Exec(FileName, Params, '', SW_HIDE, ewWaitUntilTerminated, RC);
end;

function DistroExists(): Boolean;
var
  Tmp, Cmd, OutTxt: string;
  A: AnsiString;
  RC: Integer;
begin
  Result := False;
  Tmp := ExpandConstant('{tmp}\wsl_list.txt');
  ; wsl -l -q > tmp
  if not ExecHidden(ExpandConstant('{sys}\cmd.exe'),
    '/C "' + ExpandConstant('{sys}\wsl.exe') + ' -l -q > "' + Tmp + '""', RC) then
    Exit;
  if (RC <> 0) then Exit;
  if not FileToString(Tmp, A) then Exit;
  OutTxt := String(A);
  Result := (Pos(#13#10 + DistroName + #13#10, #13#10 + OutTxt + #13#10) > 0)
         or (Pos(DistroName, OutTxt) > 0);
end;

function FindRootfs(out Rootfs: string): Boolean;
var
  SR: TFindRec;
  Base: string;
begin
  Result := False;
  Base := AddBackslash(ExpandConstant('{app}')) + 'wsl';
  if not DirExists(Base) then Exit;
  if FindFirst(Base + '\*.rootfs.tar.gz', SR) then begin
    try
      Rootfs := Base + '\' + SR.Name;
      Result := True;
    finally
      FindClose(SR);
    end;
  end;
end;

function EnsureWSLFeatures(): Boolean;
var
  RC: Integer;
  Cmd: string;
begin
  Result := True;
  { Active VirtualMachinePlatform et Microsoft-Windows-Subsystem-Linux (pas de reboot ici) }
  if not ExecHidden(ExpandConstant('{sys}\dism.exe'),
      '/Online /Enable-Feature /FeatureName:VirtualMachinePlatform /All /NoRestart', RC) then
    Exit;
  if RC <> 0 then begin
    { on n'échoue pas l'install entière, on continue }
  end;

  if not ExecHidden(ExpandConstant('{sys}\dism.exe'),
      '/Online /Enable-Feature /FeatureName:Microsoft-Windows-Subsystem-Linux /All /NoRestart', RC) then
    Exit;
  { RC non-bloquant }

  { Tente wsl --update pour récupérer le kernel (non bloquant) }
  ExecHidden(ExpandConstant('{sys}\wsl.exe'), '--update', RC);
  Result := True;
end;

function ImportDistro(const Rootfs: string): Boolean;
var
  RC: Integer;
  InstallDir, Args: string;
begin
  Result := False;
  InstallDir := AddBackslash(ExpandConstant('{app}')) + 'wsl\PiwiUbuntuFS';
  if not DirExists(InstallDir) then
    ForceDirectories(InstallDir);
  Args := Format('--import %s "%s" "%s" --version 2',
                 [DistroName, InstallDir, Rootfs]);
  if ExecHidden(ExpandConstant('{sys}\wsl.exe'), Args, RC) then
    Result := (RC = 0);
end;

function RunInWSLAsRoot(const Bash: string): Boolean;
var
  RC: Integer;
  Args: string;
begin
  Args := Format('-d %s -u root -- bash -lc "%s"', [DistroName, Bash]);
  Result := ExecHidden(ExpandConstant('{sys}\wsl.exe'), Args, RC) and (RC = 0);
end;

procedure DoInitialSetupInWSL();
var
  AppWin: string;
  AppWSL: string;
  Bash: string;
begin
  { On exécute ton setup côté WSL, en root, juste après l'import.
    - copie/usage de setup_piwi.sh déjà packagé dans {app}
    - création du marker .piwi_home.json via le script si c'est ce qu'il fait }
  AppWin := AddBackslash(ExpandConstant('{app}'));
  { Conversion rapide Windows -> WSL : /mnt/c/... (les backslashes deviennent /) }
  AppWSL := StringChangeEx(AppWin, '\', '/', True);
  AppWSL := '/mnt/' + LowerCase(Copy(AppWSL, 1, 1)) + Copy(AppWSL, 3, MaxInt);

  { On lance le setup en root WSL }
  Bash :=
    'cd ' + AppWSL + ' && ' +
    'chmod +x setup_piwi.sh || true && ' +
    './setup_piwi.sh || true';

  RunInWSLAsRoot(Bash);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Rootfs: string;
begin
  if CurStep = ssPostInstall then
  begin
    { 1) S’assurer que les features WSL sont activées (admin requis) }
    EnsureWSLFeatures();

    { 2) Import auto si la distro n’existe pas encore }
    if not DistroExists() then
    begin
      if FindRootfs(Rootfs) then
      begin
        if ImportDistro(Rootfs) then
        begin
          { 3) Setup initial dans la distro (root) }
          DoInitialSetupInWSL();
        end
        else
        begin
          MsgBox('Import WSL automatique impossible. Vous pourrez relancer Piwi et l''auto-réparation s''en chargera.',
                 mbInformation, MB_OK);
        end;
      end
      else
      begin
        { Pas de rootfs trouvé : l’app démarrera quand même (auto-réparation côté GUI) }
      end;
    end
    else
    begin
      { Distro déjà présente : (re)jouer un setup rapide, sans bloquer }
      DoInitialSetupInWSL();
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    Exec(ExpandConstant('{sys}\wsl.exe'), '--shutdown', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Exec(ExpandConstant('{sys}\wsl.exe'), '--unregister ' + DistroName, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Sleep(700);
  end;
end;
