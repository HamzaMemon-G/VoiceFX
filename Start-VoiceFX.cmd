@echo off
cd /d "%~dp0"
if exist "dist\VoiceFX\VoiceFX.exe" (
    start "" "dist\VoiceFX\VoiceFX.exe"
) else if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" "app\main.py"
) else (
    echo Run Setup.ps1 first, or download the Windows release.
    pause
)
