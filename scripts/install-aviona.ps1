# Repair and install Aviona (fixes corrupt ~lm-agentic-framework dist-info).
$ErrorActionPreference = "Stop"
$Repo = "D:\thesis\agentic-ai"
Set-Location $Repo

$Python = Join-Path $Repo ".venv\Scripts\python.exe"
$SitePackages = Join-Path $Repo ".venv\Lib\site-packages"

if (-not (Test-Path $Python)) {
    Write-Host "Creating venv..."
    python -m venv .venv
}

Write-Host "Cleaning corrupt partial installs..."
Get-Process -Name aviona -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1
Get-ChildItem $SitePackages -Filter "~*" -ErrorAction SilentlyContinue |
    ForEach-Object {
        Write-Host "  removing $($_.Name)"
        Remove-Item $_.FullName -Recurse -Force
    }

Write-Host "Installing editable package..."
& $Python -m pip install -e .
if ($LASTEXITCODE -ne 0) {
    Write-Error "pip install -e . failed. Close any running aviona.exe and retry."
}

$PkgVer = (& $Python -c "import aviona; print(aviona.__version__)").Trim()
Write-Host "Package: aviona $PkgVer"

$AvionaExe = Join-Path $Repo ".venv\Scripts\aviona.exe"
if (Test-Path $AvionaExe) {
    $CliVer = (& $AvionaExe --version).Trim()
    Write-Host "CLI:     $CliVer"
} else {
    Write-Host "CLI:     (use: python -m aviona)"
}

# Ensure venv Scripts on User PATH
$Scripts = Join-Path $Repo ".venv\Scripts"
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$Scripts*") {
    $newPath = if ($userPath) { "$userPath;$Scripts" } else { $Scripts }
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    Write-Host "Added to User PATH: $Scripts (open a new terminal)"
}

Write-Host ""
Write-Host "Ready. Examples:"
Write-Host "  cd D:\thesis\aviona-test"
Write-Host "  aviona --version"
Write-Host "  aviona --mode auto"
