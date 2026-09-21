[CmdletBinding()]
param(
    [string]$InstallRoot = $(if ($env:XIGE_SCREEN_HOME) { $env:XIGE_SCREEN_HOME } else { Join-Path $env:LOCALAPPDATA 'xige_screen' }),
    [ValidateSet('auto','cuda','cpu')][string]$Device = 'auto',
    [string]$ModelCache = '',
    [string]$SkillDir = '',
    [switch]$NoSkillInstall,
    [switch]$SkipVoiceTest
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONNOUSERSITE = '1'
$env:PYTHONPATH = ''
$env:UV_NO_CONFIG = '1'
$env:UV_PYTHON_PREFERENCE = 'only-managed'
$env:UV_HTTP_TIMEOUT = '120'
$env:UV_LINK_MODE = 'copy'
$PackageRoot = Split-Path -Parent $PSScriptRoot
function Get-Sha256([string]$Path) {
    $Hasher = [Security.Cryptography.SHA256]::Create()
    $Stream = [IO.File]::OpenRead($Path)
    try { return ([BitConverter]::ToString($Hasher.ComputeHash($Stream))).Replace('-','').ToLowerInvariant() }
    finally { $Stream.Dispose(); $Hasher.Dispose() }
}
try {
    if (-not [Environment]::Is64BitOperatingSystem -or $env:PROCESSOR_ARCHITECTURE -eq 'ARM64') {
        throw 'This package requires Windows x64. ARM64 is not supported by this build.'
    }
    $InstallRoot = [IO.Path]::GetFullPath($InstallRoot)
    New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
    $LogDir = Join-Path $InstallRoot 'logs'
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
    Start-Transcript -Path (Join-Path $LogDir 'install.log') -Append | Out-Null
    Write-Host 'xige_screen - Windows setup'
    Write-Host "Runtime: $InstallRoot"
    Write-Host 'First setup downloads Python, inference libraries and approximately 7 GB of model weights.'
    Write-Host 'Downloads are verified and can resume. No system Python, Git, CUDA toolkit or administrator account is required.'
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $InstallRoot 'python'
    $env:UV_PYTHON_BIN_DIR = Join-Path $InstallRoot 'tools/python-bin'
    $env:UV_CACHE_DIR = Join-Path $InstallRoot 'download-cache/uv'
    $ToolDir = Join-Path $InstallRoot 'tools'
    New-Item -ItemType Directory -Force -Path $ToolDir | Out-Null
    $Uv = Join-Path $ToolDir 'uv.exe'
    $UvZip = Join-Path $ToolDir 'uv-0.12.17.zip'
    $Expected = 'a252121d5b59398fcb137c6ea448176459a44010f33f67e0072305a637119ca7'
    if (-not (Test-Path -LiteralPath $UvZip) -or (Get-Sha256 $UvZip) -ne $Expected) {
        Write-Host '[1/5] Downloading verified uv runtime manager...'
        Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/astral-sh/uv/releases/download/0.12.17/uv-x86_64-pc-windows-msvc.zip' -OutFile $UvZip
    }
    if ((Get-Sha256 $UvZip) -ne $Expected) { throw 'uv download checksum mismatch. Run setup again.' }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $Archive = [IO.Compression.ZipFile]::OpenRead($UvZip)
    try {
        foreach ($Entry in $Archive.Entries) {
            if ($Entry.FullName -eq 'uv.exe' -or $Entry.FullName -eq 'uvx.exe') {
                [IO.Compression.ZipFileExtensions]::ExtractToFile($Entry, (Join-Path $ToolDir $Entry.Name), $true)
            }
        }
    } finally { $Archive.Dispose() }
    if (-not (Test-Path -LiteralPath $Uv)) { throw 'Verified uv archive did not contain uv.exe.' }
    Write-Host '[2/5] Installing isolated Python 3.11...'
    & $Uv python install 3.11.15
    if ($LASTEXITCODE -ne 0) { throw 'Python download failed. Check the network and run Install.cmd again.' }
    $Venv = Join-Path $InstallRoot 'env'
    $Python = Join-Path $Venv 'Scripts/python.exe'
    if (-not (Test-Path -LiteralPath $Python)) {
        & $Uv venv --python 3.11.15 $Venv
        if ($LASTEXITCODE -ne 0) { throw 'Creating the isolated Python environment failed.' }
    }
    $SetupArgs = @((Join-Path $PSScriptRoot 'windows_setup.py'), '--root', $InstallRoot, '--package', $PackageRoot, '--device', $Device)
    if ($ModelCache) { $SetupArgs += @('--model-cache', $ModelCache) }
    if ($SkillDir) { $SetupArgs += @('--skill-dir', $SkillDir) }
    if ($NoSkillInstall) { $SetupArgs += '--no-skill-install' }
    if ($SkipVoiceTest) { $SetupArgs += '--skip-voice-test' }
    & $Python @SetupArgs
    if ($LASTEXITCODE -ne 0) { throw "Setup did not complete (exit $LASTEXITCODE). The log is in $LogDir. Run the same command to resume." }
    Write-Host 'Setup completed. Double-click Run.cmd for status and usage.' -ForegroundColor Green
    Stop-Transcript | Out-Null
    exit 0
} catch {
    Write-Host "SETUP FAILED: $($_.Exception.Message)" -ForegroundColor Red
    try { Stop-Transcript | Out-Null } catch {}
    exit 1
}
