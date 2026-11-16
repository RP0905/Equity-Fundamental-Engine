@echo off
setlocal
cd /d "%~dp0"

set "ARC_NODE=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"
if not exist "%ARC_NODE%" set "ARC_NODE=C:\Users\Pritam\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"
if not exist "%ARC_NODE%" (
  where node >nul 2>nul
  if not errorlevel 1 (
    set "ARC_NODE=node"
  )
)

if "%ARC_NODE%"=="node" (
  echo Using Node.js from PATH: %ARC_NODE%
) else if exist "%ARC_NODE%" (
  echo Using bundled Node.js: %ARC_NODE%
) else (
  echo Bundled Node.js was not found.
  echo Install Node.js from https://nodejs.org and run: node scripts\serve.mjs
  pause
  exit /b 1
)

echo Starting Arc Trading Journal at http://localhost:4173
start "Arc Trading Journal" http://localhost:4173
"%ARC_NODE%" scripts\serve.mjs

endlocal