; 土衡 / SoilFauna Measure — Windows 安装器脚本 (Inno Setup 6)
;
; 依赖：先完成 onedir 打包，使 dist\SoilFaunaMeasure\ 存在。
; 编译：
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" scripts\installer\SoilFaunaMeasure.iss
; 或：
;   python scripts\build_windows.py --installer
;
; 安装包会：选择路径 → 释放 exe + _internal 等 → 开始菜单/桌面快捷方式。
; 运行时仍是 onedir 结构，启动速度快。

#define MyAppName "土衡 SoilFauna Measure"
#define MyAppNameEn "SoilFaunaMeasure"
#define MyAppVersion "0.8.0"
#define MyAppPublisher "SoilFauna Measure"
#define MyAppURL "https://github.com/"
#define MyAppExeName "SoilFaunaMeasure.exe"

; 路径相对于本 .iss 所在目录 (scripts/installer/)
#define DistDir "..\..\dist\SoilFaunaMeasure"
#define IconFile "..\..\src\soilfauna_measure\resources\icons\app_icon.ico"
#define OutputDir "..\..\dist"

[Setup]
; 固定 AppId，升级时识别为同一应用（勿随意改）
AppId={{8F3E2A91-5C4B-4D6E-9F1A-2B3C4D5E6F70}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppNameEn}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; 允许用户自由选择安装目录
AllowNoIcons=yes
LicenseFile=
InfoBeforeFile=
OutputDir={#OutputDir}
OutputBaseFilename=SoilFaunaMeasure-Setup-{#MyAppVersion}
SetupIconFile={#IconFile}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
; 默认装到 Program Files 需管理员；用户也可改到无管理员权限的目录
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
VersionInfoVersion={#MyAppVersion}
VersionInfoProductName={#MyAppName}
CloseApplications=yes
RestartApplications=no
; 显示「浏览」选路径
DisableDirPage=no
UsePreviousAppDir=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
; 若本机 Inno 带有简体中文语言包则启用（没有也不影响英文向导）
#if FileExists(CompilerPath + "Languages\ChineseSimplified.isl")
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
#endif

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加图标:"; Flags: checkedonce
Name: "quicklaunchicon"; Description: "创建快速启动栏图标"; GroupDescription: "附加图标:"; Flags: unchecked; OnlyBelowVersion: 6.1; Check: not IsAdminInstallMode

[Files]
; 释放整个 onedir 包（exe + _internal + 说明文档）
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即运行 {#MyAppName}"; Flags: nowait postinstall skipifsilent; WorkingDir: "{app}"

[UninstallDelete]
; 可选：清理用户可能在安装目录里生成的缓存（谨慎，仅删已知子目录）
; Type: filesandordirs; Name: "{app}\logs"
