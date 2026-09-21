# Forward arguments without asking Windows to parse user text as shell code.
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONNOUSERSITE = '1'
$env:PYTHONPATH = ''
$PackageRoot = Split-Path -Parent $PSScriptRoot
$RuntimeFile = Join-Path $PackageRoot 'runtime.json'
if (Test-Path -LiteralPath $RuntimeFile) {
    $Root = (Get-Content -LiteralPath $RuntimeFile -Raw -Encoding UTF8 | ConvertFrom-Json).root
} elseif ($env:XIGE_SCREEN_HOME) {
    $Root = $env:XIGE_SCREEN_HOME
} else {
    $Root = Join-Path $env:LOCALAPPDATA 'xige_screen'
}
$Python = Join-Path $Root 'env/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $Python) -or -not (Test-Path -LiteralPath (Join-Path $Root 'installation.json'))) {
    Write-Host 'First use: automatically installing the local voice runtime. Existing verified downloads will be reused.'
    $AutoDevice = 'auto'
    $ResumeArgs = @()
    $BackendFile = Join-Path $Root 'backend.json'
    if (Test-Path -LiteralPath $BackendFile) {
        $PreviousBackend = Get-Content -LiteralPath $BackendFile -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($PreviousBackend.device -eq 'cpu') { $AutoDevice = 'cpu' }
        if ($PreviousBackend.model_dir) { $ResumeArgs += @('-ModelCache', $PreviousBackend.model_dir) }
    }
    & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'install_windows.ps1') -InstallRoot $Root -Device $AutoDevice @ResumeArgs
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
& $Python (Join-Path $PSScriptRoot 'windows_run.py') --root $Root @args
exit $LASTEXITCODE
