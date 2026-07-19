# -*- coding: utf-8 -*-
"""Señales sonoras (núcleo): síntesis WAV compartida + interfaz BeepBackend.

Cada backend (Windows/Mac/Linux) implementa ``_play_wav(data)`` con la API de
audio de su OS; el resto (síntesis del tono, hilo por beep, los beeps semánticos)
es compartido y vive aquí.
"""
import io
import wave
import threading
import numpy as np

BEEP_VOLUME = 0.04        # 0.0 (silencio) - 1.0 (volumen máximo)
BEEP_SAMPLE_RATE = 44100  # tasa propia del beep, independiente de la del micrófono


def make_beep_wav(freq, dur_ms, volume=BEEP_VOLUME, samplerate=BEEP_SAMPLE_RATE):
    n = int(samplerate * dur_ms / 1000)
    t = np.linspace(0, dur_ms / 1000, n, endpoint=False)
    tone = np.sin(2 * np.pi * freq * t)
    # fade in/out corto para evitar "click" audible al inicio/fin
    fade = min(n // 8, int(samplerate * 0.005)) or 1
    envelope = np.ones_like(tone)
    envelope[:fade] = np.linspace(0, 1, fade)
    envelope[-fade:] = np.linspace(1, 0, fade)
    samples = (tone * envelope * volume * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(samplerate)
        wf.writeframes(samples.tobytes())
    return buf.getvalue()


class BaseBeepBackend:
    """Cada subclase implementa ``_play_wav``. Los métodos públicos son los beeps
    semánticos del monolito original (mismas frecuencias/duraciones)."""

    def _play_wav(self, data: bytes):
        raise NotImplementedError

    def _beep(self, freq, dur_ms):
        # Un hilo por beep: el original bloquea el audio de forma síncrona dentro de
        # este hilo (ver backends/windows/beep.py), así que no afecta al resto.
        def _play():
            try:
                data = make_beep_wav(freq, dur_ms)
                self._play_wav(data)
            except Exception:
                pass
        threading.Thread(target=_play, daemon=True).start()

    def recording_start(self):
        self._beep(880, 90)

    def hands_free_on(self):
        self._beep(880, 70)
        threading.Timer(0.09, lambda: self._beep(1200, 70)).start()

    def pasted(self):
        self._beep(1400, 100)

    def no_speech(self):
        self._beep(300, 180)

    def profile_friendly(self):
        self._beep(1000, 60)

    def profile_professional(self):
        self._beep(500, 60)

    def profile_reset(self):
        self._beep(700, 60)
