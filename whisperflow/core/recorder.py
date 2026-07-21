# -*- coding: utf-8 -*-
"""Grabación de audio del micrófono (núcleo multiplataforma, vía sounddevice).

El callback de audio corre en el hilo de PortAudio; por eso usa un lock para
``_frames`` pero NO para ``current_mic_level`` (ver abajo: es intencional).
"""
import threading
import numpy as np
import sounddevice as sd

from whisperflow.core.config import SAMPLE_RATE  # centralizado en config (Fase 2)

# Nivel de volumen en vivo (0..1), actualizado por el callback de audio (hilo de
# PortAudio) y leído por el overlay. Es un float global SIN lock a propósito: es
# solo cosmético (las barritas animadas), una lectura levemente "vieja" es
# inofensiva y el GIL hace que un solo float sea seguro para esto sin lock.
current_mic_level = 0.0


class Recorder:
    def __init__(self):
        self._frames = []
        self._stream = None
        self._lock = threading.Lock()

    def start(self):
        with self._lock:
            self._frames = []
            self._stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                                          callback=self._callback)
            self._stream.start()

    def _callback(self, indata, frames, time_info, status):
        with self._lock:
            self._frames.append(indata.copy())
        global current_mic_level
        rms = float(np.sqrt(np.mean(np.square(indata)))) if len(indata) else 0.0
        current_mic_level = min(1.0, rms * 9.0)

    def stop(self):
        with self._lock:
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
                self._stream = None
            if not self._frames:
                return np.zeros((0,), dtype="float32")
            audio = np.concatenate(self._frames, axis=0).flatten()
            self._frames = []
            return audio
