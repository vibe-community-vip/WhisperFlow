# -*- coding: utf-8 -*-
"""Historial de recall para Ctrl+Alt+Z (núcleo multiplataforma, sin dependencias de SO).

Recuerda hasta las últimas ``MAX_RECALL`` transcripciones y permite ciclar hacia
atrás con pulsaciones repetidas del mismo atajo, siempre que no se dicte nada nuevo
en el medio (una transcripción nueva reinicia el ciclo a la más reciente).

Persistido en disco (``RECALL_PATH``) para que sobreviva a reinicios de la app:
antes este estado vivía solo en una variable en memoria (``Application.
_last_transcribed_text``) y se perdía cada vez que el proceso se reiniciaba, que es
justo lo que hacía parecer roto a Ctrl+Alt+Z después de cualquier reinicio.
"""
import os
import json
import threading
from collections import deque

from whisperflow.core import config

MAX_RECALL = 3
RECALL_PATH = os.path.join(config.PROJECT_ROOT, "last_recordings.json")

_lock = threading.Lock()


def _load_history():
    try:
        with open(RECALL_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return deque((t for t in data if isinstance(t, str)), maxlen=MAX_RECALL)
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"[whisperflow] no se pudo leer last_recordings.json: {e}", flush=True)
    return deque(maxlen=MAX_RECALL)


def _save_history():
    try:
        with open(RECALL_PATH, "w", encoding="utf-8") as f:
            json.dump(list(_history), f, ensure_ascii=False)
    except Exception as e:
        print(f"[whisperflow] no se pudo guardar last_recordings.json: {e}", flush=True)


_history = _load_history()  # índice 0 = grabación más reciente
_index = 0                  # próxima posición del historial que se pegará al presionar Ctrl+Alt+Z


def remember(text):
    """Registra una transcripción nueva; reinicia el ciclo de recall a la más reciente."""
    global _index
    with _lock:
        _history.appendleft(text)
        _index = 0
        _save_history()


def recall_next():
    """Devuelve ``(text, posicion_1based, total)`` del siguiente ítem del ciclo, o
    ``(None, 0, 0)`` si todavía no hay historial. Cada llamada avanza el cursor; al
    llegar al final, vuelve a empezar desde la más reciente."""
    global _index
    with _lock:
        if not _history:
            return None, 0, 0
        idx = _index % len(_history)
        text = _history[idx]
        _index = idx + 1
        return text, idx + 1, len(_history)
