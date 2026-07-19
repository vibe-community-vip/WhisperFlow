# -*- coding: utf-8 -*-
"""Configuración centralizada de WhisperFlow.

Carga un archivo ``.env`` en la raíz del proyecto (si existe) **sin** depender de
python-dotenv: un loader mínimo que lee ``KEY=VALUE`` línea por línea. Las variables
del entorno del SO tienen prioridad sobre el ``.env``; el ``.env`` tiene prioridad
sobre los defaults.

Las constantes que antes estaban hardcodeadas en ``whisperflow.py`` se centralizan
acá, con los MISMOS valores por defecto -> sin cambio de comportamiento si no hay
``.env``. (La app de Fase 1/2 todavía usa sus propias constantes; Fase 2/3 las migra
a leer de aquí.)
"""
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG = os.path.dirname(_HERE)
PROJECT_ROOT = os.path.dirname(_PKG)
ENV_PATH = os.path.join(PROJECT_ROOT, ".env")


def _load_env_file(path):
    """Lee KEY=VALUE de un .env. Ignora comentarios (#) y vacías; comillas opcionales."""
    data = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip()
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
MODEL_SIZE = get("WHISPERFLOW_MODEL_SIZE", "small")   # tiny|base|small|medium|large-v3
LANGUAGE = get("WHISPERFLOW_LANGUAGE", "es")
SAMPLE_RATE = int(get("WHISPERFLOW_SAMPLE_RATE", "16000"))

# --- Backend de reescritura de tono (Fase 3) ---
LLM_BACKEND = get("WHISPERFLOW_LLM_BACKEND", "auto").lower()    # auto|ollama|openai|none
OLLAMA_BASE_URL = get("WHISPERFLOW_OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL = get("WHISPERFLOW_OLLAMA_MODEL", "qwen2.5:3b")
OPENAI_MODEL = get("WHISPERFLOW_OPENAI_MODEL", "gpt-4.1-nano")
OPENAI_API_KEY = get("OPENAI_API_KEY", "")

# --- Debug ---
DEBUG = get_bool("WHISPERFLOW_DEBUG", False)

# --- Mac: backend de hotkeys (Fase 5) ---
# pynput = estable, sin supresión de tone-keys. cgevent = nativo, SUPRIME tone-keys
# (experimental, requiere Accesibilidad + Supervisión de entrada).
MAC_HOTKEY = get("WHISPERFLOW_MAC_HOTKEY", "pynput").lower()
