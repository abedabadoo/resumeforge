@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv || goto :failed
)
".venv\Scripts\python.exe" -c "import reportlab, pdfplumber, pydantic, pypdf, docx" 2>nul
if errorlevel 1 ".venv\Scripts\python.exe" -m pip install --only-binary=:all: . || goto :failed
".venv\Scripts\python.exe" -m resumeforge serve --port 8766 --open
exit /b %errorlevel%
:failed
echo Install a supported 64-bit Python and check the setup error above.
pause
exit /b 1
