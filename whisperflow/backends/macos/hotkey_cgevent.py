# -*- coding: utf-8 -*-
"""Hotkeys globales en macOS vía CGEventTap nativo (pyobjc/Quartz).

Por qué este backend (y no pynput) es el default en Mac:
  - **Suprime teclas**: devolviendo ``None`` desde el callback se traga el evento, así
    las tone-keys ``,``/``.``/``-`` NO se escriben en el campo mientras se graba (igual
    que en Windows). pynput no suprime de forma fiable en Mac.
  - **No pasa por ``HIServices.AXIsProcessTrusted``**, que crashea con algunos combos
    pynput+pyobjc (``KeyError: 'AXIsProcessTrusted'``) dentro del contexto completo de
    la app. CGEventTap usa Quartz directamente.

Requiere **Accesibilidad** y **Supervisión de entrada**. Si el tap no se crea (falta
permiso), avisa por consola y los atajos no funcionan — pero la app no crashea.

Aordes (Mac): Cmd+Ctrl (push-to-talk), Cmd+Ctrl+Espacio (manos libres),
Cmd+Shift+Z (re-pegar). Tone-keys: ``,``/``.``/``-`` (suprimidas al escribir).
"""
import threading

from whisperflow.core.hotkey_base import HotkeyBackend, HotkeyCapabilities

# Keycodes (layout US). Suficiente para los modificadores, espacio, tone-keys y z.
_KC = {
    0x37: "cmd", 0x36: "cmd",        # left/right command
    0x3B: "ctrl", 0x3E: "ctrl",      # left/right control
    0x3A: "alt", 0x3D: "alt",        # left/right option
    0x31: "space",
    0x2B: ",", 0x2F: ".", 0x1B: "-",  # tone-keys
    0x06: "z",
}


class _Event:
    __slots__ = ("name", "event_type")

    def __init__(self, name, event_type):
        self.name = name
        self.event_type = event_type


