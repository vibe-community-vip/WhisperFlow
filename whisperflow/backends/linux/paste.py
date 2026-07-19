# -*- coding: utf-8 -*-
"""Pegado en Linux: X11 (xclip + xdotool) o Wayland (wl-copy + wtype), según la sesión.

X11 está soportado. Wayland es best-effort: la inyección de teclas (Ctrl+V) y los
hotkeys globales están restringidos por el compositor; ``wtype``/``wl-copy`` funcionan
en algunos compositores pero no en todos.
"""
import os
import subprocess

from whisperflow.core.paste_base import PasteBackend


def _session_type():
    return os.environ.get("XDG_SESSION_TYPE", "x11").lower()


class LinuxPasteBackend(PasteBackend):
    def __init__(self, hotkey, beep):
        self._hotkey = hotkey
        self._beep = beep

    def paste(self, text: str):
        st = _session_type()
        payload = (text + " ").encode("utf-8")
        try:
            if st == "wayland":
                # wl-copy + wtype (secuencia: presionar ctrl, v, soltar ctrl).
                subprocess.run(["wl-copy", text + " "], check=False)
                subprocess.run(["wtype", "-M", "ctrl", "-k", "v", "-m", "ctrl"], check=False)
            else:  # x11
                try:
                    import pyperclip
                    pyperclip.copy(text + " ")
                except Exception:
                    subprocess.run(["xclip", "-selection", "clipboard"], input=payload, check=False)
                subprocess.run(["xdotool", "key", "ctrl+v"], check=False)
        except Exception as e:
            print(f"[whisperflow] paste Linux falló (sesión={st}): {e}. "
                  "¿Están instalados xclip+xdotool (X11) o wl-copy+wtype (Wayland)?", flush=True)
        self._beep.pasted()
