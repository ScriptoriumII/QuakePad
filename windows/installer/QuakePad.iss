; Installateur QuakePad (Inno Setup 6)
; Compilation : iscc /DAppVersion=1.7.0 installer\QuakePad.iss   (depuis le dossier windows\)
; Fichier en UTF-8 avec BOM (requis par Inno Setup 6 pour les accents).
; Entrée attendue : dist\QuakePad\ (PyInstaller --onedir)
;
; Installation par utilisateur, sans droits administrateur :
;   %LOCALAPPDATA%\Programs\QuakePad ; associations de fichiers dans HKCU\Software\Classes.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "QuakePad"
#define AppExe "QuakePad.exe"
#define AppPublisher "ScriptoriumII"
#define AppURL "https://github.com/ScriptoriumII/QuakePad"
#define ProgId "QuakePad.Document"

[Setup]
; AppId fixe : ne jamais le changer (sert à reconnaître l'installation lors des mises à jour)
AppId={{FC76ACDF-FF40-5E56-A4AB-481159A712F0}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=QuakePad-Setup-{#AppVersion}
SetupIconFile=..\assets\quakepad.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
MinVersion=10.0
ChangesAssociations=yes
; Ferme QuakePad s'il tourne (mutex créé par l'application + Gestionnaire de redémarrage Windows)
AppMutex=ScriptoriumII.QuakePad.Running
CloseApplications=force
RestartApplications=no
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#AppName}
VersionInfoDescription={#AppName} — bloc-notes déroulant façon Quake

[Languages]
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "Créer une icône sur le Bureau"; GroupDescription: "Raccourcis :"; Flags: unchecked
Name: "assoc_txt"; Description: "Proposer QuakePad pour ouvrir les fichiers .txt"; GroupDescription: "Associations de fichiers :"
Name: "assoc_md"; Description: "… les fichiers .md (Markdown)"; GroupDescription: "Associations de fichiers :"; Flags: unchecked
Name: "assoc_log"; Description: "… les fichiers .log"; GroupDescription: "Associations de fichiers :"; Flags: unchecked
Name: "autostart"; Description: "Lancer QuakePad au démarrage de Windows"; GroupDescription: "Démarrage :"; Flags: unchecked

[Files]
Source: "..\dist\QuakePad\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Fichiers d'une version précédente qui n'existeraient plus (évite les mélanges de bibliothèques)
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; Comment: "Bloc-notes déroulant façon Quake"
Name: "{group}\Désinstaller {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; --- Type de document « QuakePad » (ProgID)
Root: HKA; Subkey: "Software\Classes\{#ProgId}"; ValueType: string; ValueData: "Document texte (QuakePad)"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\{#ProgId}\DefaultIcon"; ValueType: string; ValueData: "{app}\{#AppExe},0"
Root: HKA; Subkey: "Software\Classes\{#ProgId}\shell\open\command"; ValueType: string; ValueData: """{app}\{#AppExe}"" ""%1"""
; --- « Ouvrir avec » : QuakePad apparaît dans la liste pour .txt / .md / .log
Root: HKA; Subkey: "Software\Classes\.txt\OpenWithProgids"; ValueType: string; ValueName: "{#ProgId}"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc_txt
Root: HKA; Subkey: "Software\Classes\.md\OpenWithProgids"; ValueType: string; ValueName: "{#ProgId}"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc_md
Root: HKA; Subkey: "Software\Classes\.log\OpenWithProgids"; ValueType: string; ValueName: "{#ProgId}"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc_log
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "{#AppName}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\shell\open\command"; ValueType: string; ValueData: """{app}\{#AppExe}"" ""%1"""
; --- « Applications par défaut » de Windows (Paramètres) : déclaration des capacités
Root: HKA; Subkey: "Software\{#AppPublisher}\{#AppName}\Capabilities"; ValueType: string; ValueName: "ApplicationName"; ValueData: "{#AppName}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\{#AppPublisher}\{#AppName}\Capabilities"; ValueType: string; ValueName: "ApplicationDescription"; ValueData: "Bloc-notes déroulant façon Quake"
Root: HKA; Subkey: "Software\{#AppPublisher}\{#AppName}\Capabilities\FileAssociations"; ValueType: string; ValueName: ".txt"; ValueData: "{#ProgId}"; Tasks: assoc_txt
Root: HKA; Subkey: "Software\{#AppPublisher}\{#AppName}\Capabilities\FileAssociations"; ValueType: string; ValueName: ".md"; ValueData: "{#ProgId}"; Tasks: assoc_md
Root: HKA; Subkey: "Software\{#AppPublisher}\{#AppName}\Capabilities\FileAssociations"; ValueType: string; ValueName: ".log"; ValueData: "{#ProgId}"; Tasks: assoc_log
Root: HKA; Subkey: "Software\RegisteredApplications"; ValueType: string; ValueName: "{#AppName}"; ValueData: "Software\{#AppPublisher}\{#AppName}\Capabilities"; Flags: uninsdeletevalue
; --- Démarrage avec Windows (option) ; valeur toujours retirée à la désinstallation
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#AppName}"; ValueData: """{app}\{#AppExe}"" --hidden"; Flags: uninsdeletevalue; Tasks: autostart
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueName: "{#AppName}"; Flags: uninsdeletevalue dontcreatekey

[Run]
; Windows interdit aux programmes de s'imposer comme application par défaut : on ouvre la page
; des paramètres où l'utilisateur choisit QuakePad en un clic.
Filename: "ms-settings:defaultapps?registeredAppUser={#AppName}"; Description: "Choisir QuakePad comme application par défaut pour les fichiers .txt"; Flags: postinstall shellexec skipifsilent unchecked; Tasks: assoc_txt
Filename: "{app}\{#AppExe}"; Description: "Lancer QuakePad"; Flags: nowait postinstall skipifsilent
; Mise à jour automatique (installation silencieuse) : relance QuakePad
Filename: "{app}\{#AppExe}"; Flags: nowait; Check: WizardSilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

[Messages]
fr.FinishedLabel=QuakePad est installé. Appuyez sur Alt+² (touche sous Échap) pour l'afficher ou le masquer. Vos notes et paramètres sont conservés dans le dossier AppData\Roaming\QuakePad de votre profil.
