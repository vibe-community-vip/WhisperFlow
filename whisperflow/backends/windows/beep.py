# -*- coding: utf-8 -*-
"""Beeps en Windows: winsound (ruta WinMM, separada del stream de grabación)."""
import winsound

from whisperflow.core.beep_base import BaseBeepBackend


class WindowsBeepBackend(BaseBeepBackend):
    def _play_wav(self, data: bytes):
        # winsound.PlaySound (WAV en memoria vía WinMM) en vez de sounddevice: este
        # último comparte el stream/dispositivo PortAudio de la grabación (sd.InputStream)
        # y tocar un beep con sd.play() mientras se graba competía por ese stream de forma
        # intermitente. WinMM es una ruta de audio totalmente aparte.
        # Síncrono (sin SND_ASYNC) a propósito: SND_MEMORY + SND_ASYNC deja a Windows
        # reproduciendo un buffer que Python puede recolectar antes de terminar, cortando
        # el beep al azar. Como _play_wav ya corre en su propio hilo (BaseBeepBackend._beep),
        # bloquear aquí es seguro y no afecta al resto de la app.
        winsound.PlaySound(data, winsound.SND_MEMORY)
