; Inno Setup Script for Calibration Tracker
; This script creates a Windows installer for the Calibration Tracker application

#define MyAppName "Calibration Tracker"
; Keep MyAppVersion in sync with the VERSION file in the repo root
#define MyAppVersion "1.2.10"
#define MyAppPublisher "Your Company Name"
#define MyAppURL "https://www.example.com/"
#define MyAppExeName "CalibrationTracker.exe"
#define MyAppId "{{A1B2C3D4-E5F6-4A5B-8C9D-0E1F2A3B4C5D}"

[Setup]
; NOTE: The value of AppId uniquely identifies this application. Do not use the same AppId value in installers for other applications.
; (To generate a new GUID, click Tools | Generate GUID inside the IDE.)
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
LicenseFile=
InfoBeforeFile=
InfoAfterFile=
OutputDir=installer
OutputBaseFilename=CalibrationTracker_Setup
SetupIconFile=cal_tracker.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64
; Notify the system when we add Python to PATH (so existing processes can pick it up)
ChangesEnvironment=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked; OnlyBelowVersion: 6.1; Check: not IsAdminInstallMode

[Files]
; Main executable
Source: "dist\CalibrationTracker.exe"; DestDir: "{app}"; Flags: ignoreversion
; Stub used to reopen the app after an update (updater runs this; it reads params and launches main exe)
Source: "dist\RestartHelper.exe"; DestDir: "{app}"; Flags: ignoreversion
; Signatures folder
Source: "Signatures\*"; DestDir: "{app}\Signatures"; Flags: ignoreversion recursesubdirs createallsubdirs
; Logo file for PDF exports
Source: "AHI_logo.png"; DestDir: "{app}"; Flags: ignoreversion
; Update checker: script and config (for "Check for Updates" / in-app updater)
Source: "update_app.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "update_checker.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "update_config.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "update_config.example.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "VERSION"; DestDir: "{app}"; Flags: ignoreversion
; Documentation
Source: "USER_GUIDE.md"; DestDir: "{app}"; Flags: ignoreversion

[Dirs]
; Create logs directory for application logs
Name: "{app}\logs"
; Create backups directory for automatic database backups
Name: "{app}\backups"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: quicklaunchicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
// Add Python to user PATH if not already present (needed for "Update now" from installed exe)
function PythonAlreadyOnPath: Boolean;
var
  ResultCode: Integer;
begin
  Result := Exec(ExpandConstant('{cmd}'), '/c python --version', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0);
  if not Result then
    Result := Exec(ExpandConstant('{cmd}'), '/c python3 --version', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0);
end;

function FindPythonInstallPath: String;
var
  InstallPath: String;
begin
  Result := '';
  // Try HKLM PythonCore (64-bit)
  if RegQueryStringValue(HKLM, 'SOFTWARE\Python\PythonCore\3.12\InstallPath', '', InstallPath) and (InstallPath <> '') and DirExists(InstallPath) then
    Result := RemoveBackslashUnlessRoot(InstallPath)
  else if RegQueryStringValue(HKLM, 'SOFTWARE\Python\PythonCore\3.11\InstallPath', '', InstallPath) and (InstallPath <> '') and DirExists(InstallPath) then
    Result := RemoveBackslashUnlessRoot(InstallPath)
  else if RegQueryStringValue(HKLM, 'SOFTWARE\Python\PythonCore\3.10\InstallPath', '', InstallPath) and (InstallPath <> '') and DirExists(InstallPath) then
    Result := RemoveBackslashUnlessRoot(InstallPath)
  else if RegQueryStringValue(HKLM, 'SOFTWARE\Python\PythonCore\3.9\InstallPath', '', InstallPath) and (InstallPath <> '') and DirExists(InstallPath) then
    Result := RemoveBackslashUnlessRoot(InstallPath);
  if Result <> '' then Exit;

  // Try HKLM WOW6432 (32-bit Python on 64-bit OS)
  if RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Python\PythonCore\3.12\InstallPath', '', InstallPath) and (InstallPath <> '') and DirExists(InstallPath) then
    Result := RemoveBackslashUnlessRoot(InstallPath)
  else if RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Python\PythonCore\3.11\InstallPath', '', InstallPath) and (InstallPath <> '') and DirExists(InstallPath) then
    Result := RemoveBackslashUnlessRoot(InstallPath)
  else if RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Python\PythonCore\3.10\InstallPath', '', InstallPath) and (InstallPath <> '') and DirExists(InstallPath) then
    Result := RemoveBackslashUnlessRoot(InstallPath);
  if Result <> '' then Exit;

  // Try HKCU (current user install)
  if RegQueryStringValue(HKCU, 'SOFTWARE\Python\PythonCore\3.12\InstallPath', '', InstallPath) and (InstallPath <> '') and DirExists(InstallPath) then
    Result := RemoveBackslashUnlessRoot(InstallPath)
  else if RegQueryStringValue(HKCU, 'SOFTWARE\Python\PythonCore\3.11\InstallPath', '', InstallPath) and (InstallPath <> '') and DirExists(InstallPath) then
    Result := RemoveBackslashUnlessRoot(InstallPath)
  else if RegQueryStringValue(HKCU, 'SOFTWARE\Python\PythonCore\3.10\InstallPath', '', InstallPath) and (InstallPath <> '') and DirExists(InstallPath) then
    Result := RemoveBackslashUnlessRoot(InstallPath);
  if Result <> '' then Exit;

  // Common user install path
  if DirExists(ExpandConstant('{localappdata}\Programs\Python\Python312')) then
    Result := ExpandConstant('{localappdata}\Programs\Python\Python312')
  else if DirExists(ExpandConstant('{localappdata}\Programs\Python\Python311')) then
    Result := ExpandConstant('{localappdata}\Programs\Python\Python311')
  else if DirExists(ExpandConstant('{localappdata}\Programs\Python\Python310')) then
    Result := ExpandConstant('{localappdata}\Programs\Python\Python310')
  else if DirExists(ExpandConstant('{localappdata}\Programs\Python\Python39')) then
    Result := ExpandConstant('{localappdata}\Programs\Python\Python39');
end;

procedure AddPythonToUserPath(const PythonPath: String);
var
  CurrentPath, NewPath, ScriptsPath: String;
begin
  if PythonPath = '' then Exit;
  ScriptsPath := PythonPath + '\Scripts';
  if not RegQueryStringValue(HKCU, 'Environment', 'Path', CurrentPath) then
    CurrentPath := '';
  NewPath := CurrentPath;
  if (Pos(Uppercase(PythonPath), Uppercase(CurrentPath)) = 0) and (Pos(Uppercase(ScriptsPath), Uppercase(CurrentPath)) = 0) then
  begin
    if NewPath <> '' then NewPath := NewPath + ';';
    NewPath := NewPath + PythonPath;
    if DirExists(ScriptsPath) then
      NewPath := NewPath + ';' + ScriptsPath;
    RegWriteStringValue(HKCU, 'Environment', 'Path', NewPath);
    { ChangesEnvironment=yes in [Setup] helps notify the system; new CMD/app windows will see updated PATH }
  end;
end;

procedure MaybeAddPythonToPath;
var
  PythonPath: String;
begin
  if PythonAlreadyOnPath then Exit;
  PythonPath := FindPythonInstallPath;
  if PythonPath <> '' then
    AddPythonToUserPath(PythonPath);
end;

procedure InitializeWizard();
begin
  // Any custom initialization code can go here
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    // Database will be created on first run
    MaybeAddPythonToPath;
  end;
end;
