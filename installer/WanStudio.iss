; Wan Studio installer (Inno Setup 6). Built by build_client.sh:
;   ISCC /DAppVersion=1.0.0 /DDistDir=<build\dist_client\WanStudio> /DOutDir=<build> installer\WanStudio.iss
; Per-user install into %LOCALAPPDATA%\Programs\Wan Studio: no administrator rights needed.
; User data (Kaggle sign-in, settings, queue, API keys) lives in %LOCALAPPDATA%\Wan Studio\data, outside the program
; folder, so updating keeps it. Uninstalling asks whether to remove it too (default: keep).

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef DistDir
  #define DistDir "..\build\dist_client\WanStudio"
#endif
#ifndef OutDir
  #define OutDir "..\build"
#endif

[Setup]
AppId={{7B3E2C1A-5D4F-4E8B-9A61-2F0C8D7E6B53}
AppName=Wan Studio
AppVersion={#AppVersion}
AppVerName=Wan Studio {#AppVersion}
AppPublisher=luzazzm-stack
AppPublisherURL=https://github.com/luzazzm-stack/wan-studio
AppSupportURL=https://github.com/luzazzm-stack/wan-studio/issues
AppUpdatesURL=https://github.com/luzazzm-stack/wan-studio/releases/latest
DefaultDirName={localappdata}\Programs\Wan Studio
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=commandline
OutputDir={#OutDir}
OutputBaseFilename=WanStudio-Setup
SetupIconFile=..\web\wanstudio.ico
UninstallDisplayIcon={app}\WanStudio.exe
UninstallDisplayName=Wan Studio
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; old program files from an earlier version (never the user's data, which is not in {app})
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\web"
Type: filesandordirs; Name: "{app}\kaggle"

[Icons]
Name: "{autoprograms}\Wan Studio"; Filename: "{app}\WanStudio.exe"; AppUserModelID: "TheEverestHoliday.WanStudio"
Name: "{autodesktop}\Wan Studio"; Filename: "{app}\WanStudio.exe"; Tasks: desktopicon; AppUserModelID: "TheEverestHoliday.WanStudio"

[Run]
Filename: "{app}\WanStudio.exe"; Description: "Open Wan Studio now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; the app may still be running in the background (it keeps working while the window is hidden): stop only this copy
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""Get-Process WanStudio -ErrorAction SilentlyContinue | Where-Object {{ $_.Path -like '{app}\*' } | Stop-Process -Force"""; Flags: runhidden; RunOnceId: "StopWanStudio"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\Wan Studio');
    if DirExists(DataDir) and (not UninstallSilent) then
      if MsgBox('Also remove your Wan Studio sign-in, settings and API keys from this computer?' + #13#10#13#10 +
                'Your videos in the Videos\Wan Studio folder are kept either way.',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
  end;
end;
