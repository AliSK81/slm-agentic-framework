# Repair and install Aviona on Windows (corrupt ~* dist-info, aviona.exe locks).
param(
    [switch]$DryRun,
    [switch]$SkipPath
)

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Repo

$Python = Join-Path $Repo ".venv\Scripts\python.exe"
$SitePackages = Join-Path $Repo ".venv\Lib\site-packages"
$AvionaExe = Join-Path $Repo ".venv\Scripts\aviona.exe"
$InitPy = Join-Path $Repo "src\aviona\__init__.py"

function Get-ExpectedAvionaVersion {
    if (-not (Test-Path $InitPy)) {
        throw "Missing $InitPy"
    }
    $match = Select-String -Path $InitPy -Pattern '__version__ = "([^"]+)"'
    if (-not $match) {
        throw "Could not parse __version__ from $InitPy"
    }
    return $match.Matches.Groups[1].Value
}

function Stop-AvionaProcesses {
    param([int]$GraceSeconds = 1)
    $procs = @(Get-Process -Name aviona -ErrorAction SilentlyContinue)
    if ($procs.Count -eq 0) {
        return 0
    }
    foreach ($proc in $procs) {
        Write-Host "  stopping aviona pid $($proc.Id)"
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    }
    if ($GraceSeconds -gt 0) {
        Start-Sleep -Seconds $GraceSeconds
    }
    return $procs.Count
}

function Get-CorruptDistInfo {
    if (-not (Test-Path $SitePackages)) {
        return @()
    }
    return @(Get-ChildItem $SitePackages -Filter "~*" -ErrorAction SilentlyContinue)
}

function Remove-CorruptDistInfo {
    param([switch]$WhatIf)
    $removed = 0
    foreach ($item in (Get-CorruptDistInfo)) {
        if ($WhatIf) {
            Write-Host "  would remove $($item.Name)"
        } else {
            Write-Host "  removing $($item.Name)"
            Remove-Item $item.FullName -Recurse -Force
        }
        $removed++
    }
    return $removed
}

function Get-InstalledPackageVersion {
    if (-not (Test-Path $Python)) {
        return $null
    }
    try {
        return (& $Python -c "import aviona; print(aviona.__version__)").Trim()
    } catch {
        return $null
    }
}

function Get-AvionaCliVersion {
    if (-not (Test-Path $AvionaExe)) {
        return $null
    }
    try {
        return (& $AvionaExe --version 2>&1).Trim()
    } catch {
        return $null
    }
}

function Test-AvionaVersionParity {
    param(
        [Parameter(Mandatory = $true)][string]$ExpectedVersion
    )
    $pkg = Get-InstalledPackageVersion
    $cli = Get-AvionaCliVersion
    if ($null -eq $pkg) {
        throw "Package aviona is not importable in the venv."
    }
    if ($pkg -ne $ExpectedVersion) {
        throw "Package version mismatch: expected $ExpectedVersion, got $pkg"
    }
    if ($null -eq $cli) {
        throw "Missing CLI entry point at $AvionaExe"
    }
    if ($cli -notlike "*$ExpectedVersion*") {
        throw "CLI version mismatch: expected $ExpectedVersion in '$cli'"
    }
    return @{
        Package = $pkg
        Cli     = $cli
    }
}

function Install-EditablePackage {
    param([int]$MaxAttempts = 2)
    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        & $Python -m pip install -e .
        if ($LASTEXITCODE -eq 0) {
            return
        }
        Write-Host "pip install failed (attempt $attempt/$MaxAttempts)"
        Stop-AvionaProcesses | Out-Null
        if (Test-Path $AvionaExe) {
            try {
                Remove-Item $AvionaExe -Force -ErrorAction Stop
                Write-Host "  removed locked $AvionaExe"
            } catch {
                Write-Host "  could not remove ${AvionaExe}: $_"
            }
        }
        Remove-CorruptDistInfo | Out-Null
    }
    throw "pip install -e . failed after $MaxAttempts attempts. Close any running aviona.exe and retry."
}

$ExpectedVersion = Get-ExpectedAvionaVersion
Write-Host "Repo:    $Repo"
Write-Host "Target:  aviona $ExpectedVersion"

if ($DryRun) {
    Write-Host "Mode:    dry-run (no install, no PATH changes)"
    if (-not (Test-Path (Join-Path $Repo "pyproject.toml"))) {
        throw "Missing pyproject.toml under $Repo"
    }
    if (-not (Test-Path $Python)) {
        Write-Host "Venv:    would create .venv"
    } else {
        Write-Host "Venv:    present"
        $running = @(Get-Process -Name aviona -ErrorAction SilentlyContinue).Count
        if ($running -gt 0) {
            Write-Host "Process: $running aviona.exe would be stopped before install"
        } else {
            Write-Host "Process: no aviona.exe running"
        }
        $corrupt = Get-CorruptDistInfo
        if ($corrupt.Count -gt 0) {
            Write-Host "Cleanup: $($corrupt.Count) corrupt ~* dist-info entries"
            Remove-CorruptDistInfo -WhatIf | Out-Null
        } else {
            Write-Host "Cleanup: no corrupt ~* dist-info"
        }
        $versions = Test-AvionaVersionParity -ExpectedVersion $ExpectedVersion
        Write-Host "Package: aviona $($versions.Package)"
        Write-Host "CLI:     $($versions.Cli)"
    }
    Write-Host "Dry-run OK"
    exit 0
}

if (-not (Test-Path $Python)) {
    Write-Host "Creating venv..."
    python -m venv .venv
}

Write-Host "Stopping aviona processes..."
Stop-AvionaProcesses | Out-Null

Write-Host "Cleaning corrupt partial installs..."
Remove-CorruptDistInfo | Out-Null

Write-Host "Installing editable package..."
Install-EditablePackage

$versions = Test-AvionaVersionParity -ExpectedVersion $ExpectedVersion
Write-Host "Package: aviona $($versions.Package)"
Write-Host "CLI:     $($versions.Cli)"

if (-not $SkipPath) {
    $Scripts = Join-Path $Repo ".venv\Scripts"
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($userPath -notlike "*$Scripts*") {
        $newPath = if ($userPath) { "$userPath;$Scripts" } else { $Scripts }
        [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
        Write-Host "Added to User PATH: $Scripts (open a new terminal)"
    }
}

Write-Host ""
Write-Host "Ready. Examples:"
Write-Host "  cd D:\thesis\aviona-test"
Write-Host "  aviona --version"
Write-Host "  aviona --mode auto"
