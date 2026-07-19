# -*- coding: utf-8 -*-
"""Pegado en Windows: portapapeles (pyperclip) + Ctrl+V inyectado (lib keyboard)."""
import time
import threading
import pyperclip

from whisperflow.core.paste_base import PasteBackend


class WindowsPasteBackend(PasteBackend):
    def __init__(self, hotkey, beep):
        self._hotkey = hotkey
        self._beep = beep

    def paste(self, text: str):
        # Soltamos Alt/Z por si este pegado fue disparado por un atajo que todavía sigue
        # físicamente presionado (ej. Ctrl+Alt+Z se detecta al bajar la Z, antes de que se
        # suelten los dedos). Si Alt sigue abajo cuando mandamos "ctrl+v", el campo de
        # destino recibe Ctrl+Alt+V en vez de Ctrl+V y no pega nada.
        try:
            self._hotkey.release("alt")
            self._hotkey.release("z")
        except Exception:
            pass

        prev_clipboard = None
        try:
            prev_clipboard = pyperclip.paste()
        except Exception:
            pass

        # Espacio final intencional ("text + " "") para separar del cursor.
        pyperclip.copy(text + " ")
        self._hotkey.send("ctrl+v")
        self._beep.pasted()

        if prev_clipboard is not None:
            def restore():
                time.sleep(0.6)
                try:
                    pyperclip.copy(prev_clipboard)
                except Exception:
                    pass
            threading.Thread(target=restore, daemon=True).start()
