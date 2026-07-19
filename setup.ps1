# setup.ps1 — Crea un entorno virtual e instala las dependencias de WhisperFlow local.
# Uso: clic derecho > "Ejecutar con PowerShell", o desde una terminal:  .\setup.ps1

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

Write-Host "Buscando Python 3.12..." -ForegroundColor Cyan
$pythonCmd = $null
foreach ($candidate in @("py -3.12", "python")) {
    try {
        $parts = $candidate.Split(" ")
        & $parts[0] $parts[1..($parts.Length-1)] --version | Out-Null
        $pythonCmd = $candidate
        break
    } catch {}
}
if (-not $pythonCmd) {
    Write-Host "No se encontró Python 3.12. Instálalo desde https://www.python.org/downloads/ (marca 'Add to PATH') y vuelve a correr este script." -ForegroundColor Red
    exit 1
}
Write-Host "Usando: $pythonCmd" -ForegroundColor Green

$parts = $pythonCmd.Split(" ")
& $parts[0] $parts[1..($parts.Length-1)] -m venv venv

Write-Host "Instalando dependencias (puede tardar varios minutos, especialmente los paquetes de CUDA)..." -ForegroundColor Cyan
& ".\venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\venv\Scripts\python.exe" -m pip install -r requirements.txt

Write-Host ""
Write-Host "Listo. Para correr WhisperFlow:" -ForegroundColor Green
Write-Host "  .\venv\Scripts\python.exe whisperflow.py"
Write-Host ""
Write-Host "Si quieres que arranque solo al iniciar sesión en Windows:" -ForegroundColor Green
Write-Host "  .\venv\Scripts\python.exe install_startup.py"
Write-Host ""
Write-Host "Si quieres usar los 'perfiles de tono' (reescritura con OpenAI), define la" -ForegroundColor Yellow
Write-Host "variable de entorno OPENAI_API_KEY antes de correr whisperflow.py. Es opcional:" -ForegroundColor Yellow
Write-Host "sin ella, todo lo demás funciona igual, solo sin esa reescritura." -ForegroundColor Yellow
