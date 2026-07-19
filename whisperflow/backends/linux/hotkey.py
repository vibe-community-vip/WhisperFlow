# -*- coding: utf-8 -*-
"""Hotkeys globales en Linux: lib ``keyboard`` (X11).

Misma API que el backend de Windows (la lib keyboard es cross-platform Win/Linux). En
Linux, para hooks globales y SUPRESIÓN de teclas, la lib necesita acceso a
``/dev/uinput``: el usuario debe estar en el grupo ``input`` (o una regla udev), o
correr como root. Sin eso, los atajos NO funcionan (fallan silenciosamente).

Wayland: la lib keyboard NO captura teclas globales bajo la mayoría de los
compositores (restricción del portal de seguridad). En Wayland, el workaround es
 vincular un atajo del compositor (GNOME/KDE) que ejecute un subcomando CLI de
WhisperFlow (fuera del alcance de esta versión).

Acordes: Ctrl+Super (PTT), Ctrl+Super+Espacio (manos libres), Ctrl+Alt+Z (re-pegar)
— Super es reportada como "windows" por la lib, así que la máquina de estados la
trata igual que en Windows.
"""
import keyboard

from whisperflow.core.hotkey_base import HotkeyBackend, HotkeyCapabilities


class LinuxHotkeyBackend(HotkeyBackend):
    def start(self, on_event):
        keyboard.hook(on_event)

    def register_suppressible_key(self, key, handler):
        keyboard.hook_key(key, handler, suppress=True)

    def register_hotkey(self, keys, callback):
        # keys canónicos -> sintaxis de la lib keyboard (super => "windows").
        combo = "+".join({"super": "windows"}.get(k, k) for k in keys)
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
        return HotkeyCapabilities(suppress_supported=True,   # con uinput/root
                                  send_supported=True,
                                  observe_all_keys=True)
