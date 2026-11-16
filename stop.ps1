param(
    [switch]$Quiet,
    [switch]$KeepAiAgent
)

$ErrorActionPreference = "SilentlyContinue"

function Stop-Port($Port, $Label) {
    $connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    $processIds = $connections | Select-Object -ExpandProperty OwningProcess -Unique

    foreach ($processId in $processIds) {
        if (-not $processId -or $processId -eq 0) {
            continue
        }

        $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
        if ($process) {
            if (-not $Quiet) {
                Write-Host "Stopping $Label on port $Port (PID ${processId}: $($process.ProcessName))..."
            }
            Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
        }
    }
}

Stop-Port -Port 5000 -Label "Equity Fundamental Engine"

if (-not $KeepAiAgent) {
    Stop-Port -Port 8000 -Label "Stock Market Agent backend"
    Stop-Port -Port 5173 -Label "Stock Market Agent frontend"
    Stop-Port -Port 8001 -Label "RiskDesk backend"
    Stop-Port -Port 5174 -Label "RiskDesk frontend"
}

if (-not $Quiet) {
    Write-Host "Stopped."
}
