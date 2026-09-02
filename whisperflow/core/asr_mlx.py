# -*- coding: utf-8 -*-
"""Motor ASR con mlx-whisper (Apple Silicon, GPU Metal / memoria unificada).

Mucho más rápido que faster-whisper (CPU) en M-series. El modelo se descarga de HF la
primera vez (lo forzamos en ``ensure_loaded`` con ``snapshot_download`` para dar feedback
de progreso al arrancar).

Si el modelo configurado no existe o falla, cae a ``mlx-community/whisper-base-mlx`` para
que el dictado siga disponible (y avisa por consola).
"""
import threading

from whisperflow.core import config

_load_lock = threading.Lock()
_loaded = False
_model = None  # repo que efectivamente se cargó (usado en transcribe)
_no_condition_kwarg = False  # avisar una sola vez si mlx no soporta el argumento


def ensure_loaded():
    global _loaded, _model
    if _loaded:
        return
    with _load_lock:
        if _loaded:
            return
        # Probar el modelo configurado; si falla, caer a base-mlx (siempre disponible).
        candidates = [config.MLX_MODEL]
        if config.MLX_MODEL != "mlx-community/whisper-base-mlx":
            candidates.append("mlx-community/whisper-base-mlx")
        last_err = None
        for repo in candidates:
            print(f"[whisperflow] precargando modelo MLX '{repo}' "
                  f"(descarga la primera vez)...", flush=True)
            try:
                from huggingface_hub import snapshot_download
                snapshot_download(repo)
                import mlx_whisper  # noqa: F401
                _model = repo
                _loaded = True
                print(f"[whisperflow] modelo MLX '{repo}' listo (GPU Metal).", flush=True)
                return
            except Exception as e:
                last_err = e
                print(f"[whisperflow] no se pudo cargar MLX '{repo}': {str(e)[:140]}", flush=True)
                if repo != candidates[-1]:
                    print("[whisperflow] reintentando con un modelo alternativo...", flush=True)
        print(f"[whisperflow] FALLO la carga de MLX: {last_err}", flush=True)
        raise RuntimeError(f"No se pudo cargar ningún modelo MLX (último error: {last_err})")


def is_loaded():
    return _loaded


def transcribe(audio, language=None, initial_prompt=None):
    import mlx_whisper
    lang = language or config.LANGUAGE
    # condition_on_previous_text=False por el mismo motivo que en asr_ct2: cada
    # dictado es independiente y arrastrar contexto dispara bucles de repetición.
    #
    # El try/except NO es paranoia decorativa: este backend solo corre en Apple
    # Silicon y no se pudo ejecutar durante el desarrollo. Si alguna versión de
    # mlx-whisper no acepta ese argumento, sin esto CADA dictado moriría con
    # TypeError dentro del hilo de transcripción — es decir, la app parecería
    # "no transcribir nada" sin explicar por qué. Preferimos perder la opción.
    kwargs = dict(path_or_hf_repo=_model or config.MLX_MODEL, language=lang,
                  initial_prompt=initial_prompt, condition_on_previous_text=False)
    try:
        result = mlx_whisper.transcribe(audio, **kwargs)
    except TypeError as e:
        global _no_condition_kwarg
        if not _no_condition_kwarg:
            print(f"[whisperflow] mlx-whisper no acepta condition_on_previous_text "
                  f"({e}); se sigue sin esa opción.", flush=True)
            _no_condition_kwarg = True
        kwargs.pop("condition_on_previous_text", None)
        result = mlx_whisper.transcribe(audio, **kwargs)
    return (result.get("text") or "").strip()
