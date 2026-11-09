Unicode true
RequestExecutionLevel user
SetCompressor /SOLID lzma
Name "ResumeForge"
OutFile "${OUT_FILE}"
InstallDir "$LOCALAPPDATA\Programs\ResumeForge"
InstallDirRegKey HKCU "Software\ResumeForge" "InstallDir"
!include "LogicLib.nsh"
!include "MUI2.nsh"
!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\ResumeForge.exe"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Section "Install"
    SetShellVarContext current
    ; Only use an empty directory or a prior ResumeForge install.
    IfFileExists "$INSTDIR\.resumeforge-install" ready
    IfFileExists "$INSTDIR\*.*" 0 ready
    ClearErrors
    FindFirst $0 $1 "$INSTDIR\*"
    ${DoUntil} ${Errors}
        ${If} $1 != "."
        ${AndIf} $1 != ".."
            FindClose $0
            MessageBox MB_OK|MB_ICONSTOP "Choose an empty folder for ResumeForge." /SD IDOK
            SetErrorLevel 2
            Abort
        ${EndIf}
        FindNext $0 $1
    ${Loop}
    FindClose $0
ready:
    SetOutPath "$INSTDIR"
    File /r "${STAGE_FILES}"
    FileOpen $0 "$INSTDIR\.resumeforge-install" w
    FileWrite $0 "ResumeForge desktop"
    FileClose $0
    WriteUninstaller "$INSTDIR\Uninstall.exe"
    CreateShortcut "$SMPROGRAMS\ResumeForge.lnk" "$INSTDIR\ResumeForge.exe"
    WriteRegStr HKCU "Software\ResumeForge" "InstallDir" "$INSTDIR"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ResumeForge" "DisplayName" "ResumeForge"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ResumeForge" "DisplayVersion" "0.4.0"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ResumeForge" "DisplayIcon" "$INSTDIR\ResumeForge.exe"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ResumeForge" "UninstallString" '"$INSTDIR\Uninstall.exe"'
    WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ResumeForge" "NoModify" 1
    WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ResumeForge" "NoRepair" 1
SectionEnd

Section "Uninstall"
    SetShellVarContext current
    IfFileExists "$INSTDIR\.resumeforge-install" 0 done
    Delete "$SMPROGRAMS\ResumeForge.lnk"
    DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ResumeForge"
    DeleteRegKey HKCU "Software\ResumeForge"
    RMDir /r "$INSTDIR\runtime"
    Delete "$INSTDIR\ResumeForge.exe"
    Delete "$INSTDIR\.resumeforge-install"
    Delete "$INSTDIR\Uninstall.exe"
    RMDir "$INSTDIR"
done:
SectionEnd
