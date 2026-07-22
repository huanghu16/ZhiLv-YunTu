<#
.SYNOPSIS
    ZhiLv YunTu - Development Environment Check
.DESCRIPTION
    Checks whether this machine has all tools and Python packages
    required to run the zhilv-yuntu project.
    Usage in PowerShell:  .\check_env.ps1
    Or from anywhere:
    powershell -ExecutionPolicy Bypass -File C:\Users\Adminstrators\Desktop\zhilv-yuntu-main\check_env.ps1
#>

# Force UTF-8 output so results are readable in any locale
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# Project paths
$ProjectRoot    = "C:\Users\Adminstrators\Desktop\zhilv-yuntu"
$BackendDir     = "$ProjectRoot\backend"
$VenvPython     = "$BackendDir\venv\Scripts\python.exe"

# Helper: print one colored check line
function Write-Check {
    param(
        [string]$Name,
        [string]$Version,
        [string]$Required,
        [bool]$Ok
    )
    $status = if ($Ok) { "OK" } else { "MISS" }
    $color  = if ($Ok) { "Green" } else { "Red" }
    $line = "{0,-28} {1,-24} required {2,-14} [{3}]" -f $Name, $Version, $Required, $status
    Write-Host $line -ForegroundColor $color
}

# Helper: try to get version string of a command
function Get-CommandVersion {
    param([string]$Cmd, [string]$Arg = "--version")
    try {
        $raw = & $Cmd $Arg 2>$null
        if ($LASTEXITCODE -eq 0 -and $raw) {
            return ($raw | Select-Object -First 1).Trim()
        }
    } catch {}
    return $null
}

Write-Host ""
Write-Host "===== ZhiLv YunTu - Dev Environment Check =====" -ForegroundColor Cyan
Write-Host "Time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor DarkGray
Write-Host ""

# --- 1. Base tools ---
Write-Host "[1/4] Base Tools" -ForegroundColor Yellow
Write-Host ("{0,-28} {1,-24} {2}" -f "Tool", "Current", "Note") -ForegroundColor DarkGray

$pyVer = Get-CommandVersion "python"
Write-Check "Python (system)" $pyVer ">=3.11" ($null -ne $pyVer)

$nodeVer = Get-CommandVersion "node"
Write-Check "Node.js" $nodeVer ">=18" ($null -ne $nodeVer)

$npmVer = Get-CommandVersion "npm"
Write-Check "npm" $npmVer ">=9" ($null -ne $npmVer)

$gitVer = Get-CommandVersion "git"
Write-Check "git" $gitVer "any" ($null -ne $gitVer)

$dockerVer = Get-CommandVersion "docker"
Write-Check "Docker" $dockerVer "optional" ($null -ne $dockerVer)

# --- 2. venv status ---
Write-Host ""
Write-Host "[2/4] Virtual Environment (venv)" -ForegroundColor Yellow

$venvExists = Test-Path $VenvPython
if ($venvExists) {
    $venvPyVer = & $VenvPython --version 2>$null
    Write-Host ("{0,-28} {1}" -f "venv python path", $VenvPython) -ForegroundColor Green
    Write-Host ("{0,-28} {1}" -f "venv python version", $venvPyVer) -ForegroundColor Green

    # Check if venv is currently activated by comparing python paths
    $currentPython = (Get-Command python -ErrorAction SilentlyContinue).Source
    if ($currentPython -and $currentPython -ieq $VenvPython) {
        Write-Host ("{0,-28} {1}" -f "venv activated", "YES") -ForegroundColor Green
        $venvActivated = $true
    } else {
        Write-Host ("{0,-28} {1}" -f "venv activated", "NO") -ForegroundColor Red
        Write-Host "  -> Run this to activate:" -ForegroundColor Yellow
        Write-Host "     cd $BackendDir" -ForegroundColor White
        Write-Host "     .\venv\Scripts\Activate.ps1" -ForegroundColor White
        $venvActivated = $false
    }
} else {
    Write-Host ("{0,-28} {1}" -f "venv", "NOT CREATED") -ForegroundColor Red
    Write-Host "  -> Run this to create:" -ForegroundColor Yellow
    Write-Host "     cd $BackendDir" -ForegroundColor White
    Write-Host "     py -3.11 -m venv venv" -ForegroundColor White
    Write-Host "     .\venv\Scripts\Activate.ps1" -ForegroundColor White
    $venvActivated = $false
}

# --- 3. Python packages (check venv if exists, else system python) ---
Write-Host ""
Write-Host "[3/4] Python Packages" -ForegroundColor Yellow

$pythonToCheck = if ($venvExists) { $VenvPython } else { "python" }
$pythonLabel   = if ($venvExists) { "venv" } else { "system" }
Write-Host "Checking packages in: $pythonLabel Python" -ForegroundColor DarkGray
Write-Host ""

