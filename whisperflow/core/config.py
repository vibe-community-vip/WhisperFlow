# -*- coding: utf-8 -*-
"""Configuración centralizada de WhisperFlow.

Carga un archivo ``.env`` en la raíz del proyecto (si existe) **sin** depender de
python-dotenv: un loader mínimo que lee ``KEY=VALUE`` línea por línea. Las variables
del entorno del SO tienen prioridad sobre el ``.env``; el ``.env`` tiene prioridad
sobre los defaults.

Las constantes que antes estaban hardcodeadas en ``whisperflow.py`` se centralizan
acá. Todo lo ajustable de la app pasa por este módulo: no hay UI de configuración.
"""
import os
import sys
import platform

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG = os.path.dirname(_HERE)
PROJECT_ROOT = os.path.dirname(_PKG)
ENV_PATH = os.path.join(PROJECT_ROOT, ".env")


def _load_env_file(path):
    """Lee KEY=VALUE de un .env. Ignora comentarios (#) y vacías; comillas opcionales."""
    data = {}
    try:
        # utf-8-sig y no utf-8: el Bloc de notas de Windows y el Out-File de
        # PowerShell guardan con BOM. Con utf-8 puro, ese BOM se pega al nombre de
        # la PRIMERA clave ("﻿WHISPERFLOW_LANGUAGE") y esa línea se pierde en
        # silencio. utf-8-sig lo descarta y es idéntico si no hay BOM.
        with open(path, "r", encoding="utf-8-sig") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip()
                # Quitar comentarios en línea (" # ...") solo si el valor NO está entre
                # comillas. Sin esto, "KEY=base  # nota" se lee como "base  # nota".
                if val and val[0] not in ('"', "'"):
                    if val.lstrip().startswith("#"):
                        val = ""
                    else:
                        idx = val.find(" #")
                        if idx != -1:
                            val = val[:idx].rstrip()
                if len(val) >= 2 and ((val[0] == val[-1] == '"') or (val[0] == val[-1] == "'")):
                    val = val[1:-1]
                data[key] = val
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"[whisperflow] no se pudo leer .env ({e})", flush=True)
    return data


_ENV_FILE = _load_env_file(ENV_PATH)


def get(name, default=""):
    """Prioridad: entorno del SO > .env > default."""
    if name in os.environ:
        return os.environ[name]
    return _ENV_FILE.get(name, default)


def get_bool(name, default=False):
    return get(name, "1" if default else "0").strip().lower() in ("1", "true", "yes", "on")


# --- Transcripción (faster-whisper) ---
# tiny|base|small|medium|large-v3|large-v3-turbo (o cualquier repo de HF compatible).
MODEL_SIZE = get("WHISPERFLOW_MODEL_SIZE", "medium")
LANGUAGE = get("WHISPERFLOW_LANGUAGE", "es")
SAMPLE_RATE = int(get("WHISPERFLOW_SAMPLE_RATE", "16000"))
# beam_size del decodificador: más ancho = un poco más preciso y más lento.
BEAM_SIZE = int(get("WHISPERFLOW_BEAM_SIZE", "5"))

# --- Micrófono (captura permanente + pre-roll) ---
# Abrir el stream al pulsar el atajo cuesta ~120 ms reales (medido) y ese audio se
# perdía. Con el micrófono armado desde el arranque, el instante del atajo se
# captura completo y el pre-roll rescata lo dicho justo antes. Contrapartida: el
# indicador de "micrófono en uso" del SO queda encendido siempre (el audio nunca
# sale de un buffer en memoria que se descarta solo). Poné 0 para volver al modo
# anterior (abrir/cerrar el micrófono en cada dictado).
MIC_ALWAYS_ON = get_bool("WHISPERFLOW_MIC_ALWAYS_ON", True)
PREROLL_MS = int(get("WHISPERFLOW_PREROLL_MS", "350"))

