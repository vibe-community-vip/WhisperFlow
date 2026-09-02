# -*- coding: utf-8 -*-
"""Señales sonoras (núcleo): síntesis WAV compartida + interfaz BeepBackend.

Cada backend (Windows/Mac/Linux) implementa ``_play_wav(data)`` con la API de
audio de su OS; el resto (síntesis del tono, hilo por beep, los beeps semánticos)
es compartido y vive aquí.

**El beep de inicio es diferido a propósito.** Entrar en manos libres es
físicamente "Ctrl+Win abajo" y después "Espacio": la máquina de estados arranca a
grabar con los modificadores (para no perder audio) y recién asciende a manos
libres con el Espacio. Si cada paso sonara al instante se oían *tres* bips
seguidos. Ahora ``recording_start`` programa su bip con ``HANDSFREE_GRACE_MS`` de
retraso: si el Espacio llega dentro de esa ventana, ese bip se **cancela** y solo
suena el tono de manos libres. Resultado: push-to-talk = un bip; manos libres = un
bip distinto. La grabación **no** se retrasa: lo único diferido es el sonido.
"""
import io
import wave
import threading

import numpy as np

from whisperflow.core.config import HANDSFREE_GRACE_MS

BEEP_VOLUME = 0.04        # 0.0 (silencio) - 1.0 (volumen máximo)
BEEP_SAMPLE_RATE = 44100  # tasa propia del beep, independiente de la del micrófono

# Tonos semánticos (Hz, ms). Manos libres es más grave y más largo que el de
# push-to-talk: se distingue sin ambigüedad y "suena a modo que queda enganchado".
TONE_START = (880, 85)
TONE_HANDS_FREE = (620, 150)
TONE_PASTED = (1400, 100)
TONE_NO_SPEECH = (300, 180)


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
    semánticos que usa la máquina de estados."""

    def __init__(self):
        self._pending = None                 # Timer del beep de inicio, cancelable
        self._pending_lock = threading.Lock()

    def _play_wav(self, data: bytes):
        raise NotImplementedError

    def _beep(self, freq, dur_ms):
        # Un hilo por beep: el backend reproduce de forma síncrona dentro de este
        # hilo (ver backends/windows/beep.py), así que no afecta al resto.
        def _play():
            try:
                self._play_wav(make_beep_wav(freq, dur_ms))
            except Exception:
                pass
        threading.Thread(target=_play, daemon=True).start()

    def _cancel_pending(self):
        # Llamar con _pending_lock tomado.
        if self._pending is not None:
            self._pending.cancel()
            self._pending = None

    def recording_start(self):
        """Bip de inicio de dictado, diferido HANDSFREE_GRACE_MS (ver el docstring
        del módulo). Solo se retrasa el sonido; el audio ya se está grabando."""
        if HANDSFREE_GRACE_MS <= 0:
            self._beep(*TONE_START)
            return
        with self._pending_lock:
            self._cancel_pending()
            timer = threading.Timer(HANDSFREE_GRACE_MS / 1000.0, self._fire_start)
            timer.daemon = True
            self._pending = timer
            timer.start()

    def _fire_start(self):
        with self._pending_lock:
            self._pending = None
        self._beep(*TONE_START)

    def hands_free_on(self):
        """Un único tono, distinto al de push-to-talk. Cancela el bip de inicio si
        todavía no sonó (que es el caso normal al teclear el acorde de una vez)."""
        with self._pending_lock:
            self._cancel_pending()
        self._beep(*TONE_HANDS_FREE)

    def pasted(self):
        self._beep(*TONE_PASTED)

    def no_speech(self):
        with self._pending_lock:
            self._cancel_pending()
        self._beep(*TONE_NO_SPEECH)
