# -*- coding: utf-8 -*-
"""Motor ASR con mlx-whisper (Apple Silicon, GPU Metal / memoria unificada).

Mucho más rápido que faster-whisper (CPU) en M-series. El modelo se descarga de HF la
primera vez (lo forzamos en ``ensure_loaded`` con ``snapshot_download`` para dar feedback
de progreso al arrancar, igual que el motor faster-whisper).
"""
import threading

from whisperflow.core import config

_load_lock = threading.Lock()
_loaded = False


def ensure_loaded():
    global _loaded
    if _loaded:
        return
    with _load_lock:
        if _loaded:
            return
        print(f"[whisperflow] precargando modelo MLX '{config.MLX_MODEL}' "
              f"(descarga la primera vez)...", flush=True)
        try:
            from huggingface_hub import snapshot_download
            snapshot_download(config.MLX_MODEL)   # descarga/cacha el modelo (feedback de progreso)
            import mlx_whisper  # noqa: F401  (confirma que importa)
            _loaded = True
            print(f"[whisperflow] modelo MLX '{config.MLX_MODEL}' listo (GPU Metal).", flush=True)
        except Exception as e:
            print(f"[whisperflow] no se pudo precargar MLX: {e}", flush=True)
            raise


def is_loaded():
    return _loaded


def transcribe(audio, language=None, initial_prompt=None):
    import mlx_whisper
    lang = language or config.LANGUAGE
    result = mlx_whisper.transcribe(audio, path_or_hf_repo=config.MLX_MODEL,
                                    language=lang, initial_prompt=initial_prompt)
    return (result.get("text") or "").strip()
