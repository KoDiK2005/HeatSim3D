; ============================================================
;  HeatSim3D — Inno Setup Script
;  Создаёт установщик HeatSim3D_Setup.exe
; ============================================================

#define AppName "HeatSim3D"
#define AppVersion "1.0"
#define AppPublisher "HeatSim3D"
#define AppExeName "HeatSim3D.exe"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputDir=installer
OutputBaseFilename=HeatSim3D_Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
; Иконка установщика (если есть)
; SetupIconFile=icon.ico

; Требует прав администратора для установки в Program Files
PrivilegesRequired=admin

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
; Значок на рабочем столе
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; \
    GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Главный exe (собранный PyInstaller)
Source: "dist\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Ярлык в меню Пуск
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Удалить {#AppName}"; Filename: "{uninstallexe}"

; Ярлык на рабочем столе (если выбрано)
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; \
    Tasks: desktopicon

[Run]
; Запустить программу после установки
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; \
    Flags: nowait postinstall skipifsilent