class CGEventTapHotkeyBackend(HotkeyBackend):
    def __init__(self):
        self._on_event = None
        self._suppressible = {}   # nombre(tecla) -> handler (tone-keys)
        self._repaste_cb = None   # callback de re-paste (Cmd+Shift+Z)
        self._tap = None
        self._source = None
        self._thread = None
        self._runloop = None

    def start(self, on_event):
        self._on_event = on_event
        import Quartz
        from CoreFoundation import (CFMachPortCreateRunLoopSource, CFRunLoopAddSource,
                                    CFRunLoopGetCurrent, CFRunLoopRun, kCFRunLoopCommonModes)

        _FLAG_FOR = {"cmd": Quartz.kCGEventFlagMaskCommand,
                     "ctrl": Quartz.kCGEventFlagMaskControl,
                     "alt": Quartz.kCGEventFlagMaskAlternate,
                     "shift": Quartz.kCGEventFlagMaskShift}
        _FLAGS_CHANGED = Quartz.kCGEventFlagsChanged

        def tap_callback(proxy, event_type, event, refcon):
            try:
                keycode = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
                name = _KC.get(keycode, "")

                # Los modificadores en macOS llegan como FlagsChanged (no KeyDown/Up):
                # deducimos down/up mirando si su flag quedó prendido.
                if event_type == _FLAGS_CHANGED and name in _FLAG_FOR:
                    is_down = bool(Quartz.CGEventGetFlags(event) & _FLAG_FOR[name])
                    etype = "down" if is_down else "up"
                else:
                    is_down = event_type == Quartz.kCGEventKeyDown
                    etype = "down" if is_down else "up"

                # Re-paste: Cmd+Shift+Z (detectado por flags al presionar z).
                if name == "z" and is_down and self._repaste_cb is not None:
                    flags = Quartz.CGEventGetFlags(event)
                    if (flags & Quartz.kCGEventFlagMaskCommand) and (flags & Quartz.kCGEventFlagMaskShift):
                        try:
                            self._repaste_cb()
                        except Exception:
                            pass
                        return None  # tragamos la z

                # Tone-keys: despachar al handler y SUPRIMIR si devuelve False
                # (devuelve False mientras se graba -> la tecla no se escribe).
                if name in self._suppressible:
                    try:
                        swallow = self._suppressible[name](_Event(name, etype))
                    except Exception:
                        swallow = True
                    return None if not swallow else event

                # Modificadores / espacio: alimentan la máquina de estados.
                if name in ("ctrl", "cmd", "alt", "space"):
                    try:
                        on_event(_Event(name, etype))
                    except Exception:
                        pass
                return event
            except Exception:
                return event  # ante duda, dejar pasar el evento

        self._tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            0,   # placement = kCGHeadTapEventTap (pyobjc no expone el nombre; uso su valor)
            Quartz.kCGEventTapOptionDefault,   # permite suprimir (devolviendo None)
            (Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown)
             | Quartz.CGEventMaskBit(Quartz.kCGEventKeyUp)
             | Quartz.CGEventMaskBit(Quartz.kCGEventFlagsChanged)),  # modificadores
            tap_callback,
            None,
        )
        if self._tap is None:
            print("[whisperflow] CGEventTap NO se pudo crear (¿falta Accesibilidad / "
                  "Supervisión de entrada?). Los atajos no funcionarán.", flush=True)
            return

        self._source = CFMachPortCreateRunLoopSource(None, self._tap, 0)

        def _run():
            self._runloop = CFRunLoopGetCurrent()
            CFRunLoopAddSource(self._runloop, self._source, kCFRunLoopCommonModes)
            Quartz.CGEventTapEnable(self._tap, True)
            CFRunLoopRun()

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

    def register_suppressible_key(self, key, handler):
        self._suppressible[key] = handler

    def register_hotkey(self, combo, callback):
        # combo llega en sintaxis de la lib keyboard (ej. "ctrl+alt+z"). En Mac lo
        # manejamos dentro del tap como Cmd+Shift+Z; guardamos el callback.
        self._repaste_cb = callback

    def send(self, combo):
        _send_combo(combo)

    def release(self, key):
        pass  # CGEventTap no mantiene estado de teclas "mantenidas"

    def stop(self):
        try:
            from CoreFoundation import CFRunLoopStop, CFMachPortInvalidate
            if self._runloop is not None:
                CFRunLoopStop(self._runloop)
            if self._tap is not None:
                CFMachPortInvalidate(self._tap)
        except Exception:
            pass

    def capabilities(self):
        return HotkeyCapabilities(suppress_supported=True,
                                  send_supported=True,
                                  observe_all_keys=True)


def _send_combo(combo):
    """Síntesis mínima vía CGEvent (soporta 'cmd+v', 'ctrl+v'). El pegado real lo hace
    ``paste.py`` (que también usa CGEvent), así que esto casi no se usa."""
    try:
        import Quartz
        mods_map = {"cmd": (0x37, Quartz.kCGEventFlagMaskCommand),
                    "ctrl": (0x3B, Quartz.kCGEventFlagMaskControl),
                    "shift": (0x38, Quartz.kCGEventFlagMaskShift),
                    "alt": (0x3A, Quartz.kCGEventFlagMaskAlternate)}
        key_kc = {"v": 0x09, "z": 0x06, "c": 0x08}
        parts = [p.strip() for p in combo.split("+")]
        key = parts[-1]
        mods = [p for p in parts[:-1] if p in mods_map]
        src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
        flag = 0
        for m in mods:
            flag |= mods_map[m][1]
        for m in mods:
            Quartz.CGEventPost(Quartz.kCGHIDEventTap,
                               Quartz.CGEventCreateKeyboardEvent(src, mods_map[m][0], True))
        kd = Quartz.CGEventCreateKeyboardEvent(src, key_kc.get(key, 0), True)
        ku = Quartz.CGEventCreateKeyboardEvent(src, key_kc.get(key, 0), False)
        Quartz.CGEventSetFlags(kd, flag)
        Quartz.CGEventSetFlags(ku, flag)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, kd)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, ku)
        for m in reversed(mods):
            Quartz.CGEventPost(Quartz.kCGHIDEventTap,
                               Quartz.CGEventCreateKeyboardEvent(src, mods_map[m][0], False))
    except Exception:
        pass
