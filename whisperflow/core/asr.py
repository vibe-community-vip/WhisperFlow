# -*- coding: utf-8 -*-
"""Dispatcher del motor ASR: elige mlx (Apple Silicon, GPU) o faster_whisper (CPU/CUDA).

``ASR_ENGINE`` viene de ``config`` ("mlx" en Mac arm64 por defecto, "faster_whisper" en
el resto). Expone la misma interfaz que usaba el monolito: ``ensure_loaded``, ``is_loaded``,
``transcribe``.
"""
from whisperflow.core import config

if config.ASR_ENGINE == "mlx":
    from whisperflow.core.asr_mlx import ensure_loaded, is_loaded, transcribe  # noqa: F401
else:
    from whisperflow.core.asr_ct2 import ensure_loaded, is_loaded, transcribe  # noqa: F401
