# Aviona QA gate — run before manual REPL testing.
param(
    [switch]$Live
)

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Repo

$Python = Join-Path $Repo ".venv\Scripts\python.exe"
$Aviona = Join-Path $Repo ".venv\Scripts\aviona.exe"

if (-not (Test-Path $Python)) {
    Write-Error "Missing venv. Run: D:\thesis\agentic-ai\scripts\install-aviona.ps1"
}

$SitePackages = Join-Path $Repo ".venv\Lib\site-packages"
Get-Process -Name aviona -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Get-ChildItem $SitePackages -Filter "~*" -ErrorAction SilentlyContinue |
    ForEach-Object { Remove-Item $_.FullName -Recurse -Force }

$ExpectedVersion = (
    Select-String -Path (Join-Path $Repo "src\aviona\__init__.py") -Pattern '__version__ = "([^"]+)"'
).Matches.Groups[1].Value
$needsInstall = $true
try {
    $InstalledVersion = (& $Python -c "import aviona; print(aviona.__version__)").Trim()
    if ($InstalledVersion -eq $ExpectedVersion) { $needsInstall = $false }
} catch {
    $needsInstall = $true
}

if ($needsInstall) {
    Write-Host "==> pip install -e . (need $ExpectedVersion)"
    & $Python -m pip install -e .
    if ($LASTEXITCODE -ne 0) {
        Write-Error "pip install -e . failed. Close any running aviona.exe, run scripts\install-aviona.ps1, retry."
    }
} else {
    Write-Host "==> editable install OK ($ExpectedVersion)"
}
Write-Host "==> package version: $ExpectedVersion"
if (Test-Path $Aviona) {
    $CliVersion = (& $Aviona --version 2>&1).Trim()
    Write-Host "==> CLI version: $CliVersion"
}

Write-Host "==> pytest Aviona unit + contract tests"
& $Python -m pytest `
    tests/unit/test_aviona_cli.py `
    tests/unit/test_aviona_console.py `
    tests/unit/test_aviona_contract.py `
    tests/unit/test_aviona_doctor.py `
    tests/unit/test_aviona_intent.py `
    tests/unit/test_aviona_contract_matrix.py `
    tests/unit/test_runtime_answer.py `
    tests/unit/test_aviona_patch_grep.py `
    tests/unit/test_aviona_project.py `
    tests/unit/test_aviona_repl.py `
    tests/unit/test_aviona_resume.py `
    tests/unit/test_aviona_session.py `
    tests/unit/test_aviona_store.py `
    tests/unit/test_turn_io.py `
    tests/unit/test_turn_budgets.py `
    -v --tb=short
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if ($Live) {
    Write-Host "==> L3 live gate (requires API key)"
    & $Python (Join-Path $Repo "scripts\live_gate.py") --aviona $Aviona
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Write-Host "==> Aviona gate PASSED ($ExpectedVersion)"
