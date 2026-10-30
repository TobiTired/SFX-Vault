@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" tools\build_release.py --repository TobiTired/SFX-Vault
pause
