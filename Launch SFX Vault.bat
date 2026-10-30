@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Please follow the installation instructions in README.md first.
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" -m sfx_vault
