; Installationsassistent für Zeitzeuge (Inno Setup 6).
;
; Baut aus der Ordner-Variante (dist\ZeitZeuge-Ordner, ZEITZEUGE_ONEDIR=1) dist\Zeitzeuge-Setup.exe:
;   iscc /DAppVersion=4.1.25 /DFileVersion=4.1.25.330 installer\zeitzeuge.iss
;
; - Nur für den angemeldeten Benutzer, ohne Adminrechte: %LOCALAPPDATA%\Programs\Zeitzeuge.
; - Vorhandene Installation: wird aktualisiert (gleiche AppId, gleicher Ordner).
; - Alte Einzeldatei ZeitZeuge.exe (Desktop, OneDrive-Desktop, Downloads, Autostart): wird gefunden
;   und auf Wunsch durch eine Verknüpfung zur installierten Version ersetzt.
; - Daten (Einstellungen im Datenordner, Datenbank unter %LOCALAPPDATA%\Zeitzeuge): bleiben, wo
;   sie sind, und werden weiter genutzt. Vor einem Update legt Setup eine Kopie in
;   %LOCALAPPDATA%\Zeitzeuge\vor-update an. Deinstallieren lässt die Daten stehen.
; - Update aus Zeitzeuge (src/updater.py): /SILENT /SUPPRESSMSGBOXES /ZZUPDATE=show|min. Setup wartet,
;   bis Zeitzeuge sich beendet hat, lässt Autostart und Verknüpfungen wie sie sind und startet
;   Zeitzeuge danach wieder (bei min im Infobereich).

#ifndef AppVersion
  #define AppVersion "0.0.0-local"
#endif
#ifndef FileVersion
  #define FileVersion "0.0.0.0"
#endif

