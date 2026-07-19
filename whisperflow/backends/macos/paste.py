# -*- coding: utf-8 -*-
"""Pegado en macOS: ``pbcopy`` + Cmd+V sintético vía CGEvent (Quartz).

Usa Quartz directamente (no pynput) porque la síntesis fiable de teclas para pegar
en OTRA app en Mac pasa por CGEventPost, que requiere permiso de Accesibilidad.
"""
import subprocess

from whisperflow.core.paste_base import PasteBackend


def _post_cmd_v():
    """Postea un Cmd+V completo vía CGEvent. Requiere Accesibilidad."""
    import Quartz  # pyobjc-framework-Quartz
    src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
    cmd_down = Quartz.CGEventCreateKeyboardEvent(src, 0x37, True)   # left command
    v_down = Quartz.CGEventCreateKeyboardEvent(src, 0x09, True)     # v
    v_up = Quartz.CGEventCreateKeyboardEvent(src, 0x09, False)
    cmd_up = Quartz.CGEventCreateKeyboardEvent(src, 0x37, False)
    Quartz.CGEventSetFlags(v_down, Quartz.kCGEventFlagMaskCommand)
    Quartz.CGEventSetFlags(v_up, Quartz.kCGEventFlagMaskCommand)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, cmd_down)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, v_down)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, v_up)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, cmd_up)


class MacOSPasteBackend(PasteBackend):
    def __init__(self, hotkey, beep):
        self._hotkey = hotkey
        self._beep = beep

    def paste(self, text: str):
        # Portapapeles vía pbcopy (propio de macOS; no depende de pyperclip).
        # Espacio final intencional ("text + " ") para separar del cursor.
        try:
            subprocess.run(["pbcopy"], input=(text + " ").encode("utf-8"), check=False)
        except Exception as e:
            print(f"[whisperflow] pbcopy falló: {e}", flush=True)

        try:
            _post_cmd_v()
        except Exception as e:
            print(f"[whisperflow] paste CGEvent falló (¿falta permiso de Accesibilidad?): {e}",
                  flush=True)

        self._beep.pasted()
