# -*- coding: utf-8 -*-
"""Motor de transcripción faster-whisper (núcleo multiplataforma).

IMPORTANTE — orden de inicialización: ``register_cuda_dlls()`` debe ejecutarse
ANTES de ``from faster_whisper import WhisperModel`` para que ctranslate2
encuentre cublas/cudnn instalados vía pip sin depender de torch-CUDA. Ese orden
era implícito en el monolito (tope de archivo); aquí se hace explícito.

Fase 1: carga *eager* del modelo al importar el módulo (igual que el monolito).
Fase 2 la vuelve perezosa (hilo en background con feedback en la bandeja).
"""
import os

MODEL_SIZE = "small"       # ya cacheado localmente; rápido y preciso en español
LANGUAGE = "es"


def register_cuda_dlls():
    # Agrega al PATH los directorios cublas/cudnn de los paquetes pip nvidia-* para
    # que ctranslate2 los encuentre sin depender de una instalación de torch-CUDA.
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


def load_model():
    for dev, ct in [("cuda", "float16"), ("cuda", "int8_float16"), ("cuda", "int8"), ("cpu", "int8")]:
        try:
            m = WhisperModel(MODEL_SIZE, device=dev, compute_type=ct)
            print(f"[whisperflow] modelo '{MODEL_SIZE}' cargado en {dev}/{ct}", flush=True)
            return m
        except Exception as e:
            print(f"[whisperflow] no se pudo {dev}/{ct}: {str(e)[:120]}", flush=True)
    raise SystemExit("No se pudo cargar el modelo Whisper")


# Carga eager (Fase 1). Fase 2 la reemplaza por carga perezosa.
MODEL = load_model()


def is_loaded():
    return MODEL is not None


def transcribe(audio, language=LANGUAGE, initial_prompt=None):
    segments, _ = MODEL.transcribe(audio, language=language, beam_size=5,
                                   vad_filter=True, condition_on_previous_text=True,
                                   initial_prompt=initial_prompt)
    return "".join(s.text for s in segments).strip()
