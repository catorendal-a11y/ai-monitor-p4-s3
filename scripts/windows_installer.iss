#ifndef PackageDir
  #error PackageDir must point to the verified portable package
#endif
#ifndef AppVersion
  #error AppVersion must match FW_VERSION
#endif
#ifndef OutputDir
  #error OutputDir is required
#endif
#ifndef AppNumericVersion
  #error AppNumericVersion must contain the numeric major.minor.patch version
#endif

[Setup]
AppId={{873FC919-66BF-49AE-8265-F25894DBE139}
AppName=AI Monitor
AppVersion={#AppVersion}
VersionInfoVersion={#AppNumericVersion}
AppPublisher=AI Monitor contributors
AppPublisherURL=https://github.com/catorendal-a11y/ai-monitor-p4-s3
DefaultDirName={localappdata}\Programs\AI Monitor
DefaultGroupName=AI Monitor
PrivilegesRequired=lowest
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
MinVersion=10.0
DisableProgramGroupPage=yes
DisableDirPage=auto
WizardStyle=modern
SetupIconFile={#PackageDir}\assets\desktop\nova.ico
UninstallDisplayIcon={app}\AI-Monitor.exe
LicenseFile={#PackageDir}\LICENSE
Compression=lzma2/fast
SolidCompression=yes
OutputDir={#OutputDir}
OutputBaseFilename=AI-Monitor-Setup-v{#AppVersion}-windows
CloseApplications=yes
RestartApplications=no
Uninstallable=yes

[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "{#PackageDir}\*"; DestDir: "{app}"; Excludes: "tools\aim_host.json,tools\aim_host.status.json,tools\aim_host.log,tools\activity\*"; Flags: ignoreversion recursesubdirs createallsubdirs

Source: "{#PackageDir}\AI-Monitor-Console.exe"; Flags: dontcopy

[Icons]
Name: "{userprograms}\AI Monitor"; Filename: "{app}\AI-Monitor.exe"; WorkingDir: "{app}"
Name: "{userprograms}\AI Monitor Terminal"; Filename: "{app}\AI-Monitor-Terminal.exe"; WorkingDir: "{app}"; Check: FileExists(ExpandConstant('{app}\AI-Monitor-Terminal.exe'))
Name: "{userdesktop}\AI Monitor"; Filename: "{app}\AI-Monitor.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\AI-Monitor.exe"; Description: "Open AI Monitor setup"; Flags: nowait postinstall skipifsilent

[Code]
function RunLifecycle(const Option: String): Boolean;
var
  Helper: String;
  ResultCode: Integer;
begin
  ResultCode := -1;
  Helper := ExpandConstant('{app}\AI-Monitor-Console.exe');
  Result := Exec(Helper, Option, ExpandConstant('{app}'), SW_HIDE,
    ewWaitUntilTerminated, ResultCode) and (ResultCode = 0);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Result := '';
  if FileExists(ExpandConstant('{app}\AI-Monitor-Console.exe')) then begin
    ExtractTemporaryFile('AI-Monitor-Console.exe');
    if not Exec(ExpandConstant('{tmp}\AI-Monitor-Console.exe'),
      '--prepare-upgrade --installation-root "' + ExpandConstant('{app}') + '"',
      ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ResultCode) then
      ResultCode := -1;
    if ResultCode <> 0 then
      Result := 'AI Monitor could not confirm that its background host stopped. Close this installation and retry. Existing settings are preserved.';
  end;
end;

function InitializeUninstall(): Boolean;
begin
  Result := RunLifecycle('--prepare-uninstall');
  if not Result then
    MsgBox('AI Monitor could not confirm safe cleanup of its background host and owned integrations. Uninstall was stopped before removing application files. Retry after checking local provider settings and the startup task. Private settings and history are preserved.', mbError, MB_OK);
end;
