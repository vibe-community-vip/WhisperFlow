# -*- coding: utf-8 -*-
"""Beeps en macOS: ``afplay`` sobre un WAV temporal.

Ruta de audio totalmente separada del stream PortAudio de grabación (igual que
``winsound`` en Windows). ``afplay`` viene con macOS, sin dependencias extra.
"""
import os
import subprocess
import tempfile

from whisperflow.core.beep_base import BaseBeepBackend


class MacOSBeepBackend(BaseBeepBackend):
    def _play_wav(self, data: bytes):
        # _play_wav ya corre en su propio hilo (BaseBeepBackend._beep), así que
        # bloquear hasta que termine afplay (corto) es seguro.
        path = None
        try:
            fd, path = tempfile.mkstemp(suffix=".wav")
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            subprocess.run(["afplay", path], check=False)
        except Exception:
            pass
        finally:
            if path:
                try:
                    os.unlink(path)
                except Exception:
                    pass
