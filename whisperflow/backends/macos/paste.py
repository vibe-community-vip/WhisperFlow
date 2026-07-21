# -*- coding: utf-8 -*-
"""Pegado en macOS: ``pbcopy`` + Cmd+V sintético vía CGEvent (Quartz).

Usa Quartz directamente (no pynput) porque la síntesis fiable de teclas para pegar
en OTRA app en Mac pasa por CGEventPost, que requiere permiso de Accesibilidad.

**Restaura el portapapeles previo** (igual que el backend de Windows): antes de
pegar lo guardamos con ``pbpaste`` y, tras un ``Cmd+V`` + pausa de 0.6 s, lo
devolvemos con ``pbcopy`` en un hilo daemon. Así dictar no te pisa el portapapeles.
Limitación (compartida con Windows/pyperclip): si tenías algo **no-textual** copiado
(una imagen), ``pbpaste`` no lo emite a stdout => al restaurar el portapapeles queda
vacío. Para dictado de texto (el caso de uso) es correcto.
"""
import subprocess
import threading
import time

from whisperflow.core.paste_base import PasteBackend


def _save_clipboard():
    """Devuelve el contenido actual del portapapeles (bytes) o None si falla."""
    try:
        return subprocess.run(["pbpaste"], capture_output=True).stdout
    except Exception:
        return None


def _restore_clipboard(data: bytes):
    """Vuelve a poner ``data`` (bytes) en el portapapeles vía pbcopy."""
    try:
        p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
        p.communicate(input=data)
    except Exception:
        pass


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
        # 1) Guardar el portapapeles previo para restaurarlo después.
        prev = _save_clipboard()

        # 2) Portapapeles vía pbcopy (propio de macOS; no depende de pyperclip).
        # Espacio final intencional ("text + " ") para separar del cursor.
        try:
            subprocess.run(["pbcopy"], input=(text + " ").encode("utf-8"), check=False)
        except Exception as e:
            print(f"[whisperflow] pbcopy falló: {e}", flush=True)

        # 3) Inyectar Cmd+V en la app con foco.
        try:
            _post_cmd_v()
        except Exception as e:
            print(f"[whisperflow] paste CGEvent falló (¿falta permiso de Accesibilidad?): {e}",
                  flush=True)

        # 4) Restaurar el portapapeles previo tras una pausa (hilo daemon, no bloquea).
        if prev is not None:
            threading.Thread(target=self._restore_after, args=(0.6, prev), daemon=True).start()

        self._beep.pasted()

    @staticmethod
    def _restore_after(delay, data):
        time.sleep(delay)
        _restore_clipboard(data)
