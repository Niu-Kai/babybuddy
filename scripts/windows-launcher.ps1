param([ValidateSet("Setup", "Start", "Check")][string]$Mode = "Setup")
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot

function Find-Python {
    # Prefer this installation's runtime, then the Python launcher and normal installs.
    $candidates = @((Join-Path $projectRoot ".venv\Scripts\python.exe"))
    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($launcher) {
        try {
            $detected = & $launcher.Source -3.14 -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0) { $candidates += $detected }
        } catch {
            # A launcher may exist without Python 3.14; continue to other paths.
        }
    }
    $candidates += @(
        "$env:LOCALAPPDATA\Programs\Python\Python314\python.exe",
        "$env:ProgramFiles\Python314\python.exe"
    )
    $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($pythonCommand -and $pythonCommand.Source -notlike "*WindowsApps*") {
        $candidates += $pythonCommand.Source
    }
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            & $candidate -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 14) else 1)" 2>$null
            if ($LASTEXITCODE -eq 0) { return $candidate }
        }
    }
    return $null
}

try {
    if ($Mode -eq "Start") {
        $pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
        if (-not (Test-Path -LiteralPath $pythonPath)) {
            throw 'Run "Setup Baby Buddy.cmd" first.'
        }
        & $pythonPath "$PSScriptRoot\setup_app.py" start
        exit $LASTEXITCODE
    }
    $pythonPath = Find-Python
    if (-not $pythonPath -and $Mode -eq "Setup") {
        Write-Host "Baby Buddy needs Python 3.14. Setup can install it using Windows Package Manager."
        $answer = Read-Host "Install Python now? [Y/n]"
        if ($answer -notin @("", "y", "Y", "yes", "Yes")) {
            throw "Install Python 3.14 from https://www.python.org/downloads/ and run Setup again."
        }
        $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
        if (-not $winget) { throw "Windows Package Manager is unavailable. Install Python 3.14 from https://www.python.org/downloads/ and run Setup again." }
        & $winget.Source install --id Python.Python.3.14 --exact --source winget --scope user --accept-source-agreements --accept-package-agreements
        if ($LASTEXITCODE -ne 0) { throw "Python installation did not complete. Install Python 3.14 manually and run Setup again." }
        $pythonPath = Find-Python
    }
    if (-not $pythonPath) { throw "Python 3.14 was not found. Close this window, install Python 3.14 if needed, and run Setup again." }
    if ($Mode -eq "Check") {
        & $pythonPath "$PSScriptRoot\setup_app.py" check
    } else {
        & $pythonPath "$PSScriptRoot\setup_app.py" setup
    }
    exit $LASTEXITCODE
} catch {
    Write-Host ("Baby Buddy stopped: " + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