$requiredPackages = @(
    @{ Name = "fastapi";             Min = "0.110" },
    @{ Name = "uvicorn";             Min = "0.29"  },
    @{ Name = "pydantic";            Min = "2.6"   },
    @{ Name = "sqlalchemy";          Min = "2.0"   },
    @{ Name = "python-dotenv";       Min = "1.0"   },
    @{ Name = "langchain";           Min = "0.2"   },
    @{ Name = "langchain-core";      Min = "0.2"   },
    @{ Name = "langchain-community"; Min = "0.2"   },
    @{ Name = "langchain-openai";    Min = "0.1"   },
    @{ Name = "chromadb";            Min = "0.4"   },
    @{ Name = "reportlab";           Min = "4.0"   },
    @{ Name = "httpx";               Min = "0.27"  },
    @{ Name = "redis";               Min = "5.0"   },
    @{ Name = "pytest";              Min = "8.0"   }
)

# Fetch installed packages in one call
$installedRaw = & $pythonToCheck -m pip list 2>$null
$installedTable = @{}
foreach ($line in $installedRaw) {
    if ($line -match "^\s*([A-Za-z0-9_.\-]+)\s+(\S+)\s*$") {
        $installedTable[$matches[1].ToLower()] = $matches[2]
    }
}

Write-Host ("{0,-28} {1,-24} {2}" -f "Package", "Current", "Required Min") -ForegroundColor DarkGray
$missingCount = 0
foreach ($pkg in $requiredPackages) {
    $key = $pkg.Name.ToLower()
    if ($installedTable.ContainsKey($key)) {
        Write-Check $pkg.Name $installedTable[$key] $pkg.Min $true
    } else {
        Write-Check $pkg.Name "not installed" $pkg.Min $false
        $missingCount++
    }
}

# --- 4. Project files ---
Write-Host ""
Write-Host "[4/4] Project Files" -ForegroundColor Yellow

$expectedFiles = @(
    "backend\app\config.py",
    "backend\app\models\schemas.py",
    "backend\requirements.txt",
    "backend\.env",
    "backend\.env.example",
    "backend\app\rag\document_loader.py",
    "backend\app\rag\embedding.py",
    "backend\app\rag\vector_db.py",
    "backend\scripts\ingest_data.py",
    "backend\scripts\verify_stage2.py",
    "backend\data\dali_guide.md",
    "backend\data\lijiang_guide.md",
    "backend\data\chengdu_guide.md",
    "backend\data\hangzhou_guide.md",
    "backend\data\xiamen_guide.md",
    ".gitignore",
    "README.md"
)

Write-Host ("{0,-46} {1}" -f "File", "Status") -ForegroundColor DarkGray
$fileMissingCount = 0
foreach ($rel in $expectedFiles) {
    $full = Join-Path $ProjectRoot $rel
    if (Test-Path $full) {
        $line = "{0,-46} [OK]" -f $rel
        Write-Host $line -ForegroundColor Green
    } else {
        $line = "{0,-46} [missing]" -f $rel
        Write-Host $line -ForegroundColor DarkYellow
        $fileMissingCount++
    }
}

# --- Summary ---
Write-Host ""
Write-Host "===== Summary =====" -ForegroundColor Cyan

# venv status
if (-not $venvExists) {
    Write-Host "venv: NOT CREATED - create it first!" -ForegroundColor Red
} elseif (-not $venvActivated) {
    Write-Host "venv: exists but NOT ACTIVATED" -ForegroundColor Red
    Write-Host "  Run: cd $BackendDir ; .\venv\Scripts\Activate.ps1" -ForegroundColor Yellow
} else {
    Write-Host "venv: activated and ready" -ForegroundColor Green
}

# packages
if ($missingCount -gt 0) {
    Write-Host "Python packages: $missingCount missing" -ForegroundColor Red
    Write-Host "  Inside backend dir (with venv activated), run:" -ForegroundColor Yellow
    Write-Host "    pip install -r requirements.txt" -ForegroundColor White
} else {
    Write-Host "Python packages: all installed" -ForegroundColor Green
}

# files
if ($fileMissingCount -gt 0) {
    Write-Host "Project files: $fileMissingCount missing" -ForegroundColor DarkYellow
} else {
    Write-Host "Project files: all present" -ForegroundColor Green
}

Write-Host ""
Write-Host "Notes:" -ForegroundColor DarkGray
Write-Host "  - Docker is optional, only needed for deployment stage." -ForegroundColor DarkGray
Write-Host "  - If venv is not activated, package check uses system Python." -ForegroundColor DarkGray
Write-Host "  - chromadb >= 0.4 is accepted (0.4.x has Windows pre-built wheels)." -ForegroundColor DarkGray
Write-Host ""
