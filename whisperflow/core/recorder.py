# -*- coding: utf-8 -*-
"""Grabación de audio del micrófono (núcleo multiplataforma, vía sounddevice).

**Micrófono siempre armado + pre-roll.** El stream de PortAudio queda abierto desde
que arranca la app y nunca se cierra entre dictados; mientras no se graba, el audio
cae en un buffer circular corto (``PREROLL_MS``) que se descarta solo. Al pulsar el
atajo, ese buffer se usa como *semilla* de la grabación.

Por qué: abrir el ``sd.InputStream`` en el momento de pulsar cuesta tiempo real —
medido en la máquina de referencia (Windows/MME): **~90 ms de construcción + ~34 ms
hasta el primer callback ≈ 120 ms**, y ~470 ms la primera vez del proceso. Ese audio
simplemente no existía, así que las primeras sílabas se perdían y Whisper transcribía
una frase mutilada (era la sensación de "no graba bien hasta después del bip"). Con el
stream ya abierto, el instante del atajo se captura completo, y el pre-roll agrega
además lo dicho *justo antes* de pulsar.

Contrapartida: el micrófono figura como "en uso" de forma permanente (el indicador
de privacidad del SO queda encendido). El audio nunca sale del buffer en memoria, se
descarta continuamente y no se escribe a disco. Se puede volver al comportamiento
anterior (abrir/cerrar por dictado) con ``WHISPERFLOW_MIC_ALWAYS_ON=0``.

El callback de audio corre en el hilo de PortAudio; por eso usa un lock para los
buffers pero NO para ``current_mic_level`` (ver abajo: es intencional).
"""
import threading
from collections import deque

import numpy as np
import sounddevice as sd

from whisperflow.core.config import SAMPLE_RATE, MIC_ALWAYS_ON, PREROLL_MS

# Nivel de volumen en vivo (0..1), actualizado por el callback de audio (hilo de
# PortAudio) y leído por el overlay. Es un float global SIN lock a propósito: es
# solo cosmético (las barritas animadas), una lectura levemente "vieja" es
# inofensiva y el GIL hace que un solo float sea seguro para esto sin lock.
current_mic_level = 0.0

_EMPTY = np.zeros((0,), dtype="float32")


class Recorder:
    def __init__(self):
        self._lock = threading.Lock()
        self._frames = []            # bloques de la grabación en curso
        self._preroll = deque()      # bloques recientes mientras NO se graba
        self._preroll_samples = 0
        self._capturing = False
        self._stream = None
        self._preroll_max = int(SAMPLE_RATE * PREROLL_MS / 1000) if MIC_ALWAYS_ON else 0

    # --- stream persistente ---
    def arm(self):
        """Abre el stream y lo deja escuchando. Se llama al arrancar la app.
        No lanza: si el micrófono no está disponible todavía, ``start()`` reintenta."""
        if not MIC_ALWAYS_ON:
            return False
        try:
            self._ensure_stream()
            return True
        except Exception as e:
            print(f"[whisperflow] no se pudo armar el micrófono ({e}); "
                  "se abrirá al grabar (se perderán ~120 ms al inicio)", flush=True)
            return False

    def _ensure_stream(self):
        """Abre el stream si no hay uno vivo. Llamar SIN el lock (abrir el
        dispositivo puede bloquear ~100 ms y el callback necesita el lock)."""
        stream = self._stream
        if stream is not None:
            try:
                if stream.active:
                    return
            except Exception:
                pass
            self._close_stream()
        stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                                callback=self._callback)
        stream.start()
        self._stream = stream

    def _close_stream(self):
        stream, self._stream = self._stream, None
        if stream is None:
            return
        try:
            stream.stop()
            stream.close()
        except Exception:
            pass

    # --- callback de PortAudio ---
    def _callback(self, indata, frames, time_info, status):
        block = indata.copy()
        with self._lock:
            if self._capturing:
                self._frames.append(block)
            elif self._preroll_max:
                self._preroll.append(block)
                self._preroll_samples += len(block)
                while self._preroll_samples > self._preroll_max and len(self._preroll) > 1:
                    self._preroll_samples -= len(self._preroll.popleft())
        global current_mic_level
        rms = float(np.sqrt(np.mean(np.square(block)))) if len(block) else 0.0
        current_mic_level = min(1.0, rms * 9.0)

    # --- API de grabación ---
    def start(self):
        """Empieza a acumular audio. Devuelve los ms de pre-roll que se rescataron."""
        try:
            self._ensure_stream()
        except Exception as e:
            print(f"[whisperflow] no se pudo abrir el micrófono: {e}", flush=True)
            return 0.0
        with self._lock:
            if self._capturing:
                return 0.0
            # Semilla: lo que ya se venía escuchando antes de pulsar el atajo.
            self._frames = list(self._preroll)
            rescued = self._preroll_samples
            self._preroll.clear()
            self._preroll_samples = 0
            self._capturing = True
        return 1000.0 * rescued / SAMPLE_RATE

    def stop(self):
        """Corta la grabación y devuelve el audio (float32 mono). Deja el stream
        abierto: cerrarlo acá bloqueaba el hilo del hook de teclado y volvía a
        introducir la latencia de apertura en el siguiente dictado."""
        with self._lock:
            self._capturing = False
            frames, self._frames = self._frames, []
            # No arrastrar la cola de esta grabación al pre-roll de la siguiente.
            self._preroll.clear()
            self._preroll_samples = 0
        if not MIC_ALWAYS_ON:
            self._close_stream()
        if not frames:
            return _EMPTY
        return np.concatenate(frames, axis=0).flatten()

    def close(self):
        self._close_stream()
