#!/usr/bin/env bash
# install.sh — Instalador guiado de WhisperFlow local para macOS y Linux.
# Pensado para no-desarrolladores: detecta el SO, crea el venv, instala dependencias
# (incluidas las del SO: xclip/xdotool/wl-clipboard/wtype en Linux), pregunta por el
# modelo de transcripción, escribe el .env y (opcional)
# instala el arranque automático y guía los permisos.
#
# Uso:  bash install.sh
set -e

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"
OS="$(uname -s)"           # Darwin | Linux

PYTHON_BIN=""
for c in python3.12 python3.11 python3.13 python3; do
  if command -v "$c" >/dev/null 2>&1; then PYTHON_BIN="$c"; break; fi
done
if [ -z "$PYTHON_BIN" ]; then
  echo "No se encontró Python 3. Instálalo desde https://www.python.org/ y vuelve a correr este script." >&2
  exit 1
fi
echo "Sistema: $OS   Python: $PYTHON_BIN ($($PYTHON_BIN --version))"

# ---------------- Dependencias del SO (Linux) ----------------
if [ "$OS" = "Linux" ]; then
  echo "Instalando dependencias del sistema (xclip, xdotool, wl-clipboard, wtype)..."
  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update && sudo apt-get install -y xclip xdotool wl-clipboard wtype || true
  elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y xclip xdotool wl-clipboard wtype || true
  elif command -v pacman >/dev/null 2>&1; then
    sudo pacman -S --noconfirm xclip xdotool wl-clipboard wtype || true
  else
    echo "  (no reconocí tu gestor de paquetes; instalá manualmente xclip xdotool wl-clipboard wtype)"
  fi
  echo "Para que los atajos globales funcionen tu usuario debe poder leer el teclado"
  echo "y escribir a /dev/uinput. Si no funcionan, agregá tu usuario al grupo 'input':"
  echo "  sudo usermod -aG input \$USER   (luego cerrá sesión y volvé a entrar)"
fi

# ---------------- venv + deps Python ----------------
VENV_DIR="venv-mac"; [ "$OS" = "Linux" ] && VENV_DIR="venv-linux"
echo "Creando entorno virtual en $VENV_DIR ..."
"$PYTHON_BIN" -m venv "$VENV_DIR"
PY="$VENV_DIR/bin/python"
echo "Actualizando pip e instalando dependencias (puede tardar varios minutos)..."
"$PY" -m pip install --upgrade pip
"$PY" -m pip install -r requirements.txt

# ---------------- Modelo de transcripción ----------------
# El tamaño del modelo es LA decisión que define exactitud vs. espera. Con GPU
# NVIDIA, "medium" da ~3x menos errores que "small" por ~0.5 s más (medido en una
# RTX 4050; ver scripts/bench_models.py). En CPU, "medium" se siente lento.
if [ "$OS" = "Darwin" ]; then
    MODEL_DEFAULT="base"        # mlx en Apple Silicon usa WHISPERFLOW_MLX_MODEL aparte
elif command -v nvidia-smi >/dev/null 2>&1; then
    MODEL_DEFAULT="medium"
else
    MODEL_DEFAULT="small"
fi

echo
echo "¿Qué modelo de Whisper querés usar?"
echo "  1) small    — el más rápido, el que más se equivoca"
echo "  2) medium   — 3x menos errores que small; ~0.9 s por frase con GPU NVIDIA"
echo "  3) large-v3 — el más pesado (~3 GB de VRAM); más lento y no siempre mejor"
echo "  (podés cambiarlo cuando quieras editando .env, y compararlos con"
echo "   'python scripts/bench_models.py --record --audio-dir bench_audio')"
printf "Elige [1/2/3] (por defecto: %s): " "$MODEL_DEFAULT"
read -r CHOICE
case "$CHOICE" in
    1) MODEL_SIZE="small" ;;
    2) MODEL_SIZE="medium" ;;
    3) MODEL_SIZE="large-v3" ;;
    *) MODEL_SIZE="$MODEL_DEFAULT" ;;
esac

# ---------------- Escribir .env ----------------
ENV_FILE="$HERE/.env"
{
    echo "# Generado por install.sh — editá lo que quieras (ver .env.example para todas las claves)."
    echo "WHISPERFLOW_MODEL_SIZE=$MODEL_SIZE"
    echo "WHISPERFLOW_LANGUAGE=es"
} > "$ENV_FILE"
echo ".env escrito en $ENV_FILE"

# ---------------- Arranque automático (opcional) ----------------
printf "¿Arranque automático al iniciar sesión? [s/N]: "
read -r AUTOSTART
if [[ "$AUTOSTART" =~ ^[sSyY]$ ]]; then
    if [ "$OS" = "Darwin" ]; then
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
    else
        mkdir -p "$HOME/.config/autostart"
        DESKTOP="$HOME/.config/autostart/whisperflow.desktop"
        cat > "$DESKTOP" <<EOF
[Desktop Entry]
Type=Application
Name=WhisperFlow local
Exec=$HERE/$VENV_DIR/bin/python $HERE/whisperflow.py
Path=$HERE
Terminal=false
X-GNOME-Autostart-enabled=true
EOF
        echo "Autostart .desktop instalado: $DESKTOP"
    fi
fi

# ---------------- Permisos / notas por SO ----------------
if [ "$OS" = "Darwin" ]; then
    cat <<'NOTA'

======================  PERMISOS IMPORTANTES (Mac)  ======================
Configuración del Sistema > Privacidad y seguridad:
  - Accesibilidad           -> activar la terminal/Python
  - Supervisión de entrada  -> activar la terminal/Python
Sin esto, los atajos NO funcionan (fallan silenciosamente).
-------------------------------------------------------------------------
NOTA
    echo "Atajos Mac: Cmd+Ctrl (push-to-talk), Cmd+Ctrl+Espacio (manos libres), Cmd+Shift+Z (re-pegar)."
else
    echo
    echo "Notas Linux: sesion X11 = soporte completo. Wayland = best-effort (hotkeys/inyeccion"
    echo "restringidos por el compositor; si falla, probá sesión X11 o vinculá un atajo del"
    echo "compositor. Atajos: Ctrl+Super (PTT), Ctrl+Super+Espacio (manos libres), Ctrl+Alt+Z (re-pegar)."
fi

echo
echo "Listo. Para correr WhisperFlow:"
echo "  $HERE/$VENV_DIR/bin/python whisperflow.py"
