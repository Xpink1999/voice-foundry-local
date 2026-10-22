$ErrorActionPreference = 'Stop'
$PlatformRoot = Split-Path $PSScriptRoot -Parent
$BackupDir = Join-Path $PlatformRoot ('data/backups/global-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
$UserPathBefore = [Environment]::GetEnvironmentVariable('Path', 'User')
Set-Content -LiteralPath (Join-Path $BackupDir 'user-path.txt') -Value $UserPathBefore -Encoding utf8
$GlobalConfig = Join-Path $env:USERPROFILE '.codex/config.toml'
if (Test-Path -LiteralPath $GlobalConfig) {
    Copy-Item -LiteralPath $GlobalConfig -Destination (Join-Path $BackupDir 'codex-config.toml')
}
$BinDir = Join-Path $PlatformRoot 'bin'
$Entries = @($UserPathBefore -split ';' | Where-Object { $_ -and $_.TrimEnd('\') -ne $BinDir.TrimEnd('\') })
[Environment]::SetEnvironmentVariable('Path', (($Entries + $BinDir) -join ';'), 'User')
$env:Path = $env:Path + ';' + $BinDir
$PythonExe = Join-Path $PlatformRoot '.venv/Scripts/python.exe'
codex mcp add voice-foundry -- $PythonExe -m voice_platform.mcp_server
if ($LASTEXITCODE -ne 0) { throw 'Codex MCP registration failed; backup retained' }
codex mcp get voice-foundry --json
Write-Output "Global integration backup: $BackupDir"
Write-Output 'New terminals inherit the user PATH; restart Codex to discover the new MCP tools.'
