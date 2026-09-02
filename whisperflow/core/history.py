# -*- coding: utf-8 -*-
"""Historial de transcripciones en markdown (activo por defecto).

Cada transcripción se **anexa** a un archivo markdown con marca de tiempo. Es un
simple archivo de texto local — no sale de la máquina.

Configuración (ver ``.env``):
  - ``WHISPERFLOW_HISTORY``: ``1`` (default, activado) o ``0`` (desactivado).
  - ``WHISPERFLOW_HISTORY_FILE``: ruta del archivo. Vacío => ``<raíz del proyecto>/transcripciones.md``.
    Acepta ``~`` (se expande). Se crea si no existe.

El archivo se abre en modo *append* bajo un lock: seguro entre hilos (varias
transcripciones no se pisan). Si la escritura falla, se loguea y se sigue — **nunca**
rompe el dictado.
"""
import os
import threading
from datetime import datetime

from whisperflow.core import config

_lock = threading.Lock()


def _history_path() -> str:
    custom = config.get("WHISPERFLOW_HISTORY_FILE", "").strip()
    if custom:
        return os.path.expanduser(custom)
    return os.path.join(config.PROJECT_ROOT, "transcripciones.md")


def _enabled() -> bool:
    return config.get_bool("WHISPERFLOW_HISTORY", True)


def append(text):
    """Anexa una transcripción al historial markdown. No lanza."""
    text = (text or "").strip()
    if not text or not _enabled():
        return
    try:
        header = "### " + datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Blockquote: prefijar cada línea con "> " (manejamos textos multilínea).
        quoted = "\n".join("> " + line for line in text.splitlines())
        entry = f"{header}\n\n{quoted}\n\n"

        path = _history_path()
        is_new = not os.path.exists(path)
        with _lock:
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                if is_new:
                    f.write("# Historial de transcripciones — WhisperFlow\n\n")
                f.write(entry)
    except Exception as e:
        print(f"[whisperflow] no se pudo escribir el historial: {e}", flush=True)
