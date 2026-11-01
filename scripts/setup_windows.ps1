<#
.SYNOPSIS
    Idempotent Windows setup script for SpatialForge local development.
.DESCRIPTION
    Checks system prerequisites (Python 3.11+, Node.js, npm, RAM, disk space),
    creates a project-local Python virtual environment (.venv) if absent,
    installs backend dependencies into .venv, installs frontend dependencies,
    and executes verification checks.
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

# 1. Resolve repository root safely
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Split-Path -Parent $ScriptDir)
Set-Location -LiteralPath $RepoRoot

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "SpatialForge Local Development Setup (Windows)" -ForegroundColor Cyan
Write-Host "Repository root: $RepoRoot" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# 2. Check system resources: RAM and Disk Space
Write-Host "`n[1/6] Checking system resources..." -ForegroundColor Yellow

$os = Get-CimInstance Win32_OperatingSystem
$totalRamGB = [math]::Round($os.TotalVisibleMemorySize / 1MB, 2)
$freeRamGB = [math]::Round($os.FreePhysicalMemory / 1MB, 2)
Write-Host "  Total Visible RAM : $totalRamGB GB"
Write-Host "  Available Free RAM: $freeRamGB GB"

$driveLetter = (Get-Item -LiteralPath $RepoRoot).PSDrive.Name
$drive = Get-PSDrive -Name $driveLetter
$freeDiskGB = [math]::Round($drive.Free / 1GB, 2)
Write-Host "  Free Disk on ${driveLetter}: $freeDiskGB GB"

if ($freeDiskGB -lt 3.0) {
    Write-Error "CRITICAL: Less than 3.0 GB of free disk space is available ($freeDiskGB GB). Aborting setup."
    exit 1
}

# 3. Check Python 3.11+
Write-Host "`n[2/6] Checking Python installation..." -ForegroundColor Yellow

$pythonCmd = $null

# Check candidates: 'py -3.11', 'py -3', 'python'
$candidates = @(
    @("py", "-3.11"),
    @("py", "-3"),
    @("python")
)

foreach ($cand in $candidates) {
    try {
        $out = $null
        if ($cand.Length -gt 1) {
            $out = & $cand[0] $cand[1] -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')" 2>$null
        } else {
            $out = & $cand[0] -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')" 2>$null
        }
        if ($LASTEXITCODE -eq 0 -and $out) {
            $verStr = ($out | Select-Object -First 1).ToString().Trim()
            $verParts = $verStr.Split('.')
            if ($verParts.Length -ge 2) {
                $major = [int]$verParts[0]
                $minor = [int]$verParts[1]
                if ($major -eq 3 -and $minor -ge 11) {
                    $pythonCmd = $cand
                    Write-Host "  Found compatible Python $verStr via '$($cand -join ' ')'"
                    break
                }
            }
        }
    } catch {
        # continue checking next candidate
    }
}

if (-not $pythonCmd) {
    Write-Error "Python 3.11 or newer is required, but was not found. Please install Python 3.11+."
    exit 1
}

# 4. Check Node.js and npm
Write-Host "`n[3/6] Checking Node.js and npm..." -ForegroundColor Yellow

try {
    $nodeVer = (node --version).Trim()
    Write-Host "  Node.js version: $nodeVer"
} catch {
    Write-Error "Node.js was not found on PATH. Please install Node.js (version 20+ recommended)."
    exit 1
}

try {
    $npmVer = (npm --version).Trim()
    Write-Host "  npm version:     $npmVer"
} catch {
    Write-Error "npm was not found on PATH. Please install Node.js / npm."
    exit 1
}

# 5. Virtual environment setup (.venv)
Write-Host "`n[4/6] Setting up project-local Python virtual environment (.venv)..." -ForegroundColor Yellow

$venvPath = Join-Path $RepoRoot ".venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host "  Creating virtual environment at $venvPath..."
    if ($pythonCmd.Length -gt 1) {
        & $pythonCmd[0] $pythonCmd[1] -m venv "$venvPath"
    } else {
        & $pythonCmd[0] -m venv "$venvPath"
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to create Python virtual environment."
        exit 1
    }
    Write-Host "  Virtual environment created."
} else {
    Write-Host "  Virtual environment already exists at $venvPath."
}

Write-Host "  Upgrading packaging tools (pip, setuptools, wheel)..."
& $venvPython -m pip install --upgrade pip setuptools wheel
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to upgrade packaging tools."
    exit 1
}

Write-Host "  Installing SpatialForge backend dependencies (editable with dev extras)..."
& $venvPython -m pip install -e ".[dev]" onnxruntime
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to install backend dependencies."
    exit 1
}

# 6. Frontend environment setup
Write-Host "`n[5/6] Setting up frontend dependencies..." -ForegroundColor Yellow
$frontendDir = Join-Path $RepoRoot "frontend"

Push-Location $frontendDir
try {
    if (Test-Path "package-lock.json") {
        Write-Host "  Running deterministic 'npm ci'..."
        npm ci
    } else {
        Write-Host "  Running 'npm install'..."
        npm install
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to install frontend dependencies."
        exit 1
    }
} finally {
    Pop-Location
}

# 7. Verification check
Write-Host "`n[6/6] Running environment verification script..." -ForegroundColor Yellow
& $venvPython (Join-Path $RepoRoot "scripts\verify_install.py")
if ($LASTEXITCODE -ne 0) {
    Write-Error "Installation verification failed. Please check the reported errors."
    exit 1
}

Write-Host "`n============================================================" -ForegroundColor Green
Write-Host "SpatialForge local setup completed successfully!" -ForegroundColor Green
Write-Host "To start development servers, run:" -ForegroundColor Green
Write-Host "  powershell -ExecutionPolicy Bypass -File .\scripts\start_dev.ps1" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Green
exit 0
