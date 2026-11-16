$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Frontend = Join-Path $Root "frontend"
$StopScript = Join-Path $Root "stop.ps1"
$Python = (Get-Command python -ErrorAction Stop).Source

function Assert-Exists($Path, $Message) {
    if (-not (Test-Path $Path)) {
        throw $Message
    }
}

function Invoke-Checked($ScriptBlock, $Message) {
    & $ScriptBlock
    if ($LASTEXITCODE -ne 0) {
        throw $Message
    }
}

Assert-Exists (Join-Path $Root "app.py") "app.py was not found."
Assert-Exists (Join-Path $Frontend "package.json") "frontend package.json was not found."

Write-Host "Stopping any old Equity Fundamental Engine processes..."
& $StopScript -Quiet

Write-Host "Checking Python dependencies..."
& $Python -c "import app" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "Missing Python dependencies. Install the project dependencies, then run .\start again."
}

if (-not (Test-Path (Join-Path $Frontend "node_modules"))) {
    Write-Host "Installing frontend dependencies..."
    Push-Location $Frontend
    Invoke-Checked { npm install } "Frontend dependency installation failed."
    Pop-Location
}

Write-Host "Building frontend..."
Push-Location $Frontend
Invoke-Checked { npm run build } "Frontend build failed."
Pop-Location

$backendCommand = "cd /d `"$Root`" && `"$Python`" app.py"
Write-Host "Starting Equity Fundamental Engine on http://127.0.0.1:5000 ..."
Start-Process cmd.exe -ArgumentList "/k", $backendCommand -WindowStyle Normal

Start-Sleep -Seconds 2
Start-Process "http://127.0.0.1:5000"

Write-Host ""
Write-Host "Done. Use .\stop to end the engine and integrated services."
