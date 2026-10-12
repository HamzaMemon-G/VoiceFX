$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    & .venv/Scripts/python.exe -m pip install -r build-requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Build dependency installation failed' }
    & .venv/Scripts/python.exe -m PyInstaller --noconfirm --clean --windowed --onedir --name VoiceFX --paths app --add-data 'vendor;vendor' --add-data 'models/beatrice;models/beatrice' --add-data 'native/voicefx.dll;native' --add-data 'LICENSE;.' --add-data 'THIRD-PARTY.md;.' --hidden-import engine --hidden-import character --hidden-import model --hidden-import cached_convnet --hidden-import positional_encoding --hidden-import pedalboard --paths vendor/LLVC --paths vendor --hidden-import stftpitchshift.cepster --hidden-import stftpitchshift.pitcher --hidden-import stftpitchshift.resampler app/main.py
    if ($LASTEXITCODE -ne 0) { throw 'Packaging failed' }
    & .venv/Scripts/python.exe app/package_notices.py
    if ($LASTEXITCODE -ne 0) { throw 'License collection failed' }
} finally { Pop-Location }
