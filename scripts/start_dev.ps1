<#
.SYNOPSIS
    Start SpatialForge development servers (FastAPI backend and Vite frontend).
.DESCRIPTION
    Checks virtual environment and frontend node_modules, verifies ports 8000 and 5173,
    starts the backend on 127.0.0.1:8000 and the frontend on 127.0.0.1:5173,
    writes logs to the logs/ directory, and stops both servers cleanly upon exit or Ctrl+C.
#>

[CmdletBinding()]
param(
    [switch]$NoWait
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Split-Path -Parent $ScriptDir)
Set-Location -LiteralPath $RepoRoot

$venvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$frontendModules = Join-Path $RepoRoot "frontend\node_modules"

# 1. Verify prerequisites
if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Error "Virtual environment not found at $venvPython. Please run .\scripts\setup_windows.ps1 first."
    exit 1
}

if (-not (Test-Path -LiteralPath $frontendModules)) {
    Write-Error "Frontend dependencies not installed at $frontendModules. Please run .\scripts\setup_windows.ps1 first."
    exit 1
}

# Configure CPU development environment (Depth model and COLMAP)
$defaultModel = Join-Path $RepoRoot "models\depth_anything_v2_small.onnx"
if (-not $env:SPATIALFORGE_DEPTH_MODEL -and (Test-Path -LiteralPath $defaultModel)) {
    $env:SPATIALFORGE_DEPTH_MODEL = $defaultModel
    Write-Host "Configured SPATIALFORGE_DEPTH_MODEL = $defaultModel" -ForegroundColor DarkCyan
}

$colmapDir = if ($env:SPATIALFORGE_COLMAP_DIR) { $env:SPATIALFORGE_COLMAP_DIR } else { Join-Path $HOME "Downloads\colmap-x64-windows-nocuda" }
if (Test-Path -LiteralPath $colmapDir) {
    if ($env:PATH -notlike "*$colmapDir*") {
        $env:PATH = "$colmapDir;$colmapDir\bin;$env:PATH"
    }
    $colmapExe = Join-Path $colmapDir "bin\colmap.exe"
    if (Test-Path -LiteralPath $colmapExe) {
        $env:SPATIALFORGE_COLMAP_PATH = $colmapExe
    } elseif (-not $env:SPATIALFORGE_COLMAP_PATH) {
        $env:SPATIALFORGE_COLMAP_PATH = Join-Path $colmapDir "COLMAP.bat"
    }
    Write-Host "Configured COLMAP for CPU reconstruction from $colmapDir" -ForegroundColor DarkCyan
}

# 2. Check for port conflicts (8000 and 5173)
function Get-PortListener([int]$Port) {
    try {
        $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        if ($conn) {
            return $conn[0].OwningProcess
        }
    } catch {
        # Fallback using netstat if Get-NetTCPConnection is restricted
        $lines = netstat -ano | Select-String ":$Port\s+.*LISTENING\s+(\d+)"
        if ($lines) {
            if ($lines[0].Line -match ":$Port\s+.*LISTENING\s+(\d+)") {
                return [int]$matches[1]
            }
        }
    }
    return $null
}

$port8000Pid = Get-PortListener 8000
if ($port8000Pid) {
    Write-Error "Port 8000 is already in use by process PID $port8000Pid. Please stop that process before running start_dev.ps1."
    exit 1
}

$port5173Pid = Get-PortListener 5173
if ($port5173Pid) {
    Write-Error "Port 5173 is already in use by process PID $port5173Pid. Please stop that process before running start_dev.ps1."
    exit 1
}

