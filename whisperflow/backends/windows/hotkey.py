# -*- coding: utf-8 -*-
"""Hotkeys globales en Windows: envoltorio sobre la lib ``keyboard``."""
import keyboard

from whisperflow.core.hotkey_base import HotkeyBackend, HotkeyCapabilities


class WindowsHotkeyBackend(HotkeyBackend):
    def start(self, on_event):
        keyboard.hook(on_event)

    def register_suppressible_key(self, key, handler):
        # suppress=True: puede BLOQUEAR la tecla para que no llegue al campo con foco.
        # El handler devuelve True = dejar pasar, False = tragarla (ver CLAUDE.md).
        keyboard.hook_key(key, handler, suppress=True)

    def register_hotkey(self, combo, callback):
        keyboard.add_hotkey(combo, callback)

    def send(self, combo):
        keyboard.send(combo)

    def release(self, key):
        keyboard.release(key)

    def stop(self):
        try:
            keyboard.unhook_all()
        except Exception:
            pass

    def capabilities(self):
        return HotkeyCapabilities(suppress_supported=True,
                                  send_supported=True,
                                  observe_all_keys=True)
