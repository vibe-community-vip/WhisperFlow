# -*- coding: utf-8 -*-
"""Motor ASR con faster-whisper / ctranslate2 (CPU en Mac; CUDA en Win/Linux con GPU NVIDIA).

ctranslate2 NO tiene backend Metal => en Apple Silicon es CPU-only (usa mlx para GPU).
Carga perezosa. ``register_cuda_dlls()`` debe ejecutarse ANTES de importar WhisperModel.
"""
import os
import threading

from whisperflow.core.config import MODEL_SIZE, LANGUAGE

_load_lock = threading.Lock()
MODEL = None  # carga perezosa


def register_cuda_dlls():
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


register_cuda_dlls()
from faster_whisper import WhisperModel  # noqa: E402


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
