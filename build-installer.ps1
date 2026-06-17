# Build AskPet.exe and the Windows installer.
# Usage:  powershell -ExecutionPolicy Bypass -File build-installer.ps1 [-NoSign]
# Output: installer\AskPet-Setup-<version>.exe
#
# Code signing: if a code-signing cert is present (e.g. on a YubiKey),
# both the app exe and the installer are signed. Expect PIN prompts.
# -NoSign builds an unsigned test version (no PIN prompts).

param([switch]$NoSign)

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
    if ($NoSign) {
        Write-Host "  (signing skipped - NoSign test build)"
        return
    }
    if (-not $signtool -or -not $cert) {
        Write-Host "  (signing skipped - no signtool or certificate found)"
        return
    }
    Write-Host "  Signing $path (YubiKey PIN prompt may appear)..."
    & $signtool sign /sha1 $cert.Thumbprint /fd sha256 /tr $timestampUrl /td sha256 $path
    if ($LASTEXITCODE -ne 0) { throw "signtool failed for $path" }
}

Write-Host "== 1/4 Running tests =="
# A FAILING test MUST halt the build. $ErrorActionPreference='Stop' does NOT
# catch a native exe's non-zero exit, so check $LASTEXITCODE after every test
# and throw. (Piping to Select-Object/Out-Null doesn't change $LASTEXITCODE —
# it reflects python.exe's exit code.)
function Invoke-Test([string]$file, [switch]$Quiet) {
    if ($Quiet) { & $python $file | Out-Null }
    else        { & $python $file | Select-Object -Last 1 }
    if ($LASTEXITCODE -ne 0) { throw "TEST FAILED: $file (exit code $LASTEXITCODE)" }
}
Invoke-Test test_logic.py -Quiet
Invoke-Test test_history.py
Invoke-Test test_spell.py
Invoke-Test test_local_ai.py
Invoke-Test test_knowledge.py
Invoke-Test test_deckside.py
Invoke-Test test_slash.py
Invoke-Test test_gui.py
Invoke-Test test_pet.py
Invoke-Test test_games.py
Invoke-Test test_rpg.py
Invoke-Test test_world.py
Invoke-Test test_scene.py
Invoke-Test test_battle.py

Write-Host "== 2/4 Building AskPet.exe (PyInstaller) =="
& $pyinstaller --noconfirm --clean --windowed --name AskPet `
    --icon assets\askpet.ico `
    --add-data "assets\kogi\spritesheet.png;assets\kogi" `
    --add-data "assets\kogi\manifest.json;assets\kogi" `
    --add-data "data\english-words.txt;data" `
    --add-data "assets\eldermark\*.png;assets\eldermark" `
    askpet.py | Out-Null

Write-Host "== 3/4 Signing application =="
Sign-File "dist\AskPet\AskPet.exe"

Write-Host "== 4/4 Compiling and signing installer (Inno Setup) =="
& $iscc installer.iss | Select-Object -Last 2
$setup = Get-ChildItem "installer\AskPet-Setup-*.exe" | Sort-Object LastWriteTime | Select-Object -Last 1
Sign-File $setup.FullName

Write-Host "Done. Silent install:  installer\AskPet-Setup-*.exe /VERYSILENT /NORESTART"
