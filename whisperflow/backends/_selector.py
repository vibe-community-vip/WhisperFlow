# -*- coding: utf-8 -*-
"""Selección de backends según el sistema operativo."""
import sys


def select_backends():
    """Devuelve un dict {clave: clase/función} de backends para la plataforma actual."""
    if sys.platform == "win32":
        from .windows.beep import WindowsBeepBackend
        from .windows.overlay import WindowsOverlayBackend
        from .windows.paste import WindowsPasteBackend
        from .windows.hotkey import WindowsHotkeyBackend
        from .windows.startup_init import apply_startup_init
        return {
            "startup_init": apply_startup_init,
            "beep": WindowsBeepBackend,
            "overlay": WindowsOverlayBackend,
            "paste": WindowsPasteBackend,
            "hotkey": WindowsHotkeyBackend,
        }
    if sys.platform == "darwin":
        # Fase 4/5: REQUIEREN verificación en Mac real (pyobjc/pynput + permisos).
        from whisperflow.core import config
        from .macos.beep import MacOSBeepBackend
        from .macos.overlay import MacOSOverlayBackend
        from .macos.paste import MacOSPasteBackend
        from .macos.startup_init import apply_startup_init
        if config.MAC_HOTKEY == "cgevent":
            from .macos.hotkey_cgevent import CGEventTapHotkeyBackend
            hotkey_cls = CGEventTapHotkeyBackend
        else:
            from .macos.hotkey import MacOSHotkeyBackend
            hotkey_cls = MacOSHotkeyBackend
        return {
            "startup_init": apply_startup_init,
            "beep": MacOSBeepBackend,
            "overlay": MacOSOverlayBackend,
            "paste": MacOSPasteBackend,
            "hotkey": hotkey_cls,
        }
    raise NotImplementedError(
        f"Plataforma '{sys.platform}' no soportada todavía "
        f"(Fase 6: Linux)."
    )
