@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  py -3 -m venv .venv || goto :failed
)
".venv\Scripts\python.exe" -c "import PySide6.QtWidgets, pypdfium2, pydantic, reportlab, pypdf, pdfplumber, docx" >nul 2>nul
if errorlevel 1 (
  ".venv\Scripts\python.exe" -m pip install --only-binary=:all: ".[desktop]" || goto :failed
)
start "ResumeForge" ".venv\Scripts\pythonw.exe" -m resumeforge.desktop
exit /b 0
:failed
echo For an installation with Python included, run ResumeForge-Setup-x64.exe.
pause
exit /b 1
