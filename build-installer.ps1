# Build PromptMate.exe and the Windows installer.
# Usage:  powershell -ExecutionPolicy Bypass -File build-installer.ps1
# Output: installer\PromptMate-Setup-<version>.exe

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
$pyinstaller = "$env:LOCALAPPDATA\Programs\Python\Python312\Scripts\pyinstaller.exe"
$iscc = "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $iscc)) { $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" }

Write-Host "== 1/3 Running tests =="
& $python test_logic.py | Out-Null
& $python test_gui.py | Select-Object -Last 1
& $python test_pet.py | Select-Object -Last 1

Write-Host "== 2/3 Building PromptMate.exe (PyInstaller) =="
& $pyinstaller --noconfirm --clean --windowed --name PromptMate `
    --icon assets\promptmate.ico `
    --add-data "assets\kogi\spritesheet.png;assets\kogi" `
    --add-data "assets\kogi\manifest.json;assets\kogi" `
    promptmate.py | Out-Null

Write-Host "== 3/3 Compiling installer (Inno Setup) =="
& $iscc installer.iss | Select-Object -Last 2

Write-Host "Done. Silent install:  installer\PromptMate-Setup-*.exe /VERYSILENT /NORESTART"
