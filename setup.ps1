# setup.ps1 — Instalador guiado de WhisperFlow local para Windows.
# Crea el entorno virtual, instala dependencias (CUDA opcional), pregunta por el
# backend de tono (Ollama local / OpenAI / ninguno), escribe el .env y (opcional)
# instala el arranque automático. Pensado para no-desarrolladores.
#
# Uso: clic derecho > "Ejecutar con PowerShell", o desde una terminal:  .\setup.ps1

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

# ---------------- Python 3.12 ----------------
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

# ---------------- Backend de tono ----------------
Write-Host ""
Write-Host "¿Quieres la reescritura de tono (perfiles amigable/profesional)?" -ForegroundColor Cyan
Write-Host "  1) Ollama LOCAL (recomendado: offline, gratis, privado)"
Write-Host "  2) OpenAI (cloud, pago; pide tu API key)"
Write-Host "  3) Ninguna (pega el texto tal cual)"
$choice = Read-Host "Elige [1/2/3] (por defecto 1)"
if ([string]::IsNullOrWhiteSpace($choice)) { $choice = "1" }

$llmBackend = "none"
$ollamaModel = "qwen2.5:3b"
$openaiKey = ""

if ($choice -eq "1") {
    $llmBackend = "ollama"
    Write-Host "Instalando Ollama..." -ForegroundColor Cyan
    if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
        try { winget install --id Ollama.Ollama -e --silent } catch {}
    }
    Write-Host "Descargando el modelo '$ollamaModel' (la primera vez tarda)..." -ForegroundColor Cyan
    try { & ollama pull $ollamaModel } catch { Write-Host "  (no se pudo descargar ahora; corré 'ollama pull $ollamaModel' más tarde)" -ForegroundColor Yellow }
}
elseif ($choice -eq "2") {
    $llmBackend = "openai"
    $keySecure = Read-Host "Pega tu OPENAI_API_KEY" -AsSecureString
    $bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($keySecure)
    try { $openaiKey = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr) }
    finally { [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
}
else {
    $llmBackend = "none"
}

# ---------------- Escribir .env ----------------
$envFile = Join-Path $here ".env"
$lines = @(
    "# Generado por setup.ps1 — editá lo que quieras.",
    "WHISPERFLOW_MODEL_SIZE=small",
    "WHISPERFLOW_LANGUAGE=es",
    "WHISPERFLOW_LLM_BACKEND=$llmBackend"
)
if ($llmBackend -eq "ollama") {
    $lines += "WHISPERFLOW_OLLAMA_BASE_URL=http://localhost:11434/v1"
    $lines += "WHISPERFLOW_OLLAMA_MODEL=$ollamaModel"
}
if ($llmBackend -eq "openai") {
    $lines += "OPENAI_API_KEY=$openaiKey"
    $lines += "WHISPERFLOW_OPENAI_MODEL=gpt-4.1-nano"
}
$lines | Out-File -FilePath $envFile -Encoding utf8
Write-Host ".env escrito en $envFile" -ForegroundColor Green

# ---------------- Arranque automático (opcional) ----------------
$autostart = Read-Host "¿Arranque automático al iniciar sesión en Windows? [s/N]"
if ($autostart -match "^[sSyY]$") {
    & ".\venv\Scripts\python.exe" install_startup.py
}

Write-Host ""
Write-Host "Listo. Para correr WhisperFlow:" -ForegroundColor Green
Write-Host "  .\venv\Scripts\python.exe whisperflow.py"
Write-Host ""
Write-Host "Para ver diagnósticos (pythonw.exe no tiene consola):" -ForegroundColor Yellow
Write-Host "  .\venv\Scripts\python.exe whisperflow.py > debug.log 2> debug_err.log"
Write-Host "  (o WHISPERFLOW_DEBUG=1 para ver cada evento de teclado)"
