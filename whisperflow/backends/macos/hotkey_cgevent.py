# -*- coding: utf-8 -*-
"""Hotkeys globales en macOS vía CGEventTap nativo (pyobjc/Quartz) — Fase 5 (experimental).

A diferencia del backend pynput (Fase 4), CGEventTap **sí permite suprimir teclas**
(devolviendo None desde el callback se traga el evento). Así las tone-keys
(,/./-) dejan de escribirse en el campo mientras se graba, igual que en Windows.

AVISO: NO verificado en Mac real (falta pyobjc en el entorno y requiere permisos de
Accesibilidad Y de "Supervisión de entrada"). Es complejo (run loop, mapeo de
keycodes, síntesis de eventos); trátalo como experimental y validá paso a paso.
Seleccionable con ``WHISPERFLOW_MAC_HOTKEY=cgevent`` (default: pynput).
"""
import threading

from whisperflow.core.hotkey_base import HotkeyBackend, HotkeyCapabilities

# Keycodes (layout US) de las teclas que nos interesan.
_KC = {
    0x37: "cmd", 0x36: "cmd",        # left/right command
    0x3B: "ctrl", 0x3E: "ctrl",      # left/right control
    0x3A: "alt", 0x3D: "alt",        # left/right option
    0x31: "space",
}


class _Event:
    __slots__ = ("name", "event_type")

    def __init__(self, name, event_type):
        self.name = name
        self.event_type = event_type


class CGEventTapHotkeyBackend(HotkeyBackend):
    """Captura global vía CGEventTap. Puede suprimir (suppress_supported=True)."""

    def __init__(self):
        self._on_event = None
        self._suppressible = {}   # nombre(tecla) -> handler
        self._tap = None
        self._source = None
        self._thread = None
        self._runloop = None

    # --- mapeo keycode -> nombre ---
    @staticmethod
    def _name_for(event, keycode):
        if keycode in _KC:
            return _KC[keycode]
        # Letras/signos: pedir el unicode al evento.
        try:
            import Quartz
            n = Quartz.CGEventKeyboardGetUnicodeString(event, 4, None, None)
            # Algunas versiones de pyobjc devuelven (string, len); normalizamos:
            if isinstance(n, tuple):
                n = n[0]
            if n:
                return n[:1].lower()
        except Exception:
            pass
        return ""

    def start(self, on_event):
        self._on_event = on_event

        def tap_callback(proxy, event_type, event, refcon):
            try:
                import Quartz
                keycode = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
                name = self._name_for(event, keycode)
                is_down = event_type == Quartz.kCGEventKeyDown
                etype = "down" if is_down else "up"

                # Tone-keys: despachar al handler y SUPRIMIR si este devuelve False
                # (es decir, mientras se graba). Fuera de grabación, pasa la tecla.
                if name in self._suppressible:
                    try:
                        swallow = self._suppressible[name](_Event(name, etype))
                    except Exception:
                        swallow = True
                    return None if not swallow else event

                # Modificadores / espacio / resto: alimentan la máquina de estados.
                if name in ("ctrl", "cmd", "alt", "space"):
                    try:
                        on_event(_Event(name, etype))
                    except Exception:
                        pass
                return event
            except Exception:
                return event  # ante cualquier duda, dejar pasar

        import Quartz
        from CoreFoundation import (CFRunLoopGetCurrent, CFRunLoopAddSource,
                                    kCFRunLoopCommonModes, CFRunLoopRun, CFRunLoopStop)

        # kCGEventTapOptionDefault permite suprimir (devolviendo None). Head tap = alta prioridad.
        self._tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            Quartz.kCGHeadTapEventTap,
            Quartz.kCGEventTapOptionDefault,
            Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown) | Quartz.CGEventMaskBit(Quartz.kCGEventKeyUp),
            tap_callback,
            None,
        )
        if self._tap is None:
            print("[whisperflow] CGEventTap NO se pudo crear (¿falta permiso de Accesibilidad "
                  "y/o Supervisión de entrada?). El backend cgevent no funcionará.", flush=True)
            return

        self._source = Quartz.CFMachPortCreateRunLoopSource(None, self._tap, 0)

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
        # Con CGEventTap podríamos detectar el acorde de re-paste aquí mismo, pero para
        # mantenerlo simple delegamos al registro normal (Command ya se trackea). En la
        # práctica, el re-paste se maneja como cualquier otra secuencia observada.
        # (Por ahora no se registra un globalhotkeys aparte: verificación pendiente.)
        pass

    def send(self, combo):
        # Síntesis vía CGEvent (igual que macos/paste.py para cmd+v).
        try:
            import Quartz
            # Soporta "cmd+v"; se puede extender. El pegado real lo hace paste.py.
            mapping = {"v": 0x09, "z": 0x06, "cmd": 0x37, "ctrl": 0x3B}
            parts = combo.split("+")
            key = parts[-1]
            mods = parts[:-1]
            src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
            for m in mods:
                md = Quartz.CGEventCreateKeyboardEvent(src, mapping.get(m, 0), True)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, md)
            kd = Quartz.CGEventCreateKeyboardEvent(src, mapping.get(key, 0), True)
            ku = Quartz.CGEventCreateKeyboardEvent(src, mapping.get(key, 0), False)
            flag = 0
            if "cmd" in mods: flag |= Quartz.kCGEventFlagMaskCommand
            if "ctrl" in mods: flag |= Quartz.kCGEventFlagMaskControl
            Quartz.CGEventSetFlags(kd, flag)
            Quartz.CGEventSetFlags(ku, flag)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, kd)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, ku)
            for m in reversed(mods):
                mu = Quartz.CGEventCreateKeyboardEvent(src, mapping.get(m, 0), False)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, mu)
        except Exception:
            pass

    def release(self, key):
        pass  # CGEventTap no mantiene estado de teclas "mantenidas" como pynput

    def stop(self):
        try:
            import Quartz
            from CoreFoundation import CFRunLoopStop
            if self._runloop is not None:
                CFRunLoopStop(self._runloop)
            if self._tap is not None:
                Quartz.CFMachPortInvalidate(self._tap)
        except Exception:
            pass

    def capabilities(self):
        return HotkeyCapabilities(suppress_supported=True,
                                  send_supported=True,
                                  observe_all_keys=True)
