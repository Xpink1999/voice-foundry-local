param([switch]$SkipModels, [switch]$NoStart)
$ErrorActionPreference = 'Stop'
$PlatformRoot = Split-Path $PSScriptRoot -Parent
Push-Location $PlatformRoot
try {
    foreach ($Command in @('uv', 'git')) {
        if (-not (Get-Command $Command -ErrorAction SilentlyContinue)) { throw "Install prerequisite first: $Command" }
    }
    Write-Host 'Platform: Apache-2.0. Dependencies/models: THIRD_PARTY_NOTICES.md and LICENSES/.'
    Write-Host 'Downloads come from upstream. No recordings or user database are included.'
    if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) { Write-Warning 'FFmpeg is optional; install separately for encoded exports and advanced audio processing.' }
    $env:UV_CACHE_DIR = Join-Path $PlatformRoot 'runtime/uv-cache'
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $PlatformRoot 'runtime/python'
    uv python install --no-bin --no-registry 3.11.16
    if ($LASTEXITCODE -ne 0) { throw 'Python installation failed' }
    if (-not (Test-Path '.venv/Scripts/python.exe')) {
        uv venv --python 3.11.16 .venv
        if ($LASTEXITCODE -ne 0) { throw 'venv creation failed' }
    }
    if (-not $SkipModels) {
    if (-not (Test-Path 'vendor/VoxCPM/.git')) {
        git clone https://github.com/OpenBMB/VoxCPM.git vendor/VoxCPM
        if ($LASTEXITCODE -ne 0) { throw 'Official source clone failed' }
    }
    git -C vendor/VoxCPM checkout cce58a5b59303c9bd63d12f23afe6a49a4a80c59
    if ($LASTEXITCODE -ne 0) { throw 'Official source checkout failed' }
    if (-not (Test-Path 'vendor/Resemblyzer/.git')) {
        git clone https://github.com/resemble-ai/Resemblyzer.git vendor/Resemblyzer
        if ($LASTEXITCODE -ne 0) { throw 'Speaker encoder source clone failed' }
    }
    git -C vendor/Resemblyzer checkout 15d828edebe06bc72b9cabc8ef8ca5ab2cb457ce
    if ($LASTEXITCODE -ne 0) { throw 'Speaker encoder source checkout failed' }
    }
    uv pip install --python .venv/Scripts/python.exe torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu128
    if ($LASTEXITCODE -ne 0) { throw 'CUDA runtime installation failed' }
    $RequirementsFile = if (Test-Path 'requirements.lock.txt') { 'requirements.lock.txt' } else { 'requirements-inference.txt' }
    uv pip install --python .venv/Scripts/python.exe -r $RequirementsFile --editable .
    if ($LASTEXITCODE -ne 0) { throw 'Service dependencies failed' }
    if (-not $SkipModels) {
    & .venv/Scripts/python.exe scripts/download_model.py
    if ($LASTEXITCODE -ne 0) { throw 'Model verification failed' }
    & .venv/Scripts/python.exe scripts/download_reference_models.py
    if ($LASTEXITCODE -ne 0) { throw 'Reference preprocessing models failed' }
    & .venv/Scripts/python.exe scripts/fetch_processing_sources.py
    if ($LASTEXITCODE -ne 0) { throw 'Audio processing source setup failed' }
    & .venv/Scripts/python.exe scripts/download_processing_models.py
    if ($LASTEXITCODE -ne 0) { throw 'Audio processing model verification failed' }
    }
    uv pip check --python .venv/Scripts/python.exe
    if ($LASTEXITCODE -ne 0) { throw 'Dependency check failed' }
    & .venv/Scripts/python.exe -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'Core tests failed' }
    if (-not $NoStart) { & .venv/Scripts/voice.exe start }
} finally { Pop-Location }
