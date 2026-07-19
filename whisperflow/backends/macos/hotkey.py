# -*- coding: utf-8 -*-
"""Hotkeys globales en macOS: ``pynput`` (Listener + GlobalHotKeys).

Aordes (Fase 4, Mac v1):
  - Push-to-talk / manos libres: **Cmd+Ctrl** (+ Espacio). Funciona con la misma
    máquina de estados de app.py, porque _normalize mapea cmd->windows y ctrl->ctrl
    (la máquina detecta "ctrl"+"windows" ambos abajo). Usamos pynput.Listener (hook
    global crudo) y no GlobalHotKeys para PTT: evita el bug de pynput #297 (acordes
    con Ctrl/Alt no matchean bien en Mac).
  - Re-pegar último: **Cmd+Shift+Z** (vía GlobalHotKeys; acordes con Cmd/Shift sí
    funcionan en pynput Mac).
  - Tone-keys (,/./-): se DETECTAN y eligen el perfil, pero **NO se suprimen**
    (capabilities.suppress_supported=False): la tecla se escribe en el campo; el
    usuario la borra. La supresión total requiere CGEventTap (Fase 5).
"""
from pynput import keyboard as pk

from whisperflow.core.hotkey_base import HotkeyBackend, HotkeyCapabilities


class _Event:
    """Adapta un evento pynput a la forma {name, event_type} que usa app.on_event."""
    __slots__ = ("name", "event_type")

    def __init__(self, name, event_type):
        self.name = name
        self.event_type = event_type


def _key_name(key):
    """Nombre normalizado de una tecla pynput."""
    if key in (pk.Key.cmd, pk.Key.cmd_l, pk.Key.cmd_r):
        return "cmd"
    if key in (pk.Key.ctrl, pk.Key.ctrl_l, pk.Key.ctrl_r):
        return "ctrl"
    if key in (pk.Key.alt, pk.Key.alt_l, pk.Key.alt_r):
        return "alt"
    if key == pk.Key.space:
        return "space"
    if isinstance(key, pk.KeyCode):
        # char puede ser "," "." "-" "z" o None (modificadores sueltos).
        return key.char or ""
    return ""


class MacOSHotkeyBackend(HotkeyBackend):
    def __init__(self):
        self._listener = None
        self._global_hotkeys = None
        self._controller = pk.Controller()
        self._suppressible = {}  # nombre(tecla) -> handler (tone-keys; sin supresión real)

    def start(self, on_event):
        def on_press(key):
            name = _key_name(key)
            # Tone-keys: despachar a su handler si está registrado (registra el perfil,
            # pero NO bloquea la tecla — limitación de Mac v1).
            if name in self._suppressible:
                try:
                    self._suppressible[name](_Event(name, "down"))
                except Exception:
                    pass
                return
            on_event(_Event(name, "down"))

        def on_release(key):
            name = _key_name(key)
            if name in self._suppressible:
                return
            on_event(_Event(name, "up"))

        self._listener = pk.Listener(on_press=on_press, on_release=on_release)
        self._listener.daemon = True
        self._listener.start()

    def register_suppressible_key(self, key, handler):
        # key viene como ","/"."/"-" desde app.py. Lo guardamos para despacharlo en
        # on_press. NO hay supresión real en Mac v1 (la tecla se escribe igual).
        self._suppressible[key] = handler

    def register_hotkey(self, combo, callback):
        # combo llega en sintaxis de la lib keyboard (ej. "ctrl+alt+z"). En Mac lo
        # traducimos a un acorde friendly con pynput GlobalHotKeys: Cmd+Shift+Z.
        # (Solo se registra el re-pegar de último texto.)
        try:
            self._global_hotkeys = pk.GlobalHotKeys({
                "<cmd>+<shift>+z": callback,
            })
            self._global_hotkeys.daemon = True
            self._global_hotkeys.start()
        except Exception as e:
            print(f"[whisperflow] no se pudo registrar el atajo de re-paste en Mac: {e}",
                  flush=True)

    def send(self, combo):
        # Síntesis básica vía pynput Controller (puede requerir Accesibilidad).
        # El pegado real no usa esto: ver macos/paste.py (CGEvent).
        try:
            parts = combo.split("+")
            for p in parts:
                self._controller.press(p)
            for p in reversed(parts):
                self._controller.release(p)
        except Exception:
            pass

    def release(self, key):
        try:
            self._controller.release(key)
        except Exception:
            pass

    def stop(self):
        try:
            if self._listener:
                self._listener.stop()
        except Exception:
            pass
        try:
            if self._global_hotkeys:
                self._global_hotkeys.stop()
        except Exception:
            pass

    def capabilities(self):
        return HotkeyCapabilities(suppress_supported=False,   # Mac v1: sin supresión
                                  send_supported=True,        # best-effort vía Controller/CGEvent
                                  observe_all_keys=True)