[Setup]
AppId={{AC3DB4ED-EDC6-4063-9924-265CC99F82EC}
AppName=Zeitzeuge
AppVersion={#AppVersion}
AppVerName=Zeitzeuge {#AppVersion}
AppPublisher=Filip Kroczak
VersionInfoCompany=Filip Kroczak
VersionInfoCopyright=Copyright (c) 2026 Filip Kroczak
VersionInfoVersion={#FileVersion}
VersionInfoDescription=Zeitzeuge einrichten
PrivilegesRequired=lowest
DefaultDirName={autopf}\Zeitzeuge
DefaultGroupName=Zeitzeuge
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
OutputDir=..\dist
OutputBaseFilename=Zeitzeuge-Setup
SetupIconFile=..\assets\zeitzeuge.ico
UninstallDisplayIcon={app}\ZeitZeuge.exe
UninstallDisplayName=Zeitzeuge
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Laufendes Zeitzeuge prüft der Code unten selbst (Daten sauber speichern lassen statt abschießen)
CloseApplications=no

[Languages]
Name: "de"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "Verknüpfung auf dem &Desktop"
Name: "autostart"; Description: "Mit &Windows starten (im Infobereich)"

[InstallDelete]
; Bibliotheken der vorigen Version entfernen, sonst mischen sich alte und neue DLLs
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\ZeitZeuge-Ordner\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Zeitzeuge"; Filename: "{app}\ZeitZeuge.exe"
Name: "{autodesktop}\Zeitzeuge"; Filename: "{app}\ZeitZeuge.exe"; Tasks: desktopicon

[Registry]
; Gleicher Eintrag wie Einstellungen → Allgemein → Mit Windows starten (src/autostart.py)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; \
  ValueName: "Zeitzeuge"; ValueData: """{app}\ZeitZeuge.exe"" --minimized"; Tasks: autostart; \
  Check: not IsAppUpdate

[Run]
Filename: "{app}\ZeitZeuge.exe"; Description: "Zeitzeuge jetzt starten"; Flags: nowait postinstall skipifsilent
; Nach einem Update aus Zeitzeuge wieder starten, wie es vorher war (Fenster oder Infobereich)
Filename: "{app}\ZeitZeuge.exe"; Parameters: "--neustart"; Flags: nowait; Check: RestartAs('show')
Filename: "{app}\ZeitZeuge.exe"; Parameters: "--minimized --neustart"; Flags: nowait; Check: RestartAs('min')

[Code]
const
  RunKey = 'Software\Microsoft\Windows\CurrentVersion\Run';
  UninstallKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{AC3DB4ED-EDC6-4063-9924-265CC99F82EC}_is1';

var
  OldFiles: TStringList;      // alte Einzeldateien ZeitZeuge.exe und Autostart-Verknüpfungen
  FoundPage: TInputOptionWizardPage;
  PreviousVersion: String;

{ ---------- Update aus Zeitzeuge ---------- }

function IsAppUpdate: Boolean;
begin
  Result := ExpandConstant('{param:ZZUPDATE|}') <> '';
end;

function RestartAs(Mode: String): Boolean;
begin
  Result := CompareText(ExpandConstant('{param:ZZUPDATE|}'), Mode) = 0;
end;

{ ---------- Suchen ---------- }

function DataDir: String;
var
  Pointer: AnsiString;
begin
  // Wie src/storage.py: eigener Ordner aus speicherort.txt, sonst Dokumente\Zeitzeuge
  Result := '';
  if LoadStringFromFile(ExpandConstant('{userappdata}\Zeitzeuge\speicherort.txt'), Pointer) then
    Result := Trim(String(Pointer));
  if (Result = '') or not DirExists(Result) then
    Result := ExpandConstant('{userdocs}\Zeitzeuge');
end;

function ConfigFile: String;
begin
  Result := AddBackslash(DataDir) + 'zeitzeuge_config.json';
end;

function DbFile: String;
begin
  Result := ExpandConstant('{localappdata}\Zeitzeuge\zeitzeuge.db');
end;

procedure AddOld(Path: String);
begin
  if (Path = '') or not FileExists(Path) then
    exit;
  // Ordner-Variante (hat _internal daneben) ist keine alte Einzeldatei, z. B. diese Installation
  if DirExists(AddBackslash(ExtractFileDir(Path)) + '_internal') then
    exit;
  if OldFiles.IndexOf(Path) < 0 then  // ohne Rücksicht auf Groß-/Kleinschreibung
    OldFiles.Add(Path);
end;

function RunValuePath: String;
var
  Value: String;
  P: Integer;
begin
  Result := '';
  if not RegQueryStringValue(HKCU, RunKey, 'Zeitzeuge', Value) then
    exit;
  Value := Trim(Value);
  if Copy(Value, 1, 1) = '"' then
  begin
    Delete(Value, 1, 1);
    P := Pos('"', Value);
    if P > 0 then
      Result := Copy(Value, 1, P - 1);
  end
  else
  begin
    P := Pos(' ', Value);
    if P > 0 then
      Result := Copy(Value, 1, P - 1)
    else
      Result := Value;
  end;
end;

procedure FindOldFiles;
var
  Dirs: TStringList;
  I: Integer;
  Rec: TFindRec;
begin
  Dirs := TStringList.Create;
  try
    Dirs.Add(ExpandConstant('{userdesktop}'));
    Dirs.Add(ExpandConstant('{userdocs}'));
    if GetEnv('USERPROFILE') <> '' then
    begin
      Dirs.Add(GetEnv('USERPROFILE') + '\Desktop');
      Dirs.Add(GetEnv('USERPROFILE') + '\Downloads');
    end;
    if GetEnv('OneDrive') <> '' then
      Dirs.Add(GetEnv('OneDrive') + '\Desktop');
    if GetEnv('OneDriveCommercial') <> '' then
      Dirs.Add(GetEnv('OneDriveCommercial') + '\Desktop');
    if GetEnv('OneDriveConsumer') <> '' then
      Dirs.Add(GetEnv('OneDriveConsumer') + '\Desktop');
    for I := 0 to Dirs.Count - 1 do
      AddOld(AddBackslash(Dirs[I]) + 'ZeitZeuge.exe');
  finally
    Dirs.Free;
  end;
  AddOld(RunValuePath);
  // Verknüpfungen im Autostart-Ordner (alte Anleitung: shell:startup); ersetzt der Run-Eintrag
  if FindFirst(ExpandConstant('{userstartup}\*eitzeuge*.lnk'), Rec) then
  try
    repeat
      if OldFiles.IndexOf(ExpandConstant('{userstartup}\') + Rec.Name) < 0 then
        OldFiles.Add(ExpandConstant('{userstartup}\') + Rec.Name);
    until not FindNext(Rec);
  finally
    FindClose(Rec);
  end;
end;

{ ---------- Läuft Zeitzeuge? ---------- }

function ZeitzeugeRunning: Boolean;
var
  Locator, Service, Procs: Variant;
begin
  Result := False;
  try
    Locator := CreateOleObject('WbemScripting.SWbemLocator');
    Service := Locator.ConnectServer('.', 'root\CIMV2');
    Procs := Service.ExecQuery('SELECT ProcessId FROM Win32_Process WHERE Name = ''ZeitZeuge.exe''');
    Result := Procs.Count > 0;
  except
    Log('Prozessliste nicht lesbar: ' + GetExceptionMessage);
  end;
end;

{ ---------- Assistent ---------- }

function FoundText: String;
var
  I: Integer;
begin
  Result := '';
  if PreviousVersion <> '' then
    Result := Result + 'Installiert ist Zeitzeuge ' + PreviousVersion + '. Es wird auf {#AppVersion} aktualisiert.' + #13#10#13#10;
  if FileExists(DbFile) or FileExists(ConfigFile) then
  begin
    Result := Result + 'Deine Daten werden übernommen. Sie bleiben, wo sie sind:' + #13#10;
    if FileExists(ConfigFile) then
      Result := Result + '  Einstellungen: ' + ConfigFile + #13#10;
    if FileExists(DbFile) then
      Result := Result + '  Datenbank: ' + DbFile + #13#10;
    Result := Result + 'Vor dem Update legt Setup eine Kopie unter ' +
      ExpandConstant('{localappdata}\Zeitzeuge\vor-update') + ' an.' + #13#10#13#10;
  end;
  if OldFiles.Count > 0 then
  begin
    Result := Result + 'Gefunden (alte Einzeldatei oder Autostart-Verknüpfung):' + #13#10;
    for I := 0 to OldFiles.Count - 1 do
      Result := Result + '  ' + OldFiles[I] + #13#10;
  end;
end;

procedure InitializeWizard;
begin
  OldFiles := TStringList.Create;
  FindOldFiles;
  if not RegQueryStringValue(HKCU, UninstallKey, 'DisplayVersion', PreviousVersion) then
    PreviousVersion := '';
  FoundPage := CreateInputOptionPage(wpWelcome, 'Vorhandenes Zeitzeuge',
    'Was Setup auf diesem PC gefunden hat', FoundText, False, False);
  FoundPage.Add('Alte Dateien durch eine Verknüpfung zur installierten Version ersetzen');
  FoundPage.Values[0] := True;
  FoundPage.CheckListBox.Visible := OldFiles.Count > 0;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := (PageID = FoundPage.ID) and (FoundText = '');
end;

procedure CurPageChanged(CurPageID: Integer);
var
  Value: String;
begin
  // Autostart beim Update so lassen, wie er in Zeitzeuge eingestellt ist
  if (CurPageID = wpSelectTasks) and (PreviousVersion <> '') then
  begin
    if RegQueryStringValue(HKCU, RunKey, 'Zeitzeuge', Value) then
      WizardSelectTasks('autostart')
    else
      WizardSelectTasks('!autostart');
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  I: Integer;
begin
  Result := True;
  if CurPageID <> wpReady then
    exit;
  // Update aus Zeitzeuge: es beendet sich gerade selbst, bis zu 60 Sekunden darauf warten
  if WizardSilent then
  begin
    I := 0;
    while ZeitzeugeRunning and (I < 120) do
    begin
      Sleep(500);
      I := I + 1;
    end;
    if ZeitzeugeRunning then
    begin
      Log('Zeitzeuge läuft noch, Update abgebrochen');
      Result := False;  // im stillen Setup: Setup endet, nichts wird geändert
    end;
    exit;
  end;
  // Ein laufendes Zeitzeuge hält Datenbank und Dateien offen: erst selbst beenden lassen,
  // dann speichert es den laufenden Abschnitt sauber
  while ZeitzeugeRunning do
  begin
    if MsgBox('Zeitzeuge läuft noch.' + #13#10#13#10 +
              'Beende es bitte: Rechtsklick auf das Symbol im Infobereich neben der Uhr → Beenden. ' +
              'Klicke danach auf OK.', mbInformation, MB_OKCANCEL) = IDCANCEL then
    begin
      Result := False;
      exit;
    end;
  end;
end;

{ ---------- Installieren ---------- }

procedure BackupData;
var
  Dest: String;
begin
  if not FileExists(DbFile) and not FileExists(ConfigFile) then
    exit;
  Dest := ExpandConstant('{localappdata}\Zeitzeuge\vor-update');
  ForceDirectories(Dest);
  if FileExists(DbFile) then
  begin
    FileCopy(DbFile, Dest + '\zeitzeuge.db', False);
    if FileExists(DbFile + '-wal') then
      FileCopy(DbFile + '-wal', Dest + '\zeitzeuge.db-wal', False)
    else
      DeleteFile(Dest + '\zeitzeuge.db-wal');
  end;
  if FileExists(ConfigFile) then
    FileCopy(ConfigFile, Dest + '\zeitzeuge_config.json', False);
  Log('Daten gesichert nach ' + Dest);
end;

procedure ReplaceOldFiles;
var
  I: Integer;
  Path, Target: String;
begin
  if (OldFiles.Count = 0) or not FoundPage.Values[0] then
    exit;
  Target := ExpandConstant('{app}\ZeitZeuge.exe');
  for I := 0 to OldFiles.Count - 1 do
  begin
    Path := OldFiles[I];
    if CompareText(ExtractFileExt(Path), '.lnk') = 0 then
    begin
      DeleteFile(Path);  // Autostart übernimmt der Run-Eintrag
      continue;
    end;
    if not DeleteFile(Path) then
    begin
      Log('Nicht gelöscht (in Benutzung?): ' + Path);
      continue;
    end;
    // Wo die alte Datei lag, liegt jetzt eine Verknüpfung (gewohnter Platz zum Starten)
    if Pos('\downloads\', Lowercase(Path)) = 0 then
      CreateShellLink(AddBackslash(ExtractFileDir(Path)) + 'Zeitzeuge.lnk', 'Zeitzeuge', Target,
        '', ExpandConstant('{app}'), '', 0, SW_SHOWNORMAL);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
    BackupData
  else if CurStep = ssPostInstall then
  begin
    ReplaceOldFiles;
    // Beim Update aus Zeitzeuge gilt die Einstellung in Zeitzeuge (src/autostart.py)
    if not IsAppUpdate and not WizardIsTaskSelected('autostart') then
      RegDeleteValue(HKCU, RunKey, 'Zeitzeuge');
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Value: String;
begin
  // Daten bleiben stehen; nur den Autostart auf diese Installation entfernen
  if (CurUninstallStep = usUninstall) and RegQueryStringValue(HKCU, RunKey, 'Zeitzeuge', Value) then
    if Pos(Lowercase(ExpandConstant('{app}')), Lowercase(Value)) > 0 then
      RegDeleteValue(HKCU, RunKey, 'Zeitzeuge');
end;

function InitializeUninstall: Boolean;
begin
  Result := True;
  while ZeitzeugeRunning do
    if MsgBox('Zeitzeuge läuft noch. Beende es bitte über das Symbol im Infobereich → Beenden ' +
              'und klicke danach auf OK.', mbInformation, MB_OKCANCEL) = IDCANCEL then
    begin
      Result := False;
      exit;
    end;
end;
