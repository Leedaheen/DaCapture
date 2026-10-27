# DaCapture.exe 빌드 스크립트
# 사용법: PowerShell 에서  .\build.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}
$py = ".\.venv\Scripts\python.exe"
& $py -m pip install -q --upgrade pip
& $py -m pip install -q -r requirements.txt pyinstaller

& $py tools\make_icon.py assets\dacapture.ico
& $py -m PyInstaller --noconfirm --clean DaCapture.spec

Write-Host ""
Write-Host "완료: dist\DaCapture.exe"
