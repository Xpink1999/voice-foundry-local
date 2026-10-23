param([switch]$CoreOnly, [switch]$SkipModels, [switch]$NoStart)
$ErrorActionPreference = 'Stop'
$PlatformRoot = Split-Path $PSScriptRoot -Parent
$EnvironmentNames = @('UV_CACHE_DIR','UV_DATA_DIR','UV_PYTHON_INSTALL_DIR','UV_PYTHON_BIN_DIR','PYTHONPATH','PYTHONHOME','PYTHONNOUSERSITE','VIRTUAL_ENV','VOICE_PLATFORM_CONFIG','VOICE_PLATFORM_URL','TEMP','TMP','UV_HTTP_TIMEOUT','UV_HTTP_RETRIES')
$Before = @{}
foreach ($Name in $EnvironmentNames) { $Before[$Name] = [Environment]::GetEnvironmentVariable($Name, 'Process') }
function Invoke-Checked([string]$Program, [string[]]$Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed (exit $LASTEXITCODE). See runtime/install.log; fix the reported step and run this installer again." }
}
Push-Location $PlatformRoot
$TranscriptStarted = $false
try {
    if ($env:OS -ne 'Windows_NT' -or ($env:PROCESSOR_ARCHITECTURE -ne 'AMD64' -and $env:PROCESSOR_ARCHITEW6432 -ne 'AMD64')) { throw 'This installer requires Windows x64. Other platforms are not supported by this installation profile.' }
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw 'Install uv first: https://docs.astral.sh/uv/getting-started/installation/ . Then reopen PowerShell.' }
    if (-not $CoreOnly -and -not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'Install Git for Windows first: https://git-scm.com/download/win . Then reopen PowerShell.' }
    New-Item -ItemType Directory -Force -Path 'runtime/tmp' | Out-Null
    Start-Transcript -LiteralPath (Join-Path $PlatformRoot 'runtime/install.log') -Append | Out-Null
    $TranscriptStarted = $true
    Write-Host 'Voice Foundry installation. No administrator access or global Python is required.'
    Write-Host 'Models and dependencies keep their own licenses: THIRD_PARTY_NOTICES.md and LICENSES/.'
    foreach ($Name in @('PYTHONPATH','PYTHONHOME','VIRTUAL_ENV','VOICE_PLATFORM_CONFIG','VOICE_PLATFORM_URL')) { [Environment]::SetEnvironmentVariable($Name, $null, 'Process') }
    $env:PYTHONNOUSERSITE = '1'
    $env:UV_HTTP_TIMEOUT = '600'
    $env:UV_HTTP_RETRIES = '5'
    $env:UV_CACHE_DIR = Join-Path $PlatformRoot 'runtime/uv-cache'
    $env:UV_DATA_DIR = Join-Path $PlatformRoot 'runtime/uv-data'
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $PlatformRoot 'runtime/python'
    $env:UV_PYTHON_BIN_DIR = Join-Path $PlatformRoot 'runtime/python-bin'
    $env:TEMP = Join-Path $PlatformRoot 'runtime/tmp'
    $env:TMP = $env:TEMP
    $ManagedPython = Join-Path $env:UV_PYTHON_INSTALL_DIR 'cpython-3.11.16-windows-x86_64-none/python.exe'
    & uv --no-config python install --no-bin --no-registry 3.11.16
    if ($LASTEXITCODE -ne 0) {
        # Some restricted Windows accounts cannot create uv's minor-version junction.
        # A completed runtime is usable by its exact path; never fall back to PATH Python.
        if (-not (Test-Path -LiteralPath $ManagedPython)) { throw 'Project-local Python download failed. Check runtime/install.log and retry.' }
        Write-Warning 'uv did not complete registration. Checking the downloaded interpreter directly.'
    }
    Invoke-Checked $ManagedPython @('-I','-c','import sys, ssl, sqlite3, venv; assert sys.version_info[:3] == (3,11,16); print(sys.version)')
    $Python = Join-Path $PlatformRoot '.venv/Scripts/python.exe'
    if (-not (Test-Path -LiteralPath $Python)) { Invoke-Checked 'uv' @('--no-config','venv','--python',$ManagedPython,'.venv') }
    Invoke-Checked $Python @('-I','-c','import sys,pathlib; assert sys.version_info[:3] == (3,11,16); assert pathlib.Path(sys.base_prefix).resolve() == pathlib.Path(sys.argv[1]).resolve(), ''Existing .venv belongs to another Python; preserve your data and rename .venv before reinstalling.''', (Split-Path $ManagedPython -Parent))
    if ($CoreOnly) {
        Invoke-Checked 'uv' @('--no-config','pip','install','--python',$Python,'--constraint','requirements.lock.txt','--editable','.','pytest','opencc-python-reimplemented')
    } else {
        foreach ($Source in @(@('https://github.com/OpenBMB/VoxCPM.git','vendor/VoxCPM','cce58a5b59303c9bd63d12f23afe6a49a4a80c59'), @('https://github.com/resemble-ai/Resemblyzer.git','vendor/Resemblyzer','15d828edebe06bc72b9cabc8ef8ca5ab2cb457ce'))) {
            if (-not (Test-Path (Join-Path $Source[1] '.git'))) { Invoke-Checked 'git' @('clone',$Source[0],$Source[1]) }
            Invoke-Checked 'git' @('-C',$Source[1],'checkout','--detach',$Source[2])
        }
        Invoke-Checked 'uv' @('--no-config','pip','install','--python',$Python,'--requirement','requirements-cuda.txt','--constraint','requirements.lock.txt')
        Invoke-Checked 'uv' @('--no-config','pip','install','--python',$Python,'--requirement','requirements.lock.txt','--editable','.')
        Invoke-Checked $Python @('scripts/fetch_processing_sources.py')
        if (-not $SkipModels) {
            foreach ($Script in @('download_model.py','download_reference_models.py','download_processing_models.py')) { Invoke-Checked $Python @("scripts/$Script") }
        }
    }
    Invoke-Checked 'uv' @('--no-config','pip','check','--python',$Python)
    $CheckArguments = @('scripts/check_install.py','--profile',$(if ($CoreOnly) {'core'} else {'inference'}))
    if (-not $CoreOnly -and -not $SkipModels) { $CheckArguments += '--models' }
    Invoke-Checked $Python $CheckArguments
    $TestDirectory = 'runtime/pytest-install-' + [guid]::NewGuid().ToString('N')
    Invoke-Checked $Python @('-m','pytest','-q','--basetemp',$TestDirectory)
    if ($CoreOnly -or $SkipModels) { Write-Warning 'Model weights were not installed. The interface can be inspected, but speech generation is not ready.' }
    if (-not $NoStart) { Invoke-Checked $Python @('-m','voice_platform.cli','start') }
    Write-Host 'Installation checks passed. Use start-voice.cmd to open the interface.'
} finally {
    if ($TranscriptStarted) { Stop-Transcript | Out-Null }
    foreach ($Name in $EnvironmentNames) { [Environment]::SetEnvironmentVariable($Name, $Before[$Name], 'Process') }
    Pop-Location
}
