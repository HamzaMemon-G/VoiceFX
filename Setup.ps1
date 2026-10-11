param([switch]$AI)
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    if (-not (Test-Path '.venv/Scripts/python.exe')) {
        & py -3.12 -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.12 first.' }
    }
    & .venv/Scripts/python.exe -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
    if ((Get-Command g++ -ErrorAction SilentlyContinue) -and ((& g++ -dumpmachine) -match 'x86_64')) {
        & g++ -std=c++11 -O2 -s -shared -static-libgcc -static-libstdc++ native/dsp.cpp -o native/voicefx.dll
    } elseif (Get-Command zig -ErrorAction SilentlyContinue) {
        & zig c++ -target x86_64-windows-gnu -O2 -s -shared native/dsp.cpp -o native/voicefx.dll
    } else { throw 'Add a 64-bit MinGW g++ compiler or Zig to PATH.' }
    if ($LASTEXITCODE -ne 0) { throw 'Native DSP build failed' }
    if ($AI) {
        & .venv/Scripts/python.exe -m pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu
        if ($LASTEXITCODE -ne 0) { throw 'CPU AI installation failed' }
        & .venv/Scripts/python.exe app/download_models.py
        if ($LASTEXITCODE -ne 0) { throw 'Model download failed' }
    }
} finally { Pop-Location }
