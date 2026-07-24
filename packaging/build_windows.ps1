# Napravi notemkr.exe na Windows masini.
#
#     powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
#     powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1 -OneFile
#
# Isto ovo radi i GitHub Actions workflow (.github/workflows/build-windows.yml),
# pa ova skripta sluzi za lokalnu gradnju i proveru.
#
# Rezultat:
#   dist\notemkr\notemkr.exe   (podrazumevano: folder, brz start)
#   dist\notemkr.exe           (-OneFile: jedan fajl, sporiji start)

param(
    [switch]$OneFile,
    [string]$Python = "py"
)

$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")

$venv = ".venv"
$venvPython = Join-Path $venv "Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "== Pravim virtuelno okruzenje ==" -ForegroundColor Cyan
    & $Python -3.11 -m venv $venv
    if (-not (Test-Path $venvPython)) { & $Python -m venv $venv }
}

Write-Host "== Instaliram zavisnosti ==" -ForegroundColor Cyan
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -e ".[build]"
# basic-pitch u metapodacima trazi TensorFlow; nama treba samo ONNX (vidi README).
& $venvPython -m pip install --no-deps "basic-pitch==0.4.0"

Write-Host "== Preuzimam staticki ffmpeg.exe ==" -ForegroundColor Cyan
& $venvPython packaging\fetch_ffmpeg.py --os windows

Write-Host "== PyInstaller ==" -ForegroundColor Cyan
if (Test-Path build) { Remove-Item -Recurse -Force build }
if (Test-Path dist) { Remove-Item -Recurse -Force dist }

if ($OneFile) { $env:NOTEMKR_ONEFILE = "1" } else { Remove-Item Env:\NOTEMKR_ONEFILE -ErrorAction SilentlyContinue }

& $venvPython -m PyInstaller packaging\notemkr.spec --noconfirm --distpath dist --workpath build

Write-Host ""
Write-Host "== Gotovo ==" -ForegroundColor Green
Get-ChildItem dist
