$ErrorActionPreference = "Stop"

$Root = (Resolve-Path "$PSScriptRoot\..\..").Path
$BuildDir = Join-Path $Root "build\windows"
$VenvPython = Join-Path $BuildDir "venv\Scripts\python.exe"
$PyInstaller = Join-Path $BuildDir "venv\Scripts\pyinstaller.exe"
$Spec = Join-Path $Root "packaging\pyinstaller\go2_height_control.spec"
$InstallerScript = Join-Path $Root "packaging\windows\go2-height-control.iss"
$IsccCandidates = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
)

Set-Location $Root
New-Item -ItemType Directory -Force -Path $BuildDir | Out-Null
if (Get-Command py -ErrorAction SilentlyContinue) {
    py -3 -m venv (Join-Path $BuildDir "venv")
} else {
    python -m venv (Join-Path $BuildDir "venv")
}
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r (Join-Path $Root "packaging\requirements-package.txt")
& $PyInstaller --clean --noconfirm $Spec

$Iscc = $IsccCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($Iscc) {
    & $Iscc $InstallerScript
    Write-Host "Built installer under dist\installer"
} else {
    Write-Host "Inno Setup not found. Portable exe folder is ready under dist\go2-height-control"
    Write-Host "Install Inno Setup 6 and rerun this script to produce a setup.exe installer."
}
