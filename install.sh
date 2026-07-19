#!/usr/bin/env bash
# install.sh — Instalador guiado de WhisperFlow local para macOS (y Linux luego, Fase 6).
# Pensado para no-desarrolladores: crea el venv, instala dependencias, pregunta por el
# backend de tono (Ollama local / OpenAI / ninguno), escribe el .env y (opcional) instala
# el arranque automático y guía los permisos del SO.
#
# Uso:  bash install.sh
set -e

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

PYTHON_BIN=""
for c in python3.12 python3.11 python3.13 python3; do
  if command -v "$c" >/dev/null 2>&1; then PYTHON_BIN="$c"; break; fi
done
if [ -z "$PYTHON_BIN" ]; then
  echo "No se encontró Python 3. Instálalo desde https://www.python.org/ y vuelve a correr este script." >&2
  exit 1
fi
echo "Usando: $PYTHON_BIN  ($($PYTHON_BIN --version))"

VENV_DIR="venv-mac"
echo "Creando entorno virtual en $VENV_DIR ..."
"$PYTHON_BIN" -m venv "$VENV_DIR"

PY="$VENV_DIR/bin/python"
echo "Actualizando pip e instalando dependencias (puede tardar varios minutos)..."
"$PY" -m pip install --upgrade pip
"$PY" -m pip install -r requirements.txt

# ---------------- Backend de tono ----------------
echo
echo "¿Quieres la reescritura de tono (perfiles amigable/profesional)?"
echo "  1) Ollama LOCAL (recomendado: offline, gratis, privado)"
echo "  2) OpenAI (cloud, pago; pide tu API key)"
echo "  3) Ninguna (pega el texto tal cual)"
printf "Elige [1/2/3] (por defecto 1): "
read -r CHOICE
CHOICE="${CHOICE:-1}"

LLM_BACKEND="none"
OLLAMA_MODEL="qwen2.5:3b"
OPENAI_KEY_LINE=""

if [ "$CHOICE" = "1" ]; then
    LLM_BACKEND="ollama"
    echo "Instalando Ollama..."
    if ! command -v ollama >/dev/null 2>&1; then
        if command -v brew >/dev/null 2>&1; then
            brew install ollama
            brew services start ollama   # arranca Ollama al iniciar sesión
        else
            curl -fsSL https://ollama.com/install.sh | sh
        fi
    fi
    echo "Descargando el modelo '$OLLAMA_MODEL' (la primera vez tarda)..."
    ollama pull "$OLLAMA_MODEL" || echo "  (no se pudo descargar el modelo ahora; corré 'ollama pull $OLLAMA_MODEL' más tarde)"
elif [ "$CHOICE" = "2" ]; then
    LLM_BACKEND="openai"
    printf "Pega tu OPENAI_API_KEY (no se hace eco): "
    read -rs KEY
    OPENAI_KEY_LINE="OPENAI_API_KEY=$KEY"
    echo
else
    LLM_BACKEND="none"
fi

# ---------------- Escribir .env ----------------
ENV_FILE="$HERE/.env"
{
    echo "# Generado por install.sh — editá lo que quieras."
    echo "WHISPERFLOW_MODEL_SIZE=small   # en Mac recomiendo base/tiny (CPU, sin CUDA)"
    echo "WHISPERFLOW_LANGUAGE=es"
    echo "WHISPERFLOW_LLM_BACKEND=$LLM_BACKEND"
    if [ "$LLM_BACKEND" = "ollama" ]; then
        echo "WHISPERFLOW_OLLAMA_BASE_URL=http://localhost:11434/v1"
        echo "WHISPERFLOW_OLLAMA_MODEL=$OLLAMA_MODEL"
    fi
    if [ "$LLM_BACKEND" = "openai" ]; then
        echo "$OPENAI_KEY_LINE"
        echo "WHISPERFLOW_OPENAI_MODEL=gpt-4.1-nano"
    fi
} > "$ENV_FILE"
echo ".env escrito en $ENV_FILE"

# ---------------- Arranque automático (opcional, LaunchAgent) ----------------
printf "¿Arranque automático al iniciar sesión en Mac? [s/N]: "
read -r AUTOSTART
if [[ "$AUTOSTART" =~ ^[sSyY]$ ]]; then
    PLIST="$HOME/Library/LaunchAgents/local.whisperflow.plist"
    mkdir -p "$(dirname "$PLIST")"
    cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>local.whisperflow</string>
  <key>ProgramArguments</key>
  <array>
    <string>$HERE/$VENV_DIR/bin/python</string>
    <string>$HERE/whisperflow.py</string>
  </array>
  <key>WorkingDirectory</key><string>$HERE</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><false/>
</dict></plist>
EOF
    launchctl load "$PLIST" 2>/dev/null || true
    echo "LaunchAgent instalado: $PLIST"
fi

# ---------------- Permisos (Accesibilidad / Input Monitoring) ----------------
cat <<'NOTA'

======================  PERMISOS IMPORTANTES  ======================
Para que los atajos globales y el pegado funcionen en Mac, dale permisos a la
terminal (o a Python) que usaste:
  Configuración del Sistema > Privacidad y seguridad > Accesibilidad   -> activar
  Configuración del Sistema > Privacidad y seguridad > Supervisión de entrada -> activar
Sin esto, los atajos NO funcionarán (fallan silenciosamente).
------------------------------------------------------------------

NOTA

echo "Listo. Para correr WhisperFlow:"
echo "  $HERE/$VENV_DIR/bin/python whisperflow.py"
echo
echo "Atajos en Mac: Cmd+Ctrl (push-to-talk), Cmd+Ctrl+Espacio (manos libres),"
echo "Cmd+Shift+Z (re-pegar último). Los tone-keys (,/./-) eligen perfil pero NO se"
echo "bloquean (limitación conocida de esta versión)."
