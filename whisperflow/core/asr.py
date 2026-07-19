# -*- coding: utf-8 -*-
"""Motor de transcripción faster-whisper (núcleo multiplataforma, carga perezosa).

Fase 2: el modelo **no** se carga al importar el módulo (arranque instantáneo de la
bandeja). Se carga en un hilo en background al iniciar la app (ver ``app.run``) y,
como red de seguridad, bajo demanda en ``ensure_loaded``. Mientras no esté listo, la
máquina de estados bloquea el inicio de la grabación (overlay "loading" + beep).

IMPORTANTE — orden de inicialización: ``register_cuda_dlls()`` debe ejecutarse ANTES
de ``from faster_whisper import WhisperModel`` para que ctranslate2 encuentre
cublas/cudnn instalados vía pip sin depender de torch-CUDA.
"""
import os
import threading

from whisperflow.core.config import MODEL_SIZE, LANGUAGE

_load_lock = threading.Lock()


def register_cuda_dlls():
    # Agrega al PATH los dir de cublas/cudnn de los paquetes pip nvidia-* para que
    # ctranslate2 los encuentre sin depender de una instalación de torch-CUDA.
    try:
        import nvidia
        for nbase in list(nvidia.__path__):
            for sub in ("cublas", "cudnn"):
                bindir = os.path.join(nbase, sub, "bin")
                if os.path.isdir(bindir):
                    os.add_dll_directory(bindir)
                    os.environ["PATH"] = bindir + os.pathsep + os.environ.get("PATH", "")
    except Exception:
        pass


# Debe ir ANTES de importar WhisperModel (ver comentario de la sección).
register_cuda_dlls()
from faster_whisper import WhisperModel  # noqa: E402

MODEL = None  # se carga perezosamente en ensure_loaded()


def _load_model():
    for dev, ct in [("cuda", "float16"), ("cuda", "int8_float16"), ("cuda", "int8"), ("cpu", "int8")]:
        try:
            m = WhisperModel(MODEL_SIZE, device=dev, compute_type=ct)
            print(f"[whisperflow] modelo '{MODEL_SIZE}' cargado en {dev}/{ct}", flush=True)
            return m
        except Exception as e:
            print(f"[whisperflow] no se pudo {dev}/{ct}: {str(e)[:120]}", flush=True)
    raise RuntimeError("No se pudo cargar el modelo Whisper en ningún dispositivo")


def ensure_loaded():
    """Carga el modelo si no lo está aún. Seguro en hilos (double-checked locking)."""
    global MODEL
    if MODEL is not None:
        return
    with _load_lock:
        if MODEL is not None:
            return
        print(f"[whisperflow] cargando modelo '{MODEL_SIZE}'... (la primera vez tarda)", flush=True)
        MODEL = _load_model()


def is_loaded():
    return MODEL is not None


def transcribe(audio, language=LANGUAGE, initial_prompt=None):
    ensure_loaded()
    segments, _ = MODEL.transcribe(audio, language=language, beam_size=5,
                                   vad_filter=True, condition_on_previous_text=True,
                                   initial_prompt=initial_prompt)
    return "".join(s.text for s in segments).strip()
