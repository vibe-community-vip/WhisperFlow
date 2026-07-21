# -*- coding: utf-8 -*-
"""Detección de actividad de voz (VAD) por energía, **sin dependencias nuevas**.

Motivo: Whisper (mlx/ctranslate2) **alucina texto repetido** sobre audio casi mudo
(silencio o ruido de fondo muy bajo). Medido en la Mac de referencia, el silencio
ambiente da un pico de RMS ~0.003 (float32), mientras que dictado real (boca cerca
del micrófono) da ~0.1–0.2: hay un margen enorme entre ambos. Este VAD analiza la
energía **por tramas** ANTES de transcribir y descarta las capturas que claramente
no tienen voz, evitando que se pegue texto alucinado.

No distingue voz de ruido sostenido (música, ventilador fuerte): apunta al caso de
silencio/nivel muy bajo. Si en el futuro hiciera falta rechazar ruido, conviene
subir a un VAD neuronal (silero); acá privilegiamos cero dependencias nuevas y un
umbral conservador que no rompa el dictado real.

Configurable vía ``.env`` (ver ``config.py``): ``WHISPERFLOW_VAD``,
``WHISPERFLOW_VAD_THRESHOLD``, ``WHISPERFLOW_VAD_MIN_FRAMES``,
``WHISPERFLOW_VAD_FRAME_MS``.
"""
import numpy as np

from whisperflow.core.config import (
    SAMPLE_RATE, VAD_ENABLED, VAD_THRESHOLD, VAD_MIN_FRAMES, VAD_FRAME_MS,
)


def evaluate(audio, sample_rate=SAMPLE_RATE):
    """Decide si ``audio`` (float32 mono) contiene voz.

    Devuelve un dict::

        {"speech": bool,      # True => hay voz, transcribir
         "peak": float,       # RMS máximo por trama (0..1)
         "active": int,       # nro. de tramas que superan el umbral
         "n_frames": int,     # total de tramas analizadas
         "threshold": float,  # umbral efectivo usado
         "enabled": bool}     # VAD activado?
    """
    if not VAD_ENABLED:
        return {"speech": True, "peak": 0.0, "active": 0, "n_frames": 0,
                "threshold": VAD_THRESHOLD, "enabled": False}

    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    frame = max(1, int(sample_rate * VAD_FRAME_MS / 1000))   # ~480 a 30 ms / 16 kHz
    n = len(audio) // frame
    if n == 0:
        # Menos de una trama: demasiado corto para decidir; se descarta.
        return {"speech": False, "peak": 0.0, "active": 0, "n_frames": 0,
                "threshold": VAD_THRESHOLD, "enabled": True}

    frames = audio[: n * frame].reshape(n, frame)
    rms = np.sqrt(np.mean(frames ** 2, axis=1))              # RMS por trama
    peak = float(rms.max())
    active = int((rms >= VAD_THRESHOLD).sum())
    # Voz <=> el pico supera el piso absoluto Y hay varias tramas fuertes (no un click).
    speech = peak >= VAD_THRESHOLD and active >= VAD_MIN_FRAMES
    return {"speech": bool(speech), "peak": peak, "active": active,
            "n_frames": n, "threshold": VAD_THRESHOLD, "enabled": True}
