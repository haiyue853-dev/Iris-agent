[CmdletBinding()]
param(
    [switch]$Check
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
$frontendRoot = Join-Path $projectRoot 'web-react'
$envFile = Join-Path $projectRoot '.env'

function Resolve-NpmCommand {
    $command = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $nvmLink = [Environment]::GetEnvironmentVariable('NVM_SYMLINK', 'User')
    if ($nvmLink) {
        $candidate = Join-Path $nvmLink 'npm.cmd'
        if (Test-Path -LiteralPath $candidate) {
            return $candidate
        }
    }

    $fallback = 'C:\Program Files\nodejs\npm.cmd'
    if (Test-Path -LiteralPath $fallback) {
        return $fallback
    }

    throw 'npm.cmd was not found. Open a new terminal or run: nvm use 20.20.2'
}

function ConvertTo-EncodedCommand([string]$Command) {
    return [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($Command))
}

if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "Project Python virtual environment was not found: $pythonExe"
}
if (-not (Test-Path -LiteralPath (Join-Path $frontendRoot 'package.json'))) {
    throw "Frontend project was not found: $frontendRoot"
}
if (-not (Test-Path -LiteralPath $envFile)) {
    Write-Warning '.env was not found. Copy .env.example and set OPENAI_API_KEY.'
}

$npmCommand = Resolve-NpmCommand
& $pythonExe --version
& $npmCommand --version

if ($Check) {
    Write-Host 'Iris Agent startup check passed.' -ForegroundColor Green
    exit 0
}

$backendCommand = "`$Host.UI.RawUI.WindowTitle='Iris Agent Backend'; Set-Location -LiteralPath '$($projectRoot.Replace("'", "''"))'; & '$($pythonExe.Replace("'", "''"))' server.py"
$frontendCommand = "`$Host.UI.RawUI.WindowTitle='Iris Agent Frontend'; Set-Location -LiteralPath '$($frontendRoot.Replace("'", "''"))'; & '$($npmCommand.Replace("'", "''"))' run dev"

Start-Process powershell.exe -ArgumentList '-NoExit', '-EncodedCommand', (ConvertTo-EncodedCommand $backendCommand) -WindowStyle Normal
Start-Sleep -Milliseconds 800
Start-Process powershell.exe -ArgumentList '-NoExit', '-EncodedCommand', (ConvertTo-EncodedCommand $frontendCommand) -WindowStyle Normal

Write-Host ''
Write-Host 'Iris Agent is starting:' -ForegroundColor Cyan
Write-Host '  Frontend: http://localhost:5173'
Write-Host '  API docs: http://localhost:8000/docs'
Write-Host 'Keep both log windows open. Close a window to stop that service.'
