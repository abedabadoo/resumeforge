#!/bin/zsh
set -eu
APP_DIR="${0:A:h}"
RF_RUNTIME="${HOME}/Library/Application Support/ResumeForge/venv"
if [[ ! -x "$RF_RUNTIME/bin/python" ]]; then
  echo "Setting up ResumeForge's separate Python environment. No AI model is downloaded."
  python3 -m venv "$RF_RUNTIME"
fi
if ! "$RF_RUNTIME/bin/python" -c 'import reportlab, pdfplumber, pypdf, pydantic, docx' 2>/dev/null; then
  "$RF_RUNTIME/bin/python" -m pip install --only-binary=:all: "$APP_DIR"
fi
cd "$APP_DIR"
exec "$RF_RUNTIME/bin/python" -m resumeforge serve --port 8766 --open