# 3. Create log directory
$LogDir = Join-Path $RepoRoot "logs"
if (-not (Test-Path -LiteralPath $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}

$backendLog = Join-Path $LogDir "backend.log"
$backendErr = Join-Path $LogDir "backend_err.log"
$frontendLog = Join-Path $LogDir "frontend.log"
$frontendErr = Join-Path $LogDir "frontend_err.log"

# Clear old log files
"" | Set-Content -Path $backendLog -Encoding utf8
"" | Set-Content -Path $backendErr -Encoding utf8
"" | Set-Content -Path $frontendLog -Encoding utf8
"" | Set-Content -Path $frontendErr -Encoding utf8

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Starting SpatialForge Development Servers..." -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# 4. Start Backend (FastAPI on 127.0.0.1:8000)
$backendJob = Start-Job -ScriptBlock {
    param($repo, $venv, $depthModel, $colmapPath)
    Set-Location $repo
    if ($depthModel) { $env:SPATIALFORGE_DEPTH_MODEL = $depthModel }
    if ($colmapPath) { $env:SPATIALFORGE_COLMAP_PATH = $colmapPath }
    & $venv -m uvicorn spatialforge.api.main:app --host 127.0.0.1 --port 8000 --reload
} -ArgumentList $RepoRoot, $venvPython, $env:SPATIALFORGE_DEPTH_MODEL, $env:SPATIALFORGE_COLMAP_PATH

Write-Host "Backend job started (Job ID $($backendJob.Id))" -ForegroundColor Green

# 5. Start Frontend (Vite on 127.0.0.1:5173)
$frontendDir = Join-Path $RepoRoot "frontend"
$frontendJob = Start-Job -ScriptBlock {
    param($dir)
    Set-Location $dir
    node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5173
} -ArgumentList $frontendDir

Write-Host "Frontend job started (Job ID $($frontendJob.Id))" -ForegroundColor Green

# 6. Wait for servers to be responsive
Write-Host "`nWaiting for servers to become responsive..." -ForegroundColor Yellow
$backendReady = $false
$frontendReady = $false

for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Milliseconds 500

    if (-not $backendReady) {
        try {
            $resp = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 1 -ErrorAction SilentlyContinue
            if ($resp.status -eq "ok") {
                $backendReady = $true
            }
        } catch {}
    }

    if (-not $frontendReady) {
        try {
            $fresp = Invoke-WebRequest -Uri "http://127.0.0.1:5173/" -TimeoutSec 1 -UseBasicParsing -ErrorAction SilentlyContinue
            if ($fresp.StatusCode -eq 200) {
                $frontendReady = $true
            }
        } catch {}
    }

    if ($backendReady -and $frontendReady) {
        break
    }
}

Write-Host "`n------------------------------------------------------------" -ForegroundColor Cyan
Write-Host "SpatialForge is ready!" -ForegroundColor Green
Write-Host "Backend health: http://127.0.0.1:8000/health" -ForegroundColor Cyan
Write-Host "Frontend:       http://127.0.0.1:5173/" -ForegroundColor Cyan
Write-Host "API docs:       http://127.0.0.1:8000/docs" -ForegroundColor Cyan
Write-Host "------------------------------------------------------------" -ForegroundColor Cyan
Write-Host "Logs are streaming to:" -ForegroundColor Gray
Write-Host "  Backend  : $backendLog" -ForegroundColor Gray
Write-Host "  Frontend : $frontendLog" -ForegroundColor Gray
Write-Host "------------------------------------------------------------" -ForegroundColor Cyan

if ($NoWait) {
    Write-Host "NoWait flag specified. Servers running in background."
    exit 0
}

Write-Host "Press Ctrl+C to stop both servers.`n" -ForegroundColor Yellow

try {
    $ErrorActionPreference = "Continue"
    while ($true) {
        if ($backendJob.State -ne "Running") {
            Write-Warning "Backend job terminated unexpectedly."
            Receive-Job $backendJob -ErrorAction SilentlyContinue
            break
        }
        if ($frontendJob.State -ne "Running") {
            Write-Warning "Frontend job terminated unexpectedly."
            Receive-Job $frontendJob -ErrorAction SilentlyContinue
            break
        }
        try {
            $bOut = Receive-Job $backendJob -ErrorAction SilentlyContinue
            if ($bOut) { Add-Content -Path $backendLog -Value $bOut -Encoding utf8 -ErrorAction SilentlyContinue }
            $fOut = Receive-Job $frontendJob -ErrorAction SilentlyContinue
            if ($fOut) { Add-Content -Path $frontendLog -Value $fOut -Encoding utf8 -ErrorAction SilentlyContinue }
        } catch {}
        Start-Sleep -Seconds 2
    }
} catch {
    Write-Warning "Main loop error: $_"
} finally {
    Write-Host "`nShutting down development servers..." -ForegroundColor Yellow
    Stop-Job $backendJob, $frontendJob -ErrorAction SilentlyContinue
    Remove-Job $backendJob, $frontendJob -Force -ErrorAction SilentlyContinue
    
    $p8000 = Get-PortListener 8000
    if ($p8000) { Stop-Process -Id $p8000 -Force -ErrorAction SilentlyContinue }
    $p5173 = Get-PortListener 5173
    if ($p5173) { Stop-Process -Id $p5173 -Force -ErrorAction SilentlyContinue }
    Write-Host "Servers stopped." -ForegroundColor Green
}
