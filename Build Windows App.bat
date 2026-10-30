@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -m pip install "pyinstaller>=6,<7"
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m PyInstaller --noconfirm "SFX Vault.spec"
pause
