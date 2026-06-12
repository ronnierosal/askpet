# Build PromptMate.exe and the Windows installer.
# Usage:  powershell -ExecutionPolicy Bypass -File build-installer.ps1
# Output: installer\PromptMate-Setup-<version>.exe
#
# Code signing: if a code-signing cert is present (e.g. on a YubiKey),
# both the app exe and the installer are signed. Expect PIN prompts.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
$pyinstaller = "$env:LOCALAPPDATA\Programs\Python\Python312\Scripts\pyinstaller.exe"
$iscc = "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $iscc)) { $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" }

# Optional code signing (YubiKey/SSL.com): auto-detected, skipped if absent.
$signtool = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin" -Recurse -Filter signtool.exe -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -like '*x64*' } | Select-Object -Last 1 -ExpandProperty FullName
$cert = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert -ErrorAction SilentlyContinue | Select-Object -First 1
$timestampUrl = "http://ts.ssl.com"

function Sign-File($path) {
    if (-not $signtool -or -not $cert) {
        Write-Host "  (signing skipped - no signtool or certificate found)"
        return
    }
    Write-Host "  Signing $path (YubiKey PIN prompt may appear)..."
    & $signtool sign /sha1 $cert.Thumbprint /fd sha256 /tr $timestampUrl /td sha256 $path
    if ($LASTEXITCODE -ne 0) { throw "signtool failed for $path" }
}

Write-Host "== 1/4 Running tests =="
& $python test_logic.py | Out-Null
& $python test_spell.py | Select-Object -Last 1
& $python test_gui.py | Select-Object -Last 1
& $python test_pet.py | Select-Object -Last 1

Write-Host "== 2/4 Building PromptMate.exe (PyInstaller) =="
& $pyinstaller --noconfirm --clean --windowed --name PromptMate `
    --icon assets\promptmate.ico `
    --add-data "assets\kogi\spritesheet.png;assets\kogi" `
    --add-data "assets\kogi\manifest.json;assets\kogi" `
    --add-data "data\english-words.txt;data" `
    promptmate.py | Out-Null

Write-Host "== 3/4 Signing application =="
Sign-File "dist\PromptMate\PromptMate.exe"

Write-Host "== 4/4 Compiling and signing installer (Inno Setup) =="
& $iscc installer.iss | Select-Object -Last 2
$setup = Get-ChildItem "installer\PromptMate-Setup-*.exe" | Sort-Object LastWriteTime | Select-Object -Last 1
Sign-File $setup.FullName

Write-Host "Done. Silent install:  installer\PromptMate-Setup-*.exe /VERYSILENT /NORESTART"
