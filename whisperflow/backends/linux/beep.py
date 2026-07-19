# -*- coding: utf-8 -*-
"""Beeps en Linux: ``paplay`` (PulseAudio/PipeWire) o ``aplay`` (ALSA) sobre un WAV temporal.

Ruta de audio separada del stream de grabación (igual que winsound/afplay).
"""
import os
import shutil
import subprocess
import tempfile

from whisperflow.core.beep_base import BaseBeepBackend


class LinuxBeepBackend(BaseBeepBackend):
    def _play_wav(self, data: bytes):
        path = None
        try:
            fd, path = tempfile.mkstemp(suffix=".wav")
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            player = "paplay" if shutil.which("paplay") else "aplay"
            subprocess.run([player, path], check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
        finally:
            if path:
                try:
                    os.unlink(path)
                except Exception:
                    pass