# --- Beeps ---
# Ventana para cancelar el bip de push-to-talk si el atajo asciende a manos libres
# (Ctrl+Win y después Espacio). Solo difiere el SONIDO; la grabación empieza igual
# al instante. 0 = bip inmediato (vuelven a oírse dos tonos al entrar a manos libres).
HANDSFREE_GRACE_MS = int(get("WHISPERFLOW_HANDSFREE_GRACE_MS", "220"))

# --- Debug ---
DEBUG = get_bool("WHISPERFLOW_DEBUG", False)

# --- Mac: backend de hotkeys ---
# cgevent = nativo vía CGEventTap (DEFAULT): NO pasa por HIServices.AXIsProcessTrusted
#   (que crashea con algunos combos pynput+pyobjc).
# pynput = fallback (puede crashear según versiones de pyobjc).
MAC_HOTKEY = get("WHISPERFLOW_MAC_HOTKEY", "cgevent").lower()

# --- Atajos configurables (nombres canónicos: super, ctrl, alt, shift, space, o un char) ---
# super = Win (Win/Linux) o Cmd (Mac). Así una sola config sirve en todos los SO.
def _csv(s):
    return [x.strip() for x in (s or "").split(",") if x.strip()]

PTT_KEYS = set(_csv(get("WHISPERFLOW_PTT_KEYS", "super,ctrl")))        # modificadores para push-to-talk
HANDSFREE_KEY = get("WHISPERFLOW_HANDSFREE_KEY", "space").strip()      # asciende a manos libres (con PTT sostenido)
REPASTE_KEYS = _csv(get("WHISPERFLOW_REPASTE_KEYS", "ctrl,alt,z"))     # acorde para re-pegar último texto

# --- Motor ASR ---
# faster-whisper (ctranslate2) NO soporta Metal: en Apple Silicon es CPU-only.
# mlx-whisper usa la GPU unificada (Metal) => mucho más rápido en M-series.
#   "" (auto) = mlx en Mac arm64, faster_whisper en el resto.
ASR_ENGINE = get("WHISPERFLOW_ASR_ENGINE", "").strip().lower()
if ASR_ENGINE not in ("mlx", "faster_whisper"):
    ASR_ENGINE = "mlx" if (sys.platform == "darwin" and platform.machine() == "arm64") else "faster_whisper"
MLX_MODEL = get("WHISPERFLOW_MLX_MODEL", "mlx-community/whisper-large-v3-mlx-4bit")

# --- VAD (descarta capturas mudas ANTES de transcribir) ---
# Whisper alucina texto repetido sobre audio casi mudo; este filtro por energía lo
# evita. Medido en la Mac de referencia: silencio ~RMS 0.003, dictado real ~0.1-0.2.
# VAD_THRESHOLD queda ~3× sobre el silencio y ~12× bajo el habla => no rompe dictado.
# Si alguna vez te rechaza dictado real (poco probable), bajá el umbral o poned
# WHISPERFLOW_VAD=0 para desactivarlo.
VAD_ENABLED = get_bool("WHISPERFLOW_VAD", True)
VAD_THRESHOLD = float(get("WHISPERFLOW_VAD_THRESHOLD", "0.008"))   # RMS por trama (float32, 0..1)
VAD_MIN_FRAMES = int(get("WHISPERFLOW_VAD_MIN_FRAMES", "3"))        # tramas mínimas sobre el umbral
VAD_FRAME_MS = int(get("WHISPERFLOW_VAD_FRAME_MS", "30"))           # tamaño de trama de análisis

# Pico por debajo del cual se avisa de audio flojo (no descarta nada, solo avisa).
# Está muy por encima del umbral del VAD a propósito: entre 0.008 y 0.05 el dictado
# SE TRANSCRIBE, pero mal, y esa franja es la que confunde — parece que el modelo es
# malo cuando en realidad el micrófono está lejos o bajo.
WEAK_SIGNAL_PEAK = float(get("WHISPERFLOW_WEAK_SIGNAL_PEAK", "0.05"))
