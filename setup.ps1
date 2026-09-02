# setup.ps1 — Instalador guiado de WhisperFlow local para Windows.
# Crea el entorno virtual, instala dependencias (CUDA opcional), pregunta por el
# modelo de transcripción, escribe el .env y (opcional)
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

# ---------------- Modelo de transcripción ----------------
# El tamaño del modelo es LA decisión que define exactitud vs. espera. Con GPU
# NVIDIA, "medium" da ~3x menos errores que "small" por ~0.5 s más (medido en una
# RTX 4050; ver scripts/bench_models.py). Sin GPU, "medium" en CPU se siente lento.
$hasNvidia = $null -ne (Get-Command nvidia-smi -ErrorAction SilentlyContinue)
if ($hasNvidia) { $modelDefault = "medium" } else { $modelDefault = "small" }

Write-Host ""
if ($hasNvidia) {
    Write-Host "GPU NVIDIA detectada." -ForegroundColor Green
} else {
    Write-Host "No se detectó GPU NVIDIA: la transcripción correrá en CPU." -ForegroundColor Yellow
}
Write-Host "¿Qué modelo de Whisper querés usar?" -ForegroundColor Cyan
Write-Host "  1) small    — el más rápido, el que más se equivoca"
Write-Host "  2) medium   — 3x menos errores que small; ~0.9 s por frase con GPU"
Write-Host "  3) large-v3 — el más pesado (~3 GB de VRAM); más lento y no siempre mejor"
Write-Host "  (podés cambiarlo cuando quieras editando .env, y compararlos con"
Write-Host "   'python scriptsench_models.py --record --audio-dir bench_audio')"
$choice = Read-Host "Elige [1/2/3] (por defecto: $modelDefault)"
switch ($choice) {
    "1" { $modelSize = "small" }
    "2" { $modelSize = "medium" }
    "3" { $modelSize = "large-v3" }
    default { $modelSize = $modelDefault }
}

# ---------------- Escribir .env ----------------
$envFile = Join-Path $here ".env"
$lines = @(
    "# Generado por setup.ps1 — editá lo que quieras (ver .env.example para todas las claves).",
    "WHISPERFLOW_MODEL_SIZE=$modelSize",
    "WHISPERFLOW_LANGUAGE=es"
)
$lines | Out-File -FilePath $envFile -Encoding utf8

# ---------------- Diccionario personal ----------------
# dictionary.txt NO se versiona (suele llenarse de nombres de clientes y jerga
# propia). Se crea copiando la plantilla, y solo si todavía no existe: nunca hay
# que pisar el diccionario que el usuario ya venía construyendo.
$dict = Join-Path $here "dictionary.txt"
if (-not (Test-Path $dict)) {
    Copy-Item (Join-Path $here "dictionary.example.txt") $dict
    Write-Host "dictionary.txt creado desde la plantilla — agregá ahí tus términos." -ForegroundColor Green
} else {
    Write-Host "dictionary.txt ya existe, se deja como está." -ForegroundColor Yellow
}
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
