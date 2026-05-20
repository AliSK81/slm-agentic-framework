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

Write-Host "==> pytest Aviona unit + journey tests"
& $Python -m pytest `
    tests/unit/test_aviona_cli.py `
    tests/unit/test_aviona_console.py `
    tests/unit/test_aviona_doctor.py `
    tests/unit/test_aviona_effects.py `
    tests/unit/test_aviona_intent.py `
    tests/unit/test_aviona_journeys.py `
    tests/unit/test_aviona_project.py `
    tests/unit/test_aviona_repl.py `
    tests/unit/test_aviona_resume.py `
    tests/unit/test_aviona_session.py `
    tests/unit/test_aviona_store.py `
    -v --tb=short
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if ($Live) {
    Write-Host "==> L3 live smoke (requires API key)"
    $Fixture = Join-Path $Repo "tests\fixtures\sample_repo"
    $LiveWs = "D:\thesis\aviona-test"
    if (-not (Test-Path $LiveWs)) { $LiveWs = $Fixture }

    function Test-AvionaPrompt {
        param([string]$Prompt, [string[]]$MustContain)
        Write-Host "  -> $Prompt"
        $out = @($Prompt, '/exit') | & $Aviona --mode auto 2>&1 | Out-String
        foreach ($needle in $MustContain) {
            if ($out -notmatch [regex]::Escape($needle)) {
                Write-Error "Live fail: '$Prompt' missing '$needle'. Output:`n$out"
            }
        }
        if ($out -match '^\s*!\s*\|' -or $out -match 'no further action') {
            Write-Error "Live fail: '$Prompt' returned failure or vacuous answer.`n$out"
        }
    }

    Push-Location $LiveWs
    Test-AvionaPrompt 'list files in this dir' @('hello.txt', 'main.py')
    Test-AvionaPrompt 'what is content of hello file?' @('hi')
    Test-AvionaPrompt 'what is this project' @('Project overview', 'README')
    Pop-Location
}

Write-Host "==> Aviona gate PASSED ($ExpectedVersion)"
