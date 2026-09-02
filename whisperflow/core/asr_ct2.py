# -*- coding: utf-8 -*-
"""Motor ASR con faster-whisper / ctranslate2 (CPU en Mac; CUDA en Win/Linux con GPU NVIDIA).

ctranslate2 NO tiene backend Metal => en Apple Silicon es CPU-only (usa mlx para GPU).
Carga perezosa. ``register_cuda_dlls()`` debe ejecutarse ANTES de importar WhisperModel.
"""
import os
import threading

from whisperflow.core.config import BEAM_SIZE, LANGUAGE, MODEL_SIZE

# Windows sin "modo desarrollador" no deja crear symlinks, y la caché de Hugging Face
# los usa por defecto: descargar un modelo que todavía no esté cacheado revienta con
# "WinError 1314: El cliente no dispone de un privilegio requerido" (verificado al
# bajar large-v3-turbo). Con esto la caché copia en vez de enlazar y la descarga
# funciona sin permisos especiales. Hay que ponerlo ANTES de importar nada de HF.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

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
    segments, _ = MODEL.transcribe(
        audio, language=language, beam_size=BEAM_SIZE,
        vad_filter=True,
        # condition_on_previous_text=False: cada dictado es independiente, no la
        # continuación del anterior. Con True, Whisper arrastra el texto ya decodificado
        # como contexto y es la causa clásica de los bucles de repetición ("...y y y y").
        # Ojo: NO desactiva el initial_prompt — este sí llega al primer bloque de 30 s,
        # que es donde cae cualquier dictado normal (verificado con el diccionario real).
        condition_on_previous_text=False,
        initial_prompt=initial_prompt)
    return "".join(s.text for s in segments).strip()
